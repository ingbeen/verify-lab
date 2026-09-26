# 감사 원문 — 문서·주석·코드 3자 불일치 감사

> **임시 근거물이다.** 경량화 시리즈 조사(2026-09-26)에서 읽기 전용 감사 에이전트가 낸 보고를 **가공 없이** 옮겼다.
> 줄 번호는 **HEAD `f55617a` 기준**이다 — 계획서 ①(`2c8d93f`)과 그 뒤 계획서가 파일을 고치면 줄이 밀리므로 **착수할 때 grep 으로 다시 찾는다.**
> 결정은 `REPORT_lightweight_inventory.md` §10 이 SoT 이며 이 문서의 「추천」과 다르면 §10 이 이긴다.
> 시리즈를 끝낼 때 함께 지운다. 살아있는 문서는 이 파일을 링크하지 않는다.

---

## 문서·주석·코드 3자 불일치 감사 결과 (읽기 전용)

**저장소 루트**: `/home/yblee/workspace/verify-lab/`. 표 안의 경로는 모두 이 루트 기준입니다. 행이 80여 개라 절대경로를 매번 쓰지 않았습니다.

**전제 두 가지를 먼저 알립니다.**
- 과제에는 "reverse 관련 미커밋 변경이 있다"고 적혀 있었는데, 실제 `git status` 는 비어 있었습니다. 그 변경은 HEAD `f55617a`(역방향 K=10 전환)에 이미 들어가 있어 커밋된 상태를 기준으로 봤습니다.
- 문서 관련 테스트 5개 파일(205건)은 지금 전부 통과합니다. `-p no:cacheprovider` 와 바이트코드 기록 끄기로 돌려 캐시를 만들지 않았습니다. 따라서 아래 불일치는 모두 테스트가 잡지 못하는 종류입니다.

**CLI 인자 대조 결과**: `docs/COMMANDS.md` 에 나오는 예시 인자는 전부 각 스크립트의 argparse 에 실재하고 값(choices)도 맞습니다. 확인한 인자는 `--dataset qqq|kodex200`, `--repeats`, `--seed`, `--ticker`, `--index`(yfinance·pykrx·선물·배수 둘), `--model usd_rate`, `--product KRDRVFUKQI`, `--nav`, `--adjusted`, `--indicative-value`, `--keyword`, `--stat`, `--series usdkrw_close`, `--ends`, `--start`, `--end`, validate 의 `--only-*`·`--cov` 입니다. 문서에만 있고 코드에 없는 플래그는 `--stop-grid` 하나이며 INDEX:73·140 에 현재형으로 적혀 있습니다(아래 1번 표).

---

### 1. 문서 → 코드 불일치

