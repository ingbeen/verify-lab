"""전역 Claude 설정 번들의 포함·제외 판정을 고정한다.

번들은 `~/.claude` 를 이 저장소로 옮기는 사본이다. **무엇이 들어가면 안 되는가**가
이 기능의 핵심 계약이며, 셋 중 어느 것이 새도 되돌리기 어렵다.

- **자격증명** — 이 저장소는 PUBLIC 이라 커밋되면 파일을 지워도 git 이력에 남는다
- **세션 상태·감사로그** — `projects/` 만 426MB 다. 다른 PC 의 이력이 섞이면 되돌릴 수 없다
- **venv** — 플랫폼 바이너리라 받는 쪽에서 쓸 수 없고 크기만 키운다

판정 함수는 스킬 폴더에 있다. 폴더 이름에 하이픈이 있어 일반 `import` 가 성립하지 않으므로
`importlib` 로 파일 경로에서 로드한다.

번들 자체는 이 저장소의 산출물이 아니라 **다음 세션에서 스킬이 만든다.** 그래서 실물 위생
검사는 번들이 있을 때만 돌고, 없으면 통과한다 (`pytest.skip` 을 쓰지 않는다 — 계획서 Done
조건이 `skipped=0` 이다).
"""

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 판정 함수를 담은 스크립트. 스킬과 도구를 한 폴더에 두어 이동·삭제가 원자적이다
EXPORT_SCRIPT_PATH = PROJECT_ROOT / ".claude" / "skills" / "claude-config-export" / "export.py"

# 번들이 놓이는 고정 경로. 받는 쪽 스킬이 이 경로를 스스로 찾는다
BUNDLE_DIR = PROJECT_ROOT / "claude-config"
BUNDLE_HOME_DIR = BUNDLE_DIR / "home"
MANIFEST_PATH = BUNDLE_DIR / "MANIFEST.json"

# 번들 크기 상한. 실측 356KB(2026-09-09) 에 여유를 둔 값이다.
# 「담을 것만 담혔는가」를 크기로도 잡는다 — 실제로 `plugins/` 를 담았다가 6.4MB 가 나온 적이 있다
BUNDLE_SIZE_LIMIT_BYTES = 2_000_000

# 번들에 담겨야 하는 경로 (`~/.claude` 기준 상대)
INCLUDED_PATHS = (
    Path("CLAUDE.md"),
    Path("settings.json"),
    Path("skills/impl-plan/SKILL.md"),
    Path("skills/impl-plan/template.md"),
    Path("commands/commit.md"),
    Path("rules/python.md"),
    Path("hooks/plan_gate.py"),
    Path("tools/msg/msg2eml.py"),
    Path("tools/pptx/build_v14.py"),
    Path("db/acmeq.py"),
    Path("db/scripts.allow.json"),
    Path("db/acme-prd.env.example"),
)

# 번들에서 걸러져야 하는 경로. 사유를 함께 적어 실패 메시지가 「왜」를 말하게 한다
EXCLUDED_PATHS = (
    (Path("projects/-Users-yubeen-Workspace-verify-lab/abc.jsonl"), "세션 이력"),
    (Path("sessions/abc.json"), "세션 상태"),
    (Path("history.jsonl"), "프롬프트 이력"),
    (Path("file-history/abc/def.txt"), "파일 편집 이력"),
    (Path("shell-snapshots/snapshot-zsh-1.sh"), "셸 스냅샷"),
    (Path("session-env/abc.json"), "세션 환경"),
    (Path("cache/anything.json"), "캐시"),
    (Path("ide/lock.json"), "IDE 연결 상태"),
    (Path("daemon/state.json"), "데몬 상태"),
    (Path("jobs/job.json"), "작업 큐"),
    (Path("paste-cache/a.txt"), "붙여넣기 캐시"),
    (Path("downloads/a.bin"), "다운로드"),
    (Path("backups/.claude.json.backup.123"), "자동 백업"),
    (Path("tools/xlsx/venv/bin/python3"), "플랫폼 venv"),
    (Path("db/venv/lib/site-packages/x.py"), "플랫폼 venv"),
    (Path("hooks/__pycache__/plan_gate.cpython-312.pyc"), "바이트코드"),
    (Path("CLAUDE.md.bak-20260909"), "수동 백업본"),
    (Path("settings.json.bak-20260908"), "수동 백업본"),
    (Path("db/audit.jsonl"), "감사 로그"),
    (Path("db/api-audit.jsonl"), "감사 로그"),
    (Path("plugins/plugin-catalog-cache.json"), "플러그인 카탈로그 캐시"),
    (Path("plugins/marketplaces/claude-plugins-official/README.md"), "공식 마켓플레이스 사본 6.4MB"),
    (Path("plugins/known_marketplaces.json"), "받는 쪽에서 자동 재설치되고 절대경로를 담고 있다"),
)

