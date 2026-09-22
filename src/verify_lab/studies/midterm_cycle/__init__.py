"""중간선거_사이클 — 중간선거 해 4분기부터 다음해 2분기까지 들고 있는 매매법

**규칙은 하나다** — 10월 첫 거래일 종가 매수 → 다음해 6월 마지막 거래일 종가 매도.
Stock Trader's Almanac 이 "Sweet Spot" 이라 부르는 구간이며, 진입·청산이 둘 다 달력이라
미래를 참조하지 않는다.

**축은 «사이클 위치» 넷이다.** 같은 10월 → 6월 창을 사이클의 네 자리에서 각각 재고,
**네 칸의 차이가 곧 선거 사이클 고유 기여분**이다 — 그 창은 잘 알려진
「Best Six Months」(11월~4월)를 통째로 품고 있어 대조 없이는 달력 효과와 섞인다.

**달력 계산은 이 패키지가 소유한다** — 진입이 「미룸」이고 청산이 8개월 뒤 달이라
`measure/calendar_*` 의 기존 두 규칙과 방향도 기준점도 다르다. 근거는
`cycle_calendar.py` 모듈 docstring 에 있다.

확정 설계는 `docs/검증/중간선거_사이클/설계.md` 가 SoT 다.
"""

from .constants import CYCLE_POSITIONS, DATASETS, ENTRY_MONTH, EXIT_MONTH, TRACK_NAME

__all__ = ["CYCLE_POSITIONS", "DATASETS", "ENTRY_MONTH", "EXIT_MONTH", "TRACK_NAME"]
