"""중간선거_사이클 — 분할매수 체결

**분할매수는 「언제 몇 번째 몫을 사는가」 하나만 새로 정한다.** 몫마다의 수익률은
`execution/trade_fill.simulate_scheduled_trade` 를 무손절로 불러 얻고, 새로 재는 것은
**배정액 기준의 보유 중 최악** 하나다 — 몫이 여럿인 포트폴리오의 경로라 기존 산식이 없다.

[중요] **계약은 넷이다.**

| 계약 | 왜 |
| --- | --- |
| **일시매수 칸 = 기존 무손절 체결** (수익률 · 보유 중 최악 둘 다) | 새 산식이 기존 산식과 한 점에서 묶여야 조용히 갈라지지 않는다 |
| 추가 매수는 **진입 다음 거래일 ~ 12월 마지막 거래일** 안에서만 | 창 밖 체결은 규칙이 아니다 |
| B·C 는 **판정일 종가로 판정하고 다음 거래일 종가에 산다** — 장중 저가가 단계를 지나도 종가가 위면 판정하지 않는다 | 같은 종가에 사면 같은 봉 안의 미래 참조다. 지수(종가뿐)와 ETF 가 같은 규칙을 쓴다 |
| **체결일 당일 장중은 새 몫의 낙폭에 넣지 않는다** | 종가에 샀으므로 그날 장중은 들고 있지 않았다 |

**성적의 분모는 배정액이다** — 현금으로 남은 몫은 수익 0 으로 분모에 들어간다.
그래야 일시매수와 같은 분모로 견줘진다.
"""

from collections.abc import Sequence

import numpy as np
import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN
from verify_lab.execution.trade_fill import simulate_scheduled_trade
from verify_lab.studies.midterm_cycle.constants import (
    ADDITION_MONTHS,
    COL_RSI,
    FALLBACK_BUY_AT_Q4_END,
    FALLBACK_KEEP_CASH,
    FALLBACK_NONE,
    FILL_FIRST,
    FILL_INDICATOR,
    FILL_LADDER,
    FILL_MONTH_END,
    FILL_Q4_END,
    FILL_UNFILLED,
    SPLIT_METHODS,
    IndicatorCross,
    LumpSum,
    MonthEnds,
    PriceLadder,
    SplitMethod,
)
from verify_lab.studies.midterm_cycle.indicators import indicator_frame
from verify_lab.studies.midterm_cycle.split_entry import EntryWindow, entry_windows, simulate_split_entry

# 합성 시세 구간 — 2021-09-30(목) 진입 → 2022-06-30(목) 청산. 12월 31일은 금요일이다
FRAME_START = "2021-09-01"
FRAME_END = "2022-07-15"
ENTRY_DAY = "2021-09-30"
EXIT_DAY = "2022-06-30"

# 합성 시세 시드. **시드 없는 난수는 금지다**
SYNTHETIC_SEED = 20260923

LUMP = SplitMethod(label="일시", trigger=LumpSum(), fallbacks=(FALLBACK_NONE,))
MONTHLY = SplitMethod(label="월말", trigger=MonthEnds(months=ADDITION_MONTHS), fallbacks=(FALLBACK_NONE,))
LADDER = SplitMethod(
    label="사다리",
    trigger=PriceLadder(step_rate=0.05, tranches=3),
    fallbacks=(FALLBACK_BUY_AT_Q4_END, FALLBACK_KEEP_CASH),
)
RSI_CROSS = SplitMethod(
    label="RSI",
    trigger=IndicatorCross(column=COL_RSI, threshold=30.0, tranches=3),
    fallbacks=(FALLBACK_BUY_AT_Q4_END, FALLBACK_KEEP_CASH),
)


