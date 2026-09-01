# Implementation Plan: 계획서 절차를 전역 스킬 `impl-plan` 으로 통합

> 작성/운영 규칙(SoT): `/verify-plan` 스킬(`.claude/skills/verify-plan/SKILL.md`)을 반드시 참고하세요.  
> (이 템플릿을 수정하거나 새로운 양식의 계획서를 만들 때도 해당 스킬을 포인터로 두고 준수합니다.)

**상태**: 🔄 In Progress

---

🚫 **이 영역은 삭제/수정 금지** 🚫

**상태 옵션**: 🟡 Draft / 🔄 In Progress / ✅ Done

**Done 처리 규칙**:

- ✅ Done 조건: DoD 모두 [x] + `skipped=0` + `failed=0`
- ⚠️ **스킵이 1개라도 존재하면 Done 처리 금지 + DoD 테스트 항목 체크 금지**
- 상세: `/verify-plan` 스킬의 "3) 스킵 및 완료 규칙" 참고
- 위 조건은 `.claude/hooks/plan_lint.py`가 저장 시 자동 검사합니다

---

**작성일**: 2026-08-29 20:06
**마지막 업데이트**: 2026-08-29 20:18
**관련 범위**: 하네스(전역 스킬·훅), 워크스페이스 전체(verify-lab · krx-sprint · quant)
**관련 문서**: `~/.claude/CLAUDE.md`, `CLAUDE.md`, `.claude/rules/docs.md`, `tests/CLAUDE.md`, `docs/INDEX.md`

---

## 0) 고정 규칙 (이 plan은 반드시 아래 규칙을 따른다)

> 🚫 **이 영역은 삭제/수정 금지** 🚫
> 이 섹션(0)은 지워지면 안 될 뿐만 아니라 **문구가 수정되면 안 됩니다.**
> 규칙의 상세 정의/예외는 반드시 `/verify-plan` 스킬을 따릅니다.

- `poetry run python validate_project.py`는 **마지막 Phase에서만 실행**한다. 실패하면 즉시 수정 후 재검증한다.
- Phase 0은 "레드(의도적 실패 테스트)" 허용, Phase 1부터는 **그린 유지**를 원칙으로 한다.
- 이미 생성된 plan은 **체크리스트 업데이트 외 수정 금지**한다.
- 스킵은 가능하면 **Phase 분해로 제거**한다.

---

## 1) 목표(Goal)

- [ ] 목표 1: 계획서 절차의 SoT 를 전역 스킬 `~/.claude/skills/impl-plan/` **한 벌**로 통합한다
- [ ] 목표 2: `plan_gate.py` · `plan_lint.py` 를 `~/.claude/hooks/` 로 올려 워크스페이스 전체에 적용한다 (quant 는 신규 적용)
- [ ] 목표 3: 레포별 복제본을 전부 제거한다 — verify-lab `verify-plan` 스킬·훅, krx-sprint `plan` 스킬·훅, quant `docs/CLAUDE.md` 계획서 절과 `_template.md`
- [ ] 목표 4: 프로젝트마다 달라지는 부분(검증 명령·근거 승격 목적지·커밋 기능명)을 각 repo `CLAUDE.md` 로 분리해 스킬 본문을 범용화한다

## 2) 비목표(Non-Goals)

- **task-flow 도입 제외.** `docs/plans/` 가 없어 전역 훅이 자동 무시하며, Python 이 아닌 backend/frontend 구조라 `validate_project.py`·Black 전제가 맞지 않는다. 나중에 폴더만 만들면 자동 편입된다
- **계획서 절차 자체의 개정 금지.** Phase 구성 원칙·Done 3조건·스킵 설계·근거 승격의 **내용은 그대로 옮긴다.** 이번 작업은 이관이지 규칙 개정이 아니다
- **기존 계획서(`PLAN_*.md`) 본문 수정 금지.** 세 레포에 남아 있는 계획서 6건은 임시 산출물이고, 스킬 규칙상 이미 생성된 plan 은 체크리스트 외 수정 금지다. 그 안의 `/verify-plan`·`/plan` 문자열은 손대지 않는다
- 훅 로직의 기능 변경 금지 — 이번에 바꾸는 것은 `marker_path()` 의 디렉터리명 문자열과 안내 문구의 스킬 이름뿐이다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

**같은 계획서 체계가 세 레포에 복제돼 있고, 이미 갈라지기 시작했다.**

| 레포 | 계획서 SoT | 템플릿 | 훅 |
| --- | --- | --- | --- |
| verify-lab | `.claude/skills/verify-plan/SKILL.md` | 스킬 폴더 `template.md` | plan_gate + plan_lint |
| krx-sprint | `.claude/skills/plan/SKILL.md` | 스킬 폴더 `template.md` | plan_gate + plan_lint |
| quant | `docs/CLAUDE.md` 의 계획서 절 (산문) | `docs/plans/_template.md` | **없음** |

