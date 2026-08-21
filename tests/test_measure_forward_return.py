"""forward return 산식과 표본 보존 계약을 고정한다.

이 계층은 **정의가 곧 결론을 만든다.** 기준점을 하나만 두거나 두 기준의 출구를 다르게 잡으면
"두 값의 차이가 갭으로 새는 몫"이라는 해석 자체가 성립하지 않으므로, 산식을 손계산 값으로 박는다.

핵심 계약은 네 가지다.
- 종가 기준은 `D+h 종가 ÷ 신호일 종가 − 1`, 익일 시가 기준은 `D+h 종가 ÷ D+1 시가 − 1` —
  **출구가 같고 입구만 다르다**
- 측정 구간 끝이 데이터를 넘어가면 제외하되, 표본은 사라지지 않는다
  (모든 칸에서 `신호 수 = 유효 + 제외`)
- 뒤를 잘라낸 입력과 전체 입력의 값이 겹치는 범위에서 같다 (look-ahead 감시)
- 행 순서는 신호일 → 기준 → 구간 오름차순으로 고정된다

실제 시세 파일에 의존하면 데이터를 갱신할 때마다 테스트가 깨지므로 합성 데이터만 쓴다.
"""

from collections.abc import Callable, Sequence

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
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
from verify_lab.measure.forward_return import (
    DEFAULT_HORIZONS,
    NEXT_OPEN_HORIZONS,
    RESULT_COLUMNS,
    ReturnBasis,
    compute_forward_returns,
    count_excluded,
)

# 수익률은 나눗셈 한 번이라 수학적으로 정확해야 한다 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12


def _market(closes: Sequence[float], opens: Sequence[float] | None = None) -> pd.DataFrame:
    """합성 시세를 만든다. 시가를 생략하면 종가와 같다."""
    open_prices = list(closes if opens is None else opens)
    close_prices = list(closes)

    return pd.DataFrame(
        {
            COL_DATE: pd.bdate_range("2026-01-05", periods=len(close_prices)),
            COL_OPEN: open_prices,
            COL_HIGH: [max(pair) for pair in zip(open_prices, close_prices, strict=True)],
            COL_LOW: [min(pair) for pair in zip(open_prices, close_prices, strict=True)],
            COL_CLOSE: close_prices,
            COL_VOLUME: [1_000] * len(close_prices),
        }
    )


def _signals(df: pd.DataFrame, positions: Sequence[int]) -> pd.Series:
    """지정한 위치만 True 인 신호 Series 를 만든다."""
    marked = set(positions)

    return pd.Series([index in marked for index in range(len(df))], index=df.index)


def _value(df: pd.DataFrame, frame: pd.DataFrame, position: int, basis: ReturnBasis, horizon: int) -> float:
    """신호일 위치와 (기준, 구간)으로 수익률 한 칸을 꺼낸다."""
    row = frame[
        (frame[COL_DATE] == df[COL_DATE].iloc[position])
        & (frame[COL_BASIS] == basis.value)
        & (frame[COL_HORIZON] == horizon)
    ]

    return float(row[COL_FORWARD_RETURN].iloc[0])