def _frame(
    *,
    closes: dict[str, float] | None = None,
    lows: dict[str, float] | None = None,
    start: str = FRAME_START,
    end: str = FRAME_END,
    drop: Sequence[str] = (),
) -> pd.DataFrame:
    """주중 거래일마다 OHLC 가 있는 합성 시세. 종가는 기본 100, 저가는 종가와 같다.

    Args:
        closes: 날짜 → 종가
        lows: 날짜 → 저가
        start: 시작일
        end: 종료일
        drop: 거래일에서 뺄 날짜 (휴장을 흉내 낸다)

    Returns:
        시세 스키마 DataFrame
    """
    days = pd.DatetimeIndex(pd.bdate_range(start, end)).difference(pd.DatetimeIndex(list(drop)))
    close_values = [float((closes or {}).get(day.strftime("%Y-%m-%d"), 100.0)) for day in days]
    low_values = [
        float((lows or {}).get(day.strftime("%Y-%m-%d"), close_values[index])) for index, day in enumerate(days)
    ]

    return pd.DataFrame(
        {
            COL_DATE: days,
            COL_OPEN: close_values,
            COL_HIGH: close_values,
            COL_LOW: low_values,
            COL_CLOSE: close_values,
        }
    )


def _position(frame: pd.DataFrame, day: str) -> int:
    """날짜의 위치 인덱스.

    Args:
        frame: 시세
        day: 날짜

    Returns:
        위치
    """
    return int(pd.DatetimeIndex(frame[COL_DATE]).get_loc(pd.Timestamp(day)))


def _window(frame: pd.DataFrame) -> EntryWindow:
    """합성 시세의 진입 창 하나.

    Args:
        frame: 시세

    Returns:
        9월 30일 진입 · 6월 30일 청산의 창
    """
    return entry_windows(
        pd.DatetimeIndex(frame[COL_DATE]), [_position(frame, ENTRY_DAY)], [_position(frame, EXIT_DAY)]
    )[0]


def _rsi(frame: pd.DataFrame, values: dict[str, float] | None = None, default: float = 50.0) -> pd.DataFrame:
    """RSI 컬럼 하나짜리 지표 표. 특정 날짜만 값을 덮는다.

    Args:
        frame: 시세
        values: 날짜 → RSI
        default: 나머지 날의 RSI

    Returns:
        시세와 인덱스가 같은 지표 표
    """
    days = pd.DatetimeIndex(frame[COL_DATE])
    series = [float((values or {}).get(day.strftime("%Y-%m-%d"), default)) for day in days]
    return pd.DataFrame({COL_RSI: series}, index=frame.index)


def _fill_days(frame: pd.DataFrame, positions: Sequence[int | None]) -> list[str | None]:
    """체결 위치를 날짜 문자열로 바꾼다.

    Args:
        frame: 시세
        positions: 체결 위치 (미체결은 None)

    Returns:
        날짜 문자열 목록
    """
    days = pd.DatetimeIndex(frame[COL_DATE])
    return [None if position is None else days[position].strftime("%Y-%m-%d") for position in positions]


def _walk() -> pd.DataFrame:
    """장중 등락이 있는 합성 시세 — 불변조건 검사용.

    Returns:
        시세 스키마 DataFrame
    """
    days = pd.bdate_range("2021-01-04", FRAME_END)
    rng = np.random.default_rng(SYNTHETIC_SEED)
    closes = 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.015, len(days)))

    return pd.DataFrame(
        {
            COL_DATE: days,
            COL_OPEN: closes,
            COL_HIGH: closes * 1.01,
            COL_LOW: closes * 0.98,
            COL_CLOSE: closes,
        }
    )


