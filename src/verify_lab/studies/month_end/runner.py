"""월말 진입 측정 실행 — 확정 칸의 해석 재료를 한 장으로 낸다

**계산하지 않는다.** 이벤트 정의(`schedule`)와 측정(`measure`)을 조합해 돌리고, 어느 행이
어떤 칸의 결과인지를 붙이기만 한다.

**산출물은 `측정.csv` 한 장이다.** 성적표가 「걸 만한가」에 답한다면 이 표는
**「그 값을 어떻게 읽나」**에 답한다 — 중앙값(측정의 원칙 4) · 평균-비율 어긋남(원칙 13) ·
기준선 · 우연확률 · 배당락(원칙 14)이 성적표에는 하나도 없고 여기가 유일한 자리다.

**축은 「종목 × 월 × 방향」이고 확정 칸마다 한 행이다.** 성적표의 `시기 = 전체` 행과 1:1 로
조인되며, 그래서 식별 컬럼의 이름이 성적표와 같다.

[중요] **값은 1배 롱 기준 그대로다.** 「아래」 칸이라고 부호를 뒤집지 않는다 — 뒤집으면
`기준선 오른 비율` 이 실제로는 내린 비율을 가리켜 **이름이 거짓이 된다.** `방향` 은 표시일
뿐이며, 그래서 **성적표의 평균과 이 표의 평균은 부호가 다를 수 있고 대조 대상이 아니다.**

**기준선은 「그 달 아무 날 진입」 하나다**(설계 결정 ⑤). 신호와 **같은 함수**로 만들어
진입일 목록만 전 거래일로 바꾼다 — 따로 구현하면 두 계산이 조용히 갈라진다.
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from verify_lab.common_constants import ADJUSTED_FILE_TEMPLATE, COL_CLOSE, COL_DATE
from verify_lab.data.loader import load_market_csv, load_series_csv
from verify_lab.measure.calendar_entry import every_day_entries, month_entry_dates
from verify_lab.measure.calendar_exit import month_exit_returns, month_exit_schedule
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_DIVIDEND_HIT_COUNT,
    COL_DIVIDEND_MEAN_IMPACT,
    COL_DIVIDEND_MEASURED,
    COL_EXCLUDED_REASON,
    COL_EXIT_DATE,
    COL_HOLD_DAYS,
    COL_HORIZON,
    COL_JUDGEABLE,
    COL_MEAN_RATE_CONFLICT,
    DIVIDEND_IMPACT_DECIMALS,
    REASON_NONE,
)
from verify_lab.measure.distribution import dividend_impact
from verify_lab.measure.screening import COL_DIRECTION, DIRECTION_DOWN, DIRECTION_UP
from verify_lab.measure.statistics import (
    COL_DOWN_RATE_P_VALUE,
    COL_LOSS_RATE_EXCESS,
    COL_MEAN_EXCESS,
    COL_MEAN_P_VALUE,
    COL_MEDIAN_EXCESS,
    COL_MEDIAN_P_VALUE,
    COL_SAMPLE_COUNT,
    COL_TEST_NOTE,
    COL_UP_RATE_P_VALUE,
    COL_WIN_RATE_EXCESS,
    DEFAULT_RANDOM_SEED,
    DEFAULT_REPEAT_COUNT,
    excess,
    judgeable,
    mean_rate_conflict,
    permutation_test,
    summarize,
)
from verify_lab.report.run_summary import KEY_TRACK, dataset_record
from verify_lab.report.tables import to_display_columns
from verify_lab.studies.month_end.constants import (
    BASE_ENTRY_DAY,
    BASE_EXIT_OFFSET,
    BASELINE_SUFFIX,
    COL_MONTH_NUMBER,
    COL_TICKER,
    COLUMN_LABELS,
    DATASETS,
    EXECUTION_ROLE_DOWN,
    HORIZON_MONTH_END,
    KEY_CELL_DIRECTION,
    KEY_CELL_MONTH,
    KEY_CELLS,
    KEY_ENTRY_COUNT,
    KEY_EXCLUDED_COUNT,
    OUTPUT_FILES,
    PERCENT_COLUMNS,
    PROBABILITY_COLUMNS,
    TRACK_NAME,
    TRADING_CELLS,
    Dataset,
    MonthEndCell,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 산출물 필드 이름. `OUTPUT_FILES` 가 이 이름을 파일 이름으로 잇는다
FIELD_MEASURE = "measure"

# `summary.json` 의 키
KEY_PERMUTATION_REPEATS = "permutation_repeats"
KEY_PERMUTATION_SEED = "permutation_seed"
KEY_DATASETS = "datasets"
KEY_ROW_COUNTS = "row_counts"
# 데이터셋 한 줄의 공통 다섯 키는 **`report/run_summary.py` 가 소유한다.** 여기서 다시
# 정의하지 않는다 — 이름을 한 벌 더 두면 옛 경로가 살아남아 소유자를 옮겨도 검사가 통과한다
KEY_IS_INDEX = "is_index"
KEY_HOLD_DAYS = "hold_days"
KEY_BASELINE_ENTRY_COUNT = "baseline_entry_count"


@dataclass(frozen=True)
class StudyOutputs:
    """측정 산출물

    Attributes:
        measure: 확정 칸마다 한 행. 기준선·우연확률·배당락과 해석에 필요한 분포값이 들어 있다
        summary: 실행 요약
    """

    measure: pd.DataFrame
    summary: dict[str, Any]


@dataclass
class _Accumulator:
    """대상마다 나온 표 조각을 쌓는 자리"""

    measure: list[pd.DataFrame] = field(default_factory=list)


def cell_direction(cell: MonthEndCell) -> str:
    """칸의 방향 표기를 낸다.

    **`measure/screening.py` 의 값을 쓴다** — 방향 표기는 측정의 원칙 11 이 모든 매매법에
    요구하는 축이라 검증마다 문자열을 두면 산출물끼리 조인되지 않는다.

    Args:
        cell: 대상 칸

    Returns:
        「위」 또는 「아래」
    """
    return DIRECTION_DOWN if cell.bet_down else DIRECTION_UP


def _load(dataset: Dataset) -> pd.DataFrame:
    """대상의 가격 데이터를 읽는다.

    **ETF 와 지수는 로더가 다르다.** 지수는 종가 계열이라 시세 판정(0 이하 가격·급등락)을
    걸 수 없다 (`docs/매매/월말_진입/설계.md` §7.6).

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

    집계는 유효 표본으로만 한다. **제외 건수는 요약이 담당한다** —
    행을 지운 자리가 어디인지는 그쪽에서 읽는다.

    Args:
        frame: `month_exit_returns` 의 결과

    Returns:
        유효 행만 남긴 DataFrame
    """
    return frame[frame[COL_EXCLUDED_REASON] == REASON_NONE].copy()


def _frames(df: pd.DataFrame, dataset: Dataset) -> tuple[pd.DataFrame, pd.DataFrame]:
    """확정 칸(20일 → 말일)의 신호군과 기준선 long-form 을 만든다.

    **기준선은 진입일 목록만 다르고 나머지가 같다.** 같은 청산 규칙을 같은 함수로 적용하므로
    보유 길이 분포가 신호와 같은 달력 구조에서 나온다 (결정 ⑤).

    Args:
        df: 날짜 오름차순 가격 데이터
        dataset: 검증 대상 정의

    Returns:
        (신호군 long-form, 기준선 long-form). 제외 행을 포함한 전체다
    """
    trading_days = pd.DatetimeIndex(df[COL_DATE])

    signal_entries = month_entry_dates(trading_days, calendar_day=BASE_ENTRY_DAY)
    signal_schedule = month_exit_schedule(trading_days, signal_entries, exit_offset=BASE_EXIT_OFFSET)

    baseline_entries = every_day_entries(trading_days, calendar_day=BASE_ENTRY_DAY)
    baseline_schedule = month_exit_schedule(trading_days, baseline_entries, exit_offset=BASE_EXIT_OFFSET)

    signal = month_exit_returns(df, signal_schedule, horizon=HORIZON_MONTH_END, price_column=dataset.price_column)
    baseline = month_exit_returns(df, baseline_schedule, horizon=HORIZON_MONTH_END, price_column=dataset.price_column)

    return signal, baseline


def _judgeable(sample_counts: pd.Series) -> pd.Series:
    """표본이 하한을 넘는지로 `판정가능` 을 매긴다.

    표본이 모자란 칸도 **행은 남기고** 이 컬럼으로 「판정에 쓰지 말라」를 표에 적는다
    (측정의 원칙 17). 행이 사라지면 그 칸을 못 봤다는 사실 자체를 사용자가 모른다.

    Args:
        sample_counts: 칸별 유효 표본 수

    Returns:
        「예」/「아니오」 문자열 Series
    """
    return sample_counts.map(lambda count: judgeable(int(count)))


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


def _aggregate_by_month(
    signal: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    repeats: int,
    seed: int,
) -> pd.DataFrame:
    """확정 칸을 월(1~12)별로 쪼갠다.

    **구간 축을 월로 빌려 `summarize`·`excess`·`permutation_test` 를 재사용한다.**
    통계량 정의를 두 곳에서 구현하면 두 곳이 조용히 갈라지기 때문이다.

    **같은 달 기준선이 반드시 필요하다** — 계절성이 있는 달은 매매법과 무관하게 방향이 치우치므로,
    같은 달과 견주지 않으면 「그 달이 원래 그런 것」과 「그 달의 이 매매가 특별한 것」을 가를 수 없다.

    **확정 칸의 달만 남기지 않고 신호가 있는 달을 다 낸 뒤 고른다** — 기준선과 검정이 달 축
    전체에서 한 번에 나오므로, 미리 거르면 같은 계산을 칸마다 다시 돌게 된다.

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
    merged[COL_MEAN_RATE_CONFLICT] = mean_rate_conflict(merged)
    merged[COL_JUDGEABLE] = _judgeable(merged[COL_SAMPLE_COUNT])

    return merged.rename(columns={COL_HORIZON: COL_MONTH_NUMBER}).drop(columns=[COL_BASIS])


