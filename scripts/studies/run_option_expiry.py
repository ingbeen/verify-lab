#!/usr/bin/env python3
"""검증 #7 실행 — 옵션 만기일 기준 상대 거래일의 수익률

만기일을 0 으로 두고 앞뒤 상대 거래일을 **전부** 산출한다. 문헌이 말하는 "만기 1주 전"은
정의에 따라 부호가 뒤집히므로 하나를 골라 내지 않는다
(`docs/spec/option_expiry.md` 결정 ②).

가격 기준 두 벌(수정주가·원본가)을 함께 돌린다. 배당락이 만기일에 고정돼 있어 원본가에는
한 방향 편향이 들어가는데, 두 기준의 차이가 곧 그 몫이라 **차이 자체가 검산**이 된다.

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

from verify_lab.measure.statistics import COL_MEAN, COL_MEDIAN, COL_SAMPLE_COUNT, COL_WIN_RATE
from verify_lab.report.constants import PERCENT_DECIMALS, RATE_TO_PERCENT
from verify_lab.report.tables import print_dataframe
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.studies.option_expiry.constants import (
    COL_OFFSET,
    COL_TICKER,
    DATASETS,
    DISPLAY_OFFSET,
    DISPLAY_TICKER,
    STUDY_NAME,
)
from verify_lab.studies.option_expiry.runner import StudyOutputs, basis_gap, headline_table, run_study
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_OPTION_EXPIRY = "option_expiry_study"

# 산출물 파일명. 표 하나에 파일 하나이며 전부 long-form 이다
FILE_EXPIRIES = "expiries.csv"
FILE_SIGNALS = "signals.csv"
FILE_DAILY = "daily_by_offset.csv"
FILE_MONTH_POSITION = "daily_by_month_position.csv"
FILE_FORWARD = "forward_summary.csv"
FILE_EXCESS = "forward_excess.csv"
FILE_TEST = "permutation.csv"
FILE_BASIS_GAP = "basis_gap.csv"


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="옵션 만기일 기준 상대 거래일의 수익률을 측정합니다.")
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
    """본검증 기준의 offset 별 일간 등락을 화면에 표시한다.

    Args:
        outputs: 실행 산출물
    """
    headline = headline_table(outputs)
    if headline.empty:
        logger.debug("표시할 요약 행이 없습니다")
        return

    table = headline[[COL_TICKER, COL_OFFSET, COL_SAMPLE_COUNT, COL_MEAN, COL_MEDIAN, COL_WIN_RATE]].copy()
    for column in (COL_MEAN, COL_MEDIAN, COL_WIN_RATE):
        table[column] = (table[column] * RATE_TO_PERCENT).round(PERCENT_DECIMALS)

    table = table.rename(
        columns={
            COL_TICKER: DISPLAY_TICKER,
            COL_OFFSET: DISPLAY_OFFSET,
            COL_SAMPLE_COUNT: "표본",
            COL_MEAN: "평균(%)",
            COL_MEDIAN: "중앙값(%)",
            COL_WIN_RATE: "승률(%)",
        }
    )
    print_dataframe(table, logger, title="본검증 기준 · 전체 국면 · 전체 월 — 상대 거래일별 일간 등락")


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
    save_table(directory, FILE_EXPIRIES, outputs.expiries)
    save_table(directory, FILE_SIGNALS, outputs.signals)
    save_table(directory, FILE_DAILY, outputs.daily)
    save_table(directory, FILE_MONTH_POSITION, outputs.month_position)
    save_table(directory, FILE_FORWARD, outputs.forward)
    save_table(directory, FILE_EXCESS, outputs.excess)
    save_table(directory, FILE_TEST, outputs.test)
    save_table(directory, FILE_BASIS_GAP, basis_gap(outputs))

    _display_headline(outputs)

    summary = {**outputs.summary, "output_dir": str(directory)}
    save_run_summary(directory, summary)
    save_metadata(
        KEY_META_OPTION_EXPIRY,
        {
            "output_dir": str(directory),
            "datasets": [dataset.key for dataset in datasets],  # pyright: ignore[reportAttributeAccessIssue]
            "max_offset": summary["max_offset"],
            "horizons": summary["horizons"],
            "permutation_repeats": summary["permutation_repeats"],
            "permutation_seed": summary["permutation_seed"],
            "row_counts": summary["row_counts"],
        },
    )

    logger.debug(f"산출물 저장 위치: {directory}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
