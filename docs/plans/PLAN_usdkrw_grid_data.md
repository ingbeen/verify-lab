# Implementation Plan: 원달러 그리드 G0 — 데이터 확보

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

**작성일**: 2026-08-24 09:35
**마지막 업데이트**: 2026-08-24 10:12
**관련 범위**: 수집(`data/`), scripts, 문서
**관련 문서**: `CLAUDE.md`, `src/verify_lab/CLAUDE.md`, `scripts/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/python.md`, `.claude/rules/docs.md`, `docs/ROADMAP.md`, `원달러_그리드_백테스트_사양서_v2.md`

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

- [x] 목표 1: 사양서 §11.1이 지정한 데이터 4종을 저장소 안에 확보한다 — 원달러 매매기준율, 미국 3개월 T-bill(DTB3), CD 91일물, 미국달러선물 ETF 2종(261240·261250)
- [x] 목표 2: **일별 단일 값 시계열**이라는 새 데이터 형태를 `data/` 계층에 도입한다. 기존 OHLCV 스키마와 폴더·로더를 분리해 두 스키마가 한 곳에서 섞이지 않게 한다
- [x] 목표 3: ECOS 통계표코드·항목코드와 ETF 2종의 데이터 성질을 **실측으로 확정**하고 그 기록을 살아있는 문서에 남긴다
- [x] 목표 4: 논의로 확정된 설계 결정(A·B·C 시리즈)을 `docs/spec/usdkrw_grid.md` 에 이관해 계획서 삭제 후에도 재구성 가능하게 한다

## 2) 비목표(Non-Goals)

- **그리드 매매 로직 구현** — G2 이후. 이번 조각은 데이터만 다룬다
- **0단계 등가성 검증(사양서 §16) 실행** — G1. 이번엔 그 입력이 되는 데이터만 확보한다
- **`.claude/rules/strategy.md` 개정(결정 A1)** — `strategy/grid/` 를 처음 쓰는 G2에서 한다. G0는 `data/`·`scripts/data/` 만 건드리므로 아직 필요 없다
- **루트 사양서를 `docs/strategy/원달러_그리드.md` 로 흡수(결정 A3)** — `.claude/rules/strategy.md` 가 그 문서에 §2 성적을 함께 요구하므로 성적이 나오는 G5에서 한다. 이번엔 INDEX에 등록만 한다
- **기존 `storage/market/` 파일(QQQ·KODEX 200) 재수집** — 재수집하면 `docs/research/` 와 `docs/strategy/` 의 수치가 재현되지 않는다
- **새 외부 라이브러리 도입** — HTTP는 표준 라이브러리 `urllib.request` 로 처리한다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

- 원달러 그리드 백테스트를 하려면 데이터 4종이 필요한데 **저장소에는 하나도 없다.** 현재 `storage/market/` 에는 `QQQ_max.csv` 와 `069500_max.csv` 뿐이다
- 기존 수집 경로로 되는 것은 ETF 2종뿐이다. **환율과 금리는 수집기 자체가 없다**
- `data/loader.py` 의 `load_market_csv()` 는 `Open/High/Low/Close/Volume` 을 필수로 검사한다. 매매기준율·DTB3·CD91은 **일별 단일 값**이라 이 스키마에 들어가지 않는다
- ECOS 통계표코드·항목코드를 **기억으로 적으면 안 된다.** 루트 `CLAUDE.md` 가 pykrx에 대해 "기억이 아니라 실측으로 확정"을 요구했고 같은 이유가 그대로 적용된다
- 사양서 §11.1이 지정한 261240·261250이 실제로 1배/2배 상품인지, 상장일과 수정주가 가용 구간이 어떤지 **확인된 바 없다**
- 논의로 확정된 설계 결정 20여 건이 지금은 **대화에만 있다.** 살아있는 문서로 옮기지 않으면 다음 세션이 같은 논의를 반복한다

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md`
- `src/verify_lab/CLAUDE.md`
- `scripts/CLAUDE.md`
- `tests/CLAUDE.md`
- `.claude/rules/python.md`
- `.claude/rules/docs.md`
- `docs/ROADMAP.md` "계획서의 수명"

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/verify-plan` 스킬)

