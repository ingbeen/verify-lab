#!/usr/bin/env python3
"""검증 #7 실행 — 만기일 매수 → 다음주 청산 매매와 만기월별 후보 판정

만기월(1~12)로 쪼개 방향 비율을 재고, 각 칸을 **게이트 둘**(적중률 60% 이상 ·
방향 기대값 0 초과)로 판정한다. **등급은 없다** (2026-09-12 개편).
게이트를 넘지 못한 칸도 `candidates.csv` 에 값 그대로 남는다 — 화면에서만 빠진다.

가격 기준은 **원본가 하나**다. 사용자가 증권앱·차트에서 보는 가격이 곧 신호를 판정하고
주문을 거는 가격이기 때문이다 (루트 `CLAUDE.md` 측정의 원칙 14).

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
from pathlib import Path

import pandas as pd

from verify_lab.common_constants import RATE_TO_PERCENT, RESULT_LAYER_STUDY
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
    OUTPUT_FILES,
    OUTPUT_LABELS,
    PERCENT_OUTPUT_COLUMNS,
    PROBABILITY_OUTPUT_COLUMNS,
    TRACK_NAME,
    Dataset,
)
from verify_lab.studies.option_expiry.runner import (
    KEY_DATASETS,
    KEY_MAX_OFFSET,
    KEY_PERMUTATION_REPEATS,
    KEY_PERMUTATION_SEED,
    KEY_ROW_COUNTS,
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
    # **두 인자의 방식을 나머지 두 검증과 맞춘다.** 전에는 `--repeats` 만 `None` 기본값에
    # `kwargs` 로 넘기는 형태였고 `--seed` 는 아예 없었다 — runner 는 시드를 받는데
    # CLI 에서 고칠 수 없어, **시드를 바꾸려면 코드를 고쳐야** 했다
    # (`src/verify_lab/CLAUDE.md` 「난수는 시드를 인자로 받고 기본값을 상수로 둔다」)
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


def _save(directory: Path, filename: str, table: pd.DataFrame) -> None:
    """산출물을 **한글 헤더와 맞춘 단위로** 저장한다.

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


@cli_exception_handler
def main() -> int:
    """검증을 실행하고 산출물을 저장한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()
    datasets = _selected_datasets(args.dataset)

    outputs = run_study(datasets, repeats=args.repeats, seed=args.seed)

    directory = create_run_directory(TRACK_NAME, layer=RESULT_LAYER_STUDY)
    # **저장할 파일 목록의 SoT 는 `OUTPUT_FILES` 하나다.** 여기 나열하면 요약의 행 수와
    # 실제 파일이 갈릴 수 있고, 파일 이름을 CLI 가 소유하면 흩어진 문자열이 반드시 갈라진다
    # (`scripts/CLAUDE.md` 「CLI 에 도메인 로직 금지」)
    for field, filename in OUTPUT_FILES.items():
        _save(directory, filename, getattr(outputs, field))

    _display_headline(outputs)

    # **요약에 값을 끼워 넣지 않는다.** 전에는 `output_dir` 로 이 PC 의 절대경로를 한 칸 얹었는데,
    # 그 값은 파일이 놓인 폴더 «자신»이라 잉여이기도 했다 (`scripts/CLAUDE.md` 「CLI 에 도메인 로직 금지」).
    # `meta.json` 쪽은 남긴다 — git 제외라 PC 를 넘지 않고 「최근 실행이 어디 있나」가 그 파일의 용도다
    save_run_summary(directory, outputs.summary)
    save_metadata(
        KEY_META_OPTION_EXPIRY,
        {
            "output_dir": str(directory),
            KEY_DATASETS: [dataset.key for dataset in datasets],
            KEY_MAX_OFFSET: outputs.summary[KEY_MAX_OFFSET],
            KEY_PERMUTATION_REPEATS: outputs.summary[KEY_PERMUTATION_REPEATS],
            KEY_PERMUTATION_SEED: outputs.summary[KEY_PERMUTATION_SEED],
            KEY_ROW_COUNTS: outputs.summary[KEY_ROW_COUNTS],
        },
    )

    logger.debug(f"산출물 저장 위치: {directory}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
