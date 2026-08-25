"""사양서 §13.2 그리드 전용 지표의 계약을 고정한다.

**표준 지표만으로는 그리드의 실패 양상이 드러나지 않는다.** 사양서 §13.2 가 그렇게 적었고
실측이 그것을 확인했다 — 환전 2005~ 는 CAGR 2.75% 에 MDD −8.10% 로 멀쩡해 보이지만
**최장 보유가 15.8년**이고 **회전이 어느 해석으로도 기대 범위를 벗어난다.**

핵심 계약은 다섯 가지다.

- **회전은 전체와 슬롯당을 둘 다 낸다** (결정 C10). 사양서 §17.2 의 "연 5~15회" 가
  어느 단위를 전제했는지 불명확해 어느 쪽도 감추지 않는다
- **이탈 보너스 비중의 분모가 셋이다** — 총수익·실현손익·매매 기여분.
  이자가 분모에 들어오면 §15.3 의 30% 판정이 다른 것을 재게 된다
- **최장 보유기간에 미청산 슬롯을 포함한다** — "5년 물리는 슬롯"은 아직 안 팔린 것이 더 위험하다
- **계산 불가는 `None` 이다.** 체결이 0건일 때 평균 보유기간을 0 으로 돌려주면
  "하루 만에 판다"로 읽힌다
- **지표는 곡선과 체결표를 읽기만 한다.** 판정을 다시 하지 않는다
"""

import pandas as pd
import pytest

from verify_lab.common_constants import COL_DATE
from verify_lab.strategy.grid.engine import DAILY_COLUMNS, TRADE_COLUMNS, GridResult
from verify_lab.strategy.grid.execution import Slot
from verify_lab.strategy.grid.metrics import evaluate_grid, red_flags
from verify_lab.strategy.performance import evaluate_curve

# 비율 비교 허용오차
RATE_TOLERANCE = 1e-9

# 금액 비교 허용오차
AMOUNT_TOLERANCE = 0.01


def _daily(rows: list[dict[str, object]]) -> pd.DataFrame:
    """일별 곡선 원값을 만든다. 넘기지 않은 컬럼은 0 으로 채운다."""
    dates = pd.date_range("2020-01-01", periods=len(rows), freq="D")
    filled: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        base: dict[str, object] = {column: 0 for column in DAILY_COLUMNS}
        base[COL_DATE] = dates[index]
        base["Rebalanced"] = False
        base["CloseRate"] = 1000.0
        base["ExecPrice"] = 1000.0
        base["RangeLow"] = 900.0
        base["RangeHigh"] = 1100.0
        base["TotalAssets"] = 100_000_000.0
        base.update(row)
        filled.append(base)

    return pd.DataFrame(filled, columns=DAILY_COLUMNS)


def _trades(rows: list[dict[str, object]]) -> pd.DataFrame:
    """체결 내역 원값을 만든다."""
    filled: list[dict[str, object]] = []
    for row in rows:
        base: dict[str, object] = {column: 0 for column in TRADE_COLUMNS}
        base["entry_date"] = pd.Timestamp("2020-01-01")
        base["exit_date"] = pd.Timestamp("2020-01-02")
        base.update(row)
        filled.append(base)

    return pd.DataFrame(filled, columns=TRADE_COLUMNS)


def _result(
    daily: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    open_slots: tuple[Slot, ...] = (),
    open_unrealised: float = 0.0,
) -> GridResult:
    """지표 계산에 필요한 만큼만 채운 실행 결과."""
    return GridResult(
        daily=daily,
        trades=trades,
        open_slots=open_slots,
        open_invested=sum(slot.invested for slot in open_slots),
        open_value=0.0,
        open_unrealised=open_unrealised,
    )


def _slot(level_index: int, *, entry: str, invested: float = 1_000_000.0) -> Slot:
    """미청산 슬롯 하나."""
    return Slot(
        level_index=level_index,
        entry_date=pd.Timestamp(entry),
        entry_price=1000.0,
        entry_rate=1000.0,
        units=1000.0,
        invested=invested,
        entry_cost=0.0,
    )


