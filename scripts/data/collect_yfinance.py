#!/usr/bin/env python3
"""yfinance 시세 수집 CLI

미국 상장 종목의 전 기간 일별 시세를 받아 원시 시세 파일로 저장한다.

외부 서버(Yahoo Finance)에 실제 요청을 보내므로 **같은 데이터를 이유 없이 다시 받지 않는다.**
실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

from verify_lab.data.yfinance_collector import collect_yfinance_history
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 인자 없이 실행했을 때 받는 종목. 검증 #1 의 미국 측 대상이다
DEFAULT_TICKER = "QQQ"

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_YFINANCE = "yfinance_collect"

# 요약 표의 컬럼 정의 (컬럼명, 폭, 정렬)
SUMMARY_COLUMNS = [("항목", 14, Align.LEFT), ("값", 60, Align.LEFT)]

# 화면에 표시할 가격 기준 이름
DISPLAY_RAW = "원본가"
DISPLAY_ADJUSTED = "수정주가"


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="yfinance 에서 전 기간 일별 시세를 받아 원시 시세 파일로 저장합니다.")
    parser.add_argument(
        "--ticker",
        default=DEFAULT_TICKER,
        help=f"yfinance 종목 코드 (기본값: {DEFAULT_TICKER})",
    )
    parser.add_argument(
        "--adjusted",
        action="store_true",
        help="수정주가로 받는다 (기본값: 원본가). 원본가가 기본인 이유는 수집기 모듈 docstring 참고",
    )
    return parser.parse_args()


@cli_exception_handler
def main() -> int:
    """수집을 실행하고 결과를 표로 표시한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()

    result = collect_yfinance_history(args.ticker, adjusted=args.adjusted)

    table = TableLogger(SUMMARY_COLUMNS, logger)
    table.print_table(
        [
            ["종목", result.ticker],
            ["가격 기준", DISPLAY_ADJUSTED if result.adjusted else DISPLAY_RAW],
            ["기간", f"{result.start_date} ~ {result.end_date}"],
            ["행 수", f"{result.row_count:,}"],
            ["최근 제외", f"{result.excluded_recent_count}행"],
            ["저장 위치", str(result.path)],
        ],
        title="수집 결과",
    )

    save_metadata(
        KEY_META_YFINANCE,
        {
            "ticker": result.ticker,
            "adjusted": result.adjusted,
            "path": str(result.path),
            "row_count": result.row_count,
            "start_date": str(result.start_date),
            "end_date": str(result.end_date),
            "excluded_recent_count": result.excluded_recent_count,
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
