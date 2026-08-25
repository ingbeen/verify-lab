"""원달러 그리드 체결 판정의 계약을 고정한다.

체결이 틀리면 **체결 내역은 그럴듯한데 성적만 틀린다.** 특히 하향 돌파와 중복 슬롯이 그렇다.

핵심 계약은 다섯 가지다.

- **하향 돌파가 있어야 산다.** `종가 ≤ 레벨가` 만 보면 백테스트 첫날 현재가 아래가 전부
  체결되고 이후에도 같은 레벨을 매일 산다
- **보유 중인 레벨은 다시 사지 않는다** (사양서 §15.2 #12)
- **목표가는 격자에 고정된다.** 매수 체결가와 무관하며, 체결가 기준으로 잡으면
  익절폭이 슬롯마다 달라진다
- **격자 이탈 보너스는 항상 0 이상**이다. 종가 체결 가정은 유리한 쪽으로만 벗어난다
- **한 거래일에 매수와 매도가 함께 일어날 수 없다.** 매수는 종가 하락을, 매도는 상승을
  각각 함의하기 때문이다
"""

import pandas as pd
import pytest

from verify_lab.strategy.grid.execution import Slot, plan_buys, plan_sells
from verify_lab.strategy.grid.lattice import level_price, target_price
from verify_lab.strategy.grid.paths.base import CostConfig
from verify_lab.strategy.grid.paths.exchange import ExchangePath

# 손계산을 쉽게 하려고 익절폭 25% 를 쓴다. 레벨가가 640 / 800 / 1000 / 1250 / 1562.5 로 딱 떨어진다
HAND_GROWTH = 0.25

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12

# 금액 비교 허용오차
AMOUNT_TOLERANCE = 0.01

TODAY = pd.Timestamp("2020-06-15")
YESTERDAY = pd.Timestamp("2020-06-12")

# 손계산을 그대로 두려고 비용이 없는 경로를 쓴다. 비용 자체의 계약은 경로 테스트가 고정한다
FREE = ExchangePath(CostConfig(exchange_spread_rate=0.0, slippage_rate=0.0, brokerage_rate=0.0))


def _price(index: int) -> float:
    """손계산용 레벨 가격."""
    return level_price(index, growth_rate=HAND_GROWTH)


def _slot(index: int, *, entry_price: float, usd: float = 1000.0) -> Slot:
    """손계산용 보유 슬롯. 비용이 없는 경로라 투입 원화가 `보유 단위 × 체결가` 와 같다."""
    return Slot(
        level_index=index,
        entry_date=YESTERDAY,
        entry_price=entry_price,
        entry_rate=entry_price,
        units=usd,
        invested=usd * entry_price,
        entry_cost=0.0,
    )


def _buy(
    active: list[int],
    held: list[int],
    *,
    previous_close: float,
    close: float,
    amount: float = 1_000_000.0,
    cash: float = 100_000_000.0,
):
    """손계산용 기본 인자로 매수를 계획한다."""
    return plan_buys(
        active,
        held,
        previous_close=previous_close,
        close=close,
        exec_price=close,
        amounts=dict.fromkeys(active, amount),
        cash=cash,
        date=TODAY,
        growth_rate=HAND_GROWTH,
        path=FREE,
    )


