# Implementation Plan: docs 재편과 세션 부트스트랩 도입

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

**작성일**: 2026-09-05 18:49
**마지막 업데이트**: 2026-09-05 19:32
**관련 범위**: 문서(docs 전반), 하네스(`.claude/`), 테스트
**관련 문서**: `CLAUDE.md`, `src/verify_lab/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/docs.md`, `.claude/rules/python.md`, `.claude/rules/context.md`

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

- [x] 목표 1: **세션 시작 시 `docs/INDEX.md` 를 읽고 관련 문서로 이어가는 경로를 하네스가 보장한다.**
      `paths` 없는 `.claude/rules/session-bootstrap.md`(항상 로드)와 SessionStart 훅 두 겹으로 만든다
- [x] 목표 2: **`docs/` 에서 「앞으로의 계획」을 전부 제거하고 「현재 상태 + 분석 결과」만 남긴다.**
      `ROADMAP.md`·`HANDS_ON.md`·`다음세션_프롬프트.md`·`plans/` 13개를 삭제한다
- [x] 목표 3: **삭제 대상에만 있던 근거를 살아있는 문서로 승격한다.**
      계층 간 계약 8종·실측 기록 2종·코드 교훈 3종·검산 결과·집행 조건을 잃지 않는다
- [x] 목표 4: **규칙 문서를 `.claude/` 로 모은다.** `docs/research/CLAUDE.md` 를 `.claude/rules/research.md` 로 옮겨
      `docs/` 에 규칙이 남지 않게 한다

## 2) 비목표(Non-Goals)

- **`docs/research/`·`docs/spec/`·`docs/strategy/` 의 문서를 삭제하거나 축소하지 않는다.**
  사용자가 보존을 지정했다. 승격에 따른 **내용 추가**와 **깨진 링크 수정**만 한다
- **`docs/context/` 를 수정하지 않는다.** 사용자 소유 문서다 (`.claude/rules/context.md`).
  단 `context/README.md:64` 가 `docs/research/CLAUDE.md` 를 인라인 코드로 언급하므로
  **그 한 줄만 사용자 승인을 받아 경로를 갱신한다** (Risks 참고)
- **`reference/` 를 수정하지 않는다.** 읽기 전용 4금지 폴더다 (`.claude/rules/reference.md`).
  `reference/데이터처리_설계원칙.md`·`reference/pykrx_실측기록.md` 에 ROADMAP 참조가 있으나
  **verify-lab 의 것이 아니다** — "Phase 4 증분 업데이트"·"Phase 6" 은 이 저장소에 없는 번호이고,
  `pykrx_실측기록.md:9` 의 `[ROADMAP.md](ROADMAP.md)` 는 이미 깨진 상대 링크다(이관 문서의 원래 상태)
- 측정 로직·산출물·판정 기준을 바꾸지 않는다. **이 작업으로 어떤 수치도 달라지지 않는다**
- `docs/spec/usdkrw_grid.md`(169KB, 종료된 트랙)를 정리하지 않는다. 보존 지정 폴더다
- 검증 #1 결과 문서를 단기 구간으로 개정하지 않는다 (별도 작업이며, 이 계획서는 그 **미착수 항목을 삭제**한다)

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

**① 세션 시작 시 문서 지도가 읽히지 않는다.**
루트 `CLAUDE.md` 가 "저장소 전체의 문서 지도는 `docs/INDEX.md`" 라고 **가리키기만** 하고 강제하지 않는다.
이 계획서를 만든 세션이 실증이다 — INDEX 를 열지 않은 채 작업이 시작됐다.
기존 진입점인 `다음세션_프롬프트.md` 는 **사용자가 첫 메시지에 붙여넣을 때만** 작동한다.

**② `docs/` 가 「앞으로의 계획」으로 부풀어 있다.** (실측)

| 항목 | 실측값 |
| --- | --- |
| `docs/` 전체 | 1,350KB |
| `docs/plans/` | **13개 292KB (22%)** — 규칙상 "주기적으로 전부 삭제"인데 비워지지 않았다 |
| `docs/ROADMAP.md` | 817줄 82KB — 그중 Phase 0~3 작업 일지가 453줄(55%) |
| `docs/HANDS_ON.md` | 660줄 31KB — 검증 #1 전용이며 대조가 2026-08-20 에 8단계 전부 통과로 끝났다 |
| `다음세션_프롬프트.md` | 7.2KB — 전 항목의 원본이 다른 문서에 있다(grep 전수 확인) |

