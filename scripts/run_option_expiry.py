#!/usr/bin/env python3
"""옵션 만기일 실행 CLI — 측정과 체결을 한 번에 돈다

만기월(1~12)로 쪼개 방향 비율을 재고 각 칸을 **게이트 둘**(적중률 60% 이상 ·
방향 기대값 0 초과)로 판정한 뒤, 대상 칸에 손절선을 걸어 체결 원자료와 성적표를 낸다.
게이트를 넘지 못한 칸도 판정표에 값 그대로 남는다 — 화면에서만 빠진다.

**등급(검증·매매)은 분류일 뿐이라 실행을 가르지 않는다.** 한 번 돌리면 측정 표와
체결 산출물이 **한 폴더에** 함께 나오며, 어느 등급 폴더에 쌓일지는
`verify_lab/tracks.py` 의 레지스트리가 정한다.

**손절선은 격자가 기본이다** — 무손절 + -1.0%~-10.0% 를 전부 낸다. 값을 인자로 열지 않는다 —
값을 옮겨 가며 성적을 보면 표본에 맞춘 튜닝이지만, **전부 내는 것은 고르는 것이 아니다.**
확정 손절선이 무엇인지는 규칙 문서가 정하고 `손절선(%)` 한 컬럼으로 골라낸다.

가격 기준은 **원본가 하나**다. 사용자가 증권앱·차트에서 보는 가격이 곧 신호를 판정하고
주문을 거는 가격이기 때문이다 (루트 `CLAUDE.md` 측정의 원칙 14).

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
from pathlib import Path

import pandas as pd

from verify_lab.common_constants import RATE_TO_PERCENT
from verify_lab.execution.constants import DISPLAY_STOP_LEVEL, NO_STOP_LABEL, SUMMARY_FILENAME, TRADES_FILENAME
from verify_lab.execution.run_summary import KEY_ROW_COUNTS, KEY_RULE, merge_run_summary
from verify_lab.measure.constants import COL_EXCLUDED_COUNT, COL_SIGNAL_COUNT
from verify_lab.measure.statistics import (
    COL_MEAN,
    COL_MEDIAN,
    COL_WIN_RATE,
    DEFAULT_RANDOM_SEED,
    DEFAULT_REPEAT_COUNT,
)
from verify_lab.report.constants import (
    CANDIDATES_FILENAME,
    DISPLAY_EXCLUDED,
    DISPLAY_MEAN,
    DISPLAY_MEDIAN,
    DISPLAY_UP_RATE,
    PERCENT_DECIMALS,
)
from verify_lab.report.tables import build_candidates_table, print_dataframe, to_display_columns
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.studies.option_expiry.constants import (
    COL_EXIT_WEEKDAY,
    COL_EXPIRY_MONTH_NUMBER,
    COL_TICKER,
    DATASETS,
    DISPLAY_ENTRY_COUNT,
    DISPLAY_EXIT_WEEKDAY,
    DISPLAY_EXPIRY_MONTH,
    DISPLAY_TICKER,
    EXPIRY_CELLS,
    EXPIRY_STOP_LEVEL,
    EXPIRY_STOP_LEVELS,
    OUTPUT_FILES,
    OUTPUT_LABELS,
    PERCENT_OUTPUT_COLUMNS,
    PROBABILITY_OUTPUT_COLUMNS,
    TRACK_NAME,
    Dataset,
    ExpiryCell,
)
from verify_lab.studies.option_expiry.runner import (
    KEY_DATASETS,
    KEY_MAX_OFFSET,
    KEY_PERMUTATION_REPEATS,
    KEY_PERMUTATION_SEED,
    StudyOutputs,
    candidates_headline,
    run_study,
    trade_headline,
)
from verify_lab.studies.option_expiry.trading import KEY_STOP_LEVELS, ExpiryOutputs, run_option_expiry_trading
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키. **매매법당 하나다** — 실행이 하나이므로
# 측정·체결로 키를 가르면 같은 실행이 두 줄로 남는다
KEY_META_OPTION_EXPIRY = "option_expiry"

# 산출물 표의 컬럼 이름. **폭은 적지 않는다** — `print_dataframe` 이 내용에서 계산한다
DISPLAY_FILE = "파일"
DISPLAY_ROW_COUNT = "행 수"


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    **손절선 값은 인자가 아니다.** 격자 전체를 내는 것이 설계이며, 값을 골라 넣는
    노브로 쓰면 표본에 맞춘 튜닝이 된다 — **전부 내는 것은 고르는 것이 아니다.**

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="옵션 만기일 매매를 만기월별로 측정·판정하고 체결 성적을 함께 냅니다.")
    # **`nargs="+"` 로 둔다.** 같은 뜻의 인자가 스크립트마다 다른 방식이면
    # `--dataset qqq spy` 가 한쪽에서는 동작하고 다른 쪽에서는 죽는다
    parser.add_argument(
        "--dataset",
        nargs="+",
        choices=[dataset.key for dataset in DATASETS],
        default=None,
        help="대상 종목 (여러 개 가능, 기본값: 전부). 측정과 체결이 같은 범위를 씁니다",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=DEFAULT_REPEAT_COUNT,
        help=f"무작위 뽑기 대조 반복 수 (기본값: {DEFAULT_REPEAT_COUNT})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help=f"무작위 뽑기 대조 시드 (기본값: {DEFAULT_RANDOM_SEED}). 결과 재현에 필요하다",
    )
    return parser.parse_args()


def _selected_datasets(keys: list[str] | None) -> tuple[Dataset, ...]:
    """측정 대상 목록을 고른다.

    Args:
        keys: 선택된 종목 키 목록. `None` 이면 전부

    Returns:
        대상 정의 튜플
    """
    if not keys:
        return DATASETS

    return tuple(dataset for dataset in DATASETS if dataset.key in set(keys))


def _selected_cells(keys: list[str] | None) -> list[ExpiryCell]:
    """같은 키로 체결 대상 칸을 고른다.

    **측정과 체결의 범위가 한 인자로 정해진다.** 따로 받으면 한 실행 안에서 둘이 갈릴 수 있고,
    그러면 같은 폴더의 두 표가 다른 범위를 재게 된다.

    Args:
        keys: 종목 이름 목록. `None` 이면 전부

    Returns:
        선택된 칸 목록

    Raises:
        ValueError: 고른 종목에 해당하는 칸이 하나도 없는 경우
    """
    if not keys:
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
        f"= {len(cells) * (len(EXPIRY_STOP_LEVELS) + 1)}행 "
        f"(확정 손절선은 {-EXPIRY_STOP_LEVEL * RATE_TO_PERCENT:.1f}%)"
    )
    logger.debug("미국 9월 세 칸(QQQ·SPY·DIA)은 같은 날 같은 방향이라 독립된 세 번의 기회가 아닙니다")


def _display_headline(outputs: StudyOutputs) -> None:
    """**후보 판정과 맨몸 매매 성적**을 화면에 표시한다.

    후보 표를 먼저 낸다 — 화면에서 가장 먼저 봐야 할 것이 "어느 달·어느 방향"이기 때문이다.

    Args:
        outputs: 측정 산출물
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
        logger.debug(f"제외된 칸을 포함한 전 칸의 판정은 {CANDIDATES_FILENAME} 에 만기월 순서로 있습니다")

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
            COL_SIGNAL_COUNT: DISPLAY_ENTRY_COUNT,
            COL_EXCLUDED_COUNT: DISPLAY_EXCLUDED,
            COL_MEAN: DISPLAY_MEAN,
            COL_MEDIAN: DISPLAY_MEDIAN,
            COL_WIN_RATE: DISPLAY_UP_RATE,
        }
    )
    print_dataframe(table, logger, title="만기일 종가 매수 → 다음주 청산 — 전체 월")


