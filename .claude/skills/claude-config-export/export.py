"""전역 Claude 설정을 이 저장소의 고정 경로로 내보낸다.

`~/.claude` 는 git 저장소가 아니어서 다른 PC 로 옮길 통로가 없다. 이 스크립트가 옮길
가치가 있는 것만 골라 `claude-config/` 에 사본을 만들고, 받는 쪽이 대조할 수 있도록
항목별 해시를 매니페스트에 남긴다.

**골라 담는 것이 핵심이다.** `~/.claude` 는 574MB 지만 그중 옮길 것은 약 190KB 뿐이고,
나머지는 세션 이력·플랫폼 venv·감사로그다. 그래서 판정은 **허용목록** 방식이다 —
금지목록 방식이면 Claude Code 가 새 폴더를 만들 때마다 조용히 딸려온다.

자격증명은 허용목록보다 «먼저» 막는다. 이 저장소는 PUBLIC 이라 한 번 커밋되면 파일을
지워도 git 이력에 남는다. 허용목록을 넓히는 변경이 자격증명까지 열어주면 안 된다.

포함·제외 판정은 `tests/test_claude_config_bundle.py` 가 고정한다.
"""

import argparse
import copy
import hashlib
import json
import platform
import re
import shutil
import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

# 저장소 루트. 이 파일은 <루트>/.claude/skills/claude-config-export/export.py 에 있다
PROJECT_ROOT = Path(__file__).resolve().parents[3]

CLAUDE_HOME = Path.home() / ".claude"
CLAUDE_JSON_PATH = Path.home() / ".claude.json"

# 번들이 놓이는 고정 경로. 받는 쪽 스킬이 이 경로를 스스로 찾는다
BUNDLE_DIR = PROJECT_ROOT / "claude-config"
BUNDLE_HOME_DIR = BUNDLE_DIR / "home"
BUNDLE_CLAUDE_JSON_PATH = BUNDLE_DIR / "claude_json.json"
MANIFEST_PATH = BUNDLE_DIR / "MANIFEST.json"
README_PATH = BUNDLE_DIR / "README.md"
DECISIONS_DIR = BUNDLE_DIR / "decisions"

KST = ZoneInfo("Asia/Seoul")

# --- 판정 규칙 -------------------------------------------------------------
# 아래 넷의 우선순위: 자격증명 > 금지 > 허용. 자격증명이 가장 앞이어야 허용을 넓혀도 막힌다

# 최상위에서 이 파일들만 담는다
ALLOW_TOP_LEVEL_FILES = frozenset({"CLAUDE.md", "settings.json"})

# 최상위에서 이 폴더들만 담는다 (그 아래는 금지 규칙에 걸리지 않는 한 전부)
#
# `plugins/` 가 빠진 이유 — 실측 6.4MB / 441개인데 실체가 github `anthropics/claude-plugins-official`
# 의 사본이다. `officialMarketplaceAutoInstalled` 가 말하듯 받는 쪽에서 자동으로 다시 설치되고,
# 수동 설치한 플러그인은 없다. `known_marketplaces.json` 도 `installLocation` 에 절대경로를 담고 있어
# 옮기면 변환 대상만 는다.
ALLOW_TOP_LEVEL_DIRS = frozenset({"skills", "commands", "rules", "hooks", "tools", "db"})

# 경로 어느 깊이에든 이 이름의 폴더가 있으면 담지 않는다.
# 최상위 것들은 허용목록에 없어 이미 걸리지만, 허용을 넓힐 때를 대비해 이름으로도 막는다
DENY_SEGMENTS = frozenset(
    {
        "venv",
        "__pycache__",
        "projects",
        "sessions",
        "file-history",
        "shell-snapshots",
        "session-env",
        "cache",
        "ide",
        "daemon",
        "jobs",
        "paste-cache",
        "downloads",
        "backups",
    }
)

# `site-packages` 가 놓이는 자리. POSIX 와 윈도우의 레이아웃이 다르므로 둘 다 본다 —
# 한쪽만 보면 그 PC 의 venv 가 통째로 빈 목록이 되어 「없는 것」처럼 보인다
SITE_PACKAGES_GLOBS = ("lib/python*/site-packages", "Lib/site-packages")

# venv 를 만들 때 딸려오는 것들. 만드는 방식에 따라 있기도 없기도 해서(`uv` 는 넣지 않고
# `python -m venv` 는 넣는다) 목록에 실으면 **두 PC 의 패키지가 만든 방식 때문에 달라 보인다**
VENV_BOOTSTRAP_PACKAGES = frozenset({"pip", "setuptools", "wheel", "pkg-resources"})

# 실행하며 쌓이는 기록과 상태 파일의 표식 — 감사로그·세션 이력(`jsonl`) · 런타임 로그(`log`) ·
# 잠금(`lock`). 이름을 `.` 으로 쪼갠 조각과 맞춘다.
#
# 조각으로 막는 이유는 허용목록이 폴더를 «통째로» 담기 때문이다. `hooks/` 에 훅을 하나 더
# 만들면 그 훅이 남기는 로그까지 따라오므로, 파일 이름으로 막으면 다음 도구에서 또 샌다.
# 실제로 `hooks/toast.log` 가 그렇게 담겼다 [실측] 2026-09-12.
#
# **`.suffix` 로 재던 때는 절반만 막혔다** — 도트파일(`hooks/.log`)에서 빈 문자열이 되고,
# 대문자(`toast.LOG` · `audit.JSONL`)와 로테이트(`toast.log.1`)를 놓쳤다. `_is_credential` 이
# 겪은 것과 같은 결함이라 같은 규율로 통일했다.
#
# 담으면 두 가지가 깨진다 — 받는 PC 에서 뜻이 없고, **매번 달라져 `git diff` 검토를 무력화한다.**
# 설정이 한 글자도 안 바뀐 내보내기에서도 이 파일이 바뀌어, SKILL.md 「실행 후」 1단계가
# 무엇이 실제로 바뀌었는지 가려내지 못하게 된다.
#
# 자격증명과 달리 `-`·`_` 로는 쪼개지 않는다 — 넓혀야 할 사례가 확인되지 않았고,
# `package-lock.json` 처럼 정상 파일이 걸릴 여지만 는다.
RUNTIME_RECORD_TOKENS = frozenset({"jsonl", "log"})

