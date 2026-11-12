# Implementation Plan: 로더가 중복 날짜에서 멈추게 — quant · quant-data 와 정책 통일

> 작성/운영 규칙(SoT): `/impl-plan` 스킬(`~/.claude/skills/impl-plan/SKILL.md`)을 반드시 참고하세요.  
> (이 템플릿을 수정하거나 새로운 양식의 계획서를 만들 때도 해당 스킬을 포인터로 두고 준수합니다.)

**상태**: 🟡 Draft

---

> 상태는 🟡 Draft / 🔄 In Progress / ✅ Done. Done 조건과 기록 규칙은 `/impl-plan` 「3) 스킵 및 완료 규칙」이며 `~/.claude/hooks/plan_lint.py` 가 저장 때 검사한다.

---

**작성일**: 2026-11-13 08:12
**마지막 업데이트**: 2026-11-13 08:12
**관련 범위**: data(로더), tests, 문서(`src/verify_lab/CLAUDE.md` · 선물 조사 문서 §17.2)
**관련 문서**: `src/verify_lab/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/docs.md`, `.claude/rules/research.md`

---

## 1) 목표(Goal)

- [ ] 목표 1: `load_market_csv` · `load_series_csv` 가 중복 날짜를 만나면 행을 지우지 않고 `ValueError` 로 멈춘다 — quant `load_stock_data` · quant-data `prices.py` · `series.py` 와 같은 정책(「어느 행이 맞는지 알 수 없으므로 고르지 않는다」)
- [ ] 목표 2: 중복 판정은 헬퍼 하나이고 두 로더가 함께 부른다(절대 원칙 5 — 판정식 단일화)
- [ ] 목표 3: 이 동작을 적은 계약 문장 · docstring · 선물 조사 문서 §17.2 가 새 동작을 말한다
- [ ] 목표 4: 두 매매법을 인자 없이 다시 돌려도 산출물이 바이트 단위로 같다

## 2) 비목표(Non-Goals)

- **로더의 다른 판정을 quant 와 맞추지 않는다** — 거래량 검사(quant 는 합성 시세의 거래량이 0 이라 보지 않음) · 급등락 임계 · 날짜 dtype 은 데이터가 달라 일부러 다르다(2026-11-13 보고)
- **구조 검사 `validate_market_frame` 에 중복 검사를 넣지 않는다** — 메모리에서 만든 프레임에 13곳이 쓰는 검사라 범위가 넓어진다. 측정 계층의 중복 검사(`measure/calendar_entry.validate_trading_days` · `studies/halving_cycle/indicator_signals`)도 그대로 둔다
- **메시지를 quant 와 글자까지 맞추지 않는다** — verify-lab 로더의 기존 모양(「… 발견 - …, 예시 날짜: …」)을 따른다
- 지운 선물 전용 로더를 되살리지 않는다
- 품질 기록의 「중복 날짜 0건」 두 줄(`docs/조사/원달러_ETF_등가성.md` · `docs/조사/역방향.md`)은 그때의 측정이라 고치지 않는다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

