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

> **통과 기준선: `passed=1034 failed=0 skipped=0`** (2026-08-26 · G5 완료 시점).
> 코드를 늘리면 이 수는 늘어납니다. **줄었다면 무언가 깨진 것**이므로 원인을 찾기 전에는 진행하지 않습니다.

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

- **강건성 조합을 한 실행에서 전부 산출합니다.** 신호군은 테스트 × 파라미터 × 시작연도 × 방향 ×
  시대 구간 × 데이터셋의 곱이며, 각 축의 값은 `docs/spec/index_extreme_events.md` 와
  `studies/index_extreme/constants.py` 가 정합니다. **실제 개수와 실행 시간은 실행 결과의
  마지막 줄과 `summary.json` 에 나옵니다**
- **데이터셋끼리 나란히 놓고 보려면 같은 실행에서 계산해야 합니다.** 대조의 전제가
  "파라미터가 같았다"이고, 따로 돌리면 그 사실을 사람이 확인해야 합니다
- `--dataset` 이 고를 수 있는 값은 `--help` 로 확인합니다. 목록의 SoT 는
  `studies/index_extreme/constants.py` 의 `DATASETS` 입니다
- **방향 축에는 폭등·폭락(연속 상승·연속 하락) 외에 `역방향 전체` 가 있습니다.** 두 방향을 한
  표본으로 묶되 상승 방향 신호의 수익률에 −1 을 곱해 역방향 진입 기준으로 부호를 맞춘 신호군이며,
  집계 3파일에만 나옵니다 (`signals.csv` 에는 없습니다). 근거는 스펙 §7 결정 ㉕ 입니다
- 산출물은 `storage/results/<실행시각>_index_extreme/` 에 CSV 4개(`signals`·`statistics`·`excess`·`test`)와
  `summary.json` 으로 남습니다. 덮어쓰지 않고 실행 시각으로 쌓입니다
- **순위 컷·연속 일수·집계 시작연도는 인자가 아닙니다.** 스펙이 확정한 목록을 전부 산출해 나란히
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

### 원달러 그리드 — 견고성 검사 (축별 단독 + 국면 분할)

```bash
# 사양서 §12.1 축별 단독 검사와 §14 분할 분석을 한 번에. 인자가 없다
poetry run python scripts/strategy/run_usdkrw_grid_robustness.py
```

- **인자가 없습니다.** 사양서 §12.1·§14 가 확정한 축과 구간을 **전부** 산출하는 것이 설계이며,
  골라 돌리는 노브로 쓰면 **어느 축을 안 돌렸는지가 산출물에서 보이지 않습니다.**
  파라미터 하나를 골라 돌리려면 위의 `run_usdkrw_grid.py` 를 씁니다
- **최적 조합을 찾는 것이 아닙니다.** §12.1 이 "전수 탐색 금지 — 6,912가지를 돌려 최고 조합을
  고르면 그것이 과최적화" 라고 못 박았습니다. 이 실행이 답하는 것은
  **기본 설정의 결론이 축을 옮겨도 유지되는가** 하나이며, 판정은 **불리언의 뒤집힘 여부**로만 나옵니다
- **고유 실행 33회 · 약 35초**입니다. 축은 환전 2005~ 에 돌리고 **룩백 N 만 네 실행 전부**에
  돌립니다 — §15.3 #8 과 §18 의 1차 목적이 N×경로를 요구하기 때문입니다
- **축이 8개입니다.** 사양서 §12 의 일곱(N·g·차등·최소폭·상한·RP 하한·파킹 하한)에
  **환전 스프레드**를 더했으며, 표에 **「사양서 §12 에 없는 추가 축」으로 표기**됩니다
- 산출물은 `storage/results/<실행시각>_usdkrw_grid_robustness/` 에 `axes.csv`(축 비교 40줄) ·
  `regimes.csv`(국면 205줄) · `summary.json` 으로 남습니다.
  **비교표가 40줄인데 실행이 33회인 이유**는 여덟 축이 전부 기본값을 포함해서입니다 —
  기본 설정은 한 번만 돌리고 축마다 기준선으로 다시 싣습니다
