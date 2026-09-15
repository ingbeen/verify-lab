"""검증 #10 실행 계층의 집계 축과 출력 계약을 고정한다.

**조합 순회와 조립이 스크립트가 아니라 `runner` 에 있는 이유**가 이 파일이다 —
테스트가 붙는 자리에 두지 않으면 가장 조용히 틀릴 수 있는 코드가 검사 밖에 남는다.

고정하는 계약은 다섯이다.

- 격자 칸 수는 진입 달력일 × 청산 상대 거래일이다
- 월별 분해와 원자료는 **원 매매법 칸에서만** 나온다 (축을 동시에 쪼개지 않는다)
- 후보 판정은 **전체 구간 하나만** 본다 (구간은 산출물에 관찰용으로만 남는다)
- 저장 표의 헤더가 전부 한글이다 (영문 토큰이 사용자에게 나가지 않는다)
- 지수와 ETF 는 스키마가 달라도 같은 격자를 낸다
"""

from collections.abc import Callable
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
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_EXCLUDED_REASON,
    COL_FORWARD_RETURN,
    COL_HORIZON,
    COL_JUDGEABLE,
    JUDGEABLE_NO,
    PERIOD_FIRST_HALF,
    PERIOD_SECOND_HALF,
)
from verify_lab.measure.forward_return import ReturnBasis
from verify_lab.measure.screening import SCREENING_COLUMNS
from verify_lab.measure.statistics import COL_MEAN, COL_SAMPLE_COUNT
from verify_lab.studies.month_end import runner as month_end_runner
from verify_lab.studies.month_end.constants import (
    BASE_ENTRY_DAY,
    BASE_EXIT_OFFSET,
    COL_GRID_CELL,
    COL_TARGET_DAY,
    DISPLAY_PERIOD_RECENT,
    ENTRY_CALENDAR_DAYS,
    EXECUTION_ROLE_NONE,
    EXECUTION_ROLE_UP,
    EXIT_OFFSETS,
    MARKET_KOSDAQ,
    RECENT_WINDOWS_YEARS,
    Dataset,
)
from verify_lab.studies.month_end.constants import COL_EXIT_OFFSET as COL_OFFSET
from verify_lab.studies.month_end.runner import (
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
        market=MARKET_KOSDAQ,
        directory=directory,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS_KRW,
        is_index=False,
        execution_role=EXECUTION_ROLE_UP,
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
        market=MARKET_KOSDAQ,
        directory=directory,
        file_template=INDEX_FILE_TEMPLATE,
        price_column=COL_VALUE,
        price_decimals=PRICE_DECIMALS,
        is_index=True,
        execution_role=EXECUTION_ROLE_NONE,
    )


