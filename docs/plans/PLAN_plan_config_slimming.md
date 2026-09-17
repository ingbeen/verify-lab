# Implementation Plan: plan-config 를 세 키로 줄이고 저장소별 계획서 서술의 중복을 걷어낸다

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

**작성일**: 2026-09-17 09:48
**마지막 업데이트**: 2026-09-17 10:24
**관련 범위**: 전역 하네스(`~/.claude/`), 저장소 7곳의 `.claude/plan-config.json` 과 루트 `CLAUDE.md`
**관련 문서**: 전역 `~/.claude/CLAUDE.md`, `~/.claude/skills/impl-plan/SKILL.md`, 루트 `CLAUDE.md`, `.claude/rules/docs.md`, `ghg-docs/_문서규율.md`

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

- [x] 목표 1: **`plan-config.json` 의 키를 셋으로 고정한다** — `quality_check` · `auto_format` · `evidence_home`. `commit_scopes` · `scope_extras` · `evidence_promotion` 을 없앤다
- [x] 목표 2: **키 정의를 전역 한 곳에만 둔다.** 스킬·템플릿·훅 안내 문구가 같은 키 집합을 말한다
- [x] 목표 3: **저장소 7곳의 루트 `CLAUDE.md` 에서 계획서 «절차» 복제를 걷어내고 «고유 판단 근거»만 남긴다**
- [x] 목표 4: **없애는 값이 담고 있던 정보를 잃지 않는다** — 19행 중 18행은 살아있는 문서에 있음을 대조했고, `commit_scopes` 는 **두지 않기로 확정**했다

## 2) 비목표(Non-Goals)

- **훅의 판정 로직을 바꾸지 않는다.** `plan_lint.py` 가 읽는 키는 `quality_check` 하나뿐이라 스키마 축소가 판정에 닿지 않는다. 고치는 것은 **사람·모델에게 보이는 안내 문구와 docstring** 뿐이다
- **`~/.claude/commands/commit.md` 를 고치지 않는다.** 4번 규칙의 *"현재 프로젝트의 CLAUDE.md 에 기능명 컨벤션이 있으면 그것을 따른다"* 는 팀 저장소에서 여전히 유효하고, `commit_scopes` 를 없애면 그 분기가 자연스럽게 비활성된다
- **`.claude/rules/docs.md` 의 승격 목적지 표를 지우지 않는다.** 오히려 그것이 verify-lab 의 세부 SoT 로 남는다 — `evidence_home` 은 폴더만 말한다
- **`ghg-docs/_문서규율.md` 를 고치지 않는다.** 기행기소의 「신규 문서를 어디에 만드나」는 그 문서가 SoT 이며, 이 계획서는 「근거 승격을 어디로 하나」만 다룬다
- **계획서 폴더 규약(`docs/plans/` vs `.claude/plan/`)을 바꾸지 않는다**
- **7개 저장소에 새 테스트를 만들지 않는다.** 6곳에는 그런 검사 장치가 없어 한 곳만 두면 관용에서 벗어난다
- **`research-lab/docs/PROMPT_next_phase.md` 를 고치지 않는다.** 98·193행이 낡은 포인터를 담고 있지만, 그 문서는 **같은 저장소 `CLAUDE.md:390` 의 「진행 상태 문서와 인계 문서를 두지 않습니다」와 이미 모순**이다. 포인터만 고치면 그 모순이 그대로 굳으므로 **문서의 존치 여부를 먼저 정해야 한다** — 이 계획서의 범위 밖이며 발견 사항으로 보고한다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

**① 다섯 키 중 훅이 읽는 것은 하나뿐이고, 나머지 넷은 소비자가 불확실하다.**
`plan_lint.py:633` 의 docstring 이 이미 그렇게 적고 있다 — *"훅이 실제로 읽는 키는 `quality_check`
하나이고 나머지는 모델이 읽습니다."*

| 키 | 훅 | 실제 소비 경로 |
| --- | --- | --- |
| `quality_check` | **읽음** (`plan_gate` 존재 검사 · `plan_lint` 값으로 정규식 생성) | 기계 강제 |
| `auto_format` | 안 읽음 | 모델 |
| `scope_extras` | 안 읽음 | 모델 — **2/7 저장소에만 존재** |
| `evidence_promotion` | 안 읽음 | 모델 — 7/7 존재, 내용 전부 다름 |
| `commit_scopes` | 안 읽음 | **끊김.** `commands/commit.md` 4번이 `CLAUDE.md` 를 보는데 2026-09-16 이관으로 그 값이 거기서 빠졌다 |

**② `evidence_promotion` 은 7곳 전부가 두 벌이다 (실측).**

