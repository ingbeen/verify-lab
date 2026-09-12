"""번들을 받는 쪽의 «자격증명 복원» 과 «항목 식별» 계약을 고정한다.

내보내기가 자격증명을 센티널로 가리므로, 받는 쪽은 그 자리를 **이 PC 에 이미 있던 값으로
되돌려야** 한다. 되돌리지 않으면 번들이 진짜 키를 센티널로 덮어써 MCP 가 죽는다.

두 번째 계약은 **항목 식별자가 항목을 유일하게 가리킨다**는 것이다. 키가 겹치면 결정
파일에서 한 항목이 다른 항목을 덮어써, 사용자가 승인한 적 없는 설정이 조용히 만들어진다.

실경로 `~/.claude.json` 과 번들이 테스트에 걸리지 않도록 `Environment` 를 직접 만들어 쓴다
(`tests/CLAUDE.md` 「파일 격리」). **`classify_settings` 는 순수 함수가 아니다** —
`missing_hint_tools` 가 PATH 를 뒤지고 `_classify_directory` 는 폴더 실재를 본다.
그래서 여기서는 **키와 결정만** 고정하고 `reason` 문자열에는 기대를 걸지 않으며,
설정 픽스처에 `permissions.additionalDirectories` 를 넣지 않는다 — 넣으면 진짜 파일시스템을 본다.

두 스킬은 서로 import 하지 않아 센티널 상수가 갈라질 수 있다. **그 일치도 여기서 고정한다** —
갈라지면 내보내기가 가린 값을 받는 쪽이 알아보지 못하고 그대로 등록한다.
"""

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

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


def test_restore_keeps_existing_url(import_module_under_test: ModuleType) -> None:
    """
    목적: 가려진 url 이 이 PC 의 작동 중인 url 을 덮지 않음을 고정한다

    **url 은 센티널이 문자열 «안에» 박혀 온다** — query 값·userinfo·fragment 만 가려지기
    때문이다. 그래서 완전일치로 보던 복원 로직이 이 자리를 통째로 지나쳤고, 번들의 센티널
    url 이 작동 중인 url 을 덮어써 **서버가 조용히 죽는 상태**가 됐다.

    Given: query 값이 가려진 번들 url 과 진짜 url 을 담은 기존 정의
    When: 복원한다
    Then: 기존 url 이 통째로 남고 채울 것이 없다
    """
    # Given
    sentinel = import_module_under_test.REDACTED_SENTINEL
    bundle = {"type": "http", "url": f"https://vendor/mcp?api_key={sentinel}"}
    existing = {"type": "http", "url": "https://vendor/mcp?api_key=real-token-on-this-pc"}

    # When
    restored, missing = import_module_under_test.restore_redacted(bundle, existing)

    # Then
    assert restored["url"] == "https://vendor/mcp?api_key=real-token-on-this-pc"
    assert missing == []


def test_restore_reports_missing_url(import_module_under_test: ModuleType) -> None:
    """
    목적: 되돌릴 url 이 없으면 **채워야 할 항목으로 알려줌**을 고정한다

    센티널을 남기는 것은 의도다(서버를 통째로 빼지 않는다). 다만 알려주지 않으면
    사용자는 서버가 왜 죽었는지 알 방법이 없다.

    Given: 가려진 번들 url 과 그 서버가 없는 이 PC
    When: 복원한다
    Then: 센티널이 남고 `url` 이 채울 항목으로 보고된다
    """
    # Given
    sentinel = import_module_under_test.REDACTED_SENTINEL
    bundle = {"type": "http", "url": f"https://vendor/mcp?api_key={sentinel}"}

    # When
    restored, missing = import_module_under_test.restore_redacted(bundle, {})

    # Then
    assert sentinel in restored["url"]
    assert missing == ["url"]


def test_restore_keeps_bundle_url_without_sentinel(import_module_under_test: ModuleType) -> None:
    """
    목적: 센티널이 없는 url 은 번들 값이 이김을 고정한다 (기존 계약과 같다)

    보내는 쪽이 주소를 바꿨을 수 있으므로, 가릴 것이 없던 url 은 번들을 따른다.

    Given: 센티널 없는 번들 url 과 다른 기존 url
    When: 복원한다
    Then: 번들 url 이 남는다
    """
    # Given
    bundle = {"type": "http", "url": "https://new-host/mcp"}
    existing = {"type": "http", "url": "https://old-host/mcp"}

    # When
    restored, missing = import_module_under_test.restore_redacted(bundle, existing)

    # Then
    assert restored["url"] == "https://new-host/mcp"
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


