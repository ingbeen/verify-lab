"""매매 산출물의 «공통 컬럼과 파일 이름» 계약을 세 매매법에서 한꺼번에 고정한다.

같은 뜻의 표가 매매법마다 **다른 파일명·다른 컬럼·다른 값 형식**으로 나오고 있었다.
성적표가 `summary_by_target.csv`(15컬럼) · `summary_by_cell.csv`(21) · `performance.csv`(23)
셋이었고, `손절선(%)` 은 한쪽이 `"5.0"`(문자열·양수) 다른 쪽이 `-5.0`(실수·음수)이었다.
**SoT 가 없어서 갈린 것**이지 설계가 달라서가 아니다.

고정하는 계약은 일곱이다.

- 성적표는 `성적표.csv`, 거래내역은 `거래내역.csv` 이고 **이름은 상수 한 곳에서 온다**
- 세 성적표가 **같은 공통 컬럼을 같은 순서로** 갖는다. 매매법 고유 컬럼만 뒤에 붙는다
- `손절선(%)` 값은 **음수 실수**이고 무손절만 문자열이다
- 역방향 성적표의 `방향` 은 **`역방향 전체` 한 값**이다 — 그 행이 폭등·폭락을 합친 성적이다
- 역방향 성적표도 **구간 5행**이고, 표본이 하한에 못 미쳐도 행이 남는다 (측정의 원칙 17)
- `사건` 은 **구간별**로 나오고 구간 분할은 `strategy/periods.py` 하나가 소유한다
- **구현 못하는 칸은 `0` 이 아니라 빈칸**이다 — 0 은 「손절이 걸리지 않았다」로 읽힌다

**기대 컬럼 목록을 손으로 박아 둔다.** 프로덕션 상수를 import 해서 비교하면 그 상수를 고치는
순간 테스트가 함께 따라와 아무것도 고정하지 못한다
(`tests/CLAUDE.md` 「픽스처가 코드와 같은 가정을 하면 그 버그는 영원히 안 잡힙니다」).
"""

from collections.abc import Iterator, Sequence
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from verify_lab.common_constants import (
    BASE_DIR,
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
    PRICE_DECIMALS_KRW,
)
from verify_lab.report.constants import DISPLAY_EXCLUDED
from verify_lab.strategy import month_end_runner, option_expiry_runner
from verify_lab.strategy.constants import (
    DISPLAY_DIRECTION,
    DISPLAY_GAP_STOP_COUNT,
    DISPLAY_INTRADAY_STOP_COUNT,
    DISPLAY_JUDGEABLE,
    DISPLAY_PERIOD,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_STOP_LEVEL,
    DISPLAY_TICKER,
    DISPLAY_TOTAL,
    JUDGEABLE_NO,
    NO_STOP_LABEL,
    PERIODS,
    ExpiryCell,
    Target,
)
from verify_lab.strategy.month_end_runner import TradingOutputs, run_month_end_trading
from verify_lab.strategy.option_expiry_runner import ExpiryOutputs, run_option_expiry_trading
from verify_lab.strategy.reverse_runner import StrategyOutputs, run_reverse_trading
from verify_lab.studies.month_end.constants import EXECUTION_ROLE_NONE, EXECUTION_ROLE_UP
from verify_lab.studies.month_end.constants import Dataset as MonthEndDataset
from verify_lab.studies.option_expiry.constants import FRIDAY, US_MONTHLY_EXPIRY
from verify_lab.studies.option_expiry.constants import Dataset as ExpiryDataset
from verify_lab.studies.reverse.constants import DISPLAY_DIRECTION_REVERSE_ALL, EXTREME_DIRECTION_LABELS
from verify_lab.studies.reverse.constants import Dataset as ReverseDataset

# ============================================================
# 계약 — 손으로 박아 둔 기대 컬럼
# ============================================================

# 성적표의 공통 컬럼. **종목과 매매법 축 다음에 이 순서로 온다.**
# 순서까지 계약이다 — 이름만 비교하면 재배열이 조용히 통과한다.
# 앞 세 개가 식별 컬럼이고 `구간` 부터가 `periods.period_rows` 의 소유다
SUMMARY_COMMON_COLUMNS = (
    "방향",
    "손절선(%)",
    "손절적용",
    "구간",
    "신호",
    "제외",
    "합계(%)",
    "평균(%)",
    "승률(%)",
    "손익비",
    "손익분기 승률(%)",
    "질 때 표본",
    "최고(%)",
    "최악(%)",
    "표준편차(%)",
    "갭손절",
    "장중손절",
    "평균 보유일",
    "판정가능",
    "구간 시작일",
    "구간 종료일",
)