class TestHoldingPeriod:
    """보유기간을 고정한다 (사양서 §13.2 — 최장 보유기간이 특히 중요하다)."""

    def test_평균과_중앙값을_병기한다(self) -> None:
        """
        목적: 루트 CLAUDE.md 「측정의 원칙」 4 를 지표 구성으로 고정한다

        Given: 보유일이 1·2·300 인 체결 세 건
        When: 지표를 낸다
        Then: 평균과 중앙값이 모두 나오고 크게 벌어져 있다

        Note:
            실측에서 **평균 262일 대 중앙값 20일**이었다. 두 값이 벌어지면
            소수 사건이 결과를 만들고 있다는 신호이므로 하나만 내면 안 된다
        """
        # Given
        trades = _trades([{"hold_days": 1}, {"hold_days": 2}, {"hold_days": 300}])

        # When
        actual = evaluate_grid(_result(_daily([{}, {}]), trades))

        # Then
        assert actual.hold_days_mean == pytest.approx(101.0, abs=RATE_TOLERANCE)
        assert actual.hold_days_median == pytest.approx(2.0, abs=RATE_TOLERANCE)

    def test_최장_보유기간에_미청산_슬롯을_포함한다(self) -> None:
        """
        목적: 결정 C93 을 고정한다

        Given: 청산된 체결의 최장이 100일인데, 마지막 거래일 기준 500일째 물려 있는 미청산 슬롯이 있다
        When: 지표를 낸다
        Then: 최장 보유기간이 500일이다

        Note:
            §13.2 는 "5년 물리는 슬롯이 나오면 전략 재설계" 를 요구한다.
            **아직 안 팔린 슬롯이 더 위험한데** 청산분만 세면 그것이 통째로 빠진다
        """
        # Given
        daily = _daily([{COL_DATE: pd.Timestamp("2021-05-16")}])
        trades = _trades([{"hold_days": 100}])
        slot = _slot(3, entry="2020-01-02")

        # When
        actual = evaluate_grid(_result(daily, trades, open_slots=(slot,)))

        # Then
        assert actual.hold_days_max == 500
        assert actual.open_hold_days_max == 500

    def test_체결이_없으면_보유기간이_None이다(self) -> None:
        """
        목적: 엣지 케이스 — 0 을 돌려주지 않음을 고정한다

        Given: 체결도 미청산도 없는 실행
        When: 지표를 낸다
        Then: 평균·중앙값·최장이 전부 None 이다

        Note:
            0 을 돌려주면 "하루 만에 판다"로 읽힌다 — 사실은 **한 번도 사지 않았다**
        """
        # When
        actual = evaluate_grid(_result(_daily([{}, {}]), _trades([])))

        # Then
        assert actual.hold_days_mean is None
        assert actual.hold_days_median is None
        assert actual.hold_days_max is None


class TestTurnover:
    """회전 횟수를 두 단위로 낸다 (결정 C10)."""

    def test_전체와_슬롯당을_둘_다_낸다(self) -> None:
        """
        목적: 사양서 §17.2 의 "연 5~15회" 가 어느 단위인지 불명확하므로 둘 다 산출함을 고정한다

        Given: 250 거래일(=1년) 동안 청산 20건, 활성 레벨이 평균 10개
        When: 지표를 낸다
        Then: 전체 회전이 연 20회, 슬롯당 회전이 연 2회다

        Note:
            실측에서 전체 **28.9회/년**(기대 초과)·슬롯당 **0.99회/년**(기대 미달)로
            **어느 해석도 §17.2 를 만족하지 않았다.** 하나만 내면 그 사실이 보이지 않는다
        """
        # Given — 251개 점이면 수익률 250개, 즉 1년이다
        daily = _daily([{"ActiveLevels": 10} for _ in range(251)])
        trades = _trades([{"hold_days": 1} for _ in range(20)])

        # When
        actual = evaluate_grid(_result(daily, trades))

        # Then
        assert actual.turnover_per_year == pytest.approx(20.0, abs=1e-6)
        assert actual.turnover_per_slot_per_year == pytest.approx(2.0, abs=1e-6)

    def test_활성_레벨이_0이면_슬롯당_회전이_None이다(self) -> None:
        """
        목적: 엣지 케이스 — 0 으로 나누는 상황을 고정한다

        Given: 활성 레벨이 한 번도 없었던 실행
        When: 지표를 낸다
        Then: 슬롯당 회전이 None 이고 전체 회전은 나온다
        """
        # Given
        daily = _daily([{"ActiveLevels": 0} for _ in range(251)])

        # When
        actual = evaluate_grid(_result(daily, _trades([{"hold_days": 1}])))

        # Then
        assert actual.turnover_per_slot_per_year is None
        assert actual.turnover_per_year is not None


