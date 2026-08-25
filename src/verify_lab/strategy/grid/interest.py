"""실수령 금리 — 원지표가 아니라 계좌에 실제로 꽂히는 금리

```
RP금리   = max( T-bill − s(T-bill),  하한 )
파킹금리 = max( CD91 − 0.30%p,       하한 )
```

**원지표를 그대로 쓰지 않는다.** T-bill 은 무위험 단기금리라 증권사 RP 수익의 **상한**이고,
CD91 도 개인이 받는 파킹 금리보다 높다. 사양서 §11.2 가 상품 스프레드와 하한을 규정한 이유다.

**하한이 장식이 아니다.** 2005 이후 5,340 거래일 중 **2,605일(48.8%)** 에서 RP 금리를
T-bill 이 아니라 하한이 정한다. 국내 증권사는 해외주식 결제·파생 헤지로 달러가 상시 부족하고
원달러 스왑베이시스가 만성 마이너스라, 미국 금리가 0이어도 프리미엄을 얹을 여력이 있기 때문이다.
**하한이 없으면 2009~2015 제로금리 구간의 손실을 실제보다 과대평가한다** — 하필 그 구간이
원달러가 1,570 → 1,008 로 빠진 그리드 최악 국면이다.

**금리 계열은 마스터 달력에 맞춰 전일값을 이월한다** (결정 C14). 미국 휴일이라 DTB3 가 비는 날이
전체의 3.58% 이고, CD91 도 한국 공휴일에 빈다. **이월은 측정 계층의 판단이지 수집의 일이 아니다** —
수집이 미리 메우면 "원래 값이 없던 날"과 "메운 날"을 나중에 구분할 수 없다.
그래서 이월한 건수를 함께 돌려준다.

**이 모듈은 이자를 얹지 않는다.** 금리를 만들 뿐이고, 어느 잔고에 며칠치를 붙일지는
시뮬레이션 루프의 책임이다 — 이자일수 규칙이 경로마다 다르기 때문이다.

**무위험 수익률도 여기서 낸다.** 사양서 §13.1 이 Sharpe·Sortino 의 `rf = CD91` 로 규정했고,
그 원지표가 원화 파킹 금리와 **같은 계열에서 갈리기** 때문이다 — 정렬과 이월을 두 번 구현하면
두 곳이 조용히 달라진다. 다만 **rf 에는 상품 스프레드도 하한도 걸지 않는다.** 하한을 걸면
제로금리 구간에서 **무위험보다 높은 무위험 금리**가 되어 그 시기의 Sharpe 가 구조적으로 낮아진다.
대신 **세율은 적용한다** — 전략 곡선이 이미 세후(이자에 원천징수 반영)라 같은 기준이어야
사과 대 사과가 된다.
"""

from dataclasses import dataclass

import pandas as pd

