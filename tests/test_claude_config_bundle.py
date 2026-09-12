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
    # 로그 제외는 조각 «전체 일치» 다. 이름에 log 가 들어갔을 뿐인 문서는 계속 담긴다
    Path("hooks/changelog.md"),
    # 자격증명 판정이 «죽이면 안 되는» 것들. 이쪽 실패가 유출보다 조용하다 —
    # 설정 하나가 소리 없이 안 넘어가면 받는 PC 에서 원인 모를 동작 차이로 남는다.
    #
    # 셋 다 «문서·모듈 확장자 탈출구» 가 지킨다. 그 장치가 없으면 자격증명 표식을
    # 구분자까지 넓힐 수 없다 — `key-rotation-guide.md` 가 `key` 조각을 갖기 때문이다.
    # 탈출구는 «구분자» 로 쪼갠 조각에만 걸린다 — 점 조각이 표식이면 `env.py` 처럼 막힌다
    Path("db/api-key-format.md"),
    Path("db/key-rotation-guide.md"),
    Path("tools/api_key_helper.py"),
    # 런타임 기록 판정에도 같은 탈출구가 있다 — 없으면 이 둘이 조용히 사라진다
    Path("commands/log.md"),
    Path("hooks/lock.py"),
    # `lock` 을 조각 판정에 넣으면 이것이 조용히 사라진다. 막을 것은 도트파일 `.lock` 하나뿐이다
    Path("tools/xlsx/poetry.lock"),
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
    # 런타임 로그. 허용 폴더 «어디에» 있든 확장자로 걸러야 한다 —
    # 허용목록이 폴더째 담으므로 새 도구가 로그를 만들 때마다 반복된다
    (Path("hooks/toast.log"), "알림 훅의 런타임 로그"),
    (Path("db/query.log"), "런타임 로그"),
    (Path("tools/msg/convert.log"), "런타임 로그"),
    # 자격증명과 «같은 규율» 로 판정한다 — `.suffix` 로 재던 때는 아래가 전부 빠져나갔다
    (Path("hooks/.log"), "도트파일 로그 (`.suffix` 가 빈 문자열이다)"),
    (Path("hooks/toast.LOG"), "대문자 로그"),
    (Path("db/audit.JSONL"), "대문자 감사 로그"),
    (Path("hooks/toast.log.1"), "로테이트된 로그"),
    (Path("hooks/.LOCK"), "대문자 상태 파일"),
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
    # 도트파일 — `Path('.env').suffix` 가 «빈 문자열» 이라 확장자 판정이 한 번도 발동하지 않았다.
    # 파이썬은 앞의 점을 확장자 구분자가 아니라 이름의 일부로 본다 [실측] 2026-09-12
    Path("db/.env"),
    Path("tools/x/.env"),
    Path("db/.env.local"),
    # 다중 확장자 — `.suffix` 는 «마지막» 것만 준다 (`acme-prd.env.local` -> `.local`)
    Path("db/acme-prd.env.local"),
    Path("db/key.pem.bak"),
    Path("db/server.key.old"),
    # 점으로 시작하지 않는 형태. `CREDENTIAL_NAMES` 가 `.credentials.json` 만 알고 있었다
    Path("db/credentials.json"),
    # 대소문자 — mac·윈도우는 파일시스템이 구별하지 않아 `.ENV` 와 `.env` 가 같은 파일이다
    Path("db/.ENV"),
    Path("db/PRIVATE.KEY"),
    Path("db/acme.Env.local"),
    # 표식이 «첫» 토큰인 형태. `key.json` 은 GCP 서비스계정 키의 표준 파일명이다
    Path("db/key.json"),
    Path("db/env.json"),
    Path("db/key"),
    # 표식 토큰이 아예 없는 고전 이름
    Path("db/id_rsa"),
    Path("db/.netrc"),
    Path("db/.pgpass"),
    Path("db/.npmrc"),
    # 견본 표식을 붙인 우회. 예외가 «규칙» 이던 때는 이 셋이 전부 빠져나갔다 —
    # 이름 뒤에 `.sample` 만 붙이면 자격증명 판정이 통째로 꺼졌다. 지금은 견본 예외가 없다
    Path("db/real-secret.key.sample"),
    Path("db/credentials.json.example"),
    Path("db/.env.template"),
    # 견본이라도 담지 않는다. 실물 `acme-prd.env.example` 에 운영 DB 의 host·port·name 이
    # 채워져 있었다 — 「견본이면 비어 있다」는 전제가 틀렸다
    Path("db/acme-prd.env.example"),
    # 구분자로 이어진 형태. `.` 으로만 쪼개던 때는 전부 빠져나갔다
    Path("db/.env-prod"),
    Path("db/.env_old"),
    Path("db/env_local"),
    Path("db/id_rsa_backup"),
    Path("db/credentials-prod.json"),
    Path("db/.npmrc-backup"),
    # 고전 이름이 «뒤» 에 붙은 형태. 접두로만 맞추던 때는 전부 빠져나갔다
    Path("db/prod.netrc"),
    Path("db/backup.id_rsa"),
    Path("db/old-id_rsa"),
    # 문서·모듈 확장자를 씌운 우회. `.sh` 는 `export API_KEY=...` 의 표준 그릇이고
    # `.txt` 는 토큰을 붙여넣어 두는 자리다 — 둘 다 탈출구에서 뺐다
    Path("db/.env.txt"),
    Path("db/credentials.txt"),
    Path("db/api-key.txt"),
    Path("db/aws.key.sh"),
    Path("db/env.sh"),
    # 점 조각이 표식이면 문서 확장자여도 막는다
    Path("db/server.pem.md"),
    Path("tools/env.py"),
    # 폴더명 대소문자. mac 은 파일시스템이 구별하지 않아 `Keys/` 와 `keys/` 가 같은 폴더다
    Path("tools/Keys/oauth.json"),
    # 자격증명을 «폴더로 묶은» 형태. 이름 판정은 파일명만 보므로 폴더가 따로 막아야 한다
    Path("db/credentials/prod.json"),
    Path("tools/secrets/api.json"),
    # 이 PC 의 실제 자격증명이 쓰는 이름. 지금은 `keys/` 가 막지만 허용 폴더 밖에 쓰이면
    # 이름 판정 말고는 막을 것이 없다
    Path("tools/msg/token.json"),
    Path("db/client-secret.json"),
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
        # 토큰을 url 에 싣는 형태. `headers`·`env` 만 훑던 때는 이 자리가 통째로 샜다
        "query-token": {"type": "http", "url": "https://mcp.vendor.com/mcp?api_key=SECRET&mode=fast"},
        "userinfo-token": {"type": "http", "url": "https://someone:token-value@host.example.com/mcp"},
    },
    "projects": {
        "/Users/someone/Workspace/repo": {
            "mcpServers": {
                "internal": {
                    "type": "http",
                    "url": "https://internal.example.com/mcp?token=project-secret",
                    "headers": {"X_INTERNAL_TOKEN": "internal-secret-value"},
                }
            }
        }
    },
}

