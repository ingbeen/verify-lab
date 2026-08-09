# INDEX — 문서 지도

> 이 저장소에 무엇이 어디 있고 언제 읽어야 하는지의 **단일 지도**입니다.
> 자동으로 로드되지 않는 문서를 찾을 때 여기를 봅니다.
>
> **문서를 추가·삭제·이동하면 이 파일을 함께 고칩니다.**
> `tests/test_index.py`가 실제 파일 목록과 대조해 검사하므로, 안 고치면 `validate_project.py`가 실패합니다.

---

## 1. 처음 온 세션이 읽을 순서

| 순서 | 문서 | 왜 |
| --- | --- | --- |
| 1 | [../CLAUDE.md](../CLAUDE.md) | 프로젝트 규칙. 측정의 원칙 8개 |
| 2 | [context/README.md](context/README.md) | **사용자의 현재 운용 상태와 이 프로젝트가 시작된 이유. 가장 중요** |
| 3 | [ROADMAP.md](ROADMAP.md) | 검증 대상 목록과 Phase 진행 상태 |
| 4 | [spec/index_extreme_events.md](spec/index_extreme_events.md) | 첫 검증의 확정 설계 |
| 5 | [../src/verify_lab/CLAUDE.md](../src/verify_lab/CLAUDE.md) | 계층 구조와 측정 계층의 절대 원칙 5가지 |

부트스트랩 세션은 [../START_PROMPT.md](../START_PROMPT.md)가 진입점입니다.

---

## 2. 규칙 문서

| 문서 | 내용 | 로드 방식 |
| --- | --- | --- |
| [../CLAUDE.md](../CLAUDE.md) | 프로젝트 전반 규칙, 측정의 원칙, 사고 절차, 수술적 변경 | **항상 자동** |
| [../src/verify_lab/CLAUDE.md](../src/verify_lab/CLAUDE.md) | 계층 분리, 상수 관리 3계층, 핵심 패턴, 절대 원칙 | `src/verify_lab/` 작업 시 자동 |
| [../scripts/CLAUDE.md](../scripts/CLAUDE.md) | CLI 계층 책임, 예외 처리, 명령행 인자 정책 | `scripts/` 작업 시 자동 |
| [../tests/CLAUDE.md](../tests/CLAUDE.md) | 필수 테스트 3종, Given-When-Then, 부동소수점 비교, 파일 격리 | `tests/` 작업 시 자동 |
| [research/CLAUDE.md](research/CLAUDE.md) | 결과 문서 작성 규칙 | `docs/research/` 작업 시 자동 |
| [../.claude/rules/python.md](../.claude/rules/python.md) | 코딩 표준, 반올림 규칙, 로깅 정책, 주석 규칙 | `**/*.py` **Read 시점**에 자동 (실측 확인) |
| [../.claude/rules/docs.md](../.claude/rules/docs.md) | 문서 종류와 SoT 역할, 계획서 수명 | `docs/**` **Read 시점**에 자동 (실측 확인) |
| [../.claude/rules/reference.md](../.claude/rules/reference.md) | reference 폴더 읽기 전용 4금지 | `reference/**` Read 시점에 자동 |
| [../.claude/rules/context.md](../.claude/rules/context.md) | 사용자 소유 문서 보호, 해석 시 붙잡을 맥락 | `docs/context/**` Read 시점에 자동 |
| [../.claude/skills/plan/SKILL.md](../.claude/skills/plan/SKILL.md) | 계획서 작성 절차 (SoT) | `/plan` 스킬 호출 |

> **자동 로드는 편집이 아니라 읽기에서 걸립니다.** 기존 파일을 Read 하면 해당 경로의 규칙이 함께 들어옵니다.
> 따라서 **기존 파일을 열지 않고 새 파일부터 만드는 경우**에만 규칙 문서를 직접 열면 됩니다.
> 실측 근거는 [ROADMAP.md](ROADMAP.md) Phase 0에 있습니다.

---

## 3. 설계·맥락 문서

