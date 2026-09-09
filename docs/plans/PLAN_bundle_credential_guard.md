# Implementation Plan: 번들의 claude_json.json 자격증명 차단과 기존 키 보존

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

**작성일**: 2026-09-09 21:07
**마지막 업데이트**: 2026-09-09 21:07
**관련 범위**: 하네스 (`.claude/skills/claude-config-export`, `.claude/skills/claude-config-import`, `tests/`)
**관련 문서**: 루트 `CLAUDE.md`, `tests/CLAUDE.md`, `~/.claude/rules/python.md`

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

- [x] 목표 1: `claude-config/claude_json.json` 에 **평문 자격증명이 담기지 않게** 한다 — 값을 고정 센티널로 치환하고, 치환한 항목을 사용자에게 보고한다
- [x] 목표 2: 받는 PC 에 **이미 그 값이 있으면 센티널이 그것을 덮어쓰지 않게** 한다 (사용자 요구)
- [x] 목표 3: 같은 판정을 **테스트가 집행**하게 한다 — 지금은 가드 48개가 전부 통과하면서 평문 키를 놓쳤다
- [x] 목표 4: 받는 쪽이 **무엇을 스스로 채워야 하는지** 문서와 실행 출력으로 알게 한다 (구글시트 OAuth 클라이언트 파일 포함)

## 2) 비목표(Non-Goals)

- **Context7 API 키 회전** — 사용자가 하지 않기로 결정했다 (2026-09-09). git 이력·추적 파일 어디에도 없어 저장소를 통한 유출이 확인되지 않았다
- **자격증명 파일 자체의 이관 자동화** — `~/.claude/keys/**` 는 계속 담지 않는다. 문서로 안내만 한다
- **`settings.json` 의 자격증명 검사** — 실측 결과 `env` 키가 없고(빈 dict) 자격증명이 들어갈 자리가 지금은 없다. 없는 문제를 위해 코드를 늘리지 않는다
- **번들을 git 에 커밋하는 것** — 커밋은 사용자가 직접 한다
- **`~/.claude.json` 에서 옮기는 키 목록(`CLAUDE_JSON_ROOT_KEYS`)의 확대·축소**

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

`/claude-config-export` 를 실행해 만든 번들의 `claude-config/claude_json.json` 에
**Context7 API 키가 평문으로 들어갔다.**

```
mcpServers.context7.headers.CONTEXT7_API_KEY = "ctx7sk-5471…"
```

**이 저장소는 PUBLIC 이다.** 한 번 커밋되면 파일을 지워도 git 이력에 남는다.

#### 왜 기존 가드가 놓쳤나 (실측 2026-09-09)

`export.py` 의 자격증명 판정 `_is_credential()` 은 **경로 기반**이다 —
`keys/**` · `*.env` · `*.pem` · `*.key` · `.credentials.json`.
그런데 `~/.claude.json` 은 `~/.claude` **밖에** 있어 이 판정을 아예 거치지 않고,
`extract_claude_json()` 이 `mcpServers` 를 **값 검사 없이 통째로 복사**한다.

`tests/test_claude_config_bundle.py` 도 같은 함수를 재사용하므로 같은 이유로 놓쳤다.
**48개 전부 통과하면서 평문 키가 번들에 들어갔다.**

즉 스킬 문서의 「자격증명은 담기지 않는다」 선언을 **claude.json 경로에서는 집행하는 층이 없다.**

#### 유출 여부 (실측 2026-09-09)

| 확인 | 명령 | 결과 |
| --- | --- | --- |
| git 이력 | `git log --all -S 'ctx7sk-'` | **0건** |
| 추적 파일 | `git grep -l 'ctx7sk-'` | **0건** |
| `.gitignore` | `grep claude-config .gitignore` | 항목 없음 → **다음 커밋에 딸려간다** |
| 번들 전체 스캔 | `grep -rE '(sk-\|ctx7sk\|ghp_\|AKIA\|-----BEGIN\|xox[baprs]-)' claude-config/` | 위 1건뿐 |

**아직 유출되지 않았다.** 그래서 키 회전은 하지 않고 근원만 고친다.

#### 다른 MCP 서버는 어떤가 (실측 2026-09-09)

