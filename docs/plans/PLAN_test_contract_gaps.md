# Implementation Plan: 계약 테스트의 빈틈 다섯 곳 — 늘 참인 검사 · 새는 정규식 · 밟지 않는 경로 · 손으로 적은 매매법 목록

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

**작성일**: 2026-09-28 20:43
**마지막 업데이트**: 2026-09-28 22:12
**관련 범위**: tests (프로덕션 코드 변경 없음)
**관련 문서**: tests/CLAUDE.md, src/verify_lab/CLAUDE.md

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

- [x] 목표 1 (T2): `TestSingleOwner` 가 **늘 참**이 아니게 한다 — 게이트의 기준값과 판정 값을 `measure/screening.py` 밖에서 쓰면 실패한다
- [x] 목표 2 (R4-4): `_FILENAME_SHAPE` 가 **경로가 섞인 파일 이름 리터럴**(`"/성적표.csv"`)을 놓치지 않는다
- [x] 목표 3 (T4): 「순위 컷을 넓히면 신호가 늘어난다」가 **등호가 아니라 부등호로** 통과한다
- [x] 목표 4 (R5-19): 중간선거 runner 의 어긋남 열이 **「예」 경로를 실제로 밟는다**
- [x] 목표 5 (T3): `tests/test_output_contract.py` 에서 「매매법 전부」를 말하는 검사가 **레지스트리에 묶인 한 표**를 따라간다 — 새 매매법을 등록하면 그 검사들이 자동으로 그것까지 돈다

## 2) 비목표(Non-Goals)

- **프로덕션 코드(`src/`·`scripts/`)는 고치지 않는다.** 산출물(`storage/results/`)도 바뀌지 않는다 — 테스트만 바꾼다
- **T2 에 「`screen_verdict` 호출처가 `periods.py` 하나」 검사를 넣지 않는다.** 계약 문서(`src/verify_lab/CLAUDE.md` 「게이트의 진입점」)에는 적혀 있지만 백로그 지적은 「게이트를 다시 써도 통과한다」이고, 그것은 기준값·판정 값의 소유로 닫힌다
- **T2 에서 값 `"제외"` 는 검사하지 않는다** — `report/constants.py:28`(제외 건수 컬럼)과 `studies/usdkrw_equivalence/constants.py:305`(이상치 라벨)가 **동음이의어**로 같은 문자열을 갖는다(`tests/test_layer_contracts.py` 의 `_REPORT_LABEL_COLLISIONS` 가 이미 알려진 겹침으로 둔다)
- **T4 에서 기본 합성 시세(`_market()` 의 기본값)를 바꾸지 않는다** — 같은 파일의 다른 테스트가 그 신호 배치(`SIGNAL_PLACEMENTS` 셋 · 축적 구간 등락)에 기대고 있다
- **T3 에서 매매법 고유 검사는 그대로 둔다** — `TestReverseDirection` · `TestSingleColumnStopFilter` · `TestWorstHoldColumn.test_지수_행도_값을_갖는다` 등은 한 매매법의 성질을 보는 것이 맞다
- 백로그의 나머지(D · E · F 묶음, RV6-5)는 이 계획서의 범위가 아니다. **T5 · ③ Non-Goals 셋 · RV7-1 · R7 은 버리기로 했다**(사용자 결정 2026-09-28)

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

다섯 곳 모두 **테스트가 통과하지만 지키려던 계약을 실제로는 검사하지 않는** 자리다. 결함이 들어와도 초록으로 남는다.

