"""검증 #7 의 월물 만기일 산출을 고정한다.

만기일은 시세가 아니라 달력 규칙이며, **규칙일이 휴장이면 직전 거래일로 앞당겨진다.**
여기서 가장 쉽게 나는 실수가 "달력상 하루 전"으로 구현하는 것이다 — 연휴가 걸리면 직전 거래일이
일주일 넘게 떨어진 달이 실제로 있다.

고정하는 계약은 넷이다.
- 규칙일이 거래일이면 그날이 만기일이고 앞당김은 0 이다
- 휴장이면 **직전 거래일**이 만기일이며, 앞당김은 달력일 수로 기록된다
- 데이터 범위를 벗어나거나 그 달의 앞 구간이 없는 달은 값을 지어내지 않고 제외한다
- 뒤에 데이터가 더 붙어도 이미 확정된 달의 만기일이 달라지지 않는다 (look-ahead 감시)
"""

import pandas as pd
import pytest

from verify_lab.studies.option_expiry.constants import (
    COL_ADVANCED_DAYS,
    COL_EXPIRY_DATE,
    COL_EXPIRY_MONTH,
    COL_RULE_DATE,
    KR_MONTHLY_EXPIRY,
    US_MONTHLY_EXPIRY,
)
from verify_lab.studies.option_expiry.expiry_calendar import monthly_expiry_dates, nth_weekday_of_month


def _trading_days(start: str, end: str, holidays: list[str] | None = None) -> pd.DatetimeIndex:
    """주중에서 지정한 휴장일을 뺀 합성 거래일 목록을 만든다.

    실제 시세 파일에 의존하면 데이터를 갱신할 때마다 테스트가 깨진다.

    Args:
        start: 시작일
        end: 종료일
        holidays: 제외할 휴장일 목록

    Returns:
        거래일 목록
    """
    days = pd.bdate_range(start, end)
    if holidays:
        days = days.difference(pd.DatetimeIndex([pd.Timestamp(d) for d in holidays]))

    return pd.DatetimeIndex(days)


def _expiry_of(frame: pd.DataFrame, month: str) -> pd.Series:
    """만기일 표에서 지정한 만기월의 행을 꺼낸다."""
    rows = frame[frame[COL_EXPIRY_MONTH] == month]
    assert len(rows) == 1, f"{month} 의 만기일 행이 1개가 아닙니다: {len(rows)}개"

    return rows.iloc[0]


class TestNthWeekdayOfMonth:
    """달력 규칙 자체를 고정한다."""

    def test_셋째_금요일을_돌려준다(self) -> None:
        """
        목적: 미국 월물 만기의 규칙일 계산을 고정한다

        Given: 2026년 6월
        When: 셋째 금요일을 구하면
        Then: 2026-06-19 이다
        """
        # Given / When
        result = nth_weekday_of_month(2026, 6, weekday=4, ordinal=3)

        # Then
        assert result == pd.Timestamp("2026-06-19")

    def test_둘째_목요일을_돌려준다(self) -> None:
        """
        목적: 한국 월물 만기의 규칙일 계산을 고정한다

        Given: 2025년 10월
        When: 둘째 목요일을 구하면
        Then: 2025-10-09 이다
        """
        # Given / When
        result = nth_weekday_of_month(2025, 10, weekday=3, ordinal=2)

        # Then
        assert result == pd.Timestamp("2025-10-09")

    def test_달_첫날이_해당_요일이면_그날이_첫번째다(self) -> None:
        """
        목적: 경계 조건 — 1일이 곧 해당 요일인 달에서 순번이 밀리지 않는지 고정한다

        Given: 2026-05-01 은 금요일이다
        When: 셋째 금요일을 구하면
        Then: 2026-05-15 이다 (1일이 첫째 금요일)
        """
        # Given
        assert pd.Timestamp("2026-05-01").dayofweek == 4

        # When
        result = nth_weekday_of_month(2026, 5, weekday=4, ordinal=3)

        # Then
        assert result == pd.Timestamp("2026-05-15")

    def test_그_달에_없는_순번은_예외다(self) -> None:
        """
        목적: 다음 달로 넘어간 날짜를 조용히 돌려주지 않음을 고정한다

        Given: 2026년 2월
        When: 다섯째 금요일을 요구하면
        Then: ValueError 가 난다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="번째 요일"):
            nth_weekday_of_month(2026, 2, weekday=4, ordinal=5)

    def test_요일_범위를_벗어나면_예외다(self) -> None:
        """
        목적: 입력 검증을 고정한다

        Given: 요일 7
        When: 규칙일을 구하면
        Then: ValueError 가 난다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="요일은"):
            nth_weekday_of_month(2026, 6, weekday=7, ordinal=3)


