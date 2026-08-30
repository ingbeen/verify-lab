"""통계 집계·초과분·유의성 판정

`forward_return.py` 가 낸 long-form 결과를 (기준 × 구간) 칸별로 요약하고, 베이스라인과 비교한다.

**제외된 칸은 표본이 아니다.** long-form 은 구간 끝이 데이터를 넘어간 칸도 행으로 남기므로,
그대로 세면 표본이 부풀고 평균이 왜곡된다. 결과만 보면 그럴듯해 보이기 때문에 이 계층에서
가장 조용히 틀릴 수 있는 지점이다.

유의성은 **순열 검정**으로 판정한다. 모집단에서 신호 수만큼 반복 추출해 "같은 표본 수로 우연히
뽑았을 때 이 값이 나오는 빈도"를 직접 세는 방식이라 정규성·독립 가정이 필요 없다. 이 프로젝트의
표본은 신호 몇 건에 실질 사건은 그보다 더 적어, 가정을 요구하는 검정은 깨진 채로 그럴듯한
숫자를 만들어낸다.

**유효 표본이 한 자릿수인 칸에는 검정을 붙이지 않는다.** 숫자를 만들어내는 것이 더 나쁘다.

**평균·중앙값과 함께 방향 비율도 검정한다.** 오른 비율이 기준선보다 낮은 것은 탈락 사유가 아니라
아래로 거는 신호이므로(루트 `CLAUDE.md` 측정의 원칙 11) 판정은 언제나 양측이다. 평균이 양수인데
절반 넘게 내린 칸은 소수의 큰 사건이 평균을 만든 것이라, 비율 축이 없으면 그 칸을 놓친다.
"""

import numpy as np
import pandas as pd

from verify_lab.common_constants import RATE_TO_PERCENT
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_EXCLUDED_COUNT,
    COL_EXCLUDED_REASON,
    COL_FORWARD_RETURN,
    COL_HORIZON,
    COL_SIGNAL_COUNT,
)
from verify_lab.measure.forward_return import count_excluded
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================
# 집계 결과 스키마
# ============================================================

COL_SAMPLE_COUNT = "SampleCount"
COL_MEAN = "Mean"
COL_MEDIAN = "Median"
COL_WIN_RATE = "WinRate"
COL_LOSS_RATE = "LossRate"
COL_MAX = "Max"
COL_MIN = "Min"
COL_STD = "Std"

SUMMARY_COLUMNS = [
    COL_BASIS,
    COL_HORIZON,
    COL_SIGNAL_COUNT,
    COL_EXCLUDED_COUNT,
    COL_SAMPLE_COUNT,
    COL_MEAN,
    COL_MEDIAN,
    COL_WIN_RATE,
    COL_LOSS_RATE,
    COL_MAX,
    COL_MIN,
    COL_STD,
]

# ============================================================
# 초과분 결과 스키마
# ============================================================

COL_SIGNAL_SAMPLE_COUNT = "SignalSampleCount"
COL_BASELINE_SAMPLE_COUNT = "BaselineSampleCount"
COL_MEAN_EXCESS = "MeanExcess"
COL_MEDIAN_EXCESS = "MedianExcess"
COL_WIN_RATE_EXCESS = "WinRateExcess"
COL_LOSS_RATE_EXCESS = "LossRateExcess"

EXCESS_COLUMNS = [
    COL_BASIS,
    COL_HORIZON,
    COL_SIGNAL_SAMPLE_COUNT,
    COL_BASELINE_SAMPLE_COUNT,
    COL_MEAN_EXCESS,
    COL_MEDIAN_EXCESS,
    COL_WIN_RATE_EXCESS,
    COL_LOSS_RATE_EXCESS,
]

# ============================================================
# 검정 결과 스키마
# ============================================================

