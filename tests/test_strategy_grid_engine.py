"""원달러 그리드 시뮬레이션 루프의 계약을 고정한다.

**자산곡선이 틀려도 그럴듯해 보인다.** 실현손익만 집계하면 그리드 곡선은 **구조적으로 항상
우상향한다** — 매도는 무조건 이익 실현이고 손실은 미실현으로 잔류하기 때문이다.
사양서 §8 이 "2009~2014 하락장에서도 실현 기준 곡선은 예쁘게 올라가지만 실제 계좌는 반토막"
이라고 적은 것이 이 사고이며, §15.3 은 이것을 Red Flag 두 개로 명시했다.

핵심 계약은 다섯 가지다.

- **회계 항등식이 매일 성립한다** — `총자산 == 원화현금 + Σ(슬롯 보유 단위 × 당일 종가)`
- **미실현 평가손익이 곡선에 들어간다** — 들고 있는 동안 환율이 내리면 총자산이 준다
- **총자산은 거래비용만큼만 줄어든다.** 비용률이 0이면 「전후 총자산이 같다」로 되돌아간다
- **중복 슬롯이 없고 현금이 음수가 되지 않는다** (사양서 §15.2 #1·#12)
- **재조정이 보유 슬롯을 건드리지 않는다** (§15.2 #7)
- **하단 이탈 B안은 사는 곳을 늘릴 뿐 판정식을 바꾸지 않는다** — 이탈이 없는 시세에서
  A안과 원 단위까지 같고, 이탈이 있어도 **매수와 매도가 같은 날 함께 일어나지 않는다** (결정 C86)
"""

from collections.abc import Callable, Sequence

import pandas as pd
import pytest

from verify_lab.common_constants import COL_DATE, COL_VALUE
from verify_lab.strategy.grid.constants import (
    COL_ACCRUED_INTEREST,
    COL_ACTIVE_LEVELS,
    COL_BUY_AMOUNT,
    COL_BUY_COUNT,
    COL_CAPPED_LEVELS,
    COL_CASH,
    COL_CLOSE_RATE,
    COL_COST,
    COL_EXTENDED_LEVELS,
    COL_HELD_INVESTED,
    COL_HELD_SLOTS,
    COL_PARKING_INTEREST,
    COL_RP_INTEREST,
    COL_SELL_COUNT,
    COL_TAX_PAID,
    COL_TOTAL_ASSETS,
    COL_USD_VALUE,
    DEFAULT_ALLOCATION_SPREAD,
    DEFAULT_MIN_RANGE_WIDTH,
    DEFAULT_SLOT_CAP_RATIO,
    INITIAL_CAPITAL,
    LOWER_BREACH_EXTEND,
    LOWER_BREACH_HOLD,
)
from verify_lab.strategy.grid.engine import GridConfig, run_grid
from verify_lab.strategy.grid.interest import InterestConfig, RateSeries
from verify_lab.strategy.grid.lattice import level_price
from verify_lab.strategy.grid.paths.base import CostConfig
from verify_lab.strategy.grid.paths.exchange import ExchangePath
from verify_lab.strategy.grid.price_range import build_daily_ranges

# 손계산이 쉽도록 익절폭을 크게 잡는다. 레벨이 적어 체결을 눈으로 따라갈 수 있다
HAND_GROWTH = 0.05

# 워밍업 12개월 + 매매 구간
WARMUP_MONTHS = 12
TRADING_START = pd.Timestamp("2020-01-01")

# 금액 비교 허용오차
AMOUNT_TOLERANCE = 0.01

# 비용이 없는 설정. 이 조건에서는 G2 의 「매수 전후 총자산이 같다」가 그대로 성립한다
FREE_COST = CostConfig(exchange_spread_rate=0.0, slippage_rate=0.0, brokerage_rate=0.0)

# 확정된 기본 비용 (결정 C35). 편도 합계 0.18%, 왕복 0.36%
PAID_COST = CostConfig(exchange_spread_rate=0.0008, slippage_rate=0.0010, brokerage_rate=0.0)

# 이자가 없는 설정. 하한이 0이면 금리 0을 그대로 통과시킨다
FREE_INTEREST = InterestConfig(rp_floor_rate=0.0, parking_floor_rate=0.0)


def _config(
    *,
    cost: CostConfig | None = None,
    interest: InterestConfig | None = None,
    **overrides: float | int,
) -> GridConfig:
    """손계산용 기본 설정. 비용도 이자도 넘기지 않으면 **둘 다 없음**이라 회계가 단순해진다."""
    values: dict[str, float | int] = {
        "lookback_years": 1,
        "growth_rate": HAND_GROWTH,
        "min_range_width": DEFAULT_MIN_RANGE_WIDTH,
        "allocation_spread": DEFAULT_ALLOCATION_SPREAD,
        "slot_cap_ratio": DEFAULT_SLOT_CAP_RATIO,
        "initial_capital": INITIAL_CAPITAL,
    }
    values.update(overrides)

    return GridConfig(  # type: ignore[arg-type]
        **values,
        cost=cost or FREE_COST,
        interest=interest or FREE_INTEREST,
    )


def _rates(ranges: pd.DataFrame, *, rp: float = 0.0, parking: float = 0.0) -> RateSeries:
    """범위표의 거래일에 맞춘 **고정 금리** 계열. 0이면 이자가 발생하지 않는다.

    무위험 수익률은 엔진이 쓰지 않으므로(지표 계층의 입력이다) 파킹과 같은 값을 둔다.
    """
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


def _across_month() -> pd.DataFrame:
    """달을 넘길 만큼 긴 **상승** 경로. 계속 오르므로 하향 돌파가 없어 매수가 일어나지 않는다.

    2020-01-01 부터의 영업일 24개라 1월(23영업일)을 넘어 2월 첫 거래일까지 간다.
    """
    return _daily_series(1200.0, [1200.0 + index for index in range(24)])


def _run(
    series: pd.DataFrame,
    *,
    config: GridConfig | None = None,
    rp: float = 0.0,
    parking: float = 0.0,
    lower_breach: str = LOWER_BREACH_HOLD,
    sell_enabled: bool = True,
):
    """손계산용 기본 인자로 엔진을 돌린다. 금리는 기본이 0이라 이자가 붙지 않는다."""
    settings = config or _config()
    ranges = build_daily_ranges(
        series,
        start_date=TRADING_START,
        lookback_years=settings.lookback_years,
        min_range_width=settings.min_range_width,
        lower_breach=lower_breach,
    )

    return run_grid(
        series,
        ranges,
        config=settings,
        rates=_rates(ranges, rp=rp, parking=parking),
        path=ExchangePath(settings.cost),
        sell_enabled=sell_enabled,
    )


