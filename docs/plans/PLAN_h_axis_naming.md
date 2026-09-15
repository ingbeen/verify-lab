# Implementation Plan: H — 축 하나에 이름 하나, 소유자 하나

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

**작성일**: 2026-09-15 10:05
**마지막 업데이트**: 2026-09-15 11:35
**관련 범위**: 측정(report), 검증(studies), 매매(strategy), 테스트, 문서
**관련 문서**: 루트 `CLAUDE.md`, `src/verify_lab/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/docs.md`, `.claude/rules/research.md`

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

- [x] 목표 1: **산출물 헤더가 개념과 1:1이 되게 한다.** 지금 `시기` 는 두 뜻, `구간` 은 두 뜻이고,
      「측정 구간」 축 하나가 **네 가지 방식으로 렌더링**된다. 개념 다섯에 이름 다섯을 준다
- [x] 목표 2: **그 이름의 소유자를 하나로 만든다.** `HORIZON_LABELS` 가 두 벌이고, 한 검증은
      사전을 쓰지 않아 원값이 그대로 나간다
- [x] 목표 3: **재발을 기계가 막는다.** 지금 계약 테스트는 이 결함을 **한 건도 잡지 못했다**
- [x] 목표 4: 계획서 A~G 가 남긴 **실제 결함 1건과 감시 구멍 2건**을 함께 닫는다
- [x] 목표 5: **헤더 이름만 바뀌는 자리에서는 값이 한 셀도 바뀌지 않는다.** 값이 바뀌는 자리는
      둘뿐이며 그 둘은 결과 문서를 함께 고친다

## 2) 비목표(Non-Goals)

- **`COL_HORIZON` 의 «내부» 오버로딩은 손대지 않는다.** 옵션 만기일이 그 컬럼에 상대 거래일·
  보유 거래일·만기월 번호 셋을 번갈아 담는데, 이는 `measure.summarize` 가 그 컬럼으로 묶기
  때문이다. 고치려면 측정 계층의 계약을 바꿔야 하고 그것은 이 계획서의 범위가 아니다.
  **이 계획서는 «표시» 계층만 고친다**
- **`_REPORT_LABEL_COLLISIONS` 의 `날짜`·`신호`·`표본` 3건은 그대로 둔다** — 2026-09-14 사용자
  결정으로 범위 밖이다
- **이미 커밋된 산출물은 소급 수정하지 않는다** (`src/verify_lab/CLAUDE.md` 「적용 범위는 새로
  내는 산출물부터입니다」). 옛 폴더와 새 폴더의 헤더가 다른 상태가 정상이다
- **산출물 폴더 정리는 하지 않는다** — `/clean-results` 는 모델이 호출할 수 없다. 현재
  인용 없는 폴더가 59개이며 사용자가 직접 돌린다
- 측정 격자(`HORIZONS`·`HOLDING_HORIZONS`·`DEFAULT_HORIZONS`) 자체를 바꾸지 않는다. **무엇을
  재는가는 그대로이고 무엇이라 부르는가만 바꾼다**
- 검증 셋의 달력형·배수형 공통 어휘를 뽑지 않는다 — E-6 결정(2026-09-14)을 유지한다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

계획서 A~G 완료 후 전수 점검에서 나왔다. 넷은 서로 다른 층의 문제이고 한 번에 닫는다.

#### ① 등가성 검증 테스트가 실제 저장소 데이터를 읽는다 — 유일한 «실제 결함»

`studies/usdkrw_equivalence/runner.py:224` 의 `_load_spot(SPOT_CLOSE)` 가 **패치되지 않은 모듈
상수**를 쓴다. `tests/test_studies_equivalence_runner.py` 는 `KRW_RATE_PATH`·`USD_RATE_PATH`·
`ETF_TARGETS` 만 갈아끼운다. 실측으로 재현했다 — 합성 데이터 테스트가
`storage/series/USDKRW_CLOSE.csv`(9,014행 · 1990-03-02 ~ 2026-08-26)를 읽는다.

`tests/CLAUDE.md` 「파일 격리」 위반이고, **환율을 재수집하면 `effective_cost` 값이 조용히
바뀐다.** 예외는 나지 않는다. 계획서 B 가 인계했으나 C~G 어디서도 닫히지 않았다.

#### ② `assert_no_absolute_paths` 가 요약 9개 중 5개에만 걸려 있다

빠진 넷은 `option_expiry`·`month_end`·`leverage_tracking`·`futures_leverage` **검증** 요약이다.
현재 9개 요약 전부 절대경로가 없음을 실측했으므로 **값은 지금 옳고 감시만 없다.** 그런데
정작 절대경로 결함이 있던 자리가 **옵션 만기일 검증**이었다. 계획서 D 의 코드 리뷰가 지목했다.

#### ③ 죽은 이름을 가리키는 주석 7곳 — G 의 규칙이 못 미친 자리

백틱 참조를 기계로 훑어 골라냈다. 전부 C·D·E 가 지운 이름을 현재형처럼 인용한다.

| 자리 | 죽은 이름 | 무엇이 문제인가 |
| --- | --- | --- |
| `src/verify_lab/measure/constants.py:92` | `DISPLAY_PERIOD_EARLY`·`DISPLAY_TIME_HALF_EARLY` | 「이름은 계층마다 다른데」가 C 의 통합 후 **거짓**이 됐다 |
| `src/verify_lab/strategy/constants.py:96` | `DISPLAY_STDEV` | C 가 `DISPLAY_STD` 로 개명해 비교 대상이 없다 |
| `tests/test_layer_contracts.py:248` · `:906` | 같은 둘 | 같음 |
| `tests/test_layer_contracts.py:1004` · `src/verify_lab/CLAUDE.md:120` | `COL_CONVERGED_MONTHS` | D 가 지운 이름 |
| `tests/test_studies_month_end_execution.py:244` | `MARKET_BY_LABEL` | **「전에는 …였다」** 로 명시 — `.claude/rules/docs.md` 가 코드 주석에 금지한 과거형 |

#### ④ 개념이 다섯인데 이름이 셋이고, 그중 둘이 겹친다

현재 산출물 실측이다.

| 개념 | 값 | 현재 헤더 | 파일 수 |
| --- | --- | --- | --- |
| **A. 원칙 17 시기 축** | 전체·앞 절반·뒤 절반·최근 10년·최근 5년 | 검증 **`시기`** / 매매 **`구간`** | 3 + 3 (부속 2컬럼 3장) |
| **B. 측정 구간** | 1일 ~ 3년 (거래일) | **`구간`** | 42 |
| **B′. 보유 거래일** | `-1` · 4 · 5 | **`구간`** (같은 이름) | 3 |
| **C. 금리 환경** | 저금리(~2021)·고금리(2022~) | **`시기`** | 28 |
| **D. 시대 구간** | 2010년대·2020년대·전체 | `시대 구간` | 5 |

