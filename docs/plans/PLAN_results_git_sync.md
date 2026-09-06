# Implementation Plan: storage/results 를 git 동기화 대상으로 전환

> 작성/운영 규칙(SoT): `/impl-plan` 스킬(`~/.claude/skills/impl-plan/SKILL.md`)을 반드시 참고하세요.  
> (이 템플릿을 수정하거나 새로운 양식의 계획서를 만들 때도 해당 스킬을 포인터로 두고 준수합니다.)

**상태**: 🔄 In Progress

---

🚫 **이 영역은 삭제/수정 금지** 🚫

**상태 옵션**: 🟡 Draft / 🔄 In Progress / ✅ Done

**Done 처리 규칙**:

- ✅ Done 조건: DoD 모두 [x] + `skipped=0` + `failed=0`
- ⚠️ **스킵이 1개라도 존재하면 Done 처리 금지 + DoD 테스트 항목 체크 금지**
- 상세: `/impl-plan` 스킬의 "3) 스킵 및 완료 규칙" 참고
- 위 조건은 `~/.claude/hooks/plan_lint.py`가 저장 시 자동 검사합니다

---

**작성일**: 2026-09-06 21:48
**마지막 업데이트**: 2026-09-06 22:02
**관련 범위**: 하네스 설정, 문서 규칙, 결과·스펙·매매 규칙 문서
**관련 문서**: 루트 `CLAUDE.md`, `.claude/rules/docs.md`, `.claude/rules/research.md`, `.claude/rules/session-bootstrap.md`, `.claude/rules/context.md`, `tests/CLAUDE.md`, `docs/INDEX.md`

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

- [x] 목표 1: `storage/results/` 를 git 동기화 대상으로 전환한다. **`meta.json` 만 제외**한다
- [x] 목표 2: 「git 제외라 다른 PC 에 없다」를 전제한 규칙·지도·본문 서술을 **사실에 맞게** 고친다
- [ ] 목표 3: 근거가 끊긴 결과·매매 규칙 문서 **8개**를 실재하는 산출물 폴더로 다시 겨눈다
- [ ] 목표 4: 같은 현상이 되풀이되지 않게 **인용한 산출물 폴더를 지키는 규칙**을 세운다

## 2) 비목표(Non-Goals)

- **검증을 재실행하지 않는다. 시세를 재수집하지 않는다.** 수치가 달라지면 이 작업의 목적(근거 복원)이 무너진다
- **`docs/context/` 를 손대지 않는다.** 사용자 소유 문서이며(`.claude/rules/context.md`), 거기 적힌
  `storage/results/backtest/`·`storage/results/portfolio/` 는 **이전 프로젝트**의 경로라 이 저장소의 정책과 무관하다
- **원달러 그리드 코드를 복원하지 않는다.** 삭제는 2026-08-30 에 확정된 결정이다
- **고아 폴더 2개(`20260906_094153_kosdaq_month_end`·`20260906_094451_kosdaq_month_end`)의 처리를 미리 정하지 않는다.**
  사용자가 B PC 에서 결정한다 (Phase 3)
- 측정 방식·판정 기준·비용 반영은 건드리지 않는다

## 3) 배경/맥락(Context)

### 이 계획서만 받고 시작하는 세션에게 (B PC 진입 절차)

**이 문서 하나로 이어서 진행할 수 있게 쓰여 있다.** 이 파일이 `git pull` 로 넘어와 있다는 것은
**Phase 1·2 가 다른 PC(이하 「A PC」)에서 끝나 커밋됐다**는 뜻이다.

**진입 순서**

1. `docs/INDEX.md` 를 **`Read` 도구로** 연다 — 셸(`cat`·`head`)로 읽으면 그 경로의 규칙이 주입되지 않는다
2. 이 계획서의 아래 「현재 상태」와 **Phase 3** 을 읽는다
3. Phase 3 의 첫 명령(`ls storage/results/`)부터 실행한다

