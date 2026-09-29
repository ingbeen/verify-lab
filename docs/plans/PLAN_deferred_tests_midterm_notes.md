# Implementation Plan: 미룬 지적 처리 — 계약 테스트 보강 여섯 곳과 중간선거 `notes` 세 곳

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

**작성일**: 2026-09-29 11:20
**마지막 업데이트**: 2026-09-29 11:43
**관련 범위**: tests · studies/midterm_cycle(`trading.py` 의 `notes` 조립 조건과 문구) · 기본 산출물 `summary.json` · 결과 문서 재실행 기록 · 미룬 지적 파일
**관련 문서**: tests/CLAUDE.md, src/verify_lab/CLAUDE.md, scripts/CLAUDE.md, docs/MEMORY.md, .claude/rules/docs.md, .claude/rules/research.md

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

- [x] 목표 1: 지수만 돈 격자 실행에는 `NOTE_STOP_BASE`(「갭 청산은 손절선보다 더 잃는다」)를 싣지 않는다
- [x] 목표 2: 손절선 스위치에 따른 `notes` 차이와 `NOTE_STOP_BASE` 의 자리를 테스트로 고정한다
- [x] 목표 3: `NOTE_STOP_CONFIRMED` 가 「1배 측정 기준은 대상 QQQ 의 무손절 행 · 규칙이 사는 QLD 의 성적은 이 산출물에 없음」을 말한다
- [x] 목표 4: 게이트 소유 검사가 `scripts/` 까지 보고, 허용은 «파일 × 이름» 단위다
- [x] 목표 5: 성적 산식이 게이트를 «부르는지»를 소스 문자열이 아니라 AST 의 호출 노드로 본다
- [x] 목표 6: 공유 계약 테스트가 제외 건수 키를 매매법 상수에서 빌리지 않고 손으로 적는다
- [x] 목표 7: 논리적으로 함의되는 중복 테스트 `test_매매법_성적표의_공통_부분이_완전히_같다` 를 지운다
- [x] 목표 8: `Dataset.ticker` 가 종목코드 모양인지 본다 — 표시 이름이 들어가면 실패한다
- [x] 목표 9: 실행 요약 `row_counts` 에 성적표 키가 있는지 본다

## 2) 비목표(Non-Goals)

- **미룬 지적 중 버리기로 한 10건** (2026-09-29 사용자 결정) — 리터럴로 다시 쓴 게이트 검출 · `extra_surges` 범위 가드 ·
  순위 컷 신호 수 고정 · AST 헬퍼 통합 · 격자 실행을 「매매법 전부」 계약에 넣기 · 공유 계약 픽스처를 합성 성적표로 옮기기 ·
  격자 범위 문구를 상수에서 유도 · −10% 경계 주석 · 「두 매매법 모두」 제목 · `trading.md` 과거형
- **주석·문서로 끝나는 7건** — 이 계획서 «전»에 주석 수정 예외로 직접 고쳤다
- 게이트 값 · 판정 산식 · 측정과 체결의 수치는 바꾸지 않는다
- 숫자 리터럴이나 다른 이름으로 다시 쓴 게이트는 이 계획서 뒤에도 못 잡는다 — 리터럴 `0.01` 이 게이트 밖 3개 파일
  (`measure/distribution.py` · `studies/leverage_tracking/constants.py` · `studies/usdkrw_equivalence/constants.py`)에도 있어
  리터럴로 잡으면 오탐이 나므로 버린 지적이다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

출처는 `docs/DEFERRED_FINDINGS.md` 의 항목 9건이다(원래 계획서 PLAN_test_contract_gaps · PLAN_midterm_qld_no_stop_grid 의 리뷰).
**2026-09-29 에 전부 지금 코드에서 재현했다** — 저장소를 스크래치에 복사한 사본에서 프로덕션 코드를 변형하고 테스트를 돌린 뒤
원본으로 되돌렸다. 사본의 기본 테스트는 1257건 통과였고, 사본의 기본 실행 산출물은 작업 트리 산출물과 바이트 동일했다.

