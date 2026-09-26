# Implementation Plan: 만기_말일 조사 강등과 실행 코드 삭제

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

**작성일**: 2026-09-26 10:33
**마지막 업데이트**: 2026-09-26 10:41
**관련 범위**: tracks, studies/expiry_monthend, measure(달력), report, scripts, tests, docs, storage/results
**관련 문서**: src/verify_lab/CLAUDE.md, scripts/CLAUDE.md, tests/CLAUDE.md, .claude/rules/trading.md, .claude/rules/docs.md, .claude/rules/research.md

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

- [x] 목표 1: **`만기_말일` 을 조사 등급으로 내린다** — `tracks.py` 의 한 줄을 `GRADE_SURVEY` + `KIND_PROPERTY` 로. 앞선 강등 셋(`옵션_만기일`·`월말_진입`·`원달러_그리드`)과 같은 자리다
- [x] 목표 2: **실행 코드를 지운다** — `studies/expiry_monthend/` 패키지 · `scripts/run_expiry_monthend.py` · 전용 테스트 둘. 계약 테스트는 **만기_말일이 지키던 공유 계약을 중간선거_사이클 픽스처로 옮겨** 검사 범위를 유지한다
- [x] 목표 3: **이 삭제로 쓰는 곳이 없어진 공유 정의를 정리한다** — `measure/calendar_exit.py` 전체 · `measure/calendar_entry.py` 의 `validate_trading_days` 외 전부 · 상수 둘(`REASON_NO_EXPIRY_DAY` · `DISPLAY_MONTH_NUMBER`) · 그 테스트
- [x] 목표 4: **문서와 산출물을 조사 자리로 옮기고 결정을 남긴다** — `docs/매매/만기_말일/` → `docs/조사/만기_말일/`, `storage/results/매매/만기_말일/` → `storage/results/조사/만기_말일/`(바이트 불변), 강등 결정과 복원 절차를 문서에 적는다

## 2) 비목표(Non-Goals)

- **「승률 75% 초과」 기준을 도입하지 않는다.** 사용자가 고려 중인 단계다 — `screening.py` 게이트·루트 `CLAUDE.md`·`trading.md` 어디에도 적지 않는다
- **QQQ 를 이 매매법으로 잰 스크래치 결과를 문서에 싣지 않는다** (2026-09-26 사용자 결정 — 임시로 본 값)
- **성적 값을 바꾸지 않는다.** 재선정·재측정·시세 재수집 없음. 만기_말일 산출물은 **옮기기만** 한다
- **역방향·중간선거_사이클의 등급과 산출물을 바꾸지 않는다** — 재실행해 바이트 불변을 확인만 한다
- **`validate_trading_days` 를 옮기지 않는다.** 중간선거_사이클이 쓰는 살아 있는 코드다 — 깨지지 않은 코드를 옮기지 않는다
- **날짜가 붙은 실측·결정 기록은 고치지 않는다** — `docs/MEMORY.md` 의 `[실측] 2026-09-22` 절, 각 `설계.md` 의 「확정된 설계 결정」·탈락안 문장(과거형이 허용되는 자리). 거기 적힌 파일 이름이 지워져도 **그때의 기록**이다
- **기존 테스트의 빈틈을 메우지 않는다** — 예: `test_report_writer.py` 의 slug 목록에 중간선거_사이클이 없는 것은 이 변경 전부터다. 언급만 한다
- **`docs/plans/` 의 옛 계획서를 고치지 않는다** (임시 문서) · **`docs/context/` 를 건드리지 않는다** (사용자 소유)

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

- **사용자 판단 (2026-09-26): 승률이 너무 낮다.** 확정 칸 전체 구간(손절 −5%) 승률이
  SPY **66.67%**(33건) · DIA **67.86%**(28건) · KODEX 코스닥150 **70.0%**(10건)다. 그래서 걸지 않는다
