"""반감기_사이클 체결 조립 — 일시 격자 · 확정 규칙(달력 매달 분할) · 하드포크 몫의 계약을 고정한다.

매매 산출물의 공통 컬럼·순서·값 형식은 `tests/test_output_contract.py` 가 매매법 전부에 한꺼번에 건다.
**여기서는 이 매매법만의 계약**을 본다.

| 무엇 | 왜 |
| --- | --- |
| 체결가 = 측정 시세의 종가 | 진입일 정의가 두 벌이 되거나 종가를 바꾸기 전 시세를 읽으면 다른 가격에 들어가는데 예외는 나지 않는다 |
| 일시 격자 전부 · 무손절 · 「위」 | 칸을 고르지 않는다(설계 결정 ㉞) · 진입가 % 손절선을 두지 않는다(결정 60) |
| 확정 규칙 행 = 포지션 성적 | 포지션 하나가 체결 한 건이다(결정 61). 값은 손절 표를 만든 바로 그 결과다 — 산식을 다시 쓰지 않는다 |
| 대상별 신호·제외·행 없음 건수 | 성적표에 `제외` 컬럼을 두지 않으므로 요약이 그 자리다 (표본 보존) |
| 하드포크 몫 | 원본가에 없는 몫을 체결 수익률에 섞지 않고 따로 잰다 (결정 ㊲) |

**확정 규칙의 판정(회차일 · 손절선 · 이탈일)은 새로 만들지 않는다** — 그 미래 참조 감시는 분할 모듈의 테스트
(`tests/test_studies_halving_cycle_split_rule.py`)가 갖고, 체결 조립은 그 결과를 행으로 옮길 뿐이다.
"""

from collections.abc import Callable
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
from verify_lab.execution.constants import (
    EXIT_GAP_STOP,
    EXIT_INTRADAY_STOP,
    EXIT_LIMIT,
    NO_STOP_LABEL,
    PERIOD_ALL,
    PERIODS,
)
from verify_lab.execution.run_summary import KEY_RULE
from verify_lab.measure.constants import COL_EXCLUDED_REASON, COL_EXIT_DATE, COL_FORWARD_RETURN, REASON_NONE
from verify_lab.measure.screening import DIRECTION_UP, SCREEN_EXCLUDED, SCREEN_NOT_JUDGED
from verify_lab.measure.statistics import COL_MEAN, COL_SAMPLE_COUNT, COL_WIN_RATE
from verify_lab.studies.halving_cycle.constants import (
    CALENDAR_SPLIT_STEP_MONTHS,
    CALENDAR_SPLITS,
    COL_ENTRY_MONTHS,
    COL_EXIT_MONTHS,
    COL_HALVING,
    DISPLAY_ENTRY_MONTHS,
    DISPLAY_EXIT_MONTHS,
    ENTRY_MONTHS,
    EXIT_MONTHS,
    HALVINGS,
    HARD_FORKS,
    PEAK_WINDOW_MONTHS,
    REASON_NO_NEXT_HALVING,
    STOP_METHOD_LOW_BREAK,
    CalendarSplit,
    Dataset,
    HardFork,
)
from verify_lab.studies.halving_cycle.halving_calendar import PositionSchedule, position_schedule
from verify_lab.studies.halving_cycle.hard_fork import hard_fork_share
from verify_lab.studies.halving_cycle.runner import StudyOutputs, load_dataset, run_study
from verify_lab.studies.halving_cycle.split_rule import calendar_split_grid
from verify_lab.studies.halving_cycle.trading import (
    KEY_EXCLUDED_BY_REASON,
    KEY_NOT_YET_COUNT,
    KEY_OUTSIDE_CYCLE_COUNT,
    KEY_SPLIT_TARGETS,
    KEY_STOP_SOLD_COUNT,
    KEY_TARGETS,
    TradingOutputs,
    run_halving_cycle_trading,
)

