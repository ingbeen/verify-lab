"""달력으로 정해지는 청산일 — 다음 주 지정 요일과 그 달 말일 기준 상대 거래일

`forward_return.py` 는 **고정 거래일 구간**만 잰다. 청산이 달력으로 정해지는 매매법은
보유 거래일 수가 신호마다 달라 그 틀에 들어가지 않으므로 청산일을 따로 만든다.

**두 규칙이 있다.**

| 규칙 | 청산일 | 쓰는 매매법 |
| --- | --- | --- |
| 주 기준 | 주 기준일이 속한 주의 **다음 주** 지정 요일 | 옵션 만기일 · 만기_말일 |
| 말일 기준 | 그 달 마지막 거래일에서 상대 거래일만큼 이동한 날 | 월말 진입 · 만기_말일 |

**주 기준일은 진입일이 아니다.** 만기 진입에서는 **규칙일**이며, 앞당김은 진입 쪽 사정이라
목표 주까지 끌고 가면 연휴가 낀 달의 보유가 하루로 무너져 같은 표의 다른 행과 다른 물건이 된다.
베이스라인처럼 둘이 같은 경우는 같은 값을 두 번 넘기면 된다.

**목표일이 휴장이면 직전 거래일에 청산한다.** 진입 앞당김이 이미 쓰는 관용이라 저장소 안에
휴장 규칙이 하나로 유지된다.

**목표일이 데이터 끝을 넘는 진입은 값을 지어내지 않는다.** 행은 남기고 값만 비운 뒤 사유를
달아 `진입 수 = 유효 + 제외` 가 성립하게 한다 — 행을 지우면 표본이 조용히 줄어 생존편향이 생긴다.

**구간 표지(`horizon`)를 인자로 받는다.** 그 값은 매매법마다 다른 묶음 표지라 공통 계층이
들면 한 매매법의 값이 모든 매매법의 기본값이 된다.

**공통 계층이 소유한다.** 매매법끼리는 import 할 수 없으므로(`tests/test_layer_contracts.py`)
세 매매법이 같은 달력을 쓰려면 여기 있어야 하고, 복제하면 같은 달력이 조용히 갈라진다
(패키지 절대 원칙 「판정식 단일화」).

거래소 휴장일은 사전에 공표되므로 이 판정은 미래를 참조하지 않는다. 다만 구현이 판정일 이후의
데이터에 의존하지 않는지는 look-ahead 감시 테스트로 고정한다.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE
from verify_lab.data.loader import validate_market_frame
from verify_lab.measure.calendar_entry import ENTRY_DTYPES, validate_trading_days
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_ENTRY_CLOSE,
    COL_EXCLUDED_REASON,
    COL_EXIT_CLOSE,
    COL_EXIT_DATE,
    COL_EXIT_OFFSET,
    COL_FORWARD_RETURN,
    COL_HOLD_DAYS,
    COL_HORIZON,
    COL_MONTH,
    COL_MONTH_LAST_DATE,
    COL_TARGET_DATE,
    COL_TARGET_DAY,
    COL_WEEK_REFERENCE,
    REASON_NO_HOLDING,
    REASON_NO_TRADING_DAY,
    REASON_NONE,
    REASON_OUT_OF_RANGE,
)
from verify_lab.measure.forward_return import ReturnBasis
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 주 기준일이 속한 주의 월요일에서 목표 요일까지의 달력일 수. 다음 주이므로 한 주를 더한다
DAYS_TO_NEXT_WEEK = 7

# 주 기준 청산 일정표의 컬럼과 dtype. 빈 결과에서도 같은 스키마를 유지해 호출 측이 분기하지 않게 한다
WEEKLY_SCHEDULE_DTYPES = {
    COL_DATE: "datetime64[ns]",
    COL_WEEK_REFERENCE: "datetime64[ns]",
    COL_TARGET_DATE: "datetime64[ns]",
    COL_EXIT_DATE: "datetime64[ns]",
    COL_HOLD_DAYS: "Int64",
    COL_EXCLUDED_REASON: "object",
}

# 말일 기준 청산 일정표의 컬럼과 dtype
MONTH_SCHEDULE_DTYPES = {
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
WEEKLY_RETURN_COLUMNS = [
    COL_DATE,
    COL_WEEK_REFERENCE,
    COL_TARGET_DATE,
    COL_EXIT_DATE,
    COL_HOLD_DAYS,
    COL_ENTRY_CLOSE,
    COL_EXIT_CLOSE,
    COL_BASIS,
    COL_HORIZON,
    COL_FORWARD_RETURN,
    COL_EXCLUDED_REASON,
]

MONTH_RETURN_COLUMNS = [
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
class WeeklyExitSchedule:
    """진입일별 「다음 주 지정 요일」 청산 일정

    Attributes:
        frame: 진입일·주 기준일·목표일·청산일·보유 거래일수·제외 사유를 담은 DataFrame.
            **제외된 진입도 행으로 남는다** — 값만 비어 있고 사유가 붙는다
    """

    frame: pd.DataFrame

    @property
    def entry_count(self) -> int:
        """진입 수.

        Returns:
            진입일의 수
        """
        return len(self.frame)


@dataclass(frozen=True)
class MonthExitSchedule:
    """진입일별 「그 달 말일 기준 상대 거래일」 청산 일정

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


