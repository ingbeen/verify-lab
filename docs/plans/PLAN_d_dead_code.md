# Implementation Plan: D — 죽은 정의와 거짓말하는 주석을 걷어낸다

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

**작성일**: 2026-09-14 12:05
**마지막 업데이트**: 2026-09-14 22:43
**관련 범위**: common_constants, data, strategy, studies/month_end, studies/futures_leverage, studies/leverage_tracking, tests
**관련 문서**: `src/verify_lab/CLAUDE.md`, 전역 `~/.claude/rules/python.md` 「미사용 판정에는 「왜 안 쓰이는가」가 함께 필요하다」

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

- [x] 목표 1: **쓰이지 않는 상수를 「왜 안 쓰이는가」로 분류한 뒤** 지울 것은 지우고 연결할 것은 연결한다
- [x] 목표 2: **설명하던 대상이 사라진 고아 주석**을 걷어낸다 (수집기 3파일 4건)
- [x] 목표 3: **존재하지 않는 컬럼을 설명하는 docstring** 을 현재 사실에 맞춘다
- [x] 목표 4: 죽은 표시 레이블이 **다시 조용히 쌓이지 않게** 하는 테스트를 붙인다
- [x] 목표 5: **산출물의 값과 컬럼은 하나도 바뀌지 않는다**
- [x] 목표 6: **선행 계획서가 D 로 넘긴 두 건**을 처리한다 (2026-09-14 21:45 사용자 승인) —
      A 의 「증명 가능하게 죽은 조건 3곳」과 C 의 「연결 누락 1건」. 아래 D-5·D-6

## 2) 비목표(Non-Goals)

아래 셋은 **감사에서 지목했으나 검토 끝에 하지 않기로 한다.** 다음 세션이 같은 분석을 반복하지 않도록 근거를 남긴다.

- **`month_end/constants.EXECUTION_ROLES` 삭제** — `src` 에서 안 쓰이지만
  `tests/test_studies_month_end_execution.py:159` 가 **「모든 대상의 집행 역할이 이 셋 중 하나」**라는
  불변조건을 이 상수로 검사한다. 테스트가 정당한 사용처다. **남긴다**
- **`utils/result_citations.existing_result_dirs` 제거** — 계획서 A 의 Non-Goals 와 같은 이유
  (`tests/test_result_citations.py` 가 6개 테스트로 이 이름을 직접 검증한다)
- **`report/tables._sorted_cells` 인라인화** — 호출처가 `_sorted_single_basis_cells` 하나뿐인
  간접층이지만, 「정렬」과 「기준 하나 검사」는 서로 다른 책임이고 합치면 함수 하나가 두 일을 한다.
  **이득이 없다**
- 중복 정의 통합 — 계획서 C 소관. **C 를 먼저 하면 이 계획서의 대상 일부가 자연히 사라진다**
- 문서(`docs/**`)의 낡은 수치·과거 서술 — 계획서 F 소관

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

전역 `~/.claude/rules/python.md` 가 이렇게 정했다.

> 참조를 전수 집계해 호출되지 않는 정의를 찾았다면, **그 목록을 그대로 지우면 안 된다.** 두 종류가 섞여 있다.
> | 필요 없어서 | **지운다** |
> | 결론이 난 축의 잔여물 | **지운다** |
> | **연결을 빠뜨려서** | **쓰게 만든다** — 표나 코드가 같은 뜻의 하드코딩 문자열을 쓰고 있다 |

2026-09-14 AST 전수 조사(정의 파일 밖 참조 0건)에서 나온 목록을 그 셋으로 분류했다.

#### D-1. 쓰이지 않는 상수 — 분류와 처리

| 상수 | 위치 | 왜 안 쓰이나 | 처리 |
| --- | --- | --- | --- |
| `DOCS_DIR` | `common_constants.py:54` | **결론난 축의 잔여물.** 주석은 `utils/result_citations.py` 가 쓴다고 적었으나 그 모듈은 `root` 를 **인자로** 받고, 모듈 docstring 은 「루트는 `docs/` 가 아니라 **저장소 전체**다」라고 명시한다 — 스캔 범위가 넓어지면서 이 상수가 남았다 | **지운다** (주석이 거짓말을 하고 있어 더 나쁘다) |
| `BASELINE_MONTH_ANY` | `studies/month_end/constants.py:374` | **필요 없어서.** 월말의 기준선은 하나뿐이라 산출물에 이름을 실을 자리가 없다 (기준선이 둘인 옵션 만기일만 `COL_BASELINE_KIND` 로 라벨링한다) | **지운다** |
| `BASELINE_MATCHED_LENGTH` | `studies/month_end/constants.py:375` | **잔여물.** 월말에는 「같은 길이 단순 보유」 기준선 자체가 없다. 옵션 만기일 것의 복사본이다 | **지운다** |
| `COL_BASELINE_KIND` · `DISPLAY_BASELINE_KIND` | `studies/month_end/constants.py:362, 411` | **잔여물.** `COLUMN_LABELS` 에만 등장하고 실제 CSV 7개 헤더에 `기준선` 컬럼이 없다 (2026-09-14 확인) | **지운다** |
| `COL_CONVERGED_MONTHS` · `DISPLAY_CONVERGED_MONTHS` | `studies/month_end/constants.py:318, 407` | 🟡 **판단 필요.** 값 자체는 계산돼 `summary.json` 의 `converged_with_neighbour_months` 로 나간다. 표 컬럼으로 낼 자리가 없어 레이블만 남았다 | Phase 0 에서 결정 (아래) |
| `DISPLAY_TARGET_MULTIPLE` | `studies/futures_leverage/constants.py:256` | 🟡 **판단 필요.** `integer_contracts.csv` 는 `배수`(=`DISPLAY_MULTIPLE`, 목표 배수)와 `실제 배수` 두 열을 갖는다. 「목표 배수」가 더 정확한 이름이지만 지금은 `배수` 로 나간다 | Phase 0 에서 결정 (아래) |

> **위 여섯에는 「연결 누락」이 없다**: 세 번째 유형은 「표나 코드가 **같은 뜻의 하드코딩 문자열**을 쓰고 있을 때」다.
> 위 여섯은 그런 하드코딩 짝이 없다 — 컬럼 자체가 존재하지 않는다. **Phase 0 에서 확인했다** (2026-09-14 21:42).
>
> 🔴 **그러나 「이 계획서에 연결 누락이 없다」는 틀렸다.** C 가 범위 밖에서 한 건을 찾아 D 로 넘겼다 — 아래 **D-6**.
> 그것이 D-1 표에 없는 이유는 이 표가 **「쓰이지 않는 상수」**만 담기 때문이다. D-6 의 상수는
> 이미 쓰이고 있고 **한 자리만 리터럴로 우회**한다 — 전수 스캔으로는 잡히지 않는 종류다.

