"""번들을 이 PC 에 어떻게 적용할지 판정하고, 승인 후 적용한다.

**OS 가 다르다고 항목을 버리지 않는다.** 설정 대부분은 경로만 바꾸면 살아나므로 판정은
셋으로 나뉜다 — 그대로 적용 / 변환 후 적용 / 승인 후 제외. 마지막 것만 사람에게 묻는다.

판정 단위는 «파일» 이 아니라 «항목» 이다. `settings.json` 은 파일 하나지만 그 안에 권한
142건과 훅 6개가 들어 있어, 파일 통째로 버리면 `terminal-notifier` 하나 때문에 나머지
전부가 사라진다.

한 번 내린 결정은 `decisions/<pc_id>.json` 에 쌓여 다음 실행 때 다시 묻지 않는다.
다만 **원본 항목의 내용이 바뀌면 해시가 달라져 다시 묻는다** — 옛 결정을 바뀐 내용에
적용하면 조용히 어긋난다.
"""

import argparse
import copy
import hashlib
import json
import re
import shutil
import socket
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# 저장소 루트. 이 파일은 <루트>/.claude/skills/claude-config-import/plan_apply.py 에 있다.
# 받는 쪽이 경로를 입력하지 않아도 되도록 스스로 찾는다
PROJECT_ROOT = Path(__file__).resolve().parents[3]

BUNDLE_DIR = PROJECT_ROOT / "claude-config"
BUNDLE_HOME_DIR = BUNDLE_DIR / "home"
BUNDLE_CLAUDE_JSON_PATH = BUNDLE_DIR / "claude_json.json"
MANIFEST_PATH = BUNDLE_DIR / "MANIFEST.json"
DECISIONS_DIR = BUNDLE_DIR / "decisions"

TARGET_CLAUDE_HOME = Path.home() / ".claude"
TARGET_CLAUDE_JSON = Path.home() / ".claude.json"

# 판정 결과
APPLY = "apply"
TRANSFORM = "transform"
EXCLUDE = "exclude"

DECISION_LABELS = {
    APPLY: "그대로 적용",
    TRANSFORM: "변환 후 적용",
    EXCLUDE: "제외 (승인 필요)",
}

# 「넣을까 뺄까」만 사용자 결정이다. `APPLY` 와 `TRANSFORM` 은 둘 다 「넣는다」이며,
# 그중 어느 «형태» 인지는 경로에서 파생된다 — 결정 파일이 그 형태를 되살리면 안 된다
INCLUDE_DECISIONS = frozenset({APPLY, TRANSFORM})

# 경로가 들어갈 수 있어 치환 대상이 되는 텍스트 파일
TEXT_SUFFIXES = frozenset({".md", ".py", ".json", ".toml", ".txt", ".sh"})

# 내보내는 쪽이 자격증명 값을 가릴 때 쓰는 고정 문자열.
# **두 스킬은 서로 import 하지 않으므로 이 값이 갈라질 수 있다** — 갈라지면 가려진 값을
# 알아보지 못하고 센티널을 그대로 등록한다. `tests/test_claude_config_import.py` 가 일치를 고정한다
REDACTED_SENTINEL = "__CLAUDE_CONFIG_REDACTED__"

# 가려진 값이 놓이는 블록. 내보내는 쪽과 같아야 한다
CREDENTIAL_VALUE_BLOCKS = ("headers", "env")

# 훅 명령에 나타나면 이식성을 의심할 도구들. **판단 재료이지 판정이 아니다.**
#
# 셸 명령을 파싱해 실행 파일을 뽑는 방식은 버렸다 — 명령치환·변수·조건식이 섞이면
# `]` · `2>/dev/null)` · `/.claude/hooks/plan_gate.py` 같은 조각을 실행 파일로 오인하고,
# 고칠 때마다 새로운 실패 형태가 나왔다. 잘못된 자동 판정은 멀쩡한 훅을 버리거나
# 깨진 훅을 넣으며, 둘 다 조용히 나쁘다. 그래서 훅은 사람이 판단한다.
#
# 이름을 부분 문자열로 찾으므로 파싱이 필요 없고, 없는 도구를 사용자에게 알려줄 뿐이다
PORTABILITY_HINT_TOOLS = ("terminal-notifier", "jq", "osascript", "pbpaste", "python3")


@dataclass
class Environment:
    """적용 대상 PC 의 실측 정보."""

    platform: str
    hostname: str
    home: Path
    source_home: str
    source_hostname: str
    extra_path_map: dict[str, str] = field(default_factory=dict)

    @property
    def path_map(self) -> dict[str, str]:
        """치환할 경로 쌍. 긴 경로가 먼저 온다.

        홈 경로 하나만으로는 모자란 경우가 있다 — 받는 PC 의 작업 폴더가 홈 밖이거나
        이름이 다르면 `Workspace` 같은 경로가 어긋난다. 그때 결정 파일의 `path_map` 에
        쌍을 추가하면 여기에 합쳐진다.

        **긴 것부터 치환해야 한다.** 짧은 홈 경로를 먼저 바꾸면 그 안에 든 긴 경로가
        이미 바뀌어 버려 뒤 규칙이 걸리지 않는다.

        Returns:
            dict[str, str]: 출처 경로 -> 이 PC 경로
        """
        merged = {self.source_home: self.home.as_posix()} if self.source_home else {}
        merged.update(self.extra_path_map)

        return dict(sorted(merged.items(), key=lambda pair: len(pair[0]), reverse=True))

    @property
    def pc_id(self) -> str:
        """결정 파일을 가르는 식별자.

        PC 마다 제외해야 할 것이 다르므로 결정도 PC 별로 쌓인다.

        Returns:
            str: 파일명으로 쓸 수 있는 식별자
        """
        safe_host = re.sub(r"[^A-Za-z0-9_.-]", "-", self.hostname)

        return f"{safe_host}-{self.platform}"


