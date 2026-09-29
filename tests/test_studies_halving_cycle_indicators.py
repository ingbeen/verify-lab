"""반감기_사이클 2단계 지표 산식을 손 계산 값으로 고정한다.

| 무엇 | 왜 |
| --- | --- |
| Pi Cycle 비율 · 이격도 | SMA 는 공유 함수 하나가 낸다(측정의 원칙 15 · 결정 ㉒) — 창만 이 매매법의 값이다 |
| 월말 종가 | **그 달의 마지막 날이 데이터에 있는 달만** 쓴다 — 끝나지 않은 달의 값은 그 달 종가가 아니다 |
| EMA · 로그 MACD | 결정 ㉕. 씨앗은 첫 값(TradingView `ta.ema`)이고 창이 차기 전은 비운다 |
| MVRV-Z | 결정 ㉓ — 표준편차는 **그날까지**의 시가총액이다. 전 기간 표준편차는 미래 참조라 look-ahead 감시가 잡는다 |

창은 실제 값(111 · 350 · 14 · 5 · 15 · 9)이 아니라 **손으로 셀 수 있는 작은 값**을 인자로 넘긴다.
"""

import numpy as np
import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_OPEN
from verify_lab.studies.halving_cycle.constants import (
    COL_DISPARITY,
    COL_MACD_HISTOGRAM,
    COL_MARKET_CAP,
    COL_MONTHLY_RSI,
    COL_MVRV,
    COL_MVRV_Z,
    COL_NUPL,
    COL_PI_CYCLE,
)
from verify_lab.studies.halving_cycle.indicators import (
    daily_indicator_frame,
    disparity,
    exponential_average,
    log_macd_histogram,
    month_end_closes,
    monthly_indicator_frame,
    mvrv_z,
    nupl,
    pi_cycle_ratio,
    wilder_rsi,
)

# Wilder RSI 손 계산 입력 (창 3)
RSI_CLOSES = [10.0, 11.0, 10.0, 12.0, 13.0, 12.0]

# 로그 MACD 손 계산 입력 — 로그를 씌우면 0 · 1 · 3 · 6 · 10 이 된다
MACD_LOG_VALUES = [0.0, 1.0, 3.0, 6.0, 10.0]


def _daily_prices(start: str, end: str, closes: np.ndarray | None = None) -> pd.DataFrame:
    """매일 거래하는 합성 시세 (날짜 · 시가 · 종가)."""
    days = pd.date_range(start, end, freq="D")
    values = closes if closes is not None else np.linspace(100.0, 200.0, len(days))
    return pd.DataFrame({COL_DATE: days, COL_OPEN: values, COL_CLOSE: values})


class TestPiCycleAndDisparity:
    """SMA 로 만드는 두 비율"""

    def test_pi_cycle_ratio_is_short_sma_over_multiple_of_long_sma(self) -> None:
        """
        목적: Pi Cycle 비율 = 짧은 SMA ÷ (배수 × 긴 SMA) 를 박는다. 1 을 넘는 날이 「교차」다.

        Given: 종가 1 · 2 · 3 · 4 · 5, 짧은 창 2 · 긴 창 3 · 배수 2
        When: 비율을 낸다
        Then: 긴 창이 차기 전은 비고 2.5 ÷ 4 · 3.5 ÷ 6 · 4.5 ÷ 8 이다
        """
        # When
        result = pi_cycle_ratio(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), short_window=2, long_window=3, multiplier=2.0)

        # Then
        assert result.iloc[:2].isna().all()
        assert result.iloc[2:].tolist() == pytest.approx([0.625, 3.5 / 6.0, 0.5625], abs=1e-12)

    def test_disparity_is_close_over_sma(self) -> None:
        """
        목적: 이격도 = 종가 ÷ SMA (비율 — 1.0 이 이동평균과 같다).

        Given: 종가 1 · 2 · 3 · 4 · 5, 창 3
        When: 이격도를 낸다
        Then: 창이 차기 전은 비고 3 ÷ 2 · 4 ÷ 3 · 5 ÷ 4 다
        """
        # When
        result = disparity(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), window=3)

        # Then
        assert result.iloc[:2].isna().all()
        assert result.iloc[2:].tolist() == pytest.approx([1.5, 4.0 / 3.0, 1.25], abs=1e-12)


