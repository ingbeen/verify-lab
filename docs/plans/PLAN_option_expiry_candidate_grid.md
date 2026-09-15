# Implementation Plan: 옵션 만기일 매매 — 1차 게이트 통과 칸 전체에 손절선 격자

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

**작성일**: 2026-09-15 16:09
**마지막 업데이트**: 2026-09-15 16:09
**관련 범위**: strategy (매매 계층), scripts
**관련 문서**: `.claude/rules/trading.md`, `src/verify_lab/CLAUDE.md`, `scripts/CLAUDE.md`, `tests/CLAUDE.md`

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

- [ ] 목표 1: **1차 게이트를 통과한 칸 전체**(금요일 청산 26칸)에 손절선 격자를 걸어
      매매 성적표 규격(`성적표.csv` 와 같은 24컬럼)으로 산출한다
- [ ] 목표 2: 그 칸 목록을 **하드코딩하지 않고** `measure/screening.py` 의 게이트에서 유도한다 —
      손으로 적으면 그 순간 사후 선택이 되고, 시세를 재수집하면 낡는다
- [ ] 목표 3: 기존 기본 실행(`EXPIRY_CELLS` 7칸 · 손절 −5%)이 **한 칸도 달라지지 않고** 그대로 돈다

## 2) 비목표(Non-Goals)

- **KODEX 200 목요일 청산 5칸은 범위 밖이다.** 매매 계층은 금요일 청산만 지원한다
  (`collect_entries` 의 `exit_weekday=FRIDAY`). 넣으려면 `ExpiryCell` 에 청산 요일 축을 더하고
  식별 컬럼을 늘려야 하는데, 그것은 **세 매매법이 공유하는 성적표 컬럼 계약을 바꾸는 별건**이다.
  목요일 청산은 확정 규칙 §1.3 에 없는 **대조축**이기도 하다 (설계 결정 ⑳)
- **`EXPIRY_CELLS` 를 바꾸지 않는다.** 무엇을 실제로 거는지는 사용자가 정하며,
  이 작업은 **볼 목록을 넓히는 것**이지 대상을 고치는 것이 아니다
- **손절선을 다시 고르지 않는다.** 격자는 재료만 내고 값 선택은 사용자가 한다
  (측정의 원칙 1 · `.claude/rules/trading.md`)
- **수수료·슬리피지·세금을 넣지 않는다.** 맨몸 성적이 기본이며 요청받을 때만 넣는다
- **결과 문서(`docs/research/` · `docs/strategy/`)의 판정 문장을 고치지 않는다.**
  이 계획은 산출 수단을 만드는 것이고, 무엇을 뺄지는 사용자가 산출물을 보고 정한다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

**검증 계층은 60칸 전부를 판정하는데 매매 계층은 7칸만 돈다.**

- `scripts/run_option_expiry.py` 는 전 칸(종목 × 만기월 × 청산요일 = 60칸)의
  1차 판정을 `candidates.csv` 로 낸다. 손절이 없는 **맨몸** 측정이다.
  2026-09-15 재실행에서 **후보 31칸 · 제외 29칸**이었고 git diff 는 0이었다
- `scripts/run_option_expiry.py` 는 손절을 걸지만 대상이
  `strategy/option_expiry_constants.py` 의 `EXPIRY_CELLS` **7칸으로 하드코딩**돼 있다.
  `--grid`(무손절 + −1.0~−10.0%, 0.5%p 간격 19개)도 그 7칸만 돈다
- 그래서 **「게이트를 넘은 다른 칸들이 손절을 걸면 어떻게 되는가」를 물을 수단이 없다.**
  손절이 게이트 판정을 뒤집는 칸이 있는지 알 수 없다

**runner 는 이미 준비돼 있다.** `run_option_expiry_trading(cells, stop_levels)` 가
`cells` 를 인자로 받고 `EXPIRY_CELLS` 는 기본값일 뿐이다. 막고 있는 것은 CLI 뿐이며,
**필요한 것은 「후보 칸을 `ExpiryCell` 목록으로 만드는 함수」 하나**다.

