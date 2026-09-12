# Implementation Plan: 번들 받기의 `path_map` 이 권한 규칙에 닿게 한다

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

**작성일**: 2026-09-12 11:59
**마지막 업데이트**: 2026-09-12 12:30
**관련 범위**: 하네스 (`.claude/skills/claude-config-import/`), 테스트
**관련 문서**: `.claude/skills/claude-config-import/SKILL.md`, `tests/CLAUDE.md`, 루트 `CLAUDE.md`

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

- [x] 목표 1: **치환 여부를 「출처 홈이 문자열에 있는가」가 아니라 「치환이 실제로 무언가를 바꾸는가」로 판정한다.** 그러면 `path_map` 의 모든 쌍이 권한 규칙에도 닿는다
- [x] 목표 2: 같은 결함이 있는 **두 자리를 함께 고친다** — `_classify_value`(설정 항목)와 `classify_files`(번들 파일 내용)
- [x] 목표 3: 이 mac 결정 파일에 남은 **손보정 흔적 18건(`exclude`)을 걷어낸다.** 남기면 수정 후에도 그 결정이 재사용돼 보호가 다시 사라진다
- [x] 목표 4: 회귀 테스트로 계약을 고정하고, `SKILL.md`·`docs/MEMORY.md` 의 「결함이 있다」 기술을 「고쳐졌다」로 갱신한다

## 2) 비목표(Non-Goals)

- **내보내기 쪽(`claude-config-export/export.py`)은 건드리지 않는다.** 이 결함은 받는 쪽 판정 로직에만 있다
- **`~/.claude/settings.json` 을 다시 만들지 않는다.** 3회차 적용(2026-09-12)에서 이미 손으로 보정해 이 mac 의 Downloads 가드 18건이 살아 있다
- **훅을 자동 판정하게 바꾸지 않는다.** 훅이 사람 판단으로 오는 이유는 `SKILL.md` 에 있고 이 작업과 무관하다
- **결정 파일의 스키마·항목 식별자 형식을 바꾸지 않는다.** 키가 바뀌면 승인한 항목을 전부 다시 물어야 한다
- **WSL 결정 파일(`DESKTOP-4CN5LK3-linux.json`)은 고치지 않는다.** 그쪽의 같은 항목들은 이미 `transform` 이라 영향이 없다
- 4회차 실제 번들 적용은 이 계획서의 범위가 아니다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

`plan_apply.py` 의 `_classify_value`(247줄)와 `classify_files`(671·676줄)가 **「변환할지」를
`environment.source_home in text` 하나로 정한다.** 그런데 치환 규칙은 `source_home` 하나가
아니라 `Environment.path_map`(= `source_home` + 결정 파일의 `extra_path_map`)이다.

그래서 **출처 PC 의 홈 «밖» 경로를 가리키는 항목은 `path_map` 에 쌍을 넣어도 「그대로 적용」으로
판정되고, 원문이 그대로 쓰인다.** 치환 함수는 멀쩡한데 **그 함수를 부를지 말지를 좁은 조건이
가로막는 구조**다.

**3회차 적용(WSL → 이 mac, 2026-09-12)에서 실측으로 드러났다.**

| 항목 | 값 |
| --- | --- |
| 죽은 경로로 들어온 권한 규칙 | **18건** — `allow` 2건(`Edit`·`Read` of `//mnt/c/Users/yblee/Downloads/**`) + `ask` 16건(`.env*`·`*.env`·`*.pem`·`*.key` × `Read`·`Edit` × 직하·재귀) |
| 판정이 붙인 분류 | **「그대로 적용」** — 에러도 경고도 없다 |
| 결과 | 이 mac 의 `~/Downloads` 에 있는 `.env`·`.pem`·`.key` 승인 가드가 **조용히 사라진다** |

**방향에 따라 드러나고 안 드러난다.** 홈 «안»의 경로(mac 의 `/Users/yubeen/Downloads`)는
`source_home`(`/Users/yubeen`)을 품으므로 조건에 걸려 정상 변환되고, 홈 «밖»의 경로
(WSL 의 `/mnt/c/Users/yblee/Downloads`)는 `source_home`(`/home/yblee`)을 품지 않아 걸리지 않는다.
**같은 두 PC 인데 한 방향에서만 나온다** — 1·2회차(mac → WSL)에서 안 보인 이유다.

