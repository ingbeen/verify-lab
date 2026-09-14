# Implementation Plan: C — 같은 값을 두 곳에서 정의하는 것을 통합한다

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
**관련 범위**: measure, report, strategy, studies 전체, tests
**관련 문서**: `src/verify_lab/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/docs.md`

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

- [ ] 목표 1: **「측정의 원칙」이 요구하는 값이 검증마다 따로 정의된 것**을 공통 계층으로 올린다 (원칙 11·13·17)
- [ ] 목표 2: **같은 패키지·같은 계층 안의 값 중복**을 없앤다 (같은 파일 두 벌, `report` ↔ `strategy` 레이블 5쌍)
- [ ] 목표 3: **모듈 사이를 문자열 리터럴로 주고받는 컬럼명**을 상수로 만든다
- [ ] 목표 4: **공통 계층 함수의 `__all__` 재노출**을 없앤다 — 계약이 명시적으로 기각한 패턴이다
- [ ] 목표 5: 위가 다시 갈라지지 않도록 **`tests/test_layer_contracts.py` 를 `studies/` 까지 넓힌다**
- [ ] 목표 6: **산출물의 값과 컬럼 이름은 하나도 바뀌지 않는다.** 이름의 정의처만 옮긴다

## 2) 비목표(Non-Goals)

- **검증끼리 겹치는 «검증 고유» 어휘의 통합** — `exit_date`·`entry_close`·`exit_close`·`hold_days`·`baseline`·`_baseline`·`보유 거래일`·`진입 종가`·`청산 종가`·`제외 사유`·`같은 길이 단순 보유` 등이 월말↔옵션 만기일에 두 벌, `PRODUCT_ETF`·`DISPLAY_MULTIPLE`·`저금리(~2021)` 등이 두 배수 검증에 두 벌 있다.
  **판단 기준은 루트 `CLAUDE.md` 가 정한 하나다 — 「이것이 「측정의 원칙」에 적혀 있는가」.**
  적혀 있지 않으면 아직 그 검증의 것이고, 억지로 올리면 `studies/constants.py` 라는 새 공통 계층이 생긴다.
  루트 `CLAUDE.md` 가 「공통 계층은 「검증 중」이 아니라 「확정 후」에 만듭니다」라고 정했으므로 **지금 만들지 않는다.**
  ⇒ 이 판단은 계획서 E 에서 「달력형 검증 공통 어휘를 뽑을 것인가」로 한 번 더 다룬다
- 데드코드·미사용 상수 삭제 — 계획서 D 소관
- 모듈 재배치(`strategy/constants.py` 분리, `dataset_record` 소유자 이동) — 계획서 E 소관
- 산출물 컬럼 이름·값 변경 — 이 계획서는 **정의처만** 옮긴다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

`src/verify_lab/CLAUDE.md` 「상수 관리」가 이렇게 정했다.

> 사용 범위를 기준으로 배치합니다. **계층 간 중복 정의는 발견 즉시 통합합니다.**
> | 2개 이상 계층에서 사용 | `common_constants.py` |
> | 한 계층 내 2개 이상 파일에서 사용 | `<계층>/constants.py` |

2026-09-14 AST 전수 스캔 결과 아래가 남아 있다.

#### C-1. 같은 패키지 안에 같은 상수가 두 벌 🔴

| 값 | 정의처 | 쓰는 쪽 |
| --- | --- | --- |
| `"Price"` | `studies/futures_leverage/constants.py:345` **+** `studies/futures_leverage/position.py:70` | `runner` 는 앞, `position` 은 뒤 |
| `"Interest"` | `constants.py:295` **+** `position.py:75` | 같음 |

값이 우연히 같아서 지금 동작한다. **한쪽만 바뀌면 `runner.py:492` 의 `COL_PRICE` 와 `position.py:275` 가 다른 컬럼을 가리키고 예외는 나지 않는다.**

#### C-2. 「측정의 원칙」이 요구하는 값이 검증마다 따로 정의돼 있다 🔴

