"""반감기_사이클 3단계 — 달력 + MVRV 혼합 분할매수 · 매도의 회차 체결일과 포지션 성적 (결정 ㊹ ~ ㊼)

포지션 하나는 반감기 뒤에 여러 회차로 나눠 사고, 다음 반감기 뒤에 여러 회차로 나눠 판다.
**회차 k 는 「온체인 문턱 k 에 처음 닿은 날의 다음 거래일」과 「달력 기한 k」 중 빠른 날 종가에 체결한다** —
날마다 「채울 회차 수 = max(온체인으로 닿은 문턱 수, 지난 기한 수)」로 채우는 것과 같은 규칙이다.

| 계기 | 체결 | 왜 |
| --- | --- | --- |
| 온체인 | 판정일 **다음 거래일** 종가 | MVRV 의 d 값은 d+1 일에 완성된다 — 2단계 신호와 같은 관용이다(결정 ㉗) |
| 달력 | 기한 **그날** 종가 | 날짜가 미리 정해져 판정이 필요 없다 — 1단계 진입과 같은 관용이다(결정 ⑯) |

**온체인 문턱에 닿은 날은 창이 열린 날만 센다.** 달력 기한은 창과 상관없이 채운다 — 온체인이 끝내 닿지 않아도
기한에는 산다(판다).

**측정 표로만 낸다** — 1차 판정 · 손절 · 하드포크 몫 · 기준선이 없다(결정 ㊼). **값을 고르지 않는다** — 격자 전부를
내고 고르는 것은 사용자가 `규칙.md` 에서 한다.

**모든 함수가 격자 값을 인자로 받는다** — 상수를 안에서 읽지 않는다. 테스트가 실제와 다른 값을 넣어 하드코딩을 잡는다.

**달력 매달 분할(결정 51 · 52 · 54)도 여기서 잰다** — 「달력만」 조합을 폭마다 쪽별 회차 수 · 간격만 바꾸고 기한을
그 달의 말일로 옮겨 같은 두 함수(`leg_fills` · `position_result`)로 잰다. 회차 날짜와 평균 단가 · 최악의 정의가 두 벌이
되지 않는다(절대 원칙 5). **달력 매달 분할에는 저점 이탈 손절과 하드포크 몫을 손절 표로 더 낸다**(결정 58 · 64) — 장중
저가가 손절선에 닿으면 남은 매도 회차를 그날 손절 체결가로 옮겨 같은 `position_result` 로 잰다. 손절 표를 만든 성적은
표로 바꾸기 전 모양으로 함께 낸다 — 체결 조립(`trading.py`)이 그것을 확정 규칙 행으로 옮긴다(결정 61).

**손절 판정을 공유 체결식(`execution/trade_fill.py`)에 맡기지 않는다**(결정 64) — 그쪽 손절선은 진입가 대비 비율 하나인데
이 손절선은 가격이고 진입가가 여섯이다. 판정 순서(시가 → 장중)와 비교(이하)는 그쪽과 같다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_LOW, COL_OPEN
from verify_lab.execution.constants import EXIT_GAP_STOP, EXIT_INTRADAY_STOP, NO_STOP_LABEL
from verify_lab.measure.constants import COL_EXCLUDED_REASON, COL_HOLD_DAYS, REASON_NONE
from verify_lab.measure.statistics import COL_MEAN, COL_MEDIAN, COL_MIN, COL_POSITIVE_COUNT
from verify_lab.studies.halving_cycle.constants import (
    COL_AVG_BUY_PRICE,
    COL_AVG_SELL_PRICE,
    COL_BREAK_DATE,
    COL_BUY_CALENDAR_COUNT,
    COL_BUY_FIRST_DEADLINE,
    COL_BUY_LAST_DEADLINE,
    COL_BUY_ONCHAIN_COUNT,
    COL_BUY_START_ANCHOR,
    COL_BUY_START_MONTHS,
    COL_BUY_THRESHOLD,
    COL_BUY_TRANCHES,
    COL_CALENDAR_SPLIT,
    COL_CYCLE_RETURN_TEMPLATE,
    COL_CYCLE_WORST_TEMPLATE,
    COL_FINISHED_COUNT,
    COL_FIRST_BUY_DATE,
    COL_FORK_SHARE,
    COL_HALVING,
    COL_LAST_SELL_DATE,
    COL_MONTHS_SINCE_HALVING,
    COL_POSITION_RETURN,
    COL_SELL_CALENDAR_COUNT,
    COL_SELL_FIRST_DEADLINE,
    COL_SELL_LAST_DEADLINE,
    COL_SELL_ONCHAIN_COUNT,
    COL_SELL_START_MONTHS,
    COL_SELL_THRESHOLD,
    COL_SELL_TRANCHES,
    COL_SOLD_BEFORE_STOP,
    COL_SPLIT_ANCHOR_HALVING,
    COL_SPLIT_DEADLINE,
    COL_SPLIT_FILL_CLOSE,
    COL_SPLIT_FILL_DATE,
    COL_SPLIT_LAST_DEADLINE,
    COL_SPLIT_PRIOR_MVRV,
    COL_SPLIT_PRIOR_RANK,
    COL_SPLIT_SIDE,
    COL_SPLIT_START_ANCHOR,
    COL_SPLIT_START_MONTHS,
    COL_SPLIT_THRESHOLD,
    COL_SPLIT_TOTAL,
    COL_SPLIT_TRANCHE,
    COL_SPLIT_TRIGGER,
    COL_STOP_FILL_PRICE,
    COL_STOP_LINE_DATE,
    COL_STOP_LINE_LOW,
    COL_STOP_LINE_VS_COST,
    COL_STOP_METHOD,
    COL_WORST_VS_COST,
    REASON_NO_NEXT_HALVING,
    REASON_POSITION_BUYING,
    REASON_POSITION_SELLING,
    REASON_SPLIT_PENDING,
    SPLIT_ANCHOR_HALVING,
    SPLIT_ANCHOR_HIGH,
    SPLIT_SIDE_BUY,
    SPLIT_SIDE_SELL,
    SPLIT_THRESHOLD_BOOK,
    SPLIT_THRESHOLD_NONE,
    SPLIT_THRESHOLD_RANK,
    SPLIT_TRIGGER_CALENDAR,
    SPLIT_TRIGGER_ONCHAIN,
    STOP_METHOD_LOW_BREAK,
    CalendarSplit,
    Halving,
    HardFork,
)
from verify_lab.studies.halving_cycle.halving_calendar import trading_positions
from verify_lab.studies.halving_cycle.hard_fork import hard_fork_share
from verify_lab.studies.halving_cycle.indicator_signals import months_since

# 결측을 견디는 정수 컬럼 — 창이 없는 달력만 조합의 시작 개월, 체결 전 회차의 경과 개월, 끝나지 않은 포지션의 날 수
_NULLABLE_INTEGER_COLUMNS = (
    COL_SPLIT_START_MONTHS,
    COL_MONTHS_SINCE_HALVING,
    COL_BUY_START_MONTHS,
    COL_SELL_START_MONTHS,
    COL_HOLD_DAYS,
    COL_POSITIVE_COUNT,
    COL_SOLD_BEFORE_STOP,
)

# 날짜 컬럼 — 빈 날짜(체결 전 회차 · 끝나지 않은 포지션 · 이탈 없음)가 섞이거나 전부 비어도 날짜 열로 남긴다
_DATE_COLUMNS = (
    COL_SPLIT_DEADLINE,
    COL_SPLIT_FILL_DATE,
    COL_FIRST_BUY_DATE,
    COL_LAST_SELL_DATE,
    COL_STOP_LINE_DATE,
    COL_BREAK_DATE,
)


@dataclass(frozen=True)
class SplitLeg:
    """분할의 한쪽(매수 또는 매도)의 조합 하나

    Attributes:
        side: 매수 · 매도 (`constants.SPLIT_SIDE_*`)
        threshold: 문턱 방식 (`constants.SPLIT_THRESHOLD_*`). 달력만이면 창 · 문턱이 없다
        levels: 회차 순서의 문턱. 매수는 내려가고(이하에 닿으면) 매도는 올라간다(이상에 닿으면). 달력만이면 빈 튜플
        start_anchor: 창의 기준 (`constants.SPLIT_ANCHOR_*`). 달력만이면 `None`
        start_months: 창이 열리는 개월 — 반감기 기준은 기준 반감기 뒤, 신고가 기준은 가장 최근 신고가 뒤. 달력만이면 `None`
        last_deadline: 마지막 회차의 기한 (기준 반감기 뒤 개월)
    """

    side: str
    threshold: str
    levels: tuple[float, ...]
    start_anchor: str | None
    start_months: int | None
    last_deadline: int


@dataclass(frozen=True)
class TrancheFill:
    """회차 하나의 체결

    Attributes:
        deadline: 달력 기한
        fill_day: 체결일. 아직 체결 전이면 `None`
        trigger: 계기 (`constants.SPLIT_TRIGGER_*`). 체결 전이면 `None`
        reason: 제외 사유. 체결했으면 `REASON_NONE`
        fill_price: 체결가. `None` 이면 그날 종가에 체결했다 — 손절 체결(저점 이탈)만 값을 든다
    """

    deadline: pd.Timestamp
    fill_day: pd.Timestamp | None
    trigger: str | None
    reason: str
    fill_price: float | None = None


@dataclass(frozen=True)
class PositionResult:
    """포지션 하나(매수 조합 × 매도 조합 × 사이클)의 성적 — 비율은 0 ~ 1 이다

    Attributes:
        avg_buy_price: 체결한 매수 회차의 평균 단가(같은 금액 — 조화평균). 한 회차도 못 샀으면 `None`
        avg_sell_price: 매도 회차 체결가의 평균(같은 수량) — 손절 체결 회차는 체결가, 나머지는 그날 종가다. 포지션이
            끝나지 않았으면 `None`
        return_rate: 평균 매도가 ÷ 평균 매수가 − 1. 포지션이 끝나지 않았으면 `None`
        worst_vs_cost: 첫 매수 다음 날부터 마지막 매도일(끝나지 않았으면 데이터 끝)까지, 그날 전에 산 회차의 평균 단가
            대비 장중 저가의 최저. 손절 체결로 끝난 날은 장중 저가 대신 체결가까지만 센다. 셀 날이 없으면 `None`
        first_buy_day: 첫 매수일
        last_sell_day: 마지막 매도일. 끝나지 않았으면 `None`
        hold_days: 첫 매수일부터 마지막 매도일까지의 날 수. 끝나지 않았으면 `None`
        buy_counts: (온체인 회차 수, 달력 회차 수)
        sell_counts: (온체인 회차 수, 달력 회차 수)
        reason: 제외 사유. 끝났으면 `REASON_NONE`
    """

    avg_buy_price: float | None
    avg_sell_price: float | None
    return_rate: float | None
    worst_vs_cost: float | None
    first_buy_day: pd.Timestamp | None
    last_sell_day: pd.Timestamp | None
    hold_days: int | None
    buy_counts: tuple[int, int]
    sell_counts: tuple[int, int]
    reason: str


@dataclass(frozen=True)
class SplitGrid:
    """혼합 분할 격자의 표 셋 (내부 컬럼 토큰)

    Attributes:
        fills: 쪽 × 조합 × 사이클 × 회차. **체결 전 회차도 행이 있다**
        positions: 매수 조합 × 매도 조합 × 사이클 (사이클이 가장 안쪽). **끝나지 않은 포지션도 행이 있다**
        combinations: 매수 조합 × 매도 조합 — 사이클별 수익률 · 평균 단가 대비 최악을 가로로, 끝난 포지션의 집계를 함께
    """

    fills: pd.DataFrame
    positions: pd.DataFrame
    combinations: pd.DataFrame


@dataclass(frozen=True)
class StopOutcome:
    """달력 매달 분할 한 포지션의 손절 방식 하나 — 손절 표 한 행을 만든 성적 그대로 (결정 58 · 61)

    **체결 조립(`trading.py`)이 확정 규칙 행을 이것으로 만든다** — 손절 표는 첫 매수일 · 보유 날 수를 싣지 않고,
    표에서 산식을 다시 쓰면 두 벌이 된다(절대 원칙 5).

    Attributes:
        split: 폭
        halving: 포지션을 산 반감기
        method: 손절 방식 — `NO_STOP_LABEL` 또는 `STOP_METHOD_LOW_BREAK`
        result: 그 손절 방식의 포지션 성적. 손절한 포지션은 남은 매도 회차를 이탈일의 손절 체결로 옮긴 성적이다.
            손절 표의 제외 사유는 `result.reason` 이다
        fork_share: 하드포크 몫 (비율). 끝나지 않았으면 `None`
        exit_reason: 저점 이탈로 남은 보유를 판 체결의 청산 사유 — `EXIT_GAP_STOP` · `EXIT_INTRADAY_STOP`. 팔지 않았으면 `None`
    """

    split: CalendarSplit
    halving: Halving
    method: str
    result: PositionResult
    fork_share: float | None
    exit_reason: str | None


@dataclass(frozen=True)
class CalendarSplitGrid:
    """달력 매달 분할의 표 셋 (내부 컬럼 토큰)과 손절 표를 만든 결과

    Attributes:
        fills: 폭 × 반감기 × 쪽 × 회차. **체결 전 회차와 다음 반감기가 없는 매도 회차도 행이 있다**
        positions: 폭 × 반감기. **끝나지 않은 포지션도 행이 있다**
        stops: 폭 × 반감기 × 손절 방식(무손절 · 저점 이탈) — 결정 58. **끝나지 않은 포지션도 두 행이 있다**
        outcomes: `stops` 의 행마다 하나, 같은 순서 — 표로 바뀌기 전의 성적
    """

    fills: pd.DataFrame
    positions: pd.DataFrame
    stops: pd.DataFrame
    outcomes: tuple[StopOutcome, ...]


@dataclass(frozen=True)
class _LowBreak:
    """달력 매달 분할 한 포지션의 저점 이탈 (결정 58 · 64)

    Attributes:
        line_day: 손절선을 만든 날
        line_low: 손절선 — 사이클 고점 다음 날부터 마지막 매수일까지의 최저 장중 저가
        break_day: 이탈일 — 감시 중 장중 저가가 손절선에 처음 닿은 날. 그날 판다. 없으면 `None`
        fill_price: 손절 체결가 — 손절선, 그날 시가가 이미 손절선 이하면 그 시가. 이탈이 없으면 `None`
        exit_reason: 청산 사유 — `EXIT_GAP_STOP` · `EXIT_INTRADAY_STOP`. 이탈이 없으면 `None`
    """

    line_day: pd.Timestamp
    line_low: float
    break_day: pd.Timestamp | None
    fill_price: float | None
    exit_reason: str | None


def _require_increasing(index: pd.Index, label: str) -> pd.DatetimeIndex:
    """날짜 인덱스가 오름차순이고 겹치지 않는지 검사한다.

    Args:
        index: 검사할 인덱스
        label: 메시지에 쓸 이름

    Returns:
        날짜 인덱스

    Raises:
        ValueError: 오름차순이 아니거나 겹치는 날짜가 있는 경우
    """
    days = pd.DatetimeIndex(index)
    if not days.is_monotonic_increasing or not days.is_unique:
        raise ValueError(f"{label}의 날짜가 오름차순이 아니거나 겹칩니다")

    return days


def trailing_rank(values: pd.Series, *, years: int, min_days: int) -> pd.Series:
    """날마다 **그날까지 `years` 년 창**((d − years, d])에서 그날 값 이하인 관측의 비율을 낸다.

    **그날 자신을 포함하고 동점은 「이하」로 센다.** 그날까지의 값만 쓰므로 미래를 보지 않는다.

    Args:
        values: 날짜 인덱스(오름차순)의 값
        years: 창의 길이(년). 없는 날짜(2월 29일 − 1년)는 그 달 말일로 당긴다
        min_days: 창의 관측이 이보다 적으면 비운다

    Returns:
        같은 인덱스의 비율(0 ~ 1). 관측이 모자란 날은 NaN

    Raises:
        ValueError: 창 · 최소 관측이 1 보다 작거나, 날짜가 오름차순이 아니거나, 값에 결측이 있는 경우 —
            결측을 건너뛰면 창의 관측 수가 달라져 순위가 예외 없이 바뀐다
    """
    if years < 1 or min_days < 1:
        raise ValueError(f"창(년)과 최소 관측은 1 이상이어야 합니다: {years} · {min_days}")
    days = _require_increasing(values.index, "순위를 낼 계열")
    array = values.to_numpy(dtype=float)
    if np.isnan(array).any():
        raise ValueError("순위를 낼 계열에 결측이 있습니다 — 로더를 지난 계열을 넘기세요")

    lefts = days.searchsorted(days - pd.DateOffset(years=years), side="right")
    ranks = np.full(len(array), np.nan)
    for position, left in enumerate(lefts.tolist()):
        count = position + 1 - left
        if count >= min_days:
            ranks[position] = np.count_nonzero(array[left : position + 1] <= array[position]) / count

    return pd.Series(ranks, index=values.index, name=values.name)


def new_high_flags(close: pd.Series) -> pd.Series:
    """그날 종가가 **그 전의 모든 종가**보다 높은가 — 첫 날은 거짓이다.

    Args:
        close: 날짜 인덱스(오름차순)의 종가

    Returns:
        같은 인덱스의 bool

    Raises:
        ValueError: 날짜가 오름차순이 아닌 경우
    """
    _require_increasing(close.index, "종가")
    array = close.to_numpy(dtype=float)
    flags = np.zeros(len(array), dtype=bool)
    if len(array) > 1:
        flags[1:] = array[1:] > np.maximum.accumulate(array)[:-1]

    return pd.Series(flags, index=close.index)


def window_open(
    trading_days: pd.DatetimeIndex, leg: SplitLeg, anchor_day: pd.Timestamp, new_highs: pd.Series
) -> np.ndarray:
    """그날 그 쪽의 창이 열려 있는가.

    **반감기 기준**은 기준일 + N개월부터 열려 있다. **신고가 기준**은 기준일 뒤 신고가가 한 번 이상 났고 가장 최근
    신고가에서 N개월이 지난 날에 열려 있다 — 새 신고가가 나면 다시 닫힌다. 둘 다 그날까지의 종가로만 정한다.

    Args:
        trading_days: 거래일
        leg: 조합
        anchor_day: 기준 반감기일
        new_highs: `new_high_flags` 의 결과 (거래일을 덮는 인덱스)

    Returns:
        거래일마다 bool

    Raises:
        ValueError: 달력만 조합이거나, 창의 기준을 모르거나, 신고가 판정이 거래일을 덮지 못하는 경우
    """
    if leg.threshold == SPLIT_THRESHOLD_NONE or leg.start_anchor is None or leg.start_months is None:
        raise ValueError("달력만 조합에는 창이 없습니다 — 창은 문턱이 있는 조합에만 있습니다")

    if leg.start_anchor == SPLIT_ANCHOR_HALVING:
        return np.asarray(trading_days >= anchor_day + pd.DateOffset(months=leg.start_months))

    if leg.start_anchor == SPLIT_ANCHOR_HIGH:
        flags = new_highs.reindex(trading_days)
        if flags.isna().any():
            raise ValueError("신고가 판정이 거래일을 덮지 못합니다 — 같은 시세로 낸 판정을 넘기세요")
        highs = flags.to_numpy(dtype=bool) & np.asarray(trading_days >= anchor_day)
        latest = pd.Series(trading_days.where(highs)).ffill()
        opens_from = latest + pd.DateOffset(months=leg.start_months)

        return (latest.notna() & (pd.Series(trading_days) >= opens_from)).to_numpy(dtype=bool)

    raise ValueError(f"창의 기준을 모릅니다: {leg.start_anchor}")


def tranche_deadlines(
    anchor_day: pd.Timestamp, last_deadline: int, *, tranches: int, step_months: int, month_end: bool
) -> list[pd.Timestamp]:
    """회차 기한 — 마지막 기한에서 `step_months` 씩 앞으로.

    기한이 m개월인 회차의 날은 기준일 + m개월이다(m 은 첫 기한부터 간격씩 는다). `month_end` 면 그날이 속한 달의
    말일이고(결정 54 — 실제로 체결할 수 있는 날), 아니면 같은 날짜이며 없는 날짜는 그 달 말일로 당긴다.

    Args:
        anchor_day: 기준 반감기일
        last_deadline: 마지막 회차 기한 (기준 반감기 뒤 개월)
        tranches: 회차 수
        step_months: 기한 간격(개월)
        month_end: 그 달의 말일로 옮기는가

    Returns:
        회차 순서의 기한

    Raises:
        ValueError: 회차 수 · 간격이 1 보다 작거나, 첫 회차 기한이 기준 반감기 앞인 경우
    """
    if tranches < 1 or step_months < 1:
        raise ValueError(f"회차 수와 기한 간격은 1 이상이어야 합니다: {tranches} · {step_months}")
    first = last_deadline - step_months * (tranches - 1)
    if first < 0:
        raise ValueError(f"첫 회차 기한이 기준 반감기 앞입니다: 마지막 {last_deadline}개월 · {tranches}회 · {step_months}개월 간격")

    days = [anchor_day + pd.DateOffset(months=first + step_months * tranche) for tranche in range(tranches)]
    if month_end:
        return [day + pd.offsets.MonthEnd(0) for day in days]

    return days


def _validate_leg(leg: SplitLeg, tranches: int, trigger_values: pd.Series | None) -> None:
    """조합과 입력이 맞는지 검사한다.

    Args:
        leg: 조합
        tranches: 회차 수
        trigger_values: 문턱에 견줄 값

    Raises:
        ValueError: 쪽 · 문턱 방식을 모르거나, 달력만 조합에 창 · 문턱이 있거나, 문턱 수가 회차 수와 다르거나,
            문턱이 회차 순서(매수는 내려가고 매도는 올라간다)가 아니거나, 문턱 조합에 견줄 값이 없는 경우
    """
    if leg.side not in (SPLIT_SIDE_BUY, SPLIT_SIDE_SELL):
        raise ValueError(f"매수 · 매도를 모릅니다: {leg.side}")
    if leg.threshold == SPLIT_THRESHOLD_NONE:
        if leg.levels or leg.start_anchor is not None or leg.start_months is not None:
            raise ValueError(f"달력만 조합에 창이나 문턱이 있습니다: {leg}")
        return
    if leg.threshold not in (SPLIT_THRESHOLD_BOOK, SPLIT_THRESHOLD_RANK):
        raise ValueError(f"문턱 방식을 모릅니다: {leg.threshold}")
    # **창이 기준 반감기 앞으로 열리지 않게 한다** — 온체인 회차가 반감기 앞에 체결되는 것을 막는 자리가 창 하나다
    if leg.start_months is None or leg.start_months < 0:
        raise ValueError(f"창이 열리는 개월은 0 이상이어야 합니다: {leg.start_months}")
    if len(leg.levels) != tranches:
        raise ValueError(f"문턱 수({len(leg.levels)})가 회차 수({tranches})와 다릅니다: {leg}")
    steps = np.diff(np.asarray(leg.levels, dtype=float))
    ordered = bool((steps < 0).all()) if leg.side == SPLIT_SIDE_BUY else bool((steps > 0).all())
    if not ordered:
        raise ValueError(f"문턱이 회차 순서가 아닙니다 — 매수는 내려가고 매도는 올라가야 합니다: {leg.levels}")
    if trigger_values is None:
        raise ValueError(f"문턱 조합에는 견줄 값이 필요합니다: {leg.threshold}")


def leg_fills(
    trading_days: pd.DatetimeIndex,
    leg: SplitLeg,
    anchor_day: pd.Timestamp,
    *,
    trigger_values: pd.Series | None,
    new_highs: pd.Series,
    tranches: int,
    step_months: int,
    month_end: bool,
) -> list[TrancheFill]:
    """한쪽의 회차 체결일을 낸다 — 회차 k 는 min(문턱 k 에 처음 닿은 날의 다음 거래일, 기한 k) 이다.

    **문턱 판정은 기한 «전»의 날에서만 찾는다** — 기한 당일에 닿으면 다음날이 기한 뒤라 달력이 먼저다. 다음날이 곧
    기한이면 온체인으로 적는다. 값이 빈 날은 판정하지 않는다.

    Args:
        trading_days: 거래일 (휴장 없는 연속 날짜)
        leg: 조합
        anchor_day: 기준 반감기일
        trigger_values: 문턱에 견줄 값 (날짜 인덱스). 달력만이면 `None`
        new_highs: `new_high_flags` 의 결과
        tranches: 회차 수
        step_months: 기한 간격(개월)
        month_end: 기한을 그 달의 말일로 옮기는가 (`tranche_deadlines`)

    Returns:
        회차 순서의 체결. 기한이 데이터 뒤이고 온체인으로도 체결하지 못한 회차는 체결 전이다

    Raises:
        ValueError: 조합과 입력이 어긋나거나, 데이터 안의 기한이 거래일 목록에 없는 경우 — 휴장이 없는 시세라
            그런 날은 데이터의 빈틈이다(옮기면 다른 날을 잰다)
        RuntimeError: 회차 체결일이 회차 순서대로 오르지 않는 경우 (내부 불변조건)
    """
    _validate_leg(leg, tranches, trigger_values)
    deadlines = tranche_deadlines(
        anchor_day, leg.last_deadline, tranches=tranches, step_months=step_months, month_end=month_end
    )
    last_day = trading_days[-1]
    trading_positions(trading_days, pd.DatetimeIndex([day for day in deadlines if day <= last_day]), label="회차 기한")

    hits: list[int | None] = [None] * tranches
    if trigger_values is not None:
        opened = window_open(trading_days, leg, anchor_day, new_highs)
        values = trigger_values.reindex(trading_days).to_numpy(dtype=float)
        valid = ~np.isnan(values)
        for tranche, level in enumerate(leg.levels):
            reached = values <= level if leg.side == SPLIT_SIDE_BUY else values >= level
            before_deadline = np.asarray(trading_days < deadlines[tranche])
            candidates = np.flatnonzero(opened & valid & reached & before_deadline)
            hits[tranche] = int(candidates[0]) if len(candidates) else None

    fills: list[TrancheFill] = []
    for deadline, hit in zip(deadlines, hits, strict=True):
        onchain_day = pd.Timestamp(trading_days[hit + 1]) if hit is not None and hit + 1 < len(trading_days) else None
        deadline_in_data = deadline <= last_day
        if onchain_day is not None and (not deadline_in_data or onchain_day <= deadline):
            fills.append(TrancheFill(deadline, onchain_day, SPLIT_TRIGGER_ONCHAIN, REASON_NONE))
        elif deadline_in_data:
            fills.append(TrancheFill(deadline, deadline, SPLIT_TRIGGER_CALENDAR, REASON_NONE))
        else:
            fills.append(TrancheFill(deadline, None, None, REASON_SPLIT_PENDING))

    filled = [fill.fill_day for fill in fills if fill.fill_day is not None]
    if filled != sorted(filled):
        raise RuntimeError(f"내부 불변조건 위반: 회차 체결일이 회차 순서대로 오르지 않습니다: {filled}")

    return fills


def _trigger_counts(fills: Sequence[TrancheFill]) -> tuple[int, int]:
    """체결한 회차를 계기별로 센다.

    Args:
        fills: 회차

    Returns:
        (온체인 회차 수, 달력 회차 수)
    """
    triggers = [fill.trigger for fill in fills]

    return triggers.count(SPLIT_TRIGGER_ONCHAIN), triggers.count(SPLIT_TRIGGER_CALENDAR)


def _fill_prices(
    dates: pd.DatetimeIndex, closes: np.ndarray, fills: Sequence[TrancheFill], *, label: str
) -> np.ndarray:
    """체결한 회차의 체결가 — 회차가 체결가를 들면(손절 체결) 그 값, 아니면 그날 종가. 회차 순서 그대로다.

    Args:
        dates: 시세의 날짜
        closes: 같은 순서의 종가
        fills: 회차
        label: 메시지에 쓸 이름

    Returns:
        체결한 회차마다의 체결가
    """
    filled = [(fill.fill_day, fill.fill_price) for fill in fills if fill.fill_day is not None]
    # **없는 날짜에서 멈춘다** — `get_indexer` 는 없는 날짜에 −1 을 돌려줘 마지막 행의 가격을 예외 없이 쓴다
    on_day = closes[trading_positions(dates, pd.DatetimeIndex([day for day, _ in filled]), label=label)]

    return np.array(
        [close if price is None else price for (_, price), close in zip(filled, on_day, strict=True)], dtype=float
    )


def position_result(
    frame: pd.DataFrame, buy_fills: Sequence[TrancheFill], sell_fills: Sequence[TrancheFill] | None
) -> PositionResult:
    """포지션 하나의 성적을 낸다.

    **매수는 같은 금액, 매도는 보유량의 같은 몫이다** — 그래서 평균 매수가는 회차 종가의 조화평균, 평균 매도가는
    산술평균이고, 끝난 포지션의 수익률은 (매수 회차 × 매도 회차) 칸 수익률의 평균과 같다(결정 ㊱).

    **평균 단가 대비 최악은 그날 «전»에 산 회차만 센다** — 그날 종가에 산 회차는 그날 장중을 겪지 않았다. 첫 매수일
    장중도 같은 이유로 세지 않고, 마지막 매도일 뒤는 들고 있지 않은 기간이다. **손절 체결(체결가를 든 매도 회차)로 끝난
    날은 장중 저가 대신 그 체결가까지만 센다** — 그 가격에 다 팔고 나와 그날의 나머지는 들고 있지 않은 시간이다.

    Args:
        frame: 측정 시세 (날짜 · 종가 · 저가, 날짜 오름차순)
        buy_fills: 매수 회차
        sell_fills: 매도 회차. 다음 반감기가 반감기 목록에 없으면 `None`. 체결가를 든 회차는 그 값에 판 것이다

    Returns:
        포지션 성적. 끝나지 않은 이유는 매수가 남음 → 다음 반감기 없음 → 매도가 남음 순으로 적는다

    Raises:
        RuntimeError: 매도 회차가 매수가 끝나기 전(마지막 매수일 이전)에 있거나, 체결가를 든 매도 회차가 포지션이 끝나는
            날(마지막 매도일) 말고 있는 경우 (내부 불변조건 — 그 뒤에도 들고 있으면 그날을 체결가까지만 센 최악이 틀린다)
    """
    dates = pd.DatetimeIndex(frame[COL_DATE])
    closes = frame[COL_CLOSE].to_numpy(dtype=float)
    lows = frame[COL_LOW].to_numpy(dtype=float)

    buy_days = [fill.fill_day for fill in buy_fills if fill.fill_day is not None]
    sell_days = [fill.fill_day for fill in sell_fills or () if fill.fill_day is not None]
    buy_done = len(buy_days) == len(buy_fills)
    if sell_days and (not buy_done or min(sell_days) <= max(buy_days)):
        raise RuntimeError(f"내부 불변조건 위반: 매도 회차가 매수가 끝나기 전에 있습니다 — 매수 {buy_days} · 매도 {sell_days}")

    if not buy_done:
        reason = REASON_POSITION_BUYING
    elif sell_fills is None:
        reason = REASON_NO_NEXT_HALVING
    elif len(sell_days) < len(sell_fills):
        reason = REASON_POSITION_SELLING
    else:
        reason = REASON_NONE

    stop_prices = [fill.fill_price for fill in sell_fills or () if fill.fill_price is not None]
    stop_days = {fill.fill_day for fill in sell_fills or () if fill.fill_price is not None}
    if stop_prices and (reason != REASON_NONE or stop_days != {max(sell_days)}):
        raise RuntimeError(
            f"내부 불변조건 위반: 체결가를 든 매도 회차는 포지션이 끝나는 날에만 옵니다 — 사유 {reason} · 그 회차 {stop_days} · " f"매도 {sell_days}"
        )

    buy_prices = _fill_prices(dates, closes, buy_fills, label="매수 체결일")
    avg_buy = len(buy_prices) / float(np.sum(1.0 / buy_prices)) if buy_days else None

    avg_sell: float | None = None
    return_rate: float | None = None
    last_sell: pd.Timestamp | None = None
    hold_days: int | None = None
    if reason == REASON_NONE and avg_buy is not None:
        avg_sell = float(np.mean(_fill_prices(dates, closes, sell_fills or (), label="매도 체결일")))
        return_rate = avg_sell / avg_buy - 1.0
        last_sell = max(sell_days)
        hold_days = (last_sell - min(buy_days)).days

    worst: float | None = None
    if buy_days:
        order = np.argsort(pd.DatetimeIndex(buy_days).to_numpy(), kind="stable")
        sorted_days = pd.DatetimeIndex(buy_days)[order]
        cumulative_inverse = np.cumsum(1.0 / buy_prices[order])
        end = last_sell if last_sell is not None else dates[-1]
        window = (dates > sorted_days[0]) & (dates <= end)
        if window.any():
            held = sorted_days.searchsorted(dates[window], side="left")
            costs = held / cumulative_inverse[held - 1]
            held_lows = lows[window]
            if stop_prices:
                # 구간의 마지막 날이 곧 손절 체결일이다 — 위 불변조건이 그 날을 마지막 매도일로 묶었다
                held_lows[-1] = min(stop_prices)
            worst = float(np.min(held_lows / costs - 1.0))

    return PositionResult(
        avg_buy_price=avg_buy,
        avg_sell_price=avg_sell,
        return_rate=return_rate,
        worst_vs_cost=worst,
        first_buy_day=min(buy_days) if buy_days else None,
        last_sell_day=last_sell,
        hold_days=hold_days,
        buy_counts=_trigger_counts(buy_fills),
        sell_counts=_trigger_counts(sell_fills or ()),
        reason=reason,
    )


def split_legs(
    side: str,
    *,
    halving_starts: Sequence[int],
    high_starts: Sequence[int],
    last_deadlines: Sequence[int],
    book_levels: tuple[float, ...],
    rank_levels: tuple[float, ...],
) -> tuple[SplitLeg, ...]:
    """한쪽의 조합 전부를 만든다 — 달력만(기한마다 하나) 다음에 문턱 방식 × 창 기준 × 창 개월 × 기한.

    **달력만은 창 없이 기한마다 한 조합이다** — 창이 결과를 바꾸지 않아, 창마다 내면 같은 결과가 여러 행이 되어
    평평한 구간처럼 보인다.

    Args:
        side: 매수 · 매도
        halving_starts: 반감기 기준 창의 개월 목록
        high_starts: 신고가 기준 창의 개월 목록 (매도는 빈 목록)
        last_deadlines: 마지막 기한 목록
        book_levels: 책 고정 문턱
        rank_levels: 순위 문턱

    Returns:
        조합 목록
    """
    legs = [SplitLeg(side, SPLIT_THRESHOLD_NONE, (), None, None, deadline) for deadline in last_deadlines]
    for threshold, levels in ((SPLIT_THRESHOLD_BOOK, book_levels), (SPLIT_THRESHOLD_RANK, rank_levels)):
        for anchor, starts in ((SPLIT_ANCHOR_HALVING, halving_starts), (SPLIT_ANCHOR_HIGH, high_starts)):
            legs.extend(
                SplitLeg(side, threshold, tuple(levels), anchor, start, deadline)
                for start in starts
                for deadline in last_deadlines
            )

    return tuple(legs)


def _number(value: float | None) -> float:
    """빈 값을 NaN 으로 — **열 전체가 비어도 실수 열로 남게 한다.** `None` 만 모인 열은 object 가 되어 백분율 변환에서 멈춘다.

    Args:
        value: 값 또는 `None`

    Returns:
        실수 (없으면 NaN)
    """
    return np.nan if value is None else value


def _value_on(series: pd.Series, day: pd.Timestamp) -> float:
    """그날의 값. 없으면 NaN.

    Args:
        series: 날짜 인덱스의 값
        day: 날짜

    Returns:
        값
    """
    value = series.get(day)

    return float(value) if value is not None else np.nan


def _fill_rows(
    leg: SplitLeg,
    halving: Halving,
    anchor: Halving | None,
    fills: Sequence[TrancheFill] | None,
    *,
    tranches: int,
    closes: pd.Series,
    mvrv: pd.Series | None,
    ranks: pd.Series | None,
) -> list[dict[str, Any]]:
    """회차 표의 행 — 회차마다 하나. 기준 반감기가 없으면(다음 반감기가 목록에 없는 매도) 회차 칸만 두고 사유를 단다.

    Args:
        leg: 조합
        halving: 포지션의 반감기
        anchor: 그 쪽의 기준 반감기. 없으면 `None`
        fills: 회차 체결. 기준 반감기가 없으면 `None`
        tranches: 회차 수
        closes: 날짜 인덱스의 종가
        mvrv: 날짜 인덱스의 MVRV. `None` 이면 체결 전날 MVRV · 순위 칸을 싣지 않는다(달력 매달 분할)
        ranks: 날짜 인덱스의 순위. `mvrv` 와 함께 `None` 이다

    Returns:
        행 목록
    """
    identity = {
        COL_SPLIT_SIDE: leg.side,
        COL_SPLIT_THRESHOLD: leg.threshold,
        COL_SPLIT_START_ANCHOR: leg.start_anchor,
        COL_SPLIT_START_MONTHS: leg.start_months,
        COL_SPLIT_LAST_DEADLINE: leg.last_deadline,
        COL_HALVING: halving.label,
        COL_SPLIT_ANCHOR_HALVING: anchor.label if anchor is not None else None,
    }
    if anchor is None or fills is None:
        return [
            {**identity, COL_SPLIT_TRANCHE: tranche + 1, COL_EXCLUDED_REASON: REASON_NO_NEXT_HALVING}
            for tranche in range(tranches)
        ]

    rows: list[dict[str, Any]] = []
    for tranche, fill in enumerate(fills):
        row: dict[str, Any] = {
            **identity,
            COL_SPLIT_TRANCHE: tranche + 1,
            COL_SPLIT_DEADLINE: fill.deadline,
            COL_SPLIT_TRIGGER: fill.trigger,
            COL_EXCLUDED_REASON: fill.reason,
        }
        if fill.fill_day is not None:
            # **체결 전날의 값** — 온체인 회차는 그날이 판정일이고, 달력 회차도 체결 시점에 완성된 값이 전날 것이다
            prior_day = fill.fill_day - pd.Timedelta(1, unit="D")
            row |= {
                COL_SPLIT_FILL_DATE: fill.fill_day,
                COL_MONTHS_SINCE_HALVING: months_since(anchor.day, fill.fill_day),
                COL_SPLIT_FILL_CLOSE: float(closes[fill.fill_day]),
            }
            if mvrv is not None and ranks is not None:
                row |= {
                    COL_SPLIT_PRIOR_MVRV: _value_on(mvrv, prior_day),
                    COL_SPLIT_PRIOR_RANK: _value_on(ranks, prior_day),
                }
        rows.append(row)

    return rows


def _leg_identity(buy: SplitLeg, sell: SplitLeg) -> dict[str, Any]:
    """포지션 · 조합 표의 식별 칸.

    Args:
        buy: 매수 조합
        sell: 매도 조합

    Returns:
        식별 칸
    """
    return {
        COL_BUY_THRESHOLD: buy.threshold,
        COL_BUY_START_ANCHOR: buy.start_anchor,
        COL_BUY_START_MONTHS: buy.start_months,
        COL_BUY_LAST_DEADLINE: buy.last_deadline,
        COL_SELL_THRESHOLD: sell.threshold,
        COL_SELL_START_MONTHS: sell.start_months,
        COL_SELL_LAST_DEADLINE: sell.last_deadline,
    }


def _combination_row(
    identity: dict[str, Any], halvings: Sequence[Halving], results: Sequence[PositionResult]
) -> dict[str, Any]:
    """조합 표의 한 행 — 사이클별 수익률을 가로로, 끝난 포지션의 집계를 함께 (측정의 원칙 4 · 16).

    Args:
        identity: 식별 칸
        halvings: 반감기 목록
        results: 반감기 순서의 포지션 성적

    Returns:
        행
    """
    returns = pd.Series([result.return_rate for result in results], dtype=float)
    finished = returns.dropna()
    has_finished = not finished.empty

    return {
        **identity,
        **{
            COL_CYCLE_RETURN_TEMPLATE.format(halving=halving.label): _number(result.return_rate)
            for halving, result in zip(halvings, results, strict=True)
        },
        COL_FINISHED_COUNT: len(finished),
        COL_MEAN: float(finished.mean()) if has_finished else np.nan,
        COL_MEDIAN: float(finished.median()) if has_finished else np.nan,
        COL_SPLIT_TOTAL: float(finished.sum()) if has_finished else np.nan,
        COL_MIN: float(finished.min()) if has_finished else np.nan,
        # **끝난 포지션이 없으면 비운다** — 0 은 「오른 적이 없다」로 읽힌다
        COL_POSITIVE_COUNT: int((finished > 0).sum()) if has_finished else None,
        **{
            COL_CYCLE_WORST_TEMPLATE.format(halving=halving.label): _number(result.worst_vs_cost)
            for halving, result in zip(halvings, results, strict=True)
        },
    }


def _frame_of(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """행 목록을 표로 — 결측을 견디는 정수 컬럼을 `Int64` 로, 날짜 컬럼을 날짜형으로 맞춘다.

    Args:
        rows: 행 목록

    Returns:
        표
    """
    table = pd.DataFrame(rows)
    for column in _NULLABLE_INTEGER_COLUMNS:
        if column in table.columns:
            table[column] = table[column].astype("Int64")
    for column in _DATE_COLUMNS:
        if column in table.columns:
            table[column] = pd.to_datetime(table[column])

    return table


_FILL_COLUMNS = [
    COL_SPLIT_SIDE,
    COL_SPLIT_THRESHOLD,
    COL_SPLIT_START_ANCHOR,
    COL_SPLIT_START_MONTHS,
    COL_SPLIT_LAST_DEADLINE,
    COL_HALVING,
    COL_SPLIT_ANCHOR_HALVING,
    COL_SPLIT_TRANCHE,
    COL_SPLIT_DEADLINE,
    COL_SPLIT_FILL_DATE,
    COL_MONTHS_SINCE_HALVING,
    COL_SPLIT_FILL_CLOSE,
    COL_SPLIT_TRIGGER,
    COL_SPLIT_PRIOR_MVRV,
    COL_SPLIT_PRIOR_RANK,
    COL_EXCLUDED_REASON,
]


def split_grid(
    frame: pd.DataFrame,
    mvrv: pd.Series,
    halvings: Sequence[Halving],
    buy_legs: Sequence[SplitLeg],
    sell_legs: Sequence[SplitLeg],
    *,
    tranches: int,
    step_months: int,
    rank_years: int,
    rank_min_days: int,
) -> SplitGrid:
    """혼합 분할 격자 전부를 낸다 — 포지션은 반감기마다, 반감기 뒤에 사서 다음 반감기 뒤에 판다.

    **4년 순위와 신고가는 한 번만 계산한다** — 조합마다 다시 내면 같은 값을 수백 번 계산한다.
    **마지막 반감기의 포지션은 다음 반감기가 목록에 없어 매도 회차가 정의되지 않는다** — 행은 남고 사유가 붙는다.

    Args:
        frame: 측정 시세 (날짜 · 종가 · 저가, 날짜 오름차순 · 휴장 없음)
        mvrv: 날짜 인덱스의 MVRV (결측 없음)
        halvings: 반감기 목록 (날짜 오름차순)
        buy_legs: 매수 조합
        sell_legs: 매도 조합. 창의 기준은 반감기 하나다
        tranches: 회차 수
        step_months: 기한 간격(개월)
        rank_years: 순위 창(년)
        rank_min_days: 순위의 최소 관측일

    Returns:
        표 셋

    Raises:
        ValueError: 반감기 · 조합이 비었거나, 매도 조합의 창 기준이 반감기가 아니거나, 쪽이 어긋난 조합이 섞인 경우
        RuntimeError: 매수 마지막 기한이 다음 반감기와 같거나 뒤인 경우 (내부 불변조건 — 매도는 매수가 끝난 뒤에만 온다)
    """
    if not halvings or not buy_legs or not sell_legs:
        raise ValueError("반감기와 매수 · 매도 조합이 하나 이상 있어야 합니다")
    if any(leg.side != SPLIT_SIDE_BUY for leg in buy_legs) or any(leg.side != SPLIT_SIDE_SELL for leg in sell_legs):
        raise ValueError("매수 조합과 매도 조합에 다른 쪽의 조합이 섞였습니다")
    if any(leg.start_anchor not in (None, SPLIT_ANCHOR_HALVING) for leg in sell_legs):
        raise ValueError("매도 창의 기준은 다음 반감기 하나입니다 — 표가 다른 기준을 담지 못합니다")

    trading_days = _require_increasing(pd.Index(frame[COL_DATE]), "시세")
    closes = pd.Series(frame[COL_CLOSE].to_numpy(dtype=float), index=trading_days)
    new_highs = new_high_flags(closes)
    ranks = trailing_rank(mvrv, years=rank_years, min_days=rank_min_days)
    trigger_values = {SPLIT_THRESHOLD_BOOK: mvrv, SPLIT_THRESHOLD_RANK: ranks}

    # 혼합 분할의 달력 기한은 반감기와 같은 날짜다 — 측정 기록(결정 ㊻)이라 달력 분할의 월말(결정 54)을 따르지 않는다
    def fills_for(leg: SplitLeg, anchor: Halving) -> list[TrancheFill]:
        return leg_fills(
            trading_days,
            leg,
            anchor.day,
            trigger_values=trigger_values.get(leg.threshold),
            new_highs=new_highs,
            tranches=tranches,
            step_months=step_months,
            month_end=False,
        )

    buy_fills: dict[tuple[int, int], list[TrancheFill]] = {}
    sell_fills: dict[tuple[int, int], list[TrancheFill] | None] = {}
    for cycle, halving in enumerate(halvings):
        following = halvings[cycle + 1] if cycle + 1 < len(halvings) else None
        for index, leg in enumerate(buy_legs):
            fills = fills_for(leg, halving)
            if following is not None and fills[-1].deadline >= following.day:
                raise RuntimeError(
                    f"내부 불변조건 위반: 매수 마지막 기한({fills[-1].deadline.date()})이 다음 반감기"
                    f"({following.label})와 같거나 뒤입니다 — 매도는 매수가 끝난 뒤에만 와야 합니다"
                )
            buy_fills[index, cycle] = fills
        for index, leg in enumerate(sell_legs):
            sell_fills[index, cycle] = fills_for(leg, following) if following is not None else None

    fill_rows: list[dict[str, Any]] = []
    for legs, fills_by_key, is_buy in ((buy_legs, buy_fills, True), (sell_legs, sell_fills, False)):
        for index, leg in enumerate(legs):
            for cycle, halving in enumerate(halvings):
                anchor = halving if is_buy else (halvings[cycle + 1] if cycle + 1 < len(halvings) else None)
                fill_rows.extend(
                    _fill_rows(
                        leg,
                        halving,
                        anchor,
                        fills_by_key[index, cycle],
                        tranches=tranches,
                        closes=closes,
                        mvrv=mvrv,
                        ranks=ranks,
                    )
                )

    position_rows: list[dict[str, Any]] = []
    combination_rows: list[dict[str, Any]] = []
    for buy_index, buy in enumerate(buy_legs):
        for sell_index, sell in enumerate(sell_legs):
            identity = _leg_identity(buy, sell)
            results = [
                position_result(frame, buy_fills[buy_index, cycle], sell_fills[sell_index, cycle])
                for cycle in range(len(halvings))
            ]
            for halving, result in zip(halvings, results, strict=True):
                position_rows.append(
                    {
                        **identity,
                        COL_HALVING: halving.label,
                        COL_AVG_BUY_PRICE: _number(result.avg_buy_price),
                        COL_AVG_SELL_PRICE: _number(result.avg_sell_price),
                        COL_POSITION_RETURN: _number(result.return_rate),
                        COL_WORST_VS_COST: _number(result.worst_vs_cost),
                        COL_FIRST_BUY_DATE: result.first_buy_day,
                        COL_LAST_SELL_DATE: result.last_sell_day,
                        COL_HOLD_DAYS: result.hold_days,
                        COL_BUY_ONCHAIN_COUNT: result.buy_counts[0],
                        COL_BUY_CALENDAR_COUNT: result.buy_counts[1],
                        COL_SELL_ONCHAIN_COUNT: result.sell_counts[0],
                        COL_SELL_CALENDAR_COUNT: result.sell_counts[1],
                        COL_EXCLUDED_REASON: result.reason,
                    }
                )
            combination_rows.append(_combination_row(identity, halvings, results))

    return SplitGrid(
        fills=_frame_of(fill_rows).reindex(columns=_FILL_COLUMNS),
        positions=_frame_of(position_rows),
        combinations=_frame_of(combination_rows),
    )


_CALENDAR_FILL_COLUMNS = [
    COL_CALENDAR_SPLIT,
    COL_SPLIT_SIDE,
    COL_HALVING,
    COL_SPLIT_ANCHOR_HALVING,
    COL_SPLIT_TRANCHE,
    COL_SPLIT_DEADLINE,
    COL_SPLIT_FILL_DATE,
    COL_MONTHS_SINCE_HALVING,
    COL_SPLIT_FILL_CLOSE,
    COL_EXCLUDED_REASON,
]

_CALENDAR_POSITION_COLUMNS = [
    COL_CALENDAR_SPLIT,
    COL_BUY_TRANCHES,
    COL_BUY_FIRST_DEADLINE,
    COL_BUY_LAST_DEADLINE,
    COL_SELL_TRANCHES,
    COL_SELL_FIRST_DEADLINE,
    COL_SELL_LAST_DEADLINE,
    COL_HALVING,
    COL_AVG_BUY_PRICE,
    COL_AVG_SELL_PRICE,
    COL_POSITION_RETURN,
    COL_WORST_VS_COST,
    COL_FIRST_BUY_DATE,
    COL_LAST_SELL_DATE,
    COL_HOLD_DAYS,
    COL_BUY_CALENDAR_COUNT,
    COL_SELL_CALENDAR_COUNT,
    COL_EXCLUDED_REASON,
]

_CALENDAR_STOP_COLUMNS = [
    COL_CALENDAR_SPLIT,
    COL_HALVING,
    COL_STOP_METHOD,
    COL_AVG_BUY_PRICE,
    COL_AVG_SELL_PRICE,
    COL_POSITION_RETURN,
    COL_WORST_VS_COST,
    COL_LAST_SELL_DATE,
    COL_FORK_SHARE,
    COL_STOP_LINE_DATE,
    COL_STOP_LINE_LOW,
    COL_STOP_LINE_VS_COST,
    COL_BREAK_DATE,
    COL_STOP_FILL_PRICE,
    COL_SOLD_BEFORE_STOP,
    COL_EXCLUDED_REASON,
]


def _low_break(
    frame: pd.DataFrame,
    halving_day: pd.Timestamp,
    last_buy_day: pd.Timestamp,
    watch_end: pd.Timestamp,
    *,
    peak_window_months: int,
) -> _LowBreak:
    """손절선을 마지막 매수일에 고정하고, 그 다음 날부터 감시 끝까지 장중 저가로 이탈을 찾는다 (결정 58 · 64).

    **손절선은 포지션을 산 반감기의 사이클에서 정한다** — 사이클 고점은 반감기 뒤 고점 창 안의 최고 종가(차트 사이클
    요약과 같은 창)이고, 손절선은 그 다음 날부터 마지막 매수일까지의 최저 장중 저가다. 매수 기간에 난 더 낮은 저가는 팔지
    않고 손절선이 된다. 다음 반감기가 지나도 바꾸지 않는다.

    **걸어 둔 스탑 주문처럼 판다** — 장중 저가가 손절선 «이하»인 첫날 그날 판다. 판정 순서는 시가 → 장중이다: 시가가 이미
    손절선 이하면 그 시가(갭손절), 아니면 손절선(장중손절)이 체결가다. 손절선은 마지막 매수일 종가 뒤에 정해지고 주문은
    그 뒤에 걸리므로 그날까지의 가격만 쓴다.

    Args:
        frame: 측정 시세 (날짜 · 시가 · 종가 · 저가, 휴장 없는 오름차순)
        halving_day: 포지션을 산 반감기일
        last_buy_day: 마지막 매수일
        watch_end: 감시 끝 — 마지막 매도일. 매도가 끝나지 않았으면 데이터 끝
        peak_window_months: 사이클 고점을 찾는 창(개월)

    Returns:
        손절선과 이탈

    Raises:
        ValueError: 반감기일의 종가가 시세에 없는 경우 — 시세가 늦게 시작하면 고점 창의 앞이 비어, 남은 날 중 하나를 고점으로
            물어도 예외가 나지 않는다(차트 사이클 요약 `chart._cycle_segments` 도 같은 이유로 반감기일 종가를 요구한다)
        RuntimeError: 마지막 매수일이 고점 창 안인 경우 (내부 불변조건 — `calendar_split_grid` 가 폭을 먼저 검사한다)
    """
    days = pd.DatetimeIndex(frame[COL_DATE])
    closes = pd.Series(frame[COL_CLOSE].to_numpy(dtype=float), index=days)
    lows = pd.Series(frame[COL_LOW].to_numpy(dtype=float), index=days)
    window_end = halving_day + pd.DateOffset(months=peak_window_months)
    if last_buy_day < window_end:
        raise RuntimeError(f"내부 불변조건 위반: 마지막 매수일({last_buy_day.date()})이 고점 창(반감기 뒤 {peak_window_months}개월) 안입니다")
    if halving_day not in days:
        raise ValueError(f"반감기일({halving_day.date()})의 종가가 시세에 없습니다 — 손절선의 사이클 고점을 찾을 수 없습니다")

    window = closes[(days >= halving_day) & (days < window_end)]
    peak_day = pd.Timestamp(window.idxmax())
    formed = lows[(days > peak_day) & (days <= last_buy_day)]
    line_day = pd.Timestamp(formed.idxmin())
    line_low = float(formed[line_day])

    watched = lows[(days > last_buy_day) & (days <= watch_end)]
    touched = watched[watched <= line_low]
    if touched.empty:
        return _LowBreak(line_day, line_low, None, None, None)

    break_day = pd.Timestamp(touched.index[0])
    opening = float(pd.Series(frame[COL_OPEN].to_numpy(dtype=float), index=days)[break_day])
    if opening <= line_low:
        return _LowBreak(line_day, line_low, break_day, opening, EXIT_GAP_STOP)

    return _LowBreak(line_day, line_low, break_day, line_low, EXIT_INTRADAY_STOP)


def _position_fork_share(
    closes: pd.Series,
    buy_fills: Sequence[TrancheFill],
    sell_fills: Sequence[TrancheFill],
    forks: Sequence[HardFork],
) -> float:
    """끝난 포지션의 하드포크 몫 — (매수 회차 × 매도 회차) 칸마다의 몫의 평균.

    **칸마다 돈이 같다** — 같은 금액으로 사고 보유량을 같은 몫으로 판다. 포지션 수익률이 칸 수익률의 평균인 것과 같은
    이유다(결정 ㊱). 칸의 몫은 체결 격자와 같은 산식(`hard_fork.hard_fork_share`)이다. 칸 수익률은 포지션 성적과 같은
    체결가로 낸다 — 손절 체결 회차는 그날 종가가 아니라 체결가다.

    Args:
        closes: 날짜 인덱스의 종가
        buy_fills: 매수 회차 (모두 체결)
        sell_fills: 매도 회차 (모두 체결 — 손절로 옮긴 회차는 이탈일 · 체결가)
        forks: 하드포크 목록

    Returns:
        몫 (비율)
    """
    dates = pd.DatetimeIndex(closes.index)
    prices = closes.to_numpy(dtype=float)
    buy_days = [fill.fill_day for fill in buy_fills if fill.fill_day is not None]
    sell_days = [fill.fill_day for fill in sell_fills if fill.fill_day is not None]
    # **체결가는 포지션 성적과 같은 함수로 읽는다** — 두 벌이면 몫과 수익률이 다른 가격을 쓴다(절대 원칙 5)
    buy_prices = _fill_prices(dates, prices, buy_fills, label="매수 체결일")
    sell_prices = _fill_prices(dates, prices, sell_fills, label="매도 체결일")
    shares = [
        hard_fork_share(buy_day, sell_day, sell_price / buy_price - 1.0, forks)
        for buy_day, buy_price in zip(buy_days, buy_prices, strict=True)
        for sell_day, sell_price in zip(sell_days, sell_prices, strict=True)
    ]

    return float(np.mean(shares))


def _finished_fork_share(
    closes: pd.Series,
    buy_fills: Sequence[TrancheFill],
    sell_fills: Sequence[TrancheFill] | None,
    result: PositionResult,
    forks: Sequence[HardFork],
) -> float | None:
    """끝난 포지션의 하드포크 몫. 끝나지 않았으면 `None` 이다.

    Args:
        closes: 날짜 인덱스의 종가
        buy_fills: 매수 회차
        sell_fills: 그 성적이 쓴 매도 회차. 다음 반감기가 없으면 `None`
        result: 그 매도 회차로 낸 포지션 성적
        forks: 하드포크 목록

    Returns:
        몫 (비율) 또는 `None`
    """
    if result.reason != REASON_NONE or sell_fills is None:
        return None

    return _position_fork_share(closes, buy_fills, sell_fills, forks)


def _stop_metrics(result: PositionResult, share: float | None) -> dict[str, Any]:
    """손절 표 한 행의 성적 칸 — 포지션 성적 그대로에 하드포크 몫을 더한다.

    Args:
        result: 그 행의 포지션 성적
        share: 하드포크 몫. 끝나지 않았으면 `None`

    Returns:
        성적 칸
    """
    return {
        COL_AVG_BUY_PRICE: _number(result.avg_buy_price),
        COL_AVG_SELL_PRICE: _number(result.avg_sell_price),
        COL_POSITION_RETURN: _number(result.return_rate),
        COL_WORST_VS_COST: _number(result.worst_vs_cost),
        COL_LAST_SELL_DATE: result.last_sell_day,
        COL_FORK_SHARE: _number(share),
        COL_EXCLUDED_REASON: result.reason,
    }


def _stop_rows(
    frame: pd.DataFrame,
    closes: pd.Series,
    split: CalendarSplit,
    halving: Halving,
    buy_fills: Sequence[TrancheFill],
    sell_fills: Sequence[TrancheFill] | None,
    result: PositionResult,
    *,
    peak_window_months: int,
    forks: Sequence[HardFork],
) -> list[tuple[dict[str, Any], StopOutcome]]:
    """손절 표의 두 행과 그 행을 만든 성적 — 무손절(포지션 표의 성적 그대로)과 저점 이탈 (결정 58 · 64).

    **이탈하면 남은 매도 회차를 이탈일 · 손절 체결가로 옮겨 같은 `position_result` 로 잰다** — 같은 양씩 파므로 「남은
    보유를 그날 전부 판다」와 같고, 평균 매도가 · 수익률 · 평균 단가 대비 최악의 정의가 두 벌이 되지 않는다(절대 원칙 5).
    이탈일 «전»에 판 매도 회차는 그대로다 — **이탈일에 예정된 회차도 손절로 판다.** 월말 회차는 그날 종가(UTC 하루의 끝)라
    장중에 발동한 손절이 먼저다. 다음 반감기가 아직 없어 매도 회차가 정해지지 않은 포지션도 이탈하면 전량 팔고 끝난다.

    **손절선 · 이탈일은 포지션의 성질이라 두 행에 같이 싣는다** — 무손절 행에서 「이탈했는데 들고 갔다」가 보인다.
    매수가 끝나지 않았으면 손절선이 정해지지 않아 비운다.

    Args:
        frame: 측정 시세 (날짜 · 시가 · 종가 · 저가)
        closes: 날짜 인덱스의 종가
        split: 폭
        halving: 포지션을 산 반감기
        buy_fills: 매수 회차
        sell_fills: 매도 회차. 다음 반감기가 반감기 목록에 없으면 `None`
        result: 무손절 포지션 성적 (포지션 표의 그것)
        peak_window_months: 사이클 고점을 찾는 창(개월)
        forks: 하드포크 목록

    Returns:
        (무손절 행, 그 성적) · (저점 이탈 행, 그 성적)

    Raises:
        RuntimeError: 이탈했는데 손절 체결가 · 청산 사유가 비었거나 손절로 팔 회차가 남지 않은 경우 (내부 불변조건 —
            `_low_break` 는 이탈일과 그 둘을 함께 채우고, 감시가 마지막 매도일까지이고 그날 회차도 손절로 팔아 언제나
            하나 이상 남는다)
    """
    # **손절 칸을 빈 값으로 먼저 둔다** — 이탈이 한 건도 없으면 그 칸이 행에 없어, 표로 만들 때 날짜 열이 아니게 된다
    blank: dict[str, Any] = {
        COL_STOP_LINE_DATE: None,
        COL_STOP_LINE_LOW: np.nan,
        COL_STOP_LINE_VS_COST: np.nan,
        COL_BREAK_DATE: None,
        COL_STOP_FILL_PRICE: np.nan,
        COL_SOLD_BEFORE_STOP: None,
    }
    identity = {COL_CALENDAR_SPLIT: split.name, COL_HALVING: halving.label}
    plain_share = _finished_fork_share(closes, buy_fills, sell_fills, result, forks)
    plain = {
        **identity,
        COL_STOP_METHOD: NO_STOP_LABEL,
        **_stop_metrics(result, plain_share),
        **blank,
    }
    plain_outcome = StopOutcome(split, halving, NO_STOP_LABEL, result, plain_share, exit_reason=None)
    # 저점 이탈로 팔지 않은 포지션 — 성적이 무손절과 같다
    held = StopOutcome(split, halving, STOP_METHOD_LOW_BREAK, result, plain_share, exit_reason=None)
    if result.reason == REASON_POSITION_BUYING:
        return [(plain, plain_outcome), ({**plain, COL_STOP_METHOD: STOP_METHOD_LOW_BREAK}, held)]

    sell_days = [fill.fill_day for fill in sell_fills or () if fill.fill_day is not None]
    sells_done = sell_fills is not None and len(sell_days) == len(sell_fills)
    cut = _low_break(
        frame,
        halving.day,
        max(fill.fill_day for fill in buy_fills if fill.fill_day is not None),
        max(sell_days) if sells_done else pd.Timestamp(closes.index[-1]),
        peak_window_months=peak_window_months,
    )
    plain |= {
        COL_STOP_LINE_DATE: cut.line_day,
        COL_STOP_LINE_LOW: cut.line_low,
        COL_STOP_LINE_VS_COST: _number(
            None if result.avg_buy_price is None else cut.line_low / result.avg_buy_price - 1.0
        ),
        COL_BREAK_DATE: cut.break_day,
    }
    stopped = {**plain, COL_STOP_METHOD: STOP_METHOD_LOW_BREAK}
    if cut.break_day is None:
        return [(plain, plain_outcome), (stopped, held)]
    if cut.fill_price is None or cut.exit_reason is None:
        raise RuntimeError(
            f"내부 불변조건 위반: 이탈일({cut.break_day.date()})이 있는데 손절 체결가 · 청산 사유가 비었습니다 — "
            f"체결가 {cut.fill_price} · 사유 {cut.exit_reason}"
        )

    # 이탈일 «전»에 판 매도 회차는 그대로다 — 회차 체결일이 오름차순이라 앞쪽 일부다
    kept = [fill for fill in sell_fills or () if fill.fill_day is not None and fill.fill_day < cut.break_day]
    remaining = (len(sell_fills) if sell_fills is not None else split.sell_tranches) - len(kept)
    if remaining < 1:
        raise RuntimeError(
            f"내부 불변조건 위반: 이탈했는데 손절로 팔 회차가 없습니다 — {split.name} · {halving.label} · 이탈일 "
            f"{cut.break_day.date()} · 매도 {sell_days}"
        )

    moved_deadlines = (
        [fill.deadline for fill in sell_fills[len(kept) :]] if sell_fills is not None else [cut.break_day] * remaining
    )
    stop_fills = [
        *kept,
        *(
            TrancheFill(deadline, cut.break_day, STOP_METHOD_LOW_BREAK, REASON_NONE, fill_price=cut.fill_price)
            for deadline in moved_deadlines
        ),
    ]
    stop_result = position_result(frame, buy_fills, stop_fills)
    stop_share = _finished_fork_share(closes, buy_fills, stop_fills, stop_result, forks)
    sold = StopOutcome(split, halving, STOP_METHOD_LOW_BREAK, stop_result, stop_share, exit_reason=cut.exit_reason)

    return [
        (plain, plain_outcome),
        (
            {
                **stopped,
                **_stop_metrics(stop_result, stop_share),
                COL_STOP_FILL_PRICE: cut.fill_price,
                COL_SOLD_BEFORE_STOP: len(kept),
            },
            sold,
        ),
    ]


def calendar_split_grid(
    frame: pd.DataFrame,
    halvings: Sequence[Halving],
    splits: Sequence[CalendarSplit],
    *,
    step_months: int,
    peak_window_months: int,
    forks: Sequence[HardFork],
) -> CalendarSplitGrid:
    """달력 매달 분할 전부를 낸다 — 폭마다, 반감기 뒤에 사고 다음 반감기 뒤에 판다 (결정 51 · 52 · 54 · 58).

    폭 하나는 「달력만」 매수 조합과 「달력만」 매도 조합의 짝이고 쪽마다 회차 수가 따로다. **기한이 m개월인 회차는
    (기준 반감기일 + m개월)이 속한 달의 말일 종가에 체결한다** — 실제로 체결할 수 있는 날이다(결정 54).
    **마지막 반감기의 포지션은 다음 반감기가 목록에 없어 매도 회차가 정의되지 않는다** — 행은 남고 사유가 붙는다.
    포지션마다 무손절 · 저점 이탈 손절을 하드포크 몫과 함께 손절 표에 나란히 낸다(`_stop_rows`).

    Args:
        frame: 측정 시세 (날짜 · 시가 · 종가 · 저가, 날짜 오름차순 · 휴장 없음)
        halvings: 반감기 목록 (날짜 오름차순)
        splits: 폭 목록. 이름이 겹치면 안 된다
        step_months: 회차 간격(개월)
        peak_window_months: 저점 이탈 손절선의 사이클 고점을 찾는 창(개월)
        forks: 하드포크 목록 — 손절 표의 하드포크 몫

    Returns:
        표 셋과 손절 표를 만든 성적. 회차 표는 폭 → 반감기 → 매수 · 매도 → 회차 순, 손절 표와 그 성적은 폭 → 반감기 →
        무손절 · 저점 이탈 순이다

    Raises:
        ValueError: 반감기나 폭이 없거나, 폭 이름이 겹치거나, 한쪽 회차 수가 1 보다 작거나, 첫 매수 · 매도 회차가 기준
            반감기 앞이거나, 매수 마지막 회차가 다음 반감기와 같거나 뒤인 경우 — 매도는 매수가 끝난 뒤에만 온다.
            고점 창이 1개월보다 작거나 폭의 매수가 고점 창보다 먼저 끝나는 경우 — 손절선은 고점 창이 닫힌 뒤 마지막
            매수일에 고정한다. 매수가 끝난 포지션의 반감기일 종가가 시세에 없는 경우 — 사이클 고점을 찾을 수 없다
    """
    if not halvings or not splits:
        raise ValueError("반감기와 달력 분할의 폭이 하나 이상 있어야 합니다")
    names = [split.name for split in splits]
    if len(set(names)) != len(names):
        raise ValueError(f"달력 분할 폭의 이름이 겹칩니다 — 식별 칸이라 두 폭의 행이 섞입니다: {names}")
    if peak_window_months < 1:
        raise ValueError(f"사이클 고점을 찾는 고점 창은 1개월 이상이어야 합니다: {peak_window_months}")
    early = [split.name for split in splits if split.buy_last_deadline < peak_window_months]
    if early:
        raise ValueError(f"달력 분할 폭의 마지막 매수가 고점 창({peak_window_months}개월)보다 먼저 끝납니다 — 손절선을 정할 수 없습니다: {early}")

    trading_days = _require_increasing(pd.Index(frame[COL_DATE]), "시세")
    closes = pd.Series(frame[COL_CLOSE].to_numpy(dtype=float), index=trading_days)
    # 달력만 조합은 창을 쓰지 않는다 — `leg_fills` 가 받는 인자라 넘길 뿐이다
    new_highs = new_high_flags(closes)

    def fills_for(leg: SplitLeg, anchor: Halving, tranches: int) -> list[TrancheFill]:
        return leg_fills(
            trading_days,
            leg,
            anchor.day,
            trigger_values=None,
            new_highs=new_highs,
            tranches=tranches,
            step_months=step_months,
            month_end=True,
        )

    fill_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    stop_rows: list[dict[str, Any]] = []
    outcomes: list[StopOutcome] = []
    for split in splits:
        buy = SplitLeg(SPLIT_SIDE_BUY, SPLIT_THRESHOLD_NONE, (), None, None, split.buy_last_deadline)
        sell = SplitLeg(SPLIT_SIDE_SELL, SPLIT_THRESHOLD_NONE, (), None, None, split.sell_last_deadline)
        buy_first, sell_first = split.first_deadlines(step_months)
        for cycle, halving in enumerate(halvings):
            following = halvings[cycle + 1] if cycle + 1 < len(halvings) else None
            buy_fills = fills_for(buy, halving, split.buy_tranches)
            if following is not None and buy_fills[-1].deadline >= following.day:
                raise ValueError(
                    f"달력 분할 「{split.name}」의 매수 마지막 회차({buy_fills[-1].deadline.date()})가 다음 반감기"
                    f"({following.label})와 같거나 뒤입니다 — 매도는 매수가 끝난 뒤에만 와야 합니다"
                )
            sell_fills = fills_for(sell, following, split.sell_tranches) if following is not None else None

            for leg, anchor, fills, tranches in (
                (buy, halving, buy_fills, split.buy_tranches),
                (sell, following, sell_fills, split.sell_tranches),
            ):
                rows = _fill_rows(leg, halving, anchor, fills, tranches=tranches, closes=closes, mvrv=None, ranks=None)
                fill_rows.extend({COL_CALENDAR_SPLIT: split.name, **row} for row in rows)

            result = position_result(frame, buy_fills, sell_fills)
            position_rows.append(
                {
                    COL_CALENDAR_SPLIT: split.name,
                    COL_BUY_TRANCHES: split.buy_tranches,
                    COL_BUY_FIRST_DEADLINE: buy_first,
                    COL_BUY_LAST_DEADLINE: split.buy_last_deadline,
                    COL_SELL_TRANCHES: split.sell_tranches,
                    COL_SELL_FIRST_DEADLINE: sell_first,
                    COL_SELL_LAST_DEADLINE: split.sell_last_deadline,
                    COL_HALVING: halving.label,
                    COL_AVG_BUY_PRICE: _number(result.avg_buy_price),
                    COL_AVG_SELL_PRICE: _number(result.avg_sell_price),
                    COL_POSITION_RETURN: _number(result.return_rate),
                    COL_WORST_VS_COST: _number(result.worst_vs_cost),
                    COL_FIRST_BUY_DATE: result.first_buy_day,
                    COL_LAST_SELL_DATE: result.last_sell_day,
                    COL_HOLD_DAYS: result.hold_days,
                    COL_BUY_CALENDAR_COUNT: result.buy_counts[1],
                    COL_SELL_CALENDAR_COUNT: result.sell_counts[1],
                    COL_EXCLUDED_REASON: result.reason,
                }
            )
            for row, outcome in _stop_rows(
                frame,
                closes,
                split,
                halving,
                buy_fills,
                sell_fills,
                result,
                peak_window_months=peak_window_months,
                forks=forks,
            ):
                stop_rows.append(row)
                outcomes.append(outcome)

    return CalendarSplitGrid(
        fills=_frame_of(fill_rows).reindex(columns=_CALENDAR_FILL_COLUMNS),
        positions=_frame_of(position_rows).reindex(columns=_CALENDAR_POSITION_COLUMNS),
        stops=_frame_of(stop_rows).reindex(columns=_CALENDAR_STOP_COLUMNS),
        outcomes=tuple(outcomes),
    )


__all__ = [
    "CalendarSplitGrid",
    "PositionResult",
    "SplitGrid",
    "SplitLeg",
    "StopOutcome",
    "TrancheFill",
    "calendar_split_grid",
    "leg_fills",
    "new_high_flags",
    "position_result",
    "split_grid",
    "split_legs",
    "trailing_rank",
    "tranche_deadlines",
    "window_open",
]
