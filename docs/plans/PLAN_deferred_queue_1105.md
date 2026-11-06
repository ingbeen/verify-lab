# Implementation Plan: 미룬 지적 대기열 비우기 — 남은 4건 고치기

> 작성/운영 규칙(SoT): `/impl-plan` 스킬(`~/.claude/skills/impl-plan/SKILL.md`)을 반드시 참고하세요.  
> (이 템플릿을 수정하거나 새로운 양식의 계획서를 만들 때도 해당 스킬을 포인터로 두고 준수합니다.)

**상태**: ✅ Done

---

> 상태는 🟡 Draft / 🔄 In Progress / ✅ Done. Done 조건과 기록 규칙은 `/impl-plan` 「3) 스킵 및 완료 규칙」이며 `~/.claude/hooks/plan_lint.py` 가 저장 때 검사한다.

---

**작성일**: 2026-11-05 21:43
**마지막 업데이트**: 2026-11-06 21:59
**관련 범위**: report(폴더 이름 검사 테스트 · `create_run_directory` docstring) · 계약 테스트 docstring · 규칙 문서(루트 `CLAUDE.md` · `src/verify_lab/CLAUDE.md` · `.claude/rules/session-bootstrap.md` · `.claude/rules/trading.md` · `docs/INDEX.md`)
**관련 문서**: `docs/DEFERRED_FINDINGS.md` · `tests/CLAUDE.md` · `src/verify_lab/CLAUDE.md` · `.claude/rules/docs.md`

---

## 1) 목표(Goal)

`docs/DEFERRED_FINDINGS.md` 의 남은 4건을 `/impl-plan` 의 `review.md` 「미룬 지적 옮기기」 「처리」 순서로 재현한 뒤, 사용자 요청
「DEFERRED_FINDINGS.md 리스트 전부 해결해줘」(2026-11-05)대로 고치고 대기열에서 지운다. 항목은 아래 기호로 부른다.

| 기호 | 대기열 항목 | 무엇을 막나 |
| --- | --- | --- |
| D1 | 폴더 이름 검사 테스트가 `.match` 라 좁아진 패턴을 못 잡는다 | 패턴을 뒤쪽에서 좁혀도 테스트가 통과 → 실제 프로브 이름으로 실행이 `ValueError` 로 멈춤 |
| D2 | 문서 자리의 일반 표기 `docs/<등급>/<매매법>/…` 가 「조사는 한 장」을 반영하지 않는다 | 조사에 대입하면 없는 경로(`docs/조사/<이름>/규칙.md`)를 가리킴 |
| D3 | 「문서와 산출물 폴더가 같은 한글 이름」이 레지스트리 이름 일부에 맞지 않는다 | 문서가 없는 레지스트리 줄 4개에 대해 거짓 일반화 |
| D4 | 과거형 이력 서술과 지금 없는 이름이 주석 · 규칙 문서에 남아 있다 | 지금 없는 이름(`etn` · `HORIZON_LABELS` 등)을 찾게 만듦 |

- [x] 목표 1: D1 — 실제 이름 검사 테스트 둘이 운영 코드와 같은 `fullmatch` 로 재고, 패턴을 좁히는 변형 셋(A · B · C)에서 각각 실패한다
- [x] 목표 2: D2 · D3 · D4 의 자리와 같은 모양의 자리가 지금 사실을 말한다 (아래 Phase 2 · 3 의 grep 대조)
- [x] 목표 3: 4건이 대기열에서 지워지고 산출물(`storage/`)은 바뀌지 않는다

## 2) 비목표(Non-Goals)

- **`.claude/rules/docs.md` 「문서의 두 종류」 48 ~ 50행** (D2 의 자리 하나) — 추천은 고치지 않음. 항목 머리가 `{검증,매매}/<매매법>/규칙.md` 이지만
  같은 항목 마지막 문장이 「조사로 내린 매매법의 규칙도 그 조사 문서가 규칙 절로 갖는다」로 조사 자리를 이미 말해, 따라 해도 없는 경로가 나오지 않는다.
  **사용자가 고치기로 하면 승인 전에 Phase 2 에 줄을 더한다**
