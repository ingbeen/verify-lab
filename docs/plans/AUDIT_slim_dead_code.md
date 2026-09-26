# 감사 원문 — 데드 코드 감사 (src · scripts · tests)

> **임시 근거물이다.** 경량화 시리즈 조사(2026-09-26)에서 읽기 전용 감사 에이전트가 낸 보고를 **가공 없이** 옮겼다.
> 줄 번호는 **HEAD `f55617a` 기준**이다 — 계획서 ①(`2c8d93f`)과 그 뒤 계획서가 파일을 고치면 줄이 밀리므로 **착수할 때 grep 으로 다시 찾는다.**
> 결정은 `REPORT_lightweight_inventory.md` §10 이 SoT 이며 이 문서의 「추천」과 다르면 §10 이 이긴다.
> 시리즈를 끝낼 때 함께 지운다. 살아있는 문서는 이 파일을 링크하지 않는다.

---

## verify-lab 데드 코드 감사 결과 (읽기 전용, 파일 변경 없음)

경로는 모두 `/home/yblee/workspace/verify-lab/` 기준입니다. 스캐너 스크립트는 스크래치(`/tmp/claude-1000/-home-yblee-workspace-verify-lab/908f1c29-ebf7-4e9b-becf-78c94e2b996a/scratchpad/`)에 있습니다: `scan_refs.py`, `reach.py`, `unused_params.py`, `test_unused.py`, `label_only.py`.

**전제**
- 작업 트리에 미커밋 변경이 없습니다. `git status` 가 비어 있고 HEAD 는 f55617a(「역방향 순위 컷 K=10 전환…」)입니다. 말씀하신 역방향 변경은 이미 커밋된 것으로 보입니다.
- 스캔 범위: 운영 모듈 89개, 테스트 57개, 정의 1,492개(메서드 19개 포함).
- 셈 방식: AST 로 import 체인(재수출 포함)을 따라가 Name·Attribute 참조를 셌습니다. 이어서 스크립트와 `validate_project.py` 의 최상위 코드를 뿌리로 도달 가능성을 계산했습니다. 그래서 죽은 함수 안에서만 쓰이는 헬퍼도 함께 잡힙니다.
- 오탐 점검 세 가지, 모두 문제없음:
  - 지역 변수가 모듈 이름을 가리는 경우: 0건.
  - 「레이블 사전의 키로만 쓰이는 COL/DISPLAY 쌍」: 걸린 14건이 전부 행 조립용 사전이라 실제로는 0건.
  - 메서드 13개(dunder 제외): 모두 실제 호출처가 있음.

---

### A. 완전 미사용 (4건, 전부 확실)

| 이름 | 정의 위치 | 운영 참조 | 테스트 참조 | 근거 |
|---|---|---|---|---|
| `DISPLAY_BASE_TICKER` | `src/verify_lab/studies/futures_leverage/constants.py:227` | 0 | 0 | 같은 이름·값인 `leverage_tracking/constants.py:195` 만 쓰임 |
| `DISPLAY_RETURN` | `…/futures_leverage/constants.py:242` | 0 | 0 | 같은 값인 `execution/constants.py:82` 만 쓰임 |
| `DISPLAY_EXPOSURE` | `…/futures_leverage/constants.py:254` | 0 | 0 | 같은 이름은 `usdkrw_equivalence/constants.py:283` 쪽만 쓰임 |
| `RANK_COLUMNS` | `src/verify_lab/studies/reverse/extreme_move.py:29` | 0 | 0 | 같은 파일 :44 docstring 에만 이름이 나옴 |

- 앞의 두 줄 때문에 `tests/test_layer_contracts.py:1760` `_KNOWN_LABEL_DUPLICATES` 의 `'1배 종목'`·`'수익률(%)'` 항목에 futures 파일이 올라 있습니다. 부분집합 검사라 상수를 지워도 테스트는 깨지지 않고, 그 항목만 낡은 채 남습니다.
- 테스트 쪽 미사용도 1건 있습니다: `tests/test_studies_extreme_move.py:29` `EXACT_TOLERANCE` (참조 0, 확실).

