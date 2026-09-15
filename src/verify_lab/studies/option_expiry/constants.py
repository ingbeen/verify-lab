"""검증 #7(옵션 만기일) 이벤트 정의와 실행이 공유하는 상수

파라미터 값은 `docs/매매/옵션_만기일/설계.md` 가 확정한 것이며, **성과를 보며 돌리는 노브가 아니다.**
여러 값을 나란히 산출해 보고하기 위한 목록이므로 하나를 골라 두지 않는다.

표시용 한글 레이블도 여기 둔다. `report` 는 어떤 검증이 자기를 쓰는지 몰라야 하므로
검증별 컬럼 이름을 알 수 없고, 그 이름을 정하는 것은 이 검증의 몫이다.
"""

from dataclasses import dataclass
from typing import Final

from verify_lab.common_constants import COL_CLOSE, COL_DATE, MARKET_FILE_TEMPLATE, PRICE_DECIMALS, PRICE_DECIMALS_KRW
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_EXCLUDED_COUNT,
    COL_EXCLUDED_REASON,
    COL_FORWARD_RETURN,
    COL_HORIZON,
    COL_JUDGEABLE,
    COL_MEAN_RATE_CONFLICT,
    COL_SIGNAL_COUNT,
)
from verify_lab.measure.screening import (
    COL_BASELINE_GAP,
    COL_BASELINE_HIT_RATE,
    COL_DIRECTION,
    COL_EXPECTED_VALUE,
    COL_HIT_RATE,
    COL_SCREEN,
    COL_TOTAL_RETURN,
)
from verify_lab.measure.statistics import (
    COL_BASELINE_SAMPLE_COUNT,
    COL_DOWN_RATE_P_VALUE,
    COL_DOWN_RATE_PERCENTILE,
    COL_LOSS_RATE,
    COL_LOSS_RATE_EXCESS,
    COL_MAX,
    COL_MEAN,
    COL_MEAN_EXCESS,
    COL_MEAN_P_VALUE,
    COL_MEAN_PERCENTILE,
    COL_MEDIAN,
    COL_MEDIAN_EXCESS,
    COL_MEDIAN_P_VALUE,
    COL_MEDIAN_PERCENTILE,
    COL_MIN,
    COL_NEGATIVE_COUNT,
    COL_NEGATIVE_MEAN,
    COL_NULL_MEAN_P05,
    COL_NULL_MEAN_P95,
    COL_OBSERVED_DOWN_RATE,
    COL_OBSERVED_MEAN,
    COL_OBSERVED_MEDIAN,
    COL_OBSERVED_UP_RATE,
    COL_POSITIVE_COUNT,
    COL_POSITIVE_MEAN,
    COL_SAMPLE_COUNT,
    COL_SIGNAL_SAMPLE_COUNT,
    COL_STD,
    COL_TEST_NOTE,
    COL_UP_RATE_P_VALUE,
    COL_UP_RATE_PERCENTILE,
    COL_WIN_RATE,
    COL_WIN_RATE_EXCESS,
)
from verify_lab.report.constants import (
    CANDIDATES_FILENAME,
    DISPLAY_BASELINE_GAP,
    DISPLAY_BASELINE_HIT_RATE,
    DISPLAY_BASELINE_SAMPLE,
    DISPLAY_BASIS,
    DISPLAY_DATE,
    DISPLAY_DIRECTION,
    DISPLAY_DOWN_RATE,
    DISPLAY_DOWN_RATE_DIFF,
    DISPLAY_DOWN_RATE_P_VALUE,
    DISPLAY_DOWN_RATE_PERCENTILE,
    DISPLAY_EXCLUDED,
    DISPLAY_EXPECTED_VALUE,
    DISPLAY_HIT_RATE,
    DISPLAY_JUDGEABLE,
    DISPLAY_MAX,
    DISPLAY_MEAN,
    DISPLAY_MEAN_DIFF,
    DISPLAY_MEAN_P_VALUE,
    DISPLAY_MEAN_PERCENTILE,
    DISPLAY_MEAN_RATE_CONFLICT,
    DISPLAY_MEDIAN,
    DISPLAY_MEDIAN_DIFF,
    DISPLAY_MEDIAN_P_VALUE,
    DISPLAY_MEDIAN_PERCENTILE,
    DISPLAY_MIN,
    DISPLAY_NEGATIVE_COUNT,
    DISPLAY_NEGATIVE_MEAN,
    DISPLAY_NULL_P05,
    DISPLAY_NULL_P95,
    DISPLAY_OBSERVED_DOWN_RATE,
    DISPLAY_OBSERVED_MEAN,
    DISPLAY_OBSERVED_MEDIAN,
    DISPLAY_OBSERVED_UP_RATE,
    DISPLAY_PERIOD,
    DISPLAY_POSITIVE_COUNT,
    DISPLAY_POSITIVE_MEAN,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_SCREEN,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_SIGNAL_SAMPLE,
    DISPLAY_STD,
    DISPLAY_TEST_NOTE,
    DISPLAY_TOTAL_RETURN,
    DISPLAY_UP_RATE,
    DISPLAY_UP_RATE_DIFF,
    DISPLAY_UP_RATE_P_VALUE,
    DISPLAY_UP_RATE_PERCENTILE,
    SIGNALS_FILENAME,
)


