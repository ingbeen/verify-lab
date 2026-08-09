# 새 세션 시작 프롬프트

> 이 파일은 verify-lab 작업을 처음 시작하는 세션에 붙여넣을 프롬프트입니다.
> Phase 0이 끝나면 삭제해도 됩니다.

---

verify-lab 프로젝트를 시작한다. 이 프로젝트는 다른 세션에서 설계를 확정하고 틀과 문서만 잡아둔 상태다.
**패키지 소스 구현은 아직 하나도 되어 있지 않다.**

## 먼저 읽을 것 (순서대로, 전부)

1. `CLAUDE.md` — 프로젝트 규칙. 특히 "이 프로젝트가 무엇인가"와 "측정의 원칙" 8개 항목
2. **`docs/context/README.md`와 그 폴더의 두 문서** — 내 현재 투자 상태이자 이 프로젝트가 시작된 이유.
   가장 중요한 문서다. 검증 결과를 해석할 때 이 맥락이 없으면 쓸모없는 보고가 된다
3. `docs/ROADMAP.md` — 검증 대상 목록과 Phase 진행 상태
4. `docs/spec/index_extreme_events.md` — 첫 검증의 확정 설계. **이미 논의로 확정된 내용이므로
   설계를 다시 제안하지 말 것.** 특히 §7 "확정된 설계 결정"과 §8 "사전 실측 기록"
5. `src/verify_lab/CLAUDE.md` — 계층 분리, 상수 관리, **측정 계층의 절대 원칙 5가지**
6. `.claude/rules/python.md` — 코딩 표준. `.py` 파일을 읽으면 자동 주입되지만,
   **기존 파일을 열지 않고 새 파일부터 만들 때는 주입되지 않으니 직접 열 것**
7. `scripts/CLAUDE.md`, `tests/CLAUDE.md`, `docs/research/CLAUDE.md`

나머지 문서와 `reference/`의 참고 자료 28개가 어디 있는지는 `docs/INDEX.md`에 지도로 정리돼 있다.
필요할 때 INDEX를 보고 찾아 읽으면 된다. **문서를 추가하면 INDEX에 등록해야 한다** —
`tests/test_index.py`가 검사하므로 빠뜨리면 `validate_project.py`가 실패한다.

## 현재 상태

**되어 있는 것**

- 폴더 구조, 설정 파일(pyproject·pyrightconfig·pytest.ini·.gitignore·poetry.toml)
- 하네스 — `.claude/hooks/`(계획서 게이트), `.claude/rules/`(경로별 자동 주입), `.claude/skills/plan/`
- 규칙 문서 — 루트 `CLAUDE.md`, 계층별 `CLAUDE.md`(`src/verify_lab/`·`scripts/`·`tests/`·`docs/research/`)
- 설계·맥락 문서 — `docs/context/`, `docs/ROADMAP.md`, `docs/spec/index_extreme_events.md`, `docs/COMMANDS.md`(골격)
- 문서 지도 `docs/INDEX.md`와 부패 검사 `tests/test_index.py`
- `validate_project.py`

**안 되어 있는 것**

- `src/verify_lab/utils/` 4개 파일이 **이전 프로젝트에서 복사만 된 상태**다.
  내부에 옛 패키지명(`krx_sprint`) 참조가 남아 있고, `meta_manager.py`가 import하는
  `common_constants.py`가 아직 없어 그대로는 동작하지 않는다
- `common_constants.py` 없음
- `data/`·`measure/`·`report/`·`studies/` 폴더가 비어 있음
- 테스트는 `tests/test_index.py` 하나뿐. **이 프로젝트 환경에서 실행 검증된 적이 없다**
  (작성 세션에서는 외부 환경으로만 통과 확인)
- `poetry install` 미실행

## 첫 작업 — Phase 0 마무리

계획서를 먼저 쓴다 (`/plan` 스킬). 그 다음 아래를 수행한다.

1. `utils/` 4개 파일의 패키지명 참조 정리 → 검증: import 에러 없이 로드된다
2. `common_constants.py` 신설 — 경로 상수(storage 하위 구조), 공통 컬럼명 상수
   → 검증: `utils/meta_manager.py`가 정상 import된다
3. 유틸 스모크 테스트 작성 → 검증: `validate_project.py`가 `failed=0 skipped=0`으로 통과
4. `tests/test_index.py` 실행 검증 → 검증: 6개 통과. 실패하면 `docs/INDEX.md`를 고친다
5. `docs/ROADMAP.md`의 Phase 0 체크리스트 갱신

`poetry install`이 필요하면 나에게 실행을 요청할 것. 설치 명령어는 일회성이므로
`docs/COMMANDS.md`에 기재하지 않는다.

## 반드시 지킬 것

- **모든 코드 변경 전에 계획서를 쓴다.** 예외는 오타·주석·로그 메시지 수정뿐이다
- **`scripts/data/`(데이터 수집)는 내가 직접 실행한다.** 너는 코드만 쓰고 실행 방법을 안내한다.
  `scripts/studies/`(검증 실행)와 `validate_project.py`는 네가 직접 실행해도 된다
- **공통 계층을 미리 일반화하지 않는다.** 두 번째 검증에서 재사용되는지 확인한 뒤 확정한다
- 설명은 초보자도 이해할 수 있는 쉬운 한국어로. 전문 통계 용어 대신 구체적인 날짜·가격·표를 쓴다

## 참고 자료는 저장소 안에 있다

**이 프로젝트는 외부 경로를 참조하지 않는다.** 필요한 참고 자료는 전부 `reference/` 안에 옮겨져 있다.

- `reference/README.md`를 먼저 읽으면 어떤 파일을 언제 보면 되는지 표로 정리돼 있다
- `reference/`는 **읽기 전용**이다. 수정·import·실행하지 않는다. 옛 프로젝트의 모듈을 참조하고 있어
  그대로는 동작하지 않으며, 품질 검사 대상에서도 제외돼 있다
- 필요한 부분은 읽고 이해한 뒤 `src/verify_lab/`에 **새로 작성**한다

지금 단계에서 특히 볼 것:

- `reference/common_constants_qbt.py`, `reference/common_constants_krx.py` — `common_constants.py` 작성 시
- `reference/test_examples/` — look-ahead 감시 테스트와 합성 데이터 픽스처 작성 예시

## 이미 들어와 있는 데이터

`storage/market/QQQ_max.csv` — QQQ 일별 시세(1999-03-10 ~ 2026-07-24, 수정주가 기준).
이전 프로젝트에서 이관한 파일이며, `docs/spec/index_extreme_events.md` §8의 사전 실측이 이 파일로 수행됐다.
Phase 1에서 자체 수집기를 만든 뒤 재수집해 갱신한다. 그전까지는 이 파일로 작업해도 된다.

KODEX 200 데이터는 아직 없다. Phase 1에서 pykrx로 받아야 한다.
