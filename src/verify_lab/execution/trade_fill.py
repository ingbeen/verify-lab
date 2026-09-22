"""체결 계산 — 매매법을 가리지 않는 공유 계층

진입 하나에 규칙을 적용해 **체결 결과 하나**를 낸다. 청산 방식이 둘이라 진입점도 둘이다.

| 진입점 | 언제 나가나 | 쓰는 매매법 |
| --- | --- | --- |
| `simulate_signal` | 이익이 나면 **그날** 청산하고, 손실이면 한도일까지 끈다 | 역방향 |
| `simulate_scheduled_trade` | **정해진 날**까지 들고 간다. 이익이어도 중간에 팔지 않는다 | 옵션 만기일 · 월말 |

**두 번째가 첫 번째를 `take_profit=False` 로 부른다.** 차이가 그 단계 하나뿐이므로 판정식을
두 벌 만들지 않는다.

**「어느 위치가 유효한가」도 이 모듈이 소유한다.** 두 진입점의 범위 검사와, 날짜를 거래일
위치로 바꾸는 `resolve_positions` 가 여기 함께 있다 — 매매법 네 곳이 그 변환을 각자 하면
찾지 못한 날짜(`-1`)를 거르는 검사도 네 벌이 되고, 한 곳만 빠져도 예외가 나지 않는다.

**이 계층이 틀리는 방식은 판정 순서가 뒤바뀌는 것**이다. 시가·장중·종가를 이 순서로 보지
않으면 갭 하락한 날에 장중 손절가로 체결된 것처럼 계산되어 손실이 실제보다 작게 나온다.
그래서 순서를 함수 하나에 가두고 테스트로 고정한다.

**이 모듈에 매매법 이름을 두지 않는 이유**: 판정식이나 달력 청산을 한 매매법 파일에 두면
**매매법이 서로를 부르는 사슬**이 생긴다(월말 → 옵션 만기일 → 역방향). 그러면 공유 함수가
특정 매매법 파일의 소유가 되고, 그 매매법 사정으로 고칠 때 빌려 쓰는 쪽이 조용히 함께 바뀐다.
`tests/test_layer_contracts.py` 가 그 사슬이 생기지 않는지 검사한다.

**부호 규칙**: 아래로 거는 쪽(폭등 신호에 인버스 진입, 하락에 베팅)은 원지수 수익률에 −1 을
곱한 값이다. 이것은 원지수의 반대방향 수익률이지 **인버스 상품의 손익이 아니다** —
일간 복리·보수·롤 비용은 반영되지 않는다.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_HIGH, COL_LOW, COL_OPEN
from verify_lab.execution.constants import (
    EXIT_GAP_STOP,
    EXIT_INTRADAY_STOP,
    EXIT_LIMIT,
    EXIT_PROFIT,
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
        worst_hold_rate: **보유 중** 가장 깊이 밀린 지점의 수익률 (비율).
            `return_rate` 가 「매도할 때 얼마였나」라면 이것은 「끌고 가는 동안 얼마까지
            밀렸나」다. **두 값이 크게 벌어지는 체결은 같은 성적이 아니다** — 청산가만
            −5% 로 같아도 중간에 −20% 를 견뎌야 했다면 회당 기대값 대비 감당할 손실이 다르다.
            **언제나 `return_rate` 보다 나쁘거나 같다** — 청산가는 보유 중에 실제로 지난
            가격이므로 이 구간의 최솟값이 그것을 넘어설 수 없다
    """

    return_rate: float
    reason: str
    hold_days: int
    worst_hold_rate: float