@dataclass(frozen=True)
class ExpiryRule:
    """월물 만기일을 정하는 달력 규칙

    만기일은 시세와 무관한 **달력 규칙**이다. 규칙일이 휴장이면 직전 거래일까지 앞당겨지며,
    그 판정에 필요한 거래일 목록은 시세 파일의 날짜 인덱스에서 온다
    (`docs/매매/옵션_만기일/설계.md` 결정 ⑤).

    Attributes:
        label: 표시 이름
        weekday: 요일 (월=0 ~ 일=6). `pandas` 의 `dayofweek` 와 같은 기준이다
        ordinal: 그 달에서 몇 번째 해당 요일인가 (1부터)
    """

    label: str
    weekday: int
    ordinal: int


# 요일 번호 (월=0 ~ 일=6). `pandas` 의 `dayofweek` 와 같은 기준이다
THURSDAY: Final = 3
FRIDAY: Final = 4

# 미국 월물 옵션 만기 — 매월 셋째 금요일
US_MONTHLY_EXPIRY: Final = ExpiryRule(label="셋째 금요일", weekday=FRIDAY, ordinal=3)

# 한국 월물 옵션 만기 — 매월 둘째 목요일
KR_MONTHLY_EXPIRY: Final = ExpiryRule(label="둘째 목요일", weekday=THURSDAY, ordinal=2)


# ============================================================
# 상대 거래일 (offset)
# ============================================================

# 만기일을 0 으로 두고 앞뒤로 셀 거래일 수. 앞뒤 2주씩이면 문헌이 말하는 창이 전부 들어간다.
# 하나를 고르지 않고 이 범위를 전부 산출해 나란히 보고한다 (측정의 원칙 1)
MAX_OFFSET: Final = 10


# ============================================================
# DataFrame 컬럼
# ============================================================

COL_EXPIRY_MONTH: Final = "expiry_month"
COL_RULE_DATE: Final = "rule_date"
COL_EXPIRY_DATE: Final = "expiry_date"
COL_ADVANCED_DAYS: Final = "advanced_days"
COL_OFFSET: Final = "offset"

# 그날이 그 달의 몇 번째 거래일인가. 만기 창은 언제나 월 중순이라 offset 과 거의 붙어 다니므로,
# **두 축이 구별되는지**를 독자가 직접 볼 수 있게 함께 낸다 (결정 ⑭)
COL_MONTH_DAY_INDEX: Final = "month_day_index"

# 그날 하루의 등락률. forward return 과 달리 앞날을 보지 않는다
COL_DAILY_RETURN: Final = "daily_return"

# 산출물의 식별 컬럼 — 어떤 조합에서 나온 행인지
COL_TICKER: Final = "ticker"


# ============================================================
# 달력 기준 청산 (만기일 매수 → 다음주 금요일 매도)
# ============================================================

# 목표일을 셀 때 기준이 되는 날. 만기 진입에서는 **규칙일**이며 실제 만기일이 아니다 —
# 앞당김은 만기 쪽 사정이라 목표 주까지 끌고 가면 한국 추석 달의 보유가 1거래일로 무너진다
# (`docs/매매/옵션_만기일/설계.md` 결정 ⑰)
COL_WEEK_REFERENCE: Final = "week_reference"

# 달력이 지목한 청산일. 그날이 휴장이면 실제 청산일과 달라진다
COL_TARGET_DATE: Final = "target_date"

# 실제로 판 날. 목표일이 휴장이면 직전 거래일이다 (결정 ⑱)
COL_EXIT_DATE: Final = "exit_date"

# 진입일부터 청산일까지의 거래일 수. **신호마다 다르다** — 청산이 달력 기준이기 때문이다
COL_HOLD_DAYS: Final = "hold_days"

