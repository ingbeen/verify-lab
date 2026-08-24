#!/usr/bin/env python3
"""검증 #5 — 원달러 ETF 등가성 실행 CLI

**261240 이 「환전 + 달러 예치」의 대체재인가**를 잰다. 매매 로직이 없는 순수 측정이며,
사양서 §16 이 그리드 백테스트보다 먼저 실행하라고 규정한 게이트다.

**이론값을 하나로 고르지 않는다.** 사양서 §16.1 과 §2.1 이 서로 다른 식을 가리키므로 둘 다 낸다.
**이상치도 포함·제외를 모두 낸다.** 2019-03-14 의 종가 이상치 이틀이 회귀를 뒤집는다.

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.studies.usdkrw_equivalence.constants import (
    DISPLAY_ALPHA_ANNUAL,
    DISPLAY_BETA,
    DISPLAY_CORRELATION,
    DISPLAY_DRIFT_SPREAD,
    DISPLAY_EFFECTIVE_COST,
    DISPLAY_EXPOSURE,
    DISPLAY_MODEL,
    DISPLAY_OUTLIER,
    DISPLAY_PASS,
    DISPLAY_PUBLISHED_TER,
    DISPLAY_R_SQUARED,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_SPOT,
    DISPLAY_TER_GAP,
    DISPLAY_TICKER,
    DISPLAY_TRACKING_ERROR,
    STUDY_NAME,
    TheoreticalModel,
)
from verify_lab.studies.usdkrw_equivalence.runner import EquivalenceOutputs, run_equivalence
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_EQUIVALENCE = "usdkrw_equivalence_study"

# 산출물 파일 이름
EQUIVALENCE_FILENAME = "equivalence.csv"
ANNUAL_DRIFT_FILENAME = "annual_drift.csv"
LEVERAGE_FILENAME = "leverage.csv"
PREMIUM_FILENAME = "premium.csv"
EFFECTIVE_COST_FILENAME = "effective_cost.csv"
DAILY_FILENAME = "daily.csv"

# 회귀 표의 컬럼 정의 (컬럼명, 폭, 정렬)
EQUIVALENCE_COLUMNS = [
    (DISPLAY_SPOT, 13, Align.LEFT),
    (DISPLAY_MODEL, 16, Align.LEFT),
    (DISPLAY_OUTLIER, 8, Align.LEFT),
    (DISPLAY_SAMPLE_COUNT, 8, Align.RIGHT),
    (DISPLAY_CORRELATION, 9, Align.RIGHT),
    (DISPLAY_BETA, 9, Align.RIGHT),
    (DISPLAY_ALPHA_ANNUAL, 15, Align.RIGHT),
    (DISPLAY_TRACKING_ERROR, 12, Align.RIGHT),
    (DISPLAY_DRIFT_SPREAD, 20, Align.RIGHT),
    (DISPLAY_PASS, 6, Align.LEFT),
]

# 레버리지 표의 컬럼 정의
LEVERAGE_COLUMNS = [
    (DISPLAY_OUTLIER, 8, Align.LEFT),
    (DISPLAY_SAMPLE_COUNT, 8, Align.RIGHT),
    (DISPLAY_BETA, 9, Align.RIGHT),
    (DISPLAY_ALPHA_ANNUAL, 15, Align.RIGHT),
    (DISPLAY_R_SQUARED, 9, Align.RIGHT),
    (DISPLAY_PASS, 6, Align.LEFT),
]

# 실효 총비용 표의 컬럼 정의
COST_COLUMNS = [
    (DISPLAY_TICKER, 9, Align.LEFT),
    (DISPLAY_EXPOSURE, 6, Align.RIGHT),
    (DISPLAY_SAMPLE_COUNT, 8, Align.RIGHT),
    (DISPLAY_BETA, 9, Align.RIGHT),
    (DISPLAY_EFFECTIVE_COST, 15, Align.RIGHT),
    (DISPLAY_PUBLISHED_TER, 15, Align.RIGHT),
    (DISPLAY_TER_GAP, 11, Align.RIGHT),
]

# 산출물 표의 컬럼 정의
OUTPUT_COLUMNS = [("파일", 22, Align.LEFT), ("행 수", 8, Align.RIGHT)]


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    **이상치 축은 인자가 아니다.** 포함·제외를 나란히 보는 것이 이 검증의 설계이며,
    하나만 골라 산출하면 그 선택 자체가 결론에 섞인다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="261240 이 「환전 + 달러 예치」의 대체재인지 측정합니다.")
    parser.add_argument(
        "--model",
        nargs="+",
        choices=[model.value for model in TheoreticalModel],
        default=None,
        help="산출할 이론값 모형 (기본값: 전부)",
    )
    return parser.parse_args()


def _print_equivalence(outputs: EquivalenceOutputs) -> None:
    """261240 대 이론값의 회귀 결과를 표로 보여준다.

    Args:
        outputs: 실행 산출물
    """
    rows = [
        [
            row[DISPLAY_SPOT],
            row[DISPLAY_MODEL],
            row[DISPLAY_OUTLIER],
            f"{row[DISPLAY_SAMPLE_COUNT]:,}",
            f"{row[DISPLAY_CORRELATION]:.4f}",
            f"{row[DISPLAY_BETA]:.4f}",
            f"{row[DISPLAY_ALPHA_ANNUAL]:+.2f}",
            f"{row[DISPLAY_TRACKING_ERROR]:.2f}",
            f"{row[DISPLAY_DRIFT_SPREAD]:.2f}",
            row[DISPLAY_PASS],
        ]
        for _, row in outputs.equivalence.iterrows()
    ]
    TableLogger(EQUIVALENCE_COLUMNS, logger).print_table(rows, title="261240 대 이론값 (사양서 §16.2)")


def _print_leverage(outputs: EquivalenceOutputs) -> None:
    """261250 대 261240 의 회귀 결과를 표로 보여준다.

    Args:
        outputs: 실행 산출물
    """
    rows = [
        [
            row[DISPLAY_OUTLIER],
            f"{row[DISPLAY_SAMPLE_COUNT]:,}",
            f"{row[DISPLAY_BETA]:.4f}",
            f"{row[DISPLAY_ALPHA_ANNUAL]:+.2f}",
            f"{row[DISPLAY_R_SQUARED]:.4f}",
            row[DISPLAY_PASS],
        ]
        for _, row in outputs.leverage.iterrows()
    ]
    TableLogger(LEVERAGE_COLUMNS, logger).print_table(rows, title="261250 대 261240 (사양서 §16.3)")


def _print_effective_cost(outputs: EquivalenceOutputs) -> None:
    """실효 총비용과 공시 총보수 대조를 표로 보여준다.

    Args:
        outputs: 실행 산출물
    """
    rows = [
        [
            row[DISPLAY_TICKER],
            f"{row[DISPLAY_EXPOSURE]}배",
            f"{row[DISPLAY_SAMPLE_COUNT]:,}",
            f"{row[DISPLAY_BETA]:.4f}",
            f"{row[DISPLAY_EFFECTIVE_COST]:+.2f}",
            f"{row[DISPLAY_PUBLISHED_TER]:.2f}",
            f"{row[DISPLAY_TER_GAP]:+.2f}",
        ]
        for _, row in outputs.effective_cost.iterrows()
    ]
    TableLogger(COST_COLUMNS, logger).print_table(rows, title="실효 총비용 (NAV 기준, 노출 배수 반영)")


@cli_exception_handler
def main() -> int:
    """검증을 실행하고 산출물을 저장한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()
    models = tuple(TheoreticalModel(value) for value in args.model) if args.model else tuple(TheoreticalModel)

    outputs = run_equivalence(models)

    _print_equivalence(outputs)
    _print_leverage(outputs)
    _print_effective_cost(outputs)

    directory = create_run_directory(STUDY_NAME)
    save_table(directory, EQUIVALENCE_FILENAME, outputs.equivalence)
    save_table(directory, ANNUAL_DRIFT_FILENAME, outputs.annual_drift)
    save_table(directory, LEVERAGE_FILENAME, outputs.leverage)
    save_table(directory, PREMIUM_FILENAME, outputs.premium)
    save_table(directory, EFFECTIVE_COST_FILENAME, outputs.effective_cost)
    save_table(directory, DAILY_FILENAME, outputs.daily)
    save_run_summary(directory, outputs.meta)

    counts = outputs.meta["row_counts"]
    TableLogger(OUTPUT_COLUMNS, logger).print_table(
        [
            [EQUIVALENCE_FILENAME, f"{counts['equivalence']:,}"],
            [ANNUAL_DRIFT_FILENAME, f"{counts['annual_drift']:,}"],
            [LEVERAGE_FILENAME, f"{counts['leverage']:,}"],
            [PREMIUM_FILENAME, f"{counts['premium']:,}"],
            [EFFECTIVE_COST_FILENAME, f"{counts['effective_cost']:,}"],
            [DAILY_FILENAME, f"{counts['daily']:,}"],
        ],
        title=f"산출물 (저장 폴더: {directory})",
    )

    save_metadata(
        KEY_META_EQUIVALENCE,
        {
            "models": [model.value for model in models],
            "output": str(directory),
            "row_counts": counts,
            "alignment": outputs.meta["alignment"],
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
