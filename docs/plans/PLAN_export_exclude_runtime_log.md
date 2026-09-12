# Implementation Plan: 내보내기 번들에서 런타임 로그를 뺀다

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

**작성일**: 2026-09-12 09:12
**마지막 업데이트**: 2026-09-12 09:31
**관련 범위**: 하네스 (`.claude/skills/claude-config-export/`), 테스트, 저장소 루트 문서 1건
**관련 문서**: `.claude/skills/claude-config-export/SKILL.md`, `tests/CLAUDE.md`, 루트 `CLAUDE.md`

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

- [x] 목표 1: `claude-config-export` 가 **런타임 로그를 번들에 담지 않게** 한다
- [x] 목표 2: 그 판정을 테스트로 고정해, 앞으로 어느 허용 폴더에 로그가 생겨도 조용히 딸려오지 않게 한다
- [x] 목표 3: 이번 회차(WSL → mac, 이 방향의 첫 내보내기)에서 드러난 **받는 쪽이 잃는 것**을 스킬에 남긴다

## 2) 비목표(Non-Goals)

- **`claude-config-import` 스킬은 건드리지 않는다.** 결함은 보내는 쪽 허용목록에 있다
- **허용목록(`ALLOW_TOP_LEVEL_DIRS`)을 좁히지 않는다.** `hooks/` 는 계속 통째로 담는다 — 좁히면 새 훅이 조용히 빠진다
- **`~/.claude/hooks/toast.log` 원본을 지우지 않는다.** 이 PC 의 알림 이력이고 `wsl_toast.py` 가 계속 쓴다
- **mac 의 설정을 대신 고치지 않는다.** 여기서 닿을 수 없으므로 받는 쪽이 할 일을 문서로 남긴다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

`/claude-config-export` 를 이 PC(WSL)에서 처음 돌렸더니 **`hooks/toast.log` 가 번들에 담겼다**(13,405 bytes). `wsl_toast.py` 가 알림을 띄울 때마다 append 하는 런타임 로그이고, 실행 중에도 자라고 있었다(마지막 줄 `2026-09-12 09:07:44`).

판정이 이렇게 갈린 이유:

- 허용목록이 `hooks/` 를 **폴더째** 담는다 ([export.py:59](../../.claude/skills/claude-config-export/export.py#L59))
- 금지 확장자는 `.jsonl` 하나뿐이다 ([export.py:91](../../.claude/skills/claude-config-export/export.py#L91))

즉 `.log` 를 막는 규칙이 아예 없었다. 성격은 스킬이 이미 명시적으로 제외하는 `db/*.jsonl`(「감사 로그 — 그 PC 에서만 뜻이 있다」)과 **같은 계열**인데, 확장자가 달라서 통과했다.

걸리는 곳이 둘이다.

| 무엇 | 왜 문제인가 |
| --- | --- |
| 받는 PC 에 **남의 PC 세션 로그**가 깔린다 | 그 PC 에서 뜻이 없다. 이 저장소는 PUBLIC 이라 git 이력에도 남는다 |
| **`git diff` 검토가 무력해진다** | SKILL.md 「실행 후」 1단계가 「`git diff` 로 무엇이 바뀌었는지 본다」인데, 설정이 한 글자도 안 바뀌어도 이 파일이 매번 달라진다 |

두 번째가 더 무겁다. **매번 달라지는 파일이 섞이면 「이번에 실제로 바뀐 설정」을 눈으로 가릴 수 없고**, 그 검토 단계가 형식만 남는다.

### 이번 회차에서 함께 드러난 것 (문서로 남길 대상)

이 방향(WSL → mac)의 내보내기는 처음이다. `settings.json` 은 받는 쪽에서 **병합이 아니라 통째로 덮어쓰기**이므로(`~/.claude.json` 만 [plan_apply.py:958](../../.claude/skills/claude-config-import/plan_apply.py#L958) 의 `merge_claude_json` 으로 병합된다), **보내는 쪽이 제외했던 항목은 받는 쪽에서 사라진다.**

이 번들의 훅 등록은 9건뿐이고, mac 에만 있는 등록이 9건이다 — [claude-config/decisions/DESKTOP-4CN5LK3-linux.json](../../claude-config/decisions/DESKTOP-4CN5LK3-linux.json) 기준으로 `SessionStart` ×2 · `UserPromptSubmit` ×1 · `PostToolUse[Edit|Write]`(report_lint) ×1 · `PreToolUse[Bash]` ×2(acme 전용) · terminal-notifier ×3 이다. 반대로 이 번들은 mac 이 쓸 수 없는 `wsl_toast.py` 등록 3건을 들고 간다.

**스크립트 파일은 안전하다** — 제외된 훅의 `.py` 는 이 PC 디스크에 남아 있어 번들에 그대로 실렸고, `prompt_router.py` 와 acme 부트스트랩은 애초에 `~/.claude` 밖이라 건드려지지 않는다. **없어지는 것은 `settings.json` 의 등록뿐**이다.

지난 회차에 이 PC 가 `wsl_toast.py` 3건에 했던 복구의 거울상이며, **절차는 이미 SKILL.md 5단계에 있다.** 다만 「보내는 쪽이 제외한 것이 받는 쪽에서 사라진다」는 **방향이 바뀌면 규모가 커진다**는 사실이 보내는 쪽 문서에 없다.

### 부수 — `PROMPT_mac_hook_fix.md` 는 무효가 됐다

이 PC 의 `~/.claude/hooks/block-harness-memory-write.py` 에 `_resolve_workspace()` 가 이미 들어 있고 **번들에 그대로 실렸다.** 그래서 그 문서의 §1(mac 에서 손으로 고치기)과 §4(고친 뒤 다시 내보내기)는 할 일이 없어졌다. 문서 스스로 「끝나면 이 문서는 지웁니다」라고 적고 있고, 남길 근거는 `.claude/skills/claude-config-import/SKILL.md` 의 「실측 기록 — 두 번째 회차」에 이미 있다. 저장소 안 참조처는 **0건**으로 확인했다.

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절과 「예외 — `claude-config/` 와 두 하네스 스킬」 절
- `.claude/skills/claude-config-export/SKILL.md` — 절차의 SoT
- `tests/CLAUDE.md` — Given-When-Then, 파일 격리, 경계 조건
- 전역 `~/.claude/rules/python.md` — 타입 힌트, 네이밍, 예외 구분

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] `hooks/toast.log` 가 번들 판정에서 걸러진다
- [x] 그 판정이 **허용 폴더 어디에 있는 로그든** 걸러냄이 테스트로 고정됐다
- [x] 회귀/신규 테스트 추가 (`tests/test_claude_config_bundle.py`)
- [x] 번들을 다시 만들어 `claude-config/home/hooks/toast.log` 가 **없음**을 확인했다
- [x] `MANIFEST.json` 의 해시 목록에도 그 항목이 없다
- [x] 스킬의 「무엇을 담지 않는가」에 로그 제외가 **이유와 함께** 적혔다
- [x] 스킬의 「주의」에 **받는 쪽이 잃는 것**(제외 항목이 `settings.json` 덮어쓰기로 사라진다)이 적혔다
- [x] `PROMPT_mac_hook_fix.md` 삭제 — 참조처 0건 확인 후
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] `poetry run python validate_project.py` 통과 (failed=0, skipped=0; passed/failed/skipped 수 기록)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — `docs/COMMANDS.md` 변경 없음 / `SKILL.md` 갱신
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (제외 판정의 근거와 방향 비대칭을 `SKILL.md` 로 이관.
      `/impl-plan` 스킬 "근거 승격" 참고)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `.claude/skills/claude-config-export/export.py` — `DENY_SUFFIXES` 에 `.log` 추가, 주석과 `EXCLUSION_NOTICE` 갱신
- `.claude/skills/claude-config-export/SKILL.md` — 제외 목록과 「주의」 갱신 (근거 승격)
- `tests/test_claude_config_bundle.py` — `EXCLUDED_PATHS` 에 로그 사례 추가
- `claude-config/**` — 번들 재생성 산출물 (스크립트가 통째로 다시 만든다)
- `PROMPT_mac_hook_fix.md` — **삭제**
- `docs/COMMANDS.md`: **변경 없음** — 실행 명령어와 CLI 옵션이 바뀌지 않는다

### 데이터/결과 영향

- **측정·검증 산출물에 영향 없음.** `storage/` 를 건드리지 않는다
- **`~/.claude` 를 건드리지 않는다.** 이번 변경은 내보내기 «판정» 만 바꾼다. 원본 로그는 그대로 둔다
- **받는 쪽 결정에 영향 없음.** 로그는 파일 판정 단계에서 빠지므로 `decisions/` 에 항목이 생긴 적이 없다

## 6) 단계별 계획(Phases)

### Phase 0 — 제외 판정을 테스트로 먼저 고정(레드)

> 이 Phase 를 두는 이유: 허용목록이 폴더째 담는 구조라 **로그는 앞으로도 계속 생긴다.**
> 「로그는 담지 않는다」가 판정의 계약이므로 구현보다 먼저 고정한다.

**작업 내용**:

- [x] `EXCLUDED_PATHS` 에 `hooks/toast.log` 를 사유와 함께 추가한다
- [x] 경계: **다른 허용 폴더의 로그도** 걸러지는지 함께 고정한다 (`db/` · `tools/` 각 1건) — 확장자 규칙이지 `hooks/` 특례가 아님을 테스트가 말하게 한다
- [x] 경계: `.log` 가 **이름 일부일 뿐인 파일**은 계속 담기는지 고정한다 (`hooks/changelog.md` 처럼) — 접미사 판정이 이름 매칭으로 번지지 않게 한다
- [x] 이 시점에서 새 테스트가 **실패**하는 것을 확인한다 (레드)

---

### Phase 1 — 제외 구현(그린 유지)

**작업 내용**:

- [x] `DENY_SUFFIXES` 에 `.log` 를 더하고, 위 주석이 **무엇을 막는지**를 말하게 고친다
- [x] `EXCLUSION_NOTICE` 의 감사 로그 줄을 **로그 전반**으로 넓힌다 — 받는 쪽 README 와 매니페스트가 「왜 없지」에 답하는 자리다
- [x] Phase 0 의 테스트가 통과하는지 확인한다 (그린)

---

### 마지막 Phase — 번들 재생성, 문서 정리 및 최종 검증

**작업 내용**

- [x] `--dry-run` 으로 담길 항목이 **37개**이고 `toast.log` 가 빠졌는지 확인한다
- [x] 번들을 다시 만든다
- [x] `claude-config/home/hooks/toast.log` 부재와 `MANIFEST.json` 해시 목록 부재를 **기계로** 확인한다
- [x] `.claude/skills/claude-config-export/SKILL.md` 의 「무엇을 담지 않는가」에 로그 제외를 **근거와 함께** 적는다 — 「그 PC 에서만 뜻이 있다」에 더해 **`git diff` 검토를 무력화한다**는 두 번째 이유를 남긴다
- [x] 같은 문서 「주의」에 **방향 비대칭**을 적는다 — 보내는 쪽이 제외한 항목은 받는 쪽 `settings.json` 덮어쓰기로 사라지며, **방향이 바뀌면 그 규모가 달라진다**
- [x] `PROMPT_mac_hook_fix.md` 를 지운다 (참조처 0건은 확인 완료)
- [x] `docs/COMMANDS.md` — **변경 없음** (실행 명령어·CLI 옵션 불변)
- [x] 자동 포맷 적용 (`poetry run black .`)
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

> 순서를 지킨다 — 리뷰에서 고치면 코드가 바뀌므로 품질 검증이 마지막 관문이어야 한다.

- [x] `/code-review xhigh` (발견 **10건** · 조치: **내 변경이 낡게 만든 1건 수정 · 기존 결함 7건은 보고만 · 내 변경이 아닌 2건 보고**)
- [x] `poetry run python validate_project.py` (passed=**1200**, failed=**0**, skipped=**0**)

**리뷰에서 고친 1건** (이번 변경이 직접 낡게 만든 것)

| 무엇 | 고친 내용 |
| --- | --- |
| 받는 쪽 `SKILL.md` 의 미러 표가 **거짓이 됐다** | 내보내기 규칙을 `**/*.jsonl` + `**/*.log` 로 넓혔는데, 받는 PC 가 실제로 읽는 「빠지는 것」 표는 `db/*.jsonl` 로 남아 있었다. 그 표를 갱신하고 **판정의 SoT 가 내보내기의 `DENY_SUFFIXES` 임**을 적어 두 벌이 되지 않게 했다 |

**보고만 하고 고치지 않은 것** — 근거와 함께

| 무엇 | 왜 두었나 |
| --- | --- |
| 🔴 **자격증명이 «다중 확장자»를 통과한다** | `Path('db/acme-prd.env.local').suffix` 가 `.local` 이라 `CREDENTIAL_SUFFIXES` 가 안 걸린다. 실행으로 확인 — `db/acme-prd.env.local` · `tools/x/.env.local` · `db/credentials.json` 이 전부 **담긴다**. **지금 그런 파일은 없다**(실재하는 것은 의도적으로 담는 `db/acme-prd.env.example` 하나)라 유출은 없었으나, **이 저장소가 PUBLIC 이라 한 번 담기면 이력에서 못 지운다.** 이번 변경이 만든 결함이 아니고, **순진하게 「이름에 `.env` 가 들어가면 차단」으로 막으면 `.example` 템플릿까지 죽어** 설계 판단이 필요하다. 별도 계획서 대상 |
| 로테이트·대문자 로그가 샌다 (`toast.log.1` · `toast.LOG` · `hooks/logs/`) | 실행으로 확인했으나 **현재 그런 파일을 만드는 도구가 없다** — `wsl_toast.py` 는 고정 경로에 append 만 하고 크기 상한도 로테이션도 없다(`LOG_PATH` 한 줄). YAGNI 로 두고, 실제로 로테이트하는 도구가 생기면 그때 넓힌다 |
| 금지목록이 아니라 **확장자 허용목록**이어야 한다는 지적 | 모듈 docstring 의 철학(허용목록)과는 그쪽이 맞다. 다만 `hooks/`·`tools/`·`db/` 아래의 정상 확장자를 전부 열거해야 하고 **빠뜨리면 설정이 조용히 안 넘어간다** — 로그가 새는 것보다 무거운 실패다. 계획서 탈락안 표에 없던 안이라 사용자 판단이 필요하다 |
| 매니페스트 해시를 **복사 전에** 계산한다 | 내보내는 도중 원본이 바뀌면 해시와 바이트가 어긋난다. 이번 변경 이전부터 있던 구조이고, 어긋나면 `test_real_bundle_matches_manifest` 가 잡는다 |
| `~/.claude` 를 **두 번** 순회하고 첫 순회의 개수를 출력한다 | 같은 이유로 범위 밖. 낭비이자 표시 불일치 가능성이지만 기존 구조다 |
| `tests/CLAUDE.md` §5 가 「실경로 읽기 금지, 예외는 한 곳뿐」이라고 적었는데 이 테스트 파일이 이미 3곳에서 읽는다 | 문서와 실제가 어긋난다. 이번 변경이 만든 것이 아니며 규칙 문서 개정이 필요해 별건 |

**이 diff 에 섞인 «내 변경이 아닌» 2건** — 세션 시작 시 git 은 clean 이었다

| 파일 | 무엇이 바뀌었나 |
| --- | --- |
| `.claude/skills/clean-results/SKILL.md` | `disable-model-invocation: true` 가 **지워졌다.** 산출물 폴더를 지우는 스킬이 모델 호출 가능해진다 |
| `src/verify_lab/CLAUDE.md` | 「계층 간 계약」에 계층 판정 행이 **추가됐다** (내용 자체는 코드와 일치) |

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 하네스 / 내보내기 번들에서 런타임 로그를 빼고 판정을 테스트로 고정한다
2. 하네스 / toast.log 가 번들에 딸려오던 것을 막고 WSL 번들을 다시 만든다
3. 하네스 / 로그 확장자를 제외 규칙에 넣어 git diff 검토를 되살린다
4. 하네스 / 내보내기 제외 규칙에 .log 추가 + 방향 비대칭을 스킬에 남긴다
5. 하네스 / 번들에서 런타임 로그 제외, 무효가 된 mac 의뢰서 삭제

## 7) 리스크(Risks)

| 리스크 | 완화 |
| --- | --- |
| `.log` 로 끝나는 **설정 파일**이 언젠가 생겨 조용히 빠진다 | 현재 `~/.claude` 안의 `.log` 는 `hooks/toast.log` 하나뿐임을 확인했다. 로그를 설정으로 쓰는 관용은 없다. 생기면 `EXCLUSION_NOTICE` 가 받는 쪽에 「왜 없는지」를 알린다 |
| 번들 재생성이 다른 항목까지 바꾼다 | 스크립트가 `home/` 을 통째로 다시 만드는 것은 설계다. 재생성 후 **항목 수(38 → 37)와 `MANIFEST.json` 해시**로 대조해 `toast.log` 만 빠졌는지 확인한다 |
| `PROMPT_mac_hook_fix.md` 삭제로 mac 쪽 확인 절차가 사라진다 | §3 의 훅 발동 확인은 받는 쪽 절차이며 `claude-config-import/SKILL.md` 가 소유한다. 삭제 전 참조처 0건을 확인했다 |
| 방향 비대칭을 스킬에 적어도 mac 에서 안 읽는다 | 「주의」 절은 내보내기 실행 전에 읽는 자리다. 다만 **집행 장치는 아니며**, 실제 보호는 받는 쪽 5단계 대조 스크립트가 한다 |

## 8) 메모(Notes)

### 설계 결정과 탈락안

| 안 | 판정 | 근거 |
| --- | --- | --- |
| **`DENY_SUFFIXES` 에 `.log` 추가** | **채택** | 기존 `.jsonl` 과 **같은 층의 같은 성격**이라 규칙이 하나로 읽힌다. 허용 폴더가 늘어도 자동으로 덮는다 |
| `DENY_NAMES` 에 `toast.log` 추가 | 탈락 | 이 파일 하나만 막는다. **다음 도구가 만드는 로그는 또 샌다** — 허용목록이 폴더째 담는 구조라 반복이 예정돼 있다 |
| `hooks/` 를 파일 단위 허용목록으로 좁힌다 | 탈락 | 새 훅을 만들 때마다 목록을 고쳐야 하고, **빠뜨리면 훅이 조용히 안 넘어간다.** 스킬이 허용목록을 폴더 단위로 둔 이유(새 폴더가 딸려오는 것만 막는다)와도 어긋난다 |
| `hooks/toast.log` 원본을 지운다 | 탈락 | 이 PC 의 알림 이력이고 `wsl_toast.py` 가 계속 쓴다. **번들 판정의 문제를 원본 삭제로 덮지 않는다** |

### 그 밖

- 이번 내보내기에서 `context7` API 키는 센티널로 정상 치환됐다 (`__CLAUDE_CONFIG_REDACTED__`)
- 매니페스트 출처는 `DESKTOP-4CN5LK3 / linux` 로 찍혔고, `excluded_venvs` 3건(`db` · `tools/pptx` · `tools/xlsx`)이 패키지까지 기록됐다
- `~/.claude.json` 의 `projects` 는 이 PC 에 1개뿐이지만 받는 쪽이 **병합**하므로 mac 의 9개는 보존된다

### 진행 로그 (KST)

- 2026-09-12 09:12: 계획서 작성. 내보내기 1회차 산출물에서 `toast.log` 혼입을 확인
