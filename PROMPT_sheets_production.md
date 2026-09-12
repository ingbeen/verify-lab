# 런북 — google-sheets MCP 인증 (새 PC 포함)

> **이 파일 경로만 주면 된다.** AI 가 상태를 점검하고, 브라우저 승인까지 띄우고, 재발급됐는지 검증한다.
>
> **[중요] 이 파일에 시크릿 값을 절대 적지 않는다.** 이 저장소는 PUBLIC 이다.
> `client_secret`·`refresh_token` 은 화면에도 찍지 않는다 — **존재 여부와 지문(해시 앞 12자리)만** 본다.

## 0. 이미 끝난 것과 PC 마다 필요한 것

**7일 재인증은 2026-09-12 에 없앴다.** 원인은 「검증 안 된 앱」이 아니라
**OAuth 동의 화면의 게시 상태가 `Testing`** 인 것이었다.

> A Google Cloud Platform project with an OAuth consent screen configured for an external
> user type and **a publishing status of "Testing"** is issued a refresh token expiring in 7 days
> — [Google Identity: Using OAuth 2.0](https://developers.google.com/identity/protocols/oauth2)

**게시 상태는 프로젝트(`yubeen-mcp-tools`)의 속성이라 PC 마다 다시 하지 않는다.**
새 PC 에서 할 일은 토큰 발급뿐이다.

| 항목 | 상태 |
| --- | --- |
| 게시 상태 프로덕션 전환 | **완료 (2026-09-12)** — 전 PC 공통 |
| 클라이언트 시크릿 `sheets-mcp-oauth.json` | **PC 마다 필요.** 재발급 없이는 못 만든다 — 기존 PC 에서 복사해 온다 |
| `~/.claude.json` 의 MCP 등록 | **PC 마다 필요.** `claude-config-import` 스킬이 옮긴다 |
| 토큰 `sheets-mcp-token.json` | **PC 마다 발급.** 이 런북의 본론 |

**확인(verification)은 만료 조건이 아니다.** 공식 문서의 만료 조건 목록에 「미인증」 항목이 없다.
프로덕션 전환 후에도 남는 조건 중 실제로 걸릴 것은 둘뿐이다.

| 조건 | 우리 경우 |
| --- | --- |
| **6개월간 한 번도 안 씀** | **걸릴 수 있다** |
| **사용자가 직접 접근 권한 취소** | 본인이 계정 설정에서 지우지 않으면 해당 없음 |
| Gmail 스코프 + 비밀번호 변경 | **해당 없음** — scope 가 `spreadsheets`·`drive` 뿐이다 |
| 계정당 토큰 상한 초과 · 시간제한 액세스 · 관리자 제한 | 1인 개인 계정이라 무관 |

**「확인되지 않은 앱」 경고 화면은 남는다** — `drive` 가 restricted scope 라서다.
인증할 일이 없어지므로 실질 부담은 사라진다.

**서비스 계정으로 바꾸는 안은 버렸다.** 만료 개념이 없어지는 대신 **소유권 모델이 바뀐다** —
만든 시트가 서비스 계정 소유가 되어 내 드라이브에 안 보이고, 기존 시트는 그 계정에 일일이 공유해야 한다.

**자격증명을 저장소 안에 두지 않는다.** `[실측] 2026-09-09` 클라이언트 시크릿이 저장소 루트로
도착했고 `.gitignore` 에 걸리지 않아 untracked 로 떴다. 커밋됐으면 PUBLIC 이력에서 지울 수 없었다.
**옮길 때는 저장소 밖(`~/`)에 두고 시작한다.**

---

## 1. AI 가 실행할 순서

**사용자에게 되묻지 말고 1-1 부터 그대로 실행한다.** 사람이 할 일은 1-5 의 브라우저 승인 하나뿐이다.

### 1-1. 상태를 먼저 본다 (읽기만 한다)

```bash
python3 -c "
import json, pathlib, hashlib, datetime
home = pathlib.Path.home()
cfg = json.loads((home / '.claude.json').read_text())
srv = cfg.get('mcpServers', {}).get('google-sheets')
print('MCP 등록:', '있음' if srv else '없음 -> claude-config-import 로 먼저 등록한다')
if srv:
    print('command:', srv['command'])
    for k, v in srv['env'].items():
        print(k, '->', v, '(있음)' if pathlib.Path(v).exists() else '(없음)')
    tok = pathlib.Path(srv['env']['TOKEN_PATH'])
    if tok.exists():
        d = json.loads(tok.read_text())
        rt = d.get('refresh_token')
        print('옛 지문:', hashlib.sha256(rt.encode()).hexdigest()[:12] if rt else '없음')
        print('access token expiry(UTC):', d.get('expiry'))
        print('파일 mtime:', datetime.datetime.fromtimestamp(tok.stat().st_mtime))
    else:
        print('토큰 없음 - 첫 발급이다')
"
```

- **`sheets-mcp-oauth.json` 이 없으면 여기서 멈춘다.** 그 파일은 재발급 없이는 못 만든다 —
  기존 PC 에서 복사해 오거나, Google Cloud Console 의 「사용자 인증 정보」에서
  **데스크톱 앱 클라이언트** JSON 을 새로 내려받는다
- **「옛 지문」을 반드시 기록해 둔다.** 1-6 에서 이 값이 바뀌었는지로 재발급 성공을 판정한다

### 1-2. 실행 중인 서버를 먼저 종료한다

**이걸 건너뛰면 살아있는 서버가 옛 토큰으로 새 파일을 덮어쓴다.** VSCode 창마다 하나씩 뜨므로
여러 개일 수 있다.

```bash
ps -eo pid,args --no-headers | grep 'mcp-google-sheets' | grep -v grep | awk '{print $1}' | xargs -r kill
ps -eo pid,args --no-headers | grep 'mcp-google-sheets' | grep -v grep | cut -c1-120
```

두 번째 줄이 **비어 있어야** 다음으로 간다.

> **[중요] `pkill -f 'mcp-google-sheets'` 를 쓰지 않는다.** 자기 명령줄까지 물어 **셸이 함께 죽는다**
> (exit 144). `[실측] 2026-09-12` 위 형태는 `grep -v grep` 이 파이프라인 자신을 걸러내서 안전하다.

### 1-3. 기존 토큰을 «옮긴다» (지우지 않는다)

```bash
mv ~/.claude/keys/sheets-mcp-token.json ~/.claude/keys/sheets-mcp-token.json.bak
```

첫 발급이라 파일이 없으면 건너뛴다.

### 1-4. 서버를 셸에서 띄워 인증 URL 을 꺼내 브라우저에 넘긴다

**이 서버는 기동 시점에 OAuth 를 돌린다.** 스크래치 디렉터리를 `$SCRATCH` 로 잡고 실행한다.

```bash
UVX=$(python3 -c "import json,pathlib;print(json.loads((pathlib.Path.home()/'.claude.json').read_text())['mcpServers']['google-sheets']['command'])")
nohup timeout 1800 env \
  CREDENTIALS_PATH=$HOME/.claude/keys/sheets-mcp-oauth.json \
  TOKEN_PATH=$HOME/.claude/keys/sheets-mcp-token.json \
  "$UVX" --with "mcp<2" mcp-google-sheets@latest \
  < /dev/null > "$SCRATCH/auth_out.log" 2> "$SCRATCH/auth_err.log" &
```

URL 을 꺼내 **플랫폼별로** 브라우저에 넘긴다.

```bash
URL=$(grep -o 'https://accounts.google.com[^ ]*' "$SCRATCH/auth_err.log" | head -1)
case "$(uname -s)" in
  Darwin) open "$URL" ;;
  Linux)  /mnt/c/WINDOWS/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -Command "Start-Process '$URL'" ;;
esac
echo "$URL"
```

- **URL 이 아직 안 나왔으면 잠시 뒤 다시 grep 한다.** 서버 기동에 몇 초 걸린다
- **꺼낸 URL 을 사용자에게도 그대로 보여준다.** 브라우저가 안 열렸을 때 붙여넣을 수 있어야 한다

> **[함정] WSL 에서는 첫 인증이 「Connecting...」으로 영원히 멈춘다.** `[실측] 2026-09-09`
>
> WSL 에는 열 브라우저가 없어(`gio: ... Operation not supported`) 콜백을 무한정 기다린다.
> MCP initialize 가 끝나지 않으니 `/mcp` 는 계속 「Connecting...」이고 **에러도 뜨지 않는다.**
> 네트워크 문제도 설정 문제도 아니다 — 자격증명 경로를 아무리 확인해도 원인이 안 나온다.
> 위 절차가 그 함정을 우회한다. **mac 에서는 서버가 스스로 브라우저를 열지만 같은 절차로 해도 된다.**

### 1-5. 사용자가 브라우저에서 승인한다 (사람이 하는 유일한 단계)

| # | 화면 | 누를 것 |
| --- | --- | --- |
| 1 | 계정 선택 | **기존에 시트를 만들어 온 계정.** 다른 계정을 고르면 기존 시트가 안 보인다 |
| 2 | 「이 앱은 확인되지 않았습니다」 | `고급` → **`yubeen-mcp-tools(안전하지 않음)으로 이동`** |
| 3 | 권한 요청 (스프레드시트 · 드라이브) | 둘 다 체크 → **`계속`** |
| 4 | 완료 | `The authentication flow has completed.` |

- **URL 은 그 프로세스 전용이다.** 포트와 `state` 가 매번 달라 재사용할 수 없고,
  프로세스를 죽이면 콜백을 받을 곳이 사라진다. 시간을 넘겼으면 **1-4 부터** 다시 돌린다
- 2번 경고는 **프로덕션 전환 후에도 남는 것이 정상**이다 (0 절)

### 1-6. 재발급됐는지 «지문으로» 검증하고 권한을 좁힌다

```bash
grep -c 'Successfully authenticated' "$SCRATCH/auth_err.log"
chmod 600 ~/.claude/keys/sheets-mcp-token.json
ls -l ~/.claude/keys/
python3 -c "
import json, pathlib, hashlib
base = pathlib.Path.home() / '.claude/keys'
new = json.loads((base / 'sheets-mcp-token.json').read_text())
fp = lambda d: hashlib.sha256(d['refresh_token'].encode()).hexdigest()[:12] if d.get('refresh_token') else None
print('refresh_token 존재:', bool(new.get('refresh_token')))
print('새 지문:', fp(new))
print('scopes:', new.get('scopes'))
bak = base / 'sheets-mcp-token.json.bak'
if bak.exists():
    old = json.loads(bak.read_text())
    print('옛 지문:', fp(old))
    print('바뀌었나:', '예 - 새로 발급됨' if fp(new) != fp(old) else '아니오 - 기존 것 재사용(실패)')
"
```

**서버가 만든 파일은 644 로 나온다.** 600 으로 좁히는 것이 이 단계의 실제 일이다.
**지문이 안 바뀌었으면 실패다** — 1-2 의 서버 종료가 덜 됐을 가능성을 먼저 본다.

새 토큰만으로 재인증 없이 뜨는지 확인한다. **`Please visit` 가 0회여야 한다.**

```bash
timeout 60 env \
  CREDENTIALS_PATH=$HOME/.claude/keys/sheets-mcp-oauth.json \
  TOKEN_PATH=$HOME/.claude/keys/sheets-mcp-token.json \
  "$UVX" --with "mcp<2" mcp-google-sheets@latest \
  < /dev/null > "$SCRATCH/verify_out.log" 2> "$SCRATCH/verify_err.log"
grep -c 'Please visit' "$SCRATCH/verify_err.log"
```

### 1-7. 정리하고 사용자에게 재시작을 안내한다

```bash
rm -f ~/.claude/keys/sheets-mcp-token.json.bak
```

**Claude Code 창을 전부 재시작**해야 한다 — 1-2 에서 모든 창의 서버를 죽였다.
재시작 후 `/mcp` 가 `google-sheets: Connected` 면 끝이다.

---

## 2. 읽지 않으면 틀리는 것

### 토큰이 둘이고, 자동인 것은 하나뿐이다

| | 수명 | 자동 갱신 | 죽으면 |
| --- | --- | --- | --- |
| **액세스 토큰** (`token`) | **1시간** | **네 — 라이브러리가 알아서** | 티도 안 난다 |
| **리프레시 토큰** (`refresh_token`) | 프로덕션이면 사실상 무기한 | **아니오** | **브라우저로 직접 승인해야 한다** |

**[중요] 파일 수정 시각(mtime)을 「재인증했다」로 읽지 않는다.** 액세스 토큰이 갱신될 때마다
라이브러리가 `sheets-mcp-token.json` 을 **통째로 다시 쓴다.** `[실측] 2026-09-12` mtime 07:30 을
재인증으로 오독했는데, 파일의 `expiry` 가 08:30 이라 **정확히 1시간짜리 액세스 토큰 갱신**이었다.

**판별은 `expiry` 로 한다** — mtime 으로부터 약 1시간 뒤면 액세스 토큰 갱신이다.
**재인증 여부는 `refresh_token` 의 지문**으로만 가른다.

### 게시 상태를 되돌리는 두 가지를 누르지 않는다

- **`대상` 탭의 「테스트로 돌아가기」** — 누르면 7일 만료가 그대로 복귀한다
- **검증 제출 · 「브랜딩 확인」** — 앱 도메인·개인정보처리방침에 **실제로 소유하지 않는 URL**
  (`sheets-mcp.com`)을 넣어 게시했다. 제출하면 Search Console 도메인 확인에서 막히고,
  심사 동안 상태가 묶인다. **개인 용도는 검증이 선택사항**이므로 제출할 이유가 없다

---

## 3. Console 을 다시 봐야 할 때

**메뉴에서 `Google Auth Platform` 을 최상위에서 찾지 않는다 — `API 및 서비스` 안에 있다.**
예전 이름은 「OAuth 동의 화면」이며, 지금은 개요 / 브랜딩 / **대상** / 클라이언트 / 데이터 액세스
탭으로 쪼개져 있다. 게시 버튼은 **대상** 탭에만 있다.

```
탐색 메뉴 -> API 및 서비스 -> Google Auth Platform -> 대상(Audience)
https://console.cloud.google.com/auth/audience?project=yubeen-mcp-tools
```

**게시 상태가 「프로덕션 단계」이고 「테스트로 돌아가기」 버튼이 보이면 정상이다.**
그 버튼은 프로덕션일 때만 나온다.

---

## 4. 무엇으로 성공을 판정하나

**즉시 검증할 수단이 없다.** refresh token 의 만료 시각은 토큰 파일에 없고
(파일의 `expiry` 는 1시간짜리 access token 것이다), Google 도 그 값을 알려주지 않는다.

| 언제 | 무엇을 본다 | 뜻 |
| --- | --- | --- |
| 지금 | Console 게시 상태가 **「프로덕션 단계」** | 조건은 갖췄다 |
| 지금 | 지문이 **바뀌었다** | 토큰을 실제로 새로 받았다 |
| 지금 | `/mcp` 가 **Connected** | 토큰이 살아 있다 |
| **8일 뒤 이후** | 시트 도구를 불렀을 때 **인증을 요구하지 않는다** | **전환이 실제로 먹었다** |

**마지막 줄이 진짜 판정이다.** 그전까지는 「조건을 갖췄다」까지만 말한다.
8일 뒤에 또 인증을 요구하면 게시 상태가 실제로 안 바뀐 것이므로 3 절부터 다시 본다.

---

## 5. 실행 기록

| PC | 날짜 | 결과 |
| --- | --- | --- |
| WSL (`DESKTOP-`) | 2026-09-12 | 게시 상태 프로덕션 전환 · 토큰 재발급(지문 변경 확인) · 권한 600 · 재기동 시 `Please visit` 0회 |

---

## 6. 이 런북을 가리키는 곳

**이 파일이 google-sheets 인증 절차의 SoT 다.** 아래 둘은 절차를 복제하지 않고 **여기를 가리킨다** —
두 벌이 되면 한쪽이 낡고, 어느 쪽이 현재인지 매번 판별해야 한다.

| 문서 | 거기 적힌 것 |
| --- | --- |
| 전역 `~/.claude/CLAUDE.md` 「구글 스프레드시트 (Google Sheets MCP)」 | 7일 만료를 없앴다는 사실 · 남는 만료 조건 둘 · mtime 을 재인증으로 읽지 말 것 · **이 파일로의 포인터** |
| [claude-config-import 스킬](.claude/skills/claude-config-import/SKILL.md) 「무엇이 애초에 번들에 없는가」 | 토큰 파일은 번들에 안 담기고 재인증으로 생긴다는 것 · **이 파일로의 포인터** |

**절차를 고치면 이 파일만 고친다.** 위 둘은 포인터라 따라 고칠 것이 없다.

**단, 전역 `~/.claude/CLAUDE.md` 를 고쳤다면 `claude-config-export` 를 다시 돌려야 다른 PC 로 넘어간다.**
전역 파일은 git 으로 추적되지 않고 번들을 통해서만 이동한다.
