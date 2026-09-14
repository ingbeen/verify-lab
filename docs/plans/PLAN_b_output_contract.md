# Implementation Plan: B — 검증 계층 `summary.json` 을 계약에 맞춘다

> 작성/운영 규칙(SoT): `/impl-plan` 스킬(`~/.claude/skills/impl-plan/SKILL.md`)을 반드시 참고하세요.  
> (이 템플릿을 수정하거나 새로운 양식의 계획서를 만들 때도 해당 스킬을 포인터로 두고 준수합니다.)

**상태**: ✅ Done

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
**마지막 업데이트**: 2026-09-14 17:36
**관련 범위**: studies/reverse, studies/option_expiry, studies/usdkrw_equivalence, strategy/reverse, scripts, tests
**관련 문서**: `src/verify_lab/CLAUDE.md`, `scripts/CLAUDE.md`, `docs/INDEX.md`, `.claude/rules/session-bootstrap.md`

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

- [x] 목표 1: **`summary.json` 의 `ticker` 에 종목코드가 들어가게 한다.** 지금은 표시 이름이 들어가 있어 국내 종목코드가 산출물 어디에도 남지 않는다
- [x] 목표 2: **`summary.json` 에서 절대경로를 없앤다.** 두 PC 의 경로가 커밋돼 있어 재현·대조가 PC 에 묶인다
- [x] 목표 3: 역방향 매매 요약의 `rule` 에서 **산문 두 키(`entry`·`exit`)를 없앤다.** `exit` 에 손절 기준
      설명이 들어 있고 두 문장 모두 `notes` 에 또 있다 — 산문의 자리를 `notes` 하나로 모은다
      (2026-09-14 사용자 승인. 원래 문구는 「`rule.exit` 가 청산 규칙을 말하게 한다」였다 — 조사 결과
      나머지 두 매매법이 `rule` 에 기계값만 두는 관용이라 그쪽에 합류하는 편이 낫다. 진행 로그 참고)
- [x] 목표 4: 위 셋이 다시 갈라지지 않도록 **계층 간 계약 테스트**를 붙인다

## 2) 비목표(Non-Goals)

- **`dataset_record` 의 소유자를 옮기는 것** — 지금 `strategy/run_summary.py` 가 갖고 있고 검증 계층은 각자 만든다. 합치려면 `studies → strategy` 의존이 생겨 계층 방향이 뒤집히므로 **중립 자리로 옮기는 작업이 필요하고 그것은 계획서 E 소관**이다. B 는 «값과 키를 맞추고 테스트로 고정»까지만 한다
- **이미 커밋된 산출물의 `summary.json` 수정** — 산출물은 그 실행의 기록이다. 소급해 고치면 그 실행을 재현할 수 없게 된다. **새로 내는 것부터 적용**한다 (`src/verify_lab/CLAUDE.md` 「적용 범위는 새로 내는 산출물부터입니다」와 같은 관용)
- `meta.json` 의 절대경로 — `meta.json` 은 git 제외 대상(`.gitignore`)이라 PC 를 넘지 않는다. 문제가 아니다
- CSV 산출물의 컬럼 변경 — 이 계획서는 `summary.json` 만 다룬다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

#### B-1. `summary.json` 의 `ticker` 에 표시 이름이 들어간다 🔴

`src/verify_lab/CLAUDE.md` 「계층 간 계약」의 출력 계약이 이렇게 못박고 있다.

> **`Dataset` 의 두 필드 이름** — **`ticker` = 종목코드 · `label` = 표시 이름.** 세 매매법과 `data/` 수집기가 같은 뜻을 씁니다 … 전에는 `studies/reverse`·`studies/option_expiry` 의 `ticker` 에 **표시 이름**이 들어 있었고 코드가 아예 없었습니다 … 역방향 요약이 `"ticker": "KODEX 200"` 이라고 적었습니다

**계약은 「고쳤다」고 적었으나 검증 계층 두 곳이 그대로다.**

| 위치 | 코드 | 실제 산출물 (2026-09-14 확인) |
| --- | --- | --- |
| `studies/reverse/runner.py:475` `_dataset_record` | `KEY_TICKER: context.dataset.label` | `"ticker": "KODEX 200"` |
| `studies/reverse/runner.py:587` `_population_records` | 같음 | 같음 |
| `studies/reverse/runner.py:993` `_empty_group_record` | `identity[DISPLAY_TICKER]`(= 표시 이름) | 같음 |
| `studies/option_expiry/runner.py:274` `_run_dataset` | `KEY_TICKER: dataset.label` | `"ticker": "KODEX 200"` |
| `studies/month_end/runner.py:660-662` | `ticker` + `label` + `file` 분리 | (정상 — 이것이 목표 형태) |

두 `Dataset` 정의 모두 `ticker` 필드를 갖고 있는데(`069500`) **어디에도 실리지 않는다.** 계약이 「범위의 SoT 는 `datasets`」라고 정했으므로 차트·증권앱 대조에 필요한 코드가 산출물에서 소실된다. **미국 ETF 는 둘이 같아(`QQQ`) 드러나지 않고 국내에서만 샌다.**

#### B-2. `summary.json` 에 절대경로가 박혀 있다 🔴

2026-09-14 실측 — 커밋된 산출물 **9개**에 절대경로가 있고, **두 PC 의 경로가 섞여 있다.**

```
storage/results/검증/20260912_225752_reverse/summary.json
  "path": "/home/yblee/workspace/verify-lab/storage/market/QQQ_max.csv"     ← WSL
storage/results/검증/20260824_104655_usdkrw_equivalence/summary.json
  "krw_rate": "/Users/yubeen/Workspace/verify-lab/storage/series/CD91.csv"  ← mac
```

