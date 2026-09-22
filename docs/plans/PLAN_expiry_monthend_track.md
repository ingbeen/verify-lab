# Implementation Plan: 만기_말일 — 진입 2 × 청산 2 교차 검증 트랙 신설

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

**작성일**: 2026-09-21 21:36
**마지막 업데이트**: 2026-09-21 23:40
**관련 범위**: measure, studies, execution, scripts, tests, docs
**관련 문서**: `src/verify_lab/CLAUDE.md`, `scripts/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/trading.md`, `.claude/rules/research.md`, `.claude/rules/docs.md`

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

- [x] 목표 1: **달력형 진입·청산 일정 함수를 `measure/` 공유 계층으로 올린다.** 지금은 두 매매법 패키지가 한 벌씩 소유하고 있어 세 번째 달력형 검증이 그것을 빌려 쓸 길이 없다(`tests/test_layer_contracts.py` 가 매매법 간 import 를 금지한다). **이동이지 재구현이 아니며 산출물 값이 하나도 바뀌지 않아야 한다.**
- [x] 목표 2: **새 검증 트랙 `만기_말일`(slug `expiry_monthend`)을 만든다.** 진입 2종(셋째 금요일 · 20일) × 청산 2종(다음 주 금요일 · 그 달 마지막 거래일)을 교차해 **9월·12월**에서 **대상 6 × 손절 10 × 조합 4 × 달 2 × 방향 2 = 160칸**을 산출한다.
- [x] 목표 3: **「조합 선택이 결과를 만드는가」에 답할 재료를 낸다.** 네 조합이 절반 가까운 해에 같은 날로 붕괴하므로(실측 C3=C4 47.3%), 갈린 해를 세어 `통계.csv` 에 두 컬럼으로 낸다.

## 2) 비목표(Non-Goals)

- **기존 두 매매법(`옵션_만기일`·`월말_진입`)의 확정 규칙·확정 칸·손절선을 바꾸지 않는다.** 그 문서와 `TRADING_CELLS` 는 손대지 않으며, Phase 1 의 이동은 **import 경로만** 바꾼다.
- **어느 조합이 더 좋은지 코드가 고르지 않는다.** 네 조합을 전부 내고 판단은 사용자가 한다(측정의 원칙 1).
- **비용을 넣지 않는다.** 수수료·슬리피지·세금은 맨몸 성적 기준이며 사용자가 별도로 요청할 때만 넣는다(루트 `CLAUDE.md` 2026-09-06 확정).
- **한국 둘째 목요일(국내 옵션 만기) 달력을 쓰지 않는다.** 사용자가 이미 재 봤고 성과가 약했다(2026-09-21 결정). 한국도 셋째 금요일 하나로 간다.
- **종합지수(코스피 종합·코스닥 종합)를 대상에 넣지 않는다.** 2026-09-21 사용자 결정이며 근거는 §8 실측이다.
- **매매 등급으로 승격하지 않는다.** 이 트랙은 `검증` 에 머문다. 승격은 결과를 보고 사용자가 정한다.
- **시세를 재수집하지 않는다.** 기존 `storage/` 파일을 그대로 쓴다.

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

