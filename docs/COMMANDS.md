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

> **`failed=0 skipped=0` 이 통과 기준입니다.** 이 둘만 보면 됩니다.
>
> **`passed` 의 절대값을 기준선으로 삼지 않습니다.** 코드를 지우면 테스트도 함께 줄어드는 것이 정상인데,
> 숫자를 문서에 박아 두면 **정상 상태가 고장으로 읽힙니다** — 실제로 그런 적이 있습니다.
> 2026-08-26 에 `passed=1034` 를 기준선으로 적었는데, 그리드 트랙을 삭제하며 테스트 7,910줄이 빠져
> 2026-08-30 에는 567개가 됐습니다. 그 넉 달 사이 이 문서를 믿은 사람은 **깨지지도 않은 것의 원인을 찾게 됩니다.**
>
> 판단이 필요하면 **직전 실행과 비교**하세요. 지운 코드 없이 `passed` 가 줄었다면 그때가 신호입니다.

---

## 데이터 수집

> **AI 모델도 직접 실행합니다.** 다만 외부 서버(Yahoo Finance, KRX, ECOS, FRED)에 실제 요청을
> 보내므로 같은 데이터를 이유 없이 다시 받지 않으며, `storage/market/` 을 덮어쓴 경우
> 새 데이터 기준일을 해당 결과 문서에 남깁니다 (루트 [CLAUDE.md](../CLAUDE.md) "스크립트 실행 규칙").

### yfinance (미국 종목)

```bash
# QQQ 전 기간 수집 (기본값) — 원본가
poetry run python scripts/data/collect_yfinance.py

# 다른 종목 수집
poetry run python scripts/data/collect_yfinance.py --ticker SPY
poetry run python scripts/data/collect_yfinance.py --ticker DIA

# 수정주가로 받기 (본검증에는 쓰지 않습니다. 대조·실측용)
poetry run python scripts/data/collect_yfinance.py --adjusted
```

- 전 기간(`period="max"`)을 받아 `storage/market/<종목>_max.csv` 에 저장합니다. 기존 파일은 덮어씁니다
- **기본은 원본가(배당 미조정)입니다.** 사용자가 결과를 차트와 직접 대조하는 것이 전제이고
  보통의 차트는 배당 미포함이기 때문입니다 ([spec/index_extreme_events.md](spec/index_extreme_events.md) "가격 처리").
  `--adjusted` 를 붙이면 수정주가로 받으며 **`storage/market/<종목>_adjusted_max.csv` 에 따로 저장**되므로
  원본가 파일을 덮어쓰지 않습니다 (`pykrx` 쪽과 같은 규칙)
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
- **`data.krx.co.kr` 이 일시적으로 DNS 해석에 실패하는 일이 있습니다.** 코드나 계정 문제가 아니므로
  **잠시 뒤 그대로 재실행**하면 됩니다. 이 증상은 pykrx 를 쓰는 모든 수집·실측 스크립트에 해당합니다

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

#### 분배락 위치 실측 (검증 #7 용)

분배락이 옵션 만기일 근처에 고정돼 있으면 **원본가로 잰 만기 주변 수익률에 한 방향 편향**이 들어갑니다.
원본가와 수정주가의 종가 배율에 생긴 계단을 찾아 분배락일을 뽑고, 만기일 기준 상대 거래일 분포를 냅니다.

```bash
# KODEX 200 (기본값)
poetry run python scripts/data/check_kodex_distribution.py

# 다른 종목
poetry run python scripts/data/check_kodex_distribution.py --ticker 069500
```

- **외부 서버에 요청하지 않습니다.** `<종목>_max.csv`(원본가)와 `<종목>_adjusted_max.csv`(수정주가)를
  읽으므로 두 파일이 모두 있어야 합니다
- 판정 기준: **만기 창 안 분배락이 0건**이면 원본가로 재도 만기 측정에 편향이 없습니다.
  실측 결과와 해석은 [spec/option_expiry.md](spec/option_expiry.md) §7.5 에 있습니다

#### 만기 매매 보유 구간의 배당락 실측 (검증 #7 대상 8칸)

위 스크립트가 **만기 창 전체**를 보는 것과 달리, 이쪽은 **「만기일 매수 → 다음주 금요일 매도」의
보유 구간에만** 배당락이 들어가는지 봅니다. 같은 진입·청산 날짜로 원본가와 수정주가의 수익률을
각각 계산해 빼므로 **임계값을 정할 필요가 없습니다.**

