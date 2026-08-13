"""표시용 표 생성 — 번역과 렌더링

`measure` 가 낸 값을 사람이 읽는 형태로 바꾼다. **계산하지 않는다.** 집계와 검정은 전부
`measure` 의 일이며, 여기서 파생값을 만들기 시작하면 같은 수가 두 곳에서 나오게 된다.

하는 일은 셋이다.
- 비율(0.0625)을 백분율(6.25)로 바꾸고 반올림한다
- 영문 토큰을 한글 레이블과 구간 이름으로 바꾼다
- long-form 을 사람이 읽는 배치로 옮긴다 — 신호일 목록은 **신호일 한 줄**이 된다

**터미널과 CSV 는 같은 표를 쓴다.** 따로 가공하면 반올림 시점이 갈려 화면에서 본 숫자를
CSV 에서 찾지 못하고, 그러면 사용자가 직접 대조한다는 이 프로젝트의 전제가 무너진다.
"""

import logging
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_EXCLUDED_COUNT,
    COL_FORWARD_RETURN,
    COL_HORIZON,
    COL_SIGNAL_COUNT,
)
from verify_lab.measure.statistics import (
    COL_BASELINE_SAMPLE_COUNT,
    COL_MAX,
    COL_MEAN,
    COL_MEAN_EXCESS,
    COL_MEAN_P_VALUE,
    COL_MEAN_PERCENTILE,
    COL_MEDIAN,
    COL_MEDIAN_EXCESS,
    COL_MEDIAN_P_VALUE,
    COL_MEDIAN_PERCENTILE,
    COL_MIN,
    COL_NULL_MEAN_P05,
    COL_NULL_MEAN_P95,
    COL_OBSERVED_MEAN,
    COL_OBSERVED_MEDIAN,
    COL_SAMPLE_COUNT,
    COL_SIGNAL_SAMPLE_COUNT,
    COL_STD,
    COL_TEST_NOTE,
    COL_WIN_RATE,
    COL_WIN_RATE_EXCESS,
)
from verify_lab.report.constants import (
    BASIS_LABELS,
    BASIS_ORDER,
    COLUMN_GAP,
    DATE_FORMAT,
    DISPLAY_BASELINE,
    DISPLAY_BASELINE_SAMPLE,
    DISPLAY_BASIS,
    DISPLAY_DATE,
    DISPLAY_EXCLUDED,
    DISPLAY_HORIZON,
    DISPLAY_MAX,
    DISPLAY_MEAN,
    DISPLAY_MEAN_EXCESS,
    DISPLAY_MEAN_P_VALUE,
    DISPLAY_MEAN_PERCENTILE,
    DISPLAY_MEDIAN,
    DISPLAY_MEDIAN_EXCESS,
    DISPLAY_MEDIAN_P_VALUE,
    DISPLAY_MEDIAN_PERCENTILE,
    DISPLAY_MIN,
    DISPLAY_NULL_P05,
    DISPLAY_NULL_P95,
    DISPLAY_OBSERVED_MEAN,
    DISPLAY_OBSERVED_MEDIAN,
    DISPLAY_POPULATION,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_SIGNAL_SAMPLE,
    DISPLAY_STD,
    DISPLAY_TEST_NOTE,
    DISPLAY_WIN_RATE,
    DISPLAY_WIN_RATE_EXCESS,
    EMPTY_MARK,
    HORIZON_LABELS,
    PERCENT_DECIMALS,
    PROBABILITY_DECIMALS,
    RATE_TO_PERCENT,
)
from verify_lab.utils.formatting import Align, TableLogger, get_display_width


