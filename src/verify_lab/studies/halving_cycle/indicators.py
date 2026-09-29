"""반감기_사이클 2단계 지표 — 가격 지표 넷과 온체인 지표 셋의 산식

| 지표 | 산식 | 근거 |
| --- | --- | --- |
| Pi Cycle 비율 | 111일 SMA ÷ (2 × 350일 SMA) — 1 을 넘는 날이 「교차」다 | 결정 ㉒ · 책 A 232 ~ 233쪽 |
| 100일 이격도 | 종가 ÷ 100일 SMA | 결정 ㉒ · ㉖ (값으로만 낸다) |
| 월간 RSI | 끝난 달의 말일 종가로 낸 Wilder RSI(14) | 결정 ㉒ |
| 월간 MACD − 시그널 | 말일 종가의 자연로그 · EMA 5 − EMA 15 · 그 EMA 9 와의 차이 | 결정 ㉕ |
| MVRV · NUPL | Coin Metrics MVRV 그대로 · `1 − 1/MVRV` | 결정 ⑧ |
| MVRV-Z | (시가총액 − 실현 시가총액) ÷ 그날까지의 시가총액 표본 표준편차 | 결정 ㉓ |

**SMA 는 `measure.baseline.simple_moving_average` 하나가 낸다** (측정의 원칙 15). **Wilder RSI 와 이격도는
중간선거_사이클(`studies/midterm_cycle/indicators.py`)과 같은 정의의 두 번째 사본이다** — 매매법끼리 가져다 쓸 수
없고, 원칙에 없는 것은 세 번째가 올 때 공유 계층으로 올린다(`src/verify_lab/CLAUDE.md` 「어디까지가 공통이고 …」,
2026-09-29 사용자 결정). 세 번째가 오면 두 사본을 함께 올린다.

**EMA 의 씨앗은 첫 값이다** — TradingView `ta.ema` 와 같다(책 차트가 TradingView 다). 값은 첫 달부터 계산하고
**창이 차기 전은 비운다** — 0 이나 첫 값으로 채우면 「그때 과열이었다」 같은 없는 사실이 된다.

**모두 그날(그달)까지의 값만 쓴다** (미래 참조 금지). MVRV-Z 의 표준편차를 전 기간으로 내면 미래 참조다.
"""

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE
from verify_lab.data.loader import validate_market_frame
from verify_lab.measure.baseline import simple_moving_average
from verify_lab.studies.halving_cycle.constants import (
    COL_DISPARITY,
    COL_MACD_HISTOGRAM,
    COL_MARKET_CAP,
    COL_MONTHLY_RSI,
    COL_MVRV,
    COL_MVRV_Z,
    COL_NUPL,
    COL_PI_CYCLE,
    DISPARITY_WINDOW,
    MACD_FAST_SPAN,
    MACD_SIGNAL_SPAN,
    MACD_SLOW_SPAN,
    MVRV_Z_MIN_DAYS,
    PI_CYCLE_LONG_MULTIPLIER,
    PI_CYCLE_LONG_WINDOW,
    PI_CYCLE_SHORT_WINDOW,
    RSI_WINDOW,
)

# 창의 하한. 하나면 평균이 그날 값 자신이고 표준편차가 정의되지 않는다
MIN_WINDOW = 2

# RSI 를 백분율 지수로 내는 배율. 비율이 아니라 0 ~ 100 이 관행이다
RSI_SCALE = 100.0


def _require_window(window: int, label: str) -> None:
    """창이 하한 이상인지 본다.

    Args:
        window: 창
        label: 메시지에 쓸 창의 이름

    Raises:
        ValueError: 창이 하한 미만인 경우
    """
    if window < MIN_WINDOW:
        raise ValueError(f"{label} 창은 {MIN_WINDOW} 이상이어야 합니다: {window}")


