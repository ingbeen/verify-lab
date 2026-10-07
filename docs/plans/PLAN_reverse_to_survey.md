# Implementation Plan: 역방향을 조사로 내리고 코드를 지운다

> 작성/운영 규칙(SoT): `/impl-plan` 스킬(`~/.claude/skills/impl-plan/SKILL.md`)을 반드시 참고하세요.  
> (이 템플릿을 수정하거나 새로운 양식의 계획서를 만들 때도 해당 스킬을 포인터로 두고 준수합니다.)

**상태**: ✅ Done

---

> 상태는 🟡 Draft / 🔄 In Progress / ✅ Done. Done 조건과 기록 규칙은 `/impl-plan` 「3) 스킵 및 완료 규칙」이며 `~/.claude/hooks/plan_lint.py` 가 저장 때 검사한다.

---

**작성일**: 2026-10-06 22:25
**마지막 업데이트**: 2026-10-07 09:31
**관련 범위**: studies/reverse(삭제) · 공유 계층(measure · report · execution — 역방향만 쓰던 것 삭제) · tracks · 테스트 · 문서 전반
**관련 문서**: `src/verify_lab/CLAUDE.md` · `tests/CLAUDE.md` · `scripts/CLAUDE.md` · `.claude/rules/docs.md` · `.claude/rules/research.md` · `.claude/rules/trading.md` · `docs/INDEX.md` · `docs/COMMANDS.md`

---

## 1) 목표(Goal)

사용자 결정(2026-10-06): **역방향을 조사 등급으로 내리고 코드를 지운다. 성과와 분석은 한 장짜리 조사 문서로 요약해 남긴다.**
걸지 않기로 한 이유는 **「조금 더 긴 텀의 매매를 하기로 함」** 이다.

- [x] 목표 1: `docs/조사/역방향.md` 한 장이 지금 세 문서(`docs/매매/역방향/` 의 설계 · 결과 · 규칙)의 결론 · 성적 · 근거 · 원자료를
      담고, **이 저장소의 다른 파일이 가리키는 앵커를 전부** 갖는다
- [x] 목표 2: 역방향 코드(패키지 · 실행 스크립트 · 전용 테스트)와 **공유 계층에서 역방향만 쓰던 정의**를 지운다
- [x] 목표 3: `tracks.py` 의 역방향 줄을 **조사 · 성질 조사**로 바꾸고, 다른 매매법·조사의 산출물이 **바이트 단위로 그대로**다
- [x] 목표 4: 저장소 안에 `매매/역방향` 경로와 지운 코드 이름을 가리키는 곳이 남지 않는다

## 2) 비목표(Non-Goals)

- **가격 기준 전환(원본가 → 수정주가)** — 별도 계획서로 한다(이 계획서가 Done 된 뒤). 이 계획서는 숫자를 바꾸지 않는다
- **조사 셋(원달러_ETF_등가성 · 레버리지_ETF_괴리 · 선물_대_레버리지_ETF)과 실측 프로브 셋의 코드** — 그대로 둔다(사용자 결정 2026-10-06)
- **시세 파일** — `QQQ_max.csv` · `069500_max.csv` 와 그 수정주가 파일은 남긴다. 중간선거와 레버리지_ETF_괴리가 쓴다
- **역방향 재측정** — 새 문서의 수치는 `62894fa` 시점의 문서·산출물 값을 **그대로 옮긴 것**이다
- **공유 계층 리팩토링** — 고아가 된 정의를 지우는 것 말고는 손대지 않는다
- `reference/` — 읽기 전용이라 손대지 않는다(`reference/test_examples/` 가 forward return 예시를 담아도 그대로 둔다)

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

- 사용자가 더 긴 보유의 매매를 하기로 해 역방향(1 ~ 2일 보유)을 걸지 않는다. 등급의 SoT 는 `tracks.py` 한 줄이다
- **선례는 「조사로 내리면 코드를 지운다」다** — 옵션_만기일 · 월말_진입 · 만기_말일 · 원달러_그리드가 그렇게 했고,
  `tests/test_tracks.py` 의 `test_조사_등급은_종류도_조사다` 가 그 결과(조사 = 성질 조사)를 고정한다. 코드를 지우므로
  이 불변조건과 충돌하지 않는다(코드를 남기는 안은 사용자가 기각 — 2026-10-06)
- **공유 계층에는 쓰는 곳이 있는 함수만 둔다**(`src/verify_lab/CLAUDE.md`). 역방향을 지우면 고아가 되는 정의가 생긴다

### 역방향을 지우면 고아가 되는 공유 계층 정의 — 실측 (2026-10-06)

호출 그래프 도달성으로 셌다 — 역방향 밖의 매매법·조사·스크립트를 뿌리로 두고, 역방향을 뿌리에서 뺐을 때 도달하지
못하게 되는 공유 계층(`measure` · `report` · `execution` · `utils` · `data` · `common_constants.py`) 정의다.
**이름 기반이라 같은 이름이 다른 모듈에 있으면 고아를 놓친다(과소 집계)** — 아래 ※ 셋이 그렇게 빠졌다가 손으로 찾은 것이다.

| 모듈 | 고아가 되는 정의 |
| --- | --- |
| `measure/forward_return.py` | `compute_forward_returns` · `DEFAULT_HORIZONS` · `NEXT_OPEN_HORIZONS` · `_basis_horizons` · `_empty_result` · `_validate_signals` · ※`REQUIRED_MARKET_COLUMNS` · ※`RESULT_COLUMNS` · ※`_validated_horizons` (남는 것: `ReturnBasis` — 중간선거 · 반감기 · `count_excluded` — 중간선거) |
| `measure/baseline.py` | `below_moving_average` · `BelowMovingAverage` (남는 것: `simple_moving_average` · `DEFAULT_MA_WINDOW` · `MIN_MA_WINDOW` 는 Phase 2 에서 재확인) |
| `report/tables.py` | `build_signal_table` · `build_statistics_table` · `build_excess_table` · `build_test_table` · `horizon_label` · `_basis_label` · `_sorted_cells` · `_sorted_single_basis_cells` |
| `report/constants.py` | `SIGNALS_FILENAME` · `BASIS_LABELS` · `BASIS_ORDER` · `DISPLAY_BASELINE` · `DISPLAY_POPULATION` · `DISPLAY_OBSERVED_MEAN` · `DISPLAY_OBSERVED_MEDIAN` · `DISPLAY_OBSERVED_UP_RATE` · `DISPLAY_OBSERVED_DOWN_RATE` · `DISPLAY_NULL_P05` · `DISPLAY_NULL_P95` · `DISPLAY_MEAN_PERCENTILE` · `DISPLAY_MEDIAN_PERCENTILE` · `DISPLAY_UP_RATE_PERCENTILE` · `DISPLAY_DOWN_RATE_PERCENTILE` |
| `execution/constants.py` | `DISPLAY_PARAMETER` · `DISPLAY_START_YEAR` · `DISPLAY_CHANGE_RATE` · `DISPLAY_EVENT_ID` · `PARAMETER_PREFIX_RANK_CUT` |
| `common_constants.py` | `PRICE_DECIMALS_KRW` |

