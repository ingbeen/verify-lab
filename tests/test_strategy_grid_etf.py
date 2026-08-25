"""ETF 집행 경로의 계약을 고정한다.

**ETF 는 환전과 세 곳에서 다르고 셋 다 조용히 틀리는 종류다.**

- **정수 주식 수만 산다.** 못 쓴 예산은 현금으로 남고 사라지지 않는다 (사양서 §15.2 #6)
- **차익에 15.4% 가 붙는다.** 환차익은 비과세다 (§15.2 #9)
- **보유 이자가 0 이다.** 캐리·보수가 종가에 내재돼 있어 더하면 이중계산이다 (§15.2 #4·#5)
"""

import pytest

from verify_lab.strategy.grid.constants import PATH_ETF_1X, PATH_ETF_2X
from verify_lab.strategy.grid.paths.base import CostConfig
from verify_lab.strategy.grid.paths.etf import EtfPath

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12

# 금액 비교 허용오차
AMOUNT_TOLERANCE = 0.01

# 확정된 ETF 비용. 위탁수수료 편도 0.015% + 슬리피지 편도 0.10% = 편도 0.115%, 왕복 0.23%
BROKERAGE = 0.00015
SLIPPAGE = 0.0010


def _path(*, ticker: str = PATH_ETF_1X, brokerage: float = BROKERAGE, slippage: float = SLIPPAGE) -> EtfPath:
    """검사용 ETF 경로."""
    return EtfPath(
        ticker=ticker,
        cost=CostConfig(exchange_spread_rate=0.0008, slippage_rate=slippage, brokerage_rate=brokerage),
    )


class TestIntegerShares:
    """정수 주식 수와 반올림 잔액을 고정한다."""

    def test_정수_주식만_산다(self) -> None:
        """
        목적: 사양서 §15.2 #6 을 고정한다

        Given: 비용이 없는 ETF 경로와 10,000원짜리 주식
        When: 105,000원 예산으로 산다
        Then: 10주를 사고 소수 주식이 생기지 않는다
        """
        # Given
        path = _path(brokerage=0.0, slippage=0.0)

        # When
        actual = path.acquire(105_000.0, price=10_000.0)

        # Then
        assert actual.units == pytest.approx(10.0, abs=EXACT_TOLERANCE)
        assert actual.units == int(actual.units)

    def test_못_쓴_예산은_지출에_들어가지_않는다(self) -> None:
        """
        목적: 결정 C54(예산과 지출의 분리)가 실제로 쓰이는 자리를 고정한다

        Given: 비용이 없는 ETF 경로와 10,000원짜리 주식
        When: 105,000원 예산으로 산다
        Then: 지출이 100,000원이고 5,000원이 예산에 남는다
        """
        # Given
        path = _path(brokerage=0.0, slippage=0.0)

        # When
        actual = path.acquire(105_000.0, price=10_000.0)

        # Then
        assert actual.spent == pytest.approx(100_000.0, abs=AMOUNT_TOLERANCE)
        assert 105_000.0 - actual.spent == pytest.approx(5_000.0, abs=AMOUNT_TOLERANCE)

    def test_한_주도_못_사면_아무것도_사지_않는다(self) -> None:
        """
        목적: 예산이 한 주 값에 못 미치는 경우를 고정한다

        Given: 10,000원짜리 주식
        When: 9,000원 예산으로 산다
        Then: 전부 0 이고 예외가 나지 않는다
        """
        # Given
        path = _path()

        # When
        actual = path.acquire(9_000.0, price=10_000.0)

        # Then
        assert actual.units == pytest.approx(0.0, abs=EXACT_TOLERANCE)
        assert actual.spent == pytest.approx(0.0, abs=EXACT_TOLERANCE)
        assert actual.cost == pytest.approx(0.0, abs=EXACT_TOLERANCE)

    def test_비용을_포함해_살_수_있는_만큼만_산다(self) -> None:
        """
        목적: 비용이 붙으면 살 수 있는 주식 수가 줄어드는 것을 고정한다

        Given: 편도 0.115% 의 ETF 경로와 10,000원짜리 주식
        When: 100,000원 예산으로 산다
        Then: 한 주 실질 단가가 10,011.5원이라 9주만 산다. 지출이 예산을 넘지 않는다
        """
        # Given
        path = _path()

        # When
        actual = path.acquire(100_000.0, price=10_000.0)

        # Then
        assert actual.units == pytest.approx(9.0, abs=EXACT_TOLERANCE)
        assert actual.spent <= 100_000.0
        assert actual.spent == pytest.approx(90_000.0 * 1.00115, abs=AMOUNT_TOLERANCE)

    def test_지출은_명목과_비용의_합이다(self) -> None:
        """
        목적: `spent == notional + cost` 를 고정한다

        Given: 기본 비용의 ETF 경로
        When: 매수한다
        Then: 항등식이 성립한다
        """
        # Given
        path = _path()

        # When
        actual = path.acquire(1_000_000.0, price=13_000.0)

        # Then
        assert actual.spent == pytest.approx(actual.notional + actual.cost, abs=AMOUNT_TOLERANCE)
        assert actual.notional == pytest.approx(actual.units * 13_000.0, abs=AMOUNT_TOLERANCE)