# 상태 파일. **`lock` 을 위 조각 판정에 넣지 않는다** — 그러면 `poetry.lock`·`uv.lock` 처럼
# «옮겨야 하는» 의존성 고정 파일이 조용히 사라진다. 막을 것은 도트파일 하나뿐이라 이름으로 맞춘다
DENY_NAMES = frozenset({".lock"})

# 손으로 만든 백업본 (`CLAUDE.md.bak-20260909` 등)
BACKUP_NAME_PATTERN = re.compile(r"\.bak-")

# 자격증명 — 유출이 되돌려지지 않으므로 허용목록보다 먼저 판정한다.
# **폴더 이름도 본다** — 파일 판정은 이름만 보므로 `db/credentials/prod.json` 처럼 폴더로 묶으면
# 같은 것이 통째로 빠져나간다. 판정은 내려 맞춘 경로 조각으로 한다
CREDENTIAL_SEGMENTS = frozenset({"keys", "credentials", "secrets"})

# 자격증명 표식. 확장자가 아니라 **이름을 구분자로 쪼갠 조각**과 맞춘다 — 이유는 `_is_credential` 에 있다
# `token`·`secret` 이 들어 있는 이유: **이 PC 의 실제 자격증명이 그 이름을 쓴다**
# (`keys/sheets-mcp-token.json`). 지금은 `keys/` 폴더가 막지만, 도구가 같은 파일을 허용 폴더
# 밖에 쓰면(`tools/msg/token.json`) 이름 판정 말고는 막을 것이 없다
CREDENTIAL_NAME_TOKENS = frozenset({"env", "pem", "key", "credentials", "token", "secret"})

# 이름을 쪼개는 구분자. `.` 만으로는 `.env-prod` · `env_local` 을 놓친다
NAME_SEPARATORS = re.compile(r"[.\-_]")

# 사람이 읽는 문서와 모듈의 확장자. **«구분자» 로 쪼갠 조각에만 적용되는 탈출구다.**
#
# 이 탈출구가 없으면 구분자 분리를 쓸 수 없다 — `key-rotation-guide.md` 와
# `api_key_helper.py` 가 `key` 조각을 갖게 되어 죽는다.
#
# [중요] **`sh`·`txt` 를 넣지 않는다.** 한때 넣었다가 `aws.key.sh` · `credentials.txt` ·
# `api-key.txt` 가 통째로 빠져나갔다 [실측] 2026-09-12. `.sh` 는 `export API_KEY=...` 의 표준
# 그릇이고 `.txt` 는 토큰을 붙여넣어 두는 흔한 자리라 **자격증명 그릇이지 문서가 아니다.**
#
# [중요] **점으로 쪼갠 조각에는 적용되지 않는다.** `server.pem.md` 처럼 표식이 온전한 점
# 조각이면 확장자와 무관하게 막는다 — 탈출구는 「합성어에 표식이 섞였을 뿐」인 경우만 구제한다.
DOCUMENT_SUFFIXES = frozenset({"md", "py", "rst"})

# 표식 조각이 없는 고전 자격증명 파일명. 전부 소문자로, **앞의 점 없이** 적는다 —
# 아래 패턴이 구분자 경계로 맞추므로 `.netrc` 도 `prod.netrc` 도 같은 항목이 잡는다
CREDENTIAL_NAMES = (
    "credentials.json",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "netrc",
    "pgpass",
    "npmrc",
)

# 고전 이름을 «구분자 경계» 로 찾는다. 접두로만 맞추던 때는 `prod.netrc` · `backup.id_rsa` ·
# `old-id_rsa` 가 전부 빠져나갔다 [실측] 2026-09-12 — 자격증명은 앞에 무엇이 붙어도 자격증명이다
CREDENTIAL_NAME_PATTERN = re.compile(
    r"(?:^|[.\-_])(?:" + "|".join(re.escape(name) for name in CREDENTIAL_NAMES) + r")(?:$|[.\-_])"
)

# --- `~/.claude.json` 에서 옮길 키 -----------------------------------------
# 이 파일은 66KB 지만 대부분 캐시·통계다. MCP 등록과 프로젝트별 권한만 옮긴다

CLAUDE_JSON_ROOT_KEYS = ("mcpServers",)
CLAUDE_JSON_PROJECT_KEYS = (
    "mcpServers",
    "allowedTools",
    "enabledMcpjsonServers",
    "disabledMcpjsonServers",
)

# --- MCP 서버 정의의 자격증명 값 -------------------------------------------
# 파일 판정(`_is_credential`)은 경로만 본다. `~/.claude.json` 은 `~/.claude` «밖» 에 있어
# 그 판정을 아예 거치지 않으며, 실제로 이 자리에서 API 키가 번들에 들어간 적이 있다

# 자격증명 값을 대신하는 고정 문자열. 받는 쪽이 이 값을 알아보고 그 PC 의 기존 값으로 되돌린다.
# **양쪽 스킬이 같은 문자열을 써야 하며** 서로 import 하지 않으므로
# `tests/test_claude_config_import.py` 가 일치를 고정한다
REDACTED_SENTINEL = "__CLAUDE_CONFIG_REDACTED__"

