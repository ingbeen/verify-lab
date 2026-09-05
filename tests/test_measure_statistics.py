"""통계 집계·초과분·유의성 검정의 계약을 고정한다.

이 계층에서 가장 조용히 틀릴 수 있는 것은 **무엇을 표본으로 세는가** 다. 제외된 칸까지 세면
표본이 부풀고 평균이 왜곡되는데, 결과만 보면 그럴듯해 보인다. 그래서 표본 세는 규칙과
산식을 손계산 값으로 박는다.

핵심 계약은 네 가지다.
- 제외된 칸은 표본이 아니다 (`유효 표본 = 신호 수 − 제외 수`)
- 수익률이 정확히 0인 날은 승리가 아니다
- 초과분은 **통계량끼리 대응해 뺀 값**이다 (중앙값의 차이이지 차이의 중앙값이 아니다)
- **유효 표본이 한 자릿수인 칸에는 검정을 붙이지 않는다.** 숫자를 만들어내는 것이 더 나쁘다
"""

from collections.abc import Sequence

import numpy as np
import pandas as pd
import pytest

from verify_lab.common_constants import COL_DATE
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_EXCLUDED_COUNT,
    COL_EXCLUDED_REASON,
    COL_FORWARD_RETURN,
    COL_HORIZON,
    COL_SIGNAL_COUNT,
    MIN_SAMPLE_PER_CELL,
    REASON_NONE,
    REASON_OUT_OF_RANGE,
)
from verify_lab.measure.forward_return import ReturnBasis
from verify_lab.measure.statistics import (
    COL_BASELINE_SAMPLE_COUNT,
    COL_DOWN_RATE_P_VALUE,
    COL_DOWN_RATE_PERCENTILE,
    COL_LOSS_RATE,
    COL_LOSS_RATE_EXCESS,
    COL_MAX,
    COL_MEAN,
    COL_MEAN_EXCESS,
    COL_MEAN_P_VALUE,
    COL_MEAN_PERCENTILE,
    COL_MEDIAN,
    COL_MEDIAN_EXCESS,
    COL_MEDIAN_P_VALUE,
    COL_MEDIAN_PERCENTILE,
    COL_MIN,
    COL_OBSERVED_DOWN_RATE,
    COL_OBSERVED_MEAN,
    COL_OBSERVED_UP_RATE,
    COL_SAMPLE_COUNT,
    COL_SIGNAL_SAMPLE_COUNT,
    COL_STD,
    COL_TEST_NOTE,
    COL_UP_RATE_P_VALUE,
    COL_UP_RATE_PERCENTILE,
    COL_WIN_RATE,
    COL_WIN_RATE_EXCESS,
    EXCESS_COLUMNS,
    NOTE_NONE,
    NOTE_POPULATION_NOT_LARGER,
    NOTE_TOO_FEW_SAMPLES,
    SUMMARY_COLUMNS,
    TEST_COLUMNS,
    excess,
    max_non_overlapping,
    permutation_test,
    summarize,
)

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12


def _cell(
    values: Sequence[float | None],
    basis: ReturnBasis = ReturnBasis.CLOSE,
    horizon: int = 1,
) -> pd.DataFrame:
    """한 칸(기준 × 구간)짜리 long-form 프레임을 만든다. `None` 은 제외된 칸이다."""
    return pd.DataFrame(
        {
            COL_DATE: pd.bdate_range("2026-01-05", periods=len(values)),
            COL_BASIS: basis.value,
            COL_HORIZON: horizon,
            COL_FORWARD_RETURN: [np.nan if value is None else value for value in values],
            COL_EXCLUDED_REASON: [REASON_OUT_OF_RANGE if value is None else REASON_NONE for value in values],
        }
    )


def _only(frame: pd.DataFrame, column: str) -> float:
    """한 칸짜리 결과에서 값 하나를 꺼낸다."""
    return float(frame[column].iloc[0])


