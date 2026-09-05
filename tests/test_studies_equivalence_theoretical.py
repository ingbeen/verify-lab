"""이론값 구성 산식을 고정한다.

**사양서 안에서 두 식이 갈린다.** §16.1 의 H₀ 는 `현물 + (달러금리 − 원화금리)` 인데,
§2.1 의 커버드 금리평형을 따르면 `현물 + 달러금리` 가 된다. 두 식은 **원화금리만큼** 다르고,
임의로 하나를 고르면 알파가 통째로 틀린다. 그래서 둘 다 산출한다.

이 테스트가 지키는 것은 셋이다.

1. **이자는 달력일 ÷ 365 로 일할한다** — 거래일 수로 세면 주말 이자가 사라진다
2. **직전 행의 금리를 쓴다** — 구간이 끝난 뒤의 금리를 쓰면 미래를 참조한다
3. **현물과 이자를 곱으로 결합한다** — 누적 비교에서 복리가 어긋나지 않는다
"""

import numpy as np
import pandas as pd
import pytest

from verify_lab.common_constants import CALENDAR_DAYS_PER_YEAR, COL_DATE
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
    TheoreticalModel,
)
from verify_lab.studies.usdkrw_equivalence.theoretical import build_returns


def _aligned(
    dates: list[str],
    etf_close: list[float],
    spot: list[float],
    usd_rate: list[float],
    krw_rate: list[float],
) -> pd.DataFrame:
    """정렬 결과 형태의 합성 표를 만든다."""
    frame = pd.DataFrame(
        {
            COL_DATE: pd.to_datetime(dates),
            COL_ETF_CLOSE: etf_close,
            COL_SPOT: spot,
            COL_KRW_RATE: krw_rate,
            COL_USD_RATE: usd_rate,
        }
    )
    days = pd.DatetimeIndex(frame[COL_DATE]).to_numpy(dtype="datetime64[D]").astype("int64")
    frame[COL_DAY_COUNT] = np.concatenate([[np.nan], np.diff(days).astype(float)])

    return frame


SIMPLE = _aligned(
    ["2026-01-02", "2026-01-05", "2026-01-06"],
    etf_close=[10_000.0, 10_100.0, 10_050.0],
    spot=[1_000.0, 1_010.0, 1_005.0],
    usd_rate=[3.65, 3.65, 3.65],
    krw_rate=[1.46, 1.46, 1.46],
)


def test_first_row_is_dropped() -> None:
    """
    목적: 수익률이 정의되지 않는 첫 행이 결과에서 빠짐을 고정한다 (경계 조건).

    Given: 3행짜리 정렬 표
    When: 수익률을 만든다
    Then: 2행이 남는다
    """
    result = build_returns(SIMPLE, TheoreticalModel.USD_RATE)

    assert len(result) == 2
    assert result[COL_DATE].iloc[0] == pd.Timestamp("2026-01-05")


def test_actual_and_spot_returns_are_simple_changes() -> None:
    """
    목적: 실제 수익률과 현물 변화율의 산식을 고정한다.

    Given: 10,000 → 10,100 인 ETF 와 1,000 → 1,010 인 환율
    When: 수익률을 만든다
    Then: 둘 다 +1% 다
    """
    result = build_returns(SIMPLE, TheoreticalModel.USD_RATE)

    assert result[COL_ACTUAL_RETURN].iloc[0] == pytest.approx(0.01, abs=1e-12)
    assert result[COL_SPOT_RETURN].iloc[0] == pytest.approx(0.01, abs=1e-12)


def test_rate_contribution_uses_calendar_days_over_365() -> None:
    """
    목적: 이자가 **달력일 ÷ 365** 로 일할됨을 고정한다.

    금요일에서 월요일로 넘어가는 칸은 사흘치 이자가 붙어야 한다.

    Given: 연 3.65% 금리와 3일 간격
    When: 달러금리 이론값을 만든다
    Then: 이자 기여분이 0.0365 × 3 ÷ 365 다
    """
    result = build_returns(SIMPLE, TheoreticalModel.USD_RATE)

    assert result[COL_RATE_CONTRIBUTION].iloc[0] == pytest.approx(0.0365 * 3 / CALENDAR_DAYS_PER_YEAR, abs=1e-12)


def test_carry_model_uses_rate_difference() -> None:
    """
    목적: 금리차 모형이 **달러금리 − 원화금리** 를 쓰는 것을 고정한다 (사양서 §16.1).

    Given: 달러 3.65% · 원화 1.46% 와 3일 간격
    When: 금리차 이론값을 만든다
    Then: 이자 기여분이 (0.0365 − 0.0146) × 3 ÷ 365 다
    """
    result = build_returns(SIMPLE, TheoreticalModel.CARRY)

    assert result[COL_RATE_CONTRIBUTION].iloc[0] == pytest.approx(
        (0.0365 - 0.0146) * 3 / CALENDAR_DAYS_PER_YEAR, abs=1e-12
    )