| 위치 | 원문 | 실제 | 판정 | 추천 |
|---|---|---|---|---|
| src/verify_lab/CLAUDE.md:469 | "`screen_verdict`(값 하나)를 `screen_candidates`(축별 집계표)가 부른다" | `screen_candidates` 정의 0건. screening.py:163·208 에는 `screen_verdict` 와 판정하지 않는 `direction_profile` 둘뿐이고, screening.py:17-19 는 "축별 판정표 함수를 두지 않는다"고 적음 | 존재하지 않는 함수 | 문서 수정 |
| src/verify_lab/CLAUDE.md:489 | "파일 이름의 소유자: `execution/constants.py` 의 네 상수" | execution/constants.py:42-43 에 둘뿐(성적표·거래내역). 같은 문서 :490 은 "체결 둘 + 측정 둘"이라고 적음 | 틀림(문서 내부 모순) | 문서 수정 |
| src/verify_lab/CLAUDE.md:473 | "성적표는 위·아래 두 행을 내고…실측으로 세 매매법 전 칸에서 0건" | 역방향은 `역방향 전체` 한 행(reverse/trading.py:474), 중간선거는 `위` 하나(midterm/constants.py:150). 매매법은 둘뿐(test_layer_contracts.py:1315). midterm/trading.py:40-41 은 "이 매매법이 그 관찰을 깬 첫 사례"라고 적음 | 낡음·모순 | 문서 수정 |
| src/verify_lab/CLAUDE.md:495, 497, 501, 514, 552, 557-563 | "옵션 만기일·월말은 둘 다 위/아래", "신호=사건", "세 매매법 모두 0", "(만기월 · 월)", rule 예시, 「구현할 수 없는 것 셋」의 주어 | 두 매매법의 코드는 삭제됨. 지금 그 자리에 있는 것은 중간선거_사이클(축 `사이클 위치`, 방향 `위`, 지수는 `손절불가`) | 삭제된 매매법을 현재형으로 서술 | 문서 수정 |
| src/verify_lab/CLAUDE.md:360 | "메타 타입 키: `<slug>` 하나" | run_futures_leverage.py:38 `futures_leverage_study`, run_leverage_tracking.py:31 `leverage_tracking_study`, run_usdkrw_equivalence.py:46 `usdkrw_equivalence_study` | 3곳 불일치 | 문서 수정 또는 코드가 틀림(확인 필요) |
| src/verify_lab/CLAUDE.md:38-39 | "`measure`·`report`·`execution` 은 `studies` 를 import 하지 않으며 test_layer_contracts.py 가 검사" | 테스트는 execution(:1239-1263)과 studies 끼리(:1103-1117)만 검사. measure·report 는 검사 없음. 현재 코드는 규칙을 지키고 있음(grep 0건) | 검사 범위 과장 | 문서 수정(또는 테스트 추가 판단) |
| src/verify_lab/CLAUDE.md:33-36 | 도식에서 `measure ↓ report` | 실제 의존은 report → measure(report/constants.py:10, report/tables.py). 도식에 없는 execution → measure·report 의존도 있음 | 방향 반대 | 문서 수정 |
| src/verify_lab/CLAUDE.md:606-609 | "현재 저장 대상" 표에 QQQ·069500 두 파일 | storage/market 에 50개 이상의 파일이 있음 | 낡음 | 문서 수정 |
| src/verify_lab/CLAUDE.md:727-728, 731 | "매매법을 재는 여섯 산출 지점(`studies/{reverse,option_expiry,month_end}` 와 매매 셋)", "검증 여섯 개" | test_layer_contracts.py:1356-1361 은 네 지점을 검사. option_expiry·month_end 패키지는 없음. studies 는 5개 | 낡음 | 문서 수정 |
| src/verify_lab/CLAUDE.md:796 | "이벤트가 없는 검증은 `measure/` 를 쓰지 않는다" | leverage_tracking(runner.py:25-41)과 futures_leverage(runner.py:47-54)는 measure 를 import. 이 문장이 맞는 것은 usdkrw_equivalence 하나 | 일반화 오류 | 문서 수정 |
| src/verify_lab/CLAUDE.md:5·272·317·602·708, scripts/CLAUDE.md:119 (루트 CLAUDE.md:305, session-bootstrap.md:41 도 같음) | "[.claude/rules/python.md](…)" | 저장소에 그 파일이 없음. 실제 파일은 `~/.claude/rules/python.md`(전역)이고 INDEX:39 만 이렇게 맞게 적음. 코드 주석 6곳도 같은 경로를 씀(3번 표) | 죽은 링크 | 문서 수정 |
| src/verify_lab/CLAUDE.md:67-70 | 계약 예시 `def find_events(df) -> pd.Series` | 그 이름의 함수는 없음. 실제는 `find_extreme_move_events(df, *, direction, rank_cut, start_date, ranks)`(extreme_move.py:75). 중간선거는 bool Series 계약을 쓰지 않음 | 예시와 실물이 다름(경미) | 문서 수정(예시임을 명시) |
| scripts/CLAUDE.md:45·47·51 | 메타 타입 `futures_leverage` · `leverage_tracking` · `usdkrw_equivalence` | 위와 같은 `*_study` 셋 | 불일치 | 문서 수정 또는 코드 확인 필요 |
| scripts/CLAUDE.md:105 | 인자 예시 "순위 컷 5/10/20, 집계 시작 연도" | run_reverse.py:122-140 에 그런 인자가 없음. COMMANDS:325 는 "인자가 아닙니다"라고 적음 | 존재하지 않는 인자 예시 | 문서 수정 |
| scripts/CLAUDE.md:156 | "예외는 둘뿐 — `TestRunSummaryOwnership`·`TestCliHelpRenders`" | scripts 소스를 보는 테스트가 더 있음: TestStudyOutputFiles 의 2건(test_layer_contracts.py:1499-1541), test_strategy_output_contract.py:927-943(`.csv` 문자열 검사) | 틀림 | 문서 수정 |
| scripts/CLAUDE.md:135 | "runner 가 낸 것을 `save_run_summary(directory, outputs.summary)` 로 그대로" | 매매 두 스크립트는 CLI 에서 `merge_run_summary` 로 합친 뒤 저장함(run_reverse.py:266, run_midterm_cycle.py:298). 테스트는 이 방식을 허용 | 불완전 | 문서 수정 |
| scripts/CLAUDE.md:74 | 임포트 순서 "…→ 유틸리티 → 상수" | 실제는 Ruff isort 알파벳순이라 상수 import 가 utils 보다 앞(run_reverse.py:22-79) | 경미 | 문서 수정 |
| tests/CLAUDE.md:222-223 | "재현 테스트는 test_measure_screening.py 에 — 보합 20%, 수정 전 0.70 / 실제 0.50" | 그런 테스트 없음. 가장 가까운 것은 :617 의 보합 10%(40/50) 테스트이고, 시기별 적중률 함수 자체가 삭제됨 | 낡음 | 문서 수정 |
| tests/CLAUDE.md:15 | "`test_*.py` 는 src 와 1:1" | test_strategy_* · test_studies_* 처럼 1:1 이 아님 | 경미 | 문서 수정 |
| .claude/rules/trading.md:252 | 상태 구동 예시 "원달러 그리드" | 그리드 코드는 삭제됨(tracks.py:100) | 삭제된 예시(경미) | 문서 수정 |
| .claude/rules/trading.md:363 | "역방향 매매의 손절 격자표(`합계·평균·승률·최악·갭손절`)가 이 형식" | 역방향은 −5% 한 종만 냄(reverse/trading.py:180). 격자는 규칙.md §3.5 기록으로만 남음 | 낡음 | 문서 수정 |
| docs/COMMANDS.md:284, 292-294 | "세 매매법 … `summary.json` 도 같은 여섯 칸(track·datasets·rule·row_counts·cost·notes)" | 실제 최상위 키는 `track, row_counts, cost, measure, trade` 다섯이고 datasets·rule·notes 는 그 아래에 있음(execution/run_summary.py:152-158, 산출물 2개 실측). 매매법은 둘 | 틀림 | 문서 수정 |
| docs/COMMANDS.md:330-331 | "`거는 방향` 과 `방향` 은 다른 컬럼" | `거는 방향` 컬럼은 코드에도 산출물에도 0건(없어진 1차_판정.csv 의 컬럼) | 존재하지 않는 컬럼 | 문서 수정 |
| docs/COMMANDS.md:335 vs 344-345 | "대상 목록은 인자가 아닙니다" / "`--dataset kodex200` 으로 고르면 그 종목만" | run_reverse.py:293-294 에서 `--dataset` 이 체결 대상도 좁힘 | 문서 내부 모순 | 문서 수정 |
| docs/COMMANDS.md:348 | "순열 검정이 없어 수 초" | 같은 실행이 `run_study`(순열 1000회)도 돎(run_reverse.py:297) | 낡음(스크립트가 둘이던 때의 문장) | 문서 수정 |
| docs/COMMANDS.md:353 (futures_leverage/__init__.py:3-4 도 같음) | "6쌍 × 3방식" | 방식은 4개(futures_leverage/constants.py:161-164). 같은 문서 :367 은 "넷" | 틀림 | 문서 수정 |
| docs/COMMANDS.md:140 | "미국달러선물 ETF — 원달러 그리드용" | 수정주가를 소비하는 쪽은 usdkrw_equivalence(constants.py:111·122) | 낡음 | 문서 수정 |
| docs/COMMANDS.md:154 | "지수 수집 (검증 #10 용 — 코스피·코스닥 네 계열)" | 국내 지수 계열을 읽는 현행 코드가 0건(INDEX_FILE_TEMPLATE 사용처는 중간선거의 GSPC·IXIC 뿐) | 용도 표기 낡음 | 문서 수정 |
| docs/COMMANDS.md:90, 136 | "다른 ETF·다른 시작일" 예시 `--ticker 069500 --start 20021014` | 기본값과 똑같음(check_pykrx_etf.py:32-33, collect_pykrx.py:36-37) | 경미 | 문서 수정 |
| docs/INDEX.md:73, 140 | "손절선 격자는 `--stop-grid` 로 켜고", "격자는 `--stop-grid`"(현재형) | 그 플래그는 어느 스크립트에도 없음. 73·75행은 셀이 9개로 헤더(7열)와 맞지 않음 | 존재하지 않는 CLI | 문서 수정 |
| docs/INDEX.md:62 (tracks.py:74 도 같음) | "이 표와 레지스트리를 test_tracks.py 가 대조" | test_tracks.py:266-282 는 코드가 있는 5개 매매법의 한글 이름이 INDEX 어딘가에 부분 문자열로 있는지만 봄. slug·등급 열은 검사하지 않음 | 과장 | 문서 수정 |
| docs/INDEX.md:43 | trading.md 로드 경로 "`docs/매매/**`·execution·studies" | frontmatter(trading.md:2-7)에는 `docs/검증/**`·`docs/조사/**` 도 있음 | 불완전 | 문서 수정 |
| docs/INDEX.md:273 | "없앤 판정표의 값은 `통계.csv`·`grid.csv` 에" | `grid.csv` 는 없음 | 틀림 | 문서 수정 |
| docs/INDEX.md:277-278 | "국내 두 파일은 collect_pykrx.py 로 한 번에", "같은 `_max.csv` 라도 종목에 따라 가격 기준이 다릅니다" | 한 번 실행에 파일 하나(collect_pykrx.py:244). `_max.csv` 는 언제나 원본가이고 수정주가는 `_adjusted_max.csv`(pykrx_collector.py:243, yfinance_collector.py:145) | 틀림 | 문서 수정 |
| .claude/rules/research.md:15 | "실물 예시: docs/context/ 의 두 문서" | docs/context 를 지우면 이 문장이 깨짐. 테스트는 이 문장을 보지 않음 | 개편 영향 | 개편할 때 함께 수정 |

