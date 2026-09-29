"""반감기_사이클 측정 조립 — 반감기 경과 격자 48칸을 기준선과 함께 낸다

**계산하지 않는다.** 달력은 `halving_calendar`, 종가 대체는 `price_series`, 통계는 `measure/statistics`,
두 소스 대조는 `data/crosscheck` 가 소유하고 여기서는 조립만 한다.

**칸은 (진입 개월 × 보유 개월)이다.** 진입 개월마다 돌며 보유 개월을 구간 축에 둬서
`summarize` · `excess` · `permutation_test` 를 그대로 쓴다 — 통계량 정의를 여기서 다시 구현하면 두 곳이
조용히 갈라진다(절대 원칙 5).

**기준선은 「첫 반감기부터 매일 진입 × 같은 보유」다.** 청산 규칙이 신호와 같아 보유 길이가 어긋나지 않는다.
**판정에 쓰지 않는다** (루트 `CLAUDE.md` 「기준선을 넘지 못하는 것은 탈락 사유가 아닙니다」).

**값은 1배 롱 기준 그대로다.** `방향` 은 식별 라벨이고 부호를 뒤집지 않는다 — 뒤집으면 `기준선 오른 비율` 이
실제로는 내린 비율을 가리켜 이름이 거짓이 된다.
"""

from dataclasses import dataclass
from typing import Any

import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.data.crosscheck import (
    COL_DIFF_RATE,
    COL_PRIMARY,
    COL_SECONDARY,
    CrosscheckResult,
    crosscheck_closes,
)
from verify_lab.data.crypto_common import load_crypto_market_csv
from verify_lab.data.loader import load_series_csv
from verify_lab.execution.run_summary import KEY_DATASETS, KEY_ROW_COUNTS
from verify_lab.execution.trade_fill import resolve_positions
from verify_lab.measure.constants import (
    COL_ENTRY_CLOSE,
    COL_EXCLUDED_REASON,
    COL_EXIT_CLOSE,
    COL_EXIT_DATE,
    COL_FORWARD_RETURN,
    COL_HOLD_DAYS,
    COL_HORIZON,
    COL_JUDGEABLE,
    COL_MEAN_RATE_CONFLICT,
    REASON_NONE,
)
from verify_lab.measure.screening import COL_DIRECTION, DIRECTION_DOWN, DIRECTION_UP
from verify_lab.measure.statistics import (
    COL_BASIS,
    COL_DOWN_RATE_P_VALUE,
    COL_LOSS_RATE_EXCESS,
    COL_MEAN_EXCESS,
    COL_MEAN_P_VALUE,
    COL_MEDIAN_EXCESS,
    COL_MEDIAN_P_VALUE,
    COL_SAMPLE_COUNT,
    COL_SIGNAL_SAMPLE_COUNT,
    COL_TEST_NOTE,
    COL_UP_RATE_P_VALUE,
    COL_WIN_RATE_EXCESS,
    DEFAULT_RANDOM_SEED,
    DEFAULT_REPEAT_COUNT,
    SUMMARY_COLUMNS,
    excess,
    judgeable,
    max_non_overlapping,
    mean_rate_conflict,
    permutation_test,
    summarize,
    yes_no,
)
from verify_lab.report.run_summary import KEY_TRACK, dataset_record, format_period
from verify_lab.report.tables import to_display_columns
from verify_lab.studies.halving_cycle.constants import (
    BASELINE_SUFFIX,
    BET_DOWN,
    COL_BASELINE_NON_OVERLAPPING,
    COL_ENTRY_DATE,
    COL_ENTRY_MONTHS,
    COL_HALVING,
    COL_HOLD_MONTHS,
    COL_NON_OVERLAPPING,
    COL_TICKER,
    COL_ZERO_VOLUME,
    COLUMN_LABELS,
    DATASETS,
    ENTRY_MONTHS,
    FIELD_CALENDAR_YEARS,
    FIELD_CROSSCHECK,
    FIELD_ENTRIES,
    FIELD_EXCESS,
    FIELD_REPLACED,
    FIELD_STATISTICS,
    FIELD_TEST,
    HALVINGS,
    HOLD_MONTHS,
    KEY_BLOCK_TIME,
    KEY_DATE,
    KEY_ENTRY_MONTHS,
    KEY_EXCLUDED_COUNT,
    KEY_HALVINGS,
    KEY_HEIGHT,
    KEY_HOLD_MONTHS,
    KEY_SIGNAL_COUNT,
    OUTPUT_FILES,
    PERCENT_COLUMNS,
    PROBABILITY_COLUMNS,
    TRACK_NAME,
    Dataset,
)
from verify_lab.studies.halving_cycle.halving_calendar import (
    baseline_entries,
    calendar_returns,
    calendar_year_returns,
    exit_schedule,
    halving_entries,
)
from verify_lab.studies.halving_cycle.price_series import replace_zero_volume_closes
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# `summary.json` 의 측정 칸 — 무엇을 어떤 규칙으로 쟀나
KEY_PERMUTATION_REPEATS = "permutation_repeats"
KEY_PERMUTATION_SEED = "permutation_seed"
KEY_BASELINE_START = "baseline_start"
KEY_REFERENCE = "reference"
KEY_FILE = "file"
KEY_PERIOD = "period"
KEY_ROWS = "rows"
KEY_REPLACED_COUNT = "replaced_count"
KEY_CROSSCHECK = "crosscheck"
KEY_TOLERANCE = "tolerance"
KEY_OVERLAP_DAYS = "overlap_days"
KEY_OVER_TOLERANCE_DAYS = "over_tolerance_days"
KEY_PRIMARY_ONLY_DAYS = "primary_only_days"
KEY_SECONDARY_ONLY_DAYS = "secondary_only_days"
KEY_ZERO_VOLUME_DAYS = "zero_volume_days"

