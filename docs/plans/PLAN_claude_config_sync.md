# Implementation Plan: 전역 Claude 설정 두 PC 동기화 (백업 / 마이그레이션 스킬)

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

**작성일**: 2026-09-09 18:01
**마지막 업데이트**: 2026-09-09 19:45
**관련 범위**: 하네스 (`.claude/skills/`, 새 최상위 폴더 `claude-config/`, tests)
**관련 문서**: 루트 `CLAUDE.md`, `.claude/rules/docs.md`, `tests/CLAUDE.md`, `docs/INDEX.md`

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

- [x] 목표 1: 회사 mac 의 전역 Claude 설정(`~/.claude/` + `~/.claude.json`)을 **필터링 없이** 이 저장소로 내보내는 스킬을 만든다
- [x] 목표 2: 받는 PC(집 Windows)에서 **경로만 바꾸면 되는 것은 변환해 적용**하고, 정말 적용 불가한 것만 사용자 승인 후 제외하는 스킬을 만든다
- [x] 목표 3: 받는 쪽의 **결정을 누적**해 다음 마이그레이션에서 되묻지 않되, **원본 파일이 바뀌면 다시 묻는다**
- [x] 목표 4: 받는 PC 에서 **스킬만 실행하면** 고정 경로의 번들을 스스로 찾아 마이그레이션이 진행된다

## 2) 비목표(Non-Goals)

- **전역 `~/.claude/CLAUDE.md` 수정 — 하지 않는다.** 회사 정보(사내프로젝트·`acmeq.py`·회사 클래스 경로 6곳) 제거는 사용자가 보류로 결정했다
- **보안 필터링 — 하지 않는다.** 회사 식별 정보를 걸러내지 않는다 (사용자 결정: "보안 상관없어")
- 세션 상태·이력·캐시 동기화 (`projects/` 426MB · `history.jsonl` · `file-history/` 등)
- venv·플랫폼 바이너리 동기화 — 받는 쪽에서 재생성한다
- 자동 실행(훅·크론)으로 동기화하는 것. 두 스킬 모두 **사용자가 명시적으로 호출**한다
- 세 번째 PC·팀 공유 지원. 두 대(회사 mac / 집 Windows) 전제로만 만든다
- **실제 번들 생성과 커밋 — 이 계획서의 범위가 아니다.** 여기서는 스킬 구현까지만 하고,
  번들은 사용자가 **다음 세션에서 스킬을 실행해** 만든다. git 은 사용자가 직접 한다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

회사 mac 과 집 Windows 두 대에서 같은 Claude 하네스를 쓰려는데, **옮길 통로가 없다.**

- `~/.claude` 는 **git 저장소가 아니다** (실측: `git rev-parse` 실패)
- 전체 574MB 중 실제로 옮길 것은 **약 190KB** — 나머지는 세션 상태(`projects/` 426M)·플랫폼 venv(`tools/` 81M)·이력(`file-history/` 41M)·감사로그(`db/audit.jsonl` 2.4M)다
- **`~/.claude` 밖에도 있다**: `~/.claude.json`(66KB)에 MCP 등록이 들어 있다 — user 스코프 `context7`·`google-sheets`, 프로젝트 스코프 `atlassian`(사내프로젝트 저장소 9곳), 그리고 프로젝트별 `allowedTools`. 이걸 빠뜨리면 집에서 MCP 가 통째로 사라진다

받는 쪽이 어려운 이유는 **OS 의존이 설정 전반에 퍼져 있기 때문**이다 (실측).

| 종류 | 실측 내용 |
| --- | --- |
| 절대경로 | `settings.json` 안 `/Users/yubeen/...` **35건** + `additionalDirectories` 5건 전부 |
| macOS 전용 훅 | `terminal-notifier` 를 쓰는 알림 훅 4개 (Stop · PermissionRequest · PreToolUse AskUserQuestion) |
| macOS 전용 명령 allow | `pbpaste` · `sips` · `qlmanage` · `system_profiler` · `pmset` · `memory_pressure` · `colima` · `brew` |
| 도구 경로 | `~/.pyenv/versions/3.12.13` · `/opt/homebrew/...` · `~/.claude/tools/{xlsx,pptx}/venv` |
| 사내프로젝트 전용 | `db/` 폴더 · 훅 3개 · `settings.json` hooks 2개(`acme-docs/_bootstrap`) · `ask` 2건(`acmeq.py`) · `atlassian` MCP 9곳 |

