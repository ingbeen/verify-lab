# Implementation Plan: F — 같은 로직의 여러 벌과 낭비를 정리한다

> 작성/운영 규칙(SoT): `/impl-plan` 스킬(`~/.claude/skills/impl-plan/SKILL.md`)을 반드시 참고하세요.  
> (이 템플릿을 수정하거나 새로운 양식의 계획서를 만들 때도 해당 스킬을 포인터로 두고 준수합니다.)

**상태**: 🟡 Draft

---

🚫 **이 영역은 삭제/수정 금지** 🚫

**상태 옵션**: 🟡 Draft / 🔄 In Progress / ✅ Done

**Done 처리 규칙**:

- ✅ Done 조건: DoD 모두 [x] + `skipped=0` + `failed=0`
- ⚠️ **스킵이 1개라도 존재하면 Done 처리 금지 + DoD 테스트 항목 체크 금지**
- 상세: `/impl-plan` 스킬의 "3) 스킵 및 완료 규칙" 참고
- 위 조건은 `~/.claude/hooks/plan_lint.py`가 저장 시 자동 검사합니다

---

**작성일**: 2026-09-14 12:05
**마지막 업데이트**: 2026-09-14 12:05
**관련 범위**: data(수집기 4종), studies/reverse, studies/option_expiry, utils, validate_project
**관련 문서**: `src/verify_lab/CLAUDE.md`, `scripts/CLAUDE.md`, 전역 `~/.claude/rules/python.md`

---

## 0) 고정 규칙 (이 plan은 반드시 아래 규칙을 따른다)

> 🚫 **이 영역은 삭제/수정 금지** 🚫
> 이 섹션(0)은 지워지면 안 될 뿐만 아니라 **문구가 수정되면 안 됩니다.**
> 규칙의 상세 정의/예외는 반드시 `/impl-plan` 스킬을 따릅니다.

- 품질 검증 명령은 **마지막 Phase에서만 실행**한다. 실패하면 즉시 수정 후 재검증한다.
- Phase 0은 "레드(의도적 실패 테스트)" 허용, Phase 1부터는 **그린 유지**를 원칙으로 한다.
- 이미 생성된 plan은 **체크리스트 업데이트 외 수정 금지**한다.
- 스킵은 가능하면 **Phase 분해로 제거**한다.

---

## 1) 목표(Goal)

- [ ] 목표 1: **KRX 수집기 3종에 흩어진 같은 로직**을 한 벌로 만든다 (판정식 단일화)
- [ ] 목표 2: **위치 인덱싱 튜플**처럼 조용히 틀릴 수 있는 조립 형태를 이름 있는 자료구조로 바꾼다
- [ ] 목표 3: **재는 값이 같은데 두 번 계산하는 곳**을 줄인다 — 단, **먼저 재고 나서 고친다**
- [ ] 목표 4: **거짓 숫자를 만들어 내는 fallback** 을 없앤다
- [ ] 목표 5: **산출물의 값은 하나도 바뀌지 않는다**

## 2) 비목표(Non-Goals)

아래는 **검토 끝에 하지 않기로 한다.** 다음 세션이 같은 분석을 반복하지 않도록 근거를 남긴다.

- **`strategy/month_end_runner._run_cell` 의 방향 2회 시뮬 제거** — 무손절 행에서만
  「`bet_down=True` 의 수익률 = `False` 의 부호 반전」이 성립하고, **손절이 걸리면 방향마다 체결이 다르다**
  (시가·장중 판정이 방향으로 갈린다). 절반만 최적화하려면 두 갈래가 생겨
  **「체결식은 한 벌」이라는 계약과 충돌**한다. 이득보다 위험이 크다
- **`data/ecos_collector.find_series` 와 `strategy` 쪽 `_dataset` 류를 한 헬퍼로 묶는 것** —
  네 벌이지만 **계층이 다르다**(`data` 둘, `strategy` 둘). 계층을 가로지르는 4줄짜리 루프를 위해
  공통 유틸을 만드는 것은 과추상화다. **`data/` 안의 두 벌만** 다룬다
