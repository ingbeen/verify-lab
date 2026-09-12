# Implementation Plan: MCP 서버 url 에 실린 자격증명을 가리고, 금지항목 점검이 파일을 남기지 않게 한다

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

**작성일**: 2026-09-12 11:08
**마지막 업데이트**: 2026-09-12 11:08
**관련 범위**: 하네스 (`.claude/skills/claude-config-export/`), 테스트
**관련 문서**: `.claude/skills/claude-config-export/SKILL.md`, `.claude/skills/claude-config-import/SKILL.md`, `tests/CLAUDE.md`, 루트 `CLAUDE.md`

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

- [ ] 목표 1: MCP 서버 정의의 **`url` 에 실린 자격증명**(query 값·userinfo)을 센티널로 가린다
- [ ] 목표 2: 가려도 **받는 쪽에서 서버가 뜨게** 한다 — 접속에 필요한 scheme·host·path 는 남긴다
- [ ] 목표 3: 금지항목 점검이 발동할 때 **저장소에 파일을 남기지 않게** 한다

## 2) 비목표(Non-Goals)

- **파일 판정(`_is_credential`·`should_include`)을 손대지 않는다.** 직전 계획서에서 확정했다
- **금지항목 점검의 「항등식」 성질을 고치지 않는다.** 그 함수의 값어치는 «테스트» 쪽에 있다 —
  `test_real_bundle_has_no_forbidden_entries` 가 **커밋된 번들을 현재 규칙으로 다시 재서** 실제로
  `toast.log` 와 `acme-prd.env.example` 을 잡아냈다. 내보내기 시점의 중복 호출만 무의미하고,
  없애려면 복사 순서를 바꿔야 해 이득보다 위험이 크다
- **`command`·`args` 를 가리지 않는다.** 실행 인자라 가리면 받는 쪽에서 서버가 뜨지 않는다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

