"""반감기_사이클 판단용 차트 — 시세와 달력 분할 측정 표를 차트 데이터로 옮기는 모양을 고정한다.

**차트는 값을 옮길 뿐 새로 계산하지 않는다**(시세를 그리는 배수 · 경과 개월 · 고점 · 바닥과, 회차 점의 자리만 예외).
옮기다 회차가 다른 사이클 선에 찍히거나 폭이 섞여도 HTML 은 그럴듯하게 그려지고 예외는 나지 않는다 —
그래서 옮긴 값이 입력 표의 **그 행**과 같은지, 점이 **그 선**의 같은 자리에 오는지를 본다.

**픽스처는 실제와 다르게 고른다** (`docs/MEMORY.md` 「픽스처는 실제 쓰이는 값과 «다르게» 고른다」) —
반감기일 · 폭(3회 · 2개월 간격) · 바닥 앞 개월이 실제와 달라, 함수가 상수를 안에서 읽으면 걸린다.
"""

from typing import Any

import numpy as np
import pandas as pd
import pytest

from verify_lab.common_constants import CHARTS_DIR, RESULTS_DIR
from verify_lab.execution.constants import DISPLAY_RETURN, DISPLAY_TICKER
from verify_lab.measure.constants import REASON_NONE
from verify_lab.report.constants import DISPLAY_EXCLUDED_REASON, DISPLAY_HOLD_DAYS_EXACT
from verify_lab.studies.halving_cycle.chart import (
    CHART_FILENAME,
    DATA_MARKER,
    PLOTLY_MARKER,
    TEMPLATE_PATH,
    bottom_series,
    chart_path,
    chart_split,
    cycle_series,
    cycle_summary,
    render_html,
    split_info,
    split_points,
    split_table,
    timeline_series,
    window_bands,
)
from verify_lab.studies.halving_cycle.constants import (
    DISPLAY_AVG_BUY_PRICE,
    DISPLAY_AVG_SELL_PRICE,
    DISPLAY_BUY_CALENDAR_COUNT,
    DISPLAY_BUY_FIRST_DEADLINE,
    DISPLAY_BUY_LAST_DEADLINE,
    DISPLAY_CALENDAR_SPLIT,
    DISPLAY_FIRST_BUY_DATE,
    DISPLAY_HALVING,
    DISPLAY_LAST_SELL_DATE,
    DISPLAY_MONTHS_SINCE_HALVING,
    DISPLAY_SELL_CALENDAR_COUNT,
    DISPLAY_SELL_FIRST_DEADLINE,
    DISPLAY_SELL_LAST_DEADLINE,
    DISPLAY_SPLIT_ANCHOR_HALVING,
    DISPLAY_SPLIT_DEADLINE,
    DISPLAY_SPLIT_FILL_CLOSE,
    DISPLAY_SPLIT_FILL_DATE,
    DISPLAY_SPLIT_SIDE,
    DISPLAY_SPLIT_TRANCHE,
    DISPLAY_SPLIT_TRANCHES,
    DISPLAY_WORST_VS_COST,
    REASON_NO_NEXT_HALVING,
    REASON_POSITION_BUYING,
    REASON_SPLIT_PENDING,
    SPLIT_SIDE_BUY,
    SPLIT_SIDE_SELL,
    TRACK_NAME,
    CalendarSplit,
)
from verify_lab.tracks import track_of

TICKER = "합성 BTC"

# 반감기일 — 실제 넷과 다르다. 셋째는 데이터 뒤라 진행 중 사이클이 둘째다
HALVING_DAYS = (pd.Timestamp("2001-01-10"), pd.Timestamp("2004-02-20"))
DATA_START = pd.Timestamp("2000-06-01")
DATA_END = pd.Timestamp("2006-03-31")

# 폭 — 실제(6 · 12 · 24회 · 1개월 간격)와 다르다. 매수 5 · 7 · 9개월, 매도 다음 반감기 뒤 1 · 3 · 5개월
STEP = 2
SPLIT = CalendarSplit(name="가", tranches=3, buy_last_deadline=9, sell_last_deadline=5)
OTHER = CalendarSplit(name="나", tranches=2, buy_last_deadline=8, sell_last_deadline=6)