class TestEntryWindows:
    """추가 매수 창과 월말 위치"""

    def test_month_ends_of_the_fourth_quarter(self) -> None:
        """
        목적: 월말 위치는 그 달 마지막 거래일이고, 창의 끝은 12월 마지막 거래일이다.

        Given: 2021-09-30 진입 합성 시세
        When: 창을 만든다
        Then: 10·11·12월 끝이 10-29 · 11-30 · 12-31 이고 창의 끝이 12-31 이다
        """
        # Given
        frame = _frame()

        # When
        window = _window(frame)

        # Then
        ends = [window.month_end_positions[month] for month in ADDITION_MONTHS]
        assert _fill_days(frame, ends) == ["2021-10-29", "2021-11-30", "2021-12-31"]
        assert _fill_days(frame, [window.window_end_position]) == ["2021-12-31"]

    def test_holiday_pulls_the_month_end_forward(self) -> None:
        """
        목적: 말일이 휴장이면 그 이전 마지막 거래일이다 — 다음 달로 넘기지 않는다.

        Given: 12월 31일을 뺀 시세
        When: 창을 만든다
        Then: 창의 끝이 12-30 이다
        """
        # Given
        frame = _frame(drop=["2021-12-31"])

        # When
        window = _window(frame)

        # Then
        assert _fill_days(frame, [window.window_end_position]) == ["2021-12-30"]

    def test_missing_month_is_an_invariant_violation(self) -> None:
        """
        목적: 청산일이 있는데 4분기 달이 비어 있으면 데이터가 이상한 것이다 — 조용히 건너뛰지 않는다.

        Given: 11월 거래일을 전부 뺀 시세
        When: 창을 만든다
        Then: RuntimeError
        """
        # Given
        frame = _frame(drop=[day.strftime("%Y-%m-%d") for day in pd.bdate_range("2021-11-01", "2021-11-30")])

        # When / Then
        with pytest.raises(RuntimeError, match="내부 불변조건 위반"):
            _window(frame)


class TestLumpSum:
    """일시매수는 기존 체결과 같다 — 새 산식이 묶이는 한 점"""

    def test_equals_the_scheduled_trade(self) -> None:
        """
        목적: 일시매수의 수익률과 보유 중 최악이 기존 무손절 체결과 정확히 같다.

        Given: 보유 중 저가가 두 번 밀리는 시세
        When: 일시매수와 기존 체결을 함께 돈다
        Then: 두 값이 같다
        """
        # Given
        frame = _frame(
            closes={"2021-10-15": 95.0, "2022-02-10": 97.0, EXIT_DAY: 112.0},
            lows={"2021-10-15": 91.0, "2022-02-10": 88.0},
        )
        window = _window(frame)

        # When
        split = simulate_split_entry(
            frame, window, LUMP, fallback=FALLBACK_NONE, price_column=COL_CLOSE, indicators=_rsi(frame)
        )
        scheduled = simulate_scheduled_trade(
            frame,
            window.entry_position,
            window.exit_position,
            bet_down=False,
            stop_level=None,
            price_column=COL_CLOSE,
        )

        # Then
        assert split.return_rate == pytest.approx(scheduled.return_rate, abs=1e-12)
        assert split.worst_hold_rate == pytest.approx(scheduled.worst_hold_rate, abs=1e-12)

    def test_single_tranche_is_fully_invested(self) -> None:
        """
        목적: 일시매수는 몫이 하나이고 전액 투자다.

        Given: 합성 시세
        When: 일시매수를 돈다
        Then: 체결은 진입일 하나 · 투자 비율 1 · 평균 매수가 = 첫 몫 · 규칙 체결 없음
        """
        # Given
        frame = _frame()

        # When
        result = simulate_split_entry(
            frame, _window(frame), LUMP, fallback=FALLBACK_NONE, price_column=COL_CLOSE, indicators=_rsi(frame)
        )

        # Then
        assert _fill_days(frame, [fill.position for fill in result.fills]) == [ENTRY_DAY]
        assert [fill.reason for fill in result.fills] == [FILL_FIRST]
        assert result.invested_rate == pytest.approx(1.0, abs=1e-12)
        assert result.average_cost_rate == pytest.approx(0.0, abs=1e-12)
        assert result.rule_filled is False


class TestMonthEnds:
    """A — 월말 균등 분할"""

    def test_buys_a_quarter_at_each_month_end(self) -> None:
        """
        목적: 9·10·11·12월 마지막 거래일 종가에 1/4 씩 산다.

        Given: 진입 100 · 10월 말 90 · 11월 말 110 · 12월 말 100 · 청산 120
        When: A 를 돈다
        Then: 수익률 = (0.2 + 120/90−1 + 120/110−1 + 0.2) ÷ 4 = 0.2060606 · 투자 비율 1
        """
        # Given
        frame = _frame(closes={"2021-10-29": 90.0, "2021-11-30": 110.0, EXIT_DAY: 120.0})

        # When
        result = simulate_split_entry(
            frame, _window(frame), MONTHLY, fallback=FALLBACK_NONE, price_column=COL_CLOSE, indicators=_rsi(frame)
        )

        # Then
        assert _fill_days(frame, [fill.position for fill in result.fills]) == [
            ENTRY_DAY,
            "2021-10-29",
            "2021-11-30",
            "2021-12-31",
        ]
        assert [fill.reason for fill in result.fills] == [FILL_FIRST, FILL_MONTH_END, FILL_MONTH_END, FILL_MONTH_END]
        assert result.return_rate == pytest.approx(0.206060606060606, abs=1e-12)
        assert result.invested_rate == pytest.approx(1.0, abs=1e-12)
        assert result.rule_filled is True


