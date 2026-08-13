# Implementation Plan: Phase 2-c 출력 계층 — 터미널 표·CSV·마크다운

> 작성/운영 규칙(SoT): `/verify-plan` 스킬(`.claude/skills/verify-plan/SKILL.md`)을 반드시 참고하세요.  
> (이 템플릿을 수정하거나 새로운 양식의 계획서를 만들 때도 해당 스킬을 포인터로 두고 준수합니다.)

**상태**: ✅ Done

---

🚫 **이 영역은 삭제/수정 금지** 🚫

**상태 옵션**: 🟡 Draft / 🔄 In Progress / ✅ Done

**Done 처리 규칙**:

- ✅ Done 조건: DoD 모두 [x] + `skipped=0` + `failed=0`
- ⚠️ **스킵이 1개라도 존재하면 Done 처리 금지 + DoD 테스트 항목 체크 금지**
- 상세: `/verify-plan` 스킬의 "3) 스킵 및 완료 규칙" 참고
- 위 조건은 `.claude/hooks/plan_lint.py`가 저장 시 자동 검사합니다

---

**작성일**: 2026-08-13 12:21
**마지막 업데이트**: 2026-08-13 12:34
**관련 범위**: report, utils, tests
**관련 문서**: `src/verify_lab/CLAUDE.md`, `scripts/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/python.md`, `docs/research/CLAUDE.md`, `docs/ROADMAP.md`

---

## 0) 고정 규칙 (이 plan은 반드시 아래 규칙을 따른다)

> 🚫 **이 영역은 삭제/수정 금지** 🚫
> 이 섹션(0)은 지워지면 안 될 뿐만 아니라 **문구가 수정되면 안 됩니다.**
> 규칙의 상세 정의/예외는 반드시 `/verify-plan` 스킬을 따릅니다.

- `poetry run python validate_project.py`는 **마지막 Phase에서만 실행**한다. 실패하면 즉시 수정 후 재검증한다.
- Phase 0은 "레드(의도적 실패 테스트)" 허용, Phase 1부터는 **그린 유지**를 원칙으로 한다.
- 이미 생성된 plan은 **체크리스트 업데이트 외 수정 금지**한다.
- 스킵은 가능하면 **Phase 분해로 제거**한다.

---

## 1) 목표(Goal)

- [x] 목표 1: `measure` 가 낸 표를 **사람이 읽는 형태로 바꾸는 계층**을 만든다.
      비율 → 백분율 변환과 반올림, 한글 레이블 부여가 여기서 일어난다
- [x] 목표 2: **신호일 전체 목록**을 신호일 한 줄짜리 wide 표로 만든다 (2-a 가 `report` 의 몫으로 미뤄둔 pivot)
- [x] 목표 3: 터미널 표 2종과 마크다운 표를 낸다. **화면에서 본 숫자를 CSV 에서 그대로 찾을 수 있어야 한다**
- [x] 목표 4: 결과 폴더 생성과 저장을 `report` 가 소유한다 —
      `storage/results/<실행시각>_<검증명>/` 에 CSV 4개와 `summary.json`

## 2) 비목표(Non-Goals)

- **이벤트 정의와 검증 실행 스크립트** — Phase 3 `studies/`·`scripts/studies/`
- **결과 문서의 서술** — 결론·해석·한계는 사람이 쓴다. 코드는 표까지만 만든다 (§8 결정 ③)
- **집계·검정 로직** — 전부 `measure` 의 일이다. `report` 는 계산하지 않는다
- **베이스라인 long-form 원자료 저장** — 전 거래일 × 12칸이라 8만 행이다. 재생성 가능하므로 남기지 않는다
- **`docs/research/` 문서 구조의 코드화** — 구조의 SoT 는 `docs/research/CLAUDE.md` 하나다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

- `measure` 는 비율(0.0625)과 영문 컬럼으로 낸다. **사람이 읽을 수 없는 형태**이며,
  이대로 결과 문서에 붙이면 검증 결과를 사용자가 대조할 수 없다
- `scripts/CLAUDE.md` 가 **신호일 전체 목록 CSV 를 필수**로 정했다. 사용자가 차트로 직접 대조하는
  원자료이며, 집계값만 있는 보고는 미완성이다
