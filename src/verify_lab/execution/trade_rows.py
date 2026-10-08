"""체결 하나를 거래내역 행으로 바꾸는 공통 칸 — 매매법을 가리지 않는 공유 계층

거래내역 한 줄은 **식별 칸(종목 · 매매법 축 · 방향 · 손절선) + 공통 여덟 칸 + 매매법 고유 칸**이다.
그중 공통 여덟 칸 — 진입일 · 진입가 · 청산일 · 보유일 · 청산가 · 수익률 · 보유 중 최악 · 청산 사유 — 을 여기서 만든다.

**세 매매법이 같은 여덟 칸을 만든다** — 두 벌까지는 각자 두고 세 번째가 오면 공유 계층에 둔다(`src/verify_lab/CLAUDE.md`
「어디까지가 공통이고 어디부터 그 검증의 것인가」). 각자 두면 청산가를 되돌리는 부호 하나만 갈려도 거래내역의
청산가가 차트와 어긋나는데 예외는 나지 않는다.
"""

from typing import Any

import pandas as pd

from verify_lab.common_constants import COL_DATE, RATE_TO_PERCENT
from verify_lab.execution.constants import (
    DISPLAY_ENTRY_DATE,
    DISPLAY_ENTRY_PRICE,
    DISPLAY_EXIT_DATE,
    DISPLAY_EXIT_PRICE,
    DISPLAY_EXIT_REASON,
    DISPLAY_HOLD_DAYS,
    DISPLAY_RETURN,
    DISPLAY_WORST_HOLD,
)
from verify_lab.execution.trade_fill import TradeResult
from verify_lab.report.constants import DATE_FORMAT, PERCENT_DECIMALS


def trade_columns(
    frame: pd.DataFrame,
    entry_position: int,
    result: TradeResult,
    *,
    bet_down: bool,
    price_column: str,
    price_decimals: int,
) -> dict[str, Any]:
    """체결 하나의 공통 여덟 칸을 만든다. 식별 칸과 고유 칸은 호출 측이 앞뒤에 붙인다.

    **청산가는 실제 체결가다.** 손절로 나간 체결은 예정일 종가가 아니라 손절가(또는 갭이 열린 시가)에
    나가므로, 시세의 종가를 다시 읽지 않고 **수익률에서 되돌린다** — 수익률은 거는 방향이 이미 반영된
    값이라 되돌릴 때도 같은 부호를 곱한다.

    Args:
        frame: 체결을 잰 시세 또는 계열
        entry_position: 진입일의 위치 인덱스. 청산일은 이 위치 + 보유일이다
        result: `trade_fill` 이 낸 체결 결과
        bet_down: 아래로 걸었는지 여부
        price_column: 진입가를 읽을 가격 컬럼
        price_decimals: 가격 출력 자릿수. 원시 데이터를 저장한 자릿수와 같아야 한다

    Returns:
        거래내역 공통 칸 여덟 (거래내역 컬럼 순서)
    """
    exit_position = entry_position + result.hold_days

    return trade_columns_from(
        pd.Timestamp(frame.iloc[entry_position][COL_DATE]),
        float(frame.iloc[entry_position][price_column]),
        pd.Timestamp(frame.iloc[exit_position][COL_DATE]),
        result,
        bet_down=bet_down,
        price_decimals=price_decimals,
    )


def trade_columns_from(
    entry_day: pd.Timestamp,
    entry_price: float,
    exit_day: pd.Timestamp,
    result: TradeResult,
    *,
    bet_down: bool,
    price_decimals: int,
) -> dict[str, Any]:
    """진입일 · 진입가 · 청산일을 직접 받아 공통 여덟 칸을 만든다.

    **진입가가 어느 날의 종가도 아닌 체결이 있다** — 여러 회차로 나눠 산 포지션의 진입가는 평균 매수가다. 그래도
    청산가는 같은 산식(수익률에서 되돌리기)으로 나와야 한다: 평균 매수가 × (1 + 수익률) = 평균 매도가.
    `trade_columns` 도 시세에서 셋을 읽어 이것을 부른다 — 형식과 되돌리기가 한 벌이다.

    Args:
        entry_day: 진입일
        entry_price: 진입가
        exit_day: 실제로 나간 날
        result: 체결 결과. 보유일은 `result.hold_days` 를 그대로 싣는다
        bet_down: 아래로 걸었는지 여부
        price_decimals: 가격 출력 자릿수. 원시 데이터를 저장한 자릿수와 같아야 한다

    Returns:
        거래내역 공통 칸 여덟 (거래내역 컬럼 순서)
    """
    sign = -1.0 if bet_down else 1.0
    exit_price = entry_price * (1.0 + sign * result.return_rate)

    return {
        DISPLAY_ENTRY_DATE: entry_day.strftime(DATE_FORMAT),
        DISPLAY_ENTRY_PRICE: round(entry_price, price_decimals),
        DISPLAY_EXIT_DATE: exit_day.strftime(DATE_FORMAT),
        DISPLAY_HOLD_DAYS: result.hold_days,
        DISPLAY_EXIT_PRICE: round(exit_price, price_decimals),
        DISPLAY_RETURN: round(result.return_rate * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_WORST_HOLD: round(result.worst_hold_rate * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_EXIT_REASON: result.reason,
    }


__all__ = ["trade_columns", "trade_columns_from"]