> 🔴 **Phase 0 스캐너는 위 여섯 중 넷을 못 잡는다** (2026-09-14 21:42 실측). `own <= 1` 조건 때문에
> **자기 파일의 `COLUMN_LABELS` 에 한 번 등장하는 이름**(`COL_BASELINE_KIND`·`DISPLAY_BASELINE_KIND`·
> `COL_CONVERGED_MONTHS`·`DISPLAY_CONVERGED_MONTHS`)이 `own == 2` 가 되어 통과한다.
> **죽은 레이블이 쌓이는 것과 정확히 같은 구멍이다**(D-4) — 사전에 키를 얹는 것만으로 「쓰인다」가 된다.
> 스캐너 출력은 4건이고 D-1 표는 6건이므로, **대조는 개별 `grep` 으로 한다.**

#### D-2. 설명하던 대상이 사라진 고아 주석 — 4건

상수를 `data/constants.py` 로 옮기면서 **설명 문장만 제자리에 남았다.**

| 위치 | 남은 주석 | 뒤에 오는 것 |
| --- | --- | --- |
| `data/pykrx_collector.py:70-71` | `# 조회 시작일 형식. pykrx 가 요구하는 표기다` | **아무 정의도 없음** (빈 줄 뒤 다른 상수) |
| `data/etn_collector.py:80-81` | `# 조회 인자의 날짜 형식` | **없음** |
| `data/krx_futures_collector.py:129-130` | `# 조회 인자의 날짜 형식` | **없음** |
| `data/krx_futures_collector.py:131-132` | `# 응답 날짜 형식. 세션 표기를 뗀 뒤의 모양이다` | **없음** |

같은 계열로 **주석이 엉뚱한 상수에 붙은 것**이 하나 더 있다 — `data/pykrx_collector.py:54-56`.
`KRX_COLUMN_MAP` 을 설명하는 두 줄 뒤에 `KRX_CLOSE_COLUMN` 정의가 끼어들어, **읽으면 설명이 그 상수 것으로 보인다.**

#### D-3. 존재하지 않는 컬럼을 설명하는 docstring

`strategy/periods.py:236-242` — `to_summary_frame` 이 `제외` 컬럼의 `0.0` 문제를 다섯 줄로 설명한다. 그런데 그 컬럼은 계약(`src/verify_lab/CLAUDE.md:296` 「`제외` 컬럼을 성적표에 두지 않는다」)에 따라 **이미 제거**됐고 `COUNT_COLUMNS` 에도 없다. **없는 것을 근거로 든 설명**이 남아 있다.

#### D-4. 죽은 레이블이 조용히 쌓이는 구조

`report/tables.to_display_columns:530` 은 **「한글 이름 없는 컬럼」은 막지만 「쓰이지 않는 레이블」은 통과**시킨다.

```python
missing = [column for column in table.columns if column not in labels]   # ← 이 방향만 본다
```

가드가 한쪽 방향만 보므로 D-1 의 죽은 레이블 6개가 아무 신호 없이 쌓였다.
**런타임에서 양방향으로 막을 수는 없다** — 표마다 컬럼 구성이 달라 사전은 언제나 상위집합이어야 한다.
그래서 **테스트로** 잡는다.

#### D-5. 증명 가능하게 죽은 조건 3곳 — A 가 넘긴 것

`studies/month_end/schedule.py` 의 249행이 A 에서 새로 생겼다.

```python
broken = has_entry & ~has_month
if broken.any():
    raise RuntimeError("내부 불변조건 위반: 진입일이 있는데 그 달이 거래일 목록에 없습니다: ...")
```

이 가드를 지난 뒤로는 **모든 행에서 `has_entry ⇒ has_month`** 이므로 `has_entry & has_month == has_entry` 다.
그런데 바로 아래 세 줄이 여전히 `& has_month` 를 달고 있다 (259·260·262행).

| 행 | 현재 | 죽은 이유 |
| --- | --- | --- |
| 259 `out_of_range` | `has_entry & has_month & (...)` | 가드가 `has_entry & ~has_month` 를 이미 끊었다 |
| 260 `no_holding` | `has_entry & has_month & ~out_of_range & (...)` | 같음 |
| 262 `usable` | `has_entry & has_month & ~out_of_range & ~no_holding` | 같음 |

⚠️ **233행 `safe_month_position` 의 `np.where(has_month, ...)` 는 지우면 안 된다** (A 의 경고).
그 `has_month` 는 **가드보다 «앞»에 있어** 아직 죽지 않았고, `~has_entry` 행의 인덱싱이 거기서 터진다.

**빼는 대신 「왜 뺐는가」를 주석으로 남긴다.** 조건이 사라지면 그 세 줄만 읽는 사람은
`has_month` 가 어디서 보장되는지 알 수 없다.

#### D-6. 연결 누락 1건 — C 가 넘긴 것

`studies/leverage_tracking/runner.py:470` 이 판정가능 컬럼을 **리터럴 `"예"`** 로 거른다.

```python
outputs.divergence.loc[outputs.divergence[DISPLAY_JUDGEABLE] == "예", columns]
```

`measure/constants.py:53` 의 `JUDGEABLE_YES` 가 그 값의 소유자이고 `measure/statistics.py:239` 는
그것을 쓴다. **전역 `~/.claude/rules/python.md` 가 「지우지 말고 쓰게 만든다」로 정한 세 번째 유형**이다.
값이 같으므로 산출물은 바뀌지 않는다.

**같은 파일 320행의 `"예"` 는 건드리지 않는다** — `DISPLAY_DISTRIBUTION_MEASURED`(분배금을
실측했는가)라 다른 질문이고, 거짓 쪽이 `"아니오 (ETN — 분배금 없음)"` 라 `JUDGEABLE_NO` 와도 다르다.
**같은 글자라고 같은 상수가 아니다.**

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 「계획서 규약 — 이 프로젝트의 설정」 절
- 전역 `~/.claude/rules/python.md` — **「미사용 판정에는 「왜 안 쓰이는가」가 함께 필요하다」** (이 계획서의 뼈대)
- 전역 `~/.claude/CLAUDE.md` — 「주석은 코드가 못 하는 말만 한다」, 「수술적 변경」
  (**사전에 존재하던 데드 코드는 사용자 요청 없이 삭제하지 않는다** — 이 계획서가 그 요청에 해당한다)
- `src/verify_lab/CLAUDE.md` — 「상수 관리」, 「내부/출력 분리」
- `tests/CLAUDE.md`

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] **선행 계획서(A·B·C) 복기 완료** — 상태와 「후속 계획서 인계」 절을 읽고,
      이 계획서의 삭제 목록이 여전히 유효한지 판정해 진행 로그에 적었다
