"""벤치마크 3종 — 「그래서 매매할 가치가 있나」에 답하는 대조 기준선

사양서 §13.3 이 **필수 병기**로 규정한 셋이며 목적이 각각 다르다.

| 벤치마크 | 무엇을 답하나 |
| --- | --- |
| **B&H (전액 보유)** | 첫날 사서 들고만 있었어도 됐나 — **매매의 가치** |
| **분할매수 후 보유** | **§13.3 의 판정.** 못 이기면 익절 로직을 제거하는 것이 맞다 |
| **원화 파킹 100%** | 환율 위험을 진 대가가 있었나 — **리스크 대비 정당성** |

**질문은 「이기는가」가 아니다.** §13.3 이 "얼마나 자주 지고, 질 때 얼마나 지는가" 로 못 박았다.
그리드는 추세장에서 B&H 에 구조적으로 지며 이길 수 있는 유일한 환경은 횡보다.

**세 곡선이 지표 계층을 그대로 통과한다.** 결정 B1 이 「매매법의 공통 산출물은 일별 총자산 곡선이고
표준 지표는 곡선 하나만 받는 함수에서 계산한다」로 선언한 것이 여기서 처음 재사용된다 —
벤치마크마다 지표를 새로 구현하지 않는다.

**「분할매수 후 보유」는 엔진을 매도만 끄고 다시 돌린다** (결정 C11). 별도 루프로 다시 쓰면
매수 규칙이 조용히 갈라져 **두 곡선의 차이를 익절 로직의 기여로 읽을 수 없게** 된다.

**B&H 의 첫날 매수에는 슬리피지가 붙지 않는다.** 슬리피지는 사양서 §6.6 의 「15:20 돌파 판정과
종가의 차이」를 흡수한 값인데 B&H 에는 **돌파 판정이 없다** — 결정 C60 이 같은 이유로 월말 RP 이자
환전에서 슬리피지를 뺐고 그 논리를 그대로 잇는다. 방향은 벤치마크에 유리해 그리드 판정에 보수적이다.

**이자·월말 규칙은 엔진의 함수를 그대로 부른다.** 이자일수 −1(결정 C57)과 「다음 달 첫 거래일」
(결정 C58)을 복제하면 두 곳이 조용히 갈라지고, 그 오차가 §13.3 의 판정을 뒤집을 수 있다.

**첫 거래일에는 어느 이자도 붙지 않는다.** RP 는 매수 당일이라 이자일수가 0 이고(결정 C57),
파킹은 기준 잔고가 전 거래일 마감 원화현금이라 0 이다(결정 C66). 두 규칙이 같은 날 같은 답을
내므로 벤치마크의 첫날은 **직전 거래일을 자기 자신으로 두어도 결과가 같다.**

**미청산은 세전 평가다** (결정 C8·C52). B&H 와 「분할매수 후 보유」는 끝까지 팔지 않으므로
청산 비용도 차익 과세도 붙지 않는다 — **ETF 경로에서는 원래 물어야 할 세금이 유예된 것**이라
그만큼 유리해 보인다. 그 편향은 결과 문서의 한계에 적는다.
"""

from dataclasses import dataclass, replace

import pandas as pd

