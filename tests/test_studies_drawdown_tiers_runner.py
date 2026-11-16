"""하락_단계_매수 측정 조립 — 칸 구성 · 표본 보존 · 공통 신호 · 달력 축 · 기준선 · 원자료를 고정한다.

| 무엇 | 근거 (`docs/검증/하락_단계_매수/설계.md` 「확정된 설계 결정」) |
| --- | --- |
| ETF 는 신호 대상(SPY 자리)의 신호를 함께 쓰고, 상장 전 판정일은 사유와 함께 남는다 | Q8 · D11 |
| 기준선은 그 지표의 판정 가능 첫날부터 | D8 |
| 달력 축(월 · 요일)은 `통계.csv` 에만, 표본이 없는 칸도 행이 남는다 | D7 · 측정의 원칙 12 · 17 |
| 원자료에 그날의 세 지표 값과 하락장 시작일 | Q11 · D6 |
| 지표 값이 빠진 날은 요약에 남는다 | D5 |

합성 시세는 손으로 짠 경로다 — 하락장 둘(−55% · −12%), VIX 급등 셋(첫 하락장 안 둘 · 두 번째 하락장 안 하나), 공포탐욕지수 급락 둘,
공포탐욕지수 하루 빠짐.
"""

from pathlib import Path
from typing import Any

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
from verify_lab.measure.constants import (
    BASELINE_SUFFIX,
    COL_EXCLUDED_COUNT,
    COL_EXCLUDED_REASON,
    COL_HORIZON,
    COL_NON_OVERLAPPING,
    COL_SIGNAL_COUNT,
    COL_TICKER,
    REASON_NONE,
)
from verify_lab.measure.statistics import COL_SAMPLE_COUNT
from verify_lab.studies.drawdown_tiers.constants import (
    CALENDAR_ALL,
    CALENDAR_MONTH,
    CALENDAR_WEEKDAY,
    COL_CALENDAR_AXIS,
    COL_CALENDAR_VALUE,
    COL_EVENT_COUNT,
    COL_FEAR_GREED,
    COL_INDICATOR,
    COL_TIER,
    COL_VIX,
    HORIZONS,
    INDICATOR_DRAWDOWN,
    INDICATOR_FEAR_GREED,
    INDICATOR_VIX,
    MONTH_NAMES,
    REASON_BEFORE_LISTING,
    RULES,
    VIX_RULE,
    WEEKDAY_NAMES,
    Dataset,
    IndicatorFiles,
)
from verify_lab.studies.drawdown_tiers.runner import (
    KEY_INDICATORS,
    KEY_MISSING_DAYS,
    StudyOutputs,
    load_dataset,
    run_study,
)

# 합성 거래일 수와 첫날
SYNTHETIC_START = "2016-01-04"
SYNTHETIC_DAYS = 1_300

# 늦게 상장한 ETF 의 첫 거래일 위치 — 첫 하락장의 −40% 단계(위치 약 345) 뒤, −50% 단계(약 382) 앞
LATE_LISTING = 350

# 공포탐욕지수의 첫날 위치와 빠진 날 위치 — 기준선 시작(D8)과 빠진 날(D5)을 잰다
FEAR_GREED_START = 100
FEAR_GREED_MISSING = 500

# 무작위 뽑기 반복 수 — 값이 아니라 표 모양을 보므로 적게
REPEATS = 20

# 종가 경로의 꺾이는 점 (위치, 종가) — 첫 하락장 200 → 90 (−55%), 두 번째 210 → 184 (−12.4%)
PRICE_KNOTS = (
    (0, 100.0),
    (200, 200.0),
    (400, 90.0),
    (700, 210.0),
    (800, 184.0),
    (900, 220.0),
    (SYNTHETIC_DAYS - 1, 260.0),
)

# VIX · 공포탐욕지수의 바깥 값과 구간별 값 (시작 위치, 끝 위치, 값). 하루에 ±200% 를 넘지 않게 두 계단으로 오른다
VIX_BASE = 15.0
# 첫 하락장 안에 VIX 구간이 둘(300 · 340 — 사이에 20 미만으로 다시 켬), 두 번째 하락장 안에 하나(760)
VIX_SPIKES = ((300, 301, 30.0), (301, 320, 65.0), (320, 321, 30.0), (340, 345, 31.0), (760, 770, 31.0))
FEAR_GREED_BASE = 60.0
FEAR_GREED_DIPS = ((310, 330, 3.0), (780, 790, 18.0))

