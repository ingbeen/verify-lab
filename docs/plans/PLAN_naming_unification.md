# Implementation Plan: 매매법 이름과 산출물 «자리»를 통일한다 (작업 B)

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

**작성일**: 2026-09-10 18:05
**마지막 업데이트**: 2026-09-11 11:52
**관련 범위**: studies, strategy, scripts, report, utils, docs
**관련 문서**: 루트 `CLAUDE.md`, `src/verify_lab/CLAUDE.md`, `scripts/CLAUDE.md`, `.claude/rules/docs.md`, `.claude/rules/strategy.md`, `tests/CLAUDE.md`

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

- [x] 목표 1: **매매법마다 slug 를 하나로 통일한다** — 같은 매매법이 계층마다 다른 단어로 불리는 것을 없앤다
- [x] 목표 2: **매매 계층의 공유 로직을 매매법-중립 모듈로 빼고**, 매매법마다 `<slug>_runner.py` 하나만 둔다 —
      매매법 사이를 건너는 import 를 없앤다 (2026-09-11 개정, 근거는 8절 「실측으로 무너진 전제」)
- [x] 목표 3: **산출물을 `storage/results/{검증, 매매, 실측}/<시각>_<slug>/` 로 나눈다** — 계층이 경로에서 드러나게 한다
- [x] 목표 4: **문서 파일명과 문서 안에서 부르는 이름을 매매법당 하나로** 맞춘다

## 2) 비목표(Non-Goals)

- **산출물 «파일 이름»과 «컬럼»은 건드리지 않는다** — 작업 C(`PLAN_output_layout.md`)의 범위다.
  이 계획서는 「어디에 무엇이라 부르며 두는가」까지이고, 그 안에 무엇이 담기는지는 C 가 정한다
- **재실행하지 않는다.** 재실행은 **작업 C 완료 후 한 번만** 한다 (2026-09-10 사용자 결정)
- **기존 22개 산출물 폴더를 옮기거나 리네임하지 않는다.** 살아있는 문서 6개가 그 이름을 인용하고 있어
  옮기면 전부 깨진다. **새 규약은 앞으로 나오는 산출물부터** 적용한다
- **판정 기준·측정 산식을 건드리지 않는다.** 작업 A 에서 끝났다
- **`docs/plans/` 의 계획서는 개명 대상이 아니다** — 임시 산출물이다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

**같은 매매법이 계층마다 다른 이름으로 불린다.** 사용자가 실제로 헷갈린 사례에서 출발했다 —
`20260831_175819_option_expiry` 와 `20260831_180611_expiry_trading` 을 보고 **「옵션 만기일 매매는
당연히 `option_expiry` 인 줄 알았는데 `expiry_trading` 이더라」** 고 했다.

**조사해 보니 그 둘은 옛것/새것이 아니라 «같은 매매법의 두 계층»이었다.**

| 폴더 | 계층 | 내용 |
| --- | --- | --- |
| `option_expiry` | 측정(`studies/`) | 검증 #7 — 만기 전후 -10~+10일 격자, 기준선·우연확률 |
| `expiry_trading` | 매매(`strategy/`) | 확정된 매매 규칙의 성적 — 승률·손절·보유일 |

**즉 원인은 「잔재가 남은 것」이 아니라 「이름에 계층이 드러나지 않는 것」이다.**

### 확정된 결정 (2026-09-10 사용자와 합의)

**다른 세션이 이어받을 수 있도록 결정과 그 근거를 전부 남긴다.**

| # | 결정 | 사용자 선택 | 근거 |
| --- | --- | --- | --- |
| 1 | 통일 대상은 **`strategy/` 계층만** (컬럼·파일명 기준) | Q1 ① | 측정 계층은 방향이 미정이라 「승률」을 못 쓰고(`.claude/rules/docs.md` 용어 대응표), 기준선·우연확률 축을 버릴 수 없어 **파일을 2개로 줄일 수 없다** |
| 2 | 산출물 파일명은 **한글** (`성적표.csv`·`거래내역.csv`) | Q2 ① | CSV **헤더는 이미 전부 한글**이다(`src/verify_lab/CLAUDE.md` 「내부/출력 분리」). 파일명만 영문일 이유가 없다. **작업 C 의 범위** |
| 3 | 산출물 폴더를 **`검증`/`매매`/`실측` 상위 폴더로 분리** | 2라운드 #2 | 사용자가 **「결론적으로 나는 strategy 를 주로 볼 것」**이라고 밝혔다. 경로가 계층을 말하므로 **폴더명 접미사(`_study`/`_strategy`)는 불필요해졌다** |
| 4 | 상위 폴더 이름은 **한글 `검증`·`매매`·`실측`** | 2라운드 #2 답 「검증」 | 루트 `CLAUDE.md` 가 실제로 쓰는 말이다(「검증 #1·#7·#10」). 후보였던 `measure` 는 `src/verify_lab/measure/` 와 겹쳐 기각, `research` 는 `docs/research/`(결과 문서)와 뜻이 어긋나 기각 |
| 5 | **매매법 이름을 하나로 통일하고 계층은 폴더가 말한다** | Q4 ① | 사용자가 ①을 골랐다. **제 추천은 ②(대응표만 두기)였으나 기각됐다** — 그 근거는 아래 「기각된 안」에 남긴다 |
| 6 | 스크립트는 **안 B** — `run_<slug>_study.py` / `run_<slug>_trading.py` | 3라운드 | 접미사를 양쪽 다 붙인다. **안 A(양쪽 다 생략)를 기각한 이유**: `⌘P` 로 파일을 여는 워크플로에서는 폴더가 안 보여 `run_reverse.py` 두 개 중 어느 것인지 매번 경로를 확인해야 한다 |
| 7 | **문서 파일명과 문서 내부 명칭도 통일** | 2라운드 #6 | 1라운드에서 「문서명 유지」를 추천했으나 사용자가 뒤집었다 |
| 8 | 진행 순서 **A → B → C**, 재실행은 **C 후 한 번만** | Q6 ① | 폴더가 매매법당 1개만 늘고 결과 문서를 한 번만 고친다 |

