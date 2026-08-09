"""
QBT 프로젝트 공통 상수

모든 도메인에서 공통으로 사용하는 상수를 정의한다.
- 경로 상수 (디렉토리, 데이터 파일, 결과 파일)
- 데이터 상수 (컬럼명, 연간 영업일, 수치 안정성 등)

학습 포인트:
1. 상수는 UPPER_SNAKE_CASE로 작성 (예: STORAGE_DIR)
2. pathlib.Path: 파일 경로를 다루는 객체지향 방식 (문자열보다 안전)
3. '/' 연산자로 경로 결합 가능 (예: STORAGE_DIR / "stock")
"""

from pathlib import Path
from typing import Final

# ============================================================
# 경로 상수
# ============================================================

# --- 디렉토리 경로 ---
# Path("storage"): 현재 작업 디렉토리 기준 상대 경로
# 프로젝트 루트에서 실행 시 /home/user/project/storage 를 의미
STORAGE_DIR: Final = Path("storage")

# '/' 연산자로 경로 결합: Path 객체끼리 또는 Path와 문자열 결합 가능
# STORAGE_DIR / "stock" = Path("storage/stock")
STOCK_DIR: Final = STORAGE_DIR / "stock"  # 주식 데이터 저장 디렉토리
ETC_DIR: Final = STORAGE_DIR / "etc"  # 금리 등 기타 데이터 저장 디렉토리
RESULTS_DIR: Final = STORAGE_DIR / "results"  # 분석 결과 저장 디렉토리
BACKTEST_RESULTS_DIR: Final = RESULTS_DIR / "backtest"  # 백테스트 결과 저장 디렉토리
TQQQ_RESULTS_DIR: Final = RESULTS_DIR / "tqqq"  # TQQQ 시뮬레이션 결과 저장 디렉토리
PORTFOLIO_RESULTS_DIR: Final = RESULTS_DIR / "portfolio"  # 포트폴리오 실험 결과

# --- 데이터 파일 경로 ---
# 나스닥 100 추종 ETF 데이터 파일 경로
QQQ_DATA_PATH: Final = STOCK_DIR / "QQQ_max.csv"

# 합성 TQQQ 데이터 파일 경로 (시뮬레이션 생성)
TQQQ_SYNTHETIC_DATA_PATH: Final = STOCK_DIR / "TQQQ_synthetic_max.csv"

# 교차 자산 검증용 데이터 파일 경로
SPY_DATA_PATH: Final = STOCK_DIR / "SPY_max.csv"
IWM_DATA_PATH: Final = STOCK_DIR / "IWM_max.csv"
EFA_DATA_PATH: Final = STOCK_DIR / "EFA_max.csv"
EEM_DATA_PATH: Final = STOCK_DIR / "EEM_max.csv"
GLD_DATA_PATH: Final = STOCK_DIR / "GLD_max.csv"
TLT_DATA_PATH: Final = STOCK_DIR / "TLT_max.csv"

# 2배 레버리지 ETF 데이터 파일 경로
SSO_DATA_PATH: Final = STOCK_DIR / "SSO_max.csv"
QLD_DATA_PATH: Final = STOCK_DIR / "QLD_max.csv"
UGL_DATA_PATH: Final = STOCK_DIR / "UGL_max.csv"
UBT_DATA_PATH: Final = STOCK_DIR / "UBT_max.csv"

# --- 실행 이력 메타데이터 저장 경로 (JSON 형식) ---
META_JSON_PATH: Final = RESULTS_DIR / "meta.json"

# ============================================================
# 데이터 상수
# ============================================================

# --- CSV 컬럼명 (DataFrame 내부용) ---
# pandas DataFrame에서 사용할 컬럼명 상수
# 상수로 정의하면 오타 방지 및 일관성 유지 가능
COL_DATE: Final = "Date"  # 날짜 컬럼
COL_OPEN: Final = "Open"  # 시가 (Open Price)
COL_HIGH: Final = "High"  # 고가 (High Price)
COL_LOW: Final = "Low"  # 저가 (Low Price)
COL_CLOSE: Final = "Close"  # 종가 (Close Price)
COL_VOLUME: Final = "Volume"  # 거래량

# 컬럼 그룹
# 리스트(list)로 여러 컬럼명을 묶어서 관리
# CSV 파일 검증 시 필수 컬럼 확인에 사용
REQUIRED_COLUMNS: Final = [COL_DATE, COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME]

# 가격 관련 컬럼만 따로 묶음 (검증 시 양수 체크 등에 사용)
PRICE_COLUMNS: Final = [COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE]

# --- 출력용 컬럼명 (사용자 표시용) ---
# CSV나 로그에 표시할 때 사용하는 한글 레이블
DISPLAY_DATE: Final = "날짜"

# --- 기타 데이터 상수 ---

# 연간 영업일 상수
# CAGR (Compound Annual Growth Rate): 연평균 성장률 계산용
# 윤년을 고려한 1년 평균 일수 (365.25 = 365 + 1/4)
ANNUAL_DAYS: Final = 365.25  # CAGR 계산용 (윤년 포함)

# 주식 시장의 연간 거래일 수 (주말, 공휴일 제외)
# 일일 비용을 연간 비용으로 환산하거나 그 반대로 계산할 때 사용
TRADING_DAYS_PER_YEAR: Final = 252  # 일일 비용 환산용 (연간 거래일 수)

# 수치 안정성 상수
# EPSILON: 매우 작은 양수 값
# 1. 분모가 0이 되는 것 방지: 예) result = value / (divisor + EPSILON)
# 2. 로그 계산 시 0 방지: 예) log(value + EPSILON)
# 1e-12는 과학적 표기법으로 0.000000000001을 의미
EPSILON: Final = 1e-12  # 분모 0 방지 및 로그 계산 안정성 확보
