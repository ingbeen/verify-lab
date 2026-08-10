# Implementation Plan: Phase 0 부트스트랩 마무리 — 유틸 이관 완료와 공통 상수 신설

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

**작성일**: 2026-08-10 10:35
**마지막 업데이트**: 2026-08-10 11:02
**관련 범위**: utils, 공통 상수, tests
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

- [x] 목표 1: `src/verify_lab/utils/` 4개 파일에 남은 옛 패키지명(`krx_sprint`) 참조를 제거해 import 에러 없이 로드되게 한다
- [x] 목표 2: `src/verify_lab/common_constants.py`를 신설해 경로 상수와 시세 스키마 컬럼 상수를 단일 관리한다
- [x] 목표 3: 유틸 4종의 스모크 테스트와 파일 격리 픽스처를 작성해 `validate_project.py`를 `failed=0 skipped=0`으로 통과시킨다
- [x] 목표 4: `docs/ROADMAP.md` Phase 0 체크리스트를 갱신하고 근거를 살아있는 문서로 승격한다

## 2) 비목표(Non-Goals)

- `data/`·`measure/`·`report/`·`studies/` 계층 구현 (각각 Phase 1~3)
- 데이터 수집기 작성, yfinance·pykrx 호출 (Phase 1)
- 측정 상수(측정 구간, 베이스라인 반복 횟수, 난수 시드, 순위 컷) 정의 — **쓰는 계층이 아직 없어 지금 정의하면 YAGNI 위반.** Phase 2에서 `measure/`와 함께 확정한다
- pykrx가 반환하는 한글 컬럼의 정규화 규약 — **실측 전이라 확정 불가.** Phase 1-c 실측 후 결정한다
- `utils/__init__.py`의 export 범위 확장 — 요청받지 않은 변경이며, 실제 소비자(`scripts/`)가 생기는 Phase 1에 판단한다
- 기존 유틸의 "학습 포인트" 주석 정리 — 사전에 존재하던 스타일이며 이번 요청과 무관하다 (수술적 변경)

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

- `utils/` 4개 파일은 이전 프로젝트에서 **복사만 된 상태**다. 실측 결과 남은 참조는 두 곳이다.
  - `utils/meta_manager.py:19` — `from krx_sprint.common_constants import META_JSON_PATH`.
    존재하지 않는 패키지를 import하므로 **모듈 로드 자체가 실패**한다
  - `utils/logger.py:125·132·137·194` — 기본 로거 이름이 `"krx_sprint"`
  - `utils/formatting.py`·`utils/cli_helpers.py` — 표준 라이브러리만 사용하며 **수정 대상 없음** (import 전수 확인)
- `common_constants.py`가 없어 `meta_manager`가 의존하는 `META_JSON_PATH`의 정의처가 존재하지 않는다
- 테스트가 `tests/test_index.py` 하나뿐이고 `tests/conftest.py`가 없다. 유틸의 동작 계약이 코드로 고정돼 있지 않다

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md`
- `src/verify_lab/CLAUDE.md` — 계층 구조, 상수 관리 3계층, 측정 계층의 절대 원칙
- `tests/CLAUDE.md` — 필수 테스트 3종, Given-When-Then, 부동소수점 비교, 파일 격리
- `.claude/rules/python.md` — 타입 힌트, Path 객체, 반올림, 로깅 정책, 주석 규칙
- `.claude/rules/docs.md` — 문서 SoT 역할과 계획서 수명
- `docs/ROADMAP.md` — Phase 진행 상태와 계획서 승격 목적지

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/plan` 스킬)

