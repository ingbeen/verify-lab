# Implementation Plan: 경량화 ⑧ — COMMANDS.md 컴팩트화와 설명 이관

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

**작성일**: 2026-09-26 16:55
**마지막 업데이트**: 2026-09-28 17:53
**관련 범위**: `docs/COMMANDS.md`, `scripts/**/*.py` 의 모듈 docstring 과 argparse 도움말, `src/verify_lab/data/*_collector.py` docstring, 각 결과 문서의 「재현 방법」 절, COMMANDS 의 절 이름을 가리키는 문서
**관련 문서**: `scripts/CLAUDE.md`, `.claude/rules/research.md` 「재현 방법을 남긴다」, 루트 `SLIM_SERIES.md`, `docs/plans/REPORT_lightweight_inventory.md` §6 · §12, `docs/plans/AUDIT_slim_doc_code_mismatch.md` §1 (COMMANDS 행)

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

- [x] 목표 1: `docs/COMMANDS.md` 를 **명령 + 한 줄 주석**으로 줄인다 (작성 시점 495줄 → 약 110 ~ 140줄)
- [x] 목표 2: COMMANDS 가 담던 설명을 **그 설명의 대상 옆**으로 옮긴다 — 잃는 설명이 없다 (보고서 §10 Q3)
- [x] 목표 3: 옮기며 **틀린 설명은 고쳐서** 옮긴다 (AUDIT_slim_doc_code_mismatch §1 의 COMMANDS 행)

## 2) 비목표(Non-Goals)

- **CLI 동작 변경** — 인자·기본값·출력은 그대로다. 바뀌는 것은 docstring·도움말 문구뿐이다
- **`docs/COMMANDS.md` 경로 변경** — 결과 문서 여러 장의 「관련 파일」이 링크하고 `tests/test_research_docs.py` 가 실재를 검사한다
- 규칙 문서 정리 — ④ 에서 끝났다. COMMANDS 의 절 이름을 가리키는 줄만 고친다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

- COMMANDS 가 명령보다 설명이 길다 — 산출물 파일 목록 · 설계 근거 · 데이터 소스 함정 · 매매법 해석 주의 · 코드가 지워진 트랙의 이력(「코드가 없는 트랙」 절)이 한데 섞였다. 그 설명들은 **스크립트·수집기·결과 문서와 두 벌**이고 이미 어긋났다 — `summary.json` 최상위 「여섯 칸」(실제 다섯), 없는 `거는 방향` 컬럼, 역방향 「순열 검정이 없어 수 초」(순열 1000회가 돈다), 선물 「3방식」(4방식), 「원달러 그리드용」·「검증 #10 용」 표지(그 트랙들 코드 없음), 기본값과 같은 「다른 종목」 예시, 「DNS 는 잠시 뒤 재실행」(전역 규칙은 보조 DNS)
- 사용자 결정(§10 Q3): **설명은 대상 옆으로 분산**

### 설명을 어디로 옮기나 (보고서 §6.2)

