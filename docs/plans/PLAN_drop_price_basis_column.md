# Implementation Plan: 산출물에서 `가격기준` 식별 컬럼 제거

> 작성/운영 규칙(SoT): `/verify-plan` 스킬(`.claude/skills/verify-plan/SKILL.md`)을 반드시 참고하세요.  
> (이 템플릿을 수정하거나 새로운 양식의 계획서를 만들 때도 해당 스킬을 포인터로 두고 준수합니다.)

**상태**: ✅ Done

---

🚫 **이 영역은 삭제/수정 금지** 🚫

**상태 옵션**: 🟡 Draft / 🔄 In Progress / ✅ Done

**Done 처리 규칙**:

- ✅ Done 조건: DoD 모두 [x] + `skipped=0` + `failed=0`
- ⚠️ **스킵이 1개라도 존재하면 Done 처리 금지 + DoD 테스트 항목 체크 금지**
- 상세: `/verify-plan` 스킬의 "3) 스킵 및 완료 규칙" 참고
- 위 조건은 `.claude/hooks/plan_lint.py`가 저장 시 자동 검사합니다

---

**작성일**: 2026-08-20 16:57
**마지막 업데이트**: 2026-08-20 17:10
**관련 범위**: 검증(`studies/index_extreme`), CLI(`scripts/studies`), 산출물 스키마
**관련 문서**: `src/verify_lab/CLAUDE.md`, `scripts/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/docs.md`

---

## 0) 고정 규칙 (이 plan은 반드시 아래 규칙을 따른다)

> 🚫 **이 영역은 삭제/수정 금지** 🚫
> 이 섹션(0)은 지워지면 안 될 뿐만 아니라 **문구가 수정되면 안 됩니다.**
> 규칙의 상세 정의/예외는 반드시 `/verify-plan` 스킬을 따릅니다.

- `poetry run python validate_project.py`는 **마지막 Phase에서만 실행**한다. 실패하면 즉시 수정 후 재검증한다.
- Phase 0은 "레드(의도적 실패 테스트)" 허용, Phase 1부터는 **그린 유지**를 원칙으로 한다.
- 이미 생성된 plan은 **체크리스트 업데이트 외 수정 금지**한다.
- 스킵은 가능하면 **Phase 분해로 제거**한다.

## 1) 목표(Goal)

- [x] 목표 1: **네 산출물 CSV 의 식별 컬럼에서 `가격기준` 을 뺀다.** 7개 → 6개
- [x] 목표 2: **"무엇으로 쟀는지"의 기록은 잃지 않는다.** `summary.json` 의 데이터셋 목록과 터미널 "검증 대상 시세" 표에 가격 기준을 그대로 남긴다
- [x] 목표 3: **잃는 성질을 테스트로 대체한다.** 컬럼이 사라지면 산출물의 데이터셋 구분자는 `종목` 하나뿐이므로, **`DATASETS` 의 `ticker` 가 서로 달라야 한다**를 불변조건으로 건다
- [x] 목표 4: **검증을 재실행해 컬럼 외에는 아무것도 바뀌지 않았음을 확인한다**
- [x] 목표 5: 결정 근거와 탈락안을 스펙 §7 에 남기고, 계층 간 계약(ROADMAP)과 대조 가이드를 갱신한다

## 2) 비목표(Non-Goals)

- **`Dataset.price_basis` 필드를 지우지 않는다.** `summary.json` 과 터미널 표가 그대로 쓴다. 필드를 지우면 기록이 사라진다
- **`summary.json` 의 `datasets` 섹션을 건드리지 않는다.** 가격 기준은 **행 단위가 아니라 데이터셋 단위 속성**이며, 거기가 제 자리다
- **터미널 "검증 대상 시세" 표의 `가격기준` 열을 지우지 않는다.** 실행할 때마다 무엇으로 쟀는지 눈으로 확인하는 자리다
- **수정주가 방어 테스트 2건을 지우지 않는다.** `test_수정주가_데이터셋은_남아있지_않다`·`test_수정주가_파일을_가리키는_데이터셋이_없다` 가 실제 방어이며, 컬럼은 중복 방어였다
- **`measure/`·`report/` 공통 계층을 수정하지 않는다.** 식별 컬럼은 실행 계층이 붙인다(ROADMAP 실행 계층 계약)
- **다른 식별 컬럼(종목·테스트·파라미터·시작연도·방향·시대 구간)을 건드리지 않는다**
- **데이터를 재수집하지 않는다.** 저장된 시세 그대로 재실행만 한다
- **과거 결과 폴더를 손대지 않는다.** git 제외 대상이고 재생성 가능하다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

