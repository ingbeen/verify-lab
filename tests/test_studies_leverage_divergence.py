"""검증 #8 — 괴리 분해 계약

이 검증의 결론은 **괴리를 「경로 효과」와 「상품 비용」으로 나눈 값**이다. 두 항목이
어긋나면 결론 전체가 무효이므로 분해 항등식을 테스트로 못박는다.

함께 고정하는 것은 넷이다 — N=1 항등식(자기 자신과 짝지으면 괴리가 0), 표본 보존
(구간이 데이터를 넘어도 행이 남는다), 실현 배수 필터, 그리고 미래 참조 감시다.
"""

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.measure.constants import COL_EXCLUDED_REASON, COL_HORIZON, REASON_NONE, REASON_OUT_OF_RANGE
from verify_lab.studies.leverage_tracking.constants import (
    COL_ACTUAL,
    COL_NAIVE_EXPECTED,
    COL_PATH_EFFECT,
    COL_PATH_IDEAL,
    COL_PRODUCT_COST,
    COL_REALIZED_MULTIPLE,
    COL_TOTAL_DIVERGENCE,
    REASON_BASE_RETURN_TOO_SMALL,
)
from verify_lab.studies.leverage_tracking.divergence import compute_divergence
from verify_lab.studies.leverage_tracking.pairing import align_pair

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12


def _market_frame(closes: list[float], start: str = "2026-01-02") -> pd.DataFrame:
    """테스트용 최소 시세 프레임을 만든다.

    거래일은 영업일 기준으로 연속해서 매긴다. 날짜 자체는 계약에 영향을 주지 않는다.

    Args:
        closes: 종가 목록
        start: 첫 거래일 (YYYY-MM-DD)

    Returns:
        시세 스키마를 갖춘 DataFrame
    """
    dates = pd.bdate_range(start=start, periods=len(closes))
    return pd.DataFrame(
        {
            COL_DATE: dates,
            COL_OPEN: closes,
            COL_HIGH: closes,
            COL_LOW: closes,
            COL_CLOSE: closes,
            COL_VOLUME: [1_000] * len(closes),
        }
    )


def _ideal_leveraged_path(base_closes: list[float], multiple: float) -> list[float]:
    """일간 수익률에 배수를 곱해 복리로 쌓은 «이론상 완벽한 배수 상품»의 종가를 만든다.

    비용도 추적오차도 없는 상품이므로, 이것을 배수 상품으로 넣으면 상품 비용이 0 이어야 한다.

    Args:
        base_closes: 1배 상품의 종가 목록
        multiple: 명목 배수

    Returns:
        같은 길이의 이론 종가 목록 (시작값 100)
    """
    path = [100.0]
    for previous, current in zip(base_closes, base_closes[1:], strict=False):
        daily_return = current / previous - 1.0
        path.append(path[-1] * (1.0 + multiple * daily_return))

    return path


class TestDecompositionIdentity:
    """괴리 분해 항등식 — 이 검증의 결론이 성립하는 조건"""

    def test_두_분해_항목의_합이_총_괴리와_같다(self) -> None:
        """
        목적: 경로 효과 + 상품 비용 = 총 괴리 를 모든 행에서 고정한다

        Given: 오르내림이 섞인 1배 시세와 임의로 어긋나는 배수 시세
        When: 괴리를 분해한다
        Then: 값이 있는 모든 행에서 두 항목의 합이 총 괴리와 같다
        """
        # Given
        base_closes = [100.0, 103.0, 99.0, 104.0, 101.0, 106.0, 102.0, 108.0]
        target_closes = [50.0, 53.5, 48.0, 53.0, 49.5, 55.0, 49.0, 56.0]
        alignment = align_pair(_market_frame(base_closes), _market_frame(target_closes))

        # When
        result = compute_divergence(alignment.frame, multiple=2.0, horizons=(1, 2, 3))

        # Then
        valid = result[result[COL_EXCLUDED_REASON] == REASON_NONE]
        assert not valid.empty
        assert (valid[COL_PATH_EFFECT] + valid[COL_PRODUCT_COST]).tolist() == pytest.approx(
            valid[COL_TOTAL_DIVERGENCE].tolist(), abs=EXACT_TOLERANCE
        )

    def test_경로_효과는_이론값에서_단순_배수를_뺀_값이다(self) -> None:
        """
        목적: 경로 효과의 정의를 고정한다

        Given: 임의의 두 시세
        When: 괴리를 분해한다
        Then: 경로 효과 = 이론 경로 − 단순 배수 기대치
        """
        # Given
        base_closes = [100.0, 105.0, 98.0, 103.0, 107.0]
        target_closes = [50.0, 55.0, 47.0, 52.0, 56.0]
        alignment = align_pair(_market_frame(base_closes), _market_frame(target_closes))

        # When
        result = compute_divergence(alignment.frame, multiple=2.0, horizons=(1, 2))

        # Then
        valid = result[result[COL_EXCLUDED_REASON] == REASON_NONE]
        assert (valid[COL_PATH_IDEAL] - valid[COL_NAIVE_EXPECTED]).tolist() == pytest.approx(
            valid[COL_PATH_EFFECT].tolist(), abs=EXACT_TOLERANCE
        )

    def test_상품_비용은_실제에서_이론값을_뺀_값이다(self) -> None:
        """
        목적: 상품 비용의 정의를 고정한다

        Given: 임의의 두 시세
        When: 괴리를 분해한다
        Then: 상품 비용 = 실제 − 이론 경로
        """
        # Given
        base_closes = [100.0, 105.0, 98.0, 103.0, 107.0]
        target_closes = [50.0, 55.0, 47.0, 52.0, 56.0]
        alignment = align_pair(_market_frame(base_closes), _market_frame(target_closes))

        # When
        result = compute_divergence(alignment.frame, multiple=2.0, horizons=(1, 2))

        # Then
        valid = result[result[COL_EXCLUDED_REASON] == REASON_NONE]
        assert (valid[COL_ACTUAL] - valid[COL_PATH_IDEAL]).tolist() == pytest.approx(
            valid[COL_PRODUCT_COST].tolist(), abs=EXACT_TOLERANCE
        )


