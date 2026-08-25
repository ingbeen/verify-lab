"""시뮬레이션 루프와 일별 시가평가

조각 넷(격자·범위·배분·체결)을 하루씩 돌려 **일별 총자산 곡선**을 낸다.
그 곡선이 모든 매매법의 공통 산출물이며, 표준 지표는 곡선 하나만 받는 함수가 계산한다.

하루의 처리 순서는 **매도 → 총자산 평가 → 슬롯 금액 → 매수** 다. 매도로 나온 현금을 같은 날
매수에 쓸 수 있어야 자연스럽기 때문인데, **한 거래일에 매수와 매도가 함께 일어날 수 없어**
순서가 결과를 바꾸지는 않는다 — 매수는 종가 하락을, 매도는 종가 상승을 각각 함의한다.

```
총자산 = 원화현금 + Σ(슬롯 보유 단위 × 당일 종가)
```

**미실현 평가손익을 반드시 반영한다.** 실현손익만 집계하면 그리드 곡선은 **구조적으로 항상
우상향한다** — 매도는 무조건 이익 실현이고 손실은 미실현으로 잔류하기 때문이다.
사양서 §8 이 "2009~2014 하락장에서도 실현 기준 곡선은 예쁘게 올라가지만 실제 계좌는 반토막"
이라고 적은 것이 이 사고다.

**총자산은 거래비용만큼만 줄어든다.** 매도 전후와 매수 전후를 각각 검사하며, 감소분이
그때 발생한 비용과 다르면 회계가 깨진 것이므로 즉시 중단한다. 자산이 원화에서 달러로 바뀌는
것만으로는 총액이 변하지 않아야 한다.

**평가에는 비용을 적용하지 않는다** (사양서 §8). 매일 청산 비용을 차감하면 미실현 손실이
과대계상돼 MDD 가 오염된다. 비용은 **실제 체결 시점에만** 발생한다.

**이 계층은 이자와 세금을 다루지 않는다.** 달러 RP·원화 파킹 이자와 원천징수는 아직 없다.
사양서 §17.1 은 대기자금 이자를 가장 큰 수익원으로 잡았으므로 그것이 붙으면
곡선의 성격이 달라진다.
"""

from dataclasses import dataclass, field

import pandas as pd

from verify_lab.common_constants import COL_DATE, COL_VALUE
from verify_lab.data.loader import validate_market_frame
from verify_lab.strategy.grid.allocation import allocate_slots
from verify_lab.strategy.grid.constants import (
    COL_ACTIVE_LEVELS,
    COL_BLOCKED_COUNT,
    COL_BUY_COUNT,
    COL_CASH,
    COL_CLOSE_RATE,
    COL_COST,
    COL_HELD_SLOTS,
    COL_RANGE_HIGH,
    COL_RANGE_LOW,
    COL_REBALANCED,
    COL_SELL_COUNT,
    COL_TOTAL_ASSETS,
    COL_USD_VALUE,
    GRID_ANCHOR_PRICE,
)
from verify_lab.strategy.grid.execution import SellOrder, Slot, plan_buys, plan_sells
from verify_lab.strategy.grid.lattice import active_level_indices, level_price
from verify_lab.strategy.grid.paths.base import CostConfig
from verify_lab.strategy.grid.paths.exchange import ExchangePath
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 범위표가 반드시 가져야 하는 컬럼
DAILY_RANGE_REQUIRED = [COL_DATE, COL_RANGE_LOW, COL_RANGE_HIGH, COL_REBALANCED]

# 일별 곡선의 컬럼 순서
DAILY_COLUMNS = [
    COL_DATE,
    COL_CLOSE_RATE,
    COL_RANGE_LOW,
    COL_RANGE_HIGH,
    COL_REBALANCED,
    COL_ACTIVE_LEVELS,
    COL_HELD_SLOTS,
    COL_BUY_COUNT,
    COL_SELL_COUNT,
    COL_BLOCKED_COUNT,
    COL_COST,
    COL_CASH,
    COL_USD_VALUE,
    COL_TOTAL_ASSETS,
]

# 체결 내역의 컬럼 순서. 사용자가 차트로 직접 대조할 원자료다
TRADE_COLUMNS = [
    "level_index",
    "level_price",
    "target_price",
    "entry_date",
    "entry_price",
    "exit_date",
    "exit_price",
    "invested",
    "buy_cost",
    "proceeds",
    "sell_cost",
    "realized",
    "grid_excess",
    "hold_days",
]