| 지적 | 재현 (사본에서 변형) | 커밋된 산출물에서 발동 |
| --- | --- | --- |
| 지수만 돈 격자에 `NOTE_STOP_BASE` | 사본에서 `--ticker GSPC --stop-grid` 를 돌리면 `rule.stop_levels` 가 `손절불가` 하나인데 `notes` 에 그 문구가 실린다. 바로 위 주석 「가격 손절선을 돈 실행에만 싣는다」와 어긋난다 | 아니오 — 기본 실행에는 없다 |
| 스위치별 `notes` 테스트 없음 | `NOTE_STOP_CONFIRMED` 조립을 빼도, `NOTE_STOP_BASE` 를 `NOTE_SAMPLE` 뒤로 옮겨도 **전체 1257건 통과**. 결과 문서 재실행 기록(2026-09-29)의 「`--stop-grid` 로 돌리면 좁히기 전 산출물과 `summary.json` 까지 바이트 단위로 같다」가 조용히 거짓이 될 수 있다 | 아니오 — 기본(작업 트리) · 격자 · 지수 격자(사본) 세 벌의 `notes` 가 지금은 맞다 |
| `NOTE_STOP_CONFIRMED` 에 QLD 가 없다 | 기본 `summary.json` 에 「QLD」 0건. 1배 QQQ 보유 중 최악은 −22.78% 인데 규칙이 사는 QLD 는 2018 에 −41.95%(원시 시세로 다시 재도 −41.9547%) — 산출물만 여는 사람이 1배 무손절 행을 규칙의 성적으로 읽을 수 있다(위험을 작게 읽히는 쪽) | 해당 — 문구가 기본 산출물에 있다 |
| 게이트 소유 검사가 `scripts/` 를 안 본다 | `scripts/run_midterm_cycle.py` 가 `MIN_EXPECTED_VALUE` 로 후보를 직접 거르게 바꿔도 `TestSingleOwner` 2건 통과. 지금 `scripts/` 에서 게이트 이름을 쓰는 곳은 그 파일의 `SCREEN_CANDIDATE` 하나 — 판정을 다시 하지 않고 판정 값으로 화면에 띄울 행을 고르는 정당한 사용이다. `scripts/` 에 문자열 「후보」 상수는 0건 | 아니오 |
| 게이트 호출을 소스 문자열로 본다 | `periods.py` 의 `screen_verdict(...)` 호출을 지우고 주석에만 `screen_verdict(` 를 남기면 그 테스트가 통과한다(호출을 그냥 지우면 `TestScreenColumn` 3건이 잡는다). 같은 값을 내는 재구현(리터럴 비교 + `"후" + "보"`)으로 바꾸면 **전체 1257건 통과** | 아니오 |
| 제외 건수 키를 빌려 온다 | 중간선거 `KEY_EXCLUDED_COUNT` 를 `"excluded_n"` 으로 바꾸면 **틀린 중간선거는 통과하고 맞는 역방향이 실패**한다. 두 매매법이 함께 바꾸면 조용히 통과. 계약(`src/verify_lab/CLAUDE.md` 「매매 산출물 계약」)은 키 이름 자체를 `excluded_count` 로 정한다 | 아니오 |
| 중복 검사 | 공통 컬럼과 매매법 축·꼬리의 교집합이 0 이라, 바로 위 매개변수화 테스트가 통과하면 이 테스트는 반드시 통과한다 | — |
| `ticker` 에 표시 이름이 들어가도 통과 | 역방향 KODEX 200 의 `ticker` 를 `"KODEX 200"` 으로 바꿔도 **전체 1257건 통과** — 그 테스트의 docstring 이 막겠다고 한 바로 그 사고다. 미국 ETF 는 코드와 이름이 같아(`QQQ`) 「서로 다르다」를 단언할 수 없다 | 아니오 |
| `row_counts` 에 성적표 키가 없어도 통과 | 역방향 `row_counts` 에서 `SUMMARY_FILENAME` 을 빼도 **전체 1257건 통과**. 스크립트가 행 수 표에서 한 줄을 조용히 빠뜨린다 | 아니오 |