class TestAccountingIdentity:
    """회계 항등식을 고정한다."""

    def test_총자산이_현금과_달러평가액의_합이다(self) -> None:
        """
        목적: 매일 `총자산 == 원화현금 + Σ(슬롯 달러 × 당일 종가)` 를 고정한다

        Given: 오르내리는 경로
        When: 엔진을 돌린다
        Then: 모든 거래일에서 항등식이 성립한다
        """
        # Given
        series = _daily_series(1000.0, [1000.0, 950.0, 900.0, 950.0, 1000.0, 1050.0, 1000.0, 940.0])

        # When
        actual = _run(series)

        # Then
        total = actual.daily[COL_CASH] + actual.daily[COL_USD_VALUE]
        assert actual.daily[COL_TOTAL_ASSETS].tolist() == pytest.approx(total.tolist(), abs=AMOUNT_TOLERANCE)

    def test_첫날_총자산이_초기_자본금이다(self) -> None:
        """
        목적: 시작 상태를 고정한다 — 슬롯 0, 현금 100% (사양서 §11.4)

        Given: 첫날에 하향 돌파가 없는 경로
        When: 엔진을 돌린다
        Then: 첫날 총자산이 초기 자본금이고 현금이 전액이다
        """
        # Given
        series = _daily_series(1000.0, [1000.0, 1000.0, 1000.0])

        # When
        actual = _run(series)

        # Then
        assert actual.daily[COL_TOTAL_ASSETS].iloc[0] == pytest.approx(INITIAL_CAPITAL, abs=AMOUNT_TOLERANCE)
        assert actual.daily[COL_CASH].iloc[0] == pytest.approx(INITIAL_CAPITAL, abs=AMOUNT_TOLERANCE)

    def test_현금이_음수가_되지_않는다(self) -> None:
        """
        목적: 무한자금 가정이 없음을 고정한다 (사양서 §15.2 #1)

        Given: 계속 떨어지기만 하는 경로 (매수만 일어난다)
        When: 엔진을 돌린다
        Then: 현금이 언제나 0 이상이다
        """
        # Given
        series = _daily_series(1200.0, [1200.0 * (0.97**step) for step in range(40)])

        # When
        actual = _run(series)

        # Then
        assert (actual.daily[COL_CASH] >= -AMOUNT_TOLERANCE).all()


class TestUnrealisedLoss:
    """미실현 평가손익 반영을 고정한다 (사양서 §8·§15.2 #2)."""

    def test_들고_있는_동안_내리면_총자산이_준다(self) -> None:
        """
        목적: 미실현 손실이 곡선에 실림을 고정한다

        Given: 한 번 사고 나서 계속 떨어지는 경로
        When: 엔진을 돌린다
        Then: 마지막 총자산이 초기 자본금보다 작다

        Note:
            실현손익만 집계하면 매도가 없으므로 총자산이 초기값 그대로 유지돼 이 테스트가 실패한다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1140.0, 1080.0, 1020.0, 960.0, 900.0])

        # When
        actual = _run(series)

        # Then
        assert actual.daily[COL_HELD_SLOTS].iloc[-1] > 0
        assert actual.daily[COL_TOTAL_ASSETS].iloc[-1] < INITIAL_CAPITAL - AMOUNT_TOLERANCE

    def test_자산곡선이_단조_증가가_아니다(self) -> None:
        """
        목적: 사양서 §15.3 의 Red Flag「자산곡선 단조 증가 → 실현손익만 집계」를 고정한다

        Given: 하락 구간이 들어간 경로
        When: 엔진을 돌린다
        Then: 총자산이 전일보다 내려간 날이 있다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1140.0, 1080.0, 1020.0, 1080.0, 1020.0, 960.0])

        # When
        actual = _run(series)

        # Then
        assert (actual.daily[COL_TOTAL_ASSETS].diff().dropna() < 0).any()

    def test_비용이_없으면_매수_전후_총자산이_같다(self) -> None:
        """
        목적: 결정 C42 를 고정한다 — 비용이 0이면 배분 기준 총자산과 곡선 값이 일치한다

        Given: 매수가 일어나는 경로와 비용 없는 설정
        When: 엔진을 돌린다
        Then: 매수가 있었던 날에도 항등식이 유지되고, 곡선 값이 배분에 쓴 총자산과 같다

        Note:
            **비용 도입이 기존 결과를 바꾸지 않았는지 보는 회귀 안전망이다.**
            비용률만 0으로 되돌리면 G2 의 계약이 그대로 성립해야 한다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1140.0, 1080.0, 1020.0])

        # When
        actual = _run(series)

        # Then
        traded = actual.daily[actual.daily[COL_BUY_COUNT] > 0]
        assert not traded.empty
        assert traded[COL_COST].tolist() == pytest.approx([0.0] * len(traded), abs=AMOUNT_TOLERANCE)
        assert traded[COL_TOTAL_ASSETS].tolist() == pytest.approx(
            (traded[COL_CASH] + traded[COL_USD_VALUE]).tolist(), abs=AMOUNT_TOLERANCE
        )


class TestCostAccounting:
    """거래비용이 총자산에 반영되는 방식을 고정한다."""

    def test_총자산은_비용만큼만_줄어든다(self) -> None:
        """
        목적: 「자산이 원화에서 달러로 바뀌는 것만으로는 총액이 변하지 않는다」를 고정한다

        Given: 매수가 일어나는 경로와 편도 0.18% 의 비용
        When: 엔진을 돌린다
        Then: 매수한 날의 총자산 감소가 그날 비용과 같다 — 환율이 그대로인 날로 잡아
              평가 변동이 섞이지 않게 한다

        Note:
            엔진이 매도·매수 두 지점에서 같은 검사를 하므로, 어긋나면 여기 오기 전에
            `RuntimeError` 로 먼저 걸린다. 이 테스트는 그 검사가 실제로 돌았음을 고정한다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1140.0, 1140.0])

        # When
        actual = _run(series, config=_config(cost=PAID_COST))

        # Then
        traded = actual.daily[actual.daily[COL_BUY_COUNT] > 0]
        assert not traded.empty
        assert (traded[COL_COST] > 0).all()

    def test_환율이_그대로면_비용만큼만_줄어든다(self) -> None:
        """
        목적: 비용이 실제로 곡선을 깎는 폭을 정확히 고정한다

        Given: 매수 후 환율이 그대로인 경로. 비용 없이 한 번, 비용을 물고 한 번 돌린다
        When: 마지막 총자산을 견준다
        Then: 차이가 그 실행의 비용 합계와 정확히 같다

        Note:
            **환율이 움직이면 이 등식은 성립하지 않는다.** 비용이 붙으면 같은 예산으로
            더 적은 달러를 사므로 이후 평가 변동의 크기 자체가 달라져 두 궤적이 갈라진다.
            비용만큼만 줄어드는 것은 **같은 날 안에서** 성립하는 계약이며, 엔진이 매도·매수
            두 지점에서 그것을 검사한다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1140.0, 1140.0, 1140.0])

        # When
        free = _run(series)
        paid = _run(series, config=_config(cost=PAID_COST))

        # Then
        gap = float(free.daily[COL_TOTAL_ASSETS].iloc[-1]) - float(paid.daily[COL_TOTAL_ASSETS].iloc[-1])
        assert gap > 0
        assert gap == pytest.approx(float(paid.daily[COL_COST].sum()), abs=AMOUNT_TOLERANCE)

    def test_평가에는_비용을_적용하지_않는다(self) -> None:
        """
        목적: 사양서 §8 을 고정한다 — 매일 청산 비용을 차감하면 미실현 손실이 과대계상된다

        Given: 사고 나서 환율이 그대로인 경로와 편도 0.18% 의 비용
        When: 엔진을 돌린다
        Then: 매수 다음 날의 총자산이 매수일과 같다. 평가에 비용이 걸렸다면 더 줄었을 것이다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1140.0, 1140.0, 1140.0])

        # When
        actual = _run(series, config=_config(cost=PAID_COST))

        # Then
        curve = actual.daily[actual.daily[COL_CLOSE_RATE] == 1140.0][COL_TOTAL_ASSETS].tolist()
        assert len(curve) >= 2
        assert curve[-1] == pytest.approx(curve[-2], abs=AMOUNT_TOLERANCE)

    def test_이탈_보너스에_비용이_섞이지_않는다(self) -> None:
        """
        목적: 이탈 보너스의 기준(비용 전 명목)을 체결 한 건 안에서 고정한다

        Given: 청산이 일어나는 경로와 편도 0.18% 의 비용
        When: 엔진을 돌린다
        Then: `실현손익 == 이탈 보너스 + g × 명목투입 − 매수비용 − 매도비용` 이 성립한다.
              비용은 보너스 밖에서 따로 빠진다

        Note:
            §6.4 의 정의는 「지정가 운용이었다면」과의 차이다. 지정가 운용도 같은 비용을 물므로
            보너스에 비용을 섞으면 §15.3 의 「총수익의 30% 초과」 판정이 다른 것을 재게 된다.
            비용률을 0으로 되돌리면 이 식이 G2 의 `실현손익 == 보너스 + g × 투입액` 이 된다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1080.0, 1200.0, 1320.0])

        # When
        actual = _run(series, config=_config(cost=PAID_COST))

        # Then
        trades = actual.trades
        assert not trades.empty
        assert (trades["buy_cost"] > 0).all()

        notional_invested = trades["invested"] - trades["buy_cost"]
        expected = trades["grid_excess"] + HAND_GROWTH * notional_invested - trades["buy_cost"] - trades["sell_cost"]
        assert trades["realized"].tolist() == pytest.approx(expected.tolist(), abs=AMOUNT_TOLERANCE)

    def test_투입_원화가_명목보다_크다(self) -> None:
        """
        목적: 결정 C41 을 고정한다 — 비용이 붙으면 `투입 원화 = 보유 단위 × 체결가` 가 깨진다

        Given: 매수가 일어나는 경로와 편도 0.18% 의 비용
        When: 엔진을 돌린다
        Then: 미청산 슬롯의 투입 원화가 명목보다 매수 비용만큼 크다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1140.0, 1140.0])

        # When
        actual = _run(series, config=_config(cost=PAID_COST))

        # Then
        assert actual.open_slots
        slot = actual.open_slots[0]
        assert slot.invested > slot.notional_invested
        assert slot.invested - slot.notional_invested == pytest.approx(slot.entry_cost, abs=AMOUNT_TOLERANCE)