class TestPriceLadder:
    """B — 진입가 대비 사다리 (판정일 종가로 판정 · 다음 거래일 종가에 체결)"""

    def test_each_level_fills_the_next_day_after_the_first_close_at_or_below(self) -> None:
        """
        목적: 단계마다 종가가 처음 그 가격 이하로 내려간 날의 «다음 거래일» 종가에 1/3 씩 산다.

        Given: 진입 100 · 10-15(금) 종가 94(−5% 단계) → 10-18(월) 종가 96 ·
               11-10(수) 종가 89(−10% 단계) → 11-11(목) 종가 91 · 청산 100
        When: 사다리 5% 를 돈다
        Then: 10-18 · 11-11 에 체결되고 수익률 = (0 + 100/96−1 + 100/91−1) ÷ 3 = 0.0468559,
              첫 몫 대비 평균 매수가 = 0.0447587 낮다 (주식 수로 가중한 평균)
        """
        # Given
        frame = _frame(closes={"2021-10-15": 94.0, "2021-10-18": 96.0, "2021-11-10": 89.0, "2021-11-11": 91.0})

        # When
        result = simulate_split_entry(
            frame, _window(frame), LADDER, fallback=FALLBACK_KEEP_CASH, price_column=COL_CLOSE, indicators=_rsi(frame)
        )

        # Then
        assert _fill_days(frame, [fill.position for fill in result.fills]) == [ENTRY_DAY, "2021-10-18", "2021-11-11"]
        assert [fill.reason for fill in result.fills] == [FILL_FIRST, FILL_LADDER, FILL_LADDER]
        assert result.return_rate == pytest.approx(0.04685592185592191, abs=1e-12)
        assert result.average_cost_rate == pytest.approx(-0.044758711182387945, abs=1e-12)

    def test_two_levels_on_the_same_day(self) -> None:
        """
        목적: 하루에 두 단계를 한꺼번에 지나면 둘 다 그 다음 거래일 종가에 산다.

        Given: 10-15 종가 88 (−5% · −10% 둘 다 아래)
        When: 사다리 5% 를 돈다
        Then: 두 몫이 모두 10-18 에 체결된다
        """
        # Given
        frame = _frame(closes={"2021-10-15": 88.0})

        # When
        result = simulate_split_entry(
            frame, _window(frame), LADDER, fallback=FALLBACK_KEEP_CASH, price_column=COL_CLOSE, indicators=_rsi(frame)
        )

        # Then
        assert _fill_days(frame, [fill.position for fill in result.fills]) == [ENTRY_DAY, "2021-10-18", "2021-10-18"]

    def test_close_exactly_at_the_level_fills(self) -> None:
        """
        목적: 경계값 — 종가가 단계 가격과 정확히 같으면 판정이 참이다 (「이하」).

        Given: 10-15 종가 95
        When: 사다리 5% 를 돈다
        Then: 두 번째 몫이 다음 거래일(10-18)에 체결되고 세 번째는 미체결이다
        """
        # Given
        frame = _frame(closes={"2021-10-15": 95.0})

        # When
        result = simulate_split_entry(
            frame, _window(frame), LADDER, fallback=FALLBACK_KEEP_CASH, price_column=COL_CLOSE, indicators=_rsi(frame)
        )

        # Then
        assert _fill_days(frame, [fill.position for fill in result.fills]) == [ENTRY_DAY, "2021-10-18", None]
        assert [fill.reason for fill in result.fills] == [FILL_FIRST, FILL_LADDER, FILL_UNFILLED]

    def test_exact_level_survives_floating_point_residue(self) -> None:
        """
        목적: 경계값 — 부동소수점 잔차 때문에 «정확히 같은» 종가를 놓치지 않는다.

        Given: 진입 10.28 · 10-15 종가 9.766 (= 10.28 × 0.95 이지만 부동소수점으로는 9.765999… 로 계산된다)
        When: 사다리 5% 를 돈다
        Then: 두 번째 몫이 다음 거래일(10-18)에 체결된다
        """
        # Given
        frame = _frame(closes={ENTRY_DAY: 10.28, "2021-10-15": 9.766})

        # When
        result = simulate_split_entry(
            frame, _window(frame), LADDER, fallback=FALLBACK_KEEP_CASH, price_column=COL_CLOSE, indicators=_rsi(frame)
        )

        # Then
        assert _fill_days(frame, [fill.position for fill in result.fills])[1] == "2021-10-18"

    def test_intraday_low_alone_does_not_fill(self) -> None:
        """
        목적: 종가 판정이다 — 장중 저가가 단계를 지나도 종가가 위면 사지 않는다.

        Given: 10-15 저가 90 · 종가 96
        When: 사다리 5% 를 돈다
        Then: 추가 몫이 하나도 체결되지 않는다
        """
        # Given
        frame = _frame(closes={"2021-10-15": 96.0}, lows={"2021-10-15": 90.0})

        # When
        result = simulate_split_entry(
            frame, _window(frame), LADDER, fallback=FALLBACK_KEEP_CASH, price_column=COL_CLOSE, indicators=_rsi(frame)
        )

        # Then
        assert [fill.reason for fill in result.fills] == [FILL_FIRST, FILL_UNFILLED, FILL_UNFILLED]
        assert result.rule_filled is False

    def test_judged_the_day_before_the_window_end_fills_on_the_last_day(self) -> None:
        """
        목적: 12월 마지막 거래일 «전날»의 판정은 12월 마지막 거래일에 체결된다 — 창 안에서 끝난다.

        Given: 12-30 종가 94 (−5% 단계만)
        When: 사다리 5% 를 12월 말 일괄로 돈다
        Then: 두 번째 몫은 단계 도달로, 세 번째 몫은 일괄로 둘 다 12-31 에 체결된다
        """
        # Given
        frame = _frame(closes={"2021-12-30": 94.0})

        # When
        result = simulate_split_entry(
            frame,
            _window(frame),
            LADDER,
            fallback=FALLBACK_BUY_AT_Q4_END,
            price_column=COL_CLOSE,
            indicators=_rsi(frame),
        )

        # Then
        assert _fill_days(frame, [fill.position for fill in result.fills]) == [ENTRY_DAY, "2021-12-31", "2021-12-31"]
        assert [fill.reason for fill in result.fills] == [FILL_FIRST, FILL_LADDER, FILL_Q4_END]

    def test_level_reached_on_the_last_window_day_is_not_judged(self) -> None:
        """
        목적: 12월 마지막 거래일의 종가로는 판정하지 않는다 — 체결이 1월로 넘어가기 때문이다.

        Given: 12-31 종가 80 (두 단계 모두 아래)
        When: 사다리 5% 를 현금 유지로 돈다
        Then: 추가 몫이 하나도 체결되지 않는다
        """
        # Given
        frame = _frame(closes={"2021-12-31": 80.0})

        # When
        result = simulate_split_entry(
            frame, _window(frame), LADDER, fallback=FALLBACK_KEEP_CASH, price_column=COL_CLOSE, indicators=_rsi(frame)
        )

        # Then
        assert [fill.reason for fill in result.fills] == [FILL_FIRST, FILL_UNFILLED, FILL_UNFILLED]

    def test_levels_reached_only_after_december_do_not_fill(self) -> None:
        """
        목적: 창 밖(1월 이후)에는 사지 않는다. 현금 유지면 그 몫은 수익 0 으로 분모에 남는다.

        Given: 2022-01-10 종가 80 (두 단계 모두 아래) · 청산 110
        When: 사다리 5% 를 현금 유지로 돈다
        Then: 투자 비율 1/3 · 수익률 = 0.1 ÷ 3
        """
        # Given
        frame = _frame(closes={"2022-01-10": 80.0, EXIT_DAY: 110.0})

        # When
        result = simulate_split_entry(
            frame, _window(frame), LADDER, fallback=FALLBACK_KEEP_CASH, price_column=COL_CLOSE, indicators=_rsi(frame)
        )

        # Then
        assert result.invested_rate == pytest.approx(1.0 / 3.0, abs=1e-12)
        assert result.return_rate == pytest.approx(0.1 / 3.0, abs=1e-12)

    def test_fallback_buys_the_rest_at_the_december_end(self) -> None:
        """
        목적: 미체결 처리 「12월 말 일괄」은 남은 몫을 12월 마지막 거래일 종가에 산다.

        Given: 단계에 한 번도 안 닿음 · 12-31 종가 105 · 청산 110
        When: 사다리 5% 를 12월 말 일괄로 돈다
        Then: 두 몫이 12-31 에 체결되고 수익률 = (0.1 + 2 × (110/105−1)) ÷ 3 = 0.0650794
        """
        # Given
        frame = _frame(closes={"2021-12-31": 105.0, EXIT_DAY: 110.0})

        # When
        result = simulate_split_entry(
            frame,
            _window(frame),
            LADDER,
            fallback=FALLBACK_BUY_AT_Q4_END,
            price_column=COL_CLOSE,
            indicators=_rsi(frame),
        )

        # Then
        assert _fill_days(frame, [fill.position for fill in result.fills]) == [ENTRY_DAY, "2021-12-31", "2021-12-31"]
        assert [fill.reason for fill in result.fills] == [FILL_FIRST, FILL_Q4_END, FILL_Q4_END]
        assert result.return_rate == pytest.approx(0.06507936507936511, abs=1e-12)
        assert result.invested_rate == pytest.approx(1.0, abs=1e-12)
        assert result.rule_filled is False