COL_ENTRY_CLOSE: Final = "entry_close"
COL_EXIT_CLOSE: Final = "exit_close"

# 청산 요일 축 — 한국은 금요일 청산과 목요일 청산을 나란히 낸다 (결정 ⑳)
COL_EXIT_WEEKDAY: Final = "exit_weekday"

# 기준선 대비 차이 표에서 어느 기준선과 견줬는지 밝히는 축. 둘은 묻는 질문이 다르다
# (`docs/매매/옵션_만기일/설계.md` §3.7)
COL_BASELINE_KIND: Final = "baseline"

# 같은 달 기준선 통계에 붙는 접미사. `_aggregate_by_month` 의 merge suffix 와 **같은 값이어야**
# 산출물 컬럼과 한글 사전이 어긋나지 않는다
BASELINE_SUFFIX: Final = "_baseline"

# 만기월을 1~12 정수로 놓는 축. `COL_EXPIRY_MONTH` 는 "YYYY-MM" 문자열이라 12칸으로 묶이지 않는다
COL_EXPIRY_MONTH_NUMBER: Final = "expiry_month_number"

# 시기 분할 축. 신호를 **시간순으로 세어 균등하게** 가른다 — 시장 구조가 바뀐 시점으로 나누는
# 달력 경계 방식은 칸마다 표본이 들쭉날쭉해 쓰지 않는다(`docs/매매/옵션_만기일/설계.md` 결정 ㉖).
# 후보 판정의 시기 항목은 **칸당 표본 하한**을 지켜야 하므로 이 축으로 잰다
#
# 절반 구간의 **이름**은 공통 계층이 소유한다 (`measure/constants.py` 의
# `PERIOD_FIRST_HALF`·`PERIOD_SECOND_HALF`) — 원칙 17 이 모든 매매법에 요구하는 축이다
COL_TIME_HALF: Final = "time_half"

# 묶음 집계에서 쓰는 구간 표지. 보유 거래일 수를 구간 축에 넣으면 **한 매매가 여러 칸으로 쪼개져**
# 묶음 값이 나오지 않는다. 실제 보유일수로는 도달할 수 없는 음수를 써서 진짜 구간과 섞이지 않게 한다
# (`docs/매매/옵션_만기일/설계.md` 결정 ㉑)
HORIZON_NEXT_WEEK_EXIT: Final = -1

# 그 표지가 산출물에 나갈 때의 표시값. **`-1` 을 그대로 내보내지 않는다** — 사용자가 여는 CSV 에
# 「보유 거래일 -1」이 찍히고, 그것이 묶음 행이라는 사실은 코드를 읽어야만 알 수 있다
DISPLAY_HOLD_DAYS_POOLED: Final = "전체"


# ============================================================
# 검증 대상 시세
# ============================================================


@dataclass(frozen=True)
class Dataset:
    """검증 대상 종목 하나

    **가격 기준은 원본가 하나다.** 사용자가 증권앱·차트에서 보는 가격이 곧 신호를 판정하고
    주문을 거는 가격이기 때문이며, 두 기준을 나란히 내면 결과를 보고 고를 여지가 생긴다
    (루트 `CLAUDE.md` 측정의 원칙 14).

    **`ticker` 와 `label` 은 다른 것이다.** 코드는 차트·증권앱과 대조할 때 필요하고
    표시 이름은 산출물이 쓴다. **미국 ETF 는 둘이 같아(`QQQ`) 구별이 드러나지 않지만
    국내는 갈린다** — 둘을 겸하면 `069500` 이 어디에도 남지 않는다.

    Attributes:
        key: 실행 인자로 고르는 이름
        ticker: 종목코드. **`summary.json` 의 `datasets` 에만 실린다** — 행마다 반복할
            값이 아니라 데이터셋 단위 속성이다 (`src/verify_lab/CLAUDE.md` 출력 계약)
        label: 종목 표시 이름. **산출물의 종목 컬럼이 쓰는 값**이다
        rule: 그 시장의 월물 만기 규칙
        file_name: `storage/market/` 안의 원본가 파일 이름
        price_decimals: 종가를 저장할 때의 반올림 자릿수
        exit_weekdays: 달력 기준 청산의 목표 요일. 첫 번째가 본검증이고 나머지는 대조다.
            **한국만 두 벌**인 이유는 만기가 목요일이라 같은 "다음주 금요일"이
            미국 5거래일 · 한국 6거래일이 되기 때문이다 (`docs/매매/옵션_만기일/설계.md` 결정 ⑳)
    """

    key: str
    ticker: str
    label: str
    rule: ExpiryRule
    file_name: str
    price_decimals: int
    exit_weekdays: tuple[int, ...]


