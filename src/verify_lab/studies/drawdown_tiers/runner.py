"""하락_단계_매수 측정 조립 — 대상 × 지표 × 단계 × 보유 기간의 맨몸 격자와 신호일 원자료

**계산하지 않는다.** 신호와 진입 규칙은 `tiers`, 통계는 `measure/statistics` 가 소유하고 여기서는 조립만 한다.

| 표 | 칸 | 무엇 |
| --- | --- | --- |
| `통계.csv` | 대상 × 지표 × 단계 × 달력(전체 · 월 · 요일) × 보유 | 집계 · 평균-비율 어긋남 · 판정가능 · 비중첩 · 사건 수 (설계 결정 D7) |
| `excess.csv` | 대상 × 지표 × 단계 × 보유 | 기준선 집계와 기준선 대비 차이 — 달력 «전체» 칸만 |
| `test.csv` | 같음 | 무작위 뽑기 대조 — 달력 «전체» 칸만 |
| `신호내역.csv` | 판정일 × 단계 × 보유 | 세 지표 값 · 하락장 시작일 · 진입 · 청산 · 제외 사유 (측정의 원칙 8 · 설계 결정 Q11) |

**기준선은 그 지표를 판정할 수 있는 기간의 모든 대상 거래일, 신호와 같은 진입 규칙이다** (D8). 판정에 쓰지 않는다
(루트 `CLAUDE.md` 「기준선을 넘지 못하는 것은 탈락 사유가 아닙니다」).

**값은 1배 롱 기준 그대로다.** `방향` 은 체결 성적표와 조인하려는 식별 라벨이다.
"""

from collections import Counter
from dataclasses import dataclass
from typing import Any

import pandas as pd

