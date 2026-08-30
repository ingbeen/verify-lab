"""역방향 매매 실행 계층의 계약을 고정한다.

이 계층이 틀리는 방식은 **집계 단위가 어긋나는 것**이다. 자금을 3등분했는데 조각을 표본으로
세면 표본이 세 배로 부풀고 승률이 왜곡되는데, 표는 정상으로 보인다.

핵심 계약은 넷이다.
- 산출물 축은 **대상 × 보유 한도**의 곱이다
- 집계는 **신호 단위**다. 조각은 평균으로 합쳐진다
- 집계는 **원값으로** 한다. 반올림된 표에서 다시 평균을 내면 합계가 어긋난다
- 신호 판정은 `studies` 가 소유한다. 이 계층은 **어느 날이 신호인가를 다시 정하지 않는다**
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
    COL_VOLUME,
    PRICE_DECIMALS,
    RATE_TO_PERCENT,
)
from verify_lab.report.constants import DISPLAY_EXCLUDED
from verify_lab.strategy.constants import (
    DISPLAY_DATE,
    DISPLAY_HOLD_LIMIT,
    DISPLAY_MEAN_HOLD,
    DISPLAY_RETURN,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_STOP_LEVEL,
    DISPLAY_TOTAL,
    HOLD_LIMITS,
    START_YEAR,
    STOP_LOSS_LEVELS,
    TARGETS,
    Target,
)
from verify_lab.strategy.runner import IDENTITY_COLUMNS, KEY_TARGETS, StrategyOutputs, run_strategy
from verify_lab.studies.index_extreme.constants import Dataset

# 합성 시세를 만드는 난수 시드. 시드 없는 난수는 금지다
SYNTHETIC_SEED = 20260823

# 순위 축적 구간에 심는 등락의 크기. 집계 구간에서는 이보다 큰 등락만 신호가 된다
ACCUMULATION_SHOCK = 0.05

# 합성 시세의 시작일. 집계 시작연도 이전 구간이 순위 축적에 쓰인다
MARKET_START = "2005-01-03"

# 집계 구간에 심는 신호의 위치(집계 시작일 기준 오프셋)와 방향.
# **뒤를 잘라 「데이터 끝을 넘어가는 신호」를 만들 때 마지막 값을 쓴다**
SIGNAL_PLACEMENTS = ((60, -1), (140, 1), (260, -1))

# 백분율 지표의 허용오차 (tests/CLAUDE.md)
RATE_TOLERANCE = 0.1


def _accumulation_index(rows: int) -> int:
    """집계 시작연도의 첫 거래일이 몇 번째 행인지 낸다."""
    dates = pd.DatetimeIndex(pd.bdate_range(MARKET_START, periods=rows))

    return int(np.flatnonzero(dates >= pd.Timestamp(f"{START_YEAR}-01-01"))[0])


def _market(rows: int = 1_400) -> pd.DataFrame:
    """신호가 손으로 셀 수 있게 심긴 합성 시세를 만든다.

    집계 시작 전에 순위를 채워 두고, 집계 구간에는 그보다 큰 등락만 심는다.
    집계 시작연도 이전 구간이 순위 축적에 쓰이므로 그만큼 길이가 필요하다.
    """
    rng = np.random.default_rng(SYNTHETIC_SEED)
    dates = pd.DatetimeIndex(pd.bdate_range(MARKET_START, periods=rows))
    changes = rng.normal(0.0002, 0.004, rows - 1)

    # 1. 집계 시작 전에 순위 컷을 채운다 (신호가 아니다)
    accumulation = _accumulation_index(rows)
    for offset in range(25):
        changes[offset * 8] = ACCUMULATION_SHOCK
        changes[offset * 8 + 4] = -ACCUMULATION_SHOCK

    # 2. 집계 구간에 더 큰 등락을 심는다
    for offset, sign in SIGNAL_PLACEMENTS:
        if accumulation + offset >= len(changes):
            continue
        changes[accumulation + offset] = 0.09 * sign

    closes = 100.0 * np.cumprod(np.concatenate([[1.0], 1.0 + changes]))
    opens = np.concatenate([[closes[0]], closes[:-1] * 1.001])

    return pd.DataFrame(
        {
            COL_DATE: dates,
            COL_OPEN: opens,
            COL_HIGH: np.maximum(opens, closes) * 1.01,
            COL_LOW: np.minimum(opens, closes) * 0.99,
            COL_CLOSE: closes,
            COL_VOLUME: 1_000_000,
        }
    )


def _target(directory: Path, *, rank_cut: int = 10, ticker: str = "합성", rows: int = 1_400) -> Target:
    """합성 시세를 저장하고 그 파일을 가리키는 대상을 만든다.

    실경로 `storage/` 를 건드리지 않도록 언제나 임시 디렉터리에 쓴다.

    Args:
        directory: 저장할 임시 디렉터리
        rank_cut: 순위 컷
        ticker: 종목 표시 이름 (파일명에도 쓰인다)
        rows: 시세 행 수. **줄이면 뒤쪽 신호의 보유 구간이 데이터 끝을 넘어간다**
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{ticker}.csv"
    saved = _market(rows)
    saved[COL_DATE] = saved[COL_DATE].dt.strftime("%Y-%m-%d")
    saved.to_csv(path, index=False)

    return Target(
        dataset=Dataset(key="synthetic", ticker=ticker, price_basis="원본가", path=path, price_decimals=PRICE_DECIMALS),
        rank_cut=rank_cut,
    )