class TestDownwardBreakout:
    """하향 돌파 판정을 고정한다."""

    def test_위에서_내려와_뚫으면_산다(self) -> None:
        """
        목적: `전일 종가 > 레벨가 AND 당일 종가 ≤ 레벨가` 를 고정한다 (사양서 §6.1)

        Given: 전일 1,100원 → 당일 990원 (레벨 1000 을 하향 돌파)
        When: 매수를 계획한다
        Then: 그 레벨 하나를 당일 종가로 산다
        """
        # When
        actual = _buy([0], [], previous_close=1100.0, close=990.0)

        # Then
        assert [order.level_index for order in actual.orders] == [0]
        assert actual.orders[0].price == pytest.approx(990.0, abs=EXACT_TOLERANCE)

    def test_아래에서_올라와_닿으면_사지_않는다(self) -> None:
        """
        목적: 전일 종가가 "위에서 내려왔는지" 확인용임을 고정한다

        Given: 전일 900원 → 당일 990원 (레벨 1000 아래에 계속 있었다)
        When: 매수를 계획한다
        Then: 체결이 없다
        """
        # When
        actual = _buy([0], [], previous_close=900.0, close=990.0)

        # Then
        assert actual.orders == ()

    def test_첫날_대량_체결이_없다(self) -> None:
        """
        목적: 사양서 §15.2 필수 검증 #8 을 고정한다

        Given: 현재가(990원) 아래에 활성 레벨이 잔뜩 있고 전일에도 같은 자리였다
        When: 매수를 계획한다
        Then: 한 건도 체결되지 않는다

        Note:
            `종가 ≤ 레벨가` 만으로 판정하면 여기서 네 건이 동시 체결된다
        """
        # When
        actual = _buy([-3, -2, -1, 0], [], previous_close=990.0, close=990.0)

        # Then
        assert actual.orders == ()

    def test_당일_종가가_레벨가와_같으면_산다(self) -> None:
        """
        목적: 매수 조건의 부등호를 고정한다 — 당일은 `≤` 다

        Given: 전일 1,100원 → 당일 정확히 레벨가 1,000원
        When: 매수를 계획한다
        Then: 체결된다
        """
        # When
        actual = _buy([0], [], previous_close=1100.0, close=_price(0))

        # Then
        assert [order.level_index for order in actual.orders] == [0]

    def test_전일_종가가_레벨가와_같으면_사지_않는다(self) -> None:
        """
        목적: 매수 조건의 부등호를 고정한다 — 전일은 `>` 다 (같으면 아니다)

        Given: 전일이 정확히 레벨가 1,000원 → 당일 990원
        When: 매수를 계획한다
        Then: 체결이 없다

        Note:
            전일에 이미 그 레벨에 닿아 있었다면 그날 판정에서 다뤘어야 한다.
            여기서 또 사면 같은 돌파를 두 번 세게 된다
        """
        # When
        actual = _buy([0], [], previous_close=_price(0), close=990.0)

        # Then
        assert actual.orders == ()

    def test_활성이_아닌_레벨은_뚫려도_사지_않는다(self) -> None:
        """
        목적: 범위 밖 레벨이 체결되지 않음을 고정한다 (하단 이탈 A안)

        Given: 활성 레벨이 하나도 없는 상태에서 큰 하락
        When: 매수를 계획한다
        Then: 체결이 없다
        """
        # When
        actual = _buy([], [], previous_close=1100.0, close=700.0)

        # Then
        assert actual.orders == ()


class TestNoDuplicateSlot:
    """중복 슬롯 금지를 고정한다 (사양서 §15.2 #12)."""

    def test_보유_중인_레벨은_다시_사지_않는다(self) -> None:
        """
        목적: 같은 레벨이 두 개 쌓이지 않음을 고정한다

        Given: 레벨 0 을 이미 보유한 상태에서 레벨 0 을 다시 하향 돌파
        When: 매수를 계획한다
        Then: 체결이 없다

        Note:
            거르지 않으면 같은 레벨이 여러 개 쌓여 **노출이 조용히 커진다**
        """
        # When
        actual = _buy([0], [0], previous_close=1100.0, close=990.0)

        # Then
        assert actual.orders == ()

    def test_보유하지_않은_레벨만_고른다(self) -> None:
        """
        목적: 다중 체결에서 보유분만 정확히 걸러짐을 고정한다

        Given: 레벨 -1·0 이 활성이고 그중 0 만 보유 중, 둘 다 하향 돌파
        When: 매수를 계획한다
        Then: 레벨 -1 만 산다
        """
        # When
        actual = _buy([-1, 0], [0], previous_close=1100.0, close=790.0)

        # Then
        assert [order.level_index for order in actual.orders] == [-1]