def pi_cycle_ratio(close: pd.Series, *, short_window: int, long_window: int, multiplier: float) -> pd.Series:
    """Pi Cycle 비율 — 짧은 SMA ÷ (배수 × 긴 SMA).

    Args:
        close: 날짜 오름차순 종가
        short_window: 짧은 SMA 창
        long_window: 긴 SMA 창 (짧은 창보다 길어야 한다)
        multiplier: 긴 SMA 에 곱하는 배수 (양수)

    Returns:
        입력과 인덱스가 같은 비율. 긴 창이 차기 전은 비어 있다

    Raises:
        ValueError: 창 순서가 뒤집혔거나 배수가 양수가 아닌 경우 (창의 하한은 `simple_moving_average` 가 본다)
    """
    if short_window >= long_window:
        raise ValueError(f"짧은 창이 긴 창보다 짧아야 합니다: {short_window} ≥ {long_window}")
    if multiplier <= 0:
        raise ValueError(f"배수는 양수여야 합니다: {multiplier}")

    return simple_moving_average(close, short_window) / (multiplier * simple_moving_average(close, long_window))


def disparity(close: pd.Series, window: int) -> pd.Series:
    """이격도 — 종가 ÷ SMA.

    Args:
        close: 날짜 오름차순 종가
        window: 이동평균 창

    Returns:
        입력과 인덱스가 같은 비율 (1.0 = 이동평균과 같음). 창이 차기 전은 비어 있다
    """
    return close.astype(float) / simple_moving_average(close, window)


def month_end_closes(frame: pd.DataFrame) -> pd.Series:
    """끝난 달마다 그 달 마지막 날의 종가를 낸다.

    **그 달의 말일이 데이터에 있는 달만** 쓴다 — 끝나지 않은 달의 마지막 종가는 그 달 종가가 아니다.
    비트코인은 휴장이 없어 마지막 거래일이 곧 말일이다. 달 중간에 시작한 첫 달은 남는다 — 그 달의 말일 종가는
    그대로 그 달 종가다.

    Args:
        frame: 날짜 오름차순 시세 (날짜 · 종가)

    Returns:
        말일 날짜를 인덱스로 하는 종가 Series

    Raises:
        ValueError: 시세가 비었거나 필요한 컬럼이 없거나 날짜가 오름차순이 아닌 경우
    """
    validate_market_frame(frame, [COL_DATE, COL_CLOSE])

    dates = pd.DatetimeIndex(frame[COL_DATE])
    is_month_end = np.asarray(dates.is_month_end)
    closes = frame.loc[is_month_end, COL_CLOSE].astype(float)

    return pd.Series(closes.to_numpy(), index=dates[is_month_end], name=COL_CLOSE)


def wilder_rsi(values: pd.Series, window: int) -> pd.Series:
    """Wilder 방식 RSI.

    `RSI = 100 × 평균 상승 ÷ (평균 상승 + 평균 하락)` 이며, 두 평균은 **첫 값만 단순평균이고 그 뒤는 Wilder
    평활**이다. 증권앱 · 차트가 보여 주는 값과 같은 산식이다. 등락이 전혀 없으면 분모가 0 이라 비운다.

    Args:
        values: 날짜 오름차순 값 계열
        window: RSI 창 (`MIN_WINDOW` 이상)

    Returns:
        입력과 인덱스가 같은 RSI (0 ~ 100). 앞 `window` 개는 비어 있다

    Raises:
        ValueError: 창이 하한 미만인 경우
    """
    _require_window(window, "RSI")

    changes = values.astype(float).diff().to_numpy()
    average_gain = _wilder_average(np.clip(changes, 0.0, None), window)
    average_loss = _wilder_average(np.clip(-changes, 0.0, None), window)
    total = average_gain + average_loss

    # 분모가 0 이거나 비어 있는 칸은 비운다. `where` 가 양쪽을 다 계산하므로 경고를 끈다
    with np.errstate(divide="ignore", invalid="ignore"):
        rsi = np.where(total > 0, RSI_SCALE * average_gain / total, np.nan)

    return pd.Series(rsi, index=values.index, dtype="float64")


def _wilder_average(changes: np.ndarray, window: int) -> np.ndarray:
    """Wilder 평활 평균. 첫 평균은 `1..window` 번째 변화의 단순평균이다 (0 번째 칸은 변화가 없다).

    Args:
        changes: 상승분 또는 하락분 (0 이상). 0 번째는 비어 있다
        window: 평균 창

    Returns:
        같은 길이의 평균. 앞 `window` 개는 비어 있다
    """
    result = np.full(len(changes), np.nan)
    if len(changes) <= window:
        return result

    average = float(np.mean(changes[1 : window + 1]))
    result[window] = average
    for position in range(window + 1, len(changes)):
        average = (average * (window - 1) + float(changes[position])) / window
        result[position] = average

    return result


