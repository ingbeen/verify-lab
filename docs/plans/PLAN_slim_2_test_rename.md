# Implementation Plan: 경량화 ② — `test_strategy_*` 테스트 파일 개명 (이름만)

> 작성/운영 규칙(SoT): `/impl-plan` 스킬(`~/.claude/skills/impl-plan/SKILL.md`)을 반드시 참고하세요.  
> (이 템플릿을 수정하거나 새로운 양식의 계획서를 만들 때도 해당 스킬을 포인터로 두고 준수합니다.)

**상태**: 🟡 Draft

---

🚫 **이 영역은 삭제/수정 금지** 🚫

**상태 옵션**: 🟡 Draft / 🔄 In Progress / ✅ Done

**Done 처리 규칙**:

- ✅ Done 조건: DoD 모두 [x] + `skipped=0` + `failed=0`
- ⚠️ **스킵이 1개라도 존재하면 Done 처리 금지 + DoD 테스트 항목 체크 금지**
- 상세: `/impl-plan` 스킬의 "3) 스킵 및 완료 규칙" 참고
- 위 조건은 `~/.claude/hooks/plan_lint.py`가 저장 시 자동 검사합니다

---

**작성일**: 2026-09-26 16:55
**마지막 업데이트**: 2026-09-26 16:55
**관련 범위**: tests (파일 이름), 그 이름을 가리키는 주석·문서 네 곳
**관련 문서**: `tests/CLAUDE.md`, 루트 `SLIM_SERIES.md`, `docs/plans/REPORT_lightweight_inventory.md` §2.8

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

- [ ] 목표 1: `test_strategy_*` 5개를 **검사 대상 계층 이름**으로 개명한다 — 내용은 한 바이트도 바꾸지 않는다
- [ ] 목표 2: 옛 이름을 가리키는 **현재 파일 참조** 네 곳을 새 이름으로 고친다

## 2) 비목표(Non-Goals)

- **테스트 내용 변경 없음** — 삭제 매매법 잔재·중복 테스트·「세_」 테스트 함수 이름은 계획서 ③ 이다. 섞으면 git 이 rename 으로 잡지 못한다(`docs/MEMORY.md` 「이름만 바꾸는 변경과 값을 바꾸는 변경을 한 커밋에 섞지 않는다」)
- **옛 커밋 시점의 경로를 적은 기록은 고치지 않는다** — `docs/조사/만기_말일/결과.md` 의 복원 절차(`5022dc9` 트리의 파일 목록), `docs/조사/월말_진입/규칙.md` 의 삭제된 `test_strategy_month_end_runner.py`, `docs/조사/원달러_조달.md` 의 `test_strategy_grid_*`. 그 이름은 그 커밋에 실제로 있던 이름이다
- `tests/CLAUDE.md` 「`test_*.py` 는 src 와 1:1」 서술 — 계획서 ④
- `docs/plans/` 의 임시 문서(`AUDIT_slim_*`·`REPORT_*`)가 옛 이름을 쓰는 것 — 조사 시점 기록이라 그대로 둔다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

- `test_strategy_*` 는 `d838db9`(2026-09-15)에 없어진 `src/verify_lab/strategy/` 시절 이름이다. 지금은 `execution/` 과 `studies/reverse/trading.py`, 매매법 전부의 산출물 계약을 검사하는데 이름이 그것을 말하지 않는다. 같은 성격의 중간선거 체결 테스트는 `test_studies_midterm_cycle_trading.py` 라 **규칙이 없다**
- 이웃 관용: `test_<계층>_<모듈>.py` (`test_measure_screening.py` · `test_report_tables.py` · `test_studies_reverse_runner.py`), 계층을 가로지르는 계약은 계층 없이 (`test_layer_contracts.py` · `test_index.py` · `test_tracks.py`)
- 결정: 보고서 §10 Q8 ③ (개명, 별도 커밋)

### 개명표