`시기` = A + C, `구간` = A + B + B′. **`windows_*.csv` 는 4열이 `구간`(B), 16열이 `시기`(C)로
한 파일에 나란히 있다.**

**그리고 B 축 하나가 네 가지로 렌더링된다.**

| 검증 | 격자 | `구간` 에 나가는 값 | 어떻게 |
| --- | --- | --- | --- |
| 레버리지 | `HORIZONS = (5,10,21,63,126,252,756)` | `1주 · 2주 · 1개월 · 3개월 · 6개월 · 1년 · 3년` | **자기 `HORIZON_LABELS` 7키** |
| 선물 | `HOLDING_HORIZONS = (5,10,21,63,126,252,756)` | **`5 · 10 · 21 · 63 · 126 · 252 · 756`** | **라벨 미적용 — 원값** |
| 역방향 | (6칸) | `1일 · 2일 · 3일 · 1주 · 2주 · 1개월` | `report.horizon_label()` (4키 + fallback) |
| 옵션 만기일 | — | **`-1 · 4 · 5`** | 라벨 미적용. `-1` 은 `HORIZON_NEXT_WEEK_EXIT` sentinel |

**두 격자 튜플이 글자 하나까지 같은데 한쪽은 한글 한쪽은 숫자로 나간다.** 예외는 안 난다.

**근본 원인은 「측정 구간 표시명」의 소유자가 없다는 것이다.** `report/constants.HORIZON_LABELS`
가 **4키**(`1·5·10·21`)뿐이라 공통 계층이 자기 축을 다 못 덮는다. 그래서 레버리지는 7키짜리
사본을 만들었고(겹치는 3키는 값이 같은 순수 중복), 선물은 포기했고, 옵션 만기일은 sentinel 을
밀어 넣었다. `horizon_label(63)` → `"63일"`, `horizon_label(-1)` → **`"-1일"`** 이다.

> **그 사전이 4키인 데는 이유가 있었다.** 커밋 `282ab53` 이 「역방향의 측정 구간이 단기로
> 확정돼 안 쓰는 키를 뺀다」로 줄였고, 주석이 「여기 없는 구간은 `f"{days}일"` 로 나가므로 그
> 형태로 충분한 구간은 등록하지 않는다」고 적었다. **지금은 전제가 다르다** — 63·126·252·756 은
> 죽은 값이 아니라 **레버리지와 선물이 실제로 쓰는 살아있는 값**이다. 그리고 fallback 이
> 「충분」하지 않다는 것이 실측으로 드러났다: 그 때문에 사본이 생기고 렌더링이 갈렸다.
> **`report` 는 어느 검증이 자기를 쓰는지 몰라야 하므로**(계층 원칙) 「역방향이 안 쓴다」는
> 애초에 사전을 줄일 근거가 아니었다.
>
> **사전을 넓혀도 역방향 산출물은 바뀌지 않는다** — `measure.forward_return.DEFAULT_HORIZONS`
> 가 `(1, 2, 3, 5, 10, 21)` 이라 새로 더하는 네 키(63·126·252·756)에 **닿는 행이 없다**
> (실측 2026-09-15). `2`·`3` 은 계속 fallback 이 내므로 그 동작을 고정한 기존 테스트도 그대로 산다.

**갈림이 결과 문서까지 번졌다.** 같은 7격자를 `docs/research/선물_대_레버리지_ETF.md` 는
`21일·63일·252일·756일`, `docs/research/레버리지_ETF_괴리.md` 는 `1주·3개월·1년·3년` 으로 쓴다.

**독자 비용의 직접 증거가 이미 문서에 있다** — `docs/research/역방향.md:151` 이
「**`구간` 은 측정 구간**이고 **시대 구간은 `시대 구간`**」이라는 **해설 문장을 달아야 했다.**
이름이 스스로 말했으면 그 문장이 필요 없었다.

#### ⑤ 지금 계약 테스트는 이 결함을 한 건도 잡지 못한다

`_REPORT_LABEL_COLLISIONS` 는 **`report` 가 정의한 레이블의 재정의**만 본다. `시기` 는 `report`
레이블이 아니라서 보이지 않고, `HORIZON_LABELS` 같은 **사전이 두 벌인 것**도 보지 않는다.

### 확정된 설계 — 2026-09-15 사용자 승인

| 개념 | 새 헤더 | 소유자 |
| --- | --- | --- |
| **A. 원칙 17 시기 축** | **`시기`** | **`report/constants.py` 하나.** 지금은 검증 둘이 각자 `시기` 를 정의하고 매매가 `구간` 을 정의한다 — 값만 맞추면 **같은 레이블의 정의가 셋이 된다** |
| **B. 측정 구간** | **`구간`** (유지) | **`report.HORIZON_LABELS` 하나** — 8키로 넓히고 레버리지 사본 제거, 선물도 라벨 적용 |
| **B′. 보유 거래일** | **`보유 거래일`** (신설) | 옵션 만기일. `구간` 축에서 분리하고 `-1` 을 **`전체`** 로 낸다 |
| **C. 금리 환경** | **`금리 환경`** | 레버리지 · 선물 (각자 — E-6 결정 유지) |
| **D. 시대 구간** | `시대 구간` (유지) | 역방향 |

**A 를 `시기` 로 잡는 근거**: 루트 `CLAUDE.md` 원칙 12·17 **본문의 말이 「시기 분해」**다.
그러면 `구간` 이 B 전용으로 비어 **42장이 손대지 않고 정리된다.** 대안 `구간` 은 B 42장을
비켜야 해서 가장 크고, `시기 구간` 은 D 의 `시대 구간` 과 한 글자 차이라 역방향에서
둘이 나란히 읽힌다.

**A 의 소유자를 `report/constants.py` 로 두는 근거**: `measure/screening.py` 는 **축 컬럼 이름을
인자로 받고 자기가 정의하지 않는다**(「축을 모른다 — 만기월이든 요일이든 시기든」). 그래서
값만 `시기` 로 맞추면 `month_end`·`option_expiry`·`strategy` **세 곳이 같은 레이블을 각자
정의**하게 되고, 그것은 계획서 C 가 없앤 중복을 새로 만드는 것이다.
**이 저장소는 이미 답을 정해 뒀다** — `strategy/constants.py:96` 이 「같은 것을 재는 공통 컬럼은
`report/constants.py` 가 소유하고 쓰는 쪽이 거기서 직접 가져온다」고 적고, 원칙 12·17 이 요구하는
`DISPLAY_JUDGEABLE` 이 실제로 그렇게 `report` 에 있으며 `futures_leverage` 가 거기서 가져온다.
**A 도 원칙 17 이 모든 매매법에 요구하는 축이므로 같은 자리다.**

> **`시기 시작일`·`시기 종료일` 은 `strategy/constants.py` 에 남는다** — 매매 성적표 3장에만
> 있고 검증은 내지 않는다. 「1개 계층에서만 사용」이라 올릴 이유가 없다.

