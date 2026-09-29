"""반감기_사이클 달력 — 진입일 · 청산 일정 · 수익률 · 기준선 · 달력 연도의 정의를 고정한다.

**정의가 곧 결론을 만든다.** 진입일이 하루 밀리면 48칸 전부가 조용히 다른 날을 재고 예외는 나지 않는다.

**픽스처 반감기는 실제 값과 다르게 고른다** (`docs/MEMORY.md` 「픽스처는 실제 쓰이는 값과 «다르게» 고른다」).
실제 반감기 날(28 · 9 · 11 · 20일)은 어느 달에나 있어 말일 당김을 밟지 않으므로, 31일 · 29일 반감기를 두어
「달력월을 더하면 짧은 달의 말일로 당긴다」가 하드코딩돼도 걸리게 한다.
"""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_ENTRY_CLOSE,
    COL_EXCLUDED_REASON,
    COL_EXIT_CLOSE,
    COL_EXIT_DATE,
    COL_FORWARD_RETURN,
    COL_HOLD_DAYS,
    COL_HORIZON,
    REASON_NONE,
    REASON_OUT_OF_RANGE,
)
from verify_lab.studies.halving_cycle.constants import (
    COL_CALENDAR_YEAR,
    COL_ENTRY_MONTHS,
    COL_HALVING,
    COL_HALVING_POSITION,
    COL_HOLD_MONTHS,
    COL_PREVIOUS_CLOSE,
    COL_YEAR_END_CLOSE,
    POSITION_BEFORE_FIRST,
    POSITION_HALVING_YEAR,
    REASON_NO_PREVIOUS_YEAR_END,
    REASON_YEAR_UNFINISHED,
    Halving,
)
from verify_lab.studies.halving_cycle.halving_calendar import (
    baseline_entries,
    calendar_returns,
    calendar_year_returns,
    exit_schedule,
    halving_entries,
    halving_position,
)


def _halving(day: str) -> Halving:
    """그날 정오(UTC)에 블록이 나온 합성 반감기."""
    moment = pd.Timestamp(day)

    return Halving(height=0, block_time=datetime(moment.year, moment.month, moment.day, 12, 0, tzinfo=UTC))


def _days(start: str, end: str) -> pd.DatetimeIndex:
    """휴장 없는 달력일 목록 — 비트코인 시세의 모양이다."""
    return pd.date_range(start, end, freq="D")


def _prices(days: pd.DatetimeIndex) -> pd.DataFrame:
    """날마다 0.1% 씩 오르는 종가 — 수익률을 손으로 셀 수 있게 한다."""
    return pd.DataFrame({COL_DATE: days, COL_CLOSE: 100.0 * np.power(1.001, np.arange(len(days)))})


class TestHalvingPosition:
    """달력 연도가 반감기 사이클의 어디인가"""

    HALVINGS = (_halving("2012-11-28"), _halving("2016-07-09"))

    @pytest.mark.parametrize(
        ("year", "expected"),
        [
            (2011, POSITION_BEFORE_FIRST),
            (2012, POSITION_HALVING_YEAR),
            (2013, "반감기 + 1"),
            (2015, "반감기 + 3"),
            (2016, POSITION_HALVING_YEAR),
            (2019, "반감기 + 3"),
        ],
    )
    def test_가장_최근_반감기_해로부터의_햇수다(self, year: int, expected: str) -> None:
        """
        목적: 위치를 「4로 나눈 나머지」가 아니라 **반감기 목록**에서 정함을 고정한다.

        Args:
            year: 달력 연도
            expected: 기대 위치

        Given: 2012 · 2016 반감기
        When: 그해의 위치를 구한다
        Then: 가장 최근 반감기 해로부터의 햇수이고, 첫 반감기 전이면 그렇게 적는다
        """
        assert halving_position(year, self.HALVINGS) == expected