class TestMultipleFills:
    """다중 체결과 현금 부족 처리를 고정한다."""

    def test_하루에_여러_레벨이_뚫리면_전부_산다(self) -> None:
        """
        목적: 다중 체결 허용을 고정한다 (사양서 §6.3)

        Given: 전일 1,300원 → 당일 790원 (레벨 1250·1000·800 을 한꺼번에 통과)
        When: 매수를 계획한다
        Then: 세 레벨 전부 체결되고 **체결가가 모두 당일 종가로 같다**
        """
        # When
        actual = _buy([-1, 0, 1], [], previous_close=1300.0, close=790.0)

        # Then
        assert sorted(order.level_index for order in actual.orders) == [-1, 0, 1]
        assert {order.price for order in actual.orders} == {790.0}

    def test_목표가는_레벨마다_다르다(self) -> None:
        """
        목적: 같은 날 같은 가격에 사도 **목표가는 격자 위치를 따름**을 고정한다 (사양서 §6.3)

        Given: 레벨 0 과 1 을 같은 날 790원에 산다
        When: 매수 계획의 목표가를 본다
        Then: 각각 1,250원과 1,562.5원이다
        """
        # When
        actual = _buy([0, 1], [], previous_close=1300.0, close=790.0)

        # Then
        targets = {order.level_index: order.target_price for order in actual.orders}
        assert targets[0] == pytest.approx(1250.0, abs=EXACT_TOLERANCE)
        assert targets[1] == pytest.approx(1562.5, abs=EXACT_TOLERANCE)

    def test_현금이_모자라면_아래부터_채운다(self) -> None:
        """
        목적: 결정 C5 의 체결 순서를 고정한다

        Given: 세 레벨이 뚫렸고 슬롯이 100만원씩인데 현금은 250만원뿐
        When: 매수를 계획한다
        Then: 아래(싼) 두 레벨만 체결된다
        """
        # When
        actual = _buy([-1, 0, 1], [], previous_close=1300.0, close=790.0, amount=1_000_000.0, cash=2_500_000.0)

        # Then
        assert sorted(order.level_index for order in actual.orders) == [-1, 0]

    def test_못_사는_레벨에서_중단한다(self) -> None:
        """
        목적: 사양서 §6.5 의 「매수 중단」을 고정한다 (결정 E1)

        Given: 아래 레벨이 300만원이라 현금 250만원으로 못 사고, 위 레벨은 50만원이라 살 수 있다
        When: 매수를 계획한다
        Then: 한 건도 체결되지 않는다 — 건너뛰지 않는다

        Note:
            건너뛰면 체결 순서가 **가격이 아니라 슬롯 크기에 의존**하게 되어 규칙이 하나 늘어난다
        """
        # When
        actual = plan_buys(
            [-1, 0],
            [],
            previous_close=1300.0,
            close=790.0,
            exec_price=790.0,
            amounts={-1: 3_000_000.0, 0: 500_000.0},
            cash=2_500_000.0,
            date=TODAY,
            growth_rate=HAND_GROWTH,
            path=FREE,
        )

        # Then
        assert actual.orders == ()
        assert actual.blocked_levels == (-1, 0)

    def test_자금_부족으로_못_산_레벨을_돌려준다(self) -> None:
        """
        목적: 사양서 §6.5 의 「로그 기록」에 필요한 값을 반환함을 고정한다

        Given: 세 레벨이 뚫렸는데 현금이 두 개 분량뿐
        When: 매수를 계획한다
        Then: 체결되지 못한 레벨 목록이 담겨 있다

        Note:
            자금 소진은 버그가 아니라 **측정 대상**이다 (사양서 §13.2 자금 소진율 분포)
        """
        # When
        actual = _buy([-1, 0, 1], [], previous_close=1300.0, close=790.0, amount=1_000_000.0, cash=2_500_000.0)

        # Then
        assert actual.blocked_levels == (1,)

    def test_체결_합계가_현금을_넘지_않는다(self) -> None:
        """
        목적: 무한자금 가정이 없음을 고정한다 (사양서 §15.2 #1)

        Given: 여러 레벨이 뚫린 여러 현금 수준
        When: 매수를 계획한다
        Then: 언제나 체결 합계 ≤ 현금
        """
        for cash in (0.0, 500_000.0, 1_000_000.0, 2_500_000.0, 100_000_000.0):
            # When
            actual = _buy([-1, 0, 1], [], previous_close=1300.0, close=790.0, cash=cash)

            # Then
            assert sum(order.spent for order in actual.orders) <= cash + AMOUNT_TOLERANCE

    def test_슬롯_금액이_0이면_사지_않는다(self) -> None:
        """
        목적: 엣지 케이스 — 배정 금액 0 을 체결로 세지 않음을 고정한다

        Given: 슬롯 금액이 0원
        When: 매수를 계획한다
        Then: 체결이 없다
        """
        # When
        actual = _buy([0], [], previous_close=1100.0, close=990.0, amount=0.0)

        # Then
        assert actual.orders == ()


