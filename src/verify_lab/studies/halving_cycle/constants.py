"""반감기_사이클 — 파라미터와 레이블

**1단계 측정 격자는 결과를 보기 전에 정한 값이다** — 진입 = 반감기 뒤 0 ~ 45개월을 3개월 간격(16칸), 보유 = 3 · 6 · 12개월,
합 48칸이다(`docs/검증/반감기_사이클/설계.md` 결정 ⑥). 긴 보유와 고점·바닥 축은 그 결정의 탈락안이고, 긴 보유는 3단계 체결
격자(진입 시점 × 청산 시점)가 다룬다.

**체결(3단계)은 진입 시점 × 청산 시점 격자 × 손절선 격자 전부 · 「위」 한 방향이다** (결정 ㉞ · ㉟ · ⑰).
진입과 청산 모두 「가장 최근 반감기 뒤 몇 개월」이고 값은 1단계 진입 축과 같다. **칸을 고르지 않는다** — 고르는 것은
사용자가 `규칙.md` 에서 한다. 아래로 거는 칸의 크기와 빈도는 측정 표의 내린 비율이 준다.

**달력을 공통 계층에 올리지 않는다.** 진입이 「반감기일 + 개월」이라 중간선거_사이클의 「그 달 마지막
거래일」과 모양이 다르다 — 원칙에 없는 달력은 같은 모양이 세 번째로 올 때 정한다
(`src/verify_lab/CLAUDE.md` 「어디까지가 공통이고 어디부터 그 검증의 것인가」).

**2단계(보조지표 · 온체인)의 창 · 문턱 · 신호 목록도 결과를 보기 전에 정한 값이다** — 책이 적은 값 그대로이고
지표마다 정의가 하나다(결정 ㉒ · ㉓ · ㉕ · ㉖).
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pandas as pd

from verify_lab.common_constants import COL_DATE, MARKET_DIR, MARKET_FILE_TEMPLATE, PRICE_DECIMALS, SERIES_DIR
from verify_lab.data.bitstamp_collector import BITSTAMP_TICKER
from verify_lab.data.coinmetrics_collector import BTC_PRICE_SERIES, MARKET_CAP_SERIES, MVRV_SERIES
from verify_lab.data.crosscheck import COL_DIFF_RATE, COL_PRIMARY, COL_SECONDARY
from verify_lab.execution.constants import DISPLAY_ENTRY_DATE, DISPLAY_EXIT_DATE, DISPLAY_RETURN, DISPLAY_TICKER
from verify_lab.measure.constants import (
    COL_ENTRY_CLOSE,
    COL_EXCLUDED_COUNT,
    COL_EXCLUDED_REASON,
    COL_EXIT_CLOSE,
    COL_EXIT_DATE,
    COL_FORWARD_RETURN,
    COL_HOLD_DAYS,
    COL_JUDGEABLE,
    COL_MEAN_RATE_CONFLICT,
    COL_SIGNAL_COUNT,
)
from verify_lab.measure.screening import COL_DIRECTION
from verify_lab.measure.statistics import (
    COL_DOWN_RATE_P_VALUE,
    COL_LOSS_RATE,
    COL_LOSS_RATE_EXCESS,
    COL_MAX,
    COL_MEAN,
    COL_MEAN_EXCESS,
    COL_MEAN_P_VALUE,
    COL_MEDIAN,
    COL_MEDIAN_EXCESS,
    COL_MEDIAN_P_VALUE,
    COL_MIN,
    COL_NEGATIVE_COUNT,
    COL_NEGATIVE_MEAN,
    COL_POSITIVE_COUNT,
    COL_POSITIVE_MEAN,
    COL_SAMPLE_COUNT,
    COL_SIGNAL_SAMPLE_COUNT,
    COL_STD,
    COL_TEST_NOTE,
    COL_UP_RATE_P_VALUE,
    COL_WIN_RATE,
    COL_WIN_RATE_EXCESS,
)
from verify_lab.report.constants import (
    DATE_FORMAT,
    DISPLAY_DATE,
    DISPLAY_DIRECTION,
    DISPLAY_DOWN_RATE,
    DISPLAY_DOWN_RATE_DIFF,
    DISPLAY_DOWN_RATE_P_VALUE,
    DISPLAY_ENTRY_CLOSE,
    DISPLAY_EXCLUDED,
    DISPLAY_EXCLUDED_REASON,
    DISPLAY_EXIT_CLOSE,
    DISPLAY_HOLD_DAYS_EXACT,
    DISPLAY_JUDGEABLE,
    DISPLAY_MAX,
    DISPLAY_MEAN,
    DISPLAY_MEAN_DIFF,
    DISPLAY_MEAN_P_VALUE,
    DISPLAY_MEAN_RATE_CONFLICT,
    DISPLAY_MEDIAN,
    DISPLAY_MEDIAN_DIFF,
    DISPLAY_MEDIAN_P_VALUE,
    DISPLAY_MIN,
    DISPLAY_NEGATIVE_COUNT,
    DISPLAY_NEGATIVE_MEAN,
    DISPLAY_NON_OVERLAPPING,
    DISPLAY_POSITIVE_COUNT,
    DISPLAY_POSITIVE_MEAN,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_SIGNAL_SAMPLE,
    DISPLAY_STD,
    DISPLAY_TEST_NOTE,
    DISPLAY_UP_RATE,
    DISPLAY_UP_RATE_DIFF,
    DISPLAY_UP_RATE_P_VALUE,
    EXCESS_FILENAME,
    STATISTICS_FILENAME,
    TEST_FILENAME,
)

# 이 매매법의 이름(slug). 규약은 `src/verify_lab/CLAUDE.md` 「매매법 이름 계약」이 SoT다
TRACK_NAME: Final = "halving_cycle"


# ============================================================
# 반감기
# ============================================================


@dataclass(frozen=True)
class Halving:
    """반감기 하나

    Attributes:
        height: 반감기 블록 높이
        block_time: 그 블록 헤더의 시각. **시간대가 있어야 한다** — 날짜를 UTC 로 자르기 때문이다
    """

    height: int
    block_time: datetime

    def __post_init__(self) -> None:
        """시각에 시간대가 있는지 검사한다.

        Raises:
            ValueError: 시간대가 없는 시각인 경우. 실행 PC 의 시간대로 읽히면 날짜가 하루 갈릴 수 있다
        """
        if self.block_time.tzinfo is None:
            raise ValueError(f"반감기 블록 시각에 시간대가 없습니다: {self.block_time}")

    @property
    def day(self) -> pd.Timestamp:
        """반감기 날짜 — 블록 헤더 시각의 **UTC** 날짜(자정).

        Returns:
            시간대 없는 자정 Timestamp. 시세의 날짜와 같은 모양이다
        """
        return pd.Timestamp(self.block_time.astimezone(UTC).date())

    @property
    def label(self) -> str:
        """산출물에 싣는 반감기 표지.

        Returns:
            `YYYY-MM-DD`
        """
        return self.day.strftime(DATE_FORMAT)


# **블록 헤더 시각의 UTC 날짜를 쓴다** (2026-09-29 사용자 결정). mempool.space API 로 직접 조회한 값이다.
#
# [중요] **데이터에서 유도하지 않는다.** 840,000 블록의 median time past 는 2024-04-19 23:43:28 UTC 이고
# Coin Metrics 블록 수 누적도 04-19 를 낸다 — 그 날짜의 Bitstamp 종가(04-20 00:00 UTC)는 반감기 블록보다
# **9분 앞선 가격**이라 0개월 진입이 반감기 «전» 매수가 된다. 넷 모두 블록이 그날 종가보다 먼저 나왔다.
#
# **다음 반감기(2028 추정)는 넣지 않는다** — 블록 시각이 없는 값을 넣으면 추정이 측정의 입력이 된다.
# 그 해가 오면 실제 블록 시각으로 한 줄을 더한다
HALVINGS: Final = (
    Halving(height=210_000, block_time=datetime(2012, 11, 28, 15, 24, 38, tzinfo=UTC)),
    Halving(height=420_000, block_time=datetime(2016, 7, 9, 16, 46, 13, tzinfo=UTC)),
    Halving(height=630_000, block_time=datetime(2020, 5, 11, 19, 23, 43, tzinfo=UTC)),
    Halving(height=840_000, block_time=datetime(2024, 4, 20, 0, 9, 27, tzinfo=UTC)),
)


# ============================================================
# 하드포크 — BTC 를 들고 있으면 나눠 받은 코인 (결정 ㊲)
# ============================================================


@dataclass(frozen=True)
class HardFork:
    """BTC 를 들고 있으면 1:1 로 나눠 받은 코인 하나

    **원본가에는 이 몫이 없다** — 배당락처럼 체결 수익률에 더하지 않고 따로 잰다(측정의 원칙 14).

    Attributes:
        name: 코인 이름. 산출물 설명과 요약에 싣는다
        height: 스냅샷 블록 높이 — 이 블록까지 BTC 를 든 주소가 받았다
        block_time: 그 블록 헤더의 시각. **시간대가 있어야 한다** — 날짜를 UTC 로 자르기 때문이다
        price_day: 포크 코인의 첫 시세일 (Coin Metrics `PriceUSD`)
        coin_price: 그날 포크 코인 가격 (USD)
        btc_price: 그날 BTC 가격 (USD · 같은 소스). **Bitstamp 가 아니라 같은 소스를 쓴다** — 비율의 두 값이
            다른 소스면 두 소스의 괴리가 비율에 섞인다
    """

    name: str
    height: int
    block_time: datetime
    price_day: pd.Timestamp
    coin_price: float
    btc_price: float

    def __post_init__(self) -> None:
        """값을 검사한다.

        Raises:
            ValueError: 시각에 시간대가 없거나, 가격이 양수가 아니거나, 첫 시세일이 포크일 앞인 경우
        """
        if self.block_time.tzinfo is None:
            raise ValueError(f"하드포크 블록 시각에 시간대가 없습니다: {self.name} {self.block_time}")
        if self.coin_price <= 0 or self.btc_price <= 0:
            raise ValueError(f"하드포크 가격은 양수여야 합니다: {self.name} {self.coin_price} · {self.btc_price}")
        if self.price_day < self.day:
            raise ValueError(f"첫 시세일이 포크일 앞입니다: {self.name} {self.price_day.date()} < {self.day.date()}")

    @property
    def day(self) -> pd.Timestamp:
        """포크일 — 스냅샷 블록 헤더 시각의 **UTC** 날짜(자정).

        Returns:
            시간대 없는 자정 Timestamp. 시세의 날짜와 같은 모양이다
        """
        return pd.Timestamp(self.block_time.astimezone(UTC).date())

    @property
    def ratio(self) -> float:
        """BTC 하나당 받은 코인의 가치를 BTC 로 잰 비율 (0.12 = 12%).

        Returns:
            첫 시세일의 포크 코인 가격 ÷ 같은 날 BTC 가격
        """
        return self.coin_price / self.btc_price


# **스냅샷 블록은 두 체인이 공유하는 마지막 블록이다.** 시각은 mempool.space API 로 BTC 체인의 그 높이를 조회한 값이다
# (2026-09-30). BCH 는 두 체인의 블록 해시가 478,558 까지 같고 478,559 부터 갈린다(BTC 는 mempool.space ·
# BCH 는 Blockchair 로 대조). BTG 는 491,407 에서 갈렸고 그 앞 블록까지의 잔고를 나눴다(Ledger · KuCoin · OKX 공지).
#
# **가격은 Coin Metrics `PriceUSD` 를 조회한 값이다** (2026-09-30 · 가격 자릿수 규칙대로 4자리). BTG 는 포크 다음날부터
# 값이 있다. BSV(2018-11-15)는 BCH 에서 갈라져 **BTC 만 드는 체결은 받지 않는다** — 넣지 않는다.
# 포크 가치를 데이터에서 다시 받지 않는 것은 반감기 블록 시각과 같은 이유다 — 과거의 사건이라 값이 바뀌지 않는다
HARD_FORKS: Final = (
    HardFork(
        name="BCH",
        height=478_558,
        block_time=datetime(2017, 8, 1, 13, 16, 14, tzinfo=UTC),
        price_day=pd.Timestamp("2017-08-01"),
        coin_price=328.3279,
        btc_price=2727.3892,
    ),
    HardFork(
        name="BTG",
        height=491_406,
        block_time=datetime(2017, 10, 24, 1, 17, 35, tzinfo=UTC),
        price_day=pd.Timestamp("2017-10-25"),
        coin_price=152.1593,
        btc_price=5736.0178,
    ),
)


# ============================================================
# 격자 — 결과를 보기 전에 정한 값 (결정 ⑥)
# ============================================================

# 반감기 뒤 진입 개월 — 0 ~ 45개월, 3개월 간격.
#
# [주의] **다음 반감기 앞이라는 보장이 없다.** 첫 반감기 간격이 약 43.4개월이라 2012 사이클의 45개월 진입
# (2016-08-28)은 다음 반감기(2016-07-09) «뒤»다. 그래도 격자를 고치지 않는다 — 결과를 본 뒤 칸의 정의를
# 바꾸면 사후 선택과 구별되지 않는다(`docs/검증/반감기_사이클/설계.md` 결정 ㉑). 3단계 체결 격자는 같은 값을
# 쓰되 **그 사이클 안의 진입만** 둔다(`halving_calendar.position_schedule` · 결정 ㊴)
ENTRY_MONTHS: Final = tuple(range(0, 46, 3))

# 보유 개월. 청산일 = 진입일 + 보유 개월(달력월)이다 — 1단계 측정 격자의 축이다
HOLD_MONTHS: Final = (3, 6, 12)

# 3단계 체결 격자의 청산 시점 — 가장 최근 반감기 뒤 개월. **진입 축과 같은 범위 · 간격이다** (결정 ㉞).
# 청산 시점이 진입 시점보다 크면 같은 반감기 뒤, 같거나 작으면 **다음 반감기 뒤** 그 시점이다 — 보유는 최대 한 사이클
EXIT_MONTHS: Final = ENTRY_MONTHS

# 거는 방향. **「위」 하나다** — 측정과 체결이 같은 값을 봐야 두 표의 `방향` 이 같은 말을 한다
BET_DOWN: Final = False

# 손절선 — 무손절과 진입가 대비 5%p 간격 격자 **전부**다 (결정 ㉟ · 2026-09-30 사용자 결정). 검증 등급이라 좁히지
# 않는다(`.claude/rules/trading.md` 「검증 등급의 기본도 「좁히지 않음」」). **값을 골라 넣는 인자를 두지 않는다** —
# 손절선을 고르는 것은 `규칙.md` 에서 평평한 구간과 최악 통제로 한다
STOP_LEVELS: Final[tuple[float | None, ...]] = (None, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50)


# ============================================================
# 2단계 — 지표의 창 (결정 ㉒ · ㉓ · ㉕)
# ============================================================

# Pi Cycle — 111일 SMA 가 350일 SMA 의 2배를 상향 돌파 (책 A 232 ~ 233쪽). 창은 지표의 정의 그대로다
PI_CYCLE_SHORT_WINDOW: Final = 111
PI_CYCLE_LONG_WINDOW: Final = 350
PI_CYCLE_LONG_MULTIPLIER: Final = 2.0

# 100일 이격도 — 신호로 재지 않고 1단계 진입일의 값으로만 낸다 (결정 ㉖ 탈락안 ②)
DISPARITY_WINDOW: Final = 100

# 월간 RSI — Wilder 평활 (책 B 차트 「RSI 14 close」)
RSI_WINDOW: Final = 14

# 월간 MACD — 로그 종가의 EMA 5 · 15, 시그널 EMA 9 (책 B 차트 「LMACD 5 15 close 9」 · 결정 ㉕)
MACD_FAST_SPAN: Final = 5
MACD_SLOW_SPAN: Final = 15
MACD_SIGNAL_SPAN: Final = 9

# MVRV-Z 표준편차의 최소 기간(일). **첫 값의 날짜만 정하고 그 뒤의 값을 바꾸지 않는다** — 표준편차가
# 그날까지의 시가총액 전부로 나오기 때문이다(결정 ㉓). 365일은 사전조사 §6.2 가 쓴 값이다
MVRV_Z_MIN_DAYS: Final = 365


# ============================================================
# 2단계 — 책 신호 (결정 ㉖ 첫 표)
# ============================================================


@dataclass(frozen=True)
class IndicatorSignal:
    """책이 문턱을 적은 신호 하나 — 그 지표가 문턱을 돌파한 날

    **돌파는 상태 `값 ≥ 문턱` 이 바뀐 날이다** (`indicator_signals.crossing_days`). 문턱과 같은 값은
    문턱 이상으로 센다.

    Attributes:
        name: 산출물에 싣는 신호 이름. **신호의 구분자이므로 겹치면 안 된다**
        indicator: 지표 컬럼 토큰. 일간 지표면 판정일이 날마다, 월간 지표면 달의 마지막 날이다
        threshold: 문턱
        upward: 상향 돌파인가. 거짓이면 하향 돌파다
        meaning: 책이 그 신호에 붙인 뜻 — 판정이 아니라 **책의 주장**이다
    """

    name: str
    indicator: str
    threshold: float
    upward: bool
    meaning: str


# ============================================================
# 검증 대상
# ============================================================


@dataclass(frozen=True)
class Dataset:
    """검증 대상 하나 — 시세 · 거래량 0 인 날을 채울 대조 계열 · 온체인 두 계열

    Attributes:
        ticker: 파일명에 쓰는 코드. **산출물의 데이터셋 구분자이므로 겹치면 안 된다**
        label: 표시 이름. **산출물의 종목 컬럼이 쓰는 값**이다
        directory: 시세 파일이 있는 폴더
        file_template: 시세 파일명 템플릿
        reference_path: 대조 계열(일별 단일 값) 파일. 거래량 0 인 날의 종가를 이 값으로 바꾼다(결정 ④)
        mvrv_path: MVRV 계열 파일. 2단계 측정만 읽는다(결정 ⑧)
        market_cap_path: 시가총액 계열 파일. 2단계 측정만 읽는다 — 실현 시가총액은 `시가총액 ÷ MVRV` 다
        price_decimals: 가격 출력 자릿수. 원시 데이터를 저장한 값과 같아야 한다
        is_judged: 1차 판정을 거는가 — **살 수 있는 대상에만 건다** (측정의 원칙 9 · 결정 ⑤)
    """

    ticker: str
    label: str
    directory: Path
    file_template: str
    reference_path: Path
    mvrv_path: Path
    market_cap_path: Path
    price_decimals: int
    is_judged: bool

    @property
    def path(self) -> Path:
        """시세 파일 경로.

        Returns:
            읽을 시세 파일의 전체 경로
        """
        return self.directory / self.file_template.format(ticker=self.ticker)


# **Bitstamp BTC/USD 하나다** — 거래소 한 곳의 실제 체결가이고 「살 수 있는 대상」으로 본다(결정 ① · ⑤).
# 업비트 원화는 대조용이라 여기 없다
DATASETS: Final = (
    Dataset(
        ticker=BITSTAMP_TICKER,
        label="Bitstamp BTC/USD",
        directory=MARKET_DIR,
        file_template=MARKET_FILE_TEMPLATE,
        reference_path=SERIES_DIR / BTC_PRICE_SERIES.file_name,
        mvrv_path=SERIES_DIR / MVRV_SERIES.file_name,
        market_cap_path=SERIES_DIR / MARKET_CAP_SERIES.file_name,
        price_decimals=PRICE_DECIMALS,
        is_judged=True,
    ),
)


# ============================================================
# DataFrame 컬럼 (내부 계산용 토큰)
# ============================================================

COL_TICKER: Final = "ticker"

# 어느 반감기 사이클의 진입인가 — 반감기 날짜 문자열이다
COL_HALVING: Final = "halving"

# 격자의 축 — 진입은 두 격자가 함께 쓰고, 보유는 1단계 측정 · 청산 시점은 3단계 체결의 것이다
COL_ENTRY_MONTHS: Final = "entry_months"
COL_HOLD_MONTHS: Final = "hold_months"
COL_EXIT_MONTHS: Final = "exit_months"

# 진입내역의 진입일. **시세의 날짜 컬럼과 이름을 가른다** — 한 이름표 사전에서 `Date` 는 크로스체크 표의
# 「날짜」를 가리키므로, 진입일을 같은 토큰으로 두면 거래내역의 「진입일」과 다른 헤더가 나간다
COL_ENTRY_DATE: Final = "entry_date"

# 달력 연도 표
COL_CALENDAR_YEAR: Final = "calendar_year"
COL_HALVING_POSITION: Final = "halving_position"
COL_PREVIOUS_CLOSE: Final = "previous_close"
COL_YEAR_END_CLOSE: Final = "year_end_close"

# 크로스체크 표 — 그날 Bitstamp 에 거래가 없었는가 (예/아니오)
COL_ZERO_VOLUME: Final = "zero_volume"

# 기준선 집계를 신호 집계와 나란히 놓을 때 붙이는 접미사
BASELINE_SUFFIX: Final = "_baseline"

# 겹치지 않게 고를 수 있는 체결의 최대 개수 (산식은 `measure.statistics.max_non_overlapping`).
# **기준선이 이 값을 반드시 필요로 한다** — 매일 진입해 몇 달을 드는 롤링이라 이웃이 거의 다 겹친다.
# 신호 쪽은 사이클마다 한 번이라 겹침이 없고, 두 값이 같다는 것이 「표본이 서로 독립인가」의 답이다
COL_NON_OVERLAPPING: Final = "NonOverlappingCount"
COL_BASELINE_NON_OVERLAPPING: Final = f"{COL_NON_OVERLAPPING}{BASELINE_SUFFIX}"

# 2단계 — 지표 값. 일간 다섯은 시세의 날짜 위에, 월간 둘은 끝난 달의 말일 위에 있다
COL_MVRV: Final = "mvrv"
COL_MARKET_CAP: Final = "market_cap"
COL_MVRV_Z: Final = "mvrv_z"
COL_NUPL: Final = "nupl"
COL_PI_CYCLE: Final = "pi_cycle_ratio"
COL_DISPARITY: Final = "disparity"
COL_MONTHLY_RSI: Final = "monthly_rsi"
COL_MACD_HISTOGRAM: Final = "macd_histogram"

# 2단계 — 신호일 목록과 집계
COL_INDICATOR_SIGNAL: Final = "indicator_signal"
COL_SIGNAL_MEANING: Final = "signal_meaning"
COL_JUDGMENT_DATE: Final = "judgment_date"
COL_PREVIOUS_VALUE: Final = "previous_value"
COL_INDICATOR_VALUE: Final = "indicator_value"
COL_MONTHS_SINCE_HALVING: Final = "months_since_halving"

# 유효 표본이 있는 반감기 사이클의 수. 표본과 함께 보면 한 사이클에 몰렸는지 보인다 (측정의 원칙 5)
COL_CYCLE_COUNT: Final = "cycle_count"

# 2단계 — 1단계 진입일에 붙이는 값의 기준 (결정 ㉗). 값 기준일은 진입 전날, 기준 달은 그날이나 그 전에 끝난 달이다
COL_VALUE_DAY: Final = "value_day"
COL_INDICATOR_MONTH: Final = "indicator_month"

# 진입지표 표의 보유별 수익률 — 진입내역의 같은 값을 한 행에 펼친다
COL_HOLD_RETURNS: Final = {months: f"return_{months}m" for months in HOLD_MONTHS}


# 책이 문턱을 적은 신호 전부 — **결정 ㉖ 첫 표의 순서 그대로다.** 책의 「마지막」 · 「바닥 뒤」 처럼 지나고 나서야
# 정해지는 조건은 빼고 돌파를 전부 잰다. 변형(다른 문턱 · 다른 창)을 더하지 않는다 — 고를 여지가 생긴다
INDICATOR_SIGNALS: Final = (
    IndicatorSignal("Pi Cycle 상향 돌파", COL_PI_CYCLE, 1.0, True, "고점"),
    IndicatorSignal("MVRV-Z 7 상향 돌파", COL_MVRV_Z, 7.0, True, "과대평가 (강도 3)"),
    IndicatorSignal("MVRV-Z 6 상향 돌파", COL_MVRV_Z, 6.0, True, "강도 2"),
    IndicatorSignal("MVRV-Z 0 하향 돌파", COL_MVRV_Z, 0.0, False, "재진입 준비"),
    IndicatorSignal("MVRV 1 하향 돌파", COL_MVRV, 1.0, False, "바닥 구간"),
    IndicatorSignal("MVRV 1 상향 돌파", COL_MVRV, 1.0, True, "새 사이클"),
    IndicatorSignal("MVRV 1.7 하향 돌파", COL_MVRV, 1.7, False, "적극 매수"),
    IndicatorSignal("MVRV 3 상향 돌파", COL_MVRV, 3.0, True, "매도 준비"),
    IndicatorSignal("MVRV 3.7 상향 돌파", COL_MVRV, 3.7, True, "매도 · 고점 구간"),
    IndicatorSignal("NUPL 0.75 상향 돌파", COL_NUPL, 0.75, True, "Euphoria — 고점 의심"),
    IndicatorSignal("월간 RSI 50 하향 이탈", COL_MONTHLY_RSI, 50.0, False, "사이클 전환점"),
    IndicatorSignal("월간 RSI 50 상향 돌파", COL_MONTHLY_RSI, 50.0, True, "새 사이클"),
    IndicatorSignal("월간 MACD 시그널 상향 돌파", COL_MACD_HISTOGRAM, 0.0, True, "매수 · 새 사이클"),
    IndicatorSignal("월간 MACD 시그널 하향 돌파", COL_MACD_HISTOGRAM, 0.0, False, "매도"),
)


# ============================================================
# 값 — 달력 연도의 위치와 제외 사유
# ============================================================

# 반감기 해로부터의 햇수. **4로 나눈 나머지가 아니라 반감기 목록에서 정한다** — 간격이 정확히 4년이라는
# 가정을 코드에 두지 않는다
POSITION_BEFORE_FIRST: Final = "첫 반감기 전"
POSITION_HALVING_YEAR: Final = "반감기해"
POSITION_AFTER_TEMPLATE: Final = "반감기 + {years}"

# **데이터가 해 중간에 시작하거나 끝나면 그해를 재지 않되 행은 남긴다** (측정의 원칙 17).
# 끝나지 않은 해의 「연초 대비」는 그해 수익률과 다른 양이라 값을 채우지 않는다
REASON_NO_PREVIOUS_YEAR_END: Final = "전년 말 종가가 데이터 앞"
REASON_YEAR_UNFINISHED: Final = "그해가 데이터 안에서 끝나지 않음"

# 2단계 신호의 제외 사유. **행을 남긴다** (결정 ㉘ ① · 표본 보존). 청산일이 데이터 뒤인 것은 1단계와 같은 사유다.
# 판정 구간은 1단계와 기준선처럼 첫 반감기부터다 — 그 앞의 신호는 기준선과 기간이 갈린다
REASON_BEFORE_FIRST_HALVING: Final = "첫 반감기 전 판정"
# 판정은 났는데 다음날이 데이터 뒤다. 1단계의 「아직 오지 않은 진입」(행 없음)과 달리 신호는 이미 있다
REASON_ENTRY_AFTER_DATA: Final = "진입일이 데이터 뒤"

# 3단계 체결 격자의 제외 사유 — 진입은 했는데 **청산 시점이 오기 전에 반감기가 한 번 더 왔다**(결정 ㊴).
# 사이클이 격자보다 짧아 그 시점이 그 사이클에 없는 것이라 청산일을 정할 수 없다
REASON_EXIT_AFTER_NEXT_HALVING: Final = "청산 시점 전에 다음 반감기"


# ============================================================
# 표시용 한글 레이블
# ============================================================

# **여기 없는 이름은 공통 계층에서 가져온다** — 같은 뜻에 이름이 두 벌이 되면 두 산출물의 헤더가 갈린다
DISPLAY_HALVING: Final = "반감기"
DISPLAY_ENTRY_MONTHS: Final = "반감기 뒤 진입(개월)"
DISPLAY_HOLD_MONTHS: Final = "보유(개월)"
# **같은 사이클인지 다음 사이클인지를 가르는 칸을 두지 않는다** — 진입 · 청산 두 값에서 완전히 유도된다 (결정 ㉞)
DISPLAY_EXIT_MONTHS: Final = "반감기 뒤 청산(개월)"
# 거래내역 끝 칸 — 원본가에 없는 몫이라 수익률에 더하지 않고 따로 싣는다 (결정 ㊲)
DISPLAY_FORK_SHARE: Final = "하드포크 몫(%p)"

# **「연도」를 쓰지 않는다** — 원달러_ETF_등가성이 그 이름을 이미 쓴다 (`tests/test_layer_contracts.py` 레이블 겹침 검사).
# 「사이클 위치」도 중간선거_사이클의 것이라 쓰지 않는다
DISPLAY_CALENDAR_YEAR: Final = "달력 연도"
DISPLAY_HALVING_POSITION: Final = "반감기 위치"
DISPLAY_PREVIOUS_CLOSE: Final = "전년 말 종가"
DISPLAY_YEAR_END_CLOSE: Final = "그해 말 종가"

# 두 소스의 대조. **어느 소스의 값인지를 이름에 박는다** — 대체일 표에서 측정이 쓴 값은 Coin Metrics 쪽이다
DISPLAY_PRIMARY_CLOSE: Final = "Bitstamp 종가"
DISPLAY_REFERENCE_CLOSE: Final = "Coin Metrics 종가"
DISPLAY_DIFF_RATE: Final = "차이율(%)"
DISPLAY_ZERO_VOLUME: Final = "거래량 0"

# 기준선 값 컬럼 앞에 붙이는 말
BASELINE_PREFIX: Final = "기준선 "

# 2단계. **「신호」를 쓰지 않는다** — 공통 계층의 신호 «건수» 머리다(`report/constants.DISPLAY_SIGNAL_COUNT`)
DISPLAY_INDICATOR_SIGNAL: Final = "지표 신호"
DISPLAY_SIGNAL_MEANING: Final = "책이 붙인 뜻"
DISPLAY_JUDGMENT_DATE: Final = "돌파일"
DISPLAY_PREVIOUS_VALUE: Final = "직전 값"
DISPLAY_INDICATOR_VALUE: Final = "판정 값"
DISPLAY_MONTHS_SINCE_HALVING: Final = "반감기 뒤 경과(개월)"
DISPLAY_CYCLE_COUNT: Final = "사이클 수"
DISPLAY_VALUE_DAY: Final = "값 기준일"
DISPLAY_INDICATOR_MONTH: Final = "월간 지표 기준 달"
DISPLAY_MVRV: Final = "MVRV"
DISPLAY_MVRV_Z: Final = "MVRV-Z"
DISPLAY_PI_CYCLE: Final = "Pi Cycle 비율"
DISPLAY_DISPARITY: Final = f"{DISPARITY_WINDOW}일 이격도(%)"
DISPLAY_MONTHLY_RSI: Final = f"월간 RSI({RSI_WINDOW})"
DISPLAY_MACD_HISTOGRAM: Final = "월간 MACD − 시그널"


# ============================================================
# 저장 직전 컬럼 헤더 (`COL_* → DISPLAY_*`)
# ============================================================

# 집계 컬럼과 그 이름. 기준선 쪽(접미사)은 이 목록에서 유도한다 — 손으로 두 벌 적으면 한쪽이 빠진다
_SUMMARY_LABELS: Final = (
    (COL_SIGNAL_COUNT, DISPLAY_SIGNAL_COUNT),
    (COL_EXCLUDED_COUNT, DISPLAY_EXCLUDED),
    (COL_SAMPLE_COUNT, DISPLAY_SAMPLE_COUNT),
    (COL_MEAN, DISPLAY_MEAN),
    (COL_MEDIAN, DISPLAY_MEDIAN),
    (COL_WIN_RATE, DISPLAY_UP_RATE),
    (COL_LOSS_RATE, DISPLAY_DOWN_RATE),
    (COL_MAX, DISPLAY_MAX),
    (COL_MIN, DISPLAY_MIN),
    (COL_STD, DISPLAY_STD),
    (COL_POSITIVE_MEAN, DISPLAY_POSITIVE_MEAN),
    (COL_NEGATIVE_MEAN, DISPLAY_NEGATIVE_MEAN),
    (COL_POSITIVE_COUNT, DISPLAY_POSITIVE_COUNT),
    (COL_NEGATIVE_COUNT, DISPLAY_NEGATIVE_COUNT),
)

# **정의만 하고 `rename` 에 연결하지 않으면 규칙을 지킨 것이 아니다** (`src/verify_lab/CLAUDE.md` 「내부/출력 분리」).
# 표마다 컬럼 구성이 달라 이 사전은 모든 표의 상위집합이다
COLUMN_LABELS: Final = {
    # 식별
    COL_TICKER: DISPLAY_TICKER,
    COL_ENTRY_MONTHS: DISPLAY_ENTRY_MONTHS,
    COL_HOLD_MONTHS: DISPLAY_HOLD_MONTHS,
    COL_HALVING: DISPLAY_HALVING,
    COL_DIRECTION: DISPLAY_DIRECTION,
    # 진입내역 (측정 long-form)
    COL_ENTRY_DATE: DISPLAY_ENTRY_DATE,
    COL_ENTRY_CLOSE: DISPLAY_ENTRY_CLOSE,
    COL_EXIT_DATE: DISPLAY_EXIT_DATE,
    COL_EXIT_CLOSE: DISPLAY_EXIT_CLOSE,
    COL_HOLD_DAYS: DISPLAY_HOLD_DAYS_EXACT,
    COL_FORWARD_RETURN: DISPLAY_RETURN,
    COL_EXCLUDED_REASON: DISPLAY_EXCLUDED_REASON,
    # 통계
    **dict(_SUMMARY_LABELS),
    COL_MEAN_RATE_CONFLICT: DISPLAY_MEAN_RATE_CONFLICT,
    COL_JUDGEABLE: DISPLAY_JUDGEABLE,
    COL_NON_OVERLAPPING: DISPLAY_NON_OVERLAPPING,
    # 기준선 (접미사) 과 기준선 대비 차이
    **{f"{column}{BASELINE_SUFFIX}": f"{BASELINE_PREFIX}{label}" for column, label in _SUMMARY_LABELS},
    COL_BASELINE_NON_OVERLAPPING: f"{BASELINE_PREFIX}{DISPLAY_NON_OVERLAPPING}",
    COL_SIGNAL_SAMPLE_COUNT: DISPLAY_SIGNAL_SAMPLE,
    COL_MEAN_EXCESS: DISPLAY_MEAN_DIFF,
    COL_MEDIAN_EXCESS: DISPLAY_MEDIAN_DIFF,
    COL_WIN_RATE_EXCESS: DISPLAY_UP_RATE_DIFF,
    COL_LOSS_RATE_EXCESS: DISPLAY_DOWN_RATE_DIFF,
    # 무작위 뽑기 대조. **판정에 쓰지 않지만 계산은 남긴다** — 지우면 기준선 중 「무작위 진입」이 사라진다
    COL_MEAN_P_VALUE: DISPLAY_MEAN_P_VALUE,
    COL_MEDIAN_P_VALUE: DISPLAY_MEDIAN_P_VALUE,
    COL_UP_RATE_P_VALUE: DISPLAY_UP_RATE_P_VALUE,
    COL_DOWN_RATE_P_VALUE: DISPLAY_DOWN_RATE_P_VALUE,
    COL_TEST_NOTE: DISPLAY_TEST_NOTE,
    # 달력 연도
    COL_CALENDAR_YEAR: DISPLAY_CALENDAR_YEAR,
    COL_HALVING_POSITION: DISPLAY_HALVING_POSITION,
    COL_PREVIOUS_CLOSE: DISPLAY_PREVIOUS_CLOSE,
    COL_YEAR_END_CLOSE: DISPLAY_YEAR_END_CLOSE,
    # 크로스체크 · 대체일
    COL_DATE: DISPLAY_DATE,
    COL_PRIMARY: DISPLAY_PRIMARY_CLOSE,
    COL_SECONDARY: DISPLAY_REFERENCE_CLOSE,
    COL_DIFF_RATE: DISPLAY_DIFF_RATE,
    COL_ZERO_VOLUME: DISPLAY_ZERO_VOLUME,
    # 2단계 — 신호일 목록 · 지표통계 · 지표사이클
    COL_INDICATOR_SIGNAL: DISPLAY_INDICATOR_SIGNAL,
    COL_SIGNAL_MEANING: DISPLAY_SIGNAL_MEANING,
    COL_JUDGMENT_DATE: DISPLAY_JUDGMENT_DATE,
    COL_PREVIOUS_VALUE: DISPLAY_PREVIOUS_VALUE,
    COL_INDICATOR_VALUE: DISPLAY_INDICATOR_VALUE,
    COL_MONTHS_SINCE_HALVING: DISPLAY_MONTHS_SINCE_HALVING,
    COL_CYCLE_COUNT: DISPLAY_CYCLE_COUNT,
    # 2단계 — 진입지표
    COL_VALUE_DAY: DISPLAY_VALUE_DAY,
    COL_INDICATOR_MONTH: DISPLAY_INDICATOR_MONTH,
    COL_MVRV: DISPLAY_MVRV,
    COL_MVRV_Z: DISPLAY_MVRV_Z,
    COL_PI_CYCLE: DISPLAY_PI_CYCLE,
    COL_DISPARITY: DISPLAY_DISPARITY,
    COL_MONTHLY_RSI: DISPLAY_MONTHLY_RSI,
    COL_MACD_HISTOGRAM: DISPLAY_MACD_HISTOGRAM,
    **{column: f"{months}개월 {DISPLAY_RETURN}" for months, column in COL_HOLD_RETURNS.items()},
}

# 비율(0~1)로 들어와 백분율로 내보낼 컬럼. **기준선과 차이 컬럼도 빠짐없이 넣는다** —
# 하나라도 빠지면 헤더는 `(%)` 인데 값이 비율로 남아 표 안에서 단위가 섞인다
_RATE_COLUMNS: Final = (
    COL_MEAN,
    COL_MEDIAN,
    COL_WIN_RATE,
    COL_LOSS_RATE,
    COL_MAX,
    COL_MIN,
    COL_STD,
    COL_POSITIVE_MEAN,
    COL_NEGATIVE_MEAN,
)

PERCENT_COLUMNS: Final = (
    *_RATE_COLUMNS,
    *(f"{column}{BASELINE_SUFFIX}" for column in _RATE_COLUMNS),
    COL_MEAN_EXCESS,
    COL_MEDIAN_EXCESS,
    COL_WIN_RATE_EXCESS,
    COL_LOSS_RATE_EXCESS,
    COL_FORWARD_RETURN,
    COL_DIFF_RATE,
    COL_DISPARITY,
    *COL_HOLD_RETURNS.values(),
)

# 저장 직전에 자릿수만 맞출 지표 값. **돌파 판정은 반올림 «전» 값으로 이미 끝났다** — 여기서 자르는 것은
# 부동소수점 잡음이 CSV 로 나가지 않게 하는 것뿐이다. RSI 는 0 ~ 100 지수라 백분율처럼 2자리다
INDICATOR_DECIMALS: Final = 4
RSI_DECIMALS: Final = 2
INDICATOR_VALUE_COLUMNS: Final = (
    COL_PREVIOUS_VALUE,
    COL_INDICATOR_VALUE,
    COL_MVRV,
    COL_MVRV_Z,
    COL_PI_CYCLE,
    COL_MACD_HISTOGRAM,
)

# 확률로 들어와 자릿수만 맞출 컬럼. **100 을 곱하지 않는다** — 우연확률은 비율이 아니다
PROBABILITY_COLUMNS: Final = (
    COL_MEAN_P_VALUE,
    COL_MEDIAN_P_VALUE,
    COL_UP_RATE_P_VALUE,
    COL_DOWN_RATE_P_VALUE,
)


# ============================================================
# 산출물 파일
# ============================================================

# **이 매매법의 표 넷은 여기가 소유한다.** 통계 · excess · test 는 측정 격자를 좁히지 않은 매매법의
# 공통 이름이라 `report/constants.py` 가 갖는다 (루트 `CLAUDE.md` 「판정에 쓰지 않는 값도 산출물에 남습니다」).
#
# **진입내역은 측정 long-form 그대로다** — 청산이 아직 오지 않은 진입도 행으로 남아 제외 사유가 보인다
ENTRIES_FILENAME: Final = "진입내역.csv"
CALENDAR_YEARS_FILENAME: Final = "달력연도.csv"
CROSSCHECK_FILENAME: Final = "크로스체크.csv"
REPLACED_FILENAME: Final = "대체일.csv"

# 2단계 넷. **지표통계는 한 장이다** — 통계 · excess · test 세 이름은 1단계 격자가 쓰고, 이 표는 판정이 없어
# 기준선을 옆에 두는 것이 「비율 옆에 기준선 비율」(`.claude/rules/docs.md`) 그대로다
INDICATOR_SIGNALS_FILENAME: Final = "지표신호.csv"
INDICATOR_STATISTICS_FILENAME: Final = "지표통계.csv"
INDICATOR_CYCLES_FILENAME: Final = "지표사이클.csv"
ENTRY_INDICATORS_FILENAME: Final = "진입지표.csv"

# **산출물 필드 이름 → 파일 이름.** 이 사전이 「이 검증이 무슨 파일을 내는가」의 자리다.
# **키는 문자열 리터럴이다** — 계약 검사가 이 사전을 AST 로 읽으므로 상수를 키에 쓰면 선언이 없는 것으로 보인다
OUTPUT_FILES: Final[dict[str, str]] = {
    "statistics": STATISTICS_FILENAME,
    "excess": EXCESS_FILENAME,
    "test": TEST_FILENAME,
    "entries": ENTRIES_FILENAME,
    "calendar_years": CALENDAR_YEARS_FILENAME,
    "crosscheck": CROSSCHECK_FILENAME,
    "replaced": REPLACED_FILENAME,
    "indicator_signals": INDICATOR_SIGNALS_FILENAME,
    "indicator_statistics": INDICATOR_STATISTICS_FILENAME,
    "indicator_cycles": INDICATOR_CYCLES_FILENAME,
    "entry_indicators": ENTRY_INDICATORS_FILENAME,
}

# 산출물 필드 이름. **사전에서 꺼낸다** — 같은 리터럴을 두 번 적으면 한쪽만 바뀌었을 때
# 측정이 다 끝난 «저장 시점»에야 `KeyError` 가 난다
(
    FIELD_STATISTICS,
    FIELD_EXCESS,
    FIELD_TEST,
    FIELD_ENTRIES,
    FIELD_CALENDAR_YEARS,
    FIELD_CROSSCHECK,
    FIELD_REPLACED,
    FIELD_INDICATOR_SIGNALS,
    FIELD_INDICATOR_STATISTICS,
    FIELD_INDICATOR_CYCLES,
    FIELD_ENTRY_INDICATORS,
) = OUTPUT_FILES


# ============================================================
# 실행 요약 키 — 측정과 체결이 함께 쓴다
# ============================================================

KEY_HALVINGS: Final = "halvings"
KEY_HEIGHT: Final = "height"
KEY_BLOCK_TIME: Final = "block_time"
KEY_DATE: Final = "date"
KEY_ENTRY_MONTHS: Final = "entry_months"
KEY_HOLD_MONTHS: Final = "hold_months"
KEY_LABEL: Final = "label"
# 이름 한 칸 — 측정은 지표 신호의 이름, 체결은 하드포크 코인의 이름을 싣는다
KEY_NAME: Final = "name"

# **진입 하나가 축의 칸 수만큼 세어진 행의 수다** — 측정은 진입 × 보유, 체결은 진입 × 청산이다.
# 제외는 청산일을 정하지 못한 행이다
KEY_SIGNAL_COUNT: Final = "signal_count"
KEY_EXCLUDED_COUNT: Final = "excluded_count"
