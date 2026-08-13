# Implementation Plan: Phase 3-a 이벤트 정의 — 역대급 등락·연속 등락과 부가 컬럼

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

**작성일**: 2026-08-13 17:52
**마지막 업데이트**: 2026-08-13 18:32
**관련 범위**: studies, tests
**관련 문서**: `src/verify_lab/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/python.md`, `docs/spec/index_extreme_events.md`, `docs/ROADMAP.md`

---

## 0) 고정 규칙 (이 plan은 반드시 아래 규칙을 따른다)

> 🚫 **이 영역은 삭제/수정 금지** 🚫
> 이 섹션(0)은 지워지면 안 될 뿐만 아니라 **문구가 수정되면 안 됩니다.**
> 규칙의 상세 정의/예외는 반드시 `/verify-plan` 스킬을 따릅니다.

- `poetry run python validate_project.py`는 **마지막 Phase에서만 실행**한다. 실패하면 즉시 수정 후 재검증한다.
- Phase 0은 "레드(의도적 실패 테스트)" 허용, Phase 1부터는 **그린 유지**를 원칙으로 한다.
- 이미 생성된 plan은 **체크리스트 업데이트 외 수정 금지**한다.
- 스킵은 가능하면 **Phase 분해로 제거**한다.

---

## 1) 목표(Goal)

- [x] 목표 1: **테스트 A(역대급 등락)** — 판정일까지의 데이터만으로 매기는 확장창 순위와 K 컷 판정을 만든다.
      전체 기간을 한 번에 보고 순위를 매기는 코드는 금지다
- [x] 목표 2: **테스트 B(연속 등락)** — N일 연속이 **달성된 그날**을 신호로 판정한다.
      등락률 0인 날은 연속을 끊고 방향을 부여하지 않는다
- [x] 목표 3: **부가 컬럼** — 사건 번호(30일 이내 묶기)와 참고용 z-score(직전 60거래일 변동성 대비)를 낸다
- [x] 목표 4: **look-ahead 감시 계약을 네 산출 전부에 건다** (`tests/conftest.py` 의 공용 헬퍼)
- [x] 목표 5: 실데이터로 스펙 §8 의 기록값(당시 순위 7건, 집계 시작 시점별 신호 수, 테스트 B 발생 빈도)을
      재현하고 그 결과를 스펙에 남긴다

## 2) 비목표(Non-Goals)

- **실행 스크립트** — Phase 3-b (`scripts/studies/`). 강건성 조합 순회, 두 가격 기준 병기, 결과 저장이 거기 있다
- **결과 문서** — Phase 3-c (`docs/research/RESEARCH_index_extreme_events.md`)
- **표시용 변환** — 부가 컬럼의 한글 레이블과 비율 → 백분율 변환은 **3-b 가 정한다.**
  이 조각은 내부 토큰(`COL_*`)과 비율(0~1)로만 낸다
- **`measure`·`report` 수정** — 두 계층은 이번 조각의 산출을 이미 받을 수 있다.
  손대야 할 것 같으면 그 검증에만 필요한 특수화가 아닌지 먼저 의심한다
- **베이스라인·통계 재구현** — 전부 `measure` 의 일이다
- **`scripts/studies/.gitkeep` 삭제** — 이 조각은 스크립트를 만들지 않으므로 그대로 둔다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

- 공통 계층(`data`·`measure`·`report`)이 전부 끝났고 **남은 것은 이벤트 정의 하나뿐**이다.
  `studies` 가 공통 계층에 넘기는 것은 "어느 날이 신호인가" 하나이며, 그 자리가 아직 비어 있다
- `src/verify_lab/studies/` 는 아직 `.gitkeep` 만 있는 빈 폴더다. **그 계층의 첫 작업은 규칙이 자동
  주입되지 않으므로** `src/verify_lab/CLAUDE.md` 와 `.claude/rules/python.md` 를 직접 열어 읽었다
- 테스트 A 의 확장창 순위는 이 프로젝트에서 **look-ahead 가 가장 쉽게 섞이는 지점**이다.
  전체 기간으로 한 번에 순위를 매기면 결과가 좋아지고, 눈으로는 발견되지 않는다
