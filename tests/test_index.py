"""문서 지도(docs/INDEX.md)와 문서 배치 계약을 검사한다.

틀린 인덱스는 없는 것보다 나쁘다. 문서를 추가·삭제·이동했는데 INDEX를 고치지 않으면
AI 모델이 없는 파일을 찾거나 있는 파일을 놓친다. 이 프로젝트는 검증마다 문서가 계속
늘어나므로 부패가 반드시 발생한다.

네 가지를 검사한다.

1. INDEX에 적힌 경로가 실재하는가 (죽은 링크 차단)
2. 실재하는 문서가 INDEX에 등록됐는가 (누락 차단)
3. 세션 시작 규칙이 조건 없이 로드되는가 (진입 경로 보장)
4. 걷어낸 문서가 되살아나지 않았는가 (「앞으로의 계획」 재유입 차단)
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = PROJECT_ROOT / "docs" / "INDEX.md"

# 마크다운 링크에서 경로를 뽑는다: [텍스트](경로)
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

# INDEX 등록 의무에서 제외하는 경로.
# plans/ 는 주기적으로 삭제되는 임시 산출물이고, 나머지는 git 구조 유지용 빈 파일이다.
REGISTRATION_EXEMPT = (
    "docs/INDEX.md",  # 자기 자신
    "docs/plans/",
    ".gitkeep",
)

# INDEX 등록 대상 폴더
REGISTERED_DIRS = ("docs", "reference")

# 세션 시작마다 조건 없이 로드되는 규칙. 여기에 진입 순서가 있다.
BOOTSTRAP_RULE_PATH = PROJECT_ROOT / ".claude" / "rules" / "session-bootstrap.md"

# 계획서 폴더를 비워도 남겨야 하는 파일.
# 폴더가 사라지면 계획서 게이트 훅이 규약 미채택으로 보고 조용히 꺼진다.
PLANS_KEEPER_PATH = PROJECT_ROOT / "docs" / "plans" / ".gitkeep"

# 저장소에서 걷어낸 문서.
# 되살아나면 「앞으로의 계획」과 작업 일지가 다시 쌓이고, 근거가 두 벌이 된다.
REMOVED_DOCUMENTS = (
    "docs/ROADMAP.md",
    "docs/HANDS_ON.md",
    "다음세션_프롬프트.md",
    "docs/research/CLAUDE.md",
)


def _index_text() -> str:
    """INDEX 본문을 읽는다."""
    return INDEX_PATH.read_text(encoding="utf-8")


def _linked_paths() -> list[Path]:
    """INDEX의 마크다운 링크 중 저장소 내부 경로만 해석해 반환한다."""
    resolved: list[Path] = []
    for raw in MARKDOWN_LINK.findall(_index_text()):
        if raw.startswith(("http://", "https://", "#", "mailto:")):
            continue
        # 앵커(#절)는 떼고 파일 경로만 본다
        target = (INDEX_PATH.parent / raw.split("#")[0]).resolve()
        resolved.append(target)
    return resolved


def _tracked_files() -> list[Path]:
    """INDEX에 등록돼야 하는 실제 파일 목록을 만든다."""
    tracked: list[Path] = []
    for dir_name in REGISTERED_DIRS:
        for path in (PROJECT_ROOT / dir_name).rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(PROJECT_ROOT).as_posix()
            if any(part in relative for part in REGISTRATION_EXEMPT):
                continue
            tracked.append(path)
    return tracked


def _front_matter(text: str) -> str:
    """규칙 문서 앞머리의 YAML frontmatter 를 반환한다.

    Args:
        text: 규칙 문서 본문

    Returns:
        구분자(`---`) 사이의 내용. frontmatter 가 없으면 빈 문자열
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""

    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[1:index])
    return ""


def test_index_exists() -> None:
    """
    목적: 문서 지도가 존재한다는 계약을 고정한다.

    Given: 저장소 루트
    When: docs/INDEX.md 를 찾는다
    Then: 파일이 존재하고 비어 있지 않다
    """
    assert INDEX_PATH.is_file(), f"문서 지도가 없습니다: {INDEX_PATH}"
    assert _index_text().strip(), "문서 지도가 비어 있습니다"


def test_index_links_resolve() -> None:
    """
    목적: INDEX에 적힌 경로가 전부 실재함을 고정한다 (죽은 링크 차단).

    Given: INDEX의 모든 내부 마크다운 링크
    When: 각 경로를 파일 시스템에서 확인한다
    Then: 존재하지 않는 경로가 하나도 없다
    """
    missing = [p for p in _linked_paths() if not p.exists()]
    assert not missing, "INDEX가 존재하지 않는 경로를 가리킵니다:\n" + "\n".join(
        f"  - {p.relative_to(PROJECT_ROOT) if PROJECT_ROOT in p.parents else p}" for p in missing
    )


