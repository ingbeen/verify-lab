#!/usr/bin/env python3
"""중간선거_사이클 실행 CLI — 측정과 체결을 한 번에 돈다

**규칙은 하나다** — 9월 마지막 거래일 종가 매수 → 다음해 6월 마지막 거래일 종가 매도.
진입·청산 격자를 두지 않는다. 한 번 돌리면 측정 표와 체결 산출물이 **한 폴더에** 함께
나오며, 어느 등급 폴더에 쌓일지는 `verify_lab/tracks.py` 의 레지스트리가 정한다.

**축은 중간선거해 한 칸이다** (사용자 결정). 사이클 네 칸을 견주어 달력 효과와 선거 효과를
가른 대조는 10월 첫 거래일 진입으로 잰 기록이며 `docs/매매/중간선거_사이클/결과.md` 가 갖는다.

**보유가 달력 분기에 맞아떨어진다** — 9월 말에 사서 6월 말에 팔므로 4분기·1분기·2분기 셋이다.
그 분해와 「보통 얼마나 밀리나」를 **분기 표 둘**이 낸다 (이름의 소유자는 그 매매법의 `constants`).

**분할매수 격자와 진입 위치**도 함께 낸다 — 분할매수는 무손절 · 배정액 기준이고, 진입 위치는
진입일의 지표(52주 최고 대비 · 이격도 · RSI)를 그 해의 결과와 나란히 싣는다.

[중요] **살 수 있는 대상의 중간선거 칸 표본이 6~8건이라 칸당 하한(10)에 못 미친다.**
「판정가능」이 전 구간에서 「아니오」가 되고 우연확률도 붙지 않는다 — **결론의 일부이지
버그가 아니다.** 지수 둘은 그 앞을 보여주려고 함께 재지만 살 수 없어 판정하지 않는다.

**맨몸 성적이다** — 수수료·슬리피지·세금을 넣지 않는다 (루트 `CLAUDE.md` 2026-09-06 확정).

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
from pathlib import Path

import pandas as pd

from verify_lab.execution.constants import (
    DISPLAY_DIRECTION,
    DISPLAY_RETURN,
    DISPLAY_STOP_LEVEL,
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
from verify_lab.studies.midterm_cycle.constants import (
    DATASETS,
    DISPLAY_CYCLE_POSITION,
    DISPLAY_CYCLE_YEAR,
    DISPLAY_DISPARITY_LONG,
    DISPLAY_FALLBACK,
    DISPLAY_FIRST_QUARTER_RETURN,
    DISPLAY_HIGH_DISTANCE,
    DISPLAY_HOLD_WORST_MEAN,
    DISPLAY_LUMP_DIFF,
    DISPLAY_MEAN_INVESTED,
    DISPLAY_QUARTER,
    DISPLAY_RSI,
    DISPLAY_RULE_FILLED,
    DISPLAY_SPLIT_METHOD,
    DISPLAY_WORST_DEEPEST,
    DISPLAY_WORST_MEAN,
    DISPLAY_WORST_MEDIAN,
    DISPLAY_WORST_Q25,
    DISPLAY_WORST_Q75,
    ENTRY_CONTEXT_FILENAME,
    OUTPUT_FILES,
    QUARTER_SUMMARY_FILENAME,
    QUARTER_TRADES_FILENAME,
    SPLIT_SUMMARY_FILENAME,
    SPLIT_TRADES_FILENAME,
    TRACK_NAME,
    datasets_of,
)
from verify_lab.studies.midterm_cycle.runner import StudyOutputs, display_tables, run_study
from verify_lab.studies.midterm_cycle.trading import TradingOutputs, run_midterm_cycle_trading
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# `meta.json` 의 타입 키. **실행이 매매법당 하나이므로 키도 하나다**
KEY_META = "midterm_cycle"

# 산출물 표의 컬럼
DISPLAY_FILE = "파일"
DISPLAY_ROW_COUNT = "행 수"

# 화면에 띄울 성적표 행 수 상한. 전부는 CSV 에 있다
PREVIEW_LIMIT = 24


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(
        description="중간선거_사이클 — 9월 마지막 거래일에 사서 다음해 6월 마지막 거래일에 파는 매매법을 " "중간선거해에서 측정하고, 체결 성적과 분기 분해를 함께 냅니다."
    )
    parser.add_argument(
        "--ticker",
        action="append",
        help="대상 종목 또는 지수 이름. 여러 번 줄 수 있다 "
        f"(기본값: 전부 {[dataset.ticker for dataset in DATASETS]}). "
        "지수는 장중 손절을 잴 수 없어 「손절불가」 한 줄로만 나온다",
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
    """측정 표의 핵심 컬럼을 화면에 띄운다.

    Args:
        tables: 저장할 표시용 프레임
    """
    columns = [
        DISPLAY_TICKER,
        DISPLAY_CYCLE_POSITION,
        DISPLAY_SIGNAL_COUNT,
        DISPLAY_SAMPLE_COUNT,
        DISPLAY_MEAN,
        DISPLAY_MEDIAN,
        DISPLAY_UP_RATE,
        DISPLAY_JUDGEABLE,
    ]
    for table in tables.values():
        print_dataframe(table[columns], logger, title="측정 — 1배 롱 기준 (기준선은 그 해 아무 달 진입이다)")


def _print_candidates(trading: TradingOutputs) -> None:
    """1차 판정이 「후보」인 칸을 화면에 띄운다.

    **후보는 자격이지 발견이 아니다.** 게이트를 넘었다는 뜻일 뿐이며,
    **표본이 하한에 못 미친다는 사실은 그대로다.**

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
        DISPLAY_CYCLE_POSITION,
        DISPLAY_DIRECTION,
        DISPLAY_STOP_LEVEL,
        DISPLAY_SIGNAL_COUNT,
        DISPLAY_TOTAL,
        DISPLAY_MEAN,
        DISPLAY_WIN_RATE,
        DISPLAY_WORST_HOLD,
        DISPLAY_JUDGEABLE,
    ]
    print_dataframe(picked[columns].head(PREVIEW_LIMIT), logger, title=f"1차 판정 「후보」 ({len(picked)}칸)")


