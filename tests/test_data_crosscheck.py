"""두 소스의 같은 날 종가를 대조하는 크로스체크의 산식과 보고 범위를 고정한다.

크로스체크는 **값을 바꾸지 않는다**(2026-09-29 사용자 결정 — `docs/매매/반감기_사이클/설계.md` 결정 ②).
그래서 지켜야 하는 것은 「무엇을 보고하는가」다.

1. 차이율은 `주 계열 ÷ 보완 계열 − 1` 이고, 목록은 그 **절대값이 허용폭을 넘는(>)** 날이다
2. 연도별 요약 · 한쪽에만 있는 날 · 주 계열의 거래량 0 인 날을 빠짐없이 낸다
3. 입력 프레임을 건드리지 않는다

허용폭 경계 테스트는 **부동소수점으로 정확히 표현되는 값**(1.25 − 1 = 0.25)을 쓴다 — 105 ÷ 100 − 1 은
0.05 보다 아주 조금 커서 경계를 재지 못한다.
"""

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_VALUE, COL_VOLUME
from verify_lab.data.crosscheck import (
    COL_DIFF_RATE,
    COL_MAX_ABS_DIFF,
    COL_MAX_DIFF_DATE,
    COL_MEDIAN_ABS_DIFF,
    COL_OVER_TOLERANCE_DAYS,
    COL_OVERLAP_DAYS,
    COL_PRIMARY,
    COL_SECONDARY,
    COL_YEAR,
    crosscheck_closes,
)


def _primary(rows: list[tuple[str, float, float]]) -> pd.DataFrame:
    """주 계열 — (날짜, 종가, 거래량). 로더를 지난 모양(날짜 datetime64 · 오름차순)."""
    frame = pd.DataFrame(rows, columns=[COL_DATE, COL_CLOSE, COL_VOLUME])
    frame[COL_DATE] = pd.to_datetime(frame[COL_DATE])
    return frame


def _secondary(rows: list[tuple[str, float]]) -> pd.DataFrame:
    """보완 계열 — (날짜, 값). 로더를 지난 모양."""
    frame = pd.DataFrame(rows, columns=[COL_DATE, COL_VALUE])
    frame[COL_DATE] = pd.to_datetime(frame[COL_DATE])
    return frame


def test_diff_rate_is_primary_over_secondary_minus_one() -> None:
    """
    목적: 차이율 산식을 손 계산 값으로 고정한다.

    Given: 주 110 · 보완 100 인 하루
    When: 크로스체크한다
    Then: 차이율이 0.1 이다
    """
    result = crosscheck_closes(_primary([("2020-01-01", 110.0, 1.0)]), _secondary([("2020-01-01", 100.0)]))

    assert result.overlap[COL_DIFF_RATE].tolist() == pytest.approx([0.1], abs=1e-12)
    assert result.overlap[COL_PRIMARY].tolist() == pytest.approx([110.0], abs=1e-12)
    assert result.overlap[COL_SECONDARY].tolist() == pytest.approx([100.0], abs=1e-12)


def test_day_exactly_at_tolerance_is_not_listed() -> None:
    """
    목적: 허용폭과 정확히 같은 날은 목록에 넣지 않음을 고정한다 (경계 조건 · `>`).

    Given: 차이율이 정확히 +0.25 인 날과 −0.5 인 날, 허용폭 0.25
    When: 크로스체크한다
    Then: −0.5 인 날 하나만 목록에 있다 (방향과 무관하게 절대값으로 본다)
    """
    # Given
    primary = _primary([("2020-01-01", 125.0, 1.0), ("2020-01-02", 50.0, 1.0)])
    secondary = _secondary([("2020-01-01", 100.0), ("2020-01-02", 100.0)])

    # When
    result = crosscheck_closes(primary, secondary, tolerance=0.25)

    # Then
    assert result.over_tolerance[COL_DATE].tolist() == [pd.Timestamp("2020-01-02")]


def test_yearly_summary_counts_and_extremes() -> None:
    """
    목적: 연도별 요약(겹치는 날 · 중앙 절대차 · 최대와 그 날 · 허용폭 초과 일수)을 고정한다.

    Given: 2019 년 사흘(차이 0 · +0.1 · −0.5) · 2020 년 하루(차이 0), 허용폭 0.25
    When: 크로스체크한다
    Then: 2019 행은 3일 · 중앙 0.1 · 최대 0.5(01-03) · 초과 1일, 2020 행은 1일 · 초과 0일
    """
    # Given
    primary = _primary(
        [
            ("2019-01-01", 100.0, 1.0),
            ("2019-01-02", 110.0, 1.0),
            ("2019-01-03", 50.0, 1.0),
            ("2020-01-01", 100.0, 1.0),
        ]
    )
    secondary = _secondary([("2019-01-01", 100.0), ("2019-01-02", 100.0), ("2019-01-03", 100.0), ("2020-01-01", 100.0)])

    # When
    yearly = crosscheck_closes(primary, secondary, tolerance=0.25).yearly.set_index(COL_YEAR)

    # Then
    assert yearly.loc[2019, COL_OVERLAP_DAYS] == 3
    assert yearly.loc[2019, COL_MEDIAN_ABS_DIFF] == pytest.approx(0.1, abs=1e-12)
    assert yearly.loc[2019, COL_MAX_ABS_DIFF] == pytest.approx(0.5, abs=1e-12)
    assert yearly.loc[2019, COL_MAX_DIFF_DATE] == pd.Timestamp("2019-01-03")
    assert yearly.loc[2019, COL_OVER_TOLERANCE_DAYS] == 1
    assert yearly.loc[2020, COL_OVERLAP_DAYS] == 1
    assert yearly.loc[2020, COL_OVER_TOLERANCE_DAYS] == 0


