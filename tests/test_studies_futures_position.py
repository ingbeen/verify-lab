"""레버리지 포지션 엔진의 계약

**선물에는 배수가 없으므로 이 계층이 배수를 만든다.** 여기가 틀리면 「선물이 싸다/비싸다」가
통째로 뒤집히므로, 손으로 계산한 값을 박아 산식을 고정한다.

고정하는 것은 넷이다.

1. **`배수 1` · 매일 리밸런싱이면 자기자본 곡선이 가격 수익률과 정확히 같다** — 산식의 바닥
2. **매일 리밸런싱에서 유효 배수가 목표값과 항상 같다** — 배수의 정의
3. **월 1회에서 월중 표류가 실제로 관측된다** — 0 이면 리밸런싱 규칙이 동작하지 않는 것이다
4. **자기자본이 0 이하가 되면 그 시점에 끝나고 기록된다** — 강제청산을 모델링하지 않으므로
   그 뒤를 이어 붙이면 존재할 수 없는 경로가 된다

합성 데이터만 쓴다.
"""

import pandas as pd
import pytest

from verify_lab.common_constants import COL_DATE
from verify_lab.studies.futures_leverage.constants import (
    REBALANCE_DAILY,
    REBALANCE_INTERVAL_DAYS,
    REBALANCE_MONTHLY,
)
from verify_lab.studies.futures_leverage.position import (
    COL_EFFECTIVE_LEVERAGE,
    COL_EQUITY,
    COL_REBALANCED,
    run_position,
)

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-9

PRICE_COLUMN = "Price"
START_EQUITY = 100.0


def _prices(values: list[float], start: str = "2020-01-01", freq: str = "B") -> pd.DataFrame:
    """합성 가격 계열을 만든다.

    Args:
        values: 가격 목록
        start: 첫 거래일
        freq: 날짜 간격

    Returns:
        `Date` 와 `Price` 를 갖는 DataFrame
    """
    return pd.DataFrame({COL_DATE: pd.bdate_range(start, periods=len(values), freq=freq), PRICE_COLUMN: values})


class TestFormula:
    """산식 고정 — 손계산으로 값을 박는다."""

    def test_single_multiple_daily_matches_price_return(self) -> None:
        """
        목적: **배수 1 · 매일 리밸런싱이면 자기자본이 가격과 똑같이 움직임**을 고정한다.

        이것이 산식의 바닥이다. 여기가 어긋나면 나머지 배수는 볼 것도 없다.

        Given: 100 → 110 → 99 로 움직이는 가격
        When: 배수 1 로 매일 리밸런싱한다
        Then: 자기자본 비율이 가격 비율과 같다
        """
        # Given
        prices = _prices([100.0, 110.0, 99.0])

        # When
        result = run_position(prices, 1.0, REBALANCE_DAILY, price_column=PRICE_COLUMN, initial_equity=START_EQUITY)

        # Then
        expected = [START_EQUITY * value / 100.0 for value in (100.0, 110.0, 99.0)]
        assert result.curve[COL_EQUITY].tolist() == pytest.approx(expected, abs=EXACT_TOLERANCE)

    def test_double_multiple_daily_compounds_by_hand(self) -> None:
        """
        목적: 배수 2 매일 리밸런싱의 자기자본을 손계산 값으로 박는다.

        `E1 = 100`, 가격 +10% → `E2 = 100 × (1 + 2×0.10) = 120`,
        가격 −10% → `E3 = 120 × (1 + 2×(−0.10)) = 96`.
        **단순 배수 기대치(100 × (1 + 2×(−0.01)) = 98)와 다르다** — 이 차이가 경로 효과다.

        Given: 100 → 110 → 99 로 움직이는 가격
        When: 배수 2 로 매일 리밸런싱한다
        Then: 자기자본이 100 → 120 → 96 이다
        """
        # Given
        prices = _prices([100.0, 110.0, 99.0])

        # When
        result = run_position(prices, 2.0, REBALANCE_DAILY, price_column=PRICE_COLUMN, initial_equity=START_EQUITY)

        # Then
        assert result.curve[COL_EQUITY].tolist() == pytest.approx([100.0, 120.0, 96.0], abs=EXACT_TOLERANCE)

    def test_inverse_multiple_moves_opposite(self) -> None:
        """
        목적: 인버스가 반대로 움직임을 고정한다.

        `E1 = 100`, 가격 +10% → `E2 = 100 × (1 − 1×0.10) = 90`.

        Given: 100 → 110 으로 오르는 가격
        When: 배수 −1 로 매일 리밸런싱한다
        Then: 자기자본이 90 이 된다
        """
        # Given
        prices = _prices([100.0, 110.0])

        # When
        result = run_position(prices, -1.0, REBALANCE_DAILY, price_column=PRICE_COLUMN, initial_equity=START_EQUITY)

        # Then
        assert result.curve[COL_EQUITY].iloc[-1] == pytest.approx(90.0, abs=EXACT_TOLERANCE)

    def test_contract_multiplier_does_not_change_equity(self) -> None:
        """
        목적: **거래승수가 소수 계약 손익을 바꾸지 않음**을 고정한다.

        계약 수는 승수로 나누고 손익은 승수로 곱하므로 서로 지워진다. 승수가 결과를 바꾼다면
        어딘가에서 한 번만 곱해진 것이다.

        Given: 같은 가격 계열
        When: 승수 1 과 250,000 으로 각각 굴린다
        Then: 자기자본 곡선이 같다
        """
        # Given
        prices = _prices([100.0, 110.0, 99.0])

        # When
        plain = run_position(prices, 2.0, REBALANCE_DAILY, price_column=PRICE_COLUMN, initial_equity=START_EQUITY)
        scaled = run_position(
            prices,
            2.0,
            REBALANCE_DAILY,
            price_column=PRICE_COLUMN,
            initial_equity=START_EQUITY,
            contract_multiplier=250_000,
        )

        # Then
        assert scaled.curve[COL_EQUITY].tolist() == pytest.approx(plain.curve[COL_EQUITY].tolist(), abs=EXACT_TOLERANCE)


