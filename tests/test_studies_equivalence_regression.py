"""회귀 통계와 연도별 괴리 산식을 고정한다.

사양서 §16.2·§16.3 의 판정이 전부 이 값들에 걸려 있다. 산식이 조용히 달라지면
합격선 판정이 뒤집히므로, 손으로 검산 가능한 입력으로 값을 못 박는다.
"""

import numpy as np
import pandas as pd
import pytest

from verify_lab.studies.usdkrw_equivalence.constants import (
    COL_DRIFT,
    COL_TRADING_DAYS,
    COL_YEAR,
    SPEC_TRADING_DAYS_PER_YEAR,
)
from verify_lab.studies.usdkrw_equivalence.regression import annual_drift, fit_regression


def test_perfect_line_recovers_slope_and_intercept() -> None:
    """
    목적: 회귀가 기울기와 절편을 정확히 복원함을 고정한다.

    Given: y = 2x + 0.001 을 정확히 따르는 표본
    When: 회귀한다
    Then: 베타 2, 일간 알파 0.001, R2 1 이다
    """
    # Given
    x = pd.Series([0.01, -0.02, 0.03, -0.01, 0.005])
    y = 2 * x + 0.001

    # When
    result = fit_regression(x, y)

    # Then
    assert result.beta == pytest.approx(2.0, abs=1e-9)
    assert result.alpha_annual == pytest.approx(0.001 * SPEC_TRADING_DAYS_PER_YEAR, abs=1e-9)
    assert result.r_squared == pytest.approx(1.0, abs=1e-9)
    assert result.correlation == pytest.approx(1.0, abs=1e-9)


def test_alpha_is_annualized_by_trading_days() -> None:
    """
    목적: 알파 연환산이 **거래일 250 배**임을 고정한다 (사양서 §16.3).

    Given: 일간 알파가 0.001 인 표본
    When: 회귀한다
    Then: 연환산 알파가 0.001 × 250 이다
    """
    x = pd.Series([0.01, -0.02, 0.03, -0.01, 0.005])
    y = 2 * x + 0.001

    result = fit_regression(x, y)

    assert result.alpha_annual == pytest.approx(0.001 * SPEC_TRADING_DAYS_PER_YEAR, abs=1e-9)


def test_tracking_error_is_residual_std_times_sqrt_250() -> None:
    """
    목적: 추적오차 산식을 고정한다 (사양서 §16.2).

    Given: 잔차가 있는 표본
    When: 회귀한다
    Then: 추적오차가 잔차 표준편차 × √250 이다
    """
    # Given
    x = pd.Series([0.01, -0.02, 0.03, -0.01, 0.005])
    y = pd.Series([0.021, -0.039, 0.058, -0.022, 0.012])

    # When
    result = fit_regression(x, y)

    # Then
    residual = y - (result.alpha_annual / SPEC_TRADING_DAYS_PER_YEAR + result.beta * x)
    expected = float(residual.std(ddof=1)) * np.sqrt(SPEC_TRADING_DAYS_PER_YEAR)

    assert result.tracking_error == pytest.approx(expected, abs=1e-12)


def test_perfect_fit_has_zero_tracking_error() -> None:
    """
    목적: 잔차가 없으면 추적오차가 0 임을 고정한다 (경계 조건).

    Given: 정확한 직선 관계
    When: 회귀한다
    Then: 추적오차가 0 이다
    """
    x = pd.Series([0.01, -0.02, 0.03, -0.01])
    result = fit_regression(x, 2 * x + 0.001)

    assert result.tracking_error == pytest.approx(0.0, abs=1e-12)


def test_sample_count_is_reported() -> None:
    """
    목적: 표본 수가 결과에 담김을 고정한다 (표본 수 생략 금지).

    Given: 5개짜리 표본
    When: 회귀한다
    Then: 표본 수가 5 다
    """
    x = pd.Series([0.01, -0.02, 0.03, -0.01, 0.005])

    assert fit_regression(x, 2 * x).sample_count == 5