from verify_lab.common_constants import COL_DATE, PRICE_DECIMALS
from verify_lab.data.loader import load_close_series, load_market_csv, load_series_csv
from verify_lab.execution.run_summary import KEY_DATASETS, KEY_ROW_COUNTS
from verify_lab.execution.trade_fill import resolve_positions
from verify_lab.measure.constants import (
    BASELINE_SUFFIX,
    COL_BASELINE_NON_OVERLAPPING,
    COL_ENTRY_CLOSE,
    COL_EXCLUDED_COUNT,
    COL_EXCLUDED_REASON,
    COL_EXIT_CLOSE,
    COL_EXIT_DATE,
    COL_FORWARD_RETURN,
    COL_HORIZON,
    COL_JUDGEABLE,
    COL_MEAN_RATE_CONFLICT,
    COL_NON_OVERLAPPING,
    COL_SIGNAL_COUNT,
    COL_TICKER,
    REASON_NONE,
)
from verify_lab.measure.forward_return import ReturnBasis
from verify_lab.measure.screening import COL_DIRECTION, DIRECTION_UP
from verify_lab.measure.statistics import (
    COL_BASIS,
    COL_DOWN_RATE_P_VALUE,
    COL_LOSS_RATE_EXCESS,
    COL_MEAN_EXCESS,
    COL_MEAN_P_VALUE,
    COL_MEDIAN_EXCESS,
    COL_MEDIAN_P_VALUE,
    COL_NEGATIVE_COUNT,
    COL_POSITIVE_COUNT,
    COL_SAMPLE_COUNT,
    COL_SIGNAL_SAMPLE_COUNT,
    COL_TEST_NOTE,
    COL_UP_RATE_P_VALUE,
    COL_WIN_RATE_EXCESS,
    DEFAULT_RANDOM_SEED,
    DEFAULT_REPEAT_COUNT,
    NOTE_TOO_FEW_SAMPLES,
    SUMMARY_COLUMNS,
    TEST_COLUMNS,
    excess,
    judgeable,
    max_non_overlapping,
    mean_rate_conflict,
    permutation_test,
    summarize,
    yes_no,
)
from verify_lab.report.constants import MEASURE_PROBABILITY_COLUMNS
from verify_lab.report.run_summary import (
    KEY_DATASET_FILE,
    KEY_DATASET_PERIOD,
    KEY_DATASET_ROWS,
    KEY_EXCLUDED_COUNT,
    KEY_PERMUTATION_REPEATS,
    KEY_PERMUTATION_SEED,
    KEY_TRACK,
    dataset_record,
    format_period,
)
from verify_lab.report.tables import to_display_columns
from verify_lab.studies.drawdown_tiers.constants import (
    CALENDAR_ALL,
    CALENDAR_MONTH,
    CALENDAR_WEEKDAY,
    COL_CALENDAR_AXIS,
    COL_CALENDAR_VALUE,
    COL_DRAWDOWN,
    COL_ENTRY_DATE,
    COL_EVENT_COUNT,
    COL_EVENT_START,
    COL_FEAR_GREED,
    COL_INDICATOR,
    COL_TIER,
    COL_VIX,
    COLUMN_LABELS,
    DATASETS,
    DRAWDOWN_RULE,
    FEAR_GREED_DECIMALS,
    FEAR_GREED_RULE,
    FIELD_EXCESS,
    FIELD_SIGNALS,
    FIELD_STATISTICS,
    FIELD_TEST,
    HORIZONS,
    INDICATOR_FILES,
    KEY_EXCLUDED_BY_REASON,
    KEY_INDICATOR,
    KEY_SIGNAL_COUNT,
    MONTH_NAMES,
    OUTPUT_FILES,
    PERCENT_COLUMNS,
    RULES,
    TRACK_NAME,
    VIX_MAX_DAILY_CHANGE_RATE,
    VIX_RULE,
    WEEKDAY_NAMES,
    Dataset,
    IndicatorFiles,
    TierRule,
)
from verify_lab.studies.drawdown_tiers.tiers import (
    TierSignals,
    align_indicator,
    baseline_returns,
    drawdown_rates,
    entry_returns,
    peak_dates,
    tier_signals,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# `summary.json` 의 측정 칸
KEY_HORIZONS = "horizons"
KEY_RULES = "rules"
KEY_LEVELS = "levels"
KEY_FIRES_BELOW = "fires_below"
KEY_REARM_LEVEL = "rearm_level"
KEY_INDICATOR_FILES = "indicator_files"
KEY_SIGNAL_FILE = "signal_file"
KEY_INDICATORS = "indicators"
KEY_JUDGING_START = "judging_start"
KEY_TIER_SIGNALS = "tier_signals"
KEY_MISSING_DAYS = "missing_days"
KEY_UNJUDGED_DAYS = "unjudged_days"

# 집계 값 — 기준과 구간 축을 뺀 `summarize` 결과 전부. 기준선 쪽은 접미사를 붙여 실음
_SUMMARY_VALUES = [column for column in SUMMARY_COLUMNS if column not in (COL_BASIS, COL_HORIZON)]

_IDENTITY = [COL_TICKER, COL_INDICATOR, COL_TIER]

STATISTICS_COLUMNS = [
    *_IDENTITY,
    COL_CALENDAR_AXIS,
    COL_CALENDAR_VALUE,
    COL_HORIZON,
    COL_DIRECTION,
    *_SUMMARY_VALUES,
    COL_MEAN_RATE_CONFLICT,
    COL_JUDGEABLE,
    COL_NON_OVERLAPPING,
    COL_EVENT_COUNT,
]

# 기준선 표본은 접미사 붙은 집계에 한 번만 실음 — `excess` 의 기준선 표본 칸과 같은 값이라 두 칸이면 매번 견줘야 함
EXCESS_COLUMNS = [
    *_IDENTITY,
    COL_HORIZON,
    COL_DIRECTION,
    COL_SIGNAL_SAMPLE_COUNT,
    *(f"{column}{BASELINE_SUFFIX}" for column in _SUMMARY_VALUES),
    COL_BASELINE_NON_OVERLAPPING,
    COL_MEAN_EXCESS,
    COL_MEDIAN_EXCESS,
    COL_WIN_RATE_EXCESS,
    COL_LOSS_RATE_EXCESS,
]

# 관측값 · 백분위는 싣지 않음 — 관측값은 `통계.csv` 와 같은 값이고 판단 재료는 우연확률과 비고
TEST_TABLE_COLUMNS = [
    *_IDENTITY,
    COL_HORIZON,
    COL_DIRECTION,
    COL_SAMPLE_COUNT,
    COL_MEAN_P_VALUE,
    COL_MEDIAN_P_VALUE,
    COL_UP_RATE_P_VALUE,
    COL_DOWN_RATE_P_VALUE,
    COL_TEST_NOTE,
]

# 신호일 원자료 — 단계별 long-form 에 판정일의 세 지표 값과 하락장 시작일을 붙인 것
SIGNAL_COLUMNS = [
    *_IDENTITY,
    COL_DATE,
    COL_DRAWDOWN,
    COL_VIX,
    COL_FEAR_GREED,
    COL_EVENT_START,
    COL_HORIZON,
    COL_ENTRY_DATE,
    COL_ENTRY_CLOSE,
    COL_EXIT_DATE,
    COL_EXIT_CLOSE,
    COL_FORWARD_RETURN,
    COL_EXCLUDED_REASON,
]

# 단계별 long-form 의 칸 — 원자료 칸에 `summarize` 가 요구하는 기준 축
TIER_RETURN_COLUMNS = [*SIGNAL_COLUMNS, COL_BASIS]


@dataclass(frozen=True)
class LoadedIndicators:
    """외부 지표 둘 (날짜 · 값)

    Attributes:
        vix: VIX 종가 계열
        fear_greed: 공포탐욕지수 계열
    """

    vix: pd.DataFrame
    fear_greed: pd.DataFrame


@dataclass(frozen=True)
class LoadedDataset:
    """대상 하나를 읽은 결과 — 측정과 체결이 같은 것을 쓴다

    Attributes:
        frame: 대상 가격 (ETF 시세 · 지수 종가 계열)
        signal_close: 신호 대상 종가 (날짜 인덱스) — 낙폭 신호와 판정일 달력
    """

    frame: pd.DataFrame
    signal_close: pd.Series


@dataclass(frozen=True)
class IndicatorSignals:
    """지표 하나의 단계 신호

    Attributes:
        rule: 단계 규칙
        start: 판정 기간 첫날 — 기준선이 여기서 시작한다 (D8)
        result: 단계 신호와 판정하지 않은 날 수
    """

    rule: TierRule
    start: pd.Timestamp
    result: TierSignals


@dataclass(frozen=True)
class SignalSet:
    """대상 하나의 세 지표 신호와 판정일 원자료 — 측정과 체결이 같은 것을 쓴다

    Attributes:
        indicators: 지표마다 단계 신호 (`RULES` 순서)
        context: 판정일마다 세 지표 값 · 하락장 시작일
    """

    indicators: tuple[IndicatorSignals, ...]
    context: pd.DataFrame


@dataclass(frozen=True)
class StudyOutputs:
    """측정 산출물

    Attributes:
        statistics: 대상 × 지표 × 단계 × 달력 × 보유마다 한 행
        excess: 대상 × 지표 × 단계 × 보유마다 한 행 — 기준선과 차이
        test: 같은 칸의 무작위 뽑기 대조
        signals: 판정일 × 단계 × 보유 long-form. 제외 행도 사유와 함께 남는다
        summary: 실행 요약
    """

    statistics: pd.DataFrame
    excess: pd.DataFrame
    test: pd.DataFrame
    signals: pd.DataFrame
    summary: dict[str, Any]


def load_indicators(files: IndicatorFiles) -> LoadedIndicators:
    """VIX 와 공포탐욕지수를 읽는다 — VIX 는 시세 사본이라 종가 계열로, 급등락 임계는 VIX 의 값으로 (D3).

    Args:
        files: 지표 파일 둘

    Returns:
        읽은 지표 둘
    """
    return LoadedIndicators(
        vix=load_close_series(files.vix, max_daily_change_rate=VIX_MAX_DAILY_CHANGE_RATE),
        fear_greed=load_series_csv(files.fear_greed),
    )


def load_dataset(dataset: Dataset) -> LoadedDataset:
    """대상과 신호 대상의 가격을 읽는다 — 지수는 종가 계열로 (고가 · 저가를 프레임에 남기지 않는다).

    Args:
        dataset: 대상

    Returns:
        읽은 결과
    """
    frame = _load_prices(dataset, dataset.symbol)
    signal = frame if dataset.signal_symbol == dataset.symbol else _load_prices(dataset, dataset.signal_symbol)
    close = pd.Series(signal[dataset.price_column].to_numpy(dtype=float), index=pd.DatetimeIndex(signal[COL_DATE]))

    return LoadedDataset(frame=frame, signal_close=close)


def signal_set(loaded: LoadedDataset, indicators: LoadedIndicators) -> SignalSet:
    """세 지표의 단계 신호와 판정일 원자료를 낸다 — 판정일은 신호 대상의 거래일이다 (D5).

    Args:
        loaded: 대상을 읽은 결과
        indicators: 외부 지표 둘

    Returns:
        신호와 원자료
    """
    days = pd.DatetimeIndex(loaded.signal_close.index)
    drawdown = drawdown_rates(loaded.signal_close)
    vix = align_indicator(days, indicators.vix)
    fear_greed = align_indicator(days, indicators.fear_greed)

    # 지표 값은 규칙의 지표 이름으로 찾음 — 산출 순서는 `RULES` 하나가 정함
    values_by_indicator = {
        DRAWDOWN_RULE.indicator: drawdown,
        VIX_RULE.indicator: vix,
        FEAR_GREED_RULE.indicator: fear_greed,
    }
    results = tuple(
        IndicatorSignals(
            rule=rule,
            start=pd.Timestamp(values_by_indicator[rule.indicator].index[0]),
            result=tier_signals(values_by_indicator[rule.indicator], rule),
        )
        for rule in RULES
    )
    context = pd.DataFrame(
        {
            COL_DATE: days,
            COL_DRAWDOWN: drawdown.to_numpy(),
            COL_VIX: vix.reindex(days).to_numpy(),
            COL_FEAR_GREED: fear_greed.reindex(days).to_numpy(),
            COL_EVENT_START: peak_dates(loaded.signal_close).to_numpy(),
        }
    )

    return SignalSet(indicators=results, context=context)


def tier_returns(
    frame: pd.DataFrame, signal: IndicatorSignals, context: pd.DataFrame, *, label: str, price_column: str
) -> pd.DataFrame:
    """지표 하나의 단계마다 판정일 × 보유 기간 long-form 을 낸다 — 측정과 체결이 같은 표를 쓴다.

    Args:
        frame: 대상 가격
        signal: 지표 하나의 단계 신호
        context: 판정일 원자료 (`SignalSet.context`)
        label: 대상 표시 이름 (종목 칸)
        price_column: 대상 가격 칸

    Returns:
        `TIER_RETURN_COLUMNS` 구성. 단계 → 판정일 → 보유 기간 순. 신호가 없는 단계는 행이 없고,
        세 지표 모두 신호가 없으면 빈 표다
    """
    signals = signal.result.signals
    blocks: list[pd.DataFrame] = []
    for level in signal.rule.levels:
        dates = pd.DatetimeIndex(signals.loc[signals[COL_TIER] == level, COL_DATE])
        if len(dates) == 0:
            continue
        returns = entry_returns(frame, dates, horizons=HORIZONS, price_column=price_column)
        returns[COL_INDICATOR] = signal.rule.indicator
        returns[COL_TIER] = signal.rule.label(level)
        blocks.append(returns)

    if not blocks:
        return pd.DataFrame(columns=TIER_RETURN_COLUMNS)

    combined = pd.concat(blocks, ignore_index=True).merge(context, on=COL_DATE, how="left", validate="many_to_one")
    combined[COL_TICKER] = label

    return combined[TIER_RETURN_COLUMNS]


def run_study(
    datasets: tuple[Dataset, ...] = DATASETS,
    *,
    indicator_files: IndicatorFiles = INDICATOR_FILES,
    repeats: int = DEFAULT_REPEAT_COUNT,
    seed: int = DEFAULT_RANDOM_SEED,
) -> StudyOutputs:
    """하락_단계_매수 측정을 실행하고 산출물을 조립한다.

    Args:
        datasets: 대상 목록
        indicator_files: 외부 지표 파일 둘 — 테스트가 합성 파일을 넣는다
        repeats: 무작위 뽑기 반복 수
        seed: 무작위 뽑기 시드

    Returns:
        측정 산출물

    Raises:
        ValueError: 대상 목록이 비어 있는 경우
    """
    if not datasets:
        raise ValueError("검증 대상이 하나도 없습니다")

    indicators = load_indicators(indicator_files)
    blocks: dict[str, list[pd.DataFrame]] = {field: [] for field in OUTPUT_FILES}
    records: list[dict[str, Any]] = []

    for dataset in datasets:
        loaded = load_dataset(dataset)
        frame = loaded.frame
        trading_days = pd.DatetimeIndex(frame[COL_DATE])
        signals = signal_set(loaded, indicators)

        indicator_records: list[dict[str, Any]] = []
        for signal in signals.indicators:
            returns = tier_returns(
                frame, signal, signals.context, label=dataset.label, price_column=dataset.price_column
            )
            baseline = baseline_returns(frame, start=signal.start, horizons=HORIZONS, price_column=dataset.price_column)
            tables = _indicator_tables(
                returns, baseline, signal.rule, trading_days, label=dataset.label, repeats=repeats, seed=seed
            )
            for field, table in tables.items():
                blocks[field].append(table)
            # 빈 조각을 이어 붙이면 pandas 가 칸의 dtype 을 잃음 — 행 수는 요약이 셈.
            # 종가 자릿수는 데이터셋이 정함 (실행 계층 계약 「종가 반올림」 — 체결의 `trade_columns` 와 같은 값)
            if not returns.empty:
                blocks[FIELD_SIGNALS].append(
                    returns[SIGNAL_COLUMNS].round(
                        {COL_ENTRY_CLOSE: dataset.price_decimals, COL_EXIT_CLOSE: dataset.price_decimals}
                    )
                )
            indicator_records.append(_indicator_record(signal, returns))

        records.append(
            {
                **dataset_record(ticker=dataset.ticker, label=dataset.label, file=dataset.path.name, frame=frame),
                KEY_SIGNAL_FILE: dataset.signal_path.name,
                KEY_INDICATORS: indicator_records,
            }
        )

    combined = {
        field: pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=SIGNAL_COLUMNS)
        for field, frames in blocks.items()
    }
    summary: dict[str, Any] = {
        KEY_TRACK: TRACK_NAME,
        KEY_PERMUTATION_REPEATS: repeats,
        KEY_PERMUTATION_SEED: seed,
        KEY_HORIZONS: list(HORIZONS),
        KEY_RULES: [
            {
                KEY_INDICATOR: rule.indicator,
                KEY_LEVELS: [rule.label(level) for level in rule.levels],
                KEY_FIRES_BELOW: rule.fires_below,
                KEY_REARM_LEVEL: rule.rearm_level,
            }
            for rule in RULES
        ],
        KEY_INDICATOR_FILES: [
            _series_record(VIX_RULE.indicator, indicator_files.vix.name, indicators.vix),
            _series_record(FEAR_GREED_RULE.indicator, indicator_files.fear_greed.name, indicators.fear_greed),
        ],
        KEY_DATASETS: records,
        KEY_ROW_COUNTS: {OUTPUT_FILES[field]: len(table) for field, table in combined.items()},
    }

    logger.debug(f"측정 완료: 통계 {len(combined[FIELD_STATISTICS]):,}행 (대상 {len(datasets)})")

    return StudyOutputs(
        statistics=combined[FIELD_STATISTICS],
        excess=combined[FIELD_EXCESS],
        test=combined[FIELD_TEST],
        signals=combined[FIELD_SIGNALS],
        summary=summary,
    )


