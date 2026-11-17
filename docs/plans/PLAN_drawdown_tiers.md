# Implementation Plan: 하락_단계_매수 — 낙폭 · VIX · 공포탐욕지수 단계 신호의 맨몸 격자

> 작성/운영 규칙(SoT): `/impl-plan` 스킬(`~/.claude/skills/impl-plan/SKILL.md`)을 반드시 참고하세요.  
> (이 템플릿을 수정하거나 새로운 양식의 계획서를 만들 때도 해당 스킬을 포인터로 두고 준수합니다.)

**상태**: ✅ Done

---

> 상태는 🟡 Draft / 🔄 In Progress / ✅ Done. Done 조건과 기록 규칙은 `/impl-plan` 「3) 스킵 및 완료 규칙」이며 `~/.claude/hooks/plan_lint.py` 가 저장 때 검사한다.

---

**작성일**: 2026-11-16 11:40
**마지막 업데이트**: 2026-11-17 09:23
**관련 범위**: tracks · data(loader) · studies(drawdown_tiers) · scripts · tests · docs · storage/market
**관련 문서**: `src/verify_lab/CLAUDE.md` · `scripts/CLAUDE.md` · `tests/CLAUDE.md` · `.claude/rules/{docs,research,trading}.md`

---

## 1) 목표(Goal)

- [x] 목표 1: 새 매매법 「하락_단계_매수」(`drawdown_tiers`, 검증 등급 · 매매법 종류)를 세운다 — 세 지표의 **단계 신호**(회복하면 다시 켬)를 판정하는 이벤트 정의
- [x] 목표 2: 맨몸 측정 격자 — 대상(SPY · QQQ · DIA, 참고 ^GSPC) × 지표(낙폭 · VIX · 공포탐욕지수) × 단계 × 보유 기간(1 · 3 · 6 · 12 · 24 · 36개월)의 표본 · 오른/내린 비율 · 평균 · 중앙값 · 기준선 · 기준선 대비 차이 · 우연확률, 신호일 원자료
- [x] 목표 3: 같은 격자의 무손절 체결 — `성적표.csv`(시기 5행 · 1차 판정) · `거래내역.csv`
- [x] 목표 4: `설계.md` · `결과.md` · `사전조사.md` 를 쓰고 INDEX · COMMANDS 에 등록한다

## 2) 비목표(Non-Goals)

- **분할 방식 · 비중 단계 · 청산 · 손절 규칙** — 맨몸 결과를 본 뒤 규칙 라운드에서 정한다(`규칙.md` 는 그때 만든다)
- 지표 조합 격자(낙폭 단계 × VIX 단계 …) — Q11 (칸당 사건 0 ~ 2개)
- 하이일드 스프레드 — Q4 진행 안 함
- 수수료 · 슬리피지 · 세금 — 측정의 원칙 10
- 레버리지 상품으로 옮겨 읽기
- 받기 코드 — quant-data `docs/plans/PLAN_vix_fear_greed.md`

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

사용자 질문(2026-11-13): 「VIX · 하이일드 스프레드 · 공포탐욕지수를 활용하면 비교적 저점을 잡을 수 있다」를 웹에서 조사했고, 사용자가 이를 「미국 주식이 많이 빠졌을 때 분할 매수를 «시작»하는 신호, 값이 극단으로 갈수록 비중을 더하는 근거」로 다시 정의했다. 웹 자료는 「높은 VIX 다음 평균 수익률이 높았다」까지만 받치고(Elm Wealth 2026-06-30 — 샤프는 개선 없음, AQR 「Hold the Dip」 2025-12 — 하락 매수 196 조합 평균 샤프 −0.04), 「극단일수록 더」를 미래 참조 없이 잰 자료는 찾지 못했다. 이 저장소의 측정 원칙으로 잰다.

### 확정 결정 (사용자 결정 2026-11-13 ~ 16)

| # | 항목 | 결정 |
| --- | --- | --- |
| Q1 | 잴 것인가 | 이 저장소에서 잰다(검증 등급) |
| Q2 | 기본 신호 | 가격 낙폭 + VIX |
| Q3 · Q6 | 공포탐욕지수 | 낙폭 · VIX 와 같은 격자 축으로 단계별 반응을 재고, 시작 · 비중에 넣을지는 결과를 보고 정한다 |
| Q4 | 하이일드 스프레드 | 진행하지 않는다 |
| Q5 | VIX 출처 | 야후 `^VIX` |
| Q7 | 사건 | **회복하면 다시 켬** — 낙폭은 새 고점, VIX 는 20 미만, 공포탐욕지수는 50 이상에서 다시 켠다. 한 구간 안에서 단계마다 처음 닿은 날 한 번 |
| Q8 | 낙폭 신호의 가격 | **SPY 수정주가 공통** — 세 ETF 에 같은 날 신호 |
| Q9 | 단계 격자 | 낙폭 −5 · −10 · −15 · −20 · −25 · −30 · −40 · −50% / VIX 25 · 30 · 35 · 40 · 50 · 60 이상 / 공포탐욕지수 25 · 20 · 15 · 10 · 5 이하 |
| Q10 | 보유 기간 | 21 · 63 · 126 · 252 · 504 · 756 거래일 |
| Q11 | 측정 단위 | 지표별 단독 격자 셋 + 신호일 원자료에 세 지표 값을 함께 |
| Q12 | 이름 | 「하락_단계_매수」 · `drawdown_tiers` |

### 계획 중 드러나 승인이 필요한 결정 (이 계획서 승인으로 함께 확정)

| # | 항목 | 추천 | 탈락안 · 근거 |
| --- | --- | --- | --- |
| D1 | 진입 시점 | **판정일(그날 종가 정보) → 다음 거래일 종가에 진입.** 측정과 체결이 같은 진입점을 쓴다 | 판정일 종가: VIX 종가는 16:15(ET)로 ETF 종가 16:00 보다 늦고 공포탐욕지수도 장 마감 뒤 확정 → 미래 참조. 다음 거래일 시가(절대 원칙 1 의 문구): `ReturnBasis` 가 `CLOSE` 하나이고 `simulate_scheduled_trade` 가 종가 진입이라 공유 계층을 넓혀야 한다 — 다음 거래일 종가는 그보다 늦어 미래를 보지 않는다 |
| D2 | 참고 ^GSPC 행의 낙폭 신호 | **^GSPC 자기 낙폭**(1928 ~). 판정하지 않는다(원칙 9) | SPY 공통 신호: SPY 가 1993-01-29 부터라 그 앞 70년(1929 · 1974 · 1987 …)을 잃는다 — 지수 행을 두는 이유가 그 긴 축이다 |
| D3 | VIX 를 읽는 법 | **`load_close_series` 에 `max_daily_change_rate` 키워드를 더하고(기본값 그대로), VIX 의 값은 이 매매법 `constants.py` 가 갖는다 — 2.00** | 공용 임계 0.50 그대로: VIX 는 ±50% 를 넘은 날이 10일(최대 2018-02-05 +115.60% — FRED VIXCLS 1990-01-02 ~ 2026-11-11)이라 읽지 못한다. 공용 값을 올림: 한 자산군의 값이 모든 시세의 기준이 된다(비트코인 선례 — `data/crypto_common.py`) |
| D4 | 데이터 첫날이 이미 조건 안일 때 | **그 첫 구간은 판정하지 않고 건수를 남긴다** | 그 구간이 언제 시작했는지 몰라 「처음 닿은 날」을 정할 수 없다. 지금 데이터에서는 해당 없음(공포탐욕지수 첫날 68 · VIX 첫날 17.24) — 재수집 · 대상 추가에 대비한 규칙 |
| D5 | 지표 값이 없는 날 | **그날은 그 지표로 판정하지 않는다(이월하지 않음) · 빠진 날 수를 요약에 남긴다** | 전일값 이월: 절대 원칙 3(보간 금지) |
| D6 | 사건(원칙 5) | **판정일이 속한 하락장(역대 고점 → 새 고점)의 시작일** — ETF 행은 SPY, ^GSPC 행은 ^GSPC. 성적표 `사건` 컬럼 · 원자료에 싣는다 | VIX · 공포탐욕지수 구간은 한 하락장 안에 여럿 생긴다(2022 년 VIX 구간 넷) — 그대로 세면 독립 표본처럼 읽힌다 |
| D7 | 달력 축 분해(원칙 12) | **판정일의 월 · 요일 축을 `통계.csv` 에 함께** — 대부분 칸이 `판정가능` 「아니오」일 것이다 | 축 생략: 원칙 12 · 17 은 축을 안 쪼개거나 행을 지우지 않는다 |
| D8 | 기준선 모집단 | **그 지표를 판정할 수 있는 기간(지표 첫날 ~ 데이터 끝) 안의 모든 거래일**을 같은 진입 규칙(다음 거래일 종가)으로 | 대상 전 기간: 공포탐욕지수 축(2011 ~)과 1993 ~ 의 시장을 섞는다(실행 계층 계약 「신호군과 같은 기간」) |

