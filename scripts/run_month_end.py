#!/usr/bin/env python3
"""월말 진입 실행 CLI — 측정과 체결을 한 번에 돈다 (20일 매수 → 말일 매도), 코스피·코스닥

**기본 실행은 확정 칸과 확정 손절선만 낸다** (2026-09-21 사용자 결정). 폴더에 생기는
표는 **측정 한 장과 체결 둘**이며, 이름은 각 계층의 상수가 소유한다.

**등급(검증·매매)은 분류일 뿐이라 실행을 가르지 않는다.** 한 번 돌리면 측정 표와
체결 산출물이 **한 폴더에** 함께 나오며, 어느 등급 폴더에 쌓일지는
`verify_lab/tracks.py` 의 레지스트리가 정한다.

**측정과 체결의 기본 대상이 다르다.** 측정은 8대상 전부(인버스·지수 포함)이고 체결은
인버스를 뺀 여섯이다 — 인버스는 1배의 부호를 뒤집은 값과 차이가 잡음이라 같은 베팅이
두 줄로 실린다. `--ticker` 로 지목하면 양쪽 다 그 대상으로 좁아진다.

**`--stop-grid` 는 격자를 «전부» 켜는 스위치일 뿐이고 값을 고르게 해 주지 않는다** —
손절선 값을 인자로 받으면 그것은 「성과가 좋아지는 값을 찾아 돌리기」가 된다
(`.claude/rules/trading.md`).

**맨몸 성적이다** — 수수료·슬리피지·세금을 넣지 않는다 (루트 `CLAUDE.md` 2026-09-06 확정).

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
from pathlib import Path

import pandas as pd

from verify_lab.execution.constants import (
    DISPLAY_DIRECTION,
    DISPLAY_GAP_STOP_COUNT,
    DISPLAY_INTRADAY_STOP_COUNT,
    DISPLAY_STOP_LEVEL,
    DISPLAY_TICKER,
    DISPLAY_TOTAL,
    DISPLAY_WIN_RATE,
    DISPLAY_WORST_HOLD,
    PERIOD_ALL,
    STOP_NOT_MEASURABLE_LABEL,
    SUMMARY_FILENAME,
    TRADES_FILENAME,
    stop_level_value,
)
from verify_lab.execution.run_summary import KEY_ROW_COUNTS, KEY_RULE, merge_run_summary
from verify_lab.measure.screening import SCREEN_CANDIDATE, SCREEN_NOT_JUDGED
from verify_lab.measure.statistics import DEFAULT_RANDOM_SEED, DEFAULT_REPEAT_COUNT
from verify_lab.report.constants import (
    DISPLAY_DIVIDEND_HIT_COUNT,
    DISPLAY_DIVIDEND_MEAN_IMPACT,
    DISPLAY_DIVIDEND_MEASURED,
    DISPLAY_DOWN_RATE,
    DISPLAY_DOWN_RATE_DIFF,
    DISPLAY_DOWN_RATE_P_VALUE,
    DISPLAY_JUDGEABLE,
    DISPLAY_MEAN,
    DISPLAY_MEDIAN,
    DISPLAY_MIN,
    DISPLAY_MONTH_NUMBER,
    DISPLAY_PERIOD,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_SCREEN,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_UP_RATE,
)
from verify_lab.report.tables import print_dataframe
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.studies.month_end.constants import (
    BASELINE_PREFIX,
    DATASETS,
    DATASETS_TRADING,
    MONTH_END_STOP_DEFAULT,
    MONTH_END_STOP_GRID,
    MONTH_END_STOP_LEVEL,
    OUTPUT_FILES,
    TRACK_NAME,
    Dataset,
)
from verify_lab.studies.month_end.runner import (
    FIELD_MEASURE,
    StudyOutputs,
    display_tables,
    run_study,
)
from verify_lab.studies.month_end.trading import (
    KEY_CELLS,
    KEY_FROM_YEAR,
    KEY_STOP_LEVELS,
    TradingOutputs,
    run_month_end_trading,
)
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키. **매매법당 하나다** — 실행이 하나이므로
# 측정·체결로 키를 가르면 같은 실행이 두 줄로 남는다
KEY_META_MONTH_END = "month_end"

# 산출물 표의 컬럼 이름. **폭은 적지 않는다** — `print_dataframe` 이 내용에서 계산한다
DISPLAY_FILE = "파일"
DISPLAY_ROW_COUNT = "행 수"

# 화면에 낼 측정 표의 컬럼. 전 컬럼(40여 개)을 내면 가로로 넘쳐 읽을 수 없다.
# **값은 1배 롱 기준 그대로**라 「아래」 칸이어도 부호가 뒤집히지 않는다
HEADLINE_COLUMNS = [
    DISPLAY_TICKER,
    DISPLAY_MONTH_NUMBER,
    DISPLAY_DIRECTION,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_MEAN,
    DISPLAY_MEDIAN,
    DISPLAY_UP_RATE,
    DISPLAY_DOWN_RATE,
    f"{BASELINE_PREFIX}{DISPLAY_DOWN_RATE}",
    DISPLAY_DOWN_RATE_DIFF,
    DISPLAY_DOWN_RATE_P_VALUE,
    # **대조 건수를 함께 낸다.** 「걸린 건 0」과 「수정주가가 없어 못 쟀다」는 다른 사실이고,
    # 그 구별이 없으면 화면이 «없는 안전»을 보고한다 (`measure/constants.py`)
    DISPLAY_DIVIDEND_MEASURED,
    DISPLAY_DIVIDEND_HIT_COUNT,
    DISPLAY_DIVIDEND_MEAN_IMPACT,
    DISPLAY_JUDGEABLE,
]

# 화면에 낼 후보 칸의 컬럼. **성적표의 이름을 쓴다** — 판정이 그 표 안에 있기 때문이다
CANDIDATE_COLUMNS = [
    DISPLAY_TICKER,
    DISPLAY_MONTH_NUMBER,
    DISPLAY_DIRECTION,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_WIN_RATE,
    DISPLAY_MEAN,
    DISPLAY_TOTAL,
]

# 확정 손절선 행을 고르는 값 둘. **`손절불가`(지수라 못 잰다)를 함께 골라야 긴 기간 축을
# 잃지 않는다** — 숫자만 고르면 지수 넷이 통째로 빠진다 (`.claude/rules/trading.md`).
# **`무손절` 은 넣지 않는다** — 기본 실행이 그 행을 내지 않고, `--stop-grid` 로 돌린
# 실행에서 함께 고르면 같은 대상이 두 번 실린다
FIXED_STOP_DISPLAY = stop_level_value(MONTH_END_STOP_LEVEL, measurable=True)
FIXED_STOP_LABELS = (FIXED_STOP_DISPLAY, STOP_NOT_MEASURABLE_LABEL)

# 화면에 낼 성적표 컬럼
PERFORMANCE_COLUMNS = [
    DISPLAY_TICKER,
    DISPLAY_MONTH_NUMBER,
    DISPLAY_DIRECTION,
    DISPLAY_STOP_LEVEL,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_TOTAL,
    DISPLAY_MEAN,
    DISPLAY_WIN_RATE,
    DISPLAY_MIN,
    DISPLAY_WORST_HOLD,
    DISPLAY_GAP_STOP_COUNT,
    DISPLAY_INTRADAY_STOP_COUNT,
]


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="월말 진입(20일 매수 → 말일 매도)의 확정 칸을 측정하고 체결 성적을 함께 냅니다.")
    parser.add_argument(
        "--ticker",
        action="append",
        help="대상 종목 또는 지수 코드. 여러 번 줄 수 있다 "
        "(기본값: 측정은 코스피·코스닥 8대상 전부, 체결은 인버스를 뺀 여섯). "
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
    parser.add_argument(
        "--stop-grid",
        action="store_true",
        help="손절선 격자를 전부 돈다 (기본값: 확정 손절선 한 종). 시세를 재수집해 손절선을 "
        "다시 골라야 할 때 쓰는 스위치이며, 무손절 대조축도 함께 나온다. "
        "값을 고르는 노브가 아니다",
    )
    parser.add_argument(
        "--from-year",
        type=int,
        default=None,
        help="이 연도의 진입부터 체결을 잰다 (기본값: 전 기간). 「2000년 이전 시장은 다르다」 같은 "
        "미리 정한 구간을 대조하는 축이며, 성과가 좋아지는 값을 찾는 노브가 아니다. "
        "쓴 값은 summary.json 에 남는다",
    )

    return parser.parse_args()


def _known(tickers: list[str] | None) -> tuple[Dataset, ...] | None:
    """지목한 코드를 대상 정의로 바꾼다.

    **조회는 `DATASETS` 기준이다** — 체결 기본값으로 좁히면 인버스를 지목했을 때 막힌다.

    Args:
        tickers: 종목 또는 지수 코드 목록. `None` 이면 `None` 을 돌려준다

    Returns:
        고른 대상 목록. 지목이 없으면 `None`

    Raises:
        ValueError: 알 수 없는 코드를 지목한 경우
    """
    if not tickers:
        return None

    known = {dataset.ticker: dataset for dataset in DATASETS}
    unknown = [ticker for ticker in tickers if ticker not in known]
    if unknown:
        raise ValueError(f"알 수 없는 대상 코드입니다: {unknown} (가능한 값: {sorted(known)})")

    return tuple(known[ticker] for ticker in tickers)


def _print_study(tables: dict[str, pd.DataFrame]) -> None:
    """확정 칸의 측정값을 화면에 보여 준다.

    **1차 판정은 여기서 내지 않는다** (2026-09-16 통합). 판정의 자리는 성적표 하나이며
    `_print_candidates` 가 그 표에서 후보 칸을 뽑는다.

    화면은 **저장한 표시용 프레임에서 발췌**한다 — 따로 가공하면 반올림 시점이 갈려
    화면에서 본 숫자를 CSV 에서 찾지 못한다.

    Args:
        tables: 저장한 표시용 프레임
    """
    measure = tables.get(FIELD_MEASURE)
    if measure is None or measure.empty:
        return

    print_dataframe(measure[HEADLINE_COLUMNS], logger, title="확정 칸 측정 — 20일 매수 → 말일 매도 (1배 롱 기준)")


def _print_candidates(outputs: TradingOutputs) -> None:
    """성적표에서 **맨몸 후보 칸만** 뽑아 화면에 보여 준다.

    **판정표를 따로 내지 않으므로 성적표가 그 자리다** (2026-09-16 통합).
    **확정 손절선 행을 보여 준다** — 기본 실행은 그 한 종뿐이라 거를 것이 없고,
    `--stop-grid` 로 돌린 실행에서만 이 필터가 일한다.

    **분모는 «판정한» 칸이다.** 지수와 인버스는 참고용이라 판정하지 않으므로,
    전체 행 수를 분모로 쓰면 통과 비율이 실제보다 작아 보인다.

    Args:
        outputs: 체결 산출물
    """
    table = outputs.performance
    whole = table[(table[DISPLAY_STOP_LEVEL].isin(FIXED_STOP_LABELS)) & (table[DISPLAY_PERIOD] == PERIOD_ALL)]
    judged = int((whole[DISPLAY_SCREEN] != SCREEN_NOT_JUDGED).sum())
    picked = whole[whole[DISPLAY_SCREEN] == SCREEN_CANDIDATE]

    if picked.empty:
        logger.debug(f"게이트를 넘은 칸이 없습니다 (판정한 칸 {judged})")
        return

    ordered = picked.sort_values(DISPLAY_WIN_RATE, ascending=False, kind="stable")
    print_dataframe(
        ordered[CANDIDATE_COLUMNS],
        logger,
        title=f"1차 후보 — 손절 {FIXED_STOP_DISPLAY}% · 전체 구간 {len(picked)}칸 (판정한 {judged}칸 · 판정 안 함 {len(whole) - judged}칸)",
    )


def _print_performance(outputs: TradingOutputs) -> None:
    """손절 격자 성적을 화면에 보여 준다.

    Args:
        outputs: 체결 산출물
    """
    overall = outputs.performance[outputs.performance[DISPLAY_PERIOD] == PERIOD_ALL]
    if overall.empty:
        return

    print_dataframe(overall[PERFORMANCE_COLUMNS], logger, title="확정 칸 성적 — 전체 구간 (시기 5행은 CSV 에)")


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
    picked = _known(args.ticker)

    # **지목이 없으면 두 계층의 기본값이 다르다** — 측정은 인버스를 참고용으로 함께 재고
    # 체결은 같은 베팅이 두 줄로 실리지 않게 뺀다
    study_datasets = picked if picked is not None else DATASETS
    trading_datasets = picked if picked is not None else DATASETS_TRADING

    study = run_study(study_datasets, repeats=args.repeats, seed=args.seed)
    tables = display_tables(study)
    stop_levels = MONTH_END_STOP_GRID if args.stop_grid else MONTH_END_STOP_DEFAULT
    trading = run_month_end_trading(trading_datasets, stop_levels=stop_levels, from_year=args.from_year)

    directory = create_run_directory(TRACK_NAME)
    counts = _save(study, tables, trading, directory)

    _print_study(tables)
    _print_candidates(trading)
    _print_performance(trading)
    print_dataframe(
        pd.DataFrame([{DISPLAY_FILE: name, DISPLAY_ROW_COUNT: rows} for name, rows in counts.items()]),
        logger,
        title=f"산출물 (저장 폴더: {directory})",
    )

    save_metadata(
        KEY_META_MONTH_END,
        {
            "directory": str(directory),
            "tickers": [dataset.ticker for dataset in study_datasets],
            "trading_tickers": [dataset.ticker for dataset in trading_datasets],
            # **스위치가 아니라 «무엇이 돌았는가»를 남긴다.** 켜졌다는 사실만으로는
            # 아홉 손절선 중 무엇이 돌았는지 알 수 없고, 지수만 고른 실행에서는
            # 그 불린이 오히려 거짓을 말한다 (실제로는 「손절불가」 한 줄만 돈다)
            KEY_CELLS: trading.summary[KEY_RULE][KEY_CELLS],
            KEY_STOP_LEVELS: trading.summary[KEY_RULE][KEY_STOP_LEVELS],
            KEY_FROM_YEAR: args.from_year,
            "repeats": args.repeats,
            "seed": args.seed,
            KEY_ROW_COUNTS: counts,
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