def display_tables(outputs: StudyOutputs) -> dict[str, pd.DataFrame]:
    """저장할 표를 표시용(한글 헤더 · 백분율)으로 바꾼다 — 터미널과 CSV 가 같은 프레임을 쓴다.

    **빈 표는 내지 않는다** — 저장 계층이 빈 표를 거부하고, 행 수는 요약이 `0` 으로 남긴다.

    Args:
        outputs: 측정 산출물

    Returns:
        산출물 필드 이름 → 표시용 DataFrame
    """
    tables = {
        FIELD_STATISTICS: outputs.statistics,
        FIELD_EXCESS: outputs.excess,
        FIELD_TEST: outputs.test,
        # 종가는 `run_study` 가 데이터셋 자릿수로 이미 끊음 — VIX 는 시세처럼 가격 자릿수
        FIELD_SIGNALS: outputs.signals.round({COL_VIX: PRICE_DECIMALS, COL_FEAR_GREED: FEAR_GREED_DECIMALS}),
    }

    return {
        field: to_display_columns(
            table,
            COLUMN_LABELS,
            percent_columns=[column for column in PERCENT_COLUMNS if column in table.columns],
            probability_columns=[column for column in MEASURE_PROBABILITY_COLUMNS if column in table.columns],
        )
        for field, table in tables.items()
        if not table.empty
    }


