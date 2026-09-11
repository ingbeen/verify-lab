# [mac 작업 의뢰] 하네스 메모리 차단 훅의 워크스페이스 경로를 이식 가능하게 고친다

> **이 문서를 여는 PC**: 회사 mac (`yubeens-Mac-mini.local`)
> **작성**: 2026-09-12, 집 WSL(`DESKTOP-4CN5LK3`)에서 번들을 받다가 발견
> **끝나면 이 문서는 지웁니다.** 일회성 의뢰서이고, 남길 근거는 이미
> `.claude/skills/claude-config-import/SKILL.md` 의 「실측 기록 — 두 번째 회차」에 있습니다.

---

## 1. 무엇을 고치나

**파일**: `~/.claude/hooks/block-harness-memory-write.py` (mac 의 전역 훅. 이 저장소 안이 아닙니다)

`_WORKSPACE` 를 만드는 세 줄을, 폴더 이름의 **대소문자가 다른 PC 에서도** 맞게 고칩니다.

### 고치기 전

```python
_HOME = os.path.expanduser("~")
_PROJECTS_ROOT = os.path.realpath(os.path.join(_HOME, ".claude", "projects"))
_WORKSPACE = os.path.realpath(os.path.join(_HOME, "Workspace"))
```

### 고친 뒤

```python
_HOME = os.path.expanduser("~")
_PROJECTS_ROOT = os.path.realpath(os.path.join(_HOME, ".claude", "projects"))


def _resolve_workspace():
    """워크스페이스 폴더의 실제 경로를 찾는다.

    **PC 마다 이 폴더 이름의 대소문자가 다르다** — mac 은 `~/Workspace`, WSL 은 `~/workspace` 다.
    슬러그는 저장소 절대경로에서 만들어지므로 대소문자가 어긋나면 «영원히 일치하지 않고»,
    훅은 등록돼 있는데 한 번도 발동하지 않는다. 에러도 로그도 없다.

    이름을 하나로 박으면 한쪽 PC 에서 조용히 죽으므로 실재하는 쪽을 쓴다.
    [실측] 2026-09-12 — WSL 의 슬러그는 `-home-yblee-workspace-verify-lab` 인데
    대문자로 만든 값은 `-home-yblee-Workspace-verify-lab` 이라 항상 빗나갔다.
    """
    for name in ("Workspace", "workspace"):
        candidate = os.path.join(_HOME, name)
        if os.path.isdir(candidate):
            return os.path.realpath(candidate)

    return os.path.realpath(os.path.join(_HOME, "Workspace"))


_WORKSPACE = _resolve_workspace()
```

**mac 에서 동작이 달라지지 않습니다.** `~/Workspace`(대문자)를 먼저 찾고 그게 실재하므로
지금과 똑같은 값이 나옵니다. 바뀌는 것은 소문자 워크스페이스를 쓰는 PC 뿐입니다.

---

## 2. 왜 이게 문제인가

훅은 **저장소 슬러그**(저장소 절대경로의 `/` 를 `-` 로 바꾼 문자열)로 대상을 판정합니다.
`_WORKSPACE` 가 틀리면 슬러그가 통째로 어긋나 **어떤 경로도 매칭되지 않습니다.**

🔴 **실패가 조용합니다.** 훅은 정상 등록되고 매번 실행되지만 아무것도 막지 않습니다.
에러도 로그도 없어서, 문서에는 「차단돼 있다」고 적혀 있는데 실제로는 안 걸린 상태가
오래 남습니다. 집 WSL 이 정확히 그 상태였습니다 — `docs/INDEX.md` 가 전부터
「하네스 메모리가 이 저장소에서 차단돼 있어(전역 훅) 새 사실은 여기 적는다」고
적고 있었지만, 기계는 한 번도 그렇게 동작한 적이 없었습니다.

