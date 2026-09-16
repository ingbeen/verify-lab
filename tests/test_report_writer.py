"""검증 산출물 저장의 계약을 고정한다.

**산출물은 매매법당 한 폴더에만 쌓이고 재실행이 그 자리를 덮는다.** 같은 소스로 다시 돌리면
결과가 바이트 단위로 같으므로, 실행마다 폴더를 새로 만들면 이름만 다른 사본이 무한히 쌓인다.

그래서 이 모듈이 고정하는 계약은 셋이다 — **이름은 매매법 이름 하나**, **두 번 불러도 같은 자리**,
**쓰기 전에 그 자리를 비운다.** 셋째가 없으면 옛 실행의 파일이 남아 한 폴더에서 두 실행이 섞이고
**예외는 나지 않는다.**

**테스트는 실제 `storage/` 를 건드리지 않는다.** 경로 상수를 import 시점에 캡처하는 모듈까지
함께 패치해야 격리가 성립한다.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from verify_lab import common_constants
from verify_lab.report import writer
from verify_lab.report.constants import RUN_SUMMARY_FILENAME, SIGNALS_FILENAME
from verify_lab.tracks import GRADE_SURVEY, GRADE_TRADING, KIND_METHOD, Track, track_of

TRACK_NAME = "reverse"

# **같은 등급의 다른 매매법**이어야 「비우기가 그 폴더 안에만 미친다」를 잴 수 있다.
# 등급이 다르면 부모가 달라 애초에 서로 닿지 않으므로 규칙이 깨져도 통과한다
OTHER_TRACK_NAME = "option_expiry"

# 등급이 다른 매매법. **같은 등급 둘만으로는 「등급이 상위 폴더가 된다」를 고정할 수 없다** —
# 부모가 늘 같아 규칙이 깨져도 통과한다
SURVEY_TRACK_NAME = "leverage_tracking"


@pytest.fixture
def mock_results_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """검증 산출물 경로를 임시 디렉터리로 격리한다.

    `writer` 는 `from ... import RESULTS_DIR` 로 import 시점에 경로를 자기 모듈에 캡처한다.
    `common_constants` 만 패치하면 이미 캡처된 실제 경로가 그대로 쓰인다.
    """
    results_dir = tmp_path / "results"

    monkeypatch.setattr(common_constants, "RESULTS_DIR", results_dir)
    monkeypatch.setattr(writer, "RESULTS_DIR", results_dir)

    return results_dir


def test_directory_name_is_the_korean_label(mock_results_dir: Path) -> None:
    """
    목적: 결과 폴더 이름이 **그 매매법의 한글 이름 하나**임을 고정한다.

    **사용자가 여는 것은 산출물 폴더**인데 그 이름이 코드 식별자(slug)면 문서와 대조할 때마다
    번역해야 한다. 한글 이름을 쓰면 `docs/<등급>/<이름>/` 과 자리가 그대로 맞는다.

    **실행 시각을 붙이지 않는다.** 같은 소스로 재실행하면 산출물이 바이트 단위로 같으므로,
    시각을 붙이면 **내용이 같고 이름만 다른 폴더**가 실행할 때마다 쌓인다.
    **등급 접미사도 붙이지 않는다** — 등급은 상위 폴더가 말하므로 이름에 또 넣으면 중복이다.

    Given: 매매법 slug
    When: 결과 폴더를 만든다
    Then: 폴더 이름이 레지스트리의 한글 이름과 정확히 같다
    """
    # When
    directory = writer.create_run_directory(TRACK_NAME)

    # Then
    assert directory.name == track_of(TRACK_NAME).label


def test_directory_name_is_not_the_slug(mock_results_dir: Path) -> None:
    """
    목적: 한글 이름을 쓴다는 계약을 **반대쪽에서도** 고정한다 (경계 조건).

    위 테스트만 두면 `label` 을 slug 와 같은 값으로 바꾸는 것만으로 통과한다.
    둘이 실제로 다른 매매법에서 재야 계약이 닫힌다.

    Given: slug 와 한글 이름이 다른 매매법
    When: 결과 폴더를 만든다
    Then: 폴더 이름이 slug 가 아니다
    """
    # Given
    assert track_of(TRACK_NAME).label != TRACK_NAME, "이 테스트는 slug 와 한글 이름이 다른 매매법이 필요합니다"

    # When
    directory = writer.create_run_directory(TRACK_NAME)

    # Then
    assert directory.name != TRACK_NAME


def test_same_track_reuses_the_same_directory(mock_results_dir: Path) -> None:
    """
    목적: 같은 매매법·같은 계층을 두 번 불러도 **같은 자리**임을 고정한다 (목표 2 의 집행).

    이것이 「재실행해도 변화가 없다」의 뿌리다. 자리가 매번 달라지면 산출물이 같아도
    git 에는 새 폴더가 통째로 추가된 것으로 보인다.

    Given: 같은 매매법 이름과 같은 계층
    When: 결과 폴더를 두 번 만든다
    Then: 두 경로가 같다
    """
    # When
    first = writer.create_run_directory(TRACK_NAME)
    second = writer.create_run_directory(TRACK_NAME)

    # Then
    assert first == second


def test_previous_files_are_cleared(mock_results_dir: Path) -> None:
    """
    목적: 쓰기 전에 그 폴더를 **비운다**를 고정한다.

    덮어쓰기는 파일 단위라 이번 실행이 내지 않는 파일은 그대로 남는다. 대상을 좁혀 돌리면
    이번에 내지 않는 대상의 파일이 남으므로, 비우지 않으면 **한 폴더에 두 실행의
    파일이 섞이고 예외는 나지 않는다.**

    Given: 옛 실행의 파일이 남아 있는 결과 폴더
    When: 같은 매매법으로 결과 폴더를 다시 만든다
    Then: 그 파일이 사라진다
    """
    # Given
    directory = writer.create_run_directory(TRACK_NAME)
    stale = directory / "옛_산출물.csv"
    stale.write_text("옛 실행의 파일", encoding="utf-8")

    # When
    writer.create_run_directory(TRACK_NAME)

    # Then
    assert not stale.exists()


def test_clearing_keeps_other_tracks_in_the_layer(mock_results_dir: Path) -> None:
    """
    목적: 비우기가 **그 매매법 폴더 안에만** 미친다를 고정한다 (경계 조건).

    계층 폴더까지 비우면 한 매매법을 돌릴 때마다 같은 계층의 다른 매매법 산출물이
    통째로 사라진다. 검증 여섯을 잇달아 돌리는 것이 이 저장소의 관용이라 **마지막 하나만
    남는다** — 그리고 예외는 나지 않는다.

    Given: 같은 계층에 다른 매매법의 산출물이 있다
    When: 한 매매법의 결과 폴더를 다시 만든다
    Then: 다른 매매법의 파일이 그대로 있다
    """
    # Given
    other = writer.create_run_directory(OTHER_TRACK_NAME)
    kept = other / SIGNALS_FILENAME
    kept.write_text("다른 매매법의 산출물", encoding="utf-8")

    # When
    writer.create_run_directory(TRACK_NAME)

    # Then
    assert kept.exists()


@pytest.mark.parametrize("track_name", [TRACK_NAME, SURVEY_TRACK_NAME])
def test_grade_becomes_the_parent_folder(mock_results_dir: Path, track_name: str) -> None:
    """
    목적: 등급이 **경로**로 드러나는 것을 고정한다.

    등급은 폴더 이름에 접미사로 붙이지 않고 상위 폴더가 말한다. 이 계약이 무너지면
    등급이 다른 산출물이 한 자리에 섞여 폴더 목록만 봐서는 구별되지 않는다.

    Given: 레지스트리에 등록된 매매법 이름
    When: 결과 폴더를 만든다
    Then: 산출물 루트 바로 아래 **그 매매법의 등급 폴더**가 부모다
    """
    # When
    directory = writer.create_run_directory(track_name)

    # Then
    assert directory.parent == mock_results_dir / track_of(track_name).grade


def test_grade_comes_from_the_registry_not_the_caller(mock_results_dir: Path) -> None:
    """
    목적: **등급을 호출 측이 고를 수 없음**을 고정한다 (승격이 한 줄로 끝나는 근거).

    호출 측이 등급을 넘길 수 있으면 레지스트리가 SoT 가 아니게 되고, 폴더를 손으로 옮겨도
    다음 실행이 원래 자리에 다시 만든다. 그래서 `create_run_directory` 는 이름만 받는다.

    Given: 등급이 다른 두 매매법
    When: 각각 결과 폴더를 만든다
    Then: 부모 폴더가 각자의 등급이고 서로 다르다
    """
    # When
    trading = writer.create_run_directory(TRACK_NAME)
    survey = writer.create_run_directory(SURVEY_TRACK_NAME)

    # Then
    assert trading.parent.name == GRADE_TRADING
    assert survey.parent.name == GRADE_SURVEY


def test_directory_is_created(mock_results_dir: Path) -> None:
    """
    목적: 폴더가 실제로 만들어진다 (계층 폴더까지 함께).

    Given: 아직 없는 결과 경로
    When: 결과 폴더를 만든다
    Then: 디렉터리가 존재한다
    """
    # When
    directory = writer.create_run_directory(TRACK_NAME)

    # Then
    assert directory.is_dir()


def test_rejects_blank_track_name(mock_results_dir: Path) -> None:
    """
    목적: 매매법 이름이 비면 **계층 폴더 자신이 산출물 폴더가 된다** (경계 조건).

    이름이 폴더 이름 전체이므로 빈 이름은 `검증/` 을 가리키고, 비우기가 그 계층의 산출물을
    통째로 지운다.

    Given: 공백 이름
    When: 결과 폴더를 만든다
    Then: ValueError
    """
    with pytest.raises(ValueError, match="매매법"):
        writer.create_run_directory("   ")


@pytest.mark.parametrize("bad_name", ["month_end_v2", "QQQ_expiry", "month-end", "월말", "../escape", "a/b", "."])
def test_rejects_track_name_outside_the_slug_shape(mock_results_dir: Path, bad_name: str) -> None:
    """
    목적: slug 모양을 벗어난 이름으로 폴더를 만들지 못하게 한다 (경계 조건).

    두 가지를 한꺼번에 막는다.

    1. **이름 규약** — 코드에서 매매법은 영문 slug 하나로 불린다(`docs/INDEX.md` §3 이름표).
       폴더 이름이 곧 그 slug 이므로 규약을 강제하는 자리가 여기다
    2. [중요] **경로 탈출** — 이름이 폴더 이름 «전체» 이고 그 폴더를 **비우므로**, `../` 나 `/`
       가 섞이면 산출물 루트 밖을 겨눠 **지운다.** 시각 접두어가 있던 때보다 위험이 커졌다

    Given: slug 모양이 아닌 매매법 이름
    When: 결과 폴더를 만든다
    Then: ValueError 이고, 그 이름의 폴더가 만들어지지 않았다
    """
    # When / Then
    with pytest.raises(ValueError, match="영소문자"):
        writer.create_run_directory(bad_name)

    # 검사가 «비우기보다 먼저» 일어나야 한다 — 나중이면 거부해도 이미 지운 뒤다
    assert not mock_results_dir.exists(), "거부했는데 산출물 루트가 만들어졌습니다"


def test_accepts_every_real_track_name() -> None:
    """
    목적: 위 검사가 **실제로 쓰는 이름을 막지 않는다**를 고정한다.

    거부 테스트만 두면 패턴을 지나치게 좁혀도 통과한다. 짝으로 둬서 저장소의 실제 slug 가
    전부 통과하는지 본다.

    [중요] **실측 프로브 이름도 함께 본다.** 그 셋도 `create_run_directory` 에 그대로 들어가는데
    `scripts/` 는 테스트 범위 밖이라, 여기서 빠지면 **새 프로브 이름이 검사를 통과한 채
    실행 시점에야 죽는다.**

    Given: 각 검증 패키지의 매매법 이름과 실측 스크립트의 프로브 이름
    When: 폴더 이름 검사 패턴에 맞춘다
    Then: 전부 통과한다
    """
    # Given
    from verify_lab.studies.futures_leverage.constants import TRACK_NAME as FUTURES
    from verify_lab.studies.leverage_tracking.constants import TRACK_NAME as LEVERAGE
    from verify_lab.studies.month_end.constants import TRACK_NAME as MONTH_END
    from verify_lab.studies.option_expiry.constants import TRACK_NAME as OPTION_EXPIRY
    from verify_lab.studies.reverse.constants import TRACK_NAME as REVERSE
    from verify_lab.studies.usdkrw_equivalence.constants import TRACK_NAME as EQUIVALENCE

    # 프로브 이름은 `scripts/data/check_*.py` 가 소유한다. 그 스크립트를 import 하면
    # pykrx 가 딸려 와 로그인을 시도하므로(계층 계약의 「지연 import」) 값만 옮겨 적는다
    probe_names = ["ecos_probe", "pykrx_etf_probe", "pykrx_splice_probe"]
    names = [REVERSE, OPTION_EXPIRY, MONTH_END, EQUIVALENCE, LEVERAGE, FUTURES, *probe_names]

    # When / Then
    unmatched = [name for name in names if not writer.VALID_TRACK_NAME.match(name)]
    assert unmatched == [], f"실제 매매법 이름이 폴더 이름 검사를 통과하지 못합니다: {unmatched}"


@pytest.mark.parametrize("bad_label", ["../탈출", "역방향/하위", "역방향\\하위", ".", "..", "역 방향", ""])
def test_rejects_label_outside_the_folder_shape(
    mock_results_dir: Path, monkeypatch: pytest.MonkeyPatch, bad_label: str
) -> None:
    """
    목적: **폴더 이름이 slug 에서 한글 이름으로 바뀌면서 검사 대상도 옮겨간다** (경계 조건).

    slug 검사만 두면 등록된 slug 를 넘겼을 때 **아무 검사 없이** 한글 이름이 폴더가 된다.
    그 폴더를 `rmtree` 로 비우므로 `../` 가 섞이면 **산출물 루트 밖을 겨눠 지운다.**
    slug 패턴을 그대로 쓸 수는 없다 — 한글과 대문자를 허용해야 하기 때문이다.

    Given: 폴더 이름으로 쓸 수 없는 한글 이름을 가진 레지스트리 줄
    When: 결과 폴더를 만든다
    Then: ValueError 이고, **산출물 루트가 만들어지지 않았다**
    """
    # Given
    broken = Track(slug=TRACK_NAME, label=bad_label, grade=GRADE_TRADING, kind=KIND_METHOD)
    monkeypatch.setattr(writer, "track_of", lambda _slug: broken)

    # When / Then
    with pytest.raises(ValueError, match="이름"):
        writer.create_run_directory(TRACK_NAME)

    # 검사가 «비우기보다 먼저» 일어나야 한다 — 나중이면 거부해도 이미 지운 뒤다
    assert not mock_results_dir.exists(), "거부했는데 산출물 루트가 만들어졌습니다"


def test_strips_whitespace_around_the_label(mock_results_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: **`track_name` 은 `strip()` 을 거치는데 `label` 은 레지스트리에서 바로 온다** (경계 조건).

    털지 않으면 `"역방향\n"` 이 그대로 폴더 이름이 된다 — 개행이 든 폴더는 셸에서 다루기
    어렵고, 같은 매매법이 두 자리에 쌓인다.

    Given: 앞뒤에 공백과 개행이 붙은 한글 이름
    When: 결과 폴더를 만든다
    Then: 털어낸 이름으로 만들어진다
    """
    # Given
    padded = Track(slug=TRACK_NAME, label=" 역방향\n", grade=GRADE_TRADING, kind=KIND_METHOD)
    monkeypatch.setattr(writer, "track_of", lambda _slug: padded)

    # When
    directory = writer.create_run_directory(TRACK_NAME)

    # Then
    assert directory.name == "역방향"