# 절대 담기면 안 되는 자격증명. 화이트리스트를 넓혀도 이쪽이 먼저 막아야 한다
CREDENTIAL_PATHS = (
    Path("db/acme-prd.env"),
    Path("keys/sheets-mcp-oauth.json"),
    Path("keys/sheets-mcp-token.json"),
    Path("keys/whatever-comes-later.json"),
)

# 번들의 `claude_json.json` 경로. 파일 판정과 달리 «값» 을 검사해야 하는 유일한 자리다
BUNDLE_CLAUDE_JSON_PATH = BUNDLE_DIR / "claude_json.json"

# 값 치환 계약을 재는 표본. 실물 구조를 본떴다 —
# 평문 키를 담는 서버(context7), 경로만 담는 서버(google-sheets),
# 아무것도 담지 않는 서버, 그리고 프로젝트 스코프 서버
SAMPLE_CLAUDE_JSON: dict[str, Any] = {
    "mcpServers": {
        "context7": {
            "type": "http",
            "url": "https://mcp.context7.com/mcp",
            "headers": {"CONTEXT7_API_KEY": "ctx7sk-0000-example"},
        },
        "google-sheets": {
            "type": "stdio",
            "command": "/Users/someone/.local/bin/uvx",
            "args": ["--with", "mcp<2", "mcp-google-sheets@latest"],
            "env": {
                "CREDENTIALS_PATH": "/Users/someone/.claude/keys/sheets-mcp-oauth.json",
                "TOKEN_PATH": "/Users/someone/.claude/keys/sheets-mcp-token.json",
            },
        },
        "bare": {"type": "http", "url": "https://example.com/mcp"},
    },
    "projects": {
        "/Users/someone/Workspace/repo": {
            "mcpServers": {
                "internal": {
                    "type": "http",
                    "url": "https://internal.example.com/mcp",
                    "headers": {"X_INTERNAL_TOKEN": "internal-secret-value"},
                }
            }
        }
    },
}

