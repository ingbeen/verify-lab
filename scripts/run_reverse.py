#!/usr/bin/env python3
"""역방향 실행 CLI — 측정과 체결을 한 번에 돈다 (신호는 역대급 등락)

**등급(검증·매매)은 분류일 뿐이라 실행을 가르지 않는다.** 한 번 돌리면 측정 표와
체결 원자료·성적표가 **한 폴더에** 함께 나오며, 어느 등급 폴더에 쌓일지는
`verify_lab/tracks.py` 의 레지스트리가 정한다.

**두 스크립트로 나누지 않는 이유**는 둘이 같은 시세를 두 번 읽고 같은 신호를 두 번 계산하는데,
산출물 폴더가 매매법당 하나라 **나중에 돈 쪽이 앞의 산출물을 지우기 때문**이다.

**손절선과 보유 한도는 상수다.** 값을 옮겨 가며 성적을 보는 것은 과최적화이며,
어느 값이 어떤 결과를 내는지는 규칙 문서의 격자에 이미 실측으로 남아 있다.

인자 없이 실행하면 확정 설계의 설정으로 돈다. 실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
from pathlib import Path

import pandas as pd

from verify_lab.execution.constants import (
    DISPLAY_START_YEAR,
    DISPLAY_STOP_LEVEL,
    NO_STOP_LABEL,
    SUMMARY_FILENAME,
    TRADES_FILENAME,
    stop_level_value,
)
from verify_lab.execution.run_summary import KEY_ROW_COUNTS, KEY_RULE, merge_run_summary
from verify_lab.measure.forward_return import DEFAULT_HORIZONS
from verify_lab.measure.statistics import DEFAULT_RANDOM_SEED, DEFAULT_REPEAT_COUNT
from verify_lab.report.constants import (
    DISPLAY_DOWN_RATE,
    DISPLAY_HORIZON,
    DISPLAY_MEAN,
    DISPLAY_MEDIAN,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_UP_RATE,
    HORIZON_LABELS,
)
from verify_lab.report.run_summary import (
    KEY_DATASET_FILE,
    KEY_DATASET_LABEL,
    KEY_DATASET_PERIOD,
    KEY_DATASET_ROWS,
)
from verify_lab.report.tables import print_dataframe
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.studies.reverse.constants import (
    DATASETS,
    DEFAULT_START_YEAR,
    DISPLAY_DIRECTION,
    DISPLAY_ERA,
    DISPLAY_EVENT_COUNT,
    DISPLAY_PARAMETER,
    DISPLAY_PRICE_BASIS,
    DISPLAY_TEST,
    DISPLAY_TICKER,
    HOLD_LIMIT,
    OUTPUT_FILES,
    PERIOD_ALL,
    STOP_LOSS_LEVEL,
    STOP_LOSS_LEVELS,
    TARGETS,
    TRACK_NAME,
    Dataset,
    Target,
)
from verify_lab.studies.reverse.runner import (
    KEY_DATASETS,
    KEY_EMPTY_SIGNAL_GROUPS,
    KEY_PRICE_BASIS,
    KEY_SIGNAL_GROUP_COUNT,
    StudyOutputs,
    run_study,
)
from verify_lab.studies.reverse.trading import KEY_STOP_LEVELS, StrategyOutputs, run_reverse_trading
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키. **매매법당 하나다** — 실행이 하나이므로
# 측정·체결로 키를 가르면 같은 실행이 두 줄로 남는다
KEY_META_REVERSE = "reverse"

# 터미널 표의 컬럼 이름. **폭은 적지 않는다** — `print_dataframe` 이 내용에서 계산한다
DISPLAY_ROW_COUNT = "행 수"
DISPLAY_PERIOD_RANGE = "기간"
DISPLAY_FILE = "파일"

# 터미널에 실을 발췌의 축. 전 조합은 CSV 에 있고, 화면은 기본 설정만 훑는 자리다
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
    DISPLAY_UP_RATE,
    DISPLAY_DOWN_RATE,
]


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    **손절선과 보유 한도는 인자가 아니다.** 확정된 규칙을 그대로 적용하는 것이 이 스크립트의
    설계이며, 값을 골라 넣는 노브로 쓰면 표본에 맞춘 튜닝이 된다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="역방향(역대급 등락 이후 수익률)의 측정과 체결을 한 번에 실행하고 결과를 저장합니다.")
    parser.add_argument(
        "--dataset",
        nargs="+",
        choices=[dataset.key for dataset in DATASETS],
        default=[dataset.key for dataset in DATASETS],
        help="대상 시세 (기본값: 전부). 국내 두 기준의 대조는 함께 돌려야 성립합니다",
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


def _selected_targets(keys: list[str]) -> list[Target]:
    """같은 키로 체결 대상을 고른다.

    **측정과 체결의 대상이 한 인자로 정해진다.** 따로 받으면 한 실행 안에서 둘이 갈릴 수 있고,
    그러면 같은 폴더의 두 표가 다른 범위를 재게 된다.

    Args:
        keys: 데이터셋 키 목록

    Returns:
        선택된 체결 대상 목록
    """
    return [target for target in TARGETS if target.dataset.key in keys]


def _print_rule() -> None:
    """적용한 체결 규칙을 먼저 보여준다.

    **손절선은 격자가 기본이다** — 무손절과 -2%~-10% 를 전부 낸다. 확정 손절선이 무엇인지는
    규칙 문서가 정하고 `손절선(%)` 한 컬럼으로 골라낸다.
    """
    logger.debug("진입: 신호일 종가")
    logger.debug(
        f"손절: 무손절 + 손절선 {len(STOP_LOSS_LEVELS)}종 격자 — 진입가 기준, 보유 기간 내내 고정 "
        f"(확정값은 {stop_level_value(STOP_LOSS_LEVEL, measurable=True)})"
    )
    logger.debug(f"청산: 종가가 진입가 위면 즉시 청산, 손실이면 D+{HOLD_LIMIT} 까지 보유")


def _print_datasets(outputs: StudyOutputs) -> None:
    """어떤 시세로 쟀는지 표로 보여준다.

    Args:
        outputs: 측정 산출물
    """
    table = pd.DataFrame(
        [
            {
                DISPLAY_TICKER: record[KEY_DATASET_LABEL],
                DISPLAY_PRICE_BASIS: record[KEY_PRICE_BASIS],
                DISPLAY_ROW_COUNT: record[KEY_DATASET_ROWS],
                DISPLAY_PERIOD_RANGE: record[KEY_DATASET_PERIOD],
                DISPLAY_FILE: record[KEY_DATASET_FILE],
            }
            for record in outputs.summary[KEY_DATASETS]
        ]
    )
    print_dataframe(table, logger, title="대상 시세")


def _print_excerpt(outputs: StudyOutputs) -> None:
    """기본 설정의 집계를 발췌해 보여준다.

    전 조합은 CSV 에 있다. 화면에는 기본 시작연도·구간 전체·가장 긴 측정 구간만 싣되,
    **저장한 표시용 프레임에서 그대로 골라** 화면과 CSV 의 숫자가 갈리지 않게 한다.

    Args:
        outputs: 측정 산출물
    """
    statistics = outputs.statistics
    selected = statistics[
        (statistics[DISPLAY_START_YEAR] == DEFAULT_START_YEAR)
        & (statistics[DISPLAY_ERA] == PERIOD_ALL.label)
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


def _print_performance(outputs: StrategyOutputs) -> None:
    """성적표에서 **무손절 행만** 화면에 보여준다.

    **격자 전체는 CSV 에 있다.** 손절선 10종 × 대상 4 × 구간 5 = 200행을 터미널에 쏟으면
    읽을 수 없고, 무손절 행이 맨몸 성적이라 측정 표와 대조하는 자리다
    (옵션 만기일·월말 CLI 와 같은 관용).

    **대상 하나가 구간 다섯 줄이다** — `전체 · 앞 절반 · 뒤 절반 · 최근 10년 · 최근 5년`
    (측정의 원칙 17). 균등 2분할만으로는 신호가 식는 것을 놓친다.

    시작연도만 문자열로 바꾸는 것은 **연도가 개수가 아니라 식별자**이기 때문이다 —
    표 출력의 천 단위 구분자가 걸리면 `2,005` 가 되어 CSV 의 `2005` 와 달라진다.

    Args:
        outputs: 체결 산출물
    """
    table = outputs.performance
    no_stop = table[table[DISPLAY_STOP_LEVEL] == NO_STOP_LABEL].astype({DISPLAY_START_YEAR: str})
    print_dataframe(no_stop, logger, title=f"대상 × 구간 성적 — {NO_STOP_LABEL} (격자 전체는 CSV 에)")


def _save(study: StudyOutputs, trading: StrategyOutputs, directory: Path) -> dict[str, int]:
    """측정 표와 체결 산출물을 한 폴더에 저장한다.

    **저장할 파일 목록의 SoT 는 `OUTPUT_FILES` 와 파일명 상수다.** CLI 가 이름을 적으면
    흩어진 문자열이 반드시 갈라진다 (`scripts/CLAUDE.md` 「CLI 에 도메인 로직 금지」).

    Args:
        study: 측정 산출물
        trading: 체결 산출물
        directory: 결과 폴더

    Returns:
        파일 이름 → 행 수
    """
    for field, filename in OUTPUT_FILES.items():
        save_table(directory, filename, getattr(study, field))

    save_table(directory, TRADES_FILENAME, trading.trades)
    save_table(directory, SUMMARY_FILENAME, trading.performance)

    summary = merge_run_summary(study.summary, trading.summary)
    save_run_summary(directory, summary)

    counts: dict[str, int] = summary[KEY_ROW_COUNTS]

    return counts


def _print_outputs(counts: dict[str, int], directory: Path) -> None:
    """무엇이 어디에 몇 행으로 남았는지 보여준다.

    Args:
        counts: 파일 이름 → 행 수
        directory: 결과 폴더
    """
    table = pd.DataFrame([{DISPLAY_FILE: filename, DISPLAY_ROW_COUNT: rows} for filename, rows in counts.items()])
    print_dataframe(table, logger, title=f"산출물 (저장 폴더: {directory})")


@cli_exception_handler
def main() -> int:
    """측정과 체결을 한 번에 돌고 결과를 저장한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()
    datasets = _selected_datasets(args.dataset)
    targets = _selected_targets(args.dataset)

    _print_rule()
    study = run_study(datasets, repeats=args.repeats, seed=args.seed)
    trading = run_reverse_trading(targets)

    directory = create_run_directory(TRACK_NAME)
    counts = _save(study, trading, directory)

    _print_datasets(study)
    _print_excerpt(study)
    _print_performance(trading)
    _print_outputs(counts, directory)

    logger.debug(
        f"신호군 {study.summary[KEY_SIGNAL_GROUP_COUNT]:,}개를 집계했습니다 "
        f"(신호 0건이라 빠진 신호군 {len(study.summary[KEY_EMPTY_SIGNAL_GROUPS]):,}개, "
        f"순열 검정 반복 {args.repeats:,}회·시드 {args.seed})"
    )

    save_metadata(
        KEY_META_REVERSE,
        {
            "result_dir": str(directory),
            "datasets": [
                record[KEY_DATASET_LABEL] + " " + record[KEY_PRICE_BASIS] for record in study.summary[KEY_DATASETS]
            ],
            "targets": [f"{target.dataset.label} K={target.rank_cut}" for target in targets],
            "signal_group_count": study.summary[KEY_SIGNAL_GROUP_COUNT],
            "empty_signal_group_count": len(study.summary[KEY_EMPTY_SIGNAL_GROUPS]),
            "stop_loss_levels": trading.summary[KEY_RULE][KEY_STOP_LEVELS],
            "hold_limit": HOLD_LIMIT,
            "row_counts": counts,
            "repeats": args.repeats,
            "seed": args.seed,
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