class TestSummarize:
    """집계 산식과 표본 세는 규칙을 고정한다."""

    def test_matches_hand_calculation(self) -> None:
        """
        목적: 평균·중앙값·최고·최악·표준편차를 손계산 값으로 고정한다.

        Given: 수익률 +10% · −5% · 0% · +20%
        When: 집계한다
        Then: 평균 6.25%, 중앙값 5%(가운데 두 값 0%와 10%의 평균), 최고 20%, 최악 −5%,
              표준편차 = √(편차제곱합 0.036875 ÷ 3)
        """
        # Given
        frame = _cell([0.10, -0.05, 0.0, 0.20])

        # When
        summary = summarize(frame)

        # Then
        assert _only(summary, COL_MEAN) == pytest.approx(0.0625, abs=EXACT_TOLERANCE)
        assert _only(summary, COL_MEDIAN) == pytest.approx(0.05, abs=EXACT_TOLERANCE)
        assert _only(summary, COL_MAX) == pytest.approx(0.20, abs=EXACT_TOLERANCE)
        assert _only(summary, COL_MIN) == pytest.approx(-0.05, abs=EXACT_TOLERANCE)
        assert _only(summary, COL_STD) == pytest.approx((0.036875 / 3) ** 0.5, abs=EXACT_TOLERANCE)

    def test_excluded_rows_are_not_counted_as_sample(self) -> None:
        """
        목적: **제외된 칸은 표본이 아니다.** 세면 표본이 부풀고 평균이 왜곡된다.

        Given: 값이 있는 행 2개와 제외된 행 1개
        When: 집계한다
        Then: 신호 3건 · 제외 1건 · 유효 표본 2건이고, 평균은 남은 두 값의 평균이다
        """
        # Given
        frame = _cell([0.10, None, 0.20])

        # When
        summary = summarize(frame)

        # Then
        assert int(_only(summary, COL_SIGNAL_COUNT)) == 3
        assert int(_only(summary, COL_EXCLUDED_COUNT)) == 1
        assert int(_only(summary, COL_SAMPLE_COUNT)) == 2
        assert _only(summary, COL_MEAN) == pytest.approx(0.15, abs=EXACT_TOLERANCE)

    def test_zero_return_is_not_a_win(self) -> None:
        """
        목적: 승률은 **양수 비율**이다. 정확히 0인 날은 승리가 아니다.

        Given: 수익률이 0%인 날 둘
        When: 집계한다
        Then: 승률이 0이다
        """
        # Given
        frame = _cell([0.0, 0.0])

        # When
        summary = summarize(frame)

        # Then
        assert _only(summary, COL_WIN_RATE) == pytest.approx(0.0, abs=EXACT_TOLERANCE)

    def test_loss_rate_is_counted_separately_from_the_win_rate(self) -> None:
        """
        목적: 하락 비율은 **`1 − 승률` 이 아니다.** 보합이 있으면 두 값이 갈라진다.

        보합을 승률의 여집합으로 처리하면 하락 비율이 부풀고, 그 위에서 만드는
        역방향 비율이 조용히 틀린다. 그래서 `< 0` 을 따로 센다.

        Given: 상승 2건·하락 1건·보합 1건
        When: 집계한다
        Then: 승률 0.5, 하락 비율 0.25 이며 `1 − 승률(0.5)` 과 다르다
        """
        # Given
        frame = _cell([0.10, 0.20, -0.30, 0.0])

        # When
        summary = summarize(frame)

        # Then
        assert _only(summary, COL_WIN_RATE) == pytest.approx(0.5, abs=EXACT_TOLERANCE)
        assert _only(summary, COL_LOSS_RATE) == pytest.approx(0.25, abs=EXACT_TOLERANCE)

    def test_win_and_loss_rates_leave_room_for_a_flat_day(self) -> None:
        """
        목적: 승률 + 하락 비율 + 보합 비율 = 1 이 성립한다.

        Given: 상승 1건·하락 1건·보합 2건
        When: 집계한다
        Then: 두 비율의 합이 0.5 이고 나머지 0.5 가 보합이다
        """
        # Given
        frame = _cell([0.10, -0.10, 0.0, 0.0])

        # When
        summary = summarize(frame)

        # Then
        total = _only(summary, COL_WIN_RATE) + _only(summary, COL_LOSS_RATE)
        assert total == pytest.approx(0.5, abs=EXACT_TOLERANCE)

    def test_loss_rate_ignores_excluded_cells(self) -> None:
        """
        목적: 하락 비율도 **유효 표본만** 센다. 제외된 칸이 분모에 들어가면 안 된다.

        Given: 하락 1건과 제외 3건
        When: 집계한다
        Then: 표본 1건 기준이므로 하락 비율이 1.0 이다
        """
        # Given
        frame = _cell([-0.10, None, None, None])

        # When
        summary = summarize(frame)

        # Then
        assert int(_only(summary, COL_SAMPLE_COUNT)) == 1
        assert _only(summary, COL_LOSS_RATE) == pytest.approx(1.0, abs=EXACT_TOLERANCE)

    def test_empty_cell_is_not_computable(self) -> None:
        """
        목적: 표본 0건 칸은 예외가 아니라 "계산 불가"로 나온다.

        Given: 모든 행이 제외된 칸
        When: 집계한다
        Then: 유효 표본 0이고 통계량이 전부 비어 있다
        """
        # Given
        frame = _cell([None, None])

        # When
        summary = summarize(frame)

        # Then
        assert int(_only(summary, COL_SAMPLE_COUNT)) == 0
        assert pd.isna(_only(summary, COL_MEAN))
        assert pd.isna(_only(summary, COL_MEDIAN))
        assert pd.isna(_only(summary, COL_WIN_RATE))

    def test_single_sample_has_no_standard_deviation(self) -> None:
        """
        목적: 표본 1건에서 표준편차는 정의되지 않는다. 0으로 채우면 "변동이 없다"로 읽힌다.

        Given: 값이 하나뿐인 칸
        When: 집계한다
        Then: 평균은 그 값이고 표준편차는 비어 있다
        """
        # Given
        frame = _cell([0.10])

        # When
        summary = summarize(frame)

        # Then
        assert _only(summary, COL_MEAN) == pytest.approx(0.10, abs=EXACT_TOLERANCE)
        assert pd.isna(_only(summary, COL_STD))

    def test_covers_every_cell_in_declared_order(self) -> None:
        """
        목적: 입력에 있는 모든 (기준, 구간) 칸이 선언된 컬럼 순서로 나온다.

        Given: 기준 2종 × 구간 2개
        When: 집계한다
        Then: 칸이 4개이고 컬럼 구성이 선언과 같다
        """
        # Given
        frame = pd.concat(
            [_cell([0.10, 0.20], basis=basis, horizon=horizon) for basis in ReturnBasis for horizon in (1, 5)],
            ignore_index=True,
        )

        # When
        summary = summarize(frame)

        # Then
        assert len(summary) == 4
        assert list(summary.columns) == SUMMARY_COLUMNS

    def test_rejects_frame_without_required_columns(self) -> None:
        """
        목적: 다른 프레임을 넘기면 조용히 빈 집계를 내지 않고 즉시 거부한다.

        Given: 수익률 컬럼이 없는 프레임
        When: 집계한다
        Then: ValueError
        """
        frame = _cell([0.10])

        with pytest.raises(ValueError, match="필수 컬럼"):
            summarize(frame.drop(columns=[COL_FORWARD_RETURN]))