# 바닥 앞 개월 — 실제(12)와 다르다
LEAD = 3

# 시세에 심는 값 — 사이클마다 고점 하나 · 바닥 하나, 반감기일 종가, 회차 체결일 종가
PLANTED = {
    "2001-01-10": 50.0,  # 첫 반감기일 — 1배의 기준
    "2001-03-01": 10.0,  # 고점 «앞»의 더 낮은 값 — 바닥이 아니다
    "2001-06-10": 30.0,  # 첫 사이클 매수 1회차
    "2001-11-10": 300.0,  # 24개월 안 최고 — 첫 사이클 고점
    "2002-06-01": 20.0,  # 고점 뒤 최저 — 첫 사이클 바닥
    "2003-09-10": 500.0,  # 24개월 «밖» · 다음 반감기 앞 — 고점이 아니다
    "2004-02-20": 80.0,  # 둘째 반감기일
    "2004-03-20": 160.0,  # 첫 사이클 포지션의 매도 1회차
    "2004-12-01": 400.0,  # 둘째 사이클 고점
    "2005-08-01": 40.0,  # 둘째 사이클 바닥 (진행 중이라 잠정)
}


# ============================================================
# 픽스처
# ============================================================


def _days() -> pd.DatetimeIndex:
    return pd.date_range(DATA_START, DATA_END, freq="D")


def _close(overrides: dict[str, float] | None = None) -> pd.Series:
    """기본 100 에 몇 날만 다른 종가 — `overrides` 가 없으면 `PLANTED` 를 심는다"""
    marks = PLANTED if overrides is None else overrides
    days = _days()
    return pd.Series([marks.get(day.strftime("%Y-%m-%d"), 100.0) for day in days], index=days, dtype=float)


def _fill_row(
    split: str, side: str, cycle: str, anchor: str | None, tranche: int, day: str | None, close: float | None
) -> dict[str, Any]:
    """달력분할회차 표시용 프레임의 한 행 — `day` 가 없으면 체결 전이다"""
    pending = day is None
    return {
        DISPLAY_TICKER: TICKER,
        DISPLAY_CALENDAR_SPLIT: split,
        DISPLAY_SPLIT_SIDE: side,
        DISPLAY_HALVING: cycle,
        DISPLAY_SPLIT_ANCHOR_HALVING: anchor,
        DISPLAY_SPLIT_TRANCHE: tranche,
        DISPLAY_SPLIT_DEADLINE: pd.NaT if anchor is None else pd.Timestamp("2099-01-01"),
        DISPLAY_SPLIT_FILL_DATE: pd.NaT if pending else pd.Timestamp(day),
        DISPLAY_MONTHS_SINCE_HALVING: pd.NA if pending else 1,
        DISPLAY_SPLIT_FILL_CLOSE: np.nan if pending else close,
        DISPLAY_EXCLUDED_REASON: REASON_SPLIT_PENDING if pending else REASON_NONE,
    }


