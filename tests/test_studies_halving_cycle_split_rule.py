"""반감기_사이클 3단계 혼합 분할 · 달력 매달 분할 — 4년 순위 · 신고가 창 · 회차 체결일 · 포지션 성적의 정의를 고정한다.

**정의가 곧 결론을 만든다.** 회차가 하루 밀리거나 평균 단가를 다른 식으로 내도 표는 그럴듯하게 나오고 예외는 나지 않는다.

**픽스처 값은 실제 격자와 다르게 고른다** (`docs/MEMORY.md` 「픽스처는 실제 쓰이는 값과 «다르게» 고른다」) —
기한 간격 · 문턱 · 창 개월을 실제(3개월 · 1.7/1.35/1.0 등)와 다르게 두어, 함수가 상수를 안에서 읽으면 걸리게 한다.
회차 수는 대부분 실제(3회)와 같고, 다른 회차 수(2회)는 신고가 창의 미래 참조 감시 테스트가 본다. 기준 반감기일도
31일을 두어 달력월의 말일 당김을 밟게 한다.
"""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_LOW
from verify_lab.execution.constants import NO_STOP_LABEL
from verify_lab.measure.constants import COL_EXCLUDED_REASON, COL_HOLD_DAYS, REASON_NONE
from verify_lab.measure.statistics import COL_MEAN, COL_MEDIAN, COL_MIN, COL_POSITIVE_COUNT
from verify_lab.studies.halving_cycle.constants import (
    COL_AVG_BUY_PRICE,
    COL_AVG_SELL_PRICE,
    COL_BREAK_DATE,
    COL_BUY_CALENDAR_COUNT,
    COL_BUY_FIRST_DEADLINE,
    COL_BUY_LAST_DEADLINE,
    COL_BUY_TRANCHES,
    COL_CALENDAR_SPLIT,
    COL_CYCLE_RETURN_TEMPLATE,
    COL_CYCLE_WORST_TEMPLATE,
    COL_FINISHED_COUNT,
    COL_FIRST_BUY_DATE,
    COL_FORK_SHARE,
    COL_HALVING,
    COL_LAST_SELL_DATE,
    COL_MONTHS_SINCE_HALVING,
    COL_POSITION_RETURN,
    COL_SELL_CALENDAR_COUNT,
    COL_SELL_FIRST_DEADLINE,
    COL_SELL_LAST_DEADLINE,
    COL_SELL_TRANCHES,
    COL_SOLD_BEFORE_STOP,
    COL_SPLIT_ANCHOR_HALVING,
    COL_SPLIT_DEADLINE,
    COL_SPLIT_FILL_CLOSE,
    COL_SPLIT_FILL_DATE,
    COL_SPLIT_SIDE,
    COL_SPLIT_TOTAL,
    COL_SPLIT_TRANCHE,
    COL_SPLIT_TRIGGER,
    COL_STOP_LINE_CLOSE,
    COL_STOP_LINE_DATE,
    COL_STOP_LINE_VS_COST,
    COL_STOP_METHOD,
    COL_STOP_SELL_CLOSE,
    COL_STOP_SELL_DATE,
    COL_WORST_VS_COST,
    REASON_NO_NEXT_HALVING,
    REASON_POSITION_BUYING,
    REASON_POSITION_SELLING,
    REASON_SPLIT_PENDING,
    REASON_STOP_SELL_PENDING,
    SPLIT_ANCHOR_HALVING,
    SPLIT_ANCHOR_HIGH,
    SPLIT_SIDE_BUY,
    SPLIT_SIDE_SELL,
    SPLIT_THRESHOLD_BOOK,
    SPLIT_THRESHOLD_NONE,
    SPLIT_THRESHOLD_RANK,
    SPLIT_TRIGGER_CALENDAR,
    SPLIT_TRIGGER_ONCHAIN,
    STOP_METHOD_LOW_BREAK,
    CalendarSplit,
    Halving,
    HardFork,
)
from verify_lab.studies.halving_cycle.split_rule import (
    CalendarSplitGrid,
    SplitGrid,
    SplitLeg,
    TrancheFill,
    calendar_split_grid,
    leg_fills,
    new_high_flags,
    position_result,
    split_grid,
    split_legs,
    trailing_rank,
    tranche_deadlines,
    window_open,
)

# 픽스처 격자 — 기한 간격은 실제(3개월)와 다르다. 회차 수는 실제와 같다 — 다른 회차 수는 신고가 창 미래 참조 테스트가 본다
TRANCHES = 3
STEP = 2


def _halving(day: str) -> Halving:
    """그날 정오(UTC)에 블록이 나온 합성 반감기."""
    moment = pd.Timestamp(day)

    return Halving(height=0, block_time=datetime(moment.year, moment.month, moment.day, 12, 0, tzinfo=UTC))


def _days(start: str, end: str) -> pd.DatetimeIndex:
    """휴장 없는 달력일 목록 — 비트코인 시세의 모양이다."""
    return pd.date_range(start, end, freq="D")


def _values(days: pd.DatetimeIndex, default: float, overrides: dict[str, float]) -> pd.Series:
    """기본값에 몇 날만 다른 값을 심은 계열."""
    planted = {pd.Timestamp(day): value for day, value in overrides.items()}

    return pd.Series([planted.get(day, default) for day in days], index=days, dtype=float)


def _frame(
    days: pd.DatetimeIndex, closes: dict[str, float], lows: dict[str, float], base: float = 100.0
) -> pd.DataFrame:
    """기본 가격에 몇 날만 다른 종가 · 저가를 심은 시세. 저가를 따로 주지 않은 날은 종가와 같다."""
    close = _values(days, base, closes)
    planted = {pd.Timestamp(day): value for day, value in lows.items()}
    low = [planted.get(day, price) for day, price in zip(days, close.to_numpy(), strict=True)]

    return pd.DataFrame({COL_DATE: days, COL_CLOSE: close.to_numpy(), COL_LOW: low})


def _buy_leg(
    threshold: str = SPLIT_THRESHOLD_BOOK,
    levels: tuple[float, ...] = (2.0, 1.5, 0.5),
    start_anchor: str | None = SPLIT_ANCHOR_HALVING,
    start_months: int | None = 1,
    last_deadline: int = 10,
) -> SplitLeg:
    """픽스처 매수 조합 — 문턱 · 개월이 실제와 다르다."""
    return SplitLeg(
        side=SPLIT_SIDE_BUY,
        threshold=threshold,
        levels=levels,
        start_anchor=start_anchor,
        start_months=start_months,
        last_deadline=last_deadline,
    )


def _calendar_leg(side: str, last_deadline: int) -> SplitLeg:
    """달력만 조합."""
    return SplitLeg(
        side=side,
        threshold=SPLIT_THRESHOLD_NONE,
        levels=(),
        start_anchor=None,
        start_months=None,
        last_deadline=last_deadline,
    )


def _fill(day: str | None, trigger: str | None, deadline: str = "2099-01-01") -> TrancheFill:
    """손으로 만든 회차 체결."""
    return TrancheFill(
        deadline=pd.Timestamp(deadline),
        fill_day=None if day is None else pd.Timestamp(day),
        trigger=trigger,
        reason=REASON_NONE if day is not None else REASON_SPLIT_PENDING,
    )


class TestTrailingRank:
    """4년 순위 — 그날까지의 창에서 그날 값 이하인 관측의 비율"""

    def test_손으로_센_비율과_같다(self) -> None:
        """
        목적: 동점을 「이하」로 세고 그날 자신을 포함한다.

        Given: 닷새의 값 3 · 1 · 2 · 2 · 5
        When: 창이 충분히 긴 순위를 낸다
        Then: 1/1 · 1/2 · 2/3 · 3/4 · 5/5
        """
        # Given
        values = pd.Series([3.0, 1.0, 2.0, 2.0, 5.0], index=_days("2020-01-01", "2020-01-05"))

        # When
        rank = trailing_rank(values, years=1, min_days=1)

        # Then
        assert rank.tolist() == pytest.approx([1.0, 0.5, 2 / 3, 0.75, 1.0], abs=1e-12)

    def test_창의_시작_경계는_들어가지_않는다(self) -> None:
        """
        목적: 창은 (d − years, d] 이다 — 정확히 years 년 전의 관측은 빠진다.

        Given: 2020-01-02 · 2020-06-01 · 2021-01-02 의 값 0 · 5 · 3
        When: 1년 창 순위를 낸다
        Then: 2021-01-02 는 5 · 3 중 3 이하인 1개 → 0.5 (0 이 들어가면 2/3)
        """
        # Given
        values = pd.Series([0.0, 5.0, 3.0], index=pd.DatetimeIndex(["2020-01-02", "2020-06-01", "2021-01-02"]))

        # When
        rank = trailing_rank(values, years=1, min_days=1)

        # Then
        assert rank.iloc[-1] == pytest.approx(0.5, abs=1e-12)

    def test_관측이_모자라면_비운다(self) -> None:
        """
        목적: 창의 관측이 최소 일수보다 적은 날은 순위가 없다.

        Given: 닷새의 값
        When: 최소 3일로 순위를 낸다
        Then: 앞 이틀이 비고 셋째부터 값이 있다
        """
        # Given
        values = pd.Series([3.0, 1.0, 2.0, 2.0, 5.0], index=_days("2020-01-01", "2020-01-05"))

        # When
        rank = trailing_rank(values, years=1, min_days=3)

        # Then
        assert rank.isna().tolist() == [True, True, False, False, False]

    def test_뒤를_잘라도_앞의_순위가_같다(self) -> None:
        """
        목적: 미래 참조 감시 — d 의 순위는 d 뒤의 값에 기대지 않는다.

        Given: 3년치 값
        When: 전체와 앞 절반으로 각각 순위를 낸다
        Then: 겹치는 날의 순위가 같다
        """
        # Given
        days = _days("2019-01-01", "2021-12-31")
        values = pd.Series(np.sin(np.arange(len(days)) / 37.0) + np.arange(len(days)) / 500.0, index=days)
        cut = len(days) // 2

        # When
        full = trailing_rank(values, years=1, min_days=30)
        truncated = trailing_rank(values.iloc[:cut], years=1, min_days=30)

        # Then
        pd.testing.assert_series_equal(full.iloc[:cut], truncated, rtol=0, atol=1e-12)

    def test_결측이_있으면_멈춘다(self) -> None:
        """
        목적: 결측을 조용히 건너뛰면 창의 관측 수가 달라져 순위가 예외 없이 바뀐다.

        Given: 값 하나가 빈 계열
        When: 순위를 낸다
        Then: ValueError
        """
        # Given
        values = pd.Series([1.0, np.nan, 2.0], index=_days("2020-01-01", "2020-01-03"))

        # When / Then
        with pytest.raises(ValueError, match="결측"):
            trailing_rank(values, years=1, min_days=1)


class TestNewHighFlags:
    """신고가 — 그 전의 모든 종가보다 높은 날"""

    def test_같은_값은_신고가가_아니고_첫_날도_아니다(self) -> None:
        """
        목적: 「넘은 날」이다 — 같으면 넘지 않았다.

        Given: 종가 5 · 4 · 6 · 6 · 7 · 3 · 8
        When: 신고가를 찾는다
        Then: 셋째 · 다섯째 · 일곱째
        """
        # Given
        close = pd.Series([5.0, 4.0, 6.0, 6.0, 7.0, 3.0, 8.0], index=_days("2020-01-01", "2020-01-07"))

        # When
        flags = new_high_flags(close)

        # Then
        assert flags.tolist() == [False, False, True, False, True, False, True]

    def test_뒤를_잘라도_앞의_판정이_같다(self) -> None:
        """
        목적: 미래 참조 감시.

        Given: 오르내리는 종가
        When: 전체와 앞부분으로 각각 판정한다
        Then: 겹치는 날이 같다
        """
        # Given
        days = _days("2020-01-01", "2020-12-31")
        close = pd.Series(100.0 + 10.0 * np.sin(np.arange(len(days)) / 9.0) + np.arange(len(days)) / 10.0, index=days)

        # When
        full = new_high_flags(close)
        truncated = new_high_flags(close.iloc[:200])

        # Then
        pd.testing.assert_series_equal(full.iloc[:200], truncated)


