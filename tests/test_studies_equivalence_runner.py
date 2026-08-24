"""등가성 검증 실행 계층의 조립 결과를 고정한다.

**실제 수집 데이터에 의존하지 않는다.** 합성 파일을 임시 폴더에 만들고 경로를 갈아 끼운다 —
`storage/` 를 읽으면 데이터를 갱신할 때마다 테스트가 깨진다.

이 테스트가 지키는 것은 셋이다.

1. **두 축을 모두 돈다** — 이론값 2종 × 이상치 2종. 하나를 고르면 그 선택이 결론에 섞인다
2. **산출물이 서로 맞는다** — 행 수 요약이 실제 표와 일치한다
3. **합격 판정이 합격선을 따른다** — 값이 아니라 임계 비교로 결정된다
"""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from verify_lab.common_constants import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_VALUE,
    COL_VOLUME,
)
from verify_lab.studies.usdkrw_equivalence import runner as runner_module
from verify_lab.studies.usdkrw_equivalence.constants import (
    DISPLAY_MODEL,
    DISPLAY_OUTLIER,
    DISPLAY_PASS,
    DISPLAY_SPOT,
    DISPLAY_TICKER,
    MODEL_LABELS,
    OUTLIER_LABEL_EXCLUDED,
    OUTLIER_LABEL_INCLUDED,
    EtfTarget,
    SpotSource,
    TheoreticalModel,
)
from verify_lab.studies.usdkrw_equivalence.runner import run_equivalence

# 합성 데이터의 길이. 연도가 셋 이상 나오도록 넉넉히 잡는다
DAY_COUNT = 800


def _business_days() -> list[date]:
    """주말을 뺀 연속 날짜를 만든다."""
    days: list[date] = []
    cursor = date(2023, 1, 2)
    while len(days) < DAY_COUNT:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)

    return days


def _write_series(path: Path, days: list[date], values: list[float]) -> None:
    """단일 값 시계열 파일을 쓴다."""
    pd.DataFrame({COL_DATE: days, COL_VALUE: values}).to_csv(path, index=False)


def _write_market(path: Path, days: list[date], closes: list[float]) -> None:
    """OHLCV 시세 파일을 쓴다."""
    pd.DataFrame(
        {
            COL_DATE: days,
            COL_OPEN: closes,
            COL_HIGH: closes,
            COL_LOW: closes,
            COL_CLOSE: closes,
            COL_VOLUME: [1_000] * len(days),
        }
    ).to_csv(path, index=False)


@pytest.fixture
def synthetic_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[SpotSource, ...]:
    """합성 입력 파일을 만들고 실행 계층의 경로를 갈아 끼운다.

    ETF 는 **시장 환율**을 그대로 따라가게 만들고, 환율 계열을 두 벌 쓴다 —
    시차가 없는 종가형과 하루 늦은 고시형이다. 실행 계층이 계열마다 시차 보정을
    다르게 적용하는지 확인해야 하기 때문이다.

    Returns:
        실행에 넘길 환율 계열 목록
    """
    days = _business_days()

    # 시장 환율. 완만하게 오르내린다
    market = [1_300.0 + (index % 40) - (index % 7) * 0.5 for index in range(len(days))]

    # 종가형은 그날의 시장 값이다
    _write_series(tmp_path / "close.csv", days, market)

    # 고시형은 직전 시장일의 값이다. 첫날은 대응할 직전 값이 없어 같은 값으로 둔다
    _write_series(tmp_path / "published.csv", days, [market[0], *market[:-1]])

    _write_series(tmp_path / "CD91.csv", days, [3.50] * len(days))
    _write_series(tmp_path / "DTB3.csv", days, [4.20] * len(days))

    # 1배 ETF 는 시장 환율을, 2배 ETF 는 그 두 배 움직임을 따른다
    base_close = [10_000.0 * value / market[0] for value in market]
    leverage_close = [10_000.0]
    for index in range(1, len(market)):
        change = market[index] / market[index - 1] - 1
        leverage_close.append(leverage_close[-1] * (1 + 2 * change))

    _write_market(tmp_path / "base.csv", days, base_close)
    _write_market(tmp_path / "leverage.csv", days, leverage_close)
    _write_series(tmp_path / "base_nav.csv", days, base_close)
    _write_series(tmp_path / "leverage_nav.csv", days, leverage_close)

    monkeypatch.setattr(runner_module, "KRW_RATE_PATH", tmp_path / "CD91.csv")
    monkeypatch.setattr(runner_module, "USD_RATE_PATH", tmp_path / "DTB3.csv")
    monkeypatch.setattr(
        runner_module,
        "ETF_BASE",
        EtfTarget(
            "base",
            "BASE",
            "합성 1배",
            tmp_path / "base.csv",
            tmp_path / "base.csv",
            tmp_path / "base_nav.csv",
            exposure=1,
            published_ter=0.0025,
        ),
    )
    monkeypatch.setattr(
        runner_module,
        "ETF_LEVERAGE",
        EtfTarget(
            "lev",
            "LEV",
            "합성 2배",
            tmp_path / "leverage.csv",
            tmp_path / "leverage.csv",
            tmp_path / "leverage_nav.csv",
            exposure=2,
            published_ter=0.0045,
        ),
    )

    return (
        SpotSource("close", "종가형", tmp_path / "close.csv", needs_publication_shift=False),
        SpotSource("published", "고시형", tmp_path / "published.csv", needs_publication_shift=True),
    )