**B′ 를 분리하는 근거**: `4`·`5` 는 격자 칸이 아니라 **그 신호가 실제로 몇 거래일 들렸는가**다
(휴장 때문에 신호마다 다르다 — `docs/research/옵션_만기일.md:201` 이 「330건 중 78건이 4거래일」
이라 적는다). 다른 개념을 같은 축에 넣었기 때문에 **「실제 보유일로는 도달할 수 없는 음수」라는
sentinel 이 필요해졌다.** 축을 나누면 그 우회가 통째로 사라진다.

**C 를 `금리 환경` 으로 잡는 근거**: 값(`저금리(~2021)`)과 맞고, `.claude/rules/docs.md` 용어
대응표가 금지한 `국면` 을 피하며 **무엇으로 나눴는지가 이름에 드러난다.**

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「측정의 원칙」 12·17, 「후보 판정 기준」, 「계획서 규약 — 이 프로젝트의 설정」
- `src/verify_lab/CLAUDE.md` — 특히 「상수 관리」·「내부/출력 분리」·「계층 간 계약」의 매매 산출물 계약·출력 계약
- `scripts/CLAUDE.md` — CLI 계층 제약
- `tests/CLAUDE.md` — **특히 「파일 격리」와 「픽스처가 코드와 같은 가정을 하면」**
- `.claude/rules/docs.md` — 문서 종류와 SoT, **과거형이 허용되는 자리**, 말은 뜻이 드러나게
- `.claude/rules/research.md` — 결과 문서 작성 규칙
- `.claude/rules/strategy.md` — 매매 계층 예외 규정
- `~/.claude/rules/python.md` (전역) — 코딩 표준·반올림·로깅

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] **선행 계획서 복기 완료** — `docs/plans/PLAN_[a-g]_*.md` 의 「후속 계획서 인계」를 읽고
      이 계획서가 받은 항목과 남길 항목을 진행 로그에 정리했다
