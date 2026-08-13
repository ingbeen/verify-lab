"""신호일 목록에 붙는 부가 컬럼 — 사건 번호와 참고용 z-score

둘 다 **판정이 아니라 해석 보조**다. 이벤트 판정은 순위와 연속 길이로만 하며, 여기의 값이
신호 집합을 바꾸지 않는다.

**사건 번호**는 표본이 서로 독립인지를 드러낸다. 한 달 안에 몰린 신호들은 같은 충격에서 파생된
것이라 독립 표본이 아니다. 신호를 버리지는 않되 "신호 N건 = 사건 M개"를 항상 병기해,
소수 사건이 승률을 부풀리고 있다는 사실이 숨지 않게 한다.

**참고용 z-score** 는 그날의 등락이 최근 변동성에 비해 얼마나 컸는지를 보여준다. 판정 기준이
아니라 결과를 읽을 때의 보조 정보다.
"""

import numpy as np
import pandas as pd

from verify_lab.studies.index_extreme.constants import EVENT_GAP_DAYS, ZSCORE_WINDOW
from verify_lab.studies.index_extreme.daily_change import daily_change_rate
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# z-score 를 내려면 표준편차가 필요하므로 창에 값이 최소 둘은 있어야 한다
MIN_ZSCORE_WINDOW = 2


def assign_event_ids(dates: pd.Series, gap_days: int = EVENT_GAP_DAYS) -> pd.Series:
    """붙어 있는 신호일에 같은 사건 번호를 매긴다.

    간격은 **바로 앞 신호**와 잰다. 따라서 창 이내로 계속 이어지면 사건 하나가 그만큼 길어진다 —
    2008년 금융위기처럼 충격이 한 달 넘게 연쇄하는 경우를 한 사건으로 보기 위해서다.

    **폭등과 폭락을 합친 목록을 넘긴다.** 같은 충격에서 나온 급락과 급반등이 별개 사건으로
    세어지면, 사건 단위 집계가 드러내려던 비독립성이 오히려 숨는다.

    Args:
        dates: 신호일 (날짜 오름차순). 방향을 합친 목록이다
        gap_days: 같은 사건으로 볼 최대 간격 (달력일, 1 이상)

    Returns:
        1부터 시작하는 사건 번호 (인덱스는 입력과 동일). 입력은 변경하지 않는다

    Raises:
        ValueError: 창이 1 미만인 경우, 날짜 Series 가 아닌 경우, 오름차순이 아닌 경우
    """
    if gap_days < 1:
        raise ValueError(f"사건 묶기 창은 1 이상이어야 합니다: {gap_days}")

    if not pd.api.types.is_datetime64_any_dtype(dates):
        raise ValueError(f"신호일은 날짜 Series 여야 합니다 (현재 dtype: {dates.dtype})")

    if not dates.is_monotonic_increasing:
        raise ValueError("신호일이 날짜 오름차순이 아닙니다")

    # 첫 신호는 앞이 없어 언제나 새 사건이 된다. 나머지는 앞 신호와의 간격으로 갈린다
    values = dates.to_numpy()
    starts = np.ones(len(values), dtype=bool)
    if len(values) > 1:
        starts[1:] = np.diff(values) / np.timedelta64(1, "D") > gap_days

    return pd.Series(np.cumsum(starts), index=dates.index).astype(int)


def reference_zscore(df: pd.DataFrame, window: int = ZSCORE_WINDOW) -> pd.Series:
    """당일 등락률이 직전 구간의 변동성에 비해 얼마나 컸는지 낸다.

    산식은 **당일 등락률 ÷ 직전 N거래일 등락률 표준편차**다. 평균을 빼지 않는 것은 재려는 것이
    중심으로부터의 거리가 아니라 **변동성 대비 크기**이기 때문이고, 판정일을 창에서 빼는 것은
    그날의 등락이 자기 기준선에 섞이지 않게 하기 위해서다.

    창이 차기 전과 직전 구간의 변동이 전혀 없는 날은 값을 비운다. 후자에서 0 으로 나누면
    무한대가 나오는데, 그것은 "계산 불가"이지 "극단적으로 큰 등락"이 아니다.

    Args:
        df: 날짜 오름차순 시세 (`data/loader.py` 가 검증해 돌려준 형태)
        window: 변동성을 재는 창 (거래일, 2 이상). 판정일은 포함하지 않는다

    Returns:
        z-score (인덱스는 입력 시세와 동일). 계산할 수 없는 날은 값이 없다.
        입력은 변경하지 않는다

    Raises:
        ValueError: 창이 2 미만인 경우, 시세가 비었거나 필수 컬럼이 없는 경우,
            날짜가 오름차순이 아닌 경우
    """
    if window < MIN_ZSCORE_WINDOW:
        raise ValueError(f"z-score 창은 {MIN_ZSCORE_WINDOW} 이상이어야 합니다: {window}")

    rates = daily_change_rate(df)

    # 한 칸 미룬 뒤 창을 잡으면 판정일이 자기 기준선에서 빠진다
    volatility = rates.shift(1).rolling(window=window).std()

    return rates / volatility.where(volatility > 0)
