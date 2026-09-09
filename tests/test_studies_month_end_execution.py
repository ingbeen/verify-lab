"""집행 축의 계약을 고정한다 — 「어느 상품으로 그 방향을 거는가」

「아래」 방향은 1배 ETF 의 하락률이 아니라 **인버스 ETF 의 실물 가격**으로 재야 한다.
1배로 재면 분배락 하락이 이익으로 잡히는데 인버스는 그만큼 오르지 않기 때문이다
(코스닥 4월 실측 +0.65%p). 인버스 종가에는 분배락·총보수·일일 리밸런싱 손실이
**이미 들어 있어** 따로 뺄 것이 없다.

고정하는 계약은 다섯이다.

- 대상마다 집행 역할이 **정확히 하나**이고, 지수는 전부 「불가」다
- 집행 축 표에 **지수가 들어가지 않는다** — 살 수 없는 것을 실제 매매 수치로 내보내지 않는다
- 집행 축 표는 **위·아래 두 방향을 모두** 낸다. 방향을 고르지 않는다 (측정의 원칙 11)
- 집행 축 표의 값은 월별 표에서 **골라낸 것**이지 다시 계산한 값이 아니다
- 시장별 목록의 합이 전체 목록이고, 티커와 레이블이 겹치지 않는다
"""

from pathlib import Path

import pandas as pd
import pytest

from verify_lab.common_constants import (
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
    PRICE_DECIMALS_KRW,
)
from verify_lab.studies.month_end.constants import (
    COL_MONTH_NUMBER,
    COL_TICKER,
    DATASETS,
    DATASETS_KOSDAQ,
    DATASETS_KOSPI,
    EXECUTION_ROLE_DOWN,
    EXECUTION_ROLE_NONE,
    EXECUTION_ROLE_UP,
    EXECUTION_ROLES,
    Dataset,
)
from verify_lab.studies.month_end.runner import StudyOutputs, run_study

# 순열 검정 반복 수. 계약만 보는 테스트라 크게 돌릴 이유가 없다
FAST_REPEATS = 20
FIXED_SEED = 0

# 합성 시세의 구간. 월별 분해가 12칸을 채우려면 몇 해가 필요하다
SYNTHETIC_START = "2016-01-01"
SYNTHETIC_END = "2021-12-31"


def _write_market(directory: Path, ticker: str, role: str) -> Dataset:
    """ETF 시세 파일을 만들고 그 대상 정의를 돌려준다.

    Args:
        directory: 파일을 쓸 폴더
        ticker: 종목 코드
        role: 집행 역할

    Returns:
        시세 스키마 대상 정의
    """
    days = pd.bdate_range(SYNTHETIC_START, SYNTHETIC_END)
    prices = [10_000 + (index % 37) * 13 for index in range(len(days))]

    pd.DataFrame(
        {
            COL_DATE: days.date,
            COL_OPEN: prices,
            COL_HIGH: prices,
            COL_LOW: prices,
            COL_CLOSE: prices,
            COL_VOLUME: [1_000] * len(days),
        }
    ).to_csv(directory / MARKET_FILE_TEMPLATE.format(ticker=ticker), index=False)

    return Dataset(
        ticker=ticker,
        label=f"합성 ETF {ticker}",
        directory=directory,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS_KRW,
        is_index=False,
        execution_role=role,
    )


def _write_index(directory: Path, ticker: str) -> Dataset:
    """지수 계열 파일을 만들고 그 대상 정의를 돌려준다.

    Args:
        directory: 파일을 쓸 폴더
        ticker: 지수 코드

    Returns:
        단일 값 계열 대상 정의
    """
    days = pd.bdate_range(SYNTHETIC_START, SYNTHETIC_END)
    values = [700.0 + (index % 41) * 1.37 for index in range(len(days))]

    pd.DataFrame({COL_DATE: days.date, COL_VALUE: values}).to_csv(
        directory / INDEX_FILE_TEMPLATE.format(ticker=ticker), index=False
    )

    return Dataset(
        ticker=ticker,
        label=f"합성 지수 {ticker}",
        directory=directory,
        file_template=INDEX_FILE_TEMPLATE,
        price_column=COL_VALUE,
        price_decimals=PRICE_DECIMALS,
        is_index=True,
        execution_role=EXECUTION_ROLE_NONE,
    )


