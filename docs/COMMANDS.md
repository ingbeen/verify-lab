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
> 원인과 대처는 [.claude/rules/session-bootstrap.md](../.claude/rules/session-bootstrap.md) 5절에 있습니다.

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

# 지수 — 종가 하나짜리 계열로 storage/series/ 에 저장 (중간선거_사이클용)
poetry run python scripts/data/collect_yfinance.py --index '^GSPC'
poetry run python scripts/data/collect_yfinance.py --index '^IXIC'
```

- 전 기간(`period="max"`)을 받아 `storage/market/<종목>_max.csv` 에 저장합니다. 기존 파일은 덮어씁니다
- **기본은 원본가(배당 미조정)입니다.** 사용자가 결과를 차트와 직접 대조하는 것이 전제이고
  보통의 차트는 배당 미포함이기 때문입니다 ([매매/역방향/설계.md](매매/역방향/설계.md) "가격 처리").
  `--adjusted` 를 붙이면 수정주가로 받으며 **`storage/market/<종목>_adjusted_max.csv` 에 따로 저장**되므로
  원본가 파일을 덮어쓰지 않습니다 (`pykrx` 쪽과 같은 규칙)
- **확정되지 않은 최근 며칠은 저장하지 않습니다.** 제외된 행 수는 실행 결과 표의 "최근 제외"에 표시됩니다
- 이상치가 발견되면 **파일을 만들지 않고 예외로 중단**합니다. 반쪽짜리 파일이 남지 않습니다
- 🔴 **`--index` 는 «종가만» 남기고 `storage/series/<이름>_index.csv` 에 저장합니다** (파일명에서 접두 `^` 를 뗍니다).
  OHLCV 로 받지 않는 이유는 **미국 지수가 0 이 하나도 없어 시세 스키마 검증을 «그대로 통과하는데»
  옛 구간의 고가·저가가 종가로 채워져 있기** 때문입니다 — `^GSPC` 는 34.5%, `^IXIC` 는 24.7% 가 그렇습니다.
  그 상태로 장중 최악을 재면 「한 번도 안 밀렸다」로 읽히고 **예외도 경고도 나지 않습니다**
  ([매매/중간선거_사이클/설계.md](매매/중간선거_사이클/설계.md) §3.2).
  **심볼에 작은따옴표를 씌웁니다** — `^` 는 셸 메타문자입니다

### pykrx (국내 종목)

**KRX 데이터포털 계정이 필요합니다.** 저장소 루트의 `.env` 에 `KRX_ID`·`KRX_PW` 가 있어야 하며,
계정이 없으면 pykrx 는 아무것도 조회하지 못합니다.

```bash
# KODEX 200 데이터 성질 실측 (분배금 조정 여부·유동성·괴리율·결측)
poetry run python scripts/data/check_pykrx_etf.py

# 다른 ETF 나 다른 시작일로 실측
poetry run python scripts/data/check_pykrx_etf.py --ticker 069500 --start 20021014
```

- KRX 를 5회 호출하고, **각 결과를 받는 즉시** `storage/results/조사/pykrx_ETF_실측/` 에 CSV 로 남깁니다.
  한 실행 안에서는 뒤쪽 호출이 실패해도 앞선 원자료가 보존됩니다
- 🔴 **재실행은 첫 호출 «전»에 그 폴더를 비웁니다.** 대상을 바꿔 돌리면 앞 대상의 원자료가
  사라지고, 첫 호출이 실패하면 폴더가 빈 채로 남습니다. **남겨야 할 값은 `docs/<등급>/<매매법>/설계.md` 의
  「데이터 실측 기록」에 옮긴 뒤 다음 대상을 돌립니다** — 프로브는 `summary.json` 을 내지 않아
  **폴더만 봐서는 어느 대상의 결과인지 알 수 없습니다**
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
  `storage/results/조사/pykrx_이어붙이기_실측/` 에 CSV 로 남깁니다
- 판정 기준: **겹치는 구간의 값 불일치가 0건**이면 이어붙이기가 성립합니다.
  "덮지 못한 거래일"이 남으면 `--ends` 에 더 이른 종료일을 추가해 재실행합니다
- **모든 호출이 한 번의 실행 안에 있어야 합니다.** 수정계수는 조회 종료일이 아니라 조회 **시점** 기준이라,
  다른 날 받은 결과끼리 비교하면 판정이 성립하지 않습니다

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
- 검증 #1 이 원본가를 쓰는 근거는 [매매/역방향/설계.md](매매/역방향/설계.md) "가격 처리" 에 있습니다.
  원달러 그리드가 수정 종가를 쓰는 근거는 [조사/원달러_그리드/설계.md](조사/원달러_그리드/설계.md) §2 에 있습니다
- **확정되지 않은 당일은 저장하지 않습니다.** 장중에도 당일 행이 반환되기 때문이며,
  제외된 행 수는 실행 결과 표의 "최근 제외"에 표시됩니다
- 이상치가 발견되면 **파일을 만들지 않고 예외로 중단**합니다

#### 지수 수집 (검증 #10 용 — 코스피·코스닥 네 계열)

```bash
# 코스닥 종합지수 (기본값) — 1996-07-01 부터
poetry run python scripts/data/collect_pykrx.py --index

