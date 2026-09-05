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

# 수집한 원시 시세. git 으로 동기화하며 분석 코드가 덮어쓰지 않는 불변 자산이다
MARKET_DIR: Final = STORAGE_DIR / "market"

# 일별 단일 값 시계열 (환율 고시가·금리 등). `MARKET_DIR` 와 **폴더를 나누는 것이 곧 스키마 구분**이다 —
# 한 폴더에 OHLCV 와 단일 값이 섞이면 파일을 열어보기 전에는 어느 로더로 읽어야 할지 알 수 없고,
# 잘못된 로더를 부르면 컬럼 검증에서야 걸린다. 폴더가 다르면 그 판단이 경로에서 끝난다
SERIES_DIR: Final = STORAGE_DIR / "series"

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

# ============================================================
# 선물 시세 스키마 (공통 스키마의 확장)
# ============================================================

# 계약 식별자(ISIN)와 계약명. **선물은 하루에 여러 계약이 동시에 거래되므로 날짜만으로는
# 행이 유일해지지 않는다.** 공통 시세 파일이 날짜를 유일 키로 전제하는 것과 갈리는 지점이며,
# 그래서 선물은 전용 로더로 읽는다 (`data/loader.py` 의 `load_futures_csv`)
COL_CONTRACT: Final = "Contract"
COL_CONTRACT_NAME: Final = "ContractName"

# 정산가. 거래가 없는 날에도 거래소가 매기므로 **롤 계수는 종가가 아니라 이 값으로 낸다.**
# 원월물은 체결이 없는 날이 많아 종가가 결측이다
COL_SETTLE: Final = "Settle"

# 미결제약정. 시장이 어느 계약으로 옮겨갔는지를 보는 축이다
COL_OPEN_INTEREST: Final = "OpenInterest"

# 현물 지수값. 거래소가 시세와 함께 주므로 베이시스를 따로 받지 않아도 된다
COL_SPOT: Final = "Spot"

# 선물 시세 파일이 반드시 가져야 하는 컬럼과 그 순서
FUTURES_REQUIRED_COLUMNS: Final = [
    COL_DATE,
    COL_CONTRACT,
    COL_CONTRACT_NAME,
    COL_OPEN,
    COL_HIGH,
    COL_LOW,
    COL_CLOSE,
    COL_VOLUME,
    COL_SETTLE,
    COL_OPEN_INTEREST,
    COL_SPOT,
]

# 한 행을 유일하게 가리키는 키. 로더의 중복 판정이 이 조합을 쓴다
FUTURES_ROW_KEY: Final = [COL_DATE, COL_CONTRACT]

# ============================================================
# 일별 단일 값 시계열 스키마
# ============================================================

# 값 컬럼. 환율은 원, 금리는 백분율처럼 **단위가 소스마다 다르므로 중립적인 이름을 쓴다** —
# `Close` 나 `Rate` 로 두면 그 이름이 맞지 않는 소스가 들어올 때 컬럼을 다시 갈라야 한다.
# 단위와 자릿수는 각 수집기가 소유하고 `docs/spec/` 의 데이터 스펙이 기록한다
COL_VALUE: Final = "Value"

# 단일 값 시계열 파일이 반드시 가져야 하는 컬럼과 그 순서
SERIES_REQUIRED_COLUMNS: Final = [COL_DATE, COL_VALUE]

# ============================================================
# 원시 시세 파일명
# ============================================================

# **파일명 규칙은 수집기와 읽는 쪽이 공유하는 계약이다.** 수집기 4곳·측정 1곳·검증 2곳·
# 스크립트 1곳에 같은 문자열이 흩어져 있었고, 한 곳만 달라져도 **예외는 「파일 없음」으로만 뜬다** —
# 무엇이 어긋났는지가 드러나지 않는다. 그래서 한 곳에서만 정한다
# (`src/verify_lab/CLAUDE.md` 「계층 간 계약」의 원시 시세 저장 규칙).
#
# **기간은 파일명에 넣지 않는다.** 언제나 받을 수 있는 전 기간을 받으므로 로더가 읽을 대상이
# 갈리지 않는다. 반면 **가격 기준이 다르면 내용이 다른 데이터**라 파일을 나눈다
MARKET_FILE_TEMPLATE: Final = "{ticker}_max.csv"
ADJUSTED_FILE_TEMPLATE: Final = "{ticker}_adjusted_max.csv"

# 선물은 **종목이 아니라 상품 코드**로 갈린다. 하루에 여러 계약이 동시에 거래돼 날짜만으로는
# 행이 유일해지지 않으므로 전용 로더로 읽으며, 이름이 그 사실을 드러내야 한다
FUTURES_FILE_TEMPLATE: Final = "{product_id}_max.csv"

# NAV 는 시세가 아니라 일별 단일 값이라 `SERIES_DIR` 에 저장한다.
# 수집기가 쓰고 검증이 읽으므로 두 계층이 같은 이름을 봐야 한다
NAV_FILE_TEMPLATE: Final = "{ticker}_NAV.csv"

# ============================================================
# 가격 표기
# ============================================================

# 소수가 나오는 시장의 가격 자릿수. 원시 시세 저장(`data/`)과 결과 CSV 의 종가 출력(`studies/`)이
# **반드시 같은 값**을 써야 한다 — 저장이 4자리인데 출력이 더 깊으면 없는 정밀도를 만들어 내고,
# 반대면 저장해 둔 값을 버린다. 두 계층이 각자 정의하면 한쪽만 바뀌어도 예외가 나지 않는다.
# 자릿수 규칙표는 `.claude/rules/python.md` 가 SoT다
PRICE_DECIMALS: Final = 4

# KRX 원화 가격의 자릿수. **실제 호가에 없는 소수 자리를 붙이지 않는다.**
# 여러 검증이 국내 종목을 다루므로 계층마다 따로 두지 않는다
PRICE_DECIMALS_KRW: Final = 0

# ============================================================
# 단위 계수와 시간대
# ============================================================

# 비율(0~1)을 백분율로 바꾸는 계수. `measure`·`report`·`studies`·`strategy` 가 모두 쓴다 —
# 계층마다 따로 정의하면 한쪽만 바뀌어도 예외가 나지 않고 표만 조용히 어긋난다
RATE_TO_PERCENT: Final = 100

# 연 이자율을 하루치로 나눌 때 쓰는 일수. **달력일 기준이다** — 연율로 고시되는 금리는
# 거래일이 아니라 달력일로 붙으므로, 거래일로 나누면 연휴가 긴 해에 이자가 덜 붙는다.
# `usdkrw_equivalence` 와 `futures_leverage` 가 함께 쓴다
CALENDAR_DAYS_PER_YEAR: Final = 365

# 실행 시각과 타임스탬프의 기준 시간대. 결과 폴더 이름(`report/`)과
# 실행 이력(`utils/meta_manager.py`)이 같은 값을 써야 두 기록이 같은 시각을 가리킨다
KST: Final = ZoneInfo("Asia/Seoul")