class TestFormula:
    """산식을 손계산 값으로 고정한다."""

    def test_close_basis_matches_hand_calculation(self) -> None:
        """
        목적: 종가 기준 수익률은 **D+h 종가 ÷ 신호일 종가 − 1** 이다.

        Given: 종가 100 · 110 · 121 인 시세와 첫날 신호
        When: 구간 1·2로 계산한다
        Then: 1일 +10%, 2일 +21%
        """
        # Given
        df = _market([100.0, 110.0, 121.0])

        # When
        frame = compute_forward_returns(df, _signals(df, [0]), horizons=(1, 2))

        # Then
        assert _value(df, frame, 0, ReturnBasis.CLOSE, 1) == pytest.approx(0.10, abs=EXACT_TOLERANCE)
        assert _value(df, frame, 0, ReturnBasis.CLOSE, 2) == pytest.approx(0.21, abs=EXACT_TOLERANCE)

    def test_next_open_basis_starts_from_the_following_open(self) -> None:
        """
        목적: 익일 시가 기준 수익률은 **D+h 종가 ÷ D+1 시가 − 1** 이다 — 실제 집행 가능한 구간이다.

        Given: 신호일 종가 100, 다음 날 시가 105·종가 110
        When: 구간 1로 계산한다
        Then: 110 ÷ 105 − 1
        """
        # Given
        df = _market([100.0, 110.0, 121.0], opens=[100.0, 105.0, 115.0])

        # When
        frame = compute_forward_returns(df, _signals(df, [0]), horizons=(1,))

        # Then
        assert _value(df, frame, 0, ReturnBasis.NEXT_OPEN, 1) == pytest.approx(110 / 105 - 1, abs=EXACT_TOLERANCE)

    def test_both_bases_share_the_same_exit(self) -> None:
        """
        목적: 두 기준은 **출구가 같고 입구만 다르다.** 이것이 성립해야 "차이 = 갭으로 새는 몫"이 된다.

        Given: 신호일 종가 100, 다음 날 시가 105 · 종가 110
        When: 두 기준이 함께 내는 1일 구간으로 계산한다
        Then: 두 기준 모두 출구가 110이고 입구만 100과 105로 갈린다
        """
        # Given
        df = _market([100.0, 110.0], opens=[100.0, 105.0])

        # When
        frame = compute_forward_returns(df, _signals(df, [0]), horizons=(1,))

        # Then
        assert _value(df, frame, 0, ReturnBasis.CLOSE, 1) == pytest.approx(110 / 100 - 1, abs=EXACT_TOLERANCE)
        assert _value(df, frame, 0, ReturnBasis.NEXT_OPEN, 1) == pytest.approx(110 / 105 - 1, abs=EXACT_TOLERANCE)

    def test_gap_up_makes_the_next_open_basis_lower(self) -> None:
        """
        목적: 갭 상승으로 시작한 날은 익일 시가 기준이 종가 기준보다 낮다 — 그 차이가 놓친 몫이다.

        Given: 신호일 종가 100, 다음 날 시가 118로 갭 상승 후 종가 120
        When: 구간 1로 계산한다
        Then: 익일 시가 기준 < 종가 기준
        """
        # Given
        df = _market([100.0, 120.0], opens=[100.0, 118.0])

        # When
        frame = compute_forward_returns(df, _signals(df, [0]), horizons=(1,))

        # Then
        assert _value(df, frame, 0, ReturnBasis.NEXT_OPEN, 1) < _value(df, frame, 0, ReturnBasis.CLOSE, 1)

    def test_default_horizons_are_the_confirmed_spec_values(self) -> None:
        """
        목적: 측정 구간은 확정 설계값이며 호출자가 고를 수 있는 노브가 아니다.

        Given: 기본 구간 상수
        When: 값을 확인한다
        Then: 1·2·3·5·10·21 거래일이다 (스펙 §7 결정 ㉑ 로 단기화)
        """
        assert DEFAULT_HORIZONS == (1, 2, 3, 5, 10, 21)

    def test_next_open_horizons_are_the_one_day_cell_only(self) -> None:
        """
        목적: 익일 시가 기준으로 내는 구간은 **1일 하나뿐**이다 (스펙 §7 결정 ⑳).

        Given: 익일 시가 기준의 측정 구간 상수
        When: 값을 확인한다
        Then: 1거래일 하나다
        """
        assert NEXT_OPEN_HORIZONS == (1,)