class TestGainTax:
    """매매 차익 과세를 고정한다."""

    def test_차익의_15_4퍼센트를_뗀다(self) -> None:
        """
        목적: 사양서 §10 의 ETF 차익 과세를 손계산으로 고정한다

        Given: 비용 없는 ETF 경로. 10주를 100,000원에 샀다
        When: 주당 12,000원에 판다
        Then: 차익 20,000원의 15.4% 인 3,080원이 세금이고 회수는 116,920원이다
        """
        # Given
        path = _path(brokerage=0.0, slippage=0.0)

        # When
        actual = path.liquidate(10.0, price=12_000.0, cost_basis=100_000.0)

        # Then
        assert actual.notional == pytest.approx(120_000.0, abs=AMOUNT_TOLERANCE)
        assert actual.tax == pytest.approx(3_080.0, abs=AMOUNT_TOLERANCE)
        assert actual.proceeds == pytest.approx(116_920.0, abs=AMOUNT_TOLERANCE)

    def test_손실이면_세금이_0이다(self) -> None:
        """
        목적: 손실 매도에 과세하지 않음을 고정한다

        Given: 비용 없는 ETF 경로. 10주를 100,000원에 샀다
        When: 주당 9,000원에 판다
        Then: 세금이 0 이고 회수가 명목 그대로다
        """
        # Given
        path = _path(brokerage=0.0, slippage=0.0)

        # When
        actual = path.liquidate(10.0, price=9_000.0, cost_basis=100_000.0)

        # Then
        assert actual.tax == pytest.approx(0.0, abs=EXACT_TOLERANCE)
        assert actual.proceeds == pytest.approx(90_000.0, abs=AMOUNT_TOLERANCE)

    def test_비용이_과세_대상_차익을_줄인다(self) -> None:
        """
        목적: 과세 기준이 **비용을 뺀 실현손익**임을 고정한다

        Given: 편도 0.115% 의 ETF 경로. 10주를 100,000원에 샀다
        When: 주당 12,000원에 판다
        Then: 세금이 `(명목 − 매도비용 − 취득원가) × 15.4%` 다
        """
        # Given
        path = _path()

        # When
        actual = path.liquidate(10.0, price=12_000.0, cost_basis=100_000.0)

        # Then
        expected_gain = 120_000.0 - 120_000.0 * 0.00115 - 100_000.0
        assert actual.tax == pytest.approx(expected_gain * 0.154, abs=AMOUNT_TOLERANCE)

    def test_회수는_명목에서_비용과_세금을_뺀_값이다(self) -> None:
        """
        목적: `proceeds == notional − cost − tax` 를 고정한다

        Given: 기본 비용의 ETF 경로
        When: 이익이 나게 판다
        Then: 항등식이 성립한다
        """
        # Given
        path = _path()

        # When
        actual = path.liquidate(100.0, price=13_000.0, cost_basis=1_000_000.0)

        # Then
        assert actual.tax > 0
        assert actual.proceeds == pytest.approx(actual.notional - actual.cost - actual.tax, abs=AMOUNT_TOLERANCE)


