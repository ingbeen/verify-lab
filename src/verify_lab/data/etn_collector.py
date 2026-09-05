"""KRX ETN 시세 수집

국내 상장 ETN 의 일별 시세를 받아 `storage/market/` 에 원시 시세로 남긴다.

**pykrx 는 ETN 에 시세 함수를 주지 않는다.** `get_etn_ticker_list` 와 `get_etn_ticker_name`
둘뿐이고, ETF 용 `get_etf_ohlcv_by_date` 나 주식용 `get_market_ohlcv` 에 ETN 코드를 넣으면
예외 없이 **빈 결과**가 돌아온다. 그래서 이 모듈은 pykrx 의 KRX 클라이언트(`KrxWebIo`)만
재사용하고 통계 코드를 직접 지정한다.

| 통계 코드 | 내용 | 받는 인자 |
| --- | --- | --- |
| `MDCSTAT06701` | ETN 전종목 기본종목 (상장일·만기일·기초지수·제비용) | 없음 |
| `MDCSTAT06601` | ETN 개별종목 시세 추이 | `isuCd`(ISIN)·`strtDd`·`endDd` |

ETN 은 ETF 와 달리 NAV 가 아니라 **증권당 지표가치(Indicative Value)** 를 쓴다.
지표가치는 시세가 아니라 하루에 값 하나짜리 계열이므로 `storage/series/` 에 따로 저장한다.

**티커가 아니라 ISIN 으로 조회한다.** 종목 코드(6자리)를 ISIN 으로 바꾸는 표는 기본종목
조회가 준다. 이 변환을 건너뛰면 빈 결과가 돌아오고 예외가 나지 않는다.

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
    COL_VALUE,
    COL_VOLUME,
    MARKET_DIR,
    MARKET_FILE_TEMPLATE,
    PRICE_COLUMNS,
    REQUIRED_COLUMNS,
    SERIES_DIR,
)
from verify_lab.data.krx_credentials import load_krx_credentials
from verify_lab.data.loader import validate_market_data, validate_series_data
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# KRX 가 돌려주는 컬럼 → 공통 스키마. 거래대금·시가총액·기초지수는 공통 스키마에 없어 저장하지 않는다
ETN_COLUMN_MAP = {
    "TDD_OPNPRC": COL_OPEN,
    "TDD_HGPRC": COL_HIGH,
    "TDD_LWPRC": COL_LOW,
    "TDD_CLSPRC": COL_CLOSE,
    "ACC_TRDVOL": COL_VOLUME,
}

# KRX 응답의 날짜 컬럼과 그 표기
ETN_DATE_COLUMN = "TRD_DD"
ETN_RESPONSE_DATE_FORMAT = "%Y/%m/%d"

# 증권당 지표가치 컬럼. ETF 의 NAV 에 해당한다
ETN_INDICATIVE_VALUE_COLUMN = "PER1SECU_INDIC_VAL"

# 기본종목 조회가 주는 컬럼 — 종목 코드와 ISIN
ETN_BASIC_TICKER_COLUMN = "ISU_SRT_CD"
ETN_BASIC_ISIN_COLUMN = "ISU_CD"

# KRX 통계 코드
BLD_ETN_DAILY_PRICE = "dbms/MDC/STAT/standard/MDCSTAT06601"

# 조회 인자의 날짜 형식
KRX_DATE_FORMAT = "%Y%m%d"

# 저장에서 제외할 최근 구간 (달력일). 국내는 시차가 없어 전일 종가는 확정이지만
# 장중에도 당일 행이 반환되므로 당일은 반드시 뺀다. `pykrx_collector` 와 같은 기준이다
RECENT_EXCLUSION_DAYS = 1

# 저장 직전 정수화 대상. KRX 원화 가격과 거래량은 정수다
INTEGER_COLUMNS = [*PRICE_COLUMNS, COL_VOLUME]

# 지표가치 저장 파일명. **이 파일에서만 쓰므로 여기 둔다** — 시세 파일명과 달리
# 아직 읽는 계층이 없다 (`src/verify_lab/CLAUDE.md` 「상수 관리」)
INDICATIVE_VALUE_FILE_NAME_TEMPLATE = "{ticker}_IV.csv"

# 지표가치 저장 자릿수. 호가가 아니라 계산된 값이라 소스가 소수 둘째 자리까지 준다.
# `pykrx_collector` 의 NAV 와 같은 이유로 정수 반올림하지 않는다
INDICATIVE_VALUE_DECIMALS = 2


@dataclass(frozen=True)
class EtnCollectionResult:
    """ETN 시세 수집 결과 요약.

    Attributes:
        ticker: 조회한 종목 코드
        isin: 조회에 쓴 ISIN
        path: 저장된 CSV 경로
        row_count: 저장된 행 수
        start_date: 저장 구간의 첫 거래일
        end_date: 저장 구간의 마지막 거래일
        excluded_recent_count: 최근 구간 제외로 빠진 행 수
    """

    ticker: str
    isin: str
    path: Path
    row_count: int
    start_date: date
    end_date: date
    excluded_recent_count: int


@dataclass(frozen=True)
class EtnIndicativeValueResult:
    """ETN 지표가치 수집 결과 요약.

    Attributes:
        ticker: 조회한 종목 코드
        path: 저장된 CSV 경로
        row_count: 저장된 행 수
        start_date: 저장 구간의 첫 거래일
        end_date: 저장 구간의 마지막 거래일
        excluded_recent_count: 최근 구간 제외로 빠진 행 수
    """

    ticker: str
    path: Path
    row_count: int
    start_date: date
    end_date: date
    excluded_recent_count: int


def _import_krx_client() -> tuple[Any, Any]:
    """자격증명을 환경 변수에 올린 뒤 pykrx 의 KRX 클라이언트를 가져온다.

    **`import pykrx` 자체가 로그인을 시도한다.** 모듈 최상단에서 import 하면 자격증명이
    올라가기 전에 로그인이 시도되므로, 순서를 지키는 유일한 방법은 import 를 이 함수 안에
    두는 것이다. `pykrx_collector` 와 같은 이유다.

    Returns:
        (ETN 전종목기본종목 클래스, KrxWebIo 기반 클래스) 짝
    """
    load_krx_credentials()

    from pykrx.website.krx.etx.core import ETN_전종목기본종목
    from pykrx.website.krx.krxio import KrxWebIo

    return ETN_전종목기본종목, KrxWebIo


def _resolve_isin(ticker: str) -> str:
    """종목 코드를 ISIN 으로 바꾼다.

    시세 조회가 ISIN 을 요구한다. 종목 코드를 그대로 넣으면 **예외 없이 빈 결과**가
    돌아오므로, 여기서 못 찾으면 조회로 넘어가지 않고 바로 예외를 던진다.

    Args:
        ticker: 종목 코드 (6자리)

    Returns:
        해당 종목의 ISIN

    Raises:
        ValueError: 상장 ETN 목록에 없는 종목 코드인 경우
    """
    basic_class, _ = _import_krx_client()
    basic = basic_class().fetch()

    matched = basic.loc[basic[ETN_BASIC_TICKER_COLUMN] == ticker, ETN_BASIC_ISIN_COLUMN]
    if matched.empty:
        raise ValueError(f"상장 ETN 목록에서 종목을 찾지 못했습니다 - 종목: {ticker}")

    return str(matched.iloc[0])


def _fetch_daily_price(isin: str, start_date: str, end_date: str) -> pd.DataFrame:
    """ETN 개별종목 시세 추이를 조회한다.

    pykrx 가 감싸지 않은 통계라 클라이언트만 재사용하고 통계 코드를 직접 지정한다.
    조회 구간이 2년을 넘으면 `KrxWebIo` 가 알아서 나눠 부르고 이어붙인다.

    Args:
        isin: 조회할 종목의 ISIN
        start_date: 조회 시작일 (YYYYMMDD)
        end_date: 조회 종료일 (YYYYMMDD)

    Returns:
        KRX 반환값 그대로의 DataFrame
    """
    _, web_io_class = _import_krx_client()

    class ETN개별종목시세(web_io_class):  # type: ignore[misc, valid-type]
        @property
        def bld(self) -> str:
            return BLD_ETN_DAILY_PRICE

        def fetch(self, strtDd: str, endDd: str, isuCd: str) -> pd.DataFrame:  # noqa: N803
            return pd.DataFrame(self.read(isuCd=isuCd, strtDd=strtDd, endDd=endDd)["output"])

    return ETN개별종목시세().fetch(start_date, end_date, isin)


def _to_numeric(series: pd.Series) -> pd.Series:
    """KRX 가 문자열로 주는 숫자를 실수로 바꾼다.

    천 단위 구분 쉼표가 붙어 있고, 값이 없는 칸은 `-` 로 온다. 쉼표만 떼고 숫자로 바꾸며
    **`-` 는 결측으로 남긴다** — 0 으로 채우면 가격이 0인 날이 생겨 이상치 검사를 통과해 버린다.

    Args:
        series: KRX 반환값의 한 컬럼

    Returns:
        실수 Series. 변환할 수 없는 칸은 NaN
    """
    return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False), errors="coerce")


def _normalize(raw: pd.DataFrame) -> pd.DataFrame:
    """KRX 반환값을 공통 시세 스키마로 정규화한다.

    KRX 는 **최신 날짜를 먼저** 주므로 오름차순으로 다시 정렬한다. 정렬하지 않으면
    로더의 오름차순 검사에서 막힌다.

    Args:
        raw: KRX 반환값

    Returns:
        `REQUIRED_COLUMNS` 구성과 순서를 갖춘 DataFrame (날짜 오름차순)

    Raises:
        ValueError: 필요한 컬럼이 없는 경우
    """
    required_source_columns = {ETN_DATE_COLUMN, *ETN_COLUMN_MAP}
    missing_columns = required_source_columns - set(raw.columns)
    if missing_columns:
        raise ValueError(f"필수 컬럼이 누락되었습니다: {sorted(missing_columns)} (반환 컬럼: {list(raw.columns)})")

    df = raw.rename(columns={ETN_DATE_COLUMN: COL_DATE, **ETN_COLUMN_MAP})

    for column in INTEGER_COLUMNS:
        df[column] = _to_numeric(df[column])

    df[COL_DATE] = pd.to_datetime(df[COL_DATE], format=ETN_RESPONSE_DATE_FORMAT).dt.date

    return df.sort_values(COL_DATE).reset_index(drop=True)[REQUIRED_COLUMNS]


def _exclude_recent(df: pd.DataFrame, today: date) -> tuple[pd.DataFrame, int]:
    """확정되지 않은 최근 구간을 제외하고 빠진 행 수를 함께 돌려준다.

    Args:
        df: 날짜 컬럼을 가진 DataFrame
        today: 기준일

    Returns:
        (제외 후 DataFrame, 제외된 행 수)
    """
    cutoff_date = today - timedelta(days=RECENT_EXCLUSION_DAYS)
    total_count = len(df)
    trimmed = df.loc[df[COL_DATE] <= cutoff_date].reset_index(drop=True)

    return trimmed, total_count - len(trimmed)


def _validated_start_date(start_date: str) -> None:
    """조회 시작일 형식을 검증한다.

    Args:
        start_date: 조회 시작일 (YYYYMMDD)

    Raises:
        ValueError: 형식이 잘못된 경우
    """
    try:
        datetime.strptime(start_date, KRX_DATE_FORMAT)
    except ValueError as error:
        raise ValueError(f"조회 시작일 형식이 잘못되었습니다 (YYYYMMDD 여야 합니다): {start_date}") from error


def collect_etn_history(
    ticker: str,
    start_date: str,
    output_dir: Path = MARKET_DIR,
) -> EtnCollectionResult:
    """KRX 에서 ETN 일별 시세를 받아 원시 시세 파일로 저장한다.

    ISIN 변환 → 조회 → 스키마 정규화 → 최근 구간 제외 → 정수화 → 이상치 검증 → 저장
    순으로 수행하며, **검증을 통과한 데이터만 저장한다.** 검증에서 걸리면 파일을 만들지 않고
    예외를 던진다.

    ETN 은 수정주가 개념이 없다. 분배금을 지급하지 않고 지표가치에서 제비용만 차감하므로
    가격 기준이 하나뿐이며, `pykrx_collector` 의 `adjusted` 같은 인자가 없다.

    Args:
        ticker: 종목 코드 (앞뒤 공백 무관)
        start_date: 조회 시작일 (YYYYMMDD). 보통 종목의 상장일을 넣는다
        output_dir: 저장 디렉터리. 기본값은 원시 시세 폴더

    Returns:
        저장 결과 요약. 최근 구간 제외로 빠진 행 수를 함께 담는다

    Raises:
        ValueError: 종목 코드가 비었거나, 시작일 형식이 잘못됐거나, 상장 목록에 없거나,
            조회 결과가 비었거나, 필수 컬럼이 없거나, 최근 구간 제외 후 남는 행이 없거나,
            이상치가 발견된 경우
    """
    symbol = ticker.strip()
    if not symbol:
        raise ValueError("종목 코드가 비어 있습니다")

    _validated_start_date(start_date)

    today = date.today()

    # 1. 종목 코드를 ISIN 으로 바꾼다. 시세 조회가 ISIN 만 받는다
    isin = _resolve_isin(symbol)

    # 2. 조회. 종료일을 오늘로 두고 확정되지 않은 행은 뒤에서 세어 빼낸다 (표본 보존)
    raw = _fetch_daily_price(isin, start_date, today.strftime(KRX_DATE_FORMAT))

    if raw.empty:
        raise ValueError(f"수집 결과가 비어 있습니다 - 종목: {symbol}, ISIN: {isin}")

    # 3. 공통 스키마로 정규화
    df = _normalize(raw)

    # 4. 확정되지 않은 최근 구간을 제외한다
    df, excluded_recent_count = _exclude_recent(df, today)

    if df.empty:
        raise ValueError(f"최근 {RECENT_EXCLUSION_DAYS}일 제외 후 남는 데이터가 없습니다 - 종목: {symbol}")

    # 5. 저장 직전 정수화. KRX 원화 가격과 거래량은 정수다.
    #    결측이 남아 있으면 정수 변환에서 예외가 나므로 먼저 이상치 검증을 지난다
    validate_market_data(df)
    df[INTEGER_COLUMNS] = df[INTEGER_COLUMNS].round(0).astype("int64")

    # 6. 저장. 검증을 통과한 뒤에만 실행한다
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / MARKET_FILE_TEMPLATE.format(ticker=symbol)
    df.to_csv(path, index=False)

    first_date = df[COL_DATE].iloc[0]
    last_date = df[COL_DATE].iloc[-1]

    logger.debug(f"ETN 수집 완료: {symbol}, {len(df):,}행, 기간 {first_date} ~ {last_date}, 저장 위치 {path}")
    if excluded_recent_count > 0:
        logger.debug(f"최근 {RECENT_EXCLUSION_DAYS}일 데이터 {excluded_recent_count}행을 제외했습니다")

    return EtnCollectionResult(
        ticker=symbol,
        isin=isin,
        path=path,
        row_count=len(df),
        start_date=first_date,
        end_date=last_date,
        excluded_recent_count=excluded_recent_count,
    )


def collect_etn_indicative_value(
    ticker: str,
    start_date: str,
    output_dir: Path = SERIES_DIR,
) -> EtnIndicativeValueResult:
    """ETN 의 증권당 지표가치를 **일별 단일 값 시계열**로 저장한다.

    지표가치는 ETF 의 NAV 에 해당하며, 시장가와의 차이가 곧 유동성공급자 호가로 생기는
    괴리다. 시세가 아니라 하루에 값 하나짜리 계열이므로 `storage/series/` 에 저장한다.

    Args:
        ticker: 종목 코드 (앞뒤 공백 무관)
        start_date: 조회 시작일 (YYYYMMDD). 보통 종목의 상장일을 넣는다
        output_dir: 저장 디렉터리. 기본값은 단일 값 시계열 폴더

    Returns:
        저장 결과 요약

    Raises:
        ValueError: 종목 코드가 비었거나, 시작일 형식이 잘못됐거나, 상장 목록에 없거나,
            조회 결과가 비었거나, 지표가치 컬럼이 없거나, 최근 구간 제외 후 남는 행이 없거나,
            결측이 발견된 경우
    """
    symbol = ticker.strip()
    if not symbol:
        raise ValueError("종목 코드가 비어 있습니다")

    _validated_start_date(start_date)

    today = date.today()
    isin = _resolve_isin(symbol)
    raw = _fetch_daily_price(isin, start_date, today.strftime(KRX_DATE_FORMAT))

    if raw.empty:
        raise ValueError(f"지표가치 조회 결과가 비어 있습니다 - 종목: {symbol}, ISIN: {isin}")

    if ETN_INDICATIVE_VALUE_COLUMN not in raw.columns:
        raise ValueError(f"응답에 지표가치 컬럼이 없습니다 (반환 컬럼: {list(raw.columns)})")

    df = raw.rename(columns={ETN_DATE_COLUMN: COL_DATE, ETN_INDICATIVE_VALUE_COLUMN: COL_VALUE})
    df[COL_DATE] = pd.to_datetime(df[COL_DATE], format=ETN_RESPONSE_DATE_FORMAT).dt.date
    df[COL_VALUE] = _to_numeric(df[COL_VALUE]).round(INDICATIVE_VALUE_DECIMALS)
    df = df.sort_values(COL_DATE).reset_index(drop=True)[[COL_DATE, COL_VALUE]]

    df, excluded_recent_count = _exclude_recent(df, today)

    if df.empty:
        raise ValueError(f"최근 {RECENT_EXCLUSION_DAYS}일 제외 후 남는 지표가치가 없습니다 - 종목: {symbol}")

    # 단일 값 시계열의 판정을 그대로 쓴다. 로더와 갈라지면 읽을 수 없는 파일이 생긴다
    validate_series_data(df)

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / INDICATIVE_VALUE_FILE_NAME_TEMPLATE.format(ticker=symbol)
    df.to_csv(path, index=False)

    first_date = df[COL_DATE].iloc[0]
    last_date = df[COL_DATE].iloc[-1]

    logger.debug(f"ETN 지표가치 수집 완료: {symbol}, {len(df):,}행, 기간 {first_date} ~ {last_date}, 저장 위치 {path}")

    return EtnIndicativeValueResult(
        ticker=symbol,
        path=path,
        row_count=len(df),
        start_date=first_date,
        end_date=last_date,
        excluded_recent_count=excluded_recent_count,
    )