class TestGridExcessDenominators:
    """이탈 보너스 비중의 분모를 셋으로 고정한다 (§15.3 판정과 해석이 다른 분모를 쓴다)."""

    def test_분모_셋을_모두_낸다(self) -> None:
        """
        목적: ROADMAP 계층 계약 「지표의 분모를 하나로 두지 않는다」를 고정한다

        Given: 총수익 1,000만 · 세후 이자 600만 · 실현손익 500만 · 이탈 보너스 300만
        When: 지표를 낸다
        Then: 총수익 대비 30% · 실현손익 대비 60% · 매매 기여분(1,000만−600만) 대비 75% 다

        Note:
            §15.3 의 판정 기준은 **총수익**인데, 이자가 분모에 들어오면 비중이 내려가
            **이자는 종가 체결과 무관한 수익원**이라는 사실이 그 통과 뒤에 숨는다.
            실측에서 총수익 대비 24.9% 였지만 매매 기여분 대비로는 69.1% 였다
        """
        # Given — 이자 700만 중 100만을 원천징수해 세후 600만이다
        daily = _daily(
            [
                {"TotalAssets": 100_000_000.0},
                {
                    "TotalAssets": 110_000_000.0,
                    "RpInterest": 3_000_000.0,
                    "ParkingInterest": 4_000_000.0,
                    "TaxPaid": 1_000_000.0,
                },
            ]
        )
        trades = _trades([{"hold_days": 1, "realized": 5_000_000.0, "grid_excess": 3_000_000.0}])

        # When
        actual = evaluate_grid(_result(daily, trades))

        # Then
        assert actual.grid_excess_total == pytest.approx(3_000_000.0, abs=AMOUNT_TOLERANCE)
        assert actual.grid_excess_share_of_total_return == pytest.approx(0.30, abs=RATE_TOLERANCE)
        assert actual.grid_excess_share_of_realized == pytest.approx(0.60, abs=RATE_TOLERANCE)
        assert actual.grid_excess_share_of_trading == pytest.approx(0.75, abs=RATE_TOLERANCE)

    def test_매매_기여분이_0이면_그_비중만_None이다(self) -> None:
        """
        목적: 엣지 케이스 — 분모 하나가 0 이어도 나머지는 살아 있음을 고정한다

        Given: 총수익이 전부 세후 이자인 실행
        When: 지표를 낸다
        Then: 매매 기여분 대비 비중만 None 이고 총수익 대비는 나온다
        """
        # Given
        daily = _daily(
            [
                {"TotalAssets": 100_000_000.0},
                {"TotalAssets": 110_000_000.0, "ParkingInterest": 10_000_000.0},
            ]
        )
        trades = _trades([{"hold_days": 1, "realized": 1.0, "grid_excess": 1.0}])

        # When
        actual = evaluate_grid(_result(daily, trades))

        # Then
        assert actual.grid_excess_share_of_trading is None
        assert actual.grid_excess_share_of_total_return is not None


