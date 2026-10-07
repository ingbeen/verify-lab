"""forward return 표의 공통 규격 — 기준점 이름과 제외 건수 세기

"이 신호 다음에 실제로 무슨 일이 있었나"를 재는 매매법은 수익률을 **신호일 × 기준 × 구간을 한 줄씩 담은
long-form** 한 장으로 만든다. 표를 만드는 것은 각 매매법이고, 이 모듈은 그 표가 공유하는 기준점 이름과
제외 건수 세기를 갖는다.

구간 끝이 데이터 범위를 넘어가는 칸은 값 없이 사유를 달고 그대로 남는다 — 행을 지우면 표본이 조용히 사라져
생존편향이 생긴다. 그래서 몇 건이 왜 빠졌는지를 따로 센다.
"""

from enum import Enum

import pandas as pd

from verify_lab.measure.constants import (
    COL_BASIS,
    COL_EXCLUDED_COUNT,
    COL_EXCLUDED_REASON,
    COL_HORIZON,
    COL_SIGNAL_COUNT,
    EXCLUDED_SUMMARY_COLUMNS,
    REASON_NONE,
)


class ReturnBasis(Enum):
    """수익률 기준점

    Attributes:
        CLOSE: 이벤트일 종가에서 시작 — 신호의 순수한 예측력
    """

    CLOSE = "close"


def count_excluded(frame: pd.DataFrame) -> pd.DataFrame:
    """(기준, 구간) 칸별로 신호 수와 제외 건수를 센다.

    표본을 줄이는 처리를 했으면 몇 건이 왜 빠졌는지 함께 내야 한다는 원칙을 위한 요약이다.
    제외가 0건인 칸도 빠뜨리지 않으므로 `신호 수 − 제외 수 = 유효 표본` 을 그대로 읽을 수 있다.

    Args:
        frame: forward return long-form 표. `COL_BASIS` · `COL_HORIZON` · `COL_EXCLUDED_REASON` 를 갖는다

    Returns:
        `EXCLUDED_SUMMARY_COLUMNS` 순서의 요약표. 기준·구간 오름차순으로 정렬된다

    Raises:
        ValueError: 필요한 컬럼이 없는 경우
    """
    missing_columns = {COL_BASIS, COL_HORIZON, COL_EXCLUDED_REASON} - set(frame.columns)
    if missing_columns:
        raise ValueError(f"필수 컬럼이 누락되었습니다: {sorted(missing_columns)}")

    working = frame[[COL_BASIS, COL_HORIZON, COL_EXCLUDED_REASON]].copy()
    working[COL_EXCLUDED_COUNT] = working[COL_EXCLUDED_REASON] != REASON_NONE

    summary = working.groupby([COL_BASIS, COL_HORIZON], as_index=False, sort=True).agg(
        **{
            COL_SIGNAL_COUNT: (COL_EXCLUDED_REASON, "size"),
            COL_EXCLUDED_COUNT: (COL_EXCLUDED_COUNT, "sum"),
        }
    )
    summary[COL_EXCLUDED_COUNT] = summary[COL_EXCLUDED_COUNT].astype(int)

    return summary[EXCLUDED_SUMMARY_COLUMNS]