def weekly_exit_schedule(
    trading_days: pd.DatetimeIndex,
    entry_dates: pd.DatetimeIndex,
    week_reference_dates: pd.DatetimeIndex,
    *,
    exit_weekday: int,
) -> WeeklyExitSchedule:
    """진입일마다 「주 기준일이 속한 주의 다음 주 지정 요일」 청산일을 정한다.

    진입일과 주 기준일을 따로 받는다. 만기 진입에서는 두 값이 다르다 — 진입은 앞당겨진
    실제 만기일이고 주 기준은 규칙일이다. 베이스라인처럼 둘이 같은 경우는 같은 값을
    두 번 넘기면 된다.

    Args:
        trading_days: 거래일 목록. 오름차순 정렬된 중복 없는 인덱스여야 한다
        entry_dates: 진입일 목록. 전부 `trading_days` 안에 있어야 한다
        week_reference_dates: 주를 세는 기준일. `entry_dates` 와 길이가 같아야 한다
        exit_weekday: 청산 목표 요일 (월=0 ~ 일=6)

    Returns:
        진입일별 청산 일정

    Raises:
        ValueError: 거래일 목록이 비었거나 정렬·중복 조건을 어긴 경우, 두 날짜 축의 길이가
            다른 경우, 진입일이 거래일 목록에 없는 경우, 청산 요일이 범위를 벗어난 경우
    """
    if not 0 <= exit_weekday <= 6:
        raise ValueError(f"청산 요일은 0(월)~6(일) 이어야 합니다: {exit_weekday}")
    validate_trading_days(trading_days, purpose="청산일")
    if len(entry_dates) != len(week_reference_dates):
        raise ValueError(f"진입일과 주 기준일의 길이가 다릅니다: 진입일 {len(entry_dates)}개, 주 기준일 {len(week_reference_dates)}개")

    if len(entry_dates) == 0:
        return WeeklyExitSchedule(frame=empty_weekly_schedule())

    entry_positions = np.asarray(trading_days.get_indexer(entry_dates), dtype=np.int64)
    if entry_positions.min() < 0:
        missing = entry_dates[entry_positions < 0]
        raise ValueError(f"진입일이 거래일 목록에 없습니다: {[day.date().isoformat() for day in missing]}")

    # 1. 주 기준일이 속한 주의 월요일에서 다음 주 목표 요일까지 간다. 달력 연산이므로
    #    휴장 여부와 무관하게 언제나 같은 날을 지목한다
    week_monday = week_reference_dates - pd.to_timedelta(week_reference_dates.dayofweek, unit="D")
    target_dates = week_monday + pd.to_timedelta(DAYS_TO_NEXT_WEEK + exit_weekday, unit="D")

    # 2. 목표일이 휴장이면 **직전 거래일**에 청산한다. 목표일이 거래일이면 그날 자신이다
    exit_positions = np.asarray(trading_days.searchsorted(target_dates, side="right"), dtype=np.int64) - 1

    # 3. 목표일이 데이터 끝을 넘으면 청산일을 확정할 수 없다. 값을 지어내지 않는다 —
    #    있는 데이터까지 잡으면 보유 기간이 다른 표본이 같은 평균에 섞인다
    out_of_range = target_dates > trading_days[-1]
    no_trading_day = ~out_of_range & (exit_positions <= entry_positions)

    reasons = np.where(out_of_range, REASON_OUT_OF_RANGE, np.where(no_trading_day, REASON_NO_TRADING_DAY, REASON_NONE))
    usable = ~(out_of_range | no_trading_day)

    # 제외된 행의 청산 위치는 의미가 없다. 인덱싱이 터지지 않도록 범위 안으로 눌러 두고
    # 결과를 NaT 로 덮는다 — 값이 아니라 "확정하지 못했다"를 남기는 것이 목적이다
    safe_positions = np.clip(exit_positions, 0, len(trading_days) - 1)
    exit_dates = np.where(usable, trading_days.to_numpy()[safe_positions], np.datetime64("NaT", "ns"))
    hold_days = np.where(usable, exit_positions - entry_positions, np.nan)

    frame = pd.DataFrame(
        {
            COL_DATE: entry_dates,
            COL_WEEK_REFERENCE: week_reference_dates,
            COL_TARGET_DATE: target_dates,
            COL_EXIT_DATE: pd.DatetimeIndex(exit_dates),
            COL_HOLD_DAYS: pd.array(hold_days, dtype="Float64").astype("Int64"),
            COL_EXCLUDED_REASON: reasons,
        }
    )

    excluded = int((~usable).sum())
    logger.debug(
        f"청산 일정 산출: 진입 {len(frame):,}건, 제외 {excluded:,}건, 청산 요일 {exit_weekday}, "
        f"보유 분포 {frame[COL_HOLD_DAYS].value_counts().sort_index().to_dict()}"
    )

    return WeeklyExitSchedule(frame=frame)


