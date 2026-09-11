"""문서가 근거로 인용한 산출물 폴더를 찾는다.

결과 문서는 수치의 근거로 `storage/results/` 의 실행 폴더를 인용한다. 그 폴더가 사라지면
문서는 대조할 수 없는 숫자만 남기므로, **어느 폴더가 인용됐는지**를 한 곳에서 판정한다.

세 방향으로 쓴다. 앞의 둘은 **이름**을, 마지막은 **경로**를 본다.

- `missing_citations()` — 인용됐는데 없는 폴더. 품질 검증이 실패로 잡는다
- `unreferenced_dirs()` — 있는데 인용되지 않은 폴더. 정리 도구가 삭제 후보로 뽑는다
- `missing_result_paths()` — 문서가 적은 산출물 **경로**가 실재하는가

**이름과 경로를 함께 봐야 하는 이유는 하나다 — 폴더를 옮기면 이름은 살아 있고 경로만 죽는다.**
`RESULT_DIR_NAME` 은 `storage/results/` 접두어를 요구하지 않으므로 그 상태를 그대로 통과시키고,
탐색이 여러 자리를 훑으므로 「없는 폴더」로도 잡히지 않는다. 그런데 문서에 적힌 경로는 전부
죽어 있어 **사용자가 근거를 열 수 없다.** 이름만 보는 판정에는 이 실패에 눈이 없다.

**두 판정이 갈라지면 정리 도구가 「지워도 된다」고 한 폴더를 검증이 요구하는 상태가 되므로
인용의 정의는 이 모듈 하나가 소유한다.** 같은 이유로 **두 쪽이 같은 루트를 넘겨야 한다** —
루트 `CLAUDE.md` 가 실제로 산출물을 인용하므로 `docs/` 만 훑으면 그 인용을 놓치고,
그때 검증은 통과하는데 정리 도구가 근거물을 삭제 후보로 낸다. 같은 이유로 **「그 폴더가 어디 있는가」도 여기서 낸다**
(`result_dir_paths()`) — 정리 도구가 이름만 받아 경로를 되조립하면 두 곳의 가정이 갈라진다.

**산출물이 사는 자리는 계층 폴더(`검증`·`매매`·`실측`) 하나다.** 그럼에도 탐색이 루트 직하를
함께 보는 것은 옛 자리를 위해서가 아니라 **실수로 그 자리에 생긴 폴더를 치울 수 있게 하려는 것**이다.

두 장치가 **이어서** 동작한다 — `tests/test_result_citations.py` 가 루트 직하의 폴더를 품질
검증에서 실패로 알리고, 그 다음 `/clean-results` 가 **탐색을 통해** 그 폴더를 찾아 지운다.
탐색에서 루트를 빼면 알림은 오는데 **치울 수단이 없어** 빌드가 막힌 채로 남는다.
"""

import re
from collections.abc import Iterator
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

# 인라인 코드. **이 저장소의 관용이지 강제가 아니다** — 마크다운 링크나 코드블록으로 적은
# 경로는 이 판정에 잡히지 않는다. 넓히지 않는 것은 링크 검사를 `tests/test_research_docs.py` 가
# 이미 자기 범위에서 하고 있어, 여기서 또 하면 판정이 겹치기 때문이다
INLINE_CODE: Final = re.compile(r"`([^`]+)`")

# 실재를 요구하지 않는 인라인 코드에 들어가는 문자.
# 자리표시자(`<실행시각>_<매매법>`)와 묶음 표기(`{검증, 매매, 실측}`)는 **경로가 아니라 규격**이고,
# 글롭(`*`)은 실재를 0건으로도 1건으로도 만들 수 있어 이 판정의 대상이 아니다
NOT_A_PATH_CHARS: Final = "<>{}*?[]"


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


def _is_tombstone(line: str) -> bool:
    """「일부러 없앤 것」을 적은 줄인지 판정한다.

    **이름 판정과 경로 판정이 같은 어휘를 봐야 한다** — 갈라지면 한쪽이 묘비로 넘긴 줄을
    다른 쪽이 실재로 요구한다.

    Args:
        line: 문서의 한 줄

    Returns:
        bool: 묘비 낱말이 들어 있으면 True
    """
    return any(word in line for word in TOMBSTONE_WORDS)


def _scannable_lines(root: Path) -> Iterator[tuple[Path, str]]:
    """인용을 셀 문서의 줄을 훑는다.

    **훑는 범위를 한 곳이 소유한다.** 제외 폴더를 늘리거나 대상 확장자를 바꿀 때 두 곳을
    고쳐야 하면, 한쪽만 고친 순간 이름 판정과 경로 판정이 다른 문서 집합을 보게 된다.

    Args:
        root: 문서를 찾을 시작 경로

    Yields:
        tuple[Path, str]: (문서 경로, 그 문서의 한 줄)
    """
    for path in sorted(root.rglob("*.md")):
        if not _is_scannable(path, root):
            continue

        for line in path.read_text(encoding="utf-8").splitlines():
            yield path, line


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

    for _, line in _scannable_lines(root):
        if _is_tombstone(line):
            continue
        cited.update(RESULT_DIR_NAME.findall(line))

    return cited


