"""그리드 실행 — 로딩·조립·표시용 프레임을 담당한다

이 모듈은 **매매 규칙을 계산하지 않는다.** 격자·범위·배분·체결·평가는 각 계층이 이미 하므로,
하는 일은 시세를 읽어 엔진에 넘기고 결과를 사람이 읽을 형태로 바꾸는 것이다.

**표시용 프레임을 한 번만 만든다.** 화면과 CSV 가 따로 가공하면 반올림 시점이 갈려
화면에서 본 숫자를 CSV 에서 찾지 못한다. 사용자가 직접 대조하는 것이 이 프로젝트의 전제다.
"""

from dataclasses import dataclass
from typing import Any

import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE, MARKET_DIR, PRICE_DECIMALS, SERIES_DIR
from verify_lab.data.loader import load_market_csv, load_series_csv
from verify_lab.report.constants import DATE_FORMAT
from verify_lab.strategy.grid.constants import (
    COL_ACCRUED_INTEREST,
    COL_ACTIVE_LEVELS,
    COL_BLOCKED_COUNT,
    COL_BUY_COUNT,
    COL_CASH,
    COL_CLOSE_RATE,
    COL_COST,
    COL_EXEC_PRICE,
    COL_EXTENDED_LEVELS,
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
    DEFAULT_LOWER_BREACH,
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
    DISPLAY_ENTRY_RATE,
    DISPLAY_EXEC_PRICE,
    DISPLAY_EXIT_DATE,
    DISPLAY_EXIT_PRICE,
    DISPLAY_EXIT_RATE,
    DISPLAY_EXTENDED_LEVELS,
    DISPLAY_GAIN_TAX,
    DISPLAY_GRID_EXCESS,
    DISPLAY_HELD_INVESTED,
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
    DISPLAY_SELL_TAX,
    DISPLAY_TARGET_PRICE,
    DISPLAY_TAX_PAID,
    DISPLAY_TOTAL_ASSETS,
    DISPLAY_USD_VALUE,
    ETF_MARKET_FILENAMES,
    INTEREST_TAX_RATE,
    PATH_EXCHANGE,
    PATH_START_DATES,
)
from verify_lab.strategy.grid.engine import GridConfig, GridResult, run_grid
from verify_lab.strategy.grid.interest import build_rate_series
from verify_lab.strategy.grid.paths.base import ExecutionPath
from verify_lab.strategy.grid.paths.etf import EtfPath
from verify_lab.strategy.grid.paths.exchange import ExchangePath
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
NOTE_SCOPE = "거래비용·이자·세금이 모두 반영된 한 경로·한 하단 이탈 대응의 결과다. " "A안과 B안은 파라미터가 아니라 설계 대안이라 하나를 고르지 않고 둘 다 돌려 견준다"
NOTE_LOWER_BREACH = (
    "하단 이탈 B안의 격자 연장은 다음 재조정까지 유지된다 — 연장 하단은 직전 재조정 이후의 누적 최저 종가이며 "
    "재조정일에 초기화된다. 연장 레벨은 하단부 배수를 받지만 위치·배수의 기준 범위는 정식 하단·상단 그대로다"
)
NOTE_PATH = "격자·범위·하향 돌파·목표가는 언제나 원달러 종가로 판정하고 체결과 평가만 경로의 집행 가격으로 한다. " "ETF 경로는 그 종목의 개장일로 거래일을 좁혔다"
NOTE_ETF_PERIOD = "ETF 는 2016-12-27 상장이라 환전 경로(2005~)와 기간이 다르다. " "직접 비교하지 말고 같은 시작일로 돌린 대조군끼리 견준다"
NOTE_ETF_CARRY = (
    "ETF 는 캐리·보수·롤오버·감쇠가 수정 종가에 내재돼 있어 보유 이자를 붙이지 않고 총보수도 따로 빼지 않는다. " "정수 주식 수만 사며 못 쓴 예산은 현금으로 남아 파킹 이자를 받는다"
)
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
    COL_EXEC_PRICE: DISPLAY_EXEC_PRICE,
    COL_RANGE_LOW: DISPLAY_RANGE_LOW,
    COL_RANGE_HIGH: DISPLAY_RANGE_HIGH,
    COL_REBALANCED: DISPLAY_REBALANCED,
    COL_ACTIVE_LEVELS: DISPLAY_ACTIVE_LEVELS,
    COL_HELD_SLOTS: DISPLAY_HELD_SLOTS,
    COL_BUY_COUNT: DISPLAY_BUY_COUNT,
    COL_SELL_COUNT: DISPLAY_SELL_COUNT,
    COL_BLOCKED_COUNT: DISPLAY_BLOCKED_COUNT,
    COL_EXTENDED_LEVELS: DISPLAY_EXTENDED_LEVELS,
    COL_HELD_INVESTED: DISPLAY_HELD_INVESTED,
    COL_COST: DISPLAY_COST,
    COL_RP_RATE: DISPLAY_RP_RATE,
    COL_PARKING_RATE: DISPLAY_PARKING_RATE,
    COL_RP_INTEREST: DISPLAY_RP_INTEREST,
    COL_PARKING_INTEREST: DISPLAY_PARKING_INTEREST,
    COL_ACCRUED_INTEREST: DISPLAY_ACCRUED_INTEREST,
    COL_TAX_PAID: DISPLAY_TAX_PAID,
    COL_GAIN_TAX: DISPLAY_GAIN_TAX,
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
    "entry_rate": DISPLAY_ENTRY_RATE,
    "entry_price": DISPLAY_ENTRY_PRICE,
    "exit_date": DISPLAY_EXIT_DATE,
    "exit_rate": DISPLAY_EXIT_RATE,
    "exit_price": DISPLAY_EXIT_PRICE,
    "invested": DISPLAY_INVESTED,
    "buy_cost": DISPLAY_BUY_COST,
    "proceeds": DISPLAY_PROCEEDS,
    "sell_cost": DISPLAY_SELL_COST,
    "sell_tax": DISPLAY_SELL_TAX,
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