def _fills() -> pd.DataFrame:
    """「가」 — 첫 사이클은 매수 셋 · 매도 셋을 다 했고, 둘째 사이클은 매수 둘만 했다(셋째는 체결 전 · 매도는 다음 반감기 없음).
    「나」 — 다른 폭의 행이 섞여 있어도 걸러야 한다"""
    first, second = (day.strftime("%Y-%m-%d") for day in HALVING_DAYS)
    rows = [
        _fill_row("가", SPLIT_SIDE_BUY, first, first, 1, "2001-06-10", 30.0),
        _fill_row("가", SPLIT_SIDE_BUY, first, first, 2, "2001-08-10", 100.0),
        _fill_row("가", SPLIT_SIDE_BUY, first, first, 3, "2001-10-10", 100.0),
        _fill_row("가", SPLIT_SIDE_SELL, first, second, 1, "2004-03-20", 160.0),
        _fill_row("가", SPLIT_SIDE_SELL, first, second, 2, "2004-05-20", 100.0),
        _fill_row("가", SPLIT_SIDE_SELL, first, second, 3, "2004-07-20", 100.0),
        _fill_row("가", SPLIT_SIDE_BUY, second, second, 1, "2004-07-20", 100.0),
        _fill_row("가", SPLIT_SIDE_BUY, second, second, 2, "2004-09-20", 100.0),
        _fill_row("가", SPLIT_SIDE_BUY, second, second, 3, None, None),
        *(_fill_row("가", SPLIT_SIDE_SELL, second, None, tranche, None, None) for tranche in (1, 2, 3)),
        _fill_row("나", SPLIT_SIDE_BUY, first, first, 1, "2001-07-10", 100.0),
    ]
    frame = pd.DataFrame(rows)
    frame.loc[
        frame[DISPLAY_SPLIT_ANCHOR_HALVING].isna() & (frame[DISPLAY_HALVING] == second), DISPLAY_EXCLUDED_REASON
    ] = REASON_NO_NEXT_HALVING
    return frame.astype({DISPLAY_MONTHS_SINCE_HALVING: "Int64"})


def _positions() -> pd.DataFrame:
    """「가」 두 사이클(끝난 것 · 매수 중) · 「나」 한 사이클"""
    first, second = (day.strftime("%Y-%m-%d") for day in HALVING_DAYS)

    def row(split: str, cycle: str, values: dict[str, Any]) -> dict[str, Any]:
        return {
            DISPLAY_TICKER: TICKER,
            DISPLAY_CALENDAR_SPLIT: split,
            DISPLAY_SPLIT_TRANCHES: 3,
            DISPLAY_BUY_FIRST_DEADLINE: 5,
            DISPLAY_BUY_LAST_DEADLINE: 9,
            DISPLAY_SELL_FIRST_DEADLINE: 1,
            DISPLAY_SELL_LAST_DEADLINE: 5,
            DISPLAY_HALVING: cycle,
            DISPLAY_FIRST_BUY_DATE: pd.NaT,
            DISPLAY_LAST_SELL_DATE: pd.NaT,
            DISPLAY_HOLD_DAYS_EXACT: pd.NA,
            **values,
        }

    rows = [
        row(
            "가",
            first,
            {
                DISPLAY_AVG_BUY_PRICE: 61.1111,
                DISPLAY_AVG_SELL_PRICE: 120.0,
                DISPLAY_RETURN: 96.36,
                DISPLAY_WORST_VS_COST: -12.5,
                DISPLAY_BUY_CALENDAR_COUNT: 3,
                DISPLAY_SELL_CALENDAR_COUNT: 3,
                DISPLAY_EXCLUDED_REASON: REASON_NONE,
            },
        ),
        row(
            "가",
            second,
            {
                DISPLAY_AVG_BUY_PRICE: 100.0,
                DISPLAY_AVG_SELL_PRICE: np.nan,
                DISPLAY_RETURN: np.nan,
                DISPLAY_WORST_VS_COST: -3.0,
                DISPLAY_BUY_CALENDAR_COUNT: 2,
                DISPLAY_SELL_CALENDAR_COUNT: 0,
                DISPLAY_EXCLUDED_REASON: REASON_POSITION_BUYING,
            },
        ),
        row(
            "나",
            first,
            {
                DISPLAY_AVG_BUY_PRICE: 1.0,
                DISPLAY_AVG_SELL_PRICE: 2.0,
                DISPLAY_RETURN: 100.0,
                DISPLAY_WORST_VS_COST: -1.0,
                DISPLAY_BUY_CALENDAR_COUNT: 2,
                DISPLAY_SELL_CALENDAR_COUNT: 2,
                DISPLAY_EXCLUDED_REASON: REASON_NONE,
            },
        ),
    ]
    return pd.DataFrame(rows).astype({DISPLAY_HOLD_DAYS_EXACT: "Int64"})


