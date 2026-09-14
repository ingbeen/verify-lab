# Implementation Plan: E — 소유권과 계층 경계를 바로잡는다

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

**작성일**: 2026-09-14 12:05
**마지막 업데이트**: 2026-09-14 12:05
**관련 범위**: strategy, studies, report, scripts, 설정(pyrightconfig)
**관련 문서**: `src/verify_lab/CLAUDE.md`, `scripts/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/strategy.md`

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

- [ ] 목표 1: **매매법-중립이어야 할 모듈이 특정 매매법의 값을 알고 있는 상태**를 푼다
- [ ] 목표 2: **같은 원칙을 두 검증이 서로 다르게 구현한 것**을 하나로 만든다 (원칙 17 의 「빈 구간 행 유지」)
- [ ] 목표 3: **CLI 가 조립하는 `summary.json`** 을 runner 로 내린다 (남은 두 검증)
- [ ] 목표 4: **`dataset_record` 소유자를 중립 자리로** 옮겨 검증·매매가 같은 함수를 쓰게 한다
- [ ] 목표 5: 설정의 사각지대를 없앤다 — 타입 검사 밖의 루트 스크립트, 검증마다 갈리는 `--seed`
- [ ] 목표 6: **산출물의 값은 바뀌지 않는다.** 바뀌는 것은 「누가 소유하는가」뿐이다

## 2) 비목표(Non-Goals)

- 값 중복 통합 — 계획서 C 소관 (**C 를 먼저 해야 이 계획서의 import 정리가 한 번에 끝난다**)
- 데드코드 삭제 — 계획서 D 소관
- 중복 «로직» 통합과 성능 — 계획서 F 소관 (수집기 공통화·`expanding_rank` 벡터화·중복 I/O)
- 문서 정합 — 계획서 G 소관
- **`studies/constants.py` 라는 새 공통 계층을 만드는 것** — E-6 에서 결정하되, **기본은 만들지 않는다.**
  루트 `CLAUDE.md` 가 「공통 계층은 「검증 중」이 아니라 「확정 후」에 만듭니다」로 정했다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

#### E-1. 매매법-중립 모듈이 특정 매매법의 값을 기본값으로 갖는다 🔴

`strategy/trade_fill.py` 는 계약이 **「체결 판정식의 소유자. 매매법 이름을 갖지 않는다」**로 못박은 모듈이다. 그런데

```python
# trade_fill.py:67
def simulate_signal(..., stop_level: float = STOP_LOSS_LEVEL, ...)
```

`STOP_LOSS_LEVEL` 은 **역방향 매매의 확정 손절선**이다(`strategy/constants.py:62`, 근거는 `docs/strategy/역방향_매매_규칙.md` §3.1). 즉 **공유 체결식의 기본값이 한 매매법의 파라미터**다. 옵션 만기일·월말은 자기 값을 넘기므로 지금 문제가 드러나지 않지만, 인자를 빠뜨리는 순간 **역방향의 손절선이 조용히 적용된다.**

같은 계열로 `strategy/constants.py:18` 이 `studies.reverse.constants` 를 import 한다. 그래서 **월말 매매를 돌리면 역방향의 `DATASETS` 정의가 딸려 온다.** 계약이 금지한 「매매법끼리 import」를 파일 이름으로는 피했지만 **공유 constants 를 경유해 사실상 이어져 있다.**

2026-09-14 사용처 조사:

| 상수 | 성격 | 쓰는 파일 |
| --- | --- | --- |
| `TARGETS`·`START_YEAR`·`HOLD_LIMIT`·`STOP_LOSS_LEVEL` | 역방향 전용 | `reverse_runner.py` · `run_reverse_trading.py` (+ `trade_fill.py` 기본값) |
| `EXPIRY_CELLS`·`EXPIRY_STOP_LEVEL`·`EXPIRY_STOP_LEVELS` | 옵션 만기일 전용 | `option_expiry_runner.py` · `run_option_expiry_trading.py` · `check_expiry_dividend.py` |
| `MONTH_END_STOP_LEVELS` | 월말 전용 | **`month_end_runner.py` 한 파일뿐** |

