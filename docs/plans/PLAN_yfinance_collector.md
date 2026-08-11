# Implementation Plan: Phase 1-b yfinance 수집기 — QQQ 원시 시세 확보

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

**작성일**: 2026-08-11 09:52
**마지막 업데이트**: 2026-08-11 10:08
**관련 범위**: data, scripts, tests
**관련 문서**: `src/verify_lab/CLAUDE.md`, `scripts/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/python.md`, `docs/spec/index_extreme_events.md`, `docs/ROADMAP.md`

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

- [x] 목표 1: yfinance 로 미국 종목 일별 시세를 받아 `storage/market/` 에 저장하는 수집 모듈을 만든다
- [x] 목표 2: `storage/market/` 의 **파일명 규칙을 하나로 확정**한다 (ROADMAP Phase 1 의 "저장 규칙 확정")
- [x] 목표 3: 수집기가 `data/loader.py` 의 `validate_market_data()` 를 그대로 재사용해 판정식이 갈라지지 않게 한다
- [x] 목표 4: 사용자가 실행할 CLI 스크립트를 만들고 `docs/COMMANDS.md` 에 등록한다
- [x] 목표 5: 사용자가 실제로 실행해 `storage/market/QQQ_max.csv` 의 데이터 기준일을 갱신한다

## 2) 비목표(Non-Goals)

- **KRX 자격증명 로더·pykrx 실측·KODEX 200 일체** — 별도 계획서로 진행한다
- `measure/`·`report/`·`studies/` (Phase 2·3)
- **수집 기간 자르기** — 스펙 §2 가 지정한 분석 시작일(2000-01-01)로 잘라 저장하지 않는다.
  원시 시세는 받을 수 있는 만큼 전부 저장하고, 기간 절단은 측정 계층의 몫이다
- 수집 실패 시의 재시도·백오프·체크포인트 — 한 종목을 한 번 받는 작업이라 필요 없다
- **AI 모델의 수집 스크립트 실행** — 외부 서버에 실제 요청을 보내므로 사용자만 실행한다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

- `storage/market/QQQ_max.csv` 는 **이전 프로젝트에서 이관한 파일**이라 이 저장소에는 그것을 만든 코드가 없다.
  데이터를 갱신할 방법이 없고, 어떤 옵션으로 받은 값인지도 코드로 확인할 수 없다
- 데이터 기준일이 **2026-07-24 에 고정**돼 있다. 스펙 §8 의 사전 실측 수치와 `docs/context/` 의 두 문서가
  전부 이 날짜 기준이며, 검증을 실행하기 전에 최신 데이터로 갱신해야 한다
- ROADMAP Phase 1 은 "저장 규칙 확정"을 요구한다. 지금은 파일이 하나뿐이라 규칙이 암묵적이고,
  두 번째 종목이 들어오는 순간 갈라진다
- 이상치 판정이 이미 `data/loader.py` 에 있다. 수집기가 자기 판정을 새로 만들면
  절대 원칙 5(판정식 단일화)를 곧바로 어기게 된다

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md`
- `src/verify_lab/CLAUDE.md` — 계층 구조, 핵심 패턴(즉시 실패·예외 은닉 금지), 측정 계층의 절대 원칙, 데이터 저장 규칙
- `scripts/CLAUDE.md` — CLI 계층 책임, 예외 처리 데코레이터, 명령행 인자 정책, 메타데이터 관리
- `tests/CLAUDE.md` — 외부 의존성 금지(네트워크 호출 금지), 파일 격리, 결정적 테스트, Given-When-Then
- `.claude/rules/python.md` — 타입 힌트, Path 객체, 반올림 규칙, 로깅 정책
- `docs/spec/index_extreme_events.md` — §2 가격 처리(수정주가 기준), §8 사전 실측 기록

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/plan` 스킬)