def build_signal_table(frame: pd.DataFrame, signal_details: pd.DataFrame | None = None) -> pd.DataFrame:
    """신호일 한 줄에 구간별 수익률을 펼친 표를 만든다.

    사용자가 차트나 검색으로 직접 대조하는 원자료다. long-form 은 한 신호일이 12행으로
    흩어져 있어 눈으로 대조할 수 없으므로 여기서 신호일 단위로 되돌린다.

    제외된 칸은 **비워 둔다.** 0 으로 채우면 "수익률 0%"로 읽힌다.

    Args:
        frame: `compute_forward_returns` 의 결과
        signal_details: 신호일에 붙일 검증별 컬럼 (순위·사건 번호 등). 날짜 컬럼이 있어야 하며
            날짜 바로 뒤에 배치된다. 이벤트 정의가 채우는 자리다

    Returns:
        신호일 한 줄짜리 표. 수익률은 백분율이며 컬럼 이름은 "기준 구간" 형식이다

    Raises:
        ValueError: 결과 프레임에 필요한 컬럼이 없거나, 부가 정보에 날짜 컬럼이 없는 경우
    """
    _require_columns(frame, [COL_DATE, COL_BASIS, COL_HORIZON, COL_FORWARD_RETURN], "결과")

    working = frame.copy()
    bases = working[COL_BASIS].drop_duplicates().tolist()
    horizons = sorted(working[COL_HORIZON].drop_duplicates().tolist())
    ordered_labels = [f"{_basis_label(basis)} {_horizon_label(horizon)}" for basis in bases for horizon in horizons]

    working["_label"] = [
        f"{_basis_label(basis)} {_horizon_label(horizon)}"
        for basis, horizon in zip(working[COL_BASIS], working[COL_HORIZON], strict=True)
    ]
    pivoted = (
        working.pivot(index=COL_DATE, columns="_label", values=COL_FORWARD_RETURN)
        .reindex(columns=ordered_labels)
        .reset_index()
    )

    detail_columns: list[str] = []
    if signal_details is not None:
        if COL_DATE not in signal_details.columns:
            raise ValueError(f"부가 정보에 날짜 컬럼이 없습니다: {COL_DATE}")
        detail_columns = [column for column in signal_details.columns if column != COL_DATE]
        pivoted = pivoted.merge(signal_details, on=COL_DATE, how="left")

    result = pivoted[[COL_DATE, *detail_columns, *ordered_labels]].rename(columns={COL_DATE: DISPLAY_DATE})
    result[DISPLAY_DATE] = pd.to_datetime(result[DISPLAY_DATE]).dt.strftime(DATE_FORMAT)
    for label in ordered_labels:
        result[label] = _to_percent(result[label])

    return result


def build_statistics_table(summary: pd.DataFrame) -> pd.DataFrame:
    """칸별 집계를 표시용으로 바꾼다.

    행 순서는 **구간 → 기준**이다. 같은 구간의 두 기준이 위아래로 붙어 있어야
    "둘의 차이 = 갭으로 새는 몫"이 눈에 보인다.

    Args:
        summary: `statistics.summarize` 의 결과

    Returns:
        한글 레이블과 백분율로 바뀐 집계표

    Raises:
        ValueError: 필요한 컬럼이 없는 경우
    """
    ordered = _sorted_cells(summary, "집계")

    return pd.DataFrame(
        {
            DISPLAY_HORIZON: [_horizon_label(value) for value in ordered[COL_HORIZON]],
            DISPLAY_BASIS: [_basis_label(value) for value in ordered[COL_BASIS]],
            DISPLAY_SIGNAL_COUNT: ordered[COL_SIGNAL_COUNT].to_numpy(),
            DISPLAY_EXCLUDED: ordered[COL_EXCLUDED_COUNT].to_numpy(),
            DISPLAY_SAMPLE_COUNT: ordered[COL_SAMPLE_COUNT].to_numpy(),
            DISPLAY_MEAN: _to_percent(ordered[COL_MEAN]).to_numpy(),
            DISPLAY_MEDIAN: _to_percent(ordered[COL_MEDIAN]).to_numpy(),
            DISPLAY_WIN_RATE: _to_percent(ordered[COL_WIN_RATE]).to_numpy(),
            DISPLAY_MAX: _to_percent(ordered[COL_MAX]).to_numpy(),
            DISPLAY_MIN: _to_percent(ordered[COL_MIN]).to_numpy(),
            DISPLAY_STD: _to_percent(ordered[COL_STD]).to_numpy(),
        }
    )