- 2-a 는 long-form 을 확정하면서 **"신호일 한 줄짜리 표는 `report` 가 pivot 해서 만든다"** 를
  근거로 삼았다. 그 약속을 지키는 것이 이 조각이다
- 결과 폴더 생성이 지금은 실측 스크립트 안에 흩어져 있다. 검증마다 같은 코드가 복제되면
  산출물 경로 규칙이 조용히 갈라진다

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 결과 보고의 원칙, 측정의 원칙 3(표본 수)·8(사용자가 직접 검증)
- `src/verify_lab/CLAUDE.md` — 계층 분리, **내부/출력 분리**(`COL_*` → `DISPLAY_*`), 데이터 저장 규칙, 출력 규약
- `scripts/CLAUDE.md` — 산출물 저장 규칙, **신호일 전체 목록 CSV 필수**
- `tests/CLAUDE.md` — 결정적 테스트(시간 고정·파일 격리), 경계 조건
- `.claude/rules/python.md` — **출력 데이터 반올림 규칙**, 타입 힌트, Path 객체
- `docs/research/CLAUDE.md` — 결과 문서 필수 구조 (코드가 복제하지 않고 참조만 한다)
- `docs/ROADMAP.md` — 확정된 forward return 반환 계약, 확정된 베이스라인·통계 계약

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/verify-plan` 스킬)

- [x] 기능 요구사항 충족 — 표 5종 생성, 터미널 출력, 마크다운 표, 결과 폴더 저장이 동작한다
- [x] 회귀/신규 테스트 추가 — pivot 정확성·백분율 변환·레이블·정렬·파일 격리·시간 고정 (30건)
- [x] `poetry run python validate_project.py` 통과 (failed=0, skipped=0; passed/failed/skipped 수 기록)
- [x] `poetry run black .` 실행 완료 (마지막 Phase에서 자동 포맷 적용)
- [x] 필요한 문서 업데이트(`docs/COMMANDS.md` / CLAUDE.md / plan 등 — 각각 변경 여부 명시)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 근거·실측 수치를 스펙/설계/ROADMAP/COMMANDS로 이관. `/verify-plan` 스킬 "근거 승격" 참고)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/report/constants.py` (신설) — 한글 레이블, 구간 이름, 반올림 자릿수, 파일명
- `src/verify_lab/report/tables.py` (신설) — 표 5종 생성, 터미널 출력, 마크다운 변환
- `src/verify_lab/report/writer.py` (신설) — 결과 폴더 생성과 저장
- `src/verify_lab/report/__init__.py` (신설) — 공개 API
- `src/verify_lab/utils/formatting.py` (수정) — `_get_display_width` 를 **공개 함수로 승격**.
  표 폭을 내용에서 자동 계산하려면 `report` 가 써야 하는데, `src/` 는 PyRight strict 라
  비공개 함수를 다른 모듈에서 부르면 검사에 걸린다. 이름만 바꾸고 동작은 그대로다
- `tests/test_formatting.py` (수정) — 위 이름 변경 반영
- `tests/test_report_tables.py` (신설)
- `tests/test_report_writer.py` (신설)
- `docs/ROADMAP.md` (Phase 2-c 체크박스 + **확정된 출력 계약** 절 신설)
- `START_PROMPT.md` (다음 작업을 Phase 3 로 갱신)
- `docs/COMMANDS.md`: **변경 없음** — 실행 스크립트를 만들지 않는다. 검증 실행 명령은 Phase 3 에서 생긴다
- `docs/INDEX.md`: **변경 없음** — `docs/`·`reference/` 에 파일을 추가하지 않는다

### 데이터/결과 영향

- **`storage/results/` 아래에 실제 폴더를 만드는 첫 코드**다. 테스트는 `tmp_path` 로 격리하고
  경로 상수를 캡처한 모듈까지 함께 패치한다 — 놓치면 테스트가 실경로를 건드린다
- 저장 값은 **백분율 2자리**로 반올림된다. `measure` 반환값(비율)은 바뀌지 않는다
- 기존 산출물 형식과 충돌하지 않는다. 검증 산출물을 만드는 코드가 아직 없었다

## 6) 단계별 계획(Phases)

### Phase 0 — 표시 계약을 테스트로 먼저 고정(레드)

> 표시 단위와 레이블이 흔들리면 **화면에서 본 숫자를 CSV 에서 못 찾는다.** 사용자가 직접
> 대조하는 것이 이 프로젝트의 전제이므로 그 계약을 먼저 못 박는다.

