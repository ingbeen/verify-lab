"""달력형 일정의 거래일 목록 검사(`measure.calendar_entry.validate_trading_days`) 계약

**공유 계층의 검사는 자기 픽스처를 갖는다.** 이 함수를 쓰는 매매법의 테스트를 거쳐서만 검사하면
그 매매법이 지워지거나 다른 경로를 쓰게 되는 순간 **공유 함수의 검사가 예외 없이 0건이 된다**
(`docs/MEMORY.md` 「공유 계층의 테스트는 «자기 픽스처»를 갖는다」).
"""

import pandas as pd
import pytest

from verify_lab.measure.calendar_entry import validate_trading_days


def _trading_days(start: str, end: str) -> pd.DatetimeIndex:
    """평일만 담은 합성 거래일 목록을 만든다.

    Args:
        start: 첫날 (`YYYY-MM-DD`)
        end: 마지막 날 (`YYYY-MM-DD`)

    Returns:
        오름차순·중복 없는 거래일 목록
    """
    return pd.bdate_range(start, end)


class TestValidateTradingDays:
    """거래일 목록이 달력 일정 산출의 전제(비지 않음 · 오름차순 · 중복 없음)를 만족하는지"""

    def test_정상_목록은_통과한다(self) -> None:
        """
        목적: 전제를 만족하는 목록을 막지 않는다

        Given: 한 달치 평일 거래일 목록
        When: 검사하면
        Then: 예외가 나지 않는다
        """
        # Given
        days = _trading_days("2026-07-01", "2026-07-31")

        # When / Then
        validate_trading_days(days, purpose="진입일")

    def test_거래일_목록이_비면_예외다(self) -> None:
        """
        목적: 빈 목록을 조용히 통과시키지 않는다 — 일정이 0건으로 나와도 예외가 나지 않는다

        Given: 빈 거래일 목록
        When: 검사하면
        Then: ValueError 가 나고 무엇을 산출하려던 것인지가 메시지에 실린다
        """
        # Given
        days = pd.DatetimeIndex([])

        # When / Then
        with pytest.raises(ValueError, match="비어 있어 진입일을"):
            validate_trading_days(days, purpose="진입일")

    def test_정렬되지_않은_거래일_목록은_예외다(self) -> None:
        """
        목적: 위치 계산이 엉뚱한 날을 고르는 입력을 막는다

        Given: 내림차순 거래일 목록
        When: 검사하면
        Then: ValueError 가 난다
        """
        # Given
        days = pd.DatetimeIndex(_trading_days("2026-07-01", "2026-07-31")[::-1])

        # When / Then
        with pytest.raises(ValueError, match="오름차순"):
            validate_trading_days(days, purpose="청산일")

    def test_중복된_날짜가_있으면_예외다(self) -> None:
        """
        목적: 같은 날이 두 번 있으면 한 매매가 두 위치로 갈라진다 — 그 입력을 막는다 (엣지 케이스)

        Given: 오름차순이지만 한 날짜가 두 번 들어간 목록 (단조 증가는 깨지지 않는다)
        When: 검사하면
        Then: ValueError 가 난다
        """
        # Given
        base = _trading_days("2026-07-01", "2026-07-31")
        days = pd.DatetimeIndex([*base[:3], base[2], *base[3:]])
        assert days.is_monotonic_increasing, "중복 분기를 검사하려면 정렬 검사를 통과하는 입력이어야 합니다"

        # When / Then
        with pytest.raises(ValueError, match="중복"):
            validate_trading_days(days, purpose="진입일")