class TestWindowOpen:
    """창 — 반감기 기준 · 신고가 기준"""

    def test_반감기_기준은_말일로_당긴_날부터_열린다(self) -> None:
        """
        목적: 기준일 + N개월(없는 날은 그 달 말일)부터 열린다.

        Given: 기준일 2020-01-31 · 1개월
        When: 창을 낸다
        Then: 2020-02-28 은 닫히고 2020-02-29 부터 열린다
        """
        # Given
        days = _days("2020-01-01", "2020-04-30")
        flags = pd.Series(False, index=days)

        # When
        opened = window_open(days, _buy_leg(start_months=1), pd.Timestamp("2020-01-31"), flags)

        # Then
        opened_by_day = pd.Series(opened, index=days)
        assert not opened_by_day["2020-01-01":"2020-02-28"].any()
        assert opened_by_day["2020-02-29":].all()

    def test_신고가_기준은_새_신고가가_나면_다시_닫힌다(self) -> None:
        """
        목적: 창은 그날까지의 종가로만 정한다 — 가장 최근 신고가에서 N개월이 지나야 열리고, 새 신고가가 나면 닫힌다.
        기준 반감기 앞의 신고가는 세지 않는다.

        Given: 기준일 2020-02-15 앞에 신고가(01-10), 뒤에 신고가 둘(03-10 · 05-20) · 1개월
        When: 창을 낸다
        Then: 04-10 ~ 05-19 열림 · 05-20 ~ 06-19 닫힘 · 06-20 부터 열림 · 03-01 닫힘(기준일 앞 신고가로 열리지 않음)
        """
        # Given
        days = _days("2020-01-01", "2020-12-31")
        close = _values(days, 100.0, {"2020-01-10": 200.0, "2020-03-10": 210.0, "2020-05-20": 220.0})
        leg = _buy_leg(start_anchor=SPLIT_ANCHOR_HIGH, start_months=1)

        # When
        opened = pd.Series(window_open(days, leg, pd.Timestamp("2020-02-15"), new_high_flags(close)), index=days)

        # Then
        assert not opened["2020-03-01"]
        assert not opened["2020-04-09"]
        assert opened["2020-04-10":"2020-05-19"].all()
        assert not opened["2020-05-20":"2020-06-19"].any()
        assert opened["2020-06-20":].all()

    def test_기준일_뒤_신고가가_없으면_열리지_않는다(self) -> None:
        """
        목적: 신고가 기준은 「반감기 뒤 신고가가 한 번 이상」이 전제다.

        Given: 기준일 앞에만 신고가
        When: 창을 낸다
        Then: 한 번도 열리지 않는다
        """
        # Given
        days = _days("2020-01-01", "2020-12-31")
        close = _values(days, 100.0, {"2020-01-10": 200.0})
        leg = _buy_leg(start_anchor=SPLIT_ANCHOR_HIGH, start_months=1)

        # When
        opened = window_open(days, leg, pd.Timestamp("2020-02-15"), new_high_flags(close))

        # Then
        assert not opened.any()

    def test_달력만_조합에는_창이_없다(self) -> None:
        """
        목적: 달력만 조합의 창을 물으면 호출이 틀린 것이다.

        Given: 달력만 조합
        When: 창을 낸다
        Then: ValueError
        """
        # Given
        days = _days("2020-01-01", "2020-01-31")

        # When / Then
        with pytest.raises(ValueError, match="달력만"):
            window_open(days, _calendar_leg(SPLIT_SIDE_BUY, 10), days[0], pd.Series(False, index=days))


class TestTrancheDeadlines:
    """회차 기한"""

    def test_마지막_기한에서_간격만큼_앞으로_말일로_당긴다(self) -> None:
        """
        목적: 기한은 기준일 + (마지막 − 간격 × 남은 회차)개월이고, 없는 날은 그 달 말일이다.

        Given: 기준일 2020-01-31 · 마지막 7 · 3회 · 2개월 간격
        When: 기한을 낸다
        Then: 3 · 5 · 7개월 → 04-30 · 06-30 · 08-31
        """
        # When
        deadlines = tranche_deadlines(
            pd.Timestamp("2020-01-31"), 7, tranches=TRANCHES, step_months=STEP, month_end=False
        )

        # Then
        assert deadlines == [pd.Timestamp("2020-04-30"), pd.Timestamp("2020-06-30"), pd.Timestamp("2020-08-31")]

    def test_월말이면_기준일_더하기_N개월이_속한_달의_말일이다(self) -> None:
        """
        목적: 달력 매달 분할의 체결일 정의(결정 54) — 같은 날짜가 아니라 그 달의 말일이다. 연말 · 윤년 2월 · 30일 달을 밟고,
            기준일 31일(달력 산술이 이미 말일로 당긴 날)도 그 달 말일에 머물러 한 달 더 밀리지 않는다.

        Given: (가) 기준일 2019-10-10 · 마지막 6 · 3회 · 2개월 간격 (2 · 4 · 6개월)
            (나) 기준일 2020-01-31 · 마지막 3 · 3회 · 1개월 간격 (1 · 2 · 3개월)
        When: 월말 · 같은 날짜로 각각 기한을 낸다
        Then: (가) 월말은 2019-12-31 · 2020-02-29 · 2020-04-30, 같은 날짜는 2019-12-10 · 2020-02-10 · 2020-04-10
            (나) 월말은 2020-02-29 · 2020-03-31 · 2020-04-30
        """
        # Given
        anchor = pd.Timestamp("2019-10-10")
        end_of_month_anchor = pd.Timestamp("2020-01-31")

        # When
        month_end = tranche_deadlines(anchor, 6, tranches=TRANCHES, step_months=STEP, month_end=True)
        same_day = tranche_deadlines(anchor, 6, tranches=TRANCHES, step_months=STEP, month_end=False)
        from_31st = tranche_deadlines(end_of_month_anchor, 3, tranches=TRANCHES, step_months=1, month_end=True)

        # Then
        assert month_end == [pd.Timestamp("2019-12-31"), pd.Timestamp("2020-02-29"), pd.Timestamp("2020-04-30")]
        assert same_day == [pd.Timestamp("2019-12-10"), pd.Timestamp("2020-02-10"), pd.Timestamp("2020-04-10")]
        assert from_31st == [pd.Timestamp("2020-02-29"), pd.Timestamp("2020-03-31"), pd.Timestamp("2020-04-30")]

    def test_첫_기한이_기준일_앞이면_멈춘다(self) -> None:
        """
        목적: 기한이 기준 반감기 앞이면 격자 값이 틀린 것이다.

        Given: 마지막 3 · 3회 · 2개월 간격 → 첫 기한 −1개월
        When: 기한을 낸다
        Then: ValueError
        """
        # When / Then
        with pytest.raises(ValueError, match="기한"):
            tranche_deadlines(pd.Timestamp("2020-01-31"), 3, tranches=TRANCHES, step_months=STEP, month_end=False)


