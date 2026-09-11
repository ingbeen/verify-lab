# Implementation Plan: claude-config-import 의 hook_key 충돌 수정과 번들 적용

> 작성/운영 규칙(SoT): `/impl-plan` 스킬(`~/.claude/skills/impl-plan/SKILL.md`)을 반드시 참고하세요.  
> (이 템플릿을 수정하거나 새로운 양식의 계획서를 만들 때도 해당 스킬을 포인터로 두고 준수합니다.)

**상태**: ✅ Done

---

🚫 **이 영역은 삭제/수정 금지** 🚫

**상태 옵션**: 🟡 Draft / 🔄 In Progress / ✅ Done

**Done 처리 규칙**:

- ✅ Done 조건: DoD 모두 [x] + `skipped=0` + `failed=0`
- ⚠️ **스킵이 1개라도 존재하면 Done 처리 금지 + DoD 테스트 항목 체크 금지**
- 상세: `/impl-plan` 스킬의 "3) 스킵 및 완료 규칙" 참고
- 위 조건은 `~/.claude/hooks/plan_lint.py`가 저장 시 자동 검사합니다

---

**작성일**: 2026-09-12 07:48
**마지막 업데이트**: 2026-09-12 07:48
**관련 범위**: 하네스 (`.claude/skills/claude-config-import/`), 테스트
**관련 문서**: `.claude/skills/claude-config-import/SKILL.md`, `tests/CLAUDE.md`, 루트 `CLAUDE.md`

---

## 0) 고정 규칙 (이 plan은 반드시 아래 규칙을 따른다)

> 🚫 **이 영역은 삭제/수정 금지** 🚫
> 이 섹션(0)은 지워지면 안 될 뿐만 아니라 **문구가 수정되면 안 됩니다.**
> 규칙의 상세 정의/예외는 반드시 `/impl-plan` 스킬을 따릅니다.

- 품질 검증 명령은 **마지막 Phase에서만 실행**한다. 실패하면 즉시 수정 후 재검증한다.
- Phase 0은 "레드(의도적 실패 테스트)" 허용, Phase 1부터는 **그린 유지**를 원칙으로 한다.
- 이미 생성된 plan은 **체크리스트 업데이트 외 수정 금지**한다.
- 스킵은 가능하면 **Phase 분해로 제거**한다.

---

## 1) 목표(Goal)

- [x] 목표 1: `hook_key` 가 **matcher 까지 같은 그룹이 여럿일 때도** 충돌하지 않게 고친다
- [x] 목표 2: 그 충돌이 만든 두 결함을 없앤다 — ① `--apply` 가 영구히 중단되는 것 ② 한 훅의 결정이 다른 훅에 조용히 덮어씌워지는 것
- [x] 목표 3: 사용자가 승인한 결정대로 mac 번들을 이 PC 에 적용하고, 적용으로 사라지는 이 PC 고유 설정을 되살린다

## 2) 비목표(Non-Goals)

- **`claude-config-export` 스킬은 건드리지 않는다.** 결함은 받는 쪽 판정에 있다
- **번들(`claude-config/`)의 내용을 손으로 고치지 않는다.** 번들은 내보내기가 통째로 만드는 산출물이다
- **훅 자동 판정을 도입하지 않는다.** 훅의 이식성은 사람이 판단한다는 기존 설계를 유지한다
- **결정 파일의 지난 결정을 재검토하지 않는다.** 이번에 다시 묻게 된 항목만 정한다
- **보내는 PC(mac)의 원본 파일은 고치지 않는다.** 여기서 닿을 수 없으므로 「고쳐야 한다」는 사실만 문서로 남긴다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

