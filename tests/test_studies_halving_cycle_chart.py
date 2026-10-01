"""반감기_사이클 판단용 차트 — 산출물 표와 시세를 차트 데이터로 옮기는 모양을 고정한다.

**차트는 값을 옮길 뿐 새로 계산하지 않는다**(③ 의 중앙값과 ① ② 의 배수 · 경과 개월 · 고점 · 바닥만 예외).
옮기다 칸이 한 줄 밀리거나 손절 행 · 시기 행이 섞여도 HTML 은 그럴듯하게 그려지고 예외는 나지 않는다 —
그래서 옮긴 값이 입력 표의 **그 행**과 같은지를 본다.

**픽스처는 실제와 다르게 고른다** (`docs/MEMORY.md` 「픽스처는 실제 쓰이는 값과 «다르게» 고른다」) —
반감기일 · 격자 간격(2개월) · 손절선(−7 · −21%) · 문턱 · 분할 기한이 실제와 달라, 함수가 상수를 안에서 읽으면 걸린다.
"""

import json
from typing import Any

import numpy as np
import pandas as pd
import pytest

from verify_lab.common_constants import CHARTS_DIR, RESULTS_DIR
from verify_lab.execution.constants import (
    DISPLAY_DIRECTION,
    DISPLAY_ENTRY_DATE,
    DISPLAY_ENTRY_PRICE,
    DISPLAY_EXIT_DATE,
    DISPLAY_EXIT_PRICE,
    DISPLAY_GAP_STOP_COUNT,
    DISPLAY_INTRADAY_STOP_COUNT,
    DISPLAY_LOSING_COUNT,
    DISPLAY_RETURN,
    DISPLAY_STOP_LEVEL,
    DISPLAY_TICKER,
    DISPLAY_TOTAL,
    DISPLAY_WIN_RATE,
    DISPLAY_WORST_HOLD,
    NO_STOP_LABEL,
    PERIOD_ALL,
    stop_level_value,
)
from verify_lab.measure.constants import PERIOD_FIRST_HALF, REASON_NONE
from verify_lab.measure.screening import SCREEN_CANDIDATE
from verify_lab.report.constants import (
    DISPLAY_EXCLUDED,
    DISPLAY_EXCLUDED_REASON,
    DISPLAY_MEAN,
    DISPLAY_MEAN_DIFF,
    DISPLAY_MEDIAN,
    DISPLAY_MEDIAN_DIFF,
    DISPLAY_MIN,
    DISPLAY_NON_OVERLAPPING,
    DISPLAY_PERIOD,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_SCREEN,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_UP_RATE,
    DISPLAY_UP_RATE_DIFF,
)
from verify_lab.studies.halving_cycle.chart import (
    CHART_FILENAME,
    DATA_MARKER,
    PLOTLY_MARKER,
    TEMPLATE_PATH,
    chart_path,
    cycle_series,
    cycle_summary,
    grid_cells,
    render_html,
    split_view,
    stop_rows,
    timeline_series,
)
from verify_lab.studies.halving_cycle.constants import (
    BASELINE_PREFIX,
    DISPLAY_AVG_BUY_PRICE,
    DISPLAY_AVG_SELL_PRICE,
    DISPLAY_BUY_LAST_DEADLINE,
    DISPLAY_BUY_START_ANCHOR,
    DISPLAY_BUY_START_MONTHS,
    DISPLAY_BUY_THRESHOLD,
    DISPLAY_ENTRY_MONTHS,
    DISPLAY_EXIT_MONTHS,
    DISPLAY_FIRST_BUY_DATE,
    DISPLAY_FORK_SHARE,
    DISPLAY_HALVING,
    DISPLAY_HOLD_MONTHS,
    DISPLAY_LAST_SELL_DATE,
    DISPLAY_SELL_LAST_DEADLINE,
    DISPLAY_SELL_START_MONTHS,
    DISPLAY_SELL_THRESHOLD,
    DISPLAY_SPLIT_DEADLINE,
    DISPLAY_SPLIT_FILL_CLOSE,
    DISPLAY_SPLIT_FILL_DATE,
    DISPLAY_SPLIT_LAST_DEADLINE,
    DISPLAY_SPLIT_PRIOR_MVRV,
    DISPLAY_SPLIT_PRIOR_RANK,
    DISPLAY_SPLIT_SIDE,
    DISPLAY_SPLIT_START_ANCHOR,
    DISPLAY_SPLIT_START_MONTHS,
    DISPLAY_SPLIT_THRESHOLD,
    DISPLAY_SPLIT_TRANCHE,
    DISPLAY_SPLIT_TRIGGER,
    DISPLAY_WORST_VS_COST,
    REASON_POSITION_BUYING,
    REASON_SPLIT_PENDING,
    SPLIT_ANCHOR_HALVING,
    SPLIT_ANCHOR_HIGH,
    SPLIT_SIDE_BUY,
    SPLIT_SIDE_SELL,
    SPLIT_THRESHOLD_BOOK,
    SPLIT_THRESHOLD_NONE,
    SPLIT_THRESHOLD_RANK,
    SPLIT_TRIGGER_CALENDAR,
    SPLIT_TRIGGER_ONCHAIN,
    TRACK_NAME,
)
from verify_lab.tracks import track_of

TICKER = "합성 BTC"

# 반감기일 — 실제 넷과 다르다. 셋째는 데이터 뒤라 진행 중 사이클이 둘째다
HALVING_DAYS = (pd.Timestamp("2001-01-10"), pd.Timestamp("2004-02-20"))
DATA_START = pd.Timestamp("2000-06-01")
DATA_END = pd.Timestamp("2006-03-31")

# 격자 — 실제(0 ~ 45 · 3개월)와 다른 2개월 간격
ENTRY = (0, 2, 4)
EXIT = (0, 2, 4)
# 손절선 — 실제 목록에 없는 값
STOPS: tuple[float | None, ...] = (None, 0.07, 0.21)
STOP_LABELS = [stop_level_value(level, measurable=True) for level in STOPS]
# 표본이 없는 칸
EMPTY_CELL = (4, 4)
# 평균은 양수인데 셋 중 둘이 손실로 끝난 칸 — 평균의 부호와 방향 비율이 어긋난다(측정의 원칙 13)
CONFLICT_CELL = (2, 4)
# 같은 사이클 칸(청산 > 진입)
SAME_CYCLE = [(entry, exit_) for entry in ENTRY for exit_ in EXIT if exit_ > entry]
CYCLES = ("2001-01-10", "2004-02-20", "2007-04-01")


# ============================================================
# 픽스처 — 시세
# ============================================================


def _days() -> pd.DatetimeIndex:
    return pd.date_range(DATA_START, DATA_END, freq="D")