`src/verify_lab/CLAUDE.md` 「상수 관리」가 「1개 파일에서만 사용 → 해당 파일 상단」이라고 정했으므로 `MONTH_END_STOP_LEVELS` 는 위치부터 규칙 위반이다.

#### E-2. 같은 원칙을 두 검증이 다르게 구현한다 🟠

측정의 원칙 17 이 요구하는 **「표본이 0건인 구간도 행을 남긴다」**의 구현이 두 벌이고 결과 모양이 다르다.

| 검증 | 위치 | 방식 | 빈 행의 컬럼 수 |
| --- | --- | --- | --- |
| 옵션 만기일 | `studies/option_expiry/runner.py:545-549` | `merged.reindex([0])` — **전체 스키마 유지** | 40여 |
| 월말 | `studies/month_end/runner.py:426-428` | `pd.DataFrame({SAMPLE:[0], JUDGEABLE:[NO]})` | **2** |

루트 `CLAUDE.md` 가 반복해서 적은 그 상황이다 — 「원칙이 요구하는 것을 검증마다 구현하면 **같은 원칙이 다른 답을 낸다**」.

#### E-3. CLI 가 `summary.json` 을 조립하는 검증이 둘 남았다 🟠

`src/verify_lab/CLAUDE.md` 실행 요약 계약이 **「옵션 만기일은 CLI 에서 요약을 조립해 `scripts/CLAUDE.md` 의 「CLI 에 도메인 로직 금지」에 걸렸다」**를 고친 사례로 적어 두었는데, 검증 계층 둘이 그대로다.

| 위치 | 내용 |
| --- | --- |
| `scripts/studies/run_leverage_tracking_study.py:84-101` | `run_info` 를 CLI 에서 **리터럴 키**로 조립 (`"index"`·`"pair_count"`·`"divergence_rows"` …) |
| `scripts/studies/run_futures_leverage_study.py:143-154` | `summary` 를 CLI 에서 리터럴 키로 조립 |

둘 다 `row_counts` 가 **파일 이름이 아니라 별칭**(`divergence_rows`)이다 — 매매 계층이 「별칭으로 되돌아가는 것을 막는다」며 명시적으로 금지한 형태다(`strategy/run_summary.py:146`).

#### E-4. `dataset_record` 를 검증 계층이 못 쓴다 🟠

`strategy/run_summary.dataset_record` 가 「`ticker`·`label`·`file`·`period`·`rows`」를 만든다. 검증 계층이 같은 것을 만들어야 하는데 **`studies → strategy` import 는 계층 방향을 뒤집으므로** 각자 만들고 있다(계획서 B 가 값과 키를 맞췄지만 **구현은 여전히 두 벌**).

중립 자리로 옮기면 한 벌이 된다. 후보는 `report/`(산출물 저장을 이미 소유) 또는 `common_constants` 계열이다.

#### E-5. 설정의 사각지대 🟡

- `pyrightconfig.json` 의 `include` 가 `["src","tests","scripts"]` — **루트 `validate_project.py` 만 타입 검사 밖**이다. 품질 게이트 자신이 게이트를 안 받는다
- `--seed` 가 `run_reverse_study.py`·`run_month_end_study.py` 에는 있고 **`run_option_expiry_study.py` 에는 없다.** 그 runner 는 `seed` 를 받는다. `src/verify_lab/CLAUDE.md` 가 「난수는 **시드를 인자로 받고** 기본값을 상수로 둔다」로 정했다

#### E-6. C 가 넘긴 결정 — 「달력형 검증 공통 어휘」를 뽑을 것인가 🟡

