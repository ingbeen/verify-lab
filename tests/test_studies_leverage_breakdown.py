"""검증 #8 — 축 분해와 집계 계약

전체 합계 하나로 끝내지 않는다는 원칙(측정의 원칙 12)과, 표본이 모자란 칸도 행을 남긴다는
원칙(측정의 원칙 17)을 여기서 고정한다. **비중첩 표본 수**는 롤링 전수의 겹침을 드러내는
유일한 축이라 정확성을 따로 못박는다.
"""

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.measure.constants import COL_EXCLUDED_COUNT, COL_HORIZON
from verify_lab.studies.leverage_tracking.breakdown import (
    attach_axes,
    max_non_overlapping,
    summarize_by_axis,
    summarize_by_horizon,
)
from verify_lab.studies.leverage_tracking.constants import (
    COL_DIRECTION,
    COL_JUDGEABLE,
    COL_NON_OVERLAPPING_COUNT,
    COL_PERIOD,
    COL_SAMPLE_COUNT,
    COL_START_POSITION,
    DIRECTION_DOWN,
    DIRECTION_FLAT,
    DIRECTION_UP,
    JUDGEABLE_NO,
    JUDGEABLE_YES,
    PERIOD_HIGH_RATE,
    PERIOD_LOW_RATE,
)
from verify_lab.studies.leverage_tracking.divergence import compute_divergence
from verify_lab.studies.leverage_tracking.pairing import align_pair