DATASETS: Final = (
    Dataset(
        key="qqq",
        ticker="QQQ",
        label="QQQ",
        rule=US_MONTHLY_EXPIRY,
        file_name=MARKET_FILE_TEMPLATE.format(ticker="QQQ"),
        price_decimals=PRICE_DECIMALS,
        exit_weekdays=(FRIDAY,),
    ),
    Dataset(
        key="spy",
        ticker="SPY",
        label="SPY",
        rule=US_MONTHLY_EXPIRY,
        file_name=MARKET_FILE_TEMPLATE.format(ticker="SPY"),
        price_decimals=PRICE_DECIMALS,
        exit_weekdays=(FRIDAY,),
    ),
    Dataset(
        # 미국 세 번째 대표 지수. QQQ·SPY 는 독립 표본이 아니므로 "두 ETF에서 같은 모양"을
        # 두 번의 확인으로 셀 수 없다 — 세 번째로 검산한다 (결정 ㉒)
        key="dia",
        ticker="DIA",
        label="DIA",
        rule=US_MONTHLY_EXPIRY,
        file_name=MARKET_FILE_TEMPLATE.format(ticker="DIA"),
        price_decimals=PRICE_DECIMALS,
        exit_weekdays=(FRIDAY,),
    ),
    Dataset(
        # 원본가는 상장일(2002-10-14)부터 있다. 수정주가는 조회 시점 기준 최근 3,000거래일만
        # 존재해 2014년부터인데, **분배락은 만기 4~10거래일 전에 박혀 있어 이 매매의 보유
        # 구간(만기일 이후)과 겹치지 않는다.** 그래서 원본가로 전 기간을 쓴다 (결정 ㉜)
        key="kodex200",
        ticker="069500",
        label="KODEX 200",
        rule=KR_MONTHLY_EXPIRY,
        file_name=MARKET_FILE_TEMPLATE.format(ticker="069500"),
        price_decimals=PRICE_DECIMALS_KRW,
        exit_weekdays=(FRIDAY, THURSDAY),
    ),
)


# ============================================================
# 표시용 레이블
# ============================================================

DISPLAY_EXPIRY_MONTH: Final = "만기월"
DISPLAY_RULE_DATE: Final = "규칙일"
DISPLAY_EXPIRY_DATE: Final = "만기일"
DISPLAY_ADVANCED_DAYS: Final = "앞당김(달력일)"
DISPLAY_OFFSET: Final = "상대 거래일"
DISPLAY_TICKER: Final = "종목"
DISPLAY_MONTH_DAY_INDEX: Final = "월중 서수"
DISPLAY_DAILY_RETURN: Final = "일간 등락률(%)"
DISPLAY_CLOSE: Final = "종가"

DISPLAY_EXIT_WEEKDAY: Final = "청산 요일"

# 만기일 매수 → 다음주 청산 매매의 진입 수. **`report` 의 「신호」와 뜻이 같지만 말이 다르다** —
# 이 매매는 만기일이 곧 진입일이라 화면에서 「진입」으로 읽는 것이 자연스럽다
DISPLAY_ENTRY_COUNT: Final = "진입"

# 요일 번호를 표에 적을 때 쓰는 이름
WEEKDAY_LABELS: Final = ("월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일")


# ============================================================
# 산출물
# ============================================================

# 이 매매법의 이름(slug). 규약은 `src/verify_lab/CLAUDE.md` 「매매법 이름 계약」이 SoT다
TRACK_NAME: Final = "option_expiry"

# 만기월 축과 구별되는 이름. `COL_EXPIRY_MONTH` 는 "2026-08" 같은 연월 문자열이고
# `COL_EXPIRY_MONTH_NUMBER` 는 1~12 다. 둘 다 "만기월"로 적으면 어느 축인지 알 수 없다
DISPLAY_EXPIRY_YEAR_MONTH: Final = "만기 연월"

DISPLAY_BASELINE_KIND: Final = "기준선 종류"
DISPLAY_WEEK_REFERENCE: Final = "주 기준일"
DISPLAY_TARGET_DATE: Final = "청산 목표일"
DISPLAY_EXIT_DATE: Final = "실제 청산일"
DISPLAY_HOLD_DAYS: Final = "보유 거래일"
DISPLAY_ENTRY_CLOSE: Final = "진입 종가"
DISPLAY_EXIT_CLOSE: Final = "청산 종가"
DISPLAY_FORWARD_RETURN: Final = "수익률(%)"
DISPLAY_EXCLUDED_REASON: Final = "제외 사유"