class TestCapitalUsage:
    """자금 사용 지표를 고정한다."""

    def test_평균_투입률과_현금_잔류율을_낸다(self) -> None:
        """
        목적: 사양서 §13.2 의 「평균 투입률」·「현금 잔류율」을 고정한다

        Given: 총자산 1억 중 달러 평가액이 각각 2천만·4천만인 이틀
        When: 지표를 낸다
        Then: 평균 투입률이 30% 다
        """
        # Given
        daily = _daily(
            [
                {"TotalAssets": 100_000_000.0, "UsdValue": 20_000_000.0, "Cash": 80_000_000.0},
                {"TotalAssets": 100_000_000.0, "UsdValue": 40_000_000.0, "Cash": 60_000_000.0},
            ]
        )

        # When
        actual = evaluate_grid(_result(daily, _trades([])))

        # Then
        assert actual.deployment_mean == pytest.approx(0.30, abs=RATE_TOLERANCE)
        assert actual.cash_ratio_mean == pytest.approx(0.70, abs=RATE_TOLERANCE)

    def test_일일_최대_투입_비율과_그_날짜를_낸다(self) -> None:
        """
        목적: 사양서 §13.2 의 「일일 최대 투입 비율」을 고정한다 — 다중 체결로 하루에 몇 % 가 나가는가

        Given: 둘째 날에 총자산의 12% 를 매수에 쓴다
        When: 지표를 낸다
        Then: 최대 투입 비율이 12% 이고 날짜가 그날이다
        """
        # Given
        daily = _daily(
            [
                {"TotalAssets": 100_000_000.0, "BuyAmount": 5_000_000.0},
                {"TotalAssets": 100_000_000.0, "BuyAmount": 12_000_000.0},
            ]
        )

        # When
        actual = evaluate_grid(_result(daily, _trades([])))

        # Then
        assert actual.daily_deploy_max == pytest.approx(0.12, abs=RATE_TOLERANCE)
        assert actual.daily_deploy_max_date == daily[COL_DATE].iloc[1]

    def test_하루_3개_이상_체결_횟수를_센다(self) -> None:
        """
        목적: 사양서 §13.2 의 「하루 3개 이상 체결 횟수」를 고정한다

        Given: 매수가 2·3·5건인 사흘
        When: 지표를 낸다
        Then: 3개 이상인 날이 이틀이다
        """
        # Given
        daily = _daily([{"BuyCount": 2}, {"BuyCount": 3}, {"BuyCount": 5}])

        # When
        actual = evaluate_grid(_result(daily, _trades([])))

        # Then
        assert actual.multi_fill_days == 2

    def test_자금_소진율은_자금_부족일의_비중이다(self) -> None:
        """
        목적: 사양서 §13.2 의 「자금 소진율 분포」를 고정한다 — "총알 없음" 상태의 시간 비중

        Given: 나흘 중 하루만 자금 부족이 난다
        When: 지표를 낸다
        Then: 소진율이 25% 다
        """
        # Given
        daily = _daily([{}, {"BlockedCount": 2}, {}, {}])

        # When
        actual = evaluate_grid(_result(daily, _trades([])))

        # Then
        assert actual.blocked_day_ratio == pytest.approx(0.25, abs=RATE_TOLERANCE)
        assert actual.blocked_days == 1

    def test_최대_미실현_손실률과_그_날짜를_낸다(self) -> None:
        """
        목적: 사양서 §13.2 의 「최대 미실현 손실」을 고정한다 — 심리적 감내 한계

        Given: 투입 1억에 평가 9천만인 날이 있다
        When: 지표를 낸다
        Then: 최대 미실현 손실률이 −10% 이고 날짜가 그날이다

        Note:
            분모는 **보유분 투입액**이지 총자산이 아니다. 총자산으로 나누면
            원화현금이 섞여 **물린 정도가 투입률에 희석된다**
        """
        # Given
        daily = _daily(
            [
                {"HeldInvested": 100_000_000.0, "UsdValue": 98_000_000.0},
                {"HeldInvested": 100_000_000.0, "UsdValue": 90_000_000.0},
            ]
        )

        # When
        actual = evaluate_grid(_result(daily, _trades([])))

        # Then
        assert actual.unrealised_worst_rate == pytest.approx(-0.10, abs=RATE_TOLERANCE)
        assert actual.unrealised_worst_date == daily[COL_DATE].iloc[1]

    def test_보유가_한_번도_없으면_미실현_손실이_None이다(self) -> None:
        """
        목적: 엣지 케이스 — 0 으로 나누는 상황을 고정한다

        Given: 보유 투입액이 언제나 0 인 실행
        When: 지표를 낸다
        Then: 최대 미실현 손실률이 None 이다
        """
        # When
        actual = evaluate_grid(_result(_daily([{}, {}]), _trades([])))

        # Then
        assert actual.unrealised_worst_rate is None


