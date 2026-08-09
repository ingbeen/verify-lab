# reference — 참고용 원본 코드와 문서

이 폴더는 **읽기 전용 참고 자료**입니다. 이전 프로젝트에서 검증된 코드와 문서를 옮겨둔 것으로,
verify-lab에서 비슷한 것을 만들 때 바퀴를 다시 발명하지 않기 위한 자료입니다.

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
| `yfinance_downloader.py` | quant `src/qbt/utils/stock_downloader.py` | QQQ 수집기를 만들 때. yfinance 호출 방식, 수정주가 처리, 이상치 검증, 최근 2일 제외 규칙 |
| `pykrx_collect/` | krx-sprint `src/krx_sprint/collect/` | KODEX 200 수집기를 만들 때. pykrx 호출 패턴, 거래일 달력, 재시도·백필, 품질 검증 |
| `pykrx_실측기록.md` | krx-sprint `docs/데이터수집_스펙_v2.md` | **pykrx 실측 전에 반드시 읽을 것.** 어떤 함수가 무엇을 반환하는지, 어떤 함정이 있었는지가 실측으로 기록돼 있습니다 |

> `pykrx_collect/`는 **개별종목 전종목 스냅샷**을 받는 코드입니다. verify-lab이 필요한 것은
> ETF 한 종목의 일별 시세뿐이므로 훨씬 단순합니다. 호출 패턴과 검증 방식만 참고하고,
> 스냅샷·백필 구조를 그대로 가져오지 마세요.

### 측정 계층

| 파일 | 출처 | 언제 보나 |
| --- | --- | --- |
| `event_study.py` | krx-sprint `src/krx_sprint/backtest/event_study.py` | `measure/`를 만들 때. forward return 2기준(종가·익일시가), 초과수익, 구간 절단 처리, 계층별 집계 |
| `test_examples/event_study_test_example.py` | krx-sprint `tests/test_event_study.py` | **look-ahead 감시 테스트와 산식 고정 테스트를 어떻게 쓰는지**의 실제 예시 |
| `test_examples/conftest_example.py` | krx-sprint `tests/conftest.py` | 합성 데이터 픽스처 작성 방식 |
| `test_examples/conftest_qbt_example.py` | quant `tests/qbt/conftest.py` | **파일 격리 픽스처**(`mock_storage_paths`) 작성 방식. import 시점에 경로 상수를 캡처한 모듈까지 함께 패치하는 방법 |

### 결과 문서

| 파일 | 출처 | 언제 보나 |
| --- | --- | --- |
| `analysis_script_example.py` | quant `docs/research/late_entry_rally_opportunities.py` | 검증 스크립트의 크기와 형태. 규칙 정의를 docstring에 명시하고 표로 출력하는 방식 |

> 결과 문서의 **실물 예시는 `docs/context/`의 두 문서**입니다. 그 둘은 참고 자료가 아니라
> 사용자의 현재 운용 상태를 담은 살아있는 문서이므로 이 폴더가 아니라 `docs/`에 있습니다.

### 통계 해석과 과최적화 방어 (이 프로젝트의 핵심 주제)

| 파일 | 출처 | 언제 보나 |
| --- | --- | --- |
| `과최적화_검증_노하우.md` | quant `docs/strategy_validation_report.md` | **결과를 해석하기 전에 읽을 것.** 과최적화의 원리, PBO/DSR, "진짜 N" 문제, **거래 수와 통계적 검정력**(§7), **"이미 답을 본" 오염 문제**(§10). verify-lab이 매번 부딪히는 문제들이 이미 정리돼 있습니다 |
| `데이터처리_설계원칙.md` | krx-sprint `docs/백테스트_설계_v1.md` | 데이터 계층 설계 시. **§1.3 절대 원칙**(look-ahead 금지·보간 금지·생존편향 차단), §3 처리 규칙, §2.6 판정식 단일화 |

### 상수·유틸 구현

| 파일 | 출처 | 언제 보나 |
| --- | --- | --- |
| `common_constants_qbt.py` | quant `src/qbt/common_constants.py` | `common_constants.py`를 만들 때 |
| `common_constants_krx.py` | krx-sprint `src/krx_sprint/common_constants.py` | 같은 용도. 상수 접두사(`COL_`·`KEY_`·`DISPLAY_`·`DEFAULT_`) 사용 예 |
| `data_loader_qbt.py` | quant `src/qbt/utils/data_loader.py` | `data/` 계층을 만들 때. CSV 로딩 중앙집중 패턴(존재 확인→컬럼 검증→날짜 파싱→정렬→중복 제거), 두 DataFrame의 겹치는 기간 추출 |
| `parallel_executor_qbt.py` | quant `src/qbt/utils/parallel_executor.py` | 병렬 처리가 실제로 필요해졌을 때만. 무작위 1,000회 반복 정도는 numpy 벡터화로 충분하므로 **먼저 벡터화를 시도**합니다 |

## 언제 지우나

각 자료는 **대응하는 verify-lab 코드가 완성되고 나면 참고 가치가 사라집니다.**
Phase가 끝날 때마다 더 이상 볼 일 없는 파일을 정리해도 됩니다. 지운다고 프로젝트가 깨지지 않습니다.