- **`execution/trade_fill.simulate_signal` 은 남는다** — `simulate_scheduled_trade` 가 안에서 부른다(중간선거 · 반감기)
- 측정 함수 `measure/statistics.py` 의 `summarize` · `excess` · `permutation_test` 는 다른 매매법이 써서 남는다

### 지울 코드와 그 테스트

| 구분 | 경로 |
| --- | --- |
| 패키지 | `src/verify_lab/studies/reverse/` (7파일 · 2,229줄) |
| 실행 스크립트 | `scripts/run_reverse.py` (337줄) |
| 역방향 전용 테스트 | `tests/test_studies_reverse_runner.py` · `test_studies_reverse_trading.py` · `test_studies_extreme_move.py` · `test_studies_daily_change.py` · `test_studies_annotations.py` (5파일 · 3,041줄) |
| 고아 정의의 테스트 | `tests/test_measure_forward_return.py`(`TestCountExcluded` 만 남김) · `tests/test_measure_baseline.py`(`below_moving_average` 10건) · `tests/test_report_tables.py`(표 빌더 24건) |
| 공용 테스트 안의 역방향 | `tests/test_output_contract.py` 15건 · `tests/test_layer_contracts.py` 4건 + 허용목록 · `tests/test_report_writer.py`(`TRACK_NAME = "reverse"` 픽스처 19건) |
| 산출물 | `storage/results/매매/역방향/` 전체 |

### 다른 파일이 가리키는 역방향 문서의 앵커 — 새 문서가 반드시 가져야 하는 것 (실측 2026-10-06)

`매매/역방향` 경로는 **26개 파일 · 60곳**이 가리킨다(지울 파일 포함). 그중 앵커를 단 것:

| 앵커 | 가리키는 곳 |
| --- | --- |
| 설계 「확정된 설계 결정」 ⑥ · ⑫ · ⑭ ~ ⑯ · ⑰ · ⑲ · ⑳ · ㉑ · ㉓ · ㉔ · ㉕ · ① ~ ⑬ | `src/verify_lab/CLAUDE.md` 12곳 · 공유 계층 주석 |
| 설계 「사전 실측 기록」 · 결론 1 ~ 4(특히 결론 4 — 수정주가 3,000거래일) · §8 | `src/verify_lab/CLAUDE.md` · `docs/INDEX.md` · 조사 문서 셋 · 수집기·프로브 주석 |
| 설계 「가격 처리」 | 수집기 둘의 주석 |
| 설계 「통계 처리와 강건성」 · 「부가 출력」 · 「없앤 판정표를 되살리려면」 · §4 ~ §7 | `src/verify_lab/CLAUDE.md` · `measure/` 주석 |
| 규칙 결정 ② · ⑤ · ⑥ · ⑭ · §1 | `.claude/rules/trading.md` · 중간선거 설계 · 옵션_만기일 · `src/verify_lab/CLAUDE.md` |
| 규칙 머리말(수치가 시세 기간에 묶여 있다) | 루트 `CLAUDE.md` 「재수집은 이미 나온 결과를 바꿉니다」 · `report/run_summary.py` |

**`.claude/rules/trading.md` 가 역방향 실측을 근거로 인용한다**(15줄 — 무손절 최악 −17.45% 대 −5% 최악 −5.00% · 좁은 손절선의
승률 붕괴 · 갭손절 건수 · 노출 비율 0.15 ~ 1.22% 등). 근거가 사라지지 않도록 **그 수치 전부를 새 문서에 원문 그대로 둔다.**

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- `.claude/plan-config.json` — 이 저장소의 검증 명령·자동 포맷·근거 승격 목적지 (**값의 SoT**)
- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 · 측정의 원칙 · 「결과 보고의 원칙」
- `docs/MEMORY.md` — 「이름만 바꾸는 변경과 값을 바꾸는 변경을 한 커밋에 섞지 않는다」
- `src/verify_lab/CLAUDE.md` — 계층 간 계약 · 「공유 계층에는 쓰는 곳이 있는 함수만 둡니다」 · 데이터 저장 규칙
- `.claude/rules/docs.md` · `.claude/rules/research.md` · `.claude/rules/trading.md`
- `tests/CLAUDE.md` · 전역 `~/.claude/rules/python.md` · `~/.claude/rules/python-tests.md`
- `scripts/CLAUDE.md`
- 선례: `docs/조사/만기_말일.md` 「재현 방법」 · `docs/조사/연속_등락/결과.md` 「재현 방법 — 코드가 제거됐다」

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] `docs/조사/역방향.md` 가 필수 구조(`.claude/rules/research.md`)와 「걸지 않기로 한 규칙과 그 근거」를 갖고, 위 앵커 표의 앵커와 `trading.md` 가 인용하는 수치를 전부 갖는다
- [x] 체결 원자료(KODEX 200 51건 · QQQ 7건)와 신호 원자료가 행 수까지 원본과 같다
- [x] 역방향 코드 · 전용 테스트 · 산출물 폴더 · `docs/매매/역방향/` 가 지워졌다
- [x] 공유 계층 고아 정의와 그 테스트가 지워졌고, 삭제 뒤 도달성 집계에서 **고아 0건**이다
- [x] 공용 계약 테스트에서 역방향을 뺀 뒤에도 **공유 계약(시기 구간 · 판정가능 · 빈칸 저장 등)은 남은 매매법으로 검사된다**
- [x] 남은 매매법·조사 다섯을 다시 돌려 `storage/results/` 의 diff 가 역방향 폴더 삭제뿐이다
- [x] 저장소(`.git` · `storage` · `docs/plans` 제외)에 `매매/역방향` · `studies.reverse` · `run_reverse` · 지운 정의 이름이 남지 않는다(새 문서의 「재현 방법」 안의 복원 경로는 예외)
- [x] 회귀/신규 테스트 정리 (`test_tracks.py` 의 강등 목록에 `reverse` 추가)
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — `docs/INDEX.md` 변경 · `docs/COMMANDS.md` 변경(역방향 절 삭제) · 루트 `CLAUDE.md` 변경 · `src/verify_lab/CLAUDE.md` 변경 · `.claude/rules/trading.md` 변경 · `tests/CLAUDE.md`(Phase 3 에서 판단 — 변경 있음)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다 (사용자 결정과 근거를 새 문서 「걸지 않기로 한 규칙과 그 근거」·「재현 방법」에 옮겼다)
- [x] 미룬 지적 옮김 — 고치지 않은 리뷰 지적을 거르는 기준으로 걸러 `docs/DEFERRED_FINDINGS.md` 로 옮겼다 (1건 옮김 · 거른 것은 진행 로그)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- **새로 만든다**: `docs/조사/역방향.md`
- **지운다**: `src/verify_lab/studies/reverse/` · `scripts/run_reverse.py` · 역방향 전용 테스트 5파일 · `docs/매매/역방향/` 세 문서 · `storage/results/매매/역방향/`
- **고친다 (코드)**: `src/verify_lab/tracks.py` · `measure/forward_return.py` · `measure/baseline.py` · `report/tables.py` · `report/constants.py` · `execution/constants.py` · `common_constants.py` · 역방향 경로를 주석에 둔 공유 계층·수집기·프로브(`measure/statistics.py` · `report/run_summary.py` · `report/writer.py` · `execution/trade_fill.py` · `execution/run_summary.py` · `measure/distribution.py` · `data/yfinance_collector.py` · `data/pykrx_collector.py` · `scripts/data/collect_pykrx.py` · `collect_yfinance.py` · `check_pykrx_etf.py` · `check_pykrx_splice.py`)
- **고친다 (테스트)**: `test_tracks.py` · `test_output_contract.py` · `test_layer_contracts.py` · `test_report_writer.py` · `test_measure_forward_return.py` · `test_measure_baseline.py` · `test_report_tables.py` · `test_execution_trade_rows.py`(「세 매매법」 docstring) · `test_studies_midterm_cycle_runner.py`(「형제 두 매매법」 docstring)
- **고친다 (문서)**: `docs/INDEX.md` · `docs/COMMANDS.md` · 루트 `CLAUDE.md` · `src/verify_lab/CLAUDE.md` · `scripts/CLAUDE.md`(요약 표의 `reverse` 행) · `.claude/rules/trading.md` · `.claude/rules/docs.md`(역방향 1줄) · `docs/조사/옵션_만기일.md` · `월말_진입.md` · `만기_말일.md` · `연속_등락/결과.md`(경로 · 재현 방법) · `docs/매매/중간선거_사이클/설계.md` · `규칙.md` · `docs/검증/반감기_사이클/설계.md`(결정 근거 속 `horizon_label` 1곳)
- `docs/COMMANDS.md`: **변경 있음** — 「매매법·조사 실행」의 역방향 절을 지운다