- [x] Phase 0 재판단 게이트를 D-1 ~ D-4 전 항목에 실행하고 「지운다 / 연결한다 / 남긴다」를 진행 로그에 표로 남겼다
- [x] 「지운다」로 판정된 정의가 전부 사라졌고, 「연결한다」로 판정된 것은 실제로 쓰인다
- [x] 고아 주석 4건 + 오배치 주석 1건 정리
- [x] `to_summary_frame` docstring 이 현재 컬럼 구성을 설명한다
- [x] 죽은 레이블 감시 테스트 추가
- [x] **D-5** 죽은 조건 3곳을 빼고 「가드가 보장한다」를 주석으로 남겼다 (233행 `np.where` 는 그대로)
- [x] **D-6** `"예"` 리터럴이 `JUDGEABLE_YES` 로 바뀌었다 (320행은 그대로)
- [x] **미사용 전수 스캔 재실행 결과**를 진행 로그에 적었다 (남은 것이 있으면 그 근거도)
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` 변경 여부 명시 — 예상: 변경 없음)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (「`to_display_columns` 의 가드는 한 방향뿐이라 죽은 레이블은 테스트가 잡는다」를
      `src/verify_lab/CLAUDE.md` 「내부/출력 분리」에 남긴다)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/common_constants.py` — `DOCS_DIR` 제거
- `src/verify_lab/studies/month_end/constants.py` — 죽은 상수 4~6개 제거, `COLUMN_LABELS` 정리
- `src/verify_lab/studies/futures_leverage/constants.py` — `DISPLAY_TARGET_MULTIPLE` 처리
- `src/verify_lab/data/pykrx_collector.py` · `etn_collector.py` · `krx_futures_collector.py` — 고아·오배치 주석
- `src/verify_lab/strategy/periods.py` — `to_summary_frame` docstring
- `src/verify_lab/studies/month_end/schedule.py` — D-5 죽은 조건 3곳
- `src/verify_lab/studies/leverage_tracking/runner.py` — D-6 연결 누락 1곳
- `tests/test_common_constants.py` — `DOCS_DIR` 를 검증하는 테스트가 있으면 함께
- `tests/` 신규 또는 기존 — 죽은 레이블 감시
- `src/verify_lab/CLAUDE.md` — 근거 승격
- `docs/COMMANDS.md`: **변경 없음 예상**. Phase 0 에서 재확인

### 데이터/결과 영향

- **없어야 한다.** 지우는 것은 전부 「어디에도 도달하지 않는 정의」다
- `COLUMN_LABELS` 에서 키를 빼도 **`to_display_columns` 는 사전이 상위집합이면 통과**하므로 산출물이 바뀌지 않는다
- Phase 3 에서 대조로 확인한다

## 6) 단계별 계획(Phases)

### Phase 0 — 재판단 게이트

> **건너뛸 수 없다.** 특히 이 계획서는 **지우는** 작업이라 오판의 대가가 크다.

**작업 내용**:

- [x] 🔴 **선행 계획서 복기 (이 Phase 의 첫 작업)** — 이 계획서는 **지우는** 작업이라
      선행 복기가 특히 중요하다. 앞선 계획서가 「미사용」의 정의를 바꿔 놓았을 수 있다:

  ```bash
  for f in docs/plans/PLAN_[a-g]_*.md; do
    echo "=== $f"; grep -m1 '^\*\*상태\*\*' "$f"
    sed -n '/^### 후속 계획서 인계/,/^### 진행 로그/p' "$f"
  done
  ```

  - 🔴 **C 가 Done 이면 그 인계 절의 「어느 이름이 어디로 옮겨갔는가」를 반드시 읽는다.**
    C 가 중복을 통합하면서 **새로 미사용이 된 정의**가 생겼을 수 있고, 반대로
    **이 계획서의 삭제 후보가 C 에서 이미 사라졌을 수도** 있다
  - **B 가 Done 이면** `summary.json` 키가 바뀌어 `KEY_PATH` 같은 이름이 이미 없어졌을 수 있다
  - **A 가 Done 이면** 새 가드가 상수를 쓸 수 있다 — 지우기 전에 `grep` 으로 확인한다
  - 전제가 깨졌으면 Context 의 D-1 표를 **아래 스캐너 출력으로 다시 만든다**

- [x] **미사용 전수 스캔을 다시 돌린다** (감사 때 쓴 것과 같은 스캐너):

  ```bash
  poetry run python - <<'PY'
  import ast, pathlib, re
  src = list(pathlib.Path('src').rglob('*.py'))
  scripts = list(pathlib.Path('scripts').rglob('*.py'))
  tests = list(pathlib.Path('tests').rglob('*.py'))
  texts = {p: p.read_text(encoding='utf-8') for p in src + scripts + tests}
  defs = []
  for p in src:
      for node in ast.parse(texts[p]).body:
          if isinstance(node, ast.Assign):
              defs += [(t.id, p, node.lineno) for t in node.targets if isinstance(t, ast.Name)]
          elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
              defs.append((node.target.id, p, node.lineno))
  for name, p, ln in defs:
      pat = re.compile(rf'\b{re.escape(name)}\b')
      own = len(pat.findall(texts[p]))
      other = sum(len(pat.findall(texts[q])) for q in src if q != p)
      in_scripts = sum(len(pat.findall(texts[q])) for q in scripts)
      in_tests = sum(len(pat.findall(texts[q])) for q in tests)
      if other == 0 and in_scripts == 0 and own <= 1:
          print(f"NEVER  {name:38} {p}:{ln}  (테스트 {in_tests}회)")
  PY
  ```

  - 출력이 **Context 의 표와 같은지** 대조한다
  - **테스트 참조가 있는 항목은 지우기 전에 그 테스트를 읽는다** — `EXECUTION_ROLES` 처럼
    불변조건을 담고 있으면 **남긴다** (Non-Goals 에 이미 한 건 있다)
  - 🔴 **실측 결과 스캐너 출력은 4건, D-1 표는 6건이다.** 차이의 원인과 대조 방법은
    Context 의 D-1 표 아래 인용에 적었다 — **개별 `grep` 으로 대조했다**

- [x] **「연결 누락」이 아닌지 항목마다 확인한다.** 전역 규칙이 요구하는 판정이다.
      각 상수의 값(문자열)이 **다른 곳에 하드코딩돼 있는지** 본다:

  ```bash
  grep -rn "그 달 아무 날 진입\|같은 길이 단순 보유\|앞당김 수렴 달 수\|목표 배수\|기준선" src/verify_lab/studies/month_end/ src/verify_lab/studies/futures_leverage/
  ```

  하드코딩 짝이 나오면 **지우지 말고 연결한다** (그것이 세 번째 유형이다)

  - 🔴 **실측 결과 히트는 전부 산문(주석·docstring)이고 표를 만드는 코드에는 없다.**
    `목표 배수` 가 20곳 넘게 나오지만 전부 파라미터를 설명하는 문장이고, `integer_contracts.csv`
    가 실제로 내는 헤더는 `배수`(`DISPLAY_MULTIPLE`)다. **「연결 누락」의 판정 기준은
    「같은 뜻의 문자열이 산출물에 실리는가」이지 「그 낱말이 파일에 있는가」가 아니다**

