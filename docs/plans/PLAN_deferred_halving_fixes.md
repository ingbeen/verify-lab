# Implementation Plan: 미룬 지적 처리 — 반감기_사이클 몫 (공유 시세 검증기 · 후보 칸 수 화면 · 미래 참조 감시 가드 · 경고 · docstring)

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

**작성일**: 2026-09-30 15:26
**마지막 업데이트**: 2026-09-30 16:08
**관련 범위**: data(공유 시세 검증기), studies(반감기_사이클 docstring), scripts(반감기_사이클 화면), tests(로더 · 반감기 달력 · 반감기 러너), docs(미룬 지적)
**관련 문서**: `src/verify_lab/CLAUDE.md`, `scripts/CLAUDE.md`, `tests/CLAUDE.md`, `docs/DEFERRED_FINDINGS.md`, `docs/MEMORY.md`

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

- [x] 목표 1: 공유 시세 검증기 `data/loader.validate_market_data` 가 **가격(시가 · 고가 · 저가 · 종가)의 무한대**와 **거래량의 결측 · 무한대 · 음수**를 예외로 막는다. **거래량 0 은 계속 통과한다** — 거래가 없던 날이 실제 시세 파일에 있다
- [x] 목표 2: 목표 1 뒤에도 **저장된 시세 파일이 전부 그대로 읽히고, 실행 스크립트 여섯의 산출물이 바이트 단위로 같다**
- [x] 목표 3: 반감기_사이클 CLI 의 「후보 칸 수」 화면을 **종목 × 손절선**으로 묶는다 — 대상이 둘이 되면(라이트코인 교차 재현) 두 대상을 합쳐 세지 않는다
- [x] 목표 4: 반감기 기준선의 미래 참조 감시 테스트에 **「잰 칸이 없으면 실패」 가드**를 넣는다 — 옆 테스트 셋과 같게
- [x] 목표 5: 품질 검증의 경고 1건(`pd.Timedelta(days=1)` 의 NumPy DeprecationWarning)을 없앤다
- [x] 목표 6: 사실과 다른 docstring 세 곳을 바로잡는다 — 진입일 정의를 한 함수가 소유한다고 적었지만 1단계(`halving_entries`)와 3단계(`position_schedule`)가 같은 달력 규칙을 따로 구현한다

## 2) 비목표(Non-Goals)

- **버리기로 한 미룬 지적 54건을 고치지 않는다** — 사용자 지시(2026-09-30 「추천대로 하되 "고친다"에서도 불필요하다고 판단되거나 너무 작은 영향도는 그냥 버린다」)로 `docs/DEFERRED_FINDINGS.md` 에서 이미 지웠다. 항목과 이유는 아래 Context 표
- **1단계 · 3단계 진입일 함수를 하나로 합치지 않는다** — 두 함수 모두 반감기 목록을 인자로 받아 라이트코인도 진입 규칙을 건드리지 않고 자기 반감기를 넘기면 되고, 지금 실제 진입일이 57 / 57 같다. docstring 만 사실대로 고친다
- `결과.md` §16.1 의 같은 사이클 칸 기준선과 §16.2 의 평균 · 합산(미룬 지적 두 건)은 **다음 계획서**가 한다 — 새 값을 내는 변경이라 이 계획의 「산출물 바이트 불변」과 커밋을 가른다(`docs/MEMORY.md` 「이름만 바꾸는 변경과 값을 바꾸는 변경을 한 커밋에 섞지 않는다」)
- 반감기와 무관한 미룬 지적 10건(중간선거 등)은 다루지 않는다
- 시세를 다시 받지 않는다. 급등락 임계값 · 계열(`validate_series_data`) · 선물(`load_futures_csv`) 검증기를 바꾸지 않는다
- 라이트코인 교차 재현은 별도 계획서다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

사용자가 미룬 지적 처리를 지시했다(2026-09-30). 반감기_사이클 61건을 서브에이전트 넷이 **저장소 사본에서** 재현했고(원본 무변경 — `git status` 빈 출력), 결론을 좌우하는 셋은 원본 코드로 다시 확인했다. 사용자가 추천을 받아들이면서 「고친다」 중에서도 불필요하거나 영향이 작은 것은 버리라고 했다. 그 결과 **7건이 남았다** — 이 계획서가 5건, 다음 계획서가 2건.

