"""출력 계층 상수 — 표시용 레이블과 단위

`measure` 는 영문 토큰과 비율(0~1)로 낸다. 사람이 읽는 것은 한글 레이블과 백분율이므로
그 번역표를 여기 단일 관리한다. 레이블이 파일마다 흩어지면 화면과 CSV 의 헤더가 갈라진다.

**저장 값의 단위는 백분율이다.** 반올림 자릿수는 `.claude/rules/python.md` 의 출력 반올림
규칙을 따른다 — 수익률·승률 같은 백분율은 2자리, p 값 같은 확률은 4자리다.
"""

from verify_lab.measure.forward_return import ReturnBasis

# ============================================================
# 표시용 레이블 (measure 의 COL_* 에 대응)
# ============================================================

DISPLAY_DATE = "날짜"
DISPLAY_BASIS = "기준"
DISPLAY_HORIZON = "구간"

DISPLAY_SIGNAL_COUNT = "신호"
DISPLAY_EXCLUDED = "제외"
DISPLAY_SAMPLE_COUNT = "표본"

DISPLAY_MEAN = "평균(%)"
DISPLAY_MEDIAN = "중앙값(%)"
DISPLAY_WIN_RATE = "승률(%)"
DISPLAY_MAX = "최고(%)"
DISPLAY_MIN = "최악(%)"
DISPLAY_STD = "표준편차(%)"

DISPLAY_BASELINE = "베이스라인"
DISPLAY_POPULATION = "모집단"
DISPLAY_SIGNAL_SAMPLE = "신호 표본"
DISPLAY_BASELINE_SAMPLE = "베이스라인 표본"

# 초과분의 단위는 백분율 포인트다 — 백분율끼리의 차이이므로 %p 로 표기한다
DISPLAY_MEAN_EXCESS = "평균 초과(%p)"
DISPLAY_MEDIAN_EXCESS = "중앙값 초과(%p)"
DISPLAY_WIN_RATE_EXCESS = "승률 초과(%p)"

DISPLAY_OBSERVED_MEAN = "관측 평균(%)"
DISPLAY_OBSERVED_MEDIAN = "관측 중앙값(%)"
DISPLAY_NULL_P05 = "무작위 하위5%(%)"
DISPLAY_NULL_P95 = "무작위 상위5%(%)"
DISPLAY_MEAN_PERCENTILE = "평균 백분위"
DISPLAY_MEAN_P_VALUE = "p값"
DISPLAY_MEDIAN_PERCENTILE = "중앙값 백분위"
DISPLAY_MEDIAN_P_VALUE = "중앙값 p값"
DISPLAY_TEST_NOTE = "비고"

# ============================================================
# 값 번역표
# ============================================================

# 수익률 기준점의 표시 이름
BASIS_LABELS = {
    ReturnBasis.CLOSE.value: "종가",
    ReturnBasis.NEXT_OPEN.value: "익일시가",
}

# 기준을 나란히 놓을 때의 순서. 종가 기준이 먼저이고, 두 값의 차이가 갭으로 새는 몫이다
BASIS_ORDER = {basis.value: index for index, basis in enumerate(ReturnBasis)}

# 측정 구간의 표시 이름 (docs/spec/index_extreme_events.md §4)
HORIZON_LABELS = {
    1: "1일",
    5: "1주",
    21: "1개월",
    63: "3개월",
    126: "6개월",
    252: "1년",
}

# ============================================================
# 단위와 자릿수
# ============================================================

RATE_TO_PERCENT = 100

# 백분율 (수익률·승률·백분위)
PERCENT_DECIMALS = 2

# 확률 (p 값). 백분율이 아니므로 자릿수가 다르다
PROBABILITY_DECIMALS = 4

# 값이 없는 칸의 표기. 빈칸으로 두면 "값이 0" 또는 "아직 안 돌았다"로 읽힌다
EMPTY_MARK = "-"

# 터미널 표의 컬럼 사이 여백 (칸)
COLUMN_GAP = 2

DATE_FORMAT = "%Y-%m-%d"

# ============================================================
# 산출물 파일
# ============================================================

SIGNALS_FILENAME = "signals.csv"
STATISTICS_FILENAME = "statistics.csv"
EXCESS_FILENAME = "excess.csv"
TEST_FILENAME = "test.csv"
RUN_SUMMARY_FILENAME = "summary.json"

# 한글 헤더가 엑셀에서 깨지지 않도록 BOM 을 붙인다 (기존 산출물 관용과 동일)
CSV_ENCODING = "utf-8-sig"