class TestRangeAndBreach:
    """범위·하단 이탈 지표를 고정한다 (사양서 §4.1 월평균 방식의 대가)."""

    def test_하단_이탈_횟수와_기간과_최대_깊이를_낸다(self) -> None:
        """
        목적: 사양서 §13.2 의 「하단 이탈 횟수 / 기간 / 최대 깊이」를 고정한다

        Given: 하단 900원 아래로 이틀 연속, 하루 쉬고 다시 하루 내려간다
        When: 지표를 낸다
        Then: 이탈일 3일 · 연속 구간 2회 · 최대 깊이 −10% 다
        """
        # Given
        daily = _daily(
            [
                {"CloseRate": 950.0},
                {"CloseRate": 880.0},
                {"CloseRate": 810.0},
                {"CloseRate": 950.0},
                {"CloseRate": 870.0},
            ]
        )

        # When
        actual = evaluate_grid(_result(daily, _trades([])))

        # Then
        assert actual.breach_days == 3
        assert actual.breach_episodes == 2
        assert actual.breach_depth_max == pytest.approx(-0.10, abs=RATE_TOLERANCE)

    def test_이탈이_없으면_깊이가_None이다(self) -> None:
        """
        목적: 엣지 케이스 — 이탈이 0일인 실행을 고정한다

        Given: 종가가 언제나 하단 위인 실행 (실측에서 2017~ 구간이 그렇다)
        When: 지표를 낸다
        Then: 이탈일 0 · 구간 0 · 깊이 None 이다
        """
        # When
        actual = evaluate_grid(_result(_daily([{"CloseRate": 1000.0}, {"CloseRate": 1050.0}]), _trades([])))

        # Then
        assert actual.breach_days == 0
        assert actual.breach_episodes == 0
        assert actual.breach_depth_max is None

    def test_재조정_시_범위_변화량을_낸다(self) -> None:
        """
        목적: 사양서 §13.2 의 「재조정 시 범위 변화량」을 고정한다 — 윈도우 엣지 효과

        Given: 재조정일에 하단이 900 → 990 으로 10% 오른다
        When: 지표를 낸다
        Then: 하단 변화량의 최대가 10% 다

        Note:
            **첫 거래일은 변화량이 없다** — 직전 범위가 없으므로 비교 대상이 아니다
        """
        # Given
        daily = _daily(
            [
                {"Rebalanced": True, "RangeLow": 900.0},
                {"RangeLow": 900.0},
                {"Rebalanced": True, "RangeLow": 990.0},
            ]
        )

        # When
        actual = evaluate_grid(_result(daily, _trades([])))

        # Then
        assert actual.range_low_shift_max == pytest.approx(0.10, abs=RATE_TOLERANCE)

    def test_활성_레벨과_상한_발동을_센다(self) -> None:
        """
        목적: 사양서 §13.2 의 「활성 레벨 수 min/max」·「상한 발동 횟수」를 고정한다

        Given: 활성 레벨이 20~30 이고 상한이 하루만 걸린다
        When: 지표를 낸다
        Then: min 20 · max 30 · 상한 발동 1일이다
        """
        # Given
        daily = _daily([{"ActiveLevels": 20}, {"ActiveLevels": 30, "CappedLevels": 3}])

        # When
        actual = evaluate_grid(_result(daily, _trades([])))

        # Then
        assert actual.active_levels_min == 20
        assert actual.active_levels_max == 30
        assert actual.capped_days == 1