### 기각된 안과 그 이유 (되살리기 전에 읽을 것)

| 기각된 안 | 왜 기각했나 |
| --- | --- |
| **`option_expiry` 를 아카이브·삭제** | **살아있는 문서 둘이 인용 중**이다 — `docs/research/옵션_만기일.md` · `docs/strategy/투자금_결정.md`. 게다가 `.claude/rules/docs.md` 가 「아카이브 폴더를 만들지 않는다」를 명시하고, `tests/test_result_citations.py` 가 인용된 폴더의 부재를 품질 검증 실패로 잡는다 |
| **quant-notify 의 영문 이름을 기준으로 삼기** | quant-notify 에 있는 것은 **알림 모듈 이름**이지 매매법 이름이 아니다(`alerts/reverse_rank.py` · `usdkrw.py` · `buffer_zone.py`). 한글 이름은 `docs/DESIGN.md:165-167` 에 **3개**뿐이고 그중 옵션 만기일은 알림을 만들지 않는다. **verify-lab 의 7개 중 3개만 대응되고 영문은 성격이 다르다** |
| **폴더명에 계층 접미사(`_study`/`_strategy`)** | 상위 폴더로 나누기로 하면서 **중복**이 됐다 |
| **각 폴더에 `README` 한 줄만 두기** | 폴더 목록만 봐서는 여전히 구별이 안 된다 — 원래 문제가 그대로 남는다 |

### 조사로 확인한 사실 (숫자)

**이 조사를 다시 하지 않아도 되도록 결과를 남긴다.**

#### 폴더 이름을 만드는 상수의 소유자

| 폴더 접미사 | 정의 위치 | 비고 |
| --- | --- | --- |
| `index_extreme` 외 5개 | `src/verify_lab/studies/<이름>/constants.py` 의 `STUDY_NAME` | 정상 |
| `reverse_trading` · `expiry_trading` | `src/verify_lab/strategy/constants.py` (`STRATEGY_NAME` · `EXPIRY_STRATEGY_NAME`) | 정상 |
| **`kosdaq_month_end_trading`** | **`scripts/strategy/run_month_end_trading.py:45`** | **CLI 에 하드코딩. 상수명이 `STUDY_NAME` 으로 잘못 붙어 있고, 코스피까지 확장됐는데 `kosdaq_` 이 남아 있다** |
| `ecos_probe` | `scripts/data/check_ecos.py:34` (`PROBE_NAME`) | 실측 |

#### 리네임 규모 (파일 수)

| 대상 | 코드 파일 | 문서 |
| --- | ---: | ---: |
| `index_extreme` → `reverse` | **27** | 10 |
| `expiry_trading` → `option_expiry_trading` | 8 | 10 |
| `kosdaq_month_end_trading` → `month_end` | 2 | 8 |

`index_extreme` 27개의 내역: `src` 14 · `scripts` 6 · `tests` 7. 대부분은 import 경로와 주석 언급이고
**실제 구조 변경은 패키지 폴더 1개 + 스크립트 1개 + 테스트 파일명**이다.

#### 매매 계층 모듈 구성 — 실측 (2026-09-11 전수 확인)

**초안의 「월말은 체결 모듈이 없다」는 틀렸다.** 월말은 체결을 못 쓰는 것이 아니라 **이미 100%
빌려 쓰고 있어 자기 파일에 넣을 것이 없다.** `_trade_row` 는 체결이 아니라 체결 결과를 표 한 줄로
바꾸는 포매터다.

**매매법-중립 로직 셋이 매매법 이름을 가진 파일 안에 있고, 셋이 사슬로 빌려 쓴다.**

| 공유되는 것 | 지금 사는 곳 | 빌려 쓰는 쪽 |
| --- | --- | --- |
| `TradeResult` · `simulate_signal` — 시가→장중→종가 판정식 | `reverse_trading.py` (**역방향**, 170줄) | 옵션 만기일 → 월말 |
| `simulate_expiry_trade` · `_scheduled_exit` — 달력 청산·무손절 | `expiry_trading.py` (**옵션 만기일**, 138줄) | 월말 |
| `period_rows` · `_period_row` — 구간 5행 성적 산식 | `expiry_runner.py:363` (**옵션 만기일**, 529줄) | 월말 |

그래서 `month_end_runner.py:50-51` 이 **옵션 만기일 모듈 두 개를 import** 한다 — 서로 무관한
매매법인데도. 월말이 사슬의 끝이라 자기 것이 없다.

| 매매법 | 실행 모듈 | 고유 체결 로직 |
| --- | --- | --- |
| 역방향 | **`runner.py`** — slug 가 없다 | 판정식 본체 + 중간 익절 |
| 옵션 만기일 | `expiry_runner.py` (529줄) | 달력 청산 + 무손절 경로 |
| 월말 | `month_end_runner.py` (430줄) | **없다** — 규칙이 옵션 만기일과 같다 |

#### 산출물 폴더의 인용 관계

- **살아있는 문서가 인용하는 폴더는 옮기거나 지울 수 없다.** `tests/test_result_citations.py` 가 검사한다
- **진짜 잔재는 `kosdaq_month_end` 3폴더다** — 8대상 통합본 `month_end` 로 대체됐고 인용처가
  계획서(임시 문서)뿐이라 `/clean-results` 대상이다
- 작업 A 로 **산출물 폴더 7개**가 새로 생겼고 **2개만 문서가 인용**한다
  (`20260910_175212_expiry_trading` · `20260910_175213_reverse_trading`). 나머지 다섯도 정리 대상

#### 한글 경로가 안전한 이유 (실측)

