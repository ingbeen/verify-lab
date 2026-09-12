# Implementation Plan: 내보내기 필터의 남은 구멍 셋을 닫고 정리 스킬의 자동호출 차단을 되살린다

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

**작성일**: 2026-09-12 10:24
**마지막 업데이트**: 2026-09-12 10:24
**관련 범위**: 하네스 (`.claude/skills/claude-config-export/`, `.claude/skills/clean-results/`), 테스트
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

- [ ] 목표 1: **견본 예외를 없앤다** — `acme-prd.env.example` 을 더 이상 내보내지 않는다
- [ ] 목표 2: 자격증명 판정이 **구분자(하이픈·밑줄)** 로 이어진 이름도 막게 한다
- [ ] 목표 3: 로그·상태 파일 판정을 자격증명과 **같은 규율**로 통일한다 (대소문자·도트파일·로테이트)
- [ ] 목표 4: `clean-results` 스킬의 `disable-model-invocation: true` 를 되살린다

## 2) 비목표(Non-Goals)

- **허용목록(`ALLOW_TOP_LEVEL_DIRS`)을 좁히지 않는다**
- **`~/.claude` 의 파일을 고치거나 지우지 않는다.** 원본 `acme-prd.env.example` 은 mac·이 PC 모두 그대로 둔다 — 받는 쪽이 파일을 지우지 않으므로 내보내지 않는 것만으로 충분하다
- **이미 공개된 git 이력을 재작성하지 않는다.** 사용자 영역이며 이번 변경으로 바뀌지 않는다
- **병행 작업(손절 컬럼 통합)에 손대지 않는다.** 워킹트리에 섞여 있으나 이 계획의 범위가 아니다
- **`clean-results` 의 본문·동작을 고치지 않는다.** 지워진 frontmatter 한 줄만 되살린다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

직전 계획서(`PLAN_credential_dotfile_hole`)가 자격증명 판정을 토큰 방식으로 고쳤으나, 코드 리뷰가 **같은 계열의 구멍 셋**을 더 찾았고 실행으로 확인했다.

**① 구분자를 넘지 못한다** — 판정이 `.` 으로만 쪼갠다.

```
담긴다   db/.env-prod · db/.env_old · db/env_local
담긴다   db/id_rsa_backup · db/credentials-prod.json · db/.npmrc-backup
```

**② 견본 예외가 운영 정보를 실어 나른다.** `db/acme-prd.env.example` 에 운영 DB 의
host·port·name 3개가 채워져 있다(빈 키 2개는 계정·비밀번호). 예외를 규칙(`.example` 이면 통과)
으로 두었더니 우회로가 되어 경로 목록으로 바꿨는데, **그 목록에 담을 값어치가 있는 파일이
애초에 없다.**

**③ 로그·상태 파일은 아직 `.suffix` 로 판정한다** — 자격증명에서 걷어낸 바로 그 방식이
같은 파일 20여 줄 아래 남아 있다.

```
담긴다   hooks/.log · hooks/toast.LOG · db/audit.JSONL · hooks/.LOCK · hooks/toast.log.1
```

**④ `clean-results` 의 자동호출 차단이 사라졌다.** `disable-model-invocation: true` 가 지워져
**산출물 폴더를 지우는 스킬을 모델이 스스로 부를 수 있는 상태**다. 이 세션이 시작될 때 git 은
clean 이었고 이 변경은 이 세션의 작업이 아니다. 지금 `.claude/skills/` 전체에 그 플래그를 가진
스킬이 하나도 없다.

### 구분자를 넓히면 정상 파일이 죽는 문제 — 해결됐다

직전 계획서는 이 구멍을 「넓히면 `key-rotation-guide.md` 가 죽는다」는 이유로 남겨 두었다.
**문서·코드 확장자 탈출구**가 그 충돌을 없앤다 — 마지막 확장자가 `md`·`py`·`sh`·`txt`·`rst`
이면 자격증명으로 보지 않는다. 사람이 읽는 문서와 실행 코드는 자격증명 파일이 아니다.

프로토타입 실측(2026-09-12, 자격증명 26건 · 정상 4건):

```
설계 검증 어긋남: 없음
실제 번들 37개 중 새로 막히는 것: ['db/acme-prd.env.example']
```

