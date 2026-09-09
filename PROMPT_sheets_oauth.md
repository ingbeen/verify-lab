# 의뢰 — google-sheets MCP 의 OAuth 클라이언트 시크릿 옮기기 (mac -> WSL)

> **이 파일 하나로 두 PC 가 각자 할 일을 한다.** 세션에 이 파일 경로만 주면 된다.
>
> **먼저 0 절로 어느 PC 인지 판별하고, 자기 절차만 수행한다.** 수행한 항목은 체크박스를
> 채우고 4 절에 상태를 적는다.
>
> **[중요] 이 파일에 시크릿 값을 절대 적지 않는다.** 이 저장소는 PUBLIC 이다.
> 4 절에 적는 것은 「했다/못 했다」뿐이며, `client_secret` 은 화면에도 찍지 않는다.

## 0. 이 PC 가 어느 쪽인가

```bash
python3 -c "import socket, sys; print(socket.gethostname(), '/', sys.platform)"
```

| 결과 | 이 PC 는 | 할 일 |
| --- | --- | --- |
| `darwin` 이 나온다 | **보내는 쪽 (mac)** | **1 절** |
| `linux` 이고 호스트가 `DESKTOP-` 로 시작 | **받는 쪽 (WSL)** | **2 절** |
| 그 밖 | 판단할 수 없다 | 사용자에게 어느 쪽인지 묻고 시작한다 |

## 왜 이 파일만 사람이 옮기나 (양쪽 공통)

`claude-config-export` 는 **`keys/**` 를 담지 않는다** — 이 저장소가 PUBLIC 이라 한 번
커밋되면 git 이력에서 지울 수 없다. 그래서 자격증명은 번들 밖으로 사람이 옮긴다.

받는 쪽에 필요한 파일은 둘인데 **성격이 다르다.**

| 파일 | 받는 쪽에서 |
| --- | --- |
| `sheets-mcp-token.json` | **재인증하면 생긴다.** 옮기지 않는다 (동의화면이 「테스트」 상태라 7일마다 만료된다) |
| `sheets-mcp-oauth.json` | **재인증으로 생기지 않는다.** Google Cloud Console 에서 발급받은 클라이언트 시크릿이라 옮기거나 다시 내려받아야 한다 |

**이 의뢰의 대상은 두 번째 하나다.** 받는 쪽의 `uvx` 는 이미 설치돼 있고, `~/.claude.json` 도
이미 그 경로를 가리키고 있어 **설정을 고칠 일은 없다.**

---

## 1. 보내는 쪽 (mac) 에서 할 일

- [x] **1-1. 파일이 있는지 확인한다**

  ```bash
  ls -l ~/.claude/keys/
  ```

  `sheets-mcp-oauth.json` 이 없으면 **1-5 로 건너뛴다**(Console 재발급이 답이다).

- [x] **1-2. 맞는 파일인지만 가린다 — 내용은 출력하지 않는다**

  ```bash
  python3 -c "
  import json, pathlib
  d = json.loads((pathlib.Path.home() / '.claude/keys/sheets-mcp-oauth.json').read_text())
  kind = next(iter(d))
  print('타입:', kind)
  print('project_id:', d[kind].get('project_id', '(없음)'))
  print('client_id 앞 12자:', d[kind].get('client_id', '')[:12])
  "
  ```

  **`client_secret` 을 화면에 찍지 않는다.** 대화 로그에 남으면 옮기는 의미가 없다.
  위 명령은 신원을 확인할 만큼만 본다.

- [x] **1-3. 사용자가 가져갈 수 있게 꺼내둔다**

  ```bash
  cp ~/.claude/keys/sheets-mcp-oauth.json ~/Downloads/sheets-mcp-oauth.json
  ```

  **저장소에 복사하지 않는다.** verify-lab 안 어디에도 두지 않고 `git add` 하지 않는다.
  설치형 앱의 시크릿이라 절대 비밀은 아니지만, PUBLIC 저장소에 올라가면 자동 스캐너가
  **무효화하거나 남이 할당량을 쓴다.**