### 사건 수 미리보기 (수익률은 보지 않음 · 2026-11-13 대화에서 센 값)

회복하면 다시 켜는 정의로 센 단계별 구간 수 — 구현 뒤 신호 수 대조(Phase 3)의 기대값이다. VIX 는 FRED `VIXCLS` 로 셌고 측정은 야후 `^VIX` 라 다를 수 있다.

| 지표 · 기간 | 단계별 구간 수 |
| --- | --- |
| SPY 수정주가 역대 고점 대비 (1993-01-29 ~ 2026-11-10) | −10: 12 · −15: 7 · −20: 4 · −25: 3 · −30: 3 · −40: 2 · −50: 1 (−5 는 세지 않음) |
| ^GSPC 1928 이후 | −10: 26 · −15: 16 · −20: 12 · −25: 10 · −30: 7 · −40: 4 · −50: 2 |
| VIX (1990-01-02 ~ 2026-11-11) | 25: 52 · 30: 25 · 35: 15 · 40: 9 · 50: 3 · 60: 2 |
| 공포탐욕지수 이하 (2011-01-03 ~ 2026-11-12) | 25: 36 · 20: 27 · 15: 19 · 10: 15 · 5: 9 |

깊은 단계는 같은 두세 위기다(SPY −25% 이하 = 2000 ~ 02 · 2008 · 2020 / VIX 50 이상 = 2008-10-06 · 2020-03-09 · 2025-04-08). 「극단일수록 더」의 근거는 그 단계에서 통계가 아니라 원자료로만 보일 것이다.

### 데이터 — quant-data 에서 받는다

