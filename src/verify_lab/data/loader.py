"""시세·시계열 파일 로딩과 이상치 판정

모든 파일 로딩은 이 모듈을 지난다. 각 검증이 직접 `pd.read_csv` 를 부르면
스키마 검증과 이상치 판정이 검증마다 갈라지고, 같은 파일을 다르게 읽는 코드가 생긴다.

이상을 발견하면 **메우지 않고 예외를 던진다.** 로더가 조용히 결측을 보간하면
그 위의 측정 결과 전체가 무효가 된다.

**두 스키마를 다루며 판정이 서로 다르다.**

| | OHLCV 시세 | 일별 단일 값 시계열 |
| --- | --- | --- |
| 대상 | 주가·ETF | 환율 고시가·금리 |
| 유일 키 | 날짜 | 날짜 |
| 0 이하 값 | 오류로 본다 | **정상이다** (마이너스 금리) |
| 결측 종가 | 오류로 본다 | — |
| 거래량 | 결측 · 무한대 · 음수를 오류로 본다. **0 은 정상이다** (거래가 없던 날) | — |
| 큰 일간 변동 | 오류로 본다 | **정상이다** (환위기의 환율) |

값의 부호와 변동폭이 무엇을 뜻하는지는 소스마다 달라서, 시세의 판정을 시계열에 그대로
걸면 정상 데이터가 막힌다. 그래서 시계열 쪽은 **구조와 결측만** 본다.

**선물 시세(유일 키가 날짜 + 계약)에 `load_market_csv` 를 쓰면 안 된다** — 날짜 기준 중복 제거가
첫 계약만 남기고 나머지를 예외 없이 지운다. 선물 전용 로더는 `docs/조사/선물_대_레버리지_ETF.md`
「저장 스키마와 로더」 · 「재현 방법」에 있다.
"""