# 회계 항등식의 허용오차 (원). 부동소수점 누적 오차만 넘기고 실제 불일치는 잡는다
IDENTITY_TOLERANCE = 1e-6


@dataclass(frozen=True)
class GridConfig:
    """한 번의 실행에 쓰는 파라미터

    **용도별로 나눈다.** 격자를 정하는 값과 비용을 정하는 값이 한 평면에 섞이면
    "무엇이 격자를 바꾸고 무엇이 비용만 바꾸는가"가 이름으로만 구분된다. 사양서 §12.1 의
    축별 단독 검사도 용도 단위로 갈라져 있어, 축 하나를 바꾸는 것이 곧 한 객체를 갈아 끼우는 일이 된다.

    Attributes:
        lookback_years: 룩백 N (년)
        growth_rate: 익절폭 g (비율)
        min_range_width: 최소 범위폭 (비율)
        allocation_spread: 자금 차등 폭 (비율)
        slot_cap_ratio: 슬롯 상한 (비율)
        initial_capital: 초기 자본금 (원)
        cost: 거래비용 파라미터
        anchor: 격자의 앵커 가격
    """

    lookback_years: int
    growth_rate: float
    min_range_width: float
    allocation_spread: float
    slot_cap_ratio: float
    initial_capital: float
    cost: CostConfig
    anchor: float = GRID_ANCHOR_PRICE

    def __post_init__(self) -> None:
        """설정을 즉시 검사한다.

        Raises:
            ValueError: 초기 자본금이 양수가 아닌 경우.
                나머지 파라미터는 각 계층의 함수가 검사한다
        """
        if self.initial_capital <= 0:
            raise ValueError(f"초기 자본금은 양수여야 합니다: {self.initial_capital}")


@dataclass(frozen=True)
class GridResult:
    """실행 산출물

    Attributes:
        daily: 거래일 한 줄씩의 곡선. 컬럼 구성은 `DAILY_COLUMNS`
        trades: 청산이 끝난 체결 내역. 컬럼 구성은 `TRADE_COLUMNS`
        open_slots: 종료 시점에 남은 미청산 슬롯. **강제 청산하지 않는다** (결정 C8·G4)
        open_invested: 미청산 슬롯에 투입된 원화
        open_value: 미청산 슬롯의 마지막 날 시가평가액
        open_unrealised: 미청산 평가손익 (`open_value − open_invested`)
    """

    daily: pd.DataFrame
    trades: pd.DataFrame
    open_slots: tuple[Slot, ...]
    open_invested: float
    open_value: float
    open_unrealised: float = field(default=0.0)


