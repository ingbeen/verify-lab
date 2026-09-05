"""검증 #9 의 측정 대상·격자·규칙 상수

**선물에는 «배수»가 없다.** 레버리지 ETF 의 2배는 매일 리밸런싱으로 유지되는 값이지만,
선물은 증거금 대비 노출이 가격이 움직이면 저절로 변한다. 그래서 이 검증에서는
**리밸런싱 규칙이 곧 배수의 정의**이고, 규칙을 상수로 고정하지 않으면 비교가 성립하지 않는다.

**노브를 만들지 않는다.** 배수·격자·리밸런싱 주기·롤 규칙은 전부 여기서 고정하고 CLI 인자로
열지 않는다. 열면 결과를 보고 고르게 되며 그것은 측정이 아니라 과최적화다 (측정의 원칙 1).

제외 사유와 구간 컬럼은 `measure/constants.py` 를, 공통 출력 라벨은 `report/constants.py` 를
재사용한다. 같은 뜻의 상수를 검증마다 새로 만들면 두 곳이 조용히 갈라진다.
"""

from dataclasses import dataclass
from datetime import date
from typing import Final

from verify_lab.common_constants import COL_DATE
from verify_lab.data.krx_futures_collector import PRODUCT_KOSDAQ150, PRODUCT_KOSPI200
from verify_lab.measure.constants import COL_EXCLUDED_REASON, COL_HORIZON, COL_JUDGEABLE

# 표시 레이블은 공통 계층이 소유한다 — 검증마다 다른 말을 쓰면 두 결과를 나란히 읽을 수 없다
from verify_lab.report.constants import DISPLAY_HORIZON, DISPLAY_JUDGEABLE, DISPLAY_SAMPLE_COUNT

__all__ = ["DISPLAY_JUDGEABLE"]

# ============================================================
# 측정 대상
# ============================================================


@dataclass(frozen=True)
class FuturesPair:
    """선물로 만든 포지션과 그것에 대응하는 레버리지 상품의 짝.

    Attributes:
        index_name: 기초가 되는 지수 이름 (표시용)
        product_id: 선물 상품 코드
        base_ticker: 1배 상품의 티커. 롤·베이시스 비용의 기준선이다
        target_ticker: 짝이 되는 배수 상품의 티커
        multiple: 목표 배수 (인버스는 음수)
        product_type: 짝의 상품 종류 (`ETF` / `ETN`)
        base_index: 배수 상품이 추종하는 기초지수. **현물과 선물이 갈린다** —
            선물지수 기반이면 ETF 안에도 롤 비용이 들어 있어 분해의 잔여에 섞인다
    """

    index_name: str
    product_id: str
    base_ticker: str
    target_ticker: str
    multiple: float
    product_type: str
    base_index: str


PRODUCT_ETF: Final = "ETF"
PRODUCT_ETN: Final = "ETN"

# 대조할 짝 전부. 종목·기초지수는 검증 #8 이 KRX 전수 조회로 확정한 것을 그대로 쓴다
# (`docs/spec/leverage_tracking.md` §3.1). 두 검증을 나란히 읽으려면 대상이 같아야 한다.
#
# **인버스 넷은 ETF 자신이 선물지수를 추종한다.** 그래서 「선물 대 ETF」 비교가 인버스에서는
# 「직접 굴리는 선물 대 포장된 선물」이 되고, 롤 비용이 양쪽에 있어 잔여로 분리되지 않는다.
# 레버리지 둘(122630·233740)만 현물지수를 추종해 깨끗하게 갈린다.
#
# **±3배는 대상에 없다.** 국내 법정 상한이 ±2배라 대조할 ETF 가 존재하지 않는다.
# 선물로는 만들 수 있지만 **이 검증은 「선물과 ETF 중 어느 쪽이 싼가」를 묻는 대조**라,
# 짝이 없는 배수는 답할 질문이 없다.
PAIRS: Final = (
    FuturesPair("KOSPI200", PRODUCT_KOSPI200, "069500", "122630", 2.0, PRODUCT_ETF, "코스피 200"),
    FuturesPair("KOSPI200", PRODUCT_KOSPI200, "069500", "114800", -1.0, PRODUCT_ETF, "코스피 200 선물지수"),
    FuturesPair("KOSPI200", PRODUCT_KOSPI200, "069500", "252670", -2.0, PRODUCT_ETF, "코스피 200 선물지수"),
    FuturesPair("KOSDAQ150", PRODUCT_KOSDAQ150, "229200", "233740", 2.0, PRODUCT_ETF, "코스닥 150"),
    FuturesPair("KOSDAQ150", PRODUCT_KOSDAQ150, "229200", "251340", -1.0, PRODUCT_ETF, "F-코스닥150 지수"),
    FuturesPair("KOSDAQ150", PRODUCT_KOSDAQ150, "229200", "530107", -2.0, PRODUCT_ETN, "코스닥 150 선물 TWAP 인버스 -2X 지수"),
)