키별 집계: `path` 12건 · `output_dir` 2건 · `close`/`market_rate`/`krw_rate`/`usd_rate` 각 1건.

원인 세 곳:

| 위치 | 코드 |
| --- | --- |
| `studies/reverse/runner.py:477` | `KEY_PATH: str(context.dataset.path)` |
| `studies/usdkrw_equivalence/runner.py:235-239` | `{source.key: str(source.path) …}` · `str(target.price_path)` |
| `scripts/studies/run_option_expiry_study.py:218` | `{**outputs.summary, "output_dir": str(directory)}` |

매매 계층은 `strategy/run_summary.py:86` 에서 이미 규정했다.

> `file`: 읽은 파일 이름. **경로가 아니라 이름이다 — 절대경로는 PC 마다 달라 산출물이 갈린다**

이 저장소는 mac·WSL 두 PC 전제이고 `storage/results/` 를 git 동기화한다(`.claude/rules/session-bootstrap.md` 6절). `output_dir` 은 **자기 자신이 있는 폴더**라 값 자체가 잉여이기도 하다.

#### B-3. `rule.exit` 가 청산 규칙이 아니라 손절 설명이다 🟡

`strategy/reverse_runner.py:234` — `KEY_EXIT: NOTE_STOP_BASE`. 값은 「손절선은 진입가 기준이고…」다. 실제 청산 규칙(이익이면 그날 청산 / 손실이면 D+2 기한)은 `NOTE_HOLD_LIMIT` 인데 `rule` 에 안 들어간다.

덤으로 `NOTE_ENTRY`·`NOTE_STOP_BASE` 는 `rule` 과 `notes` **양쪽에 중복**으로 저장된다(`reverse_runner.py:233-238`). 같은 문장이 한 파일에 두 번 있으면 한쪽만 고쳐질 때 어느 쪽이 맞는지 판별할 수 없다.

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절
- `src/verify_lab/CLAUDE.md` — 특히 「계층 간 계약」의 **출력 계약**·**매매 산출물 계약**·**실행 요약(`summary.json`)** 절
- `scripts/CLAUDE.md` — 「CLI 계층 책임」, 「산출물 저장」
- `docs/INDEX.md` §5 — 산출물 인용과 폴더 판정
- `.claude/rules/session-bootstrap.md` 6절 — `storage/results/` git 동기화 규칙
- `tests/CLAUDE.md`

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] **선행 계획서(A) 복기 완료** — 상태와 「후속 계획서 인계」 절을 읽고,
      이 계획서의 전제가 바뀐 것이 있으면 진행 로그에 적었다
