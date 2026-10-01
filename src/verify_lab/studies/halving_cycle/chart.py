"""반감기_사이클 판단용 차트 — 측정 · 체결 산출물과 시세를 HTML 한 장의 차트 데이터로 옮긴다

**3단계에서 고를 것(매매 방식 → 칸 · 창 → 손절)을 사람이 보고 고르게 하는 보기다** (설계 결정 ㊾ · ㊿).
칸을 고르지 않고 판정하지 않는다 — **`1차 판정` 은 싣지 않는다.** ③ 이 기준선 대비 차이를 색으로 보이므로 같은
화면에 판정을 두면 기준선이 탈락 근거로 읽힌다(루트 `CLAUDE.md` 「기준선을 넘지 못하는 것은 탈락 사유가 아닙니다」).

**③ ④ ⑤ 는 산출물의 표시용 프레임을 옮기기만 한다** — `run_halving_cycle.py` 가 CSV 로 쓰는 바로 그 프레임이라
같은 시세면 차트 값이 CSV 와 같다. 산출물에 없는 값은 ③ 의 중앙값 하나다 — 다음 사이클 칸은 어느 표에도
중앙값이 없어, 256칸을 한 정의로 내려고 전부 거래내역 무손절 수익률에서 낸다.
① ② 는 시세를 그리는 보기라 배수 · 경과 개월 · 고점 · 바닥을 여기서 낸다.

**plotly 를 가져오지 않는다** — plotly.js 는 CLI 가 받아 넘긴다(개발 의존성이라 패키지가 기대지 않는다).
"""

