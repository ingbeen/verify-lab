"""반감기_사이클 2단계의 시점 규칙 — 돌파 판정 · 사이클 배정 · 진입 일정 · 진입 전날 값을 고정한다.

| 무엇 | 정의 | 근거 |
| --- | --- | --- |
| 돌파 | 상태 = `값 ≥ 문턱`, 상태가 바뀐 날. 전날이나 그날 값이 비면 판정하지 않는다 | 창이 차는 첫날을 돌파로 세면 없는 신호가 생긴다 |
| 판정일 | 시세의 거래일만 | 진입가가 없는 날의 신호는 잴 수 없다 |
| 진입 | 판정일 다음 거래일 종가, 청산은 1단계의 달력월 규칙 | 설계 결정 ㉗ |
| 제외 | 첫 반감기 전 판정 · 진입일이 데이터 뒤 · 청산일이 데이터 뒤 — **행을 남긴다** | 결정 ㉘ ① · 표본 보존 |
| 진입 전날 값 | 일간은 진입일 − 1 일, 월간은 그날이나 그 전에 끝난 달 | 결정 ㉗ — Coin Metrics 의 d 값은 d+1 일에 완성된다 |

**픽스처 반감기는 실제와 다르게 고른다** — 31일 반감기로 말일 당김(1월 31일 + 1개월 = 2월 29일)을 검사한다.
"""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_OPEN
from verify_lab.measure.constants import (
    COL_ENTRY_CLOSE,
    COL_EXCLUDED_REASON,
    COL_EXIT_DATE,
    COL_FORWARD_RETURN,
    REASON_NONE,
    REASON_OUT_OF_RANGE,
)
from verify_lab.studies.halving_cycle.constants import (
    COL_HALVING,
    COL_HOLD_MONTHS,
    COL_INDICATOR_MONTH,
    COL_INDICATOR_SIGNAL,
    COL_INDICATOR_VALUE,
    COL_JUDGMENT_DATE,
    COL_MONTHLY_RSI,
    COL_MONTHS_SINCE_HALVING,
    COL_MVRV,
    COL_PREVIOUS_VALUE,
    COL_VALUE_DAY,
    POSITION_BEFORE_FIRST,
    REASON_BEFORE_FIRST_HALVING,
    REASON_ENTRY_AFTER_DATA,
    Halving,
    IndicatorSignal,
)
from verify_lab.studies.halving_cycle.indicator_signals import (
    crossing_days,
    entry_indicator_values,
    halving_for,
    indicator_signal_returns,
    months_since,
    signal_entries,
)

# 실제 반감기와 다른 날. 첫째는 31일이라 말일 당김이 걸린다
HALVINGS = (
    Halving(height=1, block_time=datetime(2020, 1, 31, 15, 0, tzinfo=UTC)),
    Halving(height=2, block_time=datetime(2021, 3, 29, 12, 0, tzinfo=UTC)),
)

START = "2020-01-01"
END = "2021-06-30"

UPWARD = IndicatorSignal(name="시험 상향", indicator=COL_MVRV, threshold=1.0, upward=True, meaning="시험")
MONTHLY = IndicatorSignal(name="시험 월간", indicator=COL_MONTHLY_RSI, threshold=50.0, upward=True, meaning="시험")

HOLDS = (1, 2)


def _prices() -> pd.DataFrame:
    """매일 거래하는 합성 시세. 종가가 날마다 달라 진입가 · 청산가를 날짜로 구별할 수 있다."""
    days = pd.date_range(START, END, freq="D")
    closes = np.linspace(100.0, 200.0, len(days))
    return pd.DataFrame({COL_DATE: days, COL_OPEN: closes, COL_CLOSE: closes})


def _daily_values() -> pd.Series:
    """1 을 네 번 상향 돌파하는 값 — 첫 반감기 전 · 유효 · 청산 전 · 데이터 마지막 날."""
    days = pd.date_range(START, END, freq="D")
    above = days == pd.Timestamp(END)
    for first, last in (("2020-01-10", "2020-01-20"), ("2020-06-15", "2020-07-01"), ("2021-06-10", "2021-06-20")):
        above |= (days >= pd.Timestamp(first)) & (days <= pd.Timestamp(last))
    return pd.Series(np.where(above, 1.5, 0.5), index=days)