복제본 간 실측 차이:

- `SKILL.md` 두 벌 → 실질 차이 **2군데** (근거 승격 목적지, 커밋 기능명 매핑)
- `plan_gate.py` 두 벌 → **스킬 이름 2줄만** 다름
- `plan_lint.py` 두 벌 → `marker_path()` 의 임시 디렉터리명 **1줄만** 다름
- quant 는 같은 규칙이 스킬이 아니라 **산문으로 중복 기재**돼 있고, 훅이 없어 게이트가 강제되지 않는다

**전역화는 이미 코드가 전제하고 있다.** `plan_lint.py` 의 `project_uses_plans()` docstring 이 명시한다 —
"이 판정 덕분에 훅을 전역(`~/.claude/`)에 두어도 다른 언어의 프로젝트를 방해하지 않습니다."
`docs/plans/` 폴더 존재 여부로 판정하므로 미채택 레포는 자동 통과한다.
전역 `settings.json` 에 `$HOME/.claude/hooks/wsl_toast.py` 를 등록한 선례도 있다.

**이름을 `impl-plan` 으로 정한 근거**: `/plan` 단독은 Claude Code 의 plan 모드·Plan 에이전트와 혼동된다.

### 이 계획서의 위치에 대한 전제

이 작업은 **verify-lab 저장소 밖**(전역 `~/.claude/`, krx-sprint, quant)을 변경한다.
계획서를 verify-lab `docs/plans/` 에 두는 이유는 ① 현재 세션이 verify-lab 이고,
② verify-lab 이 이 체계의 가장 발전된 버전(근거 승격 절)을 갖고 있어 전역 스킬의 원본이 되며,
③ 세 레포 중 변경량이 가장 크기 때문이다. 저장소 밖 경로는 **인라인 코드로만** 표기하고 링크하지 않는다.

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 전역 규칙: `~/.claude/CLAUDE.md`
- 루트 규칙: [CLAUDE.md](../../CLAUDE.md)
- 문서 규칙: [.claude/rules/docs.md](../../.claude/rules/docs.md)
- 파이썬 규칙: [.claude/rules/python.md](../../.claude/rules/python.md)
- 테스트 규칙: [tests/CLAUDE.md](../../tests/CLAUDE.md)
- 스킬·CLAUDE.md 작성 규율: `writing-for-agents` 스킬

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/verify-plan` 스킬)

- [ ] 세 레포 `CLAUDE.md` 에 프로젝트별 계획서 설정 절 신설 완료 (스킬에서 빼기 **전에** 이관)
- [x] 전역 스킬 `~/.claude/skills/impl-plan/` (SKILL.md + template.md) 배치 완료
- [x] 전역 훅 `~/.claude/hooks/plan_gate.py` · `plan_lint.py` 배치 및 전역 `settings.json` 등록 완료
- [ ] 세 레포의 복제본 제거 완료 (스킬 2벌, 훅 2벌, `settings.json` 2개, quant 산문 절, quant `_template.md`)
- [ ] 세 레포 + 전역 CLAUDE.md 의 참조 전수 갱신 완료 (기존 `PLAN_*.md` 6건은 제외)
- [ ] 네 레포에서 훅 동작 실측 완료 (verify-lab · krx-sprint · quant 는 게이트 작동, task-flow 는 무반응)
- [ ] `poetry run python validate_project.py` 통과 (failed=0, skipped=0; passed/failed/skipped 수 기록)
- [ ] `poetry run black .` 실행 완료 (마지막 Phase에서 자동 포맷 적용)
- [ ] 필요한 문서 업데이트(`docs/COMMANDS.md` / CLAUDE.md / plan 등 — 각각 변경 여부 명시)
- [ ] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 근거·실측 수치를 스펙/설계/ROADMAP/COMMANDS로 이관. `/verify-plan` 스킬 "근거 승격" 참고)
- [ ] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

**전역 (`~/.claude/`)** — 신규·수정

- `~/.claude/skills/impl-plan/SKILL.md` (신규 — verify-lab 판을 범용화)
- `~/.claude/skills/impl-plan/template.md` (신규 — 동일)
- `~/.claude/hooks/plan_gate.py` (신규 — 안내 문구의 스킬명만 변경)
- `~/.claude/hooks/plan_lint.py` (신규 — `marker_path()` 디렉터리명만 변경)
- `~/.claude/settings.json` (PreToolUse/PostToolUse 훅 등록 추가)
- `~/.claude/CLAUDE.md` (스킬 표에 `impl-plan` 추가, 「계획서 선행」 절의 저장 위치 문구 갱신)

**verify-lab** — 삭제·수정

- 삭제: `.claude/skills/verify-plan/`, `.claude/hooks/` 전체(plan_gate.py · plan_lint.py · `__pycache__`), `.claude/settings.json`
- 수정: [CLAUDE.md](../../CLAUDE.md) 143·182행 + 프로젝트별 설정 절 신설, [docs/INDEX.md](../INDEX.md) 41행, [.claude/rules/docs.md](../../.claude/rules/docs.md) 71행, [tests/CLAUDE.md](../../tests/CLAUDE.md) 217행, `다음세션_프롬프트.md` 81행

**krx-sprint** — 삭제·수정

- 삭제: `.claude/skills/plan/`, `.claude/hooks/` 전체, `.claude/settings.json`
- 수정: `CLAUDE.md` 60행 + 프로젝트별 설정 절 신설, `.claude/rules/docs.md` 28·32행, `docs/ROADMAP.md` 5행

**quant** — 삭제·수정

- 삭제: `docs/plans/_template.md`, `docs/CLAUDE.md` 의 「포맷/린트/테스트 규칙」·「plans 폴더 사용 규칙」·「계획서 운영 규칙(SoT)」 세 절
- 수정: `CLAUDE.md` 71·73행 + 프로젝트별 설정 절 신설, `README.md` 88행, `docs/CLAUDE.md` 17행(폴더 구조에서 `_template.md` 제거)

**변경하지 않는 것**

- `docs/COMMANDS.md`: **변경 없음** — 실행 명령어·CLI 옵션이 바뀌지 않는다 (세 레포 모두 동일)
- 기존 계획서 `PLAN_*.md` 6건 (verify-lab 3 · krx-sprint 2 · quant 1)
- task-flow 전체
- quant `docs/CLAUDE.md` 의 문서 보관 정책·research 폴더 규칙 등 계획서와 무관한 절

### 데이터/결과 영향

- 측정·검증 로직 무관. 출력 스키마·결과 파일 영향 없음
- **동작 변화 1**: quant 가 처음으로 계획서 선행 게이트를 받는다 (사용자 승인 프롬프트가 뜨기 시작)
- **동작 변화 2**: `marker_path()` 디렉터리명이 바뀌어 **작업 중 세션의 기존 마커가 무효화**된다. 전환 직후 게이트가 한 번 더 뜰 수 있다
- **동작 변화 3**: `.claude/settings.json` 2개가 삭제된다. 두 파일 모두 `.gitignore` 에 없어 **git 추적 대상**이므로 커밋에 삭제로 잡힌다 (git 처리는 사용자가 수행)

## 6) 단계별 계획(Phases)

### Phase 0 — 기준선 확보 (동작 변화 없음)

> 이 작업은 새 로직을 만들지 않고 기존 자산을 옮긴다. 따라서 Phase 0 은 레드 테스트가 아니라
> **"전환 전 상태를 숫자로 고정"** 하는 데 쓴다. 전환 후 같은 수치가 나와야 회귀가 없다고 말할 수 있다.

**작업 내용**:

- [x] 세 레포에서 `poetry run python validate_project.py` 를 실행해 전환 전 `passed/failed/skipped` 를 기록한다
- [x] 훅 두 개에 PreToolUse/PostToolUse JSON 을 직접 먹여 **현재 판정 결과**를 기록한다
      (실제 파일을 편집하지 않고 stdin 으로 검증한다 — 편집 후 되돌리면 작업 트리가 지저분해진다)
- [x] task-flow 에서도 같은 JSON 으로 현재 무반응임을 기록한다 (전환 후 비교 기준)

**Validation**:

- [x] 네 레포의 전환 전 수치·판정이 Notes 진행 로그에 기록됨

> **[중요] 기준선이 이미 실패 상태다.** 세 레포 모두 전환 전부터 `validate_project.py` 가 실패한다.
> 원인은 전부 이번 작업 범위 밖이며, 상세는 Notes 「Phase 0 기준선 실측」에 기록했다.
> 이 때문에 DoD 의 "세 레포 통과" 항목은 **달성 불가능**하다 — 사용자 확인 후 판정 기준을 조정해야 한다.

---

### Phase 1 — 프로젝트별 설정을 각 repo CLAUDE.md 로 먼저 이관

> **순서가 중요하다.** 스킬 본문에서 특화 내용을 빼기 **전에** 각 repo 로 옮긴다.
> 반대로 하면 그 사이 정보가 어디에도 없는 구간이 생긴다.

**작업 내용**:

- [x] verify-lab [CLAUDE.md](../../CLAUDE.md) 에 「계획서 규약 — 프로젝트 설정」 절 신설
  - 검증 명령: `poetry run python validate_project.py` (마지막 Phase만), `poetry run black .` (자동 포맷만)
  - 근거 승격 목적지: `docs/spec/`(데이터 소스 실측·설계 결정·탈락안), `docs/research/`(측정 결과·판정),
    [docs/ROADMAP.md](../ROADMAP.md)(Phase 상태·검증 목록·계층 간 계약), [docs/COMMANDS.md](../COMMANDS.md)(실행 명령어)
  - 커밋 기능명 매핑: `src/verify_lab/data/` → `수집 /`, `measure/`·`report/` → `측정 /`,
    `studies/` → `검증 /`, 문서 → `문서 /`, `.claude/`·설정 → `하네스 /`
- [x] krx-sprint `CLAUDE.md` 에 동일 절 신설 (근거 승격 목적지는 스펙·설계 문서·ROADMAP·COMMANDS)
- [x] quant `CLAUDE.md` 에 동일 절 신설 — **quant 는 `docs/ROADMAP.md` 가 없으므로** 그 항목을 빼고 적는다
- [x] 세 절이 서로 어긋나지 않는지 대조 (같은 항목을 다른 이름으로 부르지 않기)

**Validation**:

- [x] 세 repo CLAUDE.md 에 절이 존재하고, 스킬 본문에서 뺄 예정인 항목이 **빠짐없이** 옮겨졌는지 대조
      — 세 레포 모두 「검증 명령」·「근거 승격 목적지」·「커밋 메시지의 기능명」 세 소절 확인

> **범위 밖 추가 2건 (보고 대상)**
> ① verify-lab 기능명 표에 `strategy/` → `매매 /` 를 넣었다. 스킬 원본에는 없었으나
> 최근 커밋(`매매 / 원달러 그리드를 채택 거부하고...`)이 이미 쓰고 있는 실제 관용이다.
> ② quant 표에 `.claude/`·설정 → `하네스 /` 를 넣었다. 원본에 없었으나 다른 두 레포와 맞췄다.

---

### Phase 2 — 전역 자산 구축 (등록 없이 파일만 배치)

> 이 Phase 는 **동작을 바꾸지 않는다.** 전역 `settings.json` 등록은 Phase 3 에서 한다.
> 파일만 먼저 두면 훅 중복 실행 없이 내용을 검토할 수 있다.

**작업 내용**:

- [x] `~/.claude/skills/impl-plan/SKILL.md` 작성 — verify-lab 판을 원본으로 하되 아래를 범용화
  - `verify-lab의 모든 코드 변경은...` → 프로젝트 중립 문장
  - 근거 승격 목적지 · 커밋 기능명 매핑 · 검증 명령 → **Phase 1 에서 만든 각 repo 설정 절을 가리키는 포인터로 교체**
  - 상대경로 링크 `../../../docs/ROADMAP.md` 제거 (전역에서 해석 불가)
  - frontmatter `name: impl-plan`, `description`·`when_to_use` 를 프로젝트 중립으로
- [x] `~/.claude/skills/impl-plan/template.md` 작성 — `/verify-plan` → `/impl-plan`, `src/verify_lab/...` → 범용 플레이스홀더
- [x] `~/.claude/hooks/plan_lint.py` 배치 — verify-lab 판 복사 후 `marker_path()` 의
      `"verify-lab-plan-gate"` → `"claude-plan-gate"`
      (session_id 가 이미 세션 고유값이라 프로젝트명을 붙일 필요가 없다. 시그니처 변경 없이 문자열 한 줄로 끝난다)
- [x] `~/.claude/hooks/plan_gate.py` 배치 — verify-lab 판 복사 후 안내 문구 2곳의 `/verify-plan` → `/impl-plan`
- [x] `writing-for-agents` 스킬 규율에 따라 두 문서를 자체 검토

**Validation**:

- [x] 전역 훅 두 파일에 Phase 0 과 같은 JSON 을 먹여 판정이 동일한지 확인
      (`plan_gate.py` 가 같은 폴더의 `plan_lint` 를 import 하므로 배치 위치가 맞아야 한다)
      — **4개 레포 × 3종 검사 전부 기준선과 일치**
- [x] 이 시점에 각 레포 동작이 이전과 동일함을 확인 (전역 등록 전이므로 변화 없어야 함)

> **작성 중 발견한 제약 (스킬에 기록함)**: `plan_lint.py` 의 `VALIDATION_LINE` 정규식이
> `validate_project\.py` 문자열을 하드코딩한다. 템플릿 Validation 줄에서 이 이름을 빼면
> 훅이 그 줄을 찾지 못해 **Done 검사가 조용히 건너뛰어진다.** 그래서 템플릿은 이 이름을 그대로 유지했다.

---

### Phase 3 — 원자적 전환 (복제본 제거 + 전역 등록)

> **한 Phase 안에서 닫아야 한다.** 레포 훅을 남긴 채 전역 훅을 켜면 같은 훅이 두 번 실행되고,
> 마커 디렉터리가 달라 게이트가 반복해서 뜬다.

**작업 내용**:

- [x] verify-lab: `.claude/skills/verify-plan/` · `.claude/hooks/` · `.claude/settings.json` 삭제
      (settings.json 은 훅 등록만 담고 있어 훅 절을 빼면 빈 껍데기가 된다 — 파일째 지운다)
- [x] krx-sprint: `.claude/skills/plan/` · `.claude/hooks/` · `.claude/settings.json` 삭제
- [x] quant: `docs/plans/_template.md` 삭제
- [x] `~/.claude/settings.json` 에 PreToolUse(`Edit|Write`) · PostToolUse(`Edit|Write|Bash`) 훅 등록.
      명령 형식은 verify-lab 판(`PY=$(command -v python3 || command -v python)` 폴백)을 채택한다 —
      krx-sprint 판은 `python3` 직접 호출이라 덜 견고하다. 경로는 `$HOME/.claude/hooks/` 를 쓴다
      (`$CLAUDE_PROJECT_DIR` 은 각 프로젝트를 가리키므로 전역에서는 부적합)

**Validation**:

- [x] verify-lab · krx-sprint · quant 에서 Phase 0 과 같은 JSON 으로 게이트가 **작동**하는지 확인
- [x] task-flow 에서 게이트가 **무반응**인지 확인 (`project_uses_plans` 가 막아야 함)
- [x] 전역 `settings.json` 이 유효한 JSON 인지 파싱 확인 (기존 `wsl_toast` 훅 등록을 깨뜨리지 않았는지)
      — PreToolUse 2개(AskUserQuestion→wsl_toast, Edit|Write→plan_gate), PostToolUse 1개, Notification·Stop 각 1개 유지

> **[중요] 현재 세션에는 아직 적용되지 않는다.** 세션 시작 시 로드된 훅 설정이 살아 있어
> 삭제된 `verify-lab/.claude/hooks/plan_lint.py` 를 계속 호출한다(도구 실행 자체는 성공하고 오류 메시지만 붙는다).
> **새 설정은 세션을 다시 시작해야 적용된다.**

---

### Phase 4 — 참조 문서 전수 갱신

**작업 내용**:

- [x] `~/.claude/CLAUDE.md`: 스킬 표에 `impl-plan` 행 추가, 「계획서 선행」 절의 저장 위치 문구를 스킬 참조로 갱신
- [x] verify-lab [CLAUDE.md](../../CLAUDE.md) 143·182행: `/verify-plan` → `/impl-plan`,
      182행의 스킬 파일 링크는 저장소 밖이 되므로 **링크를 없애고 인라인 코드로** 표기
      (하네스 강제 문구의 `.claude/hooks/` → 전역 `~/.claude/hooks/` 도 함께 수정)
- [x] verify-lab [docs/INDEX.md](../INDEX.md) 41행: 스킬 링크 제거.
      `REGISTERED_DIRS = ("docs", "reference")` 이므로 `.claude/skills/` 는 등록 의무 대상이 아니다 —
      행을 지워도 [tests/test_index.py](../../tests/test_index.py) 는 통과한다
- [x] verify-lab [.claude/rules/docs.md](../../.claude/rules/docs.md) 71행, [tests/CLAUDE.md](../../tests/CLAUDE.md) 217행: `/verify-plan` → `/impl-plan`
- [x] verify-lab `다음세션_프롬프트.md` 81행: `/verify-plan` → `/impl-plan`
- [x] krx-sprint `CLAUDE.md` 60행, `.claude/rules/docs.md` 28·32행, `docs/ROADMAP.md` 5행: `/plan` → `/impl-plan`
      (40행 「절차: `.claude/skills/`」 와 96행 하네스 문구도 전역 경로로 수정)
- [x] quant `docs/CLAUDE.md`: 계획서 관련 세 절을 제거하고 `/impl-plan` 포인터로 대체, 17행 폴더 구조에서 `_template.md` 제거
- [x] quant `CLAUDE.md` 71·73행, `README.md` 88행: `docs/CLAUDE.md` 참조 → `/impl-plan` 스킬 참조

**Validation**:

- [x] 세 레포에서 `/verify-plan`·`/plan` 잔존 참조를 grep 으로 전수 확인 (기존 `PLAN_*.md` 6건만 남아야 함)
      — **살아있는 문서 잔존 0건**, 기존 계획서 6건만 남음
- [x] verify-lab `poetry run pytest tests/test_index.py` 통과 — 6 passed

> **quant 고유 규칙 1건을 구제했다.** `docs/CLAUDE.md` 89행에 「Scope 에 `README.md` 와 `docs/COMMANDS.md` 의
> 변경 여부를 **각각** 명시」라는 규칙이 있었고 스킬에는 `docs/COMMANDS.md` 만 있었다.
> 제거 전에 quant `CLAUDE.md` 의 프로젝트 설정 절로 옮겼다 — 다른 두 레포에는 없는 QBT 고유 규칙이다.

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` 변경 없음 — 실행 명령어 불변)
- [x] `poetry run black .` 실행(자동 포맷 적용) — 130 files left unchanged
- [x] 변경 기능 및 전체 플로우 최종 검증
- [ ] DoD 체크리스트 최종 업데이트 및 체크 완료
- [ ] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [x] verify-lab `poetry run python validate_project.py` (passed=1109, failed=0, skipped=0)
      — Ruff·PyRight·Pytest **전부 통과**