# 거래내역의 공통 컬럼. **`청산 목표일` 이 이 목록 «안»에 끼므로**(옵션 만기일만, 진입가 다음)
# 두 토막으로 나눈다
TRADE_COMMON_HEAD = ("방향", "손절선(%)", "손절적용", "진입일", "진입가")
TRADE_COMMON_TAIL = ("청산일", "보유일", "청산가", "수익률(%)", "청산 사유")

# 매매법 축 — 종목 바로 다음에 온다. **역방향만 두 칸**이다
AXIS_REVERSE = ("파라미터", "시작연도")
AXIS_OPTION_EXPIRY = ("만기월",)
AXIS_MONTH_END = ("월",)

# 매매법 고유 컬럼 — 맨 뒤에 붙는다. 역방향만 있다
TAIL_REVERSE_SUMMARY = ("사건",)
TAIL_REVERSE_TRADES = ("등락률(%)", "사건 번호")

# 옵션 만기일만 갖는 거래내역 컬럼
EXPIRY_TARGET_DATE_COLUMN = "청산 목표일"

# ============================================================
# 합성 시세
# ============================================================

# 합성 시세 구간. 12개월이 다 차고 만기일이 해마다 나오려면 몇 해가 필요하다
SYNTHETIC_START = "2016-01-04"
SYNTHETIC_END = "2025-12-31"

# 합성 시세를 만드는 난수 시드. 시드 없는 난수는 금지다
SYNTHETIC_SEED = 20260911

# 순위 축적 구간에 심는 등락의 크기. 집계 구간에서는 이보다 큰 등락만 신호가 된다
ACCUMULATION_SHOCK = 0.05

# 집계 구간에 심는 등락의 크기. 순위 컷 안에 들어와 역방향 신호가 된다
SIGNAL_SHOCK = 0.09

# 역방향 집계 시작연도. **축적 구간이 끝난 다음 해**여야 축적분이 신호로 세어지지 않는다
REVERSE_START_YEAR = 2017

# 신호를 심는 위치. 구간 전체에 퍼뜨려 다섯 구간 모두에 표본이 들어가게 한다
SIGNAL_POSITIONS = tuple(400 + order * 150 for order in range(14))

# **앞쪽에만 심은 위치.** 데이터가 2025년까지 가므로 최근 5년 구간의 표본이 0건이 된다 —
# 「표본 0건이면 0 이 아니라 빈칸」 계약을 스킵 없이 검사하려고 둔다
EARLY_SIGNAL_POSITIONS = tuple(range(400, 700, 40))

# 옵션 만기일 대상 칸의 만기월
EXPIRY_MONTH = 9


def _closes(count: int, positions: Sequence[int]) -> np.ndarray:
    """순위 축적분과 신호가 심긴 종가 계열을 만든다.

    Args:
        count: 거래일 수
        positions: 신호를 심을 위치. **구간마다 표본을 조절하는 손잡이다** —
            앞쪽에만 심으면 최근 구간이 0건이 된다

    Returns:
        종가 배열
    """
    rng = np.random.default_rng(SYNTHETIC_SEED)
    changes = rng.normal(0.0003, 0.006, count - 1)

    # 1. 집계 시작 전에 순위 컷을 채운다 (신호가 아니다)
    for offset in range(25):
        changes[offset * 8] = ACCUMULATION_SHOCK if offset % 2 else -ACCUMULATION_SHOCK

    # 2. 집계 구간에 더 큰 등락을 심는다 — 이쪽이 역방향 신호가 된다
    for order, position in enumerate(positions):
        changes[position] = SIGNAL_SHOCK if order % 2 else -SIGNAL_SHOCK

    return 10_000.0 * np.cumprod(np.concatenate([[1.0], 1.0 + changes]))