class TestHalvingEntries:
    """진입일 = 반감기일 + e 달력월"""

    def test_진입일은_반감기일에_달력월을_더한_날이다(self) -> None:
        """
        목적: 진입일 산식을 고정한다.

        Given: 2020-01-15 반감기, 진입 0 · 3개월
        When: 진입일을 만든다
        Then: 2020-01-15 · 2020-04-15 이고 반감기 표지가 날짜 문자열이다
        """
        # Given
        days = _days("2020-01-01", "2020-12-31")

        # When
        entries = halving_entries(days, (_halving("2020-01-15"),), (0, 3))

        # Then
        assert entries[COL_DATE].tolist() == [pd.Timestamp("2020-01-15"), pd.Timestamp("2020-04-15")]
        assert entries[COL_ENTRY_MONTHS].tolist() == [0, 3]
        assert entries[COL_HALVING].tolist() == ["2020-01-15", "2020-01-15"]

    def test_말일_반감기는_짧은_달의_말일로_당긴다(self) -> None:
        """
        목적: 달력월을 더할 때 없는 날짜는 그 달 말일이 됨을 고정한다 (경계 조건 — 윤년 2월).

        Given: 2020-01-31 반감기, 진입 1 · 3개월
        When: 진입일을 만든다
        Then: 2020-02-29 · 2020-04-30
        """
        # Given
        days = _days("2020-01-01", "2020-12-31")

        # When
        entries = halving_entries(days, (_halving("2020-01-31"),), (1, 3))

        # Then
        assert entries[COL_DATE].tolist() == [pd.Timestamp("2020-02-29"), pd.Timestamp("2020-04-30")]

    def test_데이터_마지막_날_뒤의_진입은_행이_없다(self) -> None:
        """
        목적: 아직 오지 않은 진입을 제외 행으로 만들지 않음을 고정한다 — 신호 자체가 아직 없다.

        Given: 2020-03-31 까지의 거래일, 2020-01-15 반감기, 진입 0 ~ 3개월
        When: 진입일을 만든다
        Then: 0 · 1 · 2개월만 있다
        """
        # Given
        days = _days("2020-01-01", "2020-03-31")

        # When
        entries = halving_entries(days, (_halving("2020-01-15"),), (0, 1, 2, 3))

        # Then
        assert entries[COL_ENTRY_MONTHS].tolist() == [0, 1, 2]

    def test_거래일에_없는_진입일은_예외다(self) -> None:
        """
        목적: 데이터 안인데 거래일에 없는 진입을 조용히 옮기지 않음을 고정한다.

        비트코인은 휴장이 없어 그런 날은 곧 데이터의 빈틈이다 — 앞뒤 날로 옮기면 다른 날을 잰다.

        Given: 2020-02-15 가 빠진 거래일, 2020-01-15 반감기, 진입 1개월
        When: 진입일을 만든다
        Then: ValueError 가 발생한다
        """
        # Given
        days = _days("2020-01-01", "2020-12-31").drop(pd.Timestamp("2020-02-15"))

        # When / Then
        with pytest.raises(ValueError, match="거래일"):
            halving_entries(days, (_halving("2020-01-15"),), (1,))

    def test_데이터_앞의_반감기는_예외다(self) -> None:
        """
        목적: 시세가 덮지 못하는 반감기를 조용히 건너뛰지 않음을 고정한다 — 사이클 하나가 사라진다.

        Given: 2020-01-01 부터의 거래일, 2019-11-15 반감기
        When: 진입 0개월을 만든다
        Then: ValueError 가 발생한다
        """
        # Given
        days = _days("2020-01-01", "2020-12-31")

        # When / Then
        with pytest.raises(ValueError, match="거래일"):
            halving_entries(days, (_halving("2019-11-15"),), (0,))

    def test_음수_진입_개월은_예외다(self) -> None:
        """
        목적: 반감기 «전» 진입을 받지 않음을 고정한다 (입력 검증).

        Given: 진입 −3개월
        When: 진입일을 만든다
        Then: ValueError 가 발생한다
        """
        with pytest.raises(ValueError, match="개월"):
            halving_entries(_days("2020-01-01", "2020-12-31"), (_halving("2020-06-15"),), (-3,))

    def test_반감기가_없으면_예외다(self) -> None:
        """
        목적: 빈 반감기 목록을 「진입 0건」으로 통과시키지 않음을 고정한다 (경계 조건).

        Given: 빈 반감기 목록
        When: 진입일을 만든다
        Then: ValueError 가 발생한다
        """
        with pytest.raises(ValueError, match="반감기"):
            halving_entries(_days("2020-01-01", "2020-12-31"), (), (0,))


