"""검증 #7 실행 계층의 계약을 고정한다.

집계표는 **행이 무엇에 대한 값인지**를 스스로 밝혀야 한다. 식별 컬럼이 빠진 표는 예외 없이
정상으로 보이면서 해석이 불가능해진다 — 실제로 축 컬럼이 사라진 채 산출된 적이 있다.

고정하는 계약은 넷이다.
- 집계표에 축과 식별 컬럼이 모두 남는다
- 만기월 축에 **같은 달 베이스라인**이 붙는다 — 없으면 9월 약세가 만기 효과인지 계절성인지 못 가른다
- **확정 칸만 낸다** — 산출물은 칸마다 한 행이고 종목·만기월·방향이 그 행을 식별한다
- **배당락을 함께 잰다** — 「걸린 건 0」과 「수정주가가 없어 못 쟀다」가 구별돼야 한다

**상대 거래일 ±10 격자와 시기 2등분 표의 테스트는 2026-09-21 에 사라졌다** — 그 축들을
산출물에서 없앴기 때문이며, 상대 거래일은 결과 문서가 「우위 없음」으로 닫은 축이고
시기 2등분은 성적표의 시기 5행이 같은 질문에 더 고른 표본으로 답한다.
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_EXCLUDED_REASON,
    COL_FORWARD_RETURN,
    COL_HORIZON,
    COL_MEAN_RATE_CONFLICT,
    REASON_NONE,
    REASON_OUT_OF_RANGE,
)
from verify_lab.measure.statistics import (
    COL_DOWN_RATE_P_VALUE,
    COL_LOSS_RATE,
    COL_LOSS_RATE_EXCESS,
    COL_MEAN,
    COL_MEAN_P_VALUE,
    COL_UP_RATE_P_VALUE,
    COL_WIN_RATE,
)
from verify_lab.studies.option_expiry.constants import (
    COL_EXPIRY_MONTH_NUMBER,
    COL_HOLD_DAYS,
    COL_TICKER,
    HORIZON_NEXT_WEEK_EXIT,
    US_MONTHLY_EXPIRY,
    Dataset,
)
from verify_lab.studies.option_expiry.runner import (
    _aggregate_by_month,
    _per_length,
)

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12


def _market(closes: Sequence[float], start: str = "2026-01-02") -> pd.DataFrame:
    """합성 시세를 만든다. 만기일 판정과 일간 등락은 날짜와 종가만 보므로 나머지는 종가와 같게 둔다."""
    prices = list(closes)

    return pd.DataFrame(
        {
            COL_DATE: pd.bdate_range(start, periods=len(prices)),
            COL_OPEN: prices,
            COL_HIGH: prices,
            COL_LOW: prices,
            COL_CLOSE: prices,
            COL_VOLUME: [1_000] * len(prices),
        }
    )


class TestWeeklyTradeAssembly:
    """만기일 매수 → 다음주 청산 매매의 조립 계약을 고정한다."""

    def test_길이별_변환은_제외행을_버리고_보유일수를_축으로_쓴다(self) -> None:
        """
        목적: 「같은 길이 단순 보유」와 견줄 수 있는 형태를 고정한다

        제외된 행은 보유일수가 없어 어느 칸에도 속하지 못한다. **제외 건수는 묶음 표가 담당**하며,
        여기서 빠지는 것이 정상이다.

        Given: 유효 2행(보유 4·5일)과 제외 1행
        When: 길이별로 바꾸면
        Then: 제외행이 빠지고 구간 축이 보유일수가 된다
        """
        # Given
        frame = pd.DataFrame(
            {
                COL_HOLD_DAYS: pd.array([4, 5, None], dtype="Int64"),
                COL_HORIZON: [HORIZON_NEXT_WEEK_EXIT] * 3,
                COL_EXCLUDED_REASON: [REASON_NONE, REASON_NONE, REASON_OUT_OF_RANGE],
            }
        )

        # When
        result = _per_length(frame)

        # Then
        assert len(result) == 2
        assert result[COL_HORIZON].tolist() == [4, 5]

    def test_만기월_축은_같은_달_베이스라인을_달고_나온다(self) -> None:
        """
        목적: **9월 약세가 만기 효과인지 그 달의 계절성인지 가를 수 있어야 한다**를 고정한다
        (`docs/매매/옵션_만기일/설계.md` 결정 ㉓)

        같은 달 베이스라인 없이 월별 값만 내면 두 설명을 구별할 수 없다.

        Given: 3월·9월에 신호가 있고 베이스라인은 전 월에 걸친 입력
        When: 만기월 축으로 집계하면
        Then: 신호가 있는 달만 나오고 각 행에 베이스라인 통계와 초과분이 함께 있다
        """
        # Given
        signal = _long_form(["2026-03-20", "2026-09-18"], [0.02, -0.01])
        baseline = _long_form(
            ["2026-03-06", "2026-03-13", "2026-09-04", "2026-09-11", "2026-05-08"],
            [0.01, 0.00, 0.00, 0.01, 0.05],
        )

        # When
        result = _aggregate_by_month(signal, baseline, repeats=10, seed=0)

        # Then
        assert result[COL_EXPIRY_MONTH_NUMBER].tolist() == [3, 9], "신호가 없는 5월이 섞였습니다"
        assert f"{COL_MEAN}_baseline" in result.columns, "같은 달 베이스라인이 빠졌습니다"
        assert COL_MEAN_P_VALUE in result.columns, "만기월 칸에 검정이 빠졌습니다"
        march = result[result[COL_EXPIRY_MONTH_NUMBER] == 3].iloc[0]
        assert float(march[COL_MEAN]) == pytest.approx(0.02, abs=EXACT_TOLERANCE)
        assert float(march[f"{COL_MEAN}_baseline"]) == pytest.approx(0.005, abs=EXACT_TOLERANCE)
        assert float(march["MeanExcess"]) == pytest.approx(0.015, abs=EXACT_TOLERANCE)

    def test_만기월_축에_두_방향_비율과_각각의_우연확률이_붙는다(self) -> None:
        """
        목적: **아래로 치우친 달을 잡으려면 비율 축이 있어야 한다**를 고정한다
        (루트 `CLAUDE.md` 측정의 원칙 11).

        평균만 검정하면 "대부분의 해가 내렸는데 소수의 큰 상승이 평균을 올린" 달을 놓친다.

        Given: 9월 신호 12건 중 9건이 내린 입력
        When: 만기월 축으로 집계하면
        Then: 두 방향 비율과 그 차이·우연확률이 모두 붙어 나온다
        """
        # Given
        dates = [f"2026-09-{day:02d}" for day in range(1, 13)]
        signal = _long_form(dates, [-0.01] * 9 + [0.02] * 3)
        baseline = _long_form([f"2026-09-{day:02d}" for day in range(13, 28)], [0.01] * 8 + [-0.01] * 7)

        # When
        result = _aggregate_by_month(signal, baseline, repeats=50, seed=0)

        # Then
        row = result.iloc[0]
        assert float(row[COL_WIN_RATE]) == pytest.approx(3 / 12, abs=EXACT_TOLERANCE)
        assert float(row[COL_LOSS_RATE]) == pytest.approx(9 / 12, abs=EXACT_TOLERANCE)
        for column in (COL_LOSS_RATE_EXCESS, COL_UP_RATE_P_VALUE, COL_DOWN_RATE_P_VALUE):
            assert column in result.columns, f"{column} 이 만기월 축에서 빠졌습니다"

    def test_평균과_방향_비율이_어긋나는_칸에_표시가_남는다(self) -> None:
        """
        목적: **평균이 양수인데 절반 넘게 내린 칸을 표시한다** (측정의 원칙 13).

        실물 사례가 SPY 3월 만기다 — 평균은 양수인데 3분의 2가 내렸고,
        평균만 보고 "오르는 달"로 기각했던 칸이다.

        Given: 큰 상승 2건이 평균을 양수로 만들지만 12건 중 10건이 내린 9월 신호
        When: 만기월 축으로 집계하면
        Then: 어긋남 표시가 True 다
        """
        # Given
        dates = [f"2026-09-{day:02d}" for day in range(1, 13)]
        signal = _long_form(dates, [0.50, 0.45] + [-0.02] * 10)
        baseline = _long_form([f"2026-09-{day:02d}" for day in range(13, 28)], [0.01] * 8 + [-0.01] * 7)

        # When
        result = _aggregate_by_month(signal, baseline, repeats=50, seed=0)

        # Then
        row = result.iloc[0]
        assert float(row[COL_MEAN]) > 0
        assert float(row[COL_LOSS_RATE]) > 0.5
        assert bool(row[COL_MEAN_RATE_CONFLICT]) is True

    def test_평균과_방향_비율이_같은_쪽이면_표시가_없다(self) -> None:
        """
        목적: 어긋남 표시가 **아무 칸에나 붙지 않는다**를 고정한다.

        Given: 평균이 음수이고 대부분 내린 9월 신호 (두 축이 같은 쪽을 가리킨다)
        When: 만기월 축으로 집계하면
        Then: 어긋남 표시가 False 다
        """
        # Given
        dates = [f"2026-09-{day:02d}" for day in range(1, 13)]
        signal = _long_form(dates, [-0.02] * 10 + [0.01] * 2)
        baseline = _long_form([f"2026-09-{day:02d}" for day in range(13, 28)], [0.01] * 8 + [-0.01] * 7)

        # When
        result = _aggregate_by_month(signal, baseline, repeats=50, seed=0)

        # Then
        row = result.iloc[0]
        assert float(row[COL_MEAN]) < 0
        assert bool(row[COL_MEAN_RATE_CONFLICT]) is False


def _long_form(dates: Sequence[str], returns: Sequence[float]) -> pd.DataFrame:
    """만기월 집계가 요구하는 최소 long-form 을 만든다."""
    return pd.DataFrame(
        {
            COL_DATE: pd.to_datetime(list(dates)),
            COL_BASIS: ["close"] * len(dates),
            COL_HORIZON: [HORIZON_NEXT_WEEK_EXIT] * len(dates),
            COL_FORWARD_RETURN: list(returns),
            COL_EXCLUDED_REASON: [REASON_NONE] * len(dates),
        }
    )


class TestMeasureTableAssembly:
    """`측정.csv` — 확정 칸의 «해석 재료»를 한 장에 담는다 (2026-09-21)

    성적표가 「걸 만한가」에 답한다면 이 표는 **「그 값을 어떻게 읽나」**에 답한다.
    중앙값(측정의 원칙 4) · 평균-비율 어긋남(원칙 13) · 기준선 · 우연확률 · 배당락이
    그것이며, **성적표에는 그중 어느 것도 없다.**

    [중요] **값은 1배 롱 기준 그대로 둔다.** 「아래」 칸이라고 부호를 뒤집지 않는다 —
    뒤집으면 `기준선 오른 비율` 이 실제로는 내린 비율을 가리켜 **이름이 거짓이 된다.**
    `방향` 컬럼은 「어느 쪽으로 거는가」를 표시만 하고, 읽는 법은 문서가 적는다.
    그래서 **성적표의 평균과 이 표의 평균은 부호가 다를 수 있다** — 대조 대상이 아니다.
    """

    def test_확정_칸만_내고_식별_컬럼_셋이_앞에_온다(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        목적: **코드가 격자를 훑지 않고 확정 칸만 낸다**는 것을 고정한다 (2026-09-21 사용자 확정).

        전에는 대상 × 만기월 12 × 방향 2 를 전부 냈고, 사용자가 실제로 거는 것은 3칸이었다.
        **칸을 줄이는 근거는 코드가 아니라 `docs/매매/옵션_만기일/규칙.md` §1 이 갖는다** —
        코드는 그 목록을 받아 돌 뿐이다.

        식별 컬럼이 빠진 표는 **예외 없이 정상으로 보이면서 해석이 불가능해진다**
        (이 모듈 머리말). 방향이 없으면 같은 종목·같은 달의 두 행을 구별할 수 없다.

        Given: 합성 시세와 확정 칸 둘
        When: 측정을 돌렸을 때
        Then: 칸마다 한 행이고 종목·만기월·방향이 앞에 온다
        """
        # Given
        from verify_lab.measure.screening import COL_DIRECTION
        from verify_lab.studies.option_expiry import runner as expiry_runner
        from verify_lab.studies.option_expiry.constants import ExpiryCell

        rng = np.random.default_rng(20260921)
        closes = 100.0 * np.cumprod(1.0 + rng.normal(0.0004, 0.008, 520))
        market = _market(closes.tolist(), start="2024-01-02")
        market.to_csv(tmp_path / "SYN_max.csv", index=False)
        # 배당락을 재려면 수정주가가 있어야 한다 — 없으면 실행이 거부된다(아래 테스트)
        market.to_csv(tmp_path / "SYN_adjusted_max.csv", index=False)

        dataset = Dataset(
            key="synthetic",
            ticker="SYN",
            label="합성",
            rule=US_MONTHLY_EXPIRY,
            file_name="SYN_max.csv",
            price_decimals=4,
        )
        cells = (
            ExpiryCell(dataset_key="synthetic", expiry_month=9, bet_down=True),
            ExpiryCell(dataset_key="synthetic", expiry_month=12, bet_down=False),
        )
        monkeypatch.setattr(expiry_runner, "MARKET_DIR", tmp_path)

        # When
        outputs = expiry_runner.run_study((dataset,), cells=cells, repeats=10, seed=0)

        # Then
        columns = list(outputs.measure.columns)
        assert columns[:3] == [COL_TICKER, COL_EXPIRY_MONTH_NUMBER, COL_DIRECTION]
        assert len(outputs.measure) == len(cells), "확정 칸 밖의 달이 섞였습니다"
        assert outputs.measure[COL_EXPIRY_MONTH_NUMBER].tolist() == [9, 12]

    def test_배당락_두_컬럼이_함께_온다(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        목적: **배당락을 매번 별도 스크립트로 재던 것을 산출물에 넣는다**는 결정을 고정한다.

        `.claude/rules/trading.md` 가 배당·분배락을 **「확정 전 필수 항목」**으로 요구하는데
        그 값이 어느 산출물에도 없어서, 칸을 뺄지 판단할 때마다 스크립트를 따로 돌려야 했다.

        **「못 잰 것」을 0 으로 세지 않으려면 건수가 함께 있어야 한다** — 걸린 건수가 0 인 것과
        수정주가가 없어 못 잰 것은 다른 사실이다.

        Given: 합성 시세와 수정주가 (배당락 없음)
        When: 측정을 돌렸을 때
        Then: 걸린 건수와 평균 왜곡이 표에 있다
        """
        # Given
        from verify_lab.studies.option_expiry import runner as expiry_runner
        from verify_lab.studies.option_expiry.constants import (
            COL_DIVIDEND_HIT_COUNT,
            COL_DIVIDEND_MEAN_IMPACT,
            ExpiryCell,
        )

        rng = np.random.default_rng(20260921)
        closes = 100.0 * np.cumprod(1.0 + rng.normal(0.0004, 0.008, 520))
        market = _market(closes.tolist(), start="2024-01-02")
        market.to_csv(tmp_path / "SYN_max.csv", index=False)
        # 배당락이 없는 대상이라 두 계열이 같다 — 「0건 확인」이 나와야 한다
        market.to_csv(tmp_path / "SYN_adjusted_max.csv", index=False)

        dataset = Dataset(
            key="synthetic",
            ticker="SYN",
            label="합성",
            rule=US_MONTHLY_EXPIRY,
            file_name="SYN_max.csv",
            price_decimals=4,
        )
        cells = (ExpiryCell(dataset_key="synthetic", expiry_month=9, bet_down=True),)
        monkeypatch.setattr(expiry_runner, "MARKET_DIR", tmp_path)

        # When
        outputs = expiry_runner.run_study((dataset,), cells=cells, repeats=10, seed=0)

        # Then
        row = outputs.measure.iloc[0]
        assert int(row[COL_DIVIDEND_HIT_COUNT]) == 0
        assert float(row[COL_DIVIDEND_MEAN_IMPACT]) == pytest.approx(0.0, abs=1e-9)
