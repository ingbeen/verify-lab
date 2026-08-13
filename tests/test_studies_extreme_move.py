"""테스트 A(역대급 등락)의 확장창 순위 판정을 고정한다.

이 프로젝트에서 **look-ahead 가 가장 쉽게 섞이는 지점**이다. 전체 기간을 한 번에 보고 순위를
매기면 결과가 좋아지고, 눈으로는 발견되지 않는다. 순위는 판정일까지 누적된 등락률로만 매긴다.

고정하는 계약은 넷이다.
- 순위는 **자기보다 극단인 날의 수 + 1** 이다. 동률은 같은 순위를 받는다
- **집계 시작일 이전의 날은 신호가 아니지만 순위 축적에는 들어간다.** 시세를 먼저 잘라 넘기면
  순위가 그 지점부터 다시 쌓여 예외 없이 틀린 결과가 나오므로, 시작일을 함수가 직접 받는다
- 폭등과 폭락을 분리 집계한다
- 뒤에 데이터가 더 붙어도 이미 지난 날의 판정이 달라지지 않는다 (look-ahead 감시)
"""

from collections.abc import Callable, Sequence

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.studies.index_extreme.constants import DEFAULT_RANK_CUT, RANK_CUTS, Direction
from verify_lab.studies.index_extreme.extreme_move import (
    COL_PLUNGE_RANK,
    COL_SURGE_RANK,
    expanding_rank,
    find_extreme_move_events,
)

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12


def _market(closes: Sequence[float]) -> pd.DataFrame:
    """합성 시세를 만든다. 순위 판정은 종가만 보므로 나머지 가격 컬럼은 종가와 같게 둔다."""
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


# 등락률이 +5% · −4.76% · 0% · +10% · −10% 로 흐르는 종가.
# 날짜는 2026-01-05 부터의 영업일이므로 6일차는 2026-01-12 다
RANKED_CLOSES = [100.0, 105.0, 100.0, 100.0, 110.0, 99.0]


class TestExpandingRank:
    """확장창 순위 산식을 손계산 값으로 고정한다."""

    def test_ranks_only_against_days_up_to_the_judgement_day(self) -> None:
        """
        목적: 순위는 **판정일까지 누적된 등락률 안에서**만 매긴다.

        Given: 등락률이 +5% · −4.76% · 0% · +10% · −10% 인 시세
        When: 확장창 순위를 매긴다
        Then: 폭등 순위가 1 · 2 · 2 · 1 · 5 다
              (5일차 +10% 는 그때까지 자기보다 큰 날이 없어 1위,
               6일차 −10% 는 위에 +5% · −4.76% · 0% · +10% 넷이 있어 5위)
        """
        # Given
        df = _market(RANKED_CLOSES)

        # When
        result = expanding_rank(df)

        # Then
        assert result[COL_SURGE_RANK].tolist()[1:] == [1, 2, 2, 1, 5]

    def test_plunge_rank_counts_days_that_fell_further(self) -> None:
        """
        목적: 폭락 순위는 **자기보다 더 떨어진 날의 수 + 1** 이다.

        Given: 같은 시세
        When: 확장창 순위를 매긴다
        Then: 폭락 순위가 1 · 1 · 2 · 4 · 1 이다
              (5일차 +10% 는 아래에 +5% · −4.76% · 0% 셋이 있어 4위,
               6일차 −10% 는 그때까지 더 떨어진 날이 없어 1위)
        """
        # Given
        df = _market(RANKED_CLOSES)

        # When
        result = expanding_rank(df)

        # Then
        assert result[COL_PLUNGE_RANK].tolist()[1:] == [1, 1, 2, 4, 1]

    def test_first_row_has_no_rank(self) -> None:
        """
        목적: 첫 행은 등락률이 없으므로 순위도 없다. 0 이나 1 로 채우면 신호가 될 수 있다.

        Given: 시세
        When: 확장창 순위를 매긴다
        Then: 첫 행의 두 순위가 모두 비어 있다
        """
        # Given
        df = _market(RANKED_CLOSES)

        # When
        result = expanding_rank(df)

        # Then
        assert bool(result[COL_SURGE_RANK].isna().iloc[0])
        assert bool(result[COL_PLUNGE_RANK].isna().iloc[0])

    def test_equal_change_rates_share_the_same_rank(self) -> None:
        """
        목적: **동률은 같은 순위**를 받는다.

        국내 원본가는 정수 가격이라 같은 등락률이 실제로 나올 수 있다. 동률에 순번을 매기면
        나중 날이 컷 밖으로 밀려 신호 수가 조용히 달라진다.

        Given: 등락률이 +10% 로 두 번 같은 시세
        When: 확장창 순위를 매긴다
        Then: 두 날 모두 폭등 1위다
        """
        # Given
        df = _market([100.0, 110.0, 121.0])

        # When
        result = expanding_rank(df)

        # Then
        assert result[COL_SURGE_RANK].tolist()[1:] == [1, 1]


