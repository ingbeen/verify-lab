"""중간선거_사이클 — 진입 위치와 분할매수 조건에 쓰는 지표

**지표는 진입 위치 표와 분할매수 C 방식이 함께 쓴다.** 값이 틀리면 두 표가 같이 틀리고
그럴듯한 숫자가 나오므로, 손으로 계산한 예시로 값을 박는다.

| 지표 | 계약 |
| --- | --- |
| RSI | **Wilder 방식** — 첫 평균은 단순평균, 그 뒤는 `(직전 × (N−1) + 오늘) ÷ N`. 증권앱·차트가 보여 주는 값이다 |
| 이격도 | 종가 ÷ SMA. SMA 는 `measure.baseline.simple_moving_average` 하나가 낸다 |
| 52주 최고 대비 | 종가 ÷ (그날 포함 N거래일 최고 종가) − 1 |

**창이 차기 전에는 비운다** — 0 이나 첫 값으로 채우면 「그때 고점이었다」 같은 없는 사실이 된다.
**셋 다 그날까지의 종가만 쓴다** — look-ahead 감시를 지표마다 건다.
"""

from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_VALUE
from verify_lab.measure.baseline import simple_moving_average
from verify_lab.studies.midterm_cycle.constants import (
    COL_DISPARITY_LONG,
    COL_DISPARITY_SHORT,
    COL_HIGH_DISTANCE,
    COL_RSI,
    HIGH_LOOKBACK_DAYS,
    LONG_MA_WINDOW,
    RSI_WINDOW,
    SHORT_MA_WINDOW,
)
from verify_lab.studies.midterm_cycle.indicators import disparity, distance_from_high, indicator_frame, wilder_rsi

# RSI 손계산 예시. 창 3일에서 등락이 +1 · −1 · +2 · +1 · −1 이다
RSI_CLOSES = [10.0, 11.0, 10.0, 12.0, 13.0, 12.0]

# 이격도·고점 거리 손계산 예시. 창 3일
LEVEL_CLOSES = [10.0, 20.0, 30.0, 24.0, 40.0]

# 합성 시세 시드. **시드 없는 난수는 금지다**
SYNTHETIC_SEED = 20260923


def _walk(length: int) -> pd.Series:
    """장기 창을 채울 만큼 긴 합성 종가를 만든다.

    Args:
        length: 거래일 수

    Returns:
        양수 종가 계열
    """
    rng = np.random.default_rng(SYNTHETIC_SEED)
    return pd.Series(100.0 * np.cumprod(1.0 + rng.normal(0.0003, 0.012, length)))


