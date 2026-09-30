# verify-lab 실행 명령어 레퍼런스

> 이 파일은 verify-lab 실행 명령어의 **단일 SoT(Source of Truth)** 입니다.
> README.md·CLAUDE.md 등 다른 문서에는 실행 명령어를 기재하지 않으며, 필요 시 이 문서를 참조합니다.
> 설치처럼 한 번만 쓰는 일회성 명령어는 기재하지 않습니다. **평상시 반복 실행하는 명령어만** 관리합니다.
>
> **명령과 한 줄 주석만 둡니다.** 인자의 뜻·기본값·저장 위치·데이터 소스의 함정은 각 스크립트와 수집기의
> `--help`·모듈 docstring 이, 산출물을 읽는 법은 그 매매법 결과 문서의 「재현 방법」이 말합니다 —
> 여기에 함께 두면 코드와 두 벌이 되어 어긋납니다 (2026-09-26 사용자 결정).

---

## 품질 검증

```bash
poetry run python validate_project.py                # Ruff + PyRight + Pytest. 통과 기준은 failed=0 skipped=0
poetry run python validate_project.py --only-tests   # --only-lint · --only-pyright 도 같은 모양
poetry run python validate_project.py --cov          # 커버리지 포함
poetry run black .                                   # 포맷 적용 (계획서의 마지막 Phase 에서만)
```

> **`passed` 수는 기준이 아닙니다** — 코드를 지우면 테스트도 함께 줄어듭니다. 판단이 필요하면 직전 실행과 비교하고,
> 지운 코드 없이 줄었을 때가 신호입니다.
>
> **세 항목이 모두 실패하고 `Command not found` 가 보이면** 코드가 아니라 실행 환경입니다. 셸에 남은 `VIRTUAL_ENV` 를
> Poetry 가 프로젝트 `.venv` 보다 우선한 것이고(그 환경에는 개발 의존성이 없다 — `poetry env info --path` 로 확인),
> `env -u VIRTUAL_ENV` 를 붙여 다시 돌면 됩니다.

---

## 데이터 수집

> 외부 서버(Yahoo Finance · KRX · ECOS · FRED · Bitstamp · Coin Metrics)에 실제 요청을 보냅니다. 이미 받은 파일이 있으면 다시 받지 않고,
> 덮어썼으면 그 수치를 쓴 결과 문서에 새 데이터 기간을 적습니다 (루트 [CLAUDE.md](../CLAUDE.md) 「재수집은 이미 나온 결과를 바꿉니다」).

### 미국 — yfinance

```bash
poetry run python scripts/data/collect_yfinance.py                   # QQQ 전 기간 (기본값) · 원본가
poetry run python scripts/data/collect_yfinance.py --ticker SPY
poetry run python scripts/data/collect_yfinance.py --adjusted        # 수정주가 — 대조·실측용
poetry run python scripts/data/collect_yfinance.py --index '^GSPC'   # 지수(종가 계열). ^ 는 셸 메타문자라 따옴표로 감싼다
```

### 국내 — pykrx · KRX

KRX 데이터포털 계정이 필요합니다 — 저장소 루트 `.env` 의 `KRX_ID` · `KRX_PW`.

```bash
poetry run python scripts/data/collect_pykrx.py                                              # KODEX 200 전 기간 (기본값) · 원본가
poetry run python scripts/data/collect_pykrx.py --ticker 261240 --start 20161227 --adjusted  # 수정주가 — 원달러 ETF 등가성이 쓴다
poetry run python scripts/data/collect_pykrx.py --ticker 261240 --start 20161227 --nav       # NAV (단일 값 계열)
poetry run python scripts/data/collect_pykrx.py --index --ticker 1001 --start 19800104       # 지수 종가 — 지수마다 첫날을 준다

poetry run python scripts/data/collect_krx_futures.py                         # 코스피200·코스닥150 선물 (기본값). 동시에 여럿 띄우지 않는다
poetry run python scripts/data/collect_krx_futures.py --product KRDRVFUKQI    # 한 상품만

poetry run python scripts/data/collect_etn.py                                  # 삼성 인버스 2X 코스닥150 선물 ETN (기본값)
poetry run python scripts/data/collect_etn.py --ticker 520057 --start 20221017 # 다른 종목 — 시작일은 그 종목의 상장일
poetry run python scripts/data/collect_etn.py --indicative-value               # 증권당 지표가치 (ETF 의 NAV 에 해당)

poetry run python scripts/data/check_pykrx_etf.py                              # 실측 — KODEX 200 데이터 성질
poetry run python scripts/data/check_pykrx_splice.py                           # 실측 — 수정주가 구간 이어붙이기 (2분할)
poetry run python scripts/data/check_pykrx_splice.py --ends 20081231,20141231  # 3분할 — 앞 구간이 상장일에 닿지 못했을 때
```