**핵심은 「제거」가 아니라 「변환」이다.** OS 가 다르다는 이유로 항목을 버리면 받는 쪽 하네스가 원본과 달라진다. 경로만 바꾸면 살아나는 것이 대부분이므로, 버리는 것은 **정말 불가능한 것만**이어야 하고 그것도 사용자 승인을 받아야 한다.

### 확정된 설계 결정 (사용자 승인 완료)

| 항목 | 결정 |
| --- | --- |
| 번들·스킬 위치 | **verify-lab 저장소** (사용자 선택) |
| 스킬 개수 | **2개** — 내보내기 / 받기. 입력도 결과도 반대라 한 스킬에 묶으면 분기만 는다 |
| 스킬 계층 | **전역 아님.** 받는 PC 에 전역 스킬이 없으므로 저장소에 둔다 |
| 필터링 | **없음.** 전역 설정을 그대로 내보낸다 |
| 판정 주체 | **받는 쪽.** 사내프로젝트 mac 이 아니면 적용 가능한 것만 |
| 전역 설정 수정 | **보류.** 이번 작업에서 `~/.claude/CLAUDE.md` 를 고치지 않는다 |
| 스크립트 위치 | **스킬 폴더 안** (`.claude/skills/<스킬>/*.py`). 하네스 도구라 `scripts/` 의 도메인 구분(`data`·`studies`·`strategy`)에 맞지 않고, 스킬과 도구가 한 폴더에 있어야 이동·삭제가 원자적이다. **이 저장소가 쓴 코드이므로 Ruff 검사는 그대로 받는다** — 제외하지 않는다 |
| 자격증명 | **둘 다 제외.** `db/acme-prd.env` 와 `keys/**` 를 번들에 넣지 않는다. **제외 사실과 이유를 스킬 문서에 기재**해 받는 쪽이 "왜 없는지" 되묻지 않게 한다 |
| 작업 분리 | 이 계획서는 **스킬 구현까지**. 번들 생성은 다음 세션, 적용은 받는 PC 세션 |

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절과 「디렉토리 구조」
- 전역 `~/.claude/CLAUDE.md` — 「수술적 변경」·「만들기 전에 사다리를 오른다」·「주석은 코드가 못 하는 말만 한다」
- `.claude/rules/docs.md` — 문서 배치 규칙
- `.claude/rules/python.md` + 전역 `~/.claude/rules/python.md` — 파이썬 코딩 표준
- `tests/CLAUDE.md` — 테스트 작성 규칙
- `.claude/rules/session-bootstrap.md` — 6절(산출물 보존)

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 내보내기 스킬이 `--dry-run` 으로 실행돼 **포함·제외 대상 목록이 실측으로 확인됐다** (번들 생성은 다음 세션)
- [x] 제외 대상(venv · `__pycache__` · 세션상태 · 감사로그 · `*.bak-*` · **자격증명 2종**)이 판정 함수에서 걸러진다 — 테스트로 고정
- [x] **자격증명 제외 사실과 이유**가 내보내기 스킬 문서에 기재됐다
- [x] 매니페스트 규격(항목별 SHA-256 · 출처 PC · 시각)이 구현되고 dry-run 으로 확인됐다
- [x] 받기 스킬 문서에 3분류(그대로 적용 / 변환 후 적용 / 승인 후 제외) 판정 규칙과 승인 절차가 적혀 있다
- [x] **받기 스킬이 번들 경로를 스스로 찾는다** — 받는 쪽이 경로를 입력하지 않고 스킬만 실행하면 된다
- [x] 결정 누적 파일 규격이 확정되고, **해시 불일치 시 재질문** 규칙이 문서에 있다
- [x] 작업문서(`claude-config/README.md`) 생성 규격이 구현됐다 (실제 파일은 내보내기 실행 시 생성)
- [x] 회귀/신규 테스트 추가 (`tests/test_claude_config_bundle.py`)
- [x] `poetry run python validate_project.py` 통과 (failed=0, skipped=0; passed/failed/skipped 수 기록)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트(`docs/COMMANDS.md` / 루트 `CLAUDE.md` / `docs/INDEX.md` — 각각 변경 여부 명시)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (실측 수치·설계 결정을 `docs/spec/` 과 루트 `CLAUDE.md` 로 이관)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

