"""체결 하나를 거래내역 행으로 바꾸는 공통 여덟 칸을 고정한다.

**세 매매법(역방향 · 중간선거_사이클 · 반감기_사이클)이 같은 여덟 칸을 만든다.** 각자 두면
청산가를 되돌리는 부호 하나만 갈려도 **거래내역의 청산가가 차트와 어긋나는데 예외는 나지 않는다**
(`src/verify_lab/CLAUDE.md` 「어디까지가 공통이고 어디부터 그 검증의 것인가」 — 세 번째가 와서 올렸다).

**기대 컬럼과 값을 손으로 박아 둔다** — 프로덕션 상수에서 기대값을 만들면 그 상수가 바뀔 때 테스트가
함께 따라와 아무것도 고정하지 못한다 (`tests/CLAUDE.md` 「픽스처가 코드와 같은 가정을 하면 …」).
"""

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_VALUE
from verify_lab.execution.trade_fill import TradeResult
from verify_lab.execution.trade_rows import trade_columns

# 거래내역 공통 컬럼 중 «식별 칸 뒤» 여덟 칸 — 이 순서까지 계약이다
EXPECTED_COLUMNS = [
    "진입일",
    "진입가",
    "청산일",
    "보유일",
    "청산가",
    "수익률(%)",
    "보유 중 최악(%)",
    "청산 사유",
]


def _frame() -> pd.DataFrame:
    """날짜 다섯과 종가 다섯짜리 시세."""
    return pd.DataFrame(
        {
            COL_DATE: pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
            COL_CLOSE: [100.0, 101.0, 102.0, 103.0, 110.0],
        }
    )


def test_여덟_칸이_거래내역_순서로_나온다() -> None:
    """
    목적: 공통 여덟 칸의 이름과 순서를 고정한다 — 호출 측은 식별 칸만 앞에 붙인다.

    Given: 무손절 체결 하나
    When: 행 칸을 만든다
    Then: 키가 정해진 여덟 개이고 순서도 같다
    """
    # Given
    result = TradeResult(return_rate=0.10, reason="기한청산", hold_days=4, worst_hold_rate=-0.02)

    # When
    columns = trade_columns(_frame(), 0, result, bet_down=False, price_column=COL_CLOSE, price_decimals=4)

    # Then
    assert list(columns) == EXPECTED_COLUMNS


def test_위로_건_체결의_청산가는_진입가에_수익률을_곱한_값이다() -> None:
    """
    목적: 「위」 체결의 청산가 산식을 손 계산 값으로 고정한다.

    **청산가는 실제 체결가다** — 손절로 나간 체결은 예정일 종가가 아니라 손절가에 나가므로
    시세의 종가를 다시 읽지 않고 수익률에서 되돌린다.

    Given: 진입가 100, 수익률 +10%, 보유 4일
    When: 행 칸을 만든다
    Then: 청산가 110 · 청산일은 진입 위치 + 4 의 날짜 · 수익률 10.0 · 보유 중 최악 −2.0
    """
    # Given
    result = TradeResult(return_rate=0.10, reason="기한청산", hold_days=4, worst_hold_rate=-0.02)

    # When
    columns = trade_columns(_frame(), 0, result, bet_down=False, price_column=COL_CLOSE, price_decimals=4)

    # Then
    assert columns["진입일"] == "2024-01-01"
    assert columns["진입가"] == pytest.approx(100.0, abs=0.01)
    assert columns["청산일"] == "2024-01-05"
    assert columns["보유일"] == 4
    assert columns["청산가"] == pytest.approx(110.0, abs=0.01)
    assert columns["수익률(%)"] == pytest.approx(10.0, abs=0.1)
    assert columns["보유 중 최악(%)"] == pytest.approx(-2.0, abs=0.1)
    assert columns["청산 사유"] == "기한청산"


def test_아래로_건_체결은_부호를_뒤집어_청산가를_되돌린다() -> None:
    """
    목적: 「아래」 체결에서 부호를 빠뜨리면 청산가가 반대로 틀리는 것을 막는다.

    수익률은 거는 방향이 이미 반영된 값이다 — 아래로 걸어 +5% 를 벌었다면 가격은 5% **내렸다.**

    Given: 진입가 102 (위치 2), 아래로 건 수익률 +5%, 보유 1일
    When: 행 칸을 만든다
    Then: 청산가 96.9 (= 102 × 0.95)
    """
    # Given
    result = TradeResult(return_rate=0.05, reason="장중손절", hold_days=1, worst_hold_rate=-0.01)

    # When
    columns = trade_columns(_frame(), 2, result, bet_down=True, price_column=COL_CLOSE, price_decimals=4)

    # Then
    assert columns["진입가"] == pytest.approx(102.0, abs=0.01)
    assert columns["청산일"] == "2024-01-04"
    assert columns["청산가"] == pytest.approx(96.9, abs=0.01)


def test_가격_자릿수를_따른다() -> None:
    """
    목적: 원화 정수 가격처럼 자릿수가 0 인 대상이 소수를 달지 않음을 고정한다 (경계 조건).

    Given: 진입가 101, 수익률 +3.3%, 자릿수 0
    When: 행 칸을 만든다
    Then: 진입가 101 · 청산가 104 (104.333 을 0자리로)
    """
    # Given
    result = TradeResult(return_rate=0.033, reason="기한청산", hold_days=2, worst_hold_rate=0.0)

    # When
    columns = trade_columns(_frame(), 1, result, bet_down=False, price_column=COL_CLOSE, price_decimals=0)

    # Then
    assert columns["진입가"] == 101
    assert columns["청산가"] == 104


def test_가격_컬럼을_인자로_고른다() -> None:
    """
    목적: 종가 계열(지수)도 같은 함수를 지나는지 고정한다 — 가격 컬럼이 `Value` 인 경우.

    Given: `Value` 컬럼만 있는 계열, 진입 위치 0
    When: 가격 컬럼을 `Value` 로 준다
    Then: 진입가가 그 컬럼에서 온다
    """
    # Given
    series = pd.DataFrame({COL_DATE: pd.to_datetime(["2024-01-01", "2024-01-02"]), COL_VALUE: [5000.0, 5100.0]})
    result = TradeResult(return_rate=0.02, reason="기한청산", hold_days=1, worst_hold_rate=0.0)

    # When
    columns = trade_columns(series, 0, result, bet_down=False, price_column=COL_VALUE, price_decimals=4)

    # Then
    assert columns["진입가"] == pytest.approx(5000.0, abs=0.01)
    assert columns["청산가"] == pytest.approx(5100.0, abs=0.01)
