"""측정 공통 계층 패키지

forward return·베이스라인·통계를 담당한다. 어떤 검증이 자기를 쓰는지 몰라야 하므로
`studies` 를 import 하지 않는다.
"""

from .baseline import BelowMovingAverage, MovingAverageKind, below_moving_average
from .forward_return import ReturnBasis, compute_forward_returns, count_excluded
from .statistics import excess, permutation_test, summarize

__all__ = [
    "BelowMovingAverage",
    "MovingAverageKind",
    "ReturnBasis",
    "below_moving_average",
    "compute_forward_returns",
    "count_excluded",
    "excess",
    "permutation_test",
    "summarize",
]