class TestSamplePreservation:
    """표본이 조용히 사라지지 않음을 고정한다 — 생존편향이 들어오는 지점이다."""

    def test_every_cell_keeps_signal_count(self) -> None:
        """
        목적: 모든 (기준, 구간) 칸에서 **입력 신호 수 = 유효 표본 + 제외 표본** 이다.

        Given: 10거래일 시세와 신호 3건
        When: 구간 1·5로 계산한다
        Then: 행 수가 신호 수 × (종가 2칸 + 익일 시가 1칸) 이고, 칸마다 유효와 제외의 합이 신호 수와 같다
        """
        # Given
        df = _market([100.0 + index for index in range(10)])
        signals = _signals(df, [0, 5, 9])

        # When
        frame = compute_forward_returns(df, signals, horizons=(1, 5))

        # Then
        assert len(frame) == 3 * 3
        for (_, _), group in frame.groupby([COL_BASIS, COL_HORIZON]):
            usable = int(group[COL_FORWARD_RETURN].notna().sum())
            excluded = int((group[COL_EXCLUDED_REASON] != REASON_NONE).sum())
            assert usable + excluded == 3

    def test_excluded_cell_has_reason_and_no_value(self) -> None:
        """
        목적: 제외된 칸은 사유를 달고 남는다. 값과 사유가 함께 있으면 안 된다.

        Given: 마지막 거래일에 발생한 신호
        When: 계산한다
        Then: 모든 칸이 값 없음 + "구간 끝이 데이터 범위를 넘음" 사유다
        """
        # Given
        df = _market([100.0, 101.0, 102.0])

        # When
        frame = compute_forward_returns(df, _signals(df, [2]), horizons=(1, 2))

        # Then
        assert frame[COL_FORWARD_RETURN].isna().all()
        assert (frame[COL_EXCLUDED_REASON] == REASON_OUT_OF_RANGE).all()

    def test_usable_cell_carries_no_reason(self) -> None:
        """
        목적: 유효한 칸에는 제외 사유가 붙지 않는다.

        Given: 뒤에 데이터가 충분한 신호
        When: 계산한다
        Then: 사유 컬럼이 비어 있다
        """
        # Given
        df = _market([100.0, 110.0, 121.0])

        # When
        frame = compute_forward_returns(df, _signals(df, [0]), horizons=(1,))

        # Then
        assert (frame[COL_EXCLUDED_REASON] == REASON_NONE).all()

    def test_horizon_ending_exactly_on_the_last_row_is_kept(self) -> None:
        """
        목적: 구간 끝이 마지막 행과 **정확히 일치**하면 제외가 아니다 (경계 off-by-one 방지).

        Given: 5거래일 시세와 위치 2의 신호
        When: 구간 2로 계산한다 — 출구가 마지막 행이다
        Then: 값이 존재하고 제외되지 않는다
        """
        # Given
        df = _market([100.0, 101.0, 102.0, 103.0, 104.0])

        # When
        frame = compute_forward_returns(df, _signals(df, [2]), horizons=(2,))

        # Then
        assert _value(df, frame, 2, ReturnBasis.CLOSE, 2) == pytest.approx(104 / 102 - 1, abs=EXACT_TOLERANCE)
        assert (frame[COL_EXCLUDED_REASON] == REASON_NONE).all()

    def test_both_bases_are_excluded_together(self) -> None:
        """
        목적: 두 기준의 제외 조건은 같다. 구간이 1 이상이라 출구가 있으면 익일 시가도 반드시 있다.

        Given: 구간 끝이 데이터를 넘는 신호와 넘지 않는 신호가 섞인 입력
        When: 계산한다
        Then: 두 기준이 함께 내는 1일 칸에서 제외 여부가 신호일마다 일치한다
        """
        # Given
        df = _market([100.0 + index for index in range(6)])
        signals = _signals(df, [0, 4, 5])

        # When
        frame = compute_forward_returns(df, signals, horizons=(1, 3))

        # Then
        shared = frame[frame[COL_HORIZON].isin(NEXT_OPEN_HORIZONS)]
        pivoted = shared.pivot(index=[COL_DATE, COL_HORIZON], columns=COL_BASIS, values=COL_FORWARD_RETURN)
        assert (pivoted[ReturnBasis.CLOSE.value].isna() == pivoted[ReturnBasis.NEXT_OPEN.value].isna()).all()


class TestLookAhead:
    """미래 참조 감시 계약을 고정한다."""

    def test_truncated_input_gives_the_same_values(self, assert_stable_under_truncation: Callable[..., None]) -> None:
        """
        목적: **look-ahead 감시** — 뒤에 데이터가 더 붙어도 이미 확정된 칸의 값이 달라지면 안 된다.

        Given: 12거래일 시세와 신호 3건
        When: 앞 8일만 준 결과와 전체를 준 결과를 비교한다
        Then: 짧은 입력에서 값이 있던 칸이 전체 입력에서도 같은 값이다
        """
        # Given
        df = _market([100.0 * (1.01**index) for index in range(12)])
        signals = _signals(df, [0, 2, 5])

        # When / Then
        assert_stable_under_truncation(
            lambda frame: compute_forward_returns(df=frame, signals=signals.iloc[: len(frame)], horizons=(1, 3)),
            df,
            8,
            key_columns=[COL_DATE, COL_BASIS, COL_HORIZON],
            value_column=COL_FORWARD_RETURN,
        )