- 사건 번호와 z-score 는 `measure` 가 아니라 `studies` 소속으로 이미 확정돼 있다
  (확인된 재사용처 0건, ROADMAP "확정된 forward return 반환 계약")

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 측정의 원칙 8개, 공통 계층과 개별 검증의 경계
- `src/verify_lab/CLAUDE.md` — 계층 분리, `studies` 의 계약, 상수 관리 3계층, **측정 계층의 절대 원칙 5가지**
- `tests/CLAUDE.md` — 필수 테스트 3종(look-ahead 감시·산식 고정·표본 보존), 경계 조건, 부동소수점 비교
- `.claude/rules/python.md` — 타입 힌트, 비율 표기, 반올림, 로깅, 주석 규칙
- `docs/spec/index_extreme_events.md` — §3(이벤트 정의)·§7(확정된 결정)·§10(명시적 제외)·§11(부가 출력)
- `docs/ROADMAP.md` — 확정된 forward return 반환 계약, 확정된 베이스라인·통계 계약

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/verify-plan` 스킬)

- [x] 기능 요구사항 충족 — 테스트 A·B 이벤트 정의와 부가 컬럼 2종이 동작한다
- [x] 회귀/신규 테스트 추가 — look-ahead 감시 4건, 산식 고정, 경계 조건 포함
- [x] `poetry run python validate_project.py` 통과 (failed=0, skipped=0; passed/failed/skipped 수 기록)
- [x] `poetry run black .` 실행 완료 (마지막 Phase에서 자동 포맷 적용)
- [x] 필요한 문서 업데이트(`docs/COMMANDS.md` / CLAUDE.md / plan 등 — 각각 변경 여부 명시)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 근거·실측 수치를 스펙/설계/ROADMAP/COMMANDS로 이관. `/verify-plan` 스킬 "근거 승격" 참고)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/studies/__init__.py` (신설) — 패키지 초기화
- `src/verify_lab/studies/index_extreme/__init__.py` (신설) — 공개 API
- `src/verify_lab/studies/index_extreme/constants.py` (신설) — 방향 Enum, 파라미터 목록, 창 크기
- `src/verify_lab/studies/index_extreme/daily_change.py` (신설) — **일간 등락률 단일 산식**
- `src/verify_lab/studies/index_extreme/extreme_move.py` (신설) — 테스트 A (확장창 순위, K 컷)
- `src/verify_lab/studies/index_extreme/consecutive.py` (신설) — 테스트 B (부호 있는 연속 길이, N 판정)
- `src/verify_lab/studies/index_extreme/annotations.py` (신설) — 사건 번호, 참고용 z-score
- `src/verify_lab/studies/.gitkeep` (삭제) — 폴더에 다른 파일이 생기므로 역할이 끝난다
- `tests/test_studies_daily_change.py` (신설)
- `tests/test_studies_extreme_move.py` (신설)
- `tests/test_studies_consecutive.py` (신설)
- `tests/test_studies_annotations.py` (신설)
- `docs/spec/index_extreme_events.md` (수정) — §7 에 확정 결정 4건 추가, §8 에 실측 기록 추가·갱신
- `docs/ROADMAP.md` (수정) — Phase 3 체크박스 세분화, **확정된 이벤트 정의 계약** 절 신설
- `START_PROMPT.md` (수정) — 다음 작업을 3-b 로 갱신
- `docs/COMMANDS.md`: **변경 없음** — 실행 스크립트를 만들지 않는다. 검증 실행 명령은 3-b 에서 생긴다
- `docs/INDEX.md`: **변경 없음** — `docs/`·`reference/` 에 파일을 추가·삭제하지 않는다

### 데이터/결과 영향

- **산출물 파일을 만들지 않는다.** 이벤트 정의는 bool Series 와 부가 컬럼 프레임만 낸다
- 원시 시세 파일을 읽기만 하고 쓰지 않는다. 테스트는 전부 합성 데이터를 쓴다
- `measure`·`report` 의 반환 형태는 바뀌지 않는다. 기존 산출물 형식과 충돌하지 않는다
- 마지막 Phase 의 실데이터 재현 확인은 **읽기 전용**이며 `storage/` 에 파일을 남기지 않는다

## 6) 단계별 계획(Phases)

### Phase 0 — 이벤트 정의 계약을 테스트로 먼저 고정(레드)

> **정의가 곧 결론을 만든다.** 순위 동률 처리나 연속 길이 해석이 하나만 어긋나도 신호 수가
> 조용히 달라지고, 결과는 여전히 그럴듯해 보인다. 산식을 손계산으로 박아 둔 뒤 구현한다.

**작업 내용**:

- [x] `tests/test_studies_daily_change.py` — 등락률 단일 산식
      - 손계산 값 고정, 첫 행은 값 없음, 원본 DataFrame 불변
      - 필수 컬럼 누락·날짜 역순은 `ValueError`