import json
import math
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from verify_lab.common_constants import CHARTS_DIR, COL_CLOSE, COL_DATE, KST, PRICE_DECIMALS
from verify_lab.execution.constants import (
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
from verify_lab.measure.statistics import COL_LOSS_RATE, COL_MEAN, COL_WIN_RATE, mean_rate_conflict
from verify_lab.report.constants import (
    DATE_FORMAT,
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
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_UP_RATE,
    DISPLAY_UP_RATE_DIFF,
    PERCENT_DECIMALS,
)
from verify_lab.report.run_summary import (
    KEY_DATASET_FILE,
    KEY_DATASET_PERIOD,
    KEY_DATASET_ROWS,
    dataset_record,
    format_period,
)
from verify_lab.studies.halving_cycle.constants import (
    BASELINE_PREFIX,
    COL_MVRV,
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
    ENTRY_MONTHS,
    EXIT_MONTHS,
    FIELD_GRID_BASELINE,
    FIELD_SPLIT_FILLS,
    FIELD_SPLIT_POSITIONS,
    HALVINGS,
    INDICATOR_DECIMALS,
    SPLIT_BUY_BOOK_LEVELS,
    SPLIT_BUY_RANK_LEVELS,
    SPLIT_RANK_MIN_DAYS,
    SPLIT_RANK_YEARS,
    SPLIT_SELL_BOOK_LEVELS,
    SPLIT_SELL_RANK_LEVELS,
    SPLIT_SIDE_BUY,
    SPLIT_SIDE_SELL,
    SPLIT_THRESHOLD_NONE,
    STOP_LEVELS,
    TRACK_NAME,
    Dataset,
)
from verify_lab.studies.halving_cycle.runner import display_tables, load_dataset, load_onchain, run_study
from verify_lab.studies.halving_cycle.split_rule import trailing_rank
from verify_lab.studies.halving_cycle.trading import run_halving_cycle_trading
from verify_lab.tracks import track_of

CHART_FILENAME: Final = "판단차트.html"
TEMPLATE_PATH: Final = Path(__file__).with_name("chart_template.html")

# 템플릿의 자리표시. **한 번씩만 있어야 한다** — `render_html` 이 센다
DATA_MARKER: Final = "__CHART_DATA__"
PLOTLY_MARKER: Final = "__PLOTLY_JS__"

# 반감기 뒤 경과 개월의 환산 — `설계.md` §4.12 와 같다. 격자의 달력월(반감기일 + N개월)과 이틀 안쪽으로 다르다
DAYS_PER_MONTH: Final = 30.4375

# 사이클 고점을 찾는 창(개월). **반감기 ~ 다음 반감기 전체로 잡지 않는다** — 2020 사이클이 다음 반감기 직전
# (2024-03-13)을 고점으로 물어, 시장 사이클의 고점(2021-11-08)과 어긋난다(`설계.md` §4.14)
PEAK_WINDOW_MONTHS: Final = 24

# 시간축에 칠하는 해 — 반감기 뒤 2년차 · 4년차(0 이 첫 해)
BAND_YEARS: Final = (1, 3)

# 차트 데이터의 자릿수. 그리는 데만 쓰는 값이라 산출물 반올림표에 없다
MONTHS_DECIMALS: Final = 3
MULTIPLE_DECIMALS: Final = 5

# 표시용 프레임에서 읽는 컬럼
_PERFORMANCE_COLUMNS: Final = (
    DISPLAY_TICKER,
    DISPLAY_ENTRY_MONTHS,
    DISPLAY_EXIT_MONTHS,
    DISPLAY_STOP_LEVEL,
    DISPLAY_PERIOD,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_TOTAL,
    DISPLAY_MEAN,
    DISPLAY_WIN_RATE,
    DISPLAY_MIN,
    DISPLAY_WORST_HOLD,
    DISPLAY_GAP_STOP_COUNT,
    DISPLAY_INTRADAY_STOP_COUNT,
    DISPLAY_LOSING_COUNT,
)
_TRADE_COLUMNS: Final = (
    DISPLAY_TICKER,
    DISPLAY_ENTRY_MONTHS,
    DISPLAY_EXIT_MONTHS,
    DISPLAY_HALVING,
    DISPLAY_STOP_LEVEL,
    DISPLAY_ENTRY_DATE,
    DISPLAY_ENTRY_PRICE,
    DISPLAY_EXIT_DATE,
    DISPLAY_EXIT_PRICE,
    DISPLAY_RETURN,
    DISPLAY_WORST_HOLD,
    DISPLAY_FORK_SHARE,
)
_BASELINE_SAMPLE: Final = f"{BASELINE_PREFIX}{DISPLAY_SAMPLE_COUNT}"
_BASELINE_MEAN: Final = f"{BASELINE_PREFIX}{DISPLAY_MEAN}"
_BASELINE_MEDIAN: Final = f"{BASELINE_PREFIX}{DISPLAY_MEDIAN}"
_BASELINE_UP_RATE: Final = f"{BASELINE_PREFIX}{DISPLAY_UP_RATE}"
_BASELINE_NON_OVERLAPPING: Final = f"{BASELINE_PREFIX}{DISPLAY_NON_OVERLAPPING}"
_GRID_BASELINE_COLUMNS: Final = (
    DISPLAY_TICKER,
    DISPLAY_ENTRY_MONTHS,
    DISPLAY_EXIT_MONTHS,
    DISPLAY_HOLD_MONTHS,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_EXCLUDED,
    _BASELINE_SAMPLE,
    _BASELINE_NON_OVERLAPPING,
    _BASELINE_MEAN,
    _BASELINE_MEDIAN,
    _BASELINE_UP_RATE,
    DISPLAY_MEAN_DIFF,
    DISPLAY_MEDIAN_DIFF,
    DISPLAY_UP_RATE_DIFF,
)
_FILL_COLUMNS: Final = (
    DISPLAY_SPLIT_SIDE,
    DISPLAY_SPLIT_THRESHOLD,
    DISPLAY_SPLIT_START_ANCHOR,
    DISPLAY_SPLIT_START_MONTHS,
    DISPLAY_SPLIT_LAST_DEADLINE,
    DISPLAY_HALVING,
    DISPLAY_SPLIT_TRANCHE,
    DISPLAY_SPLIT_DEADLINE,
    DISPLAY_SPLIT_FILL_DATE,
    DISPLAY_SPLIT_FILL_CLOSE,
    DISPLAY_SPLIT_TRIGGER,
    DISPLAY_SPLIT_PRIOR_MVRV,
    DISPLAY_SPLIT_PRIOR_RANK,
    DISPLAY_EXCLUDED_REASON,
)
_POSITION_COLUMNS: Final = (
    DISPLAY_BUY_THRESHOLD,
    DISPLAY_BUY_START_ANCHOR,
    DISPLAY_BUY_START_MONTHS,
    DISPLAY_BUY_LAST_DEADLINE,
    DISPLAY_SELL_THRESHOLD,
    DISPLAY_SELL_START_MONTHS,
    DISPLAY_SELL_LAST_DEADLINE,
    DISPLAY_HALVING,
    DISPLAY_AVG_BUY_PRICE,
    DISPLAY_AVG_SELL_PRICE,
    DISPLAY_RETURN,
    DISPLAY_WORST_VS_COST,
    DISPLAY_FIRST_BUY_DATE,
    DISPLAY_LAST_SELL_DATE,
    DISPLAY_EXCLUDED_REASON,
)

Cell = tuple[int, int]


# ============================================================
# 값 옮기기 — 빈값을 JSON 의 null 로
# ============================================================


def _is_missing(value: object) -> bool:
    """표의 빈값인가 — `None` · `NaN` · `pd.NA` · `NaT`.

    **JSON 에 `NaN` 이 들어가면 브라우저의 `JSON.parse` 가 페이지 데이터 전체를 못 읽는다** — 빈값은 전부 `null` 로 옮긴다.
    """
    if value is None or value is pd.NA or value is pd.NaT:
        return True
    return isinstance(value, float) and math.isnan(value)


def _number(value: object, digits: int) -> float | None:
    if _is_missing(value):
        return None
    return round(float(str(value)), digits)


def _count(value: object) -> int | None:
    if _is_missing(value):
        return None
    number = float(str(value))
    if not number.is_integer():
        raise ValueError(f"건수로 옮길 수 없는 값입니다: {value!r}")
    return int(number)


def _day(value: object) -> str | None:
    """날짜를 `YYYY-MM-DD` 로. 거래내역은 문자열, 분할 표는 `Timestamp` 로 들어온다"""
    if _is_missing(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime(DATE_FORMAT)
    if isinstance(value, str):
        return value
    raise ValueError(f"날짜로 옮길 수 없는 값입니다: {value!r}")


def _text(value: object) -> str | None:
    if _is_missing(value):
        return None
    return str(value)


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name}에 차트가 읽는 컬럼이 없습니다: {missing}")


def _require_single_ticker(frame: pd.DataFrame, name: str) -> None:
    tickers = frame[DISPLAY_TICKER].dropna().unique().tolist()
    if len(tickers) > 1:
        raise ValueError(f"{name}에 종목이 여럿입니다 — 차트는 대상 하나만 그립니다: {tickers}")


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{str(key): value for key, value in row.items()} for row in frame.to_dict("records")]


# ============================================================
# ① ② — 사이클 겹치기 · 전 기간 시간축
# ============================================================


def _months_after(day: pd.Timestamp, start: pd.Timestamp) -> float:
    return (day - start).days / DAYS_PER_MONTH