class TestSell:
    """매도 판정을 고정한다."""

    def test_종가가_목표가_이상이면_판다(self) -> None:
        """
        목적: `당일 종가 ≥ 목표가` 를 고정한다 (사양서 §6.2)

        Given: 레벨 0(목표가 1,250원)을 보유하고 당일 종가가 1,300원
        When: 매도를 계획한다
        Then: 그 슬롯을 당일 종가로 판다
        """
        # When
        actual = plan_sells(
            [_slot(0, entry_price=990.0)],
            close=1300.0,
            exec_price=1300.0,
            date=TODAY,
            growth_rate=HAND_GROWTH,
            path=FREE,
        )

        # Then
        assert [order.level_index for order in actual] == [0]
        assert actual[0].price == pytest.approx(1300.0, abs=EXACT_TOLERANCE)

    def test_종가가_목표가와_같으면_판다(self) -> None:
        """
        목적: 매도 조건의 부등호를 고정한다 — `≥` 다

        Given: 당일 종가가 정확히 목표가
        When: 매도를 계획한다
        Then: 체결된다
        """
        # When
        actual = plan_sells(
            [_slot(0, entry_price=990.0)],
            close=target_price(0, growth_rate=HAND_GROWTH),
            exec_price=target_price(0, growth_rate=HAND_GROWTH),
            date=TODAY,
            growth_rate=HAND_GROWTH,
            path=FREE,
        )

        # Then
        assert len(actual) == 1

    def test_목표가에_못_미치면_팔지_않는다(self) -> None:
        """
        목적: 미실현 상태가 유지됨을 고정한다

        Given: 당일 종가 1,200원 < 목표가 1,250원
        When: 매도를 계획한다
        Then: 체결이 없다
        """
        # When
        actual = plan_sells(
            [_slot(0, entry_price=990.0)],
            close=1200.0,
            exec_price=1200.0,
            date=TODAY,
            growth_rate=HAND_GROWTH,
            path=FREE,
        )

        # Then
        assert actual == ()

    def test_목표가는_매수_체결가와_무관하다(self) -> None:
        """
        목적: 사양서 §3.3 의 「체결가 무관」을 고정한다 (결정 E4)

        Given: 같은 레벨을 990원에 산 슬롯과 950원에 산 슬롯
        When: 각각 매도를 계획한다
        Then: 목표가가 같다 — 격자에 고정돼 있다
        """
        # When
        first = plan_sells(
            [_slot(0, entry_price=990.0)],
            close=1250.0,
            exec_price=1250.0,
            date=TODAY,
            growth_rate=HAND_GROWTH,
            path=FREE,
        )
        second = plan_sells(
            [_slot(0, entry_price=950.0)],
            close=1250.0,
            exec_price=1250.0,
            date=TODAY,
            growth_rate=HAND_GROWTH,
            path=FREE,
        )

        # Then
        assert first[0].target_price == pytest.approx(second[0].target_price, abs=EXACT_TOLERANCE)

    def test_보유한_레벨_여러_개가_동시에_팔린다(self) -> None:
        """
        목적: 매도도 다중 체결됨을 고정한다

        Given: 레벨 -1(목표 1,000원)과 0(목표 1,250원)을 보유하고 종가가 1,300원
        When: 매도를 계획한다
        Then: 둘 다 팔린다
        """
        # When
        actual = plan_sells(
            [_slot(-1, entry_price=790.0), _slot(0, entry_price=990.0)],
            close=1300.0,
            exec_price=1300.0,
            date=TODAY,
            growth_rate=HAND_GROWTH,
            path=FREE,
        )

        # Then
        assert sorted(order.level_index for order in actual) == [-1, 0]

    def test_보유가_없으면_빈_결과다(self) -> None:
        """
        목적: 엣지 케이스 — 보유 0개를 예외로 만들지 않음을 고정한다

        Given: 보유 슬롯 없음
        When: 매도를 계획한다
        Then: 예외 없이 빈 결과다
        """
        # When
        actual = plan_sells([], close=1300.0, exec_price=1300.0, date=TODAY, growth_rate=HAND_GROWTH, path=FREE)

        # Then
        assert actual == ()


