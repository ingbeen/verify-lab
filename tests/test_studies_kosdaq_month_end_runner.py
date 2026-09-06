"""검증 #10 실행 계층의 집계 축과 출력 계약을 고정한다.

**조합 순회와 조립이 스크립트가 아니라 `runner` 에 있는 이유**가 이 파일이다 —
테스트가 붙는 자리에 두지 않으면 가장 조용히 틀릴 수 있는 코드가 검사 밖에 남는다.

고정하는 계약은 다섯이다.

- 격자 칸 수는 진입 달력일 × 청산 상대 거래일이다
- 월별 분해와 원자료는 **원 매매법 칸에서만** 나온다 (축을 동시에 쪼개지 않는다)
- 후보 판정의 시기 항목은 **균등 분할만** 읽는다 (관찰용 최근 구간은 판정에 쓰지 않는다)
- 저장 표의 헤더가 전부 한글이다 (영문 토큰이 사용자에게 나가지 않는다)
- 지수와 ETF 는 스키마가 달라도 같은 격자를 낸다
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
from verify_lab.studies.kosdaq_month_end.constants import (
    BASE_ENTRY_DAY,
    BASE_EXIT_OFFSET,
    COL_GRID_CELL,
    COL_TARGET_DAY,
    DISPLAY_PERIOD_EARLY,
    DISPLAY_PERIOD_LATE,
    DISPLAY_PERIOD_RECENT,
    ENTRY_CALENDAR_DAYS,
    EXIT_OFFSETS,
    RECENT_WINDOWS_YEARS,
    Dataset,
)
from verify_lab.studies.kosdaq_month_end.constants import COL_EXIT_OFFSET as COL_OFFSET
from verify_lab.studies.kosdaq_month_end.runner import (
    StudyOutputs,
    display_tables,
    grid_cell_label,
    run_study,
)

# 순열 검정 반복 수. 계약만 보는 테스트라 크게 돌릴 이유가 없다
FAST_REPEATS = 20
FIXED_SEED = 0

# 합성 시세의 구간. 월별 분해가 12칸을 채우려면 몇 해가 필요하다
SYNTHETIC_START = "2016-01-01"
SYNTHETIC_END = "2021-12-31"


def _write_market(directory: Path, ticker: str) -> Dataset:
    """ETF 시세 파일을 만들고 그 대상 정의를 돌려준다.

    Args:
        directory: 파일을 쓸 폴더
        ticker: 종목 코드

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
    )


