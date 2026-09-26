# 경량화 시리즈 — 통합 진행 문서

> **임시 문서다.** 저장소 경량화를 계획서 여러 개로 나눠 세션을 바꿔 가며 진행하려고 만들었다
> (2026-09-26 사용자 요청). 루트 `CLAUDE.md` 의 「인계 문서를 따로 두지 않습니다」의 **명시적 예외**이며,
> 시리즈가 끝나면 이 문서와 시리즈의 계획서·보고서를 **전부 지운다**(아래 「끝 — 정리」).
> 살아있는 문서는 이 파일을 링크하지 않는다.

---

## 이 문서를 받은 세션이 할 일 — 순서대로

1. **이 문서를 끝까지 읽는다.** 특히 「시리즈 공통 주의」와 「인계 메모」
2. 세션 규칙대로 `docs/INDEX.md` 를 **`Read` 도구로** 연다 (`.claude/rules/session-bootstrap.md`)
3. **상태를 확인한다**
   - `git status --short` 가 비어 있어야 한다. 비어 있지 않으면 **멈추고 사용자에게 알린다** (앞 계획서가 커밋되지 않았거나 다른 작업의 변경이다)
   - 아래 진행 표에서 상태가 「커밋 대기」인 행이 있으면 `git log --oneline -5` 에서 그 계획서의 커밋을 찾는다. 있으면 그 행을 「완료」로 바꾸고 SHA 를 적는다. 없으면 **멈추고 사용자에게 알린다**
4. 진행 표에서 상태가 「대기」인 **첫 행**을 고른다. 그 행이 「끝 — 정리」면 아래 「끝 — 정리」 절을 한다
5. 그 계획서(`docs/plans/PLAN_slim_*.md`)를 `Read` 로 연다. **그 계획서의 「영향받는 규칙」 문서를 `Read` 로 읽고**, 아래 인계 메모 중 그 계획서에 걸리는 것을 먼저 확인한다
6. 계획서 상태를 `🟡 Draft` → `🔄 In Progress` 로 바꾸고(**Edit 도구로** — 주의 3), 진행 표의 상태를 「진행 중」으로 바꾼다
7. `/impl-plan` 규칙대로 Phase 를 진행한다
   - 계획서의 **「확정하는 판단」 표는 이미 사용자가 정한 것**이다(보고서 §10). 다시 묻지 않는다
   - 계획서에 없는 판단이 필요하거나 계획서의 전제가 실측으로 무너지면 **멈추고 사용자에게 묻는다** — 계획서 본문은 체크박스와 진행 로그 외에 고치지 않는다(바꿔야 하면 Notes 에 무엇이 왜 달라졌는지 적고 승인받는다)
8. 계획서의 마지막 Phase 에서, `/commit` **전에** 이 문서를 갱신한다
   - 진행 표: 그 행을 「커밋 대기」로
   - 인계 메모: 아래 형식으로 한 절을 더한다 — **다음 계획서가 알아야 할 것**을 중심으로
   - 보고서 §12 백로그: 리뷰 「그 외」와 넘긴 항목
9. `/commit` 후보를 **그 계획서**에 옮기고 상태를 `✅ Done` 으로(주의 4). **커밋은 사용자가 한다** — 후보를 낸 뒤 멈춘다
10. **한 세션에 계획서 하나만** 한다. 사용자가 커밋한 뒤 이 문서를 다시 보내면 다음 계획서를 한다

### 승인

계획서 ② ~ ⑧ 은 2026-09-26 에 작성됐다. **사용자가 이 문서를 프롬프트로 보내는 것이 진행 표의 다음 계획서를 착수하라는 승인이다** (2026-09-26 사용자 지시). 계획서가 스스로 「멈추고 묻는다」고 적은 지점에서는 멈춘다.

---

## 진행 표

상태 어휘: `대기` · `진행 중` · `커밋 대기` · `완료`.

