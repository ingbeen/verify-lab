# verify-lab 실행 명령어 레퍼런스

> 이 파일은 verify-lab 실행 명령어의 **단일 SoT(Source of Truth)** 입니다.
> README.md·CLAUDE.md 등 다른 문서에는 실행 명령어를 기재하지 않으며, 필요 시 이 문서를 참조합니다.
> 설치처럼 한 번만 쓰는 일회성 명령어는 기재하지 않습니다. **평상시 반복 실행하는 명령어만** 관리합니다.

---

## 품질 검증

```bash
# 전체 검증 (Ruff + PyRight + Pytest)
poetry run python validate_project.py

# 개별 실행
poetry run python validate_project.py --only-lint
poetry run python validate_project.py --only-pyright
poetry run python validate_project.py --only-tests

# 커버리지 포함 테스트
poetry run python validate_project.py --cov

# 포맷 자동 적용 (마지막 Phase에서만)
poetry run black .
```

> 검증이 **세 항목 모두 실패**하면서 `Command not found` 가 보이면 코드 문제가 아니라 실행 환경 문제입니다.
> `poetry env info --path` 가 프로젝트의 `.venv` 를 가리키는지 먼저 확인하세요.
> 원인과 대처는 [ROADMAP.md](ROADMAP.md) Phase 0 의 실측 기록에 있습니다.

---

## 데이터 수집

> **사용자만 실행합니다.** 외부 서버(Yahoo Finance, KRX)에 실제 요청을 보내므로
> AI 모델은 이 명령어를 직접 실행하지 않습니다.

### yfinance (미국 종목)

```bash
# QQQ 전 기간 수집 (기본값)
poetry run python scripts/data/collect_yfinance.py

# 다른 종목 수집
poetry run python scripts/data/collect_yfinance.py --ticker SPY
```

- 전 기간(`period="max"`)을 받아 `storage/market/<종목>_max.csv` 에 저장합니다. 기존 파일은 덮어씁니다
- **확정되지 않은 최근 며칠은 저장하지 않습니다.** 제외된 행 수는 실행 결과 표의 "최근 제외"에 표시됩니다
- 이상치가 발견되면 **파일을 만들지 않고 예외로 중단**합니다. 반쪽짜리 파일이 남지 않습니다

### pykrx (국내 종목)

**KRX 데이터포털 계정이 필요합니다.** 저장소 루트의 `.env` 에 `KRX_ID`·`KRX_PW` 가 있어야 하며,
계정이 없으면 pykrx 는 아무것도 조회하지 못합니다.

```bash
# KODEX 200 데이터 성질 실측 (분배금 조정 여부·유동성·괴리율·결측)
poetry run python scripts/data/check_pykrx_etf.py

# 다른 ETF 나 다른 시작일로 실측
poetry run python scripts/data/check_pykrx_etf.py --ticker 069500 --start 20021014
```

- KRX 를 5회 호출하고, **각 결과를 받는 즉시** `storage/results/<실행시각>_pykrx_etf_probe/` 에 CSV 로 남깁니다.
  뒤쪽 호출이 실패해도 앞선 원자료는 보존됩니다
- ⚠️ **pykrx 는 로그인 시 로그인 ID 를 표준 출력에 찍습니다**(비밀번호는 찍지 않습니다).
  실행 로그를 공유하거나 문서에 붙일 때 그 줄을 빼세요

#### 수정주가 구간 이어붙이기 실측

`get_market_ohlcv(adjusted=True)` 는 분배락을 조정하지만 한 번에 3,000행까지만 옵니다.
전 기간을 덮으려면 **종료일만 다르게** 여러 번 호출해 이어붙여야 하며, 그 정합성을 재는 스크립트입니다.

```bash
# 2분할(기본값) — 종료일 2014-12-31 과 실행일
poetry run python scripts/data/check_pykrx_splice.py

# 3분할 — 앞 구간이 상장일까지 닿지 못했을 때 종료일을 늘려 재실행
poetry run python scripts/data/check_pykrx_splice.py --ends 20081231,20141231
```

