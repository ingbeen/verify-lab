# Implementation Plan: Phase 1-a 데이터 로더 계층 — 시세 파일 로딩의 단일 통로

> 작성/운영 규칙(SoT): `/plan` 스킬(`.claude/skills/plan/SKILL.md`)을 반드시 참고하세요.  
> (이 템플릿을 수정하거나 새로운 양식의 계획서를 만들 때도 해당 스킬을 포인터로 두고 준수합니다.)

**상태**: ✅ Done

---

🚫 **이 영역은 삭제/수정 금지** 🚫

**상태 옵션**: 🟡 Draft / 🔄 In Progress / ✅ Done

**Done 처리 규칙**:

- ✅ Done 조건: DoD 모두 [x] + `skipped=0` + `failed=0`
- ⚠️ **스킵이 1개라도 존재하면 Done 처리 금지 + DoD 테스트 항목 체크 금지**
- 상세: `/plan` 스킬의 "3) 스킵 및 완료 규칙" 참고
- 위 조건은 `.claude/hooks/plan_lint.py`가 저장 시 자동 검사합니다

---

**작성일**: 2026-08-10 12:11
**마지막 업데이트**: 2026-08-10 12:34
**관련 범위**: data, tests
**관련 문서**: `src/verify_lab/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/python.md`, `docs/ROADMAP.md`

---

## 0) 고정 규칙 (이 plan은 반드시 아래 규칙을 따른다)

> 🚫 **이 영역은 삭제/수정 금지** 🚫
> 이 섹션(0)은 지워지면 안 될 뿐만 아니라 **문구가 수정되면 안 됩니다.**
> 규칙의 상세 정의/예외는 반드시 `/plan` 스킬을 따릅니다.

- `poetry run python validate_project.py`는 **마지막 Phase에서만 실행**한다. 실패하면 즉시 수정 후 재검증한다.
- Phase 0은 "레드(의도적 실패 테스트)" 허용, Phase 1부터는 **그린 유지**를 원칙으로 한다.
- 이미 생성된 plan은 **체크리스트 업데이트 외 수정 금지**한다.
- 스킵은 가능하면 **Phase 분해로 제거**한다.

---

## 1) 목표(Goal)

- [x] 목표 1: 모든 시세 파일 로딩이 지나가는 단일 통로 `data/loader.py` 를 만든다
- [x] 목표 2: 로딩 시 스키마·정렬·중복·이상치를 검사하고, 이상은 **보간하지 않고 즉시 예외**로 드러낸다
- [x] 목표 3: 로더의 계약(반환 dtype, 예외 종류, 경계 동작)을 테스트로 고정한다

## 2) 비목표(Non-Goals)

- yfinance·pykrx 수집기와 `scripts/data/` 스크립트 — 별도 계획서로 진행한다
- **KODEX 200 관련 일체** — pykrx ETF 함수의 동작이 실측되지 않았고 KRX 자격증명도 없어 착수 불가
- 시세 파일의 컬럼 정규화(한글 → 공통 스키마) — 정규화 대상이 되는 pykrx 반환값을 아직 본 적이 없다
- forward return·베이스라인·통계 (Phase 2)
- 기존 `storage/market/QQQ_max.csv` 의 재수집이나 수정 — 원시 시세는 불변 자산이다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

- `src/verify_lab/data/` 가 비어 있어, 지금 상태로는 각 검증이 직접 `pd.read_csv` 를 부르게 된다.
  로딩이 흩어지면 스키마 검증과 이상치 판정이 검증마다 갈라지고, 같은 파일을 다르게 읽는 코드가 생긴다
- 측정 계층의 절대 원칙 중 **보간 금지**와 **판정식 단일화**는 로딩 지점에서부터 지켜져야 한다.
  로더가 조용히 결측을 메우면 그 위의 모든 측정이 무효가 된다
- 이미 `storage/market/QQQ_max.csv` 가 있어 Phase 2 착수 전에 이 파일을 안전하게 읽을 통로가 필요하다

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md`
- `src/verify_lab/CLAUDE.md` — 계층 구조, 핵심 패턴(데이터 로딩 중앙 집중·즉시 실패), 측정 계층의 절대 원칙
- `tests/CLAUDE.md` — 경계 조건, Given-When-Then, 파일 격리, 합성 데이터 사용
- `.claude/rules/python.md` — 타입 힌트, Path 객체, 비율 표기, 로깅 정책

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/plan` 스킬)

