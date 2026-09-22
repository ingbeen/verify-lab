#!/usr/bin/env python3
"""만기_말일 실행 CLI — 측정과 체결을 한 번에 돈다

진입 2종(셋째 금요일 · 20일) × 청산 2종(다음 주 금요일 · 그 달 마지막 거래일)을 교차해
**9월·12월**에서 여섯 대상을 잰다. 한 번 돌리면 측정 표와 체결 산출물이 **한 폴더에**
함께 나오며, 어느 등급 폴더에 쌓일지는 `verify_lab/tracks.py` 의 레지스트리가 정한다.

[중요] **네 조합이 언제나 네 개의 다른 매매인 것은 아니다.** 해에 따라 진입·청산이 둘 다
같아져 **절반 가까운 해에서 두 조합이 한 매매**가 된다. 조합 간 성적 차이가 몇 건에서
나온 것인지는 측정 표의 **「이 조합만 다른 해」**가 말한다 — 그 값은 매 실행 다시 세므로
여기에 숫자를 적지 않는다.

[중요] **9월·12월은 사후에 고른 달이다** — 두 매매법이 이미 그 달을 가리킨 뒤에 골랐으므로
이 성적으로 「우위가 있다」를 새로 주장할 수 없고, 용도는 **조합 간 비교**다.

**손절선은 확정 −5% 와 무손절 대조 두 종뿐이다.** 이 검증이 고른 값이 아니라 두 매매법이
이미 확정한 값이고, 무손절은 `.claude/rules/trading.md` 가 요구하는 대조축이다.
**격자 스위치를 두지 않는다** — 조합을 비교하는 것이 목적이라 손절선까지 축으로 두면
무엇이 차이를 만들었는지 갈리지 않는다.

**맨몸 성적이다** — 수수료·슬리피지·세금을 넣지 않는다 (루트 `CLAUDE.md` 2026-09-06 확정).

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
from pathlib import Path

import pandas as pd

from verify_lab.execution.constants import (
    DISPLAY_DIRECTION,
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
    DISPLAY_MEAN,
    DISPLAY_MEDIAN,
    DISPLAY_MONTH_NUMBER,
    DISPLAY_PERIOD,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_SCREEN,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_UP_RATE,
)
from verify_lab.report.tables import print_dataframe
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.studies.expiry_monthend.constants import (
    DATASETS,
    DISPLAY_COMBO,
    DISPLAY_SHARED_YEARS,
    DISPLAY_UNIQUE_YEARS,
    MONTHS,
    OUTPUT_FILES,
    TRACK_NAME,
    Dataset,
    combos_of,
)
from verify_lab.studies.expiry_monthend.runner import StudyOutputs, display_tables, run_study
from verify_lab.studies.expiry_monthend.trading import TradingOutputs, run_expiry_monthend_trading
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# `meta.json` 의 타입 키. **실행이 매매법당 하나이므로 키도 하나다**
KEY_META = "expiry_monthend"

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
    parser = argparse.ArgumentParser(description="만기_말일 — 진입 2종 × 청산 2종을 교차해 9월·12월을 측정하고 체결 성적을 함께 냅니다.")
    parser.add_argument(
        "--ticker",
        action="append",
        help="대상 종목 또는 지수 코드. 여러 번 줄 수 있다 (기본값: 여섯 대상 전부). " "지수는 장중 손절을 잴 수 없어 「손절불가」 한 줄로만 나온다",
    )
    parser.add_argument(
        "--combo",
        action="append",
        help="돌릴 조합. 여러 번 줄 수 있다 (기본값: 넷 전부). c1=만기→다음주금 · c2=만기→말일 · "
        "c3=20일→다음주금 · c4=20일→말일. 좁히면 조합 비교가 성립하지 않으므로 대조용이다",
    )
    parser.add_argument(
        "--month",
        action="append",
        type=int,
        help=f"재는 달. 여러 번 줄 수 있다 (기본값: {list(MONTHS)})",
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


def _known(tickers: list[str] | None) -> tuple[Dataset, ...]:
    """지목한 코드를 대상 정의로 바꾼다.

    Args:
        tickers: 종목 또는 지수 코드 목록. `None` 이면 전부

    Returns:
        고른 대상 목록

    Raises:
        ValueError: 알 수 없는 코드를 지목한 경우
    """
    if tickers is None:
        return DATASETS

    known = {dataset.ticker: dataset for dataset in DATASETS}
    unknown = sorted(set(tickers) - set(known))
    if unknown:
        raise ValueError(f"모르는 종목입니다: {unknown} (가능한 값: {sorted(known)})")

    return tuple(dataset for dataset in DATASETS if dataset.ticker in set(tickers))


def _months(months: list[int] | None) -> tuple[int, ...]:
    """지목한 달을 정리한다.

    Args:
        months: 달 목록. `None` 이면 기본값

    Returns:
        오름차순 정렬된 달 목록

    Raises:
        ValueError: 달이 1~12 를 벗어난 경우
    """
    if months is None:
        return MONTHS

    invalid = sorted(month for month in months if not 1 <= month <= 12)
    if invalid:
        raise ValueError(f"달은 1~12 이어야 합니다: {invalid}")

    return tuple(sorted(set(months)))


def _print_statistics(tables: dict[str, pd.DataFrame]) -> None:
    """측정 표의 핵심 컬럼을 화면에 띄운다.

    Args:
        tables: 저장할 표시용 프레임
    """
    columns = [
        DISPLAY_TICKER,
        DISPLAY_COMBO,
        DISPLAY_MONTH_NUMBER,
        DISPLAY_SIGNAL_COUNT,
        DISPLAY_SAMPLE_COUNT,
        DISPLAY_MEAN,
        DISPLAY_MEDIAN,
        DISPLAY_UP_RATE,
        DISPLAY_SHARED_YEARS,
        DISPLAY_UNIQUE_YEARS,
    ]
    for table in tables.values():
        print_dataframe(table[columns], logger, title="측정 — 1배 롱 기준 (아래로 걸면 부호가 뒤집힌다)")


def _print_candidates(trading: TradingOutputs) -> None:
    """1차 판정이 「후보」인 칸을 화면에 띄운다.

    **후보는 자격이지 발견이 아니다.** 게이트를 넘었다는 뜻일 뿐이며,
    9월·12월이 사후에 고른 달이라는 사실은 그대로다.

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
        DISPLAY_COMBO,
        DISPLAY_MONTH_NUMBER,
        DISPLAY_DIRECTION,
        DISPLAY_STOP_LEVEL,
        DISPLAY_SIGNAL_COUNT,
        DISPLAY_TOTAL,
        DISPLAY_MEAN,
        DISPLAY_WIN_RATE,
        DISPLAY_WORST_HOLD,
    ]
    print_dataframe(picked[columns].head(PREVIEW_LIMIT), logger, title=f"1차 판정 「후보」 ({len(picked)}칸)")


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
    datasets = _known(args.ticker)
    combos = combos_of(tuple(args.combo) if args.combo else None)
    months = _months(args.month)

    study = run_study(datasets, combos=combos, months=months, repeats=args.repeats, seed=args.seed)
    tables = display_tables(study)
    trading = run_expiry_monthend_trading(datasets, combos=combos, months=months)

    directory = create_run_directory(TRACK_NAME)
    counts = _save(study, tables, trading, directory)

    _print_statistics(tables)
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
            "combos": [combo.label for combo in combos],
            "months": list(months),
            "repeats": args.repeats,
            "seed": args.seed,
            KEY_ROW_COUNTS: counts,
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
