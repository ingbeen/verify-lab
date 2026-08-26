"""사양서 §13.3 벤치마크 3종의 계약을 고정한다.

**벤치마크는 틀려도 그럴듯해 보인다.** 이자를 하루 더 주거나 원천징수를 빠뜨려도 곡선은
매끄럽게 우상향하고, 그 오차가 §13.3 의 판정("그리드가 분할매수 후 보유를 이기는가")을
뒤집을 수 있다. 그래서 아래 넷을 계약으로 박아 둔다.

- **B&H 의 첫날 매수에는 슬리피지가 붙지 않는다** — 돌파 판정이 없는 정기 집행이다 (결정 C60 과 같은 논리)
- **이자일수 −1 과 첫 거래일 규칙이 엔진과 같다** — 첫날에는 어느 이자도 붙지 않는다 (결정 C57·C66)
- **보유 이자율을 경로가 답한다** — ETF 는 캐리가 종가에 내재돼 언제나 0 이다 (결정 C69)
- **세 곡선이 전략 곡선과 같은 거래일 인덱스를 갖는다** — 그래야 같은 rf 계열로 지표가 나온다

깊은 계약(매수 규칙이 같은가·슬롯이 쌓이기만 하는가)은 엔진 쪽에 있다.
여기서는 **벤치마크가 그 결과를 그대로 싣는지**만 본다.
"""

from collections.abc import Callable, Sequence
from dataclasses import replace

import pandas as pd
import pytest

from verify_lab.common_constants import COL_DATE, COL_VALUE
from verify_lab.strategy.grid.benchmarks import Benchmark, build_benchmarks
from verify_lab.strategy.grid.constants import (
    BENCHMARK_BUY_HOLD,
    BENCHMARK_KRW_PARKING,
    BENCHMARK_SPLIT_BUY_HOLD,
    COL_TOTAL_ASSETS,
    COL_USD_VALUE,
    DEFAULT_ALLOCATION_SPREAD,
    DEFAULT_MIN_RANGE_WIDTH,
    DEFAULT_SLOT_CAP_RATIO,
    INITIAL_CAPITAL,
    INTEREST_TAX_RATE,
    LOWER_BREACH_HOLD,
    PATH_ETF_1X,
)
from verify_lab.strategy.grid.engine import GridConfig, run_grid
from verify_lab.strategy.grid.interest import InterestConfig, RateSeries
from verify_lab.strategy.grid.paths.base import CostConfig, ExecutionPath
from verify_lab.strategy.grid.paths.etf import EtfPath
from verify_lab.strategy.grid.paths.exchange import ExchangePath
from verify_lab.strategy.grid.price_range import build_daily_ranges

# 손계산이 쉽도록 익절폭을 크게 잡는다
HAND_GROWTH = 0.05

# 워밍업 12개월 + 매매 구간
WARMUP_MONTHS = 12
TRADING_START = pd.Timestamp("2020-01-01")

# 금액 비교 허용오차
AMOUNT_TOLERANCE = 0.01

# 비용이 없는 설정. 곡선이 가격에 정비례해 손계산이 가능해진다
FREE_COST = CostConfig(exchange_spread_rate=0.0, slippage_rate=0.0, brokerage_rate=0.0)

# 확정된 기본 비용 (결정 C35). 환전 편도 0.18% 중 **슬리피지 0.10% 는 B&H 에 붙지 않는다**
PAID_COST = CostConfig(exchange_spread_rate=0.0008, slippage_rate=0.0010, brokerage_rate=0.00015)

# 이자가 없는 설정. 하한이 0이면 금리 0을 그대로 통과시킨다
FREE_INTEREST = InterestConfig(rp_floor_rate=0.0, parking_floor_rate=0.0)