class TestExcess:
    """초과분의 정의를 고정한다."""

    def test_is_a_statistic_wise_difference(self) -> None:
        """
        목적: 초과분은 **통계량끼리 대응해 뺀 값**이다 — 평균은 평균과, 중앙값은 중앙값과.

        Given: 신호 +10%·+20% (평균 15%), 베이스라인 0%·+10% (평균 5%)
        When: 초과분을 낸다
        Then: 평균 초과 +10%p, 중앙값 초과 +10%p, 승률 초과 +50%p
        """
        # Given
        signal = summarize(_cell([0.10, 0.20]))
        baseline = summarize(_cell([0.0, 0.10]))

        # When
        result = excess(signal, baseline)

        # Then
        assert _only(result, COL_MEAN_EXCESS) == pytest.approx(0.10, abs=EXACT_TOLERANCE)
        assert _only(result, COL_MEDIAN_EXCESS) == pytest.approx(0.10, abs=EXACT_TOLERANCE)
        assert _only(result, COL_WIN_RATE_EXCESS) == pytest.approx(0.50, abs=EXACT_TOLERANCE)

    def test_keeps_both_sample_counts(self) -> None:
        """
        목적: 표본 수는 절대 생략하지 않는다. 양쪽 표본 수가 크게 다른 것 자체가 해석의 일부다.

        Given: 신호 2건, 베이스라인 4건
        When: 초과분을 낸다
        Then: 두 표본 수가 모두 컬럼으로 남는다
        """
        # Given
        signal = summarize(_cell([0.10, 0.20]))
        baseline = summarize(_cell([0.0, 0.10, 0.05, 0.02]))

        # When
        result = excess(signal, baseline)

        # Then
        assert list(result.columns) == EXCESS_COLUMNS
        assert int(_only(result, COL_SIGNAL_SAMPLE_COUNT)) == 2
        assert int(_only(result, COL_BASELINE_SAMPLE_COUNT)) == 4

    def test_loss_rate_is_also_a_statistic_wise_difference(self) -> None:
        """
        목적: 하락 비율도 **대응해 뺀다** — 신호군 하락 비율 − 베이스라인 하락 비율.

        역방향 비율의 초과분이 여기서 나온다. "평소보다 더 자주 반대로 갔는가"가
        이 검증이 답하려는 질문이므로 승률 초과와 같은 자리에 둔다.

        Given: 신호군 하락 비율 0.5, 베이스라인 하락 비율 0.25
        When: 초과분을 낸다
        Then: 하락 비율 초과가 +0.25 다
        """
        # Given
        signal = summarize(_cell([0.10, -0.20]))
        baseline = summarize(_cell([0.10, 0.20, 0.30, -0.40]))

        # When
        result = excess(signal, baseline)

        # Then
        assert _only(result, COL_LOSS_RATE_EXCESS) == pytest.approx(0.25, abs=EXACT_TOLERANCE)

    def test_rejects_mismatched_cells(self) -> None:
        """
        목적: 칸 구성이 다르면 조용히 일부만 비교하지 않고 즉시 거부한다.

        Given: 구간이 서로 다른 두 집계
        When: 초과분을 낸다
        Then: ValueError
        """
        signal = summarize(_cell([0.10], horizon=1))
        baseline = summarize(_cell([0.10], horizon=5))

        with pytest.raises(ValueError, match="칸"):
            excess(signal, baseline)


