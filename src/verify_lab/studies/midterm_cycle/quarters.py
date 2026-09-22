"""보유 구간의 분기 분해와 보유 중 최악의 분포

**진입이 9월 마지막 거래일이고 청산이 다음해 6월 마지막 거래일이라 보유가 4분기·1분기·2분기에
정확히 맞는다.** 그래서 「어느 분기가 수익을 만들고 어느 분기에 밀리나」를 물을 수 있다.

**계산식을 새로 만들지 않는다.** 분기 하나를 `execution/trade_fill.simulate_scheduled_trade` 에
**무손절로** 넘기면 그 분기의 수익률과 **분기 시작가 대비** 보유 중 최악이 그대로 나오고,
**진입가 대비** 최악은 거기서 분모만 바꾼 항등식이다 (`설계.md` 결정 ⑯) —

```
부호        = 아래로 걸면 −1, 위로 걸면 +1
최악의 가격  = 분기 시작가 × (1 + 부호 × 분기 시작가 대비 최악)
진입가 대비 최악 = (최악의 가격 ÷ 진입가 − 1) × 부호
```

[중요] **부호를 빼면 「아래」 칸에서 틀린다.** 체결식이 내는 수익률에는 거는 방향이 이미
반영돼 있어(`(가격 ÷ 진입가 − 1) × 부호`), **가격을 되돌릴 때도 같은 부호를 태워야 한다.**
「위」 한 방향만 볼 때는 부호가 1 이라 눈에 띄지 않는다.

두 번째 판정식을 만들면 같은 값이 두 곳에서 갈라진다 (패키지 절대 원칙 5).

[중요] **이 분해의 계약은 검산 둘이고, 둘 다 «조용히» 깨진다.**

| 검산 | 무엇이 어긋나면 깨지나 |
| --- | --- |
| `(1+4분기)(1+1분기)(1+2분기) = 1 + 전체 수익률` | 분기 경계가 어긋나거나 구간이 겹친다 |
| `min(분기별 진입가 대비 최악) = 전체 보유 중 최악` | 세 구간의 합집합이 보유 구간 전체가 아니다 |

경계가 하루 어긋나도 값은 그럴듯하게 나오므로 **테스트가 유일한 방어선이다.**

**두 검산은 「위」 기준으로 적었다.** 첫 검산의 곱셈 형태는 부호가 +1 일 때의 것이고,
`BET_DOWN` 이 거짓이라 **「아래」 경로는 실행되지 않는다** — 방향을 뒤집기로 하면
그때 이 검산부터 다시 세운다.

**분해는 무손절 경로에서만 한다** (`설계.md` 결정 ⑮). 손절이 걸리면 보유가 중간에 끊겨
남은 분기의 표본이 사라지고, 끊긴 분기는 「그 분기 성적」이 아니라 「손절까지의 성적」이 된다.

**분기를 달력으로 묶는다 — 달을 세어 자르지 않는다.** 규칙이 바뀌면 묶음 수가 달라지는데,
`QUARTER_LABELS` 와 대조하지 않으면 **한 칸짜리 표가 조용히 나온다.**
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.execution.trade_fill import simulate_scheduled_trade
from verify_lab.studies.midterm_cycle.constants import DRAWDOWN_BUCKETS, QUARTER_LABELS
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class QuarterTrade:
    """보유 구간을 이루는 분기 하나

    Attributes:
        label: 분기 이름 (`4분기`·`1분기`·`2분기`)
        start_position: 시작 «기준가»의 거래일 위치. 첫 분기는 진입일, 나머지는 직전 분기의 끝이다
        end_position: 그 분기 마지막 거래일의 위치. 마지막 분기는 청산일이다
        start_price: 시작 기준가
        end_price: 종료가
        hold_days: 그 분기의 보유 거래일 수
        return_rate: 그 분기의 수익률 (비율). 거는 방향이 반영돼 있다
        worst_vs_start: **분기 시작가** 대비 보유 중 최악 (비율)
        worst_vs_entry: **진입가** 대비 보유 중 최악 (비율)
    """

    label: str
    start_position: int
    end_position: int
    start_price: float
    end_price: float
    hold_days: int
    return_rate: float
    worst_vs_start: float
    worst_vs_entry: float


@dataclass(frozen=True)
class DrawdownProfile:
    """보유 중 최악의 분포

    **성적표의 `보유 중 최악(%)` 은 구간 «최솟값» 하나**라 「보통 얼마나 밀리나」에 답하지
    못한다. 최솟값(`deepest`)은 그대로 담아 두 표가 이어지게 하고, 나머지가 분포를 말한다.

    Attributes:
        sample_count: 잰 체결 수
        mean: 평균
        median: 중앙값
        quantile_25: 25% 분위 — 넷 중 하나는 이보다 깊다
        quantile_75: 75% 분위 — 넷 중 하나는 이보다 얕다
        shallowest: 가장 얕게 밀린 값 (최댓값)
        deepest: 가장 깊게 밀린 값 (최솟값). **성적표의 `보유 중 최악(%)` 과 같은 값이다**
        within: `DRAWDOWN_BUCKETS` 순서대로, 그 안에 든 체결 수
    """

    sample_count: int
    mean: float
    median: float
    quantile_25: float
    quantile_75: float
    shallowest: float
    deepest: float
    within: tuple[int, ...]


def quarter_trades(
    frame: pd.DataFrame,
    *,
    entry_position: int,
    exit_position: int,
    bet_down: bool,
    price_column: str,
) -> tuple[QuarterTrade, ...]:
    """보유 구간을 달력 분기로 갈라 분기마다 체결을 잰다.

    Args:
        frame: 날짜 오름차순 가격 데이터. ETF 는 시세 스키마, 지수는 단일 값 계열이다
        entry_position: 진입일의 위치 인덱스
        exit_position: 청산일의 위치 인덱스. 진입 위치보다 뒤여야 한다
        bet_down: 아래로 거는 칸인지 여부
        price_column: 가격 컬럼 이름. **보유 중 최악의 기준도 이 값이 정한다** —
            종가면 장중 고가·저가로, 계열이면 그 컬럼 하나로 잰다

    Returns:
        시간 순서대로의 분기 체결. 길이는 `QUARTER_LABELS` 와 같다

    Raises:
        ValueError: 위치가 범위를 벗어나거나 청산이 진입보다 뒤가 아닌 경우
        RuntimeError: 분해된 분기가 `QUARTER_LABELS` 와 다른 경우 (내부 불변조건 위반)
    """
    if not 0 <= entry_position < exit_position < len(frame):
        raise ValueError(
            f"진입 위치는 0 이상이고 청산 위치는 그보다 뒤이면서 시세 범위 안이어야 합니다: "
            f"진입 {entry_position}, 청산 {exit_position} (시세 {len(frame)}행)"
        )

    entry_price = float(frame.iloc[entry_position][price_column])
    sign = -1.0 if bet_down else 1.0

    trades = [
        _quarter_trade(
            frame,
            label=label,
            start_position=start_position,
            end_position=end_position,
            bet_down=bet_down,
            price_column=price_column,
            entry_price=entry_price,
            sign=sign,
        )
        for label, start_position, end_position in _segments(frame, entry_position, exit_position)
    ]

    logger.debug(f"분기 분해: 진입 {entry_position}, 청산 {exit_position}, 분기 {len(trades)}개")

    return tuple(trades)


def drawdown_profile(rates: Sequence[float]) -> DrawdownProfile:
    """보유 중 최악의 분포를 낸다.

    **0 으로 채우지 않는다** — 잰 체결이 없는 것은 「안 밀렸다」가 아니라 「잰 적이 없다」이고,
    그 둘을 한 값으로 적으면 없는 안전을 보고하게 된다.

    Args:
        rates: 체결마다의 보유 중 최악 (비율). 거는 방향이 이미 반영된 값이다

    Returns:
        분포. `within` 은 `DRAWDOWN_BUCKETS` 순서다

    Raises:
        ValueError: 잰 체결이 하나도 없는 경우
    """
    if len(rates) == 0:
        raise ValueError("낙폭을 잴 체결이 비어 있습니다")

    series = pd.Series(list(rates), dtype="float64")

    return DrawdownProfile(
        sample_count=len(series),
        mean=float(series.mean()),
        median=float(series.median()),
        quantile_25=float(series.quantile(0.25)),
        quantile_75=float(series.quantile(0.75)),
        shallowest=float(series.max()),
        deepest=float(series.min()),
        # **경계값은 «이내»에 넣지 않는다** — 그만큼 밀린 것이 사실이다
        within=tuple(int((series > -threshold).sum()) for threshold in DRAWDOWN_BUCKETS),
    )


def _segments(frame: pd.DataFrame, entry_position: int, exit_position: int) -> list[tuple[str, int, int]]:
    """보유 구간을 달력 분기로 묶어 (이름, 시작 위치, 끝 위치)를 낸다.

    **구간은 진입 «다음» 거래일부터 청산일까지다.** 진입가가 진입일 종가이므로 그날 장중은
    이미 지나간 시간이고, 그래서 첫 분기의 «시작 기준가»만 진입일에서 온다.

    Args:
        frame: 날짜 오름차순 가격 데이터
        entry_position: 진입일의 위치 인덱스
        exit_position: 청산일의 위치 인덱스

    Returns:
        시간 순서대로의 (분기 이름, 시작 위치, 끝 위치)

    Raises:
        RuntimeError: 분해된 분기가 `QUARTER_LABELS` 와 다른 경우 (내부 불변조건 위반)
    """
    dates = pd.DatetimeIndex(frame[COL_DATE])
    window = dates[entry_position + 1 : exit_position + 1]
    quarter_values = np.asarray(window.quarter)

    # 분기 값이 바뀌는 지점이 묶음의 경계다. 마지막 묶음은 청산일에서 끝난다
    group_ends = np.append(np.flatnonzero(np.diff(quarter_values) != 0), len(quarter_values) - 1)

    segments: list[tuple[str, int, int]] = []
    start_position = entry_position
    for group_end in group_ends:
        end_position = entry_position + 1 + int(group_end)
        segments.append((f"{int(quarter_values[group_end])}분기", start_position, end_position))
        start_position = end_position

    labels = tuple(label for label, _, _ in segments)
    if labels != QUARTER_LABELS:
        raise RuntimeError(
            f"내부 불변조건 위반: 보유 구간이 {QUARTER_LABELS} 로 갈리지 않습니다: {labels} "
            f"(진입 {dates[entry_position].date()}, 청산 {dates[exit_position].date()})"
        )

    return segments


def _quarter_trade(
    frame: pd.DataFrame,
    *,
    label: str,
    start_position: int,
    end_position: int,
    bet_down: bool,
    price_column: str,
    entry_price: float,
    sign: float,
) -> QuarterTrade:
    """분기 하나를 체결로 재고 두 분모의 낙폭을 붙인다.

    Args:
        frame: 날짜 오름차순 가격 데이터
        label: 분기 이름
        start_position: 시작 기준가의 위치
        end_position: 그 분기 마지막 거래일의 위치
        bet_down: 아래로 거는 칸인지 여부
        price_column: 가격 컬럼 이름
        entry_price: 이 매매의 진입가. **분기 시작가가 아니다**
        sign: 아래로 걸면 -1, 아니면 1

    Returns:
        분기 체결
    """
    result = simulate_scheduled_trade(
        frame,
        start_position,
        end_position,
        bet_down=bet_down,
        stop_level=None,
        price_column=price_column,
    )

    start_price = float(frame.iloc[start_position][price_column])
    end_price = float(frame.iloc[end_position][price_column])

    # **분모만 바꾼 항등식이다** — 체결식이 낸 값에서 최악의 «가격»을 되돌린 뒤 진입가로 나눈다.
    # 두 번째 판정식을 만들면 같은 값이 두 곳에서 갈라진다 (절대 원칙 5)
    worst_price = start_price * (1.0 + sign * result.worst_hold_rate)
    worst_vs_entry = (worst_price / entry_price - 1.0) * sign

    return QuarterTrade(
        label=label,
        start_position=start_position,
        end_position=end_position,
        start_price=start_price,
        end_price=end_price,
        hold_days=result.hold_days,
        return_rate=result.return_rate,
        worst_vs_start=result.worst_hold_rate,
        worst_vs_entry=worst_vs_entry,
    )


__all__ = ["DrawdownProfile", "QuarterTrade", "drawdown_profile", "quarter_trades"]
