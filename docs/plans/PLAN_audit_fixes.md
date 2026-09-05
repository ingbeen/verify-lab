# Implementation Plan: 전수 분석 결함 수정 (측정 오류·버그·상수 통합·문서 불일치)

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

**작성일**: 2026-09-05 21:14
**마지막 업데이트**: 2026-09-05 22:52
**관련 범위**: measure, report, studies(option_expiry·futures_leverage·index_extreme), data, 문서, 하네스 규칙
**관련 문서**: `CLAUDE.md`, `src/verify_lab/CLAUDE.md`, `scripts/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/python.md`, `.claude/rules/docs.md`, `.claude/rules/research.md`, `.claude/rules/strategy.md`

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

- [x] 목표 1: **같은 지표가 검증마다 다른 값을 내는 상태를 없앤다** — 「비중첩 표본」 정의 이원화, 「제외 사유」 문자열 이원화를 단일 함수·단일 상수로 통합한다
- [x] 목표 2: **측정의 원칙 16·17이 코드로 집행되게 한다** — 표본 부족 구간의 행이 사라지지 않게 하고, 회당 기대값 옆에 합산 수익률이 붙게 한다
- [x] 목표 3: **조용히 틀린 값을 내는 세 지점을 막는다** — 최대 유효 레버리지의 `NaN→0.0`, ECOS 잘림 검사 무력화, 파일명 규칙 9곳 분산
- [x] 목표 4: **문서가 코드를 잘못 설명하는 12곳과 규칙 문서의 변경 이력을 정리한다**
- [x] 목표 5: **영향받는 검증(#7·#9)을 재실행해 결과 문서 수치를 갱신하고, 무엇이 왜 달라졌는지 남긴다**

## 2) 비목표(Non-Goals)

**전수 분석에서 나온 87건 중 아래는 이번 범위가 아니다.** 사용자가 우선순위 제안(15건) + 12-(나)를 택했고, 나머지는 다음 기회에 별도 판단한다.

- 1-4(백분위 자릿수 2 vs 4), 1-5(`iloc[0]` 무언 통과), 1-6(백분위 동률), 1-7(방향 동점)
- 2-4~2-7(가드 누락·빈 표 스키마·정렬 미검증·승수 이력 정렬)
- 3-4~3-10(컬럼 상수 복제, 레이블 리터럴, `SCREEN_HORIZON` 등)
- 4-3~4-10(로더 3중 복제, KRX 클라이언트 3중 복제, ETN 이중 조회 등)
- 5-1(`data/__init__` 공개 API), 5-2(`run_position` 미사용), 5-5(`DISPLAY_TEST` 단일값), 5-6(`env -u VIRTUAL_ENV`), 5-7(`csv_type` 네이밍)
- 6-1~6-10 중 이번에 함께 고쳐지는 것(6-1=2-1, 6-3=2-2) 외 전부
- 8(`type: ignore` 2건 — 근본 원인이 KRX 로그인 순서라 4-4 정리와 함께 다뤄야 실익이 있음)
- 9-3~9-6(레이블 fallback, 분위 실패 사유 뭉침 등)
- 11(문서에 박힌 수치 — 값은 전부 맞으므로 급하지 않음)
- 12-(가) 코드 주석의 이력 6건
- **`docs/spec/`·`docs/context/` 는 손대지 않는다.** 설계 근거와 사용자 소유 문서다
- **시세 재수집 금지.** `storage/market/` 은 읽기만 한다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

저장소 전체(src 46 · scripts 18 · 규칙 문서)를 전수 분석해 87건을 찾았고, 그중 **결과 수치가 틀리거나
표본이 조용히 사라지는 것**을 우선 고친다.

- **「비중첩 표본」이 두 정의로 갈려 있다.** `leverage_tracking/breakdown.py:238` 은 `p + horizon`,
  `futures_leverage/runner.py:178` 은 `p + horizon + 1` 이다. 그런데 후자의 주석은
  "검증 #8 의 설계 결정 ⑦ 과 같은 이유"라고 적혀 있어 **같은 값이라고 읽힌다.**
  두 결과 문서의 같은 이름 컬럼을 나란히 비교할 수 없다
- **측정의 원칙 17이 한 계층에서만 지켜지지 않는다.** `leverage_tracking` 과 `strategy/expiry_runner`
  는 `판정가능` 컬럼으로 행을 남기는데, `option_expiry/runner.py:487·502` 만 `continue` 로 버린다
- **측정의 원칙 16이 화면에서 깨진다.** `screening` 이 합산 수익률을 계산하고 `DISPLAY_TOTAL_RETURN`
  도 있는데 `build_candidates_table` 이 그 컬럼을 빠뜨려 **화면에는 회당 기대값만** 나온다
- **`max(0.0, nan)` 이 0.0 을 돌려준다**(실측). 전 구간 소진 칸의 최대 유효 레버리지가
  「0」으로 나가 «위험이 전혀 없었다»로 읽힌다
- **ECOS 잘림 검사가 스스로 꺼진다.** `int(body.get(KEY_TOTAL_COUNT, len(rows)))` 의 기본값이
  `len(rows)` 라 다음 줄의 대조가 언제나 통과한다
- **`{ticker}_max.csv` 규칙이 9곳에 흩어져 있다.** 「경로는 상수로만 참조, 하드코딩 금지」와
  「계층 간 중복 정의는 발견 즉시 통합」을 동시에 어긴다
- **`expanding_rank`(O(n²) 파이썬 루프)가 데이터셋당 37회 재계산된다.** `_Context` 가 이미 담아둔
  값을 `find_extreme_move_events` 가 매번 다시 만든다 — 낭비이자 「판정식 단일화」 위반
- **문서가 코드를 잘못 설명하는 곳이 12군데** 있고, 규칙 문서에는 날짜 기반 변경 이력이 남아 있다

### 확정된 결정 (2026-09-05 사용자 승인)

| # | 결정 | 탈락안 | 근거 |
| --- | --- | --- | --- |
| ① | 비중첩 표본은 **검증 #8 정의(`p + horizon`)로 통일**한다 | 검증 #9 정의(`+ 1`) / 두 정의 병기 | 구간 `[p, p+h]` 와 `[p+h, p+2h]` 는 관측일 하나를 공유하지만 **수익률 구간이 겹치지 않아** 통계적으로 독립이다. 표준 구간 스케줄링 정의이기도 하다. 병기는 산출물 컬럼을 늘리면서 「판정 하한 10건을 어느 쪽으로 거나」라는 결정을 다시 만든다 |
| ② | 시기 절반 행은 **산출물에만 복원하고 판정은 불변**으로 둔다 | 판정에도 반영 | 원칙 17(행을 남긴다)을 지키면서 `docs/research/옵션_만기일.md` 와 `EXPIRY_CELLS` 7칸의 근거를 흔들지 않는다. `판정가능` 컬럼으로 「판정에 쓰지 말라」를 표에 남기는 것은 이미 `leverage_tracking`·`expiry_runner` 의 관용이다 |
| ③ | **영향받는 검증만 재실행**한다 | 전 검증 재실행 / 재실행 안 함 | 수치가 실제로 달라지는 것은 #7·#9 뿐이다. #1·#8 은 값이 같아야 하므로 **동일성 확인용으로만** 돌린다. 재실행 안 하면 결과 문서가 현재 코드로 재현되지 않는 상태가 남는다 |
| ④ | 규칙 문서는 **날짜 표기와 「전에는 …였습니다」 서술만 제거**한다 | 계획 문장까지 제거 / 이력 전부 제거 | `.claude/rules/docs.md` 는 탈락안과 근거를 남기라고 요구하고 `python.md` 는 변경 이력을 금지한다. 날짜·과거형만 걷어내면 둘을 동시에 만족한다 |

### 자체 검증에서 고친 것 (계획서 초안 → 확정, 2026-09-05)

계획서를 비판적으로 재검증해 아래 5건을 바로잡았다. **①은 초안의 제안 자체가 틀렸다.**

| # | 초안 | 확정 | 근거 |
| --- | --- | --- | --- |
| ① | 3-3 을 「값 통일 또는 이름 분리 — 판단해서 정함」으로 미뤘다 | **이름 분리로 확정. 값은 둘 다 유지한다** | `usdkrw` 의 250 은 관행값이 아니라 **사양서 §16.2·§16.3 이 지정한 값**이다(`constants.py:185` 주석). `distribution` 의 252 는 관행값이다. **뜻이 다르므로 통일하면 사양 위반**이고, 통일했다면 추적오차·알파의 합격 판정까지 흔들 뻔했다 |
| ② | `option_expiry/constants.py` 에 `판정가능` 상수를 새로 만든다 | **`measure/constants.py` 로 승격한다** | 이미 `leverage_tracking`·`strategy` 두 곳에 같은 상수가 있어 **새로 만들면 세 벌**이 된다. 「판정가능」은 측정의 원칙 17 이 요구하는 공통 개념이므로 루트 `CLAUDE.md` 「이것이 측정의 원칙에 적혀 있는가?」 기준으로 공통 계층에 있어야 한다 |
| ③ | `measure/sampling.py` 를 신규 생성한다 | **`measure/statistics.py` 에 추가한다** | 함수 하나 때문에 모듈을 만들면 시니어 엔지니어가 과복잡하다고 본다. 표본 수를 세는 일이라 통계 계층이 제자리다 |
| ④ | `find_extreme_move_events` 에 순위를 넘긴다 | **인자를 추가하되 기본값 `None`(내부 계산)을 유지한다** | 호출처가 `index_extreme/runner.py:409` 와 `strategy/runner.py:230` **두 곳**이다. 후자는 `_Context` 를 갖지 않으므로 기본값이 없으면 깨진다 |
| ⑤ | 재실행 결과를 직전 산출물과 곧바로 대조한다 | **대조 전에 직전 산출물의 데이터 기간을 현재 시세 파일과 먼저 맞춘다** | 최신 산출물이 `index_extreme` 2026-08-30 · `option_expiry` 2026-08-30 인데 `leverage_tracking`·`futures_leverage` 는 2026-09-05 다. 그 사이 시세가 재수집됐다면 대조 자체가 성립하지 않으므로, 기간이 다르면 **동일성 확인을 포기하고 그 사실을 기록한다** |

### 실측으로 확인한 것 (2026-09-05)

- `max(0.0, float('nan'))` == **0.0** (파이썬은 `nan > 0.0` 이 False라 첫 인자를 유지한다)
- 원본가·수정주가가 겹치는 구간 **안에는 거래일 구멍이 0일**이다 —
  069500 2,999일 / QQQ 6,908일 / 122630 2,999일 / 251340 2,467일 전부 일치.
  국내 수정주가 창이 짧은 것은 **시작점이 늦은 것이지 중간이 빠진 것이 아니다.**
  따라서 `measure/distribution.py` 의 `pct_change` 는 방어 가드 대상이며 **현재 수치를 바꾸지 않는다**
- `expanding_rank` 재계산 횟수 = 순위 컷 3 × 방향 2 × (시작연도 4 + 시대구간 2) = **데이터셋당 36회** + `_Context` 1회

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「측정의 원칙」 17개, 「후보 판정 기준」, 「계획서 규약 — 이 프로젝트의 설정」
- `src/verify_lab/CLAUDE.md` — 「계층 간 계약」 8종, 「측정 계층의 절대 원칙」 5가지, 「상수 관리」
- `scripts/CLAUDE.md` — 메타 타입 목록, 산출물 저장 규칙
- `tests/CLAUDE.md` — 필수 테스트 3종, Given-When-Then, 부동소수점 비교, 파일 격리
- `.claude/rules/python.md` — 코딩 표준, 반올림 규칙표, 주석 규칙, 「미사용 판정에는 왜 안 쓰이는가가 함께 필요하다」
- `.claude/rules/docs.md` — 문서 종류와 SoT, 수치에 데이터 기간 병기, 용어 대응표
- `.claude/rules/research.md` — 결과 문서 작성 규칙
- `.claude/rules/strategy.md` — 매매 규칙 계층의 예외 규정

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 목표 1~5 충족 (Phase 1~5 체크리스트 전부 `[x]`)
- [x] 비중첩 표본을 두 검증이 **같은 함수**로 계산한다 (호출처 2곳, 정의 1곳)
- [x] 시기 절반 표에 표본 부족 달의 행이 남고 `판정가능` 이 「아니오」로 찍힌다
- [x] 후보 판정 화면 표에 「합산 수익률(%)」이 표본 수와 함께 실린다
- [x] `{ticker}_max.csv` 규칙을 참조하는 곳이 상수 하나를 지난다 (하드코딩 0건)
- [x] `판정가능` 상수가 `measure`/`report` 공통 계층 한 곳에서 나온다 (지금 3곳 중복)
- [x] `TRADING_DAYS_PER_YEAR` 두 개가 **이름으로 갈려** 사양 지정값과 관행값이 구별된다 (값은 불변)
- [x] 해소 가능한 runtime import 2곳이 최상단 import 로 올라갔다
- [x] 회귀/신규 테스트 추가 (Phase 0 에서 먼저 고정)
- [x] `poetry run python validate_project.py` 통과 (failed=0, skipped=0; passed/failed/skipped 수 기록)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 검증 #7·#9 재실행 완료, `docs/research/` 두 문서에 **새 수치와 「무엇이 왜 달라졌는지」** 기록
- [x] 검증 #1·#8 동일성 확인 완료 (수치 불변을 확인하고 결과를 Notes 에 기록)
- [x] 문서 업데이트 — `scripts/CLAUDE.md`(메타 타입 2건 추가), 각 모듈 docstring 12곳, 규칙 문서 이력 정리.
      **`docs/COMMANDS.md`: 변경 없음** (실행 명령어·CLI 옵션이 바뀌지 않음)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 ①~④ 와 실측 3건을 `src/verify_lab/CLAUDE.md` 「계층 간 계약」 및 각 `docs/research/` 로 이관)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

