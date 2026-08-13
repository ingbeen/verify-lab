"""베이스라인 모집단 — 어떤 날을 비교군으로 삼을 것인가

수익률 절대값만으로는 "이 신호가 좋은가"에 답할 수 없다. 무엇과 비교하느냐가 답을 만든다.

이 모듈은 **조건부 베이스라인**의 모집단을 정한다 — "하락 국면 안에서도 이 날이 특별한가"에
답하기 위해, 종가가 200일 이동평균 아래인 날을 고른다. 단순 이동평균과 지수 이동평균을
모두 낼 수 있으며, 어느 쪽을 쓰느냐로 결론이 갈리면 그 자체가 강건성 문제다.

나머지 두 베이스라인은 별도 판정이 필요 없다. **단순 보유**는 전 거래일이 모집단이고,
**무작위 진입**은 그 모집단에서 신호 수만큼 반복 추출한 것이라 `statistics.permutation_test` 가
직접 수행한다. 세 베이스라인 모두 전 거래일 forward return 테이블 하나에서 파생되므로
수익률 산식은 `forward_return.py` 한 곳에만 있다.
"""

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE
from verify_lab.data.loader import validate_market_frame

# 이동평균 창 (거래일). docs/spec/index_extreme_events.md §5 가 확정한 값이다
DEFAULT_MA_WINDOW = 200

# 이동평균 판정에 필요한 시세 컬럼
REQUIRED_MARKET_COLUMNS = [COL_DATE, COL_CLOSE]


class MovingAverageKind(Enum):
    """이동평균 종류

    스펙 §7 결정 ⑦ 이 둘 다 산출하도록 확정했다. 어느 쪽을 쓰느냐로 결론이 갈리면
    그것이 곧 강건성 문제이므로, 하나를 골라 두지 않는다.

    Attributes:
        SMA: 단순 이동평균 — 창 안의 종가를 같은 무게로 평균낸다
        EMA: 지수 이동평균 — 최근 종가에 더 큰 무게를 준다
    """

    SMA = "sma"
    EMA = "ema"


@dataclass(frozen=True)
class BelowMovingAverage:
    """이동평균 아래인 날의 판정 결과

    Attributes:
        mask: 종가가 이동평균 아래인 날이 True 인 bool Series (인덱스는 입력 시세와 동일).
            창이 차기 전이라 판정하지 못한 날은 False 다 — 모집단에 넣지 않는다는 뜻이다
        undetermined_count: 창이 차지 않아 판정하지 못한 일수
    """

    mask: pd.Series
    undetermined_count: int


def below_moving_average(
    df: pd.DataFrame,
    window: int = DEFAULT_MA_WINDOW,
    kind: MovingAverageKind = MovingAverageKind.SMA,
) -> BelowMovingAverage:
    """종가가 이동평균 아래인 날을 고른다.

    이동평균은 판정일까지의 종가만 쓰므로 미래를 참조하지 않는다. 뒤에 데이터가 더 붙어도
    이미 지난 날의 판정은 달라지지 않는다.

    **창이 차기 전에는 판정하지 않는다.** 지수 이동평균은 첫날부터 값이 나오지만 초기값에
    끌려다녀 기준이 되지 못하고, 단순 이동평균과 판정 시작일이 달라지면 두 방식의 표본 수부터
    어긋나 비교가 성립하지 않는다. 판정하지 못한 일수는 함께 돌려준다 — 표본이 조용히
    줄어들면 안 된다.

    Args:
        df: 날짜 오름차순 시세 (`data/loader.py` 가 검증해 돌려준 형태)
        window: 이동평균 창 (거래일, 2 이상)
        kind: 이동평균 종류

    Returns:
        판정 마스크와 판정 불가 일수. 입력은 변경하지 않는다

    Raises:
        ValueError: 시세가 비었거나 필수 컬럼이 없는 경우, 날짜가 오름차순이 아닌 경우,
            창이 2 미만인 경우
    """
    if window < 2:
        raise ValueError(f"이동평균 창은 2 이상이어야 합니다: {window}")

    validate_market_frame(df, REQUIRED_MARKET_COLUMNS)

    close = df[COL_CLOSE].astype(float)

    if kind is MovingAverageKind.SMA:
        average = close.rolling(window=window).mean()
    else:
        average = close.ewm(span=window, adjust=False, min_periods=window).mean()

    undetermined = average.isna()
    mask = (close < average) & ~undetermined

    return BelowMovingAverage(mask=mask, undetermined_count=int(undetermined.sum()))