def run_usdkrw_grid(
    config: GridConfig,
    *,
    path_name: str = PATH_EXCHANGE,
    start_date: str | None = None,
    lower_breach: str = DEFAULT_LOWER_BREACH,
) -> GridOutputs:
    """원달러 그리드를 한 경로·한 하단 이탈 대응으로 실행하고 표시용 산출물을 조립한다.

    **격자·범위·판정은 언제나 원달러 종가**이고 경로가 바꾸는 것은 집행 가격뿐이다
    (결정 C1·C17). ETF 경로에서는 **거래일도 그 종목의 개장일로 좁힌다** —
    살 수도 팔 수도 없는 날을 판정에 넣으면 돌파를 한 번 놓친다.

    **하단 이탈 A·B 는 한 번에 하나씩 돌린다.** 파라미터가 아니라 설계 대안이라
    하나를 고르는 것이 아니라 둘을 나란히 놓고 견주며, 그 비교는 곡선을 받는 쪽의 일이다.

    Args:
        config: 실행 파라미터
        path_name: 집행 경로 이름 (환전 / 261240 / 261250)
        start_date: 매매 시작일 (`YYYY-MM-DD`). 넘기지 않으면 **경로의 기본 시작일**을 쓴다
        lower_breach: 하단 이탈 대응 (사양서 §7). A안은 하단을 유지하고 B안은 격자를 아래로 연장한다

    Returns:
        표시용 곡선·체결 내역과 원값·메타

    Raises:
        FileNotFoundError: 종가 시계열이나 ETF 시세 파일이 없는 경우
        ValueError: 경로 이름이 유효하지 않거나, 워밍업이 모자라거나, 파라미터가 유효하지 않은 경우
    """
    if path_name not in PATH_START_DATES:
        raise ValueError(f"알 수 없는 집행 경로입니다: {path_name} (가능한 값: {list(PATH_START_DATES)})")

    resolved_start = start_date or PATH_START_DATES[path_name]
    series = load_series_csv(SERIES_DIR / CLOSE_SERIES_FILENAME)

    # 1. 범위표. **전 기간 시세를 넘기고 결과 행만 자른다** — 시세를 먼저 자르면 워밍업이 무너진다.
    #    월평균은 원달러 전 기간으로 계산해야 하므로 거래일 제한은 그 뒤에 건다
    ranges = build_daily_ranges(
        series,
        start_date=pd.Timestamp(resolved_start),
        lookback_years=config.lookback_years,
        min_range_width=config.min_range_width,
        lower_breach=lower_breach,
    )

    # 2. 경로와 집행 가격. 환전은 판정 가격을 그대로 쓰고 ETF 는 수정 종가를 쓴다 (사양서 §11.3)
    path, series, ranges, exec_prices = _resolve_path(path_name, config=config, series=series, ranges=ranges)

    # 3. 금리. 원지표가 없는 날은 전일값을 이월한다 (결정 C14·C65)
    rates = build_rate_series(
        pd.DatetimeIndex(ranges[COL_DATE]),
        tbill=load_series_csv(SERIES_DIR / TBILL_SERIES_FILENAME),
        cd91=load_series_csv(SERIES_DIR / CD91_SERIES_FILENAME),
        config=config.interest,
    )

    # 4. 엔진. 하향 돌파 판정에 직전 거래일 종가가 필요하므로 전 기간 시세를 함께 넘긴다
    result = run_grid(series, ranges, config=config, rates=rates, path=path, exec_prices=exec_prices)

    return GridOutputs(
        daily=_display_daily(result.daily),
        trades=_display_trades(result.trades),
        result=result,
        meta=_build_meta(
            result,
            config=config,
            path_name=path_name,
            start_date=resolved_start,
            lower_breach=lower_breach,
        ),
    )