- [x] 기능 요구사항 충족 — `verify_lab.utils` 4종이 import 에러 없이 로드되고 `common_constants.py`가 신설됨
- [x] 회귀/신규 테스트 추가 — 유틸 스모크 테스트와 파일 격리 픽스처
- [x] `poetry run python validate_project.py` 통과 (failed=0, skipped=0; passed/failed/skipped 수 기록)
- [x] `poetry run black .` 실행 완료 (마지막 Phase에서 자동 포맷 적용)
- [x] 필요한 문서 업데이트(`docs/COMMANDS.md` / CLAUDE.md / plan 등 — 각각 변경 여부 명시)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 근거·실측 수치를 스펙/설계/ROADMAP/COMMANDS로 이관. `/plan` 스킬 "근거 승격" 참고)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/common_constants.py` (신설)
- `src/verify_lab/utils/meta_manager.py` (import 1줄)
- `src/verify_lab/utils/logger.py` (기본 로거 이름과 해당 docstring)
- `tests/conftest.py` (신설)
- `tests/test_common_constants.py` (신설)
- `tests/test_meta_manager.py` (신설)
- `tests/test_formatting.py` (신설)
- `tests/test_logger.py` (신설)
- `docs/ROADMAP.md` (Phase 0 체크리스트와 근거 승격)
- `docs/COMMANDS.md`: **변경 없음** — 새 실행 명령어나 CLI 옵션이 생기지 않는다. 품질 검증 명령어는 이미 등재돼 있다

### 데이터/결과 영향

- 출력 스키마 변경 없음 — 아직 산출물을 만드는 코드가 없다
- `storage/market/QQQ_max.csv`는 읽지도 쓰지도 않는다. 테스트는 합성 데이터와 `tmp_path`만 사용한다
- `storage/results/meta.json` 경로가 상수로 확정되지만 이번 작업에서 실제 파일을 만들지 않는다

## 6) 단계별 계획(Phases)

### Phase 0 — 인바리언트/정책을 테스트로 먼저 고정(레드)

> 상수의 형태와 파일 격리 계약이 이후 모든 계층의 기준점이 되므로 먼저 고정한다.

**작업 내용**:

- [x] `tests/conftest.py` — `mock_meta_path` 픽스처 작성.
      `meta_manager`가 **import 시점에 `META_JSON_PATH`를 캡처**하므로 `common_constants`와
      `meta_manager` 양쪽을 함께 `monkeypatch` 한다 (`tests/CLAUDE.md` §5)
- [x] `tests/test_common_constants.py` — 경로 기준점과 컬럼 스키마 계약을 고정 (레드 허용)
- [x] `tests/test_meta_manager.py` — 순환 저장 개수, KST 타임스탬프, 원본 dict 불변, 타입별 분리 (레드 허용)
- [x] `tests/test_formatting.py` — 한글 2칸 폭 계산과 정렬 계약 (레드 허용)
- [x] `tests/test_logger.py` — 기본 로거 이름과 핸들러 중복 방지 계약 (레드 허용)

---

### Phase 1 — 핵심 구현/수정(그린 유지)

**작업 내용**:

- [x] `src/verify_lab/common_constants.py` 신설
      - 경로 기준점은 `Path(__file__).resolve().parents[2]` — **CWD에 의존하지 않는다.**
        검증 스크립트를 어느 디렉터리에서 실행해도 같은 경로를 가리켜야 한다
      - `STORAGE_DIR` / `MARKET_DIR` / `RESULTS_DIR` / `META_JSON_PATH`
      - `COL_*` 6종과 `REQUIRED_COLUMNS` / `PRICE_COLUMNS`
- [x] `utils/meta_manager.py` — import를 `verify_lab.common_constants`로 교체
- [x] `utils/logger.py` — 기본 로거 이름을 `verify_lab`으로 교체하고 이를 서술한 docstring을 함께 수정
- [x] Phase 0의 테스트가 전부 그린인지 확인

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [x] `docs/ROADMAP.md` Phase 0 체크리스트 갱신 및 근거 승격 (`docs/COMMANDS.md` 변경 없음 — 사유 명시)
- [x] `poetry run black .` 실행(자동 포맷 적용)
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [x] `poetry run python validate_project.py` (passed=38, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 하네스 / Phase 0 마무리 — 유틸 패키지명 정리, 공통 상수 신설, 스모크 테스트 추가
2. 유틸 / 옛 패키지명 참조 제거 및 common_constants 신설 (import 정상화)
3. 유틸 / 공통 상수 단일화 + 파일 격리 픽스처와 유틸 계약 테스트 추가
4. 하네스 / 부트스트랩 완료 — 품질 게이트 첫 통과 상태 확보
5. 문서 / ROADMAP Phase 0 갱신 + 유틸 이관 마무리 구현 반영

## 7) 리스크(Risks)

- **`Final` 사용과 monkeypatch 충돌**: 상수에 `Final`을 붙여도 런타임 재바인딩은 막히지 않으므로
  테스트 격리에는 지장이 없다. 다만 PyRight가 경고할 수 있어, 경고가 나면 테스트에서 `setattr` 경로를 쓴다
- **`logger.py`의 기본 이름 변경이 기존 호출을 깨뜨릴 위험**: 현재 `get_logger`/`setup_logger`를
  호출하는 코드가 저장소에 **0건**이므로 (전수 확인) 파급이 없다
- **pandas·numpy 스텁 한계로 PyRight strict가 실패할 위험**: 이번 변경에는 pandas를 쓰는 코드가 없어
  가능성이 낮다. 발생하면 `pyrightconfig.json`을 고치지 않고 코드 쪽에서 타입을 명시해 해소한다

## 8) 메모(Notes)

### 확정한 설계 결정과 근거

- **경로 기준점을 `parents[2]`로 한다.** `reference/common_constants_qbt.py`는 `Path("storage")`
  (CWD 상대)를, `reference/common_constants_krx.py`는 `Path(__file__).resolve().parents[2]`를 쓴다.
  두 관용이 갈리므로 하나를 골라야 한다. verify-lab은 **AI 모델이 검증 스크립트를 반복 실행**하는 것이
  전제이고 실행 디렉터리를 보장할 수 없으므로, CWD에 의존하지 않는 후자를 채택한다
- **컬럼명은 `Date`/`Open`/… 대문자 시작으로 한다.** 이것은 취향이 아니라 데이터가 결정한다.
  이미 저장소에 있는 `storage/market/QQQ_max.csv`의 실제 헤더가 `Date,Open,High,Low,Close,Volume`이고,
  원시 시세 파일은 분석 코드가 덮어쓰지 않는 불변 자산이기 때문이다.
  `reference/common_constants_krx.py`의 소문자 관용(`date`/`open`)은 pykrx 원본을 정규화한 결과라
  이 프로젝트의 기존 파일과 맞지 않는다
- **`QQQ_DATA_PATH` 같은 개별 파일 상수는 넣지 않는다.** `src/verify_lab/CLAUDE.md`의 상수 관리 3계층은
  "2개 이상 계층에서 사용"을 `common_constants.py` 배치 조건으로 둔다. 현재 소비 계층이 0개다.
  Phase 1에서 `data/`와 `scripts/`가 함께 쓰는 것이 확인되면 그때 올린다

### 실측으로 확인한 사실

- 설치 완료 환경: Python 3.12.13 / pandas 2.3.3 / scipy 1.18.0 / pytest 9.1.1 / pyright 1.1.411 / ruff 0.8.6
- `docs/INDEX.md` 정합성은 **이미 통과 상태**다. `tests/test_index.py`의 검사 로직을 그대로 재현한 결과
  죽은 링크 0건, 미등록 파일 0건(추적 대상 35개 전부 등록), 핵심 문서 3개 링크 확인.
  즉 이 단계는 수정 작업이 아니라 확인 절차다

### 진행 로그 (KST)

- 2026-08-10 10:35: 계획서 작성. `poetry install` 완료 확인, 환경 실측 기록
- 2026-08-10 10:44: 테스트 5개 파일 작성(레드), 이어서 `common_constants.py` 신설과 유틸 2개 파일 수정.
  신규 테스트 32개 그린. 실행 후 `storage/results/` 가 생성되지 않아 파일 격리도 함께 실증
- 2026-08-10 10:52: `black .` 실행. 사전에 존재하던 `tests/test_index.py` 1개 파일이 함께 재포맷됨
  (assert 메시지 줄바꿈 위치만 변경, 동작 동일). 고정 규칙이 지시한 절차의 부수 효과이므로 유지하되
  사용자에게 보고한다
- 2026-08-10 10:56: **Scope 변경 발생** — `docs/COMMANDS.md` 를 "변경 없음"으로 적었으나 변경했다.
  검증 실행 중 `poetry run` 이 프로젝트 `.venv` 가 아닌 다른 환경을 잡는 함정을 발견했고,
  이 증상은 코드 오류로 오인되기 쉬워 실행 문서에 남길 가치가 있다고 판단했다.
  근거 본문은 `docs/ROADMAP.md` Phase 0 실측 기록에 두고 `docs/COMMANDS.md` 에는 포인터만 걸었다.
  Scope 절은 "생성 후 수정 금지" 규칙에 따라 원문을 보존하고 변경 사실을 이 로그에 남긴다
- 2026-08-10 11:02: 최종 검증 통과 (Ruff·PyRight OK, Pytest passed=38 failed=0 skipped=0).
  근거 승격 완료 — 경로 기준점과 컬럼 스키마 결정은 `src/verify_lab/CLAUDE.md` "데이터 저장 규칙",
  실행 환경 함정은 `docs/ROADMAP.md` Phase 0, Phase 상태와 pykrx 정규화 과제는 `docs/ROADMAP.md`
