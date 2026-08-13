"""테스트 A — 역대급 등락 (확장창 순위)

**판정 시점까지 누적된 데이터 기준으로** 일간 등락률이 역대 상위 K위 안에 드는 날을 신호로 본다.
순위는 시간이 지나며 계속 바뀐다. 판정 당시 1위였던 날이 나중에 3위가 될 수 있으며,
그 사실 자체가 신호일 목록의 "당시 순위" 컬럼으로 남는다.

**이 모듈은 이 프로젝트에서 look-ahead 가 가장 쉽게 섞이는 지점이다.** 전체 기간을 한 번에 보고
순위를 매기면 성과가 실제보다 좋아지고, 그 오류는 눈으로 발견되지 않는다.

집계 시작일을 함수가 직접 받는 것도 같은 이유다. 호출 측이 시세를 먼저 잘라 넘기면 순위가
그 지점부터 다시 쌓여 다른 결과가 나오는데, 예외가 나지 않아 알아차릴 수 없다.
**시작일 이전의 날은 신호로 세지 않되 순위 축적에는 넣는다.**
"""

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.studies.index_extreme.constants import DEFAULT_RANK_CUT, Direction
from verify_lab.studies.index_extreme.daily_change import daily_change_rate
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 순위 결과 스키마 (내부 계산용 영문 토큰)
COL_SURGE_RANK = "SurgeRank"
COL_PLUNGE_RANK = "PlungeRank"

RANK_COLUMNS = [COL_DATE, COL_SURGE_RANK, COL_PLUNGE_RANK]


def expanding_rank(df: pd.DataFrame) -> pd.DataFrame:
    """판정일까지의 등락률만으로 폭등·폭락 순위를 매긴다.

    순위는 **자기보다 극단인 날의 수 + 1** 이다. 따라서 등락률이 같은 날은 같은 순위를 받는다 —
    동률에 순번을 매기면 나중 날이 컷 밖으로 밀려 신호 수가 조용히 달라진다.

    첫 행은 전일이 없어 등락률이 없으므로 순위도 비운다.

    Args:
        df: 날짜 오름차순 시세 (`data/loader.py` 가 검증해 돌려준 형태)

    Returns:
        `RANK_COLUMNS` 순서의 순위표. 행 수와 순서는 입력과 같다.
        입력은 변경하지 않는다

    Raises:
        ValueError: 시세가 비었거나 필수 컬럼이 없는 경우, 날짜가 오름차순이 아닌 경우
    """
    rates = daily_change_rate(df).to_numpy(dtype=float)

    surge = np.full(len(rates), np.nan)
    plunge = np.full(len(rates), np.nan)

    # 판정일까지 누적된 구간만 본다. 첫 행은 등락률이 없어 순위 대상에서 빠지므로 1부터 센다
    for position in range(1, len(rates)):
        accumulated = rates[1 : position + 1]
        surge[position] = 1 + int((accumulated > rates[position]).sum())
        plunge[position] = 1 + int((accumulated < rates[position]).sum())

    return pd.DataFrame(
        {
            COL_DATE: df[COL_DATE].to_numpy(),
            COL_SURGE_RANK: surge,
            COL_PLUNGE_RANK: plunge,
        }
    )


def find_extreme_move_events(
    df: pd.DataFrame,
    *,
    direction: Direction,
    rank_cut: int = DEFAULT_RANK_CUT,
    start_date: pd.Timestamp | None = None,
) -> pd.Series:
    """판정 시점 순위가 컷 이내인 날을 신호로 고른다.

    **집계 시작일은 여기서 처리한다.** 호출 측이 시세를 먼저 자르면 순위 축적 구간을 잃어
    다른 결과가 나오지만 예외가 나지 않는다. 그 사고를 구조로 막는다.

    Args:
        df: 날짜 오름차순 시세 (`data/loader.py` 가 검증해 돌려준 형태)
        direction: 폭등(`UP`)인지 폭락(`DOWN`)인지
        rank_cut: 순위 컷 (1 이상). 이 순위 이내면 신호다
        start_date: 신호 집계를 시작할 날. `None` 이면 전 기간을 집계한다.
            이 날 이전은 신호로 세지 않되 순위 축적에는 들어간다

    Returns:
        신호인 날이 True 인 bool Series (인덱스는 입력 시세와 동일).
        입력은 변경하지 않는다

    Raises:
        ValueError: 순위 컷이 1 미만인 경우, 시세가 비었거나 필수 컬럼이 없는 경우,
            날짜가 오름차순이 아닌 경우
    """
    if rank_cut < 1:
        raise ValueError(f"순위 컷은 1 이상이어야 합니다: {rank_cut}")

    ranks = expanding_rank(df)
    column = COL_SURGE_RANK if direction is Direction.UP else COL_PLUNGE_RANK

    # 순위가 없는 첫 행은 비교 결과가 False 라 자연히 신호에서 빠진다
    selected = ranks[column].to_numpy(dtype=float) <= rank_cut

    if start_date is not None:
        selected &= (df[COL_DATE] >= start_date).to_numpy()

    period = start_date.date() if start_date is not None else "전 기간"
    logger.debug(f"역대급 등락 신호 {int(selected.sum()):,}건 (방향 {direction.value}, 컷 {rank_cut}위, 집계 시작 {period})")

    return pd.Series(selected, index=df.index)