def _flat(value: float, overrides: dict[str, float] | None = None) -> pd.Series:
    """전 기간 같은 값의 계열 — `overrides` 의 날짜(`YYYY-MM-DD`)만 그 값이다"""
    days = _days()
    marks = overrides or {}
    return pd.Series([marks.get(day.strftime("%Y-%m-%d"), value) for day in days], index=days, dtype=float)


# ============================================================
# 픽스처 — 성적표 · 거래내역 · 격자기준선 (표시용 프레임)
# ============================================================


def _base(entry: int, exit_: int, stop_index: int, period: str) -> float:
    """행마다 다른 값 — 어느 행을 옮겼는지 값으로 드러난다"""
    return entry * 100 + exit_ * 10 + stop_index + (0.5 if period != PERIOD_ALL else 0.0)


def _performance() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for entry in ENTRY:
        for exit_ in EXIT:
            for stop_index, label in enumerate(STOP_LABELS):
                for period in (PERIOD_ALL, PERIOD_FIRST_HALF):
                    empty = (entry, exit_) == EMPTY_CELL
                    base = _base(entry, exit_, stop_index, period)
                    rows.append(
                        {
                            DISPLAY_TICKER: TICKER,
                            DISPLAY_ENTRY_MONTHS: entry,
                            DISPLAY_EXIT_MONTHS: exit_,
                            DISPLAY_DIRECTION: "위",
                            DISPLAY_STOP_LEVEL: label,
                            DISPLAY_PERIOD: period,
                            DISPLAY_SIGNAL_COUNT: 0 if empty else 3,
                            DISPLAY_TOTAL: np.nan if empty else base + 1000,
                            DISPLAY_MEAN: np.nan if empty else base,
                            DISPLAY_WIN_RATE: np.nan if empty else 50.0 + stop_index,
                            DISPLAY_MIN: np.nan if empty else -base,
                            DISPLAY_WORST_HOLD: np.nan if empty else -base - 1,
                            DISPLAY_GAP_STOP_COUNT: pd.NA if empty else stop_index,
                            DISPLAY_INTRADAY_STOP_COUNT: pd.NA if empty else 2 * stop_index,
                            DISPLAY_LOSING_COUNT: pd.NA if empty else (2 if (entry, exit_) == CONFLICT_CELL else 0),
                            DISPLAY_SCREEN: SCREEN_CANDIDATE,
                        }
                    )
    frame = pd.DataFrame(rows)
    counts = (DISPLAY_SIGNAL_COUNT, DISPLAY_GAP_STOP_COUNT, DISPLAY_INTRADAY_STOP_COUNT, DISPLAY_LOSING_COUNT)
    return frame.astype({column: "Int64" for column in counts})


# 칸마다 무손절 체결의 수익률 — (0, 2) 는 짝수 표본이라 중앙값이 두 값의 평균이다
TRADE_RETURNS: dict[tuple[int, int], list[float]] = {
    (0, 2): [10.0, 30.0],
    (0, 4): [5.0, -1.0, 7.0],
}


def _trade_row(entry: int, exit_: int, cycle: int, stop_label: float | str, value: float) -> dict[str, Any]:
    return {
        DISPLAY_TICKER: TICKER,
        DISPLAY_ENTRY_MONTHS: entry,
        DISPLAY_EXIT_MONTHS: exit_,
        DISPLAY_HALVING: CYCLES[cycle],
        DISPLAY_DIRECTION: "위",
        DISPLAY_STOP_LEVEL: stop_label,
        DISPLAY_ENTRY_DATE: f"200{cycle + 1}-0{entry + 1}-15",
        DISPLAY_ENTRY_PRICE: 100.0 + cycle,
        DISPLAY_EXIT_DATE: f"200{cycle + 2}-0{exit_ + 1}-15",
        DISPLAY_EXIT_PRICE: 100.0 + cycle + value,
        DISPLAY_RETURN: value,
        DISPLAY_WORST_HOLD: -abs(value) - 0.5,
        DISPLAY_FORK_SHARE: 0.25 * cycle,
    }


def _trades() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for entry in ENTRY:
        for exit_ in EXIT:
            if (entry, exit_) == EMPTY_CELL:
                continue
            values = TRADE_RETURNS.get((entry, exit_), [1.0])
            for cycle, value in enumerate(values):
                rows.append(_trade_row(entry, exit_, cycle, NO_STOP_LABEL, value))
                # 손절 행 — 중앙값 · 체결 목록에 섞이면 값이 크게 바뀐다
                rows.append(_trade_row(entry, exit_, cycle, STOP_LABELS[1], 999.0))
    return pd.DataFrame(rows)


def _grid_baseline() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for entry, exit_ in SAME_CYCLE:
        seed = entry * 10 + exit_
        rows.append(
            {
                DISPLAY_TICKER: TICKER,
                DISPLAY_ENTRY_MONTHS: entry,
                DISPLAY_EXIT_MONTHS: exit_,
                DISPLAY_DIRECTION: "위",
                DISPLAY_HOLD_MONTHS: exit_ - entry,
                DISPLAY_SIGNAL_COUNT: 4,
                DISPLAY_EXCLUDED: 1,
                DISPLAY_SAMPLE_COUNT: 3,
                f"{BASELINE_PREFIX}{DISPLAY_SAMPLE_COUNT}": 900 + seed,
                f"{BASELINE_PREFIX}{DISPLAY_NON_OVERLAPPING}": 50 + seed,
                f"{BASELINE_PREFIX}{DISPLAY_MEAN}": 1.5 + seed,
                f"{BASELINE_PREFIX}{DISPLAY_MEDIAN}": 2.5 + seed,
                f"{BASELINE_PREFIX}{DISPLAY_UP_RATE}": 55.0 + seed,
                DISPLAY_MEAN_DIFF: 3.5 + seed,
                DISPLAY_MEDIAN_DIFF: 4.5 + seed,
                DISPLAY_UP_RATE_DIFF: 5.5 + seed,
            }
        )
    return pd.DataFrame(rows)


def _cell(cells: list[dict[str, Any]], entry: int, exit_: int) -> dict[str, Any]:
    matches = [cell for cell in cells if (cell["entry"], cell["exit"]) == (entry, exit_)]
    assert len(matches) == 1, f"칸 ({entry}, {exit_}) 이 {len(matches)}개입니다"
    return matches[0]


# ============================================================
# 픽스처 — 혼합 분할 회차 · 포지션
# ============================================================