# 합성 시세 구간 — 네 반감기와 두 하드포크가 모두 시세 안에 든다
SYNTHETIC_START = "2012-01-01"
SYNTHETIC_END = "2025-12-31"

# 합성 시세를 만드는 난수 시드. **시드 없는 난수는 금지다**
SYNTHETIC_SEED = 20260930

# 일시 격자 행의 매매 방식. 손으로 박는다 (`tests/CLAUDE.md` 「픽스처가 코드와 같은 가정을 하면 …」)
LUMP_METHOD = "일시"

# 확정 규칙 행을 재는 폭 — **실제(매수 반감기 뒤 27 ~ 32개월 6회 · 매도 다음 반감기 뒤 9 ~ 18개월 10회)와 다르다.**
# 첫 회차가 매수 24 · 매도 10 이라, 개월 칸이 실제 첫 회차(27 · 9)를 박아 두면 걸린다. 마지막 매수(26)는
# 사이클 고점 창(24개월) 뒤라 손절선이 정의된다
SPLIT = CalendarSplit(name="가짜 분할", buy_tranches=3, buy_last_deadline=26, sell_tranches=2, sell_last_deadline=11)
SPLIT_FIRST_BUY_MONTHS = 24
SPLIT_FIRST_SELL_MONTHS = 10

# 저점 이탈이 실제로 걸리는 손으로 짠 시세 — 기본 100 에 몇 날만 심고 2026-12-31 까지 낸다. 시가는 종가 × 0.999,
# 저가는 종가 × 0.98 이다(`_dataset`).
# 첫 반감기(2012-11-28) 포지션은 고점 창 안 2013-12-01(150) · 그 뒤 최저 2014-06-01(종가 60 · 저가 58.8) — 손절선 58.8 이다 ·
# 매수 2014-11-30 · 12-31 · 2015-01-31(100) · 매수가 끝난 뒤 2015-03-10(종가 59.5 · 시가 59.4405 · 저가 58.31) — 시가는
# 손절선 위이고 장중에 닿아 그날 손절선 58.8 에 전량 판다. 무손절은 다음 반감기(2016-07-09) 뒤 2017-05-31 · 06-30(100)에 판다.
# 둘째 · 셋째 반감기 포지션은 손절선이 될 저점(2018-01-01 · 2021-12-01 의 60)을 심어 그 뒤 기본값(저가 98)이 닿지 않게 한다 —
# 심지 않으면 매일 같은 저가 98 이 손절선이 되고 감시 첫날 그 값에 닿는다.
# 넷째 반감기(2024-04-20) 포지션은 손절선 2025-06-01(저가 58.8) · 매수 2026-04-30 · 05-31 · 06-30(100) · 2026-08-10(59.5)
# 장중 이탈 — **다음 반감기가 반감기 목록에 없어 무손절은 끝나지 않았는데 저점 이탈은 끝났다.**
# 하루 등락은 비트코인 이상치 문턱(75%) 안이다
FLAT_BASE = 100.0
FLAT_END = "2026-12-31"
FLAT_PLANTED = {
    "2013-12-01": 150.0,
    "2014-06-01": 60.0,
    "2015-03-10": 59.5,
    "2017-06-01": 150.0,
    "2018-01-01": 60.0,
    "2021-03-01": 150.0,
    "2021-12-01": 60.0,
    "2025-06-01": 60.0,
    "2026-08-10": 59.5,
}


def _random_closes(days: pd.DatetimeIndex) -> np.ndarray:
    """시드를 고정한 무작위 걷기 종가."""
    rng = np.random.default_rng(SYNTHETIC_SEED)

    return np.round(100.0 * np.cumprod(np.concatenate([[1.0], 1.0 + rng.normal(0.001, 0.02, len(days) - 1)])), 4)