COL_OBSERVED_MEAN = "ObservedMean"
COL_OBSERVED_MEDIAN = "ObservedMedian"
COL_NULL_MEAN_P05 = "NullMeanP05"
COL_NULL_MEAN_P95 = "NullMeanP95"
COL_MEAN_PERCENTILE = "MeanPercentile"
COL_MEAN_P_VALUE = "MeanPValue"
COL_MEDIAN_PERCENTILE = "MedianPercentile"
COL_MEDIAN_P_VALUE = "MedianPValue"

# 방향 비율의 검정 결과. **오른 비율과 내린 비율을 각각 둔다** — 둘은 여집합이 아니다.
# 보합(수익률이 정확히 0)이 어느 쪽에도 들어가지 않아 두 비율의 합이 100% 에 못 미친다
COL_OBSERVED_UP_RATE = "ObservedUpRate"
COL_UP_RATE_PERCENTILE = "UpRatePercentile"
COL_UP_RATE_P_VALUE = "UpRatePValue"
COL_OBSERVED_DOWN_RATE = "ObservedDownRate"
COL_DOWN_RATE_PERCENTILE = "DownRatePercentile"
COL_DOWN_RATE_P_VALUE = "DownRatePValue"

COL_TEST_NOTE = "TestNote"

TEST_COLUMNS = [
    COL_BASIS,
    COL_HORIZON,
    COL_SAMPLE_COUNT,
    COL_OBSERVED_MEAN,
    COL_OBSERVED_MEDIAN,
    COL_NULL_MEAN_P05,
    COL_NULL_MEAN_P95,
    COL_MEAN_PERCENTILE,
    COL_MEAN_P_VALUE,
    COL_MEDIAN_PERCENTILE,
    COL_MEDIAN_P_VALUE,
    COL_OBSERVED_UP_RATE,
    COL_UP_RATE_PERCENTILE,
    COL_UP_RATE_P_VALUE,
    COL_OBSERVED_DOWN_RATE,
    COL_DOWN_RATE_PERCENTILE,
    COL_DOWN_RATE_P_VALUE,
    COL_TEST_NOTE,
]

# 검정 불가 사유. 검정한 칸은 빈 문자열이다
NOTE_NONE = ""
NOTE_TOO_FEW_SAMPLES = "표본 부족으로 검정 불가"
NOTE_POPULATION_TOO_SMALL = "모집단이 표본보다 작아 검정 불가"

# 유효 표본이 한 자릿수인 칸에는 검정을 붙이지 않는다
# (docs/spec/index_extreme_events.md §6). 백분위도 함께 비운다 —
# 백분위는 사실상 검정 통계량이라 남겨두면 유의성으로 읽힌다
MIN_SAMPLE_FOR_TEST = 10

# 귀무분포 반복 수와 난수 시드. 시드 없는 난수는 금지이며, 결과 문서에 시드를 적어야 재현된다
DEFAULT_REPEAT_COUNT = 1_000
DEFAULT_RANDOM_SEED = 0

# 귀무분포에서 함께 보고하는 분위 (0~1 비율)
NULL_LOWER_QUANTILE = 0.05
NULL_UPPER_QUANTILE = 0.95