@pytest.fixture(scope="module")
def outputs(tmp_path_factory: pytest.TempPathFactory) -> StrategyOutputs:
    """합성 시세로 전 조합을 돈 실행 결과 (모듈 안에서 한 번만 만든다)."""
    return run_strategy([_target(tmp_path_factory.mktemp("strategy"))])


class TestAxes:
    """산출물 축 계약"""

    def test_집계는_대상과_보유_한도의_곱만큼_나온다(self, outputs: StrategyOutputs) -> None:
        """
        목적: 보유 한도가 축으로 산출되는지 고정한다

        Given: 대상 1종으로 돈 실행 결과
        When: 집계 행 수를 봤을 때
        Then: 보유 한도 수만큼이다
        """
        # Given / When / Then
        assert len(outputs.summary) == len(HOLD_LIMITS)
        assert set(outputs.summary[DISPLAY_HOLD_LIMIT]) == {f"D+{limit}" for limit in HOLD_LIMITS}

    def test_식별_컬럼이_두_표에_모두_앞에_붙는다(self, outputs: StrategyOutputs) -> None:
        """
        목적: 어느 산출물을 열어도 어떤 설정의 결과인지 알 수 있는지 고정한다

        Given: 실행 결과의 두 표
        When: 앞쪽 컬럼을 봤을 때
        Then: 식별 컬럼이 순서대로 맨 앞에 있다
        """
        # Given / When / Then
        for table in (outputs.trades, outputs.summary):
            assert list(table.columns[: len(IDENTITY_COLUMNS)]) == list(IDENTITY_COLUMNS)

    def test_식별_컬럼은_네_개다(self) -> None:
        """
        목적: 식별 컬럼 구성을 상수가 아니라 값으로 고정한다

        Given: 식별 컬럼 정의
        When: 구성을 봤을 때
        Then: 종목·파라미터·시작연도·보유 한도 네 개다
        """
        # Given / When / Then
        assert IDENTITY_COLUMNS == ("종목", "파라미터", "시작연도", "보유 한도")

    def test_체결_내역은_신호마다_손절_단계_수만큼_나온다(self, outputs: StrategyOutputs) -> None:
        """
        목적: 조각이 빠짐없이 청산되는지 고정한다

        Given: 실행 결과의 체결 내역
        When: 한도·날짜별 행 수를 셌을 때
        Then: 전부 손절 단계 수와 같다
        """
        # Given / When
        counted = outputs.trades.groupby([DISPLAY_HOLD_LIMIT, DISPLAY_DATE]).size()

        # Then
        assert set(counted) == {len(STOP_LOSS_LEVELS)}

    def test_손절_단계가_전부_산출된다(self, outputs: StrategyOutputs) -> None:
        """
        목적: 자금 3등분이 산출물에 드러나는지 고정한다

        Given: 실행 결과의 체결 내역
        When: 손절선 값을 모았을 때
        Then: 상수와 같다
        """
        # Given / When
        levels = set(outputs.trades[DISPLAY_STOP_LEVEL])

        # Then
        assert levels == {round(level * RATE_TO_PERCENT, 2) for level in STOP_LOSS_LEVELS}