### 2. 주석·docstring → 코드 불일치 (삭제된 매매법 언급 포함)

| 위치 | 원문 | 실제 | 판정 | 추천 |
|---|---|---|---|---|
| studies/midterm_cycle/__init__.py:3, 7-9, 11-13 | "10월 첫 거래일 종가 매수", "축은 «사이클 위치» 넷", "`measure/calendar_*` 의 기존 두 규칙" | ENTRY_MONTH=9(constants.py:132), CYCLE_POSITIONS 는 한 칸(:186). measure 에는 calendar_entry.py 하나만 있음 | 전면 낡음 | 주석 수정 |
| execution/__init__.py:5-6 | "경계는 폴더 단위다" | trading.md:15 와 src CLAUDE.md:47 은 "경계는 폴더가 아니라 «행위»" | 정반대 | 주석 수정 |
| studies/reverse/trading.py:1, 7-9 | "대상과 보유 한도를 순회…한도별 결과를 전부 산출해 나란히 낸다" | HOLD_LIMIT=2 고정(constants.py:271, NOTE:104). 실제로 도는 것은 대상 × 손절선(:213-243) | 틀림 | 주석 수정 |
| studies/reverse/constants.py:260-264 | "이 값을 고른 근거는 갭손절이 0건이 되는 첫 지점", "−4%~−10% 회당 +1.27~+1.46%" | 규칙.md:470 결정 ⑤ 는 "평평한 구간 안에서 최악 상한이 좁은 쪽 — 갭 근거는 2026-09-12 에 버렸다"이고, 수치는 +1.43~+1.66%. trading.md:144 도 같음 | 폐기된 근거를 현재형으로 적음 | 주석 수정(수치는 확인 필요) |
| studies/reverse/runner.py:211, 216-217, 683 / :235 | "다섯 표의 조각", "`blocks[0]` 부터 `blocks[4]`" / "네 표의 조각" | `_SpecBlocks` 필드는 4개(:227-230), `_ReverseAllBlocks` 는 3개(:247-249) | 개수 틀림 | 주석 수정 |
| scripts/run_reverse.py:127, studies/reverse/runner.py:289 | "국내 두 기준의 대조는 함께 돌려야 성립" | DATASETS 는 QQQ·KODEX 200 두 대상이고 둘 다 원본가(constants.py:138-155) | 낡음 | help·주석 수정 |
| measure/forward_return.py:24-25 | "원본가와 수정주가를 병기해야 하는 경우 호출 측이 두 번 돌린다" | 원칙 14 는 "두 기준을 나란히 내지 않는다"(src CLAUDE.md:291-294) | 정책과 모순 | 주석 수정 |
| measure/screening.py:15 | "`direction_profile` — 쓰는 곳: 월말의 집행 축" | 운영 코드 호출 0건(measure/__init__ 재수출과 테스트뿐). report/tables.py:554 `build_direction_table` 도 운영 호출 0건 | 낡음. 두 함수는 사실상 쓰이지 않음 | 주석 수정. 함수 존치 여부는 사용자 판단(삭제하지 않고 언급만) |
| measure/screening.py:77, 219-220 / report/tables.py:570 / report/constants.py:114 | "값은 `통계.csv` 계열이 기준선 14컬럼과 차이 4컬럼으로 담는다" | 역방향 통계.csv 는 18열이고 기준선이 없음. 차이 4열은 excess.csv 에 있음. 14+4 를 담는 것은 중간선거의 측정.csv(47열) | 틀림 | 주석 수정 |
| measure/screening.py:181 | "세 매매법 전 칸에서 0건" | 1번 표 :473 행과 같음 | 낡음 | 주석 수정 |
| measure/screening.py:191-192, execution/periods.py:113 | tradable 거짓의 예로 "인버스 실물" | 인버스 대상이 없음(src CLAUDE.md:475 도 "지금 없다") | 낡음 | 주석 수정 |
| execution/constants.py:6·87·101, common_constants.py:154, report/run_summary.py:7·9, execution/run_summary.py:37, measure/statistics.py:399, futures_leverage/position.py:25, validate_project.py:26 | "`strategy/<slug>_constants.py`", "`strategy/`", "`studies → strategy`", "`strategy/constants.py`" | `strategy/` 계층은 없음. 실제는 `execution/` 과 `studies/<slug>/constants.py` | 옛 계층 이름 | 주석 수정 |
| execution/constants.py:3·209, execution/run_summary.py:5, periods.py:122·337, reverse/trading.py:69·98·112, midterm/trading.py:15, midterm/constants.py:860, report/constants.py:186 | "세 매매법", "나머지 두 매매법" | 매매법은 둘(reverse·midterm_cycle) | 개수 낡음 | 주석 수정 |
| execution/trade_fill.py:8, 129-131, 452 / periods.py:15, 22 / execution/run_summary.py:25-27, 123 / report/constants.py:194, 201 / reverse/trading.py:400 / measure/distribution.py:7 / execution/constants.py:12, 205 | 옵션 만기일·월말을 현재 사용처로 적음 | `simulate_scheduled_trade`·`is_index`·`dividend_impact`·측정.csv 의 실제 사용처는 중간선거_사이클 | 삭제된 매매법 | 주석 수정 |
| execution/constants.py:243, 254, 259 | 출처 없이 "(결정 ㊵)", "(결정 ㊷)", "(결정 ㊶)" | 이 번호는 docs/조사/옵션_만기일/설계.md:241-243 의 것 | 가리키는 곳 불명확 | 주석 수정 |
| execution/constants.py:41 | "`검증/` 폴더 안은 영문 그대로 둔다" | 같은 폴더에 통계.csv·측정.csv(한글)가 있고, 경계는 「종류」(src CLAUDE.md:490) | 낡음 | 주석 수정 |
| execution/constants.py:53-54 | 역방향 문장은 "대상 × 순위 컷마다 손절선이 갈리는 사정" | 역방향 손절선은 −5% 한 종. 이름이 같은 `NOTE_STOP_BASE` 가 값을 달리해 두 곳에 있음(execution/constants.py:55, reverse/trading.py:103) | 근거 낡음. 같은 이름에 다른 값(src CLAUDE.md:206-210 원칙과 충돌) | 확인 필요 |
| report/constants.py:183 | 한글 파일 "성적표·거래내역·1차_판정·통계" | 1차_판정은 없고 측정.csv(:204)가 빠짐 | 낡음 | 주석 수정 |
| report/constants.py:113-115 | DISPLAY_SCREEN "판정표는 판정에 쓰는 축만 담으므로" | 판정표는 없고 1차 판정은 성적표의 컬럼(periods.py:278) | 낡음 | 주석 수정 |
| report/constants.py:234-235 | "`DISPLAY_HOLD_DAYS`(보유일)는 성적표의 평균 보유일" | `보유일` 은 거래내역에서 체결마다 쓰임(reverse/trading.py:444, midterm/trading.py:369). 평균은 `DISPLAY_MEAN_HOLD`(execution/constants.py:97) | 틀림 | 주석 수정 |
| report/run_summary.py:39, 65 | "여섯 산출 지점(검증 셋·매매 셋)", 예시 `expiry_count` | 산출 지점은 넷. `expiry_count` 사용 0건 | 낡음 | 주석 수정 |
| report/writer.py:5 / 78 | "`summary.json` 의 `datasets`·`rule` 이 말한다" / "손절선 격자처럼 옵션에서만 나오는 파일" | 실제로는 measure·trade 아래에 있음. 옵션에 따라 나오는 파일은 지금 없음 | 부정확·낡은 예시(규칙 자체는 유효) | 주석 수정 |
| common_constants.py:163-164 | KST 를 "결과 폴더 이름(`report/`)과 실행 이력이" 씀 | report 는 KST 를 쓰지 않음. 사용처는 수집기 5곳과 meta_manager | 낡음 | 주석 수정 |
| common_constants.py:133, data/pykrx_collector.py:393 | "(`docs/조사/월말_진입/설계.md` §7.4)" | 시가·고가·저가 0 서술은 §7.6(설계.md:590). §7.4 는 조회 가능 구간 | 절 번호 틀림 | 주석 수정 |
| studies/futures_leverage/constants.py:245 | "`docs/.claude/rules/docs.md`" | 실제 경로는 `.claude/rules/docs.md` | 경로 틀림 | 주석 수정 |
| studies/usdkrw_equivalence/__init__.py:4-5, scripts/run_usdkrw_equivalence.py:5 | "대체 불가면 그리드 백테스트의 ETF 경로가 폐기된다", "게이트" | 그리드 코드는 삭제됨 | 낡음 | 주석 수정 |
| scripts/data/collect_pykrx.py:8-9 | "원달러 그리드처럼…`--adjusted` 를 쓴다" | 현재 소비자는 usdkrw_equivalence 등 | 낡은 예시 | 주석 수정 |
| data/ecos_collector.py:91 | "python.md 규칙표를 따른다 (환율은 가격…2자리)" | python.md 표는 "소수 가격은 4자리"(옛 코드는 그대로 두도록 허용) | 규칙표를 잘못 인용 | 주석 수정 |
| midterm_cycle/constants.py:13, trading.py:26 | "`measure/calendar_*` 의 기존 규칙", "다른 매매법의 −2 ~ −10%" | 달력 규칙은 삭제됨. 역방향은 −5% 한 종 | 낡음 | 주석 수정 |
| reverse/trading.py:209-210 | "같은 파일의 기간이 네 번 반복" | 대상 2개이고 서로 다른 데이터셋 | 경미 | 주석 수정 |
| tests/test_layer_contracts.py:1269 / 1503 / 1439 | "`measure.screening.screen_candidates` 의 `tradable`" / "네 이름" / "매매법 셋" | 그 함수는 없음. 이름은 2개, 매매법은 2개 | 틀림 | 주석 수정 |
| tests/test_measure_screening.py:625-626 | "적중률이…60% 게이트를 못 넘어 제외된다" | 게이트는 기대값 하나(screening.py:205). 이 칸은 기대값 0.004 < 0.01 이라 제외됨 | 결론은 맞고 이유가 틀림 | 주석 수정 |
| tests/test_strategy_output_contract.py:162-163, 177, 207, 394-405, 879-882, 909 | `AXIS_OPTION_EXPIRY`·`AXIS_MONTH_END`·`EXPIRY_MONTH` 는 정의만 있음(사용 0). `EXPIRY_TARGET_DATE_COLUMN` 과 `target_date` 인자는 참으로 넘기는 곳이 없음. docstring "역방향·월말이 계속 그 이름을 낸다" | 삭제된 매매법의 잔재 | 죽은 코드와 낡은 주석 | 주석 수정. 상수 삭제는 사용자 판단 |

