"""달력으로 정해지는 진입일 — 만기 규칙과 달력일 규칙

`forward_return.py` 는 **고정 거래일 구간**만 잰다. 진입이 달력으로 정해지는 매매법은
그 틀에 들어가지 않으므로 진입일을 따로 만든다.

**두 규칙이 있다.**

| 규칙 | 진입일 | 쓰는 매매법 |
| --- | --- | --- |
| 만기 달력 | 그 달의 N번째 지정 요일 (미국 셋째 금요일 · 한국 둘째 목요일) | 옵션 만기일 · 만기_말일 |
| 달력일 | 그 달의 지정 달력일 (20일) | 월말 진입 · 만기_말일 |

**둘 다 규칙일이 휴장이면 직전 거래일로 앞당긴다.** 달력상 하루 전이 아니다 — 연휴가 걸리면
직전 거래일이 일주일 넘게 떨어진 달이 실제로 있다. 그래서 앞당김 간격은 거래일 수가 아니라
**달력일 수**로 기록한다. 거래일 수로는 언제나 1 이라 정보가 없다.

**앞당김은 그 달 안에서만 일어난다.** 전월로 넘어가면 「그 달 20일에 산다」가 아닌 다른 매매가 된다.

**공통 계층이 소유한다.** 매매법끼리는 import 할 수 없으므로(`tests/test_layer_contracts.py`)
세 매매법이 같은 달력을 쓰려면 여기 있어야 하고, 복제하면 같은 달력이 조용히 갈라진다
(패키지 절대 원칙 「판정식 단일화」).

거래소 휴장일은 사전에 공표되므로 이 판정은 미래를 참조하지 않는다. 다만 구현이 판정일 이후의
데이터에 의존하지 않는지는 look-ahead 감시 테스트로 고정한다.
"""

