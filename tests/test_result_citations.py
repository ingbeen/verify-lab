"""문서와 산출물 폴더 사이의 인용 계약을 고정한다.

결과 문서는 수치의 근거로 산출물 폴더를 인용한다. **인용한 폴더가 사라지면 문서는
대조할 수 없는 숫자만 남는다** — 실제로 그 상태의 문서가 8개 쌓인 적이 있다.

두 방향을 함께 고정한다. 판정이 갈라지면 정리 도구가 「지워도 된다」고 한 폴더를
품질 검증이 요구하는 상태가 되기 때문이다.
"""

from pathlib import Path

import pytest

from verify_lab.common_constants import DOCS_DIR, RESULTS_DIR
from verify_lab.utils.result_citations import (
    cited_result_dirs,
    existing_result_dirs,
    missing_citations,
    unreferenced_dirs,
)

# 합성 문서에 쓰는 산출물 폴더 이름. 실제 저장소의 이름과 겹치지 않게 미래 날짜를 쓴다
FAKE_DIR_A = "29991231_120000_fake_study"
FAKE_DIR_B = "29991231_130000_other_study"


@pytest.fixture
def docs_root(tmp_path: Path) -> Path:
    """합성 문서 트리의 루트를 만든다.

    실제 `docs/` 와 같은 폴더 구성(`research`·`plans`·`context`)을 갖춘다.

    Args:
        tmp_path: pytest가 테스트마다 새로 만드는 임시 디렉터리

    Returns:
        Path: 문서 루트
    """
    root = tmp_path / "docs"
    for name in ("research", "plans", "context"):
        (root / name).mkdir(parents=True)

    return root


@pytest.fixture
def results_root(tmp_path: Path) -> Path:
    """합성 산출물 폴더의 부모 경로를 만든다.

    Args:
        tmp_path: pytest가 테스트마다 새로 만드는 임시 디렉터리

    Returns:
        Path: 산출물 부모 경로
    """
    root = tmp_path / "results"
    root.mkdir()

    return root


def test_prefixed_citation_is_counted(docs_root: Path) -> None:
    """
    목적: `storage/results/` 접두어가 붙은 인용을 센다 (결과 문서의 관용)

    Given: 머리말에 접두어 형태로 폴더를 적은 문서
    When: 인용을 모은다
    Then: 그 폴더가 인용 집합에 들어간다
    """
    # Given
    (docs_root / "research" / "a.md").write_text(f"> **근거 산출물**: `storage/results/{FAKE_DIR_A}/`\n", encoding="utf-8")

    # When
    cited = cited_result_dirs(docs_root)

    # Then
    assert cited == {FAKE_DIR_A}


def test_bare_folder_name_is_counted(docs_root: Path) -> None:
    """
    목적: 접두어 없이 폴더 이름만 적은 인용도 센다

    `docs/spec/` 은 대조표에서 폴더 이름만 적는다. 접두어를 요구하면 그 인용을 통째로
    놓쳐 **아직 쓰이는 산출물이 정리 대상으로 올라간다.**

    Given: 표 안에 폴더 이름만 적은 문서
    When: 인용을 모은다
    Then: 그 폴더가 인용 집합에 들어간다
    """
    # Given
    (docs_root / "research" / "a.md").write_text(f"| REF | 6자리 | `{FAKE_DIR_A}` |\n", encoding="utf-8")

    # When
    cited = cited_result_dirs(docs_root)

    # Then
    assert cited == {FAKE_DIR_A}


def test_placeholder_is_not_counted(docs_root: Path) -> None:
    """
    목적: 자리표시자를 인용으로 세지 않는다

    `<실행시각>_index_extreme` 은 「산출물이 생기는 위치」를 말하는 자리라
    실재를 요구하면 안 된다.

    Given: 자리표시자만 적힌 문서
    When: 인용을 모은다
    Then: 인용이 하나도 잡히지 않는다
    """
    # Given
    (docs_root / "research" / "a.md").write_text(
        "산출물은 `storage/results/<실행시각>_index_extreme/` 에 남습니다.\n", encoding="utf-8"
    )

    # When
    cited = cited_result_dirs(docs_root)

    # Then
    assert cited == set()


@pytest.mark.parametrize("word", ["없음", "삭제", "제거"])
def test_tombstone_line_is_not_counted(docs_root: Path, word: str) -> None:
    """
    목적: 묘비 낱말이 같은 줄에 있으면 실재를 요구하지 않는다

    산출물이 사라졌다는 사실 자체를 적은 문장까지 실재를 요구하면,
    **없어진 것을 문서에 남길 방법이 없어진다.**

    Given: 폴더 이름과 묘비 낱말이 같은 줄에 있는 문서
    When: 인용을 모은다
    Then: 그 폴더는 인용으로 세지 않는다
    """
    # Given
    (docs_root / "research" / "a.md").write_text(f"| 6장 | `{FAKE_DIR_A}` — **{word}** |\n", encoding="utf-8")

    # When
    cited = cited_result_dirs(docs_root)

    # Then
    assert cited == set()


