# Implementation Plan: 데드코드 제거와 상수 통합 (동작 불변)

> 작성/운영 규칙(SoT): `/impl-plan` 스킬(`~/.claude/skills/impl-plan/SKILL.md`)을 반드시 참고하세요.  
> (이 템플릿을 수정하거나 새로운 양식의 계획서를 만들 때도 해당 스킬을 포인터로 두고 준수합니다.)

**상태**: 🔄 In Progress

---

🚫 **이 영역은 삭제/수정 금지** 🚫

**상태 옵션**: 🟡 Draft / 🔄 In Progress / ✅ Done

**Done 처리 규칙**:

- ✅ Done 조건: DoD 모두 [x] + `skipped=0` + `failed=0`
- ⚠️ **스킵이 1개라도 존재하면 Done 처리 금지 + DoD 테스트 항목 체크 금지**
- 상세: `/impl-plan` 스킬의 "3) 스킵 및 완료 규칙" 참고
- 위 조건은 `~/.claude/hooks/plan_lint.py`가 저장 시 자동 검사합니다

---

**작성일**: 2026-08-30 12:11
**마지막 업데이트**: 2026-08-30 12:11
**관련 범위**: measure, report, studies, strategy, utils, scripts
**관련 문서**: 루트 `CLAUDE.md`, `src/verify_lab/CLAUDE.md`, `scripts/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/python.md`, `.claude/rules/docs.md`

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

- [ ] 목표 1: **아무도 호출하지 않는 정의를 지운다.** 저장소 전체의 정의 689개를 전수 집계해 확인한 목록만 다룬다
- [ ] 목표 2: **계층 간 중복 정의된 상수를 통합한다** (`src/verify_lab/CLAUDE.md` 「상수 관리 3계층」이 "발견 즉시 통합"을 규정)
- [ ] 목표 3: **정의만 있고 리터럴을 쓰던 곳이 상수를 쓰게 한다**
- [ ] 목표 4: `pyright: ignore` 3곳을 **타입을 고쳐 근본 제거**한다
- [ ] 목표 5: `utils/` 4개 파일의 **파이썬 문법 설명 주석을 걷어내고 설계 근거 주석은 전부 보존**한다
- [ ] 목표 6: **산출물이 한 바이트도 바뀌지 않는다.** 이 계획서의 모든 변경은 동작 불변이다

## 2) 비목표(Non-Goals)

- **판정 로직을 바꾸지 않는다.** `PLAN_judgment_contract_fix.md` 가 담당한다
- **계약 문서는 「지워진 것을 지웠다고 적는 것」까지만 손댄다.** `to_markdown`·`build_comparison_table`
  삭제에 따라 `docs/ROADMAP.md` 출력 계약 표의 마크다운 렌더링 행 하나를 정리하는 것이 유일한 예외이며,
  **새 계약을 만들거나 기존 계약의 판단을 바꾸지 않는다**
- **`strategy/performance.py` 는 이 계획서에서 다루지 않는다.** 위 계획서가 삭제한다
- **`docs/COMMANDS.md` 에 남은 그리드 스크립트 안내는 이 계획서의 범위가 아니다.** 문서 단독 수정으로 별도 처리한다
- **테스트 코드의 `# type: ignore` 4곳은 손대지 않는다.** pytest fixture 와 `urllib.error.HTTPError` 스텁의 한계라 정당하다
- **`scripts/data/` 의 실측 스크립트는 손대지 않는다.** `TableLogger` 를 직접 쓰지만 정상 사용이다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

#### ① 호출되지 않는 정의가 쌓여 있다

정의 689개의 참조를 전수 집계했다. 아래는 **정의부를 제외한 실제 호출이 0건**인 것들이다.

