# Implementation Plan: 판정가능·표본 하한 단일화와 futures_leverage 출력 계층 정리

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

**작성일**: 2026-09-05 22:41
**마지막 업데이트**: 2026-09-06 07:07
**관련 범위**: measure, report, studies(futures_leverage·option_expiry·leverage_tracking), strategy, scripts
**관련 문서**: `CLAUDE.md`, `src/verify_lab/CLAUDE.md`, `scripts/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/python.md`, `.claude/rules/docs.md`

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

- [x] 목표 1: **`판정가능` 이 네 계층에서 같은 값을 갖게 한다** — `futures_leverage` 만 `True`/`False` 라 산출물을 나란히 읽을 수 없고, `measure.screening` 이 `== JUDGEABLE_YES` 로 비교하므로 그 표를 판정에 넘기면 전 칸이 조용히 제외된다
- [x] 목표 2: **표본 하한을 공통 계층 하나로 통합한다** — 네 곳에 같은 값 10이 흩어져 있고, 갈라져도 예외가 나지 않는다
- [x] 목표 3: **표본 0건 구간에서 지표가 0으로 채워지는 마지막 자리를 없앤다** (측정의 원칙 17)
- [x] 목표 4: **`futures_leverage` 의 출력 경로를 다른 네 검증과 같은 관용으로 맞춘다** — 컬럼명 리터럴을 상수로, 레이블 사전을 `scripts/` 에서 `src/` 로
- [x] 목표 5: **코드를 잘못 설명하는 주석 세 곳을 사실과 맞춘다** — 이전 작업이 "통합했다"고 적었으나 실제로는 절반만 통합됐다

## 2) 비목표(Non-Goals)

**전수 감사 50건 중 이번 계획서의 범위는 12건이다.** 나머지는 뒤따르는 세 계획서가 맡는다.

- **데이터 계층** — 수집기 타임존 5곳, `RECENT_EXCLUSION_DAYS` 3중 정의, `KST` 재정의, `data/constants.py` 신설, 지연 import 헬퍼 통합, `type: ignore` 2건 → `PLAN_data_layer`
- **방어·불변조건** — 중단 누락 5건, 불필요한 fallback 4건, 빈 표 스키마 유실, `StopIteration`, `strategy` 제외 건수 유실 → `PLAN_guards`
- **리팩토링·문서** — 죽은 조건, frozen dataclass 우회, `expanding_rank` 8회 재계산, 문서 불일치 3건, 문서에 박힌 가변 수치, 코드 주석의 과거 상태 7건 → `PLAN_refactor_docs`
- **시세 재수집 금지.** `storage/market/` 은 읽기만 한다
- **`docs/spec/`·`docs/context/` 는 손대지 않는다** — 설계 근거와 사용자 소유 문서다
- **판정 기준값(60% · 0 초과 · 10건)을 바꾸지 않는다.** 옮기기만 한다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

**이전 작업이 절반만 끝났고, 주석은 전부 끝났다고 적혀 있다.**

- `measure/constants.py:47-49` 가 "실제로 세 곳(`leverage_tracking`·`strategy`·`futures_leverage`)에
  같은 문자열이 따로 정의돼 **있었다**" 라고 적었다. 앞의 둘은 재노출로 바뀌었으나
  **`futures_leverage/runner.py:100` 은 지금도 `COL_JUDGEABLE = "Judgeable"` 을 자체 정의**한다.
  더 나쁜 것은 값이다 — 같은 파일 `:209` 가 `sample_count >= MIN_SAMPLE_FOR_AXIS` 라는 **bool** 을 넣는다.
  실측: `True` / `False` 가 CSV 로 나가고, 다른 세 곳은 `예` / `아니오` 다
- `measure/constants.py:50-52` 가 "새 상수를 만들면 **지금 있는 세 개**에 네 번째가 더해진다"고
  경고하는데 **이미 네 개**다. 실측으로 넷 다 값이 10이다