# 코스닥150 지수 — 2010-01-04 부터 (소급 산출분 포함)
poetry run python scripts/data/collect_pykrx.py --index --ticker 2203 --start 20100104

# 코스피 종합지수 — 1980-01-04 부터 (이 저장소에서 가장 긴 계열)
poetry run python scripts/data/collect_pykrx.py --index --ticker 1001 --start 19800104

# 코스피200 지수 — 1990-01-03 부터
poetry run python scripts/data/collect_pykrx.py --index --ticker 1028 --start 19900103
```

- **`storage/series/<지수>_index.csv` 에 종가 하나짜리 계열로 저장합니다.** 시세가 아닙니다 —
  지수는 살 수 없어 시가에 집행할 수 없고, **네 계열 모두 소급 산출 구간의 시가·고가·저가가
  전부 0** 이라 시세 스키마로는 전 구간이 막힙니다.
  근거는 [조사/월말_진입/설계.md](조사/월말_진입/설계.md) §7.6·§7.11 에 있습니다
- **값을 정수화하지 않습니다.** ETF 원화 가격과 달리 지수는 소수 둘째 자리까지 있는 계산된 값입니다
- `--index` 는 ETF 와 **기본 티커가 다릅니다** — 인자 없이 주면 코스닥 종합(`2001`)을 받습니다
- **시작일을 직접 줍니다.** 기본값은 코스닥 종합의 산출 시작일이라 다른 지수에 그대로 쓰면
  받을 수 있는 앞 구간을 잃습니다

### 국내 선물 (코스피200·코스닥150 계약별 시세 — 검증 #9 용)

**KRX 데이터포털 계정이 필요합니다.** pykrx 와 같은 `.env` 설정을 씁니다.

```bash
# 두 상품 전 기간 (기본값) — 코스피200 1996-05-03~, 코스닥150 2015-11-23~
poetry run python scripts/data/collect_krx_futures.py

