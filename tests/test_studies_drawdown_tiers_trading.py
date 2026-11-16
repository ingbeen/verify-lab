"""하락_단계_매수 체결 조립 — 측정과 같은 진입점 · 지수 판정 안 함 · 사건 · 빈 칸의 시기 다섯 행을 고정한다.

| 무엇 | 근거 |
| --- | --- |
| 체결은 측정 원자료의 유효 행과 같은 판정일 · 같은 진입일이다 | 설계 결정 D1 — 측정과 체결이 같은 진입점 |
| 진입가는 판정일 다음 거래일 종가다 | D1 |
| 지수는 살 수 없어 판정하지 않고 손절을 잴 수 없다 | 측정의 원칙 9 · D2 |
| 성적표의 사건은 신호가 든 하락장 수다 | D6 · 측정의 원칙 5 |
| 체결이 없는 칸도 시기 다섯 행이 남는다 | 측정의 원칙 17 |

합성 시세는 손으로 짠 경로다 — 하락장 둘, VIX 급등 셋(첫 하락장 안 둘 · 두 번째 하락장 안 하나), 공포탐욕지수 급락 둘.
늦게 상장한 ETF 는 첫 하락장 안 VIX 급등 둘의 신호를 못 받는다.
"""

from pathlib import Path

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
    MARKET_FILE_TEMPLATE,
    PRICE_DECIMALS,
)
from verify_lab.execution.constants import NO_STOP_LABEL, PERIODS, STOP_NOT_MEASURABLE_LABEL
from verify_lab.measure.constants import COL_EXCLUDED_REASON, COL_HORIZON, COL_TICKER, REASON_NONE
from verify_lab.studies.drawdown_tiers.constants import (
    COL_ENTRY_DATE,
    COL_INDICATOR,
    COL_TIER,
    DRAWDOWN_RULE,
    INDICATOR_DRAWDOWN,
    INDICATOR_VIX,
    VIX_RULE,
    Dataset,
    IndicatorFiles,
)
from verify_lab.studies.drawdown_tiers.runner import StudyOutputs, run_study
from verify_lab.studies.drawdown_tiers.trading import TradingOutputs, run_drawdown_tiers_trading

SYNTHETIC_START = "2016-01-04"
SYNTHETIC_DAYS = 1_300

# 늦게 상장한 ETF 의 첫 거래일 위치 — 첫 하락장 안 VIX 급등 둘(위치 300 · 340) 뒤
LATE_LISTING = 350

# 종가 경로의 꺾이는 점 — 첫 하락장 200 → 90 (−55%), 두 번째 210 → 184 (−12.4%)
PRICE_KNOTS = (
    (0, 100.0),
    (200, 200.0),
    (400, 90.0),
    (700, 210.0),
    (800, 184.0),
    (900, 220.0),
    (SYNTHETIC_DAYS - 1, 260.0),
)
VIX_BASE = 15.0
# 첫 하락장 안에 VIX 구간이 둘(300 · 340 — 사이에 20 미만으로 다시 켬), 두 번째 하락장 안에 하나(760)
VIX_SPIKES = ((300, 301, 30.0), (301, 320, 65.0), (320, 321, 30.0), (340, 345, 31.0), (760, 770, 31.0))
FEAR_GREED_BASE = 60.0
FEAR_GREED_DIPS = ((310, 330, 3.0), (780, 790, 18.0))

LABEL_SIGNAL = "합성 신호 ETF"
LABEL_LATE = "합성 늦은 ETF"
LABEL_INDEX = "합성 지수"

# 성적표 · 거래내역 헤더 — 손으로 박는다 (프로덕션 상수를 가져오면 바뀌어도 따라와 아무것도 고정하지 못한다)
H_TICKER = "종목"
H_INDICATOR = "지표"
H_TIER = "단계"
H_HORIZON = "보유(거래일)"
H_JUDGMENT = "판정일"
H_ENTRY_DATE = "진입일"
H_ENTRY_PRICE = "진입가"
H_PERIOD = "시기"
H_SIGNALS = "신호"
H_STOP = "손절선(%)"
H_SCREEN = "1차 판정"
H_EVENTS = "사건"


