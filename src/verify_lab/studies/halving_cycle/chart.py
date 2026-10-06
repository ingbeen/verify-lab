"""반감기_사이클 판단용 차트 — 시세와 달력 매달 분할 측정 표를 HTML 한 장의 차트 데이터로 옮긴다

**사고파는 기간(②)을 사람이 보고 고르게 하는 보기다** (설계 결정 ㊾ · ㊿ · 53 · 54 · 55). 매매 방식은 달력형 매달 분할이고(결정 51),
차트는 폭 하나(`CHART_SPLIT_NAME`)의 매수 · 매도 회차를 세 보기 — 반감기 기준 겹치기 · 바닥 기준 겹치기 · 전 기간
시간축 — 에 찍는다. **고르지 않고 판정하지 않는다.**

**회차 점 · 기간 띠 · 숫자표의 값은 산출물의 표시용 프레임을 옮기기만 한다** — `run_halving_cycle.py` 가 CSV 로 쓰는 바로
그 프레임이라 같은 시세면 차트 값이 CSV 와 같고, 회차 날짜의 정의(그 달의 말일)는 `split_rule` 하나가 갖는다. 시세를
그리는 보기의 배수 · 경과 개월 · 고점 · 바닥과, 점이 선 위에 앉을 자리(그 선의 기준 종가 대비 배수 · 기준일에서 센 개월)는
여기서 낸다.

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
from verify_lab.execution.constants import DISPLAY_RETURN, DISPLAY_TICKER
from verify_lab.report.constants import DATE_FORMAT, DISPLAY_EXCLUDED_REASON, PERCENT_DECIMALS
from verify_lab.report.run_summary import KEY_DATASET_FILE, KEY_DATASET_PERIOD, KEY_DATASET_ROWS, dataset_record
from verify_lab.studies.halving_cycle.constants import (
    CALENDAR_SPLIT_STEP_MONTHS,
    CALENDAR_SPLITS,
    DISPLAY_AVG_BUY_PRICE,
    DISPLAY_AVG_SELL_PRICE,
    DISPLAY_BUY_CALENDAR_COUNT,
    DISPLAY_BUY_TRANCHES,
    DISPLAY_CALENDAR_SPLIT,
    DISPLAY_HALVING,
    DISPLAY_SELL_CALENDAR_COUNT,
    DISPLAY_SELL_TRANCHES,
    DISPLAY_SPLIT_ANCHOR_HALVING,
    DISPLAY_SPLIT_DEADLINE,
    DISPLAY_SPLIT_FILL_CLOSE,
    DISPLAY_SPLIT_FILL_DATE,
    DISPLAY_SPLIT_SIDE,
    DISPLAY_SPLIT_TRANCHE,
    DISPLAY_WORST_VS_COST,
    FIELD_CALENDAR_SPLIT_FILLS,
    FIELD_CALENDAR_SPLIT_POSITIONS,
    HALVINGS,
    PEAK_WINDOW_MONTHS,
    SPLIT_SIDE_BUY,
    SPLIT_SIDE_SELL,
    TRACK_NAME,
    CalendarSplit,
    Dataset,
)
from verify_lab.studies.halving_cycle.runner import display_tables, load_dataset, run_study
from verify_lab.tracks import track_of

CHART_FILENAME: Final = "판단차트.html"
TEMPLATE_PATH: Final = Path(__file__).with_name("chart_template.html")

# 템플릿의 자리표시. **한 번씩만 있어야 한다** — `render_html` 이 센다
DATA_MARKER: Final = "__CHART_DATA__"
PLOTLY_MARKER: Final = "__PLOTLY_JS__"

# 반감기 뒤 경과 개월의 환산(`설계.md` §4.12). 격자 날짜와 이틀 안쪽 · 말일 회차와 최대 한 달 가까이 다르다
DAYS_PER_MONTH: Final = 30.4375

# 차트가 그리는 달력 분할의 폭 — 측정한 폭 목록에서 이름으로 고른다 (결정 53 · 54)
CHART_SPLIT_NAME: Final = "월말 분할"

# 바닥 기준 선이 바닥 몇 개월 앞에서 시작하나 (2026-10-01 사용자 답). 매수 기간이 바닥 앞뒤에 걸쳐 있어 앞부분이
# 있어야 매수가 바닥보다 일렀는지 늦었는지 보인다
BOTTOM_LEAD_MONTHS: Final = 12

# 차트 데이터의 자릿수. 그리는 데만 쓰는 값이라 산출물 반올림표에 없다
MONTHS_DECIMALS: Final = 3
MULTIPLE_DECIMALS: Final = 5

# 표시용 프레임에서 읽는 컬럼
_FILL_COLUMNS: Final = (
    DISPLAY_TICKER,
    DISPLAY_CALENDAR_SPLIT,
    DISPLAY_SPLIT_SIDE,
    DISPLAY_HALVING,
    DISPLAY_SPLIT_ANCHOR_HALVING,
    DISPLAY_SPLIT_TRANCHE,
    DISPLAY_SPLIT_DEADLINE,
    DISPLAY_SPLIT_FILL_DATE,
    DISPLAY_SPLIT_FILL_CLOSE,
)
_POSITION_COLUMNS: Final = (
    DISPLAY_TICKER,
    DISPLAY_CALENDAR_SPLIT,
    DISPLAY_HALVING,
    DISPLAY_BUY_TRANCHES,
    DISPLAY_SELL_TRANCHES,
    DISPLAY_AVG_BUY_PRICE,
    DISPLAY_AVG_SELL_PRICE,
    DISPLAY_RETURN,
    DISPLAY_WORST_VS_COST,
    DISPLAY_BUY_CALENDAR_COUNT,
    DISPLAY_SELL_CALENDAR_COUNT,
    DISPLAY_EXCLUDED_REASON,
)


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
    """날짜를 `YYYY-MM-DD` 로. 표시용 프레임은 `Timestamp`, 반감기 표지는 문자열로 들어온다"""
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
# 시세 — 반감기 기준 · 바닥 기준 · 시간축 · 사이클 요약
# ============================================================


def _months_after(day: pd.Timestamp, start: pd.Timestamp) -> float:
    return (day - start).days / DAYS_PER_MONTH


def _cycle_segments(
    close: pd.Series, halving_days: Sequence[pd.Timestamp]
) -> list[tuple[pd.Timestamp, pd.Series, bool]]:
    """반감기마다 (반감기일, 그날 ~ 다음 반감기 전날의 종가, 진행 중인가).

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


