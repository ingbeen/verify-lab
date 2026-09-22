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

# 측정의 원칙 17 의 시기 축(`전체`·`앞 절반`·`뒤 절반`·`최근 10년`·`최근 5년`)의 헤더.
# **원칙이 «모든» 검증·매매법에 요구하는 축이라 소유자가 하나여야 한다** — 값(구간 이름)은
# `measure/constants.py` 가 소유하고 헤더는 여기다. 검증 둘과 매매가 각자 정의하면
# 같은 축이 계층마다 다른 이름으로 나가고, 실제로 검증은 `시기` 매매는 `구간` 이었다.
# **`DISPLAY_HORIZON` 과 헷갈리지 않게 값을 가른다** — 그쪽은 보유 기간(`1주`·`1개월`)이고
# 이쪽은 데이터의 어느 시기인가다. 한 파일에 둘이 함께 실리는 표가 실재한다
DISPLAY_PERIOD = "시기"

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

# 손익비의 재료. **방향을 정하지 않은 이름을 쓴다** — 이 계층은 어느 쪽이 「이긴 것」인지
# 모르므로 「이길 때/질 때」로 부를 수 없다 (`.claude/rules/docs.md` 용어 대응표)
DISPLAY_POSITIVE_MEAN = "오른 평균(%)"
DISPLAY_NEGATIVE_MEAN = "내린 평균(%)"
DISPLAY_POSITIVE_COUNT = "오른 건수"
DISPLAY_NEGATIVE_COUNT = "내린 건수"

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

# 겹치지 않게 고를 수 있는 구간의 최대 개수. **산식은 `measure.statistics.max_non_overlapping`
# 이 소유하고 표시 이름은 여기가 소유한다** — 롤링 전수는 이웃끼리 심하게 겹쳐
# 표본 수만 적으면 실제보다 훨씬 단단해 보이고, 그것을 드러내는 것이
# `src/verify_lab/CLAUDE.md` 「비중첩 표본 계약」이 모든 검증에 요구하는 축이다.
#
# **세 검증이 같은 표를 내므로 이름이 한 벌이어야 나란히 읽힌다** — 검증마다 두면
# 한쪽이 바뀌어도 예외가 나지 않고 헤더만 조용히 갈린다
DISPLAY_NON_OVERLAPPING = "비중첩 표본"

# 표본이 하한에 못 미쳐도 **행은 남기고** 이 컬럼으로 「판정에 쓰지 말라」를 적는다
# (측정의 원칙 17). 세 검증이 같은 문자열을 따로 두고 있었으므로 여기서 하나로 낸다
DISPLAY_JUDGEABLE = "판정가능"

# 평균의 부호와 방향 비율이 어긋나는 칸 (측정의 원칙 13). 평균이 양수인데 절반 넘게 내렸다면
# 소수의 큰 사건이 평균을 만든 것이라, 평균만 보면 그 칸을 놓친다.
# 판정은 `measure.statistics.mean_rate_conflict`, 컬럼 토큰은 `measure/constants.py` 가 갖는다
DISPLAY_MEAN_RATE_CONFLICT = "평균-비율 어긋남"

# 후보 판정 (measure/screening.py 의 결과)
DISPLAY_DIRECTION = "방향"
DISPLAY_HIT_RATE = "적중률(%)"
DISPLAY_EXPECTED_VALUE = "방향 기대값(%)"
# 회당 기대값에 표본 수를 곱한 값 — 같은 금액을 표본 수만큼 반복 투자했을 때의 단순 합이다.
# 신호가 드물거나 보유가 며칠짜리인 매매법은 **회당 평균이 구조적으로 작게 나와** 크기 감각을
# 주지 못하므로 둘을 나란히 둔다 (루트 `CLAUDE.md` 측정의 원칙 16)
DISPLAY_TOTAL_RETURN = "합산 수익률(%)"

# 후보 · 제외 · 판정 안 함 셋 중 하나. **판정표는 판정에 쓰는 축만 담으므로 기준선이 없다** —
# 그 값은 `통계.csv` 계열이 담고, 왜 판정에서 뺐는지는 루트 `CLAUDE.md`
# 「기준선은 탈락 사유가 아니다」가 SoT 다
DISPLAY_SCREEN = "1차 판정"

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
# 무엇을 재는지는 각 검증의 격자가 정한다(`measure.forward_return.DEFAULT_HORIZONS` ·
# `leverage_tracking.HORIZONS` · `futures_leverage.HOLDING_HORIZONS`).
#
# **저장소가 쓰는 격자를 여기서 «전부» 덮는다.** 공통 계층이 자기 축을 다 덮지 못하면 검증이
# 사본을 만들고, 사본은 반드시 갈라진다 — 같은 `(5,10,21,63,126,252,756)` 격자를 두고
# 한 검증은 사본으로 `1주·3개월·3년` 을, 다른 검증은 라벨을 거치지 않아 `5·63·756` 을 냈다.
# **두 산출물을 나란히 읽을 수 없고 예외는 나지 않는다.**
#
# 달력 이름이 없는 짧은 구간(`2`·`3`)은 등록하지 않는다 — `f"{days}일"` fallback 이
# 내는 `2일`·`3일` 이 이미 그 값의 정확한 이름이다 (`tables.horizon_label`).
HORIZON_LABELS = {
    1: "1일",
    5: "1주",
    10: "2주",
    21: "1개월",
    63: "3개월",
    126: "6개월",
    252: "1년",
    756: "3년",
}

# ============================================================
# 단위와 자릿수
# ============================================================

# 백분율 (수익률·승률·백분위)
PERCENT_DECIMALS = 2

# 확률 (p 값). 백분율이 아니므로 자릿수가 다르다
PROBABILITY_DECIMALS = 4