`/claude-config-import` 를 실행하니 `--apply` 단계에서 영구히 막혔다. 원인은 [plan_apply.py:260-275](../../.claude/skills/claude-config-import/plan_apply.py#L260-L275) 의 `hook_key` 다.

- `hook_key` 는 `event` + `matcher` + `index` 로 키를 만든다. docstring 은 「matcher 를 넣어야 키가 충돌하지 않는다」고 적고 있으나, **matcher 가 같은 그룹이 한 이벤트에 여럿 달리면 여전히 충돌한다**
- 이번 mac 번들이 실제로 그 구조다 — `SessionStart` 의 두 그룹이 모두 `*` 이고, `PreToolUse` 의 두 그룹이 모두 `Write|Edit|NotebookEdit|Bash` 다
- `save_decisions` 의 `items` 는 키로 만든 dict 라 **한 키에 해시가 하나만** 담긴다. 겹친 쌍은 나중 것이 앞 것을 덮으므로, 앞 것은 해시가 영영 맞지 않아 `needs_confirmation` 이 풀리지 않는다
- `main()` 은 pending 이 하나라도 있으면 중단한다 → **무엇을 저장하든 2건이 남아 적용이 불가능하다**

실측(읽기 전용 시뮬레이션, 2026-09-12):

```
키가 겹치는 항목 2쌍
  settings.json#hooks.SessionStart[*][0]                          ×2
  settings.json#hooks.PreToolUse[Write|Edit|NotebookEdit|Bash][0] ×2
결정을 저장한 뒤 재판정 -> pending 2건 남음 -> --apply 중단됨
```

두 번째 결함은 더 조용하다. `_decision_map` 이 키로 만든 dict 라 **겹친 쌍의 나중 것이 앞 것의 결정을 덮는다.** 그래서 `rebuild_settings` 는 두 훅에 같은 결정을 적용한다 — 이번 번들에서는 `block-harness-memory-write` 를 「제외」로 정해도 무시되고 적용된다. 이번에는 두 쌍 모두 같은 결정을 원해 결과가 우연히 맞지만, **결정이 갈리는 순간 사용자가 승인한 적 없는 상태가 조용히 만들어진다.**

부수로 확인한 것 하나 더 — 번들의 `block-harness-memory-write.py` 는 `~/Workspace`(대문자 W)로 슬러그를 만드는데 이 PC 는 `~/workspace`(소문자)다. 스크립트가 `~` 에서 런타임에 조립하므로 `path_map` 이 잡지 못한다. 실측으로 실제 슬러그는 `-home-yblee-workspace-verify-lab` 인데 훅은 `-home-yblee-Workspace-verify-lab` 을 만들어 비교하므로 **항상 불일치**다. 즉 등록해도 이 PC 에서는 발동하지 않는다. [docs/INDEX.md](../INDEX.md) 48행은 이 차단이 이미 걸려 있다고 적고 있으나 실제로는 걸려 있지 않다.

### 사용자에게 받은 결정 (2026-09-12)

| 항목 | 결정 |
| --- | --- |
| `SessionStart` acme-docs 부트스트랩 2건 | **제외** |
| `UserPromptSubmit` 의 `prompt_router.py` (acme-docs) | **제외** (지난 결정 `transform` 을 뒤집는다) |
| `block-harness-memory-write.py` | **적용 + 스크립트의 대소문자 문제도 고친다** |
| `report_lint.py` | **제외** (사내프로젝트 관용) |
| `csv-bom-for-excel.py` | **적용** |

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절과 「예외 — `claude-config/` 와 두 하네스 스킬」 절
- `.claude/skills/claude-config-import/SKILL.md` — 절차의 SoT
- `tests/CLAUDE.md` — Given-When-Then, 파일 격리, 경계 조건
- 전역 `~/.claude/rules/python.md` — 타입 힌트, 네이밍, 예외 구분

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] `hook_key` 충돌이 사라졌다 — matcher 가 같은 그룹이 여럿이어도 키가 서로 다르다
- [x] 겹쳤던 두 쌍이 **서로 다른 결정을 가질 수 있음**이 테스트로 고정됐다
- [x] 회귀/신규 테스트 추가 (`tests/test_claude_config_import.py`) — 5개(유일성·결정 독립성·기존 키 형식·경계·접미사 충돌)
- [x] 번들이 이 PC 에 적용됐고, 사용자 결정 7건이 그대로 반영됐다
- [x] 적용으로 사라진 이 PC 고유 설정(`wsl_toast.py` 등록 3건)이 되살아났다
- [x] `~/.claude/hooks/block-harness-memory-write.py` 가 이 PC 에서 실제로 발동한다
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] `poetry run python validate_project.py` 통과 (failed=0, skipped=0; passed/failed/skipped 수 기록)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — `docs/COMMANDS.md` 변경 없음 / `SKILL.md` 실측 기록 갱신 / `docs/MEMORY.md` 갱신
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 근거·실측 수치를 루트 `CLAUDE.md` 의 프로젝트 설정 절이 정한 목적지로 이관.
      `/impl-plan` 스킬 "근거 승격" 참고)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `.claude/skills/claude-config-import/plan_apply.py` — `hook_key` 충돌 해소
