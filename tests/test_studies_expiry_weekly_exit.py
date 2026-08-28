"""검증 #7 의 달력 기준 청산(만기일 매수 → 다음주 금요일 매도)을 고정한다.

이 매매는 **청산이 달력 기준**이라 보유 거래일 수가 신호마다 다르다. 고정 구간으로 재면
미국의 4분의 1이 틀린 값이 된다 — 만기 다음 주에 휴장이 잦기 때문이다
(`docs/spec/option_expiry.md` 결정 ⑯).

고정하는 계약은 여섯이다.
- 목표일은 **주 기준일이 속한 주**의 다음 주 지정 요일이다 (만기 진입에서는 규칙일이 주 기준일이다)
- 목표일이 거래일이 아니면 **직전 거래일**에 청산한다
- 목표일이 데이터 끝을 넘으면 값을 지어내지 않고 **제외하며 사유를 남긴다**
- 뒤에 데이터가 더 붙어도 이미 확정된 진입일의 청산 판정이 달라지지 않는다 (look-ahead 감시)
- 진입 수 = 유효 표본 + 제외 표본 (표본 보존)
- 수익률은 `청산 종가 ÷ 진입 종가 − 1` 이다
"""

from collections.abc import Sequence

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
from verify_lab.studies.option_expiry.constants import (
    COL_EXIT_DATE,
    COL_EXPIRY_DATE,
    COL_HOLD_DAYS,
    COL_RULE_DATE,
    COL_TARGET_DATE,
    COL_WEEK_REFERENCE,
    FRIDAY,
    HORIZON_NEXT_WEEK_EXIT,
    KR_MONTHLY_EXPIRY,
    THURSDAY,
    US_MONTHLY_EXPIRY,
    ExpiryRule,
)
from verify_lab.studies.option_expiry.expiry_calendar import monthly_expiry_dates
from verify_lab.studies.option_expiry.weekly_exit import (
    HolidayExit,
    WeeklyExitSchedule,
    weekly_exit_returns,
    weekly_exit_schedule,
)

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12


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


def _expiry_schedule(days: pd.DatetimeIndex, rule: ExpiryRule, exit_weekday: int) -> WeeklyExitSchedule:
    """만기일 진입의 청산 일정을 만든다.

    진입일은 만기일이고 주 기준일은 **규칙일**이다 (`docs/spec/option_expiry.md` 결정 ⑰).

    Args:
        days: 거래일 목록
        rule: 만기 달력 규칙
        exit_weekday: 청산 요일 (월=0 ~ 일=6)

    Returns:
        청산 일정
    """
    expiries = monthly_expiry_dates(days, rule)

    return weekly_exit_schedule(
        days,
        pd.DatetimeIndex(expiries[COL_EXPIRY_DATE]),
        pd.DatetimeIndex(expiries[COL_RULE_DATE]),
        exit_weekday=exit_weekday,
    )


def _row_for(frame: pd.DataFrame, entry: str) -> pd.Series:
    """청산 일정표에서 지정한 진입일의 행을 꺼낸다."""
    rows = frame[frame[COL_DATE] == pd.Timestamp(entry)]
    assert len(rows) == 1, f"{entry} 의 행이 1개가 아닙니다: {len(rows)}개"

    return rows.iloc[0]