- [x] quant `env -u VIRTUAL_ENV poetry run python validate_project.py` (passed=1027, failed=0, skipped=0)
      — Ruff·PyRight·Pytest **전부 통과**
- [ ] krx-sprint `validate_project.py` — `.venv` 부재로 Pytest 실행 불가 (`poetry install` 필요)
- [x] 기준선 대비 악화가 없음을 확인

#### 최종 검증 결과

| 레포 | Ruff | PyRight | Pytest | 판정 |
| --- | --- | --- | --- | --- |
| verify-lab | OK | OK | **1109 passed**, failed=0, skipped=0 | 통과 |
| quant | OK | OK | **1027 passed**, failed=0, skipped=0 | 통과 |
| krx-sprint | OK | OK | 실행 불가 (`.venv` 부재) | 정적 검사만 통과 |

**verify-lab 의 Ruff·PyRight 개선은 이번 작업의 결과가 아니다.** 기준선에서 실패하던
`studies/index_extreme/runner.py` 와 `tests/test_report_tables.py` 의 미사용 import 가
**20:22:38 · 20:22:39 에 수정**됐다(파일 mtime 실측). 두 파일은 이번 작업의 변경 대상이 아니며,
사용자가 진행 중이던 다른 작업(방향 무관 측정)에서 정리한 것으로 보인다.