### 데이터/결과 영향

- 산출물: `storage/results/매매/역방향/` 이 사라진다. **다른 산출물은 바이트 단위로 그대로여야 한다** — 이 계획서는 값을 바꾸지 않는다
- 원시 시세: 변화 없음
- 문서의 수치: 새 문서는 `62894fa` 의 문서·산출물 값을 옮긴다. **데이터 기간은 원문 머리말 그대로** 적는다(QQQ 1999-03-10 ~ 2026-09-24 · 6,929 거래일, KODEX 200 2002-10-14 ~ 2026-09-23 · 5,911 거래일 — Phase 1 에서 원문과 대조)

## 6) 단계별 계획(Phases)

> Phase 0(레드)은 두지 않는다 — 새 정책·산식이 없고, 지우는 작업의 회귀는 Phase 2 의 도달성 집계와 산출물 바이트 대조가 잡는다.

### Phase 1 — 요약 문서 `docs/조사/역방향.md` 작성 (코드는 아직 그대로)

> 문서를 먼저 쓰는 이유: 원문 세 문서와 산출물이 아직 있어 **옮긴 값을 그 자리에서 대조**할 수 있다.

**구성** — 선례 `docs/조사/만기_말일.md` 를 따른다

| 장 | 담는 것 | 원문 |
| --- | --- | --- |
| 머리말 | 「걸지 않기로 한 규칙의 기록이다(2026-10-06 사용자 결정)」 · 코드 없음 · 수치는 그때의 측정 기록 · 대상 · **데이터 기간 · 판정 구간(2005-01-01 이후)** · 가격 기준(원본가) · 비용 미반영 · 재현 스크립트 삭제 · **수치가 시세 기간에 묶여 있다는 문장**(루트 `CLAUDE.md` 가 예로 든다) | 세 문서 머리말 |
| 관련 파일 | 묘비 표기(`삭제` · `없음`)로 지운 경로 · 남는 시세·수집기 · 커밋 `62894fa` | — |
| 1. 결론 요약 | 근거 표 + 한 줄 요약 | 결과 §1 · 규칙 머리 |
| 2. 문제 정의 | 역대급 등락 뒤 반대로 거는가 | 결과 §2 |
| 3. 대상과 근거 소스 | 시세 파일 · 기간 · 행 수 | 결과 §3 |
| 4. 용어 정의 | 역방향 전체 · K · 사건 · 기준선 | 결과 §4 |
| 5. 측정 결과 | 1 ~ 21 거래일 성적(역방향 전체) · 방향별 · 평균-비율 어긋남 · 사건 단위 · 무작위 뽑기 대조 핵심 | 결과 §5 ~ §9 |
| 6. 확정했던 규칙과 그 성적 | 규칙 표(§1) · 성적표 10행 · 무손절 대조 · 손절선 격자(§3.5) · 보유 한도 대조 · 노출 비율 · **`trading.md` 가 인용하는 수치 전부** | 규칙 §1 ~ §3 |
| 7. 걸지 않기로 한 규칙과 그 근거 | 2026-10-06 사용자 결정 「조금 더 긴 텀의 매매를 하기로 함」 · 코드를 지운 이유(선례 · 조사 = 성질 조사 불변조건) | 이 계획서 |
| 8. 설계 결정 | **외부가 가리키는 결정은 원래 번호를 유지**해 「확정 / 탈락안 / 근거」 한 줄씩(위 앵커 표의 번호 전부) · 사전 실측 기록 · 결론 1 ~ 4 · 가격 처리 · 통계 처리와 강건성 · 부가 출력 · 없앤 판정표를 되살리려면 | 설계 전체 · 규칙 §3 |
| 9. 해석 · 10. 한계 | | 결과 · 규칙 |
| 11. 원자료 | **체결 원자료 전부**(규칙 §5.1 · §5.2 — 51 + 7행) · **신호 원자료 전부**(결과 §8.1 · §8.2 — 51 + 7행, 1일 ~ 1개월 원지수 수익률). **두 표를 합치지 않고 그대로 옮긴다** — 합치면 날짜 조인이라는 가공이 끼어든다 | 규칙 §5 · 결과 §8 |
| 12. 재현 방법 | `git checkout 62894fa -- <경로…>` 로 꺼낼 파일 표 · 공유 계층에서 지운 정의를 옮겨 붙일 목록(위 고아 표) · 꺼낸 뒤 품질 검증 · 원문 세 문서를 보는 법(`git show 62894fa:docs/매매/역방향/<문서>.md`) | 선례 `만기_말일.md` §13 |

