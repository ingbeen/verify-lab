#!/usr/bin/env python3
"""코스닥 월말 매매의 손절 격자 실행 CLI

검증 #10이 낸 「매월 20일 종가 매수 → 그 달 말일 종가 매도」에 손절선을 걸어
**손절이 무엇을 막았는가**를 수치로 낸다.

**12개월 × 두 방향 × (손절선 8종 + 무손절)** 을 전부 돈다. 눈에 띄는 달만 돌리면
그 선택이 손절 결과에도 그대로 실린다.

**맨몸 성적이다** — 수수료·슬리피지·세금을 넣지 않는다 (루트 `CLAUDE.md` 2026-09-06 확정).

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

from verify_lab.report.tables import print_dataframe
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.strategy.constants import (
    DISPLAY_DIRECTION,
    DISPLAY_GAP_STOP_COUNT,
    DISPLAY_INTRADAY_STOP_COUNT,
    DISPLAY_MEAN,
    DISPLAY_MIN,
    DISPLAY_PERIOD,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_STOP_LEVEL,
    DISPLAY_TICKER,
    DISPLAY_TOTAL,
    DISPLAY_WIN_RATE,
    PERIOD_ALL,
)
from verify_lab.strategy.month_end_runner import DISPLAY_MONTH, run_month_end_trading
from verify_lab.studies.month_end.constants import DATASETS_KOSDAQ
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_STRATEGY = "kosdaq_month_end_trading"

# 산출물 폴더 이름
STUDY_NAME = "kosdaq_month_end_trading"

# 화면에 낼 컬럼. 전 컬럼을 내면 가로로 넘쳐 읽을 수 없다
HEADLINE_COLUMNS = [
    DISPLAY_TICKER,
    DISPLAY_MONTH,
    DISPLAY_DIRECTION,
    DISPLAY_STOP_LEVEL,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_TOTAL,
    DISPLAY_MEAN,
    DISPLAY_WIN_RATE,
    DISPLAY_MIN,
    DISPLAY_GAP_STOP_COUNT,
    DISPLAY_INTRADAY_STOP_COUNT,
]

# 화면에 낼 달. **산출물에는 12개월이 다 있고** 화면만 좁힌다 — 검증 #10에서
# 1차 게이트를 통과한 달이라 지금 볼 것이 그쪽이다
HEADLINE_MONTHS = (4, 6, 9, 12)


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="코스닥 월말 매매(20일 매수 → 말일 매도)에 손절 격자를 걸어 성적을 냅니다.")
    parser.add_argument(
        "--ticker",
        action="append",
        help="측정할 종목 또는 지수 코드. 여러 번 줄 수 있다 (기본값: ETF 둘 + 지수 둘). " "지수는 장중 손절을 잴 수 없어 무손절 성적으로만 나온다",
    )
    return parser.parse_args()


def _selected_datasets(tickers: list[str] | None) -> tuple:
    """인자로 고른 대상만 남긴다.

    **지수도 기본 대상에 든다.** 장중 손절은 못 걸지만 무손절 성적은 낼 수 있고,
    ETF 11년으로는 볼 수 없는 기간(코스닥 종합 30년)이 거기 있다.

    Args:
        tickers: 종목 또는 지수 코드 목록. `None` 이면 전부

    Returns:
        고른 대상 목록

    Raises:
        ValueError: 알 수 없는 코드를 지목한 경우
    """
    if not tickers:
        return DATASETS_KOSDAQ

    known = {dataset.ticker: dataset for dataset in DATASETS_KOSDAQ}
    unknown = [ticker for ticker in tickers if ticker not in known]
    if unknown:
        raise ValueError(f"알 수 없는 대상입니다: {unknown} (가능한 값: {sorted(known)})")

    return tuple(known[ticker] for ticker in tickers)


@cli_exception_handler
def main() -> int:
    """손절 격자를 돌리고 결과를 저장한 뒤 요약을 표시한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()
    datasets = _selected_datasets(args.ticker)

    outputs = run_month_end_trading(datasets)

    directory = create_run_directory(STUDY_NAME)
    save_table(directory, "trades.csv", outputs.trades)
    save_table(directory, "performance.csv", outputs.performance)
    save_table(directory, "performance_fixed_stop.csv", outputs.performance_fixed_stop)
    save_run_summary(directory, outputs.summary)

    # 화면은 **저장한 표에서 발췌**한다 — 따로 가공하면 화면에서 본 숫자를 CSV 에서 찾지 못한다
    overall = outputs.performance[
        (outputs.performance[DISPLAY_PERIOD] == PERIOD_ALL) & (outputs.performance[DISPLAY_MONTH].isin(HEADLINE_MONTHS))
    ]
    if not overall.empty:
        print_dataframe(
            overall[HEADLINE_COLUMNS],
            logger,
            title=f"손절 격자 — 전체 구간, {', '.join(str(month) for month in HEADLINE_MONTHS)}월 (전 12개월은 CSV 에)",
        )

    logger.debug(f"산출물 저장 위치: {directory}")

    save_metadata(
        KEY_META_STRATEGY,
        {
            "directory": str(directory),
            "tickers": [dataset.ticker for dataset in datasets],
            "stop_levels": outputs.summary["stop_levels"],
            "fixed_stop_level": outputs.summary["fixed_stop_level"],
            "cost": outputs.summary["cost"],
            "row_counts": outputs.summary["row_counts"],
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