class TestBoundaryCases:
    """항등식이 성립해야 하는 경계 — 여기서 0 이 안 나오면 산식이 틀린 것이다"""

    def test_배수_1로_자기_자신과_짝지으면_괴리가_0이다(self) -> None:
        """
        목적: 산식의 기준점을 고정한다. 여기서 0 이 아니면 다른 모든 값도 믿을 수 없다

        Given: 같은 시세를 1배와 배수 양쪽에 넣은 짝
        When: 배수 1 로 괴리를 분해한다
        Then: 경로 효과·상품 비용·총 괴리가 전부 0 이다
        """
        # Given
        closes = [100.0, 103.0, 99.0, 104.0, 101.0, 106.0]
        alignment = align_pair(_market_frame(closes), _market_frame(closes))

        # When
        result = compute_divergence(alignment.frame, multiple=1.0, horizons=(1, 2, 3))

        # Then
        valid = result[result[COL_EXCLUDED_REASON] == REASON_NONE]
        assert valid[COL_PATH_EFFECT].tolist() == pytest.approx([0.0] * len(valid), abs=EXACT_TOLERANCE)
        assert valid[COL_PRODUCT_COST].tolist() == pytest.approx([0.0] * len(valid), abs=EXACT_TOLERANCE)
        assert valid[COL_TOTAL_DIVERGENCE].tolist() == pytest.approx([0.0] * len(valid), abs=EXACT_TOLERANCE)

    def test_이론상_완벽한_배수_상품은_상품_비용이_0이다(self) -> None:
        """
        목적: 경로 효과와 상품 비용이 실제로 분리되는지 고정한다

        Given: 일간 수익률의 정확히 2배로 복리를 쌓은 «완벽한» 배수 상품
        When: 괴리를 분해한다
        Then: 상품 비용은 0 이고, 경로 효과는 0 이 아니다 (음의 복리가 남는다)
        """
        # Given
        base_closes = [100.0, 106.0, 97.0, 104.0, 99.0, 108.0]
        target_closes = _ideal_leveraged_path(base_closes, 2.0)
        alignment = align_pair(_market_frame(base_closes), _market_frame(target_closes))

        # When
        result = compute_divergence(alignment.frame, multiple=2.0, horizons=(2, 3))

        # Then
        valid = result[result[COL_EXCLUDED_REASON] == REASON_NONE]
        assert valid[COL_PRODUCT_COST].tolist() == pytest.approx([0.0] * len(valid), abs=EXACT_TOLERANCE)
        assert any(abs(value) > EXACT_TOLERANCE for value in valid[COL_PATH_EFFECT])