def _cycle_segments(
    close: pd.Series, halving_days: Sequence[pd.Timestamp]
) -> list[tuple[pd.Timestamp, pd.Series, bool]]:
    """반감기마다 (반감기일, 그날 ~ 다음 반감기 전날의 종가, 진행 중인가).

    Raises:
        **데이터 끝 뒤의 반감기는 아직 오지 않은 것이라 건너뛴다** — 측정이 그 진입을 「아직 오지 않음」으로 넘기는 것과
    같다. 반감기 목록에 한 줄을 더한 날 종가가 아직 없어도 차트가 멈추지 않고, 앞 사이클이 데이터 끝까지 이어진다.

    Raises:
        ValueError: 날짜가 오름차순이 아니거나 겹치는 경우, 데이터 안에 반감기가 없거나 반감기가 오름차순이 아닌 경우,
            데이터 안의 반감기일 종가가 시세에 없는 경우 — 1배의 기준 종가가 없는 사이클을 다른 날로 그리면 예외 없이
            배수가 어긋난다
    """
    index = close.index
    if not isinstance(index, pd.DatetimeIndex) or not index.is_monotonic_increasing or index.has_duplicates:
        raise ValueError("종가는 날짜가 겹치지 않는 오름차순 날짜 인덱스여야 합니다")
    listed = list(halving_days)
    if any(later <= earlier for earlier, later in zip(listed, listed[1:], strict=False)):
        raise ValueError(f"반감기 날짜가 오름차순이 아닙니다: {listed}")
    days = [day for day in listed if len(index) and day <= index[-1]]
    if not days:
        raise ValueError(f"데이터 안에 반감기가 하나도 없습니다: {listed}")
    missing = [day.strftime(DATE_FORMAT) for day in days if day not in index]
    if missing:
        raise ValueError(f"반감기일의 종가가 시세에 없습니다: {missing}")

    segments: list[tuple[pd.Timestamp, pd.Series, bool]] = []
    for position, start in enumerate(days):
        ongoing = position + 1 == len(days)
        in_cycle = index >= start
        if not ongoing:
            in_cycle &= index < days[position + 1]
        segments.append((start, close[in_cycle], ongoing))

    return segments


def cycle_series(
    close: pd.Series, mvrv: pd.Series, rank: pd.Series, halving_days: Sequence[pd.Timestamp]
) -> list[dict[str, Any]]:
    """사이클 겹치기 — 반감기마다 경과 개월 · 반감기일 종가 대비 배수 · MVRV · 4년 순위(%).

    Args:
        close: 측정 계열 종가 (날짜 인덱스)
        mvrv: MVRV (날짜 인덱스). 종가의 날짜로 맞춘다 — 없는 날은 빈값이다
        rank: 4년 순위 (비율 0 ~ 1 · 날짜 인덱스). 백분율로 옮긴다
        halving_days: 반감기일 (오름차순)

    Returns:
        사이클마다 한 사전. 사이클은 반감기일부터 다음 반감기 전날까지이고, 마지막 사이클은 데이터 끝까지다
    """
    cycles: list[dict[str, Any]] = []
    for start, segment, ongoing in _cycle_segments(close, halving_days):
        base = float(segment.loc[start])
        days = pd.DatetimeIndex(segment.index)
        cycles.append(
            {
                "label": f"{start.year} 사이클",
                "short": f"{start.year}" + (" (진행 중)" if ongoing else ""),
                "ongoing": ongoing,
                "dates": [day.strftime(DATE_FORMAT) for day in days],
                "months": [round(_months_after(day, start), MONTHS_DECIMALS) for day in days],
                "multiple": [_number(value / base, MULTIPLE_DECIMALS) for value in segment.to_numpy(dtype=float)],
                "close": [_number(value, PRICE_DECIMALS) for value in segment.to_numpy(dtype=float)],
                "mvrv": [_number(value, INDICATOR_DECIMALS) for value in mvrv.reindex(days).to_numpy(dtype=float)],
                "rank": [_number(value * 100, PERCENT_DECIMALS) for value in rank.reindex(days).to_numpy(dtype=float)],
            }
        )

    return cycles


def cycle_summary(
    close: pd.Series, mvrv: pd.Series, halving_days: Sequence[pd.Timestamp], *, buy_level: float
) -> list[dict[str, Any]]:
    """사이클 요약 — 고점 · 바닥과 그날의 MVRV, 고점 뒤 MVRV 가 처음 매수 문턱 이하인 날.

    **고점 · 바닥은 지나고 나서야 정해지는 값이라 매매 신호가 아니다** — 차트를 읽는 기준점이다.
    고점은 반감기 뒤 `PEAK_WINDOW_MONTHS` 개월 안의 최고 종가, 바닥은 고점 뒤 사이클 끝까지의 최저 종가다.

    Args:
        close: 측정 계열 종가 (날짜 인덱스)
        mvrv: MVRV (날짜 인덱스)
        halving_days: 반감기일 (오름차순)
        buy_level: 고점 뒤 처음 닿은 날을 찾는 MVRV 문턱 (이하)

    Returns:
        사이클마다 한 사전. 문턱 이하에 닿지 않은 사이클은 그 날을 비운다
    """
    rows: list[dict[str, Any]] = []
    for start, segment, ongoing in _cycle_segments(close, halving_days):
        days = pd.DatetimeIndex(segment.index)
        cycle_mvrv = mvrv.reindex(days)
        window = segment[days < start + pd.DateOffset(months=PEAK_WINDOW_MONTHS)]
        peak = pd.Timestamp(window.idxmax())
        after_peak = segment[days >= peak]
        bottom = pd.Timestamp(after_peak.idxmin())
        mvrv_after_peak = cycle_mvrv[days >= peak]
        below = mvrv_after_peak[mvrv_after_peak <= buy_level]
        known = cycle_mvrv.dropna()
        max_day = pd.Timestamp(known.idxmax()) if len(known) else None
        rows.append(
            {
                "halving": start.strftime(DATE_FORMAT),
                "base": _number(segment.loc[start], PRICE_DECIMALS),
                "end": days[-1].strftime(DATE_FORMAT),
                "end_months": round(_months_after(days[-1], start), MONTHS_DECIMALS),
                "ongoing": ongoing,
                "peak": peak.strftime(DATE_FORMAT),
                "peak_months": round(_months_after(peak, start), MONTHS_DECIMALS),
                "peak_close": _number(segment.loc[peak], PRICE_DECIMALS),
                "peak_mvrv": _number(cycle_mvrv.loc[peak], INDICATOR_DECIMALS),
                "first_below": _day(pd.Timestamp(below.index[0])) if len(below) else None,
                "first_below_months": round(_months_after(pd.Timestamp(below.index[0]), start), MONTHS_DECIMALS)
                if len(below)
                else None,
                "bottom": bottom.strftime(DATE_FORMAT),
                "bottom_months": round(_months_after(bottom, start), MONTHS_DECIMALS),
                "bottom_close": _number(segment.loc[bottom], PRICE_DECIMALS),
                "bottom_mvrv": _number(cycle_mvrv.loc[bottom], INDICATOR_DECIMALS),
                "max_mvrv": _number(known.max(), INDICATOR_DECIMALS) if len(known) else None,
                "max_mvrv_day": _day(max_day),
                "max_mvrv_months": round(_months_after(max_day, start), MONTHS_DECIMALS)
                if max_day is not None
                else None,
                "min_mvrv": _number(known.min(), INDICATOR_DECIMALS) if len(known) else None,
            }
        )

    return rows


