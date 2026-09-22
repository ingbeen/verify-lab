"""중간선거_사이클 — 달력 진입·청산과 사이클 위치 라벨링

**이 매매법은 정의 자체가 달력이다.** 진입은 10월 첫 거래일, 청산은 다음해 6월 마지막
거래일이고 둘 다 시세와 무관하게 정해진다. 그래서 여기가 틀리면 **모든 숫자가 조용히 틀린다.**

[중요] **두 규칙의 휴장 처리 방향이 «반대»다.**

| | 목표일이 휴장이면 |
| --- | --- |
| 진입 (10월 첫 거래일) | **미룬다** — 10월 1일 이후 첫 거래일 |
| 청산 (6월 마지막 거래일) | **앞당긴다** — 6월 30일 이전 마지막 거래일 |

`measure/calendar_entry.month_entry_dates` 는 **앞당김**이라 진입에 쓸 수 없다 —
`calendar_day=1` 로 부르면 10월 1일이 휴장인 해가 전부 「진입일 없음」이 된다.
그래서 이 매매법이 자기 달력을 갖는다.

**경계 픽스처를 손으로 박는다.** 10월 1일이 토요일인 해·일요일인 해·거래일인 해를 모두
넣어 **「미룸/앞당김」이 하드코딩돼도 걸리게** 한다.
"""

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE
from verify_lab.measure.constants import (
    COL_ENTRY_CLOSE,
    COL_EXCLUDED_REASON,
    COL_EXIT_CLOSE,
    COL_EXIT_DATE,
    COL_FORWARD_RETURN,
    COL_HOLD_DAYS,
    COL_MONTH,
    REASON_NONE,
    REASON_OUT_OF_RANGE,
)
from verify_lab.studies.midterm_cycle.constants import (
    COL_CYCLE_POSITION,
    COL_CYCLE_YEAR,
    CYCLE_ELECTION,
    CYCLE_MIDTERM,
    CYCLE_POST_ELECTION,
    CYCLE_PRE_ELECTION,
    ENTRY_MONTH,
    EXIT_MONTH,
    EXIT_MONTH_OFFSET,
    HORIZON_POOLED,
)
from verify_lab.studies.midterm_cycle.cycle_calendar import (
    cycle_position,
    cycle_returns,
    month_first_entries,
    month_offset_exit_schedule,
)


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
        days = days.difference(pd.DatetimeIndex([pd.Timestamp(day) for day in holidays]))

    return pd.DatetimeIndex(days)


def _prices(trading_days: pd.DatetimeIndex, values: list[float] | None = None) -> pd.DataFrame:
    """거래일마다 종가가 있는 합성 가격 데이터를 만든다.

    Args:
        trading_days: 거래일 목록
        values: 종가 목록. 없으면 100 부터 1씩 오른다

    Returns:
        날짜와 종가만 있는 DataFrame
    """
    closes = values if values is not None else [100.0 + index for index in range(len(trading_days))]

    return pd.DataFrame({COL_DATE: trading_days, COL_CLOSE: closes})


def _entry_of(frame: pd.DataFrame, year: int) -> pd.Series:
    """표에서 지정한 진입 연도의 행을 꺼낸다.

    Args:
        frame: 진입 연도 컬럼이 있는 표
        year: 진입 연도

    Returns:
        그 해의 한 행
    """
    rows = frame[frame[COL_CYCLE_YEAR] == year]
    assert len(rows) == 1, f"{year} 의 행이 1개가 아닙니다: {len(rows)}개"

    return rows.iloc[0]


