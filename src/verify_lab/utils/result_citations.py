"""문서가 근거로 인용한 산출물 폴더를 찾는다.

결과 문서는 수치의 근거로 `storage/results/` 의 실행 폴더를 인용한다. 그 폴더가 사라지면
문서는 대조할 수 없는 숫자만 남기므로, **어느 폴더가 인용됐는지**를 한 곳에서 판정한다.

두 방향으로 쓴다.

- `missing_citations()` — 인용됐는데 없는 폴더. 품질 검증이 실패로 잡는다
- `unreferenced_dirs()` — 있는데 인용되지 않은 폴더. 정리 도구가 삭제 후보로 뽑는다

**두 판정이 갈라지면 정리 도구가 「지워도 된다」고 한 폴더를 검증이 요구하는 상태가 되므로
인용의 정의는 이 모듈 하나가 소유한다.** 같은 이유로 **두 쪽이 같은 루트를 넘겨야 한다** —
루트 `CLAUDE.md` 가 실제로 산출물을 인용하므로 `docs/` 만 훑으면 그 인용을 놓치고,
그때 검증은 통과하는데 정리 도구가 근거물을 삭제 후보로 낸다. 같은 이유로 **「그 폴더가 어디 있는가」도 여기서 낸다**
(`result_dir_paths()`) — 정리 도구가 이름만 받아 경로를 되조립하면 두 곳의 가정이 갈라진다.

**산출물이 사는 자리는 둘이고 그것이 의도다.** 계층 폴더(`검증`·`매매`·`실측`)를 도입하기 전의
산출물은 루트 직하에 남아 있다 — 살아있는 문서 여럿이 그 이름을 인용하고 있어 옮기면 전부
깨진다. 그래서 탐색은 **두 자리를 모두** 본다.
"""

import re
from pathlib import Path
from typing import Final

from verify_lab.common_constants import RESULT_LAYERS

# 매매법 이름(slug)이 가질 수 있는 모양. **폴더를 만드는 쪽과 인용을 찾는 쪽이 같은 정의를
# 봐야 한다** — 갈라지면 이 스캐너가 영원히 못 찾는 이름으로 폴더가 생기고, 그 산출물은
# 문서가 인용해도 「없는 것」으로 취급돼 정리 후보로 올라간다. 예외는 나지 않는다.
# `report/writer.py` 의 `create_run_directory` 가 이 패턴으로 입력을 거른다
TRACK_NAME_PATTERN: Final = r"[a-z][a-z_]*"

# 산출물 폴더 이름 모양: <YYYYMMDD>_<HHMMSS>_<매매법>.
# **`storage/results/` 접두어를 요구하지 않는다** — `docs/spec/` 은 폴더 이름만 적는 자리가 있어
# 접두어를 요구하면 그 인용을 통째로 놓친다. 넓게 잡는 쪽이 안전하다: 잘못 잡아도
# 폴더를 더 지키게 될 뿐이지만, 놓치면 근거가 지워진다
#
# **계층 폴더가 한글이어도 이 패턴은 그대로 쓴다.** 한글은 상위 폴더 이름에만 들어가고 산출물
# 폴더 이름 자체는 계속 ASCII 다. `storage/results/매매/20260911_120000_reverse` 에서도
# 앞의 `/` 가 경계를 주므로 그대로 잡힌다
RESULT_DIR_NAME: Final = re.compile(rf"\b(\d{{8}}_\d{{6}}_{TRACK_NAME_PATTERN})\b")

# 인용을 세지 않는 폴더. 이유가 서로 다르므로 한 줄씩 적는다.
#
# **「이 저장소가 쓴 문서」만 인용으로 센다.** 스캔 루트가 저장소 전체이므로 내려받은 것·
# 생성된 것·읽기 전용으로 들여온 것이 함께 걸린다 — 실측에서 마크다운 65개 중 **20개가
# `.venv` 안**이었다. 그것까지 세면 **의존성을 바꾸는 것만으로 품질 검증 결과가 달라지고**,
# 우연히 `<8자리>_<6자리>_<영소문자>` 모양을 가진 남의 문서 한 줄이 **고칠 수 없는 실패**를 만든다
EXCLUDED_PARTS: Final = (
    "plans",  # 임시 산출물이라 주기적으로 삭제된다. 여기 적힌 폴더명은 계약이 아니다
    "context",  # 사용자 소유 문서이고, 적힌 산출물 경로는 이전 프로젝트의 것이다
    ".venv",  # 내려받은 의존성. 저장소가 쓴 문서가 아니고 `poetry install` 로 내용이 바뀐다
    ".git",  # 이력 저장소
    ".pytest_cache",  # 실행할 때마다 생긴다
    ".ruff_cache",  # 같음
    "reference",  # 읽기 전용으로 들여온 이전 프로젝트의 원본 (`.claude/rules/reference.md`)
    "claude-config",  # 전역 설정의 사본. 이 저장소의 산출물을 가리키지 않는다
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


def result_dir_paths(results_dir: Path) -> dict[str, list[Path]]:
    """디스크에 있는 산출물 폴더를 **이름 → 경로 목록**으로 모은다.

    두 자리를 모두 훑는다 — 루트 직하(계층 폴더 도입 전의 산출물)와 계층 폴더 아래(새 산출물).
    **계층 폴더 자체는 산출물이 아니다.** 세면 정리 도구가 그것을 「인용되지 않은 폴더」로 뽑아
    통째로 지운다.

    **경로를 함께 내는 이유**: 인용의 식별자는 폴더 이름 하나지만 지우거나 용량을 재려면 경로가
    필요하다. 쓰는 쪽이 이름으로 경로를 되조립하면 자리가 한 단계 깊어진 것을 모른 채
    **존재하지 않는 경로에 `rglob` 을 돌려 예외 없이 0 바이트**를 내게 된다.

    **한 이름이 여러 경로를 가질 수 있고 그것은 오류가 아니다.** 측정과 매매가 같은 slug 를 쓰는
    것이 이 저장소의 규약이므로(목표 1), 같은 초에 두 계층을 돌리면 `검증/<시각>_reverse` 와
    `매매/<시각>_reverse` 가 함께 생긴다. 그래서 목록으로 돌려준다 — 여기서 예외를 던지면
    **인용 판정 전체가 멈춰 품질 검증과 정리 도구가 동시에 죽는다.**

    Args:
        results_dir: 산출물 폴더의 부모 경로

    Returns:
        dict[str, list[Path]]: 폴더 이름 → 실재하는 경로들. 부모 경로가 없으면 빈 사전.
            경로는 루트 직하 먼저, 이어서 계층 폴더 선언 순서다
    """
    if not results_dir.is_dir():
        return {}

    found: dict[str, list[Path]] = {}

    for parent in (results_dir, *(results_dir / layer for layer in RESULT_LAYERS)):
        if not parent.is_dir():
            continue

        for child in sorted(parent.iterdir()):
            if not child.is_dir() or child.name in RESULT_LAYERS:
                continue
            found.setdefault(child.name, []).append(child)

    return found


def existing_result_dirs(results_dir: Path) -> set[str]:
    """디스크에 있는 산출물 폴더 이름을 모은다.

    Args:
        results_dir: 산출물 폴더의 부모 경로

    Returns:
        set[str]: 실재하는 산출물 폴더 이름. 부모 경로가 없으면 빈 집합
    """
    return set(result_dir_paths(results_dir))


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
