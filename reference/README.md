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

### 결과 문서

| 파일 | 출처 | 언제 보나 |
| --- | --- | --- |
| `research_doc_example_1.md` | quant `docs/research/RESEARCH_qqq_late_entry.md` | 결과 문서를 쓸 때. 결론 요약표 → 근거 → 통계 해석 → **기각된 가설** → 한계 → 재현 방법 구성 |
| `research_doc_example_2.md` | quant `docs/research/RESEARCH_q2_2xs_qqq_correlation.md` | 같은 용도. 특히 **대안 설명을 실험으로 배제하는 방식**(§8)과 재현 코드 첨부 방식 |
| `analysis_script_example.py` | quant `docs/research/late_entry_rally_opportunities.py` | 검증 스크립트의 크기와 형태. 규칙 정의를 docstring에 명시하고 표로 출력하는 방식 |

### 상수 정의

| 파일 | 출처 | 언제 보나 |
| --- | --- | --- |
| `common_constants_qbt.py` | quant `src/qbt/common_constants.py` | `common_constants.py`를 만들 때 |
| `common_constants_krx.py` | krx-sprint `src/krx_sprint/common_constants.py` | 같은 용도. 컬럼명 상수 접두사(`COL_`·`KEY_`) 사용 예 |

## 언제 지우나

각 자료는 **대응하는 verify-lab 코드가 완성되고 나면 참고 가치가 사라집니다.**
Phase가 끝날 때마다 더 이상 볼 일 없는 파일을 정리해도 됩니다. 지운다고 프로젝트가 깨지지 않습니다.