| 저장소 | config 의 목적지 | 같은 말이 이미 있는 곳 |
| --- | --- | --- |
| quant | `docs/research/` | `CLAUDE.md:73,80` |
| quant-notify | `docs/DESIGN.md` · `docs/research/` | `CLAUDE.md:16` |
| research-lab | `docs/DESIGN.md` · `src/research_lab/CLAUDE.md` | `CLAUDE.md:385,387` |
| verify-lab | 설계.md · 결과.md · 계층 계약 · COMMANDS.md | `.claude/rules/docs.md:122-128` (5행 표, **더 상세**) |
| ghg-apps · ghg-docs · ghg-reward-repay | `../ghg-docs/...` | `ghg-docs/_문서규율.md` 「문서 배치 규칙」 |

`docs/COMMANDS.md` 는 7곳 중 5곳이 루트 `CLAUDE.md` 에서 *"모든 실행 명령어의 단일 관리"* 라고
이미 선언한다. **config 가 그것을 또 적고 있었다.**

**③ 두 벌이 실제로 갈렸다.** ghg-apps 의 `"도메인 사실": "../ghg-docs/<주제폴더>/ 문서 + _축적지식.md
한 줄"` 에는 조건이 없어 **문서함에 바로 쓰라고 읽힌다.** `_문서규율.md` 는
*"🔴 `../ghg-docs` 는 «사용자가 요청할 때만» 건드린다"* 이고, ghg-reward-repay 에는
`— 사용자 요청 시에만 반영` 이 붙어 있다. **같은 그룹 안에서 조건이 갈렸다.**

**④ 값이 파일 이름째 박혀 낡는다.** ghg-reward-repay 는
`JGG0701_JGG0705_JGG0713_리워드정산_지급파이프라인_리포트.md` 를 목적지로 적어 두었다.
주제가 달라지거나 파일명이 바뀌면 그대로 거짓이 된다.

**⑤ 키 목록이 CLAUDE.md 7곳에 복제돼 있어 키를 하나 고칠 때마다 7곳을 고쳐야 한다.**
게다가 이미 갈려 있다 — quant·quant-notify 는 *"…커밋 기능명 · Scope 추가 항목"*,
verify-lab·research-lab 은 *"…커밋 기능명"*, ghg-docs·ghg-reward-repay 는 *"…근거 승격 목적지"*
까지만 적고, **ghg-apps 는 계획서 규약 절 자체가 없다.**

**⑥ 저장소 CLAUDE.md 의 계획서 절이 전역과 중복이다.** 전역 `~/.claude/CLAUDE.md` 「계획서 선행」이
원칙·예외·폴더·스킬 SoT·config SoT 를 전부 담고 **항상 로드된다.** 전역은 결론까지 적어 두었다 —
*"루트 `CLAUDE.md` 의 「계획서 규약」 절에는 값이 아니라 **그 저장소 고유의 판단 근거**가 있다."*
설계 의도는 이미 「고유 근거만」인데 실제로는 절차 복제가 남아 있다.

**⑦ 전역 스킬·템플릿이 한 파일 안에서 갈린 곳을 가리킨다.**

| 파일 | 줄 | 가리키는 곳 | 실제 |
| --- | --- | --- | --- |
| `SKILL.md` | 18–24 표 | plan-config | 맞음 |
| `SKILL.md` | 84 · 156 · 190 | *"루트 `CLAUDE.md` 의 프로젝트 설정 절"* | **거기에 값이 없다** |
| `template.md` | 64 · 159 | plan-config | 맞음 |
| `template.md` | 80 · 144 | *"루트 `CLAUDE.md` 의 프로젝트 설정 절"* | **거기에 값이 없다** |

**⑧ `auto_format: null` 인 저장소에서 템플릿이 모순을 만든다.** `template.md:77` 의
`- [ ] 자동 포맷 적용 완료` 와 `:144` 의 포맷 줄은 **명령이 없는 저장소에서도 체크를 요구한다.**
ghg-apps · ghg-reward-repay 가 그 상태다.

### 사용자 확정 결정 (2026-09-17)

| # | 결정 |
| --- | --- |
| 1 | **`commit_scopes` 제거.** 커밋 후보는 `/commit` 에 맡긴다 |
| 2 | **`scope_extras` 제거** |
| 3 | **`evidence_promotion` → `evidence_home` 문자열 하나.** 폴더 수준 가이드만 준다 |
| 4 | **`evidence_home` 은 「근거 승격의 최종 목적지」만 뜻한다.** 「신규 문서를 어디에 만드나」는 담지 않는다 — 기행기소는 `_문서규율.md` 가 이미 그 SoT 이며 「저장소 루트 untracked → 요청 시 문서함」이 유지된다. 그래서 기행기소 값이 `../ghg-docs/` 여도 모순이 아니다 |
| 5 | **`docs_shared` 키를 두지 않는다** |
| 6 | **상대경로를 쓴다.** 절대경로는 quant·research-lab 의 config 가 git 추적 중이라 다른 PC 에서 깨진다 |
| 7 | 계획서는 **verify-lab 에 하나만** 둔다. 다른 저장소 편집 시 게이트 프롬프트를 승인한다 |

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 전역 `~/.claude/CLAUDE.md` — 특히 「계획서 선행」·「수술적 변경」·「문서와 주석은 리팩토링을 견디게 쓴다」·「문서 참조 방향」
- `~/.claude/skills/impl-plan/SKILL.md` 와 같은 폴더의 `template.md`
- 루트 `CLAUDE.md` — 「계획서 규약 — 이 프로젝트의 설정」·「계획서의 수명」
- `.claude/rules/docs.md` — 「계획서」 절 (승격 목적지 표)
- `ghg-docs/_문서규율.md` — 「문서 배치 규칙」·「문서 작성·갱신 규칙」
- 각 대상 저장소의 루트 `CLAUDE.md`

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 기능 요구사항 충족 — 저장소 7곳의 `plan-config.json` 키가 **정확히 셋**(`quality_check`·`auto_format`·`evidence_home`)이고, JSON 이 전부 파싱된다
- [x] 전역 5파일(`CLAUDE.md`·`SKILL.md`·`template.md`·`plan_gate.py`·`plan_lint.py`)에 옛 키 이름이 **0건**이다
- [x] 없애는 값이 담던 정보가 살아있는 문서에 있음을 **건건이 대조**했다 (Phase 2 의 대조표 19행).
      **단 `commit_scopes` 는 예외다** — 매핑을 어디에도 두지 않기로 확정했고, 그 근거를 Notes 에 남겼다
