"""FRED 시계열 수집

미국 세인트루이스 연준(FRED)에서 일별 단일 값 시계열을 받아 `storage/series/` 에 남긴다.
미국 3개월 T-bill(DTB3)이 이 경로로 들어온다.

**인증키가 필요 없다.** FRED 는 그래프용 CSV 를 공개 엔드포인트로 제공하며,
이 모듈은 그것을 쓴다. ECOS 수집기와 달리 마스킹할 비밀값이 없다.

**미국 휴장일은 행이 있고 값만 비어 있다.** 날짜가 빠지는 것이 아니라 값 칸이 공백으로 온다
(실측: `docs/spec/usdkrw_grid.md`). 수집기는 그 행을 **제외하고 제외 건수를 보고**하며,
전일값 이월은 하지 않는다 — 이월은 측정 계층의 판단이고, 수집이 미리 메우면
"원래 값이 없던 날"과 "메운 날"을 나중에 구분할 수 없다.

이상치 판정은 `loader.validate_series_data()` 를 그대로 재사용한다. 수집기가 자기 판정을
따로 두면 "수집은 통과했는데 로딩에서 막히는" 데이터가 생긴다.
"""

import io
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

import pandas as pd

from verify_lab.common_constants import COL_DATE, COL_VALUE, SERIES_DIR
from verify_lab.data.loader import validate_series_data
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

FRED_CSV_URL: Final = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# 기본 User-Agent 로는 차단될 수 있어 식별자를 명시한다
USER_AGENT: Final = "verify-lab"

REQUEST_TIMEOUT_SECONDS: Final = 60


@dataclass(frozen=True)
class FredSeries:
    """수집 대상 시계열 하나

    Attributes:
        key: 실행 인자로 고르는 이름
        label: 표시 이름
        series_id: FRED 시리즈 ID. 응답 CSV 의 값 컬럼 이름이기도 하다
        file_name: `storage/series/` 에 저장할 파일 이름
        decimals: 저장 직전 반올림 자릿수
        unit: 값의 단위. 컬럼 이름이 중립적이라 단위는 여기에만 있다
    """

    key: str
    label: str
    series_id: str
    file_name: str
    decimals: int
    unit: str


# 수집 대상. 자릿수는 `.claude/rules/python.md` 반올림 규칙표를 따른다 (백분율이라 2자리)
FRED_SERIES: Final = (
    FredSeries(
        key="dtb3",
        label="미국 3개월 T-bill (2차시장 할인율)",
        series_id="DTB3",
        file_name="DTB3.csv",
        decimals=2,
        unit="연%",
    ),
)


@dataclass(frozen=True)
class FredCollectionResult:
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


def find_series(key: str) -> FredSeries:
    """수집 대상 목록에서 이름으로 하나를 찾는다.

    Args:
        key: 시계열 이름

    Returns:
        해당 시계열

    Raises:
        ValueError: 그 이름의 시계열이 없는 경우
    """
    for series in FRED_SERIES:
        if series.key == key:
            return series

    raise ValueError(f"알 수 없는 시계열입니다: {key} (가능한 값: {[s.key for s in FRED_SERIES]})")


def request_fred_csv(series_id: str) -> str:
    """FRED 에서 시계열 CSV 본문을 받는다.

    Args:
        series_id: FRED 시리즈 ID

    Returns:
        CSV 본문

    Raises:
        ValueError: 시리즈 ID 가 비었거나, HTTP 오류이거나, 연결하지 못한 경우
    """
    if not series_id.strip():
        raise ValueError("시리즈 ID 가 비어 있습니다")

    url = f"{FRED_CSV_URL}?id={series_id}"
    logger.debug(f"FRED 요청: {url}")

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise ValueError(f"FRED 응답이 HTTP 오류입니다 ({error.code}) - 시리즈: {series_id}") from None
    except urllib.error.URLError as error:
        raise ValueError(f"FRED 에 연결하지 못했습니다: {error.reason} - 시리즈: {series_id}") from None


def parse_fred_csv(body: str, series: FredSeries) -> tuple[pd.DataFrame, int]:
    """FRED CSV 본문을 단일 값 스키마의 DataFrame 으로 바꾼다.

    **날짜 컬럼은 이름이 아니라 위치로 잡는다.** FRED 는 헤더를 `DATE` 에서
    `observation_date` 로 바꾼 적이 있어 이름에 기대면 조용히 깨진다. 값 컬럼은
    시리즈 ID 와 같은 이름이라 그쪽은 이름으로 찾는다.

    **값이 비어 있는 행은 메우지 않고 제외하며, 제외 건수를 함께 돌려준다.**

    Args:
        body: CSV 본문
        series: 수집 대상

    Returns:
        (날짜·값 DataFrame, 값이 비어 제외된 행 수)

    Raises:
        ValueError: 값 컬럼이 없거나, 결과가 비었거나, 값이 하나도 없는 경우
    """
    frame = pd.read_csv(io.StringIO(body))

    if frame.empty:
        raise ValueError(f"FRED 응답이 비어 있습니다 - 시계열: {series.key}")

    if series.series_id not in frame.columns:
        raise ValueError(f"응답에 값 컬럼이 없습니다: {series.series_id} (받은 컬럼: {list(frame.columns)})")

    date_column = frame.columns[0]
    total_count = len(frame)

    # 결측을 제외한다. 값 칸이 공백이거나 마침표(`.`)인 행이 여기 걸린다
    frame[COL_VALUE] = pd.to_numeric(frame[series.series_id], errors="coerce")
    frame = frame.loc[frame[COL_VALUE].notna()].copy()
    excluded_missing_count = total_count - len(frame)

    if frame.empty:
        raise ValueError(f"값이 있는 행이 하나도 없습니다 - 시계열: {series.key}")

    frame[COL_DATE] = pd.to_datetime(frame[date_column]).dt.date

    return frame[[COL_DATE, COL_VALUE]].reset_index(drop=True), excluded_missing_count


def collect_fred_series(series: FredSeries, *, output_dir: Path = SERIES_DIR) -> FredCollectionResult:
    """FRED 시계열을 받아 단일 값 시계열 파일로 저장한다.

    조회 → 파싱·결측 제외 → 정렬 → 반올림 → 검증 → 저장 순으로 수행하며,
    **검증을 통과한 데이터만 저장한다.**

    기간을 잘라 저장하지 않는다. 원시 데이터는 받을 수 있는 만큼 남기고,
    분석 구간을 정하는 것은 측정 계층의 몫이다.

    Args:
        series: 수집 대상
        output_dir: 저장 디렉터리. 기본값은 단일 값 시계열 폴더

    Returns:
        저장 결과 요약

    Raises:
        ValueError: 조회·파싱·검증에서 걸린 경우
    """
    # 1. 조회와 파싱. 결측 제외 건수를 함께 받는다
    frame, excluded_missing_count = parse_fred_csv(request_fred_csv(series.series_id), series)

    # 2. 시간순 정렬. 응답 순서에 의존하지 않는다
    frame = frame.sort_values(COL_DATE).reset_index(drop=True)

    # 3. 저장 직전 반올림
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

    return FredCollectionResult(
        series_key=series.key,
        path=path,
        row_count=len(frame),
        start_date=start_date,
        end_date=end_date,
        excluded_missing_count=excluded_missing_count,
    )