### B. 테스트에서만 사용 (27건)

「운영」 칸 형식은 `외부/내부` 참조 수이고, 괄호는 그 참조가 어디서 오는지입니다. 도구 출력 그대로입니다.

| 이름 | 정의 위치 | 운영 | 테스트 | 근거 | 확신도 |
|---|---|---|---|---|---|
| `direction_profile` | `measure/screening.py:208` | 0/0 (재수출 1) | 39+import 1 | 유일한 운영 호출처였던 `studies/month_end/runner.py` 가 2ebf2fc(2026-09-21)에서 호출을 뺌 | 확실 |
| `_direction_row` | `screening.py:264` | 0/1 (direction_profile 안) | 0 | 위와 같음 | 확실 |
| `DIRECTION_COLUMNS` | `screening.py:142` | 0/1 (direction_profile 안) | 1+1 | 위와 같음 | 확실 |
| `REQUIRED_SUMMARY_COLUMNS` | `screening.py:155` | 0/1 (direction_profile 안) | 0 | 위와 같음 | 확실 |
| `COL_HIT_RATE` · `COL_EXPECTED_VALUE` · `COL_TOTAL_RETURN` | `screening.py:123-125` | 2/2 (모두 위 함수와 `build_direction_table` 안) | 6+2 · 11+2 · 6+2 | 위와 같음 | 확실 |
| `build_direction_table` | `report/tables.py:554` | 0/0 (재수출 1) | 7+1 | 월말 runner 가 2ebf2fc 에서 호출을 뺌 | 확실 |
| `DISPLAY_HIT_RATE` · `DISPLAY_EXPECTED_VALUE` · `DISPLAY_TOTAL_RETURN` | `report/constants.py:106,107,111` | 2/0 (`build_direction_table` 안) | 2+1 · 3+1 · 4+1 | 위와 같음 | 확실 |
| `COL_SCREEN` | `screening.py:126` | 0/0 | 3+2 | 판정표를 없앤 dd2489c(2026-09-16) 이후 운영 사용 없음. 테스트는 「없어야 한다」 가드(`test_measure_screening.py:461,1015`)와 입력 픽스처(`test_report_tables.py:644`)로만 씀 | 확실 |
| `DISPLAY_BASIS` | `report/constants.py:17` | 0/0 | 4+2 | 마지막 운영 사용이 0347b58(옵션_만기일·월말 삭제)에서 사라짐. 테스트는 「기준 컬럼이 없다」를 확인할 때만 씀 | 확인 필요 (지우면 가드가 문자열을 직접 적어야 함) |
| `run_position` 외 9개 (`_rebalance_flags`, `PositionResult`, `COL_EQUITY`·`COL_EXPOSURE`·`COL_CONTRACT_COUNT`·`COL_EFFECTIVE_LEVERAGE`·`COL_REBALANCED` [`position.py:75-79`], `INITIAL_EQUITY` [`constants.py:187`], `COL_INTEREST_RATE` [`constants.py:308`]) | `studies/futures_leverage/position.py:192` | 0/0 (나머지 9개는 run_position 안에서만) | 25+2 (나머지 0~8) | 모듈 docstring(`position.py:11-14`)이 「본선은 부르지 않는다. 벡터화 경로의 검산 기준」이라고 명시. 의도된 테스트 전용 구현 | 확인 필요 (의도) |
| `IDENTITY_COLUMNS` | `studies/reverse/runner.py:97` | 0/0 (재수출 1) | 4+1 | 운영은 같은 순서를 `runner.py:656·719·833` 에서 손으로 다시 적음. 전역 python 규칙의 「연결 누락」 유형이라 지우지 말고 쓰게 해야 할 후보 | 확인 필요 |
| `IDENTITY_COLUMNS` | `studies/reverse/trading.py:72` | 0/0 | 3+1 | 같은 유형(`trading.py:394-401` 에서 손으로 조립) | 확인 필요 |
| `tracks_of_kind` | `tracks.py:129` | 0/0 | 1+1 | docstring 은 「계약을 거는 쪽이 쓴다」라는데 쓰는 곳이 없음. 반면 `test_strategy_output_contract.py` 는 매매법 둘을 손으로 적음 → 연결 누락 가능성 | 확인 필요 |
| `KINDS` | `tracks.py:48` | 0/2 (tracks_of_kind 안) | 2+1 | 위와 같음 | 확인 필요 |