def _load_prices(dataset: Dataset, symbol: str) -> pd.DataFrame:
    """대상과 같은 형식의 가격 파일을 읽는다 — 지수는 종가 계열이다.

    Args:
        dataset: 대상 (폴더 · 파일 형식 · 지수 여부)
        symbol: 읽을 심볼

    Returns:
        날짜 오름차순 가격
    """
    path = dataset.directory / dataset.file_template.format(ticker=symbol)
    return load_close_series(path) if dataset.is_index else load_market_csv(path)


def _indicator_tables(
    returns: pd.DataFrame,
    baseline: pd.DataFrame,
    rule: TierRule,
    trading_days: pd.DatetimeIndex,
    *,
    label: str,
    repeats: int,
    seed: int,
) -> dict[str, pd.DataFrame]:
    """지표 하나의 단계마다 통계(달력 축 포함) · 기준선 대비 차이 · 우연확률을 낸다.

    **제외 행을 포함한 «전체»를 받는다** — 유효 행만 넘기면 제외가 언제나 0 이 된다.

    Args:
        returns: 단계별 long-form (`tier_returns`)
        baseline: 기준선 long-form
        rule: 단계 규칙
        trading_days: 대상 거래일
        label: 대상 표시 이름 (종목 칸)
        repeats: 무작위 뽑기 반복 수
        seed: 무작위 뽑기 시드

    Returns:
        통계 · excess · test 세 표
    """
    baseline_summary = summarize(baseline)
    baseline_values = baseline_summary[[COL_HORIZON, *_SUMMARY_VALUES]].rename(
        columns={column: f"{column}{BASELINE_SUFFIX}" for column in _SUMMARY_VALUES}
    )
    baseline_overlap = _non_overlapping(trading_days, baseline)

    statistics: list[pd.DataFrame] = []
    excess_blocks: list[pd.DataFrame] = []
    test_blocks: list[pd.DataFrame] = []
    for level in rule.levels:
        tier = rule.label(level)
        cell = returns[returns[COL_TIER] == tier] if not returns.empty else returns
        identity = {COL_TICKER: label, COL_INDICATOR: rule.indicator, COL_TIER: tier, COL_DIRECTION: DIRECTION_UP}

        for axis, value, part in _calendar_parts(cell):
            statistics.append(
                _cell_statistics(part, trading_days).assign(
                    **identity, **{COL_CALENDAR_AXIS: axis, COL_CALENDAR_VALUE: value}
                )
            )

        summary = summarize(cell) if not cell.empty else _empty_summary()
        cell_excess = excess(summary, baseline_summary).merge(baseline_values, on=COL_HORIZON)
        cell_excess[COL_BASELINE_NON_OVERLAPPING] = cell_excess[COL_HORIZON].map(baseline_overlap).astype("Int64")
        excess_blocks.append(cell_excess.assign(**identity))

        cell_test = permutation_test(cell, baseline, repeats=repeats, seed=seed) if not cell.empty else _untested()
        test_blocks.append(cell_test.assign(**identity))

    def table(blocks: list[pd.DataFrame], columns: list[str]) -> pd.DataFrame:
        return pd.concat(blocks, ignore_index=True)[columns]

    return {
        FIELD_STATISTICS: table(statistics, STATISTICS_COLUMNS),
        FIELD_EXCESS: table(excess_blocks, EXCESS_COLUMNS),
        FIELD_TEST: table(test_blocks, TEST_TABLE_COLUMNS),
    }


