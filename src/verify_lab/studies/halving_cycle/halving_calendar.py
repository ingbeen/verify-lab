"""반감기 달력 — 진입일 · 청산 일정 · 수익률 · 기준선 · 달력 연도

| 무엇 | 정의 |
| --- | --- |
| 진입일 | 반감기일 + 진입 개월(달력월). 없는 날짜(31일 + 1개월 등)는 **그 달 말일**로 당긴다 |
| 청산일 | 진입일 + 보유 개월(달력월). 같은 규칙이다 |
| 기준선 | 첫 반감기일부터 **매일** 진입, 신호와 같은 청산 규칙 |
| 달력 연도 | 전년 12-31 종가 대비 그해 12-31 종가 (관찰용) |

**반감기일은 블록 헤더 시각의 UTC 날짜다** (`constants.HALVINGS`). 블록 높이는 수년 전부터 정해져 있고
진입·청산이 그 날짜와 달력으로만 정해지므로 **판정이 필요 없고 미래를 참조하지 않는다.** 다만 구현이
판정일 이후의 데이터에 기대지 않는지는 look-ahead 감시 테스트로 고정한다.

**비트코인은 휴장이 없다** — 그래서 목표일이 거래일에 없으면 앞뒤 날로 옮기지 않고 예외를 낸다. 그런 날은
데이터의 빈틈이고, 옮기면 다른 날을 잰다. 날짜 목록을 인자로 받는 모듈이라 `ValueError` 다
(`execution/trade_fill.resolve_positions` 의 구분 — 메시지 본문을 맞춘다).

**데이터 뒤의 목표일은 두 갈래다.** 진입일이 데이터 뒤면 **신호가 아직 없는 것**이라 행을 만들지 않고,
진입은 했는데 청산일이 데이터 뒤면 **행을 남기고 제외 사유**를 단다 — `진입 × 보유 = 유효 + 제외` 가 성립한다.
"""

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE
from verify_lab.data.loader import validate_market_frame
from verify_lab.measure.calendar_entry import validate_trading_days
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_ENTRY_CLOSE,
    COL_EXCLUDED_REASON,
    COL_EXIT_CLOSE,
    COL_EXIT_DATE,
    COL_FORWARD_RETURN,
    COL_HOLD_DAYS,
    COL_HORIZON,
    REASON_NONE,
    REASON_OUT_OF_RANGE,
)
from verify_lab.measure.forward_return import ReturnBasis
from verify_lab.studies.halving_cycle.constants import (
    COL_CALENDAR_YEAR,
    COL_ENTRY_MONTHS,
    COL_HALVING,
    COL_HALVING_POSITION,
    COL_HOLD_MONTHS,
    COL_PREVIOUS_CLOSE,
    COL_YEAR_END_CLOSE,
    POSITION_AFTER_TEMPLATE,
    POSITION_BEFORE_FIRST,
    POSITION_HALVING_YEAR,
    REASON_NO_PREVIOUS_YEAR_END,
    REASON_YEAR_UNFINISHED,
    Halving,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 진입일 표의 컬럼
ENTRY_COLUMNS = [COL_HALVING, COL_ENTRY_MONTHS, COL_DATE]

# 달력 연도 표의 컬럼
CALENDAR_YEAR_COLUMNS = [
    COL_CALENDAR_YEAR,
    COL_HALVING_POSITION,
    COL_PREVIOUS_CLOSE,
    COL_YEAR_END_CLOSE,
    COL_FORWARD_RETURN,
    COL_EXCLUDED_REASON,
]

# 청산 일정을 진입 순서 → 보유 순서로 세우는 임시 컬럼
_ORDER = "_entry_order"


def _positions(trading_days: pd.DatetimeIndex, dates: pd.DatetimeIndex, *, label: str) -> np.ndarray:
    """날짜를 거래일 위치로 바꾼다. 없는 날짜가 하나라도 있으면 멈춘다.

    Args:
        trading_days: 거래일 목록
        dates: 위치를 구할 날짜
        label: 메시지에 쓸 날짜의 이름 (`진입일`·`청산일`·`연말`)

    Returns:
        거래일 위치 배열

    Raises:
        ValueError: 거래일 목록에 없는 날짜가 있는 경우 — 휴장이 없는 시세라 그런 날은 데이터의 빈틈이다
    """
    positions = np.asarray(trading_days.get_indexer(dates), dtype=np.int64)
    if len(positions) and positions.min() < 0:
        missing = dates[positions < 0]
        raise ValueError(f"{label}이 거래일 목록에 없습니다: {[day.date().isoformat() for day in missing]}")

    return positions


def halving_position(year: int, halvings: Sequence[Halving]) -> str:
    """달력 연도가 반감기 사이클의 어디인지 돌려준다.

    **가장 최근 반감기 해로부터의 햇수**다 — 4로 나눈 나머지로 정하면 간격이 정확히 4년이라는 가정이
    코드에 숨는다.

    Args:
        year: 달력 연도
        halvings: 반감기 목록

    Returns:
        `반감기해` · `반감기 + N` · `첫 반감기 전` 중 하나
    """
    past = [halving.day.year for halving in halvings if halving.day.year <= year]
    if not past:
        return POSITION_BEFORE_FIRST

    offset = year - max(past)

    return POSITION_HALVING_YEAR if offset == 0 else POSITION_AFTER_TEMPLATE.format(years=offset)


def halving_entries(
    trading_days: pd.DatetimeIndex, halvings: Sequence[Halving], entry_months: Sequence[int]
) -> pd.DataFrame:
    """반감기 × 진입 개월의 진입일을 만든다.

    Args:
        trading_days: 거래일 목록 (오름차순 · 중복 없음)
        halvings: 반감기 목록
        entry_months: 반감기 뒤 진입 개월 (0 이상)

    Returns:
        `ENTRY_COLUMNS` 구성. 반감기 → 진입 개월 순서이며 **데이터 마지막 날 뒤의 진입은 행이 없다**

    Raises:
        ValueError: 반감기가 없거나, 진입 개월이 음수이거나, 거래일 목록이 잘못됐거나,
            데이터 안의 진입일이 거래일 목록에 없는 경우
    """
    if not halvings:
        raise ValueError("반감기가 하나도 없습니다")
    negative = [months for months in entry_months if months < 0]
    if negative:
        raise ValueError(f"진입 개월은 0 이상이어야 합니다 (반감기 «전» 진입은 이 격자에 없다): {negative}")
    validate_trading_days(trading_days, purpose="진입일")

    last_day = trading_days[-1]
    rows: list[dict[str, Any]] = []
    for halving in halvings:
        for months in entry_months:
            entry = halving.day + pd.DateOffset(months=months)
            # **아직 오지 않은 진입은 신호가 없는 것이다** — 제외 행으로 만들면 진입 수가 부푼다
            if entry > last_day:
                continue
            rows.append({COL_HALVING: halving.label, COL_ENTRY_MONTHS: months, COL_DATE: entry})

    entries = pd.DataFrame(rows, columns=ENTRY_COLUMNS).astype({COL_ENTRY_MONTHS: "int64", COL_DATE: "datetime64[ns]"})
    _positions(trading_days, pd.DatetimeIndex(entries[COL_DATE]), label="진입일")

    logger.debug(f"진입일 산출: 반감기 {len(halvings)} × 진입 개월 {len(entry_months)} 중 {len(entries):,}건")

    return entries


def baseline_entries(trading_days: pd.DatetimeIndex, start: pd.Timestamp) -> pd.DataFrame:
    """기준선 진입일 — 시작일(첫 반감기일)부터 **매일**이다.

    **시작일을 첫 반감기로 두는 것**은 「기준선 모집단은 신호군과 같은 기간」이라는 실행 계층 계약 때문이다
    (`src/verify_lab/CLAUDE.md`). 그 앞의 거래(2011 년의 거품·붕괴와 얇은 거래)를 넣으면 기준선 대비 차이에
    「그 사이 시장이 어땠는가」가 섞인다.

    Args:
        trading_days: 거래일 목록
        start: 첫 진입일

    Returns:
        날짜 한 컬럼짜리 표

    Raises:
        ValueError: 거래일 목록이 잘못됐거나, 시작일 이후의 거래일이 없는 경우
    """
    validate_trading_days(trading_days, purpose="기준선 진입일")

    days = trading_days[trading_days >= start]
    if len(days) == 0:
        raise ValueError(f"기준선 진입일이 하나도 없습니다: 시작일 {start.date()} 이 데이터 마지막 날 {trading_days[-1].date()} 뒤입니다")

    return pd.DataFrame({COL_DATE: days})


def exit_schedule(trading_days: pd.DatetimeIndex, entries: pd.DataFrame, hold_months: Sequence[int]) -> pd.DataFrame:
    """진입마다 보유 개월별 청산일을 붙인다.

    Args:
        trading_days: 거래일 목록. 진입일을 만들 때 넘긴 것과 같아야 한다
        entries: 날짜 컬럼이 있는 진입 표. 다른 컬럼은 행마다 그대로 따라온다
        hold_months: 보유 개월 (1 이상)

    Returns:
        진입 × 보유 행. 진입 순서 → 보유 순서이며 **청산이 데이터 끝을 넘은 행도 남는다**(청산일·보유일이
        비고 사유가 붙는다). 입력은 변경하지 않는다

    Raises:
        ValueError: 보유 개월이 없거나 1 미만이거나, 거래일 목록이 잘못됐거나, 진입 표에 날짜가 없거나,
            진입일 · 데이터 안의 청산일이 거래일 목록에 없는 경우
    """
    if not hold_months or min(hold_months) < 1:
        raise ValueError(f"보유 개월은 1 이상이어야 합니다: {list(hold_months)}")
    validate_trading_days(trading_days, purpose="청산일")
    if COL_DATE not in entries.columns:
        raise ValueError(f"진입 표에 날짜 컬럼이 없습니다: {COL_DATE}")

    last_day = trading_days[-1]
    entry_dates = pd.DatetimeIndex(entries[COL_DATE])
    entry_positions = _positions(trading_days, entry_dates, label="진입일")

    blocks: list[pd.DataFrame] = []
    for months in hold_months:
        exits = entry_dates + pd.DateOffset(months=months)
        usable = np.asarray(exits <= last_day)

        exit_positions = np.zeros(len(exits), dtype=np.int64)
        exit_positions[usable] = _positions(trading_days, exits[usable], label="청산일")

        block = entries.copy()
        block[_ORDER] = np.arange(len(block))
        block[COL_HOLD_MONTHS] = months
        block[COL_EXIT_DATE] = exits.where(usable)
        block[COL_HOLD_DAYS] = pd.array(
            np.where(usable, exit_positions - entry_positions, np.nan), dtype="Float64"
        ).astype("Int64")
        block[COL_EXCLUDED_REASON] = np.where(usable, REASON_NONE, REASON_OUT_OF_RANGE)
        blocks.append(block)

    schedule = (
        pd.concat(blocks, ignore_index=True)
        .sort_values([_ORDER, COL_HOLD_MONTHS], kind="stable")
        .drop(columns=[_ORDER])
        .reset_index(drop=True)
    )

    excluded = int((schedule[COL_EXCLUDED_REASON] != REASON_NONE).sum())
    logger.debug(f"청산 일정 산출: 진입 {len(entries):,} × 보유 {len(hold_months)} = {len(schedule):,}행, 제외 {excluded:,}행")

    return schedule


def calendar_returns(df: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    """청산 일정에 종가를 붙여 long-form 수익률을 낸다.

    **`measure.statistics.summarize` 가 읽는 두 축을 채운다** — 기준은 종가 하나, 구간 축에는 **보유 개월**을
    넣는다. 거래일 수가 아니다 — 집계가 (진입 개월 × 보유 개월) 칸으로 묶이려면 보유가 칸의 이름이어야 한다.

    Args:
        df: 날짜 오름차순 시세 (종가 컬럼)
        schedule: `exit_schedule` 의 결과

    Returns:
        일정의 컬럼 + 진입 종가 · 청산 종가 · 기준 · 구간 · 수익률. 행 수는 일정과 같다 —
        제외된 행은 청산 종가와 수익률이 빈다. 입력은 변경하지 않는다

    Raises:
        ValueError: 시세가 비었거나 필요한 컬럼이 없거나 날짜가 오름차순이 아닌 경우, 진입일의 종가가 없는 경우
        RuntimeError: 제외되지 않은 행의 수익률이 비어 있는 경우 (내부 불변조건 위반)
    """
    validate_market_frame(df, [COL_DATE, COL_CLOSE])

    prices = df.set_index(COL_DATE)[COL_CLOSE]
    frame = schedule.copy()

    entry_close = frame[COL_DATE].map(prices)
    if entry_close.isna().any():
        missing = frame.loc[entry_close.isna(), COL_DATE]
        raise ValueError(f"진입일의 종가가 없습니다: {[day.date().isoformat() for day in missing]}")

    # 제외된 행은 청산일이 비어 있으므로 `map` 이 그대로 NaN 을 돌려준다
    exit_close = frame[COL_EXIT_DATE].map(prices)

    frame[COL_ENTRY_CLOSE] = entry_close
    frame[COL_EXIT_CLOSE] = exit_close
    frame[COL_BASIS] = ReturnBasis.CLOSE.value
    frame[COL_HORIZON] = frame[COL_HOLD_MONTHS]
    frame[COL_FORWARD_RETURN] = exit_close / entry_close - 1.0

    valid = frame[COL_EXCLUDED_REASON] == REASON_NONE
    if not frame.loc[valid, COL_FORWARD_RETURN].notna().all():
        raise RuntimeError("내부 불변조건 위반: 제외되지 않은 행의 수익률이 비어 있습니다")

    return frame


def calendar_year_returns(df: pd.DataFrame, halvings: Sequence[Halving]) -> pd.DataFrame:
    """달력 연도마다 전년 12-31 종가 대비 그해 12-31 종가를 낸다 (관찰용).

    **데이터가 닿는 해마다 한 행이다** — 해 중간에 시작하거나 끝난 해도 지우지 않고 제외 사유를 단다
    (측정의 원칙 17). 있는 종가는 채우고 없는 쪽만 비운다.

    Args:
        df: 날짜 오름차순 시세 (종가 컬럼)
        halvings: 반감기 목록 — 위치 표기에 쓴다

    Returns:
        `CALENDAR_YEAR_COLUMNS` 구성. 연도 오름차순

    Raises:
        ValueError: 시세가 잘못됐거나, 데이터 안의 12-31 이 거래일 목록에 없는 경우
    """
    validate_market_frame(df, [COL_DATE, COL_CLOSE])
    trading_days = pd.DatetimeIndex(df[COL_DATE])
    validate_trading_days(trading_days, purpose="달력 연도")

    prices = df.set_index(COL_DATE)[COL_CLOSE]
    first_day = trading_days[0]
    last_day = trading_days[-1]

    def close_on(day: pd.Timestamp) -> float:
        if not first_day <= day <= last_day:
            return np.nan
        position = int(_positions(trading_days, pd.DatetimeIndex([day]), label="연말")[0])

        return float(prices.iloc[position])

    rows: list[dict[str, Any]] = []
    for year in range(first_day.year, last_day.year + 1):
        previous_end = pd.Timestamp(year=year - 1, month=12, day=31)
        year_end = pd.Timestamp(year=year, month=12, day=31)

        if previous_end < first_day:
            reason = REASON_NO_PREVIOUS_YEAR_END
        elif year_end > last_day:
            reason = REASON_YEAR_UNFINISHED
        else:
            reason = REASON_NONE

        previous_close = close_on(previous_end)
        year_end_close = close_on(year_end)
        rows.append(
            {
                COL_CALENDAR_YEAR: year,
                COL_HALVING_POSITION: halving_position(year, halvings),
                COL_PREVIOUS_CLOSE: previous_close,
                COL_YEAR_END_CLOSE: year_end_close,
                COL_FORWARD_RETURN: year_end_close / previous_close - 1.0 if reason == REASON_NONE else np.nan,
                COL_EXCLUDED_REASON: reason,
            }
        )

    return pd.DataFrame(rows, columns=CALENDAR_YEAR_COLUMNS)


__all__ = [
    "CALENDAR_YEAR_COLUMNS",
    "ENTRY_COLUMNS",
    "baseline_entries",
    "calendar_returns",
    "calendar_year_returns",
    "exit_schedule",
    "halving_entries",
    "halving_position",
]
