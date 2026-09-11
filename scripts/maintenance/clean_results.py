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

from verify_lab.common_constants import BASE_DIR, DOCS_DIR, RESULT_LAYERS, RESULTS_DIR
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.result_citations import cited_result_dirs, result_dir_paths

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

    **산출물이 사는 깊이가 둘이다.** 계층 폴더를 도입하기 전의 산출물은
    `storage/results/<폴더>/...` 에, 새 산출물은 `storage/results/<계층>/<폴더>/...` 에 있다.
    자리를 하나로 가정하면 **추적 판정이 전부 어긋나는데 예외는 나지 않고**, 「되돌릴 수 없음」
    경고가 거짓이 된다.

    **[중요] `-z` 를 반드시 붙인다.** `core.quotepath` 의 기본값이 참이라 그냥 부르면 git 이
    비ASCII 경로를 `"storage/results/\\353\\247\\244\\353\\247\\244/..."` 처럼 **escape 해서
    내보낸다.** 계층 폴더 이름이 한글이므로 그 상태로 쪼개면 「매매」와 대조가 실패해
    **계층 아래의 모든 폴더가 미추적으로 잡히고**, 그러면 위 문단이 막겠다고 한 거짓 경고가
    그대로 난다. `-z` 는 NUL 로 끊으면서 인용을 끄므로 설정에 기대지 않는다.

    Returns:
        set[str]: 추적 중인 폴더 이름

    Raises:
        ValueError: git 조회에 실패한 경우 (저장소가 아니거나 git 이 없다)
    """
    prefix = RESULTS_DIR.relative_to(BASE_DIR)
    result = subprocess.run(
        ["git", "ls-files", "-z", str(prefix)],
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
    )

    if result.returncode != 0:
        raise ValueError(f"git 조회에 실패했습니다. 이 폴더가 git 저장소인지 확인하세요 - {result.stderr.strip()}")

    depth = len(prefix.parts)
    tracked: set[str] = set()

    for entry in result.stdout.split("\0"):
        if not entry:
            continue
        parts = entry.split("/")[depth:]
        # 계층 폴더 아래면 한 칸 더 들어간다. 파일이 바로 있는 경우(meta.json)는 건너뛴다
        if parts and parts[0] in RESULT_LAYERS:
            parts = parts[1:]
        if len(parts) >= 2:
            tracked.add(parts[0])

    return tracked


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


def _print_group(names: list[str], paths: dict[str, list[Path]], tracked: set[str], title: str) -> int:
    """폴더 목록을 표로 출력하고 총 용량을 돌려준다.

    **경로를 이름으로 되조립하지 않는다.** 산출물이 계층 폴더 아래로 들어가면서 자리가 한 단계
    깊어졌고, `RESULTS_DIR / name` 은 존재하지 않는 경로가 된다. 그러면 `rglob` 이 빈 결과를 내
    **예외 없이 `0.0MB`** 로 표시된다.

    Args:
        names: 폴더 이름 목록 (정렬된 상태)
        paths: 폴더 이름 → 실재 경로들
        tracked: 추적 중인 폴더 이름
        title: 표 제목

    Returns:
        int: 총 바이트 수
    """
    sizes = {name: sum(_directory_size(path) for path in paths[name]) for name in names}
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


def _delete_dirs(names: list[str], paths: dict[str, list[Path]]) -> None:
    """산출물 폴더를 지운다.

    **한 이름이 여러 계층에 있으면 전부 지운다.** 인용은 이름 단위라 어느 쪽도 인용되지
    않았다는 판정이 둘에 같이 걸린다 — 하나만 지우면 남은 쪽이 다음 실행에서 또 후보로 올라온다.

    Args:
        names: 지울 폴더 이름 목록
        paths: 폴더 이름 → 실재 경로들
    """
    for name in names:
        for path in paths[name]:
            shutil.rmtree(path)
            logger.debug(f"삭제: {path}")


@cli_exception_handler
def main() -> int:
    """인용 여부로 산출물 폴더를 가르고, 요청 시 미추적 정리 대상을 삭제한다.

    Returns:
        int: 종료 코드 (성공 0)
    """
    args = parse_args()

    cited = cited_result_dirs(DOCS_DIR)
    paths = result_dir_paths(RESULTS_DIR)
    existing = set(paths)
    tracked = _tracked_dirs()

    keep = sorted(cited & existing)
    unreferenced = sorted(existing - cited)
    drop_untracked = [name for name in unreferenced if name not in tracked]
    drop_tracked = [name for name in unreferenced if name in tracked]

    _print_group(keep, paths, tracked, "지킨다 — 문서가 근거로 인용한다")
    _print_group(unreferenced, paths, tracked, "정리 대상 — 어느 문서도 인용하지 않는다")

    missing = sorted(cited - existing)
    if missing:
        logger.warning(f"문서가 인용했는데 없는 폴더가 있습니다: {missing}")

    if not args.delete:
        logger.warning("목록만 표시했습니다. 실제로 지우려면 --delete 를 붙이세요")

        return 0

    _delete_dirs(unreferenced, paths)
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
