"""만기_말일 — 옵션 만기일과 월말 진입을 2×2 로 교차한 검증

**두 매매법이 각자 쓰던 진입·청산을 한 축에 올려 놓는다.** 진입 2종(셋째 금요일 · 20일) ×
청산 2종(다음 주 금요일 · 그 달 마지막 거래일)이고, 재는 달은 9월·12월이다.

**한국에도 셋째 금요일을 쓴다** — 국내 만기(둘째 목요일)는 사용자가 이미 재 봤고 성과가 약했다.

**달력 계산 자체는 `measure/calendar_entry.py`·`calendar_exit.py` 가 소유한다** —
세 매매법이 같은 달력을 쓰므로 한 자리에 있어야 하고, 매매법끼리는 서로를 가져올 수 없다
(`tests/test_layer_contracts.py`). 여기 있는 것은 **이 검증의 파라미터와 조립**뿐이다.

확정 설계는 `docs/검증/만기_말일/설계.md` 가 SoT 다.
"""

from .constants import COMBOS, DATASETS, MONTHS, TRACK_NAME

__all__ = ["COMBOS", "DATASETS", "MONTHS", "TRACK_NAME"]