월말↔옵션 만기일에 같은 값의 상수가 **11쌍** 남는다(`exit_date`·`entry_close`·`exit_close`·`hold_days`·`baseline`·`_baseline`·`보유 거래일`·`진입 종가`·`청산 종가`·`제외 사유`·`같은 길이 단순 보유`). 두 배수 검증(`futures_leverage`↔`leverage_tracking`)에도 **12쌍**이 있다.

계획서 C 는 「측정의 원칙에 적혀 있는가」를 기준으로 원칙 11·13·17 의 값만 올렸다. **나머지를 어떻게 할지는 여기서 결정한다.**

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 「공통 계층과 개별 검증의 경계」(**공통 계층은 「확정 후」에 만든다**), 「측정의 원칙」 17
- `src/verify_lab/CLAUDE.md` — 「계층 구조」·「계층 간 의존 방향」·「상수 관리」·「계층 간 계약」 전체
  (특히 **매매 계층 구성 계약**과 그 **기각안 표**, **실행 요약 계약**)
- `scripts/CLAUDE.md` — 「핵심 책임」, 「제약사항」(CLI 에 도메인 로직 금지)
- `.claude/rules/strategy.md` — 매매 계층의 예외 규정
- `tests/CLAUDE.md`

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [ ] **선행 계획서(A~D) 복기 완료** — 상태와 「후속 계획서 인계」 절을 읽고,
      이 계획서가 옮기려는 대상이 여전히 그 자리에 있는지 판정해 진행 로그에 적었다
- [ ] Phase 0 재판단 게이트를 E-1 ~ E-6 전 항목에 실행하고 「한다 / 안 한다」와 근거를 진행 로그에 표로 남겼다
- [ ] E-6 의 결정(공통 어휘를 뽑을 것인가)을 내리고 **근거를 `src/verify_lab/CLAUDE.md` 에 남겼다**
- [ ] 「한다」로 판정된 항목이 전부 구현됐다
- [ ] `tests/test_layer_contracts.py` 가 새 소유권을 검사한다
- [ ] **산출물 값 불변 확인** — Phase 4 대조 결과를 진행 로그에 적었다
- [ ] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [ ] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [ ] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [ ] 필요한 문서 업데이트 — `src/verify_lab/CLAUDE.md` 계층 계약 갱신 / `scripts/CLAUDE.md` /
      `docs/COMMANDS.md` (**`--seed` 를 추가하면 변경 있음**)