class TestMonthEndCloses:
    """월봉 — 끝난 달의 마지막 날 종가"""

    def test_only_months_whose_last_day_is_in_the_data(self) -> None:
        """
        목적: 끝나지 않은 마지막 달을 빼고, 달 중간에 시작한 첫 달은 남긴다.

        첫 달은 시작이 달 중간이어도 그 달의 마지막 날 종가가 곧 그 달 종가다. 마지막 달은 말일이 데이터에
        없으면 그 달이 끝나지 않은 것이다 — 그 값을 쓰면 미래에 바뀔 값을 그 달 종가로 읽는다.

        Given: 2020-01-15 ~ 2020-03-15 매일 (윤년 2월)
        When: 월말 종가를 낸다
        Then: 2020-01-31 · 2020-02-29 두 달이고 값은 그날 종가다
        """
        # Given
        prices = _daily_prices("2020-01-15", "2020-03-15")
        closes = prices.set_index(COL_DATE)[COL_CLOSE]

        # When
        result = month_end_closes(prices)

        # Then
        assert list(result.index) == [pd.Timestamp("2020-01-31"), pd.Timestamp("2020-02-29")]
        assert result.tolist() == pytest.approx(
            [closes[pd.Timestamp("2020-01-31")], closes[pd.Timestamp("2020-02-29")]], abs=1e-12
        )


class TestWilderRsi:
    """월간 RSI 의 산식 — 중간선거_사이클과 같은 정의의 두 번째 사본이다 (설계 결정의 승인 전 확인 (나))"""

    def test_values_match_hand_calculation(self) -> None:
        """
        목적: Wilder RSI 산식을 박는다.

        Given: 종가 10 · 11 · 10 · 12 · 13 · 12, 창 3
        When: RSI 를 낸다
        Then: 앞 3개는 비고 75.0 · 81.8182 · 58.0645 다
              (첫 평균 = 상승 (1+0+2)/3 = 1 · 하락 (0+1+0)/3 = 1/3 → 100 × 1 ÷ (1+1/3) = 75,
               다음 상승 (1×2+1)/3 = 1 · 하락 (1/3×2+0)/3 = 2/9 → 100 × 1 ÷ (1+2/9) = 81.82,
               그다음 상승 (1×2+0)/3 = 2/3 · 하락 (2/9×2+1)/3 = 13/27 → 100 × 18/31 = 58.06)
        """
        # When
        result = wilder_rsi(pd.Series(RSI_CLOSES), window=3)

        # Then
        assert result.iloc[:3].isna().all()
        assert result.iloc[3:].tolist() == pytest.approx([75.0, 81.81818181818181, 58.06451612903225], abs=1e-9)

    def test_flat_series_is_undefined(self) -> None:
        """
        목적: 등락이 없으면 RSI 가 정의되지 않는다 — 50 이나 100 으로 채우지 않는다 (경계 조건).

        Given: 전 구간 같은 값, 창 3
        When: RSI 를 낸다
        Then: 전부 비어 있다
        """
        assert wilder_rsi(pd.Series([5.0] * 6), window=3).isna().all()

    def test_rejects_too_small_window(self) -> None:
        """
        목적: 창이 2 미만이면 평균이 성립하지 않는다.

        Given: 창 1
        When: RSI 를 낸다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="창"):
            wilder_rsi(pd.Series(RSI_CLOSES), window=1)


class TestExponentialAverageAndMacd:
    """EMA 는 첫 값이 씨앗이고, 로그 MACD − 시그널은 창이 차기 전을 비운다 (결정 ㉕)"""

    def test_exponential_average_seeds_with_first_value(self) -> None:
        """
        목적: EMA 의 첫 값이 입력의 첫 값이고 그 뒤는 `α × 오늘 + (1 − α) × 어제` (α = 2 ÷ (창 + 1)) 다.

        Given: 1 · 2 · 3, 창 3 (α = 0.5)
        When: EMA 를 낸다
        Then: 1 · 1.5 · 2.25
        """
        # When
        result = exponential_average(pd.Series([1.0, 2.0, 3.0]), span=3)

        # Then
        assert result.tolist() == pytest.approx([1.0, 1.5, 2.25], abs=1e-12)

    def test_log_macd_histogram_matches_hand_calculation(self) -> None:
        """
        목적: 로그 종가 MACD − 시그널을 박고, **창이 차기 전(느린 창 + 시그널 창 − 2 개)** 을 비운다.

        Given: 로그를 씌우면 0 · 1 · 3 · 6 · 10 인 종가, 빠른 창 2 · 느린 창 3 · 시그널 창 2
        When: MACD − 시그널을 낸다
        Then: 앞 3개는 비고 37/216 · 797/3888 이다 (분수로 손 계산한 값)
        """
        # Given
        closes = pd.Series(np.exp(MACD_LOG_VALUES))

        # When
        result = log_macd_histogram(closes, fast_span=2, slow_span=3, signal_span=2)

        # Then
        assert result.iloc[:3].isna().all()
        assert result.iloc[3:].tolist() == pytest.approx([37 / 216, 797 / 3888], abs=1e-12)

    def test_rejects_fast_span_not_shorter_than_slow(self) -> None:
        """
        목적: 빠른 창이 느린 창보다 짧지 않으면 MACD 가 뒤집힌다 — 인자 순서 실수를 막는다.

        Given: 빠른 창 15 · 느린 창 5
        When: MACD − 시그널을 낸다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="빠른 창"):
            log_macd_histogram(pd.Series(np.exp(MACD_LOG_VALUES)), fast_span=15, slow_span=5, signal_span=9)