class TestCyclePosition:
    """진입 연도를 사이클의 네 자리 중 하나로 라벨링한다."""

    @pytest.mark.parametrize(
        ("year", "expected"),
        [
            (1994, CYCLE_MIDTERM),
            (1995, CYCLE_PRE_ELECTION),
            (1996, CYCLE_ELECTION),
            (1997, CYCLE_POST_ELECTION),
            (2022, CYCLE_MIDTERM),
            (2023, CYCLE_PRE_ELECTION),
            (2024, CYCLE_ELECTION),
            (2025, CYCLE_POST_ELECTION),
            (2026, CYCLE_MIDTERM),
        ],
    )
    def test_진입_연도로_사이클_위치를_정한다(self, year: int, expected: str) -> None:
        """
        목적: 미국 선거 달력이 법으로 고정돼 있다는 사실을 라벨링 규칙으로 고정한다

        Given: 진입 연도
        When: 사이클 위치를 구하면
        Then: 중간선거해(4로 나눈 나머지 2) · 대선전해(3) · 대선해(0) · 대선다음해(1) 중 하나다
        """
        # Given / When
        result = cycle_position(year)

        # Then
        assert result == expected

    def test_네_위치가_4년마다_되풀이된다(self) -> None:
        """
        목적: 라벨이 사이클 주기와 어긋나지 않음을 고정한다

        Given: 연속한 12개 연도
        When: 각각의 사이클 위치를 구하면
        Then: 4년 간격의 두 해는 언제나 같은 위치다
        """
        # Given
        years = range(2014, 2026)

        # When
        positions = {year: cycle_position(year) for year in years}

        # Then
        assert all(positions[year] == positions[year + 4] for year in range(2014, 2022))