def _days() -> pd.DatetimeIndex:
    return pd.bdate_range(SYNTHETIC_START, periods=SYNTHETIC_DAYS)


def _closes() -> np.ndarray:
    positions, values = zip(*PRICE_KNOTS, strict=True)
    return np.interp(np.arange(SYNTHETIC_DAYS), positions, values)


def _stepped(base: float, steps: tuple[tuple[int, int, float], ...]) -> np.ndarray:
    values = np.full(SYNTHETIC_DAYS, base)
    for start, end, value in steps:
        values[start:end] = value
    return values


def _write_market(path: Path, days: pd.DatetimeIndex, closes: np.ndarray, *, spread: float) -> None:
    opens = np.concatenate([[closes[0]], closes[:-1]])
    pd.DataFrame(
        {
            COL_DATE: days.strftime("%Y-%m-%d"),
            COL_OPEN: np.round(opens, PRICE_DECIMALS),
            COL_HIGH: np.round(np.maximum(opens, closes) * (1 + spread), PRICE_DECIMALS),
            COL_LOW: np.round(np.minimum(opens, closes) * (1 - spread), PRICE_DECIMALS),
            COL_CLOSE: np.round(closes, PRICE_DECIMALS),
            COL_VOLUME: 1_000_000,
        }
    ).to_csv(path, index=False)


def _write_inputs(directory: Path) -> tuple[tuple[Dataset, ...], IndicatorFiles]:
    days = _days()
    closes = _closes()
    _write_market(directory / MARKET_FILE_TEMPLATE.format(ticker="SYN"), days, closes, spread=0.01)
    _write_market(
        directory / MARKET_FILE_TEMPLATE.format(ticker="LATE"), days[LATE_LISTING:], closes[LATE_LISTING:], spread=0.01
    )
    _write_market(directory / MARKET_FILE_TEMPLATE.format(ticker="^SYNIDX"), days, closes / 10, spread=0.5)
    _write_market(directory / "^SYNVIX_raw.csv", days, _stepped(VIX_BASE, VIX_SPIKES), spread=0.0)
    pd.DataFrame({COL_DATE: days.strftime("%Y-%m-%d"), COL_VALUE: _stepped(FEAR_GREED_BASE, FEAR_GREED_DIPS)}).to_csv(
        directory / "fear_greed.csv", index=False
    )

    def etf(ticker: str, label: str) -> Dataset:
        return Dataset(
            ticker=ticker,
            label=label,
            symbol=ticker,
            signal_symbol="SYN",
            directory=directory,
            file_template=MARKET_FILE_TEMPLATE,
            price_column=COL_CLOSE,
            price_decimals=PRICE_DECIMALS,
            is_index=False,
        )

    index = Dataset(
        ticker="SYNIDX",
        label=LABEL_INDEX,
        symbol="^SYNIDX",
        signal_symbol="^SYNIDX",
        directory=directory,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_VALUE,
        price_decimals=PRICE_DECIMALS,
        is_index=True,
    )
    files = IndicatorFiles(vix=directory / "^SYNVIX_raw.csv", fear_greed=directory / "fear_greed.csv")

    return (etf("SYN", LABEL_SIGNAL), etf("LATE", LABEL_LATE), index), files


@pytest.fixture(scope="module")
def inputs(tmp_path_factory: pytest.TempPathFactory) -> tuple[tuple[Dataset, ...], IndicatorFiles]:
    return _write_inputs(tmp_path_factory.mktemp("drawdown_tiers_trading"))


@pytest.fixture(scope="module")
def trading(inputs: tuple[tuple[Dataset, ...], IndicatorFiles]) -> TradingOutputs:
    datasets, files = inputs
    return run_drawdown_tiers_trading(datasets, indicator_files=files)


@pytest.fixture(scope="module")
def study(inputs: tuple[tuple[Dataset, ...], IndicatorFiles]) -> StudyOutputs:
    datasets, files = inputs
    return run_study(datasets, indicator_files=files, repeats=5)