- 사용자 결정(2026-11-13 「추천대로 진행」) — 직전 검토에서 quant 와 verify-lab 의 quant-data 사용 방식을 맞추며 남긴 항목 하나다. 세 저장소 중 verify-lab 만 중복 날짜에서 첫 행을 고른다
  - verify-lab [loader.py:185](../../src/verify_lab/data/loader.py#L185) · [loader.py:276](../../src/verify_lab/data/loader.py#L276) — 경고 뒤 `drop_duplicates(keep="first")`
  - quant `src/qbt/utils/data_loader.py` `validate_price_series` — 중복 날짜면 `ValueError`(「어느 행이 맞는지 알 수 없으므로 고르지 않는다」)
  - quant-data `src/quant_data/prices.py:79` · `src/quant_data/series.py:47` — 저장 전에 같은 검사로 멈춘다(「지우거나 메우지 않는다」)
- 첫 행을 고르면 두 행의 값이 다를 때 **어느 값으로 쟀는지가 경고 한 줄로만 남는다.** 사본은 quant-data 가 이미 걸렀으므로, 중복이 보이면 사본을 손으로 고쳤거나 다른 형식의 파일이 들어온 것이다 — 멈추는 쪽이 「예외는 숨기지 않는다」(`src/verify_lab/CLAUDE.md`)와 맞는다

### 착수 전 확인한 사실 (2026-11-12 ~ 13)

- **지금 사본 9개(`storage/market/`)의 중복 날짜는 0건이다** — 파일마다 날짜 열을 셌다. 그래서 결과는 바뀌지 않을 것으로 본다(목표 4 가 확인한다)
- **호출처** — 운영 코드(src · scripts)에서 `load_market_csv` 10 · `load_series_csv` 4, 둘을 거치는 `load_close_series` 3 · `load_crypto_market_csv` 5. 모두 두 함수의 같은 네 줄을 지난다. 테스트는 `load_market_csv` 28 · `load_series_csv` 12
- **이 동작을 고정한 테스트는 둘이다** — [test_data_loader.py:126](../../tests/test_data_loader.py#L126) `test_duplicate_dates_are_removed`(같은 값 두 행 → 한 행) · [test_data_loader.py:550](../../tests/test_data_loader.py#L550) `test_series_duplicate_dates_are_removed`(다른 값 두 행 → 첫 값). `tests/` 에서 「중복 · duplicat」 으로 찾은 것 중 로더 중복 처리를 다루는 것은 이 둘뿐이다
- **`validate_market_data` · `validate_series_data` 는 로더만 부른다**(각 1곳). 구조 검사 `validate_market_frame` 은 studies · data 에서 13곳
- **이 동작을 적은 문서** — [src/verify_lab/CLAUDE.md:194](../../src/verify_lab/CLAUDE.md#L194) 「데이터 로딩은 중앙 집중」(「… → 중복 제거」) · `loader.py` 모듈 docstring 23 ~ 25행(선물에 쓰면 안 되는 이유 「날짜 기준 중복 제거가 첫 계약만 남기고 나머지를 예외 없이 지운다」) · 두 로더 docstring 의 처리 순서 · `docs/조사/선물_대_레버리지_ETF.md` §17.2 「기존 로더를 쓰면 두 곳이 조용히 틀린다」 표 첫 행. §17.2 제목을 가리키는 곳은 없다

### 글자 규칙이 막거나 되돌릴 수 없는 결과에 물리는가

해당 없음 — 판정은 날짜 값이 같은가 하나이고 글자 규칙(정규식 · 사전)이 아니다. 막는 대상(데이터 파일)에 미리 돌려 본 결과는 위 「사본 9개 0건」이고, 멈춤은 실행을 끝낼 뿐 파일을 바꾸지 않아 되돌릴 것이 없다.

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- `.claude/plan-config.json` — 이 저장소의 검증 명령·자동 포맷·근거 승격 목적지 (**값의 SoT**)
- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절 (값이 아니라 **판단 근거**)
- `docs/MEMORY.md`
- `src/verify_lab/CLAUDE.md`
- `tests/CLAUDE.md` · 전역 `~/.claude/rules/python-tests.md`
- 전역 `~/.claude/rules/python.md`
- `.claude/rules/docs.md` · `.claude/rules/research.md`
- `/impl-plan` 의 `review.md`

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [ ] 중복 날짜가 있는 시세 · 계열 파일이 `ValueError` 로 멈추고, 메시지에 중복 날짜 · 파일 · 할 일이 있다
- [ ] 두 로더가 헬퍼 하나를 부른다
- [ ] 회귀/신규 테스트 — 기존 두 테스트(시세는 같은 값 두 행 — 경계 · 계열은 다른 값 두 행)를 멈춤으로 바꾸고 시세에 다른 값 두 행을 더했으며, 로더를 옛 동작으로 되돌리는 변형에서 실패함을 확인했다
- [ ] 두 매매법을 인자 없이 다시 돌려 `git diff --stat storage/results/` 가 비어 있다
- [ ] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [ ] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [ ] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [ ] 필요한 문서 업데이트 — `src/verify_lab/CLAUDE.md`(변경 있음) · `docs/조사/선물_대_레버리지_ETF.md`(변경 있음) · `docs/COMMANDS.md`(변경 없음)
- [ ] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다 (계층 계약은 `src/verify_lab/CLAUDE.md` 「받은 사본 규칙」 이상치 판정 행에 근거 — quant · quant-data 와 같은 정책 · 고르지 않는 이유 — 를 함께 적는다)
- [ ] 미룬 지적 옮김 — 고치지 않은 리뷰 지적을 거르는 기준으로 걸러 `deferred_findings` 파일로 옮겼다. 계획서 없이 읽히게 썼다.
      거른 지적은 진행 로그에 기준 번호와 함께 남기고 Done 보고에 표로 냈다
      이 계획서가 그 파일의 항목을 고쳤다면 그 항목을 지웠다
      (둘 다 없으면 「해당 없음」. `/impl-plan` 의 `review.md` 「미룬 지적 옮기기」 참고)
- [ ] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `src/verify_lab/data/loader.py`
  - 헬퍼 `_require_unique_dates(df, path)` 하나 — 중복 날짜가 있으면 `ValueError`. 메시지: `중복 날짜 발견 - 날짜 수: N, 예시 날짜: [처음 다섯] (파일: …) — 어느 행이 맞는지 알 수 없어 고르지 않습니다. 사본이면 quant-data 에서 다시 내보내세요(docs/COMMANDS.md 「데이터 받기」)`
  - 두 로더의 4단계(중복 제거 네 줄)를 그 호출로 바꾸고, 처리 순서 · `Raises` docstring 의 「중복 제거」를 「중복 날짜 검사」로
  - 모듈 docstring 의 선물 문단 — 「날짜가 겹쳐 멈춘다(계약을 가를 수 없다)」로
- `tests/test_data_loader.py` — 두 테스트를 `test_duplicate_dates_raise`(같은 값 두 행 — 경계) · `test_series_duplicate_dates_raise`(다른 값 두 행)로(`pytest.raises(ValueError, match="중복 날짜")` · 메시지에 그 날짜가 든다), 시세의 다른 값 두 행 테스트 하나
- `src/verify_lab/CLAUDE.md` — 「데이터 로딩은 중앙 집중」의 처리 순서 · 「데이터 검증은 즉시 실패」 · 「받은 사본 규칙」 이상치 판정 행
- `docs/조사/선물_대_레버리지_ETF.md` §17.2 — 제목을 「기존 로더로는 다계약 선물을 읽을 수 없다」로, 표 첫 행을 「`load_market_csv` 의 중복 날짜 검사 | 같은 날짜에 계약이 5 ~ 10개라 **중복 날짜로 멈춘다** — 날짜만 유일 키로 보는 로더라 계약을 가를 수 없다」로
- `docs/COMMANDS.md`: 변경 없음 — 실행 명령 · CLI 옵션이 바뀌지 않는다

### 데이터/결과 영향

- 산출물 스키마 · 값 변화 없음(사본 중복 0건) — 마지막 Phase 의 재실행 diff 가 확인한다
- 중복 날짜가 든 파일을 읽는 실행은 이제 멈춘다 — 의도한 변화다

## 6) 단계별 계획(Phases)

### Phase 0 — 멈춤 정책을 테스트로 먼저 고정(레드)

**작업 내용**:

- [ ] 착수 전 `git status --short` 에 이 계획서 밖의 변경이 없다 — quant 통일 문서 · scipy 제거를 먼저 커밋했는지 본다(Risks)
- [ ] `tests/test_data_loader.py` 의 두 테스트를 멈춤으로 바꾸고 시세의 다른 값 두 행 테스트를 더한다 — 메시지에 중복된 날짜(`2026-01-02`)가 드는지까지 본다

**Validation**:

- [ ] `env -u VIRTUAL_ENV poetry run pytest tests/test_data_loader.py` — 바꾼 · 더한 테스트만 실패하고(지금 코드는 지우고 통과시키므로) 나머지는 통과한다

---

### Phase 1 — 로더 구현(그린)

**작업 내용**:

- [ ] `loader.py` 를 Scope 대로 고친다 — 헬퍼 하나 · 두 로더의 호출 · docstring 셋
- [ ] 변형 확인 — 헬퍼 호출을 옛 네 줄로 되돌리면 Phase 0 의 테스트가 실패하는지 `PYTHONDONTWRITEBYTECODE=1` 로 보고 되돌린다

**Validation**:

- [ ] `env -u VIRTUAL_ENV poetry run pytest tests/test_data_loader.py` 통과 · 변형에서 실패한 테스트 이름을 진행 로그에 적는다

---

### Phase 2 — 문서와 재실행

**작업 내용**:

- [ ] `src/verify_lab/CLAUDE.md` · `docs/조사/선물_대_레버리지_ETF.md` §17.2 를 Scope 대로 고친다
- [ ] 두 매매법을 인자 없이 다시 돌린다(`docs/COMMANDS.md` 「시세를 다시 받은 뒤 다시 돌리는 순서」의 블록)

**Validation**:

- [ ] 두 실행 종료 코드 0 · ERROR 줄 0 · `git diff --stat storage/results/` 비어 있음

---

### 마지막 Phase — 리뷰 · 최종 검증

**작업 내용**

> 🔴 **체크박스와 상태를 먼저 확정하고, `/commit` 은 맨 마지막에** — 이유는 `/impl-plan` 「5) Commit Messages」.

- [ ] 필요한 문서 업데이트 확인 (`docs/COMMANDS.md` 변경 없음)
- [ ] 자동 포맷 적용 (`poetry run black .`)
- [ ] 변경 기능 및 전체 플로우 최종 검증 — 포맷 뒤 `git diff --stat storage/results/` 가 여전히 비어 있다
- [ ] Validation 절에 `/code-review` 와 품질 검증 **실행 결과**를 적는다
- [ ] 근거 승격 확인 · 미룬 지적 옮기기
- [ ] DoD 체크리스트 최종 업데이트 및 체크 완료
- [ ] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정
- [ ] 🔴 **마지막에 `/commit` 을 실행하고 그 후보를 «이 계획서» 의 `#### Commit Messages` 절에 옮긴다** —
      대화에만 내면 그 절이 빈 채로 남는다. **커밋은 사용자가 한다 — 후보만 낸다**

**Validation**:

> 순서는 `/code-review` → 품질 검증이다. 고칠 것 · 회차 상한 · 수정분 검증은 `/impl-plan` 의 `review.md` 가 정한다.

- [ ] `/code-review xhigh` **1회차** (발견 \_\_건 — 버그 \_\_ [무거움 \_\_ · 가벼움 \_\_] · 그 외 \_\_ · 조치: \_\_)
- [ ] 수정분 검증 (수정 \_\_건 · 발견 \_\_건 — 무거움 \_\_ · 조치: \_\_ — 마지막 회차에 고친 것이 없으면 「해당 없음」)
- [ ] `poetry run python validate_project.py` (passed=\_\_, failed=\_\_, skipped=\_\_)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다** — 추측으로 적은 줄은 그대로 나간다.

- [ ] (미작성 — `/commit` 을 실행하고 후보 5개를 **이 자리에** 번호 붙은 줄로 옮긴 뒤 이 줄을 지운다)

## 7) 리스크(Risks)

- **중복 날짜를 우연히 만드는 테스트 픽스처가 더 있으면 깨진다** — 이름으로 찾은 것은 둘뿐이다. 완화: 마지막 Phase 의 품질 검증이 전체 테스트를 돌린다. 깨지면 그 픽스처가 중복을 «의도»했는지 보고, 의도하지 않았으면 픽스처를 고친다
- **되살린 조사가 옛 파일(`git show c3a2641:…`)을 읽을 때 중복이 있으면 멈춘다** — 그 조사들의 품질 기록이 중복 날짜 0건이다(`docs/조사/원달러_ETF_등가성.md` · `docs/조사/역방향.md`). 멈추면 그 파일이 무엇인지 보고 정하는 것이 이 변경의 목적이다
- **커밋이 섞이는 위험** — 착수 전 작업 트리에 quant 통일 문서 · scipy 제거가 미커밋으로 있다. 완화: 그 변경을 먼저 커밋한 뒤 착수한다(`docs/MEMORY.md` 「이름만 바꾸는 변경과 값을 바꾸는 변경을 한 커밋에 섞지 않는다」와 같은 이유 — 재실행 diff 가 이 변경만 말하게)

## 8) 메모(Notes)

- 결정: 판정 자리는 두 로더가 중복을 지우던 자리(4단계)다. 탈락: `validate_market_data` · `validate_series_data` 안(값 검사 함수라 구조 판정이 섞인다 — 부르는 곳은 같아 효과는 같다) · `validate_market_frame` 안(메모리 프레임 13곳으로 범위가 넓어진다)
- 결정: 같은 값 두 행도 멈춘다 — quant · quant-data 가 날짜만 보고 멈추고, 값이 같은지 보고 통과시키면 「어느 쪽이 맞나」를 다시 고르게 된다

### 진행 로그 (KST)

- 2026-11-13 08:12: 계획서 작성 — 사본 9개 중복 0건 · 로더 호출처 · 고정 테스트 둘 · 문서 자리 넷 확인
- 2026-11-13 08:12: 자체 검증 5회차 — 1회차(기존 시세 테스트가 이미 같은 값 경계라 「더할 것」을 다른 값 두 행으로 정정) · 2회차(착수 전 커밋 확인을 Phase 0 체크박스로) 반영, 3 ~ 5회차 개선 없음으로 멈춤
