"""NAV 대비 프리미엄/디스카운트

사양서 §16.4 의 첫째 항목이다. **시장가가 순자산가치에서 얼마나 벗어나는가**를 재며,
이것이 크면 "환전의 대체재"라는 전제 자체가 흔들린다 — 사는 값과 실제 가치가 다르기 때문이다.

**연도별로 낸다.** 사양서가 "특히 2024~2025 급등 구간"을 지목했듯 프리미엄은 국면에 따라 달라지고,
전 기간 평균은 그 차이를 지운다.
"""

from dataclasses import dataclass

import pandas as pd

from verify_lab.studies.usdkrw_equivalence.constants import (
    COL_PREMIUM_ABS_MEAN,
    COL_PREMIUM_MAX,
    COL_PREMIUM_MEAN,
    COL_PREMIUM_MIN,
    COL_TRADING_DAYS,
    COL_YEAR,
)

# 프리미엄 계산 중간값의 컬럼. 집계 전에만 쓴다
COL_PREMIUM = "Premium"


@dataclass(frozen=True)
class PremiumResult:
    """연도별 프리미엄 통계

    Attributes:
        frame: 연도 · 거래일 수 · 평균 · 절대값 평균 · 최대 · 최소 (전부 비율)
        overall_abs_mean: 전 기간 절대값 평균 (비율)
    """

    frame: pd.DataFrame
    overall_abs_mean: float


def annual_premium(
    dates: pd.Series | pd.DatetimeIndex,
    price: pd.Series,
    nav: pd.Series,
) -> PremiumResult:
    """연도별 프리미엄/디스카운트 통계를 낸다.

    프리미엄은 `시장가 ÷ NAV − 1` 이다. 양수면 순자산가치보다 비싸게 거래된 것이다.

    Args:
        dates: 날짜
        price: 시장 종가
        nav: 같은 날의 NAV

    Returns:
        연도별 표와 전 기간 절대값 평균

    Raises:
        ValueError: 길이가 다르거나, 비었거나, 결측이 있거나, NAV 에 0 이하가 있는 경우
    """
    if not len(dates) == len(price) == len(nav):
        raise ValueError(f"세 계열의 길이가 다릅니다: {len(dates)} / {len(price)} / {len(nav)}")

    if len(dates) == 0:
        raise ValueError("프리미엄을 낼 표본이 없습니다")

    if price.isna().any() or nav.isna().any():
        raise ValueError(f"결측이 있습니다 - 종가 {int(price.isna().sum())}건, NAV {int(nav.isna().sum())}건")

    if (nav <= 0).any():
        raise ValueError(f"NAV 에 0 이하 값이 있습니다: {int((nav <= 0).sum())}건")

    frame = pd.DataFrame(
        {
            COL_YEAR: pd.DatetimeIndex(pd.to_datetime(dates)).year.to_numpy(),
            COL_PREMIUM: (price.to_numpy(dtype=float) / nav.to_numpy(dtype=float)) - 1.0,
        }
    )

    grouped = frame.groupby(COL_YEAR, sort=True)[COL_PREMIUM]
    summary = pd.DataFrame(
        {
            COL_TRADING_DAYS: grouped.size(),
            COL_PREMIUM_MEAN: grouped.mean(),
            COL_PREMIUM_ABS_MEAN: grouped.apply(lambda values: values.abs().mean()),
            COL_PREMIUM_MAX: grouped.max(),
            COL_PREMIUM_MIN: grouped.min(),
        }
    ).reset_index()

    return PremiumResult(frame=summary, overall_abs_mean=float(frame[COL_PREMIUM].abs().mean()))