def _calendar_parts(cell: pd.DataFrame) -> list[tuple[str, str, pd.DataFrame]]:
    """판정일의 달력 축으로 칸을 나눈다 — 전체 · 열두 달 · 다섯 요일 (D7). 표본이 없는 달 · 요일도 칸이 남는다.

    Args:
        cell: 단계 하나의 long-form

    Returns:
        (축, 값, 그 칸의 행) 목록

    Raises:
        ValueError: 판정일에 주말이 있는 경우 — 요일 축에 칸이 없어 표본이 조용히 빠진다
    """
    dates = pd.DatetimeIndex(cell[COL_DATE])
    if (dates.dayofweek >= len(WEEKDAY_NAMES)).any():
        raise ValueError(f"요일 축에 없는 요일의 판정일이 있습니다: {sorted(set(dates[dates.dayofweek >= 5].date))[:5]}")

    months = dates.month.to_numpy()
    weekdays = dates.dayofweek.to_numpy()

    return [
        (CALENDAR_ALL, CALENDAR_ALL, cell),
        *((CALENDAR_MONTH, name, cell[months == order]) for order, name in enumerate(MONTH_NAMES, start=1)),
        *((CALENDAR_WEEKDAY, name, cell[weekdays == order]) for order, name in enumerate(WEEKDAY_NAMES)),
    ]