**글자 규칙 점검** (`/impl-plan` 「글자 규칙이 막거나 되돌릴 수 없는 결과에 물리면」) — 목표 8 의 모양 검사(`[0-9A-Z]+` 전체 일치)가
해당한다. 입력은 열린 산문이 아니라 이 저장소의 `DATASETS` 상수이고 결과는 테스트 실패(되돌릴 수 있음)다. 저장소의 실제
종목코드 전부에 돌렸다 — `studies/*/constants.py` 의 9개(QQQ · 069500 · SPY · DIA · QQQ · GSPC · IXIC · 261240 · 261250) **전부 통과,
걸린 것 0 · 오탐 0**. 탈출구는 Risks 에 있다.

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- `.claude/plan-config.json` — 이 저장소의 검증 명령·자동 포맷·근거 승격 목적지 (**값의 SoT**)
- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절 (값이 아니라 **판단 근거**)
- `tests/CLAUDE.md` — 특히 「테스트 보강」 · 「픽스처가 코드와 같은 가정을 하면 그 버그는 영원히 안 잡힙니다」
- `src/verify_lab/CLAUDE.md` — 「매매 산출물 계약」 · 「실행 요약(`summary.json`)도 같은 틀을 씁니다」 · 「데이터 저장 규칙」
- `docs/MEMORY.md` — 「공유 계층의 테스트는 «자기 픽스처»를 갖는다」 · 「이름만 바꾸는 변경과 값을 바꾸는 변경을 한 커밋에 섞지 않는다」
- `.claude/rules/docs.md` · `.claude/rules/research.md` — 결과 문서의 재실행 기록

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 목표 1 ~ 9 충족
- [x] 보강·신규 테스트마다 변형으로 실패를 확인했다 (변형과 실패 메시지를 진행 로그에)
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 문서 업데이트 — 결과 문서 재실행 기록 한 행 · `docs/COMMANDS.md` 변경 없음 · CLAUDE.md 변경 없음
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 근거·실측 수치를 `.claude/plan-config.json` 의 `evidence_home` 이 정한 폴더로 이관.
      `/impl-plan` 스킬 "근거 승격" 참고)
