"""표준 성과 지표 — 일별 총자산 곡선 하나에서 성적을 낸다

```
총수익률 = 마지막 / 처음 − 1
CAGR    = (마지막 / 처음) ^ (250 / 수익률 개수) − 1
MDD     = min(총자산 / 누적 최고점 − 1)                    ← 평가액 기준
Calmar  = CAGR / |MDD|
Sharpe  = 평균(초과수익) / 표준편차(초과수익) × √250
Sortino = 평균(초과수익) / √평균(min(초과수익, 0)²) × √250
```

**입력은 곡선과 무위험 수익률 계열 둘뿐이다.** 어떤 매매법이 그 곡선을 만들었는지 몰라야
이벤트 구동·상태 기계·필터 구동이 같은 표에 오른다. 매매법의 유일한 공통 산출물이 이 곡선이며
체결 내역은 매매법마다 컬럼이 달라 공통 계약이 될 수 없다.

**무위험 수익률을 0으로 두지 않는다.** 대기자금이 이자를 받는 매매법에서 `rf = 0` 으로 재면
"예금만 해도 얻었을 수익"이 전략 성과로 둔갑해 Sharpe 가 크게 부풀려진다. rf 를 제대로 적용하면
Sharpe 가 0 근처로 떨어질 수 있는데 **그것은 오류가 아니라 정확한 측정**이다.

**rf 는 달력일 간격만큼 붙는다.** 두 거래일 사이가 주말이면 3일이고, 거래일마다 하루치만 주면
rf 가 실제의 3분의 2로 깎여 **Sharpe 가 3배로 부풀려진다.** 연환산 계수(250 거래일)와
이자 일할(365 달력일)이 서로 다른 계수인 것도 같은 이유다.

**계산할 수 없으면 `None` 을 돌려준다.** 낙폭이 없을 때 Calmar 를 0 으로 답하면
"위험 대비 수익이 없다"로, 무한대로 답하면 "완벽하다"로 읽힌다. 둘 다 사실과 다르다.
"""

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 연환산 계수 (거래일). 이자 일할의 365 달력일과 **다른 계수**이며 실제 거래일 밀도
# (약 261일)와도 몇 % 어긋난다. 사양서가 정한 값이라 그 오차가 사실이다
TRADING_DAYS_PER_YEAR: Final = 250

# 무위험 수익률을 일할할 때 쓰는 분모 (달력일)
CALENDAR_DAYS_PER_YEAR: Final = 365

# 연 % 로 표기된 금리를 비율로 바꾸는 나눗수
PERCENT_TO_RATE: Final = 100.0


@dataclass(frozen=True)
class PerformanceMetrics:
    """곡선 하나에서 나온 표준 지표

    **위험조정 지표는 함께 읽어야 한다.** Sharpe 만으로는 "얼마나 이겼나"를 알 수 없어
    변동성·rf 평균·rf 를 그대로 굴렸을 때의 총수익률을 나란히 담는다.

    Attributes:
        trading_days: 곡선의 거래일 수
        first_date: 첫 거래일
        last_date: 마지막 거래일
        first_value: 시작 총자산
        last_value: 종료 총자산
        total_return_rate: 총수익률
        cagr: 연복리 수익률 (250 거래일 기준)
        max_drawdown: 최대 낙폭 (음수 비율). **평가액 기준**이다
        max_drawdown_date: 최대 낙폭이 난 거래일
        peak_date: 그 낙폭의 기준이 된 직전 신고점 거래일
        calmar: `CAGR / |MDD|`. 낙폭이 없으면 `None`
        volatility: 연환산 변동성 (표본 표준편차 × √250).
            **수익률이 하나뿐이면 표본 표준편차가 정의되지 않아** `None` 이다
        sharpe: 위험조정 초과수익. 변동이 없거나 수익률이 하나뿐이면 `None`
        sortino: 하방 위험 대비 초과수익. 하락이 없으면 `None`
        excess_return_mean: 거래일당 초과수익률의 평균. Sharpe 의 분자다
        risk_free_mean: 무위험 수익률의 기간 평균 (연%)
        risk_free_return_rate: 무위험 수익률을 **그대로 복리로 굴렸을 때**의 총수익률.
            초과분을 금액으로 읽을 수 있게 하며, 벤치마크가 서기 전까지 그 자리를 대신한다
    """

    trading_days: int
    first_date: pd.Timestamp
    last_date: pd.Timestamp
    first_value: float
    last_value: float
    total_return_rate: float
    cagr: float
    max_drawdown: float
    max_drawdown_date: pd.Timestamp
    peak_date: pd.Timestamp
    calmar: float | None
    volatility: float | None
    sharpe: float | None
    sortino: float | None
    excess_return_mean: float
    risk_free_mean: float
    risk_free_return_rate: float