- [x] 데이터 4종이 저장소에 있고, 각 파일의 행 수·기간·결측 건수가 문서에 기록됐다
- [x] `load_series_csv()` 가 단일 값 시계열을 검증해 읽고, 기존 `load_market_csv()` 의 동작은 바뀌지 않았다
- [x] ECOS 통계표코드·항목코드가 **실측으로** 확정되고 프로브 원자료가 `storage/results/` 에 남았다
- [x] 261240·261250의 종목명·상장일·수정주가 가용 구간·분배금 유무가 실측으로 확인됐다
- [x] 회귀/신규 테스트 추가 (외부 서버 호출 없이 전부 모의로 동작)
- [x] `poetry run python validate_project.py` 통과 (failed=0, skipped=0; passed/failed/skipped 수 기록)
- [x] `poetry run black .` 실행 완료 (마지막 Phase에서 자동 포맷 적용)
- [x] 필요한 문서 업데이트(`docs/COMMANDS.md` / `docs/INDEX.md` / `docs/ROADMAP.md` / `docs/spec/usdkrw_grid.md` — 각각 변경 여부 명시)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (설계 결정 A·B·C 시리즈와 데이터 실측 기록을 `docs/spec/usdkrw_grid.md` 로, Phase 상태를 `docs/ROADMAP.md` 로 이관)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

**신설**

- `src/verify_lab/data/ecos_credentials.py` — ECOS 인증키 로딩
- `src/verify_lab/data/ecos_collector.py` — ECOS 일별 시계열 수집(환율·CD91)과 프로브
- `src/verify_lab/data/fred_collector.py` — FRED DTB3 수집
- `scripts/data/check_ecos.py` — ECOS 통계표·항목 실측 프로브
- `scripts/data/collect_ecos.py` — ECOS 수집 CLI
- `scripts/data/collect_fred.py` — FRED 수집 CLI
- `tests/test_ecos_credentials.py`, `tests/test_ecos_collector.py`, `tests/test_fred_collector.py`
- `docs/spec/usdkrw_grid.md` — 데이터 스펙·실측 기록·확정된 설계 결정

**수정**

- `src/verify_lab/common_constants.py` — `SERIES_DIR`, 단일 값 시계열 스키마 상수 추가
- `src/verify_lab/data/loader.py` — `load_series_csv()` **추가**(기존 함수 불변)
- `src/verify_lab/data/__init__.py` — 신규 공개 함수 재노출
- `tests/test_data_loader.py` — 단일 값 로더 테스트 추가
- `docs/ROADMAP.md` — 검증 목록에 원달러 ETF 등가성 추가, Phase G0~G5 절 신설
- `docs/INDEX.md` — 신규 문서와 루트 사양서 등록
- `docs/COMMANDS.md`: **변경 있음** — ECOS·FRED 수집 명령어와 ETF 수집 예시 추가

**수정하지 않음**

- `data/loader.py` 의 `load_market_csv`·`validate_market_data`·`validate_market_frame` 본문
- `data/pykrx_collector.py`, `data/yfinance_collector.py`, `data/krx_credentials.py`
- `measure/`, `report/`, `studies/`, `strategy/` 전체

### 데이터/결과 영향

- `storage/series/` 신설 — 일별 단일 값 시계열 3종
- `storage/market/` 에 ETF 2종 **신규 추가.** 기존 두 파일은 건드리지 않는다
- 기존 검증·매매 규칙 결과에 영향 없음 (입력 파일이 안 바뀐다)

## 6) 단계별 계획(Phases)

### Phase 0 — 스키마·정책을 테스트로 먼저 고정(레드)

> 새 데이터 형태와 자격증명 정책이 들어오므로 인터페이스를 먼저 못박는다.

**작업 내용**:

- [x] `common_constants.py` 에 `SERIES_DIR`·`COL_VALUE`·`SERIES_REQUIRED_COLUMNS` 추가
- [x] `tests/test_data_loader.py` 에 `load_series_csv` 계약 테스트 추가 — 정상 로딩, 파일 없음, 컬럼 누락, 빈 파일, 중복 날짜 제거, 결측 → `ValueError`, 날짜 오름차순 정렬
- [x] `tests/test_ecos_credentials.py` 추가 — 정상, 파일 없음, 키 없음, 빈 값 → `ValueError`이고 **예외 메시지에 인증키 값이 담기지 않음**
- [x] 이 시점에서는 구현이 없어 레드 상태여도 된다

