"""그리드 실행 계층의 표시·요약 계약을 고정한다.

`runner` 는 **계산하지 않는다.** 엔진이 낸 값을 사람이 읽는 형태로 바꾸고 요약을 모으기만 한다.

핵심 계약은 셋이다.

- **표시용 프레임을 한 번만 만든다.** 화면과 CSV 가 따로 가공하면 반올림 시점이 갈려
  화면에서 본 숫자를 CSV 에서 찾지 못한다
- **집계는 원값으로 한다.** 반올림된 표에서 다시 계산하면 이중 반올림으로 합계가 어긋난다
- **산출물만 보고는 알 수 없는 조건을 요약에 남긴다** — 비용·세금·이자가 없다는 사실이 대표적이다
"""

import pandas as pd
import pytest

from verify_lab.common_constants import COL_DATE, PRICE_DECIMALS
from verify_lab.strategy.grid.constants import (
    COL_TOTAL_ASSETS,
    DISPLAY_CLOSE_RATE,
    DISPLAY_DATE,
    DISPLAY_ENTRY_DATE,
    DISPLAY_GRID_EXCESS,
    DISPLAY_TOTAL_ASSETS,
    INITIAL_CAPITAL,
    LOWER_BREACH_EXTEND,
)
from verify_lab.strategy.grid.engine import DAILY_COLUMNS, TRADE_COLUMNS, GridConfig, GridResult
from verify_lab.strategy.grid.execution import Slot
from verify_lab.strategy.grid.interest import InterestConfig
from verify_lab.strategy.grid.paths.base import CostConfig
from verify_lab.strategy.grid.runner import (
    DAILY_LABELS,
    KEY_NOTES,
    KEY_PARAMETERS,
    KEY_PERIOD,
    KEY_RESULT,
    KEY_ROW_COUNTS,
    TRADE_LABELS,
    _build_meta,
    _display_daily,
    _display_trades,
)

# 금액 비교 허용오차
AMOUNT_TOLERANCE = 0.01


def _config() -> GridConfig:
    """테스트용 설정."""
    return GridConfig(
        lookback_years=3,
        growth_rate=0.008,
        min_range_width=0.20,
        allocation_spread=0.5,
        slot_cap_ratio=0.08,
        initial_capital=INITIAL_CAPITAL,
        cost=CostConfig(exchange_spread_rate=0.0008, slippage_rate=0.0010, brokerage_rate=0.0),
        interest=InterestConfig(rp_floor_rate=0.40, parking_floor_rate=0.50),
    )


def _daily() -> pd.DataFrame:
    """이틀짜리 일별 곡선 원값."""
    return pd.DataFrame(
        [
            {
                COL_DATE: pd.Timestamp("2020-01-02"),
                "CloseRate": 1234.56789,
                "ExecPrice": 1234.56789,
                "RangeLow": 1000.123456,
                "RangeHigh": 1500.987654,
                "Rebalanced": True,
                "ActiveLevels": 30,
                "HeldSlots": 0,
                "BuyCount": 0,
                "SellCount": 0,
                "BlockedCount": 0,
                "BuyAmount": 0.0,
                "CappedLevels": 0,
                "ExtendedLevels": 0,
                "HeldInvested": 0.0,
                "Cost": 0.0,
                "RpRate": 1.5,
                "ParkingRate": 2.5,
                "RpInterest": 0.0,
                "ParkingInterest": 0.0,
                "AccruedInterest": 0.0,
                "TaxPaid": 0.0,
                "GainTax": 0.0,
                "Cash": 100_000_000.6,
                "UsdValue": 0.0,
                "TotalAssets": 100_000_000.6,
            },
            {
                COL_DATE: pd.Timestamp("2020-01-03"),
                "CloseRate": 1200.0,
                "ExecPrice": 1200.0,
                "RangeLow": 1000.123456,
                "RangeHigh": 1500.987654,
                "Rebalanced": False,
                "ActiveLevels": 30,
                "HeldSlots": 1,
                "BuyCount": 1,
                "SellCount": 0,
                "BlockedCount": 2,
                "BuyAmount": 4_000_000.4,
                "CappedLevels": 4,
                "ExtendedLevels": 3,
                "HeldInvested": 4_007_200.4,
                "Cost": 7_200.7,
                "RpRate": 1.5,
                "ParkingRate": 2.5,
                "RpInterest": 0.0,
                "ParkingInterest": 6_849.3,
                "AccruedInterest": 6_849.3,
                "TaxPaid": 0.0,
                "GainTax": 0.0,
                "Cash": 96_000_000.0,
                "UsdValue": 4_000_000.4,
                "TotalAssets": 100_000_000.4,
            },
        ],
        columns=DAILY_COLUMNS,
    )