| 대상 | 위치 | 성격 |
| --- | --- | --- |
| `SUPPORT_TOTAL_WITHOUT_PERIOD` | `measure/screening.py:75` | 실제로는 `len(checks)` 로 계산 |
| `Align.CENTER` + `_format_cell` 의 CENTER 분기 | `utils/formatting.py:29,94-97` | 어떤 표도 가운데 정렬을 쓰지 않음 |
| `WeeklyExitSchedule.valid_count` · `.excluded_count` | `studies/option_expiry/weekly_exit.py:132,141` | `entry_count` 만 실제 사용(`:270`) |
| `OffsetAssignment.unassigned_count` | `studies/option_expiry/offsets.py:53` | |
| `AnnualDriftResult.spread_excluding_edges` + `MIN_YEARS_FOR_EDGE_SPREAD` | `studies/usdkrw_equivalence/regression.py:67,29` | 계산만 하고 아무도 읽지 않음 |
| `RegressionResult.alpha_daily` (필드) | `studies/usdkrw_equivalence/regression.py:49` | 내부 계산에만 쓰임 |
| `setup_logger(level=...)` 파라미터 | `utils/logger.py:126` | 항상 `None` 으로만 호출됨 |
| `HORIZON_LABELS` 의 `63`·`126`·`252` | `report/constants.py:109-111` | 측정 구간이 단기로 바뀌어(결정 ㉑) 도달하지 않음 |
| `to_markdown` · `build_comparison_table` | `report/tables.py:399,322` | `report/__init__` 에서 export 만, 호출 0건 |

#### ② `HolidayExit` 는 지워진 대조축의 잔여물이다

`studies/option_expiry/weekly_exit.py:88-104` 의 docstring 은 `NEXT` 를 **"대조 전용이며 함께 산출한다"**
고 적었지만, `runner.py:295,304` 의 두 호출 모두 `on_holiday` 를 넘기지 않아 **`PREVIOUS` 만 쓰인다.**
`else` 분기가 프로덕션에서 도달 불가다.

**`docs/spec/option_expiry.md` 결정 ㉘ (2026-08-30 확정)이 이미 답을 담고 있다.**

> 결론이 난 대조축을 코드와 문서에서 지운다. 지운 것은 offset −10~+10 격자 · 월중 서수 대조 ·
> 가격 기준 대조 · **휴장 규칙 네 조합** · 국면×동시만기 전개다. … 수치는 결과 문서 1장
> 「지운 대조축」 표에 한 줄씩 남겼고, 재현은 git 이력에 맡긴다.

즉 이 축은 **의도적으로 제거됐고 `HolidayExit` 만 남았다.** 값이 하나뿐인 enum 은 분기가 없는
파라미터이며, 이 저장소가 「고를 것이 없는 필터」로 부르며 걷어낸 것과 같은 형태다(결정 ㉔ 계열).

#### ③ 같은 상수가 계층마다 따로 정의돼 있다

`src/verify_lab/CLAUDE.md` 「상수 관리 3계층」이 **"계층 간 중복 정의는 발견 즉시 통합한다"** 를 규정한다.

| 개념 | 현재 정의 위치 | 비고 |
| --- | --- | --- |
| 비율→백분율 (100) | `measure/statistics.py:150` · `report/constants.py:118` · `studies/usdkrw_equivalence/constants.py:192` (`RATE_PERCENT_TO_RATIO`) | **3계층** → `common_constants.py` |
| 원화 가격 자릿수 (0) | `studies/option_expiry/constants.py:239` · `studies/index_extreme/constants.py:111` | 2곳 → `common_constants.py` |
| KST 타임존 | `report/writer.py:26` (상수) · `utils/meta_manager.py:99` (리터럴) | 2계층 → `common_constants.py` |

> `TRADING_DAYS_PER_YEAR`(250)·`CALENDAR_DAYS_PER_YEAR`/`DAYS_PER_YEAR`(365)·`PERCENT_TO_RATE`(100.0)의
> 중복은 **`PLAN_judgment_contract_fix.md` 가 `performance.py` 를 지우면 자동으로 해소된다.**
> 그 계획서를 먼저 실행한다 (아래 「실행 순서」 참고).