@dataclass
class Verdict:
    """항목 하나에 대한 판정."""

    key: str
    decision: str
    reason: str
    source_hash: str
    detail: str = ""
    needs_confirmation: bool = False


@dataclass
class Plan:
    """이 PC 에 대한 적용 계획."""

    environment: Environment
    verdicts: list[Verdict] = field(default_factory=list)

    def by_decision(self, decision: str) -> list[Verdict]:
        """분류별 항목을 돌려준다.

        Args:
            decision: `APPLY` · `TRANSFORM` · `EXCLUDE` 중 하나

        Returns:
            list[Verdict]: 해당 분류의 판정
        """
        return [verdict for verdict in self.verdicts if verdict.decision == decision]


def _hash_value(value: object) -> str:
    """항목 값의 SHA-256 을 구한다.

    「지난번과 같은 내용인가」를 판별하는 기준이다. dict 는 키 순서에 흔들리지 않도록
    정렬해 직렬화한다.

    Args:
        value: 해시할 값

    Returns:
        str: 16진수 해시
    """
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)

    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def detect_environment() -> Environment:
    """적용 대상 PC 와 번들 출처를 실측한다.

    Returns:
        Environment: 실측 결과

    Raises:
        ValueError: 번들이나 매니페스트가 없는 경우
    """
    if not MANIFEST_PATH.is_file():
        raise ValueError(f"매니페스트가 없습니다: {MANIFEST_PATH}. 내보내기를 먼저 실행하세요")

    manifest: dict[str, Any] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    source: dict[str, Any] = manifest["source"]

    environment = Environment(
        platform=sys.platform,
        hostname=socket.gethostname(),
        home=Path.home(),
        source_home=str(source.get("home", "")),
        source_hostname=str(source.get("hostname", "")),
    )
    environment.extra_path_map = dict(load_decisions(environment).get("path_map", {}))

    return environment


def transform_text_counted(text: str, environment: Environment) -> tuple[str, int]:
    """출처 PC 의 경로를 이 PC 의 경로로 바꾸고, 바꾼 자리 수를 함께 돌려준다.

    경로 구분자는 `/` 를 유지한다. Claude Code 설정은 Windows 에서도 `/` 를 쓰며,
    `\\` 로 바꾸면 JSON 안에서 이스케이프가 필요해져 규칙이 깨진다.

    **횟수는 진행 중인 문자열에서 센다.** 쌍마다 원문을 따로 세면 한 쌍이 다른 쌍을 품을 때
    (`/home/me/work` 와 `/home/me`) 같은 자리가 두 번 세어진다. 횟수는 사용자가 「무엇이
    바뀌는가」를 좁히는 재료라, 부풀면 없는 변경을 찾게 만든다.

    Args:
        text: 원본 문자열
        environment: 실측 정보

    Returns:
        tuple[str, int]: (치환된 문자열, 바꾼 자리 수)
    """
    result = text
    replaced = 0

    for source, target in environment.path_map.items():
        replaced += result.count(source)
        result = result.replace(source, target)

    return result, replaced


def transform_text(text: str, environment: Environment) -> str:
    """출처 PC 의 경로를 이 PC 의 경로로 바꾼다.

    Args:
        text: 원본 문자열
        environment: 실측 정보

    Returns:
        str: 치환된 문자열
    """
    transformed, _replaced = transform_text_counted(text, environment)

    return transformed


def missing_hint_tools(command: str) -> list[str]:
    """훅 명령에 나타나는 도구 중 이 PC 에서 찾을 수 없는 것을 고른다.

    이름을 부분 문자열로 찾으므로 셸 문법을 해석하지 않는다. **판단 재료를 모을 뿐
    판정하지 않는다** — 이 목록이 비어 있어도 그 훅이 이식 가능하다는 뜻은 아니다.

    Args:
        command: 훅의 셸 명령

    Returns:
        list[str]: 명령에 등장하지만 이 PC 에 없는 도구
    """
    return [tool for tool in PORTABILITY_HINT_TOOLS if tool in command and shutil.which(tool) is None]


def _classify_value(key: str, value: object, environment: Environment) -> Verdict:
    """설정 항목 하나를 판정한다.

    **권한 규칙은 명령이 이 PC 에 없다는 이유로 제외하지 않는다.** 규칙은 「이 명령을
    쓰면 승인 없이 실행한다」는 뜻이라 명령이 없으면 그냥 안 쓰일 뿐 해가 없고, 나중에
    설치하면 그대로 살아난다. 빼면 오히려 그때 승인창이 뜬다.
    실행 여부를 따지는 것은 «훅» 뿐이다 — 훅은 없는 명령을 부르면 매번 실패한다.

    **치환할지는 「치환이 실제로 무언가를 바꾸는가」로 정한다.** 출처 홈이 문자열에 있는지로
    정하면 **출처 PC 의 홈 «밖» 경로가 통과한다** — 결정 파일의 `path_map` 에 쌍을 넣어도
    이 조건에 걸리지 않아 죽은 경로가 그대로 쓰인다. `ask` 가드가 그렇게 되면 보호가
    조용히 사라진다. 조건을 치환 함수와 같은 것을 보게 두면 둘이 어긋날 자리가 없다.

    Args:
        key: 항목 식별자
        value: 항목 값
        environment: 실측 정보

    Returns:
        Verdict: 판정 결과
    """
    source_hash = _hash_value(value)
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    transformed = transform_text(text, environment)

    if transformed != text:
        return Verdict(
            key=key,
            decision=TRANSFORM,
            reason="출처 PC 의 경로를 이 PC 경로로 바꿉니다",
            source_hash=source_hash,
            detail=transformed,
        )

    return Verdict(key=key, decision=APPLY, reason="", source_hash=source_hash)


