"""검증 #10 실행 — 격자 순회와 집계 조립

**계산하지 않는다.** 이벤트 정의(`schedule`)와 측정(`measure`)을 조합해 돌리고, 어느 행이
어떤 설정의 결과인지를 붙여 쌓기만 한다.

**축을 동시에 쪼개지 않는다** (`docs/spec/kosdaq_month_end.md` §3.7). 집계는 세 층이다.

1. **격자** — 진입 달력일 11칸 × 청산 상대 거래일 7칸. 월별 분해 없음
2. **월별** — 원 매매법 칸(20일 → 말일) **하나만** 12개월로 쪼갠다
3. **시기** — 균등 2분할(판정용)과 최근 10년·5년(관찰용)

격자 전체를 월별로 쪼개면 924칸이 되어 다중 비교가 폭발하고 칸당 표본이 무너진다.

**기준선은 「그 달 아무 날 진입」 하나다**(결정 ⑤). 신호와 **같은 함수**로 만들어
진입일 목록만 전 거래일로 바꾼다 — 따로 구현하면 두 계산이 조용히 갈라진다.
"""

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.data.loader import load_market_csv, load_series_csv
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_EXCLUDED_REASON,
    COL_HORIZON,
    COL_JUDGEABLE,
    JUDGEABLE_NO,
    JUDGEABLE_YES,
    MIN_SAMPLE_PER_CELL,
    REASON_NONE,
)
from verify_lab.measure.screening import SCREEN_CANDIDATE, screen_candidates
from verify_lab.measure.statistics import (
    COL_DOWN_RATE_P_VALUE,
    COL_LOSS_RATE,
    COL_LOSS_RATE_EXCESS,
    COL_MEAN,
    COL_MEAN_EXCESS,
    COL_MEAN_P_VALUE,
    COL_MEDIAN_EXCESS,
    COL_MEDIAN_P_VALUE,
    COL_SAMPLE_COUNT,
    COL_TEST_NOTE,
    COL_UP_RATE_P_VALUE,
    COL_WIN_RATE,
    COL_WIN_RATE_EXCESS,
    DEFAULT_RANDOM_SEED,
    DEFAULT_REPEAT_COUNT,
    excess,
    permutation_test,
    summarize,
)
from verify_lab.report.constants import DISPLAY_HIT_RATE, DISPLAY_SCREEN
from verify_lab.report.tables import build_candidates_table, to_display_columns
from verify_lab.studies.kosdaq_month_end.constants import (
    BASE_ENTRY_DAY,
    BASE_EXIT_OFFSET,
    BASELINE_SUFFIX,
    COL_ENTRY_CLOSE,
    COL_EXIT_CLOSE,
    COL_GRID_CELL,
    COL_HOLD_DAYS,
    COL_MEAN_RATE_CONFLICT,
    COL_MONTH_NUMBER,
    COL_PERIOD,
    COL_TARGET_DAY,
    COL_TICKER,
    COLUMN_LABELS,
    DATASETS,
    DISPLAY_EXIT_OFFSET,
    DISPLAY_GRID_CELL,
    DISPLAY_MONTH_NUMBER,
    DISPLAY_PERIOD_EARLY,
    DISPLAY_PERIOD_LATE,
    DISPLAY_PERIOD_RECENT,
    DISPLAY_TARGET_DAY,
    DISPLAY_TICKER,
    ENTRY_CALENDAR_DAYS,
    EXIT_OFFSETS,
    GRID_CELL_TEMPLATE,
    GRID_EXIT_MONTH_END,
    GRID_EXIT_RELATIVE,
    HALF_RATE,
    JUDGING_PERIODS,
    PERCENT_COLUMNS,
    PROBABILITY_COLUMNS,
    RECENT_WINDOWS_YEARS,
    Dataset,
)
from verify_lab.studies.kosdaq_month_end.constants import COL_EXIT_OFFSET as COL_OFFSET
from verify_lab.studies.kosdaq_month_end.schedule import (
    converged_month_count,
    every_day_entries,
    month_entry_dates,
    month_exit_returns,
    month_exit_schedule,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# `summary.json` 의 키
KEY_PERMUTATION_REPEATS = "permutation_repeats"
KEY_PERMUTATION_SEED = "permutation_seed"
KEY_GRID = "grid"
KEY_DATASETS = "datasets"
KEY_ROW_COUNTS = "row_counts"
KEY_TICKER = "ticker"
KEY_LABEL = "label"
KEY_FILE = "file"
KEY_ROWS = "rows"
KEY_PERIOD = "period"
KEY_IS_INDEX = "is_index"
KEY_ENTRY_COUNT = "entry_count"
KEY_EXCLUDED_COUNT = "excluded_count"
KEY_HOLD_DAYS = "hold_days"
KEY_BASELINE_ENTRY_COUNT = "baseline_entry_count"
KEY_CONVERGED = "converged_with_neighbour_months"
KEY_ENTRY_DAYS = "entry_calendar_days"
KEY_EXIT_OFFSETS = "exit_offsets"


@dataclass(frozen=True)
class StudyOutputs:
    """검증 산출물

    Attributes:
        trades: 원 매매법 칸의 신호일 원자료. 사용자가 차트로 대조한다 (측정의 원칙 8)
        grid: 격자 칸별 집계와 기준선 대비 차이·검정
        months: 원 매매법 칸의 월별 분해
        month_halves: 월별 × 시기 분해. 후보 판정의 시기 항목을 재는 축이다
        periods: 격자 칸별 시기 분해 (균등 2분할 + 최근 10년·5년)
        grid_candidates: 격자 축의 후보 판정
        month_candidates: 월별 축의 후보 판정
        summary: 실행 요약
    """

    trades: pd.DataFrame
    grid: pd.DataFrame
    months: pd.DataFrame
    month_halves: pd.DataFrame
    periods: pd.DataFrame
    grid_candidates: pd.DataFrame
    month_candidates: pd.DataFrame
    summary: dict[str, Any]


@dataclass
class _Accumulator:
    """대상마다 나온 표 조각을 쌓는 자리"""

    trades: list[pd.DataFrame] = field(default_factory=list)
    grid: list[pd.DataFrame] = field(default_factory=list)
    months: list[pd.DataFrame] = field(default_factory=list)
    month_halves: list[pd.DataFrame] = field(default_factory=list)
    periods: list[pd.DataFrame] = field(default_factory=list)
    grid_candidates: list[pd.DataFrame] = field(default_factory=list)
    month_candidates: list[pd.DataFrame] = field(default_factory=list)


def grid_cell_label(calendar_day: int, exit_offset: int) -> str:
    """격자 칸의 이름을 만든다.

    판정 계층이 **단일 축 컬럼**을 받으므로 2차원 격자를 한 축으로 접는다.
    청산 0 은 「말일」로 적어 원 매매법이 눈에 띄게 한다.

    Args:
        calendar_day: 진입 목표 달력일
        exit_offset: 청산 상대 거래일

    Returns:
        `20일 → 말일` 형태의 이름
    """
    exit_label = GRID_EXIT_MONTH_END if exit_offset == 0 else GRID_EXIT_RELATIVE.format(offset=exit_offset)

    return GRID_CELL_TEMPLATE.format(day=calendar_day, exit=exit_label)


def _load(dataset: Dataset) -> pd.DataFrame:
    """대상의 가격 데이터를 읽는다.

    **ETF 와 지수는 로더가 다르다.** 지수는 종가 계열이라 시세 판정(0 이하 가격·급등락)을
    걸 수 없다 (`docs/spec/kosdaq_month_end.md` §7.6).

    Args:
        dataset: 검증 대상 정의

    Returns:
        날짜 오름차순 가격 DataFrame
    """
    if dataset.is_index:
        return load_series_csv(dataset.path)

    return load_market_csv(dataset.path)


def _valid(frame: pd.DataFrame) -> pd.DataFrame:
    """제외되지 않은 행만 남긴다.

    집계는 유효 표본으로만 한다. **제외 건수는 원자료와 요약이 담당한다** —
    행을 지운 자리가 어디인지는 그쪽에서 읽는다.

    Args:
        frame: `month_exit_returns` 의 결과

    Returns:
        유효 행만 남긴 DataFrame
    """
    return frame[frame[COL_EXCLUDED_REASON] == REASON_NONE].copy()


def _frames(
    df: pd.DataFrame,
    dataset: Dataset,
    calendar_day: int,
    exit_offset: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """한 격자 칸의 신호군과 기준선 long-form 을 만든다.

    **기준선은 진입일 목록만 다르고 나머지가 같다.** 같은 청산 규칙을 같은 함수로 적용하므로
    보유 길이 분포가 신호와 같은 달력 구조에서 나온다 (결정 ⑤).

    Args:
        df: 날짜 오름차순 가격 데이터
        dataset: 검증 대상 정의
        calendar_day: 진입 목표 달력일
        exit_offset: 청산 상대 거래일

    Returns:
        (신호군 long-form, 기준선 long-form). 제외 행을 포함한 전체다
    """
    trading_days = pd.DatetimeIndex(df[COL_DATE])

    signal_entries = month_entry_dates(trading_days, calendar_day=calendar_day)
    signal_schedule = month_exit_schedule(trading_days, signal_entries, exit_offset=exit_offset)

    baseline_entries = every_day_entries(trading_days, calendar_day=calendar_day)
    baseline_schedule = month_exit_schedule(trading_days, baseline_entries, exit_offset=exit_offset)

    signal = month_exit_returns(df, signal_schedule, price_column=dataset.price_column)
    baseline = month_exit_returns(df, baseline_schedule, price_column=dataset.price_column)

    return signal, baseline


def _mean_rate_conflict(frame: pd.DataFrame) -> pd.Series:
    """평균의 부호와 방향 비율이 어긋나는 칸을 표시한다 (측정의 원칙 13).

    평균이 양수인데 절반 넘게 내렸다면 **소수의 큰 사건이 평균을 만든 것**이고, 그 반대도 같다.
    평균만 보고 방향을 읽으면 이런 칸에서 정반대로 판단하게 된다.

    Args:
        frame: 평균과 두 방향 비율이 들어 있는 집계 프레임

    Returns:
        어긋나는 칸이면 True 인 Series
    """
    mean_up_but_fell = (frame[COL_MEAN] > 0) & (frame[COL_LOSS_RATE] > HALF_RATE)
    mean_down_but_rose = (frame[COL_MEAN] < 0) & (frame[COL_WIN_RATE] > HALF_RATE)

    return mean_up_but_fell | mean_down_but_rose


def _aggregate(
    signal: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    repeats: int,
    seed: int,
) -> pd.DataFrame:
    """신호군과 기준선을 나란히 놓고 초과분·검정을 붙인다.

    **통계량 정의를 두 곳에서 구현하지 않는다.** `summarize`·`excess`·`permutation_test` 를
    그대로 쓰며, 이 함수는 세 결과를 잇기만 한다.

    Args:
        signal: 신호군 long-form (유효 행)
        baseline: 기준선 long-form (유효 행)
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        칸별 집계 한 장. 기준선 값에는 `BASELINE_SUFFIX` 가 붙는다.
        신호가 하나도 없으면 빈 DataFrame
    """
    signal_summary = summarize(signal)
    if signal_summary.empty:
        return pd.DataFrame()

    baseline_summary = summarize(baseline)
    cell_excess = excess(signal_summary, baseline_summary)
    cell_test = permutation_test(signal, baseline, repeats=repeats, seed=seed)

    merged = (
        signal_summary.merge(baseline_summary, on=[COL_BASIS, COL_HORIZON], suffixes=("", BASELINE_SUFFIX))
        .merge(
            cell_excess[
                [
                    COL_BASIS,
                    COL_HORIZON,
                    COL_MEAN_EXCESS,
                    COL_MEDIAN_EXCESS,
                    COL_WIN_RATE_EXCESS,
                    COL_LOSS_RATE_EXCESS,
                ]
            ],
            on=[COL_BASIS, COL_HORIZON],
        )
        .merge(
            cell_test[
                [
                    COL_BASIS,
                    COL_HORIZON,
                    COL_MEAN_P_VALUE,
                    COL_MEDIAN_P_VALUE,
                    COL_UP_RATE_P_VALUE,
                    COL_DOWN_RATE_P_VALUE,
                    COL_TEST_NOTE,
                ]
            ],
            on=[COL_BASIS, COL_HORIZON],
        )
    )
    merged[COL_MEAN_RATE_CONFLICT] = _mean_rate_conflict(merged)
    merged[COL_JUDGEABLE] = _judgeable(merged[COL_SAMPLE_COUNT])

    return merged.drop(columns=[COL_BASIS, COL_HORIZON])


def _judgeable(sample_counts: pd.Series) -> pd.Series:
    """표본이 하한을 넘는지로 `판정가능` 을 매긴다.

    표본이 모자란 칸도 **행은 남기고** 이 컬럼으로 「판정에 쓰지 말라」를 표에 적는다
    (측정의 원칙 17). 행이 사라지면 그 칸을 못 봤다는 사실 자체를 사용자가 모른다.

    Args:
        sample_counts: 칸별 유효 표본 수

    Returns:
        「예」/「아니오」 문자열 Series
    """
    return sample_counts.map(lambda count: JUDGEABLE_YES if count >= MIN_SAMPLE_PER_CELL else JUDGEABLE_NO)


def _identify(frame: pd.DataFrame, **values: Any) -> pd.DataFrame:
    """식별 컬럼을 표 앞에 붙인다.

    **`report` 가 아니라 실행 계층이 붙인다** — 출력 계층은 어떤 검증이 자기를 쓰는지 몰라야
    하므로 검증별 컬럼을 알 수 없다 (계층 간 계약).

    Args:
        frame: 식별자를 붙일 표
        **values: 컬럼 이름과 값

    Returns:
        식별 컬럼이 앞에 붙은 새 DataFrame

    Raises:
        RuntimeError: 표가 비어 있는 경우 (내부 불변조건 위반)
    """
    if frame.empty:
        raise RuntimeError(f"내부 불변조건 위반: 식별자를 붙일 표가 비어 있습니다 (식별자: {values})")

    identified = frame.copy()
    for column, value in reversed(list(values.items())):
        identified.insert(0, column, value)

    return identified


def _period_masks(signal: pd.DataFrame, last_date: pd.Timestamp) -> list[tuple[str, pd.Series]]:
    """시기 구분마다 (이름, 신호 마스크) 를 만든다 (측정의 원칙 17).

    **균등 2분할이 판정용이고 최근 N년은 관찰용이다.** 균등 분할은 칸당 표본 하한을 지키지만
    「식고 있는가」를 놓치므로 최근 구간을 함께 낸다. **관찰용만으로 칸을 떨어뜨리지 않는다** —
    판정용에서 이미 무너진 칸을 확인하는 데에만 쓴다.

    **「최근 N년」의 기준일은 실행 시각이 아니라 데이터의 마지막 거래일이다.**
    실행 시각을 쓰면 코드를 안 고쳐도 날짜가 지나면 결과가 바뀌어 재현되지 않는다.

    Args:
        signal: 신호군 long-form (유효 행). 시간순 정렬을 전제한다
        last_date: 데이터의 마지막 거래일

    Returns:
        (시기 이름, 신호 마스크) 목록. 신호가 없으면 빈 목록
    """
    if signal.empty:
        return []

    dates = signal[COL_DATE]
    boundary = dates.iloc[len(signal) // 2]

    masks = [
        (DISPLAY_PERIOD_EARLY, dates < boundary),
        (DISPLAY_PERIOD_LATE, dates >= boundary),
    ]
    for years in RECENT_WINDOWS_YEARS:
        cutoff = last_date - pd.DateOffset(years=years)
        masks.append((DISPLAY_PERIOD_RECENT.format(years=years), dates > cutoff))

    return masks


def _split_by_period(
    signal: pd.DataFrame,
    baseline: pd.DataFrame,
    last_date: pd.Timestamp,
    *,
    repeats: int,
    seed: int,
) -> pd.DataFrame:
    """시기 구분마다 집계 한 행씩을 낸다.

    **표본이 하한에 못 미쳐도 행을 지우지 않는다** (측정의 원칙 17). 0건이어도 행을 남기고
    지표를 비운 뒤 `판정가능` 을 「아니오」로 적는다 — 행이 사라지면 그 구간을 못 봤다는 사실
    자체를 사용자가 모른다. **0 으로 채우는 것도 금지다**(「손실도 이익도 없었다」로 읽힌다).

    Args:
        signal: 신호군 long-form (유효 행)
        baseline: 기준선 long-form (유효 행)
        last_date: 데이터의 마지막 거래일
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        시기별 집계. 구간마다 **반드시 한 행**이다
    """
    blocks: list[pd.DataFrame] = []
    baseline_dates = baseline[COL_DATE]

    for label, signal_mask in _period_masks(signal, last_date):
        period_signal = signal[signal_mask]
        period_baseline = baseline[_matching_baseline_mask(baseline_dates, signal, signal_mask, last_date, label)]

        block = _aggregate(period_signal, period_baseline, repeats=repeats, seed=seed)
        if block.empty:
            # 신호가 하나도 없는 구간이다. **행을 지우지 않고 지표만 비운다.**
            # 표본 수는 0 이 사실이므로 적는다 (측정의 원칙 3)
            block = pd.DataFrame({COL_SAMPLE_COUNT: [0], COL_JUDGEABLE: [JUDGEABLE_NO]})

        blocks.append(_identify(block, **{COL_PERIOD: label}))

    if not blocks:
        return pd.DataFrame()

    return pd.concat(blocks, ignore_index=True)


def _matching_baseline_mask(
    baseline_dates: pd.Series,
    signal: pd.DataFrame,
    signal_mask: pd.Series,
    last_date: pd.Timestamp,
    label: str,
) -> pd.Series:
    """신호 구간과 **같은 기간**의 기준선을 고른다.

    기간을 맞추지 않으면 기준선 대비 차이에 「그 사이 시장이 어땠는가」가 섞인다.

    Args:
        baseline_dates: 기준선의 날짜
        signal: 신호군 long-form (유효 행)
        signal_mask: 이 구간의 신호 마스크
        last_date: 데이터의 마지막 거래일
        label: 시기 이름

    Returns:
        기준선 행 마스크
    """
    selected = signal.loc[signal_mask, COL_DATE]
    if selected.empty:
        return pd.Series(False, index=baseline_dates.index)

    # 최근 N년 구간은 경계가 달력이므로 그대로 쓰고, 균등 분할은 신호의 실제 구간을 쓴다
    for years in RECENT_WINDOWS_YEARS:
        if label == DISPLAY_PERIOD_RECENT.format(years=years):
            return baseline_dates > last_date - pd.DateOffset(years=years)

    return (baseline_dates >= selected.min()) & (baseline_dates <= selected.max())


def _judging_periods(periods: pd.DataFrame) -> pd.DataFrame:
    """후보 판정의 시기 항목이 읽을 행만 남긴다 (측정의 원칙 17).

    **관찰용 최근 구간을 빼는 것이 이 함수의 존재 이유다.** 최근 구간은 기간이 짧아 표본이 적고,
    그것으로 판정하면 **결과를 보고 구간을 고르는 것과 구별되지 않는다.** 판정은 균등 분할로만
    하고, 최근 구간은 판정용에서 이미 무너진 칸의 크기를 확인하는 데에만 쓴다.

    산출물에는 네 구간이 모두 남으므로 이 필터가 정보를 지우지는 않는다.

    Args:
        periods: 시기 분해 표

    Returns:
        균등 분할 행만 남긴 표
    """
    if periods.empty:
        return periods

    return periods[periods[COL_PERIOD].isin(JUDGING_PERIODS)]


def _aggregate_by_month(
    signal: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    repeats: int,
    seed: int,
) -> pd.DataFrame:
    """원 매매법 칸을 월(1~12)별로 쪼갠다.

    **구간 축을 월로 빌려 `summarize`·`excess`·`permutation_test` 를 재사용한다.**
    통계량 정의를 두 곳에서 구현하면 두 곳이 조용히 갈라지기 때문이다.

    **같은 달 기준선이 반드시 필요하다** — 계절성이 있는 달은 매매법과 무관하게 방향이 치우치므로,
    같은 달과 견주지 않으면 「그 달이 원래 그런 것」과 「그 달의 이 매매가 특별한 것」을 가를 수 없다.

    Args:
        signal: 신호군 long-form (유효 행)
        baseline: 기준선 long-form (유효 행)
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        월별 집계. 신호가 있는 달만 낸다
    """
    signal_by_month = signal.copy()
    signal_by_month[COL_HORIZON] = signal_by_month[COL_DATE].dt.month
    baseline_by_month = baseline.copy()
    baseline_by_month[COL_HORIZON] = baseline_by_month[COL_DATE].dt.month

    # 신호가 있는 달만 낸다. 기준선에만 있는 달을 남기면 초과분의 칸 구성이 어긋난다
    months = sorted(set(signal_by_month[COL_HORIZON].tolist()))
    baseline_by_month = baseline_by_month[baseline_by_month[COL_HORIZON].isin(months)]

    signal_summary = summarize(signal_by_month)
    if signal_summary.empty:
        return pd.DataFrame()

    baseline_summary = summarize(baseline_by_month)
    month_excess = excess(signal_summary, baseline_summary)
    month_test = permutation_test(signal_by_month, baseline_by_month, repeats=repeats, seed=seed)

    merged = (
        signal_summary.merge(baseline_summary, on=[COL_BASIS, COL_HORIZON], suffixes=("", BASELINE_SUFFIX))
        .merge(
            month_excess[
                [
                    COL_BASIS,
                    COL_HORIZON,
                    COL_MEAN_EXCESS,
                    COL_MEDIAN_EXCESS,
                    COL_WIN_RATE_EXCESS,
                    COL_LOSS_RATE_EXCESS,
                ]
            ],
            on=[COL_BASIS, COL_HORIZON],
        )
        .merge(
            month_test[
                [
                    COL_BASIS,
                    COL_HORIZON,
                    COL_MEAN_P_VALUE,
                    COL_MEDIAN_P_VALUE,
                    COL_UP_RATE_P_VALUE,
                    COL_DOWN_RATE_P_VALUE,
                    COL_TEST_NOTE,
                ]
            ],
            on=[COL_BASIS, COL_HORIZON],
        )
    )
    merged[COL_MEAN_RATE_CONFLICT] = _mean_rate_conflict(merged)
    merged[COL_JUDGEABLE] = _judgeable(merged[COL_SAMPLE_COUNT])

    return merged.rename(columns={COL_HORIZON: COL_MONTH_NUMBER}).drop(columns=[COL_BASIS])


def _aggregate_month_halves(
    signal: pd.DataFrame,
    baseline: pd.DataFrame,
    last_date: pd.Timestamp,
    *,
    repeats: int,
    seed: int,
) -> pd.DataFrame:
    """월별로 신호를 시기 구분마다 갈라 방향 비율을 낸다.

    후보 판정의 **시기 항목**(시기를 쪼개도 방향이 유지되는가)을 재는 축이다.
    표본이 모자란 구간도 행을 남긴다 (측정의 원칙 17).

    Args:
        signal: 신호군 long-form (유효 행)
        baseline: 기준선 long-form (유효 행)
        last_date: 데이터의 마지막 거래일
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        월 × 시기 집계
    """
    blocks: list[pd.DataFrame] = []

    for month in sorted(set(signal[COL_DATE].dt.month.tolist())):
        month_signal = signal[signal[COL_DATE].dt.month == month].sort_values(COL_DATE)
        month_baseline = baseline[baseline[COL_DATE].dt.month == month]

        split = _split_by_period(month_signal, month_baseline, last_date, repeats=repeats, seed=seed)
        if not split.empty:
            blocks.append(_identify(split, **{COL_MONTH_NUMBER: month}))

    if not blocks:
        return pd.DataFrame()

    return pd.concat(blocks, ignore_index=True)


def _run_dataset(dataset: Dataset, accumulator: _Accumulator, *, repeats: int, seed: int) -> dict[str, Any]:
    """대상 하나를 격자 전체로 돌린다.

    Args:
        dataset: 검증 대상 정의
        accumulator: 결과를 쌓는 자리
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        이 대상의 요약 수치
    """
    df = _load(dataset)
    trading_days = pd.DatetimeIndex(df[COL_DATE])
    last_date = trading_days[-1]
    identity = {COL_TICKER: dataset.ticker}

    grid_blocks: list[pd.DataFrame] = []
    period_blocks: list[pd.DataFrame] = []
    base_record: dict[str, Any] = {}

    for calendar_day in ENTRY_CALENDAR_DAYS:
        for exit_offset in EXIT_OFFSETS:
            cell = grid_cell_label(calendar_day, exit_offset)
            cell_identity = {COL_GRID_CELL: cell, COL_TARGET_DAY: calendar_day, COL_OFFSET: exit_offset}

            signal, baseline = _frames(df, dataset, calendar_day, exit_offset)
            valid_signal = _valid(signal)
            valid_baseline = _valid(baseline)

            block = _aggregate(valid_signal, valid_baseline, repeats=repeats, seed=seed)
            if block.empty:
                logger.warning(f"{dataset.ticker} {cell}: 유효 신호가 0건이라 집계에서 빠집니다")
                continue

            grid_blocks.append(_identify(block, **cell_identity))

            periods = _split_by_period(valid_signal, valid_baseline, last_date, repeats=repeats, seed=seed)
            if not periods.empty:
                period_blocks.append(_identify(periods, **cell_identity))

            # 월별 분해와 원자료는 **원 매매법 칸에서만** 낸다 (§3.7)
            if calendar_day == BASE_ENTRY_DAY and exit_offset == BASE_EXIT_OFFSET:
                base_record = _run_base_cell(
                    df,
                    dataset,
                    signal,
                    valid_signal,
                    valid_baseline,
                    last_date,
                    accumulator,
                    repeats=repeats,
                    seed=seed,
                )

    if grid_blocks:
        grid = pd.concat(grid_blocks, ignore_index=True)
        cell_periods = pd.concat(period_blocks, ignore_index=True) if period_blocks else pd.DataFrame()

        accumulator.grid.append(_identify(grid, **identity))
        if not cell_periods.empty:
            accumulator.periods.append(_identify(cell_periods, **identity))

        # **시기표는 같은 대상의 것만 넘긴다.** 다른 대상의 행이 섞이면 한 칸의 시기 항목이
        # 남의 시기로 판정된다
        accumulator.grid_candidates.append(
            _identify(
                screen_candidates(grid, _judging_periods(cell_periods), axis_column=COL_GRID_CELL),
                **identity,
            )
        )

    return {
        KEY_TICKER: dataset.ticker,
        KEY_LABEL: dataset.label,
        KEY_FILE: dataset.path.name,
        KEY_IS_INDEX: dataset.is_index,
        KEY_ROWS: len(df),
        KEY_PERIOD: f"{trading_days[0].date()} ~ {last_date.date()}",
        **base_record,
    }


def _run_base_cell(
    df: pd.DataFrame,
    dataset: Dataset,
    signal: pd.DataFrame,
    valid_signal: pd.DataFrame,
    valid_baseline: pd.DataFrame,
    last_date: pd.Timestamp,
    accumulator: _Accumulator,
    *,
    repeats: int,
    seed: int,
) -> dict[str, Any]:
    """원 매매법 칸(20일 → 말일)의 원자료·월별 분해·후보 판정을 낸다.

    Args:
        df: 가격 데이터
        dataset: 검증 대상 정의
        signal: 신호군 long-form (제외 행 포함)
        valid_signal: 유효 행만
        valid_baseline: 기준선 유효 행
        last_date: 데이터의 마지막 거래일
        accumulator: 결과를 쌓는 자리
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        요약에 담을 수치
    """
    identity = {COL_TICKER: dataset.ticker}

    # 신호일 원자료. 진입·청산 가격과 날짜를 전부 남겨 사용자가 차트로 대조한다 (측정의 원칙 8)
    raw = signal.drop(columns=[COL_BASIS, COL_HORIZON]).copy()
    raw[[COL_ENTRY_CLOSE, COL_EXIT_CLOSE]] = raw[[COL_ENTRY_CLOSE, COL_EXIT_CLOSE]].round(dataset.price_decimals)
    accumulator.trades.append(_identify(raw, **identity))

    halves = _aggregate_month_halves(valid_signal, valid_baseline, last_date, repeats=repeats, seed=seed)
    if not halves.empty:
        accumulator.month_halves.append(_identify(halves, **identity))

    by_month = _aggregate_by_month(valid_signal, valid_baseline, repeats=repeats, seed=seed)
    if not by_month.empty:
        accumulator.months.append(_identify(by_month, **identity))
        accumulator.month_candidates.append(
            _identify(
                screen_candidates(by_month, _judging_periods(halves), axis_column=COL_MONTH_NUMBER),
                **identity,
            )
        )

    # 이웃 달력일과 같은 거래일로 수렴한 달의 수 (결정 ⑥). 격자 칸이 독립이 아니라는 근거값이다
    trading_days = pd.DatetimeIndex(df[COL_DATE])
    base_entries = month_entry_dates(trading_days, calendar_day=BASE_ENTRY_DAY)
    neighbour = month_entry_dates(trading_days, calendar_day=BASE_ENTRY_DAY - 1)

    return {
        KEY_ENTRY_COUNT: len(signal),
        KEY_EXCLUDED_COUNT: len(signal) - len(valid_signal),
        KEY_HOLD_DAYS: _hold_day_counts(valid_signal),
        KEY_BASELINE_ENTRY_COUNT: len(valid_baseline),
        KEY_CONVERGED: converged_month_count(base_entries, neighbour),
    }


def _hold_day_counts(frame: pd.DataFrame) -> dict[str, int]:
    """보유 거래일수 분포를 센다.

    Args:
        frame: 유효 신호군

    Returns:
        보유일수별 건수
    """
    counts = frame[COL_HOLD_DAYS].value_counts().sort_index()

    return {str(days): int(count) for days, count in counts.items()}


def run_study(
    datasets: tuple[Dataset, ...] = DATASETS,
    *,
    repeats: int = DEFAULT_REPEAT_COUNT,
    seed: int = DEFAULT_RANDOM_SEED,
) -> StudyOutputs:
    """검증 #10 을 실행하고 산출물을 조립한다.

    Args:
        datasets: 검증 대상 목록
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        실행 산출물

    Raises:
        ValueError: 대상 목록이 빈 경우
    """
    if not datasets:
        raise ValueError("검증 대상이 하나도 없습니다")

    accumulator = _Accumulator()
    dataset_summaries = [_run_dataset(dataset, accumulator, repeats=repeats, seed=seed) for dataset in datasets]

    summary: dict[str, Any] = {
        KEY_PERMUTATION_REPEATS: repeats,
        KEY_PERMUTATION_SEED: seed,
        KEY_GRID: {
            KEY_ENTRY_DAYS: list(ENTRY_CALENDAR_DAYS),
            KEY_EXIT_OFFSETS: list(EXIT_OFFSETS),
        },
        KEY_DATASETS: dataset_summaries,
    }

    tables = {
        "trades": _concat(accumulator.trades),
        "grid": _concat(accumulator.grid),
        "months": _concat(accumulator.months),
        "month_halves": _concat(accumulator.month_halves),
        "periods": _concat(accumulator.periods),
        "grid_candidates": _concat(accumulator.grid_candidates),
        "month_candidates": _concat(accumulator.month_candidates),
    }

    # **요약을 먼저 완성한 뒤 산출물을 만든다.** 만들고 나서 그 안의 dict 를 고치면
    # 동작은 하지만 `frozen` 이 막으려던 것을 우회하게 된다
    summary[KEY_ROW_COUNTS] = {name: len(table) for name, table in tables.items()}

    return StudyOutputs(**tables, summary=summary)


def display_tables(outputs: StudyOutputs) -> dict[str, pd.DataFrame]:
    """저장할 표를 전부 표시용(한글 헤더·백분율)으로 바꾼다.

    **터미널과 CSV 가 같은 프레임을 쓴다.** 따로 가공하면 반올림 시점이 갈려 화면에서 본 숫자를
    CSV 에서 찾지 못한다 — 사용자가 직접 대조하는 것이 이 프로젝트의 전제다.

    후보 판정표는 `report.tables.build_candidates_table` 이 자기 규격을 갖고 있어 그것을 쓴다.

    Args:
        outputs: 실행 산출물

    Returns:
        파일 이름 → 표시용 DataFrame
    """
    tables: dict[str, pd.DataFrame] = {}

    for name, table in (
        ("trades", outputs.trades),
        ("grid", outputs.grid),
        ("months", outputs.months),
        ("month_halves", outputs.month_halves),
        ("periods", outputs.periods),
    ):
        if not table.empty:
            tables[name] = _display(table)

    for name, table, axis_column, axis_label in (
        ("grid_candidates", outputs.grid_candidates, COL_GRID_CELL, DISPLAY_GRID_CELL),
        ("month_candidates", outputs.month_candidates, COL_MONTH_NUMBER, DISPLAY_MONTH_NUMBER),
    ):
        if not table.empty:
            identified = table.drop(columns=[COL_TICKER])
            built = build_candidates_table(identified, axis_column=axis_column, axis_label=axis_label)
            built.insert(0, DISPLAY_TICKER, table[COL_TICKER].to_numpy())
            tables[name] = built

    return tables


def _display(table: pd.DataFrame) -> pd.DataFrame:
    """표 하나를 표시용으로 바꾼다.

    변환 대상 컬럼은 **그 표에 실제로 있는 것만** 넘긴다 — 표마다 컬럼 구성이 다르고,
    없는 컬럼을 지목하면 출력 계층이 거부한다.

    Args:
        table: 저장할 표 (영문 헤더)

    Returns:
        한글 헤더에 단위가 맞춰진 표
    """
    percent = [column for column in PERCENT_COLUMNS if column in table.columns]
    probability = [column for column in PROBABILITY_COLUMNS if column in table.columns]

    return to_display_columns(table, COLUMN_LABELS, percent_columns=percent, probability_columns=probability)


def base_cell_headline(grid_display: pd.DataFrame) -> pd.DataFrame:
    """원 매매법 칸(20일 → 말일)의 대상별 성적만 뽑는다.

    격자 77칸을 화면에 다 내면 읽을 수 없다. **사용자가 물은 것은 이 칸**이고,
    나머지는 「왜 하필 20일인가」에 답하는 보조라 CSV 가 담당한다.

    **표시용 프레임을 받는다** — 화면과 CSV 가 같은 값을 보여야 하므로 따로 가공하지 않는다.

    Args:
        grid_display: `display_tables` 가 만든 격자 표

    Returns:
        원 매매법 칸의 대상별 한 줄. 격자가 비었으면 빈 표
    """
    if grid_display.empty:
        return grid_display

    base = grid_display[
        (grid_display[DISPLAY_TARGET_DAY] == BASE_ENTRY_DAY) & (grid_display[DISPLAY_EXIT_OFFSET] == BASE_EXIT_OFFSET)
    ]

    return base.reset_index(drop=True)


def candidates_headline(candidates_display: pd.DataFrame) -> pd.DataFrame:
    """**후보 칸만** 적중률 내림차순으로 뽑는다.

    제외된 칸은 산출물에 그대로 남기되 화면에는 내지 않는다 — 화면은 "지금 볼 것"을 위한
    자리이고, 전 칸은 판정 CSV 가 격자 순서로 답한다.

    **정렬이 여기 있는 이유**: 판정 계층(`measure`)은 축을 모르므로 무엇을 먼저 보여줄지
    정할 수 없다. 동률이 흔해(적중률이 표본의 분수라 값이 겹친다) **안정 정렬**을 써서
    같은 적중률 안에서는 대상·칸 순서가 유지되게 한다.

    Args:
        candidates_display: `display_tables` 가 만든 판정표

    Returns:
        후보 칸만 남긴 판정표. 하나도 없으면 빈 표
    """
    if candidates_display.empty:
        return candidates_display

    selected = candidates_display[candidates_display[DISPLAY_SCREEN] == SCREEN_CANDIDATE]

    return selected.sort_values(DISPLAY_HIT_RATE, ascending=False, kind="stable").reset_index(drop=True)


def _concat(blocks: list[pd.DataFrame]) -> pd.DataFrame:
    """모아둔 표 조각을 하나로 잇는다.

    Args:
        blocks: 표 조각 목록

    Returns:
        이어붙인 DataFrame (조각이 없으면 빈 DataFrame)
    """
    if not blocks:
        return pd.DataFrame()

    return pd.concat(blocks, ignore_index=True)


__all__ = [
    "StudyOutputs",
    "base_cell_headline",
    "candidates_headline",
    "display_tables",
    "grid_cell_label",
    "run_study",
]