def _print_quarters(trading: TradingOutputs) -> None:
    """분기별 수익과 보유 중 최악의 분포를 화면에 띄운다.

    **성적표의 `보유 중 최악(%)` 은 가장 깊은 한 건**이라 「보통 얼마나 밀리나」에 답하지
    못한다 — 평균·중앙값·분위가 그 자리를 채운다.

    Args:
        trading: 체결 산출물
    """
    columns = [
        DISPLAY_TICKER,
        DISPLAY_QUARTER,
        DISPLAY_SAMPLE_COUNT,
        DISPLAY_MEAN,
        DISPLAY_MEDIAN,
        DISPLAY_UP_RATE,
        DISPLAY_WORST_MEAN,
        DISPLAY_WORST_MEDIAN,
        DISPLAY_WORST_Q25,
        DISPLAY_WORST_Q75,
        DISPLAY_WORST_DEEPEST,
    ]
    print_dataframe(
        trading.quarter_summary[columns],
        logger,
        title="분기 분해 — 수익과 «진입가 대비» 보유 중 최악의 분포 (무손절)",
    )


def _print_split(trading: TradingOutputs) -> None:
    """분할매수 집계를 화면에 띄운다.

    **평균만 보지 않게 보유 중 최악과 투자 비율을 함께 띄운다** — 분할은 평균을 깎고 최악을
    줄이는 교환이라 한쪽만 보면 판단이 기운다.

    Args:
        trading: 체결 산출물
    """
    columns = [
        DISPLAY_TICKER,
        DISPLAY_SPLIT_METHOD,
        DISPLAY_FALLBACK,
        DISPLAY_SAMPLE_COUNT,
        DISPLAY_MEAN,
        DISPLAY_MEDIAN,
        DISPLAY_LUMP_DIFF,
        DISPLAY_HOLD_WORST_MEAN,
        DISPLAY_WORST_HOLD,
        DISPLAY_MEAN_INVESTED,
        DISPLAY_RULE_FILLED,
    ]
    print_dataframe(
        trading.split_summary[columns],
        logger,
        title="분할매수 — 무손절 · 배정액 기준 (현금으로 남은 몫은 수익 0)",
    )


def _print_entry_context(trading: TradingOutputs) -> None:
    """진입 위치 표를 화면에 띄운다.

    Args:
        trading: 체결 산출물
    """
    columns = [
        DISPLAY_TICKER,
        DISPLAY_CYCLE_YEAR,
        DISPLAY_HIGH_DISTANCE,
        DISPLAY_DISPARITY_LONG,
        DISPLAY_RSI,
        DISPLAY_RETURN,
        DISPLAY_WORST_HOLD,
        DISPLAY_FIRST_QUARTER_RETURN,
    ]
    print_dataframe(
        trading.entry_context[columns],
        logger,
        title="진입 위치 — 진입일 지표와 그 해의 결과 (창이 차기 전은 빈칸)",
    )


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
    save_table(directory, QUARTER_TRADES_FILENAME, trading.quarter_trades)
    save_table(directory, QUARTER_SUMMARY_FILENAME, trading.quarter_summary)
    save_table(directory, SPLIT_TRADES_FILENAME, trading.split_trades)
    save_table(directory, SPLIT_SUMMARY_FILENAME, trading.split_summary)
    save_table(directory, ENTRY_CONTEXT_FILENAME, trading.entry_context)

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

    datasets = datasets_of(tuple(args.ticker)) if args.ticker else DATASETS

    study = run_study(datasets, repeats=args.repeats, seed=args.seed)
    tables = display_tables(study)
    trading = run_midterm_cycle_trading(datasets)

    directory = create_run_directory(TRACK_NAME)
    counts = _save(study, tables, trading, directory)

    _print_statistics(tables)
    _print_quarters(trading)
    _print_entry_context(trading)
    _print_split(trading)
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
            "tickers": [dataset.ticker for dataset in datasets],
            "repeats": args.repeats,
            "seed": args.seed,
            KEY_ROW_COUNTS: counts,
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