**현재 상태**

| 항목 | 상태 |
| --- | --- |
| Phase 1 (정책 전환: `.gitignore` + 서술 7곳) | **완료 · 커밋됨** |
| Phase 2 (뒤집힌 본문 서술 4곳) | **완료 · 커밋됨** |
| Phase 3 (산출물 합류 + 근거 재조준) | **남아 있다. 이 PC 에서 한다** |
| Phase 4 (재발 방지 + 최종 검증) | **남아 있다. 이 PC 에서 한다** |
| `storage/results/` | git 동기화 대상으로 전환됨. **`meta.json` 만 제외** |

**A PC 가 올린 산출물 폴더 11개** — 이 PC 의 `ls storage/results/` 결과와 대조해
**여기 없는 폴더가 이 PC 에만 있는 것**이고, 그것이 Phase 3 의 대상이다.

```
20260906_080223_index_extreme          20260906_094153_kosdaq_month_end
20260906_080311_option_expiry          20260906_094451_kosdaq_month_end
20260906_080320_leverage_tracking      20260906_123715_kosdaq_month_end
20260906_080353_futures_leverage       20260906_201656_kosdaq_month_end_trading
20260906_080354_usdkrw_equivalence
20260906_080406_reverse_trading
20260906_080410_expiry_trading
```

> **A PC 에는 2026-09-06 08:00 이후 실행 결과만 남아 있었다.** 그 전 폴더는 전부 지워진 뒤였고,
> 그래서 문서가 인용하던 옛 폴더 7개가 A PC 에서는 하나도 나오지 않았다.
> **이 PC 가 그 옛 폴더들의 마지막 소재지일 수 있다** — Phase 3 의 첫 명령이 그것을 확인하는 것이다.

**하지 말 것** (Non-Goals 의 재확인)

- **검증을 재실행하지 말 것. 시세를 재수집하지 말 것.** 수치가 달라지면 근거 복원이라는 목적이 무너진다
- `docs/context/` 를 손대지 말 것 — 사용자 소유 문서다
- 고아 폴더 2개를 임의로 지우지 말 것 — **사용자가 이 PC 에서 결정한다**

### 현재 문제점 / 동기

`docs/spec/`·`docs/research/`·`docs/strategy/` 의 **8개 문서가 존재하지 않는 산출물 폴더를 근거로 인용**하고 있다.
원인은 둘이고, 하나만 고치면 재발한다.

| # | 원인 | 근거 |
| --- | --- | --- |
| 1 | `storage/results/` 가 git 제외라 **다른 PC 로 넘어가지 않는다** | `.gitignore:27` |
| 2 | 재실행이 **새 폴더**를 만들고 옛 폴더는 지워지는데, 문서는 옛 폴더명을 그대로 들고 있다 | A PC 디스크에 2026-09-06 폴더만 남아 있음 |

**실측 (2026-09-06 21:48 KST, A PC)**

| 항목 | 값 |
| --- | --- |
| A PC `meta.json` 이 아는 실행 폴더 | 32개, 가장 이른 것이 `20260830_161331` |
| 문서가 인용한 옛 폴더 7개의 `meta.json` 기록 | **0건** — B PC 에서 실행된 것 |
| `storage/results` 원본 / git 저장 추정 | **86M / 약 15M** (zlib 압축 기준) |
| 그중 `20260906_080320_leverage_tracking` | 74M / **12.7M** (`windows_*.csv` 22개) |
| 최대 파일 | 4.2M (GitHub 100MB 제한과 무관) |
| 현재 `.git` | 16M |
| `storage/market`·`storage/series` 참조 66건 | **전부 실재** — 깨진 것은 `storage/results` 뿐 |