- **코드까지 지운다 (같은 날 사용자 결정 B).** 등급만 내리고 코드를 두는 안(A)은
  `tests/test_tracks.py` 의 `test_조사_등급은_종류도_조사다`(조사 등급 ⇒ 성적표를 내지 않는 종류)를
  완화해야 했고, 앞선 강등 셋이 모두 코드를 지운 선례와도 갈린다
- **공유 달력 계층이 딸려 간다.** AST 참조 스캔(고정점 반복, `__all__` 문자열 제외)으로
  이 삭제 뒤 **운영 코드(src·scripts) 참조가 0 이 되는 정의**를 셌다:
  - `measure/calendar_exit.py` — 13개 (파일의 공개 정의 전부)
  - `measure/calendar_entry.py` — 9개 (`ExpiryRule`·`nth_weekday_of_month`·`monthly_expiry_dates`·`month_entry_dates`·`every_day_entries`·`EXPIRY_FRAME_DTYPES`·`EXPIRY_MONTH_FORMAT`·`MIN_CALENDAR_DAY`·`MAX_CALENDAR_DAY`). **`validate_trading_days` 는 중간선거_사이클이 쓴다**
  - `measure/constants.py` 의 `REASON_NO_EXPIRY_DAY` · `report/constants.py` 의 `DISPLAY_MONTH_NUMBER`
  - 이 스캔은 **삭제될 파일의 import 줄도 참조로 셌으므로** `ENTRY_DTYPES`·`empty_entries` 같은 것은
    Phase 2 에서 `calendar_exit.py` 까지 지운 상태로 **다시 스캔해** 확정한다
- 전역 `~/.claude/CLAUDE.md` 「본인 변경으로 생긴 orphan 만 정리한다」에 따라 위 정의를 지운다.
  **남겨 두면 소비자 0 인 공유 계층이 된다** — `src/verify_lab/CLAUDE.md` 가 「정의가 하나뿐인 것을
  공유 계층에 두면 어느 매매법의 값이 기본값인가라는 문제만 생긴다」고 적은 상태보다 나쁘다

### Phase 를 이렇게 묶은 이유

**문서 링크 검사가 코드와 문서를 같은 순간에 요구한다.** `tests/test_research_docs.py` 는 결과 문서의
「관련 파일」 경로가 실재해야 하고, `tests/test_tracks.py` 는 `docs/INDEX.md` 의 등급 칸을 `tracks.py` 와
대조하며, `tests/test_index.py` 는 문서 파일 목록을 지도와 대조한다. 그래서 **코드를 지우는 Phase 가
그 코드를 가리키는 문서도 함께 고쳐야** 그 Phase 끝이 초록이다. 맥락 둘로 가른다 —
**Phase 1 은 「만기_말일이라는 매매법」**, **Phase 2 는 「그 삭제가 공유 계층에 남긴 것」**.

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- `.claude/plan-config.json` — 이 저장소의 검증 명령·자동 포맷·근거 승격 목적지 (**값의 SoT**)
- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절 (값이 아니라 **판단 근거**)
- `src/verify_lab/CLAUDE.md` · `scripts/CLAUDE.md` · `tests/CLAUDE.md`
- `.claude/rules/trading.md` · `.claude/rules/docs.md` · `.claude/rules/research.md` · `.claude/rules/session-bootstrap.md`
- `docs/INDEX.md` §6 (지도 유지 규칙) · `docs/MEMORY.md`

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] `track_of("expiry_monthend")` 가 조사 등급 · 성질 조사 종류다 (테스트로 고정)
- [x] 만기_말일 실행 코드·전용 테스트가 저장소에 없고, 운영 코드에서 `expiry_monthend` 를 가리키는 곳이 `tracks.py` 한 줄뿐이다
- [x] 고아 스캔 재실행에서 **이 변경이 만든 참조 0 정의가 0건**이다
- [x] 계약 테스트가 역방향·중간선거_사이클 두 매매법으로 같은 공유 계약(손절불가 표기·한 컬럼 필터·이길 때/질 때 부호·지수 행 값)을 검사한다
- [x] `storage/results/조사/만기_말일/` 이 옛 폴더와 **바이트 동일**하고 옛 폴더가 없다
- [x] 역방향·중간선거_사이클을 재실행해 두 산출물 폴더가 **바이트 불변**이다
- [x] 저장소 전체에서 `docs/매매/만기_말일` 과 삭제된 파일을 가리키는 살아 있는 링크·경로가 0건이다 (`docs/plans/`·날짜 붙은 기록 제외)
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — `docs/COMMANDS.md` **변경 있음**(만기_말일 절 → 「코드가 없는 트랙」) · `docs/INDEX.md` · `src/verify_lab/CLAUDE.md` · `scripts/CLAUDE.md` · `.claude/rules/trading.md` **변경 있음** · 루트 `CLAUDE.md` · `docs/MEMORY.md` **변경 없음**
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (강등 결정·탈락안·근거는 `docs/조사/만기_말일/규칙.md` §3, 복원 절차는 같은 폴더 `결과.md` 머리말)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- **삭제**: `src/verify_lab/studies/expiry_monthend/`(5파일) · `scripts/run_expiry_monthend.py` ·
  `tests/test_studies_expiry_monthend_pairing.py` · `tests/test_studies_expiry_monthend_runner.py` ·
  `src/verify_lab/measure/calendar_exit.py` · `tests/test_measure_calendar_exit.py` · `tests/test_measure_calendar_month.py`