- [x] 기능 요구사항 충족 — 수집 모듈과 CLI 스크립트가 동작하고, 검증을 통과한 데이터만 저장한다
- [x] 회귀/신규 테스트 추가 — 네트워크 없이 스텁으로 계약 고정 (18개)
- [x] `poetry run python validate_project.py` 통과 (failed=0, skipped=0; passed/failed/skipped 수 기록)
- [x] `poetry run black .` 실행 완료 (마지막 Phase에서 자동 포맷 적용)
- [x] 필요한 문서 업데이트(`docs/COMMANDS.md` / CLAUDE.md / plan 등 — 각각 변경 여부 명시)
- [x] **사용자가 실제로 수집을 실행해 `QQQ_max.csv` 가 갱신됨을 확인** (ROADMAP 의 "QQQ 재수집")
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 근거·실측 수치를 스펙/설계/ROADMAP/COMMANDS로 이관. `/plan` 스킬 "근거 승격" 참고)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/data/yfinance_collector.py` (신설)
- `src/verify_lab/data/__init__.py` (수정 — 공개 API 추가)
- `tests/test_yfinance_collector.py` (신설)
- `scripts/data/collect_yfinance.py` (신설)
- `scripts/data/.gitkeep` (삭제 — 해당 폴더에 파일이 생기므로 자리표시자 역할 종료)
- `scripts/CLAUDE.md` (수정 — "메타 타입 목록"에 신규 타입 등록)
- `docs/ROADMAP.md` (수정 — Phase 1 체크리스트, 확정된 저장 규칙 기록)
- `docs/spec/index_extreme_events.md` (수정 — §8 에 yfinance 동작 실측 결과 추가)
- `START_PROMPT.md` (수정 — 현재 상태·다음 작업 갱신)
- `docs/COMMANDS.md`: **변경 있음** — "데이터 수집" 절에 신규 스크립트 실행 명령어를 채운다
- `docs/INDEX.md`: **변경 없음** — `docs/`·`reference/` 에 새 파일을 추가하지 않는다

### 데이터/결과 영향

- **`storage/market/QQQ_max.csv` 를 덮어쓴다.** 기존 파일은 이관본이며, 스펙 §8 이
  "Phase 1에서 자체 수집기로 재수집해 갱신한다 / 신규 수집 후에는 종료일이 달라지므로 수치가 바뀔 수 있다"고
  이미 예고한 동작이다. 파일은 git 으로 동기화되므로 이전 내용은 git 이력에 남는다
- 재수집 후 스펙 §8 의 사전 실측 수치(역대 상위 10위 표, 집계 시작별 신호 수, 테스트 B 발생 빈도)는
  **종료일이 달라져 값이 바뀔 수 있다.** 이 계획서에서는 갱신하지 않는다 —
  그 표들은 측정 코드(Phase 2·3)가 만든 결과로 갱신하는 것이 맞고, 지금 손으로 고치면 근거가 흐려진다
- **행 수는 줄어들 수 있다.** 최근 2거래일을 제외하므로, 실행일에 따라 마지막 며칠이 빠진다

## 6) 단계별 계획(Phases)

### Phase 0 — 인바리언트/정책을 테스트로 먼저 고정(레드)

> 수집기는 "무엇을 저장하는가"를 정하는 지점이다. 여기서 잘못 저장하면 그 위의 모든 측정이
> 틀린 원자료를 본다. 저장 전 검증·제외 건수 보고·파일명 규칙을 코드로 먼저 못 박는다.

**작업 내용**:

- [x] `tests/test_yfinance_collector.py` — yfinance 를 스텁으로 대체하고 네트워크를 쓰지 않는다
- [x] 반환·저장 계약 고정 — 저장 컬럼 구성과 순서(`REQUIRED_COLUMNS`), 파일명 `{ticker}_max.csv`, 저장 경로
- [x] **호출 인자 고정** — `auto_adjust=True` 와 `raise_errors=True` 가 실제로 전달되는지
      (근거는 Notes. 이 둘이 빠지면 원본가를 수정주가로 착각하거나 실패가 조용히 빈 파일이 된다)
- [x] **저장 전 검증 정책 고정** — 이상치가 있는 응답이면 예외가 발생하고 **파일이 만들어지지 않는다**
- [x] **최근 2거래일 제외와 제외 건수 반환 고정** (절대 원칙 4 — 표본이 조용히 사라지지 않게)
- [x] 경계 조건 — 빈 응답, 제외 후 데이터가 하나도 남지 않는 경우, 최근 2일이 아예 없는 과거 데이터
- [x] 결정적 테스트 — `freezegun` 으로 오늘 날짜 고정, `tmp_path` 로 저장 경로 격리

---

### Phase 1 — 수집 모듈 구현(그린 유지)

**작업 내용**:

- [x] `src/verify_lab/data/yfinance_collector.py`
      - yfinance 호출 → 컬럼 선택 → 최근 2거래일 제외 → 반올림 → **검증** → 저장 순서
      - 이상치 판정은 `loader.validate_market_data()` 를 **그대로 재사용**한다 (판정식 단일화)
      - 저장 결과(경로·행 수·기간·제외 건수)를 호출자가 표시할 수 있는 형태로 돌려준다
- [x] `src/verify_lab/data/__init__.py` — 공개 API 추가
- [x] Phase 0 테스트 그린 확인

---

### Phase 2 — CLI 스크립트(그린 유지)

**작업 내용**:

- [x] `scripts/data/collect_yfinance.py` — `@cli_exception_handler`, 모듈 레벨 로거, `--ticker` 인자(기본 `QQQ`)
- [x] `TableLogger` 로 수집 요약 표시 (종목·기간·행 수·제외 건수·저장 경로)
- [x] `meta_manager.save_metadata()` 호출로 실행 이력 기록
- [x] `scripts/CLAUDE.md` "메타 타입 목록"에 신규 타입 등록
- [x] `scripts/data/.gitkeep` 삭제

---

### Phase 3 — 사용자 실행과 결과 확인

> **이 Phase 는 AI 모델이 진행할 수 없다.** 수집 스크립트는 외부 서버에 실제 요청을 보내므로
> 사용자만 실행한다. 실행 결과를 받은 뒤에 아래를 확인한다.

**작업 내용**:

- [x] 사용자에게 실행 명령어 안내 (`docs/COMMANDS.md` 기준)
- [x] 사용자 실행 후 `storage/market/QQQ_max.csv` 의 행 수와 기간을 확인
- [x] 갱신된 파일을 `load_market_csv()` 로 읽어 이상 없이 통과하는지 일회성 확인
- [x] 실측으로 확인된 yfinance 동작(수정주가 여부·컬럼 구성·최근 데이터 지연)을
      `docs/spec/index_extreme_events.md` §8 에 기록

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [x] `docs/COMMANDS.md` "데이터 수집" 절 작성 (**변경 있음**)
- [x] `docs/ROADMAP.md` Phase 1 체크리스트 갱신 + 확정된 저장 규칙 기록
- [x] `START_PROMPT.md` 현재 상태·다음 작업 갱신
- [x] `poetry run black .` 실행(자동 포맷 적용)
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [x] `poetry run python validate_project.py` (passed=71, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 수집 / yfinance 수집기 신설 — 수정주가 명시 지정과 저장 전 검증
2. 수집 / QQQ 원시 시세 수집 경로 구축 및 저장 규칙 확정
3. 수집 / yfinance 어댑터와 CLI 추가, 이상치 판정 재사용
4. 수집 / 미국 시세 수집기 + 계약 테스트 고정
5. 수집 / yfinance 수집기 신설 및 실행 명령어 등록

## 7) 리스크(Risks)

- **yfinance 가 조용히 동작을 바꿀 위험** — pykrx 와 같은 종류의 위험이다. 웹/비공식 API 래퍼라
  기본 인자나 반환 컬럼이 버전 사이에 바뀐다. 완화책은 **기본값에 기대지 않고 핵심 인자를 명시적으로 전달**하고,
  그 인자가 실제로 전달되는지를 테스트로 고정하는 것이다 (Phase 0)
- **원본가를 수정주가로 착각할 위험** — 절대 원칙 2 위반이며 결과 전체가 무효가 된다.
  `auto_adjust=True` 명시 + 테스트 고정으로 막는다
- **실패가 빈 파일로 둔갑할 위험** — `history()` 의 `raise_errors` 기본값이 `False` 라
  종목 오타나 네트워크 실패 시 **예외 없이 빈 DataFrame** 이 온다. 명시적으로 `True` 를 넘기고,
  빈 응답에도 예외를 던진다
- **재수집으로 스펙 §8 수치가 낡을 위험** — 값이 바뀔 수 있다는 사실은 §8 에 이미 적혀 있다.
  이 계획서에서는 수치를 고치지 않고, Phase 2·3 의 측정 코드가 만든 결과로 갱신한다
- **최근 2거래일 제외가 표본을 조용히 줄일 위험** — 제외 건수를 반환하고 로그·요약 표에 표시한다

## 8) 메모(Notes)

### 확정할 설계 결정과 근거

| # | 결정 | 탈락안 | 근거 |
| --- | --- | --- | --- |
| ① | **`auto_adjust=True` 를 명시적으로 넘긴다** | 라이브러리 기본값에 의존 (reference 관용) | 설치본 `yfinance 0.2.66` 의 `PriceHistory.history` 기본값이 `auto_adjust=True` 임을 시그니처로 확인했다. 지금은 원하는 값과 같지만, 이 값이 바뀌면 등락률과 forward return 이 원본가 기준이 되어 **분배락일이 인위적 하락으로 잡힌다.** 기본값에 기대면 그 사고가 조용히 일어난다 |
| ② | **`raise_errors=True` 를 명시적으로 넘긴다** | 기본값 `False` 유지 | 기본값에서는 조회 실패 시 예외 대신 **빈 DataFrame** 이 온다. `src/verify_lab/CLAUDE.md` 의 "예외는 숨기지 않는다 / 조용히 빈 DataFrame 을 반환하지 않는다"와 정면으로 충돌한다 |
| ③ | **항상 `period="max"` 로 받고 `{ticker}_max.csv` 로 저장한다** | `--start`·`--end` 인자와 `{ticker}_{start}_{end}.csv` 파일명 (reference 관용) | 파일명이 여러 갈래면 **로더가 어느 파일을 읽어야 하는지 모호해진다.** ROADMAP 이 요구하는 "저장 규칙 확정"은 규칙이 하나일 때만 성립한다. 기간 절단은 측정 계층의 몫이고, 부분 기간 수집은 아직 필요한 곳이 없다(YAGNI) |
| ④ | **최근 2거래일을 제외한다** | 전부 저장 / 당일만 제외 | 미국장은 한국 시각 기준 하루가 밀리고, 장중이나 마감 직후 데이터는 확정값이 아니다. 미확정 종가가 그대로 들어오면 그날이 "역대급 등락"으로 잡힐 수 있다. 제외 건수는 반환·로그로 남겨 절대 원칙 4를 지킨다 |
| ⑤ | **저장 전에 `validate_market_data()` 를 호출한다** | 수집기 전용 검증 함수 신설 | 절대 원칙 5(판정식 단일화). 판정이 갈라지면 "수집은 통과했는데 로딩에서 막히는" 데이터가 생긴다. 이 함수는 `data/loader.py` 에 이미 있고 로더가 쓰고 있다 |
| ⑥ | **날짜는 `YYYY-MM-DD` 문자열로 저장한다** | ISO 타임스탬프·타임존 포함 저장 | 기존 `QQQ_max.csv` 의 실제 포맷이며, 원시 시세 파일은 코드가 맞춰야 하는 불변 자산이다(`src/verify_lab/CLAUDE.md` "시세 컬럼명은 저장된 데이터가 정한다"). 로더가 읽을 때 `datetime64[ns]` 로 파싱한다 |

### 실측으로 확인한 사실 (2026-08-11)

- 설치본은 `yfinance 0.2.66`, Python 3.12.13
- `PriceHistory.history` 시그니처 기본값: `period=None, interval='1d', prepost=False, actions=True,`
  **`auto_adjust=True`**, `back_adjust=False`, `repair=False`, `keepna=False`, `rounding=False`,
  `timeout=10`, **`raise_errors=False`**
- 현재 `storage/market/QQQ_max.csv` — **6,886행, 1999-03-10 ~ 2026-07-24**,
  헤더는 `Date,Open,High,Low,Close,Volume`, 날짜는 `1999-03-10` 형식, 가격은 소수점 6자리

### 진행 로그 (KST)

- 2026-08-11 09:52: 계획서 작성. yfinance 설치본 시그니처 실측으로 ①②의 근거 확보
- 2026-08-11 10:00: Phase 0 테스트 18개 작성 후 `data/yfinance_collector.py`·`data/__init__.py` 구현, 전부 그린.
  이어서 Phase 2 의 CLI 스크립트와 `scripts/CLAUDE.md` 메타 타입 등록까지 완료
- 2026-08-11 10:04: **Phase 3(사용자 실행)보다 먼저 `docs/COMMANDS.md` 작성과 품질 검증을 수행했다.**
  사용자가 실행하려면 명령어 문서가 먼저 있어야 하고, 검증되지 않은 코드를 실행하게 할 수는 없다.
  `black .` 은 변경 없음(21 files unchanged), `validate_project.py` 는 passed=71, failed=0, skipped=0.
  사용자 실행 후 최종 검증을 한 번 더 수행한다
- 2026-08-11 10:04: 사용자 실행 대기 — Phase 3 은 AI 가 진행할 수 없다
- 2026-08-11 10:05: 사용자가 수집 실행. **6,896행, 1999-03-10 ~ 2026-08-07, 최근 제외 1행.**
  갱신된 파일을 `load_market_csv()` 로 읽어 중복 0건·`datetime64[ns]` 를 확인했다.
  **이관본과 자체 수집본의 가격 기준이 같음을 대조로 확인** — 역대 상위 10위 20개 날짜와 등락률,
  최대 일간 변동(+16.84% / −11.98%)이 모두 스펙 §8 표와 일치한다. 근거는 스펙 §8 로 승격했다
- 2026-08-11 10:07: **Scope 외 문서 1건 변경** — `docs/INDEX.md` §5 의 QQQ 파일 설명에
  종료일(2026-07-24)이 박혀 있어 재수집할 때마다 낡는다. 날짜를 빼고 재수집 스크립트를 가리키도록 고쳤다.
  Scope 절은 "생성 후 수정 금지" 규칙에 따라 원문을 보존하고 변경 사실을 이 로그에 남긴다
- 2026-08-11 10:08: 최종 검증 통과 (passed=71, failed=0, skipped=0)