def timeline_series(
    close: pd.Series, mvrv: pd.Series, rank: pd.Series, halving_days: Sequence[pd.Timestamp]
) -> dict[str, Any]:
    """전 기간 시간축 — 날마다 종가 · MVRV · 4년 순위(%)와 「어느 반감기 뒤 몇 개월」, 2 · 4년차 띠.

    Args:
        close: 측정 계열 종가 (날짜 인덱스)
        mvrv: MVRV (날짜 인덱스). 종가의 날짜로 맞춘다
        rank: 4년 순위 (비율 0 ~ 1 · 날짜 인덱스)
        halving_days: 반감기일 (오름차순)

    Returns:
        날짜 · 값 목록과 띠 목록. 띠는 다음 반감기(마지막 사이클은 데이터 끝)에서 자른다
    """
    segments = _cycle_segments(close, halving_days)
    days = pd.DatetimeIndex(close.index)
    starts = [start for start, _, _ in segments]
    positions = np.searchsorted(np.array(starts, dtype="datetime64[ns]"), days.to_numpy(), side="right") - 1
    anchors = [
        "첫 반감기 전"
        if position < 0
        else f"{starts[position].strftime(DATE_FORMAT)} 반감기 뒤 {_months_after(day, starts[position]):.1f}개월"
        for day, position in zip(days, positions, strict=True)
    ]

    bands: list[dict[str, str]] = []
    for position, start in enumerate(starts):
        stop = starts[position + 1] if position + 1 < len(starts) else days[-1]
        for year in BAND_YEARS:
            begin = start + pd.DateOffset(months=12 * year)
            if begin < stop:
                end = min(start + pd.DateOffset(months=12 * (year + 1)), stop)
                bands.append({"x0": begin.strftime(DATE_FORMAT), "x1": end.strftime(DATE_FORMAT)})

    return {
        "dates": [day.strftime(DATE_FORMAT) for day in days],
        "close": [_number(value, PRICE_DECIMALS) for value in close.to_numpy(dtype=float)],
        "mvrv": [_number(value, INDICATOR_DECIMALS) for value in mvrv.reindex(days).to_numpy(dtype=float)],
        "rank": [_number(value * 100, PERCENT_DECIMALS) for value in rank.reindex(days).to_numpy(dtype=float)],
        "anchor": anchors,
        "bands": bands,
    }


# ============================================================
# ③ — 격자 히트맵
# ============================================================


def _grid(entry_months: Sequence[int], exit_months: Sequence[int]) -> list[Cell]:
    return [(entry, exit_) for entry in entry_months for exit_ in exit_months]


def _cell_of(row: Mapping[str, Any]) -> Cell:
    return int(row[DISPLAY_ENTRY_MONTHS]), int(row[DISPLAY_EXIT_MONTHS])


def _no_stop(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame[DISPLAY_STOP_LEVEL] == NO_STOP_LABEL]


def _whole_period(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame[DISPLAY_PERIOD] == PERIOD_ALL]


def _trade(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "halving": _text(row[DISPLAY_HALVING]),
        "entry_date": _day(row[DISPLAY_ENTRY_DATE]),
        "entry_price": _number(row[DISPLAY_ENTRY_PRICE], PRICE_DECIMALS),
        "exit_date": _day(row[DISPLAY_EXIT_DATE]),
        "exit_price": _number(row[DISPLAY_EXIT_PRICE], PRICE_DECIMALS),
        "return": _number(row[DISPLAY_RETURN], PERCENT_DECIMALS),
        "worst_hold": _number(row[DISPLAY_WORST_HOLD], PERCENT_DECIMALS),
        "fork_share": _number(row[DISPLAY_FORK_SHARE], PERCENT_DECIMALS),
    }


def _baseline(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "hold": _count(row[DISPLAY_HOLD_MONTHS]),
        "cell_signals": _count(row[DISPLAY_SIGNAL_COUNT]),
        "cell_excluded": _count(row[DISPLAY_EXCLUDED]),
        "sample": _count(row[_BASELINE_SAMPLE]),
        # **롤링 전수 표본만 두지 않는다** — 이웃 진입끼리 심하게 겹쳐 실제보다 단단해 보인다(`src/verify_lab/CLAUDE.md` 「비중첩 표본 계약」)
        "non_overlapping": _count(row[_BASELINE_NON_OVERLAPPING]),
        "mean": _number(row[_BASELINE_MEAN], PERCENT_DECIMALS),
        "median": _number(row[_BASELINE_MEDIAN], PERCENT_DECIMALS),
        "up_rate": _number(row[_BASELINE_UP_RATE], PERCENT_DECIMALS),
        "mean_diff": _number(row[DISPLAY_MEAN_DIFF], PERCENT_DECIMALS),
        "median_diff": _number(row[DISPLAY_MEDIAN_DIFF], PERCENT_DECIMALS),
        "up_rate_diff": _number(row[DISPLAY_UP_RATE_DIFF], PERCENT_DECIMALS),
    }


def _median(trades: Sequence[Mapping[str, Any]]) -> float | None:
    """거래내역 수익률(표에 실린 값)의 중앙값 — 체결이 없으면 비운다.

    **산출물에 없는 값이라 정의를 여기 하나만 둔다** — ③ 칸과 ④ 손절선이 같은 함수를 쓴다.
    반올림된 값의 중앙값이라 짝수 표본에서 격자기준선의 중앙값과 0.005 안쪽으로 다를 수 있다.
    """
    returns = [float(row[DISPLAY_RETURN]) for row in trades]
    if not returns:
        return None
    return _number(float(np.median(returns)), PERCENT_DECIMALS)