### 3. 주석 규칙 위반 (docs.md 「과거형이 허용되는 자리는 둘뿐」 기준)

「(2026-09-17 사용자 확정)」처럼 **결정의 출처를 밝히는 날짜**는 규칙상 허용되므로 제외했습니다. 추천은 모두 "시제만 현재형으로 바꾸고, 담긴 '왜'는 유지"입니다.

| 위치 | 원문(요지) | 유형 |
|---|---|---|
| tracks.py:6-8 | "스크립트가 등급을 박아 넘기던 시절에는" | 과거 상태 |
| measure/screening.py:7·65·71·102-104·172·178 | "걷어냈다", "기준선을 뺐다 (2026-09-15)", "`MIN_HIT_RATE`, 60% 가 함께 있었으나", "하한이 있던 시절에는" | 변경 이력, 값 인용 |
| execution/constants.py:50-51, 114, 203-205 | "두 매매법이 같은 문장을 한 벌씩 들고 있었고", "바꿨다", "월말은 measure, 옵션 만기일은 여기서 가져갔다" | 변경 이력 |
| execution/trade_fill.py:145-147 | "실제로 역방향의 −5% 가 기본값이었고" | 과거 상태 |
| report/constants.py:22-23, 96 · report/writer.py:16-17 · measure/statistics.py:222 · futures_leverage/position.py:72 · midterm_cycle/cycle_calendar.py:36 · reverse/constants.py:178-179 | "실제로 검증은 `시기` 매매는 `구간` 이었다", "도입할 때 실측 스크립트 둘이 그 상태였다", "식은 다섯 곳에 있었다", "두 벌이던 시절", "「첫 거래일」이던 시절", "연속 등락(테스트 B)을 분리한 뒤에도" | 과거 상태, 삭제된 매매법 |
| validate_project.py:23-24, 42 · scripts/run_futures_leverage.py:101-102 · scripts/run_usdkrw_equivalence.py:196-198 | "전에는 파싱에 실패하면 1 로", "전에는 `passed` 가 든 줄이면", "전에는 `full_period` 처럼", "전에는 파일명 상수와 별칭 키를" | 과거 상태 |
| measure/constants.py:6 (src CLAUDE.md:625, 713 도 같음) | "2-b(통계 집계)와 2-c(출력)", "2-a 가" | 개발 단계 표기 |
| tests: test_validate_project.py:77·144·229, test_layer_contracts.py:1249-1250·1338·1465-1467, test_strategy_output_contract.py:876-882·1285 | "전에 …", "전에는 … 이제 …", "(2026-09-16) … (2026-09-21) … 과도기" | 과거 상태 |
| 코드를 말로 옮긴 주석 (대표 예) | validate_project.py:89 "# Ruff 출력 표시", :123 · :183 동류, :270 "# --cov 옵션 검증", :275 "# 실행할 도구 결정", :289 "# 타이틀 생성", :303 "# 결과 수집", :307·314·321 "# N. Ruff 실행" 등 | 코드 번역 |
| 삭제한 코드를 주석으로 남긴 곳 | 0건 (정규식으로 전수 확인) | — |