def _dividend_row(dataset: Dataset, valid_signal: pd.DataFrame, cell: MonthEndCell) -> dict[str, Any]:
    """그 칸의 보유 구간에 들어간 배당락을 잰다.

    **산식은 `measure/distribution.py` 가 소유한다** — 여기서 다시 계산하면 실측 스크립트와
    조용히 갈라진다 (패키지 절대 원칙 5).

    [중요] **지수는 비운다.** 지수는 상품이 아니라 계산값이라 분배금을 지급할 일이 없고
    수정주가 파일도 없다 (`scripts/data/check_month_end_dividend.py` 가 같은 이유로 지수를
    대상에서 뺀다). **0 으로 채우면 「안 걸림」과 「잴 수 없음」이 구별되지 않는다.**

    Args:
        dataset: 대상 종목
        valid_signal: 그 대상의 유효 신호 long-form
        cell: 대상 칸

    Returns:
        배당락 세 컬럼. 지수이거나 그 달의 체결이 없으면 값이 비어 있다

    Raises:
        ValueError: ETF 인데 수정주가 파일이 없는 경우
    """
    blank = {
        COL_DIVIDEND_MEASURED: pd.NA,
        COL_DIVIDEND_HIT_COUNT: pd.NA,
        COL_DIVIDEND_MEAN_IMPACT: np.nan,
    }

    if dataset.is_index:
        return blank

    month_rows = valid_signal[valid_signal[COL_DATE].dt.month == cell.month]

    # **0 으로 채우지 않는다.** 체결이 없는 것과 왜곡이 0 인 것은 다른 사실이다
    if month_rows.empty:
        return blank

    adjusted_path = dataset.directory / ADJUSTED_FILE_TEMPLATE.format(ticker=dataset.ticker)
    if not adjusted_path.is_file():
        raise ValueError(f"배당락을 재려면 수정주가 파일이 필요합니다: {adjusted_path}")

    raw_close = load_market_csv(dataset.path).set_index(COL_DATE)[dataset.price_column]
    adjusted_close = load_market_csv(adjusted_path).set_index(COL_DATE)[COL_CLOSE]

    impact = dividend_impact(
        raw_close,
        adjusted_close,
        entry_dates=pd.DatetimeIndex(month_rows[COL_DATE]),
        exit_dates=pd.DatetimeIndex(month_rows[COL_EXIT_DATE]),
        # [중요] **칸의 방향이 아니라 «그 상품을 어떻게 잡는가»다.** 인버스 실물은 「아래」를
        # 그 상품을 **사서** 거는 것이라 자기 분배금은 롱과 똑같이 수익을 깎는다 — 칸의
        # 방향을 그대로 넘기면 부호가 뒤집혀 **왜곡의 방향이 반대로 적힌다.**
        # 지금은 두 인버스 모두 분배 이력이 0건이라 값이 0 이지만, 한 건이라도 생기면
        # 조용히 틀린 부호가 산출물에 실린다
        bet_down=cell.bet_down and dataset.execution_role != EXECUTION_ROLE_DOWN,
    )

    return {
        COL_DIVIDEND_MEASURED: impact.measured_count,
        COL_DIVIDEND_HIT_COUNT: impact.hit_count,
        # **여기서 반올림한다.** 이 값은 이미 %p 단위라 저장 계층의 비율→백분율 변환을 타지
        # 않고, 그대로 두면 `1.78e-05` 같은 과학적 표기로 CSV 에 실려 읽히지 않는다
        COL_DIVIDEND_MEAN_IMPACT: round(impact.mean_percent, DIVIDEND_IMPACT_DECIMALS),
    }