def exponential_average(values: pd.Series, span: int) -> pd.Series:
    """지수이동평균 — `α × 오늘 + (1 − α) × 어제`, `α = 2 ÷ (창 + 1)`, **첫 값이 씨앗**이다.

    Args:
        values: 날짜 오름차순 값 계열 (빈 값 없음)
        span: 창

    Returns:
        입력과 인덱스가 같은 EMA. 첫 칸부터 값이 있다 — 창이 차기 전을 비우는 것은 부르는 쪽이 정한다

    Raises:
        ValueError: 창이 하한 미만이거나 입력에 빈 값이 있는 경우 — 빈 값을 건너뛰면 씨앗이 조용히 옮겨 간다
    """
    _require_window(span, "EMA")
    if values.isna().any():
        raise ValueError("EMA 입력에 빈 값이 있습니다")

    return values.astype(float).ewm(span=span, adjust=False).mean()


def log_macd_histogram(closes: pd.Series, *, fast_span: int, slow_span: int, signal_span: int) -> pd.Series:
    """로그 종가 MACD − 시그널.

    `MACD = EMA(log 종가, 빠른 창) − EMA(log 종가, 느린 창)`, `시그널 = EMA(MACD, 시그널 창)` 이다.
    **느린 창 + 시그널 창 − 2 개의 앞 칸은 비운다** — MACD 선은 느린 창이 찬 칸(느린 창 − 1 번째)부터,
    시그널은 거기서 MACD 값이 시그널 창만큼 모인 칸부터 뜻이 있다. 로그의 밑은 교차일을 바꾸지 않는다.

    Args:
        closes: 날짜 오름차순 종가 (양수)
        fast_span: 빠른 EMA 창
        slow_span: 느린 EMA 창 (빠른 창보다 길어야 한다)
        signal_span: 시그널 EMA 창

    Returns:
        입력과 인덱스가 같은 `MACD − 시그널`

    Raises:
        ValueError: 빠른 창이 느린 창보다 짧지 않거나, 종가가 양수가 아닌 경우
    """
    if fast_span >= slow_span:
        raise ValueError(f"빠른 창이 느린 창보다 짧아야 합니다: {fast_span} ≥ {slow_span}")
    if not (closes > 0).all():
        raise ValueError("로그를 씌울 종가가 양수가 아닙니다")

    logs = pd.Series(np.log(closes.astype(float).to_numpy()), index=closes.index)
    macd = exponential_average(logs, fast_span) - exponential_average(logs, slow_span)
    histogram = macd - exponential_average(macd, signal_span)

    warmup = slow_span + signal_span - 2
    histogram.iloc[:warmup] = np.nan

    return histogram


def mvrv_z(market_cap: pd.Series, mvrv: pd.Series, *, min_periods: int) -> pd.Series:
    """MVRV-Z — (시가총액 − 실현 시가총액) ÷ 그날까지의 시가총액 표본 표준편차.

    실현 시가총액은 `시가총액 ÷ MVRV` 다 (Coin Metrics 무료 목록에 실현 시가총액이 없다).
    **표준편차는 첫 날부터 그날까지다** (결정 ㉓) — 최소 기간은 첫 값의 날짜만 정한다.

    Args:
        market_cap: 날짜 오름차순 시가총액
        mvrv: 같은 날들의 MVRV (양수)
        min_periods: 표준편차를 내기 시작하는 최소 관측 수

    Returns:
        입력과 인덱스가 같은 MVRV-Z. 최소 기간 전은 비어 있다

    Raises:
        ValueError: 두 계열의 인덱스가 다르거나, 최소 기간이 하한 미만인 경우
    """
    if not market_cap.index.equals(mvrv.index):
        raise ValueError("시가총액과 MVRV 의 인덱스(날짜)가 다릅니다 — 다른 날의 값끼리 나누게 됩니다")
    _require_window(min_periods, "MVRV-Z 표준편차")

    cap = market_cap.astype(float)
    realized = cap / mvrv.astype(float)
    spread = cap.expanding(min_periods=min_periods).std(ddof=1)

    return (cap - realized) / spread


