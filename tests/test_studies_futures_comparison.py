"""구간 수익률과 차이 분해의 계약

이 계층은 **포지션 엔진을 벡터화해 다시 구현한 것**이다. 롤링 전수 구간을 엔진으로 하나씩
돌리면 2억 회가 넘는 반복이 되기 때문인데, 그 대가로 **같은 판정이 두 곳에 생긴다.**
그래서 가장 중요한 테스트는 **둘이 정확히 같은 값을 내는지**다 (절대 원칙 5 판정식 단일화).

분해 쪽에서 고정하는 것은 **잔여가 나머지로 정의되지 않았다**는 것이다.
`잔여 = 차이 − 나머지` 로 두면 항등식이 정의상 성립해 아무것도 검증하지 못한다.
"""

import numpy as np
import pandas as pd
import pytest

from verify_lab.common_constants import COL_DATE
from verify_lab.measure.constants import COL_EXCLUDED_REASON, REASON_NONE, REASON_OUT_OF_RANGE
from verify_lab.studies.futures_leverage.comparison import (
    build_interest_factor,
    build_window_table,
    decompose,
    horizons_or_default,
    leveraged_window_returns,
    plain_window_returns,
)
from verify_lab.studies.futures_leverage.constants import (
    HOLDING_HORIZONS,
    REBALANCE_DAILY,
    REBALANCE_INTERVAL_DAYS,
    REBALANCE_MONTHLY,
)
from verify_lab.studies.futures_leverage.position import run_position

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12

PRICE_COLUMN = "Price"


def _wandering_prices(count: int) -> np.ndarray:
    """오르내리는 합성 가격을 만든다.

    한 방향으로만 가면 경로 효과가 드러나지 않아 두 구현의 차이를 잡지 못한다.

    Args:
        count: 거래일 수

    Returns:
        가격 배열
    """
    steps = np.sin(np.arange(count) / 3.0) * 0.02 + np.cos(np.arange(count) / 7.0) * 0.01
    return 100.0 * np.cumprod(1.0 + steps)


def _frame(prices: np.ndarray) -> pd.DataFrame:
    """가격 배열을 엔진 입력 형태로 바꾼다."""
    return pd.DataFrame({COL_DATE: pd.bdate_range("2020-01-01", periods=len(prices)), PRICE_COLUMN: prices})


class TestEngineAgreement:
    """**두 구현이 같은 값을 내는가** — 이 계층에서 가장 중요한 계약."""

    @pytest.mark.parametrize("rule", [REBALANCE_DAILY, REBALANCE_MONTHLY])
    @pytest.mark.parametrize("multiple", [2.0, -1.0, -2.0, 3.0])
    def test_matches_position_engine(self, rule: str, multiple: float) -> None:
        """
        목적: 벡터화한 구간 수익률이 **포지션 엔진과 정확히 같음**을 고정한다.

        벡터화는 속도 때문에 판정을 두 곳에 둔 것이므로, 둘이 갈리면 어느 쪽이 맞는지
        알 수 없게 된다.

        Given: 오르내리는 가격과 여러 배수·리밸런싱 규칙
        When: 벡터화 경로와 엔진으로 각각 구간 수익률을 낸다
        Then: 모든 시작일에서 값이 같다
        """
        # Given
        prices = _wandering_prices(70)
        horizon = 50

        # When
        vectorized, _ = leveraged_window_returns(prices, multiple, horizon, rule)

        expected: list[float] = []
        for start in range(len(prices) - horizon):
            window = _frame(prices[start : start + horizon + 1])
            result = run_position(window, multiple, rule, price_column=PRICE_COLUMN, initial_equity=1.0)
            expected.append(result.final_equity - 1.0)

        # Then
        assert vectorized[: len(expected)].tolist() == pytest.approx(expected, abs=EXACT_TOLERANCE)

    @pytest.mark.parametrize("rule", [REBALANCE_DAILY, REBALANCE_MONTHLY])
    def test_matches_position_engine_with_interest(self, rule: str) -> None:
        """
        목적: 이자를 붙여도 두 구현이 같은 값을 냄을 고정한다.

        이자를 매일 손익에 섞으면 구간 수익률이 곱으로 분해되지 않아 벡터화가 불가능하다.
        그래서 엔진과 벡터화가 **같은 분리 규약**을 쓰는지가 여기서 갈린다.

        Given: 오르내리는 가격과 연 3.65% 금리
        When: 벡터화 경로와 엔진으로 각각 구간 수익률을 낸다
        Then: 모든 시작일에서 값이 같다
        """
        # Given
        prices = _wandering_prices(70)
        horizon = 50
        frame = _frame(prices)
        interest = pd.Series(3.65, index=frame[COL_DATE])

        # When
        factor = build_interest_factor(frame[COL_DATE], interest)
        vectorized, _ = leveraged_window_returns(prices, 2.0, horizon, rule, interest_factor=factor)

        expected: list[float] = []
        for start in range(len(prices) - horizon):
            window = frame.iloc[start : start + horizon + 1].reset_index(drop=True)
            result = run_position(window, 2.0, rule, price_column=PRICE_COLUMN, interest=interest, initial_equity=1.0)
            expected.append(result.final_equity - 1.0)

        # Then
        assert vectorized[: len(expected)].tolist() == pytest.approx(expected, abs=EXACT_TOLERANCE)