class TestInterestAccrual:
    """이자 발생과 월말 정산의 계약을 고정한다."""

    def test_이자가_0이면_곡선이_그대로다(self) -> None:
        """
        목적: 이자 도입이 기존 결과를 바꾸지 않았음을 보는 회귀 안전망

        Given: 금리 0 인 경로
        When: 엔진을 돌린다
        Then: 이자·세금·미인출 이자가 전부 0 이다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1140.0, 1080.0, 1140.0])

        # When
        actual = _run(series)

        # Then
        assert actual.daily[COL_RP_INTEREST].sum() == pytest.approx(0.0, abs=AMOUNT_TOLERANCE)
        assert actual.daily[COL_PARKING_INTEREST].sum() == pytest.approx(0.0, abs=AMOUNT_TOLERANCE)
        assert actual.daily[COL_TAX_PAID].sum() == pytest.approx(0.0, abs=AMOUNT_TOLERANCE)
        assert actual.open_accrued_interest == pytest.approx(0.0, abs=AMOUNT_TOLERANCE)

    def test_첫날에는_파킹_이자가_없다(self) -> None:
        """
        목적: 백테스트 시작 이전 구간의 이자를 받지 않음을 고정한다

        Given: 파킹 금리가 있는 경로
        When: 엔진을 돌린다
        Then: 첫 거래일의 파킹 이자가 0 이고 둘째 날부터 붙는다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1210.0, 1220.0])

        # When
        actual = _run(series, parking=3.65)

        # Then
        assert actual.daily[COL_PARKING_INTEREST].iloc[0] == pytest.approx(0.0, abs=AMOUNT_TOLERANCE)
        assert actual.daily[COL_PARKING_INTEREST].iloc[1] > 0

    def test_파킹_이자는_전일_잔고에_달력일만큼_붙는다(self) -> None:
        """
        목적: 파킹 이자의 산식을 손계산으로 고정한다

        Given: 매수가 없어 현금이 1억 그대로인 경로와 파킹 금리 연 3.65%
        When: 엔진을 돌린다
        Then: 둘째 날 이자가 `1억 × 3.65% × 경과 달력일 ÷ 365` 다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1210.0, 1220.0])

        # When
        actual = _run(series, parking=3.65)

        # Then
        elapsed = (actual.daily[COL_DATE].iloc[1] - actual.daily[COL_DATE].iloc[0]).days
        expected = INITIAL_CAPITAL * 0.0365 * elapsed / 365
        assert actual.daily[COL_PARKING_INTEREST].iloc[1] == pytest.approx(expected, abs=AMOUNT_TOLERANCE)

    def test_매수일_당일에는_RP_이자가_없다(self) -> None:
        """
        목적: 사양서 §9.1 의 「RP 는 매수일 당일 이자 미지급」을 고정한다

        Given: 매수가 일어나는 경로와 RP 금리
        When: 엔진을 돌린다
        Then: 처음 매수한 날의 RP 이자가 0 이다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1140.0, 1140.0])

        # When
        actual = _run(series, rp=3.65)

        # Then
        first_buy = actual.daily[actual.daily[COL_BUY_COUNT] > 0].iloc[0]
        assert float(first_buy[COL_RP_INTEREST]) == pytest.approx(0.0, abs=AMOUNT_TOLERANCE)

    def test_RP_이자일수가_보유일수_빼기_1이다(self) -> None:
        """
        목적: 사양서 §9.1 의 이자일수 −1 을 **청산된 슬롯 전체**에 대해 고정한다

        Given: 사고파는 경로와 RP 금리 연 3.65%
        When: 엔진을 돌린다
        Then: RP 이자 합계가 `Σ(보유 달러 × 3.65% × (보유일수 − 1) ÷ 365 × 매도 환율)` 과 같다

        Note:
            매수·매도 당일이 빠지는 것은 이자를 매도·매수보다 **먼저** 처리하기 때문이다.
            매도일을 미리 알 필요가 없어 look-ahead 가 생기지 않는다.
            대조가 성립하려면 미청산 슬롯이 없어야 하므로 그것도 확인한다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1080.0, 1200.0, 1320.0, 1400.0])

        # When
        actual = _run(series, rp=3.65)

        # Then
        assert not actual.trades.empty
        assert not actual.open_slots

        # 명목투입(투입액 − 매수비용)을 매수 환율로 나누면 보유 달러가 나온다.
        # 이 경로는 하루 만에 사고팔지 않으므로 환율이 그대로인 구간에서만 이자가 붙는다
        units = (actual.trades["invested"] - actual.trades["buy_cost"]) / actual.trades["entry_price"]
        days = (actual.trades["hold_days"] - 1).clip(lower=0)
        expected = float((units * 0.0365 * days / 365 * actual.trades["exit_price"]).sum())
        assert float(actual.daily[COL_RP_INTEREST].sum()) == pytest.approx(expected, abs=AMOUNT_TOLERANCE)

    def test_미인출_이자가_총자산에_들어간다(self) -> None:
        """
        목적: 결정 C7 의 「일별 발생분을 총자산에 즉시 반영」을 고정한다

        Given: 한 달 안에서 끝나는 짧은 경로와 파킹 금리
        When: 엔진을 돌린다
        Then: 마지막 총자산이 `현금 + 평가액 + 미인출 이자` 이고 미인출 이자가 0보다 크다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1210.0, 1220.0])

        # When
        actual = _run(series, parking=3.65)

        # Then
        last = actual.daily.iloc[-1]
        assert float(last[COL_ACCRUED_INTEREST]) > 0
        assert float(last[COL_TOTAL_ASSETS]) == pytest.approx(
            float(last[COL_CASH]) + float(last[COL_USD_VALUE]) + float(last[COL_ACCRUED_INTEREST]),
            abs=AMOUNT_TOLERANCE,
        )

    def test_원천징수는_달이_바뀐_첫_거래일에만_일어난다(self) -> None:
        """
        목적: 월말 정산의 시점을 고정한다

        Given: 달을 넘기는 경로와 파킹 금리
        When: 엔진을 돌린다
        Then: 원천징수가 일어난 날이 전부 달이 바뀐 첫 거래일이다

        Note:
            **「매월 마지막 거래일」로 잡으면 그 판정에 다음 행이 필요하다.** 시세를 월 중간에서
            자르면 마지막 날이 월말로 오판되어 look-ahead 감시 테스트가 깨진다
        """
        # Given
        series = _across_month()

        # When
        actual = _run(series, parking=3.65)

        # Then
        daily = actual.daily
        month_changed = daily[COL_DATE].dt.month != daily[COL_DATE].shift(1).dt.month
        settled = daily[COL_TAX_PAID] > 0
        assert settled.any()
        assert bool(month_changed[settled].all())

    def test_세금은_인출_직전_미인출_이자의_15_4퍼센트다(self) -> None:
        """
        목적: 원천징수의 과세 기준을 손계산으로 고정한다

        Given: 달을 넘기는 경로와 파킹 금리
        When: 엔진을 돌린다
        Then: 첫 정산일의 세금이 `(직전일 미인출 이자 + 당일 발생 이자) × 15.4%` 다
        """
        # Given
        series = _across_month()

        # When
        actual = _run(series, parking=3.65)

        # Then
        daily = actual.daily.reset_index(drop=True)
        position = int(daily.index[daily[COL_TAX_PAID] > 0][0])
        assert position > 0

        base = (
            float(daily[COL_ACCRUED_INTEREST].iloc[position - 1])
            + float(daily[COL_PARKING_INTEREST].iloc[position])
            + float(daily[COL_RP_INTEREST].iloc[position])
        )
        assert float(daily[COL_TAX_PAID].iloc[position]) == pytest.approx(base * 0.154, abs=AMOUNT_TOLERANCE)

    def test_파킹_이자만_있으면_정산에_환전_비용이_없다(self) -> None:
        """
        목적: 원화 이자는 환전을 거치지 않음을 고정한다

        Given: 계속 올라 매수가 없는 경로. 파킹 이자만 쌓인다
        When: 비용을 물고 엔진을 돌린다
        Then: 정산일의 거래비용이 0 이다 — 환전할 달러가 없다
        """
        # Given
        series = _across_month()

        # When
        actual = _run(series, config=_config(cost=PAID_COST), parking=3.65)

        # Then
        settled = actual.daily[actual.daily[COL_TAX_PAID] > 0]
        assert not settled.empty
        assert float(settled.iloc[0][COL_COST]) == pytest.approx(0.0, abs=AMOUNT_TOLERANCE)

    def test_이자가_붙으면_총자산이_늘어난다(self) -> None:
        """
        목적: 이자가 실제로 곡선을 밀어 올리는지 고정한다

        Given: 같은 경로를 이자 없이 한 번, 파킹 이자를 붙여 한 번 돌린다
        When: 마지막 총자산을 견준다
        Then: 이자를 붙인 쪽이 더 크다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1210.0, 1220.0, 1230.0])

        # When
        free = _run(series)
        paid = _run(series, parking=3.65)

        # Then
        assert float(paid.daily[COL_TOTAL_ASSETS].iloc[-1]) > float(free.daily[COL_TOTAL_ASSETS].iloc[-1])


class TestSlotInvariants:
    """보유 슬롯의 불변조건을 고정한다."""

    def test_중복_슬롯이_생기지_않는다(self) -> None:
        """
        목적: 사양서 §15.2 필수 검증 #12 를 전 기간에 걸쳐 고정한다

        Given: 같은 구간을 여러 번 오르내리는 경로
        When: 엔진을 돌린다
        Then: 어느 날에도 보유 슬롯 수가 활성 레벨 수를 넘지 않고, 체결 내역에
              같은 레벨이 겹치는 보유 기간으로 두 번 나오지 않는다
        """
        # Given
        path = [1200.0, 1140.0, 1200.0, 1140.0, 1200.0, 1140.0, 1200.0] * 3

        # When
        actual = _run(_daily_series(1200.0, path))

        # Then
        assert (actual.daily[COL_HELD_SLOTS] <= actual.daily[COL_ACTIVE_LEVELS]).all()
        for index, group in actual.trades.groupby("level_index"):
            ordered = group.sort_values("entry_date")
            assert (
                ordered["entry_date"].shift(-1).dropna() >= ordered["exit_date"].iloc[:-1]
            ).all(), f"레벨 {index} 의 보유 기간이 겹칩니다"

    def test_매도한_레벨은_다시_살_수_있다(self) -> None:
        """
        목적: 사양서 §6.5 의 「레벨 재활성화: 매도 즉시」를 고정한다

        Given: 같은 레벨을 두 번 오르내리는 경로
        When: 엔진을 돌린다
        Then: 같은 레벨의 체결이 두 번 이상 나온다
        """
        # Given
        path = [1200.0, 1130.0, 1220.0, 1130.0, 1220.0]

        # When
        actual = _run(_daily_series(1200.0, path))

        # Then
        assert not actual.trades.empty
        assert actual.trades["level_index"].duplicated().any()

    def test_재조정이_보유_슬롯을_건드리지_않는다(self) -> None:
        """
        목적: 사양서 §15.2 필수 검증 #7 을 고정한다

        Given: 달을 넘어가며 슬롯을 들고 있는 경로
        When: 엔진을 돌린다
        Then: 재조정일에 매도가 일어나지 않는다 — 강제 청산이 없다
        """
        # Given
        days = pd.bdate_range(TRADING_START, periods=45)
        path = [1200.0] + [1200.0 * (0.995**step) for step in range(1, len(days))]
        series = pd.concat(
            [_series([1200.0] * WARMUP_MONTHS), pd.DataFrame({COL_DATE: days, COL_VALUE: path})],
            ignore_index=True,
        )

        # When
        actual = _run(series)

        # Then — 내리기만 하는 경로라 매도가 한 건도 없어야 한다
        assert actual.daily[COL_SELL_COUNT].sum() == 0
        assert actual.daily[COL_HELD_SLOTS].iloc[-1] > 0


class TestLatticeStaysFixed:
    """격자 고정을 실행 결과로 고정한다 (사양서 §15.2 #11)."""

    def test_같은_레벨의_목표가가_언제나_같다(self) -> None:
        """
        목적: 재조정을 여러 번 지나도 레벨 가격표가 바뀌지 않음을 고정한다

        Given: 여러 달에 걸쳐 오르내리는 경로
        When: 엔진을 돌린다
        Then: 같은 레벨의 목표가가 체결마다 동일하다
        """
        # Given
        path = ([1200.0, 1130.0, 1220.0, 1130.0, 1220.0] * 12)[:55]
        days = pd.bdate_range(TRADING_START, periods=len(path))
        series = pd.concat(
            [_series([1200.0] * WARMUP_MONTHS), pd.DataFrame({COL_DATE: days, COL_VALUE: path})],
            ignore_index=True,
        )

        # When
        actual = _run(series)

        # Then
        assert not actual.trades.empty
        for index, group in actual.trades.groupby("level_index"):
            assert group["target_price"].nunique() == 1
            expected = level_price(int(index) + 1, growth_rate=HAND_GROWTH)
            assert group["target_price"].iloc[0] == pytest.approx(expected, abs=AMOUNT_TOLERANCE)


class TestLookAhead:
    """미래를 참조하지 않음을 고정한다."""

    def test_뒤를_잘라도_겹치는_날의_총자산이_같다(self, assert_stable_under_truncation: Callable[..., None]) -> None:
        """
        목적: look-ahead 감시 계약을 건다 (`tests/CLAUDE.md` 필수 테스트)

        Given: 오르내리는 긴 경로
        When: 뒤를 잘라낸 시세와 전체 시세로 각각 돌린다
        Then: 겹치는 날의 총자산이 같다

        Note:
            상태 구동 매매법이라도 **상태는 판정일까지의 체결로만 쌓인다**.
            범위 계산이나 체결 판정이 미래를 보면 여기서 걸린다
        """
        # Given
        path = ([1200.0, 1150.0, 1100.0, 1160.0, 1220.0, 1140.0] * 10)[:55]
        days = pd.bdate_range(TRADING_START, periods=len(path))
        series = pd.concat(
            [_series([1200.0] * WARMUP_MONTHS), pd.DataFrame({COL_DATE: days, COL_VALUE: path})],
            ignore_index=True,
        )

        def run(frame: pd.DataFrame) -> pd.DataFrame:
            return _run(frame).daily[[COL_DATE, COL_TOTAL_ASSETS]]

        # When / Then
        assert_stable_under_truncation(
            run, series, len(series) - 10, key_columns=[COL_DATE], value_column=COL_TOTAL_ASSETS
        )


class TestEdgeCases:
    """경계 조건을 고정한다."""

    def test_계속_오르기만_하면_매수가_없다(self) -> None:
        """
        목적: 엣지 케이스 — 하향 돌파가 한 번도 없는 경로를 고정한다

        Given: 계속 오르기만 하는 경로
        When: 엔진을 돌린다
        Then: 체결이 없고 총자산이 초기 자본금 그대로다
        """
        # Given
        series = _daily_series(1000.0, [1000.0 * (1.01**step) for step in range(10)])

        # When
        actual = _run(series)

        # Then
        assert actual.daily[COL_BUY_COUNT].sum() == 0
        assert actual.trades.empty
        assert actual.daily[COL_TOTAL_ASSETS].tolist() == pytest.approx(
            [INITIAL_CAPITAL] * len(actual.daily), abs=AMOUNT_TOLERANCE
        )

    def test_거래일이_이틀이어도_돈다(self) -> None:
        """
        목적: 엣지 케이스 — 최소 길이 입력을 고정한다

        Given: 매매 구간이 이틀뿐인 시계열
        When: 엔진을 돌린다
        Then: 예외 없이 두 줄짜리 곡선이 나온다
        """
        # Given
        series = _daily_series(1000.0, [1000.0, 950.0])

        # When
        actual = _run(series)

        # Then
        assert len(actual.daily) == 2

    def test_미청산_슬롯을_요약에_남긴다(self) -> None:
        """
        목적: 결정 G4 를 고정한다 — 종료 시점에 남은 슬롯을 강제 청산하지 않는다

        Given: 사고 나서 회복하지 못하고 끝나는 경로
        When: 엔진을 돌린다
        Then: 미청산 슬롯이 남아 있고 그 평가손익이 요약에 담긴다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1140.0, 1080.0, 1020.0])

        # When
        actual = _run(series)

        # Then
        assert actual.open_slots
        assert actual.open_unrealised < 0

    def test_초기_자본금이_양수가_아니면_거부한다(self) -> None:
        """
        목적: 설정의 유효 범위를 고정한다

        Given: 0 이하인 초기 자본금
        When: 설정을 만든다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="초기 자본금"):
            _config(initial_capital=0.0)

    def test_범위표와_시세의_거래일이_어긋나면_거부한다(self) -> None:
        """
        목적: 두 입력의 정합을 조용히 통과시키지 않음을 고정한다

        Given: 범위표에 시세에 없는 날짜가 섞여 있다
        When: 엔진을 돌린다
        Then: ValueError

        Note:
            어긋난 채로 돌면 그날의 범위가 다른 날 것으로 적용되는데 **예외가 나지 않는다**
        """
        # Given
        series = _daily_series(1000.0, [1000.0, 950.0, 900.0])
        config = _config()
        ranges = build_daily_ranges(
            series, start_date=TRADING_START, lookback_years=1, min_range_width=DEFAULT_MIN_RANGE_WIDTH
        )
        broken = ranges.copy()
        broken.loc[broken.index[0], COL_DATE] = pd.Timestamp("1999-01-01")

        # When / Then
        with pytest.raises(ValueError, match="거래일"):
            run_grid(series, broken, config=config, rates=_rates(broken), path=ExchangePath(config.cost))


