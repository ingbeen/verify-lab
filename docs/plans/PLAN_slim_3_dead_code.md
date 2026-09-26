# Implementation Plan: 경량화 ③ — 데드 코드 · 테스트 결함과 잔재 · 틀린 주석 정리 (산출물 바이트 불변)

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

- [ ] 목표 1: 운영·테스트 어디서도 쓰지 않는 정의와, 결론이 난 축의 잔여물(월말 「방향 표」 계열 · 판정표 잔여)을 지운다
- [ ] 목표 2: **무력화된 테스트**와 삭제 매매법 잔재, 공유 계층 테스트의 매매법 상수 의존, 중복 테스트를 고친다
- [ ] 목표 3: 「연결 누락」 셋을 **쓰게 만든다** (`IDENTITY_COLUMNS` 둘 · `tracks_of_kind`)
- [ ] 목표 4: 코드 주석·docstring·도움말의 틀린 서술(삭제 매매법 · 옛 `strategy/` 경로 · 「세 매매법」 · 과거형 · 버린 근거)을 현재형 사실로 고친다
- [ ] 목표 5: 메타 타입 키를 `<slug>` 로 통일한다
- [ ] 목표 6: **산출물이 한 바이트도 바뀌지 않는다** — 5개 실행 스크립트를 다시 돌려 `storage/results/` diff 0

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

- [ ] 보고서 §2.1 · §2.2 의 정의가 저장소에 없다 (AST 재스캔으로 확인)
- [ ] `test_report_writer.py` 가 같은 등급의 다른 매매법으로 검사한다 — **등급 폴더를 비우는 변형을 넣으면 실패함을 확인**했다
- [ ] 게이트 테스트가 `direction_profile` 없이 운영 경로(`screen_verdict`)를 고정한다
- [ ] 삭제 매매법 잔재·중복 테스트가 없고, 공유 계층 테스트가 매매법 상수를 import 하지 않는다
- [ ] `IDENTITY_COLUMNS` 둘과 `tracks_of_kind` 가 운영·테스트에서 실제로 쓰인다 (손으로 적은 목록이 사라졌다)
- [ ] `__init__.py` 6개가 재수출하지 않는다
- [ ] 메타 타입 키가 스크립트 전부에서 `<slug>` 다
- [ ] 주석·docstring 불일치 목록(AUDIT_slim_doc_code_mismatch §2·§3, AUDIT_slim_dead_code D, 보고서 §12.1 「③」)이 처리됐다 — Non-Goals 로 넘긴 것은 인계 메모에 남긴다
- [ ] 🔴 **5개 실행 스크립트 재실행 후 `git diff --stat storage/results/` 가 비어 있다**
- [ ] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [ ] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [ ] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [ ] 필요한 문서 업데이트 — `docs/COMMANDS.md` 변경 없음(메타 키는 COMMANDS 에 없다) · 지운 이름을 가리키는 계약 문서 줄만 수정 · `SLIM_SERIES.md` 갱신
- [ ] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다 (중복 테스트를 어느 쪽으로 남겼는지·연결 누락을 어떻게 이었는지의 «왜»는 남긴 테스트/코드의 docstring 에, 뒤 계획서가 알아야 할 것은 `SLIM_SERIES.md` 인계 메모에)
- [ ] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

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

- [ ] 착수 전: `git status` 깨끗 · 계획서 ② 커밋 확인 · 수집 테스트 수를 진행 로그에
- [ ] 5개 실행 스크립트를 인자 없이 돌린다 — `scripts/run_{reverse,midterm_cycle,leverage_tracking,futures_leverage,usdkrw_equivalence}.py` (명령은 `docs/COMMANDS.md`). 외부 호출이 없고 `storage/market/`·`storage/series/` 만 읽는다
- [ ] 재현을 확인한 뒤에야 그 diff 를 이 계획서의 통과 기준으로 쓸 수 있다
- [ ] AUDIT_slim_dead_code 머리의 방법(AST 로 import 체인·재수출을 따라 참조를 세고, 스크립트·`validate_project.py` 최상위를 뿌리로 도달 가능성 계산)으로 스캔 스크립트를 **스크래치에** 쓰고 돌려, §2.1·§2.2 목록이 지금도 같은지 확인한다 — 다르면 진행 로그에 적고 지금 결과를 따른다