def test_tombstone_elsewhere_does_not_hide_live_citation(docs_root: Path) -> None:
    """
    목적: 한 폴더가 여러 줄에 나오면 묘비가 없는 줄이 이긴다

    실재를 요구하는 쪽이 안전한 판정이다. 다른 문단의 「없음」 한 줄 때문에
    살아있는 근거가 정리 대상으로 넘어가면 안 된다.

    Given: 같은 폴더가 묘비 줄과 일반 줄에 각각 나오는 문서
    When: 인용을 모은다
    Then: 그 폴더는 인용으로 센다
    """
    # Given
    (docs_root / "research" / "a.md").write_text(
        f"이 표의 근거는 `{FAKE_DIR_A}` 이다.\n" f"과거 실행(`{FAKE_DIR_A}`)의 사본은 **없음**.\n",
        encoding="utf-8",
    )

    # When
    cited = cited_result_dirs(docs_root)

    # Then
    assert cited == {FAKE_DIR_A}


@pytest.mark.parametrize("excluded", ["plans", "context"])
def test_excluded_doc_dirs_are_not_scanned(docs_root: Path, excluded: str) -> None:
    """
    목적: 계획서와 사용자 소유 문서의 인용은 세지 않는다

    계획서는 주기적으로 삭제되는 임시 산출물이라 거기 적힌 폴더명이 계약이 아니고,
    `context/` 의 산출물 경로는 이전 프로젝트의 것이다.

    Given: 제외 폴더에만 폴더 이름이 적힌 문서
    When: 인용을 모은다
    Then: 인용이 하나도 잡히지 않는다
    """
    # Given
    (docs_root / excluded / "a.md").write_text(f"`storage/results/{FAKE_DIR_A}/`\n", encoding="utf-8")

    # When
    cited = cited_result_dirs(docs_root)

    # Then
    assert cited == set()


def test_missing_citations_finds_gone_folder(docs_root: Path, results_root: Path) -> None:
    """
    목적: 인용됐는데 실재하지 않는 폴더를 잡는다 (품질 검증이 쓰는 방향)

    Given: 두 폴더를 인용하는 문서와, 그중 하나만 있는 산출물 경로
    When: 끊긴 인용을 찾는다
    Then: 없는 폴더 하나만 나온다
    """
    # Given
    (docs_root / "research" / "a.md").write_text(
        f"`storage/results/{FAKE_DIR_A}/` 와 `storage/results/{FAKE_DIR_B}/`\n", encoding="utf-8"
    )
    (results_root / FAKE_DIR_A).mkdir()

    # When
    missing = missing_citations(docs_root, results_root)

    # Then
    assert missing == [FAKE_DIR_B]


def test_unreferenced_dirs_finds_orphan(docs_root: Path, results_root: Path) -> None:
    """
    목적: 실재하지만 아무도 인용하지 않는 폴더를 잡는다 (정리 도구가 쓰는 방향)

    Given: 한 폴더만 인용하는 문서와, 두 폴더가 있는 산출물 경로
    When: 인용되지 않은 폴더를 찾는다
    Then: 인용되지 않은 폴더 하나만 나온다
    """
    # Given
    (docs_root / "research" / "a.md").write_text(f"`storage/results/{FAKE_DIR_A}/`\n", encoding="utf-8")
    (results_root / FAKE_DIR_A).mkdir()
    (results_root / FAKE_DIR_B).mkdir()

    # When
    unreferenced = unreferenced_dirs(docs_root, results_root)

    # Then
    assert unreferenced == [FAKE_DIR_B]


def test_existing_result_dirs_ignores_files(results_root: Path) -> None:
    """
    목적: 산출물 부모 경로의 파일은 폴더로 세지 않는다

    `meta.json` 이 같은 자리에 있으므로 파일을 걸러야 한다.

    Given: 폴더 하나와 파일 하나가 있는 산출물 경로
    When: 실재하는 폴더를 모은다
    Then: 폴더만 잡힌다
    """
    # Given
    (results_root / FAKE_DIR_A).mkdir()
    (results_root / "meta.json").write_text("{}", encoding="utf-8")

    # When
    existing = existing_result_dirs(results_root)

    # Then
    assert existing == {FAKE_DIR_A}


def test_existing_result_dirs_on_missing_parent(tmp_path: Path) -> None:
    """
    목적: 산출물 경로가 아직 없어도 예외 없이 빈 집합을 낸다 (경계 조건)

    한 번도 검증을 돌리지 않은 저장소에서 품질 검증이 깨지면 안 된다.

    Given: 존재하지 않는 산출물 경로
    When: 실재하는 폴더를 모은다
    Then: 빈 집합이 나온다
    """
    # Given
    absent = tmp_path / "does_not_exist"

    # When
    existing = existing_result_dirs(absent)

    # Then
    assert existing == set()


def test_real_documents_cite_existing_dirs() -> None:
    """
    목적: 이 저장소의 문서가 인용한 산출물 폴더가 전부 실재한다

    **인용한 폴더를 지우는 순간 이 테스트가 실패한다.** 그것이 이 테스트의 존재 이유다.
    없앤 산출물은 인용과 같은 줄에 묘비 낱말(`없음`·`삭제`·`제거`)을 달아 표기한다.

    `tests/CLAUDE.md` §5 의 「`storage/` 실경로 접근 금지」에 대한 좁은 예외다 —
    파일을 열지도 쓰지도 않고 **폴더 이름의 실재만** 본다.

    Given: 저장소의 실제 문서와 산출물 경로
    When: 끊긴 인용을 찾는다
    Then: 하나도 없다
    """
    # Given / When
    missing = missing_citations(DOCS_DIR, RESULTS_DIR)

    # Then
    assert missing == [], f"문서가 인용한 산출물 폴더가 없다: {missing}"
