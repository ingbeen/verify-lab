"""시세 파일 로딩과 이상치 판정

모든 시세 파일 로딩은 이 모듈을 지난다. 각 검증이 직접 `pd.read_csv` 를 부르면
스키마 검증과 이상치 판정이 검증마다 갈라지고, 같은 파일을 다르게 읽는 코드가 생긴다.

이상을 발견하면 **메우지 않고 예외를 던진다.** 로더가 조용히 결측을 보간하면
그 위의 측정 결과 전체가 무효가 된다.
"""

from pathlib import Path

import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE, PRICE_COLUMNS, REQUIRED_COLUMNS
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 전일 대비 변동 임계 (비율, 0.50 = 50%). 이를 넘으면 시장 움직임이 아니라 데이터 오류로 본다.
# 국내 지수 ETF 의 가격제한폭(±30%)과 QQQ 의 역대 최대 일간 변동(약 ±17%)이 모두 이 아래에 있어
# 정상적인 급변동을 오탐하지 않는다
MAX_DAILY_CHANGE_RATE = 0.50


def validate_market_data(df: pd.DataFrame) -> None:
    """시세 DataFrame 의 이상 여부를 검사한다.

    결측·0 이하 가격·비정상 급등락을 검사하며, 어떤 형태의 보간도 하지 않는다.
    수집기와 로더가 이 함수를 함께 쓴다 — 판정이 두 곳으로 갈라지면
    "수집은 통과했는데 로딩에서 막히는" 데이터가 생긴다.

    Args:
        df: 검사할 시세 DataFrame (필수 컬럼이 이미 존재한다고 전제)

    Raises:
        ValueError: 결측, 0 이하 가격, 임계를 넘는 일간 변동이 발견된 경우
    """
    if df.empty:
        raise ValueError("시세 데이터가 비어 있습니다")

    # 1. 결측 검사
    for column in PRICE_COLUMNS:
        missing = df[column].isna()
        if missing.any():
            dates = df.loc[missing, COL_DATE].head().tolist()
            raise ValueError(f"결측 값 발견 - 컬럼: {column}, 건수: {int(missing.sum())}, 예시 날짜: {dates}")

    # 2. 0 이하 가격 검사. 가격이 0이 되는 것은 거래정지나 수집 오류이며 시장가가 아니다
    for column in PRICE_COLUMNS:
        non_positive = df[column] <= 0
        if non_positive.any():
            dates = df.loc[non_positive, COL_DATE].head().tolist()
            raise ValueError(f"0 이하 가격 발견 - 컬럼: {column}, 건수: {int(non_positive.sum())}, 예시 날짜: {dates}")

    # 3. 일간 변동 검사. 첫 행은 직전 값이 없어 NaN 이므로 검사 대상에서 빠진다
    change_rate = df[COL_CLOSE].pct_change()
    extreme = change_rate.abs() > MAX_DAILY_CHANGE_RATE

    if extreme.any():
        first_index = df.index[extreme][0]
        raise ValueError(
            f"비정상 급등락 발견 (임계: {MAX_DAILY_CHANGE_RATE:.0%}) - "
            f"날짜: {df.loc[first_index, COL_DATE]}, "
            f"변동률: {change_rate[first_index]:+.2%}, 건수: {int(extreme.sum())}"
        )


def load_market_csv(path: Path) -> pd.DataFrame:
    """시세 CSV 를 읽어 검증된 DataFrame 으로 돌려준다.

    파일 존재 확인 → 필수 컬럼 검증 → 날짜 파싱 → 시간순 정렬 → 중복 제거 → 이상치 검사
    순으로 수행한다. 원본 파일은 읽기만 하며 수정하지 않는다.

    Args:
        path: 시세 CSV 경로

    Returns:
        날짜 오름차순으로 정렬되고 인덱스가 0부터 다시 매겨진 DataFrame.
        날짜 컬럼의 dtype 은 `datetime64[ns]` 다

    Raises:
        FileNotFoundError: 파일이 없는 경우
        ValueError: 필수 컬럼 누락, 빈 데이터, 이상치가 발견된 경우
    """
    if not path.is_file():
        raise FileNotFoundError(f"시세 파일을 찾을 수 없습니다: {path}")

    df = pd.read_csv(path)

    # 1. 스키마 검증. 컬럼이 다르면 이후 판정이 전부 어긋나므로 가장 먼저 막는다
    missing_columns = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing_columns:
        raise ValueError(f"필수 컬럼이 누락되었습니다: {sorted(missing_columns)} (파일: {path})")

    # 2. 날짜 파싱. 창 기반 연산이 벡터화되도록 datetime64 를 유지한다
    df[COL_DATE] = pd.to_datetime(df[COL_DATE])

    # 3. 시간순 정렬
    df = df.sort_values(COL_DATE).reset_index(drop=True)

    # 4. 중복 날짜 제거. 몇 건이 왜 빠졌는지 남겨 표본이 조용히 사라지지 않게 한다
    duplicate_count = int(df.duplicated(subset=[COL_DATE]).sum())
    if duplicate_count > 0:
        logger.warning(f"중복 날짜 {duplicate_count}건을 제거했습니다 (파일: {path})")
        df = df.drop_duplicates(subset=[COL_DATE], keep="first").reset_index(drop=True)

    # 5. 이상치 검사. 통과한 데이터만 호출자에게 넘긴다
    validate_market_data(df)

    logger.debug(f"시세 로딩 완료: {len(df):,}행, 기간 {df[COL_DATE].min().date()} ~ {df[COL_DATE].max().date()}")

    return df