| 원칙 | 값 | 정의처 |
| --- | --- | --- |
| 원칙 11 (방향을 가리지 않는다) | `"위"` · `"아래"` | `measure/screening.py:83-84` **+** `strategy/constants.py:357-358` |
| 원칙 13 (평균-비율 어긋남) | `"mean_rate_conflict"` · `"평균-비율 어긋남"` | `studies/month_end/constants.py:365,412` **+** `studies/option_expiry/constants.py:214,319` |
| 원칙 17 (시기 구간) | `"앞 절반"` · `"뒤 절반"` | `strategy/constants.py:397-398` **+** `studies/month_end/constants.py:386-387` **+** `studies/option_expiry/constants.py:221-222` — **세 벌** |

원칙 13 은 **판정 함수만** `measure/statistics.mean_rate_conflict` 로 올라갔고 **컬럼 이름과 레이블은 두 벌로 남았다.** 절반만 통합된 상태다.

원칙 11 의 `"아래"` 는 실제로 두 출처가 동시에 쓰인다 — `strategy/month_end_runner.py:37` 은 `measure.screening` 에서, `strategy/option_expiry_runner.py:42` 는 `strategy.constants` 에서 가져온다. **같은 컬럼의 같은 값이 두 경로로 들어온다.**

#### C-3. `report` 가 소유한 표시 레이블을 `strategy` 가 다시 정의한다 🟠

`src/verify_lab/CLAUDE.md` 가 「`measure`·`report` 가 내는 공통 컬럼은 `report/constants.py` 의 `DISPLAY_*` 를 재사용합니다 — 검증마다 다른 말을 쓰면 두 결과를 나란히 읽을 수 없습니다」라고 정했는데, 다섯 개가 두 벌이다.

| 값 | `report/constants.py` | `strategy/constants.py` |
| --- | --- | --- |
| `"평균(%)"` | `DISPLAY_MEAN:24` | `DISPLAY_MEAN:182` |
| `"최고(%)"` | `DISPLAY_MAX:33` | `DISPLAY_MAX:184` |
| `"최악(%)"` | `DISPLAY_MIN:34` | `DISPLAY_MIN:185` |
| `"표준편차(%)"` | `DISPLAY_STD:35` | `DISPLAY_STDEV:376` |
| `"신호"` | `DISPLAY_SIGNAL_COUNT:20` | `DISPLAY_SIGNAL_COUNT:179` |

#### C-4. 모듈 사이를 리터럴로 주고받는 컬럼명 🟠

`studies/leverage_tracking/` — **생산과 소비가 다른 파일인데 접미사가 f-string 리터럴**이다.

```
breakdown.py:256-257  row[f"{column}Mean"]   / row[f"{column}Median"]
breakdown.py:260      f"{COL_TOTAL_DIVERGENCE}P{int(quantile*100):02d}"
breakdown.py:264-265  f"{COL_REALIZED_MULTIPLE}Median" / f"{COL_REALIZED_MULTIPLE}Count"
runner.py:112-121     (f"{COL_PATH_EFFECT}Mean", …) … (f"{COL_TOTAL_DIVERGENCE}P95", …)
runner.py:231-232     summary[f"{COL_REALIZED_MULTIPLE}Median"] / …Count
```

`TAIL_QUANTILES = (0.05, 0.95)` 를 바꾸면 `runner` 의 `P05`/`P95` 매핑이 **조용히 빈 컬럼**이 된다.

같은 계열로 `krx_futures_collector.py` 의 `"FirstSeen"`·`"LastSeen"` 이 있다 — `collect_contract_catalog` 가 만들고 `collect_futures_history:587-588` 이 리터럴로 읽는다(`continuous.py:73-75` 에는 같은 이름의 상수가 따로 있다).

#### C-5. 같은 긴 문장이 두 벌 🟡