# ============================================================
# 계약 명세
# ============================================================

# 거래승수 이력. **만료 계약의 승수를 주는 조회가 없어 거래대금으로 역산해 확정했다** —
# `승수 = 거래대금 ÷ (거래량 × 평균체결가)` 이고 평균체결가가 저가~고가 사이이므로
# 하루치로 구간이 나온다. 승수가 제도값이라 구간이 후보 하나만 품으면 그날 값이 확정된다.
# 코스피200 은 7,599일이 확정되고 3일만 애매했다. 근거는 `docs/spec/futures_leverage.md`.
#
# **소수 계약 본선에는 들어가지 않는다.** 정수 계약 대조에만 쓰인다
CONTRACT_MULTIPLIER_HISTORY: Final = {
    PRODUCT_KOSPI200: (
        (date(1996, 5, 3), 500_000),
        (date(2017, 3, 27), 250_000),
    ),
    PRODUCT_KOSDAQ150: ((date(2015, 11, 23), 10_000),),
}

# ============================================================
# 보유 기간 격자
# ============================================================

# 보유 기간 (거래일). **검증 #8 과 같은 값을 쓴다** — 두 검증을 나란히 읽으려면
# 격자가 같아야 한다. 1주·2주·1개월·3개월·6개월·1년·3년
HOLDING_HORIZONS: Final = (5, 10, 21, 63, 126, 252, 756)

# ============================================================
# 롤 규칙
# ============================================================

# 미결제약정 역전 규칙. 차월물 미결제약정이 근월물을 넘어선 것을 **확인한 다음 거래일**에 롤한다.
#
# **판정일 종가에 롤하지 않는다.** KRX 미결제약정은 장 마감 후 확정·공표되므로
# 그 시점에는 알 수 없는 정보다 (`src/verify_lab/CLAUDE.md` 측정 계층의 절대 원칙 1)
ROLL_RULE_OPEN_INTEREST: Final = "미결제약정 역전"

# 만기 N거래일 전 고정 규칙. 달력만으로 미리 정해지므로 미래 참조 문제가 없다
ROLL_RULE_DAYS_BEFORE_EXPIRY: Final = "만기 전 고정"
ROLL_DAYS_BEFORE_EXPIRY: Final = 5

# 두 규칙을 나란히 낸다. 하나를 고르지 않는다 (측정의 원칙 1)
ROLL_RULES: Final = (ROLL_RULE_OPEN_INTEREST, ROLL_RULE_DAYS_BEFORE_EXPIRY)

# ============================================================
# 리밸런싱과 자기자본
# ============================================================

# 매일 리밸런싱. ETF 와 경로가 같아 **비용만의 차이**를 보여준다
REBALANCE_DAILY: Final = "매일"

# 월 1회 리밸런싱. **진입일에 목표 배수로 잡고 그 뒤 `REBALANCE_INTERVAL_DAYS` 거래일마다** 맞춘다
REBALANCE_MONTHLY: Final = "월 1회"

# 그대로 두기. **진입일에 목표 배수로 잡고 그 뒤로는 손대지 않는다.**
#
# 사용자가 실제로 하는 것이 이것이다 — «1억을 넣고 계약 수를 그대로 두는 것».
# 매일·월 1회와 달리 **배수가 유지되지 않는다**: 오르면 평가익이 자기자본에 쌓여 배수가
# 내려가고(상승을 덜 먹는다), 내리면 자기자본이 줄어 배수가 올라간다(하락을 더 먹는다).
#
# **진입일 리밸런싱은 남긴다.** 목표 배수로 시작해야 항상 정확히 배수로 시작하는 ETF 와
# 출발선이 같아진다. 그것까지 없애면 비교 전제(같은 자기자본·같은 목표 배수)가 무너진다
REBALANCE_NONE: Final = "그대로"