| 서버 | 번들에 담기는 것 | 자격증명 위치 | 판정 |
| --- | --- | --- | --- |
| `context7` | `headers.CONTEXT7_API_KEY` = **평문 키** | 없음(값 자체가 키) | **문제** |
| `google-sheets` | `env.CREDENTIALS_PATH` · `env.TOKEN_PATH` = **경로 문자열** | `~/.claude/keys/` (번들 제외) | 안전 |
| `atlassian` (프로젝트 9개) | `type` · `url` 뿐 | `.credentials.json` 또는 Keychain (번들 제외) | 안전 |

**경로는 살려야 한다.** 받는 쪽 `_classify_value()` 가 `/Users/yubeen` 을 찾아 TRANSFORM 판정하고
Windows 홈으로 치환하므로, 경로를 지우면 그 기능이 죽는다.

**자격증명이 지날 수 있는 자리는 셋이다.** 지금 문제가 난 곳은 하나지만 구조는 같다.

| 자리 | 지금 상태 | 이 계획의 처리 |
| --- | --- | --- |
| 최상위 `mcpServers[*].headers` · `.env` | context7 에서 실제로 샜다 | **값 치환** |
| **`projects[*].mcpServers[*].headers` · `.env`** | atlassian 은 URL 뿐이라 지금은 비어 있다 | **같은 값 치환** — 구조가 같으므로 함께 막는다 |
| `command` · `args` | 지금은 실행 인자뿐 | 치환하지 않는다. 대신 **번들 전체를 자격증명 패턴으로 스캔하는 위생 테스트**가 덮는다 |

#### 받는 쪽이 덮어쓰는 구조 (실측 2026-09-09)

`plan_apply.py:783` 이 `servers[name] = definition` 으로 **번들 값이 기존 값을 통째로 덮는다.**
센티널을 담기만 하면 **받는 PC 에 이미 있던 진짜 키가 센티널로 덮인다.**
그래서 목표 2(기존 값 보존)가 함께 필요하다.

#### 구글시트에는 별개의 구멍이 하나 더 있다

`keys/` 의 두 파일은 성격이 다른데 문서가 구분하지 않는다.

| 파일 | 받는 PC 에서 |
| --- | --- |
| `sheets-mcp-token.json` (782B) | 동의화면이 「테스트」라 7일 만료 → **재인증하면 생긴다** |
| `sheets-mcp-oauth.json` (405B) | Google Cloud Console 에서 받은 **클라이언트 시크릿** → **재인증으로 생기지 않는다.** 따로 옮기거나 Console 에서 다시 내려받아야 한다 |

지금 스킬 문서는 「받는 PC 에서 새로 만든다」라고만 해서, 받는 사람이 재인증만 시도하다 막힌다.

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절, 「예외 — `claude-config/` 와 두 하네스 스킬」 절
- 전역 `~/.claude/CLAUDE.md` — 수술적 변경, 「만들기 전에 사다리를 오른다」, 주석 규칙
- `~/.claude/rules/python.md` — 타입 힌트, `Path` 객체, 예외 구분(`ValueError` / `RuntimeError`)
- `tests/CLAUDE.md` — Given-When-Then, 파일 격리, 결정적 테스트
- `.claude/skills/claude-config-export/SKILL.md` · `.claude/skills/claude-config-import/SKILL.md`

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 기능 요구사항 충족 (목표 1~4)
- [x] 회귀/신규 테스트 추가 — 평문 키가 번들에 들어가면 **실패하는** 테스트가 있다
      (실제로 구현 전 `test_real_bundle_claude_json_has_no_secret_pattern` 이 실물 키를 잡아 실패했다)
- [x] 번들을 재생성한 뒤 `grep -rE '(sk-|ctx7sk|ghp_|AKIA|-----BEGIN|xox[baprs]-)' claude-config/` 가 **0건**
- [x] `poetry run python validate_project.py` 통과 (passed=1059, failed=0, skipped=0)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — 두 SKILL.md 갱신, 루트 `CLAUDE.md` 근거 승격.
      `docs/COMMANDS.md` **변경 없음**, `docs/INDEX.md` **변경 없음**
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결정 근거·실측 수치를 루트 `CLAUDE.md` 의 프로젝트 설정 절이 정한 목적지로 이관.
      `/impl-plan` 스킬 "근거 승격" 참고)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `.claude/skills/claude-config-export/export.py` — 센티널 상수, 치환 함수, 호출부, `EXCLUSION_NOTICE` 한 줄
