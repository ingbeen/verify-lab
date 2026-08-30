"""역방향 매매 규칙의 체결 계산

신호일 하나에 규칙을 적용해 **체결 결과 하나**를 낸다. 규칙 전문은
`docs/strategy/역방향_매매_규칙.md` §1 이 SoT다.

**이 계층이 틀리는 방식은 판정 순서가 뒤바뀌는 것**이다. 시가·장중·종가를 이 순서로 보지
않으면 갭 하락한 날에 장중 손절가로 체결된 것처럼 계산되어 손실이 실제보다 작게 나온다.
그래서 순서를 함수 하나에 가두고 테스트로 고정한다.

**부호는 역방향 기준이다.** 폭락 신호는 지수를 사고 폭등 신호는 인버스를 사므로, 폭등 신호의
수익률은 원지수 수익률에 −1 을 곱한 값이다. 이것은 원지수의 반대방향 수익률이지
인버스 상품의 손익이 아니다 — 일간 복리·보수·롤 비용은 반영되지 않는다.
"""

from dataclasses import dataclass

import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_HIGH, COL_LOW, COL_OPEN
from verify_lab.strategy.constants import (
    EXIT_GAP_STOP,
    EXIT_INTRADAY_STOP,
    EXIT_LIMIT,
    EXIT_PROFIT,
    STOP_LOSS_LEVEL,
)

# 계산에 필요한 시세 컬럼. 장중 판정에 고가·저가가 모두 필요하다 — 방향에 따라 어느 쪽이
# 손실인지 갈린다
REQUIRED_MARKET_COLUMNS = [COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE]


@dataclass(frozen=True)
class TradeResult:
    """신호 하나의 체결 결과

    Attributes:
        return_rate: 체결 수익률 (비율). 역방향 기준으로 부호가 맞춰져 있다
        reason: 청산 사유
        hold_days: 진입일로부터의 보유 거래일 수
    """

    return_rate: float
    reason: str
    hold_days: int


def simulate_signal(
    frame: pd.DataFrame,
    entry_position: int,
    *,
    upward: bool,
    hold_limit: int,
    stop_level: float = STOP_LOSS_LEVEL,
) -> TradeResult | None:
    """신호일 하나에 매매 규칙을 적용해 체결 결과를 낸다.

    판정 순서는 **시가 → 장중 → 종가**이며, 위에서 걸리면 아래는 보지 않는다.

    1. 시가가 손절선 아래면 **그 시가로** 청산한다 (손절선보다 더 잃는다)
    2. 장중 최악이 손절선을 터치하면 **손절가로** 청산한다
    3. 종가가 진입가보다 위면 **그날 종가로** 청산한다
    4. 손실이면 다음 날로 넘기고, 한도일에는 손실이어도 종가로 청산한다

    **손절선은 진입가 기준이며 보유 기간 내내 바뀌지 않는다.** 매일 갱신하면 손실이
    이어질 때 손절선이 따라 내려가 최악이 무제한으로 열린다.

    Args:
        frame: 날짜 오름차순 시세 (`data/loader.py` 가 검증해 돌려준 형태)
        entry_position: 신호일의 위치 인덱스. 진입가는 이 날의 종가다
        upward: 상승 방향 신호(폭등)인지 여부. 참이면 인버스로 진입하므로 부호가 뒤집힌다
        hold_limit: 보유 한도 (거래일, 1 이상)
        stop_level: 손절선 (비율, 0.05 = 5%)

    Returns:
        체결 결과. 측정 구간이 데이터를 넘어가면 `None`

    Raises:
        ValueError: 한도가 1 미만이거나, 손절선이 양수가 아니거나,
            필요한 컬럼이 없거나, 진입 위치가 범위 밖인 경우
        RuntimeError: 한도 안에서 청산되지 않은 경우 (내부 불변조건 위반)
    """
    _validate(frame, entry_position, hold_limit=hold_limit, stop_level=stop_level)

    entry_price = float(frame.iloc[entry_position][COL_CLOSE])
    sign = -1.0 if upward else 1.0

    for day in range(1, hold_limit + 1):
        position = entry_position + day
        if position >= len(frame):
            # 측정 구간이 데이터를 넘어갔다. 부분 체결을 남기면 표본이 조용히 섞인다
            return None

        row = frame.iloc[position]
        open_rate = _rate(float(row[COL_OPEN]), entry_price, sign)
        worst_rate = _rate(float(row[COL_HIGH] if upward else row[COL_LOW]), entry_price, sign)
        close_rate = _rate(float(row[COL_CLOSE]), entry_price, sign)

        # 1. 시가가 이미 손절선 아래면 그 시가가 체결가다 — 손절선을 지켜주지 못한다
        if open_rate <= -stop_level:
            return TradeResult(open_rate, EXIT_GAP_STOP, day)

        # 2. 장중에 손절선을 터치하면 손절가에 체결된다
        if worst_rate <= -stop_level:
            return TradeResult(-stop_level, EXIT_INTRADAY_STOP, day)

        # 3. 이익이면 그날 종가로 청산하고 끝낸다
        if close_rate > 0:
            return TradeResult(close_rate, EXIT_PROFIT, day)

        # 4. 한도일에는 손실이어도 청산한다
        if day == hold_limit:
            return TradeResult(close_rate, EXIT_LIMIT, day)

    raise RuntimeError(f"내부 불변조건 위반: 한도 안에서 청산되지 않았습니다 - 한도 {hold_limit}")


def _rate(price: float, entry_price: float, sign: float) -> float:
    """진입가 대비 수익률을 역방향 부호로 낸다.

    Args:
        price: 비교할 가격
        entry_price: 진입가
        sign: 상승 방향 신호면 -1, 하락 방향이면 1

    Returns:
        수익률 (비율)
    """
    return (price / entry_price - 1.0) * sign


def _validate(
    frame: pd.DataFrame,
    entry_position: int,
    *,
    hold_limit: int,
    stop_level: float,
) -> None:
    """입력을 즉시 검사한다.

    Args:
        frame: 시세
        entry_position: 신호일의 위치 인덱스
        hold_limit: 보유 한도
        stop_level: 손절선

    Raises:
        ValueError: 값이 유효하지 않은 경우
    """
    missing_columns = set(REQUIRED_MARKET_COLUMNS) - set(frame.columns)
    if missing_columns:
        raise ValueError(f"시세에 필수 컬럼이 없습니다: {sorted(missing_columns)}")

    if hold_limit < 1:
        raise ValueError(f"보유 한도는 1 이상이어야 합니다: {hold_limit}")

    if stop_level <= 0:
        raise ValueError(f"손절선은 양수여야 합니다: {stop_level}")

    if not 0 <= entry_position < len(frame):
        raise ValueError(f"진입 위치가 시세 범위 밖입니다: {entry_position} (시세 {len(frame)}행)")
