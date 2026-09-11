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

import json
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
from verify_lab.strategy import month_end_runner, option_expiry_runner, periods
from verify_lab.strategy.constants import (
    DISPLAY_DIRECTION,
    DISPLAY_EVENT_COUNT,
    DISPLAY_GAP_STOP_COUNT,
    DISPLAY_INTRADAY_STOP_COUNT,
    DISPLAY_JUDGEABLE,
    DISPLAY_LOSS_AMOUNT,
    DISPLAY_PERIOD,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_STOP_LEVEL,
    DISPLAY_TICKER,
    DISPLAY_TOTAL,
    DISPLAY_WIN_AMOUNT,
    JUDGEABLE_NO,
    NO_STOP_LABEL,
    PERIOD_ALL,
    PERIOD_RECENT_5Y,
    PERIODS,
    TRADES_FILENAME,
    ExpiryCell,
    Target,
)
from verify_lab.strategy.month_end_runner import TradingOutputs, run_month_end_trading
from verify_lab.strategy.option_expiry_runner import ExpiryOutputs, run_option_expiry_trading
from verify_lab.strategy.periods import period_rows
from verify_lab.strategy.reverse_runner import StrategyOutputs, run_reverse_trading
from verify_lab.strategy.run_summary import (
    COST_NOTE,
    KEY_COST,
    KEY_DATASET_FILE,
    KEY_DATASET_LABEL,
    KEY_DATASET_PERIOD,
    KEY_DATASET_ROWS,
    KEY_DATASET_TICKER,
    KEY_DATASETS,
    KEY_NOTES,
    KEY_ROW_COUNTS,
    KEY_RULE,
    KEY_TRACK,
)
from verify_lab.studies.month_end.constants import DATASETS as MONTH_END_DATASETS
from verify_lab.studies.month_end.constants import EXECUTION_ROLE_NONE, EXECUTION_ROLE_UP, MARKET_KOSDAQ
from verify_lab.studies.month_end.constants import Dataset as MonthEndDataset
from verify_lab.studies.option_expiry.constants import DATASETS as EXPIRY_DATASETS
from verify_lab.studies.option_expiry.constants import FRIDAY, US_MONTHLY_EXPIRY
from verify_lab.studies.option_expiry.constants import Dataset as ExpiryDataset
from verify_lab.studies.reverse.constants import DATASETS as REVERSE_DATASETS
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
    # **손익비 바로 뒤에 그 분자·분모를 둔다.** `docs/strategy/투자금_결정.md` §1.2 가
    # 이 두 값의 출처를 성적표로 적어 두었는데 실제로는 없었다. `이길 때(%)` 는 양수,
    # `질 때(%)` 는 **음수**다 — `최악(%)` 과 같은 관용이고 그 문서의 예시와도 부호가 맞는다
    "이길 때(%)",
    "질 때(%)",
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
            ticker="SYN",
            label="합성 ETF",
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
        ticker="SYN",
        label="합성 ETF",
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
        market=MARKET_KOSDAQ,
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
        market=MARKET_KOSDAQ,
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
        Then: 종목 · 파라미터 · 시작연도 · 공통 23개 · 사건 순이다
        """
        # Given / When / Then
        assert list(reverse_outputs.performance.columns) == _expected_summary(AXIS_REVERSE, TAIL_REVERSE_SUMMARY)

    def test_옵션_만기일_성적표가_공통_컬럼을_순서대로_쓴다(self, expiry_outputs: ExpiryOutputs) -> None:
        """
        목적: 손절선·손절적용이 더해졌는지 고정한다

        Given: 합성 시세로 돈 옵션 만기일 결과
        When: 성적표의 컬럼을 봤을 때
        Then: 종목 · 만기월 · 공통 23개다. `사건` 은 없다
        """
        # Given / When / Then
        assert list(expiry_outputs.performance.columns) == _expected_summary(AXIS_OPTION_EXPIRY)

    def test_월말_성적표가_공통_컬럼을_순서대로_쓴다(self, month_end_outputs: TradingOutputs) -> None:
        """
        목적: 기준이 된 표가 그대로 유지됐는지 고정한다

        Given: 합성 시세로 돈 월말 결과
        When: 성적표의 컬럼을 봤을 때
        Then: 종목 · 월 · 공통 23개다
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
            for table in (reverse_outputs.performance, expiry_outputs.performance, month_end_outputs.performance)
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
        assert self._levels(reverse_outputs.performance) == {-5.0}

    def test_옵션_만기일_손절선은_음수_실수다(self, expiry_outputs: ExpiryOutputs) -> None:
        """
        목적: 손절선이 하나뿐일 때도 컬럼이 나오는지 고정한다

        전에는 `with_stop_column` 이 그 컬럼을 일부러 뺐다.

        Given: 합성 시세로 돈 옵션 만기일 결과
        When: 성적표의 손절선 값을 봤을 때
        Then: −5.0 하나뿐이다
        """
        # Given / When / Then
        assert self._levels(expiry_outputs.performance) == {-5.0}

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
        assert set(reverse_outputs.performance[DISPLAY_DIRECTION]) == {DISPLAY_DIRECTION_REVERSE_ALL}

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
        assert reverse_outputs.performance[DISPLAY_PERIOD].tolist() == list(PERIODS)

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
        summary = run_reverse_trading([target]).performance

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
        for table in (reverse_outputs.performance, expiry_outputs.performance, month_end_outputs.performance):
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
        summary = run_reverse_trading([target]).performance
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
        summary = reverse_outputs.performance.set_index(DISPLAY_PERIOD)

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
        for table in (expiry_outputs.performance, month_end_outputs.performance):
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


