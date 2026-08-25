"""그리드 실행 — 로딩·조립·표시용 프레임을 담당한다

이 모듈은 **매매 규칙을 계산하지 않는다.** 격자·범위·배분·체결·평가는 각 계층이 이미 하므로,
하는 일은 시세를 읽어 엔진에 넘기고 결과를 사람이 읽을 형태로 바꾸는 것이다.

**표시용 프레임을 한 번만 만든다.** 화면과 CSV 가 따로 가공하면 반올림 시점이 갈려
화면에서 본 숫자를 CSV 에서 찾지 못한다. 사용자가 직접 대조하는 것이 이 프로젝트의 전제다.
"""

from dataclasses import dataclass
from typing import Any

import pandas as pd

from verify_lab.common_constants import COL_DATE, PRICE_DECIMALS, SERIES_DIR
from verify_lab.data.loader import load_series_csv
from verify_lab.report.constants import DATE_FORMAT
from verify_lab.strategy.grid.constants import (
    COL_ACCRUED_INTEREST,
    COL_ACTIVE_LEVELS,
    COL_BLOCKED_COUNT,
    COL_BUY_COUNT,
    COL_CASH,
    COL_CLOSE_RATE,
    COL_COST,
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
    DISPLAY_ACCRUED_INTEREST,
    DISPLAY_ACTIVE_LEVELS,
    DISPLAY_BLOCKED_COUNT,
    DISPLAY_BUY_COST,
    DISPLAY_BUY_COUNT,
    DISPLAY_CASH,
    DISPLAY_CLOSE_RATE,
    DISPLAY_COST,
    DISPLAY_DATE,
    DISPLAY_ENTRY_DATE,
    DISPLAY_ENTRY_PRICE,
    DISPLAY_EXIT_DATE,
    DISPLAY_EXIT_PRICE,
    DISPLAY_GRID_EXCESS,
    DISPLAY_HELD_SLOTS,
    DISPLAY_HOLD_DAYS,
    DISPLAY_INVESTED,
    DISPLAY_LEVEL_INDEX,
    DISPLAY_LEVEL_PRICE,
    DISPLAY_PARKING_INTEREST,
    DISPLAY_PARKING_RATE,
    DISPLAY_PROCEEDS,
    DISPLAY_RANGE_HIGH,
    DISPLAY_RANGE_LOW,
    DISPLAY_REALIZED,
    DISPLAY_REBALANCED,
    DISPLAY_RP_INTEREST,
    DISPLAY_RP_RATE,
    DISPLAY_SELL_COST,
    DISPLAY_SELL_COUNT,
    DISPLAY_TARGET_PRICE,
    DISPLAY_TAX_PAID,
    DISPLAY_TOTAL_ASSETS,
    DISPLAY_USD_VALUE,
    INTEREST_TAX_RATE,
    TRADING_START_DATE,
)
from verify_lab.strategy.grid.engine import GridConfig, GridResult, run_grid
from verify_lab.strategy.grid.interest import build_rate_series
from verify_lab.strategy.grid.price_range import build_daily_ranges
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 판정·체결·평가의 기준 가격. 매매기준율이 아니라 **정규장 종가**다 (결정 C17·C19)
CLOSE_SERIES_FILENAME = "USDKRW_CLOSE.csv"

# 실수령 금리의 원지표. 달러는 미국 3개월 T-bill, 원화는 CD 91일물이다 (사양서 §11.1)
TBILL_SERIES_FILENAME = "DTB3.csv"
CD91_SERIES_FILENAME = "CD91.csv"

# 자본금은 정수 원 단위로 저장한다 (`.claude/rules/python.md` 반올림 규칙표)
CAPITAL_DECIMALS = 0

# 금리는 연 % 로 싣는다. 원지표가 소수 둘째 자리까지라 셋째 자리는 하한이 만든 값에서만 생긴다
RATE_DECIMALS = 3

# ============================================================
# summary.json 키
# ============================================================