# 값을 가릴 블록. MCP 서버 정의에서 자격증명이 실제로 지나는 자리다.
# `command`·`args` 는 실행 인자라 가리면 받는 쪽에서 서버가 뜨지 않는다
CREDENTIAL_VALUE_BLOCKS = ("headers", "env")

# 윈도우 드라이브로 시작하는 절대경로 (`C:\...` · `C:/...`)
WINDOWS_ABSOLUTE_PATH_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")

# 받는 쪽이 "왜 없지"를 되묻지 않도록 README 와 매니페스트에 남기는 목록
EXCLUSION_NOTICE = (
    "자격증명 — 이 저장소가 PUBLIC 이라 담지 않는다. `keys/**` 전체, 이름을 `.`·`-`·`_` 로 쪼갠 조각 "
    "중 하나가 `env`·`pem`·`key`·`credentials` 와 «같은» 파일(`.env` 도트파일 · `acme-prd.env.local` "
    "다중 확장자 · `.env-prod` 구분자 형태를 포함하며 대소문자를 가리지 않는다), 그리고 "
    "`credentials.json`·`id_rsa`·`.netrc` 같은 고전 이름이다. "
    "**`.md`·`.py`·`.rst` 는 탈출구라** `api-key-format.md`·`api_key_helper.py` 처럼 합성어에 "
    "표식이 섞였을 뿐인 문서·모듈은 그대로 담긴다(점 조각이 온전한 표식이면 확장자와 무관하게 막힌다). "
    "**견본이라고 봐주지 않는다** — `*.example` 도 표식이 있으면 막힌다(견본에 값이 채워진 채 "
    "배포되는 일이 흔하다). "
    "Google OAuth 토큰은 동의화면이 「테스트」 상태라 7일마다 만료돼 옮겨도 재인증이 필요하다",
    "MCP 서버의 자격증명 «값» (`headers`·`env` 의 비경로 값, 그리고 `url` 의 query 값·"
    "`user:password@`·fragment) — 센티널로 가려 담는다. 받는 쪽은 그 PC 에 이미 있던 값을 "
    "유지하고, 없으면 채울 항목으로 알려준다. "
    "**url 은 부분만 가려진다** — scheme·host·path 와 query 키는 남아 있고, "
    "**경로(path) 구간의 값은 가리지 못한다**(어느 구간이 키인지 구조로 판별할 수 없다). "
    "경로에 키를 넣는 서버를 등록했다면 사람이 번들을 확인해야 한다",
    "세션 상태와 이력 (`projects/` · `sessions/` · `history.jsonl` · `file-history/` 등) — 다른 PC 의 이력이 섞이면 되돌릴 수 없다",
    "실행 기록 — 이름을 `.` 으로 쪼갠 조각이 `jsonl`(감사로그)·`log`(런타임 로그)인 파일과 "
    "`.lock` 상태 파일. 대소문자를 가리지 않고 `toast.log.1` 처럼 로테이트된 것도 포함하되, "
    "`.md`·`.py`·`.rst` 는 구제한다(`commands/log.md` 같은 문서). "
    "그 PC 에서만 뜻이 있고, 매번 달라져 번들의 `git diff` 로 「이번에 무엇이 바뀌었나」를 "
    "가릴 수 없게 만든다. **`poetry.lock` 처럼 옮겨야 하는 고정 파일은 담는다**",
    "플랫폼 venv (`**/venv/**`) — 바이너리라 받는 쪽에서 쓸 수 없다. 필요하면 재생성한다",
    "**venv 만 든 폴더는 폴더째 사라진다** — 담을 것이 0개가 되기 때문이며 실물 사례가 `tools/xlsx/` 다. "
    "무엇을 재생성해야 하는지는 이 매니페스트의 `excluded_venvs` 가 경로와 패키지까지 적어 둔다",
    "플러그인 (`plugins/**`) — 공식 마켓플레이스 사본 6.4MB 이며 받는 쪽에서 자동으로 다시 설치된다",
    "캐시와 자동 백업 (`cache/` · `backups/` · `*.bak-*`)",
)


