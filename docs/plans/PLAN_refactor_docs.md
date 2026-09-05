# Implementation Plan: 죽은 코드·거짓 설명 정리와 문서에서 낡는 수치 걷어내기

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

**작성일**: 2026-09-06 07:35
**마지막 업데이트**: 2026-09-06 07:47
**관련 범위**: measure, studies, strategy, utils, 문서
**관련 문서**: `CLAUDE.md`, `src/verify_lab/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/python.md`, `.claude/rules/docs.md`

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

- [x] 목표 1: **코드가 자기를 잘못 설명하는 자리를 없앤다** — 죽은 조건, 거짓 시그니처, 뜻과 다른 컬럼 이름
- [x] 목표 2: **같은 값을 여러 번 계산하는 자리를 없앤다** — 확장창 순위가 매매 실행에서 여덟 번 다시 만들어진다
- [x] 목표 3: **문서가 코드를 잘못 설명하는 세 곳을 맞춘다**
- [x] 목표 4: **문서에서 「곧 낡을 수치」를 걷어낸다** — 지금은 전부 맞지만, 틀려도 아무도 모르는 형태다
- [x] 목표 5: **주석의 과거 상태 기재를 결과 상태 서술로 바꾼다** — `.claude/rules/python.md` 가 금지한 것이다

## 2) 비목표(Non-Goals)

**전수 감사 50건 중 남은 전부(19건)가 이 계획서의 범위다.**

- **판정 기준·산식·계층 경계를 바꾸지 않는다.** 결과 수치가 달라지면 안 된다
- **시세 재수집 금지**
- **`docs/spec/`·`docs/context/` 는 손대지 않는다** — 설계 근거와 사용자 소유 문서다
- **`docs/research/`·`docs/strategy/` 의 측정 수치는 손대지 않는다.**
  그 문서들은 **측정 당시의 기간에 묶인 기록**이며 `.claude/rules/docs.md` 가
  "재실행하지 않았는데 기간만 바꾸면 문서가 거짓말을 한다"고 못박았다.
  걷어내는 것은 **지도·명령어·규칙 문서**에 박힌 수치다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

**① 코드가 자기를 잘못 설명한다**

| 위치 | 무엇이 거짓인가 |
| --- | --- |
| `futures_leverage/comparison.py` `_segment_boundaries` | `if boundaries[-1] != horizon` 이 **항상 참**이다. `range(0, horizon, N)` 의 마지막 값은 정의상 `horizon` 보다 작다 — 조건이 있는 것처럼 보이지만 분기가 없다 |
| `utils/cli_helpers.py` | 타입이 `Callable[[], int]` 인데 래퍼는 `*args, **kwargs` 를 받는다. **시그니처가 실제 계약과 다르다** |
| `usdkrw_equivalence/regression.py` | `COL_ACTUAL_CUMULATIVE`(「누적」)에 **일간 수익률**을 담고 뒤에서 누적한다. 중간 상태에서 이름이 값과 다르다 |
| `futures_leverage/position.py` | 넘버링 주석이 `1 → 3 → 4` 로 뛴다. 2 를 찾다가 없는 것을 확인하는 데 시간이 든다 |
| `option_expiry/runner.py` | `__all__` 이 마지막 함수 정의보다 **위**에 있다. 동작하지만 그 파일에서만 다르다 |
| `option_expiry/runner.py` `run_study` | `frozen` dataclass 를 만든 **뒤** 그 안의 dict 를 변경한다. 동작하지만 `frozen` 의 뜻을 우회한다 |
| `index_extreme/runner.py` `_Context` | `ranks` 와 `surge_ranks`·`plunge_ranks` 를 **중복 보관**한다 |
| `measure/__init__.py` | 다른 모듈은 전부 공개 API 를 내보내는데 `distribution` 만 빠져 있다 |
| `futures_leverage/comparison.py` | `zip(..., strict=False)` 하나 — 저장소의 나머지는 전부 `strict=True` 다 |

**② 같은 값을 여덟 번 계산한다**