class TestExitSchedule:
    """청산일 = 진입일 + h 달력월"""

    def test_청산일은_진입일에_보유_개월을_더한_날이다(self) -> None:
        """
        목적: 청산 산식과 보유 거래일 수를 고정한다.

        Given: 2020-01-15 진입, 보유 3개월
        When: 청산 일정을 만든다
        Then: 청산일 2020-04-15 · 보유 91일 · 사유 없음
        """
        # Given
        days = _days("2020-01-01", "2020-12-31")
        entries = pd.DataFrame({COL_DATE: [pd.Timestamp("2020-01-15")]})

        # When
        schedule = exit_schedule(days, entries, (3,))

        # Then
        assert schedule[COL_EXIT_DATE].tolist() == [pd.Timestamp("2020-04-15")]
        assert schedule[COL_HOLD_DAYS].tolist() == [91]
        assert schedule[COL_HOLD_MONTHS].tolist() == [3]
        assert schedule[COL_EXCLUDED_REASON].tolist() == [REASON_NONE]

    def test_29일_진입은_평년_2월_말일에_청산한다(self) -> None:
        """
        목적: 기준선의 29 ~ 31일 진입이 짧은 달에서 말일로 당겨짐을 고정한다 (경계 조건 — 평년).

        Given: 2019-01-29 진입, 보유 1개월
        When: 청산 일정을 만든다
        Then: 청산일 2019-02-28
        """
        # Given
        days = _days("2019-01-01", "2019-12-31")
        entries = pd.DataFrame({COL_DATE: [pd.Timestamp("2019-01-29")]})

        # When
        schedule = exit_schedule(days, entries, (1,))

        # Then
        assert schedule[COL_EXIT_DATE].tolist() == [pd.Timestamp("2019-02-28")]

    def test_청산이_데이터_끝을_넘으면_행이_남고_사유가_붙는다(self) -> None:
        """
        목적: 청산이 아직 오지 않은 진입을 지우지 않음을 고정한다 (표본 보존).

        Given: 2020-06-30 까지의 거래일, 2020-05-01 진입, 보유 3개월
        When: 청산 일정을 만든다
        Then: 행은 있고 청산일·보유일은 비었으며 사유가 「구간 끝이 데이터 범위를 넘음」이다
        """
        # Given
        days = _days("2020-01-01", "2020-06-30")
        entries = pd.DataFrame({COL_DATE: [pd.Timestamp("2020-05-01")]})

        # When
        schedule = exit_schedule(days, entries, (3,))

        # Then
        assert len(schedule) == 1
        assert pd.isna(schedule[COL_EXIT_DATE].iloc[0])
        assert pd.isna(schedule[COL_HOLD_DAYS].iloc[0])
        assert schedule[COL_EXCLUDED_REASON].tolist() == [REASON_OUT_OF_RANGE]

    def test_행_수는_진입_수_곱하기_보유_수다(self) -> None:
        """
        목적: 진입 × 보유 = 유효 + 제외 가 성립함을 고정한다 (표본 보존).

        Given: 진입 셋, 보유 둘 (그중 일부는 데이터 끝을 넘는다)
        When: 청산 일정을 만든다
        Then: 여섯 행이고, 유효와 제외의 합이 여섯이다
        """
        # Given
        days = _days("2020-01-01", "2020-12-31")
        entries = pd.DataFrame({COL_DATE: pd.to_datetime(["2020-01-10", "2020-06-10", "2020-12-10"])})

        # When
        schedule = exit_schedule(days, entries, (1, 6))

        # Then
        valid = int((schedule[COL_EXCLUDED_REASON] == REASON_NONE).sum())
        excluded = int((schedule[COL_EXCLUDED_REASON] != REASON_NONE).sum())
        assert len(schedule) == 6
        assert valid + excluded == 6
        assert excluded == 2

    def test_진입_표의_다른_컬럼을_그대로_싣는다(self) -> None:
        """
        목적: 반감기 표지와 진입 개월이 청산 일정까지 따라옴을 고정한다 — 집계가 그 축으로 묶인다.

        Given: 반감기 표지와 진입 개월이 든 진입 표
        When: 청산 일정을 만든다
        Then: 두 컬럼이 행마다 그대로 있다
        """
        # Given
        days = _days("2020-01-01", "2020-12-31")
        entries = halving_entries(days, (_halving("2020-01-15"),), (0,))

        # When
        schedule = exit_schedule(days, entries, (1, 3))

        # Then
        assert schedule[COL_HALVING].tolist() == ["2020-01-15", "2020-01-15"]
        assert schedule[COL_ENTRY_MONTHS].tolist() == [0, 0]

    def test_거래일에_없는_청산일은_예외다(self) -> None:
        """
        목적: 데이터 안인데 거래일에 없는 청산을 앞뒤 날로 옮기지 않음을 고정한다.

        Given: 2020-02-15 가 빠진 거래일, 2020-01-15 진입, 보유 1개월
        When: 청산 일정을 만든다
        Then: ValueError 가 발생한다
        """
        # Given
        days = _days("2020-01-01", "2020-12-31").drop(pd.Timestamp("2020-02-15"))
        entries = pd.DataFrame({COL_DATE: [pd.Timestamp("2020-01-15")]})

        # When / Then
        with pytest.raises(ValueError, match="거래일"):
            exit_schedule(days, entries, (1,))

    def test_보유_개월이_1_미만이면_예외다(self) -> None:
        """
        목적: 보유 0개월(진입일에 청산)을 받지 않음을 고정한다 (입력 검증).

        Given: 보유 0개월
        When: 청산 일정을 만든다
        Then: ValueError 가 발생한다
        """
        entries = pd.DataFrame({COL_DATE: [pd.Timestamp("2020-01-15")]})

        with pytest.raises(ValueError, match="개월"):
            exit_schedule(_days("2020-01-01", "2020-12-31"), entries, (0,))