- `.claude/skills/claude-config-export/SKILL.md` — 자격증명 절에 claude.json 값 치환 추가
- `.claude/skills/claude-config-import/plan_apply.py` — 센티널 상수, 복원 함수, `classify_claude_json` · `merge_claude_json` 반영
- `.claude/skills/claude-config-import/SKILL.md` — 센티널 안내, 구글시트 두 파일 구분
- `tests/test_claude_config_bundle.py` — 치환 계약 + 실물 번들 위생 검사 추가
- `tests/test_claude_config_import.py` — **신규**. 복원 계약과 양쪽 센티널 일치 고정
- `claude-config/**` — 번들 재생성 산출물 (사람이 손으로 고치지 않는다)
- `docs/COMMANDS.md`: **변경 없음** — 실행 명령어와 CLI 옵션이 바뀌지 않는다
- `docs/INDEX.md`: **변경 없음** — 새로 만드는 것은 `tests/` 파일 하나이고 INDEX 는 `docs/`·`reference/` 의 지도다

### 데이터/결과 영향

- **측정 결과(`docs/research/`·`docs/strategy/`)에 영향 없음.** 이 작업은 하네스 설정 이관 경로만 건드린다
- 번들 `claude_json.json` 의 내용이 바뀌므로 `MANIFEST.json` 의 `generated_at` 이 갱신된다.
  매니페스트의 **항목 해시는 `home/**` 파일만 담으므로 바뀌지 않는다**
- **다만 받는 쪽 `decisions/` 가 쓰는 해시는 바뀐다.** `classify_claude_json()` 이 서버 정의를
  `_hash_value(definition)` 로 해싱하므로 치환된 서버의 해시가 달라진다.
  그 항목들은 `needs_confirmation=False` 인 APPLY·TRANSFORM 판정이라 **사용자에게 다시 묻지는 않는다** —
  승인이 필요한 것은 훅과 없는 저장소뿐이다

## 6) 단계별 계획(Phases)

### Phase 0 — 인바리언트를 테스트로 먼저 고정(레드)

> 해당 사유: **에러 처리·보안 정책의 추가**다. 「무엇이 번들에 들어가면 안 되는가」는
> 이 기능의 핵심 계약이고, 지금 그 계약이 claude.json 경로에서 비어 있다.

**작업 내용**:

- [x] `tests/test_claude_config_bundle.py` 에 치환 계약 테스트 추가
  - [x] `headers` 의 비경로 값이 센티널로 바뀐다
  - [x] `env` 의 절대경로 값은 **그대로 남는다** (`CREDENTIALS_PATH` · `TOKEN_PATH` 회귀 방지)
  - [x] **`projects[*].mcpServers` 안의 `headers`/`env` 도 같게 치환된다** — 최상위와 구조가 같다
  - [x] `type` · `url` · `command` · `args` 등 `headers`/`env` 밖의 키는 건드리지 않는다
  - [x] 치환한 항목의 **키 경로 목록**을 함께 돌려준다 (사용자 보고용)
  - [x] 경계: **상대경로 값은 치환된다** (절대경로만 남긴다 — 판정을 좁게 잡아 안전 쪽으로 둔다)
  - [x] 경계: **문자열이 아닌 값**(숫자·bool·null)은 그대로 둔다 — 자격증명이 아니고, 치환하면 타입이 깨진다
  - [x] 경계: `headers`·`env` 가 없는 서버 정의를 넣어도 예외 없이 그대로 나온다
  - [x] 실물 번들 위생 — `claude_json.json` **전체**를 자격증명 패턴으로 스캔해 0건임을 고정한다
        (`headers`/`env` 로 한정하지 않는다. **`args` 처럼 치환 대상 밖의 자리도 이 검사가 덮는다**).
        번들이 있을 때만 검사한다 — 기존 실물 검사와 같은 방식이며 `pytest.skip` 을 쓰지 않는다
- [x] `tests/test_claude_config_import.py` 신규 — 복원 계약
  - [x] 번들 값이 센티널이고 **기존 값이 있으면** 기존 값이 남는다
  - [x] 번들 값이 센티널이고 **기존 값이 없으면** 센티널이 남고 그 키가 「채워야 할 목록」에 든다
  - [x] 센티널이 아닌 값은 번들 값이 이긴다 (기존 동작 유지)
  - [x] 기존 서버에 없던 필드는 그대로 추가된다
  - [x] 경계: 기존에 **그 서버 자체가 없는** PC 에서도 예외 없이 동작한다 (최초 설치)
  - [x] 경계: `headers` 안의 **일부만** 센티널일 때 나머지는 번들 값이 그대로 들어간다
  - [x] **양쪽 모듈의 센티널 상수가 같다** — 두 스킬은 서로 import 하지 않으므로 테스트가 일치를 집행한다
  - [x] 파일 격리 — 이 테스트는 **실경로 `~/.claude.json` 을 읽지도 쓰지도 않는다** (`tests/CLAUDE.md` 5절)
