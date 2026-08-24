"""ECOS 오픈API 시계열 수집

한국은행 ECOS 에서 일별 단일 값 시계열을 받아 `storage/series/` 에 남긴다.
원달러 매매기준율과 CD 91일물이 이 경로로 들어온다.

**인증키가 요청 URL 경로에 들어간다.** 그래서 이 모듈은 URL 을 절대 그대로 로깅하지 않고
`mask_api_key` 를 통과시킨 문자열만 남긴다. 예외 메시지도 마찬가지다 —
`urllib` 이 던지는 예외에는 URL 이 통째로 담겨 있어 그대로 올리면 키가 로그에 남는다.

**통계표코드·항목코드는 실측으로 확정한 값이다.** 근거와 조회 가능 구간은
`docs/spec/usdkrw_grid.md` "데이터 실측 기록" 에 있다. 이 값들은 ECOS 가 개편되면 바뀔 수 있으므로
기억이 아니라 프로브(`scripts/data/check_ecos.py`)로 다시 확인한다.

이상치 판정은 `loader.validate_series_data()` 를 그대로 재사용한다. 수집기가 자기 판정을
따로 두면 "수집은 통과했는데 로딩에서 막히는" 데이터가 생긴다.
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final

import pandas as pd

from verify_lab.common_constants import COL_DATE, COL_VALUE, SERIES_DIR
from verify_lab.data.ecos_credentials import load_ecos_api_key, mask_api_key
from verify_lab.data.loader import validate_series_data
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

ECOS_BASE_URL: Final = "https://ecos.bok.or.kr/api"

# 서비스 이름. URL 의 첫 구간이며 ECOS 가 정한 값이라 바꿀 수 없다
SERVICE_TABLE_LIST: Final = "StatisticTableList"
SERVICE_ITEM_LIST: Final = "StatisticItemList"
SERVICE_SEARCH: Final = "StatisticSearch"

RESPONSE_FORMAT: Final = "json"
RESPONSE_LANGUAGE: Final = "kr"

# 한 번에 요청할 행 수 상한. 전 기간 일별 시계열이 3만 행 미만이라 페이징 없이 한 번에 받는다.
# 그럼에도 응답의 `list_total_count` 와 실제 행 수를 대조해, 잘려 들어온 것을 조용히 넘기지 않는다
MAX_ROWS: Final = 100_000

REQUEST_TIMEOUT_SECONDS: Final = 60

# 오류 응답의 최상위 키. 정상 응답은 서비스 이름을 키로 쓰고, 오류일 때만 이 키가 온다
KEY_RESULT: Final = "RESULT"
KEY_ROW: Final = "row"
KEY_TOTAL_COUNT: Final = "list_total_count"

# 조회 결과의 컬럼. ECOS 가 정한 이름이다
KEY_TIME: Final = "TIME"
KEY_DATA_VALUE: Final = "DATA_VALUE"

# ECOS 가 요구하는 날짜 표기
ECOS_DATE_FORMAT: Final = "%Y%m%d"


@dataclass(frozen=True)
class EcosSeries:
    """수집 대상 시계열 하나

    Attributes:
        key: 실행 인자로 고르는 이름
        label: 표시 이름
        stat_code: ECOS 통계표코드
        item_code: ECOS 통계항목코드
        cycle: 조회 주기. 일별은 `D`
        file_name: `storage/series/` 에 저장할 파일 이름
        decimals: 저장 직전 반올림 자릿수
        unit: 값의 단위. 컬럼 이름이 중립적이라 단위는 여기에만 있다
    """

    key: str
    label: str
    stat_code: str
    item_code: str
    cycle: str
    file_name: str
    decimals: int
    unit: str


# 수집 대상. **값은 실측으로 확정했다** — 근거는 `docs/spec/usdkrw_grid.md` 참고.
# 자릿수는 `.claude/rules/python.md` 반올림 규칙표를 따른다 (환율은 가격, CD91 은 백분율이라 둘 다 2자리)
ECOS_SERIES: Final = (
    EcosSeries(
        key="usdkrw",
        label="원/미국달러(매매기준율)",
        stat_code="731Y001",
        item_code="0000001",
        cycle="D",
        file_name="USDKRW.csv",
        decimals=2,
        unit="원",
    ),
    EcosSeries(
        key="usdkrw_close",
        label="원/달러(종가 15:30)",
        stat_code="731Y003",
        item_code="0000003",
        cycle="D",
        file_name="USDKRW_CLOSE.csv",
        decimals=2,
        unit="원",
    ),
    EcosSeries(
        key="cd91",
        label="CD(91일)",
        stat_code="817Y002",
        item_code="010502000",
        cycle="D",
        file_name="CD91.csv",
        decimals=2,
        unit="연%",
    ),
)


@dataclass(frozen=True)
class EcosCollectionResult:
    """수집 결과 요약

    Attributes:
        series_key: 수집한 시계열 이름
        path: 저장된 CSV 경로
        row_count: 저장된 행 수
        start_date: 저장 구간의 첫 날
        end_date: 저장 구간의 마지막 날
        excluded_missing_count: 값이 비어 있어 제외한 행 수
    """

    series_key: str
    path: Path
    row_count: int
    start_date: date
    end_date: date
    excluded_missing_count: int


def find_series(key: str) -> EcosSeries:
    """수집 대상 목록에서 이름으로 하나를 찾는다.

    Args:
        key: 시계열 이름

    Returns:
        해당 시계열

    Raises:
        ValueError: 그 이름의 시계열이 없는 경우
    """
    for series in ECOS_SERIES:
        if series.key == key:
            return series

    raise ValueError(f"알 수 없는 시계열입니다: {key} (가능한 값: {[s.key for s in ECOS_SERIES]})")


def request_ecos(path_parts: list[str], api_key: str) -> dict[str, Any]:
    """ECOS 오픈API 를 한 번 호출해 JSON 응답을 돌려준다.

    **URL 과 예외 메시지는 반드시 마스킹을 거쳐 로깅한다.** 인증키가 경로에 들어 있다.

    Args:
        path_parts: 서비스 이름 뒤에 붙는 경로 구간들 (인증키는 이 함수가 붙인다)
        api_key: ECOS 인증키

    Returns:
        파싱된 응답 dict

    Raises:
        ValueError: 경로가 비었거나, HTTP 오류이거나, 응답이 JSON 이 아니거나,
            ECOS 가 오류 코드를 돌려준 경우
    """
    if not path_parts:
        raise ValueError("요청 경로가 비어 있습니다")

    service = path_parts[0]
    url = "/".join([ECOS_BASE_URL, service, api_key, RESPONSE_FORMAT, RESPONSE_LANGUAGE, *path_parts[1:]])
    safe_url = mask_api_key(url, api_key)

    logger.debug(f"ECOS 요청: {safe_url}")

    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        # HTTPError 의 문자열에는 URL 이 담긴다. 그대로 올리면 인증키가 예외로 샌다
        raise ValueError(f"ECOS 응답이 HTTP 오류입니다 ({error.code}) - 요청: {safe_url}") from None
    except urllib.error.URLError as error:
        raise ValueError(f"ECOS 에 연결하지 못했습니다: {mask_api_key(str(error.reason), api_key)}") from None
    except json.JSONDecodeError:
        raise ValueError(f"ECOS 응답이 JSON 이 아닙니다 - 요청: {safe_url}") from None

    if KEY_RESULT in payload:
        result = payload[KEY_RESULT]
        raise ValueError(f"ECOS 가 오류를 돌려줬습니다: {result.get('CODE')} {result.get('MESSAGE')} - 요청: {safe_url}")

    return payload


def fetch_rows(service: str, path_parts: list[str], api_key: str) -> list[dict[str, Any]]:
    """조회 결과의 행 목록을 돌려준다.

    응답이 알린 전체 건수와 실제로 받은 행 수를 대조한다. 어긋나면 상한에 걸려 잘린 것이므로
    조용히 넘기지 않는다 — 잘린 시계열은 "그 날짜부터 데이터가 없다"로 읽힌다.

    Args:
        service: 서비스 이름
        path_parts: 서비스 뒤에 붙는 경로 구간들
        api_key: ECOS 인증키

    Returns:
        행 목록

    Raises:
        ValueError: 응답에 서비스 키가 없거나, 받은 행 수가 전체 건수와 다른 경우
    """
    payload = request_ecos([service, *path_parts], api_key)

    if service not in payload:
        raise ValueError(f"ECOS 응답에 {service} 가 없습니다 (최상위 키: {sorted(payload)})")

    body = payload[service]
    rows: list[dict[str, Any]] = body.get(KEY_ROW, [])
    total_count = int(body.get(KEY_TOTAL_COUNT, len(rows)))

    if len(rows) != total_count:
        raise ValueError(f"응답이 잘렸습니다 - 전체 {total_count:,}건 중 {len(rows):,}건만 받았습니다 (서비스: {service})")

    return rows


def fetch_table_list(api_key: str) -> list[dict[str, Any]]:
    """통계표 목록 전체를 돌려준다.

    Args:
        api_key: ECOS 인증키

    Returns:
        통계표 행 목록
    """
    return fetch_rows(SERVICE_TABLE_LIST, ["1", str(MAX_ROWS)], api_key)


def fetch_item_list(stat_code: str, api_key: str) -> list[dict[str, Any]]:
    """한 통계표의 항목 목록을 돌려준다.

    Args:
        stat_code: 통계표코드
        api_key: ECOS 인증키

    Returns:
        항목 행 목록
    """
    return fetch_rows(SERVICE_ITEM_LIST, ["1", str(MAX_ROWS), stat_code], api_key)


def fetch_series(series: EcosSeries, start: date, end: date, api_key: str) -> tuple[pd.DataFrame, int]:
    """한 시계열을 조회해 단일 값 스키마의 DataFrame 으로 돌려준다.

    **값이 비어 있는 행은 메우지 않고 제외하며, 제외 건수를 함께 돌려준다.**
    조용히 사라진 표본은 나중에 "그날은 원래 없었다"로 오해된다.

    Args:
        series: 수집 대상
        start: 조회 시작일
        end: 조회 종료일
        api_key: ECOS 인증키

    Returns:
        (날짜·값 DataFrame, 값이 비어 제외된 행 수)

    Raises:
        ValueError: 조회 구간이 뒤집혔거나, 결과가 비었거나, 날짜를 해석할 수 없는 경우
    """
    if start > end:
        raise ValueError(f"조회 구간이 뒤집혔습니다: {start} ~ {end}")

    rows = fetch_rows(
        SERVICE_SEARCH,
        [
            "1",
            str(MAX_ROWS),
            series.stat_code,
            series.cycle,
            start.strftime(ECOS_DATE_FORMAT),
            end.strftime(ECOS_DATE_FORMAT),
            series.item_code,
        ],
        api_key,
    )

    if not rows:
        raise ValueError(f"조회 결과가 비어 있습니다 - 시계열: {series.key}, 구간: {start} ~ {end}")

    frame = pd.DataFrame(rows)
    total_count = len(frame)

    # 값이 비어 있는 행을 제외한다. ECOS 는 미공표일을 빈 문자열로 돌려주는 경우가 있다
    frame[COL_VALUE] = pd.to_numeric(frame[KEY_DATA_VALUE], errors="coerce")
    frame = frame.loc[frame[COL_VALUE].notna()].copy()
    excluded_missing_count = total_count - len(frame)

    if frame.empty:
        raise ValueError(f"값이 있는 행이 하나도 없습니다 - 시계열: {series.key}, 구간: {start} ~ {end}")

    frame[COL_DATE] = pd.to_datetime(frame[KEY_TIME], format=ECOS_DATE_FORMAT).dt.date

    return frame[[COL_DATE, COL_VALUE]].reset_index(drop=True), excluded_missing_count


def collect_ecos_series(
    series: EcosSeries,
    start: date,
    end: date,
    *,
    api_key: str | None = None,
    output_dir: Path = SERIES_DIR,
) -> EcosCollectionResult:
    """ECOS 시계열을 받아 단일 값 시계열 파일로 저장한다.

    조회 → 결측 제외 → 정렬 → 반올림 → 검증 → 저장 순으로 수행하며,
    **검증을 통과한 데이터만 저장한다.** 검증에서 걸리면 파일을 만들지 않고 예외를 던진다.

    Args:
        series: 수집 대상
        start: 조회 시작일
        end: 조회 종료일
        api_key: ECOS 인증키. `None` 이면 `.env` 에서 읽는다
        output_dir: 저장 디렉터리. 기본값은 단일 값 시계열 폴더

    Returns:
        저장 결과 요약

    Raises:
        ValueError: 인증키를 읽지 못했거나, 조회·검증에서 걸린 경우
    """
    resolved_key = api_key if api_key is not None else load_ecos_api_key()

    # 1. 조회. 결측 제외 건수를 함께 받는다
    frame, excluded_missing_count = fetch_series(series, start, end, resolved_key)

    # 2. 시간순 정렬. ECOS 응답 순서에 의존하지 않는다
    frame = frame.sort_values(COL_DATE).reset_index(drop=True)

    # 3. 저장 직전 반올림. 파일에 적히는 자릿수를 맞추는 단계다
    frame[COL_VALUE] = frame[COL_VALUE].round(series.decimals)

    # 4. 검증. 로더와 같은 함수를 써서 판정이 갈라지지 않게 한다
    validate_series_data(frame)

    # 5. 저장. 검증을 통과한 뒤에만 실행한다
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / series.file_name
    frame.to_csv(path, index=False)

    start_date = frame[COL_DATE].iloc[0]
    end_date = frame[COL_DATE].iloc[-1]

    logger.debug(f"수집 완료: {series.key}, {len(frame):,}행, 기간 {start_date} ~ {end_date}, 저장 위치 {path}")
    if excluded_missing_count > 0:
        logger.debug(f"값이 비어 있는 {excluded_missing_count}행을 제외했습니다")

    return EcosCollectionResult(
        series_key=series.key,
        path=path,
        row_count=len(frame),
        start_date=start_date,
        end_date=end_date,
        excluded_missing_count=excluded_missing_count,
    )
