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

### 반감기_사이클 3단계 혼합 분할

줄 번호 기준: PLAN_halving_cycle_split_hybrid 완료 시점의 작업 트리 (2026-09-30 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `tests/test_studies_halving_cycle_split_rule.py:6` 모듈 설명 · `:102` `_buy_leg` | 「창 개월을 실제와 다르게 둔다」가 신고가 창(픽스처 `start_months=1` = 실제 `SPLIT_BUY_START_MONTHS_HIGH` 의 첫 값)과 `TestSplitGrid._sell_legs` 의 매도 창 `(0,)`(실제 첫 값)에는 틀리다. 수정분 검증의 메모리 변형 — `window_open` 이 신고가 기준에서 `leg.start_months` 대신 1 을 읽게 해도, `_fill_rows` 가 인자 `tranches` 대신 `SPLIT_TRANCHES` 를 읽게 해도 전 테스트 통과(「다른 회차 수는 … 테스트가 본다」는 `leg_fills` 경로만 맞다). 이 계획서가 다시 재지 않았다 | 그 외 | PLAN_halving_cycle_split_hybrid (2026-09-30) 수정분 검증 |
| `tests/test_studies_halving_cycle_split_rule.py:557` `TestLegFills.test_신고가_창과_순위_문턱도_뒤를_잘라도_그_전에_체결한_회차가_같다` | 설명은 순위의 미래 참조도 잡는다고 하지만 신고가 창만 잡는다 — `trailing_rank` 를 전 기간 순위 · ±1년 창 · `shift(-1)` 로 바꾼 변형 셋이 모두 통과한다(`TestTrailingRank` 의 직접 테스트만 잡는다). 딥 하루가 전 기간 최저라 미래를 넣어도 순위가 바닥에 남기 때문이다. 제안: 자른 뒤의 값을 딥보다 낮게 둔다. `split_grid` 단계에서 순위 · 신고가를 잇는 부분에는 자르기 테스트가 없다 | 그 외 | PLAN_halving_cycle_split_hybrid (2026-09-30) 수정분 검증 |

### 반감기_사이클 3단계 격자기준선

줄 번호 기준: PLAN_halving_grid_baseline 완료 시점의 작업 트리 (2026-09-30 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `tests/test_studies_halving_cycle_runner.py:1093` `TestGridBaseline.test_유효_표본이_없는_칸도_행이_남고_지표는_빈칸이다` | 유효 기준선이 없는 보유의 `기준선 비중첩 표본` 이 **빈칸**인지 보지 않는다 — `runner._baseline_for` 의 대체 값 `pd.NA` 를 `0` 으로 바꿔도 통과한다(「잰 적 없음」이 「0건」으로 나간다 — 측정의 원칙 17). 변형 ②(대체 행을 지움)만 잡는다. `설계.md` 결정 ㊽ 의 「테스트가 고정한다」는 행이 사라지지 않는 것까지다 | 그 외 | PLAN_halving_grid_baseline (2026-09-30) 리뷰 1 · 2회차 |
| `tests/test_studies_halving_cycle_runner.py:1022` `TestGridBaseline.test_보유_3_6_12개월의_기준선은_1단계_기준선과_같다` | 기준선 여섯 값 중 표본 · 평균 · 오른 비율 셋만 견준다 — 중앙값 · 내린 비율 · 비중첩을 다른 보유로 붙이는 회귀가 통과한다. 실제 실행 대조는 여섯 값을 봤다(`설계.md` §4.13) | 그 외 | PLAN_halving_grid_baseline (2026-09-30) 리뷰 1회차 |
| `tests/test_studies_halving_cycle_runner.py:956` `TestGridBaseline` | 「칸 값 = 무손절 체결」을 고정하는 테스트가 없다 — 체결 쪽 가격 규칙(예: 다음날 시가 진입)이 바뀌어도 격자기준선은 종가 ÷ 종가로 재 두 표가 같은 칸에서 어긋나고 전 테스트가 통과한다. 같은 합성 입력으로 `grid_baseline_table` 과 `run_halving_cycle_trading` 의 무손절 · 전체 행을 대조하면 잡힌다. 실제 실행 대조는 차이 0(`설계.md` §4.13) | 그 외 | PLAN_halving_grid_baseline (2026-09-30) 리뷰 2회차 |
| `tests/test_studies_halving_cycle_runner.py:1120` · `:1137` 보유 전제 가드 테스트 둘 | 멈추는 날(7월 31일) 하나와 멈추지 않는 날(7월 30일) 하나만 고정한다 — 다른 대리 조건(예: 「어떤 진입이 말일로 당겨지는가」)으로 바꿔도 둘 다 통과할 수 있다. 등식과 같다는 것은 수정분 검증의 전수 대조로만 확인했다 | 그 외 | PLAN_halving_grid_baseline (2026-09-30) 수정분 검증 |

### 반감기_사이클 판단용 차트

줄 번호 기준: PLAN_halving_chart_no_guide 완료 시점의 작업 트리 (2026-10-02 확인 — 그 계획서가 차트의 설명 블록을 지우며 자리를 옮겼다).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `src/verify_lab/studies/halving_cycle/chart.py:611` `build_chart_html` | 조립 함수에 테스트가 없다 — 표시용 프레임의 종목 거르기, 데이터 끝 뒤 반감기의 세로선 거르기, 그릴 폭(`CHART_SPLIT_NAME`)과 바닥 앞 개월(`BOTTOM_LEAD_MONTHS`)을 넘기는 배선을 뒤집어도 차트 테스트가 전부 통과한다. `run_study` 를 monkeypatch 하면 합성 프레임으로 검사할 수 있다(2026-10-01 PLAN_halving_calendar_chart 의 재구성 뒤 다시 확인 — 그 전의 문턱 배치 · `buy_level` 은 코드와 함께 사라졌다) | 그 외 | 코드 리뷰 1 · 2회차 · 출처: PLAN_halving_decision_chart (2026-10-01) |
| `tests/test_studies_halving_cycle_chart.py` `TestSplitPoints` · `TestWindowBands` · `TestSplitTable` | 종목이 둘인 프레임 · 컬럼이 빠진 프레임에서 멈추는 가드(`chart._require_single_ticker` · `_require_columns`)를 보는 테스트가 없다 — `split_points` 에서 종목 가드를 빼도 차트 테스트가 전부 통과하고, 두 종목의 점이 한 차트에 섞인다. 재구성 전에는 `TestGridCells.test_종목이_둘이면_멈춘다` 가 같은 가드를 봤다 | 그 외 | 코드 리뷰 1회차 · 출처: PLAN_halving_calendar_chart (2026-10-01) |
| `src/verify_lab/studies/halving_cycle/chart_template.html:211` `monthExtent` | ① 의 띠를 실제 회차 점까지 넓히는 계산이 테스트가 없는 JS 에만 있다 — 다른 축의 점 값(`bottom_months`)을 읽거나 쪽을 바꾸거나 기간 값과의 병합을 빼도 차트 테스트가 전부 통과하고 헤드리스 캡처로만 드러난다. 띠 범위를 Python 이 점과 같은 `_months_after` 로 내고 `TestWindowBands` 처럼 고정하면 막힌다. 결정 54 로 회차가 그 달의 말일이 되어 명목 개월(`split_info` 의 첫 · 마지막 기한)과 점의 차이가 최대 한 달 가까이로 커졌다 — ① 의 띠가 점을 덮는 것은 이제 거의 이 JS 덕이다(③ 의 띠는 회차 표의 기한을 옮겨 Python 에 있다) | 그 외 | 코드 리뷰 2회차 · 출처: PLAN_halving_calendar_chart (2026-10-01) · 코드 리뷰 1회차 · 출처: PLAN_halving_month_end_split (2026-10-01) |
| `tests/test_studies_halving_cycle_chart.py:186` `_positions` | 한 행 안에서 매도 회차 수(4)와 매도 첫 · 마지막 기한(1 · 5개월, 간격 2 — 3회를 뜻한다)이 맞지 않는다. 숫자표의 매수 · 매도 회차 수가 뒤바뀌면 걸리게 4 로 바꾸면서 생겼다. `split_table` 이 기한 칸을 읽지 않아 테스트 결과에는 영향이 없지만, 모듈 docstring 의 「가」 매도 1 · 3 · 5개월과도 어긋나 읽는 사람을 헷갈리게 한다 — 마지막 기한을 7 로 두면 맞는다 | 그 외 | 수정분 검증 · 출처: PLAN_halving_month_end_split (2026-10-01) |

## 코드

줄 번호 기준: PLAN_deferred_tests_midterm_notes 완료 시점의 작업 트리 (2026-09-29 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `src/verify_lab/studies/midterm_cycle/trading.py:1006` `run_midterm_cycle_trading` 의 `notes` 조립 | 손절선 설명 문구 둘을 실제로 돈 손절선이 아니라 **입력 플래그**(`stop_grid` · `is_index`)로 고르고, `NOTE_STOP_CONFIRMED` 는 `STOP_LEVELS_ETF_CONFIRMED` 가 무손절 하나라는 사실을 문구에 박아 둔다. 확정 규칙이 가격 손절(예: `(0.25,)`)로 바뀌면 기본 실행이 −25% 를 걸고도 「무손절 한 종만 낸다」를 싣고 `NOTE_STOP_BASE` 를 빠뜨리며, `TestStopNotes` 도 같은 가정이라 통과한다. 리뷰 제안: `NOTE_STOP_BASE` 는 ETF 에 숫자 손절선이 하나라도 돌았는지로, `NOTE_STOP_CONFIRMED` 는 `STOP_LEVELS_ETF_CONFIRMED` 가 무손절 하나인지로 가른다. 지금 `is_index` 로 가른 것은 바로 아래 문구들과 같은 관용이라서이고, 성적표의 `stop_levels_run` 에 숫자가 있는지로 가르는 안은 표시값 형식(`stop_level_value`)에 기대게 돼 택하지 않았다. 확정 규칙이 무손절이라 지금은 발동하지 않는다 | 가벼운 버그 | PLAN_deferred_tests_midterm_notes (2026-09-29) 리뷰 1회차 |
| `src/verify_lab/studies/midterm_cycle/trading.py:220` `NOTE_STOP_CONFIRMED` | 확정 규칙의 대상(QQQ) · 상품(QLD) · 절 번호(§2.5) · 등급이 든 문서 경로(`docs/매매/…`)를 산출물 문구에 박았고, ETF 가 하나라도 돌면 싣는다 — `--ticker SPY` 로 돌리면 그 산출물에 없는 「대상 QQQ 의 무손절 행」을 가리킨다. 대상 · 절 번호 · 등급이 바뀌면 커밋된 `summary.json` 이 조용히 낡는다(테스트는 상수를 import 해 따라간다). 기본 산출물은 QQQ 를 담아 지금은 맞다 | 가벼운 버그 | PLAN_deferred_tests_midterm_notes (2026-09-29) 리뷰 1회차 |
| `src/verify_lab/studies/midterm_cycle/trading.py:1006` 격자 실행의 `notes` | QLD 경고가 기본 실행 문구에만 있다 — `--stop-grid` 실행(결과 문서 §12 격자 표의 출처)에는 「규칙은 QLD 를 사고, 1배 손절선 행이 거기 그대로 옮겨지지 않는다」는 말이 없어, −25 · −30% 행이 무손절과 같다는 것을 QLD 규칙에 그대로 적용해 읽을 수 있다(QLD 는 2018 보유 중 −41.95%). 격자 실행을 좁히기 전 산출물과 바이트 동일하게 두려고 문구를 더하지 않았다 | 그 외 | PLAN_deferred_tests_midterm_notes (2026-09-29) 리뷰 1회차 |
| `src/verify_lab/studies/midterm_cycle/trading.py:1006` · `:1009` | ETF 가 있는지(`any(not dataset.is_index for dataset in datasets)`)를 두 번 계산한다 — 한 번 묶어 두면 손절·배당 문구 셋의 조건이 한 판단으로 읽히고, 조건이 바뀔 때 갈라지지 않는다 | 그 외 | PLAN_deferred_tests_midterm_notes (2026-09-29) 리뷰 1회차 |


### 데이터 계층 — 시세 검증기의 형제 (계열 · 선물)

줄 번호 기준: PLAN_deferred_halving_fixes 완료 시점의 작업 트리 (2026-09-30 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `src/verify_lab/data/loader.py:206` `validate_series_data` · `:278` `validate_futures_data` | `validate_market_data` 는 가격 · 거래량의 무한대를 막지만 형제 검증기 둘은 무한대를 보지 않는다 — 계열은 결측만 보고(값의 타당 범위는 수집기에 맡기는 설계인데 유한성을 검사하는 수집기는 `coinmetrics_collector` 하나다), 선물은 체결가 · 미결제약정의 무한대와 계약 첫 행 정산가의 무한대가 통과한다. 재현: `validate_series_data(pd.DataFrame({"Date": ["2020-01-01"], "Value": [np.inf]}))` 가 통과. 실제 저장 파일은 계열 17개 149,398행 · 선물 2개 56,946행에서 무한대 0 | 가벼운 버그 | PLAN_deferred_halving_fixes (2026-09-30) 리뷰 1회차 |

### 반감기_사이클 3단계 혼합 분할 (split_rule · runner)

줄 번호 기준: PLAN_halving_cycle_split_hybrid 완료 시점의 작업 트리 (2026-09-30 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `src/verify_lab/studies/halving_cycle/split_rule.py:744` `split_grid` · `docs/검증/반감기_사이클/설계.md` 결정 ㊼ ④ | 포지션 수익률에 하드포크 몫이 없다. 리뷰가 잰 값(이 계획서가 다시 재지 않았다): 2012 사이클 포지션이 최대 +1,167%p · 중앙값 +72%p 과소평가되고, 매도 시점에 따라 고르지 않다 — 4년 순위 매도는 전부 2017-08-01 전이라 배수 1.000, 달력 기한 21 매도는 ×1.145. 그래서 `결과.md` §20 의 2012 사이클 비교에서 포크 뒤에 판 쪽이 덜 잡힌다(온체인 매도가 이미 낮아 방향은 같다). 결정 ㊼ ④ 의 근거(`trading` → `runner` 순환 import)는 이제 없다 — `hard_fork_share` 가 잎 모듈 `studies/halving_cycle/hard_fork.py` 에 있고 달력 분할 손절 표가 이미 측정에서 쓴다(2026-10-04 옮김). **계획서가 비목표로 받아들인 것 — 넣을지 사용자 결정** | 가벼운 버그 | PLAN_halving_cycle_split_hybrid (2026-09-30) 리뷰 1회차 |
| `src/verify_lab/studies/halving_cycle/split_rule.py:811` `split_grid` · `:466` `position_result` | 호출자 입력(반감기 목록 · 격자 값 · 손으로 만든 회차)으로 닿는 조건에 `RuntimeError`(「내부 불변조건 위반」)를 낸다 — 전역 `~/.claude/rules/python.md` 는 입력 검증을 `ValueError` 로 둔다. 재현: 간격 5개월짜리 반감기 둘로 `split_grid` → `RuntimeError`. 실제 산출물에서는 발동하지 않는다(매수 기한 최대 36개월 < 가장 짧은 간격 43.37개월) | 가벼운 버그 | PLAN_halving_cycle_split_hybrid (2026-09-30) 리뷰 1회차 |
| `src/verify_lab/studies/halving_cycle/split_rule.py:183` `_require_increasing` | `measure.calendar_entry.validate_trading_days`(이 패키지에서 7곳이 부른다)를 다시 구현했고, `split_grid` · `position_result` 가 입력 시세를 `validate_market_frame` 으로 검사하지 않는다 — 저가 없는 시세는 맨 `KeyError`, 빈 시세는 `leg_fills` 의 `trading_days[-1]` 에서 `IndexError` 로 멈춘다(패키지의 분명한 `ValueError` 대신). 실제 경로는 로더를 지나 발동하지 않는다 | 가벼운 버그 | PLAN_halving_cycle_split_hybrid (2026-09-30) 리뷰 1회차 |
| `src/verify_lab/studies/halving_cycle/split_rule.py:633` `_fill_rows` | 온체인 체결은 판정일의 «다음 거래일»인데 「체결 전날 MVRV · 4년 순위」는 «달력 전날»(체결일 − 1일)을 읽는다. 시세에 빠진 날이 있으면 d 판정 → d+2 체결 → d+1 의 값이 실리고 예외가 없다. 지금 시세는 수집기가 빠진 날 0 을 보장한다(`설계.md` 결정 ⑪) | 가벼운 버그 | PLAN_halving_cycle_split_hybrid (2026-09-30) 리뷰 1회차 |
| `src/verify_lab/studies/halving_cycle/split_rule.py:489` · `:856` | `COL_HOLD_DAYS`(표시 「보유 거래일」)에 달력 날 수 차이를 싣는다 — 비트코인은 매일 거래라 값이 같다. 휴장이 있는 계열에 쓰면 달력 날 수가 「거래일」 머리로 나간다 | 가벼운 버그 | PLAN_halving_cycle_split_hybrid (2026-09-30) 리뷰 1회차 |
| `src/verify_lab/studies/halving_cycle/split_rule.py:436` `position_result` · `:396` `leg_fills` | 성능 — `position_result` 가 3,060번 불리며 매번 시세 전체를 `DatetimeIndex` · 배열로 다시 만들고, 매수 쪽 조화평균 · 누적 역수를 매도 조합마다 다시 계산한다. `leg_fills` 는 값 계열을 조합 × 사이클마다 다시 `reindex` 한다. 축이 늘면 선형으로 는다 | 그 외 | PLAN_halving_cycle_split_hybrid (2026-09-30) 리뷰 1회차 |
| `src/verify_lab/studies/halving_cycle/split_rule.py:646` `_leg_identity` · `_fill_rows` | 조합의 식별 칸에 문턱 «값»(`levels`)이 없고 조합이 겹치는지 검사하지 않는다 — 같은 방식에 두 번째 문턱 범위를 더하면 표에서 구별되지 않는 행이 예외 없이 생긴다 | 그 외 | PLAN_halving_cycle_split_hybrid (2026-09-30) 리뷰 1회차 |
| `src/verify_lab/studies/halving_cycle/split_rule.py:96` `_DATE_COLUMNS` 주석 | 「전부 비어도 날짜 열로 남긴다」가 회차 표의 체결일에는 틀리다 — 체결한 회차가 하나도 없으면 그 키가 행에 없어 `_frame_of` 에 열이 없고, `reindex` 가 float64 열로 만든다(CSV 는 같은 빈칸) | 그 외 | PLAN_halving_cycle_split_hybrid (2026-09-30) 수정분 검증 |
| `src/verify_lab/studies/halving_cycle/runner.py:262` `NOTE_SPLIT_FORK` · `scripts/run_halving_cycle.py:15` 모듈 설명 | 바로 위 주석 「격자 값을 글자로 박지 않는다」와 달리 「(2012 사이클)」(격자 · 포크 · 반감기에서 따라 나오는 사실)과 「세 번」(`SPLIT_TRANCHES`)을 문장에 박았다 — 지금은 맞지만 매수 창 · 매도 기한 · 회차 수가 바뀌면 조용히 낡는다 | 그 외 | PLAN_halving_cycle_split_hybrid (2026-09-30) 수정분 검증 |
| `src/verify_lab/studies/halving_cycle/constants.py:399` · `:400` `Dataset.mvrv_path` · `market_cap_path` 설명 | 「2단계 측정만 읽는다」인데 3단계 혼합 분할도 MVRV 를 쓰고, 시가총액도 `runner.load_onchain` 의 공통 날짜 자르기로 분할이 쓰는 MVRV 날짜 범위에 영향을 준다. `docs/검증/반감기_사이클/설계.md` §3 데이터 소스 표의 역할 칸도 「2단계 온체인」이다 | 그 외 | PLAN_halving_cycle_split_hybrid (2026-09-30) 수정분 검증 |

### 반감기_사이클 3단계 격자기준선 (runner · halving_calendar)

줄 번호 기준: PLAN_halving_grid_baseline 완료 시점의 작업 트리 (2026-09-30 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `src/verify_lab/studies/halving_cycle/halving_calendar.py:277` `exit_schedule` 의 `pd.concat` | 한 보유의 청산일이 **전부** 데이터 뒤라 `COL_EXIT_DATE` 가 전부 NaT 인 블록을 이어 붙일 때 pandas 가 NumPy `DeprecationWarning`(「'generic' unit … will raise an error in the future」)을 낸다. 재현: `grid_baseline_table` 을 2013-06-30 에서 끝나는 합성 시세에 돌린다(러너 테스트 `test_유효_표본이_없는_칸도_행이_남고_지표는_빈칸이다`) — `-W error::DeprecationWarning` 이면 실패한다. NumPy 가 오류로 바꾸면 첫 반감기 + 45개월보다 짧은 입력에서 측정 전체가 멈춘다. 실제 데이터에서는 보유 45개월도 유효 청산이 있어 나지 않는다 | 가벼운 버그 | PLAN_halving_grid_baseline (2026-09-30) 리뷰 1 · 2회차 |
| `src/verify_lab/studies/halving_cycle/runner.py:828` `_cell_tables` 의 `cell_excess.merge(baseline.overlap, …)` · `:720` `_baseline` | `_baseline` 의 비중첩 표는 유효 행이 있는 보유만 담고 `_cell_tables` 가 inner merge 한다 — 1단계 `_aggregate` · 2단계 `_indicator_statistics` 경로에서 어떤 보유에 유효 기준선이 하나도 없으면 그 보유의 차이 행이 **예외 없이 빠져** 통계와 excess 의 행 수가 갈린다. 격자기준선은 `_baseline_for` 가 빈칸 한 행을 둬 막았다. 제안: `_baseline` 에서 비중첩을 집계의 보유 전부로 reindex 하면 세 호출처가 함께 막힌다. 실제 데이터(보유 3 · 6 · 12)에서는 발동하지 않는다 | 가벼운 버그 | PLAN_halving_grid_baseline (2026-09-30) 리뷰 2회차 |
| `src/verify_lab/studies/halving_cycle/runner.py:958` `grid_baseline_table` · `:909` `_indicator_statistics` | 칸 한 행을 만드는 조립(`_cell_tables` → 기준 제거 · 차이 병합 · 검정 병합 → 보유로 개명 → 비중첩 병합 → `Int64`)과 열 목록 뒤쪽이 2단계와 거의 같다 — 한쪽에만 열을 더하거나 `_TEST_VALUES[1:]` 같은 위치 슬라이스를 고치면 지표통계와 격자기준선의 구성이 예외 없이 갈린다. 제안: 칸 행 도우미 하나와 공통 꼬리 열 목록 하나 | 그 외 | PLAN_halving_grid_baseline (2026-09-30) 리뷰 1 · 2회차 |
| `src/verify_lab/studies/halving_cycle/runner.py:741` `_baseline_for` · `:958` `grid_baseline_table` | 성능 — 보유 15종인데 `_baseline_for` 가 120칸마다 약 7만 행의 기준선을 다시 거르고, 보유 3 · 6 · 12 기준선은 `run_study` 와 `grid_baseline_table` 에서 두 번 계산된다. 보유별 묶음을 한 번 만들어 조회하면 같다. 지금 실행은 45초 | 그 외 | PLAN_halving_grid_baseline (2026-09-30) 리뷰 1 · 2회차 |
| `src/verify_lab/studies/halving_cycle/runner.py:979` `pairs` · `:1001` `same_cycle` · `constants.py:290` `GRID_BASELINE_HOLD_MONTHS` · `halving_calendar.py:307` `_position_exit` | 「같은 사이클에 판다 = 청산 개월 > 진입 개월」이 src 네 곳에 따로 적혀 있다 — 같은 함수 안의 `pairs` 와 `same_cycle` 도 따로 판정한다. 한 곳만 바꾸면(예: `>=`) 나머지가 다른 칸 집합을 본다. 갈라지면 `_baseline_for` 의 `RuntimeError` 나 칸 0건으로 드러나 조용히 틀린 값이 나가지는 않는다(수정분 검증 확인) | 그 외 | PLAN_halving_grid_baseline (2026-09-30) 리뷰 1회차 · 수정분 검증 |
| `src/verify_lab/studies/halving_cycle/runner.py:979` ~ `:998` 보유 전제 가드 | 등식을 「격자 120쌍 × 모든 반감기」로 본다 — 다음 반감기 뒤라 재지 않는 쌍 · 데이터 뒤의 쌍까지 본다. 수정분 검증의 전수 대조(가상 반감기일 2012-01-01 ~ 2019-12-31)에서는 판정이 바뀌는 날 0 이고 틀리는 방향은 안전한 쪽(미리 멈춤)이다. 예외 문구가 어긋남 5건 이하일 때 「외 0건」을 찍는다 | 그 외 | PLAN_halving_grid_baseline (2026-09-30) 수정분 검증 |


### 반감기_사이클 판단용 차트 (chart · chart_template)

줄 번호 기준: PLAN_halving_chart_no_guide 완료 시점의 작업 트리 (2026-10-02 확인 — 그 계획서가 차트의 설명 블록을 지우며 자리를 옮겼다).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `src/verify_lab/studies/halving_cycle/chart.py:570` `render_html` | plotly.js 에서 `</script` 만 막는다 — `<!--` 뒤에 `<script` 가 이어지면 HTML 토크나이저가 double-escaped 상태가 되어 뒤의 스크립트가 삼켜진다. 데이터 JSON 도 `</` 만 바꾼다(`<` 를 `\u003c` 로 바꾸지 않음). 지금 번들 · 데이터에 그 글자는 0건 | 가벼운 버그 | 코드 리뷰 1회차 · 출처: PLAN_halving_decision_chart (2026-10-01) |
| `src/verify_lab/studies/halving_cycle/chart.py:638` `build_chart_html` | 차트는 달력 분할 두 표만 쓰는데 `run_study` 전체(1 · 2단계 집계 · 무작위 뽑기 대조 · 혼합 분할 · 격자기준선)를 돌리고 시세를 두 번 읽는다 — 차트 실행 4.5초(2026-10-01). `split_rule.calendar_split_grid` 를 직접 부르면 준다 | 그 외 | 코드 리뷰 1 · 2회차 · 출처: PLAN_halving_decision_chart (2026-10-01) |
| `src/verify_lab/studies/halving_cycle/chart.py:324` `bottom_series` | 선 n 을 다음 사이클의 바닥 전날에서 끊는데, 다음 사이클이 진행 중이면 그 바닥은 잠정이다 — 다음 반감기가 목록에 들고 그 사이클의 잠정 바닥이 앞 포지션의 매도 기간 안에 오면 매도 점이 선 끝 밖에 놓이고, ② 의 가로축 범위가 선 길이로만 잡혀 그 점이 화면 밖으로 잘린다. 끊긴 선 끝이 잠정이라는 표시도 없다(점선은 마지막 선만). 지금 산출물은 2020 포지션 매도(2025-01-31 ~ 2025-10-31)가 그 선 끝(2026-06-29) 앞이라 안 나온다 | 가벼운 버그 | 코드 리뷰 1 · 2회차 · 출처: PLAN_halving_calendar_chart (2026-10-01) |
| `src/verify_lab/studies/halving_cycle/chart.py:392` `split_info` · `runner.py` `_calendar_split_rule` | 폭 한 줄(이름 · 회차 수 · 매수 · 매도 첫 · 마지막 개월)을 두 곳이 따로 조립한다 — 한쪽만 바뀌면 차트(숫자표 제목 줄 · ① 의 띠)와 `summary.json` 이 같은 폭을 예외 없이 다르게 말한다 | 그 외 | 코드 리뷰 2회차 · 출처: PLAN_halving_calendar_chart (2026-10-01) |
| `src/verify_lab/studies/halving_cycle/chart.py:506` `split_table` | 첫 매수일 · 마지막 매도일까지 회차 표에서 다시 세는데 포지션 표에 같은 값(`첫 매수일` · `마지막 매도일`)이 있다 — 회차 표가 필요한 것은 마지막 매수일 · 첫 매도일뿐이다. 두 계산이 갈리면 숫자표의 기간이 `달력분할포지션.csv` 와 예외 없이 어긋난다 | 그 외 | 코드 리뷰 2회차 · 출처: PLAN_halving_calendar_chart (2026-10-01) |
| `src/verify_lab/studies/halving_cycle/chart.py:143` `_day` | 호출처가 `split_table` 하나이고 늘 빈값 아닌 `Timestamp` 를 넘긴다 — 빈값 · 문자열 분기가 쓰이지 않고, docstring 의 「반감기 표지는 문자열로 들어온다」는 없는 호출처를 말한다 | 그 외 | 코드 리뷰 2회차 · 출처: PLAN_halving_calendar_chart (2026-10-01) |
| `src/verify_lab/studies/halving_cycle/chart.py:67` `DAYS_PER_MONTH` 주석 · `docs/검증/반감기_사이클/설계.md` §4.14 의 같은 문장 | 「격자 날짜와 이틀 안쪽」으로 적었지만 실제 반감기 넷 × 0 ~ 45개월 격자에서 최대 차이가 2.125일이다(2012-11-28 + 30개월 = 2015-05-28 은 911일, 30 × 30.4375 = 913.125일). 값 · 동작에는 영향이 없다 — 「약 이틀」로 고치면 맞는다 | 그 외 | 수정분 검증 · 출처: PLAN_halving_month_end_split (2026-10-01) |
| `src/verify_lab/studies/halving_cycle/chart.py:653` `build_chart_html` 의 `meta.sources` | 차트의 데이터 줄이 가격 파일(`BTCUSD_max.csv`) 하나만 적는다 — 측정 계열은 거래량 0 인 33일(2011 년 30일 · 2015-01-06 ~ 08)의 종가를 Coin Metrics `BTC_PriceUSD.csv` 로 바꾸고(`설계.md` 결정 ⑭) 그 값이 세 보기의 선에 들어간다. `BTC_PriceUSD.csv` 만 다시 받으면 차트 값이 바뀌어도 데이터 줄은 그대로다. 결정 55 가 이 줄을 「어느 시세로 그렸나」를 말하는 유일한 자리로 남겼다 | 그 외 | 코드 리뷰 1회차 · 출처: PLAN_halving_chart_no_guide (2026-10-01) |
| `src/verify_lab/studies/halving_cycle/chart_template.html:354` 폭 제목 줄 주석 | 「① 의 띠는 회차 점이 앉은 자리까지 넓혀 그려 이 값을 읽을 수 없다」는 띠의 뒤 끝에만 맞는다 — `monthExtent` 는 명목 기간과 점 범위 중 더 넓은 쪽이라 앞 끝은 명목값(27 · 9)과 같다. `설계.md` 결정 55 근거 ⑤ 와 같은 모양이다(문서 절) | 그 외 | 수정분 검증 2회차 · 출처: PLAN_halving_chart_no_guide (2026-10-02) |

### 반감기_사이클 3단계 달력 매달 분할 (split_rule · constants)

줄 번호 기준: PLAN_halving_month_end_split 완료 시점의 작업 트리 (2026-10-01 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `src/verify_lab/studies/halving_cycle/split_rule.py:948` `calendar_split_grid` | 매도 쪽 회차 기한(첫 매도 회차가 다음 반감기 앞인지)은 다음 반감기가 있을 때만 `tranche_deadlines` 가 검사한다 — 반감기가 하나뿐인 입력에 `CalendarSplit(sell_tranches=3, sell_last_deadline=1)`(간격 1개월)을 주면 예외 없이 첫 매도 기한 −1 이 포지션 표 · 요약에 실린다. `CalendarSplit` 자체에는 검사가 없다. 실제 폭의 첫 매도 회차는 9 라 안 나온다 | 가벼운 버그 | 코드 리뷰 1 · 2회차 · 출처: PLAN_halving_calendar_chart (2026-10-01) |
| `src/verify_lab/studies/halving_cycle/constants.py:388` `CalendarSplit.first_deadlines` · `split_rule.py:320` `tranche_deadlines` | 「첫 회차 = 마지막 − 간격 × (그쪽 회차 수 − 1)」이 두 벌이다 — 회차 날짜는 `tranche_deadlines` 가, 표 · 요약 · 차트 머리(① 의 띠)의 첫 기한 칸은 `first_deadlines` 가 낸다. 한쪽만 규칙을 바꾸면 CSV 의 첫 기한 칸이 같은 표의 회차 날짜와 예외 없이 어긋난다. `constants` 가 `split_rule` 을 가져오면 순환이라 하나로 모으려면 자리부터 정해야 한다 | 그 외 | 코드 리뷰 1회차 · 출처: PLAN_halving_calendar_chart (2026-10-01) |
| `src/verify_lab/studies/halving_cycle/split_rule.py:616` `_fill_rows` | `mvrv` · `ranks` 를 따로 선택 인자로 받고 둘 다 있을 때만 MVRV 칸을 싣는다 — 하나만 넘기면 두 칸이 예외 없이 사라진다. 달력 분할 경로는 혼합 분할의 식별 칸(문턱 · 시작 · 마지막 기한 · 계기)을 만든 뒤 `reindex` 로 버린다 | 그 외 | 코드 리뷰 1회차 · 출처: PLAN_halving_calendar_chart (2026-10-01) |
| `src/verify_lab/studies/halving_cycle/split_rule.py:983` `calendar_split_grid` 의 `new_high_flags` | 달력만 조합은 신고가를 읽지 않는데 `leg_fills` 가 받는 인자라 전 기간을 계산한다 — `trigger_values` 가 없을 때 `new_highs` 를 선택으로 두면 준다 | 그 외 | 코드 리뷰 1회차 · 출처: PLAN_halving_calendar_chart (2026-10-01) |

### 반감기_사이클 달력 분할 손절 (split_rule)

줄 번호 기준: PLAN_halving_split_stops 완료 시점의 작업 트리 (2026-10-04 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `src/verify_lab/studies/halving_cycle/split_rule.py:1224` `_stop_rows` 의 손절 매도 체결 | 저점 이탈로 옮긴 매도 회차의 `TrancheFill.trigger` 에 `STOP_METHOD_LOW_BREAK`(「저점 이탈」)를 넣는다 — 그 칸의 문서상 값은 `SPLIT_TRIGGER_*`(온체인 · 달력)뿐이고 `_trigger_counts` 가 그 회차를 어느 쪽으로도 세지 않는다. 열 매도 회차 중 아홉을 옮긴 포지션의 `position_result(...).sell_counts` 가 (0, 1) 이 된다. 지금 손절 표는 그 건수를 싣지 않아 산출물에는 0건이다 — 「매도 달력 회차」 같은 칸을 손절 표에 더하는 순간 손절로 판 회차가 예외 없이 빠진다 | 가벼운 버그 | 코드 리뷰 1 · 2회차 · 출처: PLAN_halving_split_stops (2026-10-04) |

## 문서

줄 번호 기준: PLAN_deferred_tests_midterm_notes 완료 시점의 작업 트리 (2026-09-29 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `docs/매매/중간선거_사이클/결과.md:84` §1 한 줄 요약 | QLD 수치(2018 보유 중 −41.95%)를 인용하는데 머리말의 데이터 기간에 QLD 가 없다 — `.claude/rules/docs.md` 「수치를 적을 때는 데이터 기간을 함께 적는다」(파일이 여럿이면 파일마다). QLD 기간은 `규칙.md` 머리말에 있다(2006-06-21 부터) | 그 외 | PLAN_deferred_tests_midterm_notes (2026-09-29) 리뷰 1회차 — 같은 날 미룬 지적을 처리하며 직접 고친 문장 |
| `.claude/rules/trading.md:126` 「기간 손절을 손절로 인정하는 경우」의 중간선거 문단 | 규칙 문서에 측정값(「2018 보유 중 −41.95%」)을 데이터 기간 없이 적어 `규칙.md` §2.5 와 두 벌이 됐다 — QLD 를 다시 받으면 두 곳의 최저가 갈리고 어느 쪽이 현재인지 알 수 없다(전역 「구체적 수치와 가변 정보를 직접 적지 않는다」) | 그 외 | PLAN_deferred_tests_midterm_notes (2026-09-29) 리뷰 1회차 — 같은 날 미룬 지적을 처리하며 직접 고친 문장 |

### 반감기_사이클 3단계 격자기준선 (결과 · 설계 문서)

줄 번호 기준: PLAN_halving_grid_baseline 완료 시점의 작업 트리 (2026-09-30 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `docs/검증/반감기_사이클/결과.md:997` §16.1 | 방향 비율 표(오른 체결 수 ÷ 표본, `3/4` · `4/4` …) **자체에는** 여전히 기준선 비율과 차이가 없다 — 표 머리에 §16.4 를 가리키는 한 줄만 있다. `.claude/rules/docs.md` 「방향 비율을 적는 모든 표에 같은 조건의 기준선 비율과 그 차이(%p)를 함께 둔다」. 이 표만 읽으면 보유 36개월 이상 칸의 `3/3` 을 우위로 읽는데 기준선이 99.17 ~ 100% 다. 기준선은 칸의 보유(청산 − 진입)로 정해져 한 열로 붙지 않는다 | 그 외 | PLAN_halving_grid_baseline (2026-09-30) 리뷰 1 · 2회차 |
| `docs/검증/반감기_사이클/결과.md:1045` §16.2 평균 행렬 · `:1147` · `:1171` §16.4 차이 행렬 둘 | 새로 넣은 행렬 셋에 **칸별 표본**이 없다(칸마다 1 ~ 4건 · 같은 사이클 칸은 2 ~ 4건) — `.claude/rules/research.md` 「표본 수를 모든 표에 넣는다」. 평균 행렬에는 **합산**도 없다 — 루트 `CLAUDE.md` 측정의 원칙 16. 칸별 표본은 §16.1 의 분모에 있다 | 그 외 | PLAN_halving_grid_baseline (2026-09-30) 리뷰 1 · 2회차 |
| `docs/검증/반감기_사이클/결과.md:1068` §16.2 평균-부호 어긋남 표 | 헤더가 `승률(%)` 이다 — `.claude/rules/docs.md` 는 결과 문서에서 「오른 비율」을 쓰고 `승률` 은 `규칙.md` · 체결 산출물에만 둔다. 14칸 중 같은 사이클 칸 11칸은 기준선이 있는데 기준선 비율 · 차이 열이 없다 | 그 외 | PLAN_halving_grid_baseline (2026-09-30) 리뷰 2회차 |
| `docs/검증/반감기_사이클/설계.md:464` 결정 ㊽ · `격자기준선.csv` 의 `신호` | 「앞 넷은 성적표와 같은 헤더라 그대로 이어 본다」는데 **같은 이름 `신호` 의 뜻이 다르다** — 격자기준선은 측정 표 관용대로 표본 + 제외(1단계 `통계.csv` 와 같다), `성적표.csv` 는 체결된 건수(= 표본)다. 실제 산출물을 이어 보면 120칸 중 65칸에서 `신호` 가 다르다(예: (0, 30) 은 4 대 3). 측정 표와 체결 표의 이 차이는 기존 관용이다 | 그 외 | PLAN_halving_grid_baseline (2026-09-30) 리뷰 1회차 |

### 반감기_사이클 차트 설명 제거 · 손절 측정 구성 (설계 · MEMORY 문서)

줄 번호 기준: PLAN_halving_chart_no_guide 완료 시점의 작업 트리 (2026-10-02 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `docs/검증/반감기_사이클/설계.md:561` 결정 56 근거 ④ | 「2016 · 2020 포지션을 들고 있는 동안 난 이탈 셋이 모두 사후 바닥 12 ~ 76일 전, 바닥으로 가는 마지막 하락 구간에서 났다 — 위험신호로 팔면 바닥 근처에서 판다」가 과장이다 — 2022-09-06 이탈(종가 18,789) 뒤 2022-09-12 종가 22,401(+19.2%)까지 올랐고 2022-11-09 에 또 깨졌다(§4.21 표의 다음 행). 이탈 다음 날 종가는 사후 바닥보다 2016 포지션 +75.7%(2018-11-15 · 5,585) · 2020 포지션 +22.3%(2022-09-07 · 19,276) · +11.3%(2022-11-10 · 17,551) 높았다. **같은 자리에서 두 번 지적됐다**(1회차 「마지막 투매였다」를 고친 문장) — 문장을 어떻게 다시 쓸지 사용자가 정한다. 탈락안 ④ 의 결론(감시 시작을 「버틴 저점」으로 잡으면 바닥 전 하락장에서 걸린다)은 §4.21 표가 그대로 뒷받침한다 | 그 외 | 수정분 검증 1 · 2회차 · 출처: PLAN_halving_chart_no_guide (2026-10-02) |
| `docs/검증/반감기_사이클/설계.md:553` 결정 55 근거 ⑤ | 「① 의 띠는 회차 점이 앉은 자리까지 넓혀 그려(27.0 ~ 32.7 · 9.4 ~ 18.8개월) 띠 끝으로 읽을 수 없다」의 숫자가 틀렸다 — 띠는 명목 기간과 점 범위 중 더 넓은 쪽(`chart_template.html` `monthExtent`)이라 실제로 27 ~ 32.69 · 9 ~ 18.76개월이고, 9.4 는 점의 범위다. 읽을 수 없는 것은 뒤 끝뿐이다. 결론(제목 줄에 명목 기간을 둔다)은 뒤 끝만으로 성립한다 | 그 외 | 수정분 검증 2회차 · 출처: PLAN_halving_chart_no_guide (2026-10-02) |
| `docs/검증/반감기_사이클/설계.md:559` 결정 56 확정 ③ | 「창이 닫힌 뒤에는 … 기준 저점이 감시를 시작한 날의 값에 고정된다」가 바로 앞의 「새 고점이 나면 저점을 그 뒤부터 다시 센다」와 부딪힌다 — 감시를 시작할 때 고점 창(반감기 뒤 24개월)이 열려 있다가 새 고점이 나면, 고정되는 값은 마지막으로 다시 센 뒤의 값이다. 월말 분할은 감시 첫날부터 창이 닫혀 있어 해당 없고, 어느 쪽으로 읽어도 지난 값만 쓴다(미래 참조 없음) | 그 외 | 수정분 검증 2회차 · 출처: PLAN_halving_chart_no_guide (2026-10-02) |
| `docs/MEMORY.md` 「판단용 차트에는 설명 블록을 두지 않는다」 · `docs/검증/반감기_사이클/설계.md:551` 결정 55 확정 | 차트에 남는 요소 목록을 두 곳이 적는다 — MEMORY.md 머리말의 「docs/ 문서가 담고 있는 것은 여기 쓰지 않는다」와 어긋나고, 한쪽만 바뀌면 다음 차트가 어느 목록을 따를지 갈린다 | 그 외 | 코드 리뷰 1회차 · 출처: PLAN_halving_chart_no_guide (2026-10-01) |