def _trades() -> pd.DataFrame:
    """체결 한 건짜리 원값."""
    return pd.DataFrame(
        [
            {
                "level_index": 5,
                "level_price": 1040.6451405,
                "target_price": 1048.9,
                "entry_date": pd.Timestamp("2020-01-03"),
                "entry_rate": 1200.0,
                "entry_price": 1200.0,
                "exit_date": pd.Timestamp("2020-02-03"),
                "exit_rate": 1250.0,
                "exit_price": 1250.0,
                "invested": 4_000_000.4,
                "proceeds": 4_166_667.1,
                "realized": 166_666.7,
                "grid_excess": 134_666.7,
                "hold_days": 31,
            }
        ],
        columns=TRADE_COLUMNS,
    )


def _result() -> GridResult:
    """미청산 한 건이 남은 실행 결과."""
    slot = Slot(
        level_index=7,
        entry_date=pd.Timestamp("2020-01-03"),
        entry_price=1200.0,
        entry_rate=1200.0,
        units=1000.0,
        invested=1_202_160.0,
        entry_cost=2_160.0,
    )

    return GridResult(
        daily=_daily(),
        trades=_trades(),
        open_slots=(slot,),
        open_invested=1_200_000.0,
        open_value=1_150_000.0,
        open_unrealised=-50_000.0,
        bought_units=5_000.0,
        bought_invested=6_010_800.0,
    )


class TestDisplayDaily:
    """일별 곡선의 표시용 변환을 고정한다."""

    def test_한글_헤더로_바꾼다(self) -> None:
        """
        목적: 내부 토큰과 출력 레이블의 분리를 고정한다

        Given: 엔진이 낸 영문 컬럼의 곡선
        When: 표시용으로 바꾼다
        Then: 컬럼이 전부 한글 레이블이고 순서가 유지된다
        """
        # When
        actual = _display_daily(_daily())

        # Then
        assert list(actual.columns) == [DAILY_LABELS[column] for column in DAILY_COLUMNS]

    def test_날짜를_문자열로_바꾼다(self) -> None:
        """
        목적: CSV 에서 날짜가 시각 없이 보이도록 고정한다

        Given: `datetime64` 날짜
        When: 표시용으로 바꾼다
        Then: `YYYY-MM-DD` 문자열이다
        """
        # When
        actual = _display_daily(_daily())

        # Then
        assert actual[DISPLAY_DATE].tolist() == ["2020-01-02", "2020-01-03"]

    def test_가격은_4자리_자본금은_정수로_반올림한다(self) -> None:
        """
        목적: `.claude/rules/python.md` 의 반올림 규칙표를 고정한다

        Given: 소수가 깊은 원값
        When: 표시용으로 바꾼다
        Then: 환율은 4자리, 자본금은 정수다
        """
        # When
        actual = _display_daily(_daily())

        # Then
        assert actual[DISPLAY_CLOSE_RATE].iloc[0] == pytest.approx(round(1234.56789, PRICE_DECIMALS), abs=1e-9)
        assert actual[DISPLAY_TOTAL_ASSETS].iloc[0] == pytest.approx(100_000_001.0, abs=AMOUNT_TOLERANCE)

    def test_원본을_바꾸지_않는다(self) -> None:
        """
        목적: 데이터 불변성을 고정한다

        Given: 엔진이 낸 곡선
        When: 표시용으로 바꾼다
        Then: 원본의 컬럼과 값이 그대로다
        """
        # Given
        original = _daily()
        before = original[COL_TOTAL_ASSETS].tolist()

        # When
        _display_daily(original)

        # Then
        assert list(original.columns) == DAILY_COLUMNS
        assert original[COL_TOTAL_ASSETS].tolist() == before