# 진입내역의 컬럼 — 측정 long-form 에서 사용자가 대조할 값만 남긴다 (측정의 원칙 8). 종목은 조립 때 앞에 붙는다
_ENTRY_COLUMNS = [
    COL_HALVING,
    COL_ENTRY_MONTHS,
    COL_HOLD_MONTHS,
    COL_DATE,
    COL_ENTRY_CLOSE,
    COL_EXIT_DATE,
    COL_EXIT_CLOSE,
    COL_HOLD_DAYS,
    COL_FORWARD_RETURN,
    COL_EXCLUDED_REASON,
]

# 집계 값 — 기준과 구간 축을 뺀 `summarize` 결과 전부. 신호 쪽은 그대로, 기준선 쪽은 접미사를 붙여 싣는다
_SUMMARY_VALUES = [column for column in SUMMARY_COLUMNS if column not in (COL_BASIS, COL_HORIZON)]

# excess 표의 값 — 신호 표본 · 기준선 집계 · 기준선 비중첩 · 기준선 대비 차이. **기준선 표본은 한 번만 싣는다** —
# `excess` 가 내는 기준선 표본 수는 기준선 집계의 표본과 같은 값이라 두 열이 되면 어느 쪽이 맞는지 매번 견줘야 한다
_EXCESS_VALUES = [
    COL_SIGNAL_SAMPLE_COUNT,
    *(f"{column}{BASELINE_SUFFIX}" for column in _SUMMARY_VALUES),
    COL_BASELINE_NON_OVERLAPPING,
    COL_MEAN_EXCESS,
    COL_MEDIAN_EXCESS,
    COL_WIN_RATE_EXCESS,
    COL_LOSS_RATE_EXCESS,
]

# 무작위 뽑기 대조에서 표에 싣는 값. **관측값 · 백분위는 싣지 않는다** — 관측값은 `통계.csv` 의 평균 · 중앙값 ·
# 두 비율과 같은 값이고, 백분위는 검정한 칸에만 채워지는데 칸마다 표본이 하한에 못 미쳐 지금은 전부 빈다.
# 판단 재료는 우연확률 넷과 비고다
_TEST_VALUES = [
    COL_SAMPLE_COUNT,
    COL_MEAN_P_VALUE,
    COL_MEDIAN_P_VALUE,
    COL_UP_RATE_P_VALUE,
    COL_DOWN_RATE_P_VALUE,
    COL_TEST_NOTE,
]


@dataclass(frozen=True)
class LoadedDataset:
    """대상 하나를 읽은 결과 — **측정과 체결이 같은 것을 쓴다**

    Attributes:
        frame: 측정이 쓰는 시세. 거래량 0 인 날의 종가만 대조 계열 값이다
        reference: 대조 계열 (Coin Metrics 기준가)
        replaced: 종가를 바꾼 날 목록
        crosscheck: **바꾸기 전** 원시 종가로 잰 두 소스 대조
    """

    frame: pd.DataFrame
    reference: pd.DataFrame
    replaced: pd.DataFrame
    crosscheck: CrosscheckResult