class TestPermutationTest:
    """유의성 판정의 계약을 고정한다."""

    def test_same_seed_is_reproducible(self) -> None:
        """
        목적: 같은 시드로 두 번 돌린 결과가 완전히 같다 — 재현되지 않는 측정은 근거가 되지 못한다.

        Given: 같은 신호군과 모집단
        When: 같은 시드로 두 번 검정한다
        Then: 두 결과가 완전히 같다
        """
        # Given
        signal = _cell([0.05] * 12)
        population = _cell(list(np.linspace(-0.10, 0.10, 200)))

        # When
        first = permutation_test(signal, population, repeats=100, seed=7)
        second = permutation_test(signal, population, repeats=100, seed=7)

        # Then
        pd.testing.assert_frame_equal(first, second)

    def test_extreme_signal_ranks_at_the_top(self) -> None:
        """
        목적: 모집단 어디에서 뽑아도 나오기 어려운 값이면 백분위가 최상단이다.

        Given: 평균 0 근처인 모집단과, 그 위쪽 끝에 몰린 신호 12건
        When: 검정한다
        Then: 백분위가 99 이상이고 p 값이 유의 수준 아래다
        """
        # Given
        signal = _cell([0.095] * 12)
        population = _cell(list(np.linspace(-0.10, 0.10, 500)))

        # When
        result = permutation_test(signal, population, repeats=200, seed=0)

        # Then
        assert _only(result, COL_MEAN_PERCENTILE) >= 0.99
        assert _only(result, COL_MEAN_P_VALUE) < 0.05
        assert result[COL_TEST_NOTE].iloc[0] == NOTE_NONE

    def test_p_value_is_never_zero(self) -> None:
        """
        목적: p 값은 0이 되지 않는다. 0은 "절대 우연이 아니다"로 읽히지만
              실제로는 반복 수의 한계일 뿐이다.

        Given: 모집단 밖에 있는 극단적인 신호
        When: 200회 반복으로 검정한다
        Then: p 값이 1/(반복 수 + 1) 이상이다
        """
        # Given
        signal = _cell([5.0] * 12)
        population = _cell(list(np.linspace(-0.10, 0.10, 500)))

        # When
        result = permutation_test(signal, population, repeats=200, seed=0)

        # Then
        assert _only(result, COL_MEAN_P_VALUE) == pytest.approx(1 / 201, abs=1e-9)

    def test_small_sample_is_not_tested(self) -> None:
        """
        목적: **유효 표본이 한 자릿수면 검정하지 않는다** (스펙 §6).

        Given: 신호 9건
        When: 검정한다
        Then: 사유가 남고 백분위·p 값이 비어 있다. 관측 평균은 그대로 남는다
        """
        # Given
        signal = _cell([0.095] * 9)
        population = _cell(list(np.linspace(-0.10, 0.10, 500)))

        # When
        result = permutation_test(signal, population, repeats=200, seed=0)

        # Then
        assert result[COL_TEST_NOTE].iloc[0] == NOTE_TOO_FEW_SAMPLES
        assert pd.isna(_only(result, COL_MEAN_PERCENTILE))
        assert pd.isna(_only(result, COL_MEAN_P_VALUE))
        assert pd.isna(_only(result, COL_MEDIAN_P_VALUE))
        assert _only(result, COL_OBSERVED_MEAN) == pytest.approx(0.095, abs=EXACT_TOLERANCE)

    def test_threshold_is_one_digit_samples(self) -> None:
        """
        목적: 판정선이 "한 자릿수"임을 고정한다 — 10건이면 검정한다.

        Given: 판정선 상수와 신호 10건
        When: 검정한다
        Then: 판정선이 10이고, 10건은 검정된다
        """
        # Given
        signal = _cell([0.05] * 10)
        population = _cell(list(np.linspace(-0.10, 0.10, 500)))

        # When
        result = permutation_test(signal, population, repeats=100, seed=0)

        # Then
        assert MIN_SAMPLE_PER_CELL == 10
        assert result[COL_TEST_NOTE].iloc[0] == NOTE_NONE

    def test_population_smaller_than_sample_is_not_tested(self) -> None:
        """
        목적: 모집단이 표본보다 작으면 비복원 추출이 성립하지 않는다.

        Given: 모집단 5건, 신호 12건
        When: 검정한다
        Then: 사유가 남고 검정 결과가 비어 있다
        """
        # Given
        signal = _cell([0.05] * 12)
        population = _cell([0.01, 0.02, 0.03, 0.04, 0.05])

        # When
        result = permutation_test(signal, population, repeats=100, seed=0)

        # Then
        assert result[COL_TEST_NOTE].iloc[0] == NOTE_POPULATION_NOT_LARGER
        assert pd.isna(_only(result, COL_MEAN_P_VALUE))

    def test_columns_are_declared_in_order(self) -> None:
        """
        목적: 결과 컬럼 구성과 순서를 고정한다.

        Given: 정상 입력
        When: 검정한다
        Then: 선언된 컬럼이 선언된 순서로 나온다
        """
        # Given
        signal = _cell([0.05] * 12)
        population = _cell(list(np.linspace(-0.10, 0.10, 200)))

        # When
        result = permutation_test(signal, population, repeats=50, seed=0)

        # Then
        assert list(result.columns) == TEST_COLUMNS

    def test_rejects_non_positive_repeats(self) -> None:
        """
        목적: 반복 수가 0 이하면 귀무분포가 만들어지지 않는다.

        Given: 반복 수 0
        When: 검정한다
        Then: ValueError
        """
        signal = _cell([0.05] * 12)
        population = _cell(list(np.linspace(-0.10, 0.10, 200)))

        with pytest.raises(ValueError, match="반복"):
            permutation_test(signal, population, repeats=0, seed=0)