**후보 목록을 하드코딩하지 않는 이유**: 손으로 26칸을 적으면 ① 시세를 재수집해 게이트 결과가
바뀌어도 목록이 따라오지 않고 ② 「왜 이 26칸인가」의 근거가 코드에서 사라져 사후 선택과
구별되지 않는다. `studies.option_expiry.runner.run_study()` 를 돌려 유도하면 둘 다 막힌다 —
**실측 2.57초**라 매 실행마다 불러도 부담이 없다 (2026-09-15).

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「측정의 원칙」·「후보 판정 기준」·「계획서 규약 — 이 프로젝트의 설정」 절
- `.claude/rules/trading.md` — 매매 계층의 예외 규정과 제약, 손절 격자 절차, 성적표 규격
- `src/verify_lab/CLAUDE.md` — 계층 간 의존 방향, 「매매 산출물 계약」, 「매매 계층 구성 계약」
- `scripts/CLAUDE.md` — CLI 계층 책임, 명령행 인자 정책, 메타 타입 목록
- `tests/CLAUDE.md` — 테스트 작성 규칙
- `~/.claude/rules/python.md` (전역) — 코딩 표준·반올림·로깅

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [ ] 기능 요구사항 충족 — 1차 게이트 통과 칸(금요일 청산)에 손절선 격자를 걸어
      매매 성적표 규격으로 산출된다