- `tests/test_claude_config_import.py` — 충돌·결정 독립성 테스트 추가
- `.claude/skills/claude-config-import/SKILL.md` — 실측 기록 갱신 (근거 승격)
- `docs/MEMORY.md` — 함정 2건 기록 (근거 승격)
- `claude-config/decisions/DESKTOP-4CN5LK3-linux.json` — 결정 갱신 (스크립트가 쓰고 일부는 손으로 고침)
- 저장소 밖: `~/.claude/settings.json`, `~/.claude.json`, `~/.claude/**` (적용 산출물)
- `docs/COMMANDS.md`: **변경 없음** — 실행 명령어와 CLI 옵션이 바뀌지 않는다

### 데이터/결과 영향

- **측정·검증 산출물에 영향 없음.** `storage/` 를 건드리지 않는다
- **키 형식이 바뀌면 결정 파일의 일부 항목이 다시 물어진다.** 첫 그룹은 기존 키를 그대로 유지하는 설계라 churn 을 최소로 하되, 겹쳤던 쌍의 두 번째 항목은 새 키가 되어 재승인 대상이 된다. 재승인 값은 위 「사용자에게 받은 결정」이 정한다

## 6) 단계별 계획(Phases)

### Phase 0 — 충돌 불변조건을 테스트로 먼저 고정(레드)

> 이 Phase 를 두는 이유: 「키가 항목을 유일하게 가리킨다」는 **판정의 인바리언트**다.
> 깨지면 사용자가 승인하지 않은 설정이 조용히 만들어지므로, 구현보다 먼저 고정한다.

**작업 내용**:

- [x] `tests/test_claude_config_import.py` 에 테스트 추가 — matcher 가 같은 그룹이 둘인 `settings` 에서 `classify_settings` 가 만드는 키가 **서로 다르다**
- [x] 같은 입력에서 두 훅에 **서로 다른 결정**(하나는 apply, 하나는 exclude)을 주면 `rebuild_settings` 가 그대로 반영하는지 고정한다 (지금은 나중 것이 앞 것을 덮어 둘 다 살아남는다)
- [x] 기존 키 형식이 유지되는지 고정한다 — matcher 가 겹치지 않는 그룹의 키는 **바뀌지 않아야** 지난 결정이 계속 맞는다
- [x] 경계: 훅이 0개인 그룹, 그룹이 1개뿐인 이벤트에서 예외가 나지 않는다
- [x] 이 시점에서 새 테스트가 **실패**하는 것을 확인한다 (레드) — 2 failed / 10 passed.
      `SessionStart[*][0]` 가 1개 키로 뭉쳤고, 「제외」로 정한 훅이 살아남았다

---

### Phase 1 — 충돌 해소 구현(그린 유지)

**작업 내용**:

- [x] 그룹마다 충돌하지 않는 matcher 라벨을 만드는 헬퍼(`matcher_labels`)를 추가한다 — 같은 matcher 의 **두 번째부터** 순번 접미사를 붙여 첫 그룹의 키를 보존한다
- [x] `classify_settings` 와 `rebuild_settings` 가 **그 헬퍼 하나를 공유**하게 한다. 두 곳이 각자 라벨을 계산하면 판정과 적용이 갈라진다 (판정식 단일화)
- [x] `hook_key` 의 docstring 을 실제 계약에 맞게 고친다 — 무엇이 키를 유일하게 만드는지. 파라미터도 `matcher` -> `matcher_label` 로 바꿔 날 matcher 를 넣으면 안 됨을 시그니처가 말하게 했다
- [x] Phase 0 의 테스트가 통과하는지 확인한다 (그린) — 12 passed
- [x] `--apply` 없이 판정만 다시 돌려 pending 이 **예상대로 6건**인지 확인한다 — `SessionStart` 2건 · `block-harness-memory-write` · `block-emoji-in-code`(새 키가 되어 다시 물어진다) · `report_lint` · `csv-bom-for-excel`.
      키가 `[*#2][0]` · `[Write|Edit|NotebookEdit|Bash#2][0]` 로 갈린 것을 출력으로 확인했다