class TestPayoffAmountColumns:
    """`이길 때(%)` · `질 때(%)` — 부호와 결측"""

    def test_이길_때는_양수이고_질_때는_음수다(self, month_end_outputs: TradingOutputs) -> None:
        """
        목적: 두 열의 부호를 계약으로 고정한다.

        **`최악(%)` 이 음수인 것과 같은 관용**이고 `docs/strategy/투자금_결정.md` §1.2 의
        예시(`0.0138` · `-0.0133`)와도 부호가 맞는다. 둘 다 절대값으로 내면 표를 읽는 사람이
        어느 쪽이 손실인지 이름으로만 판단해야 한다.

        Given: 합성 시세로 돈 월말 결과
        When: 값이 있는 행의 두 열을 봤을 때
        Then: 이길 때는 0 초과, 질 때는 0 미만이다
        """
        # Given
        summary = month_end_outputs.performance
        wins = summary[DISPLAY_WIN_AMOUNT].dropna()
        losses = summary[DISPLAY_LOSS_AMOUNT].dropna()
        assert not wins.empty and not losses.empty, "두 열에 값이 하나도 없습니다"

        # When / Then
        assert (wins > 0).all(), "이길 때가 양수가 아닌 행이 있습니다"
        assert (losses < 0).all(), "질 때가 음수가 아닌 행이 있습니다"

    def test_전승_칸은_질_때만_비고_이길_때는_값이_있다(self) -> None:
        """
        목적: 「진 적이 없다」와 「못 쟀다」를 가른다.

        전승 칸은 손익비가 수학적으로 무한대라 숫자로 못 적지만, **이길 때 평균은 존재한다.**
        둘을 함께 비우면 그 칸의 성적을 읽을 수 없다.

        Given: 전부 이익인 체결 목록
        When: 구간 행을 만들었을 때
        Then: 질 때는 비고 이길 때는 값이 있다
        """
        # Given
        dates = pd.DatetimeIndex(["2020-01-02", "2020-02-03", "2020-03-02"])

        # When
        rows = period_rows(dates, [0.01, 0.02, 0.03], last_day=pd.Timestamp("2020-03-31"))
        overall = rows[0]

        # Then
        assert pd.isna(overall[DISPLAY_LOSS_AMOUNT]), "진 거래가 0건인데 질 때에 값이 있습니다"
        assert overall[DISPLAY_WIN_AMOUNT] == pytest.approx(2.0, abs=1e-9)

    def test_표본이_0건인_구간은_두_열이_모두_빈다(self) -> None:
        """
        목적: 표본이 없는 것을 0 으로 채우지 않는다 (측정의 원칙 17).

        0 은 「이익도 손실도 없었다」로 읽히는데 실제로는 「잰 적이 없다」이다.

        Given: 최근 5년에 진입이 하나도 없는 체결 목록
        When: 구간 행을 만들었을 때
        Then: 그 구간의 두 열이 비어 있다
        """
        # Given — 마지막 거래일보다 10년 넘게 앞선 진입만 둔다
        dates = pd.DatetimeIndex(["2000-01-03", "2000-02-01"])

        # When
        rows = period_rows(dates, [0.01, -0.02], last_day=pd.Timestamp("2020-12-30"))
        recent = next(row for row in rows if row[DISPLAY_PERIOD] == PERIOD_RECENT_5Y)

        # Then
        assert recent[DISPLAY_SIGNAL_COUNT] == 0
        assert pd.isna(recent[DISPLAY_WIN_AMOUNT])
        assert pd.isna(recent[DISPLAY_LOSS_AMOUNT])


