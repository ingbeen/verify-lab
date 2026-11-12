# Implementation Plan: verify-lab 이 quant-data 사본을 읽도록 전환 (quant-data 3단계)

> 작성/운영 규칙(SoT): `/impl-plan` 스킬(`~/.claude/skills/impl-plan/SKILL.md`)을 반드시 참고하세요.  
> (이 템플릿을 수정하거나 새로운 양식의 계획서를 만들 때도 해당 스킬을 포인터로 두고 준수합니다.)

**상태**: ✅ Done

---

> 상태는 🟡 Draft / 🔄 In Progress / ✅ Done. Done 조건과 기록 규칙은 `/impl-plan` 「3) 스킵 및 완료 규칙」이며 `~/.claude/hooks/plan_lint.py` 가 저장 때 검사한다.

---

**작성일**: 2026-11-12 13:56
**마지막 업데이트**: 2026-11-12 14:01
**관련 범위**: data, studies(중간선거_사이클 · 반감기_사이클), scripts, tests, 문서 — 그리고 다른 저장소 quant-data 의 문서 두 장
**관련 문서**: 루트 `CLAUDE.md`, `src/verify_lab/CLAUDE.md`, `scripts/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/docs.md`, `.claude/rules/research.md`, `.claude/rules/trading.md`, `docs/MEMORY.md`, quant-data 루트 `CLAUDE.md`

---

## 1) 목표(Goal)

- [x] 목표 1: 두 매매법(중간선거_사이클 · 반감기_사이클)이 quant-data 가 내보낸 사본만 읽는다 — 받는 폴더 `storage/market/` 하나, 목록 `quant_data_files.txt`, 매니페스트 `quant_data_manifest.json`
- [x] 목표 2: verify-lab 에 시세를 받는 코드가 없다 — 수집기 · 수집 CLI · pykrx 실측 스크립트 · KRX 계정 모듈 · 의존성 셋(yfinance · pykrx · python-dotenv)
- [x] 목표 3: 재실행이 바꾼 값을 원인별로 가른 수치(① 코드 전환 · ② 6자리 입력 · 새 분배 재조정 · Coin Metrics 자릿수 · ③ 기간 연장)가 두 매매법의 결과 문서에 남는다
- [x] 목표 4: 두 저장소의 문서가 새 흐름(받기는 quant-data, verify-lab 은 사본을 읽는다)을 말하고, 따라 하는 문장이 지운 파일을 가리키지 않는다

## 2) 비목표(Non-Goals)

- **quant-data 의 코드와 내보내기 형식을 바꾸지 않는다** — verify-lab 이 quant-data 형식에 맞춘다(Q2 의 C 탈락). quant-data 는 문서 두 장만 고친다
- **quant-data 를 갱신하지 않는다** — HEAD `ef8bd2a` · 기준일 2026-11-10 그대로 내보낸다(Q8)
- **verify-lab 수집기로 다시 받지 않는다** — 지금 `storage/` 가 전환 전 기준선(Q7 ① 의 재료)이다
- **코드가 지워진 조사의 자료를 받지 않는다**(Q5) — 되살릴 때 그 줄을 목록에 더한다
- **결과 · 규칙 문서의 본문 수치를 새 실행으로 바꾸지 않는다**(Q9) — 머리말 데이터 기간과 재실행 기록만 고친다
- **확정 규칙의 값을 다시 고르지 않는다**(`.claude/rules/trading.md`) — 재실행 뒤 「재수집하면 목록을 다시 판단한다」에 걸릴 거리가 보이면 보고만 한다
- **기록은 고치지 않는다** — 머리말의 옛 데이터 기간 · 재실행 기록 · 실측 기록 · 「확정된 설계 결정」 표 · 문서에 박힌 옛 스크립트 원문(코드 블록)에 남은 옛 파일 이름은 그때의 기록이다
- **`reference/` 는 읽기 전용이라 고치지 않는다** — 수집기를 언급하는 곳이 있어도 둔다(`.claude/rules/reference.md`)
- **`storage/results/조사/pykrx_ETF_실측/` 은 지우지 않는다** — `docs/조사/원달러_ETF_등가성.md` 「14.3 ETF 2종」이 프로브 원자료로 가리킨다(사용자 2026-11-12)
- **루트 `CLAUDE.md` 측정의 원칙 14 의 한계 ③(「국내 ETF 는 KRX 가 수정주가를 최근 3,000거래일만 준다」)은 이 계획서에서 고치지 않는다** — quant-data 의 국내 수정주가(KRX 기준가로 이은 C-2)로 바뀌는 사실이지만, 국내 파일을 읽는 매매법이 없고(Q5) 국내 합성(quant-data 2단계)이 같은 자리를 다시 다룬다. 8) Notes 에 남긴다
- quant-data 2단계(국내 합성)

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

- quant-data(`/Users/yubeen/Workspace/quant-data`)가 시세를 받고 · 판정하고 · 가공해 사용처에 CSV 사본만 넘긴다. quant 는 이미 전환했다(quant 커밋 `9530ce9`). verify-lab 은 아직 자기 수집기로 받은 `storage/market/` · `storage/series/` 를 읽는다
- verify-lab 수집기에는 「다시 받은 시세가 기존 파일과 다르면 원인을 가리는」 방어가 없다(quant-data 판정 문서 1장). 전환하면 그 방어 아래의 사본을 읽게 된다
- 작업 순서: quant-data 의 Q21 은 「2단계 국내 합성 → 3단계 verify-lab 전환」이었으나 사용자가 3단계를 먼저 하기로 정했다(2026-11-12) — verify-lab 에 코드가 남은 매매법(중간선거 · 반감기)은 국내 파일을 읽지 않아 2단계에 의존하지 않는다

### 결정 기록 (2026-11-12 — 이 계획의 기준, 다시 묻지 않는다)

| # | 항목 | 결정 |
| --- | --- | --- |
| Q1 | 받는 폴더 | **한 폴더 `storage/market/`** · 목록 하나 · 매니페스트 하나 · 내보내기 한 번. 결과 한 벌이 데이터 한 버전(커밋 · 기준일 하나)에 짝지어진다. 「폴더가 스키마를 가른다」 계약은 「대상 정의(`Dataset`)가 로더를 정한다」로 바꿔 쓰고 `SERIES_DIR` 를 지운다. 탈락: 두 폴더(매니페스트 둘 사이에 버전이 에러 없이 섞인다) |
| Q2 | 지수 | **사본(OHLCV)은 그대로 두고 로더가 종가만 꺼내 `Date,Value` 계열로 넘긴다** — 매매법 코드는 `price_column=Value` 그대로. 탈락: `Close` 로 읽기(장중 판정을 `price_column` 이 고르므로 가짜 고가 · 저가가 보유 중 최악에 조용히 들어간다 — 아래 사실), quant-data 가 종가 계열로 내보내기 |
| Q3 | 자릿수 | **`PRICE_DECIMALS = 4` 유지, 뜻을 「결과 출력 자릿수」로만 고친다** — 계산은 6자리 입력 그대로. 결과에 Coin Metrics 기준가가 실리는 칸(`크로스체크.csv` · `대체일.csv`)은 4자리 출력에서 깎이는 크기를 한계로 적는다(체결 가격 Bitstamp 는 2자리라 해당 없음). 탈락: 6자리 출력(전역 가격 4자리 상한) |
| Q4 | 수집 계층 | **수집기 4 · `krx_common` · `krx_credentials` · `data/constants.py` · `scripts/data/` 전부 · 그 테스트를 지운다.** 의존성은 `poetry remove yfinance pykrx python-dotenv` 로 뺀다 — **실행 전에 승인을 받고, `poetry sync` 는 쓰지 않는다**(quant 전환 때 잠금 파일 밖 패키지까지 지웠다 — quant-data `docs/plans/PLAN_quant_data_split.md` 진행 로그 2026-11-11 13:52). `tracks.py` 의 프로브 두 줄은 남긴다(되살렸을 때 같은 자리에 쌓이게 — 그 파일 98 ~ 99행 주석과 같은 이유), `docs/INDEX.md` 는 프로브 두 행의 코드 칸과 되살리는 절차만 고친다. 남기는 것: `loader.py` · `crosscheck.py` · `crypto_common` 의 `load_crypto_market_csv` 와 75% 임계값. 옮기는 것: `BITSTAMP_TICKER` · Coin Metrics 파일 이름 셋 → 반감기 `constants.py`, `PUBLICATION_LAG_DAYS` → 쓰는 곳이 하나라 반감기 `runner.py` 상단(값 1 그대로) |
| Q5 | 받을 범위 | **두 매매법이 읽는 9개만** |
| Q6 | 옛 파일 | **`storage/market/` 의 옛 59개 · `storage/series/` 17개를 지운다**(git 이력에 남는다). 기록은 두고 **따라 하는 문장만** 고친다 — 아래 「문서 고치는 규칙」. `.gitignore` 주석은 「사본과 매니페스트를 결과와 함께 커밋」으로 |
| Q7 | diff 가르기 · 커밋 | **scratchpad 세 단계 대조** — ① 옛 파일을 새 이름 · 모양으로 바꿔 새 코드로 → 산출물 CSV 바이트 같음(`summary.json` 은 뺀다 — `docs/MEMORY.md`) ② quant-data 사본을 **파일마다 그 파일의 옛 끝날로** 자른 것(QQQ 2026-11-04 · 나머지 중간선거 파일 2026-10-05 · 반감기 넷 2026-09-30) → 차이 = 6자리 · DIA 재조정 · Coin Metrics 자릿수 ③ 전체 사본(실제 전환) → ②와의 차이 = 기간 연장. **커밋은 한 번**(코드 + 사본 + 결과) — `docs/MEMORY.md` 「이름만 바꾸는 변경과 값을 바꾸는 변경을 한 커밋에 섞지 않는다」의 **예외**이며 이 표와 커밋 메시지에 적는다. 근거: 두 커밋으로 나누면 첫 커밋이 지수 파일의 시가 · 고가 · 저가를 `Date,Value` 에서 만들어 **어느 출처에도 없는 데이터를 커밋**하게 된다. 「바이트 대조로 확인한 뒤」는 ① 이 scratchpad 에서 지킨다 |
| Q8 | quant-data 갱신 | **하지 않는다** — `ef8bd2a` 그대로 |
| Q9 | 문서 수치 | **머리말 데이터 기간 + 재실행 기록 한 행(원인별 대조 수치)만.** 본문은 그때 기록. 반감기 진행 중 포지션의 변화는 재실행 기록에 |
| — | 파일 이름 · 지수 경로 | `MARKET_FILE_TEMPLATE = "{ticker}_raw.csv"` · `ADJUSTED_FILE_TEMPLATE = "{ticker}_adjusted.csv"`(이름은 그대로, 값만). 지수는 `ticker` 를 `GSPC` · `IXIC` 그대로 두고 **파일 이름만 `symbol`(`^GSPC`)로** 만든다 — `--ticker GSPC` 와 `summary.json` 의 `ticker` 가 바뀌지 않는다. `INDEX_FILE_TEMPLATE` · `NAV_FILE_TEMPLATE` 을 지우고, `TestPriceBasis` 는 지수 템플릿 허용 대신 지수 두 대상을 분배금 없는 예외에 넣는다 |
| — | 문서 | verify-lab `docs/COMMANDS.md` 「데이터 수집」은 quant 선례처럼 quant-data `docs/COMMANDS.md` 「내보내기」를 가리키고 명령을 직접 적지 않는다. 루트 `CLAUDE.md` 「저장소 밖의 경로를 참조하지 않습니다」는 참고 자료 얘기라 유지하고 데이터는 사본으로 안에 있다고 한 줄. KRX 계정(`.env`)은 더 쓰이지 않으며 지우는 것은 사용자 몫 |

### 착수 전 확인한 사실 (2026-11-12)

**두 저장소 상태** — verify-lab HEAD `c3a2641` · quant-data HEAD `ef8bd2a` · 둘 다 작업 트리 깨끗. quant-data 매니페스트 기준일 2026-11-10 · 파일 103개.

**받을 9개(quant-data 매니페스트) ↔ 지금 verify-lab 파일**

| 사본 (quant-data `storage/` 기준) | 기간 · 행 수 (사본) | 지금 verify-lab 파일 · 끝날 · 행 수 |
| --- | --- | --- |
| `prices/SPY_adjusted.csv` | 1993-01-29 ~ 2026-11-10 · 8,504 | `market/SPY_adjusted_max.csv` · 2026-10-05 · 8,478 |
| `prices/DIA_adjusted.csv` | 1998-01-20 ~ 2026-11-10 · 7,248 | `market/DIA_adjusted_max.csv` · 2026-10-05 · 7,222 |
| `prices/QQQ_adjusted.csv` | 1999-03-10 ~ 2026-11-10 · 6,962 | `market/QQQ_adjusted_max.csv` · 2026-11-04 · 6,958 |
| `prices/^GSPC_raw.csv` (OHLCV) | 1927-12-30 ~ 2026-11-10 · 24,833 | `series/GSPC_index.csv` (`Date,Value`) · 2026-10-05 · 24,807 |
| `prices/^IXIC_raw.csv` (OHLCV) | 1971-02-05 ~ 2026-11-10 · 14,059 | `series/IXIC_index.csv` (`Date,Value`) · 2026-10-05 · 14,033 |
| `prices/BTCUSD_raw.csv` | 2011-08-18 ~ 2026-11-10 · 5,564 | `market/BTCUSD_max.csv` · 2026-09-30 · 5,523 |
| `series/BTC_PriceUSD.csv` | 2010-07-18 ~ 2026-11-10 · 5,960 | 같은 이름 · 2026-09-30 · 5,919 |
| `series/BTC_CapMVRVCur.csv` | 2010-07-18 ~ 2026-11-10 · 5,960 | 같은 이름 · 2026-09-30 · 5,919 |
| `series/BTC_CapMrktCurUSD.csv` | 2010-07-18 ~ 2026-11-10 · 5,960 | 같은 이름 · 2026-09-30 · 5,919 |