**krx-sprint 만 Pytest 를 돌릴 수 없다.** 이 PC 에서 `poetry install` 을 한 적이 없어서이며,
설정 문제가 아니다. 이번 작업이 이 레포에서 바꾼 것은 **문서뿐**(파이썬은 훅 삭제만)이고
Ruff·PyRight 가 기준선과 같이 통과하므로 악화 없음이 확인된다.

> **부작용 1건**: 확인 과정에서 `env -u VIRTUAL_ENV poetry run` 을 실행해
> `krx-sprint/.venv` 빈 디렉터리가 생성됐다(22:11). poetry 가 쓸 자리이므로 무해하며,
> `poetry install` 시 그대로 채워진다.

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> 세 레포에 걸친 변경이므로 레포마다 따로 커밋한다. 아래는 verify-lab 기준 후보다.

1. 하네스 / 계획서 스킬을 전역 impl-plan 으로 이관하고 레포 복제본을 제거
2. 하네스 / verify-plan 스킬·훅 제거 — 계획서 절차를 워크스페이스 전역으로 통합
3. 하네스 / 계획서 게이트를 전역 훅으로 옮기고 프로젝트별 설정만 남긴다
4. 하네스 / 세 벌로 갈라진 계획서 규약을 전역 스킬 한 벌로 합친다
5. 하네스 / 계획서 절차 전역화 — 스킬·훅 이관과 참조 문서 갱신