class TestDirectionRateTest:
    """방향 비율 검정의 계약을 고정한다.

    **오른 비율이 기준선보다 낮은 것은 탈락 사유가 아니라 아래로 거는 신호다**
    (루트 `CLAUDE.md` 측정의 원칙 11). 그래서 판정은 언제나 양측이고,
    평균이 놓치는 칸을 비율이 잡아내는지가 이 클래스의 핵심 계약이다.
    """

    def test_observed_rates_match_hand_count(self) -> None:
        """
        목적: 관측 비율이 손으로 센 값과 정확히 같다 — 산식이 곧 결론을 만든다.

        Given: 오른 4건 · 내린 10건 · 보합 1건인 신호 15건
        When: 검정한다
        Then: 오른 비율 4/15, 내린 비율 10/15 가 그대로 나온다
        """
        # Given
        signal = _cell([0.01] * 4 + [-0.02] * 10 + [0.0])
        population = _cell(list(np.linspace(-0.05, 0.06, 300)))

        # When
        result = permutation_test(signal, population, repeats=200, seed=0)

        # Then
        assert _only(result, COL_OBSERVED_UP_RATE) == pytest.approx(4 / 15, abs=EXACT_TOLERANCE)
        assert _only(result, COL_OBSERVED_DOWN_RATE) == pytest.approx(10 / 15, abs=EXACT_TOLERANCE)

    def test_up_and_down_rates_are_not_complements(self) -> None:
        """
        목적: **오른 비율과 내린 비율은 여집합이 아니다.** 보합이 어느 쪽에도 들어가지 않는다.
              `1 − 오른 비율` 로 내린 비율을 만들면 보합이 하락으로 새어 들어가 값이 부푼다.

        Given: 보합이 3건 섞인 신호 15건
        When: 검정한다
        Then: 두 비율의 합이 1 보다 작고, 모자란 몫이 정확히 보합 비율이다
        """
        # Given
        signal = _cell([0.01] * 6 + [-0.02] * 6 + [0.0] * 3)
        population = _cell(list(np.linspace(-0.05, 0.06, 300)))

        # When
        result = permutation_test(signal, population, repeats=200, seed=0)

        # Then
        up_rate = _only(result, COL_OBSERVED_UP_RATE)
        down_rate = _only(result, COL_OBSERVED_DOWN_RATE)
        assert up_rate + down_rate == pytest.approx(1 - 3 / 15, abs=EXACT_TOLERANCE)

    def test_downward_signal_is_significant_in_two_sided_test(self) -> None:
        """
        목적: **오른 비율이 기준선보다 낮아도 유의하게 잡힌다.** 단측이면 이 칸을 놓친다.

        Given: 모집단 오른 비율이 절반 근처인데, 신호 20건 중 16건이 내렸다
        When: 검정한다
        Then: 오른 비율 백분위가 하단이고 양쪽 비율의 p 값이 유의 수준 아래다
        """
        # Given
        signal = _cell([-0.02] * 16 + [0.01] * 4)
        population = _cell(list(np.linspace(-0.05, 0.06, 400)))

        # When
        result = permutation_test(signal, population, repeats=500, seed=0)

        # Then
        assert _only(result, COL_UP_RATE_PERCENTILE) <= 0.05
        assert _only(result, COL_UP_RATE_P_VALUE) < 0.05
        assert _only(result, COL_DOWN_RATE_P_VALUE) < 0.05

    def test_rate_axis_catches_what_mean_misses(self) -> None:
        """
        목적: **평균이 양수인데 절반 넘게 내린 칸을 비율 축이 잡는다** (측정의 원칙 13).
              소수의 큰 상승이 평균을 끌어올려도 방향 비율은 아래를 가리킨다.

        Given: 크게 오른 2건이 평균을 양수로 만들지만 12건 중 10건은 내린 신호
        When: 검정한다
        Then: 관측 평균은 양수인데 내린 비율이 과반이다
        """
        # Given
        signal = _cell([0.50, 0.45] + [-0.02] * 10)
        population = _cell(list(np.linspace(-0.05, 0.06, 300)))

        # When
        result = permutation_test(signal, population, repeats=200, seed=0)

        # Then
        assert _only(result, COL_OBSERVED_MEAN) > 0
        assert _only(result, COL_OBSERVED_DOWN_RATE) > 0.5

    def test_same_seed_is_reproducible(self) -> None:
        """
        목적: 비율 축도 같은 시드에서 완전히 재현된다.

        Given: 같은 신호군과 모집단
        When: 같은 시드로 두 번 검정한다
        Then: 두 결과가 완전히 같다
        """
        # Given
        signal = _cell([0.01] * 5 + [-0.02] * 9)
        population = _cell(list(np.linspace(-0.05, 0.06, 300)))

        # When
        first = permutation_test(signal, population, repeats=100, seed=3)
        second = permutation_test(signal, population, repeats=100, seed=3)

        # Then
        pd.testing.assert_frame_equal(first, second)

    def test_small_sample_leaves_rates_but_no_test(self) -> None:
        """
        목적: 유효 표본이 한 자릿수면 **비율도 검정하지 않는다.** 관측값은 남긴다 —
              평균·중앙값과 같은 규칙이라 축마다 기준이 갈리지 않는다.

        Given: 신호 9건
        When: 검정한다
        Then: 사유가 남고 비율의 백분위·p 값이 비어 있다. 관측 비율은 그대로 남는다
        """
        # Given
        signal = _cell([-0.02] * 9)
        population = _cell(list(np.linspace(-0.05, 0.06, 300)))

        # When
        result = permutation_test(signal, population, repeats=200, seed=0)

        # Then
        assert result[COL_TEST_NOTE].iloc[0] == NOTE_TOO_FEW_SAMPLES
        assert pd.isna(_only(result, COL_UP_RATE_PERCENTILE))
        assert pd.isna(_only(result, COL_UP_RATE_P_VALUE))
        assert pd.isna(_only(result, COL_DOWN_RATE_P_VALUE))
        assert _only(result, COL_OBSERVED_DOWN_RATE) == pytest.approx(1.0, abs=EXACT_TOLERANCE)

    def test_population_smaller_than_sample_is_not_tested(self) -> None:
        """
        목적: 모집단이 표본보다 작으면 비율도 검정하지 않는다.

        Given: 신호 12건, 모집단 10건
        When: 검정한다
        Then: 사유가 남고 비율의 p 값이 비어 있다
        """
        # Given
        signal = _cell([-0.02] * 12)
        population = _cell([0.01] * 10)

        # When
        result = permutation_test(signal, population, repeats=100, seed=0)

        # Then
        assert result[COL_TEST_NOTE].iloc[0] == NOTE_POPULATION_NOT_LARGER
        assert pd.isna(_only(result, COL_UP_RATE_P_VALUE))
        assert pd.isna(_only(result, COL_DOWN_RATE_P_VALUE))

    def test_rate_columns_are_in_the_contract(self) -> None:
        """
        목적: 방향 비율 컬럼이 검정표 스키마에 들어 있다 — 계층 간 계약이다.

        Given: 정상적인 신호군과 모집단
        When: 검정한다
        Then: 결과 컬럼이 `TEST_COLUMNS` 와 정확히 같고 방향 비율 6개가 그 안에 있다
        """
        # Given
        signal = _cell([0.01] * 12)
        population = _cell(list(np.linspace(-0.05, 0.06, 300)))

        # When
        result = permutation_test(signal, population, repeats=50, seed=0)

        # Then
        assert list(result.columns) == TEST_COLUMNS
        for column in (
            COL_OBSERVED_UP_RATE,
            COL_UP_RATE_PERCENTILE,
            COL_UP_RATE_P_VALUE,
            COL_OBSERVED_DOWN_RATE,
            COL_DOWN_RATE_PERCENTILE,
            COL_DOWN_RATE_P_VALUE,
        ):
            assert column in TEST_COLUMNS