- 옛 파일과의 대조는 quant-data 판정 문서 6.9 에 있다 — 원본가 겹친 날 설명 안 되는 차 0, DIA 수정주가는 verify-lab 끝날 뒤 새 분배(2026-10-16)로 날마다 같은 비율(0.99978)로 다르다, Coin Metrics 최대 상대차 0.000822(verify-lab 4자리 반올림)
- **시세 경로 · 파일 이름을 가리키는 코드 · 테스트**: `grep -rnE "_max|MARKET_DIR|SERIES_DIR" src scripts tests --include='*.py'` 70줄 · **16파일**(src 7 · tests 9 · scripts 0 — 넘겨받은 「21파일」은 틀렸다)
- **git 이 추적하는 옛 시세 파일**: `storage/market` + `storage/series` 76개
- 🔴 **장중 고가 · 저가를 쓸지는 `is_index` 가 아니라 `price_column` 이 정한다** — [trade_fill.py:464](../../src/verify_lab/execution/trade_fill.py#L464) `intraday = price_column == COL_CLOSE`, [split_entry.py:360](../../src/verify_lab/studies/midterm_cycle/split_entry.py#L360). 지수를 `Close` 로 읽으면 보유 중 최악이 옛 구간의 가짜 저가로 바뀌고 에러가 없다(중간선거 `설계.md` §3.2 — ^GSPC 34.5% 행이 고가 == 저가). Q2 의 근거이고 Phase 0 의 계약 테스트가 고정한다
- **`PUBLICATION_LAG_DAYS` 는 미래 참조 방어가 아니라 묵은 파일 방어다** — 반감기 [runner.py:664](../../src/verify_lab/studies/halving_cycle/runner.py#L664) · 707 이 온체인 두 계열과 시세의 끝 날짜 어긋남이 허용치(1일)를 넘으면 멈춘다. quant-data 도 Coin Metrics 에 같은 하루 지연을 허용하고(`src/quant_data/sources/coinmetrics.py:122`), `--exclude` 로 한쪽만 옛 끝날에 남는 경우도 이 검사가 잡으므로 남긴다
- **지수 사본은 시세 로더를 통과한다** — `^GSPC_raw.csv` 24,833행 · `^IXIC_raw.csv` 14,059행 모두 빈 칸 0 · 0 이하 가격 0 · 종가 최대 일간 변동 20.47% · 14.17%(로더 임계 50% 아래)
- **수집기가 하던 비트코인 방어(첫 날 · 끝 · 빈틈 · 끝나지 않은 UTC 날)는 quant-data 가 같은 모양으로 갖는다** — quant-data `src/quant_data/sources/bitstamp.py:126` · `coinmetrics.py:122` 의 `require_complete_range`(`sources/crypto_days.py`)
- **Coin Metrics 기준가의 4자리 출력 손실**(사본 6자리 기준 실측): 전 구간 최대 상대차 **8.217e-04**(2010-09-03 `0.06085`) — 그러나 그날은 Bitstamp 시작(2011-08-18) 전이라 결과 칸(크로스체크 · 대체일은 Bitstamp 날짜만)에 실리지 않는다. **2011-08-18 이후 최대 2.030e-05**(2011-10-19 `2.217255`). 사용자가 예로 든 `0.08584 → 0.0858`(2010-07-18)도 결과 칸 밖이다. 한계 문장의 값은 Phase 3 에서 실제 결과 칸으로 다시 잰다
- **대체일 33행에 첫 반감기 뒤 날짜가 있다**(2015-01-07 · 08 등) — 그날 측정 가격이 Coin Metrics 값이라 6자리 입력이 측정에도 들어간다
- **기간 연장이 두 매매법 산출물을 모두 바꿀 것으로 보인다**(계산 — Phase 3 에서 확인): 반감기 확정 규칙(월말 분할 · 반감기 뒤 27 ~ 32개월 매수 = 2026-07 ~ 12월)의 10월 회차가 새로 체결된다. 중간선거는 2026 진입의 청산이 2027-06 이라 신호 표본은 그대로이지만 기준선에 새로 끝나는 진입(2026-01 말 → 10월 말)이 생긴다

### 기존 함수 재사용 — 호출처 (전역 「기존 함수 재사용 전 검증」)

| 함수 | 직접 호출 (src · scripts) | 테스트 | 이 계획서에서 |
| --- | --- | --- | --- |
| `loader.load_market_csv` | 2곳 — `midterm_cycle/runner.py:144` · `data/crypto_common.py:47` | 28 | 새 지수 로더가 그대로 부른다 — ETF 와 같은 검증(결측 · 0 이하 · 급등락)을 지수에도 건다. 지수의 가짜 고가 · 저가는 0 보다 커서 통과하고, 로더가 종가만 남기므로 쓰이지 않는다 |
| `loader.load_series_csv` | 5곳 — 중간선거 runner 142(지수 — 새 로더로 바뀜) · 반감기 runner 605 · 650 · 651 · `scripts/data/collect_btc.py:185`(지움) | 13 | 반감기 세 곳은 그대로 |
| `loader.validate_series_data` | 5곳 — 수집기 4(지움) · `loader.py:265` | 0 | 남는 호출은 로더 하나 |

새 함수는 하나(`loader.load_close_series` — 시세 파일을 읽어 종가 하나짜리 계열로 넘긴다). 이름 · 위치는 `data/` 의 로딩 관용(「모든 시세 파일 로딩은 `data/` 계층」)을 따른다.

### 문서 고치는 규칙 (Q6 — Phase 4 가 이 규칙으로 전수를 판정한다)

| 규칙 | 대상 | 처리 |
| --- | --- | --- |
| R1 「관련 파일」 표 | 지운 파일을 가리키는 링크 · 경로(`tests/test_research_docs.py` 가 실재를 검사) | 묘비 표기(`삭제` · `없음`)로 바꾸거나 새 자리(목록 파일 · `docs/COMMANDS.md`)를 가리킨다 |
| R2 재현 방법의 선행 조건 | 「`storage/market/<옛 이름>` 이 있어야 한다」처럼 **지금 그 파일이 있다고 전제하는 문장** | 「옛 값 그대로 재현: `git show c3a2641:storage/market/<옛 이름>`. 새로 잴 때: quant-data 에서 내보낸다 — 이름 `{티커}_raw.csv` · `{티커}_adjusted.csv`, 국내 수정주가는 KRX 기준가로 이은 것이라 옛 KRX 수정주가와 다른 자료, quant-data 에 없는 자료(ECOS · FRED · ETN · KRX 선물 등)는 quant-data 에 받기를 더하는 것이 먼저」 |
| R3 「지운 정의」 표의 붙여 넣을 자리 | 붙여 넣을 파일이 이번에 통째로 지워지는 행(`krx_common.py` · `data/constants.py`) | 「그 파일째 `c3a2641` 에서 꺼낸다(quant-data 전환에서 지웠다)」 |
| R4 수집기를 되살려 받으라는 지시 | 「수집기를 되살려 받는다」 · 「`collect_*` 로 받는다」 | **verify-lab 에 수집기를 되살리지 않는다** — R2 의 「새로 잴 때」로 바꾼다(데이터 저장소가 받는다는 결정의 귀결). 옛 수집기 코드는 커밋을 지정해 볼 수 있다고만 적는다 |
| R5 기록 | 머리말 데이터 기간 · 재실행 기록 · 실측 기록 · 「확정된 설계 결정」 표 · 박힌 스크립트 원문 | **고치지 않는다** |

전수 판정 명령(Phase 4 — 줄 번호는 그때 다시 센다): `grep -rnE "_max\.csv|_index\.csv|collect_(yfinance|pykrx|btc)|scripts/data|storage/(market|series)|_collector|krx_common|krx_credentials|crypto_common|load_krx_credentials|check_pykrx" --include='*.md' docs CLAUDE.md src scripts tests README.md .claude` — `docs/plans/` 와 `reference/` 는 뺀다. 착수 전 같은 계열 grep 에서 문서 쪽 히트는 `docs/조사/` 8장 · 매매 두 폴더 · `docs/INDEX.md` · `docs/COMMANDS.md` · 루트 `CLAUDE.md` · `src/verify_lab/CLAUDE.md` 였다.

### 글자 규칙이 막거나 되돌릴 수 없는 결과에 물리는가

해당 없음 — 이 계획서는 열린 입력을 글자 규칙으로 판정해 막거나 되돌릴 수 없게 처리하는 코드를 만들지 않는다. 옛 파일 삭제는 git 이력으로 되돌릴 수 있다.

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- `.claude/plan-config.json` — 이 저장소의 검증 명령·자동 포맷·근거 승격 목적지 (**값의 SoT**)
- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절 (값이 아니라 **판단 근거**)
- `docs/MEMORY.md`
- `src/verify_lab/CLAUDE.md`
- `scripts/CLAUDE.md`
- `tests/CLAUDE.md` · 전역 `~/.claude/rules/python-tests.md`
- 전역 `~/.claude/rules/python.md`
- `.claude/rules/docs.md` · `.claude/rules/research.md` · `.claude/rules/trading.md` · `.claude/rules/reference.md`
- quant-data 루트 `CLAUDE.md` · quant-data `docs/COMMANDS.md` · quant-data `docs/research/시세_받기_판정.md`(3장 · 6.9 · 7장)
- `/impl-plan` 의 `review.md` — 특히 「다른 저장소의 변경」 리뷰 방식

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 두 매매법이 사본 9개만 읽고, 인자 없는 실행이 종료 코드 0 으로 끝난다 (`run_midterm_cycle.py` · `run_halving_cycle.py` · `chart_halving_cycle.py`)
- [x] 받는 폴더에 목록 · 매니페스트 · 사본 9개만 있고 매니페스트의 커밋이 `ef8bd2a`, 커밋 안 된 변경이 빈 목록이다
- [x] Q7 ① 산출물 CSV 바이트 같음(`summary.json` 제외), ② · ③ 의 차이를 원인별 수치로 진행 로그에 적었다
- [x] 수집 계층 삭제와 의존성 제거 — `poetry remove` 승인 · 실행 · 잠금 파일 diff 와 가상환경 패키지 목록 대조를 진행 로그에 적었다
- [x] 회귀/신규 테스트 — 지수 로더 · 지수 대상 프레임에 고가 · 저가 없음 · 새 파일 이름 · 가격 기준 예외
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation — verify-lab `/code-review` 와 quant-data 문서의 사본 diff 리뷰)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — verify-lab: 루트 `CLAUDE.md` · `src/verify_lab/CLAUDE.md` · `scripts/CLAUDE.md` · `tests/CLAUDE.md` · `docs/COMMANDS.md`(변경 있음) · `docs/INDEX.md` · `README.md` · `.gitignore` · 두 매매법 문서 · 조사 문서(「문서 고치는 규칙」 전수). quant-data: `docs/COMMANDS.md`(변경 있음) · `docs/research/시세_받기_판정.md`
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다 (중간선거 `설계.md` 결정 ㉔ · §3.10, 반감기 `설계.md` 결정 66 · §4.28, 두 `결과.md` 재실행 기록 · 반감기 한계, 계층 계약은 `src/verify_lab/CLAUDE.md`)
- [x] 미룬 지적 옮김 — 고치지 않은 리뷰 지적을 거르는 기준으로 걸러 `deferred_findings` 파일로 옮겼다. 계획서 없이 읽히게 썼다.
      거른 지적은 진행 로그에 기준 번호와 함께 남기고 Done 보고에 표로 냈다
      이 계획서가 그 파일의 항목을 고쳤다면 그 항목을 지웠다
      (둘 다 없으면 「해당 없음」. `/impl-plan` 의 `review.md` 「미룬 지적 옮기기」 참고)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

**verify-lab — 지움**

- `src/verify_lab/data/`: `yfinance_collector.py` · `pykrx_collector.py` · `bitstamp_collector.py` · `coinmetrics_collector.py` · `krx_common.py` · `krx_credentials.py` · `constants.py`
- `scripts/data/` 다섯 파일 전부(`collect_yfinance.py` · `collect_pykrx.py` · `collect_btc.py` · `check_pykrx_etf.py` · `check_pykrx_splice.py`) — 폴더째
- `tests/`: `test_yfinance_collector.py` · `test_pykrx_collector.py` · `test_bitstamp_collector.py` · `test_coinmetrics_collector.py` · `test_krx_common.py` · `test_krx_credentials.py`
- `storage/market/` 옛 59개 · `storage/series/` 17개(폴더째)

**verify-lab — 고침**

- `src/verify_lab/common_constants.py` — 두 파일 이름 템플릿 값, `MARKET_DIR` 주석(quant-data 사본 · 손으로 고치지 않는다), `SERIES_DIR` · `INDEX_FILE_TEMPLATE` · `NAV_FILE_TEMPLATE` 삭제, `PRICE_DECIMALS` 주석(결과 출력 자릿수 — 입력은 6자리)
- `src/verify_lab/data/__init__.py`(docstring) · `data/loader.py`(`load_close_series` 추가, 「수집기와 로더가 함께 쓴다」 · 「그 파일을 저장한 수집기가 넘긴 값」 같은 주석 · docstring 을 사본을 읽는 지금 흐름으로) · `data/crypto_common.py`(로더와 임계값만 남김) · `utils/meta_manager.py`(docstring 의 「검증·수집」)
- `src/verify_lab/studies/midterm_cycle/constants.py` — `Dataset.path` 를 `symbol` 로, 지수 두 대상의 폴더 · 템플릿, docstring(`ticker` · `symbol` · `price_decimals`)
- `src/verify_lab/studies/midterm_cycle/runner.py` — `load_dataset` 의 지수 분기를 `load_close_series` 로
- `src/verify_lab/studies/halving_cycle/constants.py` — 수집기 import 셋을 지우고 티커 · 파일 이름 셋을 이 파일에, 폴더 `MARKET_DIR`, `price_decimals` docstring
- `src/verify_lab/studies/halving_cycle/runner.py` — `PUBLICATION_LAG_DAYS` 를 상단 상수로(값 1 · 주석은 「끝 날짜 어긋남 허용치」), 사용자에게 보이는 예외 문구 셋(658 · 668 · 712행)의 `scripts/data/collect_btc.py` 를 「quant-data 에서 다시 내보낸다 — `docs/COMMANDS.md` 「데이터 받기」」로, `_onchain_gap` docstring 의 「수집은 시세를 먼저 저장하므로」(692 ~ 693행)를 사본 흐름으로
- `src/verify_lab/execution/trade_rows.py` — `price_decimals` docstring 의 「원시 데이터를 저장한 자릿수와 같아야」만
- `tests/test_layer_contracts.py` — 82행 「날짜」 허용 목록 항목 · 201행 `_functions_importing_pykrx` · `TestDataConstantsOwnership`(1182 ~ 1217 — 1192행 미국 제외 일수 포함) · `TestCredentialsBeforeImport`(1613 ~ 1644) · `TestKrxCommonOwnership`(1647 ~ 1733) · 그것들만 쓰던 상수(`_DATA_CONSTANTS` 등 — 지울 때 호출처를 센다)
- `tests/test_crypto_common.py`(지운 함수의 테스트 — `TestCryptoMarketLoader` 만 남는다) · `tests/test_common_constants.py`(템플릿 값 · `SERIES_DIR` · NAV) · `tests/test_data_loader.py`(새 로더) · `tests/test_studies_halving_cycle_runner.py`(308행 파일 이름 · 740행 docstring) · `tests/test_output_contract.py`(`TestPriceBasis` · `_write_index` 와 지수 대상 정의)
- **지수 픽스처를 쓰는 테스트 셋** — `tests/test_output_contract.py` 310 · 518행, `tests/test_studies_midterm_cycle_runner.py` 110 · 128행, `tests/test_studies_midterm_cycle_trading.py` 103 · 121행이 `INDEX_FILE_TEMPLATE` 으로 `Date,Value` 파일을 쓴다 → 시세(OHLCV) 파일을 `symbol` 이름으로 쓰게 바꾼다. 중간선거 runner 테스트에는 지수 프레임 계약(고가 · 저가 없음)을 더한다
- `pyproject.toml` · `poetry.lock` — `poetry remove` 결과
- 새 파일 `storage/market/quant_data_files.txt`(목록 9줄 + 머리 주석) · 내보내기가 쓰는 `storage/market/quant_data_manifest.json` 과 사본 9개
- `storage/results/매매/중간선거_사이클/` · `storage/results/매매/반감기_사이클/` — 재실행 산출물
- 문서: 루트 `CLAUDE.md` · `src/verify_lab/CLAUDE.md` · `scripts/CLAUDE.md` · `tests/CLAUDE.md` · `docs/INDEX.md` · `README.md` · `.gitignore` · 두 매매법의 `결과.md` · `설계.md`(규칙 문서 머리말은 Q9 대로 필요한 곳만) · 조사 문서(「문서 고치는 규칙」으로 판정한 줄)
- `docs/COMMANDS.md`: **변경 있음** — 「데이터 수집」 절을 quant-data `docs/COMMANDS.md` 「내보내기」를 가리키는 「데이터 받기」로 바꾸고 수집 · 실측 명령을 지운다. 반감기 「선행 조건」 문장도 사본 넷으로

**quant-data — 고침 (문서만)**

- `docs/COMMANDS.md`: **변경 있음** — 「내보내기」에 verify-lab 줄(`python3 scripts/export.py --to ../verify-lab/storage/market`)
- `docs/research/시세_받기_판정.md` — 7장 「남은 일」의 첫 줄(verify-lab 전환)을 지우고, 3.2 의 Q21 행에 순서 변경(2026-11-12 사용자 — 3단계를 2단계보다 먼저, 근거)과 3단계 완료를 덧붙인다

### 데이터/결과 영향

- **두 매매법 산출물 전부가 바뀔 수 있다** — 원인 다섯(이름 · 6자리 입력 · DIA 새 분배 재조정 · Coin Metrics 4 → 6자리 · 기간 연장)이 한 재실행에 섞이고, Q7 의 세 단계가 원인별로 가른다. `summary.json` 은 `datasets` 의 `file` 이름과 기간이 바뀐다
- 산출물 스키마(컬럼 · 파일 이름)는 바뀌지 않는다. 가격 칸의 자릿수(4)도 그대로다
- 반감기 확정 규칙의 진행 중 포지션 행과 중간선거 기준선이 기간 연장으로 바뀔 것으로 보인다(Context)
- 판단용 차트(`storage/charts/`, git 제외)는 다시 만들어 확인만 한다

## 6) 단계별 계획(Phases)

### Phase 0 — 기준 사본과 계약 테스트 먼저(레드)

**작업 내용**:

- [x] quant-data 의 고칠 문서 두 장을 scratchpad 에 사본으로 뜬다(마지막 Phase 의 다른 저장소 리뷰 기준)
- [x] 가상환경 패키지 목록을 scratchpad 에 떠 둔다(`env -u VIRTUAL_ENV poetry run pip freeze`) — Phase 1 의 `poetry remove` 대조 기준
- [x] 레드 테스트를 먼저 쓴다 — `load_close_series`(OHLCV → `Date,Value` 두 칸, 값 = 종가, 종가 0 이하는 `ValueError` — 경계), 중간선거 `load_dataset` 이 지수 대상에 고가 · 저가 없는 프레임을 낸다(결정 ⑥ · `price_column` 판정 고정), 두 템플릿의 새 값, 두 매매법 대상의 파일 이름(`SPY_adjusted.csv` · `^GSPC_raw.csv` · `BTCUSD_raw.csv` · `BTC_PriceUSD.csv` 등), `TestPriceBasis` 의 지수 예외. **지수 픽스처의 고가 · 저가는 종가와 «다르게»** 만든다(`tests/CLAUDE.md` §5 — 새어 들어가면 보유 중 최악이 달라져 드러나게)

---

### Phase 1 — 코드 전환과 수집 계층 삭제(그린)

**작업 내용**:

- [x] `common_constants.py` · `data/loader.py` · `data/crypto_common.py` · `data/__init__.py` 를 Scope 대로 고친다
- [x] 두 매매법의 `constants.py` · `runner.py` 와 `execution/trade_rows.py` docstring 을 Scope 대로 고친다
- [x] 수집기 · KRX 모듈 · `data/constants.py` · `scripts/data/` 를 지운다
- [x] 테스트를 Scope 대로 지우고 고친다 — 지운 정의를 가리키던 픽스처 · 헬퍼가 남지 않게 호출처를 센다
- [x] 🔴 **`poetry remove yfinance pykrx python-dotenv` 실행 전 사용자 승인을 받는다** — 승인 뒤 `env -u VIRTUAL_ENV poetry remove …` 로 실행한다. `poetry sync` 는 쓰지 않는다
- [x] 잠금 파일 diff 가 세 패키지와 그것만 쓰던 하위 패키지의 제거뿐인지, 가상환경 목록에서 빠진 것이 같은 집합인지 Phase 0 의 목록과 대조해 진행 로그에 적는다

**Validation**:

- [x] 고친 · 새 테스트 파일만 `pytest` 로 돌려 통과(전체 품질 검증은 마지막 Phase)
- [x] `grep -rnE "_max|SERIES_DIR|INDEX_FILE_TEMPLATE|NAV_FILE_TEMPLATE|_collector|krx_common|krx_credentials|pykrx|yfinance|dotenv" src scripts tests --include='*.py'` 의 남은 히트가 전부 의도한 것(예: `test_data_loader.py` 의 임시 파일 이름)인지 진행 로그에 적는다

---

### Phase 2 — scratchpad 대조 ① · ② (실제 `storage/` 는 건드리지 않는다)

**작업 내용**:

- [x] scratchpad 에 새 코드(`src/` · `scripts/`)를 복사한 루트 두 벌(A · B)을 만든다. `env -u VIRTUAL_ENV PYTHONPATH=<루트>/src poetry run python <루트>/scripts/run_*.py` 로 돌리고, **먼저 `verify_lab.__file__` 이 그 루트를 가리키는지 확인한다** — 저장소 패키지를 잡으면 실제 `storage/` 를 덮는다
- [x] ① 루트 A — 옛 verify-lab 파일을 새 이름 · 모양으로 바꿔 넣는다(`*_adjusted_max.csv` → `*_adjusted.csv`, `BTCUSD_max.csv` → `BTCUSD_raw.csv`, Coin Metrics 셋은 이름 그대로, 지수 `GSPC_index.csv` → `^GSPC_raw.csv` 는 시가 = 고가 = 저가 = 종가 = `Value` · 거래량 0). 두 매매법을 인자 없이 돌려 산출물 CSV 를 **루트 C(옛 코드 `git archive HEAD` + 같은 옛 파일)** 의 것과 바이트 대조한다 — `summary.json` 제외 (2026-11-12 조정 — 8) Notes)
- [x] ② 루트 B — quant-data 를 scratchpad 의 받는 폴더(목록 9줄)로 내보낸 뒤 **파일마다 그 파일의 옛 끝날까지** 자른다(QQQ 2026-11-04 · SPY · DIA · ^GSPC · ^IXIC 2026-10-05 · 반감기 넷 2026-09-30). 두 매매법을 인자 없이 돌려 **루트 C 산출물**과 CSV 별로 다른 행 수 · 바뀐 칸 · 최대 차이를 센다
- [x] 대조 스크립트는 scratchpad 에 두고 수치만 진행 로그에 적는다

