#!/usr/bin/env python3
"""하락_단계_매수 실행 CLI — 측정과 체결을 한 번에 돈다

**신호는 세 지표의 단계다** — 가격 낙폭 · VIX · 공포탐욕지수가 단계에 처음 닿은 날(회복하면 다시 켬).
판정일 다음 거래일 종가에 사서 보유 기간(거래일) 뒤 종가에 판다. 격자를 고르지 않고 전부 낸다 —
분할 방식 · 비중 · 청산 규칙은 이 결과를 본 뒤 정한다. 어느 등급 폴더에 쌓일지는 `verify_lab/tracks.py` 가 정한다.

**맨몸 성적이다** — 수수료 · 슬리피지 · 세금을 넣지 않는다 (루트 `CLAUDE.md` 2026-09-06 확정).

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
from pathlib import Path

import pandas as pd

from verify_lab.execution.constants import (
    DISPLAY_TICKER,
    DISPLAY_TOTAL,
    DISPLAY_WIN_RATE,
    DISPLAY_WORST_HOLD,
    PERIOD_ALL,
    SUMMARY_FILENAME,
    TRADES_FILENAME,
)
from verify_lab.execution.run_summary import KEY_ROW_COUNTS, merge_run_summary
from verify_lab.measure.statistics import DEFAULT_RANDOM_SEED, DEFAULT_REPEAT_COUNT
from verify_lab.report.constants import (
    DISPLAY_JUDGEABLE,
    DISPLAY_MEAN,
    DISPLAY_MEDIAN,
    DISPLAY_PERIOD,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_SCREEN,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_UP_RATE,
)
from verify_lab.report.tables import print_dataframe
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.studies.drawdown_tiers.constants import (
    CALENDAR_ALL,
    DATASETS,
    DISPLAY_CALENDAR_AXIS,
    DISPLAY_HORIZON,
    DISPLAY_INDICATOR,
    DISPLAY_TIER,
    FIELD_STATISTICS,
    OUTPUT_FILES,
    TRACK_NAME,
)
from verify_lab.studies.drawdown_tiers.runner import StudyOutputs, display_tables, run_study
from verify_lab.studies.drawdown_tiers.trading import TradingOutputs, run_drawdown_tiers_trading
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# `meta.json` 의 타입 키 — 실행이 매매법당 하나라 키도 하나
KEY_META = "drawdown_tiers"

# 산출물 표의 컬럼
DISPLAY_FILE = "파일"
DISPLAY_ROW_COUNT = "행 수"

# 화면에 띄울 대표 보유 기간 (거래일). 전부는 CSV 에 있다
PREVIEW_HORIZON = 252


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(
        description="하락_단계_매수 — 낙폭 · VIX · 공포탐욕지수가 단계에 처음 닿은 날의 다음 거래일 종가에 사서 "
        "보유 기간 뒤에 파는 맨몸 격자를 측정하고 체결 성적표를 함께 냅니다 "
        f"(대상 {' · '.join(dataset.label for dataset in DATASETS)})."
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


def _print_statistics(tables: dict[str, pd.DataFrame]) -> None:
    """달력 «전체» 칸 · 대표 보유 기간의 측정 표를 화면에 띄운다.

    Args:
        tables: 저장할 표시용 프레임
    """
    table = tables[FIELD_STATISTICS]
    picked = table[(table[DISPLAY_CALENDAR_AXIS] == CALENDAR_ALL) & (table[DISPLAY_HORIZON] == PREVIEW_HORIZON)]
    columns = [
        DISPLAY_TICKER,
        DISPLAY_INDICATOR,
        DISPLAY_TIER,
        DISPLAY_SIGNAL_COUNT,
        DISPLAY_SAMPLE_COUNT,
        DISPLAY_MEAN,
        DISPLAY_MEDIAN,
        DISPLAY_UP_RATE,
        DISPLAY_JUDGEABLE,
    ]
    print_dataframe(picked[columns], logger, title=f"측정 — 1배 롱 기준 · 보유 {PREVIEW_HORIZON}거래일 (나머지는 통계.csv)")


def _print_performance(trading: TradingOutputs) -> None:
    """대표 보유 기간 · 시기 «전체» 의 성적표를 화면에 띄운다 — 후보는 자격이지 발견이 아니다.

    Args:
        trading: 체결 산출물
    """
    frame = trading.performance
    picked = frame[(frame[DISPLAY_PERIOD] == PERIOD_ALL) & (frame[DISPLAY_HORIZON] == PREVIEW_HORIZON)]
    columns = [
        DISPLAY_TICKER,
        DISPLAY_INDICATOR,
        DISPLAY_TIER,
        DISPLAY_SIGNAL_COUNT,
        DISPLAY_TOTAL,
        DISPLAY_MEAN,
        DISPLAY_WIN_RATE,
        DISPLAY_WORST_HOLD,
        DISPLAY_SCREEN,
    ]
    print_dataframe(picked[columns], logger, title=f"성적표 — 무손절 · 보유 {PREVIEW_HORIZON}거래일 (나머지는 성적표.csv)")


def _save(
    study: StudyOutputs,
    tables: dict[str, pd.DataFrame],
    trading: TradingOutputs,
    directory: Path,
) -> dict[str, int]:
    """측정 표와 체결 산출물을 한 폴더에 저장한다.

    Args:
        study: 측정 산출물
        tables: 저장할 표시용 프레임
        trading: 체결 산출물
        directory: 결과 폴더

    Returns:
        파일 이름 → 행 수
    """
    for field, table in tables.items():
        save_table(directory, OUTPUT_FILES[field], table)

    save_table(directory, TRADES_FILENAME, trading.trades)
    save_table(directory, SUMMARY_FILENAME, trading.performance)

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

    study = run_study(DATASETS, repeats=args.repeats, seed=args.seed)
    tables = display_tables(study)
    trading = run_drawdown_tiers_trading(DATASETS)

    directory = create_run_directory(TRACK_NAME)
    counts = _save(study, tables, trading, directory)

    _print_statistics(tables)
    _print_performance(trading)
    print_dataframe(
        pd.DataFrame([{DISPLAY_FILE: name, DISPLAY_ROW_COUNT: rows} for name, rows in counts.items()]),
        logger,
        title=f"산출물 (저장 폴더: {directory})",
    )

    save_metadata(
        KEY_META,
        {
            "directory": str(directory),
            "tickers": [dataset.ticker for dataset in DATASETS],
            "repeats": args.repeats,
            "seed": args.seed,
            KEY_ROW_COUNTS: counts,
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