def _mean_rate_conflicts(rows: Sequence[Mapping[str, Any]]) -> list[bool]:
    """평균의 부호와 방향 비율이 어긋나는 행인가 (측정의 원칙 13).

    **판정은 `measure.statistics.mean_rate_conflict` 하나가 한다** — 여기서 다시 쓰면 같은 원칙이 두 답을 낸다.
    성적표에는 내린 비율이 없어 `질 때 표본 ÷ 신호`(손실로 끝난 체결의 비율)로 옮긴다. 표본이 없는 행은 어긋나지 않는다.
    """
    means: list[float] = []
    up_rates: list[float] = []
    down_rates: list[float] = []
    for row in rows:
        sample = _count(row[DISPLAY_SIGNAL_COUNT])
        losing = _count(row[DISPLAY_LOSING_COUNT])
        mean = _number(row[DISPLAY_MEAN], PERCENT_DECIMALS)
        up_rate = _number(row[DISPLAY_WIN_RATE], PERCENT_DECIMALS)
        if sample and losing is not None and mean is not None and up_rate is not None:
            means.append(mean)
            up_rates.append(up_rate / 100)
            down_rates.append(losing / sample)
        else:
            means.append(math.nan)
            up_rates.append(math.nan)
            down_rates.append(math.nan)
    frame = pd.DataFrame({COL_MEAN: means, COL_WIN_RATE: up_rates, COL_LOSS_RATE: down_rates})

    return [bool(flag) for flag in mean_rate_conflict(frame)]


def _unique_by_cell(frame: pd.DataFrame, name: str) -> dict[Cell, dict[str, Any]]:
    rows: dict[Cell, dict[str, Any]] = {}
    for row in _records(frame):
        cell = _cell_of(row)
        if cell in rows:
            raise ValueError(f"{name}에 칸 {cell} 의 행이 둘 이상입니다")
        rows[cell] = row

    return rows


def grid_cells(
    performance: pd.DataFrame,
    trades: pd.DataFrame,
    grid_baseline: pd.DataFrame,
    *,
    entry_months: Sequence[int],
    exit_months: Sequence[int],
) -> list[dict[str, Any]]:
    """격자 히트맵의 칸 — 진입 × 청산마다 성적표 무손절 · 전체 행, 중앙값, 기준선, 사이클별 체결.

    **무손절 행만 옮긴다** — 기준선(격자기준선)이 손절 없이 잰 값이라 손절 행과 견주면 뜻이 섞인다. 손절은 ④ 가 맡는다.

    Args:
        performance: 성적표 (표시용 프레임)
        trades: 거래내역 (표시용 프레임)
        grid_baseline: 격자기준선 (표시용 프레임) — 같은 사이클에 파는 칸(청산 > 진입)만 행이 있다
        entry_months: 진입 축
        exit_months: 청산 축

    Returns:
        진입 오름차순 · 청산 오름차순의 칸 목록. 표본이 없는 칸은 값을 비운다(0 이 아니다)

    Raises:
        ValueError: 컬럼이 없거나 종목이 여럿인 경우, 칸의 무손절 · 전체 행이 없거나 둘 이상인 경우,
            같은 사이클 칸의 기준선 행이 없는 경우 — 칸이 조용히 빈칸이 되면 히트맵에 구멍이 난다
    """
    _require_columns(performance, _PERFORMANCE_COLUMNS, "성적표")
    _require_columns(trades, _TRADE_COLUMNS, "거래내역")
    _require_columns(grid_baseline, _GRID_BASELINE_COLUMNS, "격자기준선")
    for frame, name in ((performance, "성적표"), (trades, "거래내역"), (grid_baseline, "격자기준선")):
        _require_single_ticker(frame, name)

    summaries = _unique_by_cell(_whole_period(_no_stop(performance)), "성적표 무손절 · 전체")
    baselines = _unique_by_cell(grid_baseline, "격자기준선")
    cell_trades: dict[Cell, list[dict[str, Any]]] = {}
    for row in _records(_no_stop(trades)):
        cell_trades.setdefault(_cell_of(row), []).append(row)

    grid = _grid(entry_months, exit_months)
    missing = [cell for cell in grid if cell not in summaries]
    if missing:
        raise ValueError(f"성적표에 칸의 무손절 · 전체 행이 없습니다: {missing}")
    conflicts = dict(zip(grid, _mean_rate_conflicts([summaries[cell] for cell in grid]), strict=True))

    cells: list[dict[str, Any]] = []
    for entry, exit_ in grid:
        summary = summaries[(entry, exit_)]
        same_cycle = exit_ > entry
        baseline = baselines.get((entry, exit_))
        if same_cycle and baseline is None:
            raise ValueError(f"격자기준선에 같은 사이클 칸 ({entry}, {exit_}) 의 기준선 행이 없습니다")
        rows = cell_trades.get((entry, exit_), [])
        cells.append(
            {
                "entry": entry,
                "exit": exit_,
                "next_cycle": not same_cycle,
                "sample": _count(summary[DISPLAY_SIGNAL_COUNT]),
                "total": _number(summary[DISPLAY_TOTAL], PERCENT_DECIMALS),
                "mean": _number(summary[DISPLAY_MEAN], PERCENT_DECIMALS),
                "median": _median(rows),
                "up_rate": _number(summary[DISPLAY_WIN_RATE], PERCENT_DECIMALS),
                "worst": _number(summary[DISPLAY_MIN], PERCENT_DECIMALS),
                "worst_hold": _number(summary[DISPLAY_WORST_HOLD], PERCENT_DECIMALS),
                "conflict": conflicts[(entry, exit_)],
                "baseline": _baseline(baseline) if same_cycle and baseline is not None else None,
                "trades": [_trade(row) for row in rows],
            }
        )

    return cells


# ============================================================
# ④ — 칸별 손절선
# ============================================================


