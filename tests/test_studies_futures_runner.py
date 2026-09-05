"""검증 #9 실행 계층의 계약을 고정한다.

두 가지를 못박는다.

- **비중첩 표본은 검증 #8 과 같은 함수로 센다.** 이 값이 검증마다 다른 규칙으로 계산되면
  두 결과 문서의 같은 이름 컬럼을 나란히 놓고 비교할 수 없다
- **최대 유효 레버리지는 잴 수 없을 때 0 이 아니다.** `max(0.0, nan)` 이 파이썬에서 `0.0` 을
  돌려주므로, 전 구간이 소진된 칸이 「위험이 전혀 없었다」로 읽히는 사고가 실제로 가능하다
"""

import math

import numpy as np

from verify_lab.measure.constants import COL_JUDGEABLE, JUDGEABLE_NO, JUDGEABLE_YES, MIN_SAMPLE_PER_CELL
from verify_lab.measure.statistics import max_non_overlapping
from verify_lab.studies.futures_leverage import constants as futures_constants
from verify_lab.studies.futures_leverage.runner import (
    COL_NON_OVERLAPPING,
    _max_effective_leverage,
    _summarize,
)


class TestNonOverlappingContract:
    """비중첩 표본 — 검증 #8 과 같은 정의를 쓰는가"""

    def test_집계가_공통_함수와_같은_값을_낸다(self) -> None:
        """
        목적: 검증 #9 가 자기 규칙을 따로 두지 않음을 고정한다

        Given: 유효 표본 10개가 연속으로 있고 구간이 3
        When: 실행 계층의 집계와 공통 함수를 각각 부른다
        Then: 두 값이 같다
        """
        # Given
        values = np.arange(10, dtype=float)

        # When
        summarized = _summarize(values, horizon=3)
        expected = max_non_overlapping(list(range(10)), horizon=3)

        # Then
        assert summarized[COL_NON_OVERLAPPING] == expected

    def test_못_잰_칸을_뺀_시작일로만_센다(self) -> None:
        """
        목적: NaN 인 시작일이 비중첩 계산에 들어가지 않음을 고정한다

        Given: 0·1·5·6·10 만 값이 있고 나머지는 NaN 이며 구간이 4
        When: 실행 계층의 집계를 낸다
        Then: 공통 함수에 같은 시작일을 넘긴 값과 일치한다
        """
        # Given
        values = np.full(11, np.nan)
        usable_positions = [0, 1, 5, 6, 10]
        values[usable_positions] = 0.01

        # When
        summarized = _summarize(values, horizon=4)

        # Then
        assert summarized[COL_NON_OVERLAPPING] == max_non_overlapping(usable_positions, horizon=4)

    def test_끝점을_공유하는_두_구간을_모두_센다(self) -> None:
        """
        목적: **정의의 핵심**을 실행 계층에서도 고정한다

        Given: 시작일 0 과 3 만 값이 있고 구간이 3
        When: 실행 계층의 집계를 낸다
        Then: 2개다. 관측일 3 을 공유하지만 수익률 구간은 겹치지 않는다
        """
        # Given
        values = np.full(7, np.nan)
        values[[0, 3]] = 0.01

        # When
        summarized = _summarize(values, horizon=3)

        # Then
        assert summarized[COL_NON_OVERLAPPING] == 2