**`meta.json` 만 제외하는 이유** — `src/verify_lab/utils/meta_manager.py` 의 `save_metadata()` 가
실행할 때마다 **파일 전체를 다시 쓴다**(`_load_full_metadata()` → `json.dump()`). 산출물 CSV 는 실행 시각으로
폴더가 갈려 절대 충돌하지 않는데 이 파일 하나만 **두 PC 가 각자 실행할 때마다 충돌**한다.
게다가 `MAX_HISTORY_COUNT = 5` 로 순환 저장이라 오래된 이력은 어차피 밀려 사라지고,
값에 `/home/yblee/...` 절대경로가 들어 있어 PC 가 바뀌면 매 줄이 충돌 후보가 된다.
**근거 보존용 파일이 아니므로 제외한다.**

**사용자 확정 사항 (2026-09-06)**

| 항목 | 결정 |
| --- | --- |
| 추적 범위 | `storage/results` **전체**, `meta.json` 만 제외 |
| `windows_*.csv` 22개 | **포함** — 측정의 원칙 8(사용자가 직접 검증할 수 있어야 한다)이 원자료를 요구하고, `docs/research/레버리지_ETF_괴리.md` §8 이 직접 인용한다 |
| 고아 폴더 2개 | **B PC 에서 결정** — 「그대로 둔다」로 확정된 것이 아니다 |
| 진행 순서 | A PC 에서 할 수 있는 것부터. **마무리는 B PC** |

### 근거가 끊긴 문서 8개 (Phase 3 대상)

| 문서 | 위치 | 현재 가리키는 것 | 재생성 |
| --- | --- | --- | --- |
| `docs/research/지수_극단_이벤트.md` | :7 · :132 | `20260820_170440_index_extreme/` | 가능 |
| `docs/research/원달러_ETF_등가성.md` | :9 | `20260824_104655_usdkrw_equivalence/` | 가능 |
| `docs/research/달러_조달_방식.md` | :7 · :84 · :461 | `20260826_112619_usdkrw_grid/` | **불가 (코드 삭제)** |
| `docs/strategy/원달러_그리드.md` | :459 · :468 | `<실행시각>_usdkrw_grid/` · `_usdkrw_grid_robustness/` | **불가 (코드 삭제)** |
| `docs/strategy/역방향_매매_규칙.md` | :8 | `20260831_105540_reverse_trading/` | 가능 |
| `docs/strategy/옵션_만기일_매매_규칙.md` | :8 · :355 | `20260903_101851_expiry_trading/` | 가능 |
| `docs/research/레버리지_ETF_괴리.md` | :6 | "2026-09-05 10:32 실행" — **폴더명 없음** | 가능 |
| `docs/research/선물_대_레버리지_ETF.md` | :9 | "2026-09-05 21:59" — **폴더명 없음** | 가능 |
| `docs/spec/usdkrw_grid.md` | :78 · :130-131 | 프로브 3개 | 스크립트로 가능 |

> 뒤의 둘은 **폴더 이름 자체를 안 적고** 실행 시각만 문장으로 남겨 1차 조사에서 빠졌다.
> Phase 3 에서 나머지와 같은 형식(머리말의 `근거 산출물` 경로)으로 통일한다.

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절과 「측정의 원칙」
- `.claude/rules/docs.md` — 문서 종류와 SoT 역할, 수치에 데이터 기간을 붙이는 규칙
- `.claude/rules/research.md` — 결과 문서의 「관련 파일」 표 규칙
- `.claude/rules/session-bootstrap.md` — §6 이 이번 변경의 직접 대상
- `.claude/rules/context.md` — `docs/context/` 를 손대지 않는 근거
- `.claude/rules/strategy.md` — `docs/strategy/` 문서를 고칠 때
- `tests/CLAUDE.md` — Phase 4 에서 테스트를 추가한다면 §5(파일 격리)와 충돌 여부를 먼저 판단

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] `.gitignore` 가 `storage/results/meta.json` 만 제외한다
- [x] 「git 제외」를 전제한 규칙·지도·코드 서술 7곳이 사실에 맞게 고쳐졌다
- [x] 정책이 뒤집힌 본문 서술(결과·스펙 문서)이 고쳐졌다
- [ ] 근거가 끊긴 문서 8개가 **실재하는 폴더**를 가리킨다 (복구 불가한 것은 그 사실을 명시)
- [ ] 재발 방지 장치를 넣었거나, **넣지 않기로 한 근거가 문서에 남았다**
- [ ] 회귀/신규 테스트 추가 (또는 추가하지 않은 근거를 Notes 에 기록)
- [ ] `poetry run python validate_project.py` 통과 (failed=0, skipped=0; passed/failed/skipped 수 기록)
- [ ] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [ ] 필요한 문서 업데이트(`docs/COMMANDS.md` / CLAUDE.md / plan 등 — 각각 변경 여부 명시)
- [ ] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 근거·실측 수치를 루트 `CLAUDE.md` 의 프로젝트 설정 절이 정한 목적지로 이관.
      `/impl-plan` 스킬 "근거 승격" 참고)