def month_exit_schedule(
    trading_days: pd.DatetimeIndex,
    entries: pd.DataFrame,
    *,
    exit_offset: int,
) -> MonthExitSchedule:
    """진입일마다 「그 달 마지막 거래일 기준 상대 거래일」 청산일을 정한다.

    상대 거래일 0 은 그 달 마지막 거래일, 음수는 그 이전, 양수는 익월이다.

    Args:
        trading_days: 거래일 목록. 진입일을 만들 때 넘긴 것과 같아야 한다
        entries: `calendar_entry` 가 낸 진입일 표 (`ENTRY_DTYPES` 구성)
        exit_offset: 그 달 마지막 거래일 기준 상대 거래일

    Returns:
        진입일별 청산 일정

    Raises:
        ValueError: 거래일 목록이 비었거나 정렬·중복 조건을 어긴 경우, 진입일 표에 필요한
            컬럼이 없는 경우, 진입일이 거래일 목록에 없는 경우
        RuntimeError: 진입일이 있는데 그 진입 달이 거래일 목록에 없는 경우
            (내부 불변조건 위반)
    """
    # **두 진입점이 같은 가드를 쓴다.** 한쪽만 정렬·중복을 안 보면 `groupby.idxmax` 와
    # `get_indexer` 가 조용히 엉뚱한 위치를 내는데 예외가 나지 않는다
    validate_trading_days(trading_days, purpose="청산일")

    missing_columns = set(ENTRY_DTYPES) - set(entries.columns)
    if missing_columns:
        raise ValueError(f"진입일 표에 필수 컬럼이 없습니다: {sorted(missing_columns)}")

    if entries.empty:
        return MonthExitSchedule(frame=empty_month_schedule(), exit_offset=exit_offset)

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

    # **「진입일은 있는데 그 달이 없다」는 상태를 여기서 끊는다.** 그런 행은 `usable` 이
    # 거짓인데 아래 세 갈래 어디에도 걸리지 않아 **진입 단계의 사유가 그대로 남는다** —
    # 유효로 세어지면서 청산일은 `NaT` 인 행이 되어 「진입 = 유효 + 제외」가 조용히 깨진다.
    # 진입일은 `trading_days` 에서 나오므로 그 달은 반드시 존재한다 — 도달하면 버그다
    broken = has_entry & ~has_month
    if broken.any():
        months = frame.loc[broken, COL_MONTH]
        raise RuntimeError(
            f"내부 불변조건 위반: 진입일이 있는데 그 달이 거래일 목록에 없습니다: " f"{[month.strftime('%Y-%m') for month in months]}"
        )

    # 3. 청산 위치는 그 달 마지막 거래일에서 상대 거래일만큼 이동한 자리다.
    # **아래 셋에 `has_month` 를 다시 걸지 않는다** — 바로 위 가드가 `has_entry & ~has_month` 를
    # 끊어 여기서는 `has_entry` 가 참이면 `has_month` 도 참이다. 그 가드를 지우려는 사람은
    # 이 셋도 함께 봐야 한다. (`safe_month_position` 쪽 `has_month` 는 가드 «앞»이라 살아 있다)
    exit_positions = safe_month_position + exit_offset

    out_of_range = has_entry & ((exit_positions > len(trading_days) - 1) | (exit_positions < 0))
    no_holding = has_entry & ~out_of_range & (exit_positions <= entry_positions)

    usable = has_entry & ~out_of_range & ~no_holding

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

    frame = frame[list(MONTH_SCHEDULE_DTYPES)].reset_index(drop=True)

    excluded = int((frame[COL_EXCLUDED_REASON] != REASON_NONE).sum())
    logger.debug(
        f"청산 일정 산출: 진입 {len(frame):,}건, 제외 {excluded:,}건, 상대 거래일 {exit_offset}, "
        f"보유 분포 {frame[COL_HOLD_DAYS].value_counts().sort_index().to_dict()}"
    )

    return MonthExitSchedule(frame=frame, exit_offset=exit_offset)