def result_dir_paths(results_dir: Path) -> dict[str, list[Path]]:
    """디스크에 있는 산출물 폴더를 **이름 → 경로 목록**으로 모은다.

    산출물은 계층 폴더 아래에 있고, **루트 직하도 함께 훑는다** — 거기 폴더가 생기는 것은
    이제 실수뿐인데, 훑지 않으면 그 실수가 정리 도구의 시야 밖에 남는다.
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


def _result_path_candidates(line: str) -> list[str]:
    """한 줄에서 실재를 확인할 산출물 경로를 고른다.

    **산출물 폴더 이름이 들어 있는 경로만 고른다.** 그 이름이 이 판정의 주제이고, 요구하지
    않으면 `storage/results/` 아래의 **산출물이 아닌 파일까지 실재를 요구하게 된다** —
    `meta.json` 은 git 제외 대상이라 아직 한 번도 실행하지 않은 PC 에는 없고,
    그것을 요구하면 **커밋으로 고칠 수 없는 실패**가 된다.

    덕분에 세 형태가 한 규칙으로 들어온다 — 접두어가 붙은 `storage/results/검증/<폴더>/x.csv`,
    계층부터 적은 `검증/<폴더>/x.csv`, 폴더 이름부터 적은 `<폴더>/x.csv`.
    뒤의 둘도 경로이며 **폴더가 움직이면 함께 죽는다.**

    [주의] 묘비 판정이 줄 단위라 **`cited_result_dirs` 보다 눈이 좁다.** 그쪽은 한 폴더가
    여러 줄에 나오면 묘비 없는 줄이 이기지만, 여기는 줄마다 따로 판정하므로 죽은 경로가
    「제거했다」 같은 낱말이 든 줄에만 적혀 있으면 검사되지 않는다.

    Args:
        line: 문서의 한 줄

    Returns:
        list[str]: 실재를 확인할 경로 문자열. 묘비 줄이면 빈 목록
    """
    if _is_tombstone(line):
        return []

    candidates: list[str] = []

    for code in INLINE_CODE.findall(line):
        raw = code.strip().rstrip("/")

        # 파일 하나를 가리키지 않는 인라인 코드가 대부분이다. 먼저 거른다
        if "/" not in raw or any(char in raw for char in NOT_A_PATH_CHARS):
            continue

        if RESULT_DIR_NAME.search(raw):
            candidates.append(raw)

    return candidates


def _resolves(raw: str, root: Path, results_dir: Path, dir_paths: dict[str, list[Path]]) -> bool:
    """산출물 경로가 실제 파일·폴더에 닿는지 판정한다.

    접두어가 붙은 형태는 `root` 기준으로 풀고, 그렇지 않은 형태는 **자리를 되조립하지 않고**
    `result_dir_paths` 가 낸 실제 경로에 남은 부분을 이어 붙인다. 이름으로 자리를 추측하면
    그 가정이 탐색과 갈라진다.

    [주의] 접두어 없는 형태에는 계층 정보가 없으므로 **같은 이름을 가진 어느 계층에서든
    닿으면 통과한다.** 측정과 매매가 같은 slug 를 쓰는 것이 이 저장소의 규약이라 생기는
    한계이며, 그래도 검사하지 않는 것보다는 낫다.

    Args:
        raw: 확인할 경로 문자열
        root: 저장소 루트
        results_dir: 산출물 폴더의 부모 경로
        dir_paths: 산출물 폴더 이름 → 실재하는 경로들

    Returns:
        bool: 실재 여부
    """
    prefix = f"{results_dir.relative_to(root).as_posix()}/"
    if raw.startswith(prefix):
        return (root / raw).exists()

    found = RESULT_DIR_NAME.search(raw)
    if found is None:
        return False

    remainder = raw[found.end() :].lstrip("/")

    return any((path / remainder).exists() for path in dir_paths.get(found.group(1), []))


def missing_result_paths(root: Path, results_dir: Path) -> list[str]:
    """문서가 적은 산출물 경로 중 실재하지 않는 것을 찾는다.

    **`missing_citations()` 이 못 잡는 실패를 잡는다** — 폴더를 옮기면 이름은 살아 있고
    경로만 죽으므로, 이름을 보는 판정은 그 상태를 통과시킨다.

    Args:
        root: 문서를 찾을 시작 경로이자 상대경로의 기준
        results_dir: 산출물 폴더의 부모 경로. `root` 아래에 있어야 한다

    Returns:
        list[str]: `<문서 경로>: <죽은 경로>` 형식. 어느 문서를 고쳐야 하는지가 값 안에 있다

    Raises:
        ValueError: `results_dir` 이 `root` 아래에 있지 않은 경우
    """
    if not results_dir.is_relative_to(root):
        raise ValueError(f"산출물 경로가 문서 루트 아래에 있어야 합니다: results_dir={results_dir}, root={root}")

    dir_paths = result_dir_paths(results_dir)
    missing: set[str] = set()

    for path, line in _scannable_lines(root):
        for raw in _result_path_candidates(line):
            if not _resolves(raw, root, results_dir, dir_paths):
                # 경로 구분자를 OS 에 맡기면 같은 저장소가 PC 마다 다른 값을 낸다.
                # 이 저장소는 mac 과 Windows 에서 이어 작업하는 것이 전제다
                missing.add(f"{path.relative_to(root).as_posix()}: {raw}")

    return sorted(missing)