- `^VIX_raw.csv`(야후 지수 OHLCV) · `fear_greed_daily.csv`(`Date,Value`) 를 quant-data 가 받아 내보낸다. 받기는 그쪽 계획서
- `storage/market/quant_data_files.txt` 에 두 줄을 더한다. **내보내기는 목록의 파일을 전부 다시 복사**하므로 기존 사본이 바뀌었는지 Phase 1 에서 본다 — quant-data 가 `--end 2026-11-10`(지금 사본의 기준일)으로 받으면 바뀌지 않는 것이 기대값이고, 바뀌면 Phase 4 가 기존 매매법을 다시 돌린다(루트 `CLAUDE.md` 「재수집은 이미 나온 결과를 바꿉니다」)

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- `.claude/plan-config.json` — 이 저장소의 검증 명령·자동 포맷·근거 승격 목적지 (**값의 SoT**)
- 루트 `CLAUDE.md` — 측정의 원칙 · 후보 판정 기준 · 계획서 규약 · 스크립트 실행 규칙
- `docs/MEMORY.md`
- `src/verify_lab/CLAUDE.md` — 계층 간 계약 전부(매매법 이름 · 매매 산출물 · forward return · 기준선 · 비중첩 표본 · 출력 · 받은 사본 · 단일 값 시계열)
- `scripts/CLAUDE.md` · `tests/CLAUDE.md`
- `.claude/rules/docs.md` · `.claude/rules/research.md` · `.claude/rules/trading.md` · `.claude/rules/charts.md`(차트는 만들지 않지만 경계 확인)
- 전역 `~/.claude/rules/python.md` · `~/.claude/rules/python-tests.md`
- 이웃 구현: `studies/halving_cycle/`(측정 격자 · 무손절 일시 격자 체결) · `studies/midterm_cycle/`(대상 정의 · 지수 로드)

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 단계 신호가 Q7 · D4 · D5 대로 판정되고 look-ahead 감시 · 산식 고정 · 표본 보존 테스트가 있다
- [x] 인자 없는 실행이 `통계.csv` · `excess.csv` · `test.csv` · 신호일 원자료 · `성적표.csv` · `거래내역.csv` · `summary.json` 을 낸다
- [x] 신호 수가 위 「사건 수 미리보기」와 맞거나, 다르면 이유가 `설계.md` 데이터 실측 기록에 있다
- [x] 세 번째 사본(Phase 1.5)이 공유 계층 한 곳에서 정의되고, 두 매매법을 다시 돌린 산출물이 바이트 그대로다
- [x] 매매법 계약 테스트(`tests/test_output_contract.py`)에 등록되고 통과한다
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — `docs/검증/하락_단계_매수/{설계,결과,사전조사}.md` 새로 / `docs/INDEX.md` 행 / `docs/COMMANDS.md` 변경 있음(실행 절 · 다시 돌리는 순서) / `scripts/CLAUDE.md` 메타 타입 목록 / `src/verify_lab/CLAUDE.md` 변경 여부(로더 키워드 — 「받은 사본 규칙」 이상치 판정 행에 VIX 를 더한다)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다 (Q1 ~ Q12 · D1 ~ D8 → `설계.md` 「확정된 설계 결정」, 사건 수 · VIX 급등락 · 출처 대조 → 「데이터 실측 기록」, 웹 조사 → `사전조사.md`) — 구현 중 결정 D9 ~ D12 도 `설계.md`, Phase 1.5 결정은 `src/verify_lab/CLAUDE.md`
- [x] 미룬 지적 옮김 — 1건(`docs/DEFERRED_FINDINGS.md` 같은 모양 항목에 덧붙임), 거른 것은 진행 로그 2026-11-17 08:16
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/tracks.py` — `Track("drawdown_tiers", "하락_단계_매수", GRADE_STUDY, KIND_METHOD)`
- `src/verify_lab/data/loader.py` — `load_close_series(path, *, max_daily_change_rate=MAX_DAILY_CHANGE_RATE)` (기본값 그대로 → 기존 호출 무영향)
- `src/verify_lab/studies/drawdown_tiers/` (새 패키지)
  - `constants.py` — `TRACK_NAME` · 단계 격자 · 다시 켜는 수준 · 보유 기간 · 대상 정의(`DATASETS`) · 지표 파일 · VIX 임계 · `OUTPUT_FILES` · 표시 레이블
  - `tiers.py` — 이벤트 정의: 지표 계열 → 구간(다시 켬) → 단계별 첫 도달일. 하락장 시작일(사건)
  - `runner.py` — 측정 조립: 대상 × 지표 × 단계 × 보유 기간의 forward return(long-form) · 기준선 · `summarize` · `excess` · `permutation_test` · `max_non_overlapping` · 월 · 요일 축 · 원자료
  - `trading.py` — 체결 조립: `simulate_scheduled_trade`(무손절 · 다음 거래일 종가 진입) · `trade_columns` · `period_rows`(`tradable` · `event_ids` · `worst_hold_rates`)
- `scripts/run_drawdown_tiers.py` — `--repeats` · `--seed` (이웃 관용), 인자 없이 전 대상
- `tests/test_studies_drawdown_tiers_tiers.py` · `test_studies_drawdown_tiers_runner.py` · `test_studies_drawdown_tiers_trading.py` · `tests/test_data_loader.py`(키워드) · `tests/test_output_contract.py`(`MethodSpec` 등록)
- `storage/market/quant_data_files.txt` (두 줄 · 머리 주석) · 내보내기가 쓰는 `^VIX_raw.csv` · `fear_greed_daily.csv` · `quant_data_manifest.json`
- `storage/results/검증/하락_단계_매수/` (산출물)
- `docs/검증/하락_단계_매수/설계.md` · `결과.md` · `사전조사.md` (새로), `docs/INDEX.md`, `docs/COMMANDS.md`, `scripts/CLAUDE.md`, `src/verify_lab/CLAUDE.md`
- 조건부(Phase 4): `storage/results/매매/{중간선거_사이클,반감기_사이클}/` · 두 매매법 `결과.md` 재실행 기록
- Phase 1.5(사용자 결정 2026-11-16): `measure/constants.py` · `report/constants.py` · `report/run_summary.py` · `execution/run_summary.py` · `studies/{midterm_cycle,halving_cycle}/` 의 constants · runner · trading(· chart) · 두 매매법 테스트 · `tests/test_output_contract.py` · `scripts/run_halving_cycle.py` · `src/verify_lab/CLAUDE.md`
- `docs/COMMANDS.md`: **변경 있음** — 「하락_단계_매수」 실행 절, 「시세를 다시 받은 뒤 다시 돌리는 순서」에 추가

### 데이터/결과 영향

- 새 산출물 폴더 하나. 기존 매매법 산출물은 사본이 바뀌지 않으면 그대로다(Phase 1 에서 확인)
- 공유 계층 변경은 로더 키워드 하나 — 기본값이 같아 기존 산출물이 바이트 그대로여야 한다(Phase 2 에서 기존 두 매매법을 돌려 `git diff --stat storage/results/` 가 비었는지 확인)

## 6) 단계별 계획(Phases)

### Phase 0 — 신호 정의와 로더 계약을 테스트로 먼저 고정(레드)

**작업 내용**:

- [x] `tests/test_studies_drawdown_tiers_tiers.py` — 손으로 만든 짧은 계열로:
  - 낙폭: 새 고점에서 구간이 끝나고, 한 구간 안에서 단계마다 처음 닿은 날 한 번, 깊은 단계는 얕은 단계 이후(또는 같은 날)
  - VIX: 20 미만에서 다시 켜짐, 25 · 30 이 같은 날 처음 닿으면 둘 다 그날
  - 공포탐욕지수: 「이하」 경계(값 25 는 25 단계에 든다) · 50 이상에서 다시 켜짐
  - D4 첫날이 조건 안이면 그 구간 판정 안 함 + 건수 / D5 값 없는 날은 판정 안 함 + 건수
  - D6 사건: 판정일이 속한 하락장 시작일
  - **look-ahead 감시** — 뒤를 자른 입력의 신호가 겹치는 범위에서 전체 입력과 같다
- [x] `tests/test_data_loader.py` — `load_close_series` 가 기본 임계에서 ±50% 초과를 막고, 키워드로 넘긴 임계를 쓴다. **임계는 자기 픽스처 값**(VIX 의 2.00 이 아닌 값)으로 고른다(`tests/CLAUDE.md` 「공유 계층의 테스트는 «자기 픽스처»를 갖는다」)
- [x] 진입 위치 · forward return 산식 고정 테스트(D1 — 판정일 다음 거래일 종가 → +h 거래일 종가, 데이터 끝을 넘으면 제외 + 사유) · 표본 보존(대상 상장 전 신호 · 끝 넘김 건수 — 입력 신호 수 = 집계 + 제외)
- [x] 기준선 산식 고정 테스트(D8 — 그 지표의 판정 가능 기간 안 모든 거래일, 같은 진입 규칙)와 기준선 대비 차이

**Validation**: 새 테스트가 레드인 것을 확인(모듈 없음 · 키워드 없음)

- [x] `poetry run pytest tests/test_studies_drawdown_tiers_tiers.py` — 수집 오류 1(`ModuleNotFoundError: verify_lab.studies.drawdown_tiers`) / `poetry run pytest tests/test_data_loader.py` — 2 failed(`TypeError: unexpected keyword argument 'max_daily_change_rate'`) · 48 passed(새 기본 임계 보존 테스트 1건은 지금 동작을 지키는 쪽이라 통과가 기대값)

---

### Phase 1 — 사본 받기 (quant-data 계획서가 끝나고 사용자가 커밋한 뒤)

**작업 내용**:

- [x] `storage/market/quant_data_files.txt` — `prices/^VIX_raw.csv` · `series/fear_greed_daily.csv` 와 머리 주석(세 매매법)
- [x] quant-data 에서 `python3 scripts/export.py --to ../verify-lab/storage/market`
- [x] `git status --short storage/market/` · `git diff --stat storage/market/` — 새 파일 둘 · 목록 · 매니페스트 밖이 바뀌었는지. 바뀌었으면 Phase 4 를 켠다
- [x] 두 새 파일의 기간 · 행 수를 매니페스트에서 옮겨 진행 로그에 적는다

**Validation**: 위 diff 결과 기록

- [x] diff — `M quant_data_files.txt` · `M quant_data_manifest.json`(커밋 `ef8bd2a` → `ff3306d` · 두 항목 추가) · `?? ^VIX_raw.csv` · `?? fear_greed_daily.csv` 뿐. 기존 사본 9개 바뀌지 않음 → Phase 4 해당 없음

---

### Phase 1.5 — 세 번째 사본을 공유 계층으로 올리기 (이름만 옮김 · 별도 커밋)

> 2026-11-16 15:18 사용자 결정으로 더한 단계(진행 로그). 값은 그대로이고 정의처만 옮긴다 — 산출물이 바이트 그대로여야 한다(`docs/MEMORY.md` 「이름만 바꾸는 변경과 값을 바꾸는 변경을 한 커밋에 섞지 않는다」).

**작업 내용**:

- [x] `measure/constants.py` — `COL_TICKER` · `BASELINE_SUFFIX` · `COL_NON_OVERLAPPING` · `COL_BASELINE_NON_OVERLAPPING`
- [x] `report/constants.py` — `BASELINE_PREFIX` · `MEASURE_COLUMN_LABELS`(측정이 내는 칸 → 한글 이름: 집계 14 · 어긋남 · 판정가능 · 비중첩 둘 · 기준선 접미사 14 · 차이 · 우연확률) · `MEASURE_PERCENT_COLUMNS` · `MEASURE_PROBABILITY_COLUMNS`
- [x] `report/run_summary.py` — `KEY_PERMUTATION_REPEATS` · `KEY_PERMUTATION_SEED` · `KEY_EXCLUDED_COUNT` / `execution/run_summary.py` — `KEY_TARGETS`
- [x] 중간선거_사이클 · 반감기_사이클의 코드 · 테스트 · 스크립트가 소유자에서 직접 가져오게 고치고 자기 정의를 지운다(`__all__` 재노출 없음 — `tests/test_layer_contracts.py`)
- [x] `src/verify_lab/CLAUDE.md` 「어디까지가 공통이고 어디부터 그 검증의 것인가」 — 세 번째에 올린 것으로 측정 표 칸 이름표 · 요약 키를 적는다
- [x] 두 매매법을 인자 없이 다시 돌려 `git status --short storage/results/` 가 빈 출력

**Validation**: 두 매매법 테스트 · 계약 테스트가 통과하고 재실행 diff 가 비었음을 진행 로그에 적는다

- [x] `poetry run pytest tests/test_studies_midterm_cycle_*.py tests/test_studies_halving_cycle_*.py tests/test_output_contract.py tests/test_layer_contracts.py` (passed=523, failed=2 — 둘 다 Phase 2 에서 등록한 `drawdown_tiers` 의 사양 · `OUTPUT_FILES` 가 아직 없어서이며 Phase 2 Validation 이 닫는다. 올리기로 깨진 검사 0) · 재실행 두 매매법 종료 코드 0 · `git status --short storage/results/` 빈 출력

#### Commit Messages (Phase 1.5)

> 이 단계의 파일만 담는 커밋이다(사용자가 커밋을 나누기로 함). 후보는 마지막 Phase 에서 `/commit` 으로 만든다.

1. 검증 / 측정 표 칸 · 이름표 · 요약 키의 공유 계층 이관
2. 검증 / 중간선거_사이클 · 반감기_사이클이 각자 두던 측정 표 상수 13종의 공유 계층 이동
3. 검증 / 하락_단계_매수 도입 전 세 번째 사본이 될 상수의 공유 계층 이관 — 두 매매법 산출물 바이트 동일
4. 검증 / 칸 토큰은 measure, 한글 이름표 · 단위 목록은 report, 요약 키는 report · execution 소유로 정리
5. 검증 / 이름만 옮기는 공유 상수 이관과 두 매매법 · 계약 테스트의 import 정리

---

### Phase 2 — 로더 · 이벤트 정의 · 측정 · 체결 · CLI (그린)

**작업 내용**:

- [x] `data/loader.py` 키워드 → 그 테스트 그린, 기존 두 매매법을 인자 없이 돌려 `git diff --stat storage/results/` 비었음 확인
- [x] `tracks.py` 한 줄 · `docs/INDEX.md` 행(같은 커밋 단위 — `tests/test_tracks.py`)
- [x] `studies/drawdown_tiers/constants.py` · `tiers.py` → Phase 0 테스트 그린
- [x] `runner.py` — 측정 표 · 원자료 · 요약 / `trading.py` — 성적표 · 거래내역 · 요약 / `scripts/run_drawdown_tiers.py`
- [x] `tests/test_studies_drawdown_tiers_runner.py` · `_trading.py` — 작은 합성 시세로 표 모양 · 표본 보존 · 1차 판정(^GSPC 「판정 안 함」)
- [x] `tests/test_output_contract.py` — `MethodSpec` 에 등록(`TestCoverage` · `TestPriceBasis` 등 전부)

**Validation**: `poetry run pytest tests/test_studies_drawdown_tiers_tiers.py tests/test_studies_drawdown_tiers_runner.py tests/test_studies_drawdown_tiers_trading.py tests/test_data_loader.py tests/test_output_contract.py tests/test_tracks.py tests/test_layer_contracts.py` 통과

- [x] 위 명령 — 291 passed · failed 0. 새 테스트의 변형 확인 9종 전부 잡힘(진입을 판정일 종가로 6 failed · VIX 다시 켜기 `<=` · 공포탐욕 `>` · 낙폭 반올림 제거 · D4 첫 구간 판정 · 달력 월 밀림 · 기준선 시작 · 사건을 판정일로 · ETF 가 자기 신호 — 각 1 ~ 4 failed), 변형 뒤 원본 복원 `diff -q` 확인

---

### Phase 3 — 실행 · 대조 · 문서

**작업 내용**:

- [x] `poetry run python scripts/run_drawdown_tiers.py` (인자 없이)
- [x] 대조 — 신호 수를 「사건 수 미리보기」와(VIX 는 야후 · FRED 차이를 날짜로 가린다), 산출물 행 수를 `summary.json` 의 `row_counts` 와, 원자료 몇 줄의 진입가 · 수익률을 사본 종가로 손계산과
- [x] `docs/검증/하락_단계_매수/설계.md` — 확정된 설계 결정(Q1 ~ Q12 · D1 ~ D8 · 탈락안 · 근거) · 데이터 실측 기록(VIX 급등락 10일 · 야후 대 FRED 행 수 · 공포탐욕지수 출처는 quant-data 문서 6장을 가리킴 · 2021-02 전 복원본 · 하이일드 자료 사정)
- [x] `docs/검증/하락_단계_매수/사전조사.md` — 웹 조사(주장 · 반증 · 1차 출처 · 복제 판정 · 미검증)
- [x] `docs/검증/하락_단계_매수/결과.md` — `.claude/rules/research.md` 필수 구조(머리말 데이터 기간 · 관련 파일 · 결론 요약 · 측정 표 · 해석 · 한계 · 재현 방법)
- [x] `docs/COMMANDS.md` · `scripts/CLAUDE.md` 메타 타입 · `src/verify_lab/CLAUDE.md`(이상치 판정 행)

**Validation**: 대조 결과를 진행 로그에 숫자로 적는다

- [x] 진행 로그 2026-11-16 17:50 에 숫자로 적음 — 신호 수 미리보기와 같음 · 파일 행 수 여섯 = `row_counts` · 원자료 14줄 손계산 일치 · 거래내역 6,528 = 신호내역 7,164 − 제외 636

---

### Phase 4 — (조건부) 기존 매매법 다시 돌리기

> Phase 1 에서 기존 사본이 바뀐 경우에만. 바뀌지 않았으면 이 Phase 의 항목을 「해당 없음 — Phase 1 diff 가 새 파일 · 목록 · 매니페스트뿐」으로 체크한다.

**작업 내용**:

- [x] 해당 없음 — Phase 1 diff 가 새 파일 · 목록 · 매니페스트뿐 (`docs/COMMANDS.md` 「시세를 다시 받은 뒤 다시 돌리는 순서」대로 중간선거_사이클 · 반감기_사이클을 인자 없이)
- [x] 해당 없음 — Phase 1 diff 가 새 파일 · 목록 · 매니페스트뿐 (두 매매법 `결과.md` 재실행 기록에 새 데이터 기간과 무엇이 달라졌는지)

**Validation**: 두 실행 종료 코드 0 · 재실행 기록

- [x] 해당 없음 — 사본이 바뀌지 않음. 참고로 Phase 2 · 1.5 에서 두 매매법을 인자 없이 다시 돌려 종료 코드 0 · `storage/results/` 바이트 그대로를 확인함

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

> 🔴 **체크박스와 상태를 먼저 확정하고, `/commit` 은 맨 마지막에** — 이유는 `/impl-plan` 「5) Commit Messages」.

- [x] 필요한 문서 업데이트 확인 (`docs/COMMANDS.md` 변경 있음)
- [x] 자동 포맷 적용 (`poetry run black .`)
- [x] 변경 기능 및 전체 플로우 최종 검증 — 인자 없이 다시 돌려 CSV 여섯 바이트 그대로 · `summary.json` 노트 갱신(진행 로그 2026-11-17 08:16)
- [x] Validation 절에 `/code-review` 와 품질 검증 **실행 결과**를 적는다
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정
- [x] 🔴 **마지막에 `/commit` 을 실행하고 그 후보를 «이 계획서» 의 `#### Commit Messages` 절에 옮긴다** —
      대화에만 내면 그 절이 빈 채로 남는다. **커밋은 사용자가 한다 — 후보만 낸다**

