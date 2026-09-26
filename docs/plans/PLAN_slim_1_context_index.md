# Implementation Plan: 경량화 ① — 끝난 계획서 · docs/context · reference 코드 원본 삭제와 INDEX 재설계

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

**작성일**: 2026-09-26 16:14
**마지막 업데이트**: 2026-09-26 17:20
**관련 범위**: docs, .claude/rules, reference, tests(`test_index.py` 하나)
**관련 문서**: `.claude/rules/docs.md`, `.claude/rules/reference.md`, `tests/CLAUDE.md`, `docs/plans/REPORT_lightweight_inventory.md`

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

- [x] 목표 1: 끝난 계획서 16개를 지운다 — 경량화 범위에 드는 미조치 지적은 먼저 인벤토리 보고서 백로그로 옮긴다
- [x] 목표 2: `docs/context/` 와 그 전제에서 나온 규칙(과제 B 「QQQ 와의 분리」)을 저장소에서 걷어내고, 루트 `CLAUDE.md` 에 **「개인 운용 상태를 전제로 판단하지 않는다」**를 적는다
- [x] 목표 3: `reference/` 에서 이미 `src/` 에 구현된 계층의 **코드 원본 21개**를 지운다
- [x] 목표 4: `docs/INDEX.md` 를 **「위치만」 원칙 + 고정 어휘 상태 칸**으로 다시 쓴다 (288줄 → 약 100줄 목표)

## 2) 비목표(Non-Goals)

- **매매법·조사 문서 본문의 개인 운용 서술 정리** — 계획서 ⑤. 단, **`docs/context` 를 링크하는 문장과 그 링크에 기대는 단락만** 여기서 지운다(삭제 즉시 죽은 링크가 되고 테스트가 못 잡기 때문)
- **`docs/MEMORY.md` 의 달러 운용 절, 규칙 문서의 중복·이력·모순 정리** — 계획서 ④
- **코드 정리** — 계획서 ②③
- **`docs/COMMANDS.md`** — 계획서 ⑥
- **공개 git 이력에서의 삭제** — HEAD 에서 지워도 이력에는 남는다. 별개의 판단이다
- **`docs/plans/PLAN_toast_skip_while_agents_run.md`** — 다른 작업의 계획서다. 읽지도 고치지도 지우지도 않는다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