def weekly_exit_returns(
    df: pd.DataFrame,
    schedule: WeeklyExitSchedule,
    *,
    horizon: int,
    price_column: str = COL_CLOSE,
) -> pd.DataFrame:
    """주 기준 청산 일정에 가격을 붙여 long-form 수익률을 낸다.

    구간 축(`COL_HORIZON`)에는 실제 보유 거래일 수가 아니라 **표지 하나**를 넣는다.
    보유일수를 넣으면 한 매매가 길이별 여러 칸으로 쪼개져 묶음 값이 나오지 않는다.
    실제 보유일수는 별도 컬럼으로 남으므로 분포는 그대로 보고할 수 있다.

    기준은 **종가**뿐이다. 이 매매의 정의가 "진입일 종가 매수 → 목표일 종가 매도" 이며
    익일 시가 진입은 다른 매매다.

    Args:
        df: 날짜 오름차순 가격 데이터. ETF 는 시세 스키마, 지수는 단일 값 계열이다
        schedule: `weekly_exit_schedule` 의 결과
        horizon: 구간 축에 넣을 묶음 표지. **매매법이 정한다** — 실제 보유일수로는
            도달할 수 없는 값이라야 진짜 구간과 섞이지 않는다
        price_column: 가격 컬럼 이름. ETF 는 `Close`, 지수는 `Value`

    Returns:
        `WEEKLY_RETURN_COLUMNS` 순서의 long-form DataFrame. 행 수는 **진입 수와 같다** —
        제외된 진입도 값만 비운 채 남는다. 입력은 변경하지 않는다

    Raises:
        ValueError: 가격 데이터가 비었거나 필수 컬럼이 없는 경우, 날짜가 오름차순이 아닌 경우,
            진입일의 가격이 없는 경우
        RuntimeError: 제외되지 않은 진입의 수익률이 비어 있는 경우 (내부 불변조건 위반)
    """
    validate_market_frame(df, [COL_DATE, price_column])

    if schedule.entry_count == 0:
        logger.debug("진입이 없습니다")
        return _empty_returns(empty_weekly_schedule(), WEEKLY_RETURN_COLUMNS)

    prices = df.set_index(COL_DATE)[price_column]
    frame = schedule.frame.copy()

    entry_price = frame[COL_DATE].map(prices)
    if entry_price.isna().any():
        missing = frame.loc[entry_price.isna(), COL_DATE]
        raise ValueError(f"진입일의 가격이 없습니다: {[day.date().isoformat() for day in missing]}")

    # 제외된 행은 청산일이 비어 있으므로 가격도 비어 있다. `map` 이 그대로 NaN 을 돌려준다
    exit_price = frame[COL_EXIT_DATE].map(prices)

    frame[COL_ENTRY_CLOSE] = entry_price
    frame[COL_EXIT_CLOSE] = exit_price
    frame[COL_BASIS] = ReturnBasis.CLOSE.value
    frame[COL_HORIZON] = horizon
    frame[COL_FORWARD_RETURN] = exit_price / entry_price - 1.0

    valid = frame[COL_EXCLUDED_REASON] == REASON_NONE
    if not frame.loc[valid, COL_FORWARD_RETURN].notna().all():
        raise RuntimeError("내부 불변조건 위반: 제외되지 않은 진입의 수익률이 비어 있습니다")

    logger.debug(f"청산 수익률 계산 완료: 진입 {len(frame):,}건, 유효 {int(valid.sum()):,}건")

    return frame[WEEKLY_RETURN_COLUMNS]