- [x] 복원 함수의 **키 경로 표기를 확정**했다 — 순수 함수는 서버 정의 하나만 보므로
      `headers.API_KEY` 처럼 **필드 경로만** 돌려주고, 서버 이름은 호출부가 붙인다

**Validation**:

- [x] 추가한 테스트가 **구현 전에 실패**함을 확인한다 (레드) — **21 failed, 48 passed**.
      실패 20건은 `AttributeError`(함수 없음)이고, `test_real_bundle_claude_json_has_no_secret_pattern`
      1건은 **실제 번들의 평문 키를 잡아** 실패했다 — 잡아야 할 것을 잡는다

---

### Phase 1 — export 쪽 구현 (그린)

**작업 내용**:

- [x] `REDACTED_SENTINEL` 상수 추가 (고정 문자열 하나) — `__CLAUDE_CONFIG_REDACTED__`
- [x] `redact_credentials(claude_json) -> tuple[dict, list[str]]` 순수 함수 추가
  - **허용목록 방식**: 최상위 `mcpServers[*]` 와 `projects[*].mcpServers[*]` 양쪽의
    `headers` · `env` 값 중 **문자열이면서 절대경로가 아닌 것을 전부** 치환한다
  - 경로 판정: 절대경로 모양(`/…` · `~…` · `C:/…`)이면 남긴다
  - **원본을 변경하지 않는다** — 사본을 만들어 돌려준다 (`~/.claude/rules/python.md` 데이터 불변성)
- [x] `export_bundle()` 이 `extract_claude_json()` 결과에 이 함수를 적용해 쓰게 한다
      — **가리는 일은 호출자(`main()`)가 한다.** `export_bundle()` 안에서 가리면 파일을 쓰지 않는
      dry-run 경로에서 무엇을 가렸는지 알 수 없다
- [x] 치환한 키 경로를 `_report()` 출력에 넣는다 — **무엇을 가렸는지 그 자리에서 보이게 한다**
- [x] **`--dry-run` 에서도 치환 목록이 나오게 한다.** 지금 dry-run 경로는 `extract_claude_json()` 을
      부르지 않아 claude.json 을 아예 보지 않는다. dry-run 의 목적이 「담기면 안 되는 것이 섞였는지
      **파일을 쓰기 전에** 보는 것」이므로 여기서 안 보이면 가드로서 뜻이 없다
- [x] `EXCLUSION_NOTICE` 에 claude.json 값 치환을 한 줄 추가 (README 에 자동 반영된다)

**Validation**:

- [x] Phase 0 의 export 쪽 테스트가 통과한다 — **60 passed**. 남은 1건은 실물 번들 위생 검사이며
      재생성 전이라 실패한 것이고, 재생성 후 통과했다
- [x] `--dry-run` 출력에 치환 목록이 나오는지 확인한다 (파일을 쓰지 않는 상태에서) —
      `가린 자격증명 값: 1개 / mcpServers.context7.headers.CONTEXT7_API_KEY`
- [x] 번들을 재생성하고 `claude_json.json` 을 눈으로 대조한다 — 키는 센티널로, 경로 2개는 그대로.
      `grep -rE '(sk-|ctx7sk|ghp_|AKIA|-----BEGIN|xox[baprs]-)' claude-config/` **0건**

---

### Phase 2 — import 쪽 구현 (그린)

**작업 내용**:

- [x] `REDACTED_SENTINEL` 상수 추가 (export 와 같은 값)
- [x] `restore_redacted(bundle_definition, existing_definition)` 순수 함수 추가
  - 서버 정의 하나를 받아 **복원된 정의**와 **채워야 할 키 목록**을 돌려준다
  - 센티널 자리에 기존 값이 있으면 되돌리고, 없으면 센티널을 남기고 그 키를 알린다
  - **순수 함수로 두는 이유**: 파일 I/O 없이 계약을 고정할 수 있고, 테스트가 실경로
    `~/.claude.json` 을 건드리지 않는다 (`tests/CLAUDE.md` 5절 파일 격리)
