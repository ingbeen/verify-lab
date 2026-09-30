"""반감기_사이클 측정 조립 — 칸 구성 · 표본 보존 · 기준선 · 데이터 품질 표를 고정한다.

| 무엇 | 왜 |
| --- | --- |
| 반감기 날짜 넷 | **블록 헤더 시각의 UTC 날짜**다(2026-09-29 사용자 결정 a). 데이터에서 유도하면 2024 가 04-19 가 되어 0개월 진입이 반감기 블록보다 9분 앞선다 |
| 칸마다 `신호 = 표본 + 제외` | 청산이 오지 않은 진입이 조용히 사라지면 생존편향이 생긴다 |
| 기준선이 첫 반감기부터 매일 | 「기준선 모집단은 신호군과 같은 기간」(`src/verify_lab/CLAUDE.md` 실행 계층 계약) |
| 크로스체크가 «대체 전» 값으로 잰다 | 대체한 값끼리 견주면 거래가 없던 날의 괴리가 사라져 목록에서 빠진다 |
"""

from datetime import UTC, datetime
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
from verify_lab.data.crosscheck import COL_PRIMARY, COL_SECONDARY
from verify_lab.execution.run_summary import KEY_DATASETS, KEY_ROW_COUNTS
from verify_lab.measure.constants import (
    COL_EXCLUDED_COUNT,
    COL_EXCLUDED_REASON,
    COL_FORWARD_RETURN,
    COL_JUDGEABLE,
    COL_SIGNAL_COUNT,
    JUDGEABLE_NO,
    REASON_NONE,
)
from verify_lab.measure.statistics import (
    COL_MEAN,
    COL_SAMPLE_COUNT,
    COL_TEST_NOTE,
    COL_WIN_RATE,
    NOTE_TOO_FEW_SAMPLES,
)
from verify_lab.report.run_summary import KEY_TRACK
from verify_lab.studies.halving_cycle import runner as runner_module
from verify_lab.studies.halving_cycle.constants import (
    BASELINE_SUFFIX,
    COL_BASELINE_NON_OVERLAPPING,
    COL_CALENDAR_YEAR,
    COL_CYCLE_COUNT,
    COL_ENTRY_MONTHS,
    COL_EXIT_MONTHS,
    COL_HALVING,
    COL_HOLD_MONTHS,
    COL_HOLD_RETURNS,
    COL_INDICATOR_SIGNAL,
    COL_JUDGMENT_DATE,
    COL_NON_OVERLAPPING,
    COL_POSITION_RETURN,
    COL_SIGNAL_MEANING,
    COL_VALUE_DAY,
    DATASETS,
    ENTRY_MONTHS,
    EXIT_MONTHS,
    GRID_BASELINE_FILENAME,
    GRID_BASELINE_HOLD_MONTHS,
    HALVINGS,
    HOLD_MONTHS,
    INDICATOR_SIGNALS,
    OUTPUT_FILES,
    SPLIT_BUY_LAST_DEADLINES,
    SPLIT_BUY_START_MONTHS_HALVING,
    SPLIT_BUY_START_MONTHS_HIGH,
    SPLIT_SELL_LAST_DEADLINES,
    SPLIT_SELL_START_MONTHS,
    SPLIT_TRANCHES,
    TRACK_NAME,
    Dataset,
    Halving,
)
from verify_lab.studies.halving_cycle.runner import (
    KEY_DROPPED_TAIL_DAYS,
    KEY_GRID_BASELINE_HOLD_MONTHS,
    KEY_MISSING_PRICE_DAYS,
    KEY_ONCHAIN,
    KEY_SPLIT,
    KEY_SPLIT_BUY,
    KEY_SPLIT_COMBINATIONS,
    KEY_SPLIT_FILL_COUNT,
    KEY_SPLIT_POSITION_COUNT,
    KEY_SPLIT_RULE,
    KEY_SPLIT_SELL,
    KEY_SPLIT_UNFILLED,
    KEY_SPLIT_UNFINISHED,
    StudyOutputs,
    display_tables,
    grid_baseline_table,
    load_dataset,
    load_onchain,
    run_study,
)

# 합성 시세 구간. **첫 반감기(2012-11-28) 앞에서 시작해야** 네 반감기가 모두 시세 안에 든다
SYNTHETIC_START = "2012-01-01"
SYNTHETIC_END = "2025-12-31"

# 합성 시세를 만드는 난수 시드. **시드 없는 난수는 금지다**
SYNTHETIC_SEED = 20260929

# 거래가 없던 날. 실제 거래 중단 사흘(2015-01-06 ~ 08)의 모양을 옮긴다
HALT_DAYS = ("2015-01-06", "2015-01-07")

# 그날의 기준가를 이월값보다 20% 높게 둔다 — 크로스체크 허용폭(5%)을 넘어 목록에 올라야 한다
HALT_REFERENCE_GAP = 1.20

# 순열 검정 반복 수. 계약만 보므로 적게 돌린다
TEST_REPEATS = 20

# 합성 온체인 계열의 시작 — 시세보다 앞이다
ONCHAIN_START = "2011-01-01"

# 합성 MVRV 의 주기(일)
MVRV_PERIOD_DAYS = 900

# 0건이 되도록 만든 신호 — 합성 MVRV 가 4 를 넘지 않는다
NEVER_CROSSED = "NUPL 0.75 상향 돌파"


def _market() -> pd.DataFrame:
    """휴장 없이 매일 거래하는 합성 시세. 거래가 없던 이틀은 네 값이 전일 종가다."""
    days = pd.date_range(SYNTHETIC_START, SYNTHETIC_END, freq="D")
    rng = np.random.default_rng(SYNTHETIC_SEED)
    closes = 100.0 * np.cumprod(np.concatenate([[1.0], 1.0 + rng.normal(0.001, 0.02, len(days) - 1)]))
    frame = pd.DataFrame(
        {
            COL_DATE: days,
            COL_OPEN: closes * 0.999,
            COL_HIGH: closes * 1.01,
            COL_LOW: closes * 0.98,
            COL_CLOSE: closes,
            COL_VOLUME: 1_000.0,
        }
    )
    for day in HALT_DAYS:
        position = int(days.get_loc(pd.Timestamp(day)))
        previous = float(frame.loc[position - 1, COL_CLOSE])
        frame.loc[position, [COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE]] = previous
        frame.loc[position, COL_VOLUME] = 0.0

    return frame.round({column: PRICE_DECIMALS for column in (COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE)})


def _reference(market: pd.DataFrame) -> pd.DataFrame:
    """종가에 0.1% 를 얹은 기준가. 거래가 없던 날만 크게 벌린다."""
    values = market[COL_CLOSE] * 1.001
    halted = market[COL_DATE].isin(pd.to_datetime(HALT_DAYS))
    values = values.where(~halted, market[COL_CLOSE] * HALT_REFERENCE_GAP)

    return pd.DataFrame({COL_DATE: market[COL_DATE], COL_VALUE: values.round(PRICE_DECIMALS)})