def matcher_labels(groups: list[Any]) -> list[str]:
    """한 이벤트의 그룹마다 서로 겹치지 않는 라벨을 만든다.

    **matcher 만으로는 부족하다.** matcher 가 «같은» 그룹도 한 이벤트에 여럿 달릴 수 있어
    (실측: mac 번들의 `SessionStart` 두 그룹이 모두 `*`), 그때는 matcher 를 키에 넣어도
    여전히 충돌한다. 그래서 같은 matcher 가 두 번째로 나올 때부터 순번을 붙인다.

    **첫 그룹은 matcher 를 그대로 둔다.** 형식을 통째로 바꾸면 기존 키가 전부 달라져
    사용자가 이미 승인한 항목까지 다시 물어야 한다. 재승인 대상을 실제로 겹친 쌍으로만 한정한다.

    **붙인 순번이 다른 matcher 와 부딪히면 더 밀어낸다** — matcher 가 `*#2` 라는 문자열일
    수도 있어서, 순번을 한 번 붙이는 것만으로는 「겹치지 않는다」가 보장되지 않는다.

    Args:
        groups: 한 이벤트에 달린 훅 그룹들

    Returns:
        list[str]: 그룹 순서대로의 라벨. 서로 겹치지 않는다
    """
    seen: dict[str, int] = {}
    labels: list[str] = []

    for group in groups:
        matcher = str(group.get("matcher", "*"))
        seen[matcher] = seen.get(matcher, 0) + 1
        label = matcher if seen[matcher] == 1 else f"{matcher}#{seen[matcher]}"

        while label in labels:
            seen[matcher] += 1
            label = f"{matcher}#{seen[matcher]}"

        labels.append(label)

    return labels


def hook_key(event: str, matcher_label: str, index: int) -> str:
    """훅의 항목 식별자를 만든다.

    키는 **이벤트 + 그룹 라벨 + 그룹 안 순번** 셋으로 항목 하나를 유일하게 가리킨다.
    라벨은 `matcher_labels` 가 만든 것이어야 한다 — 날 matcher 를 그대로 넣으면
    matcher 가 같은 그룹끼리 키가 겹치고, **결정 파일에서 한쪽이 다른 쪽을 덮어쓴다.**

    Args:
        event: 훅 이벤트 이름
        matcher_label: `matcher_labels` 가 만든 그룹 라벨
        index: 그룹 안에서의 순번

    Returns:
        str: 항목 식별자
    """
    return f"settings.json#hooks.{event}[{matcher_label}][{index}]"


def _classify_hook(
    event: str, matcher_label: str, index: int, hook: dict[str, Any], environment: Environment
) -> Verdict:
    """훅 하나를 판정한다.

    **훅은 자동으로 판정하지 않고 사람에게 넘긴다.** 셸 명령의 이식성은 문맥을 알아야
    판단할 수 있다 — `terminal-notifier` 는 macOS 전용이지만
    `command -v python3 || command -v python` 은 폴백이 있어 그대로 동작한다.
    이 차이를 파서가 알 수 없다.

    기본 제안은 «제외» 다. 깨진 훅은 매 이벤트마다 실패하므로 그쪽이 안전하다.
    사용자가 「적용」으로 바꾸면 그 결정이 누적돼 다음부터 묻지 않는다.

    Args:
        event: 훅 이벤트 이름
        matcher_label: `matcher_labels` 가 만든 그룹 라벨
        index: 그룹 안에서의 순번
        hook: 훅 정의
        environment: 실측 정보

    Returns:
        Verdict: 판정 결과
    """
    command = str(hook.get("command", ""))
    key = hook_key(event, matcher_label, index)
    missing = missing_hint_tools(command)

    hint = f" (이 PC 에 없는 도구: `{'`, `'.join(missing)}`)" if missing else ""
    transformed = transform_text(command, environment)
    path_note = " — 경로 치환이 필요합니다" if transformed != command else ""

    return Verdict(
        key=key,
        decision=EXCLUDE,
        reason=f"훅은 이식성을 사람이 판단합니다{hint}{path_note}",
        source_hash=_hash_value(hook),
        detail=transformed,
        needs_confirmation=True,
    )


def _classify_directory(key: str, raw_path: str, environment: Environment) -> Verdict:
    """추가 작업 디렉터리를 판정한다.

    권한 규칙과 달리 **경로는 실재를 따진다.** 없는 폴더를 작업 디렉터리로 등록하면
    그 PC 에서 쓰이지 않는 항목이 쌓이고, 사용자는 왜 있는지 모른다.

    Args:
        key: 항목 식별자
        raw_path: 번들에 적힌 경로
        environment: 실측 정보

    Returns:
        Verdict: 판정 결과
    """
    transformed = transform_text(raw_path, environment)
    source_hash = _hash_value(raw_path)

    if not Path(transformed).is_dir():
        return Verdict(
            key=key,
            decision=EXCLUDE,
            reason="이 PC 에 없는 경로입니다",
            source_hash=source_hash,
            detail=transformed,
            needs_confirmation=True,
        )

    if transformed != raw_path:
        return Verdict(
            key=key,
            decision=TRANSFORM,
            reason="경로를 이 PC 기준으로 바꿉니다",
            source_hash=source_hash,
            detail=transformed,
        )

    return Verdict(key=key, decision=APPLY, reason="", source_hash=source_hash)