| 확인 항목 | 결과 |
| --- | --- |
| `git config core.precomposeunicode` | **`true`** — mac/Windows 사이에서 한글 파일명이 깨지지 않는다 |
| 결과 문서가 산출물을 인용하는 방식 | **마크다운 링크가 아니라 인라인 코드**다 (`> **산출물**: \`storage/results/...\``). 한글 경로로 바꿔도 **깨질 링크가 없다** |

🔴 **인용 판정기와 정리 도구를 반드시 고쳐야 한다. 다만 고칠 곳은 초안이 지목한 자리가 아니다**
(2026-09-11 실측).

| 초안의 진단 | 실측 |
| --- | --- |
| `result_citations.py:23` 의 정규식이 소문자 ASCII 를 요구해 새 경로를 놓친다 | **정규식은 고칠 필요가 없다.** 한글은 **상위 폴더 이름**에만 들어가고 산출물 폴더 이름 자체는 `<시각>_<slug>` 로 계속 ASCII 다. `storage/results/매매/20260911_120000_reverse` 에서도 `\b` 가 `/` 뒤에서 걸려 그대로 잡힌다 |
| 안 고치면 `/clean-results` 가 인용 중인 폴더를 삭제 후보로 낸다 | **고칠 곳은 `existing_result_dirs()` 의 «탐색 깊이»다.** 한 단계 깊어진 폴더를 못 찾으면 `missing_citations` 에 걸려 **품질 검증이 실패한다**(조용하지 않다). 삭제 후보 쪽은 오히려 비어서 안전해진다 |

🔴 **정작 조용히 깨지는 것은 `scripts/maintenance/clean_results.py` 다.** 폴더를 **이름으로만**
들고 다녀 경로를 잃는다.

- `_directory_size(RESULTS_DIR / name)` — 없는 경로에 `rglob` 을 돌려 **예외 없이 `0.0MB`** 를 낸다
- `_tracked_dirs()` 의 `line.split("/")[2]` — `storage/results/매매/<폴더>/...` 에서 **`매매` 를 집는다.**
  추적 판정이 전부 어긋나 「되돌릴 수 없음」 경고가 거짓이 된다
- `shutil.rmtree(RESULTS_DIR / name)` — 여기서야 `FileNotFoundError` 가 난다

그래서 **이름 → 경로 대응을 `result_citations.py` 가 소유**하게 하고(인용의 정의를 한 모듈이
갖는다는 기존 계약의 연장) 정리 도구가 그것을 쓴다.

🔴 **두 실측 스크립트가 폴더 생성을 복제하고 있다.** `check_pykrx_etf.py:83` 과
`check_pykrx_splice.py:147` 이 `create_run_directory` 를 쓰지 않고 `RESULTS_DIR / f"{...}_{...}"` 를
직접 조립한다. 고치지 않으면 **그 둘만 옛 자리에 계속 쌓인다** — `report/writer.py` 의 머리말이
경고한 바로 그 갈라짐이다.

#### 문서 안에서 매매법을 부르는 말이 갈려 있다

| 표현 | 출현 |
| --- | ---: |
| **역방향** | 65회 |
| 역대급 등락 | 36회 |
| 지수_극단 / 지수 극단 | 17회 |
| 극단 이벤트 | 9회 |

`docs/spec/` 7개는 **전부 영문 파일명**이고, `docs/research/`·`docs/strategy/` 는 한글이다.

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 「공통 계층과 개별 검증의 경계」, 「실행 명령어 관리 원칙」, 「계획서 규약」
- `src/verify_lab/CLAUDE.md` — 계층 구조, 「데이터 저장 규칙」, 「계층 간 계약」
- `scripts/CLAUDE.md` — CLI 계층 책임
- `.claude/rules/docs.md` — 문서의 두 종류, **「아카이브 폴더를 만들지 않는다」**, 용어 대응표
- `.claude/rules/strategy.md` — 매매 규칙 계층의 예외 규정
- `.claude/rules/session-bootstrap.md` §6 — **산출물 git 동기화와 인용 규율**
- `tests/CLAUDE.md` — 테스트 규칙

## 4) 완료 조건(Definition of Done)

- [x] 매매법 slug 가 **코드·산출물 폴더·문서에서 하나**로 맞는다
- [x] 매매 계층에 **매매법 사이를 건너는 import 가 없다** — 공유 로직은 `trade_fill.py`·`periods.py` 가
      소유하고 매매법마다 **`<slug>_runner.py` 하나**만 둔다
- [x] 폴더 이름을 만드는 상수가 **CLI 가 아니라 패키지**에 있다 (`kosdaq_month_end_trading` 하드코딩 제거)
- [x] 새 산출물이 **`storage/results/{검증, 매매, 실측}/<시각>_<slug>/`** 에 생긴다
- [x] **`result_citations.py` 가 새 경로를 인식**하고, 양방향 판정(`missing_citations`·`unreferenced_dirs`)이 그대로 동작한다
- [x] `docs/spec/`·`docs/research/`·`docs/strategy/` 의 파일명이 **매매법당 같은 한글 이름**을 쓴다
- [x] 문서 본문의 매매법 호칭이 통일됐다
- [x] `docs/INDEX.md` 가 갱신되고 `tests/test_index.py` 가 통과한다
- [x] `docs/COMMANDS.md` 의 실행 명령이 새 스크립트 이름으로 갱신됐다
- [x] 회귀/신규 테스트 추가
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트(`docs/COMMANDS.md` / CLAUDE.md / plan 등 — 각각 변경 여부 명시)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 확정 이름표 (이 표가 이 계획서의 핵심 산출물이다)

