"""검증 #10 실행 계층의 집계 축과 출력 계약을 고정한다.

**조합 순회와 조립이 스크립트가 아니라 `runner` 에 있는 이유**가 이 파일이다 —
테스트가 붙는 자리에 두지 않으면 가장 조용히 틀릴 수 있는 코드가 검사 밖에 남는다.

고정하는 계약은 다섯이다.

- 측정은 **확정 칸만** 내고 칸마다 한 행이다
- 식별 컬럼이 **성적표와 같은 이름**으로 앞에 온다 (두 표가 조인되어야 한다)
- 값은 **1배 롱 기준 그대로**다 — 「아래」 칸이라고 부호를 뒤집지 않는다
- 배당락 세 컬럼은 ETF 에서 채워지고 **지수에서는 비어 있다** (잴 수 없는 것과 0 은 다르다)
- 저장 표의 헤더가 전부 한글이다 (영문 토큰이 사용자에게 나가지 않는다)
"""

from collections.abc import Callable
from pathlib import Path

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
    PRICE_DECIMALS_KRW,
)
from verify_lab.measure.statistics import COL_MEAN, COL_SAMPLE_COUNT
from verify_lab.studies.month_end.constants import (
    EXECUTION_ROLE_NONE,
    EXECUTION_ROLE_UP,
    MARKET_KOSDAQ,
    Dataset,
)
from verify_lab.studies.month_end.runner import (
    StudyOutputs,
    display_tables,
    run_study,
)

# 순열 검정 반복 수. 계약만 보는 테스트라 크게 돌릴 이유가 없다
FAST_REPEATS = 20
FIXED_SEED = 0

# 합성 시세의 구간. 확정 칸(9월)이 여러 해 나오려면 몇 해가 필요하다
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

    # **수정주가 파일을 함께 만든다.** 실제 ETF 는 전부 갖고 있고, 없으면 배당락을 잴 수 없어
    # 측정이 거부한다 — 「안 걸림」과 「못 쟀다」를 구별하는 계약이 그것을 요구한다
    pd.DataFrame(
        {
            COL_DATE: days.date,
            COL_OPEN: prices,
            COL_HIGH: prices,
            COL_LOW: prices,
            COL_CLOSE: prices,
            COL_VOLUME: [1_000] * len(days),
        }
    ).to_csv(directory / ADJUSTED_FILE_TEMPLATE.format(ticker=ticker), index=False)

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