class TestAggregation:
    """집계 단위 계약"""

    def test_집계는_조각이_아니라_신호_단위다(self, outputs: StrategyOutputs) -> None:
        """
        목적: 조각을 표본으로 세지 않는지 고정한다

        조각을 세면 표본이 세 배로 부풀고 승률이 왜곡되는데 표는 정상으로 보인다.

        Given: 실행 결과
        When: 집계의 신호 수와 체결 내역의 날짜 수를 비교했을 때
        Then: 같다 (체결 행 수의 1/3 이다)
        """
        # Given
        row = outputs.summary.iloc[0]
        block = outputs.trades[outputs.trades[DISPLAY_HOLD_LIMIT] == row[DISPLAY_HOLD_LIMIT]]

        # When / Then
        assert row[DISPLAY_SIGNAL_COUNT] == block[DISPLAY_DATE].nunique()
        assert row[DISPLAY_SIGNAL_COUNT] == len(block) // len(STOP_LOSS_LEVELS)

    def test_합계는_신호별_평균의_합이다(self, outputs: StrategyOutputs) -> None:
        """
        목적: 이중 반올림으로 합계가 어긋나지 않는지 고정한다

        체결 내역은 저장 직전 반올림이 걸린 표다. 그것으로 다시 평균을 내면
        **합계가 0.01%p 단위로 어긋난다.** 집계는 원값으로 해야 한다.

        Given: 실행 결과
        When: 체결 내역에서 신호별 평균을 다시 계산했을 때
        Then: 집계의 합계와 허용오차 안에서 같다
        """
        # Given
        row = outputs.summary.iloc[0]
        block = outputs.trades[outputs.trades[DISPLAY_HOLD_LIMIT] == row[DISPLAY_HOLD_LIMIT]]

        # When
        recomputed = block.groupby(DISPLAY_DATE)[DISPLAY_RETURN].mean().sum()

        # Then
        assert row[DISPLAY_TOTAL] == pytest.approx(recomputed, abs=RATE_TOLERANCE)

    def test_보유일은_조각이_전부_청산된_날이다(self, outputs: StrategyOutputs) -> None:
        """
        목적: 보유일을 한도로 세지 않는지 고정한다

        D+1 에 세 조각이 모두 청산되면 한도가 얼마든 보유일은 1이다.

        Given: 실행 결과
        When: 한도별 평균 보유일을 봤을 때
        Then: 한도 값을 넘지 않고, 1 이상이다
        """
        # Given / When / Then
        for _, row in outputs.summary.iterrows():
            limit = int(row[DISPLAY_HOLD_LIMIT].removeprefix("D+"))
            assert 1.0 <= row[DISPLAY_MEAN_HOLD] <= limit

    def test_한도를_늘려도_신호_수는_같다(self, outputs: StrategyOutputs) -> None:
        """
        목적: 한도마다 표본이 달라지지 않는지 고정한다

        표본이 달라지면 조합끼리 비교할 수 없다.

        Given: 실행 결과의 집계
        When: 한도별 신호 수를 봤을 때
        Then: 전부 같다
        """
        # Given / When / Then
        assert outputs.summary[DISPLAY_SIGNAL_COUNT].nunique() == 1