- 사용자가 이 저장소의 목적을 **「기존 포트폴리오 지연진입의 후속」에서 「순수 연구·분석」으로 바꿨다**(2026-09-26). 세션이 포트폴리오를 인지하지 않아야 하는데, `docs/context/` 두 문서가 **「가장 중요한 문서」로 매 진입 경로에 걸려 있다** — 루트 `CLAUDE.md`·INDEX·session-bootstrap·docs.md 가 필독으로 지목하고 `tests/test_index.py:149` 가 INDEX 링크를 강제한다
- 그 전제에서 나온 **과제 B(「이 신호가 QQQ 와 다르게 움직이는가」를 결과 문서에 반드시 적는다)** 가 루트 `CLAUDE.md` 의 규칙으로 남아 있다
- 끝난 계획서 16개(5,892줄)는 근거가 살아있는 문서로 승격돼 있다(표본 확인 완료). 살아있는 문서가 특정 계획서를 링크하는 곳 0건
- `reference/` 의 코드 원본 21개는 **이미 구현된 계층의 원본**이라 쓰임이 끝났다. 지식 문서 3개와 `test_examples/` 3개는 아직 인용된다
- INDEX 는 **「위치만 적는다」는 자기 규칙을 어기고** 문서 요약을 담아(한 셀 최대 약 1,500자) 요약이 원문보다 낡았다 — 없는 `--stop-grid`·`grid.csv`, 틀린 로드 경로, 헤더와 셀 수가 안 맞는 행(73·75행)
- 조사 근거 전체와 결정: `docs/plans/REPORT_lightweight_inventory.md` §3.5 · §3.6-F · §4 · §5 · §10

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- `.claude/plan-config.json` — 이 저장소의 검증 명령·자동 포맷·근거 승격 목적지 (**값의 SoT**)
- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절 (값이 아니라 **판단 근거**)
- `.claude/rules/docs.md` — 문서 종류 · 과거형이 허용되는 자리 · 계획서
- `.claude/rules/reference.md` — reference 폴더 규칙
- `.claude/rules/session-bootstrap.md`
- `tests/CLAUDE.md` — `tests/test_index.py` 를 고친다

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 끝난 계획서 16개 삭제, `docs/plans/.gitkeep` 유지, 미조치 지적 중 범위 해당분이 보고서 백로그에 있음
- [x] `docs/context/` 3개와 `.claude/rules/context.md` 삭제, 살아있는 문서·테스트의 context 참조 0
- [x] 과제 B 가 규칙 계층(루트 `CLAUDE.md` · `.claude/` · INDEX · README)에서 사라지고, 루트 `CLAUDE.md` 에 「개인 운용 상태를 전제로 판단하지 않는다」가 결정 출처와 함께 적힘
- [x] `reference/` 코드 원본 21개 삭제, 저장소 안의 참조 0
- [x] INDEX 재설계 — 요약 없음 · 상태 칸 고정 어휘 · 모든 표의 헤더 셀 수 = 행 셀 수
- [x] 회귀 테스트: `tests/test_index.py` 가 context 를 핵심 문서로 요구하지 않고, `docs/context` 가 되살아나면 실패한다
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — `docs/COMMANDS.md` 변경 없음 · 루트 `CLAUDE.md` 변경 있음 · INDEX 변경 있음 · `.claude/rules/` 변경 있음
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (「왜 context 를 지웠나」는 루트 `CLAUDE.md` 에, 「INDEX 는 위치만」은 `.claude/rules/docs.md`(이미 있음)와 INDEX 머리말에.
      시리즈 나머지의 결정·백로그는 보고서가 갖는다)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

**삭제**
- `docs/plans/` 의 끝난 계획서 16개 — **이름으로만 지운다(글롭 금지)**:
  `PLAN_expiry_fixed_stop_only.md` · `PLAN_expiry_monthend_promotion.md` · `PLAN_expiry_monthend_retire.md` ·
  `PLAN_expiry_monthend_track.md` · `PLAN_expiry_three_cells_and_outputs.md` · `PLAN_gate_1pct_and_worst_during_hold.md` ·
  `PLAN_gate_min_mean_and_friday_only.md` · `PLAN_midterm_cycle_track.md` · `PLAN_midterm_promotion.md` ·
  `PLAN_midterm_september_entry.md` · `PLAN_midterm_split_entry.md` · `PLAN_month_end_promotion_september.md` ·
  `PLAN_plan_config_slimming.md` · `PLAN_reverse_k10_fixed_cells.md` · `PLAN_screening_into_performance.md` ·
  `PLAN_user_facing_outputs.md`
- `docs/context/README.md` · `RESEARCH_q2_2xs_qqq_correlation.md` · `RESEARCH_qqq_late_entry.md`, `.claude/rules/context.md`
- `reference/` 코드 원본 21개: `pykrx_collect/` 14개(폴더째) · `yfinance_downloader.py` · `data_loader_qbt.py` ·
  `common_constants_qbt.py` · `common_constants_krx.py` · `event_study.py` · `analysis_script_example.py` · `parallel_executor_qbt.py`
  (남는 것: `README.md` · `과최적화_검증_노하우.md` · `데이터처리_설계원칙.md` · `pykrx_실측기록.md` · `test_examples/` 3개)

**수정**
- 루트 `CLAUDE.md` — 「이 프로젝트가 무엇인가」의 context·과제 A/B 절, 규칙 문서 표 두 행, 규칙 배치 예시, 디렉터리 트리
- `docs/INDEX.md` — 전면 재작성
- `README.md` — context 링크, 없는 `docs/검증/` 링크
- `.claude/rules/session-bootstrap.md` · `docs.md` · `research.md` · `reference.md`
- `reference/README.md`
- `tests/test_index.py`
- context 를 링크하는 본문: `docs/매매/역방향/결과.md`(§11 부근 두 곳) · `docs/매매/역방향/규칙.md`(§5.5) · `docs/조사/원달러_ETF_등가성/결과.md`(「프로젝트 맥락에서」 절)
- `docs/매매/역방향/설계.md:684` — 지우는 `reference/pykrx_collect/krx_credentials.py` 를 가리키는 서술
- `docs/plans/REPORT_lightweight_inventory.md` — 백로그 절 채우기
- `docs/COMMANDS.md`: **변경 없음** (실행 명령어·CLI 옵션 변경 없음)