import math
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from verify_lab.common_constants import (
    COL_CLOSE,
    COL_DATE,
    COL_VALUE,
    COL_VOLUME,
    PRICE_COLUMNS,
    REQUIRED_COLUMNS,
    SERIES_REQUIRED_COLUMNS,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 전일 대비 변동 임계 (비율, 0.50 = 50%). 이를 넘으면 시장 움직임이 아니라 데이터 오류로 본다.
# 국내 지수 ETF 의 가격제한폭(±30%)과 QQQ 의 역대 최대 일간 변동(약 ±17%)이 모두 이 아래에 있어
# 정상적인 급변동을 오탐하지 않는다.
#
# **주식·ETF 의 값이다.** 정상 변동 폭이 다른 자산군은 자기 값을 인자로 넘기고, 그 값은 그 자산군의
# 수집 계층이 소유한다(비트코인은 `data/crypto_common.py`) — 여기 올리면 한 자산군의 값이
# 모든 시세의 판정 기준이 된다
MAX_DAILY_CHANGE_RATE = 0.50


def validate_market_data(df: pd.DataFrame, *, max_daily_change_rate: float = MAX_DAILY_CHANGE_RATE) -> None:
    """시세 DataFrame 의 이상 여부를 검사한다.

    가격과 거래량의 결측 · 무한대, 0 이하 가격, 음수 거래량, 비정상 급등락을 검사하며, 어떤 형태의 보간도 하지 않는다.
    수집기와 로더가 이 함수를 함께 쓴다 — 판정이 두 곳으로 갈라지면
    "수집은 통과했는데 로딩에서 막히는" 데이터가 생긴다. **임계값을 넘기는 자산군은
    수집기와 로더 양쪽에 같은 값을 넘긴다.**

    Args:
        df: 검사할 시세 DataFrame (필수 컬럼이 이미 존재한다고 전제)
        max_daily_change_rate: 데이터 오류로 볼 일간 변동 임계 (비율, 0.50 = 50%)

    Raises:
        ValueError: 임계값이 유한한 양수가 아니거나, 결측 · 무한대 · 0 이하 가격 · 음수 거래량 · 임계를 넘는 일간 변동이
            발견된 경우
    """
    # 0 이하면 모든 변동이 오류가 되어 정상 시세가 전부 막히고, NaN · 무한대면 어떤 비교도 참이 되지 않아
    # 아무것도 막지 않는다 — 어느 쪽이든 판정이 뜻을 잃는다. `<= 0` 만 보면 NaN 이 그 비교마저 거짓으로 빠져나간다
    if not (math.isfinite(max_daily_change_rate) and max_daily_change_rate > 0):
        raise ValueError(f"일간 변동 임계는 유한한 양수여야 합니다: {max_daily_change_rate}")

    if df.empty:
        raise ValueError("시세 데이터가 비어 있습니다")

    value_columns = [*PRICE_COLUMNS, COL_VOLUME]

    # 1. 결측 검사
    for column in value_columns:
        missing = df[column].isna()
        if missing.any():
            dates = df.loc[missing, COL_DATE].head().tolist()
            raise ValueError(f"결측 값 발견 - 컬럼: {column}, 건수: {int(missing.sum())}, 예시 날짜: {dates}")

    # 2. 무한대 검사. 0 이하 검사는 양의 무한대를 지나보내고 일간 변동 검사는 종가만 보므로 따로 막는다.
    #    0 이하 검사보다 먼저 두어 음의 무한대를 「0 이하」가 아니라 무한대로 알린다
    for column in value_columns:
        infinite = df[column].isin([math.inf, -math.inf])
        if infinite.any():
            dates = df.loc[infinite, COL_DATE].head().tolist()
            raise ValueError(f"무한대 값 발견 - 컬럼: {column}, 건수: {int(infinite.sum())}, 예시 날짜: {dates}")

    # 3. 0 이하 가격 검사. 가격이 0이 되는 것은 거래정지나 수집 오류이며 시장가가 아니다
    for column in PRICE_COLUMNS:
        non_positive = df[column] <= 0
        if non_positive.any():
            dates = df.loc[non_positive, COL_DATE].head().tolist()
            raise ValueError(f"0 이하 가격 발견 - 컬럼: {column}, 건수: {int(non_positive.sum())}, 예시 날짜: {dates}")

    # 4. 음수 거래량 검사. 0 은 막지 않는다 — 거래가 없던 날이 실제 시세에 있다(비트코인 초기 · 인버스 ETF)
    negative_volume = df[COL_VOLUME] < 0
    if negative_volume.any():
        dates = df.loc[negative_volume, COL_DATE].head().tolist()
        raise ValueError(f"음수 거래량 발견 - 컬럼: {COL_VOLUME}, 건수: {int(negative_volume.sum())}, 예시 날짜: {dates}")

    # 5. 일간 변동 검사. 첫 행은 직전 값이 없어 NaN 이므로 검사 대상에서 빠진다
    change_rate = df[COL_CLOSE].pct_change()
    extreme = change_rate.abs() > max_daily_change_rate

    if extreme.any():
        first_index = df.index[extreme][0]
        raise ValueError(
            f"비정상 급등락 발견 (임계: {max_daily_change_rate:.0%}) - "
            f"날짜: {df.loc[first_index, COL_DATE]}, "
            f"변동률: {change_rate[first_index]:+.2%}, 건수: {int(extreme.sum())}"
        )


def validate_market_frame(df: pd.DataFrame, required_columns: Sequence[str]) -> None:
    """시세 DataFrame 이 위치 기반 계산의 전제를 만족하는지 확인한다.

    값의 이상은 `validate_market_data` 가 본다. 이 함수는 **구조만** 본다 —
    비었는가, 필요한 컬럼이 있는가, 날짜가 오름차순인가.

    측정 계층은 넘겨받은 DataFrame 의 출처를 알 수 없으므로 계산 전에 이 검사를 지난다.
    날짜가 뒤섞이면 이동평균과 forward return 이 예외 없이 조용히 어긋난다.

    Args:
        df: 검사할 시세 DataFrame
        required_columns: 호출자가 실제로 쓰는 컬럼 목록

    Raises:
        ValueError: 비었거나, 필요한 컬럼이 없거나, 날짜가 오름차순이 아닌 경우
    """
    if df.empty:
        raise ValueError("시세 데이터가 비어 있습니다")

    missing_columns = set(required_columns) - set(df.columns)
    if missing_columns:
        raise ValueError(f"필수 컬럼이 누락되었습니다: {sorted(missing_columns)}")

    if not df[COL_DATE].is_monotonic_increasing:
        raise ValueError("시세가 날짜 오름차순이 아닙니다")


def load_market_csv(path: Path, *, max_daily_change_rate: float = MAX_DAILY_CHANGE_RATE) -> pd.DataFrame:
    """시세 CSV 를 읽어 검증된 DataFrame 으로 돌려준다.

    파일 존재 확인 → 필수 컬럼 검증 → 날짜 파싱 → 시간순 정렬 → 중복 제거 → 이상치 검사
    순으로 수행한다. 원본 파일은 읽기만 하며 수정하지 않는다.

    Args:
        path: 시세 CSV 경로
        max_daily_change_rate: 데이터 오류로 볼 일간 변동 임계 (비율). **그 파일을 저장한 수집기가
            넘긴 값과 같아야 한다** — 다르면 저장은 됐는데 읽을 때 막힌다

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
    validate_market_data(df, max_daily_change_rate=max_daily_change_rate)

    logger.debug(f"시세 로딩 완료: {len(df):,}행, 기간 {df[COL_DATE].min().date()} ~ {df[COL_DATE].max().date()}")

    return df


def validate_series_data(df: pd.DataFrame) -> None:
    """일별 단일 값 시계열의 이상 여부를 검사한다.

    **값의 부호와 변동폭은 보지 않는다.** 마이너스 금리와 0% 금리는 실제로 존재하고,
    원달러는 하루에 20% 넘게 움직인 날이 있다. 시세의 판정을 그대로 걸면 정상 데이터가 막힌다.
    소스마다 다른 값의 타당 범위는 각 수집기가 자기 도메인 지식으로 검사한다.

    수집기와 로더가 이 함수를 함께 쓴다 — 판정이 두 곳으로 갈라지면
    "수집은 통과했는데 로딩에서 막히는" 데이터가 생긴다.

    Args:
        df: 검사할 시계열 DataFrame (필수 컬럼이 이미 존재한다고 전제)

    Raises:
        ValueError: 비어 있거나 결측이 발견된 경우
    """
    if df.empty:
        raise ValueError("시계열 데이터가 비어 있습니다")

    missing = df[COL_VALUE].isna()
    if missing.any():
        dates = df.loc[missing, COL_DATE].head().tolist()
        raise ValueError(f"결측 값 발견 - 컬럼: {COL_VALUE}, 건수: {int(missing.sum())}, 예시 날짜: {dates}")


def load_series_csv(path: Path) -> pd.DataFrame:
    """일별 단일 값 시계열 CSV 를 읽어 검증된 DataFrame 으로 돌려준다.

    처리 순서는 `load_market_csv` 와 같다. 파일 존재 확인 → 필수 컬럼 검증 → 날짜 파싱 →
    시간순 정렬 → 중복 제거 → 이상치 검사. 원본 파일은 읽기만 하며 수정하지 않는다.

    Args:
        path: 시계열 CSV 경로

    Returns:
        날짜 오름차순으로 정렬되고 인덱스가 0부터 다시 매겨진 DataFrame.
        날짜 컬럼의 dtype 은 `datetime64[ns]` 다

    Raises:
        FileNotFoundError: 파일이 없는 경우
        ValueError: 필수 컬럼 누락, 빈 데이터, 결측이 발견된 경우
    """
    if not path.is_file():
        raise FileNotFoundError(f"시계열 파일을 찾을 수 없습니다: {path}")

    df = pd.read_csv(path)

    # 1. 스키마 검증. 컬럼이 다르면 이후 판정이 전부 어긋나므로 가장 먼저 막는다
    missing_columns = set(SERIES_REQUIRED_COLUMNS) - set(df.columns)
    if missing_columns:
        raise ValueError(f"필수 컬럼이 누락되었습니다: {sorted(missing_columns)} (파일: {path})")

    # 2. 날짜 파싱. 시세와 날짜 기준으로 정렬해 쓰므로 datetime64 를 유지한다
    df[COL_DATE] = pd.to_datetime(df[COL_DATE])

    # 3. 시간순 정렬
    df = df.sort_values(COL_DATE).reset_index(drop=True)

    # 4. 중복 날짜 제거. 몇 건이 왜 빠졌는지 남겨 표본이 조용히 사라지지 않게 한다
    duplicate_count = int(df.duplicated(subset=[COL_DATE]).sum())
    if duplicate_count > 0:
        logger.warning(f"중복 날짜 {duplicate_count}건을 제거했습니다 (파일: {path})")
        df = df.drop_duplicates(subset=[COL_DATE], keep="first").reset_index(drop=True)

    # 5. 이상치 검사. 통과한 데이터만 호출자에게 넘긴다
    validate_series_data(df)

    logger.debug(f"시계열 로딩 완료: {len(df):,}행, 기간 {df[COL_DATE].min().date()} ~ {df[COL_DATE].max().date()}")

    return df