def _market_frame(positions: Sequence[int] = SIGNAL_POSITIONS) -> pd.DataFrame:
    """장중 등락이 있는 합성 ETF 시세를 만든다.

    **고가·저가를 벌려 둔다** — 장중 손절이 실제로 걸리는지 보려면 일중 범위가 있어야 한다.

    Args:
        positions: 신호를 심을 위치

    Returns:
        시세 스키마 DataFrame
    """
    days = pd.bdate_range(SYNTHETIC_START, SYNTHETIC_END)
    closes = _closes(len(days), positions)
    opens = np.concatenate([[closes[0]], closes[:-1] * 1.001])

    return pd.DataFrame(
        {
            COL_DATE: days.strftime("%Y-%m-%d"),
            COL_OPEN: np.round(opens),
            COL_HIGH: np.round(np.maximum(opens, closes) * 1.01),
            COL_LOW: np.round(np.minimum(opens, closes) * 0.99),
            COL_CLOSE: np.round(closes),
            COL_VOLUME: 1_000_000,
        }
    )


def _write_market(directory: Path, ticker: str, positions: Sequence[int] = SIGNAL_POSITIONS) -> Path:
    """합성 ETF 시세를 임시 폴더에 쓴다.

    Args:
        directory: 저장할 폴더
        ticker: 종목 코드
        positions: 신호를 심을 위치

    Returns:
        저장된 파일 경로
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / MARKET_FILE_TEMPLATE.format(ticker=ticker)
    _market_frame(positions).to_csv(path, index=False)

    return path


def _reverse_target(path: Path, *, rank_cut: int = 10) -> Target:
    """합성 시세를 가리키는 역방향 대상을 만든다.

    Args:
        path: 시세 파일 경로
        rank_cut: 순위 컷

    Returns:
        매매 대상
    """
    return Target(
        dataset=ReverseDataset(
            key="synthetic",
            ticker="합성 ETF",
            price_basis="원본가",
            path=path,
            price_decimals=PRICE_DECIMALS_KRW,
        ),
        rank_cut=rank_cut,
        start_year=REVERSE_START_YEAR,
    )


def _write_index(directory: Path, ticker: str) -> Path:
    """합성 지수 계열을 임시 폴더에 쓴다.

    **시가·고가·저가가 없다.** 실제 코스닥150 지수가 그렇고, 그래서 장중 손절을 잴 수 없다.

    Args:
        directory: 저장할 폴더
        ticker: 지수 코드

    Returns:
        저장된 파일 경로
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / INDEX_FILE_TEMPLATE.format(ticker=ticker)
    frame = _market_frame()
    pd.DataFrame({COL_DATE: frame[COL_DATE], COL_VALUE: frame[COL_CLOSE] / 10.0}).to_csv(path, index=False)

    return path


# ============================================================
# 실행 결과 픽스처 — 모듈마다 한 번만 돈다
# ============================================================


@pytest.fixture(scope="module")
def reverse_outputs(tmp_path_factory: pytest.TempPathFactory) -> StrategyOutputs:
    """합성 시세로 돈 역방향 매매 결과."""
    directory = tmp_path_factory.mktemp("reverse")

    return run_reverse_trading([_reverse_target(_write_market(directory, "SYN"))])


@pytest.fixture(scope="module")
def expiry_outputs(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ExpiryOutputs]:
    """합성 시세로 돈 옵션 만기일 매매 결과.

    `collect_entries` 가 `MARKET_DIR` 에서 파일을 찾고 `_dataset` 이 `DATASETS` 를 훑으므로
    **두 이름을 runner 모듈에서** 패치한다 — import 시점에 그 모듈이 값을 캡처한다.
    """
    directory = tmp_path_factory.mktemp("expiry")
    _write_market(directory, "SYN")
    dataset = ExpiryDataset(
        key="synthetic",
        ticker="합성 ETF",
        rule=US_MONTHLY_EXPIRY,
        file_name=MARKET_FILE_TEMPLATE.format(ticker="SYN"),
        price_decimals=PRICE_DECIMALS_KRW,
        exit_weekdays=(FRIDAY,),
    )

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(option_expiry_runner, "MARKET_DIR", directory)
        patch.setattr(option_expiry_runner, "DATASETS", (dataset,))
        yield run_option_expiry_trading(
            [ExpiryCell(dataset_key="synthetic", expiry_month=EXPIRY_MONTH, bet_down=False)]
        )


