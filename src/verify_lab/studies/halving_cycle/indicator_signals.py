"""반감기_사이클 2단계의 시점 규칙 — 돌파 판정 · 사이클 배정 · 진입 일정 · 진입 전날 값

| 무엇 | 정의 | 근거 |
| --- | --- | --- |
| 돌파 | 상태 `값 ≥ 문턱` 이 바뀐 날. 전날이나 그날 값이 비면 판정하지 않는다 | 창이 차는 첫날을 돌파로 세면 없는 신호가 생긴다 |
| 판정일 | 지표 계열의 날 중 **시세의 거래일**만 | 진입가가 없는 날의 신호는 잴 수 없다 |
| 사이클 | 판정일 이전(그날 포함) 가장 최근 반감기. 경과는 다 채운 달력월 수 | 1단계의 「반감기일 + 개월」과 같은 셈이다 |
| 진입 · 청산 | 판정일 다음 거래일 종가에 사고, 1단계의 달력월 규칙으로 판다 | 설계 결정 ㉗ · ⑯ |
| 제외 | 첫 반감기 전 판정 · 진입일이 데이터 뒤 · 청산일이 데이터 뒤 — **행을 남긴다** | 결정 ㉘ ① · 표본 보존 |
| 진입 전날 값 | 일간은 진입 전 거래일의 값, 월간은 그날이나 그 전에 끝난 달의 값 | 결정 ㉗ — Coin Metrics 의 d 값은 d+1 일에 완성된다 |

**판정 다음날 종가에 사는 이유**: 판정 종가에 바로 사면 같은 봉 안의 미래 참조이고, 온체인 값은 공개가 하루 늦다 —
규칙 하나로 둘을 덮는다. 월간 지표는 달의 마지막 날이 판정일이라 다음 달 첫날에 산다.
"""

from collections.abc import Mapping, Sequence
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
)
from verify_lab.measure.forward_return import ReturnBasis
from verify_lab.studies.halving_cycle.constants import (
    COL_HALVING,
    COL_HOLD_MONTHS,
    COL_INDICATOR_MONTH,
    COL_INDICATOR_SIGNAL,
    COL_INDICATOR_VALUE,
    COL_JUDGMENT_DATE,
    COL_MONTHS_SINCE_HALVING,
    COL_PREVIOUS_VALUE,
    COL_VALUE_DAY,
    POSITION_BEFORE_FIRST,
    REASON_BEFORE_FIRST_HALVING,
    REASON_ENTRY_AFTER_DATA,
    Halving,
    IndicatorSignal,
)
from verify_lab.studies.halving_cycle.halving_calendar import calendar_returns, exit_schedule, trading_positions
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 판정 표의 컬럼 — 판정마다 한 행. 진입일은 시세의 날짜 컬럼 이름을 쓴다 (1단계 달력 함수가 그 이름을 읽는다)
JUDGMENT_COLUMNS = [
    COL_INDICATOR_SIGNAL,
    COL_JUDGMENT_DATE,
    COL_PREVIOUS_VALUE,
    COL_INDICATOR_VALUE,
    COL_HALVING,
    COL_MONTHS_SINCE_HALVING,
    COL_DATE,
    COL_EXCLUDED_REASON,
]

# 신호 × 보유 long-form 의 컬럼. **기준 · 구간을 채운다** — `measure.statistics.summarize` 가 그 둘로 칸을 묶는다
SIGNAL_RETURN_COLUMNS = [
    COL_INDICATOR_SIGNAL,
    COL_HALVING,
    COL_MONTHS_SINCE_HALVING,
    COL_JUDGMENT_DATE,
    COL_PREVIOUS_VALUE,
    COL_INDICATOR_VALUE,
    COL_DATE,
    COL_ENTRY_CLOSE,
    COL_HOLD_MONTHS,
    COL_EXIT_DATE,
    COL_EXIT_CLOSE,
    COL_HOLD_DAYS,
    COL_BASIS,
    COL_HORIZON,
    COL_FORWARD_RETURN,
    COL_EXCLUDED_REASON,
]

# long-form 의 컬럼 자료형. **빈 표도 같은 자료형을 갖는다** — 신호마다 이어 붙일 때 자료형이 조용히 object 로 풀린다
_RETURN_DTYPES: dict[str, Any] = {
    COL_INDICATOR_SIGNAL: "object",
    COL_HALVING: "object",
    COL_MONTHS_SINCE_HALVING: "Int64",
    COL_JUDGMENT_DATE: "datetime64[ns]",
    COL_PREVIOUS_VALUE: "float64",
    COL_INDICATOR_VALUE: "float64",
    COL_DATE: "datetime64[ns]",
    COL_ENTRY_CLOSE: "float64",
    COL_HOLD_MONTHS: "int64",
    COL_EXIT_DATE: "datetime64[ns]",
    COL_EXIT_CLOSE: "float64",
    COL_HOLD_DAYS: "Int64",
    COL_BASIS: "object",
    COL_HORIZON: "int64",
    COL_FORWARD_RETURN: "float64",
    COL_EXCLUDED_REASON: "object",
}