def stop_rows(
    performance: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    entry_months: Sequence[int],
    exit_months: Sequence[int],
    stop_levels: Sequence[float | None],
) -> list[dict[str, Any]]:
    """칸마다 손절선 목록 순서로 성적표 전체 행을 옮기고, 손절선마다 거래내역의 중앙값을 붙인다.

    **평균만 두지 않는다** — 측정의 원칙 4(평균과 중앙값 병기). 성적표에 중앙값이 없어 ③ 과 같은 정의(`_median`)로 낸다.

    **발동 수는 장중손절과 갭손절의 합이다.** 둘 중 하나라도 비면(표본이 없는 칸) 비운다 — 0 이면 「한 번도 안 걸렸다」로 읽힌다.

    Args:
        performance: 성적표 (표시용 프레임)
        trades: 거래내역 (표시용 프레임) — 손절선마다 중앙값을 낸다
        entry_months: 진입 축
        exit_months: 청산 축
        stop_levels: 손절선 (비율, `None` 이 무손절). 이 순서로 싣는다

    Returns:
        칸마다 한 사전 — 손절선 목록

    Raises:
        ValueError: 컬럼이 없거나 종목이 여럿인 경우, 칸 · 손절선의 전체 행이 없거나 둘 이상인 경우 — 빠진 손절선이
            평평한 구간처럼 보인다
    """
    _require_columns(performance, _PERFORMANCE_COLUMNS, "성적표")
    _require_columns(trades, _TRADE_COLUMNS, "거래내역")
    for frame, name in ((performance, "성적표"), (trades, "거래내역")):
        _require_single_ticker(frame, name)

    labels = [stop_level_value(level, measurable=True) for level in stop_levels]
    stop_trades: dict[tuple[int, int, float | str], list[dict[str, Any]]] = {}
    for row in _records(trades):
        stop_trades.setdefault((*_cell_of(row), row[DISPLAY_STOP_LEVEL]), []).append(row)
    rows: dict[tuple[int, int, float | str], dict[str, Any]] = {}
    for row in _records(_whole_period(performance)):
        key = (*_cell_of(row), row[DISPLAY_STOP_LEVEL])
        if key in rows:
            raise ValueError(f"성적표에 칸 · 손절선 {key} 의 전체 행이 둘 이상입니다")
        rows[key] = row

    cells: list[dict[str, Any]] = []
    for entry, exit_ in _grid(entry_months, exit_months):
        found = [rows.get((entry, exit_, label)) for label in labels]
        missing = [label for label, row in zip(labels, found, strict=True) if row is None]
        if missing:
            raise ValueError(f"성적표에 칸 ({entry}, {exit_}) · 손절선 {missing} 의 전체 행이 없습니다")
        cell_rows = [row for row in found if row is not None]
        stops: list[dict[str, Any]] = []
        for label, row, conflict in zip(labels, cell_rows, _mean_rate_conflicts(cell_rows), strict=True):
            gap = _count(row[DISPLAY_GAP_STOP_COUNT])
            intraday = _count(row[DISPLAY_INTRADAY_STOP_COUNT])
            stops.append(
                {
                    "stop": label,
                    "sample": _count(row[DISPLAY_SIGNAL_COUNT]),
                    "total": _number(row[DISPLAY_TOTAL], PERCENT_DECIMALS),
                    "mean": _number(row[DISPLAY_MEAN], PERCENT_DECIMALS),
                    "median": _median(stop_trades.get((entry, exit_, label), [])),
                    "up_rate": _number(row[DISPLAY_WIN_RATE], PERCENT_DECIMALS),
                    "worst": _number(row[DISPLAY_MIN], PERCENT_DECIMALS),
                    "worst_hold": _number(row[DISPLAY_WORST_HOLD], PERCENT_DECIMALS),
                    "triggered": None if gap is None or intraday is None else gap + intraday,
                    "conflict": conflict,
                }
            )
        cells.append({"entry": entry, "exit": exit_, "stops": stops})

    return cells


# ============================================================
# ⑤ — 혼합 분할
# ============================================================


def _leg_key(side: str, threshold: str, anchor: str | None, start: int | None, deadline: int) -> str:
    return "|".join((side, threshold, anchor or "", "" if start is None else str(start), str(deadline)))


def _leg_label(side: str, threshold: str, anchor: str | None, start: int | None, deadline: int) -> str:
    """목록에서 조합을 고를 때 이름만 보고 문턱 · 시작 · 기한을 안다"""
    if threshold == SPLIT_THRESHOLD_NONE:
        return f"{threshold} · 기한 {deadline}개월"
    if side == SPLIT_SIDE_SELL:
        return f"{threshold} · 다음 반감기 뒤 {start}개월부터 · 기한 {deadline}개월"
    if anchor is None or start is None:
        raise ValueError(f"온체인 매수 조합에 시작 기준이나 시작 개월이 없습니다: {threshold} · 기한 {deadline}")

    return f"{threshold} · {anchor} 뒤 {start}개월부터 · 기한 {deadline}개월"


def _leg(side: str, threshold: str, anchor: str | None, start: int | None, deadline: int) -> dict[str, Any]:
    return {
        "key": _leg_key(side, threshold, anchor, start, deadline),
        "label": _leg_label(side, threshold, anchor, start, deadline),
        "threshold": threshold,
        "anchor": anchor,
        "start": start,
        "deadline": deadline,
    }


def _with_calendar_keys(legs: list[dict[str, Any]], side: str) -> list[dict[str, Any]]:
    """조합마다 마지막 기한이 같은 달력만 조합을 짝으로 단다 — ⑤ 가 「같은 기한의 달력만」과 견준다"""
    calendar = {leg["deadline"]: leg["key"] for leg in legs if leg["threshold"] == SPLIT_THRESHOLD_NONE}
    paired: list[dict[str, Any]] = []
    for leg in legs:
        key = calendar.get(leg["deadline"])
        if key is None:
            raise ValueError(f"기한 {leg['deadline']}개월의 달력만 {side} 조합이 없어 견줄 대조군이 없습니다: {leg['label']}")
        paired.append({**leg, "calendar_key": key})

    return paired


