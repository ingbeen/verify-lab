#!/usr/bin/env python3
"""검증 #10 실행 CLI — 월 하순 진입 (20일 매수 → 말일 매도), 코스피·코스닥

사용자가 전해 들은 매매법을 잰다. **하나의 칸을 고르지 않고** 진입 달력일 11칸 ×
청산 상대 거래일 7칸을 전부 산출해 나란히 보고한다 — 20일만 튀는지 이웃도 같은지가
오버피팅 판정의 근거다.

확정 설계는 `docs/spec/월말_진입_설계.md` 가 SoT 다.
실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

from verify_lab.common_constants import RESULT_LAYER_STUDY
from verify_lab.measure.screening import SCREEN_NOT_JUDGED
from verify_lab.measure.statistics import DEFAULT_RANDOM_SEED, DEFAULT_REPEAT_COUNT
from verify_lab.report.constants import DISPLAY_SCREEN
from verify_lab.report.tables import print_dataframe
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.studies.month_end.constants import DATASETS, TRACK_NAME
from verify_lab.studies.month_end.runner import (
    base_cell_headline,
    candidates_headline,
    display_tables,
    run_study,
)
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_STUDY = "month_end_study"

# 화면에 낼 원 매매법 칸의 컬럼. 전 컬럼을 내면 가로로 넘쳐 읽을 수 없다
HEADLINE_COLUMNS = [
    "대상",
    "격자 칸",
    "표본",
    "평균(%)",
    "중앙값(%)",
    "오른 비율(%)",
    "내린 비율(%)",
    "기준선 내린 비율(%)",
    "내린 비율 차이(%p)",
    "내린 비율 우연확률",
    "판정가능",
]

# 화면에 낼 후보 칸의 컬럼
CANDIDATE_COLUMNS = [
    "대상",
    "격자 칸",
    "표본",
    "방향",
    "적중률(%)",
    "방향 기대값(%)",
    "합산 수익률(%)",
    "기준선(%)",
    "기준선 대비 차이(%p)",
]


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="월 하순 진입(20일 매수 → 말일 매도)의 통계적 우위를 격자로 측정합니다.")
    parser.add_argument(
        "--ticker",
        action="append",
        help="측정할 종목 또는 지수 코드. 여러 번 줄 수 있다 (기본값: 코스피·코스닥 8대상 전부). 인버스가 드는 것은 execution.csv 가 「아래」를 인버스 실물로 재기 때문이다",
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


def _selected_datasets(tickers: list[str] | None) -> tuple:
    """인자로 고른 대상만 남긴다.

    **검증은 인버스도 기본 대상이다.** `execution.csv` 가 「아래」 방향을 인버스 실물로 재고,
    그 표가 분배락 과대평가를 잡아내는 자리이기 때문이다 (`docs/spec/월말_진입_설계.md` §7.16).

    Args:
        tickers: 대상 코드 목록. `None` 이면 전부

    Returns:
        고른 대상 목록

    Raises:
        ValueError: 알 수 없는 코드를 지목한 경우
    """
    if not tickers:
        return DATASETS

    known = {dataset.ticker: dataset for dataset in DATASETS}
    unknown = [ticker for ticker in tickers if ticker not in known]
    if unknown:
        raise ValueError(f"알 수 없는 대상 코드입니다: {unknown} (가능한 값: {sorted(known)})")

    return tuple(known[ticker] for ticker in tickers)


@cli_exception_handler
def main() -> int:
    """검증을 실행하고 결과를 저장한 뒤 요약을 표시한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()
    datasets = _selected_datasets(args.ticker)

    outputs = run_study(datasets, repeats=args.repeats, seed=args.seed)
    tables = display_tables(outputs)

    directory = create_run_directory(TRACK_NAME, layer=RESULT_LAYER_STUDY)
    for name, table in tables.items():
        save_table(directory, f"{name}.csv", table)
    save_run_summary(directory, outputs.summary)

    # 화면은 **저장한 표시용 프레임에서 발췌**한다 — 따로 가공하면 반올림 시점이 갈려
    # 화면에서 본 숫자를 CSV 에서 찾지 못한다
    headline = base_cell_headline(tables["grid"])
    if not headline.empty:
        print_dataframe(headline[HEADLINE_COLUMNS], logger, title="원 매매법 칸 — 20일 매수 → 말일 매도")

    grid_candidates = tables["grid_candidates"]
    candidates = candidates_headline(grid_candidates)
    # **분모는 «판정한» 칸이다.** 지수는 살 수 없어 판정하지 않으므로(「판정 안 함」)
    # 전체 행 수를 분모로 쓰면 통과 비율이 실제보다 작아 보인다 — 월말 기본 실행에서
    # 격자 462칸 중 308칸이 지수다
    judged = int((grid_candidates[DISPLAY_SCREEN] != SCREEN_NOT_JUDGED).sum())
    unjudged = len(grid_candidates) - judged
    if candidates.empty:
        logger.debug(f"게이트를 넘은 격자 칸이 없습니다 (판정한 칸 {judged})")
    else:
        print_dataframe(
            candidates[CANDIDATE_COLUMNS],
            logger,
            title=(f"게이트를 넘은 격자 칸 — {len(candidates)}칸 " f"(판정한 {judged}칸 · 판정 안 함 {unjudged}칸)"),
        )

    logger.debug(f"산출물 저장 위치: {directory}")

    save_metadata(
        KEY_META_STUDY,
        {
            "directory": str(directory),
            "tickers": [dataset.ticker for dataset in datasets],
            "repeats": args.repeats,
            "seed": args.seed,
            "row_counts": outputs.summary["row_counts"],
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