### 4. 문서 ↔ 문서 불일치 중 코드가 판정하는 것

| 서술 A | 서술 B | 코드 판정 |
|---|---|---|
| COMMANDS.md:292 "summary.json 여섯 칸" | src CLAUDE.md:534-536 "`measure`·`trade` 두 칸으로 나눠 담는다" | **B 가 맞음.** 최상위 키는 track·row_counts·cost·measure·trade(execution/run_summary.py:152-158). src CLAUDE.md:538-548 의 「여섯 칸」 표는 trade 쪽 틀(build_run_summary)이라는 점을 밝혀야 함 |
| src CLAUDE.md:489 "네 상수" | 같은 문서 :490 "체결 둘·측정 둘" | :490 이 맞음 |
| 루트 CLAUDE.md 「값은 지우지 않았습니다」 · docs.md 마지막 절 · screening.py:77 "`통계.csv` 가 기준선 14 + 차이 4" | src CLAUDE.md:513, 521-525 "측정.csv 가 기준선을 담고, 통계.csv 는 축 전체" | **둘 다 부분적으로 틀림.** 역방향 통계.csv(18열)에는 기준선이 없고 차이 4열은 excess.csv 에 있음. 14+4 가 있는 것은 중간선거 측정.csv 뿐 |
| src CLAUDE.md:473 "세 매매법 전 칸 0건" | midterm_cycle/trading.py:40-41 "이 매매법이 그 관찰을 깬 첫 사례" | 지금은 두 매매법 모두 한 방향만 냄. 두 서술 다 현재 상태가 아님 |
| execution/__init__.py:6 "경계는 폴더 단위" | trading.md:15, src CLAUDE.md:47 "행위" | 규칙 문서가 SoT. 코드 docstring 이 틀림 |
| src CLAUDE.md:360·scripts/CLAUDE.md 표 "`<slug>`" | 스크립트 실제 키 `*_study` 셋 | 코드는 두 관용이 섞여 있음. 어느 쪽으로 맞출지는 확인 필요 |
| COMMANDS.md:353 "3방식" · futures_leverage/__init__.py "세 방식" | COMMANDS.md:367 "넷" | 넷이 맞음(constants.py:161-164) |
| INDEX:278 "종목에 따라 가격 기준이 다름" | src CLAUDE.md:611 "두 종목 모두 원본가" | src CLAUDE.md 가 맞음 |
| scripts/CLAUDE.md:156 "예외는 둘" | test_layer_contracts.py·test_strategy_output_contract.py | 최소 넷 |
| src CLAUDE.md:796 "이벤트 없는 검증은 measure 미사용" | 배수 검증 두 패키지의 import | usdkrw_equivalence 에만 맞음 |
| INDEX:39 "python.md 는 전역" | 루트·src·scripts CLAUDE.md, session-bootstrap, 코드 주석의 `.claude/rules/python.md` | INDEX 가 맞음. 저장소에는 그 파일이 없음 |
| INDEX:62 · tracks.py:74 "표와 레지스트리를 대조" | test_tracks.py:266-282 | 대조하는 것은 한글 이름 5개의 부분 문자열 존재뿐 |