## 7) 리스크(Risks)

- **훅 중복 실행** — 레포 훅과 전역 훅이 동시에 살아있으면 게이트가 두 번 뜨고 마커가 어긋난다.
  → Phase 3 에서 제거와 등록을 한 Phase 안에 묶어 완화
- **마커 무효화** — `marker_path()` 디렉터리명 변경으로 진행 중 세션의 게이트 통과 기록이 사라진다.
  → 전환 직후 게이트가 한 번 더 뜰 수 있음을 사용자에게 사전 고지. 기능 손상은 아님
- **훅이 품질 검사 범위를 벗어난다** — Ruff 는 `extend-exclude = ["reference"]` 만 제외하므로
  현재 `.claude/hooks/*.py` 도 검사받는다. 전역으로 옮기면 **어느 레포의 Ruff·PyRight 도 훅을 검사하지 않는다.**
  → 이번 변경은 문자열 두 곳뿐이라 즉시 위험은 낮다. 다만 앞으로 훅을 고칠 때 자동 검사가 없다는 점을
  각 repo CLAUDE.md 의 설정 절에 명시해 다음 사람이 알게 한다
- **quant 의 작업 흐름 변화** — 지금까지 게이트가 없던 레포에 프롬프트가 생긴다.
  → 사용자가 명시적으로 요청한 변경. Phase 3 Validation 에서 실제 동작을 함께 확인
