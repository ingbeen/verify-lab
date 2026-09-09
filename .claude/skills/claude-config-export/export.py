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

# 감사로그·세션 이력이 쓰는 확장자
DENY_SUFFIXES = frozenset({".jsonl"})

# 상태 파일
DENY_NAMES = frozenset({".lock"})

# 손으로 만든 백업본 (`CLAUDE.md.bak-20260909` 등)
BACKUP_NAME_PATTERN = re.compile(r"\.bak-")

# 자격증명 — 유출이 되돌려지지 않으므로 허용목록보다 먼저 판정한다
CREDENTIAL_SEGMENTS = frozenset({"keys"})
CREDENTIAL_SUFFIXES = frozenset({".env", ".pem", ".key"})
CREDENTIAL_NAMES = frozenset({".credentials.json"})

# --- `~/.claude.json` 에서 옮길 키 -----------------------------------------
# 이 파일은 66KB 지만 대부분 캐시·통계다. MCP 등록과 프로젝트별 권한만 옮긴다

CLAUDE_JSON_ROOT_KEYS = ("mcpServers",)
CLAUDE_JSON_PROJECT_KEYS = (
    "mcpServers",
    "allowedTools",
    "enabledMcpjsonServers",
    "disabledMcpjsonServers",
)

# 받는 쪽이 "왜 없지"를 되묻지 않도록 README 와 매니페스트에 남기는 목록
EXCLUSION_NOTICE = (
    "자격증명 (`keys/**` · `*.env` · `*.pem` · `*.key`) — 이 저장소가 PUBLIC 이라 담지 않는다. "
    "Google OAuth 토큰은 동의화면이 「테스트」 상태라 7일마다 만료돼 옮겨도 재인증이 필요하다",
    "세션 상태와 이력 (`projects/` · `sessions/` · `history.jsonl` · `file-history/` 등) — 다른 PC 의 이력이 섞이면 되돌릴 수 없다",
    "감사 로그 (`db/*.jsonl`) — 그 PC 에서만 뜻이 있다",
    "플랫폼 venv (`**/venv/**`) — 바이너리라 받는 쪽에서 쓸 수 없다. 필요하면 재생성한다",
    "플러그인 (`plugins/**`) — 공식 마켓플레이스 사본 6.4MB 이며 받는 쪽에서 자동으로 다시 설치된다",
    "캐시와 자동 백업 (`cache/` · `backups/` · `*.bak-*`)",
)


def _is_credential(relative_path: Path) -> bool:
    """자격증명으로 취급할 경로인지 판정한다.

    Args:
        relative_path: `~/.claude` 기준 상대경로

    Returns:
        bool: 자격증명이면 True
    """
    if CREDENTIAL_SEGMENTS & set(relative_path.parts):
        return True
    if relative_path.suffix in CREDENTIAL_SUFFIXES:
        return True

    return relative_path.name in CREDENTIAL_NAMES


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
    if DENY_SEGMENTS & set(parts):
        return False
    if relative_path.suffix in DENY_SUFFIXES:
        return False
    if relative_path.name in DENY_NAMES:
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
        "entries": entries,
    }


def render_readme(manifest: dict[str, Any]) -> str:
    """받는 쪽이 읽을 작업문서를 만든다.

    Args:
        manifest: 매니페스트 내용

    Returns:
        str: README 본문
    """
    source: dict[str, Any] = manifest["source"]
    excluded = "\n".join(f"- {line}" for line in manifest["excluded_notice"])

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

## 폴더 구성

| 경로 | 내용 |
| --- | --- |
| `home/` | `~/.claude` 의 사본 (원본 트리 구조 유지) |
| `claude_json.json` | `~/.claude.json` 에서 MCP 등록과 프로젝트별 권한만 추린 것 |
| `MANIFEST.json` | 출처 PC · 시각 · 항목별 SHA-256 |
| `decisions/` | 받는 PC 별 적용·제외 결정 |
"""


def _report(relative_paths: list[Path], manifest: dict[str, Any], *, detailed: bool) -> None:
    """무엇을 담는지 사람이 읽을 수 있게 출력한다.

    `detailed` 는 dry-run 용이다. 항목이 수십 개 규모라 전부 보여줘야 사용자가
    「담기면 안 되는 것이 섞였는가」를 그 자리에서 대조할 수 있다.

    Args:
        relative_paths: 담을 파일의 상대경로
        manifest: 매니페스트 내용
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

    print("\n담지 않는 것:")
    for line in EXCLUSION_NOTICE:
        print(f"  - {line}")


def export_bundle(claude_home: Path) -> dict[str, Any]:
    """번들을 만든다.

    `home/` 은 통째로 지우고 다시 만든다. 원본에서 지운 파일이 번들에 남으면
    받는 쪽이 이미 없어진 설정을 적용하게 된다.

    Args:
        claude_home: `~/.claude` 에 해당하는 경로

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
        raise RuntimeError(f"내부 불변조건 위반: 담기면 안 되는 항목이 번들에 있습니다 — {forbidden}")

    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    (DECISIONS_DIR / ".gitkeep").touch()

    BUNDLE_CLAUDE_JSON_PATH.write_text(
        json.dumps(extract_claude_json(CLAUDE_JSON_PATH), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
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

    if args.dry_run:
        _report(relative_paths, build_manifest(CLAUDE_HOME, relative_paths), detailed=True)
        print("\n(--dry-run 이므로 파일을 쓰지 않았습니다)")
        return 0

    manifest = export_bundle(CLAUDE_HOME)
    _report(relative_paths, manifest, detailed=False)
    print(f"\n번들을 만들었습니다: {BUNDLE_DIR}")
    print("git 에 올리는 것은 사용자가 직접 합니다.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
