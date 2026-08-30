"""검증 #1 — 지수 극단 이벤트의 이벤트 정의

공통 계층에 넘기는 것은 **"어느 날이 신호인가"** 하나다.

- **테스트 A(역대급 등락)**: 판정일까지의 데이터 기준으로 일간 등락률이 역대 상위 K위 안인 날

여기에 신호일 목록에 붙는 부가 컬럼(당시 순위, 사건 번호, 참고용 z-score)을 더한다.
부가 컬럼은 해석 보조이며 판정에 쓰지 않는다.

`runner` 는 이 정의를 강건성 조합만큼 순회해 공통 계층에 넘기고 산출물을 조립한다.

확정 설계는 `docs/spec/index_extreme_events.md` 가 SoT 다.
"""

from .annotations import assign_event_ids, reference_zscore
from .constants import (
    DATASETS,
    DECADE_PERIODS,
    DEFAULT_RANK_CUT,
    DEFAULT_START_YEAR,
    EVENT_GAP_DAYS,
    PERIOD_ALL,
    RANK_CUTS,
    START_YEARS,
    STUDY_NAME,
    ZSCORE_WINDOW,
    Dataset,
    Direction,
    Period,
)
from .daily_change import daily_change_rate
from .extreme_move import expanding_rank, find_extreme_move_events
from .runner import IDENTITY_COLUMNS, StudyOutputs, run_study

__all__ = [
    "DATASETS",
    "DECADE_PERIODS",
    "DEFAULT_RANK_CUT",
    "DEFAULT_START_YEAR",
    "EVENT_GAP_DAYS",
    "IDENTITY_COLUMNS",
    "PERIOD_ALL",
    "RANK_CUTS",
    "START_YEARS",
    "STUDY_NAME",
    "ZSCORE_WINDOW",
    "Dataset",
    "Direction",
    "Period",
    "StudyOutputs",
    "assign_event_ids",
    "daily_change_rate",
    "expanding_rank",
    "find_extreme_move_events",
    "reference_zscore",
    "run_study",
]