- [x] 미룬 지적 옮김 — 고치지 않은 리뷰 지적을 추려 `deferred_findings` 파일로 옮겼다. 계획서 없이 읽히게 썼다.
      이 계획서가 그 파일의 항목을 고쳤다면 그 항목을 지웠다
      (둘 다 없으면 「해당 없음」. `/impl-plan` 스킬 "미룬 지적 옮기기" 참고)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/studies/midterm_cycle/trading.py` — `notes` 조립의 `NOTE_STOP_BASE` 조건 한 줄 · `NOTE_STOP_CONFIRMED` 문구
- `tests/test_studies_midterm_cycle_trading.py` — `notes` 테스트 (모듈 docstring 의 계약 표에 한 행)
- `tests/test_measure_screening.py` — `TestSingleOwner` (스캔 범위 · 허용 목록 구조 · 호출 검사)
- `tests/test_output_contract.py` — 제외 건수 키 상수 · 중복 테스트 삭제 · `ticker` 모양 · `row_counts` 성적표 키
- `storage/results/매매/중간선거_사이클/summary.json` — 기본 실행 재실행
- `docs/매매/중간선거_사이클/결과.md` — 재실행 기록 한 행
- `docs/DEFERRED_FINDINGS.md` — 이 계획서가 맡은 9건을 Done 때 지운다
- `docs/COMMANDS.md`: 변경 없음 — 실행 명령어와 CLI 옵션이 그대로다

### 데이터/결과 영향

- **기본 산출물**: `summary.json` 의 `notes` 중 `NOTE_STOP_CONFIRMED` 한 줄만 바뀐다. CSV 여덟 개는 바이트 불변이어야 한다
- **`--stop-grid` 전체 대상**: 바이트 불변이어야 한다 — `NOTE_STOP_CONFIRMED` 가 실리지 않고, ETF 가 있어 `NOTE_STOP_BASE` 조건이 그대로 참이다
- **지수만 돈 격자 실행**: `notes` 에서 `NOTE_STOP_BASE` 가 빠진다 (의도한 변화, 커밋되는 산출물이 아니다)
- 성적 · 판정 · 측정 값은 바뀌지 않는다

## 6) 단계별 계획(Phases)

### Phase 0 — 지수만 돈 격자 실행의 `notes` 를 테스트로 먼저 고정(레드)

**작업 내용**:

- [x] `tests/test_studies_midterm_cycle_trading.py` 에 테스트 추가: 합성 지수만 `stop_grid=True` 로 돌리면 `summary[KEY_NOTES]` 에 `NOTE_STOP_BASE` 가 없다
- [x] 지금 코드에서 **실패**를 확인하고 실패 메시지를 진행 로그에 적는다

**Validation**: `poetry run pytest tests/test_studies_midterm_cycle_trading.py` — 새 테스트 1건만 실패

---

### Phase 1 — 중간선거 `notes` (그린 유지)

**작업 내용**:

- [x] `trading.py` 의 `if stop_grid:` 를 `if stop_grid and any(not dataset.is_index for dataset in datasets):` 로 — **자리(`NOTE_SAMPLE` 앞)는 그대로 둔다.** Phase 0 테스트 통과
- [x] `notes` 테스트 셋을 더한다 (합성 ETF · 지수 픽스처 그대로)
  - ① 기본 실행은 `NOTE_STOP_CONFIRMED` 가 있고 `NOTE_STOP_BASE` 가 없다 · 격자 실행은 그 반대다
  - ② 스위치는 손절 문구 하나만 바꾼다 — 그 문구를 뺀 나머지 `notes` 는 두 실행에서 순서까지 같다
  - ③ 격자 실행의 `NOTE_STOP_BASE` 는 `NOTE_SAMPLE` 바로 앞이다 — 좁히기 전 산출물과 `summary.json` 까지 바이트 동일을 지키는 자리
- [x] **변형 확인** — 스크래치 사본에서 프로덕션을 변형한다(작업 트리의 프로덕션 파일은 변형하지 않는다)
  - (a) `NOTE_STOP_CONFIRMED` 조립 제거 → ① 실패
  - (b) `NOTE_STOP_BASE` 를 `NOTE_SAMPLE` 뒤로 → ③ 실패
  - (c) 조건을 `if stop_grid:` 로 되돌림 → Phase 0 테스트 실패
- [x] `NOTE_STOP_CONFIRMED` 문구에 「확정 규칙의 1배 측정 기준은 대상 QQQ 의 무손절 행이고, 규칙이 사는 2배 상품(QLD)의 성적은
      이 산출물에 없다(`docs/매매/중간선거_사이클/규칙.md` §2.5)」를 더하고, 같은 문자열의 「냈다」를 현재형 「낸다」로 바꾼다
- [x] **기본 실행 재실행** — 재실행 «전»에 `storage/results/매매/중간선거_사이클/` 를 스크래치에 복사 →
      `poetry run python scripts/run_midterm_cycle.py` → `diff -r` 로 **`summary.json` 의 그 한 줄만** 바뀌었는지 본다.
      그 밖의 차이가 나오면 멈추고 보고한다
- [x] 격자 실행 두 벌은 **사본에서** 돌린다 — 전체 대상 격자는 조사 때 사본에서 낸 산출물과 바이트 동일, 지수만 돈 격자는 `NOTE_STOP_BASE` 만 빠졌는지
- [x] `docs/매매/중간선거_사이클/결과.md` 재실행 기록에 한 행 — 무엇(문구)과 영향(`summary.json` 한 줄 · CSV 불변 · 격자 실행 바이트 불변)

**Validation**: `poetry run pytest tests/test_studies_midterm_cycle_trading.py tests/test_output_contract.py` 통과

---

### Phase 2 — 계약 테스트 보강 (그린 유지)

**작업 내용**:

- [x] `TestSingleOwner` — 스캔을 `src/verify_lab` 와 `scripts/` 로 넓히고 경로를 저장소 루트 기준으로 적는다. 허용 목록을
      「파일 → 쓸 수 있는 이름」 사전으로 바꾼다 — 정의 파일은 네 가지 전부, `scripts/run_midterm_cycle.py` 는 `SCREEN_CANDIDATE` 하나
      (이유 주석: 판정을 다시 하지 않고 판정 값으로 화면에 띄울 행을 고른다). 정의 파일이 네 가지를 전부 쓰는지 보는 검사는 유지한다.
      두 테스트의 docstring 에 적힌 범위(「`src` 전체」)를 함께 고친다
- [x] `test_성적_산식_계층이_이_게이트를_쓴다` — `"screen_verdict(" in source` 를 AST 의 호출 노드(함수가 이름 또는 속성 `screen_verdict`)로 바꾼다. `MIN_HIT_RATE` 부재 검사는 그대로 둔다
- [x] `tests/test_output_contract.py` — `KEY_EXCLUDED_COUNT` import 를 지우고 `"excluded_count"` 를 손으로 적은 상수로 쓴다
      (근거 주석: 계약이 키 이름 자체를 정한다 · 파일 머리의 「기대 컬럼 목록을 손으로 박아 둔다」)
- [x] `test_매매법_성적표의_공통_부분이_완전히_같다` 를 지운다 — 미사용이 되는 이름이 없는지 확인한다
- [x] `test_Dataset_이_코드와_이름을_따로_갖는다` — `ticker` 가 `[0-9A-Z]+` 에 전체 일치하는지 단언하고, docstring 의 Then 을 실제 단언과 맞춘다
      (미국 ETF 는 코드와 이름이 같아 「서로 다르다」를 단언하지 않는다는 이유를 함께 적는다)
- [x] `test_row_counts_의_키가_파일_이름이다` — `SUMMARY_FILENAME in counts` 단언을 더한다
- [x] **변형 확인** — 스크래치 사본에서
  - (a) `scripts/run_midterm_cycle.py` 가 `MIN_EXPECTED_VALUE` 로 후보를 거름 → `TestSingleOwner` 실패
  - (b) `scripts/run_reverse.py` 가 `SCREEN_CANDIDATE` 를 가져옴 → `TestSingleOwner` 실패
  - (c) `periods.py` 의 호출을 지우고 주석에만 남김 → 호출 검사 실패
  - (d) 중간선거 `KEY_EXCLUDED_COUNT` 를 `"excluded_n"` 으로 → 중간선거 칸이 실패
  - (e) 역방향 KODEX 200 의 `ticker` 를 `"KODEX 200"` 으로 → 모양 검사 실패
  - (f) 역방향 `row_counts` 에서 성적표 키 제거 → 실패

**Validation**: `poetry run pytest tests/test_measure_screening.py tests/test_output_contract.py` 통과

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

> 🔴 **`/commit` 이 «맨 마지막»인 것은 의도다.** 그 스킬은 「후보 뒤에는 아무것도 덧붙이지 말 것」으로
> 끝나므로 **호출하는 순간 그 턴이 거기서 닫힌다.** 중간에 두면 뒤에 적힌 항목이 그 벽 너머에 남는다 —
> 실제로 두 번 그렇게 샜다(`[실측] 2026-09-14` 후보를 계획서에 안 옮김 · `2026-09-16` 옮기고 체크박스를 안 닫음).
> **체크박스와 상태를 먼저 확정하고, 커밋 후보를 마지막에 만든다.**

- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` 변경 없음)
- [x] 자동 포맷 적용 (`poetry run black .`)
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] Validation 절에 `/code-review` 와 품질 검증 **실행 결과**를 적는다
- [x] 근거 승격 — 결정 근거는 테스트의 주석·docstring 과 결과 문서 재실행 기록이 갖는다. 계획서에만 남은 것이 없는지 본다
- [x] 미룬 지적 옮김 · `docs/DEFERRED_FINDINGS.md` 에서 이 계획서가 맡은 9건을 지운다
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정
- [x] 🔴 **마지막에 `/commit` 을 실행하고 그 후보를 «이 계획서» 의 `#### Commit Messages` 절에 옮긴다** —
      `/commit` 은 계획서를 모르고 「후보 뒤에 아무것도 덧붙이지 말 것」으로 끝나므로,
      **대화에만 내면 그 절이 빈 채로 남는다.** 체크박스 갱신이 diff 에 더 들어가지만
      커밋 메시지의 내용을 바꾸지 않는다. **커밋은 사용자가 한다 — 후보만 낸다**