| 한글 이름 | slug | 측정 패키지 | 매매 모듈 | 지금 이름 |
| --- | --- | --- | --- | --- |
| **역방향** | `reverse` | `studies/reverse/` | `strategy/reverse_*` | `index_extreme` **→ 개명** |
| **옵션 만기일** | `option_expiry` | `studies/option_expiry/` | `strategy/option_expiry_*` | `expiry_*` → 접두사 통일 |
| **월말 진입** | `month_end` | `studies/month_end/` | `strategy/month_end_*` | `kosdaq_month_end_trading` → `kosdaq_` 제거 |
| 원달러 ETF 등가성 | `usdkrw_equivalence` | 있음 | 없음 | 그대로 |
| 레버리지 ETF 괴리 | `leverage_tracking` | 있음 | 없음 | 그대로 |
| 선물 대 레버리지 ETF | `futures_leverage` | 있음 | 없음 | 그대로 |
| 원달러 그리드 | `usdkrw_grid` | **코드 없음** | 없음 | 폴더만 잔존 |

> **`usdkrw_grid` 는 실행 코드가 없다.** `scripts/studies/` 에 스크립트가 없고 패키지도 없다 —
> `연속_등락` 처럼 측정 코드가 제거된 검증이다. 폴더 `20260826_112619_usdkrw_grid` 는
> 살아있는 문서 2개가 인용하므로 **그대로 둔다.**

### 변경 대상 파일(예상)

- `src/verify_lab/studies/index_extreme/` → `studies/reverse/` (5파일)
- `src/verify_lab/strategy/trade_fill.py` — **신설.** `reverse_trading.py` + `expiry_trading.py` 를 합쳐
  체결 판정식 두 방식(익절형·달력형)을 매매법-중립 모듈에 둔다. 두 옛 파일은 없어진다.
  `simulate_expiry_trade` → **`simulate_scheduled_trade`** (월말도 부르므로 이름에 만기일을 두지 않는다)
- `src/verify_lab/strategy/periods.py` — **신설.** `expiry_runner.py` 의 `period_rows`·`_period_row` 를 옮긴다
- `src/verify_lab/strategy/runner.py` → `reverse_runner.py`
- `src/verify_lab/strategy/expiry_runner.py` → `option_expiry_runner.py`
- `src/verify_lab/strategy/month_end_runner.py` — import 를 공유 계층으로 돌린다 (**체결부 분리는 없다**)
- `src/verify_lab/strategy/constants.py` — `STRATEGY_NAME`·`EXPIRY_STRATEGY_NAME` 제거.
  slug 는 `studies/<slug>/constants.py` 가 매매법당 하나만 갖는다
- `src/verify_lab/studies/*/constants.py` 6개 — `STUDY_NAME` → **`TRACK_NAME`**.
  같은 상수가 검증과 매매 양쪽 폴더 이름을 만들게 되므로 `STUDY_` 가 사실과 어긋난다
- `src/verify_lab/common_constants.py` — 계층 폴더 이름 상수 3개 신설 (`report` 와 `utils` 양쪽이 쓴다)
- `src/verify_lab/report/writer.py` — `create_run_directory(track, *, layer)`
- `src/verify_lab/utils/result_citations.py` — **탐색 깊이 확장 + 이름→경로 대응 제공**
- `scripts/maintenance/clean_results.py` — 이름이 아니라 경로로 다룬다
- `scripts/data/check_pykrx_etf.py`·`check_pykrx_splice.py` — 복제한 폴더 생성을 `create_run_directory` 로
- `scripts/studies/run_*.py` 6개 → `run_<slug>_study.py`, `scripts/strategy/run_*.py` 3개 → `run_<slug>_trading.py`
- `tests/` — 리네임 대상 테스트 9파일과 `test_result_citations.py`·`test_report_writer.py`·`test_layer_contracts.py`·`test_index.py`
- `docs/spec/` 7파일, `docs/research/` 1파일, `docs/strategy/` 1파일 — 파일명과 본문
- `docs/INDEX.md` — 전면 개정
- `docs/COMMANDS.md`: **변경 있음** — 스크립트 이름이 바뀐다

### 데이터/결과 영향

- **기존 산출물의 수치는 바뀌지 않는다.** 재실행하지 않는다
- **새 산출물은 새 경로에 생긴다.** 기존 22개는 `storage/results/` 바로 아래에 남는다 —
  **두 구조가 공존하며, 그것이 의도다**
- `result_citations.py` 는 **두 자리를 모두** 훑어야 한다 (루트 직하 + 세 하위 폴더)

## 6) 단계별 계획(Phases)

### Phase 0 — 계약을 테스트로 먼저 고정(레드)

**작업 내용**:

- [x] `create_run_directory(track, *, layer)` 의 새 계약을 테스트로 고정 — **계층 폴더를 함수가 만든다.**
      스크립트는 slug 와 계층만 넘긴다. **접미사는 붙이지 않는다** (결정 3 으로 불필요해졌다)
- [x] 허용되지 않는 계층 이름을 주면 `ValueError` 임을 고정 — 조용히 새 폴더를 파면 산출물이 흩어진다
- [x] `result_citations` 가 **루트 직하와 세 하위 폴더를 모두** 훑는지 고정
- [x] `result_citations` 가 **이름 → 경로 대응**을 내는지 고정 (정리 도구가 쓴다).
      같은 이름이 두 계층에 있으면 `RuntimeError`
- [x] **기존 29개 폴더가 여전히 인용으로 잡히는지** 회귀 테스트로 고정 — 옛 자리를 놓치면
      품질 검증이 근거물을 「없다」고 보고한다 (초안의 「22개」는 작업 A 이전 수치다)
- [x] `tests/test_layer_contracts.py` 에 **매매 계층 구성 계약**을 넣는다 —
      **매매법 모듈(`*_runner.py`)끼리 서로 import 하지 않는다.** 공유 로직은 `trade_fill.py`·`periods.py` 가 소유한다

---

### Phase 1 — 이름 상수의 소유자를 정리한다(그린 유지)

**작업 내용**:

- [x] `scripts/strategy/run_month_end_trading.py:45` 의 하드코딩을 걷어낸다.
      **옮길 곳은 `strategy/constants.py` 가 아니라 `studies/month_end/constants.py` 다** —
      slug 를 매매법당 하나로 두려면 측정과 매매가 같은 정의를 봐야 한다
- [x] `studies/*/constants.py` 의 `STUDY_NAME` → `TRACK_NAME` (6곳).
      `strategy/constants.py` 의 `STRATEGY_NAME`·`EXPIRY_STRATEGY_NAME` 은 **제거**한다
- [x] `common_constants.py` 에 계층 폴더 이름 셋을 둔다 — `report`(생성)와 `utils`(탐색) 양쪽이 쓰므로
      상수 관리 3계층 규칙에 따라 공통으로 간다. **`utils` 가 `report` 를 import 하면 의존 방향이 뒤집힌다**
- [x] `create_run_directory(track, *, layer)` 로 시그니처를 넓히고 계층 폴더를 함수가 만들게 한다

**Validation**:

- [x] Phase 0 테스트가 그린

---

### Phase 2 — 패키지·모듈·스크립트 개명(그린 유지)

**작업 내용**:

- [x] `studies/index_extreme/` → `studies/reverse/`
- [x] **공유 로직을 매매법-중립 모듈로 뽑는다** (2026-09-11 확정, 안 C)
  - [x] `strategy/trade_fill.py` ← `reverse_trading.py` + `expiry_trading.py`.
        `simulate_expiry_trade` → `simulate_scheduled_trade`
  - [x] `strategy/periods.py` ← `expiry_runner.py` 의 `period_rows`·`_period_row`
- [x] `strategy/runner.py` → `reverse_runner.py`, `expiry_runner.py` → `option_expiry_runner.py`
- [x] `month_end_runner.py` 의 import 를 공유 계층으로 돌린다 — **체결부를 분리하지 않는다.**
      월말에는 고유 체결 로직이 없고, 복제하면 판정식 단일화(절대 원칙 5)가 깨진다
- [x] 스크립트를 `run_<slug>_study.py` / `run_<slug>_trading.py` 로 바꾼다 (**안 B**)
- [x] import 경로와 테스트 파일명을 함께 고친다 (9파일)

---

### Phase 3 — 산출물 경로를 셋으로 나눈다(그린 유지)

**작업 내용**:

- [x] `storage/results/{검증, 매매, 실측}/` 아래에 `<시각>_<slug>/` 가 생기게 한다
- [x] `result_citations.py` 의 **탐색 깊이**를 넓히고 이름→경로 대응을 낸다 (정규식은 그대로 둔다).
      **기존 29개(루트 직하)도 계속 인용으로 잡혀야 한다**
- [x] `scripts/maintenance/clean_results.py` 를 경로 기준으로 고친다 —
      용량 측정·추적 판정·삭제 셋 다 이름만으로는 새 구조에서 어긋난다
- [x] `check_pykrx_etf.py`·`check_pykrx_splice.py` 의 복제된 폴더 생성을 `create_run_directory` 로 돌린다
- [x] `.claude/skills/clean-results/SKILL.md` 가 새 구조를 가리키는지 확인하고 필요하면 고친다
- [x] `docs/INDEX.md` §5 「데이터와 산출물」 표와 `src/verify_lab/CLAUDE.md` 「데이터 저장 규칙」을 고친다

---

### Phase 4 — 문서 파일명과 내부 명칭(그린 유지)

**작업 내용**:

- [x] 아래 표대로 문서를 개명한다

**`docs/spec/` 에는 `_설계` 를 붙인다** (2026-09-11 확정). 붙이지 않으면 `docs/spec/역방향.md` 와
`docs/research/역방향.md` 처럼 **폴더만 다르고 이름이 같은 파일이 6쌍** 생기는데, 그것은 결정 6 이
스크립트 안 A 를 기각한 이유(`⌘P` 에서는 폴더가 안 보인다)와 같은 문제다. 개명 건수는 초안 표와
같은 9개이고 달라지는 것은 충돌 6쌍 → 0쌍이다.

| slug | `docs/spec/` | `docs/research/` | `docs/strategy/` |
| --- | --- | --- | --- |
| `reverse` | `역방향_설계.md` ← `index_extreme_events.md` | `역방향.md` ← `지수_극단_이벤트.md` | `역방향_매매_규칙.md` 그대로 |
| `option_expiry` | `옵션_만기일_설계.md` ← `option_expiry.md` | `옵션_만기일.md` 그대로 | `옵션_만기일_매매_규칙.md` 그대로 |
| `month_end` | `월말_진입_설계.md` ← `month_end.md` | `월말_진입.md` 그대로 | `월말_진입_매매_규칙.md` ← `코스닥_월말_매매_규칙.md` |
| `leverage_tracking` | `레버리지_ETF_괴리_설계.md` ← `leverage_tracking.md` | 그대로 | — |
| `futures_leverage` | `선물_대_레버리지_ETF_설계.md` ← `futures_leverage.md` | 그대로 | — |
| `usdkrw_grid` | `원달러_그리드_설계.md` ← `usdkrw_grid.md`<br>`원달러_그리드_사양서.md` ← `usdkrw_grid_rules.md` | `달러_조달_방식.md` 그대로 | `원달러_그리드.md` 그대로 |
| `usdkrw_equivalence` | (없음) | `원달러_ETF_등가성.md` 그대로 | — |

> **딸려오는 비용**: `docs/spec/` 이 한글 이름이 되면서 코드 주석 16곳·문서 22곳의 참조를 고쳐야
> 하고, **VSCode 에서 그 마크다운 링크는 클릭해도 열리지 않는다**(확장이 한글 경로를 퍼센트
> 인코딩만 하고 디코딩하지 않는다). `docs/research/`·`docs/strategy/` 는 이미 한글이라 같은 상태다.

