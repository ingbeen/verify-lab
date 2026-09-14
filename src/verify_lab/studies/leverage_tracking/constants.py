"""검증 #8 의 측정 대상과 결과 스키마

**측정 대상은 「1배 상품과 배수 상품의 짝」이다.** 배수는 상품이 약속한 명목 배수이며
실제로 그렇게 움직였는지가 이 검증의 질문이다.

제외 사유와 구간 컬럼은 `measure/constants.py` 를 재사용한다. 같은 뜻의 상수를 검증마다
새로 만들면 두 곳이 조용히 갈라진다.
"""

from dataclasses import dataclass
from typing import Final

from verify_lab.common_constants import RATE_TO_PERCENT

# **판정가능은 공통 계층이 소유한다** — 측정의 원칙 17 이 모든 검증에 요구하는 개념이라
# 검증마다 새로 만들면 같은 원칙이 다른 답을 낸다. **여기서 다시 내보내지도 않는다** —
# 옛 경로가 살아 있으면 소유자가 바뀌어도 그 경로로 들어오는 코드와 테스트가 그대로 통과해
# 이동이 실제로 일어났는지 확인할 방법이 없다. 쓰는 쪽이 `measure`·`report` 에서 직접 가져온다

# ============================================================
# 측정 대상
# ============================================================


@dataclass(frozen=True)
class LeveragePair:
    """1배 상품과 배수 상품의 짝.

    Attributes:
        index_name: 기초가 되는 지수 이름 (표시용)
        base_ticker: 1배 상품의 티커
        target_ticker: 배수 상품의 티커
        multiple: 상품이 약속한 명목 배수 (인버스는 음수)
        product_type: 상품 종류 (`ETF` / `ETN`). ETN 은 신용위험·만기·지표가치가 달라
            같은 표에 담되 구분해서 읽어야 한다
        base_index: 배수 상품이 추종하는 기초지수 이름. **현물과 선물이 갈린다** —
            선물지수 기반이면 롤오버·베이시스가 괴리에 섞여 들어온다
        note: 이 짝을 왜 넣었는지에 대한 단서. 본선이면 빈 문자열
    """

    index_name: str
    base_ticker: str
    target_ticker: str
    multiple: float
    product_type: str
    base_index: str
    note: str = ""


PRODUCT_ETF: Final = "ETF"
PRODUCT_ETN: Final = "ETN"