| 지금 | 새 이름 | 검사 대상 (import 로 확인) |
| --- | --- | --- |
| `tests/test_strategy_trade_fill.py` | `tests/test_execution_trade_fill.py` | `execution/trade_fill.py` |
| `tests/test_strategy_trade_fill_scheduled.py` | `tests/test_execution_trade_fill_scheduled.py` | `execution/trade_fill.py` (달력형 진입점) |
| `tests/test_strategy_periods.py` | `tests/test_execution_periods.py` | `execution/periods.py` |
| `tests/test_strategy_reverse_runner.py` | `tests/test_studies_reverse_trading.py` | `studies/reverse/trading.py` (`test_studies_reverse_runner.py` 는 측정 runner 라 이름이 겹치지 않는다) |
| `tests/test_strategy_output_contract.py` | `tests/test_output_contract.py` | 매매법 전부의 산출물 계약 — 계층을 가로지르므로 `test_layer_contracts.py` 와 같은 결 |

### 고칠 참조 (현재 파일을 가리키는 것 — 2026-09-26 grep)

- `src/verify_lab/CLAUDE.md` — `tests/test_strategy_output_contract.py` (「매매 산출물 계약」 절, 두 곳 이상일 수 있다 — grep 으로 전부)
- `tests/test_layer_contracts.py` — 주석 「`test_strategy_output_contract.py` 가」
- `src/verify_lab/execution/periods.py` — docstring 「`tests/test_strategy_output_contract.py` 가 본다」
- `src/verify_lab/studies/reverse/trading.py` — 주석 「(`tests/test_strategy_output_contract.py`)」

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- `.claude/plan-config.json` — 이 저장소의 검증 명령·자동 포맷·근거 승격 목적지 (**값의 SoT**)
- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절 (값이 아니라 **판단 근거**)
- `tests/CLAUDE.md`
- `docs/MEMORY.md` 「이름만 바꾸는 변경과 값을 바꾸는 변경을 한 커밋에 섞지 않는다」
- 루트 `SLIM_SERIES.md` 「시리즈 공통 주의」

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [ ] 5개 파일이 새 이름으로 있고 **내용이 HEAD 의 옛 파일과 바이트 동일**하다
- [ ] 현재 파일을 가리키는 옛 이름 참조 0 (Non-Goals 의 기록은 제외)
- [ ] 수집되는 테스트 수가 개명 전과 같다
- [ ] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [ ] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [ ] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [ ] 필요한 문서 업데이트 — `docs/COMMANDS.md` 변경 없음 · `src/verify_lab/CLAUDE.md` 경로 표기만 변경 · `SLIM_SERIES.md` 진행 표·인계 메모 갱신
- [ ] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다 (개명 규칙은 이웃 관용 그대로라 새 규칙이 없다. 옛 → 새 이름 대응은 `SLIM_SERIES.md` 인계 메모에 남긴다 — 뒤 계획서가 감사 원문의 옛 이름을 읽기 때문)
- [ ] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `tests/` 의 5개 파일 — 이름만 (개명표)
- `src/verify_lab/CLAUDE.md` · `tests/test_layer_contracts.py` · `src/verify_lab/execution/periods.py` · `src/verify_lab/studies/reverse/trading.py` — 경로 표기만
- `SLIM_SERIES.md` · 이 계획서
- `docs/COMMANDS.md`: **변경 없음**

### 데이터/결과 영향

- 없음. 산출물을 만드는 코드는 주석 두 줄만 바뀐다

## 6) 단계별 계획(Phases)

### Phase 1 — 개명과 참조 갱신 (그린 유지)

**작업 내용**:

- [ ] 착수 전: `git status` 가 깨끗한지, `poetry run pytest --collect-only -q -p no:cacheprovider | tail -1` 의 수집 수를 진행 로그에 적는다 (작성 시점 1,282)
- [ ] **`git mv` 를 쓰지 않는다** — git 은 사용자가 한다. 셸 `mv` 로 개명한다 (사용자가 스테이징하면 git 이 내용 동일로 rename 을 잡는다)
- [ ] 참조 네 곳을 grep(`test_strategy_`)으로 다시 찾아 새 이름으로 고친다. Non-Goals 의 기록은 건드리지 않는다

**Validation**:

- [ ] 개명한 5개 각각 `git show HEAD:<옛 경로> | cmp - <새 경로>` 가 차이 없음
- [ ] `grep -rn 'test_strategy_' --include=*.py --include=*.md --exclude-dir={.git,.venv,plans} .` 의 결과가 Non-Goals 의 옛 기록뿐이다
- [ ] 수집 수가 착수 전과 같다

---

### Phase 2 (마지막) — 문서 정리 및 최종 검증

