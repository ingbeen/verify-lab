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

from collections.abc import Sequence
from typing import NamedTuple

import numpy as np
import numpy.typing as npt
import pandas as pd

from verify_lab.measure.constants import (
    COL_BASIS,
    COL_EXCLUDED_COUNT,
    COL_EXCLUDED_REASON,
    COL_FORWARD_RETURN,
    COL_HORIZON,
    COL_SIGNAL_COUNT,
    HALF_RATE,
    JUDGEABLE_NO,
    JUDGEABLE_YES,
    MIN_SAMPLE_PER_CELL,
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

# 손익비의 두 재료. **어느 쪽이 「이긴 것」인지 정하지 않는다** — 방향은 이 계층이 모르고
# (측정의 원칙 11) 부르는 쪽이 정한다. 음수 평균은 **절대값**이라 둘 다 양의 값이다.
# 건수를 함께 내는 것은 **손익비의 분모가 전체 표본이 아니라 한쪽 건수**이기 때문이다 —
# 적중률이 28건으로 만든 값일 때 손익비는 5건으로 만든 값일 수 있고, 그 사실이 표에 없으면
# 5건으로 만든 1.034 와 2건으로 만든 16.822 가 같은 무게로 읽힌다 (측정의 원칙 3)
COL_POSITIVE_MEAN = "PositiveMean"
COL_NEGATIVE_MEAN = "NegativeMean"
COL_POSITIVE_COUNT = "PositiveCount"
COL_NEGATIVE_COUNT = "NegativeCount"

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
    COL_POSITIVE_MEAN,
    COL_NEGATIVE_MEAN,
    COL_POSITIVE_COUNT,
    COL_NEGATIVE_COUNT,
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

# 모집단이 표본보다 **작거나 같으면** 검정이 성립하지 않는다. 같을 때도 막는 것은
# 비복원 추출이 매번 모집단 전체를 뽑아 **귀무분포가 상수가 되기** 때문이다 —
# 그러면 우연확률이 언제나 1.0 인데, 사유가 없으면 「검정했더니 유의하지 않다」로 읽힌다
NOTE_POPULATION_NOT_LARGER = "모집단이 표본보다 크지 않아 검정 불가"

# 유효 표본이 하한에 못 미치는 칸에는 검정을 붙이지 않는다
# (docs/spec/역방향_설계.md §6). 백분위도 함께 비운다 —
# 백분위는 사실상 검정 통계량이라 남겨두면 유의성으로 읽힌다.
# **하한은 `measure/constants.py` 가 소유한다** — 축을 쪼갤 때 쓰는 것과 같은 값이다

# 귀무분포 반복 수와 난수 시드. 시드 없는 난수는 금지이며, 결과 문서에 시드를 적어야 재현된다
DEFAULT_REPEAT_COUNT = 1_000
DEFAULT_RANDOM_SEED = 0

# 귀무분포에서 함께 보고하는 분위 (0~1 비율)
NULL_LOWER_QUANTILE = 0.05
NULL_UPPER_QUANTILE = 0.95


def max_non_overlapping(start_positions: Sequence[int], horizon: int) -> int:
    """겹치지 않게 고를 수 있는 구간의 최대 개수를 센다.

    롤링 전수는 이웃끼리 심하게 겹쳐, 표본 수만 적으면 실제보다 훨씬 단단해 보인다.
    이 값이 그 겹침을 드러내는 유일한 축이다.

    시작일이 이르면 끝나는 것도 이르므로 **가장 이른 것부터 집는 그리디가 최적**이다
    (구간 스케줄링). 근사가 아니라 정확한 최대값이며, **나눗셈으로 근사하지 않는다** —
    축으로 걸러 시작일이 흩어진 칸에서는 맞지 않는다.

    **끝점을 공유하는 두 구간은 「겹치지 않음」이다.** 구간 `[p, p+h]` 와 `[p+h, p+2h]` 는
    관측일 하나를 공유하지만 **수익률 구간이 겹치지 않아** 통계적으로 독립이다. 하루를 더
    띄우면 실제보다 표본을 적게 세게 된다.

    **이 함수가 공통 계층에 있는 이유**: 검증마다 따로 구현하면 끝점 처리 같은 한 칸 차이가
    생기고, 같은 이름의 컬럼이 다른 뜻을 갖게 되면 두 결과 문서를 나란히 읽을 수 없다.

    Args:
        start_positions: 시작일의 거래일 위치 목록. 정렬돼 있지 않아도 된다
        horizon: 보유 기간 (거래일, 1 이상)

    Returns:
        서로 겹치지 않는 구간의 최대 개수

    Raises:
        ValueError: 보유 기간이 1 미만인 경우
    """
    if horizon < 1:
        raise ValueError(f"보유 기간은 1 이상이어야 합니다: {horizon}")

    count = 0
    next_available = -1

    for position in sorted(start_positions):
        if position >= next_available:
            count += 1
            next_available = position + horizon

    return count


def judgeable(sample_count: int) -> str:
    """그 칸을 판정에 써도 되는지의 표기를 낸다.

    **식이 저장소에 한 벌만 있어야 한다.** 값(`MIN_SAMPLE_PER_CELL`)은 공통 계층이 소유했는데
    **식은 다섯 곳에 있었다** — 검증 셋과 매매 계층이 각자 삼항식을 썼다. 하한을 바꿔도
    한 곳이 안 따라오면 **예외 없이** 두 산출물의 `판정가능` 이 다른 기준으로 찍힌다.

    **미달이어도 행은 남긴다** (측정의 원칙 17). 이 값이 「판정에 쓰지 말라」를 표에 남기는 자리다.

    Args:
        sample_count: 그 칸의 유효 표본 수

    Returns:
        `예` 또는 `아니오`

    Raises:
        ValueError: 표본 수가 음수인 경우
    """
    if sample_count < 0:
        raise ValueError(f"표본 수는 0 이상이어야 합니다: {sample_count}")

    return JUDGEABLE_YES if sample_count >= MIN_SAMPLE_PER_CELL else JUDGEABLE_NO


def mean_rate_conflict(frame: pd.DataFrame) -> pd.Series:
    """평균의 부호와 방향 비율이 어긋나는 칸을 표시한다 (측정의 원칙 13).

    평균이 양수인데 절반 넘게 내렸다면 **소수의 큰 사건이 평균을 만든 것**이고, 그 반대도 같다.
    평균만 보고 방향을 읽으면 이런 칸에서 정반대로 판단하게 된다 — 실물 사례가 SPY 3월
    만기다(평균 +0.257% · 중앙값 −0.348% · 내린 비율 64.7%).

    **공통 계층이 소유한다.** 전에는 `studies/month_end/runner.py` 와
    `studies/option_expiry/runner.py` 에 **docstring 까지 바이트 단위로 같은 함수**가 있었고
    둘 다 자기 docstring 에 「측정의 원칙 13」이라고 적어 두었다. 원칙이 모든 검증에 요구하는
    것을 검증마다 구현하면 같은 원칙이 다른 답을 낸다.

    Args:
        frame: 평균과 **두 방향 비율**이 들어 있는 집계 프레임

    Returns:
        어긋나는 칸이면 True 인 Series

    Raises:
        ValueError: 필요한 컬럼이 없는 경우
    """
    missing = [column for column in (COL_MEAN, COL_WIN_RATE, COL_LOSS_RATE) if column not in frame.columns]
    if missing:
        raise ValueError(f"어긋남 판정에 필요한 컬럼이 없습니다: {missing}")

    mean_up_but_fell = (frame[COL_MEAN] > 0) & (frame[COL_LOSS_RATE] > HALF_RATE)
    mean_down_but_rose = (frame[COL_MEAN] < 0) & (frame[COL_WIN_RATE] > HALF_RATE)

    return mean_up_but_fell | mean_down_but_rose


class PayoffProfile(NamedTuple):
    """손익비와 그 값을 읽는 데 필요한 것.

    **분자와 분모도 함께 낸다.** `docs/strategy/투자금_결정.md` §1.2 가 그 두 값을
    성적표의 입력으로 적어 두었는데 실제 표에는 없었다. 여기서 이미 구한 값이라
    내보내기만 하면 되고, 부르는 쪽이 다시 계산하면 **산식이 두 벌**이 된다.

    Attributes:
        payoff_ratio: 이길 때 평균 ÷ 질 때 평균. **진 적이 없으면 `NaN`** 이다
        breakeven_hit_rate: 이 적중률을 넘어야 번다 (비율). 손익비가 없으면 `NaN`
        losing_count: 손익비의 **분모가 된 표본 수**
        winning_mean: 이길 때 평균 (비율, **절대값**). 이긴 적이 없으면 `NaN`
        losing_mean: 질 때 평균 (비율, **절대값**). 진 적이 없으면 `NaN`.
            **부호를 붙이는 것은 표시 계층의 몫이다** — 이 계층은 방향을 모른다
    """

    payoff_ratio: float
    breakeven_hit_rate: float
    losing_count: int
    winning_mean: float
    losing_mean: float


def _require_positive_mean(count: int, mean: float, label: str) -> None:
    """건수가 있는 쪽의 평균이 양수인지 확인한다.

    두 평균 모두 절대값이므로 건수가 있으면 그 평균은 반드시 양수다. **그런데 비어 있어도
    예외가 나지 않는 길이 있었다** — 손익비가 조용히 `NaN` 이 되고, 판정에서 `NaN >= 1.0` 이
    거짓이라 **「못 잰 칸」이 「못 넘은 칸」으로** 바뀐다. 이제 `이길 때(%)` 도 산출물에
    나가므로 같은 값이 **빈칸으로도** 새어 나간다.

    Args:
        count: 그쪽 건수
        mean: 그쪽 평균 (절대값)
        label: 오류 메시지에 쓸 이름 (`이긴`·`진`)

    Raises:
        RuntimeError: 건수가 있는데 평균이 양수가 아닌 경우 (내부 불변조건 위반)
    """
    if count > 0 and not mean > 0:
        raise RuntimeError(f"내부 불변조건 위반: {label} 거래 {count}건의 평균이 양수가 아닙니다 ({mean})")


def payoff_profile(
    *,
    positive_mean: float,
    negative_mean: float,
    positive_count: int,
    negative_count: int,
    sample_count: int,
    downward: bool,
) -> PayoffProfile:
    """방향을 받아 손익비를 조립한다.

    **산식이 저장소에 한 벌만 있어야 한다.** 판정 계층과 매매 계층이 각자 계산하면 두 곳이
    조용히 갈라지고, 그때 어느 쪽이 맞는지 판별할 방법이 없다 (판정식 단일화).

    **방향을 인자로 받는 것은 방향을 「고르는」 것이 아니다.** 고르는 쪽은 부르는 계층이고,
    이 계층의 산출물에는 방향이 남지 않는다 (측정의 원칙 11).

    **손익분기는 전체 표본을 분모로 낸다.** 이 값은 같은 표의 적중률과 견주라고 있는 것인데,
    적중률의 분모는 전체 표본이고 손익비의 분모는 이긴 것과 진 것뿐이다. **보합이 있으면 둘이
    어긋나므로** `1 ÷ (1 + 손익비)` 가 아니라 결정된 거래의 비율을 곱한 값을 쓴다 — 그러지 않으면
    보합만큼 손익분기가 과대평가되고, 실측에서 코스닥 월말 성적표 2,400행 중 54행이 그 경우였다.

    **분자가 없는 것과 분모가 없는 것은 뜻이 다르다.**

    | 없는 쪽 | 값 | 왜 |
    | --- | --- | --- |
    | 이긴 거래 | 손익비 `0.0` | 버는 것이 없다. 손익분기는 결정된 거래 전부를 이겨야 하는 값이 된다 |
    | 진 거래 | 손익비 `NaN` · 손익분기 `NaN` | 수학적으로 무한대라 숫자로 적을 수 없다. **판정에서는 「어떤 기준도 넘는다」로 다뤄야 하며**, 비운 것을 미충족으로 세면 가장 좋은 칸이 깎인다 |

    Args:
        positive_mean: 수익률이 양수인 건들의 평균 (비율). 없으면 `NaN`
        negative_mean: 수익률이 음수인 건들의 **절대값** 평균 (비율). 없으면 `NaN`
        positive_count: 양수인 건수
        negative_count: 음수인 건수
        sample_count: 유효 표본 수. **보합을 포함한 전체**이며 손익분기의 분모가 된다
        downward: 아래로 거는 칸인가. 참이면 음수 쪽이 「이길 때」다

    Returns:
        손익비·손익분기 적중률·질 때 표본 수

    Raises:
        ValueError: 건수가 음수인 경우
        RuntimeError: 결정된 거래가 표본보다 많거나, 건수가 있는 쪽의 평균이 양수가 아닌 경우
            (내부 불변조건 위반)
    """
    if positive_count < 0 or negative_count < 0:
        raise ValueError(f"건수는 0 이상이어야 합니다: 양수 {positive_count}, 음수 {negative_count}")

    decided_count = positive_count + negative_count
    if decided_count > sample_count:
        raise RuntimeError(f"내부 불변조건 위반: 결정된 거래 {decided_count}건이 표본 {sample_count}건보다 많습니다")

    winning_mean = negative_mean if downward else positive_mean
    losing_mean = positive_mean if downward else negative_mean
    winning_count = negative_count if downward else positive_count
    losing_count = positive_count if downward else negative_count

    # **진 적이 없어도 이길 때 평균은 존재한다.** 둘을 함께 비우면 전승 칸의 성적을 읽을 수 없다.
    # **그래서 이긴 쪽 불변조건을 이 갈래에서도 건다** — 값을 내보내기 시작한 순간부터
    # 「건수는 있는데 평균이 없다」가 조용히 `이길 때(%)` 의 빈칸으로 흘러가기 때문이다
    if losing_count == 0:
        _require_positive_mean(winning_count, winning_mean, "이긴")

        return PayoffProfile(np.nan, np.nan, 0, winning_mean if winning_count else np.nan, np.nan)

    # 두 평균 모두 절대값이므로 건수가 있으면 그 평균은 반드시 양수다. 진 쪽이 0 이면 아래에서
    # 0 으로 나누게 되고, 이긴 쪽이 비어 있으면 손익비가 조용히 `NaN` 이 되어 **잴 수 없었던 칸이
    # 「기준을 못 넘은 칸」으로 바뀐다.** 어느 쪽도 그냥 넘기지 않는다
    _require_positive_mean(losing_count, losing_mean, "진")
    _require_positive_mean(winning_count, winning_mean, "이긴")

    ratio = 0.0 if winning_count == 0 else winning_mean / losing_mean

    return PayoffProfile(
        ratio,
        (decided_count / sample_count) / (1.0 + ratio),
        losing_count,
        winning_mean if winning_count else np.nan,
        losing_mean,
    )


def payoff_from_returns(returns: npt.ArrayLike) -> PayoffProfile:
    """수익률 목록에서 바로 손익비를 낸다.

    **매매 계층을 위한 진입점이다.** `strategy` 는 `summarize` 를 쓰지 않고 체결 수익률을
    직접 들고 있는데, 거기서 손익비를 따로 계산하면 **산식이 두 벌**이 되어 조용히 갈라진다.
    이 함수는 양수·음수를 갈라 `payoff_profile` 에 넘길 뿐 판정을 더하지 않는다.

    **방향 인자를 두지 않는다.** 매매 계층의 수익률은 **이미 방향이 반영된 실현 손익**이라
    아래로 거는 칸도 그 규칙대로 벌면 양수로 들어온다. 부호를 뒤집지 않은 값을 다뤄야 하는
    자리가 생기면 `payoff_profile` 을 직접 부른다.

    Args:
        returns: 수익률 목록 (비율). 보합(정확히 0)은 양쪽 어디에도 들어가지 않지만
            **손익분기의 분모에는 들어간다**

    Returns:
        손익비·손익분기 적중률·질 때 표본 수
    """
    values = np.asarray(returns, dtype=float)
    positive = values[values > 0]
    negative = -values[values < 0]

    return payoff_profile(
        positive_mean=float(positive.mean()) if positive.size else np.nan,
        negative_mean=float(negative.mean()) if negative.size else np.nan,
        positive_count=int(positive.size),
        negative_count=int(negative.size),
        sample_count=int(values.size),
        downward=False,
    )


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
                for column in (
                    COL_MEAN,
                    COL_MEDIAN,
                    COL_WIN_RATE,
                    COL_LOSS_RATE,
                    COL_MAX,
                    COL_MIN,
                    COL_STD,
                    COL_POSITIVE_MEAN,
                    COL_NEGATIVE_MEAN,
                )
            }
        )
        for column in (COL_SAMPLE_COUNT, COL_POSITIVE_COUNT, COL_NEGATIVE_COUNT):
            summary[column] = 0
        return summary[SUMMARY_COLUMNS]

    # 승률은 양수 비율이다. 정확히 0인 날은 승리가 아니다
    usable[COL_WIN_RATE] = usable[COL_FORWARD_RETURN] > 0

    # 하락 비율은 **승률의 여집합이 아니다.** 보합(정확히 0)이 어느 쪽에도 들어가지 않으므로
    # `1 − 승률` 로 만들면 보합이 하락으로 새어 들어가 값이 부푼다
    usable[COL_LOSS_RATE] = usable[COL_FORWARD_RETURN] < 0

    # 해당하지 않는 행을 **비워서**(NaN) 둔다. `mean` 은 그것을 분모에서 빼고 `count` 는
    # 세지 않으므로, 보합이 양쪽 어디에도 들어가지 않는 것이 산식 하나로 함께 성립한다.
    # 0 으로 채우면 평균이 0 쪽으로 끌려가고 건수가 부푼다
    usable[COL_POSITIVE_MEAN] = usable[COL_FORWARD_RETURN].where(usable[COL_FORWARD_RETURN] > 0)
    usable[COL_NEGATIVE_MEAN] = (-usable[COL_FORWARD_RETURN]).where(usable[COL_FORWARD_RETURN] < 0)

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
            COL_POSITIVE_MEAN: (COL_POSITIVE_MEAN, "mean"),
            COL_NEGATIVE_MEAN: (COL_NEGATIVE_MEAN, "mean"),
            COL_POSITIVE_COUNT: (COL_POSITIVE_MEAN, "count"),
            COL_NEGATIVE_COUNT: (COL_NEGATIVE_MEAN, "count"),
        }
    )

    # 표본이 0건인 칸도 남겨야 하므로 신호 수 쪽을 기준으로 붙인다
    summary = counts.merge(grouped, on=[COL_BASIS, COL_HORIZON], how="left")
    for column in (COL_SAMPLE_COUNT, COL_POSITIVE_COUNT, COL_NEGATIVE_COUNT):
        summary[column] = summary[column].fillna(0).astype(int)

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

    if sample_count < MIN_SAMPLE_PER_CELL:
        row[COL_TEST_NOTE] = NOTE_TOO_FEW_SAMPLES
        return row

    if pool.size <= sample_count:
        row[COL_TEST_NOTE] = NOTE_POPULATION_NOT_LARGER
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
    """관측값이 귀무분포의 어느 위치에 있는지 낸다.

    **비율(0~1)로 낸다.** 계층 간 계약이 "`measure` 는 비율 그대로, 저장 직전 백분율"로
    정했고 이 값만 예외로 두면 출력 계층마다 다르게 취급한다 — 한쪽은 백분율로 보고 2자리,
    다른 쪽은 확률로 보고 4자리로 반올림하게 된다.

    Args:
        null_values: 귀무분포
        observed: 관측된 통계량

    Returns:
        귀무분포에서 관측값보다 작은 값의 비율 (0~1)
    """
    return float((null_values < observed).mean())


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
