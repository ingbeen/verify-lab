"""월 하순 진입과 말일 기준 청산 — 진입일 종가 매수 → 지정 상대 거래일 종가 매도

`measure/forward_return.py` 는 **고정 거래일 구간**만 잰다. 이 매매는 진입도 청산도
**달력 기준**이라 보유 거래일 수가 달마다 다르므로 그 틀에 들어가지 않는다 —
실측에서 3~9거래일에 걸쳐 있었다 (`docs/spec/month_end.md` §7.3).

**진입일은 목표 달력일이고 휴장이면 직전 거래일로 앞당긴다**(결정 ①). 앞당김은 **그 달
안에서만** 일어난다 — 전월로 넘어가면 「그 달 20일에 산다」가 아닌 다른 매매가 된다.

**청산일은 그 달 마지막 거래일을 0 으로 둔 상대 거래일이다**(결정 ②). 음수는 말일 이전,
양수는 익월이다.

**데이터의 마지막 달에는 진입일을 만들지 않는다**(결정 ⑧). 그 달이 진행 중이면 「말일」이
실제 월말이 아니라 데이터가 끊긴 지점이고, 앞당김 방식에서는 진입일과 청산일이 같은 날이 되어
보유 0 의 가짜 표본이 된다. 그 달이 끝났는지는 데이터만으로 알 수 없으므로 언제나 뺀다.

**제외된 달도 행으로 남는다**(결정 ④). 값만 비우고 사유를 달아 `진입 수 = 유효 + 제외` 가
성립하게 한다 — 행을 지우면 표본이 조용히 줄어 생존편향이 생긴다.

**가격 컬럼을 인자로 받는다.** ETF 는 시세 스키마의 `Close`, 지수는 단일 값 계열의 `Value` 다
(§7.6). 거래소 휴장일은 사전에 공표되므로 이 판정은 미래를 참조하지 않으며, 구현이 판정일 이후의
데이터에 의존하지 않는지는 look-ahead 감시 테스트로 고정한다.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE
from verify_lab.data.loader import validate_market_frame
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_EXCLUDED_REASON,
    COL_FORWARD_RETURN,
    COL_HORIZON,
    REASON_NONE,
    REASON_OUT_OF_RANGE,
)
from verify_lab.measure.forward_return import ReturnBasis
from verify_lab.studies.month_end.constants import (
    COL_ENTRY_CLOSE,
    COL_EXIT_CLOSE,
    COL_EXIT_DATE,
    COL_EXIT_OFFSET,
    COL_HOLD_DAYS,
    COL_MONTH,
    COL_MONTH_LAST_DATE,
    COL_TARGET_DAY,
    HORIZON_MONTH_END,
    REASON_NO_ENTRY_DAY,
    REASON_NO_HOLDING,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 달력일의 허용 범위. 32 이상은 어느 달에도 없고 0 이하는 뜻이 없다
MIN_CALENDAR_DAY = 1
MAX_CALENDAR_DAY = 31

# 진입일 표의 컬럼과 dtype. 빈 결과에서도 같은 스키마를 유지해 호출 측이 분기하지 않게 한다
ENTRY_DTYPES = {
    COL_MONTH: "datetime64[ns]",
    COL_TARGET_DAY: "int64",
    COL_DATE: "datetime64[ns]",
    COL_EXCLUDED_REASON: "object",
}

# 청산 일정표의 컬럼과 dtype
SCHEDULE_DTYPES = {
    COL_MONTH: "datetime64[ns]",
    COL_TARGET_DAY: "int64",
    COL_DATE: "datetime64[ns]",
    COL_MONTH_LAST_DATE: "datetime64[ns]",
    COL_EXIT_OFFSET: "int64",
    COL_EXIT_DATE: "datetime64[ns]",
    COL_HOLD_DAYS: "Int64",
    COL_EXCLUDED_REASON: "object",
}

# 수익률 표에 함께 남기는 가격. 사용자가 차트로 직접 대조하는 원자료다 (측정의 원칙 8)
RETURN_COLUMNS = [
    COL_MONTH,
    COL_TARGET_DAY,
    COL_DATE,
    COL_MONTH_LAST_DATE,
    COL_EXIT_OFFSET,
    COL_EXIT_DATE,
    COL_HOLD_DAYS,
    COL_ENTRY_CLOSE,
    COL_EXIT_CLOSE,
    COL_BASIS,
    COL_HORIZON,
    COL_FORWARD_RETURN,
    COL_EXCLUDED_REASON,
]


@dataclass(frozen=True)
class MonthExitSchedule:
    """진입일별 청산 일정

    Attributes:
        frame: 진입 달·목표 달력일·진입일·그 달 마지막 거래일·청산 상대 거래일·청산일·
            보유 거래일수·제외 사유를 담은 DataFrame.
            **제외된 진입도 행으로 남는다** — 값만 비어 있고 사유가 붙는다
        exit_offset: 그 달 마지막 거래일 기준 청산 상대 거래일
    """

    frame: pd.DataFrame
    exit_offset: int

    @property
    def entry_count(self) -> int:
        """진입 수.

        Returns:
            진입일의 수 (제외된 달을 포함한 전체 행 수)
        """
        return len(self.frame)


def month_entry_dates(trading_days: pd.DatetimeIndex, *, calendar_day: int) -> pd.DataFrame:
    """달마다 목표 달력일의 진입일을 정한다.

    목표일이 거래일이면 그날이고, 휴장이면 **그 달 안에서** 직전 거래일로 앞당긴다(결정 ①).

    **데이터의 마지막 달은 아예 다루지 않는다**(결정 ⑧). 그 달의 「말일」은 실제 월말이 아니라
    데이터가 끊긴 지점이라, 진입일을 만들면 청산일과 같은 날이 되어 보유 0 의 가짜 표본이 된다.

    Args:
        trading_days: 거래일 목록. 오름차순 정렬된 중복 없는 인덱스여야 한다
        calendar_day: 목표 진입 달력일 (1~31)

    Returns:
        `ENTRY_DTYPES` 구성의 DataFrame. **달마다 한 행**이며 진입일을 못 정한 달도
        값만 비운 채 남는다. 진입 달 오름차순으로 정렬된다

    Raises:
        ValueError: 거래일 목록이 비었거나 정렬·중복 조건을 어긴 경우,
            목표 달력일이 범위를 벗어난 경우
    """
    if not MIN_CALENDAR_DAY <= calendar_day <= MAX_CALENDAR_DAY:
        raise ValueError(f"진입 달력일은 {MIN_CALENDAR_DAY}~{MAX_CALENDAR_DAY} 이어야 합니다: {calendar_day}")
    if len(trading_days) == 0:
        raise ValueError("거래일 목록이 비어 있어 진입일을 정할 수 없습니다")
    if not trading_days.is_monotonic_increasing:
        raise ValueError("거래일 목록이 오름차순으로 정렬되어 있어야 합니다")
    if trading_days.has_duplicates:
        raise ValueError("거래일 목록에 중복된 날짜가 있습니다")

    days = pd.DataFrame({COL_DATE: trading_days})
    days[COL_MONTH] = days[COL_DATE].dt.to_period("M").dt.to_timestamp()

    # 1. 데이터의 마지막 달을 통째로 뺀다. 그 달이 끝났는지는 데이터만으로 알 수 없으므로
    #    조건부로 넣지 않는다 — 정의가 깨진 표본을 넣는 것보다 매월 최대 1건을 잃는 쪽이 낫다
    last_month = days[COL_MONTH].iloc[-1]
    days = days[days[COL_MONTH] < last_month]

    if days.empty:
        logger.debug(f"데이터가 한 달치뿐이라 진입일이 없습니다 (달력일 {calendar_day})")
        return _empty_entries()

    # 2. 목표일 이하인 거래일 중 가장 늦은 것이 진입일이다. 목표일이 거래일이면 그날 자신이고
    #    휴장이면 직전 거래일이 된다. 같은 달 안에서만 고르므로 전월로 넘어가지 않는다
    eligible = days[days[COL_DATE].dt.day <= calendar_day]
    entry_by_month = eligible.groupby(COL_MONTH, sort=True)[COL_DATE].max()

    months = pd.DatetimeIndex(sorted(days[COL_MONTH].unique()))
    entry_dates = pd.DatetimeIndex(entry_by_month.reindex(months))

    missing = np.asarray(entry_dates.isna())
    frame = pd.DataFrame(
        {
            COL_MONTH: months,
            COL_TARGET_DAY: calendar_day,
            COL_DATE: entry_dates,
            COL_EXCLUDED_REASON: np.where(missing, REASON_NO_ENTRY_DAY, REASON_NONE),
        }
    )

    logger.debug(f"진입일 산출: 달력일 {calendar_day}, {len(frame):,}개월, 진입일 없음 {int(missing.sum()):,}개월")

    return frame


def month_exit_schedule(
    trading_days: pd.DatetimeIndex,
    entries: pd.DataFrame,
    *,
    exit_offset: int,
) -> MonthExitSchedule:
    """진입일마다 「그 달 마지막 거래일 기준 상대 거래일」 청산일을 정한다.

    상대 거래일 0 은 그 달 마지막 거래일, 음수는 그 이전, 양수는 익월이다(결정 ②).

    Args:
        trading_days: 거래일 목록. `month_entry_dates` 에 넘긴 것과 같아야 한다
        entries: `month_entry_dates` 의 결과
        exit_offset: 그 달 마지막 거래일 기준 상대 거래일

    Returns:
        진입일별 청산 일정

    Raises:
        ValueError: 거래일 목록이 비었거나, 진입일 표에 필요한 컬럼이 없거나,
            진입일이 거래일 목록에 없는 경우
    """
    if len(trading_days) == 0:
        raise ValueError("거래일 목록이 비어 있어 청산일을 정할 수 없습니다")

    missing_columns = set(ENTRY_DTYPES) - set(entries.columns)
    if missing_columns:
        raise ValueError(f"진입일 표에 필수 컬럼이 없습니다: {sorted(missing_columns)}")

    if entries.empty:
        return MonthExitSchedule(frame=_empty_schedule(), exit_offset=exit_offset)

    days = pd.DataFrame({COL_DATE: trading_days})
    days[COL_MONTH] = days[COL_DATE].dt.to_period("M").dt.to_timestamp()

    # 1. 달마다 마지막 거래일과 그 위치를 구한다. 이것이 상대 거래일의 기준점(0)이다
    last_positions = days.groupby(COL_MONTH, sort=True)[COL_DATE].idxmax()
    month_last_position = last_positions.reindex(entries[COL_MONTH]).to_numpy()

    frame = entries.copy()
    frame[COL_EXIT_OFFSET] = exit_offset

    has_month = ~pd.isna(month_last_position)
    safe_month_position = np.where(has_month, month_last_position, 0).astype(np.int64)
    frame[COL_MONTH_LAST_DATE] = pd.DatetimeIndex(
        np.where(has_month, trading_days.to_numpy()[safe_month_position], np.datetime64("NaT", "ns"))
    )

    # 2. 진입일 위치. 진입일이 없는 달은 뒤에서 사유가 유지되므로 자리만 채워 둔다
    has_entry = frame[COL_DATE].notna().to_numpy()
    entry_positions = np.asarray(trading_days.get_indexer(pd.DatetimeIndex(frame[COL_DATE])), dtype=np.int64)
    if has_entry.any() and entry_positions[has_entry].min() < 0:
        unknown = frame.loc[has_entry & (entry_positions < 0), COL_DATE]
        raise ValueError(f"진입일이 거래일 목록에 없습니다: {[day.date().isoformat() for day in unknown]}")

    # 3. 청산 위치는 그 달 마지막 거래일에서 상대 거래일만큼 이동한 자리다
    exit_positions = safe_month_position + exit_offset

    out_of_range = has_entry & has_month & ((exit_positions > len(trading_days) - 1) | (exit_positions < 0))
    no_holding = has_entry & has_month & ~out_of_range & (exit_positions <= entry_positions)

    usable = has_entry & has_month & ~out_of_range & ~no_holding

    # 4. 사유는 **진입 단계의 것을 덮지 않는다.** 진입일이 없던 행은 그 사유를 그대로 둔다
    reasons = frame[COL_EXCLUDED_REASON].to_numpy(dtype=object)
    reasons = np.where(~has_entry, reasons, np.where(out_of_range, REASON_OUT_OF_RANGE, reasons))
    reasons = np.where(has_entry & no_holding, REASON_NO_HOLDING, reasons)
    reasons = np.where(usable, REASON_NONE, reasons)
    frame[COL_EXCLUDED_REASON] = reasons

    # 제외된 행의 청산 위치는 의미가 없다. 인덱싱이 터지지 않도록 범위 안으로 눌러 두고
    # 결과를 NaT 로 덮는다 — 값이 아니라 "확정하지 못했다"를 남기는 것이 목적이다
    safe_exit_position = np.clip(exit_positions, 0, len(trading_days) - 1)
    frame[COL_EXIT_DATE] = pd.DatetimeIndex(
        np.where(usable, trading_days.to_numpy()[safe_exit_position], np.datetime64("NaT", "ns"))
    )
    hold_days = np.where(usable, exit_positions - entry_positions, np.nan)
    frame[COL_HOLD_DAYS] = pd.array(hold_days, dtype="Float64").astype("Int64")

    frame = frame[list(SCHEDULE_DTYPES)].reset_index(drop=True)

    excluded = int((frame[COL_EXCLUDED_REASON] != REASON_NONE).sum())
    logger.debug(
        f"청산 일정 산출: 진입 {len(frame):,}건, 제외 {excluded:,}건, 상대 거래일 {exit_offset}, "
        f"보유 분포 {frame[COL_HOLD_DAYS].value_counts().sort_index().to_dict()}"
    )

    return MonthExitSchedule(frame=frame, exit_offset=exit_offset)


def month_exit_returns(
    df: pd.DataFrame,
    schedule: MonthExitSchedule,
    *,
    price_column: str = COL_CLOSE,
) -> pd.DataFrame:
    """청산 일정에 가격을 붙여 long-form 수익률을 낸다.

    구간 축(`COL_HORIZON`)에는 실제 보유 거래일 수가 아니라 **표지 하나**를 넣는다.
    보유일수를 넣으면 한 매매가 길이별 여러 칸으로 쪼개져 묶음 값이 나오지 않는다.
    실제 보유일수는 별도 컬럼으로 남으므로 분포는 그대로 보고할 수 있다.

    기준은 **종가**뿐이다. 이 매매의 정의가 "진입일 종가 매수 → 청산일 종가 매도"이며
    익일 시가 진입은 다른 매매다.

    Args:
        df: 날짜 오름차순 가격 데이터. ETF 는 시세 스키마, 지수는 단일 값 계열이다
        schedule: `month_exit_schedule` 의 결과
        price_column: 가격 컬럼 이름. ETF 는 `Close`, 지수는 `Value`

    Returns:
        `RETURN_COLUMNS` 순서의 long-form DataFrame. 행 수는 **진입 수와 같다** —
        제외된 진입도 값만 비운 채 남는다. 입력은 변경하지 않는다

    Raises:
        ValueError: 가격 데이터가 비었거나 필수 컬럼이 없는 경우, 날짜가 오름차순이 아닌 경우,
            진입일의 가격이 없는 경우
        RuntimeError: 제외되지 않은 진입의 수익률이 비어 있는 경우 (내부 불변조건 위반)
    """
    validate_market_frame(df, [COL_DATE, price_column])

    if schedule.entry_count == 0:
        logger.debug("진입이 없습니다")
        return _empty_returns()

    prices = df.set_index(COL_DATE)[price_column]
    frame = schedule.frame.copy()

    entry_price = frame[COL_DATE].map(prices)
    valid = frame[COL_EXCLUDED_REASON] == REASON_NONE
    if entry_price[valid].isna().any():
        unknown = frame.loc[valid & entry_price.isna(), COL_DATE]
        raise ValueError(f"진입일의 가격이 없습니다: {[day.date().isoformat() for day in unknown]}")

    # 제외된 행은 청산일이 비어 있으므로 가격도 비어 있다. `map` 이 그대로 NaN 을 돌려준다
    exit_price = frame[COL_EXIT_DATE].map(prices)

    frame[COL_ENTRY_CLOSE] = entry_price
    frame[COL_EXIT_CLOSE] = exit_price
    frame[COL_BASIS] = ReturnBasis.CLOSE.value
    frame[COL_HORIZON] = HORIZON_MONTH_END
    frame[COL_FORWARD_RETURN] = exit_price / entry_price - 1.0

    if not frame.loc[valid, COL_FORWARD_RETURN].notna().all():
        raise RuntimeError("내부 불변조건 위반: 제외되지 않은 진입의 수익률이 비어 있습니다")

    logger.debug(f"청산 수익률 계산 완료: 진입 {len(frame):,}건, 유효 {int(valid.sum()):,}건")

    return frame[RETURN_COLUMNS]


def every_day_entries(trading_days: pd.DatetimeIndex, *, calendar_day: int) -> pd.DataFrame:
    """**전 거래일**을 진입일로 삼은 표를 만든다 — 기준선 「그 달 아무 날 진입」용이다.

    신호와 **같은 함수**(`month_exit_schedule`)에 넣어 청산일을 정하므로 기준선의 보유 길이
    분포가 신호와 같은 달력 구조에서 나온다. 기준선을 따로 구현하면 두 계산이 조용히 갈라진다.

    **데이터의 마지막 달은 신호와 같은 이유로 뺀다**(결정 ⑧). 기준선만 그 달을 포함하면
    비교 구간이 어긋난다.

    Args:
        trading_days: 거래일 목록
        calendar_day: 격자 축을 맞추기 위한 표지. 기준선 자신은 달력일을 쓰지 않지만
            신호와 같은 칸으로 묶여야 집계가 나란히 선다

    Returns:
        `ENTRY_DTYPES` 구성의 DataFrame. **거래일마다 한 행**이다

    Raises:
        ValueError: 거래일 목록이 비었거나 정렬·중복 조건을 어긴 경우
    """
    if len(trading_days) == 0:
        raise ValueError("거래일 목록이 비어 있어 기준선 진입일을 만들 수 없습니다")
    if not trading_days.is_monotonic_increasing:
        raise ValueError("거래일 목록이 오름차순으로 정렬되어 있어야 합니다")
    if trading_days.has_duplicates:
        raise ValueError("거래일 목록에 중복된 날짜가 있습니다")

    days = pd.DataFrame({COL_DATE: trading_days})
    days[COL_MONTH] = days[COL_DATE].dt.to_period("M").dt.to_timestamp()

    last_month = days[COL_MONTH].iloc[-1]
    days = days[days[COL_MONTH] < last_month].reset_index(drop=True)

    days[COL_TARGET_DAY] = calendar_day
    days[COL_EXCLUDED_REASON] = REASON_NONE

    return days[list(ENTRY_DTYPES)]


def converged_month_count(entries: pd.DataFrame, other: pd.DataFrame) -> int:
    """두 진입 달력일이 **같은 거래일로 수렴한** 달의 수를 센다.

    앞당김 때문에 서로 다른 달력일 칸이 같은 표본을 공유한다(결정 ⑥). 격자의 칸들이
    독립이 아니라는 사실의 근거값이므로 산출물에 남긴다.

    Args:
        entries: 한 달력일의 진입일 표
        other: 다른 달력일의 진입일 표

    Returns:
        진입일이 같은 달의 수. 어느 한쪽이라도 진입일이 없는 달은 세지 않는다
    """
    merged = entries[[COL_MONTH, COL_DATE]].merge(
        other[[COL_MONTH, COL_DATE]], on=COL_MONTH, how="inner", suffixes=("_left", "_right")
    )
    both = merged[f"{COL_DATE}_left"].notna() & merged[f"{COL_DATE}_right"].notna()

    return int((both & (merged[f"{COL_DATE}_left"] == merged[f"{COL_DATE}_right"])).sum())


def _empty_entries() -> pd.DataFrame:
    """진입일이 하나도 없을 때 돌려줄 빈 표를 만든다.

    Returns:
        진입일 표와 같은 스키마의 빈 DataFrame
    """
    return pd.DataFrame({column: pd.Series(dtype=dtype) for column, dtype in ENTRY_DTYPES.items()})


def _empty_schedule() -> pd.DataFrame:
    """진입이 하나도 없을 때 돌려줄 빈 일정표를 만든다.

    Returns:
        일정표와 같은 스키마의 빈 DataFrame
    """
    return pd.DataFrame({column: pd.Series(dtype=dtype) for column, dtype in SCHEDULE_DTYPES.items()})


def _empty_returns() -> pd.DataFrame:
    """진입이 하나도 없을 때 돌려줄 빈 수익률 표를 만든다.

    값이 없다는 이유로 dtype 이 흔들리면 아래 계층의 집계 키가 진입 유무에 따라 갈린다.

    Returns:
        `RETURN_COLUMNS` 구성을 갖춘 0행 DataFrame
    """
    empty = _empty_schedule()
    empty[COL_ENTRY_CLOSE] = pd.Series(dtype="float64")
    empty[COL_EXIT_CLOSE] = pd.Series(dtype="float64")
    empty[COL_BASIS] = pd.Series(dtype=object)
    empty[COL_HORIZON] = pd.Series(dtype="int64")
    empty[COL_FORWARD_RETURN] = pd.Series(dtype="float64")

    return empty[RETURN_COLUMNS]


__all__ = [
    "MonthExitSchedule",
    "converged_month_count",
    "every_day_entries",
    "month_entry_dates",
    "month_exit_returns",
    "month_exit_schedule",
]