- [x] **본문의 매매법 호칭을 「역방향」으로 통일**한다. **다만 「역대급 등락」은 «신호의 정의»를
      가리킬 때 남긴다** — 그 자리에서는 정확한 말이다. 「지수 극단」·「극단 이벤트」 26회는 교체한다
- [x] 문서끼리의 상호 링크를 전부 고친다
- [x] `docs/INDEX.md` 를 전면 개정하고 **한글 이름 ↔ slug ↔ 계층 대응표**를 한 줄씩 둔다

> **코드 slug 는 영문(`reverse`), 문서는 한글(`역방향`)로 갈린다.** `docs/` 는 사람이 읽는
> 문서라 한글이 맞고 코드에 한글 식별자를 넣을 수는 없다. **대응표가 그 다리다.**

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [x] `docs/COMMANDS.md` 의 실행 명령을 새 스크립트 이름으로 고친다 (**변경 있음**)
- [x] 근거 승격 — 아래 표대로 옮겼다. **이 계획서를 지금 지워도 잃는 것이 없다**

| 옮긴 것 | 목적지 |
| --- | --- |
| 확정 이름표(한글 ↔ slug ↔ 계층), `_설계` 접미사의 이유, 「폴더 이름이 범위를 말하지 않는다」 | `docs/INDEX.md` §3 「매매법 이름표」 |
| 산출물 두 자리 공존과 그 이유 | `docs/INDEX.md` §5 · `utils/result_citations.py` 머리말 |
| slug 소유자·모양·메타키·스크립트 규약 | `src/verify_lab/CLAUDE.md` 「매매법 이름 계약」 |
| 매매 계층 구성(공유 모듈 둘 + runner 하나)과 **기각한 안 셋** | `src/verify_lab/CLAUDE.md` 「매매 계층 구성 계약」 |
| `git ls-files` 가 한글 경로를 escape 하는 함정 | `clean_results.py` 의 `_tracked_dirs` docstring |
| 월말의 두 계층 대상 범위 차이와 **미결 항목** | `docs/spec/월말_진입_설계.md` 결정 ⑫ |
| 새 스크립트 이름과 산출물 경로 | `docs/COMMANDS.md` |
- [x] 자동 포맷 적용: `poetry run black .`
- [x] 변경 기능 및 전체 플로우 최종 검증 — **스크립트 9개를 전부 한 번씩 실행해 새 경로에 생기는지 본다**
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [x] `/code-review xhigh` (발견 **13건** · 조치: **12건 수정 · 1건 사용자 판단 대기**)
- [x] `poetry run python validate_project.py` (passed=1123, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 하네스 / 매매법 이름을 slug 하나로 통일하고 산출물을 계층별 폴더로 나눈다
2. 하네스 / 검증·매매·실측 산출물 경로 분리와 스크립트 이름 규약 통일
3. 하네스 / index_extreme 을 reverse 로 개명하고 매매 모듈 구성을 두 벌로 고정
4. 문서 / 매매법 문서명과 본문 호칭을 매매법당 하나로 맞춘다
5. 하네스 / 이름 상수의 소유자를 패키지로 모으고 인용 판정기를 새 경로에 맞춘다

## 7) 리스크(Risks)

| 리스크 | 완화 |
| --- | --- |
| 🔴 **`result_citations.py` 를 안 고치면 `/clean-results` 가 근거물을 삭제 후보로 내놓는다.** 정규식이 소문자 ASCII 를 요구한다 | Phase 0 에서 **기존 22개가 계속 잡히는지**를 회귀 테스트로 먼저 건다 |
| **문서를 개명하면 그 문서를 인용한 다른 문서가 깨진다** | `tests/test_index.py` 가 링크 해석을 검사한다. Phase 4 안에서 상호 링크를 함께 고친다 |
| **`index_extreme` 27파일 리네임 중 일부를 놓친다** | 품질 검증(PyRight)이 import 오류를 잡는다. 주석 언급은 `grep` 으로 전수 확인 |
| **개명한 문서가 「측정 대상」과 어긋난다** — 검증 #1 은 「지수 극단 이벤트」를 재는 것이지 「역방향」이 아니다 | 사용자가 통일을 택했다(결정 7). **본문에서 「역대급 등락」은 신호 정의를 가리킬 때 남긴다** |
| **작업 C 와 같은 파일을 건드린다** | B 는 「이름과 자리」, C 는 「파일명과 컬럼」으로 갈랐다. **B 를 끝낸 뒤 C 를 시작한다** |

## 8) 메모(Notes)

### 실측으로 무너진 전제 (2026-09-11, 사용자 승인 후 계획서 개정)

**착수 전 전수 확인에서 초안의 사실 넷이 틀렸다.** 무엇이 왜 달라졌는지 남긴다.

| 초안 | 실측 | 무엇이 바뀌었나 |
| --- | --- | --- |
| 월말은 체결 모듈이 없고 체결이 `_trade_row` 안에 있다 | **월말은 체결을 100% 빌려 쓴다.** `_trade_row` 는 포매터다. 고유 체결 로직이 없다 | 목표 2 를 「매매법당 두 벌」에서 **「공유 계층 2벌 + 매매법당 runner 1벌」**(안 C)로 개정 |
| `result_citations.py` 의 **정규식**을 고쳐야 한다 | 정규식은 그대로 된다 — 한글은 상위 폴더에만 들어간다. 고칠 곳은 **탐색 깊이** | Phase 0·3 의 지시를 탐색 깊이로 바꿨다 |
| 기존 산출물 폴더 22개 | **29개** (작업 A 가 7개를 더했다) | 회귀 테스트의 기준 수 |
| 정리 도구는 SKILL.md 만 보면 된다 | `clean_results.py` 가 폴더를 **이름으로만** 들고 다녀 용량·추적 판정·삭제가 어긋난다. 실측 스크립트 둘은 폴더 생성을 **복제**하고 있다 | Phase 3 에 세 파일을 추가 |

**왜 안 C 인가** (사용자 결정, 2026-09-11). 월말에 체결 파일을 만드는 두 길이 모두 나빴다 —
계산을 복사하면 같은 판정식이 두 벌이 되어 **두 매매법의 성적이 조용히 갈라지고**(절대 원칙 5 가
금지), 빈 껍데기를 만들면 내용 없는 간접층이 하나 는다. 대신 공유분을 밖으로 빼면 **매매법 사이를
건너는 import 가 전부 사라진다** — 지금은 월말이 옵션 만기일을 거쳐 역방향을 부르는 사슬이다.
사용자는 「공수가 들더라도 하나로 통일」을 택했다.

**기각한 두 안**: ① 얇은 래퍼(`month_end_trading.py` 가 남의 함수를 한 줄로 넘긴다) — 겉모습만 맞고
사슬이 그대로다. ② 체결식만 뽑고 `period_rows` 는 남긴다 — 월말이 옵션 만기일을 import 하는 것이
한 건 남는다.

### 다른 세션이 알아야 할 것

- **작업 A 는 끝났다** (`PLAN_payoff_ratio_grade.md`, Done). 손익비가 **등급**으로 들어갔고
  성적표에 `손익비` · `손익분기 승률(%)` · `질 때 표본` 3열이 실린다. **작업 C 의 공통 컬럼에 포함된다**
- **A 에서 드러난 별건**: `docs/strategy/투자금_결정.md` §1.2 가 「이길 때 · 질 때」를 성적표 입력으로
  적어 두었으나 **실제 성적표에 그 두 열이 없다.** 사용자에게 보고했고 아직 결정 전이다
- **A 에서 남긴 코드 리뷰 지적 셋**(손익비 최소 표본 가드 · `to_display_columns` 인자 셋 ·
  `int()` NaN 방어)은 사용자 판단 대기다. **B·C 에서 임의로 고치지 않는다**

### 논의 경과 — 무엇이 뒤집혔나

**다른 세션이 「추천안」으로 되돌리지 않도록 남긴다.** 아래는 전부 사용자가 최종 결정한 것이다.

| 라운드 | 논점 | 내가 추천한 것 | **사용자 결정** |
| --- | --- | --- | --- |
| 1 | 매매법 이름을 하나로 묶을 것인가 | **②** 측정은 사건명(`index_extreme`), 매매는 규칙명(`reverse_trading`)을 유지하고 **대응표만** 둔다 — 「역대급 등락을 재는 것」과 「역방향으로 거는 것」은 실제로 다른 것이라 억지로 묶으면 측정 쪽이 부정확해진다 | **①** slug 하나로 통일하고 계층은 폴더가 말한다 |
| 1 | 폴더에 계층을 어떻게 드러낼까 | **②** `_study`/`_strategy` 접미사 | (2라운드에서 **상위 폴더 분리**로 대체됨) |
| 1 | 문서 파일명까지 개명할 것인가 | **①** 문서명 유지 — 측정 문서가 「역방향」이 되면 부정확해진다 | **②** 문서 파일명과 본문 호칭까지 통일 |
| 3 | 스크립트 이름 | 처음엔 **안 A**(양쪽 다 접미사 없음)를 추천했다가, 상위 폴더 분리가 확정되면서 **안 B** 로 바꿨다 — `⌘P` 로 파일을 열 때는 폴더가 안 보인다 | **안 B** |

**두 번 뒤집힌 지점이 있다**(스크립트 이름). 첫 추천의 논리는 「폴더가 계층을 말하니 파일명은
생략해도 된다」였고, **파일명이 단독 식별자가 되는 워크플로**를 놓친 것이 이유였다.

### 작업 A 에서 배운 함정 (B 에서도 밟는다)

**작업 A(`PLAN_payoff_ratio_grade.md`)를 실제로 구현하며 겪은 것이다.**

| 함정 | 무엇이 일어났나 |
| --- | --- |
| **테스트가 통과하는데 산출물이 깨진다** | 검증 #7 을 실제로 돌려서야 라벨 누락이 드러났다. **스크립트를 한 번씩 돌려보지 않으면 모른다** |
| **저장소가 한글 헤더를 기계로 강제한다** | `report/tables.py` 의 `to_display_columns` 가 사전에 없는 컬럼을 만나면 예외를 던진다. 컬럼을 늘리면 **`DISPLAY_*` 정의와 `rename` 연결을 둘 다** 해야 한다 |
| **초안의 사실이 틀릴 수 있다** | 계획서를 쓴 뒤 호출처를 전수 확인했더니 **2건이 틀렸다**(「검증 #1 이 `screen_candidates` 를 쓴다」·「`strategy` 3종을 각각 고쳐야 한다」). **착수 전에 `grep` 으로 숫자를 확인한다** |
| **숫자를 눈으로 옮기면 틀린다** | 코드 리뷰가 문서 수치 9개의 불일치를 잡았다. 반올림된 표시값으로 재계산한 것이었다. **도구 출력을 그대로 붙여넣는다** |

### 코드 리뷰가 잡은 것 (2026-09-11, `/code-review xhigh` 13건)

**12건을 고쳤고 1건이 사용자 판단 대기다.** 고친 것 중 셋은 **조용히 틀리는** 종류였다.

| # | 무엇 | 조치 |
| --- | --- | --- |
| 1 | `git ls-files` 가 **한글 경로를 escape 해서** 내보낸다(`core.quotepath` 기본값 참). 계층 폴더가 한글이라 **그 아래 모든 폴더가 미추적으로 잡히고** 「되돌릴 수 없음」 경고가 거짓이 된다 | `-z` 추가 (NUL 구분 + 인용 해제). 설정에 기대지 않는다 |
| 2 | `result_dir_paths` 가 같은 이름이 두 계층에 있으면 `RuntimeError` 를 던졌다. 그런데 **같은 slug 를 두 계층이 쓰는 것이 이 계획서의 규약**이고 `test_report_writer` 가 그것을 정상으로 고정한다 — 같은 초에 두 계층을 돌리면 인용 판정 전체가 멈춰 **품질 검증과 정리 도구가 동시에 죽는다** | 반환형을 `dict[str, list[Path]]` 로 바꿔 둘 다 돌려준다. 정리 도구는 한 이름의 경로를 **전부** 지운다 |
| 3 | `create_run_directory` 가 계층은 검사하는데 **slug 모양은 검사하지 않았다.** 대문자·숫자가 섞인 slug 면 폴더는 생기는데 인용 스캐너가 영원히 못 찾아, 문서가 인용한 근거물이 삭제 후보로 올라간다 | 스캐너의 패턴(`TRACK_NAME_PATTERN`)을 **한 곳에서 공유**해 입력을 거른다 |
| 4 | PyRight 실패 1건 — `node.module` 이 `str \| None` 인데 첨자 접근 | 네 가지 import 형태를 모두 보게 다시 쓰면서 해소. **`import X`·`from pkg import mod`·상대 import 를 놓치고 있었다** — 그 형태로 쓰면 계약이 초록인데 사슬이 되살아난다 |
| 5 | `option_expiry_runner.__all__` 이 옮겨간 `period_rows` 를 계속 재노출 | 제거. 공유 로직을 매매법 이름이 붙은 경로로 가져올 길을 남기면 안 된다 |
| 6 | 공유 모듈의 테스트(`test_strategy_periods.py`)가 **매매법 모듈을 거쳐** `period_rows` 를 가져왔다 — 그러면 소유자가 바뀌어도 테스트가 통과한다 | `strategy.periods` 에서 직접 가져오게 고쳤다 |
| 7 | `docs/spec/원달러_그리드_사양서.md` 의 링크가 **개명된 `usdkrw_grid.md` 를 가리켜 죽어 있었다** — 자기를 이기는 문서를 가리키는 링크였다 | 새 이름으로 고쳤다 |
| 8 | 실측 스크립트 둘의 `_make_output_dir()` 가 **한 줄 래퍼**로 남았고 `check_ecos.py` 는 인라인 호출이라 관용이 둘이 됐다 | 래퍼 제거, 인라인 호출로 통일 |
| 9 | 개명한 모듈의 docstring 이 옛 호칭을 그대로 들고 있었다 (`지수 극단 이벤트`·`코스닥 월 하순`) | 고쳤다. **검증 계층의 「코스닥」은 사실과도 어긋났다** — 그쪽은 코스피까지 8대상이다 |
| 10 | `clean-results` 스킬 문서에 끼워 넣은 문단이 뒤 문장을 끊고 선행 공백을 남겼다 | 문단을 다시 배치했다 |

**사용자 판단 대기 (1건)** — 아래 「월말 매매의 범위와 문서명」 절.

### 월말 매매의 범위와 문서명 — 사용자 판단이 필요하다

**실측**: 검증 계층은 `DATASETS` **8대상**(코스피 4 + 코스닥 4)이지만 **매매 계층은
`DATASETS_KOSDAQ` 4대상뿐이다.** `--ticker 069500` 은 「알 수 없는 대상」으로 거부된다.

그런데 이 계획서가 `docs/strategy/코스닥_월말_매매_규칙.md` 를 **`월말_진입_매매_규칙.md` 로
개명**했다(Phase 4 표, 사용자 승인). 그래서 **파일명은 시장을 안 가리는데 내용은 코스닥 전용**이다.
`PLAN_month_end_kospi.md:54` 에는 「`코스닥_월말_매매_규칙.md` 를 개명하지 않는다 — 코스닥 손절
격자만 담은 문서」라는 반대 방향 결정이 남아 있다.

**지금 상태**: 문서 제목은 「코스닥 월말 매매 규칙」을 그대로 뒀고, 매매 계층 코드의 「코스닥」
표현도 유지했다(사실이므로). `run_month_end_trading.py` 에는 **폴더 이름으로 범위를 추측하지
말라**는 주의와 범위의 SoT(`summary.json` 의 `datasets`)를 적었다.

**남은 선택지** — 어느 쪽도 코드 변경 없이 문서만 움직인다.

| 안 | 내용 |
| --- | --- |
| ① 현 상태 유지 | 파일명은 `월말_진입_매매_규칙.md`, 제목과 본문이 코스닥 전용임을 밝힌다. 매매가 코스피로 넓어질 때 이름을 안 고쳐도 된다 |
| ② 개명을 되돌린다 | `코스닥_월말_매매_규칙.md` 로 되돌려 파일명이 범위를 말하게 한다. Phase 4 표와 어긋나고, 나중에 코스피를 넣으면 다시 개명해야 한다 |
| ③ 매매 계층을 8대상으로 넓힌다 | 이름이 사실과 맞게 된다. **다만 이것은 새 측정이라 이 계획서의 비목표(재실행 금지)에 걸리고 별도 계획서가 필요하다** |

### 진행 로그 (KST)

- 2026-09-10 18:05: 계획서 작성. 작업 A 완료 후 사용자 요청으로 B·C 를 분리해 작성
- 2026-09-11 11:52: Phase 0~4 와 마지막 Phase 완료. 스크립트 9개를 전부 돌려 새 경로 확인,
  `/code-review xhigh` 13건 중 12건 수정(PyRight 1건·한글 경로 escape·인용 판정 모순 포함),
  품질 검증 passed=1123 failed=0 skipped=0. 확인용 산출물 9폴더는 삭제했다(재실행은 작업 C 에서)
- 2026-09-11 11:15: 착수 전 전수 확인에서 전제 넷이 무너짐. 사용자 승인 후 목표 2(안 C)·
  Phase 0~4·변경 대상 파일·문서 개명표(`_설계` 접미사)를 개정. 상세는 8절 「실측으로 무너진 전제」

---
