"""측정 계층 공통 상수

`measure` 가 내는 long-form 결과의 스키마를 단일 관리한다. 컬럼명과 제외 사유가
파일마다 흩어지면 같은 표를 만드는 코드와 읽는 코드가 조용히 갈라진다.

이 스키마는 2-b(통계 집계)와 2-c(출력)의 입력이기도 하다. 계약과 그 근거는
`docs/ROADMAP.md` "확정된 forward return 반환 계약" 이 SoT 다.
"""

# ============================================================
# forward return 결과 스키마 (내부 계산용 영문 토큰)
# ============================================================

# 신호일은 시세 스키마의 날짜 컬럼(`common_constants.COL_DATE`)을 그대로 쓴다 —
# 새 이름을 만들면 시세와 대조할 때마다 변환이 붙는다
COL_BASIS = "Basis"
COL_HORIZON = "Horizon"
COL_FORWARD_RETURN = "ForwardReturn"
COL_EXCLUDED_REASON = "ExcludedReason"

# ============================================================
# 제외 사유
# ============================================================

# 유효한 칸은 빈 문자열이다. 제외된 행은 지우지 않고 값만 비운 뒤 사유를 단다 —
# 행이 사라지면 표본이 조용히 줄어 생존편향이 생긴다
REASON_NONE = ""
REASON_OUT_OF_RANGE = "구간 끝이 데이터 범위를 넘음"

# ============================================================
# 제외 건수 요약 스키마
# ============================================================

COL_SIGNAL_COUNT = "SignalCount"
COL_EXCLUDED_COUNT = "ExcludedCount"

EXCLUDED_SUMMARY_COLUMNS = [COL_BASIS, COL_HORIZON, COL_SIGNAL_COUNT, COL_EXCLUDED_COUNT]