- [ ] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

**Phase 1 — 정책 전환 (A PC · 완료)**

- `.gitignore` — 27줄 `storage/results/` → `storage/results/meta.json`, 주석 개정
- `docs/INDEX.md` — :167 표의 git 열
- `CLAUDE.md` — :417 디렉토리 트리 주석
- `.claude/rules/session-bootstrap.md` — §6 전체 (제목 포함)
- `.claude/rules/research.md` — :82
- `src/verify_lab/CLAUDE.md` — :185 표의 git 열
- `src/verify_lab/common_constants.py` — :31 주석 (**정책을 서술하는 소스 주석**)
- `tests/test_common_constants.py` — :45 docstring (같은 정책을 테스트가 계약으로 들고 있다)

**Phase 2 — 뒤집힌 본문 서술 (A PC · 완료)**

- `docs/research/지수_극단_이벤트.md` — :133
- `docs/research/연속_등락.md` — :114 · :527
- `docs/spec/index_extreme_events.md` — :530
- `docs/strategy/역방향_매매_규칙.md` — :356 (검토 후 판단)

**Phase 3 — 근거 재조준 (B PC)**

- 위 「근거가 끊긴 문서 8개」 표의 파일 전부

**Phase 4 — 재발 방지와 최종 검증 (B PC)**

- `tests/test_research_docs.py` 또는 대체 수단 (승인 후 결정)
- `tests/CLAUDE.md` — §5 예외를 두기로 하면

**`docs/COMMANDS.md`: 변경 없음** — 실행 명령어와 CLI 옵션이 바뀌지 않는다.
:83·:258·:313 등의 `storage/results/<실행시각>_*` 서술은 산출물이 생기는 위치를 말하는 것이라
동기화 여부와 무관하게 그대로 유효하다.

### 데이터/결과 영향

- **산출물·시세 파일의 내용은 한 글자도 바뀌지 않는다.** 추적 여부만 바뀐다
- 측정 결과·판정에 영향 없음. 검증을 다시 돌리지 않는다
- 저장소 크기: git 저장 약 **+15M** (현재 `.git` 16M → 약 31M). 클론·최초 fetch 가 그만큼 길어진다
- 이후 전체 재실행을 커밋할 때마다 비슷한 크기가 누적된다 — **재실행 결과를 무조건 커밋하지 않는다**는
  운용 습관이 필요하며, 그 근거를 Phase 1 에서 `.gitignore` 주석과 규칙 문서에 남긴다

## 6) 단계별 계획(Phases)

### Phase 1 — 정책 전환: `.gitignore` 와 규칙·지도 문서 (A PC · 완료)

**작업 내용**:

- [x] `.gitignore` 26~27줄을 고친다 — `storage/results/` 제외를 걷고 `storage/results/meta.json` 만 남긴다.
      **주석에 세 가지를 적는다**: ① 왜 동기화하는가(결과 문서가 근거로 인용한다)
      ② 왜 `meta.json` 만 빼는가(실행마다 전체 재작성 → 두 PC 충돌, 순환 저장이라 보존 가치 없음)
      ③ 재실행 산출물을 무조건 커밋하지 않는다(누적 경고)
- [x] `docs/INDEX.md` :167 — git 열 「제외 (재생성 가능)」 → 동기화. `meta.json` 예외를 같은 행에 적는다
- [x] `CLAUDE.md` :417 — 트리 주석 「검증 실행 결과 (git 제외, 재생성 가능)」 수정
- [x] `src/verify_lab/CLAUDE.md` :185 — 「데이터 저장 규칙」 표의 git 열 수정
- [x] `.claude/rules/session-bootstrap.md` §6 — **절 전체가 「넘어가지 않는다」를 전제**하므로 다시 쓴다.
      제목부터 바꾸고, 「그 PC 에서 검증을 다시 실행해야 한다」를 걷어낸다.
      **다만 「재수집하면 기존 수치가 재현되지 않는다」는 경고는 유지한다** — 그것은 git 정책과 무관하게 참이다
- [x] `.claude/rules/research.md` :82 — 「git 제외라 다른 PC 에 없고 주기적으로 지워진다」가 근거로 성립하지 않는다.
      **「관련 파일」 표에 넣지 않는다는 규칙 자체는 유지**하되(:80 이 이미 "실행 산출물 폴더는 머리말이 담당한다"고
      정했으므로 중복 방지가 진짜 이유다), 근거 문장을 그것으로 바꾼다
- [x] `src/verify_lab/common_constants.py` :31 — 「언제든 재생성 가능하므로 git 에서 제외한다」는
      **경로 상수 옆에 붙은 정책 서술**이다. 코드를 읽는 사람이 가장 먼저 보는 자리이므로 함께 고친다
- [x] `tests/test_common_constants.py` :45 — docstring 이 같은 정책을 「고정하는 계약」으로 적고 있다.
      **테스트가 검사하는 것은 경로 위치뿐**이므로 assert 는 그대로 두고 목적 문장만 고친다

**Validation**:

- [x] `grep -rn "git 제외\|git 에서 제외\|제외 (재생성 가능)" .claude/rules/ CLAUDE.md docs/INDEX.md src/ tests/`
      결과가 **0건**이거나, 남은 것이 `storage/results` 와 무관한 문맥(자격증명 `.env` 등)임을 확인한다
- [x] `git check-ignore -v storage/results/20260906_080223_index_extreme/summary.json` 이 **무시되지 않음**을 보인다
- [x] `git check-ignore -v storage/results/meta.json` 이 **무시됨**을 보인다

---

### Phase 2 — 정책이 뒤집힌 본문 서술 정리 (A PC · 완료)

> 여기서는 **근거 폴더를 다시 겨누지 않는다.** 「git 제외라서 없다」는 서술만 고친다.
> 어느 폴더를 가리킬지는 B PC 의 조사 결과가 있어야 정해진다 (Phase 3).

**작업 내용**:

- [x] `docs/research/지수_극단_이벤트.md` :133 — 「git 에서 제외돼 있으므로, 없으면 재실행」 →
      동기화 대상이 됐음을 반영. 재실행 안내는 남기되 전제를 고친다
- [x] `docs/research/연속_등락.md` :114 — 「git 제외라 남아 있지 않을 수 있고」 부분만 고친다.
      **「코드가 제거돼 재생성할 수 없다」는 그대로 유효**하고, 이 검증의 산출물은 실제로 저장소에 없다
