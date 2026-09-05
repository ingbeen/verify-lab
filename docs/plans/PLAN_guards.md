# Implementation Plan: 조용히 지나가는 자리를 막고, 남겨둘 자리에는 근거를 적는다

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

**작성일**: 2026-09-06 07:25
**마지막 업데이트**: 2026-09-06 07:33
**관련 범위**: measure, report, studies(futures_leverage), strategy
**관련 문서**: `CLAUDE.md`, `src/verify_lab/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/python.md`

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

- [x] 목표 1: **도달하면 결과가 틀리는 자리에서 멈추게 한다** — 지금은 정렬 전제·빈 입력·계약 위반이 예외 없이 통과한다
- [x] 목표 2: **조용히 사라지는 표본과 스키마를 남긴다** — 제외 건수 유실, 빈 표의 컬럼 유실
- [x] 목표 3: **남겨두기로 한 fallback 에는 「왜 남기는가」를 적는다** — 근거 없는 관용은 다음 사람이 다시 판단한다

## 2) 비목표(Non-Goals)

**전수 감사 50건 중 이번 계획서의 범위는 12건이고, 그중 4건은 「확인 후 유지」다.**

- **리팩토링·문서** — 죽은 조건, frozen dataclass 우회, `expanding_rank` 재계산, 문서 정리 → `PLAN_refactor_docs`
- **판정 기준·산식을 바꾸지 않는다.** 막는 자리를 늘릴 뿐 계산 결과는 그대로다
- **시세 재수집 금지**

### 감사에서 지적했으나 **고치지 않기로 한 것** (실측으로 전제가 달랐다)

| 항목 | 왜 안 고치나 |
| --- | --- |
| `report/tables._horizon_label` 의 `f"{days}일"` fallback | **의도된 설계다.** `report/constants.py` 가 "여기 없는 구간은 그 형태로 나가므로 등록하지 않는다"고 명시했다. `report` 는 공통 계층이라 어떤 구간이 올지 모른다 — 검증마다 격자가 다르다 |
| `leverage_tracking/breakdown` 의 `qcut` 실패를 넘기는 것 | **이미 산출물에 남는다.** `runner` 가 `fillna(AXIS_VALUE_UNAVAILABLE)` 로 「판정 불가」를 표에 찍는다. DEBUG 한 줄만 남는다고 본 것은 잘못이었다 |
| `report/tables._basis_label` 의 원본값 반환 | 호출처 셋 중 하나는 **오류 메시지를 만드는 자리**라 원본을 보여주는 것이 맞고, 나머지는 `measure` 가 채운 값만 받는다 |
| `utils/logger` 의 `Path.cwd()` fallback | **로깅 초기화에서 예외를 던지면 더 나쁘다.** 저장소 안에서만 실행되므로 도달하지 않으며, 도달해도 로그 경로만 절대경로가 된다 |

> **네 항목은 지우지 않고 「왜 남기는가」를 코드에 적는다** (목표 3). 근거가 없으면 다음 감사에서
> 같은 지적이 다시 나온다 — 실제로 이번 감사가 그렇게 나왔다.

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

`.claude/rules/python.md` 「불가능 조건 처리」가 **"조용히 기본값을 반환하거나 건너뛰지 않는다"**
를 요구하는데, 아래 자리들이 그 규칙 밖에 있다.

**① 전제를 검사하지 않고 쓰는 자리**

- `futures_leverage/contracts.py` `contract_multiplier_on` — 거래승수 이력이 **시간순이라고 전제**하고
  선형 스캔한다. 정렬이 어긋나면 잘못된 승수를 고르는데, 그 docstring 자신이
  **"경계를 하루 잘못 잡으면 그날의 명목금액이 두 배로 틀린다"** 고 경고한다
- `futures_leverage/comparison.py` `build_window_table` — `next(iter(...))` 앞에 빈 dict 검사가 없어
  `StopIteration` 이 난다. 이것은 `ValueError` 로 잡히지 않아 호출 측이 다루기 어렵다
- `futures_leverage/continuous.py` `build_continuous_series` — `present.iloc[0]` 을 무방비로 쓴다.
  **같은 파일의 `plan_rolls` 는 같은 조건을 `RuntimeError` 로 막는다** — 한 모듈 안에서 방어 수준이 갈렸다

**② 표본·스키마가 조용히 사라지는 자리**

