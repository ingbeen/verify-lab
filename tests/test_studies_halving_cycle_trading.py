"""반감기_사이클 체결 조립 — 측정과 같은 날에 들어가고, 무손절 · 「위」 한 방향으로만 내는지 고정한다.

매매 산출물의 공통 컬럼·순서·값 형식은 `tests/test_output_contract.py` 가 매매법 전부에 한꺼번에 건다.
**여기서는 이 매매법만의 계약**을 본다.

| 무엇 | 왜 |
| --- | --- |
| 체결가 = 측정 가격 | 진입일 정의가 두 벌이 되면 측정과 체결이 다른 날에 들어가는데 예외는 나지 않는다 |
| 무손절 · 「위」 | 손절은 사용자가 따로 정한다(결정 ⑦). 두 방향을 내면 측정 표와의 1:1 조인이 깨진다(2026-09-29 결정 f) |
| 대상별 신호·제외 건수 | 성적표에 `제외` 컬럼을 두지 않으므로 요약이 그 자리다 (표본 보존) |
"""

from pathlib import Path

import numpy as np
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
    MARKET_FILE_TEMPLATE,
    PRICE_DECIMALS,
)
from verify_lab.execution.constants import NO_STOP_LABEL, PERIODS
from verify_lab.execution.run_summary import KEY_RULE
from verify_lab.measure.constants import (
    COL_ENTRY_CLOSE,
    COL_EXCLUDED_COUNT,
    COL_EXCLUDED_REASON,
    COL_EXIT_CLOSE,
    COL_FORWARD_RETURN,
    COL_SIGNAL_COUNT,
    REASON_NONE,
)
from verify_lab.measure.screening import DIRECTION_UP
from verify_lab.measure.statistics import COL_SAMPLE_COUNT
from verify_lab.studies.halving_cycle.constants import (
    COL_ENTRY_MONTHS,
    COL_HALVING,
    COL_HOLD_MONTHS,
    ENTRY_MONTHS,
    HALVINGS,
    HOLD_MONTHS,
    Dataset,
)
from verify_lab.studies.halving_cycle.runner import StudyOutputs, run_study
from verify_lab.studies.halving_cycle.trading import KEY_TARGETS, TradingOutputs, run_halving_cycle_trading

# 합성 시세 구간 — 네 반감기가 모두 시세 안에 든다
SYNTHETIC_START = "2012-01-01"
SYNTHETIC_END = "2025-12-31"

# 합성 시세를 만드는 난수 시드. **시드 없는 난수는 금지다**
SYNTHETIC_SEED = 20260930


def _dataset(directory: Path) -> Dataset:
    """매일 거래하는 합성 시세와 기준가를 파일로 쓰고 대상 하나를 만든다."""
    days = pd.date_range(SYNTHETIC_START, SYNTHETIC_END, freq="D")
    rng = np.random.default_rng(SYNTHETIC_SEED)
    closes = np.round(100.0 * np.cumprod(np.concatenate([[1.0], 1.0 + rng.normal(0.001, 0.02, len(days) - 1)])), 4)
    dates = days.strftime("%Y-%m-%d")

    pd.DataFrame(
        {
            COL_DATE: dates,
            COL_OPEN: np.round(closes * 0.999, 4),
            COL_HIGH: np.round(closes * 1.01, 4),
            COL_LOW: np.round(closes * 0.98, 4),
            COL_CLOSE: closes,
            COL_VOLUME: 1_000.0,
        }
    ).to_csv(directory / MARKET_FILE_TEMPLATE.format(ticker="SYN"), index=False)
    reference_path = directory / "SYN_PriceUSD.csv"
    pd.DataFrame({COL_DATE: dates, COL_VALUE: np.round(closes * 1.001, 4)}).to_csv(reference_path, index=False)

    # 온체인 두 계열은 측정(2단계)만 읽는다 — 이 파일의 대조 테스트가 측정을 함께 돌려 파일이 있어야 한다
    mvrv_path = directory / "SYN_CapMVRVCur.csv"
    pd.DataFrame({COL_DATE: dates, COL_VALUE: 2.0}).to_csv(mvrv_path, index=False)
    market_cap_path = directory / "SYN_CapMrktCurUSD.csv"
    pd.DataFrame({COL_DATE: dates, COL_VALUE: np.round(closes * 1e6, 0)}).to_csv(market_cap_path, index=False)

    return Dataset(
        ticker="SYN",
        label="합성 비트코인",
        directory=directory,
        file_template=MARKET_FILE_TEMPLATE,
        reference_path=reference_path,
        mvrv_path=mvrv_path,
        market_cap_path=market_cap_path,
        price_decimals=PRICE_DECIMALS,
        is_judged=True,
    )