def run_grid(series: pd.DataFrame, ranges: pd.DataFrame, *, config: GridConfig) -> GridResult:
    """그리드를 하루씩 돌려 일별 총자산 곡선과 체결 내역을 낸다.

    **전 기간 시세를 넘긴다.** 매매 시작일의 하향 돌파 판정에 직전 거래일 종가가 필요한데,
    시세를 먼저 잘라 넘기면 그 값이 사라진다. 결과 행은 `ranges` 의 거래일에 맞춰진다.

    Args:
        series: 일별 단일 값 시계열 **전 기간** (`load_series_csv` 가 돌려준 형태)
        ranges: 거래일별 범위표 (`build_daily_ranges` 가 돌려준 형태)
        config: 실행 파라미터

    Returns:
        일별 곡선·체결 내역·미청산 슬롯

    Raises:
        ValueError: 입력이 비었거나, 컬럼이 없거나, 범위표의 거래일이 시세에 없는 경우
        RuntimeError: 현금이 음수가 되거나 중복 슬롯이 생기거나 회계 항등식이 깨진 경우
    """
    validate_market_frame(series, [COL_DATE, COL_VALUE])
    validate_market_frame(ranges, DAILY_RANGE_REQUIRED)

    closes = series.set_index(COL_DATE)[COL_VALUE]
    positions = closes.index.get_indexer(pd.DatetimeIndex(ranges[COL_DATE]))
    if (positions < 0).any():
        missing = pd.DatetimeIndex(ranges[COL_DATE])[positions < 0]
        raise ValueError(f"범위표의 거래일이 시세에 없습니다: {[str(date.date()) for date in missing[:5]]}")

    if positions[0] == 0:
        raise ValueError("매매 시작일 앞에 거래일이 없어 하향 돌파를 판정할 수 없습니다 — 전 기간 시세를 넘겨야 합니다")

    path = ExchangePath(config.cost)

    cash = config.initial_capital
    held: dict[int, Slot] = {}
    rows: list[dict[str, object]] = []
    trades: list[dict[str, object]] = []

    for offset, (_, day) in enumerate(ranges.iterrows()):
        date = pd.Timestamp(day[COL_DATE])
        position = int(positions[offset])
        close = float(closes.iloc[position])
        previous_close = float(closes.iloc[position - 1])

        # 1. 매도. 목표가에 닿은 슬롯을 전부 청산하고 현금을 회수한다.
        #    매도 전 총자산을 먼저 재 두는 것은 감소분이 매도 비용과 같은지 검사하기 위해서다
        opening_total = cash + sum(slot.units for slot in held.values()) * close
        sells = plan_sells(
            list(held.values()),
            close=close,
            date=date,
            growth_rate=config.growth_rate,
            path=path,
            anchor=config.anchor,
        )
        sell_cost = 0.0
        for sell in sells:
            slot = held.pop(sell.level_index)
            cash += sell.proceeds
            sell_cost += sell.cost
            trades.append(_trade_row(slot, sell, growth_rate=config.growth_rate, anchor=config.anchor))

        # 2. 총자산 평가. **매수 직전의 값**이며 사양서 §5.2 가 요구하는 "매일 종가 확정 후" 다
        usd_value = sum(slot.units for slot in held.values()) * close
        total_assets = cash + usd_value
        _assert_cost_only_decline(opening_total, total_assets, cost=sell_cost, stage="매도", date=date)

        # 3. 활성 레벨과 슬롯 금액. 분모는 활성 레벨 전체이며 보유분을 포함한다 (결정 C4)
        active = active_level_indices(
            float(day[COL_RANGE_LOW]),
            float(day[COL_RANGE_HIGH]),
            growth_rate=config.growth_rate,
            anchor=config.anchor,
        )
        allocation = allocate_slots(
            active,
            low=float(day[COL_RANGE_LOW]),
            high=float(day[COL_RANGE_HIGH]),
            total_assets=total_assets,
            growth_rate=config.growth_rate,
            anchor=config.anchor,
            spread=config.allocation_spread,
            slot_cap_ratio=config.slot_cap_ratio,
        )

        # 4. 매수. 하향 돌파한 미보유 레벨을 아래(싼) 쪽부터 현금이 닿는 데까지 산다
        plan = plan_buys(
            active,
            list(held),
            previous_close=previous_close,
            close=close,
            amounts=allocation.amounts,
            cash=cash,
            date=date,
            growth_rate=config.growth_rate,
            path=path,
            anchor=config.anchor,
        )
        buy_cost = 0.0
        for buy in plan.orders:
            if buy.level_index in held:
                raise RuntimeError(f"내부 불변조건 위반: 이미 보유한 레벨을 다시 샀습니다 - 레벨 {buy.level_index}, 날짜 {date.date()}")

            # 현금은 **배정된 예산이 아니라 실제로 나간 금액**만큼 줄어든다.
            # 경로가 예산을 다 쓰지 못할 수 있어 둘은 같은 값이 아니다
            cash -= buy.spent
            buy_cost += buy.cost
            held[buy.level_index] = Slot(
                level_index=buy.level_index,
                entry_date=date,
                entry_price=buy.price,
                units=buy.units,
                invested=buy.spent,
                entry_cost=buy.cost,
            )

        if cash < -IDENTITY_TOLERANCE:
            raise RuntimeError(f"내부 불변조건 위반: 현금이 음수입니다 - {cash:,.4f}원, 날짜 {date.date()}")

        # 5. 종가 마감 시점의 총자산을 곡선에 남긴다 (결정 C42).
        #    자산이 원화에서 달러로 바뀌는 것만으로는 총액이 변하지 않으므로,
        #    3번의 값에서 **매수 비용만큼만** 줄어 있어야 한다
        closing_usd_value = sum(slot.units for slot in held.values()) * close
        closing_total = cash + closing_usd_value
        _assert_cost_only_decline(total_assets, closing_total, cost=buy_cost, stage="매수", date=date)

        rows.append(
            {
                COL_DATE: date,
                COL_CLOSE_RATE: close,
                COL_RANGE_LOW: float(day[COL_RANGE_LOW]),
                COL_RANGE_HIGH: float(day[COL_RANGE_HIGH]),
                COL_REBALANCED: bool(day[COL_REBALANCED]),
                COL_ACTIVE_LEVELS: len(active),
                COL_HELD_SLOTS: len(held),
                COL_BUY_COUNT: len(plan.orders),
                COL_SELL_COUNT: len(sells),
                COL_BLOCKED_COUNT: len(plan.blocked_levels),
                COL_COST: sell_cost + buy_cost,
                COL_CASH: cash,
                COL_USD_VALUE: closing_usd_value,
                COL_TOTAL_ASSETS: closing_total,
            }
        )

    daily = pd.DataFrame(rows, columns=DAILY_COLUMNS)
    last_close = float(daily[COL_CLOSE_RATE].iloc[-1])
    open_slots = tuple(held[index] for index in sorted(held))
    open_invested = sum(slot.invested for slot in open_slots)
    # 미청산 슬롯은 강제 청산하지 않으므로 **청산 비용을 미리 빼지 않는다** (사양서 §8·결정 C8)
    open_value = sum(slot.units for slot in open_slots) * last_close

    logger.debug(
        f"그리드 실행 완료: {len(daily):,}거래일, 청산 {len(trades):,}건, "
        f"미청산 {len(open_slots):,}건, 최종 총자산 {daily[COL_TOTAL_ASSETS].iloc[-1]:,.0f}원"
    )

    return GridResult(
        daily=daily,
        trades=pd.DataFrame(trades, columns=TRADE_COLUMNS),
        open_slots=open_slots,
        open_invested=open_invested,
        open_value=open_value,
        open_unrealised=open_value - open_invested,
    )