- ⚠️ **「분할매수 후 보유를 이기는가」가 여덟 축 중 셋에서 뒤집힙니다** — N=7 · g=1.6%·2.4% ·
  차등 ±0.3 에서는 이깁니다. **「그러니 g=1.6% 를 쓰자」로 읽으면 §15.1 의 「결과를 보고
  파라미터 변경 금지」를 어깁니다.** 뒤집히는 지점의 절대금액이 45만~572만원(총자산의 0.4~3.2%)이라
  그 흔들림은 **표본이 그 지점을 특정할 만큼 크지 않다**는 신호입니다
- **나머지 결론 셋은 여덟 축 전부에서 흔들리지 않습니다** — 원화 파킹과 B&H 를 이기고,
  MDD 가 −10%보다 얕고, 세후 이자가 총수익의 절반을 넘습니다
- **사양서 §15.3 #8 은 통과입니다.** N=1/3/5/7 에서 세 기준(종료 총자산·Calmar·Sharpe) 모두
  경로 순위가 그대로입니다. 남은 「판정 불가」는 261250 β 하나이며 등가성 검증이 답합니다
- **슬롯 상한 8/10/12% 는 결과가 원 단위까지 같습니다.** 기본 g 에서 미발동이라 그렇고
  버그가 아닙니다. 이 축에서 무언가를 바꾸는 값은 6% 하나뿐입니다
- **익절폭 g 축을 단일 축으로 읽지 마세요.** g 를 올리면 슬롯 상한이 함께 지배해
  익절폭·상한 발동·차등 소멸·현금 잔류가 같이 움직입니다
  ([spec/usdkrw_grid.md](spec/usdkrw_grid.md) §3.6)
- **§14 축1 에서 사양서의 예상이 뒤집힌 구간이 있습니다.** 「최악, 전 슬롯 물림」으로 지목된
  2009~2014 대세 하락이 **전략이 가장 크게 이긴 구간(+21.46%p)** 입니다 — 안 산 자금이 원화로
  이자를 받았기 때문이며, 반대로 급등장(2008 −20.24%p)에서 크게 집니다.
  **전 기간 −309만원은 그 둘의 합**입니다
- **`regimes.csv` 의 국면은 세 축입니다** — 사양서 §14 의 8구간(**겹침과 빠짐을 그대로 둡니다**),
  겹치지 않는 연속 분할, 한미 금리차 부호. 구간 지표는 **직전 거래일을 앵커로 포함**해 자른
  곡선에서 내며, **구간 MDD 는 그 구간 시작 기준**이라 전 기간 MDD 와 다릅니다
- **§14 축2 의 독립 사건은 6개뿐입니다.** 금리차 부호 구간 39개 중 31개가 20거래일 미만인
  전환기의 깜빡임입니다. **부호별 우열에 통계적 주장을 하지 않습니다**
- **ETF 두 경로는 사양서 8구간 중 앞 다섯이 「기간 밖」입니다.** 빈 줄을 지우지 않고 남기는 것이
  설계입니다 — 빼 버리면 「기간 밖」과 「재고 0」이 구분되지 않습니다
- 선행 조건은 위 `run_usdkrw_grid.py` 와 같습니다
- 결과와 판정은 [strategy/원달러_그리드.md](strategy/원달러_그리드.md) 에 있습니다

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
- **보유 한도는 전부 산출해 나란히 냅니다.** 한 포지션은 한도 하나만 가질 수 있으므로
  한도별 결과는 자금 분할이 아니라 **비교표**입니다
- 산출물은 `storage/results/<실행시각>_reverse_trading/` 에 `trades.csv`(체결 내역),
  `summary_by_target.csv`(대상별·한도별 집계), `summary.json` 으로 남습니다
- `trades.csv` 는 **신호 하나가 손절 단계 수만큼의 행**입니다. 집계는 신호 단위이므로
  조각을 그대로 세면 표본이 부풀어 승률이 왜곡됩니다
- 실행 시간은 순열 검정이 없어 **수 초**입니다
