"""검증 #7(옵션 만기일) 이벤트 정의와 실행이 공유하는 상수

파라미터 값은 `docs/spec/option_expiry.md` 가 확정한 것이며, **성과를 보며 돌리는 노브가 아니다.**
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
    COL_SIGNAL_COUNT,
)
from verify_lab.measure.screening import (
    COL_BASELINE_GAP,
    COL_BASELINE_HIT_RATE,
    COL_DIRECTION,
    COL_EXPECTED_VALUE,
    COL_HIT_RATE,
    COL_P_VALUE,
    COL_PERIOD_COUNT,
    COL_PERIOD_MIN_HIT_RATE,
    COL_SCREEN,
    COL_SUPPORT_COUNT,
    COL_SUPPORT_TOTAL,
    COL_TOTAL_RETURN,
    COL_UNMET_SUPPORT,
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
    COL_NULL_MEAN_P05,
    COL_NULL_MEAN_P95,
    COL_OBSERVED_DOWN_RATE,
    COL_OBSERVED_MEAN,
    COL_OBSERVED_MEDIAN,
    COL_OBSERVED_UP_RATE,
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
    DISPLAY_HORIZON,
    DISPLAY_JUDGEABLE,
    DISPLAY_MAX,
    DISPLAY_MEAN,
    DISPLAY_MEAN_DIFF,
    DISPLAY_MEAN_P_VALUE,
    DISPLAY_MEAN_PERCENTILE,
    DISPLAY_MEDIAN,
    DISPLAY_MEDIAN_DIFF,
    DISPLAY_MEDIAN_P_VALUE,
    DISPLAY_MEDIAN_PERCENTILE,
    DISPLAY_MIN,
    DISPLAY_NULL_P05,
    DISPLAY_NULL_P95,
    DISPLAY_OBSERVED_DOWN_RATE,
    DISPLAY_OBSERVED_MEAN,
    DISPLAY_OBSERVED_MEDIAN,
    DISPLAY_OBSERVED_UP_RATE,
    DISPLAY_P_VALUE,
    DISPLAY_PERIOD_COUNT,
    DISPLAY_PERIOD_MIN_HIT_RATE,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_SCREEN,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_SIGNAL_SAMPLE,
    DISPLAY_STD,
    DISPLAY_TEST_NOTE,
    DISPLAY_TOTAL_RETURN,
    DISPLAY_UNMET_SUPPORT,
    DISPLAY_UP_RATE,
    DISPLAY_UP_RATE_DIFF,
    DISPLAY_UP_RATE_P_VALUE,
    DISPLAY_UP_RATE_PERCENTILE,
)


@dataclass(frozen=True)
class ExpiryRule:
    """월물 만기일을 정하는 달력 규칙

    만기일은 시세와 무관한 **달력 규칙**이다. 규칙일이 휴장이면 직전 거래일까지 앞당겨지며,
    그 판정에 필요한 거래일 목록은 시세 파일의 날짜 인덱스에서 온다
    (`docs/spec/option_expiry.md` 결정 ⑤).

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
# (`docs/spec/option_expiry.md` 결정 ⑰)
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
# (`docs/spec/option_expiry.md` §3.7)
COL_BASELINE_KIND: Final = "baseline"

# 같은 달 기준선 통계에 붙는 접미사. `_aggregate_by_month` 의 merge suffix 와 **같은 값이어야**
# 산출물 컬럼과 한글 사전이 어긋나지 않는다
BASELINE_SUFFIX: Final = "_baseline"

# 만기월을 1~12 정수로 놓는 축. `COL_EXPIRY_MONTH` 는 "YYYY-MM" 문자열이라 12칸으로 묶이지 않는다
COL_EXPIRY_MONTH_NUMBER: Final = "expiry_month_number"

# 평균의 부호와 방향 비율이 어긋나는 칸인지 (루트 `CLAUDE.md` 측정의 원칙 13).
# 평균이 양수인데 절반 넘게 내렸다면 소수의 큰 사건이 평균을 만든 것이라, 평균만 보면 그 칸을 놓친다
COL_MEAN_RATE_CONFLICT: Final = "mean_rate_conflict"

# 어긋남 판정의 경계 (비율, 0.5 = 50%). "절반을 넘었는가" 하나만 본다 —
# 경계를 파라미터로 열면 결과를 보고 조정하게 된다
HALF_RATE: Final = 0.5

# 시기 분할 축. 신호를 **시간순으로 세어 균등하게** 가른다 — 시장 구조가 바뀐 시점으로 나누는
# 달력 경계 방식은 칸마다 표본이 들쭉날쭉해 쓰지 않는다(`docs/spec/option_expiry.md` 결정 ㉖).
# 후보 판정의 시기 항목은 **칸당 표본 하한**을 지켜야 하므로 이 축으로 잰다
COL_TIME_HALF: Final = "time_half"
DISPLAY_TIME_HALF_EARLY: Final = "앞 절반"
DISPLAY_TIME_HALF_LATE: Final = "뒤 절반"