**측정·출력 공통 계층**

- `src/verify_lab/measure/statistics.py` — 비중첩 표본 계산의 **단일 정의**를 여기 둔다 (자체 검증 ③)
- `src/verify_lab/measure/constants.py` — `판정가능` 상수 승격 (자체 검증 ②)
- `src/verify_lab/measure/distribution.py` — 파일명 상수 참조, 구간 연속성 가드, 연율 상수 이름 정리
- `src/verify_lab/report/tables.py` — `build_candidates_table` 에 합산 수익률 추가
- `src/verify_lab/common_constants.py` — 파일명 템플릿 상수

**검증 계층**

- `src/verify_lab/studies/option_expiry/runner.py` — 시기 절반 행 보존 + `판정가능`
- `src/verify_lab/studies/option_expiry/constants.py` — `판정가능` 컬럼·레이블
- `src/verify_lab/measure/screening.py` — 판정가능한 시기 행만 등급에 반영
- `src/verify_lab/studies/futures_leverage/runner.py` — 비중첩 공통화, `NaN` 처리, 제외 사유 상수, runtime import 해소
- `src/verify_lab/studies/futures_leverage/comparison.py` — runtime import 해소, 이자 계산 단일화
- `src/verify_lab/studies/futures_leverage/position.py` — 이자 계산 단일화, `PERCENT_TO_RATE` 제거
- `src/verify_lab/studies/futures_leverage/constants.py` — 미사용 상수 정리
- `src/verify_lab/studies/leverage_tracking/breakdown.py` — 비중첩 공통화
- `src/verify_lab/studies/leverage_tracking/runner.py` — 파일명 상수 참조
- `src/verify_lab/studies/index_extreme/runner.py`·`extreme_move.py` — 순위 재계산 제거