def summarize(frame: pd.DataFrame) -> pd.DataFrame:
    """(기준 × 구간) 칸별로 수익률 분포를 요약한다.

    신호 수와 제외 수는 `count_excluded()` 를 재사용해 낸다 — 같은 수를 두 곳에서 세면
    두 값이 조용히 갈라진다. 유효 표본은 **값이 있는 행만** 센다.

    표본이 0건이면 통계량이 비어 있는 채로(NaN) 나온다. 예외가 아니라 "계산 불가"라는
    정상적인 결과다. 표본 1건의 표준편차도 마찬가지다 — 0으로 채우면 "변동이 없다"로 읽힌다.

    Args:
        frame: `compute_forward_returns` 의 결과

    Returns:
        `SUMMARY_COLUMNS` 순서의 요약표. 기준·구간 오름차순으로 정렬된다

    Raises:
        ValueError: 필요한 컬럼이 없는 경우
    """
    _validate_result_frame(frame)

    counts = count_excluded(frame)
    usable = frame[frame[COL_FORWARD_RETURN].notna()].copy()

    if usable.empty:
        summary = counts.assign(
            **{
                column: np.nan
                for column in (COL_MEAN, COL_MEDIAN, COL_WIN_RATE, COL_LOSS_RATE, COL_MAX, COL_MIN, COL_STD)
            }
        )
        summary[COL_SAMPLE_COUNT] = 0
        return summary[SUMMARY_COLUMNS]

    # 승률은 양수 비율이다. 정확히 0인 날은 승리가 아니다
    usable[COL_WIN_RATE] = usable[COL_FORWARD_RETURN] > 0

    # 하락 비율은 **승률의 여집합이 아니다.** 보합(정확히 0)이 어느 쪽에도 들어가지 않으므로
    # `1 − 승률` 로 만들면 보합이 하락으로 새어 들어가 값이 부푼다
    usable[COL_LOSS_RATE] = usable[COL_FORWARD_RETURN] < 0

    grouped = usable.groupby([COL_BASIS, COL_HORIZON], as_index=False, sort=True).agg(
        **{
            COL_SAMPLE_COUNT: (COL_FORWARD_RETURN, "size"),
            COL_MEAN: (COL_FORWARD_RETURN, "mean"),
            COL_MEDIAN: (COL_FORWARD_RETURN, "median"),
            COL_WIN_RATE: (COL_WIN_RATE, "mean"),
            COL_LOSS_RATE: (COL_LOSS_RATE, "mean"),
            COL_MAX: (COL_FORWARD_RETURN, "max"),
            COL_MIN: (COL_FORWARD_RETURN, "min"),
            COL_STD: (COL_FORWARD_RETURN, "std"),
        }
    )

    # 표본이 0건인 칸도 남겨야 하므로 신호 수 쪽을 기준으로 붙인다
    summary = counts.merge(grouped, on=[COL_BASIS, COL_HORIZON], how="left")
    summary[COL_SAMPLE_COUNT] = summary[COL_SAMPLE_COUNT].fillna(0).astype(int)

    return summary[SUMMARY_COLUMNS]


def excess(signal_summary: pd.DataFrame, baseline_summary: pd.DataFrame) -> pd.DataFrame:
    """신호군과 베이스라인의 초과분을 낸다.

    **통계량끼리 대응해 뺀다** — 평균은 평균과, 중앙값은 중앙값과, 승률은 승률과. 따라서
    중앙값 초과는 "중앙값의 차이"이지 "차이의 중앙값"이 아니다. 베이스라인이 하나의 숫자가
    아니라 분포이고 신호일과 베이스라인 날짜가 달라, 신호 하나에 대응하는 베이스라인 값이
    애초에 없기 때문이다.

    양쪽 표본 수를 모두 남긴다. 표본 수가 크게 다르다는 사실 자체가 해석의 일부다.

    Args:
        signal_summary: 신호군의 `summarize` 결과
        baseline_summary: 베이스라인의 `summarize` 결과

    Returns:
        `EXCESS_COLUMNS` 순서의 초과분표

    Raises:
        ValueError: 필요한 컬럼이 없거나 두 집계의 칸 구성이 다른 경우
    """
    for label, summary in (("신호", signal_summary), ("베이스라인", baseline_summary)):
        missing_columns = set(SUMMARY_COLUMNS) - set(summary.columns)
        if missing_columns:
            raise ValueError(f"{label} 집계에 필수 컬럼이 누락되었습니다: {sorted(missing_columns)}")

    signal_cells = _cell_keys(signal_summary)
    baseline_cells = _cell_keys(baseline_summary)
    if signal_cells != baseline_cells:
        raise ValueError(
            "두 집계의 칸 구성이 다릅니다: "
            f"신호에만 {sorted(signal_cells - baseline_cells)}, "
            f"베이스라인에만 {sorted(baseline_cells - signal_cells)}"
        )

    merged = signal_summary.merge(baseline_summary, on=[COL_BASIS, COL_HORIZON], suffixes=("_signal", "_baseline"))

    result = pd.DataFrame(
        {
            COL_BASIS: merged[COL_BASIS],
            COL_HORIZON: merged[COL_HORIZON],
            COL_SIGNAL_SAMPLE_COUNT: merged[f"{COL_SAMPLE_COUNT}_signal"],
            COL_BASELINE_SAMPLE_COUNT: merged[f"{COL_SAMPLE_COUNT}_baseline"],
            COL_MEAN_EXCESS: merged[f"{COL_MEAN}_signal"] - merged[f"{COL_MEAN}_baseline"],
            COL_MEDIAN_EXCESS: merged[f"{COL_MEDIAN}_signal"] - merged[f"{COL_MEDIAN}_baseline"],
            COL_WIN_RATE_EXCESS: merged[f"{COL_WIN_RATE}_signal"] - merged[f"{COL_WIN_RATE}_baseline"],
            COL_LOSS_RATE_EXCESS: merged[f"{COL_LOSS_RATE}_signal"] - merged[f"{COL_LOSS_RATE}_baseline"],
        }
    )

    return result[EXCESS_COLUMNS]


