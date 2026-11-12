"""verify-lab 공통 상수

두 개 이상의 계층에서 함께 쓰는 값을 단일 관리한다 — 경로·시세 스키마·가격 표기,
그리고 계층을 가로지르는 단위 계수와 시간대다.
상수를 어느 계층에 둘지 판단하는 기준과 저장 규칙은 `src/verify_lab/CLAUDE.md` 를 따른다.
"""

from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo

# ============================================================
# 경로 상수
# ============================================================

# 저장소 루트 (이 파일 기준 2단계 상위: src/verify_lab → src → 루트).
# 실행 디렉터리(CWD)를 기준으로 삼지 않는다. 같은 검증을 파라미터만 바꿔 여러 번 돌리는 것이
# 전제이므로, 어느 위치에서 실행하든 같은 곳을 가리켜야 결과가 흩어지지 않는다
BASE_DIR: Final = Path(__file__).resolve().parents[2]

STORAGE_DIR: Final = BASE_DIR / "storage"

# quant-data 사본(목록 · 매니페스트 포함)을 받는 폴더 — 손으로 고치지 않고 결과와 함께 커밋
# 시세와 값 하나짜리 계열이 섞여 있어 어느 로더로 읽을지는 매매법의 대상 정의가 정함
MARKET_DIR: Final = STORAGE_DIR / "market"

# 검증 산출물. **매매법당 한 폴더**이고 재실행이 그 자리를 덮는다. git 으로 동기화하는 것은
# diff 가 「재실행이 숫자를 바꿨는가」를 알려주는 유일한 신호이기 때문이다
RESULTS_DIR: Final = STORAGE_DIR / "results"

# 산출물의 등급 폴더 이름은 여기 두지 않는다 — **`tracks.py` 가 등급과 그 값을 함께 소유**한다.
# 여기 두면 「어떤 등급이 있는가」와 「이 매매법은 어느 등급인가」가 두 파일로 갈리고,
# 그러면 등급을 호출 측이 골라 넘기게 되어 레지스트리가 SoT 가 아니게 된다.

# 실행 이력. 최근 N개만 순환 저장한다 (개수는 `utils/meta_manager.py` 가 소유)
META_JSON_PATH: Final = RESULTS_DIR / "meta.json"

# 판단용 차트. **git 제외다** — 산출물을 다시 그린 보기라 재현은 명령이 하고, plotly.js 를 내장해 한 장이 수 MB 다.
# `RESULTS_DIR` 밖에 두는 것은 재실행이 그 폴더를 비우기 때문이다
CHARTS_DIR: Final = STORAGE_DIR / "charts"

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

# ============================================================
# 일별 단일 값 시계열 스키마
# ============================================================

# 값 컬럼. 환율은 원, 금리는 백분율처럼 **단위가 소스마다 다르므로 중립적인 이름을 쓴다** —
# `Close` 나 `Rate` 로 두면 그 이름이 맞지 않는 소스가 들어올 때 컬럼을 다시 갈라야 한다.
# 단위와 자릿수는 quant-data 가 정하고 그 매매법의 `설계.md` 가 기록한다
COL_VALUE: Final = "Value"

# 단일 값 시계열 파일이 반드시 가져야 하는 컬럼과 그 순서
SERIES_REQUIRED_COLUMNS: Final = [COL_DATE, COL_VALUE]

# ============================================================
# 원시 시세 파일명
# ============================================================

# quant-data 사본의 이름 그대로(그 저장소 결정 Q33) — 어긋나면 「파일 없음」으로만 드러나 한 곳에서 정함
# (`src/verify_lab/CLAUDE.md` 「받은 사본 규칙」). 지수는 야후 심볼(`^GSPC`)이 든 원본가 이름
MARKET_FILE_TEMPLATE: Final = "{ticker}_raw.csv"
ADJUSTED_FILE_TEMPLATE: Final = "{ticker}_adjusted.csv"

# ============================================================
# 가격 표기
# ============================================================

# 결과 CSV · 판단용 차트의 가격 자릿수 — 입력 사본은 6자리(quant-data 결정 Q6), 내보낼 때만 깎음
# (자릿수 규칙표는 `~/.claude/rules/python.md` · 근거는 `src/verify_lab/CLAUDE.md` 「받은 사본 규칙」)
PRICE_DECIMALS: Final = 4

# ============================================================
# 단위 계수와 시간대
# ============================================================

# 비율(0~1)을 백분율로 바꾸는 계수. `measure`·`report`·`execution`·`studies` 가 모두 쓴다 —
# 계층마다 따로 정의하면 한쪽만 바뀌어도 예외가 나지 않고 표만 조용히 어긋난다
RATE_TO_PERCENT: Final = 100

# 실행 시각의 기준 시간대 — 실행 이력(`utils/meta_manager.py`)과 판단용 차트의 만든 시각을 맞춤
KST: Final = ZoneInfo("Asia/Seoul")