class TestCalendarReturns:
    """청산 일정에 가격을 붙인 long-form"""

    def test_수익률은_진입_종가_대비_청산_종가다(self) -> None:
        """
        목적: 수익률 산식을 손 계산 값으로 고정한다.

        Given: 하루 0.1% 씩 오르는 종가, 2020-01-01 진입, 보유 1개월 (31일 뒤)
        When: 수익률을 낸다
        Then: 1.001^31 − 1 이고 진입·청산 종가가 함께 실린다
        """
        # Given
        days = _days("2020-01-01", "2020-12-31")
        prices = _prices(days)
        schedule = exit_schedule(days, pd.DataFrame({COL_DATE: [pd.Timestamp("2020-01-01")]}), (1,))

        # When
        returns = calendar_returns(prices, schedule)

        # Then
        assert returns[COL_FORWARD_RETURN].iloc[0] == pytest.approx(1.001**31 - 1.0, abs=1e-12)
        assert returns[COL_ENTRY_CLOSE].iloc[0] == pytest.approx(100.0, abs=0.01)
        assert returns[COL_EXIT_CLOSE].iloc[0] == pytest.approx(100.0 * 1.001**31, abs=0.01)

    def test_제외된_진입은_값이_비고_행은_남는다(self) -> None:
        """
        목적: 청산이 오지 않은 행의 수익률을 0 으로 채우지 않음을 고정한다 — 0 은 「오르지도 내리지도 않았다」다.

        Given: 데이터 끝을 넘는 청산
        When: 수익률을 낸다
        Then: 행은 있고 수익률·청산 종가는 비었다
        """
        # Given
        days = _days("2020-01-01", "2020-06-30")
        schedule = exit_schedule(days, pd.DataFrame({COL_DATE: [pd.Timestamp("2020-05-01")]}), (3,))

        # When
        returns = calendar_returns(_prices(days), schedule)

        # Then
        assert len(returns) == 1
        assert pd.isna(returns[COL_FORWARD_RETURN].iloc[0])
        assert pd.isna(returns[COL_EXIT_CLOSE].iloc[0])

    def test_집계_스키마의_기준과_구간_축을_채운다(self) -> None:
        """
        목적: `measure.statistics.summarize` 가 읽는 두 축을 채움을 고정한다 — 구간 축은 «보유 개월»이다.

        Given: 보유 3 · 12개월 일정
        When: 수익률을 낸다
        Then: 기준은 전부 종가이고 구간 축에 보유 개월이 들어 있다
        """
        # Given
        days = _days("2020-01-01", "2021-12-31")
        schedule = exit_schedule(days, pd.DataFrame({COL_DATE: [pd.Timestamp("2020-01-01")]}), (3, 12))

        # When
        returns = calendar_returns(_prices(days), schedule)

        # Then
        assert set(returns[COL_BASIS]) == {"close"}
        assert returns[COL_HORIZON].tolist() == [3, 12]


class TestBaselineEntries:
    """기준선 — 첫 반감기부터 매일 진입"""

    def test_시작일부터_매일이다(self) -> None:
        """
        목적: 기준선 모집단이 신호군과 같은 기간(첫 반감기부터)임을 고정한다 (실행 계층 계약).

        Given: 2020-01-01 ~ 01-10 거래일, 시작일 01-05
        When: 기준선 진입일을 만든다
        Then: 01-05 ~ 01-10 여섯 날이고 그 앞은 없다
        """
        # Given
        days = _days("2020-01-01", "2020-01-10")

        # When
        entries = baseline_entries(days, pd.Timestamp("2020-01-05"))

        # Then
        assert entries[COL_DATE].tolist() == list(_days("2020-01-05", "2020-01-10"))

    def test_시작일이_데이터_뒤면_예외다(self) -> None:
        """
        목적: 기준선이 통째로 비는 것을 조용히 넘기지 않음을 고정한다 (경계 조건).

        Given: 01-10 까지의 거래일, 시작일 02-01
        When: 기준선 진입일을 만든다
        Then: ValueError 가 발생한다
        """
        with pytest.raises(ValueError, match="기준선"):
            baseline_entries(_days("2020-01-01", "2020-01-10"), pd.Timestamp("2020-02-01"))


