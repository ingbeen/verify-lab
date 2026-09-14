# Implementation Plan: A — 조용히 틀리는 지점에 가드를 세운다

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

**작성일**: 2026-09-14 12:05
**마지막 업데이트**: 2026-09-14 12:40
**관련 범위**: measure, strategy, studies/month_end, tests
**관련 문서**: `src/verify_lab/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/python.md`(전역), `.claude/rules/strategy.md`

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

- [ ] 목표 1: **잘못된 입력이 예외 없이 그럴듯한 숫자로 흘러가는 경로 4곳을 막는다.** 전부 「예외도 경고도 나지 않고 결과만 틀리는」 형태다
- [ ] 목표 2: 막은 각 지점에 **재발을 잡는 테스트**를 붙인다
- [ ] 목표 3: **기존 산출물의 값은 하나도 바뀌지 않는다.** 이 계획서는 동작을 바꾸는 것이 아니라 「일어나면 안 되는 일」에서 멈추게 하는 것이다

## 2) 비목표(Non-Goals)

- 판정 기준·산식·산출물 스키마 변경 — 전부 다른 계획서(B·C·D·E·F) 소관
- 상수 중복 통합, 데드코드 삭제, 문서 정합 — B~F 소관
- **`utils/result_citations.existing_result_dirs` 제거** — 감사에서 「얇은 래퍼」로 지목했으나 `tests/test_result_citations.py` 가 6개 테스트로 이 이름을 직접 검증하고 있어 제거 이득보다 테스트 churn 이 크다. **검토했고 하지 않기로 한다** (다음 세션이 같은 분석을 반복하지 않도록 남긴다)
- **`report/tables.horizon_label`·`_basis_label` 의 「모르는 값 통과」** — 두 함수 모두 docstring 에 「의도된 설계」와 그 근거(공통 계층은 검증별 격자를 모른다)가 적혀 있다. 막지 않는다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

2026-09-14 전체 감사에서 나온 것 중 **「결과가 조용히 틀리는」** 부류만 모았다. 네 지점 모두 Ruff·PyRight 를 통과하며 현재 데이터에서는 드러나지 않는다.

#### A-1. 매매 계층의 `get_indexer` 4곳이 `-1` 을 검사하지 않는다 🔴

`pandas.Index.get_indexer` 는 찾지 못한 날짜에 **`-1`** 을 돌려준다. 검증 계층 세 곳은 전부 이것을 막는데 매매 계층 네 곳은 막지 않는다.

| 계층 | 위치 | `-1` 가드 |
| --- | --- | --- |
| studies | `studies/month_end/schedule.py:238-241` · `studies/option_expiry/weekly_exit.py:150-153` · `studies/option_expiry/offsets.py:80-83` | **있음** (`min() < 0` → `ValueError` + 날짜 목록) |
| strategy | `strategy/month_end_runner.py:185`, `:187` · `strategy/option_expiry_runner.py:300`, `:301` | **없음** |

`-1` 이 `simulate_scheduled_trade` 로 흘러가면 갈래가 둘이다.

- **손절 경로**(`stop_level` 이 숫자): `simulate_signal._validate` 의 `0 <= entry_position` 에 걸려 `ValueError` — 살아난다
- **무손절 경로**(`stop_level is None`): `_scheduled_exit` 가 `frame.iloc[-1]` 로 **마지막 행을 진입가로 쓴다.** 예외가 없다

무손절 경로는 **월말의 지수 대상이 언제나 지나는 길**이다(지수는 고가·저가가 없어 손절을 못 걸므로 `index_levels = (None,)`). 즉 가드가 없는 쪽이 하필 상시 경로다.

실증 (2026-09-14):

```
frame = 5행, Value = [100, 101, 102, 103, 500]
simulate_scheduled_trade(frame, -1, 3, bet_down=False, stop_level=None, price_column="Value")
  → TradeResult(return_rate=-0.794, reason='기한청산', hold_days=4)
     ← 예외 없이 500(마지막 행)을 진입가로 잡아 -79.4% 체결이 만들어진다
```