def _print_performance(outputs: ExpiryOutputs) -> None:
    """성적표에서 **무손절 행만** 화면에 보여 준다.

    전 행을 터미널에 쏟으면 읽을 수 없고, 무손절 행이 맨몸 성적이라 측정 표와 대조하는
    자리이기 때문이다. **격자 전체는 CSV 에 있다.**

    Args:
        outputs: 체결 산출물
    """
    no_stop = outputs.performance[outputs.performance[DISPLAY_STOP_LEVEL] == NO_STOP_LABEL]
    print_dataframe(no_stop, logger, title=f"{NO_STOP_LABEL} — 맨몸 성적 (격자 전체는 CSV 에)")


def _save_study_table(directory: Path, filename: str, table: pd.DataFrame) -> None:
    """측정 산출물을 **한글 헤더와 맞춘 단위로** 저장한다.

    표마다 컬럼 구성이 다르므로 변환 대상은 그 표에 실제로 있는 것만 고른다.
    사전에 없는 컬럼이 있으면 `to_display_columns` 가 예외를 던진다 — 컬럼을 새로 만들고
    한글 이름을 빠뜨리면 그 자리에서 실패한다 (`scripts/CLAUDE.md` 산출물 저장).

    **빈 표는 저장하지 않되 건너뛴 사실을 남긴다.** 조용히 빠지면 산출물이 하나 없는 것을
    사용자가 모른다. 아래 계층은 빈 표를 예외로 거부하므로 그대로 넘기면 실행이 죽는다.

    Args:
        directory: 저장할 폴더
        filename: 파일 이름
        table: 영문 헤더의 산출물
    """
    if table.empty:
        logger.warning(f"표가 비어 있어 저장하지 않았습니다: {filename}")
        return

    columns = set(table.columns)
    display = to_display_columns(
        table,
        OUTPUT_LABELS,
        percent_columns=[column for column in PERCENT_OUTPUT_COLUMNS if column in columns],
        probability_columns=[column for column in PROBABILITY_OUTPUT_COLUMNS if column in columns],
    )
    save_table(directory, filename, display)