- [x] 회귀/신규 테스트 추가 — **해당 없음** (비목표: 7곳에 새 검사 장치를 만들지 않는다)
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — `docs/COMMANDS.md` **변경 없음** · 저장소 7곳 `CLAUDE.md` **변경 있음** · `quant/docs/CLAUDE.md` **변경 있음** · 전역 하네스 5파일 **변경 있음**
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (`evidence_home` 의 뜻과 오해 방지는 `SKILL.md` 와 저장소 4곳 `CLAUDE.md` 에, 기능명 매핑을
      두지 않는 근거는 저장소 3곳 `CLAUDE.md` 에 각각 자립한 문장으로 들어갔다)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

**전역 하네스 (`~/.claude/`)**

- `CLAUDE.md` — 137행의 키 목록 *"(검증 명령·근거 승격 목적지·커밋 기능명)"*. **항상 로드되는 파일이라 여기가 틀리면 영향이 가장 크다**
- `skills/impl-plan/SKILL.md` — 키 표(18–24행) 교체, 낡은 포인터 3곳(84·156·190) 수정
- `skills/impl-plan/template.md` — 키 목록(64행), 낡은 포인터 2곳(80·144) 수정, `auto_format: null` 일 때의 처리 명시(77·144)
- `hooks/plan_gate.py` — `config_notice("missing")` 의 키 목록 문구(69행)
- `hooks/plan_lint.py` — `plan_config()` docstring 의 키 목록(633–634행)

**저장소 7곳 — `.claude/plan-config.json`**

- quant · quant-notify · research-lab · verify-lab · ghg-apps · ghg-docs · ghg-reward-repay

**저장소 7곳 — 루트 `CLAUDE.md`** (절 범위는 실측으로 확정)

| 저장소 | 손댈 줄 | 처리 |
| --- | --- | --- |
| quant | 38–76 | 계획서 절차 삭제, 고유 근거 2줄만 남김 (README 동반 갱신 · 설계 문서 부재) |
| quant-notify | 94–119 | 같음, 고유 근거 1줄 (알림 문구 ↔ `DESIGN.md §4`) |
| research-lab | 342–379 | 같음, 고유 근거 1줄 (`docs/spec/` 을 두지 않는 이유) |
| verify-lab | 326–369 | 같음, 고유 근거 **없음** → 절 축소 |
| ghg-docs | 64–72 | 키 목록 문장 제거 |
| ghg-reward-repay | 217–226 | 키 목록 문장 제거, 고유 근거 1줄 유지 (`null` = 「검증 수단」 3종 대체) |
| ghg-apps | (절 없음) | **신설** — 다른 6곳과 같은 형태로 |

**하위 폴더 `CLAUDE.md`** — 전수 조사 결과 계획서 키를 언급하는 곳은 하나뿐이다

- `quant/docs/CLAUDE.md:45` — 키 목록을 적고 **게다가 「루트 `CLAUDE.md` 의 계획서 규약 절이 SoT」라는 낡은 포인터**다. 그 표는 2026-09-16 이관으로 이미 없다

- `docs/COMMANDS.md`: **변경 없음** — 실행 명령어·CLI 옵션이 바뀌지 않는다

### 데이터/결과 영향

- **산출물·측정 결과에 영향이 없다.** `src/`·`scripts/` 를 건드리지 않으므로 `storage/results/` 가 바뀌지 않는다
- **훅의 판정이 바뀌지 않는다.** `quality_check` 값과 그 존재 여부를 그대로 두므로 Validation 줄 매칭 정규식이 동일하다
- 계획서를 쓰는 **다음 세션부터** 새 키 이름이 적용된다

## 6) 단계별 계획(Phases)

### Phase 1 — 전역 SoT: 키 정의를 한 곳으로