class TestGridExcessBonus:
    """격자 이탈 보너스를 고정한다 (사양서 §6.4)."""

    def test_손계산으로_박는다(self) -> None:
        """
        목적: `이탈 보너스 = 실현손익 − g × 투입액` 산식을 고정한다

        Given: 레벨 0(격자가 1,000원)을 990원에 $1,000 만큼 사서 1,300원에 판다
        When: 매도를 계획한다
        Then: 투입 99만원, 회수 130만원, 실현손익 31만원.
              격자 기준은 99만원 × 25% = 24.75만원이므로 보너스는 6.25만원이다
        """
        # When
        actual = plan_sells(
            [_slot(0, entry_price=990.0, usd=1000.0)],
            close=1300.0,
            exec_price=1300.0,
            date=TODAY,
            growth_rate=HAND_GROWTH,
            path=FREE,
        )

        # Then
        order = actual[0]
        assert order.invested == pytest.approx(990_000.0, abs=AMOUNT_TOLERANCE)
        assert order.proceeds == pytest.approx(1_300_000.0, abs=AMOUNT_TOLERANCE)
        assert order.realized == pytest.approx(310_000.0, abs=AMOUNT_TOLERANCE)
        assert order.grid_excess == pytest.approx(62_500.0, abs=AMOUNT_TOLERANCE)

    def test_격자가에_정확히_사고_팔면_보너스가_0이다(self) -> None:
        """
        목적: 보너스가 **종가 체결 가정의 기여분**임을 고정한다

        Given: 레벨가에 정확히 사서 목표가에 정확히 판다 (지정가 운용과 동일)
        When: 매도를 계획한다
        Then: 보너스가 0 이다
        """
        # When
        actual = plan_sells(
            [_slot(0, entry_price=_price(0), usd=1000.0)],
            close=target_price(0, growth_rate=HAND_GROWTH),
            exec_price=target_price(0, growth_rate=HAND_GROWTH),
            date=TODAY,
            growth_rate=HAND_GROWTH,
            path=FREE,
        )

        # Then
        assert actual[0].grid_excess == pytest.approx(0.0, abs=AMOUNT_TOLERANCE)

    @pytest.mark.parametrize("entry_price", [1000.0, 990.0, 950.0, 900.0])
    @pytest.mark.parametrize("close", [1250.0, 1300.0, 1500.0])
    def test_보너스는_언제나_0_이상이다(self, entry_price: float, close: float) -> None:
        """
        목적: 사양서 §6.4 의 "항상 유리한 쪽으로만 벗어난다" 를 불변조건으로 고정한다

        Given: 레벨가 이하에 사서 목표가 이상에 파는 여러 조합
        When: 매도를 계획한다
        Then: 보너스가 언제나 0 이상이다
        """
        # When
        actual = plan_sells(
            [_slot(0, entry_price=entry_price)],
            close=close,
            exec_price=close,
            date=TODAY,
            growth_rate=HAND_GROWTH,
            path=FREE,
        )

        # Then
        assert actual[0].grid_excess >= -AMOUNT_TOLERANCE