- [x] 기능 요구사항 충족 — `load_market_csv()` 가 스키마·정렬·중복·이상치를 처리한다
- [x] 회귀/신규 테스트 추가 — 정상 경로와 경계 조건, 예외 종류를 고정
- [x] `poetry run python validate_project.py` 통과 (failed=0, skipped=0; passed/failed/skipped 수 기록)
- [x] `poetry run black .` 실행 완료 (마지막 Phase에서 자동 포맷 적용)
- [x] 필요한 문서 업데이트(`docs/COMMANDS.md` / CLAUDE.md / plan 등 — 각각 변경 여부 명시)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 근거·실측 수치를 스펙/설계/ROADMAP/COMMANDS로 이관. `/plan` 스킬 "근거 승격" 참고)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/data/__init__.py` (신설)
- `src/verify_lab/data/loader.py` (신설)
- `tests/test_data_loader.py` (신설)
- `docs/ROADMAP.md` (Phase 1 체크리스트 일부)
- `docs/COMMANDS.md`: **변경 없음** — 실행 스크립트를 만들지 않는다. 로더는 라이브러리 코드다

### 데이터/결과 영향

- 출력 스키마 변경 없음 — 산출물을 만드는 코드가 아직 없다
- `storage/market/QQQ_max.csv` 를 **읽지 않는다.** 테스트는 합성 DataFrame 과 `tmp_path` 만 쓴다
  (실제 시세에 의존하면 데이터를 갱신할 때마다 테스트가 깨진다)

## 6) 단계별 계획(Phases)

### Phase 0 — 인바리언트/정책을 테스트로 먼저 고정(레드)

> 로더의 예외 정책과 반환 dtype 은 그 위 모든 계층의 전제가 되므로 먼저 고정한다.

**작업 내용**:

- [x] `tests/test_data_loader.py` — 정상 로딩의 반환 계약(컬럼·정렬·dtype) 고정
- [x] 예외 정책 고정 — 파일 없음/필수 컬럼 누락/결측/0·음수 가격/비정상 급등락
- [x] 경계 조건 고정 — 빈 파일, 한 행짜리 파일, 뒤섞인 날짜 순서, 중복 날짜

---

### Phase 1 — 핵심 구현/수정(그린 유지)

**작업 내용**:

- [x] `src/verify_lab/data/loader.py` — `load_market_csv()` 와 `validate_market_data()`
      - 판정식 단일화를 위해 이상치 판정을 **한 함수에만** 둔다. 수집기도 같은 함수를 쓴다
      - 날짜는 `datetime64[ns]` 로 통일한다 (근거는 Notes)
      - 원본 파일과 입력 DataFrame 을 변경하지 않는다
- [x] `src/verify_lab/data/__init__.py` — 공개 API 노출
- [x] Phase 0 테스트 그린 확인

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` 변경 없음 — 사유 명시)
- [x] `poetry run black .` 실행(자동 포맷 적용)
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [x] `poetry run python validate_project.py` (passed=53, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 수집 / 시세 로딩 단일 통로 신설 — 스키마·정렬·이상치 검증 포함
2. 수집 / data 계층 로더 추가 및 계약 테스트 고정
3. 수집 / 보간 금지·즉시 실패 정책을 로딩 지점에 구현
4. 수집 / 시세 파일 로더와 이상치 판정식 단일화
5. 수집 / data 로더 신설 + 경계 조건 테스트 보강

## 7) 리스크(Risks)

- **급등락 임계값이 정상 데이터를 오탐할 위험**: QQQ 실측 최대 변동은 +16.84% / −11.98% 이고
  국내 지수 ETF 는 가격제한폭 ±30% 안에 있다. 임계를 50%로 두면 양쪽 모두 여유가 있다
- **중복 날짜 정책이 표본 보존 원칙과 부딪힐 위험**: `src/verify_lab/CLAUDE.md` 는 로딩 시 "중복 제거"를
  지시하고, 같은 문서의 절대 원칙 4는 "표본을 줄이면 몇 건이 왜 빠졌는지 함께 반환"을 요구한다.
  로더는 지시대로 제거하되 **제거 건수를 WARNING 으로 남겨** 조용히 사라지지 않게 한다
- **dtype 선택이 이후 계층을 제약할 위험**: Notes 의 근거대로 `datetime64[ns]` 로 고정한다

## 8) 메모(Notes)

### 확정한 설계 결정과 근거

- **날짜 dtype 은 `datetime64[ns]` 로 한다.** 두 참고 파일의 관용이 갈린다 —
  `reference/data_loader_qbt.py` 는 `.dt.date`(object dtype), `reference/pykrx_실측기록.md` §0 은
  `date=datetime64[ns]` 고정이다. verify-lab 은 **확장창 순위와 이동평균처럼 창 기반 연산**이 핵심이라
  object dtype 이면 벡터화 비교와 rolling 이 막힌다. 후자를 채택한다
- **이상치 판정은 로더와 수집기가 같은 함수를 쓴다.** 절대 원칙 5(판정식 단일화)에 따른 것이며,
  수집 시점과 로딩 시점의 기준이 갈리면 "수집은 통과했는데 로딩에서 막히는" 데이터가 생긴다

### 실측으로 확인한 사실

- `storage/market/QQQ_max.csv` 는 6,886행(1999-03-10 ~ 2026-07-24)이며
  결측 0, 0 이하 가격 0행, 중복 날짜 0건, 날짜 오름차순 정렬 상태다.
  최대 일간 변동은 **+16.84% / −11.98%** 다
- 완성된 로더로 이 파일을 실제로 읽어 6,886행이 `datetime64[ns]` 날짜로 반환되는 것을 확인했다

### 진행 로그 (KST)

- 2026-08-10 12:11: 계획서 작성. QQQ 파일 실측으로 임계값 설계 근거 확보
- 2026-08-10 12:20: 테스트 15개 작성(레드) 후 `data/loader.py`·`data/__init__.py` 구현, 전부 그린.
  실제 QQQ 파일 로딩도 일회성으로 확인
- 2026-08-10 12:28: `.gitkeep` 규칙 개정에 따라 `src/verify_lab/data/.gitkeep` 삭제
  (해당 폴더에 파일이 생겼으므로 자리표시자 역할이 끝남)
- 2026-08-10 12:31: `black .` 은 변경 없음. Ruff 가 `C405`(불필요한 list 리터럴) 1건을 잡아
  집합 리터럴로 수정 후 재검증
- 2026-08-10 12:34: 최종 검증 통과 (passed=53, failed=0, skipped=0).
  **Scope 외 문서 1건 변경** — `docs/spec/index_extreme_events.md` §8 에 pykrx 실측 결과를 추가했다.
  ROADMAP 의 승격 표가 "데이터 소스 실측 결과 → 해당 검증 스펙"을 목적지로 지정하므로 그 규칙을 따랐다.
  Scope 절은 "생성 후 수정 금지" 규칙에 따라 원문을 보존하고 변경 사실을 이 로그에 남긴다
