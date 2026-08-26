"""시뮬레이션 루프와 일별 시가평가

조각 넷(격자·범위·배분·체결)을 하루씩 돌려 **일별 총자산 곡선**을 낸다.
그 곡선이 모든 매매법의 공통 산출물이며, 표준 지표는 곡선 하나만 받는 함수가 계산한다.

하루의 처리 순서는 **이자 → 월말 정산 → 매도 → 총자산 평가 → 슬롯 금액 → 매수** 다.
매도로 나온 현금을 같은 날 매수에 쓸 수 있어야 자연스럽기 때문인데, **한 거래일에 매수와 매도가
함께 일어날 수 없어** 그 둘의 순서가 결과를 바꾸지는 않는다 — 매수는 종가 하락을, 매도는 종가
상승을 각각 함의한다.

**이자가 맨 앞에 오는 것은 이자일수 −1 때문이다.** 사양서 §9.1 의 「이자일수 = 보유일수 − 1」은
매도일을 알아야 계산되는데, 그러면 미래를 보게 된다. 이자를 매도·매수보다 먼저 얹고 각 거래일에
`[전거래일, 오늘) 중 매수일을 뺀 날 수` 만큼만 주면, 매수는 이자 뒤에 일어나 매수 당일이 빠지고
매도도 이자 뒤라 매도 당일이 빠진다. 합계가 정확히 `(매도일 − 매수일) − 1` 이 되며 **미래를
보지 않는다.**

```
총자산 = 원화현금 + Σ(슬롯 보유 단위 × 당일 집행가) + 미인출 이자
```

**판정 가격과 집행 가격이 다르다.** 격자·범위·하향 돌파·목표가는 **원달러 종가**로 판정하고
(결정 C1·C17), 체결과 평가는 **경로의 집행 가격**으로 한다. 환전 경로는 둘이 같고 ETF 경로는
갈라진다. 단일 정의라야 세 경로가 **같은 날 같은 판정**을 받아 대체 가능성 비교가 성립한다.
**미인출 RP 이자만은 달러라 언제나 원달러 종가로 환산**한다.

**미실현 평가손익을 반드시 반영한다.** 실현손익만 집계하면 그리드 곡선은 **구조적으로 항상
우상향한다** — 매도는 무조건 이익 실현이고 손실은 미실현으로 잔류하기 때문이다.
사양서 §8 이 "2009~2014 하락장에서도 실현 기준 곡선은 예쁘게 올라가지만 실제 계좌는 반토막"
이라고 적은 것이 이 사고다.

**총자산은 거래비용만큼만 줄어든다.** 매도 전후와 매수 전후를 각각 검사하며, 감소분이
그때 발생한 비용과 다르면 회계가 깨진 것이므로 즉시 중단한다. 자산이 원화에서 달러로 바뀌는
것만으로는 총액이 변하지 않아야 한다.

**평가에는 비용을 적용하지 않는다** (사양서 §8). 매일 청산 비용을 차감하면 미실현 손실이
과대계상돼 MDD 가 오염된다. 비용은 **실제 체결 시점에만** 발생한다.

**이자는 세전으로 매일 쌓이고 세금은 지급 시 뗀다** (결정 C7). 달러 RP 이자는 달러로,
원화 파킹 이자는 원화로 쌓이며 **총자산에는 즉시 반영**된다 — 월말에만 반영하면 곡선에 계단이
생겨 MDD·Sharpe 가 왜곡된다. 쌓인 이자는 **다음 달 첫 거래일**에 인출되고 그때 15.4% 를
원천징수하며, RP 쪽은 환전을 거치되 **슬리피지는 붙지 않는다** — 돌파 판정이 아니라
정해진 날의 정기 환전이라 「15:20 판정과 종가의 차이」라는 성격이 없다.

**미인출 이자는 매수에 쓸 수 없다.** 총자산에는 들어가지만 현금이 아니므로 슬롯 금액의
분모는 키우고 실제 체결 여력은 키우지 않는다 — 실제 계좌에서도 미지급 이자는 그렇다.

**하단 이탈 B안은 활성 레벨만 늘린다.** 범위표가 준 연장 하단이 정식 하단보다 낮은 날에는
격자를 그 가격을 감싸는 레벨까지 늘려 켠다. **위치와 배수는 여전히 정식 범위로 잰다** —
연장 하단으로 재면 3구간 경계가 통째로 이동해 상단부 레벨이 중간부로 내려앉는다.
연장 레벨은 위치가 음수라 하단부 배수를 받으며 특별 취급이 없다.

**판정식은 그대로다.** 연장으로 켜진 레벨도 하향 돌파로만 사므로 매수는 여전히 종가 하락을
함의하고, 격자가 영구 고정이라 목표가와 매도 조건도 바뀌지 않는다. 그래서
**한 거래일에 매수와 매도가 함께 일어나지 않는다**는 불변조건이 B안에서도 성립한다.
"""

