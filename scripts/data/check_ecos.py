#!/usr/bin/env python3
"""ECOS 통계표·항목 실측 프로브

ECOS 의 **통계표코드와 항목코드를 기억이 아니라 실측으로 확정**하기 위한 스크립트다.
두 코드는 ECOS 가 통계를 개편하면 바뀔 수 있고, 바뀌어도 수집은 "해당하는 데이터가 없습니다"
한 줄로만 실패한다. 그래서 코드를 쓰기 전에 여기서 먼저 확인한다.

**받는 즉시 원자료를 저장한다.** 뒤쪽 호출이 실패해도 앞선 결과가 남는다.

저장소 루트의 `.env` 에 `ECOS_API_KEY` 가 있어야 한다.
실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
from pathlib import Path

import pandas as pd

from verify_lab.data.ecos_collector import ECOS_SERIES, fetch_item_list, fetch_table_list
from verify_lab.data.ecos_credentials import load_ecos_api_key
from verify_lab.report.constants import CSV_ENCODING
from verify_lab.report.writer import create_run_directory
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_ECOS_PROBE = "ecos_probe"

# 결과 폴더 이름 뒤에 붙는 이름
PROBE_NAME = "ecos_probe"

# 통계표 이름에서 찾을 기본 키워드. 이 검증이 필요로 하는 두 계열을 가리킨다
DEFAULT_KEYWORDS = ("환율", "시장금리")

# 조회 가능한 통계표만 후보로 본다. ECOS 는 목차용 상위 항목도 같은 목록에 섞어 준다
SEARCHABLE_FLAG = "Y"

# 통계표 목록 응답의 컬럼
COL_STAT_CODE = "STAT_CODE"
COL_STAT_NAME = "STAT_NAME"
COL_CYCLE = "CYCLE"
COL_SEARCHABLE = "SRCH_YN"

# 항목 목록 응답의 컬럼
COL_ITEM_CODE = "ITEM_CODE"
COL_ITEM_NAME = "ITEM_NAME"
COL_START_TIME = "START_TIME"
COL_END_TIME = "END_TIME"
COL_UNIT_NAME = "UNIT_NAME"

TABLE_COLUMNS = [
    ("통계표코드", 12, Align.LEFT),
    ("주기", 5, Align.LEFT),
    ("통계표 이름", 52, Align.LEFT),
]

ITEM_COLUMNS = [
    ("항목코드", 12, Align.LEFT),
    ("항목 이름", 30, Align.LEFT),
    ("가용 구간", 20, Align.LEFT),
    ("단위", 8, Align.LEFT),
]


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="ECOS 통계표·항목 코드를 실측해 원자료와 함께 보고합니다.")
    parser.add_argument(
        "--keyword",
        nargs="+",
        default=list(DEFAULT_KEYWORDS),
        help=f"통계표 이름에서 찾을 키워드 (기본값: {' '.join(DEFAULT_KEYWORDS)})",
    )
    parser.add_argument(
        "--stat",
        nargs="+",
        default=None,
        help="항목 목록을 받을 통계표코드 (기본값: 수집 대상으로 등록된 코드)",
    )
    return parser.parse_args()


def _save(rows: list[dict[str, object]], directory: Path, name: str) -> Path:
    """응답 원자료를 CSV 로 남긴다.

    Args:
        rows: 응답 행 목록
        directory: 저장 폴더
        name: 파일 이름 (확장자 제외)

    Returns:
        저장된 경로
    """
    path = directory / f"{name}.csv"
    pd.DataFrame(rows).to_csv(path, index=False, encoding=CSV_ENCODING)
    logger.debug(f"원자료 저장: {path} ({len(rows):,}행)")

    return path


@cli_exception_handler
def main() -> int:
    """실측을 실행하고 결과를 표로 표시한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()
    api_key = load_ecos_api_key()
    output_dir = create_run_directory(PROBE_NAME)

    # 1. 통계표 목록. 받는 즉시 저장한다
    tables = fetch_table_list(api_key)
    _save(tables, output_dir, "statistic_table_list")

    # 2. 키워드에 걸리면서 조회 가능한 통계표만 추린다
    candidates = [
        row
        for row in tables
        if row.get(COL_SEARCHABLE) == SEARCHABLE_FLAG
        and any(keyword in str(row.get(COL_STAT_NAME) or "") for keyword in args.keyword)
    ]

    table = TableLogger(TABLE_COLUMNS, logger)
    table.print_table(
        [[str(row[COL_STAT_CODE]), str(row.get(COL_CYCLE) or "-"), str(row[COL_STAT_NAME])] for row in candidates],
        title=f"키워드 {args.keyword} 에 걸린 조회 가능 통계표 (전체 {len(tables):,}건 중 {len(candidates)}건)",
    )

    # 3. 항목 목록. 기본값은 수집 대상으로 등록된 통계표다
    stat_codes = args.stat if args.stat else sorted({series.stat_code for series in ECOS_SERIES})

    for stat_code in stat_codes:
        items = fetch_item_list(stat_code, api_key)
        _save(items, output_dir, f"statistic_item_list_{stat_code}")

        item_table = TableLogger(ITEM_COLUMNS, logger)
        item_table.print_table(
            [
                [
                    str(row.get(COL_ITEM_CODE)),
                    str(row.get(COL_ITEM_NAME)),
                    f"{row.get(COL_START_TIME)}~{row.get(COL_END_TIME)}",
                    str(row.get(COL_UNIT_NAME) or "-"),
                ]
                for row in items
            ],
            title=f"통계표 {stat_code} 항목 {len(items)}건",
        )

    logger.debug(f"원자료 저장 위치: {output_dir}")

    save_metadata(
        KEY_META_ECOS_PROBE,
        {
            "keywords": args.keyword,
            "output_dir": str(output_dir),
            "table_count": len(tables),
            "candidate_count": len(candidates),
            "probed_stat_codes": stat_codes,
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