#### ④ 상수가 있는데 리터럴을 쓴다

| 위치 | 리터럴 | 존재하는 상수 |
| --- | --- | --- |
| `studies/usdkrw_equivalence/runner.py:456,462` | `"Nav"` | `COL_NAV` (미사용 상태) |
| `studies/option_expiry/runner.py:253` | `"advanced_days"` | `COL_ADVANCED_DAYS` |
| `studies/usdkrw_equivalence/runner.py:187,198,217,222` | `(ETF_BASE, ETF_LEVERAGE)` **4회 반복** | `ETF_TARGETS` (미사용 상태) |
| `studies/usdkrw_equivalence/effective_cost.py:68-70` | `"raw"` · `"adjusted"` · `"nav"` | 없음 — 새로 만든다 |
| `studies/option_expiry/runner.py:664-694` | `summary.json` 키 전부 | 없음 — `index_extreme` 의 `KEY_*` 관용을 따른다 |

#### ⑤ 느슨한 타입이 `pyright: ignore` 를 부른다

`scripts/studies/run_option_expiry.py:87` 의 `_selected_datasets() -> tuple[object, ...]` 때문에
`:181`·`:202` 두 곳에 `pyright: ignore` 가 붙었다. **반환 타입을 좁히면 둘 다 사라진다.**

`report/tables.py:450` 의 `int(horizon)` 은 `_horizon_label(horizon: object)` 시그니처 탓이다.

#### ⑥ `utils/` 4개 파일이 저장소 관용과 어긋난다

`utils/formatting.py` · `cli_helpers.py` · `meta_manager.py` · `logger.py` 에 **"학습 포인트"** 라는
이름의 파이썬 문법 설명이 깔려 있다.

```
학습 포인트:
1. 데코레이터 패턴: 함수를 감싸서 추가 기능을 제공하는 고급 기법
3. self: 인스턴스 자신을 가리키는 참조 (Java의 this와 유사)
# with 문: 블록이 끝나면 자동으로 파일을 닫음 (finally 불필요)
```

나머지 저장소는 **"왜 이렇게 했는가"** 만 적는 고밀도 주석이다(`forward_return.py`·`screening.py` 등).
`.claude/rules/python.md` 「주석 작성 원칙 — 현재 코드의 상태와 동작만 설명」과도 어긋난다.

**설계 근거를 담은 주석은 이 파일들에도 있으며 전부 보존한다** — `print_row` 의 공백 2칸 보정 이유,
`_find_project_root` 의 10단계 제한, `MAX_HISTORY_COUNT` 의 존재 이유 같은 것들이다.

### 실행 순서 (중요)

**`PLAN_judgment_contract_fix.md` 를 먼저 완료한 뒤 이 계획서를 실행한다.**

- 그 계획서가 `performance.py` 를 지우면 250·365·100.0 상수 중복이 자동 해소된다
- 그 계획서가 `run_index_extreme.py` 의 고정 폭 컬럼을 걷어내면 `COLUMN_GAP` 이름 충돌
  (`report/constants.py` 의 `2`(int) 대 `run_index_extreme.py` 의 `"  "`(str))도 함께 사라진다