class TestTargetDate:
    """청산 목표일이 어느 주에서 나오는지 고정한다."""

    def test_주_기준일이_속한_주의_다음주_금요일이_목표일이다(self) -> None:
        """
        목적: 목표일의 정의를 고정한다

        Given: 2026-07 (셋째 금요일 2026-07-17), 휴장 없음
        When: 미국 규칙으로 청산 일정을 만들면
        Then: 목표일이 2026-07-24 이고 보유가 5거래일이다
        """
        # Given
        days = _trading_days("2026-06-01", "2026-08-31")

        # When
        schedule = _expiry_schedule(days, US_MONTHLY_EXPIRY, FRIDAY)

        # Then
        row = _row_for(schedule.frame, "2026-07-17")
        assert row[COL_TARGET_DATE] == pd.Timestamp("2026-07-24")
        assert row[COL_EXIT_DATE] == pd.Timestamp("2026-07-24")
        assert int(row[COL_HOLD_DAYS]) == 5

    def test_미국_굿프라이데이로_만기가_밀려도_목표일은_그대로다(self) -> None:
        """
        목적: **앞당김은 만기 쪽 사정이고 목표 주는 흔들리지 않음**을 고정한다

        미국은 앞당겨도 같은 주 안이므로 규칙일 기준과 실제 만기일 기준이 같은 답을 낸다.

        Given: 2022-04-15(셋째 금요일, Good Friday)가 휴장인 달력
        When: 청산 일정을 만들면
        Then: 진입은 2022-04-14 이지만 주 기준일은 규칙일 2022-04-15 이고 목표일은 2022-04-22 다
        """
        # Given
        days = _trading_days("2022-03-01", "2022-05-31", holidays=["2022-04-15"])

        # When
        schedule = _expiry_schedule(days, US_MONTHLY_EXPIRY, FRIDAY)

        # Then
        row = _row_for(schedule.frame, "2022-04-14")
        assert row[COL_WEEK_REFERENCE] == pd.Timestamp("2022-04-15")
        assert row[COL_TARGET_DATE] == pd.Timestamp("2022-04-22")
        assert int(row[COL_HOLD_DAYS]) == 5

    def test_한국_추석_앞당김_달도_보유가_유지된다(self) -> None:
        """
        목적: **탈락안이 왜 탈락인지**를 고정한다 (`docs/spec/option_expiry.md` 결정 ⑰)

        규칙일 2025-10-09 이 추석으로 10-02 까지 7 달력일 앞당겨진 달이다.
        실제 만기일(10-02)이 속한 주로 세면 목표가 10-10 이 되어 연휴에 막혀 **보유 1거래일**이
        된다. 규칙일 기준으로 세면 10-17 이라 보유 6거래일이 유지된다.

        Given: 2025-10-03 ~ 10-09 가 전부 휴장인 달력
        When: 한국 규칙으로 금요일 청산 일정을 만들면
        Then: 진입 2025-10-02, 주 기준일 2025-10-09, 목표일 2025-10-17, 보유 6거래일이다
        """
        # Given
        days = _trading_days(
            "2025-09-01",
            "2025-11-28",
            holidays=["2025-10-03", "2025-10-06", "2025-10-07", "2025-10-08", "2025-10-09"],
        )

        # When
        schedule = _expiry_schedule(days, KR_MONTHLY_EXPIRY, FRIDAY)

        # Then
        row = _row_for(schedule.frame, "2025-10-02")
        assert row[COL_WEEK_REFERENCE] == pd.Timestamp("2025-10-09")
        assert row[COL_TARGET_DATE] == pd.Timestamp("2025-10-17")
        assert int(row[COL_HOLD_DAYS]) == 6

    def test_실제_만기일을_주_기준으로_쓰면_보유가_무너진다(self) -> None:
        """
        목적: 탈락안의 결과를 **수치로** 고정한다 — 왜 규칙일 기준을 골랐는지의 근거다

        Given: 같은 추석 달력에서 주 기준일을 실제 만기일로 준다
        When: 청산 일정을 만들면
        Then: 목표일이 2025-10-10 이고 보유가 1거래일로 무너진다
        """
        # Given
        days = _trading_days(
            "2025-09-01",
            "2025-11-28",
            holidays=["2025-10-03", "2025-10-06", "2025-10-07", "2025-10-08", "2025-10-09"],
        )
        expiries = monthly_expiry_dates(days, KR_MONTHLY_EXPIRY)
        entries = pd.DatetimeIndex(expiries[COL_EXPIRY_DATE])

        # When
        schedule = weekly_exit_schedule(days, entries, entries, exit_weekday=FRIDAY)

        # Then
        row = _row_for(schedule.frame, "2025-10-02")
        assert row[COL_TARGET_DATE] == pd.Timestamp("2025-10-10")
        assert int(row[COL_HOLD_DAYS]) == 1

    def test_한국_목요일_청산은_하루_짧다(self) -> None:
        """
        목적: 청산 요일이 인자로 갈리는 것을 고정한다 (결정 ⑳)

        Given: 휴장 없는 2026-07 (둘째 목요일 2026-07-09)
        When: 목요일 청산과 금요일 청산으로 각각 일정을 만들면
        Then: 목요일 청산이 5거래일, 금요일 청산이 6거래일이다
        """
        # Given
        days = _trading_days("2026-06-01", "2026-08-31")

        # When
        thursday_exit = _expiry_schedule(days, KR_MONTHLY_EXPIRY, THURSDAY)
        friday_exit = _expiry_schedule(days, KR_MONTHLY_EXPIRY, FRIDAY)

        # Then
        thursday_row = _row_for(thursday_exit.frame, "2026-07-09")
        assert thursday_row[COL_TARGET_DATE] == pd.Timestamp("2026-07-16")
        assert int(thursday_row[COL_HOLD_DAYS]) == 5
        assert int(_row_for(friday_exit.frame, "2026-07-09")[COL_HOLD_DAYS]) == 6