**Validation**:

- [ ] `git diff --stat storage/results/` 가 비어 있다 — **비어 있지 않으면 멈추고 사용자에게 보고한다**(시세나 환경이 바뀐 것이라 이 계획서의 기준이 성립하지 않는다)

---

### Phase 1 — 테스트 결함과 잔재 (그린 유지)

**작업 내용**:

- [ ] `tests/test_report_writer.py`: `OTHER_TRACK_NAME` 을 **reverse 와 같은 등급**의 slug(`midterm_cycle`)로. 그 뒤 `create_run_directory` 에 「등급 폴더를 통째로 비우는」 변형을 **잠깐** 넣어 `test_clearing_keeps_other_tracks_in_the_layer` 가 실패하는지 보고 되돌린다(돌이킨 것을 진행 로그에). slug 목록(삭제 매매법 옆, `midterm_cycle` 누락)도 채운다
- [ ] `tests/test_execution_trade_fill.py`: reverse 의 `HOLD_LIMIT`·`STOP_LOSS_LEVEL` import 를 **자기 픽스처 값**으로 바꾸고 `assert HOLD_LIMIT == 2` 를 지운다 — 그 사실은 `tests/test_studies_reverse_trading.py` 가 이미 고정한다 (`docs/MEMORY.md` 「공유 계층의 테스트는 자기 픽스처를 갖는다」)
- [ ] 중복 테스트: ① 제외 컬럼 없음(`test_studies_reverse_trading.py` 쪽이 `test_output_contract.py` 의 하위집합 → 하위집합 삭제) ② 구간 5행(같은 방식) ③ 스크립트의 `.csv` 문자열 — **`test_output_contract.py` 의 `test_매매_스크립트에_csv_문자열이_없다` 를 지운다.** `test_layer_contracts.py` 의 두 검사(`*_FILENAME` 정의 금지 · 파일 이름 모양 리터럴 금지)가 같은 목적을 **산문 예외까지 설계해** 지키는데, 부분 문자열 전면 금지가 그 예외를 무력화한다
- [ ] `tests/test_output_contract.py`: 삭제 매매법 상수 `AXIS_OPTION_EXPIRY`·`AXIS_MONTH_END`·`EXPIRY_MONTH` 와 도달 불가 분기(`EXPIRY_TARGET_DATE_COLUMN` · `_expected_trades(target_date=)`)를 지운다. 매매법이 둘인데 「세_」로 시작하는 테스트 함수 이름과 docstring(「세 매매법」·「역방향·월말이 계속 그 이름을 낸다」·`grid.csv`)을 현재 사실로. `midterm_cycle_outputs` 픽스처 docstring 의 「10월 진입 · 사이클 네 자리」를 9월 마지막 거래일 · 중간선거해 한 칸으로 (리뷰 R8)
- [ ] `tests/test_index.py` 실패 메시지(리뷰 R9): 「무엇이 잘못됐고 무엇을 해야 하는지」가 되게 — 되살아난 경로와 **「지우거나, 되살려야 한다면 `REMOVED_DOCUMENTS` 의 그 줄과 사유를 먼저 고친다」** 를 함께. 사유가 없는 앞 세 항목에는 블록 주석이 사유임을 한 줄로 밝힌다
- [ ] `tests/test_studies_extreme_move.py` 의 미사용 `EXACT_TOLERANCE`
- [ ] 틀린 테스트 주석: `test_measure_screening.py` 의 「60% 게이트를 못 넘어 제외」(실제 이유는 기대값 하한), `test_layer_contracts.py` 의 없는 `screen_candidates`·「네 이름」·「매매법 셋」, 허용목록 머리 주석의 달력형 어휘, `_KNOWN_LABEL_DUPLICATES` 의 futures 항목(Phase 2 와 함께)