- [x] Phase 0 재판단 게이트를 전 항목에 대해 실행하고 「한다 / 안 한다」를 진행 로그에 남겼다
- [x] B-1 ~ B-3 중 「한다」로 판정된 항목이 전부 구현됐다
- [x] 새로 낸 `summary.json` 에 **절대경로가 0건**임을 기계로 확인했다
- [x] 새로 낸 `summary.json` 의 `datasets` 에 **종목코드가 들어 있음**을 기계로 확인했다
- [x] 계층 간 계약 테스트 추가 (세 검증 + 세 매매의 `datasets` 키 집합이 같다)
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — `src/verify_lab/CLAUDE.md` 출력 계약의 「전에는 … 였습니다」 서술을 **현재 사실에 맞게** 고쳤다 / `docs/COMMANDS.md` 변경 여부 명시
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/studies/reverse/runner.py` — `_dataset_record`·`_population_records`·`_empty_group_record`, `KEY_PATH` 제거
- `src/verify_lab/studies/option_expiry/runner.py` — `_run_dataset` 의 `ticker`/`label`
- `src/verify_lab/studies/usdkrw_equivalence/runner.py` — `KEY_INPUTS` 의 경로 → 파일 이름
- `src/verify_lab/strategy/reverse_runner.py` — `rule` 의 `exit` 의미, `notes` 중복
- `scripts/studies/run_reverse_study.py` — `_print_datasets` 가 `KEY_PATH` 를 읽는다(`Path(record[KEY_PATH]).name`)
- `scripts/studies/run_option_expiry_study.py` — `output_dir` 주입 제거
- `tests/test_studies_reverse_runner.py` · `tests/test_studies_option_expiry_runner.py` · `tests/test_studies_equivalence_runner.py` · `tests/test_strategy_reverse_runner.py` · `tests/test_layer_contracts.py`
- `src/verify_lab/CLAUDE.md` — 출력 계약 서술 갱신
- `docs/COMMANDS.md`: **변경 없음 예상** (CLI 옵션·실행 방법 불변). Phase 0 에서 재확인한다

### 데이터/결과 영향

- 🔴 **`summary.json` 스키마가 바뀐다.** CSV 는 안 바뀐다
  - `datasets[].ticker` 값이 표시 이름 → 종목코드
  - `datasets[].label` 신설 (reverse·option_expiry)
  - `datasets[].path` → `file` (파일 이름만)
  - `populations[].ticker`·`empty_signal_groups[].ticker` → `label` 로 개명
  - `inputs` 의 경로 → 파일 이름
  - `output_dir` 삭제
- **이미 커밋된 산출물은 건드리지 않는다** (Non-Goals). 옛 산출물과 새 산출물의 `summary.json` 이 다른 모양인 상태가 정상이며, 그 사실을 `src/verify_lab/CLAUDE.md` 에 한 줄로 남긴다
- **결과 문서(`docs/research/`·`docs/strategy/`)가 `summary.json` 의 키를 인용하는지**를 Phase 0 에서 확인한다. 인용하면 그 문서도 함께 고친다

## 6) 단계별 계획(Phases)

### Phase 0 — 재판단 게이트

> **건너뛸 수 없다.** 감사 시점(2026-09-14) 이후 코드가 바뀌었을 수 있다.

**작업 내용**:

- [x] 🔴 **선행 계획서 복기 (이 Phase 의 첫 작업)** — **A** 를 비롯해 이미 진행된 계획서를 확인한다:

  ```bash
  for f in docs/plans/PLAN_[a-g]_*.md; do
    echo "=== $f"; grep -m1 '^\*\*상태\*\*' "$f"
    sed -n '/^### 후속 계획서 인계/,/^### 진행 로그/p' "$f"
  done
  ```

  - **A 가 Done 이면** 그 인계 절을 읽는다. A 는 `trade_fill`·`screening`·`month_end` 에
    가드를 넣으므로 **이 계획서가 손대는 파일과 겹친다**
  - **A 가 Draft 면** 순서를 어긴 것이다. A 를 먼저 하는 편이 낫다 —
    「틀리면 멈춘다」가 없는 상태에서 키를 옮기면 사고가 조용히 지나간다.
    그래도 진행한다면 **그 판단과 이유를 진행 로그에 적는다**
  - 전제가 깨졌으면 무엇이 어떻게 달라졌는지 적고 Scope·Non-Goals 를 조정한다

- [x] **B-1 재판단**:

  ```bash
  grep -rn "KEY_TICKER\|KEY_LABEL\|KEY_PATH\|KEY_FILE" src/verify_lab/studies/*/runner.py
  poetry run python -c "
  import json, glob
  for f in sorted(glob.glob('storage/results/*/*/summary.json')):
      d = json.load(open(f))
      ds = d.get('datasets')
      if isinstance(ds, list) and ds:
          print(f.split('/')[-2], [ (r.get('ticker'), r.get('label')) for r in ds ])
  "
  ```

  - **한다**: `ticker` 값에 `KODEX 200` 같은 표시 이름이 들어 있고 `label` 이 없을 때
  - **안 한다**: 이미 코드가 들어가 있을 때

- [x] **B-2 재판단**:

  ```bash
  grep -rn "str(.*\.path)\|str(directory)\|str(.*price_path)" src/verify_lab/studies/ scripts/studies/
  grep -rl "/home/\|/Users/" storage/results/*/*/summary.json | wc -l
  ```

  - **한다**: 코드가 `str(<Path>)` 를 요약에 넣고 있을 때
  - **안 한다**: 전부 `.name` 으로 바뀌어 있을 때
  - **참고**: 기존 산출물의 건수(9)는 고치지 않으므로 줄지 않는다. **코드가 기준**이다

- [x] **B-3 재판단**:

  ```bash
  sed -n '228,240p' src/verify_lab/strategy/reverse_runner.py
  ```

  - **한다**: `KEY_EXIT: NOTE_STOP_BASE` 이고 `notes` 에 같은 상수가 또 있을 때
  - **안 한다**: 이미 정리됐을 때

- [x] 🔴 **파급 확인 — 문서가 이 키를 인용하는가**:

  ```bash
  grep -rn '"ticker"\|"path"\|"output_dir"\|summary\.json' docs/ CLAUDE.md | grep -v "^docs/plans/"
  ```

  인용하는 문서가 있으면 **그 문서를 Scope 에 추가**하고 함께 고친다.
  없으면 그 사실을 진행 로그에 적는다 (다음 세션이 다시 찾지 않도록)

- [x] `docs/COMMANDS.md` 에 `summary.json` 의 키를 설명하는 줄이 있는지 확인해 Scope 를 확정한다

- [x] 세 항목 판정을 **진행 로그에 표로** 남긴다

---

### Phase 1 — 계약 테스트를 먼저 고정(레드 허용)

**작업 내용**:

- [x] `tests/test_layer_contracts.py` 에 **`datasets` 키 계약** 테스트 추가
  - 세 검증(`reverse`·`option_expiry`·`month_end`)과 세 매매의 `summary.json` `datasets` 항목이
    **같은 키 집합**을 갖는다 (`ticker`·`label`·`file`·`period`·`rows` 를 최소 집합으로)
  - 검증 계층은 `dataset_record` 를 못 쓰므로(계층 방향) **키 «집합»만 비교**한다.
    소유자 통합은 계획서 E 로 넘긴다 — 그 사실을 테스트 docstring 에 적는다
  - **구현: AST 정적 검사**(`_returned_dict_keys`). 그 파일의 기존 성격(정적 분석)과 맞고
    픽스처가 필요 없다. **상수 «이름»이 아니라 «값»으로 비교한다** — 이름이 모듈마다 달라도
    (`KEY_ROWS` 대 `KEY_ROW_COUNT`) 산출물에 나가는 것은 값이다.
    **매매 셋의 「정확히 이 다섯」은 `test_strategy_output_contract.py:1129` 가 이미 런타임으로 본다**
  - **덤으로 옵션 만기일 검증 CLI 가 요약에 값을 끼워 넣지 않는지**도 같은 클래스에 넣었다.
    전 스크립트에 걸면 범위 밖인 `run_futures_leverage_study.py`·`run_leverage_tracking_study.py`
    둘이 걸리므로 **B 가 손대는 한 파일로 좁혔다**
- [x] **절대경로 금지** 테스트 추가
  - 각 runner 가 낸 `summary` dict 를 JSON 직렬화해 `/` 로 시작하는 값이나
    `BASE_DIR` 문자열이 들어 있지 않은지 본다
  - 🔴 **문자열을 재귀로 훑어야 한다** — `inputs.spot.close` 처럼 두 단계 아래에 있다
  - **구현: `tests/conftest.py` 의 `assert_no_absolute_paths` 픽스처** (`assert_stable_under_truncation`
    과 같은 관용). 쓰는 곳은 `test_studies_reverse_runner.py` 와 `test_studies_equivalence_runner.py`
    이며 **머리 문자열을 손으로 박았다** — `BASE_DIR` 을 가져다 쓰면 이 PC 의 경로만 보게 되어
    «다른 PC 가 쓴» 경로를 못 잡는다
- [x] `tests/test_studies_reverse_runner.py` — `datasets[].ticker` 가 `069500` 임을 고정
  - 🔴 **`_write_dataset` 픽스처가 `label=ticker` 로 둘을 같게 만들고 있었다** — 고치지 않으면
    `ticker` 자리에 표시 이름이 실려도 영원히 안 잡힌다(`tests/CLAUDE.md` §9). 기본값을
    `ticker="069500"` · `label="합성"` 으로 갈랐고, 두 데이터셋 테스트의 호출부도 함께 고쳤다
- [x] `tests/test_strategy_reverse_runner.py` — `rule` 에 산문 키가 없고 `rule`·`notes` 에 같은 문장이
      중복되지 않음을 고정. **「없앴다」와 「옮겼다」를 가르는 테스트를 하나 더 붙였다** —
      청산 규칙 문장이 `notes` 에 남아 있는지 본다 (지금도 통과하며, 과하게 지우는 것을 막는다)

---

### Phase 2 — 구현(그린 유지)

**작업 내용**:

- [x] **B-1a** `studies/reverse/runner.py`
  - `KEY_LABEL = "label"`·`KEY_FILE = "file"` 추가, `KEY_PATH` 제거
  - `_dataset_record`: `ticker=dataset.ticker` · `label=dataset.label` · `file=dataset.path.name`
  - 🔴 **`row_count` → `rows`, `start_date`+`end_date` → `period` 로 맞춘다** (2026-09-14 추가).
    Phase 1 의 최소 집합이 `ticker·label·file·period·rows` 인데 **역방향만 이 셋이 다른 이름**이라
    그대로 두면 DoD 의 「세 검증 + 세 매매의 키 집합이 같다」를 만족할 수 없다.
    `period` 형식은 `strategy/run_summary.PERIOD_SEPARATOR` 와 같은 `시작 ~ 종료` 이며,
    **`run_reverse_study.py:177` 이 이미 그 문자열을 손으로 만들고 있어** 읽는 쪽이 오히려 짧아진다.
    `KEY_ROW_COUNT`·`KEY_START_DATE`·`KEY_END_DATE` 세 상수를 지운다 — 소비처는
    `run_reverse_study.py` 두 줄과 `tests/test_studies_reverse_runner.py:574` 뿐이다
  - `_population_records`·`_empty_group_record`: 키를 `KEY_TICKER` → `KEY_LABEL` 로 개명
    (값은 표시 이름 그대로. **뜻과 이름을 맞추는 것**이 목적이다)
  - `scripts/studies/run_reverse_study.py:174-178` 의 `_print_datasets` 를 함께 고친다 —
    `record[KEY_TICKER]` → 표시할 것은 `label`, `Path(record[KEY_PATH]).name` → `record[KEY_FILE]`
  - `run_reverse_study.py:291` 의 `record[KEY_TICKER] + " " + record[KEY_PRICE_BASIS]` 도 `label` 로
- [x] **B-1b** `studies/option_expiry/runner.py`
  - `KEY_LABEL` 추가, `_run_dataset` 이 `ticker=dataset.ticker`·`label=dataset.label` 을 함께 낸다
- [x] **B-2a** `studies/reverse/runner.py` — 위 B-1a 에서 `path` → `file` 로 이미 해결
- [x] **B-2b** `studies/usdkrw_equivalence/runner.py:235-239` — `str(path)` → `path.name`
  - 🔴 **`spot` 은 `{key: path}` 중첩 dict 다.** 안쪽까지 바꾼다
- [x] **B-2c** `scripts/studies/run_option_expiry_study.py:218` — `"output_dir"` 주입 제거
  - 그 값은 **파일이 놓인 폴더 자신**이라 잉여다. 화면에는 이미 `logger.debug` 로 나온다
  - `save_metadata` 쪽의 `output_dir` 은 **남긴다** — `meta.json` 은 git 제외라 PC 를 넘지 않고,
    「최근 실행이 어디에 있나」를 찾는 것이 그 파일의 용도다
- [x] **B-3** `strategy/reverse_runner.py` — **2026-09-14 사용자 승인으로 아래로 확정** (진행 로그 참고)
  - `rule` 에서 `KEY_ENTRY`·`KEY_EXIT` 두 항목을 **뺀다.** 상수 정의 두 줄도 함께 지운다
  - `notes` 는 **그대로 둔다** — 네 문장이 이미 다 있고, 청산 규칙은 `NOTE_HOLD_LIMIT` 이 담는다.
    `rule.hold_limit` 숫자도 그대로 남으므로 **잃는 정보가 없다**
  - 결과: 잘못된 `exit` 값과 산문 중복이 한 번에 사라지고 **세 매매법의 `rule` 이 기계값만 담는다**.
    계약의 「`rule` 안은 고정하지 않는다」를 어기지 않는다 — 모양을 강제하는 것이 아니라
    이미 둘이 쓰는 관용에 합류하는 것이다

---

### Phase 3 — 새 산출물로 확인

**작업 내용**:

- [x] 네 검증·한 매매를 인자 없이 돌린다 (재수집하지 않는다)

  ```bash
  poetry run python scripts/studies/run_reverse_study.py
  poetry run python scripts/studies/run_option_expiry_study.py
  poetry run python scripts/studies/run_usdkrw_equivalence_study.py
  poetry run python scripts/strategy/run_reverse_trading.py
  ```

- [x] **절대경로 0건** 확인 (새 폴더만 대상):

  ```bash
  grep -rl "/home/\|/Users/" storage/results/*/*/summary.json
  ```

  이번 실행으로 생긴 폴더가 결과에 **없어야** 한다
- [x] **종목코드 존재** 확인 — Phase 0 의 두 번째 명령을 다시 돌려 `('069500', 'KODEX 200')` 형태가 나오는지 본다
- [x] **CSV 가 안 바뀌었는지** 대조한다. 이 계획서는 `summary.json` 만 바꾸므로 CSV 는 전 셀 동일해야 한다.
      기준 폴더는 계획서 A 의 Phase 3 과 같다
- [x] 새 폴더는 **커밋하지 않는다.** `/clean-results` 로 정리한다
      → **커밋하지 않았다**(전부 untracked). 🔴 **정리는 사용자 결정으로 «건너뛴다»**(2026-09-14).
      `/clean-results` 는 모델 호출이 막혀 있어 사용자가 직접 불러야 하고, **절차를 다른 수단으로
      대신하지 않는다.** 그래서 아래 8개는 **디스크에 untracked 로 남아 있다** — 지우려면 그 스킬을 부른다.
      `검증/20260914_170117_reverse` · `170126_option_expiry` · `170132_usdkrw_equivalence` ·
      `매매/170133_reverse` (리뷰 반영 **전** 실행) 와
      `검증/20260914_172437_reverse` · `172441_option_expiry` · `172442_usdkrw_equivalence` ·
      `매매/172442_reverse` (리뷰 반영 **후** 최종 확인).
      **남아 있어도 품질 검증은 통과한다** — 인용 검사는 「인용됐는데 없는 폴더」와 「루트 직하의 폴더」만
      보고, 이 여덟은 계층 폴더 안에 있으면서 어느 문서도 인용하지 않는다(2026-09-14 17:36 실측 재확인)

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [x] `src/verify_lab/CLAUDE.md` 「계층 간 계약」 갱신
  - 출력 계약의 `Dataset` 두 필드 항목 — 「전에는 … 였습니다」가 **현재 사실이 아니게 되었으므로**
    사유 서술을 현재 시제로 고친다 (계획서 F 의 「과거 서술」 정리와 겹치지 않게, **이 항목만** 손댄다)
  - 실행 요약 절에 **「경로가 아니라 파일 이름을 담는다」가 검증 계층에도 적용된다**를 명시
  - 「이미 발행된 산출물의 `summary.json` 은 소급해 고치지 않는다」를 한 줄로 남긴다
- [x] `docs/COMMANDS.md`: 변경 여부를 확정해 적는다 (예상: 변경 없음)
- [x] 자동 포맷 적용: `poetry run black .`
- [x] 🔴 **「후속 계획서 인계」 절을 채운다** (§8 Notes) — **C~G 가 알아야 할 것**을 적는다:
      바뀐 `summary.json` 키, 새로 생긴 상수 이름(`KEY_LABEL`·`KEY_FILE`), 옮긴 import,
      **E 로 넘긴 `dataset_record` 소유자 이관**의 현재 상태, 깨진 전제.
      **비워 두면 다음 계획서가 낡은 전제로 시작한다**
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

> 순서를 지킨다 — 리뷰에서 고치면 코드가 바뀌므로 품질 검증이 마지막 관문이어야 한다.

- [x] `/code-review xhigh` (발견 13건 · 조치: **11건 수정 · 2건 후속 계획서로 인계**)
- [x] `poetry run python validate_project.py` (passed=1126, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다.**
> 계획서를 쓰는 시점에는 diff 가 없어 여기 적는 것은 전부 추측이고,
> **추측으로 적은 줄은 그대로 나간다.** 형식·문체 규칙은 `/commit` 이 정한다.

1. `검증 / 실행 요약의 종목코드 복원과 절대경로 제거`
2. `검증 / summary.json datasets 를 여섯 산출 지점 공통 다섯 키로 통일`
3. `검증 / 요약의 코드·이름 분리와 파일 이름화, 매매 rule 산문 중복 제거, 계층 계약 테스트 추가`
4. `검증 / 두 PC 에서 재현되는 산출물을 위한 요약 계약 정정`
5. `검증 / 요약 계약을 AST·재귀 검사로 고정하고 어긋난 세 자리 수정`

## 7) 리스크(Risks)

| 리스크 | 완화 |
| --- | --- |
| `summary.json` 키를 결과 문서가 인용하고 있으면 문서가 깨진다 | Phase 0 에 파급 확인 명령을 두었다. 인용하면 Scope 에 추가 |
| 옛 산출물과 새 산출물의 `summary.json` 모양이 달라 대조가 끊긴다 | **의도한 결과다.** 옛 것을 소급 수정하면 그 실행을 재현할 수 없게 된다. 그 사실을 `src/verify_lab/CLAUDE.md` 에 남긴다 |
| `datasets` 키 계약 테스트가 검증·매매를 억지로 한 모양에 묶는다 | 최소 집합만 비교한다. 검증마다 더 붙는 키(`expiry_count` 등)는 허용 |
| `KEY_TICKER` → `KEY_LABEL` 개명이 스크립트를 깨뜨린다 | `run_reverse_study.py` 두 곳을 Scope 에 명시했다. `grep -rn "KEY_TICKER" scripts/` 로 재확인 |

## 8) 메모(Notes)

- **왜 A 다음인가**: A 가 「틀리면 멈춘다」를 세운 뒤라야, 키를 옮기다 생긴 사고가 조용히 지나가지 않는다
- **월말은 이미 정상이다** (`studies/month_end/runner.py:660-662`). 그 형태를 나머지 둘이 따라가는 것이 이 계획서다 — **새 규격을 만드는 것이 아니다**
- **`dataset_record` 소유자 통합은 E 로 넘긴다.** 지금 합치면 `studies → strategy` 의존이 생긴다. 중립 자리(예: `report/` 또는 `common`)로 옮기는 것이 옳고, 그것은 구조 변경이라 별도 계획서가 맞다
- 2026-09-14 실측: 커밋된 `summary.json` 9개에 절대경로. **두 PC 의 경로가 섞여 있어** 이미 「PC 마다 갈린다」가 현실이 됐다

### 후속 계획서 인계 (이 계획서를 끝낸 뒤 채운다)

> **C~G 가 실행 전에 이 절을 읽는다.** 이 계획서로 바뀐 것 중 **그쪽 전제에 영향을 주는 것만** 적는다.
> 형식: `무엇이 | 어떻게 바뀌었나 | 어느 계획서가 영향받나`
>
> 아무것도 안 바뀌었으면 **「없음」이라고 적는다** — 비워 두면 「아직 안 썼다」와 구별되지 않는다.

| 무엇이 | 어떻게 바뀌었나 | 어느 계획서가 영향받나 |
| --- | --- | --- |
| **`summary.json` 의 `datasets` 한 줄이 여섯 지점에서 같은 모양이 됐다** | `ticker`(코드)·`label`(이름)·`file`(파일 **이름**)·`period`(`시작 ~ 종료`)·`rows` 가 **같은 순서로** 앞에 온다. 검증이 자기 축을 뒤에 더 붙이는 것은 허용 | 전부. **요약을 읽는 코드는 이 다섯을 기대해도 된다** |
| **역방향 검증의 상수 세 개가 사라지고 둘이 생겼다** | 제거 `KEY_PATH`·`KEY_ROW_COUNT`·`KEY_START_DATE`·`KEY_END_DATE` / 신설 `KEY_LABEL`·`KEY_FILE`·`KEY_DATA_PERIOD`·`KEY_ROWS`. **`KEY_DATA_PERIOD` 와 `KEY_PERIOD` 는 JSON 키 값이 둘 다 `"period"` 인데 담는 것이 다르다** — 전자는 데이터 기간, 후자는 신호군의 시대 구간이다 | **D**(미사용 판정에서 헷갈리기 쉬운 자리) · 역방향 요약을 읽는 계획서 |
| **옵션 만기일 검증 `datasets` 에 `label` 이 생겼다** | `ticker` 는 이제 종목코드다. `file` 은 원래부터 이름이었다 | 옵션 만기일 산출물을 읽는 계획서 |
| **역방향 매매 `rule` 에서 `entry`·`exit` 두 칸이 사라졌다** | 상수 `KEY_ENTRY`·`KEY_EXIT` 도 지웠다. **문장은 `notes` 에 그대로 있다** — 잃은 정보 없음. 세 매매법의 `rule` 이 이제 전부 기계값만 담는다 | **F**(공통 조각을 옮길 때 `rule` 모양을 전제하는 코드) |
| **`tests/conftest.py` 에 공용 픽스처가 하나 늘었다** | `assert_no_absolute_paths(summary, name)` — 중첩을 재귀로 훑고 **사전의 키도 값과 똑같이** 본다(`row_counts` 가 파일 이름으로 키잉되기 때문). 쓰는 곳은 검증 둘·매매 셋 | 새 runner 를 만드는 계획서. **요약을 내면 이 단언을 붙인다** |
| **`tests/test_layer_contracts.py` 에 클래스 둘이 늘었다** | `TestDatasetRecordKeys`(AST 정적 — 키 집합 **과 값의 출처**) · `TestRunSummaryOwnership`(CLI 가 요약을 조립하지 않는다). **후자가 규칙을 다른 스크립트로 넓힐 자리다** | **E**·**F** |
| **`_write_dataset` 픽스처의 기본값이 갈렸다** | `ticker="069500"` · `label="합성"`. 전에는 `label=ticker` 라 **코드/이름 혼동을 영원히 못 잡는 상태**였다. 두 데이터셋 테스트 호출부도 `label=` 로 고쳤다 | 역방향 검증 테스트를 손대는 계획서 |
| **테스트가 1,116 → 1,126 개** (새 파일 없음) | `test_layer_contracts.py` +3 · `test_studies_reverse_runner.py` +3 · `test_strategy_reverse_runner.py` +2 · `test_studies_equivalence_runner.py` +1 · `test_strategy_output_contract.py` +1 | 테스트 수를 세는 계획서 |
| **CSV 는 한 셀도 바뀌지 않았다** | 21장 · 414,833칸 전 셀 일치. **C~G 는 「B 때문에 수치가 달라졌다」를 의심하지 않아도 된다** | 전부 |
| 🔴 **뒤로 넘긴 것 ① — `" ~ "` 구분자가 네 곳에 박혀 있다** | `PERIOD_SEPARATOR` 는 `strategy/run_summary.py:73` 에 있는데 **`studies` 가 import 할 수 없다**(계층 방향). 그래서 세 검증 runner 가 f-string 에 `" ~ "` 를 직접 쓴다. **형식을 고정하는 테스트가 없어 한 곳만 `" - "` 로 바뀌어도 예외가 안 난다.** 상수 관리 규칙대로면 2개 계층이 쓰므로 `common_constants.py` 자리다 | **F**(공유 조각의 자리). B 가 세 번째 자리를 만들었으므로 **F 에서 반드시 정리한다** |
| 🔴 **뒤로 넘긴 것 ② — 등가성 테스트가 실제 `storage/series/` 를 읽는다** | `runner.py:223` 의 `_load_spot(SPOT_CLOSE)` 가 **패치되지 않은 모듈 상수**를 쓴다. `tests/test_studies_equivalence_runner.py` 는 `KRW_RATE_PATH`·`USD_RATE_PATH`·`ETF_TARGETS` 만 갈아끼운다 — `tests/CLAUDE.md` 「파일 격리」 위반이고 **B 가 만든 것이 아니라 원래 있던 것**이다. B 는 합성 금리 파일 이름을 `synthetic_krw.csv`·`synthetic_usd.csv` 로 바꿔 **그 두 축만** 패치 누수가 드러나게 해 뒀다 | 등가성 검증을 손대는 계획서 |

### 진행 로그 (KST)

- 2026-09-14 12:05: 계획서 작성. 감사의 「산출물 계약 위반」 3건을 B 로 분리
- 2026-09-14 16:41~16:55: **Phase 0 재판단 게이트 완료.**

  **선행 계획서 A 복기** — ✅ Done. 인계 절에서 이 계획서에 걸리는 것 셋:

  | A 가 남긴 것 | B 에 무엇을 뜻하나 |
  | --- | --- |
  | 산출물 값이 하나도 안 바뀌었다 (CSV 27장 · 55,027행 전 셀 일치) | **Phase 3 에서 「A 때문에 수치가 달라졌다」를 의심하지 않아도 된다** |
  | `screen_candidates` 가 **축당 정확히 한 행**을 계약으로 삼는다 | B 는 축을 늘리지 않으므로 걸리지 않는다 |
  | 산출물 대조 시 **`summary.json` 의 `rule` 을 먼저 열어 구간을 맞춘다** — 폴더 이름은 잰 구간을 말하지 않는다 | Phase 3 의 기준 폴더 고를 때 이 절차를 쓴다 |

  **세 항목 판정** (전부 「한다」):

  | 항목 | 판정 | 근거 |
  | --- | --- | --- |
  | **B-1** 표시 이름이 `ticker` 자리에 | **한다** | `studies/reverse/runner.py` 475·587·993 · `studies/option_expiry/runner.py` 274. 산출물 전수 확인 결과 두 검증 모두 `('KODEX 200', None)` — `label` 키 자체가 없다. 월말만 `('069500', 'KODEX 200')` |
  | **B-2** 절대경로 | **한다** | `str(<Path>)` 3곳 생존 (`reverse/runner.py:477` · `usdkrw_equivalence/runner.py:236,239` · `run_option_expiry_study.py:218`). 절대경로가 든 `summary.json` 은 **11건** — 계획서가 적은 9건에 오늘 실행 2건이 더해졌다. **코드가 기준**이라 판정은 그대로 |
  | **B-3** `rule.exit` | **한다** | `reverse_runner.py:234` `KEY_EXIT: NOTE_STOP_BASE` 이고 `NOTE_ENTRY`·`NOTE_STOP_BASE` 가 `notes`(238행)에 또 있다 |

  **파급 확인 — 문서가 이 키를 인용하는가**: `docs/` 전수 검색 결과 **검증 계층 `summary.json` 의
  `datasets` 키를 인용하는 살아있는 문서는 없다.** 걸린 13곳은 전부 ① 「그 파일이 남는다」는 산출물
  안내이거나 ② **매매** 계층 설명(`rule.from_year` · 여섯 칸 · 「코드는 `datasets` 에 있다」)이고,
  매매 쪽은 이번 변경 대상이 아니다. **`docs/COMMANDS.md` 는 변경 없음으로 확정한다.**

  단 하나 값이 어긋나는 곳이 `docs/spec/역방향_설계.md:775` 다 —
  `empty_signal_groups` 의 키를 「`ticker·test·…`」로 적고 있는데 B-1a 가 `label` 로 개명한다.
  🔴 **그 줄은 머리글에 두 실행 ID(`20260820_162937` → `20260820_170440`)가 박힌 «대조 이력 기록»
  안에 있어 건드리지 않기로 했다** (2026-09-14 사용자 승인). 고치면 「그때 무엇이 바뀌었는지」가
  거짓이 된다. **현재 키 모양은 이번에 갱신하는 `src/verify_lab/CLAUDE.md` 출력 계약이 말한다.**

  **B-3 의 방향을 바꿨다** (2026-09-14 사용자 승인). 계획서 원안은 `KEY_EXIT` 값을 `NOTE_HOLD_LIMIT`
  으로 바꾸는 것이었으나, 조사해 보니 **나머지 두 매매법은 `rule` 에 기계값만 두고 산문은 전부
  `notes` 에 둔다** — 옵션 만기일 `{stop_levels, cells}` · 월말 `{stop_levels, from_year, targets}`.
  역방향만 `rule` 에 산문 둘을 더 얹고 그 둘이 `notes` 에도 있었다. 원안대로 값만 고치면
  **중복을 없애려 `notes` 에서 두 줄을 빼야 해 산문이 두 자리로 갈린다.** 그래서 `rule` 에서
  산문 두 키를 빼는 쪽으로 확정했다 — 잘못된 `exit` 값과 중복이 한 번에 사라지고, 청산 규칙은
  `notes` 의 `NOTE_HOLD_LIMIT` 과 `rule.hold_limit` 숫자가 그대로 담아 **잃는 정보가 없다.**
  목표 3 과 Phase 2 의 B-3 문구를 이 결정으로 고쳤다
- 2026-09-14 17:05: **Phase 1 착수 중 계획서의 틈을 찾아 Phase 2 의 B-1a 를 보강했다.**
  Phase 1 이 요구하는 최소 집합은 `ticker·label·file·period·rows` 인데 **현재 여섯 산출 지점 중
  역방향만 뒤 두 개의 이름이 다르다.**

  | | `ticker` | `label` | `file` | `period` | `rows` |
  | --- | --- | --- | --- | --- | --- |
  | 매매 셋 (`run_summary.dataset_record`) | 있음 | 있음 | 있음 | 있음 | 있음 |
  | 검증 `month_end` | 있음 | 있음 | 있음 | 있음 | 있음 |
  | 검증 `option_expiry` | **값이 표시 이름** | **없음** | 있음 | 있음 | 있음 |
  | 검증 `reverse` | **값이 표시 이름** | **없음** | **`path`(절대경로)** | **`start_date`+`end_date`** | **`row_count`** |

  B-1a 를 원안대로만 하면 역방향에 `period`·`rows` 가 없어 **DoD 의 「세 검증 + 세 매매의 키 집합이
  같다」를 만족하지 못한다.** 그래서 세 키를 함께 맞추기로 했다. 소비처를 전수 확인했고
  `run_reverse_study.py` 2줄 · `tests/test_studies_reverse_runner.py:574` 1줄뿐이라 파급이 닫힌다.
  **`run_reverse_study.py:177` 이 이미 `f"{start} ~ {end}"` 로 같은 문자열을 손으로 만들고 있어**
  읽는 쪽은 오히려 짧아진다 — 계층마다 형식이 갈릴 여지도 함께 사라진다
- 2026-09-14 17:24: **Phase 1~3 완료.** 테스트를 먼저 레드로 고정(계약 3종)하고 구현했다.
  전 테스트 1,126 통과. 산출물 확인 — 새 `summary.json` 절대경로 **0건**, `datasets` 에
  **`('069500', 'KODEX 200')`** 이 남는다. **CSV 는 21장 · 414,833칸 전 셀 일치.**
  등가성만 기준 폴더(`20260824_104655`)가 `effective_cost.csv` 생성 이전이라 그 파일 하나가 새 폴더에만
  있는데, B 는 그 runner 에서 `KEY_INPUTS` 한 곳만 바꿨으므로 **CSV 를 추가할 수 없다** — 기준이 낡은 것이다.
- 2026-09-14 17:35: **`/code-review xhigh` 13건. 11건 수정 · 2건 인계.**

  **수정한 것 중 무거운 셋**:

  | 무엇 | 왜 고쳤나 |
  | --- | --- |
  | **AST 테스트가 키 「이름」만 보고 값의 출처를 안 봤다** | `ticker` 를 `dataset.label` 로 되돌려도 **1,126개 테스트가 전부 통과**했다 — 이 계획서가 고치려던 바로 그 버그다. `test_코드와_이름과_파일이_제_출처에서_온다` 를 더해 값 표현식의 꼬리(`.ticker`·`.label`·`.name`)를 본다. **변이 테스트로 확인**: 되돌리면 실패, 복원하면 통과 |
  | **`KEY_PERIOD` 하나를 두 뜻으로 돌려썼다** | 「같은 이름이 두 가지를 가리키면 타입 검사가 못 잡는다」는 **이 diff 가 스스로 적은 경고**인데 한 화면 아래에서 같은 일을 했다. `KEY_DATA_PERIOD`(데이터 기간)와 `KEY_PERIOD`(시대 구간)로 갈랐다 — **JSON 출력은 그대로다** |
  | **계약 문구를 너무 넓게 적었다** | 「실행 스크립트는 요약을 그대로 넘긴다」가 **범위 밖인 `run_futures_leverage_study.py`·`run_leverage_tracking_study.py` 를 위반 상태로 만들었다.** 그 둘은 `datasets` 자체가 없다(쌍·계열을 잰다). 계약을 **세 매매법으로 좁히고** 그 예외를 표에 적었다 |

  **나머지 여덟**: `_strings_in` 이 사전의 **키**도 훑게 함(`row_counts` 가 파일 이름으로 키잉된다) ·
  윈도우 드라이브 접두어 제거(YAGNI — 두 PC 다 POSIX) · `assert_no_absolute_paths` 를 매매 셋에도 적용 ·
  CLI 검사에 쌍둥이 단언 추가 · 등가성 합성 파일명을 실제와 다르게(`synthetic_krw.csv` — 같으면
  monkeypatch 가 풀려도 통과) · `_returned_records` 를 반환문마다 따로 보고 중첩 함수 제외 ·
  옵션 만기일 키 순서를 매매와 맞춤 · CLI 검사를 `TestRunSummaryOwnership` 로 분리.

  **인계로 넘긴 둘**은 「후속 계획서 인계」 표 마지막 두 줄에 있다 —
  `" ~ "` 구분자의 자리(**F**)와 등가성 테스트의 기존 격리 누수다.
- 2026-09-14 17:36: **Done.** 커밋 후보는 사용자가 **1번**(`검증 / 실행 요약의 종목코드 복원과
  절대경로 제거`)을 골랐다. **산출물 폴더 8개 정리는 사용자 결정으로 건너뛰었다** — 커밋되지 않은
  채 디스크에 남는다. 그 상태로 품질 검증을 **다시 돌려 통과를 확인**했다(1126/0/0) —
  여덟이 전부 있는 상태에서 잰 값이다. 직전 검증은 뒤 네 폴더가 생기기 전이라 다시 쟀다