| 문서 | 내용 | 언제 |
| --- | --- | --- |
| [context/README.md](context/README.md) | 두 운용 문서의 안내와 핵심 결론 | 항상 |
| [context/RESEARCH_q2_2xs_qqq_correlation.md](context/RESEARCH_q2_2xs_qqq_correlation.md) | 운용 포트폴리오의 QQQ 상관 분해. **이 프로젝트의 출발점** | 검증 결과를 해석할 때 |
| [context/RESEARCH_qqq_late_entry.md](context/RESEARCH_qqq_late_entry.md) | 현재 보유 판정(이번 사이클 미진입)과 근거 | 같음 |
| [ROADMAP.md](ROADMAP.md) | 검증 목록, Phase 상태, 계획서 승격 목적지 | 작업 시작·종료 시 |
| [spec/index_extreme_events.md](spec/index_extreme_events.md) | 검증 #1 확정 설계, 확정 결정 8건, 사전 실측 기록 | 검증 #1 관련 전부 |
| [COMMANDS.md](COMMANDS.md) | 실행 명령어 단일 SoT | 스크립트 만들거나 실행할 때 |
| [../README.md](../README.md) | 프로젝트 소개 (사람용) | — |

검증 결과 문서는 완료 시 `docs/research/RESEARCH_<검증명>.md`로 생깁니다.
계획서는 `docs/plans/PLAN_*.md`이며 **임시 산출물**이라 이 지도에 등록하지 않습니다.

---

## 4. reference/ — 참고용 원본 (읽기 전용, 28개)

수정·import·실행하지 않습니다. 읽고 이해한 뒤 `src/verify_lab/`에 새로 작성합니다.
품질 검사(Ruff·PyRight·pytest) 대상에서 제외돼 있습니다.

### 안내

| 파일 | 용도 |
| --- | --- |
| [../reference/README.md](../reference/README.md) | reference 폴더 규칙과 파일별 상세 안내 |

### 통계 해석·과최적화 방어 (결과를 해석하기 전에 읽을 것)

| 파일 | 용도 |
| --- | --- |
| [../reference/과최적화_검증_노하우.md](../reference/과최적화_검증_노하우.md) | 과최적화 원리, PBO/DSR, **거래 수와 통계적 검정력**, **"이미 답을 본" 오염 문제** |
| [../reference/데이터처리_설계원칙.md](../reference/데이터처리_설계원칙.md) | **절대 원칙**(look-ahead·보간·생존편향 금지), 데이터 처리 규칙, 판정식 단일화 |

### 데이터 수집

| 파일 | 용도 |
| --- | --- |
| [../reference/yfinance_downloader.py](../reference/yfinance_downloader.py) | QQQ 수집기 작성 시 — yfinance 호출, 수정주가, 이상치 검증, 최근 2일 제외 |
| [../reference/pykrx_실측기록.md](../reference/pykrx_실측기록.md) | **pykrx 실측 전 필독** — 함수별 반환값과 함정이 실측으로 기록됨 |
| [../reference/data_loader_qbt.py](../reference/data_loader_qbt.py) | `data/` 계층 — CSV 로딩 중앙집중 패턴, 겹치는 기간 추출 |

### 측정 계층

| 파일 | 용도 |
| --- | --- |
| [../reference/event_study.py](../reference/event_study.py) | `measure/` — forward return 2기준, 초과수익, 구간 절단, 계층별 집계 |
| [../reference/analysis_script_example.py](../reference/analysis_script_example.py) | 검증 스크립트의 크기와 형태 |
| [../reference/parallel_executor_qbt.py](../reference/parallel_executor_qbt.py) | 병렬이 실제로 필요해질 때만. **먼저 numpy 벡터화를 시도할 것** |

### 상수 정의

| 파일 | 용도 |
| --- | --- |
| [../reference/common_constants_qbt.py](../reference/common_constants_qbt.py) | `common_constants.py` 작성 시 |
| [../reference/common_constants_krx.py](../reference/common_constants_krx.py) | 같은 용도. 접두사(`COL_`·`KEY_`·`DISPLAY_`·`DEFAULT_`) 사용 예 |

### 테스트 작성 예시

