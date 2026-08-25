"""집행 경로의 계약을 고정한다.

비용은 **예외가 나지 않고 결과만 조용히 틀리는** 종류다. 왕복 0.36% 를 한쪽만 빼먹어도
성적이 그럴듯하게 유지되므로, 항등식을 값으로 박아 둔다.

핵심 계약은 다섯 가지다.

- **`spent == notional + cost`** 와 **`proceeds == notional − cost`** 가 언제나 성립한다
- **비용은 예산 안에서 나간다.** 실제 지출이 예산을 넘지 않는다
- **명목은 `보유 단위 × 체결가`** 다. 슬리피지가 체결가를 밀지 않는다
- **비용률이 0이면 비용 없는 계산이 그대로 복원된다**
- 예산·단위·가격의 유효성을 즉시 검사한다
"""

import pytest

from verify_lab.strategy.grid.paths.base import CostConfig
from verify_lab.strategy.grid.paths.exchange import ExchangePath

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12

# 금액 비교 허용오차
AMOUNT_TOLERANCE = 0.01

# 확정된 기본 비용 (결정 C35). 편도 합계 0.18%, 왕복 0.36%
SPREAD = 0.0008
SLIPPAGE = 0.0010


def _path(*, spread: float = SPREAD, slippage: float = SLIPPAGE) -> ExchangePath:
    """검사용 환전 경로."""
    return ExchangePath(CostConfig(exchange_spread_rate=spread, slippage_rate=slippage))


class TestAcquisitionIdentity:
    """매수 집행의 항등식을 고정한다."""

    def test_지출은_명목과_비용의_합이다(self) -> None:
        """
        목적: `spent == notional + cost` 를 고정한다

        Given: 기본 비용의 환전 경로
        When: 100만원 예산으로 환율 1,300원에 매수한다
        Then: 지출이 명목과 비용의 합이다
        """
        # Given
        path = _path()

        # When
        actual = path.acquire(1_000_000.0, price=1_300.0)

        # Then
        assert actual.spent == pytest.approx(actual.notional + actual.cost, abs=AMOUNT_TOLERANCE)

    def test_비용은_예산_안에서_나간다(self) -> None:
        """
        목적: 지출이 예산을 넘지 않는 계약을 고정한다

        Given: 기본 비용의 환전 경로
        When: 100만원 예산으로 매수한다
        Then: 지출이 예산과 같고 비용이 예산에 비례한다
        """
        # Given
        path = _path()

        # When
        actual = path.acquire(1_000_000.0, price=1_300.0)

        # Then
        assert actual.spent == pytest.approx(1_000_000.0, abs=AMOUNT_TOLERANCE)
        assert actual.cost == pytest.approx(1_000_000.0 * (SPREAD + SLIPPAGE), abs=AMOUNT_TOLERANCE)

    def test_명목은_단위와_체결가의_곱이다(self) -> None:
        """
        목적: 슬리피지가 체결가를 밀지 않음을 고정한다

        Given: 기본 비용의 환전 경로
        When: 100만원 예산으로 환율 1,300원에 매수한다
        Then: 명목이 `보유 달러 × 1,300` 이다 — 체결 환율이 밀렸다면 어긋난다
        """
        # Given
        path = _path()

        # When
        actual = path.acquire(1_000_000.0, price=1_300.0)

        # Then
        assert actual.notional == pytest.approx(actual.units * 1_300.0, abs=AMOUNT_TOLERANCE)

    def test_손계산으로_박는다(self) -> None:
        """
        목적: 매수 집행의 값을 손계산으로 고정한다

        Given: 편도 비용 0.18% 의 환전 경로
        When: 1,000,000원으로 환율 1,000원에 매수한다
        Then: 비용 1,800원, 명목 998,200원, 보유 998.2달러
        """
        # Given
        path = _path()

        # When
        actual = path.acquire(1_000_000.0, price=1_000.0)

        # Then
        assert actual.cost == pytest.approx(1_800.0, abs=AMOUNT_TOLERANCE)
        assert actual.notional == pytest.approx(998_200.0, abs=AMOUNT_TOLERANCE)
        assert actual.units == pytest.approx(998.2, abs=EXACT_TOLERANCE)

    def test_예산이_0이면_아무것도_사지_않는다(self) -> None:
        """
        목적: 예산 0 이 예외가 아니라 빈 체결임을 고정한다

        Given: 기본 비용의 환전 경로
        When: 예산 0 으로 매수한다
        Then: 단위·지출·비용·명목이 전부 0 이다
        """
        # Given
        path = _path()

        # When
        actual = path.acquire(0.0, price=1_300.0)

        # Then
        assert actual.units == pytest.approx(0.0, abs=EXACT_TOLERANCE)
        assert actual.spent == pytest.approx(0.0, abs=EXACT_TOLERANCE)
        assert actual.cost == pytest.approx(0.0, abs=EXACT_TOLERANCE)
        assert actual.notional == pytest.approx(0.0, abs=EXACT_TOLERANCE)


