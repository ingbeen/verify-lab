"""검증 #1 실행 — 강건성 조합을 한 번에 돌고 산출물을 조립한다

이 모듈은 **계산하지 않는다.** 이벤트 정의(`studies`)·수익률과 통계(`measure`)·표 렌더링(`report`)이
이미 전부 있으므로, 하는 일은 그것을 조합해 돌리고 사람이 읽을 형태로 쌓는 것이다.

조합을 쪼개지 않고 한 실행에서 전부 돌리는 이유는 두 가지다.

- **여러 설정값을 나란히 보고**해야 한다. 하나를 골라 "이게 제일 좋다"고 내는 순간 측정이 아니라
  과최적화가 된다
- 데이터셋끼리 **나란히 놓고 보려면** "파라미터가 같았다"가 전제여야 한다. 따로 돌리면 그 사실을
  사람이 확인해야 하고, 확인을 빠뜨려도 표는 정상으로 보인다

**자르는 것은 언제나 신호 선택이지 시세가 아니다.** 시세를 먼저 자르면 확장창 순위가 그 지점부터
다시 쌓이고 걸쳐 있던 연속이 끊긴다. 결과는 달라지는데 예외가 나지 않아 알아차릴 수 없다.

베이스라인 모집단도 **신호군과 같은 기간**으로 자른다. 전 기간 한 벌을 돌려쓰면 초과분의 차이에
"그 사이 시장이 어땠는가"가 섞여, 시작 시점 민감도 체크가 신호가 아니라 시장을 재게 된다.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any

import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE
from verify_lab.data.loader import load_market_csv
from verify_lab.measure.baseline import DEFAULT_MA_WINDOW, below_moving_average
from verify_lab.measure.constants import COL_BASIS, COL_FORWARD_RETURN
from verify_lab.measure.forward_return import DEFAULT_HORIZONS, ReturnBasis, compute_forward_returns
from verify_lab.measure.statistics import (
    DEFAULT_RANDOM_SEED,
    DEFAULT_REPEAT_COUNT,
    excess,
    permutation_test,
    summarize,
)
from verify_lab.report.constants import BASIS_LABELS, PERCENT_DECIMALS, RATE_TO_PERCENT
from verify_lab.report.tables import (
    build_excess_table,
    build_signal_table,
    build_statistics_table,
    build_test_table,
)
from verify_lab.studies.index_extreme.annotations import assign_event_ids, reference_zscore
from verify_lab.studies.index_extreme.consecutive import find_consecutive_events
from verify_lab.studies.index_extreme.constants import (
    CONSECUTIVE_DIRECTION_LABELS,
    CONSECUTIVE_LENGTHS,
    DATASETS,
    DECADE_PERIODS,
    DEFAULT_START_YEAR,
    DISPLAY_BASELINE_ALL,
    DISPLAY_BASELINE_BELOW_SMA,
    DISPLAY_CHANGE_RATE,
    DISPLAY_CLOSE,
    DISPLAY_DIRECTION,
    DISPLAY_DIRECTION_REVERSE_ALL,
    DISPLAY_EVENT_COUNT,
    DISPLAY_EVENT_ID,
    DISPLAY_GROUP_SIGNAL_COUNT,
    DISPLAY_PARAMETER,
    DISPLAY_PERIOD,
    DISPLAY_RANK,
    DISPLAY_START_YEAR,
    DISPLAY_TEST,
    DISPLAY_TEST_CONSECUTIVE,
    DISPLAY_TEST_EXTREME,
    DISPLAY_TICKER,
    DISPLAY_ZSCORE,
    EVENT_GAP_DAYS,
    EXTREME_DIRECTION_LABELS,
    PARAMETER_PREFIX_LENGTH,
    PARAMETER_PREFIX_RANK_CUT,
    PERIOD_ALL,
    RANK_CUTS,
    START_YEARS,
    STUDY_NAME,
    ZSCORE_DECIMALS,
    ZSCORE_WINDOW,
    Dataset,
    Direction,
    Period,
)
from verify_lab.studies.index_extreme.daily_change import daily_change_rate
from verify_lab.studies.index_extreme.extreme_move import (
    COL_PLUNGE_RANK,
    COL_SURGE_RANK,
    expanding_rank,
    find_extreme_move_events,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 신호군 식별 컬럼. 네 산출물 모두 이 순서로 앞에 붙는다 —
# 조합을 한 파일에 쌓으므로 어느 행이 어떤 설정의 결과인지가 행 자체에 있어야 한다
IDENTITY_COLUMNS = (
    DISPLAY_TICKER,
    DISPLAY_TEST,
    DISPLAY_PARAMETER,
    DISPLAY_START_YEAR,
    DISPLAY_DIRECTION,
    DISPLAY_PERIOD,
)

# 집계·초과분·검정이 쓰는 수익률 기준. 익일 시가는 `signals.csv` 의 원자료로만 남고
# 평균·승률로 집계되지 않는다 (docs/spec/index_extreme_events.md §7 결정 ㉓).
# 그래서 세 표의 `기준` 이 상수가 되고, 컬럼 대신 실행 요약이 그 기록을 든다
AGGREGATED_BASIS = ReturnBasis.CLOSE

# ============================================================
# summary.json 키 (영문 snake_case — meta.json 의 기존 관용과 맞춘다)
# ============================================================

KEY_AGGREGATED_BASIS = "aggregated_basis"
KEY_STUDY = "study"
KEY_DATASETS = "datasets"
KEY_PARAMETERS = "parameters"
KEY_PERMUTATION = "permutation"
KEY_POPULATIONS = "populations"
KEY_SIGNAL_GROUP_COUNT = "signal_group_count"
KEY_EMPTY_SIGNAL_GROUPS = "empty_signal_groups"
KEY_ROW_COUNTS = "row_counts"
KEY_NOTES = "notes"

KEY_TICKER = "ticker"
KEY_PRICE_BASIS = "price_basis"
KEY_PATH = "path"
KEY_ROW_COUNT = "row_count"
KEY_START_DATE = "start_date"
KEY_END_DATE = "end_date"
KEY_SMA_UNDETERMINED = "sma_undetermined_count"

KEY_TEST = "test"
KEY_PARAMETER = "parameter"
KEY_START_YEAR = "start_year"
KEY_DIRECTION = "direction"
KEY_PERIOD = "period"
KEY_BASELINE = "baseline"
KEY_DAY_COUNT = "day_count"

KEY_REPEATS = "repeats"
KEY_SEED = "seed"

KEY_SIGNALS = "signals"
KEY_STATISTICS = "statistics"
KEY_EXCESS = "excess"
KEY_TEST_TABLE = "test"

# 산출물만 보고는 알 수 없는 실행 조건. 대조의 전제가 무엇이었는지를 남긴다
NOTE_SAME_PARAMETERS = "모든 데이터셋을 같은 실행·같은 파라미터로 계산했다. 데이터셋끼리 나란히 놓고 보는 것은 이 전제 위에서만 성립한다"
NOTE_BASELINE_WINDOW = "베이스라인 모집단은 신호군과 같은 기간으로 잘랐다. 이동평균은 전 기간으로 쌓은 뒤 날짜로 걸렀다"
NOTE_REVERSE_ALL = (
    f"방향 '{DISPLAY_DIRECTION_REVERSE_ALL}' 은 두 방향을 한 표본으로 묶되 상승 방향 신호의 수익률에 -1 을 곱해 "
    "역방향 진입 기준으로 부호를 맞춘 값이다. 베이스라인은 같은 거래일을 원본과 부호 반전 두 벌로 둔 대칭 모집단이라 "
    "표본 수가 두 배이고 평균이 0 이다. 신호일 목록에는 이 방향의 행이 없다 - 방향별 두 블록을 합치면 복원된다"
)


@dataclass(frozen=True)
class StudyOutputs:
    """실행 산출물

    Attributes:
        signals: 신호일 한 줄짜리 목록 (사용자가 차트로 직접 대조하는 원자료)
        statistics: 신호군 × 칸별 집계
        excess: 베이스라인 3종 대비 초과분
        test: 모집단 3종에 대한 순열 검정
        summary: 실행 파라미터와 핵심 수치
    """

    signals: pd.DataFrame
    statistics: pd.DataFrame
    excess: pd.DataFrame
    test: pd.DataFrame
    summary: dict[str, Any]


@dataclass(frozen=True)
class _Context:
    """데이터셋 하나에서 신호군마다 다시 쓰는 값

    확장창 순위와 전 거래일 forward return 은 신호군과 무관하므로 데이터셋당 한 번만 만든다.
    """

    dataset: Dataset
    frame: pd.DataFrame
    change_rates: pd.Series
    surge_ranks: pd.Series
    plunge_ranks: pd.Series
    zscores: pd.Series
    all_day_returns: pd.DataFrame
    below_sma: pd.Series
    sma_undetermined: int


@dataclass(frozen=True)
class _Population:
    """한 기간의 베이스라인 모집단

    Attributes:
        day_count: 모집단에 든 거래일 수
        returns: 그 날들의 forward return long-form
        summary: 칸별 집계
    """

    day_count: int
    returns: pd.DataFrame
    summary: pd.DataFrame


@dataclass(frozen=True)
class _TestSpec:
    """한 이벤트 정의와 그 파라미터

    Attributes:
        test_label: 표시용 테스트 이름
        parameter_label: 표시용 파라미터 (`K=10` / `N=5`)
        direction_labels: 방향의 표시 이름. 테스트마다 부르는 이름이 다르다
        combine_directions: 사건 번호를 두 방향을 합친 목록에 매길지 여부
        find: 시세와 방향·시작일을 받아 bool Series 를 내는 함수
    """

    test_label: str
    parameter_label: str
    direction_labels: Mapping[Direction, str]
    combine_directions: bool
    find: Callable[[pd.DataFrame, Direction, pd.Timestamp], pd.Series]


def run_study(
    datasets: Sequence[Dataset] = DATASETS,
    *,
    rank_cuts: Sequence[int] = RANK_CUTS,
    consecutive_lengths: Sequence[int] = CONSECUTIVE_LENGTHS,
    start_years: Sequence[int] = START_YEARS,
    repeats: int = DEFAULT_REPEAT_COUNT,
    seed: int = DEFAULT_RANDOM_SEED,
) -> StudyOutputs:
    """강건성 조합을 전부 돌고 산출물 네 표와 요약을 만든다.

    신호군은 **테스트 × 파라미터 × 시작연도 × 방향 × 시대 구간 × 데이터셋**의 곱이다.
    시대 구간(2010년대·2020년대)은 기본 시작연도에만 붙는다 — 모든 시작연도에 곱하면
    해석하기 어려운 조합이 생기고, 스펙이 이것을 축이 아니라 강건성 "체크"로 둔 취지에서 멀어진다.

    **신호가 0건인 신호군은 집계에서 빼되 뺐다는 사실을 요약에 남긴다.** 조용히 사라진 표본은
    생존편향을 만들고, 빈 표는 아래 계층이 예외로 거부한다.

    Args:
        datasets: 검증 대상 시세 목록. 국내 두 가격 기준을 함께 넘겨야 대조가 성립한다
        rank_cuts: 테스트 A 의 순위 컷 목록
        consecutive_lengths: 테스트 B 의 연속 일수 목록
        start_years: 신호 집계 시작 연도 목록
        repeats: 순열 검정의 반복 수
        seed: 순열 검정의 난수 시드. 결과 문서에 기록해야 재현된다

    Returns:
        표시용 표 4개와 요약. 네 표 모두 식별 컬럼이 앞에 붙어 있다

    Raises:
        ValueError: 데이터셋이나 축이 비어 있는 경우, 시세를 읽을 수 없는 경우
    """
    _validate_axes(datasets, rank_cuts, consecutive_lengths, start_years)

    specs = _build_specs(rank_cuts, consecutive_lengths)
    signal_blocks: list[pd.DataFrame] = []
    statistics_blocks: list[pd.DataFrame] = []
    excess_blocks: list[pd.DataFrame] = []
    test_blocks: list[pd.DataFrame] = []
    dataset_records: list[dict[str, Any]] = []
    population_records: list[dict[str, Any]] = []
    empty_groups: list[dict[str, Any]] = []

    for dataset in datasets:
        context = _build_context(dataset)
        dataset_records.append(_dataset_record(context))

        for start_year in start_years:
            for period in _periods_for(start_year, start_years):
                start, end = _window_bounds(start_year, period)
                populations = _build_populations(context, start, end)
                population_records.extend(_population_records(context, start_year, period, populations))

                # 창에 거래일이 하나도 없으면 그 창의 신호도 전부 0건이다.
                # 조용히 넘기면 "신호군 수 + 빠진 신호군 수 = 축의 곱" 이 깨진다
                if not populations:
                    empty_groups.extend(_window_group_records(context, specs, start_year, period))
                    logger.debug(f"{dataset.ticker} {start_year}년 {period.label}: 창에 거래일이 없습니다")
                    continue

                # 대칭 모집단은 신호군과 무관하므로 창당 한 번만 만든다
                symmetric_populations = _symmetric_populations(populations)

                for spec in specs:
                    blocks = _measure_spec(
                        context,
                        spec,
                        start_year=start_year,
                        period=period,
                        start=start,
                        end=end,
                        populations=populations,
                        symmetric_populations=symmetric_populations,
                        repeats=repeats,
                        seed=seed,
                        empty_groups=empty_groups,
                    )
                    signal_blocks.extend(blocks[0])
                    statistics_blocks.extend(blocks[1])
                    excess_blocks.extend(blocks[2])
                    test_blocks.extend(blocks[3])

    signals = _stack(signal_blocks)
    statistics = _stack(statistics_blocks)
    excess_table = _stack(excess_blocks)
    test_table = _stack(test_blocks)

    summary = {
        KEY_STUDY: STUDY_NAME,
        KEY_DATASETS: dataset_records,
        KEY_PARAMETERS: {
            "rank_cuts": list(rank_cuts),
            "consecutive_lengths": list(consecutive_lengths),
            "start_years": list(start_years),
            "periods": [period.label for period in (PERIOD_ALL, *DECADE_PERIODS)],
            "horizons": list(DEFAULT_HORIZONS),
            KEY_AGGREGATED_BASIS: BASIS_LABELS[AGGREGATED_BASIS.value],
            "moving_average_window": DEFAULT_MA_WINDOW,
            "event_gap_days": EVENT_GAP_DAYS,
            "zscore_window": ZSCORE_WINDOW,
        },
        KEY_PERMUTATION: {KEY_REPEATS: repeats, KEY_SEED: seed},
        KEY_POPULATIONS: population_records,
        KEY_SIGNAL_GROUP_COUNT: len(statistics_blocks),
        KEY_EMPTY_SIGNAL_GROUPS: empty_groups,
        KEY_ROW_COUNTS: {
            KEY_SIGNALS: len(signals),
            KEY_STATISTICS: len(statistics),
            KEY_EXCESS: len(excess_table),
            KEY_TEST_TABLE: len(test_table),
        },
        KEY_NOTES: [NOTE_SAME_PARAMETERS, NOTE_BASELINE_WINDOW, NOTE_REVERSE_ALL],
    }

    logger.debug(
        f"검증 실행 완료: 신호군 {len(statistics_blocks):,}개 " f"(신호 0건 {len(empty_groups):,}개 제외), 신호일 {len(signals):,}건"
    )

    return StudyOutputs(
        signals=signals,
        statistics=statistics,
        excess=excess_table,
        test=test_table,
        summary=summary,
    )


def _validate_axes(
    datasets: Sequence[Dataset],
    rank_cuts: Sequence[int],
    consecutive_lengths: Sequence[int],
    start_years: Sequence[int],
) -> None:
    """축이 하나라도 비어 있으면 즉시 막는다.

    빈 축으로 돌면 아무것도 재지 않은 결과가 정상처럼 나온다.

    Args:
        datasets: 검증 대상 시세 목록
        rank_cuts: 순위 컷 목록
        consecutive_lengths: 연속 일수 목록
        start_years: 집계 시작 연도 목록

    Raises:
        ValueError: 비어 있는 축이 있는 경우
    """
    if not datasets:
        raise ValueError("검증 대상 데이터셋이 비어 있습니다")

    if not rank_cuts:
        raise ValueError("순위 컷 목록이 비어 있습니다")

    if not consecutive_lengths:
        raise ValueError("연속 일수 목록이 비어 있습니다")

    if not start_years:
        raise ValueError("집계 시작 연도 목록이 비어 있습니다")


def _build_specs(rank_cuts: Sequence[int], consecutive_lengths: Sequence[int]) -> list[_TestSpec]:
    """두 테스트의 파라미터를 펼쳐 이벤트 정의 목록을 만든다.

    **사건 번호의 기준이 테스트마다 다르다.** 테스트 A 는 급락과 급반등이 같은 충격에서 나오므로
    두 방향을 합쳐 매기고, 테스트 B 는 방향별로 따로 매긴다 — 신호가 촘촘한 칸에서는 30일 체인이
    끊기지 않아 합집합 사건 하나가 수년에 걸치고, 그러면 "같은 충격인가"를 더 이상 구분하지 못한다.
    근거 수치는 `docs/spec/index_extreme_events.md` §7 결정 ⑭ 에 있다.

    Args:
        rank_cuts: 테스트 A 의 순위 컷 목록
        consecutive_lengths: 테스트 B 의 연속 일수 목록

    Returns:
        테스트 A 를 먼저 담은 이벤트 정의 목록
    """
    specs = [
        _TestSpec(
            test_label=DISPLAY_TEST_EXTREME,
            parameter_label=f"{PARAMETER_PREFIX_RANK_CUT}={cut}",
            direction_labels=EXTREME_DIRECTION_LABELS,
            combine_directions=True,
            find=partial(_find_extreme, rank_cut=cut),
        )
        for cut in rank_cuts
    ]
    specs.extend(
        _TestSpec(
            test_label=DISPLAY_TEST_CONSECUTIVE,
            parameter_label=f"{PARAMETER_PREFIX_LENGTH}={length}",
            direction_labels=CONSECUTIVE_DIRECTION_LABELS,
            combine_directions=False,
            find=partial(_find_consecutive, length=length),
        )
        for length in consecutive_lengths
    )

    return specs


def _find_extreme(df: pd.DataFrame, direction: Direction, start: pd.Timestamp, *, rank_cut: int) -> pd.Series:
    """테스트 A 신호를 고른다 (집계 시작일은 이벤트 정의가 소유한다).

    Args:
        df: 시세
        direction: 폭등·폭락
        start: 집계 시작일
        rank_cut: 순위 컷

    Returns:
        신호인 날이 True 인 bool Series
    """
    return find_extreme_move_events(df, direction=direction, rank_cut=rank_cut, start_date=start)


def _find_consecutive(df: pd.DataFrame, direction: Direction, start: pd.Timestamp, *, length: int) -> pd.Series:
    """테스트 B 신호를 고른다 (집계 시작일은 이벤트 정의가 소유한다).

    Args:
        df: 시세
        direction: 연속 상승·연속 하락
        start: 집계 시작일
        length: 연속 일수

    Returns:
        신호인 날이 True 인 bool Series
    """
    return find_consecutive_events(df, direction=direction, length=length, start_date=start)


def _build_context(dataset: Dataset) -> _Context:
    """데이터셋 하나를 읽고 신호군과 무관한 값을 미리 만든다.

    확장창 순위·연속 길이·z-score·전 거래일 forward return 은 파라미터가 바뀌어도 같은 값이므로
    데이터셋당 한 번만 만든다.

    Args:
        dataset: 검증 대상 시세

    Returns:
        신호군 순회에 쓰는 공통 값

    Raises:
        FileNotFoundError: 시세 파일이 없는 경우
        ValueError: 시세가 검증을 통과하지 못한 경우
    """
    frame = load_market_csv(dataset.path)
    ranks = expanding_rank(frame)
    sma = below_moving_average(frame)

    return _Context(
        dataset=dataset,
        frame=frame,
        change_rates=daily_change_rate(frame),
        surge_ranks=ranks[COL_SURGE_RANK],
        plunge_ranks=ranks[COL_PLUNGE_RANK],
        zscores=reference_zscore(frame),
        all_day_returns=compute_forward_returns(frame, pd.Series(True, index=frame.index)),
        below_sma=sma.mask,
        sma_undetermined=sma.undetermined_count,
    )


def _dataset_record(context: _Context) -> dict[str, Any]:
    """데이터셋 정보를 요약용 dict 로 만든다.

    Args:
        context: 데이터셋 공통 값

    Returns:
        요약 dict
    """
    dates = context.frame[COL_DATE]

    return {
        KEY_TICKER: context.dataset.ticker,
        KEY_PRICE_BASIS: context.dataset.price_basis,
        KEY_PATH: str(context.dataset.path),
        KEY_ROW_COUNT: len(context.frame),
        KEY_START_DATE: str(dates.min().date()),
        KEY_END_DATE: str(dates.max().date()),
        KEY_SMA_UNDETERMINED: context.sma_undetermined,
    }


def _periods_for(start_year: int, start_years: Sequence[int]) -> tuple[Period, ...]:
    """이 시작연도에 붙일 시대 구간을 정한다.

    시대 구간은 **기본 시작연도에만** 붙인다. 기본 시작연도가 축에 없으면 축의 첫 연도에 붙여
    강건성 체크가 통째로 빠지지 않게 한다.

    Args:
        start_year: 집계 시작 연도
        start_years: 축 전체

    Returns:
        전체 구간을 앞에 둔 구간 목록
    """
    anchor = DEFAULT_START_YEAR if DEFAULT_START_YEAR in start_years else start_years[0]

    if start_year != anchor:
        return (PERIOD_ALL,)

    return (PERIOD_ALL, *DECADE_PERIODS)


def _window_bounds(start_year: int, period: Period) -> tuple[pd.Timestamp, pd.Timestamp | None]:
    """신호를 셀 창의 양끝을 정한다.

    **시세가 아니라 신호 선택의 범위다.** 시작일은 이벤트 정의 함수에 넘겨 순위 축적을 보존하고,
    끝은 판정이 끝난 뒤 걸러낸다 — 미래를 보지 않는 판정이라 뒤를 잘라도 앞의 값이 달라지지 않는다.

    Args:
        start_year: 신호군의 집계 시작 연도
        period: 시대 구간

    Returns:
        시작일과 종료일 (종료일이 없으면 `None`)
    """
    effective_start = start_year if period.start_year is None else max(start_year, period.start_year)
    start = pd.Timestamp(year=effective_start, month=1, day=1)
    end = None if period.end_year is None else pd.Timestamp(year=period.end_year, month=12, day=31)

    return start, end


def _build_populations(context: _Context, start: pd.Timestamp, end: pd.Timestamp | None) -> dict[str, _Population]:
    """이 창의 베이스라인 모집단 3종을 만든다.

    세 모집단은 따로 계산하지 않고 **전 거래일 forward return 테이블 하나에서 파생**시킨다.
    수익률 산식이 한 곳에만 있어야 판정이 갈라지지 않는다.

    이동평균 판정은 전 기간으로 쌓은 뒤 날짜로 거른다. 먼저 자르면 창이 그 지점부터 다시 찬다.

    Args:
        context: 데이터셋 공통 값
        start: 창 시작일
        end: 창 종료일 (없으면 끝을 자르지 않는다)

    Returns:
        비어 있지 않은 모집단만 담은 이름 → 모집단
    """
    window = context.frame[COL_DATE] >= start
    if end is not None:
        window &= context.frame[COL_DATE] <= end

    masks = {
        DISPLAY_BASELINE_ALL: window,
        DISPLAY_BASELINE_BELOW_SMA: window & context.below_sma,
    }

    populations: dict[str, _Population] = {}
    for name, mask in masks.items():
        day_count = int(mask.sum())
        if day_count == 0:
            continue

        dates = context.frame.loc[mask, COL_DATE]
        returns = _aggregated_basis_only(context.all_day_returns[context.all_day_returns[COL_DATE].isin(dates)])
        populations[name] = _Population(day_count=day_count, returns=returns, summary=summarize(returns))

    return populations


def _population_records(
    context: _Context,
    start_year: int,
    period: Period,
    populations: Mapping[str, _Population],
) -> list[dict[str, Any]]:
    """모집단 크기를 요약용 dict 목록으로 만든다.

    **0건인 모집단도 남긴다.** 빠졌다는 사실이 결론의 일부다.

    Args:
        context: 데이터셋 공통 값
        start_year: 집계 시작 연도
        period: 시대 구간
        populations: 만들어진 모집단

    Returns:
        요약 dict 목록
    """
    names = (DISPLAY_BASELINE_ALL, DISPLAY_BASELINE_BELOW_SMA)

    return [
        {
            KEY_TICKER: context.dataset.ticker,
            KEY_PRICE_BASIS: context.dataset.price_basis,
            KEY_START_YEAR: start_year,
            KEY_PERIOD: period.label,
            KEY_BASELINE: name,
            KEY_DAY_COUNT: populations[name].day_count if name in populations else 0,
        }
        for name in names
    ]


def _window_group_records(
    context: _Context,
    specs: Sequence[_TestSpec],
    start_year: int,
    period: Period,
) -> list[dict[str, Any]]:
    """거래일이 없는 창의 신호군 전체를 "신호 0건" 으로 기록한다.

    Args:
        context: 데이터셋 공통 값
        specs: 이벤트 정의 목록
        start_year: 집계 시작 연도
        period: 시대 구간

    Returns:
        요약 dict 목록
    """
    return [
        _empty_group_record(
            {
                DISPLAY_TICKER: context.dataset.ticker,
                DISPLAY_TEST: spec.test_label,
                DISPLAY_PARAMETER: spec.parameter_label,
                DISPLAY_START_YEAR: start_year,
                DISPLAY_DIRECTION: spec.direction_labels[direction],
                DISPLAY_PERIOD: period.label,
            }
        )
        for spec in specs
        for direction in Direction
    ]


def _measure_spec(
    context: _Context,
    spec: _TestSpec,
    *,
    start_year: int,
    period: Period,
    start: pd.Timestamp,
    end: pd.Timestamp | None,
    populations: Mapping[str, _Population],
    symmetric_populations: Mapping[str, _Population],
    repeats: int,
    seed: int,
    empty_groups: list[dict[str, Any]],
) -> tuple[list[pd.DataFrame], list[pd.DataFrame], list[pd.DataFrame], list[pd.DataFrame]]:
    """한 이벤트 정의를 방향별로 재고 네 표의 조각을 만든다.

    방향은 이벤트 정의가 내는 둘에 더해 **두 방향을 합친 `역방향 전체`** 가 하나 더 있다
    (`_measure_reverse_all` 참고). 사건 번호를 어느 목록에 매기는지는 이벤트 정의가 정한다
    (`_build_specs` 참고).

    Args:
        context: 데이터셋 공통 값
        spec: 이벤트 정의와 파라미터
        start_year: 집계 시작 연도
        period: 시대 구간
        start: 창 시작일
        end: 창 종료일
        populations: 이 창의 베이스라인 모집단
        symmetric_populations: 같은 창의 대칭 베이스라인 모집단 (`역방향 전체` 용)
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드
        empty_groups: 신호 0건이라 빠진 신호군을 담을 목록 (제자리에서 채운다)

    Returns:
        신호일·집계·초과분·검정 표의 조각 목록
    """
    selected = {direction: spec.find(context.frame, direction, start) for direction in Direction}
    if end is not None:
        within = context.frame[COL_DATE] <= end
        selected = {direction: signals & within for direction, signals in selected.items()}

    event_ids = _event_ids(context.frame, selected, combine=spec.combine_directions)

    signal_blocks: list[pd.DataFrame] = []
    statistics_blocks: list[pd.DataFrame] = []
    excess_blocks: list[pd.DataFrame] = []
    test_blocks: list[pd.DataFrame] = []
    normalized_returns: list[pd.DataFrame] = []

    for direction, signals in selected.items():
        identity = {
            DISPLAY_TICKER: context.dataset.ticker,
            DISPLAY_TEST: spec.test_label,
            DISPLAY_PARAMETER: spec.parameter_label,
            DISPLAY_START_YEAR: start_year,
            DISPLAY_DIRECTION: spec.direction_labels[direction],
            DISPLAY_PERIOD: period.label,
        }

        signal_count = int(signals.sum())
        if signal_count == 0:
            empty_groups.append(_empty_group_record(identity))
            continue

        group_events = event_ids[direction]
        counts = {
            DISPLAY_GROUP_SIGNAL_COUNT: signal_count,
            DISPLAY_EVENT_COUNT: int(group_events.nunique()),
        }

        returns = compute_forward_returns(context.frame, signals)
        aggregated = _aggregated_basis_only(returns)
        signal_summary = summarize(aggregated)
        normalized_returns.append(_reverse_normalized(aggregated, direction))

        signal_blocks.append(
            _with_identity(
                build_signal_table(returns, _signal_details(context, signals, direction, group_events)),
                identity,
            )
        )
        statistics_blocks.append(
            _with_identity(
                build_statistics_table(signal_summary),
                identity,
                {DISPLAY_EVENT_COUNT: counts[DISPLAY_EVENT_COUNT]},
            )
        )
        excess_blocks.append(
            _with_identity(
                build_excess_table(
                    {name: excess(signal_summary, population.summary) for name, population in populations.items()}
                ),
                identity,
                counts,
            )
        )
        test_blocks.append(
            _with_identity(
                build_test_table(
                    {
                        name: permutation_test(aggregated, population.returns, repeats=repeats, seed=seed)
                        for name, population in populations.items()
                    }
                ),
                identity,
                counts,
            )
        )

    reverse_blocks = _measure_reverse_all(
        context,
        spec,
        start_year=start_year,
        period=period,
        selected=selected,
        event_ids=event_ids,
        normalized_returns=normalized_returns,
        symmetric_populations=symmetric_populations,
        repeats=repeats,
        seed=seed,
        empty_groups=empty_groups,
    )
    statistics_blocks.extend(reverse_blocks[0])
    excess_blocks.extend(reverse_blocks[1])
    test_blocks.extend(reverse_blocks[2])

    return signal_blocks, statistics_blocks, excess_blocks, test_blocks


def _measure_reverse_all(
    context: _Context,
    spec: _TestSpec,
    *,
    start_year: int,
    period: Period,
    selected: Mapping[Direction, pd.Series],
    event_ids: Mapping[Direction, pd.Series],
    normalized_returns: Sequence[pd.DataFrame],
    symmetric_populations: Mapping[str, _Population],
    repeats: int,
    seed: int,
    empty_groups: list[dict[str, Any]],
) -> tuple[list[pd.DataFrame], list[pd.DataFrame], list[pd.DataFrame]]:
    """두 방향을 한 표본으로 묶은 `역방향 전체` 신호군을 잰다.

    **이벤트 정의가 아니라 집계 단계의 합성이다.** 어느 날이 신호인지는 방향별 경로가 이미
    정했고, 여기서는 그 결과를 부호만 맞춰 이어 붙인다. 그래서 `signals.csv` 에는 이 방향의
    행을 내지 않는다 — 같은 날이 두 줄로 실리면 사용자의 차트 대조를 방해한다.

    Args:
        context: 데이터셋 공통 값
        spec: 이벤트 정의와 파라미터
        start_year: 집계 시작 연도
        period: 시대 구간
        selected: 방향 → 신호 bool Series
        event_ids: 방향 → 그 방향 신호일의 사건 번호
        normalized_returns: 방향별로 부호를 맞춘 forward return. 신호 0건 방향은 들어 있지 않다
        symmetric_populations: 대칭 베이스라인 모집단
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드
        empty_groups: 신호 0건이라 빠진 신호군을 담을 목록 (제자리에서 채운다)

    Returns:
        집계·초과분·검정 표의 조각 목록
    """
    identity = {
        DISPLAY_TICKER: context.dataset.ticker,
        DISPLAY_TEST: spec.test_label,
        DISPLAY_PARAMETER: spec.parameter_label,
        DISPLAY_START_YEAR: start_year,
        DISPLAY_DIRECTION: DISPLAY_DIRECTION_REVERSE_ALL,
        DISPLAY_PERIOD: period.label,
    }

    # 두 방향이 **모두** 0건일 때만 이 신호군도 0건이다. 한쪽만 비면 남은 쪽으로 성립한다
    if not normalized_returns:
        empty_groups.append(_empty_group_record(identity))
        return [], [], []

    combined = pd.concat(normalized_returns, ignore_index=True)
    combined_summary = summarize(combined)
    counts = {
        DISPLAY_GROUP_SIGNAL_COUNT: sum(int(signals.sum()) for signals in selected.values()),
        DISPLAY_EVENT_COUNT: _reverse_all_event_count(event_ids, combine=spec.combine_directions),
    }

    # 부호를 뒤집은 뒤이므로 "오른 비율" 이 곧 방향이 맞은 비율이다
    statistics_block = _with_identity(
        build_statistics_table(combined_summary),
        identity,
        {DISPLAY_EVENT_COUNT: counts[DISPLAY_EVENT_COUNT]},
    )
    excess_block = _with_identity(
        build_excess_table(
            {name: excess(combined_summary, population.summary) for name, population in symmetric_populations.items()}
        ),
        identity,
        counts,
    )
    test_block = _with_identity(
        build_test_table(
            {
                name: permutation_test(combined, population.returns, repeats=repeats, seed=seed)
                for name, population in symmetric_populations.items()
            }
        ),
        identity,
        counts,
    )

    return [statistics_block], [excess_block], [test_block]


def _reverse_normalized(returns: pd.DataFrame, direction: Direction) -> pd.DataFrame:
    """수익률을 "역방향으로 진입했을 때"의 부호로 맞춘다.

    상승 방향 신호(폭등·연속 상승)는 인버스로 들어가므로 **가격이 내려야 이익**이다.
    부호를 맞추지 않고 그냥 합치면 그 이익이 마이너스로 들어가 하락 방향의 이익과 상쇄되고,
    평균이 해석 불가능한 값이 된다.

    **이것은 인버스 상품의 손익이 아니다.** 원지수의 반대방향 수익률이며 레버리지 상품의
    일간 복리·보수·롤 비용은 반영되지 않는다.

    Args:
        returns: 한 방향의 forward return long-form
        direction: 그 방향

    Returns:
        부호를 맞춘 프레임. 입력은 변경하지 않는다
    """
    normalized = returns.copy()
    if direction is Direction.UP:
        normalized[COL_FORWARD_RETURN] = -normalized[COL_FORWARD_RETURN]

    return normalized


def _symmetric_populations(populations: Mapping[str, _Population]) -> dict[str, _Population]:
    """베이스라인 모집단을 `역방향 전체` 와 비교할 수 있는 형태로 만든다.

    신호군의 부호를 뒤집었으면 베이스라인도 같은 규칙으로 뒤집어야 비교가 성립하는데,
    **베이스라인에는 방향이 없다.** 그래서 같은 거래일을 원본 한 벌과 부호 반전 한 벌로 두어
    **"방향을 미리 모르고 동전 던지기로 정했다면"** 의 기준선을 만든다. 이 모집단의 평균은 0 이다.

    신호군의 상승·하락 신호 비율과는 어긋난다. 대신 신호군마다 달라지지 않아 신호군끼리
    나란히 놓고 볼 수 있다.

    Args:
        populations: 한 창의 베이스라인 모집단

    Returns:
        이름 → 대칭 모집단. 입력은 변경하지 않는다
    """
    symmetric: dict[str, _Population] = {}
    for name, population in populations.items():
        flipped = population.returns.copy()
        flipped[COL_FORWARD_RETURN] = -flipped[COL_FORWARD_RETURN]
        combined = pd.concat([population.returns, flipped], ignore_index=True)
        symmetric[name] = _Population(
            day_count=population.day_count * 2,
            returns=combined,
            summary=summarize(combined),
        )

    return symmetric


def _reverse_all_event_count(event_ids: Mapping[Direction, pd.Series], *, combine: bool) -> int:
    """두 방향을 합친 신호군의 사건 수를 센다.

    **합칠지 말지는 결정 ⑭ 이 테스트마다 정해 둔 것을 그대로 잇는다.** 테스트 A 는 이미 두
    방향을 합친 목록에 번호를 매기므로 그 번호를 그대로 세면 되고, 테스트 B 는 방향별로
    따로 매기므로 방향별 사건 수를 더한다 — 합집합에 새로 매기면 신호가 촘촘해 30일 체인이
    끊기지 않고 사건 하나가 수년에 걸친다.

    Args:
        event_ids: 방향 → 그 방향 신호일의 사건 번호
        combine: 사건 번호가 두 방향을 합친 목록에 매겨졌는지 여부

    Returns:
        사건 수
    """
    if combine:
        return int(pd.concat(list(event_ids.values())).nunique())

    return sum(int(ids.nunique()) for ids in event_ids.values())


def _event_ids(
    frame: pd.DataFrame,
    selected: Mapping[Direction, pd.Series],
    *,
    combine: bool,
) -> dict[Direction, pd.Series]:
    """방향별 신호일에 사건 번호를 매긴다.

    **합칠지 말지가 결론을 바꾼다.** 테스트 A 는 급락과 급반등이 같은 충격에서 나오므로 합쳐야
    "7건 = 사건 3개"가 나오고, 나누면 결정 ③ 이 드러내려던 비독립성이 숨는다. 반대로 테스트 B 는
    신호가 촘촘해 합치면 30일 체인이 끊기지 않고 사건 하나가 수년에 걸쳐, 방향이 반대인 신호까지
    한 충격으로 묶어 버린다.

    Args:
        frame: 시세
        selected: 방향 → 신호 bool Series
        combine: 두 방향을 합친 목록에 번호를 매길지 여부

    Returns:
        방향 → 그 방향 신호일의 사건 번호
    """
    if not combine:
        return {
            direction: assign_event_ids(frame.loc[signals, COL_DATE], EVENT_GAP_DAYS)
            for direction, signals in selected.items()
        }

    union = selected[Direction.UP] | selected[Direction.DOWN]
    numbered = assign_event_ids(frame.loc[union, COL_DATE], EVENT_GAP_DAYS)

    return {direction: numbered.loc[signals[signals].index] for direction, signals in selected.items()}


def _aggregated_basis_only(returns: pd.DataFrame) -> pd.DataFrame:
    """집계에 넘길 기준의 칸만 남긴다.

    신호군과 베이스라인 모집단에 **똑같이** 걸어야 한다. 한쪽만 걸면 초과분이 칸 구성 불일치로
    거부되고, 둘 다 걸지 않으면 `기준` 컬럼 없는 표에 같은 구간이 두 줄로 나온다.

    Args:
        returns: `compute_forward_returns` 의 결과

    Returns:
        집계 기준의 행만 남은 프레임. 입력은 변경하지 않는다
    """
    return returns[returns[COL_BASIS] == AGGREGATED_BASIS.value]


def _signal_details(
    context: _Context,
    signals: pd.Series,
    direction: Direction,
    event_ids: pd.Series,
) -> pd.DataFrame:
    """신호일 목록에 붙일 부가 컬럼을 만든다.

    `studies` 는 내부 토큰과 비율로만 내므로 **한글 레이블과 백분율 변환은 여기서 정한다.**
    종가 자릿수는 데이터셋이 정한다 — 원화 가격에 없는 소수 자리를 붙이지 않기 위해서다.

    당시 순위는 두 테스트 모두에 붙인다. 테스트 B 에서는 판정 근거가 아니라 "그날의 등락이
    당시 몇 위였나"라는 해석 보조다. 연속 길이는 파라미터 컬럼이 이미 담고 있어 두지 않는다.

    Args:
        context: 데이터셋 공통 값
        signals: 신호 bool Series
        direction: 방향
        event_ids: 신호일의 사건 번호

    Returns:
        날짜와 부가 컬럼을 담은 프레임
    """
    ranks = context.surge_ranks if direction is Direction.UP else context.plunge_ranks

    return pd.DataFrame(
        {
            COL_DATE: context.frame.loc[signals, COL_DATE].to_numpy(),
            DISPLAY_CLOSE: context.frame.loc[signals, COL_CLOSE].round(context.dataset.price_decimals).to_numpy(),
            DISPLAY_CHANGE_RATE: (context.change_rates[signals] * RATE_TO_PERCENT).round(PERCENT_DECIMALS).to_numpy(),
            DISPLAY_RANK: ranks[signals].astype(int).to_numpy(),
            DISPLAY_EVENT_ID: event_ids.to_numpy(),
            DISPLAY_ZSCORE: context.zscores[signals].round(ZSCORE_DECIMALS).to_numpy(),
        }
    )


def _empty_group_record(identity: Mapping[str, Any]) -> dict[str, Any]:
    """신호 0건 신호군을 요약용 dict 로 만든다.

    Args:
        identity: 신호군 식별 정보

    Returns:
        요약 dict
    """
    return {
        KEY_TICKER: identity[DISPLAY_TICKER],
        KEY_TEST: identity[DISPLAY_TEST],
        KEY_PARAMETER: identity[DISPLAY_PARAMETER],
        KEY_START_YEAR: identity[DISPLAY_START_YEAR],
        KEY_DIRECTION: identity[DISPLAY_DIRECTION],
        KEY_PERIOD: identity[DISPLAY_PERIOD],
    }


def _with_identity(
    table: pd.DataFrame,
    identity: Mapping[str, Any],
    extra: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """표 앞에 신호군 식별 컬럼을 붙인다.

    `report` 는 어떤 검증이 자기를 쓰는지 모르므로 이 컬럼을 알 수 없다. 계산이 아니라 조립이라
    이 계층의 몫이다.

    Args:
        table: 표시용 표
        identity: 식별 컬럼 (`IDENTITY_COLUMNS` 순서)
        extra: 식별 컬럼 뒤에 붙일 값 (신호 수·사건 수)

    Returns:
        식별 컬럼이 앞에 붙은 표
    """
    columns = {**identity, **(extra or {})}
    front = pd.DataFrame({name: [value] * len(table) for name, value in columns.items()}, index=table.index)

    return pd.concat([front, table], axis=1)


def _stack(blocks: Sequence[pd.DataFrame]) -> pd.DataFrame:
    """신호군별 조각을 한 표로 쌓는다.

    Args:
        blocks: 표 조각 목록

    Returns:
        쌓은 표 (조각이 없으면 빈 표)
    """
    if not blocks:
        return pd.DataFrame()

    return pd.concat(blocks, ignore_index=True)