**작업 내용**:

- [x] 원문 세 문서와 산출물(`storage/results/매매/역방향/`)에서 **값을 도구로 뽑아 옮긴다** — 눈으로 다시 타이핑하지 않는다
- [x] 위 구성대로 `docs/조사/역방향.md` 를 쓴다. 세부 표 원문은 「`62894fa` 의 `docs/매매/역방향/<문서>.md` §N」으로 가리킨다
- [x] 원문에서 그대로 가져온 문장은 따옴표로, 고쳐 쓴 요약은 내 문장으로 가른다(전역 「문장」 규칙)
- [x] `docs/INDEX.md` 의 역방향 행에 새 문서 링크를 **더한다**(옛 링크는 Phase 2 에서 걷는다) — `tests/test_index.py` 는
      실재하는 문서의 INDEX 등록을 검사하므로 등록하지 않으면 이 Phase 에서 그린이 깨진다

**Validation**:

- [x] `pytest tests/test_index.py tests/test_research_docs.py` 통과 — 새 문서의 등록과 「관련 파일」 표 경로 실재(묘비 행 제외)

- [x] 원자료 행 수 대조 — 체결 원자료 58행 = 규칙 §5 표 행 수 = `거래내역.csv` 행 수, 신호 원자료 58행 = 결과 §8.1 · §8.2 표 행 수
- [x] 원자료 값 대조 — 옮긴 두 표를 원문 두 표와 줄 단위로 비교해 차이 0줄(스크립트)
- [x] 앵커 대조 — 위 앵커 표의 결정 번호 · 절 이름이 새 문서에 전부 있다(스크립트로 목록 대조)
- [x] `trading.md` 가 인용하는 역방향 수치(−17.45 · −5.00 · +72.26 · +76.65 · 60.78 · 64.71 · +0.87 · +0.82 · −5.85 · 0.15 · 1.22 · 0.38 등) 가 새 문서에 그대로 있다(grep)
- [x] 머리말 데이터 기간이 원문 머리말과 같다

---

### Phase 2 — 코드 삭제와 공유 계층 정리 (그린 유지)

**작업 내용**:

- [x] 삭제 전 산출물 기준점 확인 — `git status --short storage/results/` 가 비어 있다(지금 HEAD 와 같다)
- [x] `src/verify_lab/studies/reverse/` · `scripts/run_reverse.py` · 역방향 전용 테스트 5파일 · `storage/results/매매/역방향/` 를 지운다
- [x] **같은 Phase 에서 `docs/매매/역방향/` 세 문서를 지우고 INDEX 의 역방향 행을 새 문서 하나로 바꾼다**(코드 「없음」 · 상태 「걸지 않음」) —
      `tests/test_research_docs.py` 가 옛 결과 문서의 「관련 파일」 표 경로(지울 패키지 · 스크립트 · 테스트) 실재를 검사하므로, 코드만 지우면 그린이 깨진다
- [x] `tracks.py` — 역방향 줄을 `GRADE_SURVEY` · `KIND_PROPERTY` 로 바꾸고 「걸지 않기로 해 실행 코드가 없다」 주석 묶음으로 옮긴다
- [x] `test_tracks.py` — `test_걸지_않기로_한_매매법은_조사_등급이다` 의 목록에 `reverse` 를 넣는다
- [x] 공유 계층 고아 정의를 지운다(Context 의 표). **`forward_return.py` 는 남는 `ReturnBasis` · `count_excluded` 에 맞춰 모듈 설명을 다시 쓴다**
- [x] 고아 정의의 테스트를 지운다 — `test_measure_forward_return.py`(`TestCountExcluded` 만 남김) · `test_measure_baseline.py`(`below_moving_average` 10건) · `test_report_tables.py`(표 빌더 24건)
- [x] 🔴 **`TestCountExcluded` 세 건은 입력을 `compute_forward_returns` 로 만든다** — 지우는 함수에 기대지 않게
      long-form 합성 프레임(`COL_BASIS` · `COL_HORIZON` · `COL_EXCLUDED_REASON`)을 직접 만드는 자기 픽스처로 바꾼다(`tests/CLAUDE.md` 「공유 계층의 테스트는 «자기 픽스처»를 갖는다」).
      바꾼 뒤 `count_excluded` 를 일부러 깨 세 건이 실패하는지 보고 되돌린다
- [x] 공용 테스트에서 역방향을 뺀다. **15 + 4건을 하나씩 「역방향 고유 동작 → 지움」 / 「공유 계약을 역방향으로 검사 → 남은 매매법으로 옮김」으로 가르고, 그 판정표를 진행 로그에 남긴다**
  - `test_output_contract.py` — 시기 5행 · 하한 미달 행 유지 · 0건 구간 빈칸 · 사건 정수형 · 0건 구간 「판정 안 함」은 공유 계약(`execution/periods.py`)이므로 **남은 매매법의 픽스처로 같은 계약이 이미 검사되는지 먼저 확인하고, 없으면 옮긴다**
  - `test_layer_contracts.py` — 매매법 집합 `{"reverse", "midterm_cycle", "halving_cycle"}` · 레이블 겹침 허용목록의 역방향 경로 · `horizon_label` 을 쓰는 검사
  - `test_report_writer.py` — `TRACK_NAME` 을 살아 있는 매매법 slug 로 바꾸고 `studies.reverse` import 를 지운다. 라벨 검사의 임의 문자열 픽스처(`" 역방향\n"` 등)는 그대로 둔다
- [x] 남은 매매법·조사 다섯을 인자 없이 다시 돌린다 — `run_midterm_cycle.py` · `run_halving_cycle.py` · `run_leverage_tracking.py` · `run_futures_leverage.py` · `run_usdkrw_equivalence.py`

**Validation**:

- [x] 도달성 집계 재실행 — 역방향이 없는 트리에서 「뿌리에서 도달하지 못하는 공유 정의」가 0건이다(이름 충돌 ※ 셋은 손으로 재확인)
- [x] `git diff --stat storage/results/` 가 `매매/역방향/` 삭제만 보인다(다른 산출물 바이트 불변)
- [x] 바뀐 테스트 파일과 `tests/test_index.py` · `tests/test_research_docs.py` · `tests/test_tracks.py` 를 골라 `pytest` 로 돌려 통과한다(전체 품질 검증은 마지막 Phase)

---

### Phase 3 — 문서·주석 참조 정리 (그린 유지)

**참조를 셋으로 가른다** — (가) 경로 → `docs/조사/역방향.md` 「…」로 바꾼다 · (나) 역방향이 «지금» 있다고 말하는 현재형 서술 → 고치거나 지운다 ·
(다) 지금 구조의 «근거»로 든 역방향 사례 → 근거로 남기고 가리키는 곳만 바꾼다

**작업 내용**:

- [x] `docs/INDEX.md` — (이름표 행은 Phase 2 에서 끝냈다) 「찾는 것 → 어디」의 pykrx 행 ·
      표 아래 「달력 조사 셋은 한 장 안의 「걸지 않기로 한 규칙과 그 근거」 절」 · 「되살리는 절차」 두 문장에 역방향을 넣는다
- [x] `docs/COMMANDS.md` — 역방향 절 삭제
- [x] 루트 `CLAUDE.md` — 「재수집은 이미 나온 결과를 바꿉니다」의 예시 경로
- [x] `src/verify_lab/CLAUDE.md` — 역방향 32줄을 (가)(나)(다)로 가른다. **이벤트 정의 계약 · forward return 반환 계약 · 집계 3표 · 방향 축 · 확장창 순위 같은 절은 「지금 그 계약을 지키는 생산자·소비자가 남는가」로 판단해, 남지 않으면 지우고 남으면 생산자를 고친다**
- [x] `.claude/rules/trading.md` — 「이 길에 있는 것은 역방향입니다」 문단(손절선 축 좁히기의 현재 사례)을 지우고, 근거로 인용한 실측 수치는 남긴 채 가리키는 곳만 새 문서로 바꾼다
- [x] `scripts/CLAUDE.md` — 실행 스크립트 요약 표의 `reverse` 행 삭제
- [x] `.claude/rules/docs.md` · 조사 문서 넷 · 중간선거 설계·규칙 · 반감기 설계 — 경로·사례 정리
- [x] 🔴 `docs/조사/연속_등락/결과.md` 「재현 방법」 — 지금은 「지운 축의 diff 를 **지금의 `studies/reverse/`** 에 손으로 되돌려 넣는다」라
      역방향 패키지가 있어야 성립한다. **「먼저 `62894fa` 에서 역방향을 꺼낸다(`docs/조사/역방향.md` 「재현 방법」)」를 앞에 붙인다**
- [x] `docs/검증/반감기_사이클/설계.md` 의 `horizon_label` — 확정된 설계 결정의 근거 기록이라 **(다)로 남긴다.** 그 함수가 지워졌다는 사실만 괄호로 붙일지는 그 줄을 읽고 정해 진행 로그에 남긴다
- [x] 공유 계층·수집기·프로브 주석의 경로(Scope 의 코드 목록) — 새 문서 앵커로
- [x] 🔴 **근거가 사라지는 주석 (나)** — 역방향이 있어서 지금 구조가 이렇다고 말하는 문장은 지우거나 고친다:
      `execution/constants.py` 「역방향은 이 상수를 쓰지 않는다 … 두 문장이 갈라져 있는 것은 그래서다」 ·
      `report/constants.py` 「역방향은 `통계.csv` 를 낸다」 · `execution/run_summary.py` 「역방향은 측정 격자가 체결 대상보다 넓다」.
      반대로 **기본값을 두지 않는 이유 · 매매법끼리 import 를 막는 이유**로 역방향 사례를 든 문장(`execution/constants.py` 머리 · `trade_fill.py`)은 (다)로 남긴다.
      「역방향 부호」(부호를 뒤집는다는 개념어)는 매매법 이름이 아니라 그대로 둔다
- [x] `tests/CLAUDE.md` — 「산식 고정 테스트」가 지운 함수를 이름으로 가리키는지 보고, 가리키면 고친다(변경 여부를 진행 로그에 기록)
**Validation**:

- [x] `grep -rn "매매/역방향\|studies\.reverse\|run_reverse"` (`.git` · `storage` · `docs/plans` 제외) 가 새 문서 「재현 방법」 밖에서 0건
- [x] 지운 정의 이름(Context 표) grep 이 새 문서 「재현 방법」 밖에서 0건
- [x] 새 문서를 가리키는 앵커(「…」 · 결정 번호)가 새 문서에 실재한다(스크립트 대조)

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

> 🔴 **체크박스와 상태를 먼저 확정하고, `/commit` 은 맨 마지막에** — 이유는 `/impl-plan` 「5) Commit Messages」.

- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` 변경 있음 — 역방향 절 삭제)
- [x] 자동 포맷 적용 (`poetry run black .`)
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] Validation 절에 `/code-review` 와 품질 검증 **실행 결과**를 적는다
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정
- [x] 🔴 **마지막에 `/commit` 을 실행하고 그 후보를 «이 계획서» 의 `#### Commit Messages` 절에 옮긴다** —
      대화에만 내면 그 절이 빈 채로 남는다. **커밋은 사용자가 한다 — 후보만 낸다**

**Validation**:

> 순서는 `/code-review` → 품질 검증이다. 고칠 것 · 회차 상한 · 수정분 검증은 `/impl-plan` 의 `review.md` 가 정한다.