**③ 계획서 상태 표기가 실제와 어긋나 있다.**
`PLAN_futures_leverage.md`(검증 #9 완료됨)와 `PLAN_global_impl_plan_skill.md`(`/verify-plan`→`/impl-plan` 이전 완료됨)가
🔄 In Progress 로 남아 있다. 후자는 본문이 **존재하지 않는 `.claude/hooks/`** 를 가리킨다.

**④ 규칙 문서가 `docs/` 와 `.claude/` 로 갈라져 있다.**
`docs/research/CLAUDE.md`(8.6KB)만 `docs/` 안에 있다.

### 확정된 결정 (사용자 승인 완료)

| # | 결정 | 근거 |
| --- | --- | --- |
| ① | 부트스트랩은 **rules + SessionStart 훅 두 겹** | rules 는 git 추적돼 여러 PC 로 따라가고, 훅은 세션 머리에서 한 번 더 지시한다 |
| ② | `@docs/INDEX.md` import 는 **쓰지 않는다** | 공식 문서: *"imported files still load and enter the context window at launch"* — 매 세션 18.6KB 를 태우면서 그 다음 문서(ROADMAP·context)로 이어지는 것은 보장하지 못한다 |
| ③ | **검증 대상 목록도 제거** | 미착수 #2·#3·#4 는 앞으로의 계획이다. 무엇을 잴지는 그때 사용자가 정한다 |
| ④ | `HANDS_ON.md` **삭제** | 사용자용 검산서이고 검증 #1 대조가 8단계 전부 통과로 끝났다. 이후 검증 #7·#8·#9 에는 만들지 않았다 |
| ⑤ | 「검증 #1 대조 8단계 통과」 검산 결과는 **`research/지수_극단_이벤트.md` 로 이전** | 계획이 아니라 분석 결과다 |
| ⑥ | 「이미 밟은 함정」 13항목은 **옮기지 않고 버린다** | 전수 대조 결과 원본이 전부 있다. 복사하면 두 벌이 되고 한쪽이 낡는다 |
| ⑦ | 예외로 **`storage/results/` 가 git 제외라는 사실의 함의**만 rules 로 이전 | "다른 PC 에서 결과 문서를 쓰려면 재실행해야 하고 시세를 재수집하면 안 된다"는 어디에도 없다 |

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」·「계획서의 수명」·「측정의 원칙」
- `.claude/rules/docs.md` — 문서의 두 종류, 아카이브 폴더 금지, 계획서 규정
- `.claude/rules/context.md` — 사용자 소유 문서 보호
- `.claude/rules/python.md` — 승격 목적지 중 하나
- `src/verify_lab/CLAUDE.md` — 계층 계약의 승격 목적지
- `tests/CLAUDE.md` — 테스트를 추가·수정하므로
- `docs/research/CLAUDE.md` — 이동 대상 본인

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 기능 요구사항 충족 — 목표 1~4 전부
- [x] 회귀/신규 테스트 추가 — `tests/test_index.py` 갱신, 부트스트랩 규칙 존재 계약 추가
- [x] `poetry run python validate_project.py` 통과 (passed=834, failed=0, skipped=0)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트(`docs/COMMANDS.md` / CLAUDE.md / plan 등 — 각각 변경 여부 명시)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 근거·실측 수치를 루트 `CLAUDE.md` 의 프로젝트 설정 절이 정한 목적지로 이관.
      `/impl-plan` 스킬 "근거 승격" 참고)
- [x] **승격 대상 17건이 전부 새 위치에서 확인된다** —
      계층 계약 8 + 실측 기록 2 + 코드 교훈 3 + 검산 결과 1 + 집행 조건 1 + 계획서 승격 목적지 1 +
      `storage/results` 함의 1 (Phase 1·2 표 기준)