# 한 상품만
poetry run python scripts/data/collect_krx_futures.py --product KRDRVFUKQI
```

- **한 상품에 호출이 700회를 넘고 코스피200 은 25분쯤 걸립니다.** 계약 목록 스냅숏을 한 달
  간격으로 훑은 뒤 계약마다 기간 시세를 받기 때문입니다. **두 상품을 동시에 돌리지 마세요** —
  요청이 몰려 KRX 가 JSON 이 아닌 응답을 돌려주고 수집이 통째로 끊깁니다(실측). 하나씩 돌립니다
- **`MDCSTAT12601`(개별종목 시세 추이)** 를 직접 부릅니다. 이름이 비슷한 `MDCSTAT12701` 은
  「최근월물 시세 추이」라 **하루 한 행만** 주고 원월물이 통째로 빠집니다.
  근거와 통계 코드 표는 [조사/선물_대_레버리지_ETF/설계.md](조사/선물_대_레버리지_ETF/설계.md) §5.2 에 있습니다
- 저장은 **상품마다 파일 하나**(`<상품코드>_max.csv`)이고 `Contract` 컬럼으로 계약을 가릅니다.
  **읽을 때 `load_futures_csv` 를 씁니다** — 공통 `load_market_csv` 는 날짜 기준 중복 제거가
  같은 날짜의 계약을 첫 개만 남기고 지웁니다(경고만 뜨고 예외가 없습니다)
- 야간 세션·스프레드 종목·당일·미개시 구간을 제외하며 **제외 건수가 실행 결과 표에 종류별로** 나옵니다

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
  근거와 통계 코드 표는 [조사/레버리지_ETF_괴리/설계.md](조사/레버리지_ETF_괴리/설계.md) §6.1 에 있습니다
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

- 프로브는 원자료를 `storage/results/조사/ECOS_실측/` 에 남깁니다.
  **통계표코드·항목코드는 기억이 아니라 이 프로브로 확인**하며, 확정값은
  [조사/원달러_그리드/설계.md](조사/원달러_그리드/설계.md) §3.1 에 있습니다
- **환율은 두 계열을 받습니다.** `usdkrw_close`(종가 15:30)가 수익률 측정의 기준이고,
  `usdkrw`(매매기준율)는 환전 스프레드의 기준입니다. 매매기준율은 전영업일 가중평균이라 하루 늦고
  스무딩돼 있어 수익률 측정에 쓸 수 없습니다 ([조사/원달러_그리드/설계.md](조사/원달러_그리드/설계.md) §3.4)
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
  ([조사/원달러_그리드/설계.md](조사/원달러_그리드/설계.md) §3.2)

---

## 매매법·조사 실행

> AI 모델이 직접 실행할 수 있습니다. 파라미터를 바꿔가며 반복 실행하는 것이 검증의 본질입니다.
>
> 🔴 **매매법당 스크립트가 하나입니다.** 한 번 돌리면 **측정 표와 체결 산출물이 한 폴더에**
> 함께 나옵니다 — 등급(검증·매매·조사)은 분류일 뿐이라 실행을 가르지 않습니다.
> 어느 등급 폴더에 쌓일지는 [../src/verify_lab/tracks.py](../src/verify_lab/tracks.py) 가 정합니다.
>
> 둘로 나누면 같은 시세를 두 번 읽고 같은 신호를 두 번 계산하는데, **산출물 폴더가 매매법당
> 하나라 나중에 돈 쪽이 앞의 산출물을 지웁니다**(쓰기 전에 비우기 때문이고 예외는 나지 않습니다).

> ### 세 매매법의 산출물은 같은 규격입니다
>
> 파일 이름은 **`성적표.csv` · `거래내역.csv`** 이고 공통 컬럼이 같은 순서로 옵니다.
> 규격의 SoT 는 [../src/verify_lab/CLAUDE.md](../src/verify_lab/CLAUDE.md) 「매매 산출물 계약」입니다.
>
> - **`이길 때(%)` 는 양수, `질 때(%)` 는 음수**입니다 — 손익비의 분자와 분모입니다
> - **건수 컬럼은 정수로 나갑니다.** 잴 수 없는 칸은 **빈칸**이고 `0` 이 아닙니다 —
>   `0` 은 「손절이 걸리지 않았다」로 읽히는데 실제로는 「잰 적이 없다」입니다
> - **`summary.json` 도 세 매매법이 같은 여섯 칸**입니다 —
>   `track`(매매법 이름) · `datasets`(**대상 범위와 데이터 기간**) · `rule`(무엇을 어떤 규칙으로
>   돌렸나 · 제외 건수) · `row_counts`(**파일 이름** → 행 수) · `cost`(맨몸 성적 표기) · `notes`
> - **종목 컬럼은 종목명이고 종목코드는 `datasets` 에 있습니다**


### 검증 #1 — 역방향

```bash
# 전 조합 실행 (기본값) — 검증 대상 시세를 한 번에
poetry run python scripts/run_reverse.py

# 특정 시세만
poetry run python scripts/run_reverse.py --dataset qqq