**Validation**:

> 순서를 지킨다 — 리뷰에서 고치면 코드가 바뀌므로 품질 검증이 마지막 관문이어야 한다.
> **고칠 것이 0 인 회차에서 끝낸다** — 고칠 것은 무거운 버그 전부와, 실제 산출물에 나오는 가벼운 버그다.
> 2회차에도 무거운 버그가 나오면 사용자에게 보고하고 3회차 여부를 묻는다 — 나머지 가벼운 버그와
> 「그 외」는 목록만 남기고 고치지 않는다. 무게의 정의는 `/impl-plan` 의 「코드 리뷰」 절이 SoT 다.
> **뒤에 리뷰 회차가 오지 않는 수정은 고치기 «전»에 바꿀 파일을 스크래치에 복사해 두고, 고친 뒤 수정분 검증을
> 거친다** — 절차는 `/impl-plan` 의 「지적을 고칠 때」다.

- [x] `/code-review xhigh` **1회차** (발견 10건 — 버그 4 [무거움 0 · 가벼움 4] · 그 외 6 · 조치: 없음 — 고칠 것 0 이라 1회차에서 끝내고 10건 전부 미룬 지적으로 옮겼다)
  - 가벼움(목록만 — 실제 산출물 세 벌과 지금의 `periods.py` 에서 발동 0) — 손절 문구를 입력 플래그로 고르고 확정 칸이 무손절이라는 사실을 문구에 박음 · `NOTE_STOP_CONFIRMED` 가 대상 · 상품 · 절 번호 · 문서 경로를 박고 `--ticker SPY` 에도 실림 · `_called_names` 가 같은 이름의 지역 함수도 호출로 셈 · 순서 테스트가 두 문구의 짝째 이동을 못 잡고 맨 끝이면 `IndexError`
  - 그 외(목록만) — `NOTE_STOP_CONFIRMED` 내용 테스트 없음 · 결과 문서 한 줄 요약의 QLD 수치에 머리말 데이터 기간 없음 · `trading.md` 에 측정값 −41.95% 가 두 벌 · 격자 실행 `notes` 에 QLD 경고 없음 · ETF 존재 판정 두 번 계산 · `offenders` 의 차집합 두 번 계산