class TestPermutationTestRegression:
    """비율 축을 더해도 **평균·중앙값 결과가 바뀌지 않는다**를 고정한다.

    공통 계층이라 검증 두 개가 이 값에 걸려 있다. 값이 흔들리면 이미 낸 결과 문서가
    재현되지 않으므로, 확인한 값을 그대로 박아 둔다.
    """

    def test_mean_and_median_results_are_unchanged(self) -> None:
        """
        목적: 같은 입력·같은 시드에서 평균·중앙값의 관측값과 판정이 그대로다.

        Given: 신호 0.05 12건, 모집단 -0.10~0.10 200건, 반복 100회, 시드 7
        When: 검정한다
        Then: 관측 평균·중앙값과 백분위·p 값이 고정값과 일치한다
        """
        # Given
        signal = _cell([0.05] * 12)
        population = _cell(list(np.linspace(-0.10, 0.10, 200)))

        # When
        result = permutation_test(signal, population, repeats=100, seed=7)

        # Then
        assert _only(result, COL_OBSERVED_MEAN) == pytest.approx(0.05, abs=EXACT_TOLERANCE)
        assert _only(result, COL_MEAN_PERCENTILE) == pytest.approx(1.0, abs=EXACT_TOLERANCE)
        assert _only(result, COL_MEAN_P_VALUE) == pytest.approx(1 / 101, abs=EXACT_TOLERANCE)
        assert _only(result, COL_MEDIAN_PERCENTILE) == pytest.approx(0.99, abs=EXACT_TOLERANCE)
        assert _only(result, COL_MEDIAN_P_VALUE) == pytest.approx(7 / 101, abs=EXACT_TOLERANCE)