- **두 매매법이 사실상 같은 구간을 재고 있는지 아무도 모른다.** 실측하니 **미국은 33해 전부 겹치고(평균 5.09거래일)** 한국은 둘째 목요일 달력 탓에 거의 겹치지 않았다(평균 1.13거래일). 사용자는 **한국에도 셋째 금요일을 적용해** 두 매매법을 한 축에서 비교하려 한다.
- **진입과 청산을 따로 고를 수 있다는 것을 아무도 재지 않았다.** 지금 저장소에는 「만기일 → 다음 주 금요일」과 「20일 → 말일」 두 대각선만 있고, 나머지 두 칸(「만기일 → 말일」·「20일 → 다음 주 금요일」)은 측정된 적이 없다.
- **한국 축의 기간이 짧다.** 옵션 만기일의 한국 축은 `KODEX 200` 23해뿐인데, 기초지수(코스피200 36해·코스닥150 16해)를 붙이면 길어진다.
- 🔴 **구조적 막힘**: 위를 재려면 네 함수가 필요한데 **두 매매법 패키지에 나뉘어 있고 매매법끼리 import 가 금지돼 있다**(`tests/test_layer_contracts.py::test_검증끼리_서로를_가져오지_않는다`). 그 테스트의 docstring 이 *"공통으로 올릴 것은 `measure`·`report` 로 가야 한다"* 고 적는다. `src/verify_lab/CLAUDE.md` 는 달력형 어휘 11쌍의 통합을 **"세 번째 달력형 검증이 올 때 보고 정한다"(2026-09-14 확정)** 로 유보했고, **이 트랙이 그 세 번째다.**

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- `.claude/plan-config.json` — 이 저장소의 검증 명령·자동 포맷·근거 승격 목적지 (**값의 SoT**)
- 루트 `CLAUDE.md` — 「측정의 원칙」 1~17, 「후보 판정 기준」, 「계획서 규약」
- `src/verify_lab/CLAUDE.md` — 「계층 간 계약」 전부. 특히 **매매법 이름 계약 · 매매 계층 구성 계약 · 매매 산출물 계약 · 출력 계약 · 실행 요약 계약**
- `.claude/rules/trading.md` — 손절 규정, 격자 산출의 허용 범위, 성적표 규격
- `.claude/rules/research.md` — 결과 문서 필수 구조와 「관련 파일」 표
- `.claude/rules/docs.md` — 문서 배치(등급 축), 데이터 기간 표기, 용어 대응표
- `scripts/CLAUDE.md` — CLI 계층 책임
- `tests/CLAUDE.md` — Given-When-Then, look-ahead 감시, 파일 격리
- `~/.claude/rules/python.md` — 타입 힌트, 반올림 자릿수, 로깅

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 기능 요구사항 충족 — 네 조합 × 9월·12월 × 대상 6 의 측정·체결 산출물이 나온다
- [x] **Phase 1 이동으로 기존 두 매매법의 산출물이 하나도 바뀌지 않았음을 바이트 대조로 확인**
- [x] 회귀/신규 테스트 추가
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트(`docs/COMMANDS.md` / `docs/INDEX.md` / 새 설계·결과 문서)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 근거·실측 수치를 `.claude/plan-config.json` 의 `evidence_home` 이 정한 폴더로 이관.
      `/impl-plan` 스킬 "근거 승격" 참고)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

**새로 만드는 것**

- `src/verify_lab/measure/calendar_entry.py` — 진입 달력 2종
- `src/verify_lab/measure/calendar_exit.py` — 청산 일정 2종
- `src/verify_lab/studies/expiry_monthend/{__init__,constants,pairing,runner,trading}.py`
- `scripts/run_expiry_monthend.py`
- `tests/test_measure_calendar_entry.py` · `tests/test_measure_calendar_exit.py`
- `tests/test_studies_expiry_monthend_pairing.py` · `tests/test_studies_expiry_monthend_runner.py`
- `docs/검증/만기_말일/설계.md` · `docs/검증/만기_말일/결과.md`

**고치는 것**

- `src/verify_lab/measure/constants.py` — 달력 컬럼 토큰 이관
- `src/verify_lab/studies/option_expiry/{constants,runner,trading}.py` — import 경로만
- `src/verify_lab/studies/month_end/{constants,runner,trading}.py` — import 경로만
- `src/verify_lab/tracks.py` — 한 줄 추가
- `tests/test_layer_contracts.py` — 달력 소유자 계약 추가, 새 트랙 반영
- `tests/test_strategy_output_contract.py` — 새 매매법 추가
- `tests/test_index.py` 대상인 `docs/INDEX.md`
- `docs/COMMANDS.md`: **변경 있음** — 새 실행 명령어와 산출물 설명 추가

**지우는 것** (Phase 1 이동 후 빈 껍데기)

- `src/verify_lab/studies/option_expiry/expiry_calendar.py` · `weekly_exit.py`
- `src/verify_lab/studies/month_end/schedule.py`
- `tests/test_studies_option_expiry_calendar.py` · `test_studies_option_expiry_weekly_exit.py` · `test_studies_month_end_schedule.py` (새 이름으로 이동)

### 데이터/결과 영향