class TestHolidayAndRange:
    """청산 쪽 휴장과 데이터 범위 처리를 고정한다."""

    def test_목표일이_휴장이면_직전_거래일에_청산한다(self) -> None:
        """
        목적: 청산 휴장 규칙을 고정한다 (결정 ⑱)

        Given: 목표일 2026-07-24(금)가 휴장인 달력
        When: 청산 일정을 만들면
        Then: 청산일이 2026-07-23(목)이고 보유가 4거래일이다
        """
        # Given
        days = _trading_days("2026-06-01", "2026-08-31", holidays=["2026-07-24"])

        # When
        schedule = _expiry_schedule(days, US_MONTHLY_EXPIRY, FRIDAY)

        # Then
        row = _row_for(schedule.frame, "2026-07-17")
        assert row[COL_TARGET_DATE] == pd.Timestamp("2026-07-24"), "목표일 자체는 달력값 그대로 남아야 합니다"
        assert row[COL_EXIT_DATE] == pd.Timestamp("2026-07-23")
        assert int(row[COL_HOLD_DAYS]) == 4

    def test_다음_거래일_규칙은_휴장일_때만_갈린다(self) -> None:
        """
        목적: 대조 규칙의 계약을 고정한다 (결정 ⑱·㉔)

        목표일이 거래일이면 두 규칙이 같은 답을 내야 한다. 그래야 네 조합 대조표의 차이가
        **오직 휴장 달에서만** 나온다고 읽을 수 있다.

        Given: 목표일 2026-07-24(금)만 휴장인 달력
        When: 두 휴장 규칙으로 각각 일정을 만들면
        Then: 그 달만 청산일이 갈리고(23일 대 27일) 나머지 달은 같다
        """
        # Given
        days = _trading_days("2026-06-01", "2026-08-31", holidays=["2026-07-24"])
        expiries = monthly_expiry_dates(days, US_MONTHLY_EXPIRY)
        entries = pd.DatetimeIndex(expiries[COL_EXPIRY_DATE])
        references = pd.DatetimeIndex(expiries[COL_RULE_DATE])

        # When
        previous = weekly_exit_schedule(days, entries, references, exit_weekday=FRIDAY)
        following = weekly_exit_schedule(days, entries, references, exit_weekday=FRIDAY, on_holiday=HolidayExit.NEXT)

        # Then
        assert _row_for(previous.frame, "2026-07-17")[COL_EXIT_DATE] == pd.Timestamp("2026-07-23")
        assert _row_for(following.frame, "2026-07-17")[COL_EXIT_DATE] == pd.Timestamp("2026-07-27")

        merged = previous.frame.merge(following.frame, on=COL_DATE, suffixes=("_prev", "_next"))
        untouched = merged[merged[COL_DATE] != pd.Timestamp("2026-07-17")]
        assert (untouched[f"{COL_EXIT_DATE}_prev"] == untouched[f"{COL_EXIT_DATE}_next"]).all(), "목표일이 거래일인 달까지 갈렸습니다"

    def test_목표일이_데이터_끝을_넘으면_제외하고_사유를_남긴다(self) -> None:
        """
        목적: **값을 지어내지 않음**을 고정한다 (결정 ⑲)

        있는 데이터까지 잡으면 보유 기간이 다른 표본이 같은 평균에 섞인다.

        Given: 만기일 다음 3거래일에서 끝나는 달력
        When: 청산 일정을 만들면
        Then: 그 행이 남되 청산일·보유일수가 비어 있고 제외 사유가 붙는다
        """
        # Given
        days = _trading_days("2026-06-01", "2026-07-22")

        # When
        schedule = _expiry_schedule(days, US_MONTHLY_EXPIRY, FRIDAY)

        # Then
        row = _row_for(schedule.frame, "2026-07-17")
        assert row[COL_EXCLUDED_REASON] == REASON_OUT_OF_RANGE
        assert pd.isna(row[COL_EXIT_DATE])
        assert pd.isna(row[COL_HOLD_DAYS])

    def test_표본이_보존된다(self) -> None:
        """
        목적: 진입 수 = 유효 표본 + 제외 표본 을 고정한다

        Given: 마지막 만기의 목표일이 범위를 넘는 달력
        When: 청산 일정을 만들면
        Then: 진입 수가 유효와 제외의 합과 같고 제외가 1건이다
        """
        # Given
        days = _trading_days("2026-01-01", "2026-07-22")

        # When
        schedule = _expiry_schedule(days, US_MONTHLY_EXPIRY, FRIDAY)

        # Then
        assert schedule.entry_count == schedule.valid_count + schedule.excluded_count
        assert schedule.excluded_count == 1

    def test_모든_청산일은_거래일이고_진입일보다_뒤다(self) -> None:
        """
        목적: 경계 조건 — 청산이 진입과 같거나 앞서는 행이 남지 않음을 고정한다

        Given: 휴장이 여럿 섞인 2년치 달력
        When: 청산 일정을 만들면
        Then: 유효한 행의 청산일이 전부 거래일이고 진입일보다 뒤다
        """
        # Given
        days = _trading_days(
            "2025-01-01",
            "2026-12-31",
            holidays=["2025-04-18", "2025-11-28", "2025-12-26", "2026-06-19"],
        )

        # When
        schedule = _expiry_schedule(days, US_MONTHLY_EXPIRY, FRIDAY)

        # Then
        valid = schedule.frame[schedule.frame[COL_EXCLUDED_REASON] == REASON_NONE]
        assert valid[COL_EXIT_DATE].isin(days).all(), "청산일이 거래일이 아닙니다"
        assert (valid[COL_EXIT_DATE] > valid[COL_DATE]).all(), "청산일이 진입일보다 뒤가 아닙니다"
        assert (valid[COL_HOLD_DAYS] >= 1).all()


