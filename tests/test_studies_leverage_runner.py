"""검증 #8 — 실행 계층 계약

산출물은 **사용자가 직접 여는 파일**이므로 한글 헤더와 식별 컬럼을 계약으로 고정한다.
실제 시세 파일에 의존하면 데이터를 갱신할 때마다 테스트가 깨지므로 합성 데이터를 쓴다.
"""

from pathlib import Path

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.report.constants import DISPLAY_HORIZON, DISPLAY_SAMPLE_COUNT
from verify_lab.studies.leverage_tracking.constants import (
    DISPLAY_BASE_TICKER,
    DISPLAY_DIVIDEND_ADJUSTMENT,
    DISPLAY_INDEX_NAME,
    DISPLAY_JUDGEABLE,
    DISPLAY_MULTIPLE,
    DISPLAY_NON_OVERLAPPING,
    DISPLAY_PRODUCT_TYPE,
    DISPLAY_TARGET_TICKER,
    JUDGEABLE_YES,
    PRODUCT_ETF,
    LeveragePair,
)
from verify_lab.studies.leverage_tracking.runner import headline, run_study

# 합성 데이터로 만들 짝. 실제 종목과 무관한 이름을 쓴다
TEST_PAIRS = (LeveragePair("테스트지수", "BASE1X", "TARGET2X", 2.0, PRODUCT_ETF, "테스트 지수"),)

TEST_HORIZONS = (5, 10)


def _write_market_csv(path: Path, closes: list[float]) -> None:
    """테스트용 시세 CSV 를 만든다.

    Args:
        path: 저장 경로
        closes: 종가 목록
    """
    dates = pd.bdate_range(start="2020-01-02", periods=len(closes))
    pd.DataFrame(
        {
            COL_DATE: dates.date,
            COL_OPEN: closes,
            COL_HIGH: closes,
            COL_LOW: closes,
            COL_CLOSE: closes,
            COL_VOLUME: [1_000] * len(closes),
        }
    ).to_csv(path, index=False)


@pytest.fixture
def market_dir(tmp_path: Path) -> Path:
    """합성 시세 파일을 담은 임시 폴더를 만든다.

    1배는 완만히 오르내리고 배수 상품은 대략 2배로 따라간다.

    Args:
        tmp_path: pytest 가 테스트마다 새로 만드는 임시 디렉터리

    Returns:
        시세 파일이 놓인 폴더
    """
    base_closes: list[float] = [100.0]
    target_closes: list[float] = [50.0]

    for index in range(1, 60):
        # 오르내림이 섞이도록 부호를 번갈아 준다. 경로 효과가 0 이 아니게 만드는 것이 목적이다
        daily = 0.01 if index % 3 else -0.012
        base_closes.append(base_closes[-1] * (1.0 + daily))
        target_closes.append(target_closes[-1] * (1.0 + 2.0 * daily))

    _write_market_csv(tmp_path / "BASE1X_max.csv", base_closes)
    _write_market_csv(tmp_path / "TARGET2X_max.csv", target_closes)

    return tmp_path


