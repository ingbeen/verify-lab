# Implementation Plan: QQQ 원본가 전환과 수정주가 데이터셋 제거

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

**작성일**: 2026-08-20 13:06
**마지막 업데이트**: 2026-08-20 14:45
**관련 범위**: 수집(`data/`), 검증(`studies/`), 스펙·결과 문서
**관련 문서**: `src/verify_lab/CLAUDE.md`, `scripts/CLAUDE.md`, `tests/CLAUDE.md`, `docs/research/CLAUDE.md`, `.claude/rules/python.md`, `.claude/rules/docs.md`

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

- [x] 목표 1: **QQQ 를 원본가(배당 미조정) 기준으로 전환한다.** `storage/market/QQQ_max.csv` 를 원본가로 재수집하고, 수집기가 가격 기준을 명시적으로 받도록 한다
- [x] 목표 2: **수정주가 데이터셋을 프로젝트에서 제거한다.** `069500_adjusted_max.csv` 를 삭제하고 `DATASETS` 를 원본가 2종으로 줄인다
- [x] 목표 3: **결과 산출물 어디에도 `가격기준 = 수정주가` 가 남지 않게 한다.** `signals.csv` 등 네 표와 `summary.json` 전부
- [x] 목표 4: **결정을 뒤집는 근거를 스펙에 남긴다.** §7 결정 ⑨ 를 대체하는 새 결정 항목을 확정/탈락안/근거 형식으로 추가한다
- [x] 목표 5: **검증 #1 결과 문서를 원본가 기준으로 재산출한다**

## 2) 비목표(Non-Goals)