def _monthly_values() -> pd.Series:
    """2020-08-31 에 50 을 상향 돌파하는 월말 값."""
    month_ends = pd.date_range("2020-01-31", "2021-05-31", freq="ME")
    return pd.Series(np.where(month_ends >= pd.Timestamp("2020-08-31"), 60.0, 40.0), index=month_ends)


class TestCrossingDays:
    """돌파 판정"""

    def test_upward_and_downward_crossings(self) -> None:
        """
        목적: 상태(값 ≥ 문턱)가 바뀐 날만 돌파이고, **문턱과 같은 값은 문턱 이상**이며, 빈 값을 사이에 둔 날은 판정하지 않는다.

        Given: 0.5 · 1.0 · 0.9 · 1.2 · 빈 값 · 1.5 · 0.8, 문턱 1.0
        When: 두 방향으로 돌파일을 찾는다
        Then: 상향은 둘째 · 넷째 날, 하향은 셋째 · 일곱째 날이다 (다섯째 · 여섯째 날은 앞이나 그날이 비어 판정 안 함)
        """
        # Given
        days = pd.date_range("2020-01-01", periods=7, freq="D")
        values = pd.Series([0.5, 1.0, 0.9, 1.2, np.nan, 1.5, 0.8], index=days)

        # When
        up = crossing_days(values, 1.0, upward=True)
        down = crossing_days(values, 1.0, upward=False)

        # Then
        assert list(up) == [days[1], days[3]]
        assert list(down) == [days[2], days[6]]

    def test_first_valid_day_is_not_a_crossing(self) -> None:
        """
        목적: 창이 차는 첫날은 돌파가 아니다 — 비교할 전날이 없다 (경계 조건).

        Given: 빈 값 · 2.0 · 0.5, 문턱 1.0
        When: 하향 돌파일을 찾는다
        Then: 셋째 날 하나다
        """
        # Given
        days = pd.date_range("2020-01-01", periods=3, freq="D")

        # When
        down = crossing_days(pd.Series([np.nan, 2.0, 0.5], index=days), 1.0, upward=False)

        # Then
        assert list(down) == [days[2]]


class TestCycle:
    """판정일의 반감기 사이클과 경과 개월"""

    def test_halving_for_picks_the_latest_halving_on_or_before(self) -> None:
        """
        목적: 판정일 이전(그날 포함) 가장 최근 반감기를 고른다. 첫 반감기 전은 없다.

        Given: 반감기 2020-01-31 · 2021-03-29
        When: 여러 날의 사이클을 묻는다
        Then: 2020-01-30 은 없음 · 2020-01-31 은 첫째 · 2021-03-28 은 첫째 · 2021-03-29 는 둘째다
        """
        assert halving_for(pd.Timestamp("2020-01-30"), HALVINGS) is None
        assert halving_for(pd.Timestamp("2020-01-31"), HALVINGS) == HALVINGS[0]
        assert halving_for(pd.Timestamp("2021-03-28"), HALVINGS) == HALVINGS[0]
        assert halving_for(pd.Timestamp("2021-03-29"), HALVINGS) == HALVINGS[1]

    def test_months_since_counts_full_calendar_months_with_month_end_clamp(self) -> None:
        """
        목적: 경과 개월은 **다 채운 달력월 수**이고, 1단계의 「반감기일 + 개월」과 같은 말일 당김을 쓴다.

        Given: 1월 31일 반감기
        When: 2월 28일 · 2월 29일(윤년) · 3월 30일 · 3월 31일에 센다
        Then: 0 · 1 · 1 · 2 (1월 31일 + 1개월 = 2월 29일)
        """
        start = pd.Timestamp("2020-01-31")
        assert months_since(start, pd.Timestamp("2020-02-28")) == 0
        assert months_since(start, pd.Timestamp("2020-02-29")) == 1
        assert months_since(start, pd.Timestamp("2020-03-30")) == 1
        assert months_since(start, pd.Timestamp("2020-03-31")) == 2