**Validation**:

> 순서는 `/code-review` → 품질 검증이다. 고칠 것 · 회차 상한 · 수정분 검증은 `/impl-plan` 의 `review.md` 가 정한다.

- [x] `/code-review xhigh` **1회차** (발견 14건 — 버그 6 [무거움 1 · 가벼움 5] · 그 외 8 · 조치: 버그 6 수정 — 무거움 1 은 재현 테스트 먼저)
- [x] `/code-review xhigh` **2회차** (발견 14건 — 버그 2 [무거움 1 · 가벼움 1] · 그 외 12 · 조치: 무거움 1 수정(통계 표의 사건 · 비중첩 테스트), 가벼움 1 은 미룬 지적으로(종가 자른 값 대 수익률 — 공유 `trade_rows` 와 같은 모양))
- [x] 수정분 검증 (수정 6건 · 발견 3건 — 무거움 0 · 조치: 고치지 않고 사용자에게 올림 — 테스트 머리말의 「VIX 급등 둘」 · 계층 문서에 넣은 「여럿이면 올린다」가 「세 번째가 올 때」와 어긋남 · 계층 문서의 매매법 둘만 적은 자리들)
- [x] 수정분 검증 — 보고 뒤 사용자 지시 수정 (수정 5건 · 발견 11건 — 무거움 0 · 조치: 고치지 않고 사용자에게 올림 — 진행 로그 2026-11-17 08:16)
- [x] 수정분 검증 — 보고 뒤 사용자 지시 수정 2차 (수정 7건 · 발견 9건 — 무거움 0 · 조치: 고치지 않고 사용자에게 올림 — 494행은 같은 자리 두 번 · 진행 로그 2026-11-17 09:07)
- [x] 수정분 검증 — 보고 뒤 사용자 지시 수정 3차 (수정 2건 · 발견 0건 · 선택 사항 2 — 무거움 0 · 조치: 사용자 결정대로 멈춤 — 진행 로그 2026-11-17 09:23)
- [x] `poetry run python validate_project.py` (passed=1123, failed=0, skipped=0 — Ruff · PyRight 통과)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다** — 추측으로 적은 줄은 그대로 나간다.

1. 검증 / 하락_단계_매수 추가
2. 검증 / 하락_단계_매수 — 낙폭 · VIX · 공포탐욕지수 단계 신호의 맨몸 격자 측정과 무손절 체결 추가
3. 검증 / 미국 주식 하락 단계의 분할 매수 시작 신호 측정 — 아무 날보다 낫게 고르지 못함
4. 검증 / VIX · 공포탐욕지수 사본 추가와 하락_단계_매수 통계 · 신호내역 · 성적표 · 거래내역 산출
5. 검증 / 하락_단계_매수 신설 — 단계 신호 이벤트 정의 · 로더 급등락 임계 키워드 · 계약 테스트 등록과 설계 · 결과 · 사전조사 문서

## 7) 리스크(Risks)