| ID | 자리 | 지금 | 실측 (2026-09-28, HEAD `89423bc` + 미커밋 주석 정리) |
| --- | --- | --- | --- |
| T2 | `tests/test_measure_screening.py:270` | `"MIN_HIT_RATE" not in source` — 그 이름은 저장소 어디에도 없어 **늘 참**이다 | `src` 전체를 AST 로 훑으면 `MIN_EXPECTED_VALUE` · `SCREEN_CANDIDATE` · `SCREEN_EXCLUDED` 이름과 값 `"후보"` 는 **`measure/screening.py` 밖에서 0건**. 값 `"제외"` 는 위 비목표의 두 파일에서 걸린다 |
| R4-4 | `tests/test_layer_contracts.py:124` | `[^\s/\\]*\.csv` 를 `fullmatch` — **`/` 나 `\` 가 든 리터럴은 통째로 빠진다** | 후보 `\S*\.csv` 를 `scripts/run_*.py` 여섯 개의 리터럴(docstring 제외)에 돌려 **0건**(지금 정규식도 0건). 새던 모양 `"/성적표.csv"` · `"out/거래내역.csv"` 는 잡히고 산문 `"execution.csv 가 아래"` 는 여전히 빠진다 |
| T4 | `tests/test_studies_reverse_trading.py:270` | 합성 시세에서 컷 5 · 컷 20 이 **둘 다 3건**이라 `wide >= narrow` 가 등호로만 통과한다 | 집계 구간 뒤쪽에 **+6.0% 부터 0.1%p 씩 줄어드는 등락 8개**(20 거래일 간격)를 더 심으면 **컷 5 = 7건 · 컷 20 = 11건** |
| R5-19 | `tests/test_studies_midterm_cycle_runner.py:259` | `⊆ {예, 아니오}` 만 본다 | 그 픽스처의 측정 표 2행이 **전부 「아니오」** — runner 의 `yes_no(mean_rate_conflict(merged))`(`runner.py:320`)에서 **「예」 쪽 변환을 한 번도 밟지 않는다** |
| T3 | `tests/test_output_contract.py` | `TestCoverage` 는 `OUTPUT_FIXTURES` 만 레지스트리와 대조한다 | 「매매법 전부」 검사 중 **두 픽스처를 손으로 적은 것이 13개 + 픽스처 1개**(`TestRunSummary.summaries` 아래 6개). 레지스트리를 따라가는 것은 `test_보유_중_최악이_결과_최악보다_나쁘거나_같다` 하나뿐이다 |

**T3 의 13개** — `TestSummaryColumns` 3 · `TestTradeColumns` 2 · `TestReversePeriods` 2(`제외_컬럼` · `제외_건수`) ·
`TestBreakevenMargin` 1 · `TestWorstHoldColumn` 2(`값을_채운다` 두 벌) · `TestScreenColumn` 3(`판정_값_셋` · `전체가_아닌_행` · `전체_행에서는`).

#### 글자 규칙이 막는 자리 — 걸린 것과 탈출구 (`/impl-plan` 의 같은 이름 절)

T2 와 R4-4 는 소스를 글자·AST 로 판정해 **테스트를 실패시킨다(막는다).** 되돌릴 수 없는 결과는 없다.

| 규칙 | 실제 소스에서 걸린 것 | 오탐 | 탈출구 |
| --- | --- | --- | --- |
| T2 이름 셋 + 값 `"후보"` | 소유자(`measure/screening.py`) 하나 | 0 | 허용 경로를 **이름 붙은 상수 하나**(`_GATE_OWNERS`)로 두고 실패 메시지가 그 상수를 가리킨다 — 정당한 새 사용처가 생기면 이유를 주석으로 달아 거기 더한다 |
| T2 값 `"제외"` | 소유자 + 동음이의어 둘 | 2 | **규칙에 넣지 않는다**(비목표) |
| R4-4 `\S*\.csv` | 0 | 0 | 없음 — 실행 스크립트에 경로 리터럴을 적는 것 자체가 `scripts/CLAUDE.md` 「저장 경로는 `common_constants.py` 상수를 쓴다」 위반이라 걸리면 그것이 결함이다 |

### 결정과 탈락안

| # | 결정 | 탈락안 | 근거 |
| --- | --- | --- | --- |
| ① | T2 는 **AST 의 이름·상수 노드**로 본다 | 소스 문자열에 `"MIN_EXPECTED_VALUE" in source` | 문서 규칙이 「게이트 값은 적지 않고 **상수 이름을 가리킨다**」(`.claude/rules/docs.md`)라 주석이 그 이름을 적는 것은 정당하다. 문자열 검사는 그 주석에서 오탐한다. 주석은 AST 에 없다 |
| ② | T2 는 **`src` 전체**를 본다 | `periods.py` 한 파일만 | 게이트를 다시 쓸 수 있는 자리가 `periods.py` 만이 아니다 — 매매법 `trading.py` 가 직접 비교해도 같은 사고다 |
| ③ | T2 의 새 검사는 **`test_measure_screening.py` 의 `TestSingleOwner` 안**에 둔다 | `test_layer_contracts.py` 로 옮겨 그쪽 헬퍼를 쓴다 | 백로그가 지목한 자리이고 수술적 변경이다. 필요한 AST 순회는 이름·상수 두 종류뿐이라 헬퍼를 빌리지 않아도 짧다 — docstring 은 값이 통째로 `"후보"` 일 수 없어 제외 처리가 필요 없다 |
| ④ | R4-4 는 **`\S*\.csv`** | `.csv` 부분 문자열 전부 금지 | 기존 docstring 이 이미 탈락시킨 안이다 — 산문까지 걸려 「도움말이 산출물을 언급하는 것은 정의가 아니다」 예외를 무력화한다 |
| ⑤ | T4 는 `_market` · `_target` 에 **선택 인자**로 등락을 더 심고 그 테스트만 쓴다 | 기본 시세를 바꾼다 | 비목표 참조. 기본값이 그대로면 다른 테스트의 신호 수가 한 건도 안 흔들린다 |
| ⑥ | R5-19 는 runner 모듈이 가져온 **`mean_rate_conflict` 를 `monkeypatch` 로 전부 참을 내게** 바꿔 끼우고 열이 전부 「예」인지 본다 | 어긋나는 칸이 생기도록 합성 시세를 손으로 짠다 | 보려는 것은 **runner 의 배선**(판정 → `yes_no` → 열)이지 판정식이 아니다 — 판정식은 `tests/test_measure_statistics.py` 가 이미 본다. 시세를 짜면 9개월 보유 수익률 셋을 날짜에 맞춰 설계해야 해 픽스처가 판정식의 세부에 묶인다. 모듈 함수 바꿔 끼우기는 저장소에 선례가 있다(`tests/test_etn_collector.py` · `tests/test_krx_futures_collector.py`) |
| ⑦ | T3 는 `OUTPUT_FIXTURES`(slug → 픽스처 이름)를 **매매법 사양 표 하나**(slug → 픽스처 이름 · 성적표 축 · 성적표 꼬리 · 거래내역 축 · 거래내역 꼬리 · 대상 키)로 넓히고, `TestCoverage` 가 **그 표**를 레지스트리와 대조한다 | 사양 표를 `OUTPUT_FIXTURES` 옆에 따로 둔다 | 두 표면 둘 다 레지스트리와 대조해야 하고, 한쪽만 늘면 또 조용히 샌다. 한 표면 대조 하나로 닫힌다 |
| ⑧ | T3 의 13개는 **사양 표로 매개변수화**한다(`request.getfixturevalue`) | 파일 안 테스트 함수를 훑어 「두 픽스처를 손으로 받는 함수」를 금지하는 메타 검사 | 이 파일에 이미 같은 관용이 있다(`test_보유_중_최악이_결과_최악보다_나쁘거나_같다`). 메타 검사는 무엇이 「매매법 전부」 검사인지를 이름으로 판정해야 해 글자 규칙이 하나 더 생긴다 |

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- `.claude/plan-config.json` — 이 저장소의 검증 명령·자동 포맷·근거 승격 목적지 (**값의 SoT**)
- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절 (값이 아니라 **판단 근거**)
- `tests/CLAUDE.md`
- `src/verify_lab/CLAUDE.md` — 「매매 산출물 계약」 · 「검증 계층도 `row_counts` 의 키가 파일 이름입니다」
- `scripts/CLAUDE.md` — 「제약사항」
- `.claude/rules/docs.md` — 「문서는 게이트 «값»을 적지 않고 «상수 이름»을 가리킵니다」
- 전역 `~/.claude/rules/python.md`

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 다섯 항목 모두 **변형 검증을 통과** — 일부러 결함을 넣으면 새 검사가 실패하고, 되돌리면 통과한다 (각 Phase Validation 에 기록)
- [x] 프로덕션 코드 diff 0 — `git diff --stat -- src scripts storage` 가 이 계획서 착수 시점과 같다
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — `docs/COMMANDS.md` 변경 없음 · CLAUDE.md 변경 없음(아래 Scope)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 ①~⑧ 의 「왜」는 **바뀐 테스트의 docstring·주석**이 갖는다 — 테스트가 계약의 「실행 가능한 문서」다(`tests/CLAUDE.md` 8절). 실측 건수는 착수 시점 값이라 옮기지 않는다)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `tests/test_measure_screening.py` — T2
- `tests/test_layer_contracts.py` — R4-4 (`_FILENAME_SHAPE` 와 그 위 주석, `test_CLI_가_파일_이름을_직접_적지_않는다` docstring 의 「파일 이름 하나로만」 서술)
- `tests/test_studies_reverse_trading.py` — T4
- `tests/test_studies_midterm_cycle_runner.py` — R5-19 (픽스처 본문을 입력 쓰기 헬퍼로 빼고 새 테스트가 함께 쓴다)
- `tests/test_output_contract.py` — T3
- `docs/COMMANDS.md`: 변경 없음 — 실행 명령어·CLI 옵션이 바뀌지 않는다
- CLAUDE.md: 변경 없음 — `src/verify_lab/CLAUDE.md` 의 「`tests/test_output_contract.py` 가 매매법 전부에서 이것을 한꺼번에 검사합니다」가 이 변경으로 **사실이 된다**. 문구는 그대로 맞다

### 데이터/결과 영향

- 산출물 영향 없음 — 테스트만 바뀐다
- 테스트 개수는 바뀐다. T3 에서 한 함수 안에서 두 매매법을 돌던 검사가 매개변수화로 두 건이 되고, 매매법마다 두 벌이던 함수는 한 함수 두 건이 된다. **착수 전·후의 `--collect-only` 목록을 진행 로그에 남겨** 빠진 검사가 없는지 대조한다

## 6) 단계별 계획(Phases)

> **착수 전 조건**: 앞선 문서·주석 정리(백로그 A · B 묶음)가 **미커밋으로 워킹트리에 있다.**
> 마지막 Phase 의 `/code-review` 는 범위 없이 미커밋 diff 전체를 보므로, **그 정리를 먼저 커밋한 뒤** 착수한다.

### Phase 1 — 소스를 판정하는 검사 둘 (T2 · R4-4)

**작업 내용**:

- [x] T2: `TestSingleOwner` 의 `MIN_HIT_RATE` 줄을 걷고, `src` 전체를 AST 로 훑어 **이름 `MIN_EXPECTED_VALUE` · `SCREEN_CANDIDATE` · `SCREEN_EXCLUDED` 와 값 `"후보"` 가 `_GATE_OWNERS`(`verify_lab/measure/screening.py`) 밖에 없음**을 검사한다. `"screen_verdict(" in source` 검사는 그대로 둔다
- [x] T2: 걷어낸 `MIN_HIT_RATE` 줄이 **늘 참이었다는 사실**과 결정 ①·② 의 「왜」를 새 테스트 docstring 에 적는다 — 「제외」를 빼는 이유(동음이의어)도 함께
- [x] R4-4: `_FILENAME_SHAPE` 를 `\S*\.csv` 로 바꾸고 바로 위 주석과 `test_CLI_가_파일_이름을_직접_적지_않는다` docstring 의 「파일 이름 하나로만 이루어진 문자열」을 **「공백 없는 한 덩어리(경로가 섞여도)」**로 고친다 — 경로를 빼면 `"/성적표.csv"` 로 새는 이유를 한 줄로 남긴다

**Validation**:

- [x] 변형 T2: `execution/periods.py` 에 `MIN_EXPECTED_VALUE` 를 가져와 쓰는 줄을 임시로 넣으면 새 검사가 **실패**하고, 되돌리면 통과한다
- [x] 변형 T2(값): `execution/periods.py` 에 `"후보"` 리터럴을 임시로 넣으면 **실패**, 되돌리면 통과
- [x] 변형 R4-4: `scripts/run_reverse.py` 에 `"/성적표.csv"` 리터럴을 임시로 넣으면 **실패**, 되돌리면 통과
- [x] 변형을 전부 되돌린 뒤 `git diff --stat -- src scripts` 가 착수 시점과 같다
- [x] `poetry run pytest tests/test_measure_screening.py tests/test_layer_contracts.py -q` 통과 (특정 파일만 돌리는 직접 pytest — 전역 `python.md` 가 허용하는 예외)

---

### Phase 2 — 합성 데이터가 계약의 한쪽 경로를 밟게 한다 (T4 · R5-19)

**작업 내용**:

- [x] T4: `_market` · `_target` 에 **기본값이 빈 선택 인자**(더 심을 등락의 자리와 크기)를 둔다. 기본값이면 지금과 바이트 단위로 같은 시세가 나온다
- [x] T4: 더 심을 등락을 모듈 상수로 둔다 — 집계 구간 뒤쪽, **+6.0% 부터 0.1%p 씩 줄어드는 8개를 20 거래일 간격**. 크기가 **축적 구간 등락(5%)보다 크고 집계 신호(9%)보다 작아야** 순위가 2 · 3 · 4 … 로 하나씩 밀린다는 것을 상수 주석에 적는다
- [x] T4: `test_순위_컷을_넓히면_신호가_늘어난다` 가 그 등락을 쓰고 **`wide_count > narrow_count`** 로 검사한다 — 목적 docstring 에 「같은 수면 컷을 무시해도 통과한다」를 남긴다
- [x] R5-19: `outputs` 픽스처 본문(입력 파일 쓰기와 `Dataset` 둘)을 헬퍼로 빼고 픽스처는 그것을 부른다 — 픽스처 결과는 바뀌지 않는다
- [x] R5-19: 새 테스트 — `verify_lab.studies.midterm_cycle.runner.mean_rate_conflict` 를 **전부 참**을 내는 함수로 바꿔 끼우고 `run_study` 를 돌려 어긋남 열이 **전부 「예」(`JUDGEABLE_YES`)** 인지 본다. 결정 ⑥ 의 「왜」를 docstring 에 적는다

**Validation**:

- [x] 변형 T4: `studies/reverse/trading.py:290` 의 `rank_cut=target.rank_cut` 을 임시로 고정값으로 바꾸면 새 검사가 **실패**, 되돌리면 통과
- [x] 변형 R5-19: `studies/midterm_cycle/runner.py:320` 에서 `yes_no(...)` 를 임시로 걷어 불린을 그대로 담으면 새 검사가 **실패**, 되돌리면 통과
- [x] 변형을 전부 되돌린 뒤 `git diff --stat -- src scripts` 가 착수 시점과 같다
- [x] `poetry run pytest tests/test_studies_reverse_trading.py tests/test_studies_midterm_cycle_runner.py -q` 통과

---

### Phase 3 — 「매매법 전부」 검사를 레지스트리에 묶는다 (T3)

**작업 내용**:

- [x] 착수 전 `poetry run pytest tests/test_output_contract.py --collect-only -q` 목록을 진행 로그에 남긴다
- [x] `OUTPUT_FIXTURES` 를 매매법 사양 표로 넓힌다 — slug → 픽스처 이름 · 성적표 축 · 성적표 꼬리 · 거래내역 축 · 거래내역 꼬리 · 요약의 대상 키. 축·꼬리는 지금처럼 **손으로 박은 튜플**을 가리킨다(이 파일 머리말의 규칙)
- [x] `TestCoverage` 가 그 표의 slug 집합을 레지스트리와 대조한다 (실패 메시지는 「사양 표에 올리세요」로 고친다)
- [x] 13개 검사와 `TestRunSummary.summaries` 픽스처를 사양 표로 매개변수화한다(`request.getfixturevalue`). 기존 `test_보유_중_최악이_결과_최악보다_나쁘거나_같다` 도 같은 표를 쓴다
- [x] 매개변수화로 필요 없어진 것만 정리한다 — 매매법마다 두 벌이던 함수의 짝, 쓰지 않게 된 import. **매매법 고유 검사는 건드리지 않는다**
- [x] 바뀐 검사의 docstring 에서 「두 매매법」을 **「매매법 전부」**로 고친다 — 계약이 실제로 그렇게 됐으므로

**Validation**:

- [x] 착수 후 `--collect-only` 목록을 착수 전과 대조한다 — 사라진 검사가 없고, 13개와 요약 6개가 **매매법마다 한 건씩** 모인다
- [x] `grep` 으로 이 파일에서 `reverse_outputs` 와 `midterm_cycle_outputs` 를 **함께** 인자로 받는 테스트 함수가 0개임을 확인한다
- [x] 변형 T3: 사양 표에서 `midterm_cycle` 을 임시로 빼면 `TestCoverage` 가 **실패**하고, 되돌리면 통과한다
- [x] `poetry run pytest tests/test_output_contract.py -q` 통과

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

> 🔴 **`/commit` 이 «맨 마지막»인 것은 의도다.** 그 스킬은 「후보 뒤에는 아무것도 덧붙이지 말 것」으로
> 끝나므로 **호출하는 순간 그 턴이 거기서 닫힌다.** 중간에 두면 뒤에 적힌 항목이 그 벽 너머에 남는다 —
> 실제로 두 번 그렇게 샜다(`[실측] 2026-09-14` 후보를 계획서에 안 옮김 · `2026-09-16` 옮기고 체크박스를 안 닫음).
> **체크박스와 상태를 먼저 확정하고, 커밋 후보를 마지막에 만든다.**

- [x] 필요한 문서 업데이트 — `docs/COMMANDS.md` 변경 없음 · CLAUDE.md 변경 없음 (Scope 참조)
- [x] 자동 포맷 적용 (`poetry run black .`)
- [x] 변경 기능 및 전체 플로우 최종 검증 — `git diff --stat -- src scripts storage` 가 착수 시점과 같다
- [x] Validation 절에 `/code-review` 와 품질 검증 **실행 결과**를 적는다
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

- [x] `/code-review xhigh` **1회차** (발견 14건 — 버그 8 [무거움 2 · 가벼움 6] · 그 외 6 · 조치: 무거움 2 수정)
  - 무거움(수정) — ① 걷어낸 `"MIN_HIT_RATE" not in source` 는 옛 적중률 하한이 `periods.py` 에 옛 이름으로 되살아나는 것을 막는 회귀 가드였다 → 되살리고 docstring 에 그 역할을 적었다 ② `TestCoverage` 가 slug 집합만 봐 사양의 픽스처 이름이 틀려도 그 매매법의 검사 전부가 남의 산출물로 초록 → `test_사양의_픽스처가_그_매매법을_돈다`(요약의 `track` == slug) 추가. 둘 다 변형으로 실패 확인
  - 가벼움(목록만 — 지금 코드에 발동 입력 없음. 뒤에 사용자 결정으로 고친 것은 【수정】) — 【수정】`GATE_OWNERS` 에 파일을 더하면 「네 가지 전부」 요구에 걸려 탈출구가 막힘 · 【수정】중간선거 어긋남이 늘 「예」여도 두 테스트 통과(기존 `⊆` 를 `== {아니오}` 로 좁히면 닫힘) · 게이트 스캔이 `scripts/` 를 안 봄(`run_midterm_cycle.py` 가 `SCREEN_CANDIDATE` 를 정당하게 씀) · `"screen_verdict(" in source` 가 주석에도 통과(기존 줄) · `KEY_EXCLUDED_COUNT` 를 중간선거 상수에서 빌려 전 매매법에 씀(기존) · `extra_surges` 에 범위 가드 없음(행을 줄여 부르면 `IndexError`)
  - 그 외(목록만) — 【수정】새 docstring 두 곳의 과거형(`test_studies_reverse_trading.py` 「통과했다」 · 스크리닝 쪽은 무거움 ① 수정으로 현재형이 됨) · `_gate_usage` 가 `test_layer_contracts.py` 의 헬퍼와 겹침(결정 ③) · `공통_부분이_완전히_같다` 가 매개변수화된 컬럼 검사에 함의됨 · 「매매법 전부」 docstring 이 매매법별 축을 나열 · `test_Dataset_…` 의 Then(「서로 다른 것」)과 단언(비어 있지 않음) 불일치(기존)
- [x] `/code-review xhigh` **2회차** (발견 15건 — 버그 9 [무거움 1 · 가벼움 8] · 그 외 6 · 조치: 무거움 1 수정 후 멈춤 — 3회차 여부는 사용자가 정한다)
  - 무거움(수정) — 1회차 ② 와 같은 모양이 사양 표에 새로 더한 `datasets` · `output_files` 두 칸에 있었다(복사하고 안 고치면 남의 목록을 검사하고 초록) → 두 칸을 걷고 `_method_constants(slug)` 가 `studies/<slug>/constants.py` 를 찾아 `TRACK_NAME` 으로 확인한다. 변형(늘 `reverse` 패키지를 찾게)으로 `midterm_cycle 패키지의 TRACK_NAME 이 다릅니다: reverse` 실패 확인
  - 가벼움(목록만) — 1회차 여섯에 더해 둘: 게이트 스캔이 **리터럴 기준값**(`>= 1.0`)이나 다른 이름으로 다시 쓴 게이트를 못 봄(결정 ① 의 이름 기준 한계) · 순위 컷 검사가 부등호만 봐 컷을 `<` 로 다시 판정해도 통과(`11 > 6`)
  - 그 외(목록만) — 1회차 다섯에 더해 하나: `test_row_counts_의_키가_파일_이름이다` 의 Then(성적표·거래내역)과 단언(거래내역만) 불일치(기존)
- [x] `poetry run python validate_project.py` (passed=1254, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다.**
> 계획서를 쓰는 시점에는 diff 가 없어 여기 적는 것은 전부 추측이고,
> **추측으로 적은 줄은 그대로 나간다.** 형식·문체 규칙은 `/commit` 이 정한다.

1. `테스트 / 계약 테스트 빈틈 다섯 곳 보강`
2. `테스트 / 게이트 소유 AST 검사·경로 섞인 파일 이름 검사·순위 컷 부등호·어긋남 「예」 경로·매매법 사양 표 매개변수화`
3. `테스트 / 산출물 계약 검사의 레지스트리 연동 매매법 사양 표 전환과 늘 참이던 게이트 소유 검사 교체`
4. `테스트 / 결함이 들어와도 초록이던 계약 테스트 다섯 곳을 변형 검증으로 확인한 검사로 교체`
5. `테스트 / 새 매매법 등록 시 산출물 계약 검사 자동 적용과 게이트 이중화·파일 이름 조립 감지 강화`

## 7) 리스크(Risks)

- **T3 매개변수화 중 검사가 조용히 빠진다** — 한 함수 안에서 두 매매법을 돌던 검사를 쪼개며 한쪽 assert 를 잃을 수 있다. 완화: 착수 전·후 `--collect-only` 대조와 「두 픽스처를 함께 받는 함수 0개」 확인(Phase 3 Validation)
- **T3 의 사양 표가 매매법 고유 값을 끌어온다** — 대상 키(`KEY_TARGETS`)는 두 매매법 모두 `"targets"` 이지만 각자의 모듈에서 가져오는 지금 방식을 유지한다. 한 값으로 합치면 한쪽이 바뀔 때 테스트가 다른 쪽 값을 검사한다
- **T2 가 정당한 새 사용처를 막는다** — 예: 나중에 요약이 게이트 값을 기록해야 할 때. 완화: 허용 경로가 이름 붙은 상수 하나라 이유를 달아 더하면 된다(Context 「탈출구」). 막는 것은 테스트 실패뿐이라 되돌릴 수 없는 결과는 없다
- **R5-19 가 runner 의 import 모양에 묶인다** — runner 가 `statistics.mean_rate_conflict(...)` 처럼 모듈 경유로 부르게 바뀌면 바꿔 끼우기가 안 걸린다. 그때는 열이 「예」가 안 되어 **시끄럽게 실패**하므로 조용히 새지 않는다
- **T4 의 등락 크기가 순위 산식에 묶인다** — 「앞선 날 중 더 극단인 날 수 + 1」(`extreme_move.expanding_rank`)이 바뀌면 7 · 11 이 달라진다. 테스트는 개수를 박지 않고 **부등호만** 보므로, 산식이 바뀌어도 컷이 신호에 영향을 주는 한 통과한다
- **워킹트리에 앞선 정리가 미커밋으로 남아 있으면** 코드 리뷰가 그 diff 까지 본다 — 착수 전 조건(Phase 절 머리)으로 막는다

## 8) 메모(Notes)

- 출처: 경량화 시리즈 백로그(`docs/plans/BACKLOG_slim.md`, HEAD `89423bc`)의 C 묶음. 백로그는 이 계획서로 C 항목을 옮긴 뒤 지운다(사용자 결정 2026-09-28) — 원문은 `git show 89423bc:docs/plans/BACKLOG_slim.md`
- 실측 스크립트는 세션 스크래치에 두었다(저장소 밖) — 결과 수치만 위 Context 에 옮겼다
- T3 의 대상 키: `studies/reverse/trading.py:86` · `studies/midterm_cycle/trading.py:180` 둘 다 `KEY_TARGETS = "targets"`

### 진행 로그 (KST)

- 2026-09-28 20:43: 계획서 작성. 다섯 항목의 자리와 실측(위 Context 표)을 확인했다 — 착수 전 품질 검증 기준 상태 passed=1242, failed=0, skipped=0
- 2026-09-28 21:06: 승인(사용자 「추천안으로 진행」). 착수 전 조건 충족 — 앞선 정리가 `79b7115` 로 커밋돼 워킹트리가 깨끗하다
- 2026-09-28 21:28: Phase 1 완료(Phase 1 ~ 3 의 완료 시각은 재지 않았다 — 셋 다 이 시각에 잰 값으로 적는다). 허용 경로 상수는 이 파일의 클래스 상수 관용(`TestScreenColumn.VERDICTS`)에 맞춰 `GATE_OWNERS` 로 두었다(계획서 표기 `_GATE_OWNERS`). 변형 셋 모두 실패 확인 — T2 이름 `{'verify_lab/execution/periods.py': ['MIN_EXPECTED_VALUE']}` · T2 값 `['후보']` · R4-4 `['/성적표.csv']`. 되돌린 뒤 두 파일 60 passed, `src`·`scripts` diff 0
- 2026-09-28 21:28: Phase 2 완료. 변형 둘 모두 실패 확인 — T4(컷을 10 으로 고정) `컷 5 = 11건 · 컷 20 = 11건` · R5-19(`yes_no` 제거) `{True} == {'예'}` 불일치. 되돌린 뒤 두 파일 39 passed, `src` diff 0
- 2026-09-28 21:28: Phase 3 착수 전 수집 56건
- 2026-09-28 21:28: Phase 3 완료. **계획과 달라진 것 둘** —
  ① **Context 의 「13개」 집계가 둘을 놓쳤다.** 픽스처 인자로만 셌는데 `TestDatasetFields.test_Dataset_이_코드와_이름을_따로_갖는다` · `TestNoCandidatesFile.test_매매법_산출물에_판정표가_없다` 는 픽스처 대신 **각 매매법의 상수를 import 해** 「두 매매법」을 손으로 적고 있었다. 목표 5(「매매법 전부」 검사가 레지스트리에 묶인 표를 따라간다)의 범위라 함께 옮기고, 사양 표에 `datasets` · `output_files` 두 칸을 더했다 — 목표가 아니라 집계를 바로잡은 것이다.
  ② `TestRunSummary.summaries` 는 매개변수화하지 않고 **사양 표를 돌며 사전을 모으게** 바꿨다 — 받는 테스트 6개가 이미 `summaries.items()` 를 돌므로 몸통을 건드리지 않고 범위만 레지스트리에 묶인다. 이름에 「두」가 든 둘(`두_요약이` · `두_매매법_모두에`)은 이름에서 뺐다.
  수집 56 → 64 — 사라진 19건은 전부 이름이 바뀌거나 매개변수화된 짝이 있고, 새 27건은 `[reverse]` · `[midterm_cycle]` 한 쌍씩이다. 두 픽스처를 함께 받는 함수 0개. 변형(사양 표에서 `midterm_cycle` 제거) → `TestCoverage` 실패 `레지스트리 ['midterm_cycle', 'reverse'] · 사양 ['reverse']`. 되돌린 뒤 64 passed
- 2026-09-28 21:39: 마지막 Phase — `black` 적용(이번에 바꾼 테스트 두 파일만 다시 맞춰짐) · 코드 리뷰 1·2회차(Validation 참조). 2회차에 무거운 버그가 나와 고친 뒤 **3회차 여부를 사용자에게 묻고 멈춘다.** 그 시점의 `poetry run python validate_project.py` → passed=1254, failed=0, skipped=0 (착수 전 1242 — 매개변수화와 새 검사로 늘었다). 3회차를 돌지 않기로 하면 이 값을 Validation 에 옮긴다. 프로덕션(`src`·`scripts`·`storage`) diff 0
- 2026-09-28 22:10: 사용자 결정(「추천안으로 진행」) — 3회차는 돌지 않는다. 목록 중 셋만 고쳤다(Validation 의 【수정】): ⓐ 중간선거 어긋남 기존 테스트를 `== {아니오}` 로 좁힘 — 변형(늘 「예」)에서 `{'예'} == {'아니오'}` 실패 확인 · ⓑ 「네 가지 전부」 요구를 정의 파일(`GATE_DEFINER`)에만 건다 — `periods.py` 가 `SCREEN_CANDIDATE` 하나만 쓰고 허용 경로에 더한 변형에서 통과(탈출구가 열림) 확인 · ⓒ `test_studies_reverse_trading.py` docstring 의 과거형을 현재형으로. 나머지 가벼움·그 외는 고치지 않는다(사용자 결정). 최종 품질 검증 passed=1254, failed=0, skipped=0 · 프로덕션 diff 0