class TestMonthFirstEntries:
    """10월 «첫 거래일» 진입 — 휴장이면 «미룬다»."""

    def test_목표_달의_1일이_거래일이면_그날이다(self) -> None:
        """
        목적: 휴장이 없는 평범한 해의 진입일을 고정한다

        Given: 2025-10-01 은 수요일이다
        When: 10월 첫 거래일을 구하면
        Then: 2025-10-01 이다
        """
        # Given
        assert pd.Timestamp("2025-10-01").dayofweek == 2
        days = _trading_days("2025-01-02", "2026-12-31")

        # When
        result = month_first_entries(days, month=ENTRY_MONTH)

        # Then
        assert _entry_of(result, 2025)[COL_DATE] == pd.Timestamp("2025-10-01")

    def test_1일이_토요일이면_다음_월요일로_미룬다(self) -> None:
        """
        목적: [중요] **앞당김으로 구현하면 틀린다**는 것을 고정한다 — 앞당기면 9월로 넘어간다

        Given: 2022-10-01 은 토요일이다
        When: 10월 첫 거래일을 구하면
        Then: 2022-10-03(월) 이다 — 9월 30일이 아니다
        """
        # Given
        assert pd.Timestamp("2022-10-01").dayofweek == 5
        days = _trading_days("2022-01-03", "2023-12-29")

        # When
        result = month_first_entries(days, month=ENTRY_MONTH)

        # Then
        assert _entry_of(result, 2022)[COL_DATE] == pd.Timestamp("2022-10-03")

    def test_1일이_일요일이면_다음_월요일로_미룬다(self) -> None:
        """
        목적: 주말 두 형태를 모두 고정한다

        Given: 2023-10-01 은 일요일이다
        When: 10월 첫 거래일을 구하면
        Then: 2023-10-02(월) 이다
        """
        # Given
        assert pd.Timestamp("2023-10-01").dayofweek == 6
        days = _trading_days("2023-01-02", "2024-12-31")

        # When
        result = month_first_entries(days, month=ENTRY_MONTH)

        # Then
        assert _entry_of(result, 2023)[COL_DATE] == pd.Timestamp("2023-10-02")

    def test_연휴가_길어도_그_달_안에서_미룬다(self) -> None:
        """
        목적: 경계 조건 — 미룸 간격이 하루로 하드코딩돼 있지 않은지 고정한다

        Given: 2026-10-01 ~ 10-07 이 전부 휴장인 달력
        When: 10월 첫 거래일을 구하면
        Then: 2026-10-08 이다
        """
        # Given
        days = _trading_days(
            "2026-01-01",
            "2027-12-31",
            holidays=["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07"],
        )

        # When
        result = month_first_entries(days, month=ENTRY_MONTH)

        # Then
        assert _entry_of(result, 2026)[COL_DATE] == pd.Timestamp("2026-10-08")

    def test_진입일은_모두_목표_달에_있다(self) -> None:
        """
        목적: [중요] 전월로 넘어가지 않음을 고정한다 — 넘어가면 다른 매매가 된다

        Given: 휴장이 여럿 섞인 10년치 달력
        When: 10월 첫 거래일들을 구하면
        Then: 전부 10월이다
        """
        # Given
        days = _trading_days("2016-01-01", "2026-12-31", holidays=["2018-10-01", "2020-10-01", "2020-10-02"])

        # When
        result = month_first_entries(days, month=ENTRY_MONTH)

        # Then
        assert (pd.DatetimeIndex(result[COL_DATE]).month == ENTRY_MONTH).all()

    def test_진입일은_모두_거래일이다(self) -> None:
        """
        목적: 표본 보존 — 산출된 진입일이 전부 실제 거래일임을 고정한다

        Given: 휴장이 섞인 달력
        When: 진입일을 구하면
        Then: 모든 진입일이 거래일 목록 안에 있다
        """
        # Given
        days = _trading_days("2016-01-01", "2026-12-31", holidays=["2018-10-01", "2022-10-03"])

        # When
        result = month_first_entries(days, month=ENTRY_MONTH)

        # Then
        assert result[COL_DATE].isin(days).all()

    def test_데이터의_첫_달은_빠진다(self) -> None:
        """
        목적: [중요] 경계 조건 — 데이터가 달 중간부터 시작하면 그 달의 «첫 거래일»을 알 수 없다

        Given: 2020-10-15 부터 시작하는 달력
        When: 10월 첫 거래일을 구하면
        Then: 2020년 행이 없다 — 10-15 를 첫 거래일로 삼으면 다른 매매가 된다
        """
        # Given
        days = _trading_days("2020-10-15", "2026-12-31")

        # When
        result = month_first_entries(days, month=ENTRY_MONTH)

        # Then
        assert (result[COL_CYCLE_YEAR] == 2020).sum() == 0

    def test_달을_지정하지_않으면_모든_달을_낸다(self) -> None:
        """
        목적: 기준선이 같은 함수를 쓸 수 있는지 고정한다

        Given: 1년치 달력
        When: 달을 지정하지 않고 첫 거래일을 구하면
        Then: 첫 달을 뺀 나머지 달마다 한 행이다
        """
        # Given
        days = _trading_days("2025-01-02", "2025-12-31")

        # When
        result = month_first_entries(days)

        # Then
        assert len(result) == len(pd.DatetimeIndex(days).to_period("M").unique()) - 1

    def test_뒤에_데이터가_붙어도_지난_해의_진입일은_그대로다(self) -> None:
        """
        목적: **look-ahead 감시** — 미래 거래일이 있든 없든 진입일이 같음을 고정한다

        Given: 같은 시작일에서 4년치와 11년치 달력
        When: 각각 진입일을 구하면
        Then: 짧은 쪽에 있는 모든 진입 연도의 진입일이 긴 쪽과 같다
        """
        # Given
        holidays = ["2018-10-01", "2020-10-01", "2022-10-03"]
        short_days = _trading_days("2016-01-01", "2019-12-31", holidays=holidays)
        long_days = _trading_days("2016-01-01", "2026-12-31", holidays=holidays)

        # When
        short_result = month_first_entries(short_days, month=ENTRY_MONTH)
        long_result = month_first_entries(long_days, month=ENTRY_MONTH)

        # Then
        merged = short_result.merge(long_result, on=COL_CYCLE_YEAR, suffixes=("_short", "_long"))
        assert len(merged) == len(short_result), "짧은 입력의 진입 연도가 긴 입력에 전부 있어야 합니다"
        assert (
            merged[f"{COL_DATE}_short"] == merged[f"{COL_DATE}_long"]
        ).all(), "뒤를 잘라낸 입력과 전체 입력의 진입일이 다릅니다 — 미래 데이터를 참조하고 있습니다"

    def test_거래일_목록이_비면_예외다(self) -> None:
        """
        목적: 입력 검증을 고정한다

        Given: 빈 거래일 목록
        When: 진입일을 구하면
        Then: ValueError 가 난다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="비어 있어"):
            month_first_entries(pd.DatetimeIndex([]), month=ENTRY_MONTH)

    def test_정렬되지_않은_거래일_목록은_예외다(self) -> None:
        """
        목적: 입력 검증을 고정한다

        Given: 내림차순 거래일 목록
        When: 진입일을 구하면
        Then: ValueError 가 난다
        """
        # Given
        days = pd.DatetimeIndex(_trading_days("2025-01-02", "2026-12-31")[::-1])

        # When / Then
        with pytest.raises(ValueError, match="오름차순"):
            month_first_entries(days, month=ENTRY_MONTH)

    def test_달이_범위를_벗어나면_예외다(self) -> None:
        """
        목적: 입력 검증을 고정한다

        Given: 달 13
        When: 진입일을 구하면
        Then: ValueError 가 난다
        """
        # Given
        days = _trading_days("2025-01-02", "2026-12-31")

        # When / Then
        with pytest.raises(ValueError, match="달은"):
            month_first_entries(days, month=13)


class TestMonthOffsetExitSchedule:
    """진입 달 + N개월의 «마지막 거래일» 청산 — 휴장이면 «앞당긴다»."""

    def test_목표_달의_마지막_거래일에_청산한다(self) -> None:
        """
        목적: 청산일 규칙을 고정한다

        Given: 2025-10 진입, 8개월 뒤는 2026-06 이고 그 마지막 거래일은 2026-06-30(화)이다
        When: 청산 일정을 만들면
        Then: 청산일이 2026-06-30 이다
        """
        # Given
        assert pd.Timestamp("2026-06-30").dayofweek == 1
        days = _trading_days("2025-01-02", "2026-12-31")
        entries = month_first_entries(days, month=ENTRY_MONTH)

        # When
        result = month_offset_exit_schedule(days, entries, month_offset=EXIT_MONTH_OFFSET)

        # Then
        assert _entry_of(result, 2025)[COL_EXIT_DATE] == pd.Timestamp("2026-06-30")

    def test_말일이_주말이면_직전_거래일로_앞당긴다(self) -> None:
        """
        목적: [중요] **미룸으로 구현하면 틀린다**는 것을 고정한다 — 미루면 7월로 넘어간다

        Given: 2024-06-30 은 일요일이다 (2023-10 진입의 청산 달)
        When: 청산 일정을 만들면
        Then: 2024-06-28(금) 이다 — 7월 1일이 아니다
        """
        # Given
        assert pd.Timestamp("2024-06-30").dayofweek == 6
        days = _trading_days("2023-01-02", "2024-12-31")
        entries = month_first_entries(days, month=ENTRY_MONTH)

        # When
        result = month_offset_exit_schedule(days, entries, month_offset=EXIT_MONTH_OFFSET)

        # Then
        assert _entry_of(result, 2023)[COL_EXIT_DATE] == pd.Timestamp("2024-06-28")

    def test_말일이_휴장이면_직전_거래일로_앞당긴다(self) -> None:
        """
        목적: 주말이 아닌 휴장에서도 같은 방향임을 고정한다

        Given: 2026-06-29·06-30 이 휴장인 달력
        When: 2025-10 진입의 청산 일정을 만들면
        Then: 2026-06-26(금) 이다
        """
        # Given
        days = _trading_days("2025-01-02", "2026-12-31", holidays=["2026-06-29", "2026-06-30"])
        entries = month_first_entries(days, month=ENTRY_MONTH)

        # When
        result = month_offset_exit_schedule(days, entries, month_offset=EXIT_MONTH_OFFSET)

        # Then
        assert _entry_of(result, 2025)[COL_EXIT_DATE] == pd.Timestamp("2026-06-26")

    def test_청산일은_모두_목표_달에_있다(self) -> None:
        """
        목적: [중요] 익월로 넘어가지 않음을 고정한다

        Given: 휴장이 섞인 12년치 달력
        When: 청산 일정을 만들면
        Then: 유효한 청산일이 전부 6월이다
        """
        # Given
        days = _trading_days("2015-01-01", "2026-12-31", holidays=["2020-06-30", "2024-06-28"])
        entries = month_first_entries(days, month=ENTRY_MONTH)

        # When
        result = month_offset_exit_schedule(days, entries, month_offset=EXIT_MONTH_OFFSET)

        # Then
        usable = result[result[COL_EXCLUDED_REASON] == REASON_NONE]
        assert (pd.DatetimeIndex(usable[COL_EXIT_DATE]).month == EXIT_MONTH).all()

    def test_청산_달이_데이터를_넘으면_행은_남고_사유가_붙는다(self) -> None:
        """
        목적: [중요] 표본 보존 — 값을 지어내지 않고 「진입 = 유효 + 제외」가 성립함을 고정한다

        Given: 2025-10 진입은 있는데 데이터가 2026-03 에서 끝나는 달력
        When: 청산 일정을 만들면
        Then: 2025년 행이 남아 있고 청산일이 비어 있으며 사유가 붙는다
        """
        # Given
        days = _trading_days("2024-01-01", "2026-03-31")
        entries = month_first_entries(days, month=ENTRY_MONTH)

        # When
        result = month_offset_exit_schedule(days, entries, month_offset=EXIT_MONTH_OFFSET)

        # Then
        row = _entry_of(result, 2025)
        assert pd.isna(row[COL_EXIT_DATE])
        assert row[COL_EXCLUDED_REASON] == REASON_OUT_OF_RANGE

    def test_진입_수와_행_수가_같다(self) -> None:
        """
        목적: 표본 보존 — 제외된 진입도 행으로 남음을 고정한다

        Given: 뒤가 잘린 달력
        When: 청산 일정을 만들면
        Then: 행 수가 진입 수와 같다
        """
        # Given
        days = _trading_days("2015-01-01", "2026-03-31")
        entries = month_first_entries(days, month=ENTRY_MONTH)

        # When
        result = month_offset_exit_schedule(days, entries, month_offset=EXIT_MONTH_OFFSET)

        # Then
        assert len(result) == len(entries)

    def test_보유_거래일수가_양수다(self) -> None:
        """
        목적: 경계 조건 — 청산이 진입보다 뒤임을 고정한다

        Given: 12년치 달력
        When: 청산 일정을 만들면
        Then: 유효한 행의 보유 거래일수가 전부 1 이상이다
        """
        # Given
        days = _trading_days("2015-01-01", "2026-12-31")
        entries = month_first_entries(days, month=ENTRY_MONTH)

        # When
        result = month_offset_exit_schedule(days, entries, month_offset=EXIT_MONTH_OFFSET)

        # Then
        usable = result[result[COL_EXCLUDED_REASON] == REASON_NONE]
        assert (usable[COL_HOLD_DAYS] >= 1).all()

    def test_뒤에_데이터가_붙어도_지난_해의_청산일은_그대로다(self) -> None:
        """
        목적: **look-ahead 감시** — 미래 거래일이 있든 없든 청산일이 같음을 고정한다

        Given: 같은 시작일에서 5년치와 11년치 달력
        When: 각각 청산 일정을 만들면
        Then: 짧은 쪽에서 «유효한» 행의 청산일이 긴 쪽과 같다
        """
        # Given
        holidays = ["2020-06-30", "2022-10-03"]
        short_days = _trading_days("2016-01-01", "2020-12-31", holidays=holidays)
        long_days = _trading_days("2016-01-01", "2026-12-31", holidays=holidays)

        # When
        short_result = month_offset_exit_schedule(
            short_days, month_first_entries(short_days, month=ENTRY_MONTH), month_offset=EXIT_MONTH_OFFSET
        )
        long_result = month_offset_exit_schedule(
            long_days, month_first_entries(long_days, month=ENTRY_MONTH), month_offset=EXIT_MONTH_OFFSET
        )

        # Then
        usable = short_result[short_result[COL_EXCLUDED_REASON] == REASON_NONE]
        merged = usable.merge(long_result, on=COL_CYCLE_YEAR, suffixes=("_short", "_long"))
        assert len(merged) == len(usable), "짧은 입력의 진입 연도가 긴 입력에 전부 있어야 합니다"
        assert (
            merged[f"{COL_EXIT_DATE}_short"] == merged[f"{COL_EXIT_DATE}_long"]
        ).all(), "뒤를 잘라낸 입력과 전체 입력의 청산일이 다릅니다 — 미래 데이터를 참조하고 있습니다"

    def test_진입_표에_필수_컬럼이_없으면_예외다(self) -> None:
        """
        목적: 입력 검증을 고정한다

        Given: 컬럼이 모자란 진입 표
        When: 청산 일정을 만들면
        Then: ValueError 가 난다
        """
        # Given
        days = _trading_days("2025-01-02", "2026-12-31")
        entries = month_first_entries(days, month=ENTRY_MONTH).drop(columns=[COL_MONTH])

        # When / Then
        with pytest.raises(ValueError, match="필수 컬럼"):
            month_offset_exit_schedule(days, entries, month_offset=EXIT_MONTH_OFFSET)


class TestCycleReturns:
    """일정에 가격을 붙여 수익률을 낸다."""

    def test_수익률은_진입_종가_대비_청산_종가다(self) -> None:
        """
        목적: 산식 고정 — 손으로 계산한 값을 박아 둔다

        Given: 진입 종가 100, 청산 종가 120 이 되도록 만든 가격 데이터
        When: 수익률을 내면
        Then: 0.2 다
        """
        # Given
        days = _trading_days("2025-01-02", "2026-12-31")
        frame = _prices(days, values=[100.0] * len(days))
        entries = month_first_entries(days, month=ENTRY_MONTH)
        schedule = month_offset_exit_schedule(days, entries, month_offset=EXIT_MONTH_OFFSET)
        exit_date = _entry_of(schedule, 2025)[COL_EXIT_DATE]
        frame.loc[frame[COL_DATE] == exit_date, COL_CLOSE] = 120.0

        # When
        result = cycle_returns(frame, schedule, horizon=HORIZON_POOLED, price_column=COL_CLOSE)

        # Then
        row = _entry_of(result, 2025)
        assert row[COL_ENTRY_CLOSE] == pytest.approx(100.0, abs=1e-12)
        assert row[COL_EXIT_CLOSE] == pytest.approx(120.0, abs=1e-12)
        assert row[COL_FORWARD_RETURN] == pytest.approx(0.2, abs=1e-12)

    def test_제외된_진입은_값이_비고_행은_남는다(self) -> None:
        """
        목적: 표본 보존 — 행을 지우지 않음을 고정한다

        Given: 청산 달이 데이터를 넘는 진입이 있는 달력
        When: 수익률을 내면
        Then: 그 행의 수익률이 비어 있고 행 수는 진입 수와 같다
        """
        # Given
        days = _trading_days("2024-01-01", "2026-03-31")
        frame = _prices(days)
        entries = month_first_entries(days, month=ENTRY_MONTH)
        schedule = month_offset_exit_schedule(days, entries, month_offset=EXIT_MONTH_OFFSET)

        # When
        result = cycle_returns(frame, schedule, horizon=HORIZON_POOLED, price_column=COL_CLOSE)

        # Then
        assert len(result) == len(schedule)
        assert pd.isna(_entry_of(result, 2025)[COL_FORWARD_RETURN])

    def test_사이클_위치가_행에_실린다(self) -> None:
        """
        목적: 축이 산출물까지 이어짐을 고정한다

        Given: 2022(중간선거해)·2023(대선전해) 진입이 있는 달력
        When: 수익률을 내면
        Then: 각 행의 사이클 위치가 맞다
        """
        # Given
        days = _trading_days("2021-01-01", "2026-12-31")
        frame = _prices(days)
        entries = month_first_entries(days, month=ENTRY_MONTH)
        schedule = month_offset_exit_schedule(days, entries, month_offset=EXIT_MONTH_OFFSET)

        # When
        result = cycle_returns(frame, schedule, horizon=HORIZON_POOLED, price_column=COL_CLOSE)

        # Then
        assert _entry_of(result, 2022)[COL_CYCLE_POSITION] == CYCLE_MIDTERM
        assert _entry_of(result, 2023)[COL_CYCLE_POSITION] == CYCLE_PRE_ELECTION

    def test_가격_컬럼이_없으면_예외다(self) -> None:
        """
        목적: 입력 검증을 고정한다

        Given: 종가 컬럼이 없는 가격 데이터
        When: 수익률을 내면
        Then: ValueError 가 난다
        """
        # Given
        days = _trading_days("2025-01-02", "2026-12-31")
        frame = _prices(days).drop(columns=[COL_CLOSE])
        entries = month_first_entries(days, month=ENTRY_MONTH)
        schedule = month_offset_exit_schedule(days, entries, month_offset=EXIT_MONTH_OFFSET)

        # When / Then
        with pytest.raises(ValueError):
            cycle_returns(frame, schedule, horizon=HORIZON_POOLED, price_column=COL_CLOSE)
