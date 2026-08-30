#!/usr/bin/env python3
"""검증 #7 실행 — 만기일 매수 → 다음주 청산 매매와 만기월별 후보 판정

만기월(1~12)로 쪼개 방향 비율을 재고, 각 칸을 **1차 게이트와 등급**으로 판정한다.
게이트를 넘지 못한 칸도 `candidates.csv` 에 사유와 함께 남는다 — 화면에서만 빠진다.

가격 기준은 **원본가 하나**다. 사용자가 증권앱·차트에서 보는 가격이 곧 신호를 판정하고
주문을 거는 가격이기 때문이다 (루트 `CLAUDE.md` 측정의 원칙 14).

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
from pathlib import Path

import pandas as pd

from verify_lab.common_constants import RATE_TO_PERCENT
from verify_lab.measure.constants import COL_EXCLUDED_COUNT, COL_SIGNAL_COUNT
from verify_lab.measure.statistics import COL_MEAN, COL_MEDIAN, COL_WIN_RATE
from verify_lab.report.constants import PERCENT_DECIMALS
from verify_lab.report.tables import build_candidates_table, print_dataframe, to_display_columns
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.studies.option_expiry.constants import (
    COL_EXIT_WEEKDAY,
    COL_EXPIRY_MONTH_NUMBER,
    COL_TICKER,
    DATASETS,
    DISPLAY_EXIT_WEEKDAY,
    DISPLAY_EXPIRY_MONTH,
    DISPLAY_TICKER,
    OUTPUT_LABELS,
    PERCENT_OUTPUT_COLUMNS,
    PROBABILITY_OUTPUT_COLUMNS,
    STUDY_NAME,
)
from verify_lab.studies.option_expiry.runner import (
    StudyOutputs,
    candidates_headline,
    run_study,
    trade_headline,
)
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_OPTION_EXPIRY = "option_expiry_study"

# 산출물 파일명. 표 하나에 파일 하나이며 전부 long-form 이다
FILE_EXPIRIES = "expiries.csv"
FILE_SIGNALS = "signals.csv"

# 만기일 매수 → 다음주 청산 매매의 산출물. 접두사로 묶어 상대 거래일 표와 섞이지 않게 한다
FILE_TRADE_SIGNALS = "weekly_trade_signals.csv"
FILE_TRADE_SUMMARY = "weekly_trade_summary.csv"
FILE_TRADE_EXCESS = "weekly_trade_excess.csv"
FILE_TRADE_TEST = "weekly_trade_permutation.csv"
FILE_TRADE_BY_MONTH = "weekly_trade_by_month.csv"
FILE_TRADE_BY_MONTH_HALVES = "weekly_trade_by_month_halves.csv"
FILE_CANDIDATES = "candidates.csv"


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="만기일 매수 → 다음주 청산 매매를 만기월별로 측정하고 판정합니다.")
    parser.add_argument(
        "--dataset",
        choices=[dataset.key for dataset in DATASETS],
        action="append",
        help="검증할 종목 (여러 번 지정 가능, 기본값: 전부)",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=None,
        help="순열 검정 반복 수 (기본값: 측정 계층의 확정값)",
    )
    return parser.parse_args()


def _selected_datasets(keys: list[str] | None) -> tuple[object, ...]:
    """실행할 대상 목록을 고른다.

    Args:
        keys: 선택된 종목 키 목록. `None` 이면 전부

    Returns:
        대상 정의 튜플
    """
    if not keys:
        return DATASETS

    return tuple(dataset for dataset in DATASETS if dataset.key in set(keys))


def _display_headline(outputs: StudyOutputs) -> None:
    """**후보 판정과 매매 성적**을 화면에 표시한다.

    후보 표를 먼저 낸다 — 화면에서 가장 먼저 봐야 할 것이 "어느 달·어느 방향"이기 때문이다.

    Args:
        outputs: 실행 산출물
    """
    candidates = candidates_headline(outputs)
    if candidates.empty:
        logger.debug("1차 게이트를 넘은 칸이 없습니다")
    else:
        table = build_candidates_table(candidates, axis_column=COL_EXPIRY_MONTH_NUMBER, axis_label=DISPLAY_EXPIRY_MONTH)
        # 청산 요일까지 붙여야 칸이 유일해진다 — 한국은 금요일·목요일 두 벌이라
        # 종목과 만기월만으로는 같은 달이 두 줄로 겹쳐 보인다
        table.insert(0, DISPLAY_EXIT_WEEKDAY, candidates[COL_EXIT_WEEKDAY].to_numpy())
        table.insert(0, DISPLAY_TICKER, candidates[COL_TICKER].to_numpy())
        print_dataframe(table, logger, title="1차 후보 — 적중률 60% 이상 · 방향 기대값 양수 (적중률 순)")
        # 화면에서 사라진 칸이 어디 있는지 알려주지 않으면 「코드가 대신 판단한다」는 문제가 화면에 남는다
        logger.debug(f"제외된 칸을 포함한 전 칸의 판정은 {FILE_CANDIDATES} 에 만기월 순서로 있습니다")

    trade = trade_headline(outputs)
    if trade.empty:
        logger.debug("표시할 매매 요약 행이 없습니다")
        return

    table = trade[
        [COL_TICKER, COL_EXIT_WEEKDAY, COL_SIGNAL_COUNT, COL_EXCLUDED_COUNT, COL_MEAN, COL_MEDIAN, COL_WIN_RATE]
    ].copy()
    for column in (COL_MEAN, COL_MEDIAN, COL_WIN_RATE):
        table[column] = (table[column] * RATE_TO_PERCENT).round(PERCENT_DECIMALS)

    table = table.rename(
        columns={
            COL_TICKER: DISPLAY_TICKER,
            COL_EXIT_WEEKDAY: DISPLAY_EXIT_WEEKDAY,
            COL_SIGNAL_COUNT: "진입",
            COL_EXCLUDED_COUNT: "제외",
            COL_MEAN: "평균(%)",
            COL_MEDIAN: "중앙값(%)",
            COL_WIN_RATE: "오른 비율(%)",
        }
    )
    print_dataframe(table, logger, title="만기일 종가 매수 → 다음주 청산 — 전체 월")


def _save(directory: Path, filename: str, table: pd.DataFrame) -> None:
    """산출물을 **한글 헤더와 맞춘 단위로** 저장한다.

    표마다 컬럼 구성이 다르므로 변환 대상은 그 표에 실제로 있는 것만 고른다.
    사전에 없는 컬럼이 있으면 `to_display_columns` 가 예외를 던진다 — 컬럼을 새로 만들고
    한글 이름을 빠뜨리면 그 자리에서 실패한다 (`scripts/CLAUDE.md` 산출물 저장).

    Args:
        directory: 저장할 폴더
        filename: 파일 이름
        table: 영문 헤더의 산출물
    """
    columns = set(table.columns)
    display = to_display_columns(
        table,
        OUTPUT_LABELS,
        percent_columns=[column for column in PERCENT_OUTPUT_COLUMNS if column in columns],
        probability_columns=[column for column in PROBABILITY_OUTPUT_COLUMNS if column in columns],
    )
    save_table(directory, filename, display)


@cli_exception_handler
def main() -> int:
    """검증을 실행하고 산출물을 저장한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()
    datasets = _selected_datasets(args.dataset)

    kwargs = {} if args.repeats is None else {"repeats": args.repeats}
    outputs = run_study(datasets, **kwargs)  # pyright: ignore[reportArgumentType]

    directory = create_run_directory(STUDY_NAME)
    _save(directory, FILE_EXPIRIES, outputs.expiries)
    _save(directory, FILE_SIGNALS, outputs.signals)
    _save(directory, FILE_TRADE_SIGNALS, outputs.trade_signals)
    _save(directory, FILE_TRADE_SUMMARY, outputs.trade_summary)
    _save(directory, FILE_TRADE_EXCESS, outputs.trade_excess)
    _save(directory, FILE_TRADE_TEST, outputs.trade_test)
    _save(directory, FILE_TRADE_BY_MONTH, outputs.trade_by_month)
    _save(directory, FILE_TRADE_BY_MONTH_HALVES, outputs.trade_by_month_halves)
    _save(directory, FILE_CANDIDATES, outputs.candidates)

    _display_headline(outputs)

    summary = {**outputs.summary, "output_dir": str(directory)}
    save_run_summary(directory, summary)
    save_metadata(
        KEY_META_OPTION_EXPIRY,
        {
            "output_dir": str(directory),
            "datasets": [dataset.key for dataset in datasets],  # pyright: ignore[reportAttributeAccessIssue]
            "max_offset": summary["max_offset"],
            "permutation_repeats": summary["permutation_repeats"],
            "permutation_seed": summary["permutation_seed"],
            "row_counts": summary["row_counts"],
        },
    )

    logger.debug(f"산출물 저장 위치: {directory}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
