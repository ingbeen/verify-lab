"""진입 위치와 분할매수 조건에 쓰는 지표 — RSI · 이격도 · 52주 최고 대비

**두 표가 같은 값을 본다.** `진입위치.csv` 는 진입일의 지표를 결과와 나란히 싣고, 분할매수
C 방식은 같은 지표가 기준 아래로 들어가는 날에 산다 — 지표를 표마다 계산하면 같은 날의 값이
두 표에서 갈린다.

| 지표 | 산식 | 소유자 |
| --- | --- | --- |
| 이격도 | 종가 ÷ SMA | **SMA 는 `measure.baseline.simple_moving_average`** (측정의 원칙 15) |
| RSI | Wilder — 첫 평균은 단순평균, 그 뒤는 `(직전 × (N−1) + 오늘) ÷ N` | 이 모듈 |
| 52주 최고 대비 | 종가 ÷ (그날 포함 N거래일 최고 종가) − 1 | 이 모듈 |

**RSI 와 52주 최고는 측정의 원칙에 없어 이 매매법에 둔다** — 공통 계층은 세 번째가 올 때 정한다.

**셋 다 그날까지의 값만 쓴다** (미래 참조 금지). 창이 차기 전은 비운다 — 0 이나 첫 값으로
채우면 「그때 고점이었다」 같은 없는 사실이 된다.
"""

import numpy as np
import pandas as pd

from verify_lab.measure.baseline import simple_moving_average
from verify_lab.studies.midterm_cycle.constants import (
    COL_DISPARITY_LONG,
    COL_DISPARITY_SHORT,
    COL_HIGH_DISTANCE,
    COL_RSI,
    HIGH_LOOKBACK_DAYS,
    LONG_MA_WINDOW,
    RSI_WINDOW,
    SHORT_MA_WINDOW,
)

# 지표 창의 하한. 하나면 RSI 평균이 그날 값 자신이고, 고점 대비는 언제나 0 이라 정보가 없다
MIN_INDICATOR_WINDOW = 2

# RSI 를 백분율 지수로 내는 배율. 비율이 아니라 0~100 이 관행이다
RSI_SCALE = 100.0


def wilder_rsi(values: pd.Series, window: int) -> pd.Series:
    """Wilder 방식 RSI 를 낸다.

    `RSI = 100 × 평균 상승 ÷ (평균 상승 + 평균 하락)` 이며, 두 평균은 **첫 값만 단순평균이고
    그 뒤는 Wilder 평활**이다. 증권앱·차트가 보여 주는 값과 같은 산식이다.

    **등락이 전혀 없으면 비운다** — 분모가 0 이라 정의되지 않고, 50 이나 100 으로 채우면
    없는 과열·과매도가 생긴다. 하락이 한 번도 없으면 100 이다.

    Args:
        values: 날짜 오름차순 값 계열
        window: RSI 창 (`MIN_INDICATOR_WINDOW` 이상)

    Returns:
        입력과 인덱스가 같은 RSI (0~100). 앞 `window` 개는 비어 있다

    Raises:
        ValueError: 창이 하한 미만인 경우
    """
    if window < MIN_INDICATOR_WINDOW:
        raise ValueError(f"RSI 창은 {MIN_INDICATOR_WINDOW} 이상이어야 합니다: {window}")

    changes = values.astype(float).diff().to_numpy()
    average_gain = _wilder_average(np.clip(changes, 0.0, None), window)
    average_loss = _wilder_average(np.clip(-changes, 0.0, None), window)
    total = average_gain + average_loss

    # 분모가 0 이거나 비어 있는 칸은 비운다. `where` 가 양쪽을 다 계산하므로 경고를 끈다
    with np.errstate(divide="ignore", invalid="ignore"):
        rsi = np.where(total > 0, RSI_SCALE * average_gain / total, np.nan)

    return pd.Series(rsi, index=values.index, dtype="float64")


def disparity(values: pd.Series, window: int) -> pd.Series:
    """이격도 — 값 ÷ 단순 이동평균.

    Args:
        values: 날짜 오름차순 값 계열
        window: 이동평균 창

    Returns:
        입력과 인덱스가 같은 비율 (1.0 = 이동평균과 같음). 창이 차기 전은 비어 있다

    Raises:
        ValueError: 창이 이동평균 하한 미만인 경우 (`simple_moving_average` 가 던진다)
    """
    return values.astype(float) / simple_moving_average(values, window)


def distance_from_high(values: pd.Series, window: int) -> pd.Series:
    """그날을 포함한 직전 `window` 개 값의 최고치 대비 거리.

    Args:
        values: 날짜 오름차순 값 계열
        window: 최고치를 찾을 창 (`MIN_INDICATOR_WINDOW` 이상)

    Returns:
        입력과 인덱스가 같은 비율 (0 = 그날이 창의 최고치, 음수 = 그만큼 아래).
        창이 차기 전은 비어 있다

    Raises:
        ValueError: 창이 하한 미만인 경우
    """
    if window < MIN_INDICATOR_WINDOW:
        raise ValueError(f"최고치 창은 {MIN_INDICATOR_WINDOW} 이상이어야 합니다: {window}")

    series = values.astype(float)
    return series / series.rolling(window=window).max() - 1.0


def indicator_frame(frame: pd.DataFrame, *, price_column: str) -> pd.DataFrame:
    """한 대상의 지표 넷을 확정된 창으로 한 번에 낸다.

    **창을 호출부가 넘기지 않는다** — 진입위치 표와 분할매수가 다른 창을 쓰면 같은 이름의
    지표가 두 표에서 다른 값이 된다.

    Args:
        frame: 날짜 오름차순 가격 데이터
        price_column: 가격 컬럼 이름. ETF 는 종가, 지수는 `Value` 다

    Returns:
        입력과 인덱스가 같은 표 — `COL_RSI` · `COL_DISPARITY_SHORT` · `COL_DISPARITY_LONG` ·
        `COL_HIGH_DISTANCE`. 입력은 변경하지 않는다
    """
    values = frame[price_column].astype(float)

    return pd.DataFrame(
        {
            COL_RSI: wilder_rsi(values, RSI_WINDOW),
            COL_DISPARITY_SHORT: disparity(values, SHORT_MA_WINDOW),
            COL_DISPARITY_LONG: disparity(values, LONG_MA_WINDOW),
            COL_HIGH_DISTANCE: distance_from_high(values, HIGH_LOOKBACK_DAYS),
        },
        index=frame.index,
    )


def _wilder_average(changes: np.ndarray, window: int) -> np.ndarray:
    """Wilder 평활 평균. 첫 평균은 `1..window` 번째 변화의 단순평균이다.

    **0 번째 칸(첫 변화가 없는 날)은 쓰지 않는다** — 변화는 둘째 날부터 있다.

    Args:
        changes: 날마다의 상승분 또는 하락분 (0 이상). 0 번째는 비어 있다
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


__all__ = ["disparity", "distance_from_high", "indicator_frame", "wilder_rsi"]