**덤으로 `tools/env.py` 가 되살아난다** — 직전 계획서에서 `key.json` 을 막기 위해 포기했던
케이스다. 두 목표가 충돌하지 않는 길이 있었다.

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「예외 — `claude-config/` 와 두 하네스 스킬」 절과 「단순화하지 않을 것」(보안 조치)
- `.claude/skills/claude-config-export/SKILL.md` — 절차의 SoT
- `tests/CLAUDE.md` — Given-When-Then, 경계 조건
- 전역 `~/.claude/rules/python.md` — 타입 힌트, 네이밍, 예외 구분

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [ ] 구분자로 이어진 자격증명 6종이 전부 막힌다
- [ ] 로그·상태 파일 5종(도트파일·대문자·로테이트)이 전부 막힌다
- [ ] **`db/acme-prd.env.example` 이 더 이상 담기지 않는다** — 번들 **36개**
- [ ] 그 외 **36개 구성이 직전 번들과 같다** — 정상 파일이 새로 막히지 않았다
- [ ] `db/api-key-format.md` · `db/key-rotation-guide.md` · `tools/env.py` · `hooks/changelog.md` 가 계속 담긴다
- [ ] 견본 예외 기제가 **코드에서 사라졌다** (죽은 코드를 남기지 않는다)
- [ ] `clean-results/SKILL.md` 의 `disable-model-invocation: true` 가 되살아났다
- [ ] 양쪽 `SKILL.md` 와 `EXCLUSION_NOTICE` 가 **실제 판정과 일치**한다
- [ ] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [ ] `poetry run python validate_project.py` 통과 (failed=0, skipped=0; passed/failed/skipped 수 기록)
- [ ] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [ ] 필요한 문서 업데이트 — `docs/COMMANDS.md` 변경 없음 / 양쪽 `SKILL.md` 갱신
- [ ] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (확장자 탈출구의 근거와 견본 예외를 없앤 이유를 `SKILL.md` 로 이관)
- [ ] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `.claude/skills/claude-config-export/export.py` — 판정 상수와 `_is_credential`·`should_include`
- `.claude/skills/claude-config-export/SKILL.md` — 「빠지는 것」과 근거 (근거 승격)
- `.claude/skills/claude-config-import/SKILL.md` — 미러 표 두 행
- `.claude/skills/clean-results/SKILL.md` — frontmatter 한 줄 복원
- `tests/test_claude_config_bundle.py` — 구분자·로그·정상 파일 케이스
- `claude-config/**` — 번들 재생성 산출물 (37 → 36)
- `docs/COMMANDS.md`: **변경 없음** — 실행 명령어와 CLI 옵션이 바뀌지 않는다

### 데이터/결과 영향

- **측정·검증 산출물에 영향 없음.** `storage/` 를 건드리지 않는다
- **번들이 36개로 준다.** 줄어드는 것은 `db/acme-prd.env.example` 하나이며 **의도된 결과**다.
  다른 것이 줄면 정상 파일을 새로 막은 것이므로 조사 대상이다
- **받는 PC 는 아무것도 잃지 않는다.** `plan_apply.py` 는 `shutil.copy2` 만 하고 삭제를 하지
  않으므로(실측 — `unlink`·`rmtree` 없음) mac 의 `acme-prd.env.example` 은 그대로 남는다

## 6) 단계별 계획(Phases)

### Phase 0 — 세 구멍과 회귀 방지선을 테스트로 먼저 고정(레드)

> 이 Phase 를 두는 이유: 이 판정은 **PUBLIC 저장소로의 유출을 막는 마지막 관문**이고,
> 이번에는 판정을 넓히므로 **「무엇이 계속 담기는가」가 더 중요해진다.**

**작업 내용**:

- [ ] `CREDENTIAL_PATHS` 에 구분자 6종을 넣는다 (`db/.env-prod` · `db/.env_old` · `db/env_local` · `db/id_rsa_backup` · `db/credentials-prod.json` · `db/.npmrc-backup`)
- [ ] `CREDENTIAL_PATHS` 에서 `db/acme-prd.env.example` 을 **막히는 쪽으로 옮긴다** — `INCLUDED_PATHS` 에서 뺀다
- [ ] `EXCLUDED_PATHS` 에 로그·상태 5종을 넣는다 (`hooks/.log` · `hooks/toast.LOG` · `hooks/toast.log.1` · `db/audit.JSONL` · `hooks/.LOCK`)
- [ ] **회귀 방지**: `INCLUDED_PATHS` 에 `db/key-rotation-guide.md` · `tools/env.py` 를 넣는다 — 확장자 탈출구의 감시자다
- [ ] 이 시점에서 새 테스트가 **실패**하는 것을 확인한다 (레드)

---

### Phase 1 — 판정 구현(그린 유지)

**작업 내용**:

- [ ] 자격증명 표식을 **`.`·`-`·`_` 로 쪼갠 조각** 전체와 맞춘다
- [ ] **문서·코드 확장자 탈출구**를 둔다 (`md`·`py`·`sh`·`txt`·`rst`) — 사람이 읽는 문서와 실행 코드는 자격증명이 아니다. 이것이 구분자 분리를 안전하게 만드는 장치다
- [ ] 이름 목록을 **구분자 경계까지** 맞춘다 (`id_rsa_backup` · `.npmrc-backup`)
- [ ] `credentials` 를 표식에 더한다 (`credentials-prod.json`)
- [ ] **견본 예외 기제를 지운다** — `CREDENTIAL_TEMPLATE_ALLOWLIST` 와 그 검사. 담을 것이 없어졌으므로 죽은 코드를 남기지 않는다. 왜 예외를 두지 않는지는 `SKILL.md` 가 근거와 함께 갖는다
- [ ] 로그·상태 판정을 **같은 조각 방식**으로 바꾼다 (`log`·`jsonl`·`lock`). `.` 만으로 쪼갠다 — 자격증명과 달리 넓힐 필요가 확인되지 않았다
- [ ] Phase 0 의 테스트가 통과하는지 확인한다 (그린)

---

### Phase 2 — 정리 스킬의 자동호출 차단 복원

> 자격증명 판정과 문맥이 완전히 다르므로 Phase 를 나눈다.

**작업 내용**:

- [ ] `.claude/skills/clean-results/SKILL.md` frontmatter 에 `disable-model-invocation: true` 를 되살린다
- [ ] 그 플래그가 붙은 스킬이 다시 존재하는지 확인한다

---

### 마지막 Phase — 번들 재생성, 문서 정리 및 최종 검증

**작업 내용**

- [ ] `--dry-run` 으로 **36개**이고 빠진 것이 `db/acme-prd.env.example` 하나인지 확인한다
- [ ] 번들을 다시 만들고 직전 번들과 **기계로 대조**한다
- [ ] `EXCLUSION_NOTICE` 를 실제 판정과 맞춘다 — 확장자 탈출구와 견본 예외 없음을 적는다
- [ ] 양쪽 `SKILL.md` 갱신 — **왜 견본 예외를 두지 않는지**(규칙은 우회로가 됐고 목록은 담을 것이 없었다)와 **확장자 탈출구의 근거**
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

1. 하네스 / 내보내기 필터를 구분자까지 넓히고 견본 예외를 없앤다
2. 하네스 / 자격증명·로그 판정을 한 규율로 통일하고 운영 정보가 든 견본을 뺀다
3. 하네스 / 확장자 탈출구로 구분자 구멍을 막고 clean-results 자동호출을 다시 차단한다
4. 하네스 / `.env-prod` 계열과 대문자 로그가 번들에 담기던 것을 막는다
5. 하네스 / 내보내기 필터 구멍 셋 봉쇄 + 정리 스킬 안전장치 복원

## 7) 리스크(Risks)

| 리스크 | 완화 |
| --- | --- |
| **판정을 넓혀 정상 파일이 조용히 빠진다** | 이쪽이 유출보다 조용한 실패다. 확장자 탈출구를 두고, 번들 구성을 **기계로 대조**해 줄어드는 것이 견본 하나뿐임을 확인한다. `key-rotation-guide.md`·`env.py` 를 테스트로 고정한다 |
| 확장자 탈출구가 새 우회로가 된다 (`secret.env.md`) | 이론상 가능하나 **견본 예외와 성질이 다르다** — `.md`·`.py` 는 자격증명 로더가 읽는 형식이 아니라 실수로 놓일 이유가 없다. 번들 전체 패턴 스캔이 2차 방어로 남는다 |
| mac 이 `acme-prd.env.example` 를 잃는다 | **잃지 않는다.** 받는 쪽은 `shutil.copy2` 만 하고 삭제하지 않는다(실측). 번들에서 빠질 뿐 mac 의 파일은 그대로다 |
| 로그 판정을 조각 방식으로 바꿔 `changelog.md` 가 막힌다 | 조각 «전체 일치» 라 `changelog` ≠ `log` 다. 이미 `INCLUDED_PATHS` 에 있어 테스트가 지킨다 |
| `clean-results` 복원이 병행 작업과 충돌한다 | frontmatter 한 줄이라 충돌 범위가 좁다. 되살리는 것이 원래 상태이므로 의도적으로 지운 것이라면 사용자가 되돌리면 된다 |

## 8) 메모(Notes)

### 설계 결정과 탈락안

