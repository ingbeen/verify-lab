"""verify-lab 공통 상수

두 개 이상의 계층에서 함께 쓰는 경로 상수와 시세 스키마 상수를 단일 관리한다.
상수를 어느 계층에 둘지 판단하는 기준과 저장 규칙은 `src/verify_lab/CLAUDE.md` 를 따른다.
"""

from pathlib import Path
from typing import Final

# ============================================================
# 경로 상수
# ============================================================

# 저장소 루트 (이 파일 기준 2단계 상위: src/verify_lab → src → 루트).
# 실행 디렉터리(CWD)를 기준으로 삼지 않는다. 같은 검증을 파라미터만 바꿔 여러 번 돌리는 것이
# 전제이므로, 어느 위치에서 실행하든 같은 곳을 가리켜야 결과가 흩어지지 않는다
BASE_DIR: Final = Path(__file__).resolve().parents[2]

STORAGE_DIR: Final = BASE_DIR / "storage"

# 수집한 원시 시세. git 으로 동기화하며 분석 코드가 덮어쓰지 않는 불변 자산이다
MARKET_DIR: Final = STORAGE_DIR / "market"

# 검증 산출물. 실행 시각으로 구분해 쌓이며 언제든 재생성 가능하므로 git 에서 제외한다
RESULTS_DIR: Final = STORAGE_DIR / "results"

# 실행 이력. 최근 N개만 순환 저장한다 (개수는 `utils/meta_manager.py` 가 소유)
META_JSON_PATH: Final = RESULTS_DIR / "meta.json"

# ============================================================
# 시세 스키마 컬럼 상수 (내부 계산용 영문 토큰)
# ============================================================

COL_DATE: Final = "Date"
COL_OPEN: Final = "Open"
COL_HIGH: Final = "High"
COL_LOW: Final = "Low"
COL_CLOSE: Final = "Close"
COL_VOLUME: Final = "Volume"

# 시세 파일이 반드시 가져야 하는 컬럼과 그 순서. 로딩 시 이 목록으로 스키마를 검증한다
REQUIRED_COLUMNS: Final = [COL_DATE, COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME]

# 가격 컬럼. 양수 검사처럼 가격에만 적용하는 검증의 대상이다
PRICE_COLUMNS: Final = [COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE]