- 순서를 바꾸면 같은 곳을 두 번 손대게 된다

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」·「만들기 전에 사다리를 오른다」
- `src/verify_lab/CLAUDE.md` — 「상수 관리 3계층」과 상수 명명 접두사, 계층 간 의존 방향
- `scripts/CLAUDE.md` — CLI 계층의 제약사항
- `tests/CLAUDE.md` — 테스트 작성 규칙
- `.claude/rules/python.md` — 코딩 표준, 타입 힌트, 주석 작성 원칙
- `.claude/rules/docs.md` — 문서 규칙

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [ ] 기능 요구사항 충족 (목표 1~6 전부)
- [ ] 회귀/신규 테스트 추가 — 삭제한 대상을 참조하던 테스트를 정리하고, 상수 통합 후에도 값이 같은지 고정
- [ ] `poetry run python validate_project.py` 통과 (failed=0, skipped=0; passed/failed/skipped 수 기록)
- [ ] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [ ] 필요한 문서 업데이트(`docs/COMMANDS.md` / CLAUDE.md / plan 등 — 각각 변경 여부 명시)
- [ ] **세 검증을 재실행해 산출물이 직전과 동일함을 확인** (md5 대조)
- [ ] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 근거·실측 수치를 루트 `CLAUDE.md` 의 프로젝트 설정 절이 정한 목적지로 이관.
      `/impl-plan` 스킬 "근거 승격" 참고)
- [ ] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

**삭제 대상이 있는 파일**

- `src/verify_lab/measure/screening.py` · `report/constants.py` · `report/tables.py` · `report/__init__.py`
- `src/verify_lab/utils/formatting.py` · `logger.py` · `cli_helpers.py` · `meta_manager.py`
- `src/verify_lab/studies/index_extreme/constants.py`
- `src/verify_lab/studies/option_expiry/weekly_exit.py` · `offsets.py` · `runner.py`
- `src/verify_lab/studies/usdkrw_equivalence/regression.py`

**상수 통합 대상**

- `src/verify_lab/common_constants.py` (통합 목적지)
- `src/verify_lab/measure/statistics.py` · `report/constants.py` · `report/writer.py`
- `src/verify_lab/utils/meta_manager.py`
- `src/verify_lab/studies/*/constants.py`

**상수를 쓰게 바꾸는 파일**

- `src/verify_lab/studies/usdkrw_equivalence/runner.py` · `effective_cost.py`
- `src/verify_lab/studies/option_expiry/runner.py` · `constants.py`

**타입 수정**

- `scripts/studies/run_option_expiry.py` · `src/verify_lab/report/tables.py`

**테스트**

- 삭제 대상을 참조하는 테스트 정리 (`test_measure_screening.py`·`test_studies_expiry_weekly_exit.py`·
  `test_studies_expiry_offsets.py`·`test_studies_equivalence_regression.py`·`test_report_tables.py`·
  `test_formatting.py`·`test_logger.py` 등)

**문서**

- `docs/ROADMAP.md` — 출력 계약 표에서 마크다운 렌더링 행을 정리하고 **왜 지웠는지**를 남긴다
- `src/verify_lab/CLAUDE.md` — 상수 통합 결과가 「상수 관리 3계층」 예시와 어긋나지 않는지 확인
- `src/verify_lab/common_constants.py` — **모듈 docstring 을 갱신한다.** 현재 "경로 상수와 시세 스키마 상수"로
  범위를 한정했는데, 단위 계수·타임존이 들어오면 그 문장이 거짓이 된다

**`docs/COMMANDS.md`**: **변경 있음** — 실행 명령어와 CLI 옵션은 바뀌지 않지만,
이 계획서가 테스트를 지우므로 `:31` 의 **테스트 통과 기준선을 다시 맞춰야 한다.**
`PLAN_judgment_contract_fix.md` 가 먼저 갱신하므로 **이 계획서는 그 값을 한 번 더 조정**한다.

### 데이터/결과 영향

- **없다.** 이 계획서의 모든 변경은 동작 불변이며, 마지막 Phase에서 산출물 md5 대조로 확인한다
- `HolidayExit` 제거는 `weekly_exit_schedule` 의 시그니처를 바꾸지만 **본검증이 쓰던 `PREVIOUS` 경로만 남으므로 결과가 같다**
- 상수 통합은 **값이 같은 것끼리만** 합친다. 값이 다르면 통합 대상이 아니다

## 6) 단계별 계획(Phases)