- **깊은 단계는 사건 2 ~ 3개** — 「극단일수록 더」를 통계로 세울 수 없다. 결과 문서가 원자료로 보이고 그렇게 적는다(원칙 2 · 3). 1929 ~ 32(^GSPC 1930-11-10 −50% 단계 뒤 −86.19% 까지)가 반례로 참고 행에만 있다
- **행끼리 독립이 아니다** — 같은 하락장의 단계 · 보유 기간이 미래 경로를 공유한다. `사건` · 비중첩 표본 · 결과 문서 한계로 드러낸다
- **긴 보유 기간은 최근 사건을 뺀다** — 756 거래일 칸은 최근 약 3년 신호가 제외된다(제외 건수 · 사유)
- **2021-02 전 공포탐욕지수는 복원본** — 대조상 CNN 피드와 비슷하게 맞지만(quant-data 문서) 단계 경계(예: 24 대 26)에서 갈릴 수 있다
- **공유 로더 변경** — 기본값이 같아 무영향이어야 한다. Phase 2 에서 기존 매매법 산출물 바이트 대조로 확인
- **사본 재내보내기가 기존 사본을 바꿀 수 있다** — Phase 1 확인 · Phase 4
- **산출물이 크다** — 4 대상 × 19 단계 × 6 보유 기간에 월 · 요일 축과 시기 5행이 붙는다. 행 수를 `row_counts` 로 확인하고, 결과 문서는 전체 축 행만 싣고 나머지는 파일 이름을 밝힌다
- 실제 산출물로 잴 글자 규칙 판정은 없다(신호는 숫자 비교)

## 8) 메모(Notes)

- 조사 원자료(사건 수 · 출처 대조 스크립트와 출력)는 세션 임시 폴더에 있었다 — 남길 값은 이 계획서 Context 와 근거 승격으로 문서에 옮긴다
- 웹 조사 1차 출처: Elm Wealth 「When Fear Spikes, Should You Buy?」(2026-06-30, 직접 읽음) · AQR 「Hold the Dip」(2025-12, PDF 직접 읽음) · FRED 시리즈 페이지(BAMLH0A0HYM2 · BAA10Y · VIXCLS, 직접 읽음) · whit3rabbit/fear-greed-data README(직접 읽음). 나머지는 검색 요약(미검증)

### 진행 로그 (KST)

- 2026-11-16 11:40: 계획서 작성 (Draft — 승인 대기). quant-data `docs/plans/PLAN_vix_fear_greed.md` 가 선행
- 2026-11-16 11:40: 자체 검증 — 1회차: `tests/CLAUDE.md` 필수 산식 고정(기준선 · 초과분) 누락 · 공유 계층 테스트의 자기 픽스처 누락을 Phase 0 에 반영. 2회차(진입 위치 · 대상 달력 · 성적표 축 · 문서 테스트의 `규칙.md` 요구 — 없음 확인) · 3회차(quant-data 선행 순서 · 커밋 주체 · 사본 재내보내기) 개선 없음 → 멈춤
- 2026-11-16 11:53: 사용자 승인(「진행」) — 계획서와 D1 ~ D8 확정. quant-data 계획서부터 착수
- 2026-11-16 12:55: quant-data 계획서(`PLAN_vix_fear_greed`) Done · 사용자 커밋 완료 → **Phase 1(내보내기)부터 착수 가능.** quant-data 매니페스트: `^VIX_raw.csv` 9,285행 1990-01-02 ~ 2026-11-10 · `fear_greed_daily.csv` 3,965행 2011-01-03 ~ 2026-11-10. 같은 갱신에서 바뀐 기존 파일은 TLT · SPTL(quant 용, 「배당 반영」)뿐이라 내보내기 diff 는 새 두 파일 · 목록 · 매니페스트일 것이 기대값
- 2026-11-16 12:55: **구현에 걸리는 quant-data 실측**(그쪽 `docs/research/시세_받기_판정.md` 6.12) — 공포탐욕지수는 `^GSPC` 거래일 3,988일 중 23일이 없다(2020-06-08 ~ 2020-07-08 22일 · 2026-03-12). VIX 는 빠진 날 0 · `^GSPC` 에 없는 휴장일 봉 2일(2026-05-25 · 2026-09-07). → D5 를 이렇게 적용한다: **판정일은 대상의 거래일**(ETF 행은 SPY · 지수 행은 ^GSPC)로 맞추고 지표의 다른 날 값은 쓰지 않으며, 거래일에 값이 없는 날을 지표마다 세어 요약에 남긴다. 구간 다시 켜기(Q7)도 그 거래일 위의 값으로 판정한다
- 2026-11-16 12:55: **`사전조사.md` 재료 — 웹 조사(2026-11-13)**. 판단: 자료가 받치는 것은 「높은 VIX 뒤 평균 수익률이 높았다」까지이고, 「저점 포착」 · 「극단일수록 더」를 미래 참조 없이 잰 자료는 찾지 못함. 세 지표는 독립이 아님(CNN 공포탐욕지수 7 구성요소에 VIX(50일 이동평균 대비) · 정크본드 수요가 들어 있음 — 2차: finmasters · TheStreet · KB Think, CNN 페이지는 HTTP 451 이라 우회하지 않음)
  - [1차 · 직접 읽음] Elm Wealth 「When Fear Spikes, Should You Buy?」 Haghani · White 2026-06-30 https://elmwealth.com/vix-buy-signal/ — S&P 500 · VIX 1990-01 ~, 샤프: 주식·단기채 고정 0.50 · VIX 30 초과 시 비중 확대 0.47 · VIX 반비례 0.54 · VIX 중앙값 17.5 초과 시 100% → 70% 0.54 · 1년 모멘텀 0.59. 원문 "None of these differences are statistically significant." · "the standard error on the Sharpe ratio is at least 0.17" · 높은 VIX 뒤 평균 수익률 패턴은 "The pattern they describe is real"
  - [1차 · PDF 직접 읽음] AQR 「Hold the Dip」 Alternative Thinking 2025 Issue 4(2025-12) https://www.aqr.com/Insights/Research/Alternative-Thinking/Hold-the-Dip — S&P 500 1965-01-01 ~ 2025-09-30, 낙폭 4 × 기간 7 × 보유 7 = 196 조합. "the average Sharpe ratio was -0.04 less than equities (about a 16% degradation …), with over 60% of BTD implementations underperforming" · 1989-10 이후 "-0.27 worse … (a -47% degradation)" · 유의한 알파 "only 16 (i.e., only 8%!)" · 이유 "Value Investing at a Momentum Horizon" · "performs well when market declines are brief, but poorly when declines mark the beginning of a prolonged drawdown" · 적립식을 하락까지 미루는 것에 "The short answer here is also no" 단 "A full analysis will be the topic of follow-on research"
  - [1차 · 직접 읽음] FRED — BAMLH0A0HYM2 "Starting in April 2026, this series will only include 3 years of observations."(Pre-Approval Required · ICE 재배포 금지) · BAA10Y Moody's "MAY NOT BE COPIED OR OTHERWISE REPRODUCED, …"(표시는 Citation Required) · VIXCLS "Copyright, 2016, Chicago Board Options Exchange, Inc. Reprinted with permission."
  - [검색 요약 · 미검증] MUFG 2022-12 Chart of the Day — 약 20번 침체 중 스프레드가 침체 전에 정점인 것 1번, 보통 침체 시작 5 ~ 7개월 뒤 정점 / MSCI — 2008-12 스프레드 정점 · 2009-03 주가 저점 / Marquette 2026-03 「Buy High, Sell Low?」 — 스프레드 정점 6개월 뒤 매수 시 2년 성과 평균 약 20% 낮음 / Giot(2005) · Banerjee · Doran · Peterson(2007) — 높은 VIX 뒤 수익률 양(+)(2차: Cardiff 워킹페이퍼 · CXO) / NY Fed SR723 — 선형 VIX 는 예측력 없음 · 비선형은 있음 / New Frontier Advisors(Esch) — VIX 30 초과 뒤 3개월 평균 약 4 ~ 10%(etftrends · Advisor Perspectives 재게재 = 출처 1, 원문 403 · 404) / 톰 리 2025-04(블록미디어) — VIX 60 → 31 아래면 바닥 / 공포탐욕 백테스트 블로그 둘(결론 상충) / eco3min.fr 의 여러 주장(2008 VIX 첫 30 돌파 뒤 약 40% 추가 하락 등)은 한 사이트라 출처 1