### 5. 문서 구조를 강제하는 테스트 — 개편 때 무엇이 깨지나

| 테스트 | 검사 대상 | 무엇을 보나 | 깨지는 조건 |
|---|---|---|---|
| test_index.py `test_index_exists` | docs/INDEX.md | 파일이 있고 비어 있지 않음 | INDEX 삭제·이름 변경 |
| `test_index_links_resolve` | INDEX 의 모든 마크다운 링크 `[..](..)` (http·앵커 제외, `#` 뒤는 잘라냄) | docs/ 기준 상대 경로가 실재 | 링크 대상(docs/context/*, COMMANDS.md, .claude/rules/context.md 등)을 지우면서 INDEX 링크를 남길 때 |
| `test_all_documents_registered` | docs/·reference/ 아래 **모든 파일**(docs/INDEX.md, `docs/plans/`, `.gitkeep` 제외) | INDEX 에 **마크다운 링크로** 등록됐는지. 인라인 코드 표기는 등록으로 치지 않음 | INDEX 재설계로 링크가 빠진 파일이 생길 때(COMMANDS.md·MEMORY.md 포함), 새 문서를 추가할 때 |
| `test_core_documents_linked[CLAUDE.md]`, `[docs/context/README.md]` | INDEX | 두 문서가 링크돼 있는지 | **docs/context 를 지우면 반드시 실패.** 테스트 파라미터 수정이 필요함 |
| `test_bootstrap_rule_exists` / `_loads_unconditionally` | .claude/rules/session-bootstrap.md | 파일이 있고 frontmatter 에 `paths:` 가 없는지 | 파일 삭제, paths 추가 |
| `test_plans_folder_keeper_exists` | docs/plans/.gitkeep | 파일 존재 | .gitkeep 삭제 |
| `test_removed_documents_stay_removed` | docs/ROADMAP.md, docs/HANDS_ON.md, 다음세션_프롬프트.md, docs/research/CLAUDE.md | 없어야 함 | 그 이름으로 파일을 만들 때. 다른 이름의 진행 문서는 잡지 못함 |
| test_research_docs.py (대상은 `docs/{검증,매매,조사}/*/결과.md` 와 **`docs/{검증,매매,조사}/*.md`**) `test_research_documents_exist` | 위 대상 | 1개 이상 존재 | 모두 제거 |
| `test_filename_has_no_forbidden_prefix` | 위 대상 | `RESEARCH_` 접두사가 없어야 함 | 접두사 사용 |
| `test_related_section_exists` | 위 대상 | 정확히 `## 관련 파일` 인 줄 | 절 제목 변경·삭제 |
| `test_required_sections_exist` | 위 대상 | `^## (N.)?한계`, `^## (N.)?재현 방법` | 장 제목 변경 |
| `test_front_matter_declares_data_period` | 첫 `## ` 앞 머리말 | 「데이터 기간」 문자열 | 머리말에서 빠질 때 |
| `test_related_links_resolve` | 「관련 파일」 절(다음 `## ` 또는 `---` 까지)의 마크다운 링크 | 문서 위치 기준 실재 | **COMMANDS.md 를 삭제·이동하면 8개 문서가 실패**(역방향·중간선거·레버리지 괴리·만기_말일·선물·옵션 만기일·등가성 결과.md 는 `../../COMMANDS.md`, 원달러_조달.md 는 `../COMMANDS.md`). 내용만 줄이면 안전함(앵커 링크 0건) |
| `test_related_inline_paths_resolve` | 「관련 파일」 절의 백틱 경로 중 `/` 를 포함하고 `<` 가 없는 것. `없음`·`삭제`·`제거` 가 든 행은 건너뜀 | 저장소 루트 기준 실재. 글롭은 1건 이상 매치 | 코드·문서를 옮기고 표를 안 고쳤을 때 |
| `test_no_plan_references` | 문서 본문 전체 | `docs/plans`·`plans/PLAN_` 링크·인라인이 없어야 함 | 계획서를 참조할 때 |
| test_tracks.py `test_코드가_있는_매매법은_INDEX_이름표에_한글_이름이_있다` | docs/INDEX.md 본문 전체 | studies 패키지가 있는 slug 의 한글 이름(**역방향·중간선거_사이클·원달러_ETF_등가성·레버리지_ETF_괴리·선물_대_레버리지_ETF**)이 부분 문자열로 존재 | INDEX 재설계로 이 5개 문자열이 사라질 때. 표 모양·slug·등급 열은 검사하지 않음 |
| test_tracks.py 나머지 (RegistryShape·Lookup·GradeSemantics, `studies/*/constants.py` 의 `TRACK_NAME: Final = "…"` 등록 여부) | tracks.py, studies 코드 | 코드만 봄 | 문서 개편과 무관 |
| test_layer_contracts.py | src·scripts 의 `.py` 만(AST·소스 문자열) | .md 를 읽지 않음 | 문서 개편과 무관 |
| test_validate_project.py | validate_project.py 의 정규식 | 문서와 무관 | 문서 개편과 무관 |

추가 주의점:
- research.md:15 와 결과 문서 본문의 docs/context 링크(역방향/결과.md 2건, 원달러_ETF_등가성/결과.md 1건)는 테스트가 보지 않습니다. context 를 지워도 테스트는 통과하지만 죽은 링크가 조용히 남습니다.
- INDEX 재설계 중 `docs/{등급}/` 바로 아래에 새 `.md` 를 두면 결과 문서로 취급돼 위 7개 검사를 모두 받습니다.

---

### 개수 요약

| 구분 | 건수 |
|---|---|
| 1. 문서 → 코드 불일치 | 35행 |
| 2. 주석·docstring → 코드 불일치 | 34행 (죽은 코드 2묶음 포함: `direction_profile`·`build_direction_table` 운영 호출 0건, 테스트 상수 잔재) |
| 3. 주석 규칙 위반 | 과거형·이력 약 40곳(9묶음), 코드 번역 주석 대표 10여 곳, 삭제 코드 주석 0건 |
| 4. 문서 ↔ 문서 (코드가 판정) | 12쌍 |
| 5. 문서 강제 테스트 | 3개 파일·15개 검사가 문서를 읽음. layer_contracts·validate_project 는 문서 무관 |
| CLI 인자 대조 | COMMANDS 예시 전부 일치. 없는 플래그는 `--stop-grid` 1종(INDEX 2곳) |

**확인 필요로 남긴 것**: 메타 타입 키를 `<slug>` 와 `*_study` 중 어느 쪽으로 맞출지, 이름이 같은 `NOTE_STOP_BASE` 두 벌을 어떻게 할지, reverse/constants.py:260 의 수치(+1.27~+1.46)가 규칙 문서(+1.43~+1.66)와 다른 이유, 중간선거 측정.csv 의 `평균-비율 어긋남` 열이 영문 `False` 로 나가는 것. 마지막 항목은 src CLAUDE.md:679 가 영문 True/False 를 피한 근거와 같은 성격입니다.

**부수 사항**:
- 제가 파일을 하나 만들었습니다. 스크립트에서 test_research_docs 모듈을 import 할 때 바이트코드 끄기 전이라 `tests/__pycache__/test_research_docs.cpython-312.pyc` 가 생겼습니다. gitignore 대상이고 지시에 따라 지우지 않았습니다. 그 뒤 테스트 실행은 캐시를 만들지 않았고 `git status` 는 깨끗합니다.
- 대조용 스크래치 스크립트 둘(`extract_ids.py`, `extract_ids_src.py`)은 scratchpad 에만 있습니다: `/tmp/claude-1000/-home-yblee-workspace-verify-lab/908f1c29-ebf7-4e9b-becf-78c94e2b996a/scratchpad/`
- git 에는 없지만 `__pycache__` 만 든 옛 폴더 `src/verify_lab/strategy/`, `studies/month_end/`, `studies/option_expiry/` 가 디스크에 남아 있습니다. 테스트에는 영향이 없습니다.
- `docs/MEMORY.md` 는 이미 삭제된 `test_measure_calendar_exit.py`·`_month.py` 를 언급하지만, 실측 기록 문맥이라 표에 넣지 않았습니다.