def _require_date_index(values: pd.Series | pd.DataFrame, label: str) -> pd.DatetimeIndex:
    """날짜 인덱스가 오름차순 · 중복 없음인지 본다.

    Args:
        values: 검사할 계열이나 표
        label: 메시지에 쓸 이름

    Returns:
        그 인덱스

    Raises:
        ValueError: 날짜 인덱스가 아니거나 오름차순 · 중복 없음이 아닌 경우
    """
    index = values.index
    if not isinstance(index, pd.DatetimeIndex):
        raise ValueError(f"{label}의 인덱스가 날짜가 아닙니다: {type(index).__name__}")
    if not index.is_monotonic_increasing or index.has_duplicates:
        raise ValueError(f"{label}의 날짜가 오름차순 · 중복 없음이 아닙니다")

    return index


def crossing_days(values: pd.Series, threshold: float, *, upward: bool) -> pd.DatetimeIndex:
    """지표가 문턱을 돌파한 날을 찾는다.

    **상태는 `값 ≥ 문턱` 이다** — 문턱과 같은 값은 문턱 이상이다. 상향 돌파는 전날 거짓 → 그날 참, 하향 돌파는
    그 반대다. 비교는 계열 안의 **바로 앞 관측**과 한다. 전날이나 그날 값이 비면 판정하지 않는다.

    Args:
        values: 날짜 인덱스(오름차순)의 지표 계열
        threshold: 문턱
        upward: 상향 돌파를 찾는가

    Returns:
        돌파일 (오름차순)

    Raises:
        ValueError: 인덱스가 날짜 오름차순이 아닌 경우
    """
    index = _require_date_index(values, "지표 계열")

    numbers = values.astype(float)
    above = (numbers >= threshold).to_numpy()
    judged = (numbers.notna() & numbers.shift(1).notna()).to_numpy()
    before = np.concatenate([[False], above[:-1]]) if len(above) else above

    crossed = (above & ~before) if upward else (~above & before)

    return index[crossed & judged]


def halving_for(day: pd.Timestamp, halvings: Sequence[Halving]) -> Halving | None:
    """그날 이전(그날 포함) 가장 최근 반감기.

    Args:
        day: 날짜
        halvings: 반감기 목록

    Returns:
        반감기. 첫 반감기 전이면 `None`
    """
    past = [halving for halving in halvings if halving.day <= day]

    return max(past, key=lambda halving: halving.day) if past else None


def months_since(start: pd.Timestamp, day: pd.Timestamp) -> int:
    """시작일에서 그날까지 **다 채운 달력월 수**.

    `시작일 + N개월 ≤ 그날` 인 가장 큰 N 이다. 없는 날짜는 1단계처럼 그 달 말일로 당긴다(1월 31일 + 1개월 = 2월 말일).

    Args:
        start: 시작일 (반감기일)
        day: 그날 (시작일 이후)

    Returns:
        경과 개월

    Raises:
        ValueError: 그날이 시작일 앞인 경우
    """
    if day < start:
        raise ValueError(f"그날이 시작일 앞입니다: {day.date()} < {start.date()}")

    months = (day.year - start.year) * 12 + (day.month - start.month)
    if start + pd.DateOffset(months=months) > day:
        months -= 1

    return months