```bash
poetry run python scripts/data/check_expiry_dividend.py
```

- **외부 서버에 요청하지 않습니다.** 원본가와 수정주가 파일이 종목마다 둘 다 있어야 합니다
- 「아래」 칸에서 차이가 **양수면 원본가 성적이 그만큼 과대평가**돼 있습니다 —
  원본가에서 보이는 그 하락은 배당락이 만든 것이라 인버스로도 공매도로도 못 먹습니다
- 실측 결과는 [research/옵션_만기일.md](research/옵션_만기일.md) §3.2.1 에 있습니다.
  **QQQ 만 걸립니다** — 9월 8건(과대평가) · 12월 10건(과소평가). 나머지 미국 칸은 0건

#### KODEX 200 수집

```bash
# ETF 의 NAV 를 단일 값 시계열로 수집 (프리미엄/디스카운트 측정용)
poetry run python scripts/data/collect_pykrx.py --ticker 261240 --start 20161227 --nav
```

```bash
# KODEX 200 전 기간 수집 (기본값)
poetry run python scripts/data/collect_pykrx.py

# 다른 종목·다른 상장일로 수집
poetry run python scripts/data/collect_pykrx.py --ticker 069500 --start 20021014
```

```bash
# 미국달러선물 ETF — 원달러 그리드용 (수정 종가가 본검증 기준)
poetry run python scripts/data/collect_pykrx.py --ticker 261240 --start 20161227 --adjusted
poetry run python scripts/data/collect_pykrx.py --ticker 261250 --start 20161227 --adjusted
```

- **기본은 원본가입니다.** 기존 파일은 덮어씁니다
  - `storage/market/<종목>_max.csv` — **원본가**, 상장일부터 전 기간
  - `storage/market/<종목>_adjusted_max.csv` — **수정주가** (`--adjusted`). 파일명이 달라 원본가를 덮어쓰지 않습니다
- 검증 #1 이 원본가를 쓰는 근거는 [spec/index_extreme_events.md](spec/index_extreme_events.md) "가격 처리" 에 있습니다.
  원달러 그리드가 수정 종가를 쓰는 근거는 [spec/usdkrw_grid.md](spec/usdkrw_grid.md) §2 에 있습니다
- **확정되지 않은 당일은 저장하지 않습니다.** 장중에도 당일 행이 반환되기 때문이며,
  제외된 행 수는 실행 결과 표의 "최근 제외"에 표시됩니다
- 이상치가 발견되면 **파일을 만들지 않고 예외로 중단**합니다

### ETN (국내 상장지수증권 — 검증 #8 용)

**KRX 데이터포털 계정이 필요합니다.** pykrx 와 같은 `.env` 설정을 씁니다.

```bash
# 삼성 인버스 2X 코스닥150 선물 ETN (기본값) — 시세
poetry run python scripts/data/collect_etn.py

# 다른 종목·다른 상장일로 수집
poetry run python scripts/data/collect_etn.py --ticker 520057 --start 20221017

# 증권당 지표가치 (ETF 의 NAV 에 해당) — `storage/series/<종목>_IV.csv` 로 저장
poetry run python scripts/data/collect_etn.py --ticker 530107 --start 20221017 --indicative-value
```

- **pykrx 는 ETN 에 시세 함수를 주지 않습니다.** `get_etn_ticker_list`·`get_etn_ticker_name` 둘뿐이고
  ETF·주식용 조회에 ETN 코드를 넣으면 **예외 없이 빈 결과**가 돌아옵니다. 이 수집기는 pykrx 의 KRX
  클라이언트만 재사용해 **`MDCSTAT06601`(ETN 개별종목 시세 추이)** 를 직접 부릅니다.
  근거와 통계 코드 표는 [spec/leverage_tracking.md](spec/leverage_tracking.md) §6.1 에 있습니다
- **ETN 은 가격 기준이 하나뿐입니다** — 분배금을 지급하지 않으므로 `--adjusted` 에 해당하는 인자가 없습니다
- **조회는 티커가 아니라 ISIN 으로 나갑니다.** 변환표는 KRX 기본종목 조회가 주며 수집기가 알아서 처리합니다
- **수집 시작일은 기억이 아니라 `LIST_DD` 로 확인하세요.** 실제로 251340 을 상장일보다 늦게 요청해
  11거래일을 빠뜨린 적이 있습니다
- ⚠️ pykrx 는 로그인 시 **로그인 ID 를 표준 출력에 찍습니다.** 로그를 공유할 때 그 줄을 빼세요