**Validation**:

- [x] ① 산출물 CSV 바이트 같음 — 중간선거 8장 · 반감기 20장(`summary.json` 의 차이는 `file` 이름뿐인지도 본다). 다르면 멈추고 원인을 보고한다
- [x] ② 의 잘린 사본 9개가 옛 파일과 행 수 · 날짜 집합이 같다 — 다르면 ② 의 차이에 기간이 섞인 것이라 그 날짜를 먼저 적는다
- [x] ② 의 차이가 원인 셋(6자리 입력 · DIA 재조정 · Coin Metrics 자릿수)으로 설명되는지 칸별로 적었다 — 설명되지 않는 차이가 있으면 멈추고 보고한다

---

### Phase 3 — 실제 전환과 재실행(③)

**작업 내용**:

- [x] `storage/market/` 옛 59개 · `storage/series/` 를 지우고 `storage/market/quant_data_files.txt` 를 쓴다(머리 주석은 quant 선례 모양 — 내보내기 명령은 quant-data `docs/COMMANDS.md`)
- [x] quant-data 에서 `python3 scripts/export.py --to ../verify-lab/storage/market` 을 돌린다(파이썬 3.10 이상 — 전역 도구 함정 §6) — 9개 복사 · 매니페스트 커밋 `ef8bd2a` · 커밋 안 된 변경 없음을 확인한다
- [x] 두 매매법을 인자 없이 돌린다 · `BROWSER=true` 로 반감기 차트를 만든다
- [x] ③ 산출물을 ② 산출물과 대조해 기간 연장분을 센다 — 새 표본 · 바뀐 행(반감기 확정 규칙의 회차 · 포지션, 중간선거 기준선)
- [x] 반감기 결과 칸(`크로스체크.csv` · `대체일.csv`)의 Coin Metrics 종가를 사본 6자리 값과 대조해 4자리 출력의 최대 상대차를 다시 잰다(Q3 한계 문장의 값)
- [x] 중간선거가 확정 칸으로 좁힌 축에 대해 `.claude/rules/trading.md` 「재수집하면 목록을 다시 판단한다」의 판단 거리(성적표에서 확정 칸의 결론이 달라졌는가)를 보고용으로 적는다 — 값은 다시 고르지 않는다

**Validation**:

- [x] 세 실행 모두 종료 코드 0 · ERROR 줄 0
- [x] `git status --short storage/` 가 지운 76개 · 새 목록 · 매니페스트 · 사본 9개 · 두 결과 폴더의 변경뿐이다
- [x] 진행 로그에 ① · ② · ③ 의 원인별 수치가 모였다

---

### Phase 4 — 문서

**작업 내용**:

- [x] 「문서 고치는 규칙」의 전수 판정 명령을 돌려 히트마다 R1 ~ R5 판정을 진행 로그에 적고(파일 · 줄 · 규칙), R1 ~ R4 를 고친다
- [x] `docs/INDEX.md` — 프로브 두 행(`pykrx_ETF_실측` · `pykrx_이어붙이기_실측`)의 코드 칸을 `없음` 으로, 표 아래 문단에 되살리는 절차의 자리(`docs/조사/역방향.md` 「재현 방법」 — 두 프로브가 잰 것이 그 문서 §14 의 pykrx 실측이다)를 더한다. 그 절차를 `docs/조사/역방향.md` 「재현 방법」에 쓴다(`git show c3a2641:<경로>` · pykrx 의존성과 KRX 계정 모듈도 함께 되살려야 한다는 것)
- [x] 루트 `CLAUDE.md` — 「스크립트 실행 규칙」(`scripts/data/` 행 · 수집 문단 · KRX 계정 문단 → 사본을 읽는다 · 내보내기는 quant-data), 「재수집은 이미 나온 결과를 바꿉니다」(→ 사본을 다시 내보내면 바뀐다 · 흔적 규칙은 그대로 `.claude/rules/docs.md`), 「외부 라이브러리/도구 학습」의 pykrx 문단, 「기술 환경」, 「디렉토리 구조」의 `storage/` 행, reference 절에 한 줄
- [x] `src/verify_lab/CLAUDE.md` — 절대 원칙 2 의 파일 이름, 「데이터 저장 규칙」 표의 `storage/market/` 행과 조사 프로브 행, 「원시 시세 저장 규칙 — data 와 수집기」 절을 「받은 사본 규칙」으로(수집기 행을 걷고 파일 이름 · 손으로 고치지 않음 · 매니페스트와 함께 커밋 · 이상치 판정 · 날짜 · 가격 표기 — 입력 6자리 · 출력 4자리), 「실행 계층 계약」의 종가 반올림 행, 「단일 값 시계열 계층 계약」의 스키마 구분자 · 지수의 저장 형태(Q2 와 `price_column` 사실) · 지수 값의 자릿수 · 휴장일 행
- [x] `scripts/CLAUDE.md`(`data/` 행 · 메타 타입 다섯 줄) · `tests/CLAUDE.md`(수집기 테스트 이름 규칙 · 수집 라이브러리 스텁 문장) · `README.md`(스택) · `.gitignore`(시세 주석) · `docs/COMMANDS.md`
- [x] 중간선거 — `결과.md` 머리말 데이터 기간 · 재실행 기록 행(① · ② · ③ 수치, 한 커밋에 섞은 것과 그 근거) · 「대상과 근거 소스」 · 「관련 파일」 · 「재현 방법」 선행 조건, `설계.md` 결정 ㉔(사본을 읽는다 · 지수는 로더가 종가 계열로 — 확정 / 탈락안 / 근거)과 §3.10(대조 실측)
- [x] 반감기 — `결과.md` 같은 자리 + 「한계」에 Coin Metrics 4자리 출력 손실(Phase 3 실측값 · 체결 가격은 해당 없음), `설계.md` 결정 66(사본을 읽는다 · 수집 방어는 quant-data 가 갖는다 · `PUBLICATION_LAG_DAYS` 의 새 뜻)과 §4.28(대조 실측), `규칙.md` 머리말은 Q9 대로 본문이 어느 실행의 것인지만
- [x] quant-data 두 장을 Scope 대로 고친다

**Validation**:

- [x] 전수 판정 명령을 다시 돌려 남은 히트가 전부 R5(기록) 또는 의도한 것임을 진행 로그에 적는다

---

### 마지막 Phase — 리뷰 · 최종 검증

**작업 내용**

> 🔴 **체크박스와 상태를 먼저 확정하고, `/commit` 은 맨 마지막에** — 이유는 `/impl-plan` 「5) Commit Messages」.

- [x] 필요한 문서 업데이트 확인 (`docs/COMMANDS.md` 두 저장소 모두 변경 있음)
- [x] 자동 포맷 적용 (`poetry run black .`)
- [x] 변경 기능 및 전체 플로우 최종 검증 — 포맷 뒤 두 매매법을 인자 없이 다시 돌려 `git diff --stat storage/results/` 가 Phase 3 의 것과 같은지 본다
- [x] Validation 절에 `/code-review` 와 품질 검증 **실행 결과**를 적는다
- [x] 근거 승격 확인 · 미룬 지적 옮기기
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정
- [x] 🔴 **마지막에 `/commit` 을 실행하고 그 후보를 «이 계획서» 의 `#### Commit Messages` 절에 옮긴다** — 후보 본문에 `docs/MEMORY.md` 「이름만 바꾸는 변경과 값을 바꾸는 변경을 한 커밋에 섞지 않는다」의 예외와 근거(Q7)를 적는다. **커밋은 사용자가 한다 — 후보만 낸다.** quant-data 커밋 후보는 이 계획서가 Done 된 뒤 사용자가 요청하면 낸다

**Validation**:

> 순서는 `/code-review` → 품질 검증이다. 고칠 것 · 회차 상한 · 수정분 검증은 `/impl-plan` 의 `review.md` 가 정한다.

- [x] `/code-review xhigh` **1회차** (발견 13건 — 버그 5 [무거움 2 · 가벼움 3] · 그 외 8 · 조치: 무거움 1 수정(지수 파일 겹침 검사 — 변형 확인) · 무거움 1 사용자에게 올림 · 미룬 지적(사본 ↔ 결과 짝을 보는 장치 없음 — 이번 전 수집 시절부터 없던 것) · 가벼움 3 거름 · 그 외 6 은 계획 범위(지운 것을 가리키는 설명 · 이번에 쓴 문장 · 새 주석 문체)로 고침 · 그 외 2 고치지 않음) — 같은 회차 quant-data 문서 diff 리뷰(`general-purpose`, 발견 3건 — 버그 1 [무거움 0 · 가벼움 1] · 그 외 2 · 조치: 가벼움 1 수정 — 세 번째 문서 `docs/research/합성_시세_연장.md` 를 사본을 뜬 뒤 고침)
- [x] `/code-review xhigh` **2회차 — 상한** (발견 9건 — 버그 6 [무거움 3 · 가벼움 3] · 그 외 3 · 조치: 무거움 1 수정(재현 안내가 측정 뒤 다시 받은 판 `c3a2641` 을 「같은 값」으로 가리킴 — 9곳) · 무거움 2 거름(닿지 않음 — 기준 1) · 가벼움 1 수정(`크로스체크.csv` 차이율이 표에 찍힌 두 종가와 어긋남 — 변형 확인) · 가벼움 2 거름(기준 1 · 2) · 그 외 3 고치지 않음) — 같은 회차 quant-data 문서 diff 리뷰(`general-purpose`, 발견 4건 — 버그 0 · 그 외 4 · 조치: 그 외 1 수정(CD91 수집기 삭제 시점의 사실 오류 — 이번에 쓴 문장) · 그 외 3 고치지 않음). **2회차에 닿는 무거운 버그가 나와 고쳤으므로 3회차는 돌지 않고 사용자에게 보고한다**
- [x] 수정분 검증 (수정 7건 — 2회차 ① 재현 안내 · ㉠ CD91 · ⑤ 크로스체크 차이율, 보고 뒤 사용자 지시 ⑦ ⑧ ⑨ F4 · 세 번에 나눠 hunk 10 · 10 · 5개 · 발견 9건 — 무거움 0 · 조치: 1차 3건 거름(기준 1 · 2 · 3) · 2차 4건 사용자 결정(F1 미룬 지적 · F2 F3 받아들임 · F4 고침) · 3차 2건 거름(기준 3))
- [x] `poetry run python validate_project.py` (passed=1032, failed=0, skipped=0 — Ruff · PyRight 통과)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다** — 추측으로 적은 줄은 그대로 나간다.

1. 검증 / quant-data 사본 읽기로 전환
   - 두 매매법(중간선거_사이클 · 반감기_사이클)의 입력을 `storage/market/` 의 quant-data 사본 9개(커밋 `ef8bd2a` · 기준일 2026-11-10)로 교체 — 목록 `quant_data_files.txt` · 매니페스트 함께
   - 수집기 4 · 수집 CLI 5 · KRX 계정 모듈 · 그 테스트와 옛 시세 76개 삭제, 의존성 yfinance · pykrx · python-dotenv 제거
   - 이름 변경과 값 변경을 한 커밋에 담음 — `docs/MEMORY.md` 「이름만 바꾸는 변경과 값을 바꾸는 변경을 한 커밋에 섞지 않는다」의 예외. 두 커밋으로 나누면 첫 커밋이 지수 파일의 시가 · 고가 · 저가를 `Date,Value` 에서 만들어 어느 출처에도 없는 데이터를 커밋하게 됨. 바이트 대조는 scratchpad 대조 ①(같은 옛 파일에서 새 코드 = 옛 코드, CSV 28장 같음)로 대신함
2. 검증 / quant-data 3단계 — 시세 사본 전환 · 수집 계층 삭제 · 두 매매법 재실행
   - 파일 이름을 `{ticker}_raw.csv` · `{ticker}_adjusted.csv` 한 폴더로 변경(`SERIES_DIR` 삭제), 지수는 OHLCV 사본에서 종가만 꺼내는 `load_close_series` 로 읽음 — 옛 구간의 가짜 고가 · 저가가 보유 중 최악에 들어가지 않게
   - 출력 가격 4자리 유지(입력 6자리) — 반감기 크로스체크 · 대체일의 두 종가도 4자리, 차이율은 자른 값끼리
   - 재실행 결과 `1차 판정` 이 바뀐 행 0 · 확정 규칙 성적표 그대로, 기간 연장으로 반감기 2024 사이클 10월 회차 체결 · 중간선거 기준선 4행 변경
   - `docs/MEMORY.md` 「이름만 바꾸는 변경과 값을 바꾸는 변경을 한 커밋에 섞지 않는다」의 예외 — 나누면 첫 커밋이 지수의 시가 · 고가 · 저가를 `Date,Value` 에서 만들어 어느 출처에도 없는 데이터를 커밋하게 됨
3. 검증 / 시세 받기를 quant-data 로 넘기고 사본 기준 재실행
   - 같은 시세를 두 저장소가 다른 규칙으로 받지 않게 받기 · 판정은 quant-data, 이 저장소는 사본만 읽는 구조
   - 받기 쪽 방어(BTC 첫 날 · 끝 · 빈틈 · 두 소스 교차 확인)는 quant-data 가 같은 모양으로 갖고, 남긴 것은 로더 · 두 소스 대조 · 온체인 끝 날짜 허용치 `PUBLICATION_LAG_DAYS`
   - 원인별 차이(① 코드 전환 0 · ② 6자리 입력과 DIA 새 분배 · ③ 기간 연장 · ⓪ QQQ 재수집 뒤 다시 안 돌린 몫)를 두 매매법 `설계.md` · `결과.md` 에 기록
   - 한 커밋은 `docs/MEMORY.md` 「이름만 바꾸는 변경과 값을 바꾸는 변경을 한 커밋에 섞지 않는다」의 예외 — 나누면 첫 커밋이 지수의 시가 · 고가 · 저가를 `Date,Value` 에서 만들어 어느 출처에도 없는 데이터를 커밋하게 됨
4. 검증 / quant-data 사본 전환과 지운 시세를 가리키던 재현 안내 정정
   - 두 매매법 입력을 quant-data 사본 9개로 교체 · 수집 계층 삭제 · 인자 없는 재실행
   - 조사 문서 「재현 방법」을 「새로 잴 때는 quant-data 에서 내보내기 · 옛 값은 측정 당시 판을 `git log` 로 골라 `git show`」로 변경, 중간선거 본문 재현은 `7521cf5` 판 지정
   - 루트 · `src/verify_lab` · `scripts` · `tests` 의 `CLAUDE.md`, `docs/COMMANDS.md` 「데이터 받기」, `docs/INDEX.md` 를 사본 흐름으로 갱신
   - `docs/MEMORY.md` 「이름만 바꾸는 변경과 값을 바꾸는 변경을 한 커밋에 섞지 않는다」의 예외 — 나누면 첫 커밋이 지수의 시가 · 고가 · 저가를 `Date,Value` 에서 만들어 어느 출처에도 없는 데이터를 커밋하게 됨
5. 검증 / quant-data 사본 전환 · 원인별 대조 · 리뷰 2회차 반영
   - 재실행 diff 를 scratchpad 세 단계로 가름 — ① 새 코드 = 옛 코드(CSV 28장 바이트 같음) ② 6자리 입력 · DIA 새 분배 ③ 기간 연장, `1차 판정` 이 바뀐 행 0
   - 리뷰 반영 — 지수 사본 파일 겹침 검사 · 크로스체크 차이율 자기 일치 테스트 추가, 미룬 지적 둘(사본 ↔ 결과 짝 장치 없음 · 분할포지션 수익률 끝자리)을 `docs/DEFERRED_FINDINGS.md` 에 등록
   - `docs/MEMORY.md` 「이름만 바꾸는 변경과 값을 바꾸는 변경을 한 커밋에 섞지 않는다」의 예외 — 나누면 첫 커밋이 지수의 시가 · 고가 · 저가를 `Date,Value` 에서 만들어 어느 출처에도 없는 데이터를 커밋하게 됨

## 7) 리스크(Risks)

