#!/usr/bin/env python3
"""월말 확정 칸을 «배수별 실물»로 재고 1배 환산과 대조한다

성적표는 1배 롱의 부호를 뒤집어 「아래」를 만드는데 **실집행은 2배 인버스**다. 그 상품은
선물을 추종하므로 베이스시스·롤오버·일일 리밸런싱이 붙어 **부호를 뒤집어 2를 곱한 값과 같지
않을 수 있다.** 같은 진입·청산 날짜로 세 계열을 나란히 낸다.

[중요] **이 성적은 산출물이 아니라 `docs/매매/월말_진입/규칙.md` §2 가 갖는다** —
2배 상품은 판정 표본이 아니라 성적표에서 빠졌기 때문이다(2026-09-21 사용자 결정).
**그래서 재수집하면 그 수치가 낡는데 다시 잴 수단이 필요하고, 그것이 이 스크립트다.**

**손절선은 기초자산 기준으로 읽는다.** 1배 −5% 는 2배 상품에서 −10% 이며, 배수를 곱해
같은 규칙을 만든다 — 상품 가격 기준 −5% 를 그대로 옮기면 기초자산 −2.5% 에서 자르는
훨씬 타이트한 규칙이 된다.

**진입일·청산일은 `studies/month_end/schedule.py`, 체결은 `execution/trade_fill.py` 를
그대로 부른다** — 판정식을 새로 만들면 성적표와 다른 것을 재게 된다 (절대 원칙 5).

**인버스 실물은 그 상품을 «사는» 것**이므로 아래로 걸지 않는다. 1배 롱만 부호를 뒤집는다.

외부 서버에 요청하지 않는다. 이미 받아 둔 시세 파일만 읽는다.
실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

from dataclasses import dataclass
from typing import Any, Final

import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE, MARKET_DIR, MARKET_FILE_TEMPLATE, RATE_TO_PERCENT
from verify_lab.data.loader import load_market_csv
from verify_lab.execution.constants import EXIT_LIMIT
from verify_lab.execution.trade_fill import resolve_positions, simulate_scheduled_trade
from verify_lab.measure.constants import COL_EXCLUDED_REASON, REASON_NONE
from verify_lab.report.constants import PERCENT_DECIMALS
from verify_lab.studies.month_end.constants import (
    BASE_ENTRY_DAY,
    BASE_EXIT_OFFSET,
    COL_EXIT_DATE,
    COL_MONTH,
    MONTH_END_STOP_GRID,
    MONTH_END_STOP_LEVEL,
    TRADING_CELLS,
)
from verify_lab.studies.month_end.schedule import month_entry_dates, month_exit_schedule
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_MONTH_END_LEVERAGE: Final = "month_end_leverage_probe"


@dataclass(frozen=True)
class Leg:
    """대조할 계열 하나

    Attributes:
        ticker: 종목 코드
        label: 표시 이름
        market: 어느 시장인가
        multiple: 기초자산 대비 배수의 절대값. **손절선을 기초자산 기준으로 환산할 때 쓴다**
        bet_down: 아래로 거는지 여부. 1배 롱만 참이고 **인버스 실물은 그 상품을 사므로 거짓**이다
    """

    ticker: str
    label: str
    market: str
    multiple: float
    bet_down: bool


MARKET_KOSPI: Final = "코스피"
MARKET_KOSDAQ: Final = "코스닥"

# **코스닥150 에는 −2배 ETF 가 없다** — ETN 뿐이고 둘 다 2022-10-17 상장이라 표본이 3건이다.
# 삼성(`530107`)이 거래대금 1위이며 검증 #8·#9 도 그것을 대표로 쓴다
LEGS: Final = (
    Leg(ticker="069500", label="KODEX 200 (1배 롱, 부호 뒤집기)", market=MARKET_KOSPI, multiple=1.0, bet_down=True),
    Leg(ticker="114800", label="KODEX 인버스 (1배 실물)", market=MARKET_KOSPI, multiple=1.0, bet_down=False),
    Leg(
        ticker="252670",
        label="KODEX 200선물인버스2X (2배 실물)",
        market=MARKET_KOSPI,
        multiple=2.0,
        bet_down=False,
    ),
    Leg(
        ticker="229200",
        label="KODEX 코스닥150 (1배 롱, 부호 뒤집기)",
        market=MARKET_KOSDAQ,
        multiple=1.0,
        bet_down=True,
    ),
    Leg(
        ticker="251340",
        label="KODEX 코스닥150선물인버스 (1배 실물)",
        market=MARKET_KOSDAQ,
        multiple=1.0,
        bet_down=False,
    ),
    Leg(
        ticker="530107",
        label="삼성 인버스 2X 코스닥150 선물 ETN (2배 실물)",
        market=MARKET_KOSDAQ,
        multiple=2.0,
        bet_down=False,
    ),
)

RESULT_COLUMNS: Final = [
    ("시장", 8, Align.LEFT),
    ("계열", 40, Align.LEFT),
    ("손절선", 10, Align.RIGHT),
    ("신호", 6, Align.RIGHT),
    ("기간", 12, Align.RIGHT),
    ("합계(%)", 10, Align.RIGHT),
    ("회당(%)", 9, Align.RIGHT),
    ("승률(%)", 9, Align.RIGHT),
    ("최악(%)", 9, Align.RIGHT),
    ("보유 중 최악(%)", 16, Align.RIGHT),
    ("손절", 6, Align.RIGHT),
]

# **자릿수도 청산 사유도 공통 계층이 소유한다** — 여기서 다시 적으면 그 값이 바뀔 때
# 이 프로브만 조용히 어긋나고, 이 프로브의 숫자가 `docs/매매/월말_진입/규칙.md` §2 로 간다


def _stop_for(leg: Leg, base_level: float | None) -> float | None:
    """기초자산 기준 손절선을 그 상품의 가격 기준으로 환산한다.

    Args:
        leg: 대조할 계열
        base_level: 기초자산 기준 손절선 (비율). `None` 이면 무손절

    Returns:
        그 상품에 걸 손절선. 무손절이면 `None`
    """
    if base_level is None:
        return None

    return base_level * leg.multiple


def _measure(leg: Leg, base_level: float | None) -> dict[str, Any] | None:
    """한 계열을 확정 칸으로 돌려 성적 한 줄을 낸다.

    Args:
        leg: 대조할 계열
        base_level: 기초자산 기준 손절선 (비율). `None` 이면 무손절

    Returns:
        표 한 줄. 확정 칸에 체결이 하나도 없으면 `None`
    """
    frame = load_market_csv(MARKET_DIR / MARKET_FILE_TEMPLATE.format(ticker=leg.ticker))
    trading_days = pd.DatetimeIndex(frame[COL_DATE])

    entries = month_entry_dates(trading_days, calendar_day=BASE_ENTRY_DAY)
    schedule = month_exit_schedule(trading_days, entries, exit_offset=BASE_EXIT_OFFSET)
    # **제외 판정은 사유 컬럼으로 한다** — `COL_EXIT_DATE` 의 결측은 지금 그것과 일치하지만
    # 내부 구현이지 계약이 아니다. 성적표와 같은 기준을 써야 같은 체결을 잰다
    usable = schedule.frame[schedule.frame[COL_EXCLUDED_REASON] == REASON_NONE]

    wanted = {cell.month for cell in TRADING_CELLS}
    cell_rows = usable[usable[COL_MONTH].dt.month.isin(wanted)]

    # **조용히 빈 줄을 내지 않는다.** 상장일이 늦어 확정 칸에 한 건도 없는 계열이 실재한다
    if cell_rows.empty:
        logger.warning(f"{leg.label}: 확정 칸에 체결이 하나도 없습니다")
        return None

    entry_positions = resolve_positions(trading_days, pd.DatetimeIndex(cell_rows[COL_DATE]), label="진입일")
    exit_positions = resolve_positions(trading_days, pd.DatetimeIndex(cell_rows[COL_EXIT_DATE]), label="청산일")

    returns: list[float] = []
    worst_holds: list[float] = []
    stopped = 0

    for order in range(len(cell_rows)):
        result = simulate_scheduled_trade(
            frame,
            int(entry_positions[order]),
            int(exit_positions[order]),
            bet_down=leg.bet_down,
            stop_level=_stop_for(leg, base_level),
            price_column=COL_CLOSE,
        )
        returns.append(result.return_rate * RATE_TO_PERCENT)
        worst_holds.append(result.worst_hold_rate * RATE_TO_PERCENT)
        stopped += result.reason != EXIT_LIMIT

    values = pd.Series(returns)
    years = pd.DatetimeIndex(cell_rows[COL_DATE]).year

    return {
        "시장": leg.market,
        "계열": leg.label,
        "손절선": "무손절" if base_level is None else f"{-base_level * RATE_TO_PERCENT:.0f}%",
        "신호": len(values),
        "기간": f"{years.min()}~{years.max()}",
        "합계(%)": round(float(values.sum()), PERCENT_DECIMALS),
        "회당(%)": round(float(values.mean()), PERCENT_DECIMALS),
        "승률(%)": round(float((values > 0).sum()) / len(values) * RATE_TO_PERCENT, PERCENT_DECIMALS),
        "최악(%)": round(float(values.min()), PERCENT_DECIMALS),
        "보유 중 최악(%)": round(min(worst_holds), PERCENT_DECIMALS),
        "손절": stopped,
    }


@cli_exception_handler
def main() -> int:
    """확정 칸을 배수별 실물로 재고 표로 낸다.

    Returns:
        종료 코드 (성공 0)
    """
    cells = ", ".join(f"{cell.month}월 {'아래' if cell.bet_down else '위'}" for cell in TRADING_CELLS)
    rows = [row for leg in LEGS for level in MONTH_END_STOP_GRID if (row := _measure(leg, level)) is not None]

    table = TableLogger(RESULT_COLUMNS, logger)
    table.print_header(f"확정 칸({cells})을 배수별 실물로 — 손절선은 «기초자산» 기준")
    for row in rows:
        table.print_row([str(row[name]) for name, _, _ in RESULT_COLUMNS])
    table.print_footer()

    fixed = -MONTH_END_STOP_LEVEL * RATE_TO_PERCENT
    logger.debug(f"확정 손절선 {fixed:.0f}% 는 «기초자산» 기준이다 — 2배 상품에서는 {fixed * 2:.0f}% 로 건다")
    logger.debug("1배 롱만 부호를 뒤집고 인버스 실물은 그 상품을 산다 — 두 값의 차이가 배수 환산의 오차다")
    logger.debug("이 성적의 자리는 `docs/매매/월말_진입/규칙.md` §2 다. 재수집하면 여기를 다시 돌려 그 절을 고친다")

    save_metadata(KEY_META_MONTH_END_LEVERAGE, {"cells": cells, "legs": [leg.ticker for leg in LEGS], "rows": rows})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