- 지울 때 걸리는 점: `tests/test_measure_screening.py` 의 게이트(`screen_verdict`, 살아 있음) 테스트 약 35개가 `direction_profile` 을 거쳐 게이트를 잽니다(`_verdict` 헬퍼 :120). 헬퍼 docstring 은 「프로덕션 조립을 재현한다」라고 하지만, 운영은 `execution/periods.py:290-323` 이 행 평균으로 직접 부릅니다. 즉 테스트가 고정하는 경로와 운영 경로가 다릅니다. 방향 표 계열을 지우려면 이 테스트들을 다시 써야 합니다.

### C. 정의 모듈 안에서만 사용 (공개 이름) — 개수만

- src 공개 이름 349개: 상수 302 · 클래스 23 · 함수 21 · 별칭 3. 이 중 85개는 테스트도 씀.
- 스크립트와 `validate_project.py` 188개는 진입점이라 본래 내부 전용이므로 뺐습니다. src 비공개 이름은 166개입니다.
- 대표 예:
  - `measure/statistics.py:314` `payoff_profile`
  - `report/tables.py:360` `horizon_label`
  - `report/writer.py:187` `absolute_paths_in`
  - `studies/futures_leverage/continuous.py:264` `plan_rolls`
  - `studies/reverse/constants.py:301` `dataset_of`
- `__all__` 에 올라 있지만 밖에서 운영 사용이 없는 이름: 21개. 그중 테스트 사용도 0인 것:
  - `execution/run_summary.py:62-63` `KEY_MEASURE`·`KEY_TRADE`
  - `report/run_summary.py:54` `PERIOD_SEPARATOR`
  - `midterm_cycle/cycle_calendar.py` 의 `CYCLE_*_DTYPES`·`empty_entries`·`empty_schedule`
  - `quarters.py:84` `DrawdownProfile`
  - `split_entry.py:93` `TrancheFill`
  - `leverage_tracking/breakdown.py:225` `summarize`

### 재수출만 — 패키지 경로로 가져가는 곳이 0건

- 대상: `__init__.py` 6개가 재수출하는 이름 74개 — data 17, measure 16, report 12, studies/midterm_cycle 5, studies/reverse 21, utils 3.
- 이 이름들을 `from verify_lab.<패키지> import 이름` 으로 가져가는 곳이 운영 0건, 테스트 0건입니다. 모두 하위 모듈에서 직접 가져옵니다. 패키지 경로로 오는 것은 하위 모듈 import(`from verify_lab.data import pykrx_collector` 등)뿐입니다.
- 6개 파일은 합쳐서 185줄(docstring 포함)입니다.
- 확인 필요: `src/verify_lab/CLAUDE.md:218-226` 이 경고하는 「`__all__` 로 Ruff 미사용 import 검사를 끈 통과용 모듈」과 모양이 같습니다. 다만 패키지 import 때 하위 모듈을 먼저 불러오는 부작용에 기대는 곳이 있는지는 검증하지 않았습니다.

### D. 삭제된 매매법의 잔재