class TestRebalancing:
    """리밸런싱 규칙의 계약 — 규칙이 곧 배수의 정의다."""

    def test_daily_holds_the_target_multiple_every_day(self) -> None:
        """
        목적: 매일 리밸런싱에서 유효 배수가 목표값과 항상 같음을 고정한다.

        Given: 오르내리는 가격
        When: 배수 2 로 매일 리밸런싱한다
        Then: 모든 날의 유효 배수가 2 다
        """
        # Given
        prices = _prices([100.0, 110.0, 99.0, 105.0, 95.0])

        # When
        result = run_position(prices, 2.0, REBALANCE_DAILY, price_column=PRICE_COLUMN, initial_equity=START_EQUITY)

        # Then
        assert result.curve[COL_EFFECTIVE_LEVERAGE].tolist() == pytest.approx([2.0] * len(prices), abs=EXACT_TOLERANCE)
        assert result.max_effective_leverage == pytest.approx(2.0, abs=EXACT_TOLERANCE)

    def test_monthly_drifts_within_the_month(self) -> None:
        """
        목적: **월 1회 리밸런싱에서 월중 배수 표류가 실제로 관측**됨을 고정한다.

        표류가 0 이면 규칙이 동작하지 않는 것이고, 두 규칙을 비교하는 뜻이 사라진다.
        가격이 내리면 자기자본이 더 크게 줄어 **유효 배수가 목표보다 커진다** — 위험이 커지는 쪽이다.

        Given: 한 달 안에서 계속 내리는 가격
        When: 배수 2 로 월 1회 리밸런싱한다
        Then: 첫날은 2 이고 이후 2 보다 커진다
        """
        # Given
        prices = _prices([100.0, 95.0, 90.0, 85.0])

        # When
        result = run_position(prices, 2.0, REBALANCE_MONTHLY, price_column=PRICE_COLUMN, initial_equity=START_EQUITY)

        # Then
        leverage = result.curve[COL_EFFECTIVE_LEVERAGE].tolist()
        assert leverage[0] == pytest.approx(2.0, abs=EXACT_TOLERANCE)
        assert all(later > 2.0 for later in leverage[1:]), f"월중 표류가 관측되지 않습니다: {leverage}"
        assert result.max_effective_leverage > 2.0

    def test_monthly_rebalances_on_a_fixed_interval_from_entry(self) -> None:
        """
        목적: 월 1회 리밸런싱이 **진입일로부터 고정 간격**으로 일어남을 고정한다.

        달력(매월 첫 거래일)에 맞추면 리밸런싱 시점이 월중 위치에 묶여, 짧은 칸에서
        「진입일이 월중 어디냐」가 결과를 만든다.

        Given: 간격의 두 배가 조금 넘는 길이의 가격 계열
        When: 월 1회로 굴린다
        Then: 진입일과 그로부터 간격마다에만 리밸런싱한다
        """
        # Given
        length = REBALANCE_INTERVAL_DAYS * 2 + 3
        prices = _prices([100.0 + index for index in range(length)])

        # When
        result = run_position(prices, 2.0, REBALANCE_MONTHLY, price_column=PRICE_COLUMN, initial_equity=START_EQUITY)

        # Then
        expected_days = [0, REBALANCE_INTERVAL_DAYS, REBALANCE_INTERVAL_DAYS * 2]
        actual_days = result.curve.index[result.curve[COL_REBALANCED]].tolist()
        assert actual_days == expected_days
        assert result.rebalance_count == 3

    def test_rebalance_count_depends_only_on_horizon(self) -> None:
        """
        목적: **리밸런싱 횟수가 진입일이 아니라 구간 길이로만 정해짐**을 고정한다.

        이것이 달력 앵커를 버린 이유다. 달력에 묶여 있으면 같은 길이의 구간이라도
        월중 어디서 시작했느냐에 따라 리밸런싱 횟수가 달라져, 재려는 것이 아닌 축이 섞인다.

        Given: 시작일만 다르고 길이가 같은 두 구간
        When: 각각 월 1회로 굴린다
        Then: 리밸런싱 횟수가 같다
        """
        # Given
        length = REBALANCE_INTERVAL_DAYS + 5
        values = [100.0 + index for index in range(length)]
        early = _prices(values, start="2020-01-02")
        late = _prices(values, start="2020-01-30")

        # When
        early_result = run_position(early, 2.0, REBALANCE_MONTHLY, price_column=PRICE_COLUMN)
        late_result = run_position(late, 2.0, REBALANCE_MONTHLY, price_column=PRICE_COLUMN)

        # Then
        assert early_result.rebalance_count == late_result.rebalance_count == 2

    def test_short_window_never_rebalances_after_entry(self) -> None:
        """
        목적: 간격보다 짧은 구간은 진입 한 번만 리밸런싱함을 고정한다.

        5거래일 구간에서 「월 1회」는 사실상 무리밸런싱이며, **그것이 진입일과 무관하게
        일정해야** 그 칸의 숫자를 읽을 수 있다.

        Given: 5거래일짜리 구간
        When: 월 1회로 굴린다
        Then: 진입일에만 리밸런싱한다
        """
        # Given
        prices = _prices([100.0, 101.0, 102.0, 103.0, 104.0])

        # When
        result = run_position(prices, 2.0, REBALANCE_MONTHLY, price_column=PRICE_COLUMN)

        # Then
        assert result.rebalance_count == 1
        assert result.curve[COL_REBALANCED].tolist() == [True, False, False, False, False]

    def test_unknown_rule_raises(self) -> None:
        """
        목적: 모르는 리밸런싱 규칙으로 조용히 계산하지 않음을 고정한다.

        Given: 목록에 없는 규칙 이름
        When: 포지션을 굴린다
        Then: ValueError 를 던진다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="모르는 리밸런싱 규칙입니다"):
            run_position(_prices([100.0, 101.0]), 2.0, "분기 1회", price_column=PRICE_COLUMN)


class TestWipeout:
    """자기자본 소진의 계약 — 강제청산을 모델링하지 않으므로 여기서 끊는다."""

    def test_position_stops_when_equity_is_wiped_out(self) -> None:
        """
        목적: 자기자본이 0 이하가 되면 **그 시점에 끝나고 기록**됨을 고정한다.

        이어 붙이면 실제로 존재할 수 없는 경로(음수 자기자본으로 계속 굴리는 것)가 된다.

        Given: 배수 2 에서 하루에 −60% 나는 가격
        When: 월 1회로 굴린다
        Then: 그날 끝나고 소진일과 소요 거래일이 기록된다
        """
        # Given
        prices = _prices([100.0, 40.0, 45.0, 50.0])

        # When
        result = run_position(prices, 2.0, REBALANCE_MONTHLY, price_column=PRICE_COLUMN, initial_equity=START_EQUITY)

        # Then
        assert result.wipeout_date == prices[COL_DATE].iloc[1]
        assert result.days_to_wipeout == 1
        assert len(result.curve) == 2, "소진 이후 행이 이어지면 안 됩니다"
        assert result.final_equity == pytest.approx(0.0, abs=EXACT_TOLERANCE)

    def test_surviving_position_records_no_wipeout(self) -> None:
        """
        목적: 끝까지 살아남으면 소진 기록이 비어 있음을 고정한다.

        Given: 완만하게 움직이는 가격
        When: 배수 2 로 굴린다
        Then: 소진일과 소요 거래일이 None 이다
        """
        # Given
        prices = _prices([100.0, 101.0, 100.0])

        # When
        result = run_position(prices, 2.0, REBALANCE_DAILY, price_column=PRICE_COLUMN, initial_equity=START_EQUITY)

        # Then
        assert result.wipeout_date is None
        assert result.days_to_wipeout is None


class TestInterest:
    """여유현금 이자의 계약 — 자기자본 전액이 계좌 담보다."""

    def test_interest_accrues_on_calendar_days(self) -> None:
        """
        목적: 이자가 **직전 거래일부터의 달력일 수**만큼 붙음을 고정한다.

        거래일로 나누면 주말·연휴가 긴 구간에서 이자가 덜 붙는다.
        연 3.65% 라면 하루치가 정확히 0.01% 다.

        Given: 가격이 변하지 않고 하루 간격인 계열, 연 3.65% 금리
        When: 배수 1 로 굴린다
        Then: 둘째 날 자기자본이 100 × 1.0001 이다
        """
        # Given
        dates = pd.to_datetime(["2020-01-02", "2020-01-03"])
        prices = pd.DataFrame({COL_DATE: dates, PRICE_COLUMN: [100.0, 100.0]})
        interest = pd.Series([3.65, 3.65], index=dates)

        # When
        result = run_position(
            prices, 1.0, REBALANCE_DAILY, price_column=PRICE_COLUMN, interest=interest, initial_equity=START_EQUITY
        )

        # Then
        assert result.curve[COL_EQUITY].iloc[-1] == pytest.approx(100.0 * 1.0001, abs=EXACT_TOLERANCE)
        assert result.with_interest is True

    def test_weekend_gap_accrues_three_days(self) -> None:
        """
        목적: 주말이 끼면 사흘치 이자가 붙음을 고정한다.

        Given: 금요일과 월요일 (달력일 3일 차이), 연 3.65% 금리
        When: 배수 1 로 굴린다
        Then: 하루치의 세 배가 붙는다
        """
        # Given
        dates = pd.to_datetime(["2020-01-03", "2020-01-06"])
        prices = pd.DataFrame({COL_DATE: dates, PRICE_COLUMN: [100.0, 100.0]})
        interest = pd.Series([3.65, 3.65], index=dates)

        # When
        result = run_position(
            prices, 1.0, REBALANCE_DAILY, price_column=PRICE_COLUMN, interest=interest, initial_equity=START_EQUITY
        )

        # Then
        assert result.curve[COL_EQUITY].iloc[-1] == pytest.approx(100.0 * 1.0003, abs=EXACT_TOLERANCE)

    def test_without_interest_nothing_accrues(self) -> None:
        """
        목적: 이자 없음 가정에서 아무것도 붙지 않음을 고정한다.

        두 벌을 나란히 내는 것이 목적이므로 차이가 이자 하나여야 한다.

        Given: 가격이 변하지 않는 계열
        When: 이자 없이 굴린다
        Then: 자기자본이 그대로다
        """
        # Given
        prices = _prices([100.0, 100.0, 100.0])

        # When
        result = run_position(prices, 2.0, REBALANCE_DAILY, price_column=PRICE_COLUMN, initial_equity=START_EQUITY)

        # Then
        assert result.curve[COL_EQUITY].tolist() == pytest.approx([START_EQUITY] * 3, abs=EXACT_TOLERANCE)
        assert result.with_interest is False


class TestInputValidation:
    """입력 검증 — 잘못된 값으로 조용히 계산하지 않는다."""

    def test_empty_prices_raises(self) -> None:
        """
        목적: 빈 가격 계열을 막음을 고정한다.

        Given: 빈 DataFrame
        When: 포지션을 굴린다
        Then: ValueError 를 던진다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="가격 계열이 비어 있습니다"):
            run_position(
                pd.DataFrame({COL_DATE: [], PRICE_COLUMN: []}), 2.0, REBALANCE_DAILY, price_column=PRICE_COLUMN
            )

    def test_non_positive_initial_equity_raises(self) -> None:
        """
        목적: 0 이하 초기 자기자본을 막음을 고정한다.

        Given: 초기 자기자본 0
        When: 포지션을 굴린다
        Then: ValueError 를 던진다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="초기 자기자본은 0보다 커야 합니다"):
            run_position(_prices([100.0]), 2.0, REBALANCE_DAILY, price_column=PRICE_COLUMN, initial_equity=0)

    def test_missing_price_column_raises(self) -> None:
        """
        목적: 없는 컬럼을 가격으로 지정하면 막힘을 고정한다.

        Given: 존재하지 않는 컬럼 이름
        When: 포지션을 굴린다
        Then: ValueError 를 던진다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="가격 컬럼이 없습니다"):
            run_position(_prices([100.0]), 2.0, REBALANCE_DAILY, price_column="없는컬럼")

    def test_non_positive_price_raises(self) -> None:
        """
        목적: 0 이하 가격으로 계약 수를 계산하지 않음을 고정한다.

        Given: 가격이 0 인 행
        When: 포지션을 굴린다
        Then: ValueError 를 던진다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="가격이 0 이하입니다"):
            run_position(_prices([100.0, 0.0]), 2.0, REBALANCE_DAILY, price_column=PRICE_COLUMN)
