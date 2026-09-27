# Implementation Plan: 경량화 ③ — 데드 코드 · 테스트 결함과 잔재 · 틀린 주석 정리 (산출물 바이트 불변)

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

**작성일**: 2026-09-26 16:55
**마지막 업데이트**: 2026-09-28 07:38
**관련 범위**: src(measure · report · execution · studies · data · tracks), scripts, tests, validate_project.py
**관련 문서**: `src/verify_lab/CLAUDE.md`, `scripts/CLAUDE.md`, `tests/CLAUDE.md`, `~/.claude/rules/python.md`, 루트 `SLIM_SERIES.md`, `docs/plans/AUDIT_slim_dead_code.md`, `docs/plans/AUDIT_slim_doc_code_mismatch.md`, `docs/plans/REPORT_lightweight_inventory.md` §2 · §12

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

- [x] 목표 1: 운영·테스트 어디서도 쓰지 않는 정의와, 결론이 난 축의 잔여물(월말 「방향 표」 계열 · 판정표 잔여)을 지운다
- [x] 목표 2: **무력화된 테스트**와 삭제 매매법 잔재, 공유 계층 테스트의 매매법 상수 의존, 중복 테스트를 고친다
- [x] 목표 3: 「연결 누락」 셋을 **쓰게 만든다** (`IDENTITY_COLUMNS` 둘 · `tracks_of_kind`)
- [x] 목표 4: 코드 주석·docstring·도움말의 틀린 서술(삭제 매매법 · 옛 `strategy/` 경로 · 「세 매매법」 · 과거형 · 버린 근거)을 현재형 사실로 고친다
- [x] 목표 5: 메타 타입 키를 `<slug>` 로 통일한다
- [x] 목표 6: **산출물이 한 바이트도 바뀌지 않는다** — 5개 실행 스크립트를 다시 돌려 `storage/results/` diff 0

## 2) 비목표(Non-Goals)

- **산출물이 바뀌는 변경 전부** — `NOTE_ALPHA`·`NOTE_TER`(계획서 ⑦), 중간선거 `측정.csv` 의 어긋남 열(⑤), `leverage_drift.csv` 반올림(전역 규칙 「돌아가는 산출물의 자릿수를 소급해 바꾸지 않는다」로 **하지 않는다**), 역방향 `excluded_by_stop` 한 칸짜리 사전의 구조 단순화(`summary.json` 모양이 바뀐다 — 주석만 고친다)
- **문서(`*.md`) 수정** — 계약 문서(`src/verify_lab/CLAUDE.md` 등)의 틀린 서술은 계획서 ④. 이 계획서는 코드 안의 주석·docstring·도움말만 고친다. 단, **지운 코드의 이름을 계약 문서가 가리키면** 그 한 줄은 여기서 고친다(죽은 이름을 남기지 않는다)
- **다른 계획서가 옮길 문서를 가리키는 코드 주석** — 달력 조사 문서(`docs/조사/{옵션_만기일,월말_진입,만기_말일}/…`)를 가리키는 주석은 계획서 ⑥, 원달러 그리드 설계·사양서를 가리키는 주석(등가성 코드 약 57줄)은 ⑦ 이 새 자리로 고친다. 여기서 고치면 두 번 고친다
- **설계 변경** — `measure/calendar_entry.py` 의 이름·위치(리뷰 R12), `_Accumulator` 과설계, 배수형 두 검증의 내부 컬럼 토큰 통합, `run_reverse.py` `_print_rule` 의 출처 이중화, `stop_levels`·`rank_cuts`·`start_years` 주입 인자(의도된 검사 입구 — 보고서 §2.6). 백로그에 남긴다
- **선물 검산 엔진**(`studies/futures_leverage/position.py` 의 `run_position` 외 9개) — 모듈 docstring 이 「본선은 부르지 않는다, 벡터화 경로의 검산 기준」이라 명시한 **의도된 테스트 전용 구현**이다. 지우지 않는다
- **레지스트리의 삭제 slug 4줄** (`tracks.py`) — 의도된 잔존(`tests/test_tracks.py` 가 고정)
- 테스트 파일 개명 — 계획서 ②에서 끝났다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