class TestIndicatorCross:
    """C — 지표가 기준 아래로 «새로 들어간 날»의 다음 거래일에만 산다"""

    def test_buys_only_on_new_entries_up_to_the_limit(self) -> None:
        """
        목적: 조건이 이어지는 날에는 다시 사지 않고, 추가 몫 수를 넘겨 사지 않는다.
              체결은 판정일 다음 거래일이다.

        Given: RSI 가 10-11 ~ 10-13 에 25 · 11-15 에 28 · 12-01 에 20, 나머지는 50
        When: RSI 30 교차를 돈다
        Then: 10-12 · 11-16 에만 산다 (12-01 은 몫이 남지 않았다)
        """
        # Given
        frame = _frame()
        indicators = _rsi(
            frame, {"2021-10-11": 25.0, "2021-10-12": 25.0, "2021-10-13": 25.0, "2021-11-15": 28.0, "2021-12-01": 20.0}
        )

        # When
        result = simulate_split_entry(
            frame, _window(frame), RSI_CROSS, fallback=FALLBACK_KEEP_CASH, price_column=COL_CLOSE, indicators=indicators
        )

        # Then
        assert _fill_days(frame, [fill.position for fill in result.fills]) == [ENTRY_DAY, "2021-10-12", "2021-11-16"]
        assert [fill.reason for fill in result.fills] == [FILL_FIRST, FILL_INDICATOR, FILL_INDICATOR]

    def test_condition_already_true_on_entry_day_is_not_a_new_entry(self) -> None:
        """
        목적: 진입일에 이미 기준 아래였고 그대로 이어지면 «새로 들어간 날»이 아니다.

        Given: RSI 가 9-29 ~ 10-05 에 25
        When: RSI 30 교차를 돈다
        Then: 추가 몫이 체결되지 않는다
        """
        # Given
        frame = _frame()
        oversold = {day.strftime("%Y-%m-%d"): 25.0 for day in pd.bdate_range("2021-09-29", "2021-10-05")}

        # When
        result = simulate_split_entry(
            frame,
            _window(frame),
            RSI_CROSS,
            fallback=FALLBACK_KEEP_CASH,
            price_column=COL_CLOSE,
            indicators=_rsi(frame, oversold),
        )

        # Then
        assert [fill.reason for fill in result.fills] == [FILL_FIRST, FILL_UNFILLED, FILL_UNFILLED]

    def test_empty_indicator_is_not_oversold(self) -> None:
        """
        목적: 지표가 비어 있는 날(창이 차기 전)은 조건이 거짓이다 — 사지 않는다.

        Given: 창 안 전 구간 RSI 가 비어 있다
        When: RSI 30 교차를 돈다
        Then: 추가 몫이 체결되지 않는다
        """
        # Given
        frame = _frame()
        indicators = pd.DataFrame({COL_RSI: [np.nan] * len(frame)}, index=frame.index)

        # When
        result = simulate_split_entry(
            frame, _window(frame), RSI_CROSS, fallback=FALLBACK_KEEP_CASH, price_column=COL_CLOSE, indicators=indicators
        )

        # Then
        assert [fill.reason for fill in result.fills] == [FILL_FIRST, FILL_UNFILLED, FILL_UNFILLED]