def resolve_positions(trading_days: pd.DatetimeIndex, dates: pd.DatetimeIndex, *, label: str) -> np.ndarray:
    """날짜를 거래일 위치로 바꾼다. 찾지 못한 날짜가 하나라도 있으면 멈춘다.

    `pandas.Index.get_indexer` 는 찾지 못한 날짜에 **`-1`** 을 돌려준다. 검사하지 않으면 그 값이
    `simulate_scheduled_trade` 로 흘러가고, 무손절 경로에서는 `iloc` 가 뒤에서 세어
    **마지막 행을 진입가로** 잡는다 — 예외 없이 체결 하나가 만들어진다.

    **`RuntimeError` 인 이유**: 매매 계층은 진입일·청산일을 `trading_days` 자신에서 만든다
    (`month_end_runner` 는 `month_exit_schedule` 을 지난 날짜를, `option_expiry_runner` 는
    스스로 읽은 시세의 날짜를 쓴다). 따라서 `-1` 은 잘못된 입력이 아니라 **일정 모듈의 버그**로만
    생긴다. 같은 사고를 날짜 목록을 **파라미터로 받는** `studies/` 세 곳
    (`measure/calendar_entry.py` · `measure/calendar_exit.py` · `option_expiry/offsets.py`)은
    `ValueError` 로 던진다 — 거기서는 외부에서 잘못된 값이 올 수 있다. **메시지 본문은 맞춘다.**

    Args:
        trading_days: 거래일 목록
        dates: 위치를 구할 날짜
        label: 메시지에 쓸 날짜의 이름 (예: `진입일`). 진입일이 없는 것과 청산일이 없는 것은
            원인이 다르므로 한 문구로 합치지 않는다

    Returns:
        거래일 위치 배열

    Raises:
        RuntimeError: 거래일 목록에 없는 날짜가 있는 경우 (내부 불변조건 위반)
    """
    positions = np.asarray(trading_days.get_indexer(dates), dtype=np.int64)

    # 빈 배열에서 `min()` 은 예외를 내므로 길이를 먼저 본다. 진입이 하나도 없는 달은 정상이다
    if len(positions) and positions.min() < 0:
        missing = dates[positions < 0]
        raise RuntimeError(f"내부 불변조건 위반: {label}이 거래일 목록에 없습니다: {[day.date().isoformat() for day in missing]}")

    return positions