class TestMaxNonOverlapping:
    """비중첩 표본 수 — **두 검증이 같은 정의를 쓴다**를 여기서 고정한다.

    롤링 전수는 이웃끼리 심하게 겹쳐, 표본 수만 적으면 실제보다 단단해 보인다.
    이 값이 검증마다 다른 규칙으로 계산되면 두 결과 문서의 같은 이름 컬럼을
    나란히 놓고 비교할 수 없다.

    **끝점을 공유하는 두 구간은 「겹치지 않음」이다.** 구간 `[p, p+h]` 와 `[p+h, p+2h]` 는
    관측일 하나를 공유하지만 **수익률 구간이 겹치지 않아** 통계적으로 독립이다.
    """

    def test_연속된_시작일에서_구간_길이만큼_건너뛴다(self) -> None:
        """
        목적: 그리디 선택이 정확한 최대값을 내는지 고정한다

        Given: 시작일 0~9 가 전부 있고 구간이 3
        When: 비중첩 개수를 센다
        Then: 0·3·6·9 로 4개다
        """
        # When / Then
        assert max_non_overlapping(list(range(10)), horizon=3) == 4

    def test_띄엄띄엄한_시작일도_정확히_센다(self) -> None:
        """
        목적: 축으로 걸러 시작일이 흩어진 칸에서도 최대값이 맞는지 고정한다

        Given: 시작일 0·1·5·6·10 이고 구간이 4
        When: 비중첩 개수를 센다
        Then: 0·5·10 으로 3개다
        """
        # When / Then
        assert max_non_overlapping([0, 1, 5, 6, 10], horizon=4) == 3

    def test_끝점을_공유하는_구간은_겹치지_않은_것으로_센다(self) -> None:
        """
        목적: **정의의 핵심**을 고정한다 — 이 한 칸이 두 검증을 갈라놓았다

        Given: 시작일 0 과 3 이고 구간이 3 (구간은 [0,3] 과 [3,6])
        When: 비중첩 개수를 센다
        Then: 2개다. 관측일 3 을 공유하지만 수익률 구간은 겹치지 않는다
        """
        # When / Then
        assert max_non_overlapping([0, 3], horizon=3) == 2

    def test_구간이_1이면_시작일_수와_같다(self) -> None:
        """
        목적: 경계값을 고정한다

        Given: 시작일 5개
        When: 구간 1 로 센다
        Then: 5개 전부가 비중첩이다
        """
        # When / Then
        assert max_non_overlapping([0, 1, 2, 3, 4], horizon=1) == 5

    def test_시작일이_없으면_0이다(self) -> None:
        """
        목적: 빈 칸에서 예외가 아니라 0 을 내는지 고정한다

        Given: 빈 시작일 목록
        When: 비중첩 개수를 센다
        Then: 0 이다
        """
        # When / Then
        assert max_non_overlapping([], horizon=5) == 0

    def test_정렬되지_않은_시작일도_같은_값을_낸다(self) -> None:
        """
        목적: 입력 순서에 결과가 흔들리지 않음을 고정한다

        Given: 같은 시작일 집합을 뒤섞은 것
        When: 비중첩 개수를 센다
        Then: 정렬된 입력과 같다
        """
        # When / Then
        assert max_non_overlapping([10, 1, 6, 0, 5], horizon=4) == max_non_overlapping([0, 1, 5, 6, 10], horizon=4)

    def test_보유_기간이_1_미만이면_거부한다(self) -> None:
        """
        목적: 입력 파라미터 검증을 고정한다

        Given: 보유 기간 0
        When: 비중첩 개수를 센다
        Then: ValueError 가 난다
        """
        # When / Then
        with pytest.raises(ValueError, match="보유 기간"):
            max_non_overlapping([0, 1, 2], horizon=0)


