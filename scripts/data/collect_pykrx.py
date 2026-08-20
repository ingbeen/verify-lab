#!/usr/bin/env python3
"""pykrx 국내 시세 수집 CLI

국내 ETF 의 일별 시세를 **원본가 기준으로** 받아 원시 시세 파일로 저장한다. 상장일부터 전 기간을 담는다.

**수정주가는 받지 않는다.** 사용자가 결과를 차트와 직접 대조하는 것이 이 프로젝트의 전제인데
보통의 차트는 배당 미포함이기 때문이다. 근거는 `docs/spec/index_extreme_events.md` "가격 처리" 에 있다.
수집기 모듈의 `adjusted` 인자는 남아 있으므로 필요하면 그쪽을 직접 호출한다.

외부 서버(KRX)에 실제 요청을 보내므로 **사용자만 실행한다.**
실행 명령어는 `docs/COMMANDS.md` 를 참고한다.

> **로그 주의**: pykrx 는 로그인 시 **로그인 ID 를 표준 출력에 찍는다**(비밀번호는 찍지 않는다).
> 실행 로그를 공유하거나 문서에 붙일 때 그 줄을 뺀다.
"""

import argparse

from verify_lab.data.pykrx_collector import PykrxCollectionResult, collect_pykrx_history
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 인자 없이 실행했을 때 받는 종목과 그 상장일. 검증 #1 의 국내 대상이다
DEFAULT_TICKER = "069500"
DEFAULT_START_DATE = "20021014"

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_PYKRX_COLLECT = "pykrx_collect"

# 요약 표의 컬럼 정의 (컬럼명, 폭, 정렬)
SUMMARY_COLUMNS = [
    ("가격 기준", 12, Align.LEFT),
    ("기간", 26, Align.LEFT),
    ("행 수", 10, Align.RIGHT),
    ("최근 제외", 14, Align.RIGHT),
    ("파일", 30, Align.LEFT),
]

# 컬럼 사이 여백. 오른쪽 정렬 컬럼은 값이 칸 끝에 붙으므로 다음 컬럼과 맞닿는다
COLUMN_GAP = "  "

# 화면에 표시할 가격 기준 이름
DISPLAY_RAW = "원본가"
DISPLAY_ADJUSTED = "수정주가"


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="pykrx 에서 국내 ETF 시세를 원본가 기준으로 받아 저장합니다 (KRX 계정 필요).")
    parser.add_argument("--ticker", default=DEFAULT_TICKER, help=f"종목 티커 (기본값: {DEFAULT_TICKER})")
    parser.add_argument(
        "--start",
        default=DEFAULT_START_DATE,
        help=f"조회 시작일 YYYYMMDD, 보통 상장일 (기본값: {DEFAULT_START_DATE})",
    )
    return parser.parse_args()


def _summary_row(result: PykrxCollectionResult) -> list[str]:
    """수집 결과 한 건을 요약 표의 행으로 만든다.

    Args:
        result: 수집 결과

    Returns:
        표 컬럼 순서에 맞춘 문자열 목록
    """
    return [
        DISPLAY_ADJUSTED if result.adjusted else DISPLAY_RAW,
        f"{result.start_date} ~ {result.end_date}",
        f"{result.row_count:,}",
        f"{result.excluded_recent_count}행",
        f"{COLUMN_GAP}{result.path.name}",
    ]


def _metadata(result: PykrxCollectionResult) -> dict[str, object]:
    """수집 결과 한 건을 실행 이력용 dict 로 만든다.

    Args:
        result: 수집 결과

    Returns:
        메타데이터 dict
    """
    return {
        "adjusted": result.adjusted,
        "path": str(result.path),
        "row_count": result.row_count,
        "start_date": str(result.start_date),
        "end_date": str(result.end_date),
        "excluded_recent_count": result.excluded_recent_count,
    }


@cli_exception_handler
def main() -> int:
    """원본가 기준으로 수집을 실행하고 결과를 표로 표시한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()

    raw_result = collect_pykrx_history(args.ticker, args.start, adjusted=False)

    table = TableLogger(SUMMARY_COLUMNS, logger)
    table.print_table(
        [_summary_row(raw_result)],
        title=f"수집 결과 — {raw_result.ticker} (저장 폴더: {raw_result.path.parent})",
    )

    save_metadata(
        KEY_META_PYKRX_COLLECT,
        {
            "ticker": raw_result.ticker,
            "start_date": args.start,
            "raw": _metadata(raw_result),
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