---

### Phase 1 — 단일 값 로더와 ECOS 자격증명 구현(그린 전환)

**작업 내용**:

- [x] `data/loader.py` 에 `load_series_csv()` 추가. 파일 존재 → 컬럼 검증 → 날짜 파싱 → 정렬 → 중복 제거 → 결측 검사 순서를 기존 로더와 동일하게 맞춘다. **보간하지 않는다**
- [x] `data/ecos_credentials.py` 구현 — `.env` 의 `ECOS_API_KEY` 를 **값으로 반환**한다. `krx_credentials.py` 를 재사용하지 않는 이유를 모듈 docstring에 적는다(그쪽은 pykrx가 환경 변수만 읽어서 생긴 제약이고 ECOS에는 해당 없음)
- [x] `data/__init__.py` 재노출
- [x] Phase 0 테스트 그린 확인

---

### Phase 2 — ECOS 프로브: 통계표코드·항목코드 실측

**작업 내용**:

- [x] `ecos_collector.py` 에 조회 함수와 프로브 함수 구현 (`urllib.request`, 타임아웃 지정, **요청 URL 로깅 시 인증키 구간 마스킹**)
- [x] `scripts/data/check_ecos.py` 작성 — 통계표 목록·항목 목록을 조회해 원자료를 `storage/results/<실행시각>_ecos_probe/` 에 즉시 저장
- [x] 프로브 실행 후 **원달러 매매기준율**과 **CD 91일물**의 통계표코드·항목코드·주기·가용 시작일을 확정
- [x] 실측 결과를 `docs/spec/usdkrw_grid.md` "데이터 실측 기록" 에 기록
- [x] `tests/test_ecos_collector.py` — 응답 파싱·에러 응답 처리·URL 마스킹을 **모의 응답으로** 검증

---

### Phase 3 — ECOS 수집기와 CLI

**작업 내용**:

- [x] Phase 2에서 확정한 코드로 환율·CD91을 수집해 `storage/series/` 에 저장
- [x] `scripts/data/collect_ecos.py` 작성 — 기본값으로 두 시계열 모두 수집, `--series` 로 선택
- [x] 저장 자릿수는 `.claude/rules/python.md` 반올림 규칙표를 따르고 소스별 상수로 둔다
- [x] 수집 실행 후 행 수·기간·결측 건수를 확인해 문서에 기록
- [x] `meta_manager.save_metadata` 로 실행 이력 기록, 메타 타입을 `scripts/CLAUDE.md` 목록에 추가

---

### Phase 4 — FRED DTB3 수집기와 CLI

**작업 내용**:

- [x] `fred_collector.py` 구현 — CSV 응답을 받아 단일 값 시계열 스키마로 정규화. **인증키 불필요**
- [x] FRED가 결측을 `.` 으로 주는지 실측하고, 결측 행은 **메우지 않고 제외한 뒤 건수를 반환**한다
- [x] `scripts/data/collect_fred.py` 작성 후 수집 실행
- [x] `tests/test_fred_collector.py` — 모의 CSV로 파싱·결측 처리·이상치 검증
- [x] 메타 타입 추가

---

### Phase 5 — ETF 2종 실측과 수집

> 기존 스크립트를 인자만 바꿔 쓴다. **신규 코드 없음.**

**작업 내용**:

- [x] `check_pykrx_etf.py --ticker 261240` 실행 — 종목명·상장일·유동성·괴리율·분배금 조정 여부 확인
- [x] `check_pykrx_etf.py --ticker 261250` 실행 — 같은 항목 + **2배 상품이 맞는지** 확인
- [x] 두 종목의 수정주가 가용 구간을 확인 (KRX 3,000거래일 상한에 걸리는지)
- [x] `collect_pykrx.py` 로 두 종목 수집 → `storage/market/261240_max.csv`, `261250_max.csv`
- [x] 실측 결과를 `docs/spec/usdkrw_grid.md` 에 기록. **사양서 §11.1의 "1배/2배" 전제가 실측과 다르면 그 사실을 그대로 적고 사용자에게 보고한다**

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [x] `docs/spec/usdkrw_grid.md` 완성 — 데이터 스펙, 실측 기록, **확정된 설계 결정(A1~A4·B1~B2·C1~C14)을 확정/탈락안/근거 형식으로**
- [x] `docs/ROADMAP.md` 갱신 — 검증 목록에 원달러 ETF 등가성 추가, Phase G0~G5 절 신설, G0 완료 표기
- [x] `docs/INDEX.md` 갱신 — 신규 spec과 루트 사양서 등록
- [x] `docs/COMMANDS.md` 갱신 — ECOS·FRED 수집 명령어, ETF 수집·실측 예시
- [x] `scripts/CLAUDE.md` 메타 타입 목록 갱신
- [x] `poetry run black .` 실행(자동 포맷 적용)
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [x] `poetry run python validate_project.py` (passed=402, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 수집 / 원달러 그리드용 데이터 4종 확보 — ECOS·FRED 수집기와 단일 값 시계열 계층 신설
2. 수집 / ECOS·FRED 어댑터 추가와 ETF 2종 수집 — 실측으로 통계코드·상품 성질 확정
3. 수집 / 일별 단일 값 시계열 스키마 도입 — 폴더와 로더를 OHLCV와 분리
4. 수집 / 환율·금리·미국달러선물 ETF 수집 경로 신설 및 실측 기록
5. 문서 / 원달러 그리드 데이터 스펙 확정과 수집 계층 구현

## 7) 리스크(Risks)

- **ECOS에 원하는 시계열이 없거나 주기가 다를 수 있다** → Phase 2 프로브에서 먼저 확인한다. 없으면 서울외국환중개를 대안으로 검토하되 **임의로 소스를 바꾸지 않고 사용자에게 보고**한다
- **261240·261250이 사양서가 적은 1배/2배 상품이 아닐 수 있다** → Phase 5 실측이 게이트다. 다르면 그대로 보고한다
- **ETF 수정주가가 KRX 3,000거래일 상한에 걸릴 수 있다** → 2017년부터면 약 2,300거래일이라 들어올 가능성이 높지만 실측으로 확인한다. 못 받으면 원본가로 가되 분배락이 남는다는 사실을 기록한다
- **인증키 노출** → ECOS는 인증키가 URL 경로에 들어간다. 로깅·예외 메시지·프로브 원자료 어디에도 키가 남지 않도록 마스킹하고 테스트로 고정한다
- **외부 서버 호출이 테스트에 섞이는 것** → `tests/CLAUDE.md` "외부 의존성 금지"에 따라 전부 모의로 처리한다

## 8) 메모(Notes)

- 사양서 원본은 저장소 루트의 `원달러_그리드_백테스트_사양서_v2.md` 다. G5에서 `docs/strategy/` 로 흡수한다
- 확정된 설계 결정 요약(상세와 근거는 마지막 Phase에서 `docs/spec/usdkrw_grid.md` 로 이관):
  - A1 `strategy` 입력을 "신호 목록 또는 시세 자체"로 확장 (G2에서 적용)
  - A2 사양서 §16 등가성 검증을 별도 검증으로 분리
  - A3 사양서를 `docs/strategy/` 로 흡수 (G5)
  - A4 `strategy/constants.py` 는 이동하지 않고 `strategy/grid/` 신설
  - B1 모든 매매법의 공통 계약은 **일별 총자산 곡선**
  - B2 역방향 매매는 이번에 손대지 않음
  - C1 격자·범위·판정은 **원달러 매매기준율 단일 정의**, ETF는 집행 수단
  - C2 비용은 사양서 §10이 SoT (환전 편도 0.10%). §9.1의 0.2%는 오기로 처리
  - C3 초기 자본금 1억원
  - C4 슬롯 금액 분모는 활성 레벨 전체
  - C5 현금 부족 시 아래(싼) 레벨부터 체결
  - C6 하단 이탈 B안은 당일 종가를 포함하는 칸까지 연장, 배수 1.5 고정, 재조정 시 비활성
  - C7 RP 이자는 일별 발생분을 총자산에 반영, 세금은 지급 시 원천징수
  - C8 종료 시점 미청산 슬롯은 세전 평가 (편향은 한계에 기록)
  - C9 연율화 계수 250으로 통일
  - C10 회전은 전체 왕복 체결 건수와 슬롯당 회전율을 **둘 다** 산출
  - C11 벤치마크 "분할매수 후 보유"는 같은 레벨·같은 금액으로 사되 매도만 하지 않음
  - C12 사양서 §16 이론값의 금리는 **원지표**(DTB3·CD91)
  - C13 슬롯 상한 8%는 그대로 두고 기본 g=0.8%에서 미발동임을 결과로 보고
  - C14 이자 365일 일할, 마스터 달력은 원달러 고시일
- 미해결 1건: 사양서 §17.2 "연 회전 5~15회"가 전체 건수인지 슬롯당인지. **구현을 막지 않으며** G5 결과 해석 때 확정한다
- 사용자 선행 조건 잔여: 261240·261250의 **총보수** 수치 (사양서 §16.2 알파 합격선 기준값, G1에서 필요)

### 진행 로그 (KST)

- 2026-08-24 09:35: 계획서 작성. 설계 결정 A·B·C 시리즈는 사용자 승인 완료 상태에서 착수
- 2026-08-24 09:45: ECOS 프로브로 통계표·항목 코드 확정 — 환율 `731Y001`/`0000001`(1964-05-04~),
  CD91 `817Y002`/`010502000`(1995-01-03~). 두 시계열 모두 사양서 §11.4 의 워밍업 요구를 충족한다
- 2026-08-24 09:50: ECOS 수집 완료 — USDKRW 17,491행, CD91 8,032행, 결측 제외 0
- 2026-08-24 09:53: FRED DTB3 수집 완료 — 18,150행. **799행이 값 공백으로 제외**됐고 전부 미국 시장 휴일이다.
  착수 전에는 "휴장일은 행 자체가 없다"고 적었으나 **실측은 반대**였다 — 행은 있고 값만 비어 있다.
  모듈 docstring 과 테스트 설명을 실측에 맞춰 정정했다
- 2026-08-24 10:00: ETF 2종 실측 — 261240=KODEX 미국달러선물, 261250=KODEX 미국달러선물레버리지.
  **사양서 §11.1 의 1배/2배 전제가 확인**됐고, 2016년 상장이라 **수정주가가 전 기간 가용**하다(2,366 < 3,000 상한).
  2019-03-14 에 261240 종가가 NAV 대비 +21.85% 튄 단일 이상치를 발견했다 — 이 이틀을 포함하면
  261250 회귀 β 가 0.92, 제외하면 1.96 이다
- 2026-08-24 10:06: ETF 4파일 수집 완료 (원본가·수정주가 × 2종). 중간에 `data.krx.co.kr` DNS 해석이
  일시 실패해 261250 수정주가만 재시도로 받았다
- 2026-08-24 10:12: 품질 검증 통과 (402 passed / 0 failed / 0 skipped)

#### 계획 대비 달라진 점

- **Phase 5 의 "신규 코드 없음" 이 틀렸다.** `collect_pykrx.py` 가 `adjusted=False` 를 하드코딩하고 있어
  `--adjusted` 인자를 추가했다. 수집기 모듈은 이미 지원하고 있었고 저장 파일명도 분리돼 있어 CLI 만 손댔다
- **원본가도 함께 받았다.** 사양서 §11.3 의 본검증 기준은 수정 종가지만, §16.4 의 프리미엄/디스카운트
  대조에 원본가와 NAV 가 필요하다. 파일명이 달라 서로 덮어쓰지 않는다
- 실행 주체 규칙 개정으로 낡은 문구가 된 `collect_yfinance.py` 의 "사용자만 실행한다" 를 정정했다
- 수집 결과 표의 「결측 제외」 컬럼이 다음 컬럼과 붙어 나와 정렬을 왼쪽으로 바꿨다
