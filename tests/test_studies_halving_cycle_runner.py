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
from verify_lab.execution.run_summary import KEY_ROW_COUNTS
from verify_lab.measure.constants import (
    COL_EXCLUDED_COUNT,
    COL_EXCLUDED_REASON,
    COL_SIGNAL_COUNT,
    REASON_NONE,
)
from verify_lab.measure.statistics import COL_MEAN, COL_SAMPLE_COUNT, COL_TEST_NOTE, NOTE_TOO_FEW_SAMPLES
from verify_lab.report.run_summary import KEY_TRACK
from verify_lab.studies.halving_cycle.constants import (
    BASELINE_SUFFIX,
    COL_BASELINE_NON_OVERLAPPING,
    COL_CALENDAR_YEAR,
    COL_ENTRY_MONTHS,
    COL_HOLD_MONTHS,
    COL_NON_OVERLAPPING,
    DATASETS,
    ENTRY_MONTHS,
    HALVINGS,
    HOLD_MONTHS,
    OUTPUT_FILES,
    TRACK_NAME,
    Dataset,
)
from verify_lab.studies.halving_cycle.runner import StudyOutputs, display_tables, run_study

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


def _dataset(directory: Path) -> Dataset:
    """합성 시세와 합성 기준가를 파일로 쓰고 대상 하나를 만든다."""
    market = _market()
    market.assign(**{COL_DATE: market[COL_DATE].dt.strftime("%Y-%m-%d")}).to_csv(
        directory / MARKET_FILE_TEMPLATE.format(ticker="SYN"), index=False
    )
    reference = _reference(market)
    reference_path = directory / "SYN_PriceUSD.csv"
    reference.assign(**{COL_DATE: reference[COL_DATE].dt.strftime("%Y-%m-%d")}).to_csv(reference_path, index=False)

    return Dataset(
        ticker="SYN",
        label="합성 비트코인",
        directory=directory,
        file_template=MARKET_FILE_TEMPLATE,
        reference_path=reference_path,
        price_decimals=PRICE_DECIMALS,
        is_judged=True,
    )


@pytest.fixture(scope="module")
def outputs(tmp_path_factory: pytest.TempPathFactory) -> StudyOutputs:
    """합성 입력으로 돈 측정 결과."""
    return run_study((_dataset(tmp_path_factory.mktemp("halving")),), repeats=TEST_REPEATS, seed=0)


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
        assert DATASETS[0].is_judged


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