def signal_entries(
    trading_days: pd.DatetimeIndex,
    values: pd.Series,
    signal: IndicatorSignal,
    halvings: Sequence[Halving],
) -> pd.DataFrame:
    """신호 하나의 판정마다 사이클 · 진입일 · 제외 사유를 붙인다.

    Args:
        trading_days: 시세의 거래일 (오름차순 · 중복 없음)
        values: 그 신호가 보는 지표 계열 (날짜 인덱스 오름차순)
        signal: 신호
        halvings: 반감기 목록

    Returns:
        `JUDGMENT_COLUMNS` 구성. 판정일 오름차순. **진입일은 제외 행에서 비어 있다**

    Raises:
        ValueError: 거래일 목록이나 지표 계열이 잘못된 경우, 반감기가 없는 경우
    """
    validate_trading_days(trading_days, purpose="판정일")
    if not halvings:
        raise ValueError("반감기가 하나도 없습니다")

    crossed = crossing_days(values, signal.threshold, upward=signal.upward)
    judged = crossed[crossed.isin(trading_days)]
    previous = values.astype(float).shift(1)

    positions = trading_positions(trading_days, judged, label="판정일")
    rows: list[dict[str, Any]] = []
    for day, position in zip(judged, positions.tolist(), strict=True):
        halving = halving_for(day, halvings)
        has_next = position + 1 < len(trading_days)
        if halving is None:
            reason = REASON_BEFORE_FIRST_HALVING
        elif not has_next:
            reason = REASON_ENTRY_AFTER_DATA
        else:
            reason = REASON_NONE

        rows.append(
            {
                COL_INDICATOR_SIGNAL: signal.name,
                COL_JUDGMENT_DATE: day,
                COL_PREVIOUS_VALUE: float(previous[day]),
                COL_INDICATOR_VALUE: float(values[day]),
                COL_HALVING: halving.label if halving is not None else POSITION_BEFORE_FIRST,
                COL_MONTHS_SINCE_HALVING: months_since(halving.day, day) if halving is not None else pd.NA,
                # 진입일은 잰 판정에만 적는다 — 제외된 판정에 날짜를 적으면 「그날 샀다」로 읽힌다
                COL_DATE: trading_days[position + 1] if reason == REASON_NONE else pd.NaT,
                COL_EXCLUDED_REASON: reason,
            }
        )

    return pd.DataFrame(rows, columns=JUDGMENT_COLUMNS).astype(
        {
            COL_JUDGMENT_DATE: "datetime64[ns]",
            COL_PREVIOUS_VALUE: "float64",
            COL_INDICATOR_VALUE: "float64",
            COL_MONTHS_SINCE_HALVING: "Int64",
            COL_DATE: "datetime64[ns]",
        }
    )


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """표를 행 사전 목록으로 편다. 컬럼 이름이 전부 문자열이라 키를 `str` 로 맞춘다.

    Args:
        frame: 표

    Returns:
        행마다 컬럼 이름 → 값
    """
    return [{str(column): value for column, value in row.items()} for row in frame.to_dict("records")]


def _judgment_records(
    frame: pd.DataFrame, trading_days: pd.DatetimeIndex, judgments: pd.DataFrame, hold_months: Sequence[int]
) -> list[dict[str, Any]]:
    """판정 표를 신호 × 보유 행으로 편다.

    **표를 이어 붙이지 않고 행을 모은다** — 제외 행만 모인 조각은 날짜 컬럼이 전부 비어 있어, `concat` 이 그 조각의
    자료형을 버리고 추측한다(pandas 2.3 에서 NumPy 경고가 난다).

    Args:
        frame: 날짜 오름차순 시세 (종가)
        trading_days: 시세의 거래일
        judgments: `signal_entries` 의 결과 하나
        hold_months: 보유 개월

    Returns:
        `SIGNAL_RETURN_COLUMNS` 키를 가진 행. 판정일 → 보유 순서
    """
    valid = judgments[judgments[COL_EXCLUDED_REASON] == REASON_NONE]
    excluded = judgments[judgments[COL_EXCLUDED_REASON] != REASON_NONE]

    records: list[dict[str, Any]] = []
    if not valid.empty:
        # 청산 규칙은 1단계와 같은 함수다 — 두 벌이면 보유 길이가 조용히 갈린다
        measured = calendar_returns(frame, exit_schedule(trading_days, valid, hold_months))
        records.extend(_records(measured[SIGNAL_RETURN_COLUMNS]))
    for row in _records(excluded):
        for months in hold_months:
            records.append(
                {
                    **row,
                    COL_ENTRY_CLOSE: np.nan,
                    COL_HOLD_MONTHS: months,
                    COL_EXIT_DATE: pd.NaT,
                    COL_EXIT_CLOSE: np.nan,
                    COL_HOLD_DAYS: pd.NA,
                    COL_BASIS: ReturnBasis.CLOSE.value,
                    COL_HORIZON: months,
                    COL_FORWARD_RETURN: np.nan,
                }
            )

    # 판정일 → 보유. `sorted` 는 안정 정렬이라 같은 칸 안의 순서가 흔들리지 않는다
    return sorted(records, key=lambda record: (record[COL_JUDGMENT_DATE], record[COL_HOLD_MONTHS]))