def split_view(fills: pd.DataFrame, positions: pd.DataFrame) -> dict[str, Any]:
    """혼합 분할 — 조합 목록 · 조합 × 사이클의 회차 · 매수 × 매도 × 사이클의 포지션.

    **체결 전 회차는 점으로 싣지 않고 건수로 남긴다** — 그리면 아직 오지 않은 날에 산 것처럼 보인다.

    Args:
        fills: 분할회차 (표시용 프레임)
        positions: 분할포지션 (표시용 프레임)

    Returns:
        `buy_legs` · `sell_legs`(회차 표에 나온 순서 · 같은 기한의 달력만 짝) · `cycles` · `fills` · `positions`

    Raises:
        ValueError: 컬럼이 없거나 종목이 여럿인 경우, 같은 기한의 달력만 조합이 없는 경우, 포지션이 회차 표에 없는
            조합을 가리키는 경우
    """
    _require_columns(fills, _FILL_COLUMNS, "분할회차")
    _require_columns(positions, _POSITION_COLUMNS, "분할포지션")
    for frame, name in ((fills, "분할회차"), (positions, "분할포지션")):
        _require_single_ticker(frame, name)

    legs: dict[str, dict[str, dict[str, Any]]] = {SPLIT_SIDE_BUY: {}, SPLIT_SIDE_SELL: {}}
    fill_view: dict[str, dict[str, dict[str, Any]]] = {}
    for row in _records(fills):
        side = str(row[DISPLAY_SPLIT_SIDE])
        if side not in legs:
            raise ValueError(f"분할회차의 매수 · 매도 값이 아닙니다: {side!r}")
        anchor = _text(row[DISPLAY_SPLIT_START_ANCHOR]) if side == SPLIT_SIDE_BUY else None
        leg = _leg(
            side,
            str(row[DISPLAY_SPLIT_THRESHOLD]),
            anchor,
            _count(row[DISPLAY_SPLIT_START_MONTHS]),
            int(row[DISPLAY_SPLIT_LAST_DEADLINE]),
        )
        legs[side].setdefault(leg["key"], leg)
        cycle = fill_view.setdefault(leg["key"], {}).setdefault(
            str(row[DISPLAY_HALVING]), {"points": [], "pending": 0, "reasons": []}
        )
        fill_date = _day(row[DISPLAY_SPLIT_FILL_DATE])
        if fill_date is None:
            cycle["pending"] += 1
            reason = _text(row[DISPLAY_EXCLUDED_REASON])
            if reason and reason not in cycle["reasons"]:
                cycle["reasons"].append(reason)
            continue
        cycle["points"].append(
            {
                "tranche": int(row[DISPLAY_SPLIT_TRANCHE]),
                "deadline": _day(row[DISPLAY_SPLIT_DEADLINE]),
                "date": fill_date,
                "close": _number(row[DISPLAY_SPLIT_FILL_CLOSE], PRICE_DECIMALS),
                "trigger": _text(row[DISPLAY_SPLIT_TRIGGER]),
                "prior_mvrv": _number(row[DISPLAY_SPLIT_PRIOR_MVRV], INDICATOR_DECIMALS),
                "prior_rank": _number(row[DISPLAY_SPLIT_PRIOR_RANK], PERCENT_DECIMALS),
            }
        )

    cycles: list[str] = []
    position_view: dict[str, dict[str, dict[str, Any]]] = {}
    for row in _records(positions):
        buy_key = _leg_key(
            SPLIT_SIDE_BUY,
            str(row[DISPLAY_BUY_THRESHOLD]),
            _text(row[DISPLAY_BUY_START_ANCHOR]),
            _count(row[DISPLAY_BUY_START_MONTHS]),
            int(row[DISPLAY_BUY_LAST_DEADLINE]),
        )
        sell_key = _leg_key(
            SPLIT_SIDE_SELL,
            str(row[DISPLAY_SELL_THRESHOLD]),
            None,
            _count(row[DISPLAY_SELL_START_MONTHS]),
            int(row[DISPLAY_SELL_LAST_DEADLINE]),
        )
        if buy_key not in legs[SPLIT_SIDE_BUY] or sell_key not in legs[SPLIT_SIDE_SELL]:
            raise ValueError(f"분할포지션이 분할회차에 없는 조합을 가리킵니다: {buy_key} × {sell_key}")
        cycle = str(row[DISPLAY_HALVING])
        if cycle not in cycles:
            cycles.append(cycle)
        position_view.setdefault(buy_key, {}).setdefault(sell_key, {})[cycle] = {
            "avg_buy": _number(row[DISPLAY_AVG_BUY_PRICE], PRICE_DECIMALS),
            "avg_sell": _number(row[DISPLAY_AVG_SELL_PRICE], PRICE_DECIMALS),
            "return": _number(row[DISPLAY_RETURN], PERCENT_DECIMALS),
            "worst": _number(row[DISPLAY_WORST_VS_COST], PERCENT_DECIMALS),
            "first_buy": _day(row[DISPLAY_FIRST_BUY_DATE]),
            "last_sell": _day(row[DISPLAY_LAST_SELL_DATE]),
            "reason": _text(row[DISPLAY_EXCLUDED_REASON]) or None,
        }

    return {
        "buy_legs": _with_calendar_keys(list(legs[SPLIT_SIDE_BUY].values()), SPLIT_SIDE_BUY),
        "sell_legs": _with_calendar_keys(list(legs[SPLIT_SIDE_SELL].values()), SPLIT_SIDE_SELL),
        "cycles": cycles,
        "fills": fill_view,
        "positions": position_view,
    }


# ============================================================
# 렌더 · 조립
# ============================================================


