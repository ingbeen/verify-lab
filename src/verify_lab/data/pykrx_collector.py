"""pykrx 국내 시세 수집

국내 상장 ETF 의 일별 시세를 받아 `storage/market/` 에 원시 시세로 남긴다.

**같은 종목을 두 가지 가격 기준으로 받는다.** KRX 는 수정주가를 조회 시점 기준 최근 3,000거래일만
제공하므로(`docs/spec/index_extreme_events.md` §8 결론 4), 상장일부터의 전 기간은 원본가로만 얻을 수 있다.
확장창 순위처럼 상장일부터 쌓아야 하는 측정은 원본가 계열로만 가능하고, 수정주가 계열은
겹치는 구간에서 "가격 기준을 바꾸면 결론이 바뀌는가"를 대조하는 데 쓴다(스펙 §7 결정 ⑨).
**가격 기준이 다르면 내용이 다른 데이터이므로 파일을 나눈다.**

pykrx 는 KRX 웹을 감싼 라이브러리라 반환 컬럼과 dtype 이 함수마다 다르다. 그래서
**한글 컬럼을 이 계층에서 공통 스키마로 정규화하고, 정수 dtype 을 부호 있는 정수로 고정한다.**
정규화를 로딩 시점으로 미루면 로더가 파일의 출처를 알아야 하고 소스가 늘 때마다 분기가 늘어난다.

이상치 판정은 `loader.validate_market_data()` 를 그대로 재사용한다. 수집기가 자기 판정을
따로 두면 "수집은 통과했는데 로딩에서 막히는" 데이터가 생긴다.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from verify_lab.common_constants import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_VOLUME,
    MARKET_DIR,
    PRICE_COLUMNS,
    REQUIRED_COLUMNS,
)
from verify_lab.data.krx_credentials import load_krx_credentials
from verify_lab.data.loader import validate_market_data
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# pykrx 가 돌려주는 한글 컬럼 → 공통 스키마. 두 조회 함수가 함께 주는 컬럼만 담는다.
# `NAV`·`거래대금`·`기초지수`·`등락률` 은 공통 스키마에 없으므로 저장하지 않는다
KRX_COLUMN_MAP = {
    "시가": COL_OPEN,
    "고가": COL_HIGH,
    "저가": COL_LOW,
    "종가": COL_CLOSE,
    "거래량": COL_VOLUME,
}

# 반환값의 날짜 인덱스에 붙일 이름. pykrx 는 `날짜` 를 쓰지만 이름에 의존하지 않고 덮어쓴다
KRX_INDEX_NAME = "날짜"

# 조회 시작일 형식. pykrx 가 요구하는 표기다
KRX_DATE_FORMAT = "%Y%m%d"

# 저장에서 제외할 최근 구간 (달력일). 국내는 시차가 없어 전일 종가는 확정이지만,
# **장중에도 당일 행이 그대로 반환되는 것이 실측**됐다. 미확정 종가가 남으면 그날이 극단 이벤트로 잡힌다
RECENT_EXCLUSION_DAYS = 1

# 저장 직전 정수화 대상. KRX 원화 가격과 거래량은 정수이며 반올림 규칙도 0자리다.
# **부호 있는 int64 로 고정한다** — `get_etf_ohlcv_by_date` 는 가격을 `uint32` 로 주는데,
# 부호 없는 정수는 차분에서 언더플로우가 나서 하락일이 40억 근처의 거대한 양수가 된다
INTEGER_COLUMNS = [*PRICE_COLUMNS, COL_VOLUME]

# 가격 기준별 저장 파일명. 기간은 파일명에 넣지 않고(항상 받을 수 있는 전 기간을 받는다),
# 가격 기준만 구분한다
FILE_NAME_TEMPLATE = "{ticker}_max.csv"
ADJUSTED_FILE_NAME_TEMPLATE = "{ticker}_adjusted_max.csv"


@dataclass(frozen=True)
class PykrxCollectionResult:
    """수집 결과 요약.

    Attributes:
        ticker: 조회한 종목
        adjusted: 수정주가 기준이면 True, 원본가 기준이면 False
        path: 저장된 CSV 경로
        row_count: 저장된 행 수
        start_date: 저장 구간의 첫 거래일
        end_date: 저장 구간의 마지막 거래일
        excluded_recent_count: 최근 구간 제외로 빠진 행 수
    """

    ticker: str
    adjusted: bool
    path: Path
    row_count: int
    start_date: date
    end_date: date
    excluded_recent_count: int


def _import_pykrx_stock() -> Any:
    """자격증명을 환경 변수에 올린 뒤 pykrx 를 import 한다.

    **`import pykrx` 자체가 로그인을 시도한다.** 모듈 최상단에서 import 하면 자격증명이
    올라가기 전에 로그인이 시도되므로, 순서를 지키는 유일한 방법은 import 를 이 함수 안에 두는 것이다.
    최상단 import 는 순서를 구조로 보장하지 못한다 — 누군가 줄을 옮기면 조용히 깨진다.

    Returns:
        pykrx 의 `stock` 모듈
    """
    load_krx_credentials()

    from pykrx import stock

    return stock


def _fetch_ohlcv(ticker: str, start_date: str, end_date: str, adjusted: bool) -> pd.DataFrame:
    """가격 기준에 맞는 조회 함수를 부른다.

    두 기준은 **서로 다른 함수**를 쓴다. ETF 는 주식 ISIN 목록에 없어 원본가 경로
    (`get_market_ohlcv(adjusted=False)`)가 아예 동작하지 않기 때문이다(스펙 §8).

    Args:
        ticker: 종목 티커
        start_date: 조회 시작일 (YYYYMMDD)
        end_date: 조회 종료일 (YYYYMMDD)
        adjusted: 수정주가로 받을지 여부

    Returns:
        pykrx 반환값 그대로의 DataFrame
    """
    stock = _import_pykrx_stock()

    if adjusted:
        # `adjusted` 는 이 호출의 존재 이유이므로 기본값에 맡기지 않고 명시적으로 넘긴다
        return stock.get_market_ohlcv(start_date, end_date, ticker, adjusted=True)

    return stock.get_etf_ohlcv_by_date(start_date, end_date, ticker)


def _normalize(raw: pd.DataFrame) -> pd.DataFrame:
    """pykrx 반환값을 공통 스키마로 정규화한다.

    한글 컬럼을 영문 토큰으로 바꾸고, 날짜를 인덱스에서 컬럼으로 꺼내고, 숫자 컬럼을
    부호 있는 값으로 바꾼다. 공통 스키마에 없는 컬럼은 버린다.

    Args:
        raw: pykrx 반환값

    Returns:
        `REQUIRED_COLUMNS` 구성과 순서를 갖춘 DataFrame

    Raises:
        ValueError: 필요한 한글 컬럼이 없는 경우
    """
    missing_columns = set(KRX_COLUMN_MAP) - set(raw.columns)
    if missing_columns:
        raise ValueError(f"필수 컬럼이 누락되었습니다: {sorted(missing_columns)} (반환 컬럼: {list(raw.columns)})")

    df = raw.rename_axis(KRX_INDEX_NAME).reset_index()
    df = df.rename(columns={KRX_INDEX_NAME: COL_DATE, **KRX_COLUMN_MAP})

    # 부호 없는 정수를 그대로 두면 뒤따르는 차분에서 언더플로우가 난다. 예외가 아니라
    # 그럴듯한 큰 양수로 나타나므로 눈으로는 발견되지 않는다
    df[INTEGER_COLUMNS] = df[INTEGER_COLUMNS].astype(float)

    # 이미 저장된 원시 시세가 쓰는 날짜 표기에 맞춘다
    df[COL_DATE] = pd.to_datetime(df[COL_DATE]).dt.date

    return df[REQUIRED_COLUMNS]


def collect_pykrx_history(
    ticker: str,
    start_date: str,
    adjusted: bool,
    output_dir: Path = MARKET_DIR,
) -> PykrxCollectionResult:
    """pykrx 에서 일별 시세를 받아 원시 시세 파일로 저장한다.

    조회 → 스키마 정규화 → 최근 구간 제외 → 정수화 → 이상치 검증 → 저장 순으로 수행하며,
    **검증을 통과한 데이터만 저장한다.** 검증에서 걸리면 파일을 만들지 않고 예외를 던진다.

    받을 수 있는 만큼 전부 받는다. 다만 **수정주가는 KRX 가 최근 3,000거래일만 제공**하므로
    `adjusted=True` 로 받은 결과는 `start_date` 보다 늦게 시작하는 것이 정상이다.

    Args:
        ticker: 종목 티커 (앞뒤 공백 무관)
        start_date: 조회 시작일 (YYYYMMDD). 보통 종목의 상장일을 넣는다
        adjusted: 수정주가로 받을지 여부. 파일명이 기준에 따라 갈린다
        output_dir: 저장 디렉터리. 기본값은 원시 시세 폴더

    Returns:
        저장 결과 요약. 최근 구간 제외로 빠진 행 수를 함께 담는다

    Raises:
        ValueError: 종목 코드가 비었거나, 시작일 형식이 잘못됐거나, 조회 결과가 비었거나,
            필수 컬럼이 없거나, 최근 구간 제외 후 남는 행이 없거나, 이상치가 발견된 경우
    """
    symbol = ticker.strip().upper()
    if not symbol:
        raise ValueError("종목 코드가 비어 있습니다")

    try:
        datetime.strptime(start_date, KRX_DATE_FORMAT)
    except ValueError as error:
        raise ValueError(f"조회 시작일 형식이 잘못되었습니다 (YYYYMMDD 여야 합니다): {start_date}") from error

    today = date.today()

    # 1. 조회. 종료일을 오늘로 두고 확정되지 않은 행은 뒤에서 세어 빼낸다.
    #    애초에 어제까지만 요청하면 몇 건이 빠졌는지 셀 수 없다 (표본 보존)
    raw = _fetch_ohlcv(symbol, start_date, today.strftime(KRX_DATE_FORMAT), adjusted)

    if raw.empty:
        raise ValueError(f"수집 결과가 비어 있습니다 - 종목: {symbol}, 수정주가: {adjusted}")

    # 2. 공통 스키마로 정규화
    df = _normalize(raw)

    # 3. 확정되지 않은 최근 구간을 제외한다. 몇 건이 빠졌는지 호출자에게 함께 돌려준다
    cutoff_date = today - timedelta(days=RECENT_EXCLUSION_DAYS)
    total_count = len(df)
    df = df.loc[df[COL_DATE] <= cutoff_date].reset_index(drop=True)
    excluded_recent_count = total_count - len(df)

    if df.empty:
        raise ValueError(f"최근 {RECENT_EXCLUSION_DAYS}일 제외 후 남는 데이터가 없습니다 - 종목: {symbol}")

    # 4. 저장 직전 정수화. KRX 원화 가격과 거래량은 정수이며, 이후 차분이 안전하도록
    #    부호 있는 int64 로 고정한다
    df[INTEGER_COLUMNS] = df[INTEGER_COLUMNS].round(0).astype("int64")

    # 5. 이상치 검증. 로더와 같은 함수를 써서 판정이 갈라지지 않게 한다
    validate_market_data(df)

    # 6. 저장. 검증을 통과한 뒤에만 실행한다
    output_dir.mkdir(parents=True, exist_ok=True)
    template = ADJUSTED_FILE_NAME_TEMPLATE if adjusted else FILE_NAME_TEMPLATE
    path = output_dir / template.format(ticker=symbol)
    df.to_csv(path, index=False)

    first_date = df[COL_DATE].iloc[0]
    last_date = df[COL_DATE].iloc[-1]

    logger.debug(f"수집 완료: {symbol}, 수정주가={adjusted}, {len(df):,}행, 기간 {first_date} ~ {last_date}, 저장 위치 {path}")
    if excluded_recent_count > 0:
        logger.debug(f"최근 {RECENT_EXCLUSION_DAYS}일 데이터 {excluded_recent_count}행을 제외했습니다")

    return PykrxCollectionResult(
        ticker=symbol,
        adjusted=adjusted,
        path=path,
        row_count=len(df),
        start_date=first_date,
        end_date=last_date,
        excluded_recent_count=excluded_recent_count,
    )