- [x] 🟡 **`COL_CONVERGED_MONTHS` 결정** — 두 안 중 하나를 고르고 근거를 진행 로그에 적는다
  - **(a) 지운다** ← 권장. 값은 이미 `summary.json` 의 `converged_with_neighbour_months` 로 나가고,
    격자 칸마다 반복될 값이 아니라 **대상 단위 속성**이다 (계약이 「행마다 반복할 값이 아니면
    `summary.json` 에 둔다」를 `ticker` 에서 같은 이유로 정했다)
  - **(b) 컬럼으로 낸다** — 「격자 칸이 독립이 아니다」를 CSV 를 여는 사람이 바로 보게 한다.
    선택하면 **어느 표에 넣을지**와 **대상당 한 값이 전 행에 반복되는 것**을 감수할지 정해야 한다

- [x] 🟡 **`DISPLAY_TARGET_MULTIPLE` 결정**
  - **(a) 지운다** ← 권장. `integer_contracts.csv` 가 이미 `배수` / `실제 배수` 로 구별하고 있어
    세 번째 이름이 필요 없다
  - **(b) `integer_contracts` 의 `배수` 를 `목표 배수` 로 개명해 연결한다** —
    🔴 선택하면 **산출물 컬럼 이름이 바뀐다.** 결과 문서가 그 열을 인용하는지 먼저 확인해야 하고,
    이 계획서의 「값·컬럼 불변」 전제가 깨지므로 **Scope 와 DoD 를 함께 고쳐야 한다**

- [x] **D-2 재판단**: `sed -n '50,90p' src/verify_lab/data/pykrx_collector.py` 등으로
      네 자리에 정말 정의가 없는지 눈으로 확인한다 — **4건 전부 확인**
- [x] **D-3 재판단**: `grep -n "제외" src/verify_lab/strategy/periods.py` — docstring 에만 남았는지
      — **240·244행 docstring 뿐이고 `COUNT_COLUMNS`(66-72행)에 `DISPLAY_EXCLUDED` 가 없다**
- [x] **D-4 재판단**: `sed -n '526,545p' src/verify_lab/report/tables.py` — 가드가 여전히 한 방향인지
      — **530행 `missing` 이 표 → 사전 방향만 본다. 그대로다**
- [x] **D-5 재판단** (추가): 249행 `RuntimeError` 가 실재하고 259·260·262행이 `& has_month` 를 다는지
      — **셋 다 확인. 233행 `np.where` 는 가드보다 앞이라 살아 있다**
- [x] **D-6 재판단** (추가): `grep -n '"예"' src/verify_lab/studies/leverage_tracking/runner.py`
      — **320·470행 두 곳. 470행만 판정가능이고 320행은 다른 개념이다**
- [x] 항목별 판정을 **진행 로그에 표로** 남긴다 (`항목 | 지운다/연결한다/남긴다 | 근거`)

---

### Phase 1 — 죽은 레이블 감시 테스트(레드 허용)

> 지우기 «전»에 감시를 세운다. 그래야 이번에 지운 것이 다시 쌓이는지 알 수 있다.

**작업 내용**:

- [x] 새 테스트(또는 `tests/test_layer_contracts.py` 확장) 추가 — **표시 레이블 사전의 모든 키가 실제로 쓰인다**
  - 대상: `studies/month_end/constants.COLUMN_LABELS` · `studies/option_expiry/constants.OUTPUT_LABELS`
    (그 밖에 `*_LABELS` 형태의 사전이 있으면 함께)
  - 판정: 사전의 각 **키(=`COL_*` 값)** 가 그 검증 패키지 안에서 **사전 정의 줄 말고 다른 자리에**
    한 번이라도 나타나는가. AST 로 「그 이름을 참조하는 노드」를 세는 편이 문자열 grep 보다 정확하다
  - 🔴 **런타임 가드로 만들지 않는다.** `to_display_columns` 는 표마다 컬럼이 달라
    사전이 상위집합이어야 한다 — 양방향으로 막으면 정상 호출이 전부 막힌다.
    **이 사실을 테스트 docstring 에 적는다**
  - **구현**: `tests/test_layer_contracts.py` 의 `TestDisplayLabelLiveness` (헬퍼 셋 신설 —
    `_assigned_name`·`_package_trees`·`_label_dicts`)
  - 🔴 **판정식을 두 번 고쳤다. 근거는 아래 진행 로그 22:05 항목**
- [x] 지금 이 테스트가 **실패하는지 확인한다.** 실패하지 않으면 판정식이 잘못된 것이다
  - `studies/month_end/constants.py 의 COLUMN_LABELS 에 죽은 레이블이 있습니다:
    ['COL_BASELINE_KIND', 'COL_CONVERGED_MONTHS']` — **Phase 0 판정과 정확히 일치**

---

### Phase 2 — 삭제와 정리(그린 유지)

**작업 내용**:

- [x] **D-1** Phase 0 에서 「지운다」로 판정된 상수를 제거
  - `common_constants.DOCS_DIR` — **주석까지 함께 지운다.** 그 주석이 거짓 정보다
  - `studies/month_end/constants.py` 의 `BASELINE_MONTH_ANY`·`BASELINE_MATCHED_LENGTH`·
    `COL_BASELINE_KIND`·`DISPLAY_BASELINE_KIND` (+ 결정에 따라 `COL_CONVERGED_MONTHS` 짝)
  - `COLUMN_LABELS` 에서 대응 항목 제거
  - `studies/futures_leverage/constants.DISPLAY_TARGET_MULTIPLE` (결정에 따라)
  - 🔴 **지운 뒤 `__init__.py` 의 `__all__` 과 테스트 import 를 함께 본다:**
    `grep -rn "<지운 이름>" src scripts tests`
- [x] **D-2** 고아 주석 4건 제거
  - `pykrx_collector.py:70-71` · `etn_collector.py:80-81` · `krx_futures_collector.py:129-132`
  - **주석을 그냥 지운다.** 상수는 이미 `data/constants.py` 에 있고 거기에 설명이 붙어 있다
    (`KRX_REQUEST_DATE_FORMAT`·`KRX_RESPONSE_DATE_FORMAT`)
- [x] **D-2b** `pykrx_collector.py:54-56` 오배치 주석 교정
  - `KRX_COLUMN_MAP` 설명 두 줄을 **그 상수 바로 위로** 옮기고, `KRX_CLOSE_COLUMN` 은
    자기 설명만 갖게 한다
- [x] **D-3** `strategy/periods.py` 의 `to_summary_frame` docstring 정리
  - `제외` 컬럼 서술을 지우고, **현재 남아 있는 사실**로 바꾼다 — 「표본이 0건인 구간이 하나라도
    생기면 pandas 가 건수 열을 실수로 만들어 `0.0` 이 나가므로 결측을 견디는 정수형으로 캐스팅한다」
  - 🔴 **「전에는 `제외` 가 …였다」로 바꾸지 않는다.** 그것은 과거 서술이며 계획서 F 가 걷어낼 대상이다
- [x] **D-5** `studies/month_end/schedule.py` 의 259·260·262행에서 `& has_month` 를 뺀다
  - 🔴 **233행 `safe_month_position` 의 `np.where(has_month, ...)` 는 그대로 둔다** —
    가드(249행)보다 **앞**이라 아직 죽지 않았고, `~has_entry` 행의 인덱싱이 거기서 터진다
  - **「왜 뺐는가」를 주석으로 남긴다** — 세 줄만 읽는 사람은 `has_month` 가 어디서
    보장되는지 알 수 없다. 249행 가드를 가리킨다