- **축소**: `src/verify_lab/measure/calendar_entry.py`(`validate_trading_days` 와 그것이 쓰는 것만) ·
  `tests/test_measure_calendar_entry.py`(`validate_trading_days` 검사만 남기거나, 없으면 삭제) ·
  `src/verify_lab/measure/constants.py`(`REASON_NO_EXPIRY_DAY` + 재스캔으로 나오는 것) ·
  `src/verify_lab/report/constants.py`(`DISPLAY_MONTH_NUMBER` + 재스캔으로 나오는 것)
- **수정 (코드)**: `src/verify_lab/tracks.py` · `tests/test_tracks.py` · `tests/test_layer_contracts.py` ·
  `tests/test_report_writer.py` · `tests/test_strategy_output_contract.py`
- **수정 (주석만)**: `src/verify_lab/execution/trade_fill.py`(달력 계층을 가리키는 두 곳) ·
  `tests/test_studies_futures_continuous.py`(삭제될 함수를 예로 든 docstring) · 재스캔으로 걸리는 주석
- **이동**: `docs/매매/만기_말일/` → `docs/조사/만기_말일/` (3파일) · `storage/results/매매/만기_말일/` → `storage/results/조사/만기_말일/`
- **문서 수정**: `docs/조사/만기_말일/{규칙,결과,설계}.md` · `docs/INDEX.md` · `docs/COMMANDS.md` ·
  `scripts/CLAUDE.md` · `src/verify_lab/CLAUDE.md` · `.claude/rules/trading.md` ·
  `docs/조사/옵션_만기일/{규칙,결과}.md` · `docs/조사/월말_진입/{규칙,결과,설계}.md`
- `docs/COMMANDS.md`: **변경 있음** — `run_expiry_monthend.py` 명령 절을 지우고 「코드가 없는 트랙」에 옮긴다

### 데이터/결과 영향

- **산출물 값 변화 없음.** 만기_말일 산출물은 폴더만 옮긴다(재실행하지 않음 — 코드를 지우므로).
  **지금 폴더가 현재 코드의 출력과 같다는 것은 2026-09-26 스크래치 재현으로 확인했다**
  (성적표 35/35행 · 거래내역 158/158행 · 측정 4/4행 값 일치)
- 역방향·중간선거_사이클은 재실행해 바이트 불변을 확인한다 — 공유 계층 삭제가 그 둘의 출력에 닿지 않았다는 증거
- 되살리는 기준 커밋: **`5022dc9`** (이 변경 직전 HEAD — 코드가 모두 있다)