**하한이 "축마다 다르다"는 전제도 코드가 이미 깨고 있다.**
`option_expiry/runner.py:558` 은 검정 하한인 `MIN_SAMPLE_FOR_TEST` 를 **칸당 하한으로 전용**한다.
루트 `CLAUDE.md` 측정의 원칙 12가 「10건」을 명시하고 원칙 17이 「원칙 12의 10건」이라며
같은 값임을 선언하므로, 「원칙에 적혀 있으면 공통 계층」이라는 판단 기준에 따라 통합한다.

**표본 0건 구간에 0이 남아 있는 자리가 하나 있다.**
`strategy/expiry_runner.py:462-463` 은 합계·평균·승률·최고·최악을 전부 `np.nan` 으로 비우면서
갭손절·장중손절 건수만 `0` 으로 채운다. 바로 위 docstring 이
"0 으로 채우면 「손실도 이익도 없었다」로 읽히는데 실제로는 「잰 적이 없다」이다" 라고 적어 놓고
두 줄 아래에서 그렇게 한다.

**`futures_leverage` 만 출력 경로가 다르다.**
다른 네 검증은 `studies/<검증>/constants.py` 의 `OUTPUT_LABELS` 로 컬럼 이름을 `src` 에 두는데,
이 검증만 `scripts/studies/run_futures_leverage.py` 에 사전 8개를 두고 **문자열 리터럴로** `src` 와
연결한다. 컬럼 상수도 `runner.py`·`comparison.py`·`continuous.py` 에 리터럴로 흩어져 있다.

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「측정의 원칙」 12·17, 「후보 판정 기준」, 「계획서 규약 — 이 프로젝트의 설정」
- `src/verify_lab/CLAUDE.md` — 「상수 관리」 3계층, 「내부/출력 분리」, 「계층 간 계약」
- `scripts/CLAUDE.md` — CLI 계층의 책임과 산출물 저장
- `tests/CLAUDE.md` — 필수 테스트 3종, Given-When-Then, 파일 격리
- `.claude/rules/python.md` — 반올림 규칙표, 주석 작성 원칙
- `.claude/rules/docs.md` — 용어 대응표

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] `판정가능` 값이 네 계층에서 전부 `JUDGEABLE_YES`/`JUDGEABLE_NO` 문자열이다
- [x] 표본 하한이 `measure/constants.py` 한 곳에만 정의되고, 나머지 세 곳은 재노출 또는 직접 import 다
- [x] 표본 0건 구간에서 **모든** 지표가 비어 있다 (손절 건수 포함)
- [x] `futures_leverage` 의 결과 컬럼명이 전부 상수를 지나고, 레이블 사전이 `src` 에 있다
- [x] 회귀/신규 테스트 추가
- [x] `poetry run python validate_project.py` 통과 — passed=876, failed=0, skipped=0
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트(`docs/COMMANDS.md` / CLAUDE.md / plan 등 — 각각 변경 여부 명시)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 근거·실측 수치를 루트 `CLAUDE.md` 의 프로젝트 설정 절이 정한 목적지로 이관.
      `/impl-plan` 스킬 "근거 승격" 참고)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

**측정 계층**

- `src/verify_lab/measure/constants.py` — `MIN_SAMPLE_PER_CELL` 신설, 잘못된 주석 두 곳 정정
- `src/verify_lab/measure/statistics.py` — `MIN_SAMPLE_FOR_TEST` 제거하고 공통 상수 사용, `_percentile` 반환을 비율로
- `src/verify_lab/report/tables.py` — `build_test_table` 의 백분위 4개를 백분율 변환 경로로

**검증 계층**