class TestReturnContract:
    """반환 형태·정렬·불변성을 고정한다."""

    def test_next_open_basis_covers_the_one_day_horizon_only(self) -> None:
        """
        목적: 익일 시가 기준 칸은 **1일 구간에만** 생긴다 — 장기 구간은 종가 기준 값의 중복이다.

        Given: 구간 1·5·21 을 넘긴 신호 1건
        When: 계산한다
        Then: 종가 기준은 세 구간 전부, 익일 시가 기준은 1일 하나뿐이다
        """
        # Given
        df = _market([100.0 + index for index in range(30)])

        # When
        frame = compute_forward_returns(df, _signals(df, [0]), horizons=(1, 5, 21))

        # Then
        assert sorted(frame.loc[frame[COL_BASIS] == ReturnBasis.CLOSE.value, COL_HORIZON]) == [1, 5, 21]
        assert sorted(frame.loc[frame[COL_BASIS] == ReturnBasis.NEXT_OPEN.value, COL_HORIZON]) == [1]

    def test_row_count_is_signal_count_times_the_cells_of_every_basis(self) -> None:
        """
        목적: 행 수 계약을 고정한다 — 기준마다 구간 수가 다르므로 곱셈이 아니라 **기준별 합**이다.

        Given: 신호 2건과 구간 1·5 (종가 2칸 + 익일 시가 1칸)
        When: 계산한다
        Then: 2 × 3 = 6행이다
        """
        # Given
        df = _market([100.0 + index for index in range(10)])
        horizons = (1, 5)

        # When
        frame = compute_forward_returns(df, _signals(df, [0, 1]), horizons=horizons)

        # Then
        assert len(frame) == 2 * (len(horizons) + len(NEXT_OPEN_HORIZONS))

    def test_columns_are_declared_in_order(self) -> None:
        """
        목적: 컬럼 구성과 순서를 고정한다 — 아래 계층이 위치로 읽는 것을 막는다.

        Given: 정상 입력
        When: 계산한다
        Then: 선언된 컬럼이 선언된 순서로 나온다
        """
        # Given
        df = _market([100.0, 110.0, 121.0])

        # When
        frame = compute_forward_returns(df, _signals(df, [0]), horizons=(1,))

        # Then
        assert list(frame.columns) == RESULT_COLUMNS

    def test_rows_are_sorted_by_signal_date_then_basis_then_horizon(self) -> None:
        """
        목적: 행 순서를 고정한다. 같은 입력이 항상 같은 순서를 내야 재현성이 성립한다.

        Given: 신호 2건과 뒤섞어 넘긴 구간 (2, 1)
        When: 계산한다
        Then: 신호일 → 기준 → 구간 오름차순이다
        """
        # Given
        df = _market([100.0 + index for index in range(6)])

        # When
        frame = compute_forward_returns(df, _signals(df, [0, 3]), horizons=(2, 1))

        # Then
        expected = [
            (df[COL_DATE].iloc[position], basis, horizon)
            for position in (0, 3)
            for basis, horizons in ((ReturnBasis.CLOSE.value, (1, 2)), (ReturnBasis.NEXT_OPEN.value, (1,)))
            for horizon in horizons
        ]
        assert list(frame[[COL_DATE, COL_BASIS, COL_HORIZON]].itertuples(index=False, name=None)) == expected

    def test_no_signal_returns_empty_frame_with_columns(self) -> None:
        """
        목적: 신호가 0건인 것은 오류가 아니라 정상적인 측정 결과다 — 컬럼은 유지된다.

        Given: 신호가 하나도 없는 입력
        When: 계산한다
        Then: 행이 0개이고 컬럼 구성과 구간 dtype 이 그대로다
        """
        # Given
        df = _market([100.0, 110.0, 121.0])

        # When
        frame = compute_forward_returns(df, _signals(df, []), horizons=(1,))

        # Then
        assert frame.empty
        assert list(frame.columns) == RESULT_COLUMNS
        assert pd.api.types.is_integer_dtype(frame[COL_HORIZON])

    def test_horizon_column_is_integer(self) -> None:
        """
        목적: 구간은 거래일 수이므로 정수다. 실수로 새면 집계 키가 갈라진다.

        Given: 정상 입력
        When: 계산한다
        Then: 구간 컬럼이 정수 dtype 이다
        """
        # Given
        df = _market([100.0, 110.0, 121.0])

        # When
        frame = compute_forward_returns(df, _signals(df, [0]), horizons=(1,))

        # Then
        assert pd.api.types.is_integer_dtype(frame[COL_HORIZON])

    def test_inputs_are_not_modified(self) -> None:
        """
        목적: 원본 데이터 불변성을 고정한다.

        Given: 시세와 신호
        When: 계산한다
        Then: 두 입력이 그대로다
        """
        # Given
        df = _market([100.0, 110.0, 121.0])
        signals = _signals(df, [0])
        market_before = df.copy()
        signals_before = signals.copy()

        # When
        compute_forward_returns(df, signals, horizons=(1,))

        # Then
        pd.testing.assert_frame_equal(df, market_before)
        pd.testing.assert_series_equal(signals, signals_before)