def _measure_block(dataset: Dataset, by_month: pd.DataFrame, valid_signal: pd.DataFrame) -> pd.DataFrame:
    """확정 칸마다 한 행을 만든다.

    **칸이 축이고 달이 아니다.** 같은 달을 두 방향으로 걸면 두 행이 되며, 그 구별은
    `방향` 컬럼이 한다.

    Args:
        dataset: 대상 종목
        by_month: 월별 집계
        valid_signal: 그 대상의 유효 신호 long-form

    Returns:
        칸마다 한 행인 표. 종목 컬럼은 호출 측이 붙인다
    """
    wanted = pd.DataFrame(
        [
            {
                COL_MONTH_NUMBER: cell.month,
                COL_DIRECTION: cell_direction(cell),
                **_dividend_row(dataset, valid_signal, cell),
            }
            for cell in TRADING_CELLS
        ]
    )

    # **`how="left"` 다.** 확정 칸인데 그 달의 신호가 없으면 행이 조용히 사라지는 대신
    # 지표가 빈 채로 남는다 — 「잴 수 없었다」가 산출물에서 드러나야 한다 (표본 보존)
    merged = wanted.merge(by_month, on=COL_MONTH_NUMBER, how="left")

    missing = merged[merged[COL_MEAN_RATE_CONFLICT].isna()]
    if not missing.empty:
        logger.debug(f"{dataset.label}: 확정 칸의 달에 신호가 없습니다: {missing[COL_MONTH_NUMBER].tolist()}")

    # 배당락 세 컬럼을 맨 뒤로 보낸다 — 식별 축과 집계 사이에 끼면 표가 읽히지 않는다
    dividend_columns = [COL_DIVIDEND_MEASURED, COL_DIVIDEND_HIT_COUNT, COL_DIVIDEND_MEAN_IMPACT]
    ordered = [column for column in merged.columns if column not in dividend_columns] + dividend_columns

    return merged[ordered]