def _market_frame(closes: list[float], start: str = "2026-01-02") -> pd.DataFrame:
    """테스트용 최소 시세 프레임을 만든다.

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


def _prepared(base_closes: list[float], target_closes: list[float], horizons: tuple[int, ...], start: str = "2026-01-02"):  # type: ignore[no-untyped-def]
    """정렬 → 괴리 → 축 붙이기까지 한 번에 수행한다.

    Args:
        base_closes: 1배 종가
        target_closes: 배수 종가
        horizons: 보유 기간 목록
        start: 첫 거래일

    Returns:
        축이 붙은 괴리 결과
    """
    alignment = align_pair(_market_frame(base_closes, start), _market_frame(target_closes, start))
    divergence = compute_divergence(alignment.frame, multiple=2.0, horizons=horizons)
    return attach_axes(divergence, alignment.frame)


class TestMaxNonOverlapping:
    """비중첩 표본 수 — 롤링 전수가 실제로 몇 개의 독립 관측인지"""

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


class TestAttachAxes:
    """분해 축 — 무엇으로 나누는가"""

    def test_방향은_1배_수익률의_부호로_나눈다(self) -> None:
        """
        목적: 방향 축의 정의를 고정한다. 보합은 어느 쪽에도 넣지 않는다

        Given: 오르고·그대로이고·내리는 세 구간
        When: 축을 붙인다
        Then: 오름·보합·내림이 각각 붙는다
        """
        # Given / When
        prepared = _prepared([100.0, 110.0, 110.0, 99.0], [50.0, 55.0, 55.0, 49.0], horizons=(1,))

        # Then
        directions = prepared[prepared[COL_DIRECTION].notna()][COL_DIRECTION].tolist()
        assert directions == [DIRECTION_UP, DIRECTION_FLAT, DIRECTION_DOWN]

    def test_시기는_시작일의_금리_국면으로_나눈다(self) -> None:
        """
        목적: 시기 축이 시작일 기준인지 고정한다 (구간이 경계를 걸쳐도 진입 시점으로 센다)

        Given: 2021년에 시작하는 구간과 2022년에 시작하는 구간
        When: 축을 붙인다
        Then: 각각 저금리·고금리로 나뉜다
        """
        # Given / When
        prepared = _prepared([100.0, 101.0, 102.0], [50.0, 51.0, 52.0], horizons=(1,), start="2021-12-30")

        # Then
        periods = prepared.sort_values(COL_DATE)[COL_PERIOD].tolist()
        assert periods[0] == PERIOD_LOW_RATE
        assert periods[-1] == PERIOD_HIGH_RATE

    def test_시작일_위치가_거래일_순서와_같다(self) -> None:
        """
        목적: 비중첩 계산이 쓰는 위치 인덱스가 실제 거래일 순서인지 고정한다

        Given: 거래일 4일짜리 짝
        When: 축을 붙인다
        Then: 위치가 0·1·2·3 이다
        """
        # Given / When
        prepared = _prepared([100.0, 101.0, 102.0, 103.0], [50.0, 51.0, 52.0, 53.0], horizons=(1,))

        # Then
        assert sorted(prepared[COL_START_POSITION].unique().tolist()) == [0, 1, 2, 3]

    def test_다른_짝의_결과를_붙이면_예외(self) -> None:
        """
        목적: 서로 다른 짝의 결과와 정렬 프레임을 섞는 사고를 막는지 고정한다

        Given: 날짜가 겹치지 않는 괴리 결과와 정렬 프레임
        When: 축을 붙인다
        Then: ValueError 가 난다
        """
        # Given
        alignment_a = align_pair(_market_frame([100.0, 101.0, 102.0]), _market_frame([50.0, 51.0, 52.0]))
        alignment_b = align_pair(
            _market_frame([100.0, 101.0, 102.0], start="2020-01-02"),
            _market_frame([50.0, 51.0, 52.0], start="2020-01-02"),
        )
        divergence = compute_divergence(alignment_a.frame, multiple=2.0, horizons=(1,))

        # When / Then
        with pytest.raises(ValueError, match="모르는 날짜"):
            attach_axes(divergence, alignment_b.frame)


class TestSummarize:
    """집계 — 표본이 조용히 사라지지 않는가"""

    def test_표본_수와_제외_수의_합이_시작일_수와_같다(self) -> None:
        """
        목적: 표본 보존을 집계 단계에서도 고정한다

        Given: 거래일 8일짜리 짝, 구간 3
        When: 구간별로 집계한다
        Then: 유효 표본 + 제외 = 8 이다
        """
        # Given
        prepared = _prepared(
            [100.0, 103.0, 99.0, 104.0, 101.0, 106.0, 102.0, 108.0],
            [50.0, 53.0, 48.0, 53.0, 49.0, 55.0, 49.0, 56.0],
            horizons=(3,),
        )

        # When
        summary = summarize_by_horizon(prepared)

        # Then
        row = summary.iloc[0]
        assert row[COL_SAMPLE_COUNT] + row[COL_EXCLUDED_COUNT] == 8

    def test_표본이_하한에_못_미쳐도_행이_남는다(self) -> None:
        """
        목적: 측정의 원칙 17 을 고정한다 — 행을 지우면 못 봤다는 사실 자체가 사라진다

        Given: 유효 표본이 2건뿐인 짝
        When: 집계한다
        Then: 행이 남고 판정가능이 「아니오」다
        """
        # Given
        prepared = _prepared([100.0, 103.0, 99.0, 104.0], [50.0, 53.0, 48.0, 53.0], horizons=(2,))

        # When
        summary = summarize_by_horizon(prepared)

        # Then
        assert len(summary) == 1
        assert summary.iloc[0][COL_SAMPLE_COUNT] == 2
        assert summary.iloc[0][COL_JUDGEABLE] == JUDGEABLE_NO

    def test_표본이_충분하면_판정가능이_예다(self) -> None:
        """
        목적: 판정가능 경계를 고정한다

        Given: 유효 표본이 하한 이상인 짝
        When: 집계한다
        Then: 판정가능이 「예」다
        """
        # Given
        base = [100.0 + index for index in range(15)]
        target = [50.0 + index * 2 for index in range(15)]
        prepared = _prepared(base, target, horizons=(1,))

        # When
        summary = summarize_by_horizon(prepared)

        # Then
        assert summary.iloc[0][COL_SAMPLE_COUNT] == 14
        assert summary.iloc[0][COL_JUDGEABLE] == JUDGEABLE_YES

    def test_비중첩_표본_수가_유효_표본보다_작다(self) -> None:
        """
        목적: 롤링 전수의 겹침이 집계에 드러나는지 고정한다

        Given: 거래일 15일짜리 짝, 구간 5
        When: 집계한다
        Then: 비중첩 표본 수가 유효 표본 수보다 작다
        """
        # Given
        base = [100.0 + index for index in range(15)]
        target = [50.0 + index * 2 for index in range(15)]
        prepared = _prepared(base, target, horizons=(5,))

        # When
        summary = summarize_by_horizon(prepared)

        # Then
        row = summary.iloc[0]
        assert row[COL_NON_OVERLAPPING_COUNT] < row[COL_SAMPLE_COUNT]
        assert row[COL_NON_OVERLAPPING_COUNT] == 2

    def test_축별_집계는_구간과_축의_곱으로_나온다(self) -> None:
        """
        목적: 축 분해 결과의 행 구성을 고정한다

        Given: 오름과 내림이 섞인 짝, 구간 2개
        When: 방향 축으로 집계한다
        Then: 각 행이 (구간, 방향) 짝이고 방향이 둘 다 나온다
        """
        # Given
        prepared = _prepared(
            [100.0, 103.0, 99.0, 104.0, 101.0, 106.0, 102.0, 108.0],
            [50.0, 53.0, 48.0, 53.0, 49.0, 55.0, 49.0, 56.0],
            horizons=(1, 2),
        )

        # When
        summary = summarize_by_axis(prepared, COL_DIRECTION)

        # Then
        assert set(summary.columns) >= {COL_HORIZON, COL_DIRECTION, COL_SAMPLE_COUNT}
        assert set(summary[COL_DIRECTION].dropna()) == {DIRECTION_UP, DIRECTION_DOWN}