- [x] **D-6** `studies/leverage_tracking/runner.py:470` 의 `"예"` 를 `JUDGEABLE_YES` 로 바꾸고
      `measure.constants` 에서 import 한다
  - 🔴 **같은 파일 320행의 `"예"` 는 건드리지 않는다** — `DISPLAY_DISTRIBUTION_MEASURED` 라
    다른 질문이고 거짓 쪽 값도 다르다 (`"아니오 (ETN — 분배금 없음)"`)

---

### Phase 3 — 값 불변 대조

**작업 내용**:

- [x] Phase 0 의 미사용 스캐너를 다시 돌려 **이번에 다룬 이름이 목록에서 사라졌는지** 확인한다
  - **남은 것은 `EXECUTION_ROLES` 하나뿐**이고 그것은 Non-Goals 가 남기기로 한 것이다
- [x] `poetry run python scripts/studies/run_month_end_study.py` ·
      `run_futures_leverage_study.py` · **`run_leverage_tracking_study.py`**(D-6) 를 인자 없이 돌린다
- [x] 새 산출물의 **CSV 헤더와 전 셀 값**을 직전 산출물과 기계로 대조한다
  - **결과: CSV 47장 · 10,700,826칸 전 셀 일치, `summary.json` 3개 전부 일치**
      (기준: **A~C 를 먼저 했으므로 그때 낸 최신 산출물**이 기준이다 —
      `storage/results/검증/20260914_133016_month_end` · `.../20260906_080353_futures_leverage` ·
      최신 `*_leverage_tracking`. 🔴 **폴더 이름은 잰 구간을 말하지 않으므로
      `summary.json` 의 `rule` 을 먼저 열어 구간을 맞춘다** — A 의 인계사항)
- [x] 🔴 헤더가 하나라도 달라지면 **지우면 안 되는 것을 지운 것**이다. 되돌리고 원인을 적는다
  - **달라진 헤더 없음.** 되돌릴 것이 없다
- [x] 새 폴더는 커밋하지 않는다 — **정리는 사용자가 스킵하기로 했다** (2026-09-14 22:47)
  - 대조로 생긴 셋은 디스크에 남는다 — `20260914_221608_month_end`(1.1M) ·
    `20260914_221623_futures_leverage`(6.6M) · `20260914_221628_leverage_tracking`(74M).
    **셋 다 untracked 이고 어느 문서도 인용하지 않는다**
  - 🔴 **`git add -A` 로 딸려 들어가지 않게 주의한다.** 저장소 규칙이 「문서가 근거로 삼는
    실행만 올린다」이고, 한 번 커밋되면 지워도 `.git` 크기는 줄지 않는다
  - 지우려면 나중에 `/clean-results` 를 실행한다 (그 스킬은 모델이 호출할 수 없다)

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [x] `src/verify_lab/CLAUDE.md` 「내부/출력 분리」에 한 줄 추가 —
      「`to_display_columns` 의 검사는 **한 방향**(표 → 사전)뿐이다. 반대 방향(사전 → 표)은
      표마다 컬럼이 달라 런타임에서 막을 수 없으므로 **테스트가 잡는다**」
  - **판정 축의 근거도 함께 옮겼다** — 「자기가 정의한 키만 판정한다」와 그것을 빼면
    살아 있는 레이블 170개가 걸린다는 실측. 결론만 옮기면 다음 사람이 같은 두 안을 또 시도한다
- [x] `docs/COMMANDS.md`: 변경 여부 확정해 적는다 — **변경 없음.** 실행 명령이 하나도 바뀌지 않았다
- [x] 자동 포맷 적용: `poetry run black .` — `154 files left unchanged`
- [x] 🔴 **「후속 계획서 인계」 절을 채운다** (§8 Notes) — **E~G 가 알아야 할 것**을 적는다:
      **지운 이름 목록**(E 가 옮기려던 것이 없어졌을 수 있다), 지운 주석 위치,
      **남기기로 한 것과 그 근거**(다시 지우려 들지 않게), 새 감시 테스트가 무엇을 막는지,
      G 가 고쳐야 할 문서에서 이미 사라진 항목(⑨⑩). **비워 두면 다음 계획서가 낡은 전제로 시작한다**
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

> 순서를 지킨다 — 리뷰에서 고치면 코드가 바뀌므로 품질 검증이 마지막 관문이어야 한다.

- [x] `/code-review xhigh` (발견 11건 · 조치: **이 계획서 변경분 5건 전부 수정** · 나머지 6건은
      선행 계획서·기존 코드 소관이라 손대지 않고 아래 「인계」에 넘김)
- [x] `poetry run python validate_project.py` (passed=1135, failed=0, skipped=0) — Ruff·PyRight 도 통과

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다.**
> 계획서를 쓰는 시점에는 diff 가 없어 여기 적는 것은 전부 추측이고,
> **추측으로 적은 줄은 그대로 나간다.** 형식·문체 규칙은 `/commit` 이 정한다.

1. `검증 / 죽은 상수 7개·고아 주석 4건 제거와 이름표 사전 생존 감시 테스트 신설`
2. `검증 / 도달하지 않는 정의 정리와 재발 방지 계약 추가`
3. `검증 / 거짓 정보를 담은 상수·주석·docstring 교정과 그 근거의 계약 문서 승격`
4. `검증 / 미사용 정의 제거, 판정가능 리터럴의 소유자 연결, 증명 가능하게 죽은 조건 정리`
5. `검증 / 산출물 47장 전 셀 불변을 확인한 데드코드 정리와 한 방향 가드의 반대편 감시 보강`

> 🔴 **`storage/results/검증/20260914_2216*` 세 폴더는 커밋 대상이 아니다.** 값 불변 대조에만
> 쓴 산출물이라 어느 문서도 인용하지 않는다. **정리는 사용자가 스킵했으므로 untracked 로
> 디스크에 남아 있다** — 위 후보로 커밋할 때 `git add -A` 로 딸려 들어가지 않게 한다.

## 7) 리스크(Risks)

| 리스크 | 완화 |
| --- | --- |
| **「연결 누락」을 「필요 없음」으로 오판해 지운다** — 그러면 하드코딩이 정답인 것처럼 굳는다 | Phase 0 에 전역 규칙이 요구하는 하드코딩 짝 확인 명령을 두었다 |
| 지운 이름을 테스트가 import 하고 있어 수집 단계에서 죽는다 | Phase 2 에 `grep -rn "<지운 이름>" src scripts tests` 를 명시했다 |
| `COLUMN_LABELS` 에서 키를 빼다 **살아 있는 컬럼**의 레이블까지 지운다 | 그러면 `to_display_columns` 가 「한글 이름이 없는 컬럼」으로 **즉시 예외**를 낸다. Phase 3 재실행이 관문이다 |
| Phase 1 의 감시 테스트가 정당한 레이블을 죽은 것으로 잡는다 | AST 참조 계수를 쓰고, 예외가 필요하면 **이유와 함께** 테스트에 적는다 |
| `DISPLAY_TARGET_MULTIPLE` 을 (b)로 고르면 산출물 컬럼이 바뀐다 | Phase 0 에 그 경우 **Scope·DoD 를 함께 고쳐야 한다**고 명시했다. 권장은 (a) |

