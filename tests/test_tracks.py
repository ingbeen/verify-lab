"""매매법 이름표와 등급 레지스트리(`verify_lab.tracks`)의 계약을 검사한다.

이 레지스트리는 **산출물이 어느 폴더에 쌓이는지의 유일한 SoT** 다. 등급을 스크립트가 박아
넘기면 폴더를 손으로 옮겨도 다음 실행이 되돌리므로, 승격·강등이 한 줄 변경으로 끝나려면
선언할 자리가 하나여야 한다.

검사하는 것은 다섯이다.

1. 식별자가 유일한가 (slug·한글 이름)
2. 등급과 종류가 선언된 값인가
3. **한글 이름이 폴더 이름으로 쓸 수 있는 모양인가** — 산출물 폴더 이름이 이 값이고
   그 폴더를 `rmtree` 로 비우므로, 경로 구분자가 섞이면 산출물 루트 밖을 겨눠 지운다
4. 코드에 있는 매매법이 전부 등록됐는가 (`studies/<slug>/constants.py` 의 `TRACK_NAME`)
5. 그 이름이 `docs/INDEX.md` 이름표와 같은가

3·4·5 가 이 파일의 핵심이다. **레지스트리가 코드·문서와 갈라지면 예외가 나지 않는다** —
산출물만 조용히 다른 자리에 쌓인다.
"""

import re
from pathlib import Path

import pytest

