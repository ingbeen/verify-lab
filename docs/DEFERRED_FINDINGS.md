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

아래 줄 번호 기준: PLAN_midterm_qld_no_stop_grid 완료 시점의 작업 트리 (2026-09-29 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `tests/test_output_contract.py:366` `METHOD_SPECS["midterm_cycle"]` · `:694` `test_거래내역의_손절선도_같은_형식이다` | 중간선거의 「매매법 전부」 픽스처가 **기본 실행(무손절 한 종)**이라, 격자 실행(`stop_grid=True`)의 가격 손절 경로가 `_BY_METHOD` 계약(보유 중 최악 ≤ 최악 · 손익분기 대비 · 컬럼 순서)과 거래내역 손절선 형식 검사를 지나지 않는다. 격자 실행에서 `_trade_row` 가 손절선을 `-5` 로 적거나 손절 행의 보유 중 최악이 손절선보다 깊게 나와도 전 테스트가 통과한다. 격자 픽스처(`midterm_cycle_grid_outputs`, `:438`)는 `TestSingleColumnStopFilter` 와 판정 유도 테스트만 쓴다. 실제 산출물: 격자 실행은 좁히기 전 산출물과 바이트 동일이라 지금 발동하지 않는다 | 가벼운 버그 | PLAN_midterm_qld_no_stop_grid (2026-09-29) 리뷰 1 · 2회차 |
| `tests/test_studies_midterm_cycle_trading.py:237` `TestStopGridSwitch` | 스위치에 따른 `summary.json` `notes` 차이를 고정한 테스트가 없다 — 기본 실행은 `NOTE_STOP_CONFIRMED` 가 있고 `NOTE_STOP_BASE` 가 없으며, 격자 실행은 그 반대이고 순서도 좁히기 전과 같아야 한다. 조립 순서를 바꾸거나 `NOTE_STOP_CONFIRMED` 를 빼도 통과하고, 결과 문서의 「`--stop-grid` 실행은 `summary.json` 까지 바이트 동일」이 조용히 거짓이 된다. 이 클래스는 성적표만 보고 거래내역을 보지 않는다 | 가벼운 버그 | PLAN_midterm_qld_no_stop_grid (2026-09-29) 리뷰 1 · 2회차 |
| `tests/test_output_contract.py:438` `midterm_cycle_grid_outputs` | 공유 계약 `TestSingleColumnStopFilter`(`:930`)가 한 매매법의 스위치 실행에 기댄다(`docs/MEMORY.md` 「공유 계층의 테스트는 «자기 픽스처»를 갖는다」) — 중간선거 격자를 지우면 함께 무너진다. `period_rows` · `stop_level_value` 로 만든 합성 성적표로 옮기는 갈래가 있다. 같은 합성 시세를 두 번째 임시 폴더에 다시 쓰는 중복도 있다(`tests/test_studies_midterm_cycle_trading.py` 처럼 `datasets` 픽스처를 공유하면 된다) | 그 외 | PLAN_midterm_qld_no_stop_grid (2026-09-29) 리뷰 1 · 2회차 — 계획서 Risks 에서 받아들임 |

## 코드

줄 번호 기준: PLAN_midterm_qld_no_stop_grid 완료 시점의 작업 트리 (2026-09-29 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `src/verify_lab/studies/midterm_cycle/trading.py:1003` `run_midterm_cycle_trading` 의 `notes` 조립 | `NOTE_STOP_BASE`(「손절선은 진입가 기준 … 갭 청산은 손절선보다 더 잃는다」)를 `stop_grid` 로만 가른다 — `--ticker GSPC --stop-grid` 처럼 **지수만 돌린 격자 실행**은 손절선이 전부 `손절불가` 인데도 그 문구가 실린다. 바로 위 주석 「가격 손절선을 돈 실행에만 싣는다」와 어긋난다. `stop_grid and any(not d.is_index …)` 또는 실제로 돈 `stop_levels_run` 에 숫자가 있는지로 가르면 된다. 실제 산출물(인자 없이 · `--stop-grid` 전체 대상)에는 나오지 않는다 | 가벼운 버그 | PLAN_midterm_qld_no_stop_grid (2026-09-29) 리뷰 1 · 2회차 |
| `src/verify_lab/studies/midterm_cycle/trading.py:220` `NOTE_STOP_CONFIRMED` | `summary.json` 에 실리는 이 문구가 「확정 규칙이 사는 QLD 의 성적은 산출물에 없다」를 말하지 않는다 — 산출물만 여는 사람은 1배 무손절 행을 규칙의 성적으로 읽을 수 있다 | 그 외 | PLAN_midterm_qld_no_stop_grid (2026-09-29) 수정분 검증 |
| `scripts/run_midterm_cycle.py:143` `--stop-grid` help · `:18` 모듈 docstring · `src/verify_lab/studies/midterm_cycle/trading.py:28` 모듈 docstring | 격자 값 「−5 ~ −30%」를 손으로 적었다 — `constants.STOP_LEVELS_ETF` 에서 유도할 수 있어, 격자를 바꾸면 `--help` 가 틀린 범위를 보여 준다. 같은 파일의 `--ticker` help 가 `DATASETS` 로 기본값을 그리는 관용이 있다 | 그 외 | PLAN_midterm_qld_no_stop_grid (2026-09-29) 리뷰 1 · 2회차 |
| `src/verify_lab/studies/midterm_cycle/constants.py:577` · `trading.py:26` · `tests/test_output_contract.py:660` 의 「그 규칙의 1배 측정 기준」 | 「대상 QQQ 의」 한정어가 없다 — 기본 산출물에는 SPY · DIA 의 무손절 행도 있는데 확정 규칙의 1배 기준은 QQQ 행뿐이다(`docs/매매/중간선거_사이클/규칙.md` §2 머리말은 「대상 QQQ 의 행」으로 적는다). 같은 문구가 `설계.md:223` · `규칙.md:381` 에도 있다 | 그 외 | PLAN_midterm_qld_no_stop_grid (2026-09-29) 수정분 검증 |

## 문서

줄 번호 기준: PLAN_midterm_qld_no_stop_grid 완료 시점의 작업 트리 (2026-09-29 확인).

| 자리 | 무엇 | 종류 | 출처 |
| --- | --- | --- | --- |
| `.claude/rules/trading.md:124` 「기간 손절을 손절로 인정하는 경우」의 중간선거 문장 | 「9개월 보유에서 좁은 가격 손절은 합계를 무너뜨리고 넓은 것은 한 번도 발동하지 않아」에 「1배」 한정어가 없다 — 확정 규칙이 QLD(2배)로 바뀌어, QLD 는 2018 보유 중 −41.95% 로 −25 · −30% 에도 닿는다(`규칙.md` §3 손절 행이 그 사실을 적는다). 위험을 작게 읽히는 쪽이다. 이번 변경 전부터 있던 문장이다 | 그 외 | PLAN_midterm_qld_no_stop_grid (2026-09-29) 수정분 검증 |
| `docs/매매/중간선거_사이클/규칙.md:327` §2.9 표 「1배 전액 (규칙의 측정 기준)」 행 | 값(+5.41 · +0.61 · 최저 −19.99)은 **3분할** 1배다. 2026-09-29 뒤 확정 규칙의 1배 기준은 QQQ(2014 +8.38 · 2018 +0.51 · 최저 −22.78)라, 「규칙」을 현재 규칙으로 읽으면 낙폭이 얕게 보인다. 탈락안 기록 절이라 2026-09-23 규칙으로 읽을 여지는 있다. 이번 변경 전부터 있던 라벨이다 | 그 외 | PLAN_midterm_qld_no_stop_grid (2026-09-29) 수정분 검증 |
| `docs/매매/중간선거_사이클/결과.md:79` §1 한 줄 요약 | 「최악 −23% 까지 밀리며」는 1배 값인데, 바로 뒤에서 규칙이 QLD 전액이라고 말하면서 QLD 의 보유 중 −41.95% 는 적지 않는다. 틀린 값은 없지만 규칙을 안전하게 읽히게 한다 | 그 외 | PLAN_midterm_qld_no_stop_grid (2026-09-29) 수정분 검증 |
| `docs/매매/중간선거_사이클/규칙.md:50` §1.2 인용 · `:380` §3 손절 행 | 「넓은 손절선은 발동하지 않았다」 · 「9개월 보유에서 가격 손절에 평평한 구간이 없다」가 낫표 안에 있지만 원문 그대로가 아니다(가장 가까운 원문은 §2.2 「−25% 이상은 한 번도 발동하지 않아 무손절과 같다」와 `.claude/rules/trading.md:124`). 전역 규칙은 따옴표를 원문 표시로 쓴다 | 그 외 | PLAN_midterm_qld_no_stop_grid (2026-09-29) 수정분 검증 |
| `docs/매매/중간선거_사이클/규칙.md:380` §3 손절 행의 「−10% 는 … QLD 2014 · 2018 · 2022 세 해」 | QLD 2022 보유 중 최저가 −10.04% 라 −10% 경계를 0.04%p 차로 넘는다 — 시세를 다시 받으면 이 셈이 뒤집힐 수 있다(§2.5 는 재수집 뒤 다시 재라고 적는다) | 그 외 | PLAN_midterm_qld_no_stop_grid (2026-09-29) 수정분 검증 |
| `src/verify_lab/CLAUDE.md:301` 「데이터 저장 규칙」 🔴 표 · `scripts/CLAUDE.md:105` | 「좁혀 돌린 실행이 폴더를 덮는다」만 다루고 **넓혀 돌린 실행**(`--stop-grid`)이 git 추적 산출물 폴더를 덮는 경우가 없다 — 재수집 뒤 `결과.md` §12 를 갱신하려고 `--stop-grid` 만 돌리고 커밋하면 145행 격자 성적표가 기본 산출물처럼 남는다. 매매법 문서(`결과.md` §15 · `설계.md` ㉑)와 스크립트 docstring · help 에는 적혀 있다 | 그 외 | PLAN_midterm_qld_no_stop_grid (2026-09-29) 리뷰 2회차 |
| `src/verify_lab/CLAUDE.md:472` 「매매 산출물 계약」 행 제목 | 「손절선 축은 두 매매법 모두 기본이 확정 칸 하나다」가 매매법 개수를 적는다(전역 「구체적 수치와 가변 정보를 직접 적지 않는다」) — 매매법이 늘거나 하나가 격자 기본으로 돌아가면 조용히 거짓이 된다 | 그 외 | PLAN_midterm_qld_no_stop_grid (2026-09-29) 리뷰 1 · 2회차 |
| `.claude/rules/trading.md:90` 「손절선 축도 같은 조건으로 좁힐 수 있습니다」의 중간선거 문단 | 「§2.2 에 적었습니다」가 과거형이다 — `.claude/rules/docs.md` 「과거형이 허용되는 자리는 둘뿐입니다」가 `.claude/rules/` 를 현재형 자리로 둔다. 바로 위 역방향 문단(`:86` 「§3.5 에 적었습니다」)도 같은 모양이며 이번 변경 전부터 있다 | 그 외 | PLAN_midterm_qld_no_stop_grid (2026-09-29) 리뷰 1 · 2회차 |
