# Implementation Plan: 내보내기의 자격증명 판정이 도트파일·다중확장자를 놓치는 것을 고친다

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

**작성일**: 2026-09-12 09:44
**마지막 업데이트**: 2026-09-12 10:12
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

- [x] 목표 1: 자격증명 판정이 **도트파일**(`.env`)과 **다중 확장자**(`.env.local` · `key.pem.bak`)를 막게 한다
- [x] 목표 2: 그러면서 **템플릿**(`acme-prd.env.example`)은 계속 담기게 한다
- [x] 목표 3: 문서가 말하는 것과 코드가 하는 것을 일치시킨다 — 지금 양쪽 SKILL.md 와 docstring 이 거짓이다

## 2) 비목표(Non-Goals)

- **허용목록(`ALLOW_TOP_LEVEL_DIRS`)을 좁히지 않는다.** 이번 결함은 자격증명 판정에 있다
- **`DENY_SUFFIXES`(로그·감사기록)를 손대지 않는다.** 직전 계획서에서 확정한 축이다
- **확장자 «허용목록» 전환을 하지 않는다.** 별개의 큰 설계 변경이며, 빠뜨리면 설정이 조용히 안 넘어가 로그가 새는 것보다 무겁다. 필요하면 별도 계획서
- **이미 만든 번들을 손으로 고치지 않는다.** 스크립트가 통째로 다시 만드는 산출물이다
- **`~/.claude` 의 파일을 지우거나 옮기지 않는다**

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

