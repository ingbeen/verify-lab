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

줄 번호 기준: HEAD `8a521ce` (2026-09-29 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `tests/test_measure_screening.py:291` `TestSingleOwner.test_게이트의_기준값과_판정_값을_소유자_밖에서_쓰지_않는다` | 스캔 범위(`:323`)가 `src/verify_lab` 뿐이라 **`scripts/` 가 게이트를 다시 써도 못 잡는다** — 스크립트가 `MIN_EXPECTED_VALUE` 를 가져다 직접 비교해 후보를 골라도 통과한다. 범위를 넓히면 `scripts/run_midterm_cycle.py:169` 가 `SCREEN_CANDIDATE` 로 행을 고르는 정당한 사용처라 허용 경로(`GATE_OWNERS`)에 이유와 함께 더해야 한다 | 가벼운 버그 | PLAN_test_contract_gaps (2026-09-28) 리뷰 1회차 |
| `tests/test_measure_screening.py:333` `TestSingleOwner._gate_usage` | 게이트를 **이름**(AST 의 이름 · 속성 · import)으로만 찾아, 기준값을 **숫자 리터럴로 적은 비교**나 **다른 이름으로 다시 정의한 상수**로 게이트를 다시 쓰면 못 잡는다. 계획서가 이름 기준을 택하며 받아들인 한계다 | 가벼운 버그 | PLAN_test_contract_gaps (2026-09-28) 리뷰 2회차 |
| `tests/test_measure_screening.py:288` `TestSingleOwner.test_성적_산식_계층이_이_게이트를_쓴다` | `"screen_verdict(" in source` 로 **소스 문자열**을 봐, `src/verify_lab/execution/periods.py` 에서 호출이 사라지고 주석이나 문자열에만 남아도 통과한다. 바로 아래 테스트는 같은 일을 AST 로 한다 | 가벼운 버그 | PLAN_test_contract_gaps (2026-09-28) 리뷰 1회차 |
| `tests/test_output_contract.py:91` · `:806` `test_제외_건수는_요약이_대상마다_담는다` | 매매법 전부의 요약을 검사하면서 키 이름 `KEY_EXCLUDED_COUNT` 를 **`studies/midterm_cycle/constants.py` 에서 빌려 온다.** 다른 매매법이 그 키를 다른 이름으로 쓰면 중간선거의 이름으로 검사하게 되고, 중간선거 매매법을 지우면 이 공유 계약 검사가 함께 깨진다(`docs/MEMORY.md` 「공유 계층의 테스트는 «자기 픽스처»를 갖는다」) | 가벼운 버그 | PLAN_test_contract_gaps (2026-09-28) 리뷰 1회차 |
| `tests/test_studies_reverse_trading.py:122` `_market` | `extra_surges` 를 심을 때 **범위 가드가 없다.** 바로 위 `SIGNAL_PLACEMENTS` 루프(`:116`)는 `accumulation + offset >= len(changes)` 면 건너뛰지만 이쪽은 그대로 인덱싱해, `rows` 를 줄여 부르면 `MID_RANK_SURGES` 의 뒤쪽 오프셋에서 `IndexError` 가 난다. 지금 호출처는 기본 `rows` 만 써서 발동하지 않는다 | 가벼운 버그 | PLAN_test_contract_gaps (2026-09-28) 리뷰 1회차 |
| `tests/test_studies_reverse_trading.py:317` `TestSignalOwnership.test_순위_컷을_넓히면_신호가_늘어난다` | 넓은 컷의 신호 수가 좁은 컷보다 **많은지만**(`wide_count > narrow_count`) 본다. 순위 선택(`src/verify_lab/studies/reverse/extreme_move.py:119` 의 `<= rank_cut`)을 `<` 로 바꿔도 부등호가 유지돼 통과한다 — 리뷰 원문 「컷을 `<` 로 다시 판정해도 통과(`11 > 6`)」, 이 수치는 다시 재지 않았다. 개수를 박지 않은 것은 순위 산식이 바뀌어도 버티게 하려고 계획서가 택한 것이다 | 가벼운 버그 | PLAN_test_contract_gaps (2026-09-28) 리뷰 2회차 |
| `tests/test_measure_screening.py:333` `TestSingleOwner._gate_usage` | AST 로 이름·리터럴을 훑는 헬퍼가 **두 벌**이다 — `tests/test_layer_contracts.py` 의 `_literals`(`:303`) · `_files_with_literal`(`:255`) 가 같은 일을 한다. 계획서가 「리뷰가 지목한 자리에 두는 수술적 변경」으로 일부러 따로 뒀다 | 그 외 | PLAN_test_contract_gaps (2026-09-28) 리뷰 1회차 |
| `tests/test_output_contract.py:557` `test_매매법_성적표의_공통_부분이_완전히_같다` | **중복 검사다.** 바로 위 매개변수화 테스트 `test_성적표가_공통_컬럼을_순서대로_쓴다`(`:540`)가 매매법마다 전체 컬럼을 `_expected_summary`(종목 · 축 · `SUMMARY_COMMON_COLUMNS` · 꼬리)와 비교하므로 공통 부분의 일치는 거기에 이미 들어 있다 | 그 외 | PLAN_test_contract_gaps (2026-09-28) 리뷰 1회차 |
| `tests/test_output_contract.py:599` `TestTradeColumns.test_거래내역이_공통_컬럼을_순서대로_쓴다` | 「매매법 전부」를 도는 테스트의 docstring Then 이 매매법별 축을 이름으로 나열한다(「역방향은 … 중간선거_사이클은 …」) — 매매법이 늘거나 바뀌면 낡는다. 리뷰 원문은 「「매매법 전부」 docstring 이 매매법별 축을 나열」이고, 이 자리는 그 원문에 가장 가까운 곳으로 **추정**했다 | 그 외 | PLAN_test_contract_gaps (2026-09-28) 리뷰 1회차 |
| `tests/test_output_contract.py:1461` `test_Dataset_이_코드와_이름을_따로_갖는다` | docstring Then 은 「`ticker` 와 `label` 이 둘 다 있고 **서로 다른 것을 담는다**」인데 단언은 둘 다 비어 있지 않은지만 본다. 미국 ETF 는 둘이 같으므로(`QQQ`) 「다르다」를 그대로 단언할 수는 없다 — Then 문구를 고치거나 국내 종목에서만 다름을 단언하는 두 갈래다 | 그 외 | PLAN_test_contract_gaps (2026-09-28) 리뷰 1회차 |
| `tests/test_output_contract.py:1404` `test_row_counts_의_키가_파일_이름이다` | docstring Then 은 「성적표·거래내역이 들어 있다」인데 단언은 거래내역(`TRADES_FILENAME`)만 본다 — `row_counts` 에서 성적표 키가 빠져도 통과한다 | 그 외 | PLAN_test_contract_gaps (2026-09-28) 리뷰 2회차 |