### Phase 1 — 데드코드·잔여물 제거(그린 유지)

**작업 내용**:

- [ ] `measure/screening.py` — `SUPPORT_TOTAL_WITHOUT_PERIOD` 삭제
- [ ] `utils/formatting.py` — `Align.CENTER` 와 `_format_cell` 의 CENTER 분기 삭제
- [ ] `studies/option_expiry/weekly_exit.py` — `valid_count`·`excluded_count` 프로퍼티 삭제 (`entry_count` 는 유지)
- [ ] `studies/option_expiry/offsets.py` — `unassigned_count` 프로퍼티 삭제
- [ ] `studies/usdkrw_equivalence/regression.py` — `spread_excluding_edges` 필드·`MIN_YEARS_FOR_EDGE_SPREAD`·
      `alpha_daily` 필드 삭제 (`alpha_daily` 지역변수는 `alpha_annual` 계산에 필요하므로 유지)
- [ ] `utils/logger.py` — `setup_logger` 의 `level` 파라미터와 `getattr` 폴백 삭제, DEBUG 고정
- [ ] `utils/cli_helpers.py` — 모듈에 `logger` 가 없을 때의 폴백 삭제 (모든 CLI가 모듈 레벨 `logger` 를 정의함)
- [ ] `report/constants.py` — `HORIZON_LABELS` 에서 `63`·`126`·`252` 삭제
- [ ] `report/tables.py`·`report/__init__.py` — `to_markdown`·`build_comparison_table` 삭제
- [ ] `studies/option_expiry/weekly_exit.py` — `HolidayExit` enum 과 `on_holiday` 인자·필드 삭제,
      `PREVIOUS` 분기만 남긴다. **docstring 에 결정 ⑱(직전 거래일)만 남기고 ㉔ 대조 서술은 걷어낸다**
- [ ] 삭제한 대상을 참조하던 테스트 정리

---

### Phase 2 — 상수 통합과 리터럴 제거(그린 유지)

**작업 내용**:

- [ ] `common_constants.py` 에 **비율→백분율 계수**를 두고 `measure/statistics.py`·`report/constants.py`·
      `studies/usdkrw_equivalence/constants.py` 가 그것을 쓰게 한다. 각 계층의 중복 정의는 삭제
- [ ] `common_constants.py` 에 **원화 가격 자릿수**를 두고 `option_expiry`·`index_extreme` 의 중복 정의 삭제
- [ ] `common_constants.py` 에 **KST 타임존**을 두고 `report/writer.py`·`utils/meta_manager.py` 가 그것을 쓰게 한다
- [ ] `studies/usdkrw_equivalence/runner.py` — `"Nav"` 리터럴을 `COL_NAV` 로 교체
- [ ] `studies/usdkrw_equivalence/runner.py` — `(ETF_BASE, ETF_LEVERAGE)` 4곳을 `ETF_TARGETS` 로 교체
- [ ] `studies/usdkrw_equivalence/effective_cost.py` — `"raw"`·`"adjusted"`·`"nav"` 를 모듈 상수로 승격
- [ ] `studies/option_expiry/runner.py` — `"advanced_days"` 를 `COL_ADVANCED_DAYS` 로 교체
- [ ] `studies/option_expiry/constants.py` — `summary.json` 키를 `KEY_*` 상수로 정의하고
      `runner.py`·`scripts/studies/run_option_expiry.py` 가 그것을 쓰게 한다 (`index_extreme` 관용에 맞춤)
- [ ] 상수 이동 후에도 **값이 같은지** 테스트로 고정

---

### Phase 3 — 타입 정리와 주석 정리(그린 유지)

**작업 내용**:

- [ ] `scripts/studies/run_option_expiry.py` — `_selected_datasets` 반환 타입을 `tuple[Dataset, ...]` 로 좁히고
      `Dataset` 을 import. `:181`·`:202` 의 `pyright: ignore` **2개 제거**