class TestEventJudgement:
    """순위 컷 판정과 방향 분리를 고정한다."""

    def test_marks_days_within_the_rank_cut(self) -> None:
        """
        목적: 판정 시점 순위가 컷 이내인 날만 신호다.

        Given: 폭등 순위가 1 · 2 · 2 · 1 · 4 인 시세, 컷 1위
        When: 폭등 신호를 판정한다
        Then: 2일차와 5일차만 신호다
        """
        # Given
        df = _market(RANKED_CLOSES)

        # When
        result = find_extreme_move_events(df, direction=Direction.UP, rank_cut=1)

        # Then
        assert result.tolist() == [False, True, False, False, True, False]

    def test_separates_surge_from_plunge(self) -> None:
        """
        목적: 폭등과 폭락을 분리 집계한다 (스펙 §3).

        Given: 같은 시세와 같은 컷 1위
        When: 폭락 신호를 판정한다
        Then: 폭등 신호와 다른 날이 잡힌다
        """
        # Given
        df = _market(RANKED_CLOSES)

        # When
        surge = find_extreme_move_events(df, direction=Direction.UP, rank_cut=1)
        plunge = find_extreme_move_events(df, direction=Direction.DOWN, rank_cut=1)

        # Then
        assert plunge.tolist() == [False, True, True, False, False, True]
        assert surge.tolist() != plunge.tolist()

    def test_returns_a_bool_series_aligned_with_the_market(self) -> None:
        """
        목적: `studies` 가 공통 계층에 넘기는 것은 시세와 같은 축의 bool Series 하나다.

        Given: 시세
        When: 신호를 판정한다
        Then: dtype 이 bool 이고 인덱스가 시세와 같다
        """
        # Given
        df = _market(RANKED_CLOSES)

        # When
        result = find_extreme_move_events(df, direction=Direction.UP, rank_cut=1)

        # Then
        assert result.dtype == bool
        assert result.index.equals(df.index)

    def test_default_rank_cut_is_ten(self) -> None:
        """
        목적: 메인 컷 10위는 스펙이 확정한 값이고 5·20 은 강건성 확인용이다.

        Given: 상수
        When: 값을 확인한다
        Then: 기본값이 10 이고 컷 목록에 5·10·20 이 있다
        """
        assert DEFAULT_RANK_CUT == 10
        assert RANK_CUTS == (5, 10, 20)


class TestAggregationStart:
    """집계 시작일 처리를 고정한다 — 이 조각에서 가장 틀리기 쉬운 지점이다."""

    def test_days_before_the_start_date_are_not_signals(self) -> None:
        """
        목적: 집계 시작일 이전의 날은 신호로 세지 않는다 (순위 축적 구간).

        Given: 컷 2위, 시작일이 3일차(2026-01-07)
        When: 폭등 신호를 판정한다
        Then: 순위가 2위 이내인 2일차가 시작일 이전이라 신호에서 빠진다
        """
        # Given
        df = _market(RANKED_CLOSES)

        # When
        result = find_extreme_move_events(df, direction=Direction.UP, rank_cut=2, start_date=pd.Timestamp("2026-01-07"))

        # Then
        assert result.tolist() == [False, False, True, True, True, False]

    def test_start_date_does_not_restart_rank_accumulation(self) -> None:
        """
        목적: **시작일 이전의 날도 순위 축적에는 들어간다.**

        시세를 먼저 잘라 넘기면 순위가 그 지점부터 다시 쌓여 예외 없이 다른 결과가 나온다.
        그 사고를 구조로 막으려고 시작일을 함수가 직접 받는다.

        Given: 같은 컷·같은 시작일
        When: 시작일을 함수에 넘긴 결과와, 시세를 먼저 자른 뒤 판정한 결과를 비교한다
        Then: 두 결과가 다르다 — 자른 쪽은 앞 구간의 등락률을 잃어 순위가 달라진다
        """
        # Given
        df = _market(RANKED_CLOSES)
        sliced = df.iloc[2:].reset_index(drop=True)

        # When
        with_start = find_extreme_move_events(
            df, direction=Direction.UP, rank_cut=2, start_date=pd.Timestamp("2026-01-07")
        )
        after_slicing = find_extreme_move_events(sliced, direction=Direction.UP, rank_cut=2)

        # Then
        assert with_start.tolist()[2:] != after_slicing.tolist()

    def test_start_date_after_the_last_day_gives_no_signal(self) -> None:
        """
        목적: 시작일이 데이터 뒤에 있으면 신호 0건이다 — 오류가 아니라 정상적인 측정 결과다.

        Given: 데이터 마지막 날보다 뒤인 시작일
        When: 신호를 판정한다
        Then: 신호가 하나도 없다
        """
        # Given
        df = _market(RANKED_CLOSES)

        # When
        result = find_extreme_move_events(
            df, direction=Direction.UP, rank_cut=10, start_date=pd.Timestamp("2027-01-01")
        )

        # Then
        assert not result.any()