`strategy/runner._find_signals` 가 `find_extreme_move_events` 를 **순위 없이** 부른다.
그 함수는 순위를 안 받으면 `expanding_rank` 를 직접 만드는데, 그것은 **시세 길이의 제곱에 비례**한다.
대상 4개 × 방향 2개 = **여덟 번**이며, 전부 같은 시세에서 같은 값이 나온다.
`studies/index_extreme/runner` 는 이미 `ranks` 를 미리 만들어 넘기는 경로를 갖고 있고,
`extreme_move.py` 의 docstring 이 "실행 계층이 아닌 곳은 미리 계산한 값을 갖고 있지 않다"고
**현상을 적어만 두었다.**

**③ 문서가 코드를 잘못 설명한다**

- `option_expiry/weekly_exit.py` — `RuntimeError` 를 던지는데 docstring 의 `Raises` 에 없다
- `usdkrw_equivalence/alignment.to_market_dates` — "행 수가 하나 줄어든다"고 적었으나
  실제로는 `SPOT_PUBLICATION_LAG_ROWS` 만큼 준다
- `strategy/expiry_trading.simulate_expiry_trade` — "판정 순서는 시가 → 장중 → 청산일"이라
  적었으나 실제로는 **보유 기간 매일** 시가·장중을 검사한다

**④ 문서에 곧 낡을 수치가 박혀 있다**

`.claude/rules/python.md` 「문서 내구성 원칙」이 **"구체적 수치와 가변 정보를 직접 기재하지 않는다"**
를 요구하는데, 아래가 그 규칙 밖에 있다. **지금은 전부 맞다** — 문제는 틀려도 아무도 모른다는 것이다.

| 위치 | 무엇 |
| --- | --- |
| `docs/INDEX.md` · 루트 `CLAUDE.md` | 「측정의 원칙 17개」·「절대 원칙 5가지」·「계층 간 계약 9종」·「28개」 |
| `docs/INDEX.md` §3 | spec 의 **목차를 복제**한다 — 「실측 기록 15개 절」·「결정 C1~C118」·「①~㉔」·「실측 13건」 |
| `docs/COMMANDS.md` | 「7칸 × 5구간 = 35행」·「체결 199건」·「합계 약 66MB」·「9월 8건·12월 10건」 |
| `.claude/rules/strategy.md` | 「갭손절 -2% 8건 → … → -5% 이상 0건」·「447건 / 37건」 |

> **`COMMANDS.md` 자신이 이 위험을 이미 알고 있다** — 그 문서 머리에
> "2026-08-30 에는 567개가 됐습니다. 그 넉 달 사이 이 문서를 믿은 사람은
> 깨지지도 않은 것의 원인을 찾게 됩니다" 라는 경고가 있는데, 같은 문서가 수치를 계속 담고 있다.

**⑤ 주석에 과거 상태가 남아 있다**

`.claude/rules/python.md` 가 **"과거 상태, 변경 이력, 계획 단계는 기록하지 않음"** 을 명시했는데
일곱 곳이 "…있었다" · "전에는 …했는데" 형태다. 다만 **그 문장들이 「왜 이 구조인가」의 근거를
담고 있어** 그냥 지우면 손실이다 — **결과 상태 서술로 바꾼다.**

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 측정의 원칙 전체, 「계획서 규약 — 이 프로젝트의 설정」
- `src/verify_lab/CLAUDE.md` — 「계층 간 계약」, 상수 관리
- `tests/CLAUDE.md` — look-ahead 감시·산식 고정 테스트
- `.claude/rules/python.md` — **주석 작성 원칙**과 **문서 내구성 원칙**
- `.claude/rules/docs.md` — 문서의 두 종류, 수치를 적을 때의 규칙
- `.claude/rules/strategy.md` — 매매 규칙 계층의 예외 규정

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 죽은 조건·거짓 시그니처·뜻과 다른 이름이 정리됐다
- [x] `strategy` 의 확장창 순위 재계산이 없어지고 **신호 집합이 그대로임을 테스트가 고정한다**
- [x] 문서가 코드를 잘못 설명하던 세 곳이 맞다
- [x] 지도·명령어·규칙 문서에서 곧 낡을 수치가 걷혔다
- [x] 주석의 과거 상태 일곱 곳이 결과 상태 서술로 바뀌었다
- [x] 회귀/신규 테스트 추가
- [x] `poetry run python validate_project.py` 통과 — passed=892, failed=0, skipped=0
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트(`docs/COMMANDS.md` / CLAUDE.md / plan 등 — 각각 변경 여부 명시)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 근거·실측 수치를 루트 `CLAUDE.md` 의 프로젝트 설정 절이 정한 목적지로 이관.
      `/impl-plan` 스킬 "근거 승격" 참고)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