- **전역 훅이 미래의 무관한 프로젝트를 방해** — `project_uses_plans()` 가 `docs/plans/` 유무로 막는다.
  → Phase 3 Validation 에서 task-flow 로 실측
- **`settings.json` 삭제가 git 에 잡힌다** — 두 레포 모두 `.gitignore` 에 없어 추적 대상이다.
  → 삭제 사실을 사용자에게 명시적으로 보고한다 (git 처리는 사용자 몫)
- **전역 스킬 범용화 과정에서 verify-lab 고유 규칙 유실** — 특히 「근거 승격」 절은 verify-lab 에만 있던 자산이다.
  → Phase 1 에서 각 repo 로 **먼저 옮긴 뒤** Phase 2 에서 스킬을 쓴다. Phase 1 Validation 이 대조를 강제한다

## 8) 메모(Notes)

### 확정된 결정 사항 (2026-08-29, 사용자)

| 항목 | 결정 | 근거 |
| --- | --- | --- |
| 스킬 이름 | `impl-plan` | `/plan` 단독은 Claude Code 의 plan 모드·Plan 에이전트와 혼동 |
| 훅 범위 | 스킬 + 훅 **모두** 전역 | `project_uses_plans()` 가 미채택 레포를 막아줘 안전. quant 도 게이트를 얻는다 |
| quant `docs/CLAUDE.md` | 계획서 절 제거 후 스킬 참조 | 같은 규칙이 산문으로 중복 기재된 상태. 레포별 스킬 제거 방침과 일관 |
| task-flow | 제외 | `docs/plans/` 없음, Python 아님. 나중에 폴더만 만들면 자동 편입 |