| 안 | 판정 | 근거 |
| --- | --- | --- |
| **구분자 분리 + 문서·코드 확장자 탈출구** | **채택** | 두 목표가 충돌하지 않는 유일한 길이다. 프로토타입 실측으로 자격증명 26건 전부 막고 정상 4건 전부 살렸다 |
| 구분자로만 분리 (탈출구 없이) | 탈락 | `key-rotation-guide.md` · `api-key-format.md` 가 죽는다. 직전 계획서가 이 이유로 구멍을 남겼다 |
| 「표식으로 시작하고 뒤에 구분자」 형태만 막는다 | 탈락 | `key-rotation-guide.md` 가 여전히 죽는다(`key` + `-`). 좁혔는데 문제는 그대로다 |
| 견본 예외를 «빈 목록»으로 남긴다 | 탈락 | 검사만 하고 아무것도 안 맞는 **죽은 코드**다. 교훈은 `SKILL.md` 가 갖는다 |
| `acme-prd.env.example` 의 값을 비워 계속 내보낸다 | 탈락 | 받는 쪽이 파일을 지우지 않으므로 **내보내지 않아도 mac 은 쓰던 파일을 유지한다.** 원본을 고칠 이유가 없다 |

### 리뷰가 이 계획의 «첫 구현» 에서 찾은 구멍 넷 — 전부 수정

계획대로 만든 첫 판에 구멍이 넷 있었고 실행으로 확인해 모두 고쳤다.

| 무엇 | 실측 | 고친 내용 |
| --- | --- | --- |
| 🔴 **확장자 탈출구를 표식 검사 «앞» 에 둬서 통째로 꺼졌다** | `db/.env.txt` · `db/credentials.txt` · `db/aws.key.sh` · `db/env.sh` · `db/server.pem.md` 가 담겼다 | 탈출구를 **구분자 조각 단계에만** 적용한다. 점 조각이 표식이면 확장자와 무관하게 막는다 |
| 🔴 **`sh`·`txt` 를 탈출구에 넣었다** | 위와 같음 | 뺐다. **`.sh` 는 `export API_KEY=...` 의 표준 그릇이고 `.txt` 는 토큰을 붙여넣어 두는 자리다** — 문서가 아니라 자격증명 그릇이다 |
| 고전 이름을 **접두로만** 맞췄다 | `db/prod.netrc` · `db/backup.id_rsa` · `db/old-id_rsa` 가 담겼다 | 구분자 «경계» 정규식으로 바꿨다. 자격증명은 **앞뒤** 에 무엇이 붙어도 자격증명이다 |
| **폴더명은 내려 맞추지 않았다** | `tools/Keys/oauth.json` · `db/CACHE/a.json` 이 담겼다. mac 은 파일시스템이 대소문자를 구별하지 않아 `Keys/` 와 `keys/` 가 같은 폴더다 | `parts` 도 내려 맞춘다 |
| 런타임 기록에 **탈출구가 없어 정상 문서가 죽었다** | `commands/log.md`(슬래시 커맨드) · `hooks/lock.py` 가 조용히 빠졌다 | 같은 탈출구를 붙였다. 안 보낸 것은 받는 쪽에서 **묻지도 않고** 없어진다 |

첫 판에서 **`tools/env.py` 를 살렸다가 다시 막는 쪽으로 돌렸다.** 점 조각이 온전한 표식이면
막는 것이 원칙에 맞고, 대신 `api_key_helper.py` 처럼 **합성어에 표식이 섞인** 모듈은 탈출구가 지킨다.

최종 전수 확인: **막아야 44건 / 담아야 10건 — 어긋남 0**.

### 남은 것 (별건)

| 무엇 | 왜 여기서 안 했나 |
| --- | --- |
| MCP 서버 정의의 `url` 이 가려지지 않는다 | `https://host/mcp?api_key=...` 형태가 그대로 담긴다. **파일 판정이 아니라 값 치환(`CREDENTIAL_VALUE_BLOCKS`)의 문제**라 이 계획의 범위 밖이다. 현재 등록된 두 서버(`context7`·`google-sheets`)는 해당 없음 |
| 금지항목 점검이 **복사 «뒤»에 돌고 항등식이다** | `find_forbidden_entries` 가 `should_include` 를 같은 경로에 다시 적용해 **구조상 항상 비어 있다.** 기존 구조이며 고치려면 복사 순서를 바꿔야 한다 |

### 그 밖

- 이미 공개된 4개 커밋(`28aa88a`·`a336ec8`·`9b32a51`·`13c6286`)에는 그 견본이 남는다.
  값은 host·port·name 이고 계정·비밀번호는 빈 값이라 **접근권이 넘어가지는 않는다**.
  이력 재작성은 하지 않기로 했다
- 워킹트리에 **손절 컬럼 통합 병행 작업**이 섞여 있다. 이 계획의 변경과 겹치는 파일은 없다

### 진행 로그 (KST)

- 2026-09-12 10:24: 계획서 작성. 구분자 설계를 프로토타입으로 먼저 검증해 「정상 파일이 죽는다」는 직전 계획서의 보류 사유가 해소됨을 확인