## 8) 메모(Notes)

- **왜 C 다음인가**: C 가 중복을 통합하면 「한쪽이 미사용이 되는」 정의가 생긴다. D 가 뒤에 오면 한 번에 걷힌다
- 2026-09-14 실측 — AST 전수 조사에서 **정의 파일 밖 참조가 0건인 모듈 레벨 이름은 6개**였다.
  그중 `EXECUTION_ROLES` 는 테스트가 불변조건으로 쓰므로 남긴다
- 「지운다」와 「남긴다」의 판정 근거를 **진행 로그에 표로** 남기는 것이 이 계획서의 절반이다.
  근거 없이 지운 목록은 다음 사람이 다시 조사한다

### 후속 계획서 인계 (이 계획서를 끝낸 뒤 채운다)

> **E~G 가 실행 전에 이 절을 읽는다.** 이 계획서로 바뀐 것 중 **그쪽 전제에 영향을 주는 것만** 적는다.
> 형식: `무엇이 | 어떻게 바뀌었나 | 어느 계획서가 영향받나`
>
> 🔴 **「남기기로 한 것과 근거」를 반드시 적는다** — 적지 않으면 다음 세션이 같은 목록을 다시 만들고
> 같은 분석을 반복한다. 아무것도 안 바뀌었으면 **「없음」이라고 적는다**.

| 무엇이 | 어떻게 바뀌었나 | 어느 계획서가 영향받나 |
| --- | --- | --- |
| 🔴 **사라진 이름 7개 — E 가 옮기려던 것이 없어졌을 수 있다** | `common_constants.DOCS_DIR` / `studies/month_end/constants.py` 의 `BASELINE_MONTH_ANY`·`BASELINE_MATCHED_LENGTH`·`COL_BASELINE_KIND`·`DISPLAY_BASELINE_KIND`·`COL_CONVERGED_MONTHS`·`DISPLAY_CONVERGED_MONTHS` / `studies/futures_leverage/constants.DISPLAY_TARGET_MULTIPLE`. **`COLUMN_LABELS` 에서 대응 항목 3줄도 함께 빠졌다** | **E**(파일 이동) · **F**(공유 조각) · **G**(문서) |
| ⚠️ **`option_expiry` 의 같은 이름들은 «살아 있다»** | `COL_BASELINE_KIND`·`DISPLAY_BASELINE_KIND`·`BASELINE_MATCHED_LENGTH` 가 옵션 만기일에도 있고 **그쪽은 쓰인다**(기준선이 둘이라 라벨링이 필요하다). 월말 것만 복사본이었다. **이름으로 일괄 검색해 지우면 옵션 만기일이 깨진다** | 이름으로 훑는 계획서 전부 |
| 🔴 **남기기로 한 것과 근거** | ① `month_end.EXECUTION_ROLES` — `tests/test_studies_month_end_execution.py:159` 가 불변조건으로 쓴다 ② `utils/result_citations.existing_result_dirs` — 테스트 6개가 직접 검증한다 ③ `report/tables._sorted_cells` — 「정렬」과 「기준 하나 검사」는 다른 책임이다 ④ `schedule.py:233` 의 `np.where(has_month, ...)` — **가드보다 «앞»이라 죽지 않았다.** 지우면 `~has_entry` 행의 인덱싱이 터진다 ⑤ `leverage_tracking/runner.py:320` 의 `"예"` — `DISPLAY_DISTRIBUTION_MEASURED` 라 다른 개념이고 거짓 쪽 값도 다르다 | **전부. 다시 지우려 들지 않게 이 다섯을 먼저 읽는다** |
| **새 감시 테스트가 무엇을 막나** | `tests/test_layer_contracts.py` 의 `TestDisplayLabelLiveness` — 검증 패키지의 `*_LABELS` 사전에서 **그 패키지가 정의한 키**가 사전 밖에서 안 쓰이면 실패한다. **사전 목록을 손으로 박지 않고 이름으로 자동 발견하므로 새 검증의 사전도 자동으로 감시된다** — 새 검증을 만들면 이 검사를 통과해야 한다 | **E**·**F**, 새 검증을 만드는 계획서 |
| ⚠️ **미사용 전수 스캐너를 그대로 믿지 말 것** | `own <= 1` 조건 때문에 **자기 파일의 사전에 한 번 등장하는 이름을 못 잡는다.** 이번에도 6개 중 4개를 놓쳤다. 「미사용 0건」을 근거로 삼는 계획서는 **개별 `grep` 으로 재확인**한다 | 미사용을 판정하는 계획서 전부 |
| **`schedule.py` 의 세 조건이 짧아졌다** | `out_of_range`·`no_holding`·`usable` 에서 `& has_month` 가 빠졌다. **249행 `RuntimeError` 가 그 조건을 대신 보장하므로 그 가드를 지우면 셋이 함께 깨진다** — 주석에 적어 뒀다 | 월말 일정표를 손대는 계획서 |
| **`to_summary_frame` docstring 이 바뀌었다** | 없어진 `제외` 컬럼을 근거로 들던 서술을 **현재 사실**(표본 0건 구간이 하나만 생겨도 pandas 가 건수 열을 실수로 만든다)로 바꿨다. **「전에는 …였다」로 쓰지 않았다** | **G**(과거 서술을 걷어낼 때 — 이 자리는 이미 처리됐다) |
| **G 가 고칠 문서에서 이미 사라진 항목** | 감사가 지목한 ⑨(고아 주석)·⑩(없는 컬럼 docstring)은 **코드에서 처리됐다.** 문서 쪽에 그 서술이 남아 있으면 그것만 고치면 된다 | **G** |
| **`src/verify_lab/CLAUDE.md` 「내부/출력 분리」에 문단이 늘었다** | 가드가 한 방향뿐인 이유와 **판정 축**(자기가 정의한 키만 본다)이 근거와 함께 들어갔다 | **G**(그 절을 손댈 때) |
| **테스트가 1,134 → 1,135 개** (새 파일 없음) | `test_layer_contracts.py` +1 (클래스 하나 · 헬퍼 셋) | 테스트 수를 세는 계획서 |
| **산출물은 한 셀도 바뀌지 않았다** | 세 검증 재실행 대조 — **CSV 47장 · 10,700,826칸 전 셀 일치**, `summary.json` 3개 모두 일치. 따라서 **E~G 는 「D 때문에 수치가 달라졌다」를 의심하지 않아도 된다** | 전부 |
| 🔴 **넘긴 것 — 산출물 폴더 정리가 남았다** | 대조로 생긴 폴더 셋(`20260914_2216*`)은 **사용자가 `/clean-results` 로 지운다.** 그 스킬은 모델이 호출할 수 없다 | 없음 (작업 항목) |
| 🔴 **코드 리뷰가 찾았으나 «이 계획서 소관이 아니라» 손대지 않은 것 6건** | 아래 표. **전부 재현 가능한 지적이고, 다시 조사할 필요가 없게 근거를 그대로 옮긴다** | 표의 「어디」 열 |