def _hold_day_counts(frame: pd.DataFrame) -> dict[str, int]:
    """보유 거래일수 분포를 센다.

    Args:
        frame: 유효 신호군

    Returns:
        보유일수별 건수
    """
    counts = frame[COL_HOLD_DAYS].value_counts().sort_index()

    return {str(days): int(count) for days, count in counts.items()}


def _run_dataset(dataset: Dataset, accumulator: _Accumulator, *, repeats: int, seed: int) -> dict[str, Any]:
    """대상 하나를 확정 칸으로 돌린다.

    Args:
        dataset: 검증 대상 정의
        accumulator: 결과를 쌓는 자리
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        이 대상의 요약 수치

    Raises:
        RuntimeError: 유효 신호가 없어 월별 집계를 만들 수 없는 경우 (내부 불변조건 위반)
    """
    df = _load(dataset)
    signal, baseline = _frames(df, dataset)
    valid_signal = _valid(signal)
    valid_baseline = _valid(baseline)

    # **요약의 모집단을 확정 칸에 맞춘다.** 집계는 달 축 전체로 돌지만 «내는 것»은 확정 칸
    # 한 행이므로, 진입·제외·보유일을 열두 달로 세면 체결 요약(확정 칸 기준)과 나란히 놓았을 때
    # **두 숫자가 다른 모집단을 가리킨다** — 「측정 287, 체결 23」이 그 모습이다
    wanted = {cell.month for cell in TRADING_CELLS}
    cell_signal = signal[signal[COL_DATE].dt.month.isin(wanted)]
    cell_valid = valid_signal[valid_signal[COL_DATE].dt.month.isin(wanted)]
    cell_baseline = valid_baseline[valid_baseline[COL_DATE].dt.month.isin(wanted)]

    by_month = _aggregate_by_month(valid_signal, valid_baseline, repeats=repeats, seed=seed)

    # **요약이 「정상으로 보이는 것」이 이 가드의 이유다.** 집계가 비면 측정 표가 통째로
    # 사라지는데 나머지 키는 멀쩡하므로 `summary.json` 만 봐서는 알 수 없다
    if by_month.empty:
        raise RuntimeError(f"내부 불변조건 위반: 월별 집계가 비어 확정 칸을 잴 수 없습니다: " f"{dataset.label} (유효 신호 {len(valid_signal)}건)")

    block = _measure_block(dataset, by_month, valid_signal)
    accumulator.measure.append(_identify(block, **{COL_TICKER: dataset.label}))

    return {
        # **공통 다섯 키가 먼저, 이 검증의 축이 뒤에 온다.** 축을 가운데 끼우면 같은 계약을
        # 따르는 여섯 요약 중 이것만 자리가 달라진다 — 순서를 공통 함수가 정하면 갈릴 수 없다
        **dataset_record(ticker=dataset.ticker, label=dataset.label, file=dataset.path.name, frame=df),
        KEY_IS_INDEX: dataset.is_index,
        KEY_ENTRY_COUNT: len(cell_signal),
        KEY_EXCLUDED_COUNT: len(cell_signal) - len(cell_valid),
        KEY_HOLD_DAYS: _hold_day_counts(cell_valid),
        KEY_BASELINE_ENTRY_COUNT: len(cell_baseline),
    }