class TestPercentileUnitContract:
    """백분위는 계층 간 계약대로 **비율(0~1)** 로 나온다"""

    def test_백분위가_비율_범위다(self) -> None:
        """
        목적: `measure` 가 백분율로 내던 것을 막는다.

        계층 간 계약이 "`measure` 는 비율(0~1) 그대로, 저장 직전 백분율 2자리"로 정했고
        `.claude/rules/python.md` 도 "모든 비율 값은 0~1 사이 소수"를 요구한다.
        **이 값만 계약 밖으로 나가 있어서** 두 출력 경로가 서로 다르게 취급했다 —
        한쪽은 백분율(2자리), 다른 쪽은 확률(4자리)로 읽었다.

        Given: 검정이 붙을 만큼의 표본과 모집단
        When: 순열 검정을 돌린다
        Then: 백분위 네 축이 전부 0~1 범위다
        """
        # Given
        signal = _cell([0.03] * 15)
        population = _cell(list(np.linspace(-0.10, 0.10, 400)))

        # When
        result = permutation_test(signal, population, repeats=100, seed=0)

        # Then
        for column in (COL_MEAN_PERCENTILE, COL_MEDIAN_PERCENTILE, COL_UP_RATE_PERCENTILE, COL_DOWN_RATE_PERCENTILE):
            value = _only(result, column)
            assert 0.0 <= value <= 1.0, f"{column} 이 비율 범위를 벗어났습니다: {value}"


class TestPopulationSameSizeAsSample:
    """모집단이 표본과 같으면 검정이 성립하지 않는다"""

    def test_모집단이_표본과_같으면_사유를_남긴다(self) -> None:
        """
        목적: 뜻이 없는 p 값이 「검정했더니 유의하지 않다」로 읽히는 것을 막는다.

        비복원 추출로 모집단 전체를 뽑으면 **반복마다 같은 표본**이 나와 귀무분포가 상수가 된다.
        그러면 p 값이 언제나 1.0 인데, 사유가 없으면 「검정은 됐고 결과가 유의하지 않다」로 읽힌다.
        모집단이 **작을 때**는 이미 사유를 남기므로 경계 하나 차이다.

        Given: 모집단과 신호군의 유효 표본 수가 같은 칸
        When: 순열 검정을 돌린다
        Then: 검정하지 않고 사유가 남는다
        """
        # Given
        values = [0.01, -0.02, 0.03, -0.01, 0.02, 0.04, -0.03, 0.01, 0.02, -0.01, 0.05, 0.01]
        signal = _cell(values)
        population = _cell(values)

        # When
        result = permutation_test(signal, population, repeats=100, seed=0)

        # Then
        assert result[COL_TEST_NOTE].iloc[0] != NOTE_NONE
        assert pd.isna(_only(result, COL_MEAN_P_VALUE))