from verify_lab.common_constants import COL_DATE, COL_VALUE
from verify_lab.report.constants import DATE_FORMAT
from verify_lab.strategy.grid.constants import (
    BENCHMARK_BUY_HOLD,
    BENCHMARK_KRW_PARKING,
    BENCHMARK_SPLIT_BUY_HOLD,
    COL_BLOCKED_COUNT,
    COL_BUY_COUNT,
    COL_COST,
    COL_PARKING_INTEREST,
    COL_RP_INTEREST,
    COL_SELL_COUNT,
    COL_TAX_PAID,
    COL_TOTAL_ASSETS,
    DAYS_PER_YEAR,
    DISPLAY_BENCHMARK_BUY_HOLD,
    DISPLAY_BENCHMARK_KRW_PARKING,
    DISPLAY_BENCHMARK_SPLIT_BUY_HOLD,
    INTEREST_TAX_RATE,
    PERCENT_TO_RATE,
    PURPOSE_BENCHMARK_BUY_HOLD,
    PURPOSE_BENCHMARK_KRW_PARKING,
    PURPOSE_BENCHMARK_SPLIT_BUY_HOLD,
)
from verify_lab.strategy.grid.engine import GridConfig, interest_days, is_settlement_day, run_grid
from verify_lab.strategy.grid.interest import RateSeries
from verify_lab.strategy.grid.metrics import evaluate_grid
from verify_lab.strategy.grid.paths.base import ExecutionPath
from verify_lab.strategy.grid.paths.exchange import ExchangePath
from verify_lab.strategy.performance import PerformanceMetrics, evaluate_curve
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 벤치마크마다 다른 부가 사실의 타입. 금액·건수·비율과 날짜 문자열이 섞인다
BenchmarkDetail = dict[str, float | int | str | None]


@dataclass(frozen=True)
class Benchmark:
    """벤치마크 하나의 곡선과 성적

    Attributes:
        key: 요약과 산출물에서 이 벤치마크를 가리키는 키
        name: 표시 이름
        purpose: 사양서 §13.3 이 적은 확인 목적
        curve: 일별 총자산 곡선. **전략 곡선과 같은 거래일 인덱스**를 갖는다 —
            그래야 같은 rf 계열로 지표가 나온다
        performance: 곡선 하나에서 나온 표준 지표 (사양서 §13.1)
        detail: 그 벤치마크에서만 의미가 있는 부가 사실.
            **비율 지표 하나로 판정하지 않기 위한 재료**다 — 「분할매수 후 보유」는
            MDD 보다 자금 소진과 최장 보유기간이 익절 로직의 기여를 더 잘 드러낸다
    """

    key: str
    name: str
    purpose: str
    curve: pd.Series
    performance: PerformanceMetrics
    detail: BenchmarkDetail