**`가격기준` 은 이제 축이 아니라 프로젝트 상수다.**

스펙 §7 결정 ⑰ 로 두 시장 모두 원본가 단일 기준이 됐고, 2026-08-20 사용자가 **"이 프로젝트에서는 무조건 원본가 기준 — 즉 차트와 동일하게"** 로 확정했다. 그 결과 `signals.csv` 12,679행의 `가격기준` 이 전부 `원본가` 하나다. 엑셀 필터를 걸면 선택지가 하나만 뜬다.

**상수를 행마다 반복해 적는 것은 정보가 아니라 잡음이다.** 대조는 필터를 거는 작업인데(HANDS_ON 2~3단계) 고를 것이 없는 필터가 하나 끼어 있다.

### 무엇을 잃고, 그것을 어떻게 대체하는가

컬럼이 하던 일이 하나 더 있었다. **같은 종목을 두 가격 기준으로 넣으면 `종목`(표시 이름)만으로는 행이 구별되지 않는데, `가격기준` 이 둘을 갈랐다.** 실제로 `tests/test_studies_runner.py` 의 `test_두_데이터셋이_같은_실행에서_같은_파라미터로_계산된다` 가 그 성질을 잡고 있다.

컬럼을 빼면 **산출물에서 데이터셋을 구분하는 것은 `종목` 하나뿐**이 된다. 그래서 티커가 겹치면 행이 조용히 뒤섞인다 — 표는 정상으로 보인다. 이것을 막는 것이 목표 3 의 새 불변조건이다.

| 잃는 것 | 대체 |
| --- | --- |
| 같은 종목 × 두 기준을 산출물에서 구별 | `DATASETS` 의 `ticker` 중복 금지 불변조건. 겹치면 테스트가 먼저 깨진다 |
| 산출물 파일 하나만 봐도 가격 기준을 안다 | `summary.json` 의 `datasets` 와 터미널 "검증 대상 시세" 표 (둘 다 유지) |
| 수정주가가 섞이면 컬럼에서 눈에 띈다 | 기존 방어 테스트 2건이 코드 레벨에서 이미 막는다 |

### 되돌리기