class TestSameEntryAsMeasure:
    """체결과 측정이 같은 신호 · 같은 진입점을 쓴다 (D1)"""

    def test_거래내역은_측정_원자료의_유효_행과_같다(self, trading: TradingOutputs, study: StudyOutputs) -> None:
        """
        목적: 두 계층이 다른 날에 들어가지 않음을 고정한다 — 진입 규칙을 두 벌 두면 갈린다

        Given: 같은 입력으로 돈 측정과 체결
        When: (종목 × 지표 × 단계 × 보유 × 판정일 × 진입일) 목록을 견준다
        Then: 같다
        """
        # Given
        valid = study.signals[study.signals[COL_EXCLUDED_REASON] == REASON_NONE]
        measured = pd.DataFrame(
            {
                H_TICKER: valid[COL_TICKER],
                H_INDICATOR: valid[COL_INDICATOR],
                H_TIER: valid[COL_TIER],
                H_HORIZON: valid[COL_HORIZON].astype(int),
                H_JUDGMENT: pd.DatetimeIndex(valid[COL_DATE]).strftime("%Y-%m-%d"),
                H_ENTRY_DATE: pd.DatetimeIndex(valid[COL_ENTRY_DATE]).strftime("%Y-%m-%d"),
            }
        )
        keys = list(measured.columns)

        # When
        traded = trading.trades[keys].astype({H_HORIZON: int})

        # Then
        left = measured.sort_values(keys).reset_index(drop=True)
        right = traded.sort_values(keys).reset_index(drop=True)
        pd.testing.assert_frame_equal(left, right)

    def test_진입가는_판정일_다음_거래일_종가다(self, trading: TradingOutputs) -> None:
        """
        목적: 진입점 산식을 시세로 대조한다 — 판정일 종가에 사면 그날 알 수 없던 값으로 산 것이 된다

        Given: 신호 ETF 의 거래내역
        When: 판정일 다음 거래일의 합성 종가와 진입가 · 진입일을 견준다
        Then: 같다
        """
        # Given
        days = _days()
        closes = pd.Series(np.round(_closes(), PRICE_DECIMALS), index=days)
        rows = trading.trades[trading.trades[H_TICKER] == LABEL_SIGNAL]
        assert not rows.empty

        # When
        positions = days.get_indexer(pd.DatetimeIndex(rows[H_JUDGMENT]))
        next_days = days[positions + 1]

        # Then
        assert list(pd.DatetimeIndex(rows[H_ENTRY_DATE])) == list(next_days)
        assert rows[H_ENTRY_PRICE].tolist() == pytest.approx(closes.loc[next_days].tolist(), abs=1e-9)


class TestIndexRows:
    """지수는 살 수 없어 판정하지 않고, 장중을 잴 수 없다 (측정의 원칙 9)"""

    def test_지수_행은_판정_안_함이고_손절불가다(self, trading: TradingOutputs) -> None:
        """
        목적: 지수의 성적이 판정 근거가 되지 않음과 손절 표기를 고정한다

        Given: 합성 지수를 포함해 돈 체결
        When: 지수 행과 ETF 행을 본다
        Then: 지수는 전 행이 「판정 안 함」 · 손절불가, ETF 는 무손절
        """
        # Given
        table = trading.performance
        index_rows = table[table[H_TICKER] == LABEL_INDEX]
        etf_rows = table[table[H_TICKER] != LABEL_INDEX]

        # When / Then
        assert (index_rows[H_SCREEN] == "판정 안 함").all()
        assert set(index_rows[H_STOP]) == {STOP_NOT_MEASURABLE_LABEL}
        assert set(etf_rows[H_STOP]) == {NO_STOP_LABEL}


