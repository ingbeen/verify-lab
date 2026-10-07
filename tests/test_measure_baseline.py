"""이동평균(SMA) 산식을 고정한다.

이 저장소의 이동평균은 `measure.baseline.simple_moving_average` 하나가 낸다. 지표마다 평균을 따로 내면
같은 원칙이 두 곳에서 다른 답을 내므로, 산식과 **창이 차기 전의 처리**를 손계산 값으로 박는다.

핵심 계약은 세 가지다.
- **단순 이동평균(SMA) 하나만 쓴다.** 보통 쓰는 것으로 고정해야 과최적화를 막는다
  (루트 `CLAUDE.md` 측정의 원칙 15)
- **창이 차기 전은 비운다.** 0 이나 첫 값으로 채우면 초기 구간이 평균처럼 읽힌다
- 뒤에 데이터가 더 붙어도 이미 지난 날의 평균이 달라지지 않는다 (look-ahead 감시)
"""

from collections.abc import Callable, Sequence

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.measure.baseline import DEFAULT_MA_WINDOW, simple_moving_average


def _market(closes: Sequence[float]) -> pd.DataFrame:
    """합성 시세를 만든다. 이동평균은 종가만 보므로 나머지 컬럼은 종가와 같게 둔다."""
    prices = list(closes)

    return pd.DataFrame(
        {
            COL_DATE: pd.bdate_range("2026-01-05", periods=len(prices)),
            COL_OPEN: prices,
            COL_HIGH: prices,
            COL_LOW: prices,
            COL_CLOSE: prices,
            COL_VOLUME: [1_000] * len(prices),
        }
    )


# 이동평균 판정이 갈리는 자리를 고른 종가. 손계산은 각 테스트 docstring 에 있다
DIVERGING_CLOSES = [10.0, 20.0, 30.0, 24.0, 40.0]


class TestDefaultWindow:
    """기본 창을 고정한다."""

    def test_default_window_is_two_hundred(self) -> None:
        """
        목적: 창 200일은 `docs/조사/역방향.md` 「확정된 설계 결정」 ⑦ 이 확정한 값이며 성과를 보며 돌리는 노브가 아니다.

        Given: 기본 창 상수
        When: 값을 확인한다
        Then: 200 이다
        """
        assert DEFAULT_MA_WINDOW == 200


class TestSimpleMovingAverage:
    """SMA 값 자체를 고정한다 — 측정의 원칙 15 가 모든 매매법에 요구하는 산식이라 한 곳에만 둔다."""

    def test_values_match_hand_calculation(self) -> None:
        """
        목적: SMA 는 직전 N일(그날 포함) 종가의 단순평균이다.

        Given: 종가 10 · 20 · 30 · 24 · 40, 창 3일
        When: SMA 를 낸다
        Then: 앞 2일은 비고 20 · 24.6667 · 31.3333 이다
        """
        # Given
        close = pd.Series(DIVERGING_CLOSES)

        # When
        result = simple_moving_average(close, window=3)

        # Then
        assert result.iloc[:2].isna().all()
        assert result.iloc[2:].tolist() == pytest.approx([20.0, 24.666666666666668, 31.333333333333332], abs=1e-12)

    def test_rejects_too_small_window(self) -> None:
        """
        목적: 창이 2 미만이면 평균이 값 자신이 된다.

        Given: 창 1일
        When: SMA 를 낸다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="창"):
            simple_moving_average(pd.Series(DIVERGING_CLOSES), window=1)

    def test_truncated_input_gives_the_same_average(self, assert_stable_under_truncation: Callable[..., None]) -> None:
        """
        목적: **look-ahead 감시** — 뒤에 데이터가 붙어도 지난 날의 평균이 달라지지 않는다.

        Given: 12거래일 시세
        When: 앞 8일만 준 SMA 와 전체를 준 SMA 를 비교한다
        Then: 겹치는 구간의 값이 같다
        """
        # Given
        df = _market([100.0, 120.0, 90.0, 110.0, 80.0, 130.0, 95.0, 105.0, 85.0, 115.0, 92.0, 108.0])

        def run(frame: pd.DataFrame) -> pd.DataFrame:
            return pd.DataFrame({COL_DATE: frame[COL_DATE], "Average": simple_moving_average(frame[COL_CLOSE], 3)})

        # When / Then
        assert_stable_under_truncation(run, df, 8, key_columns=[COL_DATE], value_column="Average")