`trade_fill.simulate_scheduled_trade` 의 첫 검사가 `if not entry_position < exit_position < len(frame)` 이라 **하한이 비어 있는 것**이 근본 원인이다.

#### A-2. 후보 판정이 축 값당 첫 행만 쓰고 나머지를 조용히 버린다 🔴

`measure/screening.py:150-153`

```python
rows = [
    _screen_cell(cell.iloc[0], axis_column=axis_column, tradable=tradable)
    for _, cell in summary.groupby(axis_column, sort=True)
]
```

한 축 값에 행이 둘 이상이면 두 번째부터 **사라진다.** 실증 (2026-09-14): 입력 2행(`axis=9`) → 출력 1행, 로그도 `1칸 중 후보 1` 로 정상처럼 찍힌다.

같은 저장소의 `report/tables.py:467`(`_sorted_single_basis_cells`)은 같은 종류의 사고에 **`ValueError` 를 던진다.** 가드 강도가 정반대다.

**현재 호출처는 전부 축당 1행이라 값이 바뀌지 않는다** — 2026-09-14 실측으로 확인했다(아래 Phase 0 재판단 게이트에 명령 있음). 축을 하나 더 붙이거나 기준을 둘로 늘리는 날 조용히 틀린다.

#### A-3. 「진입 = 유효 + 제외」가 깨질 수 있는 경로 🟡

`studies/month_end/schedule.py:249-256` — `has_entry` 이면서 `has_month` 가 거짓이면 `usable` 은 거짓인데 사유는 진입 단계의 `REASON_NONE` 이 그대로 남는다. **「유효도 제외도 아닌 행」**이 생겨 표본 보존 항등식이 조용히 깨진다.

현재 입력에서는 도달 불가다(진입일이 `trading_days` 에서 나왔으므로 그 달은 반드시 존재한다). **도달 불가인데 방어 코드가 있고, 그 방어가 조용하다** — 전역 규칙 「불가능 조건은 `RuntimeError`, 조용히 건너뛰지 않는다」에 어긋난다.

#### A-4. 기준 칸이 0건이면 요약의 진입·제외 건수가 통째로 사라진다 🟡

`studies/month_end/runner.py:606, 618-620, 629` — `block.empty` 면 `continue` 하므로 원 매매법 칸(20일 → 말일)에 도달하지 못하고 `base_record = {}` 인 채로 요약이 나간다. 「표본 보존」이 요구하는 `entry_count`·`excluded_count`·`hold_days`·`baseline_entry_count`·`converged_months` 다섯이 통째로 빠지는데 **`summary.json` 은 정상으로 보인다.**

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절, 「측정의 원칙」
- `src/verify_lab/CLAUDE.md` — 특히 「명시적 검증 / 불가능 조건」, 「측정 계층의 절대 원칙」(표본 보존·판정식 단일화), 「계층 간 계약」
- 전역 `~/.claude/rules/python.md` — 「불가능 조건 처리」(`ValueError` 대 `RuntimeError` 구분)
- `tests/CLAUDE.md` — Given-When-Then, 부동소수점 비교, 파일 격리
- `.claude/rules/strategy.md` — 매매 계층의 예외 규정

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] **선행 계획서 복기 완료** — `docs/plans/PLAN_[a-g]_*.md` 의 상태와 「후속 계획서 인계」 절을 읽고,
      이 계획서의 전제가 바뀐 것이 있으면 진행 로그에 적었다
- [x] Phase 0 재판단 게이트를 전 항목에 대해 실행하고, 각 항목의 「한다 / 안 한다」를 진행 로그에 근거와 함께 남겼다
- [ ] A-1 ~ A-4 중 「한다」로 판정된 항목이 전부 구현됐다
- [ ] 회귀/신규 테스트 추가 (막은 지점마다 최소 1개)
- [ ] **기존 산출물 값 불변 확인** — Phase 3 의 대조 절차를 수행하고 결과를 진행 로그에 적었다
- [ ] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [ ] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [ ] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [ ] 필요한 문서 업데이트 (`docs/COMMANDS.md` 변경 없음을 확인 — 실행 방법·CLI 옵션이 바뀌지 않는다)
- [ ] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (「무손절 경로가 지수의 상시 경로라 가드가 없는 쪽이 하필 상시 경로였다」는 사실을
      `src/verify_lab/CLAUDE.md` 「계층 간 계약」의 매매 산출물 계약에 한 줄로 남긴다)