def nupl(mvrv: pd.Series) -> pd.Series:
    """NUPL = 1 − 1/MVRV. 0.75 는 MVRV 4 와 같다.

    Args:
        mvrv: MVRV 계열

    Returns:
        입력과 인덱스가 같은 NUPL
    """
    return 1.0 - 1.0 / mvrv.astype(float)


def daily_indicator_frame(prices: pd.DataFrame, onchain: pd.DataFrame) -> pd.DataFrame:
    """일간 지표 다섯을 확정된 창으로 한 번에 낸다 — **시세의 날짜 위에** 있다.

    **창을 호출부가 넘기지 않는다** — 신호와 진입지표가 다른 창을 쓰면 같은 이름의 지표가 두 표에서 다른 값이 된다.
    온체인 지표는 **온체인 계열 전체**(Coin Metrics 첫 날부터)로 계산한 뒤 시세의 날짜에 맞춘다 — MVRV-Z 의
    표준편차가 그 첫 날부터이기 때문이다. 온체인 값이 없는 날(공개 지연으로 시세보다 하루 짧을 수 있다)은 비운다.

    Args:
        prices: 날짜 오름차순 시세 (날짜 · 종가)
        onchain: 날짜 오름차순 온체인 계열 (날짜 · MVRV · 시가총액)

    Returns:
        시세 날짜를 인덱스로 하는 표 — Pi Cycle 비율 · 이격도 · MVRV · MVRV-Z · NUPL

    Raises:
        ValueError: 시세나 온체인 계열이 잘못된 경우
    """
    validate_market_frame(prices, [COL_DATE, COL_CLOSE])
    validate_market_frame(onchain, [COL_DATE, COL_MVRV, COL_MARKET_CAP])

    days = pd.DatetimeIndex(prices[COL_DATE])
    close = pd.Series(prices[COL_CLOSE].astype(float).to_numpy(), index=days)

    onchain_days = pd.DatetimeIndex(onchain[COL_DATE])
    mvrv = pd.Series(onchain[COL_MVRV].astype(float).to_numpy(), index=onchain_days)
    market_cap = pd.Series(onchain[COL_MARKET_CAP].astype(float).to_numpy(), index=onchain_days)

    onchain_values = pd.DataFrame(
        {
            COL_MVRV: mvrv,
            COL_MVRV_Z: mvrv_z(market_cap, mvrv, min_periods=MVRV_Z_MIN_DAYS),
            COL_NUPL: nupl(mvrv),
        }
    ).reindex(days)

    return pd.DataFrame(
        {
            COL_PI_CYCLE: pi_cycle_ratio(
                close,
                short_window=PI_CYCLE_SHORT_WINDOW,
                long_window=PI_CYCLE_LONG_WINDOW,
                multiplier=PI_CYCLE_LONG_MULTIPLIER,
            ),
            COL_DISPARITY: disparity(close, DISPARITY_WINDOW),
            COL_MVRV: onchain_values[COL_MVRV],
            COL_MVRV_Z: onchain_values[COL_MVRV_Z],
            COL_NUPL: onchain_values[COL_NUPL],
        },
        index=days,
    )


def monthly_indicator_frame(prices: pd.DataFrame) -> pd.DataFrame:
    """월간 지표 둘을 확정된 창으로 한 번에 낸다 — **끝난 달의 말일 위에** 있다.

    Args:
        prices: 날짜 오름차순 시세 (날짜 · 종가)

    Returns:
        말일을 인덱스로 하는 표 — 월말 종가 · 월간 RSI · 월간 MACD − 시그널
    """
    closes = month_end_closes(prices)

    return pd.DataFrame(
        {
            COL_CLOSE: closes,
            COL_MONTHLY_RSI: wilder_rsi(closes, RSI_WINDOW),
            COL_MACD_HISTOGRAM: log_macd_histogram(
                closes, fast_span=MACD_FAST_SPAN, slow_span=MACD_SLOW_SPAN, signal_span=MACD_SIGNAL_SPAN
            ),
        },
        index=closes.index,
    )


__all__ = [
    "daily_indicator_frame",
    "disparity",
    "exponential_average",
    "log_macd_histogram",
    "month_end_closes",
    "monthly_indicator_frame",
    "mvrv_z",
    "nupl",
    "pi_cycle_ratio",
    "wilder_rsi",
]