class TestLegFills:
    """회차 체결일 — min(온체인 판정일 다음 거래일, 달력 기한)"""

    ANCHOR = pd.Timestamp("2020-01-15")
    DAYS = _days("2020-01-01", "2021-06-30")

    def _fills(
        self, leg: SplitLeg, overrides: dict[str, float], days: pd.DatetimeIndex | None = None
    ) -> list[TrancheFill]:
        """기본값 3.0 에 몇 날을 심은 값으로 회차를 낸다. 기한은 6 · 8 · 10개월(07-15 · 09-15 · 11-15)."""
        trading_days = self.DAYS if days is None else days
        values = _values(trading_days, 3.0, overrides)

        return leg_fills(
            trading_days,
            leg,
            self.ANCHOR,
            trigger_values=values,
            new_highs=pd.Series(False, index=trading_days),
            tranches=TRANCHES,
            step_months=STEP,
            month_end=False,
        )

    def test_온체인이_먼저면_판정일_다음날_달력이_먼저면_기한일(self) -> None:
        """
        목적: 체결 규칙의 기본형. 창이 열리기 전의 문턱 도달은 세지 않는다.

        Given: 창 02-15 부터 · 02-10 에 1.0(창 전) · 03-01 에 1.8 · 03-05 에 1.4 · 0.5 이하 없음
        When: 회차를 낸다
        Then: 03-02 온체인 · 03-06 온체인 · 11-15 달력
        """
        # When
        fills = self._fills(_buy_leg(), {"2020-02-10": 1.0, "2020-03-01": 1.8, "2020-03-05": 1.4})

        # Then
        assert [(fill.fill_day, fill.trigger) for fill in fills] == [
            (pd.Timestamp("2020-03-02"), SPLIT_TRIGGER_ONCHAIN),
            (pd.Timestamp("2020-03-06"), SPLIT_TRIGGER_ONCHAIN),
            (pd.Timestamp("2020-11-15"), SPLIT_TRIGGER_CALENDAR),
        ]
        assert all(fill.reason == REASON_NONE for fill in fills)

    def test_하루에_두_문턱을_넘으면_두_회차가_같은_날이다(self) -> None:
        """
        목적: 문턱은 회차마다 따로 센다 — 한 날이 두 문턱을 모두 넘으면 두 회차가 함께 체결된다.

        Given: 03-01 에 1.0 (2.0 · 1.5 둘 다 이하)
        When: 회차를 낸다
        Then: 첫째 · 둘째가 03-02
        """
        # When
        fills = self._fills(_buy_leg(), {"2020-03-01": 1.0})

        # Then
        assert fills[0].fill_day == fills[1].fill_day == pd.Timestamp("2020-03-02")

    def test_기한_전날_판정이면_온체인_기한_당일_판정이면_달력(self) -> None:
        """
        목적: 동점(다음날 = 기한)은 온체인이고, 기한 당일의 도달은 다음날이 기한 뒤라 달력이 이긴다.

        Given: 셋째 회차 기한 11-15. (가) 11-14 에 0.4 (나) 11-15 에 0.4
        When: 회차를 낸다
        Then: (가) 11-15 온체인 (나) 11-15 달력
        """
        # When
        before = self._fills(_buy_leg(), {"2020-11-14": 0.4})
        same_day = self._fills(_buy_leg(), {"2020-11-15": 0.4})

        # Then
        assert (before[2].fill_day, before[2].trigger) == (pd.Timestamp("2020-11-15"), SPLIT_TRIGGER_ONCHAIN)
        assert (same_day[2].fill_day, same_day[2].trigger) == (pd.Timestamp("2020-11-15"), SPLIT_TRIGGER_CALENDAR)

    def test_매도는_문턱_이상에_닿으면_그_회차다(self) -> None:
        """
        목적: 매도 문턱은 올라가는 순서이고 「이상」으로 센다 — 같은 값이면 닿은 것이다.

        Given: 매도 문턱 4 · 5 · 6, 03-01 에 정확히 4.0
        When: 회차를 낸다
        Then: 첫째만 03-02 온체인, 나머지는 기한
        """
        # Given
        leg = SplitLeg(
            side=SPLIT_SIDE_SELL,
            threshold=SPLIT_THRESHOLD_BOOK,
            levels=(4.0, 5.0, 6.0),
            start_anchor=SPLIT_ANCHOR_HALVING,
            start_months=1,
            last_deadline=10,
        )

        # When
        fills = self._fills(leg, {"2020-03-01": 4.0})

        # Then
        assert [fill.trigger for fill in fills] == [
            SPLIT_TRIGGER_ONCHAIN,
            SPLIT_TRIGGER_CALENDAR,
            SPLIT_TRIGGER_CALENDAR,
        ]
        assert fills[0].fill_day == pd.Timestamp("2020-03-02")

    def test_기한이_데이터_뒤면_체결_전이다(self) -> None:
        """
        목적: 표본 보존 — 체결하지 못한 회차도 사유와 함께 남는다. 마지막 날의 도달은 다음날이 없어 체결 전이다.

        Given: 데이터가 2020-08-31 까지 · 08-31 에 0.4 · 셋째 기한 11-15
        When: 회차를 낸다
        Then: 셋째가 체결 전 (체결일 · 계기가 비고 사유가 붙는다)
        """
        # When
        fills = self._fills(_buy_leg(), {"2020-08-31": 0.4}, days=_days("2020-01-01", "2020-08-31"))

        # Then
        assert fills[2].fill_day is None
        assert fills[2].trigger is None
        assert fills[2].reason == REASON_SPLIT_PENDING

    def test_달력만이면_기한마다_체결한다(self) -> None:
        """
        목적: 달력만 조합은 온체인 값 없이 기한일 종가에 산다.

        Given: 달력만 · 마지막 10
        When: 회차를 낸다
        Then: 07-15 · 09-15 · 11-15 전부 달력
        """
        # When
        fills = leg_fills(
            self.DAYS,
            _calendar_leg(SPLIT_SIDE_BUY, 10),
            self.ANCHOR,
            trigger_values=None,
            new_highs=pd.Series(False, index=self.DAYS),
            tranches=TRANCHES,
            step_months=STEP,
            month_end=False,
        )

        # Then
        assert [(fill.fill_day, fill.trigger) for fill in fills] == [
            (pd.Timestamp("2020-07-15"), SPLIT_TRIGGER_CALENDAR),
            (pd.Timestamp("2020-09-15"), SPLIT_TRIGGER_CALENDAR),
            (pd.Timestamp("2020-11-15"), SPLIT_TRIGGER_CALENDAR),
        ]

    def test_월말이면_달력만_회차가_그_달의_말일_종가에_체결한다(self) -> None:
        """
        목적: 월말 정의가 회차 기한을 거쳐 체결일까지 간다 — 기한과 체결일이 같은 말일이다.

        Given: 달력만 · 마지막 10 · 기준일 2020-01-15 (6 · 8 · 10개월) · 월말
        When: 회차를 낸다
        Then: 07-31 · 09-30 · 11-30 전부 달력이고 기한도 그날이다
        """
        # When
        fills = leg_fills(
            self.DAYS,
            _calendar_leg(SPLIT_SIDE_BUY, 10),
            self.ANCHOR,
            trigger_values=None,
            new_highs=pd.Series(False, index=self.DAYS),
            tranches=TRANCHES,
            step_months=STEP,
            month_end=True,
        )

        # Then
        expected = [pd.Timestamp("2020-07-31"), pd.Timestamp("2020-09-30"), pd.Timestamp("2020-11-30")]
        assert [(fill.deadline, fill.fill_day, fill.trigger) for fill in fills] == [
            (day, day, SPLIT_TRIGGER_CALENDAR) for day in expected
        ]

    def test_빈_값은_문턱에_닿지_않는다(self) -> None:
        """
        목적: 값이 없는 날(공개 지연)은 판정하지 않는다.

        Given: 03-01 이 빈 값 · 그 밖은 3.0
        When: 회차를 낸다
        Then: 전부 달력
        """
        # When
        fills = self._fills(_buy_leg(), {"2020-03-01": np.nan})

        # Then
        assert all(fill.trigger == SPLIT_TRIGGER_CALENDAR for fill in fills)

    def test_뒤를_잘라도_그_전에_체결한_회차가_같다(self) -> None:
        """
        목적: 미래 참조 감시 — 자른 끝 전에 체결한 회차는 뒤의 데이터와 상관없이 같다.

        Given: 전체(2021-06-30 까지)와 2020-09-20 에서 자른 데이터 · 같은 값
        When: 회차를 낸다
        Then: 자른 끝 전에 체결한 회차가 같고, 뒤의 회차는 체결 전이다
        """
        # Given
        overrides = {"2020-03-01": 1.8, "2020-10-01": 1.2}
        cut = _days("2020-01-01", "2020-09-20")

        # When
        full = self._fills(_buy_leg(), overrides)
        truncated = self._fills(_buy_leg(), overrides, days=cut)

        # Then
        for whole, part in zip(full, truncated, strict=True):
            if whole.fill_day is not None and whole.fill_day <= cut[-1]:
                assert part == whole
            else:
                assert part.reason == REASON_SPLIT_PENDING

    def test_신고가_창과_순위_문턱도_뒤를_잘라도_그_전에_체결한_회차가_같다(self) -> None:
        """
        목적: 미래 참조 감시 — 신고가 창과 4년 순위 문턱도 그날까지의 값으로만 정한다. 신고가 · 순위를 자른 입력에서
        «다시» 계산해 견주므로, 창이나 순위가 뒤의 종가 · 값을 보면 체결일이 달라진다. 회차 수(2)와 기준일(31일)도
        실제와 다르게 둔다.

        Given: 기준일 2020-01-31 뒤 신고가 02-10 · 05-20(창은 03-10 ~ 05-19 에 열린다) · 날마다 오르는 값에
            03-15 하루만 가장 낮은 값(순위가 바닥) · 신고가 뒤 1개월 창 · 순위 문턱 0.3 · 0.1 · 회차 2 · 기한 간격 1 ·
            마지막 7개월(기한 07-31 · 08-31)
        When: 전체와 2020-06-15 에서 자른 입력으로 신고가 · 순위 · 회차를 각각 낸다
        Then: 자른 끝 전에 체결한 회차(03-16 둘)는 같고 나머지는 체결 전이다 — 견준 체결 회차가 하나 이상이다
        """
        # Given
        days = _days("2019-01-01", "2020-12-31")
        close = _values(days, 100.0, {"2020-02-10": 200.0, "2020-05-20": 210.0})
        dip = pd.Timestamp("2020-03-15")
        values = pd.Series([-1.0 if day == dip else float(step) for step, day in enumerate(days)], index=days)
        leg = SplitLeg(
            side=SPLIT_SIDE_BUY,
            threshold=SPLIT_THRESHOLD_RANK,
            levels=(0.3, 0.1),
            start_anchor=SPLIT_ANCHOR_HIGH,
            start_months=1,
            last_deadline=7,
        )
        anchor = pd.Timestamp("2020-01-31")
        cut = days[days <= pd.Timestamp("2020-06-15")]

        def fills_for(trading_days: pd.DatetimeIndex) -> list[TrancheFill]:
            return leg_fills(
                trading_days,
                leg,
                anchor,
                trigger_values=trailing_rank(values.loc[trading_days], years=1, min_days=30),
                new_highs=new_high_flags(close.loc[trading_days]),
                tranches=2,
                step_months=1,
                month_end=False,
            )

        # When
        full = fills_for(days)
        truncated = fills_for(cut)

        # Then
        compared = 0
        for whole, part in zip(full, truncated, strict=True):
            if whole.fill_day is not None and whole.fill_day <= cut[-1]:
                assert part == whole
                compared += 1
            else:
                assert part.reason == REASON_SPLIT_PENDING
        assert compared >= 1

    def test_기한이_데이터_안인데_거래일에_없으면_멈춘다(self) -> None:
        """
        목적: 휴장이 없는 시세라 빠진 날은 데이터의 빈틈이다 — 옮기면 다른 날을 잰다.

        Given: 첫째 기한 07-15 가 빠진 거래일
        When: 달력만 회차를 낸다
        Then: ValueError
        """
        # Given
        days = self.DAYS.drop(pd.Timestamp("2020-07-15"))

        # When / Then
        with pytest.raises(ValueError, match="거래일"):
            leg_fills(
                days,
                _calendar_leg(SPLIT_SIDE_BUY, 10),
                self.ANCHOR,
                trigger_values=None,
                new_highs=pd.Series(False, index=days),
                tranches=TRANCHES,
                step_months=STEP,
                month_end=False,
            )

    @pytest.mark.parametrize(
        ("leg", "values", "message"),
        [
            (_buy_leg(levels=(2.0, 1.5)), True, "회차"),
            (_buy_leg(levels=(1.5, 2.0, 0.5)), True, "순서"),
            (_buy_leg(), False, "값"),
            (_buy_leg(start_months=-1), True, "창"),
        ],
    )
    def test_조합과_입력이_어긋나면_멈춘다(self, leg: SplitLeg, values: bool, message: str) -> None:
        """
        목적: 문턱 수가 회차 수와 다르거나, 매수 문턱이 내려가는 순서가 아니거나, 문턱 조합에 값을 주지 않거나,
        창이 기준 반감기 앞으로 열리면 멈춘다 — 온체인 회차가 반감기 앞에 체결되는 것을 막는 자리가 창 하나다.

        Given: 어긋난 조합
        When: 회차를 낸다
        Then: ValueError
        """
        # When / Then
        with pytest.raises(ValueError, match=message):
            leg_fills(
                self.DAYS,
                leg,
                self.ANCHOR,
                trigger_values=_values(self.DAYS, 3.0, {}) if values else None,
                new_highs=pd.Series(False, index=self.DAYS),
                tranches=TRANCHES,
                step_months=STEP,
                month_end=False,
            )


