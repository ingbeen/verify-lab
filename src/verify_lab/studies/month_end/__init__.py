"""검증 #10 — 월 하순 진입의 이벤트 정의 (코스피·코스닥)

사용자가 전해 들은 매매법을 잰다 — **"코스닥은 20일 종가에 인버스를 사서 말일 종가에 팔면
확률이 높다"**. 진입도 청산도 달력 기준이라 보유 거래일 수가 달마다 다르며(3~9일),
`measure/forward_return.py` 의 고정 구간 틀에 들어가지 않는다.

**하나의 칸을 고르지 않는다.** 「왜 하필 20일·말일인가」에 답하려면 이웃 칸도 함께 봐야 하므로
확정 칸(9월 아래)을 재고 그 해석 재료를 한 장으로 낸다.

**달력 계산 자체는 `measure/calendar_entry.py`·`calendar_exit.py` 가 소유한다** —
세 매매법이 같은 달력을 쓰므로 한 자리에 있어야 하고, 매매법끼리는 서로를 가져올 수 없다
(`tests/test_layer_contracts.py`). 여기 남는 것은 **이 매매법의 파라미터**뿐이다.

확정 설계는 `docs/매매/월말_진입/설계.md` 가 SoT 다.
"""

from .constants import (
    BASE_ENTRY_DAY,
    BASE_EXIT_OFFSET,
    HORIZON_MONTH_END,
    TRACK_NAME,
)

__all__ = [
    "BASE_ENTRY_DAY",
    "BASE_EXIT_OFFSET",
    "HORIZON_MONTH_END",
    "TRACK_NAME",
]
