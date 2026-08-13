"""테스트 B(연속 등락)의 신호 판정을 고정한다.

신호일은 **N일 연속이 달성된 그날**이다. "연속 구간의 마지막 날"은 다음 날 주가를 봐야 알 수
있어 미래 참조가 되므로 채택하지 않는다 (스펙 §7 결정 ④).

고정하는 계약은 넷이다.
- 연속 길이가 **정확히 N** 인 날만 신호다. 7일 연속 랠리는 N=5 신호를 5일째에만 만든다
- **등락률이 정확히 0인 날은 연속을 끊되 방향을 부여하지 않는다** (스펙 §7 결정 ⑧)
- 연속 상승과 연속 하락을 분리 집계한다
- 뒤에 데이터가 더 붙어도 이미 지난 날의 판정이 달라지지 않는다 (look-ahead 감시)
"""

from collections.abc import Callable, Sequence

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.studies.index_extreme.consecutive import find_consecutive_events, signed_run_length
from verify_lab.studies.index_extreme.constants import CONSECUTIVE_LENGTHS, Direction


def _market(closes: Sequence[float]) -> pd.DataFrame:
    """합성 시세를 만든다. 연속 판정은 종가만 보므로 나머지 가격 컬럼은 종가와 같게 둔다."""
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


# 3일 연속 상승 → 보합 → 3일 연속 하락. 5일차 종가가 4일차와 같아 등락률이 정확히 0이다
TURNING_CLOSES = [100.0, 110.0, 121.0, 133.1, 133.1, 120.0, 108.0, 97.2]

# 5일 연속 상승. "정확히 N" 계약을 재는 데 쓴다
RALLY_CLOSES = [100.0, 110.0, 121.0, 133.1, 146.41, 161.051]


class TestRunLength:
    """부호 있는 연속 길이를 손계산 값으로 고정한다."""

    def test_counts_consecutive_days_with_a_direction_sign(self) -> None:
        """
        목적: 연속 길이에 방향 부호를 붙인다 (+3 = 3일 연속 상승, −3 = 3일 연속 하락).

        Given: 3일 연속 상승 → 보합 → 3일 연속 하락인 시세
        When: 연속 길이를 센다
        Then: 0 · 1 · 2 · 3 · 0 · −1 · −2 · −3 이다
        """
        # Given
        df = _market(TURNING_CLOSES)

        # When
        result = signed_run_length(df)

        # Then
        assert result.tolist() == [0, 1, 2, 3, 0, -1, -2, -3]

    def test_zero_change_breaks_the_run_without_a_direction(self) -> None:
        """
        목적: **등락률이 정확히 0인 날은 연속을 끊되 방향을 부여하지 않는다.**

        상승으로 간주하거나 무시하고 이어가면 어느 쪽이든 임의성이 생긴다.
        가장 보수적인 처리를 고정한다.

        Given: 5일차 종가가 4일차와 같은 시세
        When: 연속 길이를 센다
        Then: 5일차가 0 이고, 6일차가 −1 로 새로 시작한다
        """
        # Given
        df = _market(TURNING_CLOSES)

        # When
        result = signed_run_length(df)

        # Then
        assert result.iloc[4] == 0
        assert result.iloc[5] == -1

    def test_first_row_has_no_run(self) -> None:
        """
        목적: 첫 행은 등락률이 없어 연속이 시작되지 않는다.

        Given: 시세
        When: 연속 길이를 센다
        Then: 첫 행이 0 이다
        """
        # Given
        df = _market(TURNING_CLOSES)

        # When
        result = signed_run_length(df)

        # Then
        assert result.iloc[0] == 0


