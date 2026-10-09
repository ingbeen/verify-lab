#!/usr/bin/env python3
"""반감기_사이클 판단용 차트 CLI — 측정을 돌려 HTML 한 장을 만들고 브라우저로 연다

달력 매달 분할의 사고파는 기간을 보고 고르기 위한 보기다(`docs/매매/반감기_사이클/설계.md` 결정 ㊾ · ㊿ · 53 · 54 · 55).
**차트는 고르지도 판정하지도 않는다** — 그리는 폭과 바닥 앞 개월은 상수라 인자가 없다.

**산출물 폴더(`storage/results/`)를 쓰지 않는다** — git 제외 폴더(`storage/charts/`)에 덮어쓴다. 그래서
`run_halving_cycle.py` 와 따로 있어도 서로의 산출물을 지우지 않는다.

**실행 이력(`meta.json`)을 남기지 않는다** — 결과가 아니라 결과를 다시 그린 보기이고, 만든 시각과 데이터 기간은
차트 머리에 찍힌다.

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
import os
import platform
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

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


def open_in_browser(path: Path) -> None:
    """차트를 연다. WSL 에서는 Windows 쪽 `.html` 연결 앱(보통 기본 브라우저)으로 연다.

    열지 못해도 실행을 멈추지 않는다 — WSL 에서 열기 명령이 오류를 내면 WARNING 으로 남긴다.
    열렸는지는 확인하지 않는다.

    Args:
        path: 차트 HTML 경로
    """
    # 커널 이름으로 WSL 을 가린다 (WSL1 `...-Microsoft` · WSL2 `...-microsoft-standard-WSL2`).
    # 같은 커널 위의 Docker Desktop 컨테이너도 WSL 로 잡히고, 이름을 바꾼 사용자 지정 커널은 못 잡는다
    if "microsoft" not in platform.release().lower():
        webbrowser.open(path.as_uri())
        return

    # `webbrowser` 는 리눅스 쪽 열기 수단(`gio` 등)을 부르는데, 리눅스 브라우저를 따로 깔지 않은 WSL 에는
    # html 을 열 앱이 없다. 그래서 리눅스 쪽 수단이 있든 없든 Windows 경로로 바꿔 Windows 쪽에서 연다 —
    # Windows 브라우저는 리눅스 경로(`/home/...`)를 못 읽는다
    try:
        windows_path = subprocess.run(
            ["wslpath", "-w", str(path)], capture_output=True, text=True, check=True
        ).stdout.strip()
        logger.debug(f"Windows 경로: {windows_path}")

        # 지정한 것을 따른다 — `BROWSER=true` 로 열지 않고 만드는 관용(`docs/COMMANDS.md`)이 WSL 에서도 맞아야 한다
        if os.environ.get("BROWSER"):
            webbrowser.open(path.as_uri())
            return

        # `cmd.exe /c start` 는 쓰지 않는다 — 현재 폴더가 UNC 라 경고 세 줄을 CP949 로 깨뜨려 찍는다.
        # 종료코드는 보지 않는다 — 브라우저를 연 호출도 1 을 낸다(실측 2026-10-05)
        subprocess.run(["explorer.exe", windows_path], check=False)
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        logger.warning(f"브라우저를 열지 못했습니다 ({error}) — 위에 찍힌 경로의 파일을 직접 여세요")


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

    # **경로를 먼저 찍는다** — 브라우저가 열리지 않아도 파일을 찾을 수 있게
    logger.debug(f"차트 저장: {path} ({path.stat().st_size / 1_000_000:.1f}MB)")
    open_in_browser(path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
