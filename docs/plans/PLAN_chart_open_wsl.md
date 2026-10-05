# Implementation Plan: 판단용 차트를 WSL 에서 Windows 기본 브라우저로 열기

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

**작성일**: 2026-10-05 10:33
**마지막 업데이트**: 2026-10-05 11:22
**관련 범위**: scripts
**관련 문서**: scripts/CLAUDE.md, src/verify_lab/CLAUDE.md, docs/COMMANDS.md

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

- [x] 목표 1: WSL 에서 `scripts/chart_halving_cycle.py` 를 실행하면 차트가 **Windows 기본 브라우저**로 열린다
- [x] 목표 2: WSL 에서는 저장 줄 뒤에 **Windows 경로 한 줄**(`\\wsl.localhost\...`)을 DEBUG 로 찍는다 — 자동으로 안 열렸을 때 복사해서 여는 자리
- [x] 목표 3: WSL 이 아닌 환경(Mac)의 동작과 로그는 바뀌지 않는다 — 지금처럼 `webbrowser.open` 을 부른다
- [x] 목표 4: `BROWSER` 환경 변수를 지정하면(`BROWSER=true` 포함) WSL 에서도 그것을 따른다 — `docs/COMMANDS.md` 의 「브라우저를 열지 않고 만든다」 관용이 WSL 에서도 그대로 동작한다

## 2) 비목표(Non-Goals)

- 브라우저가 «실제로 열렸는지» 판정하지 않는다 — `explorer.exe` 의 종료코드가 성공 여부를 말하지 않는다고 알려져 있다(Phase 1 에서 실측해 근거를 코드 주석에 남긴다). 그 대신 Windows 경로를 항상 찍는다
- 공유 헬퍼(`utils/cli_helpers.py`)로 올리지 않는다 — 쓰는 스크립트가 하나뿐이고(`chart_<매매법>.py` 는 「있는 매매법만 둔다」), 두 번째 차트 스크립트가 생길 때 정한다
- `wslu`(`wslview`) 설치나 `BROWSER` 전역 설정 같은 환경 변경은 하지 않는다
- 차트 HTML 의 내용·저장 경로·측정 로직은 건드리지 않는다
- 순수 리눅스(데스크톱) 환경의 동작은 지금 그대로다 — `webbrowser` 가 고른 수단을 쓴다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

- WSL 에서 실행하면 차트는 저장되지만 브라우저가 열리지 않고 `gio: ... Failed to find default application for content type 'text/html'` 한 줄이 찍힌다. 종료코드는 0 이다
- 실측(2026-10-05, 이 PC):
  - 파이썬 3.12.3 `webbrowser._tryorder` = `['gio']` 하나. xdg-open · wslview · firefox · chromium · google-chrome · x-www-browser 없음
  - WSLg 가 `DISPLAY=:0` · `WAYLAND_DISPLAY=wayland-0` 을 켜 두어 `webbrowser` 가 `gio open` 을 등록하고, 리눅스 쪽에 text/html 기본 앱이 없어 실패한다
  - `BackgroundBrowser.open` 은 프로세스를 띄운 직후 `p.poll() is None` 이면 참을 돌려줘 실패가 에러로 올라오지 않는다
  - `wslpath -w <차트 경로>` = `\\wsl.localhost\Ubuntu\home\yblee\workspace\verify-lab\storage\charts\반감기_사이클\판단차트.html` — 사용자가 손으로 여는 경로와 같다
  - `cmd.exe /c ...` 는 현재 폴더가 UNC 라 **경고 세 줄을 CP949 로 깨져** 찍는다 — 로그를 더럽히므로 Windows 쪽 열기 수단에서 뺀다
  - `explorer.exe` · `wslpath` 는 PATH 에 있다(`/mnt/c/WINDOWS/explorer.exe` · `/usr/bin/wslpath`)