`_is_credential` 이 `relative_path.suffix` 하나만 본다 ([export.py:165](../../.claude/skills/claude-config-export/export.py#L165)). **파이썬은 앞의 점을 확장자 구분자가 아니라 이름의 일부로 취급하고, `suffix` 는 «마지막» 확장자만 준다.** 둘이 겹쳐 두 종류가 통째로 샌다.

실측 (`should_include` 직접 호출, 2026-09-12):

```
막힘     db/acme-prd.env
담긴다   db/.env                 <- Path('.env').suffix == ''   (도트파일)
담긴다   tools/x/.env
담긴다   db/.env.local
담긴다   db/acme-prd.env.local    <- suffix == '.local'          (다중 확장자)
담긴다   db/credentials.json     <- CREDENTIAL_NAMES 는 '.credentials.json' 만 안다
담긴다   db/key.pem.bak
담긴다   db/server.key.old
담긴다   db/acme-prd.env.example  <- 이건 «담겨야» 한다 (템플릿)
막힘     keys/anything.json
```

`Path` 의 실제 값 (실측):

| 이름 | `.suffix` | `.suffixes` |
| --- | --- | --- |
| `acme-prd.env` | `.env` | `['.env']` |
| `acme-prd.env.local` | `.local` | `['.env', '.local']` |
| **`.env`** | **`''`** | **`[]`** |
| **`.env.local`** | `.local` | **`['.local']`** |

**`.suffixes` 로 바꾸는 것만으로는 안 된다** — 도트파일에서 `.env` 조각이 통째로 사라지기 때문이다. 판정은 **이름을 점으로 쪼갠 토큰**을 봐야 한다.

### 왜 지금 고쳐야 하나

- **이 저장소는 PUBLIC 이다.** 한 번 담기면 파일을 지워도 git 이력에 남는다. `export.py` docstring 이 그 이유로 「자격증명은 허용목록보다 «먼저» 막는다」고 선언하는데, **선언과 동작이 다르다**
- **`.env` 는 자격증명 파일명의 사실상 표준**이다. 「잘 안 생기는 이름」이 아니라 가장 흔한 이름이 안 막힌다
- **문서가 거짓이다** — 내보내기 SKILL.md 와 받는 쪽 SKILL.md 의 「빠지는 것」 표가 둘 다 `*.env` 를 막는다고 적는다. 사람이 그 표를 믿고 파일을 둔다

### 지금 유출은 없다

`~/.claude` 전체를 훑어 다중확장자·도트파일 자격증명이 **실재하지 않음**을 확인했다 — 있는 것은 의도적으로 담는 `db/acme-prd.env.example` 하나다. 방금 만든 번들(37항목)도 깨끗하다. **잠재 함정을 닫는 작업이지 사고 수습이 아니다.**

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「예외 — `claude-config/` 와 두 하네스 스킬」 절과 「단순화하지 않을 것」(보안 조치)
- `.claude/skills/claude-config-export/SKILL.md` — 절차의 SoT
- `tests/CLAUDE.md` — Given-When-Then, 경계 조건
- 전역 `~/.claude/rules/python.md` — 타입 힌트, 네이밍, 예외 구분

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 위 실측표의 「담긴다」 8건 중 **자격증명 7건이 전부 막힌다**
- [x] **`db/acme-prd.env.example` 은 계속 담긴다** (회귀 없음)
- [x] `db/scripts.allow.json` · `db/acmeq.py` 같은 **정상 파일이 새로 막히지 않는다**
- [x] 경계가 테스트로 고정됐다 — 도트파일 · 다중확장자 · 템플릿 · 토큰 아닌 부분일치(`api-key-format.md`)
- [x] 번들을 다시 만들어 **항목 수가 37개 그대로**이고 구성이 같음을 확인했다
- [x] `export.py` docstring 과 양쪽 SKILL.md 의 「빠지는 것」 표현이 **실제 판정과 일치**한다
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] `poetry run python validate_project.py` 통과 (failed=0, skipped=0; passed/failed/skipped 수 기록)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — `docs/COMMANDS.md` 변경 없음 / 양쪽 `SKILL.md` 갱신
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (`Path.suffix` 의 도트파일 함정과 템플릿 예외의 근거를 `SKILL.md` 로 이관.
      `/impl-plan` 스킬 "근거 승격" 참고)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `.claude/skills/claude-config-export/export.py` — `_is_credential` 의 판정, 상수 추가, docstring
- `.claude/skills/claude-config-export/SKILL.md` — 「빠지는 것」과 근거 (근거 승격)
- `.claude/skills/claude-config-import/SKILL.md` — 미러 표 한 행 (두 벌 드리프트 방지)
- `tests/test_claude_config_bundle.py` — `CREDENTIAL_PATHS` 확장, 템플릿 회귀 케이스
- `claude-config/**` — 번들 재생성 산출물
- `docs/COMMANDS.md`: **변경 없음** — 실행 명령어와 CLI 옵션이 바뀌지 않는다

### 데이터/결과 영향

- **측정·검증 산출물에 영향 없음.** `storage/` 를 건드리지 않는다
- **번들 내용이 바뀌지 않아야 한다.** 지금 그런 파일이 없으므로 **37항목 그대로**가 맞다 — 숫자가 달라지면 정상 파일을 새로 막은 것이므로 조사 대상이다
- **받는 쪽 결정에 영향 없음.** 자격증명은 파일 판정 단계에서 빠져 `decisions/` 에 항목이 생기지 않는다

## 6) 단계별 계획(Phases)

### Phase 0 — 구멍과 회귀 방지선을 테스트로 먼저 고정(레드)

> 이 Phase 를 두는 이유: 이 판정은 **PUBLIC 저장소로의 유출을 막는 마지막 관문**이다.
> 「무엇이 막히는가」뿐 아니라 **「무엇이 계속 담기는가」**도 같은 강도로 고정해야
> 고치다가 템플릿·정상 파일을 죽이지 않는다.

**작업 내용**:

- [x] `CREDENTIAL_PATHS` 에 도트파일 3건(`db/.env` · `tools/x/.env` · `db/.env.local`)을 넣는다
- [x] 다중 확장자 3건(`db/acme-prd.env.local` · `db/key.pem.bak` · `db/server.key.old`)을 넣는다
- [x] 점 없는 `db/credentials.json` 을 넣는다
- [x] **회귀 방지**: `db/acme-prd.env.example` 이 `INCLUDED_PATHS` 에 있음을 확인한다 (이미 있다 — 이 케이스가 템플릿 예외의 감시자다)
- [x] **경계**: 토큰이 아니라 부분일치인 이름은 계속 담긴다 — `db/api-key-format.md` · ~~`tools/env.py`~~ 를 `INCLUDED_PATHS` 에 넣는다
      (**`tools/env.py` 는 뺐다** — 그것을 살리려면 첫 조각을 판정에서 빼야 하는데 그러면 `key.json` 이 샌다. 아래 「같은 리뷰에서 함께 고친 것 셋」 참고)
- [x] 이 시점에서 새 테스트가 **실패**하는 것을 확인한다 (레드)

---

### Phase 1 — 토큰 판정 구현(그린 유지)

**작업 내용**:

- [x] `_is_credential` 이 **이름을 `.` 으로 쪼갠 토큰**을 보게 한다 — ~~첫 토큰(기본 이름)은 제외하고~~ 나머지에서 자격증명 표식을 찾는다.
      ~~첫 토큰을 빼는 이유는 `env.py` 같은 정상 모듈명을 죽이지 않기 위해서다~~
      🔴 **이 두 줄은 구현 중 뒤집혔다 — 지금은 «모든» 조각을 센다.** 첫 조각을 빼면 `key.json`(GCP 서비스계정 키의 표준 파일명)이 샌다
- [x] ~~**템플릿 예외**를 둔다 — 마지막 토큰이 `example`·`sample`·`template` 이면 자격증명으로 보지 않는다.~~
      🔴 **이 줄도 뒤집혔다 — 토큰 규칙이 «우회로»가 되어 경로 허용목록으로 바꿨다.**
      둘 다 근거는 아래 「실측으로 전제가 뒤집힌 것」과 「같은 리뷰에서 함께 고친 것 셋」에 있다
- [x] 점 없는 `credentials.json` 도 `CREDENTIAL_NAMES` 에 넣는다
- [x] `_is_credential` 의 docstring 에 **왜 `suffix` 가 아니라 토큰인가**를 적는다 — 도트파일에서 `suffix` 가 빈 문자열이 되는 실측을 남긴다
- [x] Phase 0 의 테스트가 통과하는지 확인한다 (그린)

---

### 마지막 Phase — 번들 재생성, 문서 정리 및 최종 검증

**작업 내용**

- [x] `--dry-run` 으로 항목이 **37개 그대로**이고 `db/acme-prd.env.example` 이 남았는지 확인한다
- [x] 번들을 다시 만들고 항목 구성을 직전 번들과 **기계로 대조**한다
- [x] `export.py` 의 모듈 docstring 이 말하는 자격증명 차단 범위를 실제와 맞춘다
- [x] 양쪽 `SKILL.md` 의 「빠지는 것」 표현을 갱신한다 — `*.env` 가 아니라 **도트파일과 다중 확장자를 포함한다**는 것과, **템플릿(`.example`)은 예외로 담긴다**는 것
- [x] `docs/COMMANDS.md` — **변경 없음** (실행 명령어·CLI 옵션 불변)
- [x] 자동 포맷 적용 (`poetry run black .`)
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

> 순서를 지킨다 — 리뷰에서 고치면 코드가 바뀌므로 품질 검증이 마지막 관문이어야 한다.

- [x] `/code-review xhigh` **2회** (1차 발견 10건 → **내 코드의 구멍 4개를 찾아 전부 수정**(대소문자·첫 조각·견본 우회·고전 이름) / 2차 발견 **11건** → **내 변경 관련 4건**(구분자·로그 `.suffix`·견본 공개·첫 조각 절충) 중 **1건은 의도된 절충으로 기록**, **3건은 사용자 판단 대기로 「남겨 둔 구멍」에 기록**, **나머지 7건은 내 변경이 아니라 보고만**)
- [x] `poetry run python validate_project.py` (passed=**1221**, failed=**0**, skipped=**0**)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 하네스 / 자격증명 판정이 도트파일과 다중 확장자를 놓치던 구멍을 막는다
2. 하네스 / `.env` 가 번들에 담기던 것을 토큰 판정으로 고치고 템플릿은 남긴다
3. 하네스 / suffix 한 조각만 보던 자격증명 차단을 이름 토큰 전체로 넓힌다
4. 하네스 / PUBLIC 저장소로 새던 자격증명 경로 7종을 막고 경계를 테스트로 고정한다
5. 하네스 / 자격증명 차단 범위를 문서가 말하는 것과 일치시킨다

## 7) 리스크(Risks)

| 리스크 | 완화 |
| --- | --- |
| **정상 파일을 새로 막아 설정이 조용히 안 넘어간다** | 이쪽이 유출보다 «조용한» 실패다. 첫 토큰을 판정에서 빼고, `INCLUDED_PATHS` 에 부분일치 케이스를 넣어 고정한다. 번들 **항목 수 37 불변**을 대조로 확인한다 |
| 템플릿 예외를 악용해 진짜 자격증명이 `xxx.env.example` 로 들어온다 | `.example` 은 「내용이 비어 있는 견본」이라는 보편 관용이고 실제로 그 용도로 쓰이고 있다. **번들 전체 패턴 스캔**(`test_real_bundle_has_no_forbidden_entries` · `claude_json` 비밀패턴 검사)이 두 번째 층으로 남는다 |
| 토큰 판정이 이름에만 걸려 폴더명은 못 본다 | `CREDENTIAL_SEGMENTS`(`keys/`)가 폴더를 이미 담당한다. 두 축은 역할이 다르며 이번에 합치지 않는다 |
| 이 수정으로 직전 계획서의 번들이 무효가 된다 | 번들은 스크립트가 언제든 다시 만든다. **커밋 전에 재생성**하므로 옛 번들이 남지 않는다 |

## 8) 메모(Notes)

### 설계 결정과 탈락안

| 안 | 판정 | 근거 |
| --- | --- | --- |
| **이름을 `.` 으로 쪼갠 토큰 판정 + 템플릿 예외** | **채택** | 도트파일과 다중 확장자를 **한 규칙으로** 덮는다. 토큰 단위라 `api-key-format.md` 같은 부분일치를 죽이지 않는다 |
| `Path.suffixes` 로 바꾼다 | 탈락 | **도트파일을 못 잡는다** — 실측으로 `Path('.env').suffixes == []`, `Path('.env.local').suffixes == ['.local']` 이다. 다중 확장자만 고치고 더 흔한 구멍을 남긴다 |
| 이름에 `.env` 가 «들어가면» 차단 (부분 문자열) | 탈락 | `acme-prd.env.example` 을 죽인다. 예외를 또 붙여야 하고, `api-key-format.md` 처럼 정상 이름도 걸린다 |
| ~~`db/acme-prd.env.example` 하나만 예외 목록에 박는다~~ | ~~탈락~~ → **채택 (구현 중 뒤집힘)** | 아래 「실측으로 전제가 뒤집힌 것」 참고 |

### 실측으로 전제가 뒤집힌 것 — 견본 예외는 규칙이 아니라 목록이어야 한다

계획 단계에서 「파일명 하나를 박는 것은 땜질」이라며 **토큰 규칙**(마지막 조각이
`example`·`sample`·`template` 이면 통과)을 채택했다. **코드 리뷰가 그 규칙이 «우회로»임을
드러냈고 실행으로 확인했다** — 이름 뒤에 그 조각만 붙이면 자격증명 판정이 통째로 꺼진다.

```
담긴다   db/real-secret.key.sample
담긴다   db/credentials.json.example
담긴다   db/.env.template
```

**견본 파일이 값을 담은 채 배포되는 일이 흔하다는 것도 실측됐다** — `db/acme-prd.env.example`
에 운영 DB 의 host·port·name 3개가 채워져 있다(빈 키 2개는 계정·비밀번호).
즉 「`.example` 이면 안전하다」는 전제 자체가 틀렸다.

그래서 **경로 허용목록**(`CREDENTIAL_TEMPLATE_ALLOWLIST`)으로 바꿨다. 새 견본을 넣을 때
코드를 고쳐야 하는 것은 그대로지만, **그 수고가 곧 사람이 한 번 들여다보는 자리**라
우회 가능한 규칙보다 낫다. 사용자 승인 2026-09-12.

### 같은 리뷰에서 함께 고친 것 셋

| 무엇 | 실측 | 고친 내용 |
| --- | --- | --- |
| **대소문자를 가렸다** | `db/.ENV` · `db/PRIVATE.KEY` 가 담겼다 | 이름을 내려 맞춘다. mac·윈도우는 파일시스템이 대소문자를 구별하지 않아 같은 파일이다 |
| **첫 조각을 판정에서 뺐다** | `db/key.json`(GCP 서비스계정 키의 표준 파일명) · `env.json` · `key` 가 담겼다 | 모든 조각을 센다. 실제 번들 37개 중 첫 조각이 표식인 파일은 **0개**라 지킬 것이 없었다 — 가정의 `env.py` 를 살리려다 실재하는 구멍을 연 셈이었다 |
| **이름 목록이 완전일치였다** | `credentials.json.example` · `.netrc.bak` 이 담겼다. `id_rsa`·`.netrc`·`.pgpass`·`.npmrc` 는 아예 목록에 없었다 | 접두로 맞추고 고전 이름을 목록에 넣었다 — 자격증명은 뒤에 무엇이 붙어도 자격증명이다 |
| 확장자 **허용목록**으로 전환 (`.md`·`.py`·`.json` 만 담는다) | 탈락(이번엔) | 모듈 철학과는 맞지만 **빠뜨리면 설정이 조용히 안 넘어간다** — 로그·자격증명이 새는 것보다 무거운 실패다. 별도 계획서로 다룰 값어치는 있다 |

### 남겨 둔 구멍 둘 — 사용자 판단 대기

**① 구분자(하이픈·밑줄)를 넘지 못한다.** 판정이 `.` 으로만 쪼갠다.

```
담긴다   db/.env-prod · db/.env_old · db/env_local
담긴다   db/id_rsa_backup · db/credentials-prod.json · db/.npmrc-backup
```

**`-`·`_` 로도 쪼개면 정상 파일이 죽는다** — `db/key-rotation-guide.md` 가 `key` 토큰을 갖게 되어
막힌다. 이 저장소가 세운 「정상 파일을 죽이는 쪽이 유출보다 조용한 실패」와 정면으로 부딪히므로
**임의로 정하지 않는다.** 넓힐 거라면 「표식으로 «시작»하고 뒤에 구분자가 오는 경우」 같은
좁은 형태를 검토해야 하고, 그래도 `key-rotation-guide.md` 는 걸린다.

**② 로그·상태 파일 판정은 여전히 `.suffix` 다** — `_is_credential` 에서 걷어낸 바로 그 방식이
같은 파일 20줄 아래 남아 있다.

```
담긴다   hooks/.log · hooks/toast.LOG · db/audit.JSONL · hooks/.LOCK · hooks/toast.log.1
```

로테이션은 직전 계획서에서 YAGNI 로 두기로 했으나 **대소문자와 `.log` 도트파일은 그 판단에
없던 것**이다. 이쪽은 정상 파일이 `.log` 로 끝나거나 `.LOG` 인 경우가 없어 **오탐 위험이 거의
없고 비용도 작다.** 별도 계획서 후보.

### 견본 파일을 «목록에서 빼는» 선택지 (실측 근거)

`plan_apply.py` 는 `shutil.copy2` 만 하고 **파일을 지우지 않는다**(`unlink`·`rmtree` 없음).
그래서 `db/acme-prd.env.example` 를 허용목록에서 빼면 **저장소에는 안 담기고 mac 은 자기 파일을
그대로 유지한다** — 값을 비우거나 mac 에서 따로 작업할 필요가 없다. 이미 공개된 4개 커밋
(`28aa88a` · `a336ec8` · `9b32a51` · `13c6286`)은 어느 쪽을 택해도 바뀌지 않는다.

### 그 밖

- 이번 결함은 **직전 계획서(런타임 로그 제외)가 만든 것이 아니다.** 바로 옆 줄(`DENY_SUFFIXES`)을 고치다 코드 리뷰가 이웃 상수에서 찾아냈다
- 받는 쪽 `SKILL.md` 의 미러 표도 함께 고친다 — 직전 계획서에서 같은 자리가 낡아 한 번 고쳤다. **두 벌이 있는 한 계속 같이 고쳐야 하며**, 그 사실 자체를 표에 적어 둔다

### 진행 로그 (KST)

- 2026-09-12 09:44: 계획서 작성. 코드 리뷰의 다중확장자 지적을 검증하다 **도트파일 구멍(`.env`)을 추가로 발견** — 실측으로 7종이 담기는 것을 확인