- **기존 두 매매법의 산출물은 바이트 단위로 같아야 한다.** Phase 1 의 Validation 이 그것을 검사한다.
- **새 산출물**: `storage/results/검증/만기_말일/` 에 `통계.csv`(48행) · `성적표.csv`(800행) · `거래내역.csv`(약 3,870행) · `summary.json`
- 시세는 재수집하지 않으므로 기존 결과 문서의 수치는 영향받지 않는다.

## 6) 단계별 계획(Phases)

### Phase 0 — 계층 계약과 달력 계약을 테스트로 먼저 고정(레드)

> 핵심 인바리언트 변경(공유 계층 소유자 이동)이고, 최종 결과가 달라지면 안 되는 변경이라 이 Phase 를 둔다.

**작업 내용**:

- [x] `tests/test_layer_contracts.py` 에 **「달력 일정 함수의 소유자는 `measure` 하나」** 검사 추가
      — 세 검증 패키지 어디에도 `monthly_expiry_dates`·`month_entry_dates`·`weekly_exit_schedule`·`month_exit_schedule` 의 **정의**가 없고, 쓰는 쪽은 `verify_lab.measure.calendar_*` 에서 직접 가져온다
- [x] `tests/test_measure_calendar_entry.py` · `tests/test_measure_calendar_exit.py` 를 **새 자리 이름으로** 만든다
      — 기존 세 테스트 파일의 케이스를 그대로 옮기고 **look-ahead 감시 테스트를 유지**한다
- [x] `tests/test_tracks.py` 가 새 트랙 `expiry_monthend` ↔ `만기_말일` 을 요구하도록 `docs/INDEX.md` 대조 대상에 들어갈 것을 확인 (레드)

---

### Phase 1 — 달력 함수를 `measure/` 로 이동 (값 불변, 그린 유지)

> 🔴 **이 Phase 는 「이름만 바꾸는 변경」이다.** `docs/MEMORY.md` 「이름만 바꾸는 변경과 값을 바꾸는 변경을 한 커밋에 섞지 않는다」에 따라 **먼저 이동만 하고 값이 안 바뀐 것을 확인한 뒤** Phase 2 로 간다.

**작업 내용**:

- [x] `measure/constants.py` 에 달력 컬럼 토큰을 이관한다
      — `COL_RULE_DATE`·`COL_EXPIRY_DATE`·`COL_EXPIRY_MONTH`·`COL_ADVANCED_DAYS`·`COL_WEEK_REFERENCE`·`COL_TARGET_DATE`·`COL_EXIT_DATE`·`COL_HOLD_DAYS`·`COL_ENTRY_CLOSE`·`COL_EXIT_CLOSE`·`COL_MONTH`·`COL_TARGET_DAY`·`COL_MONTH_LAST_DATE`·`COL_EXIT_OFFSET`·`REASON_NO_ENTRY_DAY`·`REASON_NO_HOLDING`·`REASON_NO_TRADING_DAY`
      — **`HORIZON_*` 표지는 옮기지 않는다.** 매매법마다 다른 음수값이고 그 매매법의 묶음 표지다
- [x] `measure/calendar_entry.py` 신설 — `ExpiryRule`·`nth_weekday_of_month`·`monthly_expiry_dates`·`month_entry_dates`·`every_day_entries`
- [x] `measure/calendar_exit.py` 신설 — `WeeklyExitSchedule`·`weekly_exit_schedule`·`weekly_exit_returns`·`MonthExitSchedule`·`month_exit_schedule`·`month_exit_returns`
      — **`*_returns` 두 함수는 `horizon` 을 인자로 받는다.** 지금은 각 매매법의 상수를 직접 import 하는데, 공유 계층은 매매법을 몰라야 한다
- [x] 두 매매법의 import 를 새 자리로 바꾸고 **옛 경로를 재노출하지 않는다** (`src/verify_lab/CLAUDE.md` 기각안)
- [x] 빈 껍데기가 된 세 모듈과 세 테스트 파일을 지운다
- [x] `US_MONTHLY_EXPIRY`·`KR_MONTHLY_EXPIRY` 는 **`studies/option_expiry/constants.py` 에 남긴다** — 그 매매법의 파라미터이지 공유 값이 아니다

**Validation**:

- [x] `poetry run pytest tests/test_measure_calendar_entry.py tests/test_measure_calendar_exit.py tests/test_layer_contracts.py`
- [x] 🔴 **기존 두 매매법 재실행 후 산출물 바이트 대조**
      `poetry run python scripts/run_option_expiry.py` · `poetry run python scripts/run_month_end.py` 뒤
      `git diff --stat storage/results/` 가 **비어 있어야 한다**
      (`summary.json` 은 `row_counts` 키가 파일 이름이라 이름이 안 바뀌면 함께 같아야 한다)

---

### Phase 2 — 새 검증 패키지 `studies/expiry_monthend/` (그린 유지)

**작업 내용**:

- [x] `constants.py`
      — `TRACK_NAME = "expiry_monthend"`
      — `DATASETS` 6개: SPY · DIA · KODEX 200 · 코스피200 지수 · KODEX 코스닥150 · 코스닥150 지수
        (`ticker`·`label`·`market`·`directory`·`file_template`·`price_column`·`price_decimals`·`is_index`)
      — `ENTRY_RULES` 2종 · `EXIT_RULES` 2종 · `COMBOS` 4개 (진입 × 청산의 곱을 **상수로 펼쳐 둔다**)
      — `MONTHS = (9, 12)`
      — `STOP_LEVEL = 0.05` · `STOP_LEVELS_ETF = (0.05, None)` · `STOP_LEVELS_INDEX = (None,)`
      — `OUTPUT_FILES = {"statistics": STATISTICS_FILENAME}`
      — `COLUMN_LABELS`(한글 헤더) · `PERCENT_COLUMNS` · `PROBABILITY_COLUMNS`
- [x] `pairing.py` — 조합 하나의 진입·청산 일정을 만든다. **계산하지 않고 `measure/calendar_*` 를 조립만 한다**
      — 셋째 금요일 진입의 주 기준일은 **규칙일**(앞당김 전), 20일 진입의 주 기준일은 **그 달 20일 달력일**
      — 월말 청산은 `month_exit_schedule(exit_offset=0)` 에 진입일 표를 맞춰 넘긴다
      — **제외된 진입은 행을 남기고 사유를 단다** (표본 보존)
- [x] `runner.py` — 측정 조립 → `통계.csv` **48행** (대상 6 × 조합 4 × 달 2)
      — 신호 통계(신호·표본·평균·중앙값·오른 비율·내린 비율·최고·최악·표준편차·양수/음수 평균·건수·평균-비율 어긋남·판정가능)
      — **기준선**(전 거래일 진입, `every_day_entries`)과 **기준선 대비 차이 4컬럼**
      — **우연확률 8컬럼** (무작위 뽑기 대조, 시드 `DEFAULT_RANDOM_SEED`)
      — **배당락 3컬럼** (`measure/distribution.dividend_impact`. ETF 는 수정주가로 재고 **지수는 비운다**)
      — 🔴 **방향 컬럼을 두지 않는다.** 측정 계층은 방향을 모르고 두 비율을 나란히 낸다(출력 계약). 성적표가 방향 2행을 갖고 조인 키는 `(종목, 조합, 달)` 이다
- [x] `trading.py` — 체결 조립 → `성적표.csv` **800행** · `거래내역.csv`
      — `execution/trade_fill.simulate_scheduled_trade` · `execution/periods.period_rows` 를 **그대로** 부른다
      — 식별 컬럼: `종목 · 조합 · 달 · 방향 · 손절선(%)`
      — `손절선(%)` 값은 `execution/constants.stop_level_value(level, measurable=not is_index)`
      — `tradable=not dataset.is_index` (지수는 「판정 안 함」 — 측정의 원칙 9)
      — **`사건` 컬럼을 두지 않는다** (신호가 달·조합마다 연 1회라 신호 = 사건)
- [x] **「조합이 갈린 해만 본 표」**를 `runner.py` 가 `통계.csv` 의 컬럼으로 낸다
      — `조합 붕괴 해` · `갈린 해` 두 컬럼. **별도 파일을 만들지 않는다** (축이 같아 조인이 자명하다)

---

### Phase 3 — 등록 · CLI · 문서 (그린 유지)

**작업 내용**:

- [x] `src/verify_lab/tracks.py` 에 한 줄 추가
      `Track("expiry_monthend", "만기_말일", GRADE_STUDY, KIND_METHOD)`
