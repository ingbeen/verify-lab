"""하락_단계_매수 — 단계 규칙 · 보유 기간 · 대상 · 컬럼 토큰

**신호는 「한 구간 안에서 단계마다 처음 닿은 날 한 번」이다** — 구간은 지표가 회복해 다시 켜는 수준에 닿을 때 끝난다
(낙폭은 새 고점, VIX 는 20 미만, 공포탐욕지수는 50 이상). 판정은 `tiers.py` 가 하고 규칙 값은 여기가 갖는다.

**격자를 고르지 않는다** — 세 지표 × 단계 × 보유 기간을 전부 낸다 (루트 `CLAUDE.md` 측정의 원칙 1).
값의 출처와 탈락안은 `docs/검증/하락_단계_매수/설계.md` 「확정된 설계 결정」이다.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from verify_lab.common_constants import (
    ADJUSTED_FILE_TEMPLATE,
    COL_CLOSE,
    COL_DATE,
    COL_VALUE,
    MARKET_DIR,
    MARKET_FILE_TEMPLATE,
    PRICE_DECIMALS,
    RATE_TO_PERCENT,
)
from verify_lab.execution.constants import (
    DISPLAY_ENTRY_DATE,
    DISPLAY_EVENT_COUNT,
    DISPLAY_EXIT_DATE,
    DISPLAY_RETURN,
    DISPLAY_TICKER,
)
from verify_lab.measure.constants import (
    COL_ENTRY_CLOSE,
    COL_EXCLUDED_REASON,
    COL_EXIT_CLOSE,
    COL_EXIT_DATE,
    COL_FORWARD_RETURN,
    COL_HORIZON,
    COL_TICKER,
)
from verify_lab.measure.screening import COL_DIRECTION
from verify_lab.report.constants import (
    DISPLAY_DIRECTION,
    DISPLAY_ENTRY_CLOSE,
    DISPLAY_EXCLUDED_REASON,
    DISPLAY_EXIT_CLOSE,
    EXCESS_FILENAME,
    MEASURE_COLUMN_LABELS,
    MEASURE_PERCENT_COLUMNS,
    STATISTICS_FILENAME,
    TEST_FILENAME,
)

TRACK_NAME: Final = "drawdown_tiers"


# ============================================================
# 단계 규칙
# ============================================================


@dataclass(frozen=True)
class TierRule:
    """지표 하나의 단계 규칙

    Attributes:
        indicator: 지표 이름. 산출물의 지표 칸이 쓰는 값이다
        levels: 단계 — **얕은 것부터 깊은 순**. 신호 표의 같은 날 행과 산출물의 단계가 이 순서를 따른다
        fires_below: 참이면 값이 단계 «이하»에서 닿고 다시 켜는 수준 «이상»에서 켠다(낙폭 · 공포탐욕지수).
            거짓이면 단계 «이상»에서 닿고 다시 켜는 수준 «미만»에서 켠다(VIX)
        rearm_level: 다시 켜는 수준
        percent: 단계 값이 비율(0 ~ 1)이면 참 — 표에는 백분율로 싣는다
    """

    indicator: str
    levels: tuple[float, ...]
    fires_below: bool
    rearm_level: float
    percent: bool = False

    def __post_init__(self) -> None:
        """규칙이 스스로 모순되면 만들 때 멈춘다.

        Raises:
            ValueError: 단계가 없거나, 얕은 것부터 깊은 순이 아니거나, 단계가 다시 켜는 구역에 걸친 경우 —
                닿는 날과 켜는 날이 겹치면 같은 날의 처리 순서가 결과를 만든다
        """
        if not self.levels:
            raise ValueError(f"단계가 하나도 없습니다: {self.indicator}")

        pairs = zip(self.levels, self.levels[1:], strict=False)
        ordered = all((deep < shallow) if self.fires_below else (deep > shallow) for shallow, deep in pairs)
        if not ordered:
            raise ValueError(f"단계는 얕은 것부터 깊은 순이어야 합니다: {self.indicator} {self.levels}")

        crossing = [
            level
            for level in self.levels
            if (level >= self.rearm_level if self.fires_below else level < self.rearm_level)
        ]
        if crossing:
            raise ValueError(
                f"단계 {crossing} 가 다시 켜는 수준 {self.rearm_level} 쪽에 있습니다: {self.indicator} — "
                "닿는 구역과 다시 켜는 구역이 겹치지 않게 고치세요"
            )

    def label(self, level: float) -> str:
        """단계 하나의 표시 이름 — 값 · 단위 · 닿는 쪽을 함께 적는다 (`-10% 이하` · `25 이상`).

        Args:
            level: 이 규칙의 단계 값

        Returns:
            표시 이름

        Raises:
            ValueError: 이 규칙의 단계가 아닌 값인 경우
        """
        if level not in self.levels:
            raise ValueError(f"{self.indicator} 의 단계가 아닙니다: {level}")

        value = level * RATE_TO_PERCENT if self.percent else level
        unit = "%" if self.percent else ""
        side = "이하" if self.fires_below else "이상"

        return f"{value:g}{unit} {side}"

    def rearm_label(self) -> str:
        """다시 켜는 수준의 표시 이름 (`0% 이상` · `20 미만`).

        Returns:
            표시 이름
        """
        value = self.rearm_level * RATE_TO_PERCENT if self.percent else self.rearm_level
        unit = "%" if self.percent else ""
        side = "이상" if self.fires_below else "미만"

        return f"{value:g}{unit} {side}"


INDICATOR_DRAWDOWN: Final = "낙폭"
INDICATOR_VIX: Final = "VIX"
INDICATOR_FEAR_GREED: Final = "공포탐욕지수"

# 역대 최고 종가 대비 낙폭 (비율, -0.05 = -5%). 고점과 같은 종가도 회복으로 봄 (설계 결정 D9)
DRAWDOWN_RULE: Final = TierRule(
    indicator=INDICATOR_DRAWDOWN,
    levels=(-0.05, -0.10, -0.15, -0.20, -0.25, -0.30, -0.40, -0.50),
    fires_below=True,
    rearm_level=0.0,
    percent=True,
)

# VIX 종가 (지수 포인트)
VIX_RULE: Final = TierRule(
    indicator=INDICATOR_VIX,
    levels=(25.0, 30.0, 35.0, 40.0, 50.0, 60.0),
    fires_below=False,
    rearm_level=20.0,
)

# 공포탐욕지수 (0 ~ 100)
FEAR_GREED_RULE: Final = TierRule(
    indicator=INDICATOR_FEAR_GREED,
    levels=(25.0, 20.0, 15.0, 10.0, 5.0),
    fires_below=True,
    rearm_level=50.0,
)

# 산출물의 지표 순서
RULES: Final = (DRAWDOWN_RULE, VIX_RULE, FEAR_GREED_RULE)

# 보유 기간 (거래일, 대략 1 · 3 · 6 · 12 · 24 · 36개월) — 달력일로 세면 휴장 구간에서 길이가 갈림
HORIZONS: Final = (21, 63, 126, 252, 504, 756)

# 낙폭을 끊는 소수 자리 — 90/100−1 = −0.09999999999999998 이라 정확히 −10% 가 −10% 단계에 안 듦.
# 사본 가격이 소수 6자리라 실제로 다른 두 낙폭은 이 자리보다 크게 벌어짐
DRAWDOWN_DECIMALS: Final = 12

# VIX 의 데이터 오류 판정 일간 변동 (비율, 2.00 = 200%) — 공용 ±50% 로는 정상 급등(2018-02-05 +115.60%)이 막힘
# (설계 결정 D3)
VIX_MAX_DAILY_CHANGE_RATE: Final = 2.00


# ============================================================
# 대상과 지표 파일
# ============================================================


@dataclass(frozen=True)
class Dataset:
    """검증 대상 하나

    **낙폭 신호와 판정일 달력은 `signal_symbol` 의 시세에서 나온다** — ETF 셋은 SPY 공통(설계 결정 Q8),
    지수는 자기 자신이다(D2). 신호 대상은 대상과 같은 폴더 · 같은 파일 형식이다.

    Attributes:
        ticker: 종목코드. **산출물의 데이터셋 구분자는 `label` 이고 이 값은 요약이 갖는다**
        label: 표시 이름. 산출물의 종목 칸이 쓰는 값이다
        symbol: 파일 이름에 쓰는 심볼. 지수는 `^GSPC` 처럼 접두가 붙어 `ticker` 와 다르다
        signal_symbol: 낙폭 신호와 판정일 달력을 내는 대상의 심볼
        directory: 파일이 있는 폴더
        file_template: 파일명 템플릿
        price_column: 가격 컬럼 이름. ETF 는 `Close`, 지수는 종가 계열의 `Value`
        price_decimals: 가격 출력 자릿수
        is_index: 지수면 참. 살 수 없어 1차 판정을 하지 않는다 (측정의 원칙 9)
    """

    ticker: str
    label: str
    symbol: str
    signal_symbol: str
    directory: Path
    file_template: str
    price_column: str
    price_decimals: int
    is_index: bool

    @property
    def path(self) -> Path:
        """대상 시세 파일 경로.

        Returns:
            읽을 파일의 전체 경로
        """
        return self.directory / self.file_template.format(ticker=self.symbol)

    @property
    def signal_path(self) -> Path:
        """낙폭 신호와 판정일 달력을 내는 시세 파일 경로.

        Returns:
            읽을 파일의 전체 경로
        """
        return self.directory / self.file_template.format(ticker=self.signal_symbol)

    @property
    def is_judged(self) -> bool:
        """이 대상으로 1차 판정을 하는가 — 살 수 있는 것에만 건다 (측정의 원칙 9).

        Returns:
            판정 대상이면 참
        """
        return not self.is_index


# ETF 는 수정주가 (측정의 원칙 14). 지수는 판정하지 않고 1928 년부터의 긴 축으로만 냄 (설계 결정 D2)
DATASETS: Final = (
    Dataset(
        ticker="SPY",
        label="SPY",
        symbol="SPY",
        signal_symbol="SPY",
        directory=MARKET_DIR,
        file_template=ADJUSTED_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS,
        is_index=False,
    ),
    Dataset(
        ticker="DIA",
        label="DIA",
        symbol="DIA",
        signal_symbol="SPY",
        directory=MARKET_DIR,
        file_template=ADJUSTED_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS,
        is_index=False,
    ),
    Dataset(
        ticker="QQQ",
        label="QQQ",
        symbol="QQQ",
        signal_symbol="SPY",
        directory=MARKET_DIR,
        file_template=ADJUSTED_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS,
        is_index=False,
    ),
    Dataset(
        ticker="GSPC",
        label="S&P 500 지수",
        symbol="^GSPC",
        signal_symbol="^GSPC",
        directory=MARKET_DIR,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_VALUE,
        price_decimals=PRICE_DECIMALS,
        is_index=True,
    ),
)


@dataclass(frozen=True)
class IndicatorFiles:
    """외부 지표 파일 둘 — 대상과 무관하게 하나씩이다

    Attributes:
        vix: 야후 `^VIX` 시세 사본 (OHLCV — 종가 계열로 읽는다)
        fear_greed: 공포탐욕지수 (`Date`, `Value`)
    """

    vix: Path
    fear_greed: Path


INDICATOR_FILES: Final = IndicatorFiles(
    vix=MARKET_DIR / MARKET_FILE_TEMPLATE.format(ticker="^VIX"),
    fear_greed=MARKET_DIR / "fear_greed_daily.csv",
)


# ============================================================
# 컬럼 토큰 (내부 계산용)
# ============================================================

COL_TIER: Final = "tier"
COL_INDICATOR_VALUE: Final = "indicator_value"

# 진입일 — 판정일(`COL_DATE`) 다음 거래일이라 이름을 가름 (설계 결정 D1)
COL_ENTRY_DATE: Final = "entry_date"

# 판정일에 대상이 없으면 진입 규칙이 정의되지 않음 (설계 결정 D11)
REASON_BEFORE_LISTING: Final = "판정일에 대상이 상장 전"

COL_INDICATOR: Final = "indicator"

# 판정일이 속한 하락장의 시작일 — 같은 하락장의 신호를 한 사건으로 묶음 (설계 결정 D6 · 측정의 원칙 5)
COL_EVENT_START: Final = "event_start"

# 유효 표본이 든 하락장의 수
COL_EVENT_COUNT: Final = "event_count"

# 판정일의 세 지표 값 (설계 결정 Q11). 낙폭은 신호 대상(ETF 는 SPY · 지수는 자기)의 것
COL_DRAWDOWN: Final = "drawdown"
COL_VIX: Final = "vix"
COL_FEAR_GREED: Final = "fear_greed"

# 판정일의 달력 축 분해 (측정의 원칙 12 · 설계 결정 D7) — `통계.csv` 에만 실림
COL_CALENDAR_AXIS: Final = "calendar_axis"
COL_CALENDAR_VALUE: Final = "calendar_value"

CALENDAR_ALL: Final = "전체"
CALENDAR_MONTH: Final = "월"
CALENDAR_WEEKDAY: Final = "요일"

# 달력 값의 이름 — 표본이 0건인 달 · 요일도 행을 남기려고 목록으로 둠 (측정의 원칙 17)
MONTH_NAMES: Final = tuple(f"{month}월" for month in range(1, 13))
WEEKDAY_NAMES: Final = ("월요일", "화요일", "수요일", "목요일", "금요일")

# 출력 자릿수 — VIX 는 시세처럼 가격 자릿수, 공포탐욕지수는 0 ~ 100 지수라 백분율처럼 2자리
FEAR_GREED_DECIMALS: Final = 2


# ============================================================
# 표시용 한글 레이블
# ============================================================

DISPLAY_INDICATOR: Final = "지표"
DISPLAY_TIER: Final = "단계"
DISPLAY_HORIZON: Final = "보유(거래일)"
DISPLAY_JUDGMENT_DATE: Final = "판정일"
DISPLAY_EVENT_START: Final = "하락장 시작일"
DISPLAY_DRAWDOWN: Final = "낙폭(%)"
DISPLAY_VIX: Final = "VIX"
DISPLAY_FEAR_GREED: Final = "공포탐욕지수"
DISPLAY_CALENDAR_AXIS: Final = "달력 축"
DISPLAY_CALENDAR_VALUE: Final = "달력 값"

COLUMN_LABELS: Final = {
    # 식별
    COL_TICKER: DISPLAY_TICKER,
    COL_INDICATOR: DISPLAY_INDICATOR,
    COL_TIER: DISPLAY_TIER,
    COL_CALENDAR_AXIS: DISPLAY_CALENDAR_AXIS,
    COL_CALENDAR_VALUE: DISPLAY_CALENDAR_VALUE,
    COL_HORIZON: DISPLAY_HORIZON,
    COL_DIRECTION: DISPLAY_DIRECTION,
    # 신호내역
    COL_DATE: DISPLAY_JUDGMENT_DATE,
    COL_DRAWDOWN: DISPLAY_DRAWDOWN,
    COL_VIX: DISPLAY_VIX,
    COL_FEAR_GREED: DISPLAY_FEAR_GREED,
    COL_EVENT_START: DISPLAY_EVENT_START,
    COL_ENTRY_DATE: DISPLAY_ENTRY_DATE,
    COL_ENTRY_CLOSE: DISPLAY_ENTRY_CLOSE,
    COL_EXIT_DATE: DISPLAY_EXIT_DATE,
    COL_EXIT_CLOSE: DISPLAY_EXIT_CLOSE,
    COL_FORWARD_RETURN: DISPLAY_RETURN,
    COL_EXCLUDED_REASON: DISPLAY_EXCLUDED_REASON,
    # 통계 — 사건 수. 집계 · 기준선 · 차이 · 우연확률은 공통 이름표
    COL_EVENT_COUNT: DISPLAY_EVENT_COUNT,
    **MEASURE_COLUMN_LABELS,
}

# 비율(0 ~ 1)로 들어와 백분율로 내보낼 칸 — 측정 칸 공통 목록 위에 낙폭
PERCENT_COLUMNS: Final = (*MEASURE_PERCENT_COLUMNS, COL_DRAWDOWN)


# ============================================================
# 산출물 파일
# ============================================================

# 판정일 × 단계 × 보유 기간의 원자료 — 제외 행도 사유와 함께 남음 (측정의 원칙 8)
SIGNALS_FILENAME: Final = "신호내역.csv"

# 키는 문자열 리터럴 — 계약 검사가 이 사전을 AST 로 읽음
OUTPUT_FILES: Final[dict[str, str]] = {
    "statistics": STATISTICS_FILENAME,
    "excess": EXCESS_FILENAME,
    "test": TEST_FILENAME,
    "signals": SIGNALS_FILENAME,
}

FIELD_STATISTICS, FIELD_EXCESS, FIELD_TEST, FIELD_SIGNALS = OUTPUT_FILES


# ============================================================
# 실행 요약 키 — 측정 · 체결이 함께 씀
# ============================================================

KEY_INDICATOR: Final = "indicator"
KEY_SIGNAL_COUNT: Final = "signal_count"
KEY_EXCLUDED_BY_REASON: Final = "excluded_by_reason"