- [x] **`docs/plans/.gitkeep` 이 존재한다** — 폴더가 사라지면 계획서 게이트 훅이 조용히 꺼진다
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

**신설**

- `.claude/rules/session-bootstrap.md` — `paths` 없음(항상 로드)
- `.claude/rules/research.md` — `paths: docs/research/**`
- `.claude/settings.json` — SessionStart 훅. **git 추적 대상**(현재 저장소에 settings.json 없음)
- `docs/plans/.gitkeep`

**삭제**

- `docs/ROADMAP.md`
- `docs/HANDS_ON.md`
- `다음세션_프롬프트.md`
- `docs/research/CLAUDE.md` (→ `.claude/rules/research.md` 로 이동)
- `docs/plans/PLAN_*.md` **13개** (이 계획서 제외)

**수정**

- `CLAUDE.md` (루트) — ROADMAP 7곳 + research CLAUDE.md 3곳, 집행 조건 흡수, 세션 인계 규칙 절 교체, 디렉터리 구조
- `README.md` — ROADMAP 링크 1곳
- `src/verify_lab/CLAUDE.md` — 계층 간 계약 8종 흡수
- `scripts/CLAUDE.md` — ROADMAP 참조 1곳
- `tests/CLAUDE.md` — 코드 교훈 2종 흡수
- `.claude/rules/docs.md` — 계획서 승격 목적지 흡수, 참조 5곳
- `.claude/rules/python.md` — 코드 교훈 1종 흡수, 참조 1곳
- `docs/INDEX.md` — 삭제분 제거, 새 규칙 2종 등록, 진입점 교체
- `docs/COMMANDS.md` — 참조 2곳, 죽은 절(원달러 그리드 코드 삭제됨) 정리
- `docs/research/지수_극단_이벤트.md` — 검산 결과 흡수, 참조 3곳
- `docs/research/레버리지_ETF_괴리.md` · `선물_대_레버리지_ETF.md` · `연속_등락.md` — 참조 각 1곳
- `docs/spec/option_expiry.md` · `docs/spec/index_extreme_events.md` — 참조 1곳 / 2곳
- `docs/context/README.md` — 참조 1곳 (**사용자 승인 필요**)
- `tests/test_index.py` — 필수 문서에서 ROADMAP 제거, 새 계약 추가
- `tests/test_research_docs.py` — SoT 주석 3곳

- `docs/COMMANDS.md`: **변경 있음** — 실행 명령어 자체는 바뀌지 않으나 ROADMAP 참조 2곳과
  실행 불가 절을 고친다. **새 명령어는 추가되지 않는다**

### 데이터/결과 영향

- **없음.** 측정 코드·산출물·판정 기준을 건드리지 않는다. `storage/` 를 읽지도 쓰지도 않는다
- 기존 결과 비교 불필요 — 재실행이 없다

## 6) 단계별 계획(Phases)

### Phase 0 — 새 문서 구조를 테스트로 먼저 고정(레드)

**작업 내용**:

- [x] `tests/test_index.py` 의 `test_core_documents_linked` 필수 목록에서 `docs/ROADMAP.md` 제거
- [x] 같은 파일에 **부트스트랩 규칙 계약** 추가 — `.claude/rules/session-bootstrap.md` 가 존재하고
      `paths` frontmatter 를 갖지 않는다(= 항상 로드된다)
- [x] **삭제 대상 부재 계약** 추가 — `docs/ROADMAP.md`·`docs/HANDS_ON.md`·`다음세션_프롬프트.md`·
      `docs/research/CLAUDE.md` 가 존재하지 않는다
- [x] `docs/plans/.gitkeep` 존재 계약 추가
- [x] 레드 확인 — **7 failed, 5 passed** (2026-09-05 19:04)

> **주의**: `test_all_documents_registered` 는 `docs/`·`reference/` 만 본다. `.claude/` 는 대상이 아니므로
> 새 규칙 파일은 INDEX 등록 **의무**가 없지만, 루트 `CLAUDE.md` 가 §2 표 등록을 규정하므로 등록한다.

---

### Phase 1 — 근거 승격(그린 유지, 문서만 수정)

