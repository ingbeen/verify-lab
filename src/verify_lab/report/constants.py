"""출력 계층 상수 — 표시용 레이블과 단위

`measure` 는 영문 토큰과 비율(0~1)로 낸다. 사람이 읽는 것은 한글 레이블과 백분율이므로
그 번역표를 여기 단일 관리한다. 레이블이 파일마다 흩어지면 화면과 CSV 의 헤더가 갈라진다.

**저장 값의 단위는 백분율이다.** 반올림 자릿수는 `.claude/rules/python.md` 의 출력 반올림
규칙을 따른다 — 수익률·비율 같은 백분율은 2자리, 우연확률 같은 확률은 4자리다.
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

# 방향 비율은 **두 쪽을 그대로 나란히 둔다.** 어느 쪽이 "이긴 것"인지 정하지 않는다 —
# 오른 비율이 기준선보다 낮은 것은 탈락이 아니라 아래로 거는 신호이기 때문이다
# (루트 `CLAUDE.md` 측정의 원칙 11). 둘은 여집합이 아니다 — 보합이 어느 쪽에도 안 들어간다
DISPLAY_UP_RATE = "오른 비율(%)"
DISPLAY_DOWN_RATE = "내린 비율(%)"

DISPLAY_MAX = "최고(%)"
DISPLAY_MIN = "최악(%)"
DISPLAY_STD = "표준편차(%)"

DISPLAY_BASELINE = "베이스라인"
DISPLAY_POPULATION = "모집단"
DISPLAY_SIGNAL_SAMPLE = "신호 표본"
DISPLAY_BASELINE_SAMPLE = "베이스라인 표본"

# 기준선 대비 차이의 단위는 백분율 포인트다 — 백분율끼리의 차이이므로 %p 로 표기한다.
# **"초과"라고 쓰지 않는다** — 무엇 대비인지가 드러나지 않고, 음수일 때 "초과가 음수"라는
# 말이 되어 읽는 사람이 한 번 더 번역해야 한다
DISPLAY_MEAN_DIFF = "평균 차이(%p)"
DISPLAY_MEDIAN_DIFF = "중앙값 차이(%p)"
DISPLAY_UP_RATE_DIFF = "오른 비율 차이(%p)"
DISPLAY_DOWN_RATE_DIFF = "내린 비율 차이(%p)"

DISPLAY_OBSERVED_MEAN = "관측 평균(%)"
DISPLAY_OBSERVED_MEDIAN = "관측 중앙값(%)"
DISPLAY_NULL_P05 = "무작위 하위5%(%)"
DISPLAY_NULL_P95 = "무작위 상위5%(%)"

# **`p값` 대신 `우연확률` 로 적는다.** 뜻이 이름에 드러나야 한 줄 정의 없이 읽힌다
# (루트 `CLAUDE.md` 결과 보고의 원칙 — 전문 용어보다 일상어)
DISPLAY_MEAN_PERCENTILE = "평균 백분위"
DISPLAY_MEAN_P_VALUE = "평균 우연확률"
DISPLAY_MEDIAN_PERCENTILE = "중앙값 백분위"
DISPLAY_MEDIAN_P_VALUE = "중앙값 우연확률"

DISPLAY_OBSERVED_UP_RATE = "관측 오른 비율(%)"
DISPLAY_UP_RATE_PERCENTILE = "오른 비율 백분위"
DISPLAY_UP_RATE_P_VALUE = "오른 비율 우연확률"
DISPLAY_OBSERVED_DOWN_RATE = "관측 내린 비율(%)"
DISPLAY_DOWN_RATE_PERCENTILE = "내린 비율 백분위"
DISPLAY_DOWN_RATE_P_VALUE = "내린 비율 우연확률"

DISPLAY_TEST_NOTE = "비고"

# 표본이 하한에 못 미쳐도 **행은 남기고** 이 컬럼으로 「판정에 쓰지 말라」를 적는다
# (측정의 원칙 17). 세 검증이 같은 문자열을 따로 두고 있었으므로 여기서 하나로 낸다
DISPLAY_JUDGEABLE = "판정가능"

# 후보 판정 (measure/screening.py 의 결과)
DISPLAY_DIRECTION = "방향"
DISPLAY_HIT_RATE = "적중률(%)"
DISPLAY_EXPECTED_VALUE = "방향 기대값(%)"
# 회당 기대값에 표본 수를 곱한 값 — 같은 금액을 표본 수만큼 반복 투자했을 때의 단순 합이다.
# 신호가 드물거나 보유가 며칠짜리인 매매법은 **회당 평균이 구조적으로 작게 나와** 크기 감각을
# 주지 못하므로 둘을 나란히 둔다 (루트 `CLAUDE.md` 측정의 원칙 16)
DISPLAY_TOTAL_RETURN = "합산 수익률(%)"
DISPLAY_BASELINE_HIT_RATE = "기준선(%)"
DISPLAY_BASELINE_GAP = "기준선 대비 차이(%p)"
DISPLAY_P_VALUE = "우연확률"
DISPLAY_PERIOD_COUNT = "시기 구간"
DISPLAY_PERIOD_MIN_HIT_RATE = "가장 약한 시기(%)"
DISPLAY_SCREEN = "1차 판정"
DISPLAY_SUPPORT = "뒷받침"
DISPLAY_UNMET_SUPPORT = "미충족"

# 등급을 「충족/물음」 한 칸으로 합칠 때 쓰는 구분자. **분모를 떼지 않는다** —
# 시기를 못 잰 칸은 분모가 2 여서 `2/2` 가 되는데, 이는 `3/3` 과 같은 뜻이 아니다
SUPPORT_SEPARATOR = "/"

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

# 측정 구간의 표시 이름. **재는 구간의 목록이 아니라 "거래일 → 이름" 사전이다** —
# 무엇을 재는지는 `measure.forward_return.DEFAULT_HORIZONS` 가 정한다. 여기 없는 구간은
# `f"{days}일"` 로 나가므로(`tables._horizon_label`), 그 형태로 충분한 구간은 등록하지 않는다
HORIZON_LABELS = {
    1: "1일",
    5: "1주",
    10: "2주",
    21: "1개월",
}

# ============================================================
# 단위와 자릿수
# ============================================================

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