class TestSlotCapPassthrough:
    """조각 3 의 상한이 엔진에서도 작동함을 고정한다."""

    def test_상한이_걸리면_현금이_남는다(self) -> None:
        """
        목적: 상한 발동 시 잉여가 현금으로 남음을 고정한다 (결정 C32)

        Given: 활성 레벨이 적어 슬롯이 상한에 걸리는 설정
        When: 계속 떨어지는 경로로 돌린다
        Then: 모든 레벨을 다 사고도 현금이 남는다
        """
        # Given — 익절폭을 크게 잡아 레벨 수를 줄인다
        config = _config(growth_rate=0.05, slot_cap_ratio=0.06)
        series = _daily_series(1200.0, [1200.0 * (0.97**step) for step in range(20)])

        # When
        actual = _run(series, config=config)

        # Then
        assert actual.daily[COL_CASH].iloc[-1] > AMOUNT_TOLERANCE


class TestLowerBreachExtension:
    """하단 이탈 B안(격자 아래 연장)의 계약을 고정한다 (사양서 §7).

    B안은 **설계 대안이지 파라미터가 아니다.** 그래서 고정할 것은 "성적이 좋아지는가"가 아니라
    **"A안을 건드리지 않는가"** 와 **"판정식이 그대로인가"** 다.

    워밍업 1,200원 12개월이면 최소폭 강제로 범위가 `1,095.45 ~ 1,314.53` 이 된다.
    익절폭 5% 격자에서 활성 레벨은 k=2(1,102.5) ~ k=5(1,276.3) 네 개이고,
    **종가 1,050원(k=1 의 레벨가)으로 떨어지면 그 아래로 한 칸이 더 켜진다.**
    """

    # 이탈 없이 오르내리는 경로. 두 값 모두 범위 하단 1,095.45 위에 있다
    CALM_PATH = [1200.0, 1130.0, 1220.0, 1130.0, 1220.0, 1130.0, 1220.0]

    # 하단(1,095.45)을 뚫고 k=1 의 레벨가(1,050)까지 내려가는 경로
    BREACH_PATH = [1200.0, 1050.0, 1050.0, 1050.0]

    def test_이탈이_없으면_A안과_원_단위까지_같다(self) -> None:
        """
        목적: B안 도입이 **A안의 결과를 흔들지 않음**을 고정한다 (회귀 안전망)

        Given: 범위 하단을 한 번도 뚫지 않는 경로
        When: A안과 B안으로 각각 돌린다
        Then: 일별 총자산과 체결 건수가 정확히 같다

        Note:
            착수 전 실측에서 **ETF 기간(2017~)의 이탈일이 0일**이었다.
            이 계약이 깨지면 261240·261250 성적이 조용히 달라진다
        """
        # Given
        series = _daily_series(1200.0, self.CALM_PATH)

        # When
        hold = _run(series, lower_breach=LOWER_BREACH_HOLD)
        extend = _run(series, lower_breach=LOWER_BREACH_EXTEND)

        # Then
        assert extend.daily[COL_TOTAL_ASSETS].tolist() == pytest.approx(
            hold.daily[COL_TOTAL_ASSETS].tolist(), abs=AMOUNT_TOLERANCE
        )
        assert len(extend.trades) == len(hold.trades)
        assert extend.daily[COL_EXTENDED_LEVELS].sum() == 0

    def test_이탈하면_당일_종가를_감싸는_레벨까지_켜진다(self) -> None:
        """
        목적: 연장의 경계를 실행 결과로 고정한다 (결정 C79)

        Given: 종가가 1,050원(k=1 의 레벨가)까지 떨어지는 경로
        When: A안과 B안으로 각각 돌린다
        Then: B안의 활성 레벨이 A안보다 정확히 하나 많고, 그 하나가 연장분으로 집계된다
        """
        # Given
        series = _daily_series(1200.0, self.BREACH_PATH)

        # When
        hold = _run(series, lower_breach=LOWER_BREACH_HOLD)
        extend = _run(series, lower_breach=LOWER_BREACH_EXTEND)

        # Then — 둘째 날이 이탈일이다
        assert int(hold.daily[COL_EXTENDED_LEVELS].iloc[1]) == 0
        assert int(extend.daily[COL_EXTENDED_LEVELS].iloc[1]) == 1
        assert int(extend.daily[COL_ACTIVE_LEVELS].iloc[1]) == int(hold.daily[COL_ACTIVE_LEVELS].iloc[1]) + 1

    def test_연장_레벨을_실제로_산다(self) -> None:
        """
        목적: 연장이 **체결로 이어짐**을 고정한다

        Given: 종가가 1,050원까지 떨어지는 경로
        When: A안과 B안으로 각각 돌린다
        Then: B안만 레벨 1 을 보유하며, 그 레벨의 매수 판정은 A안과 같은 하향 돌파다
        """
        # Given
        series = _daily_series(1200.0, self.BREACH_PATH)

        # When
        hold = _run(series, lower_breach=LOWER_BREACH_HOLD)
        extend = _run(series, lower_breach=LOWER_BREACH_EXTEND)

        # Then
        assert 1 not in [slot.level_index for slot in hold.open_slots]
        assert 1 in [slot.level_index for slot in extend.open_slots]
        assert int(extend.daily[COL_BUY_COUNT].iloc[1]) == int(hold.daily[COL_BUY_COUNT].iloc[1]) + 1

    def test_연장_레벨의_목표가가_바로_위_칸이다(self) -> None:
        """
        목적: 연장 레벨도 **격자 고정 목표가**를 따름을 고정한다 (사양서 §3.3·결정 C40)

        Given: 연장 레벨 1 을 사고 그 위로 회복하는 경로
        When: B안으로 돌린다
        Then: 레벨 1 의 매도 목표가가 `레벨_2` 다
        """
        # Given — 1,050 에서 사고 1,102.5(레벨 2) 위로 올라가 팔린다
        series = _daily_series(1200.0, [1200.0, 1050.0, 1110.0])

        # When
        actual = _run(series, lower_breach=LOWER_BREACH_EXTEND)

        # Then
        sold = actual.trades[actual.trades["level_index"] == 1]
        assert not sold.empty
        assert sold["target_price"].iloc[0] == pytest.approx(
            level_price(2, growth_rate=HAND_GROWTH), abs=AMOUNT_TOLERANCE
        )

    def test_연장이_꺼져도_보유_슬롯이_남는다(self) -> None:
        """
        목적: 재조정이 **미체결 레벨만** 토글함을 고정한다 (사양서 §4.3·§4.4)

        Given: 한 달 안에서 연장 레벨을 사고, 다음 달에 이탈이 사라진다
        When: B안으로 돌린다
        Then: 다음 달에 연장 레벨 수가 0으로 돌아가지만 레벨 1 은 계속 보유 중이다

        Note:
            연장분이 꺼진다는 것은 **거기서 더 사지 않는다**는 뜻이지
            들고 있던 것을 판다는 뜻이 아니다. 재조정으로 손익이 확정되면
            사양서 §4.3 이 경계한 "인공 수익원"이 생긴다
        """
        # Given — 1월에 이탈해 레벨 1 을 사고, 2월 내내 1,100원(레벨 1 과 2 사이)에 머문다
        days = pd.bdate_range(TRADING_START, periods=30)
        path = [1200.0, 1050.0] + [1100.0] * (len(days) - 2)
        series = pd.concat(
            [_series([1200.0] * WARMUP_MONTHS), pd.DataFrame({COL_DATE: days, COL_VALUE: path})],
            ignore_index=True,
        )

        # When
        actual = _run(series, lower_breach=LOWER_BREACH_EXTEND)

        # Then
        assert int(actual.daily[COL_EXTENDED_LEVELS].iloc[-1]) == 0
        assert 1 in [slot.level_index for slot in actual.open_slots]

    def test_연장이_기존_레벨의_슬롯을_줄인다(self) -> None:
        """
        목적: 사양서 §7 의 「매일 재정규화로 자동 축소 배분」을 실행 결과로 고정한다

        Given: 이탈일에 여러 레벨이 함께 체결되는 경로. **슬롯 상한을 풀어 둔다** —
               손계산용 익절폭 5% 는 활성 레벨이 네댓 개뿐이라 기본 상한 8% 가 전부 걸리고,
               상한이 걸리면 재정규화가 슬롯이 아니라 잉여에만 나타난다
        When: A안과 B안으로 각각 돌린다
        Then: 두 안 모두 산 레벨의 투입액이 B안에서 더 작다

        Note:
            분모가 활성 레벨 전체(결정 C4)라 연장이 **기존 레벨의 슬롯까지 줄인다.**
            B안의 「낮은 평균단가」와 이 축소가 서로 반대 방향으로 작용하므로
            손익계산서를 둘로 나눠 봐야 한다
        """
        # Given
        series = _daily_series(1200.0, self.BREACH_PATH)
        config = _config(slot_cap_ratio=1.0)

        # When
        hold = _run(series, config=config, lower_breach=LOWER_BREACH_HOLD)
        extend = _run(series, config=config, lower_breach=LOWER_BREACH_EXTEND)

        # Then
        held_by_level = {slot.level_index: slot.invested for slot in hold.open_slots}
        extended_by_level = {slot.level_index: slot.invested for slot in extend.open_slots}
        shared = sorted(set(held_by_level) & set(extended_by_level))
        assert shared, "두 안이 함께 산 레벨이 없어 비교가 성립하지 않습니다"
        for index in shared:
            assert extended_by_level[index] < held_by_level[index]

    def test_보유_투입액이_곡선에_실린다(self) -> None:
        """
        목적: 사양서 §7 의 「소진 시점 평가손실률」을 낼 재료가 있음을 고정한다

        Given: 이탈해 여러 슬롯을 보유하게 되는 경로
        When: B안으로 돌린다
        Then: 마지막 날의 보유 투입액이 미청산 슬롯 투입액 합계와 같다
        """
        # Given
        series = _daily_series(1200.0, self.BREACH_PATH)

        # When
        actual = _run(series, lower_breach=LOWER_BREACH_EXTEND)

        # Then
        assert float(actual.daily[COL_HELD_INVESTED].iloc[-1]) == pytest.approx(
            actual.open_invested, abs=AMOUNT_TOLERANCE
        )

    def test_매수와_매도가_같은_날_함께_일어나지_않는다(self) -> None:
        """
        목적: **결정 C39 가 B안에서도 성립함**을 고정한다 (결정 C86)

        Given: 하단을 여러 번 뚫고 되돌아오는 긴 경로
        When: B안으로 돌린다
        Then: 매수와 매도가 함께 난 거래일이 하나도 없다

        Note:
            증명 전제가 살아 있다 — 연장으로 켜진 레벨도 **하향 돌파로만** 사므로
            매수는 여전히 종가 하락을 함의하고, 격자가 영구 고정이라 매도 조건도 그대로다.
            여기서 걸리면 하루 안의 처리 순서(결정 C38)가 그때부터 결과를 바꾸기 시작한다
        """
        # Given
        path = ([1200.0, 1120.0, 1040.0, 1000.0, 1080.0, 1160.0, 1240.0] * 9)[:60]
        days = pd.bdate_range(TRADING_START, periods=len(path))
        series = pd.concat(
            [_series([1200.0] * WARMUP_MONTHS), pd.DataFrame({COL_DATE: days, COL_VALUE: path})],
            ignore_index=True,
        )

        # When
        actual = _run(series, config=_config(cost=PAID_COST), lower_breach=LOWER_BREACH_EXTEND)

        # Then — 연장이 실제로 발동한 실행이어야 계약을 검사한 것이 된다
        assert actual.daily[COL_EXTENDED_LEVELS].sum() > 0
        both = (actual.daily[COL_BUY_COUNT] > 0) & (actual.daily[COL_SELL_COUNT] > 0)
        assert not both.any(), f"매수와 매도가 함께 난 거래일: {actual.daily.loc[both, COL_DATE].tolist()}"

    def test_뒤를_잘라도_겹치는_날의_총자산이_같다(self, assert_stable_under_truncation: Callable[..., None]) -> None:
        """
        목적: B안에도 look-ahead 감시 계약을 건다 (`tests/CLAUDE.md` 필수 테스트)

        Given: 이탈이 들어 있는 긴 경로
        When: 뒤를 잘라낸 시세와 전체 시세로 각각 B안을 돌린다
        Then: 겹치는 날의 총자산이 같다

        Note:
            연장 하단은 **직전 재조정 이후의 누적 최저 종가**다. 그 달 전체에서 최저를 구하면
            이탈 이전 날의 격자가 이미 늘어나 있어 여기서 걸린다
        """
        # Given
        path = ([1200.0, 1120.0, 1040.0, 1000.0, 1080.0, 1160.0, 1240.0] * 9)[:60]
        days = pd.bdate_range(TRADING_START, periods=len(path))
        series = pd.concat(
            [_series([1200.0] * WARMUP_MONTHS), pd.DataFrame({COL_DATE: days, COL_VALUE: path})],
            ignore_index=True,
        )

        def run(frame: pd.DataFrame) -> pd.DataFrame:
            return _run(frame, lower_breach=LOWER_BREACH_EXTEND).daily[[COL_DATE, COL_TOTAL_ASSETS]]

        # When / Then
        assert_stable_under_truncation(
            run, series, len(series) - 10, key_columns=[COL_DATE], value_column=COL_TOTAL_ASSETS
        )