**작업 내용**:

- [x] `utils/formatting.py` 의 `_get_display_width` 를 `get_display_width` 로 승격하고
      `tests/test_formatting.py` 를 맞춘 뒤 **그린을 확인**한다 (동작 변경 없음)
- [x] `tests/test_report_tables.py` — 표 생성 계약을 고정
      - 신호일 목록: long-form 이 **신호일 한 줄**로 펼쳐지고, 제외된 칸은 값이 비어 있다
      - 백분율 변환과 2자리 반올림이 적용된다 (0.062512 → 6.25). p 값만 4자리다
      - 한글 레이블과 구간 이름(1일·1주·1개월·3개월·6개월·1년)이 붙는다
      - 행 정렬은 **구간 → 기준** 이다 (같은 구간의 두 기준이 인접해야 갭이 보인다)
      - 검정하지 않은 칸은 빈칸이 아니라 **사유가 보인다**
      - 마크다운 표에 헤더·구분선·행이 모두 나오고 빈 값이 깨지지 않는다
- [x] `tests/test_report_writer.py` — 저장 계약을 고정
      - 결과 폴더 이름이 `<실행시각>_<검증명>` 이다 (`freeze_time` 으로 고정)
      - CSV 는 `utf-8-sig`, 인덱스 없이 저장된다
      - `summary.json` 에 실행 파라미터가 남는다
      - **`tmp_path` 격리** — 실제 `storage/` 를 건드리지 않는다

---

### Phase 1 — 표 생성 구현(그린 유지)

**작업 내용**:

- [x] `src/verify_lab/report/constants.py` — `DISPLAY_*` 레이블, 구간 이름 표, 자릿수, 파일명
- [x] `src/verify_lab/report/tables.py`
      - `build_signal_table(frame, signal_details=None)` — 신호일 한 줄 wide.
        `signal_details` 로 순위·사건 번호 같은 검증별 컬럼을 앞에 붙일 수 있게 둔다 (Phase 3 가 채운다)
      - `build_statistics_table(summary)` — 칸별 집계
      - `build_excess_table(excess_by_baseline)` / `build_test_table(test_by_population)` — CSV 용 (베이스라인 컬럼 포함)
      - `build_comparison_table(excess_by_baseline, test_by_population)` — 터미널·마크다운 용 (베이스라인을 열로 펼침)
      - `print_dataframe(table, logger, title=None)` — 내용에서 폭을 자동 계산해 `TableLogger` 로 출력
      - `to_markdown(table)` — 마크다운 표 문자열. **`tabulate` 의존성을 추가하지 않는다**
- [x] Phase 0 의 tables 테스트 그린 확인

---

### Phase 2 — 저장 구현(그린 유지)

**작업 내용**:

- [x] `src/verify_lab/report/writer.py`
      - `create_run_directory(study_name)` — `storage/results/<실행시각>_<검증명>/`. 덮어쓰지 않는다
      - `save_table(directory, filename, table)` — `utf-8-sig`, 인덱스 없음
      - `save_run_summary(directory, payload)` — 실행 파라미터와 핵심 통계
- [x] `src/verify_lab/report/__init__.py` — 공개 API
- [x] Phase 0 의 writer 테스트 그린 확인

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [x] `docs/ROADMAP.md` — Phase 2-c 체크박스 완료, **확정된 출력 계약** 절 신설
      (표시 단위, 파일 구성, 표 분할과 **그 근거**)