class TestDisplayTrades:
    """체결 내역의 표시용 변환을 고정한다."""

    def test_한글_헤더로_바꾸고_날짜를_문자열로_만든다(self) -> None:
        """
        목적: 사용자가 차트로 대조할 원자료의 형태를 고정한다

        Given: 체결 한 건
        When: 표시용으로 바꾼다
        Then: 한글 헤더이고 매수일이 `YYYY-MM-DD` 다
        """
        # When
        actual = _display_trades(_trades())

        # Then
        assert list(actual.columns) == [TRADE_LABELS[column] for column in TRADE_COLUMNS]
        assert actual[DISPLAY_ENTRY_DATE].iloc[0] == "2020-01-03"

    def test_이탈_보너스가_컬럼으로_남는다(self) -> None:
        """
        목적: 종가 체결 가정의 기여분이 산출물에 실림을 고정한다 (사양서 §6.4)

        Given: 체결 한 건
        When: 표시용으로 바꾼다
        Then: 이탈 보너스 컬럼이 있고 값이 정수로 반올림돼 있다
        """
        # When
        actual = _display_trades(_trades())

        # Then
        assert actual[DISPLAY_GRID_EXCESS].iloc[0] == pytest.approx(134_667.0, abs=AMOUNT_TOLERANCE)

    def test_체결이_없어도_헤더를_유지한다(self) -> None:
        """
        목적: 엣지 케이스 — 빈 체결 내역이 예외를 내지 않음을 고정한다

        Given: 체결 0건
        When: 표시용으로 바꾼다
        Then: 예외 없이 빈 표이고 컬럼 구성이 유지된다
        """
        # When
        actual = _display_trades(pd.DataFrame(columns=TRADE_COLUMNS))

        # Then
        assert actual.empty
        assert list(actual.columns) == [TRADE_LABELS[column] for column in TRADE_COLUMNS]