class TestSignalEntries:
    """판정마다 한 행 — 사이클 · 진입일 · 제외 사유"""

    def test_judgments_are_only_on_trading_days(self) -> None:
        """
        목적: 지표 계열이 시세보다 앞에서 시작해도 **시세의 거래일에만** 판정한다.

        Given: 2019-12-01 에 상향 돌파가 있는 지표, 시세는 2020-01-01 부터
        When: 판정한다
        Then: 2019-12-01 판정이 없다
        """
        # Given
        trading_days = pd.DatetimeIndex(_prices()[COL_DATE])
        early_days = pd.date_range("2019-11-01", END, freq="D")
        early = pd.Series(np.where(early_days >= pd.Timestamp("2019-12-01"), 1.5, 0.5), index=early_days)

        # When
        entries = signal_entries(trading_days, early, UPWARD, HALVINGS)

        # Then
        assert entries.empty

    def test_each_judgment_carries_cycle_entry_and_reason(self) -> None:
        """
        목적: 판정 넷의 사이클 · 경과 개월 · 진입일 · 제외 사유를 박는다.

        Given: 2020-01-10 · 2020-06-15 · 2021-06-10 · 2021-06-30(데이터 마지막 날) 상향 돌파
        When: 판정한다
        Then: 첫 반감기 전 판정은 사이클 「첫 반감기 전」과 사유 · 경과와 진입일이 비고,
              2020-06-15 는 첫 반감기 뒤 4개월 · 진입 06-16, 2021-06-10 은 둘째 반감기 뒤 2개월 · 진입 06-11,
              마지막 날 판정은 둘째 뒤 3개월 · 진입일이 비고 「진입일이 데이터 뒤」다
        """
        # Given
        trading_days = pd.DatetimeIndex(_prices()[COL_DATE])

        # When
        entries = signal_entries(trading_days, _daily_values(), UPWARD, HALVINGS)

        # Then
        assert list(entries[COL_JUDGMENT_DATE]) == [
            pd.Timestamp(day) for day in ("2020-01-10", "2020-06-15", "2021-06-10", "2021-06-30")
        ]
        assert list(entries[COL_HALVING]) == [POSITION_BEFORE_FIRST, "2020-01-31", "2021-03-29", "2021-03-29"]
        assert entries[COL_MONTHS_SINCE_HALVING].tolist()[1:] == [4, 2, 3]
        assert pd.isna(entries[COL_MONTHS_SINCE_HALVING].iloc[0])
        assert list(entries[COL_EXCLUDED_REASON]) == [
            REASON_BEFORE_FIRST_HALVING,
            REASON_NONE,
            REASON_NONE,
            REASON_ENTRY_AFTER_DATA,
        ]
        assert entries[COL_DATE].iloc[1] == pd.Timestamp("2020-06-16")
        assert entries[COL_DATE].iloc[2] == pd.Timestamp("2021-06-11")
        assert pd.isna(entries[COL_DATE].iloc[0]) and pd.isna(entries[COL_DATE].iloc[3])
        assert entries[COL_PREVIOUS_VALUE].tolist() == pytest.approx([0.5] * 4, abs=1e-12)
        assert entries[COL_INDICATOR_VALUE].tolist() == pytest.approx([1.5] * 4, abs=1e-12)


