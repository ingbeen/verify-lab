#!/usr/bin/env python3
"""KRX 국내 선물 계약별 시세 수집 CLI

코스피200·코스닥150 선물의 계약별 일별 시세를 받아 원시 시세 파일로 저장한다.
상품마다 파일 하나이고 `Contract` 컬럼으로 계약을 가른다 — 계약이 100개를 넘어
파일로 나누면 폴더가 계약으로 뒤덮인다.

**한 번 실행에 수백 번 요청이 나간다.** 계약 목록을 얻는 스냅숏이 한 달 간격으로 돌고,
그 뒤 계약마다 기간 시세를 받는다. 코스피200 은 1996년부터라 30년치다.
외부 서버(KRX)에 실제 요청을 보내므로 **같은 데이터를 이유 없이 다시 받지 않는다.**

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.

> **로그 주의**: pykrx 는 로그인 시 **로그인 ID 를 표준 출력에 찍는다**(비밀번호는 찍지 않는다).
> 실행 로그를 공유하거나 문서에 붙일 때 그 줄을 뺀다.
"""

import argparse

from verify_lab.data.krx_futures_collector import (
    PRODUCT_FIRST_TRADING_DAY,
    PRODUCT_KOSDAQ150,
    PRODUCT_KOSPI200,
    FuturesCollectionResult,
    collect_futures_history,
)
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 인자 없이 실행했을 때 받는 상품. 검증 #9 가 재는 두 지수다
DEFAULT_PRODUCTS = [PRODUCT_KOSPI200, PRODUCT_KOSDAQ150]

# 상품 코드를 사람이 읽는 이름으로 바꾼다. 코드만으로는 어느 지수인지 알 수 없다
PRODUCT_DISPLAY_NAMES = {
    PRODUCT_KOSPI200: "코스피200 선물",
    PRODUCT_KOSDAQ150: "코스닥150 선물",
}

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_KRX_FUTURES_COLLECT = "krx_futures_collect"

# 요약 표의 컬럼 정의 (컬럼명, 폭, 정렬)
SUMMARY_COLUMNS = [
    ("상품", 16, Align.LEFT),
    ("기간", 26, Align.LEFT),
    ("행 수", 10, Align.RIGHT),
    ("계약", 8, Align.RIGHT),
    ("야간 제외", 12, Align.RIGHT),
    ("미개시 제외", 14, Align.RIGHT),
    ("최근 제외", 12, Align.RIGHT),
    ("파일", 26, Align.LEFT),
]

# 컬럼 사이 여백. 오른쪽 정렬 컬럼은 값이 칸 끝에 붙으므로 다음 컬럼과 맞닿는다
COLUMN_GAP = "  "


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="KRX 에서 국내 선물 계약별 시세를 받아 원시 시세 파일로 저장합니다 (KRX 계정 필요).")
    parser.add_argument(
        "--product",
        action="append",
        choices=sorted(PRODUCT_FIRST_TRADING_DAY),
        help=f"상품 코드. 여러 번 줄 수 있다 (기본값: {' '.join(DEFAULT_PRODUCTS)})",
    )
    parser.add_argument(
        "--start",
        default=None,
        help="조회 시작일 YYYYMMDD. 생략하면 상품별 최초 거래일부터 전 기간을 받는다",
    )
    return parser.parse_args()


def _summary_row(result: FuturesCollectionResult) -> list[str]:
    """수집 결과를 요약 표의 한 행으로 바꾼다.

    Args:
        result: 한 상품의 수집 결과

    Returns:
        `SUMMARY_COLUMNS` 순서에 맞춘 문자열 목록
    """
    return [
        PRODUCT_DISPLAY_NAMES.get(result.product_id, result.product_id),
        f"{result.start_date} ~ {result.end_date}",
        f"{result.row_count:,}",
        f"{result.contract_count:,}",
        f"{result.excluded_night_count:,}행",
        f"{result.excluded_dormant_count:,}행",
        f"{result.excluded_recent_count:,}행",
        f"{COLUMN_GAP}{result.path.name}",
    ]


def _metadata_entry(result: FuturesCollectionResult) -> dict[str, object]:
    """수집 결과를 실행 이력 항목으로 바꾼다.

    Args:
        result: 한 상품의 수집 결과

    Returns:
        meta.json 에 남길 dict
    """
    return {
        "product_id": result.product_id,
        "path": str(result.path),
        "row_count": result.row_count,
        "contract_count": result.contract_count,
        "catalog_count": result.catalog_count,
        "start_date": str(result.start_date),
        "end_date": str(result.end_date),
        "excluded_night_count": result.excluded_night_count,
        "excluded_dormant_count": result.excluded_dormant_count,
        "excluded_recent_count": result.excluded_recent_count,
        "empty_contract_count": result.empty_contract_count,
        "missing_spot_count": result.missing_spot_count,
    }


@cli_exception_handler
def main() -> int:
    """수집을 실행하고 결과를 표로 표시한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()
    products = args.product or DEFAULT_PRODUCTS

    results = [collect_futures_history(product_id, start_date=args.start) for product_id in products]

    TableLogger(SUMMARY_COLUMNS, logger).print_table(
        [_summary_row(result) for result in results],
        title=f"선물 시세 수집 결과 (저장 폴더: {results[0].path.parent})",
    )

    save_metadata(
        KEY_META_KRX_FUTURES_COLLECT,
        {
            "products": products,
            "start_date": args.start,
            "collected": [_metadata_entry(result) for result in results],
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
