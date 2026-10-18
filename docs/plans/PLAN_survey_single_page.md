# Implementation Plan: 조사 문서를 한 장으로 합치고 끝난 조사의 코드를 지운다

> 작성/운영 규칙(SoT): `/impl-plan` 스킬(`~/.claude/skills/impl-plan/SKILL.md`)을 반드시 참고하세요.  
> (이 템플릿을 수정하거나 새로운 양식의 계획서를 만들 때도 해당 스킬을 포인터로 두고 준수합니다.)

**상태**: ✅ Done

---

> 상태는 🟡 Draft / 🔄 In Progress / ✅ Done. Done 조건과 기록 규칙은 `/impl-plan` 「3) 스킵 및 완료 규칙」이며 `~/.claude/hooks/plan_lint.py` 가 저장 때 검사한다.

---

**작성일**: 2026-10-16 08:37
**마지막 업데이트**: 2026-10-17 22:07
**관련 범위**: docs/조사(문서 4장 통합) · studies 셋 · scripts(실행 셋 · 수집 넷 · ECOS 프로브) · data(수집기 다섯) · 공유 계층 고아 정의 · tests · 규칙 문서
**관련 문서**: `.claude/rules/docs.md` · `.claude/rules/research.md` · `.claude/rules/trading.md` · `.claude/rules/session-bootstrap.md` · 루트 `CLAUDE.md` · `src/verify_lab/CLAUDE.md` · `scripts/CLAUDE.md` · `tests/CLAUDE.md` · `docs/INDEX.md` · `docs/COMMANDS.md`

---

## 1) 목표(Goal)

사용자 결정(2026-10-16): **`docs/조사/` 아래에는 폴더를 두지 않는다. 폴더형 조사 넷을 각 한 장으로 합쳐 `docs/조사/` 바로 아래로 옮기고,
「실질적으로 완료된 조사」이므로 그 조사의 코드를 지운다.**

- [x] 목표 1: 네 폴더(`레버리지_ETF_괴리` · `선물_대_레버리지_ETF` · `원달러_ETF_등가성` · `연속_등락`)의 문서 7장이
      `docs/조사/<이름>.md` 4장이 된다 — **내용을 빼지 않고**(무손실), 설계 장은 역방향 선례대로 측정 장 뒤 · 「해석」 앞에 둔다
- [x] 목표 2: `docs/조사/` 아래에 폴더가 생기면 테스트가 실패한다
- [x] 목표 3: 조사 셋의 측정 코드와 **그 셋만 쓰던 데이터 소스**(ECOS · FRED · ETN · KRX 선물 수집기와 ECOS 프로브),
      그리고 그것을 지우면 고아가 되는 공유 정의를 지운다. 남는 매매법 둘의 산출물은 **바이트 단위로 그대로**다
- [x] 목표 4: 규칙 문서가 「조사는 언제나 한 장」을 말하고, 저장소 안에 지운 경로 · 이름을 «지금 있는 것»으로 가리키는 곳이 남지 않는다

## 2) 비목표(Non-Goals)

- **시세 파일** — `storage/market/` · `storage/series/` 는 전부 남긴다(사용자 결정 2026-10-16). 중간선거 `규칙.md` 가
  레버리지 시세(QLD · TQQQ · UPRO · UDOW · SSO · DDM)를 원자료로 쓰고, 되살린 코드가 같은 데이터로 재현돼야 한다
- **국내 시세 어댑터** — `data/pykrx_collector.py` · `scripts/data/collect_pykrx.py` · `data/krx_common.py` · `data/krx_credentials.py` ·
  `data/constants.py` 와 pykrx 프로브 둘(`check_pykrx_etf.py` · `check_pykrx_splice.py`)은 남긴다(사용자 결정 2026-10-16)
- **재측정 · 수치 변경** — 합친 문서의 수치는 원문 그대로다. 조사 셋은 원본가로 잰 기록이며 그 사실을 머리말이 이미 밝힌다
- **문서 내용의 축약 · 정리** — 설계와 결과가 겹치는 서술도 지우지 않는다(무손실). 정리는 별도 작업이다
- **`tracks.py` 의 줄 삭제 · 순서 변경** — 지운 조사도 레지스트리에 남는다(`src/verify_lab/CLAUDE.md` 「어느 등급인가는 «레지스트리»가 정한다」). 주석만 고친다
- `reference/` — 읽기 전용(grep 결과 해당 줄 0건)
- `docs/DEFERRED_FINDINGS.md` 의 `.match` 항목을 **고치는 것** — 같은 테스트를 만지지만 고칠지는 사용자 판단이다. 이 계획서는 그 항목의 «예시 이름»만 지금 이름으로 맞춘다
- 이미 있던 것 — `tests/test_research_docs.py` 의 `_document_id` 가 한 장 문서를 모두 `docs/조사` 로 표시하는 것 ·
  `scripts/data/check_pykrx_splice.py:183` 의 `pd.to_numeric` 인라인 · `tracks.KINDS`·`tracks_of_kind` 의 런타임 미사용(테스트가 씀) — **언급만 한다**
- `.env` — 쓰지 않게 되는 `ECOS_API_KEY` 를 지우지 않는다(값을 보지 않는다 — 전역 「비밀값」). 사용자에게 알리기만 한다

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

- `.claude/rules/docs.md` 「배치는 «등급» 축이다」가 지금은 `docs/조사/<이름>/`(폴더형)과 `docs/조사/<이름>.md`(한 장)를 둘 다 허용한다.
  조사 열 건 중 여섯은 이미 한 장이고 넷이 폴더형이다. 사용자가 조사를 «끝난 것»으로 보고 한 모양으로 통일하기로 했다
- 폴더형 넷 중 셋(원달러_ETF_등가성 · 레버리지_ETF_괴리 · 선물_대_레버리지_ETF)은 코드가 살아 있고 `tests/test_tracks.py` 의
  `test_조사_등급은_종류도_조사다` 가 고정하듯 종류는 성질 조사다. 선례(옵션_만기일 · 월말_진입 · 만기_말일 · 원달러_그리드 · 역방향)는
  **조사로 끝낸 것은 코드를 지우고 되살리는 절차를 그 조사 문서가 갖는다**
- **검사 장치가 없다** — 조사 아래 폴더를 막는 테스트가 없어, 규칙만 바꾸면 다음에 폴더가 생겨도 아무것도 실패하지 않는다

### 실측 — 남는 매매법이 쓰는 것 (2026-10-16)

- 중간선거_사이클 · 반감기_사이클의 코드와 실행 · 차트 스크립트는 **ECOS · FRED · ETN · KRX 선물 · pykrx 수집기를 하나도 쓰지 않는다**(grep 0건)
- 두 매매법이 읽는 시세: SPY · DIA · QQQ 수정주가 · `GSPC_index` · `IXIC_index` · `BTCUSD_max` · BTC 계열 셋
- `measure.statistics.max_non_overlapping` 은 두 매매법 runner 가 쓴다 — 남는다

### 지울 것 — 실측 (2026-10-16, HEAD `2faa555`)

| 묶음 | 경로 | 규모 |
| --- | --- | --- |
| 조사 셋 패키지 | `src/verify_lab/studies/usdkrw_equivalence/` · `leverage_tracking/` · `futures_leverage/` | 1,649 + 1,543 + 2,606줄 |
| 조사 셋 실행 스크립트 | `scripts/run_usdkrw_equivalence.py` · `run_leverage_tracking.py` · `run_futures_leverage.py` | 470줄 |
| 조사 셋 전용 테스트 | `tests/test_studies_equivalence_*.py`(5) · `test_studies_futures_*.py`(6) · `test_studies_leverage_*.py`(4) — 14파일 | 4,941줄 |
| 수집기 넷 | `scripts/data/collect_{ecos,fred,etn,krx_futures}.py` · `src/verify_lab/data/{ecos_collector,ecos_credentials,fred_collector,etn_collector,krx_futures_collector}.py` | 2,284줄 |
| 수집기 넷의 테스트 | `tests/test_{ecos_collector,ecos_credentials,fred_collector,etn_collector,krx_futures_collector}.py` | 1,579줄 |
| ECOS 프로브 | `scripts/data/check_ecos.py` | 179줄 |
| 산출물 | `storage/results/조사/{원달러_ETF_등가성,레버리지_ETF_괴리,선물_대_레버리지_ETF,ECOS_실측}/` | git 추적 7 · 27 · 14 · 3파일 |
| 옛 문서 | `docs/조사/{레버리지_ETF_괴리,선물_대_레버리지_ETF,원달러_ETF_등가성}/{설계,결과}.md` · `docs/조사/연속_등락/결과.md` | 7장 |

### 지우면 고아가 되는 공유 정의 — 도달성 집계 (2026-10-16)

남는 뿌리(매매법 둘의 패키지 · 실행/차트 스크립트 · 남는 수집 스크립트 · `validate_project.py`)에서 AST 이름 기반으로 따라가
**도달하지 못하고 지울 코드만 참조하던** 공유 정의다. **이름 기반이라 과소 · 과대 집계가 섞일 수 있다** — Phase 2 에서 삭제 뒤 다시 돌려 확인한다.
집계 스크립트는 작업 세션의 스크래치 폴더에 있고 저장소에 넣지 않는다.