**새로 만드는 것**

- `.claude/skills/claude-config-export/SKILL.md` — 내보내기 절차
- `.claude/skills/claude-config-export/export.py` — 복사·추림·해시·매니페스트 생성
- `.claude/skills/claude-config-import/SKILL.md` — 받기 절차 (판정·승인·누적)
- `.claude/skills/claude-config-import/plan_apply.py` — 3분류 판정과 변환안 산출 (적용은 승인 후)
- `claude-config/.gitkeep` — **번들이 놓일 고정 경로.** 폴더만 만들어 둔다
- `tests/test_claude_config_bundle.py` — 포함·제외 판정 검사 + (번들이 있을 때) 위생 검사

**다음 세션에 스킬이 만드는 것** (이 계획서의 산출물이 아니다)

- `claude-config/home/**` — 번들 본체 (원본 트리 구조 유지)
- `claude-config/claude_json.json` — `~/.claude.json` 에서 이식 대상 키만 추린 것
- `claude-config/MANIFEST.json` — 출처 PC·시각·항목별 SHA-256
- `claude-config/README.md` — 작업문서
- `claude-config/decisions/<pc_id>.json` — 받는 쪽 결정 누적

**고치는 것**

- `pyproject.toml` — Ruff·Black 에서 `claude-config` 제외. **`black .` 이 번들 안의 훅 `.py` 를 재포맷해 원본을 변형시키는 것을 막는다** (번들은 이 저장소가 쓴 코드가 아니라 원본 사본이다)
- 루트 `CLAUDE.md` — 「디렉토리 구조」에 `claude-config/` 추가 + **「저장소 밖 경로를 참조하지 않는다」의 예외 명시**
- `docs/INDEX.md` — 새 문서 등록. 실측 결과 `tests/test_index.py` 의 등록 의무는 `docs`·`reference` 폴더에만 걸려 **강제되지는 않지만**, INDEX 는 저장소 문서 지도이므로 등록한다

**`docs/COMMANDS.md`**: 변경 있음 — 두 스킬이 내부에서 실행하는 스크립트 경로를 등록한다. (스킬 호출 자체는 명령어가 아니지만, 스크립트를 직접 실행할 수 있어야 진단이 된다)

### 데이터/결과 영향

- **측정 결과에 영향 없음.** `storage/`·`docs/research/`·`docs/strategy/` 를 건드리지 않는다
- 저장소 크기가 약 190KB 늘어난다 (번들 본체)
- `claude-config/` 는 **재실행 시 덮어쓴다.** 무엇이 바뀌었는지는 git diff 로 본다

## 6) 단계별 계획(Phases)

### Phase 0 — 포함·제외 판정을 테스트로 먼저 고정 (레드)

**무엇이 번들에 들어가면 안 되는가**가 이 작업의 핵심 인바리언트다. 세션 이력·감사로그·venv 가 섞이면 저장소가 수십 MB 로 부풀고, **자격증명이 섞이면 PUBLIC 저장소의 git 이력에서 지울 수 없다.**

번들 생성은 이 계획서 범위 밖이므로 **번들을 검사하는 것으로는 레드를 만들 수 없다.** 대신 판정 함수를 대상으로 삼는다 — `tests/test_result_citations.py` 와 같은 구조다(순수 함수를 `tmp_path` 로 검사하고, 실물은 있을 때만 본다).

**작업 내용**:

- [x] `tests/test_claude_config_bundle.py` 작성 (판정 함수가 없어 **레드 45 errors** 확인)
  - [x] `tmp_path` 에 가짜 `~/.claude` 트리를 만들어 판정 함수를 검사한다
  - [x] **포함되어야 하는 것**: `CLAUDE.md` · `settings.json` · `skills/**` · `commands/**` · `rules/**` · `hooks/*.py` · `tools/` 의 스크립트
  - [x] **걸러져야 하는 것**: `**/venv/**` · `**/__pycache__/**` · `*.jsonl` · `*.bak-*` · `projects/` · `sessions/` · `file-history/` · `shell-snapshots/` · `session-env/` · `cache/` · `ide/` · `daemon/` · `jobs/` · `paste-cache/` · `downloads/` · `backups/` · **`plugins/**`**
  - [x] **자격증명은 반드시 걸러진다** — `db/acme-prd.env` · `keys/**`. 되돌릴 수 없는 유출이므로 별도 테스트로 따로 고정한다
  - [x] **화이트리스트에 없는 새 폴더는 기본 제외**임을 고정한다 — 허용목록 방식이어야 새 폴더가 조용히 딸려오지 않는다
  - [x] 번들이 실재할 때만 도는 위생 검사 — 매니페스트 등재·해시 일치·금지경로 부재·크기 상한. **번들이 없으면 통과**한다 (`pytest.skip` 을 쓰지 않는다 — Done 조건이 `skipped=0` 이다)
  - [x] 크기 상한 확정 — **실측 355,917 bytes / 32개**, 상한 `2_000_000` bytes (`plugins/` 사고 재발을 잡을 수준)

---

### Phase 1 — 내보내기 스킬 (그린 전환)

**작업 내용**:

- [x] **`pyproject.toml` 에 Ruff·Black 제외를 «먼저» 넣는다** — 번들을 만든 뒤에 하면 그 사이 `black .` 이 훅 원본을 재포맷한다 (Black·Ruff 는 저장소 전체를 훑고 현재 제외는 `reference` 뿐)
- [x] `export.py` 작성
  - [x] **판정 함수를 분리한다** — Phase 0 테스트가 이 함수를 부른다. 스킬 폴더명에 하이픈이 있어(`claude-config-export`) 일반 `import` 가 성립하지 않으므로 테스트는 `importlib` 로 파일 경로에서 로드한다
  - [x] 포함 목록을 **명시적 화이트리스트**로 정의한다 — 새 폴더가 조용히 딸려오지 않게
  - [x] `~/.claude/` 에서: `CLAUDE.md` · `settings.json` · `skills/**` · `commands/**` · `rules/**` · `hooks/*.py` · `tools/**`(venv 제외) · `db/**`(venv·`*.jsonl`·`.env` 제외). **`plugins/` 는 실측 후 제외로 바꿨다**(아래 진행 로그)
  - [x] `~/.claude.json` 에서: `mcpServers` · `projects[].{mcpServers, allowedTools, enabledMcpjsonServers, disabledMcpjsonServers}` 만 추린다. 캐시·통계 키(`cachedGrowthBookFeatures` 612개 · `last*` 등)는 버린다
  - [x] **자격증명 2종을 명시적으로 배제**한다 (`db/acme-prd.env` · `keys/**`) — 허용목록보다 «먼저» 판정한다
  - [x] 제외 규칙 위반을 **스스로 검사해 중단**한다 — 테스트가 잡기 전에 스크립트가 먼저 막는다
  - [x] `MANIFEST.json` 생성: 출처 PC(hostname·platform·machineID) · 내보낸 시각(KST) · 항목별 상대경로와 SHA-256
  - [x] `README.md` 생성 — 출처·시각·빠진 것·받는 쪽 절차
  - [x] `--dry-run` 으로 복사 없이 목록만 출력. **항목을 하나씩 전부 보여준다** — 요약만으로는 「담기면 안 되는 것이 섞였는가」를 대조할 수 없다
- [x] `.claude/skills/claude-config-export/SKILL.md` 작성
  - [x] **자격증명 2종을 왜 빼는지 기재**한다 — 받는 쪽이 "왜 없지"를 되묻지 않게. `keys/` 는 토큰이 7일마다 만료돼 옮겨도 재인증이 필요하다는 사실도 함께 적는다
  - [x] 실행 후 사용자가 무엇을 확인하고 커밋하는지 (git 은 사용자가 직접 한다)