# 측정 대상 전부. 종목·상장일·거래대금·기초지수는 2026-09-02 기준 KRX 전수 조회와
# yfinance 조회로 확정했다. 근거는 `docs/spec/레버리지_ETF_괴리_설계.md` 에 있다.
#
# **국내 인버스는 전부 선물지수를 추종한다** — 레버리지만 현물지수다.
# **코스닥150 −2배는 ETF 가 없어 ETN 을 쓴다.** 국내 법정 상한이 ±2배라 −3배는 존재하지 않는다.
PAIRS: Final = (
    # 국내 — KOSPI200. 레버리지만 현물지수이고 인버스 둘은 선물지수를 추종한다
    LeveragePair("KOSPI200", "069500", "122630", 2.0, PRODUCT_ETF, "코스피 200"),
    LeveragePair("KOSPI200", "069500", "114800", -1.0, PRODUCT_ETF, "코스피 200 선물지수"),
    LeveragePair("KOSPI200", "069500", "252670", -2.0, PRODUCT_ETF, "코스피 200 선물지수"),
    # 국내 — KOSDAQ150. −2배는 ETF 가 없어 ETN 을 쓰며, 같은 날 상장한 두 발행사를
    # 나란히 둬 «발행사가 달라서 생기는 차이»를 분리한다
    LeveragePair("KOSDAQ150", "229200", "233740", 2.0, PRODUCT_ETF, "코스닥 150"),
    LeveragePair("KOSDAQ150", "229200", "251340", -1.0, PRODUCT_ETF, "F-코스닥150 지수"),
    LeveragePair("KOSDAQ150", "229200", "530107", -2.0, PRODUCT_ETN, "코스닥 150 선물 TWAP 인버스 -2X 지수", "삼성 (거래대금 1위)"),
    LeveragePair("KOSDAQ150", "229200", "520057", -2.0, PRODUCT_ETN, "코스닥 150 선물 TWAP 인버스 -2X 지수", "미래에셋 (대조)"),
    # 미국 — S&P500
    LeveragePair("S&P500", "SPY", "SSO", 2.0, PRODUCT_ETF, "S&P 500"),
    LeveragePair("S&P500", "SPY", "UPRO", 3.0, PRODUCT_ETF, "S&P 500"),
    LeveragePair("S&P500", "SPY", "SH", -1.0, PRODUCT_ETF, "S&P 500"),
    LeveragePair("S&P500", "SPY", "SDS", -2.0, PRODUCT_ETF, "S&P 500"),
    LeveragePair("S&P500", "SPY", "SPXU", -3.0, PRODUCT_ETF, "S&P 500"),
    # 미국 — 나스닥100
    LeveragePair("나스닥100", "QQQ", "QLD", 2.0, PRODUCT_ETF, "나스닥 100"),
    LeveragePair("나스닥100", "QQQ", "TQQQ", 3.0, PRODUCT_ETF, "나스닥 100"),
    LeveragePair("나스닥100", "QQQ", "PSQ", -1.0, PRODUCT_ETF, "나스닥 100"),
    LeveragePair("나스닥100", "QQQ", "QID", -2.0, PRODUCT_ETF, "나스닥 100"),
    LeveragePair("나스닥100", "QQQ", "SQQQ", -3.0, PRODUCT_ETF, "나스닥 100"),
    # 미국 — 다우. DDM 은 거래대금이 다른 칸의 1/20 수준이라 유동성을 함께 읽어야 한다
    LeveragePair("다우", "DIA", "DDM", 2.0, PRODUCT_ETF, "다우존스 산업평균"),
    LeveragePair("다우", "DIA", "UDOW", 3.0, PRODUCT_ETF, "다우존스 산업평균"),
    LeveragePair("다우", "DIA", "DOG", -1.0, PRODUCT_ETF, "다우존스 산업평균"),
    LeveragePair("다우", "DIA", "DXD", -2.0, PRODUCT_ETF, "다우존스 산업평균"),
    LeveragePair("다우", "DIA", "SDOW", -3.0, PRODUCT_ETF, "다우존스 산업평균"),
)

# ============================================================
# 보유 기간
# ============================================================

# 측정 구간 (거래일). 사용자가 재려는 구간이며 성과를 보며 돌리는 노브가 아니라 상수다.
# 3년(756)이 상한인 이유는 그보다 길면 독립 표본이 한 자릿수 초반으로 떨어지기 때문이다.
# 상장 후 전체 구간은 표본 1건이라 통계가 아니므로 이 격자에 넣지 않고 따로 낸다
HORIZONS: Final = (5, 10, 21, 63, 126, 252, 756)

# 화면·CSV 에 쓰는 구간 이름. 거래일 수를 그대로 보여주면 사람이 매번 환산해야 한다
HORIZON_LABELS: Final = {
    5: "1주",
    10: "2주",
    21: "1개월",
    63: "3개월",
    126: "6개월",
    252: "1년",
    756: "3년",
}

# ============================================================
# 판정 임계값
# ============================================================

# 실현 배수를 낼 최소 1배 수익률 (비율, 0.01 = 1%). 분모가 0 근처면 실현 배수가 폭발해
# 평균이 무의미해진다. 이 값 미만인 구간은 실현 배수를 비우고 사유를 남긴다
MIN_BASE_RETURN_FOR_REALIZED_MULTIPLE: Final = 0.01

# 축을 쪼갤 때 칸당 요구하는 최소 유효 표본은 **공통 계층이 소유한다**
# (`measure/constants.py` 의 `MIN_SAMPLE_PER_CELL` — 루트 CLAUDE.md 측정의 원칙 12).
# 쓰는 쪽이 거기서 직접 가져온다

# ============================================================
# 결과 스키마 (내부 계산용 영문 토큰)
# ============================================================

# 짝지어 정렬한 종가
COL_BASE_CLOSE: Final = "BaseClose"
COL_TARGET_CLOSE: Final = "TargetClose"