- 운영 코드(`report/writer.py` 의 패턴 · 검사 로직)의 동작 변경. writer.py 는 docstring 한 문장만 바꾼다
- 프로브 이름을 테스트에 손으로 옮겨 적는 관용(`test_accepts_every_real_track_name` 의 `probe_names`) — 지적 밖이고 이유가 그 테스트 주석에 있다
- 이 4건 밖의 과거형 서술 전수 정리 — D4 와 같은 docstring · 같은 문장 안에서 찾은 것만 함께 고친다
- 산출물 재실행 — 코드 동작이 바뀌지 않는다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

재현 결과(2026-11-05 — 저장소를 `.venv` · `.git` 없이 세션 스크래치에 떠 `PYTHONPATH` 를 앞세워 실행, 바이트코드 끔 · 되돌린 뒤 `cmp` 동일 · 저장소 무변경):

- **D1 — 재현됨.** 사본 기준선 1,161 passed.
  - 변형 A(지적 원문) `TRACK_NAME_PATTERN = r"[a-z][a-z_]{0,16}"`(17자 상한): 1 failed — 그런데 실패한 것은 `test_rejects_unregistered_track_name` 이다.
    그 테스트가 넘기는 `"unregistered_track"` 이 **우연히 18자**라 모양 검사에서 먼저 거부돼 메시지가 달라졌을 뿐이고, `.match` 테스트는 통과했다
    (`pykrx_splice_probe` — `.match` 참 · `fullmatch` 거짓). 우연에 기대지 않는 변형이 아래 C 다
  - 변형 C `TRACK_NAME_PATTERN = r"[a-z]+(?:_[a-z]+)?"`(밑줄 하나까지 — 프로브 이름 둘만 거부): **1,161 passed** — 재현
  - 변형 B `TRACK_LABEL_PATTERN = r"[A-Za-z가-힣][0-9A-Za-z가-힣_]{0,12}"`(13자 상한 — `pykrx_이어붙이기_실측` 14자만 거부): **1,161 passed** —
    **같은 모양이 400행 `test_accepts_every_real_label` 의 `VALID_TRACK_LABEL.match` 에도 있다**(지적 밖에서 찾은 자리)
  - 두 줄을 `.fullmatch` 로 바꾼 사본: 변형 없음 1,161 passed · A 2 failed(`test_accepts_every_real_track_name` 포함) · B 1 failed(`test_accepts_every_real_label`) · C 1 failed(`test_accepts_every_real_track_name`)
  - 무게: 그 검사가 막는 결함이 「정상 이름으로 실행이 멈춘다」(죽는다)라 검사 약화는 「비켜 간다」 — 계기는 패턴을 좁히는 앞으로의 변경(`review.md` 「고칠지는 «닿는가»로 가른다」)
- **D2 — 사실 확인.** 지적의 자리 여섯이 지금도 있다(줄은 그대로): 루트 `CLAUDE.md:23` · `.claude/rules/session-bootstrap.md:18` · `.claude/rules/trading.md:200` ·
  `.claude/rules/docs.md:48 ~ 50` · `src/verify_lab/report/writer.py:66` · `tests/test_report_writer.py:56`.
  `grep 'docs/<등급>/<…>/'` 로 같은 모양을 더 찾으면 괄호 한정이 없는 자리가 하나 더 있다 — `.claude/rules/trading.md:170`(「확정된 설계 결정」 형식).
  나머지 열 자리(`research.md:89 · 90` · `CLAUDE.md:212` · `docs.md:109 · 111` · `session-bootstrap.md:17` · `tracks.py:60` · `src/verify_lab/CLAUDE.md:289 · 300 · 301` · `INDEX.md:38`)는
  이미 「(조사는 …)」 괄호를 붙인다 — **이 괄호가 이 저장소의 관용이다.** `session-bootstrap.md:31 ~ 33` 은 그 절 머리말이 조사 한 장을 이미 말한다.
  `tests/test_research_docs.py:516` 은 테스트 입력 문자열이라 대상이 아니다