- [ ] 후보 목록이 `measure/screening.py` 게이트에서 유도되고 **하드코딩이 없다**
- [ ] 기존 기본 실행(7칸 · −5%)의 산출물이 **바이트 단위로 같다** (git diff 로 확인)
- [ ] 회귀/신규 테스트 추가
- [ ] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [ ] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [ ] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [ ] 필요한 문서 업데이트(`docs/COMMANDS.md` / `scripts/CLAUDE.md` / plan — 각각 변경 여부 명시)
- [ ] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 근거·실측 수치를 루트 `CLAUDE.md` 의 프로젝트 설정 절이 정한 목적지로 이관)
- [ ] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/studies/option_expiry/trading.py` — `candidate_cells()` 추가 (신규 함수 하나)
- `scripts/run_option_expiry.py` — `--candidates` 플래그 추가
- `tests/test_strategy_option_expiry_runner.py` — **신규 파일**.
  이웃(`test_strategy_month_end_runner.py` · `test_strategy_reverse_runner.py`)을 먼저 열어
  그 폴더의 관용(네이밍·픽스처·Given-When-Then)을 확인한 뒤 만든다
- `docs/COMMANDS.md`: **변경 있음** — 「옵션 만기일 매매 — 손절 격자」 절에 `--candidates` 추가
- `scripts/CLAUDE.md`: **변경 있음** — 메타 타입 `option_expiry_trading` 의 기록 내용에
  대상 선택 방식이 더해지면 그 줄을 갱신한다 (실제 변경 여부는 Phase 2 에서 확정)
- `src/verify_lab/studies/option_expiry/constants.py`: **변경 없음** — `EXPIRY_CELLS` 는 그대로 둔다

### 데이터/결과 영향

- **출력 스키마 변경 없음.** 성적표 24컬럼·거래내역 12컬럼이 그대로다.
  `--candidates` 는 **행 수만** 늘린다 (7칸 → 26칸)
- 🔴 **산출물 폴더가 하나라 재실행이 그 자리를 덮는다.**
  `storage/results/매매/option_expiry/` 는 쓰기 전에 비워지고,
  `--grid` 는 `성적표.csv` 대신 `손절선_격자.csv` 를 낸다 —
  **둘은 공존하지 못한다** (`.claude/rules/session-bootstrap.md` 6절 · `docs/MEMORY.md`).
  현재 폴더는 git clean 이므로 `git checkout` 으로 복원된다
- **기존 7칸 실행의 값은 달라지지 않아야 한다.** 같은 시세·같은 코드 경로이므로
  git diff 가 0 인 것으로 확인한다

## 6) 단계별 계획(Phases)

### Phase 0 — 후보 칸 변환 정책을 테스트로 먼저 고정(레드)

> 이 Phase 를 두는 이유: **최종 결과(어느 칸이 성적표에 실리는가)가 이 변환에 달려 있다.**
> 종목명 → 데이터셋 이름 역매핑이 조용히 빗나가거나 목요일 청산이 섞이면
> **예외 없이 엉뚱한 칸의 성적이 나온다.**

**작업 내용**:

- [ ] `tests/CLAUDE.md` 와 이웃 테스트 두 개를 `Read` 도구로 열어 관용을 확인한다
- [ ] **변환을 순수 함수로 갈라 테스트가 실제 시세에 의존하지 않게 한다**
      — `cells_from_candidates(candidates: pd.DataFrame)` 는 표만 받아 변환하고,
      `candidate_cells()` 가 `run_study()` 를 돌려 그것을 부른다.
      **가르지 않으면 이 테스트가 시세 4파일을 읽어야 하고**, 그러면 시세를 재수집할 때
      테스트가 함께 흔들려 「코드가 깨진 것」과 「데이터가 바뀐 것」이 구별되지 않는다
- [ ] `cells_from_candidates()` 의 계약을 **합성 표**로 테스트해 고정한다 (레드 허용)
  - [ ] 게이트를 통과한 칸만 돌려준다 (`1차 판정 == 후보`)
  - [ ] **금요일 청산만 돌려준다** — 목요일 청산 행은 제외된다
  - [ ] `방향 == 아래` 가 `bet_down=True` 로 매핑된다
  - [ ] 종목 표시 이름이 `DATASETS` 의 `key` 로 역매핑된다 (`KODEX 200` → `kodex200`)
  - [ ] 알 수 없는 종목명이 오면 조용히 건너뛰지 않고 예외를 던진다
        (`RuntimeError` — 내부 불변조건 위반. 조용히 빠지면 칸이 사라져도 아무 신호가 없다)
  - [ ] 후보가 하나도 없으면 빈 목록이 아니라 예외를 던진다
        (runner 가 빈 `cells` 를 이미 `ValueError` 로 거부하므로 그 자리에서 뜻이 드러나야 한다)

---

### Phase 1 — `candidate_cells()` 구현(그린 유지)

**작업 내용**:

- [ ] `strategy/option_expiry_runner.py` 에 함수 **둘**을 추가한다
  - [ ] `cells_from_candidates(candidates)` — 표만 받는 **순수 변환**
    - [ ] `COL_SCREEN == SCREEN_CANDIDATE` 이고 청산 요일이 금요일인 행만 고른다
    - [ ] `COL_TICKER`(표시 이름) → `Dataset.key` 역매핑, `COL_DIRECTION` → `bet_down`,
          `COL_EXPIRY_MONTH_NUMBER` → `expiry_month` 로 `ExpiryCell` 을 만든다
    - [ ] 종목 → 만기월 오름차순 등 **결정적 순서**로 돌려준다 —
          순서가 흔들리면 산출물 diff 가 「숫자가 바뀌었는가」를 말해 주지 못한다
  - [ ] `candidate_cells()` — `studies.option_expiry.runner.run_study()` 를 돌려 위 함수에 넘긴다
        (이 모듈은 이미 `studies.option_expiry` 를 import 하므로 계층 방향에 맞다)
- [ ] Phase 0 테스트가 전부 통과하는지 확인한다
- [ ] 주석은 「왜」만 적는다 — 왜 하드코딩하지 않는지, 왜 금요일만인지

**Validation**:

- [ ] `poetry run pytest tests/test_strategy_option_expiry_runner.py` 통과

---

### Phase 2 — CLI `--candidates` 플래그(그린 유지)

**작업 내용**:

- [ ] `scripts/run_option_expiry.py` 에 `--candidates` 플래그를 추가한다
  - [ ] 기본값은 지금 그대로(`EXPIRY_CELLS`)여야 한다 — 인자 없이 돌리면 기존 동작
  - [ ] `--ticker` 와의 조합 규칙을 정하고 `_selected_cells` 에 반영한다
        (`--candidates` 로 얻은 목록에도 종목 필터가 걸리게)
  - [ ] `_print_scope` 가 무엇을 도는지(칸 수·출처)를 먼저 보여 준다
  - [ ] **도메인 로직을 CLI 에 두지 않는다** — 변환은 Phase 1 의 함수가 하고 CLI 는 부르기만 한다
- [ ] 실제로 돌려 확인한다 (`scripts/` 는 테스트 대상이 아니므로 실행이 유일한 검증이다)
  - [ ] `--candidates --grid` 로 26칸 × 20손절선 × 5시기 = **2,600행**이 나오는지
  - [ ] 인자 없이 돌려 기존 7칸 산출물이 **git diff 0** 으로 복원되는지

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [ ] `docs/COMMANDS.md` 의 「옵션 만기일 매매 — 손절 격자」 절에 `--candidates` 를 추가한다
      (대상 선택 방식과 **산출물이 같은 자리를 덮는다는 경고**를 함께)
- [ ] `scripts/CLAUDE.md` 메타 타입 줄 갱신 여부를 확정하고 필요하면 고친다
- [ ] 근거 승격 — 아래를 살아있는 문서로 옮긴다
  - [ ] **매매 계층이 금요일 청산만 지원한다는 제약과 그 이유** → `docs/매매/옵션_만기일/설계.md`
        「확정된 설계 결정」 (확정 / 탈락안 / 근거 형식)
  - [ ] **26칸 격자의 측정 결과** → `docs/매매/옵션_만기일/규칙.md` §3.1
        (데이터 기간을 함께 적는다 — `.claude/rules/docs.md` 「수치를 적을 때는 데이터 기간을 함께 적는다」)
- [ ] 자동 포맷 적용 (`poetry run black .`)
- [ ] 변경 기능 및 전체 플로우 최종 검증
- [ ] 🔴 **`/commit` 을 실행하고 그 후보를 «이 계획서» 의 `#### Commit Messages` 절에 옮긴다** —
      `/commit` 은 계획서를 모르고 「후보 뒤에 아무것도 덧붙이지 말 것」으로 끝나므로,
      **대화에만 내면 그 절이 빈 채로 남는다**