class TestSignalOwnership:
    """신호 판정 계약"""

    def test_순위_컷을_넓히면_신호가_늘어난다(self, tmp_path: Path) -> None:
        """
        목적: 신호 판정을 `studies` 가 소유한다는 사실을 고정한다

        이 계층이 판정을 다시 하면 컷을 바꿔도 결과가 안 변하거나 다르게 변한다.

        Given: 같은 시세에 순위 컷만 다른 두 대상
        When: 각각 실행했을 때
        Then: 넓은 컷의 신호 수가 좁은 컷보다 많거나 같다
        """
        # Given
        narrow = run_strategy([_target(tmp_path / "narrow", rank_cut=5, ticker="좁은컷")])
        wide = run_strategy([_target(tmp_path / "wide", rank_cut=20, ticker="넓은컷")])

        # When
        narrow_count = int(narrow.summary[DISPLAY_SIGNAL_COUNT].iloc[0])
        wide_count = int(wide.summary[DISPLAY_SIGNAL_COUNT].iloc[0])

        # Then
        assert wide_count >= narrow_count

    def test_뒤를_잘라내도_겹치는_신호의_체결이_같다(self, tmp_path: Path) -> None:
        """
        목적: look-ahead 감시 — 미래 데이터가 체결에 섞이지 않는지 고정한다

        Given: 합성 시세와, 뒤쪽을 잘라낸 같은 시세
        When: 각각 실행했을 때
        Then: 겹치는 신호일의 수익률이 같다
        """
        # Given
        whole = _market()
        cut = whole.iloc[: len(whole) - 100]
        results = []
        for name, frame in (("전체", whole), ("절단", cut)):
            directory = tmp_path / name
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / "cut.csv"
            saved = frame.copy()
            saved[COL_DATE] = pd.to_datetime(saved[COL_DATE]).dt.strftime("%Y-%m-%d")
            saved.to_csv(path, index=False)
            target = Target(
                dataset=Dataset(
                    key="synthetic", ticker="절단", price_basis="원본가", path=path, price_decimals=PRICE_DECIMALS
                ),
                rank_cut=10,
            )
            results.append(run_strategy([target], hold_limits=(1,)).trades)

        # When
        merged = results[1].merge(results[0], on=[DISPLAY_DATE, DISPLAY_STOP_LEVEL], suffixes=("_cut", "_whole"))

        # Then
        assert not merged.empty
        assert merged[f"{DISPLAY_RETURN}_cut"].tolist() == merged[f"{DISPLAY_RETURN}_whole"].tolist()


class TestTargetsInvariant:
    """매매 대상 목록의 불변조건"""

    def test_대상은_세_종이다(self) -> None:
        """
        목적: 대상이 조용히 늘거나 줄지 않는지 값으로 고정한다

        Given: 매매 대상 목록
        When: 종목과 순위 컷을 모았을 때
        Then: KODEX 200 K=10, QQQ K=10, QQQ K=20 세 종이다
        """
        # Given / When
        pairs = {(target.dataset.ticker, target.rank_cut) for target in TARGETS}

        # Then
        assert pairs == {("KODEX 200", 10), ("QQQ", 10), ("QQQ", 20)}

    def test_손절선은_세_단계이고_오름차순이다(self) -> None:
        """
        목적: 손절 3분할 구성을 값으로 고정한다

        Given: 손절선 목록
        When: 값을 봤을 때
        Then: 4·5·6% 오름차순이다
        """
        # Given / When / Then
        assert STOP_LOSS_LEVELS == (0.04, 0.05, 0.06)
        assert list(STOP_LOSS_LEVELS) == sorted(STOP_LOSS_LEVELS)

    def test_보유_한도는_세_값이다(self) -> None:
        """
        목적: 한도 축 구성을 값으로 고정한다

        하나만 두면 표본에 맞춘 튜닝이 된다.

        Given: 보유 한도 목록
        When: 값을 봤을 때
        Then: 1·2·3 이다
        """
        # Given / When / Then
        assert HOLD_LIMITS == (1, 2, 3)

    def test_시작연도가_요약에_남는다(self, outputs: StrategyOutputs) -> None:
        """
        목적: 산출물만 보고 설정을 재구성할 수 있는지 고정한다

        Given: 실행 결과의 요약
        When: 대상 정보를 봤을 때
        Then: 시작연도와 신호 수가 남아 있다
        """
        # Given / When
        record = outputs.meta[KEY_TARGETS][0]

        # Then
        assert record["start_year"] == START_YEAR
        assert record["signal_count"] > 0