KEY_STRATEGY = "strategy"
KEY_PARAMETERS = "parameters"
KEY_PERIOD = "period"
KEY_RESULT = "result"
KEY_ROW_COUNTS = "row_counts"
KEY_NOTES = "notes"

KEY_DAILY = "daily"
KEY_TRADES = "trades"

# 산출물만 보고는 알 수 없는 실행 조건
NOTE_SCOPE = "환전 경로 단독이다. 거래비용과 이자·세금이 반영됐으며 ETF 2종과 하단 이탈 B안은 다음 단계다"
NOTE_INTEREST = "이자는 세전으로 매일 총자산에 쌓이고 다음 달 첫 거래일에 인출하며 그때 15.4% 를 원천징수한다. " "RP 이자일수는 보유일수 − 1 이고 원화 파킹은 전일 잔고에 매일 붙는다"
NOTE_INTEREST_PATH = "월말 RP 이자 환전에는 환전 스프레드만 붙고 슬리피지는 붙지 않는다. " "슬리피지는 돌파 판정과 종가의 차이를 흡수한 값인데 이자 인출은 정해진 날의 정기 환전이다"
NOTE_RATE_SOURCE = (
    "금리는 원지표가 아니라 실수령 모델이다. 달러는 max(T-bill − 계단 스프레드, 하한), " "원화는 max(CD91 − 0.30%p, 하한)이며 원지표가 없는 날은 전일값을 이월했다"
)
NOTE_COST = "거래비용은 환전 스프레드와 슬리피지의 편도 합계이며 슬롯 금액(예산) 안에서 나간다. " "총자산은 그 비용만큼만 줄어들고 평가에는 비용을 적용하지 않는다"
NOTE_OPTIMISTIC = (
    "21년 백테스트에 오늘의 환전 우대율(90%)을 소급 적용하고 있다. 토스증권은 2021년 출범이라 " "2005~2020년에 이 조건이 존재할 수 없었으므로 환전 경로 비용은 전 기간에 걸쳐 낙관적이다"
)
NOTE_PRICE = "판정·체결·일별 시가평가가 모두 정규장 종가 기준이다. 매매기준율은 쓰지 않는다"
NOTE_UNREALISED = "총자산은 시가평가이며 미실현 평가손익이 들어 있다. 실현손익만 집계하면 곡선이 구조적으로 우상향한다"
NOTE_OPEN = "종료 시점의 미청산 슬롯은 강제 청산하지 않고 세전 시가평가로 남겼다"
NOTE_EXCESS = "이탈 보너스는 종가 체결 가정의 기여분이며 비용 전 명목 기준이다. " "지정가 운용도 같은 비용을 물므로 비용을 섞으면 사양서 §15.3 의 30% 판정이 다른 것을 재게 된다"

# 일별 곡선의 표시용 컬럼 번역표
DAILY_LABELS = {
    COL_DATE: DISPLAY_DATE,
    COL_CLOSE_RATE: DISPLAY_CLOSE_RATE,
    COL_RANGE_LOW: DISPLAY_RANGE_LOW,
    COL_RANGE_HIGH: DISPLAY_RANGE_HIGH,
    COL_REBALANCED: DISPLAY_REBALANCED,
    COL_ACTIVE_LEVELS: DISPLAY_ACTIVE_LEVELS,
    COL_HELD_SLOTS: DISPLAY_HELD_SLOTS,
    COL_BUY_COUNT: DISPLAY_BUY_COUNT,
    COL_SELL_COUNT: DISPLAY_SELL_COUNT,
    COL_BLOCKED_COUNT: DISPLAY_BLOCKED_COUNT,
    COL_COST: DISPLAY_COST,
    COL_RP_RATE: DISPLAY_RP_RATE,
    COL_PARKING_RATE: DISPLAY_PARKING_RATE,
    COL_RP_INTEREST: DISPLAY_RP_INTEREST,
    COL_PARKING_INTEREST: DISPLAY_PARKING_INTEREST,
    COL_ACCRUED_INTEREST: DISPLAY_ACCRUED_INTEREST,
    COL_TAX_PAID: DISPLAY_TAX_PAID,
    COL_CASH: DISPLAY_CASH,
    COL_USD_VALUE: DISPLAY_USD_VALUE,
    COL_TOTAL_ASSETS: DISPLAY_TOTAL_ASSETS,
}