REBALANCE_RULES: Final = (REBALANCE_DAILY, REBALANCE_MONTHLY, REBALANCE_NONE)

# 월 1회 리밸런싱의 간격 (거래일). 보유 기간 격자의 「1개월」과 같은 값을 쓴다.
#
# **달력(매월 첫 거래일)이 아니라 진입일에 맞춘다** (2026-09-04 확정).
# 달력에 맞추면 리밸런싱 시점이 진입일이 아니라 월중 위치에 묶여, **짧은 칸에서 「진입일이
# 월중 어디냐」가 숨은 축으로 들어온다** — 5거래일 구간은 진입일에 따라 리밸런싱이 0회가
# 되기도 1회가 되기도 해서 「월 1회」가 어떤 칸에서는 「무리밸런싱」이 된다.
# 진입일에 맞추면 구간 길이만으로 횟수가 정해져(5일→0회, 252일→12회) 달력 축이 사라진다.
#
# **대가**: 사람이 실제로 하는 「매월 1일」과는 다르다. 이 검증이 재는 것은
# 「월 1회 리밸런싱이 얼마를 치르는가」이지 「월중 언제 시작해야 하는가」가 아니므로
# 달력 축을 두지 않는다. 결과 문서에 이 사실을 적는다
REBALANCE_INTERVAL_DAYS: Final = 21

# 비교 방식 셋. 이 이름이 산출물의 「방식」 컬럼 값이 된다
METHOD_ETF: Final = "레버리지 ETF"
METHOD_FUTURES_DAILY: Final = "선물 매일"
METHOD_FUTURES_MONTHLY: Final = "선물 월 1회"
METHOD_FUTURES_HOLD: Final = "선물 그대로"

# 리밸런싱 규칙과 그 규칙으로 굴린 방식의 짝. 두 곳에서 따로 분기하면 조용히 갈라진다
METHOD_BY_REBALANCE: Final = {
    REBALANCE_DAILY: METHOD_FUTURES_DAILY,
    REBALANCE_MONTHLY: METHOD_FUTURES_MONTHLY,
    REBALANCE_NONE: METHOD_FUTURES_HOLD,
}

# **비교의 기준선은 「선물 매일·이자 없음」 하나로 고정한다.** 셋을 한 항등식에 넣으면
# 좌변의 「선물」이 무엇인지 정해지지 않아 분해가 성립하지 않는다
BASELINE_METHOD: Final = METHOD_FUTURES_DAILY

# 여유현금 이자 가정. **증권사가 예탁금 이용료를 주는지가 갈리므로 두 벌을 나란히 낸다.**
# 한쪽만 내면 그 가정이 결과를 만든다. 실행 계층이 이 순서대로 순회한다
INTEREST_ASSUMPTIONS: Final = (True, False)

# 이자율로 쓰는 시계열. `storage/series/CD91.csv` 로 이미 확보돼 있다
INTEREST_SERIES_NAME: Final = "CD91"

# 소수 계약 본선의 초기 자기자본 (원). **결과에 영향을 주지 않는다** —
# 자기자본은 `E × (1 + 배수 × 일간수익률)` 로 닫혀 비율만 남기 때문이다.
# 값이 필요한 것은 곡선을 원 단위로 보여주기 위해서다
INITIAL_EQUITY: Final = 100_000_000

# 정수 계약 대조용 자기자본 규모 (원). **여기서는 이 값이 결과를 만든다** —
# 계약 하나를 살 수 있는지가 규모에 달렸기 때문이다.
# "얼마부터 선물이 실용적인가"를 부수적으로 보여준다
INTEGER_CONTRACT_EQUITIES: Final = (10_000_000, 50_000_000, 100_000_000, 500_000_000)

# 자기자본이 0 이하가 된 구간의 수익률. **비우지 않고 이 값으로 남긴다.**
#
# 강제청산되면 자기자본이 전액 사라지므로 그 구간의 성적은 −100% 다. 비워두면 살아남은
# 구간만 평균에 들어가 **생존편향**이 생긴다 — 그대로 두기 축에서 소진이 대량 발생하며
# (−2배 1년 326건), 제외하면 망한 구간이 결과에서 통째로 사라진다.
#
# **구간이 데이터를 넘어가 못 잰 시작일과 구분한다.** 그쪽은 «성적이 없는» 것이라 NaN 이고,
# 이쪽은 «−100% 라는 성적» 이다. 둘을 섞으면 손실을 지어내거나 감추게 된다
WIPEOUT_RETURN: Final = -1.0

