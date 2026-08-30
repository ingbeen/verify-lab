"""일간 등락률 — 이벤트 정의가 공유하는 단일 산식

테스트 A(역대급 등락)의 순위 판정과 참고용 z-score 가 이 값을 쓴다.
**판정식 단일화** 원칙상 한 곳에만 둔다 — 같은 값을 두 곳에서 계산하면 두 곳이 조용히 갈라지고,
그때 어느 쪽이 맞는지 판별할 방법이 없다.

전일이 없는 첫 행은 값을 비운다. 0 으로 채우면 보합일로 읽혀 순위에 들어간다.
"""

import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE
from verify_lab.data.loader import validate_market_frame

# 계산에 필요한 시세 컬럼. 나머지 컬럼은 보지 않는다
REQUIRED_MARKET_COLUMNS = [COL_DATE, COL_CLOSE]


def daily_change_rate(df: pd.DataFrame) -> pd.Series:
    """전일 종가 대비 등락률을 낸다.

    날짜가 오름차순인지 먼저 확인한다. 뒤섞인 상태에서는 "전일"이 전일이 아니게 되어
    등락률이 예외 없이 조용히 어긋난다.

    Args:
        df: 날짜 오름차순 시세 (`data/loader.py` 가 검증해 돌려준 형태)

    Returns:
        비율 등락률 (0.03 = 3%). 인덱스는 입력과 같고 첫 행은 값이 없다.
        입력은 변경하지 않는다

    Raises:
        ValueError: 시세가 비었거나 필수 컬럼이 없는 경우, 날짜가 오름차순이 아닌 경우
    """
    validate_market_frame(df, REQUIRED_MARKET_COLUMNS)

    return df[COL_CLOSE].astype(float).pct_change()
