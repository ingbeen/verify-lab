"""반감기 달력 — 진입일 · 청산 일정 · 수익률 · 기준선 · 달력 연도

| 무엇 | 정의 |
| --- | --- |
| 진입일 | 반감기일 + 진입 개월(달력월). 없는 날짜(31일 + 1개월 등)는 **그 달 말일**로 당긴다 |
| 청산일 | 진입일 + 보유 개월(달력월). 같은 규칙이다 |
| 기준선 | 첫 반감기일부터 **매일** 진입, 신호와 같은 청산 규칙 |
| 달력 연도 | 전년 12-31 종가 대비 그해 12-31 종가 (관찰용) |
| 3단계 체결 일정 | 진입 = 반감기일 + 진입 개월, 청산 = 청산 개월이 더 크면 **같은 반감기일** + 청산 개월 · 같거나 작으면 **다음 반감기일** + 청산 개월. 두 날 모두 **그 사이클 안**이어야 한다 |

**진입일 규칙은 하나인데 구현은 둘이다** — 1단계 `halving_entries` 와 3단계 `position_schedule` 이 각자 반감기일에
달력월을 더한다. 다음 반감기 뒤로 넘어간 진입을 1단계는 그 사이클 칸에 남기고(설계 결정 ㉑) 3단계는 행 없이 세기
때문이다(결정 ㊴). **규칙을 바꾸면 두 곳을 함께 바꾼다.**

**반감기일은 블록 헤더 시각의 UTC 날짜다** (`constants.HALVINGS`). 블록 높이는 수년 전부터 정해져 있고
진입·청산이 그 날짜와 달력으로만 정해지므로 **판정이 필요 없고 미래를 참조하지 않는다.** 다만 구현이
판정일 이후의 데이터에 기대지 않는지는 look-ahead 감시 테스트로 고정한다.

**비트코인은 휴장이 없다** — 그래서 목표일이 거래일에 없으면 앞뒤 날로 옮기지 않고 예외를 낸다. 그런 날은
데이터의 빈틈이고, 옮기면 다른 날을 잰다. 날짜 목록을 인자로 받는 모듈이라 `ValueError` 다
(`execution/trade_fill.resolve_positions` 의 구분 — 메시지 본문을 맞춘다).

**데이터 뒤의 목표일은 두 갈래다.** 진입일이 데이터 뒤면 **신호가 아직 없는 것**이라 행을 만들지 않고,
진입은 했는데 청산일이 데이터 뒤면 **행을 남기고 제외 사유**를 단다 — 1단계 일정에서는 `진입 × 보유 = 유효 + 제외` 가,
3단계 일정에서는 `PositionSchedule` 의 등식이 성립한다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
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
    COL_EXIT_MONTHS,
    COL_HALVING,
    COL_HALVING_POSITION,
    COL_HOLD_MONTHS,
    COL_PREVIOUS_CLOSE,
    COL_YEAR_END_CLOSE,
    POSITION_AFTER_TEMPLATE,
    POSITION_BEFORE_FIRST,
    POSITION_HALVING_YEAR,
    REASON_EXIT_AFTER_NEXT_HALVING,
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

# 3단계 체결 일정의 컬럼
POSITION_COLUMNS = [
    COL_HALVING,
    COL_ENTRY_MONTHS,
    COL_EXIT_MONTHS,
    COL_DATE,
    COL_EXIT_DATE,
    COL_HOLD_DAYS,
    COL_EXCLUDED_REASON,
]


@dataclass(frozen=True)
class PositionSchedule:
    """3단계 체결 일정 — 진입 시점 × 청산 시점

    **`사이클 수 × 진입 × 청산 = 행 + 그 사이클에 없음 + 아직 안 옴` 이 성립한다** (표본 보존).

    Attributes:
        schedule: 진입일이 있는 (반감기 × 진입 × 청산) 행. 청산일을 정하지 못한 행은 청산일 · 보유일이 비고 사유가 붙는다
        outside_cycle_count: 진입일이 다음 반감기 뒤라 **그 사이클에 그 시점이 없어** 행을 만들지 않은 조합 수
        not_yet_count: 진입일이 데이터 뒤라 **신호가 아직 없어** 행을 만들지 않은 조합 수
    """

    schedule: pd.DataFrame
    outside_cycle_count: int
    not_yet_count: int


def trading_positions(trading_days: pd.DatetimeIndex, dates: pd.DatetimeIndex, *, label: str) -> np.ndarray:
    """날짜를 거래일 위치로 바꾼다. 없는 날짜가 하나라도 있으면 멈춘다.

    날짜 목록을 받는 이 패키지의 달력 · 신호 함수가 쓴다. 체결과 비중첩 표본 계산은
    `execution/trade_fill.resolve_positions` 를 쓴다 — 두 함수는 예외 종류만 다르다(모듈 docstring).

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
    trading_positions(trading_days, pd.DatetimeIndex(entries[COL_DATE]), label="진입일")

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
    entry_positions = trading_positions(trading_days, entry_dates, label="진입일")

    blocks: list[pd.DataFrame] = []
    exit_dates: list[pd.DatetimeIndex] = []
    for months in hold_months:
        exits = entry_dates + pd.DateOffset(months=months)
        usable = np.asarray(exits <= last_day)

        exit_positions = np.zeros(len(exits), dtype=np.int64)
        exit_positions[usable] = trading_positions(trading_days, exits[usable], label="청산일")

        block = entries.copy()
        block[_ORDER] = np.arange(len(block))
        block[COL_HOLD_MONTHS] = months
        block[COL_HOLD_DAYS] = pd.array(
            np.where(usable, exit_positions - entry_positions, np.nan), dtype="Float64"
        ).astype("Int64")
        block[COL_EXCLUDED_REASON] = np.where(usable, REASON_NONE, REASON_OUT_OF_RANGE)
        blocks.append(block)
        exit_dates.append(pd.DatetimeIndex(exits.where(usable)))

    # **청산일은 블록을 이은 뒤에 붙인다.** 한 보유의 청산이 전부 데이터 뒤라 그 블록의 청산일이 전부 비면 `pd.concat` 이
    # NumPy 폐기 예정 경고를 낸다(pandas 2.3 · NumPy 2.5 실측) — NumPy 가 그것을 오류로 바꾸면 짧은 입력에서 측정이 멈춘다.
    # 자리는 보유 개월 바로 뒤 그대로다
    combined = pd.concat(blocks, ignore_index=True)
    combined.insert(
        list(combined.columns).index(COL_HOLD_MONTHS) + 1, COL_EXIT_DATE, exit_dates[0].append(exit_dates[1:])
    )
    schedule = (
        combined.sort_values([_ORDER, COL_HOLD_MONTHS], kind="stable").drop(columns=[_ORDER]).reset_index(drop=True)
    )

    excluded = int((schedule[COL_EXCLUDED_REASON] != REASON_NONE).sum())
    logger.debug(f"청산 일정 산출: 진입 {len(entries):,} × 보유 {len(hold_months)} = {len(schedule):,}행, 제외 {excluded:,}행")

    return schedule