class TestSamplePreservation:
    """표본 보존 — 행이 사라지면 생존편향이 생긴다"""

    def test_구간_끝이_데이터를_넘어도_행이_남는다(self) -> None:
        """
        목적: 제외된 표본이 행째로 사라지지 않는지 고정한다

        Given: 거래일 5일짜리 짝
        When: 구간 3 으로 괴리를 낸다
        Then: 행 수는 시작일 수 그대로이고, 넘어간 칸은 값이 비고 사유가 붙는다
        """
        # Given
        base_closes = [100.0, 103.0, 99.0, 104.0, 101.0]
        target_closes = [50.0, 53.0, 48.0, 53.0, 49.0]
        alignment = align_pair(_market_frame(base_closes), _market_frame(target_closes))

        # When
        result = compute_divergence(alignment.frame, multiple=2.0, horizons=(3,))

        # Then
        assert len(result) == 5
        excluded = result[result[COL_EXCLUDED_REASON] == REASON_OUT_OF_RANGE]
        assert len(excluded) == 3
        assert excluded[COL_TOTAL_DIVERGENCE].isna().all()

    def test_행_수는_시작일_수_곱하기_구간_수다(self) -> None:
        """
        목적: long-form 스키마의 행 수 계약을 고정한다

        Given: 거래일 8일짜리 짝
        When: 구간 3개로 괴리를 낸다
        Then: 행 수가 8 × 3 이다
        """
        # Given
        base_closes = [100.0, 103.0, 99.0, 104.0, 101.0, 106.0, 102.0, 108.0]
        target_closes = [50.0, 53.0, 48.0, 53.0, 49.0, 55.0, 49.0, 56.0]
        alignment = align_pair(_market_frame(base_closes), _market_frame(target_closes))

        # When
        result = compute_divergence(alignment.frame, multiple=2.0, horizons=(1, 2, 3))

        # Then
        assert len(result) == 8 * 3


class TestRealizedMultiple:
    """실현 배수 — 분모가 0 근처면 값이 폭발하므로 내지 않는다"""

    def test_1배_수익률이_작으면_실현_배수를_비운다(self) -> None:
        """
        목적: 실현 배수 필터를 고정한다

        Given: 1배가 거의 움직이지 않은 구간 (0.1%)
        When: 괴리를 낸다
        Then: 실현 배수가 비고 사유가 붙는다. 괴리 3값은 그대로 있다
        """
        # Given
        base_closes = [100.0, 100.1]
        target_closes = [50.0, 50.2]
        alignment = align_pair(_market_frame(base_closes), _market_frame(target_closes))

        # When
        result = compute_divergence(alignment.frame, multiple=2.0, horizons=(1,))

        # Then
        first = result.iloc[0]
        assert pd.isna(first[COL_REALIZED_MULTIPLE])
        assert first[COL_EXCLUDED_REASON] == REASON_BASE_RETURN_TOO_SMALL
        assert not pd.isna(first[COL_TOTAL_DIVERGENCE])

    def test_1배_수익률이_충분하면_실현_배수를_낸다(self) -> None:
        """
        목적: 필터를 넘긴 칸의 실현 배수 산식을 고정한다

        Given: 1배가 10% 오르고 배수 상품이 19% 오른 구간
        When: 괴리를 낸다
        Then: 실현 배수가 1.9 다
        """
        # Given
        base_closes = [100.0, 110.0]
        target_closes = [50.0, 59.5]
        alignment = align_pair(_market_frame(base_closes), _market_frame(target_closes))

        # When
        result = compute_divergence(alignment.frame, multiple=2.0, horizons=(1,))

        # Then
        assert result.iloc[0][COL_REALIZED_MULTIPLE] == pytest.approx(1.9, abs=EXACT_TOLERANCE)


class TestNoLookAhead:
    """미래 참조 감시 — 뒤를 잘라도 겹치는 구간의 값이 같아야 한다"""

    def test_뒤를_잘라낸_입력과_값이_같다(self, assert_stable_under_truncation) -> None:  # type: ignore[no-untyped-def]
        """
        목적: 판정일 이후 데이터가 결과를 바꾸지 않는지 고정한다

        Given: 거래일 12일짜리 짝
        When: 앞 8일만 넣은 결과와 전체를 넣은 결과를 비교한다
        Then: 겹치는 칸의 총 괴리가 같다
        """
        # Given
        base_closes = [100.0, 103.0, 99.0, 104.0, 101.0, 106.0, 102.0, 108.0, 105.0, 111.0, 107.0, 113.0]
        target_closes = [50.0, 53.0, 48.0, 53.0, 49.0, 55.0, 49.0, 56.0, 52.0, 59.0, 54.0, 61.0]
        base = _market_frame(base_closes)
        target = _market_frame(target_closes)

        def run(frame: pd.DataFrame) -> pd.DataFrame:
            """잘라낸 시세로 괴리를 다시 계산한다."""
            cut_target = target.iloc[: len(frame)]
            alignment = align_pair(frame, cut_target)
            return compute_divergence(alignment.frame, multiple=2.0, horizons=(1, 2, 3))

        # When / Then
        assert_stable_under_truncation(
            run,
            base,
            cut=8,
            key_columns=[COL_DATE, COL_HORIZON],
            value_column=COL_TOTAL_DIVERGENCE,
        )