- **이벤트 정의·측정 방법·베이스라인·통계 처리는 건드리지 않는다.** 가격 기준만 바꾸고 나머지 설계는 그대로 둔다
- **`measure/`·`report/` 공통 계층은 수정하지 않는다.** 이번 변경은 데이터 소스와 데이터셋 목록의 문제이며 공통 계층은 가격 기준을 모른다
- **수정주가를 받는 기능 자체를 코드에서 삭제하지 않는다.** `pykrx_collector` 의 `adjusted` 인자는 남긴다 — Phase 1 의 실측 대조에 필요하고, 지우면 "왜 안 쓰는지"를 다음 사람이 알 수 없다
- **다른 검증(#2~#4)의 가격 기준은 정하지 않는다.** 이 계획서는 검증 #1 의 데이터셋만 다룬다
- **과거 실행 결과 폴더(`storage/results/`)는 손대지 않는다.** git 제외 대상이고 재생성 가능하다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

**사용자가 결과를 차트와 직접 대조할 수 없다.**

이 프로젝트의 측정 원칙 8은 "사용자가 직접 검증할 수 있어야 한다 — 모든 결과물에 신호일 전체 목록(날짜·가격·등락률)을 포함한다"이다. 그런데 QQQ 는 수정주가라 `signals.csv` 의 종가가 **증권사 앱·차트의 숫자와 다르다.** 보통의 차트는 배당 미포함(미조정)이기 때문이다.

2026-08-19 대조에서 이 차이가 실제로 사용자를 막았다. 2020-03-12 의 차트 종가 177.32 와 파일 종가 170.699097 이 달랐고, 배율 1.038787 을 구해 인접 3일을 예측·대조하고 나서야 배당 조정임이 확인됐다. **대조할 때마다 이 계산을 반복해야 한다면 원자료를 제공하는 의미가 절반으로 준다.**

**이 변경은 스펙 §7 결정 ⑨ 를 뒤집는다.** 결정 ⑨ 는 국내 가격 기준을 "원본가 전 기간 본검증 + 수정주가 구간 대조 병기"로 확정했고, **탈락안 B "원본가 단일 기준"** 의 탈락 사유를 *"가격 기준을 바꾸면 결론이 바뀌는가를 아예 재지 않고 넘어간다"* 로 적어 두었다. 지금 채택하려는 것이 바로 그 탈락안 B 이므로, **새 근거를 확정/탈락안/근거 형식으로 스펙에 남기지 않으면 다음 사람이 같은 논의를 반복한다.**

**QQQ 가격 기준은 §7 결정표에 항목이 없다.** §2 "가격 처리"에 한 줄로 적혀 있을 뿐 탈락안·근거 검토 기록이 없다. 이번에 QQQ 도 함께 결정 항목으로 승격한다.

### 받아들이는 대가 (국내가 이미 겪고 있던 것과 같다)

- **배당락일이 인위적 하락으로 잡힌다.** `yfinance_collector` 의 기존 주석이 경고하던 상황이다. QQQ 는 분기당 약 0.15% 라 테스트 A(±8% 이상)에는 영향이 없지만, **테스트 B(연속 등락)는 배당락일 하루가 연속을 끊을 수 있다.** 얼마나 달라지는지는 Phase 3 에서 실측해 결과 문서에 적는다
- **1년 수익률이 총수익보다 낮게 나온다** (QQQ 배당수익률 연 0.5~0.6%). 다만 **신호군과 베이스라인에 똑같이 걸리므로 초과분 비교에는 거의 영향이 없다.** 결과 문서가 국내 원본가에 대해 이미 같은 방식으로 명시하고 있다(1년 기준 연 약 1.5%p 과소)

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 측정의 원칙 8개, 공통 계층과 개별 검증의 경계
- `src/verify_lab/CLAUDE.md` — 계층 분리, 상수 관리, 측정 계층의 절대 원칙
- `scripts/CLAUDE.md` — CLI 계층에 도메인 로직 금지, 수집 스크립트 실행 주체
- `tests/CLAUDE.md` — 테스트 작성 규칙
- `docs/research/CLAUDE.md` — 결과 문서 형식
- `.claude/rules/python.md` — 코딩 표준, 반올림, 로깅
- `.claude/rules/docs.md` — 문서 종류별 SoT 역할, 스펙과 결과의 분리
- `docs/ROADMAP.md` — 계층 간 계약 다섯 절, 확정된 원시 시세 저장 규칙

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/verify-plan` 스킬)

- [x] 기능 요구사항 충족 — `DATASETS` 가 원본가 2종이고, 산출물 네 표의 `가격기준` 이 전부 `원본가` 다
- [x] `auto_adjust=False` 수집 결과가 차트와 일치함을 **실측으로 확인**하고 스펙에 기록했다 (2020-03-13 = 192.34, 1999-03-10 배율 1.1868)
- [x] 회귀/신규 테스트 추가 — 수집기 가격 기준 인자 2건, `DATASETS` 불변조건 3건
- [x] `poetry run python validate_project.py` 통과 (passed=**279**, failed=**0**, skipped=**0**)
- [x] `poetry run black .` 실행 완료 (마지막 Phase에서 자동 포맷 적용)
- [x] 필요한 문서 업데이트 — `docs/COMMANDS.md` **변경 있음**, `scripts/CLAUDE.md` **변경 있음**, `docs/INDEX.md` **변경 있음**, 루트/기타 CLAUDE.md **변경 없음**
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다.
      결정과 탈락안은 스펙 §7 결정 ⑰, 실측 수치는 스펙 §8 두 절("QQQ 수정주가의 조정 배율"·"yfinance 원본가는 분할 반영·배당 미반영")과 §7 "전환 실측",
      측정 결과는 결과 문서, 진행 상태는 ROADMAP, 실행 명령어는 COMMANDS 로 옮겼다
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/data/yfinance_collector.py` — 가격 기준 인자 추가, 기본값 원본가
- `scripts/data/collect_yfinance.py` — CLI 인자 노출
- `scripts/data/collect_pykrx.py` — 수정주가 수집·저장 중단 (원본가만 저장)
- `src/verify_lab/studies/index_extreme/constants.py` — `DATASETS` 를 원본가 2종으로, QQQ `price_basis` 를 `원본가` 로
- `src/verify_lab/studies/index_extreme/runner.py` — `NOTE_SAME_PARAMETERS` 문구 (국내 두 기준 대조 전제가 사라짐)
- `tests/test_yfinance_collector.py`, `tests/test_pykrx_collector.py`, `tests/test_studies_runner.py`
- `storage/market/QQQ_max.csv` — 원본가로 재수집 (**사용자 실행**)
- `storage/market/069500_adjusted_max.csv` — **삭제** (git 이력에 남아 복구 가능)
- `docs/spec/index_extreme_events.md` — §2 가격 처리, §7 결정 항목 신설, §8 실측 기록 추가
- `docs/research/RESEARCH_index_extreme_events.md` — 원본가 기준 재산출
- `docs/ROADMAP.md` — 대조 진행 상태 갱신
- `docs/HANDS_ON.md` — 수정주가 전제 문구 정리 (3단계 배율 절, 자주 하는 오해 표)
- `docs/COMMANDS.md`: **변경 있음** — `collect_yfinance.py` 에 가격 기준 인자가 생기고, `collect_pykrx.py` 의 산출 파일이 하나로 준다

### 데이터/결과 영향

- **출력 스키마는 바뀌지 않는다.** 컬럼 구성·순서 그대로이며 `가격기준` 컬럼의 값에서 `수정주가` 가 사라질 뿐이다
- **행 수가 준다.** 신호군 396 → **264개**(데이터셋 3 → 2), `signals.csv` 19,611 → 약 12,700행
- **QQQ 숫자가 전부 바뀐다.** 종가는 차트와 일치하게 되고, 등락률은 배당락일 근처만, 수익률은 배당분만큼 달라진다
- **기존 결과와 비교가 필요하다.** 특히 테스트 A 신호 7건의 날짜가 유지되는지, 테스트 B 신호 수가 얼마나 달라지는지를 Phase 3 에서 확인해 결과 문서에 적는다

## 6) 단계별 계획(Phases)

### Phase 0 — 가격 기준 정책을 테스트로 먼저 고정(레드)

> 이 Phase 를 두는 이유: **최종 결과(신호일·수익률)가 달라지는 변경**이고, `auto_adjust` 는
> 기존 코드가 "바뀌면 사고가 소리 없이 일어난다"고 명시적으로 경고한 지점이다.

**작업 내용**:

- [x] `tests/test_yfinance_collector.py` — 기존 `test_history_is_called_with_adjusted_price_and_raising_errors` 를 **원본가 기준으로 뒤집는다.** `auto_adjust=False` 가 명시 전달되는지, 인자를 생략하면 안 되는지 검사 → `test_history_is_called_with_raw_price_and_raising_errors`
- [x] `tests/test_yfinance_collector.py` — 가격 기준 인자를 바꾸면 `history()` 에 그대로 전달되는지 검사 → `test_adjusted_argument_is_forwarded_to_history`
- [x] `tests/test_studies_runner.py` — `DATASETS` 에 `수정주가` 가 없다는 불변조건 테스트 추가 → `TestDatasetsInvariant` 3건 (표시 이름·파일 경로·데이터셋 구성)
- [x] ~~`tests/test_pykrx_collector.py` — CLI 가 원본가 파일 하나만 저장하는지 검사~~ → **철회.** `pytest.ini` 의 `testpaths = tests` 라 `scripts/` 는 pytest 대상이 아니고, 이 저장소의 테스트는 전부 `src` 모듈에 붙는다. CLI 변경은 Phase 1 에서 수동 확인한다

**Validation**:

- [x] 위 테스트가 **의도대로 실패**하는 것을 확인 (레드) — 2026-08-20 13:20, `5 failed, 44 passed`. 실패 5건이 전부 의도한 테스트이고 기존 테스트는 하나도 깨지지 않았다

---

### Phase 1 — 수집기 가격 기준 전환 + 실측(그린 유지)

**작업 내용**:

- [x] `yfinance_collector.collect_yfinance_history` 에 `adjusted: bool = False` 인자 추가.
      **`pykrx_collector` 가 이미 쓰는 시그니처와 같은 이름·같은 의미**로 맞춘다 (관용 단일화)
- [x] `history(period="max", auto_adjust=adjusted, raise_errors=True)` — 결과를 좌우하는 인자는 계속 명시 전달
- [x] 모듈 주석의 `auto_adjust` 경고 문구를 **원본가 기준에 맞게** 갱신 (분배락이 남아 있다는 사실과 그 이유)
- [x] `CollectionResult` 에 `adjusted` 추가 — CLI 요약과 `meta.json` 이 어느 기준으로 받았는지 남기게 한다.
      `pykrx_collector.PykrxCollectionResult` 와 같은 형태다
- [x] `scripts/data/collect_yfinance.py` 에 `--adjusted` 인자 노출 (기본값 원본가). `--help` 로 확인
- [x] `scripts/data/collect_pykrx.py` 가 **원본가만 저장**하도록 변경. `adjusted` 인자는 모듈에 남기되 CLI 에서 쓰지 않는다.
      두 번째 호출이 사라져 orphan 이 된 `import time` 과 `CALL_INTERVAL_SECONDS` 를 정리했다
- [x] `docs/COMMANDS.md` 와 `scripts/CLAUDE.md` 갱신 — **사용자가 지금 이 명령어를 쓰므로 Phase 4 로 미루지 않았다**
- [x] **[사용자 실행] 실측 ① 배당** — 03-12 **177.32**, 03-13 **192.34**, 03-16 **169.30**, 03-17 **182.14** 로 차트값과 일치
- [x] **[사용자 실행] 실측 ② 분할** — 1999-03-10 이 **51.0625**, 배율 **1.1868** 로 정상 범위(1.15~1.25). 분할 미반영이었다면 99~108 이었다
- [x] 전 기간 배율 확인 — 공통 6,896일에서 **1.000000 ~ 1.186754**, **1.5배 이상 튀는 날 0건**. 분할 불연속이 없다
- [x] 실측 결과를 `docs/spec/index_extreme_events.md` §8 에 "데이터 소스 실측 — yfinance 원본가는 분할 반영·배당 미반영" 으로 기록

**Validation**:

- [x] Phase 0 의 수집기 테스트가 그린
- [x] 실측 종가가 차트와 일치

---

### Phase 2 — 데이터셋 목록 정리(그린 유지)

**작업 내용**:

- [x] `constants.py` — QQQ 의 `price_basis` 를 `DISPLAY_PRICE_BASIS_RAW` 로 변경
- [x] `constants.py` — `kodex200_adjusted` 항목 제거. `DATASETS` 가 2종이 된다
- [x] `constants.py` — `Dataset` docstring 의 "국내는 원본가가 본검증이고 수정주가가 대조" 문구를 새 결정에 맞게 갱신
- [x] `DISPLAY_PRICE_BASIS_ADJUSTED` 상수의 존치 여부 판단 — **참조 0건이 되어 제거**했다. 패키지 밖으로 내보내지도 않던 상수다
- [x] `runner.py` — `NOTE_SAME_PARAMETERS` 문구에서 "국내 원본가와 수정주가의 대조" 전제를 걷어낸다
- [x] `runner.py` 모듈 주석의 "KRX 수정주가 조회 창이 하루씩 굴러가 다른 날 실행하면 대조가 성립하지 않는다" 문구 정리
- [x] `tests/test_studies_runner.py` — `TestMultipleDatasets` 클래스 설명을 "여러 데이터셋을 한 실행에 담는 계약" 으로 정정
- [x] **[사용자 실행] `storage/market/069500_adjusted_max.csv` 삭제** (2026-08-20). git 이력에 남아 복구 가능하다

**Validation**:

- [x] Phase 0 의 `DATASETS` 불변조건 테스트가 그린 — 전체 `279 passed` (기존 275 + 신규 4)
- [x] `grep -rn "수정주가" src/ scripts/` 결과에 남은 것이 전부 의도된 것인지 확인

---

### Phase 3 — 재실행과 결과 대조

**작업 내용**:

- [x] `poetry run python scripts/studies/run_index_extreme.py` 실행 (조합 264개) — `20260820_135545_index_extreme`
- [x] 신호군 수·신호일 수·신호 0건 조합 수를 기록 — **248개 집계**(신호 0건 16개 제외), **신호일 12,679건**
- [x] **이전 결과(`20260819_091129_index_extreme`)와 대조**하고 아래를 표로 남긴다
  - [x] 테스트 A(K=10, 2003) QQQ 신호 7건의 **날짜가 유지되는가** → **날짜·등락률·사건 번호가 완전히 동일.**
        조정 배율이 분자·분모에 함께 걸려 약분되므로 등락률이 불변인 것이 확인됐다
  - [x] 테스트 B QQQ 신호 수가 얼마나 달라졌는가 → **기간 연장분(5건)을 잘라내면 순 +23건.**
        41건이 사라지고 64건이 생겼으며 **새로 생긴 64건은 전부 연속 하락**이다.
        **신호가 바뀐 날짜 22개 전부(100%)가 배당락일 직후 10거래일 안**이고, 설명되지 않는 변화는 0건이다
  - [x] 1년 수익률이 배당분만큼 낮아졌는가 → **1년 평균 -0.889%p.** 구간이 짧을수록 작아진다 (1일 -0.053, 1개월 -0.010)
  - [x] 초과분(베이스라인 대비)이 거의 그대로인가 → **1년·단순 보유 기준 +0.058%p (중앙값 +0.030%p).**
        절대 수익률은 -0.889%p 인데 초과분은 사실상 0 이다. **왜곡이 신호군과 베이스라인에 똑같이 걸려 약분된다**
- [x] 대조 결과를 결과 문서에 실을 형태로 정리

**Validation**:

- [x] 실행이 예외 없이 끝나고 산출물 5개가 생성됐다 (`signals` 12,679 / `statistics` 2,976 / `excess` 8,928 / `test` 8,928)
- [x] 위 네 항목의 수치가 표로 정리됐다

---

### Phase 4 — 스펙·결과 문서 갱신

**작업 내용**:

- [x] `docs/spec/index_extreme_events.md` §2 "가격 처리" — QQQ·KODEX 200 모두 원본가로 갱신, 대조 병기 문단 정리
- [x] `docs/spec/index_extreme_events.md` §7 — **결정 ⑰ 추가** (확정 / 탈락안 3종 / 근거). "전환 실측" 절에 수치를 함께 실었다
- [x] **결정 ⑨ 에 "⑰ 로 대체됨" 표시**를 남겼다. 지우지 않았다 — 탈락안과 그 이유가 기록의 핵심이다
- [x] `docs/spec/index_extreme_events.md` §8 — 사전 실측 표가 **수정주가 기준이었음을 명시**했다. 등락률·순위·날짜는 가격 기준에 불변이므로 값은 그대로 둔다
- [x] `docs/research/RESEARCH_index_extreme_events.md` — 원본가 기준으로 재산출. §1·§3·§5·§7·§9·§10·§11·§12·§15·§16 갱신, §6.5·§8.5 를 가격 기준 절로 교체, 결론 요약에 10번 항목 추가
- [x] `docs/ROADMAP.md` — 검증 #1 결론 절과 "사용자 직접 대조 진행 상태" 갱신, Phase 1 기록에 대체 표시
- [x] `docs/HANDS_ON.md` — 손계산 예시를 새 값으로 갱신하고, 배율 절을 "다른 자료와 비교할 때 쓰는 법" 으로 정리
- [x] `docs/COMMANDS.md` — 수집 명령어 갱신 (`--adjusted` 인자, pykrx 산출 파일 1개)
- [x] `docs/INDEX.md`·`scripts/CLAUDE.md` — 삭제된 파일과 메타 내용 반영

**Validation**:

- [x] `grep -rn "수정주가" docs/` 결과에 남은 것이 전부 의도된 것(역사 기록·탈락안 설명)인지 확인
- [x] `poetry run python -m pytest tests/test_index.py -q` 통과

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` 포함 여부 명시 — **변경 있음**)
- [x] `poetry run black .` 실행(자동 포맷 적용) — 1개 파일 재포맷
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [x] `poetry run python validate_project.py` (passed=**279**, failed=**0**, skipped=**0**) — Ruff·PyRight·Pytest 전부 통과

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 수집 / QQQ 를 원본가로 전환하고 수정주가 데이터셋 제거 — 차트 직접 대조 가능
2. 검증 / 가격 기준을 원본가 단일로 확정 — 스펙 결정 ⑨ 대체와 결과 문서 재산출
3. 수집 / yfinance 가격 기준 인자 추가와 pykrx 수정주가 수집 중단
4. 검증 / 데이터셋을 원본가 2종으로 축소 — 조합 396 → 264 및 산출물 재생성
5. 문서 / 원본가 전환 결정 기록과 검증 #1 결과 문서 재산출

## 7) 리스크(Risks)

| 리스크 | 완화책 |
| --- | --- |
| **`auto_adjust=False` 가 차트와 다를 수 있다.** yfinance 가 분할까지 미조정으로 주면 1999년 이후 QQQ 분할이 반영되지 않아 과거 가격이 통째로 틀린다 | **Phase 1 을 실측으로 막는다.** 2020-03-13 = 192.34 를 확인하기 전에는 Phase 2 로 넘어가지 않는다. 어긋나면 계획을 멈추고 원인부터 본다 |
| **테스트 B 결과가 크게 흔들릴 수 있다.** 배당락일이 연속을 끊으면 신호 수가 달라진다 | 흔들리는 것 자체가 측정 결과다(측정의 원칙 7). Phase 3 에서 **건수를 세어 결과 문서에 그대로 싣는다** |
| **결과 문서 재작성 중 옛 수치와 새 수치가 섞일 수 있다** | §3.1 데이터 파일 표부터 먼저 갱신해 기준을 확정하고, 표 단위로 통째로 교체한다. 부분 수정하지 않는다 |
| **`069500_adjusted_max.csv` 삭제로 결정 ⑨ 의 근거 데이터가 사라진다** | git 이력에 남아 복구 가능하다. 그리고 결정 ⑨ 는 지우지 않고 "대체됨" 표시로 남긴다 |
| **국내 수정주가 재수집이 불가능해진다** — KRX 조회 창이 최근 3,000거래일로 굴러가므로 지금 파일과 같은 구간을 다시 받을 수 없다 | 위와 같이 git 이력에 남는다. 되살릴 일이 생기면 `git show` 로 꺼낸다 |

## 8) 메모(Notes)

- **사용자 실행 항목** — Phase 1 의 QQQ 재수집·실측, Phase 2 의 `069500_adjusted_max.csv` 삭제.
  AI 는 코드만 쓰고 실행 방법을 안내한다 (`scripts/data/` 는 외부 서버에 요청을 보내므로 사용자만 실행)
- **`DISPLAY_PRICE_BASIS_ADJUSTED` 상수 처리** — Phase 2 에서 참조가 0건이 되면 제거하고, 남으면 둔다.
  사전에 존재하던 데드 코드가 아니라 **이번 변경으로 생긴 orphan** 이므로 정리 대상이다
- **결정 ⑨ 는 지우지 않는다.** 탈락안과 그 이유가 스펙의 존재 이유이며, 지우면 "왜 대조를 뺐지?"가 다시 논의된다
- 대조 중 확인된 배율 실측(2020-03 구간 1.038787, 인접 3일 일치)은 이미
  `docs/spec/index_extreme_events.md` "데이터 소스 실측 — QQQ 수정주가의 조정 배율" 로 승격돼 있다.
  **이 계획서를 지워도 그 근거는 남는다**

### 진행 로그 (KST)

- 2026-08-20 14:45: **Phase 4·마지막 Phase 완료.** `validate_project.py` passed=279 failed=0 skipped=0.
  KODEX 200 원본가 결과는 네 산출물 모두 이전 실행과 **바이트 단위로 동일**해 국내 수치는 문서에서 손대지 않았다.
  QQQ 수치만 갱신했고, 결론은 하나도 뒤집히지 않았다 — 테스트 B 유의 비율이 5.0% → 4.3% 로 오히려 기대치 아래로 내려갔다
- 2026-08-20 14:05: **Phase 1~3 완료.** 실측으로 `auto_adjust=False` 가 분할 반영·배당 미반영임이 확정됐다.
  **주의: 가격 기준만 바뀐 것이 아니라 QQQ 데이터가 7거래일 늘었다**(2026-08-07 → 08-18, 6,896 → 6,903행).
  대조에서는 2026-08-07 로 잘라 기간 효과를 분리했고, 잘라낸 뒤 남은 차이가 곧 가격 기준 효과다.
  **결과 문서에도 이 분리를 명시해야 한다** — 그러지 않으면 늘어난 기간의 영향이 배당락 탓으로 잘못 읽힌다
- 2026-08-20 13:35: **Phase 1 코드 완료.** 수집기 테스트 2건 그린(`66 passed`), 남은 실패 3건은 Phase 2 의 `DATASETS` 불변조건이다.
  두 CLI 를 `--help` 로 확인했다(네트워크 미사용). **여기서 멈추고 사용자 실측을 기다린다** —
  `DATASETS` 라벨을 먼저 원본가로 바꾸면 파일은 수정주가인데 라벨만 원본가인 상태가 되므로 순서를 지킨다.
  대조 기준값: 현재 `QQQ_max.csv`(수정주가) 1999-03-10 종가 **43.027061**, 2020-03-12 **170.699097**, 2020-03-13 **185.158295**
- 2026-08-20 13:20: **Phase 0 완료(레드).** `5 failed, 44 passed`. Phase 0 의 pykrx CLI 테스트 항목은 철회했다 —
  `pytest.ini` 가 `testpaths = tests` 이고 `scripts/` 를 수집하지 않아 CLI 는 이 저장소의 테스트 대상이 아니다.
  `scripts/CLAUDE.md` 가 CLI 를 "인자 파싱·호출·표시"로 한정한 것과 같은 방향이며, CLI 변경은 Phase 1 에서 수동 확인한다
- 2026-08-20 13:10: **yfinance 0.2.66 소스 확인(외부 요청 없음).** `scrapers/history.py` 에서 가격을 변형하는 곳은
  `auto_adjust`/`back_adjust` 둘뿐이고 그 내용은 `utils.py:445` 의 `ratio = Adj Close / Close` 스케일링이 전부다.
  **분할은 `Stock Splits` 이벤트 컬럼으로 붙기만 하고 가격에 곱해지지 않는다**(history.py:419).
  따라서 "원본가가 분할 반영본인가"는 **야후 서버 응답의 성질**이며 소스로는 판정할 수 없다.
  → Phase 1 실측에 **분할 이전 날짜(1999-03-10)** 대조를 추가해 판별 가능하게 만들었다
- 2026-08-20 13:06: 계획서 작성. 사용자가 "결과 파일과 `storage/market` 어디에도 수정주가를 두지 않는다"로 결정. 이유는 보통의 차트가 배당 미포함이라 대조가 불가능하다는 것

---