| 파일 | 용도 |
| --- | --- |
| [../reference/test_examples/event_study_test_example.py](../reference/test_examples/event_study_test_example.py) | **look-ahead 감시 테스트**와 산식 고정 테스트 실제 예시 |
| [../reference/test_examples/conftest_example.py](../reference/test_examples/conftest_example.py) | 합성 데이터 픽스처 |
| [../reference/test_examples/conftest_qbt_example.py](../reference/test_examples/conftest_qbt_example.py) | **파일 격리 픽스처** — import 시점 경로 캡처 모듈까지 패치 |

### pykrx 수집 원본 (`reference/pykrx_collect/`)

전종목 스냅샷용 코드입니다. verify-lab은 ETF 한 종목만 필요하므로 **호출 패턴과 검증 방식만** 참고하고
스냅샷·백필 구조를 그대로 가져오지 않습니다.

| 파일 | 용도 |
| --- | --- |
| [../reference/pykrx_collect/__init__.py](../reference/pykrx_collect/__init__.py) | 패키지 초기화 |
| [../reference/pykrx_collect/snapshot.py](../reference/pykrx_collect/snapshot.py) | pykrx 호출과 스키마 검증의 핵심 |
| [../reference/pykrx_collect/snapshot_store.py](../reference/pykrx_collect/snapshot_store.py) | 일자별 불변 파일 저장 |
| [../reference/pykrx_collect/adjusted.py](../reference/pykrx_collect/adjusted.py) | 수정주가 산출 |
| [../reference/pykrx_collect/adjusted_store.py](../reference/pykrx_collect/adjusted_store.py) | 수정주가 저장 |
| [../reference/pykrx_collect/adjusted_backfill.py](../reference/pykrx_collect/adjusted_backfill.py) | 수정주가 백필 루프 |
| [../reference/pykrx_collect/adjusted_quality.py](../reference/pykrx_collect/adjusted_quality.py) | 수정주가 정합성 검증 |
| [../reference/pykrx_collect/backfill.py](../reference/pykrx_collect/backfill.py) | 체크포인트·재시도·휴장 처리 |
| [../reference/pykrx_collect/calendar.py](../reference/pykrx_collect/calendar.py) | **거래일 달력** — 휴장일 판정 |
| [../reference/pykrx_collect/gate_checks.py](../reference/pykrx_collect/gate_checks.py) | **pykrx 실측 스팟체크** — 실측 스크립트 작성 시 참고 |
| [../reference/pykrx_collect/quality.py](../reference/pykrx_collect/quality.py) | 커버리지·이상치·검산 리포트 |
| [../reference/pykrx_collect/names.py](../reference/pykrx_collect/names.py) | 종목명 관리 |
| [../reference/pykrx_collect/meta_store.py](../reference/pykrx_collect/meta_store.py) | 수집 메타 저장 |
| [../reference/pykrx_collect/krx_credentials.py](../reference/pykrx_collect/krx_credentials.py) | KRX 자격증명 처리 |

---

## 5. 데이터와 산출물

| 위치 | 내용 | git |
| --- | --- | --- |
| `storage/market/QQQ_max.csv` | QQQ 일별 시세 (1999-03-10 ~ 2026-07-24, 수정주가). 이관본이며 Phase 1에서 재수집 | 동기화 |
| `storage/market/` | 수집한 원시 시세 | 동기화 |
| `storage/results/<실행시각>_<검증명>/` | 검증 산출물 (CSV, summary.json) | 제외 (재생성 가능) |

KODEX 200 데이터는 아직 없습니다. Phase 1에서 pykrx로 받습니다.

---

## 6. 이 지도의 유지 규칙

- **`docs/`와 `reference/`에 파일을 추가하면 이 문서에 등록합니다.** 예외는 `docs/plans/`(임시 산출물)뿐입니다
- 파일을 지우거나 옮기면 여기서도 지웁니다
- `tests/test_index.py`가 양방향으로 검사합니다 — 등록된 경로가 실재하는지, 실재하는 파일이 등록됐는지
- 규칙 문서 자체의 내용은 여기에 복제하지 않습니다. **어디에 무엇이 있는지만** 적습니다