- [ ] DoD 체크리스트 최종 업데이트 및 체크 완료
- [ ] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

> 순서를 지킨다 — 리뷰에서 고치면 코드가 바뀌므로 품질 검증이 마지막 관문이어야 한다.

- [ ] `/code-review xhigh` (발견 \_\_건 · 조치: \_\_)
- [ ] `poetry run python validate_project.py` (passed=\_\_, failed=\_\_, skipped=\_\_)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다.**
> 계획서를 쓰는 시점에는 diff 가 없어 여기 적는 것은 전부 추측이고,
> **추측으로 적은 줄은 그대로 나간다.** 형식·문체 규칙은 `/commit` 이 정한다.

- [ ] (미작성 — `/commit` 을 실행하고 후보 5개를 **이 자리에** 번호 붙은 줄로 옮긴 뒤 이 줄을 지운다)

## 7) 리스크(Risks)

| 리스크 | 완화책 |
| --- | --- |
| **산출물 폴더를 덮어 기존 7칸 성적표가 사라진다** | 현재 폴더는 git clean 이라 `git checkout` 으로 복원된다. 작업 끝에 기본값으로 다시 돌려 diff 0 을 확인한다 |
| **`--candidates` 가 「좋아 보이는 칸 고르기」로 오독된다** | 게이트에서 유도하므로 사람이 고르는 자리가 없다. `EXPIRY_CELLS` 를 바꾸지 않는 것이 이 구분을 지킨다 |
| **후보 26칸은 60칸에서 나온 사후 선택이라는 사실이 흐려진다** | 산출물은 「볼 목록」이지 「우위 증명」이 아니다. 결과 보고에 60칸 중 26칸이라는 분모를 함께 적는다 |
| **미국 9월 세 칸은 독립 표본이 아니다** | 이미 CLI 가 경고를 찍는다. 26칸으로 늘면 겹치는 칸이 더 생기므로 보고에 명시한다 |
| **`run_study()` 를 매번 도는 비용** | 실측 2.57초. 저장은 하지 않으므로 검증 산출물을 덮지 않는다 |

## 8) 메모(Notes)

### 확인된 사실 (2026-09-15 실측)

- 검증 재실행 `git diff` **0** — 커밋된 산출물과 바이트 단위 동일
- 데이터 기간: QQQ 1999-03-10~2026-09-03 (6,915행) · SPY 1993-01-29~2026-08-25 (8,450) ·
  DIA 1998-01-20~2026-08-26 (7,195) · KODEX 200 2002-10-14~2026-09-04 (5,898)
- 60칸 판정: **후보 31 · 제외 29.** 금요일 청산만 보면 48칸 중 **26칸** (문서 §1.1 과 일치)
- 목요일 청산 후보 5칸: KODEX 200 의 1·3·4·7·9월 — **매매 계층이 낼 수 없다**
- 적중률 60% 이상인데 기대값이 음수라 떨어진 칸 둘: QQQ 7월(60.71% · −0.03%) ·
  SPY 3월(64.71% · −0.31%). **게이트를 둘로 둔 이유의 실물**
- `run_study()` 소요 **2.57초**

### 진행 로그 (KST)

- 2026-09-15 16:09: 계획서 작성. 검증 계층 전 칸 실행과 제약 조사를 마친 상태에서 시작

---