def _environment(
    module: ModuleType, extra_path_map: dict[str, str] | None = None, source_home: str = "/Users/source"
) -> object:
    """실경로를 건드리지 않는 실측 정보를 만든다.

    `detect_environment()` 는 번들 매니페스트와 결정 파일을 읽으므로 테스트에서 쓰지 않는다.

    Args:
        module: 받는 쪽 모듈
        extra_path_map: 결정 파일이 주는 추가 치환 쌍. 출처 홈 «밖» 경로를 재현하는 데 쓴다
        source_home: 출처 PC 의 홈. 빈 문자열이면 치환 쌍이 아예 없는 상태가 된다

    Returns:
        object: 판정 함수에 넘길 `Environment`
    """
    return module.Environment(
        platform="linux",
        hostname="test-pc",
        home=Path("/home/tester"),
        source_home=source_home,
        source_hostname="source-pc",
        extra_path_map=dict(extra_path_map) if extra_path_map else {},
    )


def _hook_keys(module: ModuleType, settings: dict[str, object]) -> list[str]:
    """훅 항목의 식별자만 뽑는다.

    Args:
        module: 받는 쪽 모듈
        settings: 판정할 설정

    Returns:
        list[str]: 훅 항목의 키 목록 (판정 순서 유지)
    """
    verdicts = module.classify_settings(settings, _environment(module))

    return [verdict.key for verdict in verdicts if "#hooks." in verdict.key]


def test_same_matcher_groups_get_distinct_keys(import_module_under_test: ModuleType) -> None:
    """
    목적: matcher 까지 같은 그룹이 여럿이어도 키가 겹치지 않음을 고정한다

    한 이벤트에 **matcher 가 같은 그룹이 여럿** 달릴 수 있다. 그룹 안에서만 센 순번을
    쓰면 서로 다른 훅이 같은 키를 갖고, 결정 파일에서 한쪽이 다른 쪽을 덮어쓴다.
    그러면 앞 항목은 해시가 영영 맞지 않아 `needs_confirmation` 이 풀리지 않고
    **`--apply` 가 영구히 중단된다.**

    Given: matcher 가 모두 `*` 인 SessionStart 그룹 둘
    When: 판정한다
    Then: 키가 서로 다르다
    """
    # Given
    settings = {
        "hooks": {
            "SessionStart": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo first"}]},
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo second"}]},
            ]
        }
    }

    # When
    verdicts = import_module_under_test.classify_settings(settings, _environment(import_module_under_test))
    keys = [verdict.key for verdict in verdicts]

    # Then
    assert len(keys) == 2
    assert len(set(keys)) == len(keys)


def test_matcher_containing_suffix_still_gets_distinct_keys(import_module_under_test: ModuleType) -> None:
    """
    목적: 순번 접미사가 다른 matcher 와 부딪혀도 키가 겹치지 않음을 고정한다 (경계)

    matcher 자체가 `*#2` 라는 문자열일 수 있다. 순번을 «한 번만» 붙이면 그 그룹과
    부딪혀 **고치려던 충돌이 그대로 되살아난다.**

    Given: matcher 가 `*` · `*` · `*#2` 인 그룹 셋
    When: 판정한다
    Then: 키 셋이 모두 다르다
    """
    # Given
    settings = {
        "hooks": {
            "SessionStart": [
                {"matcher": "*", "hooks": [{"command": "a"}]},
                {"matcher": "*", "hooks": [{"command": "b"}]},
                {"matcher": "*#2", "hooks": [{"command": "c"}]},
            ]
        }
    }

    # When
    keys = _hook_keys(import_module_under_test, settings)

    # Then
    assert len(keys) == 3
    assert len(set(keys)) == 3