- [x] `START_PROMPT.md` — 현재 상태와 다음 작업(Phase 3)으로 갱신
- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` **변경 없음** — 사유는 Scope 에 명시)
- [x] `poetry run black .` 실행(자동 포맷 적용)
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [x] `poetry run python validate_project.py` (passed=188, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 출력 / report 계층 신설 — 신호일 목록 wide 변환과 표시 단위 확정
2. 출력 / 터미널 표·CSV·마크다운 출력 구현
3. 출력 / 검증 산출물 저장 경로를 report 계층으로 단일화
4. 출력 / 표시용 변환 계층 추가 + 파일 격리 테스트
5. 출력 / 결과 표 5종 생성과 저장 규약 구현

## 7) 리스크(Risks)

- **테스트가 실제 `storage/` 를 건드릴 위험** — `writer` 가 import 시점에 경로 상수를 캡처하면
  `common_constants` 만 패치해도 소용없다. `meta_manager` 에서 이미 겪은 문제이며,
  같은 방식으로 **모듈 자체를 함께 패치**한다
- **화면과 CSV 의 숫자가 달라질 위험** — 터미널용과 저장용을 따로 가공하면 반올림 시점이 갈린다.
  **같은 표시용 프레임 하나를 두 곳이 함께 쓴다**
- **`report` 가 계산을 시작할 위험** — 표시용 파생값이 필요해 보이면 그것이 정말 표시용인지 의심한다.
  집계·검정은 전부 `measure` 의 일이다
- **폭 자동 계산이 터미널을 넘칠 위험** — 컬럼이 많으면 한 줄이 120칸을 넘는다.
  베이스라인 절대값은 터미널에 넣지 않고 CSV 로 보내 열 수를 줄인다
- **`utils/formatting.py` 이름 변경이 다른 곳을 깨뜨릴 위험** — 호출처는 같은 파일 안 2곳과
  테스트 6곳뿐이다. 이름만 바꾸고 동작은 그대로 두며, 기존 테스트가 그대로 통과하는 것이 증거다

## 8) 메모(Notes)

### 확정한 설계 결정과 근거

사용자 확인을 거쳐 확정한 항목 ①~④ 와, 그로부터 파생된 구현 결정 ⑤~⑧ 이다.

| # | 항목 | 확정 | 탈락안 | 근거 |
| --- | --- | --- | --- | --- |
| ① | **터미널 표 분할** | **대상별 2표**(신호군 요약 / 초과분·검정), 행은 **(구간 → 기준)** | 기준별 4표 / 베이스라인별 4표 / 한 표에 전부 | 기준을 2종 두는 이유가 "둘의 차이 = 갭으로 새는 몫"이므로 **두 값이 눈으로 붙어 있어야** 그 해석이 성립한다. 행을 (구간 → 기준)으로 두면 같은 구간의 두 기준이 위아래로 온다. 한 표에 전부 넣으면 20열이 넘어 터미널에서 줄바꿈되고, 기준별로 나누면 갭 비교가 표를 넘나든다 |
| ② | **CSV 구성** | **역할별 4개**(신호일 목록·집계·초과분·검정) + 실행 파라미터 `summary.json` | 2개로 최소화 / long-form 원자료까지 전부 | 네 표는 **컬럼 구성이 서로 완전히 다르다.** 한 파일에 섞으면 빈 칸이 대부분인 표가 된다. 반대로 베이스라인 long-form 원자료(전 거래일 × 12칸 = 8만 행)는 재생성 가능하고 사용자가 열어볼 것이 아니므로 남기지 않는다 |
| ③ | **마크다운 자동화 범위** | **표 렌더링까지만.** 서술은 사람이 쓴다 | 섹션 뼈대까지 초안 생성 / 마크다운 생성 안 함 | `docs/research/CLAUDE.md` 가 요구하는 것(결론 → 근거 → 해석 → 한계 → 재현)은 대부분 **서술**이고, 문서 구조의 SoT 는 이미 그 규칙 문서다. 코드가 뼈대를 찍으면 구조가 두 곳에 복제되어 갈라지고, 빈 「한계」 자리표시자가 그대로 남을 위험이 생긴다. 표를 손으로 옮기지 않는 것만으로 오타 위험은 사라진다 |
| ④ | **표시 단위** | **저장 직전 백분율 2자리** (`measure` 는 비율 유지) | 비율 4자리 저장 / `measure` 부터 백분율 | `.claude/rules/python.md` 반올림 규칙표가 "백분율(수익률·MDD·승률·등락률) → 2자리"로 이미 확정했다. `measure` 부터 백분율로 내면 "모든 비율 값은 0~1 소수"라는 표기 규칙이 깨진다. 내부는 비율·영문 토큰, 저장 직전 변환은 기존 **내부/출력 분리** 와 같은 형태다 |
| ⑤ | **터미널과 CSV 의 값 일치** | **같은 표시용 프레임 하나**를 터미널과 CSV 가 함께 쓴다 | 터미널용·저장용을 따로 가공 | 따로 가공하면 반올림 시점이 갈려 화면의 숫자를 CSV 에서 못 찾는다. 사용자가 직접 대조하는 것이 이 프로젝트의 전제(측정의 원칙 8)이므로 두 값이 달라지면 안 된다 |
| ⑥ | **결과 폴더의 소유자** | **`report` 가 만든다** | 스크립트가 만든다 | 지금은 실측 스크립트가 각자 만들고 있어 검증이 늘 때마다 같은 코드가 복제된다. 경로 규칙이 조용히 갈라지면 나중에 그 결과들이 같은 검증의 산출물인지 알 수 없게 된다. 스크립트는 인터페이스만 담당한다 |
| ⑦ | **마크다운 표 생성 방법** | **직접 문자열로 만든다** | `pandas.to_markdown()` 사용 | `to_markdown()` 은 `tabulate` 패키지를 요구하는데 이 프로젝트 의존성에 없다. 표 하나를 그리려고 의존성을 늘리지 않는다. 직접 만들면 빈 칸 표기와 정렬도 통제할 수 있다 |
| ⑧ | **검정하지 않은 칸의 표기** | 빈칸이 아니라 **사유 문자열**을 그대로 보여준다 | 빈칸 / "-" | 빈칸은 "값이 0" 또는 "아직 안 돌았다"로 읽힌다. "표본 부족으로 검정 불가"가 결론의 일부이며, 검증 #1 의 QQQ 는 **12칸 전부 이 표기**가 된다 |

### 미리 확인한 사실

- `TableLogger` 는 컬럼 폭을 **인자로 받는다.** 표마다 폭을 손으로 적으면 데이터가 바뀔 때 깨지므로,
  내용에서 폭을 계산하는 얇은 함수를 `report` 에 둔다. 그 계산에 `utils/formatting` 의 폭 함수가 필요하다
- `TableLogger` 는 **DEBUG 레벨로 출력한다.** 로그 레벨 설정에 따라 안 보일 수 있으므로
  검증 스크립트(Phase 3)에서 레벨을 확인한다
- 결과 폴더 이름 관용은 이미 있다 — `RESULTS_DIR / f"{시각}_{접미사}"`, CSV 는 `utf-8-sig`.
  새 규칙을 만들지 않고 그대로 따른다
- 신호일 목록에 들어갈 **순위·사건 번호·z-score 는 `studies` 소속**이라 지금은 없다.
  `build_signal_table` 이 그 컬럼들을 받아 앞에 붙일 수 있는 자리만 열어 둔다

### 진행 로그 (KST)

- 2026-08-13 12:21: 계획서 작성. 터미널 표 분할·CSV 구성·마크다운 범위·표시 단위 4건을
  사용자 확인으로 확정하고, 파생 결정 ⑤~⑧ 을 함께 정리
- 2026-08-13 12:25: `get_display_width` 승격 후 기존 8건 그린 확인. `report/` 3개 모듈과
  테스트 27건 작성, 전부 그린. `report/.gitkeep` 은 폴더에 파일이 생겼으므로 삭제
- 2026-08-13 12:31: **실데이터 출력 확인에서 결함 1건 발견하고 수정.**
  오른쪽 정렬 컬럼은 정렬 여백이 **값 앞쪽**에만 붙어서, 폭만 늘리면 다음 컬럼과 글자가 맞닿는다
  (헤더가 `p값비고` 로 읽혔다). 여백을 값에 직접 다는 방식으로 고치고 **감시 테스트 3건을 추가**했다.
  `print_dataframe` 이 테스트 없이 넘어갈 뻔한 지점이었다
- 2026-08-13 12:33: 실데이터 출력물 전체 확인 — 신호일 목록 7행·집계 12행·초과분 36행·검정 36행과
  `summary.json` 이 정상 생성됐고, 저장된 CSV 값이 스펙 §8 표와 일치했다.
  확인용으로 만든 `storage/results/*_smoke_report/` 폴더는 삭제했다
- 2026-08-13 12:34: 최종 검증 통과 (passed=188, failed=0, skipped=0)

### 발견했으나 고치지 않은 것

- `utils/formatting.py` 의 `TableLogger.print_row` 가 헤더와의 로거 함수명 길이 차이를 보정하려고
  **공백 2칸을 더한다.** 실제 차이는 3칸이라 데이터 행이 헤더보다 1칸 밀린다.
  이 계획서 이전부터 있던 동작이라 **언급만 하고 손대지 않았다** (수술적 변경 원칙)
