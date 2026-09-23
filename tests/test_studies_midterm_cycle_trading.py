"""중간선거_사이클 체결 조립 — 분할매수 표와 진입 위치 표

**새 표 셋이 기존 표와 어긋나지 않는지를 본다.** 산식은 `split_entry`·`indicators` 테스트가
고정하고, 여기서는 **조립의 계약**만 본다.

| 계약 | 왜 |
| --- | --- |
| 표본 보존 — 칸마다 원자료 행 수 = 진입 수 | 칸이 조용히 줄면 그 칸만 좋은 해로 평균이 난다 |
| 분할매수 집계의 **일시매수 행 = 성적표의 무손절 전체 행** | 두 표가 같은 체결을 다른 값으로 적으면 어느 쪽이 맞는지 판별할 수 없다 |
| 진입 위치 표는 진입마다 한 행 | 사용자가 해마다 차트와 대조하는 원자료다 (측정의 원칙 8) |
"""

import numpy as np
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
)
from verify_lab.execution.constants import (
    DISPLAY_STOP_LEVEL,
    DISPLAY_TICKER,
    DISPLAY_TOTAL,
    DISPLAY_WORST_HOLD,
    PERIOD_ALL,
    stop_level_value,
)
from verify_lab.execution.run_summary import KEY_ROW_COUNTS
from verify_lab.report.constants import DISPLAY_MEAN, DISPLAY_MIN, DISPLAY_PERIOD, DISPLAY_SAMPLE_COUNT
from verify_lab.studies.midterm_cycle.constants import (
    DISPLAY_FALLBACK,
    DISPLAY_SPLIT_METHOD,
    ENTRY_CONTEXT_FILENAME,
    SPLIT_METHODS,
    SPLIT_SUMMARY_FILENAME,
    SPLIT_TRADES_FILENAME,
    Dataset,
)
from verify_lab.studies.midterm_cycle.trading import TradingOutputs, run_midterm_cycle_trading

# 합성 시세 구간 — 중간선거해 2014 · 2018 · 2022 세 번 진입하고 52주 창이 찬다
SYNTHETIC_START = "2012-01-02"
SYNTHETIC_END = "2025-12-31"

# 합성 시세 시드. **시드 없는 난수는 금지다**
SYNTHETIC_SEED = 20260923

# 그 구간의 중간선거해 진입 수
EXPECTED_ENTRIES = 3


def _frame() -> pd.DataFrame:
    """장중 등락이 있는 합성 시세.

    Returns:
        시세 스키마 DataFrame
    """
    days = pd.bdate_range(SYNTHETIC_START, SYNTHETIC_END)
    rng = np.random.default_rng(SYNTHETIC_SEED)
    closes = 100.0 * np.cumprod(np.concatenate([[1.0], 1.0 + rng.normal(0.0003, 0.012, len(days) - 1)]))
    opens = np.concatenate([[closes[0]], closes[:-1] * 1.001])

    return pd.DataFrame(
        {
            COL_DATE: days.strftime("%Y-%m-%d"),
            COL_OPEN: np.round(opens, PRICE_DECIMALS),
            COL_HIGH: np.round(np.maximum(opens, closes) * 1.01, PRICE_DECIMALS),
            COL_LOW: np.round(np.minimum(opens, closes) * 0.98, PRICE_DECIMALS),
            COL_CLOSE: np.round(closes, PRICE_DECIMALS),
            COL_VOLUME: 1_000_000,
        }
    )


