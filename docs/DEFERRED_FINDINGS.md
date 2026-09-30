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
| `src/verify_lab/studies/halving_cycle/split_rule.py:744` `split_grid` · `docs/검증/반감기_사이클/설계.md` 결정 ㊼ ④ | 포지션 수익률에 하드포크 몫이 없다. 리뷰가 잰 값(이 계획서가 다시 재지 않았다): 2012 사이클 포지션이 최대 +1,167%p · 중앙값 +72%p 과소평가되고, 매도 시점에 따라 고르지 않다 — 4년 순위 매도는 전부 2017-08-01 전이라 배수 1.000, 달력 기한 21 매도는 ×1.145. 그래서 `결과.md` §20 의 2012 사이클 비교에서 포크 뒤에 판 쪽이 덜 잡힌다(온체인 매도가 이미 낮아 방향은 같다). 결정 ㊼ ④ 의 근거(`trading` → `runner` 순환 import)는 순수 함수 `trading.hard_fork_share` 를 잎 모듈로 옮기면 사라진다. **계획서가 비목표로 받아들인 것 — 넣을지 사용자 결정** | 가벼운 버그 | PLAN_halving_cycle_split_hybrid (2026-09-30) 리뷰 1회차 |
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