> 키의 «뜻»이 여기에 있으므로 먼저 고친다. 값(Phase 2)보다 앞서야 새 이름의 근거가 생긴다.

**작업 내용**:

- [x] `SKILL.md` 18–24 의 키 표를 셋으로 교체했다. `evidence_home` 항목에 **두 가지를 명시**했다
  - **경로는 그 저장소 루트 기준**으로 해석한다 (셸 cwd 기준이 아니다 — 한 세션에서 cwd 가 여러 번 바뀐다)
  - **폴더만 말한다.** 어느 문서의 어느 절인지는 그 저장소의 문서 규칙이 SoT 다
  - 기행기소의 `../ghg-docs/` 가 「새 문서를 만드는 곳」이 아님을 함께 적었다 — `_문서규율.md` 를 가리킨다
- [x] `SKILL.md` 84 · 156 · 190 의 *"루트 `CLAUDE.md` 의 프로젝트 설정 절"* 을 `.claude/plan-config.json` 으로 고쳤다
- [x] `SKILL.md` 190 의 기능명 매핑 문장을 **`/commit` 에 맡긴다**로 바꿨다 (`commit_scopes` 소멸)
- [x] `template.md` 64 의 키 목록을 고치고, 80 · 144 의 같은 포인터를 고쳤다
- [x] `template.md` 77 · 144 에 **`auto_format` 이 `null` 이면 그 줄을 지운다**를 명시했다
- [x] **전역 `~/.claude/CLAUDE.md:137`** 의 키 목록을 고쳤다 — 항상 로드되는 파일이라 우선순위가 가장 높다
- [x] `plan_gate.py:69` 의 키 목록 문구를 새 셋으로 고쳤다
- [x] `plan_lint.py:633–634` docstring 의 키 목록을 새 셋으로 고쳤다

**Validation**:

- [x] 옛 이름이 **0건** — 영문 키와 **한글 표현을 함께** 훑었다:
      `grep -rn "commit_scopes\|scope_extras\|evidence_promotion\|커밋 기능명\|Scope 추가 항목" ~/.claude` → **0건**.
      🔴 **영문 키만으로 훑으면 놓친다** — 자체 검증에서 전역 `CLAUDE.md:137` 과 `template.md:64` 가 그렇게 빠졌다
- [x] 훅 2개를 직접 실행했다 — `plan_gate.py` 가 실제 입력에 `ask` 를 정상 반환(종료코드 0)하고, `config_notice` 네 상태가 모두 새 문구를 낸다. `quality_check_command` 가 verify-lab 은 명령을, ghg-apps 는 `None` 을 그대로 돌려준다 (**판정이 안 바뀌었다**)

---

### Phase 2 — 값: 7개 config 를 새 스키마로

**작업 내용**:

- [x] **먼저 대조표를 만들었다.** 없애는 값 19건 전부에 목적지와 근거가 있다 — **빈칸 0건이라 선이관이 필요 없었다**

| 저장소 | 없애는 값 | 이미 있는 곳 |
| --- | --- | --- |
| quant | 측정·연구 결과와 판정 · 설계 결정과 탈락안 | `CLAUDE.md:73,80` |
| quant | 실행 명령어 | `CLAUDE.md:129` (+ `template.md` 의 Scope·DoD 가 고정으로 요구) |
| quant | `scope_extras: README.md` | `CLAUDE.md:72` — **Phase 3 에서 보존 대상** |
| quant-notify | 설계 결정과 탈락안 | `CLAUDE.md:16` |
| quant-notify | 측정·실측 결과와 판정 (`docs/research/`) | `docs/DESIGN.md` 가 6곳에서 인용(210·710·871·880·890·930) |
| quant-notify | 실행 명령어 | `CLAUDE.md:122` |
| quant-notify | `scope_extras: DESIGN.md §4` | `CLAUDE.md:116` — **Phase 3 에서 보존 대상** |
| research-lab | 설계 결정·탈락안·실측 기록 | `CLAUDE.md:385` |
| research-lab | 계층 간 계약 | `CLAUDE.md:387` |
| research-lab | 실행 명령어 | `CLAUDE.md:400` |
| verify-lab | 4행 전부 | `.claude/rules/docs.md:122-128` — **절 이름까지 있어 더 상세하다** |
| ghg-docs | 기본(주제 폴더 + `_축적지식.md`) | `_문서규율.md` 주제 폴더 표 · `CLAUDE.md:80` (셋 다 자동 주입) |
| ghg-docs | 훅·라우팅 가이드 | `CLAUDE.md:82` 「관련 문서」 |
| ghg-apps | 도메인 사실(`../ghg-docs/<주제폴더>/`) | `_문서규율.md` 「문서 배치 규칙」 — **자동 주입** |
| ghg-apps | 판정 규율(`_세션시작.md`) | 그 문서 자체가 **자동 주입** |
| ghg-apps | 개발환경(`CLAUDE.md`) | 자명 |
| ghg-reward-repay | 기본(`../ghg-docs/리워드_정산/JGG…`) | `CLAUDE.md:231` 「관련 문서」 표가 **같은 파일을 이름째** 가리킨다 |
| 4곳 | `commit_scopes` 합계 22행 | `/commit` 이 경로와 내용에서 생성 (준수율 실측 13/15) |

