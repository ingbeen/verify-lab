#!/usr/bin/env python3
"""검증 #9 실행 CLI — 선물 대 레버리지 ETF

같은 자기자본·같은 목표 배수를 **① 레버리지 ETF ② 선물 매일 리밸런싱 ③ 선물 월 1회
리밸런싱** 세 방식으로 굴렸을 때 어느 쪽이 싼지를 잰다.

**인자는 지수로 좁히는 것 하나뿐이다.** 배수·격자·리밸런싱 주기·롤 규칙은 상수로 고정돼 있고
인자로 열지 않는다 — 노브가 되면 결과를 보고 고르게 되며 그것은 측정이 아니라 과최적화다
(루트 `CLAUDE.md` 측정의 원칙 1).

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
from pathlib import Path

import pandas as pd

from verify_lab.measure.constants import COL_HORIZON
from verify_lab.report.tables import print_dataframe, to_display_columns
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.studies.futures_leverage.constants import (
    BREAKEVEN_FILENAME,
    COL_WIPEOUT_COUNT,
    COMPARISON_FILENAME,
    DECOMPOSITION_FILENAME,
    INTEGER_CONTRACTS_FILENAME,
    LEVERAGE_DRIFT_FILENAME,
    OUTPUT_LABELS,
    PAIRS,
    PERCENT_OUTPUT_COLUMNS,
    ROLL_EVENTS_FILENAME,
    STUDY_NAME,
    WIPEOUTS_FILENAME,
)
from verify_lab.studies.futures_leverage.runner import StudyOutputs, run_study
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_FUTURES_LEVERAGE_STUDY = "futures_leverage_study"

# 시작일 원자료 파일명. 짝마다 하나씩 나온다
WINDOWS_FILENAME_TEMPLATE = "windows_{pair}.csv"

# 화면에 먼저 띄울 보유 기간 (거래일). 전 격자를 찍으면 화면을 넘긴다
SCREEN_HORIZON = 252

# ============================================================
# 산출물 헤더 — 영문 계산 컬럼을 한글 레이블로 바꾼다
#
# **`DISPLAY_*` 를 정의만 하고 rename 에 연결하지 않으면 규칙을 지킨 것이 아니다.**
# 공통 컬럼(구간·표본·제외)은 `report/constants.py` 의 것을 재사용해
# 검증마다 다른 말을 쓰지 않게 한다
# ============================================================


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="선물과 레버리지 ETF 중 어느 쪽이 레버리지를 싸게 구현하는지 잽니다.")
    parser.add_argument(
        "--index",
        default=None,
        choices=sorted({pair.index_name for pair in PAIRS}),
        help="지수로 좁힌다 (기본값: 전부)",
    )
    return parser.parse_args()


def _display(table: pd.DataFrame) -> pd.DataFrame:
    """저장 직전에 헤더를 한글로 바꾸고 비율을 백분율로 맞춘다.

    사전은 **`src` 가 소유한다** (`OUTPUT_LABELS`). 표마다 컬럼 구성이 다르므로 변환 대상은
    그 표에 실제로 있는 것만 고른다. 사전에 없는 컬럼이 하나라도 있으면 `to_display_columns` 가
    예외를 던진다 — 컬럼을 새로 만들고 한글 이름을 빠뜨리면 영문 토큰이 그대로 사용자에게 나간다.

    Args:
        table: 저장할 표 (영문 헤더)

    Returns:
        헤더가 한글이고 단위가 맞춰진 표
    """
    columns = set(table.columns)

    return to_display_columns(
        table,
        OUTPUT_LABELS,
        percent_columns=[column for column in PERCENT_OUTPUT_COLUMNS if column in columns],
    )


def _save_outputs(outputs: StudyOutputs) -> str:
    """산출물을 결과 폴더에 저장하고 폴더 경로를 돌려준다.

    **CSV 는 사용자가 여는 파일이라 헤더가 한글이어야 한다.** 영문 토큰이 그대로 나가면
    무슨 값인지 알 수 없다 (`src/verify_lab/CLAUDE.md` 「내부/출력 분리」).

    Args:
        outputs: 검증 산출물

    Returns:
        결과 폴더 경로 문자열
    """
    directory = create_run_directory(STUDY_NAME)

    save_table(directory, COMPARISON_FILENAME, _display(outputs.comparison))
    save_table(directory, DECOMPOSITION_FILENAME, _display(outputs.decomposition))
    save_table(directory, ROLL_EVENTS_FILENAME, _display(outputs.roll_events))
    save_table(directory, BREAKEVEN_FILENAME, _display(outputs.breakeven))
    save_table(directory, LEVERAGE_DRIFT_FILENAME, _display(outputs.leverage_drift))
    save_table(directory, WIPEOUTS_FILENAME, _display(outputs.wipeouts))
    save_table(directory, INTEGER_CONTRACTS_FILENAME, _display(outputs.integer_contracts))

    for pair_name, windows in outputs.windows_by_pair.items():
        save_table(
            directory,
            WINDOWS_FILENAME_TEMPLATE.format(pair=pair_name),
            _display(windows),
        )

    return str(directory)


@cli_exception_handler
def main() -> int:
    """검증을 실행하고 결과를 표로 표시한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()
    outputs = run_study(index_filter=args.index)

    directory = _save_outputs(outputs)
    summary = {
        "index_filter": args.index,
        "pair_count": outputs.pair_count,
        "skipped_pairs": [{"ticker": ticker, "reason": reason} for ticker, reason in outputs.skipped_pairs],
        "comparison_rows": len(outputs.comparison),
        "decomposition_rows": len(outputs.decomposition),
        "roll_event_rows": len(outputs.roll_events),
        "breakeven_rows": len(outputs.breakeven),
        "wipeout_window_total": int(outputs.wipeouts[COL_WIPEOUT_COUNT].sum()),
        "integer_contract_rows": len(outputs.integer_contracts),
        "window_files": sorted(outputs.windows_by_pair),
    }
    # **결과 폴더 안에도 요약을 남긴다.** 실행 이력(`meta.json`)은 최근 N개만 순환 저장하므로
    # 오래된 실행은 그 폴더만 남고 「무슨 조건으로 돌렸는지」를 잃는다
    save_run_summary(Path(directory), summary)

    screen = outputs.comparison[outputs.comparison[COL_HORIZON] == SCREEN_HORIZON]
    if not screen.empty:
        print_dataframe(
            _display(screen),
            logger,
            title=f"보유 {SCREEN_HORIZON}거래일 — 방식별 성적",
        )

    if not outputs.breakeven.empty:
        print_dataframe(_display(outputs.breakeven), logger, title="선물이 앞서기 시작하는 보유 기간")

    if not outputs.integer_contracts.empty:
        print_dataframe(
            _display(outputs.integer_contracts),
            logger,
            title="정수 계약 대조 — 자기자본 규모별 실제 배수",
        )

    for ticker, reason in outputs.skipped_pairs:
        logger.warning(f"건너뛴 짝 - {ticker}: {reason}")

    save_metadata(KEY_META_FUTURES_LEVERAGE_STUDY, {"directory": directory, **summary})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