@pytest.fixture(scope="module")
def outputs(tmp_path_factory: pytest.TempPathFactory) -> TradingOutputs:
    """합성 ETF 와 합성 지수로 돈 체결 산출물.

    **지수를 함께 넣는다** — 종가 계열(`Value`)에서도 분할매수와 지표가 도는지 봐야 한다.
    """
    directory = tmp_path_factory.mktemp("midterm_cycle_trading")
    frame = _frame()
    frame.to_csv(directory / MARKET_FILE_TEMPLATE.format(ticker="SYN"), index=False)
    pd.DataFrame({COL_DATE: frame[COL_DATE], COL_VALUE: frame[COL_CLOSE] * 10.0}).to_csv(
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

    return run_midterm_cycle_trading((etf, index))


def _cell_count() -> int:
    """격자의 (방식 × 미체결 처리) 칸 수.

    Returns:
        칸 수
    """
    return sum(len(method.fallbacks) for method in SPLIT_METHODS)


class TestSampleConservation:
    """표본 보존 — 칸마다 원자료 행 수 = 진입 수"""

    def test_split_trades_have_every_entry_in_every_cell(self, outputs: TradingOutputs) -> None:
        """
        목적: 분할매수 원자료가 대상 × 칸마다 진입 수만큼 행을 갖는다.

        Given: 합성 ETF · 지수 (진입 3건씩)
        When: 체결을 돈다
        Then: 대상 × 칸마다 3행이다
        """
        # When
        counts = outputs.split_trades.groupby([DISPLAY_TICKER, DISPLAY_SPLIT_METHOD, DISPLAY_FALLBACK]).size()

        # Then
        assert len(counts) == 2 * _cell_count()
        assert (counts == EXPECTED_ENTRIES).all()

    def test_split_summary_has_one_row_per_cell(self, outputs: TradingOutputs) -> None:
        """
        목적: 분할매수 집계는 대상 × 칸마다 한 행이고 표본이 진입 수와 같다.

        Given: 합성 ETF · 지수
        When: 체결을 돈다
        Then: 2 × 칸 수 행이고 표본이 전부 3 이다
        """
        # Then
        assert len(outputs.split_summary) == 2 * _cell_count()
        assert (outputs.split_summary[DISPLAY_SAMPLE_COUNT] == EXPECTED_ENTRIES).all()

    def test_entry_context_has_one_row_per_entry(self, outputs: TradingOutputs) -> None:
        """
        목적: 진입 위치 표는 대상마다 진입 수만큼 행이다.

        Given: 합성 ETF · 지수
        When: 체결을 돈다
        Then: 대상마다 3행이다
        """
        # When
        counts = outputs.entry_context.groupby(DISPLAY_TICKER).size()

        # Then
        assert counts.to_dict() == {"합성 ETF": EXPECTED_ENTRIES, "합성 지수": EXPECTED_ENTRIES}


class TestLumpSumAgreesWithPerformance:
    """분할매수 집계의 일시매수 행이 성적표의 무손절 전체 행과 같다"""

    @pytest.mark.parametrize(("ticker", "measurable"), [("합성 ETF", True), ("합성 지수", False)])
    def test_lump_row_matches(self, outputs: TradingOutputs, ticker: str, measurable: bool) -> None:
        """
        목적: 같은 체결을 두 표가 다른 값으로 적지 않는다.

        Given: 성적표의 무손절(지수는 손절불가) 전체 행
        When: 분할매수 집계의 일시매수 행과 견준다
        Then: 합계 · 평균 · 최악 · 보유 중 최악이 같다
        """
        # Given
        performance = outputs.performance
        reference = performance[
            (performance[DISPLAY_TICKER] == ticker)
            & (performance[DISPLAY_PERIOD] == PERIOD_ALL)
            & (performance[DISPLAY_STOP_LEVEL] == stop_level_value(None, measurable=measurable))
        ]
        summary = outputs.split_summary
        lump = summary[(summary[DISPLAY_TICKER] == ticker) & (summary[DISPLAY_SPLIT_METHOD] == SPLIT_METHODS[0].label)]

        # When / Then
        assert len(reference) == 1
        assert len(lump) == 1
        for column in (DISPLAY_TOTAL, DISPLAY_MEAN, DISPLAY_MIN, DISPLAY_WORST_HOLD):
            assert float(lump[column].iloc[0]) == pytest.approx(float(reference[column].iloc[0]), abs=1e-9), column


class TestRunSummary:
    """실행 요약이 새 파일의 행 수를 담는다"""

    def test_row_counts_include_the_new_tables(self, outputs: TradingOutputs) -> None:
        """
        목적: 새 표 셋의 행 수가 `summary.json` 에 파일 이름으로 실린다.

        Given: 체결 산출물
        When: 요약의 행 수를 본다
        Then: 세 파일의 행 수가 표 길이와 같다
        """
        # When
        counts = outputs.summary[KEY_ROW_COUNTS]

        # Then
        assert counts[ENTRY_CONTEXT_FILENAME] == len(outputs.entry_context)
        assert counts[SPLIT_SUMMARY_FILENAME] == len(outputs.split_summary)
        assert counts[SPLIT_TRADES_FILENAME] == len(outputs.split_trades)