- [x] 7개 `plan-config.json` 을 세 키로 교체한다

| 저장소 | `quality_check` | `auto_format` | `evidence_home` |
| --- | --- | --- | --- |
| quant · verify-lab · research-lab · quant-notify | `poetry run python validate_project.py` | `poetry run black .` | `docs/` |
| ghg-docs | `python3 _bootstrap/check_docs.py` | `null` | `.` |
| ghg-apps · ghg-reward-repay | `null` | `null` | `../ghg-docs/` |

- [x] `quality_check` 와 `auto_format` 의 **값을 바꾸지 않았다** — 훅 판정이 흔들리면 안 된다

**Validation**:

- [x] 7개 파일이 전부 `json.load` 로 파싱되고 키 집합이 정확히 셋이다 — 기계 대조 **7/7 PASS**
- [x] 대조표 **19행 전부**에 목적지와 근거가 있다 — 빈칸 0건이라 선이관이 필요 없었다
- [x] `quality_check` 값 7개가 교체 전과 동일하다 (4곳 `poetry run python validate_project.py` · ghg-docs `python3 _bootstrap/check_docs.py` · 2곳 `null`)

---

### Phase 3 — 서술: 7개 CLAUDE.md 에서 절차 복제 제거

**작업 내용**:

- [x] 각 저장소의 계획서 절을 **「절차는 전역 · 값은 config」 한 문단 + 고유 근거**로 줄였다.
      **키 목록을 다시 적지 않았다** — 그것이 7곳을 동시에 고치게 만든 원인이다
- [x] 남길 고유 근거 (그 저장소에만 있는 판단)

| 저장소 | 남기는 것 |
| --- | --- |
| quant | Scope 에 `README.md` 를 함께 적는다 (← `scope_extras` 가 내려옴) · 별도 설계 문서가 없어 `docs/research/` 본문에 쓴다 |
| quant-notify | 알림 문구를 바꾸면 `docs/DESIGN.md §4` 예시도 함께 (← `scope_extras`) |
| research-lab | `docs/spec/` 을 두지 않는 이유 |
| ghg-reward-repay | `quality_check: null` 은 「검증 수단」 3종으로 대체한다는 뜻 |
| verify-lab · ghg-docs · ghg-apps | **실측 결과 셋 다 「없음」이 아니었다** — 아래 참조 |

> **초안의 「고유 근거 없음」은 틀렸다.** 실제로 셋 다 **`evidence_home` 값이 오해받을 여지**를
> 갖고 있어 그 오해를 막는 한 줄이 필요했다. 값을 폴더 하나로 줄인 대가이며, **줄인 만큼
> 「이 폴더가 무슨 뜻인지」를 저장소가 말해야 한다.**
>
> - **verify-lab** — `docs/` 안에서 설계.md·결과.md·계층 계약으로 갈리는 것은 `.claude/rules/docs.md` 가 SoT
> - **ghg-docs** — `.` 이 「루트에 문서를 둔다」로 읽히면 안 된다 (루트는 `INDEX.md`·`_` 기계장치 전용)
> - **ghg-apps** — `../ghg-docs/` 가 「새 문서를 만드는 곳」으로 읽히면 안 된다

- [x] verify-lab: 「계획서의 수명」 절을 지우면서 **그 절을 참조하던 문장**을 다시 썼다.
      승격 대상 SoT 가 `.claude/rules/docs.md` 라는 사실은 유지했다
- [x] ghg-apps: 계획서 규약 절을 **신설**했다 (「이 프로젝트의 검증 수단」과 「환경 설정」 사이)
- [x] verify-lab: 「규칙 문서 구성」 표의 `/impl-plan` 행(297)과 「세션 시작 규칙」의 승격 목적지 문장(354)이 그대로 유효하다
- [x] **`quant/docs/CLAUDE.md:45`** — 키 목록을 지우고 낡은 포인터를 `.claude/plan-config.json` 으로 고쳤다

**Validation**:

- [x] 옛 이름 **0건** — 저장소 7곳 전체(루트·하위 `CLAUDE.md`·`docs/`)를 영문+한글로 훑었다.
      남은 1건은 `research-lab/docs/PROMPT_next_phase.md:98` 이며 **Non-Goals 로 뺀 건**이다
- [x] 7곳 어디에도 「원칙: 모든 코드 변경은 계획서를 작성한 후」 류의 **전역 복제 문장**이 없다
- [x] ghg-docs: `python3 _bootstrap/check_docs.py` → **passed=10, failed=0, skipped=0**
- [x] **지운 절을 참조하는 곳 0건** — 「계획서의 수명」·「계획서(Plan) 작성이 필요한 경우」를 4개 저장소에서 훑었다

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