class TestInputValidation:
    """잘못된 입력을 조용히 넘기지 않음을 고정한다."""

    def test_rejects_empty_market(self) -> None:
        """
        목적: 빈 시세로는 측정이 성립하지 않는다.

        Given: 빈 시세
        When: 계산한다
        Then: ValueError
        """
        df = _market([])

        with pytest.raises(ValueError, match="비어"):
            compute_forward_returns(df, _signals(df, []), horizons=(1,))

    def test_rejects_missing_price_column(self) -> None:
        """
        목적: 필요한 가격 컬럼이 없으면 즉시 막는다.

        Given: 종가 컬럼이 없는 시세
        When: 계산한다
        Then: ValueError
        """
        df = _market([100.0, 110.0])
        signals = _signals(df, [0])

        with pytest.raises(ValueError, match="필수 컬럼"):
            compute_forward_returns(df.drop(columns=[COL_CLOSE]), signals, horizons=(1,))

    def test_rejects_unsorted_dates(self) -> None:
        """
        목적: 날짜가 오름차순이 아니면 위치 기반 계산이 조용히 어긋난다.

        Given: 날짜를 내림차순으로 뒤집은 시세
        When: 계산한다
        Then: ValueError
        """
        df = _market([100.0, 110.0, 121.0])
        reversed_dates = df.assign(**{COL_DATE: df[COL_DATE].to_numpy()[::-1]})

        with pytest.raises(ValueError, match="오름차순"):
            compute_forward_returns(reversed_dates, _signals(df, [0]), horizons=(1,))

    def test_rejects_signal_length_mismatch(self) -> None:
        """
        목적: 길이가 다른 신호는 엉뚱한 날을 신호로 만든다.

        Given: 시세보다 짧은 신호
        When: 계산한다
        Then: ValueError
        """
        df = _market([100.0, 110.0, 121.0])

        with pytest.raises(ValueError, match="길이"):
            compute_forward_returns(df, pd.Series([True, False]), horizons=(1,))

    def test_rejects_signal_index_mismatch(self) -> None:
        """
        목적: 길이가 같아도 인덱스가 다르면 정렬이 어긋난다.

        Given: 인덱스가 다른 같은 길이의 신호
        When: 계산한다
        Then: ValueError
        """
        df = _market([100.0, 110.0, 121.0])
        shifted = pd.Series([True, False, False], index=[10, 11, 12])

        with pytest.raises(ValueError, match="인덱스"):
            compute_forward_returns(df, shifted, horizons=(1,))

    def test_rejects_non_boolean_signals(self) -> None:
        """
        목적: 신호는 bool 이다. 0/1 정수를 받으면 다른 값이 섞여도 통과한다.

        Given: 정수 Series 신호
        When: 계산한다
        Then: ValueError
        """
        df = _market([100.0, 110.0, 121.0])
        numeric = pd.Series([1, 0, 0], index=df.index)

        with pytest.raises(ValueError, match="bool"):
            compute_forward_returns(df, numeric, horizons=(1,))

    def test_rejects_non_positive_horizon(self) -> None:
        """
        목적: 구간 0 이하는 신호 당일이거나 과거라 forward return 이 아니다.

        Given: 구간 0
        When: 계산한다
        Then: ValueError
        """
        df = _market([100.0, 110.0, 121.0])

        with pytest.raises(ValueError, match="측정 구간"):
            compute_forward_returns(df, _signals(df, [0]), horizons=(0,))

    def test_rejects_duplicate_horizon(self) -> None:
        """
        목적: 중복 구간은 결과 행을 조용히 부풀려 표본 수를 왜곡한다.

        Given: 같은 구간이 두 번 들어온 입력
        When: 계산한다
        Then: ValueError
        """
        df = _market([100.0, 110.0, 121.0])

        with pytest.raises(ValueError, match="중복"):
            compute_forward_returns(df, _signals(df, [0]), horizons=(1, 1))

    def test_rejects_empty_horizons(self) -> None:
        """
        목적: 잴 구간이 없으면 측정이 아니다. 빈 결과를 조용히 내지 않는다.

        Given: 빈 구간 목록
        When: 계산한다
        Then: ValueError
        """
        df = _market([100.0, 110.0, 121.0])

        with pytest.raises(ValueError, match="측정 구간"):
            compute_forward_returns(df, _signals(df, [0]), horizons=())