# 체결 내역의 표시용 컬럼 번역표
TRADE_LABELS = {
    "level_index": DISPLAY_LEVEL_INDEX,
    "level_price": DISPLAY_LEVEL_PRICE,
    "target_price": DISPLAY_TARGET_PRICE,
    "entry_date": DISPLAY_ENTRY_DATE,
    "entry_price": DISPLAY_ENTRY_PRICE,
    "exit_date": DISPLAY_EXIT_DATE,
    "exit_price": DISPLAY_EXIT_PRICE,
    "invested": DISPLAY_INVESTED,
    "buy_cost": DISPLAY_BUY_COST,
    "proceeds": DISPLAY_PROCEEDS,
    "sell_cost": DISPLAY_SELL_COST,
    "realized": DISPLAY_REALIZED,
    "grid_excess": DISPLAY_GRID_EXCESS,
    "hold_days": DISPLAY_HOLD_DAYS,
}


@dataclass(frozen=True)
class GridOutputs:
    """실행 산출물

    Attributes:
        daily: 일별 총자산 곡선 (표시용 — 값이 이미 반올림돼 있다)
        trades: 체결 내역 (표시용)
        result: 엔진의 원값. 집계는 **이 값으로 한다** — 반올림된 표에서 다시 계산하면
            이중 반올림으로 합계가 어긋난다
        meta: 실행 파라미터와 핵심 수치
    """

    daily: pd.DataFrame
    trades: pd.DataFrame
    result: GridResult
    meta: dict[str, Any]


def run_usdkrw_grid(config: GridConfig, *, start_date: str = TRADING_START_DATE) -> GridOutputs:
    """원달러 그리드를 실행하고 표시용 산출물을 조립한다.

    Args:
        config: 실행 파라미터
        start_date: 매매 시작일 (`YYYY-MM-DD`)

    Returns:
        표시용 곡선·체결 내역과 원값·메타

    Raises:
        FileNotFoundError: 종가 시계열 파일이 없는 경우
        ValueError: 워밍업이 모자라거나 파라미터가 유효하지 않은 경우
    """
    series = load_series_csv(SERIES_DIR / CLOSE_SERIES_FILENAME)

    # 1. 범위표. **전 기간 시세를 넘기고 결과 행만 자른다** — 시세를 먼저 자르면 워밍업이 무너진다
    ranges = build_daily_ranges(
        series,
        start_date=pd.Timestamp(start_date),
        lookback_years=config.lookback_years,
        min_range_width=config.min_range_width,
    )

    # 2. 금리. **마스터 달력은 원달러 고시일**이며 원지표가 없는 날은 전일값을 이월한다 (결정 C14)
    rates = build_rate_series(
        pd.DatetimeIndex(ranges[COL_DATE]),
        tbill=load_series_csv(SERIES_DIR / TBILL_SERIES_FILENAME),
        cd91=load_series_csv(SERIES_DIR / CD91_SERIES_FILENAME),
        config=config.interest,
    )

    # 3. 엔진. 하향 돌파 판정에 직전 거래일 종가가 필요하므로 전 기간 시세를 함께 넘긴다
    result = run_grid(series, ranges, config=config, rates=rates)

    return GridOutputs(
        daily=_display_daily(result.daily),
        trades=_display_trades(result.trades),
        result=result,
        meta=_build_meta(result, config=config, start_date=start_date),
    )


