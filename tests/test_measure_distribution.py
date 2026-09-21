"""분배금 몫 계약

원본가로 재기로 한 결정(측정의 원칙 14)이 만드는 왜곡의 크기를 재는 계층이다.
**인버스에서 보정 부호가 뒤집힌다**는 것이 이 모듈의 핵심이며, 그것을 테스트로 못박는다.

원칙 14 가 배당락 규모 기재를 모든 검증에 요구하므로 `measure/` 에 있다.
검증 #8(레버리지 ETF 괴리)과 #9(선물 대 레버리지 ETF), 그리고 옵션 만기일 매매가 함께 쓴다.

**답하는 질문이 둘이고 축이 다르다.** `measure_distribution_share` 는 **종목 × 전 기간**으로
「이 상품이 한 해에 배당으로 얼마를 주나」를 묻고, `dividend_impact` 는 **체결 구간**으로
「이 매매가 실제로 들고 있던 며칠에 배당락이 들어왔나」를 묻는다. 연 3% 를 주는 종목이라도
배당락일이 진입일 «당일»이면 진입가에 이미 반영돼 그 매매는 하나도 안 걸린다.
"""

from pathlib import Path

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.measure.distribution import (
    TRADING_DAYS_PER_YEAR,
    DistributionShare,
    DividendImpact,
    dividend_adjustment,
    dividend_impact,
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


# ==========================================================
# 체결 구간에 들어간 배당락 — `dividend_impact`
# ==========================================================

BASE_PRICE = 100.0

# 심는 배당락의 크기 (비율). 임계값(0.01%p)보다 두 자리 위라 반드시 「걸린 건」이 된다
DIVIDEND_RATE = 0.005


def _dates(count: int) -> pd.DatetimeIndex:
    """연속 거래일 인덱스를 만든다.

    Args:
        count: 거래일 수

    Returns:
        영업일 인덱스
    """
    return pd.DatetimeIndex(pd.bdate_range("2020-01-06", periods=count))


def _flat_series(dates: pd.DatetimeIndex, prices: list[float]) -> pd.Series:
    """날짜를 인덱스로 갖는 종가 계열을 만든다.

    Args:
        dates: 날짜 인덱스
        prices: 종가 목록

    Returns:
        종가 Series
    """
    return pd.Series(prices, index=dates, dtype=float)


class TestNoDividend:
    """배당락이 없을 때 — 두 계열이 같으면 차이도 없다"""

    def test_두_계열이_같으면_차이가_0이다(self) -> None:
        """
        목적: 없는 왜곡을 만들지 않는다는 것을 고정한다

        안 걸리는데 계산에 넣으면 「0건 확인」이라고 적어야 할 자리에 숫자가 들어간다.

        Given: 원본가와 수정주가가 완전히 같은 계열
        When: 배당락 영향을 쟀을 때
        Then: 평균과 최대가 0 이고 걸린 건이 없다
        """
        # Given
        dates = _dates(6)
        prices = [BASE_PRICE, 101.0, 102.0, 103.0, 104.0, 105.0]
        series = _flat_series(dates, prices)

        # When
        impact = dividend_impact(
            series,
            series,
            entry_dates=pd.DatetimeIndex([dates[0], dates[2]]),
            exit_dates=pd.DatetimeIndex([dates[3], dates[5]]),
            bet_down=False,
        )

        # Then
        assert impact.hit_count == 0
        assert impact.measured_count == 2
        assert impact.mean_percent == pytest.approx(0.0, abs=1e-9)
        assert impact.max_abs_percent == pytest.approx(0.0, abs=1e-9)


class TestDirectionSign:
    """부호 — 같은 배당락이 방향에 따라 반대로 읽힌다"""

    @staticmethod
    def _series_with_dividend() -> tuple[pd.DatetimeIndex, pd.Series, pd.Series]:
        """보유 구간 «안»에 배당락이 하나 든 두 계열을 만든다.

        수정주가는 배당락 **이전** 가격을 낮춰 조정하므로, 배당락일 앞의 수정주가가
        원본가보다 작다. 그래서 같은 구간을 재면 **원본가 수익률이 더 낮게** 나온다.

        Returns:
            (날짜, 원본가, 수정주가)
        """
        dates = _dates(4)
        raw = _flat_series(dates, [BASE_PRICE, BASE_PRICE, BASE_PRICE, BASE_PRICE])

        # 배당락일은 세 번째 날이다. 그 앞의 수정주가만 (1 - 배당률) 배로 낮춘다
        factor = 1.0 - DIVIDEND_RATE
        adjusted = _flat_series(
            dates,
            [BASE_PRICE * factor, BASE_PRICE * factor, BASE_PRICE, BASE_PRICE],
        )

        return dates, raw, adjusted

    def test_아래로_걸면_양수이고_과대평가다(self) -> None:
        """
        목적: 「아래」 칸의 부호 규약을 고정한다

        원본가에서 보이는 배당락 하락은 **인버스로도 공매도로도 못 먹는다.**
        그래서 원본가로 잰 성적이 실제보다 좋게 나온다.

        Given: 보유 구간 안에 배당락이 하나 든 계열
        When: 아래로 거는 칸으로 쟀을 때
        Then: 차이가 양수다
        """
        # Given
        dates, raw, adjusted = self._series_with_dividend()

        # When
        impact = dividend_impact(
            raw,
            adjusted,
            entry_dates=pd.DatetimeIndex([dates[0]]),
            exit_dates=pd.DatetimeIndex([dates[3]]),
            bet_down=True,
        )

        # Then
        assert impact.mean_percent > 0.0
        assert impact.hit_count == 1

    def test_위로_걸면_음수이고_과소평가다(self) -> None:
        """
        목적: 「위」 칸에서 부호가 뒤집히는 것을 고정한다

        실제로는 배당을 받아 보전되므로 원본가로 잰 성적이 실제보다 나쁘게 나온다.

        Given: 같은 계열
        When: 위로 거는 칸으로 쟀을 때
        Then: 차이가 음수이고 크기가 「아래」와 같다
        """
        # Given
        dates, raw, adjusted = self._series_with_dividend()
        common = {
            "entry_dates": pd.DatetimeIndex([dates[0]]),
            "exit_dates": pd.DatetimeIndex([dates[3]]),
        }

        # When
        up = dividend_impact(raw, adjusted, bet_down=False, **common)
        down = dividend_impact(raw, adjusted, bet_down=True, **common)

        # Then
        assert up.mean_percent < 0.0
        assert up.mean_percent == pytest.approx(-down.mean_percent, abs=1e-9)

    def test_배당락이_구간_밖이면_걸리지_않는다(self) -> None:
        """
        목적: **보유 구간 안에 들어온 것만** 센다는 것을 고정한다

        진입일이 곧 배당락일이면 그 하락은 **진입가에 이미 들어가 있다** —
        SPY·DIA 가 실제로 그래서 한 번도 걸리지 않는다.

        Given: 배당락이 진입일보다 앞에 있는 계열
        When: 배당락 이후 구간만 쟀을 때
        Then: 걸린 건이 없다
        """
        # Given
        dates, raw, adjusted = self._series_with_dividend()

        # When — 배당락일(세 번째 날)부터 진입한다
        impact = dividend_impact(
            raw,
            adjusted,
            entry_dates=pd.DatetimeIndex([dates[2]]),
            exit_dates=pd.DatetimeIndex([dates[3]]),
            bet_down=True,
        )

        # Then
        assert impact.hit_count == 0
        assert impact.mean_percent == pytest.approx(0.0, abs=1e-9)


class TestUnmeasurable:
    """못 잰 구간 — 0 으로 세지 않는다"""

    def test_수정주가가_덮지_못한_구간은_대조에서_빠진다(self) -> None:
        """
        목적: **「안 걸림」과 「못 쟀다」를 가른다** (`.claude/rules/trading.md`)

        국내 수정주가는 최근 3,000거래일만 존재해 앞 구간이 통째로 비는 일이 실재한다.
        그 구간을 0 으로 채우면 왜곡이 없는 것처럼 보인다.

        Given: 수정주가가 뒤쪽 절반만 있는 계열
        When: 앞뒤 두 구간을 쟀을 때
        Then: 잰 것은 하나뿐이고 그 수가 결과에 남는다
        """
        # Given
        dates = _dates(6)
        raw = _flat_series(dates, [BASE_PRICE] * 6)
        adjusted = _flat_series(dates[3:], [BASE_PRICE] * 3)

        # When
        impact = dividend_impact(
            raw,
            adjusted,
            entry_dates=pd.DatetimeIndex([dates[0], dates[3]]),
            exit_dates=pd.DatetimeIndex([dates[2], dates[5]]),
            bet_down=True,
        )

        # Then
        assert impact.measured_count == 1

    def test_하나도_못_쟀으면_평균이_결측이다(self) -> None:
        """
        목적: 잴 것이 없을 때 0 을 내지 않는다는 것을 고정한다

        `0.0` 은 「왜곡이 없었다」로 읽히는데 실제로는 「잰 적이 없다」다.

        Given: 수정주가가 구간을 전혀 덮지 못하는 계열
        When: 배당락 영향을 쟀을 때
        Then: 잰 건수가 0 이고 평균과 최대가 결측이다
        """
        # Given
        dates = _dates(6)
        raw = _flat_series(dates, [BASE_PRICE] * 6)
        # 한 해 뒤의 거래일이라 원본가 구간과 하루도 겹치지 않는다
        far_dates = pd.DatetimeIndex(pd.bdate_range("2021-01-06", periods=3))
        adjusted = _flat_series(far_dates, [BASE_PRICE] * 3)

        # When
        impact = dividend_impact(
            raw,
            adjusted,
            entry_dates=pd.DatetimeIndex([dates[0]]),
            exit_dates=pd.DatetimeIndex([dates[2]]),
            bet_down=True,
        )

        # Then
        assert impact.measured_count == 0
        assert impact.hit_count == 0
        assert pd.isna(impact.mean_percent)
        assert pd.isna(impact.max_abs_percent)


class TestInputValidation:
    """입력 검증 — 짝이 맞지 않으면 즉시 거부한다"""

    def test_진입과_청산의_개수가_다르면_거부한다(self) -> None:
        """
        목적: 조용히 짧은 쪽에 맞추지 않는다는 것을 고정한다

        `zip` 이 짧은 쪽에서 멈추면 **체결 몇 건이 예외 없이 사라진다.**

        Given: 진입 둘과 청산 하나
        When: 배당락 영향을 재려 했을 때
        Then: `ValueError` 를 던진다
        """
        # Given
        dates = _dates(4)
        series = _flat_series(dates, [BASE_PRICE] * 4)

        # When / Then
        with pytest.raises(ValueError, match="진입"):
            dividend_impact(
                series,
                series,
                entry_dates=pd.DatetimeIndex([dates[0], dates[1]]),
                exit_dates=pd.DatetimeIndex([dates[3]]),
                bet_down=True,
            )

    def test_체결이_하나도_없으면_거부한다(self) -> None:
        """
        목적: 빈 입력을 「왜곡 0」으로 내지 않는다는 것을 고정한다

        Given: 빈 진입·청산 목록
        When: 배당락 영향을 재려 했을 때
        Then: `ValueError` 를 던진다
        """
        # Given
        dates = _dates(4)
        series = _flat_series(dates, [BASE_PRICE] * 4)
        empty = pd.DatetimeIndex([])

        # When / Then
        with pytest.raises(ValueError, match="체결"):
            dividend_impact(series, series, entry_dates=empty, exit_dates=empty, bet_down=True)


class TestResultShape:
    """반환 형태 — 값 넷이 한 묶음으로 온다"""

    def test_네_값을_담은_객체를_돌려준다(self) -> None:
        """
        목적: 호출 측이 dict 키를 짐작하지 않게 한다

        Given: 배당락이 없는 계열
        When: 배당락 영향을 쟀을 때
        Then: 잰 건수·걸린 건수·평균·최대를 가진 객체다
        """
        # Given
        dates = _dates(4)
        series = _flat_series(dates, [BASE_PRICE] * 4)

        # When
        impact = dividend_impact(
            series,
            series,
            entry_dates=pd.DatetimeIndex([dates[0]]),
            exit_dates=pd.DatetimeIndex([dates[3]]),
            bet_down=True,
        )

        # Then
        assert isinstance(impact, DividendImpact)
        assert impact.measured_count == 1
        assert impact.hit_count == 0