def _config(*, cost: CostConfig | None = None) -> GridConfig:
    """손계산용 기본 설정. 비용을 넘기지 않으면 없음이라 회계가 단순해진다."""
    return GridConfig(
        lookback_years=1,
        growth_rate=HAND_GROWTH,
        min_range_width=DEFAULT_MIN_RANGE_WIDTH,
        allocation_spread=DEFAULT_ALLOCATION_SPREAD,
        slot_cap_ratio=DEFAULT_SLOT_CAP_RATIO,
        initial_capital=INITIAL_CAPITAL,
        cost=cost or FREE_COST,
        interest=FREE_INTEREST,
    )


def _rates(ranges: pd.DataFrame, *, rp: float = 0.0, parking: float = 0.0) -> RateSeries:
    """범위표의 거래일에 맞춘 **고정 금리** 계열. 0이면 이자가 발생하지 않는다."""
    index = pd.DatetimeIndex(ranges[COL_DATE])

    return RateSeries(
        rp=pd.Series(rp, index=index, dtype=float),
        parking=pd.Series(parking, index=index, dtype=float),
        risk_free=pd.Series(parking, index=index, dtype=float),
        # 원지표는 이 테스트가 쓰지 않는다. 가공 금리를 그대로 두어 두 계열이 어긋나지 않게 한다
        tbill=pd.Series(rp, index=index, dtype=float),
        cd91=pd.Series(parking, index=index, dtype=float),
        rp_filled=0,
        parking_filled=0,
    )


def _series(values: Sequence[float], *, start: str = "2019-01-01") -> pd.DataFrame:
    """월 3거래일짜리 시계열을 만든다. 값은 달마다 하나씩 주고 그 달 안에서 반복한다."""
    rows: list[tuple[pd.Timestamp, float]] = []
    months = pd.period_range(start, periods=len(values), freq="M")
    for month, value in zip(months, values, strict=True):
        for day in pd.bdate_range(f"{month}-01", periods=3):
            rows.append((day, value))

    return pd.DataFrame(rows, columns=[COL_DATE, COL_VALUE])


def _daily_series(warmup: float, path: Sequence[float]) -> pd.DataFrame:
    """워밍업 12개월(값 고정) 뒤에 매매 구간의 일별 경로를 붙인다."""
    frame = _series([warmup] * WARMUP_MONTHS)
    days = pd.bdate_range(TRADING_START, periods=len(path))
    tail = pd.DataFrame({COL_DATE: days, COL_VALUE: list(path)})

    return pd.concat([frame, tail], ignore_index=True).sort_values(COL_DATE).reset_index(drop=True)


def _ranges(series: pd.DataFrame, config: GridConfig) -> pd.DataFrame:
    """범위표를 만든다."""
    return build_daily_ranges(
        series,
        start_date=TRADING_START,
        lookback_years=config.lookback_years,
        min_range_width=config.min_range_width,
        lower_breach=LOWER_BREACH_HOLD,
    )


def _build(
    series: pd.DataFrame,
    *,
    config: GridConfig | None = None,
    rp: float = 0.0,
    parking: float = 0.0,
    path: ExecutionPath | None = None,
    exec_prices: pd.Series | None = None,
) -> tuple[Benchmark, ...]:
    """벤치마크 3종을 만든다. **정기 집행 경로는 슬리피지를 뺀 같은 경로**다."""
    settings = config or _config()
    ranges = _ranges(series, settings)
    execution: ExecutionPath = path or ExchangePath(settings.cost)

    # 정기 집행에는 슬리피지가 붙지 않는다 (결정 C60). 같은 상품을 비용만 바꿔 다시 만든다
    plain = replace(settings.cost, slippage_rate=0.0)
    scheduled: ExecutionPath = (
        EtfPath(ticker=execution.name, cost=plain) if isinstance(execution, EtfPath) else ExchangePath(plain)
    )

    return build_benchmarks(
        series,
        ranges,
        config=settings,
        rates=_rates(ranges, rp=rp, parking=parking),
        path=execution,
        scheduled_path=scheduled,
        exec_prices=exec_prices,
    )