| 모듈 | 고아가 되는 정의 |
| --- | --- |
| `measure/distribution.py` | **모듈 전체** — `DistributionShare` · `dividend_adjustment` · `measure_distribution_share` (172줄 · 테스트 `tests/test_measure_distribution.py` 216줄) |
| `data/loader.py` | `load_futures_csv` · `validate_futures_data` |
| `common_constants.py` | `CALENDAR_DAYS_PER_YEAR` · `COL_CONTRACT` · `COL_CONTRACT_NAME` · `COL_OPEN_INTEREST` · `COL_SETTLE` · `COL_SPOT` · `FUTURES_FILE_TEMPLATE` · `FUTURES_REQUIRED_COLUMNS` · `FUTURES_ROW_KEY` |
| `data/constants.py` | `KRX_RESPONSE_DATE_FORMAT` · `SERIES_NOT_FOUND_TEMPLATE` |
| `data/krx_common.py` | `to_numeric` |
| `report/constants.py` | `HORIZON_LABELS` · `DISPLAY_HORIZON` |

### 남는 테스트 중 손댈 곳 — 실측

| 파일 | 무엇 |
| --- | --- |
| `tests/test_layer_contracts.py` | `_REPORT_LABEL_COLLISIONS`(82 ~ 94) · `_KNOWN_LABEL_DUPLICATES`(1760 ~ 1801)의 지운 파일 항목 — **`test_허용목록이_실제_겹침만_담는다` 가 낡은 항목을 잡는다** · `TestKrxCommonOwnership._SHARED_NAMES` 의 `to_numeric` · **`TestHorizonLabelOwnership` 통째로**(구간 이름표를 쓰는 패키지가 `futures_leverage` 하나뿐이라 `assert renamers` 가 깨진다) · 지운 조사를 사례로 든 docstring(403 · 896 · 1074 · 1140 · 1199 · 1631 · 1679 · 1756 등) |
| `tests/test_report_writer.py` | 278 ~ 287 의 `studies.*` import 셋과 `ecos_probe` — `TRACK_NAME`(`leverage_tracking`) · `OTHER_TRACK_NAME`(`futures_leverage`)은 **레지스트리에 남으므로 그대로 둔다** |
| `tests/test_data_loader.py` | 선물 로더 픽스처 · 테스트(약 740 ~ 1072행)와 import |
| `tests/test_krx_common.py` | `to_numeric` 테스트 둘과 import · 모듈 docstring 3행 |
| `tests/test_measure_screening.py:325` · `tests/test_report_tables.py:259` | 지운 조사를 «지금 있는» 사례로 든 docstring |

`test_layer_contracts.py` 의 나머지 계약(`TestStudyOutputFiles` · `TestDisplayLabelLiveness` · `TestStudyPackageComposition` · `TestCredentialsBeforeImport`)은
남는 매매법 둘과 `pykrx_collector` 로 **검사 대상이 남는다**(`OUTPUT_FILES` 는 두 매매법 `constants.py` 에 있다 · pykrx 지연 import 함수는 1개 이상).

### 문서를 합치는 규칙 — 이 계획서가 정한다

선례: `docs/조사/역방향.md`(설계 · 결과 · 규칙 3장 → 한 장, 2026-10-07).

1. **뼈대는 그 조사의 `결과.md`** 다 — 제목 · 머리말 · 「관련 파일」 · 목차 · §1 ~ 측정 장 끝까지 **번호를 그대로** 둔다
2. **`설계.md` 의 장은 순서 그대로 측정 장 뒤 · 「해석」 앞에 넣고, 장 번호만 일정하게 민다**(괴리 +10 · 선물 +11 · 등가성 +11 — Phase 1 에서 확정해
   진행 로그에 대응표를 남긴다). 그 뒤의 「해석」 · 「기각된 가설」 · 「한계」 · 「재현 방법」 · 「원자료」 번호가 밀린다
3. **절 제목은 바꾸지 않는다** — `docs/INDEX.md` 「찾는 것 → 어디」가 제목으로 가리킨다(「데이터 실측 기록」 · 「데이터 실측 기록 — KRX 파생상품 통계」 ·
   「데이터 소스 (확정)」). 결정 번호(①, `C14` 등)도 그대로다
4. **「원문 §N」은 원본 사양서의 절 번호라 옮기지 않는다**(등가성 설계 24개 · 결과 25개). 합친 뒤에도 같은 개수여야 한다
5. 겹치는 자리 — 설계 머리말의 「측정 결과는 결과.md 에 있다」 같은 **서로를 가리키는 문장만** 지운다. 설계 머리말의 나머지(등가성의
   「원본 사양서의 처분」 · 설계 실측 데이터 기간)는 합친 머리말로 옮긴다. 선물 설계 §7 「관련 코드」는 「관련 파일」 표의 묘비 행으로,
   등가성 설계 §6 「재현 방법」은 합친 「재현 방법」의 하위 절로 들어간다
6. **코드를 지우므로 고치는 것** — 「관련 파일」의 코드 행은 묘비 표기(`삭제` · `없음` · `제거` 중 하나, **마크다운 링크 없이** 인라인 코드 — 링크는
   `test_research_docs` 가 실재를 요구한다). 「재현 방법」은 선례 `docs/조사/만기_말일.md` 「재현 방법」 모양으로 **되살리는 절차**(`git checkout 2faa555 -- <경로…>`)
   · 함께 지운 공유 정의 목록 · 되살린 뒤의 실행(지금 `docs/COMMANDS.md` 의 그 조사 절을 옮긴다)을 갖는다. 지운 코드를 «지금 있다»고 말하는 현재형 문장은
   **지우지 않고** 「(2026-10-16 코드 삭제 — 「재현 방법」)」을 붙이거나 그 문장만 과거형으로 바꾼다
7. 상대 링크는 한 단계 얕아진다(괴리 14 · 선물 20 · 등가성 결과 8 · 설계 1 · 연속_등락 2건) · 서로를 가리키던 `[설계.md](설계.md) §N` 은 문서 안의 `§M` 이 된다
8. **연속_등락은 결과 한 장뿐이라 옮기고 링크 둘만 고친다**

### 다른 곳이 가리키는 자리 — 합친 뒤 고칠 포인터 (실측)

| 가리키는 곳 | 대상 | 처리 |
| --- | --- | --- |
| `docs/매매/중간선거_사이클/설계.md:371` | 괴리 **설계 §6.2** | 새 번호로 |
| 중간선거 `규칙.md:36` · `:425` · `결과.md:740` | 괴리 **결과 §8.2** | 경로만(측정 장 번호는 그대로) |
| `docs/조사/역방향.md:94` · `:722` | `연속_등락/결과.md` §2 | 경로만 |
| `docs/조사/월말_진입.md:42` · `:453` · `:480` | 괴리 결과 · 설계 | 경로(절 이름이면 그대로) |
| `docs/조사/원달러_조달.md:12` · `:575` | 등가성 설계 · 결과 | 경로 |
| `docs/조사/원달러_조달.md:17` · `:476` | **`collect_ecos.py` 링크 · COMMANDS 「ECOS」 절** | 묘비 표기 · 되살리는 절차(등가성 「재현 방법」)로 — **링크가 남으면 `test_research_docs` 가 실패한다** |
| `docs/매매/반감기_사이클/사전조사.md:155` | 「저장소에 FRED 수집기가 있다」 | 현재형 표시 |
| `docs/INDEX.md` | 이름표 행 4 + ECOS_실측 행 · 「찾는 것」 4행 · 38행 · 64 ~ 67행 | 새 경로 · 코드 「없음」 |
| `.claude/rules/research.md:15` · `.claude/rules/trading.md:282` · `src/verify_lab/CLAUDE.md:410` | 괴리 결과 | 경로 |
| `scripts/data/collect_pykrx.py:8` | 등가성 설계 · 「수정 종가를 요구하는 조사도 쓴다」 | 주석 — 쓰는 조사가 없어진다 |
| `src/verify_lab/studies/midterm_cycle/constants.py:633` · `:638` | `report/constants.DISPLAY_HORIZON` · 「배수 검증 둘이」 | 주석 — 근거가 사라진다 |

### 폴더형을 전제한 규칙 문장 (실측)

`.claude/rules/docs.md`(배치 블록 · 살아있는 문서 표 · 「승격·강등은 폴더를 옮기는 것」 · 계획서 승격 목적지 표) ·
`.claude/rules/research.md`(10행 · 「파일 네이밍」 · 「한 장짜리는 조사 등급에만」 · 실물 예시 · 「관련 파일」 표의 확정 설계 행) ·
`.claude/rules/session-bootstrap.md`(17 · 30 ~ 32행) · `docs/INDEX.md:38` · `src/verify_lab/tracks.py:60` docstring ·
`src/verify_lab/CLAUDE.md:289` · `:300` · `:301` · 루트 `CLAUDE.md:212` · 디렉토리 구조 아래 등급 설명.

### 지운 조사만 이행하던 계약 — `src/verify_lab/CLAUDE.md` (실측)

처리 기준은 선례(역방향)와 같다 — **「지금 그 계약을 지키는 생산자 · 소비자가 남는가」로 판단해, 남지 않으면 지우고 원문을 그 조사 문서로 옮긴다.**