def simulate_signal(
    frame: pd.DataFrame,
    entry_position: int,
    *,
    upward: bool,
    hold_limit: int,
    stop_level: float | None,
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
        stop_level: 손절선 (비율, 0.05 = 5%). **`None` 이면 무손절**이며 1·2 단계를 건너뛴다 —
            `.claude/rules/trading.md` 가 「손절이 무엇을 막았는가」의 대조축으로 무손절 성적을
            요구하므로, 그것을 낼 수 없으면 규칙을 코드로 재현할 방법이 없다.
            달력형 진입점(`simulate_scheduled_trade`)이 이미 `None` 을 받으므로 **두 진입점의
            손절선 타입을 맞춘다** — 한쪽만 받으면 같은 격자를 매매법마다 다르게 내게 된다.
            **기본값을 두지 않는다** — 이 모듈은 매매법 이름을 갖지 않는 공유 체결식인데
            기본값이 있으면 그것이 **한 매매법의 파라미터**가 된다. 실제로 역방향의 −5% 가
            기본값이었고, 인자를 빠뜨린 호출은 **예외 없이 남의 손절선으로 체결**된다.
            `measure.screening.screen_verdict` 의 `tradable` 과
            `constants.stop_level_value` 의 `measurable` 이 같은 이유로 기본값을 두지 않는다
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

    # 아래로 걸면 고가가, 위로 걸면 저가가 손실 쪽이다. 이 진입점은 시세 스키마 전용이라
    # 장중을 언제나 잴 수 있다 — `_validate` 가 네 컬럼을 요구한다
    column = COL_HIGH if upward else COL_LOW

    for day in range(1, hold_limit + 1):
        position = entry_position + day
        if position >= len(frame):
            # 측정 구간이 데이터를 넘어갔다. 부분 체결을 남기면 표본이 조용히 섞인다
            return None

        row = frame.iloc[position]
        close_rate = _rate(float(row[COL_CLOSE]), entry_price, sign)

        # **무손절이면 1·2 단계를 건너뛴다.** 시가·고가·저가를 읽지 않지만 `_validate` 는
        # 그 컬럼을 그대로 요구한다 — 이 진입점은 시세 스키마 전용이고, 종가 하나짜리 계열은
        # 달력형 진입점(`simulate_scheduled_trade`)이 `price_column` 으로 받는다
        if stop_level is not None:
            open_rate = _rate(float(row[COL_OPEN]), entry_price, sign)
            worst_rate = _rate(float(row[COL_HIGH] if upward else row[COL_LOW]), entry_price, sign)

            # 1. 시가가 이미 손절선 아래면 그 시가가 체결가다 — 손절선을 지켜주지 못한다
            if open_rate <= -stop_level:
                # **보유 중 최악이 곧 체결가다.** 그 순간 포지션이 끝났으므로 그날 더 빠진 것은
                # 나온 뒤의 일이고, 그 전날까지는 전부 손절선 위였다 (아니면 거기서 끊겼다)
                return TradeResult(open_rate, EXIT_GAP_STOP, day, open_rate)

            # 2. 장중에 손절선을 터치하면 손절가에 체결된다
            if worst_rate <= -stop_level:
                return TradeResult(-stop_level, EXIT_INTRADAY_STOP, day, -stop_level)

        # 3. 이익이면 그날 종가로 청산하고 끝낸다. 청산이 달력 기준인 매매법은 이 단계를 끈다
        if take_profit and close_rate > 0:
            worst = _worst_hold_rate(frame, entry_position, position, entry_price=entry_price, sign=sign, column=column)
            return TradeResult(close_rate, EXIT_PROFIT, day, worst)

        # 4. 한도일에는 손실이어도 청산한다
        if day == hold_limit:
            worst = _worst_hold_rate(frame, entry_position, position, entry_price=entry_price, sign=sign, column=column)
            return TradeResult(close_rate, EXIT_LIMIT, day, worst)

    raise RuntimeError(f"내부 불변조건 위반: 한도 안에서 청산되지 않았습니다 - 한도 {hold_limit}")


def _worst_hold_rate(
    frame: pd.DataFrame,
    entry_position: int,
    exit_position: int,
    *,
    entry_price: float,
    sign: float,
    column: str,
) -> float:
    """청산 봉을 끝까지 들고 있었을 때, 보유 중 가장 깊이 밀린 지점의 수익률을 낸다.

    **손절로 나간 체결은 이 함수를 거치지 않는다.** 손절이 발동한 순간 포지션이 끝나므로
    그때의 보유 중 최악은 **체결가 그 자체**이고, 부르는 쪽이 그 값을 그대로 싣는다.
    여기서 계산해도 같은 값이 나오지만(손절 전날까지는 전부 손절선 위였다) **그 동치는
    판정 순서에 기대는 것이라**, 계산하지 않고 부르는 쪽이 사실을 적는 편이 읽힌다.

    **구간은 진입 «다음» 거래일부터 청산일까지다.** 진입가가 진입일 종가이므로 그날 장중은
    이미 지나간 시간이다 — 세면 사지도 않은 구간의 손실이 성적에 실린다.

    **아래로 거는 칸은 고가가 최악이다.** 주가가 오를 때 잃기 때문이며, 저가를 보면
    「가장 많이 번 지점」을 최악이라고 적게 된다. **어느 컬럼을 볼지는 부르는 쪽이 정한다** —
    종가 하나뿐인 지수는 고를 것이 없고, 그 사실을 아는 것은 대상을 든 쪽이다.

    **양수가 나올 수 있다.** 보유 내내 진입가 위였다는 뜻이며 0 으로 깎지 않는다 —
    깎으면 「한 번은 본전까지 내려왔다」는 없는 사실을 만든다.

    Args:
        frame: 날짜 오름차순 시세 또는 종가 계열
        entry_position: 진입일의 위치 인덱스
        exit_position: 청산일의 위치 인덱스. 진입 위치보다 뒤여야 한다
        entry_price: 진입가. **부르는 쪽이 체결에 쓴 값을 그대로 넘긴다** — 여기서 다시 읽으면
            수익률과 보유 중 최악이 다른 분모로 계산될 수 있고, 그래도 「보유 중 최악 <= 수익률」은
            성립해 **틀린 값이 모든 검사를 통과한다**
        sign: 상승 방향 신호(아래로 건다)면 -1, 아니면 1
        column: 최악을 읽을 가격 컬럼. 장중을 잴 수 있으면 고가·저가, 종가 계열이면 그 컬럼이다

    Returns:
        보유 중 최악의 수익률 (비율). 거는 방향이 이미 반영돼 있다

    Raises:
        ValueError: 구간 안에 0 이하 가격이 있는 경우. **계열 로더는 값의 부호를 보지 않으므로**
            (마이너스 금리가 실재한다) 진입가·청산가 검사만으로는 «구간 안»이 막히지 않는다 —
            그대로 두면 0 하나가 조용히 −100% 짜리 보유 중 최악을 만들어 그 칸의 최솟값이 된다
    """
    window = frame.iloc[entry_position + 1 : exit_position + 1]
    extreme = float(window[column].max() if sign < 0 else window[column].min())

    # 아래로 거는 칸은 «최대»를 보므로 0 이하가 있어도 이 값에 안 잡힌다. 따로 센다
    if extreme <= 0 or float(window[column].min()) <= 0:
        raise ValueError(
            f"보유 구간에 0 이하 가격이 있습니다: {float(window[column].min())} "
            f"(컬럼 {column}, 진입 {entry_position}, 청산 {exit_position})"
        )

    return _rate(extreme, entry_price, sign)


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
    stop_level: float | None,
) -> None:
    """입력을 즉시 검사한다.

    Args:
        frame: 시세
        entry_position: 신호일의 위치 인덱스
        hold_limit: 보유 한도
        stop_level: 손절선. `None` 이면 무손절이라 부호 검사를 건너뛴다

    Raises:
        ValueError: 값이 유효하지 않은 경우
    """
    missing_columns = set(REQUIRED_MARKET_COLUMNS) - set(frame.columns)
    if missing_columns:
        raise ValueError(f"시세에 필수 컬럼이 없습니다: {sorted(missing_columns)}")

    if hold_limit < 1:
        raise ValueError(f"보유 한도는 1 이상이어야 합니다: {hold_limit}")

    # **`0` 을 무손절로 읽지 않는다.** 무손절은 `None` 이고 `0` 은 「진입가에 닿으면 손절」이라
    # 뜻이 다르다 — 한 값이 둘을 겸하면 성적표의 `손절선(%)` 이 어느 쪽인지 구별되지 않는다
    if stop_level is not None and stop_level <= 0:
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
    (`measure/calendar_entry.py` 와 `measure/calendar_exit.py` — 세 매매법이 공유한다).
    여기까지 넘어온 진입은 이미 청산일이 확정된 것이므로,
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
            장중 판정에 시가·고가·저가가 필요한데 지수에는 없다.
            **보유 중 최악의 기준도 이 값이 정한다** — 종가가 아니면 장중을 잴 수 없으므로
            그 컬럼 하나로 재며, 그 값은 실제 낙폭보다 **얕다.** 어느 기준으로 잰 행인지는
            `손절선(%)` 의 `손절불가` 표기가 말한다. **별도 인자를 두지 않는 것은 같은 사실을
            두 곳에서 말하게 되기 때문이다** — 둘이 어긋나면 한쪽은 조용히 틀린다

    Returns:
        체결 결과

    Raises:
        ValueError: **진입 위치가 음수인 경우**, 청산 위치가 진입 위치보다 뒤가 아니거나
            시세 범위를 벗어난 경우, 손절선이 양수가 아닌 경우,
            **종가가 아닌 가격 컬럼에 손절선을 건 경우**,
            보유 구간에 0 이하 가격이 있는 경우,
            손절 경로에서 시세 컬럼이 없는 경우. **무손절 경로는 가격 컬럼 하나만 읽으므로
            그 컬럼이 없으면 `KeyError` 다** — 시세 스키마 전체를 요구하지 않는다
        RuntimeError: 청산일까지 체결되지 않은 경우 (내부 불변조건 위반)
    """
    # **하한을 여기 두는 이유**: 무손절 경로(`_scheduled_exit`)는 `iloc` 만 쓰므로 음수 위치가
    # 예외 없이 **마지막 행**을 진입가로 만든다. 손절 경로는 `simulate_signal._validate` 의
    # `0 <= entry_position` 에 걸려 살아나므로, 하한이 없으면 두 경로의 가드 강도가 정반대가 된다.
    # 그리고 **지수 대상은 고가·저가가 없어 무손절 경로만 지난다** — 약한 쪽이 하필 상시 경로다
    if not 0 <= entry_position < exit_position < len(frame):
        raise ValueError(
            f"진입 위치는 0 이상이고 청산 위치는 그보다 뒤이면서 시세 범위 안이어야 합니다: "
            f"진입 {entry_position}, 청산 {exit_position} (시세 {len(frame)}행)"
        )

    hold_days = exit_position - entry_position

    if stop_level is None:
        return _scheduled_exit(
            frame,
            entry_position,
            exit_position,
            bet_down=bet_down,
            hold_days=hold_days,
            price_column=price_column,
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
    """무손절 체결 — 청산일 종가로 계산하고, 보유 중 최악은 따로 잰다.

    **손절 판정이 없으므로 시가도 장중도 «체결»에는 쓰지 않는다.** 이 행은 손절 격자의
    대조축이며, `.claude/rules/trading.md` 가 「손절이 무엇을 막았는가」를 수치로 남기도록
    요구한다.

    **그 대조는 보유 중 최악에서도 성립해야 하므로 그 값은 장중으로 잰다.** 결과만 놓고
    비교하면 「손절이 막아 준 몫」이 청산가 차이로만 보이고, **얼마나 밀렸다가 돌아왔는지**가
    무손절 행에서 사라진다.

    **체결은 가격 컬럼 하나만 읽으므로 지수 계열도 이 경로로 지난다.** 지수는 시가·고가·저가가
    없어 손절 경로에 들어갈 수 없고, 그래서 무손절이 지수가 갈 수 있는 유일한 길이다 —
    그때는 보유 중 최악도 같은 컬럼으로 잰다. **기준을 가르는 것은 `price_column` 하나다.**

    Args:
        frame: 시세 또는 지수 계열
        entry_position: 진입일의 위치 인덱스
        exit_position: 청산일의 위치 인덱스
        bet_down: 아래로 거는 칸인지 여부
        hold_days: 보유 거래일 수
        price_column: 가격 컬럼 이름. **보유 중 최악의 기준도 이 값이 정한다** —
            종가면 장중 고가·저가로, 계열이면 그 컬럼 하나로 잰다

    Returns:
        청산일 종가로 나간 체결 결과

    Raises:
        ValueError: 진입가·청산가가 0 이하이거나, **보유 구간 안에** 0 이하 가격이 있는 경우
    """
    entry_price = float(frame.iloc[entry_position][price_column])
    exit_price = float(frame.iloc[exit_position][price_column])
    sign = -1.0 if bet_down else 1.0

    # **여기서 막는 이유**: 시세 로더는 「0 이하 가격」을 거부하지만 **계열 로더는 값의 부호를
    # 보지 않는다** — 마이너스 금리와 0% 금리가 실재하기 때문이며 그 판정은 옳다. 그런데
    # 월말 매매가 지수 계열을 이 경로로 넘기고 여기서 그 값이 수익률이 된다.
    #
    # **둘 다 막는다.** 진입가는 분모라 `ZeroDivisionError` 로 터지지만, **청산가는 조용하다** —
    # 0 이면 예외 없이 `-100%` 짜리 체결이 만들어져 합계·평균·최악에 그대로 섞인다
    for label, price in (("진입가", entry_price), ("청산가", exit_price)):
        if price <= 0:
            raise ValueError(f"{label}가 0 이하입니다: {price} (컬럼 {price_column}, 진입 {entry_position}, 청산 {exit_position})")

    # **장중을 잴 수 있는지는 가격 컬럼이 말한다.** 종가 계열(지수)에는 고가·저가가 없으므로
    # 그 컬럼 하나로 재며, 그 값은 실제 낙폭보다 얕다 — 같은 조건이 위 손절 경로의 가드다.
    #
    # **이 경로는 손절이 없으므로 청산 봉을 언제나 끝까지 들고 있었다** — 그 봉의 장중까지 센다.
    # 구간 안의 0 이하 가격은 `_worst_hold_rate` 가 거부한다 (진입가·청산가 검사는 양 끝만 본다)
    intraday = price_column == COL_CLOSE
    column = (COL_HIGH if bet_down else COL_LOW) if intraday else price_column

    worst_hold = _worst_hold_rate(
        frame,
        entry_position,
        exit_position,
        entry_price=entry_price,
        sign=sign,
        column=column,
    )

    return TradeResult((exit_price / entry_price - 1.0) * sign, EXIT_LIMIT, hold_days, worst_hold)


__all__ = ["TradeResult", "resolve_positions", "simulate_scheduled_trade", "simulate_signal"]