@dataclass(frozen=True)
class StudyOutputs:
    """측정 산출물

    Attributes:
        statistics: (진입 × 보유) 칸마다 한 행 — 신호 집계 · 평균-비율 어긋남 · 판정가능 · 비중첩
        excess: 칸마다 한 행 — 기준선 집계 · 기준선 대비 차이 · 기준선 비중첩
        test: 칸마다 한 행 — 무작위 뽑기 대조
        entries: 진입 × 보유 long-form. **청산이 오지 않은 행도 사유와 함께 남는다**
        calendar_years: 달력 연도마다 한 행 (관찰용)
        crosscheck: 두 소스의 차이가 허용폭을 넘은 날 전체
        replaced: 거래량 0 이라 종가를 바꾼 날 전체
        summary: 실행 요약
    """

    statistics: pd.DataFrame
    excess: pd.DataFrame
    test: pd.DataFrame
    entries: pd.DataFrame
    calendar_years: pd.DataFrame
    crosscheck: pd.DataFrame
    replaced: pd.DataFrame
    summary: dict[str, Any]


def load_dataset(dataset: Dataset) -> LoadedDataset:
    """대상의 시세와 대조 계열을 읽고, 대조한 뒤 거래량 0 인 날의 종가를 바꾼다.

    **측정과 체결이 이 함수를 함께 쓴다** — 두 벌을 두면 한쪽만 종가를 바꿔 같은 날에 다른 가격이 쓰인다.

    **대조는 바꾸기 «전»에 한다.** 바꾼 값끼리 견주면 거래가 없던 날의 괴리가 사라져 목록에서 빠진다.

    Args:
        dataset: 검증 대상

    Returns:
        읽은 결과
    """
    raw = load_crypto_market_csv(dataset.path)
    reference = load_series_csv(dataset.reference_path)
    crosscheck = crosscheck_closes(raw, reference)
    prices = replace_zero_volume_closes(raw, reference)

    return LoadedDataset(frame=prices.frame, reference=reference, replaced=prices.replaced, crosscheck=crosscheck)


def signal_returns(frame: pd.DataFrame) -> pd.DataFrame:
    """신호(반감기 × 진입 개월 × 보유 개월)의 long-form 수익률을 낸다.

    **측정과 체결이 이 함수를 함께 쓴다** — 진입일 정의를 두 벌 만들면 두 계층이 다른 날에 들어간다.

    Args:
        frame: 날짜 오름차순 시세

    Returns:
        진입 × 보유 행. 청산이 데이터 끝을 넘은 행도 남는다
    """
    trading_days = pd.DatetimeIndex(frame[COL_DATE])
    entries = halving_entries(trading_days, HALVINGS, ENTRY_MONTHS)

    return calendar_returns(frame, exit_schedule(trading_days, entries, HOLD_MONTHS))


def _baseline_returns(frame: pd.DataFrame) -> pd.DataFrame:
    """기준선(첫 반감기부터 매일 진입 × 같은 보유)의 long-form 수익률을 낸다.

    Args:
        frame: 날짜 오름차순 시세

    Returns:
        매일 × 보유 행
    """
    trading_days = pd.DatetimeIndex(frame[COL_DATE])
    entries = baseline_entries(trading_days, HALVINGS[0].day)

    return calendar_returns(frame, exit_schedule(trading_days, entries, HOLD_MONTHS))


def halving_records() -> list[dict[str, Any]]:
    """실행 요약에 싣는 반감기 넷 — 높이 · 블록 시각 · 날짜.

    **측정과 체결의 요약이 같은 함수로 낸다** — 두 칸이 다른 형식으로 같은 값을 적지 않게 한다.

    Returns:
        반감기마다 한 줄
    """
    return [
        {KEY_HEIGHT: halving.height, KEY_BLOCK_TIME: halving.block_time.isoformat(), KEY_DATE: halving.label}
        for halving in HALVINGS
    ]