| 자리 | 처리 |
| --- | --- |
| 「이벤트가 없는 검증의 계약」 절(698 ~ 705) | 생산자 0 → **표를 원문 그대로 `docs/조사/원달러_ETF_등가성.md` 「이벤트가 없는 검증의 계약」 절로 옮기고** 여기는 한 문단 포인터(선례 「이벤트 정의 계약」 660 ~ 665) |
| 152 ~ 153 배수형 어휘 · 167 ~ 170 `TREND_*` · `COL_INTEREST` · 172 ~ 176 동음이의어의 `방향`·`제외` 뜻 | 그 뜻을 쓰던 패키지가 사라진다 → 문장을 고친다 |
| 261 ~ 262 저장 자릿수 예외(ECOS 2자리 · `leverage_drift.csv`) | 생산자 0 → 지운다 |
| 512 「짝마다 나오는 파일」 행 · 517 별칭 사례 | 짝 파일을 내는 검증이 없다 → 행은 지우고 사례는 근거로 남긴다 |
| 531 ~ 534 「국내 세 수집기」 · 「그 지연 import 헬퍼는 셋으로 둡니다」 | 국내 수집기가 하나가 된다 → 고친다 |
| 655 · 656 「범위를 대상 목록으로 말하지 않는 검증」 · `inputs.spot.close` 사례 | 생산자 0 → 지운다 |
| 693 ECOS 비밀값 행 | 생산자 0 → 지운다 |

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- `.claude/plan-config.json` — 이 저장소의 검증 명령·자동 포맷·근거 승격 목적지 (**값의 SoT**)
- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 · 「공통 계층과 개별 매매법의 경계」 · 「재수집은 이미 나온 결과를 바꿉니다」
- `docs/MEMORY.md` — 「이름만 바꾸는 변경과 값을 바꾸는 변경을 한 커밋에 섞지 않는다」
- `src/verify_lab/CLAUDE.md` — 「공유 계층에는 쓰는 곳이 있는 함수만 둡니다」 · 「매매법 이름 계약」 · 데이터 저장 규칙
- `.claude/rules/docs.md` · `.claude/rules/research.md` · `.claude/rules/trading.md` · `.claude/rules/session-bootstrap.md`
- `tests/CLAUDE.md` · 전역 `~/.claude/rules/python.md` · `~/.claude/rules/python-tests.md`
- `scripts/CLAUDE.md`
- 선례: `docs/조사/역방향.md` 「재현 방법」 · `docs/조사/만기_말일.md` 「재현 방법」 · `docs/조사/연속_등락/결과.md` 「재현 방법 — 코드가 제거됐다」

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] 한 장 문서 넷이 필수 구조(`.claude/rules/research.md`)를 갖고, **원문 7장의 줄이 예외 목록 밖에서 전부 그대로** 있다(스크립트 대조)
- [x] 합친 문서 안의 `§` 참조가 전부 실재하는 절을 가리키고, 「원문 §」 개수가 원문과 같다(스크립트 대조)
- [x] `docs/조사/` 아래 폴더가 0개이고, 폴더를 만들면 새 테스트가 실패한다(변형 확인)
- [x] 지울 것 표의 경로가 전부 없고, 삭제 뒤 도달성 집계에서 **새 고아 0건**이다
- [x] 남는 매매법 둘을 다시 돌려 `storage/results/` 의 diff 가 지운 네 폴더뿐이다
- [x] 「재현 방법」의 복원 경로가 `git show 2faa555:<경로>` 로 전부 파일을 낸다
- [x] 저장소(`.git` · `storage` · `docs/plans` 제외)에 지운 경로 · 모듈 · 정의 이름이 남는 곳이 합친 문서의 기록(「재현 방법」 · 설계 결정 · 데이터 실측 기록)과 진행 로그에 적은 (다) 줄뿐이다
- [x] 합친 문서에 `docs.md` · `research.md` · `trading.md` 가 걸린다 — 이 세션에서는 실측 불가라 **근거로 갈음**(2026-10-17 사용자 승인 — 진행 로그). 이어받은 세션에서 실측으로 확인(2026-10-17 22:07 진행 로그)
- [x] 회귀/신규 테스트 정리 (새 테스트 1건 · 지운 조사의 테스트 제거 · 계약 테스트 허용목록 정리)
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — `docs/INDEX.md` 변경 · `docs/COMMANDS.md` 변경 · 루트 `CLAUDE.md` 변경 · `src/verify_lab/CLAUDE.md` 변경 · `scripts/CLAUDE.md` 변경 · `tests/CLAUDE.md` 변경 · `.claude/rules/{docs,research,trading,session-bootstrap}.md` 변경
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다 (사용자 결정 · 합치는 규칙 · 코드를 지운 이유를 규칙 문서와 각 조사 문서 머리말 · 「재현 방법」에 옮겼다)
- [x] 미룬 지적 옮김 — 고치지 않은 리뷰 지적을 거르는 기준으로 걸러 `docs/DEFERRED_FINDINGS.md` 로 옮겼다. 계획서 없이 읽히게 썼다.
      거른 지적은 진행 로그에 기준 번호와 함께 남기고 Done 보고에 표로 냈다
      이 계획서가 그 파일의 항목을 고쳤다면 그 항목을 지웠다
      (둘 다 없으면 「해당 없음」. `/impl-plan` 의 `review.md` 「미룬 지적 옮기기」 참고)
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- **새로 만든다**: `docs/조사/레버리지_ETF_괴리.md` · `docs/조사/선물_대_레버리지_ETF.md` · `docs/조사/원달러_ETF_등가성.md` · `docs/조사/연속_등락.md`
- **지운다**: Context 「지울 것」 표 전부 · `src/verify_lab/measure/distribution.py` · `tests/test_measure_distribution.py`
- **고친다 (코드)**: `src/verify_lab/common_constants.py` · `data/loader.py` · `data/constants.py` · `data/krx_common.py` · `report/constants.py` ·
  `tracks.py`(주석) · `studies/midterm_cycle/constants.py`(주석) · `scripts/data/collect_pykrx.py`(주석) · 그 밖에 Phase 3 grep 이 찾는 주석
- **고친다 (테스트)**: `tests/test_index.py`(새 테스트) · `test_layer_contracts.py` · `test_report_writer.py` · `test_data_loader.py` · `test_krx_common.py` ·
  `test_measure_screening.py`(docstring) · `test_report_tables.py`(docstring)
- **고친다 (문서)**: Context 「다른 곳이 가리키는 자리」 · 「폴더형을 전제한 규칙 문장」 · 「지운 조사만 이행하던 계약」의 문서 전부 ·
  `scripts/CLAUDE.md`(메타 타입 표 8행) · `tests/CLAUDE.md:70`(`ETF_TARGETS` 사례) · 루트 `CLAUDE.md:323`(외부 서버 목록) · `docs/DEFERRED_FINDINGS.md`(예시 이름)
- `docs/COMMANDS.md`: **변경 있음** — ETN · KRX 선물 줄(54 ~ 59) · 「한국은행 — ECOS」 절 · 「미국 금리 — FRED」 절 · 조사 셋 실행 절 셋을 지우고,
  33행 외부 서버 목록 · 50행 「원달러 ETF 등가성이 읽는다」를 고친다. 지운 실행 명령은 각 조사 문서 「재현 방법」의 「되살린 뒤의 실행」으로 옮긴다

### 데이터/결과 영향

- 산출물: `storage/results/조사/` 의 네 폴더가 사라진다. **남는 산출물(매매 둘 · pykrx_ETF_실측)은 바이트 단위로 그대로여야 한다**
- 원시 시세: 변화 없음(전부 남긴다)
- 문서의 수치: 바뀌지 않는다 — 옮기기만 한다. 머리말의 데이터 기간도 원문 그대로다

## 6) 단계별 계획(Phases)

### Phase 0 — 조사 아래 폴더를 막는 테스트 (레드)

**작업 내용**:

- [x] `tests/test_index.py` 에 테스트 하나를 더한다 — Given `docs/조사/` · When 그 안의 폴더를 모은다(`iterdir` · `is_dir` — 이름만, `tests/CLAUDE.md` 「폴더의 «실재만» 보는 검사」) ·
      Then 하나도 없다. **폴더가 실재하는지 먼저 단언**해 경로가 틀려 빈 목록으로 통과하는 것을 막는다. 실패 메시지는 무엇이 잘못됐고(폴더 목록) 무엇을 하는지(`docs/조사/<이름>.md` 한 장으로 합친다 ·
      `.claude/rules/docs.md` 「배치는 «등급» 축이다」)를 한글로 말한다. 모듈 docstring 의 「네 가지를 검사한다」 목록에 더한다

**Validation**:

- [x] `pytest tests/test_index.py` — 새 테스트 하나만 실패하고 실패 메시지에 폴더 넷이 정확히 나온다 (1 failed · 12 passed — `test_survey_grade_has_no_folders` 가 넷을 낸다)

---

### Phase 1 — 한 장 문서 넷 작성 (코드 · 옛 문서는 아직 그대로)

> 문서를 먼저 쓰는 이유: 원문과 코드가 아직 있어 **옮긴 줄과 복원 경로를 그 자리에서 대조**할 수 있다.

**작업 내용**:

- [x] 문서마다 「옛 절 → 새 절」 대응표를 만들고 진행 로그에 남긴다 — 원문 7장의 `§` 를 전부 뽑아(스크립트) 자기 참조 · 짝 문서 참조 · 「원문 §」 · 다른 문서 참조로 가른다
- [x] Context 「문서를 합치는 규칙」 1 ~ 8 대로 넷을 쓴다. 옮기는 줄은 **도구로 복사**한다(눈으로 다시 타이핑하지 않는다)
- [x] 「관련 파일」을 묘비 표기로 · 「재현 방법」을 되살리는 절차로 — 복원 목록에는 패키지 · 실행 스크립트 · 전용 테스트에 더해
      **함께 지우는 수집기와 공유 정의**(Context 표)를 그 조사에 걸리는 만큼 적는다(선물 = KRX 선물 수집기 · 선물 로더 · 선물 상수 · `to_numeric` · `HORIZON_LABELS` · `DISPLAY_HORIZON` ·
      `distribution.py` / 괴리 = ETN 수집기 · `distribution.py` · `to_numeric` / 등가성 = ECOS · FRED 수집기 · ECOS 프로브 · `CALENDAR_DAYS_PER_YEAR` · `SERIES_NOT_FOUND_TEMPLATE` — Phase 1 에서 import 를 따라가 확정한다)
- [x] 머리말에 「성질 조사를 끝내 코드를 지웠다(2026-10-16 사용자 결정) · 수치는 그때의 측정 기록 · 복원 커밋 `2faa555` · 되살리는 절차는 「재현 방법」」을 적는다
      (`scripts/CLAUDE.md` 가 「되살리는 절차는 그 매매법의 조사 문서 머리말에 있다」고 가리킨다)
- [x] `src/verify_lab/CLAUDE.md` 「이벤트가 없는 검증의 계약」 표를 원문 그대로 등가성 문서의 같은 이름 절로 옮긴다(원래 자리는 Phase 3 에서 포인터로)
- [x] `docs/INDEX.md` 이름표 네 행에 새 문서 링크를 **더한다**(옛 링크는 Phase 2 에서 걷는다) — 등록하지 않으면 `test_index` 가 실패한다

**Validation**:

- [x] 무손실 대조(스크립트) — 원문 7장의 빈 줄이 아닌 모든 줄이 새 문서에 그대로 있다. 예외는 줄마다 사유 갈래(머리 포인터 · 상대 링크 · `§` 번호 · 장 번호 · 묘비 · 현재형 표시 · 재현 방법 재작성)를 붙인 목록으로 진행 로그에 남긴다
- [x] `§` 대조(스크립트) — 새 문서 안의 `§` 참조(「원문 §」 · 다른 문서 참조 제외)가 전부 실재하는 장 · 절을 가리키고, 「원문 §」 개수가 49(등가성 24 + 25)다
      (무손실 대조의 예외로 뺀 줄에 있던 것은 사유와 함께 센다)
- [x] 목차 대조(스크립트) — 목차 항목이 실제 `##` 장 제목 · 번호와 하나씩 같다
- [x] 원자료 표 행 수가 원문과 같다(표마다 세어 대조)
- [x] `git show 2faa555:<경로>` 가 「재현 방법」의 복원 경로마다 파일을 낸다
- [x] `pytest tests/test_index.py tests/test_research_docs.py` — Phase 0 테스트만 실패하고 나머지는 통과

---

### Phase 2 — 코드 · 옛 문서 · 산출물 삭제와 공유 계층 정리 (그린 회복)

**작업 내용**:

- [x] 삭제 전 기준점 — `git status --short storage/results/` 가 비어 있다
- [x] Context 「지울 것」 표 전부를 지운다. **같은 Phase 에서 옛 문서 7장 · 폴더 넷을 지우고 INDEX 의 옛 링크를 걷는다** — 옛 결과 문서의
      「관련 파일」이 지울 코드를 가리켜 코드만 지우면 `test_research_docs` 가 깨진다
- [x] 🔴 **옛 문서 경로를 가리키는 포인터(가)도 같은 Phase 에서 바꾼다** — Context 「다른 곳이 가리키는 자리」 표의 문서 줄 전부와 INDEX 「찾는 것」 네 행 ·
      ECOS_실측 행. **테스트가 보는 자리가 섞여 있다** — INDEX 링크(`test_index`) · `월말_진입.md:42` 「관련 파일」 인라인 경로 · `원달러_조달.md:12 · 17`
      「관련 파일」 링크(`test_research_docs`). 미루면 옛 문서를 지운 순간 그린이 깨진다
- [x] 고아 공유 정의(Context 표)와 그 테스트를 지운다 — `distribution.py` · `test_measure_distribution.py` · 선물 로더 테스트 · `to_numeric` 테스트
- [x] `tracks.py` — 조사 셋과 `ecos_probe` 의 **줄은 그대로 두고** 「코드를 지웠다 · 근거와 되살리는 절차는 `docs/조사/<이름>.md`」 주석으로 묶는다
- [x] 남는 테스트 — Context 「남는 테스트 중 손댈 곳」을 한 건씩 처리한다. **허용목록 항목은 「지운 파일만 빠지고 겹침이 남는가」로 가르고**, 판정을 진행 로그에 남긴다
- [x] 도달성 집계를 삭제 뒤 트리에 다시 돌린다
- [x] 남는 매매법 둘을 인자 없이 다시 돌린다 — `run_midterm_cycle.py` · `run_halving_cycle.py`(명령은 `docs/COMMANDS.md`).
      **지운 네 폴더 밖에 diff 가 나오면 멈추고 보고한다** — 값을 바꾸는 변경을 이 계획서에 섞지 않는다(`docs/MEMORY.md`)

**Validation**:

- [x] 도달성 집계 — 삭제 전에 이미 있던 목록(`__all__` · `tracks.KINDS` · `tracks_of_kind` · `distribution` 의 모듈 상수) 밖의 새 고아 0건
- [x] `git diff --stat storage/results/` 가 지운 네 폴더뿐이다
- [x] Phase 0 테스트 그린 · 변형 확인 — `docs/조사/` 아래에 빈 폴더를 만들면 실패하고 지우면 통과한다
- [x] 바뀐 테스트 파일과 `tests/test_index.py` · `test_research_docs.py` · `test_tracks.py` · `test_layer_contracts.py` 를 골라 `pytest` 로 돌려 통과한다(전체 품질 검증은 마지막 Phase)

---

### Phase 3 — 규칙 · 문서 · 주석 정리 (그린 유지)

**참조를 셋으로 가른다**(선례) — (가) 경로 → 새 경로 · (나) 지운 것이 «지금» 있다고 말하는 현재형 → 고치거나 지운다 ·
(다) 지금 구조의 «근거»로 든 사례 → 근거로 남기고 가리키는 곳만 바꾼다

**작업 내용**:

- [x] `.claude/rules/docs.md` — 배치 블록에서 `docs/조사/<이름>/` 을 지우고 「조사는 언제나 한 장 — 폴더를 두지 않는다(2026-10-16 사용자 결정 — 끝난 조사라
      나눠 둘 이유가 없다) · 검사는 `tests/test_index.py`」 · 승격 · 강등 문장을 「검증 ↔ 매매는 폴더 이동, 조사로 내리면 한 장으로 합치고 조사에서 올리면 설계 · 결과로 나눈다」로 ·
      살아있는 문서 표 · 계획서 승격 목적지 표(조사는 그 한 장의 같은 절)
- [x] `.claude/rules/research.md` — 10행 · 「파일 네이밍」 블록 · 「한 장짜리는 조사 등급에만」 → 「조사는 언제나 한 장」 + 합치는 배치(Context 규칙 2 — 설계 장은 측정 장 뒤 · 「해석」 앞) ·
      실물 예시를 폴더형 `docs/매매/반감기_사이클/결과.md` · 한 장 `docs/조사/레버리지_ETF_괴리.md` 로 · 「관련 파일」 표의 확정 설계 행
- [x] `.claude/rules/trading.md:282` · `.claude/rules/session-bootstrap.md`(조사는 한 장 안의 같은 절)
- [x] 루트 `CLAUDE.md` — 212행 · 디렉토리 구조 아래 「문서 폴더와 산출물 폴더가 같은 한글 이름」 · 323행 외부 서버 목록
- [x] `src/verify_lab/CLAUDE.md` — Context 「지운 조사만 이행하던 계약」 표 · 289 · 300 · 301 · 410
- [x] `src/verify_lab/tracks.py:60` docstring · `docs/INDEX.md:38` · `:64 ~ 67`(되살리는 절차 문장에 조사 셋 · ECOS 를 더한다 — 「찾는 것」 네 행 · ECOS_실측 행은 Phase 2 에서 끝냈다)
- [x] `docs/COMMANDS.md` — Scope 의 그 줄
- [x] `scripts/CLAUDE.md` — 메타 타입 표에서 지운 스크립트의 8행(`krx_futures_collect` · `futures_leverage` · `etn_collect` · `leverage_tracking` · `ecos_probe` · `ecos_collect` · `fred_collect` · `usdkrw_equivalence`)
- [x] `tests/CLAUDE.md:70` — 지운 `ETF_TARGETS` 사례를 걷는다(남는 사례 `meta_manager` 는 그대로)
- [x] Context 「다른 곳이 가리키는 자리」 표의 주석(문서 줄은 Phase 2 에서 끝냈다) · `tests/test_layer_contracts.py:151` 「지금 여섯 스크립트는」(개수가 낡는다) ·
      `tests/test_research_docs.py:68 ~ 70` 주석 「한 장형은 문서가 하나뿐인 조사에 쓰이며」(조사는 이제 언제나 한 장)