class TestEvents:
    """사건 — 신호가 든 하락장 수 (D6)"""

    def test_두_하락장에_걸친_단계는_사건이_둘이다(self, trading: TradingOutputs) -> None:
        """
        목적: 같은 하락장의 신호를 한 사건으로 묶는 칸이 성적표에 실리는지 고정한다

        Given: −5% 단계가 두 하락장에서 한 번씩 닿은 신호 ETF
        When: 그 단계 · 21 거래일 칸의 전체 행을 본다
        Then: 신호 2 · 사건 2
        """
        # Given
        table = trading.performance
        tier = DRAWDOWN_RULE.label(DRAWDOWN_RULE.levels[0])

        # When
        row = table[
            (table[H_TICKER] == LABEL_SIGNAL)
            & (table[H_INDICATOR] == INDICATOR_DRAWDOWN)
            & (table[H_TIER] == tier)
            & (table[H_HORIZON] == 21)
            & (table[H_PERIOD] == PERIODS[0])
        ]

        # Then
        assert len(row) == 1
        assert int(row[H_SIGNALS].iloc[0]) == 2
        assert int(row[H_EVENTS].iloc[0]) == 2

    def test_한_하락장에_든_VIX_구간_둘은_사건_하나로_센다(self, trading: TradingOutputs) -> None:
        """
        목적: 지표 구간이 여럿이어도 같은 하락장이면 한 사건으로 묶임을 고정한다 — 그대로 세면 독립 표본처럼 읽힌다

        Given: 첫 하락장 안에 VIX 구간 둘, 두 번째 하락장 안에 하나인 신호 ETF
        When: VIX 25 이상 · 21 거래일 칸의 전체 행을 본다
        Then: 신호 3 · 사건 2
        """
        # Given
        table = trading.performance
        tier = VIX_RULE.label(VIX_RULE.levels[0])

        # When
        row = table[
            (table[H_TICKER] == LABEL_SIGNAL)
            & (table[H_INDICATOR] == INDICATOR_VIX)
            & (table[H_TIER] == tier)
            & (table[H_HORIZON] == 21)
            & (table[H_PERIOD] == PERIODS[0])
        ]

        # Then
        assert int(row[H_SIGNALS].iloc[0]) == 3
        assert int(row[H_EVENTS].iloc[0]) == 2


class TestEmptyCells:
    """체결이 없는 칸도 시기 다섯 행이 남는다 (측정의 원칙 17)"""

    def test_상장_전_신호뿐인_칸은_신호_0_으로_다섯_행이다(self, trading: TradingOutputs) -> None:
        """
        목적: 신호가 전부 상장 전이라 체결이 없는 칸이 사라지지 않음을 고정한다 — 사라지면 못 봤다는 사실 자체를 모른다

        Given: VIX 60 이상 신호가 상장 전에만 있는 늦은 ETF
        When: 그 단계 · 21 거래일 칸을 본다
        Then: 시기 다섯 행 · 신호 0 · 전 행 「판정 안 함」
        """
        # Given
        table = trading.performance
        tier = VIX_RULE.label(VIX_RULE.levels[-1])

        # When
        rows = table[
            (table[H_TICKER] == LABEL_LATE)
            & (table[H_INDICATOR] == INDICATOR_VIX)
            & (table[H_TIER] == tier)
            & (table[H_HORIZON] == 21)
        ]

        # Then
        assert rows[H_PERIOD].tolist() == list(PERIODS)
        assert (rows[H_SIGNALS] == 0).all()
        assert (rows[H_SCREEN] == "판정 안 함").all()

    def test_제외_건수는_요약이_대상_지표마다_담는다(self, trading: TradingOutputs, study: StudyOutputs) -> None:
        """
        목적: 거래내역에 없는 행(상장 전 · 끝 넘김)이 몇 건 왜 빠졌는지 체결 요약에도 남음을 고정한다

        Given: 같은 입력으로 돈 체결과 측정
        When: 대상 × 지표마다 체결 요약의 행 수 · 제외 건수와 거래내역 행 수를 견준다
        Then: 행 수 − 제외 = 거래내역 행 수
        """
        # Given
        targets = trading.summary["rule"]["targets"]
        trades = trading.trades

        # When / Then
        for record in targets:
            traded = trades[(trades[H_TICKER] == record["label"]) & (trades[H_INDICATOR] == record["indicator"])]
            assert record["signal_count"] - record["excluded_count"] == len(traded)