class TestCountExcluded:
    """제외 건수 요약의 계약을 고정한다 (측정 계층의 절대 원칙 4)."""

    def test_summary_covers_every_cell(self) -> None:
        """
        목적: 요약은 (기준 × 구간) 모든 칸을 낸다. 제외가 0건인 칸도 빠지지 않는다.

        Given: 신호 2건과 구간 2개
        When: 제외 건수를 센다
        Then: 칸이 종가 2 + 익일 시가 1 = 3개다
        """
        # Given
        df = _market([100.0 + index for index in range(8)])
        frame = compute_forward_returns(df, _signals(df, [0, 7]), horizons=(1, 3))

        # When
        summary = count_excluded(frame)

        # Then
        assert len(summary) == 3
        assert list(summary.columns) == [COL_BASIS, COL_HORIZON, COL_SIGNAL_COUNT, COL_EXCLUDED_COUNT]

    def test_summary_matches_the_preservation_identity(self) -> None:
        """
        목적: 요약이 보존 항등식과 어긋나지 않음을 고정한다.

        Given: 뒤가 잘리는 신호가 섞인 입력
        When: 제외 건수를 센다
        Then: 칸마다 신호 수 − 제외 수 = 실제 값이 있는 행 수다
        """
        # Given
        df = _market([100.0 + index for index in range(8)])
        frame = compute_forward_returns(df, _signals(df, [0, 6, 7]), horizons=(1, 3))

        # When
        summary = count_excluded(frame)

        # Then
        cells = zip(
            summary[COL_BASIS].tolist(),
            summary[COL_HORIZON].tolist(),
            summary[COL_SIGNAL_COUNT].tolist(),
            summary[COL_EXCLUDED_COUNT].tolist(),
            strict=True,
        )
        for basis, horizon, signal_count, excluded_count in cells:
            cell = frame[(frame[COL_BASIS] == basis) & (frame[COL_HORIZON] == horizon)]
            assert signal_count == 3
            assert signal_count - excluded_count == int(cell[COL_FORWARD_RETURN].notna().sum())

    def test_rejects_frame_without_required_columns(self) -> None:
        """
        목적: 다른 프레임을 넘기면 조용히 빈 요약을 내지 않고 즉시 거부한다.

        Given: 사유 컬럼이 없는 프레임
        When: 제외 건수를 센다
        Then: ValueError
        """
        df = _market([100.0, 110.0, 121.0])
        frame = compute_forward_returns(df, _signals(df, [0]), horizons=(1,))

        with pytest.raises(ValueError, match="필수 컬럼"):
            count_excluded(frame.drop(columns=[COL_EXCLUDED_REASON]))