- [x] **1-4. 사용자에게 알린다**

  다운로드 폴더에 꺼내뒀고, **직접 옮긴 뒤 원본 사본을 지우면 된다**고 전한다.
  전달 수단은 사용자가 고른다 — USB, 비밀번호 관리자, 종단간 암호화된 메신저 중 하나.

- [ ] **1-5. (파일이 없을 때만) Console 재발급을 안내한다**

  같은 프로젝트의 「사용자 인증 정보」에서 **데스크톱 앱 클라이언트**의 JSON 을 내려받으면 된다.
  새 클라이언트를 만들 경우 **동의화면의 테스트 사용자 목록에 그 계정이 있는지** 확인한다.

- [x] **1-6. 4 절에 상태를 적고, 사용자에게 커밋을 요청한다** (git 은 사용자가 직접 한다)

- [ ] **1-7. 전달이 끝났다는 확인을 받으면 꺼내둔 사본을 지운다**

  ```bash
  rm ~/Downloads/sheets-mcp-oauth.json
  ```

---

## 2. 받는 쪽 (WSL) 에서 할 일

**2-0 게이트: 파일이 이 PC 에 도착했는지 먼저 확인한다.** 사용자에게 받은 경로를 묻고,
없으면 여기서 멈춘다 — 이 파일은 git 으로 오지 않는다.

- [ ] **2-1. 제자리에 두고 권한을 좁힌다**

  ```bash
  mkdir -p ~/.claude/keys
  mv <받은경로>/sheets-mcp-oauth.json ~/.claude/keys/sheets-mcp-oauth.json
  chmod 700 ~/.claude/keys
  chmod 600 ~/.claude/keys/sheets-mcp-oauth.json
  ```

- [ ] **2-2. 설정이 그 경로를 가리키는지 확인만 한다** (고칠 일은 없다)

  ```bash
  python3 -c "
  import json, pathlib
  d = json.loads((pathlib.Path.home() / '.claude.json').read_text())
  env = d['mcpServers']['google-sheets']['env']
  for k, v in env.items():
      print(k, '->', v, '(있음)' if pathlib.Path(v).exists() else '(없음)')
  "
  ```

  `CREDENTIALS_PATH` 가 **있음**이면 된다. `TOKEN_PATH` 는 **없음이 정상**이다 — 다음 단계에서 생긴다.

- [ ] **2-3. Claude Code 를 다시 시작하고 연결을 확인한다**

  `/mcp` 로 `google-sheets` 가 뜨는지 본다. 첫 호출에서 브라우저 인증이 열린다.

- [ ] **2-4. 인증 뒤 토큰이 생겼는지 확인한다**

  ```bash
  ls -l ~/.claude/keys/sheets-mcp-token.json
  ```

  생겼으면 끝이다. **7일 뒤 만료되면 다시 인증하면 되고, 이 의뢰를 되풀이할 필요는 없다** —
  만료되는 것은 토큰이지 클라이언트 시크릿이 아니다.

- [ ] **2-5. 4 절에 상태를 적는다**

---

## 3. 끝나면

**양쪽 체크박스가 모두 채워지면 이 파일을 지운다.** 절차 자체는 `claude-config-import`
스킬 문서의 「무엇이 애초에 번들에 없는가」에 이미 있다.

---

## 4. 상태 (값이 아니라 「했다/못 했다」만 적는다)

> **[중요] `client_secret`·`client_id` 전체·토큰을 여기에 적지 않는다.**

### 보내는 쪽 (mac)

| 항목 | 상태 |
| --- | --- |
| 파일이 있었나 | **있음** (405 bytes · 권한 600 · 타입 `installed`) |
| `project_id` | `yubeen-mcp-tools` |
| 어떻게 처리했나 | **다운로드 폴더로 꺼냄** — 원본과 바이트 동일 확인(`cmp`) |
| 사용자에게 전달 안내했나 | **예** |
| 꺼내둔 사본을 지웠나 | **아직** — WSL 도착 확인 뒤 1-7 실행 |

### 받는 쪽 (WSL)

| 항목 | 상태 |
| --- | --- |
| 파일이 도착했나 | (예 / 아니오) |
| 배치와 권한(600) | (완료 / 미완) |
| `/mcp` 연결 | (성공 / 실패 — 증상) |
| 토큰 생성 | (생김 / 안 생김) |
