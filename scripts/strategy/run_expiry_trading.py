#!/usr/bin/env python3
"""옵션 만기일 매매의 손절 격자 실행 CLI

`docs/research/옵션_만기일.md` 0장의 **등급 3/3 7칸**에 손절선 격자를 걸어 성적을 낸다.
맨몸 성적은 그 문서가 이미 냈고, 여기가 더하는 것은 **손절 하나**다.

**아직 확정된 규칙이 아니다.** 손절선을 고르기 위한 재료이며, 값 선택은 격자를 본 사용자가
한다 (루트 `CLAUDE.md` 측정의 원칙 1). 그래서 이 스크립트는 손절선을 인자로 받지 않고
**격자 전체를 항상 낸다** — 값을 골라 넣는 노브로 쓰면 표본에 맞춘 튜닝이 된다.

**무손절 행이 칸마다 함께 나온다.** 손절의 실질 효용은 수익이 아니라 최악 통제이므로
대조 없이는 무엇을 막았는지 보이지 않는다 (`.claude/rules/strategy.md`).

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

import pandas as pd

from verify_lab.report.tables import print_dataframe
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.strategy.constants import (
    DISPLAY_STOP_LEVEL,
    EXPIRY_CELLS,
    EXPIRY_STOP_LEVELS,
    EXPIRY_STRATEGY_NAME,
    NO_STOP_LABEL,
    ExpiryCell,
)
from verify_lab.strategy.expiry_runner import ExpiryOutputs, run_expiry_trading
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_EXPIRY_TRADING = "expiry_trading_strategy"

# 산출물 파일 이름
GRID_FILENAME = "stop_loss_grid.csv"
TRADES_FILENAME = "trades.csv"

# 산출물 표의 컬럼 이름. **폭은 적지 않는다** — `print_dataframe` 이 내용에서 계산한다
DISPLAY_FILE = "파일"
DISPLAY_ROW_COUNT = "행 수"


def _build_parser() -> argparse.ArgumentParser:
    """명령행 인자 파서를 만든다.

    **손절선은 인자가 아니다.** 격자 전체를 내는 것이 이 스크립트의 설계다.

    Returns:
        인자 파서
    """
    parser = argparse.ArgumentParser(description="옵션 만기일 매매의 손절 격자를 산출합니다.")
    parser.add_argument(
        "--ticker",
        nargs="+",
        choices=sorted({cell.dataset_key for cell in EXPIRY_CELLS}),
        default=None,
        help="실행할 종목 (기본값: 전부)",
    )

    return parser


def _selected_cells(keys: list[str] | None) -> list[ExpiryCell]:
    """실행할 칸을 고른다.

    Args:
        keys: 종목 이름 목록. `None` 이면 전부

    Returns:
        선택된 칸 목록

    Raises:
        ValueError: 고른 종목에 해당하는 칸이 하나도 없는 경우
    """
    if keys is None:
        return list(EXPIRY_CELLS)

    selected = [cell for cell in EXPIRY_CELLS if cell.dataset_key in set(keys)]
    if not selected:
        raise ValueError(f"고른 종목에 해당하는 칸이 없습니다: {keys}")

    return selected


def _print_scope(cells: list[ExpiryCell]) -> None:
    """무엇을 도는지 먼저 보여 준다.

    **미국 9월 세 칸이 같은 날 같은 방향**이라는 사실을 함께 적는다 — 산출물을 세 번의
    확인으로 읽으면 안 되기 때문이다.

    Args:
        cells: 실행할 칸 목록
    """
    logger.debug(
        f"대상 {len(cells)}칸 × 손절선 {len(EXPIRY_STOP_LEVELS)}종 + {NO_STOP_LABEL} "
        f"= {len(cells) * (len(EXPIRY_STOP_LEVELS) + 1)}행"
    )
    logger.debug("미국 9월 세 칸(QQQ·SPY·DIA)은 같은 날 같은 방향이라 독립된 세 번의 기회가 아닙니다")


def _print_no_stop(outputs: ExpiryOutputs) -> None:
    """무손절 행만 먼저 보여 준다.

    이 행이 `docs/research/옵션_만기일.md` 12A.4 의 방향 기대값과 맞아야 두 계층이
    같은 것을 재고 있다는 뜻이다.

    Args:
        outputs: 실행 산출물
    """
    no_stop = outputs.grid[outputs.grid[DISPLAY_STOP_LEVEL] == NO_STOP_LABEL]
    print_dataframe(no_stop, logger, title=f"{NO_STOP_LABEL} — 맨몸 성적 (결과 문서 12A.4 와 대조)")


@cli_exception_handler
def main() -> int:
    """손절 격자를 실행하고 산출물을 저장한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = _build_parser().parse_args()
    cells = _selected_cells(args.ticker)

    _print_scope(cells)
    outputs = run_expiry_trading(cells)
    _print_no_stop(outputs)

    directory = create_run_directory(EXPIRY_STRATEGY_NAME)
    save_table(directory, GRID_FILENAME, outputs.grid)
    save_table(directory, TRADES_FILENAME, outputs.trades)
    save_run_summary(
        directory,
        {
            "cells": [f"{cell.dataset_key} {cell.expiry_month}월" for cell in cells],
            "stop_levels": list(EXPIRY_STOP_LEVELS),
            "row_counts": {"grid": len(outputs.grid), "trades": len(outputs.trades)},
        },
    )

    print_dataframe(
        pd.DataFrame(
            [
                {DISPLAY_FILE: GRID_FILENAME, DISPLAY_ROW_COUNT: len(outputs.grid)},
                {DISPLAY_FILE: TRADES_FILENAME, DISPLAY_ROW_COUNT: len(outputs.trades)},
            ]
        ),
        logger,
        title=f"산출물 (저장 폴더: {directory})",
    )
    save_metadata(
        KEY_META_EXPIRY_TRADING,
        {
            "cells": [f"{cell.dataset_key} {cell.expiry_month}월" for cell in cells],
            "stop_level_count": len(EXPIRY_STOP_LEVELS),
            "output": str(directory),
        },
    )
    logger.debug(f"격자 {len(outputs.grid):,}행, 체결 {len(outputs.trades):,}건을 산출했습니다")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
