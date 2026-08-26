"""국면 분할 — 전체 기간 평균이 가리는 것을 드러낸다

사양서 §14 가 "전체 기간 평균은 구조적 차이를 가린다" 로 시작하는 이유는 그리드의 성적이
**국면마다 반대 방향으로 나오기** 때문이다. 횡보에서 회전이 극대화되고 대세 하락에서 전 슬롯이 물린다.

축이 셋이다.

| 축 | 무엇으로 자르나 | 무엇을 묻나 |
| --- | --- | --- |
| **축1 시장 국면** | 사양서 §14 의 8구간 (겹침 그대로) + 겹치지 않는 연속 분할 | 어느 국면에서 지는가 |
| **축2 한미 금리차 부호** | DTB3 − CD91 **원지표**의 부호가 이어지는 구간 | 261250 이 금리차 (+) 구간에서만 좋아 보이는가 |
| 축3 룩백 N | 파라미터 축이라 이 모듈이 아니라 축 순회가 답한다 | 결론이 N 에 의존하는가 |

**구간을 자를 때 직전 거래일을 앵커로 붙인다.** 앵커가 없으면 구간 첫날의 수익률이
전 구간의 마지막 날에서 오는데 그 값이 **어느 구간에도 안 들어간다** — 예외가 나지 않고
조용히 사라지며, 구간이 많을수록 잃는 수익률이 늘어난다.

**곡선 하나만 받는 계약을 그대로 쓴다.** 구간 지표는 `evaluate_curve` 를 다시 부를 뿐이고
새 산식을 만들지 않는다. 결정 B1 이 선언한 공통 계약이 여기서 세 번째로 재사용된다.

**금리차 부호는 실수령 금리가 아니라 원지표로 잰다** (결정 C110). 실수령 금리에는 상품
스프레드와 하한이 걸려 있어 그것으로 재면 **금리차가 아니라 상품 조건의 부호**가 나온다.

**부호 구간의 표본 구조를 함께 낸다.** 2005~ 실측에서 구간이 39개인데 그중 31개가
20거래일 미만이고, 250거래일을 넘는 구간은 6개뿐이다. **일수만 보면 독립 표본을 39개로 오독한다** —
루트 `CLAUDE.md` 「측정의 원칙」 5번이 요구하는 사건 단위 집계가 이 요약이다.
**따라서 부호별 우열에 통계적 주장을 하지 않는다.**
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import pandas as pd

from verify_lab.strategy.grid.constants import (
    RATE_GAP_EQUAL,
    RATE_GAP_NEGATIVE,
    RATE_GAP_POSITIVE,
    REGIME_AXIS_CONTIGUOUS,
    REGIME_AXIS_RATE_GAP,
    REGIME_AXIS_SPEC,
)
from verify_lab.strategy.performance import PerformanceMetrics, evaluate_curve
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 「짧은 구간」의 경계 (거래일). 이보다 짧으면 지표가 나오더라도 국면이라기보다 **전환기의 깜빡임**이다
SHORT_EPISODE_DAYS: Final = 20

# 「긴 구간」의 경계 (거래일). 부호 축의 결론을 이 구간들만으로 다시 보기 위한 부분집합 기준이며,
# 실측에서 2005~ 의 39개 구간 중 여기 드는 것이 여섯이다
LONG_EPISODE_DAYS: Final = 60


@dataclass(frozen=True)
class Regime:
    """국면 하나의 정의

    Attributes:
        axis: 어느 구간표에서 온 것인가 (사양서 국면 / 연속 분할 / 한미 금리차)
        name: 구간 이름
        nature: 구간의 성격. 축1 은 사양서 §14 의 라벨, 축2 는 금리차의 부호다
        start: 시작일 (포함)
        end: 종료일 (포함)
        trading_days: 구간에 들어 있는 거래일 수. **달력으로 정의한 구간은 `None`** 이다 —
            곡선을 받기 전에는 그 구간에 거래일이 며칠 있는지 알 수 없고, 0 으로 두면
            "거래일이 없었다"로 읽힌다
    """

    axis: str
    name: str
    nature: str
    start: pd.Timestamp
    end: pd.Timestamp
    trading_days: int | None = None


@dataclass(frozen=True)
class RegimeResult:
    """한 국면에서 곡선들이 낸 성적

    Attributes:
        regime: 국면 정의
        trading_days: 국면 안의 거래일 수 (**앵커는 세지 않는다**)
        returns: 그 국면에 배정된 수익률 개수. 앵커가 있으면 `trading_days` 와 같고
            곡선 첫 구간이면 하나 적다
        metrics: 곡선 키 → 표준 지표. **수익률이 둘 미만이면 `None`** 이다 (결정 C91) —
            0 으로 답하면 "제자리였다"로 읽힌다
    """

    regime: Regime
    trading_days: int
    returns: int
    metrics: Mapping[str, PerformanceMetrics | None]


@dataclass(frozen=True)
class RateGapSummary:
    """금리차 부호 하나의 표본 구조

    **일수만으로는 독립 표본 수를 알 수 없다.** 구간 수와 길이 분포를 함께 내는 이유다.

    Attributes:
        sign: 부호 표기
        episodes: 연속 구간 수
        trading_days: 그 부호였던 총 거래일 수
        longest_days: 가장 긴 구간의 거래일 수
        short_episodes: `SHORT_EPISODE_DAYS` 미만인 구간 수
        long_episodes: `LONG_EPISODE_DAYS` 이상인 구간 수
    """

    sign: str
    episodes: int
    trading_days: int
    longest_days: int
    short_episodes: int
    long_episodes: int


# 사양서 §14 축1 의 시장 국면. **원문 그대로이며 겹침과 빠짐을 고치지 않는다** (결정 C107) —
# 2009·2014·2016·2018 이 두 구간에 들어가고 2021·2023·2026 은 어디에도 없다.
# 고쳐서 재면 원문을 잰 것이 아니게 되므로, 빠진 해는 아래 연속 분할이 따로 덮는다
_SPEC_BOUNDS: Final = (
    ("2005~2007", "안정", "2005-01-01", "2007-12-31"),
    ("2008~2009", "급등", "2008-01-01", "2009-12-31"),
    ("2009~2014", "대세 하락", "2009-01-01", "2014-12-31"),
    ("2014~2016", "완만 상승", "2014-01-01", "2016-12-31"),
    ("2016~2018", "횡보", "2016-01-01", "2018-12-31"),
    ("2018~2020", "상승 후 급등락", "2018-01-01", "2020-12-31"),
    ("2022", "급등", "2022-01-01", "2022-12-31"),
    ("2024~2025", "급등", "2024-01-01", "2025-12-31"),
)

# 겹침을 없앤 연속 분할 (결정 C107·C108). **경계는 연 단위**이고 성격 라벨은 사양서 것을 그대로 쓴다.
# 고점(2009-03-02 1,570.3원)·저점(2007-10-31 900.7원)으로 자르면 **결과를 보고 경계를 정하는 것**이
# 되어 사양서 §15.1 의 「사후에 유리한 구간 선택 금지」에 걸린다.
# 겹친 해는 사양서가 더 강한 성격으로 지목한 쪽에 준다 — 2009·2014 는 대세 하락, 2016 은 완만 상승,
# 2018 은 횡보다. 빠져 있던 2021·2023·2026 은 인접 국면에 붙는다
_CONTIGUOUS_BOUNDS: Final = (
    ("2005~2007", "안정", "2005-01-01", "2007-12-31"),
    ("2008", "급등", "2008-01-01", "2008-12-31"),
    ("2009~2014", "대세 하락", "2009-01-01", "2014-12-31"),
    ("2015~2016", "완만 상승", "2015-01-01", "2016-12-31"),
    ("2017~2018", "횡보", "2017-01-01", "2018-12-31"),
    ("2019~2021", "상승 후 급등락", "2019-01-01", "2021-12-31"),
    ("2022~2023", "급등", "2022-01-01", "2023-12-31"),
    ("2024~2026", "급등", "2024-01-01", "2026-12-31"),
)


def _build(bounds: Sequence[tuple[str, str, str, str]], *, axis: str) -> tuple[Regime, ...]:
    """경계 표를 국면 목록으로 바꾼다.

    Args:
        bounds: (이름, 성격, 시작, 종료) 튜플 목록
        axis: 구간표 이름

    Returns:
        국면 목록
    """
    return tuple(
        Regime(axis=axis, name=name, nature=nature, start=pd.Timestamp(start), end=pd.Timestamp(end))
        for name, nature, start, end in bounds
    )


SPEC_REGIMES: Final = _build(_SPEC_BOUNDS, axis=REGIME_AXIS_SPEC)
CONTIGUOUS_REGIMES: Final = _build(_CONTIGUOUS_BOUNDS, axis=REGIME_AXIS_CONTIGUOUS)


def slice_curve(curve: pd.Series, *, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """국면 구간을 자르되 **직전 거래일을 앵커로 포함**한다.

    앵커가 없으면 구간 첫날의 수익률을 만들 기준값이 없어 그 수익률이 **어느 구간에도
    들어가지 않는다.** 예외가 나지 않으므로 구간을 늘릴수록 조용히 사라지는 몫이 커진다.
    곡선의 첫 구간은 앞에 거래일이 없으므로 앵커 없이 시작한다.

    Args:
        curve: 거래일 오름차순 `DatetimeIndex` 를 가진 곡선
        start: 구간 시작일 (포함)
        end: 구간 종료일 (포함)

    Returns:
        앵커를 포함해 자른 곡선. 구간에 거래일이 하나도 없으면 빈 곡선이다

    Raises:
        ValueError: 시작이 종료보다 늦은 경우
    """
    if start > end:
        raise ValueError(f"구간의 시작이 종료보다 늦습니다: {start.date()} ~ {end.date()}")

    inside = curve.loc[(curve.index >= start) & (curve.index <= end)]
    if inside.empty:
        return inside

    before = curve.loc[curve.index < start]

    return curve.loc[before.index[-1] : end] if len(before) else inside


def rate_gap_regimes(tbill: pd.Series, cd91: pd.Series) -> tuple[Regime, ...]:
    """한미 금리차 부호가 이어지는 구간을 만든다 (사양서 §14 축2).

    **원지표의 차로 잰다** (결정 C110). 실수령 금리는 상품 스프레드와 하한이 걸려 있어
    그것으로 재면 금리차가 아니라 상품 조건의 부호가 나온다.

    **동률을 (+)나 (−)에 합치지 않는다.** 사양서 §14 는 둘만 적었지만
    「달러금리 > 원화금리」에도 「달러금리 < 원화금리」에도 해당하지 않는 날이 실재한다.

    구간을 합치거나 짧은 것을 지우지 않는다 — 잡음으로 보이는 하루짜리 전환도 표본이며,
    지우면 무엇이 빠졌는지 다음 사람이 알 수 없다.

    Args:
        tbill: 거래일별 미국 3개월 T-bill 원지표 (연%)
        cd91: 같은 인덱스의 CD 91일물 원지표 (연%)

    Returns:
        부호가 같은 날이 이어지는 구간 목록 (시간순)

    Raises:
        ValueError: 두 계열의 인덱스가 어긋나거나 비어 있는 경우
    """
    if len(tbill) != len(cd91) or not tbill.index.equals(cd91.index):
        raise ValueError(f"두 금리 계열의 인덱스가 어긋납니다: T-bill {len(tbill):,}행, CD91 {len(cd91):,}행")

    if tbill.empty:
        raise ValueError("금리 계열이 비어 있습니다")

    gap = tbill - cd91
    signs = gap.map(
        lambda value: RATE_GAP_POSITIVE if value > 0 else (RATE_GAP_NEGATIVE if value < 0 else RATE_GAP_EQUAL)
    )
    episodes = (signs != signs.shift()).cumsum()

    regimes = tuple(
        Regime(
            axis=REGIME_AXIS_RATE_GAP,
            name=f"{group.index[0].date()} ~ {group.index[-1].date()}",
            nature=str(group.iloc[0]),
            start=pd.Timestamp(group.index[0]),
            end=pd.Timestamp(group.index[-1]),
            trading_days=len(group),
        )
        for _, group in signs.groupby(episodes)
    )

    logger.debug(f"금리차 부호 구간: {len(regimes)}개, 거래일 {len(signs):,}일")

    return regimes


def rate_gap_summaries(regimes: Sequence[Regime]) -> tuple[RateGapSummary, ...]:
    """부호별로 구간 수와 길이 분포를 낸다.

    **총 일수만 내면 독립 표본 수를 구간 수로 오독한다.** 실측에서 (−) 3,604일이
    한 덩어리가 아니라 여러 구간이고, 그중 대부분이 며칠짜리 전환기다.

    Args:
        regimes: `rate_gap_regimes` 가 낸 구간 목록

    Returns:
        부호별 요약 (사양서 §14 의 (+)·(−) 순서, 동률이 있으면 마지막)

    Raises:
        ValueError: 거래일 수가 없는 구간이 섞인 경우. 달력으로 정의한 국면은 이 요약의 대상이 아니다
    """
    lengths: dict[str, list[int]] = {}
    for regime in regimes:
        if regime.trading_days is None:
            raise ValueError(f"거래일 수가 없는 구간입니다: {regime.name} - 부호 구간에만 쓸 수 있습니다")
        lengths.setdefault(regime.nature, []).append(regime.trading_days)

    order = (RATE_GAP_POSITIVE, RATE_GAP_NEGATIVE, RATE_GAP_EQUAL)

    return tuple(
        RateGapSummary(
            sign=sign,
            episodes=len(lengths[sign]),
            trading_days=sum(lengths[sign]),
            longest_days=max(lengths[sign]),
            short_episodes=sum(1 for days in lengths[sign] if days < SHORT_EPISODE_DAYS),
            long_episodes=sum(1 for days in lengths[sign] if days >= LONG_EPISODE_DAYS),
        )
        for sign in order
        if sign in lengths
    )


def evaluate_regimes(
    curves: Mapping[str, pd.Series],
    *,
    risk_free: pd.Series,
    regimes: Sequence[Regime],
) -> tuple[RegimeResult, ...]:
    """국면마다 곡선들의 표준 지표를 낸다.

    **모든 곡선을 같은 구간으로 자른다.** 전략과 벤치마크가 다른 구간을 겪으면
    "어느 국면에서 지는가" 라는 질문 자체가 성립하지 않는다.

    **구간이 곡선 범위 밖이어도 결과에서 빼지 않는다.** ETF 두 경로는 2017~ 이라
    사양서 8구간 중 앞 다섯이 비는데, 빼 버리면 「기간 밖」과 「재고 0」이 구분되지 않는다.

    Args:
        curves: 곡선 키 → 일별 총자산 곡선. 전부 같은 거래일 인덱스여야 한다
        risk_free: 같은 인덱스의 무위험 수익률 (연%, 세후)
        regimes: 국면 목록

    Returns:
        국면마다 한 개씩, 넘긴 순서 그대로

    Raises:
        ValueError: 곡선이 하나도 없거나, 곡선끼리 또는 무위험 수익률과 인덱스가 어긋나는 경우
    """
    if not curves:
        raise ValueError("곡선이 하나도 없습니다")

    reference = next(iter(curves.values()))
    for key, curve in curves.items():
        if len(curve) != len(reference) or not curve.index.equals(reference.index):
            raise ValueError(f"곡선 '{key}' 의 거래일이 다른 곡선과 어긋납니다: {len(curve):,}행 대 {len(reference):,}행")

    if len(risk_free) != len(reference) or not risk_free.index.equals(reference.index):
        raise ValueError(f"무위험 수익률 계열이 곡선과 어긋납니다: 곡선 {len(reference):,}행, 무위험 {len(risk_free):,}행")

    results: list[RegimeResult] = []
    for regime in regimes:
        inside = reference.loc[(reference.index >= regime.start) & (reference.index <= regime.end)]
        sliced_index = slice_curve(reference, start=regime.start, end=regime.end).index

        metrics: dict[str, PerformanceMetrics | None] = {}
        for key, curve in curves.items():
            window = curve.loc[sliced_index]
            # 수익률이 둘 미만이면 표본 표준편차가 정의되지 않고 지표가 통째로 뜻을 잃는다
            metrics[key] = evaluate_curve(window, risk_free=risk_free.loc[sliced_index]) if len(window) >= 2 else None

        results.append(
            RegimeResult(
                regime=regime,
                trading_days=len(inside),
                returns=max(len(sliced_index) - 1, 0),
                metrics=metrics,
            )
        )

    logger.debug(f"국면별 지표: 구간 {len(results)}개, 곡선 {len(curves)}종")

    return tuple(results)
