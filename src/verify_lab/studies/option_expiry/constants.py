"""검증 #7(옵션 만기일) 이벤트 정의와 실행이 공유하는 상수

파라미터 값은 `docs/매매/옵션_만기일/설계.md` 가 확정한 것이며, **성과를 보며 돌리는 노브가 아니다.**
여러 값을 나란히 산출해 보고하기 위한 목록이므로 하나를 골라 두지 않는다.

표시용 한글 레이블도 여기 둔다. `report` 는 어떤 검증이 자기를 쓰는지 몰라야 하므로
검증별 컬럼 이름을 알 수 없고, 그 이름을 정하는 것은 이 검증의 몫이다.
"""

from dataclasses import dataclass
from typing import Final

from verify_lab.common_constants import COL_CLOSE, COL_DATE, MARKET_FILE_TEMPLATE, PRICE_DECIMALS
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
from verify_lab.measure.screening import COL_DIRECTION
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
    DISPLAY_BASELINE_SAMPLE,
    DISPLAY_BASIS,
    DISPLAY_DATE,
    DISPLAY_DIRECTION,
    DISPLAY_DOWN_RATE,
    DISPLAY_DOWN_RATE_DIFF,
    DISPLAY_DOWN_RATE_P_VALUE,
    DISPLAY_DOWN_RATE_PERCENTILE,
    DISPLAY_EXCLUDED,
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
    DISPLAY_UP_RATE_PERCENTILE,
    MEASURE_FILENAME,
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

# 달력 기준 청산의 목표 요일. **축이 아니라 확정 규칙이다** — 「만기일 매수 → 다음 주 금요일
# 매도」가 이 매매의 정의이고, 값 하나를 확정하는 자리는 `docs/매매/옵션_만기일/규칙.md` §1 이다.
#
# **한국은 만기가 목요일이라 같은 「다음 주 금요일」이 미국 5거래일 · 한국 6거래일**이 된다.
# 그 차이를 축으로 두어 목요일 청산을 대조로 함께 내던 것을 그만뒀다 — 요일에 따라 판정이
# 갈리는 칸이 5개였고 방향이 제각각이라, **좋은 쪽을 고르면 그 선택이 결론에 숨는다.**
# 버린 쪽의 실측 성적은 `docs/매매/옵션_만기일/설계.md` 결정 ⑳ 에 탈락안으로 남아 있다
EXIT_WEEKDAY: Final = FRIDAY


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