from verify_lab.common_constants import COL_DATE, COL_VALUE
from verify_lab.strategy.grid.constants import (
    INTEREST_TAX_RATE,
    PARKING_RATE_DISCOUNT,
    RP_RATE_SPREAD_STEPS,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class InterestConfig:
    """이자 파라미터

    값의 출처는 사양서 §11.2 이며 검사 범위는 §12 다.
    **세율은 여기 없다** — 법정 세율이라 바꿔 가며 대조할 값이 아니라 상수다.

    Attributes:
        rp_floor_rate: 달러 RP 금리의 하한 (연%)
        parking_floor_rate: 원화 파킹 금리의 하한 (연%)
    """

    rp_floor_rate: float
    parking_floor_rate: float

    def __post_init__(self) -> None:
        """하한을 즉시 검사한다.

        Raises:
            ValueError: 하한이 음수인 경우
        """
        for name, rate in (("RP 하한", self.rp_floor_rate), ("파킹 하한", self.parking_floor_rate)):
            if rate < 0:
                raise ValueError(f"{name}은 0 이상이어야 합니다: {rate}")


@dataclass(frozen=True)
class RateSeries:
    """마스터 달력에 맞춘 금리 계열

    Attributes:
        rp: 거래일 → 달러 RP 금리 (연%)
        parking: 거래일 → 원화 파킹 금리 (연%)
        risk_free: 거래일 → **무위험 수익률** (연%, 세후). CD91 원지표에 세율만 적용한 값이며
            상품 스프레드도 하한도 걸지 않는다. 사양서 §13.1 의 Sharpe·Sortino 가 쓴다
        rp_filled: RP 원지표가 없어 전일값을 이월한 거래일 수
        parking_filled: 파킹 원지표가 없어 전일값을 이월한 거래일 수.
            **rf 도 같은 계열이라 이 건수가 그대로 적용된다**
    """

    rp: pd.Series
    parking: pd.Series
    risk_free: pd.Series
    rp_filled: int
    parking_filled: int


def rp_rate(tbill: float, *, floor: float) -> float:
    """미국 3개월 T-bill 에서 달러 RP 실수령 금리를 만든다.

    빼는 폭은 T-bill 수준에 따라 4구간 계단이다 (사양서 §11.2). 금리가 높을수록 증권사가
    가져가는 몫이 커지며, **음수 T-bill 도 가장 낮은 칸으로 떨어진다** — DTB3 에 실재한다.

    Args:
        tbill: 미국 3개월 T-bill 금리 (연%). 음수를 허용한다
        floor: 실수령 금리의 하한 (연%)

    Returns:
        달러 RP 실수령 금리 (연%)

    Raises:
        ValueError: 하한이 음수인 경우
    """
    if floor < 0:
        raise ValueError(f"RP 하한은 0 이상이어야 합니다: {floor}")

    spread = next(step for threshold, step in RP_RATE_SPREAD_STEPS if tbill >= threshold)

    return max(tbill - spread, floor)


def parking_rate(cd91: float, *, floor: float) -> float:
    """CD 91일물에서 원화 파킹 실수령 금리를 만든다.

    Args:
        cd91: CD 91일물 금리 (연%)
        floor: 실수령 금리의 하한 (연%)

    Returns:
        원화 파킹 실수령 금리 (연%)

    Raises:
        ValueError: 하한이 음수인 경우
    """
    if floor < 0:
        raise ValueError(f"파킹 하한은 0 이상이어야 합니다: {floor}")

    return max(cd91 - PARKING_RATE_DISCOUNT, floor)


def build_rate_series(
    calendar: pd.DatetimeIndex,
    *,
    tbill: pd.DataFrame,
    cd91: pd.DataFrame,
    config: InterestConfig,
) -> RateSeries:
    """마스터 달력의 모든 거래일에 실수령 금리와 무위험 수익률을 붙인다.

    **원지표가 없는 날은 전일값을 이월한다.** 달력 첫날 이전에 원지표가 하나도 없으면
    이월할 값이 없으므로 거부한다 — 조용히 하한으로 채우면 그 구간이 통째로 하한 금리가 된다.

    Args:
        calendar: 마스터 달력 (원달러 고시일, 오름차순)
        tbill: 미국 3개월 T-bill 시계열 (`load_series_csv` 가 돌려준 형태)
        cd91: CD 91일물 시계열 (같은 형태)
        config: 이자 파라미터

    Returns:
        거래일별 금리와 이월 건수

    Raises:
        ValueError: 달력이 비었거나, 달력 첫날 이전에 원지표가 없는 경우
    """
    if len(calendar) == 0:
        raise ValueError("마스터 달력이 비어 있습니다")

    rp_raw, rp_filled = _align(tbill, calendar=calendar, label="T-bill")
    parking_raw, parking_filled = _align(cd91, calendar=calendar, label="CD91")

    logger.debug(f"금리 계열 정렬: {len(calendar):,}거래일, " f"T-bill 이월 {rp_filled:,}일, CD91 이월 {parking_filled:,}일")

    return RateSeries(
        rp=rp_raw.map(lambda value: rp_rate(value, floor=config.rp_floor_rate)),
        parking=parking_raw.map(lambda value: parking_rate(value, floor=config.parking_floor_rate)),
        # 원지표에 세율만 적용한다. 하한을 걸면 무위험보다 높은 무위험 금리가 된다
        risk_free=parking_raw * (1.0 - INTEREST_TAX_RATE),
        rp_filled=rp_filled,
        parking_filled=parking_filled,
    )


def _align(series: pd.DataFrame, *, calendar: pd.DatetimeIndex, label: str) -> tuple[pd.Series, int]:
    """단일 값 시계열을 마스터 달력에 맞추고 전일값을 이월한다.

    Args:
        series: 일별 단일 값 시계열
        calendar: 마스터 달력
        label: 예외 메시지에 쓸 계열 이름

    Returns:
        달력에 맞춘 값과 이월한 거래일 수

    Raises:
        ValueError: 달력 첫날 이전에 값이 하나도 없는 경우
    """
    indexed = series.set_index(COL_DATE)[COL_VALUE]
    first = calendar[0]
    if not (indexed.index <= first).any():
        raise ValueError(
            f"{label} 계열이 마스터 달력 첫날({first.date()}) 이전에 값을 갖고 있지 않습니다 - " f"계열 시작 {indexed.index[0].date()}"
        )

    # 1. 달력과 원지표 날짜를 합친 축에서 이월한 뒤 달력만 남긴다.
    #    달력에 없는 날의 값도 이월에 쓰여야 한다 — 미국 시장만 열린 날이 실제로 있다
    merged = indexed.reindex(indexed.index.union(calendar)).ffill()
    aligned = merged.reindex(calendar)

    filled = int((~calendar.isin(indexed.index)).sum())

    return aligned, filled