### 조사로 확정한 사실 (재조사 불필요)

- 전역 스킬은 6개(`diagnosing-bugs`·`grilling`·`handoff`·`ponytail-audit`·`ponytail-review`·`writing-for-agents`) —
  `verify-plan` 은 전역이 아니었다. **사용자의 최초 전제가 사실과 달랐다**
- `verify-plan` 참조 12개 파일은 전부 verify-lab 내부. 다른 레포는 이 스킬을 참조하지 않았다
- 세 레포 모두 `validate_project.py` 와 `docs/COMMANDS.md` 를 갖는다. `docs/ROADMAP.md` 는 quant 만 없다
- quant `.claude/` 에는 `rules/python.md` 와 `settings.local.json`(permissions 만) 뿐 — 훅 등록이 없다
- 전역 `settings.json` 은 이미 `hooks` 절을 갖고 `$HOME/.claude/hooks/wsl_toast.py` 를 등록해 두었다
- verify-lab·krx-sprint 의 `.claude/settings.json` 은 **훅 등록만** 담는다. `.gitignore` 에 없어 추적 대상이다
- [tests/test_index.py](../../tests/test_index.py) 의 `REGISTERED_DIRS = ("docs", "reference")` —
  `.claude/skills/` 는 INDEX 등록 의무 대상이 아니므로 링크 제거가 테스트를 깨지 않는다

### 자체 검증에서 고친 것 (2026-08-29 20:18)

- **Phase 순서 모순**: 초안은 스킬에서 특화 내용을 뺀 뒤(Phase 1) 각 repo 로 옮기게(Phase 3) 되어 있어
  그 사이 정보가 붕 뜨는 구간이 있었다. Risks 의 "먼저 옮긴 뒤 뺀다"와도 어긋났다 →
  이관을 Phase 1 로 끌어올리고 전역 자산 구축을 Phase 2 로 미뤘다
- **`settings.json` 처리 미결**: "파일 자체 처리 방침을 정한다"는 애매한 문장을 **파일째 삭제**로 확정하고
  git 추적 대상이라는 사실을 Risks·Scope 에 명시했다
- **Phase 0 부실**: "테스트를 추가할지 판단한다"는 미결 문장을 **기준선 측정**이라는 실행 가능한 작업으로 바꿨다
- **검증 방법 미명시**: 게이트 확인을 "파일 편집 시도"에서 **훅에 JSON 직접 투입**으로 바꿨다.
  작업 트리를 더럽히지 않고 Phase 0 기준선과 같은 방식으로 비교할 수 있다
- **누락 리스크 추가**: 훅이 전역으로 가면 Ruff·PyRight 검사 범위를 벗어난다는 사실을 발견해 Risks 에 넣었다
- **quant 절 경계 명확화**: "60~159행 중 계획서 관련 부분"을 세 절의 이름으로 특정했다

### Phase 0 기준선 실측 (2026-08-29 20:2x)

#### `validate_project.py` — 세 레포 모두 전환 **전부터** 실패