class TestNoSameDayBuyAndSell:
    """한 거래일에 매수와 매도가 함께 일어나지 않음을 고정한다 (결정 E3)."""

    def test_매수가_일어나는_날에는_매도가_없다(self) -> None:
        """
        목적: 동시 체결 불가 불변조건을 고정한다

        Given: 레벨 -1 을 보유(목표가 1,000원)하고, 전일 1,300원 → 당일 790원으로 하락
        When: 같은 날 매수와 매도를 각각 계획한다
        Then: 매수는 있고 매도는 없다

        Note:
            매도되려면 `당일 종가 ≥ 목표가` 여야 하는데, 그 슬롯이 전일에 팔리지 않았다는 것은
            `전일 종가 < 목표가` 라는 뜻이다. 그러면 당일 종가 > 전일 종가가 되어
            하향 돌파(당일 < 전일)와 양립할 수 없다
        """
        # Given
        held = [_slot(-1, entry_price=790.0)]

        # When
        sells = plan_sells(held, close=790.0, exec_price=790.0, date=TODAY, growth_rate=HAND_GROWTH, path=FREE)
        buys = _buy([-2, -1, 0], [-1], previous_close=1300.0, close=790.0)

        # Then
        assert buys.orders
        assert sells == ()

    def test_매도가_일어나는_날에는_매수가_없다(self) -> None:
        """
        목적: 반대 방향으로도 성립함을 고정한다

        Given: 레벨 0 을 보유하고 전일 1,200원 → 당일 1,300원으로 상승
        When: 같은 날 매수와 매도를 각각 계획한다
        Then: 매도는 있고 매수는 없다
        """
        # Given
        held = [_slot(0, entry_price=990.0)]

        # When
        sells = plan_sells(held, close=1300.0, exec_price=1300.0, date=TODAY, growth_rate=HAND_GROWTH, path=FREE)
        buys = _buy([-1, 0, 1], [0], previous_close=1200.0, close=1300.0)

        # Then
        assert sells
        assert buys.orders == ()


class TestValidation:
    """입력 검증 정책을 고정한다."""

    def test_현금이_음수면_거부한다(self) -> None:
        """
        목적: 현금의 유효 범위를 고정한다

        Given: 음수 현금
        When: 매수를 계획한다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="현금"):
            _buy([0], [], previous_close=1100.0, close=990.0, cash=-1.0)

    def test_배정_금액이_없는_활성_레벨은_거부한다(self) -> None:
        """
        목적: 조각 3 의 배분과 활성 레벨이 어긋나면 즉시 실패함을 고정한다

        Given: 활성 레벨 중 하나에 배정 금액이 없다
        When: 매수를 계획한다
        Then: ValueError

        Note:
            조용히 0원으로 처리하면 **그 레벨이 영영 체결되지 않는데 예외가 나지 않는다**
        """
        with pytest.raises(ValueError, match="배정"):
            plan_buys(
                [0, 1],
                [],
                previous_close=1300.0,
                close=790.0,
                exec_price=790.0,
                amounts={0: 1_000_000.0},
                cash=100_000_000.0,
                date=TODAY,
                growth_rate=HAND_GROWTH,
                path=FREE,
            )

    @pytest.mark.parametrize("close", [0.0, -100.0])
    def test_종가가_양수가_아니면_거부한다(self, close: float) -> None:
        """
        목적: 가격의 유효 범위를 고정한다

        Given: 0 이하인 종가
        When: 매도를 계획한다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="종가"):
            plan_sells(
                [_slot(0, entry_price=990.0)],
                close=close,
                exec_price=close,
                date=TODAY,
                growth_rate=HAND_GROWTH,
                path=FREE,
            )

    def test_같은_레벨을_두_번_보유하면_거부한다(self) -> None:
        """
        목적: 중복 슬롯이 이미 생긴 상태를 조용히 통과시키지 않음을 고정한다

        Given: 같은 레벨의 슬롯 두 개
        When: 매도를 계획한다
        Then: ValueError

        Note:
            사양서 §15.2 #12 는 "동일 레벨 2개 보유 불가" 를 필수 검증으로 요구한다.
            매수 쪽에서 막지만, 상태가 깨진 채 흘러들어오는 것도 여기서 잡는다
        """
        with pytest.raises(ValueError, match="중복"):
            plan_sells(
                [_slot(0, entry_price=990.0), _slot(0, entry_price=950.0)],
                close=1300.0,
                exec_price=1300.0,
                date=TODAY,
                growth_rate=HAND_GROWTH,
                path=FREE,
            )