- `strategy/runner.py` — 한 대상의 신호가 전부 제외되면 `continue` 하는데,
  그때 `block.excluded_count` 가 요약에도 집계에도 남지 않는다.
  같은 함수의 `_summarize` 가 **"「신호 + 제외 = 전체 신호 수」가 성립한다"** 고 적었는데 그 경로에서만 깨진다
- `futures_leverage/continuous.py` `roll_events_frame` — 롤이 0건이면 **컬럼 없는 빈 표**를 낸다.
  이 저장소의 다른 빈 표는 전부 dtype 을 유지한다(`offsets._empty_frame`·`weekly_exit._empty_schedule`)

**③ 사유 없이 통과하는 자리**

- `measure/statistics.py` — 모집단 크기가 표본과 **같으면** 비복원 추출이 매번 전체를 뽑아
  귀무분포가 상수가 된다. p 값이 항상 1.0 인데 **사유가 남지 않아** 「검정했더니 유의하지 않다」로 읽힌다.
  바로 위 줄이 `pool.size < sample_count` 는 사유를 남기므로 경계 하나 차이다
- `futures_leverage/continuous.py` `_decide_execution_date` — 구간이 짧으면 롤을 조용히 앞당기면서
  `fallback=False` 로 낸다. **규칙이 정한 시점이 아닌데 산출물에서는 정상 롤과 구별되지 않는다**

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 측정의 원칙 3·17(표본 수 보존)
- `src/verify_lab/CLAUDE.md` — 「명시적 검증 / 불가능 조건」, 「예외는 숨기지 않는다」, 절대 원칙 4(표본 보존)
- `tests/CLAUDE.md` — 예외 테스트(`ValueError` / `RuntimeError` 구분), 경계 조건
- `.claude/rules/python.md` — 「불가능 조건 처리」

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 전제를 검사하지 않던 세 자리가 예외를 던진다 (입력 검증은 `ValueError`, 내부 불변조건은 `RuntimeError`)
- [x] 제외 건수와 빈 표 스키마가 사라지지 않는다
- [x] 사유 없이 통과하던 두 자리가 사유를 남긴다
- [x] **유지하기로 한 네 자리에 「왜 남기는가」가 적혀 있다**
- [x] 회귀/신규 테스트 추가
- [x] `poetry run python validate_project.py` 통과 — passed=888, failed=0, skipped=0
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트(`docs/COMMANDS.md` / CLAUDE.md / plan 등 — 각각 변경 여부 명시)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 근거·실측 수치를 루트 `CLAUDE.md` 의 프로젝트 설정 절이 정한 목적지로 이관.
      `/impl-plan` 스킬 "근거 승격" 참고)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/studies/futures_leverage/contracts.py` — 승수 이력 정렬 불변조건
- `src/verify_lab/studies/futures_leverage/comparison.py` — 빈 입력 검증
- `src/verify_lab/studies/futures_leverage/continuous.py` — `present` 방어, 빈 롤 표 스키마, 앞당김 표시
- `src/verify_lab/measure/statistics.py` — 모집단이 표본과 같을 때의 사유
- `src/verify_lab/strategy/runner.py` — 전부 제외된 대상의 제외 건수 보존
- `src/verify_lab/report/tables.py` · `src/verify_lab/report/constants.py` ·
  `src/verify_lab/studies/leverage_tracking/breakdown.py` · `src/verify_lab/utils/logger.py` —
  **유지 근거만 주석으로 추가** (동작 변경 없음)

**테스트**

- `tests/test_studies_futures_contracts.py` · `tests/test_studies_futures_comparison.py` ·
  `tests/test_studies_futures_continuous.py` · `tests/test_measure_statistics.py` ·
  `tests/test_strategy_runner.py` — 신규 경계·예외 테스트

**문서**

- `docs/COMMANDS.md`: **변경 없음** — 실행 명령어와 CLI 옵션이 바뀌지 않는다
- `src/verify_lab/CLAUDE.md`: **변경 없음** — 계층 간 계약이 바뀌지 않는다. 막는 자리를 늘릴 뿐이다

### 데이터/결과 영향

- **정상 입력의 계산 결과는 바뀌지 않는다.** 늘어나는 것은 비정상 입력에서의 예외다
- **`statistics` 의 사유 하나가 늘어난다** — 모집단이 표본과 같은 칸이 있으면 그 칸의 검정 결과가
  값 대신 사유로 바뀐다. **현재 실행 경로에서는 발생하지 않으므로 산출물이 달라지지 않는다**
  (Phase 4 에서 재실행으로 확인한다)
- **롤 앞당김 표시가 바뀔 수 있다** — 구간이 짧아 앞당겨진 롤이 실제로 있으면
  `roll_events.csv` 의 열이 `True` 로 바뀐다. **Phase 4 실측 결과 코스피200·코스닥150 모두 0건**이라
  값은 그대로이고, 열 이름만 「만기가 강제한 롤」 → 「규칙대로 못 한 롤」로 정확해졌다

## 6) 단계별 계획(Phases)

### Phase 0 — 막을 자리를 테스트로 먼저 고정(레드 허용)

**작업 내용**:

- [x] 승수 이력이 시간순이 아니면 예외라는 테스트 (레드 예상)
- [x] `build_window_table` 이 빈 입력을 거부한다는 테스트 (레드 예상 — 지금은 `StopIteration`)
- [x] `roll_events_frame` 이 이벤트 0건에서도 **컬럼을 유지**한다는 테스트 (레드 예상)
- [x] 모집단이 표본과 같으면 사유가 남는다는 테스트 (레드 예상)
- [x] 한 대상의 신호가 전부 제외되면 **그 사실이 요약에 남는다**는 테스트 (레드 예상)
- [x] 구간이 짧아 앞당겨진 롤이 **정상 롤과 구별된다**는 테스트 (레드 예상)

---

### Phase 1 — 전제를 검사하고 예외를 던진다(그린 유지)

**작업 내용**:

- [x] `contract_multiplier_on` — 이력이 시간순인지 검사한다.
      **`ValueError` 인지 `RuntimeError` 인지 먼저 가른다** — 이력은 이 저장소가 소유한 상수이므로
      어긋나면 **내부 불변조건 위반**이다 (`.claude/rules/python.md` 구분 기준)
- [x] `build_window_table` — 빈 `returns_by_method` 를 `ValueError` 로 거부한다.
      호출 측이 넘기는 값이므로 입력 검증이다
- [x] `build_continuous_series` — `present` 가 비면 `plan_rolls` 와 **같은 방식**으로 막는다.
      한 모듈 안에서 방어 수준이 갈리지 않게 한다

---

### Phase 2 — 사라지는 표본과 스키마를 남긴다(그린 유지)

**작업 내용**:

- [x] `roll_events_frame` — 이벤트 0건에서도 컬럼과 dtype 을 유지한다.
      **이 저장소의 기존 관용**(`offsets._empty_frame`·`weekly_exit._empty_schedule`)을 그대로 따른다
- [x] `strategy/runner.py` — 체결이 하나도 없는 대상의 **제외 건수를 요약에 남긴다.**
      집계표에 빈 행을 만들지, 실행 요약(`meta`)에만 담을지 **먼저 판단한다** —
      `_summarize` 는 `block.trades` 를 읽으므로 빈 행을 만들려면 그 함수가 빈 입력을 다뤄야 한다
- [x] `statistics` — 모집단이 표본과 **같을 때**도 사유를 남긴다.
      기존 사유 문구를 그대로 쓸지 새로 둘지 판단한다 — 「작아서」가 아니라 「같아서」이므로
      **같은 문구를 쓰면 거짓이 된다**
- [x] `_decide_execution_date` — 구간이 짧아 앞당긴 경우를 `fallback=True` 로 표시한다.
      **그 값의 뜻이 「규칙이 정한 시점이 아니다」로 넓어지므로** 필드 docstring 과
      산출물 레이블(`만기가 강제한 롤`)이 여전히 맞는지 확인하고, 안 맞으면 함께 고친다

---

### Phase 3 — 남겨두는 자리에 근거를 적는다(그린 유지)

> 이 Phase 가 없으면 **다음 감사에서 같은 네 항목이 다시 지적된다.** 실제로 이번 감사가 그랬다.

**작업 내용**:

- [x] `report/tables._horizon_label` — fallback 이 의도된 설계임을 적는다
      (`report` 는 공통 계층이라 검증마다 다른 격자를 미리 알 수 없다)
- [x] `leverage_tracking/breakdown` 의 `qcut` 예외 처리 두 곳 — **결과가 산출물에 「판정 불가」로
      남는다**는 사실을 적는다. 지금 주석은 "예외로 멈추지 않는다"만 말해 흔적이 없는 것처럼 읽힌다
- [x] `report/tables._basis_label` — 오류 메시지 경로에서 원본값이 필요하다는 것을 적는다
- [x] `utils/logger._find_project_root` — 로깅 초기화에서 예외를 던지지 않는 이유를 적는다

---

### Phase 4 — 재실행 확인과 최종 검증

**작업 내용**

- [x] `poetry run python scripts/studies/run_futures_leverage.py --index KOSPI200` 을 실행해
      **롤 앞당김 표시가 몇 건이나 바뀌었는지** 센다. 바뀌었으면 그 수를 이 계획서에 적는다
- [x] 나머지 산출물이 이전 실행과 같은지 확인한다
- [x] `docs/COMMANDS.md`: **변경 없음** (실행 명령어·CLI 옵션 불변)
- [x] 자동 포맷 적용 — `poetry run black .`
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [x] `poetry run python validate_project.py` (passed=888, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 검증 / 조용히 지나가던 자리를 막고 남겨둔 fallback 에 근거를 남김
2. 검증 / 전제 미검사·표본 유실·사유 없는 통과 여섯 곳을 예외와 표시로 바꿈
3. 검증 / 거래승수 정렬과 빈 입력을 불변조건으로 고정하고 빈 표의 스키마를 지킴
4. 측정 / 모집단이 표본과 같은 칸에 사유를 남기고 제외 건수 유실을 막음
5. 검증 / 방어 수준이 갈려 있던 자리를 맞추고 유지 결정에 이유를 적음

## 7) 리스크(Risks)

- **롤 앞당김 표시를 바꾸면 산출물이 달라진다.** 「만기가 강제한 롤」의 뜻이 넓어지므로
  그 열을 읽던 사람의 해석이 바뀐다.
  **완화**: Phase 4 에서 실제 건수를 세고, 0 건이 아니면 레이블과 docstring 을 함께 고친다
- **`strategy/runner` 의 빈 행 처리는 `_summarize` 의 전제를 건드린다.** 그 함수는
  `block.trades[DISPLAY_EVENT_ID].nunique()` 를 부르므로 빈 입력에서 깨진다.
  **완화**: Phase 2 에서 「빈 행을 만들지, 요약에만 담을지」를 먼저 판단한다.
  **더 단순한 쪽을 고른다** — 이 경로는 현재 데이터에서 발생하지 않는다
- **예외를 늘리면 지금까지 통과하던 입력이 막힐 수 있다.**
  **완화**: Phase 4 에서 실제 검증을 재실행해 확인한다

## 8) 메모(Notes)

- **감사 4건은 실측으로 「고치지 않는다」로 결론냈다** (2026-09-06). 근거는 2절 표에 있다.
  특히 `qcut` 실패는 **이미 산출물에 「판정 불가」로 남고 있었다** — DEBUG 한 줄만 남는다고
  본 것이 잘못이었다
- 실측(2026-09-06): 착수 전 `validate_project.py` — passed=881, failed=0, skipped=0

### 진행 로그 (KST)

- 2026-09-06 07:25: 계획서 작성. 감사 12건 중 8건을 고치고 4건은 근거만 남기기로 확정
- 2026-09-06 07:27: Phase 0 — 여섯 자리를 테스트로 고정하고 전부 레드 확인
- 2026-09-06 07:29: Phase 1 — 승수 이력 정렬(`RuntimeError`)·빈 방식(`ValueError`)·
  `present` 방어. **`plan_rolls` 와 같은 방식으로 맞춰** 한 모듈 안의 방어 수준을 통일
- 2026-09-06 07:31: Phase 2 — 빈 롤 표 스키마, `strategy` 제외 건수 보존,
  모집단 사유를 `<=` 로 확장, 롤 앞당김 표시.
  **`fallback` 의 뜻이 넓어져 레이블을 「만기가 강제한 롤」 → 「규칙대로 못 한 롤」로 고침**
- 2026-09-06 07:32: Phase 3 — 유지하기로 한 네 자리에 근거 기록
- 2026-09-06 07:33: Phase 4 — **롤 표시 변경 실측: 코스피200 0건 · 코스닥150 0건.**
  두 지수 모두 「구간이 짧아 앞당겨진 롤」이 실제로는 없었고, 기존 `True` 62건은 전부
  미결제약정 미역전이다. **산출물 수치가 바뀌지 않았고 열 이름만 정확해졌다**
- 2026-09-06 07:33: 품질 검증 통과 (passed=888, failed=0, skipped=0). Done

---