- **scratchpad 실행이 저장소 패키지를 잡아 실제 `storage/` 를 덮는다** — `PYTHONPATH` 가 편집 설치보다 앞서는지 `verify_lab.__file__` 로 먼저 확인하고, 다르면 실행하지 않는다(Phase 2)
- **① 이 바이트 같지 않다** — 코드 전환이 값을 바꾼 것이다. 멈추고 원인을 보고한다(지수 로더 · 경로 · 자릿수 중 어디인지)
- **`poetry remove` 가 다른 패키지 버전을 바꾸거나 잠금 파일 밖 패키지를 지운다** — 실행 전 승인 · 전후 `pip freeze` 대조 · 잠금 파일 diff 확인. 예상 밖 변화가 있으면 보고하고 멈춘다
- **DIA 재조정으로 DIA 의 모든 가격 칸이 바뀐다** — 날마다 같은 비율이라 수익률은 6자리 입력 차이 수준만 움직일 것으로 보인다. ② 가 그 크기를 잰다
- **기간 연장이 반감기 확정 규칙의 진행 중 포지션과 `규칙.md` 본문 수치를 어긋나게 한다** — Q9 대로 머리말과 재실행 기록에 「본문이 어느 실행의 것인가」를 적는다
- **조사 문서의 따라 하는 문장을 빠뜨린다** — 전수 판정 명령의 히트마다 R1 ~ R5 판정을 진행 로그에 남기고 Phase 4 Validation 에서 다시 돌린다. 「관련 파일」 표는 `tests/test_research_docs.py` 가 실재를 검사한다
- **옛 파일 삭제** — git 이 추적하므로 `c3a2641` 에서 되살릴 수 있다. 커밋은 사용자가 한다
- **두 저장소 커밋 사이의 공백** — verify-lab 만 커밋되고 quant-data 문서가 남으면 quant-data 「남은 일」이 낡는다. Done 보고에서 두 저장소 커밋을 함께 안내한다

## 8) 메모(Notes)

- 원칙 14 ③(국내 수정주가 3,000거래일)은 quant-data 국내 수정주가(C-2)로 바뀌는 사실이다 — 국내를 읽는 매매법을 되살리거나 quant-data 2단계(국내 합성)를 할 때 그 문장을 고친다(비목표)
- 사용자 지적(2026-11-12)의 Coin Metrics 예 `0.08584 → 0.0858`(2010-07-18, 상대 4.7e-4)은 Bitstamp 시작 전 날짜라 결과 칸에 실리지 않는다 — 한계 문장의 값은 결과 칸에서 잰 것으로 쓴다(Context)
- 사용자는 INDEX 「62행」을 지목했다 — 63행(`pykrx_이어붙이기_실측`)도 같은 모양이라 두 행을 함께 고친다
- **계획 조정 (2026-11-12 15:31 실측 · 사용자 승인 「진행」)** — Q7 ① 의 기준 「커밋된 결과와 바이트 같음」은 성립할 수 없었다: 커밋된 중간선거 결과가 QQQ 재수집(`8d5d3b7`, 2026-11-06) 전 시세로 남아 있었다(진행 로그 15:31). 그래서 ① 은 「같은 옛 파일에서 새 코드 = 옛 코드」(루트 A ↔ 루트 C)로, ② · ③ 의 비교 기준은 커밋된 결과 대신 루트 C 산출물로 바꿨다. 원인 목록에 **⓪ 커밋된 중간선거 결과가 QQQ 재수집 전 시세였다**(QQQ 행 44 — 커밋본 ↔ 루트 C)를 더해 결과 문서 재실행 기록에 따로 적는다. 탈락: ⓪ 을 먼저 따로 커밋(diff 는 갈리지만 결과 파일만 골라 커밋하는 단계가 늘고, Q7 이 이미 한 커밋으로 정했다)
- 반감기 산출물 CSV 는 20장이다 — 계획서 처음의 「21장」은 `scripts/CLAUDE.md` 메타 타입 설명의 표 수를 잘못 센 것
- **범위 추가 (2026-11-12 15:38 실측 · 사용자 승인 「진행」)** — Q3 의 전제 「결과는 4자리로 나간다」가 반감기 `대체일.csv` · `크로스체크.csv` 의 두 종가 칸에서 틀렸다(반올림 없이 나가 사본 6자리가 그대로 실린다 — 진행 로그 15:38). 반감기 `runner.display_tables` 에서 두 표의 Bitstamp · Coin Metrics 종가를 `PRICE_DECIMALS` 로 자르고, 기준가를 6자리로 쓴 합성 입력으로 두 표가 4자리를 넘지 않음을 보는 테스트 하나를 `tests/test_studies_halving_cycle_runner.py` 의 `TestDataQualityTables` 에 더한다(변형 확인 포함). `차이율(%)` 은 자르기 전 값으로 계산돼 바뀌지 않는다. 탈락: 6자리로 둔다(전역 가격 4자리 상한 · Q3 와 어긋남)

### 진행 로그 (KST)