삭제 전에 옮긴다. **순서가 안전장치다** — 승격이 끝나기 전에 원본을 지우지 않는다.

**작업 내용**:

- [x] **계층 간 계약 8종 → `src/verify_lab/CLAUDE.md`**

  | # | 원본 (ROADMAP 줄) | 내용 |
  | --- | --- | --- |
  | 1 | 253~306 | 확정된 원시 시세 저장 규칙 |
  | 2 | 307~336 | forward return 반환 계약 |
  | 3 | 337~365 | 베이스라인·통계 계약 |
  | 4 | 366~381 | 출력 계약 |
  | 5 | 560~575 | 이벤트 정의 계약 |
  | 6 | 576~605 | 실행 계층 계약 |
  | 7 | 606~615 | 데이터 계층 계약 (`storage/series/`·`Value` 컬럼·ECOS 비밀값) |
  | 8 | 634~642 | 이벤트 없는 검증 계약 |

  **8종 전부 유효함을 코드로 확인했다** — `storage/series/` 존재, `ecos_collector.py`·`fred_collector.py` 존재,
  `studies/usdkrw_equivalence/` 존재. 기존 「studies의 계약」·「데이터 저장 규칙」 절에 흡수한다

> **실측 기록 2종과 `storage/results` 함의는 Phase 2 에 있다.** 목적지 파일이 아직 없기 때문이며,
> 그 셋을 합쳐 승격 대상은 17건이다.

- [x] **코드 교훈 3종 승격**

  | 원본 (ROADMAP 줄) | 내용 | 목적지 |
  | --- | --- | --- |
  | 731~745 | 미사용 판정에는 「왜 안 쓰이는가」가 함께 필요하다 (연결을 빠뜨린 것을 지우면 하드코딩이 정답으로 굳는다) | `.claude/rules/python.md` |
  | 746~751 | 묶음 상수를 쓰면 테스트의 patch 대상이 늘어난다 | `tests/CLAUDE.md` |
  | 752~758 | 픽스처가 버그와 같은 가정을 하면 그 버그는 영원히 안 잡힌다 | `tests/CLAUDE.md` |

- [x] **분석 결과 → `docs/research/지수_극단_이벤트.md`**
      ROADMAP 488~516 「사용자 직접 대조 진행 상태」 — 8단계 전부 통과(2026-08-20), 검산 5종
      (84칸 전부 일치·사건 3개·베이스라인 승률 85.82%·QQQ 테스트 A 1,080칸 전부 검정 불가·KODEX 27줄).
      **보존 지정 폴더이므로 내용 추가만 한다**

- [x] **집행 조건 → 루트 `CLAUDE.md`**
      ROADMAP 101~121 — 수수료 우대 0.1%(일반 0.25%)·슬리피지 편도 0.1%·왕복 0.4%/0.7%·레버리지 2~3배,
      "ETF 총보수는 넣지 않는다(종가에 녹아 있다)". 측정의 원칙 10 옆에 둔다

- [x] **계획서 승격 목적지 → `.claude/rules/docs.md`**
      ROADMAP 801~817 의 표를 기존 「계획서」 절에 흡수한다 (현재 축약 포인터만 있다)

---

### Phase 2 — 부트스트랩 신설과 규칙 이동(그린 유지)

**작업 내용**:

- [x] `.claude/rules/session-bootstrap.md` 신설 — **`paths` frontmatter 를 두지 않는다**(항상 로드)

  담을 것은 넷뿐이다. **지식을 쌓지 않고 경로를 가리킨다**:

  1. **무조건**: 첫 실질 작업 전에 `docs/INDEX.md` 를 **`Read` 도구로** 연다
  2. **조건부**: 검증·코드·결과 문서 작업이면 `docs/spec/<검증명>.md` 와 `docs/context/` 로 이어 읽는다.
     하네스 설정·단순 질의응답이면 1 에서 멈춘다
  3. **함정은 각 검증의 `docs/spec/` 에 있다** — 「데이터 실측 기록」·「확정된 설계 결정」을 본다
  4. **승격 3건** (목적지가 이 파일이라 Phase 1 이 아니라 여기 있다)

     | 원본 | 내용 |
     | --- | --- |
     | ROADMAP 154~200 | `.claude/rules/` 자동 로드 실측 — 트리거는 `Read` 도구, 구멍 1(새 파일)·구멍 2(셸 읽기), **auto 모드가 셸 읽기를 권장해 규칙이 한 번도 안 걸릴 수 있다** |
     | ROADMAP 201~215 | `poetry run` 이 다른 가상환경을 잡는 경우 — `VIRTUAL_ENV` 잔류 시 Ruff·PyRight·Pytest 가 **전부 실패로 보인다.** 품질 게이트가 통과하는데도 실패로 보이는 유일한 알려진 경로다 |
     | `다음세션_프롬프트.md` | `storage/results/` 는 git 제외라 다른 PC 로 넘어가지 않는다. 결과 문서를 쓰려면 그 PC 에서 재실행해야 하고 **시세를 재수집하면 안 된다**(수치가 재현되지 않는다) |

