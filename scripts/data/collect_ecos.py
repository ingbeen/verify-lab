#!/usr/bin/env python3
"""ECOS 시계열 수집 CLI

한국은행 ECOS 에서 일별 단일 값 시계열을 받아 `storage/series/` 에 저장한다.
원달러 매매기준율과 CD 91일물이 대상이다.

**기간을 잘라 저장하지 않는다.** 받을 수 있는 전 기간을 남기고, 분석 구간을 정하는 것은
측정 계층의 몫이다. 기본 시작일이 두 시계열의 실제 시작보다 이른 이유가 그것이다.

저장소 루트의 `.env` 에 `ECOS_API_KEY` 가 있어야 한다.
실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
from datetime import date, datetime

from verify_lab.common_constants import KST
from verify_lab.data.ecos_collector import ECOS_SERIES, EcosCollectionResult, collect_ecos_series, find_series
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_ECOS = "ecos_collect"

# 인자 형식. pykrx 수집 스크립트와 같은 표기를 쓴다
ARG_DATE_FORMAT = "%Y%m%d"

# 기본 조회 시작일. 두 시계열의 실제 시작(환율 1964, CD91 1995)보다 이르게 두어
# **가용한 전 기간**을 받는다. ECOS 는 없는 구간을 조용히 건너뛴다
DEFAULT_START = date(1960, 1, 1)


# 요약 표의 컬럼 정의 (컬럼명, 폭, 정렬)
SUMMARY_COLUMNS = [
    ("시계열", 10, Align.LEFT),
    ("기간", 26, Align.LEFT),
    ("행 수", 9, Align.RIGHT),
    ("결측 제외", 12, Align.LEFT),
    ("저장 위치", 46, Align.LEFT),
]


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="ECOS 에서 일별 시계열을 받아 단일 값 시계열 파일로 저장합니다.")
    parser.add_argument(
        "--series",
        nargs="+",
        choices=[series.key for series in ECOS_SERIES],
        default=None,
        help="수집할 시계열 (기본값: 전부)",
    )
    parser.add_argument(
        "--start",
        default=DEFAULT_START.strftime(ARG_DATE_FORMAT),
        help=f"조회 시작일 YYYYMMDD (기본값: {DEFAULT_START.strftime(ARG_DATE_FORMAT)})",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="조회 종료일 YYYYMMDD (기본값: 오늘, KST)",
    )
    return parser.parse_args()


def _parse_date(text: str) -> date:
    """YYYYMMDD 문자열을 날짜로 바꾼다.

    Args:
        text: 날짜 문자열

    Returns:
        날짜

    Raises:
        ValueError: 형식이 맞지 않는 경우
    """
    try:
        return datetime.strptime(text, ARG_DATE_FORMAT).date()
    except ValueError:
        raise ValueError(f"날짜 형식이 올바르지 않습니다: {text} (YYYYMMDD)") from None


@cli_exception_handler
def main() -> int:
    """수집을 실행하고 결과를 표로 표시한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()

    start = _parse_date(args.start)
    end = _parse_date(args.end) if args.end else datetime.now(KST).date()
    keys = args.series if args.series else [series.key for series in ECOS_SERIES]

    results: list[EcosCollectionResult] = []
    for key in keys:
        results.append(collect_ecos_series(find_series(key), start, end))

    TableLogger(SUMMARY_COLUMNS, logger).print_table(
        [
            [
                result.series_key,
                f"{result.start_date} ~ {result.end_date}",
                f"{result.row_count:,}",
                f"{result.excluded_missing_count}행",
                str(result.path),
            ]
            for result in results
        ],
        title=f"ECOS 수집 결과 (조회 구간 {start} ~ {end})",
    )

    save_metadata(
        KEY_META_ECOS,
        {
            "requested_range": f"{start} ~ {end}",
            "series": [
                {
                    "key": result.series_key,
                    "path": str(result.path),
                    "row_count": result.row_count,
                    "start_date": str(result.start_date),
                    "end_date": str(result.end_date),
                    "excluded_missing_count": result.excluded_missing_count,
                }
                for result in results
            ],
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