def _cell_statistics(part: pd.DataFrame, trading_days: pd.DatetimeIndex) -> pd.DataFrame:
    """칸 하나의 보유 기간별 집계 · 어긋남 · 판정가능 · 비중첩 · 사건 수.

    Args:
        part: 그 칸의 long-form (제외 행 포함)
        trading_days: 대상 거래일

    Returns:
        보유 기간마다 한 행
    """
    summary = summarize(part) if not part.empty else _empty_summary()
    summary[COL_MEAN_RATE_CONFLICT] = yes_no(mean_rate_conflict(summary))
    summary[COL_JUDGEABLE] = summary[COL_SAMPLE_COUNT].map(lambda count: judgeable(int(count)))

    valid = part[part[COL_EXCLUDED_REASON] == REASON_NONE]
    events = valid.groupby(COL_HORIZON)[COL_EVENT_START].nunique()
    # 유효 표본이 없는 보유 기간은 센 것이 없음 — 0 이 아니라 빈칸
    summary[COL_NON_OVERLAPPING] = summary[COL_HORIZON].map(_non_overlapping(trading_days, part)).astype("Int64")
    summary[COL_EVENT_COUNT] = summary[COL_HORIZON].map(events).astype("Int64")

    return summary


def _non_overlapping(trading_days: pd.DatetimeIndex, frame: pd.DataFrame) -> pd.Series:
    """보유 기간마다 겹치지 않게 고를 수 있는 진입의 최대 개수 — 산식은 `measure.statistics.max_non_overlapping`.

    Args:
        trading_days: 대상 거래일
        frame: long-form (제외 행 포함)

    Returns:
        보유 기간을 인덱스로 단 개수. 유효 행이 없는 보유 기간은 없다
    """
    valid = frame[frame[COL_EXCLUDED_REASON] == REASON_NONE]
    counts: dict[int, int] = {}
    for horizon in HORIZONS:
        cell = valid[valid[COL_HORIZON] == horizon]
        if cell.empty:
            continue
        positions = resolve_positions(trading_days, pd.DatetimeIndex(cell[COL_ENTRY_DATE]), label="진입일")
        counts[horizon] = max_non_overlapping(positions.tolist(), horizon)

    return pd.Series(counts, dtype="int64")