def _display_daily(daily: pd.DataFrame) -> pd.DataFrame:
    """일별 곡선을 표시용으로 바꾼다.

    Args:
        daily: 엔진이 낸 원값

    Returns:
        한글 헤더에 반올림이 적용된 표
    """
    frame = daily.copy()
    frame[COL_DATE] = frame[COL_DATE].dt.strftime(DATE_FORMAT)
    frame = frame.round(
        {
            COL_CLOSE_RATE: PRICE_DECIMALS,
            COL_RANGE_LOW: PRICE_DECIMALS,
            COL_RANGE_HIGH: PRICE_DECIMALS,
            COL_COST: CAPITAL_DECIMALS,
            COL_RP_RATE: RATE_DECIMALS,
            COL_PARKING_RATE: RATE_DECIMALS,
            COL_RP_INTEREST: CAPITAL_DECIMALS,
            COL_PARKING_INTEREST: CAPITAL_DECIMALS,
            COL_ACCRUED_INTEREST: CAPITAL_DECIMALS,
            COL_TAX_PAID: CAPITAL_DECIMALS,
            COL_CASH: CAPITAL_DECIMALS,
            COL_USD_VALUE: CAPITAL_DECIMALS,
            COL_TOTAL_ASSETS: CAPITAL_DECIMALS,
        }
    )

    return frame.rename(columns=DAILY_LABELS)


def _display_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """체결 내역을 표시용으로 바꾼다.

    사용자가 차트로 직접 대조할 원자료이므로 **날짜와 가격을 그대로 싣는다.**

    Args:
        trades: 엔진이 낸 원값

    Returns:
        한글 헤더에 반올림이 적용된 표
    """
    frame = trades.copy()
    if frame.empty:
        return frame.rename(columns=TRADE_LABELS)

    for column in ("entry_date", "exit_date"):
        frame[column] = pd.to_datetime(frame[column]).dt.strftime(DATE_FORMAT)

    frame = frame.round(
        {
            "level_price": PRICE_DECIMALS,
            "target_price": PRICE_DECIMALS,
            "entry_price": PRICE_DECIMALS,
            "exit_price": PRICE_DECIMALS,
            "invested": CAPITAL_DECIMALS,
            "buy_cost": CAPITAL_DECIMALS,
            "proceeds": CAPITAL_DECIMALS,
            "sell_cost": CAPITAL_DECIMALS,
            "realized": CAPITAL_DECIMALS,
            "grid_excess": CAPITAL_DECIMALS,
        }
    )

    return frame.rename(columns=TRADE_LABELS)