class TestBoundary:
    """경계 조건을 고정한다."""

    def test_single_row_market_gives_no_signal(self) -> None:
        """
        목적: 등락률을 낼 수 없는 최소 길이 데이터에서는 신호가 0건이다.

        Given: 1행짜리 시세
        When: 신호를 판정한다
        Then: 신호가 없다
        """
        # Given
        df = _market([100.0])

        # When
        result = find_extreme_move_events(df, direction=Direction.UP, rank_cut=10)

        # Then
        assert not result.any()

    def test_rank_cut_wider_than_data_marks_every_judged_day(self) -> None:
        """
        목적: 컷이 데이터보다 넓으면 등락률이 있는 날이 모두 신호가 된다.

        Given: 컷 100위
        When: 폭등 신호를 판정한다
        Then: 첫 행을 뺀 모든 날이 신호다
        """
        # Given
        df = _market(RANKED_CLOSES)

        # When
        result = find_extreme_move_events(df, direction=Direction.UP, rank_cut=100)

        # Then
        assert result.tolist() == [False, True, True, True, True, True]


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
            signals = find_extreme_move_events(frame, direction=Direction.UP, rank_cut=3)
            return pd.DataFrame({COL_DATE: frame[COL_DATE], "IsEvent": signals.astype(float)})

        # When / Then
        assert_stable_under_truncation(run, df, 8, key_columns=[COL_DATE], value_column="IsEvent")

    def test_truncated_input_gives_the_same_rank(self, assert_stable_under_truncation: Callable[..., None]) -> None:
        """
        목적: 순위 자체도 미래를 참조하지 않는다 — 신호일 목록의 "당시 순위" 컬럼이 된다.

        Given: 12거래일 시세
        When: 앞 8일만 준 순위와 전체를 준 순위를 비교한다
        Then: 겹치는 구간의 순위가 같다
        """
        # Given
        df = _market([100.0, 120.0, 90.0, 110.0, 80.0, 130.0, 95.0, 105.0, 85.0, 115.0, 92.0, 108.0])

        # When / Then
        assert_stable_under_truncation(expanding_rank, df, 8, key_columns=[COL_DATE], value_column=COL_SURGE_RANK)


class TestInputValidation:
    """잘못된 입력을 조용히 넘기지 않음을 고정한다."""

    def test_rejects_empty_market(self) -> None:
        """
        목적: 빈 시세로는 순위가 성립하지 않는다.

        Given: 빈 시세
        When: 순위를 매긴다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="비어"):
            expanding_rank(_market([]))

    def test_rejects_non_positive_rank_cut(self) -> None:
        """
        목적: 컷이 1 미만이면 어떤 날도 신호가 될 수 없어 판정이 무의미하다.

        Given: 컷 0위
        When: 신호를 판정한다
        Then: ValueError
        """
        df = _market(RANKED_CLOSES)

        with pytest.raises(ValueError, match="순위 컷"):
            find_extreme_move_events(df, direction=Direction.UP, rank_cut=0)

    def test_input_is_not_modified(self) -> None:
        """
        목적: 원본 데이터 불변성을 고정한다.

        Given: 시세
        When: 순위를 매기고 신호를 판정한다
        Then: 입력이 그대로다
        """
        # Given
        df = _market(RANKED_CLOSES)
        before = df.copy()

        # When
        expanding_rank(df)
        find_extreme_move_events(df, direction=Direction.UP, rank_cut=2)

        # Then
        pd.testing.assert_frame_equal(df, before)