# 구간 수익률과 괴리 3값
COL_BASE_RETURN: Final = "BaseReturn"
COL_NAIVE_EXPECTED: Final = "NaiveExpected"
COL_PATH_IDEAL: Final = "PathIdeal"
COL_ACTUAL: Final = "Actual"

# 괴리 분해. 두 항목의 합이 총 괴리와 같아야 한다 (분해 항등식)
COL_PATH_EFFECT: Final = "PathEffect"
COL_PRODUCT_COST: Final = "ProductCost"
COL_TOTAL_DIVERGENCE: Final = "TotalDivergence"

COL_REALIZED_MULTIPLE: Final = "RealizedMultiple"

# ============================================================
# 분해 축
# ============================================================

# 시작일의 위치 인덱스. 비중첩 표본 수를 세려면 «어느 구간끼리 겹치는가»를 알아야 하고,
# 그것은 날짜가 아니라 거래일 위치로만 정확히 판정된다
COL_START_POSITION: Final = "StartPosition"

COL_VOLATILITY_BUCKET: Final = "VolatilityBucket"
# 값까지 가른다. **이름만 바꾸면 충돌이 그대로다** — `measure/screening.py` 의
# `COL_DIRECTION` 도 `"Direction"` 이라, 이 프레임이 그쪽 헬퍼를 지나면 `오름`/`내림` 이
# 거는 방향으로 읽히고 **문자열이 나오므로 예외가 나지 않는다**
COL_TREND: Final = "Trend"
COL_BASE_RETURN_BUCKET: Final = "BaseReturnBucket"
COL_PERIOD: Final = "Period"

# **기초지수가 오른 날인가**를 나누는 축이다. **보합을 어느 쪽에도 넣지 않는다** —
# 여집합으로 만들면 비율이 부푼다 (`.claude/rules/docs.md` 의 오른 비율·내린 비율 규약과 같은 이유).
#
# [중요] **`DIRECTION_*` 이라 부르지 않는다.** `measure/screening.py` 가 같은 이름으로
# **신호를 어느 쪽으로 거는가**(`위`·`아래`, 측정의 원칙 11)를 갖고 있어 **같은 이름에 다른 값**이
# 두 곳에 있었다 — 잘못된 모듈에서 가져와도 문자열이 나오므로 **조용히 다른 축이 된다.**
# 통합할 수 없는 다른 개념이라 이름을 갈랐다
TREND_UP: Final = "오름"
TREND_DOWN: Final = "내림"
TREND_FLAT: Final = "보합"

# 변동성 사분위 라벨. 구간 «안»의 1배 일간 변동성으로 나눈다 —
# 경로 효과는 변동성의 함수이므로 이 축이 없으면 평균이 서로 다른 국면을 뭉갠다
VOLATILITY_BUCKETS: Final = ("변동성 하위 25%", "변동성 25~50%", "변동성 50~75%", "변동성 상위 25%")

# 1배 수익률 오분위 라벨. **방향 축이 부호만 보는 것을 크기로 보완한다** —
# 방향 축에서는 `+1%` 와 `+50%` 가 똑같이 「오름」이라, 경로 효과가 크기의 함수라는 사실이 보이지 않는다.
#
# **오분위를 쓴다(사분위가 아니다).** 실측에서 경로 효과의 **최저점이 20~40% 칸**에 있고
# 양끝은 양수 쪽이라 U자를 그리는데, 4칸으로 나누면 그 바닥이 「하위 50%」에 뭉개진다.
#
# **절대 경계(±5% 등)를 쓰지 않는다.** 보유 기간마다 같은 수익률의 뜻이 달라지고 임의
# 파라미터가 된다(측정의 원칙 1). 미국은 장기 상승이라 3년 구간에서 ±5% 안에 드는 표본이
# 3~5% 뿐이라 칸이 성립하지도 않는다. 근거는 `docs/spec/레버리지_ETF_괴리_설계.md`
BASE_RETURN_BUCKETS: Final = ("1배 하위 20%", "1배 20~40%", "1배 40~60%", "1배 60~80%", "1배 상위 20%")

# 시기 구분. 차입·스왑 비용이 금리에 연동되므로 금리 국면으로 자른다.
# 미국 기준금리 인상이 시작된 2022년을 경계로 삼는다
PERIOD_CUTOFF: Final = "2022-01-01"
PERIOD_LOW_RATE: Final = "저금리(~2021)"
PERIOD_HIGH_RATE: Final = "고금리(2022~)"