class TestNoHoldingInterest:
    """보유 중 이자가 붙지 않음을 고정한다."""

    @pytest.mark.parametrize("market_rate", [0.0, 0.4, 1.547, 5.36])
    def test_시장금리와_무관하게_0이다(self, market_rate: float) -> None:
        """
        목적: 사양서 §15.2 #4 의 「ETF 캐리 이중계산 없음」을 구조로 고정한다

        Given: 어떤 시장 금리든
        When: 보유 이자율을 묻는다
        Then: 언제나 0 이다 — 캐리는 종가에 이미 내재돼 있다
        """
        # Given
        path = _path()

        # When
        actual = path.holding_interest_rate(market_rate)

        # Then
        assert actual == pytest.approx(0.0, abs=EXACT_TOLERANCE)


class TestLeveragePair:
    """261240 과 261250 이 같은 구현을 쓰는 계약을 고정한다."""

    def test_두_종목이_같은_산식을_쓴다(self) -> None:
        """
        목적: 노출 2배가 **가격 계열에만** 들어 있음을 고정한다

        Given: 같은 비용의 261240 과 261250 경로
        When: 같은 예산·같은 가격으로 산다
        Then: 결과가 완전히 같다 — 배분도 산식도 다르지 않다 (사양서 §9.2)
        """
        # Given
        one = _path(ticker=PATH_ETF_1X)
        two = _path(ticker=PATH_ETF_2X)

        # When
        bought_one = one.acquire(1_000_000.0, price=10_000.0)
        bought_two = two.acquire(1_000_000.0, price=10_000.0)

        # Then
        assert bought_one.units == pytest.approx(bought_two.units, abs=EXACT_TOLERANCE)
        assert bought_one.spent == pytest.approx(bought_two.spent, abs=AMOUNT_TOLERANCE)

    def test_경로_이름이_종목_코드다(self) -> None:
        """
        목적: 결과가 어느 종목의 곡선인지 코드에서 답할 수 있게 고정한다

        Given: 261250 경로
        When: 이름을 읽는다
        Then: 종목 코드다
        """
        # Given
        path = _path(ticker=PATH_ETF_2X)

        # When / Then
        assert path.name == PATH_ETF_2X


class TestValidation:
    """입력 검증을 고정한다."""

    def test_예산이_음수면_거부한다(self) -> None:
        """
        목적: 잘못된 예산을 즉시 막는다

        Given: 기본 비용의 ETF 경로
        When: 음수 예산으로 산다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="예산"):
            _path().acquire(-1.0, price=10_000.0)

    @pytest.mark.parametrize("price", [0.0, -10_000.0])
    def test_가격이_양수가_아니면_거부한다(self, price: float) -> None:
        """
        목적: 잘못된 집행 가격을 즉시 막는다

        Given: 기본 비용의 ETF 경로
        When: 0 이하 가격으로 사고판다
        Then: 양쪽 다 ValueError
        """
        path = _path()

        with pytest.raises(ValueError, match="가격"):
            path.acquire(1_000_000.0, price=price)

        with pytest.raises(ValueError, match="가격"):
            path.liquidate(10.0, price=price, cost_basis=100_000.0)

    def test_보유_단위가_음수면_거부한다(self) -> None:
        """
        목적: 잘못된 보유 단위를 즉시 막는다

        Given: 기본 비용의 ETF 경로
        When: 음수 주식 수를 판다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="보유 단위"):
            _path().liquidate(-1.0, price=10_000.0, cost_basis=0.0)

    def test_취득원가가_음수면_거부한다(self) -> None:
        """
        목적: 과세 기준이 되는 값을 즉시 검사한다

        Given: 기본 비용의 ETF 경로
        When: 음수 취득원가로 판다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="취득원가"):
            _path().liquidate(10.0, price=10_000.0, cost_basis=-1.0)