- 종료일 개수 + 1회(기준 조회) 만큼 KRX 를 호출하고, 원자료를
  `storage/results/<실행시각>_pykrx_splice_probe/` 에 CSV 로 남깁니다
- 판정 기준: **겹치는 구간의 값 불일치가 0건**이면 이어붙이기가 성립합니다.
  "덮지 못한 거래일"이 남으면 `--ends` 에 더 이른 종료일을 추가해 재실행합니다
- **모든 호출이 한 번의 실행 안에 있어야 합니다.** 수정계수는 조회 종료일이 아니라 조회 **시점** 기준이라,
  다른 날 받은 결과끼리 비교하면 판정이 성립하지 않습니다

#### KODEX 200 수집

```bash
# KODEX 200 전 기간 수집 (기본값)
poetry run python scripts/data/collect_pykrx.py

# 다른 종목·다른 상장일로 수집
poetry run python scripts/data/collect_pykrx.py --ticker 069500 --start 20021014
```

- **한 번 실행으로 가격 기준 두 개를 받습니다.** 기존 파일은 덮어씁니다
  - `storage/market/<종목>_max.csv` — **원본가**, 상장일부터 전 기간 (본검증)
  - `storage/market/<종목>_adjusted_max.csv` — **수정주가**, KRX 가 주는 최근 3,000거래일 (대조)
- 수정주가 파일이 상장일보다 늦게 시작하는 것은 **정상**입니다. KRX 가 그만큼만 제공합니다
  ([spec/index_extreme_events.md](spec/index_extreme_events.md) §8 결론 4)
- **확정되지 않은 당일은 저장하지 않습니다.** 장중에도 당일 행이 반환되기 때문이며,
  제외된 행 수는 실행 결과 표의 "최근 제외"에 표시됩니다
- 이상치가 발견되면 **파일을 만들지 않고 예외로 중단**합니다

---

## 검증 실행

> AI 모델이 직접 실행할 수 있습니다. 파라미터를 바꿔가며 반복 실행하는 것이 검증의 본질입니다.

### 검증 #1 — 지수 극단 이벤트

```bash
# 전 조합 실행 (기본값) — QQQ 와 KODEX 200 두 가격 기준을 한 번에
poetry run python scripts/studies/run_index_extreme.py

# 특정 시세만
poetry run python scripts/studies/run_index_extreme.py --dataset qqq

# 순열 검정 설정을 바꿔 재현성 확인
poetry run python scripts/studies/run_index_extreme.py --repeats 5000 --seed 42
```

- **강건성 조합을 한 실행에서 전부 산출합니다.** 테스트 A(순위 컷 3 × 시작연도 4 × 방향 2)와
  테스트 B(연속 일수 8 × 시작연도 4 × 방향 2)에 시대 구간 2개를 더해 데이터셋당 132개,
  세 데이터셋 합쳐 **신호군 396개**입니다
- **국내 두 가격 기준을 같은 실행 안에서 계산합니다.** 대조의 전제가 "파라미터가 같았다"이고,
  KRX 수정주가 조회 창이 하루씩 굴러가 다른 날 실행하면 대조 자체가 성립하지 않습니다
- `--dataset` 값은 `qqq` / `kodex200`(원본가, 본검증) / `kodex200_adjusted`(수정주가, 대조)입니다.
  **국내 두 기준을 따로 돌리면 대조가 성립하지 않으므로 함께 돌립니다**
- 산출물은 `storage/results/<실행시각>_index_extreme/` 에 CSV 4개(`signals`·`statistics`·`excess`·`test`)와
  `summary.json` 으로 남습니다. 덮어쓰지 않고 실행 시각으로 쌓입니다
- **순위 컷·연속 일수·집계 시작연도는 인자가 아닙니다.** 스펙이 확정한 목록을 전부 산출해 나란히
  보고하는 것이 이 검증의 설계이며, 값을 골라 넣는 노브로 쓰면 과최적화입니다
- 실행 시간은 전 조합 기준 **약 3분**입니다 (2026-08-14 실측, 반복 1,000회)