# 순열 검정 설정을 바꿔 재현성 확인
poetry run python scripts/run_reverse.py --repeats 5000 --seed 42
```

- **강건성 조합을 한 실행에서 전부 산출합니다.** 신호군은 파라미터 × 시작연도 × 방향 ×
  시대 구간 × 데이터셋의 곱이며, 각 축의 값은 `docs/매매/역방향/설계.md` 와
  `studies/reverse/constants.py` 가 정합니다. **실제 개수와 실행 시간은 실행 결과의
  마지막 줄과 `summary.json` 에 나옵니다**
- **데이터셋끼리 나란히 놓고 보려면 같은 실행에서 계산해야 합니다.** 대조의 전제가
  "파라미터가 같았다"이고, 따로 돌리면 그 사실을 사람이 확인해야 합니다
- `--dataset` 이 고를 수 있는 값은 `--help` 로 확인합니다. 목록의 SoT 는
  `studies/reverse/constants.py` 의 `DATASETS` 입니다
- **방향 축에는 폭등·폭락 외에 `역방향 전체` 가 있습니다.** 두 방향을 한
  표본으로 묶되 상승 방향 신호의 수익률에 −1 을 곱해 역방향 진입 기준으로 부호를 맞춘 신호군이며,
  집계 3파일에만 나옵니다 (`signals.csv` 에는 없습니다). 근거는 스펙 §7 결정 ㉕ 입니다
- 산출물은 `storage/results/매매/역방향/` 에 측정 CSV **4개**(`signals`·`통계`·`excess`·`test`)와
  체결 산출물(`성적표`·`거래내역`), `summary.json` 으로 남습니다.
  **재실행이 그 폴더를 비우고 다시 씁니다**
- **순위 컷·집계 시작연도는 인자가 아닙니다.** 스펙이 확정한 목록을 전부 산출해 나란히
  보고하는 것이 이 검증의 설계이며, 값을 골라 넣는 노브로 쓰면 과최적화입니다
- 🔴 **`1차_판정.csv` 를 2026-09-16 에 없앴습니다.** 1차 판정은 `성적표.csv` 의 컬럼이며
  그 표의 축(방향 3 · 시대 구간 3 · 구간 6)과 값은 **`통계.csv` 576행에 그대로 있습니다** —
  되살리는 절차는 [매매/역방향/설계.md](매매/역방향/설계.md) §13 입니다
- **`거는 방향` 과 `방향` 은 다른 컬럼입니다** — 앞은 게이트가 가리키는 쪽(위·아래),
  뒤는 신호군의 종류(폭등·폭락·역방향 전체)입니다

#### 체결 — 확정 칸

- **손절선·보유 한도·대상 목록은 인자가 아닙니다.** 확정된 규칙을 그대로 적용하는 것이 설계이며,
  값을 골라 넣는 노브로 쓰면 표본에 맞춘 튜닝이 됩니다. 값의 SoT 는
  `studies/reverse/constants.py` 이고 근거는 규칙 문서 §3 입니다
- **손절선은 확정 −5% 한 종이고 보유 한도는 D+2 하나입니다.** 손절선 격자(무손절 + −2%~−10%)와
  K=20 대상은 코드에서 지웠습니다(규칙 문서 결정 ⑭). 「손절이 무엇을 막았는가」의 무손절 대조와
  지운 격자의 수치는 규칙 문서 §3.5 가 갖고, 다시 돌리려면 git `9126c54` 의 역방향 코드를 복원합니다
- 산출물은 `storage/results/매매/역방향/` 에 `거래내역.csv`(체결 내역),
  `성적표.csv`(대상 × 시기 집계), `summary.json` 으로 남습니다
- `거래내역.csv` 는 **신호 하나가 한 행**이고, `성적표.csv` 는 **대상 하나가 시기 5행**입니다
- **대상은 2종입니다** — KODEX 200 K=10, QQQ K=10, **전부 시작연도 2005**.
  `--dataset kodex200` 처럼 종목으로 고르면 그 종목 하나만 돕니다
- **백테스트 구간은 2005 하나로 통일돼 있습니다.** 성적이 아니라 표본 근거로 고른 값이며
  근거는 규칙 문서 §3.3 입니다. **QQQ 는 2005·2008 의 신호 집합이 완전히 같아** 통일해도 성적이 같습니다
- 실행 시간은 순열 검정이 없어 **수 초**입니다

### 검증 #9 — 선물 대 레버리지 ETF

```bash
# 전 조합 실행 (기본값) — 6쌍 × 3방식 × 7격자 × 롤 규칙 2벌 × 이자 가정 2벌
poetry run python scripts/run_futures_leverage.py