def _pick(benchmarks: Sequence[Benchmark], key: str) -> Benchmark:
    """키로 벤치마크 하나를 고른다."""
    return next(benchmark for benchmark in benchmarks if benchmark.key == key)


class TestBuyAndHold:
    """「B&H + 달러 RP」의 계약을 고정한다 (사양서 §13.3 — 매매의 가치)."""

    def test_첫날_매수에_슬리피지가_붙지_않는다(self) -> None:
        """
        목적: **결정 C60 의 논리를 잇는다** — 돌파 판정이 없는 집행에는 슬리피지가 없다

        Given: 평평한 경로와 기본 비용(환전 스프레드 0.08% + 슬리피지 0.10%)
        When: 벤치마크를 만든다
        Then: 매수비용이 스프레드 몫뿐이고 슬리피지가 빠져 있다
        """
        # Given
        series = _daily_series(1000.0, [1000.0, 1000.0, 1000.0])

        # When
        actual = _pick(_build(series, config=_config(cost=PAID_COST)), BENCHMARK_BUY_HOLD)

        # Then
        expected = INITIAL_CAPITAL * PAID_COST.exchange_spread_rate
        assert actual.detail["entry_cost"] == pytest.approx(expected, abs=AMOUNT_TOLERANCE)

    def test_첫날_총자산이_비용만큼만_줄어든다(self) -> None:
        """
        목적: 전액이 실제로 투입됨을 고정한다 — 예산 밖으로 새는 돈이 없다

        Given: 평평한 경로와 기본 비용
        When: 벤치마크를 만든다
        Then: 첫날 총자산이 `초기 자본금 − 매수비용` 이다
        """
        # Given
        series = _daily_series(1000.0, [1000.0, 1000.0, 1000.0])

        # When
        actual = _pick(_build(series, config=_config(cost=PAID_COST)), BENCHMARK_BUY_HOLD)

        # Then
        cost = float(actual.detail["entry_cost"])  # type: ignore[arg-type]
        assert float(actual.curve.iloc[0]) == pytest.approx(INITIAL_CAPITAL - cost, abs=AMOUNT_TOLERANCE)

    def test_비용도_이자도_없으면_곡선이_환율에_정비례한다(self) -> None:
        """
        목적: 「사서 들고만 있는다」의 정의를 고정한다

        Given: 오르내리는 경로, 비용 0·이자 0
        When: 벤치마크를 만든다
        Then: 총자산이 `자본금 × 그날 환율 ÷ 첫날 환율` 이다
        """
        # Given
        path = [1000.0, 1100.0, 900.0, 1200.0]
        series = _daily_series(1000.0, path)

        # When
        actual = _pick(_build(series), BENCHMARK_BUY_HOLD)

        # Then
        expected = [INITIAL_CAPITAL * price / path[0] for price in path]
        assert actual.curve.tolist() == pytest.approx(expected, abs=AMOUNT_TOLERANCE)

    def test_첫_거래일에는_이자가_붙지_않는다(self) -> None:
        """
        목적: **이자일수 −1** 을 고정한다 (결정 C57) — 매수 당일은 이자가 없다

        Given: 평평한 경로에 RP 금리를 양수로 준 설정 (비용 0)
        When: 벤치마크를 만든다
        Then: 첫날 총자산이 초기 자본금 그대로다
        """
        # Given
        series = _daily_series(1000.0, [1000.0, 1000.0, 1000.0])

        # When
        actual = _pick(_build(series, rp=5.0), BENCHMARK_BUY_HOLD)

        # Then
        assert float(actual.curve.iloc[0]) == pytest.approx(INITIAL_CAPITAL, abs=AMOUNT_TOLERANCE)

    def test_보유하는_동안_RP_이자가_쌓인다(self) -> None:
        """
        목적: 보유 중 이자가 곡선에 실림을 고정한다 (사양서 §9.1)

        Given: 평평한 경로에 RP 금리를 양수로 준 설정 (비용 0)
        When: 벤치마크를 만든다
        Then: 마지막 총자산이 초기 자본금보다 크고 RP 이자 합계가 양수다
        """
        # Given
        series = _daily_series(1000.0, [1000.0] * 8)

        # When
        actual = _pick(_build(series, rp=5.0), BENCHMARK_BUY_HOLD)

        # Then
        assert float(actual.curve.iloc[-1]) > INITIAL_CAPITAL
        assert float(actual.detail["rp_interest_total"]) > 0  # type: ignore[arg-type]

    def test_종료_평가에_청산_비용과_세금이_붙지_않는다(self) -> None:
        """
        목적: 미청산 세전 평가를 고정한다 (결정 C8·C52)

        Given: 오른 경로와 기본 비용
        When: 벤치마크를 만든다
        Then: 마지막 총자산이 `보유 단위 × 마지막 가격 + 잔여현금` 이다
        """
        # Given
        series = _daily_series(1000.0, [1000.0, 1100.0, 1200.0])

        # When
        actual = _pick(_build(series, config=_config(cost=PAID_COST)), BENCHMARK_BUY_HOLD)

        # Then
        units = float(actual.detail["units"])  # type: ignore[arg-type]
        leftover = float(actual.detail["leftover_cash"])  # type: ignore[arg-type]
        assert float(actual.curve.iloc[-1]) == pytest.approx(units * 1200.0 + leftover, abs=AMOUNT_TOLERANCE)

    def test_미청산_평가손익을_세전으로_남긴다(self) -> None:
        """
        목적: **결정 C8 의 편향 크기를 잴 수 있게** 고정한다

        Given: 오른 경로와 기본 비용
        When: 벤치마크를 만든다
        Then: 미청산 평가손익이 `보유 단위 × 마지막 가격 − 실제 지출` 이다

        Note:
            ETF 경로에서는 여기에 붙었을 **차익 15.4% 가 통째로 유예**된 값이라,
            크기를 모르면 그만큼 유리해 보이는 편향을 결과 문서에 적을 수 없다
        """
        # Given
        series = _daily_series(1000.0, [1000.0, 1100.0, 1200.0])

        # When
        actual = _pick(_build(series, config=_config(cost=PAID_COST)), BENCHMARK_BUY_HOLD)

        # Then
        units = float(actual.detail["units"])  # type: ignore[arg-type]
        spent = INITIAL_CAPITAL - float(actual.detail["leftover_cash"])  # type: ignore[arg-type]
        assert float(actual.detail["open_unrealised"]) == pytest.approx(  # type: ignore[arg-type]
            units * 1200.0 - spent, abs=AMOUNT_TOLERANCE
        )

    def test_ETF_경로는_보유_이자가_0이다(self) -> None:
        """
        목적: **결정 C69 를 고정한다** — 캐리가 종가에 내재돼 이자를 더하면 이중계산이다

        Given: RP 금리를 크게 준 설정과 ETF 경로
        When: 벤치마크를 만든다
        Then: RP 이자 합계가 0 이다
        """
        # Given
        series = _daily_series(10_000.0, [10_000.0] * 8)
        config = _config(cost=PAID_COST)
        ranges = _ranges(series, config)
        prices = pd.Series(10_000.0, index=pd.DatetimeIndex(ranges[COL_DATE]), dtype=float)

        # When
        actual = _pick(
            _build(
                series, config=config, rp=5.0, path=EtfPath(ticker=PATH_ETF_1X, cost=config.cost), exec_prices=prices
            ),
            BENCHMARK_BUY_HOLD,
        )

        # Then
        assert float(actual.detail["rp_interest_total"]) == pytest.approx(0.0, abs=AMOUNT_TOLERANCE)  # type: ignore[arg-type]

    def test_ETF_경로는_정수_주식만_사고_잔액이_현금으로_남는다(self) -> None:
        """
        목적: **결정 C71 을 고정한다** — 못 쓴 예산은 사라지지도 넘어가지도 않는다

        Given: 한 주 값으로 나누어떨어지지 않는 자본금과 ETF 경로
        When: 벤치마크를 만든다
        Then: 보유 주식 수가 정수이고 잔액이 현금으로 남는다
        """
        # Given
        series = _daily_series(10_007.0, [10_007.0] * 4)
        config = _config(cost=PAID_COST)
        ranges = _ranges(series, config)
        prices = pd.Series(10_007.0, index=pd.DatetimeIndex(ranges[COL_DATE]), dtype=float)

        # When
        actual = _pick(
            _build(series, config=config, path=EtfPath(ticker=PATH_ETF_1X, cost=config.cost), exec_prices=prices),
            BENCHMARK_BUY_HOLD,
        )

        # Then
        units = float(actual.detail["units"])  # type: ignore[arg-type]
        leftover = float(actual.detail["leftover_cash"])  # type: ignore[arg-type]
        assert units == int(units)
        assert 0 < leftover < 10_007.0