# ============================================================
# 정수 계약 제약
# ============================================================

# 계약 하나도 못 사는 규모에서 남기는 사유. **0 으로 채우지 않는다** —
# 0 은 「손실도 이익도 없었다」로 읽히지만 실제로는 «그 규모에서는 할 수 없다» 는 뜻이다
REASON_NOT_EXECUTABLE: Final = "집행 불가"

# ============================================================
# 시기 축
# ============================================================

# 저금리와 고금리를 가르는 해. **검증 #8 과 같은 경계를 쓴다** (시작일 기준)
HIGH_RATE_START_YEAR: Final = 2022

DISPLAY_PERIOD_LOW_RATE: Final = "저금리(~2021)"
DISPLAY_PERIOD_HIGH_RATE: Final = "고금리(2022~)"

# ============================================================
# 출력 라벨 (CSV 헤더·화면 표시용)
# ============================================================

DISPLAY_INDEX_NAME: Final = "지수"
DISPLAY_BASE_TICKER: Final = "1배 종목"
DISPLAY_TARGET_TICKER: Final = "짝 종목"
DISPLAY_MULTIPLE: Final = "배수"
DISPLAY_METHOD: Final = "방식"
DISPLAY_ROLL_RULE: Final = "롤 규칙"
DISPLAY_INTEREST: Final = "이자 가정"

DISPLAY_NEAR_CONTRACT: Final = "근월물"
DISPLAY_NEXT_CONTRACT: Final = "차월물"
DISPLAY_DECISION_DATE: Final = "판정일"
DISPLAY_EXECUTION_DATE: Final = "집행일"
DISPLAY_ADJUSTMENT_FACTOR: Final = "조정계수"
DISPLAY_NEAR_OPEN_INTEREST: Final = "근월물 미결제약정"
DISPLAY_NEXT_OPEN_INTEREST: Final = "차월물 미결제약정"

DISPLAY_RETURN: Final = "수익률(%)"
# **「비용」이라고 쓰지 않는다.** 이 값은 백워데이션에서 양수(롤 수익)가 되고 콘탱고에서
# 음수(롤 비용)가 된다 — 이름이 부호를 정해 버리면 양수일 때 「비용이 양수」라는 말이 된다.
# `docs/.claude/rules/docs.md` 가 「초과분」을 「차이」로 바꾼 것과 같은 이유다
DISPLAY_ROLL_COST: Final = "롤·베이시스 몫(%p)"
DISPLAY_REBALANCE_ERROR: Final = "리밸런싱 오차(%p)"
DISPLAY_INTEREST_GAIN: Final = "여유현금 이자(%p)"
DISPLAY_RESIDUAL: Final = "잔여(%p)"
# 「그대로 두기」가 매일 리밸런싱과 벌어진 몫. 리밸런싱 오차와 같은 기준선을 쓴다
DISPLAY_HOLD_ERROR: Final = "그대로 두기 오차(%p)"
DISPLAY_DIVIDEND_ADJUSTMENT: Final = "배당 보정분(%p)"

DISPLAY_EXPOSURE: Final = "노출(원)"
DISPLAY_WIPEOUT_DATE: Final = "자기자본 소진일"

DISPLAY_BREAKEVEN_HORIZON: Final = "선물이 앞서는 최소 보유 기간"

DISPLAY_EQUITY_SIZE: Final = "자기자본 규모(원)"
DISPLAY_TARGET_MULTIPLE: Final = "목표 배수"
DISPLAY_ACTUAL_MULTIPLE: Final = "실제 배수"
DISPLAY_INTEGER_CONTRACTS: Final = "정수 계약 수"
DISPLAY_CONTRACT_NOTIONAL: Final = "1계약 명목(원)"
DISPLAY_EXECUTABLE: Final = "집행가능"

# 구간의 시작·끝. **날짜가 아니라 「어느 구간을 쟀는가」를 가리킨다**
DISPLAY_START_DATE: Final = "시작일"
DISPLAY_END_DATE: Final = "종료일"

# 롤링 전수는 이웃끼리 겹치므로 표본 수만 적으면 실제보다 단단해 보인다
DISPLAY_NON_OVERLAPPING: Final = "비중첩 표본"