컬럼을 다시 붙이는 것은 `IDENTITY_COLUMNS` 에 상수 하나를 넣고 identity dict 두 곳에 한 줄씩 더하는 일이다. **어려운 변경이 아니므로 지금 미리 남겨 둘 이유가 없다**(루트 `CLAUDE.md` YAGNI).

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 측정의 원칙 8개, 수술적 변경, 공통 계층과 개별 검증의 경계
- `src/verify_lab/CLAUDE.md` — 계층 분리, 상수 관리, 측정 계층의 절대 원칙
- `scripts/CLAUDE.md` — CLI 계층에 도메인 로직 금지, 산출물 저장 규칙
- `tests/CLAUDE.md` — 정책을 테스트로 고정, Given-When-Then
- `.claude/rules/python.md` — 코딩 표준, 반올림, 로깅
- `.claude/rules/docs.md` — 스펙과 결과의 분리
- `docs/ROADMAP.md` — **확정된 출력 계약**, **확정된 실행 계층 계약**(식별 컬럼을 실행 계층이 붙인다)
- `docs/spec/index_extreme_events.md` — §7 확정된 설계 결정, §12 보고 형식

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/verify-plan` 스킬)

- [x] 기능 요구사항 충족 — 네 CSV 의 식별 컬럼이 6개이고 `가격기준` 이 없다
- [x] `summary.json` 의 데이터셋 목록과 터미널 "검증 대상 시세" 표에 가격 기준이 그대로 남아 있다
- [x] `DATASETS` 의 `ticker` 중복 금지 불변조건 테스트가 있다
- [x] 재실행 결과가 **`가격기준` 컬럼이 빠진 것 외에 기존 산출물과 동일**함을 실측으로 확인했다
- [x] 회귀/신규 테스트 추가 — 식별 컬럼 구성 1건, ticker 중복 금지 1건, 기존 다중 데이터셋 테스트 갱신
- [x] `poetry run python validate_project.py` 통과 (passed=**285**, failed=**0**, skipped=**0**)
- [x] `poetry run black .` 실행 완료 (마지막 Phase에서 자동 포맷 적용)
- [x] 필요한 문서 업데이트 — `docs/spec/index_extreme_events.md`, `docs/ROADMAP.md`, `docs/HANDS_ON.md`, `docs/research/RESEARCH_index_extreme_events.md` / `docs/COMMANDS.md` **변경 없음** / `docs/INDEX.md` **변경 없음**
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정과 탈락안 → 스펙 §7, 계층 간 계약 → ROADMAP, 컬럼 구성 → HANDS_ON·결과 문서)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/studies/index_extreme/runner.py` — `IDENTITY_COLUMNS` 에서 제거, identity dict 2곳, 신호 0건 신호군 요약 변환 1곳
- `scripts/studies/run_index_extreme.py` — `EXCERPT_COLUMNS` 에서 제거
- `tests/test_studies_runner.py` — 다중 데이터셋 테스트를 새 계약으로 갱신, 식별 컬럼 구성·ticker 중복 금지 테스트 추가
- `docs/spec/index_extreme_events.md` — §7 결정 항목 신설, §12 보고 형식의 컬럼 설명
- `docs/ROADMAP.md` — 확정된 실행 계층 계약의 식별 컬럼 설명
- `docs/HANDS_ON.md` — 2·3단계의 필터 컬럼 목록과 국내 필터 예시
- `docs/research/RESEARCH_index_extreme_events.md` — §3.2 식별 컬럼 7개 → 6개, §16.5 대조 방법
- `docs/COMMANDS.md`: **변경 없음** — CLI 인자와 실행 방법이 바뀌지 않는다
- `docs/INDEX.md`: **변경 없음** — 새 문서를 만들지 않는다

### 데이터/결과 영향

- **산출물 스키마가 바뀐다.** 네 CSV 모두 컬럼이 하나 줄고, `signals.csv` 는 25개 → **24개**가 된다
- **행 수와 값은 바뀌지 않는다.** 신호군 264개(집계 248개), `signals.csv` 12,679행 그대로여야 한다
- **`summary.json` 의 `empty_signal_groups` 항목에서도 `price_basis` 가 빠진다** — 식별 dict 에서 파생되기 때문이다. `datasets` 섹션의 `price_basis` 는 유지된다
- **기존 결과와 비교가 필요하다.** 대조 기준은 `storage/results/20260820_162937_index_extreme/`

## 6) 단계별 계획(Phases)

### Phase 0 — 새 계약을 테스트로 먼저 고정 (레드 허용)

> 산출물 스키마가 바뀌는 변경이므로 Phase 0 을 둔다.
> **컬럼을 빼면 산출물의 데이터셋 구분자가 `종목` 하나뿐이 되므로**, 그 전제를 먼저 테스트로 박는다.

**작업 내용**:

- [x] `tests/test_studies_runner.py` — 식별 컬럼이 **6개이고 `가격기준` 이 없음**을 고정하는 테스트 추가
      (네 산출물 모두 같은 순서로 앞에 오는지 함께 확인)
- [x] `tests/test_studies_runner.py::TestDatasetsInvariant` — **`DATASETS` 의 `ticker` 가 서로 다름**을 고정하는 테스트 추가.
      docstring 에 "컬럼이 빠진 뒤로는 `종목` 이 산출물의 유일한 데이터셋 구분자"라는 이유를 남긴다
- [x] `summary.json` 의 데이터셋 목록에 `price_basis` 가 **남아 있음**을 고정하는 테스트 추가
      (컬럼을 빼면서 기록까지 지우는 사고를 막는다)

**Validation**:

- [x] 새 테스트 3건 중 **식별 컬럼 테스트가 레드**, 나머지 2건은 그린임을 확인한다

---

### Phase 1 — 컬럼 제거 (그린 전환)

**작업 내용**:

- [x] `runner.py` — `IDENTITY_COLUMNS` 에서 `DISPLAY_PRICE_BASIS` 제거
- [x] `runner.py` — identity dict 두 곳(신호 0건 신호군 / 정상 신호군)에서 제거
- [x] `runner.py` — 신호 0건 신호군의 요약 변환에서 `KEY_PRICE_BASIS` 제거
- [x] `scripts/studies/run_index_extreme.py` — `EXCERPT_COLUMNS` 에서 제거
- [x] 본인 변경으로 생긴 orphan import 정리 (`DISPLAY_PRICE_BASIS` 가 더 이상 필요 없는 곳)
- [x] 기존 `test_두_데이터셋이_같은_실행에서_같은_파라미터로_계산된다` 를 새 계약으로 갱신 —
      **가격 기준이 아니라 `종목` 으로 갈리는지**를 확인하고, `summary.json` 에는 두 기준이 남는지 본다

**Validation**:

- [x] Phase 0 의 식별 컬럼 테스트가 그린으로 바뀐다
- [x] `tests/test_studies_runner.py` 전체 그린

---

### Phase 2 — 재실행과 대조

**작업 내용**:

- [x] 검증 재실행 — `scripts/studies/run_index_extreme.py` (약 2분)
- [x] `20260820_162937_index_extreme` 와 대조한다
      - 네 CSV 의 행 수가 같은가 (12,679 / 2,976 / 8,928 / 8,928)
      - 컬럼이 정확히 `가격기준` 하나만 빠졌는가
      - **남은 컬럼의 값이 전부 동일한가** (컬럼을 맞춰 비교)
      - `summary.json` 의 `datasets` 에 `price_basis` 가 남아 있는가
      - 신호군 248개·빠진 16개가 그대로인가
- [x] 터미널 출력에서 "검증 대상 시세" 표의 `가격기준` 열이 그대로 나오는지 확인
- [x] 대조 결과를 진행 로그에 수치로 남긴다

**Validation**:

- [x] 컬럼 하나가 빠진 것 외에 **달라진 값이 0개**다

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [x] `docs/spec/index_extreme_events.md` §7 에 결정 항목을 확정/탈락안/근거 형식으로 추가한다
      (탈락안: 그대로 유지 / CSV 에서만 빼고 터미널 발췌 표에는 남기기)
- [x] `docs/spec/index_extreme_events.md` §12 보고 형식의 컬럼 설명을 6개로 맞춘다
- [x] `docs/ROADMAP.md` 확정된 실행 계층 계약의 식별 컬럼 항목을 갱신한다
      (**가격 기준은 데이터셋 단위 속성이라 `summary.json` 에 둔다**는 근거를 남긴다)
- [x] `docs/HANDS_ON.md` 2·3단계의 필터 컬럼 목록과 국내 필터 예시에서 `가격기준` 을 뺀다
- [x] `docs/research/RESEARCH_index_extreme_events.md` §3.2 식별 컬럼 수와 §16.5 대조 방법을 갱신한다
- [x] `docs/COMMANDS.md` **변경 없음**, `docs/INDEX.md` **변경 없음** 확인
- [x] `poetry run black .` 실행(자동 포맷 적용)
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [x] `poetry run python validate_project.py` (passed=**285**, failed=**0**, skipped=**0**)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 검증 / 산출물에서 가격기준 식별 컬럼 제거 — 원본가 단일 기준을 상수로 확정
2. 검증 / 식별 컬럼 7개 → 6개, 가격 기준 기록은 summary.json 으로
3. 검증 / 값이 하나뿐인 가격기준 컬럼을 걷어내고 ticker 중복 금지를 불변조건으로
4. 검증 / 대조 필터 간소화 + 데이터셋 구분자 계약 정리
5. 문서 / 가격기준 컬럼 제거 결정 기록 + 산출물 스키마 반영

## 7) 리스크(Risks)

| 리스크 | 완화 |
| --- | --- |
| **같은 티커의 데이터셋이 생기면 산출물 행이 조용히 뒤섞인다** | Phase 0 의 `ticker` 중복 금지 불변조건이 먼저 깨지게 만든다. 표는 정상으로 보이므로 테스트가 유일한 방어다 |
| 컬럼을 빼면서 `summary.json` 의 기록까지 사라진다 | Phase 0 에 `summary.json` 유지 테스트를 두고, `Dataset.price_basis` 필드는 비목표로 못 박았다 |
| 값이 바뀌었는데 컬럼 제거에 묻힌다 | Phase 2 에서 **남은 컬럼끼리 값 대조**를 한다. "행 수가 같다"로 끝내지 않는다 |
| 문서 여러 곳의 "식별 컬럼 7개"가 낡은 채 남는다 | 마지막 Phase 에서 스펙·ROADMAP·HANDS_ON·결과 문서 네 곳을 모두 짚는다 |
| 나중에 가격 기준을 다시 재고 싶어진다 | 되돌리기가 `IDENTITY_COLUMNS` 한 줄 + identity dict 두 줄이다. 근거는 스펙 §7 결정 항목에 남는다 |