# ============================================================
# 집계 스키마
# ============================================================

COL_SAMPLE_COUNT: Final = "SampleCount"
COL_NON_OVERLAPPING_COUNT: Final = "NonOverlappingCount"

# ============================================================
# 표시용 한글 레이블 (CSV 헤더)
# ============================================================
#
# 공통 컬럼(날짜·구간·표본·제외)은 `report/constants.py` 의 `DISPLAY_*` 를 재사용한다.
# 여기 두는 것은 이 검증에만 있는 축이다.

DISPLAY_INDEX_NAME: Final = "지수"
DISPLAY_BASE_TICKER: Final = "1배 종목"
DISPLAY_TARGET_TICKER: Final = "배수 종목"
DISPLAY_MULTIPLE: Final = "배수"
DISPLAY_PRODUCT_TYPE: Final = "상품"
DISPLAY_BASE_INDEX: Final = "기초지수"

DISPLAY_BASE_RETURN: Final = "1배 수익률(%)"
DISPLAY_NAIVE_EXPECTED: Final = "단순 배수 기대치(%)"
DISPLAY_PATH_IDEAL: Final = "이론 경로(%)"
DISPLAY_ACTUAL: Final = "실제(%)"

# 괴리 항목의 단위는 백분율 포인트다 — 수익률끼리의 차이이기 때문이다
DISPLAY_PATH_EFFECT: Final = "경로 효과(%p)"
DISPLAY_PRODUCT_COST: Final = "상품 비용(%p)"
DISPLAY_TOTAL_DIVERGENCE: Final = "총 괴리(%p)"

DISPLAY_REALIZED_MULTIPLE: Final = "실현 배수"
DISPLAY_REALIZED_MULTIPLE_COUNT: Final = "실현 배수 표본"

# 롤링 전수는 이웃끼리 겹치므로 표본 수만 적으면 실제보다 단단해 보인다
DISPLAY_NON_OVERLAPPING: Final = "비중첩 표본"

DISPLAY_AXIS: Final = "축"
DISPLAY_AXIS_VALUE: Final = "구분"
DISPLAY_VOLATILITY_AXIS: Final = "변동성"
DISPLAY_DIRECTION_AXIS: Final = "방향"
DISPLAY_BASE_RETURN_AXIS: Final = "1배 수익률 분위"
DISPLAY_PERIOD_AXIS: Final = "시기"

DISPLAY_ANNUAL_DISTRIBUTION: Final = "연율 분배 기여(%)"

# 같은 항목을 1배와 배수 상품 각각에 대해 낸다. **두 열이 한 표에 나란히 오므로**
# 접두사를 붙여 구별한다 — 붙이는 자리를 실행 계층에 두면 그 문자열이 산출물 헤더가 된다
DISPLAY_BASE_ANNUAL_DISTRIBUTION: Final = f"1배 {DISPLAY_ANNUAL_DISTRIBUTION}"
DISPLAY_TARGET_ANNUAL_DISTRIBUTION: Final = f"배수 {DISPLAY_ANNUAL_DISTRIBUTION}"
DISPLAY_DIVIDEND_ADJUSTMENT: Final = "배당 보정분(%p)"
DISPLAY_DISTRIBUTION_MEASURED: Final = "측정 여부"
DISPLAY_DISTRIBUTION_PERIOD: Final = "분배 측정 구간"

DISPLAY_COMMON_DAYS: Final = "공통 거래일"
DISPLAY_BASE_ONLY: Final = "1배에만 있는 날"
DISPLAY_TARGET_ONLY: Final = "배수에만 있는 날"
DISPLAY_START_DATE: Final = "시작일"
DISPLAY_END_DATE: Final = "종료일"

# 분포의 양 끝. 평균만 보면 최악에 얼마나 벌어졌는지 알 수 없다
DISPLAY_TOTAL_DIVERGENCE_P05: Final = "총 괴리 하위5%(%p)"
DISPLAY_TOTAL_DIVERGENCE_P95: Final = "총 괴리 상위5%(%p)"


# ============================================================
# 집계 컬럼 이름 짓기
# ============================================================

