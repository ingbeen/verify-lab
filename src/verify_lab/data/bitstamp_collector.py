"""Bitstamp 비트코인 일봉 수집

Bitstamp 거래소의 BTC/USD 일봉 OHLCV 를 받을 수 있는 전 기간으로 받아 `storage/market/` 에 남긴다.
반감기_사이클의 **주 계열**이다(2026-09-26 사용자 지시 — `docs/검증/반감기_사이클/사전조사.md` §1.3).

**인증키가 필요 없다.** 공개 REST 엔드포인트(`/api/v2/ohlc/btcusd/`)를 쓰며, 요청 한 번에 1,000개 봉을
주므로 전 기간이 일곱 번 안팎(새 봉이 없음을 확인하는 한 번 포함)에 끝난다.

**실측한 함정 넷** (2026-09-29, `docs/검증/반감기_사이클/설계.md` 「데이터 실측 기록」)

1. **시작 시각을 첫 거래일(2011-08-18 00:00 UTC)보다 앞에 두면 에러 없이 빈 응답이 온다.** 그래서 시작을
   그 시각에 고정하고, 첫 페이지가 비면 「데이터 없음」이 아니라 예외로 본다
2. **봉의 날짜는 UTC 하루다.** 한국 시각 09:00 에 하루가 바뀌고, 그 전에는 UTC 전날 봉이 아직 진행 중이다.
   끝나지 않은 봉은 저장하지 않는다(`crypto_common.exclude_unfinished_days`)
3. **거래가 없던 날도 행이 온다** — 네 값이 전일 종가로 채워지고 거래량이 0 이다(2011 년 30일 · 2015-01-06 ~ 08).
   원시 시세는 받은 그대로 두고, 그 날의 처리는 측정 계층이 한다
4. **시작 시각이 마지막 봉보다 뒤면 빈 목록이 아니라 가장 최근 봉(진행 중인 봉)을 다시 준다.** 함정 1 과 방향이
   반대다. 그래서 페이지 순회는 「빈 페이지」가 아니라 「시작 이후의 새 봉이 없음」에서 멈춘다

이상치 판정은 `loader.validate_market_data()` 를 쓰되 **비트코인의 임계값**(`crypto_common.CRYPTO_MAX_DAILY_CHANGE_RATE`)을
넘긴다 — 공용 50% 로는 2011-10-28 +56.1% 가 막혀 전 기간을 저장할 수 없다.
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final

import pandas as pd

from verify_lab.common_constants import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_VOLUME,
    KST,
    MARKET_DIR,
    MARKET_FILE_TEMPLATE,
    PRICE_COLUMNS,
    PRICE_DECIMALS,
    REQUIRED_COLUMNS,
)
from verify_lab.data.crypto_common import (
    CRYPTO_MAX_DAILY_CHANGE_RATE,
    count_missing_days,
    exclude_unfinished_days,
    require_complete_range,
)
from verify_lab.data.loader import validate_market_data
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

BITSTAMP_OHLC_URL: Final = "https://www.bitstamp.net/api/v2/ohlc/btcusd/"

# 저장 파일의 종목 이름. 파일명은 `BTCUSD_max.csv` 가 된다
BITSTAMP_TICKER: Final = "BTCUSD"

# 봉 길이 (초). 하루 봉을 받는다
DAY_SECONDS: Final = 86_400

# 요청 한 번에 받는 봉 수. Bitstamp 가 허용하는 최대값이다
PAGE_LIMIT = 1_000

# 첫 거래일 2011-08-18 00:00 UTC. **이보다 앞에서 시작하면 에러 없이 빈 응답이 온다**(모듈 docstring 함정 1)
FIRST_TRADE_TIMESTAMP: Final = 1_313_625_600

# 받은 이력이 시작해야 하는 날. 다르면 앞이 잘렸거나 소스가 바뀐 것이다
FIRST_TRADE_DATE: Final = datetime.fromtimestamp(FIRST_TRADE_TIMESTAMP, tz=UTC).date()

USER_AGENT: Final = "verify-lab"

REQUEST_TIMEOUT_SECONDS: Final = 60

# 응답의 값 키 → 시세 스키마 컬럼. 순서가 곧 저장 컬럼 순서다
_FIELD_TO_COLUMN: Final = {
    "open": COL_OPEN,
    "high": COL_HIGH,
    "low": COL_LOW,
    "close": COL_CLOSE,
    "volume": COL_VOLUME,
}


@dataclass(frozen=True)
class BitstampCollectionResult:
    """수집 결과 요약

    Attributes:
        ticker: 저장한 종목 이름
        path: 저장된 CSV 경로
        row_count: 저장된 행 수
        start_date: 저장 구간의 첫 날
        end_date: 저장 구간의 마지막 날
        excluded_recent_count: UTC 로 끝나지 않아 뺀 봉 수
        missing_day_count: 첫 날과 마지막 날 사이에 행이 없는 달력일 수. 빠진 날이 있으면 저장하지 않으므로
            저장했다면 0 이다 — 「빈틈없이 받았다」를 결과에 사실로 남긴다
    """

    ticker: str
    path: Path
    row_count: int
    start_date: date
    end_date: date
    excluded_recent_count: int
    missing_day_count: int


def request_ohlc_page(start: int) -> list[dict[str, Any]]:
    """`start` 시각부터 일봉 한 페이지를 받는다.

    Args:
        start: 첫 봉의 시각 (UTC 유닉스 초)

    Returns:
        봉 목록. 값은 서버가 준 그대로(문자열)다. 첫 거래일 앞을 물으면 빈 목록이, 마지막 봉 뒤를 물으면
        **가장 최근 봉**이 온다(모듈 docstring 함정 1 · 4)

    Raises:
        ValueError: HTTP 오류이거나, 연결하지 못했거나, 응답 모양이 다른 경우
    """
    url = f"{BITSTAMP_OHLC_URL}?step={DAY_SECONDS}&limit={PAGE_LIMIT}&start={start}"
    logger.debug(f"Bitstamp 요청: {url}")

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise ValueError(f"Bitstamp 응답이 HTTP 오류입니다 ({error.code}) - 시작 시각: {start}") from None
    except urllib.error.URLError as error:
        raise ValueError(f"Bitstamp 에 연결하지 못했습니다: {error.reason} - 시작 시각: {start}") from None

    try:
        ohlc = json.loads(body)["data"]["ohlc"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise ValueError(f"Bitstamp 응답 모양이 예상과 다릅니다 (data.ohlc 없음) - 시작 시각: {start}, 앞부분: {body[:200]}") from None

    if not isinstance(ohlc, list):
        raise ValueError(f"Bitstamp 응답의 data.ohlc 가 목록이 아닙니다 - 시작 시각: {start}")

    return ohlc


def parse_ohlc_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """봉 목록을 시세 스키마(날짜 + OHLCV 실수)의 DataFrame 으로 바꾼다.

    **봉 시각이 UTC 자정이 아니면 막는다** — 봉 경계가 바뀌면 날짜가 가리키는 하루가 달라지고,
    크로스체크 상대(Coin Metrics 의 UTC 하루)와 조용히 어긋난다.

    Args:
        rows: `request_ohlc_page` 가 준 봉들

    Returns:
        날짜 오름차순 · 봉 시각 중복 제거한 DataFrame. 날짜는 `date` 객체다

    Raises:
        ValueError: 봉이 없거나, 필요한 키가 없거나, 봉 시각이 UTC 자정이 아닌 경우
    """
    if not rows:
        raise ValueError("Bitstamp 봉 목록이 비어 있습니다")

    frame = pd.DataFrame(rows)
    missing_keys = {"timestamp", *_FIELD_TO_COLUMN} - set(frame.columns)
    if missing_keys:
        raise ValueError(f"Bitstamp 봉에 필요한 키가 없습니다: {sorted(missing_keys)}")

    timestamps = frame["timestamp"].astype("int64")
    off_midnight = timestamps % DAY_SECONDS != 0
    if off_midnight.any():
        raise ValueError(
            f"UTC 자정이 아닌 봉 시각이 있습니다 - 건수: {int(off_midnight.sum())}, 예시: {timestamps[off_midnight].head().tolist()}"
        )

    frame = frame.assign(timestamp=timestamps).drop_duplicates(subset="timestamp", keep="first")
    frame = frame.sort_values("timestamp").reset_index(drop=True)

    parsed = pd.DataFrame({COL_DATE: [datetime.fromtimestamp(int(ts), tz=UTC).date() for ts in frame["timestamp"]]})
    for field, column in _FIELD_TO_COLUMN.items():
        parsed[column] = frame[field].astype(float)

    return parsed[REQUIRED_COLUMNS]


def fetch_ohlc_history() -> pd.DataFrame:
    """첫 거래일부터 오늘까지의 일봉을 페이지를 이어 받는다.

    페이지마다 그 마지막 봉의 다음 날부터 다시 묻고, **요청한 시작 이후의 봉이 하나도 없을 때** 멈춘다.

    - 덜 찬 페이지에서 멈추지 않는다 — 서버가 한 번에 주는 개수를 줄이거나 부하로 덜 줄 때 뒤가 잘린 채 끝난다
    - 빈 페이지를 기다리지도 않는다 — **시작이 마지막 봉보다 뒤면 서버는 빈 목록이 아니라 가장 최근 봉을
      다시 준다**(모듈 docstring 함정 4). 시작 이전의 봉은 이미 받은 것이라 버리고, 새 봉이 없으면 끝이다

    잘려서 끝났는지는 여기서 판정하지 않는다 — 저장 전에 `crypto_common.require_complete_range` 가 양 끝을 본다.

    Returns:
        시세 스키마 DataFrame (최근 구간 제외 전)

    Raises:
        ValueError: 첫 페이지에 봉이 없거나, 봉 시각을 읽을 수 없거나, 요청·해석에서 걸린 경우
    """
    rows: list[dict[str, Any]] = []
    start = FIRST_TRADE_TIMESTAMP

    while True:
        page = request_ohlc_page(start)

        try:
            fresh = [row for row in page if int(row["timestamp"]) >= start]
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"Bitstamp 봉에 읽을 수 있는 timestamp 가 없습니다 - 시작 시각: {start}") from None

        if not fresh:
            if not rows:
                raise ValueError("Bitstamp 첫 페이지가 빈 응답입니다 — 시작 시각이 첫 거래일보다 앞이면 에러 없이 빈 응답이 옵니다 " f"(시작 시각: {start})")
            break

        rows.extend(fresh)
        start = max(int(row["timestamp"]) for row in fresh) + DAY_SECONDS

    return parse_ohlc_rows(rows)


def collect_bitstamp_history(*, output_dir: Path = MARKET_DIR) -> BitstampCollectionResult:
    """Bitstamp 전 기간 일봉을 받아 원시 시세 파일로 저장한다.

    조회 → 끝나지 않은 봉 제외 → 반올림 → 이상치 검증 → 빈틈 확인 → 저장 순으로 수행하며,
    **검증을 통과한 데이터만 저장한다.** 검증에서 걸리면 파일을 만들지 않고 예외를 던진다.

    기간을 잘라 저장하지 않는다. 원시 시세는 받을 수 있는 만큼 남기고, 분석 구간을 정하는 것은
    측정 계층의 몫이다.

    Args:
        output_dir: 저장 디렉터리. 기본값은 원시 시세 폴더

    Returns:
        저장 결과 요약. 끝나지 않아 뺀 봉 수와 빠진 날 수를 함께 담는다

    Raises:
        ValueError: 조회·해석·검증에서 걸렸거나, 제외 후 남는 봉이 없거나, 받은 이력의 양 끝이 잘렸거나 사이에 빠진 날이 있는 경우
    """
    # 「오늘」의 시계는 KST 하나다(`common_constants.KST`). **조회보다 먼저 잰다** — 조회가 끝난 뒤에 재면
    # KST 09:00 을 걸쳐 돈 실행에서 조회 때 진행 중이던 봉이 끝난 봉으로 저장된다
    now = datetime.now(KST)

    # 1. 전 기간 조회
    frame = fetch_ohlc_history()

    # 2. UTC 로 끝나지 않은 봉을 뺀다
    frame, excluded_recent_count = exclude_unfinished_days(frame, now)
    if frame.empty:
        raise ValueError("끝나지 않은 봉을 빼고 나니 남는 봉이 없습니다")

    # 3. 저장 직전 반올림. 거래량은 비트코인 수량이라 가격 자릿수를 걸지 않는다
    frame[PRICE_COLUMNS] = frame[PRICE_COLUMNS].round(PRICE_DECIMALS)

    # 4. 이상치 검증. 로더와 같은 함수 · 같은 임계값을 써서 판정이 갈라지지 않게 한다
    validate_market_data(frame, max_daily_change_rate=CRYPTO_MAX_DAILY_CHANGE_RATE)

    # 5. 빈틈 확인 — 양 끝과 그 사이. 거래소 봉은 끝나는 즉시 확정이라 공개 지연이 없다
    require_complete_range(frame[COL_DATE], first_day=FIRST_TRADE_DATE, now=now, publication_lag_days=0)

    # 6. 저장. 검증을 통과한 뒤에만 실행한다
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / MARKET_FILE_TEMPLATE.format(ticker=BITSTAMP_TICKER)
    frame.to_csv(path, index=False)

    start_date = frame[COL_DATE].iloc[0]
    end_date = frame[COL_DATE].iloc[-1]
    missing_day_count = count_missing_days(frame[COL_DATE])

    logger.debug(f"수집 완료: {BITSTAMP_TICKER}, {len(frame):,}행, 기간 {start_date} ~ {end_date}, 저장 위치 {path}")
    if excluded_recent_count > 0:
        logger.debug(f"UTC 로 끝나지 않은 봉 {excluded_recent_count}개를 제외했습니다")

    return BitstampCollectionResult(
        ticker=BITSTAMP_TICKER,
        path=path,
        row_count=len(frame),
        start_date=start_date,
        end_date=end_date,
        excluded_recent_count=excluded_recent_count,
        missing_day_count=missing_day_count,
    )