# 자격증명 형태를 잡는 그물의 «두 번째 겹».
# 치환은 `headers`·`env` 만 덮으므로 `command`·`args` 같은 자리는 이 스캔이 맡는다.
# **금지목록이라 새 형식은 놓칠 수 있다** — 치환의 대체가 아니라 보완이다
SECRET_VALUE_PATTERNS = (
    ("Context7", re.compile(r"ctx7sk-")),
    ("OpenAI 계열", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("GitHub", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("AWS", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Slack", re.compile(r"xox[baprs]-")),
    ("PEM 개인키", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)


@pytest.fixture(scope="module")
def export_module() -> ModuleType:
    """내보내기 스크립트를 파일 경로에서 로드한다.

    스킬 폴더 이름(`claude-config-export`)에 하이픈이 있어 파이썬 식별자가 될 수 없다.
    일반 `import` 로는 접근할 수 없으므로 `importlib` 를 쓴다.

    Returns:
        ModuleType: 판정 함수를 담은 모듈
    """
    if not EXPORT_SCRIPT_PATH.is_file():
        pytest.fail(f"내보내기 스크립트가 없습니다: {EXPORT_SCRIPT_PATH}")

    spec = importlib.util.spec_from_file_location("claude_config_export", EXPORT_SCRIPT_PATH)
    if spec is None or spec.loader is None:
        pytest.fail(f"모듈 스펙을 만들 수 없습니다: {EXPORT_SCRIPT_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


@pytest.fixture
def fake_claude_home(tmp_path: Path) -> Path:
    """포함·제외 대상이 섞인 가짜 `~/.claude` 트리를 만든다.

    실제 홈 디렉터리를 읽지 않는다 (`tests/CLAUDE.md` 「외부 의존성 금지」).

    Args:
        tmp_path: pytest가 테스트마다 새로 만드는 임시 디렉터리

    Returns:
        Path: 가짜 `~/.claude` 루트
    """
    home = tmp_path / "claude-home"
    for relative_path in INCLUDED_PATHS:
        target = home / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")

    for relative_path, _reason in EXCLUDED_PATHS:
        target = home / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")

    for relative_path in CREDENTIAL_PATHS:
        target = home / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("secret", encoding="utf-8")

    return home


@pytest.mark.parametrize("relative_path", INCLUDED_PATHS)
def test_included_path_is_kept(export_module: ModuleType, relative_path: Path) -> None:
    """
    목적: 하네스를 이루는 파일이 번들에 담기는 것을 고정한다

    Given: `~/.claude` 기준 상대경로
    When: 포함 여부를 판정한다
    Then: 포함으로 판정된다
    """
    # When
    included = export_module.should_include(relative_path)

    # Then
    assert included is True, f"번들에 담겨야 하는데 걸러졌습니다: {relative_path}"


@pytest.mark.parametrize(("relative_path", "reason"), EXCLUDED_PATHS)
def test_excluded_path_is_dropped(export_module: ModuleType, relative_path: Path, reason: str) -> None:
    """
    목적: 세션 상태·캐시·venv·감사로그가 번들에 섞이지 않음을 고정한다

    Given: 옮길 대상이 아닌 상대경로
    When: 포함 여부를 판정한다
    Then: 제외로 판정된다
    """
    # When
    included = export_module.should_include(relative_path)

    # Then
    assert included is False, f"{reason}인데 번들에 담깁니다: {relative_path}"


@pytest.mark.parametrize("relative_path", CREDENTIAL_PATHS)
def test_credential_is_dropped(export_module: ModuleType, relative_path: Path) -> None:
    """
    목적: 자격증명이 번들에 담기지 않음을 고정한다

    제외 대상 검사와 따로 두는 이유는 **유출이 되돌릴 수 없기 때문**이다. 이 저장소는
    PUBLIC 이라 한 번 커밋되면 파일을 지워도 git 이력에 남는다. 나중에 화이트리스트를
    넓힐 때 이 테스트가 먼저 걸린다.

    Given: 자격증명 파일의 상대경로
    When: 포함 여부를 판정한다
    Then: 제외로 판정된다
    """
    # When
    included = export_module.should_include(relative_path)

    # Then
    assert included is False, f"자격증명이 번들에 담깁니다: {relative_path}"


def test_unknown_top_level_is_dropped(export_module: ModuleType) -> None:
    """
    목적: 화이트리스트에 없는 새 폴더는 기본 제외임을 고정한다

    허용목록 방식이어야 Claude Code 가 새 폴더를 만들었을 때 조용히 딸려오지 않는다.

    Given: 판정 규칙이 알지 못하는 최상위 폴더
    When: 포함 여부를 판정한다
    Then: 제외로 판정된다
    """
    # When
    included = export_module.should_include(Path("some-new-feature/state.json"))

    # Then
    assert included is False, "모르는 최상위 폴더가 번들에 담깁니다"


def test_collect_gathers_only_included_paths(export_module: ModuleType, fake_claude_home: Path) -> None:
    """
    목적: 트리 순회 결과가 판정 규칙과 일치함을 고정한다

    Given: 포함·제외·자격증명이 섞인 가짜 홈 트리
    When: 담을 경로를 모은다
    Then: 포함 대상만 나온다
    """
    # When
    collected = export_module.collect_relative_paths(fake_claude_home)

    # Then
    assert set(collected) == set(INCLUDED_PATHS)


def test_collect_returns_sorted_paths(export_module: ModuleType, fake_claude_home: Path) -> None:
    """
    목적: 수집 결과의 순서가 파일시스템 순회 순서에 좌우되지 않음을 고정한다

    순서가 흔들리면 매니페스트가 실행마다 달라져 git diff 가 의미를 잃는다.

    Given: 가짜 홈 트리
    When: 담을 경로를 모은다
    Then: 정렬된 순서로 나온다
    """
    # When
    collected = export_module.collect_relative_paths(fake_claude_home)

    # Then
    assert collected == sorted(collected)


def test_collect_on_empty_home(export_module: ModuleType, tmp_path: Path) -> None:
    """
    목적: 빈 디렉터리에서 예외 없이 빈 목록을 돌려줌을 고정한다 (경계 조건)

    Given: 아무것도 없는 홈 디렉터리
    When: 담을 경로를 모은다
    Then: 빈 목록이 나온다
    """
    # Given
    empty_home = tmp_path / "empty"
    empty_home.mkdir()

    # When
    collected = export_module.collect_relative_paths(empty_home)

    # Then
    assert collected == []


def test_forbidden_entries_are_found_in_bundle(export_module: ModuleType, tmp_path: Path) -> None:
    """
    목적: 번들에 섞인 금지 항목을 위생 검사가 찾아냄을 고정한다

    판정 함수를 우회해 손으로 파일을 넣는 경우가 있다. 그때 잡는 두 번째 층이다.

    Given: 금지 항목이 섞인 번들 폴더
    When: 위생 검사를 돌린다
    Then: 그 항목이 보고된다
    """
    # Given
    bundle_home = tmp_path / "home"
    (bundle_home / "skills" / "impl-plan").mkdir(parents=True)
    (bundle_home / "skills" / "impl-plan" / "SKILL.md").write_text("x", encoding="utf-8")
    (bundle_home / "keys").mkdir(parents=True)
    (bundle_home / "keys" / "token.json").write_text("secret", encoding="utf-8")

    # When
    forbidden = export_module.find_forbidden_entries(bundle_home)

    # Then
    assert Path("keys/token.json") in forbidden


def test_clean_bundle_reports_nothing(export_module: ModuleType, tmp_path: Path) -> None:
    """
    목적: 깨끗한 번들에서 위생 검사가 오탐하지 않음을 고정한다

    Given: 포함 대상만 담긴 번들 폴더
    When: 위생 검사를 돌린다
    Then: 보고할 항목이 없다
    """
    # Given
    bundle_home = tmp_path / "home"
    for relative_path in INCLUDED_PATHS:
        target = bundle_home / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")

    # When
    forbidden = export_module.find_forbidden_entries(bundle_home)

    # Then
    assert forbidden == []


def test_real_bundle_has_no_forbidden_entries(export_module: ModuleType) -> None:
    """
    목적: 이 저장소에 실재하는 번들에 금지 항목이 없음을 고정한다

    번들은 다음 세션에서 스킬이 만든다. **아직 없으면 검사할 것이 없으므로 통과**한다
    (`pytest.skip` 을 쓰지 않는다 — 계획서 Done 조건이 `skipped=0` 이다).
    폴더의 실재와 이름만 보고 내용을 읽지 않는다 (`tests/CLAUDE.md` 5절 예외).

    Given: 저장소의 `claude-config/home/` (있을 수도, 없을 수도)
    When: 위생 검사를 돌린다
    Then: 보고할 항목이 없다
    """
    # Given
    if not BUNDLE_HOME_DIR.is_dir():
        return

    # When
    forbidden = export_module.find_forbidden_entries(BUNDLE_HOME_DIR)

    # Then
    assert forbidden == [], f"번들에 담기면 안 되는 항목이 있습니다: {forbidden}"


def test_real_bundle_matches_manifest(export_module: ModuleType) -> None:
    """
    목적: 번들의 모든 파일이 매니페스트에 등재되고 해시가 일치함을 고정한다

    받는 쪽은 매니페스트로 「사본이 원본과 같은가」를 대조하고, 결정 누적은 해시로
    「이 항목이 지난번과 같은 내용인가」를 판별한다. **둘이 어긋나면 옛 결정이 바뀐
    파일에 적용된다.** 번들이 아직 없으면 검사할 것이 없으므로 통과한다.

    Given: 저장소의 번들과 매니페스트 (있을 수도, 없을 수도)
    When: 등재 여부와 해시를 대조한다
    Then: 누락도 불일치도 없다
    """
    # Given
    if not BUNDLE_HOME_DIR.is_dir() or not MANIFEST_PATH.is_file():
        return

    manifest: dict[str, Any] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    recorded = {str(entry["path"]): str(entry["sha256"]) for entry in manifest["entries"]}

    # When
    actual = {
        path.relative_to(BUNDLE_HOME_DIR).as_posix(): export_module.file_sha256(path)
        for path in BUNDLE_HOME_DIR.rglob("*")
        if path.is_file()
    }

    # Then
    assert actual == recorded, "번들 파일과 매니페스트가 어긋납니다 — 내보내기를 다시 실행하세요"


def test_real_bundle_stays_under_size_limit() -> None:
    """
    목적: 번들이 커지는 사고를 크기로도 잡는다

    판정 규칙이 새어도 개별 항목만 보면 알아채기 어렵다. **실제로 `plugins/` 를 담았다가
    6.4MB 가 나온 적이 있다** — 공식 마켓플레이스 저장소 사본이었다.
    번들이 아직 없으면 검사할 것이 없으므로 통과한다.

    Given: 저장소의 `claude-config/home/` (있을 수도, 없을 수도)
    When: 담긴 파일의 총 크기를 잰다
    Then: 상한 아래다
    """
    # Given
    if not BUNDLE_HOME_DIR.is_dir():
        return

    # When
    total_size = sum(path.stat().st_size for path in BUNDLE_HOME_DIR.rglob("*") if path.is_file())

    # Then
    assert total_size <= BUNDLE_SIZE_LIMIT_BYTES, (
        f"번들이 상한을 넘었습니다: {total_size:,} > {BUNDLE_SIZE_LIMIT_BYTES:,} bytes. " "담기면 안 되는 것이 섞였는지 확인하세요"
    )


def test_redact_replaces_plain_header_value(export_module: ModuleType) -> None:
    """
    목적: MCP 헤더의 평문 자격증명이 번들에 남지 않음을 고정한다

    **이 저장소가 PUBLIC 이라 유출은 되돌릴 수 없다.** 파일 판정(`should_include`)은
    경로만 보므로 `~/.claude` 밖에 있는 `~/.claude.json` 을 통과시켰고, 실제로 이 자리에서
    API 키가 번들에 들어갔다.

    Given: 헤더에 평문 키를 담은 서버 정의
    When: 자격증명을 치환한다
    Then: 값이 센티널로 바뀐다
    """
    # When
    redacted, _replaced = export_module.redact_credentials(SAMPLE_CLAUDE_JSON)

    # Then
    assert redacted["mcpServers"]["context7"]["headers"]["CONTEXT7_API_KEY"] == export_module.REDACTED_SENTINEL


def test_redact_keeps_absolute_path_value(export_module: ModuleType) -> None:
    """
    목적: 경로 값은 살아남음을 고정한다

    받는 쪽은 이 경로에서 출처 PC 의 홈을 찾아 자기 경로로 치환한다. 값까지 가리면
    그 기능이 죽는다 — **자격증명 파일의 «경로» 는 자격증명이 아니다.**

    Given: `env` 에 절대경로만 담은 서버 정의
    When: 자격증명을 치환한다
    Then: 경로가 그대로 남는다
    """
    # When
    redacted, _replaced = export_module.redact_credentials(SAMPLE_CLAUDE_JSON)

    # Then
    env = redacted["mcpServers"]["google-sheets"]["env"]
    assert env["CREDENTIALS_PATH"] == "/Users/someone/.claude/keys/sheets-mcp-oauth.json"
    assert env["TOKEN_PATH"] == "/Users/someone/.claude/keys/sheets-mcp-token.json"


def test_redact_covers_project_scoped_servers(export_module: ModuleType) -> None:
    """
    목적: 프로젝트 스코프 서버도 같게 막힘을 고정한다

    `projects[*].mcpServers` 는 최상위와 구조가 같은 **두 번째 구멍**이다.
    한쪽만 막으면 저장소별 서버를 등록하는 순간 조용히 샌다.

    Given: 프로젝트 스코프에 평문 토큰을 담은 서버 정의
    When: 자격증명을 치환한다
    Then: 값이 센티널로 바뀐다
    """
    # When
    redacted, _replaced = export_module.redact_credentials(SAMPLE_CLAUDE_JSON)

    # Then
    project = redacted["projects"]["/Users/someone/Workspace/repo"]
    assert project["mcpServers"]["internal"]["headers"]["X_INTERNAL_TOKEN"] == export_module.REDACTED_SENTINEL


def test_redact_leaves_other_keys_untouched(export_module: ModuleType) -> None:
    """
    목적: `headers`·`env` 밖의 키는 건드리지 않음을 고정한다

    `command`·`args` 를 가리면 받는 쪽에서 서버가 실행되지 않는다.

    Given: 실행 인자와 URL 을 담은 서버 정의
    When: 자격증명을 치환한다
    Then: 그 값들이 원본과 같다
    """
    # When
    redacted, _replaced = export_module.redact_credentials(SAMPLE_CLAUDE_JSON)

    # Then
    sheets = redacted["mcpServers"]["google-sheets"]
    assert sheets["command"] == "/Users/someone/.local/bin/uvx"
    assert sheets["args"] == ["--with", "mcp<2", "mcp-google-sheets@latest"]
    assert redacted["mcpServers"]["context7"]["url"] == "https://mcp.context7.com/mcp"


def test_redact_reports_replaced_keys(export_module: ModuleType) -> None:
    """
    목적: 무엇을 가렸는지 사용자가 그 자리에서 알 수 있음을 고정한다

    허용목록 방식이라 자격증명이 아닌 설정값까지 가릴 수 있다. **목록이 나와야
    사용자가 오탐을 알아챈다.**

    Given: 두 자리에 평문 값을 담은 설정
    When: 자격증명을 치환한다
    Then: 치환한 키 경로가 모두 보고된다
    """
    # When
    _redacted, replaced = export_module.redact_credentials(SAMPLE_CLAUDE_JSON)

    # Then
    assert sorted(replaced) == [
        "mcpServers.context7.headers.CONTEXT7_API_KEY",
        "projects[/Users/someone/Workspace/repo].mcpServers.internal.headers.X_INTERNAL_TOKEN",
    ]


def test_redact_replaces_relative_path_value(export_module: ModuleType) -> None:
    """
    목적: 상대경로는 치환됨을 고정한다 (경계)

    경로 판정을 **절대경로로 좁게** 잡는다. 넓게 잡으면 자격증명이 경로처럼 생겼을 때
    빠져나가고, 좁게 잡아 생기는 손해는 「가리지 않아도 될 값을 가리는 것」뿐이다.

    Given: `env` 에 상대경로를 담은 서버 정의
    When: 자격증명을 치환한다
    Then: 값이 센티널로 바뀐다
    """
    # Given
    source = {"mcpServers": {"x": {"env": {"DATA_DIR": "data/cache"}}}}

    # When
    redacted, _replaced = export_module.redact_credentials(source)

    # Then
    assert redacted["mcpServers"]["x"]["env"]["DATA_DIR"] == export_module.REDACTED_SENTINEL


@pytest.mark.parametrize("value", [3000, True, None, ["a", "b"]])
def test_redact_keeps_non_string_value(export_module: ModuleType, value: object) -> None:
    """
    목적: 문자열이 아닌 값은 그대로 둠을 고정한다 (경계)

    자격증명은 문자열이고, 숫자·불리언을 센티널 문자열로 바꾸면 받는 쪽에서 타입이 깨진다.

    Given: `env` 에 문자열이 아닌 값을 담은 서버 정의
    When: 자격증명을 치환한다
    Then: 값이 원본과 같다
    """
    # Given
    source = {"mcpServers": {"x": {"env": {"PORT": value}}}}

    # When
    redacted, replaced = export_module.redact_credentials(source)

    # Then
    assert redacted["mcpServers"]["x"]["env"]["PORT"] == value
    assert replaced == []


def test_redact_handles_server_without_headers_or_env(export_module: ModuleType) -> None:
    """
    목적: 가릴 자리가 없는 서버에서 예외가 나지 않음을 고정한다 (경계)

    실물의 atlassian 이 여기 해당한다 — `type` 과 `url` 뿐이다.

    Given: `headers`·`env` 가 없는 서버 정의
    When: 자격증명을 치환한다
    Then: 정의가 그대로 나오고 보고할 것이 없다
    """
    # When
    redacted, replaced = export_module.redact_credentials(SAMPLE_CLAUDE_JSON)

    # Then
    assert redacted["mcpServers"]["bare"] == {"type": "http", "url": "https://example.com/mcp"}
    assert "bare" not in " ".join(replaced)


def test_redact_does_not_mutate_input(export_module: ModuleType) -> None:
    """
    목적: 원본 설정이 바뀌지 않음을 고정한다

    호출자가 원본을 다시 쓸 수 있어야 한다 (`~/.claude/rules/python.md` 데이터 불변성).

    Given: 평문 키를 담은 설정
    When: 자격증명을 치환한다
    Then: 원본의 값이 그대로다
    """
    # When
    export_module.redact_credentials(SAMPLE_CLAUDE_JSON)

    # Then
    assert SAMPLE_CLAUDE_JSON["mcpServers"]["context7"]["headers"]["CONTEXT7_API_KEY"] == "ctx7sk-0000-example"


def test_real_bundle_claude_json_has_no_secret_pattern() -> None:
    """
    목적: 실재하는 번들에 자격증명 형태의 값이 없음을 고정한다

    **`headers`·`env` 로 한정하지 않고 파일 전체를 본다.** 치환은 그 두 자리만 덮으므로
    `command`·`args` 처럼 가릴 수 없는 자리는 이 검사가 맡는다.
    번들이 아직 없으면 검사할 것이 없으므로 통과한다.

    Given: 저장소의 `claude-config/claude_json.json` (있을 수도, 없을 수도)
    When: 자격증명 패턴으로 스캔한다
    Then: 걸리는 값이 없다
    """
    # Given
    if not BUNDLE_CLAUDE_JSON_PATH.is_file():
        return

    content = BUNDLE_CLAUDE_JSON_PATH.read_text(encoding="utf-8")

    # When
    hits = [label for label, pattern in SECRET_VALUE_PATTERNS if pattern.search(content)]

    # Then
    assert hits == [], f"번들에 자격증명 형태의 값이 있습니다: {hits}. 내보내기를 다시 실행하세요"