- `src/verify_lab/studies/futures_leverage/runner.py` — `COL_JUDGEABLE` 로컬 정의 제거, bool→문자열, `MIN_SAMPLE_FOR_AXIS` 제거, 결과 컬럼 리터럴 상수화
- `src/verify_lab/studies/futures_leverage/constants.py` — 컬럼 상수와 `OUTPUT_LABELS` 신설
- `src/verify_lab/studies/futures_leverage/comparison.py` — `decompose` 반환 컬럼 상수화
- `src/verify_lab/studies/futures_leverage/continuous.py` — `roll_events_frame` 컬럼 상수화
- `src/verify_lab/studies/leverage_tracking/constants.py` — `MIN_SAMPLE_PER_CELL` 을 재노출로
- `src/verify_lab/studies/leverage_tracking/runner.py` — `HORIZON_LABELS.map` 의 조용한 NaN 차단
- `src/verify_lab/studies/option_expiry/constants.py` — 백분위를 확률 목록에서 백분율 목록으로
- `src/verify_lab/studies/option_expiry/runner.py` — 하한 import 경로 변경

**매매 계층**

- `src/verify_lab/strategy/constants.py` — `MIN_PERIOD_SAMPLE` 을 재노출로
- `src/verify_lab/strategy/expiry_runner.py` — 표본 0건일 때 손절 건수를 비운다

**실행 계층**

- `scripts/studies/run_futures_leverage.py` — 사전 8개를 `src` 의 `OUTPUT_LABELS` 로 대체, 리터럴 2곳 제거
- `scripts/studies/run_option_expiry.py` — 한글 레이블 하드코딩 5개를 `report/constants.py` 상수로, 빈 표 방어

**테스트**

- `tests/test_measure_statistics.py` — 상수 이름 변경 반영 + **백분위 기대값 5곳을 비율 스케일로**
  (`>= 99.0` → `>= 0.99`, `<= 5.0` → `<= 0.05`, `approx(100.0)` → `approx(1.0)`, `approx(99.0)` → `approx(0.99)`)
- `tests/test_strategy_expiry_periods.py` — 상수 이름 변경 반영 (2곳)
- `tests/test_report_tables.py` — 백분위 표시값이 그대로임을 고정
- `tests/test_studies_futures_runner.py` · `tests/test_strategy_expiry_trading.py` — 신규 인바리언트
- 신규: 네 계층 `판정가능` 값 일치 · 표본 하한 단일 정의 · 표본 0건 전 지표 공백 ·
  백분위 비율 계약 · 두 출력 경로의 표시값 일치

**문서**

- `docs/COMMANDS.md`: **변경 없음** — 실행 명령어와 CLI 옵션이 바뀌지 않는다
- `src/verify_lab/CLAUDE.md`: **변경 있음** — 「계층 간 계약」의 표본 부족 판정선에 상수 위치를 적는다

### 데이터/결과 영향

- **`futures_leverage` 산출물 CSV 의 `판정가능` 열이 `True`/`False` → `예`/`아니오` 로 바뀐다.**
  실측으로 `docs/research/선물_대_레버리지_ETF.md` 는 이 컬럼을 인용하지 않으므로 **결과 문서 수치는 바뀌지 않는다**
- **통계값은 하나도 바뀌지 않는다.** 하한 값(10)이 그대로이므로 판정 결과도 같다
- `storage/results/` 는 git 제외이며 재생성 가능하다. **재실행은 이 계획서의 검증 수단이지 산출물 갱신이 목적이 아니다**

## 6) 단계별 계획(Phases)

### Phase 0 — 인바리언트를 테스트로 먼저 고정(레드 허용)

> 이 Phase 가 필요한 이유: 「판정가능 값의 동일성」과 「표본 하한의 단일성」은 **정의**이며,
> 지금 깨져 있다는 사실을 테스트가 먼저 말해야 고친 뒤에도 다시 깨지지 않는다.

**작업 내용**:

- [x] `판정가능` 을 내는 **네 경로가 전부 `JUDGEABLE_YES`/`JUDGEABLE_NO` 만 낸다**는 테스트 (레드 예상: futures_leverage)
- [x] 네 모듈이 노출하는 표본 하한이 **`measure.constants.MIN_SAMPLE_PER_CELL` 과 같은 값**이라는 테스트.
      **`is` 비교를 쓰지 않는다** — 작은 정수는 파이썬이 캐싱해 서로 다른 정의여도 항상 통과한다.
      값 비교라야 나중에 한쪽이 갈라졌을 때 잡힌다 (레드 예상: 지금은 넷 다 자체 정의라 우연히 통과한다.
      **그래서 이 테스트는 「자체 정의가 없다」도 함께 검사한다** — 모듈 소스에 하한 리터럴이 남아 있지 않은지 본다)