`_redact_server` 가 `headers`·`env` 두 블록만 훑는다 ([export.py:487](../../.claude/skills/claude-config-export/export.py#L487)).
**`url` 은 블록이 아니라 문자열 필드라 판정을 아예 거치지 않는다.**

HTTP 형 MCP 서버는 토큰을 url 에 싣는 방식이 흔하다.

```
{"type":"http","url":"https://mcp.vendor.com/mcp?api_key=SECRET"}
{"type":"http","url":"https://user:token@host/mcp"}
```

이 값은 `extract_claude_json` → `redact_credentials` 를 그대로 통과해 `claude-config/claude_json.json`
에 평문으로 실린다. **이 저장소는 PUBLIC 이라 커밋되면 이력에서 지울 수 없다.**

**지금 노출은 없다** — 등록된 두 서버를 실측했다.

| 서버 | url | 판정 |
| --- | --- | --- |
| `context7` | `https://mcp.context7.com/mcp` | 비밀 없음. 키는 `headers` 에 있고 이미 가려진다 |
| `google-sheets` | 없음 (`command`·`args`·`env` 형) | 해당 없음 |

**그래도 닫는 이유**는 이것이 **Context7 키가 실제로 샜던 것과 같은 계층의 구멍**이기 때문이다.
모듈 docstring 이 「자격증명은 허용목록보다 먼저 막는다」고 선언하는데 값 계층에 구멍이 남아 있으면
**선언과 동작이 또 갈린다.** 직전 세 계획서가 파일 계층에서 같은 일을 했다.

### 두 번째 — 점검이 발동하면 파일이 저장소에 남는다

`export_bundle` 은 파일을 `claude-config/home/` 에 **복사한 뒤** 금지항목을 점검하고,
걸리면 `RuntimeError` 를 던진다 ([export.py:765](../../.claude/skills/claude-config-export/export.py#L765)).
그때 **문제의 파일은 이미 저장소 안에 있다.** `MANIFEST`·`README` 가 안 쓰여 「내보내기가 중단됐다」
처럼 보이지만, 실제로는 **`git add` 를 기다리는 자격증명이 디스크에 놓인 상태**다.

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「예외 — `claude-config/` 와 두 하네스 스킬」 절과 「단순화하지 않을 것」(보안 조치)
- `.claude/skills/claude-config-export/SKILL.md` — 절차의 SoT
- `tests/CLAUDE.md` — Given-When-Then, 경계 조건
- 전역 `~/.claude/rules/python.md` — 타입 힌트, 네이밍, 예외 구분

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [ ] `url` 의 query 값과 userinfo 가 센티널로 가려진다
- [ ] **scheme·host·path·query 키는 남는다** — 받는 쪽이 서버에 접속할 수 있다
- [ ] 비밀이 없는 url(`https://mcp.context7.com/mcp`)은 **건드리지 않는다**
- [ ] 가린 항목이 실행 출력과 `replaced` 목록에 나온다 (`mcpServers.<이름>.url` 형태)
- [ ] 프로젝트 스코프 서버에도 적용된다
- [ ] 입력을 제자리에서 고치지 않는다 (기존 `_redact_server` 계약과 같다)
- [ ] 금지항목 점검이 발동하면 **번들 폴더를 지우고** 예외를 던진다
- [ ] 번들을 다시 만들어 **36개 구성이 그대로**이고 `claude_json.json` 이 바뀌지 않음을 확인했다
- [ ] 양쪽 `SKILL.md` 가 **실제 가림 범위**와 일치한다
- [ ] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [ ] `poetry run python validate_project.py` 통과 (failed=0, skipped=0; passed/failed/skipped 수 기록)
- [ ] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [ ] 필요한 문서 업데이트 — `docs/COMMANDS.md` 변경 없음 / 양쪽 `SKILL.md` 갱신
- [ ] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
- [ ] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `.claude/skills/claude-config-export/export.py` — `_redact_server` 에 url 처리, `export_bundle` 의 점검 실패 처리
- `.claude/skills/claude-config-export/SKILL.md` · `claude-config-import/SKILL.md` — 가림 범위 (근거 승격)
- `tests/test_claude_config_bundle.py` — url 가림 케이스
- `claude-config/**` — 번들 재생성 산출물 (내용 불변 예상)
- `docs/COMMANDS.md`: **변경 없음**

### 데이터/결과 영향

- **측정·검증 산출물에 영향 없음**
- **번들 내용이 바뀌지 않아야 한다** — 현재 두 서버 모두 url 에 비밀이 없다.
  `claude_json.json` 이 달라지면 조사 대상이다

## 6) 단계별 계획(Phases)

### Phase 0 — url 가림 계약을 테스트로 먼저 고정(레드)

**작업 내용**:

- [ ] query 에 실린 토큰이 가려지는지 고정한다 (`?api_key=SECRET` → 키는 남고 값만 센티널)
- [ ] userinfo 가 가려지는지 고정한다 (`https://user:token@host/mcp`)
- [ ] **비밀 없는 url 은 그대로**인지 고정한다 (`https://mcp.context7.com/mcp`)
- [ ] 프로젝트 스코프 서버에도 걸리는지 고정한다
- [ ] 입력을 제자리에서 고치지 않는지 고정한다
- [ ] 이 시점에서 새 테스트가 **실패**하는 것을 확인한다 (레드)

---

### Phase 1 — 구현(그린 유지)

**작업 내용**:

- [ ] `_redact_url` 을 만든다 — `urlsplit` 으로 쪼개 query 값과 userinfo 만 센티널로 바꾸고 다시 합친다
- [ ] `_redact_server` 가 그것을 부르고 `url` 을 가린 필드 목록에 넣는다
- [ ] 금지항목 점검 실패 시 `BUNDLE_HOME_DIR` 를 지운 뒤 예외를 던진다
- [ ] Phase 0 의 테스트가 통과하는지 확인한다 (그린)

---

### 마지막 Phase — 번들 재생성, 문서 정리 및 최종 검증

**작업 내용**

- [ ] 번들을 다시 만들고 `claude_json.json` 과 항목 36개가 **그대로**인지 기계로 확인한다
- [ ] 양쪽 `SKILL.md` 의 자격증명 «값» 절에 url 을 더한다 — **무엇을 남기고 무엇을 가리는지**
- [ ] `docs/COMMANDS.md` — **변경 없음**
- [ ] 자동 포맷 적용 (`poetry run black .`)
- [ ] 변경 기능 및 전체 플로우 최종 검증
- [ ] DoD 체크리스트 최종 업데이트 및 체크 완료
- [ ] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

> 순서를 지킨다 — 리뷰에서 고치면 코드가 바뀌므로 품질 검증이 마지막 관문이어야 한다.

- [ ] `/code-review xhigh` (발견 N건 · 조치 기록)
- [ ] `poetry run python validate_project.py` (passed=N, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 하네스 / MCP url 에 실린 자격증명을 가리고 접속 정보만 남긴다
2. 하네스 / 값 가림이 headers·env 만 보던 것을 url 까지 넓힌다
3. 하네스 / url 쿼리와 userinfo 를 센티널로 바꾸고 점검 실패 시 번들을 지운다
4. 하네스 / Context7 키가 샜던 계층의 마지막 구멍을 막는다
5. 하네스 / MCP 값 가림 범위 확장 + 금지항목 점검의 뒷정리

## 7) 리스크(Risks)

| 리스크 | 완화 |
| --- | --- |
| **query 를 통째로 가려 정상 파라미터가 죽는다** | 비밀이 아닌 query 도 가려지지만 **키는 남으므로** 받는 쪽이 무엇을 채워야 하는지 안다. 기존 `headers`·`env` 가 이미 「절대경로가 아닌 값은 전부 가린다」는 허용목록 방식이라 **같은 규율**이다 |
| url 을 다시 합치며 모양이 달라진다 | 비밀이 없으면 **손대지 않고 원본을 그대로 돌려준다.** 현재 두 서버가 그 경우이며 번들 불변으로 확인한다 |
| 점검 실패 시 폴더를 지워 디버깅이 어려워진다 | 예외 메시지에 **무엇이 걸렸는지** 경로가 들어간다. 자격증명이 저장소에 남는 쪽이 훨씬 나쁘다 |

## 8) 메모(Notes)

### 설계 결정과 탈락안

| 안 | 판정 | 근거 |
| --- | --- | --- |
| **query 값·userinfo 만 가리고 나머지는 남긴다** | **채택** | 받는 쪽이 서버에 접속할 수 있어야 한다. `command`·`args` 를 안 가리는 이유와 같은 논리다 |
| url 전체를 센티널로 바꾼다 | 탈락 | 받는 쪽에서 **서버가 뜨지 않는다.** 복원 로직은 기존 값이 있을 때만 되돌리므로 새 PC 는 접속 정보를 잃는다 |
| url 에 비밀이 있는지 «패턴»으로 판별한다 (`token`·`key` 가 든 키만) | 탈락 | 이름 패턴으로 고르지 않는 것이 이 모듈의 규율이다 — 구글시트의 `TOKEN_PATH` 가 걸려 **살려야 할 경로가 죽은** 전례가 있고, 새 서버가 다른 이름을 쓰면 조용히 샌다 |
| 금지항목 점검을 복사 «앞» 으로 옮긴다 | 탈락 | 같은 술어를 같은 경로에 적용하므로 **여전히 항등식**이다. 순서만 바꾸고 얻는 것이 없다 |

### 실측으로 전제가 뒤집힌 것 — 받는 쪽을 고치지 않으면 «더 나빠진다»

계획은 내보내기만 고치는 것이었다. **코드 리뷰가 그것이 반쪽임을 드러냈다.**

`restore_redacted` 와 `_sentinel_fields` 는 `headers`·`env` 만 훑고 **`value == REDACTED_SENTINEL`
완전일치**로 판정한다([plan_apply.py:494](../../.claude/skills/claude-config-import/plan_apply.py#L494)).
그런데 **url 은 센티널이 문자열 «안에» 박힌다**(query 값만 바뀌므로). 그래서

- 받는 쪽이 url 을 **되돌리지 못하고** → 번들의 센티널 url 이 **작동 중인 url 을 덮는다**
- `_sentinel_fields` 도 못 봐서 **「채워야 할 항목」에도 안 나온다** → 서버가 조용히 죽는다

**가리지 않는 것보다 나쁘다.** 그래서 비목표를 넘어 받는 쪽도 고쳤다 — 되돌릴 때 조각을
꿰맞추지 않고 **이 PC 의 url 을 통째로** 쓴다. 어느 조각이 가려졌는지와 무관하게 그쪽이 진실이다.

**이 결함이 그린으로 통과한 이유가 테스트 배치에 있었다** — 내보내기 쪽 테스트 5개를 추가하고
**받는 쪽은 0개**였다. 왕복을 고정하는 파일(`tests/test_claude_config_import.py`)에 3개를 넣었다.

### 같은 리뷰에서 함께 고친 것 다섯

| 무엇 | 실측 | 고친 내용 |
| --- | --- | --- |
| url 의 **fragment** 를 안 가렸다 | OAuth 가 `#access_token=` 으로 토큰을 싣는 자리다 | 통째로 가린다. **MCP 접속에 쓰이지 않아** 지워도 잃을 것이 없다 |
| url query 의 **경로 값**을 가려 버렸다 | `?credentials=/Users/x/.claude/keys/o.json` 이 센티널이 되어 받는 쪽 경로 치환이 되돌릴 것을 잃는다 | `_redact_server` 와 같은 규율로 **절대경로는 남긴다** |
| 🔴 **`token`·`secret` 이 표식에 없었다** | **이 PC 의 실제 자격증명이 그 이름이다** (`keys/sheets-mcp-token.json`). 허용 폴더 밖에 쓰이면(`tools/msg/token.json`) 막을 것이 없었다 | 표식에 더했다 |
| 🔴 **자격증명을 «폴더로 묶으면» 빠져나갔다** | `db/credentials/prod.json` · `tools/secrets/api.json` 이 담겼다 — 이름 판정은 파일명만 본다 | 폴더 표식에 `credentials`·`secrets` 를 더했다 |
| `lock` 을 조각 판정에 넣어 **의존성 고정 파일이 죽었다** | `poetry.lock`·`uv.lock` 이 조용히 사라진다. 옛 규칙은 도트파일 `.lock` 하나만 막았다 | 조각 판정에서 빼고 **이름 완전일치**로 되돌렸다(대소문자만 보강) |

### 남겨 둔 것

| 무엇 | 왜 |
| --- | --- |
| **url 의 경로 구간은 못 가린다** | 어느 구간이 키인지 **구조로 판별할 수 없고** 통째로 가리면 서버가 죽는다. 경로에 키를 넣는 API 가 실제로 있으므로(ECOS — `src/verify_lab/CLAUDE.md`) **사람이 확인해야 한다**는 사실을 SKILL.md 와 받는 쪽 안내문에 적었다 |
| `DOCUMENT_SUFFIXES` 를 자격증명·로그가 **공유한다** | 로그 쪽 사정으로 `txt` 를 넣으면 자격증명이 샌다. 지금은 양쪽 주석이 서로를 가리키고 있으나 **상수를 둘로 쪼개는 것이 옳다** — 별건 |
| 조각 쪼개기가 `_is_credential` 과 `should_include` 에 **두 벌** | 이미 둘이 다르다(자격증명만 `-`·`_` 로도 쪼갠다). 공용 헬퍼로 묶는 것이 옳으나 판정 변경이 아니라 구조 변경이라 별건 |

### 진행 로그 (KST)

- 2026-09-12 11:08: 계획서 작성. 등록된 두 서버를 실측해 **현재 노출 0** 을 확인하고 예방 목적임을 명시
- 2026-09-12 11:3x: 리뷰가 **반쪽 구현**(받는 쪽 미복원)을 잡아 비목표를 넘어 `plan_apply.py` 까지 고침. 왕복 테스트 3개 추가