def _onchain(market: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """합성 MVRV 와 시가총액. **시세보다 1년 앞에서 시작한다** — 실제 Coin Metrics 가 Bitstamp 보다 먼저 시작한다.

    MVRV 는 900일 주기로 0.2 ~ 3.8 을 오가 문턱 1 · 1.7 · 3 · 3.7 을 여러 번 지나고, **4 는 한 번도 넘지 않는다** —
    NUPL 0.75(= MVRV 4) 신호가 0건인 칸이 생겨 「0건이어도 행을 남긴다」를 기본 신호 목록 그대로 검사한다.
    """
    days = pd.date_range(ONCHAIN_START, SYNTHETIC_END, freq="D")
    phase = 2.0 * np.pi * np.arange(len(days)) / MVRV_PERIOD_DAYS
    mvrv = pd.DataFrame({COL_DATE: days, COL_VALUE: np.round(2.0 + 1.8 * np.sin(phase), 4)})
    closes = market.set_index(COL_DATE)[COL_CLOSE].reindex(days).bfill()
    market_cap = pd.DataFrame({COL_DATE: days, COL_VALUE: np.round(closes.to_numpy() * 1e7, 0)})

    return mvrv, market_cap


def _write_series(frame: pd.DataFrame, path: Path) -> Path:
    """단일 값 계열을 로더가 읽는 모양(날짜 문자열)으로 쓴다."""
    frame.assign(**{COL_DATE: frame[COL_DATE].dt.strftime("%Y-%m-%d")}).to_csv(path, index=False)
    return path


def _dataset(directory: Path) -> Dataset:
    """합성 시세 · 기준가 · MVRV · 시가총액을 파일로 쓰고 대상 하나를 만든다."""
    market = _market()
    market.assign(**{COL_DATE: market[COL_DATE].dt.strftime("%Y-%m-%d")}).to_csv(
        directory / MARKET_FILE_TEMPLATE.format(ticker="SYN"), index=False
    )
    reference_path = _write_series(_reference(market), directory / "SYN_PriceUSD.csv")
    mvrv, market_cap = _onchain(market)

    return Dataset(
        ticker="SYN",
        label="합성 비트코인",
        directory=directory,
        file_template=MARKET_FILE_TEMPLATE,
        reference_path=reference_path,
        mvrv_path=_write_series(mvrv, directory / "SYN_CapMVRVCur.csv"),
        market_cap_path=_write_series(market_cap, directory / "SYN_CapMrktCurUSD.csv"),
        price_decimals=PRICE_DECIMALS,
        is_judged=True,
    )


@pytest.fixture(scope="module")
def synthetic_dataset(tmp_path_factory: pytest.TempPathFactory) -> Dataset:
    """합성 입력 대상 — 측정 결과와 손 계산이 같은 파일을 읽는다."""
    return _dataset(tmp_path_factory.mktemp("halving"))


@pytest.fixture(scope="module")
def outputs(synthetic_dataset: Dataset) -> StudyOutputs:
    """합성 입력으로 돈 측정 결과."""
    return run_study((synthetic_dataset,), repeats=TEST_REPEATS, seed=0)


def _expected_same_cycle_cells(frame: pd.DataFrame) -> dict[tuple[int, int], tuple[int, list[float]]]:
    """같은 사이클에 파는 칸마다 (신호 수, 유효 수익률)을 반감기 날짜와 달력월로 **직접** 센다.

    구현의 일정 함수(`position_schedule`)를 쓰지 않는다 — 같은 함수로 기대값을 만들면 그 함수가 틀려도 통과한다.
    진입일이 다음 반감기 뒤이거나 데이터 뒤면 신호가 아니고, 청산일이 다음 반감기 뒤이거나 데이터 뒤면 제외다.
    """
    closes = frame.set_index(COL_DATE)[COL_CLOSE]
    last_day = frame[COL_DATE].iloc[-1]
    halving_days = [halving.day for halving in HALVINGS]

    cells: dict[tuple[int, int], tuple[int, list[float]]] = {}
    for entry in ENTRY_MONTHS:
        for exit_ in EXIT_MONTHS:
            if exit_ <= entry:
                continue
            signals = 0
            returns: list[float] = []
            for index, start in enumerate(halving_days):
                bound = halving_days[index + 1] if index + 1 < len(halving_days) else None
                entry_day = start + pd.DateOffset(months=entry)
                if (bound is not None and entry_day >= bound) or entry_day > last_day:
                    continue
                signals += 1
                exit_day = start + pd.DateOffset(months=exit_)
                if (bound is not None and exit_day >= bound) or exit_day > last_day:
                    continue
                returns.append(float(closes[exit_day] / closes[entry_day] - 1.0))
            cells[(entry, exit_)] = (signals, returns)

    return cells


class TestConstants:
    """결과를 보기 «전»에 정한 값 — 바뀌면 측정 전체가 다른 것을 잰다"""

    def test_반감기는_블록_헤더_시각의_UTC_날짜다(self) -> None:
        """
        목적: 2026-09-29 결정 a 를 고정한다 — 2024 는 04-19 가 아니라 04-20 이다.

        Given: 반감기 상수
        When: 높이와 날짜를 본다
        Then: 210,000 · 420,000 · 630,000 · 840,000 과 그 블록의 UTC 날짜다
        """
        assert [halving.height for halving in HALVINGS] == [210_000, 420_000, 630_000, 840_000]
        assert [halving.label for halving in HALVINGS] == ["2012-11-28", "2016-07-09", "2020-05-11", "2024-04-20"]
        assert HALVINGS[3].block_time == datetime(2024, 4, 20, 0, 9, 27, tzinfo=UTC)

    def test_격자는_16_곱하기_3_이다(self) -> None:
        """
        목적: 결정 ⑥ 의 격자(결과를 보기 전에 정한 값)를 고정한다.

        Given: 격자 상수
        When: 진입·보유 개월을 본다
        Then: 진입 0 ~ 45 를 3개월 간격, 보유 3 · 6 · 12
        """
        assert ENTRY_MONTHS == tuple(range(0, 46, 3))
        assert HOLD_MONTHS == (3, 6, 12)

    def test_대상은_Bitstamp_시세와_Coin_Metrics_기준가를_가리킨다(self) -> None:
        """
        목적: 측정 대상(결정 ⑤)과 대체용 계열(결정 ④)의 파일을 고정한다 — 파일은 읽지 않는다.

        Given: 대상 목록
        When: 파일 이름을 본다
        Then: 대상 하나이고 `BTCUSD_max.csv` · `BTC_PriceUSD.csv` 이며 판정 대상이다
        """
        assert len(DATASETS) == 1
        assert DATASETS[0].path.name == "BTCUSD_max.csv"
        assert DATASETS[0].reference_path.name == "BTC_PriceUSD.csv"
        assert DATASETS[0].mvrv_path.name == "BTC_CapMVRVCur.csv"
        assert DATASETS[0].market_cap_path.name == "BTC_CapMrktCurUSD.csv"
        assert DATASETS[0].is_judged

    def test_지표_신호는_책이_문턱을_적은_열넷이다(self) -> None:
        """
        목적: 결정 ㉖ 첫 표의 신호 목록(결과를 보기 전에 정한 값)을 순서까지 고정한다.

        기대값은 손으로 적는다 — 상수에서 가져오면 목록을 고칠 때 테스트가 함께 따라온다.

        Given: 신호 상수
        When: 이름 · 문턱 · 방향을 본다
        Then: 설계 문서의 표와 같다
        """
        expected = [
            ("Pi Cycle 상향 돌파", 1.0, True),
            ("MVRV-Z 7 상향 돌파", 7.0, True),
            ("MVRV-Z 6 상향 돌파", 6.0, True),
            ("MVRV-Z 0 하향 돌파", 0.0, False),
            ("MVRV 1 하향 돌파", 1.0, False),
            ("MVRV 1 상향 돌파", 1.0, True),
            ("MVRV 1.7 하향 돌파", 1.7, False),
            ("MVRV 3 상향 돌파", 3.0, True),
            ("MVRV 3.7 상향 돌파", 3.7, True),
            ("NUPL 0.75 상향 돌파", 0.75, True),
            ("월간 RSI 50 하향 이탈", 50.0, False),
            ("월간 RSI 50 상향 돌파", 50.0, True),
            ("월간 MACD 시그널 상향 돌파", 0.0, True),
            ("월간 MACD 시그널 하향 돌파", 0.0, False),
        ]
        assert [(signal.name, signal.threshold, signal.upward) for signal in INDICATOR_SIGNALS] == expected


class TestStatistics:
    """칸 구성과 표본 보존"""

    def test_진입_곱하기_보유_칸마다_한_행이다(self, outputs: StudyOutputs) -> None:
        """
        목적: 48칸이 빠짐없이 한 번씩 나옴을 고정한다.

        Given: 합성 입력의 측정 결과
        When: 통계 표의 칸을 본다
        Then: (진입, 보유) 쌍이 격자와 같고 겹치지 않는다
        """
        cells = list(zip(outputs.statistics[COL_ENTRY_MONTHS], outputs.statistics[COL_HOLD_MONTHS], strict=True))

        assert sorted(cells) == sorted((entry, hold) for entry in ENTRY_MONTHS for hold in HOLD_MONTHS)

    def test_신호는_표본과_제외의_합이다(self, outputs: StudyOutputs) -> None:
        """
        목적: 청산이 오지 않은 진입이 제외로 세어지고 사라지지 않음을 고정한다 (표본 보존).

        Given: 통계 표
        When: 칸마다 세 수를 본다
        Then: 신호 = 표본 + 제외 이고, 제외가 있는 칸이 하나 이상이다(2024 사이클 뒤쪽)
        """
        table = outputs.statistics

        assert (table[COL_SIGNAL_COUNT] == table[COL_SAMPLE_COUNT] + table[COL_EXCLUDED_COUNT]).all()
        assert table[COL_EXCLUDED_COUNT].sum() > 0

    def test_신호는_칸마다_반감기_수를_넘지_않는다(self, outputs: StudyOutputs) -> None:
        """
        목적: 한 칸이 사이클마다 한 번만 진입함을 고정한다 — 표본이 3 ~ 4건인 이유다.

        Given: 통계 표
        When: 신호 수를 본다
        Then: 전부 반감기 수(4) 이하이고 최대가 4 다
        """
        assert outputs.statistics[COL_SIGNAL_COUNT].max() == len(HALVINGS)

    def test_신호_쪽_비중첩은_표본과_같다(self, outputs: StudyOutputs) -> None:
        """
        목적: 사이클마다 한 번인 신호가 서로 겹치지 않음을 고정한다 (측정의 원칙 5 의 답).

        Given: 통계 표
        When: 비중첩 표본과 표본을 견준다
        Then: 같다
        """
        table = outputs.statistics

        assert (table[COL_NON_OVERLAPPING] == table[COL_SAMPLE_COUNT]).all()


class TestBaseline:
    """기준선 — 첫 반감기부터 매일 진입, 같은 보유"""

    def test_기준선_신호는_첫_반감기부터의_날_수다(self, outputs: StudyOutputs) -> None:
        """
        목적: 기준선이 첫 반감기 앞의 날을 넣지 않음을 고정한다.

        Given: excess 표
        When: 기준선 신호 수를 본다
        Then: 칸마다 2012-11-28 ~ 2025-12-31 의 날 수와 같다
        """
        expected = len(pd.date_range(HALVINGS[0].day, SYNTHETIC_END, freq="D"))

        assert (outputs.excess[f"{COL_SIGNAL_COUNT}{BASELINE_SUFFIX}"] == expected).all()

    def test_기준선_비중첩은_표본보다_훨씬_적다(self, outputs: StudyOutputs) -> None:
        """
        목적: 매일 진입하는 기준선의 겹침을 드러냄을 고정한다 — 표본 수만 보면 실제보다 단단해 보인다.

        Given: excess 표
        When: 기준선 비중첩과 표본을 견준다
        Then: 비중첩이 표본의 1/10 보다 작다
        """
        table = outputs.excess

        assert (table[COL_BASELINE_NON_OVERLAPPING] * 10 < table[f"{COL_SAMPLE_COUNT}{BASELINE_SUFFIX}"]).all()

    def test_우연확률은_표본_부족으로_검정하지_않는다(self, outputs: StudyOutputs) -> None:
        """
        목적: 칸당 표본이 하한(10) 미만이면 우연확률을 만들어 내지 않음을 고정한다 (측정의 원칙 12).

        Given: test 표
        When: 검정 비고를 본다
        Then: 전 칸이 「표본 부족으로 검정 불가」다
        """
        assert (outputs.test[COL_TEST_NOTE] == NOTE_TOO_FEW_SAMPLES).all()


class TestEntries:
    """진입내역 — 측정 long-form 그대로"""

    def test_행_수는_통계의_신호_합과_같다(self, outputs: StudyOutputs) -> None:
        """
        목적: 원자료와 집계가 같은 진입을 셈을 고정한다 (측정의 원칙 8).

        Given: 진입내역과 통계 표
        When: 행 수와 신호 합을 견준다
        Then: 같다
        """
        assert len(outputs.entries) == int(outputs.statistics[COL_SIGNAL_COUNT].sum())

    def test_제외된_행도_남고_사유가_있다(self, outputs: StudyOutputs) -> None:
        """
        목적: 청산이 오지 않은 진입이 원자료에서도 보임을 고정한다.

        Given: 진입내역
        When: 제외 행을 본다
        Then: 통계의 제외 합과 같은 수가 있고 사유가 비어 있지 않다
        """
        excluded = outputs.entries[outputs.entries[COL_EXCLUDED_REASON] != REASON_NONE]

        assert len(excluded) == int(outputs.statistics[COL_EXCLUDED_COUNT].sum())
        assert (excluded[COL_EXCLUDED_REASON].str.len() > 0).all()


class TestDataQualityTables:
    """크로스체크와 대체일"""

    def test_크로스체크는_대체_전_원시_종가로_잰다(self, outputs: StudyOutputs) -> None:
        """
        목적: 거래가 없던 날의 괴리가 목록에서 사라지지 않음을 고정한다.

        Given: 거래가 없던 이틀에 기준가를 20% 높게 둔 입력
        When: 크로스체크 표를 본다
        Then: 그 이틀이 있고 Bitstamp 종가가 이월값(대체 전)이다
        """
        table = outputs.crosscheck.set_index(COL_DATE)
        halted = pd.to_datetime(HALT_DAYS)

        assert set(halted) <= set(table.index)
        np.testing.assert_allclose(
            table.loc[halted, COL_SECONDARY].to_numpy() / table.loc[halted, COL_PRIMARY].to_numpy(),
            HALT_REFERENCE_GAP,
            rtol=1e-3,
        )

    def test_대체일은_거래가_없던_날이다(self, outputs: StudyOutputs) -> None:
        """
        목적: 대체한 날을 빠짐없이 표시함을 고정한다 (결정 ④).

        Given: 거래가 없던 이틀
        When: 대체일 표를 본다
        Then: 그 이틀이다
        """
        assert outputs.replaced[COL_DATE].tolist() == list(pd.to_datetime(HALT_DAYS))

    def test_달력_연도는_데이터가_닿는_해마다_한_행이다(self, outputs: StudyOutputs) -> None:
        """
        목적: 끝이 잘린 해도 행을 남김을 고정한다 (측정의 원칙 17).

        Given: 2012-01-01 ~ 2025-12-31 시세
        When: 달력 연도 표를 본다
        Then: 2012 ~ 2025 열네 행이고 2012 는 제외, 나머지는 잰다
        """
        table = outputs.calendar_years.set_index(COL_CALENDAR_YEAR)

        assert table.index.tolist() == list(range(2012, 2026))
        assert table.loc[2012, COL_EXCLUDED_REASON] != REASON_NONE
        assert (table.loc[2013:, COL_EXCLUDED_REASON] == REASON_NONE).all()


class TestSummaryAndDisplay:
    """실행 요약과 표시용 표"""

    def test_요약의_행_수_키가_산출물_파일_이름이다(self, outputs: StudyOutputs) -> None:
        """
        목적: `row_counts` 가 `OUTPUT_FILES` 의 파일 이름으로 키잉됨을 고정한다 (검증 계층 계약).

        Given: 측정 요약
        When: 행 수의 키를 본다
        Then: 매매법 이름이 맞고 키가 `OUTPUT_FILES` 의 값과 같다
        """
        assert outputs.summary[KEY_TRACK] == TRACK_NAME
        assert set(outputs.summary[KEY_ROW_COUNTS]) == set(OUTPUT_FILES.values())

    def test_표시용_표가_산출물_필드마다_있다(self, outputs: StudyOutputs) -> None:
        """
        목적: CLI 가 `OUTPUT_FILES` 를 돌며 저장할 수 있게 표시용 표가 필드마다 있음을 고정한다.

        Given: 측정 결과
        When: 표시용 표를 만든다
        Then: 키가 `OUTPUT_FILES` 의 키와 같다
        """
        assert set(display_tables(outputs)) == set(OUTPUT_FILES)

    def test_표시용_통계는_한글_헤더와_백분율이다(self, outputs: StudyOutputs) -> None:
        """
        목적: 영문 토큰이 CSV 로 나가지 않고 비율이 백분율로 바뀜을 고정한다 (내부/출력 분리).

        Given: 통계 표
        When: 표시용으로 바꾼다
        Then: 축 헤더가 한글이고 평균이 비율 × 100 (2자리)이다
        """
        table = display_tables(outputs)["statistics"]

        assert {"반감기 뒤 진입(개월)", "보유(개월)", "평균(%)"} <= set(table.columns)
        np.testing.assert_allclose(
            table["평균(%)"].to_numpy(dtype=float),
            (outputs.statistics[COL_MEAN] * 100).round(2).to_numpy(dtype=float),
            atol=1e-9,
        )


class TestIndicatorStatistics:
    """2단계 지표통계 — 신호 × 보유"""

    def test_신호_곱하기_보유_칸마다_한_행이다(self, outputs: StudyOutputs) -> None:
        """
        목적: 신호 열넷 × 보유 셋이 신호 순서 → 보유 순서로 빠짐없이 한 번씩 나옴을 고정한다.

        Given: 합성 입력의 측정 결과
        When: 지표통계의 칸을 본다
        Then: (신호, 보유) 쌍이 목록 순서와 같다
        """
        cells = list(
            zip(
                outputs.indicator_statistics[COL_INDICATOR_SIGNAL],
                outputs.indicator_statistics[COL_HOLD_MONTHS],
                strict=True,
            )
        )

        assert cells == [(signal.name, hold) for signal in INDICATOR_SIGNALS for hold in HOLD_MONTHS]

    def test_신호는_표본과_제외의_합이다(self, outputs: StudyOutputs) -> None:
        """
        목적: 잴 수 없던 판정이 제외로 세어지고 사라지지 않음을 고정한다 (표본 보존).

        Given: 지표통계
        When: 칸마다 세 수를 본다
        Then: 신호 = 표본 + 제외
        """
        table = outputs.indicator_statistics

        assert (table[COL_SIGNAL_COUNT] == table[COL_SAMPLE_COUNT] + table[COL_EXCLUDED_COUNT]).all()

    def test_한_번도_없던_신호도_행이_남고_지표가_빈다(self, outputs: StudyOutputs) -> None:
        """
        목적: 0건인 신호의 행을 지우지도 0 으로 채우지도 않음을 고정한다 (측정의 원칙 17).

        Given: 합성 MVRV 가 4 를 넘지 않아 NUPL 0.75 신호가 0건인 입력
        When: 그 신호의 행을 본다
        Then: 보유마다 한 행이고 신호 0 · 평균이 비어 있으며 판정가능이 「아니오」다
        """
        rows = outputs.indicator_statistics[outputs.indicator_statistics[COL_INDICATOR_SIGNAL] == NEVER_CROSSED]

        assert len(rows) == len(HOLD_MONTHS)
        assert (rows[COL_SIGNAL_COUNT] == 0).all()
        assert rows[COL_MEAN].isna().all()
        assert (rows[COL_JUDGEABLE] == JUDGEABLE_NO).all()

    def test_책이_붙인_뜻이_신호마다_실린다(self, outputs: StudyOutputs) -> None:
        """
        목적: 산출물만 보고도 그 신호가 책에서 무엇을 뜻했는지 읽힘을 고정한다.

        Given: 지표통계
        When: 뜻 컬럼을 본다
        Then: 신호 상수의 뜻과 같다
        """
        meanings = {signal.name: signal.meaning for signal in INDICATOR_SIGNALS}
        table = outputs.indicator_statistics

        assert list(table[COL_SIGNAL_MEANING]) == [meanings[name] for name in table[COL_INDICATOR_SIGNAL]]

    def test_사이클_수는_유효_표본이_있는_반감기_수다(self, outputs: StudyOutputs) -> None:
        """
        목적: 사이클 수가 신호일 목록의 유효 행에서 센 반감기 수와 같음을 고정한다 (측정의 원칙 5).

        Given: 지표통계와 지표신호
        When: 칸마다 유효 행의 반감기 종류를 센다
        Then: 사이클 수와 같고 반감기 수(4)를 넘지 않는다
        """
        signals = outputs.indicator_signals
        valid = signals[signals[COL_EXCLUDED_REASON] == REASON_NONE]
        counted = valid.groupby([COL_INDICATOR_SIGNAL, COL_HOLD_MONTHS])[COL_HALVING].nunique()

        for _, row in outputs.indicator_statistics.iterrows():
            expected = int(counted.get((row[COL_INDICATOR_SIGNAL], row[COL_HOLD_MONTHS]), 0))
            assert row[COL_CYCLE_COUNT] == expected
        assert outputs.indicator_statistics[COL_CYCLE_COUNT].max() <= len(HALVINGS)

    def test_기준선은_1단계와_같은_보유의_기준선이다(self, outputs: StudyOutputs) -> None:
        """
        목적: 2단계가 1단계와 같은 기준선(결정 ⑬)을 씀을 고정한다 — 두 표의 기준선 값이 같다.

        Given: 지표통계와 1단계 excess
        When: 보유마다 기준선 평균을 견준다
        Then: 같다
        """
        column = f"{COL_MEAN}{BASELINE_SUFFIX}"
        stage_one = outputs.excess.groupby(COL_HOLD_MONTHS)[column].first()

        for _, row in outputs.indicator_statistics.iterrows():
            assert row[column] == pytest.approx(stage_one[row[COL_HOLD_MONTHS]], abs=1e-12)


class TestIndicatorSignalsAndCycles:
    """2단계 원자료 — 신호일 목록과 사이클 분해"""

    def test_신호일_목록의_행은_지표통계의_신호_합이다(self, outputs: StudyOutputs) -> None:
        """
        목적: 원자료와 집계가 같은 판정을 셈을 고정한다 (측정의 원칙 8).

        Given: 지표신호와 지표통계
        When: 행 수와 신호 합을 견준다
        Then: 같고, 판정일이 전부 시세 안이다
        """
        assert len(outputs.indicator_signals) == int(outputs.indicator_statistics[COL_SIGNAL_COUNT].sum())
        assert outputs.indicator_signals[COL_JUDGMENT_DATE].min() >= pd.Timestamp(SYNTHETIC_START)

    def test_사이클_분해는_신호_곱하기_보유_곱하기_반감기다(self, outputs: StudyOutputs) -> None:
        """
        목적: 0건인 사이클도 행이 남음을 고정한다 — 한 사이클에 몰린 신호가 보이려면 빈 사이클도 보여야 한다.

        Given: 지표사이클
        When: 행 수와 칸 구성을 본다
        Then: 신호 × 보유 × 반감기이고, 사이클마다 센 신호에 첫 반감기 전 판정을 더하면 지표통계의 신호와 같다
        """
        cycles = outputs.indicator_cycles
        assert len(cycles) == len(INDICATOR_SIGNALS) * len(HOLD_MONTHS) * len(HALVINGS)
        assert set(cycles[COL_HALVING]) == {halving.label for halving in HALVINGS}

        signals = outputs.indicator_signals
        before = signals[~signals[COL_HALVING].isin([halving.label for halving in HALVINGS])]
        before_counts = before.groupby([COL_INDICATOR_SIGNAL, COL_HOLD_MONTHS]).size()
        cycle_sums = cycles.groupby([COL_INDICATOR_SIGNAL, COL_HOLD_MONTHS])[COL_SIGNAL_COUNT].sum()
        for _, row in outputs.indicator_statistics.iterrows():
            key = (row[COL_INDICATOR_SIGNAL], row[COL_HOLD_MONTHS])
            assert int(cycle_sums[key]) + int(before_counts.get(key, 0)) == row[COL_SIGNAL_COUNT]


class TestEntryIndicators:
    """1단계 진입일의 지표 값"""

    def test_1단계_진입마다_한_행이고_값은_전날_것이다(self, outputs: StudyOutputs) -> None:
        """
        목적: 진입지표가 1단계 진입마다 한 행이고 값 기준일이 진입 전날임을 고정한다 (결정 ㉗).

        Given: 진입지표와 1단계 진입내역
        When: 행과 날짜를 본다
        Then: 행 수가 1단계 진입 수이고 값 기준일 = 진입일 − 1 일이다
        """
        table = outputs.entry_indicators
        stage_one = outputs.entries.drop_duplicates([COL_HALVING, COL_ENTRY_MONTHS])

        assert len(table) == len(stage_one)
        assert (table[COL_VALUE_DAY] == table[COL_DATE] - pd.Timedelta(1, unit="D")).all()

    def test_수익률은_1단계_진입내역과_같다(self, outputs: StudyOutputs) -> None:
        """
        목적: 진입지표에 붙인 보유별 수익률이 1단계 원자료와 같음을 고정한다 — 두 표가 다른 값을 싣지 않는다.

        Given: 진입지표와 진입내역
        When: 보유마다 수익률을 견준다
        Then: 같다 (청산 전인 칸은 둘 다 비어 있다)
        """
        entries = outputs.entries.set_index([COL_HALVING, COL_ENTRY_MONTHS, COL_HOLD_MONTHS])[COL_FORWARD_RETURN]

        for _, row in outputs.entry_indicators.iterrows():
            for hold in HOLD_MONTHS:
                expected = entries[(row[COL_HALVING], row[COL_ENTRY_MONTHS], hold)]
                actual = row[COL_HOLD_RETURNS[hold]]
                assert (pd.isna(expected) and pd.isna(actual)) or actual == pytest.approx(expected, abs=1e-12)


class TestOnchainLoading:
    """온체인 두 계열 읽기"""

    def test_끝이_하루_어긋나면_함께_있는_날만_쓴다(self, tmp_path: Path) -> None:
        """
        목적: 두 계열의 끝이 공개 지연으로 하루 어긋나도 측정이 멈추지 않음을 고정한다 — 한쪽에만 있는 끝 날을 뺀다.

        두 계열은 따로 받고 각자 공개 지연 하루를 허용받으므로 실제로 일어날 수 있는 모양이다. 멈추면 1단계와 체결까지
        산출물이 하나도 나오지 않는다.

        Given: 시가총액만 하루 짧은 입력
        When: 온체인 계열을 읽는다
        Then: 한 표의 마지막 날이 시가총액의 마지막 날이고, 두 파일의 원래 행 수는 따로 남으며, 뺀 날 1일을 돌려준다
        """
        # Given
        dataset = _dataset(tmp_path)
        market_cap = pd.read_csv(dataset.market_cap_path).iloc[:-1]
        market_cap.to_csv(dataset.market_cap_path, index=False)

        # When
        loaded = load_onchain(dataset)

        # Then
        assert loaded.frame[COL_DATE].iloc[-1] == pd.Timestamp(market_cap[COL_DATE].iloc[-1])
        assert len(loaded.frame) == len(loaded.market_cap) == len(loaded.mvrv) - 1
        assert loaded.dropped_days == 1

    def test_끝이_허용치보다_크게_어긋나면_멈춘다(self, tmp_path: Path) -> None:
        """
        목적: 묵은 파일이 섞이면 멈춤을 고정한다 — 끝 날을 빼고 지나가면 그 사이의 온체인 돌파가 예외 없이 사라진다.

        허용치는 수집기의 공개 지연 일수(`data/coinmetrics_collector.PUBLICATION_LAG_DAYS`)다. 두 계열을 같은 수집에서
        받으면 그보다 크게 어긋날 수 없다.

        Given: 시가총액만 이틀 짧은 입력 (허용치 하루)
        When: 온체인 계열을 읽는다
        Then: ValueError
        """
        # Given
        dataset = _dataset(tmp_path)
        pd.read_csv(dataset.market_cap_path).iloc[:-2].to_csv(dataset.market_cap_path, index=False)

        # When / Then
        with pytest.raises(ValueError, match="공개 지연 허용치"):
            load_onchain(dataset)

    def test_중간에서_어긋나면_멈춘다(self, tmp_path: Path) -> None:
        """
        목적: 끝이 아닌 자리에서 날짜가 어긋나면 계산하지 않음을 고정한다 — 다른 날의 값끼리 나누면 예외 없이 틀린다.

        Given: 시가총액의 한가운데 하루가 빠진 입력
        When: 온체인 계열을 읽는다
        Then: ValueError
        """
        # Given
        dataset = _dataset(tmp_path)
        market_cap = pd.read_csv(dataset.market_cap_path)
        market_cap.drop(index=len(market_cap) // 2).to_csv(dataset.market_cap_path, index=False)

        # When / Then
        with pytest.raises(ValueError, match="끝이 아닌 자리"):
            load_onchain(dataset)

    @staticmethod
    def _shorten_onchain(dataset: Dataset, days: int) -> None:
        """두 온체인 파일을 함께 끝에서 `days` 일 자른다 — 시세만 새롭고 온체인은 묵은 상태를 만든다."""
        for path in (dataset.mvrv_path, dataset.market_cap_path):
            pd.read_csv(path).iloc[:-days].to_csv(path, index=False)

    def test_시세보다_하루_짧은_온체인은_받고_요약에_센다(self, tmp_path: Path) -> None:
        """
        목적: 온체인이 시세보다 공개 지연 허용치(하루)만큼 짧으면 측정이 멈추지 않고, 그 날 수가 요약에 남음을 고정한다.

        Given: 두 온체인 파일이 함께 시세보다 하루 짧은 입력
        When: 측정을 돌린다
        Then: 요약의 온체인 칸에 값이 없는 시세 날 1 · 두 파일 사이에서 뺀 날 0 이 적힌다
        """
        # Given
        dataset = _dataset(tmp_path)
        self._shorten_onchain(dataset, 1)

        # When
        outputs = run_study((dataset,), repeats=TEST_REPEATS, seed=0)

        # Then
        onchain = outputs.summary[KEY_DATASETS][0][KEY_ONCHAIN]
        assert onchain[KEY_MISSING_PRICE_DAYS] == 1
        assert onchain[KEY_DROPPED_TAIL_DAYS] == 0

    def test_시세보다_크게_짧은_온체인은_멈춘다(self, tmp_path: Path) -> None:
        """
        목적: 묵은 온체인 파일이 새 시세 옆에 남으면 멈춤을 고정한다 — 빈칸으로 두면 그 사이의 온체인 돌파가 예외 없이 사라진다.

        수집 스크립트는 시세를 먼저 저장하므로, 온체인 수집이 실패하면 이 상태가 된다.

        Given: 두 온체인 파일이 함께 시세보다 이틀 짧은 입력 (허용치 하루)
        When: 측정을 돌린다
        Then: ValueError
        """
        # Given
        dataset = _dataset(tmp_path)
        self._shorten_onchain(dataset, 2)

        # When / Then
        with pytest.raises(ValueError, match="온체인 계열이 시세의 거래일을 덮지 못합니다"):
            run_study((dataset,), repeats=TEST_REPEATS, seed=0)

    def test_온체인이_시세의_중간_하루를_비우면_멈춘다(self, tmp_path: Path) -> None:
        """
        목적: 빈 날이 하루여도 끝이 아닌 자리면 멈춤을 고정한다 — 공개 지연은 끝에서만 생긴다.

        두 온체인 파일이 같은 날을 함께 빠뜨리면 두 파일 사이의 검사(`load_onchain`)는 통과하므로, 시세와의 사이에서 잡는다.

        Given: 두 온체인 파일이 시세 한가운데의 같은 하루를 함께 빠뜨린 입력
        When: 측정을 돌린다
        Then: ValueError
        """
        # Given
        dataset = _dataset(tmp_path)
        middle = pd.read_csv(dataset.mvrv_path)[COL_DATE].iloc[-400]
        for path in (dataset.mvrv_path, dataset.market_cap_path):
            series = pd.read_csv(path)
            series[series[COL_DATE] != middle].to_csv(path, index=False)

        # When / Then
        with pytest.raises(ValueError, match="온체인 계열이 시세의 거래일을 덮지 못합니다"):
            run_study((dataset,), repeats=TEST_REPEATS, seed=0)


class TestIndicatorDisplay:
    """2단계 표시용 표"""

    def test_지표통계는_한글_헤더다(self, outputs: StudyOutputs) -> None:
        """
        목적: 2단계 표의 영문 토큰이 CSV 로 나가지 않음을 고정한다 (내부/출력 분리).

        Given: 표시용 지표통계
        When: 헤더를 본다
        Then: 신호 · 뜻 · 사이클 수 · 기준선 컬럼이 한글이다
        """
        table = display_tables(outputs)["indicator_statistics"]

        assert {"지표 신호", "책이 붙인 뜻", "보유(개월)", "사이클 수", "기준선 평균(%)"} <= set(table.columns)

    def test_지표_값은_네_자리로_반올림한다(self, outputs: StudyOutputs) -> None:
        """
        목적: 지표 값의 부동소수점 잡음이 CSV 로 나가지 않음을 고정한다 — 판정은 반올림 «전» 값으로 이미 끝났다.

        Given: 표시용 지표신호
        When: 판정 값을 본다
        Then: 소수 4자리를 넘지 않는다
        """
        values = display_tables(outputs)["indicator_signals"]["판정 값"].to_numpy(dtype=float)

        np.testing.assert_allclose(values, np.round(values, 4), atol=0.0)


class TestSplitTables:
    """3단계 혼합 분할 — 격자 크기 · 표본 보존 · 표시용 표 (결정 ㊺ ~ ㊼)"""

    def test_조합_수는_창과_문턱과_기한의_곱에_달력만을_더한_것이다(self, outputs: StudyOutputs) -> None:
        """
        목적: 결과를 보기 전에 정한 격자 크기를 고정한다 — 달력만은 창 없이 기한마다 한 조합이다.

        Given: 격자 상수
        When: 요약의 조합 수를 본다
        Then: 매수 (창 × 문턱 2 + 달력만) × 기한 · 매도 (창 × 문턱 2 + 달력만) × 기한
        """
        # Given
        buy_starts = len(SPLIT_BUY_START_MONTHS_HALVING) + len(SPLIT_BUY_START_MONTHS_HIGH)
        expected_buy = (buy_starts * 2 + 1) * len(SPLIT_BUY_LAST_DEADLINES)
        expected_sell = (len(SPLIT_SELL_START_MONTHS) * 2 + 1) * len(SPLIT_SELL_LAST_DEADLINES)

        # When
        rule = outputs.summary[KEY_SPLIT_RULE]

        # Then
        assert (rule[KEY_SPLIT_BUY][KEY_SPLIT_COMBINATIONS], rule[KEY_SPLIT_SELL][KEY_SPLIT_COMBINATIONS]) == (
            expected_buy,
            expected_sell,
        )

    def test_회차_포지션_조합_행_수가_격자와_같다(self, outputs: StudyOutputs) -> None:
        """
        목적: 표본 보존 — 체결 전 회차와 끝나지 않은 포지션도 행이 있다.

        Given: 합성 입력 한 대상 · 반감기 넷
        When: 세 표의 행 수를 본다
        Then: 회차 = (매수 + 매도) × 반감기 × 회차 수 · 포지션 = 매수 × 매도 × 반감기 · 조합 = 매수 × 매도
        """
        # Given
        rule = outputs.summary[KEY_SPLIT_RULE]
        buys, sells = rule[KEY_SPLIT_BUY][KEY_SPLIT_COMBINATIONS], rule[KEY_SPLIT_SELL][KEY_SPLIT_COMBINATIONS]

        # Then
        assert len(outputs.split_fills) == (buys + sells) * len(HALVINGS) * SPLIT_TRANCHES
        assert len(outputs.split_positions) == buys * sells * len(HALVINGS)
        assert len(outputs.split_combinations) == buys * sells

    def test_요약이_빠진_건수를_사유별로_센다(self, outputs: StudyOutputs) -> None:
        """
        목적: 몇 건이 왜 빠졌는지가 요약에 남는다 (절대 원칙 「표본 보존」).

        Given: 합성 입력
        When: 요약의 대상별 혼합 분할 건수를 본다
        Then: 행 수가 표와 같고, 사유별 건수의 합이 사유가 붙은 행의 수와 같다
        """
        # When
        counts = outputs.summary[KEY_DATASETS][0][KEY_SPLIT]

        # Then
        fills, positions = outputs.split_fills, outputs.split_positions
        assert counts[KEY_SPLIT_FILL_COUNT] == len(fills)
        assert counts[KEY_SPLIT_POSITION_COUNT] == len(positions)
        assert sum(counts[KEY_SPLIT_UNFILLED].values()) == int((fills[COL_EXCLUDED_REASON] != REASON_NONE).sum())
        assert sum(counts[KEY_SPLIT_UNFINISHED].values()) == int((positions[COL_EXCLUDED_REASON] != REASON_NONE).sum())

    def test_마지막_반감기의_포지션은_끝나지_않는다(self, outputs: StudyOutputs) -> None:
        """
        목적: 다음 반감기가 목록에 없으면 매도 회차가 정의되지 않는다 — 수익률을 0 으로 채우지 않는다.

        Given: 합성 입력
        When: 마지막 반감기의 포지션을 본다
        Then: 전부 사유가 있고 수익률이 비었다
        """
        # When
        last = outputs.split_positions[outputs.split_positions[COL_HALVING] == HALVINGS[-1].label]

        # Then
        assert (last[COL_EXCLUDED_REASON] != REASON_NONE).all()
        assert last[COL_POSITION_RETURN].isna().all()

    def test_표시용_표는_한글_헤더와_사이클별_가로_칸이다(self, outputs: StudyOutputs) -> None:
        """
        목적: 영문 토큰이 CSV 로 나가지 않고, 조합 표의 사이클별 칸이 반감기 목록에서 만들어진다.

        Given: 표시용 세 표
        When: 헤더를 본다
        Then: 회차 · 포지션 표의 한글 헤더와 반감기마다 「수익률(%)」 · 「평균 단가 대비 최악(%)」 칸이 있다
        """
        # When
        tables = display_tables(outputs)

        # Then
        assert {"매수 · 매도", "회차", "회차 체결일", "계기", "체결 전날 MVRV"} <= set(tables["split_fills"].columns)
        assert {"매수 문턱", "매도 문턱", "평균 매수가", "평균 단가 대비 최악(%)"} <= set(tables["split_positions"].columns)
        for halving in HALVINGS:
            assert f"{halving.label} 수익률(%)" in tables["split_combinations"].columns
            assert f"{halving.label} 평균 단가 대비 최악(%)" in tables["split_combinations"].columns

    def test_평균_단가는_가격_자릿수로_수익률은_백분율로_낸다(self, outputs: StudyOutputs) -> None:
        """
        목적: 계산값인 평균 단가의 잡음 자리를 자르고, 비율을 백분율로 바꾼다.

        Given: 포지션 표 (원래 값과 표시용)
        When: 평균 매수가와 수익률을 본다
        Then: 평균 매수가는 소수 4자리를 넘지 않고, 수익률은 원래 값 × 100 을 2자리로 반올림한 것이다
        """
        # When
        table = display_tables(outputs)["split_positions"]

        # Then
        prices = table["평균 매수가"].dropna().to_numpy(dtype=float)
        np.testing.assert_allclose(prices, np.round(prices, PRICE_DECIMALS), atol=0.0)
        expected = (outputs.split_positions[COL_POSITION_RETURN] * 100.0).round(2)
        pd.testing.assert_series_equal(table["수익률(%)"], expected, check_names=False)


class TestGridBaseline:
    """3단계 격자 중 같은 사이클에 파는 칸의 집계와 같은 보유의 기준선 (결정 ㊶)"""

    def test_같은_사이클에_파는_칸마다_한_행이고_보유는_청산_빼기_진입이다(self, outputs: StudyOutputs) -> None:
        """
        목적: 청산 개월 > 진입 개월인 칸이 빠짐없이 한 번씩 나오고, 기준선의 보유가 그 차이임을 고정한다.

        Given: 합성 입력의 측정 결과
        When: 격자기준선 표의 칸을 본다
        Then: (진입, 청산) 쌍이 격자의 「청산 > 진입」 쌍과 같고, 보유 = 청산 − 진입 이며, 보유가 3 ~ 45개월 3개월 간격이다
        """
        # Given
        table = outputs.grid_baseline

        # When
        cells = list(zip(table[COL_ENTRY_MONTHS], table[COL_EXIT_MONTHS], strict=True))

        # Then
        assert sorted(cells) == sorted(
            (entry, exit_) for entry in ENTRY_MONTHS for exit_ in EXIT_MONTHS if exit_ > entry
        )
        assert (table[COL_HOLD_MONTHS] == table[COL_EXIT_MONTHS] - table[COL_ENTRY_MONTHS]).all()
        assert sorted(set(table[COL_HOLD_MONTHS])) == list(range(3, 46, 3)) == list(GRID_BASELINE_HOLD_MONTHS)

    def test_신호는_직접_센_진입_수이고_표본과_제외의_합이다(self, outputs: StudyOutputs, synthetic_dataset: Dataset) -> None:
        """
        목적: 청산 시점 전에 다음 반감기가 오거나 데이터가 끝난 진입이 제외로 세어지고 사라지지 않음을 고정한다 (표본 보존).

        Given: 합성 시세와 그 측정 결과
        When: 칸마다 신호 · 표본 · 제외를 반감기 날짜와 달력월로 직접 센 값과 견준다
        Then: 신호와 표본이 같고, 신호 = 표본 + 제외 이며, 제외가 있는 칸이 하나 이상이다
        """
        # Given
        expected = _expected_same_cycle_cells(load_dataset(synthetic_dataset).frame)
        table = outputs.grid_baseline

        # When / Then
        for _, row in table.iterrows():
            signals, returns = expected[(int(row[COL_ENTRY_MONTHS]), int(row[COL_EXIT_MONTHS]))]
            assert row[COL_SIGNAL_COUNT] == signals
            assert row[COL_SAMPLE_COUNT] == len(returns)
        assert (table[COL_SIGNAL_COUNT] == table[COL_SAMPLE_COUNT] + table[COL_EXCLUDED_COUNT]).all()
        assert table[COL_EXCLUDED_COUNT].sum() > 0

    def test_칸의_평균과_오른_비율은_청산_종가_나누기_진입_종가다(self, outputs: StudyOutputs, synthetic_dataset: Dataset) -> None:
        """
        목적: 칸 값이 반감기일 + 달력월 날의 종가 비율임을 고정한다 — 3단계 일정을 측정 수익률 함수에 처음 넘긴다 (산식 고정).

        Given: 합성 시세에서 칸마다 직접 낸 수익률
        When: 격자기준선 표의 평균 · 오른 비율과 견준다
        Then: 유효 표본이 있는 칸마다 같다
        """
        # Given
        expected = _expected_same_cycle_cells(load_dataset(synthetic_dataset).frame)

        # When / Then
        checked = 0
        for _, row in outputs.grid_baseline.iterrows():
            _, returns = expected[(int(row[COL_ENTRY_MONTHS]), int(row[COL_EXIT_MONTHS]))]
            if not returns:
                continue
            assert row[COL_MEAN] == pytest.approx(float(np.mean(returns)), abs=1e-12)
            assert row[COL_WIN_RATE] == pytest.approx(float(np.mean([value > 0 for value in returns])), abs=1e-12)
            checked += 1
        assert checked > 0

    def test_보유_3_6_12개월의_기준선은_1단계_기준선과_같다(self, outputs: StudyOutputs) -> None:
        """
        목적: 같은 모집단(첫 반감기부터 매일 진입)과 같은 청산 규칙을 씀을 고정한다 (결정 ⑬ · ㊶).

        Given: 격자기준선 표와 1단계 excess 표
        When: 보유 3 · 6 · 12개월 칸의 기준선 표본 · 평균 · 오른 비율을 견준다
        Then: 같다
        """
        # Given
        columns = [f"{column}{BASELINE_SUFFIX}" for column in (COL_SAMPLE_COUNT, COL_MEAN, COL_WIN_RATE)]
        stage_one = outputs.excess.groupby(COL_HOLD_MONTHS)[columns].first()
        rows = outputs.grid_baseline[outputs.grid_baseline[COL_HOLD_MONTHS].isin(HOLD_MONTHS)]

        # When / Then
        assert set(rows[COL_HOLD_MONTHS]) == set(HOLD_MONTHS)
        for _, row in rows.iterrows():
            for column in columns:
                assert row[column] == pytest.approx(stage_one.loc[row[COL_HOLD_MONTHS], column], abs=1e-12)

    def test_가장_긴_보유의_기준선_표본은_청산일이_데이터_안인_날_수다(self, outputs: StudyOutputs, synthetic_dataset: Dataset) -> None:
        """
        목적: 1단계에 없던 긴 보유의 기준선이 첫 반감기부터 매일 진입해 청산일이 데이터 안인 날만 셈을 고정한다.

        Given: 합성 시세
        When: 가장 긴 보유 칸의 기준선 표본을 직접 센 값과 견준다
        Then: 같다
        """
        # Given
        last_day = load_dataset(synthetic_dataset).frame[COL_DATE].iloc[-1]
        longest = max(GRID_BASELINE_HOLD_MONTHS)
        days = pd.date_range(HALVINGS[0].day, last_day, freq="D")
        expected = sum(1 for day in days if day + pd.DateOffset(months=longest) <= last_day)

        # When
        rows = outputs.grid_baseline[outputs.grid_baseline[COL_HOLD_MONTHS] == longest]

        # Then
        assert len(rows) > 0
        assert (rows[f"{COL_SAMPLE_COUNT}{BASELINE_SUFFIX}"] == expected).all()

    def test_요약에_기준선_보유_목록과_행_수가_실린다(self, outputs: StudyOutputs) -> None:
        """
        목적: 무엇을 어떤 보유로 쟀는지가 요약에 남음을 고정한다.

        Given: 측정 요약
        When: 기준선 보유 목록과 행 수를 본다
        Then: 보유 목록이 격자에서 유도한 값이고 행 수가 표의 행 수다
        """
        assert outputs.summary[KEY_GRID_BASELINE_HOLD_MONTHS] == list(GRID_BASELINE_HOLD_MONTHS)
        assert outputs.summary[KEY_ROW_COUNTS][GRID_BASELINE_FILENAME] == len(outputs.grid_baseline)

    def test_표시용_표는_성적표와_같은_식별_헤더와_백분율이다(self, outputs: StudyOutputs) -> None:
        """
        목적: 성적표와 같은 헤더로 이어 볼 수 있고 비율이 백분율로 나감을 고정한다 (내부/출력 분리).

        Given: 격자기준선 표
        When: 표시용으로 바꾼다
        Then: 앞 다섯 헤더가 종목 · 진입 · 청산 · 방향 · 보유이고, 평균이 비율 × 100 (2자리)이다
        """
        # When
        table = display_tables(outputs)["grid_baseline"]

        # Then
        assert list(table.columns[:5]) == ["종목", "반감기 뒤 진입(개월)", "반감기 뒤 청산(개월)", "방향", "보유(개월)"]
        assert {"평균(%)", "기준선 평균(%)", "오른 비율 차이(%p)"} <= set(table.columns)
        np.testing.assert_allclose(
            table["평균(%)"].to_numpy(dtype=float),
            (outputs.grid_baseline[COL_MEAN] * 100).round(2).to_numpy(dtype=float),
            atol=1e-9,
        )

    def test_유효_표본이_없는_칸도_행이_남고_지표는_빈칸이다(self) -> None:
        """
        목적: 진입이 아직 없거나 전부 제외된 칸이 사라지거나 0 으로 채워지지 않음을 고정한다 (측정의 원칙 17).

        Given: 첫 반감기 뒤 7개월에서 끝나는 합성 시세 — 대부분의 칸은 진입이 없거나 청산이 데이터 뒤다
        When: 격자기준선 표를 낸다
        Then: 칸이 전부 남고, 표본 0 인 칸은 평균 · 기준선 평균 · 비중첩이 비며, 신호 0 인 칸과 전부 제외된 칸이 둘 다 있다
        """
        # Given
        market = _market()
        frame = market[market[COL_DATE] <= pd.Timestamp("2013-06-30")].reset_index(drop=True)

        # When
        table = grid_baseline_table(frame, repeats=TEST_REPEATS, seed=0)

        # Then
        empty = table[table[COL_SAMPLE_COUNT] == 0]
        assert len(table) == sum(1 for entry in ENTRY_MONTHS for exit_ in EXIT_MONTHS if exit_ > entry)
        assert (table[COL_SIGNAL_COUNT] == table[COL_SAMPLE_COUNT] + table[COL_EXCLUDED_COUNT]).all()
        assert empty[COL_MEAN].isna().all()
        assert empty[COL_NON_OVERLAPPING].isna().all()
        assert (empty[COL_SIGNAL_COUNT] == 0).any()
        assert ((empty[COL_SIGNAL_COUNT] > 0) & (empty[COL_EXCLUDED_COUNT] == empty[COL_SIGNAL_COUNT])).any()
        longest = table[table[COL_HOLD_MONTHS] == max(GRID_BASELINE_HOLD_MONTHS)]
        assert (longest[f"{COL_SAMPLE_COUNT}{BASELINE_SUFFIX}"] == 0).all()
        assert longest[f"{COL_MEAN}{BASELINE_SUFFIX}"].isna().all()

    def test_진입일에_보유_개월을_더한_날이_청산일과_다르면_멈춘다(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        목적: 칸의 보유를 (청산 − 진입) 개월로 두는 전제가 깨지면 기준선을 다른 보유로 조용히 재지 않고 멈춤을 고정한다.

        Given: 두 번째 반감기를 7월 31일로 옮긴 반감기 목록 — 9개월 진입이 4월 30일로 당겨져, 보유 3개월을 더하면
            7월 30일인데 청산일(반감기일 + 12개월)은 7월 31일이다
        When: 격자기준선을 낸다
        Then: 내부 불변조건 위반으로 멈춘다
        """
        # Given
        moved = Halving(height=HALVINGS[1].height, block_time=datetime(2016, 7, 31, 16, 46, 13, tzinfo=UTC))
        monkeypatch.setattr(runner_module, "HALVINGS", (HALVINGS[0], moved, *HALVINGS[2:]))

        # When / Then
        with pytest.raises(RuntimeError, match="내부 불변조건 위반"):
            grid_baseline_table(_market(), repeats=TEST_REPEATS, seed=0)

    def test_29일_이후_반감기라도_격자가_긴_달만_지나면_멈추지_않는다(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        목적: 가드가 반감기일이라는 대리 조건이 아니라 등식 자체를 봄을 고정한다 — 3개월 간격 격자가 30일 이상인 달만
        지나면 반감기일이 30일이어도 전제가 성립하므로 측정을 멈추지 않는다.

        Given: 두 번째 반감기를 7월 30일로 옮긴 반감기 목록 — 격자가 7 · 10 · 1 · 4월만 지난다
        When: 격자기준선을 낸다
        Then: 멈추지 않고 칸이 전부 나온다
        """
        # Given
        moved = Halving(height=HALVINGS[1].height, block_time=datetime(2016, 7, 30, 16, 46, 13, tzinfo=UTC))
        monkeypatch.setattr(runner_module, "HALVINGS", (HALVINGS[0], moved, *HALVINGS[2:]))

        # When
        table = grid_baseline_table(_market(), repeats=TEST_REPEATS, seed=0)

        # Then
        assert len(table) == sum(1 for entry in ENTRY_MONTHS for exit_ in EXIT_MONTHS if exit_ > entry)