## 8) 메모(Notes)

- **이 변경의 계기**: 2026-08-20 대조 완료 직후 사용자가 "결과 파일에 `가격기준` 컬럼이 필요한가, 이 프로젝트에서는 무조건 원본가 — 차트와 동일하게"라고 물었다
- **사용자 확정 사항 (2026-08-20)**: CSV 4개에서 뺀다. `summary.json` 과 터미널 표에는 남긴다
- **판단의 핵심**: 가격 기준은 **행 단위 속성이 아니라 데이터셋 단위 속성**이다. 축이던 시절에는 행에 있어야 했지만, 상수가 된 지금은 실행 요약이 제 자리다
- **관련 결정**: 원본가 단일 기준은 스펙 §7 결정 ⑰, 가격 자릿수 4자리는 결정 ⑱. 셋 다 **"사용자가 차트와 직접 대조할 수 있어야 한다"**(측정의 원칙 8)에서 나왔다

### 진행 로그 (KST)

- 2026-08-20 16:57: 계획서 작성. 착수 전 조사 — `가격기준` 은 전 행이 `원본가` 하나이고, 코드에서 식별 컬럼으로 쓰이는 곳은 `runner.py` 3곳과 `scripts` 1곳. `summary.json` 과 터미널 "검증 대상 시세" 표는 `Dataset.price_basis` 를 따로 참조하므로 컬럼을 빼도 기록이 남는다
- 2026-08-20 17:00: Phase 0 — 테스트 3건 추가. 식별 컬럼 구성 테스트만 레드(`가격기준` 이 아직 2번째), ticker 중복 금지와 summary 유지 테스트는 그린
- 2026-08-20 17:02: Phase 1 — `IDENTITY_COLUMNS`·identity dict 2곳·신호 0건 요약 변환·`EXCERPT_COLUMNS` 에서 제거. orphan 이 된 `DISPLAY_PRICE_BASIS` import 2곳 정리. 다중 데이터셋 테스트를 "종목으로 갈리고 가격 기준은 요약에만 남는다"로 갱신
- 2026-08-20 17:06: Phase 2 — 재실행(`20260820_170440_index_extreme`) 후 대조. 컬럼 25/19/17/22 → **24/18/16/21**, 빠진 컬럼은 네 파일 모두 `가격기준` 하나뿐. 행 수 12,679/2,976/8,928/8,928 동일. **남은 컬럼 688,200칸을 통째로 비교해 달라진 칸 0개.** 신호군 248개·빠진 16개 동일. `summary.json` `datasets` 에 `price_basis` 유지, `empty_signal_groups` 키에서는 함께 빠짐
- 2026-08-20 17:07: 터미널 확인 — "검증 대상 시세" 표에 `가격기준` 열 유지, 발췌 표에서는 제거되어 CSV 와 컬럼 구성 일치
- 2026-08-20 17:09: 문서 갱신 — 스펙 §7 결정 ⑲ + §8 "가격기준 컬럼 제거 대조", ROADMAP 실행 계층 계약(식별 컬럼 6개 + 가격 기준의 자리)·대조 대상 폴더, HANDS_ON 필터 목록·국내 예시·발췌 표 헤더, 결과 문서 헤더·§3.2·§16.5
- 2026-08-20 17:10: `poetry run black .` 56파일 무변경, `validate_project.py` passed=285 failed=0 skipped=0
- **미해결로 남긴 것**: `summary.json` 의 `populations` 섹션에 `price_basis` 가 남아 있다. `empty_signal_groups` 와 같은 조합 단위 기록인데 한쪽만 상수를 담고 있어 어긋난다. 이번 범위 밖이라 그대로 두었고 스펙 §8 에 기록했다