- [x] `_period_row` 가 표본 0건이면 **손절 건수를 포함해 모든 지표가 비어 있다**는 테스트 (레드 예상)
- [x] `_summary_block` 이 `HORIZON_LABELS` 밖 구간을 받으면 **예외를 던진다**는 테스트 (레드 예상)
- [x] `statistics` 가 내는 **백분위가 0~1 비율**이라는 테스트 — 계층 간 계약 「`measure` 는 비율 그대로」 (레드 예상)
- [x] 같은 백분위가 **두 출력 경로에서 같은 값·같은 자릿수**로 나온다는 테스트
      (`report.build_test_table` 과 `option_expiry` 의 `to_display_columns` 경로) (레드 예상)
- [x] `futures_leverage` 의 모든 산출물 컬럼이 **`OUTPUT_LABELS` 로 덮인다**는 테스트 (레드 예상)

---

### Phase 1 — 판정가능과 표본 하한 단일화(그린 유지)

**작업 내용**:

- [x] `measure/constants.py` 에 **`MIN_SAMPLE_PER_CELL`** 을 신설하고 **왜 하나인지**를 docstring 에 적는다.
      이름은 원칙 12의 「**칸당** 유효 표본」에서 왔다 — 검정 하한도 (기준 × 구간) 칸의 표본이므로 같은 말이다.
      원칙 12가 「10건」을 명시하고 원칙 17이 「원칙 12의 10건」이라며 같은 값임을 선언하는 것이 통합 근거다
- [x] 잘못된 주석 두 곳을 사실과 맞춘다 — "세 곳에 있었다"(실제로는 넷이고 하나는 지금도 남아 있다),
      "지금 있는 세 개"(실제로는 네 개이며 이제 하나가 된다)
- [x] **네 곳의 옛 이름을 별칭으로 남기지 않는다.** 별칭을 두면 이름이 다섯이 되어 통합의 목적이 사라진다 —
      호출처와 테스트의 import 를 새 이름으로 고친다
      (`MIN_SAMPLE_FOR_TEST`·`MIN_SAMPLE_PER_CELL`·`MIN_SAMPLE_FOR_AXIS`·`MIN_PERIOD_SAMPLE` 전부 제거.
      `leverage_tracking` 의 이름만 우연히 같으므로 그쪽은 자체 정의를 지우고 재노출로 바꾼다)
- [x] `futures_leverage/runner.py` — `COL_JUDGEABLE` 로컬 정의와 `MIN_SAMPLE_FOR_AXIS` 를 제거하고
      공통 상수를 import 한다. `_summarize` 가 **문자열**을 넣게 고친다
- [x] `option_expiry/runner.py` 의 하한 import 를 `measure/constants.py` 경로로 바꾼다

**Validation**:

- [x] Phase 0 의 판정가능·하한 관련 레드 테스트가 그린이 된다

---

### Phase 2 — 표본 0건과 조용한 NaN 차단(그린 유지)

**작업 내용**:

- [x] `strategy/expiry_runner.py` `_period_row` — 표본 0건이면 손절 건수도 `np.nan` 으로 둔다.
      **`labels` 가 있는데 실제로 0건인 경우와 구분**해야 하므로 `empty` 기준으로 가른다
- [x] `leverage_tracking/runner.py` `_summary_block` — `HORIZON_LABELS.map` 이 조용히 NaN 을 내지 않게 한다.
      같은 파일 `_distribution_rows` 가 이미 `HORIZON_LABELS[horizon]` 로 KeyError 를 내므로 **그쪽에 맞춘다**