class TestSamplePreservation:
    """표본 보존 — 데이터 끝을 넘어가 버려진 신호가 건수로 남는다 (tests/CLAUDE.md 필수)."""

    def _trimmed_outputs(self, directory: Path) -> StrategyOutputs:
        """시세를 **마지막 신호일에서 끝나게** 잘라 실행한다.

        진입 다음 거래일이 아예 없으므로 그 신호는 **이익이든 손실이든 체결을 만들 수 없다.**
        보유 구간을 한 칸만 남기면 D+1 에 이익 청산돼 제외가 생기지 않는다.

        신호일 인덱스는 `집계 시작 + 오프셋 + 1` 이다 — 등락률이 심긴 날의 **다음 종가**가
        그 등락을 갖기 때문이다. 시세 길이를 그보다 하나 크게 잡으면 신호일이 마지막 행이 된다.
        """
        last_offset = SIGNAL_PLACEMENTS[-1][0]
        rows = _accumulation_index(1_400) + last_offset + 2

        return run_strategy([_target(directory, rows=rows)], hold_limits=[3])

    def test_체결하지_못한_신호가_제외_건수로_남는다(self, tmp_path: Path) -> None:
        """
        목적: 보유 한도가 데이터 끝을 넘어간 신호를 **조용히 버리지 않는다.**
              건수를 보고하지 않으면 표본이 줄어든 사실이 산출물에서 보이지 않는다.

        Given: 마지막 신호의 보유 구간이 잘린 시세
        When: 보유 한도 3 으로 실행하면
        Then: 집계에 제외 건수가 1건 이상 실린다
        """
        # Given / When
        outputs = self._trimmed_outputs(tmp_path)

        # Then
        assert int(outputs.summary.iloc[0][DISPLAY_EXCLUDED]) >= 1

    def test_신호_수와_제외_수의_합이_전체_신호_수다(self, tmp_path: Path) -> None:
        """
        목적: **`신호 수 = 집계된 표본 + 제외된 표본`** 이 성립한다.
              이 등식이 깨지면 표본이 어딘가로 사라진 것이다.

        Given: 마지막 신호의 보유 구간이 잘린 시세
        When: 보유 한도 3 으로 실행하면
        Then: 집계의 신호 수 + 제외 수가 요약의 전체 신호 수와 같다
        """
        # Given / When
        outputs = self._trimmed_outputs(tmp_path)

        # Then
        row = outputs.summary.iloc[0]
        counted = int(row[DISPLAY_SIGNAL_COUNT]) + int(row[DISPLAY_EXCLUDED])
        assert counted == int(outputs.meta[KEY_TARGETS][0]["signal_count"])

    def test_전부_체결되면_제외가_0이다(self, outputs: StrategyOutputs) -> None:
        """
        목적: 제외가 없을 때 0 이 실린다. 빈칸으로 두면 "안 쟀다"로 읽힌다.

        Given: 모든 신호의 보유 구간이 데이터 안에 있는 시세
        When: 전 조합을 돌면
        Then: 모든 행의 제외 건수가 0 이다
        """
        # Given / When / Then
        assert outputs.summary[DISPLAY_EXCLUDED].tolist() == [0] * len(outputs.summary)


class TestInputValidation:
    """입력 검증"""

    def test_대상이_비면_거부한다(self) -> None:
        """
        목적: 빈 축으로 돌면 아무것도 재지 않은 결과가 정상처럼 나온다

        Given: 빈 대상 목록
        When: 실행했을 때
        Then: ValueError 가 난다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="대상"):
            run_strategy([])

    def test_한도가_비면_거부한다(self, tmp_path: Path) -> None:
        """
        목적: 같은 이유로 한도 축도 막는다

        Given: 빈 한도 목록
        When: 실행했을 때
        Then: ValueError 가 난다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="한도"):
            run_strategy([_target(tmp_path)], hold_limits=())
