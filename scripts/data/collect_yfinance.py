#!/usr/bin/env python3
"""yfinance 시세 수집 CLI

미국 상장 종목의 전 기간 일별 시세를 받아 원시 시세 파일로 저장한다.
**지수는 `--index` 로 받으며 종가 하나짜리 계열이 된다** — 왜 OHLCV 가 아닌지는
수집기의 `collect_yfinance_index` docstring 이 SoT다.

외부 서버(Yahoo Finance)에 실제 요청을 보내므로 **같은 데이터를 이유 없이 다시 받지 않는다.**
실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

from verify_lab.data.yfinance_collector import collect_yfinance_history, collect_yfinance_index
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
DISPLAY_INDEX_SERIES = "종가 계열"


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="yfinance 에서 전 기간 일별 시세를 받아 원시 시세 파일로 저장합니다.")
    # **둘 중 하나만 받는다.** 함께 주면 어느 쪽을 받았는지 산출물만 봐서는 알 수 없다
    target = parser.add_mutually_exclusive_group()
    target.add_argument(
        "--ticker",
        help=f"yfinance 종목 코드 (기본값: {DEFAULT_TICKER}). 시세 스키마로 storage/market/ 에 저장한다",
    )
    target.add_argument(
        "--index",
        help="yfinance 지수 심볼(예: ^GSPC · ^IXIC). **종가 계열**로 storage/series/ 에 저장하며 "
        "파일명에서는 접두 ^ 를 뗀다. 지수는 살 수 없어 시가 집행이 불가능하고, "
        "옛 구간의 고가·저가가 종가로 채워져 있어 OHLCV 로 받으면 장중 낙폭이 조용히 사라진다",
    )
    parser.add_argument(
        "--adjusted",
        action="store_true",
        help="수정주가로 받는다 (기본값: 원본가). 원본가가 기본인 이유는 수집기 모듈 docstring 참고. " "**지수에는 해당하지 않는다** — 분배금이 없다",
    )
    return parser.parse_args()


def _collect_index(symbol: str) -> None:
    """지수를 종가 계열로 받아 결과를 표로 표시하고 이력에 남긴다.

    Args:
        symbol: yfinance 지수 심볼
    """
    result = collect_yfinance_index(symbol)

    table = TableLogger(SUMMARY_COLUMNS, logger)
    table.print_table(
        [
            ["지수", f"{result.symbol} ({result.ticker})"],
            ["가격 기준", DISPLAY_INDEX_SERIES],
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
            "symbol": result.symbol,
            "ticker": result.ticker,
            "kind": DISPLAY_INDEX_SERIES,
            "path": str(result.path),
            "row_count": result.row_count,
            "start_date": str(result.start_date),
            "end_date": str(result.end_date),
            "excluded_recent_count": result.excluded_recent_count,
        },
    )


@cli_exception_handler
def main() -> int:
    """수집을 실행하고 결과를 표로 표시한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()

    # **`is not None` 으로 가른다.** `if args.index:` 로 두면 `--index ''` 가 거짓이라
    # **지수 경로를 건너뛰고 기본 종목(QQQ)을 다시 받아 원시 시세를 덮어쓴다** —
    # 수집기의 「지수 심볼이 비어 있습니다」 가드에 닿지도 못하고, 재수집은 이미 발행된
    # 결과 문서의 수치를 재현 불가로 만든다 (`.claude/rules/session-bootstrap.md` 6절)
    if args.index is not None:
        # **`--adjusted` 를 조용히 무시하지 않는다.** 지수는 분배금이 없어 그 인자가 뜻을
        # 갖지 않는데, 받아 놓고 버리면 사용자는 수정주가를 받았다고 믿고 산출물로는
        # 구별할 수 없다 — 위 배타 그룹을 둔 것과 같은 이유다
        if args.adjusted:
            raise ValueError("--adjusted 는 지수에 쓸 수 없습니다 (지수는 분배금이 없습니다). --index 만 주세요")

        _collect_index(args.index)
        return 0

    # **`or` 로 두면 `--ticker ''` 가 거짓이라 기본 종목으로 빠져 QQQ 를 덮어쓴다** —
    # 수집기의 「종목 코드가 비어 있습니다」 가드에 닿지 못한다. `--index` 와 같은 이유로 `is None` 을 쓴다
    ticker = DEFAULT_TICKER if args.ticker is None else args.ticker
    result = collect_yfinance_history(ticker, adjusted=args.adjusted)

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