class TestWilderRsi:
    """RSI 를 손계산 값으로 고정한다"""

    def test_values_match_hand_calculation(self) -> None:
        """
        목적: Wilder RSI 산식을 박는다.

        Given: 종가 10 · 11 · 10 · 12 · 13 · 12, 창 3일
        When: RSI 를 낸다
        Then: 앞 3일은 비고 75.0 · 81.8182 · 58.0645 다
              (첫 평균 = 상승 (1+0+2)/3 = 1 · 하락 (0+1+0)/3 = 1/3 → 100 × 1 ÷ (1+1/3) = 75,
               다음 날 상승 (1×2+1)/3 = 1 · 하락 (1/3×2+0)/3 = 2/9 → 100 × 1 ÷ (1+2/9) = 81.82,
               그다음 날 상승 (1×2+0)/3 = 2/3 · 하락 (2/9×2+1)/3 = 13/27 → 100 × 18/31 = 58.06)
        """
        # Given
        close = pd.Series(RSI_CLOSES)

        # When
        result = wilder_rsi(close, window=3)

        # Then
        assert result.iloc[:3].isna().all()
        assert result.iloc[3:].tolist() == pytest.approx([75.0, 81.81818181818181, 58.06451612903225], abs=1e-9)

    def test_only_rises_gives_one_hundred(self) -> None:
        """
        목적: 하락이 한 번도 없으면 RSI 는 100 이다 — 0 으로 나누는 자리를 조용히 넘기지 않는다.

        Given: 계속 오르는 종가, 창 3일
        When: RSI 를 낸다
        Then: 창이 찬 날부터 100 이다
        """
        # When
        result = wilder_rsi(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), window=3)

        # Then
        assert result.iloc[3:].tolist() == pytest.approx([100.0, 100.0], abs=1e-12)

    def test_flat_series_is_undefined(self) -> None:
        """
        목적: 등락이 전혀 없으면 RSI 가 정의되지 않는다 — 50 이나 100 으로 채우지 않는다.

        Given: 전 구간 같은 종가, 창 3일
        When: RSI 를 낸다
        Then: 전부 비어 있다
        """
        # When
        result = wilder_rsi(pd.Series([5.0] * 6), window=3)

        # Then
        assert result.isna().all()

    def test_series_shorter_than_window_is_all_empty(self) -> None:
        """
        목적: 창이 차지 않으면 한 칸도 내지 않는다 (경계 조건).

        Given: 3거래일 종가, 창 3일 — 등락은 둘뿐이다
        When: RSI 를 낸다
        Then: 전부 비어 있다
        """
        # When
        result = wilder_rsi(pd.Series([1.0, 2.0, 3.0]), window=3)

        # Then
        assert result.isna().all()

    def test_rejects_too_small_window(self) -> None:
        """
        목적: 창이 2 미만이면 평균이 성립하지 않는다.

        Given: 창 1일
        When: RSI 를 낸다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="창"):
            wilder_rsi(pd.Series(RSI_CLOSES), window=1)


class TestDisparityAndHighDistance:
    """이격도와 52주 최고 대비 거리를 손계산 값으로 고정한다"""

    def test_disparity_is_close_over_sma(self) -> None:
        """
        목적: 이격도 = 종가 ÷ SMA. **SMA 를 따로 계산하지 않는다** — 공통 함수와 값이 같아야 한다.

        Given: 종가 10 · 20 · 30 · 24 · 40, 창 3일
        When: 이격도를 낸다
        Then: 앞 2일은 비고 1.5 · 0.97297 · 1.27660 이며, 종가 ÷ 공통 SMA 와 같다
        """
        # Given
        close = pd.Series(LEVEL_CLOSES)

        # When
        result = disparity(close, window=3)

        # Then
        assert result.iloc[:2].isna().all()
        assert result.iloc[2:].tolist() == pytest.approx([1.5, 0.9729729729729729, 1.2765957446808511], abs=1e-12)
        expected = close / simple_moving_average(close, window=3)
        assert result.iloc[2:].tolist() == pytest.approx(expected.iloc[2:].tolist(), abs=1e-12)

    def test_distance_from_high_is_zero_or_below(self) -> None:
        """
        목적: 고점 대비 거리는 그날을 포함한 창의 최고 종가로 잰다 — 신고가인 날은 0 이다.

        Given: 종가 10 · 20 · 30 · 24 · 40, 창 3일
        When: 고점 대비 거리를 낸다
        Then: 앞 2일은 비고 0 · −0.2 · 0 이다 (24 ÷ 30 − 1 = −0.2)
        """
        # When
        result = distance_from_high(pd.Series(LEVEL_CLOSES), window=3)

        # Then
        assert result.iloc[:2].isna().all()
        assert result.iloc[2:].tolist() == pytest.approx([0.0, -0.2, 0.0], abs=1e-12)

    def test_distance_rejects_too_small_window(self) -> None:
        """
        목적: 창이 2 미만이면 언제나 0 이라 정보가 없다.

        Given: 창 1일
        When: 고점 대비 거리를 낸다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="창"):
            distance_from_high(pd.Series(LEVEL_CLOSES), window=1)


