"""회귀 통계와 연도별 괴리

사양서 §16.2·§16.3 의 판정이 전부 이 값들에 걸려 있다.

**연도별 괴리가 가장 중요한 지표다.** 사양서가 "상관계수가 0.99여도 연도별 괴리가 들쭉날쭉하면
대체재로 쓸 수 없다 — 괴리가 크지만 일정하면 괜찮고, 작지만 불규칙한 것이 훨씬 나쁘다"고 적었다.
그리드는 슬롯 하나를 수개월 들고 있으므로, 그 기간에 예측 불가능한 괴리가 붙으면
전략이 아니라 도박이 된다.

**결측을 조용히 버리지 않는다.** 회귀에서 표본이 소리 없이 줄면 상관과 알파가 함께 움직여
어느 쪽이 원인인지 알 수 없게 된다.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from verify_lab.studies.usdkrw_equivalence.constants import (
    COL_ACTUAL_CUMULATIVE,
    COL_DRIFT,
    COL_THEORETICAL_CUMULATIVE,
    COL_TRADING_DAYS,
    COL_YEAR,
    TRADING_DAYS_PER_YEAR,
)

# 양끝 해를 빼고도 폭을 낼 수 있는 최소 연도 수
MIN_YEARS_FOR_EDGE_SPREAD = 3


@dataclass(frozen=True)
class RegressionResult:
    """단순 회귀 결과

    Attributes:
        sample_count: 표본 수
        correlation: 두 계열의 상관계수
        beta: 회귀 기울기
        alpha_daily: 절편 (일간, 비율)
        alpha_annual: 절편의 연환산 (거래일 250배, 비율)
        r_squared: 결정계수
        tracking_error: 잔차 표준편차 × √250 (비율)
    """

    sample_count: int
    correlation: float
    beta: float
    alpha_daily: float
    alpha_annual: float
    r_squared: float
    tracking_error: float


@dataclass(frozen=True)
class AnnualDriftResult:
    """연도별 괴리

    Attributes:
        frame: 연도 · 거래일 수 · 실제 누적 · 이론 누적 · 괴리 (전부 비율)
        spread: 연도별 괴리의 최대 − 최소
        spread_excluding_edges: 첫 해와 마지막 해를 뺀 폭. 연도가 셋 미만이면 `None`
    """

    frame: pd.DataFrame
    spread: float
    spread_excluding_edges: float | None


def fit_regression(x: pd.Series, y: pd.Series) -> RegressionResult:
    """`y = alpha + beta * x` 를 최소제곱으로 맞춘다.

    Args:
        x: 설명변수 (일간수익률, 비율)
        y: 종속변수 (일간수익률, 비율)

    Returns:
        회귀 결과

    Raises:
        ValueError: 길이가 다르거나, 표본이 두 개 미만이거나, 결측이 있거나,
            설명변수에 변동이 없는 경우
    """
    if len(x) != len(y):
        raise ValueError(f"두 계열의 길이가 다릅니다: {len(x)} vs {len(y)}")

    if len(x) < 2:
        raise ValueError(f"회귀에는 표본이 두 개 이상 필요합니다: {len(x)}개")

    if x.isna().any() or y.isna().any():
        raise ValueError(f"결측이 있습니다 - 설명변수 {int(x.isna().sum())}건, 종속변수 {int(y.isna().sum())}건")

    x_values = x.to_numpy(dtype=float)
    y_values = y.to_numpy(dtype=float)

    variance = float(np.var(x_values, ddof=1))
    if variance == 0:
        raise ValueError("설명변수에 변동이 없습니다 — 기울기를 정의할 수 없습니다")

    # 단순 회귀의 닫힌 해. `polyfit` 대신 쓰는 이유는 산식이 그대로 보이기 때문이다
    beta = float(np.cov(x_values, y_values, ddof=1)[0, 1] / variance)
    alpha_daily = float(np.mean(y_values) - beta * np.mean(x_values))

    residual = y_values - (alpha_daily + beta * x_values)
    tracking_error = float(np.std(residual, ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))

    correlation = float(np.corrcoef(x_values, y_values)[0, 1])

    return RegressionResult(
        sample_count=len(x_values),
        correlation=correlation,
        beta=beta,
        alpha_daily=alpha_daily,
        alpha_annual=alpha_daily * TRADING_DAYS_PER_YEAR,
        # 절편이 있는 단순 회귀에서는 결정계수가 상관계수의 제곱과 같다
        r_squared=correlation**2,
        tracking_error=tracking_error,
    )


def annual_drift(
    dates: pd.Series | pd.DatetimeIndex,
    actual: pd.Series,
    theoretical: pd.Series,
) -> AnnualDriftResult:
    """연도별 누적수익률의 차이를 낸다.

    **거래일 수를 함께 낸다.** 첫 해와 마지막 해는 대개 부분 연도라 괴리가 작게 나오는데,
    그 사실이 표에 보이지 않으면 폭이 실제보다 좁아 보인다.

    Args:
        dates: 날짜 (오름차순). Series 와 DatetimeIndex 를 모두 받는다
        actual: 실제 일간수익률 (비율)
        theoretical: 이론 일간수익률 (비율)

    Returns:
        연도별 표와 괴리 폭

    Raises:
        ValueError: 길이가 다르거나, 비었거나, 결측이 있는 경우
    """
    if not len(dates) == len(actual) == len(theoretical):
        raise ValueError(f"세 계열의 길이가 다릅니다: {len(dates)} / {len(actual)} / {len(theoretical)}")

    if len(dates) == 0:
        raise ValueError("연도별 괴리를 낼 표본이 없습니다")

    if actual.isna().any() or theoretical.isna().any():
        raise ValueError(f"결측이 있습니다 - 실제 {int(actual.isna().sum())}건, 이론 {int(theoretical.isna().sum())}건")

    frame = pd.DataFrame(
        {
            COL_YEAR: pd.DatetimeIndex(pd.to_datetime(dates)).year.to_numpy(),
            COL_ACTUAL_CUMULATIVE: actual.to_numpy(dtype=float),
            COL_THEORETICAL_CUMULATIVE: theoretical.to_numpy(dtype=float),
        }
    )

    grouped = frame.groupby(COL_YEAR, sort=True)
    summary = pd.DataFrame(
        {
            COL_TRADING_DAYS: grouped.size(),
            COL_ACTUAL_CUMULATIVE: grouped[COL_ACTUAL_CUMULATIVE].apply(_compound),
            COL_THEORETICAL_CUMULATIVE: grouped[COL_THEORETICAL_CUMULATIVE].apply(_compound),
        }
    ).reset_index()

    summary[COL_DRIFT] = summary[COL_ACTUAL_CUMULATIVE] - summary[COL_THEORETICAL_CUMULATIVE]

    drifts = summary[COL_DRIFT]
    spread = float(drifts.max() - drifts.min())

    spread_excluding_edges: float | None = None
    if len(summary) >= MIN_YEARS_FOR_EDGE_SPREAD:
        middle = drifts.iloc[1:-1]
        spread_excluding_edges = float(middle.max() - middle.min())

    return AnnualDriftResult(frame=summary, spread=spread, spread_excluding_edges=spread_excluding_edges)


def _compound(returns: pd.Series) -> float:
    """일간수익률을 복리로 누적한다.

    Args:
        returns: 일간수익률 (비율)

    Returns:
        누적수익률 (비율)
    """
    return float(np.prod(1.0 + returns.to_numpy(dtype=float))) - 1.0
