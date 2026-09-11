"""체결 계산 — 매매법을 가리지 않는 공유 계층

진입 하나에 규칙을 적용해 **체결 결과 하나**를 낸다. 청산 방식이 둘이라 진입점도 둘이다.

| 진입점 | 언제 나가나 | 쓰는 매매법 |
| --- | --- | --- |
| `simulate_signal` | 이익이 나면 **그날** 청산하고, 손실이면 한도일까지 끈다 | 역방향 |
| `simulate_scheduled_trade` | **정해진 날**까지 들고 간다. 이익이어도 중간에 팔지 않는다 | 옵션 만기일 · 월말 |

**두 번째가 첫 번째를 `take_profit=False` 로 부른다.** 차이가 그 단계 하나뿐이므로 판정식을
두 벌 만들지 않는다.

**이 계층이 틀리는 방식은 판정 순서가 뒤바뀌는 것**이다. 시가·장중·종가를 이 순서로 보지
않으면 갭 하락한 날에 장중 손절가로 체결된 것처럼 계산되어 손실이 실제보다 작게 나온다.
그래서 순서를 함수 하나에 가두고 테스트로 고정한다.

**이 모듈에 매매법 이름을 두지 않는 이유**: 전에는 판정식이 `reverse_trading.py` 에, 달력 청산이
`expiry_trading.py` 에 있어 **월말이 옵션 만기일을 거쳐 역방향을 부르는 사슬**이었다. 그러면
공유 함수가 특정 매매법 파일의 소유가 되고, 그 매매법 사정으로 고칠 때 빌려 쓰는 쪽이 조용히
함께 바뀐다. `tests/test_layer_contracts.py` 가 사슬이 다시 생기지 않는지 검사한다.

**부호 규칙**: 아래로 거는 쪽(폭등 신호에 인버스 진입, 하락에 베팅)은 원지수 수익률에 −1 을
곱한 값이다. 이것은 원지수의 반대방향 수익률이지 **인버스 상품의 손익이 아니다** —
일간 복리·보수·롤 비용은 반영되지 않는다.
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
    """진입 하나의 체결 결과

    Attributes:
        return_rate: 체결 수익률 (비율). **거는 방향이 이미 반영된 실현 손익**이므로
            읽는 쪽이 부호를 다시 뒤집지 않는다 (`measure` 가 내는 원지수 수익률과 다르다)
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
    take_profit: bool = True,
) -> TradeResult | None:
    """신호일 하나에 매매 규칙을 적용해 체결 결과를 낸다.

    판정 순서는 **시가 → 장중 → 종가**이며, 위에서 걸리면 아래는 보지 않는다.

    1. 시가가 손절선 아래면 **그 시가로** 청산한다 (손절선보다 더 잃는다)
    2. 장중 최악이 손절선을 터치하면 **손절가로** 청산한다
    3. 종가가 진입가보다 위면 **그날 종가로** 청산한다 (`take_profit` 이 참일 때만)
    4. 손실이면 다음 날로 넘기고, 한도일에는 손실이어도 종가로 청산한다

    **손절선은 진입가 기준이며 보유 기간 내내 바뀌지 않는다.** 매일 갱신하면 손실이
    이어질 때 손절선이 따라 내려가 최악이 무제한으로 열린다.

    **3단계를 끄는 스위치가 있는 이유**는 청산이 달력 기준인 매매법이 이 판정식을 함께 쓰기
    때문이다. 옵션 만기일 매매는 다음 주 지정 요일에 파는 것이 정의라 중간 익절이 없고,
    월말 매매도 말일 기준으로 나간다 — 둘 다 이 모듈의 `simulate_scheduled_trade` 를 지난다.
    차이가 이 단계 하나뿐이므로 판정식을 두 벌 만들지 않는다 — 시가·장중 순서가 뒤바뀌면
    손실이 실제보다 작게 나오는 함정을 두 곳에서 관리하게 된다.

    Args:
        frame: 날짜 오름차순 시세 (`data/loader.py` 가 검증해 돌려준 형태)
        entry_position: 신호일의 위치 인덱스. 진입가는 이 날의 종가다
        upward: 상승 방향 신호(폭등)인지 여부. 참이면 인버스로 진입하므로 부호가 뒤집힌다
        hold_limit: 보유 한도 (거래일, 1 이상)
        stop_level: 손절선 (비율, 0.05 = 5%)
        take_profit: 종가가 진입가 위면 그날 청산할지 여부. 거짓이면 손절이 걸리지 않는 한
            **한도일까지 보유한다**

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

        # 3. 이익이면 그날 종가로 청산하고 끝낸다. 청산이 달력 기준인 매매법은 이 단계를 끈다
        if take_profit and close_rate > 0:
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


def simulate_scheduled_trade(
    frame: pd.DataFrame,
    entry_position: int,
    exit_position: int,
    *,
    bet_down: bool,
    stop_level: float | None,
    price_column: str = COL_CLOSE,
) -> TradeResult:
    """정해진 날까지 들고 가는 체결 — 손절만 중간에 걸린다.

    **보유 기간의 매일** 아래 순서로 보며, 위에서 걸리면 아래는 보지 않는다.
    손절은 청산일에만 재는 것이 아니라 **하루하루 감시한다.**

    1. 그날 시가가 손절선 아래면 **그 시가로** 청산한다 (손절선보다 더 잃는다)
    2. 그날 장중 최악이 손절선을 터치하면 **손절가로** 청산한다
    3. 어느 날에도 걸리지 않으면 **청산일 종가**로 나간다 — 이익이어도 중간에 팔지 않는다

    **손절선은 진입가 기준이며 보유 기간 내내 바뀌지 않는다.**

    **청산 위치는 호출 측이 정한다.** 달력이 지목한 날이 휴장이면 직전 거래일로 당기는 것도,
    목표일이 데이터 끝을 넘는 진입을 제외하는 것도 각 매매법의 일정 모듈이 한다
    (옵션 만기일은 `studies/option_expiry/weekly_exit.py`, 월말은
    `studies/month_end/schedule.py`). 여기까지 넘어온 진입은 이미 청산일이 확정된 것이므로,
    범위를 벗어나면 계약 위반으로 본다.

    Args:
        frame: 날짜 오름차순 시세 (`data/loader.py` 가 검증해 돌려준 형태)
        entry_position: 진입일의 위치 인덱스. 진입가는 이 날의 종가다
        exit_position: 청산일의 위치 인덱스. 진입 위치보다 뒤여야 한다
        bet_down: 아래로 거는 칸인지 여부. 참이면 원지수가 내려야 이익이다
        stop_level: 손절선 (비율, 0.05 = 5%). **`None` 이면 무손절**이며
            얼마나 밀려도 청산일까지 보유한다
        price_column: 가격 컬럼 이름. **지수는 종가 계열이라 이름이 다르다**
            (`storage/series/` 의 `Value`). 손절을 걸 때는 이 값을 바꿀 수 없다 —
            장중 판정에 시가·고가·저가가 필요한데 지수에는 없다

    Returns:
        체결 결과

    Raises:
        ValueError: 청산 위치가 진입 위치보다 뒤가 아니거나 시세 범위를 벗어난 경우,
            손절선이 양수가 아닌 경우, 필요한 컬럼이 없거나 진입 위치가 범위 밖인 경우,
            **종가가 아닌 가격 컬럼에 손절선을 건 경우**
        RuntimeError: 청산일까지 체결되지 않은 경우 (내부 불변조건 위반)
    """
    if not entry_position < exit_position < len(frame):
        raise ValueError(
            f"청산 위치는 진입 위치보다 뒤이면서 시세 범위 안이어야 합니다: " f"진입 {entry_position}, 청산 {exit_position} (시세 {len(frame)}행)"
        )

    hold_days = exit_position - entry_position

    if stop_level is None:
        return _scheduled_exit(
            frame, entry_position, exit_position, bet_down=bet_down, hold_days=hold_days, price_column=price_column
        )

    # 손절 경로는 시가·고가·저가를 읽으므로 시세 스키마에서만 성립한다. 조용히 종가로 재면
    # 장중에 밀린 손실을 못 보고 실제보다 손절이 덜 걸려 성적이 좋아진다
    if price_column != COL_CLOSE:
        raise ValueError(f"장중 손절은 시세 스키마에서만 잴 수 있습니다 (고가·저가가 필요합니다): 가격 컬럼 {price_column}")

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
    price_column: str,
) -> TradeResult:
    """무손절 체결 — 청산일 종가로만 계산한다.

    **손절 판정이 없으므로 시가도 장중도 보지 않는다.** 이 행은 손절 격자의 대조축이며,
    `.claude/rules/strategy.md` 가 「손절이 무엇을 막았는가」를 수치로 남기도록 요구한다.

    **종가 하나만 읽으므로 지수 계열도 이 경로로 지난다.** 지수는 시가·고가·저가가 없어
    손절 경로에 들어갈 수 없고, 그래서 무손절이 지수가 갈 수 있는 유일한 길이다.

    Args:
        frame: 시세 또는 지수 계열
        entry_position: 진입일의 위치 인덱스
        exit_position: 청산일의 위치 인덱스
        bet_down: 아래로 거는 칸인지 여부
        hold_days: 보유 거래일 수
        price_column: 가격 컬럼 이름

    Returns:
        청산일 종가로 나간 체결 결과
    """
    entry_price = float(frame.iloc[entry_position][price_column])
    exit_price = float(frame.iloc[exit_position][price_column])
    sign = -1.0 if bet_down else 1.0

    return TradeResult((exit_price / entry_price - 1.0) * sign, EXIT_LIMIT, hold_days)


__all__ = ["TradeResult", "simulate_scheduled_trade", "simulate_signal"]