class TestKrwParking:
    """「원화 파킹 100%」의 계약을 고정한다 (사양서 §13.3 — 리스크 대비 정당성).

    **rf 와 다른 값이다.** rf 는 CD91 원지표 세후(하한 없음)이고 이 벤치마크는
    실수령 파킹 금리(하한 있음)라, 하한이 걸리는 구간에서는 rf 보다 높아지기도 한다.
    """

    def test_금리가_0이면_총자산이_자본금_그대로다(self) -> None:
        """
        목적: 엣지 케이스 — 이자가 없으면 아무 일도 일어나지 않는다

        Given: 파킹 금리 0
        When: 벤치마크를 만든다
        Then: 모든 거래일의 총자산이 초기 자본금이다
        """
        # Given
        series = _daily_series(1000.0, [1000.0, 1100.0, 900.0])

        # When
        actual = _pick(_build(series), BENCHMARK_KRW_PARKING)

        # Then
        assert actual.curve.tolist() == pytest.approx([INITIAL_CAPITAL] * len(actual.curve), abs=AMOUNT_TOLERANCE)

    def test_첫_거래일에는_이자가_없다(self) -> None:
        """
        목적: **결정 C66 을 고정한다** — 기준 잔고가 전 거래일 마감 원화현금이다

        Given: 파킹 금리 양수
        When: 벤치마크를 만든다
        Then: 첫날 총자산이 초기 자본금 그대로다
        """
        # Given
        series = _daily_series(1000.0, [1000.0] * 6)

        # When
        actual = _pick(_build(series, parking=5.0), BENCHMARK_KRW_PARKING)

        # Then
        assert float(actual.curve.iloc[0]) == pytest.approx(INITIAL_CAPITAL, abs=AMOUNT_TOLERANCE)

    def test_환율이_움직여도_총자산이_흔들리지_않는다(self) -> None:
        """
        목적: 「전액 원화 대기」의 정의를 고정한다 — 환율 위험이 없다

        Given: 크게 오르내리는 경로와 파킹 금리 양수
        When: 벤치마크를 만든다
        Then: 총자산이 한 번도 줄지 않는다
        """
        # Given
        series = _daily_series(1000.0, [1000.0, 1500.0, 700.0, 1200.0, 800.0])

        # When
        actual = _pick(_build(series, parking=5.0), BENCHMARK_KRW_PARKING)

        # Then
        assert (actual.curve.diff().dropna() >= -AMOUNT_TOLERANCE).all()

    def test_총자산이_세전_이자에서_원천징수를_뺀_값이다(self) -> None:
        """
        목적: **15.4% 원천징수**를 고정한다 (사양서 §10)

        Given: 달을 넘기는 경로와 파킹 금리 양수
        When: 벤치마크를 만든다
        Then: 마지막 총자산이 `자본금 + 세전 이자 − 원천징수` 이고, 세금이 실제로 걷혔다
        """
        # Given
        series = _daily_series(1000.0, [1000.0] * 45)

        # When
        actual = _pick(_build(series, parking=5.0), BENCHMARK_KRW_PARKING)

        # Then
        interest = float(actual.detail["parking_interest_total"])  # type: ignore[arg-type]
        tax = float(actual.detail["tax_paid_total"])  # type: ignore[arg-type]
        assert tax > 0
        assert float(actual.curve.iloc[-1]) == pytest.approx(INITIAL_CAPITAL + interest - tax, abs=AMOUNT_TOLERANCE)

    def test_인출된_이자에_다음_달부터_이자가_붙는다(self) -> None:
        """
        목적: 월복리를 고정한다 — 인출된 이자가 현금이 되어 다음 달 기준 잔고를 키운다

        Given: 달을 넘기는 경로와 파킹 금리 양수
        When: 벤치마크를 만든다
        Then: 세전 이자 합계가 **자본금에만 붙는 단리보다 크다**
        """
        # Given
        series = _daily_series(1000.0, [1000.0] * 45)

        # When
        actual = _pick(_build(series, parking=5.0), BENCHMARK_KRW_PARKING)

        # Then — 정산이 한 번이라도 일어났다면 기준 잔고가 자본금보다 커진 날이 있다
        interest = float(actual.detail["parking_interest_total"])  # type: ignore[arg-type]
        elapsed = int((actual.curve.index[-1] - actual.curve.index[0]).days)
        simple = INITIAL_CAPITAL * (5.0 / 100.0) * elapsed / 365.0
        assert interest > simple

    def test_원천징수는_인출된_이자에만_붙는다(self) -> None:
        """
        목적: **결정 C7·C64 를 고정한다** — 미인출 이자는 세전으로 총자산에 들어간다

        Given: 달을 넘기는 경로와 파킹 금리 양수
        When: 벤치마크를 만든다
        Then: 세금이 `(세전 이자 − 미인출 이자) × 15.4%` 다
        """
        # Given
        series = _daily_series(1000.0, [1000.0] * 45)

        # When
        actual = _pick(_build(series, parking=5.0), BENCHMARK_KRW_PARKING)

        # Then
        interest = float(actual.detail["parking_interest_total"])  # type: ignore[arg-type]
        accrued = float(actual.detail["accrued_interest"])  # type: ignore[arg-type]
        assert float(actual.detail["tax_paid_total"]) == pytest.approx(  # type: ignore[arg-type]
            (interest - accrued) * INTEREST_TAX_RATE, abs=AMOUNT_TOLERANCE
        )