class TestWindowReturns:
    """구간 수익률의 계약."""

    def test_plain_window_return_is_the_simple_ratio(self) -> None:
        """
        목적: 단순 구간 수익률이 검증 #8 과 같은 산식임을 고정한다.

        같은 원본가 파일을 읽으므로 같은 (종목, 시작일, 구간) 에서 값이 같아야 한다.

        Given: 100 → 110 → 121 로 오르는 가격
        When: 구간 2 의 단순 수익률을 낸다
        Then: 첫날이 0.21 이다
        """
        # Given
        prices = np.array([100.0, 110.0, 121.0])

        # When
        result = plain_window_returns(prices, 2)

        # Then
        assert result[0] == pytest.approx(0.21, abs=EXACT_TOLERANCE)
        assert np.isnan(result[1]) and np.isnan(result[2])

    def test_daily_rebalancing_compounds_the_multiple(self) -> None:
        """
        목적: 매일 리밸런싱 구간 수익률을 손계산 값으로 박는다.

        `(1 + 2×0.10) × (1 + 2×(−0.10)) − 1 = 1.2 × 0.8 − 1 = −0.04`.
        **단순 배수 기대치(2 × (−0.01) = −0.02)와 다르다** — 이 차이가 경로 효과다.

        Given: 100 → 110 → 99 로 움직이는 가격
        When: 배수 2 매일 리밸런싱으로 구간 2 의 수익률을 낸다
        Then: −0.04 이다
        """
        # Given
        prices = np.array([100.0, 110.0, 99.0])

        # When
        result, _ = leveraged_window_returns(prices, 2.0, 2, REBALANCE_DAILY)

        # Then
        assert result[0] == pytest.approx(-0.04, abs=EXACT_TOLERANCE)

    def test_short_window_monthly_never_rebalances(self) -> None:
        """
        목적: 간격보다 짧은 구간에서 월 1회가 **단일 조각**임을 고정한다.

        5거래일 구간의 「월 1회」는 진입 한 번뿐이므로
        `1 + 배수 × 구간수익률` 이 되어야 한다 — 매일 리밸런싱과 다른 값이다.

        Given: 100 → 110 → 99 로 움직이는 가격
        When: 배수 2 월 1회로 구간 2 의 수익률을 낸다
        Then: `2 × (99/100 − 1) = −0.02` 다
        """
        # Given
        prices = np.array([100.0, 110.0, 99.0])

        # When
        result, _ = leveraged_window_returns(prices, 2.0, 2, REBALANCE_MONTHLY)

        # Then
        assert result[0] == pytest.approx(-0.02, abs=EXACT_TOLERANCE)

    def test_two_rules_differ_beyond_the_interval(self) -> None:
        """
        목적: 간격을 넘는 구간에서 두 규칙이 실제로 갈림을 고정한다.

        같은 값이 나오면 두 벌을 내는 뜻이 없다.

        Given: 오르내리는 가격
        When: 간격의 두 배 길이 구간을 두 규칙으로 낸다
        Then: 값이 다르다
        """
        # Given
        prices = _wandering_prices(60)
        horizon = REBALANCE_INTERVAL_DAYS * 2

        # When
        daily, _ = leveraged_window_returns(prices, 2.0, horizon, REBALANCE_DAILY)
        monthly, _ = leveraged_window_returns(prices, 2.0, horizon, REBALANCE_MONTHLY)

        # Then
        assert not np.allclose(daily[:5], monthly[:5])

    def test_out_of_range_starts_are_nan(self) -> None:
        """
        목적: 구간 끝이 데이터를 넘어가는 시작일이 NaN 임을 고정한다 (0 으로 채우지 않는다).

        0 으로 채우면 「손실도 이익도 없었다」로 읽힌다 (측정의 원칙 17).

        Given: 5행짜리 가격
        When: 구간 3 의 수익률을 낸다
        Then: 뒤 3개 시작일이 NaN 이다
        """
        # Given
        prices = _wandering_prices(5)

        # When
        result, _ = leveraged_window_returns(prices, 2.0, 3, REBALANCE_DAILY)

        # Then
        assert np.isnan(result[2:]).all()
        assert not np.isnan(result[:2]).any()

    def test_wipeout_is_marked_not_raised(self) -> None:
        """
        목적: 자기자본이 0 이하가 된 구간이 **예외가 아니라 표시로** 돌아옴을 고정한다.

        강제청산을 모델링하지 않으므로 그 구간의 수익률은 정의되지 않는다. 그렇다고
        예외로 멈추면 **그런 구간이 몇 개였는지가 산출물에서 통째로 사라진다** —
        몇 건이 왜 빠졌는지 남겨야 한다 (절대 원칙 4 표본 보존).

        Given: 배수 2 에서 하루에 −60% 나는 가격
        When: 구간 수익률을 낸다
        Then: 수익률이 NaN 이고 소진 표시가 True 다
        """
        # Given
        prices = np.array([100.0, 40.0, 45.0])

        # When
        result, wiped = leveraged_window_returns(prices, 2.0, 2, REBALANCE_MONTHLY)

        # Then
        assert bool(wiped[0]) is True
        assert np.isnan(result[0])

    def test_survivors_are_not_marked_as_wiped_out(self) -> None:
        """
        목적: 살아남은 구간에 소진 표시가 붙지 않음을 고정한다.

        Given: 완만하게 움직이는 가격
        When: 구간 수익률을 낸다
        Then: 소진 표시가 하나도 없다
        """
        # Given
        prices = _wandering_prices(30)

        # When
        _, wiped = leveraged_window_returns(prices, 2.0, 10, REBALANCE_DAILY)

        # Then
        assert not wiped.any()

    def test_invalid_horizon_raises(self) -> None:
        """
        목적: 0 이하 보유 기간을 막음을 고정한다.

        Given: 보유 기간 0
        When: 구간 수익률을 낸다
        Then: ValueError 를 던진다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="보유 기간은 1 이상"):
            leveraged_window_returns(_wandering_prices(5), 2.0, 0, REBALANCE_DAILY)


class TestWindowTable:
    """구간 표의 계약 — 못 잰 시작일도 행을 남긴다."""

    def test_unusable_starts_keep_their_rows_with_a_reason(self) -> None:
        """
        목적: 구간 끝이 데이터를 넘어가는 시작일이 **행으로 남고 사유가 달림**을 고정한다.

        행이 사라지면 그 시작일을 못 쟀다는 사실 자체가 보이지 않는다.

        Given: 5거래일 가격과 구간 3
        When: 구간 표를 만든다
        Then: 5행이 모두 남고 뒤 3행에 사유가 붙는다
        """
        # Given
        dates = pd.Series(pd.bdate_range("2020-01-01", periods=5))
        values, _ = leveraged_window_returns(_wandering_prices(5), 2.0, 3, REBALANCE_DAILY)

        # When
        table = build_window_table(dates, {"선물 매일": values}, 3)

        # Then
        assert len(table) == 5
        assert table[COL_EXCLUDED_REASON].tolist() == [REASON_NONE] * 2 + [REASON_OUT_OF_RANGE] * 3


class TestDecomposition:
    """분해의 계약 — 잔여가 나머지로 정의되지 않았다."""

    def test_residual_is_not_trivially_zero(self) -> None:
        """
        목적: **잔여가 나머지로 정의되지 않았음**을 고정한다.

        `잔여 = 차이 − 나머지` 로 두면 항등식이 정의상 성립해 아무것도 검증하지 못한다.
        잔여가 독립 산식(롤 비용)에서 나온 값이어야 그 크기가 뜻을 갖는다.

        Given: 각 항이 서로 다른 값을 갖는 입력
        When: 분해한다
        Then: 잔여가 0 이 아니고 `차이 − 배수 × 롤 비용` 과 같다
        """
        # Given
        etf = np.array([0.10])
        futures_daily = np.array([0.12])
        futures_monthly = np.array([0.11])
        futures_interest = np.array([0.125])
        continuous = np.array([0.04])
        spot = np.array([0.05])

        # When
        result = decompose(etf, futures_daily, futures_monthly, futures_interest, continuous, spot, 2.0)

        # Then
        assert result["RollCost"].iloc[0] == pytest.approx(-0.01, abs=EXACT_TOLERANCE)
        assert result["RebalanceError"].iloc[0] == pytest.approx(-0.01, abs=EXACT_TOLERANCE)
        assert result["InterestGain"].iloc[0] == pytest.approx(0.005, abs=EXACT_TOLERANCE)
        assert result["FuturesMinusEtf"].iloc[0] == pytest.approx(0.02, abs=EXACT_TOLERANCE)
        # 0.02 − 2 × (−0.01) = 0.04
        assert result["Residual"].iloc[0] == pytest.approx(0.04, abs=EXACT_TOLERANCE)

    def test_roll_cost_is_measured_against_the_spot_index(self) -> None:
        """
        목적: 롤 몫의 기준선이 **현물지수**이며 ETF 와 무관함을 고정한다.

        1배 ETF 를 기준선으로 쓰면 롤 몫에 **그 ETF 의 총보수와 배당 미반영**이 섞여
        「롤이 얼마를 벌거나 잃는가」를 따로 볼 수 없다.

        Given: ETF 수익률만 다른 두 입력
        When: 각각 분해한다
        Then: 롤 몫이 같다
        """
        # Given
        common = (np.array([0.12]), np.array([0.11]), np.array([0.125]), np.array([0.04]), np.array([0.05]))

        # When
        first = decompose(np.array([0.10]), *common, 2.0)
        second = decompose(np.array([0.30]), *common, 2.0)

        # Then
        assert first["RollCost"].iloc[0] == pytest.approx(second["RollCost"].iloc[0], abs=EXACT_TOLERANCE)


class TestHorizons:
    """보유 기간 목록의 계약."""

    def test_default_is_the_study_grid(self) -> None:
        """
        목적: 기본 격자가 검증 #8 과 같은 값임을 고정한다.

        두 검증을 나란히 읽으려면 격자가 같아야 한다.

        Given: 없음
        When: 기본 격자를 얻는다
        Then: `HOLDING_HORIZONS` 와 같다
        """
        # Given / When
        result = horizons_or_default(None)

        # Then
        assert result == sorted(HOLDING_HORIZONS)

    @pytest.mark.parametrize(
        ("horizons", "message"),
        [([], "비어 있습니다"), ([0, 5], "1 이상"), ([5, 5], "중복")],
    )
    def test_invalid_horizons_raise(self, horizons: list[int], message: str) -> None:
        """
        목적: 잘못된 보유 기간 목록을 막음을 고정한다.

        Given: 비었거나 0 이하거나 중복인 목록
        When: 격자를 검증한다
        Then: ValueError 를 던진다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match=message):
            horizons_or_default(horizons)
