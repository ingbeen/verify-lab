"""달력으로 일정을 정하는 매매법의 거래일 목록 검사

진입·청산을 달력 규칙(그 달 마지막 거래일 등)으로 정하는 매매법은 **거래일 목록**을 입력으로
받는다. 그 목록이 비었거나 정렬·중복 조건을 어기면 위치 계산이 예외 없이 엉뚱한 날을 고르므로,
일정을 만들기 전에 여기서 막는다.

**공통 계층이 소유한다.** 매매법마다 같은 검사를 두면 조건이 조용히 갈라진다
(패키지 절대 원칙 「판정식 단일화」). 지금 쓰는 곳은 중간선거_사이클의 달력(`cycle_calendar.py`)이다.
"""

import pandas as pd


def validate_trading_days(trading_days: pd.DatetimeIndex, *, purpose: str) -> None:
    """거래일 목록이 달력 일정 산출의 전제를 만족하는지 검사한다.

    Args:
        trading_days: 검사할 거래일 목록
        purpose: 무엇을 산출하려던 것인지. 예외 메시지에 실린다

    Raises:
        ValueError: 비었거나 정렬·중복 조건을 어긴 경우
    """
    if len(trading_days) == 0:
        raise ValueError(f"거래일 목록이 비어 있어 {purpose}을 산출할 수 없습니다")
    if not trading_days.is_monotonic_increasing:
        raise ValueError("거래일 목록이 오름차순으로 정렬되어 있어야 합니다")
    if trading_days.has_duplicates:
        raise ValueError("거래일 목록에 중복된 날짜가 있습니다")


__all__ = ["validate_trading_days"]