# 특정 지수만 (KOSPI200 · KOSDAQ150)
poetry run python scripts/run_futures_leverage.py --index KOSDAQ150
```

- **인자는 지수로 좁히는 것 하나뿐입니다.** 배수·격자·리밸런싱 주기·롤 규칙은 상수로 고정돼
  있고 인자로 열지 않습니다 — 노브가 되면 결과를 보고 고르게 되며 그것은 과최적화입니다.
  값의 SoT 는 `src/verify_lab/studies/futures_leverage/constants.py` 입니다
- 선행 조건: `storage/market/` 에 **선물 2종**(`KRDRVFUK2I_max.csv`·`KRDRVFUKQI_max.csv`)과
  **짝이 되는 ETF·ETN 8종**, `storage/series/CD91.csv` 가 있어야 합니다
- 산출물은 `storage/results/조사/선물_대_레버리지_ETF/` 에 남습니다
  - `comparison.csv` — 지수 × 배수 × 방식 × 구간 집계. **가장 먼저 볼 표입니다**.
    방식은 넷이며(레버리지 ETF · 선물 매일 · 선물 월 1회 · **선물 그대로**),
    **「선물 그대로」가 「1억을 넣고 그냥 두면 같은가」에 답합니다**
  - `decomposition.csv` — 차이 분해(롤·베이시스 몫 · 리밸런싱 오차 · **그대로 두기 오차** · 여유현금 이자 · 잔여)
  - `roll_events.csv` — 롤 이벤트 원자료. **판정일과 집행일이 따로** 있습니다
  - `breakeven.csv` — **매일 리밸런싱과 그대로 두기를 각각** ETF 와 견준 결과
  - `integer_contracts.csv` — 자기자본 규모별 정수 계약과 **실제 배수**. 계약 하나도 못 사면 「집행 불가」
  - `wipeouts.csv` · `leverage_drift.csv`
  - `windows_<지수>_<종목>.csv` — 시작일 전체 목록. 차트 대조용입니다
- **CSV 헤더는 한글**이고 비율은 백분율 2자리로 저장됩니다
- 확정 설계는 [조사/선물_대_레버리지_ETF/설계.md](조사/선물_대_레버리지_ETF/설계.md) 입니다

### 검증 #8 — 레버리지 ETF 괴리

```bash
# 전 조합 실행 (기본값) — 22쌍 × 보유 기간 7격자 × 축 3종
poetry run python scripts/run_leverage_tracking.py

# 특정 지수만 (KOSDAQ150 · KOSPI200 · S&P500 · 나스닥100 · 다우)
poetry run python scripts/run_leverage_tracking.py --index 나스닥100
```

- **보유 기간·임계값은 인자가 아닙니다.** 확정된 격자를 전부 산출해 나란히 보고하는 것이 설계이며,
  값을 골라 넣는 노브로 쓰면 과최적화입니다. 값의 SoT 는
  `src/verify_lab/studies/leverage_tracking/constants.py` 입니다
- 선행 조건: `storage/market/` 에 `PAIRS` 가 정한 **전 종목의 원본가**와,
  **ETN 을 뺀 종목의 수정주가**가 있어야 합니다 (ETN 은 분배금을 지급하지 않아 수정주가가 없습니다)
- 산출물은 `storage/results/조사/레버리지_ETF_괴리/` 에 남습니다
  - `divergence.csv` — 쌍 × 구간 집계. **가장 먼저 볼 표입니다**
  - `breakdown.csv` — 쌍 × 구간 × 축(변동성·방향·금리 환경)
  - `distribution.csv` — 분배금 몫과 **배당 보정분**. 원본가로 재서 생긴 왜곡의 크기입니다
  - `full_period.csv` — 상장 후 전체 구간 1건씩. **표본 1건이라 통계가 아니라 사례입니다**
  - `windows_<티커>.csv` — 쌍마다 하나씩 나오는 시작일 원자료. 차트 대조용이며 **합계가 수십 MB** 입니다
- **순열 검정이 없어 난수를 쓰지 않습니다.** 같은 데이터면 항상 같은 결과가 나옵니다. 실행 시간은 수 초입니다
- **3년 칸은 비중첩 표본이 한 자릿수**라 통계가 아니라 사례에 가깝습니다.
  결과와 판정은 [조사/레버리지_ETF_괴리/결과.md](조사/레버리지_ETF_괴리/결과.md), 확정 설계는
  [조사/레버리지_ETF_괴리/설계.md](조사/레버리지_ETF_괴리/설계.md) 입니다

### 검증 #5 — 원달러 ETF 등가성

```bash
# 전 조합 실행 (기본값) — 환율 계열 2종 × 이론값 2종 × 이상치 포함·제외
poetry run python scripts/run_usdkrw_equivalence.py