def month_exit_returns(
    df: pd.DataFrame,
    schedule: MonthExitSchedule,
    *,
    horizon: int,
    price_column: str = COL_CLOSE,
) -> pd.DataFrame:
    """말일 기준 청산 일정에 가격을 붙여 long-form 수익률을 낸다.

    구간 축(`COL_HORIZON`)에는 실제 보유 거래일 수가 아니라 **표지 하나**를 넣는다.
    보유일수를 넣으면 한 매매가 길이별 여러 칸으로 쪼개져 묶음 값이 나오지 않는다.

    기준은 **종가**뿐이다. 이 매매의 정의가 "진입일 종가 매수 → 청산일 종가 매도"이며
    익일 시가 진입은 다른 매매다.

    Args:
        df: 날짜 오름차순 가격 데이터. ETF 는 시세 스키마, 지수는 단일 값 계열이다
        schedule: `month_exit_schedule` 의 결과
        horizon: 구간 축에 넣을 묶음 표지. **매매법이 정한다**
        price_column: 가격 컬럼 이름. ETF 는 `Close`, 지수는 `Value`

    Returns:
        `MONTH_RETURN_COLUMNS` 순서의 long-form DataFrame. 행 수는 **진입 수와 같다** —
        제외된 진입도 값만 비운 채 남는다. 입력은 변경하지 않는다

    Raises:
        ValueError: 가격 데이터가 비었거나 필수 컬럼이 없는 경우, 날짜가 오름차순이 아닌 경우,
            진입일의 가격이 없는 경우
        RuntimeError: 제외되지 않은 진입의 수익률이 비어 있는 경우 (내부 불변조건 위반)
    """
    validate_market_frame(df, [COL_DATE, price_column])

    if schedule.entry_count == 0:
        logger.debug("진입이 없습니다")
        return _empty_returns(empty_month_schedule(), MONTH_RETURN_COLUMNS)

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
    frame[COL_HORIZON] = horizon
    frame[COL_FORWARD_RETURN] = exit_price / entry_price - 1.0

    if not frame.loc[valid, COL_FORWARD_RETURN].notna().all():
        raise RuntimeError("내부 불변조건 위반: 제외되지 않은 진입의 수익률이 비어 있습니다")

    logger.debug(f"청산 수익률 계산 완료: 진입 {len(frame):,}건, 유효 {int(valid.sum()):,}건")

    return frame[MONTH_RETURN_COLUMNS]


def empty_weekly_schedule() -> pd.DataFrame:
    """주 기준 진입이 하나도 없을 때 돌려줄 빈 일정표를 만든다.

    Returns:
        일정표와 같은 스키마의 빈 DataFrame
    """
    return pd.DataFrame({column: pd.Series(dtype=dtype) for column, dtype in WEEKLY_SCHEDULE_DTYPES.items()})


def empty_month_schedule() -> pd.DataFrame:
    """말일 기준 진입이 하나도 없을 때 돌려줄 빈 일정표를 만든다.

    Returns:
        일정표와 같은 스키마의 빈 DataFrame
    """
    return pd.DataFrame({column: pd.Series(dtype=dtype) for column, dtype in MONTH_SCHEDULE_DTYPES.items()})


def _empty_returns(schedule: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """진입이 하나도 없을 때 돌려줄 빈 수익률 표를 만든다.

    값이 없다는 이유로 dtype 이 흔들리면 아래 계층의 집계 키가 진입 유무에 따라 갈린다.

    **인자를 변형하지 않는다** — 호출 측이 살아 있는 일정표를 넘기면 그 프레임에 다섯
    컬럼이 붙어 버린다. 지금은 두 호출부 모두 갓 만든 빈 표를 넘기지만, 시그니처가
    그 오용을 부른다.

    Args:
        schedule: 그 일정표와 같은 스키마의 DataFrame
        columns: 돌려줄 컬럼 순서

    Returns:
        요청한 구성을 갖춘 0행 DataFrame
    """
    empty = schedule.copy()
    empty[COL_ENTRY_CLOSE] = pd.Series(dtype="float64")
    empty[COL_EXIT_CLOSE] = pd.Series(dtype="float64")
    empty[COL_BASIS] = pd.Series(dtype=object)
    empty[COL_HORIZON] = pd.Series(dtype="int64")
    empty[COL_FORWARD_RETURN] = pd.Series(dtype="float64")

    return empty[columns]


__all__ = [
    "MONTH_RETURN_COLUMNS",
    "MONTH_SCHEDULE_DTYPES",
    "WEEKLY_RETURN_COLUMNS",
    "WEEKLY_SCHEDULE_DTYPES",
    "MonthExitSchedule",
    "WeeklyExitSchedule",
    "empty_month_schedule",
    "empty_weekly_schedule",
    "month_exit_returns",
    "month_exit_schedule",
    "weekly_exit_returns",
    "weekly_exit_schedule",
]