class TestSplitBuyHold:
    """「분할매수 후 보유」의 계약을 고정한다 (사양서 §13.3 — 익절 로직의 순수 기여).

    **매수 규칙이 같음은 엔진 쪽 계약이다** (`test_strategy_grid_engine.py`).
    여기서는 벤치마크가 그 결과를 그대로 싣는지만 본다.
    """

    ROUND_TRIP_PATH = ([1200.0, 1120.0, 1040.0, 1120.0, 1200.0, 1280.0] * 10)[:55]

    def _series_with_round_trips(self) -> pd.DataFrame:
        """매수와 매도가 모두 나오는 긴 경로."""
        days = pd.bdate_range(TRADING_START, periods=len(self.ROUND_TRIP_PATH))

        return pd.concat(
            [
                _series([1200.0] * WARMUP_MONTHS),
                pd.DataFrame({COL_DATE: days, COL_VALUE: self.ROUND_TRIP_PATH}),
            ],
            ignore_index=True,
        )

    def test_매도가_한_건도_없다(self) -> None:
        """
        목적: 「사되 팔지 않는다」를 고정한다 (결정 C11)

        Given: 매도가 실제로 일어나는 경로
        When: 벤치마크를 만든다
        Then: 매도 체결이 0건이고 보유 슬롯이 남아 있다
        """
        # Given
        series = self._series_with_round_trips()

        # When
        actual = _pick(_build(series, config=_config(cost=PAID_COST)), BENCHMARK_SPLIT_BUY_HOLD)

        # Then
        assert actual.detail["sell_fills"] == 0
        assert int(actual.detail["open_slots"]) > 0  # type: ignore[arg-type]

    def test_자금_소진과_최장_보유를_함께_낸다(self) -> None:
        """
        목적: **비율 지표 하나로 판정하지 않는다** (ROADMAP 계층 계약)

        Given: 매수가 일어나는 경로
        When: 벤치마크를 만든다
        Then: 자금 소진율·평균 투입률·최장 보유기간이 요약에 실린다
        """
        # Given
        series = self._series_with_round_trips()

        # When
        actual = _pick(_build(series, config=_config(cost=PAID_COST)), BENCHMARK_SPLIT_BUY_HOLD)

        # Then
        for field in ("blocked_days", "blocked_day_ratio", "deployment_mean", "hold_days_max"):
            assert field in actual.detail, f"요약에 {field} 가 없습니다"

    def test_그리드보다_투입률이_높다(self) -> None:
        """
        목적: 익절 로직의 기여가 어디서 갈리는지를 고정한다 — 팔지 않으면 노출이 쌓인다

        Given: 사고파는 경로
        When: 그리드와 벤치마크를 각각 돌린다
        Then: 벤치마크의 평균 투입률이 그리드보다 높다
        """
        # Given
        series = self._series_with_round_trips()
        config = _config(cost=PAID_COST)
        ranges = _ranges(series, config)

        # When
        grid = run_grid(
            series,
            ranges,
            config=config,
            rates=_rates(ranges),
            path=ExchangePath(config.cost),
        )
        actual = _pick(_build(series, config=config), BENCHMARK_SPLIT_BUY_HOLD)

        # Then
        grid_deployment = float((grid.daily[COL_USD_VALUE] / grid.daily[COL_TOTAL_ASSETS]).mean())
        assert float(actual.detail["deployment_mean"]) > grid_deployment  # type: ignore[arg-type]


