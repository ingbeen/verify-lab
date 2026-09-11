"""검증 #10 의 월 하순 진입과 말일 기준 청산을 고정한다.

진입일·청산일 판정은 **이 검증의 결과를 통째로 정하는 정의**다. 틀려도 예외가 나지 않고
숫자만 조용히 달라지므로 구현보다 먼저 고정한다.

고정하는 계약은 여덟이다.

- 목표 달력일이 거래일이면 그날이 진입일이다
- 목표 달력일이 휴장이면 **직전 거래일로 앞당긴다** (`docs/spec/월말_진입_설계.md` 결정 ①)
- **데이터의 마지막 달에는 진입일을 만들지 않는다** (결정 ⑧) — 그 달의 「말일」은
  실제 월말이 아니라 데이터가 끊긴 지점이라 보유 0 의 가짜 표본이 된다
- 청산 상대 거래일 0 은 그 달 마지막 거래일, +1 은 익월 첫 거래일이다 (결정 ②)
- 청산이 진입보다 뒤가 아니면 값을 비우고 사유를 남긴다 (결정 ④)
- 청산이 데이터 끝을 넘으면 값을 지어내지 않는다
- 진입 수 = 유효 표본 + 제외 표본 (표본 보존)
- 뒤에 데이터가 더 붙어도 이미 확정된 달의 판정이 달라지지 않는다 (look-ahead 감시)
"""

from collections.abc import Callable, Sequence

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_EXCLUDED_REASON,
    COL_FORWARD_RETURN,
    COL_HORIZON,
    REASON_NONE,
    REASON_OUT_OF_RANGE,
)
from verify_lab.studies.month_end.constants import (
    COL_ENTRY_CLOSE,
    COL_EXIT_CLOSE,
    COL_EXIT_DATE,
    COL_HOLD_DAYS,
    COL_MONTH,
    COL_MONTH_LAST_DATE,
    COL_TARGET_DAY,
    HORIZON_MONTH_END,
    REASON_NO_ENTRY_DAY,
    REASON_NO_HOLDING,
)
from verify_lab.studies.month_end.schedule import (
    MonthExitSchedule,
    month_entry_dates,
    month_exit_returns,
    month_exit_schedule,
)

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12

# 원 매매법의 진입 달력일. 격자의 가운데 값이다
ENTRY_DAY_20 = 20


def _trading_days(start: str, end: str, holidays: Sequence[str] = ()) -> pd.DatetimeIndex:
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


def _market(days: pd.DatetimeIndex, closes: Sequence[float] | None = None) -> pd.DataFrame:
    """합성 시세를 만든다. 이 매매는 날짜와 종가만 보므로 나머지 가격은 종가와 같게 둔다.

    Args:
        days: 거래일 목록
        closes: 종가 목록. `None` 이면 100 부터 1씩 오른다

    Returns:
        시세 DataFrame
    """
    prices = list(closes) if closes is not None else [100.0 + index for index in range(len(days))]

    return pd.DataFrame(
        {
            COL_DATE: days,
            COL_OPEN: prices,
            COL_HIGH: prices,
            COL_LOW: prices,
            COL_CLOSE: prices,
            COL_VOLUME: [1_000] * len(prices),
        }
    )


def _schedule(days: pd.DatetimeIndex, calendar_day: int, exit_offset: int) -> MonthExitSchedule:
    """진입·청산 일정을 한 번에 만든다.

    Args:
        days: 거래일 목록
        calendar_day: 목표 진입 달력일
        exit_offset: 그 달 마지막 거래일 기준 상대 거래일

    Returns:
        청산 일정
    """
    entries = month_entry_dates(days, calendar_day=calendar_day)

    return month_exit_schedule(days, entries, exit_offset=exit_offset)


def _entry_on(frame: pd.DataFrame, month: str) -> pd.Series:
    """지정한 달의 행 하나를 꺼낸다.

    Args:
        frame: 진입일 또는 청산 일정 프레임
        month: 연월 (`YYYY-MM`)

    Returns:
        그 달의 행
    """
    matched = frame[frame[COL_MONTH] == pd.Timestamp(f"{month}-01")]
    assert len(matched) == 1, f"{month} 행이 하나가 아닙니다: {len(matched)}개"

    return matched.iloc[0]