def _peak_and_bottom(segment: pd.Series, start: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    """사이클의 고점과 바닥 — 고점은 반감기 뒤 `PEAK_WINDOW_MONTHS` 개월 안의 최고 종가, 바닥은 고점 뒤 사이클 끝까지의
    최저 종가. **사이클 요약과 바닥 기준 선이 이 하나를 쓴다** — 두 보기의 바닥이 갈리면 선과 표가 다른 날을 가리킨다.
    """
    days = pd.DatetimeIndex(segment.index)
    window = segment[days < start + pd.DateOffset(months=PEAK_WINDOW_MONTHS)]
    peak = pd.Timestamp(window.idxmax())

    return peak, pd.Timestamp(segment[days >= peak].idxmin())


def cycle_series(close: pd.Series, halving_days: Sequence[pd.Timestamp]) -> list[dict[str, Any]]:
    """반감기 기준 사이클 겹치기 — 반감기마다 경과 개월 · 반감기일 종가 대비 배수.

    Args:
        close: 측정 계열 종가 (날짜 인덱스)
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
            }
        )

    return cycles


def cycle_summary(close: pd.Series, halving_days: Sequence[pd.Timestamp]) -> list[dict[str, Any]]:
    """사이클 요약 — 반감기일 종가 · 사이클 범위 · 고점 · 바닥.

    **고점 · 바닥은 지나고 나서야 정해지는 값이라 매매 신호가 아니다** — 차트를 읽는 기준점이다.

    Args:
        close: 측정 계열 종가 (날짜 인덱스)
        halving_days: 반감기일 (오름차순)

    Returns:
        사이클마다 한 사전. 진행 중인 사이클의 고점 · 바닥은 데이터가 늘면 바뀐다
    """
    rows: list[dict[str, Any]] = []
    for start, segment, ongoing in _cycle_segments(close, halving_days):
        days = pd.DatetimeIndex(segment.index)
        peak, bottom = _peak_and_bottom(segment, start)
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
                "bottom": bottom.strftime(DATE_FORMAT),
                "bottom_months": round(_months_after(bottom, start), MONTHS_DECIMALS),
                "bottom_close": _number(segment.loc[bottom], PRICE_DECIMALS),
            }
        )

    return rows


def timeline_series(close: pd.Series, halving_days: Sequence[pd.Timestamp]) -> dict[str, Any]:
    """전 기간 시간축 — 날마다 종가와 「어느 반감기 뒤 몇 개월」.

    Args:
        close: 측정 계열 종가 (날짜 인덱스)
        halving_days: 반감기일 (오름차순)

    Returns:
        날짜 · 종가 · 호버 글자
    """
    starts = [start for start, _, _ in _cycle_segments(close, halving_days)]
    days = pd.DatetimeIndex(close.index)
    positions = np.searchsorted(np.array(starts, dtype="datetime64[ns]"), days.to_numpy(), side="right") - 1
    anchors = [
        "첫 반감기 전"
        if position < 0
        else f"{starts[position].strftime(DATE_FORMAT)} 반감기 뒤 {_months_after(day, starts[position]):.1f}개월"
        for day, position in zip(days, positions, strict=True)
    ]

    return {
        "dates": [day.strftime(DATE_FORMAT) for day in days],
        "close": [_number(value, PRICE_DECIMALS) for value in close.to_numpy(dtype=float)],
        "anchor": anchors,
    }


def bottom_series(close: pd.Series, halving_days: Sequence[pd.Timestamp], *, lead_months: int) -> list[dict[str, Any]]:
    """바닥 기준 사이클 겹치기 — 바닥마다 한 선, 바닥 `lead_months` 개월 앞부터 다음 바닥 전날까지(마지막은 데이터 끝).

    가로축은 바닥에서 센 경과 개월(앞은 음수), 세로축은 바닥 종가 = 1배. 바닥의 정의는 사이클 요약과 같다.
    **진행 중인 사이클의 바닥은 잠정이다** — 데이터가 늘면 그 선의 정렬이 옮겨 간다.

    Args:
        close: 측정 계열 종가 (날짜 인덱스)
        halving_days: 반감기일 (오름차순)
        lead_months: 바닥 앞 개월. 그날이 데이터 앞이면 데이터 첫 날부터다

    Returns:
        바닥마다 한 사전 — 그 바닥이 속한 사이클(반감기 표지)과 잠정 여부를 함께 싣는다

    Raises:
        ValueError: 바닥 앞 개월이 음수인 경우
    """
    if lead_months < 0:
        raise ValueError(f"바닥 앞 개월은 0 이상이어야 합니다: {lead_months}")

    bottoms = [
        (start, _peak_and_bottom(segment, start)[1], ongoing)
        for start, segment, ongoing in _cycle_segments(close, halving_days)
    ]
    index = pd.DatetimeIndex(close.index)
    lines: list[dict[str, Any]] = []
    for position, (start, bottom, provisional) in enumerate(bottoms):
        begin = max(bottom - pd.DateOffset(months=lead_months), index[0])
        in_line = index >= begin
        if position + 1 < len(bottoms):
            in_line &= index < bottoms[position + 1][1]
        segment = close[in_line]
        base = float(close.loc[bottom])
        days = pd.DatetimeIndex(segment.index)
        label = bottom.strftime(DATE_FORMAT)
        lines.append(
            {
                "label": f"{label} 바닥" + (" (잠정)" if provisional else ""),
                "halving": start.strftime(DATE_FORMAT),
                "bottom": label,
                "provisional": provisional,
                "dates": [day.strftime(DATE_FORMAT) for day in days],
                "months": [round(_months_after(day, bottom), MONTHS_DECIMALS) for day in days],
                "multiple": [_number(value / base, MULTIPLE_DECIMALS) for value in segment.to_numpy(dtype=float)],
                "close": [_number(value, PRICE_DECIMALS) for value in segment.to_numpy(dtype=float)],
            }
        )

    return lines


# ============================================================
# 달력 분할 — 폭 · 기간 띠 · 회차 점 · 숫자표
# ============================================================


def chart_split(splits: Sequence[CalendarSplit], name: str) -> CalendarSplit:
    """폭 목록에서 이름으로 차트가 그릴 폭을 찾는다.

    Raises:
        ValueError: 그 이름의 폭이 없는 경우 — 측정 표에 없는 폭을 그리면 점이 하나도 없는 차트가 된다
    """
    for split in splits:
        if split.name == name:
            return split
    raise ValueError(f"차트가 그릴 달력 분할 폭 「{name}」이 측정 목록에 없습니다: {[split.name for split in splits]}")


def split_info(split: CalendarSplit, *, step_months: int) -> dict[str, Any]:
    """숫자표 제목 줄 · ① 의 띠에 쓰는 폭의 정보 — 쪽마다 회차 수와 매수(반감기 뒤) · 매도(다음 반감기 뒤)의 첫 · 마지막 회차 개월."""
    buy_first, sell_first = split.first_deadlines(step_months)

    return {
        "name": split.name,
        "buy_tranches": split.buy_tranches,
        "sell_tranches": split.sell_tranches,
        "buy": [buy_first, split.buy_last_deadline],
        "sell": [sell_first, split.sell_last_deadline],
    }


def window_bands(fills: pd.DataFrame, split_name: str, last_day: pd.Timestamp) -> list[dict[str, str]]:
    """전 기간 시간축의 기간 띠 — 그 폭의 포지션마다 매수 띠와 매도 띠, 회차 표의 첫 기한부터 마지막 기한까지.

    **날짜를 다시 세지 않고 회차 표의 기한을 옮긴다** — 회차 날짜의 정의(그 달의 말일 · 결정 54)는 `split_rule` 하나가
    갖는다. 체결 전 회차도 기한이 있어 띠에 들고, 기준 반감기가 없는 매도(다음 반감기가 목록에 없다)는 기한이 없어
    띠가 없다. 데이터 끝에서 자르며 데이터 뒤에서 시작하는 띠는 그리지 않는다(아직 오지 않은 기간이다).

    Args:
        fills: 달력분할회차 (표시용 프레임)
        split_name: 폭 이름
        last_day: 데이터 끝

    Returns:
        시작일 순의 띠 목록 — 쪽 · 포지션의 반감기 · 시작 · 끝

    Raises:
        ValueError: 컬럼이 없거나 종목이 여럿인 경우, 그 폭의 행이 없는 경우
    """
    _require_columns(fills, _FILL_COLUMNS, "달력분할회차")
    _require_single_ticker(fills, "달력분할회차")
    rows = fills[fills[DISPLAY_CALENDAR_SPLIT] == split_name]
    if rows.empty:
        raise ValueError(f"달력분할회차에 폭 「{split_name}」의 행이 없습니다")
    dated = rows[rows[DISPLAY_SPLIT_DEADLINE].notna()]
    cycles = dated[DISPLAY_HALVING].astype(str)
    sides = dated[DISPLAY_SPLIT_SIDE].astype(str)

    bands: list[dict[str, str]] = []
    for cycle, side in dict.fromkeys(zip(cycles, sides, strict=True)):
        deadlines = pd.DatetimeIndex(dated.loc[(cycles == cycle) & (sides == side), DISPLAY_SPLIT_DEADLINE])
        begin = pd.Timestamp(deadlines.min())
        if begin > last_day:
            continue
        end = min(pd.Timestamp(deadlines.max()), last_day)
        bands.append({"side": side, "cycle": cycle, "x0": begin.strftime(DATE_FORMAT), "x1": end.strftime(DATE_FORMAT)})

    return sorted(bands, key=lambda band: band["x0"])


def _base_close(close: pd.Series, day: pd.Timestamp, name: str) -> float:
    if day not in close.index:
        raise ValueError(f"{name}({day.strftime(DATE_FORMAT)})의 종가가 시세에 없습니다 — 점을 그 선 위에 앉힐 수 없습니다")
    return float(close.loc[day])


def split_points(
    fills: pd.DataFrame, split_name: str, close: pd.Series, bottoms: Mapping[str, pd.Timestamp]
) -> list[dict[str, Any]]:
    """회차 점 — 그 폭의 체결한 회차를 세 보기의 자리로 옮긴다.

    **점은 그 선 위에 앉는다.** 반감기 기준에서는 기준 반감기(매수는 그 반감기, 매도는 다음 반감기)에서 센 개월과 그날
    종가 대비 배수, 바닥 기준에서는 **포지션 사이클의 바닥**에서 센 개월과 그 바닥 종가 대비 배수다 — 한 포지션의 회차가
    바닥 선 하나에 모인다. 체결 전 회차는 점으로 싣지 않는다(아직 오지 않은 날에 산 것처럼 보인다).

    Args:
        fills: 달력분할회차 (표시용 프레임)
        split_name: 폭 이름
        close: 측정 계열 종가 (날짜 인덱스) — 선의 기준 종가를 찾는다
        bottoms: 사이클(반감기 표지) → 바닥일. 없는 사이클은 바닥 축 값을 비운다

    Returns:
        체결한 회차마다 한 사전 — 표의 순서 그대로

    Raises:
        ValueError: 컬럼이 없거나 종목이 여럿인 경우, 그 폭의 행이 없는 경우, 기준일의 종가가 시세에 없는 경우
    """
    _require_columns(fills, _FILL_COLUMNS, "달력분할회차")
    _require_single_ticker(fills, "달력분할회차")
    rows = fills[fills[DISPLAY_CALENDAR_SPLIT] == split_name]
    if rows.empty:
        raise ValueError(f"달력분할회차에 폭 「{split_name}」의 행이 없습니다")

    points: list[dict[str, Any]] = []
    for row in _records(rows):
        if _is_missing(row[DISPLAY_SPLIT_FILL_DATE]):
            continue
        day = pd.Timestamp(row[DISPLAY_SPLIT_FILL_DATE])
        price = float(row[DISPLAY_SPLIT_FILL_CLOSE])
        cycle = str(row[DISPLAY_HALVING])
        anchor = pd.Timestamp(str(row[DISPLAY_SPLIT_ANCHOR_HALVING]))
        bottom = bottoms.get(cycle)
        points.append(
            {
                "side": str(row[DISPLAY_SPLIT_SIDE]),
                "cycle": cycle,
                "anchor": anchor.strftime(DATE_FORMAT),
                "tranche": _count(row[DISPLAY_SPLIT_TRANCHE]),
                "date": day.strftime(DATE_FORMAT),
                "close": _number(price, PRICE_DECIMALS),
                "halving_months": round(_months_after(day, anchor), MONTHS_DECIMALS),
                "halving_multiple": _number(price / _base_close(close, anchor, "기준 반감기일"), MULTIPLE_DECIMALS),
                "bottom_months": None if bottom is None else round(_months_after(day, bottom), MONTHS_DECIMALS),
                "bottom_multiple": None
                if bottom is None
                else _number(price / _base_close(close, bottom, "바닥일"), MULTIPLE_DECIMALS),
            }
        )

    return points


def overlay_band(points: Sequence[Mapping[str, Any]], side: str, nominal: Sequence[float]) -> list[float]:
    """① 의 기간 띠 — 그 쪽의 명목 첫 · 마지막 회차 개월을 그 쪽 회차 점이 실제로 앉은 자리까지 넓힌다 (결정 59).

    회차는 그 달의 말일이고(결정 54) 가로축은 날 수를 한 달 평균 길이로 나눈 값이라, 명목 개월 그대로 그리면 회차 점이
    최대 한 달 가까이 띠 밖(오른쪽)에 찍혀 「기간 밖에서 샀다」로 읽힌다.

    Args:
        points: `split_points` 의 결과
        side: 매수 · 매도
        nominal: 그 쪽의 명목 첫 · 마지막 회차 개월 (`split_info`)

    Returns:
        [시작, 끝] 개월. 그 쪽 점이 없으면 명목 기간이다
    """
    months = [float(point["halving_months"]) for point in points if point["side"] == side]

    return [min([float(nominal[0]), *months]), max([float(nominal[1]), *months])]


def bottom_axis_range(lines: Sequence[Mapping[str, Any]], points: Sequence[Mapping[str, Any]]) -> list[float]:
    """② 의 가로축 범위 — 바닥 기준 선의 처음 · 끝 개월과 회차 점의 개월을 모두 덮는다 (결정 59).

    선은 다음 사이클의 바닥 전날에서 끊기는데 다음 사이클이 진행 중이면 그 바닥은 잠정이라, 앞 포지션의 매도 회차가 선
    끝 뒤에 올 수 있다 — 선 길이로만 범위를 잡으면 그 점이 화면 밖으로 잘린다.

    Args:
        lines: `bottom_series` 의 결과
        points: `split_points` 의 결과. 바닥 축 값이 빈 점은 건너뛴다

    Returns:
        [시작, 끝] 개월. 눈금 단위로 맞추는 것은 템플릿이 한다
    """
    months = [float(month) for line in lines for month in (line["months"][0], line["months"][-1])]
    months += [float(point["bottom_months"]) for point in points if point["bottom_months"] is not None]

    return [min(months), max(months)]


def split_table(fills: pd.DataFrame, positions: pd.DataFrame, split_name: str) -> list[dict[str, Any]]:
    """숫자표 — 그 폭의 사이클마다 한 행. 성적은 포지션 표 그대로, 산 기간 · 판 기간은 체결한 회차의 첫 날 · 마지막 날이다.

    Args:
        fills: 달력분할회차 (표시용 프레임)
        positions: 달력분할포지션 (표시용 프레임)
        split_name: 폭 이름

    Returns:
        포지션 표의 순서 그대로의 행. 끝나지 않은 포지션은 비운 값과 사유를 싣는다

    Raises:
        ValueError: 컬럼이 없거나 종목이 여럿인 경우, 그 폭의 포지션이 없는 경우
    """
    _require_columns(fills, _FILL_COLUMNS, "달력분할회차")
    _require_columns(positions, _POSITION_COLUMNS, "달력분할포지션")
    for frame, name in ((fills, "달력분할회차"), (positions, "달력분할포지션")):
        _require_single_ticker(frame, name)
    mine = positions[positions[DISPLAY_CALENDAR_SPLIT] == split_name]
    if mine.empty:
        raise ValueError(f"달력분할포지션에 폭 「{split_name}」의 행이 없습니다")
    filled = fills[(fills[DISPLAY_CALENDAR_SPLIT] == split_name) & fills[DISPLAY_SPLIT_FILL_DATE].notna()]

    def span(cycle: str, side: str) -> tuple[str | None, str | None]:
        days = filled.loc[
            (filled[DISPLAY_HALVING] == cycle) & (filled[DISPLAY_SPLIT_SIDE] == side), DISPLAY_SPLIT_FILL_DATE
        ]
        if days.empty:
            return None, None
        return _day(pd.Timestamp(days.min())), _day(pd.Timestamp(days.max()))

    rows: list[dict[str, Any]] = []
    for row in _records(mine):
        cycle = str(row[DISPLAY_HALVING])
        first_buy, last_buy = span(cycle, SPLIT_SIDE_BUY)
        first_sell, last_sell = span(cycle, SPLIT_SIDE_SELL)
        rows.append(
            {
                "halving": cycle,
                "buy_tranches": _count(row[DISPLAY_BUY_TRANCHES]),
                "sell_tranches": _count(row[DISPLAY_SELL_TRANCHES]),
                "buys": _count(row[DISPLAY_BUY_CALENDAR_COUNT]),
                "sells": _count(row[DISPLAY_SELL_CALENDAR_COUNT]),
                "first_buy": first_buy,
                "last_buy": last_buy,
                "first_sell": first_sell,
                "last_sell": last_sell,
                "avg_buy": _number(row[DISPLAY_AVG_BUY_PRICE], PRICE_DECIMALS),
                "avg_sell": _number(row[DISPLAY_AVG_SELL_PRICE], PRICE_DECIMALS),
                "return": _number(row[DISPLAY_RETURN], PERCENT_DECIMALS),
                "worst": _number(row[DISPLAY_WORST_VS_COST], PERCENT_DECIMALS),
                # 끝난 포지션의 사유는 빈 문자열이다 — 표에서 「끝남」으로 읽히게 비운다
                "reason": _text(row[DISPLAY_EXCLUDED_REASON]) or None,
            }
        )

    return rows


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
    """측정을 돌려 판단용 차트 HTML 을 만든다.

    **산출물 폴더를 쓰지 않는다** — 측정 함수를 부르기만 하고 결과는 메모리에서 옮긴다. 체결(성적표 · 거래내역)은 돌리지
    않는다 — 차트가 그 표를 읽지 않는다.

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
    close = prices.set_index(COL_DATE)[COL_CLOSE].astype(float)
    halving_days = [halving.day for halving in HALVINGS]

    tables = display_tables(run_study(tuple(datasets)))
    fills = tables[FIELD_CALENDAR_SPLIT_FILLS]
    positions = tables[FIELD_CALENDAR_SPLIT_POSITIONS]
    fills = fills[fills[DISPLAY_TICKER] == dataset.label]
    positions = positions[positions[DISPLAY_TICKER] == dataset.label]

    split = chart_split(CALENDAR_SPLITS, CHART_SPLIT_NAME)
    info = split_info(split, step_months=CALENDAR_SPLIT_STEP_MONTHS)
    summary = cycle_summary(close, halving_days)
    bottoms = {row["halving"]: pd.Timestamp(row["bottom"]) for row in summary}
    lines = bottom_series(close, halving_days, lead_months=BOTTOM_LEAD_MONTHS)
    points = split_points(fills, split.name, close, bottoms)

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
            ],
        },
        # 데이터 끝 뒤의 반감기는 아직 오지 않은 것이라 세로선을 긋지 않는다 (`_cycle_segments` 와 같다)
        "halvings": [halving.label for halving in HALVINGS if halving.day <= close.index[-1]],
        "split": info,
        # 점 · 띠의 `side` 값 — JS 가 글자를 다시 적지 않게 넘긴다
        "sides": {"buy": SPLIT_SIDE_BUY, "sell": SPLIT_SIDE_SELL},
        "cycles": cycle_series(close, halving_days),
        "bottoms": lines,
        "overlay_bands": {
            "buy": overlay_band(points, SPLIT_SIDE_BUY, info["buy"]),
            "sell": overlay_band(points, SPLIT_SIDE_SELL, info["sell"]),
        },
        "bottom_range": bottom_axis_range(lines, points),
        "summary": summary,
        "time": timeline_series(close, halving_days),
        "bands": window_bands(fills, split.name, close.index[-1]),
        "points": points,
        "table": split_table(fills, positions, split.name),
    }

    return render_html(TEMPLATE_PATH.read_text(encoding="utf-8"), payload, plotly_js)