def build_excess_table(excess_by_baseline: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """베이스라인별 초과분을 한 표로 쌓는다 (CSV 용).

    어느 베이스라인 대비인지를 컬럼으로 남기고, **양쪽 표본 수를 함께 둔다.**
    표본 수가 크게 다르다는 사실 자체가 해석의 일부다.

    Args:
        excess_by_baseline: 베이스라인 이름 → `statistics.excess` 결과

    Returns:
        베이스라인 컬럼이 붙은 초과분표 (단위는 백분율 포인트)

    Raises:
        ValueError: 입력이 비었거나 필요한 컬럼이 없는 경우
    """
    if not excess_by_baseline:
        raise ValueError("초과분 표가 비어 있습니다")

    blocks: list[pd.DataFrame] = []
    for name, table in excess_by_baseline.items():
        ordered = _sorted_cells(table, f"초과분({name})")
        blocks.append(
            pd.DataFrame(
                {
                    DISPLAY_BASELINE: name,
                    DISPLAY_HORIZON: [_horizon_label(value) for value in ordered[COL_HORIZON]],
                    DISPLAY_BASIS: [_basis_label(value) for value in ordered[COL_BASIS]],
                    DISPLAY_SIGNAL_SAMPLE: ordered[COL_SIGNAL_SAMPLE_COUNT].to_numpy(),
                    DISPLAY_BASELINE_SAMPLE: ordered[COL_BASELINE_SAMPLE_COUNT].to_numpy(),
                    DISPLAY_MEAN_EXCESS: _to_percent(ordered[COL_MEAN_EXCESS]).to_numpy(),
                    DISPLAY_MEDIAN_EXCESS: _to_percent(ordered[COL_MEDIAN_EXCESS]).to_numpy(),
                    DISPLAY_WIN_RATE_EXCESS: _to_percent(ordered[COL_WIN_RATE_EXCESS]).to_numpy(),
                }
            )
        )

    return pd.concat(blocks, ignore_index=True)


def build_test_table(test_by_population: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """모집단별 검정 결과를 한 표로 쌓는다 (CSV 용).

    검정하지 않은 칸은 값이 비고 **사유가 남는다.**

    Args:
        test_by_population: 모집단 이름 → `statistics.permutation_test` 결과

    Returns:
        모집단 컬럼이 붙은 검정표

    Raises:
        ValueError: 입력이 비었거나 필요한 컬럼이 없는 경우
    """
    if not test_by_population:
        raise ValueError("검정 표가 비어 있습니다")

    blocks: list[pd.DataFrame] = []
    for name, table in test_by_population.items():
        ordered = _sorted_cells(table, f"검정({name})")
        blocks.append(
            pd.DataFrame(
                {
                    DISPLAY_POPULATION: name,
                    DISPLAY_HORIZON: [_horizon_label(value) for value in ordered[COL_HORIZON]],
                    DISPLAY_BASIS: [_basis_label(value) for value in ordered[COL_BASIS]],
                    DISPLAY_SAMPLE_COUNT: ordered[COL_SAMPLE_COUNT].to_numpy(),
                    DISPLAY_OBSERVED_MEAN: _to_percent(ordered[COL_OBSERVED_MEAN]).to_numpy(),
                    DISPLAY_OBSERVED_MEDIAN: _to_percent(ordered[COL_OBSERVED_MEDIAN]).to_numpy(),
                    DISPLAY_NULL_P05: _to_percent(ordered[COL_NULL_MEAN_P05]).to_numpy(),
                    DISPLAY_NULL_P95: _to_percent(ordered[COL_NULL_MEAN_P95]).to_numpy(),
                    DISPLAY_MEAN_PERCENTILE: ordered[COL_MEAN_PERCENTILE].round(PERCENT_DECIMALS).to_numpy(),
                    DISPLAY_MEAN_P_VALUE: ordered[COL_MEAN_P_VALUE].round(PROBABILITY_DECIMALS).to_numpy(),
                    DISPLAY_MEDIAN_PERCENTILE: ordered[COL_MEDIAN_PERCENTILE].round(PERCENT_DECIMALS).to_numpy(),
                    DISPLAY_MEDIAN_P_VALUE: ordered[COL_MEDIAN_P_VALUE].round(PROBABILITY_DECIMALS).to_numpy(),
                    DISPLAY_TEST_NOTE: ordered[COL_TEST_NOTE].to_numpy(),
                }
            )
        )

    return pd.concat(blocks, ignore_index=True)


def build_comparison_table(excess_by_baseline: Mapping[str, pd.DataFrame], test: pd.DataFrame) -> pd.DataFrame:
    """베이스라인을 **열로 펼친** 비교 표를 만든다 (터미널·마크다운용).

    베이스라인마다 행을 쌓으면 같은 구간의 값이 흩어져 한눈에 비교되지 않는다. 대신
    검정은 한 벌만 싣는다 — 터미널은 훑어보는 자리이고, 모집단별 검정 전체는 CSV 에 남는다.

    Args:
        excess_by_baseline: 베이스라인 이름 → `statistics.excess` 결과
        test: 대표 모집단의 `statistics.permutation_test` 결과

    Returns:
        구간 × 기준 한 줄에 베이스라인별 초과분과 검정 결과가 붙은 표

    Raises:
        ValueError: 입력이 비었거나 필요한 컬럼이 없는 경우
    """
    if not excess_by_baseline:
        raise ValueError("초과분 표가 비어 있습니다")

    ordered_test = _sorted_cells(test, "검정")
    result = pd.DataFrame(
        {
            DISPLAY_HORIZON: [_horizon_label(value) for value in ordered_test[COL_HORIZON]],
            DISPLAY_BASIS: [_basis_label(value) for value in ordered_test[COL_BASIS]],
            DISPLAY_SAMPLE_COUNT: ordered_test[COL_SAMPLE_COUNT].to_numpy(),
        }
    )

    for name, table in excess_by_baseline.items():
        ordered = _sorted_cells(table, f"초과분({name})")
        result[f"{name} {DISPLAY_MEAN_EXCESS}"] = _to_percent(ordered[COL_MEAN_EXCESS]).to_numpy()
        result[f"{name} {DISPLAY_MEDIAN_EXCESS}"] = _to_percent(ordered[COL_MEDIAN_EXCESS]).to_numpy()

    result[DISPLAY_MEAN_PERCENTILE] = ordered_test[COL_MEAN_PERCENTILE].round(PERCENT_DECIMALS).to_numpy()
    result[DISPLAY_MEAN_P_VALUE] = ordered_test[COL_MEAN_P_VALUE].round(PROBABILITY_DECIMALS).to_numpy()
    result[DISPLAY_TEST_NOTE] = ordered_test[COL_TEST_NOTE].to_numpy()

    return result


def print_dataframe(table: pd.DataFrame, logger: logging.Logger, title: str | None = None) -> None:
    """표를 터미널에 출력한다.

    컬럼 폭을 내용에서 계산한다. 표마다 폭을 손으로 적으면 데이터가 바뀔 때마다 어긋난다.
    숫자 컬럼은 오른쪽 정렬해 자릿수를 눈으로 맞춘다.

    **오른쪽 정렬 컬럼은 여백을 값에 직접 단다.** 정렬 여백이 값 앞쪽에만 붙어서,
    폭만 늘리면 다음 컬럼과 글자가 맞닿아 헤더가 "p값비고" 처럼 읽힌다.

    Args:
        table: 표시용 표 (`build_*` 결과)
        logger: 출력에 쓸 로거
        title: 표 제목

    Raises:
        ValueError: 표가 비어 있는 경우
    """
    if table.empty:
        raise ValueError("표가 비어 있습니다")

    columns: list[tuple[str, int, Align]] = []
    rendered: list[list[str]] = []

    for name in table.columns:
        align = Align.RIGHT if pd.api.types.is_numeric_dtype(table[name]) else Align.LEFT
        trailing = " " * COLUMN_GAP if align is Align.RIGHT else ""

        header = str(name) + trailing
        cells = [_cell_text(value) + trailing for value in table[name]]
        width = max(get_display_width(text) for text in [header, *cells])

        columns.append((header, width if align is Align.RIGHT else width + COLUMN_GAP, align))
        rendered.append(cells)

    rows = [list(row) for row in zip(*rendered, strict=True)]
    TableLogger(columns, logger).print_table(rows, title)


def to_markdown(table: pd.DataFrame) -> str:
    """표를 마크다운 표 문자열로 바꾼다.

    `pandas.to_markdown()` 은 `tabulate` 패키지를 요구하는데 이 프로젝트 의존성에 없다.
    표 하나를 그리려고 의존성을 늘리지 않는다.

    Args:
        table: 표시용 표

    Returns:
        마크다운 표 문자열 (헤더·구분선·데이터 행)

    Raises:
        ValueError: 표가 비어 있는 경우
    """
    if table.empty:
        raise ValueError("표가 비어 있습니다")

    headers = [str(name) for name in table.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend(
        "| " + " | ".join(_cell_text(value) for value in row) + " |" for row in table.itertuples(index=False, name=None)
    )

    return "\n".join(lines)


def _basis_label(basis: object) -> str:
    """수익률 기준점을 표시 이름으로 바꾼다.

    Args:
        basis: 기준점 값

    Returns:
        표시 이름 (모르는 값이면 원래 값)
    """
    return BASIS_LABELS.get(str(basis), str(basis))


def _horizon_label(horizon: object) -> str:
    """측정 구간을 표시 이름으로 바꾼다.

    Args:
        horizon: 구간 (거래일)

    Returns:
        표시 이름 (표에 없는 구간이면 거래일 수 그대로)
    """
    days = int(horizon)  # pyright: ignore[reportArgumentType]

    return HORIZON_LABELS.get(days, f"{days}일")


def _to_percent(values: pd.Series) -> pd.Series:
    """비율을 백분율로 바꾸고 반올림한다.

    Args:
        values: 비율 값 (0.03 = 3%)

    Returns:
        백분율 값
    """
    return (values * RATE_TO_PERCENT).round(PERCENT_DECIMALS)


def _cell_text(value: Any) -> str:
    """표 한 칸을 문자열로 바꾼다. 값이 없으면 표시 문자를 쓴다.

    Args:
        value: 셀 값

    Returns:
        표시 문자열
    """
    if value is None or value == "" or (isinstance(value, float) and pd.isna(value)):
        return EMPTY_MARK

    return str(value)


def _sorted_cells(table: pd.DataFrame, label: str) -> pd.DataFrame:
    """(기준, 구간) 칸을 구간 → 기준 순서로 정렬한다.

    Args:
        table: 칸 키를 가진 표
        label: 오류 메시지에 쓸 표 이름

    Returns:
        정렬된 표

    Raises:
        ValueError: 칸 키 컬럼이 없는 경우
    """
    _require_columns(table, [COL_BASIS, COL_HORIZON], label)

    ordered = table.copy()
    ordered["_basis_order"] = [BASIS_ORDER.get(str(value), len(BASIS_ORDER)) for value in ordered[COL_BASIS]]

    return ordered.sort_values([COL_HORIZON, "_basis_order"]).reset_index(drop=True)


def _require_columns(table: pd.DataFrame, columns: Sequence[str], label: str) -> None:
    """표에 필요한 컬럼이 있는지 확인한다.

    Args:
        table: 검사할 표
        columns: 필요한 컬럼 목록
        label: 오류 메시지에 쓸 표 이름

    Raises:
        ValueError: 컬럼이 없는 경우
    """
    missing_columns = set(columns) - set(table.columns)
    if missing_columns:
        raise ValueError(f"{label} 표에 필수 컬럼이 누락되었습니다: {sorted(missing_columns)}")