- [x] `.claude/settings.json` 신설 — SessionStart 훅 (`matcher: "startup|clear"`)
      `.claude/rules/session-bootstrap.md` 를 **가리키기만** 하고 내용을 복사하지 않는다
- [x] `docs/research/CLAUDE.md` → `.claude/rules/research.md` 이동 (`paths: docs/research/**`)
- [x] `tests/test_research_docs.py` 의 SoT 주석 2곳(6·19줄) 경로 갱신
- [x] `docs/plans/.gitkeep` 생성

---

### Phase 3 — 삭제와 참조 수정(그린 유지)

**작업 내용**:

- [x] `docs/ROADMAP.md` 삭제
- [x] `docs/HANDS_ON.md` 삭제
- [x] `다음세션_프롬프트.md` 삭제
- [x] `docs/plans/PLAN_*.md` 13개 삭제 (이 계획서는 남긴다)
- [x] **참조 수정** — 아래가 전수다 (`grep -rn` 전수 집계, `reference/` 제외)

  | 파일 | 곳 | 대상 | 어디로 |
  | --- | --- | --- | --- |
  | `CLAUDE.md` | 213·262·278·284·319·342·377줄 | ROADMAP | 새 위치. **「세션 인계 규칙」 절은 부트스트랩 규칙 안내로 교체** |
  | `CLAUDE.md` | 182·202·381줄 | `docs/research/CLAUDE.md` | `.claude/rules/research.md` |
  | `README.md` | 33줄 | ROADMAP | **검증 목록이 사라지므로 문장을 지운다** |
  | `scripts/CLAUDE.md` | 59줄 | ROADMAP 「G5 이후 트랙 종료」 | `docs/strategy/원달러_그리드.md` §2.8 |
  | `docs/INDEX.md` | 17·45·56·166줄 | ROADMAP | 새 위치 |
  | `docs/INDEX.md` | 21~23·74·35줄 | 다음세션_프롬프트 / HANDS_ON / research CLAUDE.md | 삭제·교체 |
  | `docs/COMMANDS.md` | 29·415줄 | ROADMAP | 29줄→부트스트랩 규칙, 415줄→`strategy/원달러_그리드.md` |
  | `.claude/rules/docs.md` | 14·24·38·75줄 | ROADMAP | 흡수한 새 위치 |
  | `.claude/rules/docs.md` | 27줄 | `docs/research/CLAUDE.md` | `.claude/rules/research.md` |
  | `.claude/rules/python.md` | 102줄 | ROADMAP | 새 위치 |
  | `docs/research/지수_극단_이벤트.md` | 44·794줄 | **HANDS_ON 링크** | **제거.** 안 하면 `test_research_docs.py::test_related_links_resolve` 실패 |
  | `docs/research/지수_극단_이벤트.md` | 19줄 | ROADMAP 「후속 작업으로 등록」 | **그 후속 작업이 삭제되므로 문장 재작성** |
  | `docs/research/레버리지_ETF_괴리.md` | 212줄 | ROADMAP 집행 조건 | 루트 `CLAUDE.md` |
  | `docs/research/선물_대_레버리지_ETF.md` | 424줄 | ROADMAP 링크 | 새 위치 |
  | `docs/research/연속_등락.md` | 522줄 | `docs/research/CLAUDE.md` | `.claude/rules/research.md` |
  | `docs/spec/option_expiry.md` | 202줄 | ROADMAP 「확정된 원시 시세 저장 규칙」 | `src/verify_lab/CLAUDE.md` |
  | `docs/spec/index_extreme_events.md` | 189줄 | ROADMAP 실행 계층 계약 | `src/verify_lab/CLAUDE.md` |
  | `docs/spec/index_extreme_events.md` | 467줄 | **HANDS_ON 링크** | 제거 |
  | `docs/context/README.md` | 64줄 | `docs/research/CLAUDE.md` | **사용자 승인 후** `.claude/rules/research.md` |
  | `tests/test_research_docs.py` | 6·19·240줄 | `docs/research/CLAUDE.md` SoT 주석 | `.claude/rules/research.md` |

  > **보존 지정 폴더(`research`·`spec`·`strategy`)도 참조 수정 대상이다.** 삭제가 아니라
  > **깨질 링크를 고치는 것**이며, 안 고치면 그 문서들이 없는 파일을 가리킨다.

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [x] `docs/INDEX.md` 재작성 — 삭제분 제거, `.claude/rules/` 2종 등록, §1 「처음 온 세션이 읽을 순서」를
      부트스트랩 규칙과 어긋나지 않게 맞춘다