def classify_settings(settings: dict[str, Any], environment: Environment) -> list[Verdict]:
    """`settings.json` 을 항목 단위로 판정한다.

    파일 통째로 판정하면 훅 하나 때문에 권한 142건이 함께 버려진다.

    Args:
        settings: 번들의 `settings.json` 내용
        environment: 실측 정보

    Returns:
        list[Verdict]: 항목별 판정
    """
    verdicts: list[Verdict] = []

    permissions: dict[str, Any] = settings.get("permissions", {})
    for section, entries in permissions.items():
        if not isinstance(entries, list):
            verdicts.append(_classify_value(f"settings.json#permissions.{section}", entries, environment))
            continue

        for entry in entries:  # pyright: ignore[reportUnknownVariableType]
            key = f"settings.json#permissions.{section}::{entry}"
            if section == "additionalDirectories":
                verdicts.append(_classify_directory(key, str(entry), environment))
                continue
            verdicts.append(_classify_value(key, entry, environment))

    for event, groups in settings.get("hooks", {}).items():
        for label, group in zip(matcher_labels(groups), groups, strict=True):
            for index, hook in enumerate(group.get("hooks", [])):
                verdicts.append(_classify_hook(event, label, index, hook, environment))

    for key, value in settings.items():
        if key in ("permissions", "hooks"):
            continue
        verdicts.append(_classify_value(f"settings.json#{key}", value, environment))

    return verdicts


def _server_map(container: dict[str, Any]) -> dict[str, Any]:
    """설정 조각에서 `mcpServers` 를 꺼낸다.

    Args:
        container: 최상위 설정이나 프로젝트 설정

    Returns:
        dict[str, Any]: 서버 묶음. 없거나 형태가 다르면 빈 dict
    """
    servers = container.get("mcpServers")

    return servers if isinstance(servers, dict) else {}


def _sentinel_fields(definition: dict[str, Any]) -> list[str]:
    """서버 정의에서 가려진 필드 경로를 모은다.

    Args:
        definition: 서버 정의

    Returns:
        list[str]: 가려진 필드 경로 (`headers.API_KEY` 형태)
    """
    fields: list[str] = []

    for block_name in CREDENTIAL_VALUE_BLOCKS:
        block = definition.get(block_name)
        if not isinstance(block, dict):
            continue

        fields.extend(f"{block_name}.{key}" for key, value in block.items() if value == REDACTED_SENTINEL)

    # url 은 센티널이 문자열 «안에» 박혀 오므로 포함 여부로 본다 (`restore_redacted` 와 같은 판정)
    url = definition.get("url")
    if isinstance(url, str) and REDACTED_SENTINEL in url:
        fields.append("url")

    return fields