def _assert_cost_only_decline(
    before: float,
    after: float,
    *,
    cost: float,
    stage: str,
    date: pd.Timestamp,
) -> None:
    """총자산이 **거래비용만큼만** 줄었는지 검사한다.

    자산이 원화에서 달러로 바뀌거나 그 반대로 바뀌는 것만으로는 총액이 변하지 않는다.
    변하는 것은 그때 실제로 나간 비용뿐이므로, 그 폭이 어긋나면 회계가 깨진 것이다.
    비용이 0이면 「전후 총자산이 같다」로 되돌아간다.

    Args:
        before: 단계 이전의 총자산
        after: 단계 이후의 총자산
        cost: 그 단계에서 발생한 거래비용
        stage: 예외 메시지에 쓸 단계 이름
        date: 검사한 거래일

    Raises:
        RuntimeError: 감소분이 비용과 다른 경우
    """
    expected = before - cost
    if abs(after - expected) > IDENTITY_TOLERANCE:
        raise RuntimeError(
            f"내부 불변조건 위반: {stage} 전후 총자산의 변화가 거래비용과 다릅니다 - "
            f"{stage} 전 {before:,.4f}원, {stage} 후 {after:,.4f}원, "
            f"비용 {cost:,.4f}원, 차이 {after - expected:,.4f}원, 날짜 {date.date()}"
        )


def _trade_row(slot: Slot, sell: SellOrder, *, growth_rate: float, anchor: float) -> dict[str, object]:
    """청산이 끝난 체결 하나를 표의 한 줄로 만든다.

    Args:
        slot: 청산된 슬롯
        sell: 매도 체결
        growth_rate: 익절폭 g (비율)
        anchor: 격자의 앵커 가격

    Returns:
        `TRADE_COLUMNS` 순서의 한 줄
    """
    return {
        "level_index": slot.level_index,
        "level_price": level_price(slot.level_index, growth_rate=growth_rate, anchor=anchor),
        "target_price": sell.target_price,
        "entry_date": slot.entry_date,
        "entry_price": slot.entry_price,
        "exit_date": sell.date,
        "exit_price": sell.price,
        "invested": sell.invested,
        "buy_cost": slot.entry_cost,
        "proceeds": sell.proceeds,
        "sell_cost": sell.cost,
        "realized": sell.realized,
        "grid_excess": sell.grid_excess,
        "hold_days": sell.hold_days,
    }
