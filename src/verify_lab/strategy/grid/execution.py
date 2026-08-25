"""체결 판정 — 오늘 무엇을 사고 파는가

```
매수: 전일 종가 > 레벨가  AND  당일 종가 ≤ 레벨가        → 당일 종가로 체결 (하향 돌파)
매도: 당일 종가 ≥ 목표가(레벨 k+1)                       → 당일 종가로 체결
```

**하향 돌파 조건이 없으면 백테스트 첫날 현재가 아래 레벨이 전부 동시 체결되고**, 이후에도
같은 레벨을 매일 산다. 전일 종가는 "위에서 내려왔는지" 확인용일 뿐이며 **판정도 체결도 모두
당일 종가**다 (사양서 §6.1).

**목표가는 격자에 고정돼 매수 체결가와 무관하다**(§3.3). 종가 체결이라 체결가가 레벨가보다
낮은데 체결가에 익절폭을 붙이면 **익절폭이 슬롯마다 달라지고** 격자 이탈 보너스의 정의가 무너진다.

**격자 이탈 보너스를 반드시 따로 센다**(§6.4). 종가 체결 가정에서는 체결가가 격자에서
**항상 유리한 쪽으로만** 벗어나며 급락일에 커진다. 이 몫을 분리하지 않으면 실제 지정가 운용과
비교가 성립하지 않고, §15.3 은 총수익의 30% 를 넘으면 결과를 신뢰하지 말라고 규정한다.
**보너스는 비용 전 명목으로 잰다** — 지정가 운용도 같은 비용을 물므로 비용은 상쇄되며,
비용 후 금액으로 재면 그 판정이 다른 것을 재게 된다.

**금액 계산은 집행 경로가 한다.** 이 모듈은 어느 레벨을 사고 파는지까지만 정하고,
그 예산으로 실제 무엇을 얼마나 사는지는 경로에 위임한다 — 경로마다 보유 단위와 비용 구조가 다르다.

**이 모듈은 상태를 들지 않는다.** 보유 슬롯을 인자로 받아 하루치 판정만 내며,
상태를 갱신하는 것은 시뮬레이션 루프의 책임이다.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pandas as pd

from verify_lab.strategy.grid.constants import GRID_ANCHOR_PRICE
from verify_lab.strategy.grid.lattice import level_price, target_price
from verify_lab.strategy.grid.paths.base import ExecutionPath
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class Slot:
    """보유 중인 슬롯 하나

    **투입 원화를 저장한다.** 비용이 없을 때는 `보유 단위 × 체결가` 로 파생시킬 수 있었지만,
    거래비용이 붙으면서 그 등식이 깨졌다 — 예산 안에서 비용이 먼저 나가고 남은 돈으로 사기 때문이다.
    비용 전 명목은 `notional_invested` 가 따로 답한다.

    Attributes:
        level_index: 이 슬롯이 붙어 있는 레벨 번호 k
        entry_date: 매수 체결일
        entry_price: 매수 체결 가격 (당일 종가)
        units: 보유 단위 (환전 경로는 달러)
        invested: 실제로 나간 원화. **비용을 포함한다**
        entry_cost: 그중 매수 거래비용
    """

    level_index: int
    entry_date: pd.Timestamp
    entry_price: float
    units: float
    invested: float
    entry_cost: float

    @property
    def notional_invested(self) -> float:
        """비용 전 명목 투입 (`보유 단위 × 체결가`)."""
        return self.units * self.entry_price


@dataclass(frozen=True)
class BuyOrder:
    """매수 체결 하나

    Attributes:
        level_index: 레벨 번호 k
        date: 체결일
        price: 체결 가격 (당일 종가)
        budget: 배정된 슬롯 금액
        spent: 실제로 나간 원화. **경로가 예산을 다 쓰지 못할 수 있어 예산 이하다**
        cost: 그중 거래비용
        units: 사들인 보유 단위
        notional: 비용 전 명목 (`units × price`)
        target_price: 매도 목표가. **격자에 고정되며 체결가와 무관하다**
    """

    level_index: int
    date: pd.Timestamp
    price: float
    budget: float
    spent: float
    cost: float
    units: float
    notional: float
    target_price: float


@dataclass(frozen=True)
class SellOrder:
    """매도 체결 하나

    Attributes:
        level_index: 레벨 번호 k
        date: 체결일
        price: 체결 가격 (당일 종가)
        target_price: 이 슬롯의 목표가
        invested: 투입했던 원화 (비용 포함)
        notional_invested: 비용 전 명목 투입
        proceeds: 회수한 원화 (비용 차감 후)
        notional_proceeds: 비용 전 명목 회수
        cost: 매도 거래비용
        realized: 실현손익 (`proceeds − invested`). **비용을 뺀 값이다**
        grid_excess: 격자 이탈 보너스. **비용 전 명목 기준**으로 잰 종가 체결 가정의 기여분
        hold_days: 진입일로부터의 보유 달력일 수
    """

    level_index: int
    date: pd.Timestamp
    price: float
    target_price: float
    invested: float
    notional_invested: float
    proceeds: float
    notional_proceeds: float
    cost: float
    realized: float
    grid_excess: float
    hold_days: int


@dataclass(frozen=True)
class BuyPlan:
    """하루치 매수 계획

    Attributes:
        orders: 체결된 매수 (레벨 k 오름차순)
        blocked_levels: 하향 돌파했지만 **현금이 모자라 체결하지 못한** 레벨 (오름차순).
            자금 소진은 버그가 아니라 측정 대상이다 (사양서 §6.5·§13.2)
    """

    orders: tuple[BuyOrder, ...]
    blocked_levels: tuple[int, ...]


def plan_sells(
    held: Sequence[Slot],
    *,
    close: float,
    date: pd.Timestamp,
    growth_rate: float,
    path: ExecutionPath,
    anchor: float = GRID_ANCHOR_PRICE,
) -> tuple[SellOrder, ...]:
    """보유 슬롯 중 목표가에 닿은 것을 판다.

    Args:
        held: 보유 슬롯. 같은 레벨이 두 개 있으면 거부한다
        close: 당일 종가 (양수)
        date: 체결일
        growth_rate: 익절폭 g (비율)
        path: 집행 경로. 회수 금액과 비용을 계산한다
        anchor: 격자의 앵커 가격

    Returns:
        매도 체결 (레벨 k 오름차순). 없으면 빈 튜플

    Raises:
        ValueError: 종가가 양수가 아니거나, 같은 레벨의 슬롯이 중복된 경우
    """
    if close <= 0:
        raise ValueError(f"당일 종가는 양수여야 합니다: {close}")

    indices = [slot.level_index for slot in held]
    if len(set(indices)) != len(indices):
        raise ValueError(f"같은 레벨의 슬롯이 중복됐습니다: {sorted(indices)}")

    orders: list[SellOrder] = []
    for slot in sorted(held, key=lambda item: item.level_index):
        target = target_price(slot.level_index, growth_rate=growth_rate, anchor=anchor)
        if close < target:
            continue

        liquidation = path.liquidate(slot.units, price=close)
        notional_invested = slot.notional_invested

        orders.append(
            SellOrder(
                level_index=slot.level_index,
                date=date,
                price=close,
                target_price=target,
                invested=slot.invested,
                notional_invested=notional_invested,
                proceeds=liquidation.proceeds,
                notional_proceeds=liquidation.notional,
                cost=liquidation.cost,
                realized=liquidation.proceeds - slot.invested,
                # 격자대로 지정가 운용했다면 얻었을 몫을 뺀 나머지가 종가 체결 가정의 기여분이다.
                # 지정가 운용도 같은 비용을 물므로 **비용 전 명목**끼리 견준다
                grid_excess=(liquidation.notional - notional_invested) - growth_rate * notional_invested,
                hold_days=int((date - slot.entry_date).days),
            )
        )

    if orders:
        logger.debug(f"매도 {len(orders)}건: 종가 {close:,.2f}, 레벨 {[order.level_index for order in orders]}")

    return tuple(orders)


def plan_buys(
    active_indices: Sequence[int],
    held_indices: Sequence[int],
    *,
    previous_close: float,
    close: float,
    amounts: Mapping[int, float],
    cash: float,
    date: pd.Timestamp,
    growth_rate: float,
    path: ExecutionPath,
    anchor: float = GRID_ANCHOR_PRICE,
) -> BuyPlan:
    """하향 돌파한 활성 레벨을 현금이 닿는 데까지 산다.

    현금이 모자라면 **아래(싼) 레벨부터 채우고 못 사는 레벨에서 중단한다**(결정 C5·사양서 §6.5).
    건너뛰면 체결 순서가 가격이 아니라 슬롯 크기에 의존하게 되어 규칙이 하나 늘어난다.

    **중단 판정은 배정된 슬롯 금액으로 한다.** 경로가 예산을 다 쓰지 못하는 경우에도
    기준은 "배정액을 낼 수 있는가"이며, 실제로 빠져나간 금액만 남은 현금에서 줄인다.

    Args:
        active_indices: 오늘 활성인 레벨 번호
        held_indices: 이미 보유 중인 레벨 번호. **다시 사지 않는다** (사양서 §15.2 #12)
        previous_close: 전일 종가 (양수)
        close: 당일 종가 (양수)
        amounts: 레벨 번호 → 슬롯 금액. **활성 레벨 전부에 값이 있어야 한다**
        cash: 쓸 수 있는 원화 (0 이상)
        date: 체결일
        growth_rate: 익절폭 g (비율)
        path: 집행 경로. 보유 단위와 비용을 계산한다
        anchor: 격자의 앵커 가격

    Returns:
        체결된 매수와, 돌파했지만 현금이 모자라 못 산 레벨

    Raises:
        ValueError: 가격이 양수가 아니거나, 현금이 음수이거나,
            활성 레벨에 배정 금액이 없는 경우
    """
    if previous_close <= 0:
        raise ValueError(f"전일 종가는 양수여야 합니다: {previous_close}")

    if close <= 0:
        raise ValueError(f"당일 종가는 양수여야 합니다: {close}")

    if cash < 0:
        raise ValueError(f"현금은 0 이상이어야 합니다: {cash}")

    missing = [index for index in active_indices if index not in amounts]
    if missing:
        raise ValueError(f"활성 레벨에 배정 금액이 없습니다: {sorted(missing)}")

    held = set(held_indices)

    # 1. 하향 돌파 판정. 전일 종가는 "위에서 내려왔는지" 확인용이고 체결가는 당일 종가다.
    #    아래(싼) 레벨부터 처리하도록 오름차순으로 세운다 (결정 C5)
    candidates = sorted(
        index
        for index in active_indices
        if index not in held and previous_close > level_price(index, growth_rate=growth_rate, anchor=anchor) >= close
    )

    orders: list[BuyOrder] = []
    blocked: list[int] = []
    remaining = cash

    for position, index in enumerate(candidates):
        budget = amounts[index]

        # 배정이 0원이면 체결로 세지 않는다. 체결 0원짜리 슬롯은 목표가만 차지한다
        if budget <= 0:
            continue

        if budget > remaining:
            # 자금 소진. 여기서 멈추고 남은 후보를 전부 미체결로 남긴다
            blocked = candidates[position:]
            logger.debug(f"자금 소진으로 매수 중단: 남은 현금 {remaining:,.0f}원, 미체결 레벨 {blocked}")
            break

        # 2. 금액 계산은 경로가 한다. 비용은 예산 안에서 나가고 남은 돈이 명목이 된다
        acquisition = path.acquire(budget, price=close)
        remaining -= acquisition.spent

        orders.append(
            BuyOrder(
                level_index=index,
                date=date,
                price=close,
                budget=budget,
                spent=acquisition.spent,
                cost=acquisition.cost,
                units=acquisition.units,
                notional=acquisition.notional,
                target_price=target_price(index, growth_rate=growth_rate, anchor=anchor),
            )
        )

    if orders:
        logger.debug(f"매수 {len(orders)}건: 종가 {close:,.2f}, 레벨 {[order.level_index for order in orders]}")

    return BuyPlan(orders=tuple(orders), blocked_levels=tuple(blocked))