**코드 리뷰(2026-09-14 xhigh)가 남긴 것 — 손대지 않았다**

| # | 무엇 | 왜 이번에 안 했나 | 어디로 |
| --- | --- | --- | --- |
| 1 | **`futures_leverage.COL_INTEREST` 가 동음이의어를 하나로 합쳤다** — `position.py` 는 **일별 이자율(실수)**, `runner.py` 는 **`"이자 없음"`/`"이자 있음"` 축(문자열)**. `OUTPUT_LABELS` 는 그것을 `이자 가정` 으로 이름 붙인다. 이름을 갈라 놓으면 곡선 쪽 컬럼이 조용히 함께 바뀐다 | **C 가 통합한 것**이고 수술적 변경 원칙상 D 의 범위가 아니다. `src/verify_lab/CLAUDE.md` 가 **동음이의어는 통합하면 틀린다**고 이미 명시했으므로 되돌릴 근거는 있다 | **E** 또는 별도 |
| 2 | **`TestRunSummaryOwnership` 이 소스 «문자열»을 검사해 우회된다** — CLI 가 `outputs.summary["output_dir"] = ...` 를 앞줄에 끼우면 두 단언이 모두 통과하면서 절대경로가 되살아난다 | **B 가 만든 테스트**다. 고치려면 행동 검사로 바꿔야 하고 그것은 B 의 계약 작업이다 | **B 후속** |
| 3 | **`assert_no_absolute_paths` 가 여섯 요약 중 둘에만 걸려 있다** — 정작 결함이 있던 옵션 만기일 «검증» 요약과 월말·futures·leverage 검증 요약이 빠졌다 | 같음 — B 가 만든 픽스처의 적용 범위 문제다 | **B 후속** |
| 4 | **`_absolute_module` 이 `tests/`·`scripts/` 파일에 `relative_to(_SOURCE_ROOT)` 를 쓴다** — 그쪽에 상대 import 가 하나 생기면 계약 테스트가 단언 대신 `ValueError` 로 죽는다 | **D 이전부터 있던 잠재 결함**이다. 지금 터지지 않는다 | **E**·**F** |
| 5 | **`leverage_tracking.tail_column` 이 은행가 반올림을 쓴다** — `round(0.045*100)` 이 `4` 라 이름이 어긋나고, `0.045` 와 `0.05` 를 함께 넣으면 **같은 컬럼 이름으로 충돌해 한쪽이 덮인다.** 예외는 안 난다 | **C 가 옮긴 함수**이고 현재 분위 목록에는 충돌이 없다 | **F** |
| 6 | **`leverage_tracking/runner.py:320` 의 `"예"`** — 같은 파일이 `JUDGEABLE_YES` 를 import 하게 됐는데 한 자리는 리터럴로 남아 어느 쪽이 정본인지 안 보인다 | **일부러 남겼다**(위 「남기기로 한 것」 ⑤). `DISPLAY_DISTRIBUTION_MEASURED` 는 다른 질문이라 `JUDGEABLE_YES` 를 쓰면 잘못된 결합이다. **옳은 해법은 `leverage_tracking` 자기 상수를 두는 것**이며 그것은 D 의 범위가 아니다 | **F** |

### 진행 로그 (KST)

- 2026-09-14 12:05: 계획서 작성. 감사의 「불필요한 상수」·「데드코드」·「불필요한 함수」 중 삭제 대상만 D 로 분리
- 2026-09-14 21:42: **Phase 0 재판단 게이트 실행.** A·B·C 전부 ✅ Done 을 확인하고 세 인계 절을 읽었다.

  **선행 계획서가 이 계획서에 미친 영향**

  | 선행 | 무엇 | 이 계획서에 미친 영향 |
  | --- | --- | --- |
  | A | `resolve_positions` 신설 | 미사용 판정에 안 걸린다 (두 runner 가 쓴다). **영향 없음** |
  | A | `schedule.py` 의 `& has_month` 3곳이 죽었다 | **D-5 로 편입** (사용자 승인 21:45) |
  | B | `KEY_PATH`·`KEY_ROW_COUNT`·`KEY_START_DATE`·`KEY_END_DATE` 제거 | **이미 사라져 스캐너에 안 나온다.** 삭제 목록과 겹치지 않는다 |
  | B | `KEY_DATA_PERIOD` 와 `KEY_PERIOD` 가 둘 다 JSON 키 `"period"` | 둘 다 쓰이고 있어 미사용이 아니다. **헷갈릴 자리라 지우지 않도록 확인만** |
  | C | 이름 다수 이동·신설·제거 | 스캐너 재실행 결과 **C 가 만든 새 미사용은 없다** |
  | C | `leverage_tracking/runner.py` 의 `"예"` 하드코딩 | **D-6 으로 편입** (사용자 승인 21:45) |

  **항목별 판정**

  | 항목 | 판정 | 근거 (2026-09-14 21:42 실측) |
  | --- | --- | --- |
  | `common_constants.DOCS_DIR` | **지운다** | 참조 1건(정의부)뿐. 주석은 `utils/result_citations.py` 가 쓴다고 적었으나 그 모듈은 `root` 를 **인자로** 받는다 — 주석이 거짓이라 더 나쁘다 |
  | `month_end.BASELINE_MONTH_ANY` | **지운다** | 참조 1건. 값 `그 달 아무 날 진입` 은 **산문에만** 나온다 (`runner.py:14`·`schedule.py:353` docstring) |
  | `month_end.BASELINE_MATCHED_LENGTH` | **지운다** | 참조 1건. 같은 값을 `option_expiry/runner.py:302` 가 **자기 것으로 따로 정의해 쓴다** — 월말 것은 그 복사본이다 |
  | `month_end.COL_BASELINE_KIND` · `DISPLAY_BASELINE_KIND` | **지운다** | `COLUMN_LABELS`(444행)에만 등장. 산출물 CSV 8장 어디에도 `기준선` 단독 컬럼이 없다 |
  | `month_end.COL_CONVERGED_MONTHS` · `DISPLAY_CONVERGED_MONTHS` | **지운다 (a)** | `COLUMN_LABELS`(455행)에만 등장. 값은 이미 `summary.json` 의 `converged_with_neighbour_months` 로 나간다 (최신 실행에서 대상별 84·61·116·137·37). **대상 단위 속성이라 격자 칸마다 반복할 값이 아니다** |
  | `futures_leverage.DISPLAY_TARGET_MULTIPLE` | **지운다 (a)** | 참조 1건. `integer_contracts.csv` 가 이미 `배수`(목표)와 `실제 배수` 로 구별하고, `constants.py:441` 주석이 「여기서는 배수가 「목표」다」로 그 뜻을 못박았다. **(b) 는 산출물 컬럼명을 바꾸므로 「값·컬럼 불변」 전제가 깨진다** |
  | `month_end.EXECUTION_ROLES` | **남긴다** | `tests/test_studies_month_end_execution.py:159` 가 불변조건으로 쓴다 (Non-Goals) |
  | D-2 고아 주석 4건 | **지운다** | 네 자리 모두 뒤에 정의가 없다. 상수는 `data/constants.py` 에 설명과 함께 있다 |
  | D-2b 오배치 주석 | **옮긴다** | `pykrx_collector.py:54-55` 의 `KRX_COLUMN_MAP` 설명 두 줄이 `KRX_CLOSE_COLUMN` 위에 얹혀 있다 |
  | D-3 `to_summary_frame` docstring | **고친다** | `COUNT_COLUMNS`(66-72행)에 `DISPLAY_EXCLUDED` 가 없다. 없는 컬럼을 근거로 든 설명이다 |
  | D-4 죽은 레이블 감시 | **테스트를 세운다** | `tables.py:530` 이 표 → 사전 한 방향만 본다 |
  | **D-5** `schedule.py` 죽은 조건 3곳 | **뺀다** | 249행 `RuntimeError` 가 `has_entry ⇒ has_month` 를 보장한다. ⚠️ **233행 `np.where` 는 가드보다 앞이라 살아 있다 — 건드리지 않는다** |
  | **D-6** `"예"` 리터럴 | **연결한다** | `runner.py:470` 이 판정가능을 리터럴로 거른다. 소유자는 `measure/constants.JUDGEABLE_YES`(53행). **320행은 다른 개념이라 그대로 둔다** |

  🔴 **스캐너가 6개 중 4개만 잡았다.** `own <= 1` 조건 때문에 자기 파일 `COLUMN_LABELS` 에 등장하는
  넷이 통과한다 — **D-4 가 지목한 구멍과 정확히 같다.** 대조는 개별 `grep` 으로 했다.

  🔴 **`docs/COMMANDS.md` 변경 없음 확정** — 실행 명령이 하나도 바뀌지 않는다.