class TestCalendarYearReturns:
    """달력 연도 — 전년 말 종가 대비 그해 말 종가 (관찰용)"""

    HALVINGS = (_halving("2012-11-28"),)

    def _table(self) -> pd.DataFrame:
        days = _days("2011-08-18", "2013-06-30")

        return calendar_year_returns(_prices(days), self.HALVINGS)

    def test_데이터가_닿는_해마다_한_행이다(self) -> None:
        """
        목적: 끝이 잘린 해도 행을 지우지 않음을 고정한다 (측정의 원칙 17).

        Given: 2011-08-18 ~ 2013-06-30 시세
        When: 달력 연도 표를 만든다
        Then: 2011 · 2012 · 2013 세 행
        """
        assert self._table()[COL_CALENDAR_YEAR].tolist() == [2011, 2012, 2013]

    def test_수익률은_전년_말_종가_대비_그해_말_종가다(self) -> None:
        """
        목적: 달력 연도 수익률 산식을 고정한다.

        Given: 하루 0.1% 씩 오르는 종가, 2012 는 윤년 (2011-12-31 → 2012-12-31 은 366일)
        When: 달력 연도 표를 만든다
        Then: 2012 의 수익률이 1.001^366 − 1 이고 위치는 반감기해다
        """
        # Given / When
        row = self._table().set_index(COL_CALENDAR_YEAR).loc[2012]

        # Then
        assert row[COL_FORWARD_RETURN] == pytest.approx(1.001**366 - 1.0, abs=1e-12)
        assert row[COL_HALVING_POSITION] == POSITION_HALVING_YEAR
        assert row[COL_EXCLUDED_REASON] == REASON_NONE

    def test_첫_해는_전년_말_종가가_없어_제외된다(self) -> None:
        """
        목적: 데이터가 해 중간에 시작하면 그해를 재지 않되 행은 남김을 고정한다.

        Given: 2011-08-18 부터의 시세
        When: 달력 연도 표를 만든다
        Then: 2011 행의 사유가 「전년 말 종가 없음」이고 값은 비었다
        """
        # Given / When
        row = self._table().set_index(COL_CALENDAR_YEAR).loc[2011]

        # Then
        assert row[COL_EXCLUDED_REASON] == REASON_NO_PREVIOUS_YEAR_END
        assert pd.isna(row[COL_PREVIOUS_CLOSE])
        assert pd.isna(row[COL_FORWARD_RETURN])
        assert row[COL_HALVING_POSITION] == POSITION_BEFORE_FIRST

    def test_끝나지_않은_해는_제외된다(self) -> None:
        """
        목적: 끝나지 않은 해의 「연초 대비」를 그해 수익률로 적지 않음을 고정한다 — 다른 양이다.

        Given: 2013-06-30 까지의 시세
        When: 달력 연도 표를 만든다
        Then: 2013 행의 사유가 「그해가 끝나지 않음」이고 그해 말 종가는 비었다
        """
        # Given / When
        row = self._table().set_index(COL_CALENDAR_YEAR).loc[2013]

        # Then
        assert row[COL_EXCLUDED_REASON] == REASON_YEAR_UNFINISHED
        assert pd.isna(row[COL_YEAR_END_CLOSE])
        assert pd.isna(row[COL_FORWARD_RETURN])

    def test_연말이_거래일에_없으면_예외다(self) -> None:
        """
        목적: 데이터 안인데 12-31 이 빠진 경우를 다른 날로 메우지 않음을 고정한다.

        Given: 2012-12-31 이 빠진 시세
        When: 달력 연도 표를 만든다
        Then: ValueError 가 발생한다
        """
        # Given
        days = _days("2011-08-18", "2013-06-30").drop(pd.Timestamp("2012-12-31"))

        # When / Then
        with pytest.raises(ValueError, match="거래일"):
            calendar_year_returns(_prices(days), self.HALVINGS)