| 레포 | Ruff | PyRight | Pytest | 실패 원인 (전부 이번 작업 범위 밖) |
| --- | --- | --- | --- | --- |
| verify-lab | **FAIL 13** | **FAIL 7** | OK (passed=1109, failed=0, skipped=0) | `studies/index_extreme/runner.py` · `tests/test_report_tables.py` 의 미사용 import(`COL_WIN_RATE` 등)와 import 정렬. 진행 중인 다른 작업(방향 무관 측정)의 미완성분 |
| krx-sprint | OK | OK | **FAIL (passed=0)** | `.venv` 부재 — 이 PC 에서 `poetry install` 을 한 적이 없다 |
| quant | OK | ~~FAIL 32~~ → **OK** | ~~FAIL~~ → **OK (passed=1027)** | **측정 오류였음. 아래 정정 참고** |

#### [정정] 기준선 측정이 틀렸다 — `VIRTUAL_ENV` 오염 (2026-08-29 22:1x)

기준선을 `cd <레포> && poetry run ...` 으로 쟀는데, 이 세션의 `VIRTUAL_ENV` 가
`verify-lab/.venv` 를 가리키고 있어 **poetry 가 다른 레포에서도 verify-lab 의 가상환경을 썼다.**
그래서 `ModuleNotFoundError` 가 났다. 전역 `settings.json` 에 `Bash(env -u VIRTUAL_ENV poetry:*)`
권한이 등록돼 있던 것이 이 함정의 흔적이다.

`env -u VIRTUAL_ENV` 를 붙여 다시 재면:

- **quant: Ruff·PyRight·Pytest 전부 통과 (passed=1027, failed=0, skipped=0).** 처음부터 정상이었다
- **krx-sprint: `.venv` 가 실재하지 않는다.** 이쪽은 진짜로 의존성 미설치이며 `poetry install` 이 필요하다

> **다른 레포에서 poetry 를 실행할 때는 `env -u VIRTUAL_ENV` 를 붙인다.**
> 붙이지 않으면 현재 세션의 가상환경이 따라가 **엉뚱한 레포의 패키지를 찾고 실패한다.**
> 이 함정은 측정 결과를 조용히 바꾸므로, 재현하려면 반드시 같은 방식으로 실행해야 한다.

#### 훅 판정 — verify-lab 훅으로 4개 레포 cwd 를 판정 (전역 훅의 예상 동작과 동일)

| 레포 | 코드 파일 편집 | `.md` 편집 | 기존 계획서 lint |
| --- | --- | --- | --- |
| verify-lab | **ask** (게이트 작동) | 무출력 (통과) | 4건 전부 위반 없음 |
| krx-sprint | **ask** (게이트 작동) | 무출력 (통과) | 2건 전부 위반 없음 |
| quant | **ask** (게이트 작동) | 무출력 (통과) | 1건 위반 없음 |
| task-flow | **무출력** | 무출력 (통과) | 계획서 없음 |

**계획의 핵심 전제 두 가지가 실증됐다.**

1. quant 는 `docs/plans/` 를 이미 갖고 있어 전역 훅을 켜면 **곧바로 게이트 대상이 된다** (훅만 없었을 뿐이다)
2. task-flow 는 `project_uses_plans()` 가 정확히 막는다 — 전역 훅이 무관한 프로젝트를 방해하지 않는다

실측 스크립트는 스크래치패드의 `hook_baseline.py` 이며, 전환 후 같은 스크립트를 전역 훅 경로로 재실행해 대조한다.

### 진행 로그 (KST)

- 2026-08-29 20:06: 계획서 작성. 워크스페이스 4개 레포 전수 조사 완료, 사용자 결정 4건 확정
- 2026-08-29 20:18: 자체 검증 후 개정. Phase 순서 모순 해소, 미결 사항 3건 확정, 리스크 1건 추가
- 2026-08-29 20:26: Phase 0 완료. 기준선 실측 결과 **세 레포 모두 이미 실패 상태**임을 확인 —
  DoD 의 "세 레포 통과" 항목이 달성 불가능하므로 사용자 확인 필요. 훅 판정은 계획의 전제 2건을 실증
- 2026-08-29 21:1x: Phase 1~2 완료. 세 repo 에 프로젝트 설정 절 신설 후 전역 스킬·훅 배치.
  전역 훅 판정이 기준선과 4개 레포 전부 일치
- 2026-08-29 21:2x: Phase 3~4 완료. 복제본 삭제 + 전역 등록, 참조 전수 갱신.
  살아있는 문서 잔존 참조 0건, `test_index.py` 6 passed
- 2026-08-29 22:1x: **기준선 측정 오류를 정정.** `VIRTUAL_ENV` 오염으로 quant 를 실패로 잘못 판정했다.
  실제로는 quant 도 전부 통과(1027 passed)했고, 미설치는 krx-sprint 하나뿐이다.
  함정을 전역 `CLAUDE.md` 로 승격 (근거 승격 완료)

---