# 자격증명 형태를 잡는 그물의 «두 번째 겹».
# 치환은 `headers`·`env` 와 `url` 의 query·userinfo·fragment 를 덮는다.
# `command`·`args` 와 **url 의 경로 구간**은 그쪽이 가리지 못하므로 이 스캔이 맡는다.
# **금지목록이라 새 형식은 놓칠 수 있다** — 치환의 대체가 아니라 보완이다
SECRET_VALUE_PATTERNS = (
    ("Context7", re.compile(r"ctx7sk-")),
    ("OpenAI 계열", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("GitHub", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("AWS", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Slack", re.compile(r"xox[baprs]-")),
    ("PEM 개인키", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)


# 제외한 venv 를 재는 표본. `site-packages` 경로를 키로, 그 안의 `dist-info` 이름을 값으로 둔다.
# `pip` 는 만드는 방식에 따라 있기도 없기도 해서(`uv` 는 넣지 않는다) 일부러 섞었다
FAKE_VENV_DIST_INFOS: dict[str, tuple[str, ...]] = {
    "tools/xlsx/venv/lib/python3.12/site-packages": ("openpyxl-3.1.5", "pillow-12.3.0", "pip-24.0"),
    "tools/pptx/venv/lib/python3.12/site-packages": ("python_pptx-1.0.2", "lxml-6.1.3"),
    "db/venv/Lib/site-packages": ("pymysql-1.2.0",),
}

# venv 안에 또 `venv` 이름이 나오는 자리. 설치된 배포판이 이런 이름을 쓸 수 있다
NESTED_VENV_PATH = "tools/xlsx/venv/lib/python3.12/site-packages/virtualenv/venv"

# 위 표본에서 나와야 하는 결과. 경로도 패키지도 정렬되며, 이름은 설치에 쓸 수 있는 형태다
EXPECTED_VENV_INVENTORY = (
    {"path": "db/venv", "packages": ["pymysql==1.2.0"]},
    {"path": "tools/broken/venv", "packages": []},
    {"path": "tools/pptx/venv", "packages": ["lxml==6.1.3", "python-pptx==1.0.2"]},
    {"path": "tools/xlsx/venv", "packages": ["openpyxl==3.1.5", "pillow==12.3.0"]},
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


def test_redact_replaces_url_query_value(export_module: ModuleType) -> None:
    """
    목적: url 에 실린 자격증명이 번들에 남지 않음을 고정한다

    HTTP 형 MCP 서버는 토큰을 url 에 싣는 방식이 흔한데, 치환이 `headers`·`env` 두 블록만
    훑어 이 자리가 통째로 샜다. 헤더에서 Context7 키가 샜던 것과 **같은 계층**의 구멍이다.

    Given: query 에 토큰을 담은 서버 정의
    When: 자격증명을 치환한다
    Then: 값만 센티널로 바뀌고 **키와 접속 정보는 남는다** — 받는 쪽이 서버에 접속해야 한다
    """
    # When
    redacted, _replaced = export_module.redact_credentials(SAMPLE_CLAUDE_JSON)

    # Then
    url = redacted["mcpServers"]["query-token"]["url"]
    assert url.startswith("https://mcp.vendor.com/mcp?")
    assert "SECRET" not in url
    assert "fast" not in url
    assert url.count(export_module.REDACTED_SENTINEL) == 2
    assert "api_key=" in url and "mode=" in url


def test_redact_replaces_url_userinfo(export_module: ModuleType) -> None:
    """
    목적: url 의 `user:password@` 구간이 가려짐을 고정한다

    Given: userinfo 에 토큰을 담은 서버 정의
    When: 자격증명을 치환한다
    Then: 호스트는 남고 userinfo 만 센티널이 된다
    """
    # When
    redacted, _replaced = export_module.redact_credentials(SAMPLE_CLAUDE_JSON)

    # Then
    url = redacted["mcpServers"]["userinfo-token"]["url"]
    assert "token-value" not in url
    assert "someone" not in url
    assert url.endswith("@host.example.com/mcp")


def test_redact_keeps_url_without_secret(export_module: ModuleType) -> None:
    """
    목적: 비밀이 없는 url 은 **손대지 않음**을 고정한다

    가릴 것이 없는데 모양이 달라지면 받는 쪽 결정의 해시가 어긋나 불필요하게 다시 물어진다.

    Given: query 도 userinfo 도 없는 서버 정의
    When: 자격증명을 치환한다
    Then: url 이 원본 그대로다
    """
    # When
    redacted, replaced = export_module.redact_credentials(SAMPLE_CLAUDE_JSON)

    # Then
    assert redacted["mcpServers"]["context7"]["url"] == "https://mcp.context7.com/mcp"
    assert redacted["mcpServers"]["bare"]["url"] == "https://example.com/mcp"
    assert "mcpServers.context7.url" not in replaced


def test_redact_covers_url_in_project_scope(export_module: ModuleType) -> None:
    """
    목적: 프로젝트 스코프 서버의 url 에도 치환이 걸림을 고정한다

    Given: 프로젝트 스코프에 url 토큰을 담은 서버
    When: 자격증명을 치환한다
    Then: 값이 센티널로 바뀌고 가린 목록에 그 경로가 실린다
    """
    # When
    redacted, replaced = export_module.redact_credentials(SAMPLE_CLAUDE_JSON)

    # Then
    project = redacted["projects"]["/Users/someone/Workspace/repo"]["mcpServers"]["internal"]
    assert "project-secret" not in project["url"]
    assert "projects[/Users/someone/Workspace/repo].mcpServers.internal.url" in replaced


def test_redact_does_not_mutate_input_url(export_module: ModuleType) -> None:
    """
    목적: 치환이 입력을 제자리에서 고치지 않음을 고정한다 (기존 계약과 같다)

    Given: url 에 토큰을 담은 서버 정의
    When: 자격증명을 치환한다
    Then: 원본 딕셔너리의 url 이 그대로다
    """
    # When
    export_module.redact_credentials(SAMPLE_CLAUDE_JSON)

    # Then
    assert (
        SAMPLE_CLAUDE_JSON["mcpServers"]["query-token"]["url"] == "https://mcp.vendor.com/mcp?api_key=SECRET&mode=fast"
    )


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

    Given: 헤더·url 여러 자리에 평문 값을 담은 설정
    When: 자격증명을 치환한다
    Then: 치환한 키 경로가 모두 보고된다 — 비밀이 없는 url 은 목록에 없다
    """
    # When
    _redacted, replaced = export_module.redact_credentials(SAMPLE_CLAUDE_JSON)

    # Then
    assert sorted(replaced) == [
        "mcpServers.context7.headers.CONTEXT7_API_KEY",
        "mcpServers.query-token.url",
        "mcpServers.userinfo-token.url",
        "projects[/Users/someone/Workspace/repo].mcpServers.internal.headers.X_INTERNAL_TOKEN",
        "projects[/Users/someone/Workspace/repo].mcpServers.internal.url",
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


@pytest.fixture
def fake_claude_home_with_venvs(tmp_path: Path) -> Path:
    """venv 가 섞인 가짜 `~/.claude` 트리를 만든다.

    실물 구조를 본떴다 — POSIX 레이아웃과 윈도우 레이아웃, 이름에 밑줄이 든 배포판,
    부트스트랩 패키지, `site-packages` 가 없는 깨진 venv, 그리고 venv **안** 에 또
    `venv` 이름의 폴더가 있는 경우.

    Args:
        tmp_path: pytest가 테스트마다 새로 만드는 임시 디렉터리

    Returns:
        Path: 가짜 `~/.claude` 루트
    """
    home = tmp_path / "claude-home"

    for site_packages, dist_infos in FAKE_VENV_DIST_INFOS.items():
        for dist_info in dist_infos:
            (home / site_packages / f"{dist_info}.dist-info").mkdir(parents=True, exist_ok=True)

    # site-packages 가 없는 venv. 「없었다」와 「못 읽었다」가 구별되어야 한다
    (home / "tools" / "broken" / "venv").mkdir(parents=True, exist_ok=True)

    # venv 안의 `venv` 이름 폴더. 배포판이 이런 이름을 쓰면 중복으로 세어진다
    (home / NESTED_VENV_PATH).mkdir(parents=True, exist_ok=True)

    return home


def test_venv_inventory_reports_path_and_packages(export_module: ModuleType, fake_claude_home_with_venvs: Path) -> None:
    """
    목적: 제외한 venv 의 경로와 설치 패키지가 사실로 기록되는 것을 고정한다

    **받는 쪽은 이 목록만 보고 재생성한다.** 권한 규칙과 스크립트 import 는 둘 다
    간접 증거라서, venv 뿐인 폴더에 권한 규칙까지 없으면 어느 쪽에도 걸리지 않는다
    (실측 2026-09-09: `tools/xlsx` 는 규칙으로만, `tools/pptx` 는 import 로만 겨우 걸렸다).

    Given: venv 가 셋 있는 가짜 홈
    When: venv 목록을 수집한다
    Then: 경로와 패키지가 정렬된 채로 나온다
    """
    # Given
    home = fake_claude_home_with_venvs

    # When
    inventory = export_module.collect_excluded_venvs(home)

    # Then
    assert inventory == list(EXPECTED_VENV_INVENTORY)


def test_venv_inventory_reads_windows_layout(export_module: ModuleType, fake_claude_home_with_venvs: Path) -> None:
    """
    목적: 윈도우 레이아웃(`Lib/site-packages`)의 venv 도 읽는 것을 고정한다

    보내는 쪽이 윈도우면 경로가 `lib/python3.12/` 가 아니라 `Lib/` 다.
    한쪽만 보면 그 PC 의 venv 가 통째로 빈 목록이 되어 **없는 것처럼 보인다.**

    Given: `db/venv` 가 윈도우 레이아웃인 가짜 홈
    When: venv 목록을 수집한다
    Then: 그 venv 의 패키지가 비어 있지 않다
    """
    # Given
    home = fake_claude_home_with_venvs

    # When
    inventory = export_module.collect_excluded_venvs(home)

    # Then
    windows_venv = next(entry for entry in inventory if entry["path"] == "db/venv")
    assert windows_venv["packages"] == ["pymysql==1.2.0"]


def test_venv_inventory_drops_bootstrap_packages(export_module: ModuleType, fake_claude_home_with_venvs: Path) -> None:
    """
    목적: venv 를 만들 때 딸려오는 패키지가 목록에서 빠지는 것을 고정한다

    `pip` 는 만드는 방식에 따라 있기도 없기도 하다(`uv` 는 넣지 않고 `python -m venv` 는 넣는다).
    그대로 실으면 **두 PC 의 목록이 만든 방식 때문에 달라 보인다.**

    Given: `pip` 가 설치된 venv 가 있는 가짜 홈
    When: venv 목록을 수집한다
    Then: `pip` 가 목록에 없다
    """
    # Given
    home = fake_claude_home_with_venvs

    # When
    inventory = export_module.collect_excluded_venvs(home)

    # Then
    xlsx_venv = next(entry for entry in inventory if entry["path"] == "tools/xlsx/venv")
    assert not [package for package in xlsx_venv["packages"] if package.startswith("pip==")]


def test_venv_inventory_normalizes_package_name(export_module: ModuleType, fake_claude_home_with_venvs: Path) -> None:
    """
    목적: 배포판 이름이 설치에 쓸 수 있는 형태로 정규화되는 것을 고정한다

    `dist-info` 폴더는 이름을 밑줄로 적는다(`python_pptx-1.0.2.dist-info`).
    **받는 쪽은 이 목록을 그대로 설치 명령에 넣으므로** 하이픈으로 되돌린다.

    Given: `python_pptx` 가 설치된 venv 가 있는 가짜 홈
    When: venv 목록을 수집한다
    Then: `python-pptx==1.0.2` 로 나온다
    """
    # Given
    home = fake_claude_home_with_venvs

    # When
    inventory = export_module.collect_excluded_venvs(home)

    # Then
    pptx_venv = next(entry for entry in inventory if entry["path"] == "tools/pptx/venv")
    assert "python-pptx==1.0.2" in pptx_venv["packages"]


def test_venv_inventory_ignores_nested_venv(export_module: ModuleType, fake_claude_home_with_venvs: Path) -> None:
    """
    목적: venv 안의 `venv` 이름 폴더를 별도 venv 로 세지 않는 것을 고정한다

    설치된 배포판이 그런 이름을 쓰면 **하나의 venv 가 둘로 보이고**, 받는 쪽은
    존재하지 않는 도구를 재생성하려 든다.

    Given: `site-packages` 아래에 `venv` 폴더가 있는 가짜 홈
    When: venv 목록을 수집한다
    Then: 그 경로가 목록에 없다
    """
    # Given
    home = fake_claude_home_with_venvs

    # When
    inventory = export_module.collect_excluded_venvs(home)

    # Then
    assert NESTED_VENV_PATH not in [entry["path"] for entry in inventory]


def test_venv_inventory_keeps_broken_venv(export_module: ModuleType, fake_claude_home_with_venvs: Path) -> None:
    """
    목적: `site-packages` 를 못 찾은 venv 도 경로는 남기는 것을 고정한다

    **「패키지가 없었다」와 「읽지 못했다」는 다르다.** 경로마저 지우면 받는 쪽은
    그 도구가 있었다는 사실 자체를 모른다.

    Given: `site-packages` 가 없는 venv 가 있는 가짜 홈
    When: venv 목록을 수집한다
    Then: 경로는 있고 패키지는 빈 목록이다
    """
    # Given
    home = fake_claude_home_with_venvs

    # When
    inventory = export_module.collect_excluded_venvs(home)

    # Then
    broken_venv = next(entry for entry in inventory if entry["path"] == "tools/broken/venv")
    assert broken_venv["packages"] == []


def test_venv_inventory_on_home_without_venv(export_module: ModuleType, fake_claude_home: Path) -> None:
    """
    목적: venv 가 하나도 없는 홈에서 빈 목록이 나오는 것을 고정한다

    venv 가 없는 것은 정상이므로 예외가 아니다. **0건도 결과다.**

    Given: venv 파일은 있지만 `site-packages` 트리가 없는 가짜 홈
    When: venv 목록을 수집한다
    Then: `db/venv` 와 `tools/xlsx/venv` 가 패키지 없이 잡히고 그 밖은 없다
    """
    # Given
    home = fake_claude_home

    # When
    inventory = export_module.collect_excluded_venvs(home)

    # Then
    assert [entry["path"] for entry in inventory] == ["db/venv", "tools/xlsx/venv"]


def test_venv_inventory_on_empty_home(export_module: ModuleType, tmp_path: Path) -> None:
    """
    목적: 빈 홈에서 빈 목록이 나오는 것을 고정한다 (경계 조건)

    Given: 아무것도 없는 폴더
    When: venv 목록을 수집한다
    Then: 빈 목록이다
    """
    # Given
    home = tmp_path / "empty-home"
    home.mkdir()

    # When
    inventory = export_module.collect_excluded_venvs(home)

    # Then
    assert inventory == []


def test_venv_inventory_rejects_missing_home(export_module: ModuleType, tmp_path: Path) -> None:
    """
    목적: 없는 폴더를 넘기면 즉시 실패하는 것을 고정한다

    `collect_relative_paths()` 와 같은 계약이다. 조용히 빈 목록을 돌려주면
    **「venv 가 없다」와 「홈을 못 찾았다」가 구별되지 않는다.**

    Given: 존재하지 않는 경로
    When: venv 목록을 수집한다
    Then: `ValueError` 가 난다
    """
    # Given
    missing = tmp_path / "does-not-exist"

    # When / Then
    with pytest.raises(ValueError, match="설정 폴더"):
        export_module.collect_excluded_venvs(missing)


def test_manifest_carries_venv_inventory(
    export_module: ModuleType, fake_claude_home_with_venvs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    목적: 매니페스트가 venv 목록을 싣는 것을 고정한다

    **받는 쪽이 읽는 자리는 매니페스트다.** 수집만 되고 실리지 않으면 아무 소용이 없다.
    `_source_identity()` 가 실제 `~/.claude.json` 을 읽으므로 임시 파일로 격리한다.

    Given: venv 가 있는 가짜 홈
    When: 매니페스트를 만든다
    Then: `excluded_venvs` 에 목록이 들어 있다
    """
    # Given
    home = fake_claude_home_with_venvs
    fake_claude_json = tmp_path / "claude.json"
    fake_claude_json.write_text(json.dumps({"machineID": "test"}), encoding="utf-8")
    monkeypatch.setattr(export_module, "CLAUDE_JSON_PATH", fake_claude_json)

    # When
    manifest = export_module.build_manifest(home, [])

    # Then
    assert manifest["excluded_venvs"] == list(EXPECTED_VENV_INVENTORY)


def test_real_bundle_manifest_carries_venv_inventory() -> None:
    """
    목적: 실재하는 번들의 매니페스트에 venv 목록 자리가 있음을 고정한다

    옛 번들에는 이 키가 없다. **다시 내보내면 생긴다** — 그때부터 받는 쪽이
    조사 없이 재생성한다. 번들이 아직 없으면 검사할 것이 없으므로 통과한다.

    Given: 저장소의 매니페스트 (있을 수도, 없을 수도)
    When: 키를 확인한다
    Then: `excluded_venvs` 가 리스트로 있다
    """
    # Given
    if not MANIFEST_PATH.is_file():
        return

    manifest: dict[str, Any] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    # When
    inventory = manifest.get("excluded_venvs")

    # Then
    assert isinstance(inventory, list), "매니페스트에 excluded_venvs 가 없습니다. 내보내기를 다시 실행하세요"