- [x] `docs/DEFERRED_FINDINGS.md` — `.match` 항목의 예시(실제 이름 수 · 지운 `usdkrw_equivalence` · `run_usdkrw_equivalence.py`)를 지금 이름으로 맞춘다. **판단(무거운 버그)과 처리 여부는 그대로**
- [x] 저장소 grep 으로 남은 참조를 (가)(나)(다)로 가르고 (다)로 남긴 줄은 진행 로그에 적는다

**Validation**:

- [x] grep — 지운 경로(`studies/usdkrw_equivalence` · `studies/leverage_tracking` · `studies/futures_leverage` · `run_usdkrw_equivalence` · `run_leverage_tracking` · `run_futures_leverage` ·
      `ecos_collector` · `ecos_credentials` · `fred_collector` · `etn_collector` · `krx_futures_collector` · `collect_ecos` · `collect_fred` · `collect_etn` · `collect_krx_futures` · `check_ecos` · `measure/distribution` ·
      옛 문서 폴더 경로 넷)와 지운 정의 이름이 DoD 의 예외 밖에서 0건(`.git` · `storage` · `docs/plans` 제외)
- [x] 합친 문서 하나를 `Read` 로 열어 `docs.md` · `research.md` · `trading.md` 가 주입되는지 본다
- [x] `pytest tests/test_index.py tests/test_research_docs.py tests/test_tracks.py` 통과

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

> 🔴 **체크박스와 상태를 먼저 확정하고, `/commit` 은 맨 마지막에** — 이유는 `/impl-plan` 「5) Commit Messages」.

- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` 변경 있음 — Phase 3 에서 반영)
- [x] 자동 포맷 적용 (`poetry run black .`)
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] Validation 절에 `/code-review` 와 품질 검증 **실행 결과**를 적는다
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정
- [x] 🔴 **마지막에 `/commit` 을 실행하고 그 후보를 «이 계획서» 의 `#### Commit Messages` 절에 옮긴다** —
      대화에만 내면 그 절이 빈 채로 남는다. **커밋은 사용자가 한다 — 후보만 낸다**

**Validation**:

> 순서는 `/code-review` → 품질 검증이다. 고칠 것 · 회차 상한 · 수정분 검증은 `/impl-plan` 의 `review.md` 가 정한다.