- [x] `merge_claude_json()` 이 서버 정의를 넣기 전에 이 함수를 거치게 한다
  - 최상위 `mcpServers` 와 `projects[*].mcpServers` **양쪽**에 적용한다
- [x] `classify_claude_json()` 이 **판정 단계에서** 알리게 한다 — 적용 후에 알면 늦다
  - 기존 값이 있으면 「이 PC 의 기존 값을 유지합니다」
  - 없으면 「이 PC 에서 직접 채워야 합니다」
  - **이를 위해 판정 단계가 기존 `~/.claude.json` 을 읽어야 한다.** 지금 이 함수는 번들과
    `environment` 만 받으므로 **기존 설정을 인자로 받도록 시그니처를 넓힌다** —
    함수 안에서 실경로를 직접 읽으면 테스트가 사용자 홈을 건드리게 된다
  - 파일이 없는 PC(최초 설치)에서는 빈 dict 로 다루고 예외를 내지 않는다
  - 시그니처가 바뀌므로 **호출부 `build_plan()` 도 함께 고친다** (그곳이 실경로를 읽어 넘긴다)
- [x] `apply_plan()` 의 수행 요약에 「채워야 할 항목」을 남긴다
- [x] **`render_plan()` 에 「그대로 적용하되 알아둘 것」 절 추가** — 계획에 없던 보완이다.
      사유에 안내를 담았는데 **화면에 나오지 않아 실제로는 알리지 못하고 있었다**:
      `render_plan()` 은 TRANSFORM·EXCLUDE 의 사유만 출력하고 APPLY 는 개수만 세는데,
      경로가 없는 context7 은 APPLY 로 판정된다. APPLY 는 원래 사유가 비어 있으므로
      **사유가 붙은 APPLY 항목**을 뽑는 것으로 일반화했다

**Validation**:

- [x] Phase 0 의 import 쪽 테스트가 통과한다 — 두 파일 합쳐 **69 passed**
- [x] `plan_apply.py` 를 인자 없이 실행해 판정표에 안내가 나오는지 확인한다 (`--apply` 없이) —
      `claude_json.json#mcpServers.context7 — 이 PC 의 기존 값을 유지합니다
      (context7.headers.CONTEXT7_API_KEY)`. 이 mac 에는 진짜 키가 있으므로 「유지」가 맞다

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [x] `.claude/skills/claude-config-export/SKILL.md` 「무엇을 담지 않는가 — 자격증명」에 claude.json 값 치환 추가
      (「무엇을 담는가」 표의 `~/.claude.json` 행에도 표시)
- [x] `.claude/skills/claude-config-import/SKILL.md` 에 두 가지 추가
  - [x] 센티널이 남은 항목은 그 PC 에서 채운다
  - [x] 구글시트 `keys/` 두 파일의 차이 — 토큰은 재인증으로 생기고, **OAuth 클라이언트는 생기지 않는다**
        (같은 표를 export 쪽에도 넣었다 — 「토큰은 7일 만료라 재인증하면 된다」는 기존 문장이
        클라이언트 시크릿까지 그런 것처럼 읽혀 **부정확했다**)
- [x] 번들 재생성 후 `grep -rE '(sk-|ctx7sk|ghp_|AKIA|-----BEGIN|xox[baprs]-)' claude-config/` 가 0건인지 확인
- [x] `docs/COMMANDS.md`: **변경 없음** (실행 명령어·CLI 옵션 불변)
- [x] 자동 포맷 적용 — `poetry run black .` (2개 파일 재포맷)
- [x] 근거 승격 — 루트 `CLAUDE.md` 「예외 — `claude-config/` 와 두 하네스 스킬」 절에
      **「경로 기반 판정만으로는 claude.json 을 못 막는다」는 근거**를 남긴다
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

- [x] `poetry run python validate_project.py` (passed=1059, failed=0, skipped=0)
      — Ruff [OK] · PyRight [OK] · Pytest [OK].
      첫 실행에서 Ruff 가 `F402`(루프 변수 `field` 가 `dataclasses.field` import 를 가림)를 잡아
      `field_path` 로 고친 뒤 통과했다

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 하네스 / 번들의 claude.json 자격증명을 센티널로 가리고 받는 쪽이 기존 키를 보존하게 함
2. 하네스 / 경로 기반 판정이 놓치던 MCP 헤더 평문 키를 차단하고 테스트로 고정
3. 하네스 / 전역 설정 번들의 자격증명 유출 경로를 막고 받는 쪽 안내를 보강
4. 하네스 / claude_json.json 값 치환 추가 + 복원 계약 테스트 신설
5. 하네스 / 설정 이관에서 자격증명을 가리고 구글시트 키 파일 구분을 문서화