### ECOS (한국은행 — 환율·원화금리)

**ECOS 인증키가 필요합니다.** 저장소 루트의 `.env` 에 `ECOS_API_KEY` 가 있어야 하며,
[ecos.bok.or.kr](https://ecos.bok.or.kr) 에서 무료로 발급합니다.

```bash
# 통계표·항목 코드 실측 (코드를 쓰기 전에 먼저 확인)
poetry run python scripts/data/check_ecos.py

# 다른 키워드나 다른 통계표로 실측
poetry run python scripts/data/check_ecos.py --keyword 환율 국제수지 --stat 731Y001

# 환율 2종 + CD 91일물 수집 (기본값: 전부, 가용 전 기간)
poetry run python scripts/data/collect_ecos.py

# 하나만, 또는 구간을 좁혀서
poetry run python scripts/data/collect_ecos.py --series usdkrw_close --start 19980101 --end 20261231
```

- 프로브는 원자료를 `storage/results/<실행시각>_ecos_probe/` 에 남깁니다.
  **통계표코드·항목코드는 기억이 아니라 이 프로브로 확인**하며, 확정값은
  [spec/usdkrw_grid.md](spec/usdkrw_grid.md) §3.1 에 있습니다
- **환율은 두 계열을 받습니다.** `usdkrw_close`(종가 15:30)가 수익률 측정의 기준이고,
  `usdkrw`(매매기준율)는 환전 스프레드의 기준입니다. 매매기준율은 전영업일 가중평균이라 하루 늦고
  스무딩돼 있어 수익률 측정에 쓸 수 없습니다 ([spec/usdkrw_grid.md](spec/usdkrw_grid.md) §3.4)
- 수집 결과는 `storage/series/<이름>.csv` 에 `Date,Value` 스키마로 저장됩니다. 기존 파일은 덮어씁니다
- **기간을 잘라 저장하지 않습니다.** 기본 시작일이 두 시계열의 실제 시작보다 이른 이유입니다
- ⚠️ **ECOS 는 인증키를 URL 경로에 넣습니다.** 실행 로그의 요청 URL 은 키가 마스킹된 형태로 나오지만,
  직접 URL 을 만들어 호출한 결과를 문서에 붙일 때는 키를 지우세요

### FRED (미국 — 달러금리)

**인증키가 필요 없습니다.** 공개 CSV 엔드포인트를 씁니다.

```bash
# 미국 3개월 T-bill (DTB3) 수집
poetry run python scripts/data/collect_fred.py
```

- `storage/series/DTB3.csv` 에 저장합니다. 기존 파일은 덮어씁니다
- **미국 시장 휴일은 행이 있고 값만 비어 있습니다.** 수집기는 그 행을 제외하고 제외 건수를 보고하며,
  전일값 이월은 하지 않습니다 — 이월은 측정 계층의 판단입니다
  ([spec/usdkrw_grid.md](spec/usdkrw_grid.md) §3.2)

---

## 검증 실행

> AI 모델이 직접 실행할 수 있습니다. 파라미터를 바꿔가며 반복 실행하는 것이 검증의 본질입니다.

### 검증 #1 — 지수 극단 이벤트

```bash
# 전 조합 실행 (기본값) — 검증 대상 시세를 한 번에
poetry run python scripts/studies/run_index_extreme.py

# 특정 시세만
poetry run python scripts/studies/run_index_extreme.py --dataset qqq

# 순열 검정 설정을 바꿔 재현성 확인
poetry run python scripts/studies/run_index_extreme.py --repeats 5000 --seed 42
```

- **강건성 조합을 한 실행에서 전부 산출합니다.** 신호군은 파라미터 × 시작연도 × 방향 ×
  시대 구간 × 데이터셋의 곱이며, 각 축의 값은 `docs/spec/index_extreme_events.md` 와
  `studies/index_extreme/constants.py` 가 정합니다. **실제 개수와 실행 시간은 실행 결과의
  마지막 줄과 `summary.json` 에 나옵니다**
- **데이터셋끼리 나란히 놓고 보려면 같은 실행에서 계산해야 합니다.** 대조의 전제가
  "파라미터가 같았다"이고, 따로 돌리면 그 사실을 사람이 확인해야 합니다
- `--dataset` 이 고를 수 있는 값은 `--help` 로 확인합니다. 목록의 SoT 는
  `studies/index_extreme/constants.py` 의 `DATASETS` 입니다
- **방향 축에는 폭등·폭락 외에 `역방향 전체` 가 있습니다.** 두 방향을 한
  표본으로 묶되 상승 방향 신호의 수익률에 −1 을 곱해 역방향 진입 기준으로 부호를 맞춘 신호군이며,
  집계 3파일에만 나옵니다 (`signals.csv` 에는 없습니다). 근거는 스펙 §7 결정 ㉕ 입니다
- 산출물은 `storage/results/<실행시각>_index_extreme/` 에 CSV 4개(`signals`·`statistics`·`excess`·`test`)와
  `summary.json` 으로 남습니다. 덮어쓰지 않고 실행 시각으로 쌓입니다
- **순위 컷·집계 시작연도는 인자가 아닙니다.** 스펙이 확정한 목록을 전부 산출해 나란히
  보고하는 것이 이 검증의 설계이며, 값을 골라 넣는 노브로 쓰면 과최적화입니다

### 검증 #7 — 옵션 만기일

```bash
# 전 조합 실행 (기본값) — 종목 4개(원본가) × 만기월 1~12
# 「만기일 매수 → 다음주 금요일 매도」 매매를 재고 만기월별로 후보 판정한다
poetry run python scripts/studies/run_option_expiry.py

# 종목 하나만 (qqq · spy · dia · kodex200)
poetry run python scripts/studies/run_option_expiry.py --dataset kodex200

# 순열 검정 반복 수를 줄여 빠르게 확인
poetry run python scripts/studies/run_option_expiry.py --repeats 200
```

- **산출물은 9개 CSV 이고, 가장 먼저 볼 것은 `candidates.csv`** 입니다 — 전 칸의 1차 판정과
  등급이 들어 있습니다. 화면에도 실행 직후 그 표가 먼저 나옵니다
- **화면에는 1차 게이트를 넘은 칸만, `candidates.csv` 에는 전 칸이** 남습니다.
  화면은 적중률 내림차순이고 CSV 는 만기월 순서입니다 — **제외된 칸도 값이 그대로 있습니다**
- 판정 규격(게이트 둘 + 등급 셋)의 SoT 는 루트 [CLAUDE.md](../CLAUDE.md) 「후보 판정 기준」이고,
  구현은 `src/verify_lab/measure/screening.py` 입니다

- 선행 조건: `storage/market/` 에 **원본가 4개 파일**(QQQ·SPY·DIA·069500)이 있어야 합니다
- **하나의 만기월을 고르지 않습니다.** 12달을 전부 산출해 나란히 보고하고,
  한국은 **금요일·목요일 청산 두 벌**을 냅니다
- 산출물은 `storage/results/<실행시각>_option_expiry/` 에 9개 CSV 와 `summary.json` 으로 남습니다.
  **CSV 컬럼 헤더는 한글**이고 비율은 백분율로 저장됩니다.
  신호일 원자료는 `signals.csv`(만기 창 거래일)와 `weekly_trade_signals.csv`(매매)이며 차트 대조용입니다
- 결과와 판정은 [research/옵션_만기일.md](research/옵션_만기일.md), 확정 설계는
  [spec/option_expiry.md](spec/option_expiry.md) 입니다

### 검증 #8 — 레버리지 ETF 괴리

```bash
# 전 조합 실행 (기본값) — 22쌍 × 보유 기간 7격자 × 축 3종
poetry run python scripts/studies/run_leverage_tracking.py

# 특정 지수만 (KOSDAQ150 · KOSPI200 · S&P500 · 나스닥100 · 다우)
poetry run python scripts/studies/run_leverage_tracking.py --index 나스닥100
```

- **보유 기간·임계값은 인자가 아닙니다.** 확정된 격자를 전부 산출해 나란히 보고하는 것이 설계이며,
  값을 골라 넣는 노브로 쓰면 과최적화입니다. 값의 SoT 는
  `src/verify_lab/studies/leverage_tracking/constants.py` 입니다
- 선행 조건: `storage/market/` 에 **원본가 27종**과 **수정주가 25종**(ETN 2종 제외)이 있어야 합니다
- 산출물은 `storage/results/<실행시각>_leverage_tracking/` 에 남습니다
  - `divergence.csv` — 쌍 × 구간 집계. **가장 먼저 볼 표입니다**
  - `breakdown.csv` — 쌍 × 구간 × 축(변동성·방향·시기)
  - `distribution.csv` — 분배금 몫과 **배당 보정분**. 원본가로 재서 생긴 왜곡의 크기입니다
  - `full_period.csv` — 상장 후 전체 구간 1건씩. **표본 1건이라 통계가 아니라 사례입니다**
  - `windows_<티커>.csv` — 시작일 원자료 22개. 차트 대조용이며 합계 약 66MB 입니다
- **순열 검정이 없어 난수를 쓰지 않습니다.** 같은 데이터면 항상 같은 결과가 나옵니다. 실행 시간은 수 초입니다
- **3년 칸은 비중첩 표본이 1~6개**라 통계가 아니라 사례에 가깝습니다.
  결과와 판정은 [research/레버리지_ETF_괴리.md](research/레버리지_ETF_괴리.md), 확정 설계는
  [spec/leverage_tracking.md](spec/leverage_tracking.md) 입니다

### 검증 #5 — 원달러 ETF 등가성

```bash
# 전 조합 실행 (기본값) — 환율 계열 2종 × 이론값 2종 × 이상치 포함·제외
poetry run python scripts/studies/run_usdkrw_equivalence.py

# 이론값 모형을 하나만
poetry run python scripts/studies/run_usdkrw_equivalence.py --model usd_rate
```

- **이상치 축은 인자가 아닙니다.** 2019-03-14 의 종가 이상치 포함·제외를 나란히 보는 것이 설계이며,
  하나만 골라 산출하면 그 선택이 결론에 섞입니다
- 산출물은 `storage/results/<실행시각>_usdkrw_equivalence/` 에 CSV 6개(`equivalence`·`annual_drift`·
  `leverage`·`premium`·`effective_cost`·`daily`)와 `summary.json` 으로 남습니다
- `effective_cost.csv` 는 **NAV 로 직접 잰 실효 총비용**입니다. 공시 총보수와 나란히 실립니다
- `daily.csv` 는 **손으로 검산하는 원자료**입니다. 현물 변화와 이자 기여분을 따로 담아
  이론값이 어떻게 만들어졌는지 그대로 따라갈 수 있습니다
- 결과와 판정은 [research/원달러_ETF_등가성.md](research/원달러_ETF_등가성.md) 에 있습니다

---

## 매매 규칙 실행

> AI 모델이 직접 실행할 수 있습니다.
> **이것은 측정이 아니라 측정 결과로부터 도출한 매매 규칙**이며, 규칙과 확정 근거는
> [strategy/역방향_매매_규칙.md](strategy/역방향_매매_규칙.md) 가 SoT입니다.

### 원달러 그리드 — 코드 삭제됨 (2026-08-30)

**실행할 스크립트가 없다.** 그리드는 채택되지 않았고 구현을 지웠다.
규칙과 성적은 [strategy/원달러_그리드.md](strategy/원달러_그리드.md), 확정 설계는
[spec/usdkrw_grid.md](spec/usdkrw_grid.md), 기각 근거는 [ROADMAP.md](ROADMAP.md) 「G5 이후 — 트랙 종료」에 있다.

### 역방향 매매 규칙

```bash
# 전 조합 실행 (기본값) — 대상 전부 × 보유 한도 전부
poetry run python scripts/strategy/run_reverse_trading.py

# 특정 종목만
poetry run python scripts/strategy/run_reverse_trading.py --target qqq
```

- **손절선·보유 한도·대상 목록은 인자가 아닙니다.** 확정된 규칙을 그대로 적용하는 것이 설계이며,
  값을 골라 넣는 노브로 쓰면 표본에 맞춘 튜닝이 됩니다. 값의 SoT 는
  `src/verify_lab/strategy/constants.py` 이고 근거는 규칙 문서 §3 입니다
- **손절선은 -5% 하나, 보유 한도는 D+2 하나입니다** (2026-08-30 개정). 그전에는 손절 3분할과
  한도 3종을 나란히 냈는데, 실측에서 -4%~-10% 가 평평해 분할의 존재 이유가 사라졌습니다
- 산출물은 `storage/results/<실행시각>_reverse_trading/` 에 `trades.csv`(체결 내역),
  `summary_by_target.csv`(대상별 집계), `summary.json` 으로 남습니다
- `trades.csv` 는 **신호 하나가 한 행**입니다
- **대상은 4종입니다** — KODEX 200 K=10·K=20, QQQ K=10·K=20, **전부 시작연도 2005**.
  `--target kodex200` 처럼 종목으로 고르면 그 종목의 **두 컷이 함께** 돌아갑니다
  (인자는 종목 단위라 순위 컷을 따로 못 고릅니다)
- **백테스트 구간은 2005 하나로 통일돼 있습니다.** 성적이 아니라 표본 근거로 고른 값이며
  근거는 규칙 문서 §3.3 입니다. **QQQ 는 2005·2008 의 신호 집합이 완전히 같아** 통일해도 성적이 같습니다
- **KODEX 200 K=20 은 확정 규칙이 아니라 비교축입니다.** 확정 대상은 규칙 문서 §1.1 이 정하며,
  K=20 을 함께 내는 것은 두 컷을 나란히 놓고 판단하기 위해서입니다
- 실행 시간은 순열 검정이 없어 **수 초**입니다

### 옵션 만기일 매매 — 손절 격자

**아직 확정된 규칙이 아닙니다.** 손절선을 고르기 위한 재료를 내는 스크립트이며,
값 선택은 격자를 본 사용자가 합니다 (루트 `CLAUDE.md` 측정의 원칙 1).

```bash
# 확정 규칙 (기본값) — 손절 -5%
poetry run python scripts/strategy/run_expiry_trading.py

# 특정 종목만
poetry run python scripts/strategy/run_expiry_trading.py --ticker qqq

# 손절선 격자 — 손절선을 다시 고를 때만
poetry run python scripts/strategy/run_expiry_trading.py --grid
```

- **손절선 값은 인자가 아닙니다.** 확정값 **−5%** 를 그대로 적용하며, 값을 골라 넣는
  노브로 쓰면 표본에 맞춘 튜닝이 됩니다. 값의 SoT 는
  `src/verify_lab/strategy/constants.py` 의 `EXPIRY_STOP_LEVEL` 이고
  고른 근거는 `spec/option_expiry.md` 결정 ㊴ 입니다
- **기본 산출물에는 `손절선(%)` 컬럼이 없습니다** — 전 행이 같은 값이라 자리만 차지합니다
- **`--grid` 는 값을 고르는 옵션이 아니라 전부 내는 옵션입니다.** 무손절 + −1.0%~−10.0%
  (0.5%p 간격)를 내며 **시세를 재수집해 「평평한 구간」을 다시 찾아야 할 때** 씁니다
- 대상은 **7칸**이고 SoT 는
  `src/verify_lab/strategy/constants.py` 의 `EXPIRY_CELLS` 입니다
- **등급이 낮은 칸도 빼지 않습니다.** QQQ 12월은 등급 0/3 이지만 게이트를 넘었으므로 함께 냅니다 —
  등급으로 빼면 60칸에서 통계량 좋은 칸만 고르는 사후 선택이 됩니다 (`spec/option_expiry.md` 결정 ㊳)
- **미국 9월 세 칸(QQQ·SPY·DIA)은 같은 날 같은 방향**이라 독립된 세 번의 기회가 아닙니다
- 산출물은 `storage/results/<실행시각>_expiry_trading/` 에 남습니다
  - 기본: `summary_by_cell.csv`(**7칸 × 5구간 = 35행**) · `trades.csv`(체결 199건) · `summary.json`
  - `--grid`: `stop_loss_grid.csv`(7칸 × 20손절선 × 5구간) · `trades.csv` · `summary.json`
- **성적표는 구간별로 나옵니다** — `전체 · 앞 절반 · 뒤 절반 · 최근 10년 · 최근 5년`.
  **표본이 10건 미만인 구간도 행이 남고** `판정가능` 이 `아니오` 로 찍힙니다
  (루트 [CLAUDE.md](../CLAUDE.md) 측정의 원칙 17). **최근 5년은 전 칸이 5건이라 판정에 쓰지 않습니다**
- **「최근 N년」은 데이터 마지막 거래일 기준**입니다. 실행 시각과 무관하므로 같은 데이터면 같은 결과입니다
- **`--grid` 의 무손절 행이 결과 문서 12A.4 의 방향 기대값과 맞는지** 확인하세요.
  안 맞으면 `measure` 와 `strategy` 두 계층 중 하나가 틀린 것입니다
- ⚠️ **CSV 를 Excel 로 열어 저장하지 마세요.** 날짜에서 앞 0 이 지워지고(`2021-09-17` →
  `2021.9.17`) 소수 끝자리가 잘려 재분석·대조가 깨집니다. 값 자체는 안 바뀝니다
- 실행 시간은 순열 검정이 없어 **수 초**입니다