def test_same_matcher_groups_keep_independent_decisions(import_module_under_test: ModuleType) -> None:
    """
    목적: 겹쳤던 두 훅이 «서로 다른» 결정을 가질 수 있음을 고정한다

    키가 겹치면 `_decision_map` 이 나중 것으로 덮어써 **한 훅의 결정이 다른 훅에
    적용된다.** 사용자가 「제외」로 정한 훅이 조용히 적용되는 경로이므로,
    키 유일성과 별개로 «적용» 쪽에서도 고정한다.

    Given: matcher 가 같은 그룹 둘과, 앞은 제외 뒤는 적용이라는 결정
    When: 설정을 다시 조립한다
    Then: 적용으로 정한 훅만 남는다
    """
    # Given
    module = import_module_under_test
    environment = _environment(module)
    settings = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Write|Edit", "hooks": [{"type": "command", "command": "echo excluded"}]},
                {"matcher": "Write|Edit", "hooks": [{"type": "command", "command": "echo applied"}]},
            ]
        }
    }
    verdicts = module.classify_settings(settings, environment)
    hook_verdicts = [verdict for verdict in verdicts if "#hooks." in verdict.key]
    hook_verdicts[0].decision = module.EXCLUDE
    hook_verdicts[1].decision = module.APPLY
    plan = module.Plan(environment=environment, verdicts=verdicts)

    # When
    rebuilt = module.rebuild_settings(settings, plan, environment)

    # Then
    commands = [hook["command"] for group in rebuilt["hooks"]["PreToolUse"] for hook in group["hooks"]]
    assert commands == ["echo applied"]


def test_distinct_matchers_keep_existing_key_format(import_module_under_test: ModuleType) -> None:
    """
    목적: 겹치지 않는 훅의 키 형식이 바뀌지 않음을 고정한다 (회귀)

    키 형식을 통째로 바꾸면 **지난 결정이 전부 무효가 되어** 사용자가 이미 승인한
    항목까지 다시 물어야 한다. 충돌을 푸는 대가로 그것을 치르지 않는다.

    Given: matcher 가 서로 다른 그룹과 한 그룹 안의 훅 둘
    When: 판정한다
    Then: 키가 기존 형식 그대로다
    """
    # Given
    settings = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"command": "first"}, {"command": "second"}]},
                {"matcher": "Edit|Write", "hooks": [{"command": "third"}]},
            ]
        }
    }

    # When
    keys = _hook_keys(import_module_under_test, settings)

    # Then
    assert keys == [
        "settings.json#hooks.PreToolUse[Bash][0]",
        "settings.json#hooks.PreToolUse[Bash][1]",
        "settings.json#hooks.PreToolUse[Edit|Write][0]",
    ]


def test_empty_and_matcherless_groups_do_not_raise(import_module_under_test: ModuleType) -> None:
    """
    목적: 훅이 없는 그룹과 matcher 가 없는 그룹에서 예외가 나지 않음을 고정한다 (경계)

    `matcher` 는 생략될 수 있고(`*` 로 본다), 그룹의 `hooks` 가 빌 수도 있다.
    빈 그룹은 조립 결과에서도 빠져야 한다 — 남기면 의미 없는 항목이 된다.

    Given: 훅이 빈 그룹과 matcher 가 없는 그룹
    When: 판정하고 다시 조립한다
    Then: 예외가 없고, 빈 그룹은 남지 않는다
    """
    # Given
    module = import_module_under_test
    environment = _environment(module)
    settings = {
        "hooks": {
            "Stop": [
                {"matcher": "*", "hooks": []},
                {"hooks": [{"command": "echo kept"}]},
            ]
        }
    }

    # When
    verdicts = module.classify_settings(settings, environment)
    for verdict in verdicts:
        verdict.decision = module.APPLY
    rebuilt = module.rebuild_settings(settings, module.Plan(environment=environment, verdicts=verdicts), environment)

    # Then
    assert len(rebuilt["hooks"]["Stop"]) == 1
    assert rebuilt["hooks"]["Stop"][0]["hooks"][0]["command"] == "echo kept"


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