- [x] 수정분 검증 — 해당 없음 (1회차에 고친 것이 없다)
- [x] `poetry run python validate_project.py` (passed=1260, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다.**
> 계획서를 쓰는 시점에는 diff 가 없어 여기 적는 것은 전부 추측이고,
> **추측으로 적은 줄은 그대로 나간다.** 형식·문체 규칙은 `/commit` 이 정한다.

1. `테스트 / 미룬 지적 처리 — 계약 테스트 여섯 곳 보강과 중간선거 notes 정정`
2. `테스트 / 미룬 지적 26건 판정(수정 16 · 폐기 10)과 리뷰 신규 지적 10건 등록`
3. `테스트 / 게이트 소유 검사의 scripts 확장·이름 단위 허용, 게이트 호출 AST 판정, 제외 건수 키 고정, ticker 모양·성적표 행 수 검사, 중복 테스트 삭제`
4. `테스트 / 결함이 들어와도 통과하던 계약 테스트의 변형 검증 기반 보강과 지수 격자 실행의 가격 손절 설명 제외`
5. `테스트 / 중간선거 summary.json 의 QLD 성적 부재 명시와 1배 측정 기준 한정어 보강 및 notes 스위치 테스트 추가`

## 7) 리스크(Risks)

- **기본 산출물 `summary.json` 이 바뀐다** — 재실행 전 사본과 `diff -r` 로 그 한 줄만인지 확인한다. 시세 재수집 등 다른 차이가 나오면 멈추고 보고한다
- **`ticker` 모양 규칙이 앞으로 들어올 종목코드를 막을 수 있다**(예: `BRK.B`) — 패턴은 테스트 상수라 넓힐 수 있고, 넓힐 때 그 종목과 이유를 주석에 적는다. 실패 메시지가 어느 매매법의 어느 값인지 말하게 한다
- **허용 목록을 이름 단위로 두면** 새 스크립트가 판정 값을 정당하게 쓸 때마다 목록에 더해야 한다 — 실패 메시지가 파일과 이름을 말하게 하고, 목록 위 주석이 「이유를 달아 더한다」를 말한다
- **`scripts/` 스캔이 `scripts/data/` 까지 본다** — 수집 스크립트가 문자열 「후보」 상수를 쓰면 걸린다. 지금 0건(2026-09-29 확인)
- **`/code-review` 는 미커밋 diff 전체를 본다** — 이 계획서 전에 직접 고친 주석·문서 7건과 미룬 지적 파일 정리를 **착수 전에 사용자가 커밋해 두면** 리뷰 범위가 이 계획서의 변경으로 좁아진다
- **git 명령을 쓰지 않는다** — `tests/CLAUDE.md` 「테스트 보강」의 「`git diff` 로 프로덕션 diff 0」은, 변형을 스크래치 사본에서만 하고 작업 트리의 프로덕션 파일을 변형하지 않는 것으로 갈음한다. 사본의 변형 파일은 매번 원본과 바이트 대조해 복원을 확인한다

## 8) 메모(Notes)

- **`NOTE_STOP_BASE` 조건을 `is_index` 로 가르는 이유** — 바로 아래 `NOTE_DIVIDEND` · `NOTE_STOP_CONFIRMED` 가 같은
  `any(not dataset.is_index for dataset in datasets)` 관용을 쓴다. 탈락안: 성적표에 실제로 나온 손절선(`stop_levels_run`)에
  숫자가 있는지로 가르기 — 표시값의 타입(`stop_level_value` 의 형식)에 기대게 된다
- **③ 테스트가 순서를 보는 이유** — 결과 문서와 설계 문서가 「`--stop-grid` 실행은 좁히기 전 산출물과 `summary.json` 까지
  바이트 동일」을 적어 두었고, 그 동일성은 `NOTE_STOP_BASE` 의 자리에 달려 있다. 전체 목록을 손으로 적지 않고 그 한 자리만 본다 —
  새 `notes` 가 더해질 때마다 테스트가 깨지지 않게 하려는 것이다
- 이 계획서 전에 한 일 (2026-09-29, 계획서 밖): 미룬 지적 26건 재현 · 사용자가 추천안 승인 · 버린 10건 삭제 · 주석·문서 7건 직접 수정
  (`validate_project.py` passed=1257 · failed=0 · skipped=0)

### 진행 로그 (KST)

- 2026-09-29 11:20: 계획서 작성 (Draft). 착수 전 사용자 승인 대기
- 2026-09-29 11:25: 사용자 승인 — 착수. 같은 메시지로 「계획서 전에 직접 고친 주석·문서 7건은 커밋하지 않고 두어 마지막 `/code-review` 가 함께 보게 한다」는 추천도 승인한 것으로 읽었다(Risks 의 「먼저 커밋」 대신)
- 2026-09-29 11:25 ~ 11:32 사이: Phase 0 — `TestStopNotes.test_index_only_grid_has_no_price_stop_note` 추가. 지금 코드에서 1 failed · 8 passed — `AssertionError: 지수만 돈 격자 실행에 가격 손절선 설명이 실렸습니다` (`notes` 에 「손절선은 진입가 기준이고 … 갭 청산은 손절선보다 더 잃는다」가 있다)
- 2026-09-29 11:32 이전: Phase 1 — 조건 수정으로 Phase 0 테스트 통과, `notes` 테스트 ①②③ 추가(`TestStopNotes` 4건 · 모듈 docstring 계약 표에 한 행). 사본 변형: (a) `NOTE_STOP_CONFIRMED` 조립 제거 → `test_switch_swaps_the_stop_note` 실패 `기본 실행에 확정 칸 문구가 없습니다` (b) `NOTE_STOP_BASE` 를 `NOTE_SAMPLE` 뒤로 → `test_price_stop_note_sits_right_before_the_sample_note` 실패 `가격 손절선 설명의 자리가 바뀌었습니다` (c) 조건을 `if stop_grid:` 로 → `test_index_only_grid_has_no_price_stop_note` 실패. 셋 다 1 failed · 3 passed, 복원 뒤 원본과 바이트 동일. 문구 수정 후 기본 실행 재실행 — 재실행 전 사본과 `diff -r`: `summary.json` 204행(그 문구) 한 줄만 다르고 CSV 여덟 개 동일. 사본의 `--stop-grid` 전체 대상은 조사 때 산출물과 바이트 동일, `--ticker GSPC --stop-grid` 는 `notes` 에서 `NOTE_STOP_BASE` 한 줄만 빠짐. 결과 문서 재실행 기록 한 행. `pytest tests/test_studies_midterm_cycle_trading.py tests/test_output_contract.py` → 79 passed
- 2026-09-29 11:32: 진행 로그의 Phase 0 · 1 시각을 바로잡았다 — 처음에 `date` 로 확인하지 않고 11:27 · 11:40 으로 적었고, 11:32 에 확인한 시각과 맞지 않았다
- 2026-09-29 11:32: Phase 2 — `TestSingleOwner`(스캔 `src/verify_lab` + `scripts/` · 허용 목록 «파일 → 이름» · 허용 목록 파일이 스캔되는지 · 호출 검사를 `_called_names` 로), `test_output_contract.py`(`EXCLUDED_COUNT_KEY` · `TICKER_SHAPE` · 중복 테스트 삭제와 그 사실을 남은 테스트 docstring 에 · `SUMMARY_FILENAME` 단언). `pytest tests/test_measure_screening.py tests/test_output_contract.py` → 81 passed. 사본 변형 여섯 — (a) `run_midterm_cycle.py` 에 `MIN_EXPECTED_VALUE` 비교 → `{'scripts/run_midterm_cycle.py': ['MIN_EXPECTED_VALUE']}` 로 실패 (b) `run_reverse.py` 에 `SCREEN_CANDIDATE` import → `{'scripts/run_reverse.py': ['SCREEN_CANDIDATE']}` 로 실패 (c) `periods.py` 호출 제거·주석만 → `성적 산식이 게이트를 부르지 않습니다` (d) 중간선거 키 `excluded_n` → **`[midterm_cycle]` 칸**이 `midterm_cycle 요약에 제외 건수가 없습니다` 로 실패(보강 전에는 역방향 칸이 실패했다) (e) KODEX 200 `ticker` → `'KODEX 200' 가 종목코드 모양이 아닙니다` (f) 역방향 `row_counts` 성적표 키 제거 → `reverse 에 성적표 행 수가 없습니다`. 여섯 다 복원 뒤 원본과 바이트 동일
- 2026-09-29 11:42: 마지막 Phase — `black` 적용(이번에 바꾼 테스트 두 파일만 다시 맞춰짐) · `/code-review xhigh` 1회차 발견 10건(무거움 0 · 가벼움 4 · 그 외 6). 가벼움 넷은 실제 산출물 세 벌(기본 · 격자 · 지수 격자)과 지금의 `periods.py` 에서 발동 0 이라 고칠 것 0 — 1회차에서 끝냈다. 10건 전부 `docs/DEFERRED_FINDINGS.md` 로 옮기고 이 계획서가 맡은 9건을 지웠다. 그 외 둘(결과 문서 한 줄 요약의 QLD 기간 · `trading.md` 의 −41.95%)은 계획서 전에 직접 고친 문장에서 나왔다. 근거 승격: 결정 근거는 테스트 주석·docstring(`GATE_OWNERS` 이름 단위 허용 · `EXCLUDED_COUNT_KEY` · `TICKER_SHAPE` · 순서 테스트의 이유)과 결과 문서 재실행 기록에 있고, `is_index` 로 가른 이유와 탈락안은 미룬 지적 항목에 옮겼다. 최종 `poetry run python validate_project.py` → passed=1260, failed=0, skipped=0 (착수 전 1257 + `TestStopNotes` 4 − 중복 테스트 1)

---