- **D3 — 사실 확인.** `tracks.py` 13줄 중 같은 이름의 문서가 있는 줄 9 · 없는 줄 4(`원달러_그리드` · `ECOS_실측` · `pykrx_ETF_실측` · `pykrx_이어붙이기_실측`).
  지적의 자리는 `src/verify_lab/CLAUDE.md:301` · 루트 `CLAUDE.md:274`(273 에서 밀림) · `writer.py:66` · `test_report_writer.py:56`.
  같은 일반화가 `docs/INDEX.md:38`(「한글 이름이 곧 `docs/<등급>/<이름>/` … 의 이름입니다」)에도 있다 — 바로 아래 표가 예외를 보이지만 문장 자체는 한정이 없다(지적 밖에서 찾은 자리).
  `tracks.py:59 ~ 61` 의 `label` docstring 은 「그 줄의 문서가 따로 있으면」으로 이미 한정한다 — **이것을 맞출 기준으로 쓴다**
- **D4 — 사실 확인.** `tests/test_layer_contracts.py:1673 ~ 1675`(`etn` · `krx_futures` — `src` · `scripts` 에 그 이름 0건) ·
  `:396`(`HORIZON_LABELS` · `MODEL_LABELS` · `EXTREME_DIRECTION_LABELS` — `src` · `tests` 에서 이 docstring 말고 0건) ·
  `src/verify_lab/CLAUDE.md:132`(「달력 함수는 지웠고」) · `:587`(「역방향과 함께 지웠습니다」). 같은 docstring 안 `:392 ~ 393` 의
  「처음에는 `*_LABELS` 라는 이름으로 찾았는데」도 같은 모양이다(지적 밖에서 찾은 자리)
- 글자 규칙이 막거나 되돌릴 수 없는 결과에 물리는 설계: **해당 없음**

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- `.claude/plan-config.json` — 이 저장소의 검증 명령·자동 포맷·근거 승격 목적지 (**값의 SoT**)
- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절 (값이 아니라 **판단 근거**)
- `src/verify_lab/CLAUDE.md` · `tests/CLAUDE.md` · 전역 `~/.claude/rules/python.md` · `~/.claude/rules/python-tests.md`
- `.claude/rules/docs.md` · `.claude/rules/trading.md` · `.claude/rules/research.md` · `.claude/rules/session-bootstrap.md`
- `/impl-plan` 의 `review.md` — 「지적을 고칠 때」(변형 확인) · 「미룬 지적 옮기기」

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] D1 ~ D4 가 각 Phase 의 Validation 을 통과했다
- [x] 회귀/신규 테스트 추가 — 새 테스트 없음. 기존 이름 검사 테스트 넷(`test_report_writer.py` 둘 · `test_tracks.py` 둘)의 판정식을 보강했고 변형 여섯(A · B · C · D · F · G)으로 확인했다
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — 루트 `CLAUDE.md` · `src/verify_lab/CLAUDE.md` · `.claude/rules/session-bootstrap.md` · `.claude/rules/trading.md` · `docs/INDEX.md` · `docs/DEFERRED_FINDINGS.md`. `docs/COMMANDS.md` 변경 없음
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다 (「왜 `fullmatch` 인가」 · 「왜 레지스트리 전부인가」는 테스트 docstring 이 갖는다)
- [x] 미룬 지적 옮김 — 해당 없음. 리뷰 11건은 사용자 지시대로 전부 고쳤고(진행 로그 21:58) 옮길 지적이 없다. 이 계획서가 고친 대기열 4건은 지웠다
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `tests/test_report_writer.py` — D1(287 · 400행 `.match` → `.fullmatch` · 두 테스트 docstring 에 「왜 `fullmatch`」 한 문장) · D2 · D3(56행 docstring)
- `src/verify_lab/report/writer.py` — D2 · D3(`create_run_directory` docstring 66행 한 문장만)
- `tests/test_layer_contracts.py` — D4(`_rename_dicts` docstring 392 ~ 396 · `test_최근_구간_제외를_인라인으로_다시_만들지_않는다` docstring 1673 ~ 1675)
- 루트 `CLAUDE.md` — D2(23행) · D3(274행)
- `src/verify_lab/CLAUDE.md` — D3(301행) · D4(132 · 587행)
- `.claude/rules/session-bootstrap.md` — D2(18행)
- `.claude/rules/trading.md` — D2(170 · 200행)
- `docs/INDEX.md` — D3(38행)
- `docs/DEFERRED_FINDINGS.md` — 4건 삭제
- `docs/COMMANDS.md`: 변경 없음 (실행 명령 · CLI 옵션 그대로)

### 데이터/결과 영향