class TestRunStudy:
    """실행 산출물의 구성"""

    def test_네_표를_모두_낸다(self, market_dir: Path) -> None:
        """
        목적: 산출물 구성을 고정한다

        Given: 합성 시세 한 쌍
        When: 검증을 실행한다
        Then: 집계·축분해·분배금·전체구간 표가 모두 비어 있지 않다
        """
        # When
        outputs = run_study(pairs=TEST_PAIRS, horizons=TEST_HORIZONS, market_dir=market_dir)

        # Then
        assert not outputs.divergence.empty
        assert not outputs.breakdown.empty
        assert not outputs.distribution.empty
        assert not outputs.full_period.empty

    def test_쌍마다_원자료_파일을_낸다(self, market_dir: Path) -> None:
        """
        목적: 사용자 대조용 원자료가 쌍마다 나오는지 고정한다

        Given: 합성 시세 한 쌍
        When: 검증을 실행한다
        Then: 배수 종목 이름으로 원자료가 하나 나온다
        """
        # When
        outputs = run_study(pairs=TEST_PAIRS, horizons=TEST_HORIZONS, market_dir=market_dir)

        # Then
        assert set(outputs.windows) == {"TARGET2X"}
        assert not outputs.windows["TARGET2X"].empty

    def test_모든_표에_식별_컬럼이_붙는다(self, market_dir: Path) -> None:
        """
        목적: 표를 나란히 놓고 읽을 수 있도록 식별 컬럼을 고정한다

        Given: 합성 시세 한 쌍
        When: 검증을 실행한다
        Then: 집계·축분해·분배금 표에 지수·1배·배수·배수값·상품이 모두 있다
        """
        # Given
        identity = {
            DISPLAY_INDEX_NAME,
            DISPLAY_BASE_TICKER,
            DISPLAY_TARGET_TICKER,
            DISPLAY_MULTIPLE,
            DISPLAY_PRODUCT_TYPE,
        }

        # When
        outputs = run_study(pairs=TEST_PAIRS, horizons=TEST_HORIZONS, market_dir=market_dir)

        # Then
        for table in (outputs.divergence, outputs.breakdown, outputs.distribution):
            assert identity <= set(table.columns)

    def test_모든_헤더가_한글이거나_기호다(self, market_dir: Path) -> None:
        """
        목적: 산출물 헤더에 영문 토큰이 새지 않는지 고정한다

        Given: 합성 시세 한 쌍
        When: 검증을 실행한다
        Then: 어느 표에도 영문자로만 이뤄진 헤더가 없다
        """
        # When
        outputs = run_study(pairs=TEST_PAIRS, horizons=TEST_HORIZONS, market_dir=market_dir)

        # Then
        tables = [outputs.divergence, outputs.breakdown, outputs.distribution, outputs.full_period]
        tables.extend(outputs.windows.values())

        for table in tables:
            english_only = [column for column in table.columns if column.replace(" ", "").isascii()]
            assert not english_only, f"영문 헤더가 남아 있습니다: {english_only}"

    def test_분배금_표에_배당_보정분이_있다(self, market_dir: Path) -> None:
        """
        목적: 원본가 결정의 대가를 드러내는 컬럼이 빠지지 않는지 고정한다

        Given: 수정주가 파일이 없는 합성 시세 (분배금 없음)
        When: 검증을 실행한다
        Then: 배당 보정분 컬럼이 있고 값이 0 이다
        """
        # When
        outputs = run_study(pairs=TEST_PAIRS, horizons=TEST_HORIZONS, market_dir=market_dir)

        # Then
        assert DISPLAY_DIVIDEND_ADJUSTMENT in outputs.distribution.columns
        assert outputs.distribution[DISPLAY_DIVIDEND_ADJUSTMENT].abs().max() == 0.0

    def test_전체_구간은_쌍마다_한_줄이다(self, market_dir: Path) -> None:
        """
        목적: 상장 후 전체 구간이 사례 한 건으로 나오는지 고정한다

        Given: 합성 시세 한 쌍
        When: 검증을 실행한다
        Then: 전체 구간 표가 한 줄이다
        """
        # When
        outputs = run_study(pairs=TEST_PAIRS, horizons=TEST_HORIZONS, market_dir=market_dir)

        # Then
        assert len(outputs.full_period) == 1

    def test_짝_목록이_비면_예외(self, market_dir: Path) -> None:
        """
        목적: 빈 실행을 조용히 통과시키지 않는지 고정한다

        Given: 빈 짝 목록
        When: 검증을 실행한다
        Then: 예외가 난다
        """
        # When / Then
        with pytest.raises(ValueError):
            run_study(pairs=(), horizons=TEST_HORIZONS, market_dir=market_dir)


class TestHeadline:
    """화면 요약"""

    def test_판정_가능한_칸만_보여준다(self, market_dir: Path) -> None:
        """
        목적: 화면 요약이 표본 부족 칸을 걸러내는지 고정한다

        Given: 합성 시세 한 쌍
        When: 화면 요약을 만든다
        Then: 모든 행이 판정 가능한 칸에서 왔고 요약에는 판정가능 컬럼이 없다
        """
        # Given
        outputs = run_study(pairs=TEST_PAIRS, horizons=TEST_HORIZONS, market_dir=market_dir)

        # When
        summary = headline(outputs)

        # Then
        judgeable_count = int((outputs.divergence[DISPLAY_JUDGEABLE] == JUDGEABLE_YES).sum())
        assert len(summary) == judgeable_count
        assert DISPLAY_JUDGEABLE not in summary.columns

    def test_비중첩_표본을_함께_보여준다(self, market_dir: Path) -> None:
        """
        목적: 롤링 전수의 겹침이 화면에서도 보이는지 고정한다

        Given: 합성 시세 한 쌍
        When: 화면 요약을 만든다
        Then: 표본과 비중첩 표본이 나란히 있다
        """
        # Given
        outputs = run_study(pairs=TEST_PAIRS, horizons=TEST_HORIZONS, market_dir=market_dir)

        # When
        summary = headline(outputs)

        # Then
        assert {DISPLAY_SAMPLE_COUNT, DISPLAY_NON_OVERLAPPING, DISPLAY_HORIZON} <= set(summary.columns)
