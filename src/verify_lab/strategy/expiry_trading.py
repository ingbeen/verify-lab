"""옵션 만기일 매매의 체결 계산 — 만기일 종가 매수 → 다음주 지정 요일 종가 매도

측정 근거는 `docs/research/옵션_만기일.md` 이고, 청산일 산출은
`studies/option_expiry/weekly_exit.py` 가 이미 한다. 이 모듈이 더하는 것은 **손절 하나**다.

**역방향 매매와 다른 점은 중간 익절이 없다는 것 하나뿐이다.** 청산이 달력 기준이라
이익이 나도 그날까지 들고 간다. 그래서 판정식을 새로 쓰지 않고 `reverse_trading.simulate_signal`
을 `take_profit=False` 로 부른다 — 시가·장중 순서가 뒤바뀌면 손실이 실제보다 작게 나오는
함정을 두 곳에서 관리하지 않기 위해서다 (패키지 절대 원칙 「판정식 단일화」).

**방향은 `bet_down` 으로 받는다.** 참이면 원지수가 내려야 이익이므로 인버스로 진입하는
쪽이고, `simulate_signal` 의 `upward`(폭등 신호 → 인버스 진입)와 같은 자리에 들어간다.
두 이름이 다른 것은 신호의 뜻이 다르기 때문이다 — 역방향은 「무슨 신호였나」를,
여기서는 「어느 쪽에 거나」를 가리킨다.

**수익률은 원지수 부호를 뒤집은 값이지 인버스 상품의 손익이 아니다.** 일간 리밸런싱 오차·
총보수·괴리율은 반영되지 않는다. 집행 수단은 사용자가 정한다
(`docs/research/옵션_만기일.md` §15.0).
"""

import pandas as pd

from verify_lab.common_constants import COL_CLOSE
from verify_lab.strategy.constants import EXIT_LIMIT
from verify_lab.strategy.reverse_trading import TradeResult, simulate_signal


def simulate_expiry_trade(
    frame: pd.DataFrame,
    entry_position: int,
    exit_position: int,
    *,
    bet_down: bool,
    stop_level: float | None,
) -> TradeResult:
    """만기 진입 하나에 손절을 걸어 체결 결과를 낸다.

    **보유 기간의 매일** 아래 순서로 보며, 위에서 걸리면 아래는 보지 않는다.
    손절은 청산일에만 재는 것이 아니라 **하루하루 감시한다.**

    1. 그날 시가가 손절선 아래면 **그 시가로** 청산한다 (손절선보다 더 잃는다)
    2. 그날 장중 최악이 손절선을 터치하면 **손절가로** 청산한다
    3. 어느 날에도 걸리지 않으면 **청산일 종가**로 나간다 — 이익이어도 중간에 팔지 않는다

    **손절선은 진입가 기준이며 보유 기간 내내 바뀌지 않는다.**

    **청산 위치는 호출 측이 정한다.** 달력이 지목한 날이 휴장이면 직전 거래일로 당기는 것도,
    목표일이 데이터 끝을 넘는 진입을 제외하는 것도 `weekly_exit.py` 의 일이다. 여기까지
    넘어온 진입은 이미 청산일이 확정된 것이므로, 범위를 벗어나면 계약 위반으로 본다.

    Args:
        frame: 날짜 오름차순 시세 (`data/loader.py` 가 검증해 돌려준 형태)
        entry_position: 진입일(만기일)의 위치 인덱스. 진입가는 이 날의 종가다
        exit_position: 청산일의 위치 인덱스. 진입 위치보다 뒤여야 한다
        bet_down: 아래로 거는 칸인지 여부. 참이면 원지수가 내려야 이익이다
        stop_level: 손절선 (비율, 0.05 = 5%). **`None` 이면 무손절**이며
            얼마나 밀려도 청산일까지 보유한다

    Returns:
        체결 결과

    Raises:
        ValueError: 청산 위치가 진입 위치보다 뒤가 아니거나 시세 범위를 벗어난 경우,
            손절선이 양수가 아닌 경우, 필요한 컬럼이 없거나 진입 위치가 범위 밖인 경우
        RuntimeError: 청산일까지 체결되지 않은 경우 (내부 불변조건 위반)
    """
    if not entry_position < exit_position < len(frame):
        raise ValueError(
            f"청산 위치는 진입 위치보다 뒤이면서 시세 범위 안이어야 합니다: " f"진입 {entry_position}, 청산 {exit_position} (시세 {len(frame)}행)"
        )

    hold_days = exit_position - entry_position

    if stop_level is None:
        return _scheduled_exit(frame, entry_position, exit_position, bet_down=bet_down, hold_days=hold_days)

    result = simulate_signal(
        frame,
        entry_position,
        upward=bet_down,
        hold_limit=hold_days,
        stop_level=stop_level,
        take_profit=False,
    )
    if result is None:
        raise RuntimeError(f"내부 불변조건 위반: 청산 위치를 검사했는데 체결이 비었습니다 - 진입 {entry_position}, 청산 {exit_position}")

    return result


def _scheduled_exit(
    frame: pd.DataFrame,
    entry_position: int,
    exit_position: int,
    *,
    bet_down: bool,
    hold_days: int,
) -> TradeResult:
    """무손절 체결 — 청산일 종가로만 계산한다.

    **손절 판정이 없으므로 시가도 장중도 보지 않는다.** 이 행은 손절 격자의 대조축이며,
    `.claude/rules/strategy.md` 가 「손절이 무엇을 막았는가」를 수치로 남기도록 요구한다.

    Args:
        frame: 시세
        entry_position: 진입일의 위치 인덱스
        exit_position: 청산일의 위치 인덱스
        bet_down: 아래로 거는 칸인지 여부
        hold_days: 보유 거래일 수

    Returns:
        청산일 종가로 나간 체결 결과
    """
    entry_price = float(frame.iloc[entry_position][COL_CLOSE])
    exit_price = float(frame.iloc[exit_position][COL_CLOSE])
    sign = -1.0 if bet_down else 1.0

    return TradeResult((exit_price / entry_price - 1.0) * sign, EXIT_LIMIT, hold_days)


__all__ = ["simulate_expiry_trade"]