def _write_index(directory: Path, ticker: str) -> Dataset:
    """지수 계열 파일을 만들고 그 대상 정의를 돌려준다.

    **시가·고가·저가가 없다.** 실제 코스닥150 지수가 그렇고, 그래서 종가 계열로 저장한다.

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
    )


@pytest.fixture(scope="module")
def etf_dataset(tmp_path_factory: pytest.TempPathFactory) -> Dataset:
    """합성 ETF 대상 (파일은 임시 폴더에 격리된다).

    **모듈 스코프인 이유**: 격자 77칸 × 순열 검정이라 한 번 도는 데 수십 초가 걸린다.
    테스트마다 새로 돌리면 이 파일 하나가 몇 분을 먹는다. 입력이 불변이라 공유해도 안전하다.
    """
    return _write_market(tmp_path_factory.mktemp("market"), "999900")


@pytest.fixture(scope="module")
def index_dataset(tmp_path_factory: pytest.TempPathFactory) -> Dataset:
    """합성 지수 대상 (파일은 임시 폴더에 격리된다)."""
    return _write_index(tmp_path_factory.mktemp("series"), "9999")


@pytest.fixture(scope="module")
def etf_outputs(etf_dataset: Dataset) -> StudyOutputs:
    """합성 ETF 하나를 돌린 산출물. **한 번만 실행한다.**"""
    return run_study((etf_dataset,), repeats=FAST_REPEATS, seed=FIXED_SEED)


class TestGridAxis:
    """격자 축 — 진입 달력일 × 청산 상대 거래일"""

    def test_grid_has_one_row_per_cell(self, etf_outputs: StudyOutputs) -> None:
        """
        목적: 격자 칸 수가 두 축의 곱임을 고정한다.

        칸이 조용히 줄면 「그 칸을 못 봤다」는 사실 자체가 산출물에서 사라진다.

        Given: 합성 ETF 하나
        When: 검증을 돌린다
        Then: 격자 행 수가 진입 달력일 수 × 청산 상대 거래일 수다
        """
        # Given / When
        outputs = etf_outputs

        # Then
        assert len(outputs.grid) == len(ENTRY_CALENDAR_DAYS) * len(EXIT_OFFSETS)

    def test_grid_cell_label_marks_the_month_end(self) -> None:
        """
        목적: 청산 0 이 「말일」로 적힘을 고정한다.

        원 매매법이 격자 안에서 눈에 띄어야 사용자가 그 칸을 찾을 수 있다.

        Given: 원 매매법의 두 축 값
        When: 칸 이름을 만든다
        Then: 「말일」이 들어가고 상대 거래일 숫자가 나오지 않는다
        """
        # Given / When
        label = grid_cell_label(BASE_ENTRY_DAY, BASE_EXIT_OFFSET)

        # Then
        assert label == "20일 → 말일"
        assert grid_cell_label(20, -1) == "20일 → 말일-1"

    def test_index_and_etf_produce_the_same_grid_shape(self, etf_dataset: Dataset, index_dataset: Dataset) -> None:
        """
        목적: 스키마가 달라도 같은 격자를 냄을 고정한다.

        지수는 종가 계열이라 시가가 없다. 대상마다 칸 구성이 갈리면 두 결과를 나란히 읽을 수 없다.

        Given: 합성 ETF 와 합성 지수
        When: 함께 돌린다
        Then: 두 대상의 격자 칸 이름 집합이 같다
        """
        # Given / When
        outputs = run_study((etf_dataset, index_dataset), repeats=FAST_REPEATS, seed=FIXED_SEED)

        # Then
        cells = outputs.grid.groupby("ticker")[COL_GRID_CELL].apply(set)
        assert cells.iloc[0] == cells.iloc[1]


class TestAxisSeparation:
    """축을 동시에 쪼개지 않는다"""

    def test_month_split_covers_only_the_base_cell(self, etf_outputs: StudyOutputs) -> None:
        """
        목적: 월별 분해가 **원 매매법 칸에서만** 나옴을 고정한다.

        격자 전체를 월별로 쪼개면 924칸이 되어 다중 비교가 폭발하고 칸당 표본이 무너진다.

        Given: 합성 ETF 하나
        When: 검증을 돌린다
        Then: 월별 표가 12칸을 넘지 않는다 (격자 칸 수만큼 불어나지 않는다)
        """
        # Given / When
        outputs = etf_outputs

        # Then
        assert len(outputs.months) <= 12

    def test_raw_trades_cover_only_the_base_cell(self, etf_outputs: StudyOutputs) -> None:
        """
        목적: 원자료가 원 매매법 칸의 것임을 고정한다.

        Given: 합성 ETF 하나
        When: 검증을 돌린다
        Then: 원자료의 진입 달력일이 20일 하나뿐이다
        """
        # Given / When
        outputs = etf_outputs

        # Then
        assert set(outputs.trades[COL_TARGET_DAY]) == {BASE_ENTRY_DAY}

    def test_periods_cover_every_grid_cell(self, etf_outputs: StudyOutputs) -> None:
        """
        목적: 시기 분해는 격자 전체에 걸림을 고정한다.

        Given: 합성 ETF 하나
        When: 검증을 돌린다
        Then: 시기 표의 격자 칸 수가 격자 표와 같다
        """
        # Given / When
        outputs = etf_outputs

        # Then
        assert set(outputs.periods[COL_GRID_CELL]) == set(outputs.grid[COL_GRID_CELL])


class TestPeriodSplit:
    """시기 분해 — 판정용과 관찰용의 구분"""

    def test_all_four_periods_are_kept_in_the_output(self, etf_outputs: StudyOutputs) -> None:
        """
        목적: 산출물에 네 구간이 모두 남음을 고정한다 (측정의 원칙 17).

        관찰용을 판정에서 빼는 것과 산출물에서 지우는 것은 다르다.

        Given: 합성 ETF 하나
        When: 검증을 돌린다
        Then: 균등 2분할과 최근 10년·5년이 모두 있다
        """
        # Given / When
        outputs = etf_outputs

        # Then
        expected = {DISPLAY_PERIOD_EARLY, DISPLAY_PERIOD_LATE} | {
            DISPLAY_PERIOD_RECENT.format(years=years) for years in RECENT_WINDOWS_YEARS
        }
        assert set(outputs.periods["period"]) == expected

    def test_recent_windows_do_not_enter_the_screening(self, etf_outputs: StudyOutputs) -> None:
        """
        목적: **관찰용 최근 구간이 후보 판정의 시기 항목에 들어가지 않음**을 고정한다.

        최근 구간으로 판정하면 결과를 보고 구간을 고르는 것과 구별되지 않는다.
        판정에 쓰인 구간 수는 균등 분할 중 표본 하한을 넘은 것뿐이므로 **2를 넘을 수 없다.**

        Given: 합성 ETF 하나
        When: 검증을 돌린다
        Then: 판정표의 시기 구간 수가 2 이하다
        """
        # Given / When
        outputs = etf_outputs

        # Then
        assert outputs.grid_candidates["PeriodCount"].max() <= len({DISPLAY_PERIOD_EARLY, DISPLAY_PERIOD_LATE})


class TestDisplayTables:
    """저장 표의 헤더는 전부 한글이다"""

    def test_every_saved_table_has_korean_headers(self, etf_outputs: StudyOutputs) -> None:
        """
        목적: 영문 토큰이 사용자에게 나가지 않음을 고정한다.

        검증 #7 이 `COL_* → DISPLAY_*` 연결을 빠뜨려 `ticker,price_basis,SignalCount,…` 로
        나간 적이 있다. 사용자가 직접 여는 파일이라 무슨 값인지 알 수 없게 된다.

        Given: 합성 ETF 하나
        When: 표시용 표를 만든다
        Then: 어떤 표에도 ASCII 로만 된 헤더가 없다
        """
        # Given
        outputs = etf_outputs

        # When
        tables = display_tables(outputs)

        # Then
        assert tables, "저장할 표가 하나도 없습니다"
        for name, table in tables.items():
            ascii_only = [column for column in table.columns if column.isascii()]
            assert not ascii_only, f"{name} 에 영문 헤더가 남았습니다: {ascii_only}"

    def test_grid_keeps_both_axes_as_columns(self, etf_outputs: StudyOutputs) -> None:
        """
        목적: 격자의 두 축이 컬럼으로 남음을 고정한다.

        칸 이름만 남기면 사용자가 진입일이나 청산일로 정렬·필터할 수 없다.

        Given: 합성 ETF 하나
        When: 검증을 돌린다
        Then: 진입 달력일과 청산 상대 거래일이 격자 표에 있다
        """
        # Given / When
        outputs = etf_outputs

        # Then
        assert {COL_TARGET_DAY, COL_OFFSET} <= set(outputs.grid.columns)


class TestDatasetIdentity:
    """산출물의 대상 식별자 — 종목명이 구분자다"""

    def test_labels_are_unique_across_datasets(self) -> None:
        """
        목적: `DATASETS` 의 **종목명이 겹치지 않음**을 고정한다.

        산출물의 대상 컬럼에 종목명이 들어가므로 **종목명이 곧 데이터셋 구분자**다.
        겹치면 서로 다른 대상의 행이 조용히 뒤섞이는데 예외가 나지 않는다 —
        `ticker` 가 구분자였을 때 중복을 막았던 것과 같은 이유다
        (`src/verify_lab/CLAUDE.md` 실행 계층 계약).

        Given: 기본 대상 목록
        When: 종목명을 모은다
        Then: 대상 수와 종목명의 가짓수가 같다
        """
        # Given
        from verify_lab.studies.kosdaq_month_end.constants import DATASETS

        # When
        labels = [dataset.label for dataset in DATASETS]

        # Then
        assert len(set(labels)) == len(DATASETS), f"종목명이 겹칩니다: {labels}"

    def test_tickers_are_unique_across_datasets(self) -> None:
        """
        목적: 종목코드도 여전히 겹치지 않음을 고정한다.

        **코드는 산출물에서 빠졌지만 `summary.json` 의 데이터셋 목록에 남는다.**
        거기서 종목명과 코드를 잇는 유일한 자리이므로 여기서도 겹치면 안 된다.

        Given: 기본 대상 목록
        When: 종목코드를 모은다
        Then: 대상 수와 코드의 가짓수가 같다
        """
        # Given
        from verify_lab.studies.kosdaq_month_end.constants import DATASETS

        # When
        tickers = [dataset.ticker for dataset in DATASETS]

        # Then
        assert len(set(tickers)) == len(DATASETS), f"종목코드가 겹칩니다: {tickers}"

    def test_saved_tables_carry_the_label_not_the_code(self, etf_outputs: StudyOutputs) -> None:
        """
        목적: 저장 표의 대상 컬럼이 **종목명**임을 고정한다 (숫자 코드가 아니다).

        사용자가 CSV 를 열었을 때 `229200` 만 보면 무엇을 잰 것인지 알 수 없다.
        **숫자만으로 된 값이 하나도 없어야** 코드가 새어 나가지 않은 것이다.

        Given: 합성 ETF 하나를 돌린 산출물
        When: 저장 표들의 대상 컬럼 값을 모은다
        Then: 숫자만으로 이루어진 값이 없다
        """
        # Given
        from verify_lab.studies.kosdaq_month_end.constants import DISPLAY_TICKER

        tables = display_tables(etf_outputs)

        # When
        checked = 0
        for name, table in tables.items():
            if DISPLAY_TICKER not in table.columns:
                continue
            values = set(table[DISPLAY_TICKER].astype(str))

            # Then
            numeric = {value for value in values if value.isdigit()}
            assert not numeric, f"{name} 표의 대상 컬럼에 종목코드가 남아 있습니다: {sorted(numeric)}"
            checked += 1

        assert checked >= 1, "대상 컬럼을 가진 표를 하나도 찾지 못했습니다"


def test_empty_dataset_list_raises() -> None:
    """
    목적: 대상이 없으면 조용히 빈 결과를 내지 않고 실패함을 고정한다.

    Given: 빈 대상 목록
    When: 검증을 돌린다
    Then: ValueError 가 난다
    """
    # Given / When / Then
    with pytest.raises(ValueError, match="대상"):
        run_study((), repeats=FAST_REPEATS, seed=FIXED_SEED)