class TestAllocatedWorst:
    """배정액 기준 보유 중 최악 — 이 모듈이 새로 재는 유일한 값"""

    def test_hand_calculated_path(self) -> None:
        """
        목적: 몫마다 «산 다음 날부터» 낙폭에 넣는다. 체결일 당일 장중은 새 몫에 넣지 않는다.

        Given: 10-15 저가 93 · 종가 94(−5% 판정) → 10-18 저가 85 · 종가 88(2번째 몫 체결 · −10% 판정)
               → 10-19 종가 100(3번째 몫 체결), 나머지 100
        When: 사다리 5% 를 돈다
        Then: 최악 = 10-18 의 (85/100−1)/3 = −0.05
              (그날 체결한 2번째 몫까지 넣으면 −0.0613636 이 된다 — 그날 장중에는 들고 있지 않았다)
        """
        # Given
        frame = _frame(
            closes={"2021-10-15": 94.0, "2021-10-18": 88.0},
            lows={"2021-10-15": 93.0, "2021-10-18": 85.0},
        )

        # When
        result = simulate_split_entry(
            frame, _window(frame), LADDER, fallback=FALLBACK_KEEP_CASH, price_column=COL_CLOSE, indicators=_rsi(frame)
        )

        # Then
        assert _fill_days(frame, [fill.position for fill in result.fills]) == [ENTRY_DAY, "2021-10-18", "2021-10-19"]
        assert result.worst_hold_rate == pytest.approx(-0.05000000000000001, abs=1e-12)

    def test_worst_never_exceeds_return(self) -> None:
        """
        목적: 불변조건 — 보유 중 최악은 언제나 수익률 이하다 (청산가는 보유 중에 실제로 지난 가격이다).

        Given: 장중 등락이 있는 합성 시세
        When: 격자의 모든 칸을 돈다
        Then: 칸마다 `보유 중 최악 <= 수익률`
        """
        # Given
        frame = _walk()
        window = _window(frame)
        indicators = indicator_frame(frame, price_column=COL_CLOSE)

        # When / Then
        for method in SPLIT_METHODS:
            for fallback in method.fallbacks:
                result = simulate_split_entry(
                    frame, window, method, fallback=fallback, price_column=COL_CLOSE, indicators=indicators
                )
                assert result.worst_hold_rate <= result.return_rate + 1e-12, (method.label, fallback)


