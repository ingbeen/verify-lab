"""반감기_사이클 체결 조립 — 진입 시점 × 청산 시점 격자 · 손절선 격자 · 하드포크 몫의 계약을 고정한다.

매매 산출물의 공통 컬럼·순서·값 형식은 `tests/test_output_contract.py` 가 매매법 전부에 한꺼번에 건다.
**여기서는 이 매매법만의 계약**을 본다.

| 무엇 | 왜 |
| --- | --- |
| 체결가 = 측정 시세의 종가 | 진입일 정의가 두 벌이 되거나 종가를 바꾸기 전 시세를 읽으면 다른 가격에 들어가는데 예외는 나지 않는다 |
| 격자 전부 · 「위」 | 칸과 손절선을 고르지 않는다(설계 결정 ㉞ · ㉟) — 고르는 것은 `규칙.md` 에서 한다 |
| 대상별 신호·제외·행 없음 건수 | 성적표에 `제외` 컬럼을 두지 않으므로 요약이 그 자리다 (표본 보존) |
| 하드포크 몫 | 원본가에 없는 몫을 체결 수익률에 섞지 않고 따로 잰다 (결정 ㊲) |
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
from verify_lab.execution.constants import NO_STOP_LABEL, PERIODS, stop_level_value
from verify_lab.execution.run_summary import KEY_RULE
from verify_lab.measure.constants import COL_EXCLUDED_REASON, COL_EXIT_DATE, COL_FORWARD_RETURN, REASON_NONE
from verify_lab.measure.screening import DIRECTION_UP
from verify_lab.studies.halving_cycle.constants import (
    COL_HALVING,
    ENTRY_MONTHS,
    EXIT_MONTHS,
    HALVINGS,
    HARD_FORKS,
    STOP_LEVELS,
    Dataset,
    HardFork,
)
from verify_lab.studies.halving_cycle.halving_calendar import PositionSchedule, position_schedule
from verify_lab.studies.halving_cycle.hard_fork import hard_fork_share
from verify_lab.studies.halving_cycle.runner import StudyOutputs, load_dataset, run_study
from verify_lab.studies.halving_cycle.trading import (
    KEY_EXCLUDED_BY_REASON,
    KEY_NOT_YET_COUNT,
    KEY_OUTSIDE_CYCLE_COUNT,
    KEY_TARGETS,
    TradingOutputs,
    run_halving_cycle_trading,
)

# 합성 시세 구간 — 네 반감기와 두 하드포크가 모두 시세 안에 든다
SYNTHETIC_START = "2012-01-01"
SYNTHETIC_END = "2025-12-31"

# 합성 시세를 만드는 난수 시드. **시드 없는 난수는 금지다**
SYNTHETIC_SEED = 20260930


def _dataset(directory: Path) -> Dataset:
    """매일 거래하는 합성 시세와 기준가를 파일로 쓰고 대상 하나를 만든다."""
    days = pd.date_range(SYNTHETIC_START, SYNTHETIC_END, freq="D")
    rng = np.random.default_rng(SYNTHETIC_SEED)
    closes = np.round(100.0 * np.cumprod(np.concatenate([[1.0], 1.0 + rng.normal(0.001, 0.02, len(days) - 1)])), 4)
    dates = days.strftime("%Y-%m-%d")

    pd.DataFrame(
        {
            COL_DATE: dates,
            COL_OPEN: np.round(closes * 0.999, 4),
            COL_HIGH: np.round(closes * 1.01, 4),
            COL_LOW: np.round(closes * 0.98, 4),
            COL_CLOSE: closes,
            COL_VOLUME: 1_000.0,
        }
    ).to_csv(directory / MARKET_FILE_TEMPLATE.format(ticker="SYN"), index=False)
    reference_path = directory / "SYN_PriceUSD.csv"
    pd.DataFrame({COL_DATE: dates, COL_VALUE: np.round(closes * 1.001, 4)}).to_csv(reference_path, index=False)

    # 온체인 두 계열은 측정(2단계)만 읽는다 — 이 파일의 대조 테스트가 측정을 함께 돌려 파일이 있어야 한다
    mvrv_path = directory / "SYN_CapMVRVCur.csv"
    pd.DataFrame({COL_DATE: dates, COL_VALUE: 2.0}).to_csv(mvrv_path, index=False)
    market_cap_path = directory / "SYN_CapMrktCurUSD.csv"
    pd.DataFrame({COL_DATE: dates, COL_VALUE: np.round(closes * 1e6, 0)}).to_csv(market_cap_path, index=False)

    return Dataset(
        ticker="SYN",
        label="합성 비트코인",
        directory=directory,
        file_template=MARKET_FILE_TEMPLATE,
        reference_path=reference_path,
        mvrv_path=mvrv_path,
        market_cap_path=market_cap_path,
        price_decimals=PRICE_DECIMALS,
        is_judged=True,
    )


@pytest.fixture(scope="module")
def dataset(tmp_path_factory: pytest.TempPathFactory) -> Dataset:
    """합성 대상."""
    return _dataset(tmp_path_factory.mktemp("halving_trading"))


@pytest.fixture(scope="module")
def trading(dataset: Dataset) -> TradingOutputs:
    """합성 입력으로 돈 체결 결과."""
    return run_halving_cycle_trading((dataset,))


@pytest.fixture(scope="module")
def study(dataset: Dataset) -> StudyOutputs:
    """같은 입력으로 돈 측정 결과 — 체결과 대조한다."""
    return run_study((dataset,), repeats=10, seed=0)


@pytest.fixture(scope="module")
def frame(dataset: Dataset) -> pd.DataFrame:
    """체결이 읽는 것과 같은 시세 — 거래량 0 인 날의 종가를 바꾼 뒤다."""
    return load_dataset(dataset).frame


@pytest.fixture(scope="module")
def schedule(frame: pd.DataFrame) -> PositionSchedule:
    """같은 시세로 만든 체결 일정 — 요약의 건수와 대조한다."""
    return position_schedule(pd.DatetimeIndex(frame[COL_DATE]), HALVINGS, ENTRY_MONTHS, EXIT_MONTHS)


def _no_stop(trades: pd.DataFrame) -> pd.DataFrame:
    """무손절 체결만."""
    return trades[trades["손절선(%)"] == NO_STOP_LABEL]


class TestGrid:
    """격자 전부가 빠짐없이 나온다"""

    def test_성적표는_칸마다_손절선마다_시기_다섯_행이다(self, trading: TradingOutputs) -> None:
        """
        목적: 진입 × 청산 × 손절선 × 시기 5행이 빠짐없이 나옴을 고정한다 (측정의 원칙 17 — 체결이 없는 칸도 행이 있다).

        Given: 합성 입력의 체결 결과
        When: 성적표 행 수를 본다
        Then: 칸 수 × 손절선 수 × 시기 수다
        """
        assert len(trading.performance) == len(ENTRY_MONTHS) * len(EXIT_MONTHS) * len(STOP_LEVELS) * len(PERIODS)

    def test_방향은_위_하나이고_손절선은_격자_전부다(self, trading: TradingOutputs) -> None:
        """
        목적: 결정 ⑰ · ㉟ 를 고정한다 — 방향은 하나, 손절선은 상수의 격자를 고르지 않고 전부 낸다.

        Given: 성적표와 거래내역
        When: 방향과 손절선 값을 모은다
        Then: 방향은 「위」 하나이고, 손절선은 격자의 표시값 전부다
        """
        expected_stops = {stop_level_value(level, measurable=True) for level in STOP_LEVELS}
        for table in (trading.performance, trading.trades):
            assert set(table["방향"]) == {DIRECTION_UP}
            assert set(table["손절선(%)"]) == expected_stops

    def test_거래내역은_유효_일정마다_손절선마다_한_줄이다(self, trading: TradingOutputs, schedule: PositionSchedule) -> None:
        """
        목적: 청산일이 정해진 일정만 체결되고, 손절선마다 한 번씩 체결됨을 고정한다 (표본 보존).

        Given: 체결 결과와 같은 시세로 만든 일정
        When: 거래내역 행 수를 본다
        Then: 유효 일정 수 × 손절선 수다
        """
        valid = int((schedule.schedule[COL_EXCLUDED_REASON] == REASON_NONE).sum())

        assert valid > 0
        assert len(trading.trades) == valid * len(STOP_LEVELS)


class TestFillPrice:
    """체결은 측정 시세의 종가로 들어가고 나온다"""

    def test_무손절_체결은_측정_시세의_종가로_들어가고_나온다(self, trading: TradingOutputs, frame: pd.DataFrame) -> None:
        """
        목적: 체결이 측정과 같은 시세(종가 대체 뒤)를 읽음을 고정한다 — 무손절은 청산일 종가로 나간다.

        Given: 무손절 체결과 체결이 읽는 시세
        When: 진입일 · 청산일의 종가를 시세에서 찾는다
        Then: 진입가 · 청산가 · 수익률이 그 종가로 계산한 값과 같다
        """
        # Given
        trades = _no_stop(trading.trades)
        closes = frame.set_index(COL_DATE)[COL_CLOSE]

        # When
        entry = closes.reindex(pd.to_datetime(trades["진입일"])).to_numpy()
        exit_ = closes.reindex(pd.to_datetime(trades["청산일"])).to_numpy()

        # Then
        np.testing.assert_allclose(trades["진입가"], np.round(entry, PRICE_DECIMALS), atol=0.01)
        np.testing.assert_allclose(trades["청산가"], np.round(exit_, PRICE_DECIMALS), atol=0.01)
        np.testing.assert_allclose(trades["수익률(%)"], np.round((exit_ / entry - 1.0) * 100, 2), atol=0.01)

    def test_1단계와_날짜가_같은_체결은_측정과_수익률이_같다(self, trading: TradingOutputs, study: StudyOutputs) -> None:
        """
        목적: 3단계 격자가 1단계 측정과 같은 날을 같은 값으로 잼을 고정한다 — 반감기 달력이 두 벌이 되지 않았다.

        Given: 무손절 체결과 1단계 진입내역(유효 행)
        When: (반감기, 진입일, 청산일)로 맞댄다
        Then: 겹치는 체결이 있고, 그 수익률이 측정 수익률과 같다
        """
        # Given
        measured = study.entries[study.entries[COL_EXCLUDED_REASON] == REASON_NONE].assign(
            **{
                "진입일": lambda table: table[COL_DATE].dt.strftime("%Y-%m-%d"),
                "청산일": lambda table: table[COL_EXIT_DATE].dt.strftime("%Y-%m-%d"),
                "반감기": lambda table: table[COL_HALVING],
            }
        )

        # When
        joined = _no_stop(trading.trades).merge(measured, on=["반감기", "진입일", "청산일"], how="inner")

        # Then
        assert not joined.empty, "1단계와 날짜가 같은 체결이 없어 계약을 검사하지 못했습니다"
        np.testing.assert_allclose(joined["수익률(%)"], (joined[COL_FORWARD_RETURN] * 100).round(2), atol=0.01)


class TestSummary:
    """대상별 신호 · 제외 · 행 없음 건수 — 성적표에 `제외` 가 없어 요약이 그 자리다"""

    def test_대상_기록이_일정의_건수와_같다(self, trading: TradingOutputs, schedule: PositionSchedule) -> None:
        """
        목적: 몇 건이 왜 빠졌는지가 요약에 남음을 고정한다 (절대 원칙 4 — 표본 보존).

        Given: 체결 요약과 같은 시세로 만든 일정
        When: 대상 기록을 본다
        Then: 신호 · 제외 · 사유별 제외 · 그 사이클에 없는 진입 · 아직 오지 않은 진입이 일정의 건수와 같다
        """
        # Given
        record = trading.summary[KEY_RULE][KEY_TARGETS][0]
        reasons = schedule.schedule[COL_EXCLUDED_REASON]

        # When / Then
        assert record["signal_count"] == len(schedule.schedule)
        assert record["excluded_count"] == int((reasons != REASON_NONE).sum())
        assert record[KEY_EXCLUDED_BY_REASON] == reasons[reasons != REASON_NONE].value_counts().to_dict()
        assert record[KEY_OUTSIDE_CYCLE_COUNT] == schedule.outside_cycle_count
        assert record[KEY_NOT_YET_COUNT] == schedule.not_yet_count


# 합성 하드포크 — **실제 값과 다르게 고른다** (`tests/CLAUDE.md` 「픽스처는 실제 쓰이는 값과 «다르게» 고른다」).
# 둘째는 포크일과 첫 시세일이 다르다 — 실제 BTG 가 그렇다
FORK_A = HardFork(
    name="AAA",
    height=1,
    block_time=datetime(2020, 3, 10, 12, 0, tzinfo=UTC),
    price_day=pd.Timestamp("2020-03-10"),
    coin_price=10.0,
    btc_price=100.0,
)
FORK_B = HardFork(
    name="BBB",
    height=2,
    block_time=datetime(2020, 6, 5, 1, 0, tzinfo=UTC),
    price_day=pd.Timestamp("2020-06-06"),
    coin_price=5.0,
    btc_price=200.0,
)


class TestHardForkShare:
    """하드포크 몫 = (Π(1 + 비율) − 1) × (1 + 체결 수익률) — 포크 코인을 첫 시세일에 팔아 BTC 를 더 샀다고 본다"""

    @pytest.mark.parametrize(
        ("entry", "exit_", "return_rate", "expected"),
        [
            ("2020-01-01", "2020-03-09", 0.2, 0.0),
            ("2020-01-01", "2020-04-01", 0.5, 0.1 * 1.5),
            ("2020-01-01", "2020-07-01", -0.2, (1.1 * 1.025 - 1.0) * 0.8),
            ("2020-03-10", "2020-04-01", 0.5, 0.0),
            ("2020-03-01", "2020-03-10", -0.1, 0.1 * 0.9),
        ],
        ids=["포크 전에 나감", "하나를 품음", "둘을 품음", "포크일에 진입", "포크일에 청산"],
    )
    def test_몫은_품은_포크의_비율과_체결_수익률로_정해진다(self, entry: str, exit_: str, return_rate: float, expected: float) -> None:
        """
        목적: 하드포크 몫의 산식과 「품었다」의 경계(진입일 < 포크일 ≤ 청산일)를 손으로 계산한 값으로 고정한다.

        진입가는 진입일 종가(다음날 00:00 UTC)라 **포크일에 진입하면 스냅샷 뒤**이고,
        청산은 청산일 종가라 **포크일에 청산하면 스냅샷 때 들고 있었다.**

        Args:
            entry: 진입일
            exit_: 청산일 (손절이면 손절일)
            return_rate: 체결 수익률
            expected: 기대 몫 (비율)

        Given: 비율 10% · 2.5% 인 합성 포크 둘
        When: 체결 하나의 몫을 구한다
        Then: 품은 포크만큼의 비율이 체결 수익률을 따라 불어난 값이다
        """
        share = hard_fork_share(pd.Timestamp(entry), pd.Timestamp(exit_), return_rate, (FORK_A, FORK_B))

        assert share == pytest.approx(expected, abs=1e-12)

    def test_거래내역의_몫은_체결마다_그_산식이다(self, trading: TradingOutputs) -> None:
        """
        목적: 체결이 실제 청산일(손절 포함)과 실제 체결 수익률로 몫을 잼을 고정한다.

        Given: 합성 입력의 거래내역 (두 실제 포크가 시세 안에 든다)
        When: 거래내역의 진입일 · 청산일 · 수익률로 산식을 다시 계산한다
        Then: 끝 칸과 같고, 포크를 품은 체결이 있다
        """
        # Given
        trades = trading.trades

        # When
        expected = [
            hard_fork_share(pd.Timestamp(entry), pd.Timestamp(exit_), rate / 100, HARD_FORKS) * 100
            for entry, exit_, rate in zip(trades["진입일"], trades["청산일"], trades["수익률(%)"], strict=True)
        ]

        # Then
        np.testing.assert_allclose(trades["하드포크 몫(%p)"], expected, atol=0.01)
        assert (trades["하드포크 몫(%p)"] > 0).any(), "포크를 품은 체결이 없어 계약을 검사하지 못했습니다"

    def test_잘못된_포크는_만들_수_없다(self) -> None:
        """
        목적: 시간대 없는 시각 · 0 이하 가격 · 포크일 앞의 첫 시세일을 거부함을 고정한다 (입력 검증).

        Given: 잘못된 값
        When: 하드포크를 만든다
        Then: ValueError 가 발생한다
        """
        with pytest.raises(ValueError, match="시간대"):
            HardFork("X", 1, datetime(2020, 1, 1), pd.Timestamp("2020-01-01"), 1.0, 1.0)
        with pytest.raises(ValueError, match="양수"):
            HardFork("X", 1, datetime(2020, 1, 1, tzinfo=UTC), pd.Timestamp("2020-01-01"), 0.0, 1.0)
        with pytest.raises(ValueError, match="첫 시세일"):
            HardFork("X", 1, datetime(2020, 1, 2, tzinfo=UTC), pd.Timestamp("2020-01-01"), 1.0, 1.0)
