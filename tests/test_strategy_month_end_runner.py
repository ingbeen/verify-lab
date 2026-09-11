"""코스닥 월말 매매의 손절 격자 조립을 고정한다.

**판정식은 이미 있다** — `strategy/trade_fill.simulate_scheduled_trade` 가 시가 → 장중 순서와
갭손절을 담당하고, `strategy/periods.period_rows` 가 구간별 성적을 낸다.
이 파일이 검사하는 것은 **그 둘을 조립하는 부분**이다.

고정하는 계약은 일곱이다.

- 손절선 격자는 **8종 + 무손절 = 9행**이다
- **12개월이 전부 나온다** — 신호가 있는 달만 고르지 않는다
- **두 방향이 모두 나온다** — 방향을 고르는 코드가 없다 (측정의 원칙 11)
- 무손절 체결은 **청산일 종가**로 나간다 (중간 익절이 없다)
- 손절이 걸린 체결의 손실은 **손절선 이하**다 (갭이 열린 경우를 뺀다)
- 성적표는 **구간 5개**를 갖고 표본이 모자란 구간도 행이 남는다
- 뒤에 데이터가 더 붙어도 이미 확정된 체결이 달라지지 않는다 (look-ahead 감시)
"""

from pathlib import Path

import pandas as pd
import pytest

from verify_lab.common_constants import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_VOLUME,
    MARKET_FILE_TEMPLATE,
    PRICE_DECIMALS_KRW,
)
from verify_lab.measure.screening import DIRECTION_DOWN, DIRECTION_UP
from verify_lab.report.constants import DISPLAY_EXCLUDED
from verify_lab.strategy.constants import (
    DISPLAY_DIRECTION,
    DISPLAY_EXIT_REASON,
    DISPLAY_HOLD_DAYS,
    DISPLAY_PERIOD,
    DISPLAY_RETURN,
    DISPLAY_STOP_LEVEL,
    EXIT_GAP_STOP,
    EXIT_LIMIT,
    MONTH_END_STOP_LEVELS,
    NO_STOP_LABEL,
    PERIOD_ALL,
    PERIODS,
    stop_level_value,
)
from verify_lab.strategy.month_end_runner import (
    DISPLAY_MONTH,
    TradingOutputs,
    run_month_end_trading,
)
from verify_lab.studies.month_end.constants import EXECUTION_ROLE_NONE, EXECUTION_ROLE_UP, MARKET_KOSDAQ, Dataset

# 합성 시세 구간. 12개월이 다 차려면 몇 해가 필요하다
SYNTHETIC_START = "2018-01-01"
SYNTHETIC_END = "2023-12-31"

# 백분율 비교 허용오차 (tests/CLAUDE.md 백분율 지표 기준)
PERCENT_TOLERANCE = 0.1