def _bottoms() -> dict[str, pd.Timestamp]:
    """사이클(반감기 표지) → 바닥일 — `PLANTED` 의 두 바닥"""
    return {"2001-01-10": pd.Timestamp("2002-06-01"), "2004-02-20": pd.Timestamp("2005-08-01")}


# ============================================================
# ① 반감기 기준 · ③ 시간축 · 사이클 요약 — 가격만
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
        cycles = cycle_series(_close(), HALVING_DAYS)

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
        cycles = cycle_series(_close(), HALVING_DAYS)

        # Then
        assert [cycle["dates"][-1] for cycle in cycles] == ["2004-02-19", "2006-03-31"]
        assert [cycle["ongoing"] for cycle in cycles] == [False, True]

    def test_배수는_반감기일_종가가_1배이고_개월은_날_수를_30_4375_로_나눈_값이다(self) -> None:
        """
        목적: 가로축 · 세로축의 환산을 고정한다(§4.12 · §4.14 와 같은 정의).

        Given: 반감기일 종가 50, 151일 뒤(2001-06-10) 종가 30 인 시세
        When: 사이클 계열을 만든다
        Then: 반감기일 배수 1 · 그날 배수 0.6 · 경과 151 ÷ 30.4375 개월
        """
        # When
        first = cycle_series(_close(), HALVING_DAYS)[0]

        # Then
        position = first["dates"].index("2001-06-10")
        assert first["multiple"][0] == pytest.approx(1.0, abs=1e-12)
        assert first["multiple"][position] == pytest.approx(0.6, abs=1e-9)
        assert first["months"][position] == pytest.approx(151 / 30.4375, abs=1e-3)

    def test_데이터_끝_뒤의_반감기는_건너뛰고_앞_사이클이_데이터_끝까지_간다(self) -> None:
        """
        목적: 반감기 목록에 한 줄을 더한 날(그날 종가가 아직 없다) 차트가 멈추지 않는다 — 측정이 그 진입을
            「아직 오지 않음」으로 넘기는 것과 같다.

        Given: 데이터 끝(2006-03-31) 뒤의 셋째 반감기까지 넣은 반감기 목록
        When: 사이클 계열 · 요약 · 시간축 · 바닥 기준 선을 만든다
        Then: 사이클이 둘이고 둘째가 데이터 끝까지 가는 진행 중 사이클이다
        """
        # Given
        halvings = (*HALVING_DAYS, pd.Timestamp("2007-04-01"))

        # When
        cycles = cycle_series(_close(), halvings)
        summary = cycle_summary(_close(), halvings)
        timeline = timeline_series(_close(), halvings)
        bottoms = bottom_series(_close(), halvings, lead_months=LEAD)

        # Then
        assert [(cycle["dates"][-1], cycle["ongoing"]) for cycle in cycles] == [
            ("2004-02-19", False),
            ("2006-03-31", True),
        ]
        assert [row["halving"] for row in summary] == ["2001-01-10", "2004-02-20"]
        assert timeline["anchor"][-1].startswith("2004-02-20 반감기 뒤")
        assert len(bottoms) == 2

    def test_반감기일이_시세에_없으면_멈춘다(self) -> None:
        """
        목적: 1배의 기준 종가가 없는 사이클을 조용히 다른 날로 그리지 않는다.

        Given: 둘째 반감기일을 뺀 시세
        When: 사이클 계열을 만든다
        Then: ValueError
        """
        # Given
        close = _close().drop(HALVING_DAYS[1])

        # When / Then
        with pytest.raises(ValueError, match="반감기"):
            cycle_series(close, HALVING_DAYS)


