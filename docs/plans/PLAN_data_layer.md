# Implementation Plan: 수집 계층의 기준 시각 통일과 공유 상수 단일화

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

**작성일**: 2026-09-06 07:10
**마지막 업데이트**: 2026-09-06 07:22
**관련 범위**: data, scripts/data
**관련 문서**: `CLAUDE.md`, `src/verify_lab/CLAUDE.md`, `scripts/CLAUDE.md`, `tests/CLAUDE.md`, `.claude/rules/python.md`

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

- [x] 목표 1: **「당일 제외」의 기준 시각을 KST 하나로 고정한다** — 지금은 실행 PC 의 타임존을 따르므로, TZ 가 다른 곳에서 돌리면 경계가 하루 어긋난다. 이 저장소는 여러 PC 에서 이어 작업하는 것이 전제다
- [x] 목표 2: **`data/` 계층이 공유하는 상수를 한 곳에 모은다** — 제외 일수·KRX 날짜 포맷·응답 날짜 포맷이 파일마다 흩어져 있고, 주석은 서로를 "같은 기준"이라 가리킨다
- [x] 목표 3: **「자격증명 먼저」 계약을 테스트로 고정한다** — 세 수집기가 각자 지키고 있는 순서이며, 어기면 `import pykrx` 가 로그인을 먼저 시도해 실패한다
- [x] 목표 4: **`type: ignore` 2건이 근본 해결 불가임을 확정하고 근거를 코드에 남긴다** — 다음 사람이 같은 조사를 반복하지 않게 한다

## 2) 비목표(Non-Goals)

**전수 감사 50건 중 이번 계획서의 범위는 9건이다.**

- **방어·불변조건** — 중단 누락 5건, 불필요한 fallback 4건 등 → `PLAN_guards`
- **리팩토링·문서** — 죽은 조건, `expanding_rank` 재계산, 문서 정리 → `PLAN_refactor_docs`
- **수집기의 조회 로직·검증 규칙을 바꾸지 않는다.** 기준 시각과 상수 위치만 옮긴다
- **`scripts/data/` 의 CLI 인자 날짜 포맷은 통합 대상이 아니다** — 값이 우연히 같을 뿐
  사용자가 입력하는 형식이고 KRX API 규격이 아니다. 묶으면 한쪽이 바뀔 때 다른 쪽이 끌려간다
- **시세 재수집 금지.** 수집기를 고치지만 **실행하지 않는다** — 기간이 늘면 기존 결과 문서의
  수치가 재현되지 않는다 (`.claude/rules/session-bootstrap.md` 6절)

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

**「당일은 반드시 뺀다」가 실행 PC 의 타임존에 달려 있다.**

`src/verify_lab/CLAUDE.md` 「계층 간 계약」의 원시 시세 저장 규칙이
"장중에도 당일 행이 그대로 반환되는 것이 실측됐으므로 당일은 반드시 뺀다"를 요구하는데,
수집기 다섯 곳이 전부 `date.today()` — **로컬 타임존** — 를 쓴다.
`common_constants.KST` 가 "실행 시각과 타임스탬프의 기준 시간대"로 정의돼 있으나
쓰는 곳은 `report/writer.py` 와 `utils/meta_manager.py` 뿐이다.

TZ 가 UTC 인 환경에서 KST 오전 9시 이전에 실행하면 「오늘」이 전날이 되어 경계가 하루 밀린다.
**예외는 나지 않고 저장 범위만 달라진다.**

> `yfinance_collector` 도 같은 문제다. 그 모듈 주석이 이미
> "미국장은 **한국 시각 기준으로** 하루가 밀리고" 라고 적어 KST 를 전제하고 있으므로,
> 로컬 타임존을 쓰는 것은 주석과 코드가 어긋난 것이기도 하다.

**`data/` 계층에 `constants.py` 가 없어 공유 값이 흩어져 있다.** 실측:

| 값 | 정의처 | 비고 |
| --- | --- | --- |
| `RECENT_EXCLUSION_DAYS = 1` | `pykrx_collector` · `etn_collector` · `krx_futures_collector` | 셋 다 국내이고 주석이 서로를 "같은 기준"이라 가리킨다 |
| `RECENT_EXCLUSION_DAYS = 2` | `yfinance_collector` | **값이 다르다.** 미국장은 시차로 하루 더 뺀다 |
| `KRX_DATE_FORMAT = "%Y%m%d"` | `pykrx_collector` · `etn_collector` · `krx_futures_collector` | KRX 요청 규격 하나 |
| `..._RESPONSE_DATE_FORMAT = "%Y/%m/%d"` | `etn_collector` · `krx_futures_collector` | KRX 응답 규격 하나 |

`src/verify_lab/CLAUDE.md` 「상수 관리」가 "한 계층 내 2개 이상 파일에서 사용 → `<계층>/constants.py`"
로 정했는데 그 파일이 없다.

**「자격증명 먼저」 계약이 세 곳에 흩어져 있고 테스트가 없다.**
`pykrx_collector._import_pykrx_stock()` · `etn_collector._import_krx_client()` ·
`krx_futures_collector._import_krx_client()` 가 전부
`load_krx_credentials()` → `from pykrx... import` 순서를 지킨다.
순서를 어기면 `import pykrx` 가 로그인을 먼저 시도해 실패하며, 이 저장소에서 가장 조용히
틀릴 수 있는 계약 중 하나다. **지금은 각 docstring 이 설명할 뿐 아무도 검사하지 않는다.**

**`type: ignore` 2건은 같은 원인에서 나온다.** 둘 다 런타임에 얻은 KRX 클라이언트 클래스를
상속하는 자리이고, pykrx 가 타입 스텁을 제공하지 않아 기반 클래스가 `Unknown` 이다.
근본 해결이 불가하다는 사실이 코드에 적혀 있지 않아 다음 사람이 같은 조사를 반복한다.

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「스크립트 실행 규칙」과 재수집 경고
- `src/verify_lab/CLAUDE.md` — 「상수 관리」 3계층, 「계층 간 계약」의 원시 시세 저장 규칙
- `scripts/CLAUDE.md` — CLI 계층의 책임
- `tests/CLAUDE.md` — 결정적 테스트(시간 고정 `freezegun`), 외부 의존성 금지
- `.claude/rules/python.md` — 코딩 표준, 주석 작성 원칙
- `.claude/rules/session-bootstrap.md` — 6절(재수집 금지)

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 수집기 다섯 곳이 전부 KST 기준으로 「오늘」을 판정한다
- [x] `data/constants.py` 가 생기고, 공유 상수의 정의처가 하나다
- [x] 「자격증명 먼저」 순서가 테스트로 고정돼 있다
- [x] `type: ignore` 2건에 **왜 없앨 수 없는지**가 적혀 있다
- [x] 회귀/신규 테스트 추가 — 기준 시각은 `freezegun` 으로 고정해 TZ 에 무관하게 검사한다
- [x] `poetry run python validate_project.py` 통과 — passed=881, failed=0, skipped=0
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트(`docs/COMMANDS.md` / CLAUDE.md / plan 등 — 각각 변경 여부 명시)
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 근거·실측 수치를 루트 `CLAUDE.md` 의 프로젝트 설정 절이 정한 목적지로 이관.
      `/impl-plan` 스킬 "근거 승격" 참고)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

**신설**

- `src/verify_lab/data/constants.py` — 국내 제외 일수·KRX 요청/응답 날짜 포맷
  (**미국 제외 일수는 쓰는 곳이 하나라 옮기지 않는다**)

**수집 계층**

- `src/verify_lab/data/pykrx_collector.py` — 기준 시각 KST, 상수 재노출, 지연 import 헬퍼 일원화
- `src/verify_lab/data/etn_collector.py` — 같음. `_import_krx_client` 중복 제거
- `src/verify_lab/data/krx_futures_collector.py` — 같음. `type: ignore` 근거 주석
- `src/verify_lab/data/yfinance_collector.py` — 기준 시각 KST.
  **제외 일수 상수는 그대로 둔다** (쓰는 곳이 이 파일뿐)