class TestLookAhead:
    """미래 데이터를 참조하지 않는지 감시한다."""

    def test_뒤에_데이터가_붙어도_지난_진입의_청산이_그대로다(self) -> None:
        """
        목적: **look-ahead 감시** — 미래 거래일이 있든 없든 판정이 같음을 고정한다

        Given: 같은 시작일에서 6개월치와 24개월치 달력
        When: 각각 청산 일정을 만들면
        Then: 짧은 쪽에서 유효했던 모든 진입일의 청산일·보유일수가 긴 쪽과 같다
        """
        # Given
        holidays = ["2025-04-18", "2025-11-28", "2025-12-26"]
        short_days = _trading_days("2025-01-01", "2025-06-30", holidays=holidays)
        long_days = _trading_days("2025-01-01", "2026-12-31", holidays=holidays)

        # When
        short = _expiry_schedule(short_days, US_MONTHLY_EXPIRY, FRIDAY)
        long = _expiry_schedule(long_days, US_MONTHLY_EXPIRY, FRIDAY)

        # Then
        short_valid = short.frame[short.frame[COL_EXCLUDED_REASON] == REASON_NONE]
        merged = short_valid.merge(long.frame, on=COL_DATE, suffixes=("_short", "_long"))
        assert len(merged) == len(short_valid), "짧은 입력의 진입일이 긴 입력에 전부 있어야 합니다"
        assert (
            merged[f"{COL_EXIT_DATE}_short"] == merged[f"{COL_EXIT_DATE}_long"]
        ).all(), "뒤를 잘라낸 입력과 전체 입력의 청산일이 다릅니다 — 미래 데이터를 참조하고 있습니다"
        assert (merged[f"{COL_HOLD_DAYS}_short"] == merged[f"{COL_HOLD_DAYS}_long"]).all()