- [x] `tests/test_studies_extreme_move.py` — 테스트 A
      - 확장창 순위 손계산 (판정일까지의 데이터만 쓴다)
      - **동률은 같은 순위**를 받는다 (자기보다 극단인 날의 수 + 1)
      - **집계 시작일 이전은 신호가 아니지만 순위 축적에는 들어간다** — 이 조각의 핵심 계약
      - K 컷별 판정, 폭등·폭락 분리
      - **look-ahead 감시** (공용 헬퍼), 경계: 최소 길이 데이터·신호 0건
- [x] `tests/test_studies_consecutive.py` — 테스트 B
      - 부호 있는 연속 길이 손계산 (+3 = 3일 연속 상승, −3 = 3일 연속 하락)
      - **등락률 0인 날은 연속을 끊고 방향을 부여하지 않는다**
      - **연속 길이가 정확히 N 인 날만 신호다** — 7일 연속 랠리는 N=5 신호를 5일째에만 만든다
      - **look-ahead 감시**, 경계: 연속 구간이 데이터 시작·끝에 걸친 경우
- [x] `tests/test_studies_annotations.py` — 부가 컬럼
      - 사건 묶기: **달력 30일 이내는 같은 사건, 31일은 새 사건** (경계를 정확히 고정)
      - 폭등·폭락을 합친 입력에서 사건 번호가 1부터 순차로 붙는다
      - z-score: 손계산 값, 창이 안 차면 빈 값, 표준편차 0 이면 빈 값
      - **look-ahead 감시** (사건 번호·z-score 각각), 경계: 신호 0건 입력

---

### Phase 1 — 등락률 단일 산식과 테스트 A 구현(그린 유지)

> 등락률은 두 테스트와 z-score 가 함께 쓴다. **판정식 단일화** 원칙상 한 곳에만 둔다.

**작업 내용**:

- [x] `src/verify_lab/studies/__init__.py`, `index_extreme/__init__.py` 뼈대
- [x] `index_extreme/constants.py` — 방향 Enum, 순위 컷·연속 길이·집계 시작 연도 목록,
      사건 묶기 창(달력일), z-score 창(거래일)
- [x] `index_extreme/daily_change.py` — `daily_change_rate(df)`.
      `validate_market_frame` 으로 구조를 먼저 확인한다
- [x] `index_extreme/extreme_move.py`
      - `expanding_rank(df)` — 판정일까지의 등락률만으로 매긴 폭등·폭락 순위
      - `find_extreme_move_events(df, *, direction, rank_cut, start_date)` — bool Series.
        **집계 시작일을 함수 안에서 처리한다** — 밖에서 자르면 순위 축적이 무너지고 예외 없이 틀린다
- [x] `src/verify_lab/studies/.gitkeep` 삭제
- [x] Phase 0 의 daily_change·extreme_move 테스트 그린 확인

---

### Phase 2 — 테스트 B와 부가 컬럼 구현(그린 유지)

**작업 내용**:

- [x] `index_extreme/consecutive.py`
      - `signed_run_length(df)` — 당일까지 이어진 연속 길이에 방향 부호를 붙인 정수 Series
      - `find_consecutive_events(df, *, direction, length, start_date)` — bool Series
- [x] `index_extreme/annotations.py`
      - `assign_event_ids(dates)` — 앞에서부터 훑어 달력 30일 이내면 같은 사건 번호
      - `reference_zscore(df)` — 당일 등락률 ÷ 직전 60거래일 등락률 표준편차
- [x] `index_extreme/__init__.py` — 공개 API 확정
- [x] Phase 0 의 consecutive·annotations 테스트 그린 확인

---

### 마지막 Phase — 실데이터 재현, 문서 정리 및 최종 검증

**작업 내용**

- [x] **실데이터 재현 확인** — `storage/market/QQQ_max.csv` 로 스펙 §8 과 대조한다.
      당시 순위 7건, 집계 시작 시점별 신호 수(K=10), 테스트 B 발생 빈도.
      값이 어긋나면 데이터가 아니라 산식이 틀린 것이다
- [x] `docs/spec/index_extreme_events.md` — §7 에 확정 결정 4건 추가(연속 길이 해석, 사건 묶기 단위,
      사건 번호 범위, z-score 산식)하고 §8 에 이번 실측 기록 추가·발생 빈도표 갱신