class TestLookAhead:
    """추가 매수 판정은 그날까지의 데이터만 쓴다"""

    @pytest.mark.parametrize("method", [LADDER, RSI_CROSS])
    def test_fills_before_a_day_do_not_depend_on_what_follows(self, method: SplitMethod) -> None:
        """
        목적: 11-15 까지 같고 그 뒤만 다른 두 시세에서 11-15 이전 체결이 같다.

        Given: 11-15 까지 같은 두 시세 — 하나는 그 뒤 크게 빠진다
        When: 같은 규칙을 돈다
        Then: 11-15 이전 체결 목록이 같다
        """
        # Given
        base = {"2021-10-15": 94.0}
        calm = _frame(closes=base)
        crash_days = {day.strftime("%Y-%m-%d"): 70.0 for day in pd.bdate_range("2021-11-16", "2021-12-31")}
        crash = _frame(closes={**base, **crash_days})
        oversold = {"2021-10-15": 25.0}
        cutoff = _position(calm, "2021-11-15")

        # When
        results = [
            simulate_split_entry(
                frame,
                _window(frame),
                method,
                fallback=FALLBACK_KEEP_CASH,
                price_column=COL_CLOSE,
                indicators=_rsi(frame, oversold),
            )
            for frame in (calm, crash)
        ]

        # Then
        early = [
            [fill.position for fill in result.fills if fill.position is not None and fill.position <= cutoff]
            for result in results
        ]
        assert early[0] == early[1]


