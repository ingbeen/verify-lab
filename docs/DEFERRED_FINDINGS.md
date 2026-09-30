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


## 문서

줄 번호 기준: PLAN_deferred_tests_midterm_notes 완료 시점의 작업 트리 (2026-09-29 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `docs/매매/중간선거_사이클/결과.md:84` §1 한 줄 요약 | QLD 수치(2018 보유 중 −41.95%)를 인용하는데 머리말의 데이터 기간에 QLD 가 없다 — `.claude/rules/docs.md` 「수치를 적을 때는 데이터 기간을 함께 적는다」(파일이 여럿이면 파일마다). QLD 기간은 `규칙.md` 머리말에 있다(2006-06-21 부터) | 그 외 | PLAN_deferred_tests_midterm_notes (2026-09-29) 리뷰 1회차 — 같은 날 미룬 지적을 처리하며 직접 고친 문장 |
| `.claude/rules/trading.md:126` 「기간 손절을 손절로 인정하는 경우」의 중간선거 문단 | 규칙 문서에 측정값(「2018 보유 중 −41.95%」)을 데이터 기간 없이 적어 `규칙.md` §2.5 와 두 벌이 됐다 — QLD 를 다시 받으면 두 곳의 최저가 갈리고 어느 쪽이 현재인지 알 수 없다(전역 「구체적 수치와 가변 정보를 직접 적지 않는다」) | 그 외 | PLAN_deferred_tests_midterm_notes (2026-09-29) 리뷰 1회차 — 같은 날 미룬 지적을 처리하며 직접 고친 문장 |

### 반감기_사이클 3단계 (진입 × 청산 격자 · 손절선 · 하드포크)

줄 번호 기준: PLAN_halving_cycle_trading_grid 완료 시점의 작업 트리 (2026-09-30 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `docs/검증/반감기_사이클/결과.md:976` §16.1 · `설계.md` 결정 ㊵ · `trading.py` `NOTE_SCREEN` | 방향 비율 표(오른 체결 수 ÷ 표본)에 **기준선이 없다.** 결정 ㊵ 의 근거(「같은 칸도 사이클마다 보유 길이가 달라 기준선이 정의되지 않는다」)는 **다음 사이클에 파는 칸 136개에만** 맞는다 — 같은 사이클 칸 120개는 보유가 (청산 − 진입) 달력월로 고정돼 기존 `baseline_entries` + `exit_schedule` 로 기준선을 바로 낼 수 있다. 루트 `CLAUDE.md` 측정의 원칙 11 · `.claude/rules/docs.md` 「비율을 적을 때는 기준선 비율을 같은 표에 붙인다」 | 그 외 | PLAN_halving_cycle_trading_grid (2026-09-30) 리뷰 2회차 · 판단: 고친다(사용자 2026-09-30) — `설계.md` 결정 ㊶, §16.2 와 한 계획서로 |
| `docs/검증/반감기_사이클/결과.md:999` §16.2 | 256칸의 **중앙값만** 행렬로 싣고 평균은 `성적표.csv` 로 넘겼다(예 몇 칸만 본문에). 평균-부호 어긋남 표는 평균 · 표본은 있는데 **합산 수익률**이 없다 — 루트 `CLAUDE.md` 측정의 원칙 4(평균 · 중앙값 병기) · 16(회당 기대값 옆에 합산과 표본) | 그 외 | PLAN_halving_cycle_trading_grid (2026-09-30) 리뷰 2회차 · 판단: 고친다(사용자 2026-09-30) — 결정 ㊶ 의 계획서에서 함께 |