> 🔴 **`/commit` 이 «맨 마지막»인 것은 의도다.** 그 스킬은 「후보 뒤에는 아무것도 덧붙이지 말 것」으로
> 끝나므로 **호출하는 순간 그 턴이 거기서 닫힌다.** 중간에 두면 뒤에 적힌 항목이 그 벽 너머에 남는다 —
> 실제로 두 번 그렇게 샜다(`[실측] 2026-09-14` 후보를 계획서에 안 옮김 · `2026-09-16` 옮기고 체크박스를 안 닫음).
> **체크박스와 상태를 먼저 확정하고, 커밋 후보를 마지막에 만든다.**

- [x] 필요한 문서 업데이트 — `docs/COMMANDS.md` **변경 없음** (실행 명령어·CLI 옵션이 바뀌지 않았다)
- [x] 자동 포맷 적용 — `poetry run black .` → `154 files left unchanged` (파이썬을 바꾸지 않았으므로 정상)
- [x] 변경 기능 및 전체 플로우 최종 검증 — 7개 config 를 다시 읽어 키 집합과 값을 확인했다
- [x] **커밋 기능명 매핑을 어디에도 두지 않기로 확정**했다 (사용자, 2026-09-17). 시험 삼아 3곳에 넣었던 표를 되돌렸다
- [x] Validation 절에 `/code-review` 와 품질 검증 **실행 결과**를 적는다
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정
- [x] 🔴 **마지막에 `/commit` 을 실행하고 그 후보를 «이 계획서» 의 `#### Commit Messages` 절에 옮긴다** —
      `/commit` 은 계획서를 모르고 「후보 뒤에 아무것도 덧붙이지 말 것」으로 끝나므로,
      **대화에만 내면 그 절이 빈 채로 남는다.** 체크박스 갱신이 diff 에 더 들어가지만
      커밋 메시지의 내용을 바꾸지 않는다. **커밋은 사용자가 한다 — 후보만 낸다**

**Validation**:

> 순서를 지킨다 — 리뷰에서 고치면 코드가 바뀌므로 품질 검증이 마지막 관문이어야 한다.

- [x] `/code-review xhigh` (발견 **14건** · 조치: **범위 안 3건 중 1건 반영 · 1건 「두지 않음」으로 확정 · 1건은 커밋 필요 · 범위 밖 11건은 사용자 지시로 손대지 않음**)
- [x] `poetry run python validate_project.py` (passed=**1243**, failed=**0**, skipped=**0**)
- [x] `python3 _bootstrap/check_docs.py` — ghg-docs (passed=**10**, failed=**0**, skipped=**0**)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다.**
> 계획서를 쓰는 시점에는 diff 가 없어 여기 적는 것은 전부 추측이고,
> **추측으로 적은 줄은 그대로 나간다.** 형식·문체 규칙은 `/commit` 이 정한다.

> **대상 범위**: staged 가 없어 unstaged + untracked 전체를 봤고, **덩어리 둘이 섞여 있어
> A(이번 작업)만으로 후보를 냈다.** B 는 이전 세션의 옵션 만기일 손절선 근거 재작성이다.
> 전역 `~/.claude/` 변경은 이 저장소 밖이라 이 커밋에 들어가지 않는다.

1. `하네스 / 계획서 규약을 config 세 키로 축소하고 CLAUDE.md 절차 복제 제거`
2. `하네스 / plan-config 키 5개에서 3개로 축소와 evidence_home 도입`
3. `하네스 / 전역과 중복되던 계획서 절차 서술 삭제 및 값 SoT 일원화`
4. `하네스 / 소비자 없는 commit_scopes·scope_extras 제거와 근거 승격 목적지 단순화`
5. `하네스 / 계획서 규약 정비 — 키 축소·중복 서술 제거·판단 근거만 존치`

## 7) 리스크(Risks)