# 묶음 집계에서 쓰는 구간 표지. 보유 거래일 수를 구간 축에 넣으면 **한 매매가 여러 칸으로 쪼개져**
# 묶음 값이 나오지 않는다. 실제 보유일수로는 도달할 수 없는 음수를 써서 진짜 구간과 섞이지 않게 한다
# (`docs/spec/option_expiry.md` 결정 ㉑)
HORIZON_NEXT_WEEK_EXIT: Final = -1


# ============================================================
# 검증 대상 시세
# ============================================================


@dataclass(frozen=True)
class Dataset:
    """검증 대상 종목 하나

    **가격 기준은 원본가 하나다.** 사용자가 증권앱·차트에서 보는 가격이 곧 신호를 판정하고
    주문을 거는 가격이기 때문이며, 두 기준을 나란히 내면 결과를 보고 고를 여지가 생긴다
    (루트 `CLAUDE.md` 측정의 원칙 14).

    Attributes:
        key: 실행 인자로 고르는 이름
        ticker: 종목 표시 이름
        rule: 그 시장의 월물 만기 규칙
        file_name: `storage/market/` 안의 원본가 파일 이름
        price_decimals: 종가를 저장할 때의 반올림 자릿수
        exit_weekdays: 달력 기준 청산의 목표 요일. 첫 번째가 본검증이고 나머지는 대조다.
            **한국만 두 벌**인 이유는 만기가 목요일이라 같은 "다음주 금요일"이
            미국 5거래일 · 한국 6거래일이 되기 때문이다 (`docs/spec/option_expiry.md` 결정 ⑳)
    """

    key: str
    ticker: str
    rule: ExpiryRule
    file_name: str
    price_decimals: int
    exit_weekdays: tuple[int, ...]


DATASETS: Final = (
    Dataset(
        key="qqq",
        ticker="QQQ",
        rule=US_MONTHLY_EXPIRY,
        file_name=MARKET_FILE_TEMPLATE.format(ticker="QQQ"),
        price_decimals=PRICE_DECIMALS,
        exit_weekdays=(FRIDAY,),
    ),
    Dataset(
        key="spy",
        ticker="SPY",
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
        ticker="KODEX 200",
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
DISPLAY_MEAN_RATE_CONFLICT: Final = "평균-비율 어긋남"
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

# 결과 폴더 이름 뒤에 붙는 검증명
STUDY_NAME: Final = "option_expiry"

# 만기월 축과 구별되는 이름. `COL_EXPIRY_MONTH` 는 "2026-08" 같은 연월 문자열이고
# `COL_EXPIRY_MONTH_NUMBER` 는 1~12 다. 둘 다 "만기월"로 적으면 어느 축인지 알 수 없다
DISPLAY_EXPIRY_YEAR_MONTH: Final = "만기 연월"

DISPLAY_TIME_HALF: Final = "시기"
DISPLAY_BASELINE_KIND: Final = "기준선 종류"
DISPLAY_WEEK_REFERENCE: Final = "주 기준일"
DISPLAY_TARGET_DATE: Final = "청산 목표일"
DISPLAY_EXIT_DATE: Final = "실제 청산일"
DISPLAY_HOLD_DAYS: Final = "보유 거래일"
DISPLAY_ENTRY_CLOSE: Final = "진입 종가"
DISPLAY_EXIT_CLOSE: Final = "청산 종가"
DISPLAY_FORWARD_RETURN: Final = "수익률(%)"
DISPLAY_EXCLUDED_REASON: Final = "제외 사유"
DISPLAY_SUPPORT_COUNT: Final = "뒷받침 충족"
DISPLAY_SUPPORT_TOTAL: Final = "뒷받침 물음"

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
    COL_TIME_HALF: DISPLAY_TIME_HALF,
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
    COL_HORIZON: DISPLAY_HORIZON,
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
    COL_P_VALUE: DISPLAY_P_VALUE,
    COL_PERIOD_COUNT: DISPLAY_PERIOD_COUNT,
    COL_PERIOD_MIN_HIT_RATE: DISPLAY_PERIOD_MIN_HIT_RATE,
    COL_SCREEN: DISPLAY_SCREEN,
    COL_SUPPORT_COUNT: DISPLAY_SUPPORT_COUNT,
    COL_SUPPORT_TOTAL: DISPLAY_SUPPORT_TOTAL,
    COL_UNMET_SUPPORT: DISPLAY_UNMET_SUPPORT,
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
    *(
        f"{column}{BASELINE_SUFFIX}"
        for column in (COL_MEAN, COL_MEDIAN, COL_WIN_RATE, COL_LOSS_RATE, COL_MAX, COL_MIN, COL_STD)
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
    COL_PERIOD_MIN_HIT_RATE,
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
    COL_P_VALUE,
)