- [x] **백분위의 자릿수가 갈린 근본 원인은 `measure` 가 0~100 을 내는 것이다.**
      계층 간 계약이 "`measure` 는 비율(0~1) 그대로, 저장 직전 백분율 2자리"로 정했고
      `.claude/rules/python.md` 도 "모든 비율 값은 0~1 사이 소수"를 요구하는데,
      `statistics._percentile` 만 `× RATE_TO_PERCENT` 를 해서 계약 밖으로 나간다.
      그래서 두 출력 경로가 이 값을 서로 다르게 취급하게 됐다 —
      `report/tables:305` 는 백분율로 보고 2자리, `option_expiry` 는 확률로 보고 4자리
- [x] `statistics._percentile` 이 **비율(0~1)** 을 내도록 고친다. 함수 docstring 의 반환 설명도 함께 고친다
- [x] `report/tables.build_test_table` 의 백분위 4개를 `.round(PERCENT_DECIMALS)` 에서 `_to_percent(...)` 로 바꾼다.
      **표시값은 그대로다** — `0.4567 × 100` 을 2자리로 반올림한 값과 `45.67` 을 2자리로 반올림한 값이 같다
- [x] `option_expiry/constants.py` — 백분위 4개를 `PROBABILITY_OUTPUT_COLUMNS` 에서 `PERCENT_OUTPUT_COLUMNS` 로 옮긴다.
      **이제 넣어도 100을 두 번 곱하지 않는다** — 앞의 두 항목으로 입력이 비율이 됐기 때문이다.
      **세 번째 변환 목록을 만들지 않는다**: 계약을 지키면 기존 두 목록으로 충분하고,
      우회 목록을 만들면 「measure 는 비율로 낸다」가 예외를 갖게 된다

**Validation**:

- [x] Phase 0 의 표본 0건·NaN·자릿수 레드 테스트가 그린이 된다

---

### Phase 3 — futures_leverage 출력 계층을 저장소 관용에 맞춘다(그린 유지)

**작업 내용**:

- [x] `futures_leverage/constants.py` 에 결과 컬럼 상수를 모은다 —
      `runner.py:89-110` 의 기존 `COL_*` 를 옮기고, 리터럴로만 있던 것
      (`RollCost`·`RebalanceError`·`HoldError`·`InterestGain`·`Residual`·`FuturesMinusEtf`·`HoldMinusEtf`·
      `WipeoutCount`·`WindowCount`·`FirstWipeoutDate`·`DividendAdjustment`·
      `MaxEffectiveLeverageDaily`·`MaxEffectiveLeverageMonthly`·`AheadHorizonCount`·`TestedHorizonCount`·
      롤 이벤트 11개)을 상수로 만든다
- [x] `comparison.decompose` 와 `continuous.roll_events_frame` 이 그 상수를 쓰게 한다
- [x] `futures_leverage/constants.py` 에 `OUTPUT_LABELS` 를 두고, 다른 네 검증과 같은 관용으로 맞춘다.
      표마다 컬럼 구성이 달라 사전이 8개로 갈려 있으므로 **하나로 합칠지 표별로 둘지 판단하고 근거를 남긴다**
- [x] `scripts/studies/run_futures_leverage.py` — 사전 정의를 `src` import 로 바꾸고,
      `main` 의 리터럴 2곳(`outputs.wipeouts["WipeoutCount"]`·`comparison["Horizon"]`)을 상수로 바꾼다
- [x] `scripts/studies/run_option_expiry.py` — 한글 레이블 5개를 `report/constants.py` 상수로 바꾼다
      (`DISPLAY_EXCLUDED`·`DISPLAY_MEAN`·`DISPLAY_MEDIAN`·`DISPLAY_UP_RATE` 는 이미 있고,
      `"진입"` 만 새로 필요하다 — **`DISPLAY_SIGNAL_COUNT`("신호")와 뜻이 다른지 확인**하고 판단한다)
- [x] `scripts/studies/run_option_expiry.py` — 빈 표를 `_save` 로 넘기지 않도록 막고,
      **건너뛴 사실을 로그에 남긴다** (조용히 빠지면 산출물이 하나 없는 것을 사용자가 모른다)

**Validation**:

- [x] Phase 0 의 `OUTPUT_LABELS` 레드 테스트가 그린이 된다

---

### Phase 4 — 재실행 확인과 문서 정리, 최종 검증

**작업 내용**

- [x] `poetry run python scripts/studies/run_futures_leverage.py` 를 실행해
      **`판정가능` 열이 `예`/`아니오` 로 나오는지** 산출물 CSV 로 확인한다
- [x] `poetry run python scripts/studies/run_option_expiry.py` 를 실행해
      **백분위 자릿수가 2자리인지**와 표가 9개 전부 저장되는지 확인한다
- [x] 두 실행의 **통계값이 이전과 같은지** 확인한다 — 하한 값이 그대로이므로 달라지면 안 된다
- [x] `src/verify_lab/CLAUDE.md` 「계층 간 계약」의 표본 부족 판정선에 **상수가 어디 있는지**를 적는다
- [x] `docs/COMMANDS.md`: **변경 없음** (실행 명령어·CLI 옵션 불변)
- [x] 자동 포맷 적용 — `poetry run black .`
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [x] `poetry run python validate_project.py` (passed=876, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 측정 / 판정가능과 표본 하한을 공통 계층 하나로 모으고 futures_leverage 의 불린 값을 바로잡음
2. 측정 / 검증마다 갈라져 있던 판정가능·표본 하한을 단일화하고 표본 0건 칸의 0 을 걷어냄
3. 검증 / futures_leverage 의 판정가능을 문자열로 맞추고 출력 레이블을 src 로 옮김
4. 측정 / 표본 하한 네 상수를 하나로 통합하고 조용히 NaN 을 내던 두 자리를 막음
5. 측정 / 이전 작업이 절반만 끝낸 판정가능 통합을 마무리하고 주석을 사실과 맞춤

## 7) 리스크(Risks)

- **`_percentile` 의 반환 단위를 바꾸는 것이 이 계획서에서 가장 넓게 퍼지는 변경이다.**
  `measure` → `report` → `option_expiry` 세 계층을 한 번에 지나고, 중간에 하나만 고치면
  **표시값이 100배로 틀리는데 예외는 나지 않는다.**
  **완화**: Phase 0 이 「비율로 나온다」와 「두 경로의 표시값이 같다」를 둘 다 고정한다.
  Phase 4 에서 실제 산출물 CSV 의 백분위가 0~100 범위인지 눈으로 확인한다
- **`futures_leverage` 사전 8개를 하나로 합치면 `to_display_columns` 의 "사전이 덮지 못한 컬럼" 검사가
  무력해진다** — 표마다 컬럼이 다른데 사전이 전부를 덮으면 오타를 잡지 못한다.
  **완화**: 다른 네 검증이 하나의 `OUTPUT_LABELS` 를 쓰고도 검사가 동작하는 이유를 먼저 확인하고
  (`option_expiry` 는 표마다 `columns` 로 교집합을 낸다) 같은 관용을 따른다
- **`MIN_SAMPLE_FOR_TEST` 를 재노출로 바꾸면 기존 테스트의 import 가 깨질 수 있다**.
  **완화**: `tests/test_measure_statistics.py:60` 이 그 이름을 import 하므로 이름을 유지한 채 값만 공통에서 가져온다
- **`판정가능` 값 변경이 산출물 소비 코드를 깨뜨릴 수 있다**.
  **완화**: 실측으로 `docs/research/` 에 인용이 없음을 확인했고, `measure.screening` 은 오히려 지금 동작하지 않던 것이 동작하게 된다

## 8) 메모(Notes)

- **이 계획서는 `PLAN_audit_fixes.md`(Done)가 Non-Goals 로 남긴 것의 일부를 잇는다.**
  그 계획서는 87건 중 16건을 처리했고, 이번 감사에서 그 잔여분과 **이전 작업이 절반만 처리해
  새로 생긴 결함**(판정가능 통합 미완 + 그것을 완료로 적은 주석)이 함께 나왔다
- 표본 하한 통합은 사용자 결정(2026-09-05) — 원칙 12·17이 「10건」을 명시하고
  원칙 17이 「원칙 12의 10건」이라며 같은 값임을 선언하는 것이 근거다.
  **대가**: 나중에 축마다 다른 하한이 필요해지면 다시 갈라야 한다
- 실측(2026-09-05): `_summarize(np.array([0.01]*12), 5)["Judgeable"]` → `True` (bool),
  표본 3건 → `False`. 다른 세 곳은 `"예"` / `"아니오"`
- 실측(2026-09-05): 표본 하한 네 개가 전부 10 —
  `MIN_SAMPLE_FOR_TEST` · `MIN_SAMPLE_PER_CELL` · `MIN_SAMPLE_FOR_AXIS` · `MIN_PERIOD_SAMPLE`
- 실측(2026-09-05): `pd.Series([5, 999]).map(HORIZON_LABELS)` → `['1주', nan]`
- 실측(2026-09-05): `validate_project.py` 착수 전 상태 — passed=862, failed=0, skipped=0

- 실측(2026-09-05): `docs/research/선물_대_레버리지_ETF.md` 에 `판정가능`·`True`·`False` 인용 **0건** —
  이 컬럼의 값을 바꿔도 결과 문서 수치가 바뀌지 않는다
- 실측(2026-09-05): Phase 4 재실행에 필요한 시세가 전부 있다 —
  `storage/market/` 에 선물 2종(`KRDRVFUK2I`·`KRDRVFUKQI`)과 짝 ETF·ETN, `storage/series/CD91.csv` 확인
- **자체 검증에서 계획서 자신의 모순을 하나 고쳤다.** 처음에는 "백분위를 `PERCENT_OUTPUT_COLUMNS` 로 옮긴다"
  고 적었는데, 백분위가 이미 0~100 이라 **100을 두 번 곱하게 된다.** 근본 원인이
  「`measure` 가 계약을 어기고 백분율을 낸다」임을 확인하고 그쪽을 고치는 것으로 바꿨다 —
  우회 목록을 만들었다면 계약에 예외가 하나 생겼을 것이다

### 진행 로그 (KST)

- 2026-09-05 22:41: 계획서 작성. 전수 감사 50건 중 12건을 이 계획서의 범위로 확정
- 2026-09-05 22:47: 자체 검증 반영 — 백분위 처리의 모순 수정, 상수 이름(`MIN_SAMPLE_PER_CELL`) 확정,
  별칭 금지 명시, `is` 비교 함정 명시
- 2026-09-06 06:50: Phase 0 — 계층 계약 테스트 신설. 레드 확인
  (판정가능 자체 정의 1곳 · 표본 하한 자체 정의 4곳 · 백분위 단위 · 표본 0건 손절 건수 · `HORIZON_LABELS`)
- 2026-09-06 06:56: Phase 1 — `MIN_SAMPLE_PER_CELL` 신설, 네 계층의 하한 정의 제거,
  `futures_leverage` 의 `판정가능` 을 문자열로. 잘못된 주석 두 곳 정정
- 2026-09-06 07:00: Phase 2 — `_percentile` 을 비율로, `report` 를 백분율 변환 경로로,
  `option_expiry` 백분위를 백분율 목록으로. 표본 0건 손절 건수와 `HORIZON_LABELS` 방어
- 2026-09-06 07:04: Phase 3 — `futures_leverage` 컬럼 상수 43개 신설, `OUTPUT_LABELS` 를 `src` 로.
  scripts 의 사전 8개(117줄) 제거. 통합 과정에서 **두 컬럼이 같은 한글 이름을 쓰던 것**이 드러나 구별
- 2026-09-06 07:06: Phase 4 — 두 검증 재실행. `판정가능` 이 `예`, 백분위가 0~100·2자리로 확인.
  **이전 실행과 통계값이 하나도 다르지 않음**(QQQ 검정표 전 컬럼 일치)
- 2026-09-06 07:07: 품질 검증 통과 (passed=876, failed=0, skipped=0). Done

---
