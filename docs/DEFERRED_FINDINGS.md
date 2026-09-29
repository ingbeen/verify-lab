# DEFERRED_FINDINGS — 미룬 지적

> 코드 리뷰가 낸 지적 중 **계획서가 고치지 않은 것**을 모은다. 이 저장소의 판단 대기열이다.
> 무엇을 어떻게 추려 어떤 모양으로 옮기는지는 전역 `/impl-plan` 스킬 「미룬 지적 옮기기」가 SoT 다.
>
> **이 파일을 처리할 때는 먼저 그 절의 「처리」 순서를 따른다** — 항목마다 지금 코드에서 재현 → 재현 결과와
> 추천을 표로 → **고칠지는 사용자가 고른다.** 테스트를 고치면 `tests/CLAUDE.md` 「테스트 보강」대로 변형해
> 실패를 확인한다. 버린 항목은 바로, 고친 항목은 그 계획서가 Done 될 때 지운다 — 판단 전이거나 고치는 중인 것만 남는다.
>
> 항목은 계획서 없이 읽히게 쓴다. 계획서는 지워지므로 **출처는 이름과 날짜만 평문으로** 적는다.
> 줄 번호는 옮긴 시점의 값이다 — 밀렸으면 함수·테스트 이름으로 다시 찾는다.

---

## 테스트