from verify_lab.tracks import (
    GRADE_STUDY,
    GRADE_SURVEY,
    GRADE_TRADING,
    GRADES,
    KIND_METHOD,
    KIND_PROPERTY,
    KINDS,
    TRACKS,
    Track,
    track_of,
    tracks_of_kind,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STUDIES_DIR = PROJECT_ROOT / "src" / "verify_lab" / "studies"
INDEX_PATH = PROJECT_ROOT / "docs" / "INDEX.md"

# slug 의 모양. 코드에서 매매법을 부르는 이름이라 영소문자와 밑줄만 쓴다
SLUG_SHAPE = re.compile(r"^[a-z][a-z_]*$")

# 한글 이름의 모양. **산출물 폴더 이름이 이 값**이므로 slug 와 요구가 다르다 —
# 한글과 대문자를 허용하되 경로 구분자·점·공백은 막는다.
# 정의처는 `report/writer.py` 의 `TRACK_LABEL_PATTERN` 이고 여기서는 레지스트리에 든 값이
# 그 모양인지만 본다
LABEL_SHAPE = re.compile(r"^[A-Za-z가-힣][0-9A-Za-z가-힣_]*$")

# 폴더 이름에 절대 들어가면 안 되는 조각. **폴더를 비우므로** 이것이 섞이면 지우는 자리가 바뀐다
PATH_ESCAPES = ("/", "\\", "..", " ")

# `studies/<slug>/constants.py` 에서 slug 를 뽑는다
TRACK_NAME_ASSIGNMENT = re.compile(r"^TRACK_NAME\s*:\s*Final\s*=\s*\"([^\"]+)\"", re.MULTILINE)


def _declared_track_names() -> dict[str, Path]:
    """검증 패키지가 선언한 slug 를 모은다.

    Returns:
        slug → 그 값을 선언한 `constants.py` 경로
    """
    declared: dict[str, Path] = {}
    for constants_path in sorted(STUDIES_DIR.glob("*/constants.py")):
        match = TRACK_NAME_ASSIGNMENT.search(constants_path.read_text(encoding="utf-8"))
        if match:
            declared[match.group(1)] = constants_path
    return declared


class TestRegistryShape:
    """레지스트리 자체의 불변조건."""

    def test_slug이_유일하다(self) -> None:
        """
        목적: slug 가 폴더 이름 전체이므로 겹치면 두 매매법이 한 자리를 쓴다.

        Given: 레지스트리 전체
        When: slug 를 모은다
        Then: 중복이 없다
        """
        # Given / When
        slugs = [track.slug for track in TRACKS]

        # Then
        assert len(slugs) == len(set(slugs)), f"slug 가 겹칩니다: {sorted(slugs)}"

    def test_한글_이름이_유일하다(self) -> None:
        """
        목적: 한글 이름이 문서 폴더 이름이 되므로 겹치면 두 매매법의 문서가 섞인다.

        Given: 레지스트리 전체
        When: 한글 이름을 모은다
        Then: 중복이 없다
        """
        # Given / When
        labels = [track.label for track in TRACKS]

        # Then
        assert len(labels) == len(set(labels)), f"한글 이름이 겹칩니다: {sorted(labels)}"

    @pytest.mark.parametrize("track", TRACKS, ids=lambda track: track.slug)
    def test_slug이_폴더_이름으로_쓸_수_있는_모양이다(self, track: Track) -> None:
        """
        목적: slug 가 폴더 이름 전체이므로 `../` 나 `/` 가 섞이면 산출물 루트 밖을 겨눈다.

        Given: 레지스트리의 한 줄
        When: slug 의 모양을 본다
        Then: 영소문자와 밑줄로만 이루어져 있다
        """
        # Given / When / Then
        assert SLUG_SHAPE.match(track.slug), f"slug 모양이 맞지 않습니다: {track.slug}"

    @pytest.mark.parametrize("track", TRACKS, ids=lambda track: track.slug)
    def test_한글_이름이_폴더_이름으로_쓸_수_있는_모양이다(self, track: Track) -> None:
        """
        목적: **산출물 폴더 이름이 이 값**이고 그 폴더를 `rmtree` 로 비운다.

        slug 와 요구가 다르다 — 한글과 대문자를 써야 하므로 slug 패턴을 쓸 수 없고,
        그렇다고 아무 문자나 허용하면 `../` 가 섞였을 때 **산출물 루트 밖을 겨눠 지운다.**

        Given: 레지스트리의 한 줄
        When: 한글 이름의 모양을 본다
        Then: 한글·영숫자·밑줄로만 이루어져 있고 경로 조각이 섞이지 않았다
        """
        # Given / When / Then
        assert LABEL_SHAPE.match(track.label), f"한글 이름 모양이 맞지 않습니다: {track.label}"

        found = [piece for piece in PATH_ESCAPES if piece in track.label]
        assert not found, f"{track.label}: 폴더 이름에 쓸 수 없는 조각이 있습니다 {found}"

    @pytest.mark.parametrize("track", TRACKS, ids=lambda track: track.slug)
    def test_등급과_종류가_선언된_값이다(self, track: Track) -> None:
        """
        목적: 오타를 통과시키면 **예외 없이 새 상위 폴더가 생긴다.**

        Given: 레지스트리의 한 줄
        When: 등급과 종류를 본다
        Then: 각각 선언된 목록 안에 있다
        """
        # Given / When / Then
        assert track.grade in GRADES, f"{track.slug}: 알 수 없는 등급 {track.grade}"
        assert track.kind in KINDS, f"{track.slug}: 알 수 없는 종류 {track.kind}"

    def test_등급과_종류의_값이_서로_겹치지_않는다(self) -> None:
        """
        목적: 두 축이 같은 문자열을 쓰면 **잘못된 축에서 가져와도 값이 나와** 조용히 갈린다.

        Given: 등급 목록과 종류 목록
        When: 교집합을 본다
        Then: 비어 있다
        """
        # Given / When
        overlap = set(GRADES) & set(KINDS)

        # Then
        assert not overlap, f"등급과 종류가 같은 값을 씁니다: {sorted(overlap)}"

    def test_세_등급이_모두_쓰인다(self) -> None:
        """
        목적: 쓰이지 않는 등급은 폴더 규칙에서 빠진 것인지 아직 안 쓴 것인지 구별되지 않는다.

        Given: 레지스트리 전체
        When: 등급 목록과 실제 쓰인 등급을 견준다
        Then: 선언된 등급이 전부 목록 안에 있다 (빈 등급이 있어도 선언은 유지된다)
        """
        # Given / When
        used = {track.grade for track in TRACKS}

        # Then
        assert used <= set(GRADES), f"선언되지 않은 등급이 쓰였습니다: {sorted(used - set(GRADES))}"
        assert GRADE_TRADING in used, "매매 등급인 매매법이 하나도 없습니다"
        assert GRADE_SURVEY in used, "조사 등급인 트랙이 하나도 없습니다"


class TestRegistryLookup:
    """조회 함수의 계약."""

    def test_등록된_slug의_등급을_돌려준다(self) -> None:
        """
        목적: 산출물 폴더가 이 값에서만 정해진다.

        Given: 레지스트리에 있는 slug
        When: track_of 로 조회해 등급을 읽는다
        Then: 그 줄의 등급이 나온다
        """
        # Given
        track = TRACKS[0]

        # When
        grade = track_of(track.slug).grade

        # Then
        assert grade == track.grade

    def test_모르는_slug은_거부한다(self) -> None:
        """
        목적: 오타를 통과시키면 **선언되지 않은 자리에 산출물이 조용히 쌓인다.**

        Given: 레지스트리에 없는 slug
        When: track_of 로 조회한다
        Then: ValueError 가 난다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="등록되지 않은"):
            track_of("nonexistent_track")

    def test_track_of가_같은_줄을_돌려준다(self) -> None:
        """
        목적: 등급만이 아니라 한글 이름도 같은 자리에서 나와야 두 벌이 되지 않는다.

        Given: 레지스트리에 있는 slug
        When: track_of 로 조회한다
        Then: 그 줄 자체가 나온다
        """
        # Given
        track = TRACKS[0]

        # When
        found = track_of(track.slug)

        # Then
        assert found is track

    def test_종류로_거를_수_있다(self) -> None:
        """
        목적: 「매매법이면 성적표를 낸다」는 계약을 걸려면 그 목록을 얻을 수 있어야 한다.

        Given: 레지스트리 전체
        When: 매매법 종류로 거른다
        Then: 결과가 비어 있지 않고 전부 그 종류다
        """
        # Given / When
        methods = tracks_of_kind(KIND_METHOD)

        # Then
        assert methods, "매매법 종류의 트랙이 하나도 없습니다"
        assert all(track.kind == KIND_METHOD for track in methods)


class TestRegistryMatchesCode:
    """레지스트리가 실제 코드·문서와 갈라지지 않는다."""

    def test_검증_패키지의_slug이_전부_등록돼_있다(self) -> None:
        """
        목적: 등록되지 않은 slug 로 실행하면 **어느 등급 폴더에 쌓을지 정할 수 없다.**

        Given: `studies/<slug>/constants.py` 가 선언한 TRACK_NAME 전부
        When: 레지스트리와 견준다
        Then: 빠진 것이 없다
        """
        # Given
        declared = _declared_track_names()
        assert declared, "검증 패키지에서 TRACK_NAME 을 하나도 찾지 못했습니다"

        # When
        registered = {track.slug for track in TRACKS}
        missing = {slug: path for slug, path in declared.items() if slug not in registered}

        # Then
        listed = ", ".join(f"{slug} ({path.parent.name})" for slug, path in sorted(missing.items()))
        assert not missing, f"레지스트리에 없는 매매법이 있습니다: {listed}"

    def test_코드가_있는_매매법은_INDEX_이름표에_한글_이름이_있다(self) -> None:
        """
        목적: 코드 slug 와 문서 한글 이름을 잇는 다리가 두 벌이 되면 한쪽이 낡는다.

        Given: `studies/` 에 패키지가 있는 slug 의 한글 이름
        When: docs/INDEX.md 본문을 본다
        Then: 그 이름이 들어 있다
        """
        # Given
        declared = _declared_track_names()
        index_text = INDEX_PATH.read_text(encoding="utf-8")

        # When
        missing = [track_of(slug).label for slug in sorted(declared) if track_of(slug).label not in index_text]

        # Then
        assert not missing, f"docs/INDEX.md 이름표에 없는 한글 이름: {missing}"


class TestGradeSemantics:
    """등급이 뜻하는 것을 고정한다."""

    def test_월말_진입은_매매_등급이다(self) -> None:
        """
        목적: **등급은 「상태」다** — 검증은 진행 중, 매매는 걸기로 정한 것.

        월말 진입은 2026-09-21 에 **대상 달(9월 아래)과 손절선(기초자산 −5%)이 확정**돼
        `docs/매매/월말_진입/규칙.md` §1 이 권고안이 아니라 확정 규칙이 됐다.
        **승격은 이 한 줄을 바꾸는 것이고 성적 계산은 그대로다.**

        Given: 레지스트리
        When: 월말 진입의 등급을 조회한다
        Then: 매매다
        """
        # Given / When / Then
        assert track_of("month_end").grade == GRADE_TRADING

    def test_조사_등급은_종류도_조사다(self) -> None:
        """
        목적: 성적표를 낼 수 없는 것이 매매법 계약을 요구받으면 안 된다.

        Given: 레지스트리 전체
        When: 조사 등급인 줄을 고른다
        Then: 종류가 전부 성질 조사다
        """
        # Given / When
        surveys = [track for track in TRACKS if track.grade == GRADE_SURVEY]

        # Then
        wrong = [track.slug for track in surveys if track.kind != KIND_PROPERTY]
        assert not wrong, f"조사 등급인데 종류가 매매법입니다: {wrong}"

    def test_검증과_매매_등급은_전부_매매법이다(self) -> None:
        """
        목적: 「검증 = 매매법 후보」가 성립해야 승격이 폴더 이동으로 끝난다.

        Given: 레지스트리 전체
        When: 검증·매매 등급인 줄을 고른다
        Then: 종류가 전부 매매법이다
        """
        # Given / When
        graded = [track for track in TRACKS if track.grade in (GRADE_STUDY, GRADE_TRADING)]

        # Then
        wrong = [track.slug for track in graded if track.kind != KIND_METHOD]
        assert not wrong, f"검증·매매 등급인데 종류가 매매법이 아닙니다: {wrong}"