class TestCycleSummary:
    """사이클 요약 — 고점은 반감기 뒤 24개월 안의 최고 종가, 바닥은 고점 뒤 최저 종가"""

    def test_고점은_반감기_뒤_24개월_안의_최고_종가다(self) -> None:
        """
        목적: 다음 반감기 직전의 더 높은 종가가 사이클 고점으로 잡히지 않는다(§4.14 — 2020 사이클의 2024-03-13).

        Given: 반감기 뒤 10개월에 300, 32개월(다음 반감기 앞)에 500 인 시세
        When: 요약을 만든다
        Then: 고점이 10개월 쪽이다
        """
        # When
        first = cycle_summary(_close(), HALVING_DAYS)[0]

        # Then
        assert (first["peak"], first["peak_close"]) == ("2001-11-10", pytest.approx(300.0, abs=0.01))

    def test_바닥은_고점_뒤_최저_종가다(self) -> None:
        """
        목적: 고점 앞의 더 낮은 종가를 바닥으로 잡지 않는다.

        Given: 고점 앞 10 · 고점 뒤 20 인 시세
        When: 요약을 만든다
        Then: 바닥이 고점 뒤의 20 이고, 경과 개월이 반감기에서 센 값이다
        """
        # When
        first = cycle_summary(_close(), HALVING_DAYS)[0]

        # Then
        assert (first["bottom"], first["bottom_close"]) == ("2002-06-01", pytest.approx(20.0, abs=0.01))
        assert first["bottom_months"] == pytest.approx(507 / 30.4375, abs=1e-3)

    def test_가격만_싣는다(self) -> None:
        """
        목적: MVRV 를 매매 방식에서 뺐으므로(결정 51) 요약에 MVRV 값이 남지 않는다.

        Given: 시세
        When: 요약을 만든다
        Then: 칸 이름에 `mvrv` · `below` 가 없다
        """
        # When
        summary = cycle_summary(_close(), HALVING_DAYS)

        # Then
        assert not [key for row in summary for key in row if "mvrv" in key or "below" in key]


class TestTimelineSeries:
    """전 기간 시간축 — 날마다 종가와 「어느 반감기 뒤 몇 개월」"""

    def test_호버_글자가_첫_반감기_전과_반감기_뒤_개월을_가른다(self) -> None:
        """
        목적: 날마다 기준 반감기와 경과 개월을 붙이고, 첫 반감기 앞은 따로 표시한다.

        Given: 첫 반감기 앞 · 뒤의 날
        When: 시간축 계열을 만든다
        Then: 앞은 「첫 반감기 전」, 90일 뒤는 그 반감기와 3.0개월
        """
        # When
        timeline = timeline_series(_close(), HALVING_DAYS)

        # Then
        dates = timeline["dates"]
        assert timeline["anchor"][dates.index("2000-12-31")] == "첫 반감기 전"
        assert timeline["anchor"][dates.index("2001-04-10")] == "2001-01-10 반감기 뒤 3.0개월"
        assert len(timeline["close"]) == len(dates)


# ============================================================
# ② 바닥 기준 사이클 겹치기
# ============================================================