# 이론값 모형을 하나만
poetry run python scripts/run_usdkrw_equivalence.py --model usd_rate
```

- **이상치 축은 인자가 아닙니다.** 2019-03-14 의 종가 이상치 포함·제외를 나란히 보는 것이 설계이며,
  하나만 골라 산출하면 그 선택이 결론에 섞입니다
- 산출물은 `storage/results/조사/원달러_ETF_등가성/` 에 CSV 6개(`equivalence`·`annual_drift`·
  `leverage`·`premium`·`effective_cost`·`daily`)와 `summary.json` 으로 남습니다
- `effective_cost.csv` 는 **NAV 로 직접 잰 실효 총비용**입니다. 공시 총보수와 나란히 실립니다
- `daily.csv` 는 **손으로 검산하는 원자료**입니다. 현물 변화와 이자 기여분을 따로 담아
  이론값이 어떻게 만들어졌는지 그대로 따라갈 수 있습니다
- 결과와 판정은 [조사/원달러_ETF_등가성/결과.md](조사/원달러_ETF_등가성/결과.md) 에 있습니다

---

### 매매 — 중간선거_사이클 (9월 마지막 거래일 매수 → 다음해 6월 마지막 거래일 매도, 위)

**측정과 체결을 한 번에 돕니다.** 산출물은 `storage/results/매매/중간선거_사이클/` 에
`측정.csv`·`거래내역.csv`·`성적표.csv`·`분기.csv`·`분기내역.csv`·`진입위치.csv`·`분할매수.csv`·`분할매수내역.csv`·`summary.json` 아홉으로 나옵니다.

```bash
# 기본 실행 — 대상 다섯 × 중간선거해 × 손절선 격자 (방향은 「위」 하나)
poetry run python scripts/run_midterm_cycle.py

# 대상을 좁혀서 (여러 번 줄 수 있습니다. 전체는 SPY·DIA·QQQ·GSPC·IXIC)
poetry run python scripts/run_midterm_cycle.py --ticker SPY --ticker GSPC