**이 계획서가 고치는 것**

| 미룬 지적 | 무엇 | 재현 | 남긴 이유 |
| --- | --- | --- | --- |
| `data/loader.py` `validate_market_data` | 가격의 무한대(종가 밖)와 거래량의 결측 · 무한대 · 음수를 통과시킨다 | **원본에서 직접 재현** — 3행 합성 표에 `High[1]=inf` · `Volume[1]=nan` · `Volume[1]=-5` 가 모두 통과, 대조군 `Close[1]=inf` 만 급등락으로 걸림(`+inf%`). 서브에이전트는 `Open` · `Low` 의 무한대, 한 행짜리 종가 무한대, 거래량 무한대도 통과함을 확인 | **유일한 무거운 버그**(검사를 비켜 간다). 모든 시세 로딩과 수집기 넷이 지나는 자리이고, 라이트코인 시세를 새로 받을 때도 이 검사를 지난다 |
| `scripts/run_halving_cycle.py` `_print_candidate_counts` | 손절선으로만 묶어 대상이 둘이면 손절선마다 「전체 칸」이 512 가 되고 판정 안 함 대상의 행까지 섞인다 | 사본 재현 — 성적표 두 벌: `무손절 512 227`(둘째가 판정 안 함) · `무손절 512 454`(둘 다 판정) | 라이트코인을 두 번째 대상으로 넣으면 **바로 발동**한다 |
| `tests/test_studies_halving_cycle_calendar.py` `TestLookAhead.test_기준선_수익률이_뒤_데이터에_기대지_않는다` | 옆 셋과 달리 `assert not measured.empty` 가 없다 | 사본 재현 — 미래 참조 변형 + 테스트 보유 `(48,)` 에서 이 테스트는 통과, 가드를 넣으면 실패 | 필수 미래 참조 감시(`tests/CLAUDE.md`)가 빈 배열끼리 비교하며 초록이 될 수 있다 |
| 품질 검증 경고 1건 | `tests/test_studies_halving_cycle_runner.py:600` 의 `pd.Timedelta(days=1)` 이 NumPy 2.5.2 · pandas 2.3.3 에서 DeprecationWarning | 원본에서 `-W error::DeprecationWarning` 으로 재현. `pd.Timedelta("1D")` 도 경고, `pd.Timedelta(1, unit="D")` · `pd.DateOffset(days=1)` 은 경고 없음. 저장소에서 이 형태는 이 한 줄뿐 | 사용자 지시(2026-09-30 「4번」) |
| `halving_calendar.trading_positions` docstring · 모듈 docstring · `runner.signal_returns` docstring | 「날짜 → 위치 변환은 이것 하나다」(실제로는 `execution/trade_fill.resolve_positions` 도 쓴다) · 「측정과 체결이 이 함수를 함께 쓴다 — 진입일 정의를 두 벌 만들면 …」(체결은 이 함수를 부르지 않는다) | 사실 확인 — `signal_returns` 호출은 `runner.py` 한 곳 | 없는 안전 보증을 적었다. 라이트코인 계획서가 바로 이 코드를 만지므로 「한 곳만 고치면 된다」로 읽히면 안 된다 |

**다음 계획서로 넘기는 것** — `결과.md` §16.1 방향 비율 표의 기준선(결정 ㊵ 개정 — 같은 사이클 120칸), §16.2 의 평균 · 합산 수익률.

**버린 54건** — `docs/DEFERRED_FINDINGS.md` 에서 지웠다(처리 이력은 git). 묶음과 이유:

| 묶음 | 건수 | 버린 이유 |
| --- | --- | --- |
| 데이터 계층 — 부분 저장 · 중복 봉 · 무한 순회 · 오류 문구 둘 · 시각/날짜 비교 · 상수 중복 · 정렬 코드 · 테스트 단언 둘 · docstring 넷 · 계약 표 한 행 | 15 | 실제 발동 0 이고 발동해도 눈에 띄게 멈추거나 문구만 틀린다 · 동작이 같다 · 서술만 낡았다 |
| 1단계 측정 · 체결 — 대체일 종가 범위 · 빈 진입 개월 예외 · 아직 안 온 진입 건수 · 위치 검사 세 벌 · 두 번 읽기 · CLI 판정 필터 · 방향 식 · 요약 두 벌 · 컬럼 자리 · 암묵 연결 · 「세 번째」 문장 둘 · 계약 문서 과거형 · 테스트 픽스처 · 하한(10) | 15 | 실제 0 건이거나 구조상 발동하지 않는다(대체일은 「위」에서 부등식이 깨지지 않는다 · 모든 진입 개월이 비트코인 3 ~ 4건 · 라이트코인 Bitstamp 도 어느 반감기 기준이든 2건 이상) · 비용이 0.1초 대 · 서술만 낡았다. **픽스처 지적의 「갭손절 경로를 안 지난다」는 틀렸다** — 원본으로 다시 세면 합성 체결 중 갭손절 444건 |
| 2단계 — 반올림 표시 · 비거래일 돌파 · 예외 종류(재현 안 됨) · 빈 온체인 문구 · 위치 슬라이스 · 반복 · 키 이름 · `_ratio` 이름 · 검사 겹침 · 요약 키 재정의 · 읽는 순서 · `--repeats` 연결 · 테스트 허용치 · 문서 셋(「신호 열넷」 등 · 결정 ㉚ 주어 · §4.8 단위) | 16 | 실제 0 건 · 지금 일치 · 비용 무시할 만함 · 서술 · 표기 |
| 3단계 — 하드포크 몫 경로 둘 · 개월 중복 · `--help` 「11종」 · 하드포크 계산 위치 · 진입일 대조 테스트 · 경계 테스트 · `scripts/CLAUDE.md` 「두 포크」 | 8 | 실제 0 건(포크일 청산 0 / 8,371 · 방향 상수 「위」 · 상수 중복 0 · 경계 일치 0) · 문구 · 코드 배치 |

### 공유 검증기의 영향도 (착수 전 실측, 2026-09-30)

- **호출처**: `validate_market_data` — 수집기 넷(`etn_collector` · `yfinance_collector` · `bitstamp_collector` · `pykrx_collector`)과 `load_market_csv` 하나. 넷 모두 `REQUIRED_COLUMNS`(거래량 포함)를 갖춘 표를 넘긴다. 계열(`validate_series_data`)과 선물(`load_futures_csv`)은 따로라 영향 밖이다
- **저장된 시세**: `storage/market/` 59개 파일 · 304,476행(OHLCV 57개 + 선물 2개 — 선물은 별도 로더). 가격 무한대 0 · 거래량 결측 0 · 거래량 무한대 0 · 거래량 음수 0 → **새 검사에 막히는 기존 파일 0**
- **거래량 0 인 날**: `BTCUSD_max.csv` 33 · `SQQQ_max.csv` 29 · `SQQQ_adjusted_max.csv` 29 · `SDOW_max.csv` 2 · `SDOW_adjusted_max.csv` 2 (선물 두 파일은 별도 로더) → **0 을 막으면 기존 파일이 읽히지 않는다.** 0 은 정상으로 둔다
- 수집기 테스트 픽스처에 거래량이 결측 · 음수인 곳이 없다(grep)

### 글자 규칙 판정