**Validation**:

- [ ] 고친 테스트 파일만 직접 돌려 통과 (`poetry run pytest <파일들> -q`)
- [ ] 무력화 테스트의 변형 실험 결과(실패 확인 → 원복)가 진행 로그에 있다

---

### Phase 2 — 데드 코드 삭제와 게이트 테스트의 경로 교정 (그린 유지)

**작업 내용**:

- [ ] 🔴 **먼저 게이트 테스트를 운영 경로로 옮긴다** — `tests/test_measure_screening.py` 에서 `direction_profile` 을 거치는 테스트(헬퍼 `_verdict` 계열)를 `screen_verdict` 를 직접 부르는 형태로 다시 쓴다. **검사하는 계약(경계값 · 방향 · 보합 · `tradable`)은 하나도 줄이지 않는다** — 테스트 수가 줄면 무엇이 합쳐졌는지 진행 로그에 적는다
- [ ] 그다음 지운다: `direction_profile`·`_direction_row`·`DIRECTION_COLUMNS`·`REQUIRED_SUMMARY_COLUMNS`·`COL_HIT_RATE`·`COL_EXPECTED_VALUE`·`COL_TOTAL_RETURN`(screening.py), `build_direction_table`·`DISPLAY_HIT_RATE`·`DISPLAY_EXPECTED_VALUE`·`DISPLAY_TOTAL_RETURN`(report), `tests/test_report_tables.py` 의 `TestDirectionTable`
- [ ] `COL_SCREEN`·`DISPLAY_BASIS`: 테스트의 「없어야 한다」 가드는 **문자열 리터럴**로 바꾼 뒤 상수를 지운다 (가드는 남는다)
- [ ] 완전 미사용 4개(보고서 §2.1) + `_KNOWN_LABEL_DUPLICATES` 의 futures 항목
- [ ] 쓰이지 않는 인자(보고서 §2.6): `run_reverse_trading(hold_limit=)` · futures `run_study(horizons, market_dir, series_dir)` · `collect_pykrx_nav(output_dir=)` — 호출처를 다시 grep 해 **전부 기본값만 쓰는지** 확인하고 지운다
- [ ] 백로그 §12.1 「③」의 「`COLUMN_LABELS` 죽은 원자료 레이블 8개 · 도달 불가 분기」(중간선거_사이클): **지금도 있는지 먼저 확인**한다 — 있으면 지우고, 없으면 「이미 정리됨」을 진행 로그에
- [ ] `execution/constants.py` 의 `NOTE_STOP_BASE`: `reverse/trading.py` 에 같은 이름·다른 값이 있다. 참조를 세어 **쓰지 않는 쪽이면 지우고**, 둘 다 쓰이면 건드리지 않고 인계 메모에 남긴다
- [ ] 지운 이름을 가리키는 `src/verify_lab/CLAUDE.md` 줄(없는 `screen_candidates` 등)은 **이름만** 현재 것으로 — 문서 전체 정리는 ④

**Validation**:

- [ ] AST 재스캔에서 보고서 §2.1 · §2.2 목록이 0
- [ ] `poetry run pytest tests/test_measure_screening.py tests/test_report_tables.py tests/test_layer_contracts.py -q` 통과

---

### Phase 3 — 재수출 제거 · 연결 누락 · 메타 키 (그린 유지)

**작업 내용**:

- [ ] `__init__.py` 6개(`data` · `measure` · `report` · `utils` · `studies/reverse` · `studies/midterm_cycle`)의 재수출과 `__all__` 을 걷고 패키지 docstring 만 남긴다. **먼저** `from verify_lab.<패키지> import <이름>` 이 운영·테스트에 0건인지, 하위 모듈 선로딩 부작용에 기대는 곳이 없는지(`import verify_lab.<패키지>` 뒤 `.하위모듈` 속성 접근) grep 으로 확인한다. `test_layer_contracts.py` 의 「`__all__` 재등장 금지」 검사와 부딪히지 않는지 본다
- [ ] `IDENTITY_COLUMNS`(`studies/reverse/runner.py` · `trading.py`): 같은 순서를 손으로 다시 적는 자리(runner 의 표 조립 · trading 의 행 조립)가 **그 상수를 쓰게** 한다 — 순서가 바이트까지 같아야 한다(Phase 4 의 재실행이 판정)
- [ ] `tracks_of_kind`·`KINDS`: `tests/test_output_contract.py` 가 매매법 둘을 손으로 적는 자리를 `tracks_of_kind(KIND_METHOD)` 로 — 「매매법이면 성적표를 낸다」 계약이 레지스트리를 따라가게 한다
- [ ] 메타 타입 키: `run_futures_leverage.py`·`run_leverage_tracking.py`·`run_usdkrw_equivalence.py` 의 `*_study` 를 그 slug(`TRACK_NAME`)로 — 가능하면 리터럴이 아니라 그 매매법 `constants.py` 의 `TRACK_NAME` 을 쓴다(나머지 두 스크립트의 관용을 확인하고 맞춘다)

**Validation**:

- [ ] 운영·테스트에서 `from verify_lab.<패키지> import` 형태 0건, `__all__` 0건(패키지 `__init__`)
- [ ] 관련 테스트 파일 통과

---

### Phase 4 — 주석·docstring·도움말 (그린 유지)

**작업 내용**:

- [ ] AUDIT_slim_doc_code_mismatch §2 표의 코드 주석 행을 전부 처리한다 — **Non-Goals 로 넘기는 행**(달력 조사 문서·원달러 그리드 설계·사양서를 가리키는 포인터)만 빼고. 묶음: 삭제 매매법을 현재 사용처로 적은 곳 · 없는 `strategy/` 경로 · 「세 매매법」「나머지 두 매매법」 · 정반대(`execution/__init__.py` 「경계는 폴더 단위」 → 「행위」) · 전면 낡음(`studies/midterm_cycle/__init__.py`·`constants.py:13,165`) · 개수 틀림(`reverse/runner.py` 블록 개수, `reverse/trading.py` 모듈 docstring) · 정책과 모순(`measure/forward_return.py` 「병기」) · 「`통계.csv` 가 기준선 14 + 차이 4」(`screening.py`·`report/tables.py`·`report/constants.py`) · 틀린 경로(`futures_leverage/constants.py` 의 `docs/.claude/...`, 코드 주석의 `.claude/rules/python.md` → 전역 `~/.claude/rules/python.md`) · `ecos_collector.py` 의 반올림 표 인용 · `common_constants.py` KST 설명 · `report/writer.py` 예시 · `report/run_summary.py` 「여섯 산출 지점」·`expiry_count`
- [ ] AUDIT_slim_doc_code_mismatch §3 — 과거형·변경 이력·계획 단계 표기(「Phase」「2-a/2-b/2-c」)를 현재형으로, 코드를 말로 옮긴 주석(`validate_project.py` 의 「# Ruff 출력 표시」 류)은 지운다. **담긴 「왜」는 남긴다** — 시제만 바꾼다
- [ ] 보고서 §12.1 「③」: `studies/reverse/constants.py` 의 `STOP_LOSS_LEVEL`·`HOLD_LIMIT` 주석(버린 「갭손절 0건」 근거와 옛 수치 → `docs/매매/역방향/규칙.md` 결정 ⑤·⑥ 의 현재 근거를 한 줄로 가리키게) · `reverse/trading.py` 의 격자 전제 주석(리뷰 R10 — **구조는 그대로**) · 새 코드 주석 넷의 「지웠다」·커밋 해시·날짜 · `cycle_calendar.py`·`midterm_cycle/constants.py` 과거형 docstring
- [ ] `scripts/run_reverse.py` `--dataset` 도움말의 「국내 두 기준의 대조는 함께 돌려야 성립」(국내 대상은 원본가 하나) — 사용자에게 보이는 문구라 한글로 정확하게
- [ ] `tracks.py` 의 주석 정리는 **하지 않는다** — 등급 정의 문구 중립화(L2)와 같은 줄이라 계획서 ④ 가 함께 한다

**Validation**:

- [ ] `grep -rn -E 'strategy/|세 매매법|option_expiry|month_end|옵션 만기일|월말' src scripts tests validate_project.py` 의 남은 줄이 **의도된 것뿐**(레지스트리 · 금지목록 · Non-Goals 포인터)이고 그 목록이 진행 로그에 있다
- [ ] `grep -rn '\.claude/rules/python\.md' src scripts tests` 가 `~/` 형태뿐

---

### Phase 5 (마지막) — 재실행 대조 · 문서 정리 · 최종 검증

**작업 내용**

> 🔴 **`/commit` 이 «맨 마지막»인 것은 의도다.** 그 스킬은 「후보 뒤에는 아무것도 덧붙이지 말 것」으로
> 끝나므로 **호출하는 순간 그 턴이 거기서 닫힌다.** 중간에 두면 뒤에 적힌 항목이 그 벽 너머에 남는다 —
> 실제로 두 번 그렇게 샜다(`[실측] 2026-09-14` 후보를 계획서에 안 옮김 · `2026-09-16` 옮기고 체크박스를 안 닫음).
> **체크박스와 상태를 먼저 확정하고, 커밋 후보를 마지막에 만든다.**

- [ ] 🔴 5개 실행 스크립트를 인자 없이 다시 돌리고 `git diff --stat storage/results/` 가 **비어 있음**을 확인한다 — 비어 있지 않으면 어느 변경이 값을 바꿨는지 찾아 되돌린다(이 계획서는 값을 바꾸지 않는다)
- [ ] 필요한 문서 업데이트 (`docs/COMMANDS.md` 변경 없음 확인)
- [ ] 보고서 §12 백로그 갱신 — Non-Goals 로 넘긴 항목과 리뷰 「그 외」
- [ ] `SLIM_SERIES.md` 진행 표 · 인계 메모 갱신 (⑥ · ⑦ 에 넘긴 주석 포인터 목록을 반드시 남긴다)
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

- **동적 참조를 놓쳐 운영이 깨진다** (`getattr`, pandas 컬럼명으로 쓰이는 상수) — 지우기 전 문자열 grep 을 함께 하고, 최종 재실행 대조가 잡는다
- **게이트 테스트를 옮기며 계약이 조용히 빠진다** — 옮기기 전 테스트 목록(이름 · 검사하는 경계)을 진행 로그에 뽑아 두고 옮긴 뒤 대조한다
- **재수출 제거가 import 순서 부작용을 깬다** — 특히 pykrx 는 import 자체가 로그인을 시도한다(`src/verify_lab/CLAUDE.md` 「pykrx import 순서」). `data/__init__.py` 가 무엇을 먼저 불러오는지 보고, 테스트와 5개 스크립트 재실행으로 확인한다
- **`IDENTITY_COLUMNS` 연결이 컬럼 순서를 바꾼다** — 재실행 바이트 대조가 잡는다
- **주석 대상이 너무 많아 일부를 놓친다** — AUDIT 표의 행마다 처리/이관을 진행 로그에 표시한다
- **`VIRTUAL_ENV`** — 모든 도구가 실패하면 `env -u VIRTUAL_ENV`

## 8) 메모(Notes)

- 시리즈의 SoT 는 루트 `SLIM_SERIES.md`. 이 계획서는 ③ 이며 **커밋 하나**로 끝난다
- 감사 원문의 줄 번호는 `f55617a` 기준이다. ① · ② 가 바꾼 파일(`tests/test_index.py`, 개명한 5개, `src/verify_lab/CLAUDE.md` 등)은 줄이 밀렸다

### 진행 로그 (KST)

- 2026-09-26 16:55: 계획서 작성 (Draft). 중복 테스트 ③ 의 처리(부분 문자열 전면 금지 쪽 삭제)는 작성 시점에 두 테스트를 읽고 정했다 — `test_layer_contracts.py` 쪽 docstring 이 산문 예외를 의도적으로 설계했다