from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.measure.constants import (
    COL_ADVANCED_DAYS,
    COL_EXCLUDED_REASON,
    COL_EXPIRY_DATE,
    COL_EXPIRY_MONTH,
    COL_MONTH,
    COL_RULE_DATE,
    COL_TARGET_DAY,
    REASON_NO_ENTRY_DAY,
    REASON_NONE,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 만기일 표에서 만기월을 나타내는 표기. 월 단위 문자열로 두어 CSV 로 나가도 뜻이 유지된다
EXPIRY_MONTH_FORMAT = "%Y-%m"

# 만기일 표의 컬럼과 dtype. 빈 결과에서도 같은 스키마를 유지해 호출 측이 분기하지 않게 한다
EXPIRY_FRAME_DTYPES = {
    COL_EXPIRY_MONTH: "object",
    COL_RULE_DATE: "datetime64[ns]",
    COL_EXPIRY_DATE: "datetime64[ns]",
    COL_ADVANCED_DAYS: "int64",
}

# 진입일 표의 컬럼과 dtype. 빈 결과에서도 같은 스키마를 유지한다
ENTRY_DTYPES = {
    COL_MONTH: "datetime64[ns]",
    COL_TARGET_DAY: "int64",
    COL_DATE: "datetime64[ns]",
    COL_EXCLUDED_REASON: "object",
}

# 달력일의 허용 범위. 32 이상은 어느 달에도 없고 0 이하는 뜻이 없다
MIN_CALENDAR_DAY = 1
MAX_CALENDAR_DAY = 31


@dataclass(frozen=True)
class ExpiryRule:
    """월물 만기일을 정하는 달력 규칙

    만기일은 시세와 무관한 **달력 규칙**이다. 규칙일이 휴장이면 직전 거래일까지 앞당겨지며,
    그 판정에 필요한 거래일 목록은 시세 파일의 날짜 인덱스에서 온다.

    **규칙의 «값»은 이 계층이 갖지 않는다.** 어느 시장이 어느 요일을 쓰는지는 그 매매법의
    파라미터라 `studies/<매매법>/constants.py` 가 정한다 — 공통 계층이 값을 들면 그것이
    모든 매매법의 기본값이 된다.

    Attributes:
        label: 표시 이름
        weekday: 요일 (월=0 ~ 일=6). `pandas` 의 `dayofweek` 와 같은 기준이다
        ordinal: 그 달에서 몇 번째 해당 요일인가 (1부터)
    """

    label: str
    weekday: int
    ordinal: int


def nth_weekday_of_month(year: int, month: int, weekday: int, ordinal: int) -> pd.Timestamp:
    """그 달의 N번째 지정 요일을 돌려준다.

    Args:
        year: 연도
        month: 월 (1~12)
        weekday: 요일 (월=0 ~ 일=6)
        ordinal: 몇 번째인가 (1부터)

    Returns:
        해당 날짜

    Raises:
        ValueError: 요일·순번이 범위를 벗어났거나, 그 달에 해당 순번이 없는 경우
    """
    if not 0 <= weekday <= 6:
        raise ValueError(f"요일은 0(월)~6(일) 이어야 합니다: {weekday}")
    if ordinal < 1:
        raise ValueError(f"순번은 1 이상이어야 합니다: {ordinal}")

    first = pd.Timestamp(year=year, month=month, day=1)
    days_ahead = (weekday - first.dayofweek) % 7 + 7 * (ordinal - 1)
    target = first + timedelta(days=days_ahead)

    # 5번째 요일처럼 그 달에 없는 순번을 요구하면 다음 달로 넘어간다. 쓰이는 것은 2~3번째뿐이라
    # 도달하지 않지만, 넘어간 값을 그대로 돌려주면 만기월과 만기일의 달이 어긋난 채 흘러간다
    if target.month != month:
        raise ValueError(f"{year}-{month:02d} 에는 {ordinal}번째 요일 {weekday} 가 없습니다")

    return target


def validate_trading_days(trading_days: pd.DatetimeIndex, *, purpose: str) -> None:
    """거래일 목록이 달력 일정 산출의 전제를 만족하는지 검사한다.

    Args:
        trading_days: 검사할 거래일 목록
        purpose: 무엇을 산출하려던 것인지. 예외 메시지에 실린다

    Raises:
        ValueError: 비었거나 정렬·중복 조건을 어긴 경우
    """
    if len(trading_days) == 0:
        raise ValueError(f"거래일 목록이 비어 있어 {purpose}을 산출할 수 없습니다")
    if not trading_days.is_monotonic_increasing:
        raise ValueError("거래일 목록이 오름차순으로 정렬되어 있어야 합니다")
    if trading_days.has_duplicates:
        raise ValueError("거래일 목록에 중복된 날짜가 있습니다")


def monthly_expiry_dates(trading_days: pd.DatetimeIndex, rule: ExpiryRule) -> pd.DataFrame:
    """거래일 목록의 전 구간에 대해 월물 만기일을 산출한다.

    규칙일이 거래일이면 그날이 만기일이고, 휴장이면 **직전 거래일**이 만기일이다.
    직전 거래일이 그 달을 벗어나면 그 달은 제외한다 — 데이터가 그 달 중간부터 시작해
    앞 구간이 없는 경우이며, 값을 지어내지 않는다.

    Args:
        trading_days: 거래일 목록. 오름차순 정렬된 중복 없는 인덱스여야 한다
        rule: 만기일 달력 규칙

    Returns:
        만기월·규칙일·만기일·앞당김 달력일수를 담은 DataFrame (만기일 오름차순)

    Raises:
        ValueError: 거래일 목록이 비었거나 정렬·중복 조건을 어긴 경우
    """
    validate_trading_days(trading_days, purpose="만기일")

    first_day = trading_days[0]
    last_day = trading_days[-1]

    rows: list[dict[str, object]] = []
    for period in pd.period_range(first_day, last_day, freq="M"):
        rule_date = nth_weekday_of_month(period.year, period.month, rule.weekday, rule.ordinal)

        # 1. 규칙일이 데이터 범위를 벗어나면 만기일을 확정할 수 없다
        if rule_date < first_day or rule_date > last_day:
            continue

        # 2. 규칙일보다 큰 첫 거래일의 위치. 규칙일 자체가 거래일이면 그 위치가 나온다
        position = int(trading_days.searchsorted(rule_date, side="left"))

        if position < len(trading_days) and trading_days[position] == rule_date:
            expiry_date = rule_date
        elif position > 0:
            # 3. 휴장이면 직전 거래일이 만기일이다
            expiry_date = trading_days[position - 1]
        else:
            continue

        # 4. 앞당긴 결과가 그 달을 벗어나면 그 달의 만기일을 확정할 수 없다
        if (expiry_date.year, expiry_date.month) != (period.year, period.month):
            continue

        rows.append(
            {
                COL_EXPIRY_MONTH: period.strftime(EXPIRY_MONTH_FORMAT),
                COL_RULE_DATE: rule_date,
                COL_EXPIRY_DATE: expiry_date,
                COL_ADVANCED_DAYS: int((rule_date - expiry_date).days),
            }
        )

    if not rows:
        return pd.DataFrame({column: pd.Series(dtype=dtype) for column, dtype in EXPIRY_FRAME_DTYPES.items()})

    return pd.DataFrame(rows).sort_values(COL_EXPIRY_DATE, ignore_index=True)


def month_entry_dates(trading_days: pd.DatetimeIndex, *, calendar_day: int) -> pd.DataFrame:
    """달마다 목표 달력일의 진입일을 정한다.

    목표일이 거래일이면 그날이고, 휴장이면 **그 달 안에서** 직전 거래일로 앞당긴다.

    **데이터의 마지막 달은 아예 다루지 않는다.** 그 달의 「말일」은 실제 월말이 아니라
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
    validate_trading_days(trading_days, purpose="진입일")

    days = pd.DataFrame({COL_DATE: trading_days})
    days[COL_MONTH] = days[COL_DATE].dt.to_period("M").dt.to_timestamp()

    # 1. 데이터의 마지막 달을 통째로 뺀다. 그 달이 끝났는지는 데이터만으로 알 수 없으므로
    #    조건부로 넣지 않는다 — 정의가 깨진 표본을 넣는 것보다 매월 최대 1건을 잃는 쪽이 낫다
    last_month = days[COL_MONTH].iloc[-1]
    days = days[days[COL_MONTH] < last_month]

    if days.empty:
        logger.debug(f"데이터가 한 달치뿐이라 진입일이 없습니다 (달력일 {calendar_day})")
        return empty_entries()

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


def every_day_entries(trading_days: pd.DatetimeIndex, *, calendar_day: int) -> pd.DataFrame:
    """**전 거래일**을 진입일로 삼은 표를 만든다 — 기준선 「그 달 아무 날 진입」용이다.

    신호와 **같은 함수**로 청산일을 정하므로 기준선의 보유 길이 분포가 신호와 같은 달력
    구조에서 나온다. 기준선을 따로 구현하면 두 계산이 조용히 갈라진다.

    **데이터의 마지막 달은 신호와 같은 이유로 뺀다.** 기준선만 그 달을 포함하면 비교 구간이
    어긋난다.

    Args:
        trading_days: 거래일 목록
        calendar_day: 격자 축을 맞추기 위한 표지. 기준선 자신은 달력일을 쓰지 않지만
            신호와 같은 칸으로 묶여야 집계가 나란히 선다

    Returns:
        `ENTRY_DTYPES` 구성의 DataFrame. **거래일마다 한 행**이다

    Raises:
        ValueError: 거래일 목록이 비었거나 정렬·중복 조건을 어긴 경우
    """
    validate_trading_days(trading_days, purpose="기준선 진입일")

    days = pd.DataFrame({COL_DATE: trading_days})
    days[COL_MONTH] = days[COL_DATE].dt.to_period("M").dt.to_timestamp()

    last_month = days[COL_MONTH].iloc[-1]
    days = days[days[COL_MONTH] < last_month].reset_index(drop=True)

    days[COL_TARGET_DAY] = calendar_day
    days[COL_EXCLUDED_REASON] = REASON_NONE

    return days[list(ENTRY_DTYPES)]


def empty_entries() -> pd.DataFrame:
    """진입일이 하나도 없을 때 돌려줄 빈 표를 만든다.

    Returns:
        진입일 표와 같은 스키마의 빈 DataFrame
    """
    return pd.DataFrame({column: pd.Series(dtype=dtype) for column, dtype in ENTRY_DTYPES.items()})


__all__ = [
    "ENTRY_DTYPES",
    "EXPIRY_FRAME_DTYPES",
    "EXPIRY_MONTH_FORMAT",
    "ExpiryRule",
    "empty_entries",
    "every_day_entries",
    "month_entry_dates",
    "monthly_expiry_dates",
    "nth_weekday_of_month",
    "validate_trading_days",
]