def _flat_closes(days: pd.DatetimeIndex) -> np.ndarray:
    """기본 100 에 몇 날만 심은 종가."""
    planted = {pd.Timestamp(day): value for day, value in FLAT_PLANTED.items()}

    return np.array([planted.get(day, FLAT_BASE) for day in days], dtype=float)


def _dataset(
    directory: Path,
    closes_of: Callable[[pd.DatetimeIndex], np.ndarray] = _random_closes,
    end: str = SYNTHETIC_END,
) -> Dataset:
    """매일 거래하는 합성 시세와 기준가를 파일로 쓰고 대상 하나를 만든다."""
    days = pd.date_range(SYNTHETIC_START, end, freq="D")
    closes = closes_of(days)
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


@pytest.fixture(scope="module")
def flat_dataset(tmp_path_factory: pytest.TempPathFactory) -> Dataset:
    """저점 이탈이 걸리는 손으로 짠 시세."""
    return _dataset(tmp_path_factory.mktemp("halving_trading_flat"), _flat_closes, FLAT_END)


@pytest.fixture(scope="module")
def flat_trading(flat_dataset: Dataset) -> TradingOutputs:
    """손으로 짠 시세 · 실제와 다른 폭으로 돈 체결 결과."""
    return run_halving_cycle_trading((flat_dataset,), calendar_splits=(SPLIT,))


def _lump(table: pd.DataFrame) -> pd.DataFrame:
    """일시 격자 행만."""
    return table[table["매매 방식"] == LUMP_METHOD]


def _rule(table: pd.DataFrame, method: str) -> pd.DataFrame:
    """확정 규칙 행 중 한 손절 방식만."""
    return table[(table["매매 방식"] != LUMP_METHOD) & (table["손절선(%)"] == method)]