# 매수 조합 — (문턱, 시작 기준, 시작 개월, 마지막 기한). 기한 20 · 26 은 실제(30 · 33 · 36)에 없다
BUY_LEGS: tuple[tuple[str, str | None, int | None, int], ...] = (
    (SPLIT_THRESHOLD_NONE, None, None, 20),
    (SPLIT_THRESHOLD_NONE, None, None, 26),
    (SPLIT_THRESHOLD_BOOK, SPLIT_ANCHOR_HALVING, 5, 20),
    (SPLIT_THRESHOLD_RANK, SPLIT_ANCHOR_HIGH, 2, 26),
)
# 매도 조합 — (문턱, 시작 개월, 마지막 기한)
SELL_LEGS: tuple[tuple[str, int | None, int], ...] = (
    (SPLIT_THRESHOLD_NONE, None, 9),
    (SPLIT_THRESHOLD_BOOK, 1, 9),
)
SPLIT_CYCLES = CYCLES[:2]


def _fill_row(
    side: str, threshold: str, anchor: str | None, start: int | None, deadline: int, cycle: str, tranche: int
) -> dict[str, Any]:
    # 둘째 사이클의 매수 셋째 회차는 체결 전 — 점을 찍지 않고 세기만 한다
    pending = side == SPLIT_SIDE_BUY and cycle == SPLIT_CYCLES[1] and tranche == 3
    return {
        DISPLAY_TICKER: TICKER,
        DISPLAY_SPLIT_SIDE: side,
        DISPLAY_SPLIT_THRESHOLD: threshold,
        DISPLAY_SPLIT_START_ANCHOR: anchor,
        DISPLAY_SPLIT_START_MONTHS: start,
        DISPLAY_SPLIT_LAST_DEADLINE: deadline,
        DISPLAY_HALVING: cycle,
        DISPLAY_SPLIT_TRANCHE: tranche,
        DISPLAY_SPLIT_DEADLINE: pd.Timestamp(f"{cycle[:4]}-0{tranche + 1}-01") + pd.DateOffset(years=1),
        DISPLAY_SPLIT_FILL_DATE: pd.NaT if pending else pd.Timestamp(f"{cycle[:4]}-0{tranche + 1}-01"),
        DISPLAY_SPLIT_FILL_CLOSE: np.nan if pending else 10.0 * tranche + deadline,
        DISPLAY_SPLIT_TRIGGER: None
        if pending
        else (SPLIT_TRIGGER_CALENDAR if threshold == SPLIT_THRESHOLD_NONE else SPLIT_TRIGGER_ONCHAIN),
        DISPLAY_SPLIT_PRIOR_MVRV: np.nan if pending else 1.25,
        DISPLAY_SPLIT_PRIOR_RANK: np.nan if pending else 12.5,
        DISPLAY_EXCLUDED_REASON: REASON_SPLIT_PENDING if pending else REASON_NONE,
    }


def _split_fills() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for threshold, anchor, start, deadline in BUY_LEGS:
        for cycle in SPLIT_CYCLES:
            for tranche in (1, 2, 3):
                rows.append(_fill_row(SPLIT_SIDE_BUY, threshold, anchor, start, deadline, cycle, tranche))
    for threshold, start, deadline in SELL_LEGS:
        for cycle in SPLIT_CYCLES:
            for tranche in (1, 2, 3):
                rows.append(_fill_row(SPLIT_SIDE_SELL, threshold, None, start, deadline, cycle, tranche))
    frame = pd.DataFrame(rows)
    return frame.astype({DISPLAY_SPLIT_START_MONTHS: "Int64"})


def _split_positions() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for buy_index, (buy_threshold, anchor, buy_start, buy_deadline) in enumerate(BUY_LEGS):
        for sell_index, (sell_threshold, sell_start, sell_deadline) in enumerate(SELL_LEGS):
            for cycle_index, cycle in enumerate(SPLIT_CYCLES):
                ongoing = cycle_index == 1
                rows.append(
                    {
                        DISPLAY_TICKER: TICKER,
                        DISPLAY_BUY_THRESHOLD: buy_threshold,
                        DISPLAY_BUY_START_ANCHOR: anchor,
                        DISPLAY_BUY_START_MONTHS: buy_start,
                        DISPLAY_BUY_LAST_DEADLINE: buy_deadline,
                        DISPLAY_SELL_THRESHOLD: sell_threshold,
                        DISPLAY_SELL_START_MONTHS: sell_start,
                        DISPLAY_SELL_LAST_DEADLINE: sell_deadline,
                        DISPLAY_HALVING: cycle,
                        DISPLAY_AVG_BUY_PRICE: 20.0 + buy_index,
                        DISPLAY_AVG_SELL_PRICE: np.nan if ongoing else 40.0 + sell_index,
                        DISPLAY_RETURN: np.nan if ongoing else 100.0 * buy_index + 10.0 * sell_index + cycle_index,
                        DISPLAY_WORST_VS_COST: -1.0 - buy_index,
                        DISPLAY_FIRST_BUY_DATE: pd.Timestamp(f"{cycle[:4]}-02-01"),
                        DISPLAY_LAST_SELL_DATE: pd.NaT if ongoing else pd.Timestamp(f"{int(cycle[:4]) + 3}-04-01"),
                        DISPLAY_EXCLUDED_REASON: REASON_POSITION_BUYING if ongoing else REASON_NONE,
                    }
                )
    frame = pd.DataFrame(rows)
    return frame.astype({DISPLAY_BUY_START_MONTHS: "Int64", DISPLAY_SELL_START_MONTHS: "Int64"})


# ============================================================
# ① ② — 사이클 겹치기 · 전 기간 시간축
# ============================================================


