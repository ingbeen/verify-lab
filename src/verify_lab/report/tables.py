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
from typing import Any, SupportsInt

import pandas as pd

from verify_lab.common_constants import COL_DATE, RATE_TO_PERCENT
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_EXCLUDED_COUNT,
    COL_FORWARD_RETURN,
    COL_HORIZON,
    COL_SIGNAL_COUNT,
)
from verify_lab.measure.screening import (
    COL_BASELINE_GAP,
    COL_BASELINE_HIT_RATE,
    COL_DIRECTION,
    COL_EXPECTED_VALUE,
    COL_HIT_RATE,
    COL_P_VALUE,
    COL_PERIOD_COUNT,
    COL_PERIOD_MIN_HIT_RATE,
    COL_SCREEN,
    COL_SUPPORT_COUNT,
    COL_SUPPORT_TOTAL,
    COL_UNMET_SUPPORT,
)
from verify_lab.measure.statistics import (
    COL_BASELINE_SAMPLE_COUNT,
    COL_DOWN_RATE_P_VALUE,
    COL_DOWN_RATE_PERCENTILE,
    COL_LOSS_RATE,
    COL_LOSS_RATE_EXCESS,
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
    COL_OBSERVED_DOWN_RATE,
    COL_OBSERVED_MEAN,
    COL_OBSERVED_MEDIAN,
    COL_OBSERVED_UP_RATE,
    COL_SAMPLE_COUNT,
    COL_SIGNAL_SAMPLE_COUNT,
    COL_STD,
    COL_TEST_NOTE,
    COL_UP_RATE_P_VALUE,
    COL_UP_RATE_PERCENTILE,
    COL_WIN_RATE,
    COL_WIN_RATE_EXCESS,
)
from verify_lab.report.constants import (
    BASIS_LABELS,
    BASIS_ORDER,
    COLUMN_GAP,
    DATE_FORMAT,
    DISPLAY_BASELINE,
    DISPLAY_BASELINE_GAP,
    DISPLAY_BASELINE_HIT_RATE,
    DISPLAY_BASELINE_SAMPLE,
    DISPLAY_DATE,
    DISPLAY_DIRECTION,
    DISPLAY_DOWN_RATE,
    DISPLAY_DOWN_RATE_DIFF,
    DISPLAY_DOWN_RATE_P_VALUE,
    DISPLAY_DOWN_RATE_PERCENTILE,
    DISPLAY_EXCLUDED,
    DISPLAY_EXPECTED_VALUE,
    DISPLAY_HIT_RATE,
    DISPLAY_HORIZON,
    DISPLAY_MAX,
    DISPLAY_MEAN,
    DISPLAY_MEAN_DIFF,
    DISPLAY_MEAN_P_VALUE,
    DISPLAY_MEAN_PERCENTILE,
    DISPLAY_MEDIAN,
    DISPLAY_MEDIAN_DIFF,
    DISPLAY_MEDIAN_P_VALUE,
    DISPLAY_MEDIAN_PERCENTILE,
    DISPLAY_MIN,
    DISPLAY_NULL_P05,
    DISPLAY_NULL_P95,
    DISPLAY_OBSERVED_DOWN_RATE,
    DISPLAY_OBSERVED_MEAN,
    DISPLAY_OBSERVED_MEDIAN,
    DISPLAY_OBSERVED_UP_RATE,
    DISPLAY_P_VALUE,
    DISPLAY_PERIOD_COUNT,
    DISPLAY_PERIOD_MIN_HIT_RATE,
    DISPLAY_POPULATION,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_SCREEN,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_SIGNAL_SAMPLE,
    DISPLAY_STD,
    DISPLAY_SUPPORT,
    DISPLAY_TEST_NOTE,
    DISPLAY_UNMET_SUPPORT,
    DISPLAY_UP_RATE,
    DISPLAY_UP_RATE_DIFF,
    DISPLAY_UP_RATE_P_VALUE,
    DISPLAY_UP_RATE_PERCENTILE,
    EMPTY_MARK,
    HORIZON_LABELS,
    PERCENT_DECIMALS,
    PROBABILITY_DECIMALS,
    SUPPORT_SEPARATOR,
)
from verify_lab.utils.formatting import Align, TableLogger, get_display_width


