#!/usr/bin/env python3
"""FRED 시계열 수집 CLI

미국 세인트루이스 연준(FRED)에서 일별 단일 값 시계열을 받아 `storage/series/` 에 저장한다.
미국 3개월 T-bill(DTB3)이 대상이다.

**인증키가 필요 없다.** 공개 CSV 엔드포인트를 쓴다.
실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

from verify_lab.data.fred_collector import FRED_SERIES, FredCollectionResult, collect_fred_series, find_series
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_FRED = "fred_collect"

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
    parser = argparse.ArgumentParser(description="FRED 에서 일별 시계열을 받아 단일 값 시계열 파일로 저장합니다.")
    parser.add_argument(
        "--series",
        nargs="+",
        choices=[series.key for series in FRED_SERIES],
        default=None,
        help="수집할 시계열 (기본값: 전부)",
    )
    return parser.parse_args()


@cli_exception_handler
def main() -> int:
    """수집을 실행하고 결과를 표로 표시한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()
    keys = args.series if args.series else [series.key for series in FRED_SERIES]

    results: list[FredCollectionResult] = []
    for key in keys:
        results.append(collect_fred_series(find_series(key)))

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
        title="FRED 수집 결과",
    )

    save_metadata(
        KEY_META_FRED,
        {
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
            ]
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