- 2026-11-16 13:34: **Phase 1 완료** — 목록에 두 줄 · 머리 주석(세 매매법), quant-data `ff3306d` 에서 내보냄(11개 복사, 커밋 안 된 변경 없음). `^VIX_raw.csv` 9,285행 1990-01-02 ~ 2026-11-10 · `fear_greed_daily.csv` 3,965행 2011-01-03 ~ 2026-11-10(파일 줄 수 9,286 · 3,966 = 머리 1줄 포함, quant-data 원본과 `cmp` 동일). 기존 사본 9개 바뀌지 않음 → Phase 4 해당 없음
- 2026-11-16 13:34: **실측 — 달력과 지표 빠진 날**(사본 기준). SPY = DIA = QQQ 거래일(각 상장일 뒤, 양방향 0건) · SPY = ^GSPC(1993-01-29 뒤, 양방향 0건). VIX 는 SPY · ^GSPC 거래일에 빠진 날 0, ^GSPC 에 없는 날 2(2026-05-25 · 2026-09-07). 공포탐욕지수는 SPY · ^GSPC 거래일 3,988일 중 23일 빠짐(2020-06-08 ~ 2020-07-08 · 2026-03-12). SPY 첫날(1993-01-29) VIX 12.42 → ETF 행도 D4 해당 없음
- 2026-11-16 13:34: **Phase 0 완료 — 테스트가 정한 인터페이스**(Phase 2 가 이 모양으로 구현). `constants.py`: `TierRule(indicator, levels, fires_below, rearm_level)` — 얕은 → 깊은 순 · 닿는 구역과 다시 켜는 구역이 겹치면 `ValueError` / `DRAWDOWN_RULE` · `VIX_RULE` · `FEAR_GREED_RULE` · `HORIZONS` · `COL_TIER` · `COL_INDICATOR_VALUE` · `COL_ENTRY_DATE` · `REASON_BEFORE_LISTING`. `tiers.py`: `drawdown_rates(close)` · `peak_dates(close)` · `align_indicator(trading_days, indicator)` · `tier_signals(values, rule)` → `.signals`(날짜 · 단계 · 지표 값, 날짜 → 규칙의 단계 순) · `.missing_days` · `.unjudged_days` / `entry_returns(prices, signal_dates, *, horizons, price_column)` · `baseline_returns(prices, *, start, horizons, price_column)`
- 2026-11-16 13:34: **Phase 0 에서 테스트로 박은 해석 — 사용자 확인 대기**(계획서 결정이 말하지 않은 경계). ① 낙폭이 역대 고점과 «같은» 종가(낙폭 0)도 회복으로 보아 다시 켜고 새 하락장의 시작일이 된다(Q7 「새 고점」 · D6) ② D4 의 「건수」는 판정하지 않은 거래일 수다 — 값이 있는 날만 세고, 빈 날은 D5 의 빠진 날로 따로 센다 ③ 판정일에 대상이 없으면(상장 전) 다음 날이 상장일이어도 제외한다 ④ 상장 뒤인데 대상 거래일이 아닌 판정일은 `ValueError`(위 실측상 생기지 않음) ⑤ 빈 날은 신호도 다시 켜기도 하지 않고 상태를 그대로 둔다(D5). 낙폭 −10% 경계는 부동소수점으로 `90/100−1 = −0.09999999999999998` 이라 Phase 2 구현이 경계를 따로 다뤄야 테스트가 통과한다
- 2026-11-16 15:10: 사용자 확정(「추천대로」) — 위 ① ② ③ 을 추천안대로 확정(D9 · D10 · D11 로 `설계.md` 에 승격). ④ ⑤ 는 D5 에서 따라 나온 것. Phase 2 착수
- 2026-11-16 15:18: Phase 2 진행 — 로더 키워드 그린(`tests/test_data_loader.py` 50 passed). 중간선거_사이클 · 반감기_사이클을 인자 없이 다시 돌려 둘 다 종료 코드 0, `git status --short storage/results/` 빈 출력(바이트 그대로). `tracks.py` 한 줄 · INDEX 행(문서 칸은 Phase 3 에서 링크). `constants.py` · `tiers.py` → Phase 0 테스트 36 passed(로더 · tracks 와 함께 146 passed). 단계 표시 이름은 `TierRule.label`(`-10% 이하` · `25 이상`) — 낙폭 단계가 비율이라 `percent` 칸을 더함(기본값 거짓, Phase 0 테스트의 생성자 그대로)
- 2026-11-16 15:18: **신호 수 대조(사본 기준) — 미리보기와 같음.** SPY 낙폭 −5: 37 · −10: 12 · −15: 7 · −20: 4 · −25: 3 · −30: 3 · −40: 2 · −50: 1 / ^GSPC 낙폭 −5: 74 · −10: 26 · −15: 16 · −20: 12 · −25: 10 · −30: 7 · −40: 4 · −50: 2 / VIX(^GSPC 달력 1990 ~) 25: 52 · 30: 25 · 35: 15 · 40: 9 · 50: 3 · 60: 2 — SPY 달력(1993-01-29 ~)은 50 · 24 · 14 · 9 · 3 · 2(1990 ~ 1993 의 2 · 1 · 1 이 빠짐) / 공포탐욕지수 25: 36 · 20: 27 · 15: 19 · 10: 15 · 5: 9(빠진 날 23 · 판정 안 한 날 0). FRED 로 센 VIX 미리보기와 야후 `^VIX` 의 단계별 구간 수가 같음
- 2026-11-16 15:18: **계획에 없던 결정이 드러남 — 세 번째 사본.** runner · trading 이 쓸 상수 중 두 이웃이 같은 값으로 각자 둔 것: `COL_TICKER` · `BASELINE_SUFFIX` · `BASELINE_PREFIX` · `COL_NON_OVERLAPPING` · `COL_BASELINE_NON_OVERLAPPING` · 집계 칸 → 한글 이름 짝(14) · `_RATE_COLUMNS`(9) · `PROBABILITY_COLUMNS`(4) · `KEY_PERMUTATION_REPEATS` · `KEY_PERMUTATION_SEED` · `KEY_TARGETS` · `KEY_EXCLUDED_COUNT`. `src/verify_lab/CLAUDE.md` 「원칙에 없는 것은 「세 번째가 올 때」 정합니다」 — 사용자에게 물음
- 2026-11-16 15:18: 사용자 결정(「먼저 공유 계층으로 올림」) — **계획 조정**: Phase 1.5 를 더하고 DoD · Scope 에 한 줄씩 더함. 무엇이 달라졌나 — 계획서는 새 매매법이 이웃과 같은 상수를 «각자» 두는 것을 전제했으나(영향받는 규칙에 「세 번째가 올 때」가 걸리는 것을 계획 때 보지 못함), 실제로 13종이 세 번째가 됨. 이름만 옮기는 변경이라 커밋을 따로 나눔(`Commit Messages (Phase 1.5)`). 탈락안: 세 번째 사본으로 두고 미룸 — 같은 이름의 정의가 세 벌이 되어 한쪽만 바뀌면 예외 없이 갈림
- 2026-11-16 15:26: **Phase 1.5 완료** — 13종을 소유자 한 곳으로 올림(`measure/constants.py` 칸 토큰 넷 · `report/constants.py` `BASELINE_PREFIX` · `MEASURE_COLUMN_LABELS` · `MEASURE_PERCENT_COLUMNS` · `MEASURE_PROBABILITY_COLUMNS` · `report/run_summary.py` 키 셋 · `execution/run_summary.py` `KEY_TARGETS`). 두 매매법의 constants · runner · trading · 스크립트 · 테스트가 소유자에서 직접 가져오고 자기 정의 · `__all__` 재노출을 지움(반감기 trading 의 `KEY_TARGETS`). 중간선거의 `PERCENT_COLUMNS` · `PROBABILITY_COLUMNS` 는 공통 목록과 같아 지우고, 반감기의 `PERCENT_COLUMNS` 는 공통 목록 위에 자기 칸을 더하는 모양으로 남김. 미사용 import 는 Ruff F401 로 이번 변경의 고아만 걷음(변경 전 Ruff 통과). 검증: 위 Validation
- 2026-11-16 15:40: **Phase 2 완료.** `runner.py`(통계 · excess · test · 신호내역 · 요약) · `trading.py`(성적표 · 거래내역 · 요약) · `scripts/run_drawdown_tiers.py`(`--repeats` · `--seed`). 실제 사본으로 저장 없이 돌려 봄 — 측정 27초 · 통계 8,208행(4 × 19 × 18 × 6) · excess · test 456행 · 신호내역 7,164행 / 체결 2초 · 거래내역 6,528행 · 성적표 2,280행, 경고 0(`-W error`). 계약 테스트에 등록하며 손으로 박힌 목록 셋을 늘림 — `test_output_contract.py` 의 `METHOD_SPECS` · `NO_DISTRIBUTION`(`GSPC` 가격지수), `test_layer_contracts.py` 의 `dataset_record` 호출처 · 실행 모듈 목록. 구현하며 정한 것: 단계 표시는 `-10% 이하` · `25 이상` 문자열, `excess` · `test` 는 달력 «전체» 칸만(D7 의 「`통계.csv` 에 함께」를 글자 그대로), 원자료의 낙폭은 신호 대상(ETF 는 SPY)의 값, 요약의 대상 이름 키는 공유 `KEY_DATASET_LABEL`(이웃의 `KEY_LABEL` 이 세 번째가 되지 않게) · 방향 · 손절선 키는 두지 않음(성적표 칸이 말함)
- 2026-11-16 17:50: **Phase 3 완료.** 인자 없이 실행 — 종료 코드 0 · 33초. 대조: ① 신호 수가 미리보기와 단계마다 같음(VIX 는 ^GSPC 달력 1990 ~ 에서 52 · 25 · 15 · 9 · 3 · 2, SPY 달력은 1993 전 2 · 1 · 1 이 빠진 50 · 24 · 14 · 9 · 3 · 2) ② 파일 행 수 여섯이 `row_counts` 와 같음(통계 8,208 · excess 456 · test 456 · 신호내역 7,164 · 거래내역 6,528 · 성적표 2,280) · 거래내역 6,528 = 신호내역 행 − 제외(1,557 + 1,479 + 1,419 + 2,073) ③ 원자료 14줄(SPY VIX 60 · QQQ 낙폭 −50 · 지수 낙폭 −50 · SPY 공포탐욕 5)의 진입일 · 진입 종가 · 청산일 · 수익률이 사본 종가 손계산과 같음. 야후 대 FRED 는 계획 때 센 값이 남아 있지 않아 FRED 공개 CSV 를 다시 받아 셈(`설계.md` §3.8). 체결 노트에 「보유가 길어 거의 모든 칸이 게이트를 넘는다」를 더하고 다시 돌림 — CSV 일곱 바이트 그대로 · `summary.json` 노트 한 줄만 늘어남. 문서 셋 · INDEX · COMMANDS · `scripts/CLAUDE.md` · `src/verify_lab/CLAUDE.md` 갱신, 문서 테스트(`test_index` · `test_research_docs` · `test_tracks`) 176 passed. 결과 문서를 쓰다 산출물로 다시 확인해 고친 서술 셋 — 「제외」 칸의 정체 · −25% 단계 평균을 만든 건(2020) · 공포탐욕지수 요약 범위(표본 10건 이상 24칸)
- 2026-11-16 19:12: **리뷰 1회차** — 발견 14. 버그 6: [무거움] 대상 사본이 신호 대상보다 짧으면(재내보내기에서 옛 끝날에 머문 종목) `entry_returns` 가 「거래일에 없다」로 멈춤 — 재현 테스트 먼저 빨강 확인 뒤 고침(마지막 거래일 뒤 판정일은 끝 넘김). 변형(데이터 밖으로 미는 줄 제거)에서 그 판정일이 첫 행 가격의 «유효» 체결이 되어 실패 · 원본 복원 `diff -q` 확인 / [가벼움] ① 노트의 ` ~ ` 가 기간 구분자 계약 테스트를 빨갛게 함 ② PyRight 오류 6(bool 누적합 · groupby 키 · 테스트의 `object` 인덱싱) ③ 노트 · CLI 설명이 다시 켜는 수준 · 보유 범위 · 대상 이름을 글자로 박음 — 같은 모양 5곳(`NOTE_SIGNAL_SOURCE` · `NOTE_EPISODE` · `NOTE_SAMPLE` · `NOTE_SCREEN` · CLI 설명)을 상수에서 만들거나 값 없이 씀(`TierRule.rearm_label` 더함) ④ 원자료 종가를 공용 자릿수로 끊음 — 데이터셋 자릿수로(1곳) ⑤ `RULES` 대신 지표 순서를 두 곳에 따로 박음 — 2곳. 그 외 8(고치지 않음): 측정 · 체결이 신호를 두 번 계산(성능) · `_load_prices` 가 경로를 다시 조립 · 제외 집계가 runner · trading 두 벌 · 쓰이지 않는 `COL_INDICATOR_VALUE`(Phase 0 인터페이스) · 장형 표 라벨 짝이 세 매매법에 반복(절반 통합) · `summarize` 두 번(성능) · 공유 계층 주석의 매매법 이름 · 개수 · 변경 이력 — 전역 주석 규칙 위반이라 주석만 고침(주석 수정 예외) · 계층 문서의 낡은 서술 — 사실이 틀어진 56 · 414 · 430행은 DoD 문서 갱신으로 고치고, 「이벤트 정의 계약을 되살린다」(654행)는 단계 신호의 모양이 그 계약(bool Series 하나)과 달라 사용자에게 물음. 검증: PyRight 0 · 관련 테스트 182 passed(`-W error`)
- 2026-11-16 19:40: **리뷰 2회차** — 발견 14. 버그 2: [무거움 — 비켜 간다] 통계 표의 `사건` · `비중첩 표본` 칸을 보는 테스트가 없음 → `TestIndependenceColumns` 를 더함(합성 경로에 첫 하락장 안 VIX 구간 하나 추가 — 체결 테스트와 같은 경로). 변형 둘(사건을 제외 행까지 셈 · 비중첩에 보유 1) 각 1 failed, 원본 복원 `diff -q` 확인 / [가벼움] 신호내역의 종가는 데이터셋 자릿수로 자르고 수익률은 6자리 종가로 냄 — 표에 찍힌 종가로 다시 계산하면 0.01 다른 행이 하락_단계_매수 신호내역 9/6,528 · 거래내역 9/6,528(공유 `trade_rows` — 중간선거 0/58 · 반감기 0/783). 신호내역만 고치면 같은 체결의 두 표가 갈려 `docs/DEFERRED_FINDINGS.md` 의 같은 모양 항목(반감기 `분할포지션.csv`)에 자리를 덧붙임. 그 외 12(고치지 않음): 반감기 · 지수 기준선 모집단의 무작위 뽑기 메모리(지금 실행은 성공 — 성능) · 계층 문서 654행 이벤트 정의 계약(사용자 질문) · 계층 문서의 낡은 서술(343 · 411 · 413행 — DoD 문서 갱신으로 고침) · `trading.py` 머리말의 계획서 참조와 `loader.py` 의 매매법 파일 이름(주석 수정 예외로 고침) · 신호를 두 번 계산(성능) · `_non_overlapping` · `_empty_summary` · `_untested` 가 세 번째 사본(사용자 질문) · 이웃 중간선거 runner 의 기존 `KEY_DATASETS` · `KEY_ROW_COUNTS` 중복(diff 밖 기존) · `KEY_SIGNAL_COUNT` · `KEY_INDICATOR` 두 벌(세 번째 전) · 빈 결과 대체 표의 칸 · `_load_prices` 경로 재조립 · `PREVIEW_HORIZON` 상수(막는 쪽으로만 틀림). 수정분 검증(서브에이전트): 손계산 · 기존 테스트 영향 없음, 무거움 0 · 발견 3(위 Validation) — 규약대로 고치지 않음. 품질 검증(상태 확인): Ruff · PyRight 통과 · Pytest 1,123 passed · 0 failed · 0 skipped. **2회차에 무거운 지적을 고쳤으므로 멈추고 사용자에게 보고**
- 2026-11-17 08:01: 사용자 결정(「추천대로」) — ① 리뷰 3회차를 돌지 않는다(2회차 수정은 테스트 · 문서 · 주석뿐이고 실행 코드 변경 0) ② 수정분 검증의 발견 셋을 고친다(테스트 머리말 「VIX 급등 둘」 · 계층 문서 343행 「여럿이면 올린다」 · 매매법 둘만 적은 자리) ③ 손절선 축은 무손절 한 종을 유지하고 계층 문서 436행에 예외 · `설계.md` 에 결정(D12)으로 남긴다 — 탈락안: 지금 손절선 격자를 냄(분할이면 진입가가 여럿이라 진입가 기준 손절선을 분할 방식보다 먼저 정의할 수 없음) ④ 계층 문서 654행 이벤트 정의 계약 문구를 사실대로 고친다(등락 순위형은 없음 · 수준 단계형은 하락_단계_매수 하나이고 계약은 그 패키지와 `설계.md`) ⑤ `_non_overlapping` · `_empty_summary` · `_untested` 는 올리지 않는다(산식은 이미 공유 · 묶는 모양이 매매법마다 다름 · 뒤의 둘은 두 벌). 보고 뒤 지시한 수정이라 사본을 먼저 뜸(세션 스크래치 `before/`) → 수정분 검증을 거친다
- 2026-11-17 08:16: **보고 뒤 수정 5건(위 ② ③ ④ — 같은 모양을 문서 전체에서 다시 세어 서브에이전트가 짚은 6곳에 464행 「`통계.csv` 와 공존합니다」 1곳을 더함)** — 테스트 머리말 · 주석 3곳, 계층 문서 343 · 436 · 455 · 464 · 494 · 504 · 505 · 559 · 654행, `report/constants.py` 주석 1곳, `설계.md` D12 와 결정 머리말. 문서 · 매매법 · 계층 계약 테스트 234 passed. **수정분 검증**(서브에이전트 · 14 hunk): 무거움 0 · 발견 11 — 규약대로 고치지 않음. 그중 이번에 쓴 문장 자체가 부정확한 것 셋: ① 654행 「수준 단계형은 하락_단계_매수 하나」 — 반감기_사이클 2단계 지표 신호(`indicator_signals.crossing_days`)도 지표 수준으로 신호를 정함(모양은 다름 — 건널 때마다 · 다시 켜는 수준 = 문턱) ② 같은 문단의 결정 목록에 신호를 정하는 Q7 이 빠짐 ③ 494행 괄호의 이유가 이어지지 않음(방향 · 손절선 키가 없는 이유는 성적표 칸이 아니라 한 종이라서). 같은 모양이 남은 자리 넷: 135행 「달력형 … 두 매매법이 셋 다 씀」(하락_단계_매수도 씀) · `tests/test_execution_trade_rows.py:3` 매매법 둘 · 47행 「등락으로」 · 공유 계층 주석 넷의 「매매법 여럿이 … 공유 계층이 가짐」. 그 밖: `설계.md` 머리말 마지막 업데이트 날짜 · `tests/test_output_contract.py` 의 통계 이름 검사가 반감기만 봄 · `.claude/rules/trading.md` 에 D12 가리킴 없음 · 559행 아래 계약 문구가 다음 거래일 진입(D1)을 말하지 않음(이번 수정 전부터)
- 2026-11-17 08:16: **자동 포맷** — `black .` 이 바꾼 파일 8개는 전부 하락_단계_매수 파일(새 패키지 넷 · 새 테스트 셋 · `test_output_contract.py` 의 이 매매법 픽스처 한 덩어리). **최종 재실행**(인자 없이, 종료 코드 0): CSV 여섯은 바이트 그대로이고 `summary.json` 의 노트 다섯 줄만 바뀜 — 리뷰 1회차가 노트를 상수에서 만들게 고친 뒤 다시 돌리지 않아 디스크의 요약이 옛 문구였음. 품질 검증: 아래 Validation
- 2026-11-17 08:16: **Phase 1.5 커밋을 덩어리 단위로 떼어 둠** — 섞인 파일 셋(`src/verify_lab/CLAUDE.md` 152 · 343행 덩어리 / `report/constants.py` 의 import · 측정 표 이름표 덩어리 / `tests/test_output_contract.py` 의 `KEY_TARGETS` 다섯 줄)과 통째로 Phase 1.5 인 파일 13개를 HEAD 위에 얹은 패치(16 파일, 세션 스크래치 `p15/phase15.patch`). 그 트리(HEAD + 패치)에서 Ruff 통과 · PyRight 0 errors · Pytest 1,033 passed · 0 failed · 포맷 변경 0, `git apply --cached --check` 통과
- 2026-11-17 08:16: **미룬 지적 옮기기** — 옮긴 것 1(리뷰 2회차 가벼운 버그 — 종가 자른 값 대 수익률, `docs/DEFERRED_FINDINGS.md` 의 같은 모양 항목에 덧붙임). 거른 것: 리뷰 1회차 그 외 8 · 2회차 그 외 12 · 보고 뒤 수정분 검증 발견 11 — 전부 기준 3(버그가 아님 — 성능 · 코드 정리 · 문서 · 주석 · 검사 보강이며, 검사 보강(통계 이름)이 막는 결함은 파일 이름 오기라 무겁지 않음). 1 · 2회차 그 외 가운데 사용자에게 물은 둘(654행 · 세 번째 사본 함수)은 2026-11-17 결정으로 처리. 2회차 수정분 검증 발견 3 은 2026-11-17 사용자 결정으로 고침
- 2026-11-17 09:07: 사용자 결정(「추천대로」) — 위 08:16 수정분 검증 발견 11 중 ① ~ ⑦ 을 고침(사본 `before2/`). 계층 문서 47 · 56 · 135 · 494 · 654행 문단, `tests/test_execution_trade_rows.py` 머리말, `설계.md` 머리말 날짜. 같은 모양(56행 — 반감기 2단계를 빠뜨림)을 함께 고침. 품질 검증 1,123 passed · 0 failed · 0 skipped. **수정분 검증**(서브에이전트 · 7 hunk): 무거움 0 · 발견 9 — ① 494행 새 이유 「한 종이라 키를 두지 않는다」도 이어지지 않음(중간선거 · 반감기도 방향 한 종인데 `direction` 키를 둠) — **같은 자리 두 번** ② 반감기 2단계의 돌파 정의 결정 ㉙ ① 이 인용에서 빠짐 ③ 「수준형은 둘」이 반감기 3단계 혼합 분할(`split_rule.leg_fills` — MVRV 문턱에 처음 닿은 날)을 세지 않음 ④ Q8 · D2 의 코드 자리(`constants.Dataset.signal_symbol` · `runner.signal_set`)가 `tiers.py` 로만 적힘 ⑤ 공유 계층 주석 넷(`measure/constants.py` · `report/constants.py` · `measure/calendar_entry.py` · 그 테스트)이 그 칸 · 검사를 「달력형 전용」으로 적음(이번 diff 밖 기존) ⑥ 135행 「셋 다 씀」 — 반감기는 진입 달 칸을 안 씀(기존) ⑦ 431 · 504행 「반감기는 사이클당 한 번」이 2단계 신호와 어긋남(성적표 칸에서만 참) ⑧ 반감기 look-ahead 테스트 자리를 안 적음 ⑨ 테스트 머리말의 매매법 목록이 또 낡을 수 있음. 규약대로 고치지 않고 사용자에게 올림
- 2026-11-17 09:23: 사용자 결정(「추천대로」) — 위 ① ② 만 고치고 끝냄(사본 `before3/`). ① 494행은 이유를 빼고 「방향 · 손절선 키는 두지 않는다」 사실만 적음(같은 자리 두 번 — 이유가 없으면 틀릴 문장이 없음) ② 반감기 2단계 인용에 돌파를 정의하는 ㉙ 를 더함. 수정분 검증을 한 번 더 하고 무거움 0 이면 새 발견은 이 로그에만 적고 멈춤. ③ ~ ⑨ 는 고치지 않음(⑤ ~ ⑦ 은 이번 변경 전부터 있던 공유 계층 서술)
- 2026-11-17 09:23: **수정분 검증**(서브에이전트 · 2 hunk) — 무거움 0 · 틀린 문장 0. 선택 사항 둘(고치지 않음 — 위 결정대로 여기서 멈춤): 494행의 「단계 × 보유 기간은 성적표 칸이 말하고」는 이유가 아니라 나란한 사실이라 결함은 아님(반감기도 성적표에 그 칸이 있고 `rule` 에 키를 둠) · 반감기 2단계 인용에 제외 행 결정 ㉘ ① 을 더할 수 있음(모듈 머리말은 ㉘ ① 을 인용). 품질 검증 1,123 passed · 0 failed · 0 skipped

---