- [x] `docs/ROADMAP.md` — Phase 3 체크박스 세분화(3-a/3-b/3-c), **확정된 이벤트 정의 계약** 절 신설
- [x] `START_PROMPT.md` — 현재 상태와 다음 작업(3-b)으로 갱신
- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` **변경 없음** — 사유는 Scope 에 명시)
- [x] `poetry run black .` 실행(자동 포맷 적용)
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [x] `poetry run python validate_project.py` (passed=248, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 검증 / 지수 극단 이벤트 정의 신설 — 확장창 순위와 연속 등락 판정 고정
2. 검증 / studies 계층 신설 — look-ahead 감시 계약을 이벤트 정의 4종에 적용
3. 검증 / 테스트 A·B 이벤트 정의와 사건 묶기·z-score 부가 컬럼 구현
4. 검증 / 역대급 등락 순위 판정 추가 — 스펙 §8 기록값 재현 확인
5. 검증 / 검증 #1 이벤트 정의 구현과 확정 결정 4건 스펙 반영

## 7) 리스크(Risks)

- **집계 시작일을 함수 밖에서 자를 위험** — 시세를 먼저 잘라 넘기면 확장창 순위가 그 지점부터 다시
  쌓여 **예외 없이 틀린 결과**가 나온다. 시작일을 함수 인자로 받아 안에서 처리하고, 그 계약을
  테스트로 고정한다
- **순위 동률 처리로 신호 수가 조용히 달라질 위험** — 국내 원본가는 정수 가격이라 같은 등락률이
  실제로 나올 수 있다. 판정식을 손계산 테스트로 박아 둔다
- **연속 길이 해석을 `>= N` 으로 잘못 구현할 위험** — 실측상 QQQ 2011년 이후 N=3 상승이
  301건(`== N`)과 685건(`>= N`)으로 두 배 이상 갈린다. 스펙 §8 발생 빈도표와 대조해 확인한다
- **부가 컬럼이 판정에 스며들 위험** — z-score 는 **해석 보조**이며 이벤트 판정에 쓰지 않는다.
  §11 이 명시한 제약이므로 구현에서도 판정 경로와 분리한다
- **`studies` 가 공통 계층을 특수화할 위험** — `measure`·`report` 를 손대야 할 것 같으면
  그 검증에만 필요한 것인지 먼저 의심한다. 이번 조각은 두 계층을 건드리지 않는 것이 목표다
- **확장창 순위의 계산량** — 판정일마다 누적 구간을 훑으므로 데이터가 길어지면 비용이 제곱으로 는다.
  현재 규모(6,896행 0.03초)에서는 문제가 없고, 강건성 조합 전체를 돌려도 초 단위다

## 8) 메모(Notes)

### 확정한 설계 결정과 근거

사용자 확인을 거쳐 확정한 항목 ①~③ 과, 실측으로 확정한 ④ 다.

| # | 항목 | 확정 | 탈락안 | 근거 |
| --- | --- | --- | --- | --- |
| ① | **사건 묶기의 "30일"** | **달력일 30일** (30일 이내는 같은 사건, 31일부터 새 사건) | 거래일 30일 | 스펙 §4 는 측정 구간을 "1주(5거래일)·1개월(21거래일)"처럼 **거래일일 때 반드시 명시**한다. §3·§7 은 그냥 "30일"이므로 달력일로 읽는 것이 자연스럽고, "같은 충격의 연쇄"도 달력 시간 개념이다. 테스트 A 7건은 두 기준 모두 사건 3개라 구분되지 않지만, **테스트 B 는 크게 갈린다** — N=3 상승 301건이 달력 30일이면 41개, 거래일 30일이면 19개 사건이다 |
| ② | **사건 번호의 범위** | 같은 파라미터(K 또는 N)·같은 시작연도 안에서 **폭등·폭락을 합쳐** 번호를 매기고, 방향별 표에는 "그 방향 신호가 걸친 사건 수"를 적는다 | 방향별로 따로 묶기 | 스펙 §8 표가 이미 이 방식이다 — 2008 사건 ①에 폭락 2건과 폭등 2건이 **함께** 들어 있어 "7건 = 사건 3개"가 나온다. 방향별로 나누면 폭등 2건=2사건·폭락 2건=2사건이 되어, §7 결정 ③ 이 드러내려던 **비독립성이 오히려 숨는다** |
| ③ | **참고용 z-score 산식** | `당일 등락률 ÷ 직전 60거래일 등락률 표준편차` (평균 차감 없음, 판정일 제외) | `(등락률 − 직전 60일 평균) ÷ 표준편차` | §11 의 "직전 60일 **변동성 대비**"를 글자 그대로 읽은 것이다. "변동성 대비"는 중심이 아니라 산포 대비를 뜻하고, "직전"은 판정일을 뺀다는 뜻이다. 판정에 쓰지 않는 해석 보조 컬럼이라 결론을 바꾸지 않는다 |
| ④ | **테스트 B 의 "N일 연속이 달성된 그날"** | **연속 길이가 정확히 N 인 날** | 연속 길이 ≥ N 인 모든 날 | **실측으로 확정됐다.** `== N` 이 스펙 §8 발생 빈도표를 그대로 재현한다(아래 "미리 확인한 사실"). `>= N` 은 N=3 상승이 685건으로 표의 300건과 전혀 맞지 않는다. §3 의 "7일 연속 랠리는 N=5·6·7 신호를 모두 만든다"도 각 N 마다 한 건씩이라는 뜻이 된다 |

### 미리 확인한 사실 (2026-08-13 실측, QQQ 6,896행)

| 확인한 것 | 결과 |
| --- | --- |
| **확장창 순위 재현** | 스펙 §8 의 "당시 순위" **7건 전부 일치**(폭락 6·1·1·1위, 폭등 3·5·4위). 집계 시작 시점별 신호 수도 2003·2005·2008년 3/4/7건, 2011년 1/2/3건으로 §8 표와 **완전히 일치** |
| **테스트 B 발생 빈도** | `== N` 해석의 산출이 §8 표와 일치한다 (상승 301/166/96/52/29/15/10/7, 하락 186/73/31/13/3/2/2/0). §8 은 6,678행 시절 값이라 ±1 차이가 있으며, 그 차이는 재수집으로 늘어난 뒤쪽 10거래일로 설명된다 |
| **사건 묶기 기준의 영향** | 테스트 A 7건은 달력·거래일 어느 쪽이든 사건 3개. 테스트 B 는 N=3 상승 301건이 41개(달력) 대 19개(거래일)로 갈린다 |
| **계산 비용** | 확장창 순위 6,896행에 **0.03초**. 순위는 K·방향·시작연도와 무관하므로 조합마다 다시 계산해도 초 단위다. 최적화나 사전 계산 API 를 둘 이유가 없다 |
| **등락률 0인 날** | QQQ 전 기간에 **38건** 존재한다. §7 결정 ⑧(연속을 끊되 방향 미부여)이 실제로 작동하는 경로다 |

### 이 조각이 다음 조각에 넘기는 것

- 테스트 A: `find_extreme_move_events(df, *, direction, rank_cut, start_date)` → bool Series
- 테스트 B: `find_consecutive_events(df, *, direction, length, start_date)` → bool Series
- 신호일 목록 부가 컬럼: `expanding_rank(df)`, `signed_run_length(df)`, `assign_event_ids(dates)`,
  `reference_zscore(df)` — 전부 **내부 토큰과 비율**로 낸다
- 3-b 는 이것을 강건성 조합만큼 순회하며 `measure` 에 넘기고, 표시용 레이블과 백분율 변환을 정한다

### 진행 로그 (KST)

- 2026-08-13 17:52: 계획서 작성. Phase 3 분할(3조각)·강건성 조합 일괄 산출·국내 두 기준 병기·
  결과 문서 단일화 4건을 사용자 확인으로 확정하고, 이벤트 정의의 모호점 3건(사건 묶기 단위·
  사건 번호 범위·z-score 산식)을 추가로 확정. 테스트 B 해석은 스펙 §8 대조 실측으로 확정
- 2026-08-13 18:05: Phase 0 테스트 60건 작성 후 구현. **레드에서 3건이 실패했고 전부 테스트 쪽 오류였다** —
  확장창 순위 손계산 2건에서 부등호 방향을 빠뜨렸고(−4.76% > −10%, +5% < +10%),
  변동성 0 테스트는 종가 133.1·146.41 이 이진수로 딱 떨어지지 않아 표준편차가 1e-17 로 남았다.
  종가를 2배씩 올리는 값으로 바꿔 정확히 0 이 되게 했다
- 2026-08-13 18:20: 구현한 모듈로 실데이터 재현 확인. 스펙 §8 의 당시 순위 7건·종가·집계 시작
  시점별 신호 수(3/4/7·3/4/7·3/4/7·1/2/3)·사건 3개가 전부 일치. 테스트 B 발생 빈도는 코드 산출값으로
  §8 표를 갱신했다(6,678행 시절 값과 몇 칸에서 1건씩 차이, 원인은 재수집으로 늘어난 뒤쪽 10거래일)
- 2026-08-13 18:30: Ruff 2건(import 정렬)과 PyRight 1건 수정. 후자는 pandas 스텁이
  `Series.diff()` 를 `Series[float]` 로 봐서 `.dt.days` 접근이 막힌 것이라 numpy 로 간격을 계산하게
  바꿨다. **`assign_event_ids` 를 다시 쓴 뒤 실데이터 재현을 한 번 더 확인**해 값이 그대로임을 봤다
- 2026-08-13 18:32: 최종 검증 통과 (passed=248, failed=0, skipped=0)