# 보유 구간에 들어간 배당락. 산식은 `measure/distribution.py` 의 `dividend_impact` 가 소유한다
COL_DIVIDEND_MEASURED: Final = "dividend_measured"
COL_DIVIDEND_HIT_COUNT: Final = "dividend_hit"
COL_DIVIDEND_MEAN_IMPACT: Final = "dividend_mean_impact"


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
    """

    key: str
    ticker: str
    label: str
    rule: ExpiryRule
    file_name: str
    price_decimals: int


# **실제로 거는 두 종목뿐이다** (2026-09-21 사용자 확정).
#
# 전에는 QQQ·KODEX 200·KODEX 코스닥150 을 함께 돌려 대상 5 × 만기월 12 × 방향 2 = 120칸을
# 냈다. 셋을 뺀 근거는 서로 다르고 **전부 `docs/매매/옵션_만기일/규칙.md` §3 에 있다** —
# QQQ 는 배당락이 보유 구간에 들어와 측정값이 오염되고(8/26건 · 회당 +0.049%p 과대),
# 국내 둘은 이 매매법의 발단인 **네마녀의날**이 미국 달력이라 대상에서 빠졌다.
#
# [중요] **되돌리려면 이 목록에 다시 넣으면 된다.** 제외 근거와 실측 수치가 규칙 문서에
# 남아 있으므로 판단 재료가 사라지지 않는다 — 다만 QQQ 를 넣으면 **그 배당락 왜곡을
# 함께 안는 것**이고, 그 크기는 `측정.csv` 의 배당락 두 컬럼이 매 실행 알려 준다
DATASETS: Final = (
    Dataset(
        key="spy",
        ticker="SPY",
        label="SPY",
        rule=US_MONTHLY_EXPIRY,
        file_name=MARKET_FILE_TEMPLATE.format(ticker="SPY"),
        price_decimals=PRICE_DECIMALS,
    ),
    Dataset(
        # 미국 세 번째 대표 지수. SPY 와 독립 표본이 아니다 — 9월 아래 두 칸은 **28건 내내
        # 부호가 갈린 적이 없고 상관이 0.965** 다. 두 칸을 거는 것은 두 번의 확인이 아니라
        # 같은 포지션을 두 번 사는 것이며, 투자금 결정이 그 사실을 본다 (규칙.md §1.1)
        key="dia",
        ticker="DIA",
        label="DIA",
        rule=US_MONTHLY_EXPIRY,
        file_name=MARKET_FILE_TEMPLATE.format(ticker="DIA"),
        price_decimals=PRICE_DECIMALS,
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

# 보유 구간에 들어간 배당락. **`.claude/rules/trading.md` 가 「확정 전 필수 항목」으로
# 요구하는데 그 값이 어느 산출물에도 없어서** 칸을 뺄지 판단할 때마다 스크립트를 따로
# 돌려야 했다. 산식은 `measure/distribution.py` 의 `dividend_impact` 하나가 소유한다.
#
# [중요] **대조 건수를 함께 낸다.** 「걸린 건수 0」과 「수정주가가 없어 못 쟀다」는 다른
# 사실이고, 그 구별이 없으면 없는 안전을 보고한다 — 역방향이 실제로 신호 19건을
# 못 잰 채 0건으로 셌다
DISPLAY_DIVIDEND_MEASURED: Final = "배당락 대조 건수"
DISPLAY_DIVIDEND_HIT_COUNT: Final = "배당락 걸린 건수"
DISPLAY_DIVIDEND_MEAN_IMPACT: Final = "배당락 평균 왜곡(%p)"
DISPLAY_MONTH_DAY_INDEX: Final = "월중 서수"
DISPLAY_DAILY_RETURN: Final = "일간 등락률(%)"
DISPLAY_CLOSE: Final = "종가"

# 만기일 매수 → 다음주 청산 매매의 진입 수. **`report` 의 「신호」와 뜻이 같지만 말이 다르다** —
# 이 매매는 만기일이 곧 진입일이라 화면에서 「진입」으로 읽는 것이 자연스럽다
DISPLAY_ENTRY_COUNT: Final = "진입"

# 요일 번호를 표에 적을 때 쓰는 이름. **만기일이 무슨 요일에 떨어지는지**를 세는 자리가 쓴다
# (`runner.py` 의 만기일 요일 분포) — 휴장 앞당김 때문에 만기가 늘 같은 요일인 것이 아니다
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
    COL_EXPIRY_MONTH_NUMBER: DISPLAY_EXPIRY_MONTH,
    COL_DIRECTION: DISPLAY_DIRECTION,
    COL_EXPIRY_MONTH: DISPLAY_EXPIRY_YEAR_MONTH,
    COL_JUDGEABLE: DISPLAY_JUDGEABLE,
    # 만기일 달력
    COL_RULE_DATE: DISPLAY_RULE_DATE,
    COL_EXPIRY_DATE: DISPLAY_EXPIRY_DATE,
    COL_ADVANCED_DAYS: DISPLAY_ADVANCED_DAYS,
    # 만기 창 신호일 원자료
    COL_DATE: DISPLAY_DATE,
    COL_CLOSE: DISPLAY_CLOSE,
    COL_DAILY_RETURN: DISPLAY_DAILY_RETURN,
    COL_OFFSET: DISPLAY_OFFSET,
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
    # 보유 구간에 들어간 배당락
    COL_DIVIDEND_MEASURED: DISPLAY_DIVIDEND_MEASURED,
    COL_DIVIDEND_HIT_COUNT: DISPLAY_DIVIDEND_HIT_COUNT,
    COL_DIVIDEND_MEAN_IMPACT: DISPLAY_DIVIDEND_MEAN_IMPACT,
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
# **측정 산출물은 한 장뿐이다** (2026-09-21). 체결 둘(`성적표.csv`·`거래내역.csv`)은
# `execution/constants.py` 가 소유하므로 여기 없고, 폴더에 생기는 CSV 는 합쳐서 셋이다.
#
# 여덟 장이던 것을 한 장으로 줄였고 **사라진 일곱의 사정이 서로 다르다.**
#
# | 없앤 표 | 왜 |
# | --- | --- |
# | `signals.csv`(29,572행)·`expiries.csv` | **상대 거래일 ±10 격자는 결론이 난 축**이다 — 결과 문서가 「우위 없음」으로 닫았다 |
# | `weekly_trade_signals.csv` | 체결 원자료는 `거래내역.csv` 가 담는다 |
# | `weekly_trade_summary/excess/permutation.csv` | **보유 거래일 축**이라 판정에 쓰이지 않았다 |
# | `weekly_trade_by_month_halves.csv` | 성적표의 시기 5행이 같은 질문에 더 고른 표본으로 답한다 |
#
# **남길 값은 `측정.csv` 가 담는다** — 중앙값(측정의 원칙 4) · 평균-비율 어긋남(원칙 13) ·
# 기준선 · 우연확률 · 배당락. 그 넷은 성적표에 없어서 **이 표가 유일한 자리**다.
# 되살리는 절차는 `docs/매매/옵션_만기일/결과.md` 에 있다
OUTPUT_FILES: Final[dict[str, str]] = {
    # 사용자가 보는 이름은 `report/constants.py` 가 소유한다 — 이름이 갈리면 계약으로 고정할 수 없다
    "measure": MEASURE_FILENAME,
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
# **성적이 가장 좋아서 고른 값이 아니다.** 격자 실측에서 무손절이 어느 손절선보다도 나으며
# (후보 24칸 회당 0.878% 대 -5% 의 0.746%), 손절의 값은 수익이 아니라 **최악 통제**에 있다.
#
# 고른 근거는 셋이다. 후보 24칸(손절 없는 성적으로 게이트를 통과한 칸) 체결 612건 기준이다.
#   - **최악 평탄면 안이다** — -1.0% ~ -5.5% 구간의 최악이 -7.98% 로 평평하다. 그 값은
#     QQQ 8월 위 2015-08-21 갭이라 그보다 좁은 손절선은 전부 그 갭에 뚫린다
#   - **이길 때(+2.093%)의 2.39배**로 2~3배 안이다
#   - **발동률 5.6%** (34건) 로 25번에 한 번만 쓴다
#
# **손절선은 평균 손실이 아니라 드물게 쓰는 상한이다.** 지는 날의 실제 평균 손실은 손절선을
# -3% 로 좁히든 -8% 로 넓히든 -2.0 ~ -2.1% 로 거의 같고, 「실제 손실 / 이길 때」가 전 구간
# 0.98 ~ 1.02배다 — 손절선을 넓혀도 손익비가 망가지지 않는다.
#
# **역방향 매매의 「갭손절 0건의 첫 지점」 논리는 여기서 못 쓴다** — 보유가 5~6거래일이라
# 갭손절 건수가 손절선에 대해 단조롭지 않다.
# 근거 격자와 탈락안은 `docs/매매/옵션_만기일/규칙.md` 3.1 이 SoT다
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


# **실제로 거는 세 칸이다** (2026-09-21 사용자 확정).
#
# [중요] **전에는 코드가 격자를 전부 냈고, 그 방침을 사용자가 뒤집었다.** 대상 5 × 만기월 12 ×
# 방향 2 = 120칸을 내던 이유는 「코드가 칸을 고르면 사후 선택과 구별되지 않는다」였는데,
# **사용자가 실제로 걸 것만 남기기로 정했다** — 산출물이 12,000행이라 열어도 읽히지 않았고,
# 안 거는 117칸의 성적이 판단을 돕지 않았다.
#
# **그 대신 두 가지를 지킨다.**
#   - **왜 이 칸인가는 `docs/매매/옵션_만기일/규칙.md` §3 이 「확정 / 탈락안 / 근거」로 갖는다.**
#     코드는 그 결론을 옮겨 적을 뿐이고, 목록만 보고 근거를 짐작하면 안 된다
#   - **손절선 격자 20종은 그대로 둔다** — `.claude/rules/trading.md` 가 요구하는 대조축이며,
#     「값 하나를 확정하는 것」과 「격자를 전부 내는 것」의 경계는 여기서도 그대로다
#
# **시세를 다시 받으면 이 목록이 따라오지 않는다.** 그것이 격자를 내던 이유였고 지금도 사실이다 —
# 재수집 뒤에는 성적표를 보고 이 목록을 다시 판단해야 한다
TRADING_CELLS: Final = (
    ExpiryCell(dataset_key="spy", expiry_month=9, bet_down=True),
    ExpiryCell(dataset_key="dia", expiry_month=9, bet_down=True),
    ExpiryCell(dataset_key="dia", expiry_month=12, bet_down=False),
)


def trading_cells(datasets: tuple[Dataset, ...] | None = None) -> tuple[ExpiryCell, ...]:
    """확정 칸 중 그 대상에 해당하는 것만 낸다.

    **청산 요일은 축이 아니다.** 전 대상이 `EXIT_WEEKDAY`(금요일) 하나를 쓴다 — 확정 규칙이라
    고를 것이 없고, 그래서 칸에도 산출물에도 그 컬럼이 없다.

    Args:
        datasets: 대상 목록. **인자를 아예 주지 않으면** `DATASETS` 전부.
            빈 튜플은 **거부한다** — 「전부」와 「고른 결과가 없다」는 다른 사실이고,
            조용히 전부로 넓히면 대상을 좁히려던 실행이 **전 범위 산출물로 폴더를 덮는다**

    Returns:
        `TRADING_CELLS` 의 순서를 그대로 지킨 칸 목록.
        **순서가 결정적이어야** 산출물 diff 가 「숫자가 바뀌었는가」를 말해 준다

    Raises:
        ValueError: 빈 대상 목록을 넘겼거나, 고른 대상에 확정 칸이 하나도 없는 경우
    """
    if datasets is not None and not datasets:
        raise ValueError("고른 종목에 해당하는 칸이 없습니다")

    targets = DATASETS if datasets is None else datasets
    keys = {dataset.key for dataset in targets}
    cells = tuple(cell for cell in TRADING_CELLS if cell.dataset_key in keys)

    # **빈 결과를 조용히 돌려주지 않는다.** 그대로 두면 산출물이 0행으로 나오고
    # 폴더는 이미 비워진 뒤라, 좁혀 돌린 실행이 **전체 산출물을 지우기만 한다**
    if not cells:
        raise ValueError(f"고른 종목에 확정 칸이 없습니다 - 종목: {sorted(keys)}")

    return cells


# **만기월과 청산 목표일의 레이블은 위 측정 절에 이미 있다.** 측정과 체결이 같은 이름을
# 쓰는 것이 의도이며, 두 벌을 두면 한쪽만 고쳐도 예외가 나지 않고 두 표의 헤더만 갈린다


# ============================================================
# 실행 요약 키
# ============================================================

# 청산일을 확정하지 못해 빠진 진입 수. **측정과 매매가 같은 것을 세므로 한 곳에서 정의한다** —
# 두 파일에 한 벌씩 두면 한쪽만 고쳐도 예외가 나지 않고 `summary.json` 의 키만 조용히 갈린다
KEY_EXCLUDED_COUNT: Final = "excluded_count"

# 이번 실행이 어느 칸을 잰 것인가. **측정과 체결이 같은 목록을 받으므로 키도 하나다** —
# 두 파일에 한 벌씩 두면 `summary.json` 의 `measure` 와 `trade` 가 다른 이름으로 같은 것을 적는다
KEY_CELLS: Final = "cells"

# 그 목록의 한 줄이 담는 것. 측정과 체결이 같은 칸을 적으므로 이름도 한 벌이다
KEY_LABEL: Final = "label"
KEY_EXPIRY_MONTH: Final = "expiry_month"
KEY_DIRECTION: Final = "direction"