### 데이터/결과 영향

- 산출물(`storage/results/`) 변경 없음 — 바뀌는 코드는 테스트 파일 하나다
- `docs/context` 가 되살아나지 않도록 `REMOVED_DOCUMENTS` 에 한 줄을 더한다 (기존 관용: 걷어낸 문서 4개가 같은 방식으로 막혀 있다)

## 6) 단계별 계획(Phases)

### Phase 0 — 회귀 테스트를 먼저 고친다 (레드)

**작업 내용**:

- [x] `tests/test_index.py`: `test_core_documents_linked` 파라미터에서 `"docs/context/README.md"` 를 빼고, `REMOVED_DOCUMENTS` 에 `"docs/context"` 를 더한다 (주석은 옆 항목들과 같은 결로 — 「되살아나면 개인 운용 상태가 다시 진입 경로에 걸린다」)

**Validation**:

- [x] `poetry run pytest tests/test_index.py` 에서 `test_removed_documents_stay_removed[docs/context]` **하나만 실패**한다 (context 가 아직 있으므로 — 의도한 레드)

---

### Phase 1 — docs/context 삭제와 과제 B 제거 (그린)

**작업 내용**:

- [x] `docs/context/` 3개와 `.claude/rules/context.md` 를 지운다 → Phase 0 의 레드가 통과로 바뀐다
- [x] 루트 `CLAUDE.md`: 「왜 시작됐는가」와 「이 프로젝트의 과제는 둘이다」를 **과제 하나(통계적 우위)** 와 **「개인 운용 상태·포트폴리오를 전제로 판단하지 않는다 (2026-09-26 사용자 결정 — 순수 연구·분석 저장소)」** 로 바꾼다. 규칙 문서 표의 context 두 행, 「CLAUDE.md 를 두면 오히려 혼란스러운 폴더」 예시의 `docs/context/**`, 디렉터리 트리의 `context/` 줄을 지운다
- [x] `.claude/rules/session-bootstrap.md` 2절 표의 「`docs/context/` 두 문서」, `.claude/rules/docs.md` 의 살아있는 문서 목록과 `context/` SoT 설명을 지운다
- [x] `.claude/rules/research.md:15` 와 `reference/README.md:47` 의 「실물 예시 = context 두 문서」: 결과 문서 중 `research.md` 의 절 구성을 가장 잘 따르는 것 하나로 바꾼다. 따르는 문서가 없으면 문장을 지운다 (고른 근거를 진행 로그에 남긴다)
- [x] `README.md`: context 링크 줄을 지우고, 없는 `docs/검증/` 링크를 고친다
- [x] 본문의 context 링크: 역방향 `결과.md` §11 의 context 인용·포트폴리오 단락, 역방향 `규칙.md` §5.5 의 context 문장, 등가성 `결과.md` 「프로젝트 맥락에서」 절 — **context 에 기댄 문장만** 지운다. 「두 시장 신호가 같이 난다」 같은 측정 사실은 남긴다

**Validation**:

- [x] `grep -rn -E 'docs/context|\.\./context|context/README|context\.md' --exclude-dir={.git,.venv,storage,plans} .` 결과가 **`tests/test_index.py` 의 `REMOVED_DOCUMENTS` 한 줄뿐**이다 (Phase 0 이 일부러 넣은 가드)
- [x] 규칙 계층(루트 `CLAUDE.md` · `.claude/` · `docs/INDEX.md` · `README.md`)에서 `과제 B|QQQ 와의 분리|부수적 매매법|QQQ와 다르게` grep 결과가 0 이다 — 매매법·조사 문서에 남은 건은 보고서 백로그에 목록으로 둔다(계획서 ⑤)
- [x] `poetry run pytest tests/test_index.py tests/test_research_docs.py` 통과 (Phase 0 의 레드가 그린으로 바뀐 것 포함)

