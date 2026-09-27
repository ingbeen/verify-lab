# reference — 참고용 원본 문서와 테스트 예시

이 폴더는 **읽기 전용 참고 자료**입니다. 이전 프로젝트에서 옮겨 둔 문서와 테스트 예시로,
이미 겪은 원칙과 함정을 verify-lab 에서 다시 겪지 않기 위한 자료입니다.

## 이 폴더의 규칙

**읽기 전용입니다** — 수정·import·실행·복사 금지와 그 이유는 `.claude/rules/reference.md` 가 SoT 이며,
이 폴더의 파일을 `Read` 도구로 열면 함께 로드됩니다.

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

각 자료는 **인용하는 곳이 사라지면 역할이 끝납니다** — 인용처는 파일 이름으로 grep 해 확인합니다.
**`데이터처리_설계원칙.md` 와 `test_examples/conftest_example.py` 는 이 README 와 INDEX 말고 인용하는 곳이
없습니다.** 지울 때는 [docs/INDEX.md](../docs/INDEX.md) 등록도 함께 지웁니다. 지운다고 프로젝트가 깨지지 않습니다.