@pytest.fixture(scope="module")
def mixed_outputs(tmp_path_factory: pytest.TempPathFactory) -> StudyOutputs:
    """1배 ETF · 인버스 ETF · 지수를 한 번에 돌린 산출물. **한 번만 실행한다.**"""
    market = tmp_path_factory.mktemp("market")
    series = tmp_path_factory.mktemp("series")

    datasets = (
        _write_market(market, "999900", EXECUTION_ROLE_UP),
        _write_market(market, "999901", EXECUTION_ROLE_DOWN),
        _write_index(series, "9999"),
    )

    return run_study(datasets, repeats=FAST_REPEATS, seed=FIXED_SEED)


class TestExecutionRole:
    """대상마다 집행 역할이 하나로 정해져 있다"""

    def test_every_dataset_declares_a_known_role(self) -> None:
        """
        목적: 집행 역할이 정해진 세 값 중 하나임을 고정한다

        Given: 실제 검증 대상 목록
        When: 각 대상의 집행 역할을 읽는다
        Then: 전부 `EXECUTION_ROLES` 안의 값이다
        """
        # Given / When
        roles = {dataset.ticker: dataset.execution_role for dataset in DATASETS}

        # Then
        unknown = {ticker: role for ticker, role in roles.items() if role not in EXECUTION_ROLES}
        assert not unknown, f"집행 역할이 정의되지 않은 대상이 있습니다: {unknown}"

    def test_index_datasets_are_never_executable(self) -> None:
        """
        목적: 지수는 살 수 없으므로 집행 역할이 반드시 「불가」임을 고정한다

        Given: 실제 검증 대상 목록
        When: 지수 대상만 고른다
        Then: 전부 `EXECUTION_ROLE_NONE` 이다
        """
        # Given / When
        indices = [dataset for dataset in DATASETS if dataset.is_index]

        # Then
        assert indices, "지수 대상이 하나도 없습니다"
        wrong = [dataset.ticker for dataset in indices if dataset.execution_role != EXECUTION_ROLE_NONE]
        assert not wrong, f"지수인데 집행 가능으로 표시된 대상이 있습니다: {wrong}"

    def test_each_market_has_one_product_per_direction(self) -> None:
        """
        목적: 시장마다 「위」와 「아래」를 집행할 상품이 정확히 하나씩 있음을 고정한다

        Given: 시장별 대상 목록
        When: 집행 역할별로 센다
        Then: 시장마다 「위 집행」 1개 · 「아래 집행」 1개다
        """
        # Given
        for market_name, datasets in (("코스피", DATASETS_KOSPI), ("코스닥", DATASETS_KOSDAQ)):
            # When
            up = [dataset for dataset in datasets if dataset.execution_role == EXECUTION_ROLE_UP]
            down = [dataset for dataset in datasets if dataset.execution_role == EXECUTION_ROLE_DOWN]

            # Then
            assert len(up) == 1, f"{market_name} 의 「위」 집행 상품이 하나가 아닙니다: {[d.ticker for d in up]}"
            assert len(down) == 1, f"{market_name} 의 「아래」 집행 상품이 하나가 아닙니다: {[d.ticker for d in down]}"