### 한국은행 — ECOS

인증키가 필요합니다 — 저장소 루트 `.env` 의 `ECOS_API_KEY` (ecos.bok.or.kr 에서 발급).

```bash
poetry run python scripts/data/check_ecos.py                                          # 실측 — 통계표·항목 코드 (코드를 쓰기 전에)
poetry run python scripts/data/check_ecos.py --keyword 환율 국제수지 --stat 731Y001
poetry run python scripts/data/collect_ecos.py                                        # 환율(종가·매매기준율) + CD 91일물 (기본값: 전부 · 전 기간)
poetry run python scripts/data/collect_ecos.py --series usdkrw_close --start 19980101 --end 20261231
```

### 미국 금리 — FRED

```bash
poetry run python scripts/data/collect_fred.py   # 미국 3개월 T-bill (DTB3). 인증키가 필요 없다
```

### 비트코인 — Bitstamp · Coin Metrics

```bash
poetry run python scripts/data/collect_btc.py   # Bitstamp 일봉 + Coin Metrics 기준가 · MVRV · 시가총액 전 기간, 받은 뒤 두 소스 종가를 크로스체크. 인증키가 필요 없다
```

---

## 매매법·조사 실행

> **결과 문서에 쓸 수치는 인자 없이 돌린 것이어야 합니다** — 대상을 좁혀 돌리면 같은 산출물 폴더를 덮습니다.

### 역방향

```bash
poetry run python scripts/run_reverse.py                            # 전 조합 (기본값)
poetry run python scripts/run_reverse.py --dataset qqq              # 한 대상만
poetry run python scripts/run_reverse.py --repeats 5000 --seed 42   # 무작위 뽑기 대조의 반복 수·시드를 바꿔 재현성 확인
```

### 중간선거_사이클

```bash
poetry run python scripts/run_midterm_cycle.py                              # 전 대상 (기본값)
poetry run python scripts/run_midterm_cycle.py --ticker SPY --ticker GSPC   # 대상을 좁힌다 (여러 번 줄 수 있다)
poetry run python scripts/run_midterm_cycle.py --repeats 5000 --seed 42     # 무작위 뽑기 대조의 반복 수·시드
poetry run python scripts/run_midterm_cycle.py --stop-grid                  # 손절선 격자 전부 (기본은 확정 무손절 한 종)
```

### 반감기_사이클

```bash
poetry run python scripts/run_halving_cycle.py                              # 1단계 반감기 경과 격자 · 2단계 지표 신호 열넷 측정 + 3단계 진입 × 청산 격자 × 손절선 격자 체결 (기본값). 원시 파일만 읽는다
poetry run python scripts/run_halving_cycle.py --repeats 5000 --seed 42     # 무작위 뽑기 대조의 반복 수·시드 (표본이 하한 이상인 칸에만 검정이 붙는다 — 1단계 격자는 전 칸 미만)
```

선행 조건은 비트코인 수집(위 「비트코인 — Bitstamp · Coin Metrics」)이 받은 네 파일이다.

### 원달러_ETF_등가성

```bash
poetry run python scripts/run_usdkrw_equivalence.py                   # 전 조합 (기본값)
poetry run python scripts/run_usdkrw_equivalence.py --model usd_rate  # 이론값 모형 하나만
```

### 레버리지_ETF_괴리

```bash
poetry run python scripts/run_leverage_tracking.py                    # 전 쌍 (기본값)
poetry run python scripts/run_leverage_tracking.py --index 나스닥100   # 한 지수만
```

### 선물_대_레버리지_ETF

```bash
poetry run python scripts/run_futures_leverage.py                     # 전 조합 (기본값)
poetry run python scripts/run_futures_leverage.py --index KOSDAQ150   # 한 지수만
```