- [x] `docs/research/연속_등락.md` :527 — 「CSV 경로를 적을 수 없다」의 사유 갱신
- [x] `docs/spec/index_extreme_events.md` :530 — 「재생성 가능, git 제외」 수정
- [x] `docs/strategy/역방향_매매_규칙.md` :356 검토 — 「`storage/results/`가 사라져도 이 절만으로
      판단을 재구성할 수 있어야 합니다」는 **동기화 후에도 유효한 원칙**이다. 고칠 필요가 없으면 그대로 두고
      판단 근거를 진행 로그에 남긴다

**Validation**:

- [x] `grep -rn "git 제외\|git 에서 제외\|git 에서 빠져" docs/research/ docs/spec/ docs/strategy/`
      결과에 남은 행이 없거나, 남았다면 그것이 옳은 서술임을 행 단위로 확인한다
- [x] Phase 2 에서 **근거 산출물 경로를 바꾸지 않았음**을 `git diff` 로 확인한다

---

### Phase 3 — 산출물 합류와 근거 재조준 (B PC — 이 계획서를 pull 받은 PC)

> **선행 조건**: Phase 1·2 가 커밋·푸시돼 있고, A PC 의 `storage/results` 가 올라가 있어야 한다.
> 이 계획서가 손에 있다면 그 조건은 이미 충족된 것이다.

**작업 내용**:

- [ ] `git pull` 후 아래를 실행해 **이 PC 에만 있는 폴더**를 가려낸다.
      위 「A PC 가 올린 산출물 폴더 11개」에 없는 이름이 그것이다

      ```bash
      ls storage/results/
      git status --short --untracked-files=all -- storage/results
      ```
- [ ] 살아남은 폴더를 커밋한다. **특히 `20260826_112619_usdkrw_grid`** — 코드가 삭제돼 재생성이 불가능하므로
      여기 없으면 그 근거는 영영 복구되지 않는다
- [ ] 고아 폴더 2개(`20260906_094153`·`20260906_094451_kosdaq_month_end`)를 어떻게 할지 **사용자가 결정**한다.
      삭제하기로 하면 무엇을 지우는지 목록을 먼저 보이고 승인받는다
- [ ] 「근거가 끊긴 문서 8개」를 실재하는 폴더로 다시 겨눈다. 갈림길이 둘이다
      - **옛 폴더가 살아 있으면** — 그 폴더를 가리키고 수치는 그대로 둔다. 그 실행의 값이라 완전히 맞는다
      - **없으면** — 현재 실행으로 겨누고 **수치가 달라졌는지 대조한 뒤 달라진 것을 문서에 적는다**
        (`.claude/rules/docs.md` 「수치를 적을 때는 데이터 기간을 함께 적는다」)
- [ ] `docs/research/레버리지_ETF_괴리.md`·`docs/research/선물_대_레버리지_ETF.md` 의 머리말을
      **실행 시각 문장이 아니라 폴더 경로**로 통일한다
- [ ] 복구 불가한 `usdkrw_grid` 두 문서는 **근거를 붙일 수 없다는 사실과 그 이유**(2026-08-30 코드 삭제)를
      본문에 명시한다. 없는 경로를 그대로 두지 않는다

**Validation**:

- [ ] `grep -rhoE "storage/results/[0-9]{8}_[0-9]{6}_[a-z_]+" docs/ | sort -u` 의 모든 경로가 실재한다
      (복구 불가로 명시한 것은 경로를 지웠으므로 목록에 없어야 한다)
- [ ] 문서에 적힌 CSV 파일명이 해당 폴더에 실재한다

---

### 마지막 Phase — 재발 방지 장치와 최종 검증 (B PC)

**작업 내용**

- [ ] **재발 방지 장치를 결정하고 반영한다.** 후보와 쟁점은 아래 표에 있으며, **사용자 승인 후** 하나를 고른다
- [ ] 필요한 문서 업데이트 (`docs/COMMANDS.md` 변경 없음 — 실행 명령어·CLI 옵션 불변)
- [ ] 자동 포맷 적용 — `poetry run black .`
- [ ] 변경 기능 및 전체 플로우 최종 검증
- [ ] DoD 체크리스트 최종 업데이트 및 체크 완료
- [ ] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**재발 방지 장치 후보**