- [x] `--dry-run` 실행으로 포함·제외 목록 확인 → **Phase 0 판정 테스트 그린**

**Validation**:

- [x] `poetry run pytest tests/test_claude_config_bundle.py -v` 통과 (**48 passed**)
- [x] dry-run 출력에 자격증명 2종이 **없음**을 눈으로 확인 (`.env.example` 만 담기고 `acme-prd.env` 는 빠짐)
- [x] dry-run 이 집계한 총 크기로 Phase 0 의 상한값 확정 (**355,917 bytes / 32개** → 상한 2,000,000)

---

### Phase 2 — 받기(마이그레이션) 스킬

받는 쪽이 이 작업의 어려운 절반이다. **경로가 다르다는 이유로 버리지 않는다.**

**작업 내용**:

- [x] 3분류 판정 규칙을 `SKILL.md` 에 명문화한다

  | 분류 | 처리 | 예 |
  | --- | --- | --- |
  | **A. 그대로 적용** | 복사 | `skills/**` · `commands/**` · `rules/**` · `CLAUDE.md` · 훅 `.py` 본문 |
  | **B. 변환 후 적용** | 경로 치환 후 복사, **변환 내역을 보고** | `settings.json` 의 `/Users/yubeen/**` 35건 · `additionalDirectories` · venv 경로 |
  | **C. 승인 후 제외** | **리스트업 → 사용자 승인 → 제외** | `terminal-notifier` 훅 · 사내프로젝트 훅·MCP·`ask` · macOS 전용 명령 allow |

- [x] `plan_apply.py` 작성 — **적용안을 산출만 하고 쓰지 않는다.** 판정 결과를 표로 출력하고, 승인 후 별도 단계에서 적용
  - [x] **번들 경로를 스스로 찾는다** — 스킬 파일 위치를 기준으로 저장소 루트의 `claude-config/` 를 해석한다. 받는 쪽은 **경로를 입력하지 않고 스킬만 실행**하며, clone 위치가 PC 마다 달라도 상대경로라 맞는다
  - [x] 받는 PC 조사: `platform` · 홈 경로 · Workspace 경로 · 사내프로젝트 저장소 존재 여부 · 설치된 도구(`terminal-notifier` 등)
  - [x] 경로 매핑을 **사용자에게 확인받고 결정 파일에 저장** — 집 Windows 의 사용자명·Workspace 위치는 이 PC 에서만 알 수 있다
  - [x] C 분류는 **항목별로 사유를 붙여** 리스트업한다. "왜 적용할 수 없는가"가 없으면 판단할 수 없다
- [x] 결정 누적 규격 확정 — `claude-config/decisions/<pc_id>.json`
  - [x] `pc_id`: hostname + platform 조합 (PC 마다 파일이 갈린다 — 회사 mac 의 제외 결정과 집 Windows 의 결정은 다르다)
  - [x] 항목별로 `{decision, reason, source_hash}` 를 남긴다
  - [x] **다음 실행 시 `source_hash` 가 같으면 되묻지 않고 이전 결정을 적용**한다
  - [x] **`source_hash` 가 다르면 반드시 다시 묻는다** — 내용이 바뀐 항목에 옛 결정을 적용하면 조용히 어긋난다
  - [x] 결정 파일 자체도 git 으로 공유한다 (다른 PC 가 "저쪽에서 무엇을 뺐는지" 볼 수 있어야 한다)
- [x] 기존 설정 보호: 적용 전 받는 PC 의 `~/.claude/settings.json` 과 `~/.claude.json` 을 **타임스탬프 백업**한다. 되돌릴 수 없는 덮어쓰기를 만들지 않는다
- [x] `.claude/skills/claude-config-import/SKILL.md` 작성

**Validation**:

- [x] 회사 mac 에서 `plan_apply.py` 를 실행해 판정표 확인 — **그대로 적용 258 / 변환 34 / 확인 필요 11(훅 전부)**. 자기 자신이 대상이라 훅 외에는 확인 대상이 없어 정상
- [x] 가짜 Windows 환경으로 B·C 분류 확인 — `home=C:/Users/home`, `path_map={"/Users/yubeen/Workspace": "D:/dev"}` 로 재조립했을 때 **치환되지 않고 남은 출처 경로 0건**
- [x] 승인 없이 `--apply` 하면 중단되는지 확인 — **종료코드 1, 백업 파일 생성 없음**
- [x] 결정 누적 확인 — 저장 후 재실행 시 재질문 섹션이 사라지고, **번들 내용을 바꾸자 「내용이 바뀌어 다시 묻습니다」로 복귀**
- [x] `settings.json` 재조립 확인 — 훅만 빠지고 **권한 236건(allow 142·deny 68·ask 26)과 스칼라 설정은 전부 보존**

---

### Phase 3 — 작업문서와 저장소 편입

**작업 내용**:

- [x] `README.md` **템플릿 내용 확정** — 파일 자체는 `export.py` 가 실행 시점 값을 채워 생성한다
  - [x] 이 번들이 무엇인지, 출처 PC 와 시각
  - [x] 받는 쪽 절차 — **스킬만 실행하면 된다**는 사실과, 스크립트 직접 실행 경로 둘 다
  - [x] **무엇이 애초에 빠졌는지** — venv·세션상태·감사로그·**자격증명 2종**. 빠진 것을 모르면 "왜 없지"를 되묻게 된다
  - [x] 결정 파일의 위치와 읽는 법