class TestEventJudgement:
    """N 판정과 방향 분리를 고정한다."""

    def test_marks_the_day_the_run_reaches_exactly_n(self) -> None:
        """
        목적: **연속 길이가 정확히 N 인 날만 신호다.**

        5일 연속 랠리는 N=3 신호를 3일째에만 만든다. 4·5일째까지 신호로 세면
        스펙 §8 의 발생 빈도표가 두 배 이상으로 부푼다.

        Given: 5일 연속 상승하는 시세
        When: N=3 연속 상승 신호를 판정한다
        Then: 4행(3일 연속이 달성된 날)만 신호다
        """
        # Given
        df = _market(RALLY_CLOSES)

        # When
        result = find_consecutive_events(df, direction=Direction.UP, length=3)

        # Then
        assert result.tolist() == [False, False, False, True, False, False]

    def test_the_same_rally_produces_one_signal_per_n(self) -> None:
        """
        목적: 같은 랠리가 N 마다 신호를 하나씩 만든다 — N 별 결과가 서로 독립이 아닌 이유다.

        Given: 5일 연속 상승하는 시세
        When: N=3 과 N=5 를 각각 판정한다
        Then: 서로 다른 하루씩만 신호가 된다
        """
        # Given
        df = _market(RALLY_CLOSES)

        # When
        three = find_consecutive_events(df, direction=Direction.UP, length=3)
        five = find_consecutive_events(df, direction=Direction.UP, length=5)

        # Then
        assert int(three.sum()) == 1
        assert int(five.sum()) == 1
        assert three.tolist() != five.tolist()

    def test_separates_up_from_down(self) -> None:
        """
        목적: 연속 상승과 연속 하락을 분리 집계한다 (스펙 §3).

        Given: 3일 연속 상승 → 보합 → 3일 연속 하락인 시세
        When: N=3 을 방향별로 판정한다
        Then: 상승은 4행, 하락은 8행이 신호다
        """
        # Given
        df = _market(TURNING_CLOSES)

        # When
        up = find_consecutive_events(df, direction=Direction.UP, length=3)
        down = find_consecutive_events(df, direction=Direction.DOWN, length=3)

        # Then
        assert up.tolist() == [False, False, False, True, False, False, False, False]
        assert down.tolist() == [False, False, False, False, False, False, False, True]

    def test_returns_a_bool_series_aligned_with_the_market(self) -> None:
        """
        목적: `studies` 가 공통 계층에 넘기는 것은 시세와 같은 축의 bool Series 하나다.

        Given: 시세
        When: 신호를 판정한다
        Then: dtype 이 bool 이고 인덱스가 시세와 같다
        """
        # Given
        df = _market(TURNING_CLOSES)

        # When
        result = find_consecutive_events(df, direction=Direction.UP, length=3)

        # Then
        assert result.dtype == bool
        assert result.index.equals(df.index)

    def test_consecutive_lengths_cover_three_to_ten(self) -> None:
        """
        목적: N=3~10 을 모두 산출한다는 스펙 §3 의 확정 값을 고정한다.

        Given: 상수
        When: 값을 확인한다
        Then: 3부터 10까지다
        """
        assert CONSECUTIVE_LENGTHS == (3, 4, 5, 6, 7, 8, 9, 10)


class TestAggregationStart:
    """집계 시작일 처리를 고정한다."""

    def test_days_before_the_start_date_are_not_signals(self) -> None:
        """
        목적: 집계 시작일 이전의 날은 신호로 세지 않는다.

        Given: 3일 연속 상승이 4행(2026-01-08)에 달성되는 시세
        When: 시작일을 그다음 날로 두고 판정한다
        Then: 신호가 없다
        """
        # Given
        df = _market(TURNING_CLOSES)

        # When
        result = find_consecutive_events(df, direction=Direction.UP, length=3, start_date=pd.Timestamp("2026-01-09"))

        # Then
        assert not result.any()

    def test_start_date_does_not_restart_the_run(self) -> None:
        """
        목적: 시작일 이전의 날도 연속 길이 누적에는 들어간다.

        Given: 3일 연속 하락이 8행에 달성되는 시세
        When: 하락이 시작된 뒤(6행 다음)를 시작일로 두고 판정한다
        Then: 8행이 그대로 신호다 — 연속이 시작일에서 다시 세어지지 않는다
        """
        # Given
        df = _market(TURNING_CLOSES)

        # When
        result = find_consecutive_events(df, direction=Direction.DOWN, length=3, start_date=pd.Timestamp("2026-01-13"))

        # Then
        assert result.tolist() == [False, False, False, False, False, False, False, True]