LABEL_SIGNAL = "합성 신호 ETF"
LABEL_LATE = "합성 늦은 ETF"
LABEL_INDEX = "합성 지수"


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
    """OHLCV 시세 — `spread` 로 고가 · 저가를 벌린다(지수는 크게 벌려 새어 나가면 값으로 드러나게)."""
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
    """합성 대상 셋(신호 ETF · 늦은 ETF · 지수)과 지표 파일 둘을 쓴다."""
    days = _days()
    closes = _closes()
    _write_market(directory / MARKET_FILE_TEMPLATE.format(ticker="SYN"), days, closes, spread=0.01)
    _write_market(
        directory / MARKET_FILE_TEMPLATE.format(ticker="LATE"), days[LATE_LISTING:], closes[LATE_LISTING:], spread=0.01
    )
    _write_market(directory / MARKET_FILE_TEMPLATE.format(ticker="^SYNIDX"), days, closes / 10, spread=0.5)
    _write_market(directory / "^SYNVIX_raw.csv", days, _stepped(VIX_BASE, VIX_SPIKES), spread=0.0)

    fear_greed = pd.DataFrame(
        {COL_DATE: days.strftime("%Y-%m-%d"), COL_VALUE: _stepped(FEAR_GREED_BASE, FEAR_GREED_DIPS)}
    )
    fear_greed = fear_greed.iloc[FEAR_GREED_START:].drop(index=FEAR_GREED_MISSING)
    fear_greed.to_csv(directory / "fear_greed.csv", index=False)

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
    return _write_inputs(tmp_path_factory.mktemp("drawdown_tiers_runner"))


@pytest.fixture(scope="module")
def outputs(inputs: tuple[tuple[Dataset, ...], IndicatorFiles]) -> StudyOutputs:
    datasets, files = inputs
    return run_study(datasets, indicator_files=files, repeats=REPEATS)


def _tier_count() -> int:
    return sum(len(rule.levels) for rule in RULES)


def _indicator_record(outputs: StudyOutputs, label: str, indicator: str) -> dict[str, Any]:
    record = next(record for record in outputs.summary["datasets"] if record["label"] == label)
    return next(item for item in record[KEY_INDICATORS] if item["indicator"] == indicator)


class TestCellLayout:
    """칸 구성 — 격자 전부, 표본이 없는 칸도 행이 남는다"""

    def test_통계는_대상_단계_달력_보유마다_한_행이다(self, outputs: StudyOutputs) -> None:
        """
        목적: 달력 축(전체 · 12달 · 5요일)까지 칸이 빠짐없이 나옴을 고정한다 (D7 · 측정의 원칙 17)

        Given: 합성 대상 셋으로 돈 측정
        When: 통계 표의 행 수를 센다
        Then: 대상 3 × 단계 19 × 달력 18 × 보유 6 이고 키가 겹치지 않는다
        """
        # Given
        table = outputs.statistics
        keys = [COL_TICKER, COL_INDICATOR, COL_TIER, COL_CALENDAR_AXIS, COL_CALENDAR_VALUE, COL_HORIZON]

        # When / Then
        assert len(table) == 3 * _tier_count() * (1 + len(MONTH_NAMES) + len(WEEKDAY_NAMES)) * len(HORIZONS)
        assert not table.duplicated(subset=keys).any()

    def test_excess_와_test_는_달력_전체_칸만이다(self, outputs: StudyOutputs) -> None:
        """
        목적: 기준선 대비 차이 · 우연확률이 달력 «전체» 칸에만 있음을 고정한다 (D7 — 통계에만 축을 쪼갬)

        Given: 합성 대상 셋으로 돈 측정
        When: 두 표의 행 수를 센다
        Then: 대상 3 × 단계 19 × 보유 6
        """
        # Given / When / Then
        assert len(outputs.excess) == 3 * _tier_count() * len(HORIZONS)
        assert len(outputs.test) == 3 * _tier_count() * len(HORIZONS)