class TestBuildMeta:
    """요약 페이로드를 고정한다."""

    def test_실행_파라미터가_전부_담긴다(self) -> None:
        """
        목적: 산출물만 보고 어떤 설정의 결과인지 재구성할 수 있게 함을 고정한다

        Given: 실행 결과와 설정
        When: 요약을 만든다
        Then: 다섯 파라미터와 초기 자본금·비용·이자·앵커·시작일이 담겨 있다
        """
        # When
        actual = _build_meta(_result(), config=_config(), start_date="2005-01-01")

        # Then
        assert set(actual[KEY_PARAMETERS]) == {
            "lookback_years",
            "growth_rate",
            "min_range_width",
            "allocation_spread",
            "slot_cap_ratio",
            "initial_capital",
            "path",
            "lower_breach",
            "exchange_spread_rate",
            "slippage_rate",
            "brokerage_rate",
            "round_trip_cost_rate",
            "rp_floor_rate",
            "parking_floor_rate",
            "interest_tax_rate",
            "anchor",
            "start_date",
        }

    def test_왕복_비용률을_함께_남긴다(self) -> None:
        """
        목적: 편도 두 항을 더해 왕복으로 읽는 계산을 요약 쪽에 한 번만 두게 고정한다

        Given: 환전 스프레드 0.08% · 슬리피지 0.10% 의 설정
        When: 요약을 만든다
        Then: 왕복 비용률이 0.36% 다 (사양서 §10 의 왕복 총계)
        """
        # When
        actual = _build_meta(_result(), config=_config(), start_date="2005-01-01")

        # Then
        assert actual[KEY_PARAMETERS]["round_trip_cost_rate"] == pytest.approx(0.0036, abs=1e-9)

    def test_집계는_원값으로_한다(self) -> None:
        """
        목적: 이중 반올림을 피함을 고정한다

        Given: 소수가 있는 실현손익·이탈 보너스
        When: 요약을 만든다
        Then: 표시용 표가 아니라 원값에서 합산한 값이다
        """
        # When
        actual = _build_meta(_result(), config=_config(), start_date="2005-01-01")

        # Then
        assert actual[KEY_RESULT]["realized_total"] == pytest.approx(166_667.0, abs=AMOUNT_TOLERANCE)
        assert actual[KEY_RESULT]["grid_excess_total"] == pytest.approx(134_667.0, abs=AMOUNT_TOLERANCE)

    def test_미청산_슬롯을_요약에_남긴다(self) -> None:
        """
        목적: 결정 C8·G4 를 고정한다 — 강제 청산하지 않고 세전 평가로 남긴다

        Given: 미청산 한 건이 남은 결과
        When: 요약을 만든다
        Then: 건수와 투입액·평가액·평가손익이 담겨 있다
        """
        # When
        actual = _build_meta(_result(), config=_config(), start_date="2005-01-01")

        # Then
        assert actual[KEY_RESULT]["open_slots"] == 1
        assert actual[KEY_RESULT]["open_unrealised"] == pytest.approx(-50_000.0, abs=AMOUNT_TOLERANCE)

    def test_이탈_보너스_비중을_낸다(self) -> None:
        """
        목적: 사양서 §15.3 Red Flag 판정에 필요한 값을 고정한다

        Given: 실현손익과 이탈 보너스가 있는 결과
        When: 요약을 만든다
        Then: 비중이 실현손익 대비 비율로 담겨 있다
        """
        # When
        actual = _build_meta(_result(), config=_config(), start_date="2005-01-01")

        # Then
        assert actual[KEY_RESULT]["grid_excess_share_of_realized"] == pytest.approx(134_666.7 / 166_666.7, abs=1e-4)

    def test_체결이_없으면_비중이_비어_있다(self) -> None:
        """
        목적: 엣지 케이스 — 0 으로 나누지 않음을 고정한다

        Given: 체결 0건
        When: 요약을 만든다
        Then: 비중이 `None` 이다 (0 으로 채우면 "보너스가 없다"로 읽힌다)
        """
        # Given
        empty = GridResult(
            daily=_daily(),
            trades=pd.DataFrame(columns=TRADE_COLUMNS),
            open_slots=(),
            open_invested=0.0,
            open_value=0.0,
            open_unrealised=0.0,
        )

        # When
        actual = _build_meta(empty, config=_config(), start_date="2005-01-01")

        # Then
        assert actual[KEY_RESULT]["grid_excess_share_of_realized"] is None

    def test_산출물만_보고는_알_수_없는_조건을_남긴다(self) -> None:
        """
        목적: 비용·세금·이자가 없다는 사실이 요약에 남음을 고정한다

        Given: 실행 결과
        When: 요약을 만든다
        Then: 비고에 그 사실이 적혀 있다

        Note:
            이 조건을 남기지 않으면 나중에 **비용이 반영된 결과로 오독**한다
        """
        # When
        actual = _build_meta(_result(), config=_config(), start_date="2005-01-01")

        # Then
        assert any("비용" in note for note in actual[KEY_NOTES])
        assert any("미실현" in note for note in actual[KEY_NOTES])

    def test_행_수를_남긴다(self) -> None:
        """
        목적: 표본 보존 확인에 필요한 값을 고정한다

        Given: 이틀짜리 곡선과 체결 한 건
        When: 요약을 만든다
        Then: 두 표의 행 수가 담겨 있다
        """
        # When
        actual = _build_meta(_result(), config=_config(), start_date="2005-01-01")

        # Then
        assert actual[KEY_ROW_COUNTS] == {"daily": 2, "trades": 1}
        assert actual[KEY_PERIOD]["trading_days"] == 2