def test_all_documents_registered() -> None:
    """
    목적: docs/ 와 reference/ 의 모든 파일이 INDEX에 등록됨을 고정한다 (누락 차단).

    Given: 등록 의무 대상 폴더의 실제 파일 목록
    When: INDEX가 링크한 경로 집합과 대조한다
    Then: 등록되지 않은 파일이 하나도 없다
    """
    linked = set(_linked_paths())
    unregistered = [p for p in _tracked_files() if p.resolve() not in linked]
    assert not unregistered, "INDEX에 등록되지 않은 문서가 있습니다. docs/INDEX.md 에 추가하세요:\n" + "\n".join(
        f"  - {p.relative_to(PROJECT_ROOT)}" for p in sorted(unregistered)
    )


@pytest.mark.parametrize(
    "required",
    [
        "CLAUDE.md",
        "docs/context/README.md",
    ],
)
def test_core_documents_linked(required: str) -> None:
    """
    목적: 진입에 반드시 필요한 문서가 INDEX에서 빠지지 않음을 고정한다.

    Given: 핵심 문서 경로
    When: INDEX가 링크한 경로 집합을 확인한다
    Then: 해당 문서가 링크돼 있다
    """
    target = (PROJECT_ROOT / required).resolve()
    assert target in set(_linked_paths()), f"INDEX에 핵심 문서 링크가 없습니다: {required}"


def test_bootstrap_rule_exists() -> None:
    """
    목적: 세션 시작 규칙이 존재한다는 계약을 고정한다.

    Given: 저장소의 .claude/rules/
    When: session-bootstrap.md 를 찾는다
    Then: 파일이 존재하고 비어 있지 않다
    """
    assert BOOTSTRAP_RULE_PATH.is_file(), f"세션 시작 규칙이 없습니다: {BOOTSTRAP_RULE_PATH}"
    assert BOOTSTRAP_RULE_PATH.read_text(encoding="utf-8").strip(), "세션 시작 규칙이 비어 있습니다"


def test_bootstrap_rule_loads_unconditionally() -> None:
    """
    목적: 세션 시작 규칙이 조건 없이 로드됨을 고정한다.

    `paths` frontmatter 가 붙으면 그 경로의 파일을 열 때만 로드된다. 진입 순서를 정하는
    규칙이 그렇게 되면 첫 작업 전에는 보이지 않아 목적을 잃는다.

    Given: session-bootstrap.md 의 본문
    When: 앞머리의 frontmatter 를 확인한다
    Then: paths 필드가 없다
    """
    text = BOOTSTRAP_RULE_PATH.read_text(encoding="utf-8")
    front_matter = _front_matter(text)

    assert "paths:" not in front_matter, (
        "세션 시작 규칙에 paths frontmatter 가 있습니다. "
        "조건부로 바뀌어 첫 작업 전에 로드되지 않습니다:\n"
        f"  - {BOOTSTRAP_RULE_PATH.relative_to(PROJECT_ROOT)}"
    )


def test_plans_folder_keeper_exists() -> None:
    """
    목적: 계획서 폴더가 비어도 유지된다는 계약을 고정한다.

    폴더가 사라지면 계획서 게이트 훅이 규약 미채택으로 판정해 조용히 꺼진다.

    Given: docs/plans/
    When: .gitkeep 을 찾는다
    Then: 파일이 존재한다
    """
    assert PLANS_KEEPER_PATH.is_file(), "docs/plans/.gitkeep 이 없습니다. 계획서를 전부 비우면 폴더가 사라져 " "계획서 게이트가 꺼집니다"


@pytest.mark.parametrize("removed", REMOVED_DOCUMENTS)
def test_removed_documents_stay_removed(removed: str) -> None:
    """
    목적: 걷어낸 문서가 되살아나지 않음을 고정한다.

    이 저장소의 docs 는 「현재 상태와 분석 결과」만 담는다. 진행 일지와 앞으로의 계획은
    다시 쌓이기 쉬우므로 파일 단위로 막는다.

    Given: 재편에서 삭제한 문서 경로
    When: 파일 시스템에서 확인한다
    Then: 존재하지 않는다
    """
    target = PROJECT_ROOT / removed
    assert not target.exists(), (
        f"걷어낸 문서가 되살아났습니다: {removed}\n"
        "  진행 상태와 계획은 남기지 않습니다. 결과는 docs/research/, "
        "설계는 docs/spec/, 규칙은 .claude/rules/ 에 둡니다"
    )