def indicator_signal_returns(
    frame: pd.DataFrame,
    values_by_indicator: Mapping[str, pd.Series],
    signals: Sequence[IndicatorSignal],
    halvings: Sequence[Halving],
    hold_months: Sequence[int],
) -> pd.DataFrame:
    """신호들의 판정을 신호 × 보유 long-form 수익률로 낸다.

    **신호 × 보유 = 유효 + 제외** — 어떤 판정도 조용히 사라지지 않는다. 한 번도 돌파하지 않은 신호는 행이 없다 —
    그 신호의 0건 행은 집계 표가 남긴다.

    Args:
        frame: 날짜 오름차순 시세 (날짜 · 종가)
        values_by_indicator: 지표 컬럼 토큰 → 지표 계열. 신호가 보는 지표가 모두 있어야 한다
        signals: 신호 목록 (이름이 겹치지 않는다)
        halvings: 반감기 목록
        hold_months: 보유 개월

    Returns:
        `SIGNAL_RETURN_COLUMNS` 구성. 신호 목록 순서 → 판정일 → 보유 순서

    Raises:
        ValueError: 시세가 잘못됐거나, 신호 이름이 겹치거나, 신호가 보는 지표가 없는 경우
    """
    validate_market_frame(frame, [COL_DATE, COL_CLOSE])
    names = [signal.name for signal in signals]
    if len(set(names)) != len(names):
        raise ValueError(f"신호 이름이 겹칩니다: {names}")
    missing = sorted({signal.indicator for signal in signals} - set(values_by_indicator))
    if missing:
        raise ValueError(f"신호가 보는 지표 계열이 없습니다: {missing}")

    trading_days = pd.DatetimeIndex(frame[COL_DATE])
    records: list[dict[str, Any]] = []
    for signal in signals:
        judgments = signal_entries(trading_days, values_by_indicator[signal.indicator], signal, halvings)
        records.extend(_judgment_records(frame, trading_days, judgments, hold_months))

    result = pd.DataFrame(records, columns=SIGNAL_RETURN_COLUMNS).astype(_RETURN_DTYPES)

    excluded = int((result[COL_EXCLUDED_REASON] != REASON_NONE).sum())
    logger.debug(f"지표 신호 산출: 신호 {len(signals)}종, {len(result):,}행, 제외 {excluded:,}행")

    return result


def entry_indicator_values(
    trading_days: pd.DatetimeIndex,
    entry_dates: pd.DatetimeIndex,
    daily: pd.DataFrame,
    monthly: pd.DataFrame,
) -> pd.DataFrame:
    """진입일마다 **진입 전날까지 완성된** 지표 값을 붙인다 (결정 ㉗).

    일간 지표는 진입 전 거래일(값 기준일)의 값, 월간 지표는 값 기준일이나 그 전에 끝난 달의 값이다 — 달의 첫날에
    들어가면 전날이 전달 말일이라 전달 값을 쓴다. 전날이 데이터에 없으면 비운다.

    Args:
        trading_days: 시세의 거래일
        entry_dates: 진입일 (전부 거래일)
        daily: 날짜 인덱스의 일간 지표 표
        monthly: 말일 인덱스의 월간 지표 표

    Returns:
        진입일 순서 그대로 — 진입일 · 값 기준일 · 월간 지표 기준 달 · 일간 지표 컬럼 · 월간 지표 컬럼

    Raises:
        ValueError: 거래일 목록이 잘못됐거나, 진입일이 거래일에 없거나, 지표 표의 인덱스가 날짜 오름차순이 아닌 경우
    """
    validate_trading_days(trading_days, purpose="값 기준일")
    _require_date_index(daily, "일간 지표 표")
    month_ends = _require_date_index(monthly, "월간 지표 표")

    positions = trading_positions(trading_days, entry_dates, label="진입일")
    value_days = pd.DatetimeIndex([trading_days[position - 1] if position > 0 else pd.NaT for position in positions])

    # 값 기준일이나 그 전에 끝난 가장 최근 달 — `side="right"` 라 말일 당일도 든다
    month_positions = month_ends.searchsorted(value_days, side="right") - 1
    months = pd.DatetimeIndex(
        [
            month_ends[int(position)] if not pd.isna(day) and position >= 0 else pd.NaT
            for day, position in zip(value_days, month_positions, strict=True)
        ]
    )

    daily_values = daily.reindex(value_days).reset_index(drop=True)
    monthly_values = monthly.reindex(months).reset_index(drop=True)

    return pd.concat(
        [
            pd.DataFrame({COL_DATE: entry_dates, COL_VALUE_DAY: value_days, COL_INDICATOR_MONTH: months}),
            daily_values,
            monthly_values,
        ],
        axis=1,
    )


__all__ = [
    "JUDGMENT_COLUMNS",
    "SIGNAL_RETURN_COLUMNS",
    "crossing_days",
    "entry_indicator_values",
    "halving_for",
    "indicator_signal_returns",
    "months_since",
    "signal_entries",
]