def _build_meta(result: GridResult, *, config: GridConfig, start_date: str) -> dict[str, Any]:
    """실행 파라미터와 핵심 수치를 모은다.

    Args:
        result: 엔진의 원값
        config: 실행 파라미터
        start_date: 매매 시작일

    Returns:
        `summary.json` 에 담을 내용
    """
    daily = result.daily
    trades = result.trades
    first = float(daily[COL_TOTAL_ASSETS].iloc[0])
    last = float(daily[COL_TOTAL_ASSETS].iloc[-1])
    realized = float(trades["realized"].sum()) if not trades.empty else 0.0
    grid_excess = float(trades["grid_excess"].sum()) if not trades.empty else 0.0

    # 비용은 **일별 곡선**에서 합산한다. 체결 표는 청산이 끝난 것만 담고 있어
    # 미청산 슬롯의 매수 비용이 빠진다
    cost_total = float(daily[COL_COST].sum())
    buy_cost = float(trades["buy_cost"].sum()) if not trades.empty else 0.0
    sell_cost = float(trades["sell_cost"].sum()) if not trades.empty else 0.0

    rp_interest = float(daily[COL_RP_INTEREST].sum())
    parking_interest = float(daily[COL_PARKING_INTEREST].sum())
    tax_paid = float(daily[COL_TAX_PAID].sum())

    return {
        KEY_STRATEGY: "usdkrw_grid",
        KEY_PARAMETERS: {
            "lookback_years": config.lookback_years,
            "growth_rate": config.growth_rate,
            "min_range_width": config.min_range_width,
            "allocation_spread": config.allocation_spread,
            "slot_cap_ratio": config.slot_cap_ratio,
            "initial_capital": round(config.initial_capital, CAPITAL_DECIMALS),
            "exchange_spread_rate": config.cost.exchange_spread_rate,
            "slippage_rate": config.cost.slippage_rate,
            "round_trip_cost_rate": round(2.0 * (config.cost.exchange_spread_rate + config.cost.slippage_rate), 6),
            "rp_floor_rate": config.interest.rp_floor_rate,
            "parking_floor_rate": config.interest.parking_floor_rate,
            "interest_tax_rate": INTEREST_TAX_RATE,
            "anchor": config.anchor,
            "start_date": start_date,
        },
        KEY_PERIOD: {
            "first_date": daily[COL_DATE].iloc[0].strftime(DATE_FORMAT),
            "last_date": daily[COL_DATE].iloc[-1].strftime(DATE_FORMAT),
            "trading_days": int(len(daily)),
            "rebalance_count": int(daily[COL_REBALANCED].sum()),
        },
        KEY_RESULT: {
            "first_total_assets": round(first, CAPITAL_DECIMALS),
            "last_total_assets": round(last, CAPITAL_DECIMALS),
            "total_return_rate": round((last / first) - 1.0, 6),
            "closed_trades": int(len(trades)),
            "realized_total": round(realized, CAPITAL_DECIMALS),
            "cost_total": round(cost_total, CAPITAL_DECIMALS),
            "buy_cost_total": round(buy_cost, CAPITAL_DECIMALS),
            "sell_cost_total": round(sell_cost, CAPITAL_DECIMALS),
            "rp_interest_total": round(rp_interest, CAPITAL_DECIMALS),
            "parking_interest_total": round(parking_interest, CAPITAL_DECIMALS),
            "interest_total": round(rp_interest + parking_interest, CAPITAL_DECIMALS),
            "tax_paid_total": round(tax_paid, CAPITAL_DECIMALS),
            "open_accrued_interest": round(result.open_accrued_interest, CAPITAL_DECIMALS),
            "rp_rate_mean": round(float(daily[COL_RP_RATE].mean()), RATE_DECIMALS),
            "parking_rate_mean": round(float(daily[COL_PARKING_RATE].mean()), RATE_DECIMALS),
            "rp_rate_filled_days": result.rp_filled,
            "parking_rate_filled_days": result.parking_filled,
            "grid_excess_total": round(grid_excess, CAPITAL_DECIMALS),
            "grid_excess_share_of_realized": round(grid_excess / realized, 6) if realized else None,
            "open_slots": int(len(result.open_slots)),
            "open_invested": round(result.open_invested, CAPITAL_DECIMALS),
            "open_value": round(result.open_value, CAPITAL_DECIMALS),
            "open_unrealised": round(result.open_unrealised, CAPITAL_DECIMALS),
            "buy_fills": int(daily[COL_BUY_COUNT].sum()),
            "sell_fills": int(daily[COL_SELL_COUNT].sum()),
            "blocked_days": int((daily[COL_BLOCKED_COUNT] > 0).sum()),
            "active_levels_min": int(daily[COL_ACTIVE_LEVELS].min()),
            "active_levels_max": int(daily[COL_ACTIVE_LEVELS].max()),
            "held_slots_max": int(daily[COL_HELD_SLOTS].max()),
        },
        KEY_ROW_COUNTS: {KEY_DAILY: int(len(daily)), KEY_TRADES: int(len(trades))},
        KEY_NOTES: [
            NOTE_SCOPE,
            NOTE_COST,
            NOTE_INTEREST,
            NOTE_INTEREST_PATH,
            NOTE_RATE_SOURCE,
            NOTE_PRICE,
            NOTE_UNREALISED,
            NOTE_OPEN,
            NOTE_EXCESS,
            NOTE_OPTIMISTIC,
        ],
    }