# ============================================================
# 산출물 파일명
# ============================================================

COMPARISON_FILENAME: Final = "comparison.csv"
DECOMPOSITION_FILENAME: Final = "decomposition.csv"
ROLL_EVENTS_FILENAME: Final = "roll_events.csv"
BREAKEVEN_FILENAME: Final = "breakeven.csv"
WIPEOUTS_FILENAME: Final = "wipeouts.csv"
LEVERAGE_DRIFT_FILENAME: Final = "leverage_drift.csv"
INTEGER_CONTRACTS_FILENAME: Final = "integer_contracts.csv"

# 결과 폴더 이름에 쓰는 검증 이름
STUDY_NAME: Final = "futures_leverage"


# ============================================================
# 산출물 컬럼 (내부 계산용 영문 토큰)
# ============================================================

# 식별 축
COL_INDEX_NAME: Final = "IndexName"
COL_TARGET_TICKER: Final = "TargetTicker"
COL_MULTIPLE: Final = "Multiple"
COL_METHOD: Final = "Method"
COL_ROLL_RULE: Final = "RollRule"
COL_INTEREST: Final = "Interest"
COL_PERIOD: Final = "Period"

# 구간 집계
COL_SAMPLE_COUNT: Final = "SampleCount"
COL_NON_OVERLAPPING: Final = "NonOverlapping"
COL_MEAN_RETURN: Final = "MeanReturn"
COL_MEDIAN_RETURN: Final = "MedianReturn"
COL_START_DATE: Final = "StartDate"
COL_END_DATE: Final = "EndDate"

# 차이 분해. 앞 네 항은 독립 산식이고 잔여만 남는다 (`comparison.decompose`)
COL_ROLL_COST: Final = "RollCost"
COL_REBALANCE_ERROR: Final = "RebalanceError"
COL_HOLD_ERROR: Final = "HoldError"
COL_INTEREST_GAIN: Final = "InterestGain"
COL_RESIDUAL: Final = "Residual"
COL_FUTURES_MINUS_ETF: Final = "FuturesMinusEtf"
COL_HOLD_MINUS_ETF: Final = "HoldMinusEtf"
COL_DIVIDEND_ADJUSTMENT: Final = "DividendAdjustment"

# 롤 이벤트 원자료 (`continuous.roll_events_frame`).
# **판정일과 집행일을 따로 남긴다** — 둘이 같으면 미래를 참조한 것이다
COL_DECISION_DATE: Final = "DecisionDate"
COL_EXECUTION_DATE: Final = "ExecutionDate"
COL_FROM_CONTRACT: Final = "FromContract"
COL_FROM_NAME: Final = "FromName"
COL_TO_CONTRACT: Final = "ToContract"
COL_TO_NAME: Final = "ToName"
COL_ADJUSTMENT_FACTOR: Final = "AdjustmentFactor"
COL_FROM_OPEN_INTEREST: Final = "FromOpenInterest"
COL_TO_OPEN_INTEREST: Final = "ToOpenInterest"
COL_FALLBACK: Final = "Fallback"

# 자기자본 소진
COL_WIPEOUT_COUNT: Final = "WipeoutCount"
COL_WINDOW_COUNT: Final = "WindowCount"
COL_FIRST_WIPEOUT_DATE: Final = "FirstWipeoutDate"

# 최대 유효 레버리지. 매일 리밸런싱은 목표 배수 그대로이고 월 1회는 월중에 표류한다
COL_MAX_LEVERAGE_DAILY: Final = "MaxEffectiveLeverageDaily"
COL_MAX_LEVERAGE_MONTHLY: Final = "MaxEffectiveLeverageMonthly"

# 선물이 앞서기 시작하는 보유 기간
COL_BREAKEVEN_HORIZON: Final = "BreakevenHorizon"
COL_AHEAD_HORIZON_COUNT: Final = "AheadHorizonCount"
COL_TESTED_HORIZON_COUNT: Final = "TestedHorizonCount"

# 정수 계약 대조
COL_AS_OF_DATE: Final = "AsOfDate"
COL_PRICE: Final = "Price"
COL_CONTRACT_MULTIPLIER: Final = "ContractMultiplier"
COL_NOTIONAL: Final = "Notional"
COL_EQUITY_SIZE: Final = "EquitySize"
COL_INTEGER_CONTRACTS: Final = "IntegerContracts"
COL_ACTUAL_MULTIPLE: Final = "ActualMultiple"
COL_EXECUTABLE: Final = "Executable"