`NOTE_STOP_BASE` — `strategy/month_end_runner.py:94` ≡ `strategy/option_expiry_runner.py:86`, **바이트 단위로 같다.**

#### C-6. 공통 계층 함수를 `studies` 가 `__all__` 로 재노출한다 🔴

`src/verify_lab/CLAUDE.md:263` 이 **이 패턴을 기각안으로 명시**했다.

> | 공유 함수를 매매법 모듈의 `__all__` 로 **재노출**해 옛 경로를 살려 둔다 | 그 경로가 지원되는 한 사슬이 언제든 되살아납니다. **실제로 테스트 하나가 그 경로로 들어와 소유자가 바뀌어도 통과하는 상태였다** |

그런데 `studies/leverage_tracking/breakdown.py:67` 이 정확히 그것을 하고 있다.

```python
# 비중첩 표본 계산은 **공통 계층이 소유한다.** 여기서는 이름만 다시 내보내
# 기존 호출처(`summarize`)와 테스트가 그대로 동작하게 한다
__all__ = ["attach_axes", "max_non_overlapping", "summarize", …]
```

그리고 `tests/test_studies_leverage_breakdown.py:15` 가 **그 경로로 import 한다** — 기각 사유에 적힌 상황이 그대로 일어나 있다.

같은 계열로 `judgeable` 관련 이름을 재노출하는 모듈이 셋이다: `strategy/constants.py:20-26` · `studies/leverage_tracking/constants.py:18` · `studies/futures_leverage/constants.py:25`.

#### C-7. 계약 테스트가 `strategy` 만 본다 🟠

`tests/test_layer_contracts.py:48` 의 `_STRATEGY_SHARED` — 위 C-6 도 C-2 도 이 테스트에 걸리지 않는다. 그래서 계약이 「기각했다」고 적어 둔 패턴이 다른 계층에서 살아남았다.

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「측정의 원칙」 11·13·17, 「공통 계층과 개별 검증의 경계」(**「이것이 측정의 원칙에 적혀 있는가」가 판단 기준**)
- `src/verify_lab/CLAUDE.md` — 「상수 관리」, 「계층 간 계약」 전체, 특히 **매매 계층 구성 계약의 기각안 표**
- `.claude/rules/docs.md` — 용어 대응표(`strategy/` 만 `승률` 을 유지하는 예외)
- `tests/CLAUDE.md`

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [ ] **선행 계획서(A·B) 복기 완료** — 상태와 「후속 계획서 인계」 절을 읽고,
      이 계획서의 전제가 바뀐 것이 있으면 진행 로그에 적었다
- [ ] Phase 0 재판단 게이트를 C-1 ~ C-7 전 항목에 실행하고 「한다 / 안 한다」를 진행 로그에 남겼다
- [ ] 「한다」로 판정된 항목이 전부 구현됐다
- [ ] **AST 중복 스캔 재실행 결과, 이 계획서가 다룬 값의 중복이 0건**임을 확인했다
- [ ] `tests/test_layer_contracts.py` 가 `studies/` 까지 검사한다
- [ ] **산출물 값·컬럼 이름 불변 확인** — Phase 4 의 대조를 수행하고 결과를 진행 로그에 적었다
- [ ] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [ ] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [ ] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [ ] 필요한 문서 업데이트 (`docs/COMMANDS.md` 변경 여부 명시 — 예상: 변경 없음)
- [ ] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (「어디까지 공통으로 올리고 어디부터 검증의 것인가」의 판단 기준을
      `src/verify_lab/CLAUDE.md` 「상수 관리」에 한 문단으로 남긴다)