- [ ] `report/tables.py` — `_horizon_label` 이 정수를 받도록 좁히고 호출부에서 변환.
      `:450` 의 `pyright: ignore` **1개 제거**
- [ ] `utils/formatting.py`·`cli_helpers.py`·`meta_manager.py`·`logger.py` —
      **"학습 포인트" 블록과 파이썬 문법 설명 주석을 걷어낸다.** 로직은 한 줄도 바꾸지 않는다
- [ ] 같은 4개 파일에서 **설계 근거 주석은 전부 보존**한다 —
      `print_row` 의 공백 2칸 보정 이유, `_find_project_root` 의 10단계 제한,
      `MAX_HISTORY_COUNT` 의 존재 이유, `propagate = False` 의 이유 등
- [ ] Docstring 은 Google 스타일과 한글 유지 (`.claude/rules/python.md`)

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [ ] `docs/ROADMAP.md` 출력 계약 표에서 마크다운 렌더링 행을 정리하고 **왜 지웠는지**(호출 0건)를 남긴다
- [ ] `src/verify_lab/CLAUDE.md` 의 「상수 관리 3계층」 서술이 통합 결과와 맞는지 확인
- [ ] `common_constants.py` 모듈 docstring 을 통합된 상수 범위에 맞게 갱신
- [ ] `docs/COMMANDS.md:31` 테스트 통과 기준선을 **이 계획서 완료 시점의 실제 값**으로 조정하고 갱신 시점 병기
- [ ] 자동 포맷 적용 (`poetry run black .`)
- [ ] **검증 #1·#5·#7 과 역방향 매매를 재실행해 산출물 md5 가 직전 실행과 동일함을 확인**
- [ ] 변경 기능 및 전체 플로우 최종 검증
- [ ] DoD 체크리스트 최종 업데이트 및 체크 완료
- [ ] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [ ] `poetry run python validate_project.py` (passed=\_\_, failed=\_\_, skipped=\_\_)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 측정 / 호출되지 않는 정의 제거와 계층 간 중복 상수 통합 — 동작 불변
2. 측정 / 데드코드 정리 · 상수 3계층 정합 복구 · type ignore 근본 제거
3. 하네스 / 미사용 정의 삭제와 유틸 계층 주석을 저장소 관용에 맞춤
4. 측정 / 지워진 대조축의 잔여물 제거와 리터럴의 상수 치환
5. 측정 / 경량화 — 데드코드·중복 상수·느슨한 타입 정리

## 7) 리스크(Risks)

| 리스크 | 완화책 |
| --- | --- |
| 삭제한 정의를 **다른 검증이 곧 쓸 예정**이었다 | 전수 집계로 호출 0건을 확인했고, 필요해지면 git 이력에서 꺼낸다. 저장소가 이미 그리드 6,042줄에 같은 방식을 썼다 |
| 상수를 옮기면서 **값이 달라진다** | 값이 같은 것끼리만 합친다. Phase 2 에서 값 동일성을 테스트로 고정하고, 마지막 Phase 에서 산출물 md5 로 확인 |
| `HolidayExit` 제거가 결과를 바꾼다 | 프로덕션이 `PREVIOUS` 만 썼으므로 남는 경로가 같다. 재실행 md5 대조로 확인 |
| 주석 정리 중 **설계 근거를 실수로 지운다** | 로직 옆의 "왜"를 담은 주석은 보존 대상으로 Phase 3 체크리스트에 명시했다. diff 를 줄 단위로 확인한다 |
| `PLAN_judgment_contract_fix.md` 보다 먼저 실행해 같은 곳을 두 번 손댄다 | 「실행 순서」 절에 선후를 못박았다 |

## 8) 메모(Notes)

### 데드코드 판정 방법 (2026-08-30)