# 손익비. **배수라서 백분율도 확률도 아니다.** 2자리면 1.034 와 1.056 이 1.03 과 1.06 으로
# 뭉개져 1.0 경계 근처의 칸을 구별할 수 없다 — 실측에서 채택 칸이 1.034, 제외 칸이 0.788 이었다
PAYOFF_DECIMALS = 3

# 값이 없는 칸의 표기. 빈칸으로 두면 "값이 0" 또는 "아직 안 돌았다"로 읽힌다
EMPTY_MARK = "-"

# 터미널 표의 컬럼 사이 여백 (칸)
COLUMN_GAP = 2

DATE_FORMAT = "%Y-%m-%d"

# ============================================================
# 산출물 파일
# ============================================================
#
# **이름을 두 벌로 가르는 경계는 「종류」다** — 「중요도」가 아니다.
# 중요도는 사람마다·시점마다 달라서 새 표가 생길 때마다 다시 물어야 하고, 판정이 갈리면
# 이름이 뒤섞인다.
#
# | 한글 | 사용자가 **판정에 쓰는** 표 — 성적표 · 거래내역 · 1차_판정 · 통계 |
# | 영문 | **원자료와 검정** 표 — 신호일 목록 · 기준선 대비 · 무작위 대조 |
#
# 한글 넷은 **세 매매법이 글자 그대로 같은 이름**을 쓴다. 축을 이름에 넣지 않는 것이
# 그 조건이다(`만기월별_통계` 가 아니라 `통계`) — 폴더가 매매법을 말하므로 이름에 또
# 넣으면 중복이고, 넣는 순간 세 이름이 다시 갈린다.

SIGNALS_FILENAME = "signals.csv"
EXCESS_FILENAME = "excess.csv"
TEST_FILENAME = "test.csv"

# 축별 집계표. 축은 검증마다 다르지만(만기월·달·구간) **파일 이름은 같다**
STATISTICS_FILENAME = "통계.csv"

# 확정 칸의 «해석 재료»를 한 장에 담는 표 (2026-09-21). 성적표가 「걸 만한가」에 답한다면
# 이쪽은 **「그 값을 어떻게 읽나」**에 답한다 — 중앙값 · 평균-비율 어긋남 · 기준선 ·
# 우연확률 · 배당락이며 **성적표에는 그중 어느 것도 없다.**
#
# [중요] **`통계.csv` 와 공존한다.** 확정 칸으로 좁힌 매매법(옵션 만기일·월말)이 이 이름을
# 쓰고, **역방향은 아직 `통계.csv` 를 낸다** — 그쪽은 격자 전체를 재는 중이라 축별 집계표가
# 그대로 필요하다. **두 이름이 같은 자리를 뜻한다고 읽으면 안 된다** — 담는 축이 다르다
MEASURE_FILENAME = "측정.csv"

RUN_SUMMARY_FILENAME = "summary.json"

# 한글 헤더가 엑셀에서 깨지지 않도록 BOM 을 붙인다 (기존 산출물 관용과 동일)
CSV_ENCODING = "utf-8-sig"

# 배당락 세 컬럼의 표시 이름 (측정의 원칙 14 · `.claude/rules/trading.md` 「확정 전 필수 항목」).
# **컬럼 이름은 `measure/constants.py` 가 갖고 레이블은 여기가 갖는다** — 원칙이 모든
# 매매법에 요구하는 축이라 검증마다 다른 말을 쓰면 두 산출물을 나란히 읽을 수 없다
DISPLAY_DIVIDEND_MEASURED = "배당락 대조 건수"
DISPLAY_DIVIDEND_HIT_COUNT = "배당락 걸린 건수"
DISPLAY_DIVIDEND_MEAN_IMPACT = "배당락 평균 왜곡(%p)"


# ============================================================
# 달력형 매매법의 공통 레이블
# ============================================================

# 여러 매매법이 공유하는 다섯 레이블이다. 앞 넷은 **진입도 청산도 달력으로 정해지는**
# 매매법 셋이 함께 쓰고, `DISPLAY_EXCLUDED_REASON` 은 **달력형이 아닌 배수 검증도** 쓴다 —
# 「제외 사유」는 표본 보존이 모든 계층에 요구하는 말이라 달력에 묶이지 않는다.
#
# **컬럼 토큰은 `measure/constants.py` 가 소유하고 그 표시 이름은 여기가 소유한다.**
# 한쪽만 옮기면 **절반짜리 통합**이 되어, 컬럼이 공통인데 헤더는 매매법마다 갈릴 수 있다 —
# 그 상태에서는 한쪽 이름이 바뀌어도 예외가 나지 않고 두 산출물의 헤더만 어긋난다.
#
# **세 번째 달력형 매매법이 오면서 정했다** — `src/verify_lab/CLAUDE.md` 가 달력형 어휘의
# 통합을 「세 번째 검증이 올 때 무엇이 실제로 반복되는지 보고 정한다」로 유보해 두었고,
# 만기_말일이 그 세 번째다. 셋이 같은 표를 내므로 이름이 한 벌이어야 조인된다.
DISPLAY_ENTRY_CLOSE = "진입 종가"
DISPLAY_EXIT_CLOSE = "청산 종가"

# **`execution/constants.py` 의 `DISPLAY_HOLD_DAYS`(「보유일」)와 다른 값이다** —
# 그쪽은 성적표의 **평균** 보유일이고 이것은 체결 하나의 보유 거래일 수다
DISPLAY_HOLD_DAYS_EXACT = "보유 거래일"

DISPLAY_EXCLUDED_REASON = "제외 사유"

# 달 축(1~12). **`DISPLAY_DATE`(날짜)와 다른 축**이라 이름을 가른다
DISPLAY_MONTH_NUMBER = "월"