class TestBoundary:
    """경계 조건을 고정한다."""

    def test_run_reaching_the_last_row_is_a_signal(self) -> None:
        """
        목적: 연속 구간이 데이터 끝에 걸쳐도 신호다 — 그날 종가로 판정이 끝나기 때문이다.

        Given: 마지막 행에서 3일 연속 하락이 달성되는 시세
        When: 판정한다
        Then: 마지막 행이 신호다
        """
        # Given
        df = _market(TURNING_CLOSES)

        # When
        result = find_consecutive_events(df, direction=Direction.DOWN, length=3)

        # Then
        assert bool(result.iloc[-1])

    def test_run_shorter_than_n_gives_no_signal(self) -> None:
        """
        목적: 연속이 N 에 닿지 못하면 신호가 0건이다.

        Given: 최대 3일 연속인 시세
        When: N=4 로 판정한다
        Then: 신호가 없다
        """
        # Given
        df = _market(TURNING_CLOSES)

        # When
        result = find_consecutive_events(df, direction=Direction.UP, length=4)

        # Then
        assert not result.any()

    def test_single_row_market_gives_no_signal(self) -> None:
        """
        목적: 등락률을 낼 수 없는 최소 길이 데이터에서는 신호가 0건이다.

        Given: 1행짜리 시세
        When: 판정한다
        Then: 신호가 없다
        """
        # Given
        df = _market([100.0])

        # When
        result = find_consecutive_events(df, direction=Direction.UP, length=3)

        # Then
        assert not result.any()


class TestLookAhead:
    """미래 참조 감시 계약을 고정한다."""

    def test_truncated_input_gives_the_same_judgement(
        self, assert_stable_under_truncation: Callable[..., None]
    ) -> None:
        """
        목적: **look-ahead 감시** — 뒤에 데이터가 더 붙어도 지난 날의 판정이 달라지면 안 된다.

        "연속 구간의 마지막 날"로 정의했다면 이 테스트가 실패한다. 뒤를 자르면 그날이
        마지막인지가 달라지기 때문이며, 그것이 그 정의를 채택하지 않은 이유다.

        Given: 상승 3일 → 하락 3일 → 상승 4일이 이어지는 12거래일 시세
        When: 앞 8일만 준 판정과 전체를 준 판정을 비교한다
        Then: 겹치는 구간의 판정이 같다
        """
        # Given
        df = _market([100.0, 110.0, 121.0, 133.1, 120.0, 110.0, 100.0, 110.0, 121.0, 133.1, 146.41, 130.0])

        def run(frame: pd.DataFrame) -> pd.DataFrame:
            signals = find_consecutive_events(frame, direction=Direction.UP, length=3)
            return pd.DataFrame({COL_DATE: frame[COL_DATE], "IsEvent": signals.astype(float)})

        # When / Then
        assert_stable_under_truncation(run, df, 8, key_columns=[COL_DATE], value_column="IsEvent")


class TestInputValidation:
    """잘못된 입력을 조용히 넘기지 않음을 고정한다."""

    def test_rejects_empty_market(self) -> None:
        """
        목적: 빈 시세로는 연속 판정이 성립하지 않는다.

        Given: 빈 시세
        When: 연속 길이를 센다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="비어"):
            signed_run_length(_market([]))

    def test_rejects_length_below_two(self) -> None:
        """
        목적: 연속 1일은 연속이 아니다 — 그냥 상승일·하락일이다.

        Given: N=1
        When: 판정한다
        Then: ValueError
        """
        df = _market(TURNING_CLOSES)

        with pytest.raises(ValueError, match="연속 일수"):
            find_consecutive_events(df, direction=Direction.UP, length=1)

    def test_input_is_not_modified(self) -> None:
        """
        목적: 원본 데이터 불변성을 고정한다.

        Given: 시세
        When: 연속 길이를 세고 신호를 판정한다
        Then: 입력이 그대로다
        """
        # Given
        df = _market(TURNING_CLOSES)
        before = df.copy()

        # When
        signed_run_length(df)
        find_consecutive_events(df, direction=Direction.UP, length=3)

        # Then
        pd.testing.assert_frame_equal(df, before)
