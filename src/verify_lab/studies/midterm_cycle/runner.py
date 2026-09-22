"""중간선거_사이클 측정 조립 — 사이클 위치 네 칸을 한 장으로 낸다

**계산하지 않는다.** 달력은 `cycle_calendar`, 통계는 `measure/statistics`,
배당락은 `measure/distribution` 이 소유하고 여기서는 조립만 한다.

**축은 (종목 × 사이클 위치) 하나이고 `방향` 은 식별 «라벨»로 붙는다.** 값은 1배 롱 기준
그대로이며 부호를 뒤집지 않는다 — 뒤집으면 `기준선 오른 비율` 이 실제로는 내린 비율을
가리켜 이름이 거짓이 된다.

**기준선은 「그 사이클 해에 아무 달 첫 거래일 진입」이다.** 청산 규칙은 신호와 같다
(진입 달 + 8개월의 마지막 거래일). 그래서 이 대조가 답하는 것은
**「그 해가 원래 그런가, 아니면 10월 진입이 특별한가」**다.

[중요] **사이클 네 칸 대조와 이 기준선은 다른 질문이다.**

| 무엇 | 답하는 것 |
| --- | --- |
| **축** (사이클 위치 네 칸) | 「10~6월이라 좋았나, 중간선거 뒤라 좋았나」 — 달력 효과를 분리한다 |
| **기준선 컬럼** | 「그 해 아무 달에 9개월 들어도 같은가」 — 진입 달의 특별함을 묻는다 |

둘 다 **판정에 쓰지 않는다** (루트 `CLAUDE.md` 「기준선은 탈락 사유가 아니다」).
게이트는 회당 기대값 하나뿐이고, 이 값들은 사용자가 읽는 해석 재료다.
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from verify_lab.common_constants import ADJUSTED_FILE_TEMPLATE, COL_CLOSE, COL_DATE
from verify_lab.data.loader import load_market_csv, load_series_csv
from verify_lab.execution.trade_fill import resolve_positions
from verify_lab.measure.constants import (
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
    COL_BASIS,
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
    max_non_overlapping,
    mean_rate_conflict,
    permutation_test,
    summarize,
)
from verify_lab.report.run_summary import KEY_TRACK, dataset_record
from verify_lab.report.tables import to_display_columns
from verify_lab.studies.midterm_cycle.constants import (
    BASELINE_SUFFIX,
    BET_DOWN,
    COL_BASELINE_NON_OVERLAPPING,
    COL_CYCLE_POSITION,
    COL_NON_OVERLAPPING,
    COL_TICKER,
    COLUMN_LABELS,
    CYCLE_POSITIONS,
    DATASETS,
    ENTRY_MONTH,
    EXIT_MONTH,
    EXIT_MONTH_OFFSET,
    FIELD_STATISTICS,
    HORIZON_POOLED,
    KEY_ENTRY_COUNT,
    KEY_ENTRY_MONTH,
    KEY_EXCLUDED_COUNT,
    KEY_EXIT_MONTH,
    KEY_POSITIONS,
    OUTPUT_FILES,
    PERCENT_COLUMNS,
    PROBABILITY_COLUMNS,
    TRACK_NAME,
    Dataset,
)
from verify_lab.studies.midterm_cycle.cycle_calendar import (
    cycle_returns,
    month_first_entries,
    month_offset_exit_schedule,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

KEY_PERMUTATION_REPEATS = "permutation_repeats"
KEY_PERMUTATION_SEED = "permutation_seed"
KEY_DATASETS = "datasets"
KEY_ROW_COUNTS = "row_counts"
KEY_IS_INDEX = "is_index"

# 조회 심볼. 지수는 파일명(`GSPC`)과 다르므로(`^GSPC`) 따로 남긴다
KEY_SYMBOL = "symbol"


@dataclass(frozen=True)
class StudyOutputs:
    """측정 산출물

    Attributes:
        statistics: (종목 × 사이클 위치) 마다 한 행. 기준선·차이·우연확률·배당락이 들어 있다
        summary: 실행 요약
    """

    statistics: pd.DataFrame
    summary: dict[str, Any]


@dataclass
class _Accumulator:
    """대상마다 나온 표 조각을 쌓는 자리"""

    statistics: list[pd.DataFrame] = field(default_factory=list)


def load_dataset(dataset: Dataset) -> pd.DataFrame:
    """대상의 가격 데이터를 읽는다.

    **측정과 체결이 같은 함수를 쓴다** — 같은 패키지 안에 두 벌을 두면 ETF·지수 분기가
    갈릴 수 있고, 그러면 한 매매법의 두 계층이 다른 스키마를 보게 된다.

    Args:
        dataset: 검증 대상 정의

    Returns:
        날짜 오름차순 가격 DataFrame
    """
    if dataset.is_index:
        return load_series_csv(dataset.path)

    return load_market_csv(dataset.path)


def signal_returns(df: pd.DataFrame, dataset: Dataset) -> pd.DataFrame:
    """신호(10월 첫 거래일 진입)의 long-form 수익률을 낸다.

    **측정과 체결이 이 함수를 함께 쓴다** — 진입일 정의를 두 벌 만들면 두 계층이
    다른 날에 들어간다.

    Args:
        df: 날짜 오름차순 가격 데이터
        dataset: 검증 대상 정의

    Returns:
        `CYCLE_RETURN_COLUMNS` 구성의 long-form. 제외된 진입도 행으로 남는다
    """
    trading_days = pd.DatetimeIndex(df[COL_DATE])
    entries = month_first_entries(trading_days, month=ENTRY_MONTH)
    schedule = month_offset_exit_schedule(trading_days, entries, month_offset=EXIT_MONTH_OFFSET)

    return cycle_returns(df, schedule, horizon=HORIZON_POOLED, price_column=dataset.price_column)


def _baseline_returns(df: pd.DataFrame, dataset: Dataset) -> pd.DataFrame:
    """기준선(아무 달 첫 거래일 진입)의 long-form 수익률을 낸다.

    **청산 규칙이 신호와 같다** — 진입 달 + 8개월의 마지막 거래일이다. 달리하면 보유 길이가
    어긋나 그 차이가 그대로 기준선 대비 차이와 우연확률에 실린다.

    Args:
        df: 날짜 오름차순 가격 데이터
        dataset: 검증 대상 정의

    Returns:
        `CYCLE_RETURN_COLUMNS` 구성의 long-form
    """
    trading_days = pd.DatetimeIndex(df[COL_DATE])
    entries = month_first_entries(trading_days)
    schedule = month_offset_exit_schedule(trading_days, entries, month_offset=EXIT_MONTH_OFFSET)

    return cycle_returns(df, schedule, horizon=HORIZON_POOLED, price_column=dataset.price_column)


def _valid(frame: pd.DataFrame) -> pd.DataFrame:
    """제외되지 않은 행만 남긴다.

    집계는 유효 표본으로만 한다. **제외 건수는 요약이 담당한다.**

    Args:
        frame: `cycle_returns` 의 결과

    Returns:
        유효 행만 남긴 DataFrame
    """
    return frame[frame[COL_EXCLUDED_REASON] == REASON_NONE].copy()


def _non_overlapping_by_position(trading_days: pd.DatetimeIndex, frame: pd.DataFrame) -> dict[str, int]:
    """사이클 위치마다 **겹치지 않게 고를 수 있는 체결의 최대 개수**를 센다.

    **산식은 `measure.statistics.max_non_overlapping` 이 소유한다** — 검증마다 따로 구현하면
    끝점 처리 같은 한 칸 차이가 생기고, 같은 이름의 컬럼이 다른 뜻을 갖는다.

    [중요] **보유가 신호마다 달라(186~188 거래일) 그 칸의 «가장 긴» 보유를 구간 길이로 쓴다.**
    짧게 잡으면 실제로 겹친 두 구간을 독립으로 세어 **표본이 실제보다 단단해 보인다** —
    이 값을 내는 목적과 정반대가 된다. 길게 잡는 쪽은 적게 세므로 안전하다.

    Args:
        trading_days: 거래일 목록. 겹침은 날짜가 아니라 위치로만 정확히 판정된다
        frame: `cycle_returns` 의 결과. 제외 행이 섞여 있어도 된다

    Returns:
        사이클 위치 → 비중첩 최대 개수. 유효 체결이 없는 위치는 키가 없다
    """
    valid = frame[frame[COL_EXCLUDED_REASON] == REASON_NONE]

    counts: dict[str, int] = {}
    for position, rows in valid.groupby(COL_CYCLE_POSITION, sort=False):
        # **위치 변환은 `trade_fill.resolve_positions` 가 소유한다** — 날것의 `get_indexer` 는
        # 찾지 못한 날짜에 `-1` 을 돌려주고 `max_non_overlapping` 이 그것을 한 구간으로 세어
        # **비중첩 표본이 늘어난다.** 이 컬럼의 목적이 표본을 «줄여» 보여주는 것이라 정반대가 된다
        positions = resolve_positions(trading_days, pd.DatetimeIndex(rows[COL_DATE]), label="진입일")
        counts[str(position)] = max_non_overlapping(positions.tolist(), int(rows[COL_HOLD_DAYS].max()))

    return counts


def _aggregate_by_position(
    signal: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    trading_days: pd.DatetimeIndex,
    repeats: int,
    seed: int,
) -> pd.DataFrame:
    """사이클 위치별로 쪼개 집계·기준선 대비 차이·우연확률을 한 번에 낸다.

    **구간 축을 사이클 위치로 빌려 `summarize`·`excess`·`permutation_test` 를 재사용한다** —
    통계량 정의를 여기서 다시 구현하면 두 곳이 조용히 갈라진다 (절대 원칙 5).

    [중요] **제외 행을 포함한 «전체»를 받는다.** 유효 행만 넘기면 `summarize` 의
    `count_excluded` 가 셀 것이 없어 **`제외` 컬럼이 언제나 0** 이 되는데, 이 저장소에서
    0 은 「재서 0」이라는 뜻이라 없는 안전을 보고하게 된다 (패키지 절대 원칙 4 「표본 보존」).

    **사이클 위치는 제외 행에도 있다** — 진입 «연도»에서 나오므로 청산을 확정하지 못해도
    값이 채워진다. 달 축과 달리 축이 비어 그룹째 사라지는 일이 없다.

    Args:
        signal: 신호군 long-form. **제외 행을 포함한 전체**다
        baseline: 기준선 long-form. **제외 행을 포함한 전체**다
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        사이클 위치별 집계. 신호가 있는 위치만 낸다
    """
    signal_by_position = signal.copy()
    signal_by_position[COL_HORIZON] = signal_by_position[COL_CYCLE_POSITION]
    baseline_by_position = baseline.copy()
    baseline_by_position[COL_HORIZON] = baseline_by_position[COL_CYCLE_POSITION]

    # 신호가 있는 위치만 낸다. 기준선에만 있는 위치를 남기면 초과분의 칸 구성이 어긋난다
    positions = set(signal_by_position[COL_HORIZON].tolist())
    baseline_by_position = baseline_by_position[baseline_by_position[COL_HORIZON].isin(positions)]

    signal_summary = summarize(signal_by_position)
    if signal_summary.empty:
        return pd.DataFrame()

    baseline_summary = summarize(baseline_by_position)
    position_excess = excess(signal_summary, baseline_summary)
    position_test = permutation_test(signal_by_position, baseline_by_position, repeats=repeats, seed=seed)

    merged = (
        signal_summary.merge(baseline_summary, on=[COL_BASIS, COL_HORIZON], suffixes=("", BASELINE_SUFFIX))
        .merge(
            position_excess[
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
            position_test[
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
    merged[COL_JUDGEABLE] = merged[COL_SAMPLE_COUNT].map(lambda count: judgeable(int(count)))

    result = merged.rename(columns={COL_HORIZON: COL_CYCLE_POSITION}).drop(columns=[COL_BASIS])

    # **비중첩 표본을 «양쪽» 다 낸다** (`src/verify_lab/CLAUDE.md` 「비중첩 표본 계약」).
    # 기준선은 달마다 진입해 9개월을 드는 롤링이라 이웃이 8/9 씩 겹치므로 표본 수만으로는
    # 단단함을 오독한다. 신호 쪽은 4년 간격이라 겹치지 않으며, **두 값이 같다는 것이
    # 「표본이 서로 독립인가」(측정의 원칙 5)에 대한 답**이다
    for column, source in (
        (COL_NON_OVERLAPPING, _non_overlapping_by_position(trading_days, signal)),
        (COL_BASELINE_NON_OVERLAPPING, _non_overlapping_by_position(trading_days, baseline)),
    ):
        result[column] = result[COL_CYCLE_POSITION].map(source).astype("Int64")

    return result


def _order_by_cycle(frame: pd.DataFrame) -> pd.DataFrame:
    """사이클 순서로 행을 세운다.

    **알파벳순이 아니라 사람이 읽는 순서다.** 집계 계층은 축을 문자열로 받아 사전순으로
    정렬하므로, 그대로 두면 「대선다음해 → 대선전해 → 대선해 → 중간선거해」가 된다.
    순서가 결정적이어야 산출물 diff 가 「숫자가 바뀌었는가」를 말해 준다.

    Args:
        frame: 사이클 위치 컬럼이 있는 표

    Returns:
        `CYCLE_POSITIONS` 순서로 정렬된 표
    """
    order = {position: index for index, position in enumerate(CYCLE_POSITIONS)}

    return frame.sort_values(COL_CYCLE_POSITION, key=lambda values: values.map(order)).reset_index(drop=True)


def _dividend_row(dataset: Dataset, valid_signal: pd.DataFrame, position: str) -> dict[str, Any]:
    """그 칸의 보유 구간에 들어간 배당락을 잰다.

    **산식은 `measure/distribution.py` 가 소유한다.**

    [중요] **이 매매법은 배당락이 «매번» 걸린다.** 보유가 9개월이라 분기 배당 3회가
    구조적으로 들어오므로 「걸린 건수 = 표본」이 정상이고, **평균 왜곡이 곧 원본가가 놓친
    몫**이다. 다른 매매법처럼 「걸린 칸을 뺀다」로 대응할 수 없어 크기를 수치로 남긴다.

    [중요] **지수는 비운다.** 지수는 상품이 아니라 계산값이라 분배금을 지급할 일이 없고
    수정주가 파일도 없다. **0 으로 채우면 「안 걸림」과 「잴 수 없음」이 구별되지 않는다.**

    **방향은 「위」로 잰다** — 측정 표의 값이 1배 롱 기준 그대로이기 때문이다.

    Args:
        dataset: 대상 종목
        valid_signal: 유효 신호 long-form
        position: 재는 사이클 위치

    Returns:
        배당락 세 컬럼. 지수이거나 그 칸의 체결이 없으면 값이 비어 있다

    Raises:
        ValueError: ETF 인데 수정주가 파일이 없는 경우
    """
    blank: dict[str, Any] = {
        COL_DIVIDEND_MEASURED: pd.NA,
        COL_DIVIDEND_HIT_COUNT: pd.NA,
        COL_DIVIDEND_MEAN_IMPACT: np.nan,
    }

    if dataset.is_index:
        return blank

    rows = valid_signal[valid_signal[COL_CYCLE_POSITION] == position]

    # **0 으로 채우지 않는다.** 체결이 없는 것과 왜곡이 0 인 것은 다른 사실이다
    if rows.empty:
        return blank

    adjusted_path = dataset.directory / ADJUSTED_FILE_TEMPLATE.format(ticker=dataset.ticker)
    if not adjusted_path.is_file():
        raise ValueError(f"배당락을 재려면 수정주가 파일이 필요합니다: {adjusted_path}")

    raw_close = load_market_csv(dataset.path).set_index(COL_DATE)[dataset.price_column]
    adjusted_close = load_market_csv(adjusted_path).set_index(COL_DATE)[COL_CLOSE]

    impact = dividend_impact(
        raw_close,
        adjusted_close,
        entry_dates=pd.DatetimeIndex(rows[COL_DATE]),
        exit_dates=pd.DatetimeIndex(rows[COL_EXIT_DATE]),
        bet_down=False,
    )

    return {
        COL_DIVIDEND_MEASURED: impact.measured_count,
        COL_DIVIDEND_HIT_COUNT: impact.hit_count,
        # **여기서 반올림한다.** 이 값은 이미 %p 단위라 저장 계층의 비율→백분율 변환을 타지
        # 않고, 그대로 두면 과학적 표기로 CSV 에 실려 읽히지 않는다
        COL_DIVIDEND_MEAN_IMPACT: round(impact.mean_percent, DIVIDEND_IMPACT_DECIMALS),
    }


def _run_dataset(
    dataset: Dataset,
    accumulator: _Accumulator,
    *,
    repeats: int,
    seed: int,
) -> dict[str, Any]:
    """대상 하나를 돌린다.

    Args:
        dataset: 검증 대상 정의
        accumulator: 결과를 쌓는 자리
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        이 대상의 요약 수치

    Raises:
        RuntimeError: 사이클 위치별 집계가 통째로 비어 잴 수 없는 경우 (내부 불변조건 위반)
    """
    df = load_dataset(dataset)
    trading_days = pd.DatetimeIndex(df[COL_DATE])

    signal = signal_returns(df, dataset)
    baseline = _baseline_returns(df, dataset)
    valid_signal = _valid(signal)

    # **전체를 넘긴다** — 유효만 넘기면 `제외` 가 언제나 0 이 된다 (위 함수의 설명)
    block = _aggregate_by_position(signal, baseline, trading_days=trading_days, repeats=repeats, seed=seed)

    # **요약이 「정상으로 보이는 것」이 이 가드의 이유다.** 집계가 비면 그 대상이 통째로
    # 사라지는데 나머지 키는 멀쩡하므로 `summary.json` 만 봐서는 알 수 없다
    if block.empty:
        raise RuntimeError(f"내부 불변조건 위반: 사이클 위치별 집계가 비어 잴 수 없습니다: {dataset.label}")

    block = _order_by_cycle(block)

    dividend = pd.DataFrame(
        [_dividend_row(dataset, valid_signal, str(position)) for position in block[COL_CYCLE_POSITION]],
        index=block.index,
    )
    block = pd.concat([block, dividend], axis=1)

    block.insert(0, COL_TICKER, dataset.label)

    # **방향은 식별 컬럼이고 값을 바꾸지 않는다.** 측정 표의 수치는 1배 롱 기준 그대로이며,
    # 부호를 뒤집으면 `기준선 오른 비율` 이 실제로는 내린 비율을 가리켜 이름이 거짓이 된다
    block.insert(2, COL_DIRECTION, DIRECTION_DOWN if BET_DOWN else DIRECTION_UP)

    accumulator.statistics.append(block)

    excluded_count = int((signal[COL_EXCLUDED_REASON] != REASON_NONE).sum())

    return {
        # **공통 다섯 키가 먼저, 이 검증의 축이 뒤에 온다.** `ticker` 는 반드시
        # `dataset.ticker` 에서 온다 — 둘 다 `str` 이라 다른 필드를 넘겨도 키 이름은 그대로고
        # 값만 조용히 뒤바뀐다 (`tests/test_layer_contracts.py` 가 출처를 검사한다)
        **dataset_record(ticker=dataset.ticker, label=dataset.label, file=dataset.path.name, frame=df),
        # **원 심볼은 별도 키로 남긴다.** 지수는 파일명(`GSPC`)과 조회 심볼(`^GSPC`)이 달라
        # 이 값이 없으면 차트·증권앱과 대조할 때 무엇을 찾아야 할지 알 수 없다
        KEY_SYMBOL: dataset.symbol,
        KEY_IS_INDEX: dataset.is_index,
        KEY_ENTRY_COUNT: len(signal),
        KEY_EXCLUDED_COUNT: excluded_count,
    }


def run_study(
    datasets: tuple[Dataset, ...] = DATASETS,
    *,
    repeats: int = DEFAULT_REPEAT_COUNT,
    seed: int = DEFAULT_RANDOM_SEED,
) -> StudyOutputs:
    """중간선거_사이클 측정을 실행하고 산출물을 조립한다.

    Args:
        datasets: 검증 대상 목록
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        실행 산출물

    Raises:
        ValueError: 대상 목록이 비어 있는 경우
    """
    if not datasets:
        raise ValueError("검증 대상이 하나도 없습니다")

    accumulator = _Accumulator()
    dataset_summaries = [_run_dataset(dataset, accumulator, repeats=repeats, seed=seed) for dataset in datasets]

    statistics = pd.concat(accumulator.statistics, ignore_index=True)

    summary: dict[str, Any] = {
        KEY_PERMUTATION_REPEATS: repeats,
        KEY_PERMUTATION_SEED: seed,
        KEY_ENTRY_MONTH: ENTRY_MONTH,
        KEY_EXIT_MONTH: EXIT_MONTH,
        KEY_POSITIONS: list(CYCLE_POSITIONS),
        KEY_TRACK: TRACK_NAME,
        KEY_DATASETS: dataset_summaries,
        KEY_ROW_COUNTS: {OUTPUT_FILES[FIELD_STATISTICS]: len(statistics)},
    }

    logger.debug(f"측정 완료: {len(statistics):,}행 (대상 {len(datasets)} × 사이클 위치 {len(CYCLE_POSITIONS)})")

    return StudyOutputs(statistics=statistics, summary=summary)


def display_tables(outputs: StudyOutputs) -> dict[str, pd.DataFrame]:
    """저장할 표를 표시용(한글 헤더·백분율)으로 바꾼다.

    **터미널과 CSV 가 같은 프레임을 쓴다.** 따로 가공하면 반올림 시점이 갈려 화면에서 본 숫자를
    CSV 에서 찾지 못한다.

    Args:
        outputs: 실행 산출물

    Returns:
        산출물 필드 이름 → 표시용 DataFrame
    """
    if outputs.statistics.empty:
        return {}

    table = to_display_columns(
        outputs.statistics,
        COLUMN_LABELS,
        percent_columns=[column for column in PERCENT_COLUMNS if column in outputs.statistics.columns],
        probability_columns=[column for column in PROBABILITY_COLUMNS if column in outputs.statistics.columns],
    )

    return {FIELD_STATISTICS: table}


__all__ = [
    "FIELD_STATISTICS",
    "StudyOutputs",
    "display_tables",
    "load_dataset",
    "run_study",
    "signal_returns",
]