**번들의 경로 치환이 이걸 못 잡습니다.** 치환은 파일 안의 «문자열»을 바꾸는데,
이 경로는 런타임에 `~` 에서 조립되므로 파일에는 `Workspace` 라는 낱말만 있습니다.
그래서 받는 쪽 판정이 「그대로 적용」으로 통과시킵니다.

---

## 3. 고친 뒤 확인

**셸에 경로를 직접 치지 마세요.** `<슬러그>/memory` 와 리다이렉트가 한 줄에 있으면
**그 명령 자체가 이 훅에 막힙니다**(실제로 겪었습니다). 아래를 파일로 저장해 실행합니다.

```python
# ~/verify_hook.py
import json, os, subprocess

HOOK = os.path.expanduser("~/.claude/hooks/block-harness-memory-write.py")
ROOT = os.path.expanduser("~/.claude/projects")
MEM = "memory"

# mac 의 실제 워크스페이스에서 슬러그를 만든다
slug = os.path.realpath(os.path.expanduser("~/Workspace/verify-lab")).replace(os.sep, "-")

CASES = [
    ("이 저장소 메모리 쓰기", "deny",
     {"tool_name": "Write", "tool_input": {"file_path": f"{ROOT}/{slug}/{MEM}/n.md"}}),
    ("메모리 읽기", "pass",
     {"tool_name": "Bash", "tool_input": {"command": "cat " + f"{ROOT}/{slug}/{MEM}/n.md"}}),
    ("평범한 문서 쓰기", "pass",
     {"tool_name": "Write", "tool_input": {"file_path": os.path.expanduser("~/Workspace/verify-lab/docs/x.md")}}),
]

for label, expected, payload in CASES:
    out = subprocess.run(["python3", HOOK], input=json.dumps(payload),
                         capture_output=True, text=True).stdout.strip()
    actual = json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else "pass"
    print(f"[{'OK ' if actual == expected else '다름'}] {label:<22} 기대={expected:<4} 실제={actual}")
```

```bash
python3 ~/verify_hook.py
```

**세 줄 모두 `OK` 여야 합니다.** 사내프로젝트 저장소(`~/Workspace/acme-docs` 등)로 슬러그를 바꿔
한 번 더 돌리면 `ACME_REASON` 쪽 분기도 확인됩니다.

---

## 4. 그 다음 — 다시 내보낸다

고친 훅이 다음 번들에 실리도록 mac 에서 내보내기를 돌립니다.

```
/claude-config-export
```

`claude-config/` 에 번들이 만들어지면 **사용자가 커밋·푸시**합니다.
집 PC 는 pull 한 뒤 `/claude-config-import` 를 돌리면 됩니다.

---

## 5. mac 에서 «할 일이 없는» 것

- **`plan_apply.py` 의 `hook_key` 충돌 수정** — 그 스킬은 저장소 안(`.claude/skills/`)에 있어
  **git pull 만으로 따라옵니다.** mac 에서 따로 할 것이 없습니다
- **집 PC 에서 제외한 훅들**(acme-docs 부트스트랩 3건 · `report_lint.py`) — 받는 쪽 결정일 뿐이라
  mac 설정은 그대로 둡니다. 결정은 `claude-config/decisions/DESKTOP-4CN5LK3-linux.json` 에만 쌓입니다

---

## 6. 참고 — 왜 이번에 훅 4개가 다시 물어졌나

내보내는 쪽에서 **훅 그룹의 순서나 구성을 바꾸면** 받는 쪽이 그 항목을 다시 묻습니다.
항목 식별자가 `이벤트 + 그룹 라벨 + 그룹 안 순번` 이라, 내용이 한 글자도 안 바뀌어도
자리가 옮겨지면 저장된 결정을 찾지 못하기 때문입니다.

**고장이 아니라 안전장치입니다** — 조용히 잘못 적용하는 것보다 다시 묻는 쪽이 낫습니다.
자세한 것은 `.claude/skills/claude-config-import/SKILL.md` 의
「결정이 쌓여도 내용이 바뀌면 다시 묻는다」 절에 표로 있습니다.