**코드 (B 와 겹침)**
- 방향 표 계열 11개(B 1~6행): 월말_진입 잔재입니다. 확실합니다.
- `DISPLAY_BASIS`: 옵션_만기일·월말 삭제로 운영 사용이 0이 됐습니다.
- `tracks.py:85,86,90,100` 의 삭제 slug 4줄: 의도된 잔존입니다. `src/verify_lab/CLAUDE.md:358` 이 「레지스트리에는 남는다」고 명시하고 `tests/test_tracks.py:302` 가 고정합니다.

**테스트**

| 항목 | 위치 | 참조 | 근거 | 확신도 |
|---|---|---|---|---|
| `AXIS_OPTION_EXPIRY` · `AXIS_MONTH_END` · `EXPIRY_MONTH` | `tests/test_strategy_output_contract.py:162,163,207` | 0 | 삭제 매매법용 기대 컬럼·픽스처 값 | 확실 |
| `EXPIRY_TARGET_DATE_COLUMN` + `_expected_trades(target_date=)` 분기 | `…:177`, `:394-405` | 호출 2건(482·493) 모두 인자 미전달 | 「옵션 만기일만 참」인 분기라 도달하지 않음 | 확실 |
| **`OTHER_TRACK_NAME = "option_expiry"`** | `tests/test_report_writer.py:29`, 쓰는 곳 `:150` | 1 | 주석은 「같은 등급의 다른 매매법이어야 한다」가 전제인데, 0347b58 이후 option_expiry 는 `조사`, reverse 는 `매매`. 부모 폴더가 달라 등급 폴더를 통째로 비우는 버그가 생겨도 `test_clearing_keeps_other_tracks_in_the_layer` 가 통과함. 테스트가 무력화됨 | 확실 |
| `TestDirectionTable` 픽스처 (`AXIS_COLUMN="expiry_month_number"`, 「QQQ 9월 실측」) | `tests/test_report_tables.py:623-747` | — | B 인 `build_direction_table` 을 옵션 만기일 값으로 검사 | 확실 |

**현재 상태를 틀리게 말하는 주석·이름** (코드 동작에는 영향 없음, 모두 확실)
- `execution/trade_fill.py`
  - :8 — `simulate_scheduled_trade` 의 쓰는 곳을 「옵션 만기일 · 월말」로 적음. 실제로는 중간선거_사이클.
  - :13 — 「매매법 네 곳」.
  - :22, :130-131, :452 — 월말을 지금 쓰는 것처럼 서술.
- `execution/constants.py:6,12,87,101,205` — 삭제된 `strategy/` 경로와 월말·옵션 만기일.
- `execution/periods.py:22`, `execution/run_summary.py:26,123`.
- `report/constants.py:201` — `측정.csv` 를 「옵션 만기일·월말」이 쓴다고 적음. 실제로는 중간선거_사이클.
- `report/run_summary.py:65` — `expiry_count`.
- `measure/screening.py:15` — 「월말의 집행 축」.
- `measure/distribution.py:7` — 「옵션 만기일 매매가 함께 쓴다」.
- `studies/reverse/trading.py:66-67` — 「세 매매법이 공유하는 계약」.
- `studies/reverse/trading.py:400` — 「지수를 받는 매매법(월말)」.
- `studies/futures_leverage/position.py:25`, `validate_project.py:26` — `strategy/` 경로.
- `tests/test_layer_contracts.py:1750-1754` — 허용목록 머리 주석의 ㉮(달력형 어휘 넷)와 ㉰의 `만기월`. 목록에는 이미 없음.
- `tests/test_strategy_output_contract.py` — 매매법이 둘인데 「세_」로 시작하는 테스트 이름(:963, :1396, :1441, :1591). 「세 매매법」·「셋 다」·「역방향·월말이 계속 그 이름을 낸다」·`grid.csv` 서술(:668, :879-882, :1366, :1587).
- 참고: 두 계약 테스트의 「전에는 월말이…」 식 docstring(`test_layer_contracts.py` 25·862·895·921·1247·1321·1348·1521 등)은 과거 사고 기록일 뿐이고 검사 로직은 트리 전체를 일반적으로 봅니다. 잔재가 아닙니다.