def test_two_models_differ_by_krw_rate() -> None:
    """
    목적: 두 모형의 차이가 정확히 **원화금리만큼**임을 고정한다.

    이것이 사양서 §16.1 과 §2.1 이 갈리는 지점이며, 둘 다 산출하는 이유다.

    Given: 같은 정렬 표
    When: 두 모형의 이자 기여분을 비교한다
    Then: 차이가 원화금리 일할분이다
    """
    carry = build_returns(SIMPLE, TheoreticalModel.CARRY)
    usd = build_returns(SIMPLE, TheoreticalModel.USD_RATE)

    difference = usd[COL_RATE_CONTRIBUTION] - carry[COL_RATE_CONTRIBUTION]
    expected = SIMPLE[COL_KRW_RATE].shift(1).iloc[1:] / 100 * SIMPLE[COL_DAY_COUNT].iloc[1:] / CALENDAR_DAYS_PER_YEAR

    assert difference.tolist() == pytest.approx(expected.tolist(), abs=1e-12)


def test_rate_is_taken_from_previous_row() -> None:
    """
    목적: 이자에 **직전 행의 금리**를 쓰는 것을 고정한다 (look-ahead 차단).

    구간이 끝난 뒤에 고시된 금리로 그 구간의 이자를 계산하면 미래를 참조하는 것이다.

    Given: 둘째 날에 금리가 급변한 표
    When: 수익률을 만든다
    Then: 첫 칸의 이자가 **변하기 전** 금리로 계산된다
    """
    # Given
    frame = _aligned(
        ["2026-01-02", "2026-01-05"],
        etf_close=[10_000.0, 10_000.0],
        spot=[1_000.0, 1_000.0],
        usd_rate=[3.65, 99.0],
        krw_rate=[1.46, 1.46],
    )

    # When
    result = build_returns(frame, TheoreticalModel.USD_RATE)

    # Then
    assert result[COL_RATE_CONTRIBUTION].iloc[0] == pytest.approx(0.0365 * 3 / CALENDAR_DAYS_PER_YEAR, abs=1e-12)


def test_theoretical_return_combines_multiplicatively() -> None:
    """
    목적: 현물 변화와 이자를 **곱으로** 결합함을 고정한다.

    이론 자산은 "달러 현물을 들고 이자를 받는 것"이라 원화 평가액이
    `환율 × (1 + 이자)` 로 커진다. 더하기로 두면 누적 비교에서 복리가 어긋난다.

    Given: 현물 +1%, 이자 기여분이 있는 칸
    When: 이론 수익률을 만든다
    Then: (1+현물)(1+이자) − 1 이다
    """
    result = build_returns(SIMPLE, TheoreticalModel.USD_RATE)
    row = result.iloc[0]

    expected = (1 + row[COL_SPOT_RETURN]) * (1 + row[COL_RATE_CONTRIBUTION]) - 1

    assert row[COL_THEORETICAL_RETURN] == pytest.approx(expected, abs=1e-12)


def test_single_row_input_raises() -> None:
    """
    목적: 수익률을 만들 수 없는 입력을 조용히 빈 표로 돌려주지 않음을 고정한다 (경계 조건).

    Given: 한 행짜리 정렬 표
    When: 수익률을 만든다
    Then: ValueError 가 발생한다
    """
    frame = _aligned(["2026-01-02"], [10_000.0], [1_000.0], [3.65], [1.46])

    with pytest.raises(ValueError, match="두 행"):
        build_returns(frame, TheoreticalModel.USD_RATE)


def test_source_frame_is_not_modified() -> None:
    """
    목적: 계산이 원본 DataFrame 을 건드리지 않음을 고정한다 (데이터 불변성).

    Given: 정렬 표의 사본
    When: 수익률을 만든다
    Then: 원본이 그대로다
    """
    before = SIMPLE.copy()

    build_returns(SIMPLE, TheoreticalModel.CARRY)

    pd.testing.assert_frame_equal(SIMPLE, before)


def test_returns_are_stable_under_truncation(assert_stable_under_truncation) -> None:  # type: ignore[no-untyped-def]
    """
    목적: 뒤를 잘라내도 앞선 행의 값이 같음을 고정한다 (look-ahead 감시).

    Given: 긴 정렬 표
    When: 뒤를 잘라 계산한 결과와 전체를 계산한 결과를 비교한다
    Then: 겹치는 범위의 값이 같다
    """
    # Given
    dates = [f"2026-01-{day:02d}" for day in range(2, 12)]
    frame = _aligned(
        dates,
        etf_close=[10_000.0 + index * 7 for index in range(len(dates))],
        spot=[1_000.0 + index for index in range(len(dates))],
        usd_rate=[3.65 + index * 0.01 for index in range(len(dates))],
        krw_rate=[1.46] * len(dates),
    )

    # When / Then
    assert_stable_under_truncation(
        lambda source: build_returns(source, TheoreticalModel.CARRY),
        frame,
        cut=6,
        key_columns=[COL_DATE],
        value_column=COL_THEORETICAL_RETURN,
    )
