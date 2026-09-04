#!/usr/bin/env python3
"""검증 #8 실행 CLI — 레버리지·인버스 상품의 괴리 측정

배수 상품이 1배 상품 대비 보유 기간별로 얼마나 벌어지는지를 재고, 괴리를
**경로 효과(음의 복리)** 와 **상품 비용(보수·스왑·추적오차)** 으로 나눈다.

**보유 기간과 임계값은 인자가 아니다.** 확정된 격자를 전부 산출해 나란히 보고하는 것이
이 검증의 설계이며, 값을 골라 넣는 노브로 쓰면 과최적화가 된다.

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

from verify_lab.report.tables import print_dataframe
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.studies.leverage_tracking.constants import (
    BREAKDOWN_FILENAME,
    DISTRIBUTION_FILENAME,
    DIVERGENCE_FILENAME,
    FULL_PERIOD_FILENAME,
    HORIZONS,
    PAIRS,
    STUDY_NAME,
    WINDOWS_FILENAME_TEMPLATE,
)
from verify_lab.studies.leverage_tracking.runner import headline, run_study
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_LEVERAGE_TRACKING = "leverage_tracking_study"

# `--index` 로 고를 수 있는 값. 목록의 SoT 는 `studies/leverage_tracking/constants.py` 의 PAIRS 다
INDEX_CHOICES = sorted({pair.index_name for pair in PAIRS})


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="레버리지·인버스 상품이 1배 대비 얼마나 벌어지는지를 재고 괴리를 두 몫으로 나눕니다.")
    parser.add_argument(
        "--index",
        choices=INDEX_CHOICES,
        help=f"특정 지수만 실행한다 (기본값: 전부). 고를 수 있는 값: {', '.join(INDEX_CHOICES)}",
    )
    return parser.parse_args()


@cli_exception_handler
def main() -> int:
    """검증을 실행하고 산출물을 저장한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()

    pairs = tuple(pair for pair in PAIRS if args.index is None or pair.index_name == args.index)
    if not pairs:
        raise ValueError(f"실행할 짝이 없습니다 - 지수: {args.index}")

    outputs = run_study(pairs=pairs)

    print_dataframe(headline(outputs), logger, title="구간별 괴리 분해 (판정 가능한 칸)")

    directory = create_run_directory(STUDY_NAME)
    save_table(directory, DIVERGENCE_FILENAME, outputs.divergence)
    save_table(directory, BREAKDOWN_FILENAME, outputs.breakdown)
    save_table(directory, DISTRIBUTION_FILENAME, outputs.distribution)
    save_table(directory, FULL_PERIOD_FILENAME, outputs.full_period)

    for ticker, window in outputs.windows.items():
        save_table(directory, WINDOWS_FILENAME_TEMPLATE.format(ticker=ticker), window)

    # 산출물만 보고 어떤 설정의 결과인지 재구성할 수 있어야 한다
    run_info = {
        "index": args.index,
        "pair_count": outputs.pair_count,
        "horizons": list(HORIZONS),
        "pairs": [
            {
                "index": pair.index_name,
                "base": pair.base_ticker,
                "target": pair.target_ticker,
                "multiple": pair.multiple,
            }
            for pair in pairs
        ],
        "divergence_rows": len(outputs.divergence),
        "breakdown_rows": len(outputs.breakdown),
        "distribution_rows": len(outputs.distribution),
        "window_rows": int(sum(len(window) for window in outputs.windows.values())),
    }
    save_run_summary(directory, run_info)

    logger.debug(f"산출물 저장 완료: {directory}")

    save_metadata(KEY_META_LEVERAGE_TRACKING, {"directory": str(directory), **run_info})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