# ============================================================
# 산출물 레이블
# ============================================================

DISPLAY_MEAN_RETURN: Final = "평균 수익률(%)"
DISPLAY_MEDIAN_RETURN: Final = "중앙 수익률(%)"
DISPLAY_FUTURES_MINUS_ETF: Final = "선물 − ETF(%p)"
DISPLAY_HOLD_MINUS_ETF: Final = "선물 그대로 − ETF(%p)"
DISPLAY_FROM_NAME: Final = "근월물 이름"
DISPLAY_TO_NAME: Final = "차월물 이름"

# **규칙이 정한 날에 롤하지 못한 경우다.** 미결제약정이 끝내 역전되지 않아 만기로 밀린 것과,
# 두 계약이 겹치는 날이 모자라 앞당겨진 것 둘 다 여기 걸린다 —
# 「만기가 강제한」이라고 적으면 뒤쪽이 거짓이 된다
DISPLAY_FALLBACK: Final = "규칙대로 못 한 롤"

DISPLAY_AHEAD_HORIZON_COUNT: Final = "선물이 앞선 보유 기간 수"

# **「잰 시작일 수」와 다른 것을 센다.** 이쪽은 보유 기간 격자의 칸 수이고 그쪽은 시작일 수다 —
# 같은 이름을 쓰면 두 표를 나란히 읽을 때 어느 축인지 알 수 없다
DISPLAY_TESTED_HORIZON_COUNT: Final = "잰 보유 기간 수"
DISPLAY_MAX_LEVERAGE_DAILY: Final = "매일 리밸런싱 최대 유효 레버리지"
DISPLAY_MAX_LEVERAGE_MONTHLY: Final = "월 1회 최대 유효 레버리지"
DISPLAY_WIPEOUT_COUNT: Final = "자기자본 소진 구간 수"
DISPLAY_WINDOW_COUNT: Final = "잰 시작일 수"
DISPLAY_PERIOD: Final = "시기"
DISPLAY_EXCLUDED_REASON: Final = "제외 사유"
DISPLAY_AS_OF_DATE: Final = "기준일"
DISPLAY_PRICE: Final = "정산가"
DISPLAY_CONTRACT_MULTIPLIER: Final = "거래승수"