class TestWeeklyExitReturns:
    """수익률 산식과 long-form 스키마를 고정한다."""

    def test_수익률은_청산종가_나누기_진입종가다(self) -> None:
        """
        목적: 산식을 손으로 계산한 값으로 고정한다

        Given: 진입일 2026-07-17 종가 100, 청산일 2026-07-24 종가 105
        When: 수익률을 내면
        Then: 0.05 다
        """
        # Given
        days = _trading_days("2026-06-01", "2026-08-31")
        closes = [100.0] * len(days)
        closes[int(days.get_loc(pd.Timestamp("2026-07-24")))] = 105.0
        df = _market(days, closes)
        schedule = _expiry_schedule(days, US_MONTHLY_EXPIRY, FRIDAY)

        # When
        result = weekly_exit_returns(df, schedule)

        # Then
        row = result[result[COL_DATE] == pd.Timestamp("2026-07-17")].iloc[0]
        assert float(row[COL_FORWARD_RETURN]) == pytest.approx(0.05, abs=EXACT_TOLERANCE)

    def test_묶음_칸은_표지_구간_하나로_모인다(self) -> None:
        """
        목적: **보유 길이가 달라도 한 매매는 한 칸**임을 고정한다 (결정 ㉑)

        보유 거래일 수를 구간 축에 넣으면 한 매매가 여러 칸으로 쪼개져 묶음 값이 나오지 않는다.

        Given: 보유 4거래일과 5거래일이 섞이는 달력
        When: 수익률을 내면
        Then: 구간 축의 값이 표지 하나뿐이다
        """
        # Given
        days = _trading_days("2026-01-01", "2026-12-31", holidays=["2026-07-24"])
        df = _market(days)
        schedule = _expiry_schedule(days, US_MONTHLY_EXPIRY, FRIDAY)

        # When
        result = weekly_exit_returns(df, schedule)

        # Then
        assert schedule.frame[COL_HOLD_DAYS].nunique() > 1, "보유 길이가 섞이는 달력이어야 합니다"
        assert result[COL_HORIZON].unique().tolist() == [HORIZON_NEXT_WEEK_EXIT]
        assert result[COL_BASIS].unique().tolist() == ["close"]

    def test_제외된_진입도_행으로_남는다(self) -> None:
        """
        목적: 표본 보존 — 제외된 행이 사라지지 않음을 고정한다

        행이 사라지면 표본이 조용히 줄어 생존편향이 생긴다.

        Given: 마지막 만기의 목표일이 범위를 넘는 달력
        When: 수익률을 내면
        Then: 그 진입일의 행이 남고 값이 비어 있으며 사유가 붙는다
        """
        # Given
        days = _trading_days("2026-01-01", "2026-07-22")
        df = _market(days)
        schedule = _expiry_schedule(days, US_MONTHLY_EXPIRY, FRIDAY)

        # When
        result = weekly_exit_returns(df, schedule)

        # Then
        assert len(result) == schedule.entry_count
        excluded = result[result[COL_EXCLUDED_REASON] != REASON_NONE]
        assert len(excluded) == 1
        assert excluded[COL_FORWARD_RETURN].isna().all()

    def test_진입이_하나도_없으면_빈_결과다(self) -> None:
        """
        목적: 경계 조건 — 표본 0건이 예외가 아니라 정상 결과임을 고정한다

        Given: 만기일이 하나도 없는 짧은 달력
        When: 청산 일정과 수익률을 내면
        Then: 스키마를 유지한 빈 결과가 나온다
        """
        # Given
        days = _trading_days("2026-07-01", "2026-07-10")
        df = _market(days)

        # When
        schedule = _expiry_schedule(days, US_MONTHLY_EXPIRY, FRIDAY)
        result = weekly_exit_returns(df, schedule)

        # Then
        assert schedule.entry_count == 0
        assert result.empty
        assert COL_FORWARD_RETURN in result.columns