def _position_exit(
    anchors: tuple[pd.Timestamp, pd.Timestamp | None, pd.Timestamp | None],
    entry_months: int,
    exit_months: int,
    last_day: pd.Timestamp,
) -> tuple[pd.Timestamp | None, str]:
    """3단계 체결 하나의 청산일과 제외 사유를 정한다.

    Args:
        anchors: (그 반감기일, 다음 반감기일, 그다음 반감기일). 목록에 없으면 `None`
        entry_months: 진입 개월
        exit_months: 청산 개월
        last_day: 데이터 마지막 날

    Returns:
        (청산일 또는 `None`, 제외 사유). 청산일이 있으면 사유는 `REASON_NONE` 이다
    """
    halving_day, next_day, after_next_day = anchors
    if exit_months > entry_months:
        anchor, bound = halving_day, next_day
    elif next_day is None:
        # **반감기 목록이 데이터를 덮는다는 전제다** (결정 ⑫ — 그 해가 오면 실제 블록 시각으로 한 줄을 더한다).
        # 그 전제 아래서 다음 반감기가 없다는 것은 그 청산일이 데이터 뒤라는 뜻이다
        return None, REASON_OUT_OF_RANGE
    else:
        anchor, bound = next_day, after_next_day

    exit_day = anchor + pd.DateOffset(months=exit_months)
    # **데이터 끝보다 먼저 본다** — 이 판정은 데이터와 무관한 사실이라 뒤를 잘라도 사유가 바뀌지 않는다
    if bound is not None and exit_day >= bound:
        return None, REASON_EXIT_AFTER_NEXT_HALVING
    if exit_day > last_day:
        return None, REASON_OUT_OF_RANGE

    return exit_day, REASON_NONE


