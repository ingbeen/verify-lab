"""검증 #7 — 옵션 만기일 주변 수익률의 이벤트 정의

공통 계층에 넘기는 것은 **"어느 날이 신호인가"** 하나이며, 이 검증의 신호는
**만기일 기준 상대 거래일(offset)이 특정 값인 날**이다.

만기일은 시세가 아니라 달력 규칙(미국 셋째 금요일 · 한국 둘째 목요일)이므로 외부 데이터가
필요 없다. 규칙일이 휴장이면 직전 거래일로 앞당기며, 그 판정에 쓰는 거래일 목록은
시세 파일의 날짜 인덱스에서 온다.

**하나의 창을 고르지 않는다.** 문헌이 말하는 "만기 1주 전"은 정의에 따라 부호가 뒤집히므로,
offset 을 앞뒤로 전부 산출해 나란히 보고한다.

확정 설계는 `docs/spec/option_expiry.md` 가 SoT 다.
"""

from .constants import (
    COL_ADVANCED_DAYS,
    COL_EXPIRY_DATE,
    COL_EXPIRY_MONTH,
    COL_OFFSET,
    COL_RULE_DATE,
    KR_MONTHLY_EXPIRY,
    MAX_OFFSET,
    STUDY_NAME,
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
    "STUDY_NAME",
    "US_MONTHLY_EXPIRY",
    "ExpiryRule",
    "OffsetAssignment",
    "expiry_offsets",
    "monthly_expiry_dates",
    "nth_weekday_of_month",
]