### E. 쓰이지 않는 인자·분기

**확실**
- `studies/reverse/trading.py:176` `run_reverse_trading(hold_limit=)`: 운영 호출 1건과 테스트 호출 16건이 모두 넘기지 않습니다.
- `studies/futures_leverage/runner.py:612` `run_study(horizons, market_dir, series_dir)`: 운영 호출 1건(`scripts/run_futures_leverage.py:125`)은 `index_filter` 만 넘기고, 테스트 호출은 0건입니다.
- `data/pykrx_collector.py:286` `collect_pykrx_nav(output_dir=)`: 운영 1건이 넘기지 않고 테스트 호출은 0건입니다. 이 함수에는 테스트 자체가 없습니다.
- `scripts/run_reverse.py:125` `--dataset` 도움말의 「국내 두 기준의 대조는 함께 돌려야 성립합니다」: 수정주가 데이터셋을 없앤 31e69ea(2026-08-20) 이후 국내 대상은 KODEX 200 하나, 가격 기준도 하나입니다.

**확인 필요 (의도 여부)**
- `run_reverse_trading(stop_levels=)`: 운영 0, 테스트 15. docstring 이 「합성 시세 검사 입구」라고 명시합니다. 운영에서는 다중 손절선과 `None`(무손절) 분기에 도달하지 않습니다.
- `reverse/runner.py:271` `run_study(rank_cuts, start_years)`: 운영 0, 테스트 1·2.
- 역방향 `Dataset.price_basis`: 두 대상 모두 `원본가`(`reverse/constants.py:143,151`)라 `summary.json`·콘솔의 「가격기준」 값이 상수입니다. 지우면 산출물이 바뀝니다.

**나머지**
- 운영은 안 넘기고 테스트만 넘기는 주입 인자(`output_dir`·`path`·`today`·`window`·`horizons`·`sources` 등)가 15개 함수에 있습니다. 정상적인 주입으로 봤습니다.
- CLI 플래그 37개는 선언된 것이 모두 `args.*` 로 읽힙니다.

### 3. 테스트 쪽

- **존재하지 않는 모듈을 import 하는 테스트: 0건.** 다만 위 `test_report_writer.py` 는 삭제 매매법의 레지스트리 줄에 기대다가 의미를 잃었습니다.
- **공유 계층 테스트가 매매법 상수를 빌리는 곳**: `tests/test_strategy_trade_fill.py:28` 이 reverse 의 `HOLD_LIMIT`·`STOP_LOSS_LEVEL` 을 가져오고, :198 에서 `assert HOLD_LIMIT == 2` 를 합니다. MEMORY 「공유 계층의 테스트는 자기 픽스처를 갖는다」가 경고한 결합과 같은 모양입니다(확인 필요).
- **중복 테스트**
  1. `HOLD_LIMIT == 2` — `test_strategy_trade_fill.py:198` 과 `test_strategy_reverse_runner.py:470` 이 같은 assert.
  2. 역방향 성적표에 제외 컬럼이 없다 — `test_strategy_reverse_runner.py:642` 과 `test_strategy_output_contract.py:654`(후자가 상위집합).
  3. 역방향 구간 5행 — `test_strategy_reverse_runner.py:184`(개수만)와 `test_strategy_output_contract.py:623`(순서까지, 상위집합).
  4. 스크립트의 `.csv` 문자열 — `test_layer_contracts.py:1517`(파일명 모양 리터럴, 「산문은 뺀다」)과 `test_strategy_output_contract.py:927`(부분 문자열 전면 금지)이 같은 `scripts/run_*.py` 를 봅니다. 후자가 전자의 완화를 무력화합니다(확인 필요).
