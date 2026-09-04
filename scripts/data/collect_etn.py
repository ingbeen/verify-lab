#!/usr/bin/env python3
"""KRX ETN 시세 수집 CLI

국내 상장 ETN 의 일별 시세를 받아 원시 시세 파일로 저장한다. 상장일부터 전 기간을 담는다.

**ETN 은 가격 기준이 하나뿐이다.** 분배금을 지급하지 않고 지표가치에서 제비용만 차감하므로
`collect_pykrx.py` 의 `--adjusted` 에 해당하는 인자가 없다. 대신 `--indicative-value` 로
증권당 지표가치(ETF 의 NAV 에 해당)를 단일 값 시계열로 받는다.

외부 서버(KRX)에 실제 요청을 보내므로 **같은 데이터를 이유 없이 다시 받지 않는다.**
실행 명령어는 `docs/COMMANDS.md` 를 참고한다.

> **로그 주의**: pykrx 는 로그인 시 **로그인 ID 를 표준 출력에 찍는다**(비밀번호는 찍지 않는다).
> 실행 로그를 공유하거나 문서에 붙일 때 그 줄을 뺀다.
"""

import argparse

from verify_lab.data.etn_collector import collect_etn_history, collect_etn_indicative_value
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 인자 없이 실행했을 때 받는 종목과 그 상장일.
# 검증 #8 의 코스닥150 -2배 본선 종목이다 (삼성 인버스 2X 코스닥150 선물 ETN)
DEFAULT_TICKER = "530107"
DEFAULT_START_DATE = "20221017"

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_ETN_COLLECT = "etn_collect"

# 요약 표의 컬럼 정의 (컬럼명, 폭, 정렬)
SUMMARY_COLUMNS = [
    ("종류", 12, Align.LEFT),
    ("기간", 26, Align.LEFT),
    ("행 수", 10, Align.RIGHT),
    ("최근 제외", 14, Align.RIGHT),
    ("파일", 30, Align.LEFT),
]

# 컬럼 사이 여백. 오른쪽 정렬 컬럼은 값이 칸 끝에 붙으므로 다음 컬럼과 맞닿는다
COLUMN_GAP = "  "

# 화면에 표시할 수집 종류 이름
DISPLAY_PRICE = "시세"
DISPLAY_INDICATIVE_VALUE = "지표가치"


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="KRX 에서 ETN 시세를 받아 원시 시세 파일로 저장합니다 (KRX 계정 필요).")
    parser.add_argument("--ticker", default=DEFAULT_TICKER, help=f"종목 코드 (기본값: {DEFAULT_TICKER})")
    parser.add_argument(
        "--start",
        default=DEFAULT_START_DATE,
        help=f"조회 시작일 YYYYMMDD, 보통 상장일 (기본값: {DEFAULT_START_DATE})",
    )
    parser.add_argument(
        "--indicative-value",
        action="store_true",
        help="시세 대신 증권당 지표가치를 받아 `storage/series/` 에 단일 값 시계열로 저장한다",
    )
    return parser.parse_args()


def _collect_indicative_value(ticker: str, start_date: str) -> int:
    """지표가치를 수집하고 결과를 표로 표시한다.

    Args:
        ticker: 종목 코드
        start_date: 조회 시작일 (YYYYMMDD)

    Returns:
        종료 코드 (성공 0)
    """
    result = collect_etn_indicative_value(ticker, start_date)

    TableLogger(SUMMARY_COLUMNS, logger).print_table(
        [
            [
                DISPLAY_INDICATIVE_VALUE,
                f"{result.start_date} ~ {result.end_date}",
                f"{result.row_count:,}",
                f"{result.excluded_recent_count}행",
                f"{COLUMN_GAP}{result.path.name}",
            ]
        ],
        title=f"지표가치 수집 결과 — {result.ticker} (저장 폴더: {result.path.parent})",
    )

    save_metadata(
        KEY_META_ETN_COLLECT,
        {
            "ticker": result.ticker,
            "start_date": start_date,
            "indicative_value": {
                "path": str(result.path),
                "row_count": result.row_count,
                "start_date": str(result.start_date),
                "end_date": str(result.end_date),
                "excluded_recent_count": result.excluded_recent_count,
            },
        },
    )

    return 0


@cli_exception_handler
def main() -> int:
    """수집을 실행하고 결과를 표로 표시한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()

    if args.indicative_value:
        return _collect_indicative_value(args.ticker, args.start)

    result = collect_etn_history(args.ticker, args.start)

    TableLogger(SUMMARY_COLUMNS, logger).print_table(
        [
            [
                DISPLAY_PRICE,
                f"{result.start_date} ~ {result.end_date}",
                f"{result.row_count:,}",
                f"{result.excluded_recent_count}행",
                f"{COLUMN_GAP}{result.path.name}",
            ]
        ],
        title=f"수집 결과 — {result.ticker} (ISIN {result.isin}, 저장 폴더: {result.path.parent})",
    )

    save_metadata(
        KEY_META_ETN_COLLECT,
        {
            "ticker": result.ticker,
            "isin": result.isin,
            "start_date": args.start,
            "price": {
                "path": str(result.path),
                "row_count": result.row_count,
                "start_date": str(result.start_date),
                "end_date": str(result.end_date),
                "excluded_recent_count": result.excluded_recent_count,
            },
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
