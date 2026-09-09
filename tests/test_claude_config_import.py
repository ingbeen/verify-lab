"""번들을 받는 쪽의 자격증명 복원 계약을 고정한다.

내보내기가 자격증명을 센티널로 가리므로, 받는 쪽은 그 자리를 **이 PC 에 이미 있던 값으로
되돌려야** 한다. 되돌리지 않으면 번들이 진짜 키를 센티널로 덮어써 MCP 가 죽는다.

판정 대상은 순수 함수 하나다. 파일을 읽지도 쓰지도 않으므로 실경로 `~/.claude.json` 이
테스트에 걸리지 않는다 (`tests/CLAUDE.md` 「파일 격리」).

두 스킬은 서로 import 하지 않아 센티널 상수가 갈라질 수 있다. **그 일치도 여기서 고정한다** —
갈라지면 내보내기가 가린 값을 받는 쪽이 알아보지 못하고 그대로 등록한다.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

IMPORT_SCRIPT_PATH = PROJECT_ROOT / ".claude" / "skills" / "claude-config-import" / "plan_apply.py"
EXPORT_SCRIPT_PATH = PROJECT_ROOT / ".claude" / "skills" / "claude-config-export" / "export.py"


def _load_script(path: Path, module_name: str) -> ModuleType:
    """스킬 스크립트를 파일 경로에서 로드한다.

    스킬 폴더 이름에 하이픈이 있어 파이썬 식별자가 될 수 없다.

    Args:
        path: 스크립트 경로
        module_name: 로드할 모듈에 붙일 이름

    Returns:
        ModuleType: 로드된 모듈
    """
    if not path.is_file():
        pytest.fail(f"스크립트가 없습니다: {path}")

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        pytest.fail(f"모듈 스펙을 만들 수 없습니다: {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


@pytest.fixture(scope="module")
def import_module_under_test() -> ModuleType:
    """받는 쪽 스크립트를 로드한다.

    Returns:
        ModuleType: 복원 함수를 담은 모듈
    """
    return _load_script(IMPORT_SCRIPT_PATH, "claude_config_import")


@pytest.fixture(scope="module")
def export_module() -> ModuleType:
    """내보내는 쪽 스크립트를 로드한다.

    센티널 상수가 양쪽에서 같은지 대조하는 데만 쓴다.

    Returns:
        ModuleType: 치환 함수를 담은 모듈
    """
    return _load_script(EXPORT_SCRIPT_PATH, "claude_config_export_for_import_test")


def test_sentinel_matches_between_skills(import_module_under_test: ModuleType, export_module: ModuleType) -> None:
    """
    목적: 양쪽 스킬의 센티널이 같은 값임을 고정한다

    두 스킬은 서로 import 하지 않으므로 상수가 조용히 갈라질 수 있다. 갈라지면
    **받는 쪽이 가려진 값을 알아보지 못하고 센티널을 그대로 등록한다.**

    Given: 내보내기와 받기 두 모듈
    When: 센티널 상수를 비교한다
    Then: 같다
    """
    # Then
    assert import_module_under_test.REDACTED_SENTINEL == export_module.REDACTED_SENTINEL


def test_restore_keeps_existing_value(import_module_under_test: ModuleType) -> None:
    """
    목적: 이 PC 에 이미 있던 값이 센티널에 덮이지 않음을 고정한다

    받는 쪽은 서버 정의를 통째로 대입하므로, 복원이 없으면 **쓰고 있던 진짜 키가
    센티널로 바뀐다.**

    Given: 센티널을 담은 번들 정의와 진짜 키를 담은 기존 정의
    When: 복원한다
    Then: 기존 값이 남고 채울 것이 없다
    """
    # Given
    sentinel = import_module_under_test.REDACTED_SENTINEL
    bundle = {"type": "http", "url": "https://x/mcp", "headers": {"API_KEY": sentinel}}
    existing = {"type": "http", "url": "https://x/mcp", "headers": {"API_KEY": "real-key-on-this-pc"}}

    # When
    restored, missing = import_module_under_test.restore_redacted(bundle, existing)

    # Then
    assert restored["headers"]["API_KEY"] == "real-key-on-this-pc"
    assert missing == []


def test_restore_reports_missing_value(import_module_under_test: ModuleType) -> None:
    """
    목적: 되돌릴 값이 없으면 그 사실이 보고됨을 고정한다

    서버를 통째로 빼지 않는다 — 빼면 「MCP 가 통째로 사라진다」는 이 기능의 취지에
    역행한다. 대신 **무엇을 채워야 하는지 알려준다.**

    Given: 센티널을 담은 번들 정의와 그 필드가 없는 기존 정의
    When: 복원한다
    Then: 센티널이 남고 그 필드가 보고된다
    """
    # Given
    sentinel = import_module_under_test.REDACTED_SENTINEL
    bundle = {"type": "http", "headers": {"API_KEY": sentinel}}

    # When
    restored, missing = import_module_under_test.restore_redacted(bundle, {})

    # Then
    assert restored["headers"]["API_KEY"] == sentinel
    assert missing == ["headers.API_KEY"]


def test_restore_prefers_bundle_value_when_not_sentinel(import_module_under_test: ModuleType) -> None:
    """
    목적: 센티널이 아닌 값은 번들이 이김을 고정한다 (기존 동작 유지)

    복원은 **가려진 자리에만** 개입한다. 그 밖의 설정까지 기존 값을 우선하면
    번들을 적용하는 뜻이 사라진다.

    Given: 서로 다른 URL 을 담은 번들 정의와 기존 정의
    When: 복원한다
    Then: 번들 값이 남는다
    """
    # Given
    bundle = {"type": "http", "url": "https://new/mcp"}
    existing = {"type": "http", "url": "https://old/mcp"}

    # When
    restored, missing = import_module_under_test.restore_redacted(bundle, existing)

    # Then
    assert restored["url"] == "https://new/mcp"
    assert missing == []


def test_restore_adds_field_absent_in_existing(import_module_under_test: ModuleType) -> None:
    """
    목적: 기존에 없던 필드가 그대로 추가됨을 고정한다

    Given: 기존 정의에 없는 `env` 를 담은 번들 정의
    When: 복원한다
    Then: 그 필드가 번들 값 그대로 들어간다
    """
    # Given
    bundle = {"type": "stdio", "env": {"CREDENTIALS_PATH": "/home/me/keys/oauth.json"}}
    existing = {"type": "stdio"}

    # When
    restored, missing = import_module_under_test.restore_redacted(bundle, existing)

    # Then
    assert restored["env"]["CREDENTIALS_PATH"] == "/home/me/keys/oauth.json"
    assert missing == []


def test_restore_when_existing_server_missing(import_module_under_test: ModuleType) -> None:
    """
    목적: 그 서버가 처음 들어오는 PC 에서도 예외가 나지 않음을 고정한다 (경계)

    최초 설치 PC 에는 `~/.claude.json` 자체가 없을 수 있다.

    Given: 센티널과 경로를 담은 번들 정의와 «비어 있는» 기존 정의
    When: 복원한다
    Then: 예외 없이 센티널만 보고된다
    """
    # Given
    sentinel = import_module_under_test.REDACTED_SENTINEL
    bundle = {"headers": {"API_KEY": sentinel}, "env": {"DATA_PATH": "/home/me/data"}}

    # When
    restored, missing = import_module_under_test.restore_redacted(bundle, {})

    # Then
    assert restored["env"]["DATA_PATH"] == "/home/me/data"
    assert missing == ["headers.API_KEY"]


def test_restore_partial_sentinel(import_module_under_test: ModuleType) -> None:
    """
    목적: 같은 블록 안에서 가려진 값과 아닌 값이 따로 처리됨을 고정한다 (경계)

    한 `headers` 에 자격증명과 일반 헤더가 섞일 수 있다. 블록 단위로 되돌리면
    **번들이 새로 바꾼 일반 헤더가 옛 값으로 돌아간다.**

    Given: 한 필드만 센티널인 번들 정의와 두 필드를 모두 가진 기존 정의
    When: 복원한다
    Then: 센티널 자리만 기존 값으로 돌아가고 나머지는 번들 값이 남는다
    """
    # Given
    sentinel = import_module_under_test.REDACTED_SENTINEL
    bundle = {"headers": {"API_KEY": sentinel, "X_VERSION": "2"}}
    existing = {"headers": {"API_KEY": "real-key", "X_VERSION": "1"}}

    # When
    restored, missing = import_module_under_test.restore_redacted(bundle, existing)

    # Then
    assert restored["headers"] == {"API_KEY": "real-key", "X_VERSION": "2"}
    assert missing == []


def test_restore_does_not_mutate_input(import_module_under_test: ModuleType) -> None:
    """
    목적: 번들 정의가 바뀌지 않음을 고정한다

    같은 정의를 판정 단계와 적용 단계가 각각 본다. 한쪽이 원본을 바꾸면
    다른 쪽이 다른 값을 보게 된다.

    Given: 센티널을 담은 번들 정의
    When: 복원한다
    Then: 원본의 값이 그대로다
    """
    # Given
    sentinel = import_module_under_test.REDACTED_SENTINEL
    bundle = {"headers": {"API_KEY": sentinel}}
    existing = {"headers": {"API_KEY": "real-key"}}

    # When
    import_module_under_test.restore_redacted(bundle, existing)

    # Then
    assert bundle["headers"]["API_KEY"] == sentinel