def _empty_summary() -> pd.DataFrame:
    """신호가 한 번도 없던 칸의 집계 — 보유 기간마다 건수 0 · 지표 빈칸 (0 으로 채우면 「손실도 이익도 없었다」로 읽힘).

    Returns:
        `SUMMARY_COLUMNS` 구성
    """
    counts = (COL_SIGNAL_COUNT, COL_EXCLUDED_COUNT, COL_SAMPLE_COUNT, COL_POSITIVE_COUNT, COL_NEGATIVE_COUNT)
    empty = pd.DataFrame({COL_BASIS: ReturnBasis.CLOSE.value, COL_HORIZON: list(HORIZONS)})
    for column in SUMMARY_COLUMNS[2:]:
        empty[column] = 0 if column in counts else float("nan")

    return empty[SUMMARY_COLUMNS]


def _untested() -> pd.DataFrame:
    """신호가 없어 검정하지 않은 칸의 무작위 뽑기 대조 — 표본 0 · 우연확률 빈칸 · 사유.

    Returns:
        `TEST_COLUMNS` 구성
    """
    untested = pd.DataFrame({COL_BASIS: ReturnBasis.CLOSE.value, COL_HORIZON: list(HORIZONS), COL_SAMPLE_COUNT: 0})
    for column in TEST_COLUMNS[3:]:
        untested[column] = NOTE_TOO_FEW_SAMPLES if column == COL_TEST_NOTE else float("nan")

    return untested[TEST_COLUMNS]