| # | 계획서 | 범위 | 산출물 영향 | 상태 | 커밋 |
| --- | --- | --- | --- | --- | --- |
| ① | `docs/plans/PLAN_slim_1_context_index.md` | 끝난 계획서 16개 · `docs/context` · reference 코드 원본 삭제, INDEX 재설계 | 없음 | 완료 | `2c8d93f` |
| ② | `docs/plans/PLAN_slim_2_test_rename.md` | `test_strategy_*` 5개 개명 — 이름만 | 없음 | 대기 | |
| ③ | `docs/plans/PLAN_slim_3_dead_code.md` | 데드 코드 · 테스트 결함 · 재수출 · 연결 누락 · 주석 · 메타 키 | **없음 (재실행 바이트 동일이 통과 조건)** | 대기 | |
| ④ | `docs/plans/PLAN_slim_4_rule_docs.md` | 규칙·하네스 문서 — 중복 → SoT, 이력, 모순, 개인 운용 | 없음 | 대기 | |
| ⑤ | `docs/plans/PLAN_slim_5_trading_docs.md` | 역방향 · 중간선거 문서 6장, `측정.csv` 어긋남 열 | 중간선거 `측정.csv` | 대기 | |
| ⑥ | `docs/plans/PLAN_slim_6_calendar_docs.md` | 달력 조사 9장 → 한 장 3개, 복원 절차, 산출물 폴더 3개 삭제 | 폴더 삭제 | 대기 | |
| ⑦ | `docs/plans/PLAN_slim_7_survey_docs.md` | 원달러 5장 → 3장 · 연속_등락 · 괴리 · 선물, `NOTE_*` | 등가성 `summary.json` · 폴더 삭제 | 대기 | |
| ⑧ | `docs/plans/PLAN_slim_8_commands.md` | COMMANDS 컴팩트화와 설명 이관 | 없음 | 대기 | |
| 끝 | (계획서 없음 — 아래 「끝 — 정리」) | 시리즈 임시 문서 전부 삭제 | 없음 | 대기 | |

---

## 시리즈의 임시 문서

| 문서 | 담당 |
| --- | --- |
| `docs/plans/REPORT_lightweight_inventory.md` | 조사 요약(§0 ~ §9) · **확정된 결정(§10 — 결정의 SoT)** · 시리즈 범위(§11) · **백로그(§12)** |
| `docs/plans/AUDIT_slim_*.md` 6개 | 읽기 전용 감사 에이전트의 **보고 원문**(가공 없음). 계획서가 「AUDIT_slim_… §n」으로 가리킨다 |
| `docs/plans/PLAN_slim_1 ~ 8_*.md` | 계획서 |
| 이 문서 | 진행 표 · 절차 · 공통 주의 · 인계 메모 |

---

## 시리즈 공통 주의 — 모든 계획서에 걸린다