- 2026-11-12 13:56: 결정 질문 한 라운드(Q1 ~ Q9) → 사용자 「추천대로」 + 추가 조건 다섯(프로브 산출물 · `tracks.py` 두 줄 유지 · `poetry remove` 승인 · 지울 계약 테스트 명시 · Coin Metrics 한계 · Q7 자르는 날짜와 MEMORY 예외). 계획서 작성
- 2026-11-12 14:01: 자체 검증. 1회차 — 지수 픽스처를 `INDEX_FILE_TEMPLATE` 으로 쓰는 테스트 셋(`test_output_contract` · 중간선거 runner · trading) 누락, 지수 사본이 시세 로더를 통과하는지(빈 칸 · 0 이하 · 급등락) 미확인 → 실측해 Context 에, ② 의 잘린 사본이 옛 파일과 날짜 집합까지 같은지 확인 단계 추가. 2회차 — 지우는 수집기를 말하는 남는 코드의 주석 · 예외 문구(`loader.py` · 반감기 runner 658 · 668 · 712 · 692 ~ 693 · `meta_manager.py`) 누락 → Scope 에, quant-data 도 Coin Metrics 하루 지연을 허용한다는 사실(허용치를 남기는 근거) 추가, 수집기로 다시 받지 않는다를 비목표에. 3회차 — 넘겨받은 금지 사항(수집기 재수집 · 묻기 전 갱신 · 내보내기 · git 상태 변경)과 Phase 대조, DoD ↔ Phase 짝, 동시성(두 실행 모두 단일 프로세스 · scratchpad 실행은 `meta.json` 도 scratchpad 에 씀) — 고칠 것 없음. 4회차 — 산출물 요약의 `file` 칸이 지수에서 `^GSPC_raw.csv` 가 되고 `ticker` 는 `GSPC` 로 남는 것이 계약 테스트(`dataset_record` 의 인자 출처)와 맞는지 — 맞음, 고칠 것 없음. 5회차 — 조사 문서 R2 의 「새로 잴 때」 안내가 국내 수정주가 차이를 함께 말하는지 · 비목표의 원칙 14 ③ 과 부딪히지 않는지 — 고칠 것 없음. 연속 3회 개선 없음으로 멈춤
- 2026-11-12 15:04: 사용자 승인 → 🔄 In Progress. **Phase 0 완료.** 사본 — quant-data `docs/COMMANDS.md` · `docs/research/시세_받기_판정.md` 를 scratchpad `qd_before/` 에, 가상환경 `pip freeze` 57줄(yfinance 0.2.66 · pykrx 1.2.8 · python-dotenv 1.2.2 포함)을 `pip_freeze_before.txt` 에. 레드 테스트 — `test_data_loader.py`(새 로더 두 개), `test_common_constants.py`(템플릿 값 · 두 기준 이름이 다름), 중간선거 runner(`test_읽는_파일은_quant_data_사본의_이름이다` · `TestIndexLoad`, 지수 픽스처를 고가 · 저가 벌린 OHLCV 로) · trading(지수 픽스처), `test_output_contract.py`(`_write_index` OHLCV · `TestPriceBasis` 지수 예외 둘), 반감기 runner(`BTCUSD_raw.csv`). 실행 — `test_data_loader.py` 는 `load_close_series` import 실패로 수집 오류, 나머지 다섯 파일 20 failed · 36 errors · 118 passed. 실패 원인은 셋뿐 — 지수 파일 경로(`FileNotFoundError` 53 — 코드가 아직 `ticker` 로 경로를 만들고 값 계열 로더로 읽는다) · 파일 이름 단언 3(`BTCUSD_max.csv` · 중간선거 이름 목록 · 템플릿)
- 2026-11-12 15:08: Phase 1 코드 — `common_constants`(템플릿 `{ticker}_raw.csv` · `{ticker}_adjusted.csv`, `SERIES_DIR` · `NAV_FILE_TEMPLATE` · `INDEX_FILE_TEMPLATE` 삭제, `MARKET_DIR` · `PRICE_DECIMALS` · `COL_VALUE` · `KST` 주석), `loader.load_close_series` 추가와 수집기를 말하던 주석 넷, `crypto_common` 은 로더 · 임계값만, 중간선거 `Dataset.path` 를 `symbol` 로 · 지수 둘을 `MARKET_DIR` + 원본가 템플릿으로 · `load_dataset` 의 지수 분기를 새 로더로, 반감기 대상의 이름 넷을 constants 안에 직접 · `PUBLICATION_LAG_DAYS = 1` 을 runner 상단으로 · 예외 문구 셋과 docstring 둘, `trade_rows` · `meta_manager` docstring. 지움 — 수집기 4 · `krx_common` · `krx_credentials` · `data/constants.py` · `scripts/data/` 5 · 수집기 테스트 6. `test_crypto_common.py` 는 로더 테스트 셋만 남김(351 → 95줄), `test_layer_contracts.py` 는 `_DATA_CONSTANTS` · 「날짜」 허용 항목 · `_functions_importing_pykrx` · `TestDataConstantsOwnership` · `TestCredentialsBeforeImport` · `TestKrxCommonOwnership` 제거(1,871 → 1,683줄, 지우기 전 경계 줄을 단언으로 확인). 고친 테스트 8파일 `pytest` — **257 passed**. 남은 히트 grep 13줄은 전부 의도한 것 — `tracks.py` 확인 스크립트 두 줄(남기기로 함) · 중간선거 constants 504행(다우 지수를 넣지 않은 결정의 기록) · `report/writer.py` 45행(확인 스크립트의 한글 이름 예) · 테스트의 임시 파일 이름(`TEST_max.csv` · `BTCUSD_max.csv` · `QQQ_max.csv` 등 — 경로 거부 · 로더 검사용이라 이름이 뜻을 갖지 않음) · `test_data_loader.py` 308행(옛 데이터 소스의 사례 설명) · `test_meta_manager.py` 의 `max_count`
- 2026-11-12 15:21: 사용자 「진행」 → `env -u VIRTUAL_ENV poetry remove yfinance pykrx python-dotenv` — 설치 0 · 갱신 0 · **제거 28**(세 패키지와 그것만 쓰던 beautifulsoup4 · certifi · cffi · charset-normalizer · contourpy · curl-cffi · cycler · deprecated · fonttools · frozendict · idna · kiwisolver · matplotlib · multipledispatch · multitasking · peewee · pillow · protobuf · pycparser · pyparsing · requests · soupsieve · urllib3 · websockets · wrapt). 대조 — `pip freeze` 57 → 29줄, 빠진 28개 = 잠금 파일에서 빠진 `name` 28개(이름 집합 같음), 새로 생기거나 버전이 바뀐 패키지 0. `poetry.lock` 추가 줄 4개는 `content-hash` 와 `packaging` · `platformdirs` · `typing-extensions` 의 그룹이 `["main", "dev"]` → `["dev"]` 로 바뀐 것뿐(설치는 그대로 — `src` · `scripts` 가 이 셋을 import 하지 않음). 지운 28개를 `src` · `scripts` · `tests` · `validate_project.py` 가 import 하는 곳 0. **Phase 1 완료**
- 2026-11-12 15:31: Phase 2 ① — scratchpad 루트 A(새 코드)를 `PYTHONPATH` 로 돌리기 전 확인: `verify_lab` 은 이름 공간 패키지라 `__file__` 이 없고 `__path__` 첫 자리가 루트 A, `common_constants` · `report.writer` · `meta_manager` · 두 runner 모두 루트 A 의 파일, `META_JSON_PATH` 도 루트 A. 입력 9개(옛 파일 7개 바이트 복사 · 지수 둘은 `Value` 문자열을 네 가격 칸에 그대로 · 거래량 0 — 24,807 · 14,033행). 두 매매법 종료 코드 0 · ERROR 0, 저장소 `storage/` 변경 0. **커밋된 결과와 대조 — 반감기 CSV 20장 같음, 중간선거 8장 중 6장 다름**(계획서 ① 기준 미충족 → 멈춤). 요약 diff 에서 커밋된 결과의 QQQ 가 `1999-03-10 ~ 2026-10-05 · 6,936행`, 지금 파일은 `~ 2026-11-04 · 6,958행`. 원인 가름 — 루트 C(옛 코드 `git archive HEAD` + 같은 옛 파일 이름 그대로)를 돌려 **루트 A ↔ 루트 C CSV 28장(중간선거 8 · 반감기 20) 전부 바이트 같음 → 코드 전환이 바꾼 값 0.** 커밋본 ↔ 루트 C 의 다른 행은 전부 QQQ — 거래내역 3 · 분기내역 4 · 분할매수 2 · 분할매수내역 32 · 진입위치 2 · 측정 1(합 44행씩), 분기 · 성적표는 같음. 중간선거 산출물의 마지막 커밋은 `5a1a916`(2026-10-07)이고 QQQ 수정주가 파일은 그 뒤 `8d5d3b7`(2026-11-06, 역방향 조사의 재수집)에서 바뀌었다 — **커밋된 중간선거 결과가 QQQ 재수집 전 시세로 남아 있던 것**(quant 전환 때의 고원 결과와 같은 모양). 계획 조정 승인 요청
- 2026-11-12 15:38: 사용자 「진행」(조정 A) → 8) Notes 에 기록하고 Phase 2 ① · ② 의 비교 기준을 루트 C 로 고침. ② — 목록 9줄을 scratchpad 루트 B 받는 폴더에 두고 quant-data `python3 scripts/export.py --to …` → 9개 복사 · 매니페스트 커밋 `ef8bd2a…` · 커밋 안 된 변경 `[]` · 기준일 2026-11-10. 파일마다 옛 끝날까지 자름(줄은 글자 그대로) — 9개 모두 **옛 파일과 날짜 목록이 같다**(SPY 8,504 → 8,478 · DIA 7,248 → 7,222 · QQQ 6,962 → 6,958 · ^GSPC 24,833 → 24,807 · ^IXIC 14,059 → 14,033 · BTCUSD 5,564 → 5,523 · Coin Metrics 셋 5,960 → 5,919, 사본에만 · 옛 파일에만 있는 날 0). 두 매매법 종료 코드 0 · ERROR 0 · WARNING 0. **루트 C ↔ 루트 B**(scratchpad `compare.py`): 중간선거 — 측정 · 분기 · 분할매수 3장 같음. 다른 칸은 가격 칸이 대부분 — **DIA** 의 모든 가격 칸이 상대 2.2e-4(새 분배 재조정 비율 0.99978 — 거래내역 진입가 · 청산가 7칸씩 최대 0.0714, 분기내역 42칸, 분할매수내역 226칸, 진입위치 7칸), **SPY · QQQ** 는 6자리 입력을 4자리로 깎은 끝자리 0.0001 뿐(상대 4e-6 이하 — 거래내역 6칸 · 분기내역 14칸 · 분할매수내역 104칸 · 진입위치 2칸). 수익률 칸은 백분율 끝자리 0.01 이 셋 — 성적표 DIA `합계(%)` 1칸 · 분할매수내역 DIA `보유 중 최악(%)` 1칸 · 분기내역 S&P 500 지수 `분기 시작가 대비 최악(%)` 1칸. 반감기 — CSV 20장 중 18장 같음(성적표 · 거래내역 포함), 다른 둘은 `대체일.csv`(33행)와 `크로스체크.csv`(106/107행)의 Coin Metrics 종가와 `차이율(%)` 끝자리 0.01 11칸. 🔴 **발견: 그 두 표의 Coin Metrics 종가는 반올림 없이 나가 사본 6자리가 그대로 실린다**(루트 C 4자리 → 루트 B 6자리 — 전 산출물 칸의 소수 자릿수를 루트 C 와 견줘 4자리를 넘게 바뀐 칸은 이 둘뿐). Q3 「출력 4자리」의 전제가 이 두 칸에서 틀렸다 — 고칠 자리는 반감기 `runner.display_tables` 의 `FIELD_CROSSCHECK` · `FIELD_REPLACED` 두 줄. 범위 추가 승인 요청
- 2026-11-12 16:08: 사용자 「진행」 → 8) Notes 「범위 추가」. 반감기 `runner._rounded_closes`(두 종가를 `PRICE_DECIMALS` 로)를 `display_tables` 의 두 표에 걸고, `TestDataQualityTables.test_두_소스의_종가는_가격_자릿수로_낸다`(기준가를 `× 1.0000123` 해 6자리로 쓴 합성 입력) 추가. **변형 확인**(`PYTHONDONTWRITEBYTECODE=1`) — 수정 상태 1 passed → 두 줄을 반올림 없는 원래 모양으로 되돌리면 1 failed(`Mismatched elements: 2 / 2` · `Max absolute difference among violations: 4.3e-05`) → scratchpad 사본(`runner_fixed.py`)으로 되돌리고 `cmp` 같음 · 1 passed. 고친 runner 로 루트 B · 루트 A 반감기 재실행 — **루트 C ↔ 루트 B 의 남은 차이는 `크로스체크.csv` 의 `차이율(%)` 끝자리 0.01 11칸뿐**(Coin Metrics 6자리 입력으로 차이율이 바뀐 몫), `대체일.csv` 같아짐. 루트 A ↔ 루트 C 는 여전히 20장 바이트 같음(옛 4자리 값은 반올림해도 그대로). **Phase 2 완료**
- 2026-11-12 16:11: **Phase 3.** 옛 시세 CSV 76개(`storage/market` 59 · `storage/series` 17 — 두 폴더에 CSV 말고 다른 파일 0) 삭제 · `storage/series/` 폴더 삭제 · 목록 9줄(`quant_data_files.txt`) · quant-data `python3 scripts/export.py --to ../verify-lab/storage/market` → 9개 복사, 매니페스트 커밋 `ef8bd2a59a37d7984500c61300d030fe5418d32d` · 커밋 안 된 변경 `[]` · 기준일 2026-11-10 · 파일 9개 모두 끝날 2026-11-10 · 상태 「노이즈뿐」. 두 매매법 · 차트(`BROWSER=true`) 종료 코드 0 · ERROR 0 · WARNING 0, 차트 5.6MB. **③ ← ② 대조(기간 연장분)** — 중간선거: 7장 같음(성적표 · 거래내역 포함), `측정.csv` 의 기준선 칸만 4행(SPY · DIA · S&P 500 지수 · 나스닥 종합 지수 — 기준선 신호 · 표본 · 비중첩 +1 = 2026-01 말 진입 → 10월 말 청산이 새로 끝났다, 기준선 비율 최대 0.21%p · 우연확률 2칸. **QQQ 는 옛 끝날이 이미 2026-11-04 라 그대로**). 반감기: 같음 4장(달력연도 · 대체일 · 지표사이클 · 크로스체크), 기준선 모집단 +41일 → `excess`(48/48) · `지표통계`(42/42) · `격자기준선`(120/120) 전 행, 새 표본 — `통계`/`test` 3칸 신호 +1, `거래내역` 767 → 783(+16), `성적표` 90/1290행, `진입내역` 174 → 177, `진입지표` 58 → 59, `지표신호` 3행(옛 데이터 뒤라 비어 있던 진입일 · 진입 종가가 채워짐), 2024 사이클 진행 중 포지션 — `달력분할회차` 1행(새 회차 체결) · `달력분할포지션` 1행(평균 매수가 · 평균 단가 대비 최악 1.78%p) · `달력분할손절` 2행 · `분할회차` 27 · `분할포지션` 405 · `분할조합` 15행. **판정** — 두 매매법 모두 `1차 판정` 이 바뀐 행 0(루트 C → ③ · ② → ③ 둘 다), 새로 생긴 성적표 행 0, 반감기 확정 규칙(`매매 방식 = 월말 분할`) 성적표 10행 ② → ③ 바뀐 행 0, 중간선거 성적표 ② → ③ 같음 → `.claude/rules/trading.md` 「재수집하면 목록을 다시 판단한다」에 걸릴 거리 없음. **Coin Metrics 4자리 출력 손실**(결과 칸 ↔ 사본 6자리) 최대 상대차 **2.030e-05**(`크로스체크.csv` 2011-10-19 `2.217255` → `2.2173`). `git status --short storage/` — 삭제 76 · 결과 수정 26(반감기 CSV 17 + 요약, 중간선거 CSV 7 + 요약) · 새 파일 11(사본 9 · 목록 · 매니페스트). **Phase 3 완료**
- 2026-11-12 16:28: **Phase 4.** 전수 판정(히트 234줄) — **R1**(「관련 파일」의 지운 파일 링크 · 경로): 매매 `결과.md` 둘의 「데이터 수집」 행 → 「데이터」(목록 파일), 조사 10장의 「데이터 수집」 · 「실측 프로브」 · 「지수 수집」 행 → 묘비(`삭제`) 표기. **R2**(재현 방법의 선행 조건): 중간선거 · 반감기 `결과.md`, 역방향 §20.4 · §20.5 · §20.6, 레버리지_ETF_괴리 §19.2, 레버리지_RSI_분할 §15, 선물 「선행 조건」, 연속_등락 · 옵션_만기일 · 월말_진입 · 원달러_ETF_등가성 · 원달러_조달 — 「옛 값은 `git show c3a2641:…` · 새로 잴 때는 quant-data 사본(국내 수정주가는 다른 자료 · 없는 자료는 거기에 받기를 더한다)」. **R3**(붙여 넣을 자리가 통째로 지워진 행): 레버리지_ETF_괴리 · 선물의 `krx_common` · `data/constants` 행(되살리지 않는다), 원달러_ETF_등가성의 `data/constants` 행(`c3a2641` 에서 꺼낸다). **R4**(수집기를 되살려 받으라는 지시): ETN · KRX 선물 수집기 행 → 되살리지 않는다, ECOS · FRED 수집기 행은 ECOS 프로브가 그 모듈을 import 해서(`git show 2faa555:scripts/data/check_ecos.py` — `from verify_lab.data.ecos_collector import …`) 남기고 측정 입력은 quant-data 로, 원달러_조달의 ECOS 재수집 문장. **R5 로 둔 것**: 머리말 데이터 기간 · 재실행 기록 · 실측 기록 · 「확정된 설계 결정」 표의 옛 파일 이름, 문서에 박힌 옛 스크립트 원문(역방향 §20.5 · §20.6 · 레버리지_RSI_분할 §15 — 경로를 인자로 받는다), 커밋을 지정해 꺼내는 목록(만기_말일 §13.1 · 월말_진입 「재현 방법」의 프로브), `reference/`. 확인한 사실 셋을 문서에 넣었다 — 역방향 §20.6 의 지시(「11-05 행이 들어오면 647.05 와 같은지 먼저 대조」)를 quant-data 사본으로 대조해 `2026-11-05` 종가 `647.049988` = 647.05(4자리), 국내 원본가 사본은 열이 셋 더 있다(`BasePrice` · `ChangeRate` · `ListedShares`), 국내 지수 사본은 `Date,Value`. 레버리지_RSI_분할에 처음 적은 「측정 때(2026-11-01) 받은 파일은 … 커밋하지 않았다」는 확인하지 않은 날짜와 사실이라 원문에 있던 사실(「새 폴더로 받으라고 했다」 · 데이터 끝 2026-10-30)로 바로잡음. **규칙 · 안내 문서**: 루트 `CLAUDE.md`(외부 라이브러리 · 기술 환경 · 디렉토리 구조 · reference 절 한 줄 · 스크립트 실행 규칙 — 받기 명령 없음 · 「재수집은 …」 본문에 「다시 내보냈으면 그 사본을 읽는 매매법을 전부 다시 돌린다」와 그 실측(⓪)), `src/verify_lab/CLAUDE.md`(절대 원칙 2 · 데이터 저장 규칙 표 · 조사 프로브 행 → 남은 산출물 행 · 「원시 시세 저장 규칙 — data 와 수집기」 → 「받은 사본 규칙 — data」 · Dataset 이름 행 · 로직의 위치 · 가격 기준의 자리 · 종가 반올림 · 단일 값 시계열 계약 다섯 행), `scripts/CLAUDE.md`(`data/` 행 · 메타 타입 5줄), `tests/CLAUDE.md` 두 줄, `.claude/rules/research.md` 「관련 파일」 안내 한 행, `README.md` 스택, `.gitignore` 주석, `docs/COMMANDS.md`(「데이터 받기」 · 반감기 선행 조건 · 머리말의 「수집기의」), `docs/INDEX.md`(프로브 두 행 코드 칸 `없음` · 표 아래 문단). **근거 승격**: 중간선거 `설계.md` 결정 ㉔ · §3.10, 반감기 `설계.md` 결정 66 · §4.28 · 「데이터 소스」 아래 한 단락, 두 `결과.md` 재실행 기록 · 머리말, 반감기 `결과.md` 「한계」의 Coin Metrics 4자리 항목, 두 `규칙.md` 머리말(반감기는 「재수집하면 다시 판단한다」 — 매도 9 ~ 18개월에 닿는 새 사실 없음), 역방향 §20.7(pykrx 실측 둘을 되살리는 절차). 중간선거 규칙 문서에 처음 쓴 「성적표 · 거래내역은 바뀐 값이 끝자리뿐」은 커밋본 ↔ 최종 대조로 틀린 것을 확인해(DIA 가격 칸 상대 2.2e-4) 「대상 QQQ 의 행은 그대로 · DIA 재조정 · SPY 끝자리」로 바로잡음. ⓪ 의 성격도 대조로 바로잡음 — 가격 끝자리만이 아니라 `측정.csv` 의 QQQ 기준선 +1(QQQ 끝날 10-05 → 11-04)이 함께 들어 있다. **quant-data**: `docs/COMMANDS.md` 「내보내기」에 verify-lab 줄, `docs/research/시세_받기_판정.md` 의 Q21 행에 순서 변경과 3단계 완료 · 7장 첫 줄 삭제. 재판정 — 「관련 파일」 · 「재현 방법」 안의 남은 히트는 전부 R5 이거나 이번에 쓴 안내문, 지운 파일을 가리키는 마크다운 링크 0. **Phase 4 완료**
- 2026-11-12 16:46: **리뷰 1회차.** `/code-review xhigh`(범위 인자 없음) 13건과 quant-data 문서 diff(`diff -u` 사본 ↔ 현재, `general-purpose` 서브에이전트) 3건. 분류 · 조치 —
  ① 반감기 `진입내역` · `지표신호` 의 진입 · 청산 종가도 반올림 없이 나가 대체일(Coin Metrics 6자리)에 진입 · 청산이 오면 6자리가 샌다 — **가벼움 · 거름(기준 1 닿지 않는다)**: 지금 산출물의 최대 소수 자릿수 진입내역 2 · 지표신호 4 · 진입지표 4, 대체일은 Bitstamp 거래량 0 인 날(2011-08 ~ 2015-01 33일)뿐이고 지난 신호일은 미래 참조가 없어 다시 내보내도 움직이지 않는다 — 새 거래량 0 인 날이 진입일과 겹쳐야 생긴다
  ② 새 자릿수 테스트의 `assert_allclose` 가 `rtol` 기본값(1e-7)이라 가격이 약 500 을 넘으면 6자리가 새도 통과 — **그 외(기준 3)**: 막는 결함(출력 자릿수)이 무거움이 아니라 검사 보강은 그 외. 이 픽스처의 대체일 가격(약 240)에서는 변형으로 실패를 확인했다
  ③ 사본 · 목록 · 매니페스트와 결과의 짝(「다시 내보냈으면 전부 다시 돌린다」)을 보는 장치가 없다 — **무거움(비켜 간다 — 막지 못하면 낡은 수치가 에러 없이 커밋된다) · 사용자에게 올림 · 미룬 지적**: 수집 시절에도 없던 장치이고(⓪ 이 그 결과), `tests/CLAUDE.md` 가 테스트의 실제 `storage/` 읽기를 막아 테스트로는 둘 수 없다 — 어디에 둘지(검증 스크립트 · 실행 스크립트)는 설계 결정이다
  ④ 로더를 `is_index` 하나로 골라 국내 지수 사본(`Date,Value`)을 지수 대상으로 더하면 「필수 컬럼 누락」으로 멈춘다 — **가벼움 · 거름(기준 1 · 2)**: 새 대상 정의를 써야 생기고 멈추는 쪽으로만 틀린다
  ⑤ 파일 이름을 `symbol` 로 만들게 바꿨는데 겹침 검사는 `ticker` 만 본다 — **무거움(비켜 간다 — 같은 파일이 두 이름으로 실린다) · 수정**: `test_읽는_파일이_겹치지_않는다` 추가. 변형(`DIA` 의 `symbol` 을 `SPY` 로) → `AssertionError: 두 대상이 같은 파일을 읽습니다` 1 failed → 사본으로 되돌리고 `cmp` 같음 · 1 passed. 같은 모양(경로를 만드는 이름과 겹침 검사의 이름이 다름)은 반감기에 없다(경로와 검사가 둘 다 `ticker`)
  ⑥ `execution/trade_fill.py:347` docstring · `tests/test_execution_trade_fill_scheduled.py:649` 가 「지수는 `storage/series/` … 시가·고가·저가가 없다」 — **그 외 · 고침(계획 범위 — Phase 4 전수 판정이 `.md` 만 봐서 놓쳤다)**. 같은 모양 grep(`.py` 의 `storage/series` · `수집기` · `collect_*` · `_index.csv`) — 이 둘과 ⑧ 말고는 `test_layer_contracts.py` 656 · 1505(「강제하면 수집기가 출력 계층의 상수를 가져오게 된다」 — 가정문이라 둠) · `test_report_writer.py:561`(경로 거부 픽스처)
  ⑦ `tracks.py` 의 프로브 주석이 ECOS 만 코드가 없다고 말한다 — **그 외 · 고침(계획 범위)**
  ⑧ `TestPriceBasis` docstring 이 「수집기 기본값」을 근거로 든다 — **그 외 · 고침(계획 범위)**
  ⑨ 루트 `CLAUDE.md` 에 새로 쓴 「저장소 밖에 있는 것은 내보내기 명령뿐」이 문서가 quant-data 파일을 근거로 가리키는 것과 어긋난다 — **그 외 · 고침(이번에 쓴 문장의 사실 오류)**
  ⑩ 새로 쓴 구현 주석이 전역 규칙(1 ~ 2줄 · 이유 하나 · 간결체)을 어긴다 — **그 외 · 고침**: `common_constants` 의 `MARKET_DIR` · 템플릿 · `PRICE_DECIMALS` · `KST`, 반감기 runner 의 `PUBLICATION_LAG_DAYS`, 반감기 constants 의 대상 주석 끝맺음
  ⑪ 로더의 「시세 파일을 찾을 수 없습니다」가 다음 행동(quant-data 에서 내보낸다)을 말하지 않는다 — **가벼움 · 거름(기준 2 막는 쪽으로만 틀린다)**: 수집 시절부터 같은 문장이다
  ⑫ 조사 문서의 「되살릴 것」 표에 이번에 지운 공통 이름(`SERIES_DIR` · `NAV_FILE_TEMPLATE` · `INDEX_FILE_TEMPLATE`)과 템플릿 값 변경이 없다 — **그 외 · 고침(계획 범위)**: 각 표의 「꺼낸 코드가 지금 없는 이름을 import 할 수 있다 — 지금 공유 계층에 맞춘다」가 그 경우를 받지만, 무엇이 바뀌었는지를 `docs/INDEX.md` 표 아래 문단에 한 번 적었다
  ⑬ `_rounded_closes` 가 `_rounded_prices` 와 같은 일을 한 벌 더 한다 — **그 외(기준 3) · 고치지 않음**
  quant-data — ㉠ `docs/research/합성_시세_연장.md:558` 의 2단계 재료 「verify-lab 의 CD91(1995-01-03 ~, 수집기 지워짐)」이 이번에 지운 파일을 가리킨다 — **가벼움 · 닿는다(2단계 착수) · 수정**: 사본을 뜬 뒤 「1995-01-03 ~ 2026-08-21 · 8,032행 — 수집기와 파일 모두 3단계에서 지웠고 `git show c3a2641:storage/series/CD91.csv` 로 꺼낸다」(기간 · 행 수는 그 커밋에서 확인). 같은 모양 grep — quant-data 문서의 verify-lab 파일 언급은 그 밖에 기록(판정 문서 1장 15행 · Q9)뿐. ㉡ Q21 칸의 순서 표기가 표의 변경 표기 관용과 다르다 — **그 외 · 고치지 않음** ㉢ 「3단계는 2026-11-12 에 끝냈다」가 verify-lab 커밋 전이다 — **그 외** · 두 저장소를 함께 커밋하도록 Done 보고에 넣는다