class TestOnchain:
    """MVRV-Z 와 NUPL"""

    def test_mvrv_z_uses_standard_deviation_up_to_that_day(self) -> None:
        """
        목적: MVRV-Z = (시가총액 − 실현 시가총액) ÷ **그날까지의** 시가총액 표본 표준편차 (결정 ㉓).

        실현 시가총액은 `시가총액 ÷ MVRV` 다.

        Given: 시가총액 10 · 20 · 30 · 40, MVRV 2 · 2 · 3 · 4, 최소 기간 3
        When: MVRV-Z 를 낸다
        Then: 앞 2개는 비고 (30 − 10) ÷ 10 = 2.0 · (40 − 10) ÷ 12.9099 = 2.3238 이다
        """
        # When
        result = mvrv_z(pd.Series([10.0, 20.0, 30.0, 40.0]), pd.Series([2.0, 2.0, 3.0, 4.0]), min_periods=3)

        # Then
        assert result.iloc[:2].isna().all()
        assert result.iloc[2:].tolist() == pytest.approx([2.0, 2.32379000772445], abs=1e-9)

    def test_mvrv_z_rejects_misaligned_inputs(self) -> None:
        """
        목적: 두 계열의 날짜가 다르면 계산하지 않는다 — 다른 날의 값끼리 나누면 예외 없이 틀린다.

        Given: 인덱스가 다른 시가총액과 MVRV
        When: MVRV-Z 를 낸다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="인덱스"):
            mvrv_z(pd.Series([1.0, 2.0], index=[0, 1]), pd.Series([1.0, 2.0], index=[1, 2]), min_periods=2)

    def test_nupl_is_one_minus_inverse_mvrv(self) -> None:
        """
        목적: NUPL = 1 − 1/MVRV — 0.75 는 MVRV 4 와 같다.

        Given: MVRV 2 · 4 · 0.5
        When: NUPL 을 낸다
        Then: 0.5 · 0.75 · −1.0
        """
        assert nupl(pd.Series([2.0, 4.0, 0.5])).tolist() == pytest.approx([0.5, 0.75, -1.0], abs=1e-12)


class TestIndicatorFrames:
    """확정된 창으로 한 번에 내는 두 표"""

    def test_daily_frame_is_on_price_days_and_leaves_missing_onchain_empty(self) -> None:
        """
        목적: 일간 지표 표가 **시세의 날짜** 위에 있고, 온체인 값이 없는 날은 비운다.

        Coin Metrics 는 공개 지연 하루를 허용해 받으므로 시세보다 하루 짧을 수 있다 — 그날을 메우지 않는다.

        Given: 2019-01-01 ~ 2020-12-31 시세, 온체인은 2018-01-01 ~ 2020-12-30 (하루 짧다)
        When: 일간 지표 표를 낸다
        Then: 인덱스가 시세의 날짜이고, 마지막 날의 온체인 지표 셋이 비어 있다
        """
        # Given
        prices = _daily_prices("2019-01-01", "2020-12-31")
        onchain_days = pd.date_range("2018-01-01", "2020-12-30", freq="D")
        onchain = pd.DataFrame(
            {
                COL_DATE: onchain_days,
                COL_MVRV: np.linspace(0.8, 3.0, len(onchain_days)),
                COL_MARKET_CAP: np.linspace(1e9, 5e9, len(onchain_days)),
            }
        )

        # When
        result = daily_indicator_frame(prices, onchain)

        # Then
        assert list(result.index) == list(prices[COL_DATE])
        assert set(result.columns) == {COL_PI_CYCLE, COL_DISPARITY, COL_MVRV, COL_MVRV_Z, COL_NUPL}
        assert result.iloc[-1][[COL_MVRV, COL_MVRV_Z, COL_NUPL]].isna().all()
        assert result.iloc[-2][[COL_MVRV, COL_MVRV_Z, COL_NUPL]].notna().all()

    def test_monthly_frame_has_rsi_and_macd_on_month_ends(self) -> None:
        """
        목적: 월간 지표 표가 끝난 달의 말일 위에 RSI 와 MACD − 시그널을 갖는다.

        Given: 2010-01-01 ~ 2013-06-15 매일 시세 (마지막 달은 끝나지 않았다)
        When: 월간 지표 표를 낸다
        Then: 마지막 행이 2013-05-31 이고 두 지표 컬럼이 있다
        """
        # When
        result = monthly_indicator_frame(_daily_prices("2010-01-01", "2013-06-15"))

        # Then
        assert result.index[-1] == pd.Timestamp("2013-05-31")
        assert {COL_MONTHLY_RSI, COL_MACD_HISTOGRAM} <= set(result.columns)


class TestLookAhead:
    """뒤를 자른 입력의 결과가 겹치는 구간에서 전체 입력과 같다 (`tests/CLAUDE.md` 필수)"""

    def test_mvrv_z_does_not_depend_on_later_days(self) -> None:
        """
        목적: MVRV-Z 가 그날 뒤의 시가총액에 기대지 않는다 — 전 기간 표준편차로 바뀌면 여기서 걸린다.

        Given: 400일 합성 시가총액 · MVRV
        When: 전체와 앞 250일로 각각 낸다
        Then: 앞 250일의 값이 같다
        """
        # Given
        rng = np.random.default_rng(20260929)
        market_cap = pd.Series(1e9 * np.cumprod(1.0 + rng.normal(0.002, 0.03, 400)))
        mvrv = pd.Series(1.0 + np.abs(rng.normal(0.5, 0.5, 400)))

        # When
        full = mvrv_z(market_cap, mvrv, min_periods=30)
        short = mvrv_z(market_cap.iloc[:250], mvrv.iloc[:250], min_periods=30)

        # Then
        pd.testing.assert_series_equal(full.iloc[:250], short, check_exact=False, rtol=1e-12)

    def test_price_indicators_do_not_depend_on_later_days(self) -> None:
        """
        목적: 일간 · 월간 가격 지표가 뒤의 시세에 기대지 않는다.

        월봉은 자른 입력에서 **끝난 달만** 견준다 — 자른 날이 달 중간이면 그 달은 짧은 입력에 없는 것이 정상이다.

        Given: 2010-01-01 ~ 2014-12-31 합성 시세
        When: 전체와 2013-07-15 까지로 각각 낸다
        Then: 짧은 입력에 있는 날 · 달의 값이 같다
        """
        # Given
        days = pd.date_range("2010-01-01", "2014-12-31", freq="D")
        rng = np.random.default_rng(20260930)
        prices = _daily_prices("2010-01-01", "2014-12-31", 100.0 * np.cumprod(1.0 + rng.normal(0.001, 0.03, len(days))))
        short_prices = prices[prices[COL_DATE] <= pd.Timestamp("2013-07-15")].reset_index(drop=True)
        onchain = pd.DataFrame(
            {COL_DATE: days, COL_MVRV: np.full(len(days), 2.0), COL_MARKET_CAP: prices[COL_CLOSE] * 1e6}
        )
        short_onchain = onchain[onchain[COL_DATE] <= pd.Timestamp("2013-07-15")]

        # When
        full_daily = daily_indicator_frame(prices, onchain)
        short_daily = daily_indicator_frame(short_prices, short_onchain)
        full_monthly = monthly_indicator_frame(prices)
        short_monthly = monthly_indicator_frame(short_prices)

        # Then
        pd.testing.assert_frame_equal(full_daily.loc[short_daily.index], short_daily, check_exact=False, rtol=1e-12)
        pd.testing.assert_frame_equal(
            full_monthly.loc[short_monthly.index], short_monthly, check_exact=False, rtol=1e-12
        )