1. **줄 번호는 조사 시점(`f55617a`) 기준이다.** 앞 계획서가 파일을 고치면 밀린다 — 착수할 때 grep 으로 다시 찾는다. 감사 원문의 테스트 파일 이름은 ② 이전 이름이다(② 의 인계 메모에 대응표)
2. 🔴 **다른 작업의 계획서 `docs/plans/PLAN_toast_skip_while_agents_run.md` 가 `🔄 In Progress` 로 있다.** `/commit` 스킬의 규칙 10 은 「In Progress 계획서에 후보를 채운다」인데 — **후보는 이 시리즈의 `PLAN_slim_*` 에 채운다.** toast 계획서는 읽지도 고치지도 지우지도 않는다. 그 파일의 변경이 diff 에 섞이면 사용자에게 알린다
3. 🔴 **이모지 차단 훅** — 한 Bash 명령에 코드 파일 이름(예: `validate_project.py`)과 이모지가 함께 있으면 **명령 전체가 막힌다.** `✅` 같은 이스케이프도 막힌다. 계획서의 상태 줄(`🔄`·`✅`)은 **Edit 도구로** 바꾼다
4. 🔴 **`plan_lint` 는 Commit Messages 절이 채워진 뒤에만 `✅ Done` 저장을 허용한다.** 순서: 체크박스·Validation 확정 → `/commit` → 후보를 계획서에 옮김 → 상태 `✅ Done`(Edit). 계획서 ① 이 이 순서로 통과했다
5. **스크립트(python·sed)로 파일을 고친 뒤 Edit/Write 를 쓰려면 그 파일을 `Read` 로 다시 열어야 한다** — 안 그러면 거부된다
6. **시각은 추정하지 않는다** — `TZ=Asia/Seoul date '+%Y-%m-%d %H:%M'`. 계획서 ① 에서 추정 시각을 적은 실수가 있었다
7. **산출물 대조** — 실행 스크립트는 5개(`scripts/run_{reverse,midterm_cycle,leverage_tracking,futures_leverage,usdkrw_equivalence}.py`, 명령은 `docs/COMMANDS.md`). 재실행 뒤 `git diff --stat storage/results/`. 외부 호출이 없다(데이터 수집 스크립트는 돌리지 않는다)
8. **테스트가 문서를 검사한다** — `tests/test_index.py`(docs/·reference/ 의 모든 파일이 INDEX 에 **마크다운 링크**로 등록 · 링크 실재 · `docs/context` 부활 금지), `tests/test_research_docs.py`(`docs/{검증,매매,조사}/*/결과.md` 와 `docs/{검증,매매,조사}/*.md` 의 머리말 「데이터 기간」·`## 관련 파일`·`## N. 한계`·`## N. 재현 방법`·관련 파일 링크 실재·계획서 참조 금지), `tests/test_tracks.py`(코드가 있는 매매법의 한글 이름이 INDEX 에 있다). **본문 링크와 코드 주석의 문서 포인터는 어떤 테스트도 보지 않는다** — grep 과 링크 검사 스크립트로 확인한다
9. **규칙 문서가 INDEX 의 표를 이름으로 가리킨다** — 「규칙 문서」 표 · 「매매법·조사」 표. 표 제목을 바꾸지 않는다
10. **`.claude/rules/research.md` 의 결과 문서 「실물 예시」는 `docs/조사/레버리지_ETF_괴리/결과.md`** 다 — 그 문서의 장 순서를 깨지 않는다
11. **마크다운에서 범위를 적을 때 `~` 양옆에 공백** — 한 줄에 붙은 `~` 가 둘이면 그 사이가 취소선이 된다
12. **근거 승격** — 보고서와 감사 원문은 시리즈 끝에 지워진다. 각 계획서 범위의 결정(§10)은 **그 계획서가 살아있는 문서로 옮긴다**(각 DoD 에 있다)
13. **코드 리뷰** — `/code-review xhigh`, 버그 0 인 회차에서 끝낸다. 「그 외」는 고치지 않고 보고서 §12 백로그에 적는다. 그 계획서가 **스스로 만든** 결함은 사용자에게 따로 알린다(① 의 R1·R7·R9·R13 처럼)
14. **`VIRTUAL_ENV`** — 품질 검증이 세 항목 모두 실패하고 `Command not found` 가 보이면 `env -u VIRTUAL_ENV` 로 다시 돈다
15. **Git 은 사용자가 한다** — `git mv`·`git add` 도 하지 않는다. 읽기(`status`·`diff`·`log`·`show`)만

---

## 인계 메모 — 계획서가 끝날 때마다 아래에 한 절씩 더한다

형식: `### ⑦ PLAN_slim_… — 커밋 대기 (YYYY-MM-DD HH:MM)` 아래에 **한 일 3줄 이내**와 **다음 계획서가 알아야 할 것**(바뀐 경로·이름 · 넘긴 항목 · 밟은 함정). 커밋 SHA 는 다음 세션이 3단계에서 채운다.

### ① PLAN_slim_1_context_index — 완료 (`2c8d93f`)

- 한 일: `docs/context` 3개와 `.claude/rules/context.md` 삭제, 루트 `CLAUDE.md` 의 과제 A/B 를 「과제는 통계적 우위 하나 · **개인 포트폴리오·운용 상태를 전제로 판단하지 않는다 (2026-09-26 사용자 결정)**」로 교체. 끝난 계획서 16개 · `reference/` 코드 원본 21개 삭제. INDEX 288 → 93줄 재작성
- 다음 계획서가 알 것
  - **L2(개인 운용 서술 제거)의 근거 문장은 루트 `CLAUDE.md` 의 위 문장**이다 — ④ ⑤ ⑥ ⑦ 이 개인 서술을 지울 때 이 문장을 근거로 든다
  - INDEX 구조: §1 「규칙 문서」 · §2 「매매법·조사」(아직 `등급` 열이 있다 — ④ 가 지운다) · §3 「찾는 것 → 어디」(절 번호가 아니라 **절 제목**으로 가리킨다 — ⑤ ⑥ ⑦ 이 그 제목을 바꾸면 INDEX 도 고친다) · §4 「그 밖」
  - `tests/test_index.py` 의 `REMOVED_DOCUMENTS` 에 `docs/context` 가드가 있다. 그 테스트의 실패 메시지는 ① 이 바꿨고 리뷰에서 안내가 약해졌다는 지적(R9)을 받았다 — ③ 이 고친다
  - `docs/매매/역방향/결과.md` §11 은 **context 에 기댄 부분만** 걷었다(도입 · 옛 §11.2 · 포트폴리오 행). 결론 5행 · 한 줄 요약 · §11.3 표의 「QQQ와 다르게 움직이는가」와 **결론 표의 §11 링크 앵커(R1 — 옛 앵커)** 는 ⑤ 가 한다
  - `.claude/rules/research.md` 의 실물 예시를 `docs/조사/레버리지_ETF_괴리/결과.md` 로 바꿨다(필수 구조를 순서까지 따르는 유일한 결과 문서)
  - `reference/README.md` 의 「언제 지우나」가 인용처를 부풀렸다(R7 — `데이터처리_설계원칙.md`·`test_examples/conftest_example.py` 는 인용처가 없다) — ④ 가 사실대로 고친다
  - 리뷰 「그 외」 13건 전체는 보고서 §12.3
  - 계획서 ① 의 진행 로그 시각 일부는 추정값이다(같은 로그의 정정 줄 참고)