@pytest.fixture(scope="module")
def etf_dataset(tmp_path_factory: pytest.TempPathFactory) -> Dataset:
    """합성 ETF 대상 (파일은 임시 폴더에 격리된다).

    **모듈 스코프인 이유**: 순열 검정이 붙어 한 번 도는 데 시간이 걸린다.
    입력이 불변이라 공유해도 안전하다.
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


# ============================================================
# 확정 칸 개편 (2026-09-21) — 아래 계약이 새 규격이다
# ============================================================


def _write_adjusted(dataset: Dataset, *, shift_from: str, ratio: float) -> None:
    """그 대상의 수정주가 파일을 만든다.

    **원본가와 «다르게» 만든다.** 같으면 배당락이 0 으로 나와 「걸렸다」와 「안 걸렸다」를
    구별하는 계약을 검사할 수 없다. 특정 날짜부터 배율을 곱해 계단 하나를 심는다.

    Args:
        dataset: 시세 스키마 대상
        shift_from: 이 날짜부터 배율을 적용한다
        ratio: 곱할 배율 (1 보다 작으면 배당락 방향)
    """
    raw = pd.read_csv(dataset.path, parse_dates=[COL_DATE])
    adjusted = raw.copy()
    mask = adjusted[COL_DATE] < pd.Timestamp(shift_from)
    adjusted.loc[mask, COL_CLOSE] = (adjusted.loc[mask, COL_CLOSE] * ratio).round(PRICE_DECIMALS_KRW)

    adjusted.to_csv(
        dataset.directory / ADJUSTED_FILE_TEMPLATE.format(ticker=dataset.ticker),
        index=False,
    )


@pytest.fixture(scope="module")
def fixed_cell_etf(tmp_path_factory: pytest.TempPathFactory) -> Dataset:
    """확정 칸 측정용 합성 ETF. **수정주가에 계단을 심어** 배당락이 잡히게 한다."""
    dataset = _write_market(tmp_path_factory.mktemp("fixed_market"), "999901")
    _write_adjusted(dataset, shift_from="2019-09-25", ratio=0.99)

    return dataset


@pytest.fixture(scope="module")
def fixed_cell_outputs(fixed_cell_etf: Dataset) -> StudyOutputs:
    """확정 칸만 돈 산출물. **한 번만 실행한다.**"""
    return run_study((fixed_cell_etf,), repeats=FAST_REPEATS, seed=FIXED_SEED)


class TestFixedCellMeasure:
    """측정은 «확정 칸»만 낸다 — 축은 종목 × 월 × 방향"""

    def test_확정_칸은_9월_아래_하나다(self) -> None:
        """
        목적: 코드가 내는 칸 목록이 `규칙.md` §3 의 결론과 같음을 고정한다.

        **목록만 보고 근거를 짐작하면 안 된다** — 왜 이 칸인지는 그 문서가 갖는다
        (`.claude/rules/trading.md`). 여기서는 **몇 칸이고 무엇인지**만 못 박는다.

        Given: 확정 칸 상수
        When: 목록을 읽는다
        Then: 9월 · 아래 한 칸이다
        """
        # Given / When
        from verify_lab.studies.month_end.constants import TRADING_CELLS

        # Then
        assert len(TRADING_CELLS) == 1, f"확정 칸이 하나가 아닙니다: {TRADING_CELLS}"
        assert TRADING_CELLS[0].month == 9
        assert TRADING_CELLS[0].bet_down is True

    def test_측정표는_대상당_한_행이다(self, fixed_cell_outputs: StudyOutputs) -> None:
        """
        목적: `측정.csv` 가 **칸마다 한 행**임을 고정한다.

        성적표의 `시기 = 전체` 행과 1:1 로 조인되려면 그래야 한다.

        Given: 합성 ETF 하나를 확정 칸으로 돌린 산출물
        When: 측정 표의 행 수를 센다
        Then: 대상 1개 × 확정 칸 1개 = 1행이다
        """
        # Given
        from verify_lab.studies.month_end.constants import TRADING_CELLS

        # When
        rows = len(fixed_cell_outputs.measure)

        # Then
        assert rows == len(TRADING_CELLS), f"측정 표가 칸당 한 행이 아닙니다: {rows}행"

    def test_식별_컬럼이_성적표와_같은_이름으로_앞에_온다(self, fixed_cell_outputs: StudyOutputs) -> None:
        """
        목적: 측정 표와 성적표를 **같은 이름으로 조인**할 수 있게 한다.

        이름이 갈리면(`대상` 대 `종목`) 두 표를 나란히 읽을 수 없다.

        Given: 산출물
        When: 표시용 측정 표의 앞 세 컬럼을 본다
        Then: 종목 · 월 · 방향이다
        """
        # Given
        from verify_lab.execution.constants import DISPLAY_DIRECTION, DISPLAY_TICKER
        from verify_lab.studies.month_end.constants import DISPLAY_MONTH_NUMBER  # noqa: F401

        # When
        table = display_tables(fixed_cell_outputs)["measure"]

        # Then
        assert list(table.columns[:3]) == [DISPLAY_TICKER, DISPLAY_MONTH_NUMBER, DISPLAY_DIRECTION]

    def test_값은_1배_롱_기준_그대로다(self, fixed_cell_outputs: StudyOutputs) -> None:
        """
        목적: 「아래」 칸이라고 **부호를 뒤집지 않음**을 고정한다.

        뒤집으면 `기준선 오른 비율` 이 실제로는 내린 비율을 가리켜 **이름이 거짓이 된다.**
        `방향` 은 표시일 뿐이고, 그래서 성적표의 평균과 이 표의 평균은 부호가 다를 수 있다.

        Given: 아래로 거는 확정 칸의 산출물
        When: 측정 표의 평균과 같은 칸을 1배 롱으로 직접 집계한 평균을 견준다
        Then: 두 값이 같다 (뒤집히지 않았다)
        """
        # Given
        from verify_lab.measure.statistics import (
            COL_NEGATIVE_COUNT,
            COL_NEGATIVE_MEAN,
            COL_POSITIVE_COUNT,
            COL_POSITIVE_MEAN,
        )

        row = fixed_cell_outputs.measure.iloc[0]

        # When — 평균은 오른 쪽과 내린 쪽의 가중 합이다 (`내린 평균` 은 절대값이라 뺀다).
        # **한쪽 건수가 0 이면 그쪽 평균은 `NaN` 이므로 그 항을 0 으로 둔다** —
        # `measure` 계약이 「해당 건이 없으면 NaN 이며 0 이 아니다」로 정한 값이다
        def weighted(mean_column: str, count_column: str) -> float:
            count = int(row[count_column])

            return 0.0 if count == 0 else float(row[mean_column]) * count

        rebuilt = (
            weighted(COL_POSITIVE_MEAN, COL_POSITIVE_COUNT) - weighted(COL_NEGATIVE_MEAN, COL_NEGATIVE_COUNT)
        ) / int(row[COL_SAMPLE_COUNT])

        # Then — 「아래」라고 평균만 뒤집으면 이 항등식이 깨진다
        assert float(row[COL_MEAN]) == pytest.approx(rebuilt, abs=1e-9), "「아래」 칸에서 평균이 뒤집혔습니다"

    def test_ETF는_배당락_세_컬럼이_채워진다(self, fixed_cell_outputs: StudyOutputs) -> None:
        """
        목적: 확정 전 필수 항목인 배당락이 산출물에 실림을 고정한다
              (`.claude/rules/trading.md`).

        Given: 수정주가 파일이 있는 ETF 의 산출물
        When: 배당락 세 컬럼을 읽는다
        Then: 대조 건수가 1건 이상이고 값이 비어 있지 않다
        """
        # Given
        from verify_lab.measure.constants import (
            COL_DIVIDEND_HIT_COUNT,
            COL_DIVIDEND_MEAN_IMPACT,
            COL_DIVIDEND_MEASURED,
        )

        row = fixed_cell_outputs.measure.iloc[0]

        # When / Then
        assert int(row[COL_DIVIDEND_MEASURED]) > 0, "수정주가가 있는데 대조 건수가 0입니다"
        assert not pd.isna(row[COL_DIVIDEND_HIT_COUNT])
        assert not pd.isna(row[COL_DIVIDEND_MEAN_IMPACT])

    def test_지수는_배당락_세_컬럼이_비어_있다(self, index_dataset: Dataset) -> None:
        """
        목적: **지수는 상품이 아니라 분배금을 지급할 일이 없다.** 수정주가 파일도 없다.

        0 으로 채우면 「안 걸림」과 「잴 수 없음」이 구별되지 않는다 —
        그것이 `.claude/rules/trading.md` 가 경고한 바로 그 사고다.

        Given: 지수 대상 (수정주가 파일이 없다)
        When: 확정 칸으로 돌린다
        Then: 예외 없이 돌고 배당락 세 컬럼이 비어 있다
        """
        # Given
        from verify_lab.measure.constants import (
            COL_DIVIDEND_HIT_COUNT,
            COL_DIVIDEND_MEAN_IMPACT,
            COL_DIVIDEND_MEASURED,
        )

        # When
        outputs = run_study((index_dataset,), repeats=FAST_REPEATS, seed=FIXED_SEED)

        # Then
        row = outputs.measure.iloc[0]
        assert pd.isna(row[COL_DIVIDEND_MEASURED]), "지수인데 배당락 대조 건수가 채워졌습니다"
        assert pd.isna(row[COL_DIVIDEND_HIT_COUNT])
        assert pd.isna(row[COL_DIVIDEND_MEAN_IMPACT])


class TestMeasureOutputFiles:
    """산출물은 «측정 한 장»뿐이다 — 체결 둘과 합쳐 셋이 된다"""

    def test_출력_파일이_하나다(self) -> None:
        """
        목적: 측정 계층이 내는 파일이 `측정.csv` 하나임을 고정한다.

        Given: 산출물 이름 사전
        When: 값을 읽는다
        Then: 측정 한 장이고 파일 이름이 공통 상수와 같다
        """
        # Given
        from verify_lab.report.constants import MEASURE_FILENAME
        from verify_lab.studies.month_end.constants import OUTPUT_FILES

        # When / Then
        assert OUTPUT_FILES == {"measure": MEASURE_FILENAME}, f"산출물이 하나가 아닙니다: {OUTPUT_FILES}"

    def test_저장_표의_헤더가_전부_한글이다(self, fixed_cell_outputs: StudyOutputs) -> None:
        """
        목적: 영문 토큰이 사용자에게 나가지 않게 한다 (내부/출력 분리).

        Given: 산출물
        When: 표시용 표의 컬럼을 훑는다
        Then: ASCII 로만 된 컬럼이 없다
        """
        # Given
        tables = display_tables(fixed_cell_outputs)

        # When / Then
        for name, table in tables.items():
            ascii_only = [column for column in table.columns if column.isascii()]
            assert not ascii_only, f"{name} 표에 영문 헤더가 남아 있습니다: {ascii_only}"


class TestDatasetInvariants:
    """대상 정의의 불변조건 — 「집행 역할」이 체결 대상 목록을 정하므로 오타가 조용히 새면 안 된다

    **집행 축 표를 없애면서 그 테스트 파일이 사라졌고, 이 불변조건들이 함께 사라질 뻔했다.**
    `DATASETS_TRADING` 이 `execution_role` 문자열 비교로 유도되므로, 그 값이 한 글자만 달라도
    **인버스가 성적표 대상에 조용히 들어온다** — 예외가 나지 않는다.
    """

    def test_집행_역할은_선언된_셋_중_하나다(self) -> None:
        """
        목적: 오타가 새 역할을 만들지 못하게 한다.

        Given: 기본 대상 목록
        When: 집행 역할을 모은다
        Then: 선언된 셋 안에 있다
        """
        # Given
        from verify_lab.studies.month_end.constants import DATASETS, EXECUTION_ROLES

        # When
        roles = {dataset.execution_role for dataset in DATASETS}

        # Then
        assert roles <= set(EXECUTION_ROLES), f"선언되지 않은 집행 역할입니다: {roles - set(EXECUTION_ROLES)}"

    def test_지수는_집행할_수_없다(self) -> None:
        """
        목적: **살 수 없는 대상이 집행 상품으로 표시되지 않게** 한다 (측정의 원칙 9).

        Given: 기본 대상 목록
        When: 지수의 집행 역할을 본다
        Then: 전부 「불가」다
        """
        # Given
        from verify_lab.studies.month_end.constants import DATASETS, EXECUTION_ROLE_NONE

        # When
        roles = {dataset.execution_role for dataset in DATASETS if dataset.is_index}

        # Then
        assert roles == {EXECUTION_ROLE_NONE}, f"지수에 집행 역할이 붙어 있습니다: {roles}"

    def test_시장마다_위와_아래_상품이_하나씩이다(self) -> None:
        """
        목적: 같은 방향의 집행 상품이 둘이면 **어느 것으로 잰 값인지 산출물만 봐서는 모른다.**

        Given: 기본 대상 목록
        When: 시장 × 집행 역할로 센다
        Then: 「불가」가 아닌 칸이 시장마다 하나씩이다
        """
        # Given
        from collections import Counter

        from verify_lab.studies.month_end.constants import DATASETS, EXECUTION_ROLE_NONE

        # When
        counted = Counter(
            (dataset.market, dataset.execution_role)
            for dataset in DATASETS
            if dataset.execution_role != EXECUTION_ROLE_NONE
        )

        # Then
        duplicated = {key: count for key, count in counted.items() if count != 1}
        assert not duplicated, f"같은 시장에 같은 역할의 상품이 둘 이상입니다: {duplicated}"

    def test_전체_대상은_두_시장의_합이고_체결은_그_부분집합이다(self) -> None:
        """
        목적: 목록 셋이 갈라지지 않게 한다.

        Given: 세 목록
        When: 관계를 본다
        Then: `DATASETS` 는 두 시장의 합이고 `DATASETS_TRADING` 은 그 진부분집합이다
        """
        # Given
        from verify_lab.studies.month_end.constants import (
            DATASETS,
            DATASETS_KOSDAQ,
            DATASETS_KOSPI,
            DATASETS_TRADING,
        )

        # When / Then
        assert DATASETS == DATASETS_KOSPI + DATASETS_KOSDAQ
        assert set(DATASETS_TRADING) < set(DATASETS), "체결 기본값이 측정 기본값의 진부분집합이 아닙니다"

    def test_모든_대상이_시장을_갖는다(self) -> None:
        """
        목적: **조용히 빈칸이 되는 사고를 막는다.**

        시장이 조회표였을 때 `.get(label, "")` 가 빈 문자열을 내는데 바로 옆 줄은 같은 라벨로
        `KeyError` 를 내 **가드 강도가 정반대**였다 (`src/verify_lab/CLAUDE.md` 출력 계약).

        Given: 기본 대상 목록
        When: 시장 값을 본다
        Then: 빈 값이 없고 선언된 둘 중 하나다
        """
        # Given
        from verify_lab.studies.month_end.constants import DATASETS, MARKET_KOSDAQ, MARKET_KOSPI

        # When
        markets = {dataset.market for dataset in DATASETS}

        # Then
        assert markets == {MARKET_KOSPI, MARKET_KOSDAQ}, f"시장 값이 어긋납니다: {markets}"