class TestIntegerCounts:
    """건수 컬럼은 정수로 나간다 — 빈칸은 빈칸으로 둔 채"""

    # 건수 컬럼. **`제외` 가 `0.0` 으로 나가고 있었다** — 전체 구간엔 정수, 나머지엔 결측이라
    # pandas 열이 실수가 됐다. 같은 구조가 나머지 넷에도 있어 0건 구간이 하나만 생기면
    # 그 열 전체가 `11.0` 로 바뀐다
    COUNT_COLUMNS = ("신호", "제외", "질 때 표본", "갭손절", "장중손절")

    def test_박아_둔_건수_목록이_프로덕션과_어긋나지_않는다(self) -> None:
        """
        목적: 건수 컬럼이 하나 늘었을 때 **검사에서 조용히 빠지는 것**을 막는다

        **목록을 `periods.COUNT_COLUMNS` 로 대체하지 않는다** — 이 파일의 규율은 기대값을
        손으로 박는 것이고(머리말), 상수를 가져오면 그 상수를 고치는 순간 테스트가 따라와
        아무것도 고정하지 못한다. **대신 두 벌이 어긋나면 여기서 실패하게 한다.**

        Given: 손으로 박은 목록과 정수화의 소유자가 아는 목록
        When: 둘을 비교한다
        Then: `사건`(역방향 전용, 별도 테스트가 본다)을 빼면 같다
        """
        # Given
        owned = set(periods.COUNT_COLUMNS)

        # When / Then
        assert set(self.COUNT_COLUMNS) | {DISPLAY_EVENT_COUNT} == owned, (
            f"건수 컬럼이 어긋납니다 — 손으로 박은 목록 {sorted(self.COUNT_COLUMNS)} · " f"프로덕션 {sorted(owned)}"
        )

    @pytest.mark.parametrize("column", COUNT_COLUMNS)
    def test_월말_성적표의_건수_컬럼이_정수형이다(self, month_end_outputs: TradingOutputs, column: str) -> None:
        """
        목적: 같은 행의 `신호` 는 `51` 인데 `제외` 만 `0.0` 으로 나가던 것을 닫는다

        Given: 합성 시세로 돈 월말 결과
        When: 건수 컬럼의 dtype 을 봤을 때
        Then: 결측을 담을 수 있는 정수형이다
        """
        # Given / When / Then
        assert str(month_end_outputs.performance[column].dtype) == "Int64", f"{column} 이 정수형이 아닙니다"

    def test_역방향_사건도_정수형이다(self, reverse_outputs: StrategyOutputs) -> None:
        """
        목적: 매매법 고유 건수 컬럼도 같은 규칙을 받는다

        Given: 합성 시세로 돈 역방향 결과
        When: `사건` 컬럼의 dtype 을 봤을 때
        Then: 결측을 담을 수 있는 정수형이다
        """
        # Given / When / Then
        assert str(reverse_outputs.performance[DISPLAY_EVENT_COUNT].dtype) == "Int64"

    def test_정수형이어도_빈칸은_빈칸으로_저장된다(self, month_end_outputs: TradingOutputs) -> None:
        """
        목적: 정수화가 빈칸을 `0` 으로 바꾸지 않는지 확인한다 — 그러면 원래 문제가 뒤집혀 재발한다

        `제외` 는 전체 구간 행에만 적고 나머지 네 구간은 비운다. `0` 을 적으면
        뒤 절반·최근 N년이 「제외 0건」이라고 거짓으로 주장한다.

        Given: 합성 시세로 돈 월말 결과
        When: 성적표를 CSV 문자열로 뽑았을 때
        Then: 전체 아닌 구간의 `제외` 칸이 빈칸이다
        """
        # Given
        summary = month_end_outputs.performance
        others = summary[summary[DISPLAY_PERIOD] != PERIOD_ALL]
        assert not others.empty

        # When
        text = others.head(1).to_csv(index=False)

        # Then
        assert others[DISPLAY_EXCLUDED].isna().all(), "전체 아닌 구간의 제외가 비어 있지 않습니다"
        assert ",," in text, "빈칸이 값으로 채워졌습니다"