def permutation_test(
    signal_frame: pd.DataFrame,
    population_frame: pd.DataFrame,
    *,
    repeats: int = DEFAULT_REPEAT_COUNT,
    seed: int = DEFAULT_RANDOM_SEED,
) -> pd.DataFrame:
    """모집단에서 신호 수만큼 반복 추출해 관측값이 얼마나 드문지 잰다.

    칸마다 모집단에서 **신호 수와 같은 개수를 비복원 추출**하는 것을 반복해 귀무분포를 만들고,
    관측된 평균·중앙값이 그 분포의 어디에 있는지 낸다. "같은 표본 수로 우연히 뽑았을 때
    이 값이 나오는 빈도"를 직접 세는 것이므로 정규성·독립 가정이 필요 없다.

    평균과 중앙값을 모두 검정한다. **평균은 드문데 중앙값은 그렇지 않다면 소수 사건이
    결과를 만들었다는 신호**이며, 이 프로젝트가 반드시 드러내야 하는 상황이다.

    **오른 비율과 내린 비율도 각각 검정한다.** 둘은 여집합이 아니다 — 보합이 어느 쪽에도
    들어가지 않으므로 한쪽만 재고 나머지를 빼서 만들면 값이 부푼다. 판정은 양측이라
    **기준선보다 낮은 비율도 유의하게 잡힌다** — 그것이 아래로 거는 신호다.

    p 값은 `(관측만큼 극단인 횟수 + 1) ÷ (반복 수 + 1)` 로 낸다. 0 이 나오면 "절대 우연이
    아니다"로 읽히지만 실제로는 반복 수의 한계일 뿐이다.

    Args:
        signal_frame: 신호군의 `compute_forward_returns` 결과
        population_frame: 베이스라인 모집단의 `compute_forward_returns` 결과
        repeats: 귀무분포를 만들 반복 수 (1 이상)
        seed: 난수 시드. 결과 문서에 기록해야 재현된다

    Returns:
        `TEST_COLUMNS` 순서의 검정표. 검정하지 않은 칸은 사유가 채워지고 결과가 비어 있다

    Raises:
        ValueError: 반복 수가 1 미만이거나 필요한 컬럼이 없는 경우
    """
    if repeats < 1:
        raise ValueError(f"반복 수는 1 이상이어야 합니다: {repeats}")

    _validate_result_frame(signal_frame)
    _validate_result_frame(population_frame)

    rng = np.random.default_rng(seed)
    cells = signal_frame[[COL_BASIS, COL_HORIZON]].drop_duplicates().sort_values([COL_BASIS, COL_HORIZON])

    rows = [
        _test_cell(
            basis,
            horizon,
            _cell_values(signal_frame, basis, horizon),
            _cell_values(population_frame, basis, horizon),
            repeats,
            rng,
        )
        for basis, horizon in zip(cells[COL_BASIS].tolist(), cells[COL_HORIZON].tolist(), strict=True)
    ]

    result = pd.DataFrame(rows, columns=TEST_COLUMNS)
    tested = int((result[COL_TEST_NOTE] == NOTE_NONE).sum())
    logger.debug(f"순열 검정 완료: {tested}/{len(result)}칸 검정, 반복 {repeats:,}회, 시드 {seed}")

    return result