def restore_redacted(
    bundle_definition: dict[str, Any], existing_definition: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """가려진 자격증명 값을 이 PC 의 기존 값으로 되돌린다.

    받는 쪽은 서버 정의를 통째로 대입하므로, 되돌리지 않으면 **이 PC 에서 쓰고 있던 진짜
    키가 센티널로 덮인다.**

    되돌릴 값이 없으면 센티널을 «남긴다». 서버를 통째로 빼면 「빠뜨리면 MCP 가 통째로
    사라진다」는 이 기능의 취지에 역행하기 때문이며, 대신 무엇을 채워야 하는지 알려준다.

    가려진 «자리마다» 판정한다. 블록 단위로 되돌리면 같은 `headers` 안에서 번들이 새로
    바꾼 일반 헤더가 옛 값으로 돌아간다.

    Args:
        bundle_definition: 번들의 서버 정의
        existing_definition: 이 PC 에 이미 있는 같은 서버의 정의 (없으면 빈 dict)

    Returns:
        tuple[dict[str, Any], list[str]]: (되돌린 사본, 직접 채워야 할 필드 경로).
            원본은 바뀌지 않는다
    """
    restored = copy.deepcopy(bundle_definition)
    missing: list[str] = []

    for block_name in CREDENTIAL_VALUE_BLOCKS:
        block = restored.get(block_name)
        if not isinstance(block, dict):
            continue

        existing_block = existing_definition.get(block_name)
        existing_block = existing_block if isinstance(existing_block, dict) else {}

        for key, value in block.items():  # pyright: ignore[reportUnknownVariableType]
            if value != REDACTED_SENTINEL:
                continue

            kept = existing_block.get(key)
            if isinstance(kept, str) and kept != REDACTED_SENTINEL:
                block[key] = kept
                continue

            missing.append(f"{block_name}.{key}")

    # `url` 은 센티널이 «문자열 안에» 박혀 온다(query 값·userinfo·fragment 만 가려진다).
    # 그래서 완전일치로는 못 잡고, 되돌릴 때도 조각을 꿰맞추지 않고 **이 PC 의 url 을 통째로**
    # 쓴다 — 어느 조각이 가려졌는지와 무관하게 그쪽이 이 PC 의 진실이다.
    #
    # 이걸 빠뜨리면 번들의 센티널 url 이 **작동 중인 url 을 덮어써 서버가 조용히 죽는다.**
    url = restored.get("url")
    if isinstance(url, str) and REDACTED_SENTINEL in url:
        kept_url = existing_definition.get("url")
        if isinstance(kept_url, str) and REDACTED_SENTINEL not in kept_url:
            restored["url"] = kept_url
        else:
            missing.append("url")

    return restored, missing


def _redaction_note(bundle_servers: dict[str, Any], existing_servers: dict[str, Any]) -> str:
    """가려진 값이 어떻게 처리되는지 한 줄로 만든다.

    **적용한 뒤에 알면 늦다.** 무엇이 이 PC 의 값으로 남고 무엇을 직접 채워야 하는지를
    승인 전에 보여준다.

    Args:
        bundle_servers: 번들의 서버 묶음
        existing_servers: 이 PC 의 같은 자리 서버 묶음

    Returns:
        str: 안내 문구. 가려진 값이 없으면 빈 문자열
    """
    kept: list[str] = []
    missing: list[str] = []

    for name, definition in bundle_servers.items():
        existing = existing_servers.get(name)
        _restored, server_missing = restore_redacted(definition, existing if isinstance(existing, dict) else {})

        for field_path in _sentinel_fields(definition):
            target = missing if field_path in server_missing else kept
            target.append(f"{name}.{field_path}")

    notes: list[str] = []
    if kept:
        notes.append(f"이 PC 의 기존 값을 유지합니다 ({', '.join(kept)})")
    if missing:
        notes.append(f"이 PC 에서 직접 채워야 합니다 ({', '.join(missing)})")

    return " / ".join(notes)


def _with_note(reason: str, note: str) -> str:
    """판정 사유에 안내를 덧붙인다.

    Args:
        reason: 기존 사유 (없을 수 있다)
        note: 덧붙일 안내 (없을 수 있다)

    Returns:
        str: 합친 문구
    """
    return " / ".join(part for part in (reason, note) if part)


def classify_claude_json(
    claude_json: dict[str, Any], environment: Environment, existing_claude_json: dict[str, Any]
) -> list[Verdict]:
    """`~/.claude.json` 에서 옮겨온 값을 판정한다.

    프로젝트별 설정은 **그 저장소가 이 PC 에 있을 때만** 뜻이 있다. 없는 저장소의
    권한을 넣으면 쓰이지 않는 항목이 쌓인다.

    Args:
        claude_json: 번들의 `claude_json.json` 내용
        environment: 실측 정보
        existing_claude_json: 이 PC 의 `~/.claude.json` 내용 (없는 PC 면 빈 dict).
            **인자로 받는 이유**는 여기서 실경로를 직접 읽으면 테스트가 사용자 홈을 건드리기 때문이다

    Returns:
        list[Verdict]: 항목별 판정
    """
    verdicts: list[Verdict] = []

    existing_servers = _server_map(existing_claude_json)
    for name, definition in claude_json.get("mcpServers", {}).items():
        verdict = _classify_value(f"claude_json.json#mcpServers.{name}", definition, environment)
        verdict.reason = _with_note(verdict.reason, _redaction_note({name: definition}, existing_servers))
        verdicts.append(verdict)

    existing_projects: dict[str, Any] = existing_claude_json.get("projects", {})
    for project_path, definition in claude_json.get("projects", {}).items():
        key = f"claude_json.json#projects.{project_path}"
        transformed = transform_text(project_path, environment)

        if not Path(transformed).is_dir():
            verdicts.append(
                Verdict(
                    key=key,
                    decision=EXCLUDE,
                    reason="이 PC 에 없는 저장소입니다",
                    source_hash=_hash_value(definition),
                    detail=transformed,
                    needs_confirmation=True,
                )
            )
            continue

        existing_project = existing_projects.get(transformed)
        note = _redaction_note(
            _server_map(definition), _server_map(existing_project) if isinstance(existing_project, dict) else {}
        )

        verdicts.append(
            Verdict(
                key=key,
                decision=TRANSFORM if transformed != project_path else APPLY,
                reason=_with_note("저장소 경로를 이 PC 경로로 바꿉니다" if transformed != project_path else "", note),
                source_hash=_hash_value(definition),
                detail=transformed,
            )
        )

    return verdicts


def classify_files(environment: Environment) -> list[Verdict]:
    """번들의 파일을 판정한다.

    `settings.json` 은 항목 단위로 따로 판정하므로 여기서 제외한다.

    Args:
        environment: 실측 정보

    Returns:
        list[Verdict]: 파일별 판정

    Raises:
        ValueError: 번들이 없는 경우
    """
    if not BUNDLE_HOME_DIR.is_dir():
        raise ValueError(f"번들이 없습니다: {BUNDLE_HOME_DIR}")

    verdicts: list[Verdict] = []
    for path in sorted(BUNDLE_HOME_DIR.rglob("*")):
        if not path.is_file():
            continue

        relative = path.relative_to(BUNDLE_HOME_DIR)
        if relative.as_posix() == "settings.json":
            continue

        raw = path.read_bytes()
        source_hash = hashlib.sha256(raw).hexdigest()
        key = f"home/{relative.as_posix()}"

        if path.suffix not in TEXT_SUFFIXES or not environment.path_map:
            verdicts.append(Verdict(key=key, decision=APPLY, reason="", source_hash=source_hash))
            continue

        text = raw.decode("utf-8", errors="replace")
        transformed, occurrences = transform_text_counted(text, environment)
        if transformed != text:
            verdicts.append(
                Verdict(
                    key=key,
                    decision=TRANSFORM,
                    reason=f"경로 {occurrences}곳을 바꿉니다",
                    source_hash=source_hash,
                )
            )
            continue

        verdicts.append(Verdict(key=key, decision=APPLY, reason="", source_hash=source_hash))

    return verdicts


def load_decisions(environment: Environment) -> dict[str, Any]:
    """이 PC 의 지난 결정을 읽는다.

    Args:
        environment: 실측 정보

    Returns:
        dict[str, Any]: 저장된 결정. 없으면 빈 구조
    """
    path = DECISIONS_DIR / f"{environment.pc_id}.json"
    if not path.is_file():
        return {"pc_id": environment.pc_id, "items": {}}

    return json.loads(path.read_text(encoding="utf-8"))


def apply_previous_decisions(plan: Plan, decisions: dict[str, Any]) -> None:
    """지난 결정을 이번 판정에 반영한다.

    **해시가 같을 때만** 재사용한다. 내용이 바뀐 항목에 옛 결정을 적용하면 사용자가
    승인한 적 없는 상태가 조용히 만들어진다.

    **되살리는 것은 「넣을까 뺄까」뿐이다.** 해시는 항목 «값» 만 담고 `path_map` 은 담지
    않으므로, 쌍을 나중에 더해도 해시는 그대로다. 그때 기억된 «형태» 까지 되살리면
    **새 쌍이 생겼는데도 옛 `APPLY` 가 이겨 죽은 경로가 그대로 쓰인다** — 실제로 3 회차에서
    권한 규칙 18건이 그 경로로 죽었고, 손으로 결정을 지워야 했다.
    그래서 양쪽이 다 「넣는다」면 형태는 **이번 판정** 을 쓴다.

    Args:
        plan: 이번 판정
        decisions: 저장된 결정
    """
    stored: dict[str, Any] = decisions.get("items", {})

    for verdict in plan.verdicts:
        remembered = stored.get(verdict.key)
        if remembered is None:
            continue

        if remembered.get("source_hash") != verdict.source_hash:
            if verdict.decision == EXCLUDE:
                verdict.reason = f"{verdict.reason} (지난 결정이 있으나 내용이 바뀌어 다시 묻습니다)"
            continue

        remembered_decision = str(remembered["decision"])
        verdict.needs_confirmation = False

        if remembered_decision in INCLUDE_DECISIONS and verdict.decision in INCLUDE_DECISIONS:
            continue

        verdict.decision = remembered_decision
        verdict.reason = str(remembered.get("reason", ""))


def build_plan() -> Plan:
    """이 PC 에 대한 적용 계획을 만든다.

    Returns:
        Plan: 판정 결과
    """
    environment = detect_environment()
    plan = Plan(environment=environment)

    plan.verdicts.extend(classify_files(environment))

    settings_path = BUNDLE_HOME_DIR / "settings.json"
    if settings_path.is_file():
        plan.verdicts.extend(classify_settings(json.loads(settings_path.read_text(encoding="utf-8")), environment))

    if BUNDLE_CLAUDE_JSON_PATH.is_file():
        existing_claude_json: dict[str, Any] = {}
        if TARGET_CLAUDE_JSON.is_file():
            existing_claude_json = json.loads(TARGET_CLAUDE_JSON.read_text(encoding="utf-8"))

        plan.verdicts.extend(
            classify_claude_json(
                json.loads(BUNDLE_CLAUDE_JSON_PATH.read_text(encoding="utf-8")), environment, existing_claude_json
            )
        )

    apply_previous_decisions(plan, load_decisions(environment))

    return plan


def render_plan(plan: Plan) -> str:
    """판정 결과를 사람이 읽을 표로 만든다.

    제외 후보는 **하나씩 사유와 함께** 보여준다. 사유 없이 목록만 주면 승인할 수 없다.

    Args:
        plan: 판정 결과

    Returns:
        str: 출력할 본문
    """
    environment = plan.environment
    lines = [
        f"적용 대상: {environment.hostname} ({environment.platform})",
        f"번들 출처: {environment.source_hostname} (홈 {environment.source_home})",
        "",
    ]

    for decision in (APPLY, TRANSFORM, EXCLUDE):
        items = plan.by_decision(decision)
        lines.append(f"[{DECISION_LABELS[decision]}] {len(items)}건")

    excluded = plan.by_decision(EXCLUDE)
    pending = [verdict for verdict in excluded if verdict.needs_confirmation]

    if pending:
        lines.extend(["", f"--- 승인이 필요한 제외 후보 {len(pending)}건 ---"])
        for verdict in pending:
            lines.append(f"  {verdict.key}")
            lines.append(f"      사유: {verdict.reason}")
            if verdict.detail:
                lines.append(f"      내용: {verdict.detail[:110]}")

    transformed = plan.by_decision(TRANSFORM)
    if transformed:
        lines.extend(["", f"--- 경로를 바꿔 적용할 항목 {len(transformed)}건 ---"])
        for verdict in transformed:
            lines.append(f"  {verdict.key} — {verdict.reason}")

    # 그대로 적용하는 항목은 원래 사유가 없다. 사유가 붙어 있다면 알아둘 것이 있다는 뜻이며,
    # 지금은 가려진 자격증명 안내가 그 경로다. **여기서 보여주지 않으면 적용한 뒤에야 알게 된다**
    noted = [verdict for verdict in plan.by_decision(APPLY) if verdict.reason]
    if noted:
        lines.extend(["", f"--- 그대로 적용하되 알아둘 것 {len(noted)}건 ---"])
        for verdict in noted:
            lines.append(f"  {verdict.key} — {verdict.reason}")

    return "\n".join(lines)


def save_decisions(plan: Plan) -> Path:
    """이번 판정을 결정 파일로 남긴다.

    Args:
        plan: 판정 결과

    Returns:
        Path: 저장한 결정 파일 경로
    """
    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = DECISIONS_DIR / f"{plan.environment.pc_id}.json"

    payload = {
        "pc_id": plan.environment.pc_id,
        "platform": plan.environment.platform,
        "source_hostname": plan.environment.source_hostname,
        "path_map": plan.environment.extra_path_map,
        "updated_at": datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M %z"),
        "items": {
            verdict.key: {
                "decision": verdict.decision,
                "reason": verdict.reason,
                "source_hash": verdict.source_hash,
            }
            for verdict in plan.verdicts
        },
    }

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return path


def _decision_map(plan: Plan) -> dict[str, Verdict]:
    """항목 식별자로 판정을 찾을 수 있게 만든다.

    Args:
        plan: 판정 결과

    Returns:
        dict[str, Verdict]: 식별자 -> 판정
    """
    return {verdict.key: verdict for verdict in plan.verdicts}


def _transformed(value: object, environment: Environment) -> object:
    """값 안의 출처 경로를 이 PC 경로로 바꾼다.

    문자열이 아니면 직렬화해 치환하고 되돌린다. 중첩된 구조 안의 경로도 바뀐다.

    Args:
        value: 원본 값
        environment: 실측 정보

    Returns:
        object: 치환된 값
    """
    if isinstance(value, str):
        return transform_text(value, environment)

    return json.loads(transform_text(json.dumps(value, ensure_ascii=False), environment))


def rebuild_settings(settings: dict[str, Any], plan: Plan, environment: Environment) -> dict[str, Any]:
    """판정에 따라 `settings.json` 을 다시 조립한다.

    제외된 항목만 빠지고 나머지는 살아남는다. 훅 그룹이 통째로 비면 그 그룹도 뺀다 —
    빈 그룹을 남기면 Claude Code 가 읽을 때 의미 없는 항목이 된다.

    Args:
        settings: 번들의 `settings.json` 내용
        plan: 판정 결과
        environment: 실측 정보

    Returns:
        dict[str, Any]: 이 PC 에 쓸 설정
    """
    decisions = _decision_map(plan)
    result: dict[str, Any] = {}

    rebuilt_permissions: dict[str, Any] = {}
    for section, entries in settings.get("permissions", {}).items():
        if not isinstance(entries, list):
            verdict = decisions.get(f"settings.json#permissions.{section}")
            if verdict is not None and verdict.decision != EXCLUDE:
                rebuilt_permissions[section] = entries
            continue

        kept: list[Any] = []
        for entry in entries:  # pyright: ignore[reportUnknownVariableType]
            verdict = decisions.get(f"settings.json#permissions.{section}::{entry}")
            if verdict is None or verdict.decision == EXCLUDE:
                continue
            kept.append(_transformed(entry, environment) if verdict.decision == TRANSFORM else entry)

        rebuilt_permissions[section] = kept

    if rebuilt_permissions:
        result["permissions"] = rebuilt_permissions

    rebuilt_hooks: dict[str, Any] = {}
    for event, groups in settings.get("hooks", {}).items():
        kept_groups: list[Any] = []
        for label, group in zip(matcher_labels(groups), groups, strict=True):
            kept_hooks: list[Any] = []

            for index, hook in enumerate(group.get("hooks", [])):
                verdict = decisions.get(hook_key(event, label, index))
                if verdict is None or verdict.decision == EXCLUDE:
                    continue
                new_hook = dict(hook)
                if verdict.decision == TRANSFORM:
                    new_hook["command"] = transform_text(str(hook.get("command", "")), environment)
                kept_hooks.append(new_hook)

            if kept_hooks:
                new_group = dict(group)
                new_group["hooks"] = kept_hooks
                kept_groups.append(new_group)

        if kept_groups:
            rebuilt_hooks[event] = kept_groups

    if rebuilt_hooks:
        result["hooks"] = rebuilt_hooks

    for key, value in settings.items():
        if key in ("permissions", "hooks"):
            continue
        verdict = decisions.get(f"settings.json#{key}")
        if verdict is None or verdict.decision == EXCLUDE:
            continue
        result[key] = _transformed(value, environment) if verdict.decision == TRANSFORM else value

    return result


def backup_targets() -> list[Path]:
    """덮어쓸 파일을 먼저 백업한다.

    **되돌릴 수 없는 덮어쓰기를 만들지 않는다.** 받는 PC 에 그 PC 고유의 설정이
    있을 수 있고, 적용 후에야 그것을 알아채는 경우가 있다.

    Returns:
        list[Path]: 만든 백업 파일
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    made: list[Path] = []

    for path in (TARGET_CLAUDE_HOME / "settings.json", TARGET_CLAUDE_JSON):
        if not path.is_file():
            continue
        backup = path.with_name(f"{path.name}.bak-{stamp}")
        shutil.copy2(path, backup)
        made.append(backup)

    return made


def merge_claude_json(plan: Plan, environment: Environment) -> list[str]:
    """`~/.claude.json` 에 MCP 등록과 프로젝트 설정을 «병합» 한다.

    덮어쓰지 않는다. 이 파일에는 그 PC 의 온보딩 상태·캐시·통계가 들어 있어
    통째로 바꾸면 Claude Code 가 처음 실행처럼 동작한다.

    가려진 자격증명은 **이 PC 의 기존 값으로 되돌린 뒤에** 넣는다. 그냥 대입하면
    쓰고 있던 진짜 키가 센티널로 덮인다.

    Args:
        plan: 판정 결과
        environment: 실측 정보

    Returns:
        list[str]: 이 PC 에서 직접 채워야 하는 자격증명의 키 경로
    """
    if not BUNDLE_CLAUDE_JSON_PATH.is_file():
        return []

    bundle: dict[str, Any] = json.loads(BUNDLE_CLAUDE_JSON_PATH.read_text(encoding="utf-8"))
    existing: dict[str, Any] = {}
    if TARGET_CLAUDE_JSON.is_file():
        existing = json.loads(TARGET_CLAUDE_JSON.read_text(encoding="utf-8"))

    decisions = _decision_map(plan)
    needs_fill: list[str] = []

    servers: dict[str, Any] = existing.get("mcpServers", {})
    for name, definition in bundle.get("mcpServers", {}).items():
        verdict = decisions.get(f"claude_json.json#mcpServers.{name}")
        if verdict is None or verdict.decision == EXCLUDE:
            continue

        prepared = _transformed(definition, environment) if verdict.decision == TRANSFORM else definition
        existing_server = servers.get(name)
        restored, missing = restore_redacted(prepared, existing_server if isinstance(existing_server, dict) else {})

        servers[name] = restored
        needs_fill.extend(f"mcpServers.{name}.{field}" for field in missing)
    if servers:
        existing["mcpServers"] = servers

    projects: dict[str, Any] = existing.get("projects", {})
    for project_path, definition in bundle.get("projects", {}).items():
        verdict = decisions.get(f"claude_json.json#projects.{project_path}")
        if verdict is None or verdict.decision == EXCLUDE:
            continue

        target_path = transform_text(project_path, environment)
        existing_project: dict[str, Any] = dict(projects.get(target_path, {}))
        merged: dict[str, Any] = dict(existing_project)
        merged.update(definition)

        bundle_servers = _server_map(definition)
        if bundle_servers:
            existing_project_servers = _server_map(existing_project)
            restored_servers: dict[str, Any] = {}
            for name, server in bundle_servers.items():
                existing_server = existing_project_servers.get(name)
                restored, missing = restore_redacted(
                    server, existing_server if isinstance(existing_server, dict) else {}
                )
                restored_servers[name] = restored
                needs_fill.extend(f"projects[{target_path}].mcpServers.{name}.{field}" for field in missing)
            merged["mcpServers"] = restored_servers

        projects[target_path] = merged
    if projects:
        existing["projects"] = projects

    TARGET_CLAUDE_JSON.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return needs_fill


def apply_plan(plan: Plan) -> list[str]:
    """판정에 따라 이 PC 에 적용한다.

    Args:
        plan: 판정 결과

    Returns:
        list[str]: 수행한 작업 요약
    """
    environment = plan.environment
    performed = [f"백업: {path}" for path in backup_targets()]

    copied = 0
    for verdict in plan.verdicts:
        if not verdict.key.startswith("home/") or verdict.decision == EXCLUDE:
            continue

        relative = Path(verdict.key[len("home/") :])
        source = BUNDLE_HOME_DIR / relative
        target = TARGET_CLAUDE_HOME / relative
        target.parent.mkdir(parents=True, exist_ok=True)

        if verdict.decision == TRANSFORM:
            target.write_text(transform_text(source.read_text(encoding="utf-8"), environment), encoding="utf-8")
        else:
            shutil.copy2(source, target)
        copied += 1

    performed.append(f"파일 {copied}개 적용")

    bundle_settings_path = BUNDLE_HOME_DIR / "settings.json"
    if bundle_settings_path.is_file():
        rebuilt = rebuild_settings(json.loads(bundle_settings_path.read_text(encoding="utf-8")), plan, environment)
        (TARGET_CLAUDE_HOME / "settings.json").write_text(
            json.dumps(rebuilt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        performed.append("settings.json 재조립 완료")

    needs_fill = merge_claude_json(plan, environment)
    performed.append("~/.claude.json 병합 완료")

    if needs_fill:
        performed.append(f"[중요] 이 PC 에서 직접 채워야 할 자격증명 {len(needs_fill)}건:")
        performed.extend(f"    {key}" for key in needs_fill)

    return performed


def parse_args() -> argparse.Namespace:
    """명령행 인자를 해석한다.

    Returns:
        argparse.Namespace: 해석된 인자
    """
    parser = argparse.ArgumentParser(description="번들을 이 PC 에 어떻게 적용할지 판정한다")
    parser.add_argument("--save-decisions", action="store_true", help="판정 결과를 결정 파일로 저장한다")
    parser.add_argument("--apply", action="store_true", help="판정에 따라 실제로 적용한다 (승인 후에만 쓴다)")

    return parser.parse_args()


def main() -> int:
    """스크립트 진입점.

    Returns:
        int: 종료 코드
    """
    args = parse_args()

    try:
        plan = build_plan()
    except ValueError as error:
        print(f"[오류] {error}", file=sys.stderr)
        return 1

    print(render_plan(plan))

    if args.apply:
        pending = [verdict for verdict in plan.by_decision(EXCLUDE) if verdict.needs_confirmation]
        if pending:
            print(
                f"\n[중단] 승인받지 않은 제외 후보가 {len(pending)}건 남아 있습니다."
                "\n판정표를 사용자에게 보여주고 결정을 받은 뒤 --save-decisions 로 저장하세요.",
                file=sys.stderr,
            )
            return 1

        for line in apply_plan(plan):
            print(f"  {line}")
        print("\n적용했습니다. Claude Code 를 다시 시작하면 반영됩니다.")

    if args.save_decisions:
        saved = save_decisions(plan)
        print(f"\n결정을 저장했습니다: {saved}")
    elif not args.apply:
        print("\n(판정만 했습니다. 승인 후 --save-decisions 로 결정을 남기세요)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