class TestBottomSeries:
    """바닥마다 한 선 — 바닥 N개월 앞부터 다음 바닥 전날까지, 바닥 종가 = 1배"""

    def test_선은_바닥_앞_N개월에서_시작해_다음_바닥_전날에_끝나고_마지막은_데이터_끝까지다(self) -> None:
        """
        목적: 선의 구간을 고정한다 — 두 선이 같은 날을 나눠 갖지 않고, 마지막 선만 데이터 끝까지 간다.

        Given: 바닥 2002-06-01 · 2005-08-01 · 바닥 앞 3개월
        When: 바닥 기준 선을 만든다
        Then: 첫 선 2002-03-01 ~ 2005-07-31, 둘째 선 2005-05-01 ~ 2006-03-31
        """
        # When
        lines = bottom_series(_close(), HALVING_DAYS, lead_months=LEAD)

        # Then
        assert [(line["dates"][0], line["dates"][-1]) for line in lines] == [
            ("2002-03-01", "2005-07-31"),
            ("2005-05-01", "2006-03-31"),
        ]

    def test_배수는_바닥_종가가_1배이고_개월은_바닥에서_센다(self) -> None:
        """
        목적: 바닥 앞은 음수 개월, 바닥은 0개월 · 1배다.

        Given: 첫 바닥 종가 20
        When: 바닥 기준 선을 만든다
        Then: 바닥일 0개월 · 1배, 첫 날 −92 ÷ 30.4375 개월 · 100 ÷ 20 = 5배
        """
        # When
        first = bottom_series(_close(), HALVING_DAYS, lead_months=LEAD)[0]

        # Then
        position = first["dates"].index("2002-06-01")
        assert first["months"][position] == pytest.approx(0.0, abs=1e-12)
        assert first["multiple"][position] == pytest.approx(1.0, abs=1e-12)
        assert first["months"][0] == pytest.approx(-92 / 30.4375, abs=1e-3)
        assert first["multiple"][0] == pytest.approx(5.0, abs=1e-9)

    def test_진행_중_사이클의_바닥은_잠정이고_어느_사이클의_바닥인지_싣는다(self) -> None:
        """
        목적: 데이터가 늘면 바뀌는 바닥을 확정된 것처럼 그리지 않는다. 회차 점을 그 선에 찍으려면 사이클을 알아야 한다.

        Given: 끝난 첫 사이클 · 진행 중인 둘째 사이클
        When: 바닥 기준 선을 만든다
        Then: 잠정 표시가 거짓 · 참이고 사이클이 각 반감기 표지다
        """
        # When
        lines = bottom_series(_close(), HALVING_DAYS, lead_months=LEAD)

        # Then
        assert [(line["halving"], line["bottom"], line["provisional"]) for line in lines] == [
            ("2001-01-10", "2002-06-01", False),
            ("2004-02-20", "2005-08-01", True),
        ]

    def test_바닥_앞이_데이터_앞이면_데이터_첫_날에서_시작한다(self) -> None:
        """
        목적: 데이터 밖의 날을 지어내지 않는다.

        Given: 바닥 앞 30개월 — 첫 선의 시작(1999-12-01)이 데이터 첫 날(2000-06-01) 앞이다
        When: 바닥 기준 선을 만든다
        Then: 첫 선이 데이터 첫 날에서 시작한다
        """
        # When
        first = bottom_series(_close(), HALVING_DAYS, lead_months=30)[0]

        # Then
        assert first["dates"][0] == "2000-06-01"


# ============================================================
# 달력 분할 — 폭 · 기간 띠 · 회차 점 · 숫자표
# ============================================================


class TestChartSplit:
    """차트가 그릴 폭 — 이름으로 찾고, 매수 · 매도 개월을 회차 수와 간격에서 낸다"""

    def test_이름으로_폭을_찾고_첫_마지막_개월을_낸다(self) -> None:
        """
        목적: 첫 회차 개월은 마지막 회차와 간격에서 나온다 — 측정과 같은 산술이다.

        Given: 폭 둘 · 간격 2개월
        When: 「가」를 찾아 정보를 만든다
        Then: 매수 5 ~ 9 · 매도 1 ~ 5 · 회차 3
        """
        # When
        info = split_info(chart_split((OTHER, SPLIT), "가"), step_months=STEP)

        # Then
        assert info == {"name": "가", "tranches": 3, "buy": [5, 9], "sell": [1, 5]}

    def test_없는_이름이면_멈춘다(self) -> None:
        """
        목적: 차트가 그릴 폭이 측정 목록에 없으면 빈 차트를 그리지 않는다.

        Given: 「가」 · 「나」만 있는 목록
        When: 「다」를 찾는다
        Then: ValueError
        """
        # When / Then
        with pytest.raises(ValueError, match="다"):
            chart_split((OTHER, SPLIT), "다")