- **산출물 변경 없음** — 운영 코드 동작이 바뀌지 않아 재실행하지 않는다. `git status --porcelain storage/` 빈 출력으로 확인
- 출력 스키마 변경 없음

## 6) 단계별 계획(Phases)

### Phase 1 — 폴더 이름 검사 테스트 (D1 · 그린 유지)

**작업 내용**:

- [x] `test_accepts_every_real_track_name` 의 `writer.VALID_TRACK_NAME.match(name)` → `.fullmatch(name)`
- [x] `test_accepts_every_real_label` 의 `writer.VALID_TRACK_LABEL.match(track.label)` → `.fullmatch(track.label)`
- [x] 두 docstring 에 한 문장 — 운영 코드(`create_run_directory`)와 같은 `fullmatch` 로 잰다 · `.match` 는 앞부분만 맞아도 통과해 패턴을 뒤쪽에서 좁히는 변경을 못 잡는다

**Validation** (변형은 `src/verify_lab/report/writer.py` 에 넣고, 넣기 전 사본을 떠 되돌린 뒤 `cmp` · `PYTHONDONTWRITEBYTECODE=1` · `passed/failed/error` 를 모두 센다):

- [x] 변형 A — `TRACK_NAME_PATTERN` 17자 상한: `test_accepts_every_real_track_name` 실패
- [x] 변형 B — `TRACK_LABEL_PATTERN` 13자 상한: `test_accepts_every_real_label` 실패
- [x] 변형 C — `TRACK_NAME_PATTERN` 밑줄 하나까지: `test_accepts_every_real_track_name` 실패
- [x] 되돌린 뒤 `tests/test_report_writer.py` 통과 · `cmp` 동일

---

### Phase 2 — 문서 자리 표기 (D2 · D3)

**작업 내용** (괄호 한정은 이미 열 자리가 쓰는 관용 「(조사는 …)」을 그대로 쓰고, 문서 유무는 `tracks.py` 의 `label` docstring 표현 「그 줄의 문서가 따로 있으면」에 맞춘다):

- [x] 루트 `CLAUDE.md:23` — `docs/<등급>/<매매법>/규칙.md` 뒤에 「(조사는 그 한 장의 규칙 절)」
- [x] `.claude/rules/session-bootstrap.md:18` — 같은 행 17 의 형식대로 「(조사는 한 장 `docs/조사/<이름>.md` 의 규칙 절)」
- [x] `.claude/rules/trading.md:170` — 「(조사는 그 한 장의 같은 절)」 · `:200` — 「(조사는 그 한 장의 결과 장)」
- [x] `src/verify_lab/report/writer.py:66` · `tests/test_report_writer.py:56` docstring — 「문서가 따로 있으면 `docs/<등급>/<이름>/`(조사는 한 장 `docs/조사/<이름>.md`)과」로
- [x] 루트 `CLAUDE.md:274` · `src/verify_lab/CLAUDE.md:301` · `docs/INDEX.md:38` — 산출물 폴더는 늘 그 이름이고 문서는 따로 있는 줄만 그 이름이라고 한정하고, 어느 줄인지는 `docs/INDEX.md` 「매매법·조사」 표를 가리킨다

**Validation**:

- [x] `grep -rn 'docs/<등급>/<[^>]*>/'` 결과의 모든 자리가 같은 줄 · 같은 절 머리말에 조사 한정을 갖는다(테스트 입력 문자열 `test_research_docs.py:516` 제외) — 자리 수를 진행 로그에 적는다
- [x] `tests/test_index.py` · `tests/test_research_docs.py` · `tests/test_report_writer.py` 통과

---

### Phase 3 — 과거형 · 없는 이름 (D4)

**작업 내용**:

- [x] `tests/test_layer_contracts.py` `test_최근_구간_제외를_인라인으로_다시_만들지_않는다` docstring — `etn` · `krx_futures` 이력을 걷고 「수집기마다 복사본이나 인라인 로직을 두면 한 곳만 고쳐도 예외가 나지 않는다 — 저장 범위만 하루 달라진 파일이 만들어진다」를 현재형 근거로 남긴다
- [x] 같은 파일 `_rename_dicts` docstring — 「처음에는 … 찾았는데」를 「이름으로 찾으면 …」 현재형으로, 값-사전의 예 셋을 「키가 정수 · 실수 · 열거형인 사전」으로
- [x] `src/verify_lab/CLAUDE.md:132` — 「쓰는 매매법이 없는 달력 함수는 두지 않고」 · `:587` — 「조건부 기준선(…)은 쓰는 매매법이 없어 두지 않습니다」