class TestMonthEntryDates:
    """진입일 판정 — 목표 달력일과 앞당김"""

    def test_target_day_that_is_a_trading_day_becomes_the_entry(self) -> None:
        """
        목적: 목표 달력일이 거래일이면 그날이 진입일임을 고정한다.

        Given: 2024-02-20 은 화요일이라 거래일이다
        When: 20일 진입일을 구한다
        Then: 진입일이 2024-02-20 이다
        """
        # Given
        days = _trading_days("2024-01-01", "2024-06-28")

        # When
        entries = month_entry_dates(days, calendar_day=ENTRY_DAY_20)

        # Then
        assert _entry_on(entries, "2024-02")[COL_DATE] == pd.Timestamp("2024-02-20")

    def test_target_day_on_a_weekend_falls_back_to_the_previous_trading_day(self) -> None:
        """
        목적: 목표 달력일이 휴장이면 **직전 거래일로 앞당긴다**를 고정한다 (결정 ①).

        Given: 2024-01-20 은 토요일이다
        When: 20일 진입일을 구한다
        Then: 진입일이 직전 거래일인 2024-01-19(금) 이다
        """
        # Given
        days = _trading_days("2024-01-01", "2024-06-28")

        # When
        entries = month_entry_dates(days, calendar_day=ENTRY_DAY_20)

        # Then
        assert _entry_on(entries, "2024-01")[COL_DATE] == pd.Timestamp("2024-01-19")

    def test_target_day_on_a_holiday_falls_back_to_the_previous_trading_day(self) -> None:
        """
        목적: 주말이 아닌 휴장일에서도 앞당김이 동작함을 고정한다.

        Given: 2024-02-20(화)과 2024-02-19(월)이 모두 휴장이다
        When: 20일 진입일을 구한다
        Then: 진입일이 2024-02-16(금) 이다 — 이틀을 거슬러 올라간다
        """
        # Given
        days = _trading_days("2024-01-01", "2024-06-28", holidays=["2024-02-19", "2024-02-20"])

        # When
        entries = month_entry_dates(days, calendar_day=ENTRY_DAY_20)

        # Then
        assert _entry_on(entries, "2024-02")[COL_DATE] == pd.Timestamp("2024-02-16")

    def test_entry_never_crosses_into_the_previous_month(self) -> None:
        """
        목적: 앞당김이 **그 달 안에서만** 일어남을 고정한다.

        Given: 2024-02 의 1~20일이 전부 휴장이라 목표일 이전 거래일이 없다
        When: 20일 진입일을 구한다
        Then: 행은 남고 진입일이 비며 사유가 붙는다 (전월로 넘어가지 않는다)
        """
        # Given
        february = pd.bdate_range("2024-02-01", "2024-02-20").strftime("%Y-%m-%d").tolist()
        days = _trading_days("2024-01-01", "2024-06-28", holidays=february)

        # When
        entries = month_entry_dates(days, calendar_day=ENTRY_DAY_20)

        # Then
        row = _entry_on(entries, "2024-02")
        assert pd.isna(row[COL_DATE])
        assert row[COL_EXCLUDED_REASON] == REASON_NO_ENTRY_DAY

    def test_last_month_of_data_gets_no_row(self) -> None:
        """
        목적: **데이터의 마지막 달을 제외**함을 고정한다 (결정 ⑧).

        그 달이 진행 중이면 「말일」이 실제 월말이 아니라 데이터가 끊긴 지점이다.
        앞당김 방식에서는 진입일과 청산일이 같은 날이 되어 보유 0 의 가짜 표본이 생긴다.

        Given: 거래일이 2024-06-05 에서 끝난다 (6월 중간)
        When: 20일 진입일을 구한다
        Then: 2024-06 행이 없고, 직전 달인 2024-05 는 남는다
        """
        # Given
        days = _trading_days("2024-01-01", "2024-06-05")

        # When
        entries = month_entry_dates(days, calendar_day=ENTRY_DAY_20)

        # Then
        months = set(entries[COL_MONTH])
        assert pd.Timestamp("2024-06-01") not in months
        assert pd.Timestamp("2024-05-01") in months

    def test_target_day_is_recorded_on_every_row(self) -> None:
        """
        목적: 격자 축인 목표 달력일이 산출물에 남음을 고정한다.

        Given: 25일을 목표로 한다
        When: 진입일을 구한다
        Then: 모든 행의 목표 달력일이 25 다
        """
        # Given
        days = _trading_days("2024-01-01", "2024-06-28")

        # When
        entries = month_entry_dates(days, calendar_day=25)

        # Then
        assert set(entries[COL_TARGET_DAY]) == {25}

    @pytest.mark.parametrize("calendar_day", [0, 32, -1])
    def test_invalid_calendar_day_raises(self, calendar_day: int) -> None:
        """
        목적: 달력일 범위 검증을 고정한다.

        Given: 달력일이 1~31 밖이다
        When: 진입일을 구한다
        Then: ValueError 가 난다
        """
        # Given
        days = _trading_days("2024-01-01", "2024-06-28")

        # When / Then
        with pytest.raises(ValueError, match="달력일"):
            month_entry_dates(days, calendar_day=calendar_day)

    def test_empty_trading_days_raises(self) -> None:
        """
        목적: 빈 거래일 목록을 거부함을 고정한다.

        Given: 거래일이 하나도 없다
        When: 진입일을 구한다
        Then: ValueError 가 난다
        """
        # Given
        days = pd.DatetimeIndex([])

        # When / Then
        with pytest.raises(ValueError, match="거래일"):
            month_entry_dates(days, calendar_day=ENTRY_DAY_20)