- **`utils/logger._find_project_root` 의 `Path.cwd()` fallback 제거** — 주석이
  「저장소 안에서만 실행되므로 도달하지 않는다」고 인정하지만, **로깅 초기화에서 예외를 던지면
  정작 원인을 알려줄 로그가 하나도 안 나온다.** 그 판단이 옳다. 남긴다
- 값 중복 통합·데드코드·소유권 이동 — 계획서 C·D·E 소관
- 문서 정합 — 계획서 G 소관

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

#### F-1. KRX 수집기 3종에 같은 로직이 여러 벌 🟠

`src/verify_lab/CLAUDE.md` 「측정 계층의 절대 원칙」 5 — **「판정식 단일화 — 같은 판정을 두 곳에서 구현하지 않는다. 복제하면 두 곳이 조용히 갈라진다.」**

2026-09-14 실측:

| 로직 | 벌 수 | 위치 |
| --- | --- | --- |
| `_exclude_recent` (최근 구간 제외 + 건수 반환) | **2 + 인라인 3** | `etn_collector.py:261-275` ≡ `krx_futures_collector.py:527-541` **바이트 단위 동일** / `pykrx_collector.py` 는 세 함수(`collect_pykrx_history:234-240`·`collect_pykrx_nav:344-350`·`collect_pykrx_index:453-459`)에 **인라인으로 복사** |
| `_to_numeric` (쉼표 제거 + `-` 를 결측으로) | **2** | `etn_collector.py:216-228` ≡ `krx_futures_collector.py:251-264` **바이트 단위 동일** |
| `_import_krx_client` / `_import_pykrx_stock` (자격증명 → pykrx import) | **3** | `pykrx_collector.py:112` · `etn_collector.py:139` · `krx_futures_collector.py:195` |
| 조회 시작일 형식 검증 | **3형태 5곳** | `etn_collector._validated_start_date` / `krx_futures_collector._validate_date_format` / `pykrx_collector` 의 인라인 `try` **3개** |

특히 `_import_*` 는 **「자격증명을 올린 뒤에 pykrx 를 import 한다」는 순서를 지키는 자리**다.
`tests/test_layer_contracts.py` 가 세 수집기에서 이 순서를 검사할 만큼 중요한데 **진입점이 셋**이다.

#### F-2. `find_series` 두 벌 🟡

`data/ecos_collector.py:146-162` 와 `data/fred_collector.py:97-113` — 「목록에서 `key` 로 하나 찾고 없으면 `ValueError`」가 로직·메시지 형식까지 같다. **같은 계층 두 파일**이므로 `data/constants.py` 또는 새 헬퍼로 한 벌이 되는 것이 「상수 관리」 규칙에 맞다.

#### F-3. 위치 인덱싱 튜플 🟠

`studies/reverse/runner.py` — `_measure_spec` 이 **5-튜플**을 돌려주고 호출부가 `blocks[0]`~`blocks[4]` 로 받는다(`:310-314`). `_measure_reverse_all` 은 **4-튜플**이고 `reverse_blocks[0]`~`[3]` 로 받는다(`:749-752`).

**다섯 원소가 전부 `list[pd.DataFrame]` 이라 순서를 바꿔도 타입 검사가 못 잡는다.** 순서가 어긋나면 `signals.csv` 에 `statistics` 가 들어가는 식으로 표가 통째로 바뀌는데 실행은 성공한다.

#### F-4. 같은 값을 두 번 이상 계산한다 🟡

| 위치 | 낭비 |
| --- | --- |
| `studies/reverse/extreme_move.expanding_rank:56-59` | **O(n²)** — 거래일마다 누적 구간 전체를 다시 훑는다. QQQ 6,915행 → 약 2,400만 회 비교. 데이터셋마다 한 번씩 |
| `strategy/option_expiry_runner.collect_entries:281-290` | **칸마다** CSV 를 다시 읽고 만기 달력·청산 일정을 다시 만든다. 7칸 중 종목은 3종이라 **4번이 중복**. 바로 위 `dataset_records` 는 중복을 일부러 피하는데 정작 무거운 쪽은 안 한다 |
| `studies/option_expiry/runner._record_trade_cell:656,658` · `:672,673` | 같은 프레임에 `summarize` 를 **두 번** 부른다 |