def _write_market(directory: Path, ticker: str, days: pd.DatetimeIndex | None = None) -> Dataset:
    """장중 등락이 있는 합성 ETF 시세를 만든다.

    **고가·저가를 종가에서 벌려 둔다** — 장중 손절이 실제로 걸리는지 보려면 일중 범위가 있어야 한다.

    Args:
        directory: 파일을 쓸 폴더
        ticker: 종목 코드
        days: 거래일 달력. **제외를 만들려면 거래일을 비워야 하므로 받는다** —
            어느 달의 20일 이전이 전부 휴장이면 그 달은 진입일을 잡을 수 없다

    Returns:
        시세 스키마 대상 정의
    """
    days = pd.bdate_range(SYNTHETIC_START, SYNTHETIC_END) if days is None else days
    closes = [10_000 + (index % 29) * 97 - (index % 13) * 61 for index in range(len(days))]
    highs = [close + 180 for close in closes]
    lows = [close - 180 for close in closes]
    opens = [close + (60 if index % 3 else -140) for index, close in enumerate(closes)]

    pd.DataFrame(
        {
            COL_DATE: days.date,
            COL_OPEN: opens,
            COL_HIGH: highs,
            COL_LOW: lows,
            COL_CLOSE: closes,
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
    """합성 지수 계열을 만든다.

    **시가·고가·저가가 없다.** 실제 코스닥150 지수가 그렇고(`docs/spec/월말_진입_설계.md` §7.6),
    그래서 장중 손절을 잴 수 없다.

    Args:
        directory: 파일을 쓸 폴더
        ticker: 지수 코드

    Returns:
        단일 값 계열 대상 정의
    """
    from verify_lab.common_constants import COL_VALUE, INDEX_FILE_TEMPLATE, PRICE_DECIMALS

    days = pd.bdate_range(SYNTHETIC_START, SYNTHETIC_END)
    values = [700.0 + (index % 29) * 6.1 - (index % 13) * 3.7 for index in range(len(days))]

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
def dataset(tmp_path_factory: pytest.TempPathFactory) -> Dataset:
    """합성 ETF 대상 (파일은 임시 폴더에 격리된다)."""
    return _write_market(tmp_path_factory.mktemp("market"), "999900")


@pytest.fixture(scope="module")
def index_dataset(tmp_path_factory: pytest.TempPathFactory) -> Dataset:
    """합성 지수 대상 (파일은 임시 폴더에 격리된다)."""
    return _write_index(tmp_path_factory.mktemp("series"), "9999")


@pytest.fixture(scope="module")
def index_outputs(index_dataset: Dataset) -> TradingOutputs:
    """지수 하나를 돌린 산출물. 손절선을 넘겨도 무손절로 강등되는지 보려고 그대로 넘긴다."""
    return run_month_end_trading((index_dataset,))


@pytest.fixture(scope="module")
def outputs(dataset: Dataset) -> TradingOutputs:
    """격자를 한 번만 돌린 산출물.

    **모듈 스코프인 이유**: 12개월 × 2방향 × 9손절 을 도는 데 시간이 걸린다.
    입력이 불변이라 공유해도 안전하다.
    """
    return run_month_end_trading((dataset,))


class TestGridAxis:
    """격자 축 — 손절선 · 월 · 방향"""

    def test_stop_grid_has_eight_levels_plus_no_stop(self, outputs: TradingOutputs) -> None:
        """
        목적: 손절선 격자가 **8종 + 무손절 = 9행**임을 고정한다.

        무손절이 빠지면 「손절이 무엇을 막았는가」를 잴 기준이 없어진다
        (`.claude/rules/strategy.md`).

        Given: 합성 ETF 하나
        When: 격자를 돌린다
        Then: 손절선 축의 값이 9개이고 무손절 표기가 들어 있다
        """
        # Given / When
        levels = set(outputs.performance[DISPLAY_STOP_LEVEL])

        # Then
        assert len(levels) == len(MONTH_END_STOP_LEVELS) + 1
        assert NO_STOP_LABEL in levels

    def test_all_twelve_months_are_present(self, outputs: TradingOutputs) -> None:
        """
        목적: **12개월이 전부** 나옴을 고정한다.

        눈에 띄는 달만 돌리면 그 선택이 손절 결과에도 그대로 실린다.

        Given: 합성 ETF 하나
        When: 격자를 돌린다
        Then: 월 축이 1~12 전부다
        """
        # Given / When
        months = set(outputs.performance[DISPLAY_MONTH])

        # Then
        assert months == set(range(1, 13))

    def test_both_directions_are_present(self, outputs: TradingOutputs) -> None:
        """
        목적: **두 방향이 모두** 나옴을 고정한다 (측정의 원칙 11).

        방향을 고르는 코드를 두면 그 선택이 결론에 숨는다.

        Given: 합성 ETF 하나
        When: 격자를 돌린다
        Then: 방향 축에 「위」와 「아래」가 다 있다
        """
        # Given / When
        directions = set(outputs.performance[DISPLAY_DIRECTION])

        # Then
        assert directions == {DIRECTION_UP, DIRECTION_DOWN}

    def test_performance_covers_every_period(self, outputs: TradingOutputs) -> None:
        """
        목적: 성적표가 **구간 5개**를 전부 가짐을 고정한다 (측정의 원칙 17).

        Given: 합성 ETF 하나
        When: 격자를 돌린다
        Then: 구간 축이 `PERIODS` 와 같다
        """
        # Given / When
        periods = set(outputs.performance[DISPLAY_PERIOD])

        # Then
        assert periods == set(PERIODS)


class TestStopLoss:
    """손절 판정이 조립을 거쳐도 유지된다"""

    def test_no_stop_trades_exit_on_the_scheduled_day(self, outputs: TradingOutputs) -> None:
        """
        목적: 무손절 체결이 **청산일까지 보유**됨을 고정한다.

        중간 익절이 섞이면 「달력 청산」이라는 이 매매의 정의가 깨진다.

        Given: 합성 ETF 하나
        When: 격자를 돌린다
        Then: 무손절 체결의 청산 사유가 전부 기한청산이다
        """
        # Given / When
        no_stop = outputs.trades[outputs.trades[DISPLAY_STOP_LEVEL] == NO_STOP_LABEL]

        # Then
        assert not no_stop.empty
        assert set(no_stop[DISPLAY_EXIT_REASON]) == {EXIT_LIMIT}

    def test_stopped_trades_do_not_lose_more_than_the_level(self, outputs: TradingOutputs) -> None:
        """
        목적: 손절이 걸린 체결의 손실이 **손절선 이하**임을 고정한다.

        **갭손절은 예외다** — 시가가 이미 손절선 아래로 열리면 그 시가에 나가므로 더 잃는다.
        손절선이 막아주는 것은 장중에 밀리는 손실뿐이다 (`.claude/rules/strategy.md`).

        Given: 손절선 −5% 로 잡은 체결
        When: 갭손절이 아닌 체결만 본다
        Then: 손실이 −5% 를 넘지 않는다
        """
        # Given
        sliced = outputs.trades[outputs.trades[DISPLAY_STOP_LEVEL] == -5.0]
        assert not sliced.empty, "−5% 손절선 체결이 하나도 없습니다"

        # When
        without_gap = sliced[sliced[DISPLAY_EXIT_REASON] != EXIT_GAP_STOP]

        # Then
        assert without_gap[DISPLAY_RETURN].min() >= -5.0 - PERCENT_TOLERANCE

    def test_gap_stops_are_counted_separately(self, outputs: TradingOutputs) -> None:
        """
        목적: **갭손절이 따로 세어짐**을 고정한다.

        갭손절 건수는 그 손절선이 실제로 지켜지는지를 말해 주므로 성적표에 남아야 한다.

        Given: 합성 ETF 하나
        When: 격자를 돌린다
        Then: 성적표에 갭손절 컬럼이 있고 표본이 있는 행은 비어 있지 않다
        """
        # Given / When
        from verify_lab.strategy.constants import DISPLAY_GAP_STOP_COUNT, DISPLAY_SIGNAL_COUNT

        counted = outputs.performance[outputs.performance[DISPLAY_SIGNAL_COUNT] > 0]

        # Then
        assert DISPLAY_GAP_STOP_COUNT in outputs.performance.columns
        assert counted[DISPLAY_GAP_STOP_COUNT].notna().all()

    def test_wider_stop_triggers_fewer_stops_in_total(self, outputs: TradingOutputs) -> None:
        """
        목적: 손절선이 넓어지면 **손절 총 건수(갭 + 장중)가 줄어듦**을 고정한다.

        **장중손절만 세면 단조성이 성립하지 않는다** — 두 사유가 서로 잡아먹기 때문이다.
        좁은 손절선에서는 같은 갭이 이미 손절선을 넘어 **갭손절**로 분류되고, 넓은 손절선에서는
        그 갭을 통과한 뒤 나중에 장중에 걸려 **장중손절**이 된다. 실측에서 −3% 의 장중손절이
        3건인데 −10% 가 4건인 달이 나왔다. 둘을 합쳐야 손절선 축의 단조성이 드러난다.

        **「좁은 손절선이 최악을 개선한다」는 계약도 두지 않는다** — 성립하지 않기 때문이다.
        장중에 손절선을 터치했다가 회복해 더 작은 손실로 끝나는 구간에서는 **손절이 오히려
        최악을 나쁘게 만든다.** 이 합성 데이터의 4월이 무손절 −2.45% 대 −3% 손절 −3.00% 다.
        손절이 보장하는 것은 **장중에 밀리는 손실의 상한**이지 결과의 개선이 아니다.

        Given: 전체 구간의 「아래」 방향 성적
        When: −3% 와 −10% 의 손절 총 건수를 견준다
        Then: −10% 쪽이 더 적거나 같다
        """
        # Given
        from verify_lab.strategy.constants import (
            DISPLAY_GAP_STOP_COUNT,
            DISPLAY_INTRADAY_STOP_COUNT,
            PERIOD_ALL,
        )

        overall = outputs.performance[
            (outputs.performance[DISPLAY_PERIOD] == PERIOD_ALL)
            & (outputs.performance[DISPLAY_DIRECTION] == DIRECTION_DOWN)
        ]

        def _total_stops(level: float) -> pd.Series:
            sliced = overall[overall[DISPLAY_STOP_LEVEL] == level].set_index(DISPLAY_MONTH)

            return sliced[DISPLAY_GAP_STOP_COUNT] + sliced[DISPLAY_INTRADAY_STOP_COUNT]

        tight = _total_stops(-3.0)
        wide = _total_stops(-10.0)

        # When / Then
        assert (wide <= tight).all()
        assert tight.sum() > 0, "손절이 한 건도 없으면 이 계약을 검사하지 못합니다"


class TestSamplePreservation:
    """표본이 조용히 사라지지 않는다"""

    def test_제외_건수가_성적표에_실린다(self, tmp_path: Path) -> None:
        """
        목적: 제외 건수가 **성적표까지** 오는지 고정한다.

        전에는 `_collect_entries` 가 센 값이 `summary.json` 에만 가고 성적표에는 안 왔다 —
        성적표의 제외가 **구조적으로 항상 0** 이었고, 실제 값도 0 이어서 드러나지 않았다.
        표본을 줄이는 처리는 몇 건이 왜 빠졌는지 함께 내야 한다 (절대 원칙 「표본 보존」).

        **달별로 센다.** 대상 합계를 칸마다 실으면 같은 건수가 216번 반복된다.

        Given: 6월 20일 이전이 전부 휴장인 달력 — 그 달은 진입일을 잡을 수 없다
        When: 격자를 돌린다
        Then: 6월 전체 행의 제외가 1 이고 다른 달은 0 이다
        """
        # Given
        gap_year, gap_month = 2021, 6
        days = pd.DatetimeIndex(
            [
                day
                for day in pd.bdate_range(SYNTHETIC_START, SYNTHETIC_END)
                if not (day.year == gap_year and day.month == gap_month and day.day <= 20)
            ]
        )
        dataset = _write_market(tmp_path, "999911", days)

        # When
        overall = run_month_end_trading((dataset,)).performance
        overall = overall[overall[DISPLAY_PERIOD] == PERIOD_ALL]

        # Then
        counts = overall.groupby(DISPLAY_MONTH)[DISPLAY_EXCLUDED].max()
        assert counts[gap_month] == 1, f"6월 제외가 1 이 아닙니다: {counts[gap_month]}"
        assert set(counts.drop(gap_month)) == {0}, f"다른 달에 제외가 섞였습니다: {counts.to_dict()}"

    def test_구간_행의_제외는_비어_있다(self, outputs: TradingOutputs) -> None:
        """
        목적: 구간 행이 「제외 0건」이라고 **거짓으로 주장하지 않는지** 고정한다.

        제외된 신호는 **언제나 가장 최근**이므로, 뒤 절반·최근 N년에 `0` 을 적으면
        사실과 반대가 될 수 있다. 귀속 규칙이 없으니 빈칸으로 남긴다.

        Given: 격자 성적표
        When: 전체가 아닌 구간 행을 봤을 때
        Then: 제외 칸이 비어 있다
        """
        # Given
        others = outputs.performance[outputs.performance[DISPLAY_PERIOD] != PERIOD_ALL]

        # When / Then
        assert not others.empty
        assert others[DISPLAY_EXCLUDED].isna().all()

    def test_trade_count_matches_across_stop_levels(self, outputs: TradingOutputs) -> None:
        """
        목적: 손절선을 바꿔도 **체결 수가 같음**을 고정한다.

        달력 청산이라 미체결이 없다. 손절선이 바꾸는 것은 언제 나가느냐이지 몇 건이냐가 아니다.

        Given: 합성 ETF 하나
        When: 손절선별 체결 수를 센다
        Then: 전부 같다
        """
        # Given / When
        counts = outputs.trades.groupby(DISPLAY_STOP_LEVEL).size()

        # Then
        assert counts.nunique() == 1

    def test_hold_days_never_exceed_the_scheduled_span(self, outputs: TradingOutputs) -> None:
        """
        목적: 보유일이 **예정 청산일을 넘지 않음**을 고정한다.

        손절은 일찍 나가게 할 뿐 늦게 나가게 하지 않는다.

        Given: 무손절과 −3% 체결
        When: 진입일별로 보유일을 견준다
        Then: −3% 의 보유일이 무손절보다 길지 않다
        """
        # Given
        from verify_lab.strategy.constants import DISPLAY_ENTRY_DATE

        keys = [DISPLAY_MONTH, DISPLAY_DIRECTION, DISPLAY_ENTRY_DATE]
        no_stop = outputs.trades[outputs.trades[DISPLAY_STOP_LEVEL] == NO_STOP_LABEL].set_index(keys)
        tight = outputs.trades[outputs.trades[DISPLAY_STOP_LEVEL] == -3.0].set_index(keys)

        # When
        merged = tight[[DISPLAY_HOLD_DAYS]].join(no_stop[[DISPLAY_HOLD_DAYS]], lsuffix="_tight", rsuffix="_none")

        # Then
        assert (merged[f"{DISPLAY_HOLD_DAYS}_tight"] <= merged[f"{DISPLAY_HOLD_DAYS}_none"]).all()


class TestLookAhead:
    """look-ahead 감시 — 미래 데이터가 체결을 바꾸지 않는다"""

    def test_trades_are_stable_under_truncation(self, tmp_path: Path, dataset: Dataset) -> None:
        """
        목적: **look-ahead 감시** — 뒤에 데이터가 더 붙어도 이미 확정된 체결이 달라지면 안 된다.

        Given: 합성 시세와 그 앞부분만 잘라낸 시세
        When: 두 입력으로 각각 격자를 돌린다
        Then: 겹치는 진입일의 수익률이 같다
        """
        # Given
        from verify_lab.strategy.constants import DISPLAY_ENTRY_DATE

        full = pd.read_csv(dataset.path)
        short_path = tmp_path / MARKET_FILE_TEMPLATE.format(ticker="999901")
        full.iloc[: len(full) - 260].to_csv(short_path, index=False)
        truncated = Dataset(
            ticker="999901",
            label="잘라낸 합성 ETF",
            market=MARKET_KOSDAQ,
            directory=tmp_path,
            file_template=MARKET_FILE_TEMPLATE,
            price_column=COL_CLOSE,
            price_decimals=PRICE_DECIMALS_KRW,
            is_index=False,
            execution_role=EXECUTION_ROLE_UP,
        )

        # When
        whole_trades = run_month_end_trading((dataset,)).trades
        short_trades = run_month_end_trading((truncated,)).trades

        # Then
        keys = [DISPLAY_STOP_LEVEL, DISPLAY_DIRECTION, DISPLAY_ENTRY_DATE]
        merged = short_trades.merge(whole_trades, on=keys, how="inner", suffixes=("_short", "_whole"))
        assert not merged.empty, "겹치는 체결이 하나도 없습니다 — 자르는 위치를 뒤로 옮기세요"
        assert merged[f"{DISPLAY_RETURN}_short"].tolist() == pytest.approx(
            merged[f"{DISPLAY_RETURN}_whole"].tolist(), abs=PERCENT_TOLERANCE
        )


class TestIndexDataset:
    """지수는 손절을 못 재므로 무손절로 강등된다 (거부하지 않는다)"""

    def test_index_produces_only_the_no_stop_row(self, index_outputs: TradingOutputs) -> None:
        """
        목적: 지수에 손절선을 넘겨도 **무손절 한 줄만** 나옴을 고정한다.

        **조용히 종가로 손절을 재면 안 된다** — 장중 최악을 모르니 실제보다 손절이 덜 걸려
        성적이 좋아지고, 그것이 「손절이 필요 없다」로 읽힌다.

        Given: 합성 지수 하나 (손절선 목록을 그대로 넘긴다)
        When: 격자를 돌린다
        Then: 손절선 축의 값이 무손절 하나뿐이다
        """
        # Given / When
        levels = set(index_outputs.performance[DISPLAY_STOP_LEVEL])

        # Then
        assert levels == {NO_STOP_LABEL}

    def test_index_rows_are_marked_as_not_applicable(self, index_outputs: TradingOutputs) -> None:
        """
        목적: 지수 행에 **「손절을 잴 수 없었다」가 적힘**을 고정한다.

        무손절 값만 보면 「손절을 걸었는데 한 번도 안 걸렸다」와 구별되지 않는다.
        **빈칸으로 두지 않는다** — 빈칸은 「값을 못 구했다」로 읽힌다.

        Given: 합성 지수 하나
        When: 격자를 돌린다
        Then: 두 표의 손절적용 컬럼이 전부 「불가」다
        """
        # Given
        from verify_lab.strategy.constants import DISPLAY_STOP_APPLICABLE, STOP_NOT_APPLICABLE

        # When / Then
        for table in (index_outputs.performance, index_outputs.trades):
            assert DISPLAY_STOP_APPLICABLE in table.columns
            assert set(table[DISPLAY_STOP_APPLICABLE]) == {STOP_NOT_APPLICABLE}

    def test_etf_rows_are_marked_as_applicable(self, outputs: TradingOutputs) -> None:
        """
        목적: ETF 행은 **「가능」**임을 고정한다.

        **손절선 값을 이 컬럼에 담지 않는다** — 격자표에는 `손절선(%)` 이 이미 있어 중복이고,
        손절선을 고정한 표에서만 손절선 뜻이 되면 같은 컬럼명이 파일마다 다른 것을 가리킨다.

        Given: 합성 ETF 하나
        When: 격자를 돌린다
        Then: 손절적용 컬럼이 전부 「가능」이다
        """
        # Given
        from verify_lab.strategy.constants import DISPLAY_STOP_APPLICABLE, STOP_APPLICABLE

        # When / Then
        assert set(outputs.performance[DISPLAY_STOP_APPLICABLE]) == {STOP_APPLICABLE}

    def test_index_trades_exit_on_the_scheduled_day(self, index_outputs: TradingOutputs) -> None:
        """
        목적: 지수 체결이 **청산일 종가**로 나감을 고정한다.

        Given: 합성 지수 하나
        When: 격자를 돌린다
        Then: 청산 사유가 전부 기한청산이다
        """
        # Given / When / Then
        assert set(index_outputs.trades[DISPLAY_EXIT_REASON]) == {EXIT_LIMIT}


class TestDatasetLabel:
    """산출물의 종목 컬럼은 종목명이다"""

    def test_outputs_carry_the_label_not_the_code(self, outputs: TradingOutputs) -> None:
        """
        목적: 종목 컬럼이 **종목명**임을 고정한다 (숫자 코드가 아니다).

        **숫자만으로 된 값이 하나도 없어야** 코드가 새어 나가지 않은 것이다.
        종목코드는 `summary.json` 의 데이터셋 목록이 갖는다.

        Given: 합성 ETF 하나
        When: 격자를 돌린다
        Then: 두 표의 종목 컬럼에 숫자만인 값이 없다
        """
        # Given
        from verify_lab.strategy.constants import DISPLAY_TICKER

        # When / Then
        for table in (outputs.performance, outputs.trades):
            values = set(table[DISPLAY_TICKER].astype(str))
            numeric = {value for value in values if value.isdigit()}
            assert not numeric, f"종목 컬럼에 코드가 남아 있습니다: {sorted(numeric)}"

    def test_summary_keeps_the_ticker(self, outputs: TradingOutputs) -> None:
        """
        목적: **종목코드가 요약에 남음**을 고정한다.

        산출물에서 코드를 뺐으므로 차트·증권앱과 대조할 때 코드를 찾을 자리가 필요하다.
        여기가 종목명과 코드를 잇는 유일한 자리다.

        Given: 합성 ETF 하나
        When: 격자를 돌린다
        Then: 요약의 데이터셋 항목에 코드와 종목명이 모두 있다
        """
        # Given
        from verify_lab.strategy.run_summary import KEY_DATASET_LABEL, KEY_DATASET_TICKER, KEY_DATASETS

        # When
        entries = outputs.summary[KEY_DATASETS]

        # Then
        assert entries
        for entry in entries:
            assert entry[KEY_DATASET_TICKER]
            assert entry[KEY_DATASET_LABEL]


class TestFixedStopTable:
    """손절선을 고정한 성적표"""

    def test_fixed_table_has_no_stop_level_column(self, outputs: TradingOutputs) -> None:
        """
        목적: 고정 성적표에 **손절선 컬럼이 남음**을 고정한다.

        **「값이 하나뿐인 필터」라는 전제가 이 표에서는 성립하지 않는다** — ETF 행은 −5% 이고
        지수 행은 무손절이라 두 행이 서로 다른 규칙으로 만들어진 성적이다. 컬럼이 없으면
        `손절적용` 으로 추측해야 하고 「가능」이 −5% 인지 −3% 인지는 알 수 없다.

        Given: 합성 ETF 하나
        When: 격자를 돌린다
        Then: 고정 표의 컬럼 구성이 격자 성적표와 같다
        """
        # Given
        from verify_lab.strategy.constants import DISPLAY_STOP_APPLICABLE

        # When
        fixed = outputs.performance_fixed_stop

        # Then
        assert list(fixed.columns) == list(outputs.performance.columns)
        assert DISPLAY_STOP_LEVEL in fixed.columns
        assert DISPLAY_STOP_APPLICABLE in fixed.columns

    def test_fixed_table_matches_the_grid_rows(self, outputs: TradingOutputs) -> None:
        """
        목적: 고정 표의 값이 **격자의 해당 손절선 행과 같음**을 고정한다.

        **따로 계산하지 않는다** — 다시 계산하면 두 표가 조용히 갈라진다.

        Given: 합성 ETF 하나
        When: 격자의 −5% 행과 고정 표를 견준다
        Then: 합계가 같다
        """
        # Given
        from verify_lab.strategy.constants import DISPLAY_TOTAL, FIXED_STOP_LEVEL

        keys = [DISPLAY_MONTH, DISPLAY_DIRECTION, DISPLAY_PERIOD]
        grid = outputs.performance
        sliced = grid[grid[DISPLAY_STOP_LEVEL] == stop_level_value(FIXED_STOP_LEVEL)].set_index(keys)

        # When
        fixed = outputs.performance_fixed_stop.set_index(keys)
        merged = fixed[[DISPLAY_TOTAL]].join(sliced[[DISPLAY_TOTAL]], lsuffix="_fixed", rsuffix="_grid")

        # Then
        assert not merged.empty
        assert merged[f"{DISPLAY_TOTAL}_fixed"].tolist() == pytest.approx(
            merged[f"{DISPLAY_TOTAL}_grid"].tolist(), abs=PERCENT_TOLERANCE, nan_ok=True
        )

    def test_fixed_table_uses_the_no_stop_row_for_indexes(self, index_outputs: TradingOutputs) -> None:
        """
        목적: 지수는 고정 표에 **무손절 행**으로 들어감을 고정한다.

        −5% 행이 아예 없으므로 걸러내면 지수가 표에서 사라진다 —
        **30년 축을 보려고 지수를 넣었는데 그러면 목적이 사라진다.**

        Given: 합성 지수 하나
        When: 격자를 돌린다
        Then: 고정 표에 행이 있고 손절적용이 「불가」다
        """
        # Given
        from verify_lab.strategy.constants import DISPLAY_STOP_APPLICABLE, STOP_NOT_APPLICABLE

        # When
        fixed = index_outputs.performance_fixed_stop

        # Then
        assert not fixed.empty
        assert set(fixed[DISPLAY_STOP_APPLICABLE]) == {STOP_NOT_APPLICABLE}


def test_empty_dataset_list_raises() -> None:
    """
    목적: 대상이 없으면 조용히 빈 결과를 내지 않고 실패함을 고정한다.

    Given: 빈 대상 목록
    When: 격자를 돌린다
    Then: ValueError 가 난다
    """
    # Given / When / Then
    with pytest.raises(ValueError, match="대상"):
        run_month_end_trading(())