class TestPositionResult:
    """포지션 성적 — 평균 단가 · 수익률 · 평균 단가 대비 최악"""

    DAYS = _days("2020-01-01", "2020-01-10")
    # 매수 01-02(100) · 01-04(50), 매도 01-07(90) · 01-09(110)
    FRAME = _frame(
        DAYS,
        closes={"2020-01-02": 100.0, "2020-01-04": 50.0, "2020-01-07": 90.0, "2020-01-09": 110.0},
        lows={
            "2020-01-02": 10.0,
            "2020-01-03": 80.0,
            "2020-01-04": 45.0,
            "2020-01-05": 40.0,
            "2020-01-06": 70.0,
            "2020-01-07": 85.0,
            "2020-01-08": 95.0,
            "2020-01-09": 100.0,
            "2020-01-10": 1.0,
        },
    )
    BUYS = (_fill("2020-01-02", SPLIT_TRIGGER_ONCHAIN), _fill("2020-01-04", SPLIT_TRIGGER_CALENDAR))
    SELLS = (_fill("2020-01-07", SPLIT_TRIGGER_CALENDAR), _fill("2020-01-09", SPLIT_TRIGGER_CALENDAR))

    def test_평균_매수가는_조화평균_매도가는_산술평균이다(self) -> None:
        """
        목적: 같은 금액으로 사고 같은 수량씩 판다.

        Given: 매수 100 · 50, 매도 90 · 110
        When: 성적을 낸다
        Then: 평균 매수가 2 ÷ (1/100 + 1/50) = 66.67 · 평균 매도가 100 · 수익률 +50%
        """
        # When
        result = position_result(self.FRAME, self.BUYS, self.SELLS)

        # Then
        assert result.avg_buy_price == pytest.approx(200.0 / 3.0, abs=1e-9)
        assert result.avg_sell_price == pytest.approx(100.0, abs=1e-9)
        assert result.return_rate == pytest.approx(0.5, abs=1e-12)
        assert result.reason == REASON_NONE

    def test_평균_단가_대비_최악은_그날_전에_산_회차만_센다(self) -> None:
        """
        목적: 그날 종가에 산 회차는 그날 장중을 겪지 않았다. 첫 매수일과 마지막 매도일 뒤도 세지 않는다.

        Given: 01-04 저가 45 (그날 두 번째 회차를 샀다) · 01-02 저가 10 · 01-10 저가 1
        When: 성적을 낸다
        Then: 01-04 에는 첫 회차(100)만 들고 있어 45 ÷ 100 − 1 = −55% 가 최악이다
            (두 회차 단가 66.67 로 세면 −32.5%, 01-02 나 01-10 을 세면 더 깊다)
        """
        # When
        result = position_result(self.FRAME, self.BUYS, self.SELLS)

        # Then
        assert result.worst_vs_cost == pytest.approx(-0.55, abs=1e-12)

    def test_날짜와_계기_수(self) -> None:
        """
        목적: 첫 매수일 · 마지막 매도일 · 보유 날 수 · 계기별 회차 수.

        Given: 위 포지션
        When: 성적을 낸다
        Then: 01-02 · 01-09 · 7일 · 매수 (온체인 1, 달력 1) · 매도 (0, 2)
        """
        # When
        result = position_result(self.FRAME, self.BUYS, self.SELLS)

        # Then
        assert (result.first_buy_day, result.last_sell_day, result.hold_days) == (
            pd.Timestamp("2020-01-02"),
            pd.Timestamp("2020-01-09"),
            7,
        )
        assert (result.buy_counts, result.sell_counts) == ((1, 1), (0, 2))

    def test_달력만이면_격자_칸_수익률의_평균과_같다(self) -> None:
        """
        목적: 같은 금액으로 사고 같은 수량씩 팔면 포지션 수익률 = (매수 회차 × 매도 회차) 칸 수익률의 평균이다(결정 ㊱).

        Given: 매수 셋 · 매도 셋의 서로 다른 종가
        When: 성적을 낸다
        Then: 아홉 칸 (매도가 ÷ 매수가 − 1) 의 평균과 같다
        """
        # Given
        days = _days("2020-01-01", "2020-01-12")
        buys = {"2020-01-02": 80.0, "2020-01-03": 120.0, "2020-01-05": 95.0}
        sells = {"2020-01-08": 130.0, "2020-01-10": 70.0, "2020-01-11": 150.0}
        frame = _frame(days, closes={**buys, **sells}, lows={})
        buy_fills = tuple(_fill(day, SPLIT_TRIGGER_CALENDAR) for day in buys)
        sell_fills = tuple(_fill(day, SPLIT_TRIGGER_CALENDAR) for day in sells)

        # When
        result = position_result(frame, buy_fills, sell_fills)

        # Then
        cells = [sell / buy - 1.0 for buy in buys.values() for sell in sells.values()]
        assert result.return_rate == pytest.approx(sum(cells) / len(cells), abs=1e-12)

    def test_다음_반감기가_없으면_매도_전이고_최악은_데이터_끝까지_센다(self) -> None:
        """
        목적: 표본 보존 — 끝나지 않은 포지션도 결과가 있고, 매수 쪽 값은 남는다.

        Given: 매도 회차가 없다(다음 반감기가 목록에 없다)
        When: 성적을 낸다
        Then: 사유 「다음 반감기가 반감기 목록에 없음」 · 수익률이 비고 · 최악은 01-10 저가 1 까지 센다
        """
        # When
        result = position_result(self.FRAME, self.BUYS, None)

        # Then
        assert result.reason == REASON_NO_NEXT_HALVING
        assert result.return_rate is None and result.avg_sell_price is None
        assert result.avg_buy_price == pytest.approx(200.0 / 3.0, abs=1e-9)
        assert result.worst_vs_cost == pytest.approx(1.0 / (200.0 / 3.0) - 1.0, abs=1e-12)

    def test_매수_회차가_남으면_매수_중_매도_회차가_남으면_매도_중이다(self) -> None:
        """
        목적: 끝나지 않은 이유를 가른다 — 매수가 남은 것이 먼저다.

        Given: (가) 둘째 매수 체결 전 (나) 둘째 매도 체결 전
        When: 성적을 낸다
        Then: (가) 매수 회차가 남음 · 평균 매수가는 산 회차만 (나) 매도 회차가 남음
        """
        # When
        buying = position_result(self.FRAME, (self.BUYS[0], _fill(None, None)), None)
        selling = position_result(self.FRAME, self.BUYS, (self.SELLS[0], _fill(None, None)))

        # Then
        assert buying.reason == REASON_POSITION_BUYING
        assert buying.avg_buy_price == pytest.approx(100.0, abs=1e-9)
        assert selling.reason == REASON_POSITION_SELLING
        assert selling.return_rate is None

    def test_매도가_마지막_매수보다_앞이면_불변조건_위반이다(self) -> None:
        """
        목적: 매도는 매수가 끝난 뒤에만 온다 — 어기면 평균 단가가 정의되지 않는다.

        Given: 01-03 매도 · 01-04 매수
        When: 성적을 낸다
        Then: RuntimeError
        """
        # When / Then
        with pytest.raises(RuntimeError, match="내부 불변조건"):
            position_result(self.FRAME, self.BUYS, (_fill("2020-01-03", SPLIT_TRIGGER_CALENDAR), self.SELLS[1]))


class TestSplitLegs:
    """조합 목록"""

    def test_문턱이_있는_조합은_창마다_달력만은_기한마다_하나다(self) -> None:
        """
        목적: 달력만은 창이 결과를 바꾸지 않아 창 없이 한 조합이다 — 같은 결과를 여러 행으로 내면 평평한 구간처럼 보인다.

        Given: 반감기 창 둘 · 신고가 창 하나 · 기한 둘
        When: 매수 조합을 만든다
        Then: (창 3 × 문턱 2 + 달력만 1) × 기한 2 = 14, 서로 다르고, 달력만은 창이 없다
        """
        # When
        legs = split_legs(
            SPLIT_SIDE_BUY,
            halving_starts=(5, 7),
            high_starts=(2,),
            last_deadlines=(11, 13),
            book_levels=(2.0, 1.5, 0.5),
            rank_levels=(0.3, 0.2, 0.1),
        )

        # Then
        assert len(legs) == 14
        assert len(set(legs)) == 14
        calendar_only = [leg for leg in legs if leg.threshold == SPLIT_THRESHOLD_NONE]
        assert len(calendar_only) == 2
        assert all(leg.start_anchor is None and leg.start_months is None and leg.levels == () for leg in calendar_only)
        assert {leg.threshold for leg in legs} == {SPLIT_THRESHOLD_NONE, SPLIT_THRESHOLD_BOOK, SPLIT_THRESHOLD_RANK}


class TestSplitGrid:
    """격자 전부 — 표본 보존 · 가로 칸 · 등식 · 불변조건"""

    HALVINGS = (_halving("2019-01-20"), _halving("2020-03-20"), _halving("2021-05-20"))
    DAYS = _days("2018-01-01", "2021-12-31")

    @staticmethod
    def _buy_legs() -> tuple[SplitLeg, ...]:
        """매수 조합 — 반감기 창 하나 · 신고가 창 하나 · 기한 둘."""
        return split_legs(
            SPLIT_SIDE_BUY,
            halving_starts=(2,),
            high_starts=(1,),
            last_deadlines=(7, 9),
            book_levels=(1.2, 1.0, 0.8),
            rank_levels=(0.3, 0.2, 0.1),
        )

    @staticmethod
    def _sell_legs() -> tuple[SplitLeg, ...]:
        """매도 조합 — 다음 반감기 창 하나 · 기한 하나."""
        return split_legs(
            SPLIT_SIDE_SELL,
            halving_starts=(0,),
            high_starts=(),
            last_deadlines=(5,),
            book_levels=(1.6, 1.8, 2.0),
            rank_levels=(0.7, 0.8, 0.9),
        )

    def _grid(self, halvings: tuple[Halving, ...] | None = None) -> tuple[pd.DataFrame, SplitGrid]:
        """오르내리는 합성 시세와 MVRV 로 격자를 낸다."""
        steps = np.arange(len(self.DAYS))
        close = 100.0 * np.exp(0.6 * np.sin(steps / 60.0) + steps / 2000.0)
        frame = pd.DataFrame({COL_DATE: self.DAYS, COL_CLOSE: close, COL_LOW: close * 0.97})
        mvrv = pd.Series(1.4 + 0.7 * np.sin(steps / 60.0), index=self.DAYS)
        grid = split_grid(
            frame,
            mvrv,
            self.HALVINGS if halvings is None else halvings,
            self._buy_legs(),
            self._sell_legs(),
            tranches=TRANCHES,
            step_months=STEP,
            rank_years=1,
            rank_min_days=30,
        )

        return frame, grid

    def test_회차_포지션_조합_행_수가_격자와_같다(self) -> None:
        """
        목적: 표본 보존 — 체결 전 회차와 끝나지 않은 포지션도 행이 있다.

        Given: 반감기 셋 · 매수 조합 · 매도 조합
        When: 격자를 낸다
        Then: 회차 = (매수 + 매도) × 반감기 × 회차 수 · 포지션 = 매수 × 매도 × 반감기 · 조합 = 매수 × 매도
        """
        # When
        _, grid = self._grid()

        # Then
        halvings, buys, sells = len(self.HALVINGS), len(self._buy_legs()), len(self._sell_legs())
        assert len(grid.fills) == (buys + sells) * halvings * TRANCHES
        assert len(grid.positions) == buys * sells * halvings
        assert len(grid.combinations) == buys * sells

    def test_마지막_반감기의_포지션은_다음_반감기가_없어_끝나지_않는다(self) -> None:
        """
        목적: 다음 반감기가 목록에 없으면 매도 회차가 정의되지 않는다 — 행은 남고 사유가 붙는다.

        Given: 반감기 셋
        When: 격자를 낸다
        Then: 마지막 반감기의 매도 회차와 포지션에 그 사유가 붙는다
        """
        # When
        _, grid = self._grid()

        # Then
        last = self.HALVINGS[-1].label
        sell_rows = grid.fills[(grid.fills[COL_HALVING] == last) & (grid.fills[COL_SPLIT_SIDE] == SPLIT_SIDE_SELL)]
        assert (sell_rows[COL_EXCLUDED_REASON] == REASON_NO_NEXT_HALVING).all()
        assert sell_rows[COL_SPLIT_FILL_DATE].isna().all()
        last_positions = grid.positions[grid.positions[COL_HALVING] == last]
        assert (last_positions[COL_EXCLUDED_REASON] != REASON_NONE).all()
        assert last_positions[COL_POSITION_RETURN].isna().all()

    def test_조합_표의_가로_칸과_집계가_포지션_표와_같다(self) -> None:
        """
        목적: 조합 표는 포지션 표를 가로로 펼친 것이다 — 두 표가 같은 값을 다르게 실으면 안 된다.

        Given: 격자
        When: 조합 표를 포지션 표와 견준다
        Then: 사이클별 수익률 칸 · 끝난 포지션 수 · 평균 · 중앙값 · 합계 · 최악 · 오른 건수가 같다
        """
        # When
        _, grid = self._grid()

        # Then
        combination = grid.combinations.iloc[0]
        positions = grid.positions.iloc[: len(self.HALVINGS)]
        returns = positions[COL_POSITION_RETURN]
        for halving, value in zip(self.HALVINGS, returns, strict=True):
            column = COL_CYCLE_RETURN_TEMPLATE.format(halving=halving.label)
            assert (pd.isna(value) and pd.isna(combination[column])) or combination[column] == pytest.approx(value)
            assert COL_CYCLE_WORST_TEMPLATE.format(halving=halving.label) in grid.combinations.columns
        finished = returns.dropna()
        assert combination[COL_FINISHED_COUNT] == len(finished)
        assert combination[COL_MEAN] == pytest.approx(finished.mean(), abs=1e-12)
        assert combination[COL_MEDIAN] == pytest.approx(finished.median(), abs=1e-12)
        assert combination[COL_SPLIT_TOTAL] == pytest.approx(finished.sum(), abs=1e-12)
        assert combination[COL_MIN] == pytest.approx(finished.min(), abs=1e-12)
        assert combination[COL_POSITIVE_COUNT] == int((finished > 0).sum())

    def test_달력만_조합은_기한일_종가로만_산다(self) -> None:
        """
        목적: 등식 — 달력만 매수 × 달력만 매도 포지션은 기한일 종가끼리의 칸 평균과 같다.

        Given: 첫 반감기 · 달력만 매수(마지막 7 → 3 · 5 · 7개월) · 달력만 매도(다음 반감기 뒤 1 · 3 · 5개월)
        When: 격자를 낸다
        Then: 그 포지션의 수익률이 아홉 칸 평균과 같다
        """
        # When
        frame, grid = self._grid()

        # Then
        close = frame.set_index(COL_DATE)[COL_CLOSE]
        first, second = self.HALVINGS[0].day, self.HALVINGS[1].day
        buy_prices = [close[first + pd.DateOffset(months=months)] for months in (3, 5, 7)]
        sell_prices = [close[second + pd.DateOffset(months=months)] for months in (1, 3, 5)]
        cells = [sell / buy - 1.0 for buy in buy_prices for sell in sell_prices]
        calendar_buy = next(
            index
            for index, leg in enumerate(self._buy_legs())
            if leg.threshold == SPLIT_THRESHOLD_NONE and leg.last_deadline == 7
        )
        calendar_sell = next(
            index for index, leg in enumerate(self._sell_legs()) if leg.threshold == SPLIT_THRESHOLD_NONE
        )
        row = (calendar_buy * len(self._sell_legs()) + calendar_sell) * len(self.HALVINGS)
        position = grid.positions.iloc[row]
        assert position[COL_HALVING] == self.HALVINGS[0].label
        assert position[COL_POSITION_RETURN] == pytest.approx(sum(cells) / len(cells), abs=1e-12)
        assert position[COL_AVG_BUY_PRICE] == pytest.approx(3.0 / sum(1.0 / price for price in buy_prices), abs=1e-9)

    def test_회차_표의_계기는_온체인_또는_달력뿐이다(self) -> None:
        """
        목적: 체결한 회차에는 계기가 있고, 체결 전 회차에는 없다.

        Given: 격자
        When: 회차 표를 본다
        Then: 체결일이 있으면 계기가 둘 중 하나, 없으면 비어 있다
        """
        # When
        _, grid = self._grid()

        # Then
        filled = grid.fills[COL_SPLIT_FILL_DATE].notna()
        assert set(grid.fills.loc[filled, COL_SPLIT_TRIGGER]) <= {SPLIT_TRIGGER_ONCHAIN, SPLIT_TRIGGER_CALENDAR}
        assert grid.fills.loc[~filled, COL_SPLIT_TRIGGER].isna().all()

    def test_매수_기한이_다음_반감기_뒤면_불변조건_위반이다(self) -> None:
        """
        목적: 매도는 매수가 끝난 뒤에만 온다 — 매수 기한이 다음 반감기를 넘으면 격자 값이 틀린 것이다.

        Given: 간격 5개월짜리 반감기 (매수 마지막 기한 7 · 9개월보다 짧다)
        When: 격자를 낸다
        Then: RuntimeError
        """
        # Given
        halvings = (_halving("2019-01-20"), _halving("2019-06-20"))

        # When / Then
        with pytest.raises(RuntimeError, match="내부 불변조건"):
            self._grid(halvings)