def _is_credential(relative_path: Path) -> bool:
    """자격증명으로 취급할 경로인지 판정한다.

    이름은 확장자가 아니라 **`.` 으로 쪼갠 토큰**으로 본다. `Path.suffix` 는 마지막 확장자
    하나만 주고, **도트파일에서는 아예 빈 문자열이 된다** — 파이썬이 앞의 점을 확장자
    구분자가 아니라 이름의 일부로 보기 때문이다. 그래서 확장자로 판정하면 `.env` 라는
    **가장 흔한 자격증명 파일명이 한 번도 안 걸리고**, `acme-prd.env.local` 처럼 뒤에 한
    조각이 더 붙어도 샌다. [실측] 2026-09-12 — `Path('.env').suffix` 는 `''`,
    `Path('.env.local').suffixes` 는 `['.local']` 이라 `.suffixes` 로 바꿔도 못 잡는다.

    **첫 토큰도 센다.** 한때 `env.py` 같은 모듈명을 살리려고 뺐으나, 그러면 `key.json`
    (GCP 서비스계정 키의 표준 파일명) · `env.json` · `key` 가 통째로 샌다. 실제 번들 37개 중
    첫 토큰이 표식인 파일은 **0개**라 지킬 것이 없었고, 가정의 파일을 살리려다 실재하는
    구멍을 연 셈이었다 `[실측] 2026-09-12`.

    **이름은 내려 맞춘다.** mac·윈도우는 대소문자를 구별하지 않는 파일시스템이라
    `.ENV` 와 `.env` 가 같은 파일인데, 그대로 비교하면 한쪽만 막힌다.

    조각은 `.` 뿐 아니라 **`-`·`_` 로도 쪼갠다.** `.` 만으로는 `.env-prod` · `env_local` ·
    `id_rsa_backup` 이 전부 빠져나간다.

    **견본 예외를 두지 않는다.** 한때 「마지막 조각이 `example`·`sample`·`template` 이면
    통과」라는 규칙이었는데 **그것이 우회로였다** — 이름 뒤에 그 조각만 붙이면 판정이 통째로
    꺼진다. 경로 목록으로 바꿔 봤으나 담을 값어치가 있는 파일이 애초에 없었다. 실물
    `acme-prd.env.example` 에는 운영 DB 의 host·port·name 이 채워져 있었다 —
    **「견본이면 비어 있다」는 전제가 틀렸다** `[실측] 2026-09-12`.

    조각 «전체 일치» 이고 **문서·코드 확장자는 탈출구**(`DOCUMENT_SUFFIXES`)라
    `api-key-format.md` · `key-rotation-guide.md` · `env.py` 는 살아남는다 —
    **정상 파일을 죽이는 쪽이 유출보다 조용한 실패라** 이 경계를 함께 지킨다.

    Args:
        relative_path: `~/.claude` 기준 상대경로

    Returns:
        bool: 자격증명이면 True
    """
    if CREDENTIAL_SEGMENTS & {part.lower() for part in relative_path.parts[:-1]}:
        return True

    lowered = relative_path.name.lower()
    if CREDENTIAL_NAME_PATTERN.search(lowered):
        return True

    # 점으로 쪼갠 조각이 표식이면 **확장자와 무관하게** 막는다. 여기에 탈출구를 두었더니
    # `.env.txt` · `aws.key.sh` · `server.pem.md` 가 빠져나갔다 [실측] 2026-09-12
    dotted = lowered.split(".")
    if CREDENTIAL_NAME_TOKENS & set(dotted):
        return True

    # 구분자까지 쪼갠 조각은 합성어를 건드리므로 문서·모듈 확장자를 구제한다
    if dotted[-1] in DOCUMENT_SUFFIXES:
        return False

    return bool(CREDENTIAL_NAME_TOKENS & {piece for piece in NAME_SEPARATORS.split(lowered) if piece})


def should_include(relative_path: Path) -> bool:
    """`~/.claude` 기준 상대경로가 번들에 담기는지 판정한다.

    Args:
        relative_path: `~/.claude` 기준 상대경로

    Returns:
        bool: 담으면 True

    Raises:
        ValueError: 절대경로가 들어온 경우
    """
    if relative_path.is_absolute():
        raise ValueError(f"상대경로를 넘겨야 합니다: {relative_path}")

    parts = relative_path.parts
    if not parts:
        return False

    if _is_credential(relative_path):
        return False
    if DENY_SEGMENTS & {part.lower() for part in parts}:
        return False

    # 문서·모듈 확장자는 구제한다 — `commands/log.md`(슬래시 커맨드)·`hooks/lock.py` 가
    # 조용히 사라지던 것을 막는다 [실측] 2026-09-12. 안 보낸 것은 받는 쪽에서 «묻지도 않고» 없어진다
    record_tokens = relative_path.name.lower().split(".")
    if RUNTIME_RECORD_TOKENS & set(record_tokens) and record_tokens[-1] not in DOCUMENT_SUFFIXES:
        return False
    if relative_path.name.lower() in DENY_NAMES:
        return False
    if BACKUP_NAME_PATTERN.search(relative_path.name):
        return False

    if len(parts) == 1:
        return parts[0] in ALLOW_TOP_LEVEL_FILES

    return parts[0] in ALLOW_TOP_LEVEL_DIRS


def collect_relative_paths(claude_home: Path) -> list[Path]:
    """번들에 담을 파일의 상대경로를 정렬해 돌려준다.

    정렬하는 이유는 매니페스트가 실행마다 같아야 git diff 가 「무엇이 바뀌었나」를
    말해주기 때문이다. 파일시스템 순회 순서는 보장되지 않는다.

    Args:
        claude_home: `~/.claude` 에 해당하는 경로

    Returns:
        list[Path]: 담을 파일의 상대경로 (정렬됨)

    Raises:
        ValueError: 경로가 디렉터리가 아닌 경우
    """
    if not claude_home.is_dir():
        raise ValueError(f"설정 폴더가 없습니다: {claude_home}")

    collected = [
        path.relative_to(claude_home) for path in claude_home.rglob("*") if path.is_file() and not path.is_symlink()
    ]

    return sorted(relative for relative in collected if should_include(relative))


def _read_venv_packages(venv_dir: Path) -> list[str]:
    """venv 에 설치된 배포판을 `이름==버전` 으로 읽는다.

    `pip freeze` 를 부르지 않는다 — 인터프리터가 깨져 있으면 내보내기 전체가 실패하고,
    외부 프로세스에 의존하게 된다. `dist-info` 폴더명이 같은 정보를 파일시스템만으로 준다.

    이름은 PEP 503 으로 정규화한다(`python_pptx` → `python-pptx`). **받는 쪽이 이 값을
    그대로 설치 명령에 넣기 때문**이고, 그래야 만든 도구(`pip`·`uv`)가 달라도 목록이 같아진다.

    Args:
        venv_dir: venv 루트

    Returns:
        list[str]: `이름==버전` 목록 (정렬됨). 읽을 자리가 없으면 빈 목록
    """
    dist_infos: set[Path] = set()
    for site_packages in SITE_PACKAGES_GLOBS:
        dist_infos.update(path for path in venv_dir.glob(f"{site_packages}/*.dist-info") if path.is_dir())

    packages: list[str] = []
    for dist_info in dist_infos:
        name, _, version = dist_info.name.removesuffix(".dist-info").rpartition("-")
        if not name or not version:
            continue

        normalized = name.replace("_", "-").lower()
        if normalized in VENV_BOOTSTRAP_PACKAGES:
            continue

        packages.append(f"{normalized}=={version}")

    return sorted(packages)


