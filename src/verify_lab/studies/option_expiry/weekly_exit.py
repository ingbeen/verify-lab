"""달력 기준 청산 — 진입일 종가 매수 → 다음주 지정 요일 종가 매도

`measure/forward_return.py` 는 **고정 거래일 구간**만 잰다. 이 매매는 청산이 **달력 기준**이라
보유 거래일 수가 신호마다 다르므로 그 틀에 들어가지 않는다 — 미국은 만기 다음 주에 휴장이 잦아
330건 중 78건이 5거래일이 아니라 4거래일이고, 한국은 목요일 만기라 대부분 6거래일이다
(`docs/spec/option_expiry.md` 결정 ⑯).

**목표일은 「주 기준일이 속한 주」의 다음 주 지정 요일**이다. 만기 진입에서 주 기준일은
실제 만기일이 아니라 **규칙일**이다 — 앞당김은 만기 쪽 사정이고, 실제 만기일로 세면 한국
2025-10(추석) 의 보유가 1거래일로 무너져 같은 표의 다른 행과 다른 물건이 된다(결정 ⑰).

**목표일이 휴장이면 직전 거래일에 청산한다**(결정 ⑱). 만기 앞당김이 이미 쓰는 관용이라
저장소 안에 휴장 규칙이 하나로 유지된다.

**목표일이 데이터 끝을 넘는 진입은 값을 지어내지 않는다**(결정 ⑲). 행은 남기고 값만 비운 뒤
사유를 달아 `진입 수 = 유효 + 제외` 가 성립하게 한다 — 행을 지우면 표본이 조용히 줄어
생존편향이 생긴다.

거래소 휴장일은 사전에 공표되므로 이 판정은 미래를 참조하지 않는다. 다만 구현이 판정일 이후의
데이터에 의존하지 않는지는 look-ahead 감시 테스트로 고정한다.
"""