def build_benchmarks(
    series: pd.DataFrame,
    ranges: pd.DataFrame,
    *,
    config: GridConfig,
    rates: RateSeries,
    path: ExecutionPath,
    scheduled_path: ExecutionPath,
    exec_prices: pd.Series | None = None,
) -> tuple[Benchmark, ...]:
    """사양서 §13.3 의 벤치마크 3종을 만든다.

    입력은 **그리드 실행이 쓰는 것과 똑같다.** 같은 거래일·같은 가격·같은 금리를 겪어야
    비교가 성립하며, 갈리는 것은 **무엇을 사고 언제 파는가**뿐이다.

    Args:
        series: 일별 단일 값 시계열 **전 기간** (`load_series_csv` 가 돌려준 형태)
        ranges: 거래일별 범위표 (`build_daily_ranges` 가 돌려준 형태)
        config: 실행 파라미터
        rates: `ranges` 의 거래일에 맞춘 실수령 금리 계열
        path: 집행 경로. **「분할매수 후 보유」가 그리드와 같은 비용으로 산다**
        scheduled_path: 같은 상품을 **슬리피지 없이** 집행하는 경로.
            B&H 의 첫날 매수처럼 **돌파 판정이 없는 집행**에 쓴다 (결정 C60)
        exec_prices: `ranges` 의 거래일에 맞춘 집행 가격. 넘기지 않으면 판정 가격을 그대로 쓴다

    Returns:
        사양서 §13.3 표의 순서대로 벤치마크 셋

    Raises:
        ValueError: 범위표의 거래일이 시세에 없거나, 거래일이 둘 미만인 경우
    """
    dates = pd.DatetimeIndex(ranges[COL_DATE])
    closes = series.set_index(COL_DATE)[COL_VALUE].reindex(dates)
    if closes.isna().any():
        missing = dates[closes.isna().to_numpy()]
        raise ValueError(f"범위표의 거래일이 시세에 없습니다: {[str(day.date()) for day in missing[:5]]}")

    prices = closes if exec_prices is None else pd.Series(exec_prices.to_numpy(dtype=float), index=dates)
    risk_free = rates.risk_free.set_axis(dates)

    hold_curve, hold_detail = _buy_and_hold(
        dates, closes=closes, prices=prices, rates=rates, config=config, path=scheduled_path
    )
    split_curve, split_detail = _split_buy_hold(
        series, ranges, config=config, rates=rates, path=path, exec_prices=exec_prices
    )
    parking_curve, parking_detail = _krw_parking(dates, rates=rates, config=config)

    benchmarks = (
        Benchmark(
            key=BENCHMARK_BUY_HOLD,
            name=DISPLAY_BENCHMARK_BUY_HOLD,
            purpose=PURPOSE_BENCHMARK_BUY_HOLD,
            curve=hold_curve,
            performance=evaluate_curve(hold_curve, risk_free=risk_free),
            detail=hold_detail,
        ),
        Benchmark(
            key=BENCHMARK_SPLIT_BUY_HOLD,
            name=DISPLAY_BENCHMARK_SPLIT_BUY_HOLD,
            purpose=PURPOSE_BENCHMARK_SPLIT_BUY_HOLD,
            curve=split_curve,
            performance=evaluate_curve(split_curve, risk_free=risk_free),
            detail=split_detail,
        ),
        Benchmark(
            key=BENCHMARK_KRW_PARKING,
            name=DISPLAY_BENCHMARK_KRW_PARKING,
            purpose=PURPOSE_BENCHMARK_KRW_PARKING,
            curve=parking_curve,
            performance=evaluate_curve(parking_curve, risk_free=risk_free),
            detail=parking_detail,
        ),
    )

    logger.debug(
        "벤치마크 3종: "
        + " · ".join(f"{benchmark.name} {benchmark.performance.last_value:,.0f}원" for benchmark in benchmarks)
    )

    return benchmarks