def collect_excluded_venvs(claude_home: Path) -> list[dict[str, Any]]:
    """번들에서 빠진 venv 의 경로와 설치 패키지를 모은다.

    venv 자체는 플랫폼 바이너리라 담지 않는다. 그런데 **빠졌다는 사실이 받는 쪽에 남지
    않아서** 도구가 죽은 채 넘어간 적이 있다(2026-09-09 `tools/xlsx`·`tools/pptx`).
    권한 규칙과 스크립트 import 로 알아내는 방법은 둘 다 «간접 증거» 라, venv 뿐인 폴더에
    권한 규칙까지 없으면 어느 쪽에도 걸리지 않는다.

    **보내는 쪽은 venv 를 직접 보고 있으므로 추론할 필요가 없다.** 여기서 적어 두면
    받는 쪽은 조사 없이 재생성한다.

    Args:
        claude_home: `~/.claude` 에 해당하는 경로

    Returns:
        list[dict[str, Any]]: `{"path": 상대경로, "packages": [이름==버전]}` (경로 정렬).
            읽지 못한 venv 도 **경로는 남긴다** — 「패키지가 없었다」와 「읽지 못했다」는 다르다

    Raises:
        ValueError: 경로가 디렉터리가 아닌 경우
    """
    if not claude_home.is_dir():
        raise ValueError(f"설정 폴더가 없습니다: {claude_home}")

    inventory: list[dict[str, Any]] = []
    for venv_dir in claude_home.rglob("venv"):
        if not venv_dir.is_dir():
            continue

        relative = venv_dir.relative_to(claude_home)
        # venv 안의 `venv` 이름 폴더는 설치된 배포판의 일부다. 하나가 둘로 보이면
        # 받는 쪽이 존재하지 않는 도구를 재생성하려 든다
        if "venv" in relative.parent.parts:
            continue

        inventory.append({"path": relative.as_posix(), "packages": _read_venv_packages(venv_dir)})

    return sorted(inventory, key=lambda entry: str(entry["path"]))


def find_forbidden_entries(bundle_home: Path) -> list[Path]:
    """번들에 담기면 안 되는 항목을 찾는다.

    수집과 «같은 판정»을 쓴다. 판정을 두 벌로 만들면 한쪽이 담아도 된다고 한 파일을
    다른 쪽이 거부하는 상태가 된다.

    Args:
        bundle_home: 번들의 `home/` 경로

    Returns:
        list[Path]: 담기면 안 되는 항목의 상대경로 (정렬됨)

    Raises:
        ValueError: 경로가 디렉터리가 아닌 경우
    """
    if not bundle_home.is_dir():
        raise ValueError(f"번들 폴더가 없습니다: {bundle_home}")

    forbidden = [
        path.relative_to(bundle_home) for path in bundle_home.rglob("*") if path.is_file() and not path.is_symlink()
    ]

    return sorted(relative for relative in forbidden if not should_include(relative))


def extract_claude_json(source: Path) -> dict[str, Any]:
    """`~/.claude.json` 에서 옮길 값만 추린다.

    이 파일에는 MCP 등록과 프로젝트별 권한이 들어 있어 빠뜨리면 받는 쪽에서 MCP 가
    통째로 사라진다. 나머지(캐시·통계·온보딩 상태)는 그 PC 의 것이라 옮기지 않는다.

    Args:
        source: `~/.claude.json` 경로

    Returns:
        dict[str, Any]: 추린 설정. 프로젝트 경로는 원본 그대로 두며, 변환은 받는 쪽이 한다

    Raises:
        ValueError: 파일이 없는 경우
    """
    if not source.is_file():
        raise ValueError(f"설정 파일이 없습니다: {source}")

    raw: dict[str, Any] = json.loads(source.read_text(encoding="utf-8"))

    extracted: dict[str, Any] = {key: raw[key] for key in CLAUDE_JSON_ROOT_KEYS if key in raw}

    projects: dict[str, Any] = {}
    for project_path, project_value in raw.get("projects", {}).items():
        kept = {key: project_value[key] for key in CLAUDE_JSON_PROJECT_KEYS if project_value.get(key)}
        if kept:
            projects[project_path] = kept

    if projects:
        extracted["projects"] = projects

    return extracted


def _is_absolute_path(value: str) -> bool:
    """값이 절대경로 모양인지 판정한다.

    경로는 자격증명이 아니라 **자격증명이 놓인 곳**이다. 받는 쪽이 그 문자열에서 출처 PC 의
    홈을 찾아 자기 경로로 치환하므로, 가리면 그 기능이 죽는다.

    판정을 절대경로로 **좁게** 잡는다. 넓게 잡으면 경로처럼 생긴 자격증명이 빠져나가고,
    좁게 잡아 생기는 손해는 「가리지 않아도 될 값을 가리는 것」뿐이다.

    Args:
        value: 검사할 문자열

    Returns:
        bool: 절대경로 모양이면 True
    """
    if value.startswith(("/", "~/")):
        return True

    return bool(WINDOWS_ABSOLUTE_PATH_PATTERN.match(value))