| COMMANDS 속 설명 | 옮길 곳 |
| --- | --- |
| 인자의 뜻 · 기본값 · 저장 경로 · 덮어쓰기 · 「최근 제외」 | 그 스크립트의 **모듈 docstring · argparse 도움말** — 이미 있는 것과 대조해 빠진 것만 옮긴다 |
| 데이터 소스 함정 (KRX 계정 · pykrx 가 로그인 ID 를 출력 · 선물 두 상품 동시 실행 금지 · ECOS 키가 URL 에 · FRED 휴일 행 · 지수 OHLC · ETN 에 시세 함수 없음) | 그 **수집기 모듈 docstring** + 이미 있는 `설계.md` 「데이터 실측 기록」 |
| 매매법 산출물 파일 설명 · 해석 주의 (「1차 판정에 변별력 없음」 등) | 그 매매법 **`결과.md` 「재현 방법」** (research.md 가 요구하고 테스트가 그 절의 존재를 검사한다) |
| 공통 산출물 규격 (`summary.json` · 빈칸 ≠ 0) | `src/verify_lab/CLAUDE.md` 「매매 산출물 계약」 — 이미 SoT. 중복만 지운다 |
| 품질 검증 통과 기준 · `VIRTUAL_ENV` 증상 | **COMMANDS 에 1줄씩 유지** — 증상이 나는 자리다(④ 가 bootstrap 에서 지우고 여기를 SoT 로 남겼다) |
| 「코드가 없는 트랙」 절 | **삭제** — INDEX 「매매법·조사」 표의 상태·코드 칸과 각 한 장 문서의 재현 방법(복원 절차)이 대신한다 |

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- `.claude/plan-config.json` — 이 저장소의 검증 명령·자동 포맷·근거 승격 목적지 (**값의 SoT**)
- 루트 `CLAUDE.md` — 특히 「실행 명령어 관리 원칙」(COMMANDS 가 명령어의 단일 SoT) · 「계획서 규약」
- `scripts/CLAUDE.md` — CLI 계층 책임 · 인자 정책 · 사용자에게 보이는 문구는 한글로 「무엇이 잘못됐고 무엇을 해야 하는지」
- `.claude/rules/research.md` 「재현 방법을 남긴다」 — 실행 명령어는 COMMANDS 를 참조로 걸고 결과 문서에 중복 기재하지 않는다
- 루트 `SLIM_SERIES.md` 「시리즈 공통 주의」

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] COMMANDS 가 명령 + 한 줄 주석(+ 품질 검증 1줄 · VIRTUAL_ENV 1줄 · 수집 전 주의 1줄)이다 — 줄 수를 진행 로그에
- [x] COMMANDS 에서 지운 설명 문장마다 **새 자리 또는 삭제 사유**가 진행 로그 표에 있다 (잃는 설명 0)
- [x] COMMANDS 에 남은 모든 명령의 인자가 해당 스크립트 argparse 에 실재한다 (스크립트로 전수)
- [x] 모든 실행 스크립트의 `--help` 가 오류 없이 나온다 (`tests/test_layer_contracts.py` 의 도움말 검사 포함)
- [x] COMMANDS 의 옛 절 이름을 가리키는 문서가 없다
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — `docs/COMMANDS.md` **변경 있음**(이 계획서의 대상) · 결과 문서 재현 방법 · `SLIM_SERIES.md`
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다 (옮긴 설명 자체가 승격이다)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `docs/COMMANDS.md`
- `scripts/run_*.py` · `scripts/data/*.py` — 모듈 docstring · argparse `help`
- `src/verify_lab/data/{yfinance,pykrx,krx_futures,etn,ecos,fred}_collector.py` — 모듈 docstring
- `docs/매매/*/결과.md` · `docs/조사/**/결과.md` · `docs/조사/*.md` — 「재현 방법」 절
- COMMANDS 의 절 이름(「검증 실행」 · 「매매 규칙 실행」 · 「검증 #1 — 역방향」 등)을 가리키는 문서
- `SLIM_SERIES.md` · 보고서 §12 · 이 계획서

### 데이터/결과 영향

- 없음 (도움말·docstring 만 바뀐다)

## 6) 단계별 계획(Phases)

### Phase 1 — 설명을 옮긴다 (그린 유지)

**작업 내용**:

- [x] 착수 전: `git status` 깨끗 · 계획서 ⑦ 커밋 확인 · COMMANDS 줄 수를 진행 로그에
- [x] COMMANDS 의 설명 문장(불릿·인용 블록)을 전부 뽑아 **옮길 곳 표**(위 「설명을 어디로 옮기나」)에 한 줄씩 배정한다 — 진행 로그에 표로
- [x] 배정대로 옮긴다. **옮기기 전에 사실을 확인한다** — AUDIT_slim_doc_code_mismatch §1 의 COMMANDS 행과 이 계획서 3) 의 틀린 설명은 코드를 읽어 고친 뒤 옮긴다. 대상에 이미 같은 설명이 있으면 옮기지 않고 COMMANDS 쪽만 지운다
- [x] 백로그(보고서 §12.1 「⑥」 — 옛 번호, 지금 ⑧): 중간선거 `--help`·로그 문구가 분할매수·진입 위치 표를 말하지 않는다 → 도움말에 반영

**Validation**:

- [x] 옮긴 설명마다 새 자리 grep 결과가 진행 로그 표에 있다
- [x] 모든 실행 스크립트 `poetry run python <스크립트> --help` 가 0 으로 끝난다

---

### Phase 2 — COMMANDS 를 다시 쓴다 (그린 유지)

**작업 내용**:

- [x] 머리말: 「평상시 반복 실행하는 명령만 둔다. 인자의 뜻은 `--help`, 산출물을 읽는 법은 그 매매법 `결과.md` 의 「재현 방법」」
- [x] 품질 검증(통과 기준 `failed=0 skipped=0` 1줄 · `VIRTUAL_ENV` 1줄) · 데이터 수집(외부 호출 · 이미 있으면 다시 받지 않는다 · 재수집하면 결과 문서에 흔적 — 1줄) · 매매법·조사 실행. 절 제목은 **INDEX 와 같은 한글 이름**으로 통일(지금은 「검증 #1 — 역방향」과 「매매 — 중간선거_사이클」이 섞여 있다)
- [x] 기본값과 같은 예시(`--ticker 069500 --start 20021014`)는 지운다. 인자가 있는 명령은 대표 하나씩만
- [x] 「코드가 없는 트랙」 절을 지운다
- [x] COMMANDS 의 옛 절 이름을 가리키는 문서를 grep 해 문서 단위 포인터로 고친다

**Validation**:

- [x] COMMANDS 의 명령에서 인자를 뽑아 각 스크립트 argparse 와 대조하는 스크립트 결과 불일치 0
- [x] `poetry run pytest tests/test_research_docs.py tests/test_index.py -q` 통과 (COMMANDS 링크 실재)

---

### Phase 3 (마지막) — 문서 정리 및 최종 검증

**작업 내용**

> 🔴 **`/commit` 이 «맨 마지막»인 것은 의도다.** 그 스킬은 「후보 뒤에는 아무것도 덧붙이지 말 것」으로
> 끝나므로 **호출하는 순간 그 턴이 거기서 닫힌다.** 중간에 두면 뒤에 적힌 항목이 그 벽 너머에 남는다 —
> 실제로 두 번 그렇게 샜다(`[실측] 2026-09-14` 후보를 계획서에 안 옮김 · `2026-09-16` 옮기고 체크박스를 안 닫음).
> **체크박스와 상태를 먼저 확정하고, 커밋 후보를 마지막에 만든다.**

- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` 변경 확인)
- [x] 보고서 §12 백로그 · `SLIM_SERIES.md` 진행 표와 인계 메모 갱신 — **이 계획서가 시리즈의 마지막이다.** 인계 메모에 「끝 — 정리」 단계가 할 일(남은 백로그 목록 · 사용자에게 물을 것)을 적는다
- [x] 자동 포맷 적용 (`poetry run black .`)
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] Validation 절에 `/code-review` 와 품질 검증 **실행 결과**를 적는다
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정
- [x] 🔴 **마지막에 `/commit` 을 실행하고 그 후보를 «이 계획서» 의 `#### Commit Messages` 절에 옮긴다** —
      `/commit` 은 계획서를 모르고 「후보 뒤에 아무것도 덧붙이지 말 것」으로 끝나므로,
      **대화에만 내면 그 절이 빈 채로 남는다.** 체크박스 갱신이 diff 에 더 들어가지만
      커밋 메시지의 내용을 바꾸지 않는다. **커밋은 사용자가 한다 — 후보만 낸다**

**Validation**:

> 순서를 지킨다 — 리뷰에서 고치면 코드가 바뀌므로 품질 검증이 마지막 관문이어야 한다.
> **버그가 0 인 회차에서 끝낸다.** 2회차에도 버그가 나오면 사용자에게 보고하고 3회차 여부를 묻는다 —
> 「그 외」는 목록만 남기고 고치지 않는다. `/impl-plan` 의 「코드 리뷰」 절이 SoT 다.

- [x] `/code-review xhigh` **1회차** (발견 12건 — 버그 0 · 그 외 12 · 조치: ⑧ 이 만든 그 외 6건(F3 · F6 · F8 · F9 · F10 · F12)은 사용자 결정으로 수정, 나머지 6건(⑦ 이 만든 F1 · 기존 F2 · F4 · F5 · F7 · F11)은 보고서 §12.10 백로그)
- [x] `poetry run python validate_project.py` (passed=1242, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다.**
> 계획서를 쓰는 시점에는 diff 가 없어 여기 적는 것은 전부 추측이고,
> **추측으로 적은 줄은 그대로 나간다.** 형식·문체 규칙은 `/commit` 이 정한다.

1. 문서 / COMMANDS 를 명령과 한 줄 주석으로 줄이고 설명을 스크립트·수집기 docstring 과 결과 문서 재현 방법으로 이관
2. 문서 / COMMANDS 493줄 → 125줄 컴팩트화와 설명의 대상 옆 이관
3. 문서 / 실행 명령어 문서 경량화 — 틀린 설명(summary.json 여섯 칸·거는 방향·3방식·수 초) 정정과 코드가 없는 트랙 절 삭제
4. 문서 / COMMANDS 설명의 코드 옆 이관으로 두 벌 해소, 선물 방식 수·ECOS 환율 계열·프로브 재실행 안내 등 docstring 정정
5. 문서 / 경량화 ⑧ — COMMANDS 컴팩트화, 러너 산출물 표·수집기 docstring 보강, 결과 문서 재현 방법의 포인터 정리

## 7) 리스크(Risks)

- **설명을 옮기다 잃는다** — 문장 단위 배정표(Phase 1)가 막는다. 표에 없는 문장이 COMMANDS 에서 사라지면 안 된다
- **틀린 설명을 그대로 옮긴다** — 옮기기 전에 코드로 확인한다(AUDIT 의 COMMANDS 행이 알려진 오류 목록이다)
- **도움말 문구가 길어져 `--help` 가 읽히지 않는다** — 인자별 한두 줄, 긴 사정은 모듈 docstring 으로
- **`VIRTUAL_ENV`** — 모든 도구가 실패하면 `env -u VIRTUAL_ENV`

## 8) 메모(Notes)

- 시리즈의 SoT 는 루트 `SLIM_SERIES.md`. 이 계획서는 ⑧(마지막)이며 **커밋 하나**로 끝난다. 그 뒤는 `SLIM_SERIES.md` 「끝 — 정리」다
- ⑥ ⑦ 이 COMMANDS 의 **경로만** 고쳐 두었다(달력·원달러 문서 이동)

### 진행 로그 (KST)

- 2026-09-26 16:55: 계획서 작성 (Draft). 착수는 `SLIM_SERIES.md` 를 받은 세션이 한다
- 2026-09-28 17:07: 착수. `git status --short` 비어 있음 · ⑦ 커밋 `8ee75ee` 확인(reflog: `9a0f7fd` 커밋 → `0746727` 로 reset → 재커밋. 새 파일 `docs/조사/원달러_ETF_등가성/설계.md` 가 추적됨) · `docs/COMMANDS.md` **493줄**
- 2026-09-28 17:07: **계획서에 없던 판단 넷 — 사용자 결정 (전부 추천안)**
  1. **산출물 설명의 자리**: 선물·괴리는 `studies/<slug>/runner.py` 모듈 docstring 의 산출물 표를 SoT 로 두고 낡은 칸만 고친다(괴리 축 「시기」 → 넷 · 선물 `그대로 두기 오차` 누락). `결과.md` 「재현 방법」에는 포인터 한 줄. 등가성은 러너에 표가 없어 `결과.md` 「재현 방법」에 한두 줄 — 설명을 두 벌로 만들지 않는다
  2. **선물 「세 방식」(실제 넷) 4곳도 고친다** — `studies/futures_leverage/{__init__,runner,comparison}.py` 머리 · `constants.py:160` (Scope 밖 · 주석만)
  3. **「대표 하나씩만」은 «변형만 줄임»** — 같은 인자의 변형(SPY·DIA · ^GSPC·^IXIC · 지수 넷 · 261240·261250)을 하나로. 목적이 다른 인자(`--dataset` 좁히기 · `--repeats/--seed` 재현)는 남긴다. 지수별 시작일은 `collect_pykrx.py` docstring 으로
  4. **인접 백로그 주석 셋도 고친다** — `check_pykrx_etf.py:9` · `check_pykrx_splice.py:20` 「사용자만 실행한다」(R5-16 · RV6-4) · `ecos_collector.py:91` 「둘 다 2자리」(RV7-3)
  - 그 밖에 범위 안에서 찾은 오류: 역방향 `결과.md` §14.1 「`--adjusted` 를 붙이면 수정주가가 같은 파일명에 덮어쓰인다」 — 실제로는 `_adjusted_max.csv` 로 따로 저장된다(`yfinance_collector.py` `ADJUSTED_FILE_TEMPLATE`). 재현 방법 절이라 고친다
- 2026-09-28 17:07: **COMMANDS 설명 문장 배정표** (줄 번호는 `8ee75ee` 기준 · 「이미」는 대상에 같은 설명이 있어 COMMANDS 쪽만 지운다는 뜻)

  | # | COMMANDS 줄 | 설명 요지 | 새 자리 / 삭제 사유 |
  | --- | --- | --- | --- |
  | C1 | 3-5 | SoT · 다른 문서에 기재 안 함 · 반복 명령만 | COMMANDS 머리말 유지 (+ `--help` · 재현 방법 안내) |
  | C2 | 12 · 15-24 | 전체 검증 구성 · 개별 · 커버리지 · 포맷(마지막 Phase) | COMMANDS 명령 + 한 줄 주석 유지 |
  | C3 | 27-29 | VIRTUAL_ENV 증상 · 확인 · 원인 · 대처 | COMMANDS 유지 (④ 가 여기를 유일한 자리로 정함) |
  | C4 | 31 | 통과 기준 `failed=0 skipped=0` | COMMANDS 주석 유지 |
  | C5 | 33-38 | `passed` 절대값을 기준선으로 삼지 않음 · 직전 실행과 비교 · 1034 → 567 사건 | 규칙은 COMMANDS 한 줄로 유지. **사건 서술은 삭제** — 이력(`.claude/rules/docs.md` 「과거형이 허용되는 자리」: COMMANDS 는 현재형) |
  | C6 | 44-46 | AI 직접 실행 · 다시 받지 않음 · 덮어쓰면 결과 문서에 기준일 | COMMANDS 「수집 전 주의」 한 줄 유지 (SoT 루트 「스크립트 실행 규칙」 · 「재수집은 이미 나온 결과를 바꿉니다」) |
  | C7 | 51-63 | yfinance 명령 · `--ticker DIA` · `--index '^IXIC'` | 명령 유지. DIA · ^IXIC 는 변형이라 삭제(판단 3) — 필요한 파일 목록은 중간선거 `결과.md` §15 선행 조건 |
  | C8 | 58 · 61 | 「수정주가는 대조·실측용」 · 「중간선거_사이클용」 | 앞은 COMMANDS 주석 유지. 뒤는 삭제 — 소비자 표지는 낡는다 |
  | C9 | 66 | 전 기간 · `<종목>_max.csv` · 덮어씀 | `collect_yfinance.py` 모듈 docstring 에 추가(파일명 형식은 `src/verify_lab/CLAUDE.md` 「원시 시세 저장 규칙」 이미) |
  | C10 | 67-70 | 원본가 기본 · 근거 · `--adjusted` 는 따로 저장 | 원본가·근거는 `yfinance_collector.py` 모듈 docstring 이미. 「따로 저장」은 `--adjusted` help 에 추가. 역방향 `결과.md` §14.1 의 반대 서술을 고침 |
  | C11 | 71 · 72 | 최근 며칠 제외 · 이상치면 파일 없이 예외 | `yfinance_collector.py`(`RECENT_EXCLUSION_DAYS` 주석 · `collect_yfinance_history` docstring) 이미 |
  | C12 | 73-78 | `--index` 종가 계열 · 경로 · `^` 뗌 · OHLC 가 종가로 채워짐(34.5% · 24.7%) · 작은따옴표 | `--index` help · `collect_yfinance_index` docstring 이미. 작은따옴표는 명령 입력법이라 COMMANDS 주석 유지 |
  | C13 | 82-83 · 181 · 204 | KRX 계정 · `.env` 의 `KRX_ID` · `KRX_PW` | COMMANDS 절 머리 한 줄 유지 (스크립트 description 「KRX 계정 필요」 · `krx_credentials` 오류 메시지 이미) |
  | C14 | 86 · 89-90 | ETF 실측 주석 · 기본값과 같은 예시 | 주석 유지 · 예시 삭제(계획서 Phase 2) |
  | C15 | 93-94 · 117-118 · 246 | 프로브 호출 수 · 받는 즉시 저장 · 원자료 폴더 | 호출 수·즉시 저장은 프로브 docstring 이미. 폴더는 삭제 — 세 프로브가 실행 끝에 「원자료 저장 위치」를 찍는다 |
  | C16 | 95-98 | 재실행이 폴더를 비움 · 첫 호출 실패 시 빈 폴더 · summary.json 없음 · 남길 값은 `설계.md` 로 | 함정은 `src/verify_lab/CLAUDE.md` 「데이터 저장 규칙」 「조사 프로브」 행 이미. 행동 지침(옮긴 뒤 다음 대상)은 `check_pykrx_etf.py` docstring 에 추가 |
  | C17 | 99-100 · 225 | pykrx 가 로그인 ID 를 찍는다 | pykrx 를 쓰는 스크립트 docstring 넷 이미 |
  | C18 | 101-102 | DNS 실패는 잠시 뒤 재실행 | **삭제** — 전역 「외부 요청이 실패하면」(보조 DNS)과 모순. 루트 `CLAUDE.md` 가 그쪽을 가리킨다 |
  | C19 | 106-107 · 121-122 | 3,000행 상한 · 종료일만 바꿔 이어붙임 · 한 실행 안에서 | `check_pykrx_splice.py` docstring 이미 |
  | C20 | 110-114 | splice 명령 둘 | 유지(기본 · 3분할) |
  | C21 | 119-120 | 판정 기준 · 덮지 못한 거래일이면 `--ends` 에 이른 종료일 | 판정 기준은 docstring 이미. 「덮지 못한 거래일」은 `--ends` help 에 추가 |
  | C22 | 127-143 | NAV · 기본 · 기본값 예시 · 261240/261250 `--adjusted` | NAV · 기본 · 261240 `--adjusted` 유지. 기본값 예시와 261250 은 삭제(변형) — 필요한 파일 목록은 등가성 `결과.md` §15 |
  | C23 | 145-149 | 기본 원본가 · 덮어씀 · 파일명 두 형식 · 근거 포인터 둘 | 원본가·다른 파일명·근거 포인터는 `collect_pykrx.py` docstring·help 이미. 파일명 형식은 `src/verify_lab/CLAUDE.md` 이미. 「덮어쓴다」는 `collect_pykrx.py` docstring 에 추가 |
  | C24 | 150-152 | 당일 제외(장중에도 당일 행) · 이상치면 예외 | `src/verify_lab/CLAUDE.md` 「원시 시세 저장 규칙」 최근 구간 행 · `collect_pykrx_history` docstring 이미 |
  | C25 | 154 · 179 · 202 · 298 · 350 · 378 · 404 · 425 | 절 제목의 「검증 #N 용」 · 「매매 —」 표지 | **삭제** — INDEX 의 한글 이름으로 통일(계획서 Phase 2). 국내 지수는 읽는 코드가 0건(감사 §1) |
  | C26 | 157-167 | 지수 명령 넷과 지수별 시작일 | 대표 하나 유지. 지수별 코드·시작일은 `collect_pykrx.py` 모듈 docstring 에 추가 |
  | C27 | 170-175 | 종가 계열 · 시세 아님 · 0 인 행 · 정수화 안 함 · 기본 티커가 다름 | `collect_pykrx_index` docstring · `--ticker` help 이미 |
  | C28 | 176-177 | 지수는 시작일을 직접 준다 · 기본값을 다른 지수에 쓰면 앞 구간을 잃는다 | `collect_pykrx.py` `--start` help 에 추가 |
  | C29 | 184 | 선물 두 상품 시작일 | `PRODUCT_FIRST_TRADING_DAY` · `--start` help 「상품별 최초 거래일」 이미 |
  | C30 | 191-193 | 호출 700회 · 코스피200 25분 · 두 상품 동시 실행 금지 | 호출 수는 `krx_futures_collector.py:149` 주석 이미. 「동시 금지」 · 「25분」은 `collect_krx_futures.py` docstring 에 추가 |
  | C31 | 194-200 | MDCSTAT12601/12701 · 상품당 파일 하나 · `load_futures_csv` · 넷 제외 | `krx_futures_collector.py` docstring · `collect_krx_futures.py` docstring · `loader.load_futures_csv` docstring 이미 |
  | C32 | 207-214 | ETN 명령 셋(기본 · 다른 종목 · 지표가치) | 유지. 지표가치 예시는 인자가 기본값과 같아 `--indicative-value` 만 |
  | C33 | 217-222 | pykrx 에 ETN 시세 함수 없음 · MDCSTAT06601 · 가격 기준 하나 · ISIN | `etn_collector.py` · `collect_etn.py` docstring 이미 |
  | C34 | 223-224 | 시작일은 `LIST_DD` 로 확인 · 251340 을 늦게 요청해 11거래일 누락 | 확인 지침은 `collect_etn.py` `--start` help 에 추가. 사건 서술은 삭제(이력 — 「늦게 주면 앞 구간이 조용히 빠진다」로 이유만 남김) |
  | C35 | 229-230 | ECOS 인증키 · 발급처 | COMMANDS 절 머리 한 줄 유지(스크립트 docstring · `ecos_credentials` 오류 메시지의 발급처 이미) |
  | C36 | 233-243 | ECOS 명령 넷 | 유지(프로브 · 수집 각각 기본 + 인자 예시) |
  | C37 | 247-248 | 코드는 프로브로 확인 · 확정값은 등가성 설계 §3.1 | `check_ecos.py` · `ecos_collector.py` docstring 이미 |
  | C38 | 249-251 | 환율 두 계열의 역할 · 매매기준율은 하루 늦고 스무딩 | `ecos_collector.py` 모듈 docstring 에 추가 — 지금 「매매기준율과 CD 91일물」로 틀림. `collect_ecos.py` docstring 같은 오류도 고침 |
  | C39 | 252-253 · 266 | `Date,Value` · 덮어씀 · 기간 안 자름 · DTB3 경로 | 스키마는 `src/verify_lab/CLAUDE.md` 「단일 값 시계열 계층 계약」 이미 · 기간은 `collect_ecos.py` 이미 · 경로는 `FRED_SERIES` 상수. 「덮어쓴다」는 `collect_ecos.py` · `collect_fred.py` docstring 에 추가 |
  | C40 | 254-255 | 키가 URL 에 · 로그 마스킹 · 직접 만든 URL 을 붙일 때 키를 지운다 | 앞 둘은 `ecos_collector.py` docstring 이미. 마지막은 그 docstring 에 추가 |
  | C41 | 259 · 267-269 | 인증키 불필요 · 휴일 행 · 이월 안 함 | `collect_fred.py` · `fred_collector.py` docstring 이미. 「인증키 불필요」는 COMMANDS 주석 유지 |
  | C42 | 275-282 | AI 직접 실행 · 스크립트 하나 · 한 폴더 · 나누면 지움 | 루트 「스크립트 실행 규칙」 · `run_reverse.py` · `run_midterm_cycle.py` docstring · `src/verify_lab/CLAUDE.md` 「매매법 이름 계약」 이미 |
  | C43 | 284-295 | 매매 산출물 공통 규격 · `summary.json` 「여섯 칸」(틀림) | `src/verify_lab/CLAUDE.md` 「매매 산출물 계약」 이미(최상위 다섯 칸으로 맞게) |
  | C44 | 301-308 | 역방향 명령 셋 | 유지(판단 3) · `--dataset` 줄에 「전체 산출물 폴더를 덮는다」 주석 |
  | C45 | 311-318 · 325-326 | 강건성 조합 전부 · 같은 실행에서 · 값은 `--help` · 순위 컷·시작연도는 인자 아님 | 역방향 `결과.md` §14.2 · `--dataset` help · `src/verify_lab/CLAUDE.md` 「좁혀 돌린 실행」 이미. 「순위 컷·시작연도도 상수」는 `run_reverse.py` docstring 에 추가 |
  | C46 | 319-324 | `역방향 전체` · 집계 3파일에만 · 산출물 넷 · 폴더를 비움 | 역방향 `결과.md` §3.2 · §4 · §14.2 · `src/verify_lab/CLAUDE.md` 「실행 계층 계약」 이미 |
  | C47 | 327-331 | `1차_판정.csv` 를 없앴다 · `거는 방향` 컬럼 | 앞은 **삭제**(이력 · 되살리는 절차는 `src/verify_lab/CLAUDE.md` 가 가리킨다). 뒤는 **삭제** — 틀림(그 컬럼 0건 · 감사 §1) |
  | C48 | 335-347 | 손절선·보유 한도·대상 목록 인자 아님 · −5% · D+2 · 격자 삭제 · 대상 2종 · 2005 통일 · 체결 산출물 | 「대상 목록은 인자 아님」은 **삭제** — 틀림(`--dataset` 이 체결 대상도 좁힌다 · 감사 §1). 나머지는 `run_reverse.py` docstring · 역방향 `규칙.md` §1 · §2.1 · §2.2 · §3.3 · 결정 ⑭ · §3.5 이미 |
  | C49 | 348 | 「순열 검정이 없어 수 초」 | **삭제** — 틀림(같은 실행이 순열 1,000회를 돈다 · 감사 §1) |
  | C50 | 353 · 381 · 407 | 조합 수 주석(선물 「3방식」 · 괴리 「축 3종」) | **삭제** — 틀림(방식 넷 · 축 넷). 조합 구성은 러너 docstring 이 갖는다 |
  | C51 | 360-364 · 388-392 · 414-415 | 인자가 하나뿐 · 격자 상수 · 선행 조건 · 이상치 축 | 세 스크립트 docstring · 선물 `결과.md` §15 · 괴리 `결과.md` §13 · `run_usdkrw_equivalence.py` 이미 |
  | C52 | 365-375 | 선물 산출물 목록 · 방식 넷 · 헤더 한글 | `studies/futures_leverage/runner.py` docstring 표(판단 1 — 빠진 `그대로 두기 오차` · breakeven 두 방식 · 「집행 불가」 보충) · 방식 넷은 `comparison.py` docstring 이미 · 헤더는 `run_futures_leverage._display` 이미. 선물 `결과.md` §15 에 포인터 |
  | C53 | 393-402 | 괴리 산출물 목록 · 수십 MB · 난수 없음 · 3년 칸 비중첩 | `studies/leverage_tracking/runner.py` docstring 표(판단 1 — 축 넷으로 고치고 「수십 MB」 보충) · 괴리 `결과.md` §12 · §13 이미. §13 에 포인터 |
  | C54 | 416-421 | 등가성 산출물 여섯 · `effective_cost` · `daily` | 등가성 `결과.md` §15 에 추가(판단 1 — 러너에 표 없음) |
  | C55 | 427-428 · 447-452 | 중간선거 산출물 아홉 · 분기·분할매수·진입위치는 무손절로만 · 격자 고정 | `run_midterm_cycle.py` docstring · `scripts/CLAUDE.md` 메타 표 이미. 중간선거 `결과.md` §15 에 한 줄. argparse description 에 분할매수·진입 위치 추가(백로그 §12.1 ⑧) |
  | C56 | 441-446 · 453-465 | 규칙 하나 · 휴장 앞당김 · 축 하나 · 표본 미달 · 변별력 없음 · 방향 위 하나 · 지수 판정 안 함 · 선행 조건 · 문서 포인터 | `run_midterm_cycle.py` docstring · `--ticker` help · 중간선거 `규칙.md` §1.1 · `설계.md` 결정 ⑨ · ⑫ · `결과.md` §13.3 · §14 · §15 이미 |
  | C57 | 466-467 | 1배만 잰다 · 레버리지 성적은 `규칙.md` 에만 | 중간선거 `규칙.md` 머리말 · 「산출물에 없고 이 문서에만 있다」 이미 |
  | C58 | 471-493 | 「코드가 없는 트랙」 절 | **삭제**(계획서 결정) — INDEX 「매매법·조사」 표(코드 없음 · 걸지 않음) · `docs/조사/만기_말일.md` 「재현 방법」 · `docs/조사/원달러_조달.md` 부록 |
- 2026-09-28 17:14: **Phase 1 완료.** 배정대로 옮기고 고쳤다 — 스크립트 docstring·help 12개(`collect_{yfinance,pykrx,krx_futures,etn,ecos,fred}.py` · `check_pykrx_{etf,splice}.py` · `run_{reverse,midterm_cycle,leverage_tracking,futures_leverage}.py`) · `ecos_collector.py` · 러너 docstring 둘(선물·괴리) · 선물 「세 방식」 넷 · 결과 문서 「재현 방법」 다섯(역방향 §14.1 반대 서술 정정 · 선물 「검증 #9」 절 포인터 → 문서 단위). 배정표에 없던 곁가지 둘도 같은 사실이라 함께 고쳤다: `collect_pykrx.py` 상수 주석 「검증 #10 의 최장 기간 축」(C25 와 같은 낡은 표지) · `collect_ecos.py` `DEFAULT_START` 주석 「두 시계열」(C38 과 같은 오류). `--start` help 는 처음에 「다른 지수에 쓰면 앞 구간을 잃는다」로 적었다가 코스닥150(2010~)은 잃지 않으므로 「더 일찍 시작하는 지수(코스피 종합·코스피200)」로 좁혔다(COMMANDS 원문도 같은 과장)
  - **새 자리 대조**: 스크래치 스크립트로 배정표의 「추가」 · 「이미」 자리 112건의 문구를 파일에서 셈 — **없음 0건**
  - **`--help`**: 스크립트 14개 전부 종료코드 0
- 2026-09-28 17:17: **Phase 2 완료.** `docs/COMMANDS.md` **493 → 125줄**. 머리말에 Q3 결정(설명은 대상 옆 — 근거 「코드와 두 벌이 되어 어긋난다」 · 2026-09-26)을 적었다. 절 제목은 INDEX 한글 이름(역방향 · 중간선거_사이클 · 원달러_ETF_등가성 · 레버리지_ETF_괴리 · 선물_대_레버리지_ETF, INDEX 표 순서)이고, 수집은 시장·소스 넷(yfinance · pykrx·KRX · ECOS · FRED)으로 묶었다. 다른 문서가 이름으로 가리키는 절(「품질 검증」 · 「데이터 수집」 · 「매매법·조사 실행」의 역방향 절 · 「ECOS」)은 유지 — 포인터 7곳이 그대로 산다. 「좁혀 돌리면 같은 폴더를 덮는다」는 명령마다 달지 않고 「매매법·조사 실행」 머리 한 줄로
  - **인자 대조**: 스크래치 스크립트가 COMMANDS 의 코드 펜스 안 명령 36개를 각 스크립트의 `parse_args()` 에 그대로 넣음 — **파싱 실패 0**. 값도 실재함을 따로 확인(`datasets_of(('SPY','GSPC'))` · 역방향 `qqq` · 괴리 `나스닥100` · 선물 `KOSDAQ150`)
  - **옛 절 이름**: `검증 실행|매매 규칙 실행|검증 #1 — 역방향|코드가 없는 트랙|… |「검증 #N` grep — COMMANDS 를 가리키는 줄 0(걸린 것은 무관한 일반 문구와 `SLIM_SERIES.md` 인계 메모뿐). 유일한 옛 포인터였던 선물 `결과.md` §15 「검증 #9」는 Phase 1 에서 문서 단위로 바꿨다
  - **테스트**: `tests/test_research_docs.py` · `tests/test_index.py` 94 passed
- 2026-09-28 17:53: **Phase 3.** `black .` 변경 없음(146 files unchanged, 리뷰 수정 뒤 한 번 더 돌려도 같음). `/code-review xhigh` 1회차 12건 — 버그 0 · 그 외 12. 리뷰 범위에 push 전 ⑦ 커밋 `8ee75ee` 가 함께 들어와 출처부터 갈랐다(⑧ 6 · ⑦ 1 · 기존 5). **사용자 결정**: ⑧ 이 만든 6건은 커밋 전에 고치고 나머지는 백로그(보고서 §12.10)
  - 고친 것: F3 `comparison.py` 의 남은 「세 방식」·「세 항」 · F6 중간선거 §15 파일 목록 포인터와 무손절 이유 · F8 선물 수집 시간(「25분쯤」 ↔ 수집기 「30분짜리」 → 「700회 · 수십 분」) · F9 개수 표현(「셋 다」·「세 시계열」·「네 방식」·「방식 넷」·「두 계열」 → 개수 없는 말) · F10 등가성 §15 의 261250 · 원본가 받는 법 · F12 splice · ECOS 프로브의 폴더 비움 안내. 대조 스크립트 문구를 새 문안으로 바꿔 **116건 없음 0** · 인자 파싱 36개 실패 0 · `--help` 14개 전부 0
  - 품질 검증(문서 갱신까지 끝난 뒤 최종): Ruff · PyRight 통과, **passed=1242 · failed=0 · skipped=0** · `git diff --stat storage/` 빈 출력(산출물 불변)
  - `REPORT_lightweight_inventory.md` §12.10 신설 · `SLIM_SERIES.md` 진행 표 ⑧ 「커밋 대기」 · ⑧ 인계 메모(끝 정리가 보일 남은 백로그 목록 — 결정 필요 · 고칠지 물을 것 · 기록만)
  - 🔴 **알린다 — 이 계획서가 스스로 만든 결함**: 위 F3 · F6 · F8 · F9 · F10 · F12 (전부 커밋 전에 고침)