class TestCalendarSplitGrid:
    """달력 매달 분할 — 폭마다 반감기 뒤 매달 사고 다음 반감기 뒤 매달 판다. 회차는 그 달의 말일이다 (결정 51 · 52 · 54)

    **픽스처 폭은 실제(매수 6 · 매도 10회 · 1개월 간격)와 다르다** — 쪽마다 2 · 3회 · 2개월 간격이고, 한 폭 안에서도
    매수와 매도의 회차 수가 다르다. 함수가 상수를 안에서 읽거나 한쪽 회차 수를 다른 쪽에 쓰면 회차 날짜와 행 수가
    어긋나 걸린다. 반감기일은 20일이라 같은 날짜와 말일이 언제나 갈린다.
    """

    HALVINGS = (_halving("2019-01-20"), _halving("2020-03-20"), _halving("2021-05-20"))
    DAYS = _days("2018-01-01", "2021-12-31")
    # 「가」 — 반감기 뒤 5 · 7개월에 사고(2회) 다음 반감기 뒤 2 · 4 · 6개월에 판다(3회).
    # 「나」 — 반감기 뒤 5 · 7 · 9개월에 사고(3회) 다음 반감기 뒤 3 · 5개월에 판다(2회)
    SPLITS = (
        CalendarSplit(name="가", buy_tranches=2, buy_last_deadline=7, sell_tranches=3, sell_last_deadline=6),
        CalendarSplit(name="나", buy_tranches=3, buy_last_deadline=9, sell_tranches=2, sell_last_deadline=5),
    )
    STEP = 2
    # 고점 창 — 실제(24개월)와 다르다. 이 클래스는 손절 표를 보지 않고, 두 폭의 매수가 이 창보다 늦게 끝나기만 하면 된다
    PEAK_WINDOW = 3
    # 첫 반감기 「가」 포지션 — 매수 2019-06-30(80) · 2019-08-31(120), 매도 2020-05-31(150) · 2020-07-31(210) ·
    # 2020-09-30(240). 같은 날짜(06-20 · 08-20 · …)는 기본 가격 100 이라 말일을 놓치면 값이 달라진다.
    # 저가: 첫 매수일 50(그날 산 회차는 그날 장중을 겪지 않는다) · 07-10 60 · 09-01 84 · 마지막 매도 다음날 10
    FRAME = _frame(
        DAYS,
        closes={
            "2019-06-30": 80.0,
            "2019-08-31": 120.0,
            "2020-05-31": 150.0,
            "2020-07-31": 210.0,
            "2020-09-30": 240.0,
        },
        lows={"2019-06-30": 50.0, "2019-07-10": 60.0, "2019-09-01": 84.0, "2020-10-01": 10.0},
    )

    def _grid(
        self,
        frame: pd.DataFrame | None = None,
        halvings: tuple[Halving, ...] | None = None,
        splits: tuple[CalendarSplit, ...] | None = None,
    ) -> CalendarSplitGrid:
        return calendar_split_grid(
            self.FRAME if frame is None else frame,
            self.HALVINGS if halvings is None else halvings,
            self.SPLITS if splits is None else splits,
            step_months=self.STEP,
            peak_window_months=self.PEAK_WINDOW,
            forks=(),
        )

    def _position(self, grid: CalendarSplitGrid, name: str, halving: Halving) -> pd.Series:
        rows = grid.positions[
            (grid.positions[COL_CALENDAR_SPLIT] == name) & (grid.positions[COL_HALVING] == halving.label)
        ]
        assert len(rows) == 1

        return rows.iloc[0]

    def test_회차_포지션_행_수가_폭_반감기_쪽마다_회차와_같다(self) -> None:
        """
        목적: 표본 보존 — 체결 전 회차 · 다음 반감기가 없는 매도 회차 · 끝나지 않은 포지션도 행이 있다.
            매수 · 매도의 회차 수가 달라도 쪽마다 제 회차 수만큼 행이 있다.

        Given: 반감기 셋 · 폭 둘(「가」 매수 2 · 매도 3, 「나」 매수 3 · 매도 2)
        When: 격자를 낸다
        Then: 회차 = 반감기 × Σ(매수 회차 + 매도 회차) = 3 × (5 + 5) · 포지션 = 폭 × 반감기 · 쪽마다 행 수가 제 회차 수다
        """
        # When
        grid = self._grid()

        # Then
        halvings = len(self.HALVINGS)
        assert len(grid.fills) == halvings * sum(split.buy_tranches + split.sell_tranches for split in self.SPLITS)
        assert len(grid.positions) == len(self.SPLITS) * halvings
        for split in self.SPLITS:
            rows = grid.fills[grid.fills[COL_CALENDAR_SPLIT] == split.name]
            assert int((rows[COL_SPLIT_SIDE] == SPLIT_SIDE_BUY).sum()) == halvings * split.buy_tranches
            assert int((rows[COL_SPLIT_SIDE] == SPLIT_SIDE_SELL).sum()) == halvings * split.sell_tranches

    def test_회차는_반감기일_더하기_N개월이_속한_달의_말일_종가이고_매도는_다음_반감기에서_센다(self) -> None:
        """
        목적: 회차 날짜는 달력 산술 하나로 정해진다 — 그 달의 말일이고(결정 54), 매수는 그 반감기 · 매도는 다음 반감기가 기준이다.

        Given: 「나」 · 첫 반감기(2019-01-20) — 다음 반감기 2020-03-20
        When: 회차 표를 본다
        Then: 매수 2019-06-30 · 08-31 · 10-31(5 · 7 · 9개월) · 매도 2020-06-30 · 08-31(3 · 5개월). 기한과 체결일이 같고,
            종가는 그날 종가이고 기준 반감기는 매수가 첫 반감기 · 매도가 둘째 반감기다. 체결한 회차는 전부 말일이다
        """
        # When
        grid = self._grid()

        # Then
        rows = grid.fills[(grid.fills[COL_CALENDAR_SPLIT] == "나") & (grid.fills[COL_HALVING] == self.HALVINGS[0].label)]
        close = self.FRAME.set_index(COL_DATE)[COL_CLOSE]
        expected = {
            SPLIT_SIDE_BUY: (["2019-06-30", "2019-08-31", "2019-10-31"], [5, 7, 9], self.HALVINGS[0].label),
            SPLIT_SIDE_SELL: (["2020-06-30", "2020-08-31"], [3, 5], self.HALVINGS[1].label),
        }
        for side, (days, months, anchor) in expected.items():
            part = rows[rows[COL_SPLIT_SIDE] == side]
            assert part[COL_SPLIT_TRANCHE].tolist() == list(range(1, len(days) + 1))
            assert part[COL_SPLIT_FILL_DATE].tolist() == [pd.Timestamp(day) for day in days]
            assert part[COL_SPLIT_DEADLINE].tolist() == [pd.Timestamp(day) for day in days]
            assert part[COL_MONTHS_SINCE_HALVING].tolist() == months
            assert part[COL_SPLIT_FILL_CLOSE].tolist() == [close[pd.Timestamp(day)] for day in days]
            assert (part[COL_SPLIT_ANCHOR_HALVING] == anchor).all()
            assert (part[COL_EXCLUDED_REASON] == REASON_NONE).all()
        filled = pd.DatetimeIndex(grid.fills[COL_SPLIT_FILL_DATE].dropna())
        assert len(filled) > 0
        assert bool(filled.is_month_end.all())

    def test_포지션_성적은_손으로_센_값과_같다(self) -> None:
        """
        목적: 산식 고정 — 같은 금액으로 사고(조화평균) 같은 양씩 팔며(산술평균), 최악은 그날 «전»에 산 회차의 단가로 센다.
            매도 회차 수가 매수와 달라도 평균 매도가는 매도 회차만으로 낸다.

        Given: 「가」 · 첫 반감기 — 매수 80 · 120(2회), 매도 150 · 210 · 240(3회). 저가 07-10 60(첫 회차만 보유, 단가 80) ·
            09-01 84(두 회차, 단가 96) · 첫 매수일 50 · 마지막 매도 다음날 10
        When: 포지션 표를 본다
        Then: 평균 매수가 2 ÷ (1/80 + 1/120) = 96 · 평균 매도가 200 · 수익률 200 ÷ 96 − 1 · 최악 60 ÷ 80 − 1 = −25%
            (첫 매수일 · 마지막 매도 뒤의 저가는 세지 않는다) · 보유 2019-06-30 ~ 2020-09-30 = 458일 · 매수 2회 · 매도 3회
        """
        # When
        position = self._position(self._grid(), "가", self.HALVINGS[0])

        # Then
        assert position[COL_AVG_BUY_PRICE] == pytest.approx(96.0, abs=1e-9)
        assert position[COL_AVG_SELL_PRICE] == pytest.approx(200.0, abs=1e-9)
        assert position[COL_POSITION_RETURN] == pytest.approx(200.0 / 96.0 - 1.0, abs=1e-12)
        assert position[COL_WORST_VS_COST] == pytest.approx(-0.25, abs=1e-12)
        assert (position[COL_FIRST_BUY_DATE], position[COL_LAST_SELL_DATE], position[COL_HOLD_DAYS]) == (
            pd.Timestamp("2019-06-30"),
            pd.Timestamp("2020-09-30"),
            458,
        )
        assert (position[COL_BUY_CALENDAR_COUNT], position[COL_SELL_CALENDAR_COUNT]) == (2, 3)
        assert position[COL_EXCLUDED_REASON] == REASON_NONE

    def test_식별_칸이_폭과_쪽마다_회차_수와_첫_마지막_기한을_싣는다(self) -> None:
        """
        목적: 표만 보고 어느 폭인지 · 언제부터 언제까지 몇 번 사고팔았는지 안다 — 첫 기한은 그쪽의 마지막 기한 · 회차 수 ·
            간격에서 나온다.

        Given: 「나」(매수 3회 · 마지막 9, 매도 2회 · 마지막 5, 간격 2개월)
        When: 포지션 표와 회차 표를 본다
        Then: 매수 3회 · 5 ~ 9 · 매도 2회 · 3 ~ 5 · 칸 순서가 계약대로다
        """
        # When
        grid = self._grid()

        # Then
        position = self._position(grid, "나", self.HALVINGS[0])
        assert (
            position[COL_BUY_TRANCHES],
            position[COL_BUY_FIRST_DEADLINE],
            position[COL_BUY_LAST_DEADLINE],
            position[COL_SELL_TRANCHES],
            position[COL_SELL_FIRST_DEADLINE],
            position[COL_SELL_LAST_DEADLINE],
        ) == (3, 5, 9, 2, 3, 5)
        assert list(grid.fills.columns) == [
            COL_CALENDAR_SPLIT,
            COL_SPLIT_SIDE,
            COL_HALVING,
            COL_SPLIT_ANCHOR_HALVING,
            COL_SPLIT_TRANCHE,
            COL_SPLIT_DEADLINE,
            COL_SPLIT_FILL_DATE,
            COL_MONTHS_SINCE_HALVING,
            COL_SPLIT_FILL_CLOSE,
            COL_EXCLUDED_REASON,
        ]
        assert list(grid.positions.columns) == [
            COL_CALENDAR_SPLIT,
            COL_BUY_TRANCHES,
            COL_BUY_FIRST_DEADLINE,
            COL_BUY_LAST_DEADLINE,
            COL_SELL_TRANCHES,
            COL_SELL_FIRST_DEADLINE,
            COL_SELL_LAST_DEADLINE,
            COL_HALVING,
            COL_AVG_BUY_PRICE,
            COL_AVG_SELL_PRICE,
            COL_POSITION_RETURN,
            COL_WORST_VS_COST,
            COL_FIRST_BUY_DATE,
            COL_LAST_SELL_DATE,
            COL_HOLD_DAYS,
            COL_BUY_CALENDAR_COUNT,
            COL_SELL_CALENDAR_COUNT,
            COL_EXCLUDED_REASON,
        ]

    def test_마지막_반감기는_매도_회차가_없고_매수가_남으면_그_사유가_먼저다(self) -> None:
        """
        목적: 끝나지 않은 포지션을 0 으로 채우지 않고 사유를 단다 — 매수가 남음 → 다음 반감기 없음 순이다.

        Given: 마지막 반감기(2021-05-20) · 데이터 끝 2021-12-31 — 「가」는 두 회차를 다 샀고(10-31 · 12-31),
            「나」의 셋째 회차(2022-02-28)는 데이터 뒤다
        When: 마지막 반감기의 행을 본다
        Then: 매도 회차는 전부 「다음 반감기 없음」이고 쪽마다 제 회차 수만큼이다 · 「가」 포지션도 그 사유 ·
            「나」 포지션은 「매수 회차가 남음」이고 셋째 매수 회차는 「체결 전」이다. 수익률은 비었다
        """
        # When
        grid = self._grid()

        # Then
        last = self.HALVINGS[-1]
        fills = grid.fills[grid.fills[COL_HALVING] == last.label]
        sells = fills[fills[COL_SPLIT_SIDE] == SPLIT_SIDE_SELL]
        assert (sells[COL_EXCLUDED_REASON] == REASON_NO_NEXT_HALVING).all()
        assert sells[COL_SPLIT_FILL_DATE].isna().all()
        assert sells.groupby(COL_CALENDAR_SPLIT).size().to_dict() == {"가": 3, "나": 2}
        pending = fills[(fills[COL_CALENDAR_SPLIT] == "나") & (fills[COL_SPLIT_SIDE] == SPLIT_SIDE_BUY)]
        assert pending[COL_EXCLUDED_REASON].tolist() == [REASON_NONE, REASON_NONE, REASON_SPLIT_PENDING]
        assert pending[COL_SPLIT_DEADLINE].tolist()[-1] == pd.Timestamp("2022-02-28")
        assert self._position(grid, "가", last)[COL_EXCLUDED_REASON] == REASON_NO_NEXT_HALVING
        assert self._position(grid, "나", last)[COL_EXCLUDED_REASON] == REASON_POSITION_BUYING
        assert grid.positions[grid.positions[COL_HALVING] == last.label][COL_POSITION_RETURN].isna().all()

    def test_뒤를_잘라도_그_전에_체결한_회차와_끝난_포지션이_같다(self) -> None:
        """
        목적: 미래 참조 감시 — 회차와 성적은 그날까지의 시세로만 정해진다.

        Given: 같은 시세를 2021-08-31 에서 자른 입력 — 둘째 반감기 「가」 포지션의 둘째 매도(2021-09-30)가 데이터 뒤다
        When: 두 입력으로 격자를 낸다
        Then: 자른 입력에서 체결한 회차의 날짜 · 종가와 끝난 포지션의 성적이 전체 입력과 같고,
            매도가 남은 포지션은 「매도 회차가 남음」이다
        """
        # Given
        cut = pd.Timestamp("2021-08-31")
        short = self.FRAME[self.FRAME[COL_DATE] <= cut].reset_index(drop=True)

        # When
        full, part = self._grid(), self._grid(frame=short)

        # Then
        filled = part.fills[COL_SPLIT_FILL_DATE].notna()
        assert filled.any()
        for column in (COL_SPLIT_FILL_DATE, COL_SPLIT_FILL_CLOSE):
            assert part.fills.loc[filled, column].tolist() == full.fills.loc[filled, column].tolist()
        finished = part.positions[COL_EXCLUDED_REASON] == REASON_NONE
        assert finished.any()
        for column in (COL_AVG_BUY_PRICE, COL_AVG_SELL_PRICE, COL_POSITION_RETURN, COL_WORST_VS_COST):
            np.testing.assert_allclose(
                part.positions.loc[finished, column].to_numpy(dtype=float),
                full.positions.loc[finished, column].to_numpy(dtype=float),
                rtol=0.0,
                atol=1e-12,
            )
        assert self._position(part, "가", self.HALVINGS[1])[COL_EXCLUDED_REASON] == REASON_POSITION_SELLING

    def test_매수_마지막_회차가_다음_반감기와_같거나_뒤면_멈춘다(self) -> None:
        """
        목적: 매도는 매수가 끝난 뒤에만 온다 — 폭과 반감기 간격이 어긋나면 입력이 틀린 것이다.

        Given: 간격 5개월짜리 반감기 둘 (「가」의 매수 마지막 7개월보다 짧다)
        When: 격자를 낸다
        Then: ValueError
        """
        # Given
        halvings = (_halving("2019-01-20"), _halving("2019-06-20"))

        # When / Then
        with pytest.raises(ValueError, match="다음 반감기"):
            self._grid(halvings=halvings)

    @pytest.mark.parametrize(
        ("splits", "message"),
        [
            ((), "폭"),
            (
                (
                    CalendarSplit(name="가", buy_tranches=2, buy_last_deadline=7, sell_tranches=3, sell_last_deadline=6),
                    CalendarSplit(name="가", buy_tranches=3, buy_last_deadline=9, sell_tranches=2, sell_last_deadline=5),
                ),
                "이름",
            ),
            (
                (CalendarSplit(name="다", buy_tranches=5, buy_last_deadline=3, sell_tranches=2, sell_last_deadline=5),),
                "기준 반감기 앞",
            ),
            (
                (CalendarSplit(name="라", buy_tranches=3, buy_last_deadline=9, sell_tranches=3, sell_last_deadline=3),),
                "기준 반감기 앞",
            ),
            (
                (CalendarSplit(name="마", buy_tranches=0, buy_last_deadline=7, sell_tranches=3, sell_last_deadline=6),),
                "회차 수",
            ),
            (
                (CalendarSplit(name="바", buy_tranches=2, buy_last_deadline=7, sell_tranches=0, sell_last_deadline=6),),
                "회차 수",
            ),
        ],
    )
    def test_폭이_없거나_이름이_겹치거나_첫_회차가_반감기_앞이거나_한쪽_회차가_없으면_멈춘다(
        self, splits: tuple[CalendarSplit, ...], message: str
    ) -> None:
        """
        목적: 폭 목록의 입력 검사 — 이름은 식별 칸이라 겹치면 두 폭의 행이 섞인다. 첫 회차가 기준 반감기 앞이면
            반감기 «전»에 사거나 다음 반감기 «전»에 팔게 되고, 한쪽 회차가 0 이면 사지 않거나 팔지 않는 포지션이 된다.

        Given: 빈 목록 · 이름이 겹치는 둘 · 첫 매수 회차가 반감기 앞인 폭(5회 · 마지막 3개월 · 간격 2개월) ·
            첫 매도 회차가 다음 반감기 앞인 폭(3회 · 마지막 3개월 · 간격 2개월) · 매수 회차 0 · 매도 회차 0 인 폭
        When: 격자를 낸다
        Then: ValueError
        """
        # When / Then
        with pytest.raises(ValueError, match=message):
            self._grid(splits=splits)


