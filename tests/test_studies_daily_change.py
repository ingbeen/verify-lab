"""일간 등락률 단일 산식을 고정한다.

등락률은 테스트 A(역대급 등락)·테스트 B(연속 등락)·참고용 z-score 가 함께 쓴다.
**판정식 단일화** 원칙상 한 곳에만 있어야 하며, 이 값이 흔들리면 세 산출이 동시에 어긋난다.

고정하는 계약은 셋이다.
- 전일 종가 대비 비율이며, 전일이 없는 첫 행은 값이 없다
- **등락률이 정확히 0인 날이 실제로 존재한다** — QQQ 전 기간에 38건 있으며, 연속 판정에서
  방향을 부여하지 않는 근거가 된다
- 구조가 어긋난 입력은 조용히 넘기지 않고 예외를 던진다
"""

from collections.abc import Sequence

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.studies.index_extreme.daily_change import daily_change_rate

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12


def _market(closes: Sequence[float]) -> pd.DataFrame:
    """합성 시세를 만든다. 등락률은 종가만 보므로 나머지 가격 컬럼은 종가와 같게 둔다."""
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


# 상승·하락·보합을 한 번에 담은 종가. 손계산은 각 테스트 docstring 에 있다
MIXED_CLOSES = [100.0, 110.0, 99.0, 99.0]


class TestChangeRateFormula:
    """등락률 산식을 손계산 값으로 고정한다."""

    def test_computes_rate_against_previous_close(self) -> None:
        """
        목적: 등락률은 **전일 종가 대비 비율**이다 (0.03 = 3%).

        Given: 종가 100 · 110 · 99 · 99
        When: 등락률을 계산한다
        Then: 2일차 +0.10 (110/100−1), 3일차 −0.10 (99/110−1) 이다
        """
        # Given
        df = _market(MIXED_CLOSES)

        # When
        result = daily_change_rate(df)

        # Then
        assert result.iloc[1] == pytest.approx(0.10, abs=EXACT_TOLERANCE)
        assert result.iloc[2] == pytest.approx(99 / 110 - 1, abs=EXACT_TOLERANCE)

    def test_first_row_has_no_rate(self) -> None:
        """
        목적: 전일이 없는 첫 행은 등락률이 없다. 0 으로 채우면 "보합"으로 읽힌다.

        Given: 종가 4일치
        When: 등락률을 계산한다
        Then: 첫 행만 값이 없다
        """
        # Given
        df = _market(MIXED_CLOSES)

        # When
        result = daily_change_rate(df)

        # Then
        assert bool(result.isna().iloc[0])
        assert not result.iloc[1:].isna().any()

    def test_unchanged_close_gives_exactly_zero(self) -> None:
        """
        목적: 종가가 그대로면 등락률이 **정확히 0** 이다.

        국내 ETF 에서 실제로 발생하며, 연속 판정이 방향을 부여하지 않는 날의 근거다.

        Given: 3일차와 4일차 종가가 같은 시세
        When: 등락률을 계산한다
        Then: 4일차가 0 이다
        """
        # Given
        df = _market(MIXED_CLOSES)

        # When
        result = daily_change_rate(df)

        # Then
        assert result.iloc[3] == pytest.approx(0.0, abs=EXACT_TOLERANCE)

    def test_keeps_the_input_index(self) -> None:
        """
        목적: 반환 Series 는 시세와 같은 축을 쓴다 — 신호 판정이 위치로 대조되기 때문이다.

        Given: 시세
        When: 등락률을 계산한다
        Then: 인덱스가 시세와 같고 길이도 같다
        """
        # Given
        df = _market(MIXED_CLOSES)

        # When
        result = daily_change_rate(df)

        # Then
        assert result.index.equals(df.index)
        assert len(result) == len(df)


class TestInputValidation:
    """잘못된 입력을 조용히 넘기지 않음을 고정한다."""

    def test_rejects_empty_market(self) -> None:
        """
        목적: 빈 시세로는 등락률이 성립하지 않는다.

        Given: 빈 시세
        When: 등락률을 계산한다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="비어"):
            daily_change_rate(_market([]))

    def test_rejects_missing_close_column(self) -> None:
        """
        목적: 종가가 없으면 등락률을 낼 수 없다.

        Given: 종가 컬럼이 없는 시세
        When: 등락률을 계산한다
        Then: ValueError
        """
        df = _market(MIXED_CLOSES)

        with pytest.raises(ValueError, match="필수 컬럼"):
            daily_change_rate(df.drop(columns=[COL_CLOSE]))

    def test_rejects_unsorted_dates(self) -> None:
        """
        목적: 날짜가 뒤섞이면 전일이 전일이 아니게 되어 등락률이 조용히 어긋난다.

        Given: 날짜를 내림차순으로 뒤집은 시세
        When: 등락률을 계산한다
        Then: ValueError
        """
        df = _market(MIXED_CLOSES)
        reversed_dates = df.assign(**{COL_DATE: df[COL_DATE].to_numpy()[::-1]})

        with pytest.raises(ValueError, match="오름차순"):
            daily_change_rate(reversed_dates)

    def test_input_is_not_modified(self) -> None:
        """
        목적: 원본 데이터 불변성을 고정한다.

        Given: 시세
        When: 등락률을 계산한다
        Then: 입력이 그대로다
        """
        # Given
        df = _market(MIXED_CLOSES)
        before = df.copy()

        # When
        daily_change_rate(df)

        # Then
        pd.testing.assert_frame_equal(df, before)