@pytest.fixture(scope="module")
def month_end_outputs(tmp_path_factory: pytest.TempPathFactory) -> TradingOutputs:
    """합성 시세와 합성 지수로 돈 월말 매매 결과.

    **지수를 함께 넣는다** — 장중 손절을 못 거는 대상이 있어야 `손절적용` 과 무손절 표기가 검사된다.
    """
    directory = tmp_path_factory.mktemp("month_end")
    _write_market(directory, "SYN")
    _write_index(directory, "SYNIDX")

    etf = MonthEndDataset(
        ticker="SYN",
        label="합성 ETF",
        directory=directory,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS_KRW,
        is_index=False,
        execution_role=EXECUTION_ROLE_UP,
    )
    index = MonthEndDataset(
        ticker="SYNIDX",
        label="합성 지수",
        directory=directory,
        file_template=INDEX_FILE_TEMPLATE,
        price_column=COL_VALUE,
        price_decimals=PRICE_DECIMALS,
        is_index=True,
        execution_role=EXECUTION_ROLE_NONE,
    )

    return run_month_end_trading((etf, index))


def _expected_summary(axis: tuple[str, ...], tail: tuple[str, ...] = ()) -> list[str]:
    """그 매매법의 성적표 기대 컬럼을 만든다.

    Args:
        axis: 매매법 축 컬럼
        tail: 맨 뒤에 붙는 고유 컬럼

    Returns:
        기대 컬럼 목록
    """
    return ["종목", *axis, *SUMMARY_COMMON_COLUMNS, *tail]


def _expected_trades(axis: tuple[str, ...], *, target_date: bool = False, tail: tuple[str, ...] = ()) -> list[str]:
    """그 매매법의 거래내역 기대 컬럼을 만든다.

    Args:
        axis: 매매법 축 컬럼
        target_date: 달력이 지목한 청산 목표일을 싣는지 여부 (옵션 만기일만 참)
        tail: 맨 뒤에 붙는 고유 컬럼

    Returns:
        기대 컬럼 목록
    """
    middle = [EXPIRY_TARGET_DATE_COLUMN] if target_date else []

    return ["종목", *axis, *TRADE_COMMON_HEAD, *middle, *TRADE_COMMON_TAIL, *tail]


class TestSummaryColumns:
    """성적표의 공통 컬럼 — 이름과 «순서»"""

    def test_역방향_성적표가_공통_컬럼을_순서대로_쓴다(self, reverse_outputs: StrategyOutputs) -> None:
        """
        목적: 셋 중 가장 좁았던 표가 공통 형식으로 올라왔는지 고정한다

        Given: 합성 시세로 돈 역방향 결과
        When: 성적표의 컬럼을 봤을 때
        Then: 종목 · 파라미터 · 시작연도 · 공통 21개 · 사건 순이다
        """
        # Given / When / Then
        assert list(reverse_outputs.summary.columns) == _expected_summary(AXIS_REVERSE, TAIL_REVERSE_SUMMARY)

    def test_옵션_만기일_성적표가_공통_컬럼을_순서대로_쓴다(self, expiry_outputs: ExpiryOutputs) -> None:
        """
        목적: 손절선·손절적용이 더해졌는지 고정한다

        Given: 합성 시세로 돈 옵션 만기일 결과
        When: 성적표의 컬럼을 봤을 때
        Then: 종목 · 만기월 · 공통 21개다. `사건` 은 없다
        """
        # Given / When / Then
        assert list(expiry_outputs.grid.columns) == _expected_summary(AXIS_OPTION_EXPIRY)

    def test_월말_성적표가_공통_컬럼을_순서대로_쓴다(self, month_end_outputs: TradingOutputs) -> None:
        """
        목적: 기준이 된 표가 그대로 유지됐는지 고정한다

        Given: 합성 시세로 돈 월말 결과
        When: 성적표의 컬럼을 봤을 때
        Then: 종목 · 월 · 공통 21개다
        """
        # Given / When / Then
        assert list(month_end_outputs.performance.columns) == _expected_summary(AXIS_MONTH_END)

    def test_세_성적표의_공통_부분이_완전히_같다(
        self,
        reverse_outputs: StrategyOutputs,
        expiry_outputs: ExpiryOutputs,
        month_end_outputs: TradingOutputs,
    ) -> None:
        """
        목적: 매매법 축과 고유 컬럼을 뺀 나머지가 한 벌임을 고정한다

        이 계약이 깨지면 세 산출물을 나란히 놓고 읽을 수 없다.

        Given: 세 매매법의 성적표
        When: 매매법 축과 고유 컬럼을 뺀 컬럼 목록을 비교했을 때
        Then: 셋이 같다
        """
        # Given
        axes = {*AXIS_REVERSE, *AXIS_OPTION_EXPIRY, *AXIS_MONTH_END, "종목", *TAIL_REVERSE_SUMMARY}

        # When
        common = [
            [column for column in table.columns if column not in axes]
            for table in (reverse_outputs.summary, expiry_outputs.grid, month_end_outputs.performance)
        ]

        # Then
        assert common[0] == common[1] == common[2] == list(SUMMARY_COMMON_COLUMNS)