def build_signal_table(frame: pd.DataFrame, signal_details: pd.DataFrame | None = None) -> pd.DataFrame:
    """신호일 한 줄에 구간별 수익률을 펼친 표를 만든다.

    사용자가 차트나 검색으로 직접 대조하는 원자료다. long-form 은 한 신호일이 칸 수만큼 여러 행으로
    흩어져 있어 눈으로 대조할 수 없으므로 여기서 신호일 단위로 되돌린다.

    제외된 칸은 **비워 둔다.** 0 으로 채우면 "수익률 0%"로 읽힌다.

    **컬럼은 프레임에 실제로 있는 (기준, 구간) 조합에서만 만든다.** 기준마다 측정 구간이
    다르므로(익일 시가는 1일만) 데카르트 곱으로 펼치면 영영 채워지지 않는 칸이 생기고,
    그 빈칸은 제외된 칸과 구분되지 않는다.

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
    horizons_by_basis = {
        basis: sorted(working[working[COL_BASIS] == basis][COL_HORIZON].drop_duplicates().tolist()) for basis in bases
    }
    ordered_labels = [
        f"{_basis_label(basis)} {_horizon_label(horizon)}" for basis in bases for horizon in horizons_by_basis[basis]
    ]

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

    행 순서는 **구간 오름차순**이다.

    **오른 비율과 내린 비율을 그대로 나란히 둔다.** 어느 쪽이 "이긴 것"인지 이 계층이 정하지
    않는다 — 오른 비율이 기준선보다 낮은 것은 탈락이 아니라 아래로 거는 신호이기 때문이다
    (루트 `CLAUDE.md` 측정의 원칙 11). 둘은 여집합이 아니라 각각 사실이다.

    Args:
        summary: `statistics.summarize` 의 결과. 기준 하나만 담겨 있어야 한다

    Returns:
        한글 레이블과 백분율로 바뀐 집계표

    Raises:
        ValueError: 필요한 컬럼이 없거나 기준이 둘 이상인 경우
    """
    ordered = _sorted_single_basis_cells(summary, "집계")

    return pd.DataFrame(
        {
            DISPLAY_HORIZON: [_horizon_label(value) for value in ordered[COL_HORIZON]],
            DISPLAY_SIGNAL_COUNT: ordered[COL_SIGNAL_COUNT].to_numpy(),
            DISPLAY_EXCLUDED: ordered[COL_EXCLUDED_COUNT].to_numpy(),
            DISPLAY_SAMPLE_COUNT: ordered[COL_SAMPLE_COUNT].to_numpy(),
            DISPLAY_MEAN: _to_percent(ordered[COL_MEAN]).to_numpy(),
            DISPLAY_MEDIAN: _to_percent(ordered[COL_MEDIAN]).to_numpy(),
            DISPLAY_UP_RATE: _to_percent(ordered[COL_WIN_RATE]).to_numpy(),
            DISPLAY_DOWN_RATE: _to_percent(ordered[COL_LOSS_RATE]).to_numpy(),
            DISPLAY_MAX: _to_percent(ordered[COL_MAX]).to_numpy(),
            DISPLAY_MIN: _to_percent(ordered[COL_MIN]).to_numpy(),
            DISPLAY_STD: _to_percent(ordered[COL_STD]).to_numpy(),
        }
    )