**Validation**:

- [x] `grep -rnE 'HORIZON_LABELS|MODEL_LABELS|EXTREME_DIRECTION_LABELS|etn`·`krx_futures|처음에는 `\*_LABELS`|함수는 지웠고|함께 지웠습니다' src tests` 0건
- [x] `tests/test_layer_contracts.py` 통과

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

> 🔴 **체크박스와 상태를 먼저 확정하고, `/commit` 은 맨 마지막에** — 이유는 `/impl-plan` 「5) Commit Messages」.

- [x] `docs/DEFERRED_FINDINGS.md` 에서 4건을 지운다
- [x] 자동 포맷 적용 (`poetry run black .`)
- [x] 변경 기능 및 전체 플로우 최종 검증 — `git status --porcelain storage/` 빈 출력
- [x] Validation 절에 `/code-review` 와 품질 검증 **실행 결과**를 적는다
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정
- [x] 🔴 **마지막에 `/commit` 을 실행하고 그 후보를 «이 계획서» 의 `#### Commit Messages` 절에 옮긴다** —
      대화에만 내면 그 절이 빈 채로 남는다. **커밋은 사용자가 한다 — 후보만 낸다**

**Validation**:

> 순서는 `/code-review` → 품질 검증이다. 고칠 것 · 회차 상한 · 수정분 검증은 `/impl-plan` 의 `review.md` 가 정한다.