- 2026-11-12 17:33: **리뷰 2회차(상한).** (16:58 ~ 17:12 에 돌린 것을 세션이 끊긴 뒤 원본 로그에서 이어 받아 적음.) `/code-review xhigh`(범위 인자 없음) 9건과 quant-data 문서 세 장 diff(사본 ↔ 현재, `general-purpose`) 4건. 분류 · 조치 —
  ① 중간선거 `결과.md` 「재현 방법」이 본문 수치(2026-10-07 실행)를 `git show c3a2641:…` 로 「같은 값」 재현한다고 안내하는데, `c3a2641` 의 QQQ 수정주가는 `8d5d3b7`(2026-11-06) 재수집본(6,958행 · ~ 11-04)이고 본문은 `7521cf5` 판(6,936행 · ~ 10-05)이다 — **무거움(위험한 쪽으로 틀린다 — 따르면 QQQ 44행이 에러 없이 다르게 나온다) · 닿는다(지시) · 수정**. 같은 모양 grep(`c3a2641` 과 「재현 · 같은 값 · 꺼낸」) 히트 13줄 — 고침 9(중간선거 `결과.md` 는 `7521cf5` 를 직접 · 조사 여덟 장(원달러_ETF_등가성 · 레버리지_ETF_괴리 · 역방향 §20.4 · 월말_진입 · 선물_대_레버리지_ETF · 원달러_조달 · 연속_등락 · 옵션_만기일)은 「머리말 데이터 기간과 끝날이 같은 판을 `git log -- <파일>` 에서 골라 꺼낸다 — 마지막 판 `c3a2641` 은 측정 뒤 다시 받은 것일 수 있다」) · 맞아서 둠 4(역방향 §20.5 · §20.6 의 11-04 까지 파일 — `9a08eb2` · `8d5d3b7` 과 blob 같음, 역방향의 코드 꺼내기, 반감기 §21.6 · §21.7 의 `7133295` 판). 고치기 전 사본 아홉 장
  ② 반감기 `load_dataset` — 비트코인 시세의 첫 날 · 끝 · 빠진 날 검사가 verify-lab 에서 사라져, 빠진 날이 있는 사본이 오면 월말 회차 · 진입일이 조용히 밀린다 — **무거움 모양(위험한 쪽으로 틀린다) · 닿지 않는다 · 거름(기준 1)**: 그 검사는 옛 코드에서도 로더가 아니라 수집기(받을 때 — `c3a2641:src/verify_lab/data/bitstamp_collector.py` 267행)에 있었고, 지금은 quant-data 가 받을 때 같은 검사를 한다(`src/quant_data/sources/crypto_days.require_complete_range` — 첫 날 · 끝 · 사이 빈틈에서 예외, `bitstamp.py:126` · `coinmetrics.py:122`). 받기 예외는 `--accept`(판정의 비정상만 덮는다)로 덮이지 않아, 빠진 날이 있는 사본은 사본을 손으로 고쳐야만(「받은 사본 규칙」 위반) 생긴다
  ③ 온체인 끝 어긋남으로 멈출 때의 문구 셋(`load_onchain` 두 곳 · `_onchain_gap`)이 「quant-data 에서 다시 내보내세요」라, `--exclude` 로 묵은 계열이면 다시 내보내도 같은 예외가 난다 — **가벼움 · 거름(기준 2 — 멈추는 쪽으로만 틀리고 다음 행동 안내만 모자라다)**
  ④ 반감기 테스트의 합성 기준가가 4자리라 진입내역 · 지표신호 · 진입지표의 종가 칸(반올림 없음)이 대체일과 겹칠 때 6자리로 새는 것을 어떤 테스트도 못 본다 — **1회차 ① 과 같은 모양 · 합침 · 가벼움 · 거름(기준 1)**, 근거는 1회차 ① 그대로. 테스트 보강 몫은 막는 결함이 무겁지 않아 그 외(기준 3)
  ⑤ `_rounded_closes` 가 두 종가만 4자리로 자르고 `차이율(%)` 은 자르기 전 6자리 값으로 둬, 표에 찍힌 두 종가로 다시 계산한 차이율과 0.01 다른 행이 생긴다 — **가벼움 · 닿는다(지금 `크로스체크.csv` 107행 중 11행 · 커밋본 0행) · 수정**: 사본(`runner.py` · 테스트 · 두 문서 · `src/verify_lab/CLAUDE.md` · 산출물)을 뜬 뒤 자른 두 종가로 차이율을 다시 내게 고침. 테스트 `TestDataQualityTables.test_차이율은_표에_찍힌_두_종가로_다시_낸_값이다`(실측 2011-10-19 한 행 — 3.92 · 2.217255) — 고치기 전 코드에서 1 failed(`[76.8] == approx([76.79 ± 1.0e-09])`), 고친 뒤 반감기 runner 테스트 63 passed, **변형**(다시 계산하는 두 줄 제거 · `PYTHONDONTWRITEBYTECODE=1`) → 1 failed(`Mismatched elements: 1 / 1`) → 사본으로 되돌려 `cmp` 같음 · 5 passed. 루트 A · B 의 `src` · `scripts` 를 지금 코드로 맞춰 반감기를 다시 돌림(둘 다 `__path__` · `common_constants` · runner 가 그 루트, 종료 코드 0 · ERROR 0 · WARNING 0) — **① · ② 모두 루트 C 와 CSV 스무 장 같음**(② 에 남던 11칸이 이것이었다). 저장소 반감기 재실행(종료 코드 0 · ERROR 0 · WARNING 0, 저장소 `storage/` 변경 줄 수 113 그대로) — 직전 산출물 대비 `크로스체크.csv` 의 `차이율(%)` 11칸만 바뀜(최대 0.01) · `summary.json` 같음, **`크로스체크.csv` 가 커밋본(`c3a2641`)과 바이트 같음**, ③(루트 B ↔ 저장소)의 같은 넷 그대로. 같은 모양 — diff 안의 반올림 함수는 이것 하나, diff 밖 중간선거 `거래내역.csv` 58행 · `분기내역.csv` 174행은 표 값으로 다시 낸 수익률과 어긋나는 행 0(지금 · 커밋본 둘 다). 문서 — 반감기 `결과.md` 머리말 ② · 「한계」 Coin Metrics 항목, `설계.md` 결정 66(확정 · 탈락안 ④ · 근거) · §4.28 ② 행과 새 줄, `src/verify_lab/CLAUDE.md` 「받은 사본 규칙」 가격 표기 행에 「자른 값에서 나오는 칸은 자른 값끼리 다시 낸다」
  ⑥ `load_close_series` 가 버리는 시가 · 고가 · 저가 · 거래량에도 `load_market_csv` 검사를 걸어 그 칸의 0 · 결측에 지수 축 전체가 멈춘다 — **무거움 모양(죽는다) · 닿지 않는다 · 거름(기준 1)**: quant-data 는 쓰기 전에 모든 시세 파일(`--accept` 로 받아들인 비정상 포함)의 가격 칸 넷(시가 · 고가 · 저가 · 종가)의 결측 · 0 · 음수를 거부한다(`src/quant_data/prices.validate_price_series` · `update._validate_before_write` · `save_prices`). 지금 사본 `^GSPC_raw.csv` 24,833행 · `^IXIC_raw.csv` 14,059행의 가격 칸 0 이하 · 결측 0 (거래량 0 은 5,497 · 3,457행 — 로더가 정상으로 본다)
  ⑦ `TestIndexLoad` 를 `TestDatasetsInvariant` 가운데에 끼워 그 클래스의 테스트 넷(지수만 판정에서 빠진다 · 모르는 이름 · 빈 목록 · 인자 없음)이 지수 로딩 클래스 아래로 옮겨졌다 — **그 외 · 고치지 않음**(사실 확인 — `tests/test_studies_midterm_cycle_runner.py` 225행, 네 테스트는 그대로 돈다)
  ⑧ `docs/INDEX.md` 73행(1회차 ⑫ 가 쓴 문장)이 살아있는 문서에 과거형 변경 이력을 적었다(`.claude/rules/docs.md` 「과거형이 허용되는 자리는 둘뿐입니다」) — **그 외 · 고치지 않음**
  ⑨ `docs/INDEX.md` pykrx 실측 두 행의 「문서」 칸이 `없음` 인데 되살리는 절차는 역방향 §20.7 에 있다(ECOS 실측 행은 그 칸에 문서를 가리킨다) — **그 외 · 고치지 않음**
  quant-data — ㉠ `합성_시세_연장.md` 의 CD91 「수집기와 파일 모두 3단계에서 지웠고」가 틀렸다 — 수집기는 `f26c673`(2026-10-18)에서 먼저 지웠다(`c3a2641` 에 없음 · 마지막은 `2faa555`) — **그 외(1회차 ㉠ 수정이 쓴 문장의 사실 오류) · 고침**(고치기 전 사본) ㉡ Q21 「3단계는 2026-11-12 에 끝냈다」가 verify-lab 커밋 전에는 참이 아니다 — **그 외 · 1회차 ㉢ 과 합침** ㉢ 1장 16행 「방어가 verify-lab 에는 없다」가 현재형 — **그 외 · diff 밖** ㉣ 9장 6.9 재현이 지운 verify-lab 옛 파일을 쓰는데 꺼낼 커밋을 적지 않았다 — **그 외 · diff 밖**
  **수정분 검증 1**(① · ㉠ — hunk 10개, `general-purpose`, 수정분과 겨냥한 지적만 줌): 발견 3 — 무거움 0. (가) 월말_진입 — 분배락용 `069500_adjusted_max.csv` 는 머리말에 줄이 없고 머리말의 KODEX 200 끝날(2026-09-04)과 같은 판이 없어 새 문장대로는 고를 수 없다(판은 `c3130f9` ~ 08-11 · `6199559` ~ 08-26, 고치기 전 `c3a2641` 은 이 파일에 한해 맞는 판이었다) — 막힐 뿐 조용히 틀리지 않는다. 옵션_만기일 §8.5 격자가 수정주가를 읽었다면 같은 모양(서브에이전트가 확인 못 함) (나) 원달러_조달 — 고친 문장이 `git show` 명령 없이 「골라 꺼낸다」로 끝나 덜 구체적 (다) 연속_등락 — 머리말에 실제로 적힌 QQQ 날짜는 재수집 기록(2026-10-05 = `7521cf5`)뿐이라 「머리말 끝날」을 글자 그대로 따르면 그 판을 고를 여지 — 머리말의 데이터 기간 줄이 「§3.1 참고」라 가능성은 낮다. **조치: 고치지 않음**(수정분 검증의 발견) · 거름 — (가) 기준 2(막는 쪽으로만) · (나) 기준 3 · (다) 기준 1(머리말 데이터 기간 줄의 「§3.1 참고」를 건너뛰어야 생긴다). 나머지 hunk 는 머리말 기간 · 행 수와 맞는 판이 git 이력에 있음을 확인(예: 중간선거 `7521cf5` 다섯 파일 SPY 8,478 · DIA 7,222 · QQQ 6,936 · GSPC 24,807 · IXIC 14,033행)
  **품질 검증**(수정분 검증 1 을 기다리는 동안 · ⑤ 수정 전): `validate_project.py` — Ruff 통과 · PyRight 통과 · Pytest passed=1031 · failed=0 · skipped=0. ⑤ 수정 뒤 마지막 Phase 에서 다시 돈다
