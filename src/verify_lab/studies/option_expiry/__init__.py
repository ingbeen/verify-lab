"""검증 #7 — 옵션 만기일 매매

**신호는 만기일 그 자체다** — 만기일 종가에 사서 다음 주 금요일 종가에 판다.

만기일은 시세가 아니라 달력 규칙(미국 셋째 금요일 · 한국 둘째 목요일)이므로 외부 데이터가
필요 없다. 규칙일이 휴장이면 직전 거래일로 앞당기며, 그 판정에 쓰는 거래일 목록은
시세 파일의 날짜 인덱스에서 온다.

**상대 거래일(offset) 축은 산출물에서 빠졌다** (2026-09-21). 만기 앞뒤 ±10거래일의
수익률을 전부 내던 축이며 **결과 문서가 「우위 없음」으로 닫았다.** 계산 자체는
`offsets.py` 에 남아 있고 `scripts/data/check_kodex_distribution.py` 가 분배락 위치를
재는 데 쓴다 — 그쪽은 「만기 창 안에 분배락이 있는가」를 묻는 다른 질문이다.

확정 설계는 `docs/매매/옵션_만기일/설계.md`, 실제로 거는 칸은 `docs/매매/옵션_만기일/규칙.md` 가 SoT 다.
"""

from .constants import (
    COL_ADVANCED_DAYS,
    COL_EXPIRY_DATE,
    COL_EXPIRY_MONTH,
    COL_OFFSET,
    COL_RULE_DATE,
    KR_MONTHLY_EXPIRY,
    MAX_OFFSET,
    TRACK_NAME,
    US_MONTHLY_EXPIRY,
    ExpiryRule,
)
from .expiry_calendar import monthly_expiry_dates, nth_weekday_of_month
from .offsets import OffsetAssignment, expiry_offsets

__all__ = [
    "COL_ADVANCED_DAYS",
    "COL_EXPIRY_DATE",
    "COL_EXPIRY_MONTH",
    "COL_OFFSET",
    "COL_RULE_DATE",
    "KR_MONTHLY_EXPIRY",
    "MAX_OFFSET",
    "TRACK_NAME",
    "US_MONTHLY_EXPIRY",
    "ExpiryRule",
    "OffsetAssignment",
    "expiry_offsets",
    "monthly_expiry_dates",
    "nth_weekday_of_month",
]