---

## 끝 — 정리 (⑧ 이 커밋된 뒤)

계획서가 없다 — 문서만 지우므로 계획서 선행 대상이 아니다. 그래도 순서를 지킨다.

1. 진행 표의 ② ~ ⑧ 이 전부 「완료」이고 SHA 가 `git log` 에 있는지 확인한다
2. **보고서 §10 의 결정이 살아있는 문서로 옮겨졌는지 대조한다** — 결정마다 「어디에 있는가」를 표로 만들어 사용자에게 보인다. 빠진 것이 있으면 **옮긴 뒤에** 지운다
   - Q1 → 루트 `CLAUDE.md` · Q2 → `docs/INDEX.md` 머리말 · Q3 → `docs/COMMANDS.md` 머리말 · Q4 → 한 장 문서 3개 · 등가성 `설계.md` 머리말(사양서 처분) · Q5 → 역방향 `결과.md` 재실행 기록 · Q6 → `reference/README.md` · Q7 → 한 장 문서·조달 부록의 원자료 포인터 · Q8 → 코드 · Q9 ⑴ ⑵ → `docs/조사/월말_진입.md`·`만기_말일.md` · Q9 ⑶ ⑷ → `.claude/rules/trading.md` · 루트 `CLAUDE.md` · Q9 ⑸ → 스크립트 · `src/verify_lab/CLAUDE.md` · 「측정.csv」 → `src/verify_lab/CLAUDE.md`
3. **보고서 §12 백로그에 남은 미처리 항목을 사용자에게 목록으로 보여 주고 처리 여부를 묻는다** — 지우면 그 목록이 사라진다. 알려진 것: `measure/calendar_entry.py` 이름·위치(R12) · 국내 종목을 코드로만 적은 조사 문서 표 · 인용처 없는 reference 두 파일 · 배수형 두 검증의 내부 컬럼 토큰 · `_print_rule` 출처 이중화
4. 사용자가 답하면 지운다 — **이름으로만**
   - `SLIM_SERIES.md`
   - `docs/plans/REPORT_lightweight_inventory.md`
   - `docs/plans/AUDIT_slim_dead_code.md` · `AUDIT_slim_rule_docs.md` · `AUDIT_slim_doc_code_mismatch.md` · `AUDIT_slim_trading_docs.md` · `AUDIT_slim_calendar_docs.md` · `AUDIT_slim_other_survey_docs.md`
   - `docs/plans/PLAN_slim_1_context_index.md` · `PLAN_slim_2_test_rename.md` · `PLAN_slim_3_dead_code.md` · `PLAN_slim_4_rule_docs.md` · `PLAN_slim_5_trading_docs.md` · `PLAN_slim_6_calendar_docs.md` · `PLAN_slim_7_survey_docs.md` · `PLAN_slim_8_commands.md`
   - **남긴다**: `docs/plans/.gitkeep`(계획서 게이트가 폴더 존재로 동작한다) · 다른 작업의 계획서
5. 확인: `grep -rn -E 'SLIM_SERIES|REPORT_lightweight|AUDIT_slim|PLAN_slim' --exclude-dir={.git,.venv} .` 가 0, `poetry run python validate_project.py` 통과
6. `/commit` 으로 후보를 낸다 — 계획서가 없으므로 후보는 대화에만 둔다. 커밋은 사용자가 한다