class TestWindowBands:
    """전 기간 시간축의 기간 띠 — 반감기마다 매도 띠(앞 사이클 포지션)와 매수 띠"""

    def test_반감기마다_매도_띠와_매수_띠이고_첫_반감기에는_매도_띠가_없다(self) -> None:
        """
        목적: 띠가 어느 포지션의 것인지 고정한다 — 반감기 뒤의 매도는 앞 반감기 포지션을 판다.

        Given: 반감기 둘 · 「가」(매수 5 ~ 9 · 매도 1 ~ 5개월) · 데이터 끝 2006-03-31
        When: 띠를 만든다
        Then: 첫 반감기는 매수 띠만, 둘째는 매도 띠(첫 사이클 포지션)와 매수 띠
        """
        # When
        bands = window_bands(HALVING_DAYS, DATA_END, SPLIT, step_months=STEP)

        # Then
        assert bands == [
            {"side": SPLIT_SIDE_BUY, "cycle": "2001-01-10", "x0": "2001-06-10", "x1": "2001-10-10"},
            {"side": SPLIT_SIDE_SELL, "cycle": "2001-01-10", "x0": "2004-03-20", "x1": "2004-07-20"},
            {"side": SPLIT_SIDE_BUY, "cycle": "2004-02-20", "x0": "2004-07-20", "x1": "2004-11-20"},
        ]

    def test_데이터_끝에서_자르고_데이터_뒤에서_시작하는_띠는_없다(self) -> None:
        """
        목적: 아직 오지 않은 기간을 그리지 않는다.

        Given: 데이터 끝 2004-07-01 — 둘째 반감기의 매도 띠 중간, 매수 띠 앞
        When: 띠를 만든다
        Then: 매도 띠는 2004-07-01 에서 끝나고 둘째 매수 띠는 없다
        """
        # When
        bands = window_bands(HALVING_DAYS, pd.Timestamp("2004-07-01"), SPLIT, step_months=STEP)

        # Then
        assert bands[-1] == {"side": SPLIT_SIDE_SELL, "cycle": "2001-01-10", "x0": "2004-03-20", "x1": "2004-07-01"}
        assert len(bands) == 2


class TestSplitPoints:
    """회차 점 — 측정 표의 체결 행을 세 축의 자리로 옮긴다"""

    def test_그_폭의_체결한_회차만_옮긴다(self) -> None:
        """
        목적: 다른 폭의 행과 체결 전 회차를 점으로 찍지 않는다 — 아직 오지 않은 날에 산 것처럼 보인다.

        Given: 「가」 체결 8 · 체결 전 4 · 「나」 체결 1
        When: 「가」의 점을 만든다
        Then: 점이 8개이고 날짜 · 종가 · 회차가 표 그대로다
        """
        # When
        points = split_points(_fills(), "가", _close(), _bottoms())

        # Then
        assert len(points) == 8
        assert [(point["side"], point["tranche"], point["date"]) for point in points[:4]] == [
            (SPLIT_SIDE_BUY, 1, "2001-06-10"),
            (SPLIT_SIDE_BUY, 2, "2001-08-10"),
            (SPLIT_SIDE_BUY, 3, "2001-10-10"),
            (SPLIT_SIDE_SELL, 1, "2004-03-20"),
        ]
        assert points[0]["close"] == pytest.approx(30.0, abs=1e-9)

    def test_매수는_그_반감기_선_매도는_다음_반감기_선의_같은_자리에_온다(self) -> None:
        """
        목적: ① 에서 점이 선 위에 앉는다 — 가로는 기준 반감기에서 센 개월, 세로는 그 반감기일 종가 대비 배수다.

        Given: 매수 1회차 2001-06-10(30, 기준 2001-01-10 종가 50) · 매도 1회차 2004-03-20(160, 기준 2004-02-20 종가 80)
        When: 점을 만든다
        Then: 매수 151 ÷ 30.4375 개월 · 0.6배, 매도 29 ÷ 30.4375 개월 · 2배, 기준 반감기가 각 선이다
        """
        # When
        points = split_points(_fills(), "가", _close(), _bottoms())

        # Then
        buy, sell = points[0], points[3]
        assert (buy["anchor"], sell["anchor"]) == ("2001-01-10", "2004-02-20")
        assert buy["halving_months"] == pytest.approx(151 / 30.4375, abs=1e-3)
        assert buy["halving_multiple"] == pytest.approx(0.6, abs=1e-5)
        assert sell["halving_months"] == pytest.approx(29 / 30.4375, abs=1e-3)
        assert sell["halving_multiple"] == pytest.approx(2.0, abs=1e-5)

    def test_바닥_축에서는_포지션_사이클의_바닥에서_센다(self) -> None:
        """
        목적: ② 에서 한 포지션의 회차가 그 사이클 바닥의 선 하나에 모인다 — 매도도 다음 바닥이 아니라 그 바닥에서 센다.

        Given: 첫 사이클 포지션 · 바닥 2002-06-01(20)
        When: 점을 만든다
        Then: 매수 −356 ÷ 30.4375 개월 · 1.5배, 매도 658 ÷ 30.4375 개월 · 8배, 사이클이 첫 반감기다
        """
        # When
        points = split_points(_fills(), "가", _close(), _bottoms())

        # Then
        buy, sell = points[0], points[3]
        assert (buy["cycle"], sell["cycle"]) == ("2001-01-10", "2001-01-10")
        assert buy["bottom_months"] == pytest.approx(-356 / 30.4375, abs=1e-3)
        assert buy["bottom_multiple"] == pytest.approx(1.5, abs=1e-5)
        assert sell["bottom_months"] == pytest.approx(658 / 30.4375, abs=1e-3)
        assert sell["bottom_multiple"] == pytest.approx(8.0, abs=1e-5)

    def test_없는_폭이면_멈춘다(self) -> None:
        """
        목적: 이름이 어긋나 점이 하나도 없는 차트를 조용히 그리지 않는다.

        Given: 「다」 행이 없는 회차 표
        When: 「다」의 점을 만든다
        Then: ValueError
        """
        # When / Then
        with pytest.raises(ValueError, match="다"):
            split_points(_fills(), "다", _close(), _bottoms())