**데이터 계층**

- `src/verify_lab/data/ecos_collector.py` — 잘림 검사 fallback 제거
- `src/verify_lab/data/{yfinance,pykrx,etn,krx_futures}_collector.py` — 파일명 상수 참조

**매매·스크립트**

- `src/verify_lab/strategy/constants.py` — 미사용 상수 정리
- `src/verify_lab/strategy/expiry_runner.py` — 미사용 상수 정리
- `scripts/data/check_kodex_distribution.py` — 파일명 상수 참조

**테스트**

- `tests/test_measure_sampling.py` — 신규
- `tests/test_studies_leverage_breakdown.py`·`test_studies_futures_comparison.py`·`test_studies_expiry_runner.py`·`test_report_tables.py`·`test_ecos_collector.py`·`test_measure_screening.py` — 갱신

**문서**

- `scripts/CLAUDE.md` — 메타 타입 2건 추가
- `src/verify_lab/CLAUDE.md` — 계층 간 계약에 비중첩 정의 추가, 변경 이력 표기 정리
- `.claude/rules/strategy.md`·`docs/INDEX.md` — 변경 이력 표기 정리
- `docs/research/옵션_만기일.md`·`docs/research/선물_대_레버리지_ETF.md` — 재실행 수치 갱신
- `docs/COMMANDS.md`: **변경 없음**