from dataclasses import dataclass, field, replace

import pandas as pd

from verify_lab.common_constants import COL_DATE, COL_VALUE
from verify_lab.data.loader import validate_market_frame
from verify_lab.strategy.grid.allocation import allocate_slots
from verify_lab.strategy.grid.constants import (
    COL_ACCRUED_INTEREST,
    COL_ACTIVE_LEVELS,
    COL_BLOCKED_COUNT,
    COL_BUY_AMOUNT,
    COL_BUY_COUNT,
    COL_CAPPED_LEVELS,
    COL_CASH,
    COL_CLOSE_RATE,
    COL_COST,
    COL_EXEC_PRICE,
    COL_EXTENDED_LEVELS,
    COL_EXTENDED_LOW,
    COL_GAIN_TAX,
    COL_HELD_INVESTED,
    COL_HELD_SLOTS,
    COL_PARKING_INTEREST,
    COL_PARKING_RATE,
    COL_RANGE_HIGH,
    COL_RANGE_LOW,
    COL_REBALANCED,
    COL_RP_INTEREST,
    COL_RP_RATE,
    COL_SELL_COUNT,
    COL_TAX_PAID,
    COL_TOTAL_ASSETS,
    COL_USD_VALUE,
    DAYS_PER_YEAR,
    GRID_ANCHOR_PRICE,
    INTEREST_TAX_RATE,
    PERCENT_TO_RATE,
)
from verify_lab.strategy.grid.execution import SellOrder, Slot, plan_buys, plan_sells
from verify_lab.strategy.grid.interest import InterestConfig, RateSeries
from verify_lab.strategy.grid.lattice import active_level_indices, enclosing_level_index, level_price
from verify_lab.strategy.grid.paths.base import CostConfig, ExecutionPath
from verify_lab.strategy.grid.paths.exchange import ExchangePath
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 범위표가 반드시 가져야 하는 컬럼
DAILY_RANGE_REQUIRED = [COL_DATE, COL_RANGE_LOW, COL_RANGE_HIGH, COL_EXTENDED_LOW, COL_REBALANCED]