- **두 대형 테스트 파일의 목록**: `test_layer_contracts.py` 의 두 허용목록에 든 파일 경로를 기계로 대조했고 전부 실재합니다. 삭제 매매법 경로는 없습니다. `test_strategy_output_contract.py:1384` 의 옛 slug 목록은 의도된 금지목록입니다.
- **`test_strategy_*` 와 `test_studies_*` 접두**: 의미 있는 구분이 아닙니다. `test_strategy_*` 는 d838db9(2026-09-15)에서 없어진 `src/verify_lab/strategy/` 패키지 시절 이름입니다. 지금은 `execution/periods.py`·`execution/trade_fill.py`·`studies/reverse/trading.py`·출력 계약을 검사하는데, 중간선거_사이클 체결 테스트는 `test_studies_midterm_cycle_trading.py` 라 소스 계층과 대응하지 않습니다.

### 4. storage — 코드가 더 이상 만들지 않는 산출물 폴더

`storage/results/조사/` 아래 4개입니다. 모두 git 추적 중이고 파일은 각 4개입니다.

| 폴더 | 마지막 커밋 |
|---|---|
| `옵션_만기일/` | 0347b58 |
| `월말_진입/` | 0347b58 |
| `만기_말일/` | 9126c54 |
| `원달러_그리드/` | 57ea9a1 |

- 이 폴더들을 가리키는 문서: `docs/COMMANDS.md`, `docs/조사/{옵션_만기일,월말_진입,만기_말일,원달러_그리드}/…`, `docs/조사/원달러_조달.md`, `docs/plans/PLAN_expiry_monthend_retire.md`.
- 반대 방향의 사실: `pykrx_splice_probe` 는 레지스트리에 있지만 산출물 폴더가 없습니다.

### 곁가지로 확인된 것

- `src/verify_lab/CLAUDE.md:469` 가 `screen_candidates` 를 가리키지만 코드에는 0건입니다.
- `tests/test_report_writer.py:277` 의 slug 목록에 midterm_cycle 이 빠져 있습니다. 철수 계획서에 「기존 빈틈」으로 기록돼 있습니다.
- 철수 계획서는 「HEAD 에서도 0 이던 13건은 원래 것이라 손대지 않음」이라고 적었습니다. 이번 A+B 가 그 전체 그림입니다.

### 요약

| 분류 | 개수 | 지울 경우 대략 줄 수 |
|---|---|---|
| A | src 4 + 테스트 1 | 약 5줄 |
| B — 결론 난 축의 잔여물 (방향 표 11 · `COL_SCREEN` · `DISPLAY_BASIS`) | 13 | src 약 170줄 + `test_report_tables.py` 170줄. `test_measure_screening.py` 약 880줄은 삭제가 아니라 재작성 필요 |
| B — 의도 또는 연결 누락 의심 (선물 검산 엔진 10 · `IDENTITY_COLUMNS` 2 · `tracks_of_kind`+`KINDS` 2) | 14 | 지우는 대상으로 보지 않음. 선물 엔진만 해도 src 약 200줄 + 테스트 약 590줄 |
| C | src 공개 349 | 데드 코드 아님 |
| 재수출만 | 74개 이름, 6개 파일 | 185줄 |
| D — 코드 | 12 (B 와 겹침) | B 에 포함 |
| D — 테스트 | 상수·분기 5 + 무력화된 테스트 1 | 약 10줄 + 테스트 1개 수정 |
| D — 틀린 주석·이름 | 약 20곳 | 코드 동작과 무관 |
| D — 레지스트리 | 4줄 | 의도된 잔존 |
| D — storage | 폴더 4개(파일 16개) | — |
| E | 확실 4 · 확인 필요 3 | — |

공유 계층 이름 중 소비자가 매매법 하나뿐인 것이 57개 있지만, 원칙 소유자 규칙으로 설명되는 배치라 데드 코드로 보지 않았습니다.
