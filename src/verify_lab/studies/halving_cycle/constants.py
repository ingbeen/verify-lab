"""반감기_사이클 — 파라미터와 레이블

**격자는 결과를 보기 전에 정한 값이다** — 진입 = 반감기 뒤 0 ~ 45개월을 3개월 간격(16칸), 보유 = 3 · 6 · 12개월,
합 48칸이다(`docs/검증/반감기_사이클/설계.md` 결정 ⑥). 긴 보유와 고점·바닥 축은 그 결정의 탈락안이다.

**체결은 무손절 한 종 · 「위」 한 방향이다** (결정 ⑦ · 2026-09-29 사용자 결정). 손절은 사용자가 따로 정하고,
아래로 거는 칸의 크기와 빈도는 측정 표의 내린 비율이 준다.

**달력을 공통 계층에 올리지 않는다.** 진입이 「반감기일 + 개월」이라 중간선거_사이클의 「그 달 마지막
거래일」과 모양이 다르다 — 원칙에 없는 달력은 같은 모양이 세 번째로 올 때 정한다
(`src/verify_lab/CLAUDE.md` 「어디까지가 공통이고 어디부터 그 검증의 것인가」).
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pandas as pd

from verify_lab.common_constants import COL_DATE, MARKET_DIR, MARKET_FILE_TEMPLATE, PRICE_DECIMALS, SERIES_DIR
from verify_lab.data.bitstamp_collector import BITSTAMP_TICKER
from verify_lab.data.coinmetrics_collector import BTC_PRICE_SERIES
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
# 격자 — 결과를 보기 전에 정한 값 (결정 ⑥)
# ============================================================

# 반감기 뒤 진입 개월 — 0 ~ 45개월, 3개월 간격.
#
# [주의] **다음 반감기 앞이라는 보장이 없다.** 첫 반감기 간격이 약 43.4개월이라 2012 사이클의 45개월 진입
# (2016-08-28)은 다음 반감기(2016-07-09) «뒤»다. 그래도 격자를 고치지 않는다 — 결과를 본 뒤 칸의 정의를
# 바꾸면 사후 선택과 구별되지 않는다(`docs/검증/반감기_사이클/설계.md` 결정 ㉑)
ENTRY_MONTHS: Final = tuple(range(0, 46, 3))

# 보유 개월. 청산일 = 진입일 + 보유 개월(달력월)이다
HOLD_MONTHS: Final = (3, 6, 12)

# 거는 방향. **「위」 하나다** — 측정과 체결이 같은 값을 봐야 두 표의 `방향` 이 1:1 로 조인된다
BET_DOWN: Final = False

# 손절선. **무손절 한 종이다** (결정 ⑦). 손절은 사용자가 따로 정하며, 값을 골라 넣는 인자를 두지 않는다
STOP_LEVELS: Final[tuple[float | None, ...]] = (None,)


# ============================================================
# 검증 대상
# ============================================================


@dataclass(frozen=True)
class Dataset:
    """검증 대상 하나 — 시세와 거래량 0 인 날을 채울 대조 계열의 짝

    Attributes:
        ticker: 파일명에 쓰는 코드. **산출물의 데이터셋 구분자이므로 겹치면 안 된다**
        label: 표시 이름. **산출물의 종목 컬럼이 쓰는 값**이다
        directory: 시세 파일이 있는 폴더
        file_template: 시세 파일명 템플릿
        reference_path: 대조 계열(일별 단일 값) 파일. 거래량 0 인 날의 종가를 이 값으로 바꾼다(결정 ④)
        price_decimals: 가격 출력 자릿수. 원시 데이터를 저장한 값과 같아야 한다
        is_judged: 1차 판정을 거는가 — **살 수 있는 대상에만 건다** (측정의 원칙 9 · 결정 ⑤)
    """

    ticker: str
    label: str
    directory: Path
    file_template: str
    reference_path: Path
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

# 격자의 두 축
COL_ENTRY_MONTHS: Final = "entry_months"
COL_HOLD_MONTHS: Final = "hold_months"

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


# ============================================================
# 표시용 한글 레이블
# ============================================================

# **여기 없는 이름은 공통 계층에서 가져온다** — 같은 뜻에 이름이 두 벌이 되면 두 산출물의 헤더가 갈린다
DISPLAY_HALVING: Final = "반감기"
DISPLAY_ENTRY_MONTHS: Final = "반감기 뒤 진입(개월)"
DISPLAY_HOLD_MONTHS: Final = "보유(개월)"

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

# **진입 × 보유 칸의 수다** — 진입 하나가 보유 셋으로 세 번 세어진다. 제외는 청산이 데이터 끝을 넘은 칸이다
KEY_SIGNAL_COUNT: Final = "signal_count"
KEY_EXCLUDED_COUNT: Final = "excluded_count"