- [x] `/code-review xhigh` **1회차** (발견 11건 — 버그 2 [무거움 2 · 가벼움 0] · 그 외 9 · 조치: 11건 전부 수정 + 같은 모양 3곳 — 사용자 지시로 다시 리뷰하지 않음)
- [x] 수정분 검증 — 해당 없음 (사용자 지시 2026-11-06 「반복되게 수정하고 리뷰하고 … 하지말고」 — 대신 변형 여섯 · grep 대조 · 품질 검증으로 확인. 진행 로그 21:58)
- [x] `poetry run python validate_project.py` (passed=1161, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다** — 추측으로 적은 줄은 그대로 나간다.

1. 검증 / 미룬 지적 대기열 4건과 리뷰 지적 11건 처리
2. 검증 / 폴더 이름 검사 테스트의 운영 패턴 fullmatch 전환과 레지스트리 전수 검사
3. 검증 / 미룬 지적 대기열 비우기 — 이름 검사 테스트 보강 · 조사 한 장 표기 정리 · 과거형 서술 현재형 전환
4. 검증 / 좁아진 이름 패턴과 끝 개행 slug 를 놓치던 테스트 보강과 규칙 문서의 조사 자리 표기 정정
5. 검증 / 문서 · docstring 의 지금 없는 이름과 거짓 일반화 정리

## 7) 리스크(Risks)

- **변형을 저장소 파일에 넣는 동안 되돌림이 빠진다** — 완화: 변형마다 사본을 뜨고 되돌린 뒤 `cmp`, 바이트코드를 끄고 돈다
- **규칙 문서 표현을 바꾸다 다른 문장의 뜻을 바꾼다** — 완화: 괄호 한정만 덧붙이고 문장 구조는 그대로 둔다. 바꾼 줄은 `git diff` 로 줄 단위 대조
- **D3 를 고친 문장이 `tracks.py` docstring 과 다른 말로 같은 것을 말한다** — 완화: 그 docstring 의 표현(「따로 있으면」 · `docs/INDEX.md` 「매매법·조사」 표)을 그대로 쓴다

## 8) 메모(Notes)

- 재현 원자료(스크래치 사본 · 변형 로그)는 세션 스크래치에 있고 저장소에 남기지 않는다. 판정 근거 수치는 위 Context 가 갖는다
- D2 · D3 · D4 는 대기열에 「그 외 — 사용자가 미루기로 함」으로 들어온 항목이다. 이번 요청이 「전부 해결」이라 고친다

### 진행 로그 (KST)

- 2026-11-05 21:43: 대기열 4건 재현 · 사실 확인 뒤 계획서 작성 (Draft). 대기열 4건 출처에 「고치는 중: PLAN_deferred_queue_1105」를 붙였다
- 2026-11-06 08:59: 사용자 승인 「진행」 — 추천안대로: `docs.md:48 ~ 50` 은 고치지 않는다(비목표 그대로) · 지적 밖에서 찾은 같은 모양 넷(`test_report_writer.py:400` · `trading.md:170` · `INDEX.md:38` · `test_layer_contracts.py:392`)을 함께 고친다
- 2026-11-06 09:01: Phase 1 — 두 줄을 `.fullmatch` 로 · docstring 에 이유 한 문장씩. 변형(저장소 `writer.py` 에 넣고 사본으로 되돌림 · 바이트코드 끔 · 전체 테스트):
  A 17자 상한 → 2 failed · 1,159 passed(`test_accepts_every_real_track_name` 「실제 매매법 이름이 폴더 이름 검사를 통과하지 못합니다: ['pykrx_splice_probe']」 + 전부터 우연히 잡던 `test_rejects_unregistered_track_name`) ·
  B 13자 상한 → 1 failed(`test_accepts_every_real_label` 「… ['pykrx_이어붙이기_실측']」) · C 밑줄 하나까지 → 1 failed(`test_accepts_every_real_track_name` 「… ['pykrx_etf_probe', 'pykrx_splice_probe']」) ·
  error 0. 되돌릴 때마다 `cmp` 동일 · `git status` 에 `writer.py` 없음 · `tests/test_report_writer.py` 40 passed
- 2026-11-06 09:03: Phase 2 — 괄호 한정 다섯 자리(D2) · 문서 유무 한정 다섯 자리(D3 — `writer.py` · `test_report_writer.py` docstring 은 D2 와 한 문장).
  `grep 'docs/<등급>/<…>/'` 22자리 중 한정 있음 18 · 없음 4 — `session-bootstrap.md:31 ~ 33`(§3 머리말이 「조사 등급은 설계 · 결과가 한 장」을 말한다) · `test_research_docs.py:516`(합성 테스트 입력).
  `src/verify_lab/CLAUDE.md:301` 은 `docs/INDEX.md` 를 가리키며 같은 파일의 기존 링크 형식(`../../docs/INDEX.md`)을 따랐다. index · research_docs · report_writer 149 passed
- 2026-11-06 09:03: Phase 3 — `test_layer_contracts.py` docstring 둘(수집기 복사본 이력 → 현재형 근거 · `_rename_dicts` 의 「처음에는」과 없는 이름 셋 → 「키가 정수·실수·열거형인 사전」) ·
  `src/verify_lab/CLAUDE.md` 두 문장(「지웠고」 · 「함께 지웠습니다」 → 「두지 않」). 옛 서술 grep 0건 · 계약 테스트 40 passed
- 2026-11-06 09:03 이후(시각 미확인 — 다음 확인 시각이 21:42): 마지막 Phase — 대기열 4건을 지웠다(머리말만 남음). `poetry run black .` 110 files left unchanged. `/code-review xhigh` 1회차는 사용량 한도로 실행되지 않았다(「You've hit your 5-hour limit」)
- 2026-11-06 21:42: 사용자 지시 「코드 리뷰시 반복되게 수정하고 리뷰하고 이런식으로 진행하지말고 전부 해결하는 것을 목표로 하자」 — 이 계획서는 리뷰를 **1회차만** 돌리고,
  지적 중 지금 코드에서 사실로 확인된 것은 무게 · 「닿는가」와 관계없이 그 자리에서 한꺼번에 고친다(대기열로 다시 옮기지 않는다). 고친 뒤 다시 리뷰하지 않으며 수정분 검증 서브에이전트도 돌리지 않는다 —
  대신 고친 자리마다 변형 · grep · 테스트로 직접 확인한다. 사실이 아닌 지적은 재현 결과와 함께 진행 로그에 남기고 고치지 않는다
- 2026-11-06 21:58: `/code-review xhigh` 1회차 11건 — 전부 지금 코드에서 확인했고(F5 의 `tracks.py:14` 는 「이 값」이 등급이라 거짓은 아니고 「문서 폴더」가 모호할 뿐 — 표현만 좁혔다) 전부 고쳤다. 범위가 `tests/test_tracks.py` · `src/verify_lab/tracks.py` 로 넓어졌다(사용자 지시 「전부 해결」).
  - F1(무거움 · 비켜 간다) `test_tracks.py` 의 slug · 한글 이름 모양 테스트가 운영 패턴의 `^…$` 복사본을 `.match` 로 쟀다 → 복사본을 지우고 `report.writer` 의 `VALID_TRACK_NAME` · `VALID_TRACK_LABEL` 을 `fullmatch` 로
  - F2(무거움 · 비켜 간다) `test_accepts_every_real_track_name` 이 손으로 고른 4개만 봤다(레지스트리 13개 중 9개 미검사) → 레지스트리 slug 전부
  - 변형(수정 전 스크래치 사본): D `TRACK_NAME_PATTERN = r"(?!ecos)[a-z][a-z_]*"` → 1,161 passed · F 레지스트리 `Track("usdkrw_grid\n", …)` → 1,161 passed — 둘 다 구멍이었다.
    변형(저장소 · 사본으로 되돌려 `cmp` 동일 · 바이트코드 끔): A 4 failed(report_writer 둘 · tracks `[usdkrw_equivalence]` · `[pykrx_splice_probe]`) · B 2 failed · C 3 failed · D 2 failed(`[ecos_probe]` 포함) · F 2 failed(`[usdkrw_grid\n]` 포함) · G 한글 이름 끝 개행 2 failed · error 0
  - F3 대기열을 Done 전에 지웠다(09:03 이후 ~ 21:42 동안 대기열이 비어 있었다) → 4건을 「고치는 중」과 함께 되살렸고(커밋본과 꼬리 넷만 다름) 품질 검증 직전에 다시 지웠다
  - F4 `test_layer_contracts.py` 의 과거형 · 지금 없는 이름 7곳(모듈 docstring 표 둘 · 판정가능 식 · 방향 표기 · 어긋남 레이블 · 같은 접두사 · 옛 경로 · CLI 파일 이름) → 현재형 근거. 같은 모양 3곳(872 · 1003 · 1190 — 「세 국내 수집기」 포함)도 함께
  - F5 `tracks.py:14` 「문서 폴더」 → 「산출물과 문서가 놓이는 상위 폴더(`storage/results/<등급>/` · `docs/<등급>/`)」 · `test_tracks.py` 한글 이름 유일성 목적문 → 산출물 폴더 기준
  - F6 `session-bootstrap.md:17 · 18` 조사 자리를 `docs/조사/<이름>.md` 틀 대신 `docs/INDEX.md` 「매매법·조사」 표로(원달러_그리드처럼 다른 문서의 절인 줄)
  - F7 `INDEX.md:39` 「문서가 없는 줄은 `tracks.py` 가 말합니다」 · F8 `writer.py:37` · `test_report_writer.py:246` 의 「`docs/INDEX.md` §3 이름표」 → 「매매법·조사」 표 · F9 `src/verify_lab/CLAUDE.md:301` 「왜」 칸도 「문서가 따로 있는 줄은」
  - F10 `trading.md:200` 의 「(조사는 그 한 장의 결과 장)」을 걷고 「조사는 결과 장이 같은 한 장에 있어 그 장을 가리키면 되고 복사하지 않아도 됩니다」 — 한 장 안의 사본을 만들게 하던 지시
  - F11 `_rename_dicts` docstring 이 구현(`isinstance(key, ast.Name)`)보다 넓게 말했다 → 리터럴 · `열거형.멤버` 키는 빠지고 이름 붙은 상수 키는 걸린다고 고쳤다(실행 확인: `LIT` · `ENUM` 빠짐, `NAMED` · `RENAME` 걸림)
  - 같은 모양 잔존 grep: INDEX 절 번호 참조 0 · 옛 이름 0 · 「문서 폴더」는 `test_index.py` 의 `docs/조사/` 자체를 가리키는 둘뿐. `black` 110 files left unchanged · `validate_project.py` Ruff · PyRight 통과 · passed=1161 failed=0 skipped=0 · `storage/` 0줄
- 2026-11-06 21:59: `/commit` 후보 5개를 옮기고 상태를 Done 으로 확정

---