def _permission_verdict(module: ModuleType, environment: object, section: str, entry: str) -> Any:
    """권한 규칙 한 건의 판정을 꺼낸다.

    키를 못 찾으면 **키 형식이 바뀐 것**이므로 그 사실을 말하고 실패한다. 벗은 `next()` 는
    `StopIteration` 을 내 헬퍼를 범인으로 가리키고, 실제로 깨진 계약을 감춘다.

    Args:
        module: 받는 쪽 모듈
        environment: 판정에 쓸 실측 정보
        section: `allow` · `deny` · `ask` 중 하나
        entry: 권한 규칙 문자열

    Returns:
        Any: 그 규칙의 `Verdict`
    """
    settings = {"permissions": {section: [entry]}}
    verdicts = module.classify_settings(settings, environment)
    matched = [verdict for verdict in verdicts if verdict.key.endswith(f"::{entry}")]

    assert len(matched) == 1, f"권한 규칙의 키를 찾지 못했습니다: {[verdict.key for verdict in verdicts]}"

    return matched[0]


def test_extra_path_map_reaches_permission_rule(import_module_under_test: ModuleType) -> None:
    """
    목적: 출처 홈 «밖» 경로를 가리키는 권한 규칙도 치환 대상으로 판정됨을 고정한다

    치환 규칙은 출처 홈 하나가 아니라 `path_map` 전체다. 판정이 출처 홈만 보면
    **홈 밖 경로는 「그대로 적용」으로 통과해 죽은 경로가 그대로 쓰인다.**
    `ask` 가드가 그렇게 되면 **보호가 조용히 사라진다** — 에러도 경고도 없다.

    Given: 출처 홈 밖 경로를 이 PC 경로로 잇는 치환 쌍과, 그 경로를 가리키는 `ask` 규칙
    When: 판정한다
    Then: 「변환 후 적용」이고 치환 결과가 이 PC 경로다
    """
    # Given
    module = import_module_under_test
    environment = _environment(module, {"/mnt/win/Downloads": "/home/tester/Downloads"})

    # When
    verdict = _permission_verdict(module, environment, "ask", "Read(//mnt/win/Downloads/*.env)")

    # Then
    assert verdict.decision == module.TRANSFORM
    assert verdict.detail == "Read(//home/tester/Downloads/*.env)"


def test_rebuild_applies_extra_path_map_to_permission_rule(import_module_under_test: ModuleType) -> None:
    """
    목적: 다시 조립한 설정에 이 PC 경로가 들어감을 고정한다

    판정만 맞고 조립이 원문을 쓰면 사용자에게 보이는 결과는 그대로 죽은 경로다.
    **사용자가 실제로 치르는 계약은 이쪽이다.**

    Given: 홈 밖 경로를 가리키는 `ask` 규칙과 그 치환 쌍
    When: 판정한 뒤 설정을 다시 조립한다
    Then: 규칙 문자열이 이 PC 경로로 바뀌어 있다
    """
    # Given
    module = import_module_under_test
    environment = _environment(module, {"/mnt/win/Downloads": "/home/tester/Downloads"})
    settings = {"permissions": {"ask": ["Read(//mnt/win/Downloads/*.pem)"]}}
    verdicts = module.classify_settings(settings, environment)

    # When
    rebuilt = module.rebuild_settings(settings, module.Plan(environment=environment, verdicts=verdicts), environment)

    # Then
    assert rebuilt["permissions"]["ask"] == ["Read(//home/tester/Downloads/*.pem)"]