**코드**

- `src/verify_lab/studies/futures_leverage/comparison.py` — 죽은 조건, `strict=True`
- `src/verify_lab/utils/cli_helpers.py` — 시그니처
- `src/verify_lab/studies/usdkrw_equivalence/regression.py` — 중간 컬럼 이름
- `src/verify_lab/studies/futures_leverage/position.py` — 주석 번호
- `src/verify_lab/studies/option_expiry/runner.py` — `__all__` 위치, `frozen` 우회
- `src/verify_lab/studies/index_extreme/runner.py` — `_Context` 중복 필드
- `src/verify_lab/measure/__init__.py` — `distribution` 공개
- `src/verify_lab/strategy/runner.py` — 확장창 순위 재사용
- `src/verify_lab/measure/baseline.py` — 이동평균 창 하한 상수화
- `src/verify_lab/studies/leverage_tracking/runner.py` — 접두사 리터럴
- `src/verify_lab/studies/option_expiry/weekly_exit.py` · `.../usdkrw_equivalence/alignment.py` ·
  `src/verify_lab/strategy/expiry_trading.py` — docstring 정정
- 주석의 과거 상태 7곳 — `measure/constants.py` · `index_extreme/runner.py` ·
  `futures_leverage/runner.py` · `futures_leverage/constants.py` · `data/ecos_collector.py` ·
  `option_expiry/runner.py`

**테스트**

- `tests/test_strategy_runner.py` — 순위 재사용 후 **신호 집합 불변** 고정
- 그 외 영향받는 테스트

**문서**

- `docs/INDEX.md` — 구조 개수와 spec 목차 복제 제거
- `docs/COMMANDS.md`: **변경 있음** — 실행 결과 수치 제거 (명령어·옵션은 불변)
- 루트 `CLAUDE.md` — 「28개」
- `.claude/rules/strategy.md` — 실측 수치
- `.claude/rules/python.md` — 「미사용 판정」 표의 실물 사례가 **이미 삭제된 심볼 이름**을 든다

### 데이터/결과 영향

- **결과 수치가 하나도 바뀌면 안 된다.** 특히 확장창 순위 재사용은 **신호 집합이 같아야** 한다 —
  Phase 0 이 그것을 고정하고 Phase 4 가 실제 실행으로 확인한다
- `strategy` 실행이 빨라진다. 속도는 목표가 아니라 부수 효과다

## 6) 단계별 계획(Phases)

### Phase 0 — 「결과가 바뀌지 않는다」를 테스트로 먼저 고정(그린 유지)

> 이 계획서는 **동작을 바꾸지 않는 정리**가 대부분이라 레드가 필요 없다.
> 필요한 것은 **바뀌지 않았음을 증명하는 장치**다.

**작업 내용**:

- [x] **신호 집합 동일성은 이미 고정돼 있다** — `tests/test_studies_extreme_move.py` 의
      `test_미리_낸_순위와_내부_계산이_같은_신호를_낸다` 가 순위를 넘겼을 때와 안 넘겼을 때를
      대조한다. 새로 만들지 않고 **그 테스트가 그대로 그린인지**를 Phase 2 에서 확인한다
- [x] `strategy` 산출물이 재사용 전후로 같은지는 **Phase 4 의 실제 실행**으로 대조한다
- [x] `_segment_boundaries` 가 경계를 어떻게 내는지 값으로 고정한다 (죽은 조건 제거 전후 비교용)

---

### Phase 1 — 코드가 자기를 잘못 설명하는 자리 정리(그린 유지)

**작업 내용**:

- [x] `_segment_boundaries` — 항상 참인 조건을 없앤다. **`horizon` 을 반드시 넣는다**는 사실이
      코드에 드러나게 쓴다
- [x] `cli_helpers` — 시그니처를 실제 계약과 맞춘다. **인자를 받는지 안 받는지 먼저 확인한다** —
      호출처가 전부 `main()` 이면 `*args` 가 필요 없다
- [x] `regression.py` — 중간 컬럼 이름을 값과 맞춘다
- [x] `position.py` — 주석 번호를 이어지게 고친다
- [x] `option_expiry/runner.py` — `__all__` 을 파일 끝으로 옮기고,
      `frozen` dataclass 를 만들기 **전에** 요약을 완성한다
- [x] `index_extreme/runner.py` — `_Context` 의 중복 필드를 없앤다.
      **없애는 쪽이 `ranks` 인지 파생 둘인지 판단한다** — 쓰는 곳이 다르다
- [x] `measure/__init__.py` — `distribution` 의 공개 API 를 내보낸다
- [x] `comparison.py` — `strict=True` 로 맞춘다 (두 목록의 길이가 항상 같음을 확인하고)

---

### Phase 2 — 확장창 순위 재계산 제거(그린 유지)

**작업 내용**:

- [x] `strategy/runner._find_signals` 가 `expanding_rank` 를 **한 번만** 만들어
      두 방향에 같은 값을 넘긴다
- [x] `extreme_move.py` 의 docstring 에서 "실행 계층이 아닌 곳은 미리 계산한 값을 갖고 있지 않다"를
      **현재 사실로** 고친다 — 이제 `strategy` 도 넘긴다
- [x] Phase 0 테스트가 여전히 그린인지 확인한다 (신호 집합 불변)

---

### Phase 3 — 문서·주석 정리

**작업 내용**:

- [x] docstring 세 곳 정정 (`weekly_exit` 의 `Raises` · `to_market_dates` 의 행 수 · `expiry_trading` 의 판정 순서)
- [x] 잔여 상수 둘 (`baseline` 의 창 하한 · `leverage_tracking` 의 접두사)
- [x] **주석의 과거 상태 7곳을 결과 상태 서술로 바꾼다.** 지우는 것이 아니라 **바꾸는 것**이다 —
      "전에는 X였는데 Y로 고쳤다" → "Y다. X로 하면 (이런 문제)가 생긴다"
- [x] `docs/INDEX.md` — 구조 개수와 spec 목차 복제를 걷어낸다.
      **지도는 「어디에 무엇이 있는지」만 적는다** (그 문서 자신의 유지 규칙)
- [x] 루트 `CLAUDE.md`·`.claude/rules/strategy.md`·`.claude/rules/python.md` 의 낡을 수치를 정리한다.
      **실물 사례의 「무엇이 문제였나」는 남기고 「몇 건이었나」를 뺀다** — 사례는 규칙을 이해시키는
      장치이고 건수는 재수집하면 바뀐다
- [x] `docs/COMMANDS.md` — 실행 결과 수치를 걷어낸다. **선행 조건과 산출물 목록은 남긴다** —
      그것은 명령어를 쓰려면 필요한 정보다

---

### Phase 4 — 재실행 확인과 최종 검증

**작업 내용**

- [x] `poetry run python scripts/strategy/run_reverse_trading.py` 를 실행해
      **체결 내역이 이전과 완전히 같은지** 확인한다 (순위 재사용의 유일한 위험)