class TestCycleSeries:
    """반감기마다 한 사이클 — 반감기일부터 다음 반감기 전날까지"""

    def test_첫_반감기_전의_날은_어느_사이클에도_없다(self) -> None:
        """
        목적: 첫 반감기 앞 구간이 첫 사이클의 앞머리로 섞이지 않는다.

        Given: 첫 반감기보다 7개월 앞에서 시작하는 시세
        When: 사이클 계열을 만든다
        Then: 첫 사이클의 첫 날이 반감기일이다
        """
        # Given / When
        cycles = cycle_series(_flat(10.0), _flat(1.0), _flat(0.5), HALVING_DAYS)

        # Then
        assert cycles[0]["dates"][0] == "2001-01-10"

    def test_사이클은_다음_반감기_전날에서_끝나고_마지막은_데이터_끝까지다(self) -> None:
        """
        목적: 다음 반감기일이 앞 사이클의 끝에 겹치지 않고, 진행 중 사이클만 데이터 끝까지 간다.

        Given: 반감기 둘과 그 뒤 2년 남짓의 시세
        When: 사이클 계열을 만든다
        Then: 첫 사이클은 다음 반감기 전날에 끝나고 진행 중이 아니며, 둘째는 데이터 끝까지 가고 진행 중이다
        """
        # Given / When
        cycles = cycle_series(_flat(10.0), _flat(1.0), _flat(0.5), HALVING_DAYS)

        # Then
        assert [cycle["dates"][-1] for cycle in cycles] == ["2004-02-19", "2006-03-31"]
        assert [cycle["ongoing"] for cycle in cycles] == [False, True]

    def test_배수는_반감기일_종가가_1배이고_개월은_날_수를_30_4375_로_나눈_값이다(self) -> None:
        """
        목적: 가로축 · 세로축의 환산을 고정한다(§4.12 · §4.14 와 같은 정의).

        Given: 반감기일 종가 50, 90일 뒤 종가 150 인 시세
        When: 사이클 계열을 만든다
        Then: 반감기일 배수 1 · 90일 뒤 배수 3 · 90일 뒤 경과 90 ÷ 30.4375 개월
        """
        # Given
        close = _flat(10.0, {"2001-01-10": 50.0, "2001-04-10": 150.0})  # 반감기일 · 90일 뒤

        # When
        first = cycle_series(close, _flat(1.0), _flat(0.5), HALVING_DAYS)[0]

        # Then
        position = first["dates"].index("2001-04-10")
        assert first["multiple"][0] == pytest.approx(1.0, abs=1e-12)
        assert first["multiple"][position] == pytest.approx(3.0, abs=1e-9)
        assert first["months"][position] == pytest.approx(90 / 30.4375, abs=1e-3)

    def test_순위는_백분율로_옮기고_MVRV_는_시세_날짜에_맞춘다(self) -> None:
        """
        목적: 4년 순위(비율)를 백분율로 싣고, MVRV 가 시세에 없는 날을 끼워 넣지 않는다.

        Given: 순위 0.25 · 시세보다 앞뒤로 긴 MVRV
        When: 사이클 계열을 만든다
        Then: 순위가 25 이고 MVRV 의 길이가 날짜 수와 같다
        """
        # Given
        longer = pd.Series(2.0, index=pd.date_range("1999-01-01", "2008-01-01", freq="D"))

        # When
        first = cycle_series(_flat(10.0), longer, _flat(0.25), HALVING_DAYS)[0]

        # Then
        assert first["rank"][0] == pytest.approx(25.0, abs=1e-9)
        assert len(first["mvrv"]) == len(first["dates"])

    def test_데이터_끝_뒤의_반감기는_건너뛰고_앞_사이클이_데이터_끝까지_간다(self) -> None:
        """
        목적: 반감기 목록에 한 줄을 더한 날(그날 종가가 아직 없다) 차트가 멈추지 않는다 — 측정이 그 진입을
            「아직 오지 않음」으로 넘기는 것과 같다.

        Given: 데이터 끝(2006-03-31) 뒤의 셋째 반감기까지 넣은 반감기 목록
        When: 사이클 계열 · 요약 · 시간축을 만든다
        Then: 사이클이 둘이고 둘째가 데이터 끝까지 가는 진행 중 사이클이다
        """
        # Given
        halvings = (*HALVING_DAYS, pd.Timestamp("2007-04-01"))

        # When
        cycles = cycle_series(_flat(10.0), _flat(1.0), _flat(0.5), halvings)
        summary = cycle_summary(_flat(10.0), _flat(1.0), halvings, buy_level=1.4)
        timeline = timeline_series(_flat(10.0), _flat(1.0), _flat(0.5), halvings)

        # Then
        assert [(cycle["dates"][-1], cycle["ongoing"]) for cycle in cycles] == [
            ("2004-02-19", False),
            ("2006-03-31", True),
        ]
        assert [row["halving"] for row in summary] == ["2001-01-10", "2004-02-20"]
        assert timeline["anchor"][-1].startswith("2004-02-20 반감기 뒤")

    def test_반감기일이_시세에_없으면_멈춘다(self) -> None:
        """
        목적: 1배의 기준 종가가 없는 사이클을 조용히 다른 날로 그리지 않는다.

        Given: 둘째 반감기일을 뺀 시세
        When: 사이클 계열을 만든다
        Then: ValueError
        """
        # Given
        close = _flat(10.0).drop(HALVING_DAYS[1])

        # When / Then
        with pytest.raises(ValueError, match="반감기"):
            cycle_series(close, _flat(1.0), _flat(0.5), HALVING_DAYS)


class TestCycleSummary:
    """사이클 요약 — 고점은 반감기 뒤 24개월 안의 최고 종가, 바닥 · 문턱 아래는 고점 뒤"""

    @staticmethod
    def _series() -> tuple[pd.Series, pd.Series]:
        close = _flat(
            100.0,
            {
                "2001-03-01": 10.0,  # 고점 «앞»의 더 낮은 값 — 바닥이 아니다
                "2001-11-10": 300.0,  # 24개월 안 최고 — 고점
                "2002-06-01": 20.0,  # 고점 뒤 최저 — 바닥
                "2003-09-10": 500.0,  # 24개월 «밖» · 다음 반감기 앞 — 고점이 아니다
            },
        )
        mvrv = _flat(
            2.0,
            {
                "2001-05-01": 1.0,  # 고점 «앞»에 문턱 아래 — 세지 않는다
                "2002-01-15": 1.2,  # 고점 뒤 처음 문턱 아래
            },
        )
        return close, mvrv

    def test_고점은_반감기_뒤_24개월_안의_최고_종가다(self) -> None:
        """
        목적: 다음 반감기 직전의 더 높은 종가가 사이클 고점으로 잡히지 않는다(§4.14 — 2020 사이클의 2024-03-13).

        Given: 반감기 뒤 10개월에 300, 32개월(다음 반감기 앞)에 500 인 시세
        When: 요약을 만든다
        Then: 고점이 10개월 쪽이다
        """
        # Given
        close, mvrv = self._series()

        # When
        first = cycle_summary(close, mvrv, HALVING_DAYS, buy_level=1.4)[0]

        # Then
        assert (first["peak"], first["peak_close"]) == ("2001-11-10", pytest.approx(300.0, abs=0.01))

    def test_바닥은_고점_뒤_최저_종가다(self) -> None:
        """
        목적: 고점 앞의 더 낮은 종가를 바닥으로 잡지 않는다.

        Given: 고점 앞 10 · 고점 뒤 20 인 시세
        When: 요약을 만든다
        Then: 바닥이 고점 뒤의 20 이다
        """
        # Given
        close, mvrv = self._series()

        # When
        first = cycle_summary(close, mvrv, HALVING_DAYS, buy_level=1.4)[0]

        # Then
        assert (first["bottom"], first["bottom_close"]) == ("2002-06-01", pytest.approx(20.0, abs=0.01))

    def test_문턱_아래는_고점_뒤에_처음_닿은_날이고_없으면_비운다(self) -> None:
        """
        목적: 고점 앞의 문턱 아래를 세지 않고, 닿은 적이 없는 사이클은 빈칸이다(0 이나 다른 날이 아니다).

        Given: 첫 사이클은 고점 앞 · 뒤에 문턱 아래가 하나씩, 둘째 사이클은 문턱 아래가 없다
        When: 문턱 1.4 로 요약을 만든다
        Then: 첫 사이클은 고점 뒤의 날, 둘째는 None
        """
        # Given
        close, mvrv = self._series()

        # When
        summary = cycle_summary(close, mvrv, HALVING_DAYS, buy_level=1.4)

        # Then
        assert [row["first_below"] for row in summary] == ["2002-01-15", None]