class TestCommonContract:
    """세 벤치마크에 공통으로 걸리는 계약을 고정한다."""

    def test_세_벤치마크가_사양서_순서로_나온다(self) -> None:
        """
        목적: §13.3 표의 순서를 고정한다 — 판정인 「분할매수 후 보유」가 가운데다

        Given: 아무 경로
        When: 벤치마크를 만든다
        Then: 키가 §13.3 의 순서대로 셋이다
        """
        # Given
        series = _daily_series(1000.0, [1000.0, 1100.0, 900.0])

        # When
        actual = _build(series)

        # Then
        assert [benchmark.key for benchmark in actual] == [
            BENCHMARK_BUY_HOLD,
            BENCHMARK_SPLIT_BUY_HOLD,
            BENCHMARK_KRW_PARKING,
        ]

    def test_곡선의_인덱스가_전략_곡선과_같다(self) -> None:
        """
        목적: 같은 rf 계열로 지표를 낼 수 있음을 고정한다 (결정 C87·C88)

        Given: 사고파는 경로
        When: 그리드와 벤치마크를 각각 돌린다
        Then: 네 곡선의 거래일 인덱스가 정확히 같다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1130.0, 1220.0, 1130.0, 1240.0])
        config = _config(cost=PAID_COST)
        ranges = _ranges(series, config)

        # When
        grid = run_grid(series, ranges, config=config, rates=_rates(ranges), path=ExchangePath(config.cost))
        actual = _build(series, config=config)

        # Then
        expected = pd.DatetimeIndex(grid.daily[COL_DATE])
        for benchmark in actual:
            assert benchmark.curve.index.equals(expected), f"{benchmark.name} 의 거래일이 다릅니다"

    def test_총자산이_언제나_양수다(self) -> None:
        """
        목적: 지표 계층이 요구하는 전제를 고정한다 — 0 이하가 있으면 `evaluate_curve` 가 거부한다

        Given: 크게 떨어지는 경로
        When: 벤치마크를 만든다
        Then: 세 곡선의 모든 값이 양수다
        """
        # Given
        series = _daily_series(1200.0, [1200.0 * (0.95**step) for step in range(20)])

        # When
        actual = _build(series, config=_config(cost=PAID_COST), rp=2.0, parking=3.0)

        # Then
        for benchmark in actual:
            assert (benchmark.curve > 0).all(), f"{benchmark.name} 에 0 이하가 있습니다"

    def test_표준_지표가_함께_나온다(self) -> None:
        """
        목적: **곡선 하나만 받는 함수를 그대로 재사용함**을 고정한다 (결정 B1·C94)

        Given: 오르내리는 경로
        When: 벤치마크를 만든다
        Then: 셋 다 표준 지표를 갖고 종료 총자산이 곡선의 마지막 값과 같다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1130.0, 1220.0, 1130.0, 1240.0])

        # When
        actual = _build(series, config=_config(cost=PAID_COST))

        # Then
        for benchmark in actual:
            assert benchmark.performance.last_value == pytest.approx(
                float(benchmark.curve.iloc[-1]), abs=AMOUNT_TOLERANCE
            )

    def test_평평한_시세에_비용도_이자도_없으면_셋_다_자본금_그대로다(self) -> None:
        """
        목적: 엣지 케이스 — 아무 일도 일어나지 않는 실행을 고정한다

        Given: 평평한 경로, 비용 0, 이자 0
        When: 벤치마크를 만든다
        Then: 세 곡선이 전부 초기 자본금이다
        """
        # Given
        series = _daily_series(1000.0, [1000.0] * 5)

        # When
        actual = _build(series)

        # Then
        for benchmark in actual:
            assert benchmark.curve.tolist() == pytest.approx(
                [INITIAL_CAPITAL] * len(benchmark.curve), abs=AMOUNT_TOLERANCE
            ), f"{benchmark.name} 이 자본금과 다릅니다"