- [x] `/code-review xhigh` **1회차** (발견 14건 — 버그 3 [무거움 2 · 가벼움 1] · 그 외 11 · 조치: 무거움 2 고침 · 가벼움 1 거름(기준 1 닿지 않음) · 그 외 9 고침(계획서 목표 4 · 전역 주석 규칙 — #8 은 docstring 만) · 그 외 2 미조치(#9 · #10))
- [x] `/code-review xhigh` **2회차** (발견 14건 — 버그 3 [무거움 0 · 가벼움 3 — 지시 셋, 따르면 테스트가 막는다] · 그 외 11 · 조치: 가벼움 3 · 그 외 8 고침 · 미조치 3(R2-4 · R2-5 · R2-13))
- [x] 수정분 검증 **1차** (수정 11건 · 19 hunk · 발견 9건 — 무거움 2 · 조치: 사용자 결정 「다시 고치고 수정분 검증 한 번 더」)
- [x] 수정분 검증 **2차** (수정 9건 + 같은 모양 2자리 · 6 hunk · 발견 8건 — 무거움 0 · 가벼움 3 · 그 외 5 · 조치: 고치지 않음 — 여덟 건 모두 거름 기준 3)
- [x] `poetry run python validate_project.py` (passed=1154, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다** — 추측으로 적은 줄은 그대로 나간다.

1. 검증 / 폴더형 조사 넷의 한 장 통합과 끝난 성질 조사 셋의 코드 삭제
2. 검증 / 조사 문서 한 장 규칙 확정 — 폴더형 넷 무손실 통합 · 조사 아래 폴더를 막는 테스트 추가
3. 검증 / 원달러_ETF_등가성 · 레버리지_ETF_괴리 · 선물_대_레버리지_ETF 의 패키지 · 실행 스크립트 · 전용 수집기(ECOS · FRED · ETN · KRX 선물) · 테스트 · 산출물과 고아 공유 정의 삭제
4. 검증 / 「실질적으로 완료된 조사」 결정에 따른 조사 셋 코드 정리와 되살리는 절차의 조사 문서 이관
5. 검증 / 조사 등급 한 장 전환 — 남은 매매법 산출물 바이트 불변 확인 · 복원 기준 커밋 2faa555 명시

## 7) 리스크(Risks)

- **절 번호를 잘못 옮기면 포인터가 조용히 엉뚱한 절을 가리킨다** — 예외가 나지 않고 이를 잡는 테스트도 없다. 완화: Phase 1 의 대응표 · `§` 대조 스크립트 · 「원문 §」 개수 대조
- **무손실이 깨져도 겉으로 드러나지 않는다** — 완화: 원문 줄 단위 대조 스크립트와 사유가 붙은 예외 목록
- **검사 대상이 사라진 계약 테스트가 빈 채로 통과한다** — 완화: 대상이 사라지는 클래스(`TestHorizonLabelOwnership`)는 지우고, 남는 클래스는 대상이 비면 실패하는 단언(`assert packages` · `checked >= 1` 등)이 있는지 Phase 2 에서 확인한다
- **복원 절차가 깨진다** — 꺼낸 코드가 그 사이 바뀐 공유 계층을 import 할 수 있다(선례 역방향 「재현 방법」 ④). 완화: 복원 경로를 `git show` 로 확인하고, 「재현 방법」에 함께 지운 공유 정의 목록을 적는다
- **고아 집계가 이름 기반이라 놓친다** — 완화: 삭제 뒤 재집계 · Phase 3 grep · 품질 검증(Ruff 미사용 import · PyRight)
- **지운 산출물 폴더가 다음 실행으로 되살아나지 않는다** — 실행 스크립트를 함께 지우므로 생산자가 없다. 반대로 pykrx 프로브를 돌리면 `pykrx_ETF_실측` 이 덮인다 — 이 계획서는 프로브를 돌리지 않는다
- **`.env` 의 `ECOS_API_KEY` 가 쓰는 곳 없이 남는다** — 값을 보지 않고 사용자에게 알린다

## 8) 메모(Notes)

- 사용자 결정 (2026-10-16): ① 조사 아래에 폴더를 두지 않는다 ② 통합은 무손실 · 설계 장은 역방향 선례 배치 · 폴더를 막는 테스트를 둔다(앞 라운드 추천안 승인)
  ③ 조사의 관련 코드를 지운다 — 「실질적으로 완료된 조사들」 ④ 범위는 조사 전용 소스까지(ECOS · FRED · ETN · KRX 선물 수집기 · ECOS 프로브), pykrx 수집기와 pykrx 프로브 둘은 남긴다 ⑤ 시세 파일은 전부 남긴다
- 복원 커밋은 착수 HEAD `2faa555` 다 — 커밋은 사용자가 하므로 삭제 커밋의 해시는 미리 알 수 없다

### 진행 로그 (KST)

- 2026-10-16 08:37: 계획서 작성 (Draft)
- 2026-10-16 08:37: 자체 검증 6회차 — 1회차(누락): 옛 문서 경로 포인터를 Phase 3 → Phase 2 로(테스트가 보는 자리 셋이 섞여 있어 미루면 그린이 깨진다) ·
  `test_layer_contracts.py:151` 개수 docstring · 머리말의 「재현 방법」 포인터. 2회차(검증 수단): 목차 대조 · 예상 밖 diff 에서 멈춤.
  3회차(규칙 문장): `test_research_docs.py:68 ~ 70` 주석. 4 ~ 6회차(과복잡성 · Phase 사이 그린 · 사용자 문구) 개선 없음 — 멈춤
- 2026-10-17 15:13: 사용자 승인 — 착수 (HEAD `2faa555`, 작업 트리는 이 계획서 하나만 untracked)
- 2026-10-17 15:15: Phase 0 완료 — `tests/test_index.py::test_survey_grade_has_no_folders` 레드(폴더 넷), 나머지 12 passed
- 2026-10-17 15:35: Phase 1 완료 — 합본 넷(괴리 907줄 · 선물 976줄 · 등가성 956줄 · 연속_등락 469줄). 원문 줄을 스크립트로 복사하고, 바꾸는 줄은
  「정확히 한 번 맞을 때만 바꾸는」 치환으로만 고쳤다(스크립트는 세션 스크래치 — 저장소에 넣지 않는다).
  **장 대응표** — 괴리: 결과 §1 ~ §10 그대로 · 설계 §1 ~ §6 → §11 ~ §16 · 결과 §11 해석 · §12 한계 · §13 재현 → §17 · §18 · §19 /
  선물: 결과 §1 ~ §11 그대로 · 설계 §1 ~ §6 → §12 ~ §17 · 설계 §7 「관련 코드」 → 「관련 파일」 묘비 행 · 결과 §12 ~ §15 → §18 ~ §21 /
  등가성: 결과 §1 ~ §11 그대로 · 설계 §1 ~ §5 → §12 ~ §16 · 설계 §6 「재현 방법」 → §20 하위 절 · 결과 §12 ~ §15 → §17 ~ §20 / 연속_등락: 그대로(상대 링크 2건만).
  **무손실 대조** — 원문의 비어 있지 않은 줄 중 그대로 없는 줄: 괴리 46/654 · 선물 69/675 · 등가성 69/687 · 연속_등락 1/(링크 줄). 전부 사유 갈래 안이다 —
  장 제목 번호 · 문서 안 `§`/앵커/「N장」 번호 · 「관련 파일」 묘비 · 목차 · 설계 머리(짝 문서 안내 · 「설계가 바뀌면 여기를」) · 재현 방법 재작성 ·
  지운 코드의 현재형 표시(괴리 3 · 선물 1 · 등가성 4). 표 행은 개수 기준으로도 대조했다(줄어든 행이 전부 위 갈래).
  **`§` 대조** — 미해결 0(등가성 6건은 사양서 원문의 절 번호 §2.1 · §6.5 · §6.6 · §16.1 · §16.2 라 그대로가 맞다) · 「원문 §」 49 = 원문 24 + 25 · 목차 문제 0.
  🔴 **스크립트 대조가 하나를 잡았다** — 등가성 결정 C17 행의 「§3.4 의 실측으로 깨졌다」(옛 설계 §3.4 → §14.4)를 치환 목록에서 빠뜨렸다. 설계 장의 `§` 를 전수
  출력해 눈으로 확인한 뒤 고쳤다. 결과 쪽에서 밀린 장(해석 · 기각 · 한계 · 재현)을 가리키던 표기 13곳도 전수 출력해 전부 처리됐음을 확인했다.
  **판단 1 (원문 그대로 둔 번호)** — 괴리 설계 §5 의 「§6 의 수치는 이 규약으로 읽는다」 · 「§6 의 수치는 재실행 없이 유효하다」의 §6 은 **옮기지 않았다.**
  처음 쓰인 커밋 `091af6c` 에서도 설계 §6 은 「데이터 실측 기록」이라 문맥이 맞지 않고, 당시 결과 문서 §6 이 「총 괴리의 크기」(부호 있는 값)였다.
  합본에서도 결과 §6 번호는 그대로라 원문 그대로가 그 뜻을 가리킨다.
  **계획 조정 1** — 지운 실행 명령을 문서로 «옮기지» 않고 선례(`만기_말일.md` 「재현 방법」)처럼 `git show 2faa555:docs/COMMANDS.md` 의 절을 가리켰다.
  명령을 문서에 복제하면 전역 「`docs/COMMANDS.md` 가 있는 저장소 — 실행 명령어는 거기서만 관리한다」와 부딪힌다. 되살릴 정보는 그대로 남는다.
  **계획 조정 2** — 새 문장에 🔴 를 쓰지 않았다(합본 스크립트가 코드 파일이라 이모지 훅에 막혔다 — 우회하지 않고 굵은 글씨만 썼다).
  복원 경로 49개 전부 `git cat-file -e 2faa555:<경로>` 통과. `pytest tests/test_index.py tests/test_research_docs.py` — 1 failed(Phase 0) · 129 passed
- 2026-10-17 15:48: Phase 2 완료 — 「지울 것」 표 전부(패키지 셋 · 실행 셋 · 전용 테스트 14 · 수집기 넷 모듈 다섯 · 그 테스트 다섯 · ECOS 프로브 ·
  `measure/distribution.py` 와 그 테스트 · 산출물 네 폴더 · 옛 문서 7장과 폴더 넷)를 지웠다. 고아 공유 정의: `common_constants` 선물 스키마 여덟 ·
  `FUTURES_FILE_TEMPLATE` · `CALENDAR_DAYS_PER_YEAR`, `data/loader` 의 선물 두 함수(모듈 설명의 「세 스키마」 표를 두 스키마로), `data/constants` 의
  `KRX_RESPONSE_DATE_FORMAT` · `SERIES_NOT_FOUND_TEMPLATE`, `data/krx_common.to_numeric`(과 `__all__`), `report/constants` 의 `HORIZON_LABELS` · `DISPLAY_HORIZON`.
  같은 파일 안에서 지운 것을 근거로 든 주석(나)도 고쳤다 — `NAV_FILE_TEMPLATE`(「검증이 읽는다」) · `DISPLAY_PERIOD` · `DISPLAY_EXCLUDED_REASON`(배수 검증) ·
  `data/constants` · `krx_common` 머리(「세 수집기」).
  🔴 **계획서 표에 없던 테스트 하나** — `tests/test_common_constants.py::test_futures_file_template_uses_product_id`(선물 파일명 검사)가 깨져 지웠고,
  `docs/조사/선물_대_레버리지_ETF.md` §21.1 ② 의 되살릴 목록에 더했다. Context 「남는 테스트 중 손댈 곳」을 만든 grep 패턴이 `FUTURES_FILE_TEMPLATE` 를 안 잡아 놓쳤다.
  **허용목록 판정**(「지운 파일만 빠지고 겹침이 남는가」 — 현재 정의처를 `_display_label_owners` · `_files_defining_value` 로 세어 정했다):
  `_KNOWN_LABEL_DUPLICATES` — `방향`(report · execution) 하나만 남고 열 개(`날짜` · `금리 환경` · `배당 보정분(%p)` · `배수` · `시작일` · `실제(%)` · `종료일` ·
  `종목` · `지수` · `표본`)는 겹침이 사라져 지웠다(`test_허용목록이_실제_겹침만_담는다` 가 잡았다). `_REPORT_LABEL_COLLISIONS` — `날짜`(pykrx_collector) ·
  `방향`(execution) · `제외`(screening) 에서 지운 파일만 빠지고 `표본` 은 비어 지웠다. `TestKrxCommonOwnership._SHARED_NAMES` 에서 `to_numeric` 을 뺐고,
  `TestHorizonLabelOwnership` 은 검사 대상(구간 이름표 · 구간 축을 내는 검증)이 없어져 통째로 지웠다(남기면 `assert renamers` 로 실패).
  남는 클래스는 대상이 비면 실패하는 단언을 이미 갖는다(`assert packages` · `assert scripts` · `checked >= 1` · `assert calls`).
  **docstring (가)(나)(다)** — (나) 고침: `test_layer_contracts.py` 151(「여섯 스크립트」) · 1631(「세 수집기 … 네 번째 수집기」) · 1838(「대부분은 배수형 어휘」) ·
  허용목록 위 주석, `test_krx_common.py` 머리 · `TestExcludeRecent`, `test_measure_screening.py:325`, `test_report_tables.py:259`(과거형). (다) 그대로: `test_layer_contracts.py`
  403(값-사전의 예 `HORIZON_LABELS` · `MODEL_LABELS`) · 896(판정가능 식이 다섯 곳에 «있었다») · 1074 · 1140(옛 사례) · 1199(세 국내 수집기가 값을 «두던») ·
  1679(`etn` · `krx_futures` 가 복사본을 «갖고 있었다») · `TestOutputLabelUniqueness` 클래스 설명(배수 검증의 `windows_*.csv` 사례) — 전부 그 검사가 있는 이유의 기록이다.
  `test_report_writer.py` — `studies.*` import 셋과 프로브 이름 `ecos_probe` 를 지웠다. `TRACK_NAME`(`leverage_tracking`) · `OTHER_TRACK_NAME`(`futures_leverage`)은 레지스트리에 남아 그대로 둔다.
  **(가) 문서 포인터** — INDEX 이름표 다섯 행(코드 「없음」) · 「찾는 것」 네 행, `월말_진입.md` 셋(480 은 「상장 연혁」이라 §13.1 로) · `원달러_조달.md` 다섯
  (17 의 `collect_ecos.py` 링크는 묘비로 · 19 「실행 명령어」는 가리킬 명령이 없어져 「없음」으로 · 476 수집 명령은 되살리는 절차로) · `역방향.md` 둘 ·
  중간선거 결과 · 규칙 셋(괴리 §8.2 — 번호 그대로) · 중간선거 설계(괴리 설계 §6.2 → §16.2) · 반감기 사전조사 155(「FRED 수집기가 있다」 → 있었다).
  도달성 재집계: 새 고아 0(남은 목록은 삭제 전부터 있던 `__all__` 아홉 · `tracks.KINDS` · `tracks_of_kind`). 재실행: `run_midterm_cycle.py` · `run_halving_cycle.py` 둘 다 exit 0,
  `git diff --stat storage/results/` → 51 files changed(지운 네 폴더 3 · 27 · 14 · 7 의 삭제뿐 — 다른 산출물 바이트 불변). 변형 확인: `docs/조사/변형확인_임시/` 를 만들면
  `test_survey_grade_has_no_folders` 1 failed, 지우면 1 passed. `pytest tests/` — 1154 passed
- 2026-10-17 16:13: Phase 3 완료 — 규칙: `docs.md`(배치 블록 · 「조사는 언제나 한 장」 문단 · 승격 · 강등 문장 · 살아있는 문서 표 · `조사/<이름>.md` 역할 한 줄 ·
  「설계와 결과의 분리」의 예외 · 승격 목적지 표 — 과거형 · 게이트 값 예외 표는 「설계.md · 결과.md 규칙은 그 한 장의 설계 장 · 결과 장에 똑같이 걸린다」 한 줄로
  덮어 손대지 않았다), `research.md`(대상 경로 · 실물 예시를 폴더형 `docs/매매/반감기_사이클/결과.md` · 한 장 `docs/조사/레버리지_ETF_괴리.md` 로 · 파일 네이밍 ·
  합치는 배치 · 「관련 파일」 두 행), `trading.md:282`, `session-bootstrap.md`(두 줄), 루트 `CLAUDE.md`(212 · 274 · 323), `src/verify_lab/CLAUDE.md`(Context 표 전부 ·
  289 · 300 · 301 · 410 — 「이벤트가 없는 검증의 계약」은 한 문단 포인터로), `tracks.py` docstring, INDEX(38 · 되살리는 절차 문장), COMMANDS(외부 서버 목록 ·
  ETN · 선물 줄 · ECOS · FRED 절 · 조사 셋 실행 절 · 50행 주석), `scripts/CLAUDE.md` 8행, `tests/CLAUDE.md:70`, `DEFERRED_FINDINGS.md`(예시 이름 · 줄 번호 287 — 판단 그대로).
  주석(나): `collect_pykrx.py:6 ~ 8` · 중간선거 `constants.py` 633 · 640 · `test_research_docs.py:68 ~ 70` · **계획서 표 밖에서 grep 이 찾은 것** —
  `report/run_summary.py` 29(KEY_TRACK 을 둔 이유) · 99(`format_period` 를 `dataset_record` 밖에서 쓰는 곳 → 지금은 반감기_사이클의 대조 계열 요약) ·
  `report/writer.py:190` · `test_layer_contracts.py` 의 `TestDirectionNameOwnership` 설명 · `test_krx_common.py:104` · `만기_말일.md` §13.1 ② 의 배당락 산식 행
  (`measure/distribution.py` 가 «지금 트리에 있는 파일»이 아니게 됐다 → `7521cf5` 에서 통째로 꺼낸다).
  **(다) 그대로 둔 줄** — `test_layer_contracts.py` 103 · 396 · 889 · 1067 · 1133 · 1426 · `TestOutputLabelUniqueness` 설명, `test_report_writer.py:555`(이미 과거형) ·
  389(`ECOS_실측` 은 레지스트리에 남는 이름), `report/writer.py:45`(`원달러_ETF_등가성` 은 레지스트리에 남는 이름), 중간선거 설계 241 · 243 · 385 · `역방향.md:514` ·
  달력 조사 셋의 `dividend_impact` 묘비(2026-10-07 에 지운 것의 기록). **「원본가 파일은 원본가로 잰 조사가 읽는다」**(`src/verify_lab/CLAUDE.md` 231 · COMMANDS 40 ·
  `yfinance_collector.py:9` · `collect_pykrx.py:6`)는 지금 ETF 원본가를 읽는 코드가 없지만 **파일의 역할**을 말하는 문장이라(되살린 코드가 그대로 읽는다) 그대로 뒀다.
  grep: 지운 경로 · 정의 이름이 합친 문서의 기록(관련 파일 묘비 · 설계 결정 · 재현 방법)과 위 (다) 줄 밖에서 0건.
  **계획 조정 3 (사용자 승인 2026-10-17)** — DoD 「합친 문서를 `Read` 로 열면 규칙이 주입된다(실측)」는 이 세션에서 잴 수 없다(세 규칙이 이미 실려 있다 —
  `~/.claude/docs/하네스_동작.md` §1 의 방법은 새 세션이 필요하다). 근거로 갈음했다: ① 공식 문서상 `paths` 는 gitignore 글롭이고 `dir/**` 는 바로 아래 파일을
  잡는다(권한 규칙 표의 `src/**` 가 `src/app.ts` 를 잡는 것과 같은 문법 — Context7 `/websites/code_claude`) ② 같은 깊이에 기존 한 장 조사 문서 여섯이 있다.
  새 세션에서 확인하려면 합친 문서 하나를 `Read` 한 뒤, 파일을 더 열지 말고 `research.md` 에만 있는 값(예: 「묘비 표기로 쓸 수 있는 낱말 셋」)을 묻는다.
  `pytest` 문서 · 계약 6파일 — 247 passed
- 2026-10-17 16:43: 마지막 Phase — `black` 1파일(`data/loader.py` import 묶음). `/code-review xhigh` 1회차(16:16 첫 시도는 세션 한도로 실행 안 됨 · 16:23 재실행) 14건:
  **버그 무거움 #6** 괴리 · 선물의 복원 절차가 `measure/distribution.py` 를 `2faa555` 에서, 만기_말일은 `7521cf5` 에서 꺼내라 해 차례로 따르면 `dividend_impact` 가 덮인다
  (지시 — 쓰이는 동안 닿는다) → 세 문서에 「달력 조사도 되살리면 `7521cf5` 판(상위집합)」을 적었다. 실측: `git diff --numstat 7521cf5 2faa555` — `2faa555` 쪽 추가는 모듈 docstring 5 · 3줄뿐
  (리뷰는 「삭제뿐」이라 했으나 docstring 차이가 있다 — 기능으로 상위집합). **무거움 #5** `src/verify_lab/CLAUDE.md` 가 자릿수 예외를 선물 「재현 방법」으로 가리키는데 그 목록에
  없었다(되살려 다시 돌리면 `leverage_drift.csv` 자릿수가 조용히 바뀐다) → 괴리 · 선물 ② 표에 `src/verify_lab/CLAUDE.md` 행(`TREND_*` · `COL_INTEREST` · 짝 파일 행 · 자릿수 예외 ·
  이벤트가 없는 검증의 계약). **가벼움 #1** `test_accepts_every_real_track_name` 이 레지스트리에 남은 slug(`usdkrw_equivalence` 등)를 안 본다 → **거름 기준 1**: 그 이름을 쓰는
  호출(`create_run_directory`)은 코드를 되살려야만 생긴다(새 호출 코드). 같은 테스트의 `.match` 지적은 이미 `docs/DEFERRED_FINDINGS.md` 에 있다.
  **그 외 고침** #2 산출물 폴더에 원자료가 «있다»(괴리 머리말 · §3 · 선물 §3.3 → git `2faa555` 경로) · #3 연속_등락의 `0746727` 포인터가 이동으로 깨짐(→ 그때 경로
  `docs/조사/연속_등락/결과.md` — `git show` 로 §5.x 실재 확인) · #4 반감기 「연도」 주석 · #7 COMMANDS 50행 · #12 `crypto_common.py:9` · `data/constants.py:22` ·
  `check_pykrx_splice.py:108` · #13 `test_layer_contracts.py` 절 제목 · 「217종」 · #14 `test_index.py` 머리 개수 · #8 의 `TestReportLabelOwnership` docstring ·
  **#11 내가 넣은 코드 주석의 변경 이력**(「…지웠다」 — 전역 「주석은 코드가 못 하는 말만 한다」의 적지 않는 것) — `common_constants` · `data/constants` · `krx_common` ·
  `loader` · `report/constants` 둘 · `run_summary` 둘 · `writer` · 중간선거 · 반감기 상수 · `tracks.py` 둘 · `collect_pykrx.py` · 테스트 docstring 여섯을 현재형 사실과
  「어디 있는가」 포인터로 바꿨다. **그 외 미조치** #8 `방향` 레이블 통합(`execution` 이 `report` 레이블을 가져오게 — 코드 정리, 범위 밖) · #9 `START_DATE_LABEL` · #10
  `NAV_FILE_TEMPLATE` 를 쓰는 파일 상단으로(상수 자리 정리 — 범위 밖, 거름 기준 3). `pytest tests/` — 1154 passed · `black` 무변경
- 2026-10-17 21:34: `/code-review xhigh` 2회차 14건 — **고침 11**: R2-1 `trading.md` 24 · 181 · `docs.md` 역할 목록(조사가 따로 `규칙.md` 를 갖는다고 읽힘) · R2-2 괴리 · 선물 복원 표
  (괴리만 되살리면 `TestHorizonLabelOwnership` · 짝 어휘 허용목록이 테스트를 깬다) · R2-3 세 복원 표에 「범위를 대상 목록으로 말하지 않는 검증」 행 · R2-6 `report/constants`
  「구간」 주석 · R2-7 선물 머리말 표 · R2-8 `src/verify_lab/CLAUDE.md` 과거 서술 일곱 곳 → 현재형 · R2-9 `test_krx_common` 머리 · R2-10 `test_report_tables`(1회차에 「과거형」으로
  적었으나 그때 현재형 예시로 바꿨던 것 — 이번에 예시 없이) · R2-11 `krx_common` 포인터(ETN 은 괴리 문서) · R2-12 `run_summary` 29 · R2-14 `tracks.py` `label` docstring.
  **미조치 3**: R2-4 `방향` 중복(이번 변경 전부터 `execution` 이 허용목록에 있던 같은 뜻 중복 — 통합은 매매법 import 를 바꾸는 리팩터링, 거름 기준 3) · R2-5 이름 검사(1회차 #1 과 같은 판정 —
  거름 기준 1) · R2-13 `KRX_RESPONSE_DATE_FORMAT` 정규식(되살렸을 때를 막는 가드 — (다)). 사본: 세션 스크래치 `r2_before/`(12파일) · diff `r2_fix.diff`(236줄 · 19 hunk).
  **수정분 검증**(맥락 없는 `general-purpose` 서브에이전트 — 수정분과 겨냥한 지적만 줬다) 9건. **무거움 2** — ① 괴리 · 선물 복원 표의 「되살린 runner 는 `datasets` 대신 `inputs` · `pairs` 를 낸다」가
  틀렸다(실측 `git grep 2faa555`: `futures_leverage` 는 둘 다 없음 · `leverage_tracking` 은 `pairs` 만 · `usdkrw_equivalence` 만 `inputs`) ② 괴리 복원 표의 「`TestHorizonLabelOwnership` 은 넣지 않는다 —
  구간 축을 이름표로 내보내는 검증은 선물 하나였다」의 이유가 틀렸다(`leverage_tracking` runner 도 `HORIZON_LABELS` 로 구간 축을 낸다 — 267 · 341 · 385행). 괴리만 되살릴 때도 첫 검사
  (`test_구간_이름표가_한_곳에만_있다` — 괴리의 옛 사본을 지운 `29c31ce` 가 넣은 가드)는 넣어야 하고 둘째 검사만 선물과 함께다. **가벼움 7** — `실제(%)`(괴리 ↔ 등가성 짝 어휘)가 복원 표에 없다 ·
  F5 로 `src/verify_lab/CLAUDE.md` 260 이 자릿수 예외를 다시 현재형으로 적어 등가성 906 · 선물 947 의 「되살릴 것」과 겹친다 · F1 모양 잔여(루트 `CLAUDE.md:23` · `session-bootstrap.md:18` ·
  `trading.md:199` · `docs.md:48 ~ 50` · `writer.py:66` · `test_report_writer.py:56`) · `trading.md:182` 「걸지 않기로 한 규칙과 그 근거」가 역방향(§10.1)과 원달러_그리드(조달 부록)에 맞지 않는다 ·
  F11 모양 잔여(`src/verify_lab/CLAUDE.md:301` · 루트 `CLAUDE.md:273` · `writer.py:66` · `test_report_writer.py:56`) · 「KRX 공통 판정의 소유자」 행의 `to_numeric` 을 되살릴 것에 없음 ·
  선물 25 「(`2faa555` 까지)」가 산출물을 마지막으로 만든 `57ea9a1` 보다 넓다. 그 밖에 이번 변경 전부터 있던 이력 서술 넷(`test_layer_contracts.py` 1673 · 396 · `src/verify_lab/CLAUDE.md` 132 · 587).
  **`review.md` 「지적을 고칠 때」 4 — 수정분 검증의 발견은 고치지 않고, 무거움이 있어 멈추고 사용자에게 고르게 한다**
- 2026-10-17 21:40: **사용자 결정** — 「다시 고치고 수정분 검증 한 번 더」(추천안): 무거움 2 와 내가 새로 쓴 문장의 가벼운 사실 오류(`실제(%)` 짝 · 자릿수 예외 중복 안내 ·
  `trading.md:182` 절 이름 · `to_numeric` 행 · 「`2faa555` 까지」)를 고치고 수정분 검증을 한 번 더 돈다. F1 · F11 모양이 남은 다른 파일과 이번 변경 전부터 있던 이력 서술은 손대지 않고
  미룬 지적으로 옮긴다(사용자가 미루기로 함 — 거르는 기준과 무관). **컨텍스트가 차서 다른 세션에서 이어간다** — 사용자 요청으로 저장소 루트에 인계 문서
  `HANDOFF_survey_single_page.md` 를 두었다(전역 「인계 문서를 두지 않는다」의 예외 — 이어받은 세션이 끝나면 지운다)
- 2026-10-17 22:07: 새 세션에서 이어받았다(인계 문서). **사용자 결정(21:40)대로 다시 고쳤다** — 고치기 전 사본은 세션 스크래치 `r3_before/`(4파일).
  H1 괴리 · 선물 복원 표의 runner 키(실측 `2faa555`: 괴리 `index_filter` · `pair_count` · `horizons` · `pairs` / 선물 `index_filter` · `pair_count` · `skipped_pairs` ·
  `wipeout_window_total` / 등가성 `inputs`) · H1 덧 등가성 §15 원문 행 아래에 「원문 그대로 · 짝이 정확하지 않다」 한 줄(원문은 손대지 않고 경고만 덧붙였다) ·
  H2 괴리 복원 표 — 첫 검사는 함께 넣고 둘째 검사는 선물과 함께(`29c31ce` 가 괴리의 7칸 사본을 지우며 그 클래스를 넣었음을 확인) · H2 덧 선물 같은 행 ·
  L1 `실제(%)` 짝(괴리 · 등가성 두 행) · L2 등가성 · 선물 행의 자릿수 예외 항목을 뺐다 · L3 `trading.md` 「문서 구성」의 절 이름을 INDEX 포인터로 ·
  L4 괴리 · 선물 행에 `to_numeric` 과 「지금은 `pykrx_collector` 하나」 · L5 선물 머리말을 `57ea9a1`(2026-09-16)로(그 산출물에 `1주` · `금리 환경` 이 실린 것을 확인).
  **같은 모양** — 모양: 「② 표가 «되살릴 것»으로 적은 문장이 지금 `src/verify_lab/CLAUDE.md` 에 현재형으로 이미 있다」 → 2자리 더(괴리의 `TREND_*` · 선물의
  `COL_INTEREST` — 지금 166 ~ 170). L1 모양(조사끼리만 겹치는 짝 어휘)은 `2faa555` 허용목록을 전수 대조해 배수형 여섯과 `실제(%)` 뿐 — 더 없음. H1 · H2 · L5 모양은
  grep 으로 고친 자리 밖 0. 수정분 diff `r3_fix.diff`(72줄 · 6 hunk). `pytest tests/test_index.py tests/test_research_docs.py` — 102 passed.
  **수정분 검증 2차**(맥락 없는 `general-purpose` — 수정분과 겨냥한 지적만 줬다) 발견 8건 — 무거움 0 · 가벼움 3 · 그 외 5. 새 문장의 사실 주장은 전부
  `2faa555` · 지금 트리와 맞다고 확인됐다. 무거움이 없어 멈추지 않았고, 발견은 `review.md` 「지적을 고칠 때」 4 대로 고치지 않았다.
  가벼움 3 — ⓐ L2 로 뺀 항목이 가리키던 `src/verify_lab/CLAUDE.md` 의 「지금 코드가 없다」 문장(153 · 170 · 173 · 260 ~ 262)을 되살린 뒤 고치라는 안내가 사라졌다
  (L4 는 같은 모양인 「지금은 `pykrx_collector` 하나」를 고칠 것으로 넣어 두 처리가 어긋난다) ⓑ L5 모양이 괴리 머리말 15 에 남았다(「마지막 산출물은 … 2026-09-06 에
  다시 돌린 것」 — 실측: 그 폴더 파일의 마지막 변경은 `57ea9a1` · `full_period.csv` 만 `9c224e3`) ⓒ 복원 표가 「범위를 「대상 목록」으로…」 원문 행을 되살리라고만 해
  부정확한 원문이 그대로 돌아갈 수 있다. 그 외 5 — `tests/test_layer_contracts.py:1626` docstring 「지금은 `pykrx_collector` 하나」 · 복원 표의 `tests/test_report_writer.py`
  행이 `names` 리스트를 빠뜨렸다(import 만 넣으면 Ruff 미사용 import 로 막힌다) · `src/verify_lab/CLAUDE.md:262` 가 가리키는 선물 §21 에 자릿수 언급이 없고 `ECOS_SERIES`
  포인터도 빠졌다 · 선물 25 의 「재실행」은 git 으로 보이지 않는다(`57ea9a1` 은 R100 이름 이동) · `trading.md` 「구성은 셋 다 같습니다」가 원달러_그리드 부록과 다르다.
  **거름**(`review.md` 「미룬 지적 옮기기」) — 여덟 건 모두 기준 3(버그가 아니다). 가벼움 셋은 검증 에이전트에게 «따르는 지시의 결함»을 가벼움으로 주어 그렇게 나왔다 —
  `review.md` 정의(지시는 따르면 무거운 결과가 나는 것만 버그)로는 따라도 문서 문장이 낡거나 원문의 부정확한 행이 돌아올 뿐이라 「그 외」다(검증 ③: 위험한 쪽으로 바뀐 것 없음 ·
  산출물 자릿수는 ① 에서 파일을 통째로 꺼내 그대로 보존된다). `test_report_writer` 행은 기준 2(막는 쪽)이기도 하다.
  **미룬 지적 옮김** — 사용자가 미루기로 한 셋을 `docs/DEFERRED_FINDINGS.md` 에 옮겼다: F1 모양(`docs/<등급>/<매매법>/…` 일반 표기 여섯 자리 — `trading.md` 는 L3 로
  199 → 200) · F11 모양(「같은 한글 이름」 일반화 두 자리) · 이력 서술 넷. 옮기기 전에 자리를 지금 트리에서 다시 확인했다. 앞 회차에서 거른 지적은 16:43 · 21:34 줄에 있다.
  **DoD 재확인** — `docs/조사` 아래 폴더 0 · 지울 것 표 경로 전부 없음 · `storage/results/` diff 51 D(3 · 27 · 14 · 7 — 네 폴더 밖 0) · 「재현 방법」 복원 경로 71개
  (괴리 21 · 선물 26 · 등가성 24) 전부 `git cat-file -e 2faa555:` 통과 · 지운 이름 grep 이 기록 · (다) 줄 · 리뷰가 넣은 포인터(`krx_common.py:5`) · pandas `pd.to_numeric` 밖 0.
  **결정 6 의 실측** — 이 세션에서 `docs/조사/레버리지_ETF_괴리.md` 를 `Read` 하자 `research.md` · `trading.md` 가 주입됐다(`docs.md` 는 같은 `docs/**` 로 `docs/INDEX.md` 를
  열 때 이미 실렸다) — `docs/조사/**` 가 폴더 바로 아래 한 장을 잡는다. `black` 110파일 무변경 · `validate_project.py` passed=1154 · failed=0 · skipped=0
