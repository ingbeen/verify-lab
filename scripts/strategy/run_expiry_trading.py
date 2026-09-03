#!/usr/bin/env python3
"""옵션 만기일 매매 실행 CLI

`docs/research/옵션_만기일.md` 0장에서 **1차 게이트를 넘은 8칸**에 손절선 격자를 걸어 성적을 낸다.
맨몸 성적은 그 문서가 이미 냈고, 여기가 더하는 것은 **손절 하나**다.

**등급이 낮은 칸도 뺀 것이 없다.** QQQ 12월은 등급 0/3 이지만 게이트를 넘었으므로 함께 낸다 —
등급으로 빼면 60칸에서 통계량 좋은 칸만 고르는 사후 선택이 된다 (`docs/spec/option_expiry.md` 결정 ㊳).

**손절선은 확정값 -5% 하나다** (`EXPIRY_STOP_LEVEL`). 값을 인자로 열지 않는다 —
값을 옮겨 가며 성적을 보면 표본에 맞춘 튜닝이 된다. 고른 근거와 탈락안은
`docs/spec/option_expiry.md` 결정 ㊴ 에 있다.

**`--grid` 로 손절선 격자를 낼 수 있다.** 무손절 + -1.0%~-10.0% 를 전부 내며,
**시세를 재수집해 「평평한 구간」을 다시 찾아야 할 때** 쓴다.

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

import pandas as pd

from verify_lab.common_constants import RATE_TO_PERCENT
from verify_lab.report.tables import print_dataframe
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.strategy.constants import (
    DISPLAY_STOP_LEVEL,
    EXPIRY_CELLS,
    EXPIRY_STOP_LEVEL,
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

# 산출물 파일 이름. 격자와 확정 성적표는 내용이 다르므로 파일명을 나눈다 —
# 같은 이름이면 폴더만 보고 어느 쪽인지 알 수 없다
SUMMARY_FILENAME = "summary_by_cell.csv"
GRID_FILENAME = "stop_loss_grid.csv"
TRADES_FILENAME = "trades.csv"

# 산출물 표의 컬럼 이름. **폭은 적지 않는다** — `print_dataframe` 이 내용에서 계산한다
DISPLAY_FILE = "파일"
DISPLAY_ROW_COUNT = "행 수"


def _build_parser() -> argparse.ArgumentParser:
    """명령행 인자 파서를 만든다.

    **손절선 값은 인자가 아니다.** 확정값을 그대로 적용하는 것이 설계이며, 값을 골라 넣는
    노브로 쓰면 표본에 맞춘 튜닝이 된다. `--grid` 는 값을 고르는 것이 아니라 **전부 내는** 쪽이다.

    Returns:
        인자 파서
    """
    parser = argparse.ArgumentParser(description="옵션 만기일 매매를 실행합니다.")
    parser.add_argument(
        "--ticker",
        nargs="+",
        choices=sorted({cell.dataset_key for cell in EXPIRY_CELLS}),
        default=None,
        help="실행할 종목 (기본값: 전부)",
    )
    parser.add_argument(
        "--grid",
        action="store_true",
        help="손절선 격자를 낸다 (무손절 + -1.0%%~-10.0%%). 손절선을 다시 고를 때만 쓴다",
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


def _print_scope(cells: list[ExpiryCell], *, grid: bool) -> None:
    """무엇을 도는지 먼저 보여 준다.

    **미국 9월 세 칸이 같은 날 같은 방향**이라는 사실을 함께 적는다 — 산출물을 세 번의
    확인으로 읽으면 안 되기 때문이다.

    Args:
        cells: 실행할 칸 목록
        grid: 손절선 격자를 내는지 여부
    """
    if grid:
        logger.debug(
            f"대상 {len(cells)}칸 × 손절선 {len(EXPIRY_STOP_LEVELS)}종 + {NO_STOP_LABEL} "
            f"= {len(cells) * (len(EXPIRY_STOP_LEVELS) + 1)}행"
        )
    else:
        logger.debug(f"대상 {len(cells)}칸 · 손절선 {-EXPIRY_STOP_LEVEL * RATE_TO_PERCENT:.1f}% (확정값)")
    logger.debug("미국 9월 세 칸(QQQ·SPY·DIA)은 같은 날 같은 방향이라 독립된 세 번의 기회가 아닙니다")


def _print_summary(outputs: ExpiryOutputs, *, grid: bool) -> None:
    """성적표를 화면에 보여 준다.

    격자일 때는 **무손절 행만** 낸다 — 160행을 터미널에 쏟으면 읽을 수 없고, 그 행이
    `docs/research/옵션_만기일.md` 12A.4 의 방향 기대값과 맞아야 두 계층이 같은 것을
    재고 있다는 뜻이기 때문이다.

    Args:
        outputs: 실행 산출물
        grid: 손절선 격자를 낸 실행인지 여부
    """
    if grid:
        no_stop = outputs.grid[outputs.grid[DISPLAY_STOP_LEVEL] == NO_STOP_LABEL]
        print_dataframe(no_stop, logger, title=f"{NO_STOP_LABEL} — 맨몸 성적 (결과 문서 12A.4 와 대조)")
        return

    print_dataframe(outputs.grid, logger, title=f"칸별 성적 (손절 {-EXPIRY_STOP_LEVEL * RATE_TO_PERCENT:.1f}%)")


@cli_exception_handler
def main() -> int:
    """매매를 실행하고 산출물을 저장한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = _build_parser().parse_args()
    cells = _selected_cells(args.ticker)

    # 격자일 때만 무손절을 앞에 붙인다. 손절이 무엇을 막았는지는 그 행과 견줘야 보인다
    stop_levels: list[float | None] = [None, *EXPIRY_STOP_LEVELS] if args.grid else [EXPIRY_STOP_LEVEL]
    summary_filename = GRID_FILENAME if args.grid else SUMMARY_FILENAME

    _print_scope(cells, grid=args.grid)
    outputs = run_expiry_trading(cells, stop_levels)
    _print_summary(outputs, grid=args.grid)

    directory = create_run_directory(EXPIRY_STRATEGY_NAME)
    save_table(directory, summary_filename, outputs.grid)
    save_table(directory, TRADES_FILENAME, outputs.trades)
    save_run_summary(
        directory,
        {
            "cells": [f"{cell.dataset_key} {cell.expiry_month}월" for cell in cells],
            "stop_levels": [NO_STOP_LABEL if level is None else level for level in stop_levels],
            "row_counts": {"summary": len(outputs.grid), "trades": len(outputs.trades)},
        },
    )

    print_dataframe(
        pd.DataFrame(
            [
                {DISPLAY_FILE: summary_filename, DISPLAY_ROW_COUNT: len(outputs.grid)},
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
            "stop_level_count": len(stop_levels),
            "output": str(directory),
        },
    )
    logger.debug(f"성적 {len(outputs.grid):,}행, 체결 {len(outputs.trades):,}건을 산출했습니다")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