class TestValidation:
    """잘못된 조합을 조용히 넘기지 않는다"""

    def test_rejects_a_fallback_the_method_does_not_have(self) -> None:
        """
        목적: 미체결 처리는 그 방식이 선언한 것만 받는다.

        Given: 일시매수와 「현금 유지」
        When: 돈다
        Then: ValueError
        """
        frame = _frame()

        with pytest.raises(ValueError, match="미체결 처리"):
            simulate_split_entry(
                frame, _window(frame), LUMP, fallback=FALLBACK_KEEP_CASH, price_column=COL_CLOSE, indicators=_rsi(frame)
            )

    def test_ladder_needs_two_or_more_tranches(self) -> None:
        """
        목적: 몫이 하나뿐인 사다리는 일시매수다 — 다른 이름으로 두지 않는다.

        Given: 몫 1개 사다리
        When: 만든다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="몫"):
            PriceLadder(step_rate=0.05, tranches=1)

    def test_ladder_levels_stay_above_zero(self) -> None:
        """
        목적: 가장 깊은 단계가 0 이하이면 영원히 안 닿는 몫이 생긴다.

        Given: 간격 50% · 몫 3개 (가장 깊은 단계 = 0)
        When: 만든다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="단계"):
            PriceLadder(step_rate=0.5, tranches=3)

    def test_methods_without_misses_take_only_the_empty_fallback(self) -> None:
        """
        목적: 미체결이 생길 수 없는 방식에 미체결 처리를 붙이지 않는다 — 같은 칸이 두 번 나온다.

        Given: 일시매수에 「12월 말 일괄」
        When: 만든다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="미체결 처리"):
            SplitMethod(label="일시", trigger=LumpSum(), fallbacks=(FALLBACK_BUY_AT_Q4_END,))


class TestGrid:
    """격자는 계획서 승인 시점에 고정했다 — 결과를 본 뒤 바꾸지 않는다"""

    def test_grid_has_ten_cells_and_starts_with_lump_sum(self) -> None:
        """
        목적: 칸 수와 대조 칸의 자리를 고정한다.

        Given: 격자 상수
        When: (방식 × 미체결 처리) 칸을 센다
        Then: 10칸이고 첫 방식이 일시매수다
        """
        # When
        cells = [(method.label, fallback) for method in SPLIT_METHODS for fallback in method.fallbacks]

        # Then
        assert len(cells) == 10
        assert isinstance(SPLIT_METHODS[0].trigger, LumpSum)

    def test_labels_are_unique(self) -> None:
        """
        목적: 방식 이름이 산출물의 구분자다 — 겹치면 행이 섞인다.

        Given: 격자 상수
        When: 이름을 모은다
        Then: 중복이 없다
        """
        labels = [method.label for method in SPLIT_METHODS]

        assert len(labels) == len(set(labels))

    def test_conditional_methods_carry_both_fallbacks(self) -> None:
        """
        목적: 조건부 방식은 미체결 처리 둘을 다 낸다 — 하나를 고르면 그 선택이 결론에 숨는다.

        Given: 격자 상수
        When: 사다리·지표 방식의 미체결 처리를 본다
        Then: 둘 다 「12월 말 일괄」·「현금 유지」다
        """
        for method in SPLIT_METHODS:
            if isinstance(method.trigger, PriceLadder | IndicatorCross):
                assert method.fallbacks == (FALLBACK_BUY_AT_Q4_END, FALLBACK_KEEP_CASH), method.label