class TestSignalReturns:
    """신호 × 보유 long-form"""

    @pytest.fixture
    def returns(self) -> pd.DataFrame:
        """일간 신호 하나와 월간 신호 하나를 두 보유로 잰 long-form."""
        return indicator_signal_returns(
            _prices(),
            {COL_MVRV: _daily_values(), COL_MONTHLY_RSI: _monthly_values()},
            (UPWARD, MONTHLY),
            HALVINGS,
            HOLDS,
        )

    def test_rows_are_judgments_times_holds_and_split_into_valid_and_excluded(self, returns: pd.DataFrame) -> None:
        """
        목적: **신호 × 보유 = 유효 + 제외** — 어떤 판정도 조용히 사라지지 않는다 (표본 보존).

        Given: 일간 판정 넷 · 월간 판정 하나, 보유 둘
        When: long-form 을 낸다
        Then: 10행이고, 유효는 일간 2020-06-15 의 두 보유와 월간 2020-08-31 의 두 보유 — 넷이다
        """
        assert len(returns) == 10
        valid = returns[returns[COL_EXCLUDED_REASON] == REASON_NONE]
        assert len(valid) == 4
        assert returns[COL_FORWARD_RETURN].notna().sum() == 4

    def test_order_is_signal_then_judgment_then_hold(self, returns: pd.DataFrame) -> None:
        """
        목적: 행 순서가 신호 → 판정일 → 보유다 — 사용자가 차트와 대조하며 위에서 아래로 읽는다.

        Given: 위 long-form
        When: 순서를 본다
        Then: 일간 신호 8행이 먼저이고, 판정일마다 보유 1 · 2 가 붙어 있다
        """
        assert list(returns[COL_INDICATOR_SIGNAL]) == [UPWARD.name] * 8 + [MONTHLY.name] * 2
        assert list(returns[COL_HOLD_MONTHS]) == [1, 2] * 5

    def test_valid_rows_enter_next_day_close_and_exit_by_calendar_months(self, returns: pd.DataFrame) -> None:
        """
        목적: 판정일 다음날 종가에 사고 달력월 뒤 종가에 판다 — 수익률은 청산 ÷ 진입 − 1 이다 (결정 ㉗ · ⑯).

        Given: 일간 2020-06-15 판정 · 월간 2020-08-31 판정
        When: 유효 행을 본다
        Then: 진입 06-16 · 청산 07-16 / 08-16, 월간은 진입 09-01 · 청산 10-01 / 11-01 이고 진입 종가가 그날 종가다
        """
        # Given
        closes = _prices().set_index(COL_DATE)[COL_CLOSE]
        valid = returns[returns[COL_EXCLUDED_REASON] == REASON_NONE]

        # Then
        assert list(valid[COL_DATE]) == [pd.Timestamp(day) for day in ("2020-06-16",) * 2 + ("2020-09-01",) * 2]
        assert list(valid[COL_EXIT_DATE]) == [
            pd.Timestamp(day) for day in ("2020-07-16", "2020-08-16", "2020-10-01", "2020-11-01")
        ]
        assert valid[COL_ENTRY_CLOSE].tolist() == pytest.approx(list(closes[valid[COL_DATE]]), abs=1e-12)
        expected = closes[valid[COL_EXIT_DATE]].to_numpy() / closes[valid[COL_DATE]].to_numpy() - 1.0
        assert valid[COL_FORWARD_RETURN].tolist() == pytest.approx(list(expected), abs=1e-12)

    def test_excluded_rows_keep_their_reasons(self, returns: pd.DataFrame) -> None:
        """
        목적: 제외 행이 사유와 함께 남고 값이 비어 있다 — 0 으로 채우면 「손실도 이익도 없었다」로 읽힌다.

        Given: 위 long-form
        When: 일간 신호의 사유를 판정일 순서로 본다
        Then: 첫 반감기 전 둘 · 유효 둘 · 청산 전 둘(2021-06-10 → 진입 06-11 의 1 · 2개월 뒤가 데이터 밖) · 데이터 뒤 진입 둘
        """
        daily = returns[returns[COL_INDICATOR_SIGNAL] == UPWARD.name]
        assert list(daily[COL_EXCLUDED_REASON]) == [
            REASON_BEFORE_FIRST_HALVING,
            REASON_BEFORE_FIRST_HALVING,
            REASON_NONE,
            REASON_NONE,
            REASON_OUT_OF_RANGE,
            REASON_OUT_OF_RANGE,
            REASON_ENTRY_AFTER_DATA,
            REASON_ENTRY_AFTER_DATA,
        ]
        excluded = daily[daily[COL_EXCLUDED_REASON] != REASON_NONE]
        assert excluded[COL_FORWARD_RETURN].isna().all()

    def test_signal_without_any_crossing_has_no_rows(self) -> None:
        """
        목적: 한 번도 돌파하지 않은 신호는 long-form 에 행이 없다 — 0건 행은 집계 표가 남긴다 (경계 조건).

        Given: 문턱을 한 번도 넘지 않는 값
        When: long-form 을 낸다
        Then: 빈 표이고 컬럼은 갖춰져 있다
        """
        # Given
        never = IndicatorSignal(name="시험 무", indicator=COL_MVRV, threshold=1000.0, upward=True, meaning="시험")

        # When
        result = indicator_signal_returns(_prices(), {COL_MVRV: _daily_values()}, (never,), HALVINGS, HOLDS)

        # Then
        assert result.empty
        assert COL_EXCLUDED_REASON in result.columns