def _non_overlapping(trading_days: pd.DatetimeIndex, frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """칸마다 **겹치지 않게 고를 수 있는 체결의 최대 개수**를 센다.

    **산식은 `measure.statistics.max_non_overlapping` 이 소유한다.** 보유가 달력월이라 체결마다 길이가
    며칠씩 다르므로 **그 칸의 가장 긴 보유**를 구간 길이로 쓴다 — 짧게 잡으면 실제로 겹친 두 구간을
    독립으로 세어 표본이 실제보다 단단해 보인다.

    Args:
        trading_days: 거래일 목록
        frame: 제외 행이 섞인 long-form
        keys: 칸을 가르는 컬럼

    Returns:
        칸 키 컬럼 + 비중첩 개수
    """
    valid = frame[frame[COL_EXCLUDED_REASON] == REASON_NONE]

    rows: list[dict[str, Any]] = []
    # 키를 «목록»으로 넘기므로 묶음 키는 칸이 하나여도 언제나 튜플이다
    for key, cell in valid.groupby(keys, sort=True):
        positions = resolve_positions(trading_days, pd.DatetimeIndex(cell[COL_DATE]), label="진입일")
        count = max_non_overlapping(positions.tolist(), int(cell[COL_HOLD_DAYS].max()))
        rows.append({**dict(zip(keys, key, strict=True)), COL_NON_OVERLAPPING: count})

    return pd.DataFrame(rows, columns=[*keys, COL_NON_OVERLAPPING])


def _aggregate(
    signal: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    trading_days: pd.DatetimeIndex,
    repeats: int,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """칸마다 신호 집계 · 기준선 대비 차이 · 우연확률을 낸다.

    [중요] **제외 행을 포함한 «전체»를 받는다.** 유효 행만 넘기면 `summarize` 가 셀 제외가 없어
    `제외` 가 언제나 0 이 되는데, 이 저장소에서 0 은 「재서 0」이라 없는 안전을 보고하게 된다.

    Args:
        signal: 신호 long-form (제외 행 포함)
        baseline: 기준선 long-form (제외 행 포함)
        trading_days: 거래일 목록
        repeats: 무작위 뽑기 반복 수
        seed: 무작위 뽑기 시드

    Returns:
        (통계, excess, test) — 식별 컬럼 없이 진입 · 보유 칸 축만 붙은 표

    Raises:
        ValueError: 진입이 하나도 없는 진입 개월이 있는 경우 — 칸 구성이 기준선과 어긋나 차이를 낼 수 없다
    """
    baseline_summary = summarize(baseline)
    baseline_values = baseline_summary[[COL_HORIZON, *_SUMMARY_VALUES]].rename(
        columns={column: f"{column}{BASELINE_SUFFIX}" for column in _SUMMARY_VALUES}
    )
    baseline_overlap = _non_overlapping(trading_days, baseline, [COL_HOLD_MONTHS]).rename(
        columns={COL_HOLD_MONTHS: COL_HORIZON, COL_NON_OVERLAPPING: COL_BASELINE_NON_OVERLAPPING}
    )
    signal_overlap = _non_overlapping(trading_days, signal, [COL_ENTRY_MONTHS, COL_HOLD_MONTHS])

    statistics: list[pd.DataFrame] = []
    excess_blocks: list[pd.DataFrame] = []
    test_blocks: list[pd.DataFrame] = []
    for entry_months in ENTRY_MONTHS:
        cell = signal[signal[COL_ENTRY_MONTHS] == entry_months]
        if cell.empty:
            raise ValueError(f"진입이 하나도 없는 칸이 있습니다: 반감기 뒤 {entry_months}개월 진입")

        summary = summarize(cell)
        cell_excess = excess(summary, baseline_summary).merge(baseline_values, on=COL_HORIZON)
        cell_excess = cell_excess.merge(baseline_overlap, on=COL_HORIZON)
        cell_test = permutation_test(cell, baseline, repeats=repeats, seed=seed)

        summary[COL_MEAN_RATE_CONFLICT] = yes_no(mean_rate_conflict(summary))
        summary[COL_JUDGEABLE] = summary[COL_SAMPLE_COUNT].map(lambda count: judgeable(int(count)))

        for table, blocks in ((summary, statistics), (cell_excess, excess_blocks), (cell_test, test_blocks)):
            blocks.append(table.assign(**{COL_ENTRY_MONTHS: entry_months}))

    def cells(blocks: list[pd.DataFrame], values: list[str]) -> pd.DataFrame:
        combined = pd.concat(blocks, ignore_index=True).rename(columns={COL_HORIZON: COL_HOLD_MONTHS})
        return combined[[COL_ENTRY_MONTHS, COL_HOLD_MONTHS, *values]]

    statistics_values = [*_SUMMARY_VALUES, COL_MEAN_RATE_CONFLICT, COL_JUDGEABLE]
    statistics_table = cells(statistics, statistics_values).merge(
        signal_overlap, on=[COL_ENTRY_MONTHS, COL_HOLD_MONTHS], how="left"
    )
    # 유효 체결이 없는 칸은 비중첩도 0 이 아니라 **센 것이 없다** — 결측을 견디는 정수로 둔다
    statistics_table[COL_NON_OVERLAPPING] = statistics_table[COL_NON_OVERLAPPING].astype("Int64")

    return statistics_table, cells(excess_blocks, _EXCESS_VALUES), cells(test_blocks, _TEST_VALUES)


def _crosscheck_table(result: CrosscheckResult) -> pd.DataFrame:
    """허용폭을 넘은 날 전체와 그날 Bitstamp 에 거래가 있었는지.

    Args:
        result: 크로스체크 결과

    Returns:
        날짜 · 두 종가 · 차이율 · 거래량 0 여부
    """
    table = result.over_tolerance[[COL_DATE, COL_PRIMARY, COL_SECONDARY, COL_DIFF_RATE]].reset_index(drop=True)
    table[COL_ZERO_VOLUME] = yes_no(table[COL_DATE].isin(result.zero_volume[COL_DATE]))

    return table


def run_study(
    datasets: tuple[Dataset, ...] = DATASETS,
    *,
    repeats: int = DEFAULT_REPEAT_COUNT,
    seed: int = DEFAULT_RANDOM_SEED,
) -> StudyOutputs:
    """반감기_사이클 측정을 실행하고 산출물을 조립한다.

    Args:
        datasets: 검증 대상 목록
        repeats: 무작위 뽑기 반복 수
        seed: 무작위 뽑기 시드

    Returns:
        실행 산출물

    Raises:
        ValueError: 대상 목록이 비어 있는 경우
    """
    if not datasets:
        raise ValueError("검증 대상이 하나도 없습니다")

    blocks: dict[str, list[pd.DataFrame]] = {field: [] for field in OUTPUT_FILES}
    dataset_summaries: list[dict[str, Any]] = []

    for dataset in datasets:
        loaded = load_dataset(dataset)
        frame = loaded.frame
        trading_days = pd.DatetimeIndex(frame[COL_DATE])

        signal = signal_returns(frame)
        statistics, cell_excess, cell_test = _aggregate(
            signal, _baseline_returns(frame), trading_days=trading_days, repeats=repeats, seed=seed
        )

        direction = DIRECTION_DOWN if BET_DOWN else DIRECTION_UP
        tables = {
            FIELD_STATISTICS: statistics,
            FIELD_EXCESS: cell_excess,
            FIELD_TEST: cell_test,
            FIELD_ENTRIES: signal[_ENTRY_COLUMNS],
            FIELD_CALENDAR_YEARS: calendar_year_returns(frame, HALVINGS),
            FIELD_CROSSCHECK: _crosscheck_table(loaded.crosscheck),
            FIELD_REPLACED: loaded.replaced,
        }
        for field, table in tables.items():
            labelled = table.copy()
            labelled.insert(0, COL_TICKER, dataset.label)
            # **방향은 칸 표 셋에만 붙는다** — 성적표와 조인되는 표이고, 나머지는 칸이 아니다
            if field in (FIELD_STATISTICS, FIELD_EXCESS, FIELD_TEST):
                labelled.insert(3, COL_DIRECTION, direction)
            blocks[field].append(labelled)

        excluded_count = int((signal[COL_EXCLUDED_REASON] != REASON_NONE).sum())
        reference_dates = loaded.reference[COL_DATE]
        crosscheck = loaded.crosscheck
        dataset_summaries.append(
            {
                # **`ticker` 는 반드시 `dataset.ticker` 에서 온다** — 둘 다 `str` 이라 다른 필드를 넘겨도
                # 키 이름은 그대로고 값만 조용히 뒤바뀐다 (`tests/test_layer_contracts.py` 가 출처를 검사한다)
                **dataset_record(ticker=dataset.ticker, label=dataset.label, file=dataset.path.name, frame=frame),
                # **파일 이름만 싣는다** — 절대경로는 PC 마다 달라 커밋된 요약이 갈린다
                KEY_REFERENCE: {
                    KEY_FILE: dataset.reference_path.name,
                    KEY_PERIOD: format_period(reference_dates.iloc[0], reference_dates.iloc[-1]),
                    KEY_ROWS: len(loaded.reference),
                },
                KEY_SIGNAL_COUNT: len(signal),
                KEY_EXCLUDED_COUNT: excluded_count,
                KEY_REPLACED_COUNT: len(loaded.replaced),
                KEY_CROSSCHECK: {
                    KEY_TOLERANCE: crosscheck.tolerance,
                    KEY_OVERLAP_DAYS: len(crosscheck.overlap),
                    KEY_OVER_TOLERANCE_DAYS: len(crosscheck.over_tolerance),
                    KEY_PRIMARY_ONLY_DAYS: crosscheck.primary_only_count,
                    KEY_SECONDARY_ONLY_DAYS: crosscheck.secondary_only_count,
                    KEY_ZERO_VOLUME_DAYS: len(crosscheck.zero_volume),
                },
            }
        )

    combined = {field: pd.concat(frames, ignore_index=True) for field, frames in blocks.items()}

    summary: dict[str, Any] = {
        KEY_TRACK: TRACK_NAME,
        KEY_PERMUTATION_REPEATS: repeats,
        KEY_PERMUTATION_SEED: seed,
        KEY_HALVINGS: halving_records(),
        KEY_ENTRY_MONTHS: list(ENTRY_MONTHS),
        KEY_HOLD_MONTHS: list(HOLD_MONTHS),
        KEY_BASELINE_START: HALVINGS[0].label,
        KEY_DATASETS: dataset_summaries,
        KEY_ROW_COUNTS: {OUTPUT_FILES[field]: len(table) for field, table in combined.items()},
    }

    logger.debug(f"측정 완료: {len(combined[FIELD_STATISTICS]):,}칸 (대상 {len(datasets)})")

    return StudyOutputs(
        statistics=combined[FIELD_STATISTICS],
        excess=combined[FIELD_EXCESS],
        test=combined[FIELD_TEST],
        entries=combined[FIELD_ENTRIES],
        calendar_years=combined[FIELD_CALENDAR_YEARS],
        crosscheck=combined[FIELD_CROSSCHECK],
        replaced=combined[FIELD_REPLACED],
        summary=summary,
    )


def display_tables(outputs: StudyOutputs) -> dict[str, pd.DataFrame]:
    """저장할 표를 표시용(한글 헤더·백분율)으로 바꾼다.

    **터미널과 CSV 가 같은 프레임을 쓴다.** 따로 가공하면 반올림 시점이 갈려 화면에서 본 숫자를
    CSV 에서 찾지 못한다.

    **빈 표는 내지 않는다** — 저장 계층이 빈 표를 거부하고, 행 수는 요약이 `0` 으로 남긴다
    (`src/verify_lab/CLAUDE.md` 「`row_counts` 의 `0` 은 「파일이 없다」는 뜻입니다」).

    Args:
        outputs: 실행 산출물

    Returns:
        산출물 필드 이름 → 표시용 DataFrame
    """
    tables = {
        FIELD_STATISTICS: outputs.statistics,
        FIELD_EXCESS: outputs.excess,
        FIELD_TEST: outputs.test,
        # **진입일을 시세의 날짜와 다른 이름으로 낸다** — 거래내역의 「진입일」과 같은 헤더가 나가야 대조된다
        FIELD_ENTRIES: outputs.entries.rename(columns={COL_DATE: COL_ENTRY_DATE}),
        FIELD_CALENDAR_YEARS: outputs.calendar_years,
        FIELD_CROSSCHECK: outputs.crosscheck,
        FIELD_REPLACED: outputs.replaced,
    }

    return {
        field: to_display_columns(
            table,
            COLUMN_LABELS,
            percent_columns=[column for column in PERCENT_COLUMNS if column in table.columns],
            probability_columns=[column for column in PROBABILITY_COLUMNS if column in table.columns],
        )
        for field, table in tables.items()
        if not table.empty
    }


__all__ = [
    "LoadedDataset",
    "StudyOutputs",
    "display_tables",
    "halving_records",
    "load_dataset",
    "run_study",
    "signal_returns",
]