class TestLiquidationIdentity:
    """매도 집행의 항등식을 고정한다."""

    def test_회수는_명목에서_비용을_뺀_값이다(self) -> None:
        """
        목적: `proceeds == notional − cost` 를 고정한다

        Given: 기본 비용의 환전 경로
        When: 1,000달러를 환율 1,300원에 판다
        Then: 회수액이 명목에서 비용을 뺀 값이다
        """
        # Given
        path = _path()

        # When
        actual = path.liquidate(1_000.0, price=1_300.0)

        # Then
        assert actual.proceeds == pytest.approx(actual.notional - actual.cost, abs=AMOUNT_TOLERANCE)

    def test_손계산으로_박는다(self) -> None:
        """
        목적: 매도 집행의 값을 손계산으로 고정한다

        Given: 편도 비용 0.18% 의 환전 경로
        When: 1,000달러를 환율 1,000원에 판다
        Then: 명목 1,000,000원, 비용 1,800원, 회수 998,200원
        """
        # Given
        path = _path()

        # When
        actual = path.liquidate(1_000.0, price=1_000.0)

        # Then
        assert actual.notional == pytest.approx(1_000_000.0, abs=AMOUNT_TOLERANCE)
        assert actual.cost == pytest.approx(1_800.0, abs=AMOUNT_TOLERANCE)
        assert actual.proceeds == pytest.approx(998_200.0, abs=AMOUNT_TOLERANCE)

    def test_사고_바로_팔면_왕복비용만큼_잃는다(self) -> None:
        """
        목적: 왕복비용이 확정값(0.36%)과 맞는지 고정한다

        Given: 편도 비용 0.18% 의 환전 경로
        When: 같은 환율로 사고 바로 판다
        Then: 손실이 예산의 0.36% 근처다 (매수 비용이 지출 기준이라 2차항만큼 더 크다)
        """
        # Given
        path = _path()

        # When
        bought = path.acquire(1_000_000.0, price=1_300.0)
        sold = path.liquidate(bought.units, price=1_300.0)

        # Then
        loss_rate = (bought.spent - sold.proceeds) / bought.spent
        assert loss_rate == pytest.approx(0.0036, abs=1e-5)


class TestZeroCost:
    """비용률 0 이 비용 없는 계산을 복원함을 고정한다."""

    def test_비용이_0이면_예산_전액이_명목이_된다(self) -> None:
        """
        목적: 비용 도입이 기존 결과를 바꾸지 않았음을 보는 회귀 안전망

        Given: 비용률이 전부 0 인 환전 경로
        When: 100만원으로 환율 1,250원에 사고 같은 환율로 판다
        Then: 명목이 예산과 같고, 왕복해도 금액이 보존된다
        """
        # Given
        path = _path(spread=0.0, slippage=0.0)

        # When
        bought = path.acquire(1_000_000.0, price=1_250.0)
        sold = path.liquidate(bought.units, price=1_250.0)

        # Then
        assert bought.notional == pytest.approx(1_000_000.0, abs=AMOUNT_TOLERANCE)
        assert bought.units == pytest.approx(800.0, abs=EXACT_TOLERANCE)
        assert sold.proceeds == pytest.approx(1_000_000.0, abs=AMOUNT_TOLERANCE)


class TestValidation:
    """입력 검증을 고정한다."""

    @pytest.mark.parametrize("rate", [-0.001, 1.0, 1.5])
    def test_비용률이_범위를_벗어나면_거부한다(self, rate: float) -> None:
        """
        목적: 비용률의 유효 범위를 고정한다

        Given: 0 미만이거나 1 이상인 비용률
        When: 설정을 만든다
        Then: ValueError
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="0 이상 1 미만"):
            CostConfig(exchange_spread_rate=rate, slippage_rate=SLIPPAGE)

    def test_예산이_음수면_거부한다(self) -> None:
        """
        목적: 잘못된 예산을 즉시 막는다

        Given: 기본 비용의 환전 경로
        When: 음수 예산으로 매수한다
        Then: ValueError
        """
        # Given
        path = _path()

        # When / Then
        with pytest.raises(ValueError, match="예산"):
            path.acquire(-1.0, price=1_300.0)

    @pytest.mark.parametrize("price", [0.0, -1_300.0])
    def test_가격이_양수가_아니면_거부한다(self, price: float) -> None:
        """
        목적: 잘못된 집행 가격을 즉시 막는다

        Given: 기본 비용의 환전 경로
        When: 0 이하 가격으로 사고판다
        Then: 양쪽 다 ValueError
        """
        # Given
        path = _path()

        # When / Then
        with pytest.raises(ValueError, match="가격"):
            path.acquire(1_000_000.0, price=price)

        with pytest.raises(ValueError, match="가격"):
            path.liquidate(1_000.0, price=price)

    def test_보유_단위가_음수면_거부한다(self) -> None:
        """
        목적: 잘못된 보유 단위를 즉시 막는다

        Given: 기본 비용의 환전 경로
        When: 음수 단위를 판다
        Then: ValueError
        """
        # Given
        path = _path()

        # When / Then
        with pytest.raises(ValueError, match="보유 단위"):
            path.liquidate(-1.0, price=1_300.0)


class TestPathIdentity:
    """경로가 자기를 밝히는 계약을 고정한다."""

    def test_경로_이름을_돌려준다(self) -> None:
        """
        목적: 결과가 어느 경로의 곡선인지 코드에서 답할 수 있게 고정한다

        Given: 환전 경로
        When: 이름을 읽는다
        Then: 비어 있지 않은 이름이다
        """
        # Given
        path = _path()

        # When
        actual = path.name

        # Then
        assert actual == "환전"
