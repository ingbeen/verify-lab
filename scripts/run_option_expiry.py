#!/usr/bin/env python3
"""옵션 만기일 실행 CLI — 측정과 체결을 한 번에 돈다

**확정 칸**의 해석 재료를 한 장으로 내고, 같은 칸에 손절선을 걸어 체결 원자료와 성적표를 낸다.
게이트(회당 기대값의 하한)를 넘지 못한 칸도 성적표에 값 그대로 남는다 — 화면에서만 빠진다.
**기준값의 소유자는 `measure/screening.py` 하나다** — 여기서 값을 다시 적지 않는다.

**등급(검증·매매)은 분류일 뿐이라 실행을 가르지 않는다.** 한 번 돌리면 측정 표와
체결 산출물이 **한 폴더에** 함께 나오며, 어느 등급 폴더에 쌓일지는
`verify_lab/tracks.py` 의 레지스트리가 정한다.

**손절선은 격자가 기본이다** — 무손절 + -1.0%~-10.0% 를 전부 낸다. 값을 인자로 열지 않는다 —
값을 옮겨 가며 성적을 보면 표본에 맞춘 튜닝이지만, **전부 내는 것은 고르는 것이 아니다.**
확정 손절선이 무엇인지는 규칙 문서가 정하고 `손절선(%)` 한 컬럼으로 골라낸다.

**거는 칸은 코드가 아니라 `docs/매매/옵션_만기일/규칙.md` §3 이 정한다** — 코드는 그 결론을
옮겨 적을 뿐이고, 왜 그 칸인지는 그 문서의 「확정 / 탈락안 / 근거」가 갖는다.

가격 기준은 **원본가 하나**다. 사용자가 증권앱·차트에서 보는 가격이 곧 신호를 판정하고
주문을 거는 가격이기 때문이다 (루트 `CLAUDE.md` 측정의 원칙 14).

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
from pathlib import Path

import pandas as pd

from verify_lab.common_constants import RATE_TO_PERCENT
from verify_lab.execution.constants import (
    DISPLAY_DIRECTION,
    DISPLAY_STOP_LEVEL,
    DISPLAY_TOTAL,
    DISPLAY_WIN_RATE,
    NO_STOP_LABEL,
    PERIOD_ALL,
    PERIODS,
    SUMMARY_FILENAME,
    TRADES_FILENAME,
)
from verify_lab.execution.run_summary import KEY_ROW_COUNTS, KEY_RULE, merge_run_summary
from verify_lab.measure.screening import COL_DIRECTION, DIRECTION_DOWN, DIRECTION_UP, SCREEN_CANDIDATE
from verify_lab.measure.statistics import (
    COL_MEAN,
    COL_MEDIAN,
    COL_SAMPLE_COUNT,
    DEFAULT_RANDOM_SEED,
    DEFAULT_REPEAT_COUNT,
)
from verify_lab.report.constants import (
    DISPLAY_MEAN,
    DISPLAY_PERIOD,
    DISPLAY_SCREEN,
    DISPLAY_SIGNAL_COUNT,
    PERCENT_DECIMALS,
)
from verify_lab.report.tables import print_dataframe, to_display_columns
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.studies.option_expiry.constants import (
    COL_DIVIDEND_HIT_COUNT,
    COL_EXPIRY_MONTH_NUMBER,
    COL_TICKER,
    DATASETS,
    DISPLAY_EXPIRY_MONTH,
    DISPLAY_TICKER,
    EXPIRY_STOP_LEVEL,
    EXPIRY_STOP_LEVELS,
    OUTPUT_FILES,
    OUTPUT_LABELS,
    PERCENT_OUTPUT_COLUMNS,
    PROBABILITY_OUTPUT_COLUMNS,
    TRACK_NAME,
    Dataset,
    ExpiryCell,
    trading_cells,
)
from verify_lab.studies.option_expiry.runner import (
    KEY_DATASETS,
    KEY_PERMUTATION_REPEATS,
    KEY_PERMUTATION_SEED,
    StudyOutputs,
    run_study,
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

# 화면에 낼 후보 칸의 컬럼. **성적표 전 컬럼을 쏟으면 가로로 넘쳐 읽을 수 없고**,
# 바로 뒤의 맨몸 성적 표가 같은 행을 다시 내므로 여기서는 판정에 필요한 것만 낸다
CANDIDATE_COLUMNS = [
    DISPLAY_TICKER,
    DISPLAY_EXPIRY_MONTH,
    DISPLAY_DIRECTION,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_WIN_RATE,
    DISPLAY_MEAN,
    DISPLAY_TOTAL,
]


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


def _selected_cells(datasets: tuple[Dataset, ...]) -> list[ExpiryCell]:
    """고른 대상의 **확정 칸**을 만든다.

    **측정과 체결의 범위가 한 인자로 정해진다.** 따로 받으면 한 실행 안에서 둘이 갈릴 수 있고,
    그러면 같은 폴더의 두 표가 다른 범위를 재게 된다.

    **목록 생성은 도메인 로직이라 CLI 가 아니라 `studies.option_expiry.constants.trading_cells`
    가 소유한다.** 그 칸을 왜 고른 것인지는 `docs/매매/옵션_만기일/규칙.md` §3 이 갖는다.

    Args:
        datasets: 이번 실행의 측정 대상

    Returns:
        그 대상들의 확정 칸
    """
    return list(trading_cells(datasets))


def _print_scope(cells: list[ExpiryCell]) -> None:
    """무엇을 도는지 먼저 보여 준다.

    **같은 달 두 칸이 같은 날 같은 방향**이라는 사실을 함께 적는다 — 산출물을 두 번의
    확인으로 읽으면 안 되기 때문이다.

    Args:
        cells: 실행할 칸 목록
    """
    stop_count = len(EXPIRY_STOP_LEVELS) + 1
    logger.debug(
        f"대상 {len(cells)}칸 × 손절선 {stop_count}종({NO_STOP_LABEL} 포함) × 시기 {len(PERIODS)}행 "
        f"= 성적표 {len(cells) * stop_count * len(PERIODS):,}행 "
        f"(확정 손절선은 {-EXPIRY_STOP_LEVEL * RATE_TO_PERCENT:.1f}%)"
    )
    logger.debug("확정 칸만 냅니다 — 그 칸을 왜 고른 것인지는 docs/매매/옵션_만기일/규칙.md §3 이 갖습니다")
    logger.debug("9월 두 칸(SPY·DIA)은 같은 날 같은 방향이고 상관 0.965 라 독립된 두 번의 기회가 아닙니다")


def _print_candidates(outputs: ExpiryOutputs) -> None:
    """성적표에서 **맨몸 후보 칸만** 뽑아 화면에 보여 준다.

    **판정표를 따로 내지 않으므로 성적표가 그 자리다** (2026-09-16 통합). 화면은 "지금 볼 것"을
    위한 자리이고, 제외된 칸을 포함한 전 칸은 성적표가 만기월 순서로 답한다.

    **무손절 행을 보여 준다** — 게이트가 맨몸 성적으로 걸리기 때문이다(측정의 원칙 10).
    같은 칸이 확정 손절선에서 어떻게 되는지는 CSV 에서 `손절선(%)` 을 바꿔 보면 된다.

    Args:
        outputs: 체결 산출물
    """
    table = outputs.performance
    picked = table[
        (table[DISPLAY_STOP_LEVEL] == NO_STOP_LABEL)
        & (table[DISPLAY_PERIOD] == PERIOD_ALL)
        & (table[DISPLAY_SCREEN] == SCREEN_CANDIDATE)
    ]
    if picked.empty:
        logger.debug("1차 게이트를 넘은 칸이 없습니다")
        return

    # 동률이 흔하므로(적중률이 표본의 분수라 값이 겹친다) **안정 정렬**을 써서
    # 같은 적중률 안에서는 종목·만기월 순서가 유지되게 한다
    ordered = picked.sort_values(DISPLAY_WIN_RATE, ascending=False, kind="stable")
    print_dataframe(
        ordered[CANDIDATE_COLUMNS],
        logger,
        title=f"1차 후보 — {NO_STOP_LABEL} · 게이트를 넘은 칸 (적중률 순)",
    )
    logger.debug(f"제외된 칸을 포함한 전 칸의 판정은 {SUMMARY_FILENAME} 의 「1차 판정」 컬럼에 있습니다")


def _display_headline(outputs: StudyOutputs) -> None:
    """측정 표에서 **해석에 먼저 필요한 몇 열만** 화면에 보여 준다.

    전 열을 터미널에 쏟으면 읽을 수 없다. **전체는 측정 산출물에 있다.**

    [중요] **여기 값은 1배 롱 기준이다** — 「아래」 칸의 평균은 음수로 나오고, 성적표의
    같은 칸과 부호가 다르다. 둘은 대조 대상이 아니다.

    Args:
        outputs: 측정 산출물
    """
    if outputs.measure.empty:
        logger.debug("표시할 측정 행이 없습니다")
        return

    columns = [COL_TICKER, COL_EXPIRY_MONTH_NUMBER, COL_DIRECTION, COL_SAMPLE_COUNT, COL_MEAN, COL_MEDIAN]
    table = outputs.measure[[*columns, COL_DIVIDEND_HIT_COUNT]].copy()
    for column in (COL_MEAN, COL_MEDIAN):
        table[column] = (table[column] * RATE_TO_PERCENT).round(PERCENT_DECIMALS)

    print_dataframe(
        table.rename(columns=OUTPUT_LABELS),
        logger,
        title=f"측정 — 1배 롱 기준 (전체는 {OUTPUT_FILES['measure']} 에)",
    )


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
    cells = _selected_cells(datasets)

    _print_scope(cells)
    # **측정과 체결이 같은 칸 목록을 받는다.** 따로 정하면 한 폴더의 두 표가 다른 범위를 잰다
    study = run_study(datasets, cells=tuple(cells), repeats=args.repeats, seed=args.seed)

    # **손절선 목록을 CLI 가 다시 만들지 않는다.** 여기서 조립하면 runner 의 기본값을 좁혔을 때
    # 두 곳이 갈리고 `meta.json` 이 돌지 않은 격자를 적는다 — 예외는 나지 않는다
    trading = run_option_expiry_trading(cells)

    directory = create_run_directory(TRACK_NAME)
    counts = _save(study, trading, directory)

    _print_candidates(trading)
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
            # **방향까지 붙여야 칸이 유일해진다** — 만기월만 적으면 같은 문자열이 두 번 실려
            # 무엇을 돌렸는지 알 수 없다
            "cells": [
                f"{cell.dataset_key} {cell.expiry_month}월 " f"{DIRECTION_DOWN if cell.bet_down else DIRECTION_UP}"
                for cell in cells
            ],
            "stop_levels": trading.summary[KEY_RULE][KEY_STOP_LEVELS],
            KEY_PERMUTATION_REPEATS: study.summary[KEY_PERMUTATION_REPEATS],
            KEY_PERMUTATION_SEED: study.summary[KEY_PERMUTATION_SEED],
            KEY_ROW_COUNTS: counts,
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