`_classify_directory`·`classify_claude_json` 의 프로젝트 경로는 조건 없이 `transform_text` 를
부르므로 영향이 없다. **결함은 위 두 자리뿐이고, 전수 조사(`grep source_home`)로 확인했다.**

### 손보정이 남긴 부채 — 이것을 함께 걷어내지 않으면 수정이 무효가 된다

3회차에서는 그 18건을 결정 파일에 **`exclude`** 로 적어 빼고, 이 mac 의 같은 역할 규칙을
5단계에서 되살렸다(사용자 승인 2026-09-12). 수정 후에는 그 18건이 **`transform` 으로 판정되는
것이 옳은데**, `apply_previous_decisions` 는 **키와 해시가 맞으면 저장된 결정을 그대로
재사용한다.** 키도 해시도 안 바뀌므로 **`exclude` 가 살아남아 수정이 먹지 않는다.**

### 사용자에게 받은 결정 (2026-09-12)

- 3회차는 **손으로 보정**하고 넘어간다. 결함은 기록한 뒤 **별도 계획서**로 고친다
- 죽은 `/mnt/c` 권한 규칙 18건은 **제외한다** — 각 PC 의 `settings.json` 이 자기 경로만 갖는
  현재 상태를 지키고, 회차마다 중복이 누적되는 것을 막는다

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절
- `.claude/skills/claude-config-import/SKILL.md` — 「경로가 홈만으로 안 맞을 때」·「권한 규칙은 명령이 없어도 빼지 않는다」·「실측 기록」 세 회차
- `tests/CLAUDE.md` — 특히 「파일 격리」와 「픽스처가 코드와 같은 가정을 하면 그 버그는 영원히 안 잡힙니다」
- 전역 `~/.claude/CLAUDE.md` — 「수술적 변경」·「버그 수정은 증상이 아니라 근원을 고친다」
- 전역 `~/.claude/rules/python.md` — 타입 힌트·`Path`·네이밍

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 기능 요구사항 충족 — `path_map` 의 모든 쌍이 권한 규칙·번들 파일 내용에 닿는다
- [x] 회귀/신규 테스트 추가 — Phase 0 의 레드 테스트가 수정 후 그린
- [x] 이 mac 결정 파일의 `exclude` 18건 제거 완료
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — `SKILL.md` 의 🔴 절과 `docs/MEMORY.md` 의 해당 줄을 「고쳐졌다」로 갱신. `docs/COMMANDS.md` **변경 없음**
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (결함의 원인·방향 비대칭·실측 18건·탈락안을 `SKILL.md` 로 이관)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `.claude/skills/claude-config-import/plan_apply.py` — 판정 조건 두 자리 + 치환 횟수 헬퍼
- `.claude/skills/claude-config-import/SKILL.md` — 「경로가 홈만으로 안 맞을 때」의 🔴 절을 「고쳐졌다」로 갱신
- `tests/test_claude_config_import.py` — 회귀 테스트 추가
- `claude-config/decisions/yubeens-Mac-mini.local-darwin.json` — `exclude` 18건 제거
- `docs/MEMORY.md` — 3회차 함정 줄 갱신
- `docs/COMMANDS.md`: **변경 없음** — 실행 명령어·CLI 옵션이 바뀌지 않는다

### 데이터/결과 영향

- **측정 산출물에 영향 없다.** 하네스 설정 계층이며 `storage/` 를 건드리지 않는다
- **이 mac 의 `~/.claude/settings.json` 은 이 작업으로 바뀌지 않는다.** 효과는 **다음 번들 적용(4회차)** 에서 나타난다
- 판정 출력의 분류 개수가 달라진다 — 「그대로 적용」에서 「변환 후 적용」으로 18건이 옮겨간다

## 6) 단계별 계획(Phases)

### Phase 0 — 치환 계약을 테스트로 먼저 고정(레드)

**작업 내용**:

- [x] `tests/test_claude_config_import.py` 에 절을 추가한다 — 기존 파일의 픽스처(`import_module_under_test`)와 Given-When-Then 양식을 그대로 쓴다
- [x] 기존 `_environment` 헬퍼에 **`extra_path_map` 인자를 더해** 쓴다. 두 번째 헬퍼를 만들지 않는다 — 갈라지면 한쪽이 낡는다
- [x] `classify_settings` — 홈 밖 경로를 가리키는 `ask` 규칙이 **`TRANSFORM` 으로 판정**됨을 고정 (현재 `APPLY` → 레드)
- [x] `rebuild_settings` — 그 규칙이 **이 PC 경로 문자열로 재조립**됨을 고정. **사용자에게 보이는 계약은 이쪽이다**
- [x] `classify_files` — 홈 밖 경로만 든 텍스트 파일이 `TRANSFORM` 으로 판정됨을 고정. `BUNDLE_HOME_DIR` 를 `tmp_path` 로 `monkeypatch` 해 실경로를 읽지 않게 한다
- [x] 경계: **겹치는 쌍**(`/home/yblee/workspace` 와 `/home/yblee`)에서 **긴 쪽이 이기고 치환 횟수가 이중 계산되지 않음**을 고정
- [x] 경계: 치환할 것이 없는 항목은 **`APPLY` 로 남음**을 고정 (분류가 통째로 `TRANSFORM` 으로 쏠리지 않게)
- [x] 경계: `path_map` 이 빈 경우(출처 홈 미상)에 예외 없이 `APPLY` 로 떨어짐을 고정

**Validation**: 레드 확인만 한다 (`pytest tests/test_claude_config_import.py`). 품질 검증은 마지막 Phase.

---

### Phase 1 — 판정 조건 수정(그린 유지)

**작업 내용**:

- [x] `transform_text_counted(text, environment) -> tuple[str, int]` 를 추가하고 `transform_text` 가 그것을 부르게 한다. **치환 순서를 두 벌로 만들지 않는 것이 목적**이며, 횟수는 진행 중인 문자열에서 세어 겹치는 쌍의 이중 계산을 막는다
- [x] `_classify_value` — 조건을 `transform_text(...) != text` 로 바꾼다. `path_map` 이 이미 `source_home` 을 품으므로 기존 동작의 **상위집합**이다
- [x] `classify_files` — 같은 조건으로 바꾸고, 앞단 가드 `not environment.source_home` 을 `not environment.path_map` 으로 바꾼다. 사유 문구의 「출처 홈 경로 N곳」은 **「경로 N곳」** 으로 고친다 (더 이상 홈 경로만이 아니다)
- [x] Phase 0 의 테스트가 전부 그린임을 확인한다

**Validation**: `pytest tests/test_claude_config_import.py` 그린. 품질 검증은 마지막 Phase.

---

### Phase 2 — 손보정 흔적 제거

**작업 내용**:

- [x] `claude-config/decisions/yubeens-Mac-mini.local-darwin.json` 에서 **`/mnt/c/` 를 포함하는 `permissions` 항목 18건을 제거**한다 (`additionalDirectories` 항목은 이미 `transform` 이므로 손대지 않는다)
- [x] 제거 후 그 18건이 **다음 실행에서 `transform` 으로 새로 판정될 자리**가 됨을 확인한다 (저장된 결정이 없으면 판정 결과가 그대로 쓰인다)
- [x] 훅 결정 6건(`apply`)·3건(`exclude`)과 `path_map` 2쌍은 **그대로 둔다** — 그것들은 사용자가 승인한 결정이다

**Validation**: 결정 파일에 `/mnt/c/` 를 포함한 `permissions` 키가 0건임을 확인한다.

---

### Phase 3 — 코드 리뷰 조치 (계획에 없던 단계, 2026-09-12 승인)

> 리뷰가 **같은 뿌리의 두 번째 결함**을 찾았다. 조치 범위를 사용자에게 받아 이 Phase 를 더했다
> (아래 「계획에서 달라진 것」).

**작업 내용**:

- [x] `apply_previous_decisions` 가 **「넣을까 뺄까」만 되살리게** 한다. 양쪽이 다 「넣는다」면 형태는 이번 판정을 쓴다
- [x] `INCLUDE_DECISIONS` 상수를 두고 그 뜻(형태는 파생값이다)을 한 자리에 적는다
- [x] 회귀 테스트 3건 — 옛 `apply` 가 새 `transform` 을 못 덮는다 · `exclude` 는 그대로 이긴다 · **승인한 훅은 계속 적용된다**
- [x] 실제 번들에 옛 `apply` 18건을 심어 재현하고, 죽은 경로 0건과 훅 결정 보존을 확인한다
- [x] 고치지 않기로 한 실제 결함 셋을 `SKILL.md` 에 **터질 조건과 함께** 기록한다

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