## 6) 단계별 계획(Phases)

### Phase 0 — 등급 결정을 테스트로 먼저 고정(레드)

**작업 내용**:

- [x] `tests/test_tracks.py` `TestGradeSemantics` — `test_만기_말일이_매매_등급이다` 를 지우고,
      `test_걸지_않기로_한_매매법은_조사_등급이다` 의 parametrize 에 `expiry_monthend` 를 더한다.
      목적 문구에 **「2026-09-26 승률이 사용자 기준에 못 미쳐 걸지 않기로 했다」**를 적는다
- [x] 레드 확인 — `poetry run pytest tests/test_tracks.py` 에서 그 한 칸만 실패 (1 failed · 51 passed — `[expiry_monthend]` 한 칸, `'매매' == '조사'`)

---

### Phase 1 — 만기_말일을 조사 자리로 옮기고 매매법 코드를 지운다(그린 유지)

**작업 내용** — 코드:

- [x] `src/verify_lab/tracks.py` — `Track("expiry_monthend", "만기_말일", GRADE_SURVEY, KIND_PROPERTY)`.
      주석을 옵션_만기일 줄과 같은 모양으로(무엇 때문에 걸지 않기로 했고 코드를 지웠는가, 근거 문서 자리)
- [x] 삭제: `studies/expiry_monthend/` · `scripts/run_expiry_monthend.py` · 전용 테스트 둘
- [x] `tests/test_layer_contracts.py` — 매매법 slug 집합과 파일 목록에서 `expiry_monthend` 제외
- [x] `tests/test_report_writer.py` — 실제 slug 목록에서 `expiry_monthend` 제외
- [x] `tests/test_strategy_output_contract.py` — 만기_말일 픽스처·import 를 지우고,
      **그 픽스처로만 검사하던 공유 계약은 `midterm_cycle_outputs` 로 옮긴다**
      (지수 손절불가 · 거래내역 손절선 형식 · 사건 컬럼 부재 · 한 컬럼 필터 셋 · 손익분기 순서 ·
      이길 때/질 때 부호 · 지수 행 값). **만기_말일 고유 축**(`조합`·`월` 컬럼 순서)만 지운다.
      옮기기 전에 중간선거_사이클 산출물이 그 계약의 전제(ETF 무손절 행 + 손절 행 · 지수 손절불가 행)를 갖는지 확인하고,
      **옮기기 전후 테스트 수**를 적어 줄어든 것이 만기_말일 고유 축뿐인지 본다

**작업 내용** — 문서·산출물:

- [x] `mv docs/매매/만기_말일 docs/조사/만기_말일` · `mv storage/results/매매/만기_말일 storage/results/조사/만기_말일`
      → 이동 전 스크래치 사본과 `diff -r` 로 **바이트 동일** 확인
- [x] `docs/조사/만기_말일/규칙.md` — 머리에 **「걸지 않기로 한 규칙 (2026-09-26) · 실행 코드 없음」** 배너
      (옵션_만기일·월말_진입과 같은 모양). §3 에 **결정 하나 추가**: 확정 = 조사 강등·코드 삭제 /
      탈락안 = 매매 유지 · 등급만 내리고 코드 유지 / 근거 = 승률 세 값과 표본 수, 조사 등급 불변조건과 선례.
      §1 의 「확정 규칙」·§1.3 의 2026 날짜는 **그때의 기록**으로 둔다. 본문의 `docs/매매/만기_말일` 경로를 고친다
- [x] `docs/조사/만기_말일/결과.md` — 머리말에 코드 삭제·복원 절차(`5022dc9`) 배너, 「관련 파일」 표의
      매매법 코드 행을 묘비 표기(`삭제`)로, §11 재현 방법을 「재현하려면 복원」으로
