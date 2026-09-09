"""검증 #10 — 코스닥 월 하순 진입의 이벤트 정의

사용자가 전해 들은 매매법을 잰다 — **"코스닥은 20일 종가에 인버스를 사서 말일 종가에 팔면
확률이 높다"**. 진입도 청산도 달력 기준이라 보유 거래일 수가 달마다 다르며(3~9일),
`measure/forward_return.py` 의 고정 구간 틀에 들어가지 않는다.

**하나의 칸을 고르지 않는다.** 「왜 하필 20일·말일인가」에 답하려면 이웃 칸도 함께 봐야 하므로
진입 달력일과 청산 상대 거래일을 격자로 산출해 나란히 보고한다.

확정 설계는 `docs/spec/month_end.md` 가 SoT 다.
"""

from .constants import (
    BASE_ENTRY_DAY,
    BASE_EXIT_OFFSET,
    ENTRY_CALENDAR_DAYS,
    EXIT_OFFSETS,
    HORIZON_MONTH_END,
    STUDY_NAME,
)
from .schedule import (
    MonthExitSchedule,
    converged_month_count,
    month_entry_dates,
    month_exit_returns,
    month_exit_schedule,
)

__all__ = [
    "BASE_ENTRY_DAY",
    "BASE_EXIT_OFFSET",
    "ENTRY_CALENDAR_DAYS",
    "EXIT_OFFSETS",
    "HORIZON_MONTH_END",
    "STUDY_NAME",
    "MonthExitSchedule",
    "converged_month_count",
    "month_entry_dates",
    "month_exit_returns",
    "month_exit_schedule",
]