def test_rejects_newline_inside_the_label(mock_results_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: **`$` 는 끝의 개행 «앞»에서도 맞는다** — 그래서 `fullmatch` 로 잰다 (경계 조건).

    `re.match(r"^...$", "역방향\n악성")` 은 거부하지만 `"역방향\n"` 은 통과한다.
    털어내는 것만으로는 **가운데 개행**을 막지 못하므로 모양 검사가 끝까지 맞아야 한다.

    Given: 이름 가운데에 개행이 든 줄
    When: 결과 폴더를 만든다
    Then: ValueError 이고 산출물 루트가 만들어지지 않았다
    """
    # Given
    broken = Track(slug=TRACK_NAME, label="역방향\n악성", grade=GRADE_TRADING, kind=KIND_METHOD)
    monkeypatch.setattr(writer, "track_of", lambda _slug: broken)

    # When / Then
    with pytest.raises(ValueError, match="이름"):
        writer.create_run_directory(TRACK_NAME)

    assert not mock_results_dir.exists(), "거부했는데 산출물 루트가 만들어졌습니다"


def test_rejects_undeclared_grade(mock_results_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: **등급도 경로 한 조각이라 같은 강도로 본다** (경계 조건).

    `RESULTS_DIR / track.grade / label` 이므로 `grade` 에 `..` 이 들면 산출물 루트 밖을
    겨눠 지운다. 레지스트리 검사는 테스트 시점에만 걸리므로 **실행 시점을 막지 못한다** —
    한글 이름에 런타임 가드를 둔 것과 같은 이유로 여기도 둔다.

    Given: 선언되지 않은 등급을 가진 줄
    When: 결과 폴더를 만든다
    Then: ValueError 이고 산출물 루트가 만들어지지 않았다
    """
    # Given
    broken = Track(slug=TRACK_NAME, label="역방향", grade="..", kind=KIND_METHOD)
    monkeypatch.setattr(writer, "track_of", lambda _slug: broken)

    # When / Then
    with pytest.raises(ValueError, match="등급"):
        writer.create_run_directory(TRACK_NAME)

    assert not mock_results_dir.exists(), "거부했는데 산출물 루트가 만들어졌습니다"


def test_accepts_every_real_label() -> None:
    """
    목적: 한글 이름 검사가 **실제로 쓰는 이름을 막지 않는다**를 고정한다.

    거부 테스트만 두면 패턴을 지나치게 좁혀도 통과한다. 실측 프로브 이름(`ECOS_실측`·
    `pykrx_ETF_실측`)은 **대문자와 영문이 섞여** 있어 한글만 허용하는 패턴에서 조용히 막힌다.

    Given: 레지스트리의 모든 한글 이름
    When: 폴더 이름 검사 패턴에 맞춘다
    Then: 전부 통과한다
    """
    # Given
    from verify_lab.tracks import TRACKS

    # When / Then
    unmatched = [track.label for track in TRACKS if not writer.VALID_TRACK_LABEL.match(track.label)]
    assert unmatched == [], f"실제 한글 이름이 폴더 이름 검사를 통과하지 못합니다: {unmatched}"


def test_rejects_unregistered_track_name(mock_results_dir: Path) -> None:
    """
    목적: 레지스트리에 없는 매매법으로 폴더를 파지 못하게 한다 (경계 조건).

    **모양만 맞으면 통과하던 자리다.** 오타 하나가 통과하면 등급을 정할 수 없는데도
    폴더가 생기고, 산출물이 선언된 등급 밖으로 조용히 흩어진다.

    Given: slug 모양은 맞지만 등록되지 않은 이름
    When: 결과 폴더를 만든다
    Then: ValueError 이고, 산출물 루트가 만들어지지 않았다
    """
    # When / Then
    with pytest.raises(ValueError, match="등록되지 않은"):
        writer.create_run_directory("unregistered_track")

    assert not mock_results_dir.exists(), "거부했는데 산출물 루트가 만들어졌습니다"


def test_table_is_saved_without_index(tmp_path: Path) -> None:
    """
    목적: CSV 에 인덱스 컬럼이 섞이지 않는다. 섞이면 사용자가 여는 표에 의미 없는 열이 생긴다.

    Given: 2행짜리 표
    When: 저장한다
    Then: 첫 줄이 선언한 헤더 그대로다
    """
    # Given
    table = pd.DataFrame({"날짜": ["2026-01-05", "2026-01-06"], "평균(%)": [2.22, 3.33]})

    # When
    path = writer.save_table(tmp_path, SIGNALS_FILENAME, table)

    # Then
    assert path.read_text(encoding="utf-8-sig").splitlines()[0] == "날짜,평균(%)"


def test_table_is_saved_with_bom(tmp_path: Path) -> None:
    """
    목적: 한글 헤더가 엑셀에서 깨지지 않도록 BOM 을 붙인다 (기존 산출물 관용과 동일).

    Given: 한글 헤더를 가진 표
    When: 저장한다
    Then: 파일이 BOM 으로 시작한다
    """
    # Given
    table = pd.DataFrame({"구간": ["1일"]})

    # When
    path = writer.save_table(tmp_path, SIGNALS_FILENAME, table)

    # Then
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_rejects_empty_table(tmp_path: Path) -> None:
    """
    목적: 빈 표를 조용히 저장하지 않는다. 헤더만 있는 파일은 "결과가 없다"와 구분되지 않는다.

    Given: 행이 없는 표
    When: 저장한다
    Then: ValueError
    """
    with pytest.raises(ValueError, match="비어"):
        writer.save_table(tmp_path, SIGNALS_FILENAME, pd.DataFrame({"구간": []}))


def test_run_summary_keeps_parameters(tmp_path: Path) -> None:
    """
    목적: 실행 파라미터가 산출물 옆에 남는다. 남지 않으면 어떤 설정의 결과인지 재구성할 수 없다.

    Given: 시드와 반복 수를 담은 실행 정보
    When: 저장한다
    Then: JSON 에 그대로 남는다
    """
    # Given
    payload = {"study": TRACK_NAME, "seed": 0, "repeats": 1000}

    # When
    path = writer.save_run_summary(tmp_path, payload)

    # Then
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["seed"] == 0
    assert saved["repeats"] == 1000


def test_run_summary_uses_the_declared_filename(tmp_path: Path) -> None:
    """
    목적: 실행 정보 파일명을 고정한다 — 검증마다 이름이 달라지면 찾을 수 없다.

    Given: 실행 정보
    When: 저장한다
    Then: 선언된 파일명으로 저장된다
    """
    # When
    path = writer.save_run_summary(tmp_path, {"study": TRACK_NAME})

    # Then
    assert path.name == RUN_SUMMARY_FILENAME


class TestRunSummaryRejectsAbsolutePaths:
    """실행 요약은 **경로가 아니라 파일 이름**을 담는다 — 저장 시점에 막는다

    이 저장소는 mac·WSL 두 PC 전제이고 `storage/results/` 를 git 으로 동기화한다. 절대경로가
    산출물에 박히면 재현·대조가 그 PC 에 묶이고, 실제로 커밋된 `summary.json` 11개에 두 PC 의
    경로가 섞여 있었다.

    **판정이 테스트에만 있으면 production 은 여전히 그 값을 쓴다.** `save_run_summary` 는
    `summary.json` 을 쓰는 유일한 함수이므로(검증 여섯 · 매매 셋이 모두 여기를 지난다) 여기서
    막으면 아홉 개가 한 번에 덮이고, **앞으로 만들 검증도 자동으로 덮인다.**
    """

    def test_정상_요약은_그대로_저장된다(self, tmp_path: Path) -> None:
        """
        목적: 가드가 멀쩡한 요약을 막지 않는다.

        Given: 파일 이름만 담은 요약
        When: 저장한다
        Then: 예외 없이 저장된다
        """
        # Given
        payload = {"track": TRACK_NAME, "datasets": [{"file": "QQQ_max.csv", "rows": 6915}]}

        # When
        path = writer.save_run_summary(tmp_path, payload)

        # Then
        assert json.loads(path.read_text(encoding="utf-8")) == payload

    def test_절대경로가_있으면_저장하지_않는다(self, tmp_path: Path) -> None:
        """
        목적: 「조용히 저장되고 나중에 다른 PC 에서 발견되는」 경로를 닫는다.

        Given: 절대경로가 든 요약
        When: 저장한다
        Then: `ValueError` 이고 **파일이 만들어지지 않는다**
        """
        # Given
        payload = {"track": TRACK_NAME, "output_dir": "/Users/someone/verify-lab/storage/results"}

        # When / Then
        with pytest.raises(ValueError, match="절대경로"):
            writer.save_run_summary(tmp_path, payload)

        assert not (tmp_path / RUN_SUMMARY_FILENAME).exists(), "거부했는데 파일이 남았습니다"

    def test_중첩_두_단계_아래도_찾는다(self, tmp_path: Path) -> None:
        """
        목적: 얕게 훑으면 지나가는 자리를 막는다.

        실제 결함이 최상위 키에 있지 않았다 — 등가성 검증의 것은 `inputs.spot.close` 처럼
        **두 단계 아래**에 있었다.

        Given: 중첩된 자리에 절대경로가 든 요약
        When: 저장한다
        Then: `ValueError` 이고 **어느 자리인지** 메시지에 있다
        """
        # Given
        payload = {"inputs": {"spot": {"close": "/home/user/storage/series/USDKRW_CLOSE.csv"}}}

        # When / Then
        with pytest.raises(ValueError, match=r"inputs\.spot\.close"):
            writer.save_run_summary(tmp_path, payload)

    def test_사전의_키도_본다(self, tmp_path: Path) -> None:
        """
        목적: 값만 보면 절반을 놓친다.

        `row_counts` 는 **파일 이름으로 키잉**되므로 경로가 키 쪽에 박힐 수 있다.

        Given: 키가 절대경로인 요약
        When: 저장한다
        Then: `ValueError`
        """
        # Given
        payload = {"row_counts": {"/Users/someone/성적표.csv": 25}}

        # When / Then
        with pytest.raises(ValueError, match="절대경로"):
            writer.save_run_summary(tmp_path, payload)

    def test_목록_안도_본다(self, tmp_path: Path) -> None:
        """
        목적: `datasets` 는 목록이라 재귀가 목록을 안 보면 통째로 지나간다.

        Given: 목록 원소에 절대경로가 든 요약
        When: 저장한다
        Then: `ValueError`
        """
        # Given
        payload = {"datasets": [{"file": "QQQ_max.csv"}, {"file": "~/storage/market/069500_max.csv"}]}

        # When / Then
        with pytest.raises(ValueError, match="절대경로"):
            writer.save_run_summary(tmp_path, payload)
