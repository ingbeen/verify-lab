"""문서가 근거로 인용한 산출물 폴더를 찾는다.

결과 문서는 수치의 근거로 `storage/results/` 의 실행 폴더를 인용한다. 그 폴더가 사라지면
문서는 대조할 수 없는 숫자만 남기므로, **어느 폴더가 인용됐는지**를 한 곳에서 판정한다.

두 방향으로 쓴다.

- `missing_citations()` — 인용됐는데 없는 폴더. 품질 검증이 실패로 잡는다
- `unreferenced_dirs()` — 있는데 인용되지 않은 폴더. 정리 도구가 삭제 후보로 뽑는다

**두 판정이 갈라지면 정리 도구가 「지워도 된다」고 한 폴더를 검증이 요구하는 상태가 되므로
인용의 정의는 이 모듈 하나가 소유한다.**
"""

import re
from pathlib import Path
from typing import Final

# 산출물 폴더 이름 모양: <YYYYMMDD>_<HHMMSS>_<검증명>.
# **`storage/results/` 접두어를 요구하지 않는다** — `docs/spec/` 은 폴더 이름만 적는 자리가 있어
# 접두어를 요구하면 그 인용을 통째로 놓친다. 넓게 잡는 쪽이 안전하다: 잘못 잡아도
# 폴더를 더 지키게 될 뿐이지만, 놓치면 근거가 지워진다
RESULT_DIR_NAME: Final = re.compile(r"\b(\d{8}_\d{6}_[a-z][a-z_]*)\b")

# 인용을 세지 않는 문서 폴더. 이유가 서로 다르므로 한 줄씩 적는다
EXCLUDED_PARTS: Final = (
    "plans",  # 임시 산출물이라 주기적으로 삭제된다. 여기 적힌 폴더명은 계약이 아니다
    "context",  # 사용자 소유 문서이고, 적힌 산출물 경로는 이전 프로젝트의 것이다
)

# 묘비 낱말. 인용과 **같은 줄**에 있으면 「일부러 없앤 것」이라 실재를 요구하지 않는다.
# `tests/test_research_docs.py` 와 **같은 어휘**를 쓴다 — 두 벌이 되면 조용히 갈라진다
TOMBSTONE_WORDS: Final = ("없음", "삭제", "제거")


def _is_scannable(path: Path, root: Path) -> bool:
    """인용을 셀 마크다운 파일인지 판정한다.

    제외 판정은 **`root` 아래의 상대경로**로만 한다. 절대경로로 보면 저장소 밖의 상위 폴더
    이름이 우연히 제외 낱말과 같을 때 조용히 전부 걸러진다.

    Args:
        path: 검사할 경로
        root: 판정 기준이 되는 시작 경로

    Returns:
        bool: 제외 경로에 걸리지 않는 마크다운 파일이면 True
    """
    if path.suffix != ".md":
        return False

    return not any(part in EXCLUDED_PARTS for part in path.relative_to(root).parts)


def cited_result_dirs(root: Path) -> set[str]:
    """문서가 살아있는 근거로 인용한 산출물 폴더 이름을 모은다.

    **묘비 낱말이 같은 줄에 있으면 세지 않는다.** 산출물이 사라졌다는 사실 자체를 적은 문장까지
    실재를 요구하면, 없어진 것을 문서에 남길 방법이 없어진다.

    한 폴더가 여러 줄에 나오면 **묘비가 없는 줄이 하나라도 있을 때 인용으로 센다.**
    실재를 요구하는 쪽이 안전한 판정이다.

    Args:
        root: 문서를 찾을 시작 경로

    Returns:
        set[str]: 인용된 산출물 폴더 이름
    """
    cited: set[str] = set()

    for path in sorted(root.rglob("*.md")):
        if not _is_scannable(path, root):
            continue

        for line in path.read_text(encoding="utf-8").splitlines():
            if any(word in line for word in TOMBSTONE_WORDS):
                continue
            cited.update(RESULT_DIR_NAME.findall(line))

    return cited


def existing_result_dirs(results_dir: Path) -> set[str]:
    """디스크에 있는 산출물 폴더 이름을 모은다.

    Args:
        results_dir: 산출물 폴더의 부모 경로

    Returns:
        set[str]: 실재하는 산출물 폴더 이름. 부모 경로가 없으면 빈 집합
    """
    if not results_dir.is_dir():
        return set()

    return {child.name for child in results_dir.iterdir() if child.is_dir()}


def missing_citations(root: Path, results_dir: Path) -> list[str]:
    """문서가 인용했는데 실재하지 않는 산출물 폴더를 찾는다.

    Args:
        root: 문서를 찾을 시작 경로
        results_dir: 산출물 폴더의 부모 경로

    Returns:
        list[str]: 이름 오름차순. 비어 있으면 모든 인용이 실재한다
    """
    return sorted(cited_result_dirs(root) - existing_result_dirs(results_dir))


def unreferenced_dirs(root: Path, results_dir: Path) -> list[str]:
    """실재하지만 어느 문서도 인용하지 않는 산출물 폴더를 찾는다.

    정리 후보이지 삭제 대상이 아니다. **지우기 전에 문서의 조준이 최신인지 먼저 확인한다** —
    아직 폴더를 겨누지 않은 문서가 있으면 그 근거가 여기 섞인다.

    Args:
        root: 문서를 찾을 시작 경로
        results_dir: 산출물 폴더의 부모 경로

    Returns:
        list[str]: 이름 오름차순
    """
    return sorted(existing_result_dirs(results_dir) - cited_result_dirs(root))
