"""중간선거_사이클 체결 조립 — 분할매수 표와 진입 위치 표 · 손절선 격자 스위치

**새 표 셋이 기존 표와 어긋나지 않는지를 본다.** 산식은 `split_entry`·`indicators` 테스트가
고정하고, 여기서는 **조립의 계약**만 본다.

| 계약 | 왜 |
| --- | --- |
| 표본 보존 — 칸마다 원자료 행 수 = 진입 수 | 칸이 조용히 줄면 그 칸만 좋은 해로 평균이 난다 |
| 분할매수 집계의 **일시매수 행 = 성적표의 무손절 전체 행** | 두 표가 같은 체결을 다른 값으로 적으면 어느 쪽이 맞는지 판별할 수 없다 |
| 진입 위치 표는 진입마다 한 행 | 사용자가 해마다 차트와 대조하는 원자료다 (측정의 원칙 8) |
| **스위치를 켜면 손절선 격자 아홉 종이 전부 나온다** | 격자는 확정 규칙을 고른 근거이고, 시세를 다시 받으면 이 스위치로 다시 판단한다 — 값이 빠지거나 바뀌면 그 근거를 재현하지 못한다 |
| **손절선 설명 문구는 실제로 돈 손절선을 따르고, 스위치는 그 문구 하나만 바꾼다** | 돌지 않은 조건을 말하면 요약이 거짓이 되고, 격자 실행이 좁히기 전 산출물과 바이트 동일하다는 결과 문서의 기록이 문구의 자리에 달려 있다 |
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
    NOTE_STOP_BASE,
    PERIOD_ALL,
    stop_level_value,
)
from verify_lab.execution.run_summary import KEY_NOTES, KEY_ROW_COUNTS
from verify_lab.report.constants import DISPLAY_MEAN, DISPLAY_MIN, DISPLAY_PERIOD, DISPLAY_SAMPLE_COUNT
from verify_lab.studies.midterm_cycle import trading as trading_module
from verify_lab.studies.midterm_cycle.constants import (
    DISPLAY_FALLBACK,
    DISPLAY_SPLIT_METHOD,
    ENTRY_CONTEXT_FILENAME,
    SPLIT_METHODS,
    SPLIT_SUMMARY_FILENAME,
    SPLIT_TRADES_FILENAME,
    Dataset,
)
from verify_lab.studies.midterm_cycle.trading import (
    NOTE_SAMPLE,
    NOTE_STOP_CONFIRMED,
    TradingOutputs,
    run_midterm_cycle_trading,
)

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
def datasets(tmp_path_factory: pytest.TempPathFactory) -> tuple[Dataset, Dataset]:
    """합성 ETF 와 합성 지수.

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

    return (etf, index)


@pytest.fixture(scope="module")
def outputs(datasets: tuple[Dataset, Dataset]) -> TradingOutputs:
    """합성 대상으로 인자 없이 돈 체결 산출물."""
    return run_midterm_cycle_trading(datasets)


@pytest.fixture(scope="module")
def grid_outputs(datasets: tuple[Dataset, Dataset]) -> TradingOutputs:
    """같은 합성 대상으로 손절선 격자를 켜고 돈 체결 산출물."""
    return run_midterm_cycle_trading(datasets, stop_grid=True)


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


class TestStopGridSwitch:
    """손절선 격자는 스위치를 켰을 때만 전부 나온다"""

    # 격자 아홉 종. **프로덕션 상수를 import 하지 않고 손으로 박는다** — 격자 값을 다시 고르면
    # 여기서 걸려야 한다(`.claude/rules/trading.md` 「값을 재선정하지 않는다」)
    GRID_LEVELS = frozenset({"무손절", -5.0, -8.0, -10.0, -12.0, -15.0, -20.0, -25.0, -30.0})

    def test_stop_grid_emits_every_level_for_etf(self, grid_outputs: TradingOutputs) -> None:
        """
        목적: 스위치를 켜면 ETF 의 손절선이 격자 아홉 종 전부다.

        Given: 합성 ETF · 지수를 손절선 격자를 켜고 돈 산출물
        When: 성적표에서 ETF 행의 손절선 값을 모은다
        Then: 손으로 적은 아홉 종과 같다
        """
        # When
        performance = grid_outputs.performance
        levels = set(performance.loc[performance[DISPLAY_TICKER] == "합성 ETF", DISPLAY_STOP_LEVEL])

        # Then
        assert levels == self.GRID_LEVELS

    def test_stop_grid_leaves_index_single_row(self, grid_outputs: TradingOutputs) -> None:
        """
        목적: 스위치를 켜도 지수는 `손절불가` 한 줄이다 — 장중 고가·저가가 없어 손절을 잴 수 없다.

        Given: 합성 ETF · 지수를 손절선 격자를 켜고 돈 산출물
        When: 성적표에서 지수 행의 손절선 값을 모은다
        Then: `손절불가` 하나뿐이다
        """
        # When
        performance = grid_outputs.performance
        levels = set(performance.loc[performance[DISPLAY_TICKER] == "합성 지수", DISPLAY_STOP_LEVEL])

        # Then
        assert levels == {"손절불가"}