class TestSamplePreservation:
    """표본 보존 — 신호 = 표본 + 제외, 원자료 행 = 요약의 행 수"""

    def test_통계_전체_칸의_신호는_표본과_제외의_합이다(self, outputs: StudyOutputs) -> None:
        """
        목적: 집계에서 표본이 조용히 사라지지 않음을 고정한다

        Given: 통계 표의 달력 «전체» 칸
        When: 신호 · 표본 · 제외를 견준다
        Then: 모든 행에서 신호 = 표본 + 제외
        """
        # Given
        table = outputs.statistics[outputs.statistics[COL_CALENDAR_AXIS] == CALENDAR_ALL]

        # When / Then
        assert (table[COL_SIGNAL_COUNT] == table[COL_SAMPLE_COUNT] + table[COL_EXCLUDED_COUNT]).all()

    def test_요약의_행_수와_제외_건수가_원자료와_같다(self, outputs: StudyOutputs) -> None:
        """
        목적: 몇 건이 왜 빠졌는지가 요약에 남는지 고정한다 (절대 원칙 4)

        Given: 합성 대상 셋으로 돈 측정
        When: 대상 × 지표마다 요약과 신호내역을 견준다
        Then: 행 수 · 제외 건수 · 사유별 건수가 같다
        """
        # Given
        signals = outputs.signals

        # When / Then
        for record in outputs.summary["datasets"]:
            for item in record[KEY_INDICATORS]:
                rows = signals[(signals[COL_TICKER] == record["label"]) & (signals[COL_INDICATOR] == item["indicator"])]
                excluded = rows[rows[COL_EXCLUDED_REASON] != REASON_NONE]
                assert item["signal_count"] == len(rows)
                assert item["excluded_count"] == len(excluded)
                assert item["excluded_by_reason"] == excluded[COL_EXCLUDED_REASON].value_counts().to_dict()

    def test_상장_전_판정일은_사유와_함께_남는다(self, outputs: StudyOutputs) -> None:
        """
        목적: 공통 신호를 늦게 상장한 대상에 걸 때 상장 전 판정일이 행으로 남음을 고정한다 (D11)

        Given: 첫 하락장의 −5 ~ −40% 단계가 상장 전, −50% 단계가 상장 뒤인 대상
        When: 그 대상의 낙폭 요약을 본다
        Then: 상장 전 사유가 단계 일곱 × 보유 기간 수만큼이다
        """
        # Given / When
        record = _indicator_record(outputs, LABEL_LATE, INDICATOR_DRAWDOWN)

        # Then
        assert record["excluded_by_reason"][REASON_BEFORE_LISTING] == 7 * len(HORIZONS)


class TestIndependenceColumns:
    """통계 표의 사건 · 비중첩 표본 — 표본이 서로 독립인가 (측정의 원칙 5 · 설계 결정 D6)"""

    @staticmethod
    def _cell(outputs: StudyOutputs, label: str, horizon: int) -> pd.Series:
        table = outputs.statistics
        tier = VIX_RULE.label(VIX_RULE.levels[0])
        rows = table[
            (table[COL_TICKER] == label)
            & (table[COL_INDICATOR] == INDICATOR_VIX)
            & (table[COL_TIER] == tier)
            & (table[COL_CALENDAR_AXIS] == CALENDAR_ALL)
            & (table[COL_HORIZON] == horizon)
        ]
        assert len(rows) == 1
        return rows.iloc[0]

    @pytest.mark.parametrize(("horizon", "non_overlapping"), [(21, 3), (63, 2)])
    def test_같은_하락장의_신호는_사건_하나이고_비중첩은_보유_기간으로_센다(
        self, outputs: StudyOutputs, horizon: int, non_overlapping: int
    ) -> None:
        """
        목적: 사건과 비중첩 표본의 산식을 손계산으로 고정한다

        Given: VIX 25 이상 진입이 위치 301 · 341 (첫 하락장) · 761 (두 번째 하락장)인 신호 ETF
        When: 통계 표의 달력 «전체» 칸을 본다
        Then: 사건 2. 비중첩은 21거래일이면 셋 다 안 겹쳐 3, 63거래일이면 301 ~ 364 와 341 이 겹쳐 2
        """
        # Given / When
        row = self._cell(outputs, LABEL_SIGNAL, horizon)

        # Then
        assert row[COL_SAMPLE_COUNT] == 3
        assert row[COL_EVENT_COUNT] == 2
        assert row[COL_NON_OVERLAPPING] == non_overlapping

    def test_사건은_유효_표본만_센다(self, outputs: StudyOutputs) -> None:
        """
        목적: 제외된 행(상장 전)의 하락장을 사건으로 세지 않음을 고정한다 — 세면 표본보다 사건이 많아진다

        Given: 첫 하락장의 VIX 신호 둘이 상장 전이라 제외된 늦은 ETF
        When: VIX 25 이상 · 21거래일 칸을 본다
        Then: 표본 1 · 사건 1
        """
        # Given / When
        row = self._cell(outputs, LABEL_LATE, 21)

        # Then
        assert row[COL_SAMPLE_COUNT] == 1
        assert row[COL_EVENT_COUNT] == 1


