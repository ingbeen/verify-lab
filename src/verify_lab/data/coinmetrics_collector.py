"""Coin Metrics 커뮤니티 API 일별 지표 수집

Coin Metrics 무료(커뮤니티) API 에서 비트코인 일별 지표를 전 기간으로 받아 `storage/series/` 에 남긴다.
반감기_사이클의 **보완 계열이자 크로스체크 상대**다 — Bitstamp 가 없는 2011-08-17 이전과
거래가 없던 날을 덮고, 같은 날 종가를 대조한다(`docs/검증/반감기_사이클/설계.md`).

**인증키가 필요 없다.** 커뮤니티 엔드포인트는 IP 당 6초에 10회까지 받으며, 요청 한 번에 최대 10,000행을
주므로 지금 전 기간(2010-07-18 ~)이 한 번에 끝난다. 그 너머는 `next_page_url` 을 따라간다.

**실측한 함정 둘** (2026-09-29, `docs/검증/반감기_사이클/설계.md` 「데이터 실측 기록」)

1. **`paging_from` 을 주지 않으면 최신 행부터 온다.** 그 상태로 한 페이지만 받으면 **예외 없이 최근 구간만**
   저장된다. 그래서 `paging_from=start` 를 명시한다
2. **값의 날짜 d 는 d 일 UTC 하루가 끝난 시점의 값이다.** Bitstamp 일봉의 날짜와 같은 하루를 가리킨다.
   끝나지 않은 날은 저장하지 않는다(`crypto_common.exclude_unfinished_days`)

**값이 비어 있으면 메우지 않고 예외로 드러낸다**(`loader.validate_series_data`). FRED 와 달리 휴장이 없어
값이 빈 날은 「원래 없는 날」이 아니라 소스의 결함이다.

무료 CSV 저장소(`coinmetrics/data`)는 2026-05 에서 멈춰 있어 쓰지 않는다 — API 는 멈추지 않았다(같은 실측).
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_DATE, COL_VALUE, KST, PRICE_DECIMALS, SERIES_DIR
from verify_lab.data.crypto_common import count_missing_days, exclude_unfinished_days, require_complete_range
from verify_lab.data.loader import validate_series_data
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

COINMETRICS_METRICS_URL: Final = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"

# 요청 한 번에 받는 행 수. 커뮤니티 API 가 허용하는 최대값이다
PAGE_SIZE: Final = 10_000

USER_AGENT: Final = "verify-lab"

REQUEST_TIMEOUT_SECONDS: Final = 60

# 끝난 날의 값이 올라오기까지 허용하는 일수. Coin Metrics 는 날짜 d 의 값을 **d+1 일 UTC 02:28 ~ 03:32
# (KST 11:28 ~ 12:32)에 완성한다**(`AssetEODCompletionTime` 여섯 날 실측, 2026-09-29) — KST 09:00 ~ 12:30 에
# 돌리면 어제 값이 아직 없어서, 하루를 허용하지 않으면 정상 실행이 「뒤가 잘렸다」로 막힌다
PUBLICATION_LAG_DAYS: Final = 1


@dataclass(frozen=True)
class CoinMetricsSeries:
    """수집 대상 지표 하나

    Attributes:
        key: 결과와 실행 이력에서 부르는 이름
        label: 표시 이름
        asset: Coin Metrics 자산 코드 (`btc`)
        metric: Coin Metrics 지표 이름. 응답에서 값이 이 키로 온다
        file_name: `storage/series/` 에 저장할 파일 이름 — `{자산}_{지표}.csv`
        decimals: 저장 직전 반올림 자릿수
        unit: 값의 단위. 컬럼 이름이 중립적(`Value`)이라 단위는 여기에만 있다
        first_date: 그 지표의 첫 날. 받은 이력이 이 날에서 시작하지 않으면 앞이 잘린 것이다
    """

    key: str
    label: str
    asset: str
    metric: str
    file_name: str
    decimals: int
    unit: str
    first_date: date


# 비트코인 기준가. **Bitstamp 일봉의 크로스체크 상대**라 이름으로 집는다.
# 가격은 `common_constants.PRICE_DECIMALS` 를 따른다 — 2010 년 초 값은 조금 깎이지만(0.08584 → 0.0858 은 0.047%,
# 전 구간 최대 0.082%) 측정이 쓰는 첫 반감기(2012-11-28) 뒤로는 최대 0.0004% 다 (2026-09-29 실측)
BTC_PRICE_SERIES: Final = CoinMetricsSeries(
    key="btc_price",
    label="비트코인 기준가 (Coin Metrics)",
    asset="btc",
    metric="PriceUSD",
    file_name="BTC_PriceUSD.csv",
    decimals=PRICE_DECIMALS,
    unit="달러",
    # 마운트곡스 개장일 — Coin Metrics 가격 계열의 시작 (2026-09-29 실측)
    first_date=date(2010, 7, 18),
)

# 수집 대상 전부. 지표를 더할 때는 여기에 한 줄을 더한다
COINMETRICS_SERIES: Final = (BTC_PRICE_SERIES,)


@dataclass(frozen=True)
class CoinMetricsCollectionResult:
    """수집 결과 요약

    Attributes:
        series_key: 수집한 지표 이름
        path: 저장된 CSV 경로
        row_count: 저장된 행 수
        start_date: 저장 구간의 첫 날
        end_date: 저장 구간의 마지막 날
        excluded_recent_count: UTC 로 끝나지 않아 뺀 행 수
        missing_day_count: 첫 날과 마지막 날 사이에 행이 없는 달력일 수. 빠진 날이 있으면 저장하지 않으므로
            저장했다면 0 이다 — 「빈틈없이 받았다」를 결과에 사실로 남긴다
    """

    series_key: str
    path: Path
    row_count: int
    start_date: date
    end_date: date
    excluded_recent_count: int
    missing_day_count: int


def first_page_url(series: CoinMetricsSeries) -> str:
    """첫 페이지 요청 URL 을 만든다. **오래된 행부터**(`paging_from=start`) 묻는다 (모듈 docstring 함정 1).

    Args:
        series: 수집 대상

    Returns:
        요청 URL
    """
    query = urllib.parse.urlencode(
        {
            "assets": series.asset,
            "metrics": series.metric,
            "frequency": "1d",
            "page_size": PAGE_SIZE,
            "paging_from": "start",
        }
    )
    return f"{COINMETRICS_METRICS_URL}?{query}"


def request_page(url: str) -> dict[str, Any]:
    """한 페이지를 받아 JSON 으로 돌려준다.

    Args:
        url: 요청 URL (첫 페이지 URL 또는 응답이 준 `next_page_url`)

    Returns:
        응답 JSON. `data` 목록을 반드시 갖는다

    Raises:
        ValueError: HTTP 오류이거나, 연결하지 못했거나, 응답 모양이 다른 경우
    """
    logger.debug(f"Coin Metrics 요청: {url}")

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise ValueError(f"Coin Metrics 응답이 HTTP 오류입니다 ({error.code}) - URL: {url}") from None
    except urllib.error.URLError as error:
        raise ValueError(f"Coin Metrics 에 연결하지 못했습니다: {error.reason} - URL: {url}") from None

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise ValueError(f"Coin Metrics 응답이 JSON 이 아닙니다 - URL: {url}, 앞부분: {body[:200]}") from None

    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError(f"Coin Metrics 응답 모양이 예상과 다릅니다 (data 목록 없음) - URL: {url}, 앞부분: {body[:200]}")

    return payload


def fetch_metric_rows(series: CoinMetricsSeries) -> list[dict[str, Any]]:
    """첫 페이지부터 `next_page_url` 을 따라가 모든 행을 모은다.

    Args:
        series: 수집 대상

    Returns:
        행 목록. 값은 서버가 준 그대로(문자열)다

    Raises:
        ValueError: 다음 URL 이 방금 받은 URL 과 같아 앞으로 나아가지 않거나, 요청에서 걸린 경우
    """
    rows: list[dict[str, Any]] = []
    url: str | None = first_page_url(series)

    while url is not None:
        payload = request_page(url)
        rows.extend(payload["data"])

        next_url = payload.get("next_page_url")
        if next_url is not None and next_url == url:
            raise ValueError(f"Coin Metrics 다음 페이지가 앞으로 나아가지 않습니다 (같은 URL) - {url}")
        url = next_url

    return rows


def parse_metric_rows(rows: list[dict[str, Any]], series: CoinMetricsSeries) -> pd.DataFrame:
    """행 목록을 단일 값 스키마(날짜 + 실수)의 DataFrame 으로 바꾼다.

    **값이 없는 행은 빼지 않고 결측으로 남긴다** — 이어지는 검증이 예외로 드러낸다(모듈 docstring).
    **시각이 UTC 자정이 아니면 막는다** — Bitstamp 봉과 같은 이유다(`bitstamp_collector.parse_ohlc_rows`).
    날짜 기준이 바뀌면 값이 하루 밀린 채 저장되고, 크로스체크 상대와 조용히 어긋난다.

    Args:
        rows: `fetch_metric_rows` 가 준 행들
        series: 수집 대상

    Returns:
        날짜 · 값 DataFrame. 날짜는 그 값의 UTC 날짜(`date` 객체)다

    Raises:
        ValueError: 행이 없거나, 시각 키가 없거나, 시각이 UTC 자정이 아닌 경우
    """
    if not rows:
        raise ValueError(f"Coin Metrics 응답이 비어 있습니다 - 지표: {series.key}")

    frame = pd.DataFrame(rows)
    if "time" not in frame.columns:
        raise ValueError(f"Coin Metrics 행에 time 이 없습니다 - 지표: {series.key}")

    times = pd.to_datetime(frame["time"], utc=True)
    off_midnight = times != times.dt.normalize()
    if off_midnight.any():
        raise ValueError(
            f"UTC 자정이 아닌 시각이 있습니다 - 지표: {series.key}, 건수: {int(off_midnight.sum())}, "
            f"예시: {frame.loc[off_midnight, 'time'].head().tolist()}"
        )

    values = frame[series.metric] if series.metric in frame.columns else pd.Series(float("nan"), index=frame.index)

    return pd.DataFrame(
        {
            COL_DATE: times.dt.date,
            COL_VALUE: pd.to_numeric(values, errors="coerce"),
        }
    )


def collect_coinmetrics_series(
    series: CoinMetricsSeries, *, output_dir: Path = SERIES_DIR
) -> CoinMetricsCollectionResult:
    """Coin Metrics 지표를 전 기간으로 받아 단일 값 시계열 파일로 저장한다.

    조회 → 해석 → 정렬 → 끝나지 않은 날 제외 → 반올림 → 검증 → 빈틈 확인 → 저장 순으로 수행하며,
    **검증을 통과한 데이터만 저장한다.**

    Args:
        series: 수집 대상
        output_dir: 저장 디렉터리. 기본값은 단일 값 시계열 폴더

    Returns:
        저장 결과 요약. 끝나지 않아 뺀 행 수와 빠진 날 수를 함께 담는다

    Raises:
        ValueError: 조회·해석·검증에서 걸렸거나, 제외 후 남는 행이 없거나, 받은 이력의 양 끝이 잘렸거나 사이에 빠진 날이 있는 경우
    """
    # 「오늘」의 시계는 KST 하나다(`common_constants.KST`). **조회보다 먼저 잰다** — Bitstamp 수집기와 같은 이유
    now = datetime.now(KST)

    # 1. 조회와 해석
    frame = parse_metric_rows(fetch_metric_rows(series), series)

    # 2. 시간순 정렬. 응답 순서에 의존하지 않는다
    frame = frame.sort_values(COL_DATE).reset_index(drop=True)

    # 3. UTC 로 끝나지 않은 날을 뺀다
    frame, excluded_recent_count = exclude_unfinished_days(frame, now)
    if frame.empty:
        raise ValueError(f"끝나지 않은 날을 빼고 나니 남는 행이 없습니다 - 지표: {series.key}")

    # 4. 저장 직전 반올림
    frame[COL_VALUE] = frame[COL_VALUE].round(series.decimals)

    # 5. 검증. 로더와 같은 함수를 써서 판정이 갈라지지 않게 한다
    validate_series_data(frame)

    # 5-1. 값의 범위. 단일 값 로더는 부호도 무한대도 보지 않고 범위를 수집기에 맡긴다(`loader.validate_series_data`).
    # 지금 받는 지표는 가격이라 **유한한 양수**여야 한다 — 0 이면 크로스체크가 무한대를 내고, 무한대면
    # 그 날의 대조가 무한대가 되며, 측정의 대체가 그 값을 옮긴다. 반올림으로 0 이 된 값도 여기서 걸린다.
    # 부호가 있는 지표를 더하면 이 판정을 지표마다 가른다
    invalid = ~(np.isfinite(frame[COL_VALUE]) & (frame[COL_VALUE] > 0))
    if invalid.any():
        raise ValueError(
            f"유한한 양수가 아닌 값 발견(0 이하 · 무한대) - 지표: {series.key}, 건수: {int(invalid.sum())}, "
            f"예시 날짜: {frame.loc[invalid, COL_DATE].head().tolist()}"
        )

    # 6. 빈틈 확인 — 양 끝과 그 사이. 끝난 날의 값이 늦게 올라오므로 끝에 하루를 허용한다
    require_complete_range(
        frame[COL_DATE], first_day=series.first_date, now=now, publication_lag_days=PUBLICATION_LAG_DAYS
    )

    # 7. 저장. 검증을 통과한 뒤에만 실행한다
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / series.file_name
    frame.to_csv(path, index=False)

    start_date = frame[COL_DATE].iloc[0]
    end_date = frame[COL_DATE].iloc[-1]
    missing_day_count = count_missing_days(frame[COL_DATE])

    logger.debug(f"수집 완료: {series.key}, {len(frame):,}행, 기간 {start_date} ~ {end_date}, 저장 위치 {path}")
    if excluded_recent_count > 0:
        logger.debug(f"UTC 로 끝나지 않은 {excluded_recent_count}행을 제외했습니다")

    return CoinMetricsCollectionResult(
        series_key=series.key,
        path=path,
        row_count=len(frame),
        start_date=start_date,
        end_date=end_date,
        excluded_recent_count=excluded_recent_count,
        missing_day_count=missing_day_count,
    )
