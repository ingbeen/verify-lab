# 경량화 시리즈 백로그 — 고치지 않고 남긴 지적

> **임시 문서다.** 경량화 시리즈(계획서 ① ~ ⑧, 2026-09-26 ~ 09-28)를 끝내며 시리즈 문서를 지우기 전에
> 미처리 지적만 옮겨 둔 것이다(2026-09-28 사용자 결정). 다음 계획서가 범위를 고를 때 쓰고, 다 처리하거나
> 버리기로 하면 지운다. 살아있는 문서는 이 파일을 링크하지 않는다.
>
> **기준**: HEAD `fa62c93` 트리에서 2026-09-28 에 자리를 다시 확인했고 **전부 미해결**이었다. 줄 번호는 그 시점 값이다.
> **원문**(리뷰 지적의 따옴표 원문 · 결정 · 계획서별 진행 로그)은 git 에 있다.
>
> ```
> git show fa62c93:docs/plans/REPORT_lightweight_inventory.md   # §10 결정 · §12 백로그 원문
> git show fa62c93:SLIM_SERIES.md                              # 계획서별 인계 메모
> git show fa62c93:docs/plans/PLAN_slim_3_dead_code.md          # 계획서 진행 로그 (파일 이름의 숫자 1 ~ 8)
> ```
>
> ID 의 접두는 보고서 §12 의 절이다 — `R`(①) · `S`(②) · `T`(③) · `R4-`(④) · `R5-`(⑤) · `RV6-`(⑥) · `RV7-`(⑦) · `F`(⑧).

---

## 1. 결정이 필요한 것

| ID | 자리 | 무엇 |
| --- | --- | --- |
| R12 | `src/verify_lab/measure/calendar_entry.py` | 남은 함수가 `validate_trading_days` 하나이고 쓰는 곳도 중간선거 `cycle_calendar.py` 하나 — 모듈 이름·위치가 역할과 어긋나고 「정의가 하나뿐인 것은 공유 계층에 두지 않는다」와도 어긋난다 |
| T2 | `tests/test_measure_screening.py:270` `TestSingleOwner` | 저장소에 없는 `MIN_HIT_RATE` 의 부재만 봐 늘 참 — 성적 산식이 게이트를 다시 써도 통과한다 |
| T3 (= R4-5) | `tests/test_output_contract.py` `TestCoverage` | `OUTPUT_FIXTURES` 만 레지스트리와 대조한다. 다른 계약 테스트는 픽스처 목록을 손으로 적어 새 매매법을 조용히 건너뛸 수 있다 |
| T4 | `tests/test_studies_reverse_trading.py:270` | 합성 시세에서 컷 5 · 20 의 신호 수가 같아 `wide >= narrow` 가 등호로만 통과한다 — `_market` 픽스처를 바꿔야 한다 |
| T5 | `tests/` · `src/verify_lab/*/__init__.py` | 「재수출하지 않는다」를 docstring 선언 말고 강제하는 장치가 없다 |
| T7 | `execution/constants.py:82` `보유일` · `report/constants.py:230` `보유 거래일` | 같은 값(체결 하나의 보유 거래일 수)에 헤더가 둘 — 합치면 중간선거 `측정.csv` 헤더가 바뀐다(값 변경 커밋) |
| R4-1 | 루트 `CLAUDE.md:348` | 「이 프로젝트는 저장소 밖의 경로를 참조하지 않습니다」가 전역 `~/.claude/` 포인터들과 어긋나 보인다 |
| R4-2 | 루트 `CLAUDE.md:119` (원칙 17) | 「위 DIA 6월처럼 뒤 절반과 최근 5년이 음수여도」 — 위 문단에 뒤 절반 회당값이 없어 전제를 확인할 수 없다 |
| R5-9 | `docs/매매/역방향/결과.md` §6.3 · §6.4 · §9.1 · §9.2 | 네 표 모두 기준선 비율 열이 없고 §9.1 · §9.2 는 중앙값도 없다(원칙 4 · 11). 역방향 전체의 기준선은 대칭 모집단이라 50% 근처다 |
| RV6-1 (= R5-13 · R5-14) | `measure/statistics.py:242` `mean_rate_conflict` · `:272` `yes_no` | 표본 0건 칸이 NaN 비교로 「아니오」가 되고, nullable `boolean` 의 NA 는 빈칸이 된다. 지금 산출물에서 발동 0건. 고치면 판정 로직이 바뀐다 |
| RV7-1 | `docs/조사/원달러_ETF_등가성/설계.md` §4 | 결정 표가 `# · 항목 · 확정 · 근거` — 탈락안 열이 없다. 옮긴 결정 기록이라 채우면 새 판단이 된다 |
| RV7-2 | 괴리 · 선물 · 등가성 문서 | 국내 종목을 코드로만 적은 표(`261240` · `122630` 등) — 루트 「코드만 적지 않습니다」 |
| ③ Non-Goals | `studies/midterm_cycle/trading.py:251` · `runner.py:130` | `_Accumulator` 두 벌 · 과설계 |
| ③ Non-Goals | `futures_leverage` ↔ `leverage_tracking` | 배수형 두 검증의 내부 컬럼 토큰 통합 |
| ③ Non-Goals | `scripts/run_reverse.py:173` `_print_rule` | 상수에서 손절선을 찍어 체결 기본값과 출처가 둘이다(지금은 같은 값) |