🔴 **성능은 「먼저 재고 나서 고친다」.** 루트 `CLAUDE.md` 의 「자문 체크 — 시니어 엔지니어가 과복잡하다고 볼까?」와 「YAGNI」가 여기 걸린다. **Phase 0 에서 실제 시간을 재고**, 체감되지 않으면 하지 않는다.

#### F-5. 거짓 숫자를 만들어 내는 fallback 🟠

`validate_project.py`

```python
# :72-73, :123-124
if error_count == 0:
    error_count = 1        # 「파싱 실패 시 기본값 1」
```

**「몇 개인지 모른다」와 「1개다」가 구별되지 않는다.** 이 저장소가 다른 곳에서는 일관되게 금지하는 패턴이다 — 예: `measure/screening.py` 의 「판정 안 함」과 「제외」를 가른 이유, `strategy/constants.py` 의 `무손절`·`손절불가` 를 가른 이유.

`run_pyright:113-118` 도 **줄에서 첫 정수를 오류 수로 채택**한다. `0 errors, 1 warning` 이면 0 → 위 fallback 이 1로 덮는다.

#### F-6. 같은 일을 하는 두 관용 🟡

- `report/writer.py:68` `datetime.now(KST)` vs `utils/meta_manager.py:62` `datetime.now(UTC).astimezone(KST)`
  — 결과는 같지만 **두 관용이 공존**한다. 계약이 「실행 시각과 타임스탬프의 기준 시간대」를
  `common_constants.KST` 하나로 정했으므로 쓰는 법도 하나여야 한다

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 「이 프로젝트의 개발 원칙」(YAGNI·간결성·자문 체크), 「만들기 전에 사다리를 오른다」
- `src/verify_lab/CLAUDE.md` — 「측정 계층의 절대 원칙」 5(판정식 단일화), 「상수 관리」,
  「계층 간 계약」의 **원시 시세 저장 규칙**(특히 **pykrx import 순서**)
- 전역 `~/.claude/rules/python.md` — 「불가능 조건 처리」
- `scripts/CLAUDE.md`
- `tests/CLAUDE.md`

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [ ] **선행 계획서(A~E) 복기 완료** — 상태와 「후속 계획서 인계」 절을 읽고,
      이 계획서의 대상과 「공통 조각을 둘 자리」가 여전히 유효한지 판정해 진행 로그에 적었다