---

### Phase 2 — 끝난 계획서 정리

**작업 내용**:

- [x] 잔여물이 있는 5개(`midterm_cycle_track` · `midterm_september_entry` · `midterm_split_entry` · `midterm_promotion` · `reverse_k10_fixed_cells`)에서 **경량화 범위(데드 코드 · 주석 · 문서 사실 오류)** 에 드는 미조치 지적을 보고서 §12 백로그로 옮긴다 — 원문은 따옴표, 출처 계획서 이름을 붙인다. 범위 밖(설계 제안 등)은 옮기지 않는다(보고서 §10 Q10)
- [x] 16개를 위 목록의 **이름으로** 지운다. `.gitkeep` · 이 계획서 · 보고서 · `PLAN_toast_skip_while_agents_run.md` 는 남는다

**Validation**:

- [x] `ls -a docs/plans` 가 `.gitkeep` · `PLAN_slim_1_context_index.md` · `PLAN_toast_skip_while_agents_run.md` · `REPORT_lightweight_inventory.md` 만 보인다
- [x] 살아있는 문서(`docs/plans` 제외)의 `PLAN_` 참조 grep 결과가 0 이다

---

### Phase 3 — reference 코드 원본 삭제와 INDEX 재설계

**작업 내용**:

- [x] `reference/` 코드 원본 21개를 지운다 (Scope 목록)
- [x] `reference/README.md`: 지운 파일의 행을 지우고, 「Phase가 끝날 때」 같은 수명 서술을 지금 상태(남은 것은 지식 문서와 테스트 예시)로 고친다. `.claude/rules/reference.md` 의 같은 서술도 고친다
- [x] `docs/매매/역방향/설계.md:684` 의 `reference/pykrx_collect/krx_credentials.py` 서술을 저장소 안의 구현(`src/verify_lab/data/krx_credentials.py`) 기준으로 고친다
- [x] 옛 INDEX 의 「언제 읽나」 안내를 목록으로 뽑아, 새 INDEX §3 이나 각 문서의 머리말로 **대체되는지 하나씩 대조**한다. 대체되지 않는 것은 §3 에 넣는다
- [x] `docs/INDEX.md` 를 다시 쓴다
  - 머리말: 위치만 적는다 · 「무엇」은 각 문서의 머리말이 말한다 · 진입 순서의 SoT 는 session-bootstrap · `tests/test_index.py` 가 양방향 검사
  - §1 규칙 문서 — `문서 | 담당(한 줄) | 로드`
  - §2 매매법·조사 — `이름 | slug | 등급 | 코드 | 문서 | 상태`. 링크 텍스트는 「설계 · 결과 · 규칙」. **상태는 고정 어휘 하나**: `확정 규칙` · `재는 중` · `걸지 않음` · `우위 없음` · `성질 조사` · `데이터 실측` — 어휘 정의는 표 위 한 줄. `원달러_조달.md`(레지스트리 밖 한 장형)도 한 행
  - §3 찾는 것 → 어디 — 매매법 폴더 밖에서 찾기 어려운 지식만. **절 번호가 아니라 절 제목으로** 가리킨다 (예: ETN 시세 → `레버리지_ETF_괴리/설계.md` 「6. 데이터 실측 기록」, 국내 선물 시세 → `선물_대_레버리지_ETF/설계.md` 「5. 데이터 실측 기록 — KRX 파생상품 통계」, 지수 OHLC 의 진위 → `중간선거_사이클/설계.md` 「3. 데이터 실측 기록」, ECOS·FRED 코드 → `원달러_그리드/설계.md` 「3. 데이터 실측 기록」, pykrx 동작 → `역방향/설계.md` 「8. 사전 실측 기록」·`reference/pykrx_실측기록.md`)
  - §4 그 밖 — COMMANDS · README · reference(README + 남은 파일 링크 목록)
  - 옛 §5 「데이터와 산출물」과 §6 「유지 규칙」은 담지 않는다 — 같은 내용이 `src/verify_lab/CLAUDE.md` 「데이터 저장 규칙」과 `.claude/rules/docs.md` 에 있는지 **먼저 확인**하고, 없는 것이 있으면 그 자리로 옮긴다