class TestMonthExitSchedule:
    """청산일 판정 — 말일 기준 상대 거래일"""

    def test_offset_zero_is_the_last_trading_day_of_the_month(self) -> None:
        """
        목적: 상대 거래일 0 이 그 달 마지막 거래일임을 고정한다 (결정 ②).

        Given: 2024-03-31 은 일요일이라 3월 마지막 거래일은 2024-03-29(금) 이다
        When: 상대 거래일 0 으로 청산 일정을 만든다
        Then: 청산일이 2024-03-29 다
        """
        # Given
        days = _trading_days("2024-01-01", "2024-06-28")

        # When
        schedule = _schedule(days, ENTRY_DAY_20, exit_offset=0)

        # Then
        row = _entry_on(schedule.frame, "2024-03")
        assert row[COL_EXIT_DATE] == pd.Timestamp("2024-03-29")
        assert row[COL_MONTH_LAST_DATE] == pd.Timestamp("2024-03-29")

    def test_positive_offset_crosses_into_the_next_month(self) -> None:
        """
        목적: 양수 상대 거래일이 익월로 넘어감을 고정한다.

        Given: 3월 마지막 거래일이 2024-03-29(금) 이다
        When: 상대 거래일 +1 로 청산 일정을 만든다
        Then: 청산일이 익월 첫 거래일인 2024-04-01(월) 이다
        """
        # Given
        days = _trading_days("2024-01-01", "2024-06-28")

        # When
        schedule = _schedule(days, ENTRY_DAY_20, exit_offset=1)

        # Then
        assert _entry_on(schedule.frame, "2024-03")[COL_EXIT_DATE] == pd.Timestamp("2024-04-01")

    def test_negative_offset_moves_before_the_month_end(self) -> None:
        """
        목적: 음수 상대 거래일이 말일 이전으로 감을 고정한다.

        Given: 1월 마지막 거래일이 2024-01-31(수) 이다
        When: 상대 거래일 −1 로 청산 일정을 만든다
        Then: 청산일이 2024-01-30(화) 이다
        """
        # Given
        days = _trading_days("2024-01-01", "2024-06-28")

        # When
        schedule = _schedule(days, ENTRY_DAY_20, exit_offset=-1)

        # Then
        assert _entry_on(schedule.frame, "2024-01")[COL_EXIT_DATE] == pd.Timestamp("2024-01-30")

    def test_hold_days_count_trading_days(self) -> None:
        """
        목적: 보유일이 **거래일 수**임을 고정한다 (달력일이 아니다).

        Given: 2024-02 진입일은 2/20(화), 2월 마지막 거래일은 2/29(목) 이다
        When: 상대 거래일 0 으로 청산 일정을 만든다
        Then: 보유가 7거래일이다 (2/21·22·23·26·27·28·29)
        """
        # Given
        days = _trading_days("2024-01-01", "2024-06-28")

        # When
        schedule = _schedule(days, ENTRY_DAY_20, exit_offset=0)

        # Then
        assert _entry_on(schedule.frame, "2024-02")[COL_HOLD_DAYS] == 7

    def test_exit_not_after_entry_is_excluded(self) -> None:
        """
        목적: 청산이 진입보다 뒤가 아니면 제외함을 고정한다 (결정 ④).

        Given: 25일 진입에 상대 거래일 −5 라 청산이 진입보다 앞선다
        When: 청산 일정을 만든다
        Then: 그런 달의 청산일이 비고 사유가 붙는다
        """
        # Given
        days = _trading_days("2024-01-01", "2024-06-28")

        # When
        schedule = _schedule(days, 25, exit_offset=-5)

        # Then
        excluded = schedule.frame[schedule.frame[COL_EXCLUDED_REASON] == REASON_NO_HOLDING]
        assert not excluded.empty, "청산이 진입보다 앞서는 달이 하나도 걸리지 않았습니다"
        assert excluded[COL_EXIT_DATE].isna().all()

    def test_exit_beyond_data_end_is_excluded(self) -> None:
        """
        목적: 청산이 데이터 끝을 넘으면 값을 지어내지 않음을 고정한다.

        Given: 데이터가 2024-05-02 에서 끝나고 상대 거래일이 +3 이다
        When: 청산 일정을 만든다
        Then: 마지막 판정 대상 달(2024-04)이 범위 초과로 제외된다
        """
        # Given
        # 5월은 데이터 마지막 달이라 결정 ⑧ 으로 이미 빠진다. 4월 마지막 거래일(4/30)에서
        # 3거래일째는 5/3 인데 데이터가 5/2 에서 끊긴다
        days = _trading_days("2024-01-01", "2024-05-02")

        # When
        schedule = _schedule(days, ENTRY_DAY_20, exit_offset=3)

        # Then
        assert _entry_on(schedule.frame, "2024-04")[COL_EXCLUDED_REASON] == REASON_OUT_OF_RANGE

    def test_sample_is_preserved(self) -> None:
        """
        목적: **진입 수 = 유효 + 제외** 를 고정한다 (표본 보존).

        Given: 제외가 섞이는 설정이다
        When: 청산 일정을 만든다
        Then: 유효 행과 제외 행의 합이 전체 행 수와 같다
        """
        # Given
        days = _trading_days("2024-01-01", "2024-06-28")

        # When
        schedule = _schedule(days, 25, exit_offset=-3)

        # Then
        valid = (schedule.frame[COL_EXCLUDED_REASON] == REASON_NONE).sum()
        excluded = (schedule.frame[COL_EXCLUDED_REASON] != REASON_NONE).sum()
        assert valid + excluded == len(schedule.frame)
        assert schedule.entry_count == len(schedule.frame)

    def test_entry_without_a_day_keeps_its_reason(self) -> None:
        """
        목적: 진입일이 없던 행의 사유가 청산 단계에서 덮이지 않음을 고정한다.

        Given: 2024-02 에 목표일 이전 거래일이 없다
        When: 청산 일정을 만든다
        Then: 그 행의 사유가 그대로 「진입일 없음」이다
        """
        # Given
        february = pd.bdate_range("2024-02-01", "2024-02-20").strftime("%Y-%m-%d").tolist()
        days = _trading_days("2024-01-01", "2024-06-28", holidays=february)

        # When
        schedule = _schedule(days, ENTRY_DAY_20, exit_offset=0)

        # Then
        assert _entry_on(schedule.frame, "2024-02")[COL_EXCLUDED_REASON] == REASON_NO_ENTRY_DAY