줄 번호 기준: PLAN_deferred_tests_midterm_notes 완료 시점의 작업 트리 (2026-09-29 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `tests/test_studies_midterm_cycle_trading.py:318` `TestStopNotes.test_price_stop_note_sits_right_before_the_sample_note` | `NOTE_STOP_BASE` 가 `NOTE_SAMPLE` **바로 앞**인지만 본다 — 두 문구를 짝째로 `NOTE_DIVIDEND` 뒤로 옮기면 `TestStopNotes` 4건이 모두 통과하는데, `--stop-grid` 실행의 `summary.json` 은 좁히기 전 산출물과 바이트 동일하지 않게 된다(결과 문서 재실행 기록이 그 동일성을 적는다). `NOTE_STOP_BASE` 가 맨 끝이면 단언 메시지 대신 `IndexError` 가 난다(`:334`). 실제 격자 산출물의 순서는 맞다(2026-09-29 대조) | 가벼운 버그 | PLAN_deferred_tests_midterm_notes (2026-09-29) 리뷰 1회차 |
| `tests/test_measure_screening.py:385` `TestSingleOwner._called_names` | 호출 노드의 이름만 봐, `periods.py` 에 같은 이름의 지역 함수 `def screen_verdict(...)` 를 두고 비교를 다시 써도 `test_성적_산식_계층이_이_게이트를_쓴다` 가 통과한다(그 전의 소스 문자열 검사도 같았다). 반대로 `import screen_verdict as verdict` 로 부르면 거짓 실패한다. 지금 `periods.py` 는 `measure.screening` 에서 가져와 부른다 | 가벼운 버그 | PLAN_deferred_tests_midterm_notes (2026-09-29) 리뷰 1회차 |
| `tests/test_studies_midterm_cycle_trading.py:285` `TestStopNotes` | `NOTE_STOP_CONFIRMED` 의 **내용**(1배 측정 기준이 대상 QQQ 의 무손절 행 · QLD 성적은 산출물에 없음)을 보는 테스트가 없다 — 테스트가 프로덕션 상수를 import 하므로 문구를 옛 것으로 되돌려도 전체가 통과하고, 재실행 뒤 `summary.json` diff 로만 드러난다 | 그 외 | PLAN_deferred_tests_midterm_notes (2026-09-29) 리뷰 1회차 |
| `tests/test_measure_screening.py:345` `TestSingleOwner.test_게이트의_기준값과_판정_값을_소유자_밖에서_쓰지_않는다` 의 `offenders` | `used - self.GATE_OWNERS.get(path, frozenset())` 를 파일마다 두 번(거르는 조건과 값) 계산한다 — 허용 목록 조회가 두 벌이다 | 그 외 | PLAN_deferred_tests_midterm_notes (2026-09-29) 리뷰 1회차 |

### 반감기_사이클 데이터 계층 (비트코인 수집 · 크로스체크)

줄 번호 기준: PLAN_halving_cycle_data 완료 시점의 작업 트리 (2026-09-29 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `tests/test_data_crosscheck.py:80` `test_yearly_summary_counts_and_extremes` | 연도별 요약의 **95분위(`COL_P95_ABS_DIFF`)를 단언하지 않는다** — `abs_diff.quantile(_P95)` 를 다른 분위나 `interpolation="higher"`, 부호 있는 차이로 바꿔도 전부 통과하는데, 수집 화면과 `docs/검증/반감기_사이클/설계.md` §4.3 표의 「95분위」 열이 조용히 바뀐다 | 그 외 | PLAN_halving_cycle_data (2026-09-29) 리뷰 1회차 |
| `tests/test_coinmetrics_collector.py:174` `test_time_off_utc_midnight_is_rejected` | 12:00Z 만 넣어 **날짜가 실제로 밀리는 입력**(`"2010-07-18T00:00:00+09:00"` — 검사가 없으면 2010-07-17 로 저장된다)을 고정하지 않는다. 코드는 그 입력도 막는다(수정분 검증에서 확인) | 그 외 | PLAN_halving_cycle_data (2026-09-29) 수정분 검증 (2회차 수정) |
| `tests/test_bitstamp_collector.py:201` `test_latest_bar_returned_for_a_future_start_ends_the_history` docstring | 「설계 문서 결정 ⑪ 탈락안 ③」 — 같은 날 결정 ⑪ 의 탈락안을 다시 번호 매겨 「빈 페이지가 올 때까지 돈다」는 **④** 가 됐다 | 그 외 | PLAN_halving_cycle_data (2026-09-29) 수정분 검증 (마지막 수정) |
| `tests/test_coinmetrics_collector.py:10` 모듈 docstring 3번 | 「빠진 날을 메우지 않고 센다」 — 수집기는 이제 빠진 날이 있으면 **저장하지 않고 예외**를 낸다(`crypto_common.require_complete_range`) | 그 외 | PLAN_halving_cycle_data (2026-09-29) 수정분 검증 (마지막 수정) |
| `tests/test_coinmetrics_collector.py:412` `test_collect_rejects_value_that_is_not_a_finite_positive` docstring | 「무한대면 그 날의 대조가 무한대가 된다」 — 크로스체크는 `Bitstamp ÷ Coin Metrics − 1` 이라 분모가 무한대면 **−1.0(−100%)** 이 된다. 검사는 옳고 이유 설명만 틀렸다 | 그 외 | PLAN_halving_cycle_data (2026-09-29) 수정분 검증 (마지막 수정) |

### 반감기_사이클 측정 · 체결 (반감기 경과 격자 · 무손절 체결)

줄 번호 기준: PLAN_halving_cycle_measure 완료 시점의 작업 트리 (2026-09-29 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `tests/test_studies_halving_cycle_calendar.py:566` `TestLookAhead.test_기준선_수익률이_뒤_데이터에_기대지_않는다` | 옆의 두 look-ahead 테스트와 달리 `assert not measured.empty` 가드가 없다 — 짧은 입력에서 기준선 칸이 전부 제외되도록 바뀌면(보유 개월 · 자르는 날 변경 등) 빈 배열끼리 비교해 통과하고, 필수 미래 참조 감시가 아무것도 검사하지 않는다 | 그 외 | PLAN_halving_cycle_measure (2026-09-29) 리뷰 1회차 · 2회차 |
| `tests/test_studies_halving_cycle_trading.py:63` `_dataset` | 합성 시세에 거래량 0 인 날이 없어(`COL_VOLUME: 1_000.0`) 「체결 = 측정과 같은 가격」 계약이 종가를 바꾼 날에서는 검사되지 않는다 — `run_halving_cycle_trading` 이 `load_dataset(...).frame` 대신 원시 시세(`load_crypto_market_csv`)를 읽게 바뀌어도 전부 통과한다 | 그 외 | PLAN_halving_cycle_measure (2026-09-29) 리뷰 2회차 |
| `tests/test_execution_trade_rows.py:5` 모듈 docstring | 「세 번째가 와서 올렸다」 — `**/*.py` 는 현재형이어야 하는 자리다(`.claude/rules/docs.md` 「과거형이 허용되는 자리는 둘뿐입니다」). 같은 문장을 프로덕션 `execution/trade_rows.py` 에서는 고쳤다 | 그 외 | PLAN_halving_cycle_measure (2026-09-29) 수정분 검증 (마지막 수정) |
| `tests/test_studies_halving_cycle_runner.py:253` `test_우연확률은_표본_부족으로_검정하지_않는다` docstring | 표본 하한을 숫자로 적었다(「하한(10)」). 값은 `tests/test_measure_statistics.py` 가 고정하고 `tests/test_execution_periods.py:198` 에도 같은 관용이 있어 받아들일 만하다 | 그 외 | PLAN_halving_cycle_measure (2026-09-29) 수정분 검증 (마지막 수정) |


## 코드

줄 번호 기준: PLAN_deferred_tests_midterm_notes 완료 시점의 작업 트리 (2026-09-29 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `src/verify_lab/studies/midterm_cycle/trading.py:1006` `run_midterm_cycle_trading` 의 `notes` 조립 | 손절선 설명 문구 둘을 실제로 돈 손절선이 아니라 **입력 플래그**(`stop_grid` · `is_index`)로 고르고, `NOTE_STOP_CONFIRMED` 는 `STOP_LEVELS_ETF_CONFIRMED` 가 무손절 하나라는 사실을 문구에 박아 둔다. 확정 규칙이 가격 손절(예: `(0.25,)`)로 바뀌면 기본 실행이 −25% 를 걸고도 「무손절 한 종만 낸다」를 싣고 `NOTE_STOP_BASE` 를 빠뜨리며, `TestStopNotes` 도 같은 가정이라 통과한다. 리뷰 제안: `NOTE_STOP_BASE` 는 ETF 에 숫자 손절선이 하나라도 돌았는지로, `NOTE_STOP_CONFIRMED` 는 `STOP_LEVELS_ETF_CONFIRMED` 가 무손절 하나인지로 가른다. 지금 `is_index` 로 가른 것은 바로 아래 문구들과 같은 관용이라서이고, 성적표의 `stop_levels_run` 에 숫자가 있는지로 가르는 안은 표시값 형식(`stop_level_value`)에 기대게 돼 택하지 않았다. 확정 규칙이 무손절이라 지금은 발동하지 않는다 | 가벼운 버그 | PLAN_deferred_tests_midterm_notes (2026-09-29) 리뷰 1회차 |
| `src/verify_lab/studies/midterm_cycle/trading.py:220` `NOTE_STOP_CONFIRMED` | 확정 규칙의 대상(QQQ) · 상품(QLD) · 절 번호(§2.5) · 등급이 든 문서 경로(`docs/매매/…`)를 산출물 문구에 박았고, ETF 가 하나라도 돌면 싣는다 — `--ticker SPY` 로 돌리면 그 산출물에 없는 「대상 QQQ 의 무손절 행」을 가리킨다. 대상 · 절 번호 · 등급이 바뀌면 커밋된 `summary.json` 이 조용히 낡는다(테스트는 상수를 import 해 따라간다). 기본 산출물은 QQQ 를 담아 지금은 맞다 | 가벼운 버그 | PLAN_deferred_tests_midterm_notes (2026-09-29) 리뷰 1회차 |
| `src/verify_lab/studies/midterm_cycle/trading.py:1006` 격자 실행의 `notes` | QLD 경고가 기본 실행 문구에만 있다 — `--stop-grid` 실행(결과 문서 §12 격자 표의 출처)에는 「규칙은 QLD 를 사고, 1배 손절선 행이 거기 그대로 옮겨지지 않는다」는 말이 없어, −25 · −30% 행이 무손절과 같다는 것을 QLD 규칙에 그대로 적용해 읽을 수 있다(QLD 는 2018 보유 중 −41.95%). 격자 실행을 좁히기 전 산출물과 바이트 동일하게 두려고 문구를 더하지 않았다 | 그 외 | PLAN_deferred_tests_midterm_notes (2026-09-29) 리뷰 1회차 |
| `src/verify_lab/studies/midterm_cycle/trading.py:1006` · `:1009` | ETF 가 있는지(`any(not dataset.is_index for dataset in datasets)`)를 두 번 계산한다 — 한 번 묶어 두면 손절·배당 문구 셋의 조건이 한 판단으로 읽히고, 조건이 바뀔 때 갈라지지 않는다 | 그 외 | PLAN_deferred_tests_midterm_notes (2026-09-29) 리뷰 1회차 |

### 반감기_사이클 데이터 계층 (비트코인 수집 · 크로스체크)

줄 번호 기준: PLAN_halving_cycle_data 완료 시점의 작업 트리 (2026-09-29 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `src/verify_lab/data/loader.py:61` `validate_market_data` | **공유 시세 검증기가 시가 · 고가 · 저가의 무한대와 거래량을 보지 않는다.** 무한대는 종가만 `pct_change` 로 걸리고(한 행이거나 종가가 전부 무한대면 그것도 통과), 거래량은 빈 값 · 무한대 · 음수가 모두 통과해 수집기가 저장하고 `load_market_csv` 가 읽는다. 재현: 2020-01-01 ~ 03 · OHLC 10 · 종가 [10, 10.1, 10.2] · 거래량 1 에서 `High[1]=inf` 또는 `Volume[1]=nan` → `validate_market_data(frame, max_daily_change_rate=0.75)` 가 통과. 크로스체크의 「거래량 0 인 날」 목록도 빈 거래량을 놓친다. **모든 시세 파일(주식 · ETF 포함)에 걸리는 공유 계층의 틈**이라 고칠 때 기존 시세 파일 전수 대조가 필요하다. 실제 비트코인 파일(5,521행)에는 무한대 · 빈 거래량 0 | 버그 — 검사 우회 (사용자가 미루기로 함) | PLAN_halving_cycle_data (2026-09-29) 리뷰 1회차 · 수정분 검증 (마지막 수정) |
| `scripts/data/collect_btc.py:178` `main` | Bitstamp 를 **저장한 뒤에** Coin Metrics 를 받는다 — Coin Metrics 가 실패하면(HTTP 429 · 공개 지연이 하루를 넘어 끝 확인에 걸림 등) Bitstamp 파일만 갱신되고 크로스체크와 실행 이력 기록이 돌지 않는다. 예외는 난다(시끄럽게 실패). 리뷰 제안: 두 소스를 받고 검증까지 마친 뒤에 둘 다 쓴다. 실제 실패 0회 | 가벼운 버그 | PLAN_halving_cycle_data (2026-09-29) 리뷰 1회차 · 2회차 |
| `src/verify_lab/data/bitstamp_collector.py:181` `parse_ohlc_rows` · `src/verify_lab/data/coinmetrics_collector.py:208` `parse_metric_rows` | Bitstamp 는 같은 봉 시각 중복을 `keep="first"` 로 **건수도 경고도 없이** 버린다(값이 다른 중복이면 어느 값을 버렸는지 모른다). Coin Metrics 는 날짜 중복을 빼지 않아 저장 행 수가 부풀고, 로더가 나중에 경고와 함께 뺀다(`load_series_csv`) — 로더의 「중복 제거 + 경고 + 건수」 관용과 다르다. 실제 Coin Metrics 중복 0, Bitstamp 원 응답은 남기지 않아 셀 수 없다 | 가벼운 버그 | PLAN_halving_cycle_data (2026-09-29) 리뷰 1회차 · 2회차 |
| `src/verify_lab/data/coinmetrics_collector.py:201` `fetch_metric_rows` | 진행 검사가 「다음 URL 이 방금 URL 과 같은가」 하나뿐 — A ↔ B 로 번갈거나 빈 `data` 에 새 토큰만 주면 끝나지 않는다(429 가 날 때까지). Bitstamp 처럼 페이지마다 날짜가 앞으로 가는지 보면 막힌다. 실제 응답은 한 페이지 | 가벼운 버그 | PLAN_halving_cycle_data (2026-09-29) 리뷰 2회차 |
| `src/verify_lab/data/coinmetrics_collector.py:233` `parse_metric_rows` | `time` 이 비었거나 없는 행이 「UTC 자정이 아닌 시각」 문구로 거부된다(`NaT != NaT` 가 참) — 막히는 방향은 맞고 문구만 틀린다 | 가벼운 버그 | PLAN_halving_cycle_data (2026-09-29) 수정분 검증 (2회차 수정) |
| `src/verify_lab/data/crypto_common.py:106` `require_complete_range` | 빈 날 검사는 **시각**으로, 첫 · 끝 검사와 `count_missing_days` 는 **날짜**로 비교한다 — 자정이 아닌 시각이 섞이면 있는 날을 「빠진 날」로 짚고 `count_missing_days` 와 답이 갈린다. 재현: `pd.to_datetime(["2026-09-26 00:00", "2026-09-27 05:00", "2026-09-28 00:00"])` 가 「빠진 날 1일(2026-09-27)」. 두 수집기는 `date` 객체만 넘겨 지금은 일어나지 않는다 | 가벼운 버그 | PLAN_halving_cycle_data (2026-09-29) 수정분 검증 (마지막 수정) |
| `src/verify_lab/data/bitstamp_collector.py:76` · `src/verify_lab/data/coinmetrics_collector.py:47` · `src/verify_lab/data/fred_collector.py:38` | HTTP 요청(`urllib` · User-Agent · 제한 시간 · `HTTPError`/`URLError` → `ValueError`)과 상수 `USER_AGENT`(세 벌) · `REQUEST_TIMEOUT_SECONDS`(`ecos_collector.py:56` 까지 네 벌)가 수집기마다 복사돼 있다 — 「한 계층 내 2개 이상 파일에서 사용 → `<계층>/constants.py`」(`src/verify_lab/CLAUDE.md` 「상수 관리」). 한 소스의 제한 시간만 바꾸면 나머지와 조용히 갈린다 | 그 외 | PLAN_halving_cycle_data (2026-09-29) 리뷰 1회차 · 2회차 |
| `src/verify_lab/data/loader.py:105` `validate_market_data` 오류 문구 | 임계값을 `:.0%` 로 찍어 정수 퍼센트가 아닌 값은 반올림돼 보인다(0.755 → 「임계: 76%」인데 +75.8% 를 거부) | 그 외 | PLAN_halving_cycle_data (2026-09-29) 리뷰 2회차 |
| `scripts/data/collect_btc.py:184` · `:149` | Coin Metrics 결과를 돈 뒤 `next(...)` 로 가격 계열을 다시 찾는다(`BTC_PRICE_SERIES` 를 바로 받으면 되고 `StopIteration` 경로도 사라진다) · `reindex(abs().sort_values().index)` 는 `sort_values(COL_DIFF_RATE, key=abs, ascending=False)` 와 같다 | 그 외 | PLAN_halving_cycle_data (2026-09-29) 리뷰 2회차 |
| `src/verify_lab/data/coinmetrics_collector.py:289` 5-1 주석 | 「무한대면 그 날의 대조가 무한대가 되며」 — 분모가 무한대라 실제로는 −100% 다(위 테스트 docstring 과 같은 지적) | 그 외 | PLAN_halving_cycle_data (2026-09-29) 수정분 검증 (마지막 수정) |
| `src/verify_lab/data/bitstamp_collector.py:200` `fetch_ohlc_history` docstring · `scripts/data/collect_btc.py:126` 표 제목 | 「`require_complete_range` 가 양 끝을 본다」 — 이제 사이의 빠진 날도 본다. 표 제목 「빠진 날은 메우지 않았다」는 빠진 날이 있으면 애초에 저장하지 않으므로 그 열이 늘 0 이라는 사실과 어긋난다 | 그 외 | PLAN_halving_cycle_data (2026-09-29) 수정분 검증 (마지막 수정) |

### 반감기_사이클 측정 · 체결 (반감기 경과 격자 · 무손절 체결)

줄 번호 기준: PLAN_halving_cycle_measure 완료 시점의 작업 트리 (2026-09-29 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `src/verify_lab/studies/halving_cycle/price_series.py:89` `replace_zero_volume_closes` | 종가만 대조 값으로 바꾸고 이월된 시가 · 고가 · 저가를 두어 **종가가 그날의 [저가, 고가] 밖**에 놓인다 — 실측 2011-09-09 종가 4.9868 · 저가 7.4, 2015-01-07 종가 297.54 · 고가 276.8. 그날 청산하는 체결이 생기면 `trade_fill._worst_hold_rate` 가 이월 저가(아래로 걸면 이월 고가)로 재어 **보유 중 최악이 수익률보다 좋게** 나오고 「보유 중 최악 <= 수익률」이 예외 없이 깨진다. 계획이 「시가 · 고가 · 저가는 받은 그대로」로 받아들인 모양이고, 실제 신호의 진입 · 청산일에 대체일은 0건(기준선 18행만 닿는다) | 가벼운 버그 | PLAN_halving_cycle_measure (2026-09-29) 리뷰 1회차 · 2회차 |
| `src/verify_lab/studies/halving_cycle/runner.py:358` `_aggregate` | 진입이 0건인 진입 개월을 만나면 `ValueError` 로 실행 전체를 멈춘다 — 체결 `trading._run_cell` 은 같은 빈 칸에도 시기 5행을 남기게 짜여 두 계층의 빈 칸 처리가 반대다. 시세가 2016-08-28(첫 반감기 + 45개월) 전에 끝나는 입력이면 측정이 먼저 죽는다. 실제 16개 진입 개월 모두 3 ~ 4건 | 가벼운 버그 | PLAN_halving_cycle_measure (2026-09-29) 리뷰 1회차 |
| `src/verify_lab/studies/halving_cycle/halving_calendar.py:155` `halving_entries` 의 `continue` | 데이터 뒤의 진입(2024 사이클 30 ~ 45개월 6건)을 행 없이 건너뛰는데(설계 결정 ⑯) **건수가 요약 · 산출물 어디에도 없다** — 30 ~ 45개월 칸이 `신호 3` 으로만 보여 「사이클이 셋뿐」과 「넷째가 아직 안 왔다」가 산출물만으로 구별되지 않는다 | 그 외 | PLAN_halving_cycle_measure (2026-09-29) 리뷰 1회차 · 2회차 |
| `src/verify_lab/studies/halving_cycle/halving_calendar.py:80` `_positions` | `execution/trade_fill.resolve_positions` 와 예외 타입(`ValueError` 대 `RuntimeError`)만 다른 사본이고, 중간선거 `cycle_calendar.py:294` 에도 같은 검사가 인라인으로 있어 세 벌이다 — `src/verify_lab/CLAUDE.md` 는 「어느 위치가 유효한가」의 소유자를 `trade_fill.py` 하나로 둔다. 리뷰 제안: 예외 타입을 고르는 인자 또는 일정 모듈 공용 변환 | 그 외 | PLAN_halving_cycle_measure (2026-09-29) 리뷰 1회차 · 2회차 |
| `src/verify_lab/studies/halving_cycle/trading.py:228` · `:142` | CLI 한 번에 `run_study` 와 `run_halving_cycle_trading` 이 각각 `load_dataset` · `signal_returns` 를 돌아 CSV 두 개를 두 번 읽고 크로스체크 · 종가 대체를 두 번 계산한다. `_run_cell` 은 칸마다 거래일 목록을 다시 만든다(48회). 중간선거_사이클도 같은 모양 | 그 외 | PLAN_halving_cycle_measure (2026-09-29) 리뷰 1회차 · 2회차 |
| `scripts/run_halving_cycle.py:140` `_print_candidates` | `run_midterm_cycle.py` 의 같은 함수를 거의 그대로 복제했다 — 후보 필터가 CLI 마다 사본으로 쌓이고, 새 매매법 CLI 마다 `tests/test_measure_screening.py` 의 `GATE_OWNERS` 에 한 줄씩 더해야 한다 | 그 외 | PLAN_halving_cycle_measure (2026-09-29) 리뷰 1회차 |
| `src/verify_lab/studies/halving_cycle/runner.py:435` · `trading.py:150` · `trading.py:276` | 방향 식 `DIRECTION_DOWN if BET_DOWN else DIRECTION_UP` 이 여러 곳에서 되풀이된다 — 한 곳만 바뀌면 측정 표와 성적표의 `방향` 이 어긋나 1:1 조인이 조용히 깨진다. 리뷰 제안: `constants.py` 에 방향 값 하나 | 그 외 | PLAN_halving_cycle_measure (2026-09-29) 리뷰 1회차 |
| `src/verify_lab/studies/halving_cycle/runner.py:487` · `trading.py:273` | 반감기 넷 · 진입 개월 · 보유 개월이 측정 요약과 체결 `rule` 에 똑같이 두 벌 실린다 — 한쪽 생성만 바뀌면 `summary.json` 안에서 두 값이 갈라져도 예외가 없다 | 그 외 | PLAN_halving_cycle_measure (2026-09-29) 리뷰 1회차 |
| `src/verify_lab/studies/halving_cycle/runner.py:450` `run_study` | 칸 표 셋에 방향 컬럼을 **숫자 자리 3** 에 넣는다 — `_aggregate` 의 `cells()` 가 앞에 두는 컬럼이 늘거나 바뀌면 방향이 엉뚱한 자리에 조용히 들어가고, 앞 네 칸 순서를 고정하는 테스트가 없다(`tests/test_studies_halving_cycle_runner.py` 는 컬럼이 있는지만 본다) | 그 외 | PLAN_halving_cycle_measure (2026-09-29) 리뷰 2회차 · 수정분 검증 (2회차 수정) |
| `src/verify_lab/studies/halving_cycle/constants.py:467` `KEY_HEIGHT` · `KEY_BLOCK_TIME` · `KEY_DATE` | `runner.py` 한 파일에서만 쓰는데 패키지 `constants.py` 에 있다 — 「1개 파일에서만 사용 → 해당 파일 상단」(`src/verify_lab/CLAUDE.md` 「상수 관리」) | 그 외 | PLAN_halving_cycle_measure (2026-09-29) 리뷰 2회차 |
| `src/verify_lab/studies/halving_cycle/trading.py:85` · `:88` · `:89` · `price_series.py:69` | black 이 한 줄로 합친 암묵 문자열 연결(`"… " "…"`)이 남아 있다 — 이음매에서 공백을 빠뜨리기 쉽다. 문자열 하나로 합치면 된다 | 그 외 | PLAN_halving_cycle_measure (2026-09-29) 리뷰 2회차 |
| `scripts/run_halving_cycle.py:88` 설명 · `trading.py:85` `NOTE_INDEPENDENCE` | 격자 값(0 ~ 45개월 · 3개월 간격 · 3 · 6 · 12개월 · 48칸)을 상수가 아니라 글자로 적었다 — `ENTRY_MONTHS` · `HOLD_MONTHS` 가 바뀌면 `--help` 와 `summary.json` 의 `notes` 가 거짓이 된다(전역 「구체적 수치와 가변 정보를 직접 적지 않는다」). 같은 파일의 하한 리터럴(10)은 고쳤다 | 그 외 | PLAN_halving_cycle_measure (2026-09-29) 리뷰 2회차 |
| `src/verify_lab/execution/trade_rows.py:6` 모듈 docstring | 「세 번째가 오면 공유 계층에 둔다」가 「셋이 되면 자동으로 올린다」로 읽힌다 — `src/verify_lab/CLAUDE.md` 는 「세 번째가 올 때 정합니다」 · 「개수는 판단 기준이 아닙니다」라고 적는다. 「세 번째가 오면 정하고, 이 여덟 칸은 공유 계층이 갖는다」 정도가 정확하다 | 그 외 | PLAN_halving_cycle_measure (2026-09-29) 수정분 검증 (마지막 수정) |


## 문서

줄 번호 기준: PLAN_deferred_tests_midterm_notes 완료 시점의 작업 트리 (2026-09-29 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `docs/매매/중간선거_사이클/결과.md:84` §1 한 줄 요약 | QLD 수치(2018 보유 중 −41.95%)를 인용하는데 머리말의 데이터 기간에 QLD 가 없다 — `.claude/rules/docs.md` 「수치를 적을 때는 데이터 기간을 함께 적는다」(파일이 여럿이면 파일마다). QLD 기간은 `규칙.md` 머리말에 있다(2006-06-21 부터) | 그 외 | PLAN_deferred_tests_midterm_notes (2026-09-29) 리뷰 1회차 — 같은 날 미룬 지적을 처리하며 직접 고친 문장 |
| `.claude/rules/trading.md:126` 「기간 손절을 손절로 인정하는 경우」의 중간선거 문단 | 규칙 문서에 측정값(「2018 보유 중 −41.95%」)을 데이터 기간 없이 적어 `규칙.md` §2.5 와 두 벌이 됐다 — QLD 를 다시 받으면 두 곳의 최저가 갈리고 어느 쪽이 현재인지 알 수 없다(전역 「구체적 수치와 가변 정보를 직접 적지 않는다」) | 그 외 | PLAN_deferred_tests_midterm_notes (2026-09-29) 리뷰 1회차 — 같은 날 미룬 지적을 처리하며 직접 고친 문장 |

### 반감기_사이클 데이터 계층 (비트코인 수집 · 크로스체크)

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `src/verify_lab/CLAUDE.md:740` 「단일 값 시계열 계층 계약」의 「휴장일·결측」 행 | 계약은 「수집기는 결측을 **제외하고 건수를 보고**한다」인데 Coin Metrics 수집기는 결측을 **예외로 드러낸다**(휴장이 없어 결측은 소스의 결함이라서 — `coinmetrics_collector.py` 모듈 docstring). 계약 표에 그 예외가 적혀 있지 않아, 다음 시계열 수집기가 어느 쪽을 따를지 표만 봐서는 알 수 없다 | 그 외 | PLAN_halving_cycle_data (2026-09-29) 리뷰 1회차 |

### 반감기_사이클 측정 · 체결 (반감기 경과 격자 · 무손절 체결)

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `src/verify_lab/CLAUDE.md:150` · `:164` | 현재형만 쓰는 계약 문서에 과거형이 남아 있다 — 「쓰던 매매법이 모두 사라진 달력 함수는 지웠고」 · 「원칙 13 이 실제로 그 상태였습니다」. **이 계획 전부터 있던 문장**이다(`.claude/rules/docs.md` 「과거형이 허용되는 자리는 둘뿐입니다」) | 그 외 | PLAN_halving_cycle_measure (2026-09-29) 수정분 검증 (마지막 수정) |