- [x] `UserPromptSubmit` 은 **pending 이 아니다** — 지난 결정 `transform` 이 해시까지 맞아 자동 적용된다. 사용자 결정이 「제외」이므로 Phase 2 에서 손으로 뒤집는다

---

### Phase 2 — 번들 적용과 이 PC 고유 설정 복구

> **이 Phase 는 저장소 밖(`~/.claude`)을 바꾼다.** 되돌릴 수 있게 백업부터 확인한다.

**작업 내용**:

- [x] 적용 «전에» 되살릴 것을 떠둔다 — 이 PC 의 `wsl_toast.py` 등록 3건(`Notification[*]`·`Stop[*]`·`PreToolUse[AskUserQuestion]`)을 파일로 저장한다
- [x] `--save-decisions` 로 결정을 저장한다
- [x] 결정 파일에서 사용자 결정 7건을 반영한다 (`SessionStart` 2건 제외 · `UserPromptSubmit` 제외 · `block-harness-memory-write` 적용 · `block-emoji-in-code` 적용 · `report_lint` 제외 · `csv-bom-for-excel` 적용)
- [x] `--apply` 로 적용한다. 백업 경로가 출력되는지 확인한다 — `settings.json.bak-20260912-080022` · `.claude.json.bak-20260912-080022`, 파일 35개 적용
- [x] **대조** — 백업과 새 `settings.json` 을 비교해 사라진 최상위 키와 훅을 센다. 스킬 5단계의 대조 스크립트를 쓴다.
      사라진 키 **없음**, 권한 146/68/26/4 **전부 보존**, 사라진 훅 5건(의도한 제외 2 + 되살릴 `wsl_toast` 3)
- [x] 떠둔 `wsl_toast.py` 등록 3건을 되살린다
- [x] 대조를 다시 돌려 사라진 것이 **의도한 제외 2건**(`SessionStart`·`UserPromptSubmit`)만 남는지 확인한다
- [x] 적용된 훅 목록이 사용자 결정과 일치하는지 기계로 확인한다 — 9개 등록 전부 일치
- [x] `~/.claude/hooks/block-harness-memory-write.py` 의 워크스페이스 경로 해석을 고친다 — `Workspace`·`workspace` 중 **실재하는 쪽**을 쓰게 한다
- [x] 고친 훅이 실제로 발동하는지 확인한다 — 5개 사례(쓰기 2·통과 3) 전부 기대와 일치.
      **전후 대조**: 같은 입력에 번들 원본은 `pass`(무동작), 고친 것은 `deny`
- [x] 스킬 6단계 확인 — MCP 실행 파일·자격증명·venv. **할 일 없음**: `context7`(http·키 유지) · `google-sheets`(`uvx` 실재, 자격증명 2개 실재) · venv 3개 실재 · 훅 스크립트 7개 실재
- [x] 스킬 7단계 — 번들 본체를 지우고 `decisions/` 만 남긴다

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [x] `.claude/skills/claude-config-import/SKILL.md` 실측 기록에 이번 회차를 추가한다 — 충돌의 정체와 **왜 matcher 만으로는 부족한가**, 훅 스크립트의 대소문자 함정, mac 원본도 고쳐야 한다는 사실.
      「결정이 쌓여도 내용이 바뀌면 다시 묻는다」 절에 **재사용 조건이 «키 + 해시» 둘 다**임을 표로 추가했다