class TestTradeColumns:
    """거래내역의 공통 컬럼"""

    def test_역방향_거래내역이_공통_컬럼을_순서대로_쓴다(self, reverse_outputs: StrategyOutputs) -> None:
        """
        목적: 청산일·청산가가 생겼고 `날짜` 가 `진입일` 로 바뀌었는지 고정한다

        청산 지점이 없으면 사용자가 차트로 대조할 수 없다 (측정의 원칙 8).

        Given: 합성 시세로 돈 역방향 결과
        When: 거래내역의 컬럼을 봤을 때
        Then: 공통 컬럼 뒤에 등락률·사건 번호가 붙는다
        """
        # Given / When / Then
        assert list(reverse_outputs.trades.columns) == _expected_trades(AXIS_REVERSE, tail=TAIL_REVERSE_TRADES)

    def test_옵션_만기일_거래내역이_공통_컬럼을_순서대로_쓴다(self, expiry_outputs: ExpiryOutputs) -> None:
        """
        목적: 손절선·손절적용이 더해졌고 청산 목표일은 제자리인지 고정한다

        Given: 합성 시세로 돈 옵션 만기일 결과
        When: 거래내역의 컬럼을 봤을 때
        Then: 진입가 다음에 청산 목표일이 끼어 있다
        """
        # Given / When / Then
        assert list(expiry_outputs.trades.columns) == _expected_trades(AXIS_OPTION_EXPIRY, target_date=True)

    def test_월말_거래내역이_공통_컬럼을_순서대로_쓴다(self, month_end_outputs: TradingOutputs) -> None:
        """
        목적: 기준이 된 표가 그대로 유지됐는지 고정한다

        Given: 합성 시세로 돈 월말 결과
        When: 거래내역의 컬럼을 봤을 때
        Then: 종목 · 월 · 공통 10개다
        """
        # Given / When / Then
        assert list(month_end_outputs.trades.columns) == _expected_trades(AXIS_MONTH_END)


class TestStopLevelFormat:
    """`손절선(%)` 의 값 형식 — 음수 실수 하나"""

    @staticmethod
    def _levels(table: pd.DataFrame) -> set[object]:
        """손절선 컬럼의 서로 다른 값을 모은다."""
        return set(table[DISPLAY_STOP_LEVEL].tolist())

    def test_역방향_손절선은_음수_실수다(self, reverse_outputs: StrategyOutputs) -> None:
        """
        목적: 확정 손절선이 행 안에서 읽히는지 고정한다

        산출물만 보고 −5% 성적인지 무손절인지 판별할 수 없으면 그 표는 근거가 못 된다.

        Given: 합성 시세로 돈 역방향 결과
        When: 성적표의 손절선 값을 봤을 때
        Then: −5.0 하나뿐이다
        """
        # Given / When / Then
        assert self._levels(reverse_outputs.summary) == {-5.0}

    def test_옵션_만기일_손절선은_음수_실수다(self, expiry_outputs: ExpiryOutputs) -> None:
        """
        목적: 손절선이 하나뿐일 때도 컬럼이 나오는지 고정한다

        전에는 `with_stop_column` 이 그 컬럼을 일부러 뺐다.

        Given: 합성 시세로 돈 옵션 만기일 결과
        When: 성적표의 손절선 값을 봤을 때
        Then: −5.0 하나뿐이다
        """
        # Given / When / Then
        assert self._levels(expiry_outputs.grid) == {-5.0}

    def test_월말_손절선은_음수_실수와_무손절이다(self, month_end_outputs: TradingOutputs) -> None:
        """
        목적: 양수 문자열(`"5.0"`)이 남아 있지 않은지 고정한다

        Given: 합성 시세로 돈 월말 결과
        When: 성적표의 손절선 값을 봤을 때
        Then: 전부 음수 실수이고 무손절만 문자열이다
        """
        # Given
        levels = self._levels(month_end_outputs.performance)

        # When
        numeric = {level for level in levels if level != NO_STOP_LABEL}

        # Then
        assert NO_STOP_LABEL in levels
        assert numeric and all(isinstance(level, float) and level < 0 for level in numeric)

    def test_거래내역의_손절선도_같은_형식이다(self, month_end_outputs: TradingOutputs) -> None:
        """
        목적: 두 표의 값이 갈리면 조인이 안 된다는 것을 고정한다

        Given: 합성 시세로 돈 월말 결과
        When: 성적표와 거래내역의 손절선 값 집합을 비교했을 때
        Then: 같다
        """
        # Given / When / Then
        assert self._levels(month_end_outputs.trades) == self._levels(month_end_outputs.performance)