from dataclasses import dataclass
from enum import Enum

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
from verify_lab.studies.option_expiry.constants import (
    COL_ENTRY_CLOSE,
    COL_EXIT_CLOSE,
    COL_EXIT_DATE,
    COL_HOLD_DAYS,
    COL_TARGET_DATE,
    COL_WEEK_REFERENCE,
    HORIZON_NEXT_WEEK_EXIT,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 주 기준일이 속한 주의 월요일에서 목표 요일까지의 달력일 수. 다음 주이므로 한 주를 더한다
DAYS_TO_NEXT_WEEK = 7

# 청산일이 진입일보다 뒤가 아닌 경우의 사유. 목표일까지 사이에 거래일이 하나도 없는 달에서만
# 생기며, 값을 지어내는 대신 제외하고 사유를 남긴다
REASON_NO_TRADING_DAY = "진입일과 목표일 사이에 거래일이 없음"

# 청산 일정표의 컬럼과 dtype. 빈 결과에서도 같은 스키마를 유지해 호출 측이 분기하지 않게 한다
SCHEDULE_DTYPES = {
    COL_DATE: "datetime64[ns]",
    COL_WEEK_REFERENCE: "datetime64[ns]",
    COL_TARGET_DATE: "datetime64[ns]",
    COL_EXIT_DATE: "datetime64[ns]",
    COL_HOLD_DAYS: "Int64",
    COL_EXCLUDED_REASON: "object",
}

# 수익률 표에 함께 남기는 가격. 사용자가 차트로 직접 대조하는 원자료다 (측정의 원칙 8)
RETURN_COLUMNS = [
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

REQUIRED_MARKET_COLUMNS = [COL_DATE, COL_CLOSE]


class HolidayExit(Enum):
    """청산 목표일이 휴장일 때 어느 쪽으로 갈 것인가

    본검증은 `PREVIOUS` 다 — 만기 앞당김이 이미 쓰는 관용이라 저장소 안에 휴장 규칙이 하나로
    유지되고, "그 주 안에서 나온다"는 의도가 지켜진다. `NEXT` 는 **대조 전용**이며,
    규칙 선택이 결론을 만들지 않았음을 보이기 위해 함께 산출한다
    (`docs/spec/option_expiry.md` 결정 ⑱·㉔).

    목표일이 거래일이면 두 값은 같은 답을 낸다.

    Attributes:
        PREVIOUS: 직전 거래일에 청산 (본검증)
        NEXT: 다음 거래일에 청산 (대조)
    """

    PREVIOUS = "직전 거래일 청산"
    NEXT = "다음 거래일 청산"


@dataclass(frozen=True)
class WeeklyExitSchedule:
    """진입일별 청산 일정

    Attributes:
        frame: 진입일·주 기준일·목표일·청산일·보유 거래일수·제외 사유를 담은 DataFrame.
            **제외된 진입도 행으로 남는다** — 값만 비어 있고 사유가 붙는다
        exit_weekday: 청산 목표 요일 (월=0 ~ 일=6)
        on_holiday: 목표일이 휴장일 때 적용한 규칙
    """

    frame: pd.DataFrame
    exit_weekday: int
    on_holiday: HolidayExit

    @property
    def entry_count(self) -> int:
        """진입 수.

        Returns:
            진입일의 수
        """
        return len(self.frame)

    @property
    def excluded_count(self) -> int:
        """청산일을 확정하지 못해 제외된 진입 수.

        Returns:
            제외된 진입의 수
        """
        return int((self.frame[COL_EXCLUDED_REASON] != REASON_NONE).sum())

    @property
    def valid_count(self) -> int:
        """청산일이 확정된 진입 수.

        Returns:
            유효한 진입의 수
        """
        return self.entry_count - self.excluded_count


def weekly_exit_schedule(
    trading_days: pd.DatetimeIndex,
    entry_dates: pd.DatetimeIndex,
    week_reference_dates: pd.DatetimeIndex,
    *,
    exit_weekday: int,
    on_holiday: HolidayExit = HolidayExit.PREVIOUS,
) -> WeeklyExitSchedule:
    """진입일마다 「주 기준일이 속한 주의 다음 주 지정 요일」 청산일을 정한다.

    진입일과 주 기준일을 따로 받는다. 만기 진입에서는 두 값이 다르다 — 진입은 앞당겨진
    실제 만기일이고 주 기준은 규칙일이다(결정 ⑰). 베이스라인처럼 둘이 같은 경우는 같은 값을
    두 번 넘기면 된다.

    Args:
        trading_days: 거래일 목록. 오름차순 정렬된 중복 없는 인덱스여야 한다
        entry_dates: 진입일 목록. 전부 `trading_days` 안에 있어야 한다
        week_reference_dates: 주를 세는 기준일. `entry_dates` 와 길이가 같아야 한다
        exit_weekday: 청산 목표 요일 (월=0 ~ 일=6)
        on_holiday: 목표일이 휴장일 때의 규칙. 본검증은 직전 거래일이며 다음 거래일은 대조 전용이다

    Returns:
        진입일별 청산 일정

    Raises:
        ValueError: 거래일 목록이 비었거나 정렬·중복 조건을 어긴 경우, 두 날짜 축의 길이가
            다른 경우, 진입일이 거래일 목록에 없는 경우, 청산 요일이 범위를 벗어난 경우
    """
    if not 0 <= exit_weekday <= 6:
        raise ValueError(f"청산 요일은 0(월)~6(일) 이어야 합니다: {exit_weekday}")
    if len(trading_days) == 0:
        raise ValueError("거래일 목록이 비어 있어 청산일을 정할 수 없습니다")
    if not trading_days.is_monotonic_increasing:
        raise ValueError("거래일 목록이 오름차순으로 정렬되어 있어야 합니다")
    if trading_days.has_duplicates:
        raise ValueError("거래일 목록에 중복된 날짜가 있습니다")
    if len(entry_dates) != len(week_reference_dates):
        raise ValueError(f"진입일과 주 기준일의 길이가 다릅니다: 진입일 {len(entry_dates)}개, 주 기준일 {len(week_reference_dates)}개")

    if len(entry_dates) == 0:
        return WeeklyExitSchedule(frame=_empty_schedule(), exit_weekday=exit_weekday, on_holiday=on_holiday)

    entry_positions = np.asarray(trading_days.get_indexer(entry_dates), dtype=np.int64)
    if entry_positions.min() < 0:
        missing = entry_dates[entry_positions < 0]
        raise ValueError(f"진입일이 거래일 목록에 없습니다: {[day.date().isoformat() for day in missing]}")

    # 1. 주 기준일이 속한 주의 월요일에서 다음 주 목표 요일까지 간다. 달력 연산이므로
    #    휴장 여부와 무관하게 언제나 같은 날을 지목한다
    week_monday = week_reference_dates - pd.to_timedelta(week_reference_dates.dayofweek, unit="D")
    target_dates = week_monday + pd.to_timedelta(DAYS_TO_NEXT_WEEK + exit_weekday, unit="D")

    # 2. 청산 위치를 정한다. 목표일이 거래일이면 두 규칙 모두 그날 자신을 가리킨다 —
    #    갈리는 것은 목표일이 휴장인 달뿐이다
    if on_holiday is HolidayExit.PREVIOUS:
        exit_positions = np.asarray(trading_days.searchsorted(target_dates, side="right"), dtype=np.int64) - 1
    else:
        exit_positions = np.asarray(trading_days.searchsorted(target_dates, side="left"), dtype=np.int64)

    # 3. 목표일이 데이터 끝을 넘으면 청산일을 확정할 수 없다. 값을 지어내지 않는다 —
    #    있는 데이터까지 잡으면 보유 기간이 다른 표본이 같은 평균에 섞인다.
    #    두 규칙 모두 같은 조건이다: 직전 거래일 규칙은 정의상 그렇고, 다음 거래일 규칙은
    #    목표일이 마지막 거래일보다 뒤면 잡을 거래일이 아예 없다
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
        f"휴장 규칙 {on_holiday.value}, 보유 분포 {frame[COL_HOLD_DAYS].value_counts().sort_index().to_dict()}"
    )

    return WeeklyExitSchedule(frame=frame, exit_weekday=exit_weekday, on_holiday=on_holiday)


def weekly_exit_returns(df: pd.DataFrame, schedule: WeeklyExitSchedule) -> pd.DataFrame:
    """청산 일정에 시세를 붙여 long-form 수익률을 낸다.

    구간 축(`COL_HORIZON`)에는 실제 보유 거래일 수가 아니라 **표지 하나**를 넣는다.
    보유일수를 넣으면 한 매매가 길이별 여러 칸으로 쪼개져 묶음 값이 나오지 않는다
    (`docs/spec/option_expiry.md` 결정 ㉑). 실제 보유일수는 별도 컬럼으로 남으므로
    분포는 그대로 보고할 수 있다.

    기준은 **종가**뿐이다. 이 매매의 정의가 "만기일 종가 매수 → 목표일 종가 매도" 이며,
    익일 시가 진입은 다른 매매다.

    Args:
        df: 날짜 오름차순 시세 (`data/loader.py` 가 검증해 돌려준 형태)
        schedule: `weekly_exit_schedule` 의 결과

    Returns:
        `RETURN_COLUMNS` 순서의 long-form DataFrame. 행 수는 **진입 수와 같다** —
        제외된 진입도 값만 비운 채 남는다. 입력은 변경하지 않는다

    Raises:
        ValueError: 시세가 비었거나 필수 컬럼이 없는 경우, 날짜가 오름차순이 아닌 경우,
            일정표의 날짜가 시세에 없는 경우
    """
    validate_market_frame(df, REQUIRED_MARKET_COLUMNS)

    if schedule.entry_count == 0:
        logger.debug("진입이 없습니다")
        return _empty_returns()

    closes = df.set_index(COL_DATE)[COL_CLOSE]
    frame = schedule.frame.copy()

    entry_close = frame[COL_DATE].map(closes)
    if entry_close.isna().any():
        missing = frame.loc[entry_close.isna(), COL_DATE]
        raise ValueError(f"진입일의 종가가 시세에 없습니다: {[day.date().isoformat() for day in missing]}")

    # 제외된 행은 청산일이 비어 있으므로 종가도 비어 있다. `map` 이 그대로 NaN 을 돌려준다
    exit_close = frame[COL_EXIT_DATE].map(closes)

    frame[COL_ENTRY_CLOSE] = entry_close
    frame[COL_EXIT_CLOSE] = exit_close
    frame[COL_BASIS] = ReturnBasis.CLOSE.value
    frame[COL_HORIZON] = HORIZON_NEXT_WEEK_EXIT
    frame[COL_FORWARD_RETURN] = exit_close / entry_close - 1.0

    valid = frame[COL_EXCLUDED_REASON] == REASON_NONE
    if not frame.loc[valid, COL_FORWARD_RETURN].notna().all():
        raise RuntimeError("내부 불변조건 위반: 제외되지 않은 진입의 수익률이 비어 있습니다")

    logger.debug(f"청산 수익률 계산 완료: 진입 {len(frame):,}건, 유효 {int(valid.sum()):,}건")

    return frame[RETURN_COLUMNS]


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
    empty[COL_BASIS] = pd.Series(dtype="object")
    empty[COL_HORIZON] = pd.Series(dtype="int64")
    empty[COL_FORWARD_RETURN] = pd.Series(dtype="float64")

    return empty[RETURN_COLUMNS]


__all__ = ["HolidayExit", "WeeklyExitSchedule", "weekly_exit_returns", "weekly_exit_schedule"]