class TestMonthlyExpiryDates:
    """만기일 산출과 휴장 앞당김을 고정한다."""

    def test_규칙일이_거래일이면_그날이_만기일이다(self) -> None:
        """
        목적: 휴장이 없는 평범한 달의 만기일을 고정한다

        Given: 2026년 7월 전체가 거래일인 합성 달력
        When: 미국 규칙으로 만기일을 구하면
        Then: 셋째 금요일 2026-07-17 이고 앞당김은 0 이다
        """
        # Given
        days = _trading_days("2026-07-01", "2026-07-31")

        # When
        result = monthly_expiry_dates(days, US_MONTHLY_EXPIRY)

        # Then
        row = _expiry_of(result, "2026-07")
        assert row[COL_EXPIRY_DATE] == pd.Timestamp("2026-07-17")
        assert row[COL_ADVANCED_DAYS] == 0

    def test_미국_굿프라이데이는_직전_목요일로_앞당겨진다(self) -> None:
        """
        목적: 실제로 발생한 휴장 앞당김을 고정한다

        Given: 2022-04-15(셋째 금요일, Good Friday)가 휴장인 달력
        When: 미국 규칙으로 만기일을 구하면
        Then: 2022-04-14 이고 앞당김은 1 달력일이다
        """
        # Given
        days = _trading_days("2022-04-01", "2022-04-29", holidays=["2022-04-15"])

        # When
        result = monthly_expiry_dates(days, US_MONTHLY_EXPIRY)

        # Then
        row = _expiry_of(result, "2022-04")
        assert row[COL_RULE_DATE] == pd.Timestamp("2022-04-15")
        assert row[COL_EXPIRY_DATE] == pd.Timestamp("2022-04-14")
        assert row[COL_ADVANCED_DAYS] == 1

    def test_한국_연휴가_걸리면_일주일_넘게_앞당겨진다(self) -> None:
        """
        목적: **"달력상 하루 전"으로 구현하면 틀린다**는 것을 고정한다

        Given: 2025-10-03 ~ 10-09 가 전부 휴장인 달력 (추석 연휴)
        When: 한국 규칙으로 만기일을 구하면
        Then: 규칙일 2025-10-09 의 직전 거래일인 2025-10-02 이고 앞당김은 7 달력일이다
        """
        # Given
        days = _trading_days(
            "2025-10-01",
            "2025-10-31",
            holidays=["2025-10-03", "2025-10-06", "2025-10-07", "2025-10-08", "2025-10-09"],
        )

        # When
        result = monthly_expiry_dates(days, KR_MONTHLY_EXPIRY)

        # Then
        row = _expiry_of(result, "2025-10")
        assert row[COL_RULE_DATE] == pd.Timestamp("2025-10-09")
        assert row[COL_EXPIRY_DATE] == pd.Timestamp("2025-10-02")
        assert row[COL_ADVANCED_DAYS] == 7

    def test_규칙일이_데이터_범위_밖이면_그_달은_빠진다(self) -> None:
        """
        목적: 경계 조건 — 값을 지어내지 않음을 고정한다

        Given: 셋째 금요일 이전에 끝나는 달력
        When: 만기일을 구하면
        Then: 그 달의 행이 없다
        """
        # Given
        days = _trading_days("2026-07-01", "2026-07-10")

        # When
        result = monthly_expiry_dates(days, US_MONTHLY_EXPIRY)

        # Then
        assert result.empty

    def test_그_달의_앞_구간이_없으면_그_달은_빠진다(self) -> None:
        """
        목적: 경계 조건 — 데이터가 달 중간부터 시작하고 규칙일이 휴장인 경우를 고정한다

        Given: 2026-06-19(셋째 금요일)가 휴장이고 데이터가 그날부터 시작하는 달력
        When: 만기일을 구하면
        Then: 직전 거래일이 그 달에 없으므로 2026-06 행이 없다
        """
        # Given
        days = _trading_days("2026-06-19", "2026-07-31", holidays=["2026-06-19"])

        # When
        result = monthly_expiry_dates(days, US_MONTHLY_EXPIRY)

        # Then
        assert (result[COL_EXPIRY_MONTH] == "2026-06").sum() == 0

    def test_만기일은_모두_거래일이다(self) -> None:
        """
        목적: 표본 보존 — 산출된 만기일이 전부 실제 거래일임을 고정한다

        Given: 휴장이 여럿 섞인 2년치 달력
        When: 만기일을 구하면
        Then: 모든 만기일이 거래일 목록 안에 있다
        """
        # Given
        days = _trading_days("2025-01-01", "2026-12-31", holidays=["2025-04-18", "2026-06-19", "2025-10-09"])

        # When
        result = monthly_expiry_dates(days, US_MONTHLY_EXPIRY)

        # Then
        assert result[COL_EXPIRY_DATE].isin(days).all()

    def test_거래일_목록이_비면_예외다(self) -> None:
        """
        목적: 입력 검증을 고정한다

        Given: 빈 거래일 목록
        When: 만기일을 구하면
        Then: ValueError 가 난다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="비어 있어"):
            monthly_expiry_dates(pd.DatetimeIndex([]), US_MONTHLY_EXPIRY)

    def test_정렬되지_않은_거래일_목록은_예외다(self) -> None:
        """
        목적: 입력 검증을 고정한다

        Given: 내림차순 거래일 목록
        When: 만기일을 구하면
        Then: ValueError 가 난다
        """
        # Given
        days = pd.DatetimeIndex(_trading_days("2026-07-01", "2026-07-31")[::-1])

        # When / Then
        with pytest.raises(ValueError, match="오름차순"):
            monthly_expiry_dates(days, US_MONTHLY_EXPIRY)

    def test_뒤에_데이터가_붙어도_지난_달의_만기일은_그대로다(self) -> None:
        """
        목적: **look-ahead 감시** — 미래 거래일이 있든 없든 판정이 같음을 고정한다

        Given: 같은 시작일에서 6개월치와 24개월치 달력
        When: 각각 만기일을 구하면
        Then: 짧은 쪽에 있는 모든 만기월의 만기일이 긴 쪽과 같다
        """
        # Given
        holidays = ["2025-04-18", "2025-10-09", "2026-06-19"]
        short_days = _trading_days("2025-01-01", "2025-06-30", holidays=holidays)
        long_days = _trading_days("2025-01-01", "2026-12-31", holidays=holidays)

        # When
        short_result = monthly_expiry_dates(short_days, US_MONTHLY_EXPIRY)
        long_result = monthly_expiry_dates(long_days, US_MONTHLY_EXPIRY)

        # Then
        merged = short_result.merge(long_result, on=COL_EXPIRY_MONTH, suffixes=("_short", "_long"))
        assert len(merged) == len(short_result), "짧은 입력의 만기월이 긴 입력에 전부 있어야 합니다"
        assert (
            merged[f"{COL_EXPIRY_DATE}_short"] == merged[f"{COL_EXPIRY_DATE}_long"]
        ).all(), "뒤를 잘라낸 입력과 전체 입력의 만기일이 다릅니다 — 미래 데이터를 참조하고 있습니다"