def _buy_and_hold(
    dates: pd.DatetimeIndex,
    *,
    closes: pd.Series,
    prices: pd.Series,
    rates: RateSeries,
    config: GridConfig,
    path: ExecutionPath,
) -> tuple[pd.Series, BenchmarkDetail]:
    """첫 거래일에 전액을 사서 끝까지 들고 있는 곡선을 만든다 (사양서 §13.3 — 매매의 가치).

    보유 중 이자율은 **경로가 답한다** (결정 C69). 환전 경로는 달러 RP 금리를 그대로 받고
    ETF 는 캐리가 종가에 내재돼 언제나 0 이라, 이 함수에 경로 분기가 생기지 않는다.

    Args:
        dates: 거래일
        closes: 그날의 원달러 종가. **미인출 RP 이자는 달러라 언제나 이 값으로 환산**한다
        prices: 그날의 집행 가격
        rates: 실수령 금리 계열
        config: 실행 파라미터
        path: 슬리피지가 빠진 집행 경로

    Returns:
        일별 총자산 곡선과 부가 사실
    """
    # 월말 RP 이자 인출은 **달러를 원화로 바꾸는 정기 환전**이라 스프레드만 붙는다 (결정 C60)
    interest_path = ExchangePath(replace(config.cost, slippage_rate=0.0))

    acquisition = path.acquire(config.initial_capital, price=float(prices.iloc[0]))
    entry_date = pd.Timestamp(dates[0])

    # 정수 주식 수라 예산을 다 못 쓰는 경로가 있다. 남은 돈은 **현금으로 남아 파킹 이자를 받는다** (결정 C71)
    cash = config.initial_capital - acquisition.spent

    accrued_rp_usd = 0.0
    accrued_parking = 0.0
    previous_cash = 0.0
    previous_date = entry_date

    rp_total = 0.0
    parking_total = 0.0
    tax_total = 0.0
    cost_total = acquisition.cost

    values: list[float] = []
    for offset, current in enumerate(dates):
        date = pd.Timestamp(current)
        close = float(closes.iloc[offset])
        elapsed = int((date - previous_date).days)

        # 1. 이자. 엔진과 같은 규칙을 **같은 함수로** 얹는다 (결정 C57·C66)
        holding_rate = path.holding_interest_rate(float(rates.rp.iloc[offset]))
        days = interest_days(entry_date=entry_date, date=date, previous=previous_date)
        rp_interest_usd = acquisition.units * (holding_rate / PERCENT_TO_RATE) * days / DAYS_PER_YEAR
        parking_interest = (
            previous_cash * (float(rates.parking.iloc[offset]) / PERCENT_TO_RATE) * elapsed / DAYS_PER_YEAR
        )

        accrued_rp_usd += rp_interest_usd
        accrued_parking += parking_interest
        rp_total += rp_interest_usd * close
        parking_total += parking_interest

        # 2. 월말 정산. 과세 기준은 **세전 이자**이고 환전 비용은 빼지 않는다 (결정 C63)
        if is_settlement_day(date, previous=previous_date):
            liquidation = interest_path.liquidate(accrued_rp_usd, price=close)
            tax = (liquidation.notional + accrued_parking) * INTEREST_TAX_RATE
            cash += liquidation.notional - liquidation.cost + accrued_parking - tax

            cost_total += liquidation.cost
            tax_total += tax
            accrued_rp_usd = 0.0
            accrued_parking = 0.0

        # 3. 평가. **미인출 이자도 총자산에 들어간다** (결정 C7·C64)
        values.append(cash + acquisition.units * float(prices.iloc[offset]) + accrued_rp_usd * close + accrued_parking)

        previous_cash = cash
        previous_date = date

    detail: BenchmarkDetail = {
        "units": acquisition.units,
        "entry_price": float(prices.iloc[0]),
        "entry_cost": acquisition.cost,
        "leftover_cash": config.initial_capital - acquisition.spent,
        # 끝까지 팔지 않으므로 이 손익은 **세전**이다 (결정 C8). ETF 경로에서는 여기에 붙었을
        # 차익 15.4% 가 통째로 유예된 것이라, 그 크기를 알아야 편향을 한계에 적을 수 있다
        "open_unrealised": acquisition.units * float(prices.iloc[-1]) - acquisition.spent,
        "rp_interest_total": rp_total,
        "parking_interest_total": parking_total,
        "interest_total": rp_total + parking_total,
        "tax_paid_total": tax_total,
        "cost_total": cost_total,
        "accrued_interest": accrued_rp_usd * float(closes.iloc[-1]) + accrued_parking,
    }

    return pd.Series(values, index=dates, dtype=float), detail