- [ ] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
- [ ] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/strategy/trade_fill.py` — 기본값 제거 (E-1)
- `src/verify_lab/strategy/constants.py` — 매매법별 상수 이동, `studies.reverse` import 제거 (E-1)
- `src/verify_lab/strategy/reverse_runner.py` · `option_expiry_runner.py` · `month_end_runner.py` — import 교정
- `scripts/strategy/run_reverse_trading.py` · `run_option_expiry_trading.py` · `scripts/data/check_expiry_dividend.py` — import 교정
- `src/verify_lab/studies/month_end/runner.py` — 빈 구간 행 구현 통일 (E-2)
- `src/verify_lab/studies/leverage_tracking/runner.py` · `futures_leverage/runner.py` — 요약 조립 이관 (E-3)
- `scripts/studies/run_leverage_tracking_study.py` · `run_futures_leverage_study.py` — 조립 제거 (E-3)
- `src/verify_lab/report/writer.py` 또는 신규 중립 모듈 — `dataset_record` 이관 (E-4)
- `src/verify_lab/strategy/run_summary.py` — `dataset_record` 를 새 소유자에서 재사용
- `scripts/studies/run_option_expiry_study.py` — `--seed` 추가 (E-5)
- `pyrightconfig.json` — `validate_project.py` 포함 (E-5)
- `tests/test_layer_contracts.py` · 관련 테스트
- `src/verify_lab/CLAUDE.md` · `scripts/CLAUDE.md` · `docs/COMMANDS.md`
- `docs/COMMANDS.md`: **변경 있음 예상** (`run_option_expiry_study.py --seed`). Phase 0 에서 확정

### 데이터/결과 영향

- **CSV 값·컬럼 불변**
- 🔴 **`summary.json` 이 바뀐다** — `leverage_tracking`·`futures_leverage` 의 `row_counts` 키가
  별칭(`divergence_rows`)에서 **파일 이름**(`divergence.csv`)으로 바뀐다
  - 계획서 B 와 같은 원칙: **이미 커밋된 산출물은 소급 수정하지 않는다**
  - 결과 문서가 그 키를 인용하는지 Phase 0 에서 확인한다
- `--seed` 는 **기본값이 상수와 같으므로** 인자 없이 돌리면 결과가 그대로다

## 6) 단계별 계획(Phases)

### Phase 0 — 재판단 게이트

> **건너뛸 수 없다.** 이 계획서는 **파일을 옮기는** 작업이라 되돌리기가 가장 비싸다.

**작업 내용**:

- [ ] 🔴 **선행 계획서 복기 (이 Phase 의 첫 작업)** — 이 계획서는 **파일을 옮기는** 작업이라
      앞선 계획서가 이미 옮겼거나 지운 것을 또 옮기려 들 수 있다:

  ```bash
  for f in docs/plans/PLAN_[a-g]_*.md; do
    echo "=== $f"; grep -m1 '^\*\*상태\*\*' "$f"
    sed -n '/^### 후속 계획서 인계/,/^### 진행 로그/p' "$f"
  done
  ```

  - 🔴 **C 의 인계 절**: 「어느 이름이 어디로 옮겨갔는가」 — 이 계획서의 import 정리 대상이 달라진다.
    **C 가 세운 계약 테스트가 무엇을 막는지**도 읽는다 (파일을 옮기다 그 테스트에 걸린다)
  - 🔴 **D 의 인계 절**: 지운 이름 목록 — **없어진 것을 옮기려 들지 않게** 한다
  - 🔴 **B 의 인계 절**: E-4(`dataset_record` 이관)는 **B 가 키를 맞춘 뒤**여야 한 번에 끝난다.
    **B 가 Draft 면 E-4 를 이번에 하지 말고 Non-Goals 로 옮긴다** (그 사실을 진행 로그에)
  - **C 가 E-6(달력형 공통 어휘)을 넘겼다.** C 의 인계 절에 그 결정 상태가 적혀 있다
  - 전제가 깨졌으면 Scope 를 조정하고 무엇이 왜 달라졌는지 적는다

- [ ] **E-1 재판단**:

  ```bash
  grep -n "STOP_LOSS_LEVEL" src/verify_lab/strategy/trade_fill.py
  grep -n "from verify_lab.studies" src/verify_lab/strategy/constants.py
  for n in TARGETS START_YEAR STOP_LOSS_LEVEL HOLD_LIMIT EXPIRY_CELLS EXPIRY_STOP_LEVEL EXPIRY_STOP_LEVELS MONTH_END_STOP_LEVELS; do
    echo -n "$n: "; grep -rln "\b$n\b" src scripts | grep -v "strategy/constants.py" | tr '\n' ' '; echo
  done
  ```

  - **한다**: `trade_fill` 이 여전히 매매법 상수를 기본값으로 갖고, `strategy/constants.py` 가 `studies.reverse` 를 import 할 때
  - 🔴 **어디로 옮길지 결정한다.** 세 안:
    - **(a) `strategy/<slug>_runner.py` 파일 상단** — 「1개 파일에서만 사용」인 `MONTH_END_STOP_LEVELS` 에 정확히 맞다.
      다만 `TARGETS`·`EXPIRY_CELLS` 는 스크립트도 쓰므로 2파일 이상이라 규칙에 안 맞는다
    - **(b) `strategy/<slug>_constants.py` 신설** ← 권장. 2파일 이상 쓰는 것은 여기,
      1파일 전용은 (a). **`strategy/constants.py` 에는 매매법 이름이 붙지 않는 것만 남는다**
    - **(c) 그대로 두고 문서로 근거를 남긴다** — 파일 수를 늘리지 않는 대신 결합이 남는다
  - 고른 안과 근거를 진행 로그에 적는다

- [ ] **E-2 재판단**:

  ```bash
  sed -n '540,556p' src/verify_lab/studies/option_expiry/runner.py
  sed -n '417,436p' src/verify_lab/studies/month_end/runner.py
  ```

  - **한다**: 두 구현이 여전히 다른 모양의 빈 행을 낼 때
  - 🔴 **어느 쪽에 맞출지 결정한다.** 권장은 **옵션 만기일 방식(전체 스키마 유지)** — 산출물에서
    빈 행과 정상 행의 컬럼이 같아 표 도구로 한 번에 읽힌다. 다만 **월말의 `periods.csv` 컬럼 구성이 바뀔 수 있으므로**
    Phase 4 대조에서 그 차이를 반드시 확인한다
  - ⚠️ **월말을 옵션 만기일에 맞추면 `periods.csv` 의 빈 행이 「2컬럼 + NaN」에서 「전 컬럼 NaN」으로 바뀐다.**
    값(NaN)은 같고 **CSV 상 빈칸도 같다.** 그래도 대조에서 확인한다

- [ ] **E-3 재판단**:

  ```bash
  grep -n "save_run_summary" -B25 scripts/studies/run_leverage_tracking_study.py | tail -30
  grep -n "save_run_summary" -B18 scripts/studies/run_futures_leverage_study.py | tail -22
  grep -rn '"[a-z_]*_rows"' src scripts
  ```

  - **한다**: CLI 에 리터럴 키 조립이 남아 있을 때
  - 파급: `grep -rn "divergence_rows\|comparison_rows\|pair_count" docs/ CLAUDE.md`

- [ ] **E-4 재판단**: `grep -rn "dataset_record\|KEY_DATASET_" src/verify_lab/`
  - **한다**: 검증 계층이 여전히 자기 손으로 같은 dict 를 만들 때
  - 🔴 **어디로 옮길지 결정한다.** 권장은 **`report/`** — 산출물 폴더 생성과 저장을 이미 소유하고,
    `studies`·`strategy` 둘 다 이미 `report` 에 의존하므로 **방향이 뒤집히지 않는다**
  - **안 한다**: 계획서 B 를 아직 안 했다면 **B 를 먼저 한다.** 순서가 뒤집히면 같은 줄을 두 번 고친다

- [ ] **E-5 재판단**:

  ```bash
  grep -n "seed" scripts/studies/run_option_expiry_study.py
  grep -n "include" pyrightconfig.json
  ```

  - 🔴 `validate_project.py` 를 `include` 에 넣으면 **strict 검사가 새로 걸린다.**
    먼저 얼마나 걸리는지 본다: `poetry run pyright validate_project.py`
    - 오류가 많고 그 파일이 「도구 스크립트」 성격이면 **`executionEnvironments` 로 `scripts/` 와 같은 완화를 준다**
    - 그래도 과하면 **하지 않는다** — 근거를 진행 로그에 적는다

- [ ] 🟡 **E-6 결정 — 달력형·배수형 공통 어휘를 뽑을 것인가**
  - **(a) 뽑지 않는다** ← 권장. 루트 `CLAUDE.md` 가 「공통 계층은 「확정 후」에 만든다」고 정했고,
    두 쌍 다 **검증 «고유» 어휘**라 「측정의 원칙에 적혀 있는가」 기준에 걸리지 않는다.
    대신 **왜 뽑지 않는지를 `src/verify_lab/CLAUDE.md` 에 명문화**해 다음 사람이 같은 판단을 반복하지 않게 한다
  - **(b) 뽑는다** — `studies/constants.py` 를 만들고 11+12쌍을 올린다.
    선택하면 **새 공통 계층이 생기므로** 「무엇이 여기 들어오는가」의 기준을 함께 정해야 한다
  - 어느 쪽이든 **결정과 근거를 문서에 남기는 것이 이 항목의 산출물**이다

- [ ] 항목별 판정을 **진행 로그에 표로** 남긴다

---

### Phase 1 — 계약 테스트를 먼저 넓힌다(레드 허용)

**작업 내용**:

- [ ] `tests/test_layer_contracts.py` 에 추가
  - **매매법-중립 모듈이 매매법 상수를 모른다** — `strategy/trade_fill.py`·`periods.py`·`run_summary.py` 가
    `TARGETS`·`EXPIRY_CELLS`·`STOP_LOSS_LEVEL` 류를 import 하지 않는다
  - **`strategy/constants.py` 가 `studies` 를 import 하지 않는다** (E-1 을 (b)나 (a)로 고른 경우)
  - **`row_counts` 의 키는 파일 이름이다** — 세 매매 + 다섯 검증의 요약에서 키가 전부 `.csv` 로 끝난다
    (`strategy/run_summary.build_run_summary` 가 매매에 대해 이미 검사한다. **검증까지 넓힌다**)
  - **`dataset_record` 정의처가 하나다** (E-4 를 「한다」로 고른 경우)
- [ ] 지금 실패하는지 확인한다

---

### Phase 2 — 소유권 이동(그린 유지)

**작업 내용**:

- [ ] **E-1a** `strategy/trade_fill.py` 의 `stop_level` 기본값 제거
  - 🔴 **기본값을 지우면 호출부가 전부 값을 넘겨야 한다.** `reverse_runner.py` 는 이미 넘긴다 —
    `grep -rn "simulate_signal(" src scripts tests` 로 전수 확인
  - `measure/screening.screen_candidates` 의 `tradable` 과 `strategy/constants.stop_level_value` 의
    `measurable` 이 **「기본값을 두지 않는다」를 같은 이유로 이미 하고 있다.** 그 관용을 따른다
- [ ] **E-1b** 매매법별 상수를 Phase 0 에서 고른 자리로 옮긴다
  - `strategy/constants.py` 에서 `from verify_lab.studies.reverse.constants import DATASETS, Dataset` 제거
  - `MONTH_END_STOP_LEVELS` 는 **한 파일 전용**이므로 `month_end_runner.py` 상단으로 (규칙 그대로)
  - `strategy/constants.py` 에는 **매매법 이름이 붙지 않는 것만** 남는다 — 파일명 상수·청산 사유·
    표시 레이블·구간 축·`stop_level_value`
  - 옮긴 뒤 `grep -rn "<옮긴 이름>" src scripts tests` 로 import 를 전부 교정
- [ ] **E-2** 빈 구간 행 구현을 하나로
  - Phase 0 에서 고른 방식으로 월말(또는 옵션 만기일)을 맞춘다
  - 🔴 **두 검증이 같은 함수를 쓰게 하려면 그 함수가 어디 있어야 하는가** — `measure/` 가 자연스럽지만
    「빈 행을 만드는 방법」은 표 조립이라 `report/` 일 수도 있다. **E-6 을 (a)로 골랐다면
    새 공통 모듈을 만들지 않고 «같은 모양»만 맞춘다** (구현은 두 벌로 두되 결과가 같게)
  - 어느 쪽이든 **테스트로 「두 검증의 빈 행 컬럼 구성이 같다」를 고정**한다
- [ ] **E-3** CLI 요약 조립을 runner 로
  - `studies/leverage_tracking/runner.py` · `studies/futures_leverage/runner.py` 가
    `summary` 를 **자기가** 만든다 (`StudyOutputs.summary` 로 내보낸다 — 나머지 세 검증의 관용)
  - `row_counts` 키를 **파일 이름 상수**로 바꾼다. 파일명 상수가 없으면 그 검증 `constants.py` 에 만든다
  - CLI 는 `save_run_summary(directory, outputs.summary)` 한 줄만 남긴다
  - ⚠️ CLI 만 아는 값(`--index` 필터)은 **runner 에 인자로 넘겨** runner 가 요약에 담는다.
    `run_study(index_filter=...)` 가 이미 그 인자를 받는다
- [ ] **E-4** `dataset_record` 를 중립 자리로
  - Phase 0 에서 고른 자리(권장 `report/`)로 옮기고 `strategy/run_summary.py` 는 재export 하지 않고
    **직접 import** 한다 (재노출은 계약이 기각한 패턴 — 계획서 C 참고)
  - 다섯 검증 runner 가 같은 함수를 쓰게 한다
  - 🔴 검증마다 `datasets` 항목에 더 붙는 키가 있다(`expiry_count`·`is_index` 등).
    **공통 함수가 낸 dict 에 검증이 덧붙이는 형태**로 만든다 — 공통 함수에 검증별 인자를 넣지 않는다

---

### Phase 3 — 설정의 사각지대(그린 유지)

**작업 내용**:

- [ ] **E-5a** `scripts/studies/run_option_expiry_study.py` 에 `--seed` 추가
  - 기본값은 `DEFAULT_RANDOM_SEED` — **인자 없이 돌리면 결과가 그대로여야 한다**
  - 현재 `--repeats` 는 `None` 기본에 `kwargs` 로 넘기는 형태다(`:202`). **두 인자의 방식을 맞춘다** —
    나머지 두 검증처럼 `default=DEFAULT_*` 로 두고 그냥 넘기는 쪽이 단순하다
  - `docs/COMMANDS.md` 의 그 절에 예시 한 줄 추가
- [ ] **E-5b** `pyrightconfig.json` 의 `include` 에 `validate_project.py` 추가
  - Phase 0 에서 잰 오류 수에 따라 `executionEnvironments` 완화를 함께 넣는다
  - **오류가 남은 채로 넘기지 않는다** — 품질 게이트가 실패한다

---

### Phase 4 — 값 불변 대조

**작업 내용**:

- [ ] 다섯 검증 + 세 매매를 인자 없이 돌린다 (재수집하지 않는다)
- [ ] **CSV 는 전 셀 동일**해야 한다. 직전 산출물과 기계로 대조한다
- [ ] **`summary.json` 은 `leverage_tracking`·`futures_leverage` 만 바뀐다.**
      나머지 여섯은 동일해야 한다 — 그것도 대조로 확인한다
- [ ] E-2 를 「한다」로 했다면 **월말 `periods.csv` 의 빈 행**을 눈으로도 한 번 본다.
      값은 같아야 하고 컬럼 구성만 넓어진다
- [ ] 🔴 예상 밖의 차이가 있으면 멈추고 원인을 밝힌다
- [ ] 새 폴더는 커밋하지 않고 `/clean-results` 로 정리한다

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [ ] `src/verify_lab/CLAUDE.md` 갱신
  - 「계층 구조」에 매매법별 상수의 자리를 적는다 (E-1 결정)
  - 실행 요약 계약에 **「검증 계층도 `row_counts` 키는 파일 이름」**을 명시
  - `dataset_record` 소유자를 적는다
  - **E-6 결정과 그 근거를 한 문단으로 남긴다** — 「검증 고유 어휘가 두 벌인 것을 왜 지금 합치지 않는가」
- [ ] `scripts/CLAUDE.md` 갱신 — 「CLI 는 요약을 조립하지 않는다」를 명시 (지금은 사례로만 적혀 있다)
- [ ] `docs/COMMANDS.md` — `--seed` 예시 추가 (**변경 있음**)
- [ ] 자동 포맷 적용: `poetry run black .`
- [ ] 🔴 **「후속 계획서 인계」 절을 채운다** (§8 Notes) — **F·G 가 알아야 할 것**을 적는다:
      **새로 생긴 파일과 옮긴 모듈**(F 가 공통 조각을 둘 자리를 정할 때 본다),
      바뀐 `summary.json` 키, **E-6 결정과 그 근거**, `validate_project.py` 가 타입 검사에
      들어갔는지(F-5 와 순서가 걸린다), G 가 고칠 문서에서 이미 반영된 항목.
      **비워 두면 다음 계획서가 낡은 전제로 시작한다**
- [ ] 변경 기능 및 전체 플로우 최종 검증
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

(비어 있음 — `/commit` 으로 채운다)

## 7) 리스크(Risks)

| 리스크 | 완화 |
| --- | --- |
| **파일을 옮기다 순환 import** 가 생긴다 | E-4 의 이동 방향(`strategy → report`)이 의존 방향과 같다. E-1 은 오히려 `strategy → studies` 의존을 **끊는다** |
| `trade_fill` 기본값 제거로 호출부가 깨진다 | Phase 2 에 전수 grep 을 명시. 세 매매법 전부 이미 값을 넘긴다 |
| E-3 이 `summary.json` 을 바꿔 결과 문서 인용이 깨진다 | Phase 0 에 파급 확인 명령. 두 검증은 결과 문서가 `row_counts` 를 인용할 가능성이 낮지만 **확인 후 진행** |
| E-2 로 월말 `periods.csv` 컬럼이 넓어져 문서 수치와 어긋나 보인다 | **값은 안 바뀐다**(빈칸은 빈칸). Phase 4 에서 확인하고, 컬럼 구성이 달라진 사실은 결과 문서 머리말에 한 줄로 남긴다 |
| E-1 을 (b)로 하면 파일이 3개 늘어난다 | 「과복잡한가」를 스스로 물어야 한다. **`MONTH_END_STOP_LEVELS` 처럼 1파일 전용은 파일을 만들지 말고 그 파일 상단으로** |
| E-6 을 (b)로 골라 새 공통 계층을 만들면 되돌리기 어렵다 | 권장은 (a). 고르더라도 **기준을 함께 문서화**해야 다음 검증에서 흔들리지 않는다 |

## 8) 메모(Notes)

- **왜 D 다음인가**: C·D 가 값 중복과 죽은 정의를 걷어낸 뒤라야 「무엇을 옮길지」가 명확하다. 먼저 옮기면 죽은 것까지 옮긴다
- **B 와의 순서 의존**: E-4(`dataset_record` 이관)는 **B 가 키를 맞춘 뒤**여야 한 번에 끝난다. B 를 건너뛰었다면 E-4 도 미룬다
- 2026-09-14 실측 — `trade_fill.simulate_signal` 의 `stop_level` 기본값이 **역방향의 −5%** 이고,
  `MONTH_END_STOP_LEVELS` 는 **`month_end_runner.py` 한 파일에서만** 쓰인다
- E-6 은 **「하지 않기로 결정하고 그 근거를 남기는 것」도 완료**다. 결정 없이 넘기는 것만 실패다

### 후속 계획서 인계 (이 계획서를 끝낸 뒤 채운다)

> **F·G 가 실행 전에 이 절을 읽는다.** 이 계획서로 바뀐 것 중 **그쪽 전제에 영향을 주는 것만** 적는다.
> 형식: `무엇이 | 어떻게 바뀌었나 | 어느 계획서가 영향받나`
>
> 🔴 **새로 생긴 모듈과 옮긴 파일을 반드시 적는다** — F 가 「공통 조각을 어디 둘까」를 정할 때
> 이 목록이 기준이 된다. 아무것도 안 바뀌었으면 **「없음」이라고 적는다**.

(비어 있음 — 마지막 Phase 에서 채운다)

### 진행 로그 (KST)

- 2026-09-14 12:05: 계획서 작성. 감사의 「구조개선」과 B·C 가 넘긴 결정 항목을 E 로 묶음