class TestTimelineSeries:
    """전 기간 시간축 — 호버의 「어느 반감기 뒤 몇 개월」과 2 · 4년차 띠"""

    def test_호버_글자가_첫_반감기_전과_반감기_뒤_개월을_가른다(self) -> None:
        """
        목적: 날마다 기준 반감기와 경과 개월을 붙이고, 첫 반감기 앞은 따로 표시한다.

        Given: 첫 반감기 앞 · 뒤의 날
        When: 시간축 계열을 만든다
        Then: 앞은 「첫 반감기 전」, 90일 뒤는 그 반감기와 3.0개월
        """
        # Given / When
        timeline = timeline_series(_flat(10.0), _flat(1.0), _flat(0.5), HALVING_DAYS)

        # Then
        dates = timeline["dates"]
        assert timeline["anchor"][dates.index("2000-12-31")] == "첫 반감기 전"
        assert timeline["anchor"][dates.index("2001-04-10")] == "2001-01-10 반감기 뒤 3.0개월"

    def test_2년차_4년차_띠는_다음_반감기와_데이터_끝에서_잘린다(self) -> None:
        """
        목적: 띠가 다음 사이클로 넘어가거나 데이터 밖에 그려지지 않는다.

        Given: 반감기 간격 37개월 남짓 · 둘째 반감기 뒤 25개월 남짓의 데이터
        When: 시간축 계열을 만든다
        Then: 첫 사이클 4년차 띠는 다음 반감기에서 끝나고, 둘째 사이클에는 4년차 띠가 없다
        """
        # Given / When
        timeline = timeline_series(_flat(10.0), _flat(1.0), _flat(0.5), HALVING_DAYS)

        # Then
        assert timeline["bands"] == [
            {"x0": "2002-01-10", "x1": "2003-01-10"},
            {"x0": "2004-01-10", "x1": "2004-02-20"},
            {"x0": "2005-02-20", "x1": "2006-02-20"},
        ]


# ============================================================
# ③ — 격자 히트맵
# ============================================================