class TestRunSummary:
    """`summary.json` — 세 매매법이 같은 틀을 쓴다"""

    @pytest.fixture
    def summaries(
        self,
        reverse_outputs: StrategyOutputs,
        expiry_outputs: ExpiryOutputs,
        month_end_outputs: TradingOutputs,
    ) -> dict[str, dict[str, object]]:
        """세 매매법의 실행 요약."""
        return {
            "역방향": reverse_outputs.summary,
            "옵션 만기일": expiry_outputs.summary,
            "월말": month_end_outputs.summary,
        }

    def test_세_요약이_같은_최상위_키를_갖는다(self, summaries: dict[str, dict[str, object]]) -> None:
        """
        목적: 만드는 자리·키가 매매법마다 갈리던 것을 닫는다

        전에는 역방향이 `strategy`/`targets`/`rule`/`row_counts`/`notes`,
        옵션 만기일이 **CLI 에서** `cells`/`stop_levels`/`row_counts`,
        월말이 `stop_levels`/`fixed_stop_level`/`cost`/`datasets`/`row_counts` 였다.

        Given: 세 매매법의 실행 요약
        When: 최상위 키를 봤을 때
        Then: 여섯 키가 전부 있다
        """
        # Given
        expected = {KEY_TRACK, KEY_DATASETS, KEY_RULE, KEY_ROW_COUNTS, KEY_COST, KEY_NOTES}

        # When / Then
        for name, summary in summaries.items():
            assert set(summary) == expected, f"{name} 의 요약 키가 다릅니다: {sorted(summary)}"

    def test_대상_범위와_기간이_datasets_에_있다(self, summaries: dict[str, dict[str, object]]) -> None:
        """
        목적: 「범위의 SoT 는 `summary.json` 의 `datasets`」를 세 매매법이 실제로 이행한다

        전에는 **월말만** 그 키를 가졌고, 옵션 만기일은 종목코드를 어디에도 남기지 않았다.

        Given: 세 매매법의 실행 요약
        When: `datasets` 의 한 줄을 봤을 때
        Then: 코드·이름·파일·기간·행 수가 전부 있다
        """
        # Given
        expected = {KEY_DATASET_TICKER, KEY_DATASET_LABEL, KEY_DATASET_FILE, KEY_DATASET_PERIOD, KEY_DATASET_ROWS}

        # When / Then
        for name, summary in summaries.items():
            records = summary[KEY_DATASETS]
            assert isinstance(records, list) and records, f"{name} 의 datasets 가 비었습니다"
            for record in records:
                assert set(record) == expected, f"{name} 의 datasets 한 줄이 다릅니다: {sorted(record)}"

    def test_row_counts_의_키가_파일_이름이다(self, summaries: dict[str, dict[str, object]]) -> None:
        """
        목적: `"performance"` 같은 별칭을 없앤다 — 작업 C 이후 그 이름의 파일은 존재하지 않는다

        파일 이름으로 키잉하면 스크립트가 `summary[row_counts][SUMMARY_FILENAME]` 로 읽으므로
        별칭을 따로 관리할 필요가 없어진다.

        Given: 세 매매법의 실행 요약
        When: `row_counts` 의 키를 봤을 때
        Then: 전부 `.csv` 로 끝나고 성적표·거래내역이 들어 있다
        """
        # Given / When / Then
        for name, summary in summaries.items():
            counts = summary[KEY_ROW_COUNTS]
            assert isinstance(counts, dict)
            assert all(key.endswith(".csv") for key in counts), f"{name} 의 row_counts 키가 파일 이름이 아닙니다: {sorted(counts)}"
            assert TRADES_FILENAME in counts, f"{name} 에 거래내역 행 수가 없습니다"

    def test_비용_표기가_세_매매법_모두에_있다(self, summaries: dict[str, dict[str, object]]) -> None:
        """
        목적: `.claude/rules/strategy.md` 의 맨몸 성적 표기를 월말만 갖고 있던 것을 닫는다

        빠뜨린 것과 일부러 뺀 것을 구별할 수 없으면 다음 사람이 다시 계산한다.

        Given: 세 매매법의 실행 요약
        When: `cost` 를 봤을 때
        Then: 셋 다 같은 문장이다
        """
        # Given / When / Then
        for name, summary in summaries.items():
            assert summary[KEY_COST] == COST_NOTE, f"{name} 의 비용 표기가 다릅니다"

    def test_요약에_옛_slug_가_값으로_남아_있지_않다(self, summaries: dict[str, dict[str, object]]) -> None:
        """
        목적: 작업 B 가 없애려던 이름이 **데이터 값**으로 남아 있던 것을 닫는다

        역방향 요약이 `"strategy": "reverse_trading"` 이라고 적고 있었다 — 폴더는 `reverse` 다.

        Given: 세 매매법의 실행 요약
        When: 요약 전체를 문자열로 봤을 때
        Then: 옛 이름이 하나도 없다
        """
        # Given
        stale = ("reverse_trading", "expiry_trading", "index_extreme", "kosdaq_month_end")

        # When / Then
        for name, summary in summaries.items():
            text = json.dumps(summary, ensure_ascii=False)
            for word in stale:
                assert word not in text, f"{name} 의 요약에 옛 이름 {word} 이 남아 있습니다"

    def test_옵션_만기일_요약을_CLI_가_만들지_않는다(self) -> None:
        """
        목적: `scripts/CLAUDE.md` 의 「CLI 에 도메인 로직 금지」를 되돌린다

        요약을 CLI 에서 조립하면 그 매매법만 규약이 갈리고, 테스트가 닿지 않는 자리에 남는다.

        Given: 옵션 만기일 실행 스크립트
        When: 소스에서 요약 키를 찾았을 때
        Then: 조립부가 없다
        """
        # Given
        script = BASE_DIR / "scripts" / "strategy" / "run_option_expiry_trading.py"

        # When
        source = script.read_text(encoding="utf-8")

        # Then — **`save_run_summary` 에 사전 리터럴을 넘기지 않는다.** 조립부의 흔적이다
        assert "save_run_summary(directory, outputs.summary)" in source, "요약을 runner 에서 받지 않습니다"
        assert "save_run_summary(\n" not in source, "CLI 가 요약을 조립합니다"