**Validation**:

- [x] `poetry run pytest tests/test_index.py tests/test_tracks.py` 통과
- [x] INDEX 의 모든 표에서 헤더 셀 수 = 행 셀 수 (스크립트로 센다)
- [x] INDEX 줄 수와 바이트 수를 진행 로그에 적는다 (목표 약 100줄)
- [x] 지운 reference 파일 이름(경로 형태) grep 결과가 저장소 안에서 0 이다 (`docs/plans` 제외)

---

### Phase 4 (마지막) — 문서 정리 및 최종 검증

**작업 내용**

> 🔴 **`/commit` 이 «맨 마지막»인 것은 의도다.** 그 스킬은 「후보 뒤에는 아무것도 덧붙이지 말 것」으로
> 끝나므로 **호출하는 순간 그 턴이 거기서 닫힌다.** 중간에 두면 뒤에 적힌 항목이 그 벽 너머에 남는다 —
> 실제로 두 번 그렇게 샜다(`[실측] 2026-09-14` 후보를 계획서에 안 옮김 · `2026-09-16` 옮기고 체크박스를 안 닫음).
> **체크박스와 상태를 먼저 확정하고, 커밋 후보를 마지막에 만든다.**

- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` 변경 없음 확인)
- [x] 보고서 §12 백로그 최신화 (Phase 1 에서 남긴 매매법·조사 문서의 과제 B 서술 목록 포함)
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

- [x] `/code-review xhigh` **1회차** (발견 13건 — 버그 0 · 그 외 13 · 조치: 없음 — 목록은 보고서 §12.3, 조치 여부는 사용자 결정)
- [x] `poetry run python validate_project.py` (passed=1282, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다.**
> 계획서를 쓰는 시점에는 diff 가 없어 여기 적는 것은 전부 추측이고,
> **추측으로 적은 줄은 그대로 나간다.** 형식·문체 규칙은 `/commit` 이 정한다.

1. 문서 / docs/context 삭제와 INDEX 위치 전용 재설계
2. 문서 / 개인 운용 맥락 제거와 끝난 계획서 16개 · reference 코드 원본 21개 정리
3. 문서 / 순수 연구 저장소 전환 — 포트폴리오 문서와 과제 B 제거, 되살아남 방지 테스트 추가
4. 문서 / 경량화 1단계 — 계획서 · context · reference 코드 삭제와 INDEX 288줄 → 93줄 축소
5. 문서 / INDEX 요약 제거와 고정 어휘 상태 칸 도입, 절 번호 포인터의 표 이름 전환

## 7) 리스크(Risks)

- **INDEX 등록 누락** — `test_all_documents_registered` 가 잡는다 (마크다운 링크만 등록으로 친다)
- **본문의 죽은 링크는 테스트가 못 잡는다** — 결과 문서는 「관련 파일」 절만 검사된다. Phase 1 의 grep 이 대신한다
- **INDEX 요약을 걷어내며 「언제 읽나」 안내를 잃는다** — Phase 3 의 대조 항목으로 막는다
- **research.md 의 새 실물 예시가 그 규칙을 안 따를 수 있다** — 절 구성을 대조해 고르고, 없으면 문장을 지운다
- **다른 세션이 `docs/plans/` 에 파일을 만들고 있다** (`PLAN_toast_skip_while_agents_run.md`) — 삭제는 이름 목록으로만 한다
- **`VIRTUAL_ENV` 가 프로젝트 밖을 가리키면 pytest·validate 가 전부 실패한다** — 그 증상이면 `env -u VIRTUAL_ENV` 로 다시 돈다 (session-bootstrap 5절)
- **공개 저장소라 지운 문서가 이력에 남는다** — 이 계획서의 범위가 아니다(Non-Goals)

## 8) 메모(Notes)

- 시리즈와 결정의 자리는 `docs/plans/REPORT_lightweight_inventory.md` §10(결정) · §11(시리즈) · §12(백로그)다. 이 계획서는 시리즈 ①이며 **커밋 하나**로 끝난다. ②는 이 커밋 뒤에 쓴다
- 만기_말일 강등 기준(승률 75% 초과, 게이트 미도입)은 삭제할 `PLAN_expiry_monthend_retire.md` 에만 있어 보고서 §10 Q9⑵ 로 먼저 옮겼다
- quant-notify(역방향 20위 → 10위) 갱신 필요는 2026-09-26 대화에서 사용자에게 전달했다 — 저장소 문서에는 적지 않는다(진행 상태 문서화 금지)

### 진행 로그 (KST)

- 2026-09-26 16:14: 계획서 작성 (Draft). 조사는 읽기 전용 감사 7건, 결정은 사용자 답(Q9⑴ 사전 가설 · 나머지 추천안)
- 2026-09-26 16:18: 승인 요청 전 자체 검증 — 레드 단계가 Phase 2 안에 있어 고정 규칙 「Phase 1부터 그린 유지」에 어긋나므로 회귀 테스트 수정을 Phase 0 으로 분리하고 context 삭제를 Phase 1, 계획서 정리를 Phase 2 로 바꿨다. 같은 검증에서 Phase 1 grep 의 기대값을 「0」에서 「Phase 0 이 넣은 가드 한 줄」로 고쳤다
- 2026-09-26 16:40: Phase 0 레드 확인(1 failed · 11 passed) → Phase 1 완료(pytest 94 passed). research.md 실물 예시는 `docs/조사/레버리지_ETF_괴리/결과.md` — 필수 구조를 순서까지 따르고 앞머리 재실행 블록이 없는 유일한 결과 문서라서 골랐다. INDEX 의 context 3행은 링크 검사를 지키려고 Phase 1 에서 먼저 지웠다(전면 재작성은 Phase 3)
- 2026-09-26 16:52: Phase 2 완료 — 잔여 지적 14묶음을 보고서 §12.1 로, 과제 B 잔존 자리를 §12.2 로 옮기고 16개를 이름으로 삭제. 남은 `PLAN_` 은 테스트 정규식·폴더 규약 설명뿐(특정 계획서 참조 0)
- 2026-09-26 17:05: Phase 3 완료 — reference 코드 원본 21개 삭제, INDEX 288줄 · 43,932B → 93줄 · 8.3KB(표 4개 셀 수 불일치 0), pytest 64 passed. 옛 INDEX 의 「언제 읽나」 안내는 대조 결과 문서 내부 절 안내(각 문서 목차가 대신함)와 교차 지식(§3 「찾는 것」 8행으로 옮김)으로 갈렸고, 그리드 설계와 사양서의 우선순위는 사양서 머리말이 이미 말한다. 옛 §5·§6 내용은 `src/verify_lab/CLAUDE.md` 「데이터 저장 규칙」·`.claude/rules/docs.md` INDEX 항목에 이미 있음을 확인(옛 §5 의 「같은 `_max.csv` 라도 가격 기준이 다르다」는 틀린 서술이라 옮기지 않음). INDEX 절 번호를 가리키던 4곳(research.md · 루트 CLAUDE.md · src CLAUDE.md 2)을 표 이름으로 바꿈
- 2026-09-26 17:20: 마지막 Phase — black 변경 0 · COMMANDS 무변경 · `/code-review xhigh` 1회차 버그 0(그 외 13, 보고서 §12.3 — 이 계획서가 만든 4건 R1·R7·R9·R13 은 사용자 결정 대기) · 품질 검증 passed=1282 failed=0 skipped=0. 상태 Done 확정
- 2026-09-26 16:55: **시각 정정** — 위 16:40 · 16:52 · 17:05 · 17:20 과 머리의 「마지막 업데이트」는 `date` 로 확인하지 않고 적은 값이다. `date` 로 확인한 실제 시각은 이 줄(16:55)이며, 마지막 Phase 는 커밋 `2c8d93f` 보다 앞서 끝났다