- [ ] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/strategy/trade_fill.py` — 진입 위치 하한 검사 (A-1 근본)
- `src/verify_lab/strategy/option_expiry_runner.py` — `collect_entries` 의 `-1` 가드 (A-1)
- `src/verify_lab/strategy/month_end_runner.py` — `_collect_entries` 의 `-1` 가드, `_run_dataset` 의 기준 칸 누락 (A-1, A-4)
- `src/verify_lab/measure/screening.py` — 축 중복 거부 (A-2)
- `src/verify_lab/studies/month_end/schedule.py` — `has_month` 불변조건 (A-3)
- `src/verify_lab/studies/month_end/runner.py` — 기준 칸 미도달 (A-4)
- `tests/test_strategy_trade_fill_scheduled.py` · `tests/test_measure_screening.py` · `tests/test_studies_month_end_schedule.py` · `tests/test_strategy_month_end_runner.py` · `tests/test_studies_month_end_runner.py`
- `src/verify_lab/CLAUDE.md` — 근거 승격 한 줄
- `docs/COMMANDS.md`: **변경 없음** (실행 명령어·CLI 옵션이 바뀌지 않는다)

### 데이터/결과 영향

- **출력 스키마 변경 없음**
- **값 변경 없음이 요구사항이다.** 네 가드 전부 현재 입력에서 도달 불가한 조건에서만 발동한다.
  Phase 3 에서 대조로 확인한다
- 새 산출물 폴더가 생기면 **커밋하지 않는다.** 결과 문서가 인용하지 않으므로 `/clean-results` 로 정리한다
  (`.claude/rules/session-bootstrap.md` 6절)

## 6) 단계별 계획(Phases)

### Phase 0 — 재판단 게이트 (코드를 고치기 전에 «정말 고쳐야 하는지»를 다시 확인한다)

> **이 Phase 는 건너뛸 수 없다.** 감사 시점(2026-09-14)과 실행 시점 사이에 코드가 바뀌었을 수 있고,
> 감사 판단 자체가 틀렸을 수도 있다. **항목마다 「확인 명령」을 돌려 현재 상태를 눈으로 보고,
> 「이러면 하지 않는다」에 해당하면 그 항목을 Non-Goals 로 옮긴 뒤 진행 로그에 사유를 적는다.**

**작업 내용**:

- [x] 🔴 **선행 계획서 복기 (모든 계획서의 첫 작업)** — 이 계획서는 **A**(첫 번째)지만,
      순서를 어겨 다른 계획서가 먼저 실행됐을 수 있다. `docs/plans/` 를 훑어 확인한다:

  ```bash
  for f in docs/plans/PLAN_[a-g]_*.md; do
    echo "=== $f"; grep -m1 '^\*\*상태\*\*' "$f"
    sed -n '/^### 후속 계획서 인계/,/^### 진행 로그/p' "$f"
  done
  ```

  - **🟡 Draft 가 아닌 계획서**가 있으면 그 「후속 계획서 인계」 절을 읽고,
    이 계획서의 Context·Scope 전제가 여전히 참인지 판정한다
  - 전제가 깨졌으면 **진행 로그에 무엇이 어떻게 달라졌는지 적고** 그 항목을 Non-Goals 로 옮긴다.
    조용히 기준을 낮추는 것과 구별된다 (`/impl-plan` 스킬 「이미 생성된 계획서 수정 규칙」)

- [x] **A-1 재판단** — 확인 명령:

  ```bash
  grep -rn "get_indexer" src/verify_lab/strategy/ src/verify_lab/studies/
  grep -n "entry_position < exit_position" src/verify_lab/strategy/trade_fill.py
  ```

  - **한다**: `strategy/` 의 `get_indexer` 중 하나라도 뒤에 `< 0` 검사가 없고, `trade_fill.py` 의 검사식에 하한(`0 <=`)이 없을 때
  - **안 한다**: 이미 하한이 들어가 있거나, `strategy/` 에서 `get_indexer` 가 사라졌을 때
  - 판정 보조 — 아래를 그대로 돌려 **예외가 나면 이미 고쳐진 것**이다:

    ```bash
    poetry run python -c "
    import pandas as pd
    from verify_lab.strategy.trade_fill import simulate_scheduled_trade
    from verify_lab.common_constants import COL_DATE, COL_VALUE
    f = pd.DataFrame({COL_DATE: pd.date_range('2020-01-01', periods=5), COL_VALUE: [100,101,102,103,500]})
    print(simulate_scheduled_trade(f, -1, 3, bet_down=False, stop_level=None, price_column=COL_VALUE))
    "
    ```

- [x] **A-2 재판단** — 확인 명령:

  ```bash
  sed -n '145,160p' src/verify_lab/measure/screening.py
  grep -rn "screen_candidates(" src/verify_lab/
  ```

  - **한다**: `cell.iloc[0]` 이 그대로이고, 호출처가 축당 1행을 보장하지 못할 여지가 있을 때
  - **안 한다**: 이미 중복 거부가 들어갔을 때
  - 🔴 **동시에 확인할 것** — 현재 호출처가 정말 축당 1행인지. 아래가 **전부 「유일」과 「행 수」가 같아야** 값이 안 바뀐다는 것이 보장된다:

    ```bash
    poetry run python -c "
    import pandas as pd, glob
    for f in sorted(glob.glob('storage/results/검증/*/*candidates*.csv')):
        d = pd.read_csv(f)
        keys = [c for c in d.columns if c in ('종목','대상','청산 요일','만기월','격자 칸','월','구간')]
        print(len(d), len(d.drop_duplicates(subset=keys)), keys, f)
    "
    ```

    행 수와 유일 조합 수가 **다른 파일이 하나라도 있으면** — 이미 조용히 버려지고 있다는 뜻이므로
    **가드를 넣는 순간 실행이 죽는다.** 그때는 가드를 넣기 전에 **왜 중복이 생기는지**를 먼저 조사하고
    사용자에게 보고한다 (조용히 넘기지 않는다)

- [x] **A-3 재판단** — 확인 명령:

  ```bash
  sed -n '224,258p' src/verify_lab/studies/month_end/schedule.py
  ```

  - **한다**: `has_month` 분기가 남아 있고 그 거짓 갈래가 사유를 남기지 않을 때
  - **안 한다**: `has_month` 가 사라졌거나(구조가 바뀌어 도달 자체가 없어짐) 이미 예외를 던질 때

- [x] **A-4 재판단** — 확인 명령:

  ```bash
  sed -n '598,640p' src/verify_lab/studies/month_end/runner.py
  grep -n "base_record" src/verify_lab/studies/month_end/runner.py
  ```

  - **한다**: `base_record: dict[str, Any] = {}` 초기값이 그대로 요약에 펼쳐질 수 있을 때
  - **안 한다**: 이미 기준 칸 누락을 예외로 잡을 때
  - **판단 유보 가능**: 이 항목만 심각도가 낮다(현 데이터에서 도달 불가). A-1~A-3 만 하고
    A-4 를 Non-Goals 로 옮겨도 이 계획서는 성립한다 — 그때는 **왜 뺐는지를 진행 로그에 적는다**

- [x] 네 항목의 판정을 **진행 로그에 표로** 남긴다 (`항목 | 한다/안 한다 | 근거`)

---

### Phase 1 — 인바리언트를 테스트로 먼저 고정(레드 허용)

> 「한다」로 판정된 항목만 다룬다.

**작업 내용**:

- [ ] **A-1 테스트** — `tests/test_strategy_trade_fill_scheduled.py`
  - `simulate_scheduled_trade(frame, -1, exit, stop_level=None, ...)` 이 `ValueError` 를 던진다
  - 손절 경로(`stop_level=0.05`)에서도 같은 입력이 `ValueError` 를 던진다 (기존 동작 유지 확인)
  - **정상 입력에서는 값이 그대로**임을 고정하는 기존 테스트가 깨지지 않는지 본다
- [ ] **A-1 테스트(호출부)** — `tests/test_strategy_month_end_runner.py`
  - 시세에 없는 진입일이 섞이면 **날짜가 담긴** `RuntimeError` 가 난다 (`get_indexer` 가드).
    **2026-09-14 사용자 승인으로 `ValueError` 에서 바꿨다** — 근거는 진행 로그
  - 옵션 만기일 쪽은 `collect_entries` 가 파일을 읽으므로, 파일 격리 픽스처가 없으면
    **runner 대신 `trade_fill` 단에서만 고정**하고 그 사실을 테스트 docstring 에 적는다
- [ ] **A-2 테스트** — `tests/test_measure_screening.py`
  - 같은 축 값이 두 행이면 `ValueError` 이고, 메시지에 **그 축 값**이 들어 있다
  - 축당 1행인 기존 테스트 9개가 그대로 통과한다
- [ ] **A-3 테스트** — `tests/test_studies_month_end_schedule.py`
  - 진입일은 있는데 그 달이 거래일 목록에 없는 프레임을 **직접 만들어** `RuntimeError` 를 확인한다
  - 메시지에 「내부 불변조건 위반」 접두사와 위반된 값이 들어 있다
- [ ] **A-4 테스트** — `tests/test_studies_month_end_runner.py`
  - 기준 칸의 유효 신호가 0건이 되는 최소 데이터로 `run_study` 가 **조용히 넘어가지 않음**을 확인한다

---

### Phase 2 — 구현(그린 유지)

**작업 내용**:

- [ ] **A-1a (근본)** `strategy/trade_fill.py` — `simulate_scheduled_trade` 의 첫 검사에 하한을 넣는다.

  ```python
  if not 0 <= entry_position < exit_position < len(frame):
  ```

  메시지도 「진입 위치가 0 이상이어야 한다」를 포함하게 고친다.
  **주석으로 남길 것**: 무손절 경로(`_scheduled_exit`)는 `iloc` 만 쓰므로 음수 인덱스가
  **예외 없이 마지막 행**이 된다는 사실. 이것이 하한을 여기 두는 이유다
- [ ] **A-1b (호출부 4곳)** `strategy/option_expiry_runner.py:300-301` · `strategy/month_end_runner.py:185-187`
  - `get_indexer` 결과에 `-1` 이 있으면 **어느 날짜가 시세에 없는지**를 담아 `RuntimeError`
    (「내부 불변조건 위반」 접두사). **2026-09-14 사용자 승인으로 `ValueError` 에서 바꿨다** —
    근거는 진행 로그
  - **구현을 복사하지 않는다.** 같은 검사가 4곳이 되므로 **`strategy/trade_fill.py`** 에
    한 벌만 둔다 (2026-09-14 사용자 확정 — 그 모듈이 이미 「위치가 유효한가」를 소유한다).
    `studies/` 세 곳(`schedule.py`·`weekly_exit.py`·`offsets.py`)의 기존 구현과
    **메시지 본문 형식을 맞춘다** — 같은 사고의 메시지가 계층마다 다르면 안 된다
  - 🔴 **주의**: `studies/` 세 곳을 이 헬퍼로 «바꾸지 않는다». 계층 의존 방향이
    `studies → strategy` 가 되어 뒤집힌다. 지금은 형식만 맞춘다
- [ ] **A-2** `measure/screening.py`
  - `groupby` 결과의 그룹 크기가 1이 아니면 `ValueError`
  - 메시지에 축 이름·축 값·행 수를 담는다
  - 모듈 docstring 에 「축당 한 행을 요구한다」를 한 줄 추가
- [ ] **A-3** `studies/month_end/schedule.py`
  - `has_entry & ~has_month` 가 하나라도 있으면 `RuntimeError`(「내부 불변조건 위반」 접두사 + 해당 달)
  - 그 뒤에는 `has_month` 분기를 **유지**한다 — 예외가 먼저 나므로 `safe_month_position` 의
    `np.where` 는 그대로 두어도 되고, 지우면 인덱싱이 터지는 자리가 생긴다
- [ ] **A-4** `studies/month_end/runner.py`
  - 기준 칸(`BASE_ENTRY_DAY`, `BASE_EXIT_OFFSET`)이 격자 순회에서 한 번도 도달하지 못했으면
    `RuntimeError` — 「기준 칸의 유효 신호가 0건이라 요약에 진입·제외 건수를 남길 수 없다」
  - `logger.warning` 으로 끝내지 않는다. 요약이 **정상으로 보이는 것**이 이 항목의 문제다

---

### Phase 3 — 값 불변 대조

> 이 계획서의 성립 조건이다. **가드가 현재 실행을 하나도 바꾸지 않아야 한다.**

**작업 내용**:

- [ ] 세 검증과 세 매매를 인자 없이 한 번씩 돌린다 (재수집하지 않는다 — 시세 파일은 그대로 쓴다)

  ```bash
  poetry run python scripts/studies/run_reverse_study.py
  poetry run python scripts/studies/run_option_expiry_study.py
  poetry run python scripts/studies/run_month_end_study.py
  poetry run python scripts/strategy/run_reverse_trading.py
  poetry run python scripts/strategy/run_option_expiry_trading.py
  poetry run python scripts/strategy/run_month_end_trading.py
  ```

- [ ] 새 폴더의 CSV 를 **직전 산출물과 기계로 대조**한다. 눈으로 보지 않는다.
      기준 폴더(2026-09-14 기준 최신):
  - 검증: `storage/results/검증/20260912_225752_reverse` · `.../20260912_212058_option_expiry` · `.../20260912_221404_month_end`
  - 매매: `storage/results/매매/20260912_211908_reverse` · `.../20260912_211914_option_expiry` · `.../20260912_211927_month_end`
  - 대조는 **컬럼 구성과 전 셀 값**을 본다. `summary.json` 은 이 계획서에서 안 바꾸므로 함께 본다
  - 🔴 **한 셀이라도 다르면 멈추고 원인을 밝힌다.** 「가드를 넣었더니 값이 달라졌다」는
    **가드가 실제 경로를 막았다**는 뜻이고, 그러면 지금까지의 산출물이 틀렸을 수 있다
- [ ] 대조 결과(파일 수·행 수·불일치 셀 수)를 진행 로그에 적는다.
      **옛 폴더 이름을 결과 문서에 적지 않는다** — 인용 스캐너가 그것을 인용으로 잡아
      그 폴더가 영구히 묶인다 (`docs/INDEX.md` §5)
- [ ] 이번 실행으로 생긴 새 폴더는 **커밋하지 않는다.** `/clean-results` 로 정리한다

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [ ] `src/verify_lab/CLAUDE.md` 「계층 간 계약」의 매매 산출물 계약에 근거 한 줄 추가 —
      「지수 대상은 무손절 경로만 지나므로 그 경로에 가드가 없으면 상시 노출된다」
- [ ] `docs/COMMANDS.md`: **변경 없음** (실행 방법·CLI 옵션 불변)
- [ ] 자동 포맷 적용: `poetry run black .`
- [ ] 🔴 **「후속 계획서 인계」 절을 채운다** (§8 Notes) — 이 계획서가 바꾼 것 중
      **B~G 가 알아야 할 것**을 적는다: 새로 생긴 가드와 그 예외 타입, 바뀐 시그니처,
      새 테스트 파일, 뒤로 넘긴 결정, **계획서 본문에 적힌 전제 중 깨진 것**.
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
| 가드가 **현재 실행을 막는다** (= 이미 조용히 틀리고 있었다) | Phase 0 의 A-2 확인 명령과 Phase 3 대조가 이것을 먼저 드러낸다. 막히면 고치지 말고 **원인을 조사해 사용자에게 보고**한다 |
| A-1b 헬퍼를 `studies/` 까지 공유하려다 의존 방향이 뒤집힌다 | Phase 2 에 「바꾸지 않는다」를 명시했다. 형식만 맞춘다 |
| Phase 3 재실행으로 산출물 폴더가 6개 늘어난다 | 커밋하지 않고 `/clean-results` 로 정리. 결과 문서를 고치지 않으므로 인용이 깨지지 않는다 |
| A-3·A-4 는 도달 불가 조건이라 테스트가 인위적이다 | 전역 규칙이 「불가능 조건은 `RuntimeError` 로 즉시 인지」를 요구한다. 인위적 입력으로 고정하는 것이 정상이며 `tests/CLAUDE.md` 관용을 따른다 |

## 8) 메모(Notes)

- 감사 원본: 2026-09-14 전체 감사. 이 계획서는 그중 **「비즈니스 로직 오류」·「버그」·「불가능 값 중단 누락」** 카테고리에서 **동작이 조용히 틀리는 것만** 뽑았다
- 같은 감사의 나머지는 B~F 계획서가 담는다. **A 를 먼저 하는 이유**는 B~F 가 코드를 옮기고 지우는 작업이라, 그 전에 「틀리면 멈춘다」를 세워 두어야 옮기다 생긴 사고가 드러나기 때문이다
- **A-2 의 「축당 1행」 판정은 2026-09-14 실측**이다: `grid_candidates` 616행/616유일 · `month_candidates` 96/96 · option_expiry `candidates` 60/60 · reverse `candidates` 576행. 시세를 재수집하면 이 수치는 바뀌지만 **유일성은 구조가 보장**한다
- 감사에서 지목했으나 **이 계획서에서 다루지 않기로 한 것**은 Non-Goals 에 근거와 함께 적어 두었다

### 후속 계획서 인계 (이 계획서를 끝낸 뒤 채운다)

> **B~G 가 실행 전에 이 절을 읽는다.** 이 계획서로 바뀐 것 중 **그쪽 전제에 영향을 주는 것만** 적는다.
> 형식: `무엇이 | 어떻게 바뀌었나 | 어느 계획서가 영향받나`
>
> 아무것도 안 바뀌었으면 **「없음」이라고 적는다** — 비워 두면 「아직 안 썼다」와 구별되지 않는다.

(비어 있음 — 마지막 Phase 에서 채운다)

### 진행 로그 (KST)

- 2026-09-14 12:05: 계획서 작성. 전체 감사 결과 중 「조용히 틀리는」 4건을 A 로 분리
- 2026-09-14 12:40: **Phase 0 재판단 게이트 완료. 네 항목 전부 「한다」.**

  선행 계획서 복기 — `PLAN_[a-g]` 일곱 개가 **전부 🟡 Draft** 이고 「후속 계획서 인계」가 모두
  비어 있다. 순서를 어겨 먼저 실행된 계획서가 없으므로 이 계획서의 Context·Scope 전제는 그대로다.

  | 항목 | 판정 | 근거 |
  | --- | --- | --- |
  | A-1 | **한다** | `strategy/` 의 `get_indexer` 4곳(`month_end_runner.py:185`·`:187` · `option_expiry_runner.py:300`·`:301`)에 `< 0` 검사가 없고, `trade_fill.py:232` 의 검사식이 `entry_position < exit_position < len(frame)` 로 하한이 비어 있다. 판정 보조 명령이 예외 없이 `TradeResult(return_rate=-0.794, reason='기한청산', hold_days=4)` 를 냈다 |
  | A-2 | **한다** | `cell.iloc[0]` 그대로이고 호출처 4곳 전부 축당 1행을 구조로만 보장한다. **현재 값은 바뀌지 않는다** — 아래 대조 참고 |
  | A-3 | **한다** | `schedule.py:230-256` 에 `has_month` 분기가 그대로 있고, 거짓 갈래가 `reasons` 를 덮는 세 `np.where` 어디에도 걸리지 않아 진입 단계 사유가 남는다 |
  | A-4 | **한다** | `runner.py:606` 의 `base_record: dict[str, Any] = {}` 가 `:618-620` 의 `continue` 로 기준 칸 미도달 시 그대로 `**base_record` 로 펼쳐진다. 심각도는 낮지만(현 데이터에서 도달 불가) 수정이 한 줄이라 Non-Goals 로 옮기지 않는다 |

  🔴 **A-2 의 확인 명령이 틀렸다 — 판정은 바뀌지 않지만 근거가 바뀌었다.**
  계획서 Phase 0 의 A-2 명령은 산출물 CSV 를 `('종목','대상','청산 요일','만기월','격자 칸','월','구간')`
  으로 재는데, **그것들은 `screen_candidates` 의 축이 아니다.** 실제 축은 `COL_HORIZON` ·
  `COL_GRID_CELL` · `COL_MONTH_NUMBER` · `COL_EXPIRY_MONTH_NUMBER` 이고, 식별 컬럼은 판정이
  끝난 **뒤에** `_identify` 가 붙인다. 그래서 `reverse` 가 576행 / 12유일로 나와 「이미 조용히
  버려지고 있다」처럼 보이지만 오독이다. 게다가 **출력의 유일성은 누락을 원리적으로 못 잡는다** —
  행이 버려져도 남은 행은 여전히 유일하기 때문이다.

  **올바른 대조는 「입력 집계표 행 수 = 판정표 행 수」이고, 산출물에 그 입력이 그대로 남아 있다.**

  | 입력 집계표 | 행 | 판정표 | 행 |
  | --- | --- | --- | --- |
  | `20260912_221404_month_end/grid.csv` | 616 | `grid_candidates.csv` | 616 |
  | `20260912_221404_month_end/months.csv` | 96 | `month_candidates.csv` | 96 |
  | `20260912_212058_option_expiry/weekly_trade_by_month.csv` | 60 | `candidates.csv` | 60 |
  | `20260912_225752_reverse/statistics.csv` | 576 | `candidates.csv` | 576 |

  네 쌍 모두 일치하므로 **버려지는 행이 없고, 가드를 넣어도 실행이 죽지 않는다.**
  (`reverse` 는 `statistics` 를 단순 보유 초과분과 merge 한 것이 입력이라 merge 가 행을
  늘리거나 줄였다면 수가 갈렸을 것이다. 576 대 576 이 그것까지 함께 배제한다.)

- 2026-09-14 12:50: **계획서 전제 하나를 고쳤다 (사용자 승인).** A-1b 의 예외 타입이
  `ValueError` → **`RuntimeError`** 다.

  계획서는 `studies/` 세 곳과 형식을 맞추려고 `ValueError` 로 적었는데, **그 세 곳과 매매 계층
  네 곳은 조건의 성격이 다르다.** `studies/` 의 `month_exit_schedule`·`weekly_exit_schedule`·
  `assign_offsets` 는 날짜 목록을 **파라미터로 받으므로** 잘못된 값이 외부에서 올 수 있다 —
  입력 검증이고 `ValueError` 가 맞다. 반면 매매 계층 넷은 그 날짜를 **자기가 만든다**:

  - `_collect_entries` — `entry_dates` 는 `month_exit_schedule(trading_days, ...)` 를 지나
    이미 검증됐고, `exit_dates` 는 `trading_days.to_numpy()[safe_exit_position]` 이라 원소가 보장된다
  - `collect_entries` — `dataset`·`cell` 만 받고 **CSV 를 스스로 읽는다.** 호출자에게서
    날짜를 받는 경로가 아예 없다 (호출처 3곳 전수 확인)

  즉 `-1` 은 잘못된 입력이 아니라 **일정 모듈의 버그로만** 생긴다. 전역 `~/.claude/rules/python.md`
  「불가능 조건 처리」가 이것을 `RuntimeError` 로 규정하며, 그 문서는 이 계획서 Context 의
  「영향받는 규칙」에 이미 들어 있다. **`ValueError` 로 고정하면 「외부에서 잘못된 날짜가 올 수
  있다」는 틀린 계약이 테스트에 박힌다.**

  헬퍼 위치도 함께 확정했다 — **`strategy/trade_fill.py`**. 그 모듈이 이미 「위치가 유효한가」를
  소유하고 있고(`_validate` 의 `0 <= entry_position < len(frame)`, A-1a 로 고칠 검사식),
  10줄짜리 함수 하나를 위해 모듈을 늘리지 않는다.