class TestDatasetFields:
    """`Dataset` 의 필드 뜻 — 세 모듈에서 같다"""

    def test_세_Dataset_이_코드와_이름을_따로_갖는다(self) -> None:
        """
        목적: 필드 이름이 모듈마다 다른 것을 가리키던 상태를 닫는다

        `month_end` 는 `ticker`=코드 · `label`=이름인데 나머지 둘은 **`ticker` 에 이름**이
        들어 있고 코드가 없었다. 미국 ETF 는 둘이 같아(`QQQ`) 드러나지 않았고,
        국내에서만 `"ticker": "KODEX 200"` 으로 새어 나왔다.

        Given: 세 매매법의 데이터셋 목록
        When: 각 데이터셋의 필드를 봤을 때
        Then: `ticker` 와 `label` 이 둘 다 있고 서로 다른 것을 담는다
        """
        # Given
        groups = {
            "역방향": REVERSE_DATASETS,
            "옵션 만기일": EXPIRY_DATASETS,
            "월말": MONTH_END_DATASETS,
        }

        # When / Then
        for name, datasets in groups.items():
            for dataset in datasets:
                assert dataset.ticker, f"{name} 의 데이터셋에 종목코드가 없습니다"
                assert dataset.label, f"{name} 의 데이터셋에 표시 이름이 없습니다"

    def test_국내_종목은_코드와_이름이_다르다(self) -> None:
        """
        목적: 「코드가 이름 자리에 들어 있다」가 다시 생기면 잡는다

        미국 ETF 는 코드와 이름이 같아 이 계약을 검사하지 못한다. **국내 종목이 그 자리다.**

        Given: 역방향과 옵션 만기일의 국내 데이터셋
        When: 코드와 이름을 봤을 때
        Then: 코드는 숫자이고 이름은 숫자가 아니다
        """
        # Given
        domestic = [dataset for dataset in (*REVERSE_DATASETS, *EXPIRY_DATASETS) if dataset.ticker.isdigit()]
        assert domestic, "국내 데이터셋을 찾지 못했습니다"

        # When / Then
        for dataset in domestic:
            assert not dataset.label.isdigit(), f"{dataset.ticker} 의 표시 이름이 코드입니다"