- [x] `docs/MEMORY.md` 에 **이 저장소 작업에 영향이 남는 것만** 적는다 (함정 자체의 SoT 는 SKILL.md — 두 벌이 되지 않게 한다)
- [x] `docs/COMMANDS.md` — **변경 없음** (실행 명령어·CLI 옵션 불변)
- [x] 자동 포맷 적용 (`poetry run black .`) — 158개 변경 없음
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

> 순서를 지킨다 — 리뷰에서 고치면 코드가 바뀌므로 품질 검증이 마지막 관문이어야 한다.
> (이 두 줄짜리 Validation 은 **적용 과정에서 갱신된 전역 `impl-plan` 템플릿**의 형식이다.
> 계획서를 쓸 때는 없던 단계이며, 번들 적용이 작업 절차까지 옮긴 실물 사례다.)

- [x] `/code-review xhigh` (발견 **11건** · 조치: **내 변경이 만든 5건 수정 · 기존 결함 6건은 보고만**)
- [x] `poetry run python validate_project.py` (passed=**1196**, failed=**0**, skipped=**0**)

**리뷰에서 고친 5건** (전부 이번 변경이 만든 것)

| 무엇 | 고친 내용 |
| --- | --- |
| `matcher_labels` 가 「겹치지 않는다」를 **보장하지 못했다** | matcher 가 `*#2` 라는 문자열이면 붙인 순번과 부딪힌다. 이미 쓴 라벨이면 더 밀어내게 고치고 경계 테스트를 추가했다 |
| 테스트 모듈 docstring 이 **사실과 달랐다** | 「파일을 읽지도 쓰지도 않는다」고 적었으나 `classify_settings` 는 PATH 를 뒤지고 폴더 실재를 본다. 실제 성질과 그래서 무엇을 하지 않는지로 고쳤다 |
| 유일성 검사가 **한 이벤트 안으로만** 좁았다 | 그 설정의 **모든 판정**에 대해 키가 유일한지 보게 넓혔다 |
| 새로 넣은 `# pyright: ignore` 가 **무동작**이었다 | 이 파일은 `pyrightconfig.json` 의 `include` 밖이다. 내가 추가한 것만 뺐다 (기존 것은 범위 밖이라 두었다) |
| `docs/MEMORY.md` 가 `SKILL.md` 와 **두 벌**이 됐다 | 같은 문단이 「SKILL.md 가 SoT」라고 적고는 그 내용을 옮겨 적고 있었다. 중복 항목을 뺐다 |

**보고만 하고 고치지 않은 6건** (전부 이번 변경 이전부터 있던 것)

| 무엇 | 왜 두었나 |
| --- | --- |
| `settings.json` 을 **병합이 아니라 통째로 덮어씀** | `rebuild_settings` 의 근본 설계다. `SKILL.md` 5단계가 이미 이 사실과 수동 복구 절차를 명시한다 |
| 판정을 못 찾으면 **조용히 건너뜀** (`verdict is None`) | 「제외」와 「버그」가 구분되지 않는다. 기존 5곳의 공통 패턴이라 범위 밖 |
| **키 유일성 불변조건이 없다** | 이번에 고친 충돌이 `permissions`·`projects` 에서 재발할 수 있다. **다만 중복이 실제로 있으면 import 전체가 막히므로 결정이 필요하다** |
| 백업이 **2개 파일뿐** | 이번에 덮어쓴 35개 파일은 백업되지 않는다. 손으로 고친 훅도 이 범위다 |
| 승인 전 `--save-decisions` 가 **기본 EXCLUDE 를 「승인됨」으로 굳힌다** | 절차를 지키면 안 걸린다(이번에도 승인 후 저장했다). 스크립트가 막아주지는 않는다 |
| `load_decisions` 를 실행당 **2번** 읽음 | 사소한 비효율 |

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 하네스 / import 판정의 훅 키 충돌을 없애고 mac 번들을 적용한다
2. 하네스 / matcher 가 같은 훅 그룹이 서로의 결정을 덮던 버그 수정 + 회귀 테스트
3. 하네스 / 훅 키를 그룹까지 구분해 --apply 가 영구 중단되던 것을 고친다
4. 하네스 / 번들 적용 절차의 결정 독립성을 테스트로 고정하고 설정을 이관한다
5. 하네스 / 훅 키 충돌 수정과 이 PC 고유 알림 훅 복구