| 안 | 내용 | 쟁점 |
| --- | --- | --- |
| A | `tests/test_research_docs.py` 에 **머리말의 근거 산출물 경로 실재 검사**를 추가 | **`tests/CLAUDE.md` §5 「테스트에서 `storage/` 실경로 접근 금지」와 정면 충돌**한다. 예외를 두려면 그 규칙을 함께 고쳐야 한다. 대신 가장 확실하다 — 인용한 폴더를 지우는 순간 `validate_project.py` 가 실패한다 |
| B | 규칙 문서에 **「결과 문서가 인용한 산출물 폴더는 지우지 않는다」**만 적는다 | 규칙 충돌이 없다. 대신 강제력이 없어 같은 사고가 반복될 수 있다 — 이번 8건이 그 증거다 |
| C | A + B 를 함께 | 규칙과 집행이 같이 간다. 작업량이 가장 크다 |

> **판단 재료**: 이 저장소는 이미 `tests/test_index.py`(문서 지도)와 `tests/test_research_docs.py`
> (관련 파일 표)로 **문서 부패를 기계로 잡는 관용**을 갖고 있다. §5 의 취지는 "테스트가 실제 데이터를
> 읽거나 쓰지 말라"이지 "실재 여부도 보지 말라"가 아닐 수 있으므로, 예외 문구를 좁게 쓰면 A 가 가능하다.

**Validation**:

- [ ] `poetry run python validate_project.py` (passed=\_\_, failed=\_\_, skipped=\_\_)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 하네스 / storage/results 를 git 동기화 대상으로 전환하고 meta.json 만 제외
2. 하네스 / 검증 산출물을 저장소에 넣어 결과 문서의 근거가 다른 PC 에서도 열리게 함
3. 문서 / 산출물 동기화 정책 전환에 맞춰 규칙·지도·본문 서술을 사실에 맞춤
4. 하네스 / 산출물 동기화 전환 + 근거가 끊긴 결과 문서 재조준
5. 하네스 / 결과 문서가 인용한 산출물이 사라지지 않게 동기화 정책을 바꾸고 규칙을 세움

## 7) 리스크(Risks)

| 리스크 | 크기 | 완화 |
| --- | --- | --- |
| 저장소가 약 15M 커진다 | 중 | 최대 파일 4.2M 로 GitHub 제한과 무관. **재실행 산출물을 무조건 커밋하지 않는다**는 경고를 `.gitignore` 주석과 규칙에 남긴다 |
| B PC 에 옛 폴더가 없으면 근거를 못 살린다 | 중 | 특히 `usdkrw_grid` 는 재생성 불가. 그 경우 **복구 불가 사실을 문서에 명시**하는 것이 유일한 처리이며 Phase 3 에 넣어 뒀다 |
| 재조준 과정에서 문서 수치와 새 산출물이 어긋난다 | 중 | 옛 폴더가 없으면 **대조 후 달라진 것을 적는다**. 수치를 조용히 갈아끼우지 않는다 (`.claude/rules/docs.md`) |
| 재발 방지 A 안이 `tests/CLAUDE.md` §5 와 충돌 | 중 | 마지막 Phase 에서 **사용자 승인 후** 결정. 규칙을 고칠 것인지부터 묻는다 |
| 두 PC 가 같은 파일을 동시에 고쳐 충돌 | 소 | 산출물 폴더는 실행 시각으로 갈려 충돌하지 않는다. `meta.json` 은 제외했다. 문서는 Phase 로 PC 를 갈라 뒀다 (A PC 는 Phase 1·2, B PC 는 Phase 3·4) |
| Phase 2 에서 근거 경로까지 손대 Phase 3 과 겹친다 | 소 | Phase 2 Validation 에 `git diff` 확인을 넣어 뒀다 |

