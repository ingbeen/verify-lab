"""테스트 B — 연속 등락

신호일은 **N일 연속 상승 또는 하락이 달성된 그날**이다. 그날 종가로 판정이 끝나고 다음 날
시가에 집행할 수 있다.

"연속 구간의 마지막 날"은 채택하지 않는다. 그날이 마지막인지는 **다음 날 주가를 봐야** 알 수
있어 미래 참조가 되고, 그 정의로 낸 결과는 실제 매매에 쓸 수 없다.

**연속 길이가 정확히 N 인 날만 신호다.** 5일 연속 랠리는 N=3 신호를 3일째에만 만든다.
같은 랠리가 N 마다 신호를 하나씩 만들므로 N 별 결과는 서로 독립이 아니며, 그 사실을 결과
문서에 함께 적는다.

**등락률이 정확히 0인 날은 연속을 끊되 방향을 부여하지 않는다.** 상승으로 간주하거나 무시하고
이어가면 어느 쪽이든 임의성이 생기므로 가장 보수적인 처리를 택한다.
"""

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.studies.index_extreme.constants import Direction
from verify_lab.studies.index_extreme.daily_change import daily_change_rate
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 연속으로 인정하는 최소 일수. 1일은 연속이 아니라 그냥 상승일·하락일이다
MIN_CONSECUTIVE_LENGTH = 2


def signed_run_length(df: pd.DataFrame) -> pd.Series:
    """당일까지 이어진 연속 일수에 방향 부호를 붙여 돌려준다.

    +3 은 3일 연속 상승, −3 은 3일 연속 하락이다. 방향이 없는 날(첫 행과 보합일)은 0 이며,
    그 날을 지나면 연속이 1부터 다시 시작한다.

    Args:
        df: 날짜 오름차순 시세 (`data/loader.py` 가 검증해 돌려준 형태)

    Returns:
        부호 있는 연속 길이 (인덱스는 입력 시세와 동일). 입력은 변경하지 않는다

    Raises:
        ValueError: 시세가 비었거나 필수 컬럼이 없는 경우, 날짜가 오름차순이 아닌 경우
    """
    rates = daily_change_rate(df).to_numpy(dtype=float)

    # 등락률이 없는 첫 행과 보합일을 같은 0 으로 둔다. 둘 다 방향이 없는 날이다
    directions = np.sign(np.nan_to_num(rates, nan=0.0)).astype(int)

    lengths = np.zeros(len(rates), dtype=int)
    for position in range(1, len(rates)):
        if directions[position] == 0:
            continue

        # 방향이 이어지면 부호를 유지한 채 한 칸 늘리고, 바뀌면 그 방향으로 다시 시작한다
        if directions[position] == directions[position - 1]:
            lengths[position] = lengths[position - 1] + directions[position]
        else:
            lengths[position] = directions[position]

    return pd.Series(lengths, index=df.index)


def find_consecutive_events(
    df: pd.DataFrame,
    *,
    direction: Direction,
    length: int,
    start_date: pd.Timestamp | None = None,
) -> pd.Series:
    """N일 연속이 달성된 그날을 신호로 고른다.

    **집계 시작일은 여기서 처리한다.** 호출 측이 시세를 먼저 자르면 걸쳐 있던 연속이 끊겨
    다른 결과가 나오지만 예외가 나지 않는다.

    Args:
        df: 날짜 오름차순 시세 (`data/loader.py` 가 검증해 돌려준 형태)
        direction: 연속 상승(`UP`)인지 연속 하락(`DOWN`)인지
        length: 연속 일수 (2 이상)
        start_date: 신호 집계를 시작할 날. `None` 이면 전 기간을 집계한다.
            이 날 이전은 신호로 세지 않되 연속 길이 누적에는 들어간다

    Returns:
        신호인 날이 True 인 bool Series (인덱스는 입력 시세와 동일).
        입력은 변경하지 않는다

    Raises:
        ValueError: 연속 일수가 2 미만인 경우, 시세가 비었거나 필수 컬럼이 없는 경우,
            날짜가 오름차순이 아닌 경우
    """
    if length < MIN_CONSECUTIVE_LENGTH:
        raise ValueError(f"연속 일수는 {MIN_CONSECUTIVE_LENGTH} 이상이어야 합니다: {length}")

    target = length if direction is Direction.UP else -length
    selected = signed_run_length(df).to_numpy() == target

    if start_date is not None:
        selected &= (df[COL_DATE] >= start_date).to_numpy()

    period = start_date.date() if start_date is not None else "전 기간"
    logger.debug(f"연속 등락 신호 {int(selected.sum()):,}건 (방향 {direction.value}, {length}일 연속, 집계 시작 {period})")

    return pd.Series(selected, index=df.index)