- 스크립트 주석([chart_halving_cycle.py:62](../../scripts/chart_halving_cycle.py#L62))이 처음부터 「브라우저를 못 여는 환경(WSL 등)」을 예상하고 경로만 먼저 찍지만, 찍는 경로가 리눅스 경로라 Windows 에서 그대로 쓸 수 없다
- 글자 규칙이 막거나 되돌릴 수 없는 결과에 물리는 설계: **해당 없음** (판정은 커널 이름 하나이고, 결과는 브라우저 열기라 되돌릴 것이 없다)

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- `.claude/plan-config.json` — 이 저장소의 검증 명령·자동 포맷·근거 승격 목적지 (**값의 SoT**)
- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 절 (값이 아니라 **판단 근거**)
- 작업 도메인 규칙: `scripts/CLAUDE.md`
- 패키지 규칙(로깅·예외 정책): `src/verify_lab/CLAUDE.md` · 전역 `~/.claude/rules/python.md`
- 실행 명령어: `docs/COMMANDS.md`
- 테스트 규칙(테스트를 더하지 않는 판단의 근거): `tests/CLAUDE.md`

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 기능 요구사항 충족 (목표 1 ~ 4 — Phase 1 Validation 의 실행 기록으로 확인)
- [x] 회귀/신규 테스트 — **추가하지 않는다.** `scripts/` 는 테스트 대상이 아닌 계층이고(`scripts/CLAUDE.md` 「CLI 를 고쳤으면 그 스크립트를 한 번 돌려 보고 넘깁니다」), 분기는 실제 실행과 스크래치 시뮬레이션으로 확인한다
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — `docs/COMMANDS.md` 변경 없음 (명령·인자 그대로 · `BROWSER=true` 줄도 WSL 에서 그대로 맞다) · CLAUDE.md 변경 없음
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다
      (`explorer.exe` 를 고른 이유 · 종료코드를 보지 않는 이유 · `BROWSER` 를 따르는 이유를 **코드 주석**에 남긴다 — 그 선택의 「왜」가 그 자리에서만 쓰인다)
- [x] 미룬 지적 옮김 — **해당 없음** (고치지 않은 지적 전부가 거르는 기준에 걸림 — 진행 로그 2026-10-05 11:22 항목) — 고치지 않은 리뷰 지적을 거르는 기준으로 걸러 `deferred_findings` 파일로 옮겼다. 계획서 없이 읽히게 썼다.
      거른 지적은 진행 로그에 기준 번호와 함께 남기고 Done 보고에 표로 냈다
      이 계획서가 그 파일의 항목을 고쳤다면 그 항목을 지웠다
      (둘 다 없으면 「해당 없음」. `/impl-plan` 스킬 "미룬 지적 옮기기" 참고)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- `scripts/chart_halving_cycle.py` — 브라우저 여는 함수 하나를 더하고 `main` 이 그것을 부른다. 62행 주석을 실제 동작에 맞춘다
- `docs/COMMANDS.md`: **변경 없음** — 명령과 인자가 그대로이고, `BROWSER=true` 줄은 목표 4 로 WSL 에서도 그대로 맞다

### 설계

```python
def open_in_browser(path: Path) -> None:
    # WSL 이 아니면 지금 그대로
    if "microsoft" not in platform.release().lower():
        webbrowser.open(path.as_uri())
        return

    try:
        windows_path = subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True, check=True).stdout.strip()
        logger.debug(f"Windows 경로: {windows_path}")

        if os.environ.get("BROWSER"):     # 사용자가 지정한 것을 따른다 (BROWSER=true 관용)
            webbrowser.open(path.as_uri())
            return

        subprocess.run(["explorer.exe", windows_path], check=False)   # 종료코드는 성공 여부를 말하지 않는다 (Phase 1 실측)
    except (OSError, subprocess.CalledProcessError) as error:
        logger.warning(f"브라우저를 열지 못했습니다 ({error}) — 위에 찍힌 경로의 파일을 직접 여세요")
```

- **WSL 판정은 커널 이름**(`platform.release()` 에 `microsoft`)으로 한다 — WSL1(`...-Microsoft`)·WSL2(`...-microsoft-standard-WSL2`) 둘 다 잡고, Mac(`23.x.0`)·일반 리눅스에는 없다
- **Windows 경로는 `wslpath -w` 가 만든다** — 손으로 `\\wsl.localhost\<배포판>\...` 을 조립하면 `/mnt/c/...` 같은 경로에서 틀린다
- **실패는 WARNING 하나로 끝내고 종료코드를 바꾸지 않는다** — 차트는 이미 저장됐고 경로도 찍혔다. 여는 것은 편의 단계라, 여기서 죽으면 만든 결과가 실패로 읽힌다. 오류 내용은 메시지에 그대로 싣는다(삼키지 않는다)
- 위 코드는 설계 의도를 보이는 스케치이며 구현 시 주석·docstring 은 저장소 규칙(「왜」만 · 현재형)에 맞춘다

### 데이터/결과 영향

- 산출물(`storage/results/`) 영향 없음 — 차트 스크립트는 그 폴더를 쓰지 않는다
- 차트 HTML 영향 없음 — 여는 방법만 바뀐다

## 6) 단계별 계획(Phases)

### Phase 1 — 구현과 실측(그린 유지)

**작업 내용**:

- [x] `scripts/chart_halving_cycle.py` 에 `open_in_browser(path)` 를 더하고 `main` 의 `webbrowser.open(...)` 을 그것으로 바꾼다
- [x] `explorer.exe` 를 실제로 불러 **종료코드 · 표준출력/오류 · 걸린 시간 · 한글 경로 전달**을 잰다 → 결과를 진행 로그와 코드 주석(종료코드를 보지 않는 근거)에 남긴다
- [x] 62행 주석을 실제 동작에 맞춘다 (WSL 을 「못 여는 환경」의 예로 들지 않는다)

**Validation**:

- [x] WSL 기본 실행 → 저장 줄 + Windows 경로 줄이 찍히고 `gio:` 줄이 없다 · 사용자가 Windows 브라우저에 차트가 열린 것을 확인한다
- [x] WSL `BROWSER=true` 실행 → 저장 줄 + Windows 경로 줄 · 브라우저가 열리지 않는다
- [x] 스크래치 시뮬레이션(커밋하지 않음) — ① 커널 이름을 Mac 값으로 바꾸면 `webbrowser.open` 이 `file://` 주소로 불리고 `subprocess.run` 은 안 불린다(Mac 로그가 지금과 같다) ② `explorer.exe` 가 `FileNotFoundError` 를 내면 WARNING 한 줄 · 예외 없이 끝난다

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

> 🔴 **`/commit` 이 «맨 마지막»인 것은 의도다.** 그 스킬은 「후보 뒤에는 아무것도 덧붙이지 말 것」으로
> 끝나므로 **호출하는 순간 그 턴이 거기서 닫힌다.** 중간에 두면 뒤에 적힌 항목이 그 벽 너머에 남는다 —
> 실제로 두 번 그렇게 샜다(`[실측] 2026-09-14` 후보를 계획서에 안 옮김 · `2026-09-16` 옮기고 체크박스를 안 닫음).
> **체크박스와 상태를 먼저 확정하고, 커밋 후보를 마지막에 만든다.**

- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` 변경 없음 — 재확인)
- [x] 자동 포맷 적용 (`poetry run black .`)
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] Validation 절에 `/code-review` 와 품질 검증 **실행 결과**를 적는다
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정
- [x] 🔴 **마지막에 `/commit` 을 실행하고 그 후보를 «이 계획서» 의 `#### Commit Messages` 절에 옮긴다** —
      `/commit` 은 계획서를 모르고 「후보 뒤에 아무것도 덧붙이지 말 것」으로 끝나므로,
      **대화에만 내면 그 절이 빈 채로 남는다.** 체크박스 갱신이 diff 에 더 들어가지만
      커밋 메시지의 내용을 바꾸지 않는다. **커밋은 사용자가 한다 — 후보만 낸다**

**Validation**:

> 순서를 지킨다 — 리뷰에서 고치면 코드가 바뀌므로 품질 검증이 마지막 관문이어야 한다.
> **고칠 것이 0 인 회차에서 끝낸다** — 고칠 것은 무거운 버그 전부와, 실제 산출물에 나오는 가벼운 버그다.
> 2회차에도 무거운 버그가 나오면 사용자에게 보고하고 3회차 여부를 묻는다 — 나머지 가벼운 버그와
> 「그 외」는 목록만 남기고 고치지 않는다. 무게의 정의는 `/impl-plan` 의 「코드 리뷰」 절이 SoT 다.
> **뒤에 리뷰 회차가 오지 않는 수정은 고치기 «전»에 바꿀 파일을 스크래치에 복사해 두고, 고친 뒤 수정분 검증을
> 거친다** — 절차는 `/impl-plan` 의 「지적을 고칠 때」다.

- [x] `/code-review xhigh` **1회차** (발견 10건 — 버그 8 [무거움 1 · 가벼움 7] · 그 외 2 · 조치: 무거움 1 수정)
- [x] `/code-review xhigh` **2회차** (발견 13건 — 버그 8 [무거움 0 · 가벼움 8] · 그 외 5 · 조치: 없음 — 가벼움 8건 모두 실제 환경 0건)
- [x] 수정분 검증 — 해당 없음 (마지막 회차인 2회차에 고친 것이 없다. 1회차 수정은 2회차 리뷰가 다시 봤다)
- [x] `poetry run python validate_project.py` (passed=1638, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다.**
> 계획서를 쓰는 시점에는 diff 가 없어 여기 적는 것은 전부 추측이고,
> **추측으로 적은 줄은 그대로 나간다.** 형식·문체 규칙은 `/commit` 이 정한다.

1. 검증 / 반감기_사이클 판단용 차트 WSL 브라우저 열기 지원
2. 검증 / 반감기_사이클 판단용 차트를 WSL 에서 Windows 기본 브라우저로 열기
3. 검증 / 반감기_사이클 판단용 차트가 WSL 에서 gio 로 실패하던 브라우저 열기 수정
4. 검증 / 반감기_사이클 판단용 차트의 WSL 열기를 wslpath 변환과 explorer.exe 호출로 변경하고 Windows 경로 로그 추가
5. 검증 / 반감기_사이클 판단용 차트 열기 실패의 경고 처리와 WSL 에서의 BROWSER 지정 존중

## 7) 리스크(Risks)

- **Mac 분기를 이 PC 에서 실제로 돌릴 수 없다** → 완화: Mac 경로는 지금 코드(`webbrowser.open(path.as_uri())`)를 그대로 부르고, 분기 조건은 스크래치 시뮬레이션으로 확인한다. 다음에 Mac 에서 실행할 때 브라우저가 열리는지 사용자가 본다
- **`explorer.exe` 가 성공해도 실패 종료코드를 낼 수 있다** → 받아들인다: 종료코드로 성공을 판정하지 않고, Windows 경로를 항상 찍어 사람이 확인·대체할 수 있게 한다
- **Windows 실행 연동이 꺼진 WSL**(`explorer.exe` 를 못 찾거나 실행 형식 오류) → `OSError` 를 WARNING 으로 알리고 종료코드 0 으로 끝난다 — 차트는 이미 저장됐다
- **`explorer.exe` 가 오래 붙잡고 있으면** 스크립트 종료가 늦어진다 → Phase 1 실측에서 걸린 시간을 재고, 붙잡으면 기다리지 않는 호출로 바꾼다(그때 사용자에게 알린다)

## 8) 메모(Notes)

- 사용자 결정 (2026-10-05): C안(WSL 이면 Windows 쪽에서 연다) + 로그 가안(WSL 에서 Windows 경로 한 줄 추가 · Mac 로그는 그대로)
- 버린 대안: `cmd.exe /c start` (UNC 경고 세 줄이 깨진 한글로 찍힘 — 실측) · `wslu` 설치 + `BROWSER=wslview` (설치가 필요하고 `file://` 주소 처리 미확인) · 로그에 경로만 추가(브라우저는 여전히 안 열림)

### 진행 로그 (KST)

- 2026-10-05 10:33: 계획서 작성 (Draft)
- 2026-10-05 10:41: 사용자 승인 — 착수 (In Progress)
- 2026-10-05 10:49: `explorer.exe '\\wsl.localhost\Ubuntu\...\반감기_사이클\판단차트.html'` 실측 — 종료코드 1 · 0.677초 · 표준출력 0바이트 · 표준오류 0바이트 (한글 경로 그대로 전달). 붙잡지 않으므로 `subprocess.run` 으로 기다린다
- 2026-10-05 10:50: 구현. `BROWSER=true` 실행 — 종료코드 0 · 마지막 두 줄 `[main] 차트 저장: /home/...` · `[open_in_browser] Windows 경로: \\wsl.localhost\Ubuntu\...` · `gio` 0줄. 함수 이름 칸이 `[main]` 이 아니라 `[open_in_browser]` 로 찍힌다(로그 포맷이 함수명을 넣는다)
- 2026-10-05 10:51: 기본 실행 — 종료코드 0 · 같은 두 줄 · `gio` 0줄 · WARNING 0줄. 브라우저가 열렸는지는 사용자 확인 대기
- 2026-10-05 10:52: 스크래치 시뮬레이션(`simulate_open.py`, 세션 스크래치) — ① 커널 `23.6.0`(Mac) → `webbrowser.open(file://...)` 1회 · `subprocess.run` 0회 · 로그 0줄 (BROWSER=true 도 같다) ② WSL · `explorer.exe` FileNotFoundError → DEBUG Windows 경로 + WARNING 1줄 · 예외 없음 ③ WSL · `wslpath` CalledProcessError → WARNING 1줄 · 예외 없음 ④ WSL1 커널 이름(`4.4.0-19041-Microsoft`) + BROWSER=true → WSL 로 판정 · Windows 경로 줄 · `webbrowser.open` 1회
- 2026-10-05 10:56: 사용자 확인 — Windows 브라우저에 차트 탭 2개(10:49 `explorer.exe` 실측 · 10:51 기본 실행)가 열렸다. 종료코드 1 이 «성공한 호출»의 값임이 확정됐다
- 2026-10-05 11:05: `/code-review xhigh` 1회차 — 발견 10건. 분류와 조치:
  - [무거움·수정] `wslpath` 출력 디코딩(`text=True`)의 `UnicodeDecodeError` 가 except 밖으로 새어 차트를 저장한 뒤 종료코드 1 로 죽는다. 이 PC 는 모든 로캘(C · POSIX · C.UTF-8 · 미설치 ko_KR.EUC-KR)에서 파이썬이 UTF-8 로 돌아 재현 불가지만 모양이 「죽는다」라 고친다. 리뷰가 낸 `encoding="utf-8"` 대신 **except 에 `UnicodeDecodeError` 를 더했다** — 비 UTF-8 로캘에서는 파일시스템 인코딩도 같이 바뀌어 `wslpath` 에 넘긴 바이트가 UTF-8 이 아닐 수 있고, 그때 utf-8 강제가 오히려 예외를 만든다. 같은 모양(텍스트 디코딩하는 subprocess 호출) 검색: diff 안 1곳(`wslpath`)뿐 — `explorer.exe` 호출은 출력을 받지 않는다. 변형 확인: 스크래치 ⑤ 케이스(`wslpath` 가 UnicodeDecodeError) — 고치기 전 `예외: UnicodeDecodeError(...)` 로 샘 → 고친 뒤 WARNING 1줄 · 예외 없음, ①~④ 결과 불변
  - [가벼움·안 고침] VS Code Remote-WSL 이 `BROWSER=…/helpers/browser.sh` 를 넣으면 `explorer.exe` 분기를 건너뛴다 — 실측: VS Code 터미널 셸(pid 1266 · 1336, `TERM_PROGRAM=vscode`)의 환경에 `BROWSER` 없음 · `~/.bashrc` 등 시작 파일에 export 없음 · 사용자의 처음 로그가 `gio` 로 갔다(BROWSER 가 있었다면 그쪽을 먼저 부른다) → 실제 환경 0건
  - [가벼움·안 고침] `BROWSER` 확인이 `wslpath` 뒤에 있어 `wslpath` 가 실패하면 `BROWSER=true` 에서도 거짓 WARNING — `wslpath` 실패 실제 0건
  - [가벼움·안 고침] 커널 이름 판정의 오판 두 방향(Docker Desktop 컨테이너 = 거짓 양성 → WARNING · 사용자 지정 커널 = 거짓 음성 → 예전 `gio` 동작) — 실제 0건. 주석 「WSL 커널 이름에만」의 부정확은 그 외
  - [가벼움·안 고침] `CalledProcessError` 의 문자열에 `wslpath` 표준오류가 안 실린다 — 실제 0건
  - [가벼움·안 고침] `wslpath` 실패 시 WARNING 의 「위에 찍힌 경로」가 리눅스 경로뿐 — 실제 0건
  - [가벼움·안 고침] 경로에 쉼표가 있으면 `explorer.exe` 가 오해석 / `.html` 연결 앱이 브라우저가 아닐 수 있다 — 실제 경로에 쉼표 0 · 연결 앱은 사용자 선택
  - [가벼움·안 고침] interop 정지 시 `subprocess.run` 에 timeout 이 없어 멈춘다 — 실측 0.677초 · 정지 0건
  - [그 외] docstring 「열지 못하면 WARNING 만 남기고 돌아간다」가 종료코드를 안 보는 실패·`webbrowser.open` 거짓 반환까지 덮는 것처럼 읽힌다 · `str(path)` 대신 Path 를 넘길 수 있다(전역 python.md 「Path 객체만」)
- 2026-10-05 11:22: `/code-review xhigh` 2회차 — 발견 13건, 무거움 0. 새로 나온 가벼움 2건: WSL 에서 `BROWSER` 를 따를 때 리눅스 URI(`file:///home/...`)를 넘겨 Windows 쪽 브라우저 지정(`chrome.exe` · VS Code `browser.sh`)이면 못 연다 — 실제 환경에 `BROWSER` 없음(위 1회차 실측) / WSL 이면 리눅스 쪽 열기 수단(wslview · WSLg 브라우저)을 건너뛴다 — 이 PC 에 그런 수단 0개(`_tryorder` = `['gio']`). 새 그 외 2건: `webbrowser.open` 두 곳 중복 · 헬퍼를 `utils/cli_helpers.py` 로 올리라는 높이 지적(비목표로 미룸). 주석 「리눅스에는 html 을 열 앱이 없고」가 이 PC 사정을 일반 사실처럼 쓴다(그 외). 고칠 것 0 → 종료
- 2026-10-05 11:22: `poetry run python validate_project.py` — Ruff 통과 · PyRight 통과 · Pytest passed=1638 failed=0 skipped=0
- 2026-10-05 11:22: 미룬 지적 거르기 — 옮길 것 0건. 거른 지적(회차 사이 중복은 합침):
  - `BROWSER` 확인이 `wslpath` 뒤 → 거짓 WARNING — 기준 2(경고가 하나 더 나갈 뿐) · `wslpath` 실패 실제 0건
  - WSL + `BROWSER` 분기가 리눅스 URI 를 넘김 → 안 열림 — 기준 2(안 열릴 뿐 틀린 값을 내지 않음, Windows 경로 줄은 남음) · VS Code 터미널 `BROWSER` 0건
  - 커널 이름 판정의 거짓 양성(컨테이너) · 거짓 음성(사용자 지정 커널) — 기준 2(WARNING 또는 예전 `gio` 실패) · 실제 0건
  - 리눅스 쪽 열기 수단을 건너뜀 — 기준 2(Windows 연결 앱으로 열림) · 이 PC 에 수단 0개
  - `subprocess.run` timeout 없음 → interop 정지 시 멈춤 — 기준 1(실측 0.677초 · 정지 0건 · interop 고장이 있어야 남) · 기준 2(멈출 뿐)
  - `CalledProcessError` 메시지에 표준오류 없음 · `wslpath` 실패 시 안내 경로가 리눅스 경로뿐 — 기준 2(안내가 어색할 뿐)
  - 쉼표 든 경로 오해석 · `.html` 연결 앱 — 기준 2 · 실제 경로 쉼표 0
  - docstring 과장 · 주석 두 곳의 부정확(「커널 이름에만」 · 「리눅스에는 html 을 열 앱이 없고」) · `str(path)` · `webbrowser.open` 중복 · 헬퍼 위치 — 기준 3(그 외)
- 2026-10-05 11:22: `/commit` 후보 5개를 이 계획서에 옮기고 Done
- 2026-10-05 11:27: 사용자 요청으로 「그 외」 주석 세 곳 수정 (주석만 — 계획서 예외) — docstring 을 「열지 못해도 실행을 멈추지 않는다 · 열렸는지는 확인하지 않는다」로, 커널 이름 판정 주석에 Docker Desktop 컨테이너(거짓 양성)와 이름을 바꾼 사용자 지정 커널(거짓 음성)을, 「리눅스에는 html 을 열 앱이 없고」를 「리눅스 브라우저를 따로 깔지 않은 WSL 에는」으로 바꾸고 리눅스 쪽 수단이 있어도 Windows 쪽으로 간다는 점을 밝혔다. black 변경 없음 · ruff 통과 · pyright 0 errors. 커밋 후보는 그대로 맞다