## 2. 문서·주석 — 고칠지 정할 것

| ID | 자리 | 무엇 |
| --- | --- | --- |
| F1 | `docs/조사/연속_등락/결과.md:403` | 「5.3 의 QQQ 연속 하락 1일 차이 +0.28%p」 — ⑦ 이 §5.1 ~ §5.8 을 지워 그 절도 값도 문서에 없다 |
| F2 | `docs/조사/원달러_ETF_등가성/결과.md:339` (54행도) | 「0.9707 은 합격선(0.98)에 3%p 못 미친다」 — 합격선까지는 0.93%p, 3%p 는 1.0 까지의 거리 |
| F4 (= RV7-4) | `studies/usdkrw_equivalence/alignment.py:8` | 매매기준율을 「이 검증의 기준 가격」이라 적는다 — 기준은 종가 15:30(결정 C15) |
| F5 | `studies/futures_leverage/constants.py:137` · `comparison.py:6` · `:350` | 「사용자가 실제로 하는 것」·「사용자 질문에 직접 답하는 열」 — 개인 운용 서술(Q1 L2) |
| F7 | `docs/조사/레버리지_ETF_괴리/결과.md:103` · `:281` | 「왕복 수수료 0.4%」 — 240행은 수수료 + 슬리피지 왕복, 503행은 「왕복 거래비용」 |
| F11 | `docs/매매/중간선거_사이클/결과.md:154-155` | 한 인용 문단에 붙은 물결표 둘(`6~8건` · `2~3%p`)이 취소선으로 렌더된다 |
| R7 | `reference/데이터처리_설계원칙.md` · `reference/test_examples/conftest_example.py` | INDEX 말고 인용하는 곳이 없다 |
| T8 | `tests/test_measure_screening.py:13` | 「하나»만«」 겹화살괄호 방향 |
| R4-9 | `execution/trade_fill.py:8·80·83·130·336·452` · `execution/run_summary.py:27` · `execution/constants.py:52` · `execution/periods.py:22` · `measure/calendar_entry.py:8` · `measure/distribution.py:7` | 공유 계층 주석이 지금 소비자(중간선거_사이클)를 이름으로 적는다 — 소비자가 바뀌면 다시 낡는다 |
| R5-17 | `docs/매매/중간선거_사이클/규칙.md` 머리말 | 1배 다섯(SPY · DIA · QQQ · S&P 500 · 나스닥 종합)의 행 수가 없다(`.claude/rules/docs.md` 요구) |
| R5-18 | `docs/매매/중간선거_사이클/설계.md` 결정 ⑳ 「대가」 | 「`규칙.md` §2.5 머리에 … 데이터 기간」 — 레버리지 기간은 문서 머리말에 있다 |
| RV6-5 | `measure/distribution.py:195` · `data/pykrx_collector.py` `collect_pykrx_index` · `studies/reverse/constants.py:205` | 코드 docstring 에 실측 건수·값(QQQ 배당 89건 등)이 들어 있다 — 전역 「가변 수치를 적지 않는다」 |
| 새 발견 | 코드 51줄(35개 파일 — `src` · `scripts` · `tests`) · 괴리 · 선물 문서 4장 · 루트 `CLAUDE.md` 원칙 15 | 옛 「검증 #N」 번호(예: `run_study` docstring 「검증 #9 를 실행한다」). ⑧ 은 COMMANDS 제목에서만 걷었다 |