def build_excess_table(excess_by_baseline: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """베이스라인별 **기준선 대비 차이**를 한 표로 쌓는다 (CSV 용).

    어느 베이스라인 대비인지를 컬럼으로 남기고, **양쪽 표본 수를 함께 둔다.**
    표본 수가 크게 다르다는 사실 자체가 해석의 일부다.

    집계표와 같은 이유로 **두 방향 비율의 차이를 그대로 나란히 둔다** — 어느 쪽이 유리한지는
    이 계층이 판단하지 않는다.

    Args:
        excess_by_baseline: 베이스라인 이름 → `statistics.excess` 결과

    Returns:
        베이스라인 컬럼이 붙은 차이표 (단위는 백분율 포인트)

    Raises:
        ValueError: 입력이 비었거나 필요한 컬럼이 없거나 기준이 둘 이상인 경우
    """
    if not excess_by_baseline:
        raise ValueError("기준선 대비 차이 표가 비어 있습니다")

    blocks: list[pd.DataFrame] = []
    for name, table in excess_by_baseline.items():
        label = f"차이({name})"
        ordered = _sorted_single_basis_cells(table, label)
        blocks.append(
            pd.DataFrame(
                {
                    DISPLAY_BASELINE: name,
                    DISPLAY_HORIZON: [_horizon_label(value) for value in ordered[COL_HORIZON]],
                    DISPLAY_SIGNAL_SAMPLE: ordered[COL_SIGNAL_SAMPLE_COUNT].to_numpy(),
                    DISPLAY_BASELINE_SAMPLE: ordered[COL_BASELINE_SAMPLE_COUNT].to_numpy(),
                    DISPLAY_MEAN_DIFF: _to_percent(ordered[COL_MEAN_EXCESS]).to_numpy(),
                    DISPLAY_MEDIAN_DIFF: _to_percent(ordered[COL_MEDIAN_EXCESS]).to_numpy(),
                    DISPLAY_UP_RATE_DIFF: _to_percent(ordered[COL_WIN_RATE_EXCESS]).to_numpy(),
                    DISPLAY_DOWN_RATE_DIFF: _to_percent(ordered[COL_LOSS_RATE_EXCESS]).to_numpy(),
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
        ordered = _sorted_single_basis_cells(table, f"검정({name})")
        blocks.append(
            pd.DataFrame(
                {
                    DISPLAY_POPULATION: name,
                    DISPLAY_HORIZON: [_horizon_label(value) for value in ordered[COL_HORIZON]],
                    DISPLAY_SAMPLE_COUNT: ordered[COL_SAMPLE_COUNT].to_numpy(),
                    DISPLAY_OBSERVED_MEAN: _to_percent(ordered[COL_OBSERVED_MEAN]).to_numpy(),
                    DISPLAY_OBSERVED_MEDIAN: _to_percent(ordered[COL_OBSERVED_MEDIAN]).to_numpy(),
                    DISPLAY_NULL_P05: _to_percent(ordered[COL_NULL_MEAN_P05]).to_numpy(),
                    DISPLAY_NULL_P95: _to_percent(ordered[COL_NULL_MEAN_P95]).to_numpy(),
                    DISPLAY_MEAN_PERCENTILE: ordered[COL_MEAN_PERCENTILE].round(PERCENT_DECIMALS).to_numpy(),
                    DISPLAY_MEAN_P_VALUE: ordered[COL_MEAN_P_VALUE].round(PROBABILITY_DECIMALS).to_numpy(),
                    DISPLAY_MEDIAN_PERCENTILE: ordered[COL_MEDIAN_PERCENTILE].round(PERCENT_DECIMALS).to_numpy(),
                    DISPLAY_MEDIAN_P_VALUE: ordered[COL_MEDIAN_P_VALUE].round(PROBABILITY_DECIMALS).to_numpy(),
                    DISPLAY_OBSERVED_UP_RATE: _to_percent(ordered[COL_OBSERVED_UP_RATE]).to_numpy(),
                    DISPLAY_UP_RATE_PERCENTILE: ordered[COL_UP_RATE_PERCENTILE].round(PERCENT_DECIMALS).to_numpy(),
                    DISPLAY_UP_RATE_P_VALUE: ordered[COL_UP_RATE_P_VALUE].round(PROBABILITY_DECIMALS).to_numpy(),
                    DISPLAY_OBSERVED_DOWN_RATE: _to_percent(ordered[COL_OBSERVED_DOWN_RATE]).to_numpy(),
                    DISPLAY_DOWN_RATE_PERCENTILE: ordered[COL_DOWN_RATE_PERCENTILE].round(PERCENT_DECIMALS).to_numpy(),
                    DISPLAY_DOWN_RATE_P_VALUE: ordered[COL_DOWN_RATE_P_VALUE].round(PROBABILITY_DECIMALS).to_numpy(),
                    DISPLAY_TEST_NOTE: ordered[COL_TEST_NOTE].to_numpy(),
                }
            )
        )

    return pd.concat(blocks, ignore_index=True)


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


def _basis_label(basis: object) -> str:
    """수익률 기준점을 표시 이름으로 바꾼다.

    Args:
        basis: 기준점 값

    Returns:
        표시 이름 (모르는 값이면 원래 값)
    """
    return BASIS_LABELS.get(str(basis), str(basis))


def _horizon_label(horizon: SupportsInt) -> str:
    """측정 구간을 표시 이름으로 바꾼다.

    구간은 정수로 들어온다. pandas 컬럼을 순회하면 numpy 정수가 오므로 `int` 가 아니라
    `SupportsInt` 로 받는다 — 둘 다 정수로 바꿀 수 있다는 사실만 요구하면 충분하다.

    Args:
        horizon: 구간 (거래일)

    Returns:
        표시 이름 (표에 없는 구간이면 거래일 수 그대로)
    """
    days = int(horizon)

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

    **정수에는 천 단위 구분자를 붙인다.** 신호 수·행 수처럼 자릿수를 눈으로 세는 값이라
    구분자가 없으면 자리를 잘못 읽는다. 실수는 이미 반올림된 상태로 들어오므로 건드리지 않는다.

    Args:
        value: 셀 값

    Returns:
        표시 문자열
    """
    if value is None or value == "" or (isinstance(value, float) and pd.isna(value)):
        return EMPTY_MARK

    if pd.api.types.is_integer(value):
        return f"{value:,}"

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


def _sorted_single_basis_cells(table: pd.DataFrame, label: str) -> pd.DataFrame:
    """한 기준짜리 표를 구간 순서로 정렬한다.

    집계·초과분·검정 표는 `기준` 컬럼을 내지 않으므로(스펙 §7 결정 ㉔) **두 기준이
    섞여 들어오면 같은 구간이 두 줄로 나오면서 어느 줄이 무엇인지 알 수 없게 된다.**
    값이 그럴듯해 보여 눈으로 발견되지 않으므로 여기서 막는다.

    Args:
        table: 칸 키를 가진 표
        label: 오류 메시지에 쓸 표 이름

    Returns:
        구간 오름차순으로 정렬된 표

    Raises:
        ValueError: 칸 키 컬럼이 없거나 기준이 둘 이상인 경우
    """
    ordered = _sorted_cells(table, label)

    bases = ordered[COL_BASIS].drop_duplicates().tolist()
    if len(bases) > 1:
        raise ValueError(f"{label} 표는 기준 하나만 받습니다 (받은 기준: {[_basis_label(basis) for basis in bases]})")

    return ordered


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


def to_display_columns(
    table: pd.DataFrame,
    labels: Mapping[str, str],
    *,
    percent_columns: Sequence[str] = (),
    probability_columns: Sequence[str] = (),
) -> pd.DataFrame:
    """저장 직전에 컬럼 헤더를 한글로 바꾸고 단위를 맞춘다.

    **사전에 없는 컬럼이 하나라도 있으면 예외를 던진다.** 이것이 이 함수의 존재 이유다 —
    컬럼을 새로 추가하고 한글 이름을 만들지 않으면 영문 토큰이 그대로 사용자에게 나가는데,
    조용히 지나가면 발견되지 않는다 (`src/verify_lab/CLAUDE.md` 「내부/출력 분리」).

    **단위 변환을 함께 하는 이유**: 헤더를 `평균(%)` 로 바꾸면서 값이 비율(0.003)이면
    헤더가 거짓말이 된다. 이름과 단위는 한 자리에서 같이 정해야 어긋나지 않는다.

    **사전은 호출자가 준다.** 이 계층은 어떤 검증이 자기를 쓰는지 몰라야 하므로
    검증별 컬럼 이름을 알 수 없다.

    Args:
        table: 저장할 표 (영문 `COL_*` 헤더)
        labels: `COL_* → 한글 레이블` 사전. 표의 모든 컬럼을 덮어야 한다
        percent_columns: 비율(0~1)로 들어와 백분율로 내보낼 컬럼
        probability_columns: 확률로 들어와 자릿수만 맞출 컬럼

    Returns:
        헤더가 한글이고 단위가 맞춰진 새 DataFrame. 컬럼 순서는 그대로다

    Raises:
        ValueError: 표가 비어 있거나, 사전이 덮지 못한 컬럼이 있는 경우,
            변환 대상으로 지목한 컬럼이 표에 없는 경우
    """
    if table.empty:
        raise ValueError("표가 비어 있습니다")

    missing = [column for column in table.columns if column not in labels]
    if missing:
        raise ValueError(f"한글 이름이 없는 컬럼이 있습니다: {missing}")

    unknown = [column for column in (*percent_columns, *probability_columns) if column not in table.columns]
    if unknown:
        raise ValueError(f"변환 대상 컬럼이 표에 없습니다: {unknown}")

    converted = table.copy()
    for column in percent_columns:
        converted[column] = (converted[column] * RATE_TO_PERCENT).round(PERCENT_DECIMALS)
    for column in probability_columns:
        converted[column] = converted[column].round(PROBABILITY_DECIMALS)

    return converted.rename(columns=dict(labels))


def build_candidates_table(candidates: pd.DataFrame, *, axis_column: str, axis_label: str) -> pd.DataFrame:
    """후보 판정 결과를 표시용으로 바꾼다.

    비율은 백분율로, 우연확률은 확률 자릿수로 반올림한다. 시기를 쪼갤 수 없었던 칸은
    「가장 약한 시기」가 비어 있는데, **0 으로 채우지 않는다** — 0% 로 읽히기 때문이다.

    **등급은 「충족/물음」 한 칸으로 합치되 분모를 떼지 않는다.** 시기를 못 잰 칸은 `2/2` 가
    되는데 이는 `3/3` 과 같은 뜻이 아니며, 분모를 지우면 표본이 작은 칸이 만점처럼 보인다.

    Args:
        candidates: `screening.screen_candidates` 의 결과
        axis_column: 축 컬럼 이름
        axis_label: 축의 표시 이름

    Returns:
        한글 레이블과 백분율로 바뀐 판정표

    Raises:
        ValueError: 축 컬럼이 없는 경우
    """
    if axis_column not in candidates.columns:
        raise ValueError(f"판정표에 축 컬럼이 없습니다: {axis_column}")

    support = [
        f"{int(count)}{SUPPORT_SEPARATOR}{int(total)}"
        for count, total in zip(candidates[COL_SUPPORT_COUNT], candidates[COL_SUPPORT_TOTAL], strict=True)
    ]

    return pd.DataFrame(
        {
            axis_label: candidates[axis_column].to_numpy(),
            DISPLAY_SAMPLE_COUNT: candidates[COL_SAMPLE_COUNT].to_numpy(),
            DISPLAY_DIRECTION: candidates[COL_DIRECTION].to_numpy(),
            DISPLAY_HIT_RATE: _to_percent(candidates[COL_HIT_RATE]).to_numpy(),
            DISPLAY_EXPECTED_VALUE: _to_percent(candidates[COL_EXPECTED_VALUE]).to_numpy(),
            DISPLAY_BASELINE_HIT_RATE: _to_percent(candidates[COL_BASELINE_HIT_RATE]).to_numpy(),
            DISPLAY_BASELINE_GAP: _to_percent(candidates[COL_BASELINE_GAP]).to_numpy(),
            DISPLAY_P_VALUE: candidates[COL_P_VALUE].round(PROBABILITY_DECIMALS).to_numpy(),
            DISPLAY_PERIOD_COUNT: candidates[COL_PERIOD_COUNT].to_numpy(),
            DISPLAY_PERIOD_MIN_HIT_RATE: _to_percent(candidates[COL_PERIOD_MIN_HIT_RATE]).to_numpy(),
            DISPLAY_SCREEN: candidates[COL_SCREEN].to_numpy(),
            DISPLAY_SUPPORT: support,
            DISPLAY_UNMET_SUPPORT: candidates[COL_UNMET_SUPPORT].to_numpy(),
        }
    )
