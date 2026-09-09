# 의뢰 — google-sheets MCP 의 7일 재인증 없애기 (Testing -> 프로덕션)

> **이 파일 하나로 절차가 끝난다.** 새 세션에 이 파일 경로만 주면 된다.
>
> **[중요] 이 파일에 시크릿 값을 절대 적지 않는다.** 이 저장소는 PUBLIC 이다.
> 5 절에 적는 것은 「했다/못 했다」뿐이며, `client_secret`·`refresh_token` 은 화면에도 찍지 않는다.

## 0. 무엇을 왜 하는가

`google-sheets` MCP 는 **7일마다 재인증**을 요구한다. 원인은 「검증 안 된 앱」이 아니라
**OAuth 동의 화면의 게시 상태가 `Testing`** 인 것이다. 공식 문서 문구가 조건을 못박는다.

> A Google Cloud Platform project with an OAuth consent screen configured for an external
> user type and **a publishing status of "Testing"** is issued a refresh token expiring in 7 days
> — [Google Identity: Using OAuth 2.0](https://developers.google.com/identity/protocols/oauth2)

**게시 상태를 「프로덕션」으로 바꾸면 만료가 무기한이 된다.** 확인해 둔 사실은 아래와 같다.

| 항목 | 사실 | 출처 |
| --- | --- | --- |
| 검증(보안 감사) 필요 여부 | **불필요.** 사용자 100명 미만 개인 용도는 검증이 선택사항 | [When is verification not needed](https://support.google.com/cloud/answer/13464323?hl=en) |
| 전환 후 남는 만료 조건 | ① 6개월 미사용 ② 사용자가 직접 취소 ③ 계정당 토큰 상한 초과 | 위 OAuth 문서 |
| 전환해도 안 사라지는 것 | **「확인되지 않은 앱」 경고 화면.** `drive` 가 restricted scope 라서다. 인증할 일이 없어지므로 실질 부담은 사라진다 | [Manage App Audience](https://support.google.com/cloud/answer/15549945?hl=en) |
| 100명 신규 사용자 한도 | 미검증이라 걸리지만 **본인 1명이라 무관** | 같음 |

**서비스 계정으로 바꾸는 안은 버렸다.** 만료 개념이 없어지는 대신 **소유권 모델이 바뀐다** —
만든 시트가 서비스 계정 소유가 되어 내 드라이브에 안 보이고, 기존 시트는 그 계정에 일일이
공유해야 한다. 게시 상태 전환으로 되는 일이라 여기까지 갈 이유가 없다.

---

## 1. 먼저 현재 연결 상태를 본다

- [ ] **1-1. `/mcp` 로 `google-sheets` 가 Connected 인지 확인한다**

  「Connecting...」에 멈춰 있으면 **아래 3 절의 WSL 함정**이다. 그 경우 게시 상태 전환과
  무관하게 먼저 풀어야 하므로, 3 절을 읽고 오늘 안에 토큰을 만든 뒤 2 절로 간다.

- [ ] **1-2. 자격증명과 토큰이 제자리에 있는지 확인한다**

  ```bash
  ls -l ~/.claude/keys/
  python3 -c "
  import json, pathlib
  d = json.loads((pathlib.Path.home() / '.claude.json').read_text())
  for k, v in d['mcpServers']['google-sheets']['env'].items():
      print(k, '->', v, '(있음)' if pathlib.Path(v).exists() else '(없음)')
  "
  ```

  `sheets-mcp-oauth.json`(클라이언트 시크릿)은 **재발급 없이는 못 만든다.** 없으면
  Google Cloud Console 의 「사용자 인증 정보」에서 **데스크톱 앱 클라이언트** JSON 을 내려받는다.

---

## 2. 게시 상태를 프로덕션으로 바꾼다 (사람이 한다)

**AI 는 Google Cloud Console 에 접근할 수 없다.** 이 절은 사용자가 브라우저로 직접 한다.

- [ ] **2-1. Console 에서 전환한다**

  1. [Google Cloud Console](https://console.cloud.google.com/) → 프로젝트 **`yubeen-mcp-tools`**
  2. **Google Auth Platform → 대상(Audience)** — 예전 이름은 「OAuth 동의 화면」
  3. **「앱 게시」 / `PUBLISH APP`** 을 누르고 프로덕션 전환을 확인한다

- [ ] **2-2. 전환됐는지 화면에서 확인한다**

  게시 상태가 **「프로덕션」/`In production`** 으로 바뀌었으면 된다.
  **검증 제출을 요구받아도 하지 않는다** — 0 절 표대로 개인 용도는 검증이 선택사항이고,
  제출하면 심사 동안 오히려 상태가 묶인다.

- [ ] **2-3. AI 에게 전환 완료를 알린다**

---

## 3. 토큰을 새로 받는다

**이미 발급된 토큰에 전환이 소급 적용되는지는 문서에 없다.** 확실하게 하려고 새로 받는다.

- [ ] **3-1. 기존 토큰을 치운다** (지우지 않고 옮긴다 — 실패하면 되돌린다)

  ```bash
  mv ~/.claude/keys/sheets-mcp-token.json ~/.claude/keys/sheets-mcp-token.json.bak
  ```

- [ ] **3-2. 재인증한다 — 이 PC 가 어느 쪽인지에 따라 갈린다**

  ```bash
  python3 -c "import socket, sys; print(socket.gethostname(), '/', sys.platform)"
  ```

  **`darwin` (mac) 이면** — Claude Code 를 재시작하고 `google-sheets` 도구를 한 번 부르면
  브라우저가 알아서 열린다. 승인하면 끝이다.

  **`linux` + 호스트가 `DESKTOP-` (WSL) 이면** — 아래 함정 때문에 그냥은 안 된다.

  > **[함정] WSL 에서는 첫 인증이 「Connecting...」으로 영원히 멈춘다.** `[실측] 2026-09-09`
  >
  > 이 서버는 **기동 시점에** OAuth 를 돌리는데, WSL 에는 열 브라우저가 없어
  > (`gio: ... Operation not supported`) 콜백을 무한정 기다린다. MCP initialize 가 끝나지
  > 않으니 `/mcp` 는 계속 「Connecting...」이고 **에러도 뜨지 않는다.**
  > 네트워크 문제도 설정 문제도 아니다 — 자격증명 경로를 아무리 확인해도 원인이 안 나온다.

  WSL 은 아래 순서로 푼다. **서버를 셸에서 직접 띄워 인증 URL 을 꺼내 Windows 브라우저에 넘긴다.**

  ```bash
  # (1) 서버를 백그라운드로 띄운다 (stderr 를 파일로 받는다)
  cd <스크래치디렉터리>
  timeout 900 env \
    CREDENTIALS_PATH=$HOME/.claude/keys/sheets-mcp-oauth.json \
    TOKEN_PATH=$HOME/.claude/keys/sheets-mcp-token.json \
    ~/.local/bin/uvx --with "mcp<2" mcp-google-sheets@latest \
    < /dev/null > auth_out.log 2> auth_err.log &

  # (2) stderr 에서 인증 URL 을 꺼낸다
  grep -o 'https://accounts.google.com[^ ]*' auth_err.log | head -1

  # (3) Windows 기본 브라우저에 넘긴다
  URL=$(grep -o 'https://accounts.google.com[^ ]*' auth_err.log | head -1)
  /mnt/c/WINDOWS/System32/WindowsPowerShell/v1.0/powershell.exe \
    -NoProfile -Command "Start-Process '$URL'"
  ```

  - **URL 은 그 프로세스 전용이다.** 포트와 `state` 가 매번 달라 재사용할 수 없고,
    프로세스를 죽이면 콜백을 받을 곳이 사라진다
  - 승인 화면에서 **「이 앱은 확인되지 않았습니다」** 가 나오면 `고급` →
    `yubeen-mcp-tools(안전하지 않음)으로 이동` 을 누른다. 2 절을 마쳐도 이 경고는 남는다
  - 성공하면 stderr 마지막에 `Successfully authenticated using OAuth flow` 가 찍힌다

- [ ] **3-3. 새 토큰을 확인하고 권한을 좁힌다**

  ```bash
  chmod 600 ~/.claude/keys/sheets-mcp-token.json
  ls -l ~/.claude/keys/
  python3 -c "
  import json, pathlib
  d = json.loads((pathlib.Path.home() / '.claude/keys/sheets-mcp-token.json').read_text())
  print('refresh_token 존재:', bool(d.get('refresh_token')))
  print('scopes:', d.get('scopes'))
  "
  ```

  **서버가 만든 파일은 644 로 나온다.** 600 으로 좁히는 것이 이 단계의 실제 일이다.
  `refresh_token` 이 있고 scope 가 스프레드시트·드라이브 둘이면 정상이다.
  **값은 찍지 않는다** — 위 명령은 존재 여부만 본다.

- [ ] **3-4. 백업을 지운다**

  ```bash
  rm ~/.claude/keys/sheets-mcp-token.json.bak
  ```

- [ ] **3-5. Claude Code 를 재시작하고 `/mcp` 가 Connected 인지 본다**

---

## 4. 무엇으로 성공을 판정하나

**즉시 검증할 수단이 없다.** refresh token 의 만료 시각은 토큰 파일에 없고
(파일의 `expiry` 는 1시간짜리 access token 것이다), Google 도 그 값을 알려주지 않는다.

| 언제 | 무엇을 본다 | 뜻 |
| --- | --- | --- |
| 지금 | Console 게시 상태가 **「프로덕션」** | 조건은 갖췄다 |
| 지금 | `/mcp` 가 **Connected** | 토큰이 살아 있다 |
| **8일 뒤 이후** | 시트 도구를 불렀을 때 **인증을 요구하지 않는다** | **전환이 실제로 먹었다** |

**마지막 줄이 진짜 판정이다.** 그전까지는 「조건을 갖췄다」까지만 말한다.
8일 뒤에 또 인증을 요구하면 게시 상태가 실제로 안 바뀐 것이므로 2 절부터 다시 본다.

---

## 5. 상태 (값이 아니라 「했다/못 했다」만 적는다)

| 항목 | 상태 |
| --- | --- |
| `/mcp` 연결 (전환 전) | (Connected / Connecting 멈춤 / 실패 — 증상) |
| Console 게시 상태 전환 | (완료 / 미완) |
| 토큰 재발급 | (생김 / 안 생김) — 권한 600 여부도 적는다 |
| `/mcp` 연결 (전환 후) | (Connected / 실패 — 증상) |
| **8일 뒤 재인증 요구 여부** | (없었음 = 성공 / 또 요구함 = 실패) |

---

## 6. 끝나면

**5 절의 마지막 줄까지 채워지면** 이 파일을 지운다. 다만 **지우기 전에 아래를 승격한다** —
이 파일은 임시 산출물이고, 승격하지 않으면 다음에 같은 조사를 처음부터 반복한다.

| 옮길 것 | 목적지 |
| --- | --- |
| **WSL 인증 함정과 푸는 법** (3-2 의 인용 블록 + 명령) | 전역 `~/.claude/CLAUDE.md` 「구글 스프레드시트 (Google Sheets MCP)」 절 |
| **7일 만료의 원인이 게시 상태라는 것**과 프로덕션 전환 결과 | 같은 절 — 지금 그 절에 있는 "7일마다 만료된다. 만료되면 토큰을 지우고 한 번 더 인증한다" 문장을 **대체**한다 |
| 같은 문장의 **두 번째 사본** | [.claude/skills/claude-config-import/SKILL.md](.claude/skills/claude-config-import/SKILL.md) 「무엇이 애초에 번들에 없는가」의 표 — `sheets-mcp-token.json` 행이 같은 주장을 담고 있다. **한쪽만 고치면 어느 쪽이 현재인지 판별해야 한다** |
| **자격증명을 저장소 안에 두면 안 된다는 것** | 같은 절. `[실측] 2026-09-09` 클라이언트 시크릿이 저장소 루트로 도착했고 `.gitignore` 에 걸리지 않아 untracked 로 떴다. 커밋됐으면 PUBLIC 이력에서 지울 수 없었다 — **다음에 옮길 때는 저장소 밖(예: `~/`)에 두고 시작한다** |

전역 문서는 사용자 소유다. **AI 는 승인 없이 고치지 않는다** — 무엇을 어떻게 바꿀지 먼저 보인다.