- 매매법 다섯(옵션_만기일 · 월말_진입 · 만기_말일 · 원달러_그리드 · 연속_등락)의 코드가 지워진 뒤 **그것들만 쓰던 정의·테스트·주석이 남았다.** 전수 스캔 결과가 `docs/plans/AUDIT_slim_dead_code.md`, 주석 불일치가 `docs/plans/AUDIT_slim_doc_code_mismatch.md` §2·§3 에 있다 (**둘 다 줄 번호는 `f55617a` 기준, 테스트 파일 이름은 계획서 ② 이전 이름** — 대응은 `SLIM_SERIES.md` 인계 메모)
- 🔴 **무력화된 테스트가 하나 있다** — `tests/test_report_writer.py` 의 `OTHER_TRACK_NAME = "option_expiry"` 는 「같은 등급의 다른 매매법」이 전제인데 option_expiry 가 조사로 내려가 reverse(매매)와 부모 폴더가 달라졌다. **등급 폴더를 통째로 비우는 버그가 생겨도 `test_clearing_keeps_other_tracks_in_the_layer` 가 통과한다**
- 🔴 **게이트 테스트가 운영과 다른 경로를 고정한다** — `tests/test_measure_screening.py` 의 게이트 테스트 약 35개가 운영 호출 0건인 `direction_profile` 을 거쳐 `screen_verdict` 를 잰다. 운영은 `execution/periods.py` 가 `screen_verdict` 를 직접 부른다
- 결정: 보고서 §10 Q8 (① 재수출 제거 ② 연결 누락은 연결 ④ 미사용 인자 제거), Q9 ⑤ (메타 키 `<slug>`), Q10 (옛 계획서의 리뷰 잔여 중 범위분 — 보고서 §12.1 의 「③」 행), 계획서 ① 리뷰 R8 · R9 · R10(주석만) · R11 (보고서 §12.3)

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- `.claude/plan-config.json` — 이 저장소의 검증 명령·자동 포맷·근거 승격 목적지 (**값의 SoT**)
- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절 (값이 아니라 **판단 근거**)
- `src/verify_lab/CLAUDE.md` — 계층 간 계약 · 「주석은 현재형으로 씁니다」
- `~/.claude/rules/python.md` — 특히 「미사용 판정에는 「왜 안 쓰이는가」가 함께 필요하다」
- `scripts/CLAUDE.md` · `tests/CLAUDE.md`
- `.claude/rules/docs.md` 「과거형이 허용되는 자리는 둘뿐입니다」 — 코드 주석은 현재형 자리다
- 루트 `SLIM_SERIES.md` 「시리즈 공통 주의」

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 보고서 §2.1 · §2.2 의 정의가 저장소에 없다 (AST 재스캔으로 확인)
- [x] `test_report_writer.py` 가 같은 등급의 다른 매매법으로 검사한다 — **등급 폴더를 비우는 변형을 넣으면 실패함을 확인**했다
- [x] 게이트 테스트가 `direction_profile` 없이 운영 경로(`screen_verdict`)를 고정한다
- [x] 삭제 매매법 잔재·중복 테스트가 없고, 공유 계층 테스트가 매매법 상수를 import 하지 않는다
- [x] `IDENTITY_COLUMNS` 둘과 `tracks_of_kind` 가 운영·테스트에서 실제로 쓰인다 (손으로 적은 목록이 사라졌다)
- [x] `__init__.py` 6개가 재수출하지 않는다
- [x] 메타 타입 키가 스크립트 전부에서 `<slug>` 다
- [x] 주석·docstring 불일치 목록(AUDIT_slim_doc_code_mismatch §2·§3, AUDIT_slim_dead_code D, 보고서 §12.1 「③」)이 처리됐다 — Non-Goals 로 넘긴 것은 인계 메모에 남긴다
- [x] 🔴 **5개 실행 스크립트 재실행 후 `git diff --stat storage/results/` 가 비어 있다**
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — `docs/COMMANDS.md` 변경 없음(메타 키는 COMMANDS 에 없다) · 지운 이름을 가리키는 계약 문서 줄만 수정 · `SLIM_SERIES.md` 갱신
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다 (중복 테스트를 어느 쪽으로 남겼는지·연결 누락을 어떻게 이었는지의 «왜»는 남긴 테스트/코드의 docstring 에, 뒤 계획서가 알아야 할 것은 `SLIM_SERIES.md` 인계 메모에)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/measure/screening.py` · `report/tables.py` · `report/constants.py` — 방향 표 계열 11개, `COL_SCREEN`, `DISPLAY_BASIS`
- `src/verify_lab/studies/futures_leverage/constants.py` (`DISPLAY_BASE_TICKER`·`DISPLAY_RETURN`·`DISPLAY_EXPOSURE`), `studies/reverse/extreme_move.py` (`RANK_COLUMNS`)
- `src/verify_lab/{data,measure,report,utils}/__init__.py`, `studies/{reverse,midterm_cycle}/__init__.py` — 재수출
- `src/verify_lab/studies/reverse/{runner,trading,constants}.py`, `studies/futures_leverage/runner.py`, `data/pykrx_collector.py`, `tracks.py` — 연결 · 미사용 인자 · 주석
- `scripts/run_{futures_leverage,leverage_tracking,usdkrw_equivalence}.py` — 메타 키. `scripts/run_reverse.py` — `--dataset` 도움말
- `src/verify_lab/**` 주석·docstring (범위: AUDIT_slim_doc_code_mismatch §2·§3, Non-Goals 의 ⑥·⑦ 몫 제외), `validate_project.py` 주석
- `tests/test_report_writer.py`, `tests/test_measure_screening.py`, `tests/test_report_tables.py`, `tests/test_output_contract.py`, `tests/test_execution_trade_fill.py`, `tests/test_studies_reverse_trading.py`, `tests/test_layer_contracts.py`, `tests/test_index.py`, `tests/test_studies_extreme_move.py`
- `src/verify_lab/CLAUDE.md` — **지운 이름을 가리키는 줄만** (예: 없는 `screen_candidates`)
- `SLIM_SERIES.md` · 보고서 §12 · 이 계획서
- `docs/COMMANDS.md`: **변경 없음**

### 데이터/결과 영향

- **없어야 한다.** 이것이 이 계획서의 통과 조건이다. `storage/results/meta.json` 은 git 제외라 메타 키가 바뀌어도 diff 에 나오지 않는다

## 6) 단계별 계획(Phases)

### Phase 0 — 기준선 (코드 변경 없음)

**작업 내용**:

- [x] 착수 전: `git status` 깨끗 · 계획서 ② 커밋 확인 · 수집 테스트 수를 진행 로그에
- [x] 5개 실행 스크립트를 인자 없이 돌린다 — `scripts/run_{reverse,midterm_cycle,leverage_tracking,futures_leverage,usdkrw_equivalence}.py` (명령은 `docs/COMMANDS.md`). 외부 호출이 없고 `storage/market/`·`storage/series/` 만 읽는다
- [x] 재현을 확인한 뒤에야 그 diff 를 이 계획서의 통과 기준으로 쓸 수 있다
- [x] AUDIT_slim_dead_code 머리의 방법(AST 로 import 체인·재수출을 따라 참조를 세고, 스크립트·`validate_project.py` 최상위를 뿌리로 도달 가능성 계산)으로 스캔 스크립트를 **스크래치에** 쓰고 돌려, §2.1·§2.2 목록이 지금도 같은지 확인한다 — 다르면 진행 로그에 적고 지금 결과를 따른다

**Validation**:

- [x] `git diff --stat storage/results/` 가 비어 있다 — **비어 있지 않으면 멈추고 사용자에게 보고한다**(시세나 환경이 바뀐 것이라 이 계획서의 기준이 성립하지 않는다)

---

### Phase 1 — 테스트 결함과 잔재 (그린 유지)

**작업 내용**:

- [x] `tests/test_report_writer.py`: `OTHER_TRACK_NAME` 을 **reverse 와 같은 등급**의 slug(`midterm_cycle`)로. 그 뒤 `create_run_directory` 에 「등급 폴더를 통째로 비우는」 변형을 **잠깐** 넣어 `test_clearing_keeps_other_tracks_in_the_layer` 가 실패하는지 보고 되돌린다(돌이킨 것을 진행 로그에). slug 목록(삭제 매매법 옆, `midterm_cycle` 누락)도 채운다
- [x] `tests/test_execution_trade_fill.py`: reverse 의 `HOLD_LIMIT`·`STOP_LOSS_LEVEL` import 를 **자기 픽스처 값**으로 바꾸고 `assert HOLD_LIMIT == 2` 를 지운다 — 그 사실은 `tests/test_studies_reverse_trading.py` 가 이미 고정한다 (`docs/MEMORY.md` 「공유 계층의 테스트는 자기 픽스처를 갖는다」)
- [x] 중복 테스트: ① 제외 컬럼 없음(`test_studies_reverse_trading.py` 쪽이 `test_output_contract.py` 의 하위집합 → 하위집합 삭제) ② 구간 5행(같은 방식) ③ 스크립트의 `.csv` 문자열 — **`test_output_contract.py` 의 `test_매매_스크립트에_csv_문자열이_없다` 를 지운다.** `test_layer_contracts.py` 의 두 검사(`*_FILENAME` 정의 금지 · 파일 이름 모양 리터럴 금지)가 같은 목적을 **산문 예외까지 설계해** 지키는데, 부분 문자열 전면 금지가 그 예외를 무력화한다
- [x] `tests/test_output_contract.py`: 삭제 매매법 상수 `AXIS_OPTION_EXPIRY`·`AXIS_MONTH_END`·`EXPIRY_MONTH` 와 도달 불가 분기(`EXPIRY_TARGET_DATE_COLUMN` · `_expected_trades(target_date=)`)를 지운다. 매매법이 둘인데 「세_」로 시작하는 테스트 함수 이름과 docstring(「세 매매법」·「역방향·월말이 계속 그 이름을 낸다」·`grid.csv`)을 현재 사실로. `midterm_cycle_outputs` 픽스처 docstring 의 「10월 진입 · 사이클 네 자리」를 9월 마지막 거래일 · 중간선거해 한 칸으로 (리뷰 R8)
- [x] `tests/test_index.py` 실패 메시지(리뷰 R9): 「무엇이 잘못됐고 무엇을 해야 하는지」가 되게 — 되살아난 경로와 **「지우거나, 되살려야 한다면 `REMOVED_DOCUMENTS` 의 그 줄과 사유를 먼저 고친다」** 를 함께. 사유가 없는 앞 세 항목에는 블록 주석이 사유임을 한 줄로 밝힌다
- [x] `tests/test_studies_extreme_move.py` 의 미사용 `EXACT_TOLERANCE`
- [x] 틀린 테스트 주석: `test_measure_screening.py` 의 「60% 게이트를 못 넘어 제외」(실제 이유는 기대값 하한), `test_layer_contracts.py` 의 없는 `screen_candidates`·「네 이름」·「매매법 셋」, 허용목록 머리 주석의 달력형 어휘, `_KNOWN_LABEL_DUPLICATES` 의 futures 항목(Phase 2 와 함께)

**Validation**:

- [x] 고친 테스트 파일만 직접 돌려 통과 (`poetry run pytest <파일들> -q`)
- [x] 무력화 테스트의 변형 실험 결과(실패 확인 → 원복)가 진행 로그에 있다

---

### Phase 2 — 데드 코드 삭제와 게이트 테스트의 경로 교정 (그린 유지)

**작업 내용**:

- [x] 🔴 **먼저 게이트 테스트를 운영 경로로 옮긴다** — `tests/test_measure_screening.py` 에서 `direction_profile` 을 거치는 테스트(헬퍼 `_verdict` 계열)를 `screen_verdict` 를 직접 부르는 형태로 다시 쓴다. **검사하는 계약(경계값 · 방향 · 보합 · `tradable`)은 하나도 줄이지 않는다** — 테스트 수가 줄면 무엇이 합쳐졌는지 진행 로그에 적는다
- [x] 그다음 지운다: `direction_profile`·`_direction_row`·`DIRECTION_COLUMNS`·`REQUIRED_SUMMARY_COLUMNS`·`COL_HIT_RATE`·`COL_EXPECTED_VALUE`·`COL_TOTAL_RETURN`(screening.py), `build_direction_table`·`DISPLAY_HIT_RATE`·`DISPLAY_EXPECTED_VALUE`·`DISPLAY_TOTAL_RETURN`(report), `tests/test_report_tables.py` 의 `TestDirectionTable`
- [x] `COL_SCREEN`·`DISPLAY_BASIS`: 테스트의 「없어야 한다」 가드는 **문자열 리터럴**로 바꾼 뒤 상수를 지운다 (가드는 남는다)
- [x] 완전 미사용 4개(보고서 §2.1) + `_KNOWN_LABEL_DUPLICATES` 의 futures 항목
- [x] 쓰이지 않는 인자(보고서 §2.6): `run_reverse_trading(hold_limit=)` · futures `run_study(horizons, market_dir, series_dir)` · `collect_pykrx_nav(output_dir=)` — 호출처를 다시 grep 해 **전부 기본값만 쓰는지** 확인하고 지운다
- [x] 백로그 §12.1 「③」의 「`COLUMN_LABELS` 죽은 원자료 레이블 8개 · 도달 불가 분기」(중간선거_사이클): **지금도 있는지 먼저 확인**한다 — 있으면 지우고, 없으면 「이미 정리됨」을 진행 로그에
- [x] `execution/constants.py` 의 `NOTE_STOP_BASE`: `reverse/trading.py` 에 같은 이름·다른 값이 있다. 참조를 세어 **쓰지 않는 쪽이면 지우고**, 둘 다 쓰이면 건드리지 않고 인계 메모에 남긴다
- [x] 지운 이름을 가리키는 `src/verify_lab/CLAUDE.md` 줄(없는 `screen_candidates` 등)은 **이름만** 현재 것으로 — 문서 전체 정리는 ④

**Validation**:

- [x] AST 재스캔에서 보고서 §2.1 · §2.2 목록이 0
- [x] `poetry run pytest tests/test_measure_screening.py tests/test_report_tables.py tests/test_layer_contracts.py -q` 통과

---

### Phase 3 — 재수출 제거 · 연결 누락 · 메타 키 (그린 유지)

**작업 내용**:

- [x] `__init__.py` 6개(`data` · `measure` · `report` · `utils` · `studies/reverse` · `studies/midterm_cycle`)의 재수출과 `__all__` 을 걷고 패키지 docstring 만 남긴다. **먼저** `from verify_lab.<패키지> import <이름>` 이 운영·테스트에 0건인지, 하위 모듈 선로딩 부작용에 기대는 곳이 없는지(`import verify_lab.<패키지>` 뒤 `.하위모듈` 속성 접근) grep 으로 확인한다. `test_layer_contracts.py` 의 「`__all__` 재등장 금지」 검사와 부딪히지 않는지 본다
- [x] `IDENTITY_COLUMNS`(`studies/reverse/runner.py` · `trading.py`): 같은 순서를 손으로 다시 적는 자리(runner 의 표 조립 · trading 의 행 조립)가 **그 상수를 쓰게** 한다 — 순서가 바이트까지 같아야 한다(Phase 4 의 재실행이 판정)
- [x] `tracks_of_kind`·`KINDS`: `tests/test_output_contract.py` 가 매매법 둘을 손으로 적는 자리를 `tracks_of_kind(KIND_METHOD)` 로 — 「매매법이면 성적표를 낸다」 계약이 레지스트리를 따라가게 한다
- [x] 메타 타입 키: `run_futures_leverage.py`·`run_leverage_tracking.py`·`run_usdkrw_equivalence.py` 의 `*_study` 를 그 slug(`TRACK_NAME`)로 — 가능하면 리터럴이 아니라 그 매매법 `constants.py` 의 `TRACK_NAME` 을 쓴다(나머지 두 스크립트의 관용을 확인하고 맞춘다)

**Validation**:

- [x] 운영·테스트에서 `from verify_lab.<패키지> import` 형태 0건, `__all__` 0건(패키지 `__init__`)
- [x] 관련 테스트 파일 통과

---

### Phase 4 — 주석·docstring·도움말 (그린 유지)

**작업 내용**:

- [x] AUDIT_slim_doc_code_mismatch §2 표의 코드 주석 행을 전부 처리한다 — **Non-Goals 로 넘기는 행**(달력 조사 문서·원달러 그리드 설계·사양서를 가리키는 포인터)만 빼고. 묶음: 삭제 매매법을 현재 사용처로 적은 곳 · 없는 `strategy/` 경로 · 「세 매매법」「나머지 두 매매법」 · 정반대(`execution/__init__.py` 「경계는 폴더 단위」 → 「행위」) · 전면 낡음(`studies/midterm_cycle/__init__.py`·`constants.py:13,165`) · 개수 틀림(`reverse/runner.py` 블록 개수, `reverse/trading.py` 모듈 docstring) · 정책과 모순(`measure/forward_return.py` 「병기」) · 「`통계.csv` 가 기준선 14 + 차이 4」(`screening.py`·`report/tables.py`·`report/constants.py`) · 틀린 경로(`futures_leverage/constants.py` 의 `docs/.claude/...`, 코드 주석의 `.claude/rules/python.md` → 전역 `~/.claude/rules/python.md`) · `ecos_collector.py` 의 반올림 표 인용 · `common_constants.py` KST 설명 · `report/writer.py` 예시 · `report/run_summary.py` 「여섯 산출 지점」·`expiry_count`
- [x] AUDIT_slim_doc_code_mismatch §3 — 과거형·변경 이력·계획 단계 표기(「Phase」「2-a/2-b/2-c」)를 현재형으로, 코드를 말로 옮긴 주석(`validate_project.py` 의 「# Ruff 출력 표시」 류)은 지운다. **담긴 「왜」는 남긴다** — 시제만 바꾼다
- [x] 보고서 §12.1 「③」: `studies/reverse/constants.py` 의 `STOP_LOSS_LEVEL`·`HOLD_LIMIT` 주석(버린 「갭손절 0건」 근거와 옛 수치 → `docs/매매/역방향/규칙.md` 결정 ⑤·⑥ 의 현재 근거를 한 줄로 가리키게) · `reverse/trading.py` 의 격자 전제 주석(리뷰 R10 — **구조는 그대로**) · 새 코드 주석 넷의 「지웠다」·커밋 해시·날짜 · `cycle_calendar.py`·`midterm_cycle/constants.py` 과거형 docstring
- [x] `scripts/run_reverse.py` `--dataset` 도움말의 「국내 두 기준의 대조는 함께 돌려야 성립」(국내 대상은 원본가 하나) — 사용자에게 보이는 문구라 한글로 정확하게
- [x] `tracks.py` 의 주석 정리는 **하지 않는다** — 등급 정의 문구 중립화(L2)와 같은 줄이라 계획서 ④ 가 함께 한다

**Validation**:

- [x] `grep -rn -E 'strategy/|세 매매법|option_expiry|month_end|옵션 만기일|월말' src scripts tests validate_project.py` 의 남은 줄이 **의도된 것뿐**(레지스트리 · 금지목록 · Non-Goals 포인터)이고 그 목록이 진행 로그에 있다
- [x] `grep -rn '\.claude/rules/python\.md' src scripts tests` 가 `~/` 형태뿐

---

### Phase 5 (마지막) — 재실행 대조 · 문서 정리 · 최종 검증

**작업 내용**

> 🔴 **`/commit` 이 «맨 마지막»인 것은 의도다.** 그 스킬은 「후보 뒤에는 아무것도 덧붙이지 말 것」으로
> 끝나므로 **호출하는 순간 그 턴이 거기서 닫힌다.** 중간에 두면 뒤에 적힌 항목이 그 벽 너머에 남는다 —
> 실제로 두 번 그렇게 샜다(`[실측] 2026-09-14` 후보를 계획서에 안 옮김 · `2026-09-16` 옮기고 체크박스를 안 닫음).
> **체크박스와 상태를 먼저 확정하고, 커밋 후보를 마지막에 만든다.**

- [x] 🔴 5개 실행 스크립트를 인자 없이 다시 돌리고 `git diff --stat storage/results/` 가 **비어 있음**을 확인한다 — 비어 있지 않으면 어느 변경이 값을 바꿨는지 찾아 되돌린다(이 계획서는 값을 바꾸지 않는다)
- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` 변경 없음 확인)
- [x] 보고서 §12 백로그 갱신 — Non-Goals 로 넘긴 항목과 리뷰 「그 외」
- [x] `SLIM_SERIES.md` 진행 표 · 인계 메모 갱신 (⑥ · ⑦ 에 넘긴 주석 포인터 목록을 반드시 남긴다)
- [x] 자동 포맷 적용 (`poetry run black .`)
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] Validation 절에 `/code-review` 와 품질 검증 **실행 결과**를 적는다
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정
- [x] 🔴 **마지막에 `/commit` 을 실행하고 그 후보를 «이 계획서» 의 `#### Commit Messages` 절에 옮긴다** —
      `/commit` 은 계획서를 모르고 「후보 뒤에 아무것도 덧붙이지 말 것」으로 끝나므로,
      **대화에만 내면 그 절이 빈 채로 남는다.** 체크박스 갱신이 diff 에 더 들어가지만
      커밋 메시지의 내용을 바꾸지 않는다. **커밋은 사용자가 한다 — 후보만 낸다**

**Validation**:

> 순서를 지킨다 — 리뷰에서 고치면 코드가 바뀌므로 품질 검증이 마지막 관문이어야 한다.
> **버그가 0 인 회차에서 끝낸다.** 2회차에도 버그가 나오면 사용자에게 보고하고 3회차 여부를 묻는다 —
> 「그 외」는 목록만 남기고 고치지 않는다. `/impl-plan` 의 「코드 리뷰」 절이 SoT 다.

- [x] `/code-review xhigh` **1회차** (발견 15건 — 버그 0 · 그 외 15 · 조치: 이 계획서가 만든 A·B·C 를 사용자 결정으로 고침, 나머지 T1 ~ T9 는 보고서 §12.5)
- [x] `poetry run python validate_project.py` (passed=1239, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다.**
> 계획서를 쓰는 시점에는 diff 가 없어 여기 적는 것은 전부 추측이고,
> **추측으로 적은 줄은 그대로 나간다.** 형식·문체 규칙은 `/commit` 이 정한다.

> `storage/results/조사/레버리지_ETF_괴리/full_period.csv` 와 `docs/INDEX.md` 는 이 커밋에 넣지 않는다 — 사용자가 먼저 따로 커밋한다(Notes).

1. 정리 / 쓰이지 않는 방향 표 계열과 재수출 제거, 무력화된 테스트 보강
2. 정리 / 데드 코드 · 미사용 인자 · `__init__` 재수출 제거와 게이트 테스트의 운영 경로 이전
3. 정리 / 산출물 바이트 불변 아래 데드 코드 제거 · 무력화 테스트 수리 · 식별 컬럼과 레지스트리 연결 · 주석 현재형 정리
4. 정리 / 삭제 매매법 잔재와 낡은 주석 정리, 메타 타입 키의 slug 통일
5. 정리 / 경량화 ③ — 운영 호출 0건 코드 제거와 회귀를 실제로 잡는 테스트로의 보강

## 7) 리스크(Risks)

- **동적 참조를 놓쳐 운영이 깨진다** (`getattr`, pandas 컬럼명으로 쓰이는 상수) — 지우기 전 문자열 grep 을 함께 하고, 최종 재실행 대조가 잡는다
- **게이트 테스트를 옮기며 계약이 조용히 빠진다** — 옮기기 전 테스트 목록(이름 · 검사하는 경계)을 진행 로그에 뽑아 두고 옮긴 뒤 대조한다
- **재수출 제거가 import 순서 부작용을 깬다** — 특히 pykrx 는 import 자체가 로그인을 시도한다(`src/verify_lab/CLAUDE.md` 「pykrx import 순서」). `data/__init__.py` 가 무엇을 먼저 불러오는지 보고, 테스트와 5개 스크립트 재실행으로 확인한다
- **`IDENTITY_COLUMNS` 연결이 컬럼 순서를 바꾼다** — 재실행 바이트 대조가 잡는다
- **주석 대상이 너무 많아 일부를 놓친다** — AUDIT 표의 행마다 처리/이관을 진행 로그에 표시한다
- **`VIRTUAL_ENV`** — 모든 도구가 실패하면 `env -u VIRTUAL_ENV`

## 8) 메모(Notes)

- 시리즈의 SoT 는 루트 `SLIM_SERIES.md`. 이 계획서는 ③ 이며 **커밋 하나**로 끝난다
- 감사 원문의 줄 번호는 `f55617a` 기준이다. ① · ② 가 바꾼 파일(`tests/test_index.py`, 개명한 5개, `src/verify_lab/CLAUDE.md` 등)은 줄이 밀렸다

### 착수 후 사용자 결정 (2026-09-26 21:21)

- **기준선**: Phase 0 재실행이 `storage/results/조사/레버리지_ETF_괴리/full_period.csv` 의 `1배에만 있는 날` 8행을 바꿨다(원인은 `f55617a` 의 QQQ·069500 재수집 — 진행 로그). **그 파일 하나를 사용자가 먼저 따로 커밋**하고, 그 커밋 뒤의 HEAD 를 이 계획서의 기준선으로 쓴다 — 값 변경과 산출물 불변 변경을 한 커밋에 섞지 않는다(`docs/MEMORY.md`)
- **범위 추가**: 계획서 ② 리뷰가 새로 드러낸 무력화 테스트 셋(보고서 §12.4 S1 · S2 · S12)을 Phase 1 에서 함께 고친다. 목표 2 「무력화된 테스트」와 같은 성격이고 테스트만 바뀐다. 셋 다 **회귀를 잠깐 넣어 실패를 확인한 뒤 되돌린다**
  - [x] S1 `tests/test_studies_reverse_trading.py` — 「모든 신호가 잘린」 테스트가 제외 **건수**를 검사한다
  - [x] S2 `tests/test_output_contract.py` — 표본 0건 행의 정수 건수 칸이 CSV 에서 빈칸인지를 **그 칸들로** 검사한다
  - [x] S12 `tests/test_studies_reverse_trading.py` — 순위 컷 테스트가 `.iloc[0]` 대신 전체 구간 행으로 신호 수를 집는다 (변형 실험은 성립하지 않았다 — 진행 로그 21:38)
- S8(개명한 세 파일의 모듈 docstring) · S13(`FIXED_LEVEL` 의 「월말 규칙 문서」 출처 · `세_이름` 테스트)은 삭제 매매법을 말하는 주석이라 **목표 4 와 Phase 4 grep 검증이 이미 덮는다** — 따로 항목을 두지 않는다
- **머지 문서 등록**(2026-09-26 21:30): 작업 중 들어온 `docs/검증/반감기_사이클/` 두 장을 `docs/INDEX.md` 에 한 행으로 등록하고 **사용자가 그 파일만 따로 커밋**한다 — ③ 범위 밖
- **리뷰 자체 결함 A · B · C 를 커밋 전에 고친다**(2026-09-28 07:20): 리뷰 1회차가 버그 0 으로 끝났고, 「그 외」 중 이 계획서가 만든 셋만 고친다 — A 파일 이름 검사가 조립(`f"{name}.csv"`)을 놓침 · B `_identity` 의 조용한 키 누락 · C 새로 쓴 주석 셋. 나머지는 보고서 §12.5 백로그

### 진행 로그 (KST)

- 2026-09-26 16:55: 계획서 작성 (Draft). 중복 테스트 ③ 의 처리(부분 문자열 전면 금지 쪽 삭제)는 작성 시점에 두 테스트를 읽고 정했다 — `test_layer_contracts.py` 쪽 docstring 이 산문 예외를 의도적으로 설계했다
- 2026-09-26 21:14: 착수 (In Progress). `git status --short` 비어 있음, 계획서 ② 커밋 `c5f6979` 확인(5개 파일 rename 으로 잡힘). 수집 **1,282**
- 2026-09-26 21:18: Phase 0
  - 5개 스크립트 인자 없이 실행 — 전부 rc=0 (reverse 23s · midterm_cycle 3s · leverage_tracking 13s · futures_leverage 34s · usdkrw_equivalence 2s)
  - 🔴 **`git diff --stat storage/results/` 가 비어 있지 않다** — `storage/results/조사/레버리지_ETF_괴리/full_period.csv` 한 파일, 8행, **`1배에만 있는 날` 한 컬럼만** 바뀐다(코스피200 3행 +13 · 나스닥100 5행 +14). 나머지 컬럼과 다른 파일은 전부 같다
  - 원인: 역방향 커밋 `f55617a` 가 `storage/market/QQQ_max.csv`(+14행 → 2026-09-24)·`069500_max.csv`(+13행 → 2026-09-23)를 재수집했는데 `레버리지_ETF_괴리` 산출물은 그 뒤 다시 돌리지 않았다(마지막 갱신 `57ea9a1`, 2026-09-16). 배수 상품 시세는 2026-09-01·02 에서 끝나 공통 구간은 그대로이고 「1배에만 있는 날」만 늘었다. `docs/조사/레버리지_ETF_괴리/` 는 그 컬럼 값을 인용하지 않는다
  - 계획서 Phase 0 Validation 의 지시대로 **멈추고 사용자에게 보고**
  - AST 재스캔(감사 스크립트 `reach.py` 를 스크래치에 복사해 실행): §2.1 넷 + §2.2 열셋 + 의도·연결 누락 목록이 **감사와 같고 줄 번호도 같다.** `EXACT_TOLERANCE`(`tests/test_studies_extreme_move.py:29`)도 그대로
- 2026-09-26 21:21: 사용자 결정 둘(Notes 「착수 후 사용자 결정」). `full_period.csv` 는 사용자가 따로 커밋한다
- 2026-09-26 21:30: 🔴 **HEAD 가 작업 중에 움직였다** — 사용자가 `origin/claude/gallant-heisenberg-r0j0re` 를 머지(`f93995a`)해 `docs/검증/반감기_사이클/{도서,사전조사}.md` 두 장이 INDEX 미등록으로 들어와 `test_index` 가 실패. 사용자 결정으로 `docs/INDEX.md` §2 에 한 행을 넣고 **사용자가 그 파일만 따로 커밋**한다(③ 범위 밖 — ③ 커밋에 넣지 않는다)
- 2026-09-26 21:38: Phase 1 완료 — 변형 실험 넷
  - `test_report_writer.py`: `OTHER_TRACK_NAME` → `midterm_cycle`. `writer.py` 의 `rmtree(directory)` 를 `rmtree(directory.parent)` 로 바꾸자 **여전히 통과** — 테스트가 역방향 폴더를 «처음» 만들어 비우는 경로를 한 번도 지나지 않았다. Given 에서 역방향 폴더를 먼저 만들게 고치자 같은 변형에서 `assert kept.exists()` 로 **실패**, 원복 후 통과. 등급이 갈리는 변형(`OTHER_TRACK_NAME = "option_expiry"`)도 새 선행 단언이 **실패**로 잡는다. slug 목록에 `MIDTERM_CYCLE` 추가. 같은 파일의 「검증 여섯 · 매매 셋 · 아홉 개」 개수 서술도 뺐다
  - S1(`test_studies_reverse_trading.py`): `trading.py:236` 의 제외 건수를 `0` 으로 바꾸는 변형 → 새 단언이 `{'-5.0': 0}` 으로 **실패**(옛 단언은 키만 봐서 통과했을 것). 원복 후 통과
  - S2(`test_output_contract.py`): `periods.py:351` 을 `fillna(0).astype(...)` 로 바꾸는 변형 → 새 단언이 `질 때 표본·갭손절·장중손절·사건` 이 `'0'` 으로 **실패**. 원복 후 통과
  - S12: `.iloc[0]` → `_overall(...)`. **변형 실험이 성립하지 않는다** — 합성 시세에서 순위 컷 5·10·20 이 모두 신호 3건(전체 · 앞 절반 1 · 뒤 절반 2 · 최근 10년 3 · 최근 5년 3)이라 `wide >= narrow` 가 언제나 등호로 통과한다. 즉 **매매 계층이 순위 컷을 무시해도 이 테스트는 못 잡는다** — 픽스처(`_market`)를 바꿔야 하는 별개 결함이라 고치지 않고 백로그로 넘긴다
  - 매 변형 뒤 `git diff --stat` 로 원본 복원 확인(src 쪽 diff 0)
  - 그 밖: 중복 테스트 셋 삭제와 남긴 쪽 docstring 에 「왜 한 곳인가」 한 줄, `test_execution_trade_fill.py` 는 `STOP_LEVEL = 0.05` 자기 픽스처(형제 `test_execution_trade_fill_scheduled.py` 의 관용)와 모듈 docstring(S8), `test_output_contract.py` 는 `TRADE_COMMON_HEAD/TAIL` 두 토막을 한 벌로(쪼갠 이유가 옵션 만기일의 `청산 목표일` 뿐이었다), `FIXED_LEVEL` 출처(S13), `세_이름` 테스트 이름, 과거형 docstring(1285·1304 · `TestSingleColumnStopFilter`), `test_layer_contracts.py` 의 `screen_candidates`·「네 이름」·「매매법 셋」·「세 매매법」과 남긴 파일 이름 검사의 「왜」 한 줄
  - 「60% 게이트」 주석은 그 테스트가 `direction_profile` 을 거쳐 Phase 2 에서 다시 쓰이므로 거기서 처리, 허용목록 머리 주석은 futures 항목과 함께 Phase 2 에서
  - 고친 7개 파일 직접 실행: 226 passed + `test_index` 1 실패(머지 문서 — 위 21:30). INDEX 행 추가 뒤 문서 테스트 146 passed
- 2026-09-26 21:38: Phase 2 착수 전 — `tests/test_measure_screening.py` 의 테스트 **47개** 목록(옮긴 뒤 대조용)
  - `TestScreen`(9): 기대값을_넘으면_후보다 · 적중률이_낮아도_기대값을_넘으면_후보다 · 기대값이_음수면_제외된다 · 기대값이_하한과_같으면_후보다 · 기대값이_양수여도_하한_미만이면_제외된다 · 기준선과_똑같아도_게이트를_넘으면_후보다 · 표본이_1건이어도_판정한다 · 표본이_0건이면_판정하지_않는다 · 제외된_칸도_행이_남는다
  - `TestBaselineIsNotInTheVerdict`(3): 판정표에_기준선_컬럼이_없다 · 기준선_초과분_없이도_판정된다 · 기준선을_빼도_판정_값이_그대로다
  - `TestNotJudged`(3): 살_수_없는_대상은_판정_안_함으로_남는다 · 판정_안_해도_값은_그대로_실린다 · 게이트를_못_넘어도_판정_안_함이다
  - `TestExpectedValue`(2): 아래_방향은_평균의_부호를_뒤집는다 · 위_방향은_평균을_그대로_쓴다
  - `TestDirectionSymmetry`(5): 위로_멀어진_칸도_같은_기준으로_후보가_된다 · 방향은_두_비율_중_큰_쪽이다 · 기준선보다_낮아도_적중률이_높으면_후보다 · 보합이_커도_여집합으로_방향을_정하지_않는다 · 자주_맞아도_걸면_손실인_칸은_기대값이_거른다
  - `TestAxisIndependence`(8) · `TestFormula`(3) · `TestTotalReturn`(4) — 전부 `direction_profile` 의 스키마·축·산식
  - `TestScalarVerdict`(8): 방향_표의_값으로_게이트가_걸린다 · 기대값이_하한과_같으면_후보다_스칼라 · 기대값이_하한에_한_칸_못_미치면_제외다_스칼라 · 표본이_1건이어도_판정한다 · 표본이_0건이면_판정하지_않는다 · 살_수_없는_대상은_판정하지_않는다 · 결측_기대값은_판정하지_않는다 · 성적_산식_계층이_이_게이트를_쓴다
  - `TestGateValues`(2): 게이트_조건이_하나다 · 회당_기대값_하한이_1퍼센트다
- 2026-09-26 21:49: Phase 2 완료
  - **게이트 테스트 47 → 14.** 계약별 행방:
    - 경계(이상 · 미만 · 양수인데 모자람) → `TestGateBoundary` 넷. `기대값이_하한과_같으면_후보다` 와 `_스칼라` 가 하나로, `기대값이_음수면_제외된다` 와 `자주_맞아도_걸면_손실인_칸은_기대값이_거른다`(둘 다 SPY 3월 실물)가 `자주_맞아도_걸면_손실인_칸은_제외된다` 하나로
    - 「적중률이 낮아도 · 기준선과 같아도 · 기준선보다 낮아도 · 합산이 커도 · 위로 멀어져도 같은 기준」(7) + `TestBaselineIsNotInTheVerdict`(3) → `TestGateInputs.test_게이트는_기대값_표본_판정대상_셋만_받는다` 하나 — 게이트가 받을 자리가 없으면 그것으로 가를 수 없다는 것을 **시그니처로** 고정한다. 변형 둘(`hit_rate` 인자 추가 · `tradable` 기본값) 모두 **실패**로 잡고 원복
    - 표본 1건 · 0건 · 결측(방향 표판 · 스칼라판 중복 5) → `TestSampleCount` 셋
    - `tradable`(4) → `TestNotJudged` 둘(넘어도 · 못 넘어도 판정 안 함). `판정_안_해도_값은_그대로_실린다` 는 방향 표 전용 — 운영 대응은 `test_output_contract.py` 의 `살_수_없는_대상은_전체_행에서도_판정하지_않는다` · `TestWorstHoldColumn.지수_행도_값을_갖는다`
    - **`direction_profile` 과 함께 사라지는 것**: 방향을 두 비율 중 큰 쪽으로 고르는 규칙 · 적중률 매핑 · 합산 산식 · 축 스키마·정렬·중복·결측 검사(`TestAxisIndependence` 8 · `TestFormula` 3 · `TestTotalReturn` 3 · `TestExpectedValue` 2 · `방향은_두_비율_중_큰_쪽이다` · `보합이_커도_여집합으로_방향을_정하지_않는다` · `제외된_칸도_행이_남는다` · `방향_표의_값으로_게이트가_걸린다`). 운영에서 방향을 고르는 코드가 없으므로(매매법마다 방향이 확정) 검사할 대상도 없다. **방향 부호와 보합의 운영 쪽 계약은 이미 따로 있다** — 부호: `test_execution_trade_fill.py` 「상승_방향_신호는_원지수_하락이_이익이다」, 보합: `test_measure_statistics.py`(두 비율이 여집합이 아님 · 손익비의 보합) · `test_execution_trade_fill.py:303`
    - 그대로: `성적_산식_계층이_이_게이트를_쓴다` · `TestGateValues` 둘
  - 지운 것: `screening.py` 의 방향 표 계열 7 + `COL_SCREEN`(가드 없음 — 가드였던 테스트가 방향 표와 함께 사라짐) · `report/tables.py` 의 `build_direction_table` · `report/constants.py` 의 `DISPLAY_HIT_RATE`·`DISPLAY_EXPECTED_VALUE`·`DISPLAY_TOTAL_RETURN`·`DISPLAY_BASIS`(가드 넷은 `BASIS_HEADER = "기준"` · 지역 리터럴로) · `test_report_tables.py` 의 `TestDirectionTable`·`TestDirectionTotalReturn` · §2.1 넷(`RANK_COLUMNS` 는 반환이 `COL_*` 를 직접 써 연결 누락이 아니다 — docstring 은 실제 컬럼 이름으로) · `_KNOWN_LABEL_DUPLICATES` 의 `1배 종목`·`수익률(%)` 두 항목(정의처가 하나가 됨)과 머리 주석의 달력형 어휘 · 인자 셋
  - `screening.py` 는 이 기회에 AUDIT_slim_doc_code_mismatch 의 이 파일 행(:15 · :77 · :181 · :191-192 · §3 과거형)을 함께 처리했다 — 모듈 docstring 에서 방향 표 설명을 걷고, 「`통계.csv` 가 기준선 14 + 차이 4」를 「`excess.csv` · `측정.csv`」로, 「인버스 실물」·「세 매매법」을 뺐다. `report/constants.py:113-115`(판정표) · `futures_leverage/constants.py:245`(`docs/.claude/...` 경로) · `studies/midterm_cycle/__init__.py`(전면 낡음)도 같은 파일을 고치며 처리 — Phase 4 표에서 처리 완료로 센다
  - `__init__.py` 6개의 재수출은 Phase 3 항목이지만 `direction_profile`·`build_direction_table` 을 재수출하던 두 파일이 import 에러를 내므로 **Phase 2 에서 여섯을 한꺼번에** 걷었다. 착수 전 스캔(스크래치 `check_pkg_imports.py`): 패키지 경로로 이름을 가져가는 곳 0 · 패키지 자체 import 0 · 문자열 경로 참조 0
  - §12.1 「`COLUMN_LABELS` 죽은 원자료 레이블 8개」 — 감사의 `label_only.py` 재실행 결과 14건이 감사 때와 같고 전부 행 조립용 사전(실질 0) → **이미 정리됨.** 「도달 불가 분기」는 원문이 자리를 특정하지 않아 확인하지 못했다(`_Accumulator` 는 Non-Goals 의 설계 변경)
  - `NOTE_STOP_BASE`: 둘 다 쓰인다 — `execution/constants.py` 것은 중간선거_사이클이, `reverse/trading.py` 것은 역방향이. 문장이 「전부」 한 단어 다르고 역방향 `summary.json` 의 `notes` 에 실리므로 합치면 산출물이 바뀐다 → 건드리지 않고 인계 메모로
  - `src/verify_lab/CLAUDE.md` 는 `screen_candidates` 행 하나만(「진입점 둘」 → 「하나」)
  - 검증: AST 재스캔 A 0 · B 는 의도(선물 검산 엔진 10)와 Phase 3 연결 대상(`IDENTITY_COLUMNS` 둘 · `tracks_of_kind` · `KINDS`)뿐. 지정 테스트 96 passed · Ruff 통과
- 2026-09-26 21:53: Phase 3 완료
  - `__init__` 6개는 Phase 2 에서 끝냈다(위). 선언된 `__all__` 0 — `data/__init__.py` 에 남은 `__all__` 은 docstring 의 낱말이다
  - `IDENTITY_COLUMNS`: runner 는 손으로 순서를 적던 세 자리(방향별 · `역방향 전체` · 신호 없는 창)를 새 도우미 `_identity` 로, trading 은 기존 `_identity` 를 **키로 짝지은 값 사전 → `IDENTITY_COLUMNS` 순서로 뽑기**로. 위치로 짝짓는 `zip` 을 쓰지 않은 것은 상수의 순서를 바꿨을 때 값이 다른 컬럼으로 조용히 밀리기 때문이다. 바이트 대조는 Phase 5 재실행이 판정
  - `tracks_of_kind`: `test_output_contract.py` 에 `OUTPUT_FIXTURES`(slug → 픽스처 이름)와 `TestCoverage.test_레지스트리의_매매법마다_픽스처가_있다` 를 두고, 매매법 둘을 손으로 적던 parametrize 목록을 그 표로. 변형(`tracks.py` 에서 중간선거_사이클을 `KIND_PROPERTY` 로) → **실패**, 원복. 테스트 본문의 `(이름, 표)` 튜플 목록은 픽스처 값을 직접 쓰는 자리라 그대로 두었다 — 새 매매법이 오면 위 테스트가 먼저 실패해 그 자리를 알린다
  - 메타 키: `run_reverse.py`(`"reverse"`) · `run_midterm_cycle.py`(`"midterm_cycle"`)의 관용이 **모듈 상수에 slug 리터럴**이라 셋도 같은 모양으로 값만 바꿨다(`TRACK_NAME` 을 쓰면 다섯 중 셋만 방식이 달라진다). `meta.json` 은 git 제외라 산출물 diff 없음. meta_manager 에 타입 허용목록 없음
  - 검증: 패키지 경로 import 0 · 관련 테스트 7 파일 250 passed
- 2026-09-26 22:05: Phase 4 완료
  - AUDIT_slim_doc_code_mismatch §2 행별 처리 — **처리**: `midterm_cycle/__init__.py` · `execution/__init__.py`(폴더 → 행위) · `reverse/trading.py:1,7-9`(모듈 docstring — 보유 한도 D+2 · 손절선 −5% 하나, 결정 ⑤·⑥·⑭ 가리킴) · `reverse/constants.py:260-264`·HOLD_LIMIT(결정 ⑤·⑥ 가리킴, 옛 수치 제거) · `reverse/runner.py` 블록 개수 넷(`_SpecBlocks` 넷 · `_ReverseAllBlocks` 셋 · 두 docstring 의 「판정 표」) · `run_reverse.py`/`reverse/runner.py:289` 「국내 두 기준」 · `forward_return.py` 「병기」 · `screening.py` 전부(Phase 2) · `report/tables.py:570`(함수와 함께 삭제) · `report/constants.py:114·183·194·201·234-235` · `periods.py:113·122·337·15-22` · `strategy/` 경로 전부(`execution/constants.py` · `common_constants.py` · `report/run_summary.py` · `execution/run_summary.py` · `measure/statistics.py` · `position.py` · `validate_project.py`) · 「세 매매법」 전부 · 삭제 매매법을 현재 사용처로 적은 곳 전부(`trade_fill.py` · `run_summary.py` · `report/constants.py` · `reverse/trading.py:400` · `distribution.py`) · `execution/constants.py:41·53-54` · `report/run_summary.py:39·65` · `report/writer.py:5·78` · `common_constants.py:163-164` · `futures_leverage/constants.py:245` · `ecos_collector.py:91`(반올림 표 인용 — 경로는 `~/`) · `midterm_cycle/constants.py:13·165`·`trading.py:26` · `reverse/trading.py:209-210` · 테스트 주석(Phase 1)
  - **⑥ 으로 넘긴 행**(달력 조사 문서를 가리키는 포인터): `common_constants.py:133` · `data/pykrx_collector.py:388` · `tests/test_pykrx_collector.py:677·688`(`docs/조사/월말_진입/설계.md` §7.4 — 감사는 §7.6 이 맞다고 봤다) · `execution/constants.py:231`(§7.6) · `execution/constants.py:243·254·259` 의 「(결정 ㊵·㊷·㊶)」(출처 없는 번호 — `docs/조사/옵션_만기일/설계.md` 의 것)
  - **⑦ 로 넘긴 행**(원달러 그리드 설계·사양서 포인터와 그리드를 현재형으로 적은 목적 문장): `studies/usdkrw_equivalence/__init__.py:4-5` · `scripts/run_usdkrw_equivalence.py:5` · `scripts/data/collect_pykrx.py:8-9` · `data/ecos_collector.py:89` 의 설계 문서 포인터 · 등가성 코드의 그리드 포인터 전부
  - §3(과거형): 코드 쪽 전부 처리 — `execution/constants.py:50-51·114·203-205` · `trade_fill.py:145-147` · `report/constants.py:22-23·96` · `report/writer.py:16-17` · `measure/statistics.py:222` · `position.py:72` · `cycle_calendar.py:36` · `reverse/constants.py:178-179` · `measure/constants.py:6`(2-b/2-c) · `validate_project.py:23-24·42` · `run_futures_leverage.py:101-102` · `run_usdkrw_equivalence.py:196-198` · 테스트(`test_validate_project.py` 셋 · `test_layer_contracts.py:1249-1250·1338·1465-1467` · `test_output_contract.py` 둘). 코드를 말로 옮긴 주석 13줄(`validate_project.py`) 삭제 — 도구 동작을 알려 주는 주석(「exit code 1 반환」 · 파싱 형식)은 남겼다. `tracks.py:6-8` 은 Non-Goals(④)
  - §12.1 「③」: `STOP_LOSS_LEVEL`·`HOLD_LIMIT` 주석과 테스트 docstring 둘을 결정 ⑤·⑥ 포인터로, 격자 전제 주석(「네 번 반복」·「격자 안에서」·모듈 docstring 의 보유 한도 비교 축)을 현재 구성으로, 「지웠다」 셋(`reverse/constants.py` K=20 · `reverse/trading.py` · `run_reverse.py`)을 현재형으로 — `9126c54` 는 되살리는 자리를 가리키는 포인터라 남겼다(`.claude/rules/trading.md` 가 같은 SHA 를 적는다). 넷째로 셀 만한 것은 찾지 못했다. `cycle_calendar.py:36`·`midterm_cycle/constants.py:6-7` 처리
  - `python.md` 경로 7곳 → `~/.claude/rules/python.md`
  - **남은 grep 1 줄(전부 의도)**: 레지스트리(`tracks.py:85-86` · `test_tracks.py:302·307`) · 금지목록(`test_report_writer.py:238` · `test_output_contract.py:1403`) · 중간선거_사이클의 「월말」 분할 어휘(`split_entry.py` · `constants.py:250·258` · `trading.py:208` · `cycle_calendar.py:248·289` · 테스트 셋) · 측정 기록(`execution/constants.py:159` · `periods.py:15` · `statistics.py:334` · `test_measure_statistics.py:1109` · `test_output_contract.py:1444`) · 계약 테스트의 과거 사고 기록(`test_layer_contracts.py:25-26·423·862·895·921-922·1247·1321·1347·1520` — 감사가 「잔재 아님」으로 분류) · `test_report_tables.py:736`(같은 성격) · ⑥ 포인터 넷. `.md` 두 개(`src/verify_lab/CLAUDE.md` · `scripts/CLAUDE.md`)는 Non-Goals(④)
  - 전체 pytest 1,239 passed(1,282 − 43: 게이트 −33 · trade_fill 중복 −1 · reverse 중복 −2 · csv 문자열 −1 · 방향 표 −7 · 커버리지 +1) · Ruff 통과
- 2026-09-26 (22:05 이후 · 시각 미확인): Phase 5 — 재실행 대조 1차. 사용자 커밋 두 건이 아직 없어, Phase 0 산출물(③ 코드 변경 전)을 스크래치에 떠 두고 5개 재실행 뒤 `diff -r -x meta.json` → **동일.** `git diff --stat storage/results/` 는 따로 커밋할 `full_period.csv` 하나뿐. `docs/COMMANDS.md` 에 바뀐 이름 없음 → 변경 없음. `black .` 2개 파일
- 2026-09-26 (시각 미확인): `/code-review xhigh` 가 주간 한도로 멈춤 — 세션 중단
- 2026-09-28 07:14: 재개. 작업 트리 그대로(60개), 사용자 커밋 두 건은 아직 없음
- 2026-09-28 07:20: `/code-review xhigh` 1회차 — 15건, 버그 0(실행 코드가 틀린 값을 내는 결함 없음). 이 계획서가 만든 A(#1) · B(#10) · C(#11 · #12 · #13)를 사용자 결정으로 고침(Notes). #1 · #12 는 직접 재현해 확인(AST 상수 `['.csv', '.csv']` → 매치 0 · `measure` 칸에 `rule` 없음, 조사 요약에 `datasets`·`rule` 없음)
- 2026-09-28 07:30: A · B · C 반영
  - A: `_FILENAME_SHAPE` `+` → `*`. 변형 셋 — `f"{TRACK_NAME}.csv"` · `TRACK_NAME + ".csv"` → **실패**, `f"결과는 {TRACK_NAME}.csv 에 저장합니다"`(산문) → 통과. 원복을 `cmp` 로 확인
  - B: 두 `_identity` 에 키 집합 불일치 `RuntimeError`. 변형(runner 의 `IDENTITY_COLUMNS` 에서 `DISPLAY_ERA` 제거 · trading 에서 `DISPLAY_STOP_LEVEL` 제거) → 둘 다 「내부 불변조건 위반」, 원복을 `cmp` 로 확인
  - C: `writer.py` docstring 을 실제 키로(매매법은 `measure`·`trade` 칸의 `datasets` 와 `trade.rule`, 조사는 `pairs`·`inputs`) · `execution/constants.py` 모듈 docstring 「매매법 전부가 함께 쓰는」 → 「매매법을 가리지 않는」, `NOTE_STOP_BASE` 주석에 「지금 쓰는 곳은 중간선거_사이클 하나」 · `test_report_tables.py` 주석 현재형
  - `black .` 2개 파일
- 2026-09-28 07:33: 재실행 대조 2차 — 스크래치 스냅숏이 세션 공백 뒤 사라져 **HEAD 대비**로 했다. 5개 rc=0, `git diff --stat storage/results/` 는 `full_period.csv` 하나이고 그 8행이 Phase 0 의 값(1829→1842 · 1721→1734 · 3458→3471 · 1834→1848 · 2751→2765 · 1835→1849 · 1850→1864 · 2751→2765)과 같다 — 나머지 산출물은 HEAD(= ③ 이전)와 바이트 동일. **DoD 「diff 가 비어 있다」는 사용자가 그 파일을 따로 커밋한 뒤의 HEAD 를 기준선으로 한다**(Notes 의 결정)
- 2026-09-28 07:35: 보고서 §12.5(리뷰 그 외 T1 ~ T9 · 고친 A · B · C) · `SLIM_SERIES.md` ③ 인계 메모(⑥ · ⑦ 포인터 목록 포함) · 진행 표 「커밋 대기」
- 2026-09-28 07:38: `validate_project.py` — Ruff OK · PyRight OK · Pytest passed=1239 failed=0 skipped=0