class TestGrid:
    """일시 격자 전부와 확정 규칙 행이 빠짐없이 나온다"""

    def test_성적표는_일시_격자_칸과_확정_규칙의_손절_방식마다_시기_다섯_행이다(self, trading: TradingOutputs) -> None:
        """
        목적: 진입 × 청산 × 시기 5행과, 폭 × 손절 방식(무손절 · 저점 이탈) × 시기 5행이 빠짐없이 나옴을 고정한다
            (측정의 원칙 17 — 체결이 없는 칸도 행이 있다)

        Given: 합성 입력의 체결 결과 (인자 없이 — 폭은 상수 그대로)
        When: 성적표 행 수를 본다
        Then: (일시 격자 칸 수 + 폭 수 × 2) × 시기 수다
        """
        expected = (len(ENTRY_MONTHS) * len(EXIT_MONTHS) + len(CALENDAR_SPLITS) * 2) * len(PERIODS)

        assert len(trading.performance) == expected
        assert len(_lump(trading.performance)) == len(ENTRY_MONTHS) * len(EXIT_MONTHS) * len(PERIODS)

    def test_방향은_위_하나이고_일시_격자는_무손절_한_종이다(self, trading: TradingOutputs) -> None:
        """
        목적: 결정 ⑰ · 60 을 고정한다 — 방향은 하나, 일시 격자에 진입가 % 손절선이 없다

        Given: 성적표와 거래내역
        When: 방향과 일시 격자의 손절선 값을 모은다
        Then: 방향은 「위」 하나이고 요약의 방향도 「위」 한 값(중간선거_사이클과 같은 문자열)이며, 일시 격자의 손절선은
            `무손절` 하나다
        """
        for table in (trading.performance, trading.trades):
            assert set(table["방향"]) == {DIRECTION_UP}
            assert set(_lump(table)["손절선(%)"]) == {NO_STOP_LABEL}
        assert trading.summary[KEY_RULE]["direction"] == DIRECTION_UP

    def test_일시_격자를_아래로_걸면_체결이_멈춘다(self, dataset: Dataset, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        목적: 확정 규칙은 사는 매매라 「위」로만 잰다 — 일시 격자만 아래로 걸면 한 성적표와 요약의 방향 한 칸에 방향이
            둘이 되므로, 산출물을 내지 않고 멈춤을 고정한다

        Given: 거는 방향 상수를 「아래」로 바꾼다
        When: 체결을 돈다
        Then: RuntimeError 가 발생하고 메시지가 그 상수를 가리킨다
        """
        # Given
        monkeypatch.setattr("verify_lab.studies.halving_cycle.trading.BET_DOWN", True)

        # When / Then
        with pytest.raises(RuntimeError, match="BET_DOWN"):
            run_halving_cycle_trading((dataset,))

    def test_거래내역의_일시_격자는_유효_일정마다_한_줄이다(self, trading: TradingOutputs, schedule: PositionSchedule) -> None:
        """
        목적: 청산일이 정해진 일정만 체결됨을 고정한다 (표본 보존).

        Given: 체결 결과와 같은 시세로 만든 일정
        When: 거래내역의 일시 격자 행 수를 본다
        Then: 유효 일정 수다
        """
        valid = int((schedule.schedule[COL_EXCLUDED_REASON] == REASON_NONE).sum())

        assert valid > 0
        assert len(_lump(trading.trades)) == valid


class TestFillPrice:
    """체결은 측정 시세의 종가로 들어가고 나온다"""

    def test_무손절_체결은_측정_시세의_종가로_들어가고_나온다(self, trading: TradingOutputs, frame: pd.DataFrame) -> None:
        """
        목적: 체결이 측정과 같은 시세(종가 대체 뒤)를 읽음을 고정한다 — 무손절은 청산일 종가로 나간다.

        Given: 일시 격자 체결(무손절)과 체결이 읽는 시세
        When: 진입일 · 청산일의 종가를 시세에서 찾는다
        Then: 진입가 · 청산가 · 수익률이 그 종가로 계산한 값과 같다
        """
        # Given
        trades = _lump(trading.trades)
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

        Given: 일시 격자 체결(무손절)과 1단계 진입내역(유효 행)
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
        joined = _lump(trading.trades).merge(measured, on=["반감기", "진입일", "청산일"], how="inner")

        # Then
        assert not joined.empty, "1단계와 날짜가 같은 체결이 없어 계약을 검사하지 못했습니다"
        np.testing.assert_allclose(joined["수익률(%)"], (joined[COL_FORWARD_RETURN] * 100).round(2), atol=0.01)

    def test_같은_사이클_칸의_격자기준선은_성적표의_무손절_전체_행과_같다(self, trading: TradingOutputs, study: StudyOutputs) -> None:
        """
        목적: 격자기준선의 칸 값이 곧 무손절 체결임을 고정한다 — 측정은 칸을 종가 ÷ 종가로 따로 재므로, 체결 쪽의 칸
        선택이나 가격 규칙이 한쪽만 바뀌면 두 표가 같은 칸에서 어긋나는데 예외는 나지 않는다.

        Given: 같은 합성 입력의 격자기준선(같은 사이클에 파는 칸)과 성적표의 일시 격자 · 전체 행
        When: (진입 개월, 청산 개월)로 맞댄다
        Then: 칸마다 표본 = 신호이고, 표본이 있는 칸은 평균 · 오른 비율이 평균(%) · 승률(%)과 같다 — 그런 칸이 하나 이상이다
        """
        # Given
        performance = trading.performance
        rows = _lump(performance[performance["시기"] == PERIOD_ALL])

        # When
        joined = study.grid_baseline.merge(
            rows,
            left_on=[COL_ENTRY_MONTHS, COL_EXIT_MONTHS],
            right_on=[DISPLAY_ENTRY_MONTHS, DISPLAY_EXIT_MONTHS],
            how="left",
            validate="one_to_one",
        )

        # Then
        np.testing.assert_array_equal(joined[COL_SAMPLE_COUNT].astype(int), joined["신호"].astype(int))
        sampled = joined[joined[COL_SAMPLE_COUNT] > 0]
        assert not sampled.empty, "표본이 있는 칸이 없어 값을 견주지 못했습니다"
        np.testing.assert_allclose(sampled[COL_MEAN] * 100, sampled["평균(%)"], atol=0.01)
        np.testing.assert_allclose(sampled[COL_WIN_RATE] * 100, sampled["승률(%)"], atol=0.01)


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

        Given: 합성 입력의 일시 격자 거래내역 (두 실제 포크가 시세 안에 든다)
        When: 거래내역의 진입일 · 청산일 · 수익률로 산식을 다시 계산한다
        Then: 끝 칸과 같고, 포크를 품은 체결이 있다
        """
        # Given — 확정 규칙 행의 몫은 회차 칸 몫의 평균이라 이 산식이 아니다 (분할 모듈 테스트가 그 산식을 본다)
        trades = _lump(trading.trades)

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


class TestConfirmedRule:
    """확정 규칙(달력 매달 분할 + 저점 이탈) 행 — 포지션 하나가 체결 한 건이다 (설계 결정 61)"""

    def test_식별_칸은_폭_이름과_첫_회차_개월과_두_손절_방식이다(self, flat_trading: TradingOutputs) -> None:
        """
        목적: 확정 규칙 행을 일시 격자와 가르는 칸을 고정한다 — 개월 칸은 첫 회차라 일시 격자의 칸과 겹칠 수 있어
            `매매 방식` 이 갈라 준다

        Given: 실제와 다른 폭(첫 회차 매수 24 · 매도 10)으로 돈 결과
        When: 확정 규칙 행의 식별 칸을 모은다
        Then: 매매 방식은 폭 이름 · 개월 칸은 24 · 10 · 손절선은 무손절 · 저점 이탈 둘이다
        """
        # Given / When
        for table in (flat_trading.performance, flat_trading.trades):
            rule = table[table["매매 방식"] != LUMP_METHOD]

            # Then
            assert set(rule["매매 방식"]) == {SPLIT.name}
            assert set(rule[DISPLAY_ENTRY_MONTHS]) == {SPLIT_FIRST_BUY_MONTHS}
            assert set(rule[DISPLAY_EXIT_MONTHS]) == {SPLIT_FIRST_SELL_MONTHS}
            assert set(rule["손절선(%)"]) == {NO_STOP_LABEL, STOP_METHOD_LOW_BREAK}

    def test_이탈한_포지션의_저점_이탈_행은_이탈일에_손절선_가격으로_남은_보유를_판_체결이다(self, flat_trading: TradingOutputs) -> None:
        """
        목적: 산식 고정 — 거래내역 한 줄의 여덟 칸이 포지션 성적이다. 진입가는 평균 매수가, 청산가는 평균 매도가,
            보유 중 최악은 평균 단가 대비 최악(결정 ㊻)이고, 손절로 끝난 포지션은 이탈일 · 사유 「장중손절」이다(결정 64)

        Given: 첫 반감기 포지션 — 매수 2014-11-30 · 12-31 · 2015-01-31(100) · 손절선 58.8(2014-06-01 저가) ·
            2015-03-10 시가 59.4405 · 저가 58.31 — 장중에 닿는다. 손절로 나간 날은 체결가까지만 세 최악이 58.8 ÷ 100 − 1,
            무손절은 그날 저가 58.31 을 지나간다
        When: 그 포지션의 두 거래내역 행을 본다
        Then: 저점 이탈 — 2014-11-30 · 100 · 2015-03-10 · 100일 · 58.8 · −41.2% · −41.2% · 「장중손절」
            무손절 — 2017-06-30 · 943일 · 100 · 0.0% · −41.69% · 「기한청산」
        """
        # Given
        first = HALVINGS[0].label

        # When
        stopped = _rule(flat_trading.trades, STOP_METHOD_LOW_BREAK)
        plain = _rule(flat_trading.trades, NO_STOP_LABEL)
        stopped_row = stopped[stopped["반감기"] == first].iloc[0]
        plain_row = plain[plain["반감기"] == first].iloc[0]

        # Then
        assert (stopped_row["진입일"], stopped_row["청산일"], stopped_row["보유일"]) == ("2014-11-30", "2015-03-10", 100)
        assert stopped_row["진입가"] == pytest.approx(100.0, abs=0.01)
        assert stopped_row["청산가"] == pytest.approx(58.8, abs=0.01)
        assert stopped_row["수익률(%)"] == pytest.approx(-41.2, abs=0.01)
        assert stopped_row["보유 중 최악(%)"] == pytest.approx(-41.2, abs=0.01)
        assert stopped_row["청산 사유"] == EXIT_INTRADAY_STOP
        assert (plain_row["진입일"], plain_row["청산일"], plain_row["보유일"]) == ("2014-11-30", "2017-06-30", 943)
        assert plain_row["청산가"] == pytest.approx(100.0, abs=0.01)
        assert plain_row["수익률(%)"] == pytest.approx(0.0, abs=0.01)
        assert plain_row["보유 중 최악(%)"] == pytest.approx(-41.69, abs=0.01)
        assert plain_row["청산 사유"] == EXIT_LIMIT

    def test_전체_행만_끝난_포지션으로_판정한다(self, flat_trading: TradingOutputs) -> None:
        """
        목적: 확정 규칙도 일시 격자와 같은 게이트를 «전체 행 하나»로 받는다 — 판정과 집행이 같은 표에 있다

        Given: 끝난 포지션 셋(2012 · 2016 · 2020 반감기)의 저점 이탈 수익률 −41.2 · 0 · 0 %
        When: 저점 이탈 행의 시기별 판정을 본다
        Then: 전체 행 — 신호 3 · 평균 −13.73 · 「제외」. 나머지 네 행은 「판정 안 함」
        """
        # Given / When
        rows = _rule(flat_trading.performance, STOP_METHOD_LOW_BREAK).set_index("시기")

        # Then
        assert rows.loc[PERIOD_ALL, "신호"] == 3
        assert rows.loc[PERIOD_ALL, "평균(%)"] == pytest.approx(-13.73, abs=0.01)
        assert rows.loc[PERIOD_ALL, "1차 판정"] == SCREEN_EXCLUDED
        assert set(rows.drop(index=PERIOD_ALL)["1차 판정"]) == {SCREEN_NOT_JUDGED}

    def test_끝나지_않은_포지션은_거래내역에_없고_요약에_폭마다_사유별로_남는다(self, flat_trading: TradingOutputs) -> None:
        """
        목적: 표본 보존 — 무손절이 끝나지 않은 포지션은 체결이 아니지만 사라지지 않는다. 포지션을 한 번 세고 폭마다 적는다

        Given: 2024 반감기 포지션 — 다음 반감기가 반감기 목록에 없어 무손절이 끝나지 않았다
        When: 거래내역의 확정 규칙 행과 요약의 대상 기록을 본다
        Then: 거래내역 6행(끝난 포지션 3 × 손절 방식 2) · 요약 — 폭 하나, 포지션 4 = 끝남 3 + 제외 1 · 사유
            「다음 반감기가 반감기 목록에 없음」 1 · 저점 이탈로 판 포지션 2(2012 · 2024)
        """
        # Given / When
        rule_trades = flat_trading.trades[flat_trading.trades["매매 방식"] != LUMP_METHOD]
        record = flat_trading.summary[KEY_RULE][KEY_TARGETS][0]

        # Then
        assert len(rule_trades) == 6
        assert record[KEY_SPLIT_TARGETS] == [
            {
                "name": SPLIT.name,
                "signal_count": 4,
                "excluded_count": 1,
                "excluded_by_reason": {REASON_NO_NEXT_HALVING: 1},
                "stop_sold_count": 2,
            }
        ]

    def test_저점_이탈로_판_포지션은_장중손절로_세지고_표본에서_빠진_것은_요약이_센다(self, flat_trading: TradingOutputs) -> None:
        """
        목적: 저점 이탈 손절은 성적표의 갭손절 · 장중손절에 세진다 — 어느 손절인지는 `손절선(%)` 의 「저점 이탈」이 말한다.
            무손절이 끝나기 전에 이탈한 포지션은 거래내역에도 성적표에도 없다 — 그 이탈이 체결 산출물에 숫자로 남는 자리가
            요약의 폭별 기록임을 고정한다

        Given: 2012 포지션(2015-03-10 장중손절 · 표본에 듦)과 2024 포지션(2026-08-10 장중손절 · 무손절이 끝나지 않아 빠짐)
        When: 거래내역의 손절 청산 · 성적표의 저점 이탈 전체 행 · 요약의 폭별 저점 이탈 매도 수를 본다
        Then: 거래내역의 「장중손절」 청산은 1건(2012)이고 「갭손절」은 없다. 성적표 전체 행의 장중손절 1 · 갭손절 0 ·
            요약은 빠진 2024 까지 2 를 센다
        """
        # Given / When
        trades = flat_trading.trades
        intraday = trades[trades["청산 사유"] == EXIT_INTRADAY_STOP]
        record = flat_trading.summary[KEY_RULE][KEY_TARGETS][0][KEY_SPLIT_TARGETS][0]
        rows = _rule(flat_trading.performance, STOP_METHOD_LOW_BREAK).set_index("시기")

        # Then
        assert list(intraday["반감기"]) == [HALVINGS[0].label]
        assert set(intraday["손절선(%)"]) == {STOP_METHOD_LOW_BREAK}
        assert not (trades["청산 사유"] == EXIT_GAP_STOP).any()
        assert (rows.loc[PERIOD_ALL, "갭손절"], rows.loc[PERIOD_ALL, "장중손절"]) == (0, 1)
        assert record[KEY_STOP_SOLD_COUNT] == 2

    def test_두_손절_방식은_같은_포지션을_잰다(self, flat_trading: TradingOutputs, flat_dataset: Dataset) -> None:
        """
        목적: 「손절이 무엇을 막았는가」를 한 표에서 견주려면 두 손절 방식 행이 같은 포지션을 재야 한다 — 표본은 무손절
            포지션이 끝났는가로 정한다. 저점 이탈로 먼저 끝난 포지션도 무손절이 끝날 때까지 두 행 모두에서 빠진다
            (일시 격자가 예정 청산일로 표본을 정하는 것과 같다)

        Given: 2024 반감기 포지션 — 저점 이탈로는 2026-08-10 에 끝났지만 무손절은 다음 반감기가 없어 끝나지 않았다
            (그런 포지션이 실제로 생겼는지 분할 모듈의 결과로 먼저 확인한다)
        When: 두 손절 방식의 거래내역과 전체 행을 본다
        Then: 두 방식 모두 신호 3 · 거래내역의 반감기가 같은 셋이고 2024 행이 없다
        """
        # Given
        grid = calendar_split_grid(
            load_dataset(flat_dataset).frame,
            HALVINGS,
            (SPLIT,),
            step_months=CALENDAR_SPLIT_STEP_MONTHS,
            peak_window_months=PEAK_WINDOW_MONTHS,
            forks=HARD_FORKS,
        )
        last = HALVINGS[-1]
        early = [outcome for outcome in grid.outcomes if outcome.halving == last]
        assert {(outcome.method, outcome.result.reason, outcome.exit_reason) for outcome in early} == {
            (NO_STOP_LABEL, REASON_NO_NEXT_HALVING, None),
            (STOP_METHOD_LOW_BREAK, REASON_NONE, EXIT_INTRADAY_STOP),
        }, "저점 이탈로만 먼저 끝난 포지션이 없어 계약을 검사하지 못했습니다"

        # When
        halvings = {
            method: set(_rule(flat_trading.trades, method)["반감기"]) for method in (NO_STOP_LABEL, STOP_METHOD_LOW_BREAK)
        }
        signals = {
            method: _rule(flat_trading.performance, method).set_index("시기").loc[PERIOD_ALL, "신호"]
            for method in (NO_STOP_LABEL, STOP_METHOD_LOW_BREAK)
        }

        # Then
        assert halvings[NO_STOP_LABEL] == halvings[STOP_METHOD_LOW_BREAK]
        assert last.label not in halvings[STOP_METHOD_LOW_BREAK]
        assert signals == {NO_STOP_LABEL: 3, STOP_METHOD_LOW_BREAK: 3}

    def test_인자_없이_돈_확정_규칙_행은_분할_모듈의_포지션_결과다(self, trading: TradingOutputs, frame: pd.DataFrame) -> None:
        """
        목적: 기본 실행(실제 폭)의 확정 규칙 행이 손절 표를 만든 바로 그 결과임을 고정한다 — 체결 조립이 산식을 다시
            쓰지 않는다 (절대 원칙 5)

        Given: 인자 없이 돈 결과와, 같은 시세 · 같은 인자로 낸 달력 매달 분할 결과
        When: 끝난 포지션마다 (반감기, 손절 방식)으로 맞댄다
        Then: 진입일 = 첫 매수일 · 진입가 = 평균 매수가 · 청산일 = 마지막 매도일 · 청산가 = 평균 매도가 · 수익률 ·
            보유 중 최악 = 평균 단가 대비 최악 · 하드포크 몫이 같고, 그런 포지션이 하나 이상이다
        """
        # Given
        grid = calendar_split_grid(
            frame,
            HALVINGS,
            CALENDAR_SPLITS,
            step_months=CALENDAR_SPLIT_STEP_MONTHS,
            peak_window_months=PEAK_WINDOW_MONTHS,
            forks=HARD_FORKS,
        )
        rule = trading.trades[trading.trades["매매 방식"] != LUMP_METHOD]

        # When — 표본은 무손절 포지션이 끝났는가로 정한다 (체결 조립과 같은 규칙 · 설계 결정 61)
        judged = {
            outcome.halving
            for outcome in grid.outcomes
            if outcome.method == NO_STOP_LABEL and outcome.result.reason == REASON_NONE
        }
        chosen = [outcome for outcome in grid.outcomes if outcome.halving in judged]

        # Then
        assert chosen, "끝난 포지션이 없어 계약을 검사하지 못했습니다"
        assert len(rule) == len(chosen)
        for outcome in chosen:
            matched = rule[(rule["반감기"] == outcome.halving.label) & (rule["손절선(%)"] == outcome.method)]
            assert len(matched) == 1
            row = matched.iloc[0]
            result = outcome.result
            assert result.first_buy_day is not None and result.last_sell_day is not None
            assert result.avg_buy_price is not None and result.avg_sell_price is not None
            assert result.return_rate is not None and result.worst_vs_cost is not None
            assert outcome.fork_share is not None
            assert row["진입일"] == result.first_buy_day.strftime("%Y-%m-%d")
            assert row["청산일"] == result.last_sell_day.strftime("%Y-%m-%d")
            assert row["진입가"] == pytest.approx(result.avg_buy_price, abs=0.01)
            assert row["청산가"] == pytest.approx(result.avg_sell_price, abs=0.01)
            assert row["수익률(%)"] == pytest.approx(result.return_rate * 100, abs=0.01)
            assert row["보유 중 최악(%)"] == pytest.approx(result.worst_vs_cost * 100, abs=0.01)
            assert row["하드포크 몫(%p)"] == pytest.approx(outcome.fork_share * 100, abs=0.01)