| 리스크 | 완화 |
| --- | --- |
| **정보가 조용히 사라진다** — 없애는 값이 유일한 기록인 경우 | Phase 2 를 **대조표부터** 시작한다. 목적지와 줄 번호가 비면 그 Phase 안에서 살아있는 문서에 **먼저** 넣는다. `scope_extras` 2건은 이미 각 저장소 `CLAUDE.md:72`·`:116` 에 있음을 실측했다 |
| **`/commit` 의 기능명 품질이 떨어진다** | 실측상 verify-lab 최근 15개 중 13개가 기존 기능명을 지켰고, 벗어난 것은 계획서 워크플로 밖의 손 커밋(`delete plan`)이었다. 기능명은 경로에서 자연스럽게 나온다 |
| **저장소 6곳에서 게이트 프롬프트가 뜬다** (`.json` 은 문서 제외 대상이 아니다) | 마커가 `세션 + cwd` 로 갈리기 때문이며 **차단이 아니라 확인**이다. 저장소당 1회, 승인하면 그 세션 내내 통과한다. 계획서는 실제로 존재하되 훅이 cwd 밖을 못 볼 뿐이다 |
| **다른 저장소의 품질 검증을 이 계획서의 Validation 으로 쓸 수 없다** | verify-lab 의 `validate_project.py` 는 자기 저장소만 본다. ghg-docs 는 `check_docs.py` 를 Phase 3 에서 따로 돌린다. 나머지 5곳은 `.md`·`.json` 만 바뀌어 코드 검사 대상이 아니다 |
| **`/code-review` 가 verify-lab diff 만 본다** | 다른 6곳의 변경은 리뷰 범위 밖이다. 그 사실을 Validation 줄에 적고, 6곳은 Phase 2·3 의 기계 대조로 대신한다 |
| **`evidence_home: "."` (ghg-docs)이 「저장소 루트에 문서를 둔다」로 읽힌다** | `_문서규율.md` 가 *"`../ghg-docs` 루트에는 문서를 두지 않는다"* 고 이미 못 박고 있다. `SKILL.md` 의 키 설명에 **「폴더만 말한다 · 세부 배치는 그 저장소 문서 규칙이 SoT」**를 적어 이 해석을 막는다 |
| **상대경로가 cwd 기준으로 해석된다** | `SKILL.md` 키 설명에 **「그 저장소 루트 기준」**을 명시한다. 이 세션에서만 cwd 가 세 번 바뀌었다 |
| **quant·research-lab 의 config 는 git 추적 중이라 다른 PC 로 넘어간다** | 그래서 절대경로를 쓰지 않는다 (사용자 결정 6). 상대경로는 mac·WSL 양쪽에서 같게 해석된다 |
| **Phase 1·2 사이에 세션이 끊기면** 스킬은 새 키를 말하는데 config 는 옛 키인 중간 상태가 남는다 | 훅이 읽는 것은 `quality_check` 뿐이라 **판정은 그 상태에서도 정상**이다. 남는 영향은 모델이 `evidence_home` 을 찾다 못 찾는 것뿐이고, 이 계획서가 남아 있어 복구 지점이 드러난다 |

## 8) 메모(Notes)

### 실측 기록 (2026-09-17)

- **분포**: `plan-config.json` 7곳 ↔ 계획서 폴더 보유 저장소 7곳이 **정확히 1:1**. 나머지 7개 저장소(ghg-and·ghg-bats·ghg-ios·kubernetes·ghg-prd-dmz-web1/2·ghg-alimtalk-batch)는 규약 미채택
- **git 추적 상태**: quant·research-lab **추적 중** / verify-lab·quant-notify·ghg-docs·ghg-reward-repay 미추적(커밋 전) / ghg-apps `.gitignore` 대상
- **키 중복**: `quality_check` 는 4/7 이 같은 값, `auto_format` 은 5/7 이 같은 값. 전역 기본값을 두는 안(C)은 **채택하지 않았다** — `SKILL.md:139-142` 가 「값을 저장소 안에 두어 막다른 길을 없앴다」고 명시적으로 선택한 설계이고, 훅이 저장소 밖을 읽으면 실패 모드가 는다
- **커밋 기능명 준수율**: verify-lab 최근 15개 중 13개가 `commit_scopes` 의 기능명 사용. quant·research-lab·quant-notify 도 같은 경향. 벗어난 것은 계획서 밖 손 커밋
- **`/commit` 의 끊긴 경로**: `commands/commit.md` 4번이 `CLAUDE.md` 를 보는데 이관으로 값이 거기서 빠져, 지금은 *"없으면 적절한 한글 기능명을 정한다"* 분기로 떨어진다. 그럼에도 준수율이 높은 이유는 계획서 작업 중 config 가 이미 컨텍스트에 있었기 때문 — **우연에 기댄 구조였다**

### 검토했으나 채택하지 않은 안

| 안 | 왜 버렸나 |
| --- | --- |
| **B. 축소 후 각 저장소 문서로 되돌리기** | 2026-09-16 이관의 부분 철회가 된다. 값이 산문으로 흩어져 스키마가 사라지고, 훅이 깨진 것을 알아챌 방법이 없어진다(JSON 은 깨지면 예외가 난다 — `plan_lint.py:640` 주석) |
| **C. 전역 기본값 + 저장소 오버라이드** | 훅이 저장소 밖 파일을 읽어야 하고, 「이 저장소의 실효값」을 한 파일로 볼 수 없게 된다 |
| **`docs_shared` 키 추가** | 사용자 결정 5. 「신규 문서를 어디에 만드나」는 `_문서규율.md` 가 SoT 이므로 config 가 두 벌로 담을 이유가 없다 |
| **`/commit` 이 plan-config 를 읽게 고치기** | `commit_scopes` 를 없애므로 고칠 대상 자체가 사라진다 |

### 자체 검증에서 찾은 누락 (2026-09-17, 초안 직후)

전역 규칙 「계획서 검증」에 따라 초안을 기계로 훑었더니 **범위 누락 3건 + 범위 밖 발견 1건**이 나왔다.