## 8) 메모(Notes)

- **`docs/context/` 의 `storage/results/backtest/`·`storage/results/portfolio/` 는 이 저장소의 경로가 아니다.**
  이전 프로젝트의 산출물을 가리키며, 사용자 소유 문서라 손대지 않는다 (`.claude/rules/context.md`)
- `docs/research/옵션_만기일.md` :10 은 타임스탬프 대신 **`최신 *_option_expiry 폴더` 패턴**을 써서
  이번 사고를 혼자 피했다. 다만 어느 실행이 그 수치를 냈는지는 알 수 없으므로,
  동기화 후에는 **정확한 폴더명이 더 낫다** — Phase 3 에서 함께 볼 것
- `storage/results/20260906_080407_expiry_trading` 은 `meta.json` 에만 있고 디스크에 없다.
  같은 날 `080410` 이 3초 뒤에 다시 돌아 대체한 것으로 보인다. **문서가 인용하지 않으므로 이번 범위 밖**이다

### 진행 로그 (KST)

- 2026-09-06 21:48: 계획서 작성. `.gitignore`·규칙 5곳·본문 4곳·문서 8개·재발 방지의 5묶음으로 범위 확정.
  사용자 결정 반영 — 전체 추적 / `meta.json` 제외 / `windows_*.csv` 포함 / 고아 폴더는 다른 PC 에서 결정
- 2026-09-06 21:52: 자체 검증에서 **범위 누락 2건**을 찾아 Phase 1 에 넣었다 —
  `src/verify_lab/common_constants.py` :31 주석과 `tests/test_common_constants.py` :45 docstring 이
  같은 정책을 서술하고 있었다. **문서만 훑으면 코드에 박힌 정책 서술을 놓친다**는 것이 이번 교훈이라,
  Phase 1 Validation 의 grep 범위를 `src/`·`tests/` 까지 넓혔다
- 2026-09-06 21:55: **Phase 1 완료.** `.gitignore` 전환 + 7곳 갱신. 검증 셋 다 통과 —
  잔존 grep 3건은 전부 정당한 문맥(`session-bootstrap.md` §6 의 「전에는 git 제외라」 과거 서술 1건,
  `.env` 자격증명 2건)이고, `git check-ignore` 가 산출물은 `exit=1`(추적) · `meta.json` 은 `exit=0`(제외)이다
- 2026-09-06 21:56: **Phase 2 완료.** 네 곳을 고쳤고 **`docs/strategy/역방향_매매_규칙.md` :356 은
  고치지 않기로 판단**했다 — 「`storage/results/`가 사라져도 이 절만으로 판단을 재구성할 수 있어야 합니다」는
  git 정책을 말하는 문장이 아니라 **문서 자립 원칙**이고, 동기화 후에도 참이다
  (`.claude/rules/strategy.md` 「핵심 결론은 요약해 복사한다 — 그쪽이 개정돼도 이 문서가 자립해야 한다」와 같은 취지).
  Validation 2건 통과 — 본문 grep 0건, `git diff` 에서 근거 산출물 경로 변경 0건
- 2026-09-06 21:57: 표적 테스트로 상태 확인 — `test_index.py`·`test_research_docs.py`·`test_common_constants.py`
  **91 passed**. 전체 품질 검증은 규칙대로 마지막 Phase(B PC)에서 돌린다
- 2026-09-06 22:02: **B PC 단독 진행이 가능하도록 자립화했다.** Context 맨 앞에 「이 계획서만 받고 시작하는
  세션에게」를 넣어 진입 순서·현재 상태·A PC 가 올린 폴더 11개 목록·하지 말 것을 담았고,
  Phase 표기를 「이 PC / 다른 PC」에서 **A PC / B PC** 로 바꿨다 — 읽는 쪽이 바뀌면 두 말이 뒤집힌다.
  Phase 3 첫 항목에 실행할 명령을 직접 넣었다

---