- [x] Phase 0 재판단 게이트를 전 항목에 대해 실행하고, 각 항목의 「한다 / 안 한다」를 근거와 함께 남겼다
- [x] ①②③④ 중 「한다」로 판정된 항목이 전부 구현됐다
- [x] 회귀/신규 테스트 추가 (닫은 구멍마다 최소 1개)
- [x] **값 불변 확인** — 헤더만 바뀌는 자리에서 값이 한 셀도 바뀌지 않았음을 Phase 4 의 대조로 보였다
- [x] **값이 바뀐 두 자리는 결과 문서를 함께 고쳤다** (선물 `구간` 표기 · 옵션 만기일 `보유 거래일`)
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` 변경 여부를 Phase 4 에서 명시)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

**① 등가성 파일 격리**

- `src/verify_lab/studies/usdkrw_equivalence/runner.py` — 비용 계산이 모듈 상수 대신 **전달받은
  `sources` 에서 종가 계열을 고르게** 한다. `run_equivalence(models, sources=SPOT_SOURCES)` 가
  이미 그 인자를 받으므로 시그니처는 그대로다. **고를 계열이 없으면 `ValueError`** —
  조용히 기본값으로 되돌아가면 지금 결함이 그대로 남는다
- `tests/test_studies_equivalence_runner.py` — 합성 계열만 읽음을 고정하는 테스트 추가

**② 절대경로 감시 — 단일 길목에서 막는다** (2026-09-15 조정 승인)

- 🔴 `src/verify_lab/report/writer.py` — **`save_run_summary` 가 요약에 절대경로가 있으면 거부**한다.
  판정 함수도 여기가 소유한다. **이 함수가 `summary.json` 을 쓰는 유일한 자리**임을 호출처
  전수로 확인했다 — 검증 6 + 매매 3 = **9곳 전부이고 그 외 없다**. 그래서 한 곳이 아홉 개와
  **앞으로 만들 검증까지** 덮는다
- `tests/conftest.py` — `assert_no_absolute_paths` 가 **그 같은 함수를 쓰게** 한다.
  지금은 판정이 테스트에만 있어 production 에 없다 (절대 원칙 5 판정식 단일화)
- `tests/test_studies_month_end_runner.py` · `tests/test_studies_leverage_runner.py`
  — `assert_no_absolute_paths` 적용 (이중 방어와 더 나은 실패 메시지)
- `tests/test_report_writer.py` — 거부 동작을 고정하는 테스트

> **네 테스트에 거는 원안을 버린 이유**: `test_studies_option_expiry_runner.py` 와
> `test_studies_futures_runner.py` 는 **`run_study` 를 부르지 않고 비공개 헬퍼만 시험한다**
> (`.summary` 참조 0건). 걸려면 e2e 실행 테스트를 새로 만들어야 하고, **그렇게 해도 그 둘만
> 덮는다.** 길목에서 막으면 아홉 개가 한 번에 덮인다

**③ 죽은 이름 주석**

- `src/verify_lab/measure/constants.py` · `src/verify_lab/strategy/constants.py` ·
  `src/verify_lab/CLAUDE.md` · `tests/test_layer_contracts.py` · `tests/test_studies_month_end_execution.py`

**④-A 원칙 17 축 → `시기`, 소유자는 `report`**

- `src/verify_lab/report/constants.py` — A 축 레이블 **신설** (`시기`)
- `src/verify_lab/studies/month_end/constants.py` — 자기 `DISPLAY_PERIOD` 정의 제거, `report` 에서 가져옴
- `src/verify_lab/studies/option_expiry/constants.py` — 자기 `DISPLAY_TIME_HALF` 정의 제거, 같음
- `src/verify_lab/strategy/constants.py` — `DISPLAY_PERIOD` 정의 제거(`report` 에서 가져옴).
  `DISPLAY_PERIOD_START`·`DISPLAY_PERIOD_END` 는 **값만** `시기 시작일`·`시기 종료일` 로 바꾸고 제자리에 둔다
- `tests/test_strategy_output_contract.py` — 계약 컬럼 목록
- `tests/test_layer_contracts.py` — `_REPORT_LABEL_COLLISIONS` 의 `구간` 항목 정리

**④-B 측정 구간 소유자 통합**

- `src/verify_lab/report/constants.py` — `HORIZON_LABELS` 를 8키로, 주석 갱신
- `src/verify_lab/studies/leverage_tracking/constants.py` — 자기 `HORIZON_LABELS` 제거
- `src/verify_lab/studies/leverage_tracking/runner.py` — `report` 것을 import
- `src/verify_lab/studies/futures_leverage/{constants,runner}.py` — 라벨 적용
- `src/verify_lab/report/tables.py` — `horizon_label` docstring 갱신

**④-B′ 보유 거래일 분리**

- `src/verify_lab/studies/option_expiry/constants.py` — `OUTPUT_LABELS` 의 `COL_HORIZON` 을
  **이미 있는 `DISPLAY_HOLD_DAYS`(`"보유 거래일"`)** 로 돌린다. **상수를 새로 만들지 않는다** —
  집계 축이 곧 `weekly_trade_signals.csv` 의 `보유 거래일` 과 같은 양이라 **같은 이름이어야
  두 표를 이어 읽을 수 있다**
- `src/verify_lab/studies/option_expiry/runner.py` — `-1` 을 `전체` 로 내는 표시 변환
- 🔴 `src/verify_lab/report/tables.py` — **`to_display_columns` 가 결과 헤더 중복을 거부**하게 한다.
  `COL_HOLD_DAYS` 와 `COL_HORIZON` 이 **`RETURN_COLUMNS` 에 함께 들어 있어**, 둘 다 실린 표를
  저장하면 pandas 가 **예외 없이 `보유 거래일,보유 거래일` 을 쓴다**(실측). 지금은 두 컬럼이
  같이 저장되는 표가 없지만 가드가 없으면 다음 표에서 조용히 터진다.
  **판정은 사전이 아니라 «결과 프레임»의 헤더로 한다** — `futures_leverage.OUTPUT_LABELS` 가
  `Date`·`StartDate` 를 둘 다 `시작일` 로 내보내는데 **한 표에 같이 나오지 않아 정당하다**

**④-C 금리 환경**

- `src/verify_lab/studies/leverage_tracking/constants.py` — `DISPLAY_PERIOD_AXIS` → `DISPLAY_RATE_REGIME`("금리 환경")
- `src/verify_lab/studies/futures_leverage/constants.py` — `DISPLAY_PERIOD` → `DISPLAY_RATE_REGIME`("금리 환경")
- 두 `runner.py` 의 호출부

**⑤ 감시 테스트**

- `tests/test_layer_contracts.py` — 새 클래스 둘 (아래 Phase 0)

**문서**

- 루트 `CLAUDE.md` (원칙 12·17 의 「구간 5행」 표기) · `src/verify_lab/CLAUDE.md` (매매 산출물 계약·출력 계약) ·
  `docs/INDEX.md` · `docs/COMMANDS.md` ·
  `docs/strategy/{역방향,옵션_만기일,월말_진입}_매매_규칙.md` · `docs/strategy/투자금_결정.md` ·
  `docs/research/{선물_대_레버리지_ETF,레버리지_ETF_괴리,옵션_만기일,역방향}.md` ·
  `docs/spec/옵션_만기일_설계.md`(결정 ㉑ 의 sentinel 서술)
- `docs/COMMANDS.md`: **변경 있음** — 산출물 컬럼 설명에 「구간」이 있어 표기를 맞춘다.
  **실행 명령어·CLI 옵션은 바뀌지 않는다**

### 데이터/결과 영향

| 자리 | 바뀌는 것 | 값이 바뀌나 |
| --- | --- | --- |
| 매매 성적표 3장 | `구간`→`시기` · `구간 시작일`→`시기 시작일` · `구간 종료일`→`시기 종료일` | **헤더만** |
| 레버리지 28장 · 선물 | `시기`→`금리 환경` | **헤더만** |
| 레버리지 `구간` | 사전 출처만 바뀜 (값은 동일) | **아니오** |
| **선물 `구간`** | `5·10·21·63·126·252·756` → `1주·2주·1개월·3개월·6개월·1년·3년` | **예** |
| **옵션 만기일 weekly_trade 3장** | `구간`→`보유 거래일`, `-1`→`전체` | **예** |

- **옛 산출물은 소급 수정하지 않는다.** 옛 폴더와 새 폴더의 헤더가 다른 상태가 정상이다
- 대조는 **「값이 바뀐 컬럼을 뺀 나머지 전 셀 일치」**로 한다

## 6) 단계별 계획(Phases)

### Phase 0 — 재판단 게이트와 감시 테스트 먼저(레드 허용)

> 코드를 고치기 전에 **정말 고쳐야 하는지**를 다시 확인하고, 재발을 막을 테스트를 먼저 세운다.

**작업 내용**:

- [x] 🔴 **선행 계획서 복기** — `docs/plans/PLAN_[a-g]_*.md` 의 「후속 계획서 인계」 절을 전부 읽고,
      이 계획서가 받은 항목(①②③)과 **받지 않기로 한 항목**(허용목록 3건·`_kst_now`·산출물 정리·
      INDEX 「8대상」)을 진행 로그에 표로 남긴다
- [x] **① 재판단** — `_load_spot(SPOT_CLOSE)` 가 정말 실제 파일을 읽는지 다시 확인한다.
      확인 방법: `load_series_csv` 를 감싸 읽은 경로를 기록하는 pytest 플러그인으로 재현
- [x] **② 재판단** — 검증 넷의 요약 테스트에 요약을 만드는 픽스처가 있는지 본다.
      없으면 **테스트를 새로 만들지 말고 인계에 남긴다**(범위 관리)
- [x] **③ 재판단** — 죽은 이름 7곳을 다시 훑어 그 사이 사라졌거나 늘어난 것이 없는지 본다
- [x] **④ 재판단** — 아래 넷을 각각 확인하고 「한다/안 한다」를 근거와 함께 남긴다
  - **A 축 레이블을 `report` 가 소유할 때 계층 방향이 성립하는가** — `studies`·`strategy` 둘 다
    이미 `report` 에 의존하므로 성립해야 한다. `TestCommonLayerReexport` 가 **옛 경로로 가져오는
    것**을 막으므로, 세 소비처가 소유자에서 직접 가져오는지 확인한다
  - `tests/test_report_tables.py:396` 이 「`2`·`3` 은 사전에 없고 fallback 이 낸다」를 고정한다.
    **2·3 은 등록하지 않으므로 그대로 통과해야 한다**
  - `tests/test_studies_leverage_runner.py:308` 의 `unknown = max(HORIZON_LABELS) + 1` 이
    사전 교체 후에도 성립하는지
  - 옵션 만기일 `-1` → `전체` 변환이 `trade_headline` 의 필터(`COL_HORIZON == -1`)를 깨지 않는지
    — **필터는 내부 컬럼을 보고 변환은 표시 컬럼에서 하므로 분리돼야 한다**
  - **`TestDisplayLabelLiveness` 가 `report` 에서 «가져온» 키도 제외하는지** — 제외 목록이
    `measure`·`common` 뿐이면, A 축 레이블을 `report` 로 옮긴 순간 `month_end`·`option_expiry` 의
    사전에서 그 키가 **「자기가 정의했는데 안 쓰인다」로 오탐**될 수 있다. 판정 축을 먼저 확인한다
- [x] **감시 테스트 신설 (레드 허용)** — `tests/test_layer_contracts.py`
  - `TestOutputLabelUniqueness` — **산출물로 나가는 `DISPLAY_*` 값이 서로 다른 소유자에게
    겹치지 않는다.** 이미 알려진 동음이의어만 허용목록으로 고정한다.
    `_REPORT_LABEL_COLLISIONS` 가 `report` 레이블만 보던 것을 **전 계층으로 넓히는 자리**다
  - `TestHorizonLabelOwnership` — ① `HORIZON_LABELS` 정의처가 **하나**다
    ② 측정 구간 축을 산출물로 내는 검증은 **전부 그 사전(또는 `horizon_label`)을 거친다** —
    원값을 그대로 rename 만 해서 내보내지 않는다
  - `to_display_columns` 의 **중복 헤더 거부** 테스트 — 같은 레이블로 접히는 두 컬럼을 넣으면
    예외가 난다. 지금은 `보유 거래일,보유 거래일` 이 **조용히 저장된다**(실측)
- [x] 네 항목의 판정을 **진행 로그에 표로** 남긴다 (`항목 | 한다/안 한다 | 근거`)

**Validation**:

- [x] 새 감시 테스트가 **현재 코드에서 실패**하는 것을 확인한다 (레드) — 통과하면 그 테스트는
      결함을 못 보는 것이므로 판정 축을 다시 짠다

---

### Phase 1 — ① 파일 격리와 ② 절대경로 감시(그린 유지)

> ④와 독립이라 먼저 닫는다. 여기서 산출물 값은 바뀌지 않는다.

**작업 내용**:

- [x] **①** `run_equivalence` 가 비용 계산에 쓸 종가 계열을 **전달받은 `sources` 에서 고르게** 한다.
      모듈 상수 `SPOT_CLOSE` 를 직접 읽지 않는다
- [x] **①** 테스트에 「저장소 실제 파일을 읽지 않는다」를 고정하는 단언을 추가한다 —
      `tests/CLAUDE.md` 「파일 격리」의 집행이다
- [x] **②** `report/writer.py` 가 **「요약에 절대경로가 있는가」 판정을 소유**하고
      `save_run_summary` 가 발견 시 예외를 던지게 한다. 메시지에 **어느 자리인지**를 담는다 —
      중첩 두 단계 아래(`inputs.spot.close`)에 있던 것이 실제 사례다
- [x] **②** `tests/conftest.assert_no_absolute_paths` 가 그 함수를 쓰게 바꾼다. **두 벌로 두지 않는다**
- [x] **②** `run_study` 를 부르는 두 테스트(`month_end`·`leverage`)에 단언을 추가한다
- [x] **②** `tests/test_report_writer.py` 에 거부 동작을 고정한다 (정상 요약은 통과, 절대경로는 예외)

**Validation**:

- [x] `poetry run pytest tests/test_studies_equivalence_runner.py` 그린
- [x] 위 추적 플러그인으로 **저장소 실제 파일 읽기 0건** 확인

---

### Phase 2 — ④-A 원칙 17 축을 `시기` 로 통일(그린 유지)

**작업 내용**:

- [x] `report/constants.py` 에 A 축 레이블을 **신설**한다 (값 `시기`). 주석에 **「원칙 17 이 모든
      매매법에 요구하는 축이라 소유자가 하나」**라는 근거를 적는다
- [x] `month_end`·`option_expiry`·`strategy` 의 자기 정의를 지우고 **소유자에서 직접 가져온다**.
      옛 경로로 재노출하지 않는다 (`src/verify_lab/CLAUDE.md` 「옛 경로로 가져오지 않습니다」)
- [x] `strategy/constants.py` 의 `DISPLAY_PERIOD_START`·`DISPLAY_PERIOD_END` **값**을
      `시기 시작일`·`시기 종료일` 로 바꾼다. **파이썬 이름은 그대로 둔다** — 뜻이 바뀌지 않았다
- [x] `tests/test_strategy_output_contract.py` 의 계약 컬럼 목록을 맞춘다
- [x] `_REPORT_LABEL_COLLISIONS` 에서 `구간` 항목을 뺀다 — **겹침이 해소되면 허용목록에 남을
      이유가 없고, 남기면 다음 겹침이 조용히 통과한다**

**Validation**:

- [x] 매매 셋을 재실행해 `성적표.csv` 헤더가 바뀌고 **나머지 전 셀이 일치**함을 대조한다
- [x] 월말·옵션 만기일 **검증**도 재실행해 `시기` 컬럼이 **값까지 그대로**임을 대조한다 —
      소유자만 옮겼으므로 한 셀도 바뀌면 안 된다

---

### Phase 3 — ④-B / B′ / C 측정 구간 소유자 통합(그린 유지)

**작업 내용**:

- [x] **B** `report/constants.HORIZON_LABELS` 에 `63·126·252·756` 을 더한다. 주석을
      **「자기 격자를 아는 검증이 사본을 만들지 않게 공통이 다 덮는다」**로 고쳐 쓴다 —
      **「전에는 4키였다」로 쓰지 않는다**(`.claude/rules/docs.md` 현재형 규칙)
- [x] **B** `leverage_tracking/constants.py` 의 `HORIZON_LABELS` 를 지우고 runner 가 `report` 것을 가져온다.
      **`[...]` 인덱싱은 유지한다** — 자기 격자를 아는 검증은 모르는 칸에서 죽는 것이 맞다
- [x] **B** `futures_leverage` 가 `구간` 을 원값으로 내던 것을 라벨로 바꾼다
- [x] **B′** 옵션 만기일 weekly_trade 계열의 표시 헤더를 **이미 있는 `DISPLAY_HOLD_DAYS`** 로
      돌리고 `-1` 을 `전체` 로 낸다. **내부 `COL_HORIZON` 과 `trade_headline` 의 필터는 건드리지 않는다**
- [x] **B′** `to_display_columns` 에 **결과 헤더 중복 거부**를 더한다. 판정은 사전이 아니라
      **결과 프레임의 헤더**로 한다 — 정당한 동일값 쌍(`Date`·`StartDate` → `시작일`)을 막지 않기 위해서다.
      **기존 산출물에 중복 헤더가 0건**임을 실측했으므로 이 가드로 깨지는 표는 없다
- [x] **C** 레버리지·선물의 `시기` 를 `금리 환경` 으로 바꾸고 **파이썬 이름도 `DISPLAY_RATE_REGIME`** 으로
      맞춘다 — 여기는 뜻이 「시기」가 아니었으므로 이름이 틀려 있었다
- [x] Phase 0 의 감시 테스트 둘이 **그린이 되는 것**을 확인한다

**Validation**:

- [x] 검증 여섯을 재실행해 **값이 바뀐 두 컬럼을 뺀 나머지 전 셀 일치**를 대조한다
- [x] 바뀐 두 컬럼은 **바뀐 값이 의도한 것과 정확히 같은지**를 따로 눈으로 확인한다

---

### Phase 4 — 문서 정리 및 최종 검증

**작업 내용**

- [x] **③** 죽은 이름 주석 7곳을 현재형 사실로 고친다. **정보를 지우지 않는다** —
      「그래서 지금 이 구조다」를 남기고 시제만 바꾼다
- [x] 결과 문서 둘을 값에 맞춘다 — `docs/research/선물_대_레버리지_ETF.md`(구간 표기 전환) ·
      `docs/research/옵션_만기일.md`(§11 의 `보유 거래일`)
- [x] `docs/research/역방향.md:151` 의 **해설 문장이 아직 필요한지** 판단한다 —
      `구간` 이 B 전용이 되면 불필요할 수 있다
- [x] 매매 문서 4개·`COMMANDS.md`·`INDEX.md`·루트 `CLAUDE.md`·`src/verify_lab/CLAUDE.md` 의
      「구간 5행」·「구간별 성적」 산문을 `시기` 로 맞춘다
- [x] `docs/spec/옵션_만기일_설계.md` 결정 ㉑ 에 **sentinel 이 표시 축에서 사라졌다**는 사실을 더한다
- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` 포함 여부 명시)
- [x] 자동 포맷 적용 (`poetry run black .`)
- [x] 변경 기능 및 전체 플로우 최종 검증 — **CLI 21개 기동 확인**(계층 계약 테스트가
      `scripts/` 를 다 덮지 못한다. E 가 인계한 함정이다)