**실행 계층**

- `scripts/data/collect_ecos.py` — `KST` 로컬 재정의 제거하고 `common_constants` 사용

**테스트**

- `tests/test_pykrx_collector.py` · `tests/test_etn_collector.py` ·
  `tests/test_krx_futures_collector.py` · `tests/test_yfinance_collector.py` — 상수 경로 반영
- 신규: 기준 시각이 KST 임을 고정 (`freezegun` 으로 UTC 자정 근처를 재현) ·
  `data/` 공유 상수의 정의처가 하나임

**문서**

- `docs/COMMANDS.md`: **변경 없음** — 실행 명령어와 CLI 옵션이 바뀌지 않는다
- `src/verify_lab/CLAUDE.md`: **변경 있음** — 「계층 간 계약」의 원시 시세 저장 규칙에
  「최근 구간」의 기준 시각이 KST 임을 적는다

### 데이터/결과 영향

- **저장되는 시세는 바뀌지 않는다** — 이 PC 의 TZ 가 이미 KST 라 같은 값이 나온다.
  바뀌는 것은 **다른 TZ 에서 돌렸을 때의 동작**이다
- **수집 스크립트를 실행하지 않는다.** 재수집은 기존 결과 문서의 수치를 재현 불가로 만든다
- 검증 방법은 `freezegun` 으로 시각을 고정한 **테스트**이며 실제 수집이 아니다

## 6) 단계별 계획(Phases)

### Phase 0 — 기준 시각 계약을 테스트로 먼저 고정(레드 허용)

> 이 Phase 가 필요한 이유: 기준 시각은 **에러 처리 정책**이 아니라 **판정 경계**다.
> 어긋나도 예외가 나지 않고 저장 범위만 달라지므로, 테스트가 먼저 말해야 한다.
>
> **이 PC 의 TZ 가 KST 라 그냥 두면 레드가 나지 않는다.** `freezegun` 으로
> **UTC 기준 자정 직후**(= KST 로는 이미 다음 날 오전)를 재현해 두 해석이 갈리는 순간을 만든다.

**작업 내용**:

- [x] 수집기가 「오늘」을 KST 로 판정한다는 테스트 — UTC 와 KST 가 다른 날짜를 가리키는 시각에서
      **KST 쪽 날짜로 잘린다**를 고정 (레드 예상)
- [x] `data/` 공유 상수의 정의처가 하나라는 테스트 —
      `PLAN_judgeable_thresholds` 가 만든 `tests/test_layer_contracts.py` 의 관용을 그대로 쓴다 (레드 예상)
- [x] 세 KRX 지연 import 헬퍼가 **pykrx 를 가져오기 전에 자격증명을 올린다**는 테스트.
      **레드가 아니다** — 지금도 지키고 있으며, 새 수집기가 빠뜨리는 것을 막는 장치다

---

### Phase 1 — `data/constants.py` 신설과 상수 이동(그린 유지)

**작업 내용**:

- [x] `data/constants.py` 를 만들고 **왜 이 계층에 두는지**를 docstring 에 적는다
- [x] **국내 제외 일수만** 옮긴다 (세 파일이 공유). **미국(2)은 `yfinance_collector` 한 곳에서만
      쓰므로 그 파일에 남긴다** — 「상수 관리」가 "1개 파일에서만 사용 → 해당 파일 상단"으로 정했고,
      쓰이는 곳이 하나인 값을 계층 상수로 올리면 그 파일을 읽는 사람이 공유값이라고 오해한다.
      대신 **두 값의 관계**(미국은 국내에 시차 하루가 더 붙은 것)를 양쪽 주석이 서로 가리키게 한다