- 2026-11-12 17:43: ⑤ 수정 뒤 `validate_project.py` — Ruff 통과 · PyRight 통과 · Pytest passed=1032 · failed=0 · skipped=0(새 테스트 1). **수정분 검증 2**(⑤ — hunk 10개 · `runner.py` · 테스트 · 반감기 `결과.md` · `설계.md` · `src/verify_lab/CLAUDE.md`, `general-purpose`, 수정분과 겨냥한 지적만 줌): 회귀 없음 — 문서의 주장(107 · 11 · 76.80 → 76.79 · 커밋본과 바이트 같음 · ① · ② 스무 장 · ③ 같은 넷)을 실제 파일로 확인, 목록에 오르는 날은 자른 값으로 걸렀어도 바뀌는 날 0(가장 작은 |차이율| 5.0139% → 5.0142%), `_rounded_closes` 호출처 2(크로스체크 · 대체일 — 대체일은 차이율 칸이 없어 새 분기를 안 탄다). 발견 4 — 무거움 0, **전부 `c3a2641` 에도 있던 것**: F1 `분할포지션.csv` 의 `수익률(%)` 이 `_rounded_prices` 로 자른 평균 매수가 · 평균 매도가로 다시 계산한 값과 0.01 다른 행 12/2,295(직접 다시 셈 — 커밋본도 12/2,295 · `달력분할포지션.csv` 0/3) — 이번에 `src/verify_lab/CLAUDE.md` 에 쓴 「자른 값에서 나오는 칸은 자른 값끼리 다시 낸다」를 이 표가 어기는 상태 F2 `격자기준선.csv` · `지표통계.csv` 의 기준선 대비 차이 칸이 반올림 전 통계량끼리 뺀 값(평균 · 중앙값 · 오른 · 내린 비율 차이 어긋남 42 · 30 · 8 · 8 / 120, 16 · 8 · 4 · 4 / 42 — 판정에 쓰지 않는 값 · `measure` 공유 계층) F3 `분할조합.csv` 의 `합계(%)` ≠ 사이클별 칸의 합 225/765행(최대 0.01 — 성적표 합계와 같은 관례) F4 반감기 `설계.md` 결정 66 의 「대가」 칸에 탈락안 ④ 의 대가(찍힌 차이율이 6자리로 낸 값과 0.01 다른 행 11)가 없다(§4.28 · `결과.md` 에는 있다). **조치: 고치지 않음**(수정분 검증의 발견) — F1 · F2 · F4 는 사용자에게 올림, F3 은 그 외(기준 3)로 거름. **2회차에 닿는 무거운 버그(①)를 고쳤으므로 규칙대로 멈추고 사용자에게 보고한다** — 3회차 여부와 1회차 ③(사본 ↔ 결과 짝 장치)의 처리를 함께 묻는다
- 2026-11-12 18:07: 사용자 「추천대로 진행」 — **D1** 3회차 돌지 않음 · **D2** 1회차 ③ 을 미룬 지적으로 · **D3** F1 은 계약 문장을 두고 `분할포지션.csv` 위반을 미룬 지적으로 · **D4** F2 · F3 고치지 않음(사용자가 받아들임 — 옮기지 않음) · **D5** 그 외 넷(⑦ ⑧ ⑨ F4)을 한 묶음으로 고치고 수정분 검증. D5 — 사본(`tests/test_studies_midterm_cycle_runner.py` · `docs/INDEX.md` · 반감기 `설계.md`)을 뜬 뒤 ⑦ `TestIndexLoad` 를 `TestDatasetsInvariant` 끝 뒤(`TestStatisticsAssembly` 앞)로 옮김(수집 결과 `TestDatasetsInvariant` 8 · `TestIndexLoad` 1) ⑧ INDEX 표 아래 문단을 현재형으로(지금 없는 이름 · 지금 템플릿 값 · 되살린 코드가 맞출 것) ⑨ pykrx 실측 두 행의 「문서」 칸을 `[역방향.md](조사/역방향.md) 「재현 방법」` 으로(두 프로브는 `tracks.py` 에서 조사 등급) F4 결정 66 「대가」 칸에 탈락안 ④ 의 대가(11/107행). 같은 모양 — ⑦ 이번 diff 의 새 테스트 클래스는 이것 하나, ⑧ 이번에 더한 살아있는 규칙 · 안내 문서 줄의 과거형 후보 둘은 현재 상태(「프로브 코드는 지웠고」)와 `[실측]` 근거라 해당 없음, ⑨ INDEX 의 다른 `없음` 행 없음. 관련 테스트(중간선거 runner · `test_index` · `test_research_docs` · `test_tracks`) 183 passed. **미룬 지적 옮김** — `docs/DEFERRED_FINDINGS.md` 에 둘: 「받은 사본과 커밋되는 결과가 짝인지 보는 장치가 없다」(무거운 버그 — 1회차 ③) · 「반감기 `분할포지션.csv` 의 수익률이 표에 찍힌 평균 매수가 · 평균 매도가와 어긋난다」(가벼운 버그 — 2회차 수정분 검증 F1, 12/2,295행이 모두 반감기 2012-11-28 · `책 고정` 의 같은 가격 쌍임을 다시 셈). **자동 포맷** — `black --check` 바꿀 파일 0 · `black .` 92 files left unchanged. **최종 재실행** — 두 매매법 인자 없이 · 반감기 차트(`BROWSER=true`) 모두 종료 코드 0 · ERROR 0 · WARNING 0, 산출물이 재실행 전 사본과 바이트 같음(`meta.json` 제외), `git diff --stat storage/results/` 25개 파일(Phase 3 의 26 에서 `크로스체크.csv` 가 커밋본과 같아져 빠짐), `git status --short storage/` 삭제 76 · 수정 25 · 새 파일 11. **품질 검증** — Ruff 통과 · PyRight 통과 · Pytest passed=1032 · failed=0 · skipped=0
- 2026-11-12 18:20: **수정분 검증 3**(D5 — ⑦ ⑧ ⑨ F4 · hunk 5개, `general-purpose`, 수정분과 겨냥한 지적만 줌): 회귀 없음 — ⑦ AST 대조로 함수 21개 본문 같음 · 클래스가 바뀐 것은 지목한 넷뿐 · 17 passed, ⑨ 링크 실재 · 등급(조사)이 `tracks.py` 와 맞음 · 역방향 §20.7 이 두 프로브의 절차를 갖고 `c3a2641` 의 두 스크립트 import 와 그 목록이 맞음, ⑧ 새 문단의 사실(지금 없는 이름 셋 · 템플릿 값 77 · 78행 · `c3a2641` 의 옛 정의)이 맞음, F4 의 107 · 11 을 사본 6자리로 다시 셈(표에 찍힌 값끼리는 107/107 같음 · 6자리로 낸 값과 11행이 정확히 0.01 다름). 발견 2 — 무거움 0, 둘 다 그 외: (가) `src/verify_lab/CLAUDE.md` 「조사 프로브의 남은 산출물」 행의 「프로브 코드는 지웠고」가 과거형 (나) 조사 문서 「재현 방법」에 이번에 들어간 「그때의 파일은 2026-11-12 … 지웠다」 류 15줄이 `docs.md` 의 과거형 허용 자리 밖 — `c3a2641` 의 조사 문서 아홉 장에 같은 꼴이 관용으로 있다. **조치: 고치지 않음 · 거름(기준 3)** — 서브에이전트의 제안(관용을 `docs.md` 에 세 번째 허용 자리로 적거나 현재형으로 고치기)은 Done 보고에 사용자 판단 거리로 낸다. **근거 승격 점검** — 결정 · 근거는 중간선거 `설계.md` 결정 ㉔ · §3.10, 반감기 `설계.md` 결정 66 · §4.28, 두 `결과.md` 머리말 · 재실행 기록 · 반감기 「한계」, `src/verify_lab/CLAUDE.md` 「받은 사본 규칙」 · 「단일 값 시계열 계층 계약」, 미룬 지적 둘은 `docs/DEFERRED_FINDINGS.md`, Q7 의 MEMORY 예외는 커밋 메시지에 있다. 비목표인 루트 `CLAUDE.md` 원칙 14 ③(국내 수정주가 3,000거래일)은 사실 쪽이 조사 문서 「재현 방법」(국내 수정주가는 KRX 기준가로 이은 다른 자료)과 quant-data 판정 문서에 있고, 「2단계 때 그 문장을 고친다」는 할 일만 이 계획서에 남는다 — 할 일 문서를 두지 않는 규칙(전역 「개인 프로젝트 공통」)대로 Done 보고에 한 줄로 낸다. **Done 처리** — 체크박스 확정 뒤 `/commit` 후보를 옮긴다