- [x] 🔴 **`/commit` 을 실행하고 그 후보를 «이 계획서» 의 `#### Commit Messages` 절에 옮긴다** —
      `/commit` 은 계획서를 모르고 「후보 뒤에 아무것도 덧붙이지 말 것」으로 끝나므로,
      **대화에만 내면 그 절이 빈 채로 남는다**
- [x] 🔴 **「후속 계획서 인계」 절을 채운다** (§8 Notes)
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

> 순서를 지킨다 — 리뷰에서 고치면 코드가 바뀌므로 품질 검증이 마지막 관문이어야 한다.

- [x] `/code-review xhigh` (발견 **13건** · 조치: **10건 반영 · 3건 근거 남기고 유보**)
- [x] `poetry run python validate_project.py` (passed=1194, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다.**
> 계획서를 쓰는 시점에는 diff 가 없어 여기 적는 것은 전부 추측이고,
> **추측으로 적은 줄은 그대로 나간다.** 형식·문체 규칙은 `/commit` 이 정한다.

1. 측정 / 산출물 축 이름 통일과 소유자 일원화
2. 측정 / 시기·구간 동음이의 해소와 측정 구간 이름표 8키 통합
3. 측정 / 같은 축이 네 방식으로 나가던 렌더링 통일
4. 측정 / 축 이름 정리와 절대경로·중복 헤더·원값 노출 가드 4종 신설
5. 측정 / 헤더-개념 1:1 확립, 파일 격리 결함 1건과 감시 구멍 2건 해소

## 7) 리스크(Risks)

| 리스크 | 완화 |
| --- | --- |
| **선물 `구간` 값이 바뀌어 결과 문서와 어긋난다** | Phase 4 에서 `선물_대_레버리지_ETF.md` 표기를 함께 전환한다. **전환 전후로 수치가 아니라 표기만 바뀌는 것**이므로 값 대조로 확인한다 |
| **옵션 만기일 `-1` 변환이 `trade_headline` 필터를 깬다** | 필터는 내부 `COL_HORIZON`, 변환은 표시 컬럼에서 한다. Phase 0 에서 이 분리를 먼저 확인한다 |
| **`HORIZON_LABELS` 확장이 역방향 산출물을 바꾼다** | **해소됨** — `DEFAULT_HORIZONS = (1,2,3,5,10,21)` 이라 새 키에 닿는 행이 없다(실측 2026-09-15). Phase 3 재실행 대조로 한 번 더 확인한다 |
| **A 축 소유자 이전이 「옛 경로」를 남긴다** | `__all__` 재노출을 하지 않고 세 소비처가 소유자에서 직접 가져온다. `TestCommonLayerReexport` 가 이미 그 방향을 검사하므로 어기면 그 테스트가 실패한다 |
| **레버리지 사본 제거로 `KeyError` 가 뒤늦게 터진다** | 사전이 상위집합이 되므로 오히려 덜 터진다. 그래도 Phase 3 재실행으로 확인한다 |
| **문서 산문을 고치다 수치를 건드린다** | 문서 변경은 **표기만** — 숫자를 손대면 그 자리에서 멈추고 진행 로그에 적는다 |
| 감시 테스트의 허용목록이 너무 넓어 아무것도 못 잡는다 | Phase 0 에서 **레드를 먼저 확인**한다. 통과하면 판정 축을 다시 짠다 |

## 8) 메모(Notes)

- **B′ 의 대안**: `보유 거래일` 대신 `집계 단위`(묶음 / 보유 4일 / 보유 5일) 컬럼을 두는 안도 있었다.
  **기각** — 표 구성이 바뀌어 `trade_excess`·`trade_test` 와 축이 어긋나고, 지금 필요한 것은
  「이 열이 무엇인가」를 드러내는 것이지 새 축이 아니다
- **B′ 에서 상수를 새로 만들지 않는 이유**: `DISPLAY_HOLD_DAYS` 가 **이미 있고 뜻이 정확히 같다**.
  새로 만들면 `보유 거래일` 과 `보유 길이` 처럼 **비슷한 이름 둘**이 생기는데, 그것이 이 계획서가
  없애려는 병이다 (전역 「사다리」 2단 — 이미 이 코드베이스에 있나)
- **`to_display_columns` 가드는 매매 성적표를 덮지 않는다** — `strategy/periods.py` 가 그 함수를
  지나지 않고 저장 직전에 직접 반올림한다(그 함수의 Note 가 명시). **이 계획서는 넓히지 않는다** —
  매매 산출물 계약이 컬럼을 고정하고 `test_strategy_output_contract.py` 가 그것을 검사하므로
  같은 사고의 경로가 이미 막혀 있다
- **파이썬 이름을 언제 바꾸고 언제 두는가**: 뜻이 그대로인 A 는 **값만** 바꾸고(`DISPLAY_PERIOD` 유지),
  뜻이 틀렸던 C 는 **이름도** 바꾼다(`DISPLAY_PERIOD_AXIS` → `DISPLAY_RATE_REGIME`).
  기준은 「그 이름이 지금 담는 것을 말하는가」 하나다

### 후속 계획서 인계 (이 계획서를 끝낸 뒤 채운다)

> H 는 A~G 의 후속이다. **다음 작업(새 계획서 또는 다음 감사)이 이 절을 읽는다.**
> 형식: `무엇이 | 어떤 상태인가 | 어디에 남겼나`
>
> 🔴 **`docs/plans/` 는 주기적으로 삭제된다.** 여기 적은 것 중 계속 참이어야 하는 것은
> **살아있는 문서로 옮기고** 이 절에는 그 위치만 적는다.
> 남은 것이 없으면 **「없음」이라고 적는다**.

| 무엇이 | 어떤 상태인가 | 어디에 남겼나 |
| --- | --- | --- |
| 🔴 **축 이름과 소유자 — 이 계획서의 핵심 산출물** | **확정.** 개념 다섯에 이름 다섯이고 소유자가 하나씩이다 — `시기`(원칙 17, `report`) · `구간`(측정 구간, `report`) · `보유 거래일`(옵션 만기일) · `금리 환경`(배수 검증 둘) · `시대 구간`(역방향). 근거는 「원칙 12·17 본문의 말이 「시기 분해」」이고, 그래야 `구간` 이 측정 구간 전용으로 비어 **42장이 손대지 않고 정리된다** | [src/verify_lab/CLAUDE.md](../../src/verify_lab/CLAUDE.md) 「출력 계약」·「매매 산출물 계약」 · `report/constants.py` 의 두 상수 주석 — **SoT** |
| 🔴 **`report.HORIZON_LABELS` 가 저장소의 격자를 전부 덮는다** | **확정(8키).** 공통 계층이 자기 축을 다 못 덮으면 검증이 사본을 만들고 사본은 갈라진다 — 같은 격자를 한 검증은 `1주·3개월·3년` 으로, 다른 검증은 `5·63·756` 으로 내고 있었다. 달력 이름이 없는 `2`·`3` 은 등록하지 않고 fallback 이 `2일`·`3일` 을 낸다 | `report/constants.py` `HORIZON_LABELS` 주석 · `report/tables.py` `horizon_label` docstring |
| **왜 사전을 줄였던 결정을 뒤집었나** | 커밋 `282ab53` 이 「역방향이 안 쓰는 키를 뺀다」로 줄였는데, **`report` 는 어느 검증이 자기를 쓰는지 몰라야 하므로** 그것은 애초에 줄일 근거가 아니었다. 63·126·252·756 은 배수 검증 둘이 실제로 쓴다 | 같은 주석 |
| **`-1` sentinel 은 내부에만 둔다** | **확정.** 실제 보유일로 도달할 수 없는 음수라야 길이 칸과 안 섞이지만(결정 ㉑), 그 값이 그대로 나가 CSV 에 `-1` 이 찍히고 있었다. 표시 축은 `보유 거래일` 이고 묶음 행은 `전체` 다 | [docs/spec/옵션_만기일_설계.md](../spec/옵션_만기일_설계.md) 결정 ㉑ |
| 🔴 **요약의 절대경로를 «저장 길목»에서 막는다** | **확정.** `report/writer.save_run_summary` 가 `summary.json` 을 쓰는 유일한 함수라(검증 6 + 매매 3) 한 곳이 아홉 개와 **앞으로 만들 검증까지** 덮는다. 판정은 프로덕션이 소유하고 테스트 픽스처가 같은 함수를 쓴다(절대 원칙 5). 접두사를 손으로 박는 이유(`BASE_DIR` 파생은 이 PC 경로만 본다)도 그 자리에 있다 | `report/writer.py` `ABSOLUTE_PATH_PREFIXES`·`save_run_summary` 주석 |
| **두 컬럼이 같은 헤더로 접히는 것을 막는다** | **확정.** pandas 는 예외 없이 `X,X` 를 쓴다(실측). 판정은 사전이 아니라 **결과 프레임 헤더**로 한다 — 정당한 동일값 쌍(`Date`·`StartDate` → `시작일`)을 막지 않기 위해서다 | `report/tables.py` `to_display_columns` 주석 |
| 🔴 **CLI 가 도메인 축을 직접 거르지 않는다** | **확정.** 선물 CLI 가 `== 252` 로 걸렀는데 축의 값이 표시 이름으로 바뀌자 **표가 사라진 채 실행이 성공했다.** `scripts/` 는 타입 검사·계약 테스트 대상이 아니라 아무도 못 봤다. 선택을 runner(`comparison_headline`)로 옮겨 테스트가 덮는다 | `futures_leverage/runner.py` `comparison_headline` docstring · `tests/test_studies_futures_runner.py` |
| **새 감시 장치 넷** | `TestOutputLabelUniqueness`(산출물 레이블 유일성 + 허용목록 최신성) · `TestHorizonLabelOwnership`(사전 정의처 하나 · 원값 노출 금지) · `save_run_summary` 절대경로 거부 · `to_display_columns` 중복 헤더 거부. **허용목록 28종은 「지금 무엇이 겹쳐 있는가」의 기계 검증된 기록**이며 대부분이 E-6 결정(달력형·배수형 어휘를 뽑지 않는다)의 결과다 | `tests/test_layer_contracts.py` · `tests/test_report_writer.py` · `tests/test_report_tables.py` |
| ⚠️ **결과 문서 셋은 «고치지 않고 주석을 달았다»** | 세 문서 모두 **옛 폴더를 인용**해, 표기를 바꾸면 문서가 자기 근거물과 어긋난다(`.claude/rules/docs.md`). 무엇이 달라졌는지를 머리말에 적었다. `역방향.md:151` 의 해설 문장은 **남겼다** — 그 문서 표에 `구간`·`시대 구간` 두 컬럼이 함께 있어 저장소 전체 모호성과 별개로 여전히 필요하다 | `docs/research/선물_대_레버리지_ETF.md` · `docs/research/옵션_만기일.md` 머리말 |
| 🔴 **코드 리뷰가 남긴 것 셋 — 근거와 함께 유보** | ① `save_run_summary` 가 **CSV 를 다 쓴 뒤** 거부해 요약 없는 폴더가 남는다. 앞당기려면 9개 CLI 의 호출 순서를 바꿔야 하고, 저장 중 어떤 예외든 같은 상태를 만들므로 이 가드만의 문제가 아니다 ② `TestHorizonLabelOwnership` 의 두 번째 검사는 **소스 문자열로 패키지를 고르므로 선물 하나만 덮는다** — 「그 검증이 측정 구간 축을 내는가」를 정적으로 알 방법이 없었다 ③ `전체` 가 `보유 거래일`(묶음)과 `시기`(전 구간) 두 자리에 있다. **값은 컬럼이 문맥을 주므로 헤더 충돌보다 해롭지 않다**고 보고 그대로 뒀다 | 이 표 |
| ⚠️ **같은 «이름» 다른 «값»인 `DISPLAY_*` 가 7종 있다** | `DISPLAY_TICKER`·`DISPLAY_HOLD_DAYS`·`DISPLAY_EXIT_DATE`·`DISPLAY_MONTH`·`DISPLAY_EXPOSURE`·`DISPLAY_TARGET_TICKER` **6종은 기존 것**이라 수술적 변경 원칙으로 손대지 않았다. 이 계획서가 만든 `DISPLAY_PERIOD` 충돌만 없앴다(역방향을 `DISPLAY_ERA` 로). **이름 충돌을 막는 감시 장치는 없다** — 넣으려면 그 6종을 먼저 정리해야 한다 | 이 표 |
| **산출물은 두 컬럼 말고 한 셀도 안 바뀌었다** | 9개 실행 대조 — **CSV 73장 · 11,296,716칸**. 바뀐 것은 선물의 보유 기간 표기(`5`→`1주`)와 옵션 만기일의 묶음 표지(`-1`→`전체`)뿐이고, 레버리지 `breakdown.csv` 의 `축` 값 294행은 `시기`→`금리 환경` 개명이 반영된 것이다(그 컬럼을 뺀 58,719칸 일치) | 마지막 Phase Validation |
| 🔴 **넘긴 것 — 산출물 폴더** | **사용자가 `/clean-results` 로 지운다.** 모델이 호출할 수 없다. 이 계획서가 대조로 여러 벌을 더 만들었다 | 없음 (작업 항목) |
| **전역 훅 하나를 고쳤다** | `~/.claude/hooks/plan_unfinished_on_stop.py` 가 **템플릿 placeholder 를 「마지막 Phase 도달」 증거로 세어**, 계획서를 `In Progress` 로 올리는 순간부터 모든 턴 끝이 막혔다. `plan_lint.FAILED_COUNT` 로 「숫자가 든 기록」만 세게 좁혔다(사용자 승인 2026-09-15). 저장소 밖이라 직접 실행해 6경우로 확인했다 | 그 훅의 `is_unfinished` docstring |

### 진행 로그 (KST)

- 2026-09-15 10:05: 계획서 작성. A~G 완료 후 전수 점검에서 나온 4건을 묶었다.
  ④의 통일 방향(`시기`·`구간`·`보유 거래일`·`금리 환경`)은 사용자 승인을 받았다
- 2026-09-15 11:35: **Done.** Phase 0~4 완료. 품질 검증 `passed=1194 · failed=0 · skipped=0`,
  코드 리뷰 13건 중 10건 반영(#1 은 이 계획서가 만든 실제 결함이었다 — 선물 CLI 의 헤드라인 표가
  **예외 없이 사라졌다**). 산출물 9개 재실행 대조에서 **CSV 73장 · 11,296,716칸**이 일치했고,
  바뀐 것은 의도한 두 컬럼과 레버리지 `축` 값 294행뿐이다
- 2026-09-15 10:50: **②의 방식 조정을 사용자가 승인했다.** 네 테스트에 단언을 거는 원안 대신
  **`report/writer.save_run_summary` 한 곳에서 막는다.** 그 함수가 요약 9개 전부의 단일 길목임을
  호출처 전수로 확인했고, 원안으로는 `option_expiry`·`futures` 를 영영 못 덮는다(그 둘의 runner
  테스트가 `run_study` 를 부르지 않는다). 판정 함수는 production 이 소유하고 테스트 픽스처가 쓴다
- 2026-09-15 10:40: **상태를 `In Progress` 로 올렸다가 `Draft` 로 되돌렸다.** Phase 0 은
  조사와 판정뿐이라 **소스 변경이 0건**이고, `plan_unfinished_on_stop.py` 가 규정한
  「Draft = 아직 착수 전」이 이 상태의 정확한 표기다. Phase 1 이 실제로 코드를 고칠 때 올린다.
  (그 훅은 `In Progress` + Validation 절의 품질 검증 줄 + 빈 커밋 후보 셋이 맞을 때 막는데,
  **템플릿의 placeholder 줄도 「마지막 Phase 도달」 증거로 센다** — 상태 표기를 미리 올리면 걸린다)
- 2026-09-15 10:35: **Phase 0 재판단 게이트 실행.** 판정표는 아래. **②의 전제가 무너져
  사용자 승인 대기 중**이며, 그 항목 외에는 계획대로 간다.

| 항목 | 한다/안 한다 | 근거 (실측 2026-09-15) |
| --- | --- | --- |
| **①** 등가성 파일 격리 | **한다** | 추적 플러그인으로 재현 — 합성 테스트가 `storage/series/USDKRW_CLOSE.csv`(9,014행)를 읽는다. `run_equivalence(models, sources=SPOT_SOURCES)` 가 이미 `sources` 를 받아 수정에 시그니처 변경이 없다 |
| **②** 절대경로 감시 | **방식 변경 제안** | 계획한 네 테스트 중 **둘만 가능**하다 — `test_studies_option_expiry_runner.py`·`test_studies_futures_runner.py` 는 **`run_study` 를 부르지 않고 비공개 헬퍼만 시험한다**(`.summary` 참조 0건). 대신 **`report/writer.save_run_summary` 가 요약 9개 전부의 단일 길목**임을 확인했다(호출처 9곳 = 검증 6 + 매매 3, 그 외 없음) |
| **③** 죽은 이름 주석 | **한다** | 7곳 그대로. 그 사이 늘거나 준 것 없음 |
| **④-A** A 축 소유자 이전 | **한다** | `TestDisplayLabelLiveness` 는 `owned`(그 패키지가 **대입한** 이름)만 판정하므로, 소유자를 `report` 로 옮기면 `month_end`·`option_expiry` 사전의 그 키는 **판정 대상에서 자동으로 빠진다** — 오탐 없음 |
| **④-B** 사전 통합 | **한다** | `DEFAULT_HORIZONS = (1,2,3,5,10,21)` 이라 새 키 넷에 닿는 행이 없다 → 역방향 불변. `test_report_tables.py:396`(2·3 fallback)은 2·3 을 등록하지 않으므로 그대로 산다. `test_studies_leverage_runner.py:308` 의 `max(HORIZON_LABELS)+1` 은 757 이 되어 여전히 성립 |
| **④-B′** 보유 거래일 분리 | **한다** | `trade_headline` 은 CLI 143행에서 **내부 프레임**을 필터하고 표시 변환은 188행 저장 시점이라 **분리돼 있다.** 값 변환은 `to_display_columns` 가 못 하므로(헤더만 바꾼다) **leverage 의 관용**(runner 가 표시 컬럼을 직접 만든다 — `runner.py:266`)을 따른다 |
| **④-C** 금리 환경 | **한다** | 정의 2곳·사용 5곳으로 국소적 |
| **중복 헤더 가드** | **한다** | pandas 가 `X,X` 를 예외 없이 쓴다(실측). 기존 산출물 중복 헤더 **0건**이고, 유일한 동일값 쌍(`Date`·`StartDate`→`시작일`)은 한 표에 공존하지 않아 **결과 프레임 기준 판정이면 안 깨진다** |

- 2026-09-15 10:15: **자체 검증에서 전제 하나가 무너져 초안을 고쳤다.** 「매매의 값만 `시기` 로
  바꾼다」로 썼는데, `measure/screening.py` 가 축 이름을 **인자로 받고 정의하지 않으므로**
  그렇게 하면 `month_end`·`option_expiry`·`strategy` **세 곳이 같은 레이블을 각자 정의**하게 된다 —
  계획서 C 가 없앤 중복을 새로 만드는 것이다. **A 축 레이블의 소유자를 `report/constants.py` 로**
  두는 것으로 고쳤고, 근거는 `strategy/constants.py:96` 의 관용과 `DISPLAY_JUDGEABLE` 선례다.
  같은 검증에서 `DEFAULT_HORIZONS = (1,2,3,5,10,21)` 을 실측해 「사전 확장이 역방향을 바꾼다」는
  리스크를 해소했고, `run_equivalence` 가 `sources` 를 받는 것과 테스트 파일 넷의 실재를 확인했다
