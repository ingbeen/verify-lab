#!/usr/bin/env python3
"""반감기_사이클 실행 CLI — 측정과 체결을 한 번에 돈다

**1단계 측정 격자를 잰다** — 비트코인 반감기 뒤 몇 개월째에 진입해 몇 개월 드는 격자(진입 개월 × 보유 개월)다.
기준선은 첫 반감기부터 매일 진입해 같은 기간 든 성적이다. 한 번 돌리면 측정 표와 체결 산출물이 **한 폴더에**
함께 나오며, 어느 등급 폴더에 쌓일지는 `verify_lab/tracks.py` 의 레지스트리가 정한다.

**2단계(보조지표 · 온체인)도 같은 실행에서 잰다** — 책이 문턱을 적은 신호 열넷이 문턱을 돌파한 다음날 종가에 들어가
같은 보유 · 같은 기준선으로 잰다. 1단계 진입일마다 진입 전날까지의 지표 값도 낸다. **측정만 하고 체결하지 않는다.**

**3단계 체결은 진입 시점 × 청산 시점의 일시 격자를 무손절로, 확정 규칙(달력 매달 분할)을 무손절 · 저점 이탈로 ·
「위」 한 방향으로 낸다** — 일시 격자는 둘 다 가장 최근 반감기 뒤 몇 개월이고, 청산 시점이 진입보다 같거나 앞이면 다음
반감기 뒤다. 일시 격자의 칸을 고르지 않는다(비교용). 확정 규칙은 끝난 포지션 하나가 체결 한 건이다. 진입가 % 손절선은
두지 않는다. 하드포크 몫은 거래내역 끝 칸에 따로 싣는다.

**3단계 격자 중 같은 사이클에 파는 칸은 같은 보유의 기준선과 나란히 측정 표로도 낸다**(격자기준선) — 판정에 쓰지 않는다.

**3단계 달력 + MVRV 혼합 분할 격자도 같은 실행에서 잰다** — 반감기 뒤 세 번 사고 다음 반감기 뒤 세 번 파는 포지션을
조합 전부로 내고(분할회차 · 분할포지션 · 분할조합), 측정 표라 1차 판정 · 손절이 없다. 조합을 고르지 않는다.

**3단계 달력 매달 분할도 같은 실행에서 잰다** — 반감기 뒤 매달 사고 다음 반감기 뒤 매달 파는 포지션(달력분할회차 ·
달력분할포지션)과, 포지션마다 무손절과 저점 이탈 손절을 하드포크 몫과 나란히 둔 손절 표(달력분할손절)다. 이 셋은
측정 표라 1차 판정이 없고, 같은 포지션의 1차 판정은 성적표의 확정 규칙 행이 받는다.

**대상은 Bitstamp BTC/USD 하나다.** 거래량이 0 인 날의 종가는 Coin Metrics 기준가로 바꿔 재고(원시 파일은
그대로), 두 소스의 차이가 허용폭을 넘은 날과 바꾼 날을 표로 함께 낸다.

[중요] **칸마다 표본이 많아야 사이클 수라 칸당 하한(`measure/constants.MIN_SAMPLE_PER_CELL`)에 못 미친다.** 「판정가능」이
전부 「아니오」이고 1단계 칸에는 우연확률도 붙지 않는다 — **결론의 일부이지 버그가 아니다.** 격자의 칸은 같은 사이클을 나눈 것이라
서로 독립이 아니다. 2단계 신호는 돌파가 한 바닥에 몰리는 것이 많아 표본이 하한을 넘어도 서로 독립이 아니다 — 사이클 수와
비중첩 표본을 함께 본다.

**맨몸 성적이다** — 수수료·슬리피지·세금을 넣지 않는다 (루트 `CLAUDE.md` 2026-09-06 확정).

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
from pathlib import Path

import pandas as pd

from verify_lab.execution.constants import (
    DISPLAY_RETURN,
    DISPLAY_STOP_LEVEL,
    DISPLAY_TICKER,
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
    BASELINE_PREFIX,
    DATASETS,
    DISPLAY_CALENDAR_YEAR,
    DISPLAY_CYCLE_COUNT,
    DISPLAY_ENTRY_MONTHS,
    DISPLAY_HALVING_POSITION,
    DISPLAY_HOLD_MONTHS,
    DISPLAY_INDICATOR_SIGNAL,
    DISPLAY_TRADE_METHOD,
    ENTRY_MONTHS,
    EXIT_MONTHS,
    FIELD_CALENDAR_YEARS,
    FIELD_INDICATOR_STATISTICS,
    FIELD_STATISTICS,
    HOLD_MONTHS,
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

# 매매 방식 · 손절선별 후보 수 표의 컬럼
# **「후보」 한 낱말로 두지 않는다** — 1차 판정 값과 같은 글자라 판정을 CLI 에서 다시 쓰는 것으로 읽힌다
DISPLAY_CELL_COUNT = "전체 칸"
DISPLAY_CANDIDATE_COUNT = "후보 칸"


def _grid_text(values: tuple[int, ...]) -> str:
    """격자 개월 값을 설명에 싣는 글자로 바꾼다.

    **범위로 줄이는 것은 간격이 고를 때뿐이다** — 3 · 6 · 12 를 「3 ~ 12개월」로 적으면 재지 않는 4 · 5 · 7개월이
    있는 것처럼 읽히고 칸 수와도 어긋난다.

    Args:
        values: 격자 값 (오름차순)

    Returns:
        `처음 ~ 끝개월(간격개월 간격)` — 셋 이상이고 간격이 고를 때. 아니면 값을 전부 `·` 로 잇는다
    """
    steps = {later - earlier for earlier, later in zip(values, values[1:], strict=False)}
    if len(values) > 2 and len(steps) == 1:
        return f"{values[0]} ~ {values[-1]}개월({steps.pop()}개월 간격)"

    return " · ".join(str(value) for value in values) + "개월"


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    # **격자 값을 글자로 박지 않는다** — 상수가 바뀌면 `--help` 가 거짓이 된다
    parser = argparse.ArgumentParser(
        description=(
            f"반감기_사이클 — 비트코인 반감기 뒤 {_grid_text(ENTRY_MONTHS)} 진입 × 보유 {_grid_text(HOLD_MONTHS)} "
            f"({len(ENTRY_MONTHS) * len(HOLD_MONTHS)}칸)을 Bitstamp BTC/USD 로 재고, 진입 × 청산 시점 "
            f"({len(ENTRY_MONTHS) * len(EXIT_MONTHS)}칸)의 일시 격자를 무손절로, 확정 규칙(달력 매달 분할)을 무손절 · 저점 이탈로 "
            "체결한 성적표와 두 소스 대조 표를 함께 냅니다. 책이 문턱을 적은 보조지표 · 온체인 신호 열넷도 같은 보유와 기준선으로 잽니다(체결하지 않습니다). "
            "달력 + MVRV 혼합 분할매수 · 매도 격자도 측정 표로 냅니다(1차 판정 · 손절 없음). "
            "달력 매달 분할도 측정 표로 내고, 포지션마다 무손절과 저점 이탈 손절을 나란히 잽니다(측정 표에는 1차 판정이 없고, "
            "같은 포지션은 성적표의 확정 규칙 행으로 판정받습니다). "
            "같은 사이클에 파는 칸은 같은 보유(청산 − 진입)의 기준선과 나란히 측정 표로도 냅니다(판정에 쓰지 않습니다)."
        )
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=DEFAULT_REPEAT_COUNT,
        help=f"무작위 뽑기 대조 반복 수 (기본값: {DEFAULT_REPEAT_COUNT}). 표본이 하한 이상인 칸에만 검정이 붙는다 — " "1단계 격자는 전 칸이 하한 미만이다",
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


def _print_indicator_statistics(tables: dict[str, pd.DataFrame]) -> None:
    """2단계 신호마다의 핵심 값을 기준선과 나란히 화면에 띄운다. 전체 값은 지표통계 표에 있다.

    Args:
        tables: 저장할 표시용 프레임
    """
    columns = [
        DISPLAY_INDICATOR_SIGNAL,
        DISPLAY_HOLD_MONTHS,
        DISPLAY_SIGNAL_COUNT,
        DISPLAY_SAMPLE_COUNT,
        DISPLAY_CYCLE_COUNT,
        DISPLAY_MEAN,
        DISPLAY_MEDIAN,
        DISPLAY_UP_RATE,
        f"{BASELINE_PREFIX}{DISPLAY_UP_RATE}",
        DISPLAY_DOWN_RATE,
    ]
    print_dataframe(
        tables[FIELD_INDICATOR_STATISTICS][columns],
        logger,
        title="2단계 지표 신호 — 돌파 다음날 종가 진입, 1배 롱 기준 (측정만 — 체결하지 않는다)",
    )


def _print_candidate_counts(trading: TradingOutputs) -> None:
    """종목 · 매매 방식 · 손절선마다 1차 판정이 「후보」인 칸의 수를 화면에 띄운다.

    **칸 목록을 띄우지 않는다** — 일시 격자가 수백 칸이라 화면에서 읽히지 않고, 전체는 성적표가 갖는다.
    **매매 방식으로 가른다** — 일시 격자와 확정 규칙의 무손절 행이 한 줄에 합쳐지면 확정 규칙의 판정이 보이지 않는다.
    **후보는 자격이지 발견이 아니다.** 게이트를 넘었다는 뜻일 뿐이며, 표본이 하한에 못 미치고 칸끼리
    독립이 아니라는 사실은 그대로다. **종목으로도 묶는다** — 손절선으로만 묶으면 대상이 둘일 때 두 격자의 칸과
    판정하지 않는 대상의 칸이 한 줄에 합쳐진다.

    Args:
        trading: 체결 산출물
    """
    frame = trading.performance
    whole = frame[frame[DISPLAY_PERIOD] == PERIOD_ALL]
    counts = (
        whole.assign(**{DISPLAY_CANDIDATE_COUNT: whole[DISPLAY_SCREEN] == SCREEN_CANDIDATE})
        .groupby([DISPLAY_TICKER, DISPLAY_TRADE_METHOD, DISPLAY_STOP_LEVEL], sort=False)
        .agg(
            **{DISPLAY_CELL_COUNT: (DISPLAY_SCREEN, "size"), DISPLAY_CANDIDATE_COUNT: (DISPLAY_CANDIDATE_COUNT, "sum")}
        )
        .reset_index()
    )
    print_dataframe(
        counts,
        logger,
        title="1차 판정 「후보」 칸 수 — 종목 · 매매 방식 · 손절선마다 (「위」 · 전체 구간). 칸 전체는 성적표에 있다",
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
    _print_indicator_statistics(tables)
    _print_candidate_counts(trading)
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