# 산출물 CSV 의 컬럼 한글 이름 (`src/verify_lab/CLAUDE.md` 「내부/출력 분리」).
# **전 산출물을 한 사전으로 덮는다** — 표마다 사전을 두면 같은 컬럼에 다른 이름이 붙는다.
# 표마다 컬럼 구성이 다르므로 호출 측이 그 표에 실제로 있는 것만 골라 넘긴다
OUTPUT_LABELS: Final = {
    # 식별 축
    COL_INDEX_NAME: DISPLAY_INDEX_NAME,
    COL_TARGET_TICKER: DISPLAY_TARGET_TICKER,
    COL_MULTIPLE: DISPLAY_MULTIPLE,
    COL_METHOD: DISPLAY_METHOD,
    COL_ROLL_RULE: DISPLAY_ROLL_RULE,
    COL_INTEREST: DISPLAY_INTEREST,
    COL_PERIOD: DISPLAY_PERIOD,
    COL_HORIZON: DISPLAY_HORIZON,
    COL_DATE: DISPLAY_START_DATE,
    # 구간 집계
    COL_START_DATE: DISPLAY_START_DATE,
    COL_END_DATE: DISPLAY_END_DATE,
    COL_SAMPLE_COUNT: DISPLAY_SAMPLE_COUNT,
    COL_NON_OVERLAPPING: DISPLAY_NON_OVERLAPPING,
    COL_MEAN_RETURN: DISPLAY_MEAN_RETURN,
    COL_MEDIAN_RETURN: DISPLAY_MEDIAN_RETURN,
    COL_JUDGEABLE: DISPLAY_JUDGEABLE,
    # 차이 분해
    COL_ROLL_COST: DISPLAY_ROLL_COST,
    COL_REBALANCE_ERROR: DISPLAY_REBALANCE_ERROR,
    COL_HOLD_ERROR: DISPLAY_HOLD_ERROR,
    COL_INTEREST_GAIN: DISPLAY_INTEREST_GAIN,
    COL_RESIDUAL: DISPLAY_RESIDUAL,
    COL_FUTURES_MINUS_ETF: DISPLAY_FUTURES_MINUS_ETF,
    COL_HOLD_MINUS_ETF: DISPLAY_HOLD_MINUS_ETF,
    COL_DIVIDEND_ADJUSTMENT: DISPLAY_DIVIDEND_ADJUSTMENT,
    # 롤 이벤트
    COL_DECISION_DATE: DISPLAY_DECISION_DATE,
    COL_EXECUTION_DATE: DISPLAY_EXECUTION_DATE,
    COL_FROM_CONTRACT: DISPLAY_NEAR_CONTRACT,
    COL_FROM_NAME: DISPLAY_FROM_NAME,
    COL_TO_CONTRACT: DISPLAY_NEXT_CONTRACT,
    COL_TO_NAME: DISPLAY_TO_NAME,
    COL_ADJUSTMENT_FACTOR: DISPLAY_ADJUSTMENT_FACTOR,
    COL_FROM_OPEN_INTEREST: DISPLAY_NEAR_OPEN_INTEREST,
    COL_TO_OPEN_INTEREST: DISPLAY_NEXT_OPEN_INTEREST,
    COL_FALLBACK: DISPLAY_FALLBACK,
    # 선물이 앞서는 지점
    COL_BREAKEVEN_HORIZON: DISPLAY_BREAKEVEN_HORIZON,
    COL_AHEAD_HORIZON_COUNT: DISPLAY_AHEAD_HORIZON_COUNT,
    COL_TESTED_HORIZON_COUNT: DISPLAY_TESTED_HORIZON_COUNT,
    # 최대 유효 레버리지와 소진
    COL_MAX_LEVERAGE_DAILY: DISPLAY_MAX_LEVERAGE_DAILY,
    COL_MAX_LEVERAGE_MONTHLY: DISPLAY_MAX_LEVERAGE_MONTHLY,
    COL_WIPEOUT_COUNT: DISPLAY_WIPEOUT_COUNT,
    COL_WINDOW_COUNT: DISPLAY_WINDOW_COUNT,
    COL_FIRST_WIPEOUT_DATE: DISPLAY_WIPEOUT_DATE,
    # 시작일 원자료 — 방식 이름이 그대로 컬럼이 된다
    METHOD_ETF: f"{METHOD_ETF}(%)",
    METHOD_FUTURES_DAILY: f"{METHOD_FUTURES_DAILY}(%)",
    METHOD_FUTURES_MONTHLY: f"{METHOD_FUTURES_MONTHLY}(%)",
    METHOD_FUTURES_HOLD: f"{METHOD_FUTURES_HOLD}(%)",
    COL_EXCLUDED_REASON: DISPLAY_EXCLUDED_REASON,
    # 정수 계약 대조. **여기서는 배수가 「목표」다** — 규모 때문에 실제 배수가 달라지는 것이 요점이다
    COL_AS_OF_DATE: DISPLAY_AS_OF_DATE,
    COL_PRICE: DISPLAY_PRICE,
    COL_CONTRACT_MULTIPLIER: DISPLAY_CONTRACT_MULTIPLIER,
    COL_NOTIONAL: DISPLAY_CONTRACT_NOTIONAL,
    COL_EQUITY_SIZE: DISPLAY_EQUITY_SIZE,
    COL_INTEGER_CONTRACTS: DISPLAY_INTEGER_CONTRACTS,
    COL_ACTUAL_MULTIPLE: DISPLAY_ACTUAL_MULTIPLE,
    COL_EXECUTABLE: DISPLAY_EXECUTABLE,
}

# 비율(0~1)로 계산해 백분율로 내보낼 컬럼. 헤더에 `(%)`·`(%p)` 가 붙는 것과 짝을 이룬다
PERCENT_OUTPUT_COLUMNS: Final = (
    COL_MEAN_RETURN,
    COL_MEDIAN_RETURN,
    COL_ROLL_COST,
    COL_REBALANCE_ERROR,
    COL_HOLD_ERROR,
    COL_INTEREST_GAIN,
    COL_RESIDUAL,
    COL_FUTURES_MINUS_ETF,
    COL_HOLD_MINUS_ETF,
    COL_DIVIDEND_ADJUSTMENT,
    METHOD_ETF,
    METHOD_FUTURES_DAILY,
    METHOD_FUTURES_MONTHLY,
    METHOD_FUTURES_HOLD,
)
