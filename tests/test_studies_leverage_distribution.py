"""검증 #8 — 분배금 몫 계약

원본가로 재기로 한 결정(측정의 원칙 14)이 만드는 왜곡의 크기를 재는 계층이다.
**인버스에서 보정 부호가 뒤집힌다**는 것이 이 모듈의 핵심이며, 그것을 테스트로 못박는다.
"""

from pathlib import Path

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.studies.leverage_tracking.distribution import (
    TRADING_DAYS_PER_YEAR,
    DistributionShare,
    dividend_adjustment,
    measure_distribution_share,
)

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12


def _write_market_csv(path: Path, closes: list[float]) -> None:
    """테스트용 시세 CSV 를 만든다.

    Args:
        path: 저장 경로
        closes: 종가 목록
    """
    dates = pd.bdate_range(start="2026-01-02", periods=len(closes))
    pd.DataFrame(
        {
            COL_DATE: dates.date,
            COL_OPEN: closes,
            COL_HIGH: closes,
            COL_LOW: closes,
            COL_CLOSE: closes,
            COL_VOLUME: [1_000] * len(closes),
        }
    ).to_csv(path, index=False)


class TestMeasureDistributionShare:
    """분배 기여 측정"""

    def test_수정주가가_원본가보다_빨리_오르면_양의_기여다(self, tmp_path: Path) -> None:
        """
        목적: 분배 기여의 부호와 크기를 고정한다

        Given: 원본가는 매일 1%, 수정주가는 매일 1.1% 오르는 종목
        When: 분배 기여를 잰다
        Then: 일간 기여가 약 0.1%p 이고 연율은 그 252배다
        """
        # Given
        _write_market_csv(tmp_path / "TEST_max.csv", [100.0 * 1.01**index for index in range(11)])
        _write_market_csv(tmp_path / "TEST_adjusted_max.csv", [100.0 * 1.011**index for index in range(11)])

        # When
        share = measure_distribution_share("TEST", market_dir=tmp_path)

        # Then
        assert share.daily_contribution == pytest.approx(0.001, abs=1e-9)
        assert share.annual_contribution == pytest.approx(0.001 * TRADING_DAYS_PER_YEAR, abs=1e-9)
        assert share.measured is True

    def test_두_계열이_같으면_기여가_0이다(self, tmp_path: Path) -> None:
        """
        목적: 분배금이 없는 종목의 기준점을 고정한다

        Given: 원본가와 수정주가가 완전히 같은 종목
        When: 분배 기여를 잰다
        Then: 일간 기여가 0 이다
        """
        # Given
        closes = [100.0, 102.0, 99.0, 105.0, 103.0]
        _write_market_csv(tmp_path / "TEST_max.csv", closes)
        _write_market_csv(tmp_path / "TEST_adjusted_max.csv", closes)

        # When
        share = measure_distribution_share("TEST", market_dir=tmp_path)

        # Then
        assert share.daily_contribution == pytest.approx(0.0, abs=EXACT_TOLERANCE)

    def test_수정주가_파일이_없으면_분배금_없음으로_본다(self, tmp_path: Path) -> None:
        """
        목적: ETN 처리 정책을 고정한다 — 결측이 아니라 「분배금 없음」이다

        Given: 원본가만 있고 수정주가 파일이 없는 종목
        When: 분배 기여를 잰다
        Then: 기여가 0 이고 measured 가 False 다
        """
        # Given
        _write_market_csv(tmp_path / "TEST_max.csv", [100.0, 101.0, 102.0])

        # When
        share = measure_distribution_share("TEST", market_dir=tmp_path)

        # Then
        assert share.daily_contribution == 0.0
        assert share.measured is False

    def test_원본가_파일이_없으면_예외(self, tmp_path: Path) -> None:
        """
        목적: 원본가 결측을 조용히 0 으로 넘기지 않는지 고정한다

        Given: 아무 파일도 없는 폴더
        When: 분배 기여를 잰다
        Then: ValueError 가 난다
        """
        # When / Then
        with pytest.raises(ValueError, match="원본가 파일이 없습니다"):
            measure_distribution_share("TEST", market_dir=tmp_path)


class TestDividendAdjustment:
    """배당 보정분 — 총수익 기준으로 다시 쟀다면 총 괴리가 얼마나 달라지는가"""

    def _share(self, ticker: str, daily: float) -> DistributionShare:
        """테스트용 분배 기여를 만든다.

        Args:
            ticker: 종목
            daily: 일간 분배 기여

        Returns:
            분배 기여 요약
        """
        return DistributionShare(
            ticker=ticker,
            daily_contribution=daily,
            annual_contribution=daily * TRADING_DAYS_PER_YEAR,
            overlap_days=1_000,
            start_date=None,
            end_date=None,
            measured=True,
        )

    def test_레버리지에서는_1배_배당이_보정을_음수로_만든다(self) -> None:
        """
        목적: 양의 배수에서 보정 부호를 고정한다

        Given: 1배만 배당을 주고 2배 상품은 안 주는 상황
        When: 21거래일 보정분을 낸다
        Then: 보정분이 음수다 (원본가 기준 괴리가 과대평가돼 있다)
        """
        # Given
        base = self._share("BASE", 0.00005)
        target = self._share("TARGET", 0.0)

        # When
        adjustment = dividend_adjustment(base, target, multiple=2.0, horizon=21)

        # Then
        assert adjustment == pytest.approx(-2.0 * 0.00005 * 21, abs=EXACT_TOLERANCE)
        assert adjustment < 0

    def test_인버스에서는_부호가_뒤집힌다(self) -> None:
        """
        목적: 이 모듈의 핵심 — 음의 배수에서 보정 방향이 반대인지 고정한다

        Given: 1배만 배당을 주고 −2배 상품은 안 주는 상황
        When: 21거래일 보정분을 낸다
        Then: 보정분이 양수다 (원본가 기준 괴리가 과소평가돼 있다)
        """
        # Given
        base = self._share("BASE", 0.00005)
        target = self._share("TARGET", 0.0)

        # When
        adjustment = dividend_adjustment(base, target, multiple=-2.0, horizon=21)

        # Then
        assert adjustment == pytest.approx(2.0 * 0.00005 * 21, abs=EXACT_TOLERANCE)
        assert adjustment > 0

    def test_배수_상품의_배당이_1배의_배수만큼이면_보정이_0이다(self) -> None:
        """
        목적: 보정분이 0 이 되는 조건을 고정한다

        Given: 배수 상품의 분배 기여가 정확히 1배의 2배인 상황
        When: 보정분을 낸다
        Then: 0 이다
        """
        # Given
        base = self._share("BASE", 0.00005)
        target = self._share("TARGET", 0.0001)

        # When
        adjustment = dividend_adjustment(base, target, multiple=2.0, horizon=63)

        # Then
        assert adjustment == pytest.approx(0.0, abs=EXACT_TOLERANCE)

    def test_보정분은_보유_기간에_비례한다(self) -> None:
        """
        목적: 구간 길이가 보정분을 선형으로 키우는지 고정한다

        Given: 같은 분배 기여
        When: 구간 21 과 63 의 보정분을 각각 낸다
        Then: 63 쪽이 정확히 3배다
        """
        # Given
        base = self._share("BASE", 0.00005)
        target = self._share("TARGET", 0.0)

        # When
        short = dividend_adjustment(base, target, multiple=2.0, horizon=21)
        long = dividend_adjustment(base, target, multiple=2.0, horizon=63)

        # Then
        assert long == pytest.approx(short * 3, abs=EXACT_TOLERANCE)
