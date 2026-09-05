"""실효 총비용 산식을 고정한다.

이 측정은 **두 보정 중 하나만 빠져도 값이 크게 틀린다.**

1. NAV 에 분배금 조정을 걸지 않으면 분배락이 비용으로 잡혀 값이 부풀려진다
2. 기준선에 노출 배수를 반영하지 않으면 2배 상품에서 **원화금리 전액이 비용으로 둔갑**한다

둘 다 예외 없이 조용히 틀리는 종류라 테스트로 못 박는다.
"""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from verify_lab.common_constants import (
    CALENDAR_DAYS_PER_YEAR,
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_VALUE,
    COL_VOLUME,
)
from verify_lab.studies.usdkrw_equivalence.constants import (
    COL_ACTUAL_RETURN,
    COL_DAY_COUNT,
    COL_ETF_CLOSE,
    COL_KRW_RATE,
    COL_RATE_CONTRIBUTION,
    COL_SPOT,
    COL_SPOT_RETURN,
    COL_THEORETICAL_RETURN,
    COL_USD_RATE,
    EtfTarget,
)
from verify_lab.studies.usdkrw_equivalence.effective_cost import build_adjusted_nav, build_cost_returns
from verify_lab.studies.usdkrw_equivalence.regression import fit_regression


def _aligned(dates: list[str], nav: list[float], spot: list[float], usd: list[float], krw: list[float]) -> pd.DataFrame:
    """정렬 결과 형태의 합성 표를 만든다."""
    frame = pd.DataFrame(
        {
            COL_DATE: pd.to_datetime(dates),
            COL_ETF_CLOSE: nav,
            COL_SPOT: spot,
            COL_KRW_RATE: krw,
            COL_USD_RATE: usd,
        }
    )
    days = pd.DatetimeIndex(frame[COL_DATE]).to_numpy(dtype="datetime64[D]").astype("int64")
    frame[COL_DAY_COUNT] = [float("nan"), *(days[1:] - days[:-1]).astype(float)]

    return frame


SIMPLE = _aligned(
    ["2026-01-02", "2026-01-05"],
    nav=[10_000.0, 10_100.0],
    spot=[1_000.0, 1_010.0],
    usd=[3.65, 3.65],
    krw=[1.46, 1.46],
)


def test_exposure_one_uses_usd_rate_only() -> None:
    """
    목적: 1배에서는 이자가 달러금리 그대로임을 고정한다.

    Given: 연 3.65% 달러금리와 3일 간격
    When: 노출 1배로 수익률을 만든다
    Then: 이자 기여분이 0.0365 × 3 ÷ 365 다
    """
    result = build_cost_returns(SIMPLE, exposure=1)

    assert result[COL_RATE_CONTRIBUTION].iloc[0] == pytest.approx(0.0365 * 3 / CALENDAR_DAYS_PER_YEAR, abs=1e-12)


def test_exposure_two_subtracts_one_krw_rate() -> None:
    """
    목적: 2배에서 **원화금리를 1배만 차감**함을 고정한다.

    2배 상품은 2배 노출을 1배 담보로 굴린다. 담보가 하나뿐이라 원화 이자도 하나뿐이다.
    이것을 빼먹으면 원화금리 전액이 비용으로 둔갑한다.

    Given: 달러 3.65% · 원화 1.46% 와 3일 간격
    When: 노출 2배로 수익률을 만든다
    Then: 이자 기여분이 (2×0.0365 − 1×0.0146) × 3 ÷ 365 다
    """
    result = build_cost_returns(SIMPLE, exposure=2)

    expected = (2 * 0.0365 - 1 * 0.0146) * 3 / CALENDAR_DAYS_PER_YEAR

    assert result[COL_RATE_CONTRIBUTION].iloc[0] == pytest.approx(expected, abs=1e-12)