- [ ] Phase 0 재판단 게이트를 F-1 ~ F-6 전 항목에 실행하고 「한다 / 안 한다」와 근거를 진행 로그에 표로 남겼다
- [ ] F-4 의 **성능 측정치**(변경 전/후 초)를 진행 로그에 적었다. 재지 않고 고치지 않았다
- [ ] 「한다」로 판정된 항목이 전부 구현됐다
- [ ] `tests/test_layer_contracts.py` 의 **pykrx import 순서 검사가 여전히 통과**한다
- [ ] **산출물 값 불변 확인** — Phase 4 대조 결과를 진행 로그에 적었다
- [ ] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [ ] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [ ] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [ ] 필요한 문서 업데이트 (`docs/COMMANDS.md` 변경 여부 명시 — 예상: 변경 없음)
- [ ] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (「pykrx import 순서를 지키는 진입점은 하나다」를 `src/verify_lab/CLAUDE.md` 원시 시세 저장 규칙에 남긴다)
- [ ] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/data/` — 신규 공통 모듈(예: `data/krx_common.py`) 또는 `data/constants.py` 확장
- `src/verify_lab/data/pykrx_collector.py` · `etn_collector.py` · `krx_futures_collector.py` — 공통 조각 사용
- `src/verify_lab/data/ecos_collector.py` · `fred_collector.py` — `find_series` 통합
- `src/verify_lab/studies/reverse/runner.py` — 튜플 → 자료구조
- `src/verify_lab/studies/reverse/extreme_move.py` — (측정 결과에 따라) 벡터화
- `src/verify_lab/strategy/option_expiry_runner.py` — (측정 결과에 따라) 중복 I/O 제거
- `src/verify_lab/studies/option_expiry/runner.py` — `summarize` 중복 호출
- `src/verify_lab/utils/meta_manager.py` — 시각 관용 통일
- `validate_project.py` — 파싱 fallback
- `tests/` — 위 각 항목의 회귀 테스트
- `src/verify_lab/CLAUDE.md` — 근거 승격
- `docs/COMMANDS.md`: **변경 없음 예상**. Phase 0 에서 재확인

### 데이터/결과 영향

- **없어야 한다.** 전부 「같은 값을 다른 방법으로 얻기」다
- 🔴 **`expanding_rank` 벡터화는 값이 바뀔 위험이 가장 크다** — 순위 정의가
  「자기보다 극단인 날의 수 + 1」이고 **동률은 같은 순위**다. 부동소수점 비교라
  구현을 바꾸면 경계에서 순위가 흔들릴 수 있다. Phase 2 에 **전 구간 동일성 검사**를 둔다
- Phase 4 에서 전 산출물 대조로 확인한다

## 6) 단계별 계획(Phases)

### Phase 0 — 재판단 게이트 (성능은 여기서 «잰다»)

> **건너뛸 수 없다.**

**작업 내용**:

- [ ] 🔴 **선행 계획서 복기 (이 Phase 의 첫 작업)**:

  ```bash
  for f in docs/plans/PLAN_[a-g]_*.md; do
    echo "=== $f"; grep -m1 '^\*\*상태\*\*' "$f"
    sed -n '/^### 후속 계획서 인계/,/^### 진행 로그/p' "$f"
  done
  ```

  - 🔴 **E 의 인계 절**: 새로 생긴 모듈과 옮긴 파일 — **F-1 의 「공통 조각을 어디 둘까」가
    E 가 만든 자리와 어긋나면 안 된다.** E 가 이미 `data/` 에 무언가 만들었으면 거기 붙인다
  - 🔴 **E-5b(`validate_project.py` 타입 검사 편입)의 상태**를 확인한다 —
    이미 편입됐으면 **F-5 의 파싱 수정이 타입 오류를 낼 수 있다.** 편입 전이면 순서가 자유롭다
  - **C 의 인계 절**: 옮긴 이름 — F-2(`find_series`) 대상이 이미 정리됐을 수 있다
  - **A 의 인계 절**: `trade_fill` 에 들어간 가드 — F 가 그 파일을 손대지 않지만 확인한다
  - 전제가 깨졌으면 Scope 를 조정하고 무엇이 왜 달라졌는지 적는다

- [ ] **F-1 재판단**:

  ```bash
  grep -n "_exclude_recent\|_to_numeric\|_import_krx_client\|_import_pykrx_stock\|_validated_start_date\|_validate_date_format" \
    src/verify_lab/data/*.py
  grep -n "cutoff_date = today - timedelta" src/verify_lab/data/pykrx_collector.py
  ```

  - **한다**: 위 표의 벌 수가 그대로일 때
  - 🔴 **어디에 둘지 결정한다.** 권장은 **`data/krx_common.py` 신설** —
    `data/constants.py` 는 「값」의 자리이고 이것들은 「함수」다.
    `data/loader.py` 에 넣으면 로더가 수집 관심사를 갖게 된다
  - ⚠️ **`_import_*` 를 합칠 때 주의**: 세 수집기가 **서로 다른 pykrx 클래스**를 가져온다
    (`stock` / `ETN_전종목기본종목`+`KrxWebIo` / `전종목시세`+`KrxWebIo`).
    **「자격증명을 먼저 올린다」만 공통**이고 무엇을 import 하는지는 다르다 —
    공통 부분만 뽑고 import 문 자체는 각자 함수에 남기는 편이 정확할 수 있다.
    `tests/test_layer_contracts.py` 의 **「함수 본문에 pykrx import 가 있다」 검사가 계속 통과하는지**가 판정 기준이다

- [ ] **F-2 재판단**: `grep -n "def find_series" -A16 src/verify_lab/data/ecos_collector.py src/verify_lab/data/fred_collector.py`
  - **한다**: 두 구현이 여전히 같을 때
  - ⚠️ 두 함수는 **각자의 모듈에서 public 이름**이다. 합치면 import 경로가 바뀌므로
    스크립트·테스트를 함께 본다: `grep -rn "find_series" scripts tests`

- [ ] **F-3 재판단**: `grep -n "blocks\[0\]\|blocks\[1\]\|reverse_blocks\[" src/verify_lab/studies/reverse/runner.py`
  - **한다**: 위치 인덱싱이 남아 있을 때

- [ ] 🔴 **F-4 재판단 — 먼저 «잰다»**:

  ```bash
  poetry run python -c "
  import time, pandas as pd
  from verify_lab.data.loader import load_market_csv
  from verify_lab.common_constants import MARKET_DIR, MARKET_FILE_TEMPLATE
  from verify_lab.studies.reverse.extreme_move import expanding_rank
  df = load_market_csv(MARKET_DIR / MARKET_FILE_TEMPLATE.format(ticker='QQQ'))
  t = time.perf_counter(); expanding_rank(df); print(f'expanding_rank {len(df)}행: {time.perf_counter()-t:.2f}초')
  "
  ```

  ```bash
  # 검증·매매 전체 실행 시간 (재수집하지 않는다)
  for s in scripts/studies/run_reverse_study.py scripts/strategy/run_option_expiry_trading.py scripts/studies/run_option_expiry_study.py; do
    echo "--- $s"; /usr/bin/time -p poetry run python "$s" 2>&1 | tail -4
  done
  ```

  **판정 기준**:
  - `expanding_rank` 가 **1초 미만**이면 벡터화하지 않는다 — 위험(값 변화)만 사고 이득이 없다
  - `collect_entries` 중복 I/O 가 전체 실행의 **눈에 띄는 몫이 아니면** 하지 않는다
  - `summarize` 중복 호출은 **한 줄 변수 할당**으로 끝나므로 시간과 무관하게 **한다**
    (성능이 아니라 「같은 것을 두 번 적지 않는다」가 이유다)
  - 측정치를 진행 로그에 **초 단위로** 적는다. 「빨라 보였다」는 근거가 아니다

- [ ] **F-5 재판단**: `sed -n '54,76p' validate_project.py` · `sed -n '105,127p' validate_project.py`
  - **한다**: 「파싱 실패 시 기본값 1」이 남아 있을 때
  - ⚠️ 계획서 E 가 `validate_project.py` 를 타입 검사에 넣기로 했다면 **E 를 먼저** 하거나,
    여기서 고친 뒤 E 가 검사에 넣는다. 순서를 진행 로그에 적는다

- [ ] **F-6 재판단**: `grep -rn "datetime.now(" src/verify_lab/`

- [ ] 항목별 판정을 **진행 로그에 표로** 남긴다 (`항목 | 한다/안 한다 | 근거 · 측정치`)

---

### Phase 1 — 회귀 테스트를 먼저 고정(레드 허용)

> 이 계획서는 **동작을 바꾸지 않는 변경**이다. 테스트가 「바뀌지 않았음」을 증명하는 자리다.

**작업 내용**:

- [ ] **F-1 테스트** — 공통 조각을 옮긴 뒤에도
  - `_exclude_recent` 가 세 수집기에서 **같은 경계**를 쓴다 (`DOMESTIC_RECENT_EXCLUSION_DAYS`)
  - `_to_numeric` 이 `-` 를 **결측으로** 남긴다 (0 으로 채우지 않는다)
  - 기존 수집기 테스트(`tests/test_pykrx_collector.py`·`test_etn_collector.py`·`test_krx_futures_collector.py`)가
    **그대로 통과**한다 — 이것이 주 방어선이다
- [ ] **F-3 테스트** — `_measure_spec` 이 낸 표들이 **이름으로** 꺼내진다
  (자료구조를 도입하면 순서 뒤바뀜이 타입 오류가 되므로, 테스트는 「필드 이름이 맞다」만 고정)
- [ ] 🔴 **F-4a 테스트 (벡터화를 「한다」로 판정한 경우에만)** — **전 구간 동일성**
  - 현재 구현을 `_expanding_rank_reference` 로 복사해 테스트 파일에 두고,
    **실제 시세 두 파일 전 구간**에서 새 구현과 `assert_frame_equal` (동률 포함)
  - 합성 데이터로 **동률이 실제로 생기는 입력**(같은 등락률 반복)을 따로 만든다 —
    국내 원본가는 정수라 동률이 실제로 나온다(`src/verify_lab/CLAUDE.md` 이벤트 정의 계약)
  - ⚠️ 이 테스트는 **느리다.** `tests/CLAUDE.md` 와 `pytest.ini` 의 `slow` 마커 관용을 확인해 붙인다

---

### Phase 2 — 중복 로직 통합(그린 유지)

**작업 내용**:

- [ ] **F-1** KRX 공통 조각을 Phase 0 에서 고른 자리로
  - `_exclude_recent` — 한 벌. **`pykrx_collector` 의 인라인 3곳도 이것을 쓰게 한다**
  - `_to_numeric` — 한 벌
  - 조회 시작일 형식 검증 — 한 벌. 메시지 문구를 하나로 맞춘다
    (지금 `etn` 은 「조회 시작일 형식이…」, `futures` 는 「`{label}` 형식이…」로 다르다)
  - `_import_*` — Phase 0 의 판단대로. **합치더라도 `tests/test_layer_contracts.py` 의
    「함수 본문에 pykrx import」 검사가 통과해야 한다.** 통과하지 않으면 합치지 않는다
- [ ] **F-2** `find_series` 한 벌
  - 두 모듈이 그 이름을 계속 노출하려면 **재노출이 아니라 얇은 래퍼**도 피한다 —
    호출처(`scripts/data/collect_ecos.py`·`collect_fred.py`)가 공통 함수를 직접 부르게 한다
    (재노출 금지는 계획서 C 가 세운 원칙이다)
- [ ] **F-3** `studies/reverse/runner.py` 의 튜플 → `@dataclass(frozen=True)`
  - 다섯 표를 담는 이름 있는 자료구조 하나(예: `_SpecBlocks`)와 네 표짜리 하나
  - `run_study` 의 `blocks[0]`~`[4]`, `_measure_reverse_all` 의 `[0]`~`[3]` 을 필드 이름으로
  - **다섯 리스트 이름은 `StudyOutputs` 의 필드명과 맞춘다** (`signals`·`statistics`·`excess`·`test`·`candidates`)
- [ ] **F-6** `utils/meta_manager.py:62` 를 `datetime.now(KST)` 로
  - 값은 같다. **관용을 하나로** 하는 것이 목적이다
  - `tests/test_meta_manager.py` 가 `freezegun` 을 쓰면 그 고정 방식이 계속 통하는지 본다

---

### Phase 3 — 재계산 정리와 fallback (그린 유지)

**작업 내용**:

- [ ] **F-4c** `studies/option_expiry/runner._record_trade_cell` — `summarize` 결과를 변수로 받아 재사용
      (`:656,658` 과 `:672,673`). **시간과 무관하게 한다** — 같은 것을 두 번 적지 않는다
- [ ] **F-4b** (Phase 0 에서 「한다」인 경우) `strategy/option_expiry_runner.collect_entries` 중복 I/O 제거
  - 종목별로 「시세 + 만기 달력 + 청산 일정」을 **한 번만** 만들고 칸이 그것을 나눠 쓴다
  - 🔴 **`Entries` 는 지금 `@dataclass`(가변)이고 public 이다.** 공유하려면 `frozen=True` 로 바꾸는 것이 안전하다 —
    한 칸이 고치면 다른 칸이 함께 바뀐다
  - `collect_entries` 는 `__all__` 에 있어 **외부 계약**이다. 시그니처를 바꾸면 테스트를 함께 본다
- [ ] **F-4a** (Phase 0 에서 「한다」인 경우) `expanding_rank` 벡터화
  - **Phase 1 의 동일성 테스트가 그린일 때만 채택**한다. 하나라도 어긋나면 되돌린다
  - 주석에 **「왜 이 방식인가」와 「동률을 어떻게 유지하는가」**를 적는다 — 순위 정의가 이 검증의 핵심이다
- [ ] **F-5** `validate_project.py` 의 파싱 fallback
  - 「파싱 실패 시 1」을 없애고 **「개수를 알 수 없음」을 그대로 표시**한다 (예: `-` 또는 `개수 미상`)
  - `run_pyright` 의 「첫 정수 채택」을 **`N error(s)` 패턴을 직접 잡는 정규식**으로 바꾼다
  - 🔴 **성패 판정은 계속 종료코드로 한다.** 개수는 표시용이며, 이 변경으로
    `failed=`·`skipped=` 표기가 깨지면 **계획서 훅(`plan_lint.py`)이 Done 을 막는다** — 그 형식은 유지한다
  - `run_pytest` 의 파싱도 같은 문제가 있다(`-v` 출력에 `passed` 를 포함한 이름이 있으면 오파싱).
    **pytest 요약 줄(`=== N passed … ===`)만 잡도록** 좁힌다

---

### Phase 4 — 값 불변 대조

**작업 내용**:

- [ ] 다섯 검증 + 세 매매를 인자 없이 돌린다 (**재수집하지 않는다** — 수집기를 고쳤지만 실행하지 않는다)
- [ ] 새 산출물의 CSV·`summary.json` 을 직전 산출물과 기계로 대조한다. **전 셀 동일**이어야 한다
- [ ] 🔴 `expanding_rank` 를 고쳤다면 **`signals.csv` 의 `당시 순위` 열을 특히 본다**
- [ ] **수집기는 실행하지 않는다.** 외부 서버에 요청하지 않고, 대신 기존 수집기 테스트로 판정한다
      (루트 `CLAUDE.md` 「같은 데이터를 이유 없이 다시 받지 않습니다」)
- [ ] F-4 측정치(변경 전/후)를 진행 로그에 적는다
- [ ] 새 폴더는 커밋하지 않고 `/clean-results` 로 정리한다

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [ ] `src/verify_lab/CLAUDE.md` 「계층 간 계약」의 원시 시세 저장 규칙에 한 줄 —
      「**pykrx import 순서를 지키는 진입점은 하나다**」(F-1 을 합쳤다면). 합치지 않았다면
      **왜 셋으로 두는지**를 적는다 — 어느 쪽이든 다음 사람이 판단을 반복하지 않게 한다
- [ ] `docs/COMMANDS.md`: 변경 여부 확정해 적는다 (예상: 변경 없음)
- [ ] 자동 포맷 적용: `poetry run black .`
- [ ] 🔴 **「후속 계획서 인계」 절을 채운다** (§8 Notes) — **G 가 알아야 할 것**을 적는다:
      새로 생긴 공통 모듈과 옮긴 함수, **`validate_project.py` 의 출력 형식이 바뀌었는지**
      (G 의 품질 검증 기록에 영향), 지운 주석, **F-4 를 「안 한다」로 판정했다면 그 근거**
      (G 가 성능 관련 주석을 고칠 때 본다). **비워 두면 다음 계획서가 낡은 전제로 시작한다**
- [ ] 변경 기능 및 전체 플로우 최종 검증
- [ ] DoD 체크리스트 최종 업데이트 및 체크 완료
- [ ] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

> 순서를 지킨다 — 리뷰에서 고치면 코드가 바뀌므로 품질 검증이 마지막 관문이어야 한다.

- [ ] `/code-review xhigh` (발견 \_\_건 · 조치: \_\_)
- [ ] `poetry run python validate_project.py` (passed=\_\_, failed=\_\_, skipped=\_\_)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다.**
> 계획서를 쓰는 시점에는 diff 가 없어 여기 적는 것은 전부 추측이고,
> **추측으로 적은 줄은 그대로 나간다.** 형식·문체 규칙은 `/commit` 이 정한다.

(비어 있음 — `/commit` 으로 채운다)

## 7) 리스크(Risks)

| 리스크 | 완화 |
| --- | --- |
| 🔴 **`expanding_rank` 벡터화가 순위를 바꾼다** — 그러면 신호 집합이 달라져 **모든 결과가 무효**가 된다 | Phase 1 에 실제 시세 전 구간 동일성 테스트를 두었고, Phase 0 이 「1초 미만이면 하지 않는다」로 문턱을 세웠다. **의심되면 하지 않는 쪽이 옳다** |
| `_import_*` 를 합치다 pykrx import 순서가 깨진다 | `tests/test_layer_contracts.py` 의 검사 통과를 **채택 조건**으로 명시했다. 통과 못 하면 합치지 않는다 |
| 수집기를 고쳤는데 실행으로 확인할 수 없다 | 외부 요청을 늘리지 않는 것이 규칙이다. **기존 수집기 테스트 3종이 방어선**이며, 다음 정기 수집 때 실측된다. 그 사실을 진행 로그에 적는다 |
| `validate_project.py` 를 고치다 `failed=`·`skipped=` 표기가 깨져 **계획서 훅이 Done 을 막는다** | Phase 3 에 명시했다. 형식은 유지하고 **개수 파싱만** 고친다 |
| `Entries` 를 공유하다 한 칸의 수정이 다른 칸에 샌다 | `frozen=True` 로 바꾸는 것을 Phase 3 에 명시했다 |
| 공통 모듈을 만들었는데 **과추상화**가 된다 | Non-Goals 에 「계층을 가로지르는 4줄 루프는 묶지 않는다」를 근거와 함께 적었다. 자문 체크(루트 `CLAUDE.md`)를 마지막 Phase 에서 한 번 더 한다 |

## 8) 메모(Notes)

- **왜 E 다음인가**: E 가 소유권을 정리한 뒤라야 「공통 조각을 어디 둘지」가 명확하다
- **이 계획서의 성공 조건은 「아무것도 안 바뀌었다」**이다. 값이 바뀌면 그것이 곧 실패다
- 2026-09-14 실측: `_exclude_recent` 와 `_to_numeric` 은 두 수집기에서 **바이트 단위로 같다**.
  `pykrx_collector` 는 같은 로직을 **세 함수에 인라인**으로 갖는다
- F-4 는 **재고 나서 고치는 항목**이다. 측정치 없이 「고쳤다」로 넘어가면 이 계획서의 취지가 무너진다

### 후속 계획서 인계 (이 계획서를 끝낸 뒤 채운다)

> **G 가 실행 전에 이 절을 읽는다.** 이 계획서로 바뀐 것 중 **그쪽 전제에 영향을 주는 것만** 적는다.
> 형식: `무엇이 | 어떻게 바뀌었나 | 어느 계획서가 영향받나`
>
> 🔴 **F-4 를 「안 한다」로 판정했다면 그 측정치와 근거를 반드시 적는다** — 그러지 않으면
> 다음 세션이 같은 성능 항목을 다시 재고 다시 고민한다.
> 아무것도 안 바뀌었으면 **「없음」이라고 적는다**.

(비어 있음 — 마지막 Phase 에서 채운다)

### 진행 로그 (KST)

- 2026-09-14 12:05: 계획서 작성. 감사의 「리팩토링」·「불필요한 fallback」을 F 로 묶음
