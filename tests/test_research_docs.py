"""검증 결과 문서(`docs/research/`)의 「모양」 계약을 검사한다.

결과 문서는 이 저장소의 최종 산출물이자 그 검증의 진입점이다. 계획서가 삭제되고 산출물 폴더가
비워져도 이 문서 하나로 "무엇을 어떻게 재서 어떤 결론이 나왔는지"가 재구성돼야 한다.

작성 규칙은 `.claude/rules/research.md` 가 SoT이고, 그중 **기계가 채점할 수 있는 항목만** 여기서 고정한다.
문체·해석·판단은 사람이 읽어야 알 수 있으므로 대상이 아니다.

`tests/test_index.py` 와 같은 역할이다 — 문서가 계속 늘어나므로 부패가 반드시 발생하고,
틀린 진입점은 없는 것보다 나쁘다.

## 「관련 파일」 표에서 묘비 표기를 존중하는 이유

작성 규칙은 "없는 것도 「없음」으로 적고 이유를 붙인다"를 요구한다. 그래서 코드가 제거된 검증의
표에는 `**없음(제거됨)** - `...` 였다` 처럼 **지금은 없는 경로**가 기록으로 남는다.
이것을 실재 검사 대상으로 삼으면 규칙을 가장 잘 지킨 문서가 실패한다.

따라서 묘비 낱말이 있는 행의 인라인 경로는 검사하지 않는다. 어떤 낱말이 묘비인지는
`.claude/rules/research.md` 가 정하며, 이 모듈의 `TOMBSTONE_WORDS` 가 그것을 집행한다.
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESEARCH_DIR = PROJECT_ROOT / "docs" / "research"

# 마크다운 링크에서 경로를 뽑는다: [텍스트](경로)
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

# 인라인 코드에서 경로 후보를 뽑는다: `경로`
INLINE_CODE = re.compile(r"`([^`]+)`")

# 「관련 파일」 절의 제목
RELATED_HEADING = "## 관련 파일"

# 필수 장. 장 번호와 뒤따르는 설명을 허용한다 (예: `## 8. 재현 방법 - 코드가 제거됐다`)
REQUIRED_SECTIONS = {
    "한계": re.compile(r"^##\s+(?:\d+\.\s*)?한계", re.MULTILINE),
    "재현 방법": re.compile(r"^##\s+(?:\d+\.\s*)?재현 방법", re.MULTILINE),
}

# 묘비 표기. 이 낱말이 있는 행의 경로는 "지금은 없다"는 기록이므로 실재를 요구하지 않는다.
TOMBSTONE_WORDS = ("없음", "삭제", "제거")

# 파일명에 붙이면 안 되는 접두사. 폴더가 이미 "검증 결과 문서"를 뜻한다.
FORBIDDEN_PREFIX = "RESEARCH_"

# 머리말에 반드시 있어야 하는 표기. 기간이 없는 수치는 나중에 맞는지 판별할 수 없다.
DATA_PERIOD_TOKEN = "데이터 기간"

# 계획서는 주기적으로 삭제되는 임시 산출물이라 살아있는 문서가 가리키면 안 된다.
PLAN_REFERENCE = re.compile(r"docs/plans|plans/PLAN_")

# 글롭으로 해석해야 하는 경로에 들어가는 문자
GLOB_CHARS = "*?["

# 검사 대상 결과 문서
RESULT_DOCS = sorted(RESEARCH_DIR.glob("*.md"))


def _front_matter(text: str) -> str:
    """첫 `##` 제목 앞의 머리말을 잘라낸다.

    Args:
        text: 문서 본문

    Returns:
        str: 머리말. 제목이 하나도 없으면 본문 전체
    """
    match = re.search(r"^##\s", text, re.MULTILINE)
    return text[: match.start()] if match else text


def _related_section(text: str) -> str | None:
    """「관련 파일」 절의 본문을 잘라낸다.

    절의 끝은 다음 `##` 제목 또는 구분선(`---`) 중 먼저 오는 것으로 잡는다.
    표의 구분행(`| --- |`)은 `|` 로 시작하므로 구분선과 헷갈리지 않는다.

    Args:
        text: 문서 본문

    Returns:
        str | None: 절 본문. 절이 없으면 None
    """
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == RELATED_HEADING), None)
    if start is None:
        return None

    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() == "---" or line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body)


def _missing_required_sections(text: str) -> list[str]:
    """빠진 필수 장의 이름을 모은다.

    Args:
        text: 문서 본문

    Returns:
        list[str]: 빠진 장 이름 목록
    """
    return [name for name, pattern in REQUIRED_SECTIONS.items() if not pattern.search(text)]


def _missing_links(section: str, doc_dir: Path) -> list[str]:
    """절 안의 마크다운 링크 중 실재하지 않는 경로를 모은다.

    링크는 문서 위치 기준 상대경로이며, 외부 URL과 문서 내 앵커는 대상이 아니다.
    묘비 행이라도 링크를 걸었다면 그것은 살아있는 참조이므로 실재를 요구한다.

    Args:
        section: 「관련 파일」 절 본문
        doc_dir: 문서가 들어 있는 폴더

    Returns:
        list[str]: 실재하지 않는 링크 경로 목록
    """
    missing: list[str] = []
    for raw in MARKDOWN_LINK.findall(section):
        if raw.startswith(("http://", "https://", "#", "mailto:")):
            continue
        if not (doc_dir / raw.split("#")[0]).resolve().exists():
            missing.append(raw)
    return missing


def _inline_path_candidates(section: str) -> list[str]:
    """절 안에서 실재를 확인할 인라인 코드 경로를 고른다.

    묘비 낱말이 있는 행은 통째로 건너뛴다. 구분자 `/` 가 없는 인라인 코드(옵션 문자열 등)와
    자리표시자(`<검증명>`)도 경로가 아니므로 제외한다.

    Args:
        section: 「관련 파일」 절 본문

    Returns:
        list[str]: 실재를 확인할 경로 목록
    """
    candidates: list[str] = []
    for line in section.splitlines():
        if any(word in line for word in TOMBSTONE_WORDS):
            continue
        candidates += [code for code in INLINE_CODE.findall(line) if "/" in code and "<" not in code]
    return candidates


def _path_exists(root: Path, raw: str) -> bool:
    """저장소 루트 기준 경로가 실재하는지 판정한다.

    글롭 문자가 있으면 1건 이상 매치를 요구한다. 코드를 지우면 매치가 0건이 되어
    "표를 묘비로 바꾸라"는 신호가 된다.

    Args:
        root: 저장소 루트
        raw: 루트 기준 상대경로 또는 글롭

    Returns:
        bool: 실재 여부
    """
    target = raw.rstrip("/")
    if any(char in target for char in GLOB_CHARS):
        return any(root.glob(target))
    return (root / target).exists()


def _missing_inline_paths(section: str, root: Path) -> list[str]:
    """절 안의 인라인 코드 경로 중 실재하지 않는 것을 모은다.

    Args:
        section: 「관련 파일」 절 본문
        root: 저장소 루트

    Returns:
        list[str]: 실재하지 않는 경로 목록
    """
    return [raw for raw in _inline_path_candidates(section) if not _path_exists(root, raw)]


def _plan_references(text: str) -> list[str]:
    """계획서를 가리키는 링크와 인라인 경로를 모은다.

    Args:
        text: 문서 본문

    Returns:
        list[str]: 계획서 참조 목록
    """
    found = [raw for raw in MARKDOWN_LINK.findall(text) if PLAN_REFERENCE.search(raw)]
    found += [code for code in INLINE_CODE.findall(text) if PLAN_REFERENCE.search(code)]
    return found


def _document_id(path: Path) -> str:
    """파라미터화된 테스트의 표시 이름을 만든다.

    Args:
        path: 결과 문서 경로

    Returns:
        str: 파일명
    """
    return path.name


def test_research_documents_exist() -> None:
    """
    목적: 검사 대상이 비어 있지 않음을 고정한다 (조용한 통과 차단).

    Given: docs/research/ 폴더
    When: 결과 문서 목록을 만든다
    Then: 폴더가 존재하고 결과 문서가 하나 이상 있다
    """
    assert RESEARCH_DIR.is_dir(), f"결과 문서 폴더가 없습니다: {RESEARCH_DIR}"
    assert RESULT_DOCS, "docs/research/ 에 결과 문서가 하나도 없습니다"


@pytest.mark.parametrize("doc", RESULT_DOCS, ids=_document_id)
def test_filename_has_no_forbidden_prefix(doc: Path) -> None:
    """
    목적: 파일명 규약을 고정한다 (폴더가 이미 뜻하는 것을 이름에 두 번 적지 않는다).

    Given: 결과 문서 파일명
    When: 금지 접두사를 확인한다
    Then: `RESEARCH_` 로 시작하지 않는다
    """
    assert not doc.name.startswith(FORBIDDEN_PREFIX), (
        f"결과 문서에 `{FORBIDDEN_PREFIX}` 접두사를 붙이지 않습니다: {doc.name}\n"
        "  폴더가 이미 「검증 결과 문서」를 뜻합니다 (.claude/rules/research.md 「파일 네이밍」)"
    )


@pytest.mark.parametrize("doc", RESULT_DOCS, ids=_document_id)
def test_related_section_exists(doc: Path) -> None:
    """
    목적: 결과 문서가 그 검증의 진입점 역할을 한다는 계약을 고정한다.

    Given: 결과 문서 본문
    When: 「관련 파일」 절을 찾는다
    Then: 절이 존재한다
    """
    text = doc.read_text(encoding="utf-8")
    assert _related_section(text) is not None, (
        f"「{RELATED_HEADING}」 절이 없습니다: {doc.name}\n" "  결과 문서는 그 검증의 진입점이며 여기서 설계·코드·스크립트·테스트에 도달해야 합니다"
    )


@pytest.mark.parametrize("doc", RESULT_DOCS, ids=_document_id)
def test_required_sections_exist(doc: Path) -> None:
    """
    목적: 「한계」와 「재현 방법」이 빠지지 않음을 고정한다 (둘 다 작성 규칙상 필수).

    Given: 결과 문서 본문
    When: 필수 장 제목을 찾는다
    Then: 빠진 장이 없다
    """
    missing = _missing_required_sections(doc.read_text(encoding="utf-8"))
    assert not missing, f"필수 장이 없습니다: {doc.name}\n" + "\n".join(f"  - {name}" for name in missing)


@pytest.mark.parametrize("doc", RESULT_DOCS, ids=_document_id)
def test_front_matter_declares_data_period(doc: Path) -> None:
    """
    목적: 수치의 근거 기간이 머리말에 있음을 고정한다.

    기간이 없는 수치는 시세를 재수집한 뒤 맞는지 틀린지 판별할 방법이 없다.

    Given: 결과 문서의 머리말(첫 `##` 제목 앞)
    When: 데이터 기간 표기를 찾는다
    Then: 표기가 존재한다
    """
    front = _front_matter(doc.read_text(encoding="utf-8"))
    assert DATA_PERIOD_TOKEN in front, (
        f"머리말에 「{DATA_PERIOD_TOKEN}」 표기가 없습니다: {doc.name}\n" "  시작일과 종료일, 행 수를 적습니다 (.claude/rules/docs.md)"
    )


@pytest.mark.parametrize("doc", RESULT_DOCS, ids=_document_id)
def test_related_links_resolve(doc: Path) -> None:
    """
    목적: 「관련 파일」 표의 마크다운 링크가 전부 실재함을 고정한다 (죽은 진입점 차단).

    Given: 「관련 파일」 절의 내부 링크
    When: 각 경로를 파일 시스템에서 확인한다
    Then: 존재하지 않는 링크가 없다
    """
    section = _related_section(doc.read_text(encoding="utf-8"))
    assert section is not None, f"「{RELATED_HEADING}」 절이 없습니다: {doc.name}"

    missing = _missing_links(section, doc.parent)
    assert not missing, f"「관련 파일」 표가 없는 경로를 링크합니다: {doc.name}\n" + "\n".join(f"  - {raw}" for raw in missing)


@pytest.mark.parametrize("doc", RESULT_DOCS, ids=_document_id)
def test_related_inline_paths_resolve(doc: Path) -> None:
    """
    목적: 「관련 파일」 표의 인라인 경로가 실재함을 고정한다 (코드를 지우고 표를 안 고친 경우 차단).

    묘비 표기가 있는 행은 "지금은 없다"는 기록이므로 검사하지 않는다.

    Given: 「관련 파일」 절의 인라인 코드 경로 중 묘비 행이 아닌 것
    When: 저장소 루트 기준으로 실재를 확인한다 (글롭은 1건 이상 매치를 요구)
    Then: 실재하지 않는 경로가 없다
    """
    section = _related_section(doc.read_text(encoding="utf-8"))
    assert section is not None, f"「{RELATED_HEADING}」 절이 없습니다: {doc.name}"

    missing = _missing_inline_paths(section, PROJECT_ROOT)
    assert not missing, (
        f"「관련 파일」 표가 없는 경로를 가리킵니다: {doc.name}\n"
        + "\n".join(f"  - {raw}" for raw in missing)
        + f"\n  코드를 지웠다면 그 행을 묘비 표기로 바꿉니다 (허용 낱말: {', '.join(TOMBSTONE_WORDS)})"
    )


@pytest.mark.parametrize("doc", RESULT_DOCS, ids=_document_id)
def test_no_plan_references(doc: Path) -> None:
    """
    목적: 살아있는 문서가 임시 산출물을 가리키지 않음을 고정한다.

    계획서는 사용자가 주기적으로 전부 삭제하므로 링크가 반드시 깨진다.

    Given: 결과 문서 본문 전체
    When: 계획서를 가리키는 링크와 인라인 경로를 찾는다
    Then: 하나도 없다
    """
    found = _plan_references(doc.read_text(encoding="utf-8"))
    assert not found, (
        f"계획서(docs/plans/)를 참조합니다: {doc.name}\n"
        + "\n".join(f"  - {raw}" for raw in found)
        + "\n  계획서는 주기적으로 삭제되는 임시 산출물이라 참조가 깨집니다"
    )


@pytest.fixture
def fake_root(tmp_path: Path) -> Path:
    """합성 검사용 저장소 루트를 만든다.

    실제 `docs/` 를 건드리지 않기 위해 임시 폴더에 최소한의 파일만 둔다.

    Args:
        tmp_path: pytest 임시 폴더

    Returns:
        Path: 합성 저장소 루트
    """
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample_one.py").touch()
    (tmp_path / "docs" / "spec").mkdir(parents=True)
    (tmp_path / "docs" / "spec" / "sample.md").touch()
    return tmp_path


def test_forbidden_prefix_is_detected() -> None:
    """
    목적: 접두사 검사가 실제로 위반을 잡는지 고정한다.

    Given: 금지 접두사가 붙은 파일명
    When: 접두사를 확인한다
    Then: 위반으로 판정된다
    """
    assert "RESEARCH_옵션_만기일.md".startswith(FORBIDDEN_PREFIX)
    assert not "옵션_만기일.md".startswith(FORBIDDEN_PREFIX)


def test_missing_related_section_is_detected() -> None:
    """
    목적: 「관련 파일」 절 누락을 잡는지 고정한다.

    Given: 그 절이 없는 합성 문서
    When: 절을 잘라낸다
    Then: None 이 반환된다
    """
    text = "# 표본 검증\n\n> **데이터 기간**: 2020-01-01 ~ 2020-12-31 (250 거래일)\n\n## 1. 결론\n\n없다\n"
    assert _related_section(text) is None


def test_missing_required_section_is_detected() -> None:
    """
    목적: 필수 장 누락을 잡는지 고정한다.

    Given: 「한계」 장이 없는 합성 문서
    When: 필수 장을 확인한다
    Then: 빠진 장으로 보고된다
    """
    text = "# 표본 검증\n\n## 5. 재현 방법\n\n돌린다\n"
    assert _missing_required_sections(text) == ["한계"]


def test_front_matter_stops_at_first_heading() -> None:
    """
    목적: 머리말 판정이 본문까지 훑지 않음을 고정한다 (경계 조건).

    Given: 표기가 본문에만 있는 합성 문서
    When: 머리말을 잘라낸다
    Then: 머리말에는 표기가 없다
    """
    text = "# 표본 검증\n\n> 대상: 표본\n\n## 3. 대상과 근거 소스\n\n데이터 기간은 여기에 있다\n"
    assert DATA_PERIOD_TOKEN not in _front_matter(text)
    assert DATA_PERIOD_TOKEN in text


def test_dead_link_is_detected(fake_root: Path) -> None:
    """
    목적: 「관련 파일」 표의 죽은 마크다운 링크를 잡는지 고정한다.

    Given: 없는 파일을 링크한 합성 절
    When: 링크를 해석한다
    Then: 죽은 링크로 보고된다
    """
    doc_dir = fake_root / "docs" / "research"
    doc_dir.mkdir(parents=True)
    section = "| 확정 설계 | [sample.md](../spec/sample.md) · [gone.md](../spec/gone.md) |"

    assert _missing_links(section, doc_dir) == ["../spec/gone.md"]


def test_external_link_is_not_checked(fake_root: Path) -> None:
    """
    목적: 외부 URL과 앵커를 실재 검사 대상에서 뺀다는 계약을 고정한다 (경계 조건).

    Given: 외부 URL과 문서 내 앵커만 있는 합성 절
    When: 링크를 해석한다
    Then: 죽은 링크가 없다
    """
    doc_dir = fake_root / "docs" / "research"
    doc_dir.mkdir(parents=True)
    section = "| 참고 | [문헌](https://example.com/a) · [본문](#3-대상과-근거-소스) |"

    assert _missing_links(section, doc_dir) == []


def test_dead_inline_path_is_detected(fake_root: Path) -> None:
    """
    목적: 「관련 파일」 표의 죽은 인라인 경로를 잡는지 고정한다.

    Given: 묘비가 아닌 행이 없는 경로를 가리키는 합성 절
    When: 실재를 확인한다
    Then: 죽은 경로로 보고된다
    """
    section = "| 실행 스크립트 | `scripts/studies/run_sample.py` 로 돌립니다 |"

    assert _missing_inline_paths(section, fake_root) == ["scripts/studies/run_sample.py"]


def test_tombstone_row_is_exempt(fake_root: Path) -> None:
    """
    목적: 묘비 표기 행을 검사에서 빼는 계약을 고정한다.

    작성 규칙이 "없는 것도 「없음」으로 적고 이유를 붙인다"를 요구하므로, 코드가 제거된 검증의
    표에는 지금 없는 경로가 기록으로 남는다. 이것을 실패로 처리하면 규칙을 지킨 문서가 실패한다.

    Given: 실물(`연속_등락.md`) 형식을 본뜬 묘비 행
    When: 실재를 확인한다
    Then: 검사 대상에서 빠져 위반이 없다
    """
    section = "\n".join(
        [
            "| 이벤트 정의 | **없음(제거됨)** - `src/verify_lab/studies/sample/gone.py` 였다 |",
            "| 실행 스크립트 | **삭제됨** (2026-08-30) - `scripts/studies/run_gone.py` 였습니다 |",
            "| 테스트 | **없음(제거됨)** - `tests/test_gone_*.py` 였다 |",
        ]
    )

    assert _inline_path_candidates(section) == []
    assert _missing_inline_paths(section, fake_root) == []


def test_glob_requires_at_least_one_match(fake_root: Path) -> None:
    """
    목적: 글롭 경로가 1건 이상 매치를 요구함을 고정한다 (경계 조건).

    Given: 매치되는 글롭과 매치되지 않는 글롭
    When: 실재를 확인한다
    Then: 매치가 0건인 글롭만 위반으로 보고된다
    """
    section = "| 테스트 | `tests/test_sample_*.py` · `tests/test_absent_*.py` |"

    assert _missing_inline_paths(section, fake_root) == ["tests/test_absent_*.py"]


def test_non_path_inline_code_is_ignored(fake_root: Path) -> None:
    """
    목적: 경로가 아닌 인라인 코드를 검사 대상에서 뺀다는 계약을 고정한다 (경계 조건).

    Given: 옵션 문자열과 자리표시자가 든 합성 절
    When: 검사 대상을 고른다
    Then: 하나도 고르지 않는다
    """
    section = "| 데이터 수집 | `--series usdkrw_close` · `docs/spec/<검증명>.md` |"

    assert _inline_path_candidates(section) == []


def test_plan_reference_is_detected() -> None:
    """
    목적: 계획서 참조를 잡는지 고정한다.

    Given: 계획서를 링크·인라인으로 가리키는 합성 문서
    When: 참조를 찾는다
    Then: 둘 다 보고된다
    """
    text = "본문 [계획서](../plans/PLAN_sample.md) 와 `docs/plans/PLAN_other.md` 를 가리킨다"

    assert _plan_references(text) == ["../plans/PLAN_sample.md", "docs/plans/PLAN_other.md"]
