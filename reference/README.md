# reference — 참고용 원본 문서와 테스트 예시

이 폴더는 **읽기 전용 참고 자료**입니다. 이전 프로젝트에서 옮겨 둔 문서와 테스트 예시로,
이미 겪은 원칙과 함정을 verify-lab 에서 다시 겪지 않기 위한 자료입니다.

## 이 폴더의 규칙

- **수정하지 않습니다.** 원본 그대로 보존합니다
- **import하지 않습니다.** 이 폴더의 코드는 verify-lab 패키지가 아니며, 옛 프로젝트의 모듈을 참조하고 있어
  그대로는 동작하지 않습니다
- **실행하지 않습니다**
- 품질 검사(Ruff·PyRight·pytest) 대상에서 제외돼 있습니다
- 필요한 부분은 **읽고 이해한 뒤 `src/verify_lab/`에 새로 작성**합니다.
  복사해 붙이면 verify-lab에 맞지 않는 전제(국내 개별종목 패널, 포트폴리오 엔진 등)가 따라 들어옵니다
- 이 폴더의 문서에 있는 **링크와 파일 경로는 옛 프로젝트 기준이라 열리지 않습니다.**
  내용을 읽는 용도이며, 링크가 깨져 있어도 정상입니다

## 파일별 용도

### 데이터 수집

| 파일 | 출처 | 언제 보나 |
| --- | --- | --- |
| `pykrx_실측기록.md` | krx-sprint `docs/데이터수집_스펙_v2.md` | **pykrx 실측 전에 반드시 읽을 것.** 어떤 함수가 무엇을 반환하는지, 어떤 함정이 있었는지가 실측으로 기록돼 있습니다 |

### 테스트 작성 예시

| 파일 | 출처 | 언제 보나 |
| --- | --- | --- |
| `test_examples/event_study_test_example.py` | krx-sprint `tests/test_event_study.py` | **look-ahead 감시 테스트와 산식 고정 테스트를 어떻게 쓰는지**의 실제 예시 |
| `test_examples/conftest_example.py` | krx-sprint `tests/conftest.py` | 합성 데이터 픽스처 작성 방식 |
| `test_examples/conftest_qbt_example.py` | quant `tests/qbt/conftest.py` | **파일 격리 픽스처**(`mock_storage_paths`) 작성 방식. import 시점에 경로 상수를 캡처한 모듈까지 함께 패치하는 방법 |

### 통계 해석과 과최적화 방어 (이 프로젝트의 핵심 주제)

| 파일 | 출처 | 언제 보나 |
| --- | --- | --- |
| `과최적화_검증_노하우.md` | quant `docs/strategy_validation_report.md` | **결과를 해석하기 전에 읽을 것.** 과최적화의 원리, PBO/DSR, "진짜 N" 문제, **거래 수와 통계적 검정력**(§7), **"이미 답을 본" 오염 문제**(§10). verify-lab이 매번 부딪히는 문제들이 이미 정리돼 있습니다 |
| `데이터처리_설계원칙.md` | krx-sprint `docs/백테스트_설계_v1.md` | 데이터 계층 설계 시. **§1.3 절대 원칙**(look-ahead 금지·보간 금지·생존편향 차단), §3 처리 규칙, §2.6 판정식 단일화 |

## 언제 지우나

각 자료는 **인용하는 곳이 사라지면 역할이 끝납니다** — 지식 문서는 `.claude/rules/research.md` 와
설계 문서가, 테스트 예시는 `tests/CLAUDE.md` 가 가리킵니다. 지울 때는 [docs/INDEX.md](../docs/INDEX.md)
등록도 함께 지웁니다. 지운다고 프로젝트가 깨지지 않습니다.