## 7) 리스크(Risks)

| 리스크 | 완화 |
| --- | --- |
| 키 형식을 바꾸면 지난 결정이 전부 무효가 되어 11건을 다시 물어야 한다 | **첫 그룹은 기존 키를 그대로 둔다.** 두 번째부터만 접미사를 붙여 재승인 대상을 겹쳤던 쌍으로 한정한다 |
| `settings.json` 이 통째로 재작성돼 이 PC 고유 설정이 조용히 사라진다 | 적용 «전에» 떠두고, 적용 후 대조 스크립트로 **기계로** 확인한다. 사전 조사에서 최상위 키 손실은 없고 훅 3건만 대상임을 확인했다 |
| `~/.claude/hooks/` 의 스크립트 수정이 다음 번들 적용 때 되돌아간다 | 되돌아간다는 사실 자체를 SKILL.md 에 적고, **mac 원본도 고쳐야 영구적**임을 남긴다 |
| 번들 삭제(7단계) 후 되돌릴 수 없다 | 번들은 mac 에서 다시 내보내면 된다. `decisions/` 는 남기므로 승인 이력은 보존된다 |
| `block-harness-memory-write` 적용으로 이 저장소에서 하네스 메모리 쓰기가 막힌다 | **의도한 동작이다.** [docs/INDEX.md](../INDEX.md) 48행이 이미 그 상태를 전제하고 있고, 대체 목적지(`docs/MEMORY.md`)를 훅이 직접 알려준다 |

## 8) 메모(Notes)

### 설계 결정과 탈락안

| 안 | 판정 | 근거 |
| --- | --- | --- |
| **같은 matcher 의 두 번째 그룹부터 순번 접미사** | **채택** | 첫 그룹의 키가 그대로라 **지난 결정 대부분이 계속 맞는다.** 재승인 대상이 겹쳤던 쌍으로 한정된다 |
| 항상 그룹 번호를 키에 넣는다 (`[matcher@0][0]`) | 탈락 | 형식이 일관되지만 **기존 훅 키가 전부 바뀌어** 11건을 다시 물어야 한다. 얻는 것에 비해 사용자 부담이 크다 |
| 명령문 해시를 키로 쓴다 (`[matcher]#<sha8>`) | 탈락 | 그룹 순서가 바뀌어도 결정이 따라가는 장점이 있으나, **키와 값에 해시가 두 벌**이 되고 역시 기존 키가 전부 바뀐다. 순서가 바뀌면 해시 불일치로 어차피 다시 묻히므로 실익이 작다 |

> **그룹 순서가 바뀌면 어떻게 되나**: 겹친 쌍의 순서가 mac 에서 뒤집히면 두 키의 «가리키는 대상»이 서로 바뀐다.
> 그때는 저장된 해시가 맞지 않아 **둘 다 다시 물어진다** — 조용히 잘못 적용되지 않는다. 이것이 순번 접미사를 택한 두 번째 이유다.

### 그 밖

- 사전 조사에서 **스킬 6단계에 할 일이 없음**을 확인했다 — `db/venv`·`tools/xlsx/venv`·`tools/pptx/venv` 셋 다 실재하고, 구글시트 키 2개도 있다. 매니페스트의 `excluded_venvs` 와 대조한 결과다
- 지난 결정 15건은 그대로 재사용된다 (macOS 알림 훅 3건 · 회사 전용 훅 2건 · 없는 저장소 `projects` 9건 · `/private/tmp` 1건)
- 권한 규칙은 변환 후 현재 상태와 개수가 같다 (allow 146 · deny 68 · ask 26). `additionalDirectories` 만 번들 5 대 이 PC 4 이며 차이는 제외한 `/private/tmp` 다
- **`context7` 의 API 키는 이 PC 값이 유지된다** — 번들에는 센티널로 와 있고 복원 로직이 기존 값을 지킨다

### 진행 로그 (KST)

- 2026-09-12 07:48: 계획서 작성. 사전 조사와 읽기 전용 시뮬레이션으로 충돌이 하드 블로커임을 확인
