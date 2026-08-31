#!/usr/bin/env python3
"""역방향 매매 규칙 실행 CLI

확정 규칙(단일 손절선 · 종가 집행 · 수익 시 즉시 청산)을 대상 3종에 적용해
체결 내역과 집계를 낸다. 규칙 전문과 확정 근거는
`docs/strategy/역방향_매매_규칙.md` 가 SoT다.

**손절선과 보유 한도는 상수다.** 값을 옮겨 가며 성적을 보는 것은 과최적화이며,
어느 값이 어떤 결과를 내는지는 규칙 문서 §3.1 의 격자에 이미 실측으로 남아 있다.

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

import pandas as pd

from verify_lab.common_constants import RATE_TO_PERCENT
from verify_lab.report.tables import print_dataframe
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.strategy.constants import (
    DISPLAY_START_YEAR,
    HOLD_LIMIT,
    STOP_LOSS_LEVEL,
    STRATEGY_NAME,
    TARGETS,
    Target,
)
from verify_lab.strategy.runner import KEY_SUMMARY, KEY_TRADES, StrategyOutputs, run_strategy
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_REVERSE_TRADING = "reverse_trading_strategy"

# 산출물 파일 이름
TRADES_FILENAME = "trades.csv"
SUMMARY_FILENAME = "summary_by_target.csv"

# 산출물 표의 컬럼 이름. **폭은 적지 않는다** — `print_dataframe` 이 내용에서 계산한다
DISPLAY_FILE = "파일"
DISPLAY_ROW_COUNT = "행 수"


def _build_parser() -> argparse.ArgumentParser:
    """명령행 인자 파서를 만든다.

    **손절선과 대상 목록은 인자가 아니다.** 확정된 규칙을 그대로 적용하는 것이 이 스크립트의
    설계이며, 값을 골라 넣는 노브로 쓰면 표본에 맞춘 튜닝이 된다.

    Returns:
        인자 파서
    """
    parser = argparse.ArgumentParser(description="역방향 매매 규칙을 대상별로 실행합니다.")
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
    logger.debug("진입: 신호일 종가")
    logger.debug(f"손절: -{STOP_LOSS_LEVEL * RATE_TO_PERCENT:.0f}% — 진입가 기준, 보유 기간 내내 고정")
    logger.debug(f"청산: 종가가 진입가 위면 즉시 청산, 손실이면 D+{HOLD_LIMIT} 까지 보유")


def _print_summary(outputs: StrategyOutputs) -> None:
    """대상별 집계를 표로 보여준다.

    **저장하는 표를 그대로 화면에 낸다.** 열을 빼거나 따로 가공하면 반올림·부호 표기가 갈려
    화면에서 본 행을 CSV 에서 찾지 못한다. 시작연도도 대상마다 다른 값이라 함께 낸다.

    시작연도만 문자열로 바꾸는 것은 **연도가 개수가 아니라 식별자**이기 때문이다.
    표 출력이 정수에 붙이는 천 단위 구분자가 연도에 걸리면 `2,005` 가 되어 CSV 의 `2005` 와
    달라진다 — 화면과 CSV 를 맞추기 위한 변환이지 값을 가공하는 것이 아니다.

    Args:
        outputs: 실행 산출물
    """
    table = outputs.summary.astype({DISPLAY_START_YEAR: str})
    print_dataframe(table, logger, title="대상별 성적")


@cli_exception_handler
def main() -> int:
    """역방향 매매 규칙을 실행하고 산출물을 저장한다.

    Returns:
        종료 코드 (성공 0)
    """
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
    print_dataframe(
        pd.DataFrame(
            [
                {DISPLAY_FILE: TRADES_FILENAME, DISPLAY_ROW_COUNT: counts[KEY_TRADES]},
                {DISPLAY_FILE: SUMMARY_FILENAME, DISPLAY_ROW_COUNT: counts[KEY_SUMMARY]},
            ]
        ),
        logger,
        title=f"산출물 (저장 폴더: {directory})",
    )
    save_metadata(
        KEY_META_REVERSE_TRADING,
        {
            "targets": [f"{target.dataset.ticker} K={target.rank_cut}" for target in targets],
            "stop_loss_level": round(STOP_LOSS_LEVEL * RATE_TO_PERCENT, 2),
            "hold_limit": HOLD_LIMIT,
            "output": str(directory),
        },
    )
    logger.debug(f"체결 {counts[KEY_TRADES]:,}건, 집계 {counts[KEY_SUMMARY]:,}행을 산출했습니다")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