### 데이터/결과 영향

- **출력 스키마 변경 있음**
  - `weekly_trade_by_month_halves.csv` — 행 증가 + `판정가능` 컬럼 추가
  - `candidates.csv` — 컬럼 순서 유지, 화면 표에만 「합산 수익률(%)」 추가
  - `comparison.csv`·`decomposition.csv` — 「비중첩 표본」 값 증가
  - `leverage_drift.csv` — 소진 칸이 `0` → 빈칸(또는 사유)
  - `windows_*.csv`(검증 #9) — 제외 사유 문자열이 `구간 밖` → `구간 끝이 데이터 범위를 넘음`
- **기존 결과 비교 필요**: 검증 #1·#8 은 수치가 **바뀌면 안 된다.** 재실행해 동일성을 확인한다
- **시세 재수집 없음**: `storage/market/` 은 읽기 전용으로 다룬다

## 6) 단계별 계획(Phases)

### Phase 0 — 인바리언트를 테스트로 먼저 고정(레드 허용)

> 해당 사유: **최종 결과(지표 정의·산식·판정 기준)가 달라지는 변경**이고
> **에러 처리 정책 변경**(NaN·잘림 검사)을 포함한다.

**작업 내용**:

- [x] `tests/test_measure_statistics.py` — 비중첩 표본의 단일 정의를 고정한다
      (연속 시작일 · 띄엄띄엄한 시작일 · `horizon=1` · 빈 입력 · **끝점 공유가 «겹치지 않음»으로 세어진다**는 경계 사례)
- [x] `tests/test_studies_leverage_breakdown.py` — **옮기지 않는다.** Phase 1 에서 `breakdown` 이 공통 함수를 재노출하므로 기존 테스트가 그대로 통과하며, 그 자체가 재노출 계약을 검증한다
- [x] `tests/test_studies_futures_runner.py` 신규 — **검증 #9 의 비중첩 값이 검증 #8 과 같은 규칙을 따른다**는 계약 테스트 추가 (레드 확인)
- [x] `tests/test_studies_expiry_runner.py` — 표본 부족 달의 행이 **남고** `판정가능` 이 「아니오」임을 고정 (레드 확인). **기존 테스트 `test_시기_2등분은_표본이_모자란_달을_내지_않는다` 가 원칙 17 위반 동작을 계약으로 박아두고 있어 새 계약으로 교체했다**
- [x] `tests/test_measure_screening.py` — 판정 불가 시기 행이 등급 분모에 들어가지 않음을 고정 (결정 ②, 레드 확인)
- [x] `tests/test_report_tables.py` — `build_candidates_table` 산출에 「합산 수익률(%)」과 「표본」이 함께 있음을 고정 (레드 2건 확인, 기존 37건 통과)
- [x] `tests/test_studies_futures_runner.py` — 전 구간 소진 시 최대 유효 레버리지가 **0.0 이 아님**을 고정 (레드 확인)
- [x] `tests/test_ecos_collector.py` — `list_total_count` 와 `row` 가 없는 응답에서 **예외가 난다**는 것을 고정 (레드 2건 확인, 기존 13건 통과)
- [x] 파일명 상수 존재·유일성을 불변조건 테스트로 고정 (`tests/test_common_constants.py`, 레드 3건 확인)

---

### Phase 1 — 측정 오류와 버그 수정(그린 유지)

**작업 내용**:

- [x] **1-1** `measure/statistics.py` 에 `max_non_overlapping(start_positions, horizon)` 하나를 두고
      **결정 ①의 근거를 docstring 에 적는다** (자체 검증 ③)
- [x] **1-1** `leverage_tracking/breakdown.py` 의 `max_non_overlapping` 을 공통 함수 재노출로 바꾸고,
      `futures_leverage/runner.py` 의 `_non_overlapping_count` 를 제거해 공통 함수를 부른다
- [x] **1-2** `measure/constants.py` 로 `COL_JUDGEABLE`·`JUDGEABLE_YES`·`JUDGEABLE_NO` 를 승격하고,
      `leverage_tracking/constants.py`·`strategy/constants.py` 의 기존 정의를 재노출로 바꾼다 (자체 검증 ②).
      표시 레이블 `DISPLAY_JUDGEABLE` 은 `report/constants.py` 로 올린다 (지금 세 곳에 같은 문자열이 있다)
- [x] **1-2** `option_expiry/runner.py` `_aggregate_month_halves` — `continue` 를 없애고
      표본 부족 달도 행을 남긴 뒤 지표를 비우고 `판정가능` 을 「아니오」로 채운다
- [x] **1-2** `option_expiry/constants.py` `OUTPUT_LABELS` 에 `판정가능` 을 연결한다
      (**`DISPLAY_*` 를 정의만 하고 rename 에 연결하지 않으면 규칙을 지킨 것이 아니다**)
- [x] **1-2 · 결정 ②** `measure/screening.py` — 시기 항목이 **판정가능한 행만** 읽도록 필터를 넣고,
      그 이유를 docstring 에 적는다. 판정 결과가 바뀌지 않아야 한다
- [x] **1-3** `report/tables.py` `build_candidates_table` — `DISPLAY_TOTAL_RETURN` 을
      「방향 기대값(%)」 바로 뒤에 넣는다 (측정의 원칙 16: 회당·합산·표본을 같은 표에)
- [x] **2-1** `futures_leverage/runner.py` `_max_effective_leverage` — 잴 수 있는 칸이 하나도 없으면
      `0.0` 이 아니라 `NaN` 을 유지하도록 고치고, `np.nanmax` 의 All-NaN 경고 경로를 없앤다
- [x] **2-2** `data/ecos_collector.py` — `body.get(KEY_ROW, [])` 와 `body.get(KEY_TOTAL_COUNT, len(rows))` 의
      **기본값을 없애고** 키가 없으면 `ValueError` 를 던진다

**Validation**:

- [x] Phase 0 의 레드 테스트가 전부 그린이 된다 — `pytest tests/` **855 통과 · 3 실패**.
      남은 3건은 Phase 2 에서 만들 파일명 상수를 미리 고정한 것이라 Phase 1 범위 밖이다

---

### Phase 2 — 상수 통합과 중복 계산 제거(그린 유지)

**작업 내용**:

- [x] **3-1** `common_constants.py` 에 원시 시세 파일명 템플릿 상수를 두고
      (`MARKET_FILE_TEMPLATE` · `ADJUSTED_FILE_TEMPLATE` 등) **9곳이 전부 그것을 지나게** 한다.
      선물은 `{product_id}` 라 키 이름이 다르므로 별도 상수로 둔다
- [x] **3-3 · 자체 검증 ①** `TRADING_DAYS_PER_YEAR` 를 **이름으로 가른다. 값은 둘 다 유지한다** —
      `usdkrw` 쪽은 사양서가 지정한 값임이 이름에 드러나게 바꾸고, `measure` 쪽은 관행값임을 유지한다.
      **두 곳의 주석에 「값이 다르며 왜 다른가」를 서로 가리키게 적는다** — 지금은 같은 이름이라
      다음 사람이 통일하려 든다. `DAYS_PER_YEAR`(usdkrw, 365)와 `CALENDAR_DAYS_PER_YEAR`(futures, 365)도
      같은 뜻이므로 이쪽은 **한 이름으로 합친다**
- [x] **3-2**(7-해소에 필요) `futures_leverage/position.py` 의 `PERCENT_TO_RATE` 를 없애고
      `common_constants.RATE_TO_PERCENT` 를 쓴다. `CALENDAR_DAYS_PER_YEAR` 는 `constants.py` 로 올린다
- [x] **4-1 · 자체 검증 ④** `index_extreme` 의 확장창 순위 재계산 제거 —
      `find_extreme_move_events` 에 순위 인자를 추가하되 **기본값 `None`(내부 계산)을 유지**하고
      `_Context` 의 값을 넘긴다. `strategy/runner.py:230` 은 `_Context` 가 없어 기본값에 의존한다.
      **신호 집합이 바뀌면 안 된다** (동일성은 Phase 4 에서 확인)
- [x] **4-2** 이자 누적 계산 단일화 — `position._daily_interest_rates` 와
      `comparison.build_interest_factor` 의 공통 부분을 한 함수로 모은다 (절대 원칙 5)
- [x] **2-3** `futures_leverage/runner.py` 의 `"구간 밖"` 리터럴을 `REASON_OUT_OF_RANGE` 로 바꾼다.
      `comparison.build_window_table` 이 같은 일을 이미 하므로 **그 함수를 쓰거나, 못 쓰는 이유를 주석에 남긴다**

---

### Phase 3 — 미사용 정의 정리와 runtime import 해소(그린 유지)

> `.claude/rules/python.md` 「미사용 판정에는 「왜 안 쓰이는가」가 함께 필요하다」를 따른다.
> **세 종류로 분류한 뒤** 지울 것과 연결할 것을 가른다.

**작업 내용**:

- [x] **5-3** `futures_leverage/constants.py` 미사용 13건 분류표를 만든다
      (①필요 없어서 ②결론이 난 축의 잔여물 ③연결을 빠뜨려서)
- [x] **5-3** ①②로 판정된 것은 지운다 (`METHODS`·`ROLL_EXECUTION_LAG_DAYS` 등)
- [x] **5-3** ③으로 판정된 것은 **쓰게 만들거나**, 축 자체가 구현되지 않은 경우
      (`REFERENCE_MULTIPLES`·`INTEREST_ASSUMPTIONS`) **주석이 「낸다」고 적은 것과 코드가 어긋난 사실을
      사용자에게 보고하고 판단을 받는다** — 임의로 지우면 하드코딩이 정답인 것처럼 굳는다
- [x] **5-4** 나머지 미사용 정의 정리 — `DISPLAY_HOLD_LIMIT`·`HOLD_LIMIT_PREFIX`·
      `IDENTITY_COLUMNS`/`IDENTITY_COLUMNS_WITH_STOP`(expiry_runner)·`IDENTITY_COLUMNS`(leverage_tracking)·
      `BLD_FUTURES_ALL_PRICE`·`COL_RETURN`·`COL_PRODUCT_ID`·`KRX_COL_DATE`·
      `leverage_tracking/constants.py` 의 `COL_INDEX_NAME` 등 5건
- [x] **7** `comparison.py:258` 의 함수 내부 import 를 최상단으로 올린다 (순환 없음을 확인하고 진행)
- [x] **7** `futures_leverage/runner.py:510` 의 함수 내부 import 를 기존 최상단 import 목록에 합친다
- [x] **7** KRX 로그인 순서 때문에 **남겨야 하는 runtime import 7곳**은 그대로 두고,
      각 docstring 이 이유를 적고 있는지 확인한다 (근본 해결 불가임을 계획서 Notes 에 남긴다)

---

### Phase 4 — 재실행과 결과 문서 갱신

> **시세를 재수집하지 않는다.** `storage/market/` 은 읽기만 한다.
> 재실행 명령은 `docs/COMMANDS.md` 를 따른다.

**작업 내용**:

- [x] **자체 검증 ⑤** 대조 전 준비 — 직전 산출물 4종(`20260830_200537_index_extreme` ·
      `20260830_164316_option_expiry` · `20260905_103244_leverage_tracking` ·
      `20260905_085938_futures_leverage`)의 `summary.json` 이 적은 **데이터 기간·행 수**를
      현재 `storage/market/` 파일과 대조한다. **어긋나면 그 검증은 동일성 확인을 포기하고 사유를 기록한다**
- [x] 검증 #1(`index_extreme`) 재실행 — **수치가 그대로여야 한다.** 4-1 이 값을 바꾸지 않았음을 확인하고
      직전 산출물과 대조한 결과를 Notes 에 기록한다
- [x] 검증 #8(`leverage_tracking`) 재실행 — 결정 ①이 #8 기준이라 비중첩은 불변이다.
      다만 **3-3 의 연율 상수 이름 정리로 `distribution.csv` 의 「연율 분배 기여(%)」 값은 그대로여야** 하므로
      그것까지 대조한다 (값을 바꾸지 않는 것이 이번 처리의 핵심이다)
- [x] 검증 #7(`option_expiry`) 재실행 — `weekly_trade_by_month_halves.csv` 행 수 증가와
      `candidates.csv` 불변(결정 ②)을 확인한다
- [x] 검증 #9(`futures_leverage`) 재실행 — 「비중첩 표본」 증가분과 `leverage_drift.csv` 의 빈칸을 확인한다
- [x] `docs/research/옵션_만기일.md` 갱신 — 새 수치, **데이터 기간과 행 수 병기**,
      「무엇이 왜 달라졌는지」(시기 절반 행 복원, 판정 불변) 기록
- [x] `docs/research/선물_대_레버리지_ETF.md` 갱신 — 새 비중첩 수치와
      「비중첩 정의를 검증 #8 과 통일했다」는 사실·근거 기록
- [x] 두 문서의 **판정 문장이 바뀌는지** 확인한다. 바뀌면 사용자에게 보고하고 승인받는다

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [x] **10-1** `scripts/CLAUDE.md` 메타 타입 목록에 `expiry_trading_strategy`·`expiry_dividend_probe` 추가
- [x] **10-2·10-3·10-4** `futures_leverage/runner.py` 모듈 docstring — 「3방식」→ 실제 방식 수,
      `windows_<지수>_<배수>.csv` → 실제 파일명 규칙, `integer_contracts.csv` 누락 보완
- [x] **10-5** `leverage_tracking/runner.py` — 「산출물은 넷이다」 vs 다섯 줄 표 정리
- [x] **10-6** `index_extreme/runner.py` — 삭제된 「테스트 B」·「연속 상승」 서술 제거 (12-가 중 이 2건은 10-6과 같은 지점이라 함께 고친다)
- [x] **10-7** `data/loader.py` 모듈 docstring 표 — 선물의 0 이하 값 판정 실제와 맞춘다
- [x] **10-8** `data/pykrx_collector.py` — 「부호 있는 정수로 고정」 서술을 실제 흐름(정규화=float, 저장 직전=int64)과 맞춘다
- [x] **10-9** `option_expiry/runner.py` — 시기 절반 하한 서술을 Phase 1 결과와 맞춘다
- [x] **10-10** `futures_leverage/position.py`·`comparison.py` — `run_position` 이 테스트 오라클임을 명시
- [x] **10-11** `usdkrw_equivalence/runner.py` — `_drift_frame`·`_daily_frame` docstring 에 `source` 인자 추가
- [x] **10-12** `data/__init__.py` — docstring 을 실제 공개 범위와 맞춘다 (공개 API 확장은 Non-Goal)
- [x] **12-(나) · 결정 ④** `src/verify_lab/CLAUDE.md` 6곳 — 「(2026-08-30 축소)」 같은 날짜 표기와
      「전에는 …였습니다」 서술을 걷어내고 **탈락안과 근거는 현재형으로 다시 적는다**
- [x] **12-(나)** `.claude/rules/strategy.md`·`scripts/CLAUDE.md`·`docs/INDEX.md` 의 날짜 기반 이력 정리
      (「git 이력에서 꺼낸다」 같은 계획 문장은 **결정 ④에 따라 유지**)
- [x] **근거 승격** — 결정 ①(비중첩 정의)을 `src/verify_lab/CLAUDE.md` 「계층 간 계약」에 추가,
      결정 ②③을 각 `docs/research/` 에 기록, 실측 3건을 해당 문서로 이관
- [x] 자동 포맷 적용 — `poetry run black .`
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [x] `poetry run python validate_project.py` (passed=862, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 측정 / 비중첩 표본 정의를 단일화하고 표본 부족 구간의 행이 사라지지 않게 고침
2. 측정 / 조용히 틀린 값을 내던 세 지점을 막고 회당 기대값 옆에 합산 수익률을 붙임
3. 측정 / 두 검증이 갈라져 있던 지표 정의와 제외 사유를 하나로 모음
4. 측정 / 파일명·단위 상수를 통합하고 확장창 순위 재계산을 제거
5. 문서 / 코드와 어긋난 설명 12곳과 규칙 문서의 변경 이력을 정리

## 7) 리스크(Risks)

| 리스크 | 완화책 |
| --- | --- |
| **결정 ①로 검증 #9 의 비중첩 수치가 바뀐다** | Phase 4 에서 재실행하고 `docs/research/선물_대_레버리지_ETF.md` 에 변경 사실과 근거를 적는다. 판정 문장이 바뀌면 사용자 승인을 받는다 |
| **결정 ②의 필터를 잘못 넣으면 후보 판정이 조용히 달라진다** | Phase 0 에서 「판정 불변」을 테스트로 먼저 고정하고, Phase 4 에서 `candidates.csv` 를 직전 산출물과 대조한다 |
| **4-1(순위 재계산 제거)이 신호 집합을 바꿀 수 있다** | 기존 look-ahead 감시 테스트를 유지하고, Phase 4 에서 검증 #1 산출물의 신호일 목록을 직전과 완전 일치로 대조한다 |
| **미사용 상수를 지우다 「연결을 빠뜨린」 것을 지운다** | Phase 3 에서 세 종류로 분류표를 먼저 만들고, ③(연결 누락)은 지우지 않고 사용자에게 보고한다 |
| **`storage/results/` 는 다른 PC 로 동기화되지 않는다** | 재실행 결과를 문서로 승격하고, 산출물 폴더에 의존하는 서술을 남기지 않는다 |
| **파일명 상수 통합이 수집기 경로를 바꿔 기존 파일을 못 읽게 만든다** | 상수 값은 현재 문자열과 **완전히 동일**하게 두고, 통합 후 `storage/market/` 의 파일을 실제로 로딩해 확인한다 |

## 8) 메모(Notes)

### 범위 근거

- 전수 분석 87건 중 사용자가 우선순위 제안 15건 + 12-(나)를 선택했다.
  나머지는 「2) 비목표」에 명시했고 다음 기회에 별도 판단한다.
- **3-2 는 원래 범위 밖이었으나 7(runtime import 해소)에 필요해 끌려 들어왔다** —
  `comparison.py:258` 이 `position.py` 에서 `PERCENT_TO_RATE`·`CALENDAR_DAYS_PER_YEAR` 를 가져오므로,
  두 상수를 `constants.py`/공통으로 올려야 최상단 import 가 깔끔해진다.
- **12-가 중 2건(테스트 B 서술)은 10-6 과 같은 지점**이라 마지막 Phase 에서 함께 고친다.
  나머지 12-가 4건은 범위 밖이다.

### 남겨야 하는 runtime import 7곳 (근본 해결 불가)

`import pykrx` 자체가 로그인을 시도하므로, 자격증명을 환경 변수에 올린 **뒤에** import 해야 한다.
최상단 import 는 그 순서를 구조로 보장하지 못한다(줄을 옮기면 조용히 깨진다).

- `data/pykrx_collector.py:123` · `data/etn_collector.py:149-150` · `data/krx_futures_collector.py:207-208`
- `scripts/data/check_pykrx_etf.py:318` · `scripts/data/check_pykrx_splice.py:409`

`src/verify_lab/` 의 `# type: ignore` 2건(`etn_collector.py:196`·`krx_futures_collector.py:437`)도
같은 원인이다 — 기반 클래스가 runtime import 로 와서 `Any` 가 된다. **이번 범위 밖이며**,
세 수집기의 KRX 클라이언트 헬퍼를 공용화(4-4)할 때 억제 지점을 한 곳으로 줄이는 것이 실익이 크다.

### 진행 로그 (KST)

- 2026-09-05 21:14: 계획서 작성. 전수 분석 87건 중 우선순위 15건 + 12-(나) 를 범위로 확정
- 2026-09-05 21:14: 결정 ①~④ 사용자 승인 (비중첩=검증 #8 정의 / 시기 행=산출물만 복원 / 재실행=영향분만 / 문서=날짜·과거형만 제거)
- 2026-09-05 21:14: 실측 — `max(0.0, nan)==0.0` 확인, 원본가·수정주가 겹침 구간의 거래일 구멍 0일 확인(4종목)
- 2026-09-05 22:52: **마지막 Phase 완료 · Done.** `validate_project.py` **passed=862 · failed=0 · skipped=0**.
  · 문서 불일치 12곳과 규칙 문서의 날짜 표기를 정리했다. 결정 ④대로 **날짜와 「전에는 …였습니다」만
    걷어내고 탈락안·근거는 현재형으로 남겼다** — 「git 이력에서 꺼낸다」 같은 계획 문장은 유지
  · **근거 승격**: 결정 ①을 `src/verify_lab/CLAUDE.md` 「계층 간 계약」에 **비중첩 표본 계약**으로
    추가했다(계약 8종 → 9종, `docs/INDEX.md` 도 함께 갱신). 결정 ②③은 두 `docs/research/` 문서의
    「재실행 기록」 절에 있다
  · **PyRight 가 마지막에 한 건 잡았다** — `Index.get_loc` 은 슬라이스도 돌려줄 수 있어 위치 계산에
    쓰면 안 된다. `list(...).index(...)` 로 바꿨다
- 2026-09-05 22:35: **Phase 4 완료.** 네 검증을 재실행했고 **변화가 완전히 분리됐다.**
  · **자체 검증 ⑤가 적중했다** — QQQ·069500 이 산출물 생성 뒤 7거래일씩 재수집돼 있었다.
    `index_extreme`·`option_expiry` 는 직전 산출물과 단순 대조가 성립하지 않는다
  · **코드 변경이 값을 바꾼 곳은 검증 #9 의 「비중첩 표본」 하나뿐이다.**
    시세가 그대로인 대조군에서 확인했다 — #8 의 KOSDAQ150·S&P500·다우 **전 컬럼 동일**,
    #7 의 SPY·DIA **전 컬럼 동일 · 1차 판정 뒤집힘 0**, #9 의 KOSDAQ150 **`비중첩 표본`만**
  · **4-1(순위 재계산 제거)의 무해함은 재실행이 아니라 코드로 증명했다** — 시세가 늘어
    대조가 성립하지 않으므로, `ranks` 를 넘긴 경로와 내부 계산 경로가 같은 신호를 낸다는
    테스트를 넣었다. 재실행에서도 신호 915행이 완전히 같았고 꼬리 5건의 NaN 만 채워졌다
  · **비중첩 증가 패턴이 정의 변경의 산술과 일치한다** — 5일 +20%(`n/5` 대 `n/6`), 756일 +0
  · **1-2(시기 절반 행 복원)는 현재 데이터에서 복원된 행이 0개**다. 12개 만기월이 전부
    하한을 넘어 버려진 달이 애초에 없었다. 회귀 방지 장치로 남는다
- 2026-09-05 22:18: **Phase 3 대부분 완료.** 859 통과 · 린트 통과 · 해소 대상 runtime import 0건.
  미사용 20건을 분류해 **18건 삭제 · 1건 연결 · 1건 보류**했다.
  · **연결(③)**: `INTEREST_ASSUMPTIONS` — 실행 계층이 `(True, False)` 를 인라인으로 순회하고
    있었다. 축은 이미 구현돼 있었고 상수만 안 쓰고 있었으므로 쓰게 만들었다
  · **삭제(②) 중 판단이 갈릴 뻔한 것**: `ROLL_EXECUTION_LAG_DAYS` — 「판정 후 다음 거래일 집행」은
    미결제약정이 장 마감 후 공표되기 때문이라 **구조이지 노브가 아니다.** 상수로 두면 조정
    가능한 것처럼 읽히고, `later[LAG - 1]` 로 연결하면 0 일 때 마지막 원소를 집는 함정이 생긴다.
    이유는 `continuous.py` 주석에 이미 있으므로 상수만 지웠다
  · **보류였던 `REFERENCE_MULTIPLES` 는 사용자가 「지우고 이유를 남긴다」로 확정**(2026-09-05).
    「국내 법정 상한이 ±2배라 대조할 ETF 가 없고, 이 검증은 «선물과 ETF 중 어느 쪽이 싼가»를
    묻는 대조라 짝 없는 배수는 답할 질문이 없다」를 `PAIRS` 주석으로 옮겼다
- 2026-09-05 22:05: **Phase 2 완료.** 859 통과 · 린트 통과. 세 가지를 기록해 둔다.
  ① 파일명 하드코딩 0건 달성 (수집기 4·측정 1·검증 4·스크립트 2 곳이 상수 하나를 지난다).
  ② 3-3 은 **이름 분리**로 끝났다 — `SPEC_TRADING_DAYS_PER_YEAR`(250, 사양서 지정) 대
  `TRADING_DAYS_PER_YEAR`(252, 관행). 반면 `DAYS_PER_YEAR`/`CALENDAR_DAYS_PER_YEAR` 는 뜻이
  같아 공통 계층의 `CALENDAR_DAYS_PER_YEAR` 하나로 합쳤다.
  ③ **2-3 을 고치며 `build_window_table` 이 되살아났다** — runner 가 같은 표를 인라인으로 다시
  조립하면서 제외 사유만 다른 문자열을 쓰고 있었다. 함수를 쓰게 하니 둘이 한 번에 풀렸다.
  ④ **린트가 잠재 버그를 잡았다** — `_half_block` 의 빈 절반 경로에서 `COL_SAMPLE_COUNT` 가
  미정의였는데 테스트가 그 경계를 안 밟고 있었다. 경계 테스트를 추가했다
- 2026-09-05 21:47: **Phase 1 완료.** 855 통과. `MIN_SAMPLE_FOR_HALVES` 가 월 단위 건너뛰기
  제거로 orphan 이 되어 함께 지웠다 — 절반별 판정은 `MIN_SAMPLE_FOR_TEST`(10) 하나로 충분하며,
  20 이라는 파생 상수를 남기면 한쪽만 바뀌었을 때 조용히 갈라진다
- 2026-09-05 21:33: **Phase 0 완료.** 계약 테스트 9종 작성, 전부 의도한 레드 확인.
  기존 테스트 하나(`test_시기_2등분은_표본이_모자란_달을_내지_않는다`)가 **측정의 원칙 17 위반 동작을
  계약으로 박아두고 있어** 새 계약으로 교체했다 — `tests/CLAUDE.md` 9절이 경고한 「픽스처가 코드와
  같은 가정을 하면 그 버그는 영원히 안 잡힌다」의 테스트판이다
- 2026-09-05 21:26: 계획서 자체 검증 후 5건 수정. **①이 특히 중요하다** — 3-3 을 「값 통일」로 잡았던 초안이
  틀렸다. `usdkrw` 의 250 은 사양서 §16.2·§16.3 지정값이라 통일했다면 추적오차·알파의 합격 판정을
  근거 없이 흔들었을 것이다. 나머지는 상수 중복 신설 방지(②)·모듈 신설 철회(③)·호출처 2곳 보호(④)·
  대조 전제 확인(⑤)

---