해당 없음 — 숫자 값의 유한성 · 부호 검사다.

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- `.claude/plan-config.json` — 이 저장소의 검증 명령·자동 포맷·근거 승격 목적지 (**값의 SoT**)
- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절 (값이 아니라 **판단 근거**)
- `src/verify_lab/CLAUDE.md` — 「데이터 검증은 즉시 실패」 · 「원시 시세 저장 규칙」의 「이상치 판정」 행 · 「데이터 저장 규칙」
- `scripts/CLAUDE.md` — CLI 계층 책임
- `tests/CLAUDE.md` — 필수 테스트(미래 참조 감시) · 경계 조건 · 예외 테스트 · 「테스트 보강」의 변형 확인
- `docs/MEMORY.md` — 「변형 확인은 바이트코드를 끄고 돌린다」 · 「이름만 바꾸는 변경과 값을 바꾸는 변경을 한 커밋에 섞지 않는다」
- 전역 `~/.claude/rules/python.md` — 명시적 검증 · 불가능 조건 · 로깅

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 기능 요구사항 충족 — 목표 1 ~ 6
- [x] 회귀/신규 테스트 추가 — 로더의 무한대 · 거래량 테스트, 기준선 감시 가드
- [x] 저장된 시세 전부가 새 검증기로 읽히고, 실행 스크립트 여섯의 산출물이 착수 전 사본과 바이트 단위로 같다
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — `docs/COMMANDS.md` 변경 없음 · CLAUDE.md 변경 없음(검증기의 판정 목록은 `loader.py` docstring 이 소유한다)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다 (거래량 0 을 허용하는 이유는 `loader.py` docstring 에, 버린 54건의 판단은 git 이력과 이 계획서 Context 에만 있어도 된다 — 버린 항목은 판단을 끝낸 것이다)
- [x] 미룬 지적 옮김 — 이 계획서가 고친 5건의 행을 `docs/DEFERRED_FINDINGS.md` 에서 지웠다. 리뷰에서 새로 미룬 지적이 있으면 옮겼다
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/data/loader.py` — `validate_market_data` 에 무한대 · 거래량 검사, 모듈 docstring 표와 함수 docstring
- `tests/test_data_loader.py` — 무한대 가격 · 거래량 결측/무한대/음수 · 거래량 0 통과 · 한 행짜리 종가 무한대
- `scripts/run_halving_cycle.py` — `_print_candidate_counts` 를 종목 × 손절선으로 묶는다(`DISPLAY_TICKER` import)
- `tests/test_studies_halving_cycle_calendar.py` — 기준선 감시 테스트에 가드 한 줄
- `tests/test_studies_halving_cycle_runner.py` — `pd.Timedelta(1, unit="D")`
- `src/verify_lab/studies/halving_cycle/halving_calendar.py` — `trading_positions` docstring · 모듈 docstring
- `src/verify_lab/studies/halving_cycle/runner.py` — `signal_returns` docstring
- `docs/DEFERRED_FINDINGS.md` — 고친 5건의 행 삭제
- `docs/COMMANDS.md`: 변경 없음 — 실행 명령 · CLI 옵션이 그대로다

### 데이터/결과 영향

- **산출물 변화 없음** — 검증기는 막는 조건만 더하고 기존 파일 중 막히는 것이 0 이다. 나머지는 테스트 · docstring · 화면이다. 실행 스크립트 여섯을 인자 없이 다시 돌려 `storage/results/` 를 착수 전 사본과 파일마다 대조한다(`meta.json` 제외 — git 제외 파일이고 실행마다 바뀐다)
- 반감기_사이클 CLI 화면의 「후보 칸 수」 표에 `종목` 열이 붙는다(저장 파일 아님)
- 앞으로의 수집이 거래량 결측 · 무한대 · 음수를 만나면 저장하지 않고 멈춘다 — Risks

## 6) 단계별 계획(Phases)

### Phase 0 — 검증기의 새 정책을 테스트로 먼저 고정(레드)

**작업 내용**:

- [x] 착수 전 사본: `storage/results/` 전체를 세션 스크래치에 복사한다(대조 기준)
- [x] 착수 전 로딩 기록: 저장된 OHLCV 57개 파일을 운영 로더로 읽어 **파일마다 통과 여부 · 행 수**를 스크래치에 남긴다 — 비트코인은 `crypto_common.load_crypto_market_csv`, 나머지는 `load_market_csv`(기본 임계값). 원래부터 막히는 파일이 있으면 그것도 기록한다
- [x] `tests/test_data_loader.py` 에 이웃과 같은 모양(`_row` · `_write_csv` · Given-When-Then)으로 추가한다
  - 시가 · 고가 · 저가 중 하나가 `inf` 또는 `-inf` 인 행 → `ValueError`, `match="무한대"`(매개변수화). **문구까지 본다** — `-inf` 는 지금도 「0 이하」로 걸려 예외 종류만 보면 레드가 되지 않는다
  - 한 행짜리 파일의 종가가 `inf` → `ValueError`, `match="무한대"` (지금은 일간 변동이 NaN 이라 통과한다)
  - 거래량 결측 · `inf` · 음수 → `ValueError`(매개변수화), 메시지에 거래량 컬럼 이름
  - 거래량 0 인 행 → 통과(경계 — 거래가 없던 날)
  - 무한대 판정은 `isin([inf, -inf])` 로 한다 — 정수형 거래량에도 그대로 걸린다
- [x] 새 테스트만 돌려 **거래량 0 통과를 뺀 나머지가 실패**하는 것을 본다(실패 수를 진행 로그에)

**Validation**:

- [x] `PYTHONDONTWRITEBYTECODE=1 poetry run pytest tests/test_data_loader.py -q -p no:cacheprovider` — 새 테스트 중 기대한 수만 실패

---

### Phase 1 — 검증기 구현과 기존 시세 · 산출물 대조(그린)

**작업 내용**:

- [x] `validate_market_data`: 결측 검사 대상을 가격 넷 + 거래량으로 넓히고, 같은 대상에 무한대 검사를 더하고(0 이하 검사보다 앞 — `-inf` 를 「0 이하」가 아니라 「무한대」로 알린다), 거래량 음수 검사를 더한다. 가격의 0 이하 검사와 일간 변동 검사는 그대로. 메시지는 기존 형식(`… 발견 - 컬럼: …, 건수: …, 예시 날짜: …`)을 따른다
- [x] 모듈 docstring 의 판정 표 · 함수 docstring 에 무한대 · 거래량을 반영하고, **거래량 0 을 막지 않는 이유**(거래가 없던 날이 실제 시세에 있다 — 비트코인 초기 · 인버스 ETF)를 적는다
- [x] Phase 0 테스트 전부 통과
- [x] 저장된 OHLCV 57개 파일을 같은 방식으로 다시 읽어 Phase 0 의 기록과 **파일마다 통과 여부 · 행 수가 같음**을 본다(결과는 진행 로그)
- [x] 실행 스크립트 여섯(`scripts/run_*.py`)을 인자 없이 돌리고 `storage/results/` 를 착수 전 사본과 `diff -r`(`meta.json` 제외) — 다른 파일 0. 다르면 사본으로 되돌리고 멈춰 보고한다

**Validation**:

- [x] `PYTHONDONTWRITEBYTECODE=1 poetry run pytest tests/test_data_loader.py -q -p no:cacheprovider` 전부 통과
- [x] 시세 57개 로딩 결과가 착수 전과 같음 · 산출물 대조 다른 파일 0

---

### Phase 2 — 화면 · 감시 가드 · 경고 · docstring(그린 유지)

**작업 내용**:

- [x] `_print_candidate_counts` 를 `DISPLAY_TICKER` × `DISPLAY_STOP_LEVEL` 로 묶는다. 스크래치에서 실제 성적표를 두 벌로 만들어 넣어 **종목마다 256칸**이 따로 나오는지 본다(고치기 전 `512`)
- [x] 기준선 감시 테스트에 `assert not measured.empty, "짧은 입력에서 잰 기준선 칸이 없어 계약을 검사하지 못했습니다"` 를 넣는다. **변형 확인**(`PYTHONDONTWRITEBYTECODE=1`): 사본을 뜬 뒤 테스트의 보유를 `(48,)` 로 바꾸면 가드 때문에 실패하고, 되돌린 뒤 사본과 바이트 대조
- [x] `pd.Timedelta(days=1)` → `pd.Timedelta(1, unit="D")`. 그 테스트를 `-W error::DeprecationWarning` 으로 돌려 통과
- [x] docstring 셋: `trading_positions`(1단계 · 2단계 · 3단계 달력 함수가 쓰고, 체결 · 비중첩 계산은 `execution/trade_fill.resolve_positions` 를 쓴다), 모듈 docstring(`진입 × 보유 = 유효 + 제외` 가 1단계의 것임과 3단계 일정의 등식 자리), `signal_returns`(1단계 측정만 쓰고, 3단계 일정은 같은 달력 규칙을 `position_schedule` 이 따로 구현한다 — 규칙을 바꾸면 두 곳을 함께 바꾼다)

**Validation**:

- [x] `PYTHONDONTWRITEBYTECODE=1 poetry run pytest tests/test_studies_halving_cycle_calendar.py tests/test_studies_halving_cycle_runner.py -q -p no:cacheprovider -W error::DeprecationWarning` 통과
- [x] 화면 대조(두 대상 → 종목마다 256칸) 결과를 진행 로그에

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

> 🔴 **`/commit` 이 «맨 마지막»인 것은 의도다.** 그 스킬은 「후보 뒤에는 아무것도 덧붙이지 말 것」으로
> 끝나므로 **호출하는 순간 그 턴이 거기서 닫힌다.** 중간에 두면 뒤에 적힌 항목이 그 벽 너머에 남는다 —
> 실제로 두 번 그렇게 샜다(`[실측] 2026-09-14` 후보를 계획서에 안 옮김 · `2026-09-16` 옮기고 체크박스를 안 닫음).
> **체크박스와 상태를 먼저 확정하고, 커밋 후보를 마지막에 만든다.**

- [x] 필요한 문서 업데이트 — `docs/COMMANDS.md` 변경 없음. `docs/DEFERRED_FINDINGS.md` 에서 고친 5건의 행을 지운다(행이 없어지는 소절은 제목째)
- [x] 자동 포맷 적용 (`poetry run black .`)
- [x] 변경 기능 및 전체 플로우 최종 검증 — 리뷰에서 코드가 바뀌었으면 Phase 1 의 산출물 대조를 다시 한다
- [x] Validation 절에 `/code-review` 와 품질 검증 **실행 결과**를 적는다
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정
- [x] 🔴 **마지막에 `/commit` 을 실행하고 그 후보를 «이 계획서» 의 `#### Commit Messages` 절에 옮긴다** —
      `/commit` 은 계획서를 모르고 「후보 뒤에 아무것도 덧붙이지 말 것」으로 끝나므로,
      **대화에만 내면 그 절이 빈 채로 남는다.** 체크박스 갱신이 diff 에 더 들어가지만
      커밋 메시지의 내용을 바꾸지 않는다. **커밋은 사용자가 한다 — 후보만 낸다**