class TestIndicatorFrame:
    """한 대상의 지표 넷을 한 번에 낸다 — 진입 위치 표와 분할매수 C 가 같은 값을 본다"""

    def test_columns_follow_the_fixed_windows(self) -> None:
        """
        목적: 지표 표의 각 컬럼이 확정된 창으로 계산된다 — 창을 호출부마다 넘기지 않는다.

        Given: 창을 다 채울 만큼 긴 합성 종가
        When: 지표 표를 낸다
        Then: 네 컬럼이 개별 함수를 확정 창으로 부른 값과 같다
        """
        # Given
        close = _walk(HIGH_LOOKBACK_DAYS + 60)
        frame = pd.DataFrame({COL_DATE: pd.bdate_range("2020-01-01", periods=len(close)), COL_CLOSE: close})

        # When
        result = indicator_frame(frame, price_column=COL_CLOSE)

        # Then
        pd.testing.assert_series_equal(result[COL_RSI], wilder_rsi(close, RSI_WINDOW), check_names=False)
        pd.testing.assert_series_equal(
            result[COL_DISPARITY_SHORT], disparity(close, SHORT_MA_WINDOW), check_names=False
        )
        pd.testing.assert_series_equal(result[COL_DISPARITY_LONG], disparity(close, LONG_MA_WINDOW), check_names=False)
        pd.testing.assert_series_equal(
            result[COL_HIGH_DISTANCE], distance_from_high(close, HIGH_LOOKBACK_DAYS), check_names=False
        )

    def test_reads_the_given_price_column(self) -> None:
        """
        목적: 지수는 `Value` 컬럼이다 — 종가 컬럼을 하드코딩하면 지수에서 `KeyError` 가 난다.

        Given: `Value` 하나뿐인 지수 계열
        When: 가격 컬럼을 `Value` 로 넘겨 지표 표를 낸다
        Then: RSI 가 그 컬럼으로 계산된다
        """
        # Given
        values = _walk(60)
        frame = pd.DataFrame({COL_DATE: pd.bdate_range("2020-01-01", periods=len(values)), COL_VALUE: values})

        # When
        result = indicator_frame(frame, price_column=COL_VALUE)

        # Then
        pd.testing.assert_series_equal(result[COL_RSI], wilder_rsi(values, RSI_WINDOW), check_names=False)

    def test_input_is_not_modified(self) -> None:
        """
        목적: 원본 데이터 불변성.

        Given: 합성 시세
        When: 지표 표를 낸다
        Then: 입력이 그대로다
        """
        # Given
        close = _walk(40)
        frame = pd.DataFrame({COL_DATE: pd.bdate_range("2020-01-01", periods=len(close)), COL_CLOSE: close})
        before = frame.copy()

        # When
        indicator_frame(frame, price_column=COL_CLOSE)

        # Then
        pd.testing.assert_frame_equal(frame, before)


class TestLookAhead:
    """지표마다 look-ahead 감시를 건다 (`tests/CLAUDE.md` 필수)"""

    @pytest.mark.parametrize("column", [COL_RSI, COL_DISPARITY_SHORT, COL_DISPARITY_LONG, COL_HIGH_DISTANCE])
    def test_truncated_input_gives_the_same_values(
        self, column: str, assert_stable_under_truncation: Callable[..., None]
    ) -> None:
        """
        목적: 뒤에 데이터가 붙어도 지난 날의 지표 값이 달라지지 않는다.

        Given: 장기 창을 채우는 합성 시세
        When: 앞부분만 준 지표와 전체를 준 지표를 비교한다
        Then: 겹치는 구간의 값이 같다
        """
        # Given
        close = _walk(HIGH_LOOKBACK_DAYS + 80)
        frame = pd.DataFrame({COL_DATE: pd.bdate_range("2020-01-01", periods=len(close)), COL_CLOSE: close})

        def run(market: pd.DataFrame) -> pd.DataFrame:
            values = indicator_frame(market, price_column=COL_CLOSE)[column]
            return pd.DataFrame({COL_DATE: market[COL_DATE], "Value": values})

        # When / Then
        assert_stable_under_truncation(
            run, frame, HIGH_LOOKBACK_DAYS + 20, key_columns=[COL_DATE], value_column="Value"
        )