class TestMaxEffectiveLeverage:
    """최대 유효 레버리지 — 잴 수 없는 칸을 0 으로 만들지 않는가"""

    def test_전_구간이_소진되면_0이_아니라_빈_값이다(self) -> None:
        """
        목적: `max(0.0, nan)` 이 0.0 을 돌려주는 함정을 고정한다

        Given: -2배로 하루에 100% 오르는 가격 (자기자본이 즉시 소진된다)
        When: 최대 유효 레버리지를 낸다
        Then: 0.0 이 아니라 NaN 이다 — 0 은 「위험이 전혀 없었다」로 읽힌다
        """
        # Given
        prices = np.array([100.0, 200.0])

        # When
        result = _max_effective_leverage(prices, multiple=-2.0, horizon=1)

        # Then
        assert math.isnan(result)

    def test_구간을_하나도_잴_수_없으면_빈_값이다(self) -> None:
        """
        목적: 보유 기간이 데이터보다 길 때의 처리를 고정한다

        Given: 거래일 2개인데 보유 기간이 5
        When: 최대 유효 레버리지를 낸다
        Then: NaN 이다
        """
        # Given
        prices = np.array([100.0, 101.0])

        # When
        result = _max_effective_leverage(prices, multiple=2.0, horizon=5)

        # Then
        assert math.isnan(result)

    def test_가격이_내리면_유효_배수가_목표를_넘는다(self) -> None:
        """
        목적: 정상 경로가 값을 내는지, 그리고 **표류 방향**이 맞는지 고정한다

        Given: 완만하게 내리는 가격
        When: 2배로 최대 유효 레버리지를 낸다
        Then: 목표 배수 2.0 을 넘는다 — 자기자본이 줄어 배수가 저절로 올라가는 쪽이다
        """
        # Given
        prices = np.array([100.0, 99.0, 98.0, 97.0, 96.0, 95.0])

        # When
        result = _max_effective_leverage(prices, multiple=2.0, horizon=3)

        # Then
        assert result > 2.0


class TestJudgeableValue:
    """`판정가능` 은 다른 세 검증과 같은 말을 쓴다"""

    def test_판정_가능한_칸이_예다(self) -> None:
        """
        목적: 이 검증만 `True`/`False` 를 내던 것을 막는다.

        같은 이름의 컬럼이 검증마다 다른 값을 가지면 두 산출물을 나란히 읽을 수 없고,
        `measure.screening` 이 `== JUDGEABLE_YES` 로 거르므로 이 표를 판정에 넘기면
        전 칸이 조용히 제외된다.

        Given: 하한을 넘는 유효 표본
        When: 집계 한 줄을 만든다
        Then: `판정가능` 이 「예」 문자열이다
        """
        # Given
        values = np.full(MIN_SAMPLE_PER_CELL + 2, 0.01)

        # When
        summarized = _summarize(values, horizon=1)

        # Then
        assert summarized[COL_JUDGEABLE] == JUDGEABLE_YES

    def test_표본이_모자란_칸이_아니오다(self) -> None:
        """
        목적: 반대쪽 값도 같은 어휘를 쓰는지 고정한다.

        Given: 하한에 못 미치는 유효 표본
        When: 집계 한 줄을 만든다
        Then: `판정가능` 이 「아니오」 문자열이다
        """
        # Given
        values = np.full(MIN_SAMPLE_PER_CELL - 1, 0.01)

        # When
        summarized = _summarize(values, horizon=1)

        # Then
        assert summarized[COL_JUDGEABLE] == JUDGEABLE_NO

    def test_판정가능은_불린이_아니다(self) -> None:
        """
        목적: 값이 우연히 참·거짓으로 읽히는 것을 막는다.

        `"예" == True` 는 거짓이지만 `bool` 을 그대로 두면 CSV 에 `True` 로 나가고
        사용자가 여는 파일에 영문 토큰이 남는다 (`src/verify_lab/CLAUDE.md` 「내부/출력 분리」).

        Given: 표본이 충분한 칸과 모자란 칸
        When: 두 집계를 만든다
        Then: 둘 다 `bool` 이 아니다
        """
        # Given
        enough = np.full(MIN_SAMPLE_PER_CELL + 1, 0.01)
        few = np.full(1, 0.01)

        # When
        results = [_summarize(enough, horizon=1), _summarize(few, horizon=1)]

        # Then
        assert not any(isinstance(row[COL_JUDGEABLE], bool) for row in results)


class TestOutputLabelOwnership:
    """산출물 레이블 사전은 `src` 가 소유한다"""

    def test_레이블_사전이_검증_상수에_있다(self) -> None:
        """
        목적: 다른 네 검증과 같은 관용으로 맞춘다.

        이 검증만 사전을 `scripts/` 에 두고 **문자열 리터럴로** `src` 의 컬럼과 연결하고 있었다.
        한쪽 이름만 바뀌면 영문 토큰이 그대로 사용자에게 나간다.

        Given: 검증 상수 모듈
        When: 산출물 레이블 사전을 읽는다
        Then: 비어 있지 않은 사전이다
        """
        # When
        labels = futures_constants.OUTPUT_LABELS

        # Then
        assert isinstance(labels, dict)
        assert labels