**Validation**:

> 순서를 지킨다 — 리뷰에서 고치면 코드가 바뀌므로 품질 검증이 마지막 관문이어야 한다.
> **고칠 것이 0 인 회차에서 끝낸다** — 고칠 것은 무거운 버그 전부와, 실제 산출물에 나오는 가벼운 버그다.
> 2회차에도 무거운 버그가 나오면 사용자에게 보고하고 3회차 여부를 묻는다 — 나머지 가벼운 버그와
> 「그 외」는 목록만 남기고 고치지 않는다. 무게의 정의는 `/impl-plan` 의 「코드 리뷰」 절이 SoT 다.
> **뒤에 리뷰 회차가 오지 않는 수정은 고치기 «전»에 바꿀 파일을 스크래치에 복사해 두고, 고친 뒤 수정분 검증을
> 거친다** — 절차는 `/impl-plan` 의 「지적을 고칠 때」다.

- [x] `/code-review xhigh` **1회차** (발견 10건 — 버그 3 [무거움 0 · 가벼움 3] · 그 외 7 · 조치: 그 외 2 수정 — `signal_returns` docstring 의 「1단계 측정만 쓴다」가 사실과 다름(2단계 진입지표 표도 쓴다 — 목표 6 의 대상) · `validate_market_frame` docstring 의 값 검사 나열이 이번 변경으로 낡음. 가벼움 3 은 실제 산출물 0건이라 고치지 않음)
- [x] 수정분 검증 (수정 2건 · 발견 7건 — 무거움 0 · 조치: 고치지 않음 — 가벼움 2 는 서술이 검사를 실제보다 적게 말하는 안전한 쪽, 그 외 5)
- [x] `poetry run python validate_project.py` (passed=1513, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다.**
> 계획서를 쓰는 시점에는 diff 가 없어 여기 적는 것은 전부 추측이고,
> **추측으로 적은 줄은 그대로 나간다.** 형식·문체 규칙은 `/commit` 이 정한다.

1. `수집 / 공유 시세 검증기에 가격 무한대 · 거래량 결측 · 무한대 · 음수 검사 추가`
2. `수집 / 미룬 지적 처리 — 시세 검증기의 무한대 · 거래량 검사, 반감기 후보 칸 수의 종목별 집계, 기준선 미래 참조 감시 가드, Timedelta 경고 제거`
3. `수집 / 거래량 0 은 정상으로 두고 가격 무한대와 거래량 결측 · 무한대 · 음수만 막는 시세 검증 보강`
4. `수집 / 라이트코인 교차 재현 전 정리 — 시세 검증 틈 차단과 반감기 두 대상 화면 · 진입일 docstring 정정`
5. `수집 / 반감기_사이클 미룬 지적 54건 정리와 남긴 5건 처리 — 공유 검증기 무한대 · 거래량 틈 차단`

## 7) 리스크(Risks)

- **앞으로의 수집이 멈출 수 있다** — yfinance · pykrx · ETN · Bitstamp 응답에 거래량 결측 · 음수가 섞이면 이제 저장하지 않고 예외를 낸다. 저장소 규칙(「보간 금지 · 이상은 즉시 실패」 · 「검증을 통과한 데이터만 저장」)과 같은 방향이고 기존 파일에는 0 건이다. 메시지가 날짜와 건수를 알려 원인을 바로 찾게 한다
- **산출물이 바뀌면 멈춘다** — 산출물 대조에서 다른 파일이 하나라도 나오면 원인(검증기인지 · 재실행의 비결정성인지)을 찾기 전에는 진행하지 않고 보고한다
- 실행 스크립트 여섯을 다시 도는 데 시간이 든다(반감기_사이클만 약 50초) — 받아들인다. 공유 계층을 바꾸는 변경의 영향도를 산출물로 확인하는 유일한 방법이다
- 화면 표에 열이 하나 늘어난다 — 저장 파일이 아니라 산출물 계약 밖이다

## 8) 메모(Notes)

- 재현은 `rsync` 로 뜬 저장소 사본에서 `PYTHONPATH=<사본>/src` 로 돌렸다 — 사본의 `src` 가 import 되고 `common_constants.BASE_DIR` 가 사본을 가리킨다(실측). git 명령은 쓰지 않았다
- 버린 54건 중 「틀린 지적」 하나: 체결 픽스처가 갭손절 경로를 지나지 않는다는 서술 — 원본 코드로 픽스처 체결을 다시 세면 `{'기한청산': 5193, '장중손절': 2206, '갭손절': 444}`

### 진행 로그 (KST)

- 2026-09-30 15:26: 계획서 작성. 미룬 지적 파일에서 버린 반감기 항목 54건 삭제 · 남긴 7건 중 5건에 「고치는 중: PLAN_deferred_halving_fixes」 표시(나머지 2건은 다음 계획서)
- 2026-09-30 15:40: Phase 0 — `storage/results/` 사본 88파일(`meta.json` 제외). 착수 전 로딩 기록: OHLCV 57개 파일 전부 통과(막힘 0). 새 테스트 11건 중 **10건 실패 · 1건 통과**(거래량 0) — `+inf` 가격은 예외 없음, `-inf` 가격은 「0 이하」 문구로 걸려 `match="무한대"` 불일치, 한 행짜리 종가 무한대 · 거래량 결측/무한대/음수는 예외 없음
- 2026-09-30 15:43: Phase 1 — 검증기 구현 뒤 `tests/test_data_loader.py` 58 passed. 57개 파일 로딩 기록이 착수 전과 바이트 동일(`cmp`). 실행 스크립트 여섯 인자 없이 재실행(종료코드 전부 0 · futures 14s · halving 49s · leverage 6s · midterm · reverse 25s · usdkrw) → `diff -rq --exclude=meta.json` 다른 파일 0, `git status --porcelain storage/` 빈 출력
- 2026-09-30 15:55: Phase 2 — 후보 칸 수: 실제 성적표에 판정 안 함 둘째 대상을 붙여 넣은 입력에서 고치기 전 손절선마다 `512 · 227`(무손절) → 고친 뒤 `Bitstamp BTC/USD 256 · 227` · `둘째 대상 256 · 0`(스크래치 `candidate_counts.py`). 감시 가드 변형 확인(`PYTHONDONTWRITEBYTECODE=1`, 기준선 보유 `(3,)` → `(48,)`): 가드 전 `1 passed`(빈 배열끼리 비교) · 가드 후 `AssertionError: 짧은 입력에서 잰 기준선 칸이 없어 계약을 검사하지 못했습니다` `1 failed` · 되돌린 뒤 사본과 `cmp` 동일 · `git diff` 는 가드 한 줄 · 달력 테스트 48 passed. `pd.Timedelta(1, unit="D")` 뒤 러너 테스트 `-W error::DeprecationWarning` 37 passed. docstring 셋 — 「두 일정의 진입일 규칙이 같고 구현이 둘」이라는 경고는 달력 모듈 docstring 한 곳에 두고 나머지는 그쪽을 가리킨다(호출처를 늘어놓지 않는다)
- 2026-09-30 16:00: `/code-review xhigh` 1회차 — 발견 10건. 무게와 조치: ① 진입일 구현 두 벌 · ⑥ 같은 지적의 규약 판정 → 사용자가 합치는 리팩터와 약한 대조 테스트를 버렸다(받아들임) · ② 형제 검증기(`validate_series_data` · `validate_futures_data`)도 무한대를 안 본다 → 가벼움, 실제 계열 17개 149,398행 · 선물 2개 56,946행에서 무한대 0 → **미룬 지적으로 옮김** · ③ `signal_returns` docstring 「1단계 측정만 쓴다」 사실 오류 → **수정**(「측정만 쓰고 체결은 부르지 않는다」) · ④ pykrx 수집기가 검증 전에 거래량을 정수로 바꿔 결측이 `IntCastingNaNError` 로 막힌다(진단 문구만 잃음, 저장은 막힘) → 가벼움 · 실제 0 → 버림 · ⑤ 문자열 거래량이 `TypeError` → 가벼움 · 실제 0 · 가격 컬럼도 원래 같은 동작 → 버림 · ⑦ 버린 54건의 근거가 계획서에만 → 절차상 처리 이력은 git 이 말한다 → 버림 · ⑧ 남은 미룬 지적 행이 지운 테스트 행을 가리킴 → 그 행은 Done 에 지운다 → 해당 없음 · ⑨ 모듈 판정 표 「0 이하 값」과 거래량 0 · `validate_market_frame` 나열 → 나열만 **수정**, 표는 바로 아래 거래량 행이 가른다 → 버림 · ⑩ CLI 가 후보 집계를 가짐 → 사용자가 같은 지적(M-C6)을 버렸다 → 버림. 「버림」은 사용자 지시(2026-09-30 「불필요하거나 너무 작은 영향도는 그냥 버린다」)를 새 지적에도 적용한 것이다
- 2026-09-30 16:05: 수정분 검증(서브에이전트, 수정분 diff 와 겨냥한 지적만 전달) — 두 hunk 모두 동작 불변 · 새 문장이 호출처 전수 대조와 맞음 · 위험한 쪽으로 바뀐 것 없음. 발견 7건(가벼움 2: 모듈 판정 표에 가격 무한대 행 없음 · `validate_market_data` Raises 에 빈 표 없음 / 그 외 5: `trading_positions` 의 「예외 종류만 다르다」에 메시지 접두 차이 · 「0 이하 값」 행 · `validate_market_frame` 이 계열에도 쓰임 · 중복 날짜가 오름차순 검사를 지남 · `src/verify_lab/CLAUDE.md` 의 「0값」) — 절차대로 고치지 않고, 전부 서술이라 같은 기준으로 버림
- 2026-09-30 16:08: 미룬 지적 — 이 계획서가 고친 5행을 지우고 ② 한 줄을 「데이터 계층 — 시세 검증기의 형제」 소절로 옮김(17행 → 13행). 고친 CLI 를 인자 없이 한 번 돌림(종료코드 0 · 화면 「종목 · 손절선마다」 11행) → `storage/results/` 가 착수 전 사본과 다른 파일 0. `black` 172 files unchanged. 품질 검증 passed=1513 · failed=0 · skipped=0 · 경고 줄 없음(착수 전 1 warning)

---
