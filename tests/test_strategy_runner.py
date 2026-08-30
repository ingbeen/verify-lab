"""역방향 매매 실행 계층의 계약을 고정한다.

이 계층이 틀리는 방식은 **집계 단위가 어긋나는 것**이다. 신호 하나가 여러 행이 되면
표본이 부풀고 승률이 왜곡되는데, 표는 정상으로 보인다.

핵심 계약은 넷이다.
- 산출물 축은 **대상**뿐이다. 손절 분할과 보유 한도 축은 없다
- 집계는 **신호 단위**다. 신호 하나가 체결 내역 한 행이다
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
    DISPLAY_MEAN_HOLD,
    DISPLAY_RETURN,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_TOTAL,
    HOLD_LIMIT,
    START_YEAR,
    STOP_LOSS_LEVEL,
    TARGETS,
    Target,
)
from verify_lab.strategy.runner import (
    IDENTITY_COLUMNS,
    KEY_HOLD_LIMIT,
    KEY_RULE,
    KEY_STOP_LEVEL,
    KEY_TARGETS,
    StrategyOutputs,
    run_strategy,
)
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
    """합성 시세로 돈 실행 결과 (모듈 안에서 한 번만 만든다)."""
    return run_strategy([_target(tmp_path_factory.mktemp("strategy"))])


class TestAxes:
    """산출물 축 계약"""

    def test_집계는_대상마다_한_줄이다(self, outputs: StrategyOutputs) -> None:
        """
        목적: 산출물 축이 대상 하나뿐인지 고정한다

        손절 분할과 보유 한도 축을 걷어냈으므로 대상 하나가 집계 한 줄이다.

        Given: 대상 하나로 돈 실행 결과
        When: 집계 행 수를 봤을 때
        Then: 1행이다
        """
        # Given / When / Then
        assert len(outputs.summary) == 1

    def test_식별_컬럼이_두_표에_모두_앞에_붙는다(self, outputs: StrategyOutputs) -> None:
        """
        목적: 조합을 한 파일에 쌓아도 어느 행이 어떤 설정인지 행 자체로 알 수 있게 한다

        Given: 실행 결과의 두 표
        When: 앞쪽 컬럼을 봤을 때
        Then: 식별 컬럼이 정의된 순서 그대로 앞에 있다
        """
        # Given / When / Then
        for table in (outputs.trades, outputs.summary):
            assert list(table.columns[: len(IDENTITY_COLUMNS)]) == list(IDENTITY_COLUMNS)

    def test_식별_컬럼은_세_개다(self) -> None:
        """
        목적: 보유 한도 축이 사라진 것을 값으로 고정한다

        Given: 식별 컬럼 정의
        When: 개수를 봤을 때
        Then: 종목·파라미터·시작연도 셋이다
        """
        # Given / When / Then
        assert len(IDENTITY_COLUMNS) == 3

    def test_체결_내역은_신호마다_한_행이다(self, outputs: StrategyOutputs) -> None:
        """
        목적: 조각 축이 사라진 것을 고정한다

        3분할이던 시절에는 신호 하나가 세 행이었다. 그 상태로 표본을 세면
        **표본이 세 배로 부풀고 승률이 왜곡된다.**

        Given: 실행 결과
        When: 날짜별 행 수를 셌을 때
        Then: 모든 날짜가 한 행이다
        """
        # Given / When
        counted = outputs.trades.groupby(DISPLAY_DATE).size()

        # Then
        assert set(counted) == {1}
        assert len(outputs.trades) == int(outputs.summary.iloc[0][DISPLAY_SIGNAL_COUNT])


class TestAggregation:
    """집계 계약"""

    def test_합계는_신호별_수익률의_합이다(self, outputs: StrategyOutputs) -> None:
        """
        목적: 집계를 **원값으로** 하는지 고정한다

        반올림된 표에서 다시 평균을 내면 이중 반올림으로 합계가 어긋난다.

        Given: 실행 결과
        When: 체결 내역의 수익률을 직접 더했을 때
        Then: 집계의 합계와 허용오차 안에서 같다
        """
        # Given
        row = outputs.summary.iloc[0]

        # When
        counted = float(outputs.trades[DISPLAY_RETURN].sum())

        # Then
        assert float(row[DISPLAY_TOTAL]) == pytest.approx(counted, abs=RATE_TOLERANCE)

    def test_평균_보유일은_한도를_넘지_않는다(self, outputs: StrategyOutputs) -> None:
        """
        목적: 보유일이 한도 안에 있는지 고정한다 (경계 조건)

        Given: 실행 결과
        When: 평균 보유일을 봤을 때
        Then: 1 이상 한도 이하다
        """
        # Given / When
        mean_hold = float(outputs.summary.iloc[0][DISPLAY_MEAN_HOLD])

        # Then
        assert 1.0 <= mean_hold <= HOLD_LIMIT


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
            results.append(run_strategy([target]).trades)

        # When
        merged = results[1].merge(results[0], on=[DISPLAY_DATE], suffixes=("_cut", "_whole"))

        # Then
        assert not merged.empty
        assert merged[f"{DISPLAY_RETURN}_cut"].tolist() == merged[f"{DISPLAY_RETURN}_whole"].tolist()


class TestTargetsInvariant:
    """매매 대상과 규칙 상수의 불변조건"""

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

    def test_손절선은_단일_5퍼센트다(self) -> None:
        """
        목적: 확정된 손절선을 값으로 고정한다

        **-5% 는 성적이 가장 좋아서가 아니라 갭손절이 0건이 되는 첫 지점이라 고른 값**이다.
        -4%~-10% 는 회당 평균이 +1.27~+1.46% 로 평평해 값 선택이 결과를 만들지 않는다.

        Given: 손절선 상수
        When: 값을 봤을 때
        Then: 0.05 하나다
        """
        # Given / When / Then
        assert STOP_LOSS_LEVEL == 0.05

    def test_보유_한도는_D_플러스_2다(self) -> None:
        """
        목적: 확정된 보유 한도를 값으로 고정한다

        3일 구간은 평균 우연확률이 0.2917 로 근거가 없다.

        Given: 보유 한도 상수
        When: 값을 봤을 때
        Then: 2 다
        """
        # Given / When / Then
        assert HOLD_LIMIT == 2

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

    def test_적용한_규칙이_요약에_남는다(self, outputs: StrategyOutputs) -> None:
        """
        목적: 산출물만 보고 어떤 손절선·한도로 돌았는지 알 수 있게 한다

        Given: 실행 결과의 요약
        When: 규칙 항목을 봤을 때
        Then: 손절선(%)과 보유 한도가 남아 있다
        """
        # Given / When
        rule = outputs.meta[KEY_RULE]

        # Then
        assert rule[KEY_STOP_LEVEL] == pytest.approx(STOP_LOSS_LEVEL * RATE_TO_PERCENT, abs=RATE_TOLERANCE)
        assert rule[KEY_HOLD_LIMIT] == HOLD_LIMIT


class TestSamplePreservation:
    """표본 보존 — 데이터 끝을 넘어가 버려진 신호가 건수로 남는다 (tests/CLAUDE.md 필수)."""

    def _trimmed_outputs(self, directory: Path) -> StrategyOutputs:
        """시세를 **마지막 신호일에서 끝나게** 잘라 실행한다.

        진입 다음 거래일이 아예 없으므로 그 신호는 **이익이든 손실이든 체결을 만들 수 없다.**

        신호일 인덱스는 `집계 시작 + 오프셋 + 1` 이다 — 등락률이 심긴 날의 **다음 종가**가
        그 등락을 갖기 때문이다. 시세 길이를 그보다 하나 크게 잡으면 신호일이 마지막 행이 된다.
        """
        last_offset = SIGNAL_PLACEMENTS[-1][0]
        rows = _accumulation_index(1_400) + last_offset + 2

        return run_strategy([_target(directory, rows=rows)])

    def test_체결하지_못한_신호가_제외_건수로_남는다(self, tmp_path: Path) -> None:
        """
        목적: 보유 한도가 데이터 끝을 넘어간 신호를 **조용히 버리지 않는다.**
              건수를 보고하지 않으면 표본이 줄어든 사실이 산출물에서 보이지 않는다.

        Given: 마지막 신호의 보유 구간이 잘린 시세
        When: 실행하면
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
        When: 실행하면
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
        When: 실행하면
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