**작업 내용**

> 🔴 **`/commit` 이 «맨 마지막»인 것은 의도다.** 그 스킬은 「후보 뒤에는 아무것도 덧붙이지 말 것」으로
> 끝나므로 **호출하는 순간 그 턴이 거기서 닫힌다.** 중간에 두면 뒤에 적힌 항목이 그 벽 너머에 남는다 —
> 실제로 두 번 그렇게 샜다(`[실측] 2026-09-14` 후보를 계획서에 안 옮김 · `2026-09-16` 옮기고 체크박스를 안 닫음).
> **체크박스와 상태를 먼저 확정하고, 커밋 후보를 마지막에 만든다.**

- [ ] 필요한 문서 업데이트 (`docs/COMMANDS.md` 변경 없음 확인)
- [ ] `SLIM_SERIES.md` 진행 표(②: 완료 대기 커밋)와 인계 메모(옛 → 새 이름 대응 포함)를 갱신한다
- [ ] 자동 포맷 적용 (`poetry run black .`)
- [ ] 변경 기능 및 전체 플로우 최종 검증
- [ ] Validation 절에 `/code-review` 와 품질 검증 **실행 결과**를 적는다
- [ ] DoD 체크리스트 최종 업데이트 및 체크 완료
- [ ] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정
- [ ] 🔴 **마지막에 `/commit` 을 실행하고 그 후보를 «이 계획서» 의 `#### Commit Messages` 절에 옮긴다** —
      `/commit` 은 계획서를 모르고 「후보 뒤에 아무것도 덧붙이지 말 것」으로 끝나므로,
      **대화에만 내면 그 절이 빈 채로 남는다.** 체크박스 갱신이 diff 에 더 들어가지만
      커밋 메시지의 내용을 바꾸지 않는다. **커밋은 사용자가 한다 — 후보만 낸다**

**Validation**:

> 순서를 지킨다 — 리뷰에서 고치면 코드가 바뀌므로 품질 검증이 마지막 관문이어야 한다.
> **버그가 0 인 회차에서 끝낸다.** 2회차에도 버그가 나오면 사용자에게 보고하고 3회차 여부를 묻는다 —
> 「그 외」는 목록만 남기고 고치지 않는다. `/impl-plan` 의 「코드 리뷰」 절이 SoT 다.

- [ ] `/code-review xhigh` **1회차** (발견 \_\_건 — 버그 \_\_ · 그 외 \_\_ · 조치: \_\_)
- [ ] `poetry run python validate_project.py` (passed=\_\_, failed=\_\_, skipped=\_\_)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다.**
> 계획서를 쓰는 시점에는 diff 가 없어 여기 적는 것은 전부 추측이고,
> **추측으로 적은 줄은 그대로 나간다.** 형식·문체 규칙은 `/commit` 이 정한다.

- [ ] (미작성 — `/commit` 을 실행하고 후보 5개를 **이 자리에** 번호 붙은 줄로 옮긴 뒤 이 줄을 지운다)

## 7) 리스크(Risks)

- **내용이 조금이라도 바뀌면 git 이 rename 대신 삭제+추가로 본다** — 이 계획서에서는 5개 파일의 내용을 고치지 않는다. 리뷰 지적이 그 파일 내용을 겨누면 계획서 ③ 백로그로 넘긴다
- **다른 곳이 옛 경로를 문자열로 부를 수 있다** (`pytest.ini`·`validate_project.py`·CI) — Phase 1 grep 에 `*.ini`·`*.toml`·`*.cfg` 도 넣어 확인한다
- **`VIRTUAL_ENV` 가 프로젝트 밖을 가리키면 pytest·validate 가 전부 실패한다** — 그 증상이면 `env -u VIRTUAL_ENV` 로 다시 돈다

## 8) 메모(Notes)

- 시리즈의 SoT 는 루트 `SLIM_SERIES.md`. 이 계획서는 ② 이며 **커밋 하나**로 끝난다
- 뒤 계획서(③)의 감사 원문(`AUDIT_slim_*`)은 옛 이름으로 적혀 있다 — 인계 메모의 대응표로 읽는다

### 진행 로그 (KST)

- 2026-09-26 16:55: 계획서 작성 (Draft). 착수는 `SLIM_SERIES.md` 를 받은 세션이 한다