class TestEntryIndicatorValues:
    """1단계 진입일에 붙이는 값 — 진입 전날까지 완성된 것 (결정 ㉗)"""

    def test_daily_from_previous_day_and_monthly_from_month_ended_by_then(self) -> None:
        """
        목적: 일간은 진입일 − 1 일의 값, 월간은 **그날이나 그 전에 끝난 달**의 값이다.

        달의 첫날에 들어가면 전날이 전달 말일이라 **전달**의 값을 쓴다 — 그달 값은 아직 끝나지 않았다.

        Given: 진입일 2020-09-02 · 2020-09-01, 일간 값은 날짜마다 다르고 월간은 달마다 다르다
        When: 진입 전날 값을 붙인다
        Then: 값 기준일은 09-01 · 08-31, 월간 기준 달은 둘 다 2020-08-31 이고 값이 그날 · 그달 것이다
        """
        # Given
        days = pd.date_range(START, END, freq="D")
        daily = pd.DataFrame({COL_MVRV: np.arange(len(days), dtype=float)}, index=days)
        month_ends = pd.date_range("2020-01-31", "2021-05-31", freq="ME")
        monthly = pd.DataFrame({COL_MONTHLY_RSI: np.arange(len(month_ends), dtype=float)}, index=month_ends)
        entries = pd.DatetimeIndex(["2020-09-02", "2020-09-01"])

        # When
        result = entry_indicator_values(pd.DatetimeIndex(days), entries, daily, monthly)

        # Then
        assert list(result[COL_VALUE_DAY]) == [pd.Timestamp("2020-09-01"), pd.Timestamp("2020-08-31")]
        assert list(result[COL_INDICATOR_MONTH]) == [pd.Timestamp("2020-08-31")] * 2
        assert result[COL_MVRV].tolist() == pytest.approx(
            [float(days.get_loc(pd.Timestamp("2020-09-01"))), float(days.get_loc(pd.Timestamp("2020-08-31")))],
            abs=1e-12,
        )
        assert result[COL_MONTHLY_RSI].tolist() == pytest.approx(
            [float(month_ends.get_loc(pd.Timestamp("2020-08-31")))] * 2, abs=1e-12
        )

    def test_entry_on_first_trading_day_has_no_values(self) -> None:
        """
        목적: 전날이 데이터에 없으면 값을 비운다 — 그날 값으로 채우면 미래 참조다 (경계 조건).

        Given: 진입일이 첫 거래일
        When: 진입 전날 값을 붙인다
        Then: 값 기준일 · 기준 달 · 값이 모두 비어 있다
        """
        # Given
        days = pd.date_range(START, END, freq="D")
        daily = pd.DataFrame({COL_MVRV: np.ones(len(days))}, index=days)
        monthly = pd.DataFrame({COL_MONTHLY_RSI: [50.0]}, index=pd.DatetimeIndex(["2020-01-31"]))

        # When
        result = entry_indicator_values(pd.DatetimeIndex(days), pd.DatetimeIndex([START]), daily, monthly)

        # Then
        assert pd.isna(result[COL_VALUE_DAY].iloc[0])
        assert pd.isna(result[COL_INDICATOR_MONTH].iloc[0])
        assert result[[COL_MVRV, COL_MONTHLY_RSI]].isna().all(axis=None)


class TestLookAhead:
    """판정이 뒤의 데이터에 기대지 않는다 (`tests/CLAUDE.md` 필수)"""

    def test_judgments_do_not_depend_on_later_days(self) -> None:
        """
        목적: 앞쪽 판정의 날짜 · 값 · 사이클이 뒤 데이터를 잘라도 같다.

        자른 입력의 **마지막 날 판정**은 진입일이 데이터 뒤로 바뀌는 것이 정상이라 사유는 견주지 않는다.

        Given: 전체 시세 · 값과 2021-01-31 까지로 자른 것
        When: 각각 판정한다
        Then: 자른 입력의 판정이 전체 판정의 앞부분과 같다
        """
        # Given
        prices = _prices()
        values = _daily_values()
        cut = pd.Timestamp("2021-01-31")
        short_days = pd.DatetimeIndex(prices.loc[prices[COL_DATE] <= cut, COL_DATE])

        # When
        full = signal_entries(pd.DatetimeIndex(prices[COL_DATE]), values, UPWARD, HALVINGS)
        short = signal_entries(short_days, values[:cut], UPWARD, HALVINGS)

        # Then
        compared = [COL_JUDGMENT_DATE, COL_PREVIOUS_VALUE, COL_INDICATOR_VALUE, COL_HALVING]
        assert not short.empty
        pd.testing.assert_frame_equal(
            full[compared].iloc[: len(short)].reset_index(drop=True), short[compared].reset_index(drop=True)
        )