def _indicator_record(signal: IndicatorSignals, returns: pd.DataFrame) -> dict[str, Any]:
    """대상 하나 · 지표 하나의 요약 — 판정 기간 · 단계별 신호 수 · 빠진 날 · 제외 사유별 행 수 (표본 보존).

    Args:
        signal: 지표 하나의 단계 신호
        returns: 그 지표의 단계별 long-form

    Returns:
        요약 한 줄
    """
    signals = signal.result.signals
    reasons = Counter(reason for reason in returns[COL_EXCLUDED_REASON] if reason != REASON_NONE)

    return {
        KEY_INDICATOR: signal.rule.indicator,
        KEY_JUDGING_START: signal.start.date().isoformat(),
        KEY_TIER_SIGNALS: {
            signal.rule.label(level): int((signals[COL_TIER] == level).sum()) for level in signal.rule.levels
        },
        KEY_MISSING_DAYS: signal.result.missing_days,
        KEY_UNJUDGED_DAYS: signal.result.unjudged_days,
        KEY_SIGNAL_COUNT: len(returns),
        KEY_EXCLUDED_COUNT: sum(reasons.values()),
        KEY_EXCLUDED_BY_REASON: dict(reasons),
    }


def _series_record(indicator: str, file: str, frame: pd.DataFrame) -> dict[str, Any]:
    """지표 파일 하나의 이름 · 기간 · 행 수.

    Args:
        indicator: 지표 이름
        file: 파일 이름 (경로가 아니다)
        frame: 읽은 계열

    Returns:
        요약 한 줄
    """
    dates = frame[COL_DATE]

    return {
        KEY_INDICATOR: indicator,
        KEY_DATASET_FILE: file,
        KEY_DATASET_PERIOD: format_period(dates.iloc[0], dates.iloc[-1]),
        KEY_DATASET_ROWS: len(frame),
    }