- [ ] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/measure/constants.py` — 원칙 13·17 의 컬럼/구간 이름을 받는다
- `src/verify_lab/report/constants.py` — 원칙 13 의 표시 레이블을 받는다
- `src/verify_lab/strategy/constants.py` — 중복 5개·`EXPIRY_DIRECTION_*`·`PERIOD_FIRST/SECOND_HALF` 제거, `__all__` 정리
- `src/verify_lab/strategy/periods.py` · `month_end_runner.py` · `option_expiry_runner.py` · `reverse_runner.py` — import 경로 교정, `NOTE_STOP_BASE` 통합
- `src/verify_lab/studies/month_end/constants.py` · `studies/option_expiry/constants.py` — 올라간 이름 제거·재import
- `src/verify_lab/studies/futures_leverage/position.py` — `COL_PRICE`·`COL_INTEREST` 를 `constants` 에서 가져온다
- `src/verify_lab/studies/leverage_tracking/constants.py` · `breakdown.py` · `runner.py` — 접미사 상수화, `__all__` 정리
- `src/verify_lab/studies/futures_leverage/constants.py` — `__all__` 정리
- `src/verify_lab/data/krx_futures_collector.py` — `FirstSeen`·`LastSeen` 상수화
- `tests/test_layer_contracts.py` (확장) · `tests/test_studies_leverage_breakdown.py` (import 경로) · 그 밖에 이동한 이름을 import 하는 테스트
- `src/verify_lab/CLAUDE.md` — 「상수 관리」에 판단 기준 명문화
- `docs/COMMANDS.md`: **변경 없음 예상** (실행 방법·CLI 옵션 불변). Phase 0 에서 재확인

### 데이터/결과 영향

- **없어야 한다.** 이 계획서는 **정의처만** 옮긴다 — 문자열 값은 전부 그대로다
- 산출물 CSV 의 헤더와 값, `summary.json` 모두 불변. Phase 4 에서 대조로 확인한다
- 🔴 **하나라도 달라지면 옮기는 과정에서 값이 바뀐 것**이므로 멈추고 원인을 찾는다

## 6) 단계별 계획(Phases)

### Phase 0 — 재판단 게이트

> **건너뛸 수 없다.**

**작업 내용**:

- [ ] 🔴 **선행 계획서 복기 (이 Phase 의 첫 작업)** — **A·B** 를 비롯해 이미 진행된 계획서를 확인한다:

  ```bash
  for f in docs/plans/PLAN_[a-g]_*.md; do
    echo "=== $f"; grep -m1 '^\*\*상태\*\*' "$f"
    sed -n '/^### 후속 계획서 인계/,/^### 진행 로그/p' "$f"
  done
  ```

  - **B 가 Done 이면** `summary.json` 키가 이미 바뀌었다. B 가 새로 만든 상수
    (`KEY_LABEL`·`KEY_FILE` 등)가 **이 계획서의 중복 목록에 새로 들어왔을 수 있다** —
    아래 스캐너 출력으로 확인한다
  - **A 가 Done 이면** `screening`·`trade_fill`·`month_end` 에 가드가 들어가 있다.
    이 계획서가 그 파일들의 import 를 바꾸므로 **가드를 건드리지 않도록** 주의한다
  - 전제가 깨졌으면 무엇이 어떻게 달라졌는지 적고 Scope 를 조정한다

- [ ] **중복 현황을 다시 뽑는다** (감사 때 쓴 것과 같은 스캐너):

  ```bash
  poetry run python - <<'PY'
  import re, pathlib, collections
  pat = re.compile(r'^([A-Z][A-Z_0-9]*)(?:\s*:\s*Final)?\s*=\s*("(?:[^"\\]|\\.)*")\s*$')
  vals = collections.defaultdict(list)
  for p in sorted(pathlib.Path('src').rglob('*.py')):
      for i, line in enumerate(p.read_text(encoding='utf-8').splitlines(), 1):
          m = pat.match(line)
          if m:
              vals[m.group(2)].append(f"{p}:{i} {m.group(1)}")
  for v, locs in sorted(vals.items()):
      if len(locs) > 1:
          print(v); [print("   ", l) for l in locs]
  PY
  ```

  - 이 목록을 **Context 의 표와 대조**한다. 사라진 항목은 이미 고쳐진 것이므로 그 항목을 Non-Goals 로 옮긴다
  - **새로 생긴 항목이 있으면** 같은 판단 기준(「측정의 원칙에 적혀 있는가」)으로 분류해 Scope 에 넣는다

- [ ] **C-1 재판단**: `grep -n "COL_PRICE\|COL_INTEREST" src/verify_lab/studies/futures_leverage/*.py`
  - **한다**: `position.py` 와 `constants.py` 양쪽에 정의가 있을 때
- [ ] **C-2 재판단**: 위 스캐너 출력에 `"위"`·`"아래"`·`"앞 절반"`·`"mean_rate_conflict"` 가 남아 있는가
  - **한다**: 남아 있을 때. **안 한다**: 이미 하나로 줄었을 때
- [ ] **C-3 재판단**: `"평균(%)"`·`"최고(%)"`·`"최악(%)"`·`"표준편차(%)"`·`"신호"` 가 두 곳에 있는가
  - 🔴 **주의**: `.claude/rules/docs.md` 용어 대응표가 **`strategy/` 만 `승률` 을 유지**하는 예외를 두었다.
    `DISPLAY_WIN_RATE`(`승률(%)`)는 **통합 대상이 아니다** — 뜻이 다른 말이다.
    위 다섯만 통합한다
- [ ] **C-4 재판단**: `grep -rn '}Mean\|}Median\|}Count\|}P05\|}P95' src/verify_lab/`
- [ ] **C-5 재판단**: `grep -rn "NOTE_STOP_BASE" src/verify_lab/strategy/`
- [ ] **C-6 재판단**: `grep -rn "^__all__" src/verify_lab/studies/ src/verify_lab/strategy/constants.py`
  - `max_non_overlapping` 이 `breakdown.__all__` 에 있고 테스트가 그 경로로 들어오는지 확인:
    `grep -n "breakdown import" -A6 tests/test_studies_leverage_breakdown.py`
- [ ] **C-7 재판단**: `grep -n "_STRATEGY_SHARED\|_SOURCE_ROOT" tests/test_layer_contracts.py`
- [ ] 🔴 **`studies` 교차 import 현황을 재확인한다** (2026-09-14 기준 **0건**):

  ```bash
  for d in reverse option_expiry month_end leverage_tracking futures_leverage usdkrw_equivalence; do
    grep -rn "from verify_lab.studies\." src/verify_lab/studies/$d/ | grep -v "studies\.$d\." ;
  done
  ```

  0건이면 C-7 의 새 테스트는 **현재 상태를 고정**하는 것이고, 1건이라도 있으면
  **그 자체가 발견**이므로 먼저 보고한다
- [ ] 항목별 판정을 **진행 로그에 표로** 남긴다

---

### Phase 1 — 계약 테스트를 먼저 넓힌다(레드 허용)

**작업 내용**:

- [ ] `tests/test_layer_contracts.py` 에 추가
  - **소유자 단일성** — `"위"`·`"아래"`·`"앞 절반"`·`"뒤 절반"`·`"mean_rate_conflict"`·`"평균-비율 어긋남"` 을
    **직접 정의하는 파일이 각각 하나**임을 검사한다. 기존 `_files_defining` 헬퍼를 재사용한다
  - **`report` 레이블 재정의 금지** — `report/constants.py` 가 정의한 `DISPLAY_*` 문자열을
    다른 파일이 직접 정의하지 않는다. **`승률(%)` 은 예외 목록에 명시**한다
  - **같은 패키지 두 벌 금지** — `studies/<검증>/` 안에서 한 값이 두 파일에 정의되지 않는다
  - **공통 계층 함수 재노출 금지** — `studies/**`·`strategy/**` 의 `__all__` 에
    `measure`·`report` 에서 import 한 이름이 들어가지 않는다
  - **검증끼리 import 금지** — `studies/<A>/` 가 `studies/<B>/` 를 import 하지 않는다
    (`_imported_strategy_modules` 와 같은 방식으로 네 가지 import 형태를 전부 본다)
- [ ] 이 테스트들이 **지금 실패하는지 확인**한다. 실패하지 않으면 테스트가 잘못 짜인 것이다

---

### Phase 2 — 「측정의 원칙」이 요구하는 값을 공통 계층으로 올린다(그린 유지)

**작업 내용**:

- [ ] **C-2a (원칙 11)** `"위"`·`"아래"` 를 `measure/screening.py` 의 `DIRECTION_UP`·`DIRECTION_DOWN` 하나로
  - `strategy/constants.py:357-358` 의 `EXPIRY_DIRECTION_UP`·`EXPIRY_DIRECTION_DOWN` 제거
  - `strategy/option_expiry_runner.py` 가 `measure.screening` 에서 가져오게 한다
    (`month_end_runner.py` 는 이미 그렇게 하고 있다 — **그쪽에 맞춘다**)
- [ ] **C-2b (원칙 13)** `COL_MEAN_RATE_CONFLICT` 를 `measure/constants.py` 로,
      `DISPLAY_MEAN_RATE_CONFLICT` 를 `report/constants.py` 로
  - 판정 함수는 이미 `measure/statistics.mean_rate_conflict` 다. **이름만 따라 올린다**
  - 두 검증 `constants.py` 는 재정의 대신 import
- [ ] **C-2c (원칙 17)** `"앞 절반"`·`"뒤 절반"` 을 **한 곳**으로
  - 🔴 **어디로 올릴지 결정이 필요하다.** 세 후보와 근거:
    - `measure/constants.py` — 원칙 17 은 「모든 매매법」에 요구하므로 측정 공통이 자연스럽다.
      **`MIN_SAMPLE_PER_CELL`·`COL_JUDGEABLE` 이 이미 같은 이유로 여기 있다** ← 권장
    - `report/constants.py` — 표시 문자열이라는 성격에 맞지만, `measure` 쪽 `judgeable` 과 자리가 갈린다
    - 그대로 셋 — 통합 안 함
  - **권장안(`measure/constants.py`)으로 진행하되, 다르게 판단했다면 그 근거를 진행 로그에 적는다**
  - `strategy/constants.py` 의 `PERIOD_FIRST_HALF`·`PERIOD_SECOND_HALF` 와
    두 검증의 `DISPLAY_PERIOD_EARLY`/`LATE`·`DISPLAY_TIME_HALF_EARLY`/`LATE` 를 그 하나로 모은다
  - ⚠️ **`strategy/constants.PERIODS` 튜플과 `RECENT_YEARS` 는 매매 계층의 구성이라 그대로 둔다** —
    올리는 것은 **문자열 값**이지 구간 목록이 아니다

---

### Phase 3 — 같은 계층·같은 패키지 안의 중복을 없앤다(그린 유지)

**작업 내용**:

- [ ] **C-1** `studies/futures_leverage/position.py:70,75` 의 `COL_PRICE`·`COL_INTEREST` 정의를 지우고
      `constants.py` 에서 import
  - 🔴 `position.py` 에는 `COL_EQUITY`·`COL_EXPOSURE`·`COL_CONTRACT_COUNT`·`COL_EFFECTIVE_LEVERAGE`·`COL_REBALANCED` 도 있다.
    **이들이 `constants.py` 에도 있는지 확인**해 있으면 함께 통합하고, 없으면 그대로 둔다
    (「1개 파일에서만 사용 → 해당 파일 상단」 규칙에 맞다)
- [ ] **C-3** `strategy/constants.py` 의 `DISPLAY_MEAN`·`DISPLAY_MAX`·`DISPLAY_MIN`·`DISPLAY_STDEV`·`DISPLAY_SIGNAL_COUNT` 를
      `report/constants.py` 에서 import 로 바꾼다
  - ⚠️ `DISPLAY_STDEV` 와 `DISPLAY_STD` 는 **이름이 다르고 값이 같다.** 이름을 `report` 쪽(`DISPLAY_STD`)으로 맞추고
    `strategy` 안의 사용처를 전부 고친다 — 이름을 남겨 두면 「두 값이 같다」를 매번 확인해야 한다
- [ ] **C-4a** `studies/leverage_tracking/constants.py` 에 접미사 상수를 둔다
      (예: `SUFFIX_MEAN`·`SUFFIX_MEDIAN`·`SUFFIX_COUNT`, 분위 라벨은 `TAIL_QUANTILES` 에서 유도하는 함수 하나)
  - `breakdown.py` 와 `runner.py` 가 **같은 함수/상수**로 이름을 만들게 한다
  - 🔴 `TAIL_QUANTILES` 를 바꿔도 양쪽이 함께 따라오는 형태여야 한다. 지금은 `runner` 가 `P05`·`P95` 를 손으로 적는다
- [ ] **C-4b** `data/krx_futures_collector.py` 의 `"FirstSeen"`·`"LastSeen"` 을 파일 상단 상수로
  - `continuous.py:73-75` 에 같은 이름의 상수가 **따로** 있다. 두 모듈이 같은 표를 주고받지 않는다면
    각자 두는 것이 규칙에 맞다 — **먼저 확인하고**, 주고받는다면 한 곳으로 모은다
- [ ] **C-5** `NOTE_STOP_BASE` 를 `strategy/constants.py` 로 올리고 두 runner 가 import
  - 같은 자리에 `NOTE_ENTRY`·`NOTE_EXIT` 도 있는데 **이들은 매매법마다 내용이 다르다.**
    올리는 것은 **바이트 단위로 같은 것 하나**다
- [ ] **C-6** 재노출 제거
  - `studies/leverage_tracking/breakdown.py:67` 의 `__all__` 에서 `max_non_overlapping` 제거
  - `tests/test_studies_leverage_breakdown.py:15` 의 import 를 `verify_lab.measure.statistics` 로 교정
  - `strategy/constants.py:20-26` · `studies/leverage_tracking/constants.py:18` ·
    `studies/futures_leverage/constants.py:25` 의 `__all__` 재노출 정리
  - 🔴 **재노출을 지우면 그 이름을 그 경로로 가져오던 곳이 전부 깨진다.** 먼저 찾는다:

    ```bash
    grep -rn "from verify_lab.strategy.constants import" -A30 src scripts tests | grep -n "JUDGEABLE\|MIN_SAMPLE_PER_CELL"
    grep -rn "leverage_tracking.constants import\|futures_leverage.constants import" -A30 src scripts tests | grep -n "JUDGEABLE"
    ```

    깨지는 곳은 **소유자(`measure/constants.py`·`report/constants.py`)에서 직접** 가져오게 고친다

---

### Phase 4 — 값 불변 대조

**작업 내용**:

- [ ] Phase 0 의 중복 스캐너를 다시 돌려 **이 계획서가 다룬 값이 목록에서 사라졌는지** 확인한다
- [ ] 여섯 실행(검증 3 + 매매 3)을 인자 없이 돌린다. 재수집하지 않는다
- [ ] 새 산출물의 **CSV 헤더와 전 셀 값**, `summary.json` 을 직전 산출물과 기계로 대조한다
      (기준 폴더는 계획서 A Phase 3 과 같다. 계획서 B 를 먼저 했다면 **B 가 낸 산출물**이 기준이다)
- [ ] 🔴 **한 셀이라도 다르면 멈춘다.** 이 계획서는 정의처만 옮기므로 값이 달라질 이유가 없다
- [ ] 대조 결과를 진행 로그에 적고, 새 폴더는 커밋하지 않고 `/clean-results` 로 정리한다

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [ ] `src/verify_lab/CLAUDE.md` 「상수 관리」에 **판단 기준**을 명문화한다
  - 「어디까지 공통이고 어디부터 그 검증의 것인가」 = 루트 `CLAUDE.md` 의 「이것이 「측정의 원칙」에
    적혀 있는가」. 원칙 11·13·17 의 값이 공통 계층에 있는 이유를 예시로 든다
  - 비목표로 남긴 「검증 고유 어휘 두 벌」이 **왜 지금 통합 대상이 아닌지**도 함께 적는다 —
    적지 않으면 다음 사람이 같은 판단을 처음부터 한다
- [ ] `docs/COMMANDS.md`: 변경 여부 확정해 적는다 (예상: 변경 없음)
- [ ] 자동 포맷 적용: `poetry run black .`
- [ ] 🔴 **「후속 계획서 인계」 절을 채운다** (§8 Notes) — **D~G 가 알아야 할 것**을 적는다:
      **어느 이름이 어디로 옮겨갔는지**(D 가 지울 후보를 판정할 때 필요), 새로 죽은 정의,
      새 계약 테스트가 무엇을 막는지(E 가 파일을 옮길 때 걸린다),
      **E 로 넘긴 「달력형 공통 어휘」 결정의 현재 상태**, 깨진 전제.
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
| import 를 옮기다 **순환 import** 가 생긴다 | 올리는 방향이 전부 `studies/strategy → measure/report` 로 **의존 방향과 같다.** 반대로 가는 이동은 이 계획서에 없다 |
| 재노출 제거로 테스트·스크립트가 대량으로 깨진다 | Phase 3 C-6 에 «먼저 찾는» 명령을 두었다. 깨지는 곳은 소유자에서 직접 가져오게 고친다 |
| `DISPLAY_STDEV` → `DISPLAY_STD` 개명이 산출물 컬럼을 바꾼다 | **값은 같다**(`"표준편차(%)"`). 바뀌는 것은 파이썬 이름뿐이며 Phase 4 대조가 확인한다 |
| 「어디까지 올릴 것인가」가 다음 사람에게 다시 모호해진다 | 마지막 Phase 에서 판단 기준을 `src/verify_lab/CLAUDE.md` 에 명문화한다. **이것이 이 계획서의 근거 승격 핵심**이다 |
| 새 계약 테스트가 정당한 예외까지 막는다 | `승률(%)` 예외를 명시했다. 다른 예외가 나오면 **테스트에 이유와 함께** 적는다 |

## 8) 메모(Notes)

- **왜 B 다음인가**: B 가 `summary.json` 키를 손대므로, C 가 먼저 상수를 옮기면 두 변경이 같은 줄에서 겹친다
- **C 가 하는 일은 「값 이동」이 아니라 「정의처 이동」이다.** 산출물이 한 글자도 바뀌지 않는 것이 성공 조건이다
- 2026-09-14 실측: `studies` 끼리 교차 import **0건**, `"앞 절반"` **3벌**, `"위"`/`"아래"` **2벌이 동시에 사용 중**
- C-2c 의 「어디로 올릴 것인가」는 **결정 사항**이다. 권장안을 적었으나 실행 세션이 다르게 판단할 수 있고, 그때는 근거를 남기면 된다

### 후속 계획서 인계 (이 계획서를 끝낸 뒤 채운다)

> **D~G 가 실행 전에 이 절을 읽는다.** 이 계획서로 바뀐 것 중 **그쪽 전제에 영향을 주는 것만** 적는다.
> 형식: `무엇이 | 어떻게 바뀌었나 | 어느 계획서가 영향받나`
>
> 🔴 **「이름이 어디로 옮겨갔는가」는 반드시 적는다** — D 가 「미사용」을 판정할 때,
> E 가 파일을 옮길 때, G 가 문서를 고칠 때 전부 이 목록을 본다.
> 아무것도 안 바뀌었으면 **「없음」이라고 적는다**.

(비어 있음 — 마지막 Phase 에서 채운다)

### 진행 로그 (KST)

- 2026-09-14 12:05: 계획서 작성. 감사의 「상수화 필요」·「불필요한 상수(중복)」·「불필요한 함수(재노출)」를 C 로 묶음
