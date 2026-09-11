"""문서와 산출물 폴더 사이의 인용 계약을 고정한다.

결과 문서는 수치의 근거로 산출물 폴더를 인용한다. **인용한 폴더가 사라지면 문서는
대조할 수 없는 숫자만 남는다** — 실제로 그 상태의 문서가 8개 쌓인 적이 있다.

두 방향을 함께 고정한다. 판정이 갈라지면 정리 도구가 「지워도 된다」고 한 폴더를
품질 검증이 요구하는 상태가 되기 때문이다.
"""

from pathlib import Path

import pytest

from verify_lab.common_constants import (
    BASE_DIR,
    RESULT_LAYER_PROBE,
    RESULT_LAYER_STRATEGY,
    RESULT_LAYER_STUDY,
    RESULTS_DIR,
)
from verify_lab.utils.result_citations import (
    cited_result_dirs,
    existing_result_dirs,
    missing_citations,
    result_dir_paths,
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

    `<실행시각>_reverse` 은 「산출물이 생기는 위치」를 말하는 자리라
    실재를 요구하면 안 된다.

    Given: 자리표시자만 적힌 문서
    When: 인용을 모은다
    Then: 인용이 하나도 잡히지 않는다
    """
    # Given
    (docs_root / "research" / "a.md").write_text(
        "산출물은 `storage/results/검증/<실행시각>_reverse/` 에 남습니다.\n", encoding="utf-8"
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


@pytest.mark.parametrize("layer", [RESULT_LAYER_STUDY, RESULT_LAYER_STRATEGY, RESULT_LAYER_PROBE])
def test_existing_result_dirs_finds_layer_subfolders(results_root: Path, layer: str) -> None:
    """
    목적: 계층 하위 폴더 안의 산출물을 실재로 센다 (새 자리).

    산출물이 `검증`·`매매`·`실측` 아래로 들어가면서 한 단계 깊어졌다. 탐색이 루트 직하만
    보면 **품질 검증이 살아있는 근거물을 「없다」고 보고한다.**

    Given: 계층 폴더 아래의 산출물 폴더
    When: 실재하는 폴더를 모은다
    Then: 계층 이름이 아니라 산출물 폴더 이름이 잡힌다
    """
    # Given
    (results_root / layer / FAKE_DIR_A).mkdir(parents=True)

    # When
    existing = existing_result_dirs(results_root)

    # Then
    assert existing == {FAKE_DIR_A}


def test_existing_result_dirs_finds_both_layouts(results_root: Path) -> None:
    """
    목적: **옛 자리와 새 자리를 동시에** 본다 (회귀).

    기존 산출물은 루트 직하에 남고 새 산출물만 계층 폴더로 들어가므로 **두 구조가 공존한다.**
    한쪽만 보면 다른 쪽이 시야에서 사라진다.

    Given: 루트 직하 폴더 하나와 계층 폴더 아래 폴더 하나
    When: 실재하는 폴더를 모은다
    Then: 둘 다 잡힌다
    """
    # Given
    (results_root / FAKE_DIR_A).mkdir()
    (results_root / RESULT_LAYER_STRATEGY / FAKE_DIR_B).mkdir(parents=True)

    # When
    existing = existing_result_dirs(results_root)

    # Then
    assert existing == {FAKE_DIR_A, FAKE_DIR_B}


def test_layer_folder_itself_is_not_a_result_dir(results_root: Path) -> None:
    """
    목적: 계층 폴더 자체를 산출물로 세지 않는다 (경계 조건).

    계층 폴더를 산출물로 세면 **정리 도구가 그것을 「인용되지 않은 폴더」로 뽑아 통째로 지운다.**

    Given: 산출물이 하나도 없는 빈 계층 폴더
    When: 실재하는 폴더를 모은다
    Then: 빈 집합이다
    """
    # Given
    (results_root / RESULT_LAYER_STUDY).mkdir()

    # When
    existing = existing_result_dirs(results_root)

    # Then
    assert existing == set()


def test_result_dir_paths_keeps_the_location(results_root: Path) -> None:
    """
    목적: 이름만이 아니라 **경로**를 돌려준다 (정리 도구가 쓰는 방향).

    `clean_results.py` 가 이름만 받아 `RESULTS_DIR / name` 으로 되돌려 쓰고 있었다.
    계층 폴더가 끼면 그 경로는 존재하지 않는데 **`rglob` 이 빈 결과를 내 용량이 `0.0MB`** 로
    나오고 예외도 나지 않는다. 경로를 잃지 않는 것이 유일한 방어다.

    Given: 두 자리에 각각 있는 산출물 폴더
    When: 이름 → 경로 대응을 모은다
    Then: 각 이름이 실재하는 경로를 가리킨다
    """
    # Given
    (results_root / FAKE_DIR_A).mkdir()
    (results_root / RESULT_LAYER_STRATEGY / FAKE_DIR_B).mkdir(parents=True)

    # When
    paths = result_dir_paths(results_root)

    # Then
    assert paths[FAKE_DIR_A] == [results_root / FAKE_DIR_A]
    assert paths[FAKE_DIR_B] == [results_root / RESULT_LAYER_STRATEGY / FAKE_DIR_B]


def test_same_name_in_two_layers_returns_both(results_root: Path) -> None:
    """
    목적: 한 이름이 두 계층에 있어도 **예외를 던지지 않고 둘 다 돌려준다** (경계 조건).

    측정과 매매가 같은 slug 를 쓰는 것이 이 저장소의 규약이라(목표 1), 같은 초에 두 계층을
    돌리면 `검증/<시각>_X` 와 `매매/<시각>_X` 가 함께 생긴다 —
    `test_report_writer.test_same_track_splits_by_layer` 가 그것을 정상으로 고정한다.
    **여기서 예외를 던지면 인용 판정 전체가 멈춰 품질 검증과 정리 도구가 동시에 죽는다.**

    Given: 두 계층에 같은 이름의 폴더
    When: 이름 → 경로 대응을 모은다
    Then: 그 이름에 경로 둘이 달려 있다
    """
    # Given
    (results_root / RESULT_LAYER_STUDY / FAKE_DIR_A).mkdir(parents=True)
    (results_root / RESULT_LAYER_STRATEGY / FAKE_DIR_A).mkdir(parents=True)

    # When
    paths = result_dir_paths(results_root)

    # Then
    assert sorted(paths[FAKE_DIR_A]) == sorted(
        [results_root / RESULT_LAYER_STUDY / FAKE_DIR_A, results_root / RESULT_LAYER_STRATEGY / FAKE_DIR_A]
    )


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

    **`docs/` 가 아니라 저장소 전체를 훑는다.** 루트 `CLAUDE.md` 가 실제로 산출물을 인용하고
    있어서 `docs/` 만 보면 그 인용을 놓친다 — 그러면 정리 도구가 근거물을 삭제 후보로 낸다.

    `tests/CLAUDE.md` §5 의 「`storage/` 실경로 접근 금지」에 대한 좁은 예외다 —
    파일을 열지도 쓰지도 않고 **폴더 이름의 실재만** 본다.

    Given: 저장소의 실제 문서와 산출물 경로
    When: 끊긴 인용을 찾는다
    Then: 하나도 없다
    """
    # Given / When
    missing = missing_citations(BASE_DIR, RESULTS_DIR)

    # Then
    assert missing == [], f"문서가 인용한 산출물 폴더가 없다: {missing}"


def test_citation_outside_docs_is_counted(tmp_path: Path) -> None:
    """
    목적: **`docs/` 밖의 마크다운이 인용한 폴더도 지킨다**

    루트 `CLAUDE.md` 가 실제로 산출물 두 개를 인용하고 있었다. 스캔 루트가 `docs/` 면
    그 인용이 보이지 않아 **품질 검증은 통과하고 정리 도구는 삭제 후보로 낸다** —
    이 모듈이 막겠다고 한 「두 판정이 갈라진다」의 거울상이다.

    Given: 저장소 루트의 `CLAUDE.md` 만 폴더를 인용하는 트리
    When: 저장소 전체를 훑는다
    Then: 그 폴더가 인용으로 잡힌다
    """
    # Given
    (tmp_path / "docs").mkdir()
    (tmp_path / "CLAUDE.md").write_text(f"근거는 `storage/results/매매/{FAKE_DIR_A}/성적표.csv` 에 있습니다.\n", encoding="utf-8")

    # When
    cited = cited_result_dirs(tmp_path)

    # Then
    assert cited == {FAKE_DIR_A}


def test_real_repository_keeps_seeing_the_old_layout() -> None:
    """
    목적: 계층 폴더를 도입해도 **옛 자리의 산출물이 시야에서 빠지지 않는다** (회귀).

    기존 산출물은 옮기지 않기로 했다 — 살아있는 문서 여럿이 그 이름을 인용하고 있어
    옮기면 전부 깨진다. 그래서 두 구조가 공존하며, **그것이 의도다.** 탐색이 새 자리만
    보게 되면 품질 검증이 근거물을 「없다」고 보고한다.

    개수를 박지 않는다 — 실행할 때마다 폴더가 늘어 값이 낡는다. 대신 **루트 직하에 실제로
    있는 것과 탐색 결과를 대조**한다.

    `tests/CLAUDE.md` §5 의 「폴더의 실재만 보는 검사」 예외에 해당한다.

    Given: 저장소의 실제 산출물 경로
    When: 루트 직하의 폴더 이름을 직접 세고, 탐색 결과와 비교한다
    Then: 직하의 폴더가 전부 탐색 결과에 들어 있다
    """
    # Given
    layers = {RESULT_LAYER_STUDY, RESULT_LAYER_STRATEGY, RESULT_LAYER_PROBE}
    at_root = {child.name for child in RESULTS_DIR.iterdir() if child.is_dir() and child.name not in layers}

    # When
    found = existing_result_dirs(RESULTS_DIR)

    # Then
    assert at_root <= found, f"옛 자리의 산출물이 탐색에서 빠졌습니다: {sorted(at_root - found)}"