class TestReverseDirection:
    """역방향의 `방향` — 성적표와 거래내역이 다른 것을 가리킨다"""

    def test_성적표의_방향은_역방향_전체_하나다(self, reverse_outputs: StrategyOutputs) -> None:
        """
        목적: 합친 성적에 `위`·`아래` 를 적지 않는다는 것을 고정한다

        그 행은 폭등 신호와 폭락 신호를 한 표본으로 묶은 것이라 어느 쪽도 아니다.

        Given: 합성 시세로 돈 역방향 결과
        When: 성적표의 방향 값을 봤을 때
        Then: `역방향 전체` 하나뿐이다
        """
        # Given / When / Then
        assert set(reverse_outputs.summary[DISPLAY_DIRECTION]) == {DISPLAY_DIRECTION_REVERSE_ALL}

    def test_거래내역의_방향은_신호_방향_그대로다(self, reverse_outputs: StrategyOutputs) -> None:
        """
        목적: 거래내역의 `폭등`/`폭락` 을 거는 방향으로 환산하지 않았음을 고정한다

        환산하면 기존 컬럼의 **뜻이 조용히 바뀌고** 규칙 문서 §5 원자료 표와 어긋난다.

        Given: 합성 시세로 돈 역방향 결과
        When: 거래내역의 방향 값을 봤을 때
        Then: 폭등·폭락 안에 든다
        """
        # Given / When / Then
        assert set(reverse_outputs.trades[DISPLAY_DIRECTION]) <= set(EXTREME_DIRECTION_LABELS.values())


class TestReversePeriods:
    """역방향 성적표의 구간 축 (측정의 원칙 17)"""

    def test_대상마다_구간_다섯_행이다(self, reverse_outputs: StrategyOutputs) -> None:
        """
        목적: 역방향도 구간으로 쪼개진다는 것을 고정한다

        균등 2분할만으로는 신호가 식는 것을 놓친다.

        Given: 대상 하나로 돈 역방향 결과
        When: 성적표의 구간 컬럼을 봤을 때
        Then: `PERIODS` 순서 그대로 다섯 행이다
        """
        # Given / When / Then
        assert reverse_outputs.summary[DISPLAY_PERIOD].tolist() == list(PERIODS)

    def test_표본이_하한에_못_미쳐도_행이_남는다(self, tmp_path: Path) -> None:
        """
        목적: 행이 사라지면 그 구간을 못 봤다는 사실 자체를 모른다는 것을 고정한다

        Given: 신호가 적게 심긴 합성 시세
        When: 성적표를 봤을 때
        Then: 다섯 행이 모두 있고 하한 미달 구간은 `판정가능` 이 「아니오」다
        """
        # Given
        target = _reverse_target(_write_market(tmp_path / "sparse", "SYN", EARLY_SIGNAL_POSITIONS))

        # When
        summary = run_reverse_trading([target]).summary

        # Then
        assert summary[DISPLAY_PERIOD].tolist() == list(PERIODS)
        assert (summary.loc[summary[DISPLAY_SIGNAL_COUNT] < 10, DISPLAY_JUDGEABLE] == JUDGEABLE_NO).all()

    def test_구간_행의_제외는_세_매매법_모두_비어_있다(
        self,
        reverse_outputs: StrategyOutputs,
        expiry_outputs: ExpiryOutputs,
        month_end_outputs: TradingOutputs,
    ) -> None:
        """
        목적: 같은 컬럼이 매매법마다 다른 뜻이 되지 않게 고정한다

        제외된 신호는 보유 구간이 데이터 끝을 넘어간 것이라 **언제나 가장 최근**이다.
        구간 행에 `0` 을 적으면 뒤 절반·최근 N년이 「제외 0건」이라고 **거짓으로 주장**한다.
        전에는 월말만 이 컬럼을 아예 받지 못해 **구조적으로 항상 0** 이기도 했다.

        Given: 세 매매법의 성적표
        When: 전체가 아닌 구간 행의 제외 칸을 봤을 때
        Then: 셋 다 비어 있다
        """
        # Given / When / Then
        for table in (reverse_outputs.summary, expiry_outputs.grid, month_end_outputs.performance):
            others = table[table[DISPLAY_PERIOD] != PERIODS[0]]
            assert not others.empty
            assert others[DISPLAY_EXCLUDED].isna().all()

    def test_표본이_0건인_구간은_지표를_비운다(self, tmp_path: Path) -> None:
        """
        목적: 구현 못하는 칸이 0 이 아니라 빈칸임을 고정한다

        0 은 「손절이 걸리지 않았다」·「손실도 이익도 없었다」로 읽히는데 실제로는 「잰 적이 없다」다.

        Given: 신호를 앞쪽에만 심은 합성 시세 (최근 5년 구간이 0건이 된다)
        When: 표본이 0건인 구간 행을 봤을 때
        Then: 합계·갭손절·장중손절이 비어 있다
        """
        # Given
        target = _reverse_target(_write_market(tmp_path / "early", "SYN", EARLY_SIGNAL_POSITIONS))

        # When
        summary = run_reverse_trading([target]).summary
        empty = summary[summary[DISPLAY_SIGNAL_COUNT] == 0]

        # Then
        assert not empty.empty, "표본 0건 구간이 없어 계약을 검사하지 못했습니다 — 신호 위치를 앞으로 옮기세요"
        for column in (DISPLAY_TOTAL, DISPLAY_GAP_STOP_COUNT, DISPLAY_INTRADAY_STOP_COUNT):
            assert empty[column].isna().all()