class TestRedFlags:
    """사양서 §15.3 의 징후 판정을 고정한다.

    **판정할 수 없는 항목을 통과로 적지 않는다.** 빼 버리거나 통과로 적으면
    "검사했는데 괜찮았다"와 "애초에 검사하지 않았다"가 구분되지 않는다.
    """

    def _flags(self, curve: list[float], *, daily_rows: list[dict[str, object]] | None = None):
        """곡선 하나로 아홉 개 판정을 만든다."""
        rows = daily_rows or [{"TotalAssets": value} for value in curve]
        daily = _daily(rows)
        result = _result(daily, _trades([{"hold_days": 1, "realized": 1.0, "grid_excess": 1.0}]))
        series = daily.set_index(COL_DATE)["TotalAssets"]

        return {
            flag.name: flag
            for flag in red_flags(
                evaluate_curve(series, risk_free=pd.Series(0.0, index=series.index)),
                evaluate_grid(result),
            )
        }

    def test_아홉_개를_전부_판정한다(self) -> None:
        """
        목적: §15.3 표의 행을 하나도 빠뜨리지 않음을 고정한다

        Given: 아무 곡선
        When: 판정한다
        Then: 항목이 아홉 개다
        """
        # When
        actual = self._flags([100_000_000.0, 110_000_000.0, 105_000_000.0])

        # Then
        assert len(actual) == 9

    def test_한_실행으로_알_수_없는_항목은_판정_불가다(self) -> None:
        """
        목적: 「N 에 따라 경로 순위 변동」·「261250 β」를 통과로 적지 않음을 고정한다

        Given: 아무 곡선
        When: 판정한다
        Then: 두 항목의 판정이 None 이다

        Note:
            축별 검사와 등가성 검증이 답하는 항목이다. **통과로 적으면 검사한 것이 된다**
        """
        # When
        actual = self._flags([100_000_000.0, 110_000_000.0, 105_000_000.0])

        # Then
        assert actual["N 에 따라 경로 순위 변동"].triggered is None
        assert actual["261250 β < 1.95"].triggered is None

    def test_단조_증가_곡선이_걸린다(self) -> None:
        """
        목적: §15.3 의 「자산곡선 단조 증가」 판정을 고정한다

        Given: 한 번도 내려가지 않는 곡선
        When: 판정한다
        Then: 그 항목이 걸리고, 낙폭이 있는 곡선에서는 통과한다

        Note:
            익절형 매매법에서 실현손익만 집계하면 곡선이 **구조적으로** 우상향한다.
            그것을 잡으려는 징후이므로 낙폭이 0 인지가 기준이다
        """
        # When
        rising = self._flags([100_000_000.0, 110_000_000.0, 120_000_000.0])
        dipping = self._flags([100_000_000.0, 110_000_000.0, 105_000_000.0])

        # Then
        assert rising["자산곡선 단조 증가"].triggered is True
        assert dipping["자산곡선 단조 증가"].triggered is False

    def test_얕은_MDD가_걸린다(self) -> None:
        """
        목적: §15.3 의 「MDD 가 −10%보다 얕음」 판정을 고정한다

        Given: 낙폭이 −5% 인 곡선과 −20% 인 곡선
        When: 판정한다
        Then: 얕은 쪽만 걸린다

        Note:
            실측에서 이 항목이 **유일하게 걸리는 Red Flag** 이며, 원인은 미실현 손실 누락이
            아니라 투입률(평균 35.87%)이다. 판정은 그대로 두고 원인을 결과 문서에 적는다
        """
        # When
        shallow = self._flags([100_000_000.0, 100_000_000.0, 95_000_000.0])
        deep = self._flags([100_000_000.0, 100_000_000.0, 80_000_000.0])

        # Then
        assert shallow["MDD 가 −10%보다 얕음"].triggered is True
        assert deep["MDD 가 −10%보다 얕음"].triggered is False