class TestLookAhead:
    """벤치마크도 미래를 참조하지 않음을 고정한다 (`tests/CLAUDE.md` 필수 테스트)."""

    LONG_PATH = ([1200.0, 1150.0, 1100.0, 1160.0, 1220.0, 1140.0] * 10)[:55]

    def _series(self) -> pd.DataFrame:
        """뒤를 잘라 비교할 만큼 긴 경로."""
        days = pd.bdate_range(TRADING_START, periods=len(self.LONG_PATH))

        return pd.concat(
            [_series([1200.0] * WARMUP_MONTHS), pd.DataFrame({COL_DATE: days, COL_VALUE: self.LONG_PATH})],
            ignore_index=True,
        )

    @pytest.mark.parametrize("key", [BENCHMARK_BUY_HOLD, BENCHMARK_SPLIT_BUY_HOLD, BENCHMARK_KRW_PARKING])
    def test_뒤를_잘라도_겹치는_날의_총자산이_같다(self, key: str, assert_stable_under_truncation: Callable[..., None]) -> None:
        """
        목적: look-ahead 감시 계약을 벤치마크에도 건다

        Given: 오르내리는 긴 경로
        When: 뒤를 잘라낸 시세와 전체 시세로 각각 벤치마크를 만든다
        Then: 겹치는 날의 총자산이 같다

        Note:
            월말 정산을 「그 달의 마지막 거래일」로 잡으면 그 판정에 다음 행이 필요해
            여기서 걸린다. **「다음 달 첫 거래일」이라야 과거만 본다** (결정 C58)
        """
        # Given
        series = self._series()

        def run(frame: pd.DataFrame) -> pd.DataFrame:
            benchmark = _pick(_build(frame, config=_config(cost=PAID_COST), rp=2.0, parking=3.0), key)

            return pd.DataFrame({COL_DATE: benchmark.curve.index, COL_TOTAL_ASSETS: benchmark.curve.to_numpy()})

        # When / Then
        assert_stable_under_truncation(
            run, series, len(series) - 10, key_columns=[COL_DATE], value_column=COL_TOTAL_ASSETS
        )