def test_exposure_multiplies_spot_return() -> None:
    """
    목적: 현물 부분이 노출 배수만큼 곱해짐을 고정한다.

    일간 리밸런싱 상품의 하루 수익은 기초자산 하루 수익의 정확히 L 배다.

    Given: 현물 +1%
    When: 노출 2배로 수익률을 만든다
    Then: 이론값의 현물 몫이 +2% 다
    """
    result = build_cost_returns(SIMPLE, exposure=2)
    row = result.iloc[0]

    assert row[COL_SPOT_RETURN] == pytest.approx(0.01, abs=1e-12)
    assert row[COL_THEORETICAL_RETURN] == pytest.approx(2 * 0.01 + row[COL_RATE_CONTRIBUTION], abs=1e-12)


def test_zero_exposure_raises() -> None:
    """
    목적: 노출 배수가 1 미만이면 거부함을 고정한다 (경계 조건).

    Given: 노출 0
    When: 수익률을 만든다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="노출 배수"):
        build_cost_returns(SIMPLE, exposure=0)


def test_single_row_raises() -> None:
    """
    목적: 수익률을 만들 수 없는 입력을 거부함을 고정한다 (경계 조건).

    Given: 한 행짜리 정렬 표
    When: 수익률을 만든다
    Then: ValueError 가 발생한다
    """
    single = _aligned(["2026-01-02"], [10_000.0], [1_000.0], [3.65], [1.46])

    with pytest.raises(ValueError, match="두 행"):
        build_cost_returns(single, exposure=1)


def test_adjusted_nav_applies_price_ratio(tmp_path: Path) -> None:
    """
    목적: NAV 에 **시세에서 뽑은 조정 배율**이 적용됨을 고정한다.

    원 NAV 를 그대로 쓰면 분배락이 비용으로 잡혀 실효 비용이 부풀려진다.

    Given: 수정 종가가 원본가의 0.99 배인 시세와 NAV
    When: 조정된 NAV 를 만든다
    Then: NAV 도 0.99 배가 된다
    """
    # Given
    days = [date(2026, 1, 2), date(2026, 1, 5)]
    pd.DataFrame(
        {
            COL_DATE: days,
            COL_OPEN: [10_000.0, 10_000.0],
            COL_HIGH: [10_000.0, 10_000.0],
            COL_LOW: [10_000.0, 10_000.0],
            COL_CLOSE: [10_000.0, 10_000.0],
            COL_VOLUME: [1_000, 1_000],
        }
    ).to_csv(tmp_path / "raw.csv", index=False)
    pd.DataFrame(
        {
            COL_DATE: days,
            COL_OPEN: [9_900.0, 9_900.0],
            COL_HIGH: [9_900.0, 9_900.0],
            COL_LOW: [9_900.0, 9_900.0],
            COL_CLOSE: [9_900.0, 9_900.0],
            COL_VOLUME: [1_000, 1_000],
        }
    ).to_csv(tmp_path / "adj.csv", index=False)
    pd.DataFrame({COL_DATE: days, COL_VALUE: [10_050.0, 10_060.0]}).to_csv(tmp_path / "nav.csv", index=False)

    target = EtfTarget(
        key="t",
        ticker="T",
        label="합성",
        price_path=tmp_path / "adj.csv",
        raw_price_path=tmp_path / "raw.csv",
        nav_path=tmp_path / "nav.csv",
        exposure=1,
        published_ter=0.0025,
    )

    # When
    result = build_adjusted_nav(target)

    # Then
    assert result[COL_CLOSE].tolist() == pytest.approx([10_050.0 * 0.99, 10_060.0 * 0.99], abs=1e-9)


def test_known_fee_is_recovered_for_leveraged_fund() -> None:
    """
    목적: 알려진 수수료를 가진 합성 2배 펀드에서 그 값이 복원됨을 고정한다.

    **이 테스트가 산식 전체의 정합을 잡는다.** 노출 배수나 담보 구조를 틀리면
    복원값이 원화금리만큼 어긋난다.

    Given: 연 0.45% 수수료를 떼는 완벽한 2배 펀드
    When: 노출 2배 기준선에 회귀한다
    Then: 실효 비용이 0.45% 로 복원된다
    """
    # Given
    fee = 0.0045
    usd, krw = 4.20, 3.50
    days: list[date] = []
    cursor = date(2024, 1, 2)
    while len(days) < 500:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)

    spot = [1_300.0 + (index % 30) - (index % 11) * 0.4 for index in range(len(days))]
    nav = [10_000.0]
    for index in range(1, len(days)):
        gap = (days[index] - days[index - 1]).days
        spot_change = spot[index] / spot[index - 1] - 1
        carry = (2 * usd / 100 - 1 * krw / 100) * gap / CALENDAR_DAYS_PER_YEAR
        nav.append(nav[-1] * (1 + 2 * spot_change + carry - fee * gap / CALENDAR_DAYS_PER_YEAR))

    aligned = _aligned(
        [day.isoformat() for day in days],
        nav=nav,
        spot=spot,
        usd=[usd] * len(days),
        krw=[krw] * len(days),
    )

    # When
    returns = build_cost_returns(aligned, exposure=2)
    fit = fit_regression(returns[COL_THEORETICAL_RETURN], returns[COL_ACTUAL_RETURN])

    # Then
    # 정확히 일치하지는 않는다. **일할은 365 달력일, 연환산은 250 거래일**이라
    # 표본의 실제 거래일 밀도(약 261일/년)와 어긋나기 때문이다. 250 은 사양서 §16.3 이 정한 값이므로
    # 코드가 아니라 이 오차가 사실이며, 그 크기가 몇 % 수준임을 함께 고정한다
    assert -fit.alpha_annual == pytest.approx(fee, rel=0.06)
    assert fit.beta == pytest.approx(1.0, abs=1e-3)


def test_wrong_exposure_inflates_cost_by_krw_rate() -> None:
    """
    목적: 노출 배수를 반영하지 않으면 **원화금리만큼 비용이 부풀려짐**을 고정한다.

    이것이 이 모듈이 존재하는 이유다. 2배 상품을 `2 × (현물 + 달러금리)` 에 견주면
    담보가 1배뿐이라는 구조가 무시되어 원화금리 전액이 비용으로 둔갑한다.

    Given: 수수료가 0 인 완벽한 2배 펀드
    When: 노출을 반영한 기준선과 반영하지 않은 기준선으로 각각 잰다
    Then: 두 값의 차이가 원화금리다
    """
    # Given
    usd, krw = 4.20, 3.50
    days: list[date] = []
    cursor = date(2024, 1, 2)
    while len(days) < 500:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)

    spot = [1_300.0 + (index % 30) - (index % 11) * 0.4 for index in range(len(days))]
    nav = [10_000.0]
    for index in range(1, len(days)):
        gap = (days[index] - days[index - 1]).days
        spot_change = spot[index] / spot[index - 1] - 1
        carry = (2 * usd / 100 - 1 * krw / 100) * gap / CALENDAR_DAYS_PER_YEAR
        nav.append(nav[-1] * (1 + 2 * spot_change + carry))

    aligned = _aligned(
        [day.isoformat() for day in days], nav=nav, spot=spot, usd=[usd] * len(days), krw=[krw] * len(days)
    )

    # When
    correct = build_cost_returns(aligned, exposure=2)
    correct_cost = -fit_regression(correct[COL_THEORETICAL_RETURN], correct[COL_ACTUAL_RETURN]).alpha_annual

    # 담보 구조를 빼먹은 기준선 — 「2 × (현물 + 달러금리)」
    wrong = correct.copy()
    wrong[COL_THEORETICAL_RETURN] = wrong[COL_THEORETICAL_RETURN] + (krw / 100) * gap_series(aligned)
    wrong_cost = -fit_regression(wrong[COL_THEORETICAL_RETURN], wrong[COL_ACTUAL_RETURN]).alpha_annual

    # Then: 차이가 원화금리다. 연환산 250 과 실제 거래일 밀도의 차이만큼 어긋난다
    assert correct_cost == pytest.approx(0.0, abs=1e-4)
    assert wrong_cost - correct_cost == pytest.approx(krw / 100, rel=0.06)


def gap_series(aligned: pd.DataFrame) -> pd.Series:
    """첫 행을 뺀 달력일 비율(일수 ÷ 365)을 돌려준다."""
    return (aligned[COL_DAY_COUNT] / CALENDAR_DAYS_PER_YEAR).iloc[1:].reset_index(drop=True)