def _long_form(dates: pd.DatetimeIndex) -> pd.DataFrame:
    """`measure` 계약의 long-form 한 칸(기준 × 구간)을 만든다.

    **여집합이 아닌 값을 여집합으로 만들지 않는다** (`tests/CLAUDE.md`) — 수익률에
    0 을 섞지 않아 오른 비율과 내린 비율의 합이 1 이 되는 착시를 만들지 않는다.

    Args:
        dates: 신호일

    Returns:
        `Date`·`Basis`·`Horizon`·`ForwardReturn`·`ExcludedReason` 다섯 컬럼
    """
    count = len(dates)

    return pd.DataFrame(
        {
            COL_DATE: dates,
            COL_BASIS: [ReturnBasis.CLOSE.value] * count,
            COL_HORIZON: [5] * count,
            COL_FORWARD_RETURN: [0.01 if order % 3 else -0.007 for order in range(count)],
            COL_EXCLUDED_REASON: [""] * count,
        }
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
        expected = {PERIOD_FIRST_HALF, PERIOD_SECOND_HALF} | {
            DISPLAY_PERIOD_RECENT.format(years=years) for years in RECENT_WINDOWS_YEARS
        }
        assert set(outputs.periods["period"]) == expected

    def test_no_period_enters_the_screening(self, etf_outputs: StudyOutputs) -> None:
        """
        목적: **어떤 구간도 판정에 들어가지 않음**을 고정한다 (2026-09-12 개편).

        게이트는 전체 구간 하나만 본다. 쪼개면 칸당 표본이 5~6건까지 줄어 한 건이 20%p 를
        움직이므로, 그 값으로 칸을 떨어뜨리면 멀쩡한 매매법이 우연으로 죽는다.
        **구간은 산출물에 관찰용으로만 남고**(위 테스트), 판정표에는 흔적이 없어야 한다.

        Given: 합성 ETF 하나
        When: 검증을 돌린다
        Then: 판정표 컬럼이 `SCREENING_COLUMNS` 계약 그대로이고 시기 관련 열이 없다
        """
        # Given / When
        outputs = etf_outputs

        # Then
        assert set(SCREENING_COLUMNS) <= set(outputs.grid_candidates.columns)
        leftovers = [column for column in outputs.grid_candidates.columns if "Period" in column]
        assert leftovers == []

    def test_표본이_0건인_구간도_전체_스키마를_갖는다(self) -> None:
        """
        목적: 빈 구간 행의 **모양**을 옵션 만기일과 맞춘 것을 고정한다 (측정의 원칙 17).

        전에는 이 검증만 빈 구간에 **두 컬럼짜리 표**(`표본`·`판정가능`)를 붙였고, 옵션
        만기일은 전체 스키마를 유지했다. 값은 `pd.concat` 이 결측으로 채워 같아 보이지만,
        **그 두 컬럼짜리 표가 맨 앞에 오면 산출물의 컬럼 순서가 거기서부터 시작한다** —
        같은 원칙이 검증마다 다른 산출물을 내는 상태였다.

        **[중요] 이 경로는 실제 데이터로 재현되지 않는다.** 월말 신호는 매달 나오므로
        「최근 N년」이 비는 일이 없고, 그래서 두 구현이 갈라진 채로 아무도 밟지 않았다.
        그러니 `_split_by_period` 를 직접 불러 **결정적으로** 그 경로를 태운다 —
        「최근 N년」의 기준일이 인자라, 신호보다 한참 뒤를 주면 두 관찰 구간이 비워진다.

        Given: 2016년 신호와 **2030년을 마지막 거래일로 준** 입력
        When: 시기 분해를 돌린다
        Then: 최근 10년·5년 행이 남고, 다른 행과 **같은 컬럼**을 가지며 지표가 비어 있다
        """
        # Given
        signal = _long_form(pd.bdate_range("2016-01-04", periods=30))
        last_date = pd.Timestamp("2030-12-31")

        # When
        periods = month_end_runner._split_by_period(signal, signal, last_date, repeats=FAST_REPEATS, seed=FIXED_SEED)

        # Then
        blank = periods[periods[COL_SAMPLE_COUNT] == 0]
        assert len(blank) == len(RECENT_WINDOWS_YEARS), "표본 0건 구간이 사라졌습니다"
        assert (blank[COL_JUDGEABLE] == JUDGEABLE_NO).all()
        assert blank[COL_MEAN].isna().all(), "잰 적이 없는 칸은 0 이 아니라 빈칸이어야 합니다"

    def test_빈_구간_행이_이웃의_컬럼을_그대로_갖는다(self) -> None:
        """
        목적: 빈 행이 **전체 스키마**를 갖는 것을 고정한다 (측정의 원칙 17).

        [중요] **합쳐진 표에서 보면 이 계약을 검사할 수 없다.** `pd.concat` 이 없는 컬럼을
        결측으로 채우므로 「빈 행의 컬럼 == 표의 컬럼」은 **무엇을 만들었든 참**이다 —
        두 컬럼짜리 표를 붙여도 통과한다. 그래서 **행을 만드는 함수를 직접** 본다.

        차이가 산출물에 드러나는 경우는 **빈 블록이 맨 앞에 올 때**뿐이다. 그때 두 컬럼짜리
        표가 `concat` 의 컬럼 순서를 정해 산출물이 `표본`·`판정가능` 부터 시작한다.

        Given: 정상 집계 한 장 (컬럼 구성을 빌려줄 이웃)
        When: 빈 구간 행을 만든다
        Then: 이웃과 **컬럼이 같고 순서까지 같다**
        """
        # Given
        signal = _long_form(pd.bdate_range("2016-01-04", periods=30))
        template = month_end_runner._aggregate(signal, signal, repeats=FAST_REPEATS, seed=FIXED_SEED)
        assert not template.empty, "이웃으로 쓸 집계를 만들지 못했습니다"

        # When
        blank = month_end_runner._blank_period_row(template)

        # Then
        assert list(blank.columns) == list(template.columns), "빈 행이 이웃과 다른 컬럼을 갖습니다"
        assert len(blank) == 1
        assert blank[COL_SAMPLE_COUNT].tolist() == [0]
        assert blank[COL_JUDGEABLE].tolist() == [JUDGEABLE_NO]
        assert blank[COL_MEAN].isna().all(), "잰 적이 없는 칸은 0 이 아니라 빈칸이어야 합니다"


class TestBaseCellRecord:
    """기준 칸이 요약에 진입·제외 건수를 남기는지 — 표본 보존의 마지막 자리

    월별 분해와 원자료는 **원 매매법 칸(20일 → 말일)에서만** 낸다. 그 칸에 도달하지 못하면
    요약의 `진입`·`제외`·`보유일`·`기준선 진입`·`수렴한 달` 다섯이 통째로 빠지는데,
    **`summary.json` 은 나머지 키가 멀쩡해 정상으로 보인다.**

    현재 데이터에서는 도달할 수 없다 — 격자가 기준 칸을 포함하고 그 칸에 신호가 있다.
    **그래서 격자를 기준 칸이 없는 것으로 갈아끼운다** (전역 `python.md` — 불가능 조건은
    `RuntimeError` 로 즉시 인지시킨다).
    """

    def test_base_cell_missing_from_the_grid_raises(
        self, etf_dataset: Dataset, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        목적: 기준 칸에 한 번도 닿지 못한 실행이 **조용히 요약을 내지 않는지** 고정한다.

        Given: 기준 칸(20일 → 말일)을 포함하지 않는 격자
        When: 검증을 돌린다
        Then: RuntimeError 이고 메시지에 「내부 불변조건 위반」과 기준 칸이 담긴다
        """
        # Given
        assert BASE_ENTRY_DAY not in (15,), "기준 칸이 축소한 격자에 들어가면 이 테스트가 무의미해진다"
        monkeypatch.setattr(month_end_runner, "ENTRY_CALENDAR_DAYS", (15,))
        monkeypatch.setattr(month_end_runner, "EXIT_OFFSETS", (BASE_EXIT_OFFSET,))

        # When / Then
        with pytest.raises(RuntimeError, match="내부 불변조건 위반") as caught:
            run_study((etf_dataset,), repeats=FAST_REPEATS, seed=FIXED_SEED)

        assert grid_cell_label(BASE_ENTRY_DAY, BASE_EXIT_OFFSET) in str(caught.value)

    def test_base_cell_with_no_valid_signal_raises(self, etf_dataset: Dataset, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        목적: **실제로 일어날 수 있는 쪽**을 고정한다 — 기준 칸의 유효 신호가 0건인 경우.

        그때 격자 순회는 그 칸에 «닿지만» 집계가 비어 `continue` 하므로 `base_record` 가
        빈 채로 남는다. 앞 테스트(격자에 기준 칸이 없는 경우)와 도달 경로가 다르므로
        둘을 함께 건다 — 한쪽만 걸면 `block.empty` 처리를 바꿨을 때 조용히 통과한다.

        Given: 어느 칸에서도 집계가 나오지 않는 실행
        When: 검증을 돌린다
        Then: 경고로 끝나지 않고 RuntimeError 가 난다
        """

        # Given
        def _no_aggregate(*_args: object, **_kwargs: object) -> pd.DataFrame:
            return pd.DataFrame()

        monkeypatch.setattr(month_end_runner, "_aggregate", _no_aggregate)

        # When / Then
        with pytest.raises(RuntimeError, match="내부 불변조건 위반"):
            run_study((etf_dataset,), repeats=FAST_REPEATS, seed=FIXED_SEED)


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
        from verify_lab.studies.month_end.constants import DATASETS

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
        from verify_lab.studies.month_end.constants import DATASETS

        # When
        tickers = [dataset.ticker for dataset in DATASETS]

        # Then
        assert len(set(tickers)) == len(DATASETS), f"종목코드가 겹칩니다: {tickers}"

    def test_inverse_is_in_the_study_default_but_not_the_trading_default(self) -> None:
        """
        목적: **인버스가 검증에는 들고 매매에는 안 드는 것**을 고정한다 (2026-09-12).

        **검증에 드는 이유**: `execution.csv` 가 「아래」 방향을 **인버스 실물로 재는 표**이고,
        1배 ETF 의 하락률로 재면 분배락 하락이 이익으로 잡히는데 인버스는 그만큼 오르지 않는다
        (4월 +18.63% 대 +10.44%). **매매에서 빼는 이유**는 아래.

        「아래」 방향을 1배의 부호를 뒤집어 재는 것과 인버스 실물로 재는 것의 차이가
        6월 1.94 대 1.95 · 9월 2.97 대 3.05 · 12월 2.99 대 3.01 로 잡음이고, 실제 집행은
        2배 인버스라 1배 실물도 집행 상품이 아니다. **그래도 지우지 않는 이유**는
        어긋나는 칸이 곧 분배락이 걸린 칸이라(4월 +18.63% 대 +10.44%) 확정 전 교차검증에 쓰기 때문이다.

        Given: 검증 기본값과 매매 기본값
        When: 인버스가 어디에 있는지 본다
        Then: 검증에는 있고 매매에는 없다
        """
        # Given
        from verify_lab.studies.month_end.constants import (
            DATASETS,
            DATASETS_TRADING,
            EXECUTION_ROLE_DOWN,
        )

        # When
        in_study = {dataset.ticker for dataset in DATASETS if dataset.execution_role == EXECUTION_ROLE_DOWN}
        in_trading = {dataset.ticker for dataset in DATASETS_TRADING if dataset.execution_role == EXECUTION_ROLE_DOWN}

        # Then
        assert in_study, "검증 기본 대상에 인버스가 없습니다 — `execution.csv` 가 「아래」를 못 잽니다"
        assert in_trading == set(), f"매매 기본 대상에 인버스가 남아 있습니다: {in_trading}"
        assert set(DATASETS_TRADING) < set(DATASETS)

    def test_index_stays_in_the_default_targets(self) -> None:
        """
        목적: **지수는 두 계층 어디에서도 빼지 않는다.** 게이트 판정은 안 받지만
              ETF 로는 볼 수 없는 기간이 거기 있다 (코스피 종합 46년 · 코스닥 종합 30년).

        Given: 검증 기본 대상 목록
        When: 지수를 센다
        Then: 시장마다 둘씩 남아 있다
        """
        # Given
        from verify_lab.studies.month_end.constants import DATASETS

        # When
        indices = [dataset.ticker for dataset in DATASETS if dataset.is_index]

        # Then
        assert len(indices) == 4, f"지수가 기본 대상에서 빠졌습니다: {indices}"

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
        from verify_lab.studies.month_end.constants import DISPLAY_TICKER

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


class TestRunSummaryPaths:
    """실행 요약은 경로가 아니라 **파일 이름**을 담는다"""

    def test_요약에_절대경로가_없다(
        self,
        etf_outputs: StudyOutputs,
        assert_no_absolute_paths: Callable[[object, str], None],
    ) -> None:
        """
        목적: 두 PC 를 오가는 산출물에 그 PC 의 경로가 박히지 않게 한다.

        `save_run_summary` 가 저장 시점에 같은 판정으로 막지만, **여기서 먼저 잡으면**
        어느 검증이 그랬는지가 실패 메시지에 바로 나온다.

        Given: 합성 데이터로 돌린 산출물
        When: 요약을 재귀로 훑는다
        Then: 절대경로가 하나도 없다
        """
        assert_no_absolute_paths(etf_outputs.summary, "월말 진입 검증")