| # | 놓친 곳 | 왜 놓쳤나 |
| --- | --- | --- |
| 1 | 전역 `~/.claude/CLAUDE.md:137` | 키 목록이 **한글 표현**(*"검증 명령·근거 승격 목적지·커밋 기능명"*)이라 영문 키 grep 에 안 걸렸다 |
| 2 | `template.md:64` | 같은 이유. 80·144 만 세고 64 를 빠뜨렸다 |
| 3 | `quant/docs/CLAUDE.md:45` | **하위 폴더 `CLAUDE.md`** 를 범위에서 빠뜨렸다. 게다가 이 줄은 낡은 포인터까지 함께 갖고 있다 |
| 4 | `research-lab/docs/PROMPT_next_phase.md:98,193` | 범위 밖. 그 저장소 `CLAUDE.md:390` 과 이미 모순인 문서라 **존치 판단이 먼저다** |

**배운 것**: 이 저장소들은 키를 **영문 이름과 한글 설명 두 벌로** 적는다. 한쪽만 훑으면
남은 쪽이 조용히 낡는다. 그래서 Phase 1·3 의 Validation 을 **양쪽을 함께 훑도록** 고쳤다.
하위 폴더 `CLAUDE.md` 19개를 전수 조사했고, 계획서 키를 언급하는 것은 `quant/docs/CLAUDE.md` 하나뿐이었다.

### 커밋 기능명 매핑 — 어디에도 두지 않는다 (2026-09-17 확정)

코드 리뷰가 「`commit_scopes` 22행 → `/commit` 이 경로에서 생성」 판정에 반례를 들었다.
`studies/<매매법>/runner.py`(`검증 / `)와 **같은 폴더의** `trading.py`(`매매 / `)가 갈리고,
`notifier/`→`발송`·`tqqq/`→`TQQQ시뮬레이션` 도 폴더명에서 안 나온다.

매핑을 각 저장소 `CLAUDE.md` 의 「판단 근거」로 옮기는 안을 만들어 **실제로 3곳에 넣어 봤고,
사용자가 되돌렸다.**

**확정: 매핑표를 어디에도 두지 않는다.** `/commit` 이 변경된 경로와 **내용**을 보고 그때그때
정한다. 근거는 **표가 강제가 되는 것 자체가 문제**라는 것이다 — 표를 두면 폴더가 늘 때마다
낡고, 낡은 표를 따르면 **실제 변경과 어긋난 기능명이 나간다.** 리뷰가 지적한 「유도 불가」는
**경로만 볼 때**의 이야기이고, `/commit` 은 `git diff` 의 내용까지 읽는다.

그 대가로 **같은 폴더에서 기능명이 갈리던 구분은 기계로 보장되지 않는다.** 받아들인 비용이다.

### 코드 리뷰 결과 (2026-09-17, `xhigh`)

**발견 14건 중 11건이 이 계획서의 범위 밖이다** — `/code-review` 는 미커밋 diff 전체를 보는데,
이 저장소에는 **이번 작업 이전의 미커밋 변경**(옵션 만기일 `규칙.md`·`결과.md`·`설계.md`·
`constants.py`·`INDEX.md`)이 이미 있었다. 그 11건은 사용자에게 따로 보고한다.

| 범위 | 건 | 처리 |
| --- | --- | --- |
| 안 | 커밋 기능명 매핑 소실 | **반영하지 않기로 확정** — 위 절. 표를 두지 않는 것이 결정이다 |
| 안 | 「복제하지 않습니다」 다음 줄에서 `evidence_home` 값을 복제 | **고쳤다** (verify-lab·ghg-docs·ghg-apps·ghg-reward-repay 4곳에서 값을 빼고 뜻으로 서술) |
| 안 | `.claude/plan-config.json` 이 git untracked | **커밋이 필요하다** — 작업 전부터의 상태이고 커밋은 사용자가 한다 |
| 밖 | 옵션 만기일 문서·코드 11건 | **손대지 않는다** (사용자 지시 2026-09-17). 이번 작업 이전의 미커밋 변경에 대한 지적이다 |

### 진행 로그 (KST)

- 2026-09-17 09:48: 계획서 작성. 사용자 확정 결정 7건과 실측 기록을 반영
- 2026-09-17 09:55: 자체 검증 — 범위 누락 3건을 Scope·Phase 에 반영하고, Validation 의 grep 을 한글 표현까지 훑도록 고쳤다. 범위 밖 발견 1건은 Non-Goals 에 근거와 함께 남겼다
- 2026-09-17 10:12: Phase 1~3 완료. 코드 리뷰 14건 중 범위 안 2건을 반영하고, 1건(기능명 매핑)은 사용자 판단 대기로 남겼다
- 2026-09-17 10:20: 기능명 매핑을 3곳 `CLAUDE.md` 에 넣었다가 **사용자 지시로 되돌렸다** — 표를 두는 것 자체가 강제가 되어 낡은 기능명을 밀어내므로, `/commit` 이 그때그때 정한다. 범위 밖 11건은 손대지 않기로 확정했다. 되돌린 상태로 재검증해 둘 다 통과했다

---