def _krw_parking(
    dates: pd.DatetimeIndex,
    *,
    rates: RateSeries,
    config: GridConfig,
) -> tuple[pd.Series, BenchmarkDetail]:
    """전액을 원화 파킹 금리로 굴리는 곡선을 만든다 (사양서 §13.3 — 리스크 대비 정당성).

    **무위험 수익률(rf)과 다른 값이다.** rf 는 CD91 원지표 세후라 하한이 없고(결정 C87),
    여기는 그리드의 대기자금이 실제로 받는 **실수령 파킹 금리**(하한 있음)다.
    하한이 걸리는 저금리 구간에서는 이 벤치마크가 rf 보다 높아지므로 둘을 섞으면 안 된다.

    Args:
        dates: 거래일
        rates: 실수령 금리 계열
        config: 실행 파라미터

    Returns:
        일별 총자산 곡선과 부가 사실
    """
    cash = config.initial_capital
    accrued = 0.0
    previous_cash = 0.0
    previous_date = pd.Timestamp(dates[0])

    interest_total = 0.0
    tax_total = 0.0

    values: list[float] = []
    for offset, current in enumerate(dates):
        date = pd.Timestamp(current)
        elapsed = int((date - previous_date).days)

        # 1. 이자. 기준 잔고는 **전 거래일 마감 원화현금**이라 첫날은 0 이다 (결정 C66)
        interest = previous_cash * (float(rates.parking.iloc[offset]) / PERCENT_TO_RATE) * elapsed / DAYS_PER_YEAR
        accrued += interest
        interest_total += interest

        # 2. 월말 정산. 인출된 이자가 현금이 되어 다음 달부터 함께 이자를 받는다
        if is_settlement_day(date, previous=previous_date):
            tax = accrued * INTEREST_TAX_RATE
            cash += accrued - tax
            tax_total += tax
            accrued = 0.0

        values.append(cash + accrued)

        previous_cash = cash
        previous_date = date

    detail: BenchmarkDetail = {
        "parking_interest_total": interest_total,
        "tax_paid_total": tax_total,
        "accrued_interest": accrued,
    }

    return pd.Series(values, index=dates, dtype=float), detail


def _split_buy_hold(
    series: pd.DataFrame,
    ranges: pd.DataFrame,
    *,
    config: GridConfig,
    rates: RateSeries,
    path: ExecutionPath,
    exec_prices: pd.Series | None,
) -> tuple[pd.Series, BenchmarkDetail]:
    """그리드와 같은 레벨·같은 금액으로 사되 팔지 않는 곡선을 만든다 (사양서 §13.3 — §13.3 의 판정).

    **엔진을 매도만 끄고 다시 돌린다** (결정 C11). 매수·배분·판정이 같은 코드를 그대로 지나므로
    두 곡선의 차이가 **익절 로직 하나**에서 나온다는 것이 구조로 보장된다.

    부가 사실에 **자금 소진과 최장 보유기간**을 함께 담는다. 팔지 않으면 슬롯이 쌓이기만 해
    현금이 빨리 마르는데, MDD 같은 비율 지표만 보면 그 대가가 통째로 보이지 않는다.

    Args:
        series: 일별 단일 값 시계열 전 기간
        ranges: 거래일별 범위표
        config: 실행 파라미터
        rates: 실수령 금리 계열
        path: 집행 경로. **그리드와 같은 비용**으로 산다
        exec_prices: 거래일에 맞춘 집행 가격

    Returns:
        일별 총자산 곡선과 부가 사실
    """
    result = run_grid(
        series,
        ranges,
        config=config,
        rates=rates,
        path=path,
        exec_prices=exec_prices,
        sell_enabled=False,
    )
    grid = evaluate_grid(result)

    daily = result.daily
    blocked = daily[daily[COL_BLOCKED_COUNT] > 0]

    detail: BenchmarkDetail = {
        "buy_fills": int(daily[COL_BUY_COUNT].sum()),
        "sell_fills": int(daily[COL_SELL_COUNT].sum()),
        "open_slots": len(result.open_slots),
        "open_unrealised": result.open_unrealised,
        "blocked_days": grid.blocked_days,
        "blocked_day_ratio": grid.blocked_day_ratio,
        "first_blocked_date": None if blocked.empty else pd.Timestamp(blocked[COL_DATE].iloc[0]).strftime(DATE_FORMAT),
        "deployment_mean": grid.deployment_mean,
        "hold_days_max": grid.hold_days_max,
        "unrealised_worst_rate": grid.unrealised_worst_rate,
        "interest_total": float(daily[COL_RP_INTEREST].sum() + daily[COL_PARKING_INTEREST].sum()),
        "tax_paid_total": float(daily[COL_TAX_PAID].sum()),
        "cost_total": float(daily[COL_COST].sum()),
    }

    return daily.set_index(COL_DATE)[COL_TOTAL_ASSETS], detail