class TestEventCount:
    """`사건` — 구간별로 나오고 분할은 공유 모듈이 소유한다"""

    def test_사건이_구간마다_따로_세어진다(self, reverse_outputs: StrategyOutputs) -> None:
        """
        목적: 전체 구간의 사건 수를 모든 행에 복사하지 않았음을 고정한다

        같은 사건에서 파생된 신호를 묶어 세는 것이 측정의 원칙 5 이며, 구간을 쪼개면
        그 수도 구간마다 달라야 한다.

        Given: 합성 시세로 돈 역방향 결과
        When: 전체 행과 앞 절반 행의 사건 수를 비교했을 때
        Then: 앞 절반이 전체보다 작다
        """
        # Given
        summary = reverse_outputs.summary.set_index(DISPLAY_PERIOD)

        # When
        whole = int(summary.loc[PERIODS[0], TAIL_REVERSE_SUMMARY[0]])
        first_half = int(summary.loc[PERIODS[1], TAIL_REVERSE_SUMMARY[0]])

        # Then
        assert first_half < whole

    def test_사건을_주지_않은_매매법에는_그_컬럼이_없다(self, expiry_outputs: ExpiryOutputs, month_end_outputs: TradingOutputs) -> None:
        """
        목적: 잴 수 없는 것을 빈칸으로 싣지 않고 **컬럼을 내지 않는다**는 정책을 고정한다

        옵션 만기일과 월말은 신호가 연 1회씩이라 신호 = 사건이다.

        Given: 두 매매법의 성적표
        When: 사건 컬럼을 찾았을 때
        Then: 없다
        """
        # Given / When / Then
        for table in (expiry_outputs.grid, month_end_outputs.performance):
            assert TAIL_REVERSE_SUMMARY[0] not in table.columns

    def test_구간_분할은_periods_가_소유한다(self) -> None:
        """
        목적: runner 가 구간 마스크를 다시 만들지 않았음을 고정한다

        복제하면 구간 분할이 두 벌이 되어 같은 원칙이 다른 답을 낸다 (절대 원칙 5).

        Given: 매매 계층의 runner 소스
        When: 구간 경계를 만드는 표현을 찾았을 때
        Then: `periods.py` 밖에는 없다
        """
        # Given
        runners = sorted((BASE_DIR / "src" / "verify_lab" / "strategy").glob("*_runner.py"))
        assert runners, "runner 파일을 찾지 못했습니다"

        # When / Then
        for runner in runners:
            source = runner.read_text(encoding="utf-8")
            assert "DateOffset" not in source, f"{runner.name} 이 최근 N년 경계를 직접 만듭니다"
            assert "PERIOD_FIRST_HALF" not in source, f"{runner.name} 이 절반 분할을 직접 만듭니다"