class TestGridCells:
    """칸마다 성적표 무손절 · 전체 행을 옮기고, 중앙값과 체결 목록은 거래내역 무손절 행에서"""

    def test_모든_칸이_진입_청산_순서로_나온다(self) -> None:
        """
        목적: 칸이 빠지거나 순서가 섞이면 히트맵의 자리가 밀린다.

        Given: 3 × 3 격자의 성적표
        When: 칸을 만든다
        Then: 진입 오름차순 · 그 안에서 청산 오름차순으로 9칸
        """
        # Given / When
        cells = grid_cells(_performance(), _trades(), _grid_baseline(), entry_months=ENTRY, exit_months=EXIT)

        # Then
        assert [(cell["entry"], cell["exit"]) for cell in cells] == [(e, x) for e in ENTRY for x in EXIT]

    def test_값은_무손절_전체_행_그대로다(self) -> None:
        """
        목적: 손절 행이나 시기 행을 옮기지 않는다 — 행마다 값이 달라 섞이면 드러난다.

        Given: 행마다 다른 값을 둔 성적표
        When: 칸 (2, 0) 을 만든다
        Then: 무손절 · 전체 행의 값이다
        """
        # Given / When
        cell = _cell(
            grid_cells(_performance(), _trades(), _grid_baseline(), entry_months=ENTRY, exit_months=EXIT), 2, 0
        )

        # Then
        assert (cell["sample"], cell["total"], cell["mean"], cell["up_rate"], cell["worst"], cell["worst_hold"]) == (
            3,
            pytest.approx(1200.0, abs=1e-9),
            pytest.approx(200.0, abs=1e-9),
            pytest.approx(50.0, abs=1e-9),
            pytest.approx(-200.0, abs=1e-9),
            pytest.approx(-201.0, abs=1e-9),
        )

    def test_표본이_없는_칸은_값을_비운다(self) -> None:
        """
        목적: 잴 것이 없는 칸을 0 으로 칠하지 않는다 — 0 은 「오르지도 내리지도 않았다」로 읽힌다.

        Given: 칸 (4, 4) 의 신호가 0 이고 지표가 빈 성적표
        When: 칸을 만든다
        Then: 표본 0 · 평균 · 중앙값 None · 체결 없음
        """
        # Given / When
        cell = _cell(
            grid_cells(_performance(), _trades(), _grid_baseline(), entry_months=ENTRY, exit_months=EXIT), *EMPTY_CELL
        )

        # Then
        assert (cell["sample"], cell["mean"], cell["median"], cell["trades"]) == (0, None, None, [])

    def test_중앙값은_거래내역_무손절_수익률의_중앙값이다(self) -> None:
        """
        목적: 산출물에 없는 값을 한 정의로 낸다 — 짝수 표본은 가운데 두 값의 평균, 손절 행은 섞지 않는다.

        Given: (0, 2) 무손절 10 · 30, (0, 4) 무손절 5 · −1 · 7, 그리고 칸마다 999 인 손절 행
        When: 칸을 만든다
        Then: 20 과 5
        """
        # Given / When
        cells = grid_cells(_performance(), _trades(), _grid_baseline(), entry_months=ENTRY, exit_months=EXIT)

        # Then
        assert _cell(cells, 0, 2)["median"] == pytest.approx(20.0, abs=1e-9)
        assert _cell(cells, 0, 4)["median"] == pytest.approx(5.0, abs=1e-9)

    def test_칸마다_사이클별_무손절_체결을_싣는다(self) -> None:
        """
        목적: 호버의 사이클별 체결이 손절 행을 섞지 않고 거래내역 값 그대로다.

        Given: (0, 4) 에 무손절 셋 · 손절 셋
        When: 칸을 만든다
        Then: 체결 셋이고 반감기 · 수익률 · 하드포크 몫이 무손절 행 그대로다
        """
        # Given / When
        trades = _cell(
            grid_cells(_performance(), _trades(), _grid_baseline(), entry_months=ENTRY, exit_months=EXIT), 0, 4
        )["trades"]

        # Then
        assert [(trade["halving"], trade["return"], trade["fork_share"]) for trade in trades] == [
            (CYCLES[0], pytest.approx(5.0, abs=1e-9), pytest.approx(0.0, abs=1e-9)),
            (CYCLES[1], pytest.approx(-1.0, abs=1e-9), pytest.approx(0.25, abs=1e-9)),
            (CYCLES[2], pytest.approx(7.0, abs=1e-9), pytest.approx(0.5, abs=1e-9)),
        ]

    def test_평균과_방향이_어긋나는_칸을_표시한다(self) -> None:
        """
        목적: 평균만 보고 방향을 읽으면 정반대로 판단하는 칸을 따로 표시한다(측정의 원칙 13).

        Given: (2, 4) 는 평균이 양수인데 셋 중 둘이 손실로 끝났고, 나머지 칸은 손실이 없는 성적표
        When: 칸을 만든다
        Then: (2, 4) 만 어긋남이고, 표본이 없는 칸은 어긋나지 않는다
        """
        # Given / When
        cells = grid_cells(_performance(), _trades(), _grid_baseline(), entry_months=ENTRY, exit_months=EXIT)

        # Then
        assert [(cell["entry"], cell["exit"]) for cell in cells if cell["conflict"]] == [CONFLICT_CELL]

    def test_기준선은_같은_사이클_칸에만_있다(self) -> None:
        """
        목적: 다음 사이클 칸은 같은 보유가 정의되지 않아 기준선이 없다(결정 ㊵) — 빈칸으로 둔다.

        Given: 같은 사이클 칸에만 행이 있는 격자기준선
        When: 칸을 만든다
        Then: (0, 2) 는 그 행의 값, (2, 0) 은 None
        """
        # Given / When
        cells = grid_cells(_performance(), _trades(), _grid_baseline(), entry_months=ENTRY, exit_months=EXIT)

        # Then
        baseline = _cell(cells, 0, 2)["baseline"]
        assert (
            baseline["hold"],
            baseline["mean_diff"],
            baseline["up_rate_diff"],
            baseline["sample"],
            baseline["non_overlapping"],
        ) == (2, pytest.approx(5.5, abs=1e-9), pytest.approx(7.5, abs=1e-9), 902, 52)
        assert _cell(cells, 2, 0)["baseline"] is None

    def test_같은_사이클_칸에_기준선_행이_없으면_멈춘다(self) -> None:
        """
        목적: 기준선이 있어야 할 칸이 조용히 빈칸이 되지 않는다.

        Given: (0, 2) 행을 뺀 격자기준선
        When: 칸을 만든다
        Then: ValueError
        """
        # Given
        baseline = _grid_baseline()
        baseline = baseline[~((baseline[DISPLAY_ENTRY_MONTHS] == 0) & (baseline[DISPLAY_EXIT_MONTHS] == 2))]

        # When / Then
        with pytest.raises(ValueError, match="기준선"):
            grid_cells(_performance(), _trades(), baseline, entry_months=ENTRY, exit_months=EXIT)

    def test_칸의_무손절_전체_행이_없으면_멈춘다(self) -> None:
        """
        목적: 성적표에 칸이 빠지면 히트맵에 조용히 구멍이 나지 않는다.

        Given: (2, 2) 무손절 · 전체 행을 뺀 성적표
        When: 칸을 만든다
        Then: ValueError
        """
        # Given
        performance = _performance()
        drop = (
            (performance[DISPLAY_ENTRY_MONTHS] == 2)
            & (performance[DISPLAY_EXIT_MONTHS] == 2)
            & (performance[DISPLAY_STOP_LEVEL] == NO_STOP_LABEL)
            & (performance[DISPLAY_PERIOD] == PERIOD_ALL)
        )

        # When / Then
        with pytest.raises(ValueError, match="성적표"):
            grid_cells(performance[~drop], _trades(), _grid_baseline(), entry_months=ENTRY, exit_months=EXIT)

    def test_종목이_둘이면_멈춘다(self) -> None:
        """
        목적: 두 대상의 칸이 한 히트맵에 섞이지 않는다.

        Given: 종목이 둘인 성적표
        When: 칸을 만든다
        Then: ValueError
        """
        # Given
        other = _performance().assign(**{DISPLAY_TICKER: "다른 종목"})
        performance = pd.concat([_performance(), other], ignore_index=True)

        # When / Then
        with pytest.raises(ValueError, match="종목"):
            grid_cells(performance, _trades(), _grid_baseline(), entry_months=ENTRY, exit_months=EXIT)


# ============================================================
# ④ — 칸별 손절선
# ============================================================