def _validate_result_frame(frame: pd.DataFrame) -> None:
    """long-form 결과 프레임인지 확인한다.

    Args:
        frame: 검사할 프레임

    Raises:
        ValueError: 필요한 컬럼이 없는 경우
    """
    missing_columns = {COL_BASIS, COL_HORIZON, COL_FORWARD_RETURN, COL_EXCLUDED_REASON} - set(frame.columns)
    if missing_columns:
        raise ValueError(f"필수 컬럼이 누락되었습니다: {sorted(missing_columns)}")


def _cell_keys(summary: pd.DataFrame) -> set[tuple[object, object]]:
    """집계표의 (기준, 구간) 칸 집합을 만든다.

    Args:
        summary: `summarize` 결과

    Returns:
        칸 키 집합
    """
    return set(zip(summary[COL_BASIS].tolist(), summary[COL_HORIZON].tolist(), strict=True))


def _cell_values(frame: pd.DataFrame, basis: object, horizon: object) -> np.ndarray:
    """한 칸의 유효한 수익률만 배열로 꺼낸다.

    Args:
        frame: long-form 결과
        basis: 수익률 기준점 값
        horizon: 측정 구간

    Returns:
        제외된 칸을 뺀 수익률 배열
    """
    cell = frame[(frame[COL_BASIS] == basis) & (frame[COL_HORIZON] == horizon)]

    return cell[COL_FORWARD_RETURN].dropna().to_numpy(dtype=float)


def _test_cell(
    basis: object,
    horizon: object,
    observed: np.ndarray,
    pool: np.ndarray,
    repeats: int,
    rng: np.random.Generator,
) -> dict[str, object]:
    """한 칸을 검정한다. 검정할 수 없으면 사유를 남긴다.

    Args:
        basis: 수익률 기준점 값
        horizon: 측정 구간
        observed: 신호군의 유효 수익률
        pool: 모집단의 유효 수익률
        repeats: 반복 수
        rng: 난수 생성기

    Returns:
        검정표 한 줄
    """
    sample_count = int(observed.size)
    row: dict[str, object] = {
        COL_BASIS: basis,
        COL_HORIZON: horizon,
        COL_SAMPLE_COUNT: sample_count,
        COL_OBSERVED_MEAN: float(observed.mean()) if sample_count else np.nan,
        COL_OBSERVED_MEDIAN: float(np.median(observed)) if sample_count else np.nan,
        COL_NULL_MEAN_P05: np.nan,
        COL_NULL_MEAN_P95: np.nan,
        COL_MEAN_PERCENTILE: np.nan,
        COL_MEAN_P_VALUE: np.nan,
        COL_MEDIAN_PERCENTILE: np.nan,
        COL_MEDIAN_P_VALUE: np.nan,
        # 관측 비율은 **검정하지 않는 칸에도 남긴다.** 표본이 적다는 것과 값이 없다는 것은 다르고,
        # 비율은 표본 수와 함께 읽으면 그 자체로 사실이다
        COL_OBSERVED_UP_RATE: float((observed > 0).mean()) if sample_count else np.nan,
        COL_UP_RATE_PERCENTILE: np.nan,
        COL_UP_RATE_P_VALUE: np.nan,
        COL_OBSERVED_DOWN_RATE: float((observed < 0).mean()) if sample_count else np.nan,
        COL_DOWN_RATE_PERCENTILE: np.nan,
        COL_DOWN_RATE_P_VALUE: np.nan,
        COL_TEST_NOTE: NOTE_NONE,
    }

    if sample_count < MIN_SAMPLE_FOR_TEST:
        row[COL_TEST_NOTE] = NOTE_TOO_FEW_SAMPLES
        return row

    if pool.size < sample_count:
        row[COL_TEST_NOTE] = NOTE_POPULATION_TOO_SMALL
        return row

    null_means, null_medians, null_up_rates, null_down_rates = _null_distribution(pool, sample_count, repeats, rng)
    observed_mean = float(observed.mean())
    observed_median = float(np.median(observed))
    observed_up_rate = float((observed > 0).mean())
    observed_down_rate = float((observed < 0).mean())

    row[COL_NULL_MEAN_P05] = float(np.quantile(null_means, NULL_LOWER_QUANTILE))
    row[COL_NULL_MEAN_P95] = float(np.quantile(null_means, NULL_UPPER_QUANTILE))
    row[COL_MEAN_PERCENTILE] = _percentile(null_means, observed_mean)
    row[COL_MEAN_P_VALUE] = _two_sided_p_value(null_means, observed_mean)
    row[COL_MEDIAN_PERCENTILE] = _percentile(null_medians, observed_median)
    row[COL_MEDIAN_P_VALUE] = _two_sided_p_value(null_medians, observed_median)
    row[COL_UP_RATE_PERCENTILE] = _percentile(null_up_rates, observed_up_rate)
    row[COL_UP_RATE_P_VALUE] = _two_sided_p_value(null_up_rates, observed_up_rate)
    row[COL_DOWN_RATE_PERCENTILE] = _percentile(null_down_rates, observed_down_rate)
    row[COL_DOWN_RATE_P_VALUE] = _two_sided_p_value(null_down_rates, observed_down_rate)

    return row


