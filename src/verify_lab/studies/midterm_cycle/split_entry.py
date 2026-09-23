"""분할매수 체결 — 몫을 언제 사는가

**새로 정하는 것은 「몇 번째 몫을 언제 사는가」 하나다.** 몫마다의 수익률은
`execution/trade_fill.simulate_scheduled_trade` 를 무손절로 불러 얻는다 — 청산이 같은 날
(6월 마지막 거래일 종가)이라 몫 하나는 그 몫의 체결일에 진입한 달력형 체결과 같다.

**새로 재는 값은 배정액 기준의 보유 중 최악 하나다.** 몫이 여럿인 포트폴리오의 경로라 기존
산식이 없다. **일시매수 칸에서 기존 체결의 `보유 중 최악` 과 정확히 같아야 하며**, 그 동치를
테스트가 묶는다 — 두 산식이 한 점에서 묶여 있어야 조용히 갈라지지 않는다.

| 규칙 | 왜 |
| --- | --- |
| 첫 몫은 언제나 진입일(9월 마지막 거래일) 종가 | 일시매수와 같은 날이라 대조가 선다 |
| 추가 몫은 **진입 다음 거래일 ~ 12월 마지막 거래일** 안에서만 산다 | 최저점이 ETF 전부에서 4분기에 있었다. **결과를 보고 정한 창**이다 |
| B·C 는 **판정일 종가로 판정하고 «다음 거래일» 종가에 산다** | 같은 종가에 사면 그 종가가 찍혀야 알 수 있는 조건으로 그 종가에 사는 것이라 **미래 참조**다 (패키지 절대 원칙 1). 미국장 마감이 한국 시각 새벽이라 실제 집행도 다음 거래일이다 |
| 그래서 B·C 의 판정은 **12월 마지막 거래일 «전날»까지** | 체결이 창 끝을 넘지 않고, 12월 말 일괄 매수와 같은 날 겹칠 때 순서가 분명하다 |
| A(월말)·12월 말 일괄은 **그날 종가** | 날짜가 달력으로 미리 정해져 있어 판정이 필요 없다 |
| 판정·체결 가격은 **종가** | 지수는 종가뿐이다 — 장중 지정가를 가정하면 ETF 와 지수가 다른 규칙이 된다 |
| **체결일 당일 장중은 새 몫의 낙폭에 넣지 않는다** | 종가에 샀으므로 그날 장중은 들고 있지 않았다 |
| 성적의 분모는 **배정액** — 현금으로 남은 몫은 수익 0 | 일시매수와 같은 분모여야 견줘진다 |

**「위」 한 방향만 정의한다.** 사다리가 진입가 «아래»에 깔리고 지표 조건이 과매도라, 아래로
거는 매매에서는 뜻이 없다 — 이 매매법의 방향(`constants.BET_DOWN`)이 거짓인 것과 맞는다.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import assert_never

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_LOW
from verify_lab.execution.trade_fill import resolve_positions, simulate_scheduled_trade
from verify_lab.measure.constants import COL_MONTH
from verify_lab.studies.midterm_cycle.constants import (
    ADDITION_MONTHS,
    FALLBACK_BUY_AT_Q4_END,
    FALLBACK_NONE,
    FILL_FIRST,
    FILL_INDICATOR,
    FILL_LADDER,
    FILL_MONTH_END,
    FILL_Q4_END,
    FILL_UNFILLED,
    IndicatorCross,
    LumpSum,
    MonthEnds,
    PriceLadder,
    SplitMethod,
    SplitTrigger,
)
from verify_lab.studies.midterm_cycle.cycle_calendar import month_last_entries
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 사다리 단계 비교의 상대 허용오차. **「이하」의 경계에서 부동소수점 잔차만 흡수한다** —
# 10.28 × 0.95 가 9.765999… 로 계산돼 종가 9.766 이 단계에 «못 닿은» 것이 되는 일이
# 실제 가격 자릿수(소수 4자리)에서 생긴다. 가격 한 틱보다 훨씬 작아 다른 판정을 바꾸지 않는다
LEVEL_RELATIVE_TOLERANCE = 1e-12

# 판정일에서 체결일까지의 거래일 수. **0 으로 두면 판정한 종가에 그대로 사는 것이 되어
# 같은 봉 안의 미래 참조가 된다** — 그 종가가 찍혀야 조건이 참인지 알 수 있다
FILL_DELAY_DAYS = 1


@dataclass(frozen=True)
class EntryWindow:
    """진입 하나의 추가 매수 창

    Attributes:
        entry_position: 진입일(첫 몫)의 위치
        exit_position: 청산일의 위치
        month_end_positions: `ADDITION_MONTHS` 의 달 → 그 달 마지막 거래일의 위치 (진입 연도)
    """

    entry_position: int
    exit_position: int
    month_end_positions: Mapping[int, int]

    @property
    def window_end_position(self) -> int:
        """창의 끝 — 마지막 추가 달의 마지막 거래일.

        Returns:
            위치
        """
        return self.month_end_positions[ADDITION_MONTHS[-1]]


@dataclass(frozen=True)
class TrancheFill:
    """몫 하나의 체결

    Attributes:
        position: 체결일의 위치. **미체결이면 `None`** — 그 몫은 현금으로 남는다
        reason: 체결 사유 (`FILL_*`)
    """

    position: int | None
    reason: str


@dataclass(frozen=True)
class SplitResult:
    """진입 하나에 분할 방식 하나를 적용한 결과

    Attributes:
        fills: 몫마다의 체결. 첫 몫부터이고 길이가 방식의 몫 수와 같다
        return_rate: **배정액 기준** 수익률 (비율)
        worst_hold_rate: **배정액 기준** 보유 중 최악 (비율). 언제나 `return_rate` 이하다
        invested_rate: 투자된 비율 (비율, 1 = 전액)
        average_cost_rate: 첫 몫 가격 대비 평균 매수가 (비율, 음수 = 더 싸게 샀다).
            **투자된 몫만의 주식 수 가중 평균**이다
        rule_filled: 추가 몫 하나 이상이 **규칙 자체로** 체결됐는가. 미체결 처리로 산 몫은 세지 않는다
    """

    fills: tuple[TrancheFill, ...]
    return_rate: float
    worst_hold_rate: float
    invested_rate: float
    average_cost_rate: float
    rule_filled: bool


def entry_windows(
    trading_days: pd.DatetimeIndex, entry_positions: Sequence[int], exit_positions: Sequence[int]
) -> list[EntryWindow]:
    """진입마다 추가 매수 창을 만든다.

    **월말은 같은 패키지의 `cycle_calendar.month_last_entries` 가 정한다** — 진입일을 고른 것과
    같은 함수라 말일이 휴장인 달도 같은 방식(앞당김)으로 잡힌다.

    Args:
        trading_days: 거래일 목록
        entry_positions: 진입일 위치
        exit_positions: 청산일 위치. `entry_positions` 와 길이가 같아야 한다

    Returns:
        진입 순서대로의 창

    Raises:
        ValueError: 두 목록의 길이가 다른 경우
        RuntimeError: 진입 연도의 추가 달이 시세에 없거나, 창의 끝이 진입과 청산 사이에 있지
            않은 경우 (내부 불변조건 위반 — 청산일이 있으면 그 사이의 달은 반드시 있다)
    """
    if len(entry_positions) != len(exit_positions):
        raise ValueError(f"진입과 청산의 수가 다릅니다: 진입 {len(entry_positions)}개, 청산 {len(exit_positions)}개")

    month_ends = month_last_entries(trading_days)
    months = pd.DatetimeIndex(month_ends[COL_MONTH])
    positions = resolve_positions(trading_days, pd.DatetimeIndex(month_ends[COL_DATE]), label="월말")
    last_by_month = {
        (int(month.year), int(month.month)): int(position) for month, position in zip(months, positions, strict=True)
    }

    windows: list[EntryWindow] = []
    for entry_position, exit_position in zip(entry_positions, exit_positions, strict=True):
        entry_day = trading_days[entry_position]
        missing = [month for month in ADDITION_MONTHS if (entry_day.year, month) not in last_by_month]
        if missing:
            raise RuntimeError(f"내부 불변조건 위반: 진입 {entry_day.date()} 의 추가 매수 달이 시세에 없습니다: {missing}월")

        window = EntryWindow(
            entry_position=int(entry_position),
            exit_position=int(exit_position),
            month_end_positions={month: last_by_month[(entry_day.year, month)] for month in ADDITION_MONTHS},
        )
        if not window.entry_position < window.window_end_position < window.exit_position:
            raise RuntimeError(
                f"내부 불변조건 위반: 추가 매수 창의 끝이 진입과 청산 사이에 있지 않습니다: "
                f"진입 {window.entry_position}, 창의 끝 {window.window_end_position}, 청산 {window.exit_position}"
            )
        windows.append(window)

    return windows


def simulate_split_entry(
    frame: pd.DataFrame,
    window: EntryWindow,
    method: SplitMethod,
    *,
    fallback: str,
    price_column: str,
    indicators: pd.DataFrame,
) -> SplitResult:
    """진입 하나에 분할 방식 하나를 적용한다.

    Args:
        frame: 날짜 오름차순 가격 데이터
        window: 추가 매수 창
        method: 분할 방식
        fallback: 미체결 처리. `method.fallbacks` 안의 값이어야 한다
        price_column: 가격 컬럼 이름. **보유 중 최악의 기준도 이 값이 정한다** — 종가면 장중 저가로,
            계열(지수)이면 그 컬럼 하나로 잰다 (`simulate_scheduled_trade` 와 같은 규칙)
        indicators: `indicators.indicator_frame` 이 낸 지표 표. 가격 데이터와 행이 맞아야 한다

    Returns:
        체결과 배정액 기준 성적

    Raises:
        ValueError: 방식에 없는 미체결 처리이거나, 지표 표의 길이가 가격 데이터와 다르거나,
            보유 구간에 0 이하 가격이 있는 경우
        RuntimeError: 미체결이 생길 수 없는 방식에서 미체결이 생긴 경우 (내부 불변조건 위반)
    """
    if fallback not in method.fallbacks:
        raise ValueError(f"{method.label} 에 없는 미체결 처리입니다: {fallback} (가능한 값: {method.fallbacks})")
    if len(indicators) != len(frame):
        raise ValueError(f"지표 표의 길이가 가격 데이터와 다릅니다: 지표 {len(indicators)}행, 가격 {len(frame)}행")

    prices = frame[price_column].to_numpy(dtype=float)

    ruled = _rule_fills(method.trigger, window, prices, indicators)
    missing = method.tranches - 1 - len(ruled)
    if missing and fallback == FALLBACK_NONE:
        raise RuntimeError(f"내부 불변조건 위반: 미체결이 생길 수 없는 방식에서 {missing}몫이 비었습니다 ({method.label})")

    rest = [
        (
            TrancheFill(window.window_end_position, FILL_Q4_END)
            if fallback == FALLBACK_BUY_AT_Q4_END
            else TrancheFill(None, FILL_UNFILLED)
        )
        for _ in range(missing)
    ]
    fills = (TrancheFill(window.entry_position, FILL_FIRST), *ruled, *rest)

    weight = 1.0 / method.tranches
    held = [fill.position for fill in fills if fill.position is not None]

    # **몫 하나 = 그 체결일에 진입한 달력형 체결**이다. 산식을 새로 만들지 않는다
    returns = [
        simulate_scheduled_trade(
            frame, position, window.exit_position, bet_down=False, stop_level=None, price_column=price_column
        ).return_rate
        for position in held
    ]

    fill_prices = [float(prices[position]) for position in held]
    invested = weight * len(held)
    shares = sum(weight / price for price in fill_prices)

    return SplitResult(
        fills=fills,
        return_rate=weight * float(sum(returns)),
        worst_hold_rate=_allocated_worst(frame, window, held, weight=weight, price_column=price_column),
        invested_rate=invested,
        average_cost_rate=(invested / shares) / fill_prices[0] - 1.0,
        rule_filled=bool(ruled),
    )


def _rule_fills(
    trigger: SplitTrigger, window: EntryWindow, prices: np.ndarray, indicators: pd.DataFrame
) -> list[TrancheFill]:
    """규칙 자체로 체결된 추가 몫을 순서대로 낸다. 미체결 처리는 여기서 하지 않는다.

    Args:
        trigger: 추가 몫을 언제 사는가
        window: 추가 매수 창
        prices: 가격 배열
        indicators: 지표 표

    Returns:
        체결된 추가 몫. 길이는 몫 수 − 1 이하다
    """
    match trigger:
        case LumpSum():
            return []
        case MonthEnds():
            return [TrancheFill(window.month_end_positions[month], FILL_MONTH_END) for month in trigger.months]
        case PriceLadder():
            return _ladder_fills(trigger, window, prices)
        case IndicatorCross():
            return _indicator_fills(trigger, window, indicators)
        case _:
            assert_never(trigger)


def _ladder_fills(trigger: PriceLadder, window: EntryWindow, prices: np.ndarray) -> list[TrancheFill]:
    """단계마다 종가가 처음 그 가격 «이하»로 내려간 날(판정일)의 **다음 거래일 종가**에 산다.

    **얕은 단계에 닿지 않았으면 깊은 단계도 닿지 않았다** — 깊은 단계 이하인 종가는 얕은 단계
    이하이기도 하므로 거기서 멈춘다. 같은 날 두 단계를 지나면 둘 다 그 다음 거래일에 산다.

    Args:
        trigger: 사다리
        window: 추가 매수 창
        prices: 가격 배열

    Returns:
        체결된 단계의 몫
    """
    first_price = float(prices[window.entry_position])
    start = window.entry_position + 1
    # **판정은 창 끝 «전날»까지다** — 체결이 다음 거래일이라 그래야 창 안에서 끝난다
    judged = prices[start : window.window_end_position + 1 - FILL_DELAY_DAYS]

    fills: list[TrancheFill] = []
    for rate in trigger.level_rates:
        level = first_price * (1.0 - rate)
        reached = (judged <= level) | np.isclose(judged, level, rtol=LEVEL_RELATIVE_TOLERANCE, atol=0.0)
        hits = np.flatnonzero(reached)
        if hits.size == 0:
            break
        fills.append(TrancheFill(start + int(hits[0]) + FILL_DELAY_DAYS, FILL_LADDER))

    return fills


def _indicator_fills(trigger: IndicatorCross, window: EntryWindow, indicators: pd.DataFrame) -> list[TrancheFill]:
    """지표가 기준 아래로 «새로 들어간 날»(전날 거짓 → 그날 참)마다, 그 **다음 거래일 종가**에 산다.

    **비어 있는 지표는 거짓이다** — 창이 차기 전의 날에 조건을 세우지 않는다.
    **전날 값은 창 밖(진입일)이어도 본다** — 진입일에 이미 기준 아래였고 이어지면 새로 들어간 날이 아니다.

    Args:
        trigger: 지표 조건
        window: 추가 매수 창
        indicators: 지표 표

    Returns:
        체결된 몫. 몫 수 − 1 을 넘지 않는다
    """
    values = indicators[trigger.column].to_numpy(dtype=float)
    below = np.nan_to_num(values, nan=np.inf) < trigger.threshold

    start = window.entry_position + 1
    # **판정은 창 끝 «전날»까지다** — 체결이 다음 거래일이라 그래야 창 안에서 끝난다
    end = window.window_end_position + 1 - FILL_DELAY_DAYS
    crosses = below[start:end] & ~below[start - 1 : end - 1]
    positions = start + np.flatnonzero(crosses) + FILL_DELAY_DAYS

    return [TrancheFill(int(position), FILL_INDICATOR) for position in positions[: trigger.tranches - 1]]


def _allocated_worst(
    frame: pd.DataFrame, window: EntryWindow, held: Sequence[int], *, weight: float, price_column: str
) -> float:
    """배정액 기준 보유 중 최악 — 날마다 «그 전날까지 산 몫»의 평가손익 합의 최솟값.

    **구간은 진입 다음 거래일부터 청산일까지다** (기존 체결의 `보유 중 최악` 과 같다).
    몫은 **체결일 다음 날부터** 넣는다 — 종가에 샀으므로 그날 장중은 들고 있지 않았다.

    Args:
        frame: 가격 데이터
        window: 추가 매수 창
        held: 체결된 몫의 위치
        weight: 몫 하나의 비중 (비율)
        price_column: 가격 컬럼 이름. 종가면 장중 저가로 잰다

    Returns:
        보유 중 최악 (비율)

    Raises:
        ValueError: 보유 구간에 0 이하 가격이 있는 경우 — 0 하나가 −100% 짜리 최악을 조용히 만든다
    """
    column = COL_LOW if price_column == COL_CLOSE else price_column
    start = window.entry_position + 1
    path = frame[column].to_numpy(dtype=float)[start : window.exit_position + 1]
    if (path <= 0).any():
        raise ValueError(f"보유 구간에 0 이하 가격이 있습니다: 컬럼 {column}, 진입 {window.entry_position}")

    days = np.arange(start, window.exit_position + 1)
    prices = frame[price_column].to_numpy(dtype=float)
    value = np.zeros(len(days))
    for position in held:
        value += np.where(days > position, weight * (path / prices[position] - 1.0), 0.0)

    return float(value.min())


__all__ = ["EntryWindow", "SplitResult", "TrancheFill", "entry_windows", "simulate_split_entry"]