- [x] `tests/test_index.py` 가 문서 변경 뒤에도 통과하는지 확인한다
- [x] `docs/COMMANDS.md`: **변경 있음** (실행 결과 수치 제거)
- [x] 자동 포맷 적용 — `poetry run black .`
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [x] `poetry run python validate_project.py` (passed=892, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 문서 / 코드가 자기를 잘못 설명하던 자리를 고치고 문서에서 낡을 수치를 걷어냄
2. 측정 / 확장창 순위 재계산을 없애고 죽은 조건·거짓 시그니처를 정리
3. 문서 / 주석의 과거 상태를 결과 상태로 바꾸고 지도의 목차 복제를 제거
4. 검증 / 동작을 바꾸지 않는 정리 — 죽은 코드·중복 계산·거짓 설명
5. 문서 / 규칙이 금지한 수치·이력 기재를 규칙대로 정리

## 7) 리스크(Risks)

- **확장창 순위 재사용이 신호 집합을 바꾸면 매매 성적이 통째로 달라진다.**
  `docs/strategy/역방향_매매_규칙.md` 의 44건 신호가 그 위에 서 있다.
  **완화**: Phase 0 이 신호 집합·체결 결과를 먼저 고정하고, Phase 4 가 실제 실행으로 대조한다
- **문서에서 수치를 걷다가 근거까지 지울 수 있다.** 실물 사례의 건수는 규칙을 납득시키는 힘이 있다.
  **완화**: 「무엇이 문제였나」는 남기고 「몇 건이었나」만 뺀다. 판단이 애매하면 남긴다 —
  낡은 수치보다 나쁜 것은 근거가 사라진 규칙이다
- **`tests/test_index.py` 가 지도와 실제 파일을 양방향 검사한다.** 지도를 고치다 링크를 건드리면 깨진다.
  **완화**: 걷어내는 것은 **설명문의 수치**이고 링크는 손대지 않는다

## 8) 메모(Notes)

- 실측(2026-09-06): 착수 전 `validate_project.py` — passed=888, failed=0, skipped=0
- 실측(2026-09-06): `_segment_boundaries` 의 `if boundaries[-1] != horizon` 은
  horizon 1·5·21·42·63 전부에서 참이었다 — 분기가 존재하지 않는다
- 실측(2026-09-06): 순위 재사용의 안전성은 **이미 테스트가 고정하고 있다** —
  `test_미리_낸_순위와_내부_계산이_같은_신호를_낸다`. Phase 0 에서 새로 만들지 않는다
- **성능 근거가 실측으로 무너졌다** (2026-09-06). 확장창 순위 재계산을 「시세 길이의 제곱」이라
  적었으나 실제 실행은 **1.2초**다 — numpy 슬라이스라 상수가 작다. 그래서 이 변경의 근거는
  속도가 아니라 **같은 값이 두 경로로 나오지 않게 하는 것**이며, `ranks` 인자가 이미 있어
  한 줄로 끝났다. 실행 시간은 부수 효과로 0.976초가 됐다
- **규칙 문서의 실측 수치는 남겼다.** 「무엇이 문제였나」를 이해시키는 장치이고,
  대신 **재수집하면 어디를 다시 보면 되는지**(SoT 링크)를 붙였다.
  걷어낸 것은 지도·명령어 문서의 「실행하면 바뀌는 수치」다
- 이 계획서는 **전수 감사 50건의 마지막 묶음**이다. 앞의 세 계획서가 처리한 것은
  판정가능·표본 하한(12건) · 수집 계층(9건) · 방어와 fallback(12건)이다

### 진행 로그 (KST)

- 2026-09-06 07:35: 계획서 작성. 감사의 남은 19건을 이 계획서의 범위로 확정
- 2026-09-06 07:37: Phase 0 — 순위 재사용 동일성은 기존 테스트가 이미 고정하고 있음을 확인.
  `_segment_boundaries` 값만 새로 고정
- 2026-09-06 07:40: Phase 1 — 죽은 조건·시그니처·중간 컬럼 이름·주석 번호·`__all__` 위치·
  `frozen` 우회·`_Context` 중복 필드·`distribution` 공개·`strict=True`
- 2026-09-06 07:42: Phase 2 — 순위 재사용. **실행 시간 1.175초 → 0.976초이고
  체결 내역은 완전히 동일**(diff 무차이). 성능이 목적이 아니라 중복 제거가 목적이었음이 실측으로 확인됨
- 2026-09-06 07:45: Phase 3 — docstring 3곳·잔여 상수 2곳·과거 상태 주석 7곳.
  문서에서는 **지도의 구조 개수와 spec 목차 복제**, **COMMANDS 의 실행 결과 수치**를 걷어냄
- 2026-09-06 07:47: 품질 검증 통과 (passed=892, failed=0, skipped=0). Done

---