# 무작위 뽑기 대조의 반복 수·시드 (기본값 1000 / 0)
poetry run python scripts/run_midterm_cycle.py --repeats 5000 --seed 42
```

- **규칙은 하나이고 진입·청산 격자가 없습니다** — 9월 마지막 거래일 종가 매수 → 다음해 6월
  마지막 거래일 종가 매도. **휴장 처리는 양쪽 다 앞당김입니다**
- **축은 「중간선거해」 하나입니다** (2026-09-22 사용자 결정). 사이클 네 칸을 견주어
  「Best Six Months(11~4월)라 좋았다」와 「중간선거 뒤라 좋았다」를 가른 대조는
  **10월 첫 거래일 진입으로 잰 기록**이며 `docs/매매/중간선거_사이클/결과.md` §17.1 에 있습니다 —
  **지금 구성으로는 재현되지 않습니다**
- **보유가 달력 분기에 맞아떨어집니다** — 4분기·1분기·2분기 셋이고, `분기.csv` 가 분기별 수익과
  **진입가 대비 보유 중 최악의 분포**(평균·중앙값·분위·구간별 건수)를 냅니다.
  두 표는 **무손절 경로로만** 나옵니다 — 손절이 걸리면 분기가 온전하지 않기 때문입니다
- **분할매수 격자와 진입 위치도 함께 나옵니다** — `분할매수.csv`(대상 × 10칸 집계)·`분할매수내역.csv`(진입마다 몫별 체결)는
  **무손절 · 배정액 기준**이고, 격자는 결과를 보기 전에 고정해 **인자로 바꾸지 않습니다**.
  `진입위치.csv` 는 진입일의 52주 최고 대비 · 이격도 · RSI 를 그 해의 결과와 나란히 싣습니다
- 🔴 **살 수 있는 대상의 중간선거 칸이 6~8건이라 칸당 하한(10)에 미달합니다.**
  `판정가능` 이 전 구간 「아니오」이고 우연확률도 붙지 않습니다 — **결론의 일부이지 버그가 아닙니다**
- 🔴 **1차 판정에 변별력이 없습니다.** 게이트가 회당 기대값 하나인데 9개월 보유 평균이 16~29% 라
  **판정 대상 칸이 전부 후보**가 됩니다. 며칠짜리 이벤트형에 맞춰진 기준이라 그대로 읽으면 안 됩니다
- **방향은 「위」 하나입니다.** 두 방향을 함께 내면 `측정.csv` 와의 1:1 조인이 깨지고
  같은 칸이 위·아래 둘 다 후보가 되는 표가 나옵니다 — 반대 방향은 `측정.csv` 의
  **오른 비율·내린 비율**(1배 롱 기준)로 되짚습니다
- **지수 둘은 판정하지 않습니다**(살 수 없음). 긴 축을 보려고 함께 재며 `손절불가` 한 줄만 나옵니다
- 선행 조건은 **ETF 세 파일**(SPY·DIA·QQQ)과 각각의 `_adjusted_max.csv`(배당락 측정용),
  그리고 **지수 두 파일**(`storage/series/GSPC_index.csv`·`IXIC_index.csv`)입니다 —
  지수는 위 yfinance 절의 `--index` 로 받습니다
- 결과와 확정 설계는 `docs/매매/중간선거_사이클/결과.md` 와 `docs/매매/중간선거_사이클/설계.md`,
  확정 규칙은 `docs/매매/중간선거_사이클/규칙.md` §1 입니다
- 🔴 **이 스크립트는 1배만 잽니다.** 규칙이 집행하는 레버리지 상품(2배 SSO · DDM · QLD · 3배 UPRO · UDOW · TQQQ)의
  성적은 산출물에 없고 `규칙.md` §2.8 ~ §2.13 이 측정 기록으로 갖습니다 — 재실행으로 나오지 않습니다

---

## 코드가 없는 트랙

### 옵션 만기일 · 월말 진입 — 코드 삭제됨 (2026-09-22)

**실행할 스크립트가 없다.** 두 매매법의 확정 칸이 **`만기_말일` 의 조합(C1·C4)에 그대로
포함돼** 걸지 않기로 했고, 중복이 된 구현과 전용 실측 프로브 넷을 함께 지웠다.
규칙·성적은 `docs/조사/옵션_만기일/규칙.md` 와 `docs/조사/월말_진입/규칙.md`,
측정 기록과 **복원 절차**는 같은 폴더의 `결과.md` 머리말에 있다.

**두 매매법이 답하던 질문을 받던 `만기_말일` 도 아래처럼 코드를 지웠다.** 되살리려면
그 문서의 절차로 달력 계층까지 함께 꺼낸다.

### 만기_말일 — 코드 삭제됨 (2026-09-26)

**실행할 스크립트가 없다.** 확정 칸(9월 · 셋째 금요일 → 그 달 마지막 거래일 · 아래 ·
SPY·DIA·KODEX 코스닥150)의 승률이 사용자 기준에 못 미쳐 걸지 않기로 했고, 구현과
**그것만 쓰던 공유 달력 함수**를 함께 지웠다. 규칙·성적과 결정 근거(§3.6)는
`docs/조사/만기_말일/규칙.md`, 측정 기록과 **복원 절차**는 같은 폴더의 `결과.md` 머리말에 있다.
마지막 기본 실행의 산출물은 `storage/results/조사/만기_말일/` 에 그대로 남아 있다.

### 원달러 그리드 — 코드 삭제됨 (2026-08-30)

**실행할 스크립트가 없다.** 그리드는 채택되지 않았고 구현을 지웠다.
규칙·성적과 **기각 근거(§2.8)** 는 [조사/원달러_그리드/규칙.md](조사/원달러_그리드/규칙.md),
확정 설계는 [조사/원달러_그리드/설계.md](조사/원달러_그리드/설계.md) 에 있다.