- [x] `claude-config/.gitkeep` 생성 — 번들이 놓일 고정 경로를 미리 확보한다
- [x] 루트 `CLAUDE.md` 「디렉토리 구조」에 `claude-config/` 추가
- [x] 루트 `CLAUDE.md` 에 **예외 명시** — 「이 프로젝트는 저장소 밖의 경로를 참조하지 않습니다」와 정면으로 어긋나므로, 어긋나는 이유를 적지 않으면 다음 세션이 이 폴더를 오해한다
- [x] `docs/INDEX.md` 에 새 문서 등록

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` 에 스크립트 실행 명령 등록)
- [x] 자동 포맷 적용 — `poetry run black .`
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [x] `poetry run python validate_project.py` (passed=1038, failed=0, skipped=0) — Ruff·PyRight·Pytest 모두 통과

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 하네스 / 전역 Claude 설정을 저장소로 내보내고 다른 PC 에서 경로 변환해 적용하는 스킬 2개 추가
2. 하네스 / 두 PC 하네스 동기화 — 번들 내보내기·마이그레이션 스킬과 결정 누적 규격
3. 하네스 / 전역 설정 백업 번들과 위생 테스트, OS 경로 변환 판정 절차 도입
4. 하네스 / claude-config 번들 신설 — 내보내기·받기 스킬, 승인 기반 제외와 해시 재질문
5. 하네스 / 전역 하네스 이식 절차 구축 (번들·매니페스트·PC별 결정 파일)

## 7) 리스크(Risks)

| # | 리스크 | 완화 |
| --- | --- | --- |
| 1 | **저장소 성격 충돌** — verify-lab 은 "측정소"이고 CLAUDE.md 가 「저장소 밖 경로를 참조하지 않는다」고 못 박았다. 이 번들은 정면으로 어긋난다 | Phase 3 에서 예외를 **명시적으로** 적는다. 적지 않으면 다음 세션이 규칙 위반으로 오해하거나 조용히 지운다 |
| 2 | **자격증명이 PUBLIC 저장소의 git 이력에 영구히 남는다** — 커밋 후에는 파일을 지워도 이력에서 사라지지 않는다 | **해소됨.** `db/acme-prd.env` 와 `keys/**` 를 번들에서 제외하기로 확정했고, 그 제외를 Phase 0 의 **별도 테스트로 고정**한다. 규칙만으로는 다음에 화이트리스트를 넓힐 때 새어나간다 |
| 3 | **Windows 훅 실행 방식을 실측하지 않았다** — 현재 훅 명령이 POSIX sh 문법(`f=...; [ -f "$f" ] && ...`)과 `jq` 에 의존한다 | 받는 쪽에서 **실측 후 결정**한다. 회사 mac 에서 추측해 변환 규칙을 박으면 틀린 채로 굳는다. C 분류(승인 후 제외) 후보로 두고 집에서 판정 |
| 4 | 번들 재실행이 이전 번들을 덮어써 무엇이 바뀌었는지 놓친다 | git diff 로 확인한다. 매니페스트에 해시가 있어 변경 항목이 드러난다 |
| 5 | `~/.claude.json` 은 Claude Code 가 **실행 중 계속 쓴다.** 적용 시점에 충돌할 수 있다 | 적용 전 백업 + 적용은 종료 상태에서 하도록 문서에 명시 |
| 6 | 결정 누적이 오래되어 "왜 뺐는지" 근거가 흐려진다 | 결정 파일에 `reason` 을 필수로 남긴다 |
| 7 | 스킬 폴더명의 하이픈 때문에 테스트가 판정 함수를 일반 `import` 로 부를 수 없다 | `importlib` 로 파일 경로에서 로드한다. `pyrightconfig.json` 의 tests 환경은 `reportUnknownMemberType` 등이 꺼져 있어 통과할 가능성이 높으나, 걸리면 그 자리에서 대응한다 |
| 8 | 두 PC 에서 각각 내보내 push 하면 번들이 충돌한다 | git 이 충돌로 잡는다. 사용자가 git 을 직접 다루므로 조용히 덮이지 않는다 |

## 8) 메모(Notes)

### 확정 사항 (2026-09-09 사용자 승인)

- **자격증명 2종을 번들에서 제외한다** — `~/.claude/db/acme-prd.env`(회사 운영 DB 접속 정보) · `~/.claude/keys/sheets-mcp-{oauth,token}.json`(Google OAuth).
  **제외 사실과 이유를 내보내기 스킬 문서에 기재**한다. `sheets-mcp-token.json` 은 동의화면이 「테스트」 상태라 **7일마다 만료**되므로 옮겨도 재인증이 필요해 실익이 작다 (전역 `CLAUDE.md` 기록)
- **이 계획서의 범위는 스킬 구현까지**다. 번들 생성은 사용자가 다음 세션에서 스킬을 실행해 하고, 적용은 받는 PC 의 세션에서 한다

### 실측 기록 (2026-09-09, 회사 mac)

- `~/.claude` 는 git 저장소가 아니다
- 전체 574MB / 옮길 것 약 190KB (`CLAUDE.md` 48K · `settings.json` 16K · `skills/` 60K · `hooks/*.py` 48K · `commands/`+`rules/` 16K · `tools/` 스크립트 44K)
- `settings.json`: allow 142건 · deny 68건 · ask 26건 · additionalDirectories 5건. 절대경로 35건
- `~/.claude.json` 66KB — `projects` 15개, MCP 는 user 2개(`context7`·`google-sheets`) + 프로젝트 스코프 `atlassian` 9곳
- 회사 식별 정보는 `~/.claude/CLAUDE.md` 6곳(354·417·422·440·462·493줄). **이번 작업에서 건드리지 않는다**
- `hooks/block-db-connect.py` 는 범용 DB 접속 차단 훅이지만 `acmeq.py` 예외 블록을 안고 있다 — 받는 쪽 C 분류 후보
- `reexec_in_venv()` (`db/acmeq.py` 222줄, 26줄짜리)는 로직이 범용이나 회사 파일 안에만 있다
- **새 최상위 폴더는 기존 테스트를 깨지 않는다** — `test_index.py` 의 등록 대상은 `docs`·`reference` 뿐이고, `test_layer_contracts.py` 는 `src/` 만, `test_research_docs.py` 는 `docs/research/` 만 스캔한다. `pytest` 는 `tests/` 만 수집한다
- **그러나 Ruff 와 `black .` 은 저장소 전체를 훑는다** (현재 `extend-exclude` 는 `reference` 뿐) — 제외를 먼저 넣지 않으면 **번들 안의 훅 원본이 재포맷된다.** 백업이 원본과 달라지는 조용한 손상이라 Phase 1 의 첫 항목으로 올렸다

### 진행 로그 (KST)

- 2026-09-09 18:01: 계획서 작성. 착수 전 「미결 사항」 승인 대기
- 2026-09-09 18:10: 자체 검증 — 세 건 수정. ① INDEX 등록이 강제된다는 서술이 틀렸음(등록 의무는 `docs`·`reference` 한정) ② `black .` 이 번들을 재포맷하는 경로를 발견해 제외 설정을 Phase 3 → Phase 1 로 앞당김 ③ 스크립트 위치를 「확정된 설계 결정」에 명시
- 2026-09-09 18:25: 사용자 승인으로 **범위 축소** — 계획서는 스킬 구현까지, 번들 생성은 다음 세션. 자격증명 2종 제외 확정.
  이에 따라 **Phase 0 을 재설계**했다. 번들이 없는 상태로 Done 이 되어야 하는데 「번들 위생 검사」로는 레드를 만들 수 없고,
  번들 부재를 `pytest.skip` 으로 넘기면 Done 조건(`skipped=0`)에 걸린다. 그래서 대상을 **판정 함수**로 바꾸고
  (`tests/test_result_citations.py` 와 같은 구조), 번들 위생 검사는 **실재할 때만 도는 검사**로 남겼다
- 2026-09-09 18:50: Phase 0 레드(45 errors) → Phase 1 그린(48 passed) 확인.
  **계획 전제가 실측으로 깨져 `plugins/` 를 포함에서 제외로 바꿨다.** 계획서는
  `plugins/known_marketplaces.json` 과 `plugins/marketplaces/**` 를 담기로 했는데,
  dry-run 결과 **441개 / 6.4MB** 가 나왔다. 실체는 github `anthropics/claude-plugins-official`
  의 사본이고 `officialMarketplaceAutoInstalled` 가 말하듯 **받는 쪽에서 자동으로 다시 설치**된다.
  수동 설치한 플러그인은 없다(`~/.claude.json`·`settings.json` 어디에도 목록이 없다).
  `known_marketplaces.json` 도 `installLocation` 에 절대경로를 담고 있어 옮기면 변환 대상만 는다.
  승인받은 전제가 「약 190KB」였고 6.4MB 는 그 30배라 전제 자체가 무너지므로 제외했다.
  제외 후 **32개 / 355,917 bytes**
- 2026-09-09 19:30: Phase 2 완료. **판정 규칙을 두 번 고쳤고 둘 다 실측이 근거다.**
  ① 처음에는 권한 규칙에도 명령 존재 검사를 걸어 자기 자신을 대상으로 했는데도 13건이
  제외 후보로 나왔다(`rg` · `tree` · `set -e`). **권한 규칙은 명령이 없어도 뺄 이유가 없다** —
  안 쓰이면 그만이고 나중에 설치하면 살아나며, 빼면 오히려 그때 승인창이 뜬다. 검사를 훅과 경로로 한정했다.
  ② 훅의 셸 명령을 파싱해 실행 파일을 뽑는 방식은 **버렸다.** `"$(jq` · `]` · `2>/dev/null)` ·
  `/.claude/hooks/plan_gate.py` 를 실행 파일로 오인했고 고칠 때마다 새 실패 형태가 나왔다.
  훅은 6개뿐이고 이식성 판단에 문맥이 필요하므로(`terminal-notifier` 는 불가, `command -v python3 || command -v python` 은 가능)
  **사람에게 넘기고 스크립트는 판단 재료만 준다.**
  또 `PreToolUse[0]` 이 두 번 나오는 **키 충돌**을 발견해 항목 키에 matcher 를 넣었다 —
  한 이벤트에 matcher 가 다른 그룹이 여럿(PreToolUse 는 4개)이라 결정 파일에서 서로 덮어썼다.
  홈 경로 하나만으로는 작업 폴더가 안 맞아 결정 파일의 `path_map` 으로 **쌍을 추가**할 수 있게 했고, 긴 경로부터 치환한다
- 2026-09-09 19:45: Phase 3 · 마지막 Phase 완료. 검증용으로 만들었던 번들을 지우고 `claude-config/.gitkeep` 만 남겼다.
  `validate_project.py` **passed=1038 / failed=0 / skipped=0**

---
