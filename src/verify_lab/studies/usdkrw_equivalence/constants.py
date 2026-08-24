"""검증 #5 의 대상·합격선·표시 레이블

합격선은 **사양서 §16.2·§16.3 이 사전 등록한 값**이며 결과를 보고 조정하지 않는다.
이상치 날짜는 G0 실측으로 확인된 것이고 근거는 `docs/spec/usdkrw_grid.md` §3.3 에 있다.
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Final

from verify_lab.common_constants import MARKET_DIR, SERIES_DIR

# ============================================================
# 입력 파일
# ============================================================

# 매매기준율의 **고시 시차**. 고시일 D 의 값은 D−1 의 은행간 거래를 반영하므로,
# 시장일 기준으로 쓰려면 고시일을 한 칸 앞으로 당겨야 한다.
#
# **실측으로 확정한 값이다** (`docs/spec/usdkrw_grid.md` §3.4). 보정하지 않으면 261240 일간수익률과의
# 상관이 −0.03 으로 무의미해지고, 보정하면 0.88 로 올라온다. 시차를 모른 채 계산하면
# 예외도 나지 않고 결과만 틀린다
SPOT_PUBLICATION_LAG_ROWS: Final = 1


@dataclass(frozen=True)
class SpotSource:
    """현물 환율 계열 하나

    **어느 계열을 쓰느냐로 결론이 갈린다.** 매매기준율은 「전영업일 은행간 거래의 가중평균」이라
    하루 늦고 스무딩돼 있어, 261240 이 아무리 잘 복제해도 사양서 §16.2 의 상관·추적오차 합격선을
    통과할 수 없다. 종가 15:30 은 시차가 없고 사양서 §6.6 의 판정 시각과도 맞는다.

    Attributes:
        key: 실행 인자로 고르는 이름
        label: 표시 이름
        path: 시계열 파일
        needs_publication_shift: 고시일을 시장일로 옮겨야 하는지 여부
    """

    key: str
    label: str
    path: Path
    needs_publication_shift: bool


SPOT_MARKET_RATE: Final = SpotSource(
    key="market_rate",
    label="매매기준율",
    path=SERIES_DIR / "USDKRW.csv",
    needs_publication_shift=True,
)

SPOT_CLOSE: Final = SpotSource(
    key="close",
    label="종가 15:30",
    path=SERIES_DIR / "USDKRW_CLOSE.csv",
    needs_publication_shift=False,
)

SPOT_SOURCES: Final = (SPOT_CLOSE, SPOT_MARKET_RATE)

# 원화 단기금리 (CD 91일물)
KRW_RATE_PATH: Final = SERIES_DIR / "CD91.csv"

# 달러 단기금리 (미국 3개월 T-bill)
USD_RATE_PATH: Final = SERIES_DIR / "DTB3.csv"


@dataclass(frozen=True)
class EtfTarget:
    """검증 대상 ETF 하나

    Attributes:
        key: 실행 인자로 고르는 이름
        ticker: 종목 코드
        label: 표시 이름
        price_path: 수정 종가 파일. 사양서 §11.3 이 본검증 기준으로 지정한 것이다
        raw_price_path: 원본가 파일. **NAV 대비 프리미엄은 이쪽으로만 잴 수 있다** —
            수정 종가는 분배금만큼 과거가 낮아져 있어 원본 기준인 NAV 와 비교하면
            그 조정폭이 통째로 디스카운트로 잡힌다
        nav_path: NAV 시계열 파일
        exposure: 노출 배수. 실효 비용을 재려면 **구조를 반영한 기준선**이 필요하다 —
            2배 상품은 2배 노출을 1배 담보로 굴리므로 원화 이자를 1배만 받는다
        published_ter: 공시 총보수 (비율, 0.0025 = 연 0.25%). **측정값의 교차확인용**이며
            판정 기준이 아니다
    """

    key: str
    ticker: str
    label: str
    price_path: Path
    raw_price_path: Path
    nav_path: Path
    exposure: int
    published_ter: float


ETF_BASE: Final = EtfTarget(
    key="261240",
    ticker="261240",
    label="KODEX 미국달러선물",
    price_path=MARKET_DIR / "261240_adjusted_max.csv",
    raw_price_path=MARKET_DIR / "261240_max.csv",
    nav_path=SERIES_DIR / "261240_NAV.csv",
    exposure=1,
    published_ter=0.0025,
)

ETF_LEVERAGE: Final = EtfTarget(
    key="261250",
    ticker="261250",
    label="KODEX 미국달러선물레버리지",
    price_path=MARKET_DIR / "261250_adjusted_max.csv",
    raw_price_path=MARKET_DIR / "261250_max.csv",
    nav_path=SERIES_DIR / "261250_NAV.csv",
    exposure=2,
    published_ter=0.0045,
)

ETF_TARGETS: Final = (ETF_BASE, ETF_LEVERAGE)


class TheoreticalModel(Enum):
    """이론값 구성 방식

    **사양서 안에서 두 식이 갈린다.** 하나를 고르면 알파가 통째로 달라지므로 둘 다 산출하고
    어느 쪽이 실제와 맞는지를 측정으로 답한다.

    Attributes:
        CARRY: 현물 + (달러금리 − 원화금리). 사양서 §16.1 의 H₀
        USD_RATE: 현물 + 달러금리. 사양서 §2.1 의 커버드 금리평형에서 나오는 값
    """

    CARRY = "carry"
    USD_RATE = "usd_rate"


# ============================================================
# 이상치
# ============================================================

# 261240 의 종가가 NAV 대비 +21.85% 튄 날과 되돌아온 다음 날.
# **NAV 는 정상이고 종가만 튀었다**(`docs/spec/usdkrw_grid.md` §3.3).
# 포함/제외 두 벌을 모두 산출하며, 어느 쪽을 본 판정으로 쓸지는 결과를 보고 정한다
OUTLIER_DATES: Final = (date(2019, 3, 14), date(2019, 3, 15))


# ============================================================
# 합격선 — 사양서 §16.2 (261240 vs 이론값)
# ============================================================

CORRELATION_MIN: Final = 0.97
BETA_MIN: Final = 0.98
BETA_MAX: Final = 1.02

# 잔차 표준편차의 연환산. 비율(0.015 = 1.5%)
TRACKING_ERROR_MAX: Final = 0.015

# 연도별 (실제 − 이론) 의 최대-최소 폭. 비율(0.003 = 0.3%p)
ANNUAL_DRIFT_SPREAD_MAX: Final = 0.003

# 알파의 참고 기준. **총보수 확정값이 아니다** — 사양서 §16.2 가 "총보수 근방(−0.25% 내외)"
# 이라고만 적었고 실제 총보수는 아직 확인되지 않았다. 결과 문서에 그 사실을 함께 적는다
ALPHA_REFERENCE: Final = -0.0025


# ============================================================
# 합격선 — 사양서 §16.3 (261250 vs 261240)
# ============================================================

LEVERAGE_BETA_MIN: Final = 1.95
LEVERAGE_BETA_MAX: Final = 2.00
LEVERAGE_ALPHA_MIN: Final = -0.010
LEVERAGE_ALPHA_MAX: Final = -0.005
LEVERAGE_R_SQUARED_MIN: Final = 0.99


# ============================================================
# 연율화
# ============================================================

# 알파와 추적오차의 연환산 계수 (거래일). 사양서 §16.2·§16.3 이 250 을 쓴다
TRADING_DAYS_PER_YEAR: Final = 250

# 이자 일할 계산의 분모 (달력일). `docs/spec/usdkrw_grid.md` §4.3 결정 C14
DAYS_PER_YEAR: Final = 365

# 금리 시계열의 단위는 연 백분율이다. 비율로 바꿀 때 나눈다
RATE_PERCENT_TO_RATIO: Final = 100


# ============================================================
# 정렬 결과의 컬럼 (내부 계산용 영문 토큰)
# ============================================================

COL_ETF_CLOSE: Final = "EtfClose"
COL_NAV: Final = "Nav"
COL_SPOT: Final = "Spot"
COL_USD_RATE: Final = "UsdRate"
COL_KRW_RATE: Final = "KrwRate"

# 직전 거래일과의 **달력일** 차이. 주말과 휴장을 건너뛴 이자를 일할로 계산하려면 필요하다
COL_DAY_COUNT: Final = "DayCount"


# ============================================================
# 수익률 계산 결과의 컬럼
# ============================================================

# ETF 의 실제 일간수익률 (수정 종가 기준)
COL_ACTUAL_RETURN: Final = "ActualReturn"

# 원달러 매매기준율의 일간 변화율
COL_SPOT_RETURN: Final = "SpotReturn"

# 이자 기여분. 연 금리 × 달력일 ÷ 365
COL_RATE_CONTRIBUTION: Final = "RateContribution"

# 이론 일간수익률. 현물 변화와 이자를 곱으로 결합한 값
COL_THEORETICAL_RETURN: Final = "TheoreticalReturn"


# ============================================================
# 연도별 괴리 표의 컬럼
# ============================================================

COL_YEAR: Final = "Year"
COL_TRADING_DAYS: Final = "TradingDays"
COL_ACTUAL_CUMULATIVE: Final = "ActualCumulative"
COL_THEORETICAL_CUMULATIVE: Final = "TheoreticalCumulative"
COL_DRIFT: Final = "Drift"


# ============================================================
# 프리미엄/디스카운트 표의 컬럼
# ============================================================

COL_PREMIUM_MEAN: Final = "PremiumMean"
COL_PREMIUM_ABS_MEAN: Final = "PremiumAbsMean"
COL_PREMIUM_MAX: Final = "PremiumMax"
COL_PREMIUM_MIN: Final = "PremiumMin"


# ============================================================
# 정렬 집계의 키
# ============================================================

KEY_SPOT_MISSING: Final = "spot_missing"
KEY_KRW_RATE_MISSING: Final = "krw_rate_missing"
KEY_USD_RATE_MISSING: Final = "usd_rate_missing"
KEY_USD_RATE_CARRIED: Final = "usd_rate_carried"


# ============================================================
# 표시용 레이블
# ============================================================

DISPLAY_TICKER: Final = "종목"
DISPLAY_SPOT: Final = "환율 계열"
DISPLAY_MODEL: Final = "이론값"
DISPLAY_OUTLIER: Final = "이상치"
DISPLAY_SAMPLE_COUNT: Final = "표본"
DISPLAY_CORRELATION: Final = "상관"
DISPLAY_BETA: Final = "베타"
DISPLAY_ALPHA_ANNUAL: Final = "알파 연환산(%)"
DISPLAY_R_SQUARED: Final = "R2"
DISPLAY_TRACKING_ERROR: Final = "추적오차(%)"
DISPLAY_YEAR: Final = "연도"
DISPLAY_ACTUAL_RETURN: Final = "실제(%)"
DISPLAY_THEORETICAL_RETURN: Final = "이론(%)"
DISPLAY_DRIFT: Final = "괴리(%p)"
DISPLAY_DRIFT_SPREAD: Final = "연도별 괴리 폭(%p)"
DISPLAY_PREMIUM_MEAN: Final = "프리미엄 평균(%)"
DISPLAY_PREMIUM_ABS_MEAN: Final = "프리미엄 절대값 평균(%)"
DISPLAY_PREMIUM_MAX: Final = "프리미엄 최대(%)"
DISPLAY_PREMIUM_MIN: Final = "프리미엄 최소(%)"
DISPLAY_PASS: Final = "합격"
DISPLAY_EXPOSURE: Final = "노출"
DISPLAY_EFFECTIVE_COST: Final = "실효 총비용(%)"
DISPLAY_PUBLISHED_TER: Final = "공시 총보수(%)"
DISPLAY_TER_GAP: Final = "차이(%p)"
DISPLAY_TRADING_DAYS: Final = "거래일"
DISPLAY_DATE: Final = "날짜"
DISPLAY_ACTUAL_DAILY: Final = "실제 일간(%)"
DISPLAY_SPOT_DAILY: Final = "현물 일간(%)"
DISPLAY_RATE_DAILY: Final = "이자 일간(%)"
DISPLAY_THEORETICAL_DAILY: Final = "이론 일간(%)"

# 일간 원자료의 백분율 자릿수. **집계표(2자리)와 다르다** — 일간 이자 기여분이 0.0x% 수준이라
# 2자리로 저장하면 그 컬럼이 전부 `0.00` 이 되어 사용자가 손으로 검산할 수 없다
DAILY_PERCENT_DECIMALS: Final = 4

# 이론값·이상치 축의 표시 이름
MODEL_LABELS: Final = {
    TheoreticalModel.CARRY: "현물+금리차",
    TheoreticalModel.USD_RATE: "현물+달러금리",
}

OUTLIER_LABEL_INCLUDED: Final = "포함"
OUTLIER_LABEL_EXCLUDED: Final = "제외"

# 합격 여부 표기. 값이 아니라 판정이므로 기호로 둔다
PASS_MARK: Final = "O"
FAIL_MARK: Final = "X"

# 상관·베타·R2 는 배수라 백분율이 아니다. 소수 넷째 자리까지 본다
RATIO_DECIMALS: Final = 4

# 결과 폴더 이름 뒤에 붙는 검증명
STUDY_NAME: Final = "usdkrw_equivalence"