class TestFixedStopTable:
    """`성적표_고정손절.csv` — 손절선을 빼지 않는다"""

    def test_고정손절_표에_손절선이_남는다(self, month_end_outputs: TradingOutputs) -> None:
        """
        목적: ETF 행과 지수 행이 다른 규칙으로 만들어진 성적임을 표 안에서 드러낸다

        전에는 이 컬럼을 일부러 드롭했다 — 「전 행이 같은 값」이라는 근거였는데
        이 표에서는 애초에 성립하지 않는다.

        Given: 합성 시세로 돈 월말 결과
        When: 고정손절 표의 컬럼을 봤을 때
        Then: 격자 성적표와 컬럼이 완전히 같다
        """
        # Given / When / Then
        assert list(month_end_outputs.performance_fixed_stop.columns) == list(month_end_outputs.performance.columns)

    def test_지수_행은_무손절이고_ETF_행은_확정_손절선이다(self, month_end_outputs: TradingOutputs) -> None:
        """
        목적: 두 행의 손절선이 실제로 다르다는 것을 값으로 고정한다

        Given: 합성 시세로 돈 월말 결과
        When: 고정손절 표의 손절선 값을 봤을 때
        Then: 음수 실수와 무손절이 함께 있다
        """
        # Given
        levels = set(month_end_outputs.performance_fixed_stop[DISPLAY_STOP_LEVEL].tolist())

        # When / Then
        assert NO_STOP_LABEL in levels
        assert -5.0 in levels

    def test_고정손절_표는_격자에서_골라낸_행이다(self, month_end_outputs: TradingOutputs) -> None:
        """
        목적: 다시 계산하지 않았음을 고정한다 — 같은 값을 두 곳에서 만들면 조용히 갈라진다

        Given: 합성 시세로 돈 월말 결과
        When: 고정손절 표의 행을 격자에서 찾았을 때
        Then: 전부 격자에 그대로 있다
        """
        # Given — **종목을 키에 넣는다.** 빼면 다른 대상의 행으로 만족될 수 있고,
        # 같은 값을 가진 행이 둘이면 left merge 가 행을 불려도 드러나지 않는다
        keys = [
            DISPLAY_TICKER,
            month_end_runner.DISPLAY_MONTH,
            DISPLAY_DIRECTION,
            DISPLAY_STOP_LEVEL,
            DISPLAY_PERIOD,
            DISPLAY_TOTAL,
        ]
        fixed = month_end_outputs.performance_fixed_stop

        # When
        merged = fixed.merge(month_end_outputs.performance[keys].drop_duplicates(), on=keys, how="left", indicator=True)

        # Then
        assert len(merged) == len(fixed), "행이 불었습니다 — 키가 행을 특정하지 못합니다"
        assert (merged["_merge"] == "both").all()


class TestFilenames:
    """파일 이름은 상수 한 곳에서 온다"""

    def test_네_파일_이름이_상수로_정의돼_있다(self) -> None:
        """
        목적: 이름이 코드 여러 곳에 흩어진 문자열이던 상태를 닫는다

        Given: 매매 계층의 상수 모듈
        When: 파일명 상수를 읽었을 때
        Then: 네 이름이 한글로 정의돼 있다
        """
        # Given
        from verify_lab.strategy.constants import (
            STOP_GRID_FILENAME,
            SUMMARY_FILENAME,
            SUMMARY_FIXED_STOP_FILENAME,
            TRADES_FILENAME,
        )

        # When / Then
        assert SUMMARY_FILENAME == "성적표.csv"
        assert TRADES_FILENAME == "거래내역.csv"
        assert STOP_GRID_FILENAME == "손절선_격자.csv"
        assert SUMMARY_FIXED_STOP_FILENAME == "성적표_고정손절.csv"

    def test_매매_스크립트에_csv_문자열이_없다(self) -> None:
        """
        목적: 상수를 만들고 연결을 빠뜨리는 것을 막는다

        정의만 하고 두면 규칙을 지킨 것이 아니다 (`src/verify_lab/CLAUDE.md` 상수 관리).

        Given: `scripts/strategy/` 의 실행 스크립트
        When: 소스에서 `.csv` 를 찾았을 때
        Then: 하나도 없다
        """
        # Given
        scripts = sorted((BASE_DIR / "scripts" / "strategy").glob("run_*.py"))
        assert scripts, "매매 스크립트를 찾지 못했습니다"

        # When / Then
        for script in scripts:
            assert ".csv" not in script.read_text(encoding="utf-8"), f"{script.name} 에 파일명이 박혀 있습니다"
