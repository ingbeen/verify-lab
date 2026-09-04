"""검증 #8 — 1배 상품과 배수 상품의 날짜 정렬 계약

두 종목을 짝지어 재는 것이 이 검증의 전제다. 한쪽에만 있는 거래일을 채우거나 조용히
버리면 괴리가 아니라 정렬 오류를 재게 되므로, **공통 거래일만 남기고 몇 건이 왜 빠졌는지
함께 돌려준다**는 계약을 여기서 고정한다.
"""

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.studies.leverage_tracking.constants import COL_BASE_CLOSE, COL_TARGET_CLOSE
from verify_lab.studies.leverage_tracking.pairing import align_pair


def _market_frame(dates: list[str], closes: list[float]) -> pd.DataFrame:
    """테스트용 최소 시세 프레임을 만든다.

    Args:
        dates: 거래일 목록 (YYYY-MM-DD)
        closes: 종가 목록

    Returns:
        시세 스키마를 갖춘 DataFrame
    """
    return pd.DataFrame(
        {
            COL_DATE: pd.to_datetime(dates),
            COL_OPEN: closes,
            COL_HIGH: closes,
            COL_LOW: closes,
            COL_CLOSE: closes,
            COL_VOLUME: [1_000] * len(dates),
        }
    )


class TestAlignPair:
    """공통 거래일 정렬 계약"""

    def test_공통_거래일만_남긴다(self) -> None:
        """
        목적: 한쪽에만 있는 거래일이 결과에서 빠지는지 고정한다

        Given: 1배는 4일, 배수는 그중 3일만 가진 시세
        When: align_pair 로 정렬한다
        Then: 두 종목이 모두 가진 3일만 남는다
        """
        # Given
        base = _market_frame(["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"], [100.0, 101.0, 102.0, 103.0])
        target = _market_frame(["2026-01-02", "2026-01-06", "2026-01-07"], [50.0, 52.0, 54.0])

        # When
        alignment = align_pair(base, target)

        # Then
        assert alignment.frame[COL_DATE].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-02", "2026-01-06", "2026-01-07"]

    def test_한쪽에만_있는_거래일_수를_돌려준다(self) -> None:
        """
        목적: 표본이 조용히 사라지지 않도록 제외 건수를 돌려주는지 고정한다

        Given: 1배에만 있는 날 1일, 배수에만 있는 날 2일
        When: align_pair 로 정렬한다
        Then: 양쪽 제외 건수가 각각 보고된다
        """
        # Given
        base = _market_frame(["2026-01-02", "2026-01-05", "2026-01-06"], [100.0, 101.0, 102.0])
        target = _market_frame(["2026-01-02", "2026-01-06", "2026-01-07", "2026-01-08"], [50.0, 52.0, 54.0, 55.0])

        # When
        alignment = align_pair(base, target)

        # Then
        assert (alignment.base_only_count, alignment.target_only_count) == (1, 2)

    def test_두_종가를_각각_컬럼으로_담는다(self) -> None:
        """
        목적: 결과 스키마를 고정한다

        Given: 서로 다른 종가를 가진 두 시세
        When: align_pair 로 정렬한다
        Then: 1배 종가와 배수 종가가 각자의 컬럼에 들어간다
        """
        # Given
        base = _market_frame(["2026-01-02", "2026-01-05"], [100.0, 110.0])
        target = _market_frame(["2026-01-02", "2026-01-05"], [50.0, 60.0])

        # When
        alignment = align_pair(base, target)

        # Then
        assert alignment.frame[COL_BASE_CLOSE].tolist() == [100.0, 110.0]
        assert alignment.frame[COL_TARGET_CLOSE].tolist() == [50.0, 60.0]

    def test_날짜_오름차순을_보장한다(self) -> None:
        """
        목적: 위치 기반 계산의 전제인 정렬을 고정한다

        Given: 날짜가 뒤섞인 시세
        When: align_pair 로 정렬한다
        Then: 결과가 날짜 오름차순이다
        """
        # Given
        base = _market_frame(["2026-01-06", "2026-01-02", "2026-01-05"], [102.0, 100.0, 101.0])
        target = _market_frame(["2026-01-05", "2026-01-06", "2026-01-02"], [52.0, 54.0, 50.0])

        # When
        alignment = align_pair(base, target)

        # Then
        assert alignment.frame[COL_DATE].is_monotonic_increasing

    def test_겹치는_거래일이_없으면_예외(self) -> None:
        """
        목적: 겹치는 날이 0건인 상황을 조용히 빈 결과로 넘기지 않는지 고정한다

        Given: 기간이 전혀 겹치지 않는 두 시세
        When: align_pair 를 호출한다
        Then: ValueError 가 난다
        """
        # Given
        base = _market_frame(["2026-01-02", "2026-01-05"], [100.0, 101.0])
        target = _market_frame(["2026-02-02", "2026-02-03"], [50.0, 51.0])

        # When / Then
        with pytest.raises(ValueError, match="겹치는 거래일"):
            align_pair(base, target)
