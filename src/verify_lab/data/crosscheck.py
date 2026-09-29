"""두 소스의 같은 날 종가 대조 (크로스체크)

주 계열(거래소 한 곳의 OHLCV)과 보완 계열(다른 소스의 일별 단일 값)을 같은 날끼리 맞대어
**얼마나 벌어지는지를 보고한다.** 반감기_사이클이 Bitstamp 일봉과 Coin Metrics `PriceUSD` 로 쓴다
(2026-09-26 사용자 지시 — 「데이터 로드 단계에서 두 소스를 서로 비교해 크로스체크한다」).

**값을 바꾸지 않는다**(2026-09-29 사용자 결정 — `docs/검증/반감기_사이클/설계.md` 결정 ②).
그래서 허용폭은 **목록의 범위만 정할 뿐 어떤 값도 고르지 않는다.** 보고하는 것은 다섯이다.

1. 겹치는 날마다의 차이율 `주 ÷ 보완 − 1`
2. 그 절대값이 허용폭을 **넘는**(`>`) 날 목록
3. 연도별 요약 — 겹치는 날 · 중앙 절대차 · 95분위(선형 보간) · 최대와 그 날 · 허용폭 초과 일수
4. 한쪽에만 있는 날의 수 (양방향)
5. 주 계열에서 거래량이 0 인 날 — 그날 가격은 체결가가 아니라 전일값 이월이다

두 소스의 날짜가 **같은 하루**를 가리킨다는 전제 위에 서 있다 — 비트코인은 둘 다 UTC 하루다
(`docs/검증/반감기_사이클/설계.md` 「데이터 실측 기록」). 하루 밀린 두 계열을 넣으면 예외 없이 차이만 커진다.
"""

import math
from dataclasses import dataclass
from typing import Final

import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_VALUE, COL_VOLUME
from verify_lab.data.loader import validate_market_frame

# 목록에 올릴 차이율의 절대값 경계 (비율, 0.05 = 5%). 사전조사가 처음 잰 기준과 같다
# (`docs/검증/반감기_사이클/사전조사.md` §4.4). **값을 바꾸지 않으므로 이 수가 측정을 움직이지 않는다**
DEFAULT_TOLERANCE: Final = 0.05

# 95분위의 분위 값. 연도별 요약의 한 칸이다
_P95: Final = 0.95

# 겹친 날 표의 컬럼 (내부 토큰)
COL_PRIMARY: Final = "Primary"
COL_SECONDARY: Final = "Secondary"
COL_DIFF_RATE: Final = "DiffRate"

# 연도별 요약의 컬럼 (내부 토큰)
COL_YEAR: Final = "Year"
COL_OVERLAP_DAYS: Final = "OverlapDays"
COL_MEDIAN_ABS_DIFF: Final = "MedianAbsDiff"
COL_P95_ABS_DIFF: Final = "P95AbsDiff"
COL_MAX_ABS_DIFF: Final = "MaxAbsDiff"
COL_MAX_DIFF_DATE: Final = "MaxDiffDate"
COL_OVER_TOLERANCE_DAYS: Final = "OverToleranceDays"


@dataclass(frozen=True)
class CrosscheckResult:
    """크로스체크 결과

    Attributes:
        tolerance: 목록에 쓴 허용폭 (비율)
        overlap: 겹치는 날마다 한 행 — 날짜 · 주 · 보완 · 차이율 (비율)
        over_tolerance: `overlap` 중 차이율 절대값이 허용폭을 넘는 행
        yearly: 연도마다 한 행 — 겹치는 날 · 중앙 · 95분위 · 최대 절대차(비율) · 최대인 날 · 허용폭 초과 일수
        primary_only_count: 주 계열에만 있는 날 수
        secondary_only_count: 보완 계열에만 있는 날 수
        zero_volume: 주 계열에서 거래량이 0 인 날 — 날짜 · 종가
    """

    tolerance: float
    overlap: pd.DataFrame
    over_tolerance: pd.DataFrame
    yearly: pd.DataFrame
    primary_only_count: int
    secondary_only_count: int
    zero_volume: pd.DataFrame