# 기준선 쪽 통계에 붙는 접두사. `_aggregate_by_month` 가 merge 하며 만드는 `_baseline` 접미사를
# 사람이 읽는 말로 바꾼다
_BASELINE_PREFIX: Final = "기준선 "

# 산출물 CSV 의 컬럼 한글 이름 (`src/verify_lab/CLAUDE.md` 「내부/출력 분리」).
# **전 산출물을 한 사전으로 덮는다** — 파일마다 사전을 두면 같은 컬럼에 다른 이름이 붙는다.
# 공통 컬럼은 `report/constants.py` 의 것을 그대로 쓴다: 검증마다 다른 말을 쓰면
# 두 결과를 나란히 읽을 수 없다
OUTPUT_LABELS: Final = {
    # 식별 축
    COL_TICKER: DISPLAY_TICKER,
    COL_EXIT_WEEKDAY: DISPLAY_EXIT_WEEKDAY,
    COL_EXPIRY_MONTH_NUMBER: DISPLAY_EXPIRY_MONTH,
    COL_EXPIRY_MONTH: DISPLAY_EXPIRY_YEAR_MONTH,
    COL_TIME_HALF: DISPLAY_PERIOD,
    COL_JUDGEABLE: DISPLAY_JUDGEABLE,
    COL_BASELINE_KIND: DISPLAY_BASELINE_KIND,
    # 만기일 달력
    COL_RULE_DATE: DISPLAY_RULE_DATE,
    COL_EXPIRY_DATE: DISPLAY_EXPIRY_DATE,
    COL_ADVANCED_DAYS: DISPLAY_ADVANCED_DAYS,
    # 만기 창 신호일 원자료
    COL_DATE: DISPLAY_DATE,
    COL_CLOSE: DISPLAY_CLOSE,
    COL_DAILY_RETURN: DISPLAY_DAILY_RETURN,
    COL_OFFSET: DISPLAY_OFFSET,
    COL_MONTH_DAY_INDEX: DISPLAY_MONTH_DAY_INDEX,
    # 매매 원자료
    COL_WEEK_REFERENCE: DISPLAY_WEEK_REFERENCE,
    COL_TARGET_DATE: DISPLAY_TARGET_DATE,
    COL_EXIT_DATE: DISPLAY_EXIT_DATE,
    COL_HOLD_DAYS: DISPLAY_HOLD_DAYS,
    COL_ENTRY_CLOSE: DISPLAY_ENTRY_CLOSE,
    COL_EXIT_CLOSE: DISPLAY_EXIT_CLOSE,
    COL_FORWARD_RETURN: DISPLAY_FORWARD_RETURN,
    COL_EXCLUDED_REASON: DISPLAY_EXCLUDED_REASON,
    # 집계
    COL_BASIS: DISPLAY_BASIS,
    COL_HORIZON: DISPLAY_HOLD_DAYS,
    COL_SIGNAL_COUNT: DISPLAY_SIGNAL_COUNT,
    COL_EXCLUDED_COUNT: DISPLAY_EXCLUDED,
    COL_SAMPLE_COUNT: DISPLAY_SAMPLE_COUNT,
    COL_MEAN: DISPLAY_MEAN,
    COL_MEDIAN: DISPLAY_MEDIAN,
    COL_WIN_RATE: DISPLAY_UP_RATE,
    COL_LOSS_RATE: DISPLAY_DOWN_RATE,
    COL_MAX: DISPLAY_MAX,
    COL_MIN: DISPLAY_MIN,
    COL_STD: DISPLAY_STD,
    COL_POSITIVE_MEAN: DISPLAY_POSITIVE_MEAN,
    COL_NEGATIVE_MEAN: DISPLAY_NEGATIVE_MEAN,
    COL_POSITIVE_COUNT: DISPLAY_POSITIVE_COUNT,
    COL_NEGATIVE_COUNT: DISPLAY_NEGATIVE_COUNT,
    COL_MEAN_RATE_CONFLICT: DISPLAY_MEAN_RATE_CONFLICT,
    # 같은 달 기준선 (merge 가 붙인 `_baseline` 접미사)
    **{
        f"{column}{BASELINE_SUFFIX}": f"{_BASELINE_PREFIX}{label}"
        for column, label in (
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
    },
    # 기준선 대비 차이
    COL_SIGNAL_SAMPLE_COUNT: DISPLAY_SIGNAL_SAMPLE,
    COL_BASELINE_SAMPLE_COUNT: DISPLAY_BASELINE_SAMPLE,
    COL_MEAN_EXCESS: DISPLAY_MEAN_DIFF,
    COL_MEDIAN_EXCESS: DISPLAY_MEDIAN_DIFF,
    COL_WIN_RATE_EXCESS: DISPLAY_UP_RATE_DIFF,
    COL_LOSS_RATE_EXCESS: DISPLAY_DOWN_RATE_DIFF,
    # 무작위 뽑기 대조
    COL_OBSERVED_MEAN: DISPLAY_OBSERVED_MEAN,
    COL_OBSERVED_MEDIAN: DISPLAY_OBSERVED_MEDIAN,
    COL_NULL_MEAN_P05: DISPLAY_NULL_P05,
    COL_NULL_MEAN_P95: DISPLAY_NULL_P95,
    COL_MEAN_PERCENTILE: DISPLAY_MEAN_PERCENTILE,
    COL_MEAN_P_VALUE: DISPLAY_MEAN_P_VALUE,
    COL_MEDIAN_PERCENTILE: DISPLAY_MEDIAN_PERCENTILE,
    COL_MEDIAN_P_VALUE: DISPLAY_MEDIAN_P_VALUE,
    COL_OBSERVED_UP_RATE: DISPLAY_OBSERVED_UP_RATE,
    COL_UP_RATE_PERCENTILE: DISPLAY_UP_RATE_PERCENTILE,
    COL_UP_RATE_P_VALUE: DISPLAY_UP_RATE_P_VALUE,
    COL_OBSERVED_DOWN_RATE: DISPLAY_OBSERVED_DOWN_RATE,
    COL_DOWN_RATE_PERCENTILE: DISPLAY_DOWN_RATE_PERCENTILE,
    COL_DOWN_RATE_P_VALUE: DISPLAY_DOWN_RATE_P_VALUE,
    COL_TEST_NOTE: DISPLAY_TEST_NOTE,
    # 후보 판정
    COL_DIRECTION: DISPLAY_DIRECTION,
    COL_HIT_RATE: DISPLAY_HIT_RATE,
    COL_EXPECTED_VALUE: DISPLAY_EXPECTED_VALUE,
    COL_TOTAL_RETURN: DISPLAY_TOTAL_RETURN,
    COL_BASELINE_HIT_RATE: DISPLAY_BASELINE_HIT_RATE,
    COL_BASELINE_GAP: DISPLAY_BASELINE_GAP,
    COL_SCREEN: DISPLAY_SCREEN,
}

# 비율(0~1)로 계산해 백분율로 내보낼 컬럼. 헤더에 `(%)` 가 붙는 것과 짝을 이룬다
PERCENT_OUTPUT_COLUMNS: Final = (
    COL_DAILY_RETURN,
    COL_FORWARD_RETURN,
    COL_MEAN,
    COL_MEDIAN,
    COL_WIN_RATE,
    COL_LOSS_RATE,
    COL_MAX,
    COL_MIN,
    COL_STD,
    COL_POSITIVE_MEAN,
    COL_NEGATIVE_MEAN,
    *(
        f"{column}{BASELINE_SUFFIX}"
        for column in (
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
    ),
    COL_MEAN_EXCESS,
    COL_MEDIAN_EXCESS,
    COL_WIN_RATE_EXCESS,
    COL_LOSS_RATE_EXCESS,
    COL_OBSERVED_MEAN,
    COL_OBSERVED_MEDIAN,
    COL_NULL_MEAN_P05,
    COL_NULL_MEAN_P95,
    COL_OBSERVED_UP_RATE,
    COL_OBSERVED_DOWN_RATE,
    COL_HIT_RATE,
    COL_EXPECTED_VALUE,
    COL_TOTAL_RETURN,
    COL_BASELINE_HIT_RATE,
    COL_BASELINE_GAP,
    # 백분위는 **백분율이지 확률이 아니다.** 「귀무분포에서 관측값보다 작은 값의 비율」이라
    # 0~100 으로 읽는 값이며, `report.build_test_table` 도 같은 자릿수로 낸다
    COL_MEAN_PERCENTILE,
    COL_MEDIAN_PERCENTILE,
    COL_UP_RATE_PERCENTILE,
    COL_DOWN_RATE_PERCENTILE,
)

# 확률로 계산해 자릿수만 맞출 컬럼. **100 을 곱하지 않는다** — 우연확률은 비율이 아니다
PROBABILITY_OUTPUT_COLUMNS: Final = (
    COL_MEAN_P_VALUE,
    COL_MEDIAN_P_VALUE,
    COL_UP_RATE_P_VALUE,
    COL_DOWN_RATE_P_VALUE,
)


# ============================================================
# 산출물 파일
# ============================================================

# **산출물 필드 이름 → 파일 이름.** 이 사전이 「이 검증이 무슨 파일을 내는가」의 자리다.
# runner 가 `row_counts` 를 이것으로 키잉하고 CLI 가 이것을 돌며 저장한다 —
# 왜 CLI 가 이름을 갖지 않는지는 `src/verify_lab/CLAUDE.md` 실행 요약 계약이 SoT 다.
OUTPUT_FILES: Final[dict[str, str]] = {
    "expiries": "expiries.csv",
    # 공통 컬럼의 파일 이름은 `report/constants.py` 가 소유한다 — 역방향도 같은 상수를 쓴다
    "signals": SIGNALS_FILENAME,
    "trade_signals": "weekly_trade_signals.csv",
    "trade_summary": "weekly_trade_summary.csv",
    "trade_excess": "weekly_trade_excess.csv",
    "trade_test": "weekly_trade_permutation.csv",
    "trade_by_month": "weekly_trade_by_month.csv",
    "trade_by_month_halves": "weekly_trade_by_month_halves.csv",
    "candidates": CANDIDATES_FILENAME,
}


# ============================================================
# 매매 파라미터
# ============================================================
#
# 규칙의 확정 근거는 이 매매법의 규칙 문서가 SoT다.
# **여기 값은 과거 신호를 보고 고른 것**이며, 성적은 과거 재구성이지 예측이 아니다.
#
# **이 매매법의 값을 공유 모듈에 두지 않는다.** 매매법 이름이 붙지 않는 것(파일명 상수·
# 청산 사유·구간 축·`stop_level_value`)은 `execution/constants.py` 가 갖는다 —
# `tests/test_layer_contracts.py` 가 공유 모듈이 이 파일을 가져오지 못하게 막는다.

# ============================================================
# 손절 격자
# ============================================================

# 확정된 손절선. **진입가 기준이며 보유 기간 내내 바뀌지 않는다.**
#
# **성적이 가장 좋아서 고른 값이 아니다.** 격자 실측에서 무손절이 어느 손절선보다도 나았고
# (7칸 합계 +175.07% 대 최고 +174.43%), 손절의 값은 수익이 아니라 **최악 통제**에 있다.
# 이 값을 고른 근거는 **최악 통제가 포화되는 지점**이라는 것이다 — KODEX 200 9월의
# 2011-09-08 진입 건이 **−5.35% 갭**이라 그보다 좁은 손절선은 전부 그 갭에 뚫리고,
# 최악은 −5.35% 에서 더 줄지 않는데 합계만 계속 깎인다.
# **역방향 매매의 「갭손절 0건의 첫 지점」 논리는 여기서 못 쓴다** — 보유가 5~6거래일이라
# 갭손절 건수가 손절선에 대해 단조롭지 않다. 근거 격자는
# `docs/매매/옵션_만기일/결과.md` 12B.2·12B.3·12B.4 에 있다
EXPIRY_STOP_LEVEL: Final = 0.05

# **확정 규칙이 아니라 대조축이다.** 손절선을 다시 고를 때 쓰는 격자이고 **기본 실행이
# 이것을 전부 낸다** — 확정 손절선 한 행은 `손절선(%)` 한 컬럼 필터로 고른다.
# **시세를 재수집하면 이 절차를 다시 밟아야 한다** — `.claude/rules/trading.md` 가
# 「손절선 후보를 격자로 전부 돌려 평평한 구간을 찾는다」를 절차로 요구하기 때문이다.
#
# 하한을 -1% 로 연 것은 이 매매의 표준편차가 2.26~3.31% 라 **-1% 대에서 이미 노이즈 손절이
# 나올 것으로 보기 때문**이다. 역방향 매매는 보유가 1~2거래일이라 -2% 부터 열어도 됐지만
# 여기는 5~6거래일이라 손절선이 닿는 빈도가 다르다.
# 상한 -10% 는 전체 월 합계 최악(QQQ -10.65% · SPY -11.16% · DIA -12.14% ·
# KODEX 200 -13.44%)을 다 덮지는 않지만, 그보다 넓히면 손절이 사실상 무손절과 같아진다 —
# 무손절 자체는 `None` 행으로 따로 낸다
EXPIRY_STOP_LEVELS: Final = tuple(round(0.010 + 0.005 * step, 4) for step in range(19))


# ============================================================
# 대상 칸
# ============================================================


@dataclass(frozen=True)
class ExpiryCell:
    """옵션 만기일 매매의 대상 칸 하나

    Attributes:
        dataset_key: `studies.option_expiry` 의 데이터셋 이름
        expiry_month: 만기월 (1~12)
        bet_down: 아래로 거는 칸인지 여부. 참이면 원지수가 내려야 이익이다
    """

    dataset_key: str
    expiry_month: int
    bet_down: bool


# `docs/매매/옵션_만기일/결과.md` 0장에서 **게이트를 넘은 칸**이다. 전부 금요일 청산이다.
#
# **통계량으로 칸을 빼지 않는다.** 게이트를 넘었으면 함께 두며, 통계량으로 빼면
# 60칸에서 좋아 보이는 칸만 고르는 **사후 선택**이 된다 (결정 ㊳).
# **그래서 이 목록은 「실제로 거는 칸」이 아니다** — 그쪽은 `docs/매매/옵션_만기일/규칙.md`
# §1.1 이 갖고 이 목록보다 좁다. 여기서 칸을 빼려면 통계량이 아니라 데이터 오염이나
# 사용자 결정 같은 게이트 밖의 근거가 있어야 한다.
# **게이트 위에 「등급」 표기를 두지 않는다** — 등급 자체가 판정에 없다 (결정 ㊹).
#
# **미국 9월 세 칸은 같은 날 같은 방향이라 독립된 세 번의 기회가 아니다.** QQQ·SPY·DIA 는
# 같은 시장의 지수 ETF로 상관이 매우 높아 사실상 한 번의 베팅이며, 산출물을 읽을 때
# 세 번의 확인으로 세면 안 된다 (결과 문서 §12A.6). **다만 12월에는 QQQ↔DIA 상관이 0.418 로
# 9월(0.769)보다 훨씬 낮다** — 12월 세 칸은 9월만큼 같이 움직이지 않는다.
#
# **DIA 6월은 아직 이 목록에 없다.** 시기 축이 판정에 들어가지 않으므로 게이트로는 후보다
# (결정 ㊸·㊺ — 표본 29 · 적중률 75.86% · 회당 +0.44%).
# 뒤 절반 −0.167% · 최근 5년 −1.832% 는 그대로 사실이지만 **관찰용**이며,
# **넣을지는 사용자가 정한다** — 코드가 대신 판단하지 않으므로 결정 전까지 목록 밖에 둔다
EXPIRY_CELLS: Final = (
    ExpiryCell(dataset_key="dia", expiry_month=12, bet_down=False),
    ExpiryCell(dataset_key="kodex200", expiry_month=9, bet_down=False),
    ExpiryCell(dataset_key="spy", expiry_month=9, bet_down=True),
    ExpiryCell(dataset_key="dia", expiry_month=9, bet_down=True),
    ExpiryCell(dataset_key="spy", expiry_month=12, bet_down=False),
    ExpiryCell(dataset_key="qqq", expiry_month=9, bet_down=True),
    # 기준선 대비 +6.33%p 로 얇다. **통계적 근거가 있어서 넣는 것이 아니라,
    # 뺄 근거가 사후 선택뿐이라 안 빼는 것이다.** 같은 27건으로 맞춰도 적중률이
    # 62.96% 로 DIA(81.48%)·SPY(70.37%)보다 낮아 표본 기간 탓이 아니다
    ExpiryCell(dataset_key="qqq", expiry_month=12, bet_down=False),
)

# **만기월과 청산 목표일의 레이블은 위 측정 절에 이미 있다.** 측정과 체결이 같은 이름을
# 쓰는 것이 의도이며, 두 벌을 두면 한쪽만 고쳐도 예외가 나지 않고 두 표의 헤더만 갈린다


# ============================================================
# 실행 요약 키
# ============================================================

# 청산일을 확정하지 못해 빠진 진입 수. **측정과 매매가 같은 것을 세므로 한 곳에서 정의한다** —
# 두 파일에 한 벌씩 두면 한쪽만 고쳐도 예외가 나지 않고 `summary.json` 의 키만 조용히 갈린다
KEY_EXCLUDED_COUNT: Final = "excluded_count"