def _save(study: StudyOutputs, trading: ExpiryOutputs, directory: Path) -> dict[str, int]:
    """측정 표와 체결 산출물을 한 폴더에 저장한다.

    Args:
        study: 측정 산출물
        trading: 체결 산출물
        directory: 결과 폴더

    Returns:
        파일 이름 → 행 수
    """
    for field, filename in OUTPUT_FILES.items():
        _save_study_table(directory, filename, getattr(study, field))

    save_table(directory, SUMMARY_FILENAME, trading.performance)
    save_table(directory, TRADES_FILENAME, trading.trades)

    summary = merge_run_summary(study.summary, trading.summary)
    save_run_summary(directory, summary)

    counts: dict[str, int] = summary[KEY_ROW_COUNTS]

    return counts


@cli_exception_handler
def main() -> int:
    """측정과 체결을 한 번에 돌고 결과를 저장한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()
    datasets = _selected_datasets(args.dataset)
    cells = _selected_cells(args.dataset)

    _print_scope(cells)
    study = run_study(datasets, repeats=args.repeats, seed=args.seed)

    # **손절선 목록을 CLI 가 다시 만들지 않는다.** 여기서 조립하면 runner 의 기본값을 좁혔을 때
    # 두 곳이 갈리고 `meta.json` 이 돌지 않은 격자를 적는다 — 예외는 나지 않는다
    trading = run_option_expiry_trading(cells)

    directory = create_run_directory(TRACK_NAME)
    counts = _save(study, trading, directory)

    _display_headline(study)
    _print_performance(trading)
    print_dataframe(
        pd.DataFrame([{DISPLAY_FILE: name, DISPLAY_ROW_COUNT: rows} for name, rows in counts.items()]),
        logger,
        title=f"산출물 (저장 폴더: {directory})",
    )

    save_metadata(
        KEY_META_OPTION_EXPIRY,
        {
            "output_dir": str(directory),
            KEY_DATASETS: [dataset.key for dataset in datasets],
            "cells": [f"{cell.dataset_key} {cell.expiry_month}월" for cell in cells],
            "stop_levels": trading.summary[KEY_RULE][KEY_STOP_LEVELS],
            KEY_MAX_OFFSET: study.summary[KEY_MAX_OFFSET],
            KEY_PERMUTATION_REPEATS: study.summary[KEY_PERMUTATION_REPEATS],
            KEY_PERMUTATION_SEED: study.summary[KEY_PERMUTATION_SEED],
            KEY_ROW_COUNTS: counts,
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