- [x] `scripts/run_expiry_monthend.py` — 인자 파싱·호출·표시·저장만
      — `--ticker`(반복) · `--combo`(반복) · `--month`(반복) · `--stop-grid` 없음(손절선이 이미 2종) · `--repeats` · `--seed`
      — 산출물 저장은 `report/writer.{create_run_directory,save_table,save_run_summary}`
- [x] `docs/검증/` 폴더와 `docs/검증/만기_말일/설계.md` 작성
      — 「확정된 설계 결정」에 ①~⑩ 과 **탈락안**을 적는다 (한국 둘째 목요일 · 종합지수 · 12달 전체 · 격자 이름 등)
      — 「데이터 실측 기록」에 §8 의 프로브 수치를 전부 옮긴다
- [x] `docs/검증/만기_말일/결과.md` 뼈대 작성 (수치는 마지막 Phase 에서 채운다)
      — `.claude/rules/research.md` 필수 구조와 「관련 파일」 표를 지킨다
- [x] `docs/INDEX.md` §3 이름표에 등록
- [x] `docs/COMMANDS.md` 에 실행 명령어와 산출물 설명 추가
- [x] `tests/test_strategy_output_contract.py` 에 새 매매법 추가

---

### 마지막 Phase — 실행, 문서 확정, 최종 검증

**작업 내용**

> 🔴 **`/commit` 이 «맨 마지막»인 것은 의도다.** 그 스킬은 「후보 뒤에는 아무것도 덧붙이지 말 것」으로
> 끝나므로 **호출하는 순간 그 턴이 거기서 닫힌다.** 중간에 두면 뒤에 적힌 항목이 그 벽 너머에 남는다 —
> 실제로 두 번 그렇게 샜다(`[실측] 2026-09-14` 후보를 계획서에 안 옮김 · `2026-09-16` 옮기고 체크박스를 안 닫음).
> **체크박스와 상태를 먼저 확정하고, 커밋 후보를 마지막에 만든다.**