- 2026-09-14 22:05: **Phase 1 — 감시 테스트 레드 확인.** `TestDisplayLabelLiveness` 가
  `['COL_BASELINE_KIND', 'COL_CONVERGED_MONTHS']` 를 잡아 Phase 0 판정과 일치했다.

  🔴 **판정식을 두 번 버렸다. 그 근거를 남긴다 — 이 검사를 다시 만드는 사람이 같은 길을 두 번 간다.**

  | 안 | 판정 | 결과 | 왜 틀렸나 |
  | --- | --- | --- | --- |
  | 1 | 사전의 키·값이 사전 밖에서 참조되는가 | **오탐 0건** (아무것도 못 잡음) | `constants.py` 를 **두 번 파싱**해 노드 객체가 새로 생겼고, `id()` 로 하는 「이 노드는 사전 안이다」 제외가 한 번도 안 걸렸다. **에러 없이 통과했다** |
  | 2 | 위를 고침 | **오탐 170건** | `DISPLAY_*` 는 **사전이 유일한 소비처인 것이 정상**이다. `measure` 가 만드는 `COL_SIGNAL_COUNT` 류도 마찬가지 — 검증 패키지 안에서는 사전에만 나온다 |
  | 3 | **키 중 「그 패키지가 «정의»한」 것**만 판정 | **정확히 2건** | 죽은 것과 산 것을 가르는 축은 「사전 밖 참조」가 아니라 **「누가 그 컬럼을 프레임에 넣는가」**다. import 한 키는 다른 계층이 넣으므로 사전이 유일한 등장처여도 살아 있다 |

  **1안의 실패 방식이 이 검사가 막으려는 것과 같은 종류다** — 조용히 통과했고 값도 그럴듯했다.
  그래서 「판정한 키가 0개면 실패」 단언을 테스트에 함께 넣었다.

  **사전 목록을 손으로 박지 않고 `*_LABELS` 이름으로 자동 발견한다.** 박으면 다음 검증의
  사전이 감시 밖에 남는데, 그것이 바로 이 검사가 막으려는 실패 방식이다.
  전 패키지(6개)에 돌려 **`month_end` 외 오탐 0건**을 확인했다 — 값-사전
  (`HORIZON_LABELS`·`MODEL_LABELS`·`EXTREME_DIRECTION_LABELS`)은 키가 `Name` 이 아니라 자연히 빠진다.

- 2026-09-14 22:20: **Phase 2·3 완료.** 삭제·정리 후 세 검증을 재실행해
  **CSV 47장 · 10,700,826칸 전 셀 일치**, `summary.json` 3개 일치. 미사용 스캔에 남은 것은
  `EXECUTION_ROLES` 하나(Non-Goals).

- 2026-09-14 22:35: **코드 리뷰(xhigh) 11건 — 이 계획서 변경분 5건을 고쳤다.**

  | 지적 | 조치 |
  | --- | --- |
  | 🔴 **PyRight 2건 실패** — `_label_dicts` 가 `ast.stmt` 에 `.value` 로 접근 | `_module_assignments` 로 `Assign`/`AnnAssign` 을 먼저 좁혔다. **품질 게이트를 깨는 지적이었다** |
  | 사전을 `*_LABELS` **이름**으로 찾아, 이름만 바꾸면 감시에서 빠지는데 검사는 초록으로 남는다 | **구조로 찾도록 바꿨다** — 「키에 상수 이름이 오는 사전」. 이름 규약과 무관해졌다 |
  | 발견한 사전을 **전부** 참조 집계에서 빼, 스키마 사전(`SCHEDULE_DTYPES` 등)에도 있는 살아 있는 컬럼이 죽은 것으로 뒤집힐 수 있다 | 제외 범위를 **판정 중인 사전 하나**로 좁혔다 |
  | `_assigned_name` 이 `COL_A = COL_B = "x"` 를 놓쳐 그 상수가 「자기 정의」 목록에서 빠진다 | 이름을 **목록**으로 내도록 바꿨다 |
  | `CLAUDE.md` 와 테스트 docstring 이 **서로 다른 개수**를 박아 뒀고 둘 다 재현되지 않는다 | **수치를 걷어냈다.** 전역 규칙이 「문서에 개수를 직접 적지 않는다」로 정한 것이기도 하다 |

  **나머지 6건은 선행 계획서·기존 코드 소관이라 손대지 않고** 위 「인계」에 근거와 함께 넘겼다 —
  수술적 변경 원칙이다. 그중 `COL_INTEREST` 동음이의어 통합(C)이 가장 무겁다.

  검증 후 `black` 재적용, `validate_project.py` **passed=1135 / failed=0 / skipped=0**.

- 2026-09-14 22:47: **사용자가 산출물 폴더 정리를 스킵하기로 했다.** 대조로 생긴 셋(합 82M)은
  untracked 로 디스크에 남는다 — 어느 문서도 인용하지 않으므로 결과 문서의 근거에는 영향이 없다.
  **커밋에 딸려 들어가지 않게 하는 것만 남았고**, 이 계획서의 작업은 이것으로 끝났다.
