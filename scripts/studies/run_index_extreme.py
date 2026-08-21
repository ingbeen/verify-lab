#!/usr/bin/env python3
"""검증 #1 — 지수 극단 이벤트 실행 CLI

강건성 조합(순위 컷·연속 일수·집계 시작연도·방향·시대 구간)을 **한 실행에서 전부** 돌고,
산출물 CSV 4개와 `summary.json` 을 실행 시각 폴더에 남긴다.

**국내 두 가격 기준을 같은 실행 안에서 계산한다.** 대조의 전제가 "파라미터가 같았다"이기
때문이며, 따로 돌리면 그 사실을 사람이 확인해야 한다.

인자 없이 실행하면 `docs/spec/index_extreme_events.md` 가 확정한 설정으로 돈다.
실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
from pathlib import Path

import pandas as pd

from verify_lab.measure.forward_return import DEFAULT_HORIZONS
from verify_lab.measure.statistics import DEFAULT_RANDOM_SEED, DEFAULT_REPEAT_COUNT
from verify_lab.report.constants import (
    DISPLAY_HORIZON,
    DISPLAY_MEAN,
    DISPLAY_MEDIAN,
    DISPLAY_REVERSE_RATE,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_WIN_RATE,
    EXCESS_FILENAME,
    HORIZON_LABELS,
    SIGNALS_FILENAME,
    STATISTICS_FILENAME,
    TEST_FILENAME,
)
from verify_lab.report.tables import print_dataframe
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.studies.index_extreme.constants import (
    DATASETS,
    DEFAULT_START_YEAR,
    DISPLAY_DIRECTION,
    DISPLAY_EVENT_COUNT,
    DISPLAY_PARAMETER,
    DISPLAY_PERIOD,
    DISPLAY_START_YEAR,
    DISPLAY_TEST,
    DISPLAY_TICKER,
    PERIOD_ALL,
    STUDY_NAME,
    Dataset,
)
from verify_lab.studies.index_extreme.runner import (
    KEY_DATASETS,
    KEY_EMPTY_SIGNAL_GROUPS,
    KEY_END_DATE,
    KEY_EXCESS,
    KEY_PATH,
    KEY_PRICE_BASIS,
    KEY_ROW_COUNT,
    KEY_ROW_COUNTS,
    KEY_SIGNAL_GROUP_COUNT,
    KEY_SIGNALS,
    KEY_START_DATE,
    KEY_STATISTICS,
    KEY_TEST_TABLE,
    KEY_TICKER,
    StudyOutputs,
    run_study,
)
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_INDEX_EXTREME = "index_extreme_study"

# 데이터셋 개요 표의 컬럼 정의 (컬럼명, 폭, 정렬)
DATASET_COLUMNS = [
    ("종목", 12, Align.LEFT),
    ("가격기준", 12, Align.LEFT),
    ("행 수", 10, Align.RIGHT),
    ("기간", 26, Align.LEFT),
    ("파일", 30, Align.LEFT),
]

# 산출물 표의 컬럼 정의
OUTPUT_COLUMNS = [
    ("파일", 20, Align.LEFT),
    ("행 수", 12, Align.RIGHT),
]

# 저장할 파일과 요약의 행 수 키. 출력 계약이 확정한 CSV 4개다
OUTPUT_FILES = (
    (SIGNALS_FILENAME, KEY_SIGNALS),
    (STATISTICS_FILENAME, KEY_STATISTICS),
    (EXCESS_FILENAME, KEY_EXCESS),
    (TEST_FILENAME, KEY_TEST_TABLE),
)

# 컬럼 사이 여백. 오른쪽 정렬 컬럼은 값이 칸 끝에 붙어 다음 컬럼과 맞닿는다
COLUMN_GAP = "  "

# 터미널에 실을 발췌의 축. 전 조합은 CSV 에 있고, 화면은 기본 설정만 훑는 자리다.
# 집계는 한 기준으로만 나오므로(runner.AGGREGATED_BASIS) 기준으로 거를 것이 없다
EXCERPT_HORIZON = HORIZON_LABELS[DEFAULT_HORIZONS[-1]]

# 발췌에 실을 컬럼. 값은 저장한 표시용 프레임에서 그대로 가져온다 —
# 따로 가공하면 화면에서 본 숫자를 CSV 에서 찾지 못한다
EXCERPT_COLUMNS = [
    DISPLAY_TICKER,
    DISPLAY_TEST,
    DISPLAY_PARAMETER,
    DISPLAY_DIRECTION,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_EVENT_COUNT,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_MEAN,
    DISPLAY_MEDIAN,
    DISPLAY_WIN_RATE,
    DISPLAY_REVERSE_RATE,
]


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="지수 극단 이벤트 검증을 강건성 조합 전체로 실행하고 결과를 저장합니다.")
    parser.add_argument(
        "--dataset",
        nargs="+",
        choices=[dataset.key for dataset in DATASETS],
        default=[dataset.key for dataset in DATASETS],
        help="검증할 시세 (기본값: 전부). 국내 두 기준의 대조는 함께 돌려야 성립합니다",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=DEFAULT_REPEAT_COUNT,
        help=f"순열 검정 반복 수 (기본값: {DEFAULT_REPEAT_COUNT})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help=f"순열 검정 난수 시드 (기본값: {DEFAULT_RANDOM_SEED})",
    )

    return parser.parse_args()


def _selected_datasets(keys: list[str]) -> list[Dataset]:
    """인자로 받은 키에 해당하는 데이터셋을 정의 순서대로 고른다.

    Args:
        keys: 데이터셋 키 목록

    Returns:
        데이터셋 목록
    """
    return [dataset for dataset in DATASETS if dataset.key in keys]


def _print_datasets(outputs: StudyOutputs) -> None:
    """어떤 시세로 쟀는지 표로 보여준다.

    Args:
        outputs: 실행 산출물
    """
    rows = [
        [
            record[KEY_TICKER],
            record[KEY_PRICE_BASIS],
            f"{record[KEY_ROW_COUNT]:,}",
            f"{COLUMN_GAP}{record[KEY_START_DATE]} ~ {record[KEY_END_DATE]}",
            Path(record[KEY_PATH]).name,
        ]
        for record in outputs.summary[KEY_DATASETS]
    ]
    TableLogger(DATASET_COLUMNS, logger).print_table(rows, title="검증 대상 시세")


def _print_excerpt(outputs: StudyOutputs) -> None:
    """기본 설정의 집계를 발췌해 보여준다.

    전 조합은 CSV 에 있다. 화면에는 기본 시작연도·구간 전체·가장 긴 측정 구간의 종가 기준만
    싣되, **저장한 표시용 프레임에서 그대로 골라** 화면과 CSV 의 숫자가 갈리지 않게 한다.

    Args:
        outputs: 실행 산출물
    """
    statistics = outputs.statistics
    selected = statistics[
        (statistics[DISPLAY_START_YEAR] == DEFAULT_START_YEAR)
        & (statistics[DISPLAY_PERIOD] == PERIOD_ALL.label)
        & (statistics[DISPLAY_HORIZON] == EXCERPT_HORIZON)
    ]

    if selected.empty:
        logger.warning(f"기본 설정({DEFAULT_START_YEAR}년 시작)에 해당하는 신호군이 없어 발췌를 건너뜁니다")
        return

    print_dataframe(
        selected[EXCERPT_COLUMNS].reset_index(drop=True),
        logger,
        title=f"{DEFAULT_START_YEAR}년 이후 · {EXCERPT_HORIZON} 수익률 (전 조합은 CSV 참고)",
    )


def _save_outputs(outputs: StudyOutputs, directory: Path) -> None:
    """산출물 네 표와 요약을 저장한다.

    Args:
        outputs: 실행 산출물
        directory: 결과 폴더
    """
    for filename, key in OUTPUT_FILES:
        save_table(directory, filename, _table_of(outputs, key))

    save_run_summary(directory, outputs.summary)


def _table_of(outputs: StudyOutputs, key: str) -> pd.DataFrame:
    """요약의 행 수 키에 대응하는 표를 꺼낸다.

    Args:
        outputs: 실행 산출물
        key: 행 수 키

    Returns:
        표시용 표
    """
    tables = {
        KEY_SIGNALS: outputs.signals,
        KEY_STATISTICS: outputs.statistics,
        KEY_EXCESS: outputs.excess,
        KEY_TEST_TABLE: outputs.test,
    }

    return tables[key]


def _print_outputs(outputs: StudyOutputs, directory: Path) -> None:
    """무엇이 어디에 몇 행으로 남았는지 보여준다.

    Args:
        outputs: 실행 산출물
        directory: 결과 폴더
    """
    row_counts = outputs.summary[KEY_ROW_COUNTS]
    rows = [[filename, f"{row_counts[key]:,}"] for filename, key in OUTPUT_FILES]
    TableLogger(OUTPUT_COLUMNS, logger).print_table(rows, title=f"산출물 (저장 폴더: {directory})")


@cli_exception_handler
def main() -> int:
    """강건성 조합을 전부 돌고 결과를 저장한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()
    datasets = _selected_datasets(args.dataset)

    outputs = run_study(datasets, repeats=args.repeats, seed=args.seed)

    directory = create_run_directory(STUDY_NAME)
    _save_outputs(outputs, directory)

    _print_datasets(outputs)
    _print_excerpt(outputs)
    _print_outputs(outputs, directory)

    logger.debug(
        f"신호군 {outputs.summary[KEY_SIGNAL_GROUP_COUNT]:,}개를 집계했습니다 "
        f"(신호 0건이라 빠진 신호군 {len(outputs.summary[KEY_EMPTY_SIGNAL_GROUPS]):,}개, "
        f"순열 검정 반복 {args.repeats:,}회·시드 {args.seed})"
    )

    save_metadata(
        KEY_META_INDEX_EXTREME,
        {
            "result_dir": str(directory),
            "datasets": [
                record[KEY_TICKER] + " " + record[KEY_PRICE_BASIS] for record in outputs.summary[KEY_DATASETS]
            ],
            "signal_group_count": outputs.summary[KEY_SIGNAL_GROUP_COUNT],
            "empty_signal_group_count": len(outputs.summary[KEY_EMPTY_SIGNAL_GROUPS]),
            "row_counts": outputs.summary[KEY_ROW_COUNTS],
            "repeats": args.repeats,
            "seed": args.seed,
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