class TestMonthExitReturns:
    """수익률 산식과 원자료"""

    def test_return_is_exit_close_over_entry_close(self) -> None:
        """
        목적: 수익률이 `청산 종가 ÷ 진입 종가 − 1` 임을 고정한다.

        Given: 종가가 100 부터 1씩 오르는 시세다
        When: 수익률을 낸다
        Then: 손으로 계산한 값과 같다
        """
        # Given
        days = _trading_days("2024-01-01", "2024-06-28")
        market = _market(days)
        schedule = _schedule(days, ENTRY_DAY_20, exit_offset=0)

        # When
        returns = month_exit_returns(market, schedule)

        # Then
        row = _entry_on(returns, "2024-02")
        expected = row[COL_EXIT_CLOSE] / row[COL_ENTRY_CLOSE] - 1.0
        assert row[COL_FORWARD_RETURN] == pytest.approx(expected, abs=EXACT_TOLERANCE)

    def test_prices_are_kept_for_manual_verification(self) -> None:
        """
        목적: 사용자가 차트로 대조할 원자료가 남음을 고정한다 (측정의 원칙 8).

        Given: 합성 시세다
        When: 수익률을 낸다
        Then: 진입가·청산가가 시세의 종가와 일치한다
        """
        # Given
        days = _trading_days("2024-01-01", "2024-06-28")
        market = _market(days)
        closes = market.set_index(COL_DATE)[COL_CLOSE]
        schedule = _schedule(days, ENTRY_DAY_20, exit_offset=0)

        # When
        returns = month_exit_returns(market, schedule)

        # Then
        row = _entry_on(returns, "2024-03")
        assert row[COL_ENTRY_CLOSE] == closes[row[COL_DATE]]
        assert row[COL_EXIT_CLOSE] == closes[row[COL_EXIT_DATE]]

    def test_excluded_rows_stay_with_empty_values(self) -> None:
        """
        목적: 제외된 행이 사라지지 않음을 고정한다 (표본 보존).

        Given: 제외가 섞이는 설정이다
        When: 수익률을 낸다
        Then: 행 수가 진입 수와 같고 제외 행의 수익률이 비어 있다
        """
        # Given
        days = _trading_days("2024-01-01", "2024-06-28")
        market = _market(days)
        schedule = _schedule(days, 25, exit_offset=-3)

        # When
        returns = month_exit_returns(market, schedule)

        # Then
        assert len(returns) == schedule.entry_count
        excluded = returns[returns[COL_EXCLUDED_REASON] != REASON_NONE]
        assert excluded[COL_FORWARD_RETURN].isna().all()

    def test_horizon_carries_a_single_label(self) -> None:
        """
        목적: 구간 축이 **보유일수가 아니라 표지 하나**임을 고정한다.

        보유일수를 넣으면 한 매매가 길이별 여러 칸으로 쪼개져 묶음 값이 나오지 않는다.

        Given: 보유가 달마다 다른 시세다
        When: 수익률을 낸다
        Then: 구간 축의 값이 하나뿐이다
        """
        # Given
        days = _trading_days("2024-01-01", "2024-06-28")
        market = _market(days)
        schedule = _schedule(days, ENTRY_DAY_20, exit_offset=0)

        # When
        returns = month_exit_returns(market, schedule)

        # Then
        assert set(returns[COL_HORIZON]) == {HORIZON_MONTH_END}
        assert returns[COL_HOLD_DAYS].nunique() > 1, "보유일이 하나뿐이면 이 계약을 검사하지 못합니다"

    def test_basis_is_close_only(self) -> None:
        """
        목적: 기준이 **종가 하나**임을 고정한다.

        이 매매의 정의가 "20일 종가 매수 → 말일 종가 매도"이며 익일 시가 진입은 다른 매매다.

        Given: 합성 시세다
        When: 수익률을 낸다
        Then: 기준 축의 값이 하나뿐이다
        """
        # Given
        days = _trading_days("2024-01-01", "2024-06-28")
        market = _market(days)
        schedule = _schedule(days, ENTRY_DAY_20, exit_offset=0)

        # When
        returns = month_exit_returns(market, schedule)

        # Then
        assert returns[COL_BASIS].nunique() == 1


class TestLookAhead:
    """look-ahead 감시 — 미래 데이터가 판정을 바꾸지 않는다"""

    def test_judgement_is_stable_under_truncation(self, assert_stable_under_truncation: Callable[..., None]) -> None:
        """
        목적: **look-ahead 감시** — 뒤에 데이터가 더 붙어도 이미 확정된 달의 값이
        달라지면 안 된다.

        Given: 6개월치 합성 시세와 그 앞부분만 잘라낸 입력
        When: 두 입력으로 각각 수익률을 낸다
        Then: 겹치는 달의 값이 같다
        """
        # Given
        days = _trading_days("2024-01-01", "2024-06-28")
        market = _market(days)

        def run(frame: pd.DataFrame) -> pd.DataFrame:
            trading_days = pd.DatetimeIndex(frame[COL_DATE])
            schedule = _schedule(trading_days, ENTRY_DAY_20, exit_offset=0)

            return month_exit_returns(frame, schedule)

        # When / Then
        assert_stable_under_truncation(
            run,
            market,
            cut=len(market) - 40,
            key_columns=[COL_MONTH],
            value_column=COL_FORWARD_RETURN,
        )