class TestStopRows:
    """칸마다 손절선 목록 순서로 성적표 전체 행을 옮긴다"""

    def test_칸마다_손절선이_목록_순서로_나온다(self) -> None:
        """
        목적: 평평한 구간을 읽으려면 손절선이 좁은 쪽부터 넓은 쪽으로 늘 같은 순서여야 한다.

        Given: 무손절 · −7 · −21% 성적표
        When: 손절선 행을 만든다
        Then: 칸마다 그 순서다
        """
        # Given / When
        rows = stop_rows(_performance(), _trades(), entry_months=ENTRY, exit_months=EXIT, stop_levels=STOPS)

        # Then
        assert [(row["entry"], row["exit"]) for row in rows] == [(e, x) for e in ENTRY for x in EXIT]
        assert all([stop["stop"] for stop in row["stops"]] == STOP_LABELS for row in rows)

    def test_값은_전체_행_그대로고_발동_수는_장중손절과_갭손절의_합이다(self) -> None:
        """
        목적: 시기 행을 섞지 않고, 발동 수가 두 청산 방식을 모두 센다.

        Given: 손절선마다 값이 다른 성적표 (−21% 행: 갭 2 · 장중 4)
        When: 칸 (2, 4) 의 손절선 행을 만든다
        Then: −21% 행의 평균이 전체 행 값이고 발동 수가 6 이다
        """
        # Given / When
        row = next(
            row
            for row in stop_rows(_performance(), _trades(), entry_months=ENTRY, exit_months=EXIT, stop_levels=STOPS)
            if (row["entry"], row["exit"]) == (2, 4)
        )

        # Then
        widest = row["stops"][2]
        assert (widest["mean"], widest["triggered"], widest["sample"]) == (pytest.approx(242.0, abs=1e-9), 6, 3)

    def test_표본이_없는_칸의_발동_수는_비운다(self) -> None:
        """
        목적: 잰 적이 없는 칸의 발동 수를 0 으로 적지 않는다.

        Given: 칸 (4, 4) 의 갭 · 장중 손절이 빈 성적표
        When: 손절선 행을 만든다
        Then: 발동 수 None
        """
        # Given / When
        row = next(
            row
            for row in stop_rows(_performance(), _trades(), entry_months=ENTRY, exit_months=EXIT, stop_levels=STOPS)
            if (row["entry"], row["exit"]) == EMPTY_CELL
        )

        # Then
        assert [stop["triggered"] for stop in row["stops"]] == [None, None, None]

    def test_손절선마다_평균과_방향이_어긋나는지_표시한다(self) -> None:
        """
        목적: ④ 표의 평균도 원칙 13 의 표시를 잃지 않는다.

        Given: (2, 4) 는 손절선마다 평균이 양수인데 셋 중 둘이 손실로 끝난 성적표
        When: 손절선 행을 만든다
        Then: (2, 4) 의 손절선 행은 전부 어긋남이고, (2, 0) 은 하나도 아니다
        """
        # Given / When
        rows = {
            (row["entry"], row["exit"]): row
            for row in stop_rows(_performance(), _trades(), entry_months=ENTRY, exit_months=EXIT, stop_levels=STOPS)
        }

        # Then
        assert [stop["conflict"] for stop in rows[CONFLICT_CELL]["stops"]] == [True, True, True]
        assert [stop["conflict"] for stop in rows[(2, 0)]["stops"]] == [False, False, False]

    def test_손절선마다_그_손절선_체결의_중앙값을_싣는다(self) -> None:
        """
        목적: ④ 도 평균과 중앙값을 나란히 둔다(측정의 원칙 4) — 중앙값은 그 손절선의 체결에서만 낸다.

        Given: (0, 2) 에 무손절 10 · 30, −7% 999 · 999, −21% 체결 없음인 거래내역
        When: 손절선 행을 만든다
        Then: 중앙값이 20 · 999 · None 이다
        """
        # Given / When
        row = next(
            row
            for row in stop_rows(_performance(), _trades(), entry_months=ENTRY, exit_months=EXIT, stop_levels=STOPS)
            if (row["entry"], row["exit"]) == (0, 2)
        )

        # Then
        assert [stop["median"] for stop in row["stops"]] == [
            pytest.approx(20.0, abs=1e-9),
            pytest.approx(999.0, abs=1e-9),
            None,
        ]

    def test_손절선_행이_빠지면_멈춘다(self) -> None:
        """
        목적: 11종 중 하나가 빠진 채 비교하지 않는다 — 빠진 자리가 평평한 구간처럼 보인다.

        Given: 칸 (0, 0) 의 −7% 전체 행을 뺀 성적표
        When: 손절선 행을 만든다
        Then: ValueError
        """
        # Given
        performance = _performance()
        drop = (
            (performance[DISPLAY_ENTRY_MONTHS] == 0)
            & (performance[DISPLAY_EXIT_MONTHS] == 0)
            & (performance[DISPLAY_STOP_LEVEL] == STOP_LABELS[1])
            & (performance[DISPLAY_PERIOD] == PERIOD_ALL)
        )

        # When / Then
        with pytest.raises(ValueError, match="성적표"):
            stop_rows(performance[~drop], _trades(), entry_months=ENTRY, exit_months=EXIT, stop_levels=STOPS)


class TestNoScreen:
    """1차 판정을 차트 데이터에 싣지 않는다 — 기준선 대비 차이와 같은 화면이라 탈락 근거로 읽힌다"""

    def test_성적표를_읽는_두_함수의_출력에_판정이_없다(self) -> None:
        """
        목적: 판정 열을 가진 성적표를 받아도 그 열과 값이 차트로 새지 않는다.

        Given: 모든 행이 「후보」인 성적표
        When: 칸 · 손절선 행을 만든다
        Then: 출력 어디에도 판정 열 이름과 「후보」가 없다
        """
        # Given / When
        cells = grid_cells(_performance(), _trades(), _grid_baseline(), entry_months=ENTRY, exit_months=EXIT)
        stops = stop_rows(_performance(), _trades(), entry_months=ENTRY, exit_months=EXIT, stop_levels=STOPS)
        text = json.dumps([cells, stops], ensure_ascii=False)

        # Then
        assert DISPLAY_SCREEN not in text
        assert SCREEN_CANDIDATE not in text


# ============================================================
# ⑤ — 혼합 분할
# ============================================================


class TestSplitView:
    """조합마다 사이클별 회차 · 포지션과 같은 기한의 달력만 짝"""

    def test_조합은_회차_표에_나온_순서이고_이름이_문턱_시작_기한을_말한다(self) -> None:
        """
        목적: 목록에서 조합을 고를 때 이름만 보고 무엇인지 안다.

        Given: 매수 넷 · 매도 둘의 회차 표
        When: 분할 보기를 만든다
        Then: 매수 · 매도 조합 이름이 순서대로다
        """
        # Given / When
        view = split_view(_split_fills(), _split_positions())

        # Then
        assert [leg["label"] for leg in view["buy_legs"]] == [
            "달력만 · 기한 20개월",
            "달력만 · 기한 26개월",
            "책 고정 · 반감기 뒤 5개월부터 · 기한 20개월",
            f"{SPLIT_THRESHOLD_RANK} · 신고가 뒤 2개월부터 · 기한 26개월",
        ]
        assert [leg["label"] for leg in view["sell_legs"]] == [
            "달력만 · 기한 9개월",
            "책 고정 · 다음 반감기 뒤 1개월부터 · 기한 9개월",
        ]

    def test_달력만_짝은_마지막_기한이_같은_달력만_조합이다(self) -> None:
        """
        목적: 「같은 기한의 달력만과 견준다」가 기한이 다른 조합과 견주지 않는다.

        Given: 기한 20 · 26 의 달력만과 온체인 조합
        When: 분할 보기를 만든다
        Then: 각 조합의 달력만 짝이 같은 기한의 달력만이다
        """
        # Given / When
        view = split_view(_split_fills(), _split_positions())

        # Then
        keys = {leg["key"]: leg for leg in view["buy_legs"]}
        pairs = [(leg["deadline"], keys[leg["calendar_key"]]["deadline"]) for leg in view["buy_legs"]]
        assert pairs == [(20, 20), (26, 26), (20, 20), (26, 26)]
        assert all(keys[leg["calendar_key"]]["threshold"] == SPLIT_THRESHOLD_NONE for leg in view["buy_legs"])

    def test_체결_전_회차는_점이_아니라_건수로_남는다(self) -> None:
        """
        목적: 체결일이 없는 회차를 그리지 않되, 있었다는 사실은 남긴다.

        Given: 둘째 사이클 매수 셋째 회차가 체결 전인 회차 표
        When: 분할 보기를 만든다
        Then: 그 사이클의 점이 둘이고 체결 전 건수가 1 이다
        """
        # Given / When
        view = split_view(_split_fills(), _split_positions())

        # Then
        first_buy = view["buy_legs"][0]["key"]
        fills = view["fills"][first_buy][SPLIT_CYCLES[1]]
        assert ([fill["tranche"] for fill in fills["points"]], fills["pending"]) == ([1, 2], 1)

    def test_포지션은_매수_매도_사이클로_찾고_값이_그대로다(self) -> None:
        """
        목적: 고른 조합의 사이클별 성적이 다른 조합 · 사이클의 값과 뒤바뀌지 않는다.

        Given: 조합 · 사이클마다 수익률이 다른 포지션 표
        When: 분할 보기를 만든다
        Then: (매수 셋째 · 매도 둘째 · 첫 사이클) 이 그 행의 값이고, 끝나지 않은 포지션은 수익률이 비고 사유가 남는다
        """
        # Given / When
        view = split_view(_split_fills(), _split_positions())

        # Then
        buy_key = view["buy_legs"][2]["key"]
        sell_key = view["sell_legs"][1]["key"]
        done = view["positions"][buy_key][sell_key][SPLIT_CYCLES[0]]
        ongoing = view["positions"][buy_key][sell_key][SPLIT_CYCLES[1]]
        assert (done["return"], done["worst"], done["first_buy"]) == (
            pytest.approx(210.0, abs=1e-9),
            pytest.approx(-3.0, abs=1e-9),
            "2001-02-01",
        )
        assert (ongoing["return"], ongoing["reason"]) == (None, REASON_POSITION_BUYING)

    def test_달력만_짝이_없는_기한이면_멈춘다(self) -> None:
        """
        목적: 견줄 대조군이 없는 조합을 조용히 대조군 없이 그리지 않는다.

        Given: 기한 26 의 달력만 조합을 뺀 회차 표
        When: 분할 보기를 만든다
        Then: ValueError
        """
        # Given
        fills = _split_fills()
        drop = (fills[DISPLAY_SPLIT_THRESHOLD] == SPLIT_THRESHOLD_NONE) & (fills[DISPLAY_SPLIT_LAST_DEADLINE] == 26)

        # When / Then
        with pytest.raises(ValueError, match="달력만"):
            split_view(fills[~drop], _split_positions())