class TestSharedSignal:
    """ETF 는 신호 대상의 신호를 함께 쓴다 (Q8)"""

    def test_늦은_ETF_의_판정일은_신호_ETF_와_같다(self, outputs: StudyOutputs) -> None:
        """
        목적: 판정일이 대상 자신이 아니라 신호 대상의 낙폭 · 달력에서 나옴을 고정한다

        Given: 같은 신호 대상을 쓰는 두 ETF
        When: 지표 × 단계마다 판정일 목록을 견준다
        Then: 같다 (상장 전 판정일도 행으로 남아 있으므로)
        """
        # Given
        signals = outputs.signals
        keys = [COL_INDICATOR, COL_TIER, COL_DATE]

        # When
        first = signals[signals[COL_TICKER] == LABEL_SIGNAL][keys].drop_duplicates().reset_index(drop=True)
        late = signals[signals[COL_TICKER] == LABEL_LATE][keys].drop_duplicates().reset_index(drop=True)

        # Then
        pd.testing.assert_frame_equal(first, late)


class TestCalendarAxis:
    """달력 축 분해 — 월 · 요일 칸의 합이 전체와 같다 (D7)"""

    @pytest.mark.parametrize("axis", [CALENDAR_MONTH, CALENDAR_WEEKDAY])
    def test_축_칸의_신호_합이_전체와_같다(self, outputs: StudyOutputs, axis: str) -> None:
        """
        목적: 축을 쪼갤 때 판정일이 빠지거나 두 번 세지 않음을 고정한다

        Given: 통계 표
        When: (대상 × 지표 × 단계 × 보유)마다 그 축 칸의 신호를 더한다
        Then: 전체 칸의 신호와 같다
        """
        # Given
        table = outputs.statistics
        keys = [COL_TICKER, COL_INDICATOR, COL_TIER, COL_HORIZON]

        # When
        whole = table[table[COL_CALENDAR_AXIS] == CALENDAR_ALL].set_index(keys)[COL_SIGNAL_COUNT]
        parts = table[table[COL_CALENDAR_AXIS] == axis].groupby(keys)[COL_SIGNAL_COUNT].sum()

        # Then
        pd.testing.assert_series_equal(parts.sort_index(), whole.sort_index(), check_names=False)


class TestBaseline:
    """기준선 — 그 지표의 판정 가능 첫날부터의 모든 대상 거래일 (D8)"""

    def test_공포탐욕지수의_기준선은_지표_첫날부터다(self, outputs: StudyOutputs) -> None:
        """
        목적: 기준선 모집단이 지표 기간에 맞춰짐을 고정한다 — 낙폭 행은 대상 전 기간, 공포탐욕지수 행은 지표 첫날부터

        Given: 신호 ETF 의 excess 표
        When: 지표별 기준선 신호 수를 본다
        Then: 낙폭은 거래일 전부, 공포탐욕지수는 지표 첫날 이후 거래일 수
        """
        # Given
        table = outputs.excess[outputs.excess[COL_TICKER] == LABEL_SIGNAL]
        column = f"{COL_SIGNAL_COUNT}{BASELINE_SUFFIX}"

        # When
        drawdown = set(table.loc[table[COL_INDICATOR] == INDICATOR_DRAWDOWN, column])
        fear_greed = set(table.loc[table[COL_INDICATOR] == INDICATOR_FEAR_GREED, column])

        # Then
        assert drawdown == {SYNTHETIC_DAYS}
        assert fear_greed == {SYNTHETIC_DAYS - FEAR_GREED_START}