`ast` 로 `src/` 의 함수·클래스·모듈 최상위 상수 **689개**를 뽑고, `src`·`scripts`·`tests`·
`validate_project.py` 전체에서 각 이름의 등장 횟수를 셌다. 정의부와 `__init__` 재export 를 뺀
실호출이 0건인 것만 목록에 올렸다.

**호출이 있어 목록에서 제외한 것들** — 다음에 같은 조사를 반복하지 않도록 남긴다.

| 대상 | 실제 호출처 |
| --- | --- |
| `_sorted_cells` | `_sorted_single_basis_cells` 가 씀 |
| `TableLogger.print_header`·`print_row`·`print_footer` | `scripts/data/` 의 실측 스크립트 5개가 직접 씀 |
| `DEFAULT_RANK_CUT` | `find_extreme_move_events` 의 기본 인자 |
| `WeeklyExitSchedule.entry_count` | `weekly_exit_returns:270` |
| `RegressionResult.alpha_daily` (지역변수) | `alpha_annual` 계산에 필요 |

### `HolidayExit` 가 잔여물인 근거

`docs/spec/option_expiry.md` 결정 ㉘(2026-08-30 확정)이 **「휴장 규칙 네 조합」을 지운 대조축으로
명시**했고, 수치는 결과 문서 1장 「지운 대조축」 표에 남겼다. 재현은 git 이력에 맡긴다는 것도
같은 결정에 적혀 있다. 이 계획서는 그때 남은 enum 을 마저 걷어낼 뿐이며 **새 결정을 만들지 않는다.**

### 삭제 대상이 참조된 테스트 건수 (2026-08-30 실측)

정리해야 할 테스트의 규모를 미리 잡아 둔다. **건수는 참조 횟수이지 테스트 함수 수가 아니다.**

| 대상 | 테스트 참조 |
| --- | --- |
| `setup_logger` (파라미터만 제거, 함수는 유지) | 11건 |
| `to_markdown` | 4건 |
| `build_comparison_table` | 3건 |
| `HolidayExit` · `unassigned_count` · `spread_excluding_edges` · `alpha_daily` | 각 2건 |
| `valid_count` | 1건 |
| `Align.CENTER` · `SUPPORT_TOTAL_WITHOUT_PERIOD` | **0건** |

### `DISPLAY_PRICE_BASIS` 는 삭제 대상이 아니다 (2026-08-30 정정)

초안에서 삭제 목록에 넣었으나 **틀렸다.** 「검증 대상 시세」 표가 `"가격기준"` 을 하드코딩하고
있어 미사용으로 보였을 뿐이고, `docs/ROADMAP.md` 실행 계층 계약이 **가격 기준을 그 표에 두라고
명시**한다. `PLAN_judgment_contract_fix.md` 가 표를 고치면서 이 상수를 실제로 쓰게 했다.

> **미사용이라는 사실만으로 지우면 안 된다.** 「왜 안 쓰이는가」를 먼저 봐야 한다 —
> 필요 없어서 안 쓰이는 것과, 연결을 빠뜨려 안 쓰이는 것은 처리가 정반대다.

> 현재 수집되는 테스트는 **582개**다. `docs/COMMANDS.md` 의 기준선(`1034`)은
> 그리드 삭제가 반영되지 않아 낡았으며, `PLAN_judgment_contract_fix.md` 가 먼저 바로잡는다.

### 진행 로그 (KST)

- 2026-08-30 12:11: 계획서 작성. 전수 분석 13개 항목 중 동작 불변 정리에 해당하는 것을 모았다
- 2026-08-30 12:2x: 자체 검증에서 세 가지를 보강했다 — ① Non-Goals 가 "계약을 안 바꾼다"고 하면서
  ROADMAP 출력 계약을 고치는 모순을 예외 명시로 해소 ② `docs/COMMANDS.md` 를 변경 대상에 포함
  ③ `common_constants.py` docstring 갱신을 누락했던 것을 추가

---
