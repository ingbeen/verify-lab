#!/usr/bin/env python3
"""반감기_사이클 실행 CLI — 측정과 체결을 한 번에 돈다

**격자 하나를 잰다** — 비트코인 반감기 뒤 0 ~ 45개월(3개월 간격)에 진입해 3 · 6 · 12개월 드는 48칸이다.
기준선은 첫 반감기부터 매일 진입해 같은 기간 든 성적이다. 한 번 돌리면 측정 표와 체결 산출물이 **한 폴더에**
함께 나오며, 어느 등급 폴더에 쌓일지는 `verify_lab/tracks.py` 의 레지스트리가 정한다.

**대상은 Bitstamp BTC/USD 하나다.** 거래량이 0 인 날의 종가는 Coin Metrics 기준가로 바꿔 재고(원시 파일은
그대로), 두 소스의 차이가 허용폭을 넘은 날과 바꾼 날을 표로 함께 낸다.

**체결은 무손절 한 종 · 「위」 한 방향이다** — 손절은 사용자가 따로 정한다.

[중요] **칸마다 표본이 사이클 수(3 ~ 4건)라 칸당 하한(`measure/constants.MIN_SAMPLE_PER_CELL`)에 못 미친다.** 「판정가능」이 전부 「아니오」이고
우연확률도 붙지 않는다 — **결론의 일부이지 버그가 아니다.** 48칸은 같은 사이클을 나눈 것이라 서로 독립이 아니다.

**맨몸 성적이다** — 수수료·슬리피지·세금을 넣지 않는다 (루트 `CLAUDE.md` 2026-09-06 확정).

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
from pathlib import Path

import pandas as pd

from verify_lab.execution.constants import (
    DISPLAY_RETURN,
    DISPLAY_TICKER,
    DISPLAY_TOTAL,
    DISPLAY_WIN_RATE,
    DISPLAY_WORST_HOLD,
    PERIOD_ALL,
    SUMMARY_FILENAME,
    TRADES_FILENAME,
)
from verify_lab.execution.run_summary import KEY_ROW_COUNTS, merge_run_summary
from verify_lab.measure.screening import SCREEN_CANDIDATE
from verify_lab.measure.statistics import DEFAULT_RANDOM_SEED, DEFAULT_REPEAT_COUNT
from verify_lab.report.constants import (
    DISPLAY_DOWN_RATE,
    DISPLAY_EXCLUDED,
    DISPLAY_EXCLUDED_REASON,
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
from verify_lab.studies.halving_cycle.constants import (
    DATASETS,
    DISPLAY_CALENDAR_YEAR,
    DISPLAY_ENTRY_MONTHS,
    DISPLAY_HALVING_POSITION,
    DISPLAY_HOLD_MONTHS,
    FIELD_CALENDAR_YEARS,
    FIELD_STATISTICS,
    OUTPUT_FILES,
    TRACK_NAME,
)
from verify_lab.studies.halving_cycle.runner import StudyOutputs, display_tables, run_study
from verify_lab.studies.halving_cycle.trading import TradingOutputs, run_halving_cycle_trading
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# `meta.json` 의 타입 키. **실행이 매매법당 하나이므로 키도 하나다**
KEY_META = "halving_cycle"

# 산출물 표의 컬럼
DISPLAY_FILE = "파일"
DISPLAY_ROW_COUNT = "행 수"


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(
        description="반감기_사이클 — 비트코인 반감기 뒤 0 ~ 45개월(3개월 간격)에 진입해 3 · 6 · 12개월 드는 48칸을 "
        "Bitstamp BTC/USD 로 재고, 무손절 체결 성적과 두 소스 대조 표를 함께 냅니다."
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=DEFAULT_REPEAT_COUNT,
        help=f"무작위 뽑기 대조 반복 수 (기본값: {DEFAULT_REPEAT_COUNT}). 칸마다 표본이 하한 미만이라 검정은 붙지 않는다",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help=f"무작위 뽑기 대조 시드 (기본값: {DEFAULT_RANDOM_SEED}). 결과 재현에 필요하다",
    )

    return parser.parse_args()


def _print_statistics(tables: dict[str, pd.DataFrame]) -> None:
    """칸마다의 핵심 값을 화면에 띄운다. 기준선과 차이는 excess 표에 있다.

    Args:
        tables: 저장할 표시용 프레임
    """
    columns = [
        DISPLAY_ENTRY_MONTHS,
        DISPLAY_HOLD_MONTHS,
        DISPLAY_SIGNAL_COUNT,
        DISPLAY_EXCLUDED,
        DISPLAY_SAMPLE_COUNT,
        DISPLAY_MEAN,
        DISPLAY_MEDIAN,
        DISPLAY_UP_RATE,
        DISPLAY_DOWN_RATE,
        DISPLAY_JUDGEABLE,
    ]
    print_dataframe(tables[FIELD_STATISTICS][columns], logger, title="측정 — 1배 롱 기준, 칸마다 표본은 사이클 수")


def _print_calendar_years(tables: dict[str, pd.DataFrame]) -> None:
    """달력 연도 표를 화면에 띄운다 (관찰용).

    Args:
        tables: 저장할 표시용 프레임
    """
    columns = [DISPLAY_CALENDAR_YEAR, DISPLAY_HALVING_POSITION, DISPLAY_RETURN, DISPLAY_EXCLUDED_REASON]
    # 연도는 수가 아니라 이름이다 — 숫자로 두면 화면 표가 천 단위 쉼표(`2,011`)를 붙인다. CSV 는 그대로다
    table = tables[FIELD_CALENDAR_YEARS][columns].astype({DISPLAY_CALENDAR_YEAR: str})
    print_dataframe(table, logger, title="달력 연도 — 전년 말 종가 대비 그해 말 종가 (관찰용)")


def _print_candidates(trading: TradingOutputs) -> None:
    """1차 판정이 「후보」인 칸을 화면에 띄운다.

    **후보는 자격이지 발견이 아니다.** 게이트를 넘었다는 뜻일 뿐이며, 표본이 하한에 못 미치고 칸끼리
    독립이 아니라는 사실은 그대로다.

    Args:
        trading: 체결 산출물
    """
    frame = trading.performance
    picked = frame[(frame[DISPLAY_PERIOD] == PERIOD_ALL) & (frame[DISPLAY_SCREEN] == SCREEN_CANDIDATE)]

    if picked.empty:
        logger.debug("1차 판정이 「후보」인 칸이 없습니다")
        return

    columns = [
        DISPLAY_TICKER,
        DISPLAY_ENTRY_MONTHS,
        DISPLAY_HOLD_MONTHS,
        DISPLAY_SIGNAL_COUNT,
        DISPLAY_TOTAL,
        DISPLAY_MEAN,
        DISPLAY_WIN_RATE,
        DISPLAY_WORST_HOLD,
        DISPLAY_JUDGEABLE,
    ]
    print_dataframe(picked[columns], logger, title=f"1차 판정 「후보」 ({len(picked)}칸 — 무손절 · 「위」)")


def _save(
    study: StudyOutputs,
    tables: dict[str, pd.DataFrame],
    trading: TradingOutputs,
    directory: Path,
) -> dict[str, int]:
    """측정 표와 체결 산출물을 한 폴더에 저장한다.

    Args:
        study: 측정 산출물
        tables: 저장할 표시용 프레임 (빈 표는 빠져 있다)
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
    trading = run_halving_cycle_trading(DATASETS)

    directory = create_run_directory(TRACK_NAME)
    counts = _save(study, tables, trading, directory)

    _print_statistics(tables)
    _print_calendar_years(tables)
    _print_candidates(trading)
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