def _redact_url(url: str) -> str | None:
    """url 에 실린 자격증명만 센티널로 바꾼다. 가릴 것이 없으면 None 을 돌려준다.

    **접속에 필요한 것은 남긴다** — scheme·host·path 와 query 의 «키» 는 그대로 두고
    query 의 «값» 과 `user:password@` 구간만 바꾼다. url 전체를 가리면 받는 쪽에서 서버가
    뜨지 않는다(`command`·`args` 를 가리지 않는 것과 같은 이유다).

    값을 이름으로 고르지 않는 것은 이 모듈의 규율이다 — 구글시트의 `TOKEN_PATH` 가 걸려
    **살려야 할 경로가 죽은** 전례가 있고, 새 서버가 다른 이름을 쓰면 조용히 샌다.

    [주의] **경로(path) 구간은 가리지 않는다.** 어느 구간이 키인지 «구조로 판별할 수 없고»
    통째로 가리면 서버가 뜨지 않는다. query·userinfo·fragment 는 규격이 「값을 싣는 자리」로
    정해 둔 곳이라 기계로 가릴 수 있지만 경로는 그렇지 않다. 경로에 키를 넣는 API 가 실제로
    있으므로(ECOS 가 그렇다 — `src/verify_lab/CLAUDE.md`) **그런 서버를 등록할 때는 사람이
    번들을 확인해야 한다.** 두 번째 겹인 번들 전체 패턴 스캔이 알려진 키 형식만 잡는다.

    Args:
        url: MCP 서버 정의의 `url` 값

    Returns:
        str | None: 가린 url. 가릴 것이 없으면 None (모양을 바꾸지 않기 위해)
    """
    parts = urlsplit(url)
    netloc = parts.netloc
    pairs = parse_qsl(parts.query, keep_blank_values=True) if parts.query else []

    # 경로 값은 남긴다 — `_redact_server` 와 같은 규율이다. 자격증명이 아니라 자격증명이
    # 놓인 곳이고, 가리면 받는 쪽의 경로 치환이 되돌릴 것을 잃는다
    redact_pairs = [(key, value) for key, value in pairs if not _is_absolute_path(value)]

    if "@" not in netloc and not redact_pairs and not parts.fragment:
        return None

    if "@" in netloc:
        netloc = f"{REDACTED_SENTINEL}@{netloc.rsplit('@', 1)[1]}"

    query = parts.query
    if redact_pairs:
        query = urlencode([(key, REDACTED_SENTINEL if not _is_absolute_path(value) else value) for key, value in pairs])

    # 조각(fragment)은 통째로 가린다. OAuth 가 `#access_token=` 으로 토큰을 싣는 자리이고,
    # **MCP 서버 접속에는 쓰이지 않으므로** 지워도 받는 쪽이 잃을 것이 없다
    fragment = REDACTED_SENTINEL if parts.fragment else ""

    return urlunsplit((parts.scheme, netloc, parts.path, query, fragment))


def _redact_server(definition: dict[str, Any]) -> list[str]:
    """서버 정의 하나의 자격증명 값을 제자리에서 가린다.

    Args:
        definition: 서버 정의. **사본을 넘겨야 한다** — 이 함수는 제자리에서 고친다

    Returns:
        list[str]: 가린 필드 경로 (`headers.API_KEY` 형태). 서버 이름은 호출자가 붙인다
    """
    redacted_fields: list[str] = []

    for block_name in CREDENTIAL_VALUE_BLOCKS:
        block = definition.get(block_name)
        if not isinstance(block, dict):
            continue

        for key, value in block.items():  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(value, str) or _is_absolute_path(value):
                continue

            block[key] = REDACTED_SENTINEL
            redacted_fields.append(f"{block_name}.{key}")

    url = definition.get("url")
    if isinstance(url, str):
        redacted_url = _redact_url(url)
        if redacted_url is not None:
            definition["url"] = redacted_url
            redacted_fields.append("url")

    return redacted_fields