def _yearly_summary(overlap: pd.DataFrame, tolerance: float) -> pd.DataFrame:
    """겹친 날 표를 달력 연도로 묶어 요약한다."""
    rows: list[dict[str, object]] = []
    for year, group in overlap.groupby(overlap[COL_DATE].dt.year, sort=True):
        abs_diff = group[COL_DIFF_RATE].abs()
        max_position = abs_diff.to_numpy().argmax()
        rows.append(
            {
                COL_YEAR: int(year),
                COL_OVERLAP_DAYS: len(group),
                COL_MEDIAN_ABS_DIFF: float(abs_diff.median()),
                COL_P95_ABS_DIFF: float(abs_diff.quantile(_P95)),
                COL_MAX_ABS_DIFF: float(abs_diff.iloc[max_position]),
                COL_MAX_DIFF_DATE: group[COL_DATE].iloc[max_position],
                COL_OVER_TOLERANCE_DAYS: int((abs_diff > tolerance).sum()),
            }
        )

    return pd.DataFrame(rows)


def crosscheck_closes(
    primary: pd.DataFrame, secondary: pd.DataFrame, *, tolerance: float = DEFAULT_TOLERANCE
) -> CrosscheckResult:
    """주 계열 종가와 보완 계열 값을 같은 날끼리 대조한다. 입력은 바꾸지 않는다.

    Args:
        primary: 주 계열. 로더를 지난 시세 프레임 — 날짜(오름차순) · 종가 · 거래량
        secondary: 보완 계열. 로더를 지난 단일 값 프레임 — 날짜(오름차순) · 값
        tolerance: 목록에 올릴 차이율 절대값의 경계 (비율, 0.05 = 5%). 이 값을 **넘는** 날만 오른다

    Returns:
        크로스체크 결과

    Raises:
        ValueError: 허용폭이 유한한 양수가 아니거나, 필요한 컬럼이 없거나, 날짜가 오름차순이 아니거나,
            겹치는 날이 하나도 없는 경우
    """
    # NaN · 무한대면 어떤 날도 목록에 오르지 않는다 — `<= 0` 만 보면 NaN 이 빠져나간다
    if not (math.isfinite(tolerance) and tolerance > 0):
        raise ValueError(f"허용폭은 유한한 양수여야 합니다: {tolerance}")

    validate_market_frame(primary, [COL_DATE, COL_CLOSE, COL_VOLUME])
    validate_market_frame(secondary, [COL_DATE, COL_VALUE])

    left = primary[[COL_DATE, COL_CLOSE]].rename(columns={COL_CLOSE: COL_PRIMARY})
    right = secondary[[COL_DATE, COL_VALUE]].rename(columns={COL_VALUE: COL_SECONDARY})
    overlap = left.merge(right, on=COL_DATE, how="inner")

    if overlap.empty:
        raise ValueError("두 계열에 겹치는 날이 하나도 없어 대조할 수 없습니다")

    overlap[COL_DIFF_RATE] = overlap[COL_PRIMARY] / overlap[COL_SECONDARY] - 1
    over_tolerance = overlap.loc[overlap[COL_DIFF_RATE].abs() > tolerance].reset_index(drop=True)

    primary_days = set(primary[COL_DATE])
    secondary_days = set(secondary[COL_DATE])

    zero_volume = primary.loc[primary[COL_VOLUME] == 0, [COL_DATE, COL_CLOSE]].reset_index(drop=True)

    return CrosscheckResult(
        tolerance=tolerance,
        overlap=overlap,
        over_tolerance=over_tolerance,
        yearly=_yearly_summary(overlap, tolerance),
        primary_only_count=len(primary_days - secondary_days),
        secondary_only_count=len(secondary_days - primary_days),
        zero_volume=zero_volume,
    )


__all__ = [
    "COL_DIFF_RATE",
    "COL_MAX_ABS_DIFF",
    "COL_MAX_DIFF_DATE",
    "COL_MEDIAN_ABS_DIFF",
    "COL_OVER_TOLERANCE_DAYS",
    "COL_OVERLAP_DAYS",
    "COL_P95_ABS_DIFF",
    "COL_PRIMARY",
    "COL_SECONDARY",
    "COL_YEAR",
    "DEFAULT_TOLERANCE",
    "CrosscheckResult",
    "crosscheck_closes",
]