def evaluate_curve(curve: pd.Series, *, risk_free: pd.Series) -> PerformanceMetrics:
    """일별 총자산 곡선에서 표준 지표를 낸다.

    **곡선에는 미실현 평가손익이 들어 있어야 한다.** 실현손익만 집계한 곡선은 익절형
    매매법에서 구조적으로 우상향하므로 MDD 가 거의 0 으로 나온다 — 그것은 위험이 없다는 뜻이
    아니라 위험을 안 재고 있다는 뜻이다. 이 함수는 그 사실을 확인할 수 없으므로
    **곡선을 만드는 쪽의 책임**이다.

    Args:
        curve: 거래일 오름차순 `DatetimeIndex` 를 가진 일별 총자산. 값은 전부 양수여야 한다
        risk_free: 같은 인덱스의 무위험 수익률 (연%). **세후 기준으로 넘긴다** —
            곡선이 세후라면 rf 도 세후여야 사과 대 사과가 된다

    Returns:
        표준 지표

    Raises:
        ValueError: 거래일이 둘 미만이거나, 총자산에 0 이하가 있거나,
            날짜가 오름차순이 아니거나, 무위험 수익률 계열이 곡선과 어긋나는 경우
    """
    if len(curve) < 2:
        raise ValueError(f"거래일이 둘 이상이어야 수익률을 만들 수 있습니다: {len(curve)}일")

    if not isinstance(curve.index, pd.DatetimeIndex):
        raise ValueError(f"곡선의 인덱스는 거래일이어야 합니다: {type(curve.index).__name__}")

    if not curve.index.is_monotonic_increasing:
        raise ValueError("곡선의 날짜가 오름차순이 아닙니다 - 정렬하지 않고 계산하면 최대 낙폭이 실제보다 얕게 나옵니다")

    if (curve <= 0).any():
        worst = pd.Timestamp(curve.index[int(curve.to_numpy().argmin())])
        raise ValueError(f"총자산에 0 이하 값이 있습니다: {float(curve.min()):,.4f}원, 날짜 {worst.date()}")

    if len(risk_free) != len(curve) or not risk_free.index.equals(curve.index):
        raise ValueError(f"무위험 수익률 계열이 곡선과 어긋납니다: 곡선 {len(curve):,}행, 무위험 {len(risk_free):,}행")

    values = curve.to_numpy(dtype=float)
    dates = curve.index

    # 1. 수익률과 그 구간의 무위험 수익률. **rf 는 달력일 간격만큼** 붙는다 —
    #    거래일마다 하루치만 주면 주말이 통째로 빠져 rf 가 3분의 2로 깎인다
    returns = values[1:] / values[:-1] - 1.0
    elapsed = (dates[1:] - dates[:-1]).days.to_numpy(dtype=float)
    rf_period = risk_free.to_numpy(dtype=float)[1:] / PERCENT_TO_RATE / CALENDAR_DAYS_PER_YEAR * elapsed
    excess = returns - rf_period

    # 2. 낙폭. 누적 최고점 대비이며 시작값 대비가 아니다 —
    #    시작값 기준이면 한 번 올랐다가 빠진 낙폭이 통째로 사라진다
    peaks = np.maximum.accumulate(values)
    drawdowns = values / peaks - 1.0
    worst_index = int(np.argmin(drawdowns))
    max_drawdown = float(drawdowns[worst_index])
    peak_index = int(np.argmax(values[: worst_index + 1]))

    total_return_rate = float(values[-1] / values[0] - 1.0)
    cagr = float((values[-1] / values[0]) ** (TRADING_DAYS_PER_YEAR / len(returns)) - 1.0)

    # 3. 표본 표준편차는 수익률이 둘 이상이라야 정의된다. 하나뿐이면 `NaN` 이 나오는데,
    #    그 값은 비교·정렬을 전부 조용히 통과하므로 여기서 `None` 으로 끊는다
    has_deviation = len(returns) >= 2
    deviation = float(returns.std(ddof=1)) if has_deviation else None
    excess_deviation = float(excess.std(ddof=1)) if has_deviation else None
    downside = float(math.sqrt(float(np.mean(np.minimum(excess, 0.0) ** 2))))
    annualiser = math.sqrt(TRADING_DAYS_PER_YEAR)

    metrics = PerformanceMetrics(
        trading_days=len(curve),
        first_date=dates[0],
        last_date=dates[-1],
        first_value=float(values[0]),
        last_value=float(values[-1]),
        total_return_rate=total_return_rate,
        cagr=cagr,
        max_drawdown=max_drawdown,
        max_drawdown_date=dates[worst_index],
        peak_date=dates[peak_index],
        # 낙폭이 없으면 나눌 수 없다. 0 이나 무한대는 「계산 불가」와 다른 뜻이 된다
        calmar=None if max_drawdown == 0.0 else cagr / abs(max_drawdown),
        volatility=None if deviation is None else deviation * annualiser,
        sharpe=(
            None
            if excess_deviation is None or excess_deviation == 0.0
            else float(excess.mean()) / excess_deviation * annualiser
        ),
        sortino=None if downside == 0.0 else float(excess.mean()) / downside * annualiser,
        excess_return_mean=float(excess.mean()),
        risk_free_mean=float(risk_free.mean()),
        risk_free_return_rate=float(np.prod(1.0 + rf_period) - 1.0),
    )

    logger.debug(
        f"표준 지표: {metrics.trading_days:,}거래일, 총수익률 {total_return_rate:.4%}, "
        f"CAGR {cagr:.4%}, MDD {max_drawdown:.4%}, Sharpe {metrics.sharpe}"
    )

    return metrics
