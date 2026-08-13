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
    REASON_NONE,
    REASON_OUT_OF_RANGE,
)
from verify_lab.measure.forward_return import ReturnBasis
from verify_lab.measure.statistics import (
    COL_BASELINE_SAMPLE_COUNT,
    COL_MAX,
    COL_MEAN,
    COL_MEAN_EXCESS,
    COL_MEAN_P_VALUE,
    COL_MEAN_PERCENTILE,
    COL_MEDIAN,
    COL_MEDIAN_EXCESS,
    COL_MEDIAN_P_VALUE,
    COL_MIN,
    COL_OBSERVED_MEAN,
    COL_SAMPLE_COUNT,
    COL_SIGNAL_SAMPLE_COUNT,
    COL_STD,
    COL_TEST_NOTE,
    COL_WIN_RATE,
    COL_WIN_RATE_EXCESS,
    EXCESS_COLUMNS,
    MIN_SAMPLE_FOR_TEST,
    NOTE_NONE,
    NOTE_POPULATION_TOO_SMALL,
    NOTE_TOO_FEW_SAMPLES,
    SUMMARY_COLUMNS,
    TEST_COLUMNS,
    excess,
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
        assert _only(result, COL_MEAN_PERCENTILE) >= 99.0
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
        assert MIN_SAMPLE_FOR_TEST == 10
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
        assert result[COL_TEST_NOTE].iloc[0] == NOTE_POPULATION_TOO_SMALL
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