class TestSignalContext:
    """원자료 — 판정일의 세 지표 값 · 빠진 날"""

    def test_판정일의_지표_값이_원본과_같다(self, outputs: StudyOutputs) -> None:
        """
        목적: 사용자가 대조하는 원자료의 지표 값이 그날 값임을 고정한다 (Q11)

        Given: 신호 ETF 의 VIX 신호 행
        When: 판정일의 VIX · 공포탐욕지수 값을 합성 원본과 견준다
        Then: 같다 (공포탐욕지수가 빠진 날 · 첫날 전은 빈칸)
        """
        # Given
        days = _days()
        vix = pd.Series(_stepped(VIX_BASE, VIX_SPIKES), index=days)
        fear_greed = pd.Series(_stepped(FEAR_GREED_BASE, FEAR_GREED_DIPS), index=days)
        fear_greed.iloc[:FEAR_GREED_START] = np.nan
        fear_greed.iloc[FEAR_GREED_MISSING] = np.nan
        rows = outputs.signals[
            (outputs.signals[COL_TICKER] == LABEL_SIGNAL) & (outputs.signals[COL_INDICATOR] == INDICATOR_VIX)
        ]
        assert not rows.empty

        # When
        dates = pd.DatetimeIndex(rows[COL_DATE])

        # Then
        assert rows[COL_VIX].tolist() == pytest.approx(vix.loc[dates].tolist(), abs=1e-12)
        assert rows[COL_FEAR_GREED].tolist() == pytest.approx(fear_greed.loc[dates].tolist(), abs=1e-12, nan_ok=True)

    def test_지표가_빠진_날은_요약에_남는다(self, outputs: StudyOutputs) -> None:
        """
        목적: 판정하지 않은 날의 수가 요약에 남음을 고정한다 (D5)

        Given: 공포탐욕지수가 하루 빠진 합성 지표
        When: 신호 ETF 의 공포탐욕지수 요약을 본다
        Then: 빠진 날이 1이다 (지표 첫날 전은 판정 기간 밖이라 세지 않는다)
        """
        # Given / When
        record = _indicator_record(outputs, LABEL_SIGNAL, INDICATOR_FEAR_GREED)

        # Then
        assert record[KEY_MISSING_DAYS] == 1


class TestIndexLoad:
    """지수는 종가 계열로 읽는다 — 고가 · 저가를 프레임에 남기지 않는다"""

    def test_지수_대상은_날짜와_값_두_칸이다(self, inputs: tuple[tuple[Dataset, ...], IndicatorFiles]) -> None:
        """
        목적: 장중 판정이 가짜 고가 · 저가를 쓰지 않게 지수의 읽는 모양을 고정한다

        Given: 고가 · 저가를 크게 벌린 합성 지수
        When: 대상을 읽는다
        Then: 날짜 · 값 두 칸이다
        """
        # Given
        index = next(dataset for dataset in inputs[0] if dataset.is_index)

        # When
        frame = load_dataset(index).frame

        # Then
        assert list(frame.columns) == [COL_DATE, COL_VALUE]


class TestGuards:
    """입력 검증"""

    def test_대상이_비면_예외다(self, inputs: tuple[tuple[Dataset, ...], IndicatorFiles]) -> None:
        """
        목적: 빈 대상으로 빈 산출물이 조용히 나가지 않게 한다

        Given: 빈 대상 목록
        When: 측정을 돈다
        Then: ValueError
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="대상"):
            run_study((), indicator_files=inputs[1], repeats=REPEATS)