def _resolve_path(
    path_name: str,
    *,
    config: GridConfig,
    series: pd.DataFrame,
    ranges: pd.DataFrame,
) -> tuple[ExecutionPath, pd.DataFrame, pd.DataFrame, pd.Series | None]:
    """경로를 만들고 그 경로의 거래일·집행 가격에 맞춰 입력을 좁힌다.

    ETF 경로는 **그 종목이 열린 날에만** 사고팔 수 있다. 원달러 고시일 중 ETF 휴장일을
    남겨 두면 그날 판정이 다음 거래일의 「전일 종가」가 되어 **돌파를 한 번 놓친다.**

    Args:
        path_name: 집행 경로 이름
        config: 실행 파라미터
        series: 원달러 종가 전 기간
        ranges: 거래일별 범위표

    Returns:
        경로, 거래일이 좁혀진 원달러 시세, 좁혀진 범위표, 집행 가격
        (환전 경로는 집행 가격이 `None` 이며 판정 가격을 그대로 쓴다)

    Raises:
        FileNotFoundError: ETF 시세 파일이 없는 경우
        ValueError: 좁힌 결과 거래일이 남지 않는 경우
    """
    if path_name == PATH_EXCHANGE:
        return ExchangePath(config.cost), series, ranges, None

    market = load_market_csv(MARKET_DIR / ETF_MARKET_FILENAMES[path_name])
    trading_days = pd.DatetimeIndex(market[COL_DATE])

    narrowed_series = series[series[COL_DATE].isin(trading_days)].reset_index(drop=True)
    narrowed_ranges = ranges[ranges[COL_DATE].isin(trading_days)].reset_index(drop=True)
    dropped = len(ranges) - len(narrowed_ranges)

    if narrowed_ranges.empty:
        raise ValueError(f"{path_name} 의 개장일과 겹치는 거래일이 없습니다 — 매매 시작일을 확인하세요")

    prices = market.set_index(COL_DATE)[COL_CLOSE].reindex(pd.DatetimeIndex(narrowed_ranges[COL_DATE]))
    if prices.isna().any():
        missing = prices.index[prices.isna()]
        raise ValueError(f"{path_name} 시세에 값이 없는 거래일이 있습니다: {[str(day.date()) for day in missing[:5]]}")

    logger.debug(f"{path_name} 경로: 거래일 {len(narrowed_ranges):,}일, 원달러 고시일 중 휴장 {dropped:,}일 제외")

    return EtfPath(ticker=path_name, cost=config.cost), narrowed_series, narrowed_ranges, prices


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
            COL_EXEC_PRICE: PRICE_DECIMALS,
            COL_RANGE_LOW: PRICE_DECIMALS,
            COL_RANGE_HIGH: PRICE_DECIMALS,
            COL_HELD_INVESTED: CAPITAL_DECIMALS,
            COL_COST: CAPITAL_DECIMALS,
            COL_RP_RATE: RATE_DECIMALS,
            COL_PARKING_RATE: RATE_DECIMALS,
            COL_RP_INTEREST: CAPITAL_DECIMALS,
            COL_PARKING_INTEREST: CAPITAL_DECIMALS,
            COL_ACCRUED_INTEREST: CAPITAL_DECIMALS,
            COL_TAX_PAID: CAPITAL_DECIMALS,
            COL_GAIN_TAX: CAPITAL_DECIMALS,
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
            "entry_rate": PRICE_DECIMALS,
            "entry_price": PRICE_DECIMALS,
            "exit_rate": PRICE_DECIMALS,
            "exit_price": PRICE_DECIMALS,
            "invested": CAPITAL_DECIMALS,
            "buy_cost": CAPITAL_DECIMALS,
            "proceeds": CAPITAL_DECIMALS,
            "sell_cost": CAPITAL_DECIMALS,
            "sell_tax": CAPITAL_DECIMALS,
            "realized": CAPITAL_DECIMALS,
            "grid_excess": CAPITAL_DECIMALS,
        }
    )

    return frame.rename(columns=TRADE_LABELS)