@pytest.fixture(scope="module")
def dataset(tmp_path_factory: pytest.TempPathFactory) -> Dataset:
    """합성 대상."""
    return _dataset(tmp_path_factory.mktemp("halving_trading"))


@pytest.fixture(scope="module")
def trading(dataset: Dataset) -> TradingOutputs:
    """합성 입력으로 돈 체결 결과."""
    return run_halving_cycle_trading((dataset,))


@pytest.fixture(scope="module")
def study(dataset: Dataset) -> StudyOutputs:
    """같은 입력으로 돈 측정 결과 — 체결과 대조한다."""
    return run_study((dataset,), repeats=10, seed=0)


def test_성적표는_칸마다_시기_다섯_행이다(trading: TradingOutputs) -> None:
    """
    목적: 48칸 × 시기 5행이 빠짐없이 나옴을 고정한다 (측정의 원칙 17).

    Given: 합성 입력의 체결 결과
    When: 성적표 행 수를 본다
    Then: 칸 수 × 시기 수다
    """
    assert len(trading.performance) == len(ENTRY_MONTHS) * len(HOLD_MONTHS) * len(PERIODS)


def test_방향은_위_하나이고_손절은_걸지_않는다(trading: TradingOutputs) -> None:
    """
    목적: 결정 ⑦ · f 를 고정한다 — 두 방향이나 손절선 격자가 섞이면 측정 표와 조인이 깨진다.

    Given: 성적표와 거래내역
    When: 방향과 손절선 값을 모은다
    Then: 방향은 「위」, 손절선은 「무손절」 하나씩이다
    """
    for table in (trading.performance, trading.trades):
        assert set(table["방향"]) == {DIRECTION_UP}
        assert set(table["손절선(%)"]) == {NO_STOP_LABEL}


def test_체결은_측정과_같은_날_같은_가격에_들어간다(trading: TradingOutputs, study: StudyOutputs) -> None:
    """
    목적: 진입일 정의가 한 벌임을 고정한다 — 거래내역의 진입가·청산가·수익률이 측정 원자료와 같다.

    무손절이라 체결 수익률이 곧 측정 수익률이다. 어긋나면 두 계층이 다른 날에 들어간 것이다.

    Given: 같은 입력의 체결 결과와 측정 결과
    When: (반감기, 진입, 보유)로 맞대어 견준다
    Then: 체결 수가 유효 측정 수와 같고 진입가·청산가·수익률이 같다
    """
    # Given
    measured = study.entries[study.entries[COL_EXCLUDED_REASON] == REASON_NONE]
    trades = trading.trades.rename(
        columns={"반감기": COL_HALVING, "반감기 뒤 진입(개월)": COL_ENTRY_MONTHS, "보유(개월)": COL_HOLD_MONTHS}
    )

    # When
    joined = trades.merge(measured, on=[COL_HALVING, COL_ENTRY_MONTHS, COL_HOLD_MONTHS], how="outer", indicator=True)

    # Then
    assert (joined["_merge"] == "both").all(), "체결과 측정 중 한쪽에만 있는 진입이 있습니다"
    assert len(trades) == len(measured)
    np.testing.assert_allclose(joined["진입가"], joined[COL_ENTRY_CLOSE], atol=0.01)
    np.testing.assert_allclose(joined["청산가"], joined[COL_EXIT_CLOSE], atol=0.01)
    np.testing.assert_allclose(joined["수익률(%)"], (joined[COL_FORWARD_RETURN] * 100).round(2), atol=0.1)


def test_거래내역의_반감기는_상수의_날짜다(trading: TradingOutputs) -> None:
    """
    목적: 어느 사이클의 체결인지 행 안에서 읽힘을 고정한다 — 날짜만으로는 사이클이 바로 읽히지 않는다.

    Given: 거래내역
    When: 반감기 값을 모은다
    Then: 반감기 상수의 날짜 넷이다 (합성 입력이 네 사이클을 모두 덮는다)
    """
    assert set(trading.trades["반감기"]) == {halving.label for halving in HALVINGS}


def test_대상별_신호와_제외_건수가_측정과_같다(trading: TradingOutputs, study: StudyOutputs) -> None:
    """
    목적: 요약의 제외 건수가 측정이 센 것과 같음을 고정한다 (표본 보존 — 성적표에는 제외 컬럼이 없다).

    Given: 체결 요약과 측정 통계
    When: 대상별 기록을 본다
    Then: 신호 수와 제외 수가 통계 표의 합과 같다
    """
    # Given
    record = trading.summary[KEY_RULE][KEY_TARGETS][0]

    # When / Then
    assert record["signal_count"] == int(study.statistics[COL_SIGNAL_COUNT].sum())
    assert record["excluded_count"] == int(study.statistics[COL_EXCLUDED_COUNT].sum())
    assert len(trading.trades) == int(study.statistics[COL_SAMPLE_COUNT].sum())