# ============================================================
# 렌더 · 출력 자리
# ============================================================


class TestRenderHtml:
    """템플릿의 자리표시 둘을 한 번에 채운다"""

    TEMPLATE = f"<p>{DATA_MARKER}</p><script>{PLOTLY_MARKER}</script>"

    def test_데이터의_닫는_태그가_스크립트를_닫지_않는다(self) -> None:
        """
        목적: 데이터 문자열 속 `</script>` 가 페이지를 깨뜨리지 않는다.

        Given: `</script>` 를 담은 데이터
        When: 렌더한다
        Then: 출력에 그 글자가 그대로 없고 `<\\/` 로 바뀌어 있다
        """
        # Given / When
        html = render_html(self.TEMPLATE, {"text": "</script><b>"}, "PLOTLY")

        # Then
        assert "</script><b>" not in html
        assert "<\\/script><b>" in html

    def test_넣은_글자_속_자리표시_모양은_다시_바뀌지_않는다(self) -> None:
        """
        목적: plotly.js 나 데이터에 자리표시와 같은 글자가 있어도 두 번 치환되지 않는다.

        Given: 데이터 자리표시 글자를 담은 plotly 문자열
        When: 렌더한다
        Then: 그 글자가 그대로 남는다
        """
        # Given / When
        html = render_html(self.TEMPLATE, {"n": 1}, f"x{DATA_MARKER}y")

        # Then
        assert f"x{DATA_MARKER}y" in html
        assert '<p>{"n":1}</p>' in html

    def test_자리표시가_없거나_둘이면_멈춘다(self) -> None:
        """
        목적: 데이터가 빠진 페이지나 두 번 들어간 페이지를 만들지 않는다.

        Given: 데이터 자리표시가 없는 템플릿 · 두 번 있는 템플릿
        When: 렌더한다
        Then: 둘 다 ValueError
        """
        # Given
        missing = f"<script>{PLOTLY_MARKER}</script>"
        doubled = f"{DATA_MARKER}{DATA_MARKER}{PLOTLY_MARKER}"

        # When / Then
        with pytest.raises(ValueError, match="자리표시"):
            render_html(missing, {}, "PLOTLY")
        with pytest.raises(ValueError, match="자리표시"):
            render_html(doubled, {}, "PLOTLY")

    def test_숫자가_아닌_값이_섞이면_멈춘다(self) -> None:
        """
        목적: `NaN` 이 JSON 에 들어가 브라우저의 `JSON.parse` 가 페이지 전체를 못 읽는 일을 막는다.

        Given: NaN 을 담은 데이터
        When: 렌더한다
        Then: ValueError
        """
        # Given / When / Then
        with pytest.raises(ValueError):
            render_html(self.TEMPLATE, {"x": float("nan")}, "PLOTLY")

    def test_plotly_문자열이_스크립트를_닫으면_멈춘다(self) -> None:
        """
        목적: 넣는 스크립트가 제 `<script>` 를 닫아 뒤를 깨뜨리지 않는다.

        Given: `</script>` 를 담은 plotly 문자열
        When: 렌더한다
        Then: ValueError
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="plotly"):
            render_html(self.TEMPLATE, {}, "a</script>b")

    def test_패키지의_템플릿에_자리표시가_하나씩_있다(self) -> None:
        """
        목적: 실제 템플릿이 렌더 계약을 지킨다.

        Given: 패키지의 차트 템플릿
        When: 자리표시를 센다
        Then: 둘 다 정확히 한 번
        """
        # Given
        template = TEMPLATE_PATH.read_text(encoding="utf-8")

        # When / Then
        assert (template.count(DATA_MARKER), template.count(PLOTLY_MARKER)) == (1, 1)


class TestChartPath:
    """차트는 git 제외 폴더에 쓰고 산출물 폴더를 건드리지 않는다"""

    def test_차트는_차트_폴더의_한글_이름_아래이고_산출물_폴더_밖이다(self) -> None:
        """
        목적: 재실행이 비우는 산출물 폴더에 차트가 섞이지 않는다.

        Given: 이 매매법의 레지스트리 이름
        When: 차트 경로를 구한다
        Then: `CHARTS_DIR / <한글 이름> / <파일 이름>` 이고 `RESULTS_DIR` 아래가 아니다
        """
        # Given
        label = track_of(TRACK_NAME).label

        # When
        path = chart_path()

        # Then
        assert path == CHARTS_DIR / label / CHART_FILENAME
        assert RESULTS_DIR not in path.parents