class TestLookAhead:
    """뒤를 잘라낸 입력과 전체 입력의 결과가 **겹치는 칸에서** 같다 (tests/CLAUDE.md — 필수)

    forward return 은 정의상 미래를 보므로 뒤를 자르면 청산이 데이터를 넘는 칸이 「제외」로 바뀌는 것이
    정상이다. 그래서 **짧은 입력에서 값이 있는 칸**만 견준다.
    """

    HALVINGS = (_halving("2012-11-28"), _halving("2016-07-09"))
    FULL = _days("2012-06-01", "2019-12-31")
    CUT = pd.Timestamp("2016-10-31")

    def _signal(self, days: pd.DatetimeIndex) -> pd.DataFrame:
        entries = halving_entries(days, self.HALVINGS, (0, 3, 12, 30))
        schedule = exit_schedule(days, entries, (3, 12))

        return calendar_returns(_prices(self.FULL).iloc[: len(days)], schedule)

    def test_신호_수익률이_뒤_데이터에_기대지_않는다(self) -> None:
        """
        목적: 진입일·청산일·수익률이 판정일 이후 데이터 없이도 같음을 고정한다.

        Given: 2019 까지의 시세와 2016-10-31 에서 자른 시세
        When: 두 입력으로 신호 수익률을 낸다
        Then: 짧은 입력에서 값이 있는 칸은 전체 입력의 값과 같다
        """
        # Given
        short_days = self.FULL[self.FULL <= self.CUT]

        # When
        full = self._signal(self.FULL).set_index([COL_HALVING, COL_ENTRY_MONTHS, COL_HOLD_MONTHS])
        short = self._signal(short_days).set_index([COL_HALVING, COL_ENTRY_MONTHS, COL_HOLD_MONTHS])

        # Then
        measured = short[short[COL_EXCLUDED_REASON] == REASON_NONE]
        assert not measured.empty, "짧은 입력에서 잰 칸이 없어 계약을 검사하지 못했습니다"
        np.testing.assert_allclose(
            measured[COL_FORWARD_RETURN].to_numpy(), full.loc[measured.index, COL_FORWARD_RETURN].to_numpy(), rtol=1e-12
        )

    def test_기준선_수익률이_뒤_데이터에_기대지_않는다(self) -> None:
        """
        목적: 기준선도 같은 계약을 지킴을 고정한다.

        Given: 두 입력
        When: 첫 반감기부터 매일 진입한 기준선 수익률을 낸다
        Then: 짧은 입력에서 값이 있는 칸은 전체 입력의 값과 같다
        """
        # Given
        short_days = self.FULL[self.FULL <= self.CUT]
        start = self.HALVINGS[0].day

        def baseline(days: pd.DatetimeIndex) -> pd.DataFrame:
            schedule = exit_schedule(days, baseline_entries(days, start), (3,))
            return calendar_returns(_prices(self.FULL).iloc[: len(days)], schedule).set_index(COL_DATE)

        # When
        full = baseline(self.FULL)
        short = baseline(short_days)

        # Then
        measured = short[short[COL_EXCLUDED_REASON] == REASON_NONE]
        np.testing.assert_allclose(
            measured[COL_FORWARD_RETURN].to_numpy(), full.loc[measured.index, COL_FORWARD_RETURN].to_numpy(), rtol=1e-12
        )

    def test_달력_연도가_뒤_데이터에_기대지_않는다(self) -> None:
        """
        목적: 끝난 해의 값이 그 뒤 데이터 없이도 같음을 고정한다.

        Given: 두 입력
        When: 달력 연도 표를 만든다
        Then: 짧은 입력에서 값이 있는 해는 전체 입력의 값과 같다
        """
        # Given
        short_days = self.FULL[self.FULL <= self.CUT]

        # When
        full = calendar_year_returns(_prices(self.FULL), self.HALVINGS).set_index(COL_CALENDAR_YEAR)
        short = calendar_year_returns(_prices(self.FULL).iloc[: len(short_days)], self.HALVINGS).set_index(
            COL_CALENDAR_YEAR
        )

        # Then
        measured = short[short[COL_EXCLUDED_REASON] == REASON_NONE]
        assert not measured.empty, "짧은 입력에서 잰 해가 없어 계약을 검사하지 못했습니다"
        np.testing.assert_allclose(
            measured[COL_FORWARD_RETURN].to_numpy(), full.loc[measured.index, COL_FORWARD_RETURN].to_numpy(), rtol=1e-12
        )