- [x] `/code-review xhigh` **1회차** (발견 13건 — 버그 4 [무거움 4 · 가벼움 0] · 그 외 9 · 조치: 버그 4 수정 · 그 외 중 이 계획서 Phase 3 범위의 남은 참조·서술 4건 정리 · 나머지 그 외 5건 미조치)
- [x] `/code-review xhigh` **2회차** (발견 11건 — 버그 3 [무거움 2 · 가벼움 1] · 그 외 8 · 조치: 버그 3 수정 · 그 외 중 이 계획서가 만든 부정확함 3건 정리 · 나머지 그 외 5건 미조치)
- [x] 수정분 검증 (수정 1건 · 발견 0건 — 무거움 0 · 조치: 해당 없음 — 1차 검증의 무거움 1건을 사용자 결정으로 고친 뒤 다시 돌린 결과다. 1차 경과는 진행 로그)
- [x] `poetry run python validate_project.py` (passed=1454, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다** — 추측으로 적은 줄은 그대로 나간다.

1. 검증 / 역방향 조사 등급 이관과 실행 코드 삭제
2. 검증 / 역방향 세 문서를 조사 한 장으로 통합 · 패키지 · 실행 스크립트 · 전용 테스트 · 산출물과 공유 계층 고아 정의 45개 삭제
3. 검증 / 긴 보유 매매로의 방향 전환에 따른 역방향 매매 중단과 코드 정리
4. 검증 / 역방향 삭제에 맞춘 공유 계약 테스트의 남은 매매법 이전과 자기 픽스처 전환
5. 검증 / 역방향 걸지 않음 기록 — 남은 산출물 바이트 불변 확인 · 복원 기준 커밋 62894fa 명시

## 7) 리스크(Risks)

- **요약이 근거를 잃는다** — 1,938줄을 한 장으로 줄이면 다른 문서가 가리키던 근거가 빠질 수 있다.
  완화: 외부 앵커와 `trading.md` 인용 수치를 Validation 에서 기계적으로 대조하고, 세부 표는 `62894fa` 원문을 가리킨다
- **공유 계약의 검사가 함께 사라진다** — 공용 계약 테스트 일부가 역방향 픽스처로만 시기 구간·빈칸 계약을 검사한다.
  완화: Phase 2 에서 하나씩 판정해 남은 매매법으로 옮기고 판정표를 진행 로그에 남긴다
- **이름 기반 도달성 집계가 고아를 놓친다** — 같은 이름이 다른 모듈에 있으면 살아 있는 것으로 센다(이미 ※ 셋을 놓쳤다).
  완화: 삭제 뒤 재집계 + 모듈별 손 감사 + Ruff 미사용 검사 + `TestDisplayLabelLiveness`
- **산출물이 조용히 바뀐다** — 공유 계층을 지우다 남은 매매법의 경로를 건드리면 숫자가 바뀌어도 예외가 안 난다.
  완화: 남은 다섯을 재실행해 `storage/results/` 바이트 대조
- **diff 가 크다** — 삭제가 대부분(코드 약 2,600줄 + 테스트 약 3,000줄 이상 + 문서 1,938줄)이라 검토가 어렵다.
  완화: 진행 로그에 Phase 별 삭제 목록을 남기고, 커밋 후보에 범위를 밝힌다
- **복원 커밋 `62894fa` 뒤 공유 계층이 바뀌면 꺼낸 코드가 맞지 않는다** — 선례 `만기_말일.md` 와 같은 경고를 「재현 방법」에 둔다

## 8) 메모(Notes)

- 사용자 결정 (2026-10-06): ① 역방향만 조사로 내린다 — 조사 셋·프로브 코드는 둔다 ② 역방향 코드를 지운다(코드를 남기고 조사 + 매매법 종류를 허용하는 안 기각) ③ 문서는 한 장 `docs/조사/역방향.md` ④ 걸지 않는 이유: 조금 더 긴 텀의 매매를 하기로 함
- 같은 대화에서 정한 가격 기준 결정(조사 = 원본가 기록 · 매매·검증 = 수정주가 · 신호 판정도 수정주가 · 원본 종가 대조 칸 없음)은 **다음 계획서**의 입력이다 — 이 계획서는 다루지 않는다
- 복원 기준 커밋: `62894fa` (계획서 작성 시점 HEAD — 역방향 코드·문서·산출물이 전부 있는 마지막 커밋)
- 도달성 집계 스크립트는 세션 스크래치(`reach.py`)에 있다 — 저장소에 넣지 않는다

### 진행 로그 (KST)

- 2026-10-06 22:25: 계획서 작성
- 2026-10-06 22:25 ~ 22:32: 자체 검증 — 1회차(전제 사실 대조): 신호 원자료 출처 §7 → §8 · `TestCountExcluded` 가 지울 함수로 입력을 만듦 ·
  `scripts/CLAUDE.md` 의 `reverse` 행 누락 · `연속_등락` 재현 절차가 역방향 패키지를 전제 — 4건 반영.
  2회차(다른 로직 영향): 근거가 사라지는 주석 3곳 · INDEX 표 아래 두 문장 — 2건 반영. 재실행할 다섯 스크립트는 외부 호출이 없음을 확인(grep 0건).
  3회차(훅 규약 · 테스트 공백 · 데이터 영향) — 개선 없음.
  4회차(Phase 간 그린 유지) — 2건 반영: Phase 1 에서 새 문서를 INDEX 에 올리지 않으면 `test_index` 가 깨지고, Phase 2 에서 코드만 지우면
  옛 결과 문서의 「관련 파일」 경로 검사(`test_research_docs`)가 깨진다 → 새 문서 등록을 Phase 1 로, 옛 문서 삭제와 INDEX 행 교체를 Phase 2 로 옮김.
  문서 본문을 읽는 테스트는 그 둘과 `test_tracks`(INDEX 의 한글 이름)뿐임을 확인(grep).
  5회차(Non-Goals 경계 · DoD 와 Phase 대응) · 6회차(삭제 대상과 남는 정의의 경계 — `simulate_signal` · `count_excluded` · `ReturnBasis`) ·
  7회차(되살리는 절차의 성립 — 연속_등락이 역방향 위에 서 있음까지 반영됨) — 개선 없음, 3회 연속이라 멈춤
- 2026-10-06 22:32: 사용자 승인(「진행」) — Phase 1 착수
- 2026-10-06 22:40: Phase 1 완료 — `docs/조사/역방향.md` 1,294줄(원문 세 문서 1,938줄). 표 51개 · 491줄은 커밋 `62894fa` 원문에서
  줄 번호로 끼워 넣었고(스크래치 `splice.py` — 표 경계를 단언), 성적표 10행은 그 커밋의 `성적표.csv` 값 그대로다.
  검증: 원자료 네 표 51 · 7 · 51 · 7행이 원문과 줄 단위로 같음 · `거래내역.csv` 58행과 일치 · 앵커 제목 15종과 설계 결정 ①~㉗ ·
  규칙 결정 ①~⑭ 누락 0 · `pytest tests/test_index.py tests/test_research_docs.py` 108 passed.
  🔴 **계획서의 trading.md 인용 수치 목록 중 0.15 · 1.22 · 0.38(노출 비율)은 역방향 문서가 아니라 trading.md 자체의 실측 표**라
  새 문서에 둘 대상이 아니었다(계획 작성 때의 오인). 역방향 문서를 근거로 인용한 수치(trading.md 102 · 103 · 138 · 141 · 143 · 151 · 152 · 157 · 158행)는 전부 있다
- 2026-10-06 23:02: Phase 2 완료.
  삭제 — 역방향 패키지 7파일 · `scripts/run_reverse.py` · 전용 테스트 5파일 · `storage/results/매매/역방향/` 7파일 · `docs/매매/역방향/` 3문서.
  공유 계층 — Context 표 그대로 지웠고, **계획 표에 없던 고아 하나를 더 지웠다: `ReturnBasis.NEXT_OPEN`**(지운 함수와 레이블에서만 쓰였다).
  그 여파로 `tests/test_measure_statistics.py` 의 「칸 4개」 검사가 `for basis in ReturnBasis` 로 두 기준을 만들다 깨져, 두 번째 기준을
  픽스처가 직접 만들게 고쳤다(칸 세기의 기준 축을 무시하는 변형을 잡음 확인).
  `forward_return.py` 는 `ReturnBasis`(CLOSE 하나) · `count_excluded` 만 남기고 모듈 설명을 다시 썼다. `baseline.py` 는 `simple_moving_average` ·
  `DEFAULT_MA_WINDOW` · `MIN_MA_WINDOW` 만 남는다.
  `TestCountExcluded` 를 자기 픽스처로 바꿨다(변형 둘 — 제외 판정 뒤집기 · 기준 축 무시 — 둘 다 잡음).
  **공용 계약 테스트 판정표 (15 + 4건)**:
  | 테스트 | 처리 |
  | --- | --- |
  | `test_output_contract` 사양 표의 `reverse` · 픽스처 · 대상 함수 · 상수 | 지움 |
  | 역방향 손절선 음수 실수 | 옮김 → 중간선거 격자 실행의 숫자 손절선 |
  | 성적표 방향 · 거래내역 방향 | 지움 (역방향 고유) |
  | 구간 다섯 행 · 하한 미달 행 유지 | 옮김 → 매매법 전부(`_BY_METHOD`), 칸마다 |
  | 0건 구간 지표 비움 | 지움 — `test_execution_periods` 의 「손절 건수도 비어 있다」·「표본 0건 구간은 비어 있다」가 이미 본다 |
  | 사건이 구간마다 따로 · 사건 정수형 | 옮김 → `test_execution_periods` `TestEventCount` (자기 픽스처) |
  | 정수형 빈칸 저장 · 0건 구간 판정 안 함 | 옮김 → `test_execution_periods` (자기 픽스처) |
  | 통계 이름을 낸다 | 옮김 → 반감기_사이클의 `OUTPUT_FILES` |
  | 사건을 주지 않은 매매법에 컬럼 없음 · 건수 목록 대조 | 남김 (`사건` 을 손으로 박은 상수로) |
  | `test_layer_contracts` 매매법 집합 · 산출 지점 · 레이블 겹침 허용목록 · `horizon_label` 대안 | `reverse` 를 빼고 겹침이 사라진 항목 여섯을 지움 |
  | `test_report_writer` | 같은 등급 쌍을 조사 둘(레버리지 · 선물), 등급이 다른 쪽을 중간선거로. 파일명 픽스처는 `EXCESS_FILENAME` |
  옮긴 `periods` 테스트 넷은 변형 둘(사건을 전체로 · 건수 결측을 0 으로)로 잡음 확인.
  재실행 다섯 — 중간선거 1초 · 반감기 49초 · 레버리지 6초 · 선물 15초 · 등가성 1초, 전부 종료코드 0. `git diff --stat storage/results/` 는
  역방향 7파일 삭제(4,287줄)뿐 — 남은 산출물 바이트 불변.
  도달성 재집계 고아 0 · import 기준 죽은 정의 0. 바뀐 테스트 묶음 399 passed.
- 2026-10-06 23:02: Phase 3 완료.
  (나) 고침 — `src/verify_lab/CLAUDE.md`: 이벤트 정의 계약을 「지금 이벤트형이 없다 — 새 문서 ①~⑬ 과 `62894fa` 원문」으로 줄임 ·
  실행 계층 계약의 역방향 전용 행 셋(식별 컬럼 6개 · 네 표의 신호·사건 수 · `역방향 전체` 방향 축) 삭제 · forward return 계약의
  `next_open` · 「두 기준의 산식」 행 삭제 · 조건부 기준선 행 둘 삭제와 「함께 지웠다」 한 줄 · report 출력 계약의 행 정렬 · 집계 3표 · 신호일 목록 행 삭제 ·
  매매 산출물 계약의 역방향 예시 정리. `.claude/rules/trading.md` 「이 길에 있는 것은 역방향입니다」 문단 삭제와 예시 둘 교체.
  `tests/CLAUDE.md` 「산식 고정 테스트」를 「그 계산을 하는 매매법이 있으면」으로 고침(변경 있음).
  (다) 남김 — 근거로 든 역방향 사례(−5% 기본값 · 매매법 사슬 · 19건 · QQQ 결과 최악 +0.25% · 순열 검정 근거 · 노출 비율)와
  `.claude/rules/docs.md` 의 용어 「역방향 비율 (폐기)」.
  `docs/검증/반감기_사이클/설계.md` 결정의 `horizon_label` 은 **그때의 결정 근거 기록이라 괄호를 붙이지 않고 그대로 둔다**(과거형 허용 자리).
  Validation — 경로·지운 이름 grep 의 남은 자리는 새 문서와 연속_등락의 「관련 파일」 묘비 행 · 「재현 방법」(복원 경로)과 위 설계 결정 기록뿐 ·
  새 문서를 가리키는 앵커 25곳 어긋남 0
- 2026-10-06 23:37: 마지막 Phase — black(1파일) · 리뷰 2회차(상한)까지. 멈추고 사용자 보고.
  **1회차 13건** — 버그 4(무거움 4): PyRight 오류 2(`test_measure_forward_return` 의 Scalar 뺄셈) · 이벤트 정의 계약 포인터가 없는 것을 보증 ·
  복원 목록에 `ReturnBasis.NEXT_OPEN` 누락(복원 시 import 실패) · 손절선 형식 검사 약화(단위 틀림을 놓침). 넷 다 고침 —
  새 문서 §13 에 「이벤트 정의 계약」 표를 원문 그대로 옮김 · 손절선은 손으로 박은 격자 값과 정확 비교(비율 단위 변형을 잡음).
  그 외 9 중 이 계획서 Phase 3 범위의 남은 참조·서술(「스펙 §N」 5곳 · 중간선거 주석의 옛 근거 · 조건부 기준선 서술 모순 · 현재형 서술 9곳)을 정리.
  **2회차 11건** — 버그 3: 빈칸 검사가 건수 컬럼을 고정 목록으로 박음(무거움 — 늘어난 컬럼의 0 채움 변형을 잡음) · 실제 slug 목록에
  `halving_cycle` 누락(무거움 — 반감기만 거부하는 패턴 변형을 잡음) · 복원 절차가 「삭제 커밋」 찾기에 기댐(가벼움 — §20.2 를 지운 정의 전부의
  이름 표로 바꾸고 `62894fa` 를 가리킴). 그 외 중 이 계획서가 만든 부정확함 3건(INDEX 의 규칙 본문 자리 · trading.md 이벤트형 예시 · 지운 예시
  `--dataset` · `signals.csv`) 정리.
  **수정분 검증**(서브에이전트, 수정 6건 · 10 hunk) — 무거움 1: 빈칸 검사 수정이 `DISPLAY_LOSING_COUNT` import 를 남겨 Ruff F401 → 품질 검증 실패(직접 확인).
  가벼움 4: 빈칸 검사가 계약 테스트의 「목록을 프로덕션 상수로 대체하지 않는다」 관용과 다름(대조 검사가 공백을 메움) · slug 검사가 `.match` 라
  좁아진 패턴을 못 잡음(기존) · 루트 `CLAUDE.md` 「연 며칠의 노출」 전제에 맞는 매매법이 지금 없음(기존 서술) · 프로브 이름 목록에 대조 검사 없음.
  미조치 그 외(두 회차 합) — `simulate_signal` 익절 기본값과 그 분기 · `period_rows(event_ids=...)` 경로 · 순열 검정의 아무도 안 읽는 아홉 컬럼 ·
  `DEFAULT_MA_WINDOW` 가 한 매매법만 쓰는 공유 상수 · `HORIZON_LABELS[1]` · 계약 테스트 합성 시세의 순위 축적 장치 · 손절선 검사가 중간선거 격자 값에 묶임
- 2026-10-07 09:29: 사용자 결정(2026-10-07 09:19 「추천대로」) — ① 미사용 import 를 지우고 수정분 검증을 한 번 더 ② 리뷰 3회차는 돌리지 않는다.
  `tests/test_execution_periods.py` 의 `DISPLAY_LOSING_COUNT` import 한 줄 삭제(사본을 먼저 뜸).
  **수정분 검증 2차**(서브에이전트, 1 hunk) 발견 0 — 동작 변화 없음(그 이름을 쓰는 곳 0) · r2 hunk 전부에서 같은 모양 없음 ·
  위험한 쪽으로 바뀐 검사 없음(`COUNT_COLUMNS` 에서 「질 때 표본」을 빼는 변형은 `test_output_contract.py:1291` 의 손으로 박은 목록 대조가,
  0건 구간을 0 으로 채우는 변형은 `test_execution_periods.py:443-444` 가 잡는다 — 서브에이전트가 변형을 적용하지 않고 판정) ·
  안 쓰인 이유는 지운 사용처의 잔여물(연결 누락 아님). 관찰 1(지적 아님): 그 빈칸 보호가 두 파일에 걸쳐 단독 실행으로는 일부 변형을 못 잡지만 전체 스위트에서 잡는다.
  Ruff 전체 통과 · black 무변경(165 files unchanged) · `validate_project.py` passed=1454 · failed=0 · skipped=0 (Ruff · PyRight 통과).
  **미룬 지적 옮기기** — 옮김 1: 폴더 이름 검사 테스트의 `.match`(1차 수정분 검증 가벼움 3, diff 밖 기존 코드 — `[a-z][a-z_]{0,16}` 로 좁히면
  `.match` 는 실제 이름 8개를 다 통과시키고 `fullmatch` 는 둘을 거부함을 패턴 수준에서 재현).
  거른 것:
  | 지적 | 기준 | 근거 |
  | --- | --- | --- |
  | `simulate_signal` 익절 기본값 `take_profit=True` · 익절 분기 · `EXIT_PROFIT` | 3 · 1 | 죽은 분기(그 외). 기본값을 밟으려면 인자를 빼고 부르는 새 호출 코드가 필요 — 지금 호출처는 `trade_fill.py:393` 한 곳 |
  | `period_rows(event_ids=...)` · `사건` 컬럼 | 3 | 운영 호출처 0 의 죽은 경로(그 외) |
  | 순열 검정의 아무도 안 읽는 아홉 컬럼 · `src/verify_lab/CLAUDE.md:605` 「백분율 변환은 report 가 한다」 | 3 | 죽은 계산과 문서 서술(그 외) |
  | `DEFAULT_MA_WINDOW` 가 한 매매법만 쓰는 공유 상수 | 3 · 1 | 관용 이탈(그 외). 새 지표 작성자가 기본값으로 쓰는 것은 새 코드 |
  | `HORIZON_LABELS[1]` | 3 | 죽은 항목(그 외) |
  | 계약 테스트 합성 시세의 순위 축적 장치 · `positions` | 3 | 테스트 정리(그 외) |
  | 손절선 형식 검사가 중간선거 격자 값에 묶임 | 2 · 3 | 격자를 바꾸면 그 테스트가 시끄럽게 실패한다(막는 쪽) |
  | 빈칸 검사가 「목록을 프로덕션 상수로 대체하지 않는다」 관용과 다름 (1차 수정분 검증 가벼움 2) | 2 | `test_output_contract.py:1291` 대조가 시끄럽게 잡음 — 2차 검증이 변형으로 판정 |
  | 루트 `CLAUDE.md:179` 「연 며칠의 노출」 전제에 맞는 매매법이 없음 (1차 가벼움 4) | 3 | 문서 서술(그 외) |
  | 프로브 이름 목록에 대조 검사 없음 (1차 가벼움 5) | 1 | 지금 프로브 셋(`ecos_probe` · `pykrx_etf_probe` · `pykrx_splice_probe`)이 목록과 같다 — 어긋나려면 새 프로브 스크립트가 필요 |
  | 「질 때 표본」 빈칸 보호가 두 파일에 걸침 (2차 관찰) | 2 | 전체 스위트에서 시끄럽게 잡힘 |
  | `test_output_contract.py:1270-1272` 주석이 지금 없는 `제외` 컬럼을 근거로 듦 (2차 범위 밖) | 3 | 주석(그 외) |
  가격 기준 전환 결정(이 계획서 Notes)은 다음 계획서가 받는다
- 2026-10-07 09:31: `/commit` 후보 5개를 옮기고 Done