# 일별 곡선의 컬럼 순서
DAILY_COLUMNS = [
    COL_DATE,
    COL_CLOSE_RATE,
    COL_EXEC_PRICE,
    COL_RANGE_LOW,
    COL_RANGE_HIGH,
    COL_REBALANCED,
    COL_ACTIVE_LEVELS,
    COL_HELD_SLOTS,
    COL_BUY_COUNT,
    COL_SELL_COUNT,
    COL_BLOCKED_COUNT,
    COL_BUY_AMOUNT,
    COL_CAPPED_LEVELS,
    COL_EXTENDED_LEVELS,
    COL_HELD_INVESTED,
    COL_COST,
    COL_RP_RATE,
    COL_PARKING_RATE,
    COL_RP_INTEREST,
    COL_PARKING_INTEREST,
    COL_ACCRUED_INTEREST,
    COL_TAX_PAID,
    COL_GAIN_TAX,
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
    "entry_rate",
    "entry_price",
    "exit_date",
    "exit_rate",
    "exit_price",
    "invested",
    "buy_cost",
    "proceeds",
    "sell_cost",
    "sell_tax",
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
        interest: 이자 파라미터
        anchor: 격자의 앵커 가격
    """

    lookback_years: int
    growth_rate: float
    min_range_width: float
    allocation_spread: float
    slot_cap_ratio: float
    initial_capital: float
    cost: CostConfig
    interest: InterestConfig
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
        open_accrued_interest: 종료 시점에 아직 인출되지 않은 이자 (원, **세전**).
            결정 C8 의 세전 평가와 같은 정신이며 총자산에는 이미 들어 있다
        rp_filled: T-bill 원지표가 없어 전일값을 이월한 거래일 수
        parking_filled: CD91 원지표가 없어 전일값을 이월한 거래일 수
        bought_units: 전 기간 매수로 취득한 보유 단위 합계 (환전은 달러, ETF 는 주식 수)
        bought_invested: 그 매수에 실제로 나간 원화 합계 (**비용 포함**).
            둘의 비가 **평균단가**이며 사양서 §7 의 「A안 대비 평균단가 개선폭」이 그것으로 판정한다.
            체결표에서 역산하면 나눗셈이 하나 늘고 그것이 두 번째 판정식이 되므로 여기서 누적한다
    """

    daily: pd.DataFrame
    trades: pd.DataFrame
    open_slots: tuple[Slot, ...]
    open_invested: float
    open_value: float
    open_unrealised: float = field(default=0.0)
    open_accrued_interest: float = field(default=0.0)
    rp_filled: int = field(default=0)
    parking_filled: int = field(default=0)
    bought_units: float = field(default=0.0)
    bought_invested: float = field(default=0.0)


def run_grid(
    series: pd.DataFrame,
    ranges: pd.DataFrame,
    *,
    config: GridConfig,
    rates: RateSeries,
    path: ExecutionPath,
    exec_prices: pd.Series | None = None,
    sell_enabled: bool = True,
) -> GridResult:
    """그리드를 하루씩 돌려 일별 총자산 곡선과 체결 내역을 낸다.

    **전 기간 시세를 넘긴다.** 매매 시작일의 하향 돌파 판정에 직전 거래일 종가가 필요한데,
    시세를 먼저 잘라 넘기면 그 값이 사라진다. 결과 행은 `ranges` 의 거래일에 맞춰진다.

    Args:
        series: 일별 단일 값 시계열 **전 기간** (`load_series_csv` 가 돌려준 형태)
        ranges: 거래일별 범위표 (`build_daily_ranges` 가 돌려준 형태)
        config: 실행 파라미터
        rates: `ranges` 의 거래일에 맞춘 실수령 금리 계열
        path: 집행 경로. 사고파는 방법과 세금·보유 이자율을 정한다
        exec_prices: `ranges` 의 거래일에 맞춘 **집행 가격**. 넘기지 않으면 판정 가격(원달러 종가)을
            그대로 쓴다 — 환전 경로가 그렇다
        sell_enabled: 목표가에 닿은 슬롯을 팔지 여부. **끄면 사양서 §13.3 의 「분할매수 후 보유」**가
            된다 — 매수·배분·판정이 같은 코드를 그대로 지나므로 **익절 로직만 분리된다** (결정 C11)

    Returns:
        일별 곡선·체결 내역·미청산 슬롯

    Raises:
        ValueError: 입력이 비었거나, 컬럼이 없거나, 범위표의 거래일이 시세에 없거나,
            금리 계열이 범위표와 어긋나는 경우
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

    if len(rates.rp) != len(ranges) or len(rates.parking) != len(ranges):
        raise ValueError(
            f"금리 계열의 길이가 범위표와 다릅니다: 범위표 {len(ranges):,}행, " f"RP {len(rates.rp):,}행, 파킹 {len(rates.parking):,}행"
        )

    if exec_prices is not None and len(exec_prices) != len(ranges):
        raise ValueError(f"집행 가격 계열의 길이가 범위표와 다릅니다: 범위표 {len(ranges):,}행, 집행가 {len(exec_prices):,}행")

    # 월말 이자 환전에는 **슬리피지가 붙지 않는다.** 슬리피지는 사양서 §6.6 의
    # 「15:20 판정과 종가의 차이」를 흡수한 값인데, 이자 인출은 돌파 판정이 아니라
    # 정해진 날에 하는 정기 환전이라 그 성격이 없다
    interest_path = ExchangePath(replace(config.cost, slippage_rate=0.0))

    cash = config.initial_capital
    held: dict[int, Slot] = {}
    rows: list[dict[str, object]] = []
    trades: list[dict[str, object]] = []

    # 아직 인출되지 않은 세전 이자. RP 는 달러로, 파킹은 원화로 쌓인다
    accrued_rp_usd = 0.0
    accrued_parking = 0.0

    # 파킹 이자의 기준 잔고는 **전 거래일 마감 원화현금**이다. 첫날은 이자가 없다
    previous_cash = 0.0

    # 평균단가의 재료. 청산 여부와 무관하게 **모든 매수**를 센다
    bought_units = 0.0
    bought_invested = 0.0

    for offset, (_, day) in enumerate(ranges.iterrows()):
        date = pd.Timestamp(day[COL_DATE])
        position = int(positions[offset])
        close = float(closes.iloc[position])
        previous_close = float(closes.iloc[position - 1])
        previous_date = pd.Timestamp(closes.index[position - 1])
        elapsed_days = int((date - previous_date).days)

        # 집행 가격. 환전 경로는 판정 가격과 같고 ETF 경로는 수정 종가다
        exec_price = close if exec_prices is None else float(exec_prices.iloc[offset])
        if exec_price <= 0:
            raise ValueError(f"집행 가격은 양수여야 합니다: {exec_price}, 날짜 {date.date()}")

        rp_rate_pct = float(rates.rp.iloc[offset])
        parking_rate_pct = float(rates.parking.iloc[offset])

        # 1. 이자. **매도·매수보다 먼저**라야 이자일수 −1 이 미래를 보지 않고 성립한다.
        #    매수는 이자 뒤에 일어나 매수 당일이 빠지고, 매도도 이자 뒤라 매도 당일이 빠진다
        opening_total = (
            cash + sum(slot.units for slot in held.values()) * exec_price + accrued_rp_usd * close + accrued_parking
        )

        # **보유 이자율은 경로가 정한다.** ETF 는 캐리가 종가에 내재돼 0 을 돌려주므로
        # 이 식 하나가 세 경로에 그대로 쓰인다 — 엔진에 경로 분기를 만들지 않는다 (사양서 §15.2 #4)
        holding_rate = path.holding_interest_rate(rp_rate_pct)
        rp_interest_usd = (
            sum(
                slot.units
                * (holding_rate / PERCENT_TO_RATE)
                * interest_days(entry_date=slot.entry_date, date=date, previous=previous_date)
                for slot in held.values()
            )
            / DAYS_PER_YEAR
        )
        parking_interest = previous_cash * (parking_rate_pct / PERCENT_TO_RATE) * elapsed_days / DAYS_PER_YEAR

        accrued_rp_usd += rp_interest_usd
        accrued_parking += parking_interest

        after_interest = (
            cash + sum(slot.units for slot in held.values()) * exec_price + accrued_rp_usd * close + accrued_parking
        )
        _assert_balance_change(
            opening_total, after_interest, change=rp_interest_usd * close + parking_interest, stage="이자", date=date
        )

        # 2. 월말 정산. **다음 달 첫 거래일**에 전월분을 인출하고 15.4% 를 원천징수한다.
        #    「마지막 거래일」로 잡으면 그 판정에 다음 행이 필요해 미래를 보게 된다
        tax_paid = 0.0
        interest_cost = 0.0
        if is_settlement_day(date, previous=previous_date):
            liquidation = interest_path.liquidate(accrued_rp_usd, price=close)
            rp_gross = liquidation.notional
            interest_cost = liquidation.cost

            # 세금은 **세전 이자**에 붙는다. 환전 비용은 과세 대상이 아니라 별도 지출이다
            tax_paid = (rp_gross + accrued_parking) * INTEREST_TAX_RATE
            cash += rp_gross - interest_cost + accrued_parking - tax_paid

            accrued_rp_usd = 0.0
            accrued_parking = 0.0

            after_settlement = (
                cash + sum(slot.units for slot in held.values()) * exec_price + accrued_rp_usd * close + accrued_parking
            )
            _assert_balance_change(
                after_interest, after_settlement, change=-(tax_paid + interest_cost), stage="이자 정산", date=date
            )

        # 3. 매도. 목표가에 닿은 슬롯을 전부 청산하고 현금을 회수한다.
        #    매도 전 총자산을 먼저 재 두는 것은 감소분이 매도 비용과 같은지 검사하기 위해서다
        opening_total = (
            cash + sum(slot.units for slot in held.values()) * exec_price + accrued_rp_usd * close + accrued_parking
        )
        sells = (
            plan_sells(
                list(held.values()),
                close=close,
                exec_price=exec_price,
                date=date,
                growth_rate=config.growth_rate,
                path=path,
                anchor=config.anchor,
            )
            if sell_enabled
            else ()
        )
        sell_cost = 0.0
        gain_tax = 0.0
        for sell in sells:
            slot = held.pop(sell.level_index)
            cash += sell.proceeds
            sell_cost += sell.cost
            gain_tax += sell.tax
            trades.append(_trade_row(slot, sell, growth_rate=config.growth_rate, anchor=config.anchor))

        # 4. 총자산 평가. **매수 직전의 값**이며 사양서 §5.2 가 요구하는 "매일 종가 확정 후" 다.
        #    **미인출 이자도 총자산에 들어간다** — 현금은 아니지만 이미 내 것이다 (결정 C7)
        usd_value = sum(slot.units for slot in held.values()) * exec_price
        accrued_value = accrued_rp_usd * close + accrued_parking
        total_assets = cash + usd_value + accrued_value
        _assert_balance_change(opening_total, total_assets, change=-(sell_cost + gain_tax), stage="매도", date=date)

        # 5. 활성 레벨과 슬롯 금액. 분모는 활성 레벨 전체이며 보유분을 포함한다 (결정 C4).
        #    하단 이탈 B안은 격자를 **연장 하단을 감싸는 레벨까지** 아래로 늘린다.
        #    A안이면 연장 하단이 정식 하단과 같아 이 분기가 아무 일도 하지 않는다
        low = float(day[COL_RANGE_LOW])
        high = float(day[COL_RANGE_HIGH])
        extended_low = float(day[COL_EXTENDED_LOW])

        grid_low = low
        if extended_low < low:
            grid_low = level_price(
                enclosing_level_index(extended_low, growth_rate=config.growth_rate, anchor=config.anchor),
                growth_rate=config.growth_rate,
                anchor=config.anchor,
            )

        active = active_level_indices(grid_low, high, growth_rate=config.growth_rate, anchor=config.anchor)
        extended_levels = sum(
            1 for index in active if level_price(index, growth_rate=config.growth_rate, anchor=config.anchor) < low
        )

        # **위치와 배수는 정식 범위로 잰다.** 연장 하단으로 재면 3구간 경계가 통째로 이동해
        # 상단부 레벨이 중간부로 내려앉는다 — 연장 레벨은 위치가 음수라 하단부 배수를 받는다
        allocation = allocate_slots(
            active,
            low=low,
            high=high,
            total_assets=total_assets,
            growth_rate=config.growth_rate,
            anchor=config.anchor,
            spread=config.allocation_spread,
            slot_cap_ratio=config.slot_cap_ratio,
        )

        # 6. 매수. 하향 돌파한 미보유 레벨을 아래(싼) 쪽부터 현금이 닿는 데까지 산다.
        #    **미인출 이자는 쓸 수 없다** — 현금만 넘긴다
        plan = plan_buys(
            active,
            list(held),
            previous_close=previous_close,
            close=close,
            exec_price=exec_price,
            amounts=allocation.amounts,
            cash=cash,
            date=date,
            growth_rate=config.growth_rate,
            path=path,
            anchor=config.anchor,
        )
        buy_cost = 0.0
        buy_amount = 0.0
        for buy in plan.orders:
            if buy.level_index in held:
                raise RuntimeError(f"내부 불변조건 위반: 이미 보유한 레벨을 다시 샀습니다 - 레벨 {buy.level_index}, 날짜 {date.date()}")

            # 현금은 **배정된 예산이 아니라 실제로 나간 금액**만큼 줄어든다.
            # 경로가 예산을 다 쓰지 못할 수 있어 둘은 같은 값이 아니다
            cash -= buy.spent
            buy_cost += buy.cost
            buy_amount += buy.spent
            bought_units += buy.units
            bought_invested += buy.spent
            held[buy.level_index] = Slot(
                level_index=buy.level_index,
                entry_date=date,
                entry_price=buy.price,
                entry_rate=buy.rate,
                units=buy.units,
                invested=buy.spent,
                entry_cost=buy.cost,
            )

        if cash < -IDENTITY_TOLERANCE:
            raise RuntimeError(f"내부 불변조건 위반: 현금이 음수입니다 - {cash:,.4f}원, 날짜 {date.date()}")

        # 7. 종가 마감 시점의 총자산을 곡선에 남긴다 (결정 C42).
        #    자산이 원화에서 달러로 바뀌는 것만으로는 총액이 변하지 않으므로,
        #    평가 시점의 값에서 **매수 비용만큼만** 줄어 있어야 한다
        closing_usd_value = sum(slot.units for slot in held.values()) * exec_price
        closing_accrued = accrued_rp_usd * close + accrued_parking
        closing_total = cash + closing_usd_value + closing_accrued
        _assert_balance_change(total_assets, closing_total, change=-buy_cost, stage="매수", date=date)

        rows.append(
            {
                COL_DATE: date,
                COL_CLOSE_RATE: close,
                COL_EXEC_PRICE: exec_price,
                COL_RANGE_LOW: low,
                COL_RANGE_HIGH: high,
                COL_REBALANCED: bool(day[COL_REBALANCED]),
                COL_ACTIVE_LEVELS: len(active),
                COL_HELD_SLOTS: len(held),
                COL_BUY_COUNT: len(plan.orders),
                COL_SELL_COUNT: len(sells),
                COL_BLOCKED_COUNT: len(plan.blocked_levels),
                COL_BUY_AMOUNT: buy_amount,
                COL_CAPPED_LEVELS: len(allocation.capped_levels),
                COL_EXTENDED_LEVELS: extended_levels,
                COL_HELD_INVESTED: sum(slot.invested for slot in held.values()),
                COL_COST: sell_cost + buy_cost + interest_cost,
                COL_RP_RATE: rp_rate_pct,
                COL_PARKING_RATE: parking_rate_pct,
                COL_RP_INTEREST: rp_interest_usd * close,
                COL_PARKING_INTEREST: parking_interest,
                COL_ACCRUED_INTEREST: closing_accrued,
                COL_TAX_PAID: tax_paid,
                COL_GAIN_TAX: gain_tax,
                COL_CASH: cash,
                COL_USD_VALUE: closing_usd_value,
                COL_TOTAL_ASSETS: closing_total,
            }
        )

        previous_cash = cash

    daily = pd.DataFrame(rows, columns=DAILY_COLUMNS)
    last_close = float(daily[COL_CLOSE_RATE].iloc[-1])
    last_exec = float(daily[COL_EXEC_PRICE].iloc[-1])
    open_slots = tuple(held[index] for index in sorted(held))
    open_invested = sum(slot.invested for slot in open_slots)
    # 미청산 슬롯은 강제 청산하지 않으므로 **청산 비용과 세금을 미리 빼지 않는다** (사양서 §8·결정 C8)
    open_value = sum(slot.units for slot in open_slots) * last_exec

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
        open_accrued_interest=accrued_rp_usd * last_close + accrued_parking,
        rp_filled=rates.rp_filled,
        parking_filled=rates.parking_filled,
        bought_units=bought_units,
        bought_invested=bought_invested,
    )


def interest_days(*, entry_date: pd.Timestamp, date: pd.Timestamp, previous: pd.Timestamp) -> int:
    """보유분 하나가 오늘 받을 RP 이자의 달력일 수를 낸다.

    구간은 `[전거래일, 오늘)` 이고 **매수일은 빠진다.** 매수·매도가 이자보다 뒤에 처리되므로
    매수 당일과 매도 당일이 자동으로 제외되며, 전 구간을 더하면 정확히
    `(매도일 − 매수일) − 1` 이 된다 (사양서 §9.1). **미래를 보지 않는다.**

    **벤치마크도 이 함수를 부른다.** 규칙을 복제하면 이자일수 −1 이 두 곳에서 조용히 갈라진다.

    Args:
        entry_date: 그 보유분을 산 날
        date: 오늘 거래일
        previous: 직전 거래일

    Returns:
        이자가 붙는 달력일 수 (0 이상)
    """
    elapsed = int((date - previous).days)
    since_entry = int((date - entry_date).days)

    # 매수일이 직전 거래일보다 앞이면 구간 전체가 이자 대상이고,
    # 직전 거래일에 샀다면 그날 하루가 빠진다. 매수일은 직전 거래일보다 뒤일 수 없다
    return max(0, min(elapsed, since_entry - 1))


def is_settlement_day(date: pd.Timestamp, *, previous: pd.Timestamp) -> bool:
    """오늘이 **전월분 이자를 인출하는 날**인지 답한다 (사양서 §9.1 의 「월말」).

    판정은 **「다음 달 첫 거래일」** 이다 (결정 C58). 「그 달의 마지막 거래일」로 잡으면
    그 판정에 다음 행이 필요해 **미래를 보게 되고**, 시세를 월 중간에서 자르면
    마지막 날이 월말로 오판된다. 현실에서도 월말 이자는 다음 영업일에 입금된다.

    Args:
        date: 오늘 거래일
        previous: 직전 거래일

    Returns:
        달이 바뀌었으면 `True`
    """
    return date.year != previous.year or date.month != previous.month


def _assert_balance_change(
    before: float,
    after: float,
    *,
    change: float,
    stage: str,
    date: pd.Timestamp,
) -> None:
    """총자산이 **예상한 만큼만** 움직였는지 검사한다.

    자산이 원화에서 달러로 바뀌거나 그 반대로 바뀌는 것만으로는 총액이 변하지 않는다.
    변하는 것은 그때 발생한 이자(증가)와 비용·세금(감소)뿐이므로, 그 폭이 어긋나면 회계가 깨진 것이다.
    이자도 비용도 0이면 「전후 총자산이 같다」로 되돌아간다.

    Args:
        before: 단계 이전의 총자산
        after: 단계 이후의 총자산
        change: 그 단계에서 예상되는 변화량. 이자는 양수, 비용·세금은 음수다
        stage: 예외 메시지에 쓸 단계 이름
        date: 검사한 거래일

    Raises:
        RuntimeError: 변화량이 예상과 다른 경우
    """
    expected = before + change
    if abs(after - expected) > IDENTITY_TOLERANCE:
        raise RuntimeError(
            f"내부 불변조건 위반: {stage} 전후 총자산의 변화가 예상과 다릅니다 - "
            f"{stage} 전 {before:,.4f}원, {stage} 후 {after:,.4f}원, "
            f"예상 변화 {change:,.4f}원, 차이 {after - expected:,.4f}원, 날짜 {date.date()}"
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
        "entry_rate": slot.entry_rate,
        "entry_price": slot.entry_price,
        "exit_date": sell.date,
        "exit_rate": sell.rate,
        "exit_price": sell.price,
        "invested": sell.invested,
        "buy_cost": slot.entry_cost,
        "proceeds": sell.proceeds,
        "sell_cost": sell.cost,
        "sell_tax": sell.tax,
        "realized": sell.realized,
        "grid_excess": sell.grid_excess,
        "hold_days": sell.hold_days,
    }