class TestLowerBreachSummary:
    """하단 이탈 B안의 측정 항목이 요약에 실림을 고정한다 (사양서 §7).

    §7 은 B안에 다섯 가지를 요구한다 — 연장 발생 횟수 / 최대 연장 칸 수 / 현금 완전 소진
    여부·시점 / 소진 시점의 평가손실률 / A안 대비 평균단가·MDD. **앞의 넷은 실행 하나로 나오고**
    마지막 하나는 두 실행을 견주는 일이라 요약이 재료(평균단가)만 낸다.
    """

    def test_연장_통계를_남긴다(self) -> None:
        """
        목적: 사양서 §7 의 측정 항목 1(연장 발생 횟수·최대 칸 수)을 고정한다

        Given: 둘째 날에 연장 레벨이 3개 켜진 곡선
        When: 요약을 만든다
        Then: 연장 발동 거래일이 1일, 최대 연장 칸이 3이다
        """
        # When
        actual = _build_meta(_result(), config=_config(), start_date="2005-01-01")

        # Then
        assert actual[KEY_RESULT]["extension_days"] == 1
        assert actual[KEY_RESULT]["extension_levels_max"] == 3

    def test_소진_시점과_그때의_평가손익률을_남긴다(self) -> None:
        """
        목적: 사양서 §7 의 측정 항목 2·3 을 고정한다

        Given: 둘째 날에 자금 부족이 2건 나고 그날 보유 투입액이 4,007,200.4원, 평가액이 4,000,000.4원인 곡선
        When: 요약을 만든다
        Then: 첫 소진일이 그날이고 평가손익률이 `(평가액 − 투입액) ÷ 투입액` 이다
        """
        # Given
        expected = (4_000_000.4 - 4_007_200.4) / 4_007_200.4

        # When
        actual = _build_meta(_result(), config=_config(), start_date="2005-01-01")

        # Then
        assert actual[KEY_RESULT]["first_blocked_date"] == "2020-01-03"
        assert actual[KEY_RESULT]["unrealised_rate_at_first_block"] == pytest.approx(expected, abs=1e-6)

    def test_평균단가는_투입원화를_취득단위로_나눈_값이다(self) -> None:
        """
        목적: 평균단가의 정의를 고정한다 (결정 C84)

        Given: 매수 누계가 6,010,800원 / 5,000단위인 결과
        When: 요약을 만든다
        Then: 평균단가가 1,202.16원이다

        Note:
            **비용을 포함한 실제 단가**다. 지정가 운용이었다면 얼마였을지가 아니라
            "이 매매법이 실제로 얼마에 샀는가" 가 §7 의 물음이기 때문이다
        """
        # When
        actual = _build_meta(_result(), config=_config(), start_date="2005-01-01")

        # Then
        assert actual[KEY_RESULT]["average_unit_cost"] == pytest.approx(1_202.16, abs=AMOUNT_TOLERANCE)

    def test_취득_단위가_없으면_평균단가가_비어_있다(self) -> None:
        """
        목적: 엣지 케이스 — 매수가 한 건도 없을 때 0 으로 나누지 않음을 고정한다

        Given: 매수 누계가 0인 결과
        When: 요약을 만든다
        Then: 평균단가가 None 이다 — 0 을 돌려주면 "0원에 샀다"로 읽힌다
        """
        # Given
        result = GridResult(
            daily=_daily(),
            trades=_trades(),
            open_slots=(),
            open_invested=0.0,
            open_value=0.0,
        )

        # When
        actual = _build_meta(result, config=_config(), start_date="2005-01-01")

        # Then
        assert actual[KEY_RESULT]["average_unit_cost"] is None

    def test_소진이_없으면_시점이_비어_있다(self) -> None:
        """
        목적: 엣지 케이스 — 자금 부족이 한 번도 없는 실행을 고정한다

        Given: 자금 부족이 0인 곡선
        When: 요약을 만든다
        Then: 첫 소진일과 그때의 평가손익률이 모두 None 이다
        """
        # Given
        daily = _daily()
        daily["BlockedCount"] = 0
        result = GridResult(
            daily=daily,
            trades=_trades(),
            open_slots=(),
            open_invested=0.0,
            open_value=0.0,
        )

        # When
        actual = _build_meta(result, config=_config(), start_date="2005-01-01")

        # Then
        assert actual[KEY_RESULT]["first_blocked_date"] is None
        assert actual[KEY_RESULT]["unrealised_rate_at_first_block"] is None

    def test_하단_이탈_방식이_파라미터에_남는다(self) -> None:
        """
        목적: 산출물만 보고 A안인지 B안인지 알 수 있게 함을 고정한다

        Given: B안으로 돈 결과
        When: 요약을 만든다
        Then: 파라미터에 그 값이 담겨 있다
        """
        # When
        actual = _build_meta(_result(), config=_config(), start_date="2005-01-01", lower_breach=LOWER_BREACH_EXTEND)

        # Then
        assert actual[KEY_PARAMETERS]["lower_breach"] == LOWER_BREACH_EXTEND