class TestStopNotes:
    """`summary.json` 의 손절선 설명 문구는 «실제로 돈» 손절선을 따른다"""

    def test_switch_swaps_the_stop_note(self, outputs: TradingOutputs, grid_outputs: TradingOutputs) -> None:
        """
        목적: 기본 실행은 확정 칸만 냈다는 문구를, 격자 실행은 가격 손절선의 기준 설명을 싣는다.

        Given: 합성 ETF · 지수를 인자 없이 돈 산출물과 손절선 격자를 켜고 돈 산출물
        When: 두 실행의 `notes` 를 본다
        Then: 기본은 `NOTE_STOP_CONFIRMED` 만, 격자는 `NOTE_STOP_BASE` 만 갖는다
        """
        # When
        default_notes = outputs.summary[KEY_NOTES]
        grid_notes = grid_outputs.summary[KEY_NOTES]

        # Then
        assert NOTE_STOP_CONFIRMED in default_notes, "기본 실행에 확정 칸 문구가 없습니다"
        assert NOTE_STOP_BASE not in default_notes, "기본 실행에 가격 손절선 설명이 실렸습니다"
        assert NOTE_STOP_BASE in grid_notes, "격자 실행에 가격 손절선 설명이 없습니다"
        assert NOTE_STOP_CONFIRMED not in grid_notes, "격자 실행에 확정 칸 문구가 실렸습니다"

    def test_switch_changes_only_the_stop_note(self, outputs: TradingOutputs, grid_outputs: TradingOutputs) -> None:
        """
        목적: 스위치가 손절 문구 하나만 바꾸고 나머지 문구의 구성과 순서는 그대로 둔다.

        Given: 합성 ETF · 지수를 인자 없이 돈 산출물과 손절선 격자를 켜고 돈 산출물
        When: 각자의 손절 문구를 뺀 나머지 `notes` 를 견준다
        Then: 순서까지 같다
        """
        # When
        default_rest = [note for note in outputs.summary[KEY_NOTES] if note != NOTE_STOP_CONFIRMED]
        grid_rest = [note for note in grid_outputs.summary[KEY_NOTES] if note != NOTE_STOP_BASE]

        # Then
        assert grid_rest == default_rest

    def test_price_stop_note_sits_right_before_the_sample_note(self, grid_outputs: TradingOutputs) -> None:
        """
        목적: 격자 실행의 가격 손절선 설명은 표본 하한 문구 바로 앞이다.

        결과 문서는 「`--stop-grid` 로 돌리면 좁히기 전 산출물과 `summary.json` 까지 바이트 단위로 같다」를
        재실행 기록으로 갖고, 그 동일성이 이 자리에 달려 있다 — 좁히기 전 산출물이 이 순서다.
        **전체 목록을 손으로 적지 않는다** — 새 문구가 더해질 때마다 이 테스트가 깨지게 된다.

        Given: 합성 ETF · 지수를 손절선 격자를 켜고 돈 산출물
        When: `NOTE_STOP_BASE` 다음 문구를 본다
        Then: `NOTE_SAMPLE` 이다
        """
        # Given
        notes = grid_outputs.summary[KEY_NOTES]

        # When
        following = notes[notes.index(NOTE_STOP_BASE) + 1]

        # Then
        assert following == NOTE_SAMPLE, "가격 손절선 설명의 자리가 바뀌었습니다 — 격자 실행이 좁히기 전 산출물과 달라집니다"

    def test_confirmed_price_stop_gets_the_price_stop_note(
        self, datasets: tuple[Dataset, Dataset], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        목적: 손절선 설명 문구는 스위치(`stop_grid`)가 아니라 «실제로 돈» 손절선을 따른다 — 확정 규칙이 가격 손절로
        바뀌면 기본 실행이 그 손절을 거므로, 가격 손절선 설명을 싣고 「무손절 한 종만 낸다」를 싣지 않는다.

        Given: 확정 손절선을 −25% 로 바꾼 합성 ETF · 지수
        When: 인자 없이 돈다
        Then: `NOTE_STOP_BASE` 가 있고 바로 다음이 `NOTE_SAMPLE` 이며, `NOTE_STOP_CONFIRMED` 가 없다
        """
        # Given
        monkeypatch.setattr(trading_module, "STOP_LEVELS_ETF_CONFIRMED", (0.25,))

        # When
        notes = run_midterm_cycle_trading(datasets).summary[KEY_NOTES]

        # Then
        assert NOTE_STOP_BASE in notes, "가격 손절을 돈 기본 실행에 가격 손절선 설명이 없습니다"
        assert notes[notes.index(NOTE_STOP_BASE) + 1] == NOTE_SAMPLE
        assert NOTE_STOP_CONFIRMED not in notes, "가격 손절을 돈 기본 실행에 「무손절 한 종만 낸다」가 실렸습니다"

    def test_index_only_grid_has_no_price_stop_note(self, datasets: tuple[Dataset, Dataset]) -> None:
        """
        목적: 지수만 돈 격자 실행에는 가격 손절선의 기준 설명을 싣지 않는다.

        지수는 장중 고가·저가가 없어 스위치를 켜도 `손절불가` 한 줄뿐이다. 그 실행에
        「갭 청산은 손절선보다 더 잃는다」가 실리면 돌지도 않은 조건을 말하게 된다.

        Given: 합성 지수 하나
        When: 손절선 격자를 켜고 돈다
        Then: `notes` 에 `NOTE_STOP_BASE` 가 없다
        """
        # Given
        index = datasets[1]
        assert index.is_index, "픽스처의 두 번째 대상이 지수가 아닙니다 — 이 테스트가 다른 것을 봅니다"

        # When
        notes = run_midterm_cycle_trading((index,), stop_grid=True).summary[KEY_NOTES]

        # Then
        assert NOTE_STOP_BASE not in notes, "지수만 돈 격자 실행에 가격 손절선 설명이 실렸습니다"