- [x] KRX 요청 포맷(`%Y%m%d`)과 응답 포맷(`%Y/%m/%d`)을 각각 하나로 모은다.
      **두 포맷을 한 상수로 합치지 않는다** — 요청과 응답은 KRX 가 정한 서로 다른 규격이다
- [x] 네 수집기가 그 상수를 쓰도록 고친다

---

### Phase 2 — 기준 시각을 KST 로 고정(그린 유지)

**작업 내용**:

- [x] 수집기 다섯 곳의 `date.today()` 를 KST 기준으로 바꾼다
- [x] **헬퍼 함수를 만들지 않는다.** `datetime.now(KST).date()` 는 그 자체로 의도가 드러나고,
      감싸면 「왜 감쌌나」를 설명해야 하는데 실익이 없다 (YAGNI).
      **다섯 곳이 같은 표현을 쓰는 것이 오히려 검색으로 확인된다**
- [x] `scripts/data/collect_ecos.py` 의 `KST` 로컬 재정의를 제거하고 `common_constants` 를 쓴다

---

### Phase 3 — 지연 import 일원화와 `type: ignore` 근거 기록(그린 유지)

**작업 내용**:

- [x] **`_import_krx_client()` 를 합치지 않는다.** 실측으로 두 함수는 **이름만 같고 다른 것을
      반환한다** — ETN 은 `ETN_전종목기본종목`, 선물은 `전종목시세` 를 각자 가져온다.
      공통인 것은 `load_krx_credentials()` 호출과 `KrxWebIo` 뿐이고, 그만큼을 새 모듈로 빼면
      **각 수집기가 여전히 자기 조회 클래스를 함수 안에서 import 해야 해** 줄어드는 것이 없다.
      깨지지 않은 코드를 리팩토링하지 않는다 (전역 「수술적 변경」)
- [x] **실제 위험은 「자격증명 먼저」 순서를 새 수집기가 빠뜨리는 것**이므로 그것을 테스트로 고정한다 —
      세 헬퍼가 pykrx 를 import 하기 전에 `load_krx_credentials()` 를 부르는지 검사한다.
      코드를 옮기는 것보다 이쪽이 위험을 직접 막는다
- [x] 반환 타입이 `tuple[Any, Any]` 인 이유 — pykrx 에 스텁이 없어 그 이상 좁힐 수 없다 — 를 적는다
- [x] `type: ignore` 2건에 **왜 없앨 수 없는지**를 적는다. 지금은 억제 코드만 있고 이유가 없어
      다음 사람이 같은 조사를 반복한다. 「런타임에 얻은 클래스를 상속하는 자리이며 pykrx 에
      타입 스텁이 없다. 없애려면 스텁을 직접 쓰거나 상속을 버려야 하는데, 상속은 pykrx 내부
      프로토콜을 따르는 유일한 방법이다」

---

### Phase 4 — 문서 정리 및 최종 검증

**작업 내용**

- [x] `src/verify_lab/CLAUDE.md` 「계층 간 계약」의 원시 시세 저장 규칙에
      **「최근 구간」의 기준 시각이 KST** 임을 적는다
