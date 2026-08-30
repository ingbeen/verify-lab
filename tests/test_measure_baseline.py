"""조건부 베이스라인 모집단(200일선 아래인 날) 판정을 고정한다.

이 판정은 "같은 국면 안에서 이 날이 특별한가"에 답하기 위한 비교군을 정한다.
모집단이 흔들리면 초과분이 통째로 흔들리므로, 이동평균 산식과 **창이 차기 전의 처리**를
손계산 값으로 박는다.

핵심 계약은 세 가지다.
- **단순 이동평균(SMA) 하나만 쓴다.** 보통 쓰는 것으로 고정해야 과최적화를 막는다
  (루트 `CLAUDE.md` 측정의 원칙 15)
- **창이 차기 전에는 판정하지 않는다.** 판정하지 못한 일수를 함께 돌려준다
- 뒤에 데이터가 더 붙어도 이미 지난 날의 판정이 달라지지 않는다 (look-ahead 감시)
"""

from collections.abc import Callable, Sequence

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.measure.baseline import DEFAULT_MA_WINDOW, below_moving_average


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


class TestMovingAverageJudgement:
    """이동평균 판정을 손계산 값으로 고정한다."""

    def test_sma_marks_days_below_the_simple_average(self) -> None:
        """
        목적: SMA 판정은 **종가 < 직전 N일 단순평균** 이다.

        Given: 종가 10 · 20 · 30 · 24 · 40, 창 3일
        When: SMA 로 판정한다
        Then: 4일차만 아래다
              (4일차 평균 = (20+30+24)/3 = 24.67 > 종가 24,
               3일차 평균 = 20 < 30, 5일차 평균 = 31.33 < 40)
        """
        # Given
        df = _market(DIVERGING_CLOSES)

        # When
        result = below_moving_average(df, window=3)

        # Then
        assert result.mask.tolist() == [False, False, False, True, False]

    def test_default_window_is_two_hundred(self) -> None:
        """
        목적: 창 200일은 스펙이 확정한 값이며 성과를 보며 돌리는 노브가 아니다.

        Given: 기본 창 상수
        When: 값을 확인한다
        Then: 200 이다
        """
        assert DEFAULT_MA_WINDOW == 200


class TestWindowShortage:
    """창이 차기 전의 처리를 고정한다 — 표본이 조용히 사라지는 지점이다."""

    def test_days_before_the_window_fills_are_not_judged(self) -> None:
        """
        목적: 창이 차기 전에는 판정하지 않는다. 판정하지 않은 날은 모집단에 넣지 않는다.

        Given: 창 3일
        When: 판정한다
        Then: 앞 2일은 False 이고, 판정 불가 건수가 2로 보고된다
        """
        # Given
        df = _market(DIVERGING_CLOSES)

        # When
        result = below_moving_average(df, window=3)

        # Then
        assert result.mask.tolist()[:2] == [False, False]
        assert result.undetermined_count == 2

    def test_window_longer_than_data_judges_nothing(self) -> None:
        """
        목적: 데이터보다 창이 길면 표본 0건이다 — 오류가 아니라 정상적인 결과다.

        Given: 5거래일 시세와 창 10일
        When: 판정한다
        Then: 아무 날도 아래로 잡히지 않고 전부 판정 불가로 보고된다
        """
        # Given
        df = _market(DIVERGING_CLOSES)

        # When
        result = below_moving_average(df, window=10)

        # Then
        assert not result.mask.any()
        assert result.undetermined_count == 5


class TestLookAhead:
    """미래 참조 감시 계약을 고정한다."""

    def test_truncated_input_gives_the_same_judgement(
        self, assert_stable_under_truncation: Callable[..., None]
    ) -> None:
        """
        목적: **look-ahead 감시** — 뒤에 데이터가 더 붙어도 지난 날의 판정이 달라지면 안 된다.

        Given: 12거래일 시세
        When: 앞 8일만 준 판정과 전체를 준 판정을 비교한다
        Then: 겹치는 구간의 판정이 같다
        """
        # Given
        df = _market([100.0, 120.0, 90.0, 110.0, 80.0, 130.0, 95.0, 105.0, 85.0, 115.0, 92.0, 108.0])

        def run(frame: pd.DataFrame) -> pd.DataFrame:
            result = below_moving_average(frame, window=3)
            return pd.DataFrame({COL_DATE: frame[COL_DATE], "Below": result.mask.astype(float)})

        # When / Then
        assert_stable_under_truncation(run, df, 8, key_columns=[COL_DATE], value_column="Below")


class TestInputValidation:
    """잘못된 입력을 조용히 넘기지 않음을 고정한다."""

    def test_rejects_empty_market(self) -> None:
        """
        목적: 빈 시세로는 판정이 성립하지 않는다.

        Given: 빈 시세
        When: 판정한다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="비어"):
            below_moving_average(_market([]), window=3)

    def test_rejects_missing_close_column(self) -> None:
        """
        목적: 종가가 없으면 이동평균을 낼 수 없다.

        Given: 종가 컬럼이 없는 시세
        When: 판정한다
        Then: ValueError
        """
        df = _market(DIVERGING_CLOSES)

        with pytest.raises(ValueError, match="필수 컬럼"):
            below_moving_average(df.drop(columns=[COL_CLOSE]), window=3)

    def test_rejects_unsorted_dates(self) -> None:
        """
        목적: 날짜가 뒤섞이면 이동평균이 조용히 어긋난다.

        Given: 날짜를 내림차순으로 뒤집은 시세
        When: 판정한다
        Then: ValueError
        """
        df = _market(DIVERGING_CLOSES)
        reversed_dates = df.assign(**{COL_DATE: df[COL_DATE].to_numpy()[::-1]})

        with pytest.raises(ValueError, match="오름차순"):
            below_moving_average(reversed_dates, window=3)

    def test_rejects_too_small_window(self) -> None:
        """
        목적: 창이 2 미만이면 이동평균이 종가 자신이 되어 판정이 무의미하다.

        Given: 창 1일
        When: 판정한다
        Then: ValueError
        """
        df = _market(DIVERGING_CLOSES)

        with pytest.raises(ValueError, match="창"):
            below_moving_average(df, window=1)

    def test_input_is_not_modified(self) -> None:
        """
        목적: 원본 데이터 불변성을 고정한다.

        Given: 시세
        When: 판정한다
        Then: 입력이 그대로다
        """
        # Given
        df = _market(DIVERGING_CLOSES)
        before = df.copy()

        # When
        below_moving_average(df, window=3)

        # Then
        pd.testing.assert_frame_equal(df, before)
