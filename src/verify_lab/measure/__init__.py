"""측정 공통 계층 패키지

forward return·베이스라인·통계·후보 판정을 담당한다. 어떤 검증이 자기를 쓰는지 몰라야 하므로
`studies` 를 import 하지 않으며, **판정도 축을 모른다** — 축 이름은 인자로 받는다.
"""

from .baseline import BelowMovingAverage, below_moving_average
from .distribution import DistributionShare, dividend_adjustment, measure_distribution_share
from .forward_return import ReturnBasis, compute_forward_returns, count_excluded
from .screening import screen_candidates
from .statistics import excess, max_non_overlapping, permutation_test, summarize

__all__ = [
    "BelowMovingAverage",
    "DistributionShare",
    "ReturnBasis",
    "below_moving_average",
    "compute_forward_returns",
    "count_excluded",
    "dividend_adjustment",
    "excess",
    "max_non_overlapping",
    "measure_distribution_share",
    "permutation_test",
    "screen_candidates",
    "summarize",
]