def _null_distribution(
    pool: np.ndarray, size: int, repeats: int, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """모집단에서 `size` 개를 비복원 추출하는 것을 `repeats` 회 반복한다.

    행마다 난수 키를 만들어 부분 정렬하는 방식으로 한 번에 벡터화한다.
    `rng.choice(..., replace=False)` 에 2차원 크기를 주면 **행별 비복원이 아니라
    전체 비복원**이 되어 원하는 추출이 되지 않는다.

    **네 통계량을 같은 추출 표본에서 낸다.** 축마다 따로 뽑으면 같은 시드에서도 축끼리
    다른 표본을 보게 되어, 한 칸 안에서 평균과 비율의 판정 근거가 어긋난다.

    Args:
        pool: 모집단 값
        size: 한 번에 뽑을 개수
        repeats: 반복 수
        rng: 난수 생성기

    Returns:
        반복별 평균·중앙값·오른 비율·내린 비율 배열
    """
    keys = rng.random((repeats, pool.size))
    picked = np.argpartition(keys, size - 1, axis=1)[:, :size]
    samples = pool[picked]

    return (
        samples.mean(axis=1),
        np.median(samples, axis=1),
        (samples > 0).mean(axis=1),
        (samples < 0).mean(axis=1),
    )


def _percentile(null_values: np.ndarray, observed: float) -> float:
    """관측값이 귀무분포의 몇 백분위에 있는지 낸다.

    Args:
        null_values: 귀무분포
        observed: 관측된 통계량

    Returns:
        백분위 (0~100)
    """
    return float((null_values < observed).mean()) * RATE_TO_PERCENT


def _two_sided_p_value(null_values: np.ndarray, observed: float) -> float:
    """귀무분포 중심에서 관측값만큼 멀리 떨어진 값의 비율을 낸다 (양측).

    분자·분모에 1을 더한다. 그렇게 하지 않으면 0 이 나오는데, 0 은 "절대 우연이 아니다"로
    읽히지만 실제로는 반복 수가 유한하다는 뜻일 뿐이다.

    Args:
        null_values: 귀무분포
        observed: 관측된 통계량

    Returns:
        양측 p 값
    """
    center = float(null_values.mean())
    extreme = int((np.abs(null_values - center) >= abs(observed - center)).sum())

    return (extreme + 1) / (null_values.size + 1)