## 3. 작은 코드 — 고칠지 정할 것

| ID | 자리 | 무엇 |
| --- | --- | --- |
| R4-4 | `tests/test_layer_contracts.py:124` `_FILENAME_SHAPE` | `[^\s/\\]*\.csv` 를 `fullmatch` 해 `"/성적표.csv"` · `str(d) + "/거래내역.csv"` 같은 경로 포함 리터럴이 검사를 빠져나간다 |
| R4-10 | `execution/constants.py:56` · `studies/reverse/trading.py:102` | `NOTE_STOP_BASE` 두 벌, 문구가 다르다 — 합치면 역방향 `summary.json` 이 바뀐다 |
| R4-14 | `studies/reverse/trading.py:374` · `runner.py:1031` | 식별 키 투영 가드(`_identity`)가 같은 패키지에 두 벌 |
| R5-15 | 선물 `integer_contracts.csv`(24줄) · `roll_events.csv`(328줄) | 불린 열(`집행가능` · `규칙대로 못 한 롤`)이 영문 `True`/`False` 로 나간다 — 고치면 산출물이 바뀐다 |
| R5-19 | `tests/test_studies_midterm_cycle_runner.py:259` | 어긋남 테스트가 `⊆ {예, 아니오}` 만 봐 runner 에서 「예」 경로를 밟지 않는다 |
| RV6-3 | `studies/midterm_cycle/runner.py:320` | 예/아니오 변환을 호출처가 한다 — 다음 매매법이 `mean_rate_conflict` 를 그대로 넣으면 영문 `True`/`False` 가 다시 나간다 |

## 4. 기록만 — 고치지 않기로 했거나 운영 사항

| ID | 무엇 |
| --- | --- |
| T6 (= R4-6 · R4-13) | `collect_pykrx_nav` · futures `run_study` 의 주입 인자를 걷어 테스트 입구가 사라지고 형제 함수와 API 가 갈렸다 — Q8 ④ 로 사용자가 정한 제거 |
| R4-15 | 커밋 `9c224e3` 에 `full_period.csv` 값 변경과 INDEX 등록이 함께 들어갔다 — 사용자 선택 |
| R5-12 (= RV6-2) | 어긋남 열이 `판정가능` 의 `JUDGEABLE_YES/NO` 를 빌려 쓴다 — 사용자가 유지로 정함(2026-09-28) |
| ⑥ 분량 | 달력 조사 한 장 셋의 합 2,096줄 — 계획 목표(약 1,450 ~ 1,750) 초과 |
| 로컬 잔재 | 디스크의 미추적 폴더 `src/verify_lab/studies/expiry_monthend/`(`__pycache__` 만) — 로컬 정리 대상 |

## 5. 이 정리의 범위 밖

- **공개 저장소의 git 이력** — HEAD 에서 지운 개인 운용 정보가 이력에는 남아 있다. 이력까지 지울지는 경량화와 별개의 판단으로 미뤘다(보고서 §1)
