"""중간선거_사이클 측정 조립 — 불변조건과 계약

**형제 두 매매법이 이미 거는 검사를 이 매매법에도 건다.** 계약 테스트가 둘만 돌면
새 매매법의 산출물이 **컬럼이 비거나 대상이 섞여도 통과한다.**

여기서 보는 것은 셋이다.

| 무엇 | 왜 |
| --- | --- |
| `DATASETS` 의 **표시 이름 중복 금지** | 종목명이 곧 데이터셋 구분자라 겹치면 **서로 다른 대상의 행이 조용히 뒤섞인다** (`src/verify_lab/CLAUDE.md` 「종목은 코드가 아니라 이름으로 냅니다」) |
| 축·판정·비중첩의 조립 | 사이클 네 칸이 다 나오는지, 지수가 「판정 안 함」이 되는지, 롤링 기준선의 비중첩이 표본보다 적은지 |
| 배당락의 **빈칸과 0 의 구별** | 지수는 분배금이 없어 «비우고», ETF 는 재서 값을 넣는다 — 0 으로 채우면 「안 걸림」과 「못 쟀다」가 같아진다 |
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from verify_lab.common_constants import (
    ADJUSTED_FILE_TEMPLATE,
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_VALUE,
    COL_VOLUME,
    INDEX_FILE_TEMPLATE,
    MARKET_FILE_TEMPLATE,
    PRICE_DECIMALS,
)
from verify_lab.measure.constants import COL_DIVIDEND_HIT_COUNT, COL_DIVIDEND_MEASURED, COL_JUDGEABLE
from verify_lab.measure.screening import COL_DIRECTION, DIRECTION_UP
from verify_lab.measure.statistics import COL_SAMPLE_COUNT
from verify_lab.studies.midterm_cycle.constants import (
    COL_BASELINE_NON_OVERLAPPING,
    COL_CYCLE_POSITION,
    COL_NON_OVERLAPPING,
    CYCLE_POSITIONS,
    DATASETS,
    Dataset,
    datasets_of,
)
from verify_lab.studies.midterm_cycle.runner import run_study

# 합성 시세 구간. 10월 진입이 사이클 네 자리에 모두 생기려면 몇 해가 필요하다
SYNTHETIC_START = "2012-01-02"
SYNTHETIC_END = "2025-12-31"

# 합성 시세를 만드는 난수 시드. **시드 없는 난수는 금지다**
SYNTHETIC_SEED = 20260922

# 순열 검정 반복 수. 계약만 보므로 적게 돌린다
TEST_REPEATS = 50


def _frame() -> pd.DataFrame:
    """장중 등락이 있는 합성 시세를 만든다.

    Returns:
        시세 스키마 DataFrame
    """
    days = pd.bdate_range(SYNTHETIC_START, SYNTHETIC_END)
    rng = np.random.default_rng(SYNTHETIC_SEED)
    closes = 100.0 * np.cumprod(np.concatenate([[1.0], 1.0 + rng.normal(0.0004, 0.01, len(days) - 1)]))
    opens = np.concatenate([[closes[0]], closes[:-1] * 1.001])

    return pd.DataFrame(
        {
            COL_DATE: days.strftime("%Y-%m-%d"),
            COL_OPEN: np.round(opens, PRICE_DECIMALS),
            COL_HIGH: np.round(np.maximum(opens, closes) * 1.01, PRICE_DECIMALS),
            COL_LOW: np.round(np.minimum(opens, closes) * 0.99, PRICE_DECIMALS),
            COL_CLOSE: np.round(closes, PRICE_DECIMALS),
            COL_VOLUME: 1_000_000,
        }
    )


@pytest.fixture(scope="module")
def outputs(tmp_path_factory: pytest.TempPathFactory) -> pd.DataFrame:
    """합성 ETF 와 합성 지수로 돈 측정 표.

    **지수를 함께 넣는다** — 판정하지 않는 대상과 배당락을 비우는 대상이 있어야
    두 계약이 검사된다.
    """
    directory = tmp_path_factory.mktemp("midterm_cycle_runner")
    frame = _frame()
    frame.to_csv(directory / MARKET_FILE_TEMPLATE.format(ticker="SYN"), index=False)
    # **수정주가는 원본가와 조금 다르게 둔다** — 같으면 배당락 왜곡이 0 이라 「쟀다」가 안 보인다
    adjusted = frame.copy()
    adjusted[COL_CLOSE] = np.round(adjusted[COL_CLOSE] * 0.99, PRICE_DECIMALS)
    adjusted.to_csv(directory / ADJUSTED_FILE_TEMPLATE.format(ticker="SYN"), index=False)
    pd.DataFrame({COL_DATE: frame[COL_DATE], COL_VALUE: frame[COL_CLOSE] / 10.0}).to_csv(
        directory / INDEX_FILE_TEMPLATE.format(ticker="SYNIDX"), index=False
    )

    etf = Dataset(
        ticker="SYN",
        label="합성 ETF",
        symbol="SYN",
        directory=directory,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS,
        is_index=False,
    )
    index = Dataset(
        ticker="SYNIDX",
        label="합성 지수",
        symbol="^SYNIDX",
        directory=directory,
        file_template=INDEX_FILE_TEMPLATE,
        price_column=COL_VALUE,
        price_decimals=PRICE_DECIMALS,
        is_index=True,
    )

    return run_study((etf, index), repeats=TEST_REPEATS).statistics


class TestDatasetsInvariant:
    """대상 정의의 불변조건 — 형제 두 매매법이 이미 거는 것"""

    def test_표시_이름이_겹치지_않는다(self) -> None:
        """
        목적: 종목명이 곧 데이터셋 구분자이므로 겹치면 행이 조용히 뒤섞인다

        Given: 선언된 대상 목록
        When: 표시 이름을 모았을 때
        Then: 중복이 없다
        """
        # Given / When
        labels = [dataset.label for dataset in DATASETS]

        # Then
        assert len(labels) == len(set(labels)), f"표시 이름이 겹칩니다: {labels}"

    def test_파일명에_쓰는_이름도_겹치지_않는다(self) -> None:
        """
        목적: 같은 파일을 두 대상이 가리키면 같은 값이 두 번 실린다

        Given: 선언된 대상 목록
        When: `ticker` 를 모았을 때
        Then: 중복이 없다
        """
        # Given / When
        tickers = [dataset.ticker for dataset in DATASETS]

        # Then
        assert len(tickers) == len(set(tickers)), f"파일명이 겹칩니다: {tickers}"

    def test_지수만_판정에서_빠진다(self) -> None:
        """
        목적: 살 수 없는 대상으로 판정하지 않음을 고정한다 (측정의 원칙 9)

        Given: 선언된 대상 목록
        When: `is_judged` 를 봤을 때
        Then: 지수만 거짓이다
        """
        # Given / When / Then
        assert all(dataset.is_judged != dataset.is_index for dataset in DATASETS)

    def test_모르는_이름을_고르면_예외다(self) -> None:
        """
        목적: 입력 검증을 고정한다

        Given: 없는 종목 이름
        When: 대상을 고르면
        Then: ValueError 가 난다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="모르는 종목"):
            datasets_of(("NOPE",))

    def test_빈_목록은_거부한다(self) -> None:
        """
        목적: 「전부」와 「고른 결과가 없다」를 가른다

        빈 튜플을 조용히 전부로 넓히면 좁히려던 실행이 전 범위 산출물로 폴더를 덮는다.

        Given: 빈 튜플
        When: 대상을 고르면
        Then: ValueError 가 난다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="고른 대상이 없습니다"):
            datasets_of(())

    def test_인자를_주지_않으면_전부다(self) -> None:
        """
        목적: 기본값이 전 범위임을 고정한다

        Given: 인자 없음
        When: 대상을 고르면
        Then: 선언된 목록 그대로다
        """
        # Given / When / Then
        assert datasets_of() == DATASETS


class TestStatisticsAssembly:
    """측정 표의 축과 판정"""

    def test_대상마다_사이클_네_칸이_나온다(self, outputs: pd.DataFrame) -> None:
        """
        목적: 축이 빠짐없이 나오는지 고정한다

        Given: 대상 둘로 돈 측정 표
        When: 행 수와 축 값을 봤을 때
        Then: 대상 2 × 사이클 위치 4 = 8행이고 순서가 `CYCLE_POSITIONS` 다
        """
        # Given / When / Then
        assert len(outputs) == 2 * len(CYCLE_POSITIONS)
        assert outputs[COL_CYCLE_POSITION].tolist()[: len(CYCLE_POSITIONS)] == list(CYCLE_POSITIONS)

    def test_방향은_위_하나다(self, outputs: pd.DataFrame) -> None:
        """
        목적: 측정 표와 성적표의 1:1 조인이 성립하려면 방향이 한 값이어야 한다

        Given: 측정 표
        When: 방향 컬럼을 봤을 때
        Then: 「위」 하나다
        """
        # Given / When / Then
        assert set(outputs[COL_DIRECTION]) == {DIRECTION_UP}

    def test_판정가능이_문자열이다(self, outputs: pd.DataFrame) -> None:
        """
        목적: 불린이 담기면 `screening` 이 「예」로 거르므로 전 칸이 조용히 제외된다

        Given: 측정 표
        When: 판정가능 값을 봤을 때
        Then: 「예」 또는 「아니오」다
        """
        # Given / When / Then
        assert set(outputs[COL_JUDGEABLE]) <= {"예", "아니오"}


class TestNonOverlapping:
    """비중첩 표본 — 롤링 기준선이 실제보다 단단해 보이는 것을 막는다"""

    def test_신호는_표본과_비중첩이_같다(self, outputs: pd.DataFrame) -> None:
        """
        목적: 4년 간격이라 보유 구간이 겹치지 않음을 고정한다 (측정의 원칙 5)

        Given: 측정 표
        When: 신호의 표본 수와 비중첩 수를 견줬을 때
        Then: 두 값이 같다
        """
        # Given / When / Then
        assert (outputs[COL_SAMPLE_COUNT] == outputs[COL_NON_OVERLAPPING]).all()

    def test_기준선은_비중첩이_표본보다_적다(self, outputs: pd.DataFrame) -> None:
        """
        목적: 롤링 기준선의 겹침이 실제로 드러나는지 고정한다

        기준선은 달마다 진입해 9개월을 들므로 이웃이 8/9 씩 겹친다.

        Given: 측정 표
        When: 기준선의 표본 수와 비중첩 수를 견줬을 때
        Then: 비중첩이 더 적다
        """
        # Given / When / Then
        assert (outputs[COL_BASELINE_NON_OVERLAPPING] < outputs[f"{COL_SAMPLE_COUNT}_baseline"]).all()


class TestDividendColumns:
    """배당락 — 「안 걸림」과 「못 쟀다」를 가른다"""

    def test_지수는_비우고_ETF_는_잰다(self, outputs: pd.DataFrame) -> None:
        """
        목적: 0 으로 채우면 두 사실이 같아진다 (측정의 원칙 14)

        지수는 상품이 아니라 계산값이라 분배금을 지급할 일이 없다.

        Given: ETF 와 지수로 돈 측정 표
        When: 배당락 대조 건수를 봤을 때
        Then: 지수 행은 비어 있고 ETF 행은 값이 있다
        """
        # Given
        index_rows = outputs[outputs["ticker"] == "합성 지수"]
        etf_rows = outputs[outputs["ticker"] == "합성 ETF"]

        # When / Then
        assert index_rows[COL_DIVIDEND_MEASURED].isna().all(), "지수 행의 배당락이 비어 있지 않습니다"
        assert etf_rows[COL_DIVIDEND_MEASURED].notna().all(), "ETF 행의 배당락을 재지 않았습니다"
        assert (etf_rows[COL_DIVIDEND_HIT_COUNT] <= etf_rows[COL_DIVIDEND_MEASURED]).all()

    def test_수정주가가_없으면_예외다(self, tmp_path: Path) -> None:
        """
        목적: 「못 쟀다」를 0 으로 흘려보내지 않음을 고정한다

        Given: 수정주가 파일이 없는 ETF 대상
        When: 측정을 돌리면
        Then: ValueError 가 난다
        """
        # Given
        _frame().to_csv(tmp_path / MARKET_FILE_TEMPLATE.format(ticker="SYN"), index=False)
        etf = Dataset(
            ticker="SYN",
            label="합성 ETF",
            symbol="SYN",
            directory=tmp_path,
            file_template=MARKET_FILE_TEMPLATE,
            price_column=COL_CLOSE,
            price_decimals=PRICE_DECIMALS,
            is_index=False,
        )

        # When / Then
        with pytest.raises(ValueError, match="수정주가 파일이 필요합니다"):
            run_study((etf,), repeats=TEST_REPEATS)


class TestRunStudyGuards:
    """입력 검증"""

    def test_대상이_비면_예외다(self) -> None:
        """
        목적: 조용히 빈 산출물을 내지 않음을 고정한다

        Given: 빈 대상 목록
        When: 측정을 돌리면
        Then: ValueError 가 난다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="검증 대상이 하나도 없습니다"):
            run_study(())