- [x] `docs/조사/만기_말일/설계.md` — 「관련 파일」 표의 매매법 코드 행을 묘비 표기로. **확정된 설계 결정 본문은 그대로**
- [x] `docs/조사/옵션_만기일/{규칙,결과}.md` · `docs/조사/월말_진입/{규칙,결과}.md` —
      「지금 9월에 거는 규칙은 만기_말일」과 「그 질문은 만기_말일이 받는다」를 고친다
      (**만기_말일도 2026-09-26 조사로 내려가 지금 9월에 거는 규칙은 없다** · 복원은 git)
- [x] `docs/INDEX.md` — 만기_말일 행(등급·코드·링크·설명), 옵션_만기일·월말_진입 행의 같은 문장, §3 하단 예시 문장(`studies/expiry_monthend/constants.py`)
- [x] `docs/COMMANDS.md` — 만기_말일 실행 절 삭제, 「코드가 없는 트랙」에 한 절 추가(옵션 만기일 절과 같은 모양), 옵션 만기일 절의 「만기_말일이 받는다」 문장 수정
- [x] `scripts/CLAUDE.md` — 메타 타입 `expiry_monthend` 행 삭제와 안내 한 줄
- [x] `src/verify_lab/CLAUDE.md` — `_trade_row` · `tradable` 예시 · 손절선 축 행 · `측정.csv` 절(지금 그 파일을 내는 매매법)에서 만기_말일을 전제한 **현재형 서술**을 고친다
- [x] `.claude/rules/trading.md` — 「지금 이 길에 있는 것은 만기_말일 하나」 · 「며칠짜리 매매법(역방향 · 만기_말일)」 문장

**Validation**:

- [x] `poetry run pytest tests/test_tracks.py tests/test_layer_contracts.py tests/test_report_writer.py tests/test_strategy_output_contract.py tests/test_index.py tests/test_research_docs.py` 초록 (287 passed · 계약 테스트 59 → 56, 빠진 3개는 만기_말일 고유 축뿐)

---

### Phase 2 — 이 삭제가 공유 계층에 남긴 고아를 정리한다(그린 유지)

**작업 내용** — 코드:

- [x] 삭제: `measure/calendar_exit.py` · `tests/test_measure_calendar_exit.py` · `tests/test_measure_calendar_month.py`
- [x] `measure/calendar_entry.py` 축소 — 고아 9개 제거, 모듈 docstring 을 **지금 담는 것**(거래일 목록 검사)으로 현재형 재작성
- [x] `tests/test_measure_calendar_entry.py` — 고아를 검사하던 부분 제거. `validate_trading_days` 검사가 남지 않으면 파일 삭제
- [x] 고아 스캔 재실행 (삭제 반영 상태) → 새로 나오는 정의를 지우고 **0건이 될 때까지** 반복.
      지우기 전에 각 정의가 **「결론이 난 축의 잔여물」**인지 **「연결 누락」**인지 가른다(전역 python 규칙) — 뒤쪽이면 지우지 않고 보고한다
- [x] 주석 정리 — `execution/trade_fill.py` 두 곳 · `measure/constants.py` · `report/constants.py` ·
      `tests/test_studies_futures_continuous.py` 에서 지운 모듈을 가리키는 문장을 현재형으로

**작업 내용** — 문서:

- [x] 지운 달력 파일·테스트를 가리키는 링크를 묘비 표기로 — `docs/조사/옵션_만기일/결과.md`(「그대로 남아 있다」 문장 포함) ·
      `docs/조사/월말_진입/결과.md` · `docs/조사/만기_말일/{결과,설계}.md` 의 「관련 파일」 표
- [x] `docs/조사/월말_진입/설계.md` 의 **현재형 서술**(지금 달력을 누가 소유하는가)만 고친다 — 확정 결정 본문은 그대로
- [x] `src/verify_lab/CLAUDE.md` 「달력형은 세 번째가 왔고 올렸습니다」 절 — 올렸던 것이 이제 지워졌고 `validate_trading_days` 만 남았다는 **현재 상태**로

**Validation**:

- [x] `poetry run pytest tests/test_measure_calendar_entry.py tests/test_studies_midterm_cycle*.py tests/test_layer_contracts.py tests/test_index.py tests/test_research_docs.py` 초록 (calendar_entry 테스트 파일이 지워졌으면 그 인자를 뺀다) — 410 passed (중간선거_사이클 6파일 · 계약 · 문서 · 체결 판정 포함)
- [x] 고아 스캔 결과 0건 (HEAD 대비 새로 참조 0 이 된 정의 — 1차 14건을 지운 뒤 재스캔에서 0건. HEAD 에서도 0 이던 13건은 원래 것이라 손대지 않음)

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

> 🔴 **`/commit` 이 «맨 마지막»인 것은 의도다.** 그 스킬은 「후보 뒤에는 아무것도 덧붙이지 말 것」으로
> 끝나므로 **호출하는 순간 그 턴이 거기서 닫힌다.** 중간에 두면 뒤에 적힌 항목이 그 벽 너머에 남는다 —
> 실제로 두 번 그렇게 샜다(`[실측] 2026-09-14` 후보를 계획서에 안 옮김 · `2026-09-16` 옮기고 체크박스를 안 닫음).
> **체크박스와 상태를 먼저 확정하고, 커밋 후보를 마지막에 만든다.**

- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` **변경 있음** — Phase 1 에서 반영)
- [x] 잔여 참조 점검 — `grep -rn "매매/만기_말일\|expiry_monthend\|calendar_exit\|run_expiry_monthend\|month_entry_dates\|monthly_expiry_dates"` 결과가
      `tracks.py`·`docs/INDEX.md` 이름표·`docs/조사/` 기록의 묘비·`docs/plans/`·날짜 붙은 기록뿐인지 확인
- [x] 자동 포맷 적용 (`poetry run black .`)
- [x] 역방향·중간선거_사이클 재실행(`docs/COMMANDS.md` 의 기본 명령) → `git diff --stat storage/results/` 가 **만기_말일 이동 외에 비어 있음**
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

- [x] `/code-review xhigh` **1회차** (발견 10건 — 버그 0 · 그 외 10 · 조치: 사용자 선택으로 ①②③⑤⑥ 수정, ④⑦⑧⑨⑩ 미조치 — 목록은 진행 로그 11:10 첫 항목)
- [x] `poetry run python validate_project.py` (passed=1281, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다.**
> 계획서를 쓰는 시점에는 diff 가 없어 여기 적는 것은 전부 추측이고,
> **추측으로 적은 줄은 그대로 나간다.** 형식·문체 규칙은 `/commit` 이 정한다.

1. `조사 / 만기_말일 강등과 실행 코드 삭제`
2. `조사 / 만기_말일 조사 강등 및 실행 코드·공유 달력 계층 정리`
3. `조사 / 승률 미달에 따른 만기_말일 조사 강등과 코드 삭제`
4. `조사 / 만기_말일 코드 삭제에 따른 달력 고아 정리와 계약 테스트의 중간선거_사이클 이관`
5. `조사 / 만기_말일 비채택 결정 기록과 문서·산출물의 조사 이동`

## 7) 리스크(Risks)

| 리스크 | 완화 |
| --- | --- |
| **계약 테스트 커버리지가 조용히 줄어든다** — 지수 손절불가·한 컬럼 필터 검사가 만기_말일 픽스처에만 붙어 있었다 | 지우지 않고 중간선거_사이클 픽스처로 옮긴다. 옮기기 전후 **테스트 수**를 대조해 줄어든 것이 만기_말일 고유 축뿐인지 본다 |
| **공유 계층을 지우다 중간선거_사이클을 깬다** — `validate_trading_days` 를 함께 지우는 실수 | 스캔 결과로만 지우고, Phase 2 끝에 중간선거_사이클 테스트를 돌리고, 마지막 Phase 에서 재실행 바이트 대조 |
| **고아 스캔이 이름 단위라 과소 보고한다** — 같은 이름이 다른 모듈에 있으면 살아 있는 것으로 센다 | 삭제 반영 후 재스캔을 고정점까지 반복하고, 남은 후보는 `grep` 으로 정의 모듈을 확인한다 |
| **문서 링크가 깨진다** — 삭제된 파일을 가리키는 링크가 여러 조사 문서에 있다 | 코드를 지우는 Phase 가 그 링크도 함께 고치고 `tests/test_research_docs.py`·`tests/test_index.py` 로 닫는다. 인라인 경로는 마지막 Phase 의 잔여 참조 `grep` 으로 잡는다 |
| **산출물 이동 중 파일이 섞이거나 빠진다** | 이동 전 스크래치 사본과 `diff -r` |
| **되살릴 수단이 사라진다** | 복원 기준 커밋 `5022dc9` 와 절차를 `결과.md` 머리말에 적는다 |

## 8) 메모(Notes)

- 사용자 결정 (2026-09-26): ① 만기_말일을 조사로 — 승률이 너무 낮다 ② 코드까지 지운다(B) ③ QQQ 스크래치 결과는 남기지 않는다
- 「승률 75% 초과만 진행」은 **고려 중**이라 이 계획서 범위 밖이다. 지금 걸면 역방향(80.68% · 85.71%)과
  중간선거_사이클(무손절 100%)은 통과하고 만기_말일만 빠지며, 70% ~ 80.68% 사이 어느 값도 같은 결과다
- 고아 스캔 스크립트는 세션 스크래치에 있다(임시). 방법: 운영 코드(src·scripts)의 최상위 정의마다
  Name·Attribute·import 참조를 세고, 삭제 파일과 고아가 된 정의의 본문 안 참조를 빼며 고정점까지 반복

### 진행 로그 (KST)

- 2026-09-26 10:33: 계획서 작성. 사용자 결정 셋 반영, 고아 스캔 1차 결과(공유 정의 24개) 반영
- 2026-09-26 10:41: 승인 전 자체 검증으로 Phase 재구성 — 초안은 코드 삭제(Phase 1)와 문서 이동(Phase 3)을 갈라 두어
  **그 사이 문서 링크·INDEX 대조 테스트가 빨간 채로 남았다.** 코드를 지우는 Phase 가 그 코드를 가리키는 문서도 함께 고치도록 둘로 다시 묶었다
- 2026-09-26 10:39: 사용자 승인. Phase 0 레드 확인 (1 failed · 51 passed)
- 2026-09-26 10:51: Phase 1 완료 (287 passed). 계획과 다르게 한 것 둘 —
  ① `tests/test_layer_contracts.py` 「네 산출 지점」 검사는 만기_말일 두 줄을 빼는 대신 **중간선거_사이클 두 줄로 바꿨다**
  (그쪽도 측정·체결에서 `dataset_record` 를 부른다 — 빼기만 하면 검사가 역방향 하나로 줄어든다. 목표 2 와 같은 취지)
  ② 달력 파일을 가리키는 문서 행(조사 문서 넷·INDEX)은 Phase 2 를 기다리지 않고 **최종 상태(묘비)로 바로 썼다** — 같은 줄을 두 번 고치지 않으려고.
  묘비 행의 인라인 경로는 실재 검사를 받지 않아 Phase 1 초록에 영향이 없다
- 2026-09-26 10:55: Phase 2 완료 (410 passed). 결정·확인 셋 —
  ① `tests/test_measure_calendar_entry.py` 는 **통째로 지웠다** — 검사가 전부 고아 함수 대상이고, 남는 `validate_trading_days` 의
  두 검사(빈 목록 · 정렬)는 `tests/test_studies_midterm_cycle_calendar.py` 가 같은 함수를 거쳐 이미 검사한다
  ② 재스캔에서 **달력 토큰 13개 + `DISPLAY_MONTH_NUMBER`** 가 새로 참조 0 이 됐다. 같은 값의 하드코딩이 어디에도 없어
  「연결 누락」이 아니라 「결론이 난 축의 잔여물」로 판정해 지웠다. `ENTRY_DTYPES`·`empty_entries` 는 1차 스캔에서
  `calendar_exit.py` 의 import 때문에 살아 있는 것으로 셌던 것이라 함께 지웠다
  ③ 계획서에 없던 주석 수정 둘 — `studies/midterm_cycle/cycle_calendar.py` 모듈 docstring(지운 함수 이름으로 「왜 공유 함수를
  못 쓰나」를 설명하던 것)과 `tests/test_strategy_trade_fill_scheduled.py` docstring. 둘 다 지운 모듈을 가리켜 생긴 것이다
- 2026-09-26 11:10 (기록 시각): 마지막 Phase — 잔여 참조 점검 통과(남은 것은 slug 레지스트리·묘비·날짜 붙은 기록뿐), black 변경 0,
  역방향·중간선거_사이클 재실행 후 `git diff --stat storage/results/매매/` 가 만기_말일 이동분뿐(두 매매법 **바이트 불변**).
  `/code-review xhigh` 1회차 「그 외」 10건 (버그 0):
  ① 「지금 9월에 거는 규칙은 없다」가 틀렸다 — 중간선거_사이클이 중간선거해 9월 마지막 거래일에 진입한다(5곳)
  ② `결과.md` 복원 절차의 상수 목록이 모자란다 — 지운 달력 토큰 13개 중 하나만 적었다
  ③ `validate_trading_days` 가 자기 테스트 없이 소비자 테스트로만 검사된다(중복 분기는 무검사)
  ④ `midterm_cycle_outputs` 픽스처 docstring 이 낡았다(10월 진입·네 자리) — 옮긴 한 컬럼 필터 검사가 값 하나뿐인 축에서 돈다
  ⑤ `trade_fill.py` 80행이 없는 `month_end_runner`·`month_exit_schedule` 을 예로 든다
  ⑥ `docs/INDEX.md` 중간선거_사이클 행이 지운 공통 진입 함수를 현재형으로 말한다
  ⑦ `docs/MEMORY.md` 가 지운 달력 테스트를 살아 있는 장치로 설명한다
  ⑧ 테스트 이름·docstring 의 「세」→「두」 변경이 반쪽이다
  ⑨ `calendar_entry.py` 에 검사 함수 하나만 남아 모듈 이름과 내용이 어긋난다
  ⑩ `tests/test_report_writer.py` 의 slug 목록을 손으로 적는다(중간선거_사이클 누락은 이전부터)
- 2026-09-26 11:10 (기록 시각): 사용자가 ①②⑤⑥(문서 사실 오류)과 ③(공유 함수 자기 테스트)을 골랐다. 조치 —
  ① 다섯 곳을 「9월 만기일·월말에 거는 단기 규칙은 지금 없다 — 9월 마지막 거래일에 진입하는 중간선거_사이클은 별개」로
  ② `결과.md` 복원 절차를 「강등 커밋 통째로 되돌리기가 가장 확실」 + 부분 복원 시 상수 14개·계약 테스트 목록으로
  ⑤ `trade_fill.py` 예를 중간선거_사이클 `cycle_calendar` 로 ⑥ INDEX 중간선거 행에서 지운 함수 언급을 규칙 설명으로
  ③ **Phase 2 의 결정 ①(파일 통째 삭제)을 뒤집었다** — `tests/test_measure_calendar_entry.py` 를 `validate_trading_days` 전용
  4건(정상 · 빈 목록 · 정렬 · **중복**)으로 자기 픽스처와 함께 다시 만들었다. 중복 분기는 그전까지 어디서도 검사되지 않았다.
  그에 맞춰 묘비 행 셋(`만기_말일/{결과,설계}.md` · `옵션_만기일/결과.md`)의 테스트 설명을 「달력 부분만 삭제」로 고쳤다.
  ④⑦⑧⑨⑩ 은 미조치(사용자 결정)
- 2026-09-26 11:10: 품질 검증 통과 (Ruff · PyRight 통과, Pytest passed=1281 · failed=0 · skipped=0). black 변경 0