def test_days_present_on_one_side_are_counted_both_ways() -> None:
    """
    목적: 한쪽에만 있는 날을 양방향으로 따로 셈을 고정한다.

    보완 계열이 주 계열보다 먼저 시작하는 것은 정상(비트코인은 Coin Metrics 가 13개월 앞선다)이라
    **개수를 내는 것이지 막는 것이 아니다.**

    Given: 주 계열 01-02 ~ 01-04, 보완 계열 01-01 ~ 01-03
    When: 크로스체크한다
    Then: 주 계열에만 1일(01-04), 보완 계열에만 1일(01-01)
    """
    # Given
    primary = _primary([("2020-01-02", 100.0, 1.0), ("2020-01-03", 100.0, 1.0), ("2020-01-04", 100.0, 1.0)])
    secondary = _secondary([("2020-01-01", 100.0), ("2020-01-02", 100.0), ("2020-01-03", 100.0)])

    # When
    result = crosscheck_closes(primary, secondary)

    # Then
    assert result.primary_only_count == 1
    assert result.secondary_only_count == 1
    assert len(result.overlap) == 2


def test_zero_volume_days_of_primary_are_listed() -> None:
    """
    목적: 주 계열에서 거래가 없던 날을 목록으로 냄을 고정한다.

    거래가 없던 날의 가격은 체결가가 아니라 전일값 이월이다(Bitstamp 2015-01-06 ~ 08 실측).
    이 목록이 측정 계층의 대체(`설계.md` 결정 ④)의 입력이 된다.

    Given: 거래량이 0 인 날 하나
    When: 크로스체크한다
    Then: 그 날이 목록에 있다
    """
    # Given
    primary = _primary([("2020-01-01", 100.0, 5.0), ("2020-01-02", 100.0, 0.0)])
    secondary = _secondary([("2020-01-01", 100.0), ("2020-01-02", 101.0)])

    # When
    result = crosscheck_closes(primary, secondary)

    # Then
    assert result.zero_volume[COL_DATE].tolist() == [pd.Timestamp("2020-01-02")]


def test_inputs_are_not_modified() -> None:
    """
    목적: 두 입력 프레임을 바꾸지 않음을 고정한다 (데이터 불변성 · `설계.md` 결정 ②).

    Given: 두 계열
    When: 크로스체크한다
    Then: 원본이 그대로다
    """
    # Given
    primary = _primary([("2020-01-01", 110.0, 1.0)])
    secondary = _secondary([("2020-01-01", 100.0)])
    primary_before, secondary_before = primary.copy(), secondary.copy()

    # When
    crosscheck_closes(primary, secondary)

    # Then
    pd.testing.assert_frame_equal(primary, primary_before)
    pd.testing.assert_frame_equal(secondary, secondary_before)


def test_no_overlapping_day_is_rejected() -> None:
    """
    목적: 겹치는 날이 하나도 없으면 「차이 없음」으로 넘기지 않음을 고정한다 (경계 조건).

    Given: 날짜가 전혀 겹치지 않는 두 계열
    When: 크로스체크한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="겹치는 날"):
        crosscheck_closes(_primary([("2020-01-01", 100.0, 1.0)]), _secondary([("2020-01-02", 100.0)]))


def test_non_positive_tolerance_is_rejected() -> None:
    """
    목적: 0 이하 허용폭을 받지 않음을 고정한다.

    Given: 허용폭 0
    When: 크로스체크한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="허용폭"):
        crosscheck_closes(_primary([("2020-01-01", 100.0, 1.0)]), _secondary([("2020-01-01", 100.0)]), tolerance=0.0)


@pytest.mark.parametrize("tolerance", [float("nan"), float("inf")])
def test_non_finite_tolerance_is_rejected(tolerance: float) -> None:
    """
    목적: NaN · 무한대 허용폭을 받지 않음을 고정한다 — 받으면 어떤 날도 목록에 오르지 않는다.

    Given: 허용폭 NaN 또는 무한대
    When: 크로스체크한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="허용폭"):
        crosscheck_closes(
            _primary([("2020-01-01", 200.0, 1.0)]), _secondary([("2020-01-01", 100.0)]), tolerance=tolerance
        )


def test_year_uses_calendar_year_of_date() -> None:
    """
    목적: 연도 칸이 날짜의 달력 연도임을 고정한다.

    Given: 2019-12-31 과 2020-01-01
    When: 크로스체크한다
    Then: 연도가 2019 · 2020 두 행이다
    """
    primary = _primary([("2019-12-31", 100.0, 1.0), ("2020-01-01", 100.0, 1.0)])
    secondary = _secondary([("2019-12-31", 100.0), ("2020-01-01", 100.0)])

    years = crosscheck_closes(primary, secondary).yearly[COL_YEAR].tolist()

    assert years == [2019, 2020]
