"""동적 범위 — 격자 중 어느 레벨을 켤지 정한다

`범위 = 과거 12N개 월평균 종가의 min ~ max` 이며 **당월은 보지 않는다**(사양서 §4.1).
격자(`lattice.py`)가 가격표를 영구 고정하고, 이 계층은 그중 **활성 구간만** 정한다.

**월평균을 쓰는 이유**는 일종가 min/max 로 잡으면 하루짜리 스파이크가 N년간 경계를 지배하고,
그 스파이크가 창에서 빠질 때 경계가 급격히 움직이기 때문이다. 대가는 **월평균이 정의상
월중 저점보다 높아 급락 시 1~4% 아래를 못 사는 것**이며, 이것은 버그가 아니라 측정 대상이다.

**이 계층이 틀리는 방식은 창이 한 칸 밀리는 것**이다. 당월이 섞이면 그날 시세로 그날 범위를
정하는 룩어헤드가 되고, 워밍업이 모자란 채로 돌면 범위가 좁아져 슬롯 하나가 거대해진다.
둘 다 예외가 나지 않으므로 **개수를 세어 즉시 실패**하고 look-ahead 감시 테스트를 건다.
"""

import math
from dataclasses import dataclass

import pandas as pd

from verify_lab.common_constants import COL_DATE, COL_VALUE
from verify_lab.data.loader import validate_market_frame
from verify_lab.strategy.grid.constants import (
    COL_RANGE_HIGH,
    COL_RANGE_LOW,
    COL_RANGE_WIDENED,
    COL_RAW_RANGE_HIGH,
    COL_RAW_RANGE_LOW,
    COL_REBALANCED,
    MONTHS_PER_YEAR,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 범위표의 컬럼 순서
DAILY_RANGE_COLUMNS = [
    COL_DATE,
    COL_RANGE_LOW,
    COL_RANGE_HIGH,
    COL_RAW_RANGE_LOW,
    COL_RAW_RANGE_HIGH,
    COL_RANGE_WIDENED,
    COL_REBALANCED,
]

# 월 단위 기간의 빈도 문자열
MONTH_FREQ = "M"


@dataclass(frozen=True)
class RangeResult:
    """한 번의 재조정으로 확정된 범위

    최소폭 강제 **이전**의 값을 함께 담는다. 강제가 결과에 얼마나 관여했는지는
    이 둘의 차이로만 알 수 있고, 강제는 원달러 변동폭에 대한 사전 지식이라
    관여분을 모르면 나중에 해석할 수 없다.

    Attributes:
        low: 확정된 범위 하단
        high: 확정된 범위 상단
        raw_low: 최소폭 강제 이전의 하단 (창의 월평균 최솟값)
        raw_high: 최소폭 강제 이전의 상단 (창의 월평균 최댓값)
        widened: 최소폭 강제가 발동했는지 여부
        month_count: 참조한 월 수. 언제나 12N 이다
        first_month: 참조 창의 첫 달
        last_month: 참조 창의 마지막 달 (재조정 달의 직전 달)
    """

    low: float
    high: float
    raw_low: float
    raw_high: float
    widened: bool
    month_count: int
    first_month: pd.Period
    last_month: pd.Period


def monthly_average_close(series: pd.DataFrame) -> pd.Series:
    """일별 종가 시계열을 월평균으로 접는다.

    **그 달에 존재하는 거래일의 단순 평균**이며 며칠짜리 달인지 따지지 않는다.
    "며칠이면 한 달인가"는 사양서에 없는 새 파라미터다.

    Args:
        series: 일별 단일 값 시계열 (`load_series_csv` 가 돌려준 형태)

    Returns:
        월 오름차순 `Period[M]` 인덱스의 월평균

    Raises:
        ValueError: 비었거나, 필요한 컬럼이 없거나, 날짜가 오름차순이 아닌 경우
    """
    validate_market_frame(series, [COL_DATE, COL_VALUE])

    frame = series[[COL_DATE, COL_VALUE]].copy()
    months = frame[COL_DATE].dt.to_period(MONTH_FREQ)

    return frame[COL_VALUE].groupby(months).mean().sort_index()


def resolve_range(
    monthly: pd.Series,
    target_month: pd.Period,
    *,
    lookback_years: int,
    min_range_width: float,
) -> RangeResult:
    """한 달의 재조정 범위를 확정한다.

    참조 창은 **재조정 달의 직전 달로 끝나는 12N개월**이다. 당월을 넣으면
    그날 시세로 그날 범위를 정하는 룩어헤드가 된다.

    창이 모자라면 **있는 만큼으로 대체하지 않고 즉시 실패한다.** 짧은 창은 범위를 좁혀
    슬롯 하나를 거대하게 만드는데, 그 사고는 조용히 지나간다.

    Args:
        monthly: 월 오름차순 `Period[M]` 인덱스의 월평균
        target_month: 재조정이 일어나는 달
        lookback_years: 룩백 N (년). 참조 개월 수는 12N 이다
        min_range_width: 최소 범위폭 (비율, 0.20 = 20%)

    Returns:
        확정된 범위와 강제 발동 여부

    Raises:
        ValueError: 룩백·최소폭이 유효하지 않거나, 참조 창이 12N개월에 못 미치는 경우
    """
    if lookback_years < 1:
        raise ValueError(f"룩백은 1년 이상이어야 합니다: {lookback_years}")

    if min_range_width <= 0:
        raise ValueError(f"최소 범위폭은 양수여야 합니다: {min_range_width}")

    required = lookback_years * MONTHS_PER_YEAR
    last_month = target_month - 1
    first_month = last_month - (required - 1)

    # 1. 창을 잘라낸다. 당월은 `last_month` 가 직전 달이라 구조적으로 빠진다
    window = monthly.loc[(monthly.index >= first_month) & (monthly.index <= last_month)]

    if len(window) != required:
        raise ValueError(
            f"월평균이 모자랍니다 - 필요 {required}개월({first_month} ~ {last_month}), " f"실제 {len(window)}개월, 재조정 대상 {target_month}"
        )

    raw_low = float(window.min())
    raw_high = float(window.max())

    if raw_low <= 0:
        raise ValueError(f"월평균에 0 이하 값이 있습니다: {raw_low} ({first_month} ~ {last_month})")

    low, high, widened = _apply_min_width(raw_low, raw_high, min_range_width=min_range_width)

    return RangeResult(
        low=low,
        high=high,
        raw_low=raw_low,
        raw_high=raw_high,
        widened=widened,
        month_count=required,
        first_month=first_month,
        last_month=last_month,
    )


def build_daily_ranges(
    series: pd.DataFrame,
    *,
    start_date: pd.Timestamp,
    lookback_years: int,
    min_range_width: float,
) -> pd.DataFrame:
    """거래일 한 줄씩 범위가 실린 표를 만든다.

    재조정은 **매월 첫 거래일**에 일어나고 사이 날은 직전 범위를 그대로 쓴다.
    **백테스트 첫 거래일은 언제나 재조정일**이다 — 시작일이 월 중간이면 첫날에 범위가 없어
    그 달 내내 매수가 불가능해진다 (사양서 §11.4 "첫날 상태: 완성된 범위와 격자 보유").

    **전체 시세를 넘기고 결과 행만 자른다.** 시세를 먼저 잘라 넘기면 월평균 창이 그 지점부터
    다시 쌓여 워밍업이 무너지는데, 결과는 달라지고 예외는 나지 않는다.

    Args:
        series: 일별 단일 값 시계열 **전 기간** (`load_series_csv` 가 돌려준 형태)
        start_date: 매매 시작일. 이 날짜 이상인 거래일만 결과에 담는다
        lookback_years: 룩백 N (년)
        min_range_width: 최소 범위폭 (비율)

    Returns:
        거래일 오름차순 표. 컬럼 구성은 `DAILY_RANGE_COLUMNS`

    Raises:
        ValueError: 시작일 이후 거래일이 없거나, 워밍업이 모자라거나,
            파라미터가 유효하지 않은 경우
    """
    monthly = monthly_average_close(series)

    trading_dates = series.loc[series[COL_DATE] >= start_date, COL_DATE].reset_index(drop=True)
    if trading_dates.empty:
        raise ValueError(f"매매 시작일 이후 거래일이 없습니다: {start_date.date()} (시세 마지막 {series[COL_DATE].max().date()})")

    months = trading_dates.dt.to_period(MONTH_FREQ)

    # 1. 재조정일 판정. 달이 바뀌는 첫 행이며, 첫 거래일도 언제나 재조정일이다.
    #    달력 1일로 잡으면 그날이 휴일일 때 재조정이 통째로 사라진다
    rebalanced = months != months.shift(1)

    # 2. 재조정 달마다 한 번씩만 범위를 계산한다
    resolved = {
        month: resolve_range(monthly, month, lookback_years=lookback_years, min_range_width=min_range_width)
        for month in months[rebalanced]
    }

    frame = pd.DataFrame(
        {
            COL_DATE: trading_dates,
            COL_RANGE_LOW: [resolved[month].low for month in months],
            COL_RANGE_HIGH: [resolved[month].high for month in months],
            COL_RAW_RANGE_LOW: [resolved[month].raw_low for month in months],
            COL_RAW_RANGE_HIGH: [resolved[month].raw_high for month in months],
            COL_RANGE_WIDENED: [resolved[month].widened for month in months],
            COL_REBALANCED: rebalanced,
        }
    )

    widened_count = int(frame.loc[frame[COL_REBALANCED], COL_RANGE_WIDENED].sum())
    logger.debug(f"범위표 생성: {len(frame):,}거래일, 재조정 {int(rebalanced.sum()):,}회, 최소폭 강제 {widened_count:,}회")

    return frame[DAILY_RANGE_COLUMNS]


def _apply_min_width(raw_low: float, raw_high: float, *, min_range_width: float) -> tuple[float, float, bool]:
    """최소 범위폭을 강제한다.

    기하평균을 중심으로 **대칭 확장**한다. 등비 격자 위의 범위라 산술평균이 아니라
    기하평균이 중심이다.

    **판정은 곱셈으로 한다.** 사양서 §4.2 의 `상단/하단 − 1 < 폭` 을 문자 그대로 쓰면
    폭이 정확히 임계값일 때 오발동한다 — `1200/1000 − 1` 이 0.19999999999999996 이라
    0.20 보다 작다고 판정된다. 사양서 검사 범위 4개 중 15%·20% 두 개에서 실제로 발생하며,
    값은 그대로인 채 「강제 발동 횟수」만 늘어 지표가 오염된다.

    Args:
        raw_low: 창의 월평균 최솟값
        raw_high: 창의 월평균 최댓값
        min_range_width: 최소 범위폭 (비율)

    Returns:
        `(하단, 상단, 강제 발동 여부)`
    """
    if raw_high >= raw_low * (1.0 + min_range_width):
        return raw_low, raw_high, False

    middle = math.sqrt(raw_low * raw_high)
    half = math.sqrt(1.0 + min_range_width)

    return middle / half, middle * half, True