- [x] `scripts/run_expiry_monthend.py` 를 **인자 없이** 돌려 산출물을 만든다
- [x] `docs/검증/만기_말일/결과.md` 에 실제 수치를 채운다 (결론 요약 · 조합별 성적 · 조합 붕괴 · 한계)
- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` **변경 있음**)
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

- [x] `/code-review xhigh` **1회차** (발견 14건 — 버그 4 · 그 외 10 · 조치: 버그 4 + 계획 미이행 1 + 거짓 서술·죽은 포인터 3)
- [x] `/code-review xhigh` **2회차** (발견 13건 — 버그 1 · 그 외 12 · 조치: 버그 1 + 계획 미이행 2 + 자기유발 함정·오기 4)
- [x] `/code-review xhigh` **3회차** (발견 13건 — 버그 3 · 그 외 10 · 조치: 버그 3 + 자기유발 6)
- [x] `/code-review xhigh` **4회차** (발견 10건 — 버그 1 · 그 외 9 · 조치: 버그 1 + 죽은 포인터 5 + 자기유발 4)
- [x] `/code-review xhigh` **5회차** (발견 10건 — 버그 2 · 그 외 8 · 조치: **버그 2건이 둘 다 4회차 수정에서 나온 것**이라 그것만 고치고 닫음)
- [x] `poetry run python validate_project.py` (passed=1328, failed=0, skipped=0)

> 🔴 **5회차에서 닫았고 「버그 0 회차」에 도달하지 못했다.** 발견이 14 → 13 → 13 → 10 → 10 으로
> 줄지만 0 으로 가지 않았고, **3회차부터는 버그가 전부 직전 회차에 넣은 수정에서 나왔다** —
> `/impl-plan` 이 실측으로 적어 둔 순환(「새 테스트를 넣으면 그 테스트가 다음 회차의 대상이
> 된다」)과 같은 모양이다. **고치지 않은 「그 외」는 다섯 회차 내내 같은 넷이다** —
> `_aggregate_by_month` 세 벌 복제 · 죽은 레이블 10개 · 배당락의 CSV 재로딩 · 공개 API 과다.
> **그중 첫째는 위험이 크므로 `src/verify_lab/CLAUDE.md` 공통 계층 절에 상태와 근거를 남겼다.**

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다.**
> 계획서를 쓰는 시점에는 diff 가 없어 여기 적는 것은 전부 추측이고,
> **추측으로 적은 줄은 그대로 나간다.** 형식·문체 규칙은 `/commit` 이 정한다.

1. `검증 / 만기_말일 트랙 신설과 달력 계산 공유 계층 이관`
2. `검증 / 진입 2종 × 청산 2종 교차 트랙 신설과 달력 함수 measure 이관`
3. `검증 / 세 번째 달력형 트랙 도입에 따른 달력 소유자 measure 단일화`
4. `검증 / 만기_말일 신설로 옵션 만기일·월말 진입을 한 축에서 비교`
5. `검증 / 만기_말일 트랙 추가와 달력·레이블의 공통 계층 승격`

> **커밋 분리를 제안했고 판단은 사용자에게 넘겼다.** 이 변경은 ① 달력 계산 이관(산출물 diff 0)과
> ② 새 트랙 신설(새 값) 둘로 갈리며, `docs/MEMORY.md` 가 「이름만 바꾸는 변경과 값을 바꾸는
> 변경을 한 커밋에 섞지 않는다」로 정한 바로 그 모양이다. 위 후보는 **한 커밋으로 갈 때**의
> 것이며, 나누기로 하면 후보를 다시 낸다.

## 7) 리스크(Risks)

| 리스크 | 완화 |
| --- | --- |
| 🔴 **Phase 1 이동이 기존 두 매매법의 값을 조용히 바꾼다** | Phase 1 Validation 이 **재실행 후 `git diff --stat storage/results/`** 로 검사한다. 비어 있지 않으면 이동이 아니라 변경이다 |
| **9월·12월이 이미 답을 본 달이다** | 사후 선택이라 「우위가 있다」를 새로 주장할 수 없다. **결과 문서의 한계에 명시**하고 용도를 「조합 간 비교」로 한정한다 |
| **네 조합이 절반의 해에 같은 날로 붕괴한다** | 비교 표본이 실제보다 적다. **`통계.csv` 에 「갈린 해」 컬럼을 두어** 읽는 사람이 그 크기를 바로 본다 |
| **한국 축이 짧아졌다** (코스피 46→36해 · 코스닥 30→16해) | 종합지수를 뺀 대가다. 근거(ETF 대리 상관 0.89 대 0.99)를 설계 문서에 남긴다 |
| **표본이 칸당 10~36건이라 한 건이 결과를 움직인다** | 표본 수를 전 표에 적고, 하한 미달 칸은 `판정가능 = 아니오` 로 남긴다(측정의 원칙 12·17) |
| **`measure/` 가 비대해진다** | 달력 두 파일만 올린다. `HORIZON_*` 표지와 만기 규칙(`US_MONTHLY_EXPIRY` 등)은 각 매매법에 남긴다 |

## 8) 메모(Notes)

### 확정된 결정과 근거 (설계 문서로 승격할 것)

| # | 결정 | 근거 |
| --- | --- | --- |
| ① | **한국도 셋째 금요일** | 사용자가 둘째 목요일을 이미 재 봤고 성과가 약했다. 실측으로 앞당김이 드물다 — `KODEX 200` 47해 중 **2해**(2013-09-17·2016-09-13, 둘 다 추석) |
| ② | **9월·12월만** | 사용자 결정. **대가는 사후 선택**이고 결과 문서의 한계에 적는다 |
| ③ | **손절은 ETF −5% 고정 + 무손절 대조, 지수는 손절불가** | −5% 는 사용자 결정. 무손절은 `.claude/rules/trading.md` 가 「손절이 무엇을 막았는가」로 요구하며, 이 트랙은 `규칙.md` 가 없어 산출로 메운다 |
| ④ | **대상은 기초지수 둘(코스피200·코스닥150), 종합지수 제외** | 종합지수가 ETF 를 잘 대리하지 못한다 — 아래 실측 |
| ⑤ | **달력 함수를 `measure/` 로 올린다** | 매매법 간 import 금지. `src/verify_lab/CLAUDE.md` 가 「세 번째 달력형 검증이 올 때 정한다」로 유보한 시점이 왔다 |
| ⑥ | **측정 표에 방향 컬럼을 두지 않는다** | 측정 계층은 방향을 모르고 두 비율을 나란히 낸다(출력 계약). 방향은 성적표의 축이다 |
| ⑦ | **측정 산출물은 `통계.csv` 한 장** | 좁히지 않은 격자라 이름은 `통계.csv` 이고(매매 산출물 계약), 축이 하나라 `excess`·`test` 를 따로 낼 이유가 없다 — 전부 같은 48행이라 나누면 사용자가 조인해야 한다 |
| ⑧ | **`signals.csv` 를 내지 않는다** | 신호가 달력으로 정의되고 **체결 원자료가 `거래내역.csv` 에 진입가·청산가까지 들어 있어** 측정의 원칙 8 을 그쪽이 충족한다 (옵션 만기일이 `weekly_trade_signals.csv` 를 없앤 것과 같은 근거) |

### 실측 기록 (2026-09-21, 설계 문서로 승격할 것)

**가) 두 매매법의 보유 구간이 겹치는가** — 진입·청산 달력만으로 잰 값이다.

| 시장 | 겹친 거래일 평균 | 겹침 0인 해 |
| --- | ---: | ---: |
| SPY 9월 (33해) | **5.09** | 0 |
| SPY 12월 (33해) | **4.39** | 0 |
| KODEX 200 9월 (23해, 둘째 목요일) | 1.13 | 6 |
| 코스피 종합 9월 (46해, 둘째 목요일) | 0.98 | 19 |

**나) 네 조합이 같은 날로 붕괴하는 빈도** — 8대상 446해(9월+12월) 합산.

| 쌍 | 진입·청산이 둘 다 같은 해 |
| --- | ---: |
| C3 = C4 | **48.4%** (216/446) |
| C2 = C4 | 41.0% (183) |
| C1 = C3 | 39.7% (177) |
| C1 = C2 | 12.8% (57) |
| C1 = C4 · C2 = C3 | 1.3% (6) |

한 해에 서로 다른 조합의 수: SPY 66해 — 2개 48% · 3개 38% · **4개 14%**. KODEX 200 47해 — 2개 57% · 3개 38% · **4개 4%**.

**다) 종합지수가 ETF 를 대리하는가** — 무손절·종가 기준 체결 수익률의 상관.

| 쌍 | r 범위 | 절대차 평균 |
| --- | --- | --- |
| `KODEX 200` ↔ 코스피200 지수 | 0.9660 ~ 0.9949 | 0.22 ~ 1.29%p |
| `KODEX 200` ↔ 코스피 종합지수 | 0.9593 ~ 0.9881 | 0.37 ~ 1.37%p |
| `KODEX 코스닥150` ↔ **코스닥150 지수** | **0.9928 ~ 0.9991** | **0.18 ~ 0.40%p** |
| `KODEX 코스닥150` ↔ **코스닥 종합지수** | **0.8924 ~ 0.9743** | **0.64 ~ 1.29%p** |

코스피는 둘이 대등하지만 **코스닥은 종합지수가 ETF 와 크게 벌어진다**(12월 C1 에서 0.9928 대 **0.8924**). 코스닥 종합 대 코스닥150 의 회당 차이가 12월에 **0.44 ~ 0.64%p** 로 회당 기대값과 같은 크기다.

**라) 대상별 신호 수** (네 조합 공통, 제외 0건)

| 대상 | 데이터 기간 | 9월 | 12월 |
| --- | --- | ---: | ---: |
| SPY | 1993-01-29 ~ 2026-08-25 | 33 | 33 |
| DIA | 1998-01-20 ~ 2026-08-26 | 28 | 28 |
| KODEX 200 | 2002-10-14 ~ 2026-09-04 | 23 | 24 |
| 코스피200 지수 | 1990-01-03 ~ 2026-09-08 | 36 | 36 |
| KODEX 코스닥150 | 2015-10-01 ~ 2026-09-02 | 10 | 11 |
| 코스닥150 지수 | 2010-01-04 ~ 2026-09-04 | 16 | 16 |
| **합계** | | **146** | **148** |

### 진행 로그 (KST)

- 2026-09-21 21:36: 계획서 작성. 사용자 결정 넷(한국도 셋째 금요일 · 9월·12월만 · 손절 −5% 고정 · 이름 `만기_말일`)과 기초지수 채택을 반영

---
