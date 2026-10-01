#!/usr/bin/env python3
"""반감기_사이클 판단용 차트 CLI — 측정을 돌려 HTML 한 장을 만들고 브라우저로 연다

달력 매달 분할의 사고파는 기간을 보고 고르기 위한 보기다(`docs/검증/반감기_사이클/설계.md` 결정 ㊾ · ㊿ · 53).
**차트는 고르지도 판정하지도 않는다** — 그리는 폭과 바닥 앞 개월은 상수라 인자가 없다.

**산출물 폴더(`storage/results/`)를 쓰지 않는다** — git 제외 폴더(`storage/charts/`)에 덮어쓴다. 그래서
`run_halving_cycle.py` 와 따로 있어도 서로의 산출물을 지우지 않는다.

**실행 이력(`meta.json`)을 남기지 않는다** — 결과가 아니라 결과를 다시 그린 보기이고, 만든 시각과 데이터 기간은
차트 머리에 찍힌다.

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
import webbrowser
from datetime import datetime

from plotly.offline import get_plotlyjs

from verify_lab.common_constants import KST
from verify_lab.studies.halving_cycle.chart import build_chart_html, chart_path
from verify_lab.studies.halving_cycle.constants import DATASETS
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다 — 인자는 없고 `--help` 만 있다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(
        description=(
            "반감기_사이클 판단용 차트 — 반감기 기준 · 바닥 기준 사이클 겹치기와 전 기간 시간축에 달력 매달 분할의 "
            "매수 · 매도 회차를 찍고 사이클별 숫자표를 붙여 HTML 한 장으로 만들어 브라우저로 엽니다. 측정을 다시 돌리고, "
            "산출물 폴더는 건드리지 않습니다."
        )
    )

    return parser.parse_args()


@cli_exception_handler
def main() -> int:
    """차트를 만들어 저장하고 연다.

    Returns:
        종료 코드 (성공 0)
    """
    parse_args()

    html = build_chart_html(DATASETS, plotly_js=get_plotlyjs(), created_at=datetime.now(KST))
    path = chart_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")

    # **경로를 먼저 찍는다** — 브라우저를 못 여는 환경(WSL 등)에서도 파일을 찾을 수 있게
    logger.debug(f"차트 저장: {path} ({path.stat().st_size / 1_000_000:.1f}MB)")
    webbrowser.open(path.as_uri())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
