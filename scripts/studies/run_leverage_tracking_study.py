#!/usr/bin/env python3
"""검증 #8 실행 CLI — 레버리지·인버스 상품의 괴리 측정

배수 상품이 1배 상품 대비 보유 기간별로 얼마나 벌어지는지를 재고, 괴리를
**경로 효과(음의 복리)** 와 **상품 비용(보수·스왑·추적오차)** 으로 나눈다.

**보유 기간과 임계값은 인자가 아니다.** 확정된 격자를 전부 산출해 나란히 보고하는 것이
이 검증의 설계이며, 값을 골라 넣는 노브로 쓰면 과최적화가 된다.

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

from verify_lab.common_constants import RESULT_LAYER_STUDY
from verify_lab.report.tables import print_dataframe
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.studies.leverage_tracking.constants import (
    OUTPUT_FILES,
    PAIRS,
    TRACK_NAME,
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

    # **거르는 것은 runner 가 한다.** CLI 가 거르고 runner 에는 이름만 넘기면,
    # 둘이 어긋났을 때 요약이 「이 지수만 쟀다」고 적으면서 전부 잰 결과를 담는다
    outputs = run_study(index_filter=args.index)

    print_dataframe(headline(outputs), logger, title="구간별 괴리 분해 (판정 가능한 칸)")

    directory = create_run_directory(TRACK_NAME, layer=RESULT_LAYER_STUDY)

    # **저장할 파일 목록의 SoT 는 `OUTPUT_FILES` 하나다.** 여기 나열하면 요약의 행 수와
    # 실제 파일이 갈릴 수 있다 — 실제로 `full_period` 는 저장은 되는데 **요약에서 통째로
    # 빠져** 있었다
    for field, filename in OUTPUT_FILES.items():
        save_table(directory, filename, getattr(outputs, field))

    for ticker, window in outputs.windows.items():
        save_table(directory, WINDOWS_FILENAME_TEMPLATE.format(ticker=ticker), window)

    # 산출물만 보고 어떤 설정의 결과인지 재구성할 수 있어야 한다.
    # **조립은 runner 가 한다** (`scripts/CLAUDE.md` 「CLI 에 도메인 로직 금지」)
    save_run_summary(directory, outputs.summary)

    logger.debug(f"산출물 저장 완료: {directory}")

    save_metadata(KEY_META_LEVERAGE_TRACKING, {"directory": str(directory), **outputs.summary})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