class TestMetricColumns:
    """사양서 §13.2 가 요구하는 재료를 곡선에 남김을 고정한다.

    **지표를 위해 판정을 바꾸지 않는다.** 두 컬럼은 이미 일어난 일을 적을 뿐이며,
    총자산과 체결은 그대로여야 한다.
    """

    def test_매수_투입액이_그날_실제_지출과_같다(self) -> None:
        """
        목적: 「일일 최대 투입 비율」(§13.2)의 재료를 고정한다

        Given: 하루에 여러 레벨이 함께 체결되는 급락 경로
        When: 엔진을 돌린다
        Then: 그날 매수 투입액이 그날 줄어든 현금과 같다

        Note:
            **배정된 예산이 아니라 실제로 나간 금액**이다. ETF 경로는 정수 주식 수라
            둘이 다르고, 예산으로 적으면 투입 비율이 실제보다 커 보인다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1050.0, 1050.0])

        # When
        actual = _run(series)

        # Then — 매수만 있고 매도가 없는 날이므로 현금 감소분이 곧 투입액이다
        daily = actual.daily
        spent = daily[COL_CASH].shift(1).iloc[1] - daily[COL_CASH].iloc[1]
        assert float(daily[COL_BUY_AMOUNT].iloc[1]) == pytest.approx(spent, abs=AMOUNT_TOLERANCE)
        assert float(daily[COL_BUY_AMOUNT].iloc[0]) == pytest.approx(0.0, abs=AMOUNT_TOLERANCE)

    def test_상한이_걸린_레벨_수를_남긴다(self) -> None:
        """
        목적: 사양서 §5.3 의 「상한 발동 횟수」(§13.2 필수 지표)를 고정한다

        Given: 활성 레벨이 적어 슬롯 상한 8% 가 전부 걸리는 손계산 설정
        When: 엔진을 돌린다
        Then: 상한 발동 레벨 수가 활성 레벨 수와 같다
        """
        # Given
        actual = _run(_across_month())

        # Then
        daily = actual.daily
        assert (daily[COL_CAPPED_LEVELS] == daily[COL_ACTIVE_LEVELS]).all()

    def test_상한이_안_걸리면_0이다(self) -> None:
        """
        목적: 엣지 케이스 — 상한을 풀면 발동이 사라짐을 고정한다

        Given: 슬롯 상한을 100% 로 둔 설정
        When: 엔진을 돌린다
        Then: 상한 발동 레벨 수가 언제나 0 이다
        """
        # When
        actual = _run(_across_month(), config=_config(slot_cap_ratio=1.0))

        # Then
        assert actual.daily[COL_CAPPED_LEVELS].sum() == 0

    def test_컬럼_추가가_총자산을_바꾸지_않는다(self) -> None:
        """
        목적: 지표용 컬럼이 **판정과 회계에 영향을 주지 않음**을 고정한다

        Given: 사고파는 경로
        When: 엔진을 돌린다
        Then: 매수가 실제로 일어났는데도 회계 항등식이 그대로 성립한다

        Note:
            매수는 원화를 달러로 바꾸는 것이라 **투입액이 총자산에서 사라지지 않는다.**
            총자산 자체는 환율이 움직이면 미실현 평가손익 때문에 변하므로,
            고정할 것은 「투입액만큼 줄었는가」가 아니라 **「현금과 평가액의 합인가」** 다
        """
        # Given
        series = _daily_series(1200.0, [1200.0, 1130.0, 1220.0, 1130.0])

        # When
        actual = _run(series)

        # Then
        daily = actual.daily
        assert daily[COL_BUY_AMOUNT].sum() > 0
        total = daily[COL_CASH] + daily[COL_USD_VALUE]
        assert daily[COL_TOTAL_ASSETS].tolist() == pytest.approx(total.tolist(), abs=AMOUNT_TOLERANCE)


class TestSellSwitch:
    """매도를 끄는 인자의 계약을 고정한다 (사양서 §13.3 「분할매수 후 보유」).

    **매수 규칙이 같아야 익절 로직만 분리된다** (결정 C11). 그래서 벤치마크를 별도 루프로
    다시 쓰지 않고 **엔진의 매도 한 단계만 끈다** — 매수·배분·판정이 같은 코드라는 사실이
    구조로 보장돼야 두 곡선의 차이를 익절 로직의 기여로 읽을 수 있다.
    """

    # 사고팔기가 모두 일어나는 경로. 내려가서 사고 올라와서 파는 구간이 반복된다
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

    def test_기본값은_매도를_한다(self) -> None:
        """
        목적: 새 인자의 기본값이 **기존 동작**임을 고정한다 (회귀 안전망)

        Given: 사고파는 경로
        When: 인자를 넘기지 않은 실행과 매도를 켠 실행을 각각 돌린다
        Then: 두 곡선이 원 단위까지 같다
        """
        # Given
        series = self._series_with_round_trips()

        # When
        default = _run(series, config=_config(cost=PAID_COST))
        explicit = _run(series, config=_config(cost=PAID_COST), sell_enabled=True)

        # Then
        assert default.daily[COL_TOTAL_ASSETS].tolist() == pytest.approx(
            explicit.daily[COL_TOTAL_ASSETS].tolist(), abs=AMOUNT_TOLERANCE
        )
        assert len(default.trades) == len(explicit.trades)

    def test_매도를_끄면_체결표가_비고_매도가_0건이다(self) -> None:
        """
        목적: 「분할매수 후 보유」의 정의를 고정한다 — 사되 팔지 않는다

        Given: 매도가 실제로 일어나는 경로
        When: 매도를 끄고 돌린다
        Then: 매도 체결이 0건이고 청산된 체결표가 비어 있다
        """
        # Given
        series = self._series_with_round_trips()

        # When
        selling = _run(series, config=_config(cost=PAID_COST))
        holding = _run(series, config=_config(cost=PAID_COST), sell_enabled=False)

        # Then — 매도가 실제로 나는 경로여야 계약을 검사한 것이 된다
        assert selling.daily[COL_SELL_COUNT].sum() > 0
        assert holding.daily[COL_SELL_COUNT].sum() == 0
        assert holding.trades.empty

    def test_매도를_꺼도_매수는_같은_날_같은_레벨에서_시작한다(self) -> None:
        """
        목적: **매수 규칙이 같음**을 고정한다 (결정 C11)

        Given: 사고파는 경로
        When: 매도를 켠 실행과 끈 실행을 각각 돌린다
        Then: 첫 매수가 같은 날 같은 건수로 일어난다

        Note:
            그 뒤로는 갈라지는 것이 정상이다 — 팔지 않으면 그 레벨을 다시 살 수 없고
            현금도 줄어든다. **갈라지는 원인이 익절 로직 하나**라는 것이 이 벤치마크의 전제다
        """
        # Given
        series = self._series_with_round_trips()

        # When
        selling = _run(series, config=_config(cost=PAID_COST))
        holding = _run(series, config=_config(cost=PAID_COST), sell_enabled=False)

        # Then
        first_selling = selling.daily[selling.daily[COL_BUY_COUNT] > 0].iloc[0]
        first_holding = holding.daily[holding.daily[COL_BUY_COUNT] > 0].iloc[0]
        assert first_selling[COL_DATE] == first_holding[COL_DATE]
        assert first_selling[COL_BUY_COUNT] == first_holding[COL_BUY_COUNT]
        assert first_selling[COL_BUY_AMOUNT] == pytest.approx(first_holding[COL_BUY_AMOUNT], abs=AMOUNT_TOLERANCE)

    def test_매도를_꺼도_회계_항등식이_성립한다(self) -> None:
        """
        목적: 매도를 꺼도 회계가 깨지지 않음을 고정한다

        Given: 사고파는 경로에 비용을 붙인 설정
        When: 매도를 끄고 돌린다
        Then: 매일 `총자산 == 원화현금 + 달러 평가액` 이 성립한다
        """
        # Given
        series = self._series_with_round_trips()

        # When
        actual = _run(series, config=_config(cost=PAID_COST), sell_enabled=False)

        # Then
        total = actual.daily[COL_CASH] + actual.daily[COL_USD_VALUE]
        assert actual.daily[COL_TOTAL_ASSETS].tolist() == pytest.approx(total.tolist(), abs=AMOUNT_TOLERANCE)

    def test_매도를_끄면_보유_슬롯이_줄지_않는다(self) -> None:
        """
        목적: 슬롯이 쌓이기만 함을 고정한다 — 자금 소진이 빨라지는 원인이다

        Given: 사고파는 경로
        When: 매도를 끄고 돌린다
        Then: 보유 슬롯 수가 한 번도 줄지 않는다
        """
        # Given
        series = self._series_with_round_trips()

        # When
        actual = _run(series, config=_config(cost=PAID_COST), sell_enabled=False)

        # Then
        held = actual.daily[COL_HELD_SLOTS]
        assert (held.diff().dropna() >= 0).all()
        assert int(held.iloc[-1]) == len(actual.open_slots)
