# 새 세션 시작 프롬프트

> 이 파일은 verify-lab 작업을 이어받는 세션에 붙여넣을 프롬프트입니다.
> **작업이 진척되면 이 파일도 함께 갱신합니다.** 낡은 진입점은 없는 것보다 나쁩니다.

---

verify-lab 프로젝트를 이어서 진행한다. 설계는 확정돼 있고, 부트스트랩과 **미국 데이터 확보까지** 끝났다.

## 먼저 읽을 것 (순서대로, 전부)

1. `CLAUDE.md` — 프로젝트 규칙. 특히 "이 프로젝트가 무엇인가"와 "측정의 원칙" 8개 항목
2. **`docs/context/README.md`와 그 폴더의 두 문서** — 내 현재 투자 상태이자 이 프로젝트가 시작된 이유.
   가장 중요한 문서다. 검증 결과를 해석할 때 이 맥락이 없으면 쓸모없는 보고가 된다
3. `docs/ROADMAP.md` — **진행 상태의 SoT.** 무엇이 끝났고 무엇이 남았는지는 여기가 기준이다
4. `docs/spec/index_extreme_events.md` — 첫 검증의 확정 설계. **이미 논의로 확정된 내용이므로
   설계를 다시 제안하지 말 것.** 특히 §7 "확정된 설계 결정"과 §8 "사전 실측 기록"
5. `src/verify_lab/CLAUDE.md` — 계층 분리, 상수 관리, **측정 계층의 절대 원칙 5가지**,
   그리고 확정된 경로 기준점·컬럼 스키마 규약
6. `.claude/rules/python.md` — 코딩 표준. `.py` 파일을 읽으면 자동 주입되지만,
   **기존 파일을 열지 않고 새 파일부터 만들 때는 주입되지 않으니 직접 열 것**
7. `scripts/CLAUDE.md`, `tests/CLAUDE.md`, `docs/research/CLAUDE.md`

나머지 문서와 `reference/`의 참고 자료가 어디 있는지는 `docs/INDEX.md`에 지도로 정리돼 있다.
**문서를 추가하면 INDEX에 등록해야 한다** — `tests/test_index.py`가 검사하므로 빠뜨리면
`validate_project.py`가 실패한다.

## 현재 상태

**되어 있는 것**

- 폴더 구조, 설정 파일, 하네스(`.claude/`의 훅·규칙·`/plan` 스킬), 규칙 문서 전체
- 설계·맥락 문서 — `docs/context/`, `docs/ROADMAP.md`, `docs/spec/index_extreme_events.md`
- 문서 지도 `docs/INDEX.md`와 부패 검사 `tests/test_index.py`
- **`poetry install` 완료** — 프로젝트 내부 `.venv` 사용
- **`src/verify_lab/common_constants.py`** — 경로 상수와 시세 스키마 컬럼 상수
- **`src/verify_lab/utils/` 4종** — 옛 패키지명 참조 정리 완료, 전부 정상 로드
- **`src/verify_lab/data/loader.py`** — 모든 시세 로딩의 단일 통로.
  스키마·정렬·중복·이상치를 검사하고 **보간 없이 즉시 예외**를 던진다.
  이상치 판정 함수는 수집기도 같이 쓴다(판정식 단일화)
- **`src/verify_lab/data/yfinance_collector.py` + `scripts/data/collect_yfinance.py`** — 미국 종목 수집 경로.
  수정주가·오류 전파 인자를 **명시적으로** 넘기고, 검증을 통과한 데이터만 저장한다
- **QQQ 데이터 확보 완료** — 자체 수집기로 재수집했고, 이관본과 가격 기준이 같음을 대조로 확인했다
- 테스트와 품질 게이트 — `validate_project.py`가 `failed=0 skipped=0`으로 통과하는 상태

**안 되어 있는 것**

- **KRX 자격증명 로더** — `.env`는 있으나 이를 환경 변수로 올리는 코드가 없다 (아래 "다음 작업" 참고)
- pykrx 수집기와 실측 — KODEX 200 데이터가 아직 없다
- `measure/`·`report/`·`studies/` 폴더가 비어 있음

## 다음 작업

`docs/ROADMAP.md` Phase 1의 남은 항목이다. **계획서를 먼저 쓴다** (`/plan` 스킬).

| 후보 | 선행 조건 | 비고 |
| --- | --- | --- |
| **자격증명 로더 + pykrx ETF 실측 스크립트** | 없음 | 한 묶음으로 진행할 것. 로더만 만들면 호출처가 0건이라 실제 로그인 여부를 확인할 수 없다. KRX 계정은 준비됐고, 아래 주의사항을 먼저 읽을 것 |
| KODEX 200 수집기 | 위 실측 결과 | 실측 없이는 설계 불가. **착수하지 말 것** |
| Phase 2 공통 계층 | 없음 | QQQ 데이터가 확보돼 미국 쪽만으로도 착수 가능하다. 다만 국내 데이터가 늦게 들어오면 스키마 정규화를 나중에 끼워 넣어야 한다 |

새 수집기를 만들 때는 `docs/ROADMAP.md` Phase 1의 **"확정된 원시 시세 저장 규칙"** 을 따른다.
파일명·수집 범위·최근 구간 제외·저장 시점이 계층 간 계약으로 고정돼 있다.

**KRX 계정은 준비됐다.** `.env`에 `KRX_ID`·`KRX_PW`가 있고 git에서 제외돼 있다.

**단, `.env`가 있다고 pykrx가 바로 동작하지는 않는다.** pykrx는 환경 변수만 읽고 `.env` 파일은
읽지 않으며, `python-dotenv`도 설치돼 있지 않다. pykrx를 쓰려면 먼저
**`python-dotenv` 의존성 추가 + `.env`를 환경 변수로 올리는 로더**가 필요하고,
그 로더는 **`pykrx` import보다 먼저** 호출해야 한다.
확인한 근거와 구현 요건은 `docs/spec/index_extreme_events.md` §8에 정리돼 있다.
`reference/pykrx_collect/krx_credentials.py`가 참고 구현이다.

## 반드시 지킬 것

- **모든 코드 변경 전에 계획서를 쓴다.** 예외는 오타·주석·로그 메시지 수정뿐이다
- **`scripts/data/`(데이터 수집)는 내가 직접 실행한다.** 너는 코드만 쓰고 실행 방법을 안내한다.
  `scripts/studies/`(검증 실행)와 `validate_project.py`는 네가 직접 실행해도 된다
- **공통 계층을 미리 일반화하지 않는다.** 두 번째 검증에서 재사용되는지 확인한 뒤 확정한다
- **`reference/`는 읽기 전용이다.** 읽고 이해한 뒤 `src/verify_lab/`에 새로 작성한다
- 설명은 초보자도 이해할 수 있는 쉬운 한국어로. 전문 통계 용어 대신 구체적인 날짜·가격·표를 쓴다

## 실행 환경 주의

품질 검증이 **세 항목 모두 실패**하면서 `Command not found`가 보이면 코드 문제가 아니다.
`poetry env info --path`가 프로젝트 `.venv`를 가리키는지 먼저 확인한다.
증상·원인·대처는 `docs/ROADMAP.md` Phase 0의 실측 기록에 있다.