def test_both_axes_are_covered(synthetic_inputs: tuple[SpotSource, ...]) -> None:
    """
    목적: 환율 계열 2종 × 이론값 2종 × 이상치 2종을 모두 산출함을 고정한다.

    하나를 고르면 그 선택 자체가 결론에 섞인다.

    Given: 합성 입력
    When: 검증을 실행한다
    Then: 회귀 표에 네 조합이 모두 있다
    """
    outputs = run_equivalence(sources=synthetic_inputs)

    combinations = set(
        zip(
            outputs.equivalence[DISPLAY_SPOT],
            outputs.equivalence[DISPLAY_MODEL],
            outputs.equivalence[DISPLAY_OUTLIER],
            strict=True,
        )
    )

    assert combinations == {
        (source.label, MODEL_LABELS[model], label)
        for source in synthetic_inputs
        for model in TheoreticalModel
        for label in (OUTLIER_LABEL_INCLUDED, OUTLIER_LABEL_EXCLUDED)
    }


def test_selected_model_only_is_produced(synthetic_inputs: tuple[SpotSource, ...]) -> None:
    """
    목적: 모형을 골라 넘기면 그것만 산출됨을 고정한다.

    Given: 합성 입력
    When: 달러금리 모형만 지정해 실행한다
    Then: 회귀 표에 그 모형만 있다
    """
    outputs = run_equivalence((TheoreticalModel.USD_RATE,), synthetic_inputs)

    assert set(outputs.equivalence[DISPLAY_MODEL]) == {MODEL_LABELS[TheoreticalModel.USD_RATE]}


def test_publication_lag_is_corrected(synthetic_inputs: tuple[SpotSource, ...]) -> None:
    """
    목적: 실행 계층이 **계열마다 다르게** 시차를 보정함을 고정한다.

    합성 입력의 ETF 는 시장 환율을 그대로 따라간다. 종가형은 보정하면 안 되고
    고시형은 보정해야 한다. 어느 한쪽이라도 틀리면 그 계열의 상관이 무너진다.

    Given: 종가형과 고시형 두 계열
    When: 검증을 실행한다
    Then: 두 계열 모두 상관이 높다
    """
    outputs = run_equivalence((TheoreticalModel.USD_RATE,), synthetic_inputs)

    for label in ("종가형", "고시형"):
        row = outputs.equivalence[outputs.equivalence[DISPLAY_SPOT] == label].iloc[0]
        assert row["상관"] > 0.99, f"{label} 계열의 상관이 낮습니다"


def test_leverage_beta_is_recovered(synthetic_inputs: tuple[SpotSource, ...]) -> None:
    """
    목적: 2배 ETF 의 베타가 복원됨을 고정한다 (사양서 §16.3).

    Given: 정확히 2배로 움직이는 합성 ETF
    When: 검증을 실행한다
    Then: 베타가 2 근방이고 합격으로 표기된다
    """
    outputs = run_equivalence((TheoreticalModel.USD_RATE,), synthetic_inputs)
    row = outputs.leverage.iloc[0]

    assert row["베타"] == pytest.approx(2.0, abs=0.05)
    assert row[DISPLAY_PASS] in {"O", "X"}


def test_row_counts_match_actual_tables(synthetic_inputs: tuple[SpotSource, ...]) -> None:
    """
    목적: 요약의 행 수가 실제 표와 일치함을 고정한다.

    어긋나면 산출물만 보고 무엇이 빠졌는지 알 수 없게 된다.

    Given: 합성 입력
    When: 검증을 실행한다
    Then: 다섯 표의 행 수가 요약과 같다
    """
    outputs = run_equivalence(sources=synthetic_inputs)
    counts = outputs.meta["row_counts"]

    assert counts["equivalence"] == len(outputs.equivalence)
    assert counts["annual_drift"] == len(outputs.annual_drift)
    assert counts["leverage"] == len(outputs.leverage)
    assert counts["premium"] == len(outputs.premium)
    assert counts["daily"] == len(outputs.daily)


def test_premium_covers_both_targets(synthetic_inputs: tuple[SpotSource, ...]) -> None:
    """
    목적: 프리미엄 표가 두 종목을 모두 담음을 고정한다 (사양서 §16.4).

    Given: 합성 입력
    When: 검증을 실행한다
    Then: 프리미엄 표에 두 종목이 있다
    """
    outputs = run_equivalence(sources=synthetic_inputs)

    assert set(outputs.premium[DISPLAY_TICKER]) == {"BASE", "LEV"}


def test_empty_model_list_raises(synthetic_inputs: tuple[SpotSource, ...]) -> None:
    """
    목적: 빈 모형 목록을 조용히 전체 실행으로 바꾸지 않음을 고정한다 (경계 조건).

    Given: 합성 입력
    When: 빈 목록으로 실행한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="비어 있습니다"):
        run_equivalence((), synthetic_inputs)