# 집계표의 컬럼은 **원본 컬럼 이름에 접미사를 붙여** 만든다. 그 이름을 만드는 쪽(`breakdown`)과
# 읽는 쪽(`runner`)이 다른 파일이므로 접미사가 리터럴이면 한쪽만 바뀌어도 예외가 나지 않는다 —
# `runner` 의 `_to_percent` 는 없는 컬럼을 **건너뛰므로 조용히 빈 열**이 된다
SUFFIX_MEAN: Final = "Mean"
SUFFIX_MEDIAN: Final = "Median"
SUFFIX_COUNT: Final = "Count"

# 분위 컬럼과 그 표시 이름. **재는 쪽과 읽는 쪽이 같은 목록을 본다** — 전에는 재는 쪽만
# `TAIL_QUANTILES` 에서 컬럼 이름을 유도하고 읽는 쪽은 `P05`·`P95` 를 손으로 적어,
# 분위를 바꾸면 그 열이 조용히 비었다.
#
# [주의] **레이블 문자열에는 분위가 박혀 있다**(`하위5%`). 키를 바꾸면 컬럼 이름은 따라오지만
# 레이블은 따라오지 않으므로 **아래 `DISPLAY_TOTAL_DIVERGENCE_P05`·`_P95` 도 함께 고친다**
TAIL_DISPLAY_LABELS: Final = {
    0.05: DISPLAY_TOTAL_DIVERGENCE_P05,
    0.95: DISPLAY_TOTAL_DIVERGENCE_P95,
}

TAIL_QUANTILES: Final = tuple(TAIL_DISPLAY_LABELS)


def tail_column(quantile: float) -> str:
    """분위 컬럼 이름을 만든다.

    Args:
        quantile: 분위 (비율, 0.05 = 하위 5%)

    Returns:
        총 괴리의 분위 컬럼 이름 (예: `TotalDivergenceP05`)
    """
    # **`int()` 로 자르지 않는다.** 이진 부동소수 오차 때문에 `0.29 * 100` 이 28.999… 로 나와
    # `P28` 이 되고, 그 열은 29분위 값을 담은 채 이름만 틀린다 — 예외는 나지 않는다
    return f"{COL_TOTAL_DIVERGENCE}P{round(quantile * RATE_TO_PERCENT):02d}"


# ============================================================
# 산출물 파일
# ============================================================

# 이 매매법의 이름(slug). 규약은 `src/verify_lab/CLAUDE.md` 「매매법 이름 계약」이 SoT다
TRACK_NAME: Final = "leverage_tracking"

DIVERGENCE_FILENAME: Final = "divergence.csv"
BREAKDOWN_FILENAME: Final = "breakdown.csv"
DISTRIBUTION_FILENAME: Final = "distribution.csv"
FULL_PERIOD_FILENAME: Final = "full_period.csv"

# 시작일 원자료는 쌍마다 파일을 나눈다. 한 파일에 담으면 60만 행이 넘어 열리지 않는다
WINDOWS_FILENAME_TEMPLATE: Final = "windows_{ticker}.csv"

# ============================================================
# 제외 사유 (measure 의 사유와 뜻이 다른 것만 여기 둔다)
# ============================================================

# 실현 배수를 내지 않은 칸의 사유. 괴리 3값은 그대로 있고 실현 배수만 비어 있다
REASON_BASE_RETURN_TOO_SMALL: Final = "1배 수익률이 너무 작아 실현 배수를 내지 않음"


# ============================================================
# 산출물 파일
# ============================================================

# **산출물 필드 이름 → 파일 이름.** 이 사전이 「이 검증이 무슨 파일을 내는가」의 자리다.
# runner 가 `row_counts` 를 이것으로 키잉하고 CLI 가 이것을 돌며 저장한다 —
# 왜 CLI 가 이름을 갖지 않는지는 `src/verify_lab/CLAUDE.md` 실행 요약 계약이 SoT 다.
OUTPUT_FILES: Final[dict[str, str]] = {
    "divergence": DIVERGENCE_FILENAME,
    "breakdown": BREAKDOWN_FILENAME,
    "distribution": DISTRIBUTION_FILENAME,
    "full_period": FULL_PERIOD_FILENAME,
}