def position_schedule(
    trading_days: pd.DatetimeIndex,
    halvings: Sequence[Halving],
    entry_months: Sequence[int],
    exit_months: Sequence[int],
) -> PositionSchedule:
    """3단계 체결 일정 — 반감기 × 진입 시점 × 청산 시점마다 진입일과 청산일을 정한다.

    **진입과 청산 모두 「가장 최근 반감기 뒤 몇 개월」이다.** 청산 개월이 진입 개월보다 크면 같은 반감기 뒤,
    같거나 작으면 **다음 반감기 뒤** 그 시점에 판다 — 보유는 최대 한 사이클이다(설계 결정 ㉞). 다음 사이클의
    청산일은 그 반감기가 지난 뒤에야 알 수 있지만, 그 날짜로 체결할 뿐 **그 뒤의 가격으로 무엇을 판정하지 않으므로**
    미래 참조가 아니다.

    **정해지지 않는 조합은 넷이고 두 갈래로 나뉜다** (결정 ㊴).

    | 경우 | 처리 |
    | --- | --- |
    | 진입일이 다음 반감기 뒤 — 그 사이클에 그 시점이 없다 | 행 없음 · 건수만 |
    | 진입일이 데이터 뒤 — 신호가 아직 없다 | 행 없음 · 건수만 |
    | 청산 시점 전에 반감기가 한 번 더 왔다 | 제외 행 · `REASON_EXIT_AFTER_NEXT_HALVING` |
    | 다음 사이클 청산인데 다음 반감기가 목록에 없다 · 청산일이 데이터 뒤 | 제외 행 · `REASON_OUT_OF_RANGE` |

    Args:
        trading_days: 거래일 목록 (오름차순 · 중복 없음)
        halvings: 반감기 목록 — **날짜 오름차순**
        entry_months: 진입 개월 (0 이상)
        exit_months: 청산 개월 (0 이상)

    Returns:
        일정과 행을 만들지 않은 두 종의 건수. 일정은 `POSITION_COLUMNS` 구성이고 반감기 → 진입 → 청산 순서다

    Raises:
        ValueError: 반감기가 없거나 날짜 오름차순이 아니거나, 개월이 음수이거나, 거래일 목록이 잘못됐거나,
            데이터 안의 진입일 · 청산일이 거래일 목록에 없는 경우
    """
    if not halvings:
        raise ValueError("반감기가 하나도 없습니다")
    halving_days = [halving.day for halving in halvings]
    if any(later <= earlier for earlier, later in zip(halving_days, halving_days[1:], strict=False)):
        raise ValueError(
            "반감기는 날짜 오름차순이어야 합니다 — 순서가 틀리면 「다음 반감기」가 다른 날을 가리킵니다: "
            f"{[day.date().isoformat() for day in halving_days]}"
        )
    negative = [months for months in (*entry_months, *exit_months) if months < 0]
    if negative:
        raise ValueError(f"진입 · 청산 개월은 0 이상이어야 합니다: {negative}")
    validate_trading_days(trading_days, purpose="체결 일정")

    last_day = trading_days[-1]
    rows: list[dict[str, Any]] = []
    outside_cycle = 0
    not_yet = 0
    for index, halving in enumerate(halvings):
        next_day = halving_days[index + 1] if index + 1 < len(halving_days) else None
        after_next_day = halving_days[index + 2] if index + 2 < len(halving_days) else None
        for entry in entry_months:
            entry_day = halving.day + pd.DateOffset(months=entry)
            if next_day is not None and entry_day >= next_day:
                outside_cycle += len(exit_months)
                continue
            # **아직 오지 않은 진입은 신호가 없는 것이다** — 제외 행으로 만들면 신호 수가 부푼다 (결정 ⑯)
            if entry_day > last_day:
                not_yet += len(exit_months)
                continue
            for exit_ in exit_months:
                exit_day, reason = _position_exit((halving.day, next_day, after_next_day), entry, exit_, last_day)
                rows.append(
                    {
                        COL_HALVING: halving.label,
                        COL_ENTRY_MONTHS: entry,
                        COL_EXIT_MONTHS: exit_,
                        COL_DATE: entry_day,
                        COL_EXIT_DATE: exit_day,
                        COL_EXCLUDED_REASON: reason,
                    }
                )

    schedule = pd.DataFrame(rows, columns=POSITION_COLUMNS).astype(
        {
            COL_ENTRY_MONTHS: "int64",
            COL_EXIT_MONTHS: "int64",
            COL_DATE: "datetime64[ns]",
            COL_EXIT_DATE: "datetime64[ns]",
        }
    )

    valid = np.asarray(schedule[COL_EXCLUDED_REASON] == REASON_NONE)
    entry_positions = trading_positions(trading_days, pd.DatetimeIndex(schedule[COL_DATE]), label="진입일")
    exit_positions = np.zeros(len(schedule), dtype=np.int64)
    exit_positions[valid] = trading_positions(
        trading_days, pd.DatetimeIndex(schedule.loc[valid, COL_EXIT_DATE]), label="청산일"
    )
    schedule[COL_HOLD_DAYS] = pd.array(
        np.where(valid, exit_positions - entry_positions, np.nan), dtype="Float64"
    ).astype("Int64")

    logger.debug(
        f"체결 일정 산출: 행 {len(schedule):,} (제외 {int((~valid).sum()):,}), "
        f"그 사이클에 없는 진입 {outside_cycle:,} · 아직 오지 않은 진입 {not_yet:,}"
    )

    return PositionSchedule(schedule=schedule, outside_cycle_count=outside_cycle, not_yet_count=not_yet)


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
        position = int(trading_positions(trading_days, pd.DatetimeIndex([day]), label="연말")[0])

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
    "POSITION_COLUMNS",
    "PositionSchedule",
    "baseline_entries",
    "calendar_returns",
    "calendar_year_returns",
    "exit_schedule",
    "halving_entries",
    "halving_position",
    "position_schedule",
    "trading_positions",
]