class TestDatasetComposition:
    """시장별 목록과 전체 목록의 관계"""

    def test_all_datasets_are_the_sum_of_two_markets(self) -> None:
        """
        목적: 전체 목록이 시장별 목록의 합임을 고정한다 — 어느 한쪽에만 있는 대상이 없다

        Given: 시장별 목록과 전체 목록
        When: 티커 집합을 비교한다
        Then: 합집합이 전체와 같고 개수도 같다
        """
        # Given
        kospi = {dataset.ticker for dataset in DATASETS_KOSPI}
        kosdaq = {dataset.ticker for dataset in DATASETS_KOSDAQ}

        # When
        combined = kospi | kosdaq
        every = {dataset.ticker for dataset in DATASETS}

        # Then
        assert combined == every, f"시장별 목록의 합이 전체와 다릅니다: {combined ^ every}"
        assert len(DATASETS) == len(DATASETS_KOSPI) + len(DATASETS_KOSDAQ), "두 시장에 겹치는 대상이 있습니다"

    def test_tickers_and_labels_are_unique(self) -> None:
        """
        목적: 산출물의 데이터셋 구분자가 겹치지 않음을 고정한다

        Given: 전체 대상 목록
        When: 티커와 레이블을 각각 센다
        Then: 둘 다 중복이 없다
        """
        # Given / When
        tickers = [dataset.ticker for dataset in DATASETS]
        labels = [dataset.label for dataset in DATASETS]

        # Then
        assert len(set(tickers)) == len(tickers), f"티커가 겹칩니다: {tickers}"
        assert len(set(labels)) == len(labels), f"종목명이 겹칩니다: {labels}"


class TestExecutionTable:
    """집행 축 표가 담는 것과 담지 않는 것"""

    def test_execution_excludes_index_datasets(self, mixed_outputs: StudyOutputs) -> None:
        """
        목적: 살 수 없는 지수가 「실제 매매 수치」 표에 섞이지 않음을 고정한다

        Given: 1배·인버스·지수를 함께 돌린 산출물
        When: 집행 축 표의 종목을 읽는다
        Then: 지수 레이블이 하나도 없다
        """
        # Given / When
        labels = set(mixed_outputs.execution[COL_TICKER])

        # Then
        assert "합성 지수 9999" not in labels, "집행 축 표에 지수가 들어갔습니다"
        assert labels, "집행 축 표가 비어 있습니다"

    def test_execution_keeps_every_executable_product(self, mixed_outputs: StudyOutputs) -> None:
        """
        목적: 집행 가능한 상품이 빠짐없이 실림을 고정한다 — 방향을 고르지 않는다 (측정의 원칙 11)

        Given: 1배·인버스·지수를 함께 돌린 산출물
        When: 집행 축 표의 종목을 읽는다
        Then: 「위 집행」과 「아래 집행」 상품이 둘 다 있다
        """
        # Given / When
        labels = set(mixed_outputs.execution[COL_TICKER])

        # Then
        assert "합성 ETF 999900" in labels, "「위 집행」 상품이 빠졌습니다"
        assert "합성 ETF 999901" in labels, "「아래 집행」 상품이 빠졌습니다"

    def test_execution_rows_are_selected_from_month_candidates(self, mixed_outputs: StudyOutputs) -> None:
        """
        목적: 집행 축 표가 월별 판정표에서 **골라낸 행**이지 다시 계산한 값이 아님을 고정한다

        Given: 월별 판정표와 집행 축 표
        When: 집행 축의 각 행을 (종목, 월) 로 월별 판정표와 맞춘다
        Then: 공통 컬럼의 값이 전부 같다
        """
        # Given
        candidates = mixed_outputs.month_candidates
        execution = mixed_outputs.execution
        keys = [COL_TICKER, COL_MONTH_NUMBER]
        shared = [column for column in execution.columns if column in candidates.columns and column not in keys]

        # When
        merged = execution.merge(candidates, on=keys, how="left", suffixes=("_execution", "_source"))

        # Then
        assert not merged.empty, "집행 축 표가 월별 판정표와 이어지지 않습니다"
        assert shared, "두 표에 공통 컬럼이 없습니다 — 골라낸 표가 아닙니다"
        for column in shared:
            left = merged[f"{column}_execution"]
            right = merged[f"{column}_source"]
            assert left.equals(right), f"집행 축 표의 `{column}` 이 원본과 다릅니다 — 다시 계산했습니다"