- [x] `docs/COMMANDS.md` — 실행 불가 절(원달러 그리드, 코드 삭제됨) 정리
- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` 포함 — **변경 있음**, 참조 2곳과 죽은 절)
- [x] 자동 포맷 적용 — `poetry run black .`
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [x] `poetry run python validate_project.py` (passed=834, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 문서 / 앞으로의 계획을 걷어내고 현재 상태와 분석 결과만 남김 — 세션 부트스트랩 규칙 신설
2. 하네스 / 세션 시작 시 문서 지도를 먼저 읽도록 규칙과 SessionStart 훅을 추가
3. 문서 / ROADMAP·HANDS_ON·인계 프롬프트를 해체하고 계층 계약 8종을 코드 계층 문서로 승격
4. 문서 / 계획서 13개와 진행 일지를 비우고 근거만 살아있는 문서로 이관
5. 하네스 / 규칙 문서를 .claude 로 모으고 docs 를 결과 문서 전용으로 정리

## 7) 리스크(Risks)

| 리스크 | 완화 |
| --- | --- |
| **승격 누락** — 지운 뒤에 필요한 근거가 없어진다 | Phase 1 을 삭제(Phase 3)보다 **먼저** 둔다. DoD 에 「승격 13건 전부 새 위치에서 확인」을 명시 체크로 넣는다 |
| **`test_research_docs.py` 실패** — 보존 지정 문서가 HANDS_ON 을 링크 중이다 | Phase 3 참조 수정 표에 명시했다. 링크 제거는 삭제와 **같은 Phase** 에서 한다 |
| **계획서 게이트가 조용히 꺼진다** — `docs/plans/` 가 비면 폴더가 사라진다 | `.gitkeep` 을 Phase 2 에서 만들고 DoD 체크에 넣는다 |
| **SessionStart 훅이 워크스페이스 신뢰 프롬프트를 띄운다** | 정상 동작이다. 훅은 `echo` 한 줄이며 파일을 읽거나 쓰지 않는다 |
| **부트스트랩 규칙이 매 세션 컨텍스트를 먹는다** | 지식을 담지 않고 **경로만** 가리켜 2KB 안쪽으로 유지한다 |
| **`.claude/settings.json` 이 `settings.local.json` 과 겹친다** | 역할이 다르다 — local 은 권한(gitignore 대상), 신규 settings.json 은 훅(git 추적) |
| 사용자가 나중에 검증 #2·#3·#4 를 찾는다 | **의도된 삭제다**(결정 ③). 무엇을 잴지는 그때 정한다 |
| **`docs/context/README.md:64` 가 `docs/research/CLAUDE.md` 를 언급한다** — 사용자 소유 폴더라 임의 수정이 금지돼 있다 (`.claude/rules/context.md`) | **승인 없이는 손대지 않는다.** 인라인 코드라 링크 테스트에는 걸리지 않으나 내용이 틀리게 된다. Phase 3 착수 전에 사용자에게 그 한 줄 수정을 확인한다 |
| **보존 지정 폴더의 링크가 깨진다** — `research` 3곳·`spec` 3곳이 ROADMAP·HANDS_ON 을 가리킨다 | 참조 수정 표에 전부 넣었다. **삭제가 아니라 링크 수정**이므로 보존 지정과 충돌하지 않는다 |

## 8) 메모(Notes)

### 조사로 확정한 사실 (추측 아님)

- **`@path` import 를 쓰지 않는 이유** — 공식 문서 원문: *"Splitting into `@path` imports helps organization
  but doesn't reduce context, since imported files load at launch."* INDEX 18.6KB 가 매 세션 들어가면서도
  그 다음 문서로 이어지는 것은 보장하지 못한다
- **`paths` 없는 rules 가 항상 로드되는 근거** — 공식 문서 원문: *"Rules without a `paths` field are loaded
  unconditionally and apply to all files."* 현재 이 저장소의 rules 5개는 전부 `paths` 를 가져 조건부다
- **SessionStart 훅의 컨텍스트 주입** — `hookSpecificOutput.additionalContext` 또는 평문 stdout.
  matcher 는 `startup`·`resume`·`clear`·`compact`·`fork`
- **함정 13개의 원본 위치 전수 대조 결과** — 고아 0개.
  4개(등급·회당 기대값·표본 보존·DNS)는 루트 `CLAUDE.md`, 6개는 해당 검증의 spec/research 에 §번호까지,
  3개는 `INDEX.md`·`.gitignore`·`COMMANDS.md`·`strategy/옵션_만기일_매매_규칙.md`·
  `spec/futures_leverage.md`+코드 4곳
- **HANDS_ON 이 사용자용인 근거** — 머리말 *"통계나 파이썬을 몰라도 따라올 수 있게 썼습니다"*,
  ROADMAP 488~516 의 「사용자 직접 대조 진행 상태」에 3·4단계를 사용자가 직접 수행한 기록
- **「재현 방법」 절이 HANDS_ON 을 대신하지 못하는 이유** — 전자는 스크립트 재실행(선행 파일·명령·고정
  파라미터), 후자는 손계산. 역할이 다르다. **그럼에도 삭제하는 것은 대조가 이미 끝났기 때문**이다
- **계약 8종이 전부 유효한 근거** — `storage/series/`·`ecos_collector.py`·`fred_collector.py`·
  `studies/usdkrw_equivalence/` 가 모두 존재한다

### 자체 검증에서 고친 것 (작성 직후, 승인 전)

첫 판의 참조 수정 표는 **전수가 아니었다.** 앞선 조사에서 `grep ... | head -20` 으로 잘린 결과를
그대로 옮겼기 때문이다. 전수 재집계(113건)로 아래를 추가했다.

| 발견 | 조치 |
| --- | --- |
| `README.md:33`·`scripts/CLAUDE.md:59` 가 ROADMAP 을 가리킨다 | 참조 표에 추가 |
| **보존 지정 폴더가 6곳에서 가리킨다** — `research` 3곳(지수_극단_이벤트 19·44·794줄 외), `spec` 3곳(option_expiry 202, index_extreme_events 189·467) | 참조 표에 추가. **링크 수정은 삭제가 아니므로 보존 지정과 충돌하지 않는다** |
| `docs/context/README.md:64` 가 `docs/research/CLAUDE.md` 를 언급한다 | **사용자 소유 폴더** — Risks 에 올리고 승인 대상으로 뺐다 |
| `reference/` 2개 문서에도 ROADMAP 참조가 있다 | **이 저장소 것이 아니다.** "Phase 4·6" 은 verify-lab 에 없는 번호이고 `pykrx_실측기록.md:9` 의 링크는 이미 깨져 있다(이관 문서의 원래 상태). 읽기 전용 폴더이므로 **비목표에 명시하고 손대지 않는다** |
| `CLAUDE.md` 3곳·`.claude/rules/docs.md` 1곳·`연속_등락.md` 1곳이 `docs/research/CLAUDE.md` 를 가리킨다 | 이동 대상이므로 참조 표에 추가 |


### 실행 중 계획의 전제가 바뀐 것

| 발견 | 계획 | 실제 조치 |
| --- | --- | --- |
| **코드 3곳이 ROADMAP 을 참조했다** — `tests/test_yfinance_collector.py`·`src/verify_lab/measure/constants.py`·`src/verify_lab/data/yfinance_collector.py` | 계획서 참조 표에 없었다 (조사가 `*.md` 만 봤다) | 셋 다 `src/verify_lab/CLAUDE.md` 「계층 간 계약」으로 돌렸다 |
| **`docs/COMMANDS.md` 의 「원달러 그리드 — 코드 삭제됨」은 죽은 절이 아니었다** | "실행 불가 절 정리" 로 적었다 | **의도적 묘비**다(「없는 것도 없음으로 적는다」 관용). 지우지 않고 중복 링크만 정리했다 |
| **`docs/research/CLAUDE.md` 에 이미 `paths` frontmatter 가 있었다** | 새로 붙일 계획이었다 | CLAUDE.md 는 디렉터리 기반 로드라 그 frontmatter 는 **효과가 없었다.** `.claude/rules/research.md` 로 옮기면서 비로소 작동한다 |
| `docs/spec/index_extreme_events.md` 의 HANDS_ON 참조가 **2건**이었다 | 1건으로 적었다 | 둘 다 처리 (467줄 링크 제거, 189줄 본문 표현 수정) |
| `tests/test_research_docs.py` 의 `NOT_A_RESULT` 가 orphan 이 됐다 | 계획에 없었다 | 이 변경으로 생긴 orphan 이라 제거하고 `RESULT_DOCS` 를 단순화했다 |

### 승격 17건의 최종 위치

| 승격 대상 | 새 위치 |
| --- | --- |
| 계층 간 계약 8종 | `src/verify_lab/CLAUDE.md` 「계층 간 계약」 |
| `.claude/rules/` 자동 로드 실측 | `.claude/rules/session-bootstrap.md` 4절 |
| `poetry run` 가상환경 실측 | 같은 파일 5절 |
| `storage/results/` 함의 | 같은 파일 6절 |
| 미사용 판정 교훈 | `.claude/rules/python.md` |
| 묶음 상수 patch 교훈 | `tests/CLAUDE.md` 5절 |
| 픽스처 가정 교훈 | `tests/CLAUDE.md` 9절 |
| 검증 #1 대조 8단계 통과 | `docs/research/지수_극단_이벤트.md` §15 |
| 사용자 실제 집행 조건 | 루트 `CLAUDE.md` |
| 계획서 승격 목적지 표 | `.claude/rules/docs.md` 「계획서」 |

### 결과 수치

- `docs/` **1.5M → 1004K**
- 삭제: `ROADMAP.md`(817줄) · `HANDS_ON.md`(660줄) · `다음세션_프롬프트.md` · 계획서 13개
- 신설: `.claude/rules/session-bootstrap.md` · `.claude/rules/research.md` · `.claude/settings.json` · `docs/plans/.gitkeep`
- 참조 수정 **20개 파일**
- `validate_project.py` — passed=834 · failed=0 · skipped=0

### 진행 로그 (KST)

- 2026-09-05 18:49: 계획서 작성. 사용자 결정 ①~⑦ 반영
- 2026-09-05 19:32: 마지막 Phase 완료. validate_project.py passed=834 failed=0 skipped=0
- 2026-09-05 19:25: Phase 3 완료 — 삭제 4종, 참조 20개 파일 수정
- 2026-09-05 19:15: Phase 2 완료 — 부트스트랩 규칙·훅·research 규칙 이동·gitkeep
- 2026-09-05 19:10: Phase 1 완료 — 승격 14건 (나머지 3건은 Phase 2)
- 2026-09-05 19:04: Phase 0 완료 — 테스트 4종 추가, 레드 7건 확인
- 2026-09-05 18:58: 자체 검증 — 참조 누락 8건·규칙 충돌 1건을 찾아 Scope·Phase 3·Risks·비목표 보강

---