class TestValidation:
    """입력 검증을 고정한다."""

    def test_거래일_목록이_비면_예외다(self) -> None:
        """
        목적: 입력 검증을 고정한다

        Given: 빈 거래일 목록
        When: 청산 일정을 만들면
        Then: ValueError 가 난다
        """
        # Given
        entries = pd.DatetimeIndex([pd.Timestamp("2026-07-17")])

        # When / Then
        with pytest.raises(ValueError, match="비어 있어"):
            weekly_exit_schedule(pd.DatetimeIndex([]), entries, entries, exit_weekday=FRIDAY)

    def test_청산_요일이_범위를_벗어나면_예외다(self) -> None:
        """
        목적: 입력 검증을 고정한다

        Given: 요일 7
        When: 청산 일정을 만들면
        Then: ValueError 가 난다
        """
        # Given
        days = _trading_days("2026-07-01", "2026-08-31")
        entries = pd.DatetimeIndex([pd.Timestamp("2026-07-17")])

        # When / Then
        with pytest.raises(ValueError, match="요일은"):
            weekly_exit_schedule(days, entries, entries, exit_weekday=7)

    def test_진입일이_거래일에_없으면_예외다(self) -> None:
        """
        목적: 입력 검증을 고정한다 — 엉뚱한 날에 진입하는 사고는 예외 없이 일어난다

        Given: 거래일 목록에 없는 진입일 (2026-07-18 은 토요일)
        When: 청산 일정을 만들면
        Then: ValueError 가 난다
        """
        # Given
        days = _trading_days("2026-07-01", "2026-08-31")
        entries = pd.DatetimeIndex([pd.Timestamp("2026-07-18")])

        # When / Then
        with pytest.raises(ValueError, match="거래일 목록에 없습니다"):
            weekly_exit_schedule(days, entries, entries, exit_weekday=FRIDAY)

    def test_진입일과_주_기준일의_길이가_다르면_예외다(self) -> None:
        """
        목적: 입력 검증을 고정한다 — 두 축이 어긋나면 엉뚱한 주에서 목표일이 나온다

        Given: 진입일 2개와 주 기준일 1개
        When: 청산 일정을 만들면
        Then: ValueError 가 난다
        """
        # Given
        days = _trading_days("2026-07-01", "2026-08-31")
        entries = pd.DatetimeIndex([pd.Timestamp("2026-07-17"), pd.Timestamp("2026-08-21")])
        references = pd.DatetimeIndex([pd.Timestamp("2026-07-17")])

        # When / Then
        with pytest.raises(ValueError, match="길이가 다릅니다"):
            weekly_exit_schedule(days, entries, references, exit_weekday=FRIDAY)