def render_html(template: str, data: Mapping[str, Any], plotly_js: str) -> str:
    """템플릿의 자리표시 둘에 차트 데이터(JSON)와 plotly.js 를 넣는다.

    **한 번에 나눠 끼운다** — 넣은 글자 속에 자리표시와 같은 글자가 있어도 다시 바뀌지 않는다.
    데이터 속 `</` 는 `<\\/` 로 바꿔 데이터가 제 `<script>` 를 닫지 못하게 한다.

    Args:
        template: HTML 템플릿. 자리표시 둘이 한 번씩 있어야 한다
        data: 차트 데이터. JSON 으로 바뀌며 `NaN` 이 있으면 안 된다
        plotly_js: plotly.js 본문

    Returns:
        완성된 HTML

    Raises:
        ValueError: 자리표시가 없거나 둘 이상인 경우, 데이터에 `NaN` · 무한대가 있는 경우(브라우저의 `JSON.parse` 가
            페이지 데이터 전체를 못 읽는다), plotly.js 가 `</script` 를 담은 경우
    """
    if "</script" in plotly_js.lower():
        raise ValueError("plotly.js 본문에 `</script` 가 있어 페이지에 그대로 넣을 수 없습니다")
    for marker in (DATA_MARKER, PLOTLY_MARKER):
        count = template.count(marker)
        if count != 1:
            raise ValueError(f"템플릿의 자리표시 {marker} 가 {count}번 있습니다 — 한 번이어야 합니다")

    data_text = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":")).replace("</", "<\\/")
    pieces = re.split(f"({re.escape(DATA_MARKER)}|{re.escape(PLOTLY_MARKER)})", template)
    fills = {DATA_MARKER: data_text, PLOTLY_MARKER: plotly_js}

    return "".join(fills.get(piece, piece) for piece in pieces)


def chart_path() -> Path:
    """차트 파일 경로 — `CHARTS_DIR / <한글 이름> / CHART_FILENAME`. 산출물 폴더 밖이다

    Returns:
        쓸 파일 경로. 폴더는 만들지 않는다
    """
    return CHARTS_DIR / track_of(TRACK_NAME).label / CHART_FILENAME


def build_chart_html(datasets: Sequence[Dataset], *, plotly_js: str, created_at: datetime) -> str:
    """측정 · 체결을 돌려 판단용 차트 HTML 을 만든다 — **약 45초**(손절 체결이 대부분).

    **산출물 폴더를 쓰지 않는다** — 측정 · 체결 함수를 부르기만 하고 결과는 메모리에서 옮긴다.

    Args:
        datasets: 검증 대상. **하나여야 한다** — 차트는 대상 하나를 그린다
        plotly_js: plotly.js 본문 (CLI 가 넘긴다)
        created_at: 만든 시각 (시간대가 있어야 한다). 차트 머리에 KST 로 찍는다

    Returns:
        완성된 HTML

    Raises:
        ValueError: 대상이 하나가 아니거나 만든 시각에 시간대가 없는 경우
    """
    if len(datasets) != 1:
        raise ValueError(f"판단용 차트는 대상 하나만 그립니다: {[dataset.label for dataset in datasets]}")
    if created_at.tzinfo is None:
        raise ValueError(f"만든 시각에 시간대가 없습니다: {created_at}")
    dataset = datasets[0]

    prices = load_dataset(dataset).frame
    onchain = load_onchain(dataset).frame
    close = prices.set_index(COL_DATE)[COL_CLOSE].astype(float)
    mvrv = onchain.set_index(COL_DATE)[COL_MVRV].astype(float)
    rank = trailing_rank(mvrv, years=SPLIT_RANK_YEARS, min_days=SPLIT_RANK_MIN_DAYS)
    halving_days = [halving.day for halving in HALVINGS]

    tables = display_tables(run_study(tuple(datasets)))
    trading = run_halving_cycle_trading(tuple(datasets))
    performance = trading.performance[trading.performance[DISPLAY_TICKER] == dataset.label]
    trades = trading.trades[trading.trades[DISPLAY_TICKER] == dataset.label]

    price_record = dataset_record(ticker=dataset.ticker, label=dataset.label, file=dataset.path.name, frame=prices)
    payload: dict[str, Any] = {
        "meta": {
            "label": dataset.label,
            "created_at": created_at.astimezone(KST).strftime("%Y-%m-%d %H:%M KST"),
            "sources": [
                {
                    "name": "가격",
                    "file": price_record[KEY_DATASET_FILE],
                    "period": price_record[KEY_DATASET_PERIOD],
                    "rows": price_record[KEY_DATASET_ROWS],
                },
                {
                    "name": "MVRV",
                    "file": dataset.mvrv_path.name,
                    "period": format_period(onchain[COL_DATE].iloc[0], onchain[COL_DATE].iloc[-1]),
                    "rows": len(onchain),
                },
            ],
        },
        # 데이터 끝 뒤의 반감기는 아직 오지 않은 것이라 세로선을 긋지 않는다 (`_cycle_segments` 와 같다)
        "halvings": [halving.label for halving in HALVINGS if halving.day <= close.index[-1]],
        "rank_years": SPLIT_RANK_YEARS,
        "rank_min_days": SPLIT_RANK_MIN_DAYS,
        "thresholds": {
            "mvrv_buy": list(SPLIT_BUY_BOOK_LEVELS),
            "mvrv_sell": list(SPLIT_SELL_BOOK_LEVELS),
            "rank_buy": [round(level * 100, PERCENT_DECIMALS) for level in SPLIT_BUY_RANK_LEVELS],
            "rank_sell": [round(level * 100, PERCENT_DECIMALS) for level in SPLIT_SELL_RANK_LEVELS],
        },
        "cycles": cycle_series(close, mvrv, rank, halving_days),
        "summary": cycle_summary(close, mvrv, halving_days, buy_level=max(SPLIT_BUY_BOOK_LEVELS)),
        "time": timeline_series(close, mvrv, rank, halving_days),
        "grid": {
            "entry_months": list(ENTRY_MONTHS),
            "exit_months": list(EXIT_MONTHS),
            "cells": grid_cells(
                performance, trades, tables[FIELD_GRID_BASELINE], entry_months=ENTRY_MONTHS, exit_months=EXIT_MONTHS
            ),
        },
        "stops": stop_rows(
            performance, trades, entry_months=ENTRY_MONTHS, exit_months=EXIT_MONTHS, stop_levels=STOP_LEVELS
        ),
        "split": split_view(tables[FIELD_SPLIT_FILLS], tables[FIELD_SPLIT_POSITIONS]),
    }

    return render_html(TEMPLATE_PATH.read_text(encoding="utf-8"), payload, plotly_js)