- [x] `SKILL.md` 「경로가 홈만으로 안 맞을 때」의 🔴 절을 **「고쳐졌다 + 왜 그랬나」** 로 갱신한다. **실측 근거(18건·방향 비대칭)는 남긴다** — 근거를 버리면 같은 논의를 반복한다
- [x] `SKILL.md` 「실측 기록 — 세 번째 회차」의 Downloads 줄에 수정 사실을 한 줄로 잇는다
- [x] `docs/MEMORY.md` 의 3회차 함정 줄을 「손보정 후 수정 완료」로 갱신한다
- [x] `docs/COMMANDS.md`: **변경 없음** (실행 명령어·CLI 옵션 불변)
- [x] 자동 포맷 적용 (`poetry run black .`)
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정

**Validation**:

> 순서를 지킨다 — 리뷰에서 고치면 코드가 바뀌므로 품질 검증이 마지막 관문이어야 한다.

- [x] `/code-review xhigh` (발견 13건 · 조치: 7건 수정 · 6건 기록)
- [x] `poetry run python validate_project.py` (passed=1270, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

1. 하네스 / 받기 판정이 path_map 전체를 보게 하고 죽은 경로 유입을 막는다
2. 하네스 / 홈 밖 경로가 그대로 적용되던 결함을 고치고 회귀 테스트를 고정한다
3. 하네스 / 치환 여부를 실제 변화로 판정하고 손보정 결정을 걷어낸다
4. 하네스 / 권한 규칙에 경로 치환이 닿지 않던 두 자리를 함께 고친다
5. 하네스 / path_map 결함 수정과 실측 기록 갱신

## 7) 리스크(Risks)

- **분류가 과도하게 `TRANSFORM` 으로 쏠릴 수 있다.** `path_map` 에 짧은 문자열이 들어 있으면 무관한 항목까지 걸린다. Phase 0 의 「치환할 것이 없으면 `APPLY`」 경계 테스트로 막고, `path_map` 에 절대경로만 넣는 관행을 `SKILL.md` 가 이미 요구한다
- **`source_home` 이 이 PC 홈과 같은 경우 동작이 달라진다** — 지금은 `TRANSFORM`(결과는 동일), 수정 후 `APPLY`. **결과 문자열은 같고 분류 이름만 바뀐다.** 결정 파일에 그 항목의 옛 결정이 `transform` 으로 남아 있어도 해시가 같아 재사용되므로 적용 결과가 흔들리지 않는다
- **끝까지 검증되는 시점은 4회차 실제 적용이다.** 단위 테스트가 판정·재조립 계약을 고정하지만, 「실제 번들에서 18건이 살아 온다」는 다음 번들이 와야 보인다. 3회차 번들은 7단계에서 지웠고 git 이력에 남아 있다
- **결정 파일에서 18건을 지우는 것을 빠뜨리면 수정이 조용히 무효가 된다.** 그래서 Phase 2 를 독립 Phase 로 두고 DoD 에도 별도 항목으로 넣었다

## 8) 메모(Notes)

### 설계 결정과 탈락안

| 안 | 판정 | 이유 |
| --- | --- | --- |
| **치환 결과가 원문과 다르면 `TRANSFORM`** | **채택** | 조건이 「치환 함수가 실제로 하는 일」과 같아져 두 벌이 되지 않는다. `path_map` 이 이미 `source_home` 을 품으므로 기존 동작의 상위집합이다 |
| 조건에 `any(key in text for key in path_map)` 를 쓴다 | 탈락 | 같은 판정을 **두 번 다른 방식으로** 구현한다. 치환 순서가 바뀌면 조건과 결과가 어긋난다 |
| `extra_path_map` 도 `source_home` 처럼 별도 조건으로 추가한다 | 탈락 | 조건이 둘로 늘고, 쌍이 세 종류가 되면 또 늘어난다 |
| 사유 문구의 치환 횟수를 없애고 「경로를 바꿉니다」로 통일 | 탈락 | 횟수는 사람이 검토할 재료다 — 3회차에서 `db/scripts.allow.json` 의 「2곳」이 무엇이 바뀌는지 좁혀 줬다 |
| 죽은 `/mnt/c` 규칙을 `settings.json` 에 그대로 두기 | 탈락 (사용자 결정) | 회차마다 중복이 누적되고, 각 PC 가 자기 경로만 갖는 현재 상태가 깨진다 |

### 그 밖

- **이 수정은 「권한 규칙은 명령이 없어도 빼지 않는다」와 충돌하지 않는다.** 그 규칙은 *이 PC 에
  없는 명령*을 가리키는 규칙을 지키라는 것이고(나중에 설치하면 살아난다), 여기서 다루는 것은
  *다른 PC 의 절대경로*라 영영 매칭되지 않는다. 둘은 이유가 다르다
- 3회차에서 손으로 되살린 이 mac 의 Downloads 규칙 18건은 수정 후 **번들에서 같은 문자열로
  변환돼 온다.** `rebuild_settings` 는 번들만 보고 목록을 만들므로 중복이 생기지 않는다

### 착수 전 확인한 것 (2026-09-12, 실측)

- **결함이 있는 자리는 두 곳뿐이다.** `grep source_home` 전수 결과 조건으로 쓰이는 자리는
  247줄(`_classify_value`)과 671·676줄(`classify_files`)이고, 나머지는 dataclass 필드 선언·
  `path_map` 조립·매니페스트 읽기·출력 문구다. `_classify_directory`·`classify_claude_json` 의
  프로젝트 경로는 조건 없이 `transform_text` 를 부른다
- **기존 테스트는 이 수정으로 깨지지 않는다.** 분류기의 출력 결정을 단정하는 테스트가 없고,
  `rebuild_settings` 를 보는 두 테스트는 `verdict.decision` 을 **손으로 대입**한 뒤 호출한다
  (419·422·489·491줄)
- **`docs/COMMANDS.md` 는 이 스크립트의 CLI 호출 3개를 적고 있는데 인자가 바뀌지 않는다** —
  그래서 「변경 없음」이다. 새 플래그도 없다

### 진행 로그 (KST)

- 2026-09-12 11:59: 3회차 적용 중 발견한 결함으로 계획서 작성. 착수 전 Draft
- 2026-09-12 12:05: Phase 0 레드 확인 — 결함을 담은 3건만 실패, 경계·회귀 20건 통과
- 2026-09-12 12:10: Phase 1·2 완료. `source_home` 이 더는 판정 조건으로 쓰이지 않음을 전수 확인
- 2026-09-12 12:20: 코드 리뷰 13건. PyRight 5오류로 품질 게이트가 한 번 붉었고 즉시 수정
- 2026-09-12 12:30: Phase 3(리뷰 조치) 완료 후 최종 검증 통과

### 계획에서 달라진 것 (사용자 승인 2026-09-12)

**Phase 3 을 더했다.** 리뷰가 **같은 뿌리의 두 번째 결함**을 찾았기 때문이다 —
`apply_previous_decisions` 가 기억된 «형태»(`apply`/`transform`)까지 되살려서,
`path_map` 에 쌍을 나중에 더해도 **옛 `apply` 가 이겨 죽은 경로가 다시 쓰인다.**
해시가 항목 «값» 만 담아 쌍이 바뀌어도 그대로이기 때문이며, **Phase 2 의 손보정을
다음 회차에 또 요구하는 구조**였다. 조치 범위를 두 갈래로 물어 승인받았다.

- **캐시 병합증**: 「넣을까 뺄까」만 되살리게 좁힌다 (채택). 치환을 항상 적용하는 구조 변경안은
  탈락 — 세 함수를 건드리고 분류 표시와 실제 동작이 어긋날 수 있다
- **나머지 실제 결함 셋**: `SKILL.md` 에 터질 조건과 함께 기록하고 넣지 않는다 (채택).
  전부 이번 변경 전부터 있었고 지금 번들에서는 터지지 않아, 수술적 변경 원칙에 맞춰 범위를 닫았다