def run_study(
    datasets: tuple[Dataset, ...] = DATASETS,
    *,
    repeats: int = DEFAULT_REPEAT_COUNT,
    seed: int = DEFAULT_RANDOM_SEED,
) -> StudyOutputs:
    """월말 진입 측정을 실행하고 산출물을 조립한다.

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

    measure = _concat(accumulator.measure)

    summary: dict[str, Any] = {
        KEY_PERMUTATION_REPEATS: repeats,
        KEY_PERMUTATION_SEED: seed,
        KEY_CELLS: [{KEY_CELL_MONTH: cell.month, KEY_CELL_DIRECTION: cell_direction(cell)} for cell in TRADING_CELLS],
        KEY_TRACK: TRACK_NAME,
        KEY_DATASETS: dataset_summaries,
    }

    # **요약을 먼저 완성한 뒤 산출물을 만든다.** 만들고 나서 그 안의 dict 를 고치면
    # 동작은 하지만 `frozen` 이 막으려던 것을 우회하게 된다
    # **키는 파일 이름이다.** `OUTPUT_FILES` 가 필드 이름과 파일 이름을 잇는다
    summary[KEY_ROW_COUNTS] = {OUTPUT_FILES[FIELD_MEASURE]: len(measure)}

    logger.debug(f"측정 완료: {len(measure):,}행 (대상 {len(datasets)}개 × 확정 칸 {len(TRADING_CELLS)}개)")

    return StudyOutputs(measure=measure, summary=summary)


def display_tables(outputs: StudyOutputs) -> dict[str, pd.DataFrame]:
    """저장할 표를 표시용(한글 헤더·백분율)으로 바꾼다.

    **터미널과 CSV 가 같은 프레임을 쓴다.** 따로 가공하면 반올림 시점이 갈려 화면에서 본 숫자를
    CSV 에서 찾지 못한다 — 사용자가 직접 대조하는 것이 이 프로젝트의 전제다.

    Args:
        outputs: 실행 산출물

    Returns:
        산출물 필드 이름 → 표시용 DataFrame
    """
    if outputs.measure.empty:
        return {}

    return {FIELD_MEASURE: _display(outputs.measure)}


def _display(table: pd.DataFrame) -> pd.DataFrame:
    """표 하나를 표시용으로 바꾼다.

    변환 대상 컬럼은 **그 표에 실제로 있는 것만** 넘긴다 — 없는 컬럼을 지목하면 출력 계층이 거부한다.

    Args:
        table: 저장할 표 (영문 헤더)

    Returns:
        한글 헤더에 단위가 맞춰진 표
    """
    percent = [column for column in PERCENT_COLUMNS if column in table.columns]
    probability = [column for column in PROBABILITY_COLUMNS if column in table.columns]

    return to_display_columns(table, COLUMN_LABELS, percent_columns=percent, probability_columns=probability)


def _concat(blocks: list[pd.DataFrame]) -> pd.DataFrame:
    """모아둔 표 조각을 하나로 잇는다.

    Args:
        blocks: 표 조각 목록

    Returns:
        이어 붙인 표. 조각이 없으면 빈 DataFrame
    """
    if not blocks:
        return pd.DataFrame()

    return pd.concat(blocks, ignore_index=True)


__all__ = ["FIELD_MEASURE", "StudyOutputs", "cell_direction", "display_tables", "run_study"]