def test_extra_path_map_reaches_bundle_file(
    import_module_under_test: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    목적: 번들 파일 내용의 홈 밖 경로도 치환 대상으로 판정됨을 고정한다

    같은 결함이 파일 판정에도 있다. 파일 안의 경로가 안 바뀌면 **그 파일을 읽는 도구가
    없는 경로를 가리킨다** — 등록된 SQL 목록처럼 경로가 곧 식별자인 파일이 그렇다.

    Given: 홈 밖 경로만 든 번들 파일과 그 치환 쌍
    When: 파일을 판정한다
    Then: 「변환 후 적용」이다
    """
    # Given
    module = import_module_under_test
    monkeypatch.setattr(module, "BUNDLE_HOME_DIR", tmp_path)
    (tmp_path / "registry.json").write_text('{"path": "/mnt/win/Downloads/query.sql"}', encoding="utf-8")
    environment = _environment(module, {"/mnt/win/Downloads": "/home/tester/Downloads"})

    # When
    verdicts = module.classify_files(environment)

    # Then
    assert [verdict.decision for verdict in verdicts] == [module.TRANSFORM]


def test_longest_path_map_pair_wins(import_module_under_test: ModuleType) -> None:
    """
    목적: 한 쌍이 다른 쌍을 품을 때 긴 쪽이 이김을 고정한다 (경계)

    짧은 홈 경로를 먼저 바꾸면 그 안에 든 긴 경로가 이미 바뀌어 **뒤 규칙이 걸리지 않는다.**
    작업 폴더 이름이 PC 마다 다른 경우가 정확히 이 형태다.

    Given: 출처 홈과 그 아래 작업 폴더를 각각 잇는 쌍 둘
    When: 작업 폴더를 가리키는 규칙을 판정한다
    Then: 긴 쌍의 대상 경로가 쓰인다
    """
    # Given
    module = import_module_under_test
    environment = _environment(module, {"/Users/source/Workspace": "/home/tester/work"})

    # When
    verdict = _permission_verdict(module, environment, "allow", "Read(//Users/source/Workspace/**)")

    # Then
    assert verdict.detail == "Read(//home/tester/work/**)"


def test_overlapping_pairs_are_not_double_counted(
    import_module_under_test: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    목적: 치환 횟수를 쌍마다 따로 세지 않음을 고정한다 (경계)

    한 쌍이 다른 쌍을 품으면 **같은 자리가 두 번 세어진다.** 횟수는 사람이
    「무엇이 바뀌는가」를 좁히는 재료라, 부풀면 없는 변경을 찾게 만든다.

    Given: 서로를 품는 쌍 둘과, 그중 한 자리만 등장하는 파일
    When: 파일을 판정한다
    Then: 사유에 적힌 횟수가 1곳이다
    """
    # Given
    module = import_module_under_test
    monkeypatch.setattr(module, "BUNDLE_HOME_DIR", tmp_path)
    (tmp_path / "note.md").write_text("경로는 /Users/source/Workspace/repo 하나뿐이다", encoding="utf-8")
    environment = _environment(module, {"/Users/source/Workspace": "/home/tester/work"})

    # When
    verdicts = module.classify_files(environment)

    # Then
    assert verdicts[0].reason == "경로 1곳을 바꿉니다"


def test_entry_without_mapped_path_stays_apply(import_module_under_test: ModuleType) -> None:
    """
    목적: 치환할 것이 없는 항목은 「그대로 적용」으로 남음을 고정한다 (경계)

    조건을 넓히다가 **분류가 통째로 「변환 후 적용」으로 쏠리면** 판정표가 쓸모없어진다.
    사용자는 그 표로 무엇이 손대지는지 가린다.

    Given: 어느 치환 쌍과도 겹치지 않는 권한 규칙
    When: 판정한다
    Then: 「그대로 적용」이다
    """
    # Given
    module = import_module_under_test
    environment = _environment(module, {"/mnt/win/Downloads": "/home/tester/Downloads"})

    # When
    verdict = _permission_verdict(module, environment, "allow", "Bash(git status)")

    # Then
    assert verdict.decision == module.APPLY


def test_empty_path_map_does_not_raise(
    import_module_under_test: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    목적: 치환 쌍이 아예 없어도 예외 없이 「그대로 적용」됨을 고정한다 (경계)

    매니페스트에 출처 홈이 없을 수 있다. 그때 치환 쌍은 빈 dict 이며,
    **판정이 멈추지 않고 원문을 그대로 쓰는 것이 정책이다.**

    Given: 출처 홈이 빈 실측 정보와, 경로가 든 규칙·파일
    When: 설정과 파일을 판정한다
    Then: 예외 없이 둘 다 「그대로 적용」이다
    """
    # Given
    module = import_module_under_test
    monkeypatch.setattr(module, "BUNDLE_HOME_DIR", tmp_path)
    (tmp_path / "note.md").write_text("/Users/source/Workspace/repo", encoding="utf-8")
    environment = _environment(module, source_home="")

    # When
    verdict = _permission_verdict(module, environment, "allow", "Read(//Users/source/Workspace/**)")
    file_verdicts = module.classify_files(environment)

    # Then
    assert verdict.decision == module.APPLY
    assert [file_verdict.decision for file_verdict in file_verdicts] == [module.APPLY]


def _decisions(module: ModuleType, key: str, decision: str, value: object) -> dict[str, Any]:
    """항목 하나에 대한 지난 결정을 만든다.

    Args:
        module: 받는 쪽 모듈
        key: 항목 식별자
        decision: 저장돼 있던 결정
        value: 그 항목의 값 (해시를 맞추는 데 쓴다)

    Returns:
        dict[str, Any]: `apply_previous_decisions` 가 받는 구조
    """
    return {"items": {key: {"decision": decision, "reason": "지난 회차", "source_hash": module._hash_value(value)}}}


def test_remembered_include_does_not_freeze_path_form(import_module_under_test: ModuleType) -> None:
    """
    목적: 기억된 「넣는다」가 새 경로 판정을 덮지 않음을 고정한다

    해시는 항목 «값» 만 담고 `path_map` 은 담지 않는다. 그래서 쌍을 나중에 더해도 해시는
    그대로이고, 기억된 형태까지 되살리면 **옛 `apply` 가 이겨 죽은 경로가 그대로 쓰인다.**
    3 회차에서 권한 규칙 18건이 그 경로로 죽었고 손으로 결정을 지워야 했다.

    Given: 쌍이 없던 때 `apply` 로 저장된 결정과, 쌍이 생긴 지금의 `transform` 판정
    When: 지난 결정을 반영한다
    Then: 이번 판정의 `transform` 이 유지된다
    """
    # Given
    module = import_module_under_test
    entry = "Read(//mnt/win/Downloads/*.env)"
    environment = _environment(module, {"/mnt/win/Downloads": "/home/tester/Downloads"})
    settings = {"permissions": {"ask": [entry]}}
    verdicts = module.classify_settings(settings, environment)
    plan = module.Plan(environment=environment, verdicts=verdicts)

    # When
    module.apply_previous_decisions(plan, _decisions(module, verdicts[0].key, module.APPLY, entry))

    # Then
    assert verdicts[0].decision == module.TRANSFORM


def test_remembered_exclude_still_wins(import_module_under_test: ModuleType) -> None:
    """
    목적: 사용자가 「뺀다」로 정한 항목은 그대로 빠짐을 고정한다

    형태(`apply`/`transform`)는 파생값이지만 **제외는 사용자 결정이다.** 형태를 새로
    판정한다는 이유로 제외까지 흔들면 승인한 적 없는 항목이 되살아난다.

    Given: `exclude` 로 저장된 결정과, 이번에 `transform` 으로 판정된 같은 항목
    When: 지난 결정을 반영한다
    Then: `exclude` 가 유지된다
    """
    # Given
    module = import_module_under_test
    entry = "Read(//mnt/win/Downloads/*.key)"
    environment = _environment(module, {"/mnt/win/Downloads": "/home/tester/Downloads"})
    settings = {"permissions": {"ask": [entry]}}
    verdicts = module.classify_settings(settings, environment)
    plan = module.Plan(environment=environment, verdicts=verdicts)

    # When
    module.apply_previous_decisions(plan, _decisions(module, verdicts[0].key, module.EXCLUDE, entry))

    # Then
    assert verdicts[0].decision == module.EXCLUDE


def test_remembered_hook_approval_still_wins(import_module_under_test: ModuleType) -> None:
    """
    목적: 승인한 훅이 계속 적용됨을 고정한다 (회귀)

    훅은 **언제나 `EXCLUDE` 로 판정되고** 사용자의 승인에만 기댄다. 형태를 새로 판정하는
    규칙이 훅까지 삼키면 **승인한 훅이 매 회차 사라진다.**

    Given: `apply` 로 승인된 훅과, 이번에도 `EXCLUDE` 로 나온 같은 훅
    When: 지난 결정을 반영한다
    Then: `apply` 가 유지되고 다시 묻지 않는다
    """
    # Given
    module = import_module_under_test
    hook = {"type": "command", "command": "python3 $HOME/.claude/hooks/guard.py"}
    environment = _environment(module)
    settings = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [hook]}]}}
    verdicts = module.classify_settings(settings, environment)
    plan = module.Plan(environment=environment, verdicts=verdicts)

    # When
    module.apply_previous_decisions(plan, _decisions(module, verdicts[0].key, module.APPLY, hook))

    # Then
    assert verdicts[0].decision == module.APPLY
    assert verdicts[0].needs_confirmation is False
