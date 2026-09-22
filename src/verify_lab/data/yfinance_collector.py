"""yfinance 시세 수집

미국 상장 종목의 일별 시세를 받아 `storage/market/` 에 원시 시세로 남긴다.

yfinance 는 웹 API 를 감싼 라이브러리라 기본 인자와 반환 컬럼이 버전 사이에 조용히 바뀔 수 있다.
그래서 **가격 기준과 오류 전파를 기본값에 맡기지 않고 명시적으로 지정한다.**

**기본은 원본가(배당 미조정)다.** 사용자가 결과를 차트와 직접 대조하는 것이 이 프로젝트의 전제인데
(루트 `CLAUDE.md` 측정의 원칙 8), 보통의 차트는 배당 미포함이라 수정주가로 저장하면 종가가 어긋난다.
근거는 `docs/매매/역방향/설계.md` "가격 처리" 에 있다. 그 대신 분배락이 조정되지 않은 채
남으므로 **배당락일이 하루짜리 하락으로 잡힌다.** 이 왜곡은 신호군과 베이스라인에 똑같이 걸리므로
초과분 비교에는 거의 남지 않고 절대 수익률에만 남는다.

`auto_adjust` 의 라이브러리 기본값은 `True`(수정주가)라 **인자를 빠뜨리면 수정주가가 조용히 저장된다.**
파일은 정상으로 보이고 종가만 차트와 어긋나므로 눈으로는 발견되지 않는다.
`raise_errors` 가 어긋나면 조회 실패가 예외 대신 빈 결과로 돌아와 빈 파일이 저장된다.

이상치 판정은 `loader.validate_market_data()` 를 그대로 재사용한다. 수집기가 자기 판정을
따로 두면 "수집은 통과했는데 로딩에서 막히는" 데이터가 생긴다.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from verify_lab.common_constants import (
    ADJUSTED_FILE_TEMPLATE,
    COL_CLOSE,
    COL_DATE,
    COL_VALUE,
    INDEX_FILE_TEMPLATE,
    KST,
    MARKET_DIR,
    MARKET_FILE_TEMPLATE,
    PRICE_COLUMNS,
    PRICE_DECIMALS,
    REQUIRED_COLUMNS,
    SERIES_DIR,
)
from verify_lab.data.loader import validate_market_data, validate_series_data
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 저장에서 제외할 최근 구간 (달력일). 미국장은 한국 시각 기준으로 하루가 밀리고,
# 마감 직후 값은 확정값이 아니다. 미확정 종가를 그대로 남기면 그날이 극단 이벤트로 잡힐 수 있다.
#
# **국내(`data/constants.DOMESTIC_RECENT_EXCLUSION_DAYS`)보다 하루 많다** — 그 하루가 시차다.
# 여기 두는 것은 미국 수집기가 이 파일뿐이라서다 (`src/verify_lab/CLAUDE.md` 「상수 관리」)
RECENT_EXCLUSION_DAYS = 2

# yfinance 가 지수 심볼에 붙이는 접두 (`^GSPC`). **파일명에서는 뗀다** — 셸에서 이스케이프가
# 필요해 `grep`·`ls` 양쪽에서 성가시고, 원래 심볼은 `summary.json` 의 `datasets.ticker` 가 갖는다
INDEX_SYMBOL_PREFIX = "^"


@dataclass(frozen=True)
class CollectionResult:
    """수집 결과 요약.

    Attributes:
        ticker: 조회한 종목 (대문자로 정규화된 값)
        path: 저장된 CSV 경로
        row_count: 저장된 행 수
        start_date: 저장 구간의 첫 거래일
        end_date: 저장 구간의 마지막 거래일
        excluded_recent_count: 최근 구간 제외로 빠진 행 수
        adjusted: 수정주가 기준이면 True, 원본가 기준이면 False
    """

    ticker: str
    path: Path
    row_count: int
    start_date: date
    end_date: date
    excluded_recent_count: int
    adjusted: bool


def collect_yfinance_history(
    ticker: str,
    adjusted: bool = False,
    output_dir: Path = MARKET_DIR,
) -> CollectionResult:
    """yfinance 에서 전 기간 일별 시세를 받아 원시 시세 파일로 저장한다.

    조회 → 스키마 확인 → 최근 구간 제외 → 반올림 → 이상치 검증 → 저장 순으로 수행하며,
    **검증을 통과한 데이터만 저장한다.** 검증에서 걸리면 파일을 만들지 않고 예외를 던진다.

    기간을 잘라 저장하지 않는다. 원시 시세는 받을 수 있는 만큼 남기고, 분석 구간을 정하는 것은
    측정 계층의 몫이다.

    Args:
        ticker: yfinance 종목 코드 (대소문자·앞뒤 공백 무관)
        adjusted: 수정주가로 받을지 여부. **기본값은 원본가**이며, 근거는 모듈 docstring 참고
        output_dir: 저장 디렉터리. 기본값은 원시 시세 폴더

    Returns:
        저장 결과 요약. 최근 구간 제외로 빠진 행 수를 함께 담는다

    Raises:
        ValueError: 종목 코드가 비었거나, 조회 결과가 비었거나, 필수 컬럼이 없거나,
            최근 구간 제외 후 남는 행이 없거나, 이상치가 발견된 경우
    """
    symbol = ticker.strip().upper()
    if not symbol:
        raise ValueError("종목 코드가 비어 있습니다")

    # 1. 전 기간 조회. 결과를 좌우하는 인자는 기본값에 맡기지 않고 명시한다 (모듈 docstring 참고)
    raw = yf.Ticker(symbol).history(period="max", auto_adjust=adjusted, raise_errors=True)

    if raw.empty:
        raise ValueError(f"수집 결과가 비어 있습니다 - 종목: {symbol}")

    # 2. 날짜를 인덱스에서 컬럼으로 꺼낸다. 이후 스키마는 저장된 원시 시세와 같은 형태를 쓴다
    df = raw.reset_index()

    missing_columns = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing_columns:
        raise ValueError(f"필수 컬럼이 누락되었습니다: {sorted(missing_columns)} (종목: {symbol})")

    # 3. 거래소 타임존을 떼고 날짜만 남긴다. 이미 저장된 원시 시세가 쓰는 표기에 맞춘다
    df[COL_DATE] = pd.to_datetime(df[COL_DATE]).dt.date

    # 4. 확정되지 않은 최근 구간을 제외한다. 몇 건이 빠졌는지 호출자에게 함께 돌려준다
    cutoff_date = datetime.now(KST).date() - timedelta(days=RECENT_EXCLUSION_DAYS)
    total_count = len(df)
    df = df.loc[df[COL_DATE] <= cutoff_date, REQUIRED_COLUMNS].reset_index(drop=True)
    excluded_recent_count = total_count - len(df)

    if df.empty:
        raise ValueError(f"최근 {RECENT_EXCLUSION_DAYS}일 제외 후 남는 데이터가 없습니다 - 종목: {symbol}")

    # 5. 저장 직전 반올림. 내부 계산 정밀도가 아니라 파일에 적히는 자릿수를 맞추는 단계다
    df[PRICE_COLUMNS] = df[PRICE_COLUMNS].round(PRICE_DECIMALS)

    # 6. 이상치 검증. 로더와 같은 함수를 써서 판정이 갈라지지 않게 한다
    validate_market_data(df)

    # 7. 저장. 검증을 통과한 뒤에만 실행한다
    output_dir.mkdir(parents=True, exist_ok=True)
    template = ADJUSTED_FILE_TEMPLATE if adjusted else MARKET_FILE_TEMPLATE
    path = output_dir / template.format(ticker=symbol)
    df.to_csv(path, index=False)

    start_date = df[COL_DATE].iloc[0]
    end_date = df[COL_DATE].iloc[-1]

    logger.debug(f"수집 완료: {symbol}, 수정주가={adjusted}, {len(df):,}행, 기간 {start_date} ~ {end_date}, 저장 위치 {path}")
    if excluded_recent_count > 0:
        logger.debug(f"최근 {RECENT_EXCLUSION_DAYS}일 데이터 {excluded_recent_count}행을 제외했습니다")

    return CollectionResult(
        ticker=symbol,
        path=path,
        row_count=len(df),
        start_date=start_date,
        end_date=end_date,
        excluded_recent_count=excluded_recent_count,
        adjusted=adjusted,
    )


@dataclass(frozen=True)
class IndexCollectionResult:
    """지수 수집 결과 요약.

    Attributes:
        symbol: 조회한 yfinance 심볼 (`^GSPC`). 차트와 대조할 때 필요하다
        ticker: 파일명에 쓴 이름 (`GSPC`). 접두 `^` 를 뗀 값이다
        path: 저장된 CSV 경로
        row_count: 저장된 행 수
        start_date: 저장 구간의 첫 거래일
        end_date: 저장 구간의 마지막 거래일
        excluded_recent_count: 최근 구간 제외로 빠진 행 수
    """

    symbol: str
    ticker: str
    path: Path
    row_count: int
    start_date: date
    end_date: date
    excluded_recent_count: int


def collect_yfinance_index(symbol: str, output_dir: Path = SERIES_DIR) -> IndexCollectionResult:
    """미국 지수를 **종가 하나짜리 계열**로 받아 `storage/series/` 에 저장한다.

    국내 지수의 `pykrx_collector.collect_pykrx_index` 와 **같은 계약**이다 — 종가만 남기고,
    `validate_series_data` 를 통과한 뒤에만 저장하며, 최근 미확정 구간의 제외 건수를
    함께 돌려준다. 계층 계약은 `src/verify_lab/CLAUDE.md` 「단일 값 시계열 계층 계약」이 SoT다.

    [중요] **OHLCV 로 받지 않는다. 그리고 이유가 국내 지수와 «다르다».**
    국내 지수는 소급 산출 구간의 시가·고가·저가가 **0** 이라 시세 스키마 검증에 걸려
    **예외로 드러난다.** 미국 지수는 반대다 — 0 이 하나도 없어 검증을 **그대로 통과하는데**
    옛 구간의 고가·저가가 **종가로 채워져** 있다. `[실측] 2026-09-22` `^GSPC` 는 24,797행 중
    **8,547행(34.5%)이 고가 == 저가**이고 장중폭이 실제로 있는 첫 날이 **1962-01-02**,
    `^IXIC` 는 14,023행 중 **3,459행(24.7%)** 이고 첫 날이 **1984-10-11** 이다.

    그 상태로 OHLCV 를 받으면 **`보유 중 최악` 이 「장중에 한 번도 안 밀렸다」로 읽히는데
    예외도 경고도 나지 않는다.** 종가로 받으면 그 사실이 `손절선(%)` 의 「손절불가」 표기로
    표에 드러난다 — **값을 지우는 것이 아니라 어떻게 잰 값인지 밝히는 것**이다.

    Args:
        symbol: yfinance 지수 심볼 (`^GSPC`. 대소문자·앞뒤 공백 무관)
        output_dir: 저장 디렉터리. 기본값은 단일 값 시계열 폴더

    Returns:
        저장 결과 요약

    Raises:
        ValueError: 심볼이 비었거나 접두를 뗀 뒤 남는 이름이 없는 경우, 조회 결과가 비었거나,
            종가 컬럼이 없거나, 최근 구간 제외 후 남는 행이 없거나, 결측이 발견된 경우
    """
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("지수 심볼이 비어 있습니다")

    ticker = normalized.lstrip(INDEX_SYMBOL_PREFIX)
    if not ticker:
        raise ValueError(f"접두 {INDEX_SYMBOL_PREFIX!r} 를 뗀 뒤 남는 이름이 없습니다: {normalized}")

    # 1. 전 기간 조회. 결과를 좌우하는 인자는 기본값에 맡기지 않는다 (모듈 docstring 참고).
    #    **지수는 분배금이 없어 `auto_adjust` 가 값을 바꾸지 않지만 그래도 명시한다** —
    #    라이브러리가 기본값을 바꿔도 이 호출의 뜻이 흔들리지 않아야 한다
    raw = yf.Ticker(normalized).history(period="max", auto_adjust=False, raise_errors=True)

    if raw.empty:
        raise ValueError(f"수집 결과가 비어 있습니다 - 지수: {normalized}")

    df = raw.reset_index()

    if COL_CLOSE not in df.columns:
        raise ValueError(f"응답에 종가 컬럼이 없습니다 (반환 컬럼: {list(df.columns)}, 지수: {normalized})")

    # 2. 종가만 꺼내 단일 값 스키마로 정규화한다. 거래소 타임존을 떼고 날짜만 남긴다
    df[COL_DATE] = pd.to_datetime(df[COL_DATE]).dt.date
    df = df.rename(columns={COL_CLOSE: COL_VALUE})[[COL_DATE, COL_VALUE]]

    # 3. 확정되지 않은 최근 구간을 제외한다. **ETF 와 같은 기준을 쓴다** — 같은 시장이라
    #    시차도 같고, 수집기마다 경계가 갈리면 두 파일의 마지막 날이 어긋난다
    cutoff_date = datetime.now(KST).date() - timedelta(days=RECENT_EXCLUSION_DAYS)
    total_count = len(df)
    df = df.loc[df[COL_DATE] <= cutoff_date].reset_index(drop=True)
    excluded_recent_count = total_count - len(df)

    if df.empty:
        raise ValueError(f"최근 {RECENT_EXCLUSION_DAYS}일 제외 후 남는 데이터가 없습니다 - 지수: {normalized}")

    # 4. 저장 직전 반올림. **정수화하지 않는다** — 지수는 소수 둘째 자리까지 있는 계산된 값이라
    #    정수로 반올림하면 그만큼이 사라진다 (국내 지수 수집기와 같은 이유)
    df[COL_VALUE] = df[COL_VALUE].astype(float).round(PRICE_DECIMALS)

    # 5. 검증. 로더와 같은 함수를 써서 판정이 갈라지지 않게 한다
    validate_series_data(df)

    # 6. 저장. 검증을 통과한 뒤에만 실행한다
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / INDEX_FILE_TEMPLATE.format(ticker=ticker)
    df.to_csv(path, index=False)

    start_date = df[COL_DATE].iloc[0]
    end_date = df[COL_DATE].iloc[-1]

    logger.debug(f"지수 수집 완료: {normalized}, {len(df):,}행, 기간 {start_date} ~ {end_date}, 저장 위치 {path}")
    if excluded_recent_count > 0:
        logger.debug(f"최근 {RECENT_EXCLUSION_DAYS}일 데이터 {excluded_recent_count}행을 제외했습니다")

    return IndexCollectionResult(
        symbol=normalized,
        ticker=ticker,
        path=path,
        row_count=len(df),
        start_date=start_date,
        end_date=end_date,
        excluded_recent_count=excluded_recent_count,
    )