- [x] `docs/COMMANDS.md`: **변경 없음** (실행 명령어·CLI 옵션 불변)
- [x] 자동 포맷 적용 — `poetry run black .`
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [x] `poetry run python validate_project.py` (passed=881, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 수집 / 당일 제외의 기준 시각을 KST 로 고정하고 계층 공유 상수를 한 곳에 모음
2. 수집 / 실행 PC 의 타임존에 달려 있던 수집 경계를 KST 로 못박음
3. 수집 / data 계층 상수 파일을 신설하고 KRX 지연 import 를 일원화
4. 수집 / 기준 시각·제외 일수·날짜 포맷의 정의처를 하나로 정리
5. 수집 / 타임존 의존을 걷어내고 type ignore 두 곳에 해소 불가 근거를 남김

## 7) 리스크(Risks)

- **이 PC 가 KST 라 잘못 고쳐도 테스트가 통과할 수 있다.**
  **완화**: Phase 0 이 `freezegun` 으로 UTC 와 KST 가 다른 날짜를 가리키는 시각을 만들어
  두 해석이 갈리는 순간을 재현한다. 시각 고정 없이 검사하면 이 계획서의 목적 자체가 검증되지 않는다
- **`_import_krx_client` 를 옮길 곳을 잘못 고르면 「자격증명 먼저」 계약이 깨진다.**
  `krx_credentials.py` 는 "pykrx 를 import 하지 않는다"를 docstring 으로 선언했고
  그 이유가 순서 보장이다. 거기 두면 선언이 거짓이 된다.
  **완화**: Phase 3 에서 위치를 먼저 판단하고 근거를 남긴다
- **제외 일수를 하나로 합치거나, 반대로 둘 다 계층 상수로 올리고 싶은 유혹.**
  국내 1·미국 2 는 값도 이유도 다르고, 미국 쪽은 쓰는 곳이 한 파일뿐이다.
  **완화**: 국내만 올리고 미국은 제자리에 두되 두 주석이 서로를 가리키게 한다

## 8) 메모(Notes)

- 실측(2026-09-06): `date.today()` 5곳 —
  `pykrx_collector`(2) · `etn_collector`(2) · `krx_futures_collector`(1) · `yfinance_collector`(1)
- 실측(2026-09-06): `RECENT_EXCLUSION_DAYS` 4곳(국내 3곳 값 1, 미국 1곳 값 2),
  `KRX_DATE_FORMAT` 3곳, `..._RESPONSE_DATE_FORMAT` 2곳, `_import_krx_client` 2곳
- 실측(2026-09-06): 이 PC 의 TZ 는 KST 라 **현재 동작에는 차이가 없다.**
  고치는 것은 다른 TZ 에서 돌렸을 때의 동작이며, 그래서 테스트에 시각 고정이 반드시 필요하다
- 실측(2026-09-06): 착수 전 `validate_project.py` — passed=876, failed=0, skipped=0

- **실측으로 계획의 전제 하나가 무너져 방향을 바꿨다** (2026-09-06).
  감사에서 `_import_krx_client()` 를 「두 파일의 중복 정의」로 적었으나, 실제로는
  **이름만 같고 반환하는 것이 다르다** — ETN 은 `ETN_전종목기본종목`, 선물은 `전종목시세` 다.
  공통인 것은 자격증명 호출과 `KrxWebIo` 뿐이라 합쳐도 각 수집기가 자기 클래스를 여전히
  함수 안에서 가져와야 한다. **합치는 대신 실제 위험(순서 누락)을 테스트로 막는다.**

### 진행 로그 (KST)

- 2026-09-06 07:10: 계획서 작성. 전수 감사 50건 중 9건을 이 계획서의 범위로 확정
- 2026-09-06 07:13: Phase 0 — 기준 시각 계약 테스트. **`freeze_time` 아래에서 `date.today()` 가
  UTC 를 그대로 내는 것**을 이용해 두 해석이 갈리는 시각(UTC 20:00 = KST 익일 05:00)을 만들어 레드 확인
- 2026-09-06 07:16: Phase 1 — `data/constants.py` 신설. 국내 제외 일수·KRX 요청/응답 포맷을 모으고
  세 수집기가 그것을 쓰게 함. **미국 제외 일수는 쓰는 곳이 하나라 제자리에 둠**
- 2026-09-06 07:19: Phase 2 — `date.today()` 5곳을 `datetime.now(KST).date()` 로.
  `collect_ecos.py` 의 `KST` 재정의 제거
- 2026-09-06 07:21: Phase 3 — **`_import_krx_client` 합치기를 취소**하고(실측으로 중복이 아님)
  「자격증명 먼저」를 AST 기반 테스트로 고정. `type: ignore` 2건에 해소 불가 근거 기록
- 2026-09-06 07:22: 품질 검증 통과 (passed=881, failed=0, skipped=0). Done

---
