#!/usr/bin/env python3
"""문서가 인용하지 않는 검증 산출물 폴더를 가려내고 지운다

`storage/results/` 는 실행할 때마다 폴더가 쌓이지만, **결과 문서가 근거로 인용하는 폴더는
지우면 안 된다** — 문서에 대조할 수 없는 숫자만 남는다. 어느 폴더가 인용됐는지의 판정은
`utils/result_citations.py` 하나가 소유하며, 품질 검증도 같은 함수를 쓴다.

기본 실행은 **목록만 보여준다.** 지우려면 `--delete` 를 붙인다.

**되돌릴 수 있는지가 git 추적 여부로 갈린다.** 추적 중이던 폴더는 이력에 남아 되살릴 수 있고,
미추적 폴더는 지우면 끝이다. 삭제는 파일 조작일 뿐이므로 이 스크립트가 둘 다 지우며,
**그 삭제를 이력에 기록하는 커밋은 사용자가 한다.**

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
import shutil
import subprocess
from pathlib import Path

from verify_lab.common_constants import BASE_DIR, DOCS_DIR, RESULTS_DIR
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.result_citations import cited_result_dirs, existing_result_dirs

logger = get_logger(__name__)

# 표시용 상태 레이블
DISPLAY_TRACKED = "추적중"
DISPLAY_UNTRACKED = "미추적"

# 우측 정렬 컬럼을 맨 뒤에 둔다. `TableLogger` 는 칸을 구분자 없이 이어 붙이므로,
# 우측 정렬 칸 뒤에 다른 칸이 오면 값이 서로 맞닿아 읽을 수 없다
TABLE_COLUMNS = [
    ("산출물 폴더", 44, Align.LEFT),
    ("git", 8, Align.LEFT),
    ("용량", 10, Align.RIGHT),
]


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        argparse.Namespace: 파싱된 인자
    """
    parser = argparse.ArgumentParser(description="문서가 인용하지 않는 검증 산출물 폴더를 가려내고 지웁니다")
    parser.add_argument(
        "--delete",
        action="store_true",
        help="정리 대상을 실제로 삭제합니다 (삭제를 이력에 남기는 커밋은 직접 하세요)",
    )

    return parser.parse_args()


def _tracked_dirs() -> set[str]:
    """git 이 추적 중인 산출물 폴더 이름을 모은다.

    읽기 전용 조회만 한다. 커밋 이력을 바꾸는 명령은 이 스크립트가 실행하지 않는다.

    Returns:
        set[str]: 추적 중인 폴더 이름

    Raises:
        ValueError: git 조회에 실패한 경우 (저장소가 아니거나 git 이 없다)
    """
    result = subprocess.run(
        ["git", "ls-files", str(RESULTS_DIR.relative_to(BASE_DIR))],
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
    )

    if result.returncode != 0:
        raise ValueError(f"git 조회에 실패했습니다. 이 폴더가 git 저장소인지 확인하세요 - {result.stderr.strip()}")

    return {line.split("/")[2] for line in result.stdout.splitlines() if line.count("/") >= 2}


def _directory_size(path: Path) -> int:
    """폴더가 차지하는 바이트 수를 잰다.

    Args:
        path: 대상 폴더

    Returns:
        int: 하위 파일 크기의 합
    """
    return sum(child.stat().st_size for child in path.rglob("*") if child.is_file())


def _format_size(num_bytes: int) -> str:
    """바이트 수를 MB 표기로 바꾼다.

    Args:
        num_bytes: 바이트 수

    Returns:
        str: `12.3MB` 형식
    """
    return f"{num_bytes / 1_000_000:.1f}MB"


def _print_group(names: list[str], tracked: set[str], title: str) -> int:
    """폴더 목록을 표로 출력하고 총 용량을 돌려준다.

    Args:
        names: 폴더 이름 목록 (정렬된 상태)
        tracked: 추적 중인 폴더 이름
        title: 표 제목

    Returns:
        int: 총 바이트 수
    """
    sizes = {name: _directory_size(RESULTS_DIR / name) for name in names}
    total = sum(sizes.values())

    table = TableLogger(TABLE_COLUMNS, logger)
    table.print_table(
        [
            [name, DISPLAY_TRACKED if name in tracked else DISPLAY_UNTRACKED, _format_size(sizes[name])]
            for name in names
        ],
        title=f"{title} — {len(names)}개 · {_format_size(total)}",
    )

    return total


def _delete_dirs(names: list[str]) -> None:
    """산출물 폴더를 지운다.

    Args:
        names: 지울 폴더 이름 목록
    """
    for name in names:
        shutil.rmtree(RESULTS_DIR / name)
        logger.debug(f"삭제: {name}")


@cli_exception_handler
def main() -> int:
    """인용 여부로 산출물 폴더를 가르고, 요청 시 미추적 정리 대상을 삭제한다.

    Returns:
        int: 종료 코드 (성공 0)
    """
    args = parse_args()

    cited = cited_result_dirs(DOCS_DIR)
    existing = existing_result_dirs(RESULTS_DIR)
    tracked = _tracked_dirs()

    keep = sorted(cited & existing)
    unreferenced = sorted(existing - cited)
    drop_untracked = [name for name in unreferenced if name not in tracked]
    drop_tracked = [name for name in unreferenced if name in tracked]

    _print_group(keep, tracked, "지킨다 — 문서가 근거로 인용한다")
    _print_group(unreferenced, tracked, "정리 대상 — 어느 문서도 인용하지 않는다")

    missing = sorted(cited - existing)
    if missing:
        logger.warning(f"문서가 인용했는데 없는 폴더가 있습니다: {missing}")

    if not args.delete:
        logger.warning("목록만 표시했습니다. 실제로 지우려면 --delete 를 붙이세요")

        return 0

    _delete_dirs(unreferenced)
    logger.warning(
        f"{len(unreferenced)}개를 삭제했습니다 — "
        f"추적중 {len(drop_tracked)}개(git 이력에서 되살릴 수 있음) · "
        f"미추적 {len(drop_untracked)}개(되돌릴 수 없음)"
    )

    if drop_tracked:
        logger.warning("추적 중이던 폴더의 삭제는 아직 커밋되지 않았습니다. 커밋해야 다른 PC 에 반영됩니다")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