def _build_meta(
    result: GridResult,
    *,
    config: GridConfig,
    path_name: str = PATH_EXCHANGE,
    start_date: str,
    lower_breach: str = DEFAULT_LOWER_BREACH,
) -> dict[str, Any]:
    """실행 파라미터와 핵심 수치를 모은다.

    사양서 §7 이 하단 이탈 B안에 요구하는 측정 항목 중 **한 실행으로 나오는 넷**을 여기서 낸다 —
    연장 발생 횟수·최대 연장 칸 수·현금 소진 시점·그 시점의 평가손익률이다. 남은 하나인
    「A안 대비 평균단가·MDD」는 두 실행을 견주는 일이라 여기서는 **평균단가라는 재료**만 낸다.

    Args:
        result: 엔진의 원값
        config: 실행 파라미터
        path_name: 집행 경로 이름
        start_date: 매매 시작일
        lower_breach: 하단 이탈 대응

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

    # 사양서 §7 의 B안 측정 항목. **A안에서도 전부 계산한다** — 값이 0 이라는 사실 자체가
    # 「A안은 연장하지 않는다」의 확인이고, 두 요약의 필드 구성이 같아야 나란히 놓을 수 있다
    extension_days = int((daily[COL_EXTENDED_LEVELS] > 0).sum())
    extension_levels_max = int(daily[COL_EXTENDED_LEVELS].max())
    blocked = daily[daily[COL_BLOCKED_COUNT] > 0]
    first_blocked = blocked.iloc[0] if not blocked.empty else None
    average_unit_cost = result.bought_invested / result.bought_units if result.bought_units else None

    rp_interest = float(daily[COL_RP_INTEREST].sum())
    parking_interest = float(daily[COL_PARKING_INTEREST].sum())
    tax_paid = float(daily[COL_TAX_PAID].sum())
    gain_tax = float(daily[COL_GAIN_TAX].sum())

    return {
        KEY_STRATEGY: "usdkrw_grid",
        KEY_PARAMETERS: {
            "path": path_name,
            "lower_breach": lower_breach,
            "lookback_years": config.lookback_years,
            "growth_rate": config.growth_rate,
            "min_range_width": config.min_range_width,
            "allocation_spread": config.allocation_spread,
            "slot_cap_ratio": config.slot_cap_ratio,
            "initial_capital": round(config.initial_capital, CAPITAL_DECIMALS),
            "exchange_spread_rate": config.cost.exchange_spread_rate,
            "slippage_rate": config.cost.slippage_rate,
            "brokerage_rate": config.cost.brokerage_rate,
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
            "gain_tax_total": round(gain_tax, CAPITAL_DECIMALS),
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
            "blocked_days": int(len(blocked)),
            "first_blocked_date": None if first_blocked is None else first_blocked[COL_DATE].strftime(DATE_FORMAT),
            "unrealised_rate_at_first_block": (None if first_blocked is None else _unrealised_rate(first_blocked)),
            "extension_days": extension_days,
            "extension_levels_max": extension_levels_max,
            "average_unit_cost": None if average_unit_cost is None else round(average_unit_cost, PRICE_DECIMALS),
            "bought_units": round(result.bought_units, PRICE_DECIMALS),
            "bought_invested": round(result.bought_invested, CAPITAL_DECIMALS),
            "active_levels_min": int(daily[COL_ACTIVE_LEVELS].min()),
            "active_levels_max": int(daily[COL_ACTIVE_LEVELS].max()),
            "held_slots_max": int(daily[COL_HELD_SLOTS].max()),
        },
        KEY_ROW_COUNTS: {KEY_DAILY: int(len(daily)), KEY_TRADES: int(len(trades))},
        KEY_NOTES: [
            NOTE_SCOPE,
            NOTE_LOWER_BREACH,
            NOTE_PATH,
            NOTE_ETF_PERIOD,
            NOTE_ETF_CARRY,
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


def _unrealised_rate(row: pd.Series) -> float | None:
    """하루치 곡선에서 **보유분의 미실현 평가손익률**을 낸다.

    사양서 §7 이 하단 이탈 B안에 요구하는 「소진 시점의 평가손실률」이다.
    분모는 **보유 슬롯에 실제로 들어간 원화**(비용 포함)이며, 총자산이 아니다 —
    총자산으로 나누면 원화현금이 섞여 **물린 정도가 투입률에 희석된다.**

    Args:
        row: 일별 곡선의 한 줄

    Returns:
        `(보유 평가액 − 보유 투입액) ÷ 보유 투입액`.
        보유가 없으면 `None` — 0 을 돌려주면 "손익이 없다"로 읽힌다
    """
    invested = float(row[COL_HELD_INVESTED])
    if invested <= 0:
        return None

    return round((float(row[COL_USD_VALUE]) - invested) / invested, 6)