class TestCalendarSplitStops:
    """달력 매달 분할의 저점 이탈 손절 — 매수 기간에는 손절이 없고, 마지막 매수일에 고정한 손절선(사이클 고점 뒤 최저
    종가)을 종가가 깨면 다음 거래일 종가에 남은 보유를 전부 판다 (설계 결정 58)

    **픽스처는 실제와 다르다** — 고점 창 2개월(실제 24) · 매수 2회 · 매도 3회 · 2개월 간격. 고점 창을 상수에서 읽으면
    손절선이 다른 날을 문다. 반감기일은 20일이라 회차가 말일로 간다.
    """

    HALVINGS = (_halving("2019-01-20"), _halving("2020-03-20"), _halving("2021-05-20"))
    DAYS = _days("2018-01-01", "2022-06-30")
    SPLITS = (CalendarSplit(name="가", buy_tranches=2, buy_last_deadline=7, sell_tranches=3, sell_last_deadline=6),)
    STEP = 2
    PEAK_WINDOW = 2
    # 첫 반감기 포지션 — 사이클 고점 2019-02-10(300 · 고점 창 안) · 첫 매수 «앞»의 바닥 2019-05-15(40) · 매수 2019-06-30(80) ·
    # 08-31(120) · 첫 매수 뒤 최저 2019-07-15(60) · 매수가 끝난 뒤 2019-10-10(50 — 첫 매수 뒤 최저보다 낮고 손절선보다 높다) ·
    # 매도 2020-05-31(150) · 07-31(210) · 09-30(240).
    # 둘째 반감기 사이클 — 고점 2020-04-10(500) · 그 뒤 2020-04-20(45) · 06-10(42). 둘째 사이클로 손절선을 다시 세면
    # 06-10 의 42 가 이탈이 된다. 셋째 반감기 — 고점 2021-06-01(400) · 그 뒤 최저 2021-09-10(90) · 매수 10-31(110) · 12-31(130)
    CLOSES = {
        "2019-02-10": 300.0,
        "2019-05-15": 40.0,
        "2019-06-30": 80.0,
        "2019-07-15": 60.0,
        "2019-08-31": 120.0,
        "2019-10-10": 50.0,
        "2020-04-10": 500.0,
        "2020-04-20": 45.0,
        "2020-05-31": 150.0,
        "2020-06-10": 42.0,
        "2020-07-31": 210.0,
        "2020-09-30": 240.0,
        "2021-06-01": 400.0,
        "2021-09-10": 90.0,
        "2021-10-31": 110.0,
        "2021-12-31": 130.0,
    }
    # 첫 반감기 포지션의 평균 매수가(같은 금액 — 조화평균)와 무손절 평균 매도가
    AVG_BUY = 96.0
    AVG_SELL = 200.0
    # 셋째 반감기 포지션의 평균 매수가
    THIRD_AVG_BUY = 2.0 / (1.0 / 110.0 + 1.0 / 130.0)
    # 첫 반감기 포지션이 들고 있는 동안의 포크 — 비율 0.1
    FORK = HardFork(
        name="CCC",
        height=7,
        block_time=datetime(2020, 1, 15, 12, 0, tzinfo=UTC),
        price_day=pd.Timestamp("2020-01-15"),
        coin_price=10.0,
        btc_price=100.0,
    )

    def _market(self, overrides: dict[str, float] | None = None, end: str | None = None) -> pd.DataFrame:
        """픽스처 시세 — 몇 날을 바꾸거나 뒤를 자른다. 저가는 종가와 같다."""
        frame = _frame(self.DAYS, closes={**self.CLOSES, **(overrides or {})}, lows={})
        if end is None:
            return frame

        return frame[frame[COL_DATE] <= pd.Timestamp(end)].reset_index(drop=True)

    def _grid(
        self,
        frame: pd.DataFrame,
        *,
        forks: tuple[HardFork, ...] = (),
        splits: tuple[CalendarSplit, ...] | None = None,
        peak_window: int | None = None,
    ) -> CalendarSplitGrid:
        return calendar_split_grid(
            frame,
            self.HALVINGS,
            self.SPLITS if splits is None else splits,
            step_months=self.STEP,
            peak_window_months=self.PEAK_WINDOW if peak_window is None else peak_window,
            forks=forks,
        )

    def _row(self, grid: CalendarSplitGrid, halving: Halving, method: str) -> pd.Series:
        rows = grid.stops[(grid.stops[COL_HALVING] == halving.label) & (grid.stops[COL_STOP_METHOD] == method)]
        assert len(rows) == 1

        return rows.iloc[0]

    def test_행은_폭_반감기마다_무손절과_저점_이탈_둘이고_칸_순서가_계약대로다(self) -> None:
        """
        목적: 표본 보존 — 끝나지 않은 포지션도 두 행이 다 있다. 무손절 행이 손절이 무엇을 막았는지의 대조축이다.

        Given: 폭 하나 · 반감기 셋
        When: 격자를 낸다
        Then: 손절 표 행 = 폭 × 반감기 × 2 · 포지션마다 무손절 · 저점 이탈 순 · 칸 순서가 계약대로다
        """
        # When
        grid = self._grid(self._market())

        # Then
        assert len(grid.stops) == len(self.SPLITS) * len(self.HALVINGS) * 2
        for halving in self.HALVINGS:
            methods = grid.stops[grid.stops[COL_HALVING] == halving.label][COL_STOP_METHOD].tolist()
            assert methods == [NO_STOP_LABEL, STOP_METHOD_LOW_BREAK]
        assert list(grid.stops.columns) == [
            COL_CALENDAR_SPLIT,
            COL_HALVING,
            COL_STOP_METHOD,
            COL_AVG_BUY_PRICE,
            COL_AVG_SELL_PRICE,
            COL_POSITION_RETURN,
            COL_WORST_VS_COST,
            COL_LAST_SELL_DATE,
            COL_FORK_SHARE,
            COL_STOP_LINE_DATE,
            COL_STOP_LINE_CLOSE,
            COL_STOP_LINE_VS_COST,
            COL_BREAK_DATE,
            COL_STOP_SELL_DATE,
            COL_STOP_SELL_CLOSE,
            COL_SOLD_BEFORE_STOP,
            COL_EXCLUDED_REASON,
        ]

    def test_무손절_행은_포지션_표와_같다(self) -> None:
        """
        목적: 무손절 행은 새 계산이 아니라 포지션 표의 성적 그대로다 — 두 표가 같은 포지션을 다르게 말하지 않는다.

        Given: 픽스처 시세
        When: 격자를 낸다
        Then: 반감기마다 무손절 행의 평균 매수가 · 평균 매도가 · 수익률 · 최악 · 마지막 매도일 · 사유가 포지션 표와 같다
        """
        # When
        grid = self._grid(self._market())

        # Then
        for halving in self.HALVINGS:
            stop = self._row(grid, halving, NO_STOP_LABEL)
            position = grid.positions[grid.positions[COL_HALVING] == halving.label].iloc[0]
            for column in (COL_AVG_BUY_PRICE, COL_AVG_SELL_PRICE, COL_POSITION_RETURN, COL_WORST_VS_COST):
                np.testing.assert_allclose(float(stop[column]), float(position[column]), rtol=0.0, atol=1e-12)
            assert pd.isna(stop[COL_LAST_SELL_DATE]) == pd.isna(position[COL_LAST_SELL_DATE])
            if not pd.isna(position[COL_LAST_SELL_DATE]):
                assert stop[COL_LAST_SELL_DATE] == position[COL_LAST_SELL_DATE]
            assert stop[COL_EXCLUDED_REASON] == position[COL_EXCLUDED_REASON]

    def test_손절선은_마지막_매수일까지의_사이클_고점_뒤_최저_종가다(self) -> None:
        """
        목적: 손절선은 첫 매수 뒤 최저(기준 B)가 아니라 사이클 고점 뒤 최저(기준 A)다 — 바닥이 첫 매수 «앞»이면 둘이 갈린다.

        Given: 첫 반감기 — 바닥 2019-05-15(40)이 첫 매수(06-30) 앞이고, 매수가 끝난 뒤 2019-10-10 종가 50 은
            첫 매수 뒤 최저(60)보다 낮고 손절선(40)보다 높다
        When: 격자를 낸다
        Then: 두 행 모두 손절선 2019-05-15 · 40 · 평균 매수가 대비 40 ÷ 96 − 1 · 이탈 없음 ·
            저점 이탈 행의 수익률이 무손절과 같다(200 ÷ 96 − 1)
        """
        # When
        grid = self._grid(self._market())

        # Then
        first = self.HALVINGS[0]
        for method in (NO_STOP_LABEL, STOP_METHOD_LOW_BREAK):
            row = self._row(grid, first, method)
            assert row[COL_STOP_LINE_DATE] == pd.Timestamp("2019-05-15")
            assert row[COL_STOP_LINE_CLOSE] == pytest.approx(40.0, abs=1e-12)
            assert row[COL_STOP_LINE_VS_COST] == pytest.approx(40.0 / self.AVG_BUY - 1.0, abs=1e-12)
            assert pd.isna(row[COL_BREAK_DATE])
        stop = self._row(grid, first, STOP_METHOD_LOW_BREAK)
        assert stop[COL_POSITION_RETURN] == pytest.approx(self.AVG_SELL / self.AVG_BUY - 1.0, abs=1e-12)
        assert pd.isna(stop[COL_STOP_SELL_DATE]) and pd.isna(stop[COL_SOLD_BEFORE_STOP])

    def test_매수_기간_중에_저점을_깨면_팔지_않고_그_값이_손절선이_된다(self) -> None:
        """
        목적: 매수 기간에는 손절이 없다 — 그 기간에 난 더 낮은 종가는 손절선이 된다(「이전에 형성된 최저점」).

        Given: 매수 기간 중 2019-07-20 종가 30, 매수가 끝난 뒤 2019-10-10 종가 35 (40 보다 낮고 30 보다 높다)
        When: 격자를 낸다
        Then: 손절선 2019-07-20 · 30 · 이탈 없음 · 저점 이탈 행이 무손절과 같은 성적이다
        """
        # When
        grid = self._grid(self._market({"2019-07-20": 30.0, "2019-10-10": 35.0}))

        # Then
        stop = self._row(grid, self.HALVINGS[0], STOP_METHOD_LOW_BREAK)
        assert (stop[COL_STOP_LINE_DATE], stop[COL_STOP_LINE_CLOSE]) == (pd.Timestamp("2019-07-20"), 30.0)
        assert pd.isna(stop[COL_BREAK_DATE]) and pd.isna(stop[COL_STOP_SELL_DATE])
        assert stop[COL_POSITION_RETURN] == pytest.approx(self.AVG_SELL / self.AVG_BUY - 1.0, abs=1e-12)

    def test_이탈하면_다음_거래일_종가에_남은_보유를_전부_판다(self) -> None:
        """
        목적: 산식 고정 — 이탈은 종가로 판정하고 다음 거래일 종가에 남은 보유를 «전부» 판다. 무손절 행은 들고 간다.

        Given: 매수가 끝난 뒤 · 매도 전 2019-11-05 종가 35(< 40), 2019-11-06 종가 45
        When: 격자를 낸다
        Then: 저점 이탈 행 — 이탈 11-05 · 손절 매도 11-06 · 45 · 손절 전에 판 매도 회차 0 · 평균 매도가 45 ·
            수익률 45 ÷ 96 − 1 · 마지막 매도일 11-06 · 끝남. 무손절 행 — 이탈일은 같고 손절 매도가 없고 수익률 200 ÷ 96 − 1
        """
        # When
        grid = self._grid(self._market({"2019-11-05": 35.0, "2019-11-06": 45.0}))

        # Then
        first = self.HALVINGS[0]
        stop = self._row(grid, first, STOP_METHOD_LOW_BREAK)
        assert stop[COL_BREAK_DATE] == pd.Timestamp("2019-11-05")
        assert (stop[COL_STOP_SELL_DATE], stop[COL_STOP_SELL_CLOSE]) == (pd.Timestamp("2019-11-06"), 45.0)
        assert stop[COL_SOLD_BEFORE_STOP] == 0
        assert stop[COL_AVG_SELL_PRICE] == pytest.approx(45.0, abs=1e-9)
        assert stop[COL_POSITION_RETURN] == pytest.approx(45.0 / self.AVG_BUY - 1.0, abs=1e-12)
        assert stop[COL_LAST_SELL_DATE] == pd.Timestamp("2019-11-06")
        assert stop[COL_EXCLUDED_REASON] == REASON_NONE
        plain = self._row(grid, first, NO_STOP_LABEL)
        assert plain[COL_BREAK_DATE] == pd.Timestamp("2019-11-05")
        assert pd.isna(plain[COL_STOP_SELL_DATE]) and pd.isna(plain[COL_SOLD_BEFORE_STOP])
        assert plain[COL_POSITION_RETURN] == pytest.approx(self.AVG_SELL / self.AVG_BUY - 1.0, abs=1e-12)

    def test_매도_기간_중에_이탈하면_그_전에_판_회차는_그대로고_다음_반감기가_지나도_손절선은_그대로다(self) -> None:
        """
        목적: 「매도 기간이든 아니든 전량」 — 이미 판 회차는 그 값 그대로, 남은 회차만 손절 매도로 간다. 손절선은 포지션을
            산 반감기의 것이라 다음 반감기 사이클의 고점 · 저점으로 다시 세지 않는다.

        Given: 둘째 반감기 사이클의 저점 뒤 2020-06-10 종가 42 (둘째 사이클로 다시 세면 이탈, 첫 손절선 40 보다는 높다),
            첫 매도(05-31 · 150) 뒤 2020-06-15 종가 39(< 40), 06-16 종가 42.5
        When: 격자를 낸다
        Then: 이탈 06-15(06-10 이 아니다) · 손절 전에 판 매도 회차 1 · 손절 매도 06-16 · 42.5 ·
            평균 매도가 (150 + 42.5 + 42.5) ÷ 3 · 손절선은 2019-05-15 · 40 그대로
        """
        # When
        grid = self._grid(self._market({"2020-06-15": 39.0, "2020-06-16": 42.5}))

        # Then
        stop = self._row(grid, self.HALVINGS[0], STOP_METHOD_LOW_BREAK)
        assert stop[COL_BREAK_DATE] == pd.Timestamp("2020-06-15")
        assert stop[COL_SOLD_BEFORE_STOP] == 1
        assert (stop[COL_STOP_SELL_DATE], stop[COL_STOP_SELL_CLOSE]) == (pd.Timestamp("2020-06-16"), 42.5)
        average = (150.0 + 42.5 + 42.5) / 3.0
        assert stop[COL_AVG_SELL_PRICE] == pytest.approx(average, abs=1e-9)
        assert stop[COL_POSITION_RETURN] == pytest.approx(average / self.AVG_BUY - 1.0, abs=1e-12)
        assert (stop[COL_STOP_LINE_DATE], stop[COL_STOP_LINE_CLOSE]) == (pd.Timestamp("2019-05-15"), 40.0)

    def test_마지막_매도일에_이탈하면_팔_것이_남지_않아_무손절과_같다(self) -> None:
        """
        목적: 경계 — 이탈한 날 종가에 마지막 회차를 이미 판다. 다음 거래일에 팔 것이 없다.

        Given: 마지막 매도일 2020-09-30 종가 38(< 40)
        When: 격자를 낸다
        Then: 저점 이탈 행 — 이탈 09-30 · 손절 매도 없음 · 수익률이 무손절과 같다((150 + 210 + 38) ÷ 3 ÷ 96 − 1)
        """
        # When
        grid = self._grid(self._market({"2020-09-30": 38.0}))

        # Then
        first = self.HALVINGS[0]
        stop = self._row(grid, first, STOP_METHOD_LOW_BREAK)
        assert stop[COL_BREAK_DATE] == pd.Timestamp("2020-09-30")
        assert pd.isna(stop[COL_STOP_SELL_DATE]) and pd.isna(stop[COL_SOLD_BEFORE_STOP])
        expected = (150.0 + 210.0 + 38.0) / 3.0 / self.AVG_BUY - 1.0
        assert stop[COL_POSITION_RETURN] == pytest.approx(expected, abs=1e-12)
        assert self._row(grid, first, NO_STOP_LABEL)[COL_POSITION_RETURN] == pytest.approx(expected, abs=1e-12)

    def test_다음_반감기가_없는_포지션도_매수가_끝난_뒤_이탈하면_손절로_끝난다(self) -> None:
        """
        목적: 매도 회차가 아직 정해지지 않은 포지션(다음 반감기가 반감기 목록에 없다)도 손절선은 산다 — 이탈하면 전량 팔고 끝난다.

        Given: 셋째 반감기 — 손절선 2021-09-10(90), (가) 이탈 없음 (나) 2022-02-10 종가 85 · 02-11 종가 88
        When: 격자를 낸다
        Then: (가) 두 행 모두 「다음 반감기가 반감기 목록에 없음」 · 손절선 2021-09-10 · 90
            (나) 저점 이탈 행 — 끝남 · 손절 매도 02-11 · 88 · 수익률 88 ÷ 평균 매수가 − 1. 무손절 행은 그 사유 그대로이고 이탈일만 있다
        """
        # When
        quiet = self._grid(self._market())
        broken = self._grid(self._market({"2022-02-10": 85.0, "2022-02-11": 88.0}))

        # Then
        third = self.HALVINGS[2]
        for method in (NO_STOP_LABEL, STOP_METHOD_LOW_BREAK):
            row = self._row(quiet, third, method)
            assert row[COL_EXCLUDED_REASON] == REASON_NO_NEXT_HALVING
            assert (row[COL_STOP_LINE_DATE], row[COL_STOP_LINE_CLOSE]) == (pd.Timestamp("2021-09-10"), 90.0)
        stop = self._row(broken, third, STOP_METHOD_LOW_BREAK)
        assert stop[COL_EXCLUDED_REASON] == REASON_NONE
        assert (stop[COL_STOP_SELL_DATE], stop[COL_STOP_SELL_CLOSE]) == (pd.Timestamp("2022-02-11"), 88.0)
        assert stop[COL_POSITION_RETURN] == pytest.approx(88.0 / self.THIRD_AVG_BUY - 1.0, abs=1e-12)
        plain = self._row(broken, third, NO_STOP_LABEL)
        assert plain[COL_EXCLUDED_REASON] == REASON_NO_NEXT_HALVING
        assert plain[COL_BREAK_DATE] == pd.Timestamp("2022-02-10")
        assert pd.isna(plain[COL_POSITION_RETURN])

    def test_매수가_남은_포지션은_손절선이_없고_사유를_단다(self) -> None:
        """
        목적: 표본 보존 — 손절선은 매수가 끝나야 정해진다. 0 으로 채우지 않고 비운 채 사유를 단다.

        Given: 2021-11-15 에서 자른 시세 — 셋째 반감기의 둘째 매수(12-31)가 데이터 뒤다
        When: 격자를 낸다
        Then: 셋째 반감기 두 행 모두 「매수 회차가 남음」 · 손절선 · 이탈일 · 수익률이 비었다
        """
        # When
        grid = self._grid(self._market(end="2021-11-15"))

        # Then
        for method in (NO_STOP_LABEL, STOP_METHOD_LOW_BREAK):
            row = self._row(grid, self.HALVINGS[2], method)
            assert row[COL_EXCLUDED_REASON] == REASON_POSITION_BUYING
            assert pd.isna(row[COL_STOP_LINE_DATE]) and pd.isna(row[COL_STOP_LINE_CLOSE])
            assert pd.isna(row[COL_BREAK_DATE]) and pd.isna(row[COL_POSITION_RETURN])

    def test_뒤를_잘라도_그날까지의_이탈_판정과_손절로_끝난_성적이_같다(self) -> None:
        """
        목적: 미래 참조 감시 — 이탈은 그날 종가까지로 판정하고, 판정한 날에는 팔지 않는다(다음 거래일).

        Given: 2019-11-05 종가 35 · 11-06 종가 45 를 심은 시세와, 그것을 (가) 2019-12-31 (나) 2019-11-05 에서 자른 시세
        When: 셋으로 격자를 낸다
        Then: (가) 첫 반감기 저점 이탈 행이 전체 입력과 같다 — 이탈 11-05 · 손절 매도 11-06 · 수익률 · 끝남
            (나) 이탈 11-05 는 같고, 다음 거래일이 데이터 뒤라 손절 매도가 비고 「이탈 다음 거래일이 데이터 뒤」다
        """
        # Given
        overrides = {"2019-11-05": 35.0, "2019-11-06": 45.0}

        # When
        full = self._grid(self._market(overrides))
        later = self._grid(self._market(overrides, end="2019-12-31"))
        same_day = self._grid(self._market(overrides, end="2019-11-05"))

        # Then
        first = self.HALVINGS[0]
        whole = self._row(full, first, STOP_METHOD_LOW_BREAK)
        part = self._row(later, first, STOP_METHOD_LOW_BREAK)
        for column in (COL_BREAK_DATE, COL_STOP_SELL_DATE, COL_STOP_LINE_DATE, COL_EXCLUDED_REASON):
            assert part[column] == whole[column]
        for column in (COL_POSITION_RETURN, COL_STOP_SELL_CLOSE, COL_STOP_LINE_CLOSE):
            assert part[column] == pytest.approx(float(whole[column]), abs=1e-12)
        edge = self._row(same_day, first, STOP_METHOD_LOW_BREAK)
        assert edge[COL_BREAK_DATE] == pd.Timestamp("2019-11-05")
        assert pd.isna(edge[COL_STOP_SELL_DATE]) and pd.isna(edge[COL_POSITION_RETURN])
        assert edge[COL_EXCLUDED_REASON] == REASON_STOP_SELL_PENDING

    def test_하드포크_몫은_칸_몫의_평균이고_포크_전에_다_팔면_0이다(self) -> None:
        """
        목적: 포지션의 하드포크 몫은 (매수 회차 × 매도 회차) 칸마다의 몫의 평균이다 — 칸마다 돈이 같다. 수익률에 더하지 않는다.

        Given: 2020-01-15 포크(비율 0.1). (가) 이탈 없음 — 모든 칸이 포크일을 품는다 (나) 2019-11-05 이탈 · 11-06 전량 매도
        When: 격자를 낸다
        Then: (가) 두 행 모두 0.1 × (1 + 수익률) = 0.1 × 200 ÷ 96, 수익률은 포크가 없을 때와 같다
            (나) 저점 이탈 행 0 · 무손절 행 0.1 × 200 ÷ 96
        """
        # When
        quiet = self._grid(self._market(), forks=(self.FORK,))
        broken = self._grid(self._market({"2019-11-05": 35.0, "2019-11-06": 45.0}), forks=(self.FORK,))

        # Then
        first = self.HALVINGS[0]
        held = 0.1 * self.AVG_SELL / self.AVG_BUY
        for method in (NO_STOP_LABEL, STOP_METHOD_LOW_BREAK):
            row = self._row(quiet, first, method)
            assert row[COL_FORK_SHARE] == pytest.approx(held, abs=1e-12)
            assert row[COL_POSITION_RETURN] == pytest.approx(self.AVG_SELL / self.AVG_BUY - 1.0, abs=1e-12)
        assert self._row(broken, first, STOP_METHOD_LOW_BREAK)[COL_FORK_SHARE] == pytest.approx(0.0, abs=1e-12)
        assert self._row(broken, first, NO_STOP_LABEL)[COL_FORK_SHARE] == pytest.approx(held, abs=1e-12)
        assert pd.isna(self._row(quiet, self.HALVINGS[2], NO_STOP_LABEL)[COL_FORK_SHARE])

    @pytest.mark.parametrize("start", ["2019-03-01", "2019-04-01"])
    def test_시세가_반감기일보다_늦게_시작하면_멈춘다(self, start: str) -> None:
        """
        목적: 시세가 반감기일 뒤에 시작하면 고점 창의 앞이 비어 사이클 고점이 정해지지 않는다 — 남은 날 중 하나를 고점으로
            물거나 빈 창에서 판다스 오류로 죽지 않고, 무엇이 없는지 말하며 멈춘다.

        Given: 첫 반감기(2019-01-20)보다 늦게 시작하는 시세 — (가) 고점 창 안 2019-03-01 (진짜 고점 2019-02-10 이 빠진다)
            (나) 고점 창이 닫힌 뒤 2019-04-01. 둘 다 첫 반감기 포지션의 매수(06-30 · 08-31)는 시세 안이다
        When: 격자를 낸다
        Then: ValueError — 반감기일의 종가가 없다
        """
        # Given
        market = self._market()
        late = market[market[COL_DATE] >= pd.Timestamp(start)].reset_index(drop=True)

        # When / Then
        with pytest.raises(ValueError, match="반감기일"):
            self._grid(late)

    @pytest.mark.parametrize("peak_window", [0, 8])
    def test_고점_창이_1개월보다_작거나_매수가_고점_창보다_먼저_끝나면_멈춘다(self, peak_window: int) -> None:
        """
        목적: 손절선은 고점 창이 닫힌 뒤(매수가 끝난 날)에 고정된다 — 매수가 고점 창 안에서 끝나는 폭에는 정의되지 않는다.

        Given: (가) 고점 창 0개월 (나) 고점 창 8개월 — 폭의 마지막 매수(7개월)보다 길다
        When: 격자를 낸다
        Then: ValueError
        """
        # When / Then
        with pytest.raises(ValueError, match="고점 창"):
            self._grid(self._market(), peak_window=peak_window)