class TestSplitTable:
    """숫자표 — 그 폭의 사이클마다 한 행, 값은 측정 표 그대로"""

    def test_사이클마다_한_행이고_값은_포지션_표_그대로다(self) -> None:
        """
        목적: 차트가 성적을 다시 계산하지 않는다 — 같은 시세면 CSV 와 같다(결정 ㊿).

        Given: 「가」 두 사이클 · 「나」 한 사이클
        When: 「가」의 표를 만든다
        Then: 두 행이고 평균 매수가 · 평균 매도가 · 수익률 · 최악 · 회차 수가 포지션 표 그대로다
        """
        # When
        rows = split_table(_fills(), _positions(), "가")

        # Then
        assert [row["halving"] for row in rows] == ["2001-01-10", "2004-02-20"]
        first = rows[0]
        assert (first["tranches"], first["buys"], first["sells"]) == (3, 3, 3)
        assert first["avg_buy"] == pytest.approx(61.1111, abs=1e-9)
        assert first["avg_sell"] == pytest.approx(120.0, abs=1e-9)
        assert first["return"] == pytest.approx(96.36, abs=1e-9)
        assert first["worst"] == pytest.approx(-12.5, abs=1e-9)
        assert first["reason"] is None

    def test_기간은_체결한_회차의_첫_날과_마지막_날이다(self) -> None:
        """
        목적: 산 기간 · 판 기간은 체결한 회차에서 낸다 — 매수 중인 사이클은 판 기간이 비고 끝나지 않은 사유가 남는다.

        Given: 첫 사이클은 다 사고 다 팔았고, 둘째는 두 회차만 샀다
        When: 표를 만든다
        Then: 첫 사이클 2001-06-10 ~ 2001-10-10 · 2004-03-20 ~ 2004-07-20, 둘째 2004-07-20 ~ 2004-09-20 · 판 기간 없음 ·
            「매수 회차가 남음」 · 수익률 없음
        """
        # When
        rows = split_table(_fills(), _positions(), "가")

        # Then
        first, second = rows
        assert (first["first_buy"], first["last_buy"], first["first_sell"], first["last_sell"]) == (
            "2001-06-10",
            "2001-10-10",
            "2004-03-20",
            "2004-07-20",
        )
        assert (second["first_buy"], second["last_buy"], second["first_sell"], second["last_sell"]) == (
            "2004-07-20",
            "2004-09-20",
            None,
            None,
        )
        assert (second["buys"], second["sells"], second["return"], second["reason"]) == (
            2,
            0,
            None,
            REASON_POSITION_BUYING,
        )


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