## 7) 리스크(Risks)

| 리스크 | 완화 |
| --- | --- |
| **허용목록 치환이 자격증명이 아닌 설정값까지 가린다** (`TZ` · `NODE_ENV` 같은 값) | 지금 실물은 경로 2개뿐이라 실제 손해가 없다. 치환 목록을 실행 때마다 출력해 사용자가 그 자리에서 알아채게 한다. 금지목록(이름에 `KEY`·`TOKEN` 포함)을 택하지 않은 이유는 **`TOKEN_PATH` 가 걸려 살려야 할 경로가 죽고**, 새 서버가 다른 이름을 쓰면 조용히 새기 때문이다 |
| **`command`·`args` 로 자격증명이 새면 치환이 막지 못한다** | 이 자리는 실행 인자라 치환하면 서버가 실행되지 않는다. 대신 **번들 전체 패턴 스캔 테스트**가 덮는다. 스캔은 금지목록이라 새 형식의 키를 놓칠 수 있으므로 **치환의 대체가 아니라 그물의 두 번째 겹**이다 |
| **양쪽 센티널 상수가 갈라진다** — 두 스킬은 서로 import 하지 않는다 | 테스트가 두 모듈을 로드해 값 일치를 assert 한다. 갈라지면 품질 검증이 실패한다 |
| 받는 PC 에 기존 키가 없으면 센티널이 그대로 등록돼 MCP 가 깨진 채 남는다 | 서버를 통째로 빼지 않고 센티널을 남기는 쪽을 택했다 — 빼면 「MCP 가 통째로 사라진다」는 스킬 취지에 역행한다. 대신 **판정 단계와 적용 요약 양쪽에서** 채워야 할 항목을 보고한다 |
| `.claude/` 가 PyRight `include` 밖이고(`src`·`tests`·`scripts` 만) `exclude` 에 `**/.*` 가 있어 타입 검사를 받지 않는다 | 기존 두 스크립트와 같은 수준으로 타입 힌트를 유지한다. Ruff 대상 여부는 마지막 Phase 의 `validate_project.py` 가 판정한다 |
| 번들 재생성이 `home/` 을 통째로 지우고 다시 만든다 | 기존 동작이며 이 계획으로 바뀌지 않는다. `decisions/` 는 지우지 않는다 |

## 8) 메모(Notes)

### 확정된 설계 결정

- **치환 판정은 허용목록** — 경로가 아닌 `headers`/`env` 값은 전부 가린다.
  `export.py` 가 파일 판정에서 이미 채택한 철학과 같다(모듈 docstring: "금지목록 방식이면
  Claude Code 가 새 폴더를 만들 때마다 조용히 딸려온다"). **값 판정에도 같은 이유가 적용된다**
- **센티널은 고정 문자열 하나** — 키 이름을 섞어 넣지 않는다. `==` 비교로 끝나고
  해시가 안정적이라 받는 쪽 `decisions/` 재질문이 생기지 않는다
- **복원은 순수 함수** — 파일 I/O 없이 테스트할 수 있고, 실경로 `~/.claude.json` 을 건드리지 않는다
- **키 회전 안 함** — 사용자 결정 (2026-09-09). git 이력·추적 파일 어디에도 없다

### 진행 로그 (KST)

- 2026-09-09 21:07: 계획서 작성. `/claude-config-export` 실행 중 번들에서 평문 API 키 발견,
  유출 여부 실측(git 이력 0건) 후 근원 수정으로 방향 확정
- 2026-09-09 21:20: Phase 0 레드 확인 (21 failed / 48 passed)
- 2026-09-09 21:30: Phase 1·2 구현. 계획에 없던 보완 1건 —
  **사유에만 담고 화면에 출력하지 않아 「판정 단계에서 알린다」가 실제로는 동작하지 않았다.**
  `render_plan()` 에 「그대로 적용하되 알아둘 것」 절을 추가해 고쳤다
- 2026-09-09 21:40: 문서 갱신·근거 승격·최종 검증 완료 (passed=1059, failed=0, skipped=0)

---
