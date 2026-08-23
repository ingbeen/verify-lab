#!/usr/bin/env python3
"""역방향 매매 규칙 실행 CLI

확정 규칙(손절 3분할 · 종가 집행 · 수익 시 전량 청산)을 **대상 3종 × 보유 한도 3종**에
적용해 체결 내역과 집계를 낸다. 규칙 전문과 확정 근거는
`docs/strategy/역방향_매매_규칙.md` 가 SoT다.

**보유 한도를 하나로 고르지 않는다.** 한 포지션은 한도 하나만 가질 수 있으므로 한도별 결과는
비교표이며, 하나를 골라 산출하면 표본에 맞춘 튜닝이 된다.

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

from verify_lab.report.constants import PERCENT_DECIMALS, RATE_TO_PERCENT
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.strategy.constants import (
    DISPLAY_EVENT_COUNT,
    DISPLAY_HOLD_LIMIT,
    DISPLAY_MAX,
    DISPLAY_MEAN,
    DISPLAY_MEAN_HOLD,
    DISPLAY_MIN,
    DISPLAY_PARAMETER,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_TICKER,
    DISPLAY_TOTAL,
    DISPLAY_WIN_RATE,
    HOLD_LIMITS,
    STOP_LOSS_LEVELS,
    STRATEGY_NAME,
    TARGETS,
    Target,
)
from verify_lab.strategy.runner import KEY_SUMMARY, KEY_TRADES, StrategyOutputs, run_strategy
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_REVERSE_TRADING = "reverse_trading_strategy"

# 산출물 파일 이름
TRADES_FILENAME = "trades.csv"
SUMMARY_FILENAME = "summary_by_target.csv"

# 집계 표의 컬럼 정의 (컬럼명, 폭, 정렬)
SUMMARY_COLUMNS = [
    (DISPLAY_TICKER, 11, Align.LEFT),
    (DISPLAY_PARAMETER, 8, Align.LEFT),
    (DISPLAY_HOLD_LIMIT, 8, Align.LEFT),
    (DISPLAY_SIGNAL_COUNT, 6, Align.RIGHT),
    (DISPLAY_EVENT_COUNT, 6, Align.RIGHT),
    (DISPLAY_TOTAL, 10, Align.RIGHT),
    (DISPLAY_MEAN, 9, Align.RIGHT),
    (DISPLAY_WIN_RATE, 9, Align.RIGHT),
    (DISPLAY_MAX, 9, Align.RIGHT),
    (DISPLAY_MIN, 9, Align.RIGHT),
    (DISPLAY_MEAN_HOLD, 12, Align.RIGHT),
]

# 산출물 표의 컬럼 정의
OUTPUT_COLUMNS = [("파일", 26, Align.LEFT), ("행 수", 8, Align.RIGHT)]


def _build_parser() -> argparse.ArgumentParser:
    """명령행 인자 파서를 만든다.

    **손절선과 대상 목록은 인자가 아니다.** 확정된 규칙을 그대로 적용하는 것이 이 스크립트의
    설계이며, 값을 골라 넣는 노브로 쓰면 표본에 맞춘 튜닝이 된다.

    Returns:
        인자 파서
    """
    parser = argparse.ArgumentParser(description="역방향 매매 규칙을 대상별·보유 한도별로 실행합니다.")
    parser.add_argument(
        "--target",
        nargs="+",
        choices=sorted({target.dataset.key for target in TARGETS}),
        default=None,
        help="실행할 종목 (기본값: 전부)",
    )

    return parser


def _selected_targets(keys: list[str] | None) -> list[Target]:
    """실행할 대상을 고른다.

    Args:
        keys: 종목 이름 목록. `None` 이면 전부

    Returns:
        선택된 대상 목록
    """
    if keys is None:
        return list(TARGETS)

    return [target for target in TARGETS if target.dataset.key in keys]


def _print_rule() -> None:
    """적용한 규칙을 먼저 보여준다."""
    levels = " → ".join(f"-{level * RATE_TO_PERCENT:.0f}%" for level in STOP_LOSS_LEVELS)
    limits = " / ".join(f"D+{limit}" for limit in HOLD_LIMITS)
    logger.debug(f"진입: 신호일 종가 (자금 {len(STOP_LOSS_LEVELS)}등분)")
    logger.debug(f"손절: {levels} — 전부 진입가 기준, 보유 기간 내내 고정")
    logger.debug(f"청산: 종가가 진입가 위면 남은 전량 청산, 손실이면 한도까지 보유 ({limits})")


def _print_summary(outputs: StrategyOutputs) -> None:
    """대상별·한도별 집계를 표로 보여준다.

    Args:
        outputs: 실행 산출물
    """
    rows = [
        [
            row[DISPLAY_TICKER],
            row[DISPLAY_PARAMETER],
            row[DISPLAY_HOLD_LIMIT],
            f"{row[DISPLAY_SIGNAL_COUNT]:,}",
            f"{row[DISPLAY_EVENT_COUNT]:,}",
            f"{row[DISPLAY_TOTAL]:+.{PERCENT_DECIMALS}f}",
            f"{row[DISPLAY_MEAN]:+.{PERCENT_DECIMALS}f}",
            f"{row[DISPLAY_WIN_RATE]:.{PERCENT_DECIMALS}f}",
            f"{row[DISPLAY_MAX]:+.{PERCENT_DECIMALS}f}",
            f"{row[DISPLAY_MIN]:+.{PERCENT_DECIMALS}f}",
            f"{row[DISPLAY_MEAN_HOLD]:.2f}",
        ]
        for _, row in outputs.summary.iterrows()
    ]
    TableLogger(SUMMARY_COLUMNS, logger).print_table(rows, title="대상별 · 보유 한도별 성적")


@cli_exception_handler
def main() -> None:
    """역방향 매매 규칙을 실행하고 산출물을 저장한다."""
    args = _build_parser().parse_args()
    targets = _selected_targets(args.target)

    _print_rule()
    outputs = run_strategy(targets)
    _print_summary(outputs)

    directory = create_run_directory(STRATEGY_NAME)
    save_table(directory, TRADES_FILENAME, outputs.trades)
    save_table(directory, SUMMARY_FILENAME, outputs.summary)
    save_run_summary(directory, outputs.meta)

    counts = outputs.meta["row_counts"]
    TableLogger(OUTPUT_COLUMNS, logger).print_table(
        [[TRADES_FILENAME, f"{counts[KEY_TRADES]:,}"], [SUMMARY_FILENAME, f"{counts[KEY_SUMMARY]:,}"]],
        title=f"산출물 (저장 폴더: {directory})",
    )
    save_metadata(
        KEY_META_REVERSE_TRADING,
        {
            "targets": [f"{target.dataset.ticker} K={target.rank_cut}" for target in targets],
            "hold_limits": list(HOLD_LIMITS),
            "output": str(directory),
        },
    )
    logger.debug(f"체결 {counts[KEY_TRADES]:,}건, 집계 {counts[KEY_SUMMARY]:,}행을 산출했습니다")


if __name__ == "__main__":
    main()