def test_mismatched_length_raises() -> None:
    """
    목적: 길이가 다른 입력을 조용히 잘라 쓰지 않음을 고정한다 (경계 조건).

    Given: 길이가 다른 두 계열
    When: 회귀한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="길이"):
        fit_regression(pd.Series([0.01, 0.02]), pd.Series([0.01]))


def test_too_few_samples_raises() -> None:
    """
    목적: 두 점 미만으로 회귀하지 않음을 고정한다 (경계 조건).

    Given: 한 점짜리 표본
    When: 회귀한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="두 개"):
        fit_regression(pd.Series([0.01]), pd.Series([0.02]))


def test_constant_x_raises() -> None:
    """
    목적: 설명변수가 상수면 회귀하지 않음을 고정한다 (경계 조건).

    기울기가 정의되지 않는데 조용히 0 이나 NaN 을 돌려주면 합격선 판정이 오작동한다.

    Given: 모두 같은 값인 설명변수
    When: 회귀한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="변동이 없습니다"):
        fit_regression(pd.Series([0.01, 0.01, 0.01]), pd.Series([0.02, 0.03, 0.01]))


def test_missing_values_raise() -> None:
    """
    목적: 결측을 조용히 버리지 않음을 고정한다 (표본 보존).

    Given: 결측이 섞인 표본
    When: 회귀한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="결측"):
        fit_regression(pd.Series([0.01, np.nan, 0.03]), pd.Series([0.02, 0.04, 0.06]))


def test_annual_drift_is_actual_minus_theoretical_per_year() -> None:
    """
    목적: 연도별 괴리가 **그 해 누적수익률의 차이**임을 고정한다.

    Given: 2년치 수익률
    When: 연도별 괴리를 낸다
    Then: 각 해의 (실제 누적 − 이론 누적) 이 나온다
    """
    # Given: 2025년 두 칸(+1%, +1%), 2026년 두 칸(+2%, 0%)
    dates = pd.to_datetime(["2025-06-02", "2025-06-03", "2026-06-02", "2026-06-03"])
    actual = pd.Series([0.01, 0.01, 0.02, 0.00])
    theoretical = pd.Series([0.01, 0.00, 0.01, 0.01])

    # When
    result = annual_drift(dates, actual, theoretical)

    # Then
    assert result.frame[COL_YEAR].tolist() == [2025, 2026]
    assert result.frame[COL_DRIFT].tolist() == pytest.approx([1.01 * 1.01 - 1.01, 1.02 * 1.00 - 1.01 * 1.01], abs=1e-12)


def test_annual_drift_reports_day_count_per_year() -> None:
    """
    목적: 연도별 거래일 수가 함께 나옴을 고정한다.

    부분 연도(첫 해·마지막 해)를 독자가 알아볼 수 있어야 괴리 폭을 오독하지 않는다.

    Given: 2025년 2칸, 2026년 1칸
    When: 연도별 괴리를 낸다
    Then: 거래일 수가 [2, 1] 이다
    """
    dates = pd.to_datetime(["2025-06-02", "2025-06-03", "2026-06-02"])
    result = annual_drift(dates, pd.Series([0.01, 0.01, 0.02]), pd.Series([0.01, 0.00, 0.01]))

    assert result.frame[COL_TRADING_DAYS].tolist() == [2, 1]


def test_annual_drift_spread_is_max_minus_min() -> None:
    """
    목적: 괴리 폭이 최대−최소임을 고정한다 (사양서 §16.2 의 "편차 0.3%p 이내").

    Given: 연도별 괴리가 서로 다른 표본
    When: 연도별 괴리를 낸다
    Then: 폭이 최대와 최소의 차이다
    """
    dates = pd.to_datetime(["2024-06-02", "2025-06-02", "2026-06-02"])
    result = annual_drift(dates, pd.Series([0.03, 0.01, 0.02]), pd.Series([0.01, 0.01, 0.01]))

    drifts = result.frame[COL_DRIFT]

    assert result.spread == pytest.approx(float(drifts.max() - drifts.min()), abs=1e-12)