def redact_credentials(claude_json: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """MCP 서버 정의의 자격증명 값을 센티널로 바꾼다.

    **허용목록 방식이다** — `headers`·`env` 의 문자열 값 중 절대경로가 «아닌» 것을 전부 가린다.
    이름 패턴(`KEY`·`TOKEN` 이 들어간 키)으로 고르지 않는 이유는 실측에 있다:
    구글시트의 `TOKEN_PATH` 가 그 패턴에 걸려 **살려야 할 경로가 죽고**, 새 서버가 다른 이름을
    쓰면 조용히 샌다. 파일 판정을 허용목록으로 둔 것과 같은 이유다.

    최상위 `mcpServers` 와 `projects[*].mcpServers` **양쪽**을 본다. 둘은 구조가 같아서
    한쪽만 막으면 저장소별 서버를 등록하는 순간 새는 자리가 남는다.

    Args:
        claude_json: `extract_claude_json()` 이 추린 설정

    Returns:
        tuple[dict[str, Any], list[str]]: (가린 사본, 가린 키 경로 목록). 원본은 바뀌지 않는다
    """
    redacted = copy.deepcopy(claude_json)
    replaced: list[str] = []

    for name, definition in redacted.get("mcpServers", {}).items():
        replaced.extend(f"mcpServers.{name}.{field}" for field in _redact_server(definition))

    for project_path, project_value in redacted.get("projects", {}).items():
        for name, definition in project_value.get("mcpServers", {}).items():
            replaced.extend(
                f"projects[{project_path}].mcpServers.{name}.{field}" for field in _redact_server(definition)
            )

    return redacted, replaced


def file_sha256(path: Path) -> str:
    """파일의 SHA-256 을 구한다.

    매니페스트를 만들 때와 받는 쪽이 대조할 때 «같은» 계산을 써야 하므로 공개한다.

    Args:
        path: 대상 파일

    Returns:
        str: 16진수 해시
    """
    digest = hashlib.sha256()
    digest.update(path.read_bytes())

    return digest.hexdigest()


def _source_identity() -> dict[str, str]:
    """번들을 만든 PC 를 식별하는 값을 모은다.

    `home` 을 함께 남기는 이유는 **받는 쪽이 경로를 치환할 기준점**이기 때문이다.
    설정 곳곳에 출처 PC 의 홈 절대경로가 박혀 있고, 그 문자열을 알아야 바꿔 끼울 수 있다.
    설정값에서 거꾸로 추론하면 홈이 아닌 경로까지 잘못 치환한다.

    Returns:
        dict[str, str]: 호스트명·플랫폼·홈 경로·machineID
    """
    machine_id = ""
    if CLAUDE_JSON_PATH.is_file():
        raw: dict[str, Any] = json.loads(CLAUDE_JSON_PATH.read_text(encoding="utf-8"))
        machine_id = str(raw.get("machineID", ""))

    return {
        "hostname": socket.gethostname(),
        "platform": sys.platform,
        "os_release": platform.release(),
        "home": Path.home().as_posix(),
        "machine_id": machine_id,
    }


def build_manifest(claude_home: Path, relative_paths: list[Path]) -> dict[str, Any]:
    """매니페스트를 만든다.

    받는 쪽이 「사본이 원본과 같은가」를 대조할 수 있어야 하고, 결정 누적이
    「이 항목이 지난번과 같은 내용인가」를 해시로 판별한다.

    Args:
        claude_home: `~/.claude` 에 해당하는 경로
        relative_paths: 담을 파일의 상대경로

    Returns:
        dict[str, Any]: 매니페스트 내용
    """
    entries = [
        {
            "path": relative.as_posix(),
            "sha256": file_sha256(claude_home / relative),
            "size": (claude_home / relative).stat().st_size,
        }
        for relative in relative_paths
    ]

    return {
        "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "source": _source_identity(),
        "entry_count": len(entries),
        "total_size": sum(int(entry["size"]) for entry in entries),
        "excluded_notice": list(EXCLUSION_NOTICE),
        "excluded_venvs": collect_excluded_venvs(claude_home),
        "entries": entries,
    }


def _render_venv_table(excluded_venvs: list[dict[str, Any]]) -> str:
    """제외한 venv 를 받는 쪽이 읽을 표로 만든다.

    **0건일 때도 줄을 남긴다** — 「검사했고 없었다」와 「검사하지 않았다」는 다르다.

    Args:
        excluded_venvs: `collect_excluded_venvs()` 의 결과

    Returns:
        str: 마크다운 표. venv 가 없으면 그 사실을 적은 한 줄
    """
    if not excluded_venvs:
        return "이 PC 의 `~/.claude` 에는 venv 가 없었습니다."

    rows: list[str] = []
    for entry in excluded_venvs:
        packages = " · ".join(f"`{package}`" for package in entry["packages"])
        rows.append(f"| `{entry['path']}` | {packages or '**읽지 못했습니다**'} |")

    return "\n".join(["| venv 경로 | 설치 패키지 |", "| --- | --- |", *rows])


def render_readme(manifest: dict[str, Any]) -> str:
    """받는 쪽이 읽을 작업문서를 만든다.

    Args:
        manifest: 매니페스트 내용

    Returns:
        str: README 본문
    """
    source: dict[str, Any] = manifest["source"]
    excluded = "\n".join(f"- {line}" for line in manifest["excluded_notice"])
    venv_table = _render_venv_table(manifest["excluded_venvs"])

    return f"""# 전역 Claude 설정 번들

이 폴더는 **다른 PC 의 `~/.claude` 사본**입니다. 사람이 손으로 고치는 곳이 아니라
`claude-config-export` 스킬이 통째로 다시 만드는 산출물입니다.

- **출처**: `{source["hostname"]}` ({source["platform"]}, {source["os_release"]})
- **만든 시각**: {manifest["generated_at"]} KST
- **담긴 항목**: {manifest["entry_count"]}개 / {manifest["total_size"]:,} bytes

## 받는 쪽에서 할 일

이 저장소를 pull 한 뒤 **`claude-config-import` 스킬을 실행**하면 됩니다.
경로를 입력할 필요가 없습니다 — 스킬이 이 폴더를 스스로 찾습니다.

스킬은 항목을 셋으로 나눠 처리합니다.

| 분류 | 처리 |
| --- | --- |
| 그대로 적용 | 스킬·커맨드·규칙·훅처럼 OS 와 경로에 무관한 것 |
| 변환 후 적용 | 절대경로가 박힌 것. **경로를 바꿔 적용하고 무엇을 바꿨는지 보고합니다** |
| 승인 후 제외 | 그 PC 에 대상이 없어 적용할 수 없는 것. **목록을 보여주고 승인을 받은 뒤에만** 뺍니다 |

한 번 내린 제외 결정은 `decisions/` 에 PC별로 쌓여 다음 실행 때 다시 묻지 않습니다.
다만 **원본 파일 내용이 바뀌면 해시가 달라져 다시 묻습니다.**

## 애초에 담기지 않은 것

{excluded}

### 제외한 venv — 받는 쪽에서 다시 만듭니다

**이 표가 재생성의 근거입니다.** 권한 규칙이나 스크립트의 import 로 짐작하지 않아도 됩니다 —
보내는 쪽이 실제로 본 것을 그대로 적었습니다. 만드는 절차는 `claude-config-import` 스킬 6단계에 있습니다.

{venv_table}

## 폴더 구성

| 경로 | 내용 |
| --- | --- |
| `home/` | `~/.claude` 의 사본 (원본 트리 구조 유지) |
| `claude_json.json` | `~/.claude.json` 에서 MCP 등록과 프로젝트별 권한만 추린 것 |
| `MANIFEST.json` | 출처 PC · 시각 · 항목별 SHA-256 |
| `decisions/` | 받는 PC 별 적용·제외 결정 |
"""


def _report(relative_paths: list[Path], manifest: dict[str, Any], redacted_keys: list[str], *, detailed: bool) -> None:
    """무엇을 담는지 사람이 읽을 수 있게 출력한다.

    `detailed` 는 dry-run 용이다. 항목이 수십 개 규모라 전부 보여줘야 사용자가
    「담기면 안 되는 것이 섞였는가」를 그 자리에서 대조할 수 있다.

    **가린 값은 `detailed` 와 무관하게 전부 나열한다.** 치환이 허용목록 방식이라
    자격증명이 아닌 설정값까지 가릴 수 있고, 그 오탐은 목록을 봐야 알아챈다.
    0건일 때도 줄을 남긴다 — 「검사했고 없었다」와 「검사하지 않았다」는 다르다.

    Args:
        relative_paths: 담을 파일의 상대경로
        manifest: 매니페스트 내용
        redacted_keys: 센티널로 가린 키 경로
        detailed: 항목을 하나씩 나열할지 여부
    """
    print(f"담을 항목: {len(relative_paths)}개 / {manifest['total_size']:,} bytes\n")

    if detailed:
        sizes = {str(entry["path"]): int(entry["size"]) for entry in manifest["entries"]}
        for relative in relative_paths:
            print(f"  {relative.as_posix():<52} {sizes[relative.as_posix()]:>9,} bytes")
    else:
        grouped: dict[str, int] = {}
        for relative in relative_paths:
            top = relative.parts[0] if len(relative.parts) > 1 else "(최상위 파일)"
            grouped[top] = grouped.get(top, 0) + 1

        for top, count in sorted(grouped.items()):
            print(f"  {top:<12} {count:>4}개")

    print(f"\n가린 자격증명 값: {len(redacted_keys)}개")
    for key in redacted_keys:
        print(f"  - {key}")

    excluded_venvs: list[dict[str, Any]] = manifest["excluded_venvs"]
    print(f"\n담지 않은 venv: {len(excluded_venvs)}개 — 받는 쪽은 이 목록으로 재생성한다")
    for entry in excluded_venvs:
        packages = ", ".join(entry["packages"])
        print(f"  - {entry['path']}: {packages or '(패키지를 읽지 못했습니다)'}")

    print("\n담지 않는 것:")
    for line in EXCLUSION_NOTICE:
        print(f"  - {line}")


def export_bundle(claude_home: Path, redacted_claude_json: dict[str, Any]) -> dict[str, Any]:
    """번들을 만든다.

    `home/` 은 통째로 지우고 다시 만든다. 원본에서 지운 파일이 번들에 남으면
    받는 쪽이 이미 없어진 설정을 적용하게 된다.

    Args:
        claude_home: `~/.claude` 에 해당하는 경로
        redacted_claude_json: 자격증명을 이미 가린 `~/.claude.json` 추출본.
            **가리는 일을 호출자가 하는 이유**는 `--dry-run` 도 같은 결과를 보여야 하기 때문이다 —
            여기서 가리면 파일을 쓰지 않는 경로에서는 무엇을 가렸는지 알 수 없다

    Returns:
        dict[str, Any]: 매니페스트 내용

    Raises:
        RuntimeError: 담기면 안 되는 항목이 번들에 들어간 경우
    """
    relative_paths = collect_relative_paths(claude_home)
    manifest = build_manifest(claude_home, relative_paths)

    if BUNDLE_HOME_DIR.exists():
        shutil.rmtree(BUNDLE_HOME_DIR)

    for relative in relative_paths:
        target = BUNDLE_HOME_DIR / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(claude_home / relative, target)

    forbidden = find_forbidden_entries(BUNDLE_HOME_DIR)
    if forbidden:
        # **지운 뒤에 던진다.** 점검이 걸린 파일은 이미 복사돼 있어, 그대로 두면
        # 「내보내기가 중단됐다」로 보이는 상태에서 **`git add` 를 기다리는 자격증명이
        # 저장소 안에 놓인다.** 무엇이 걸렸는지는 메시지가 경로로 말한다
        shutil.rmtree(BUNDLE_HOME_DIR, ignore_errors=True)
        raise RuntimeError(f"내부 불변조건 위반: 담기면 안 되는 항목이 번들에 있습니다 — {forbidden}")

    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    (DECISIONS_DIR / ".gitkeep").touch()

    BUNDLE_CLAUDE_JSON_PATH.write_text(
        json.dumps(redacted_claude_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    README_PATH.write_text(render_readme(manifest), encoding="utf-8")

    return manifest


def parse_args() -> argparse.Namespace:
    """명령행 인자를 해석한다.

    Returns:
        argparse.Namespace: 해석된 인자
    """
    parser = argparse.ArgumentParser(description="전역 Claude 설정을 claude-config/ 로 내보낸다")
    parser.add_argument("--dry-run", action="store_true", help="복사하지 않고 담을 목록만 출력한다")

    return parser.parse_args()


def main() -> int:
    """스크립트 진입점.

    Returns:
        int: 종료 코드
    """
    args = parse_args()

    if not CLAUDE_HOME.is_dir():
        print(f"[오류] 전역 설정 폴더를 찾을 수 없습니다: {CLAUDE_HOME}", file=sys.stderr)
        return 1

    relative_paths = collect_relative_paths(CLAUDE_HOME)
    if not relative_paths:
        print("[오류] 담을 항목이 하나도 없습니다. 판정 규칙을 확인하세요.", file=sys.stderr)
        return 1

    redacted_claude_json, redacted_keys = redact_credentials(extract_claude_json(CLAUDE_JSON_PATH))

    if args.dry_run:
        _report(relative_paths, build_manifest(CLAUDE_HOME, relative_paths), redacted_keys, detailed=True)
        print("\n(--dry-run 이므로 파일을 쓰지 않았습니다)")
        return 0

    manifest = export_bundle(CLAUDE_HOME, redacted_claude_json)
    _report(relative_paths, manifest, redacted_keys, detailed=False)
    print(f"\n번들을 만들었습니다: {BUNDLE_DIR}")
    print("git 에 올리는 것은 사용자가 직접 합니다.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
