# INDEX — 문서 지도

> 이 저장소에 무엇이 어디 있고 언제 읽어야 하는지의 **단일 지도**입니다.
> 자동으로 로드되지 않는 문서를 찾을 때 여기를 봅니다.
>
> **문서를 추가·삭제·이동하면 이 파일을 함께 고칩니다.**
> `tests/test_index.py`가 실제 파일 목록과 대조해 검사하므로, 안 고치면 `validate_project.py`가 실패합니다.

---

## 1. 처음 온 세션이 읽을 순서

**진입 순서 자체는 [../.claude/rules/session-bootstrap.md](../.claude/rules/session-bootstrap.md) 가 정합니다.**
그 규칙은 `paths` 가 없어 **매 세션 자동 로드**되며, 첫 작업 전에 이 지도를 열도록 지시합니다.

| 순서 | 문서 | 왜 |
| --- | --- | --- |
| 1 | [../CLAUDE.md](../CLAUDE.md) | 프로젝트 규칙. 측정의 원칙과 후보 판정 기준 |
| 2 | [context/README.md](context/README.md) | **사용자의 현재 운용 상태와 이 프로젝트가 시작된 이유. 가장 중요** |
| 3 | 작업 대상의 `spec/` · `research/` · `strategy/` | 아래 3절에서 고릅니다 |
| 4 | [../src/verify_lab/CLAUDE.md](../src/verify_lab/CLAUDE.md) | 계층 구조, 측정 계층의 절대 원칙, **계층 간 계약** |

**전부 읽지 않습니다.** 하네스 설정·문서 정리·단순 질의응답이면 1·2 에서 멈춥니다.

> **진행 상태 문서와 인계 문서를 두지 않습니다.** 무엇이 끝났는지는 git 이력과 결과 문서가 말하고,
> 무엇을 다음에 할지는 그때 사용자가 정합니다. `tests/test_index.py` 가 이 규칙을 집행합니다.

---

## 2. 규칙 문서

| 문서 | 내용 | 로드 방식 |
| --- | --- | --- |
| [../CLAUDE.md](../CLAUDE.md) | 프로젝트 전반 규칙, 측정의 원칙, 사고 절차, 수술적 변경 | **항상 자동** |
| [../src/verify_lab/CLAUDE.md](../src/verify_lab/CLAUDE.md) | 계층 분리, 상수 관리 3계층, 핵심 패턴, 절대 원칙 | `src/verify_lab/` 작업 시 자동 |
| [../scripts/CLAUDE.md](../scripts/CLAUDE.md) | CLI 계층 책임, 예외 처리, 명령행 인자 정책 | `scripts/` 작업 시 자동 |
| [../tests/CLAUDE.md](../tests/CLAUDE.md) | 필수 테스트, Given-When-Then, 부동소수점 비교, 파일 격리 | `tests/` 작업 시 자동 |
| [../.claude/rules/research.md](../.claude/rules/research.md) | 결과 문서 작성 규칙 | `docs/research/**` Read 시점에 자동 |
| `~/.claude/rules/python.md` **(전역)** | 코딩 표준, 반올림 규칙, 로깅 정책 — 저장소 밖이라 링크하지 않습니다 | `**/*.py` **Read 시점**에 자동 (실측 확인) |
| [../.claude/rules/docs.md](../.claude/rules/docs.md) | 문서 종류와 SoT 역할, 계획서 수명 | `docs/**` **Read 시점**에 자동 (실측 확인) |
| [../.claude/rules/reference.md](../.claude/rules/reference.md) | reference 폴더 읽기 전용 4금지 | `reference/**` Read 시점에 자동 |
| [../.claude/rules/context.md](../.claude/rules/context.md) | 사용자 소유 문서 보호, 해석 시 붙잡을 맥락 | `docs/context/**` Read 시점에 자동 |
| [../.claude/rules/strategy.md](../.claude/rules/strategy.md) | **매매 규칙 계층의 예외 규정** — 이 폴더에서만 손절·기간 설계가 허용되는 이유와 제약 | `docs/strategy/**`·`src/verify_lab/strategy/**`·`scripts/strategy/**` Read 시점에 자동 |
| [../.claude/skills/clean-results/SKILL.md](../.claude/skills/clean-results/SKILL.md) | **검증 산출물 정리 절차** — 조준 확인 → 목록 → 승인 → 삭제. 인용 판정은 `src/verify_lab/utils/result_citations.py` 가 소유하고 품질 검증이 같은 함수를 씁니다 | `/clean-results` 스킬 호출 |
| [../.claude/skills/claude-config-export/SKILL.md](../.claude/skills/claude-config-export/SKILL.md) | **전역 Claude 설정 내보내기** — `~/.claude` 와 `~/.claude.json` 에서 옮길 것만 골라 `claude-config/` 에 사본을 만듭니다. **자격증명은 담지 않으며** 그 이유가 문서에 있습니다 | `/claude-config-export` 스킬 호출 |
| [../.claude/skills/claude-config-import/SKILL.md](../.claude/skills/claude-config-import/SKILL.md) | **받는 PC 에서 적용** — 그대로 적용 / 경로 변환 후 적용 / 승인 후 제외로 나눠 판정하고, 결정을 PC 별로 누적합니다. **훅을 자동 판정하지 않는 이유**가 문서에 있습니다 | `/claude-config-import` 스킬 호출 |
| `~/.claude/skills/impl-plan/SKILL.md` **(전역)** | 계획서 작성 절차 (SoT) — 저장소 밖이라 링크하지 않습니다 | `/impl-plan` 스킬 호출 |
| [MEMORY.md](MEMORY.md) | **작업하며 알아낸 것** — 함정·도메인 사실·인계사항·작업 규율·환경 노하우. 하네스 메모리가 이 저장소에서 차단돼 있어(전역 훅) 새 사실은 여기 적습니다 | **항상 자동** (`CLAUDE.md` 가 `@import`) |

> **자동 로드는 편집이 아니라 읽기에서 걸립니다.** 기존 파일을 Read 하면 해당 경로의 규칙이 함께 들어옵니다.
> 따라서 **기존 파일을 열지 않고 새 파일부터 만드는 경우**에만 규칙 문서를 직접 열면 됩니다.
> 실측 근거는 [../.claude/rules/session-bootstrap.md](../.claude/rules/session-bootstrap.md) 4절에 있습니다.

---

## 3. 설계·맥락 문서

### 매매법 이름표 — 한글 이름 ↔ 코드 slug ↔ 계층

**매매법 하나는 어디서든 같은 이름으로 불립니다.** 코드는 영문 slug, 문서는 한글이며
**이 표가 그 다리입니다.** 계층은 이름이 아니라 **자리**가 말합니다 — 코드는 폴더
(`studies/` 대 `strategy/`), 산출물은 상위 폴더(`검증`·`매매`), 문서는 접미사(`_설계`·`_매매_규칙`)입니다.

| 한글 이름 | slug | 측정 코드 | 매매 코드 | 설계 | 결과 | 매매 규칙 |
| --- | --- | --- | --- | --- | --- | --- |
| **역방향** | `reverse` | `studies/reverse/` | `strategy/reverse_runner.py` | [spec/역방향_설계.md](spec/역방향_설계.md) | [research/역방향.md](research/역방향.md) | [strategy/역방향_매매_규칙.md](strategy/역방향_매매_규칙.md) |
| **옵션 만기일** | `option_expiry` | `studies/option_expiry/` | `strategy/option_expiry_runner.py` | [spec/옵션_만기일_설계.md](spec/옵션_만기일_설계.md) | [research/옵션_만기일.md](research/옵션_만기일.md) | [strategy/옵션_만기일_매매_규칙.md](strategy/옵션_만기일_매매_규칙.md) |
| **월말 진입** | `month_end` | `studies/month_end/` | `strategy/month_end_runner.py` | [spec/월말_진입_설계.md](spec/월말_진입_설계.md) | [research/월말_진입.md](research/월말_진입.md) | [strategy/월말_진입_매매_규칙.md](strategy/월말_진입_매매_규칙.md) |
| 원달러 ETF 등가성 | `usdkrw_equivalence` | `studies/usdkrw_equivalence/` | — | (없음) | [research/원달러_ETF_등가성.md](research/원달러_ETF_등가성.md) | — |
| 레버리지 ETF 괴리 | `leverage_tracking` | `studies/leverage_tracking/` | — | [spec/레버리지_ETF_괴리_설계.md](spec/레버리지_ETF_괴리_설계.md) | [research/레버리지_ETF_괴리.md](research/레버리지_ETF_괴리.md) | — |
| 선물 대 레버리지 ETF | `futures_leverage` | `studies/futures_leverage/` | — | [spec/선물_대_레버리지_ETF_설계.md](spec/선물_대_레버리지_ETF_설계.md) | [research/선물_대_레버리지_ETF.md](research/선물_대_레버리지_ETF.md) | — |
| 원달러 그리드 | `usdkrw_grid` | **없음** (제거됨) | — | [spec/원달러_그리드_설계.md](spec/원달러_그리드_설계.md) | [research/달러_조달_방식.md](research/달러_조달_방식.md) | [strategy/원달러_그리드.md](strategy/원달러_그리드.md) |

- **slug 의 정의처는 `studies/<slug>/constants.py` 의 `TRACK_NAME` 하나**입니다. 측정과 매매가
  같은 값을 보므로 산출물 폴더 이름이 계층마다 갈리지 않습니다
- **매매 계층은 매매법마다 `<slug>_runner.py` 하나**입니다. 체결 판정식(`strategy/trade_fill.py`)과
  구간별 성적 산식(`strategy/periods.py`)은 **매매법 이름을 갖지 않는 공유 모듈**이 소유하며,
  매매법 모듈끼리 서로를 import 하지 않는 것을 `tests/test_layer_contracts.py` 가 검사합니다
- **스크립트는 `run_<slug>_study.py` / `run_<slug>_trading.py`** 입니다. 폴더가 계층을 말하지만
  `⌘P` 로 파일을 열 때는 폴더가 보이지 않아 파일명이 단독 식별자가 됩니다
- **`usdkrw_grid` 는 실행 코드가 없습니다.** 채택되지 않아 측정 구현을 지웠고, 문서만 근거로 남습니다
- **`docs/spec/` 에 `_설계` 를 붙인 이유**: 붙이지 않으면 `docs/spec/역방향.md` 와
  `docs/research/역방향.md` 처럼 **폴더만 다르고 이름이 같은 파일이 6쌍** 생깁니다. 스크립트에
  `_study`/`_trading` 접미사를 붙인 것과 같은 이유이며 — `⌘P` 로 파일을 열 때는 폴더가 보이지 않아
  같은 이름 둘 중 어느 것인지 매번 경로를 확인해야 합니다
- **폴더 이름이 대상 범위를 말하지 않습니다.** 같은 slug 를 측정과 매매가 공유하므로 범위가
  갈릴 수 있습니다 — **월말은 검증 8대상(코스피·코스닥)이지만 매매는 코스닥 4대상뿐**입니다.
  범위의 SoT 는 산출물의 `summary.json` 의 `datasets` 입니다

| 문서 | 내용 | 언제 |
| --- | --- | --- |
| [context/README.md](context/README.md) | 두 운용 문서의 안내와 핵심 결론 | 항상 |
| [context/RESEARCH_q2_2xs_qqq_correlation.md](context/RESEARCH_q2_2xs_qqq_correlation.md) | 운용 포트폴리오의 QQQ 상관 분해. **이 프로젝트의 출발점** | 검증 결과를 해석할 때 |
| [context/RESEARCH_qqq_late_entry.md](context/RESEARCH_qqq_late_entry.md) | 현재 보유 판정(이번 사이클 미진입)과 근거 | 같음 |
| [spec/역방향_설계.md](spec/역방향_설계.md) | 검증 #1 확정 설계, 확정된 설계 결정, 사전 실측 기록 | 검증 #1 관련 전부 |
| [spec/원달러_그리드_설계.md](spec/원달러_그리드_설계.md) | **원달러 그리드 트랙의 SoT** — 데이터 실측 기록(ECOS/FRED 코드, ETF, 매매기준율 시차, 동적 범위, 슬롯 상한, 환전 비용, 그리드 엔진 실행 — 비용 없음·거래비용·이자·ETF 경로·하단 이탈 B안·지표 계층·벤치마크·견고성 검사)과 확정된 설계 결정 | 원달러 그리드·검증 #5 관련 전부. **§4 가 원본 사양서를 이긴다** |
| [spec/원달러_그리드_사양서.md](spec/원달러_그리드_사양서.md) | 원달러 그리드 **매매 규칙의 원본 사양서** (사용자 작성). **일부 규정이 실측으로 바뀌었으므로 위 spec 의 §4 가 SoT** | 그리드 규칙 본문(격자·범위·자금배분·체결·비용·지표)을 볼 때 |
| [spec/레버리지_ETF_괴리_설계.md](spec/레버리지_ETF_괴리_설계.md) | **검증 #8 확정 설계** — 괴리를 「경로 효과 + 상품 비용」으로 나누는 산식, 측정 대상의 선정 근거(거래대금·상장일·기초지수·총보수), 확정된 설계 결정, 데이터 실측 기록(**ETN 시세를 KRX `MDCSTAT06601` 로 직접 받는 법**·yfinance 분할 조정·비중첩 표본·251340 상장일) | 검증 #8 관련 전부. **ETN 시세가 필요할 때 §6.1** |
| [spec/선물_대_레버리지_ETF_설계.md](spec/선물_대_레버리지_ETF_설계.md) | **검증 #9 확정 설계** — 세 방식(ETF·선물 매일·선물 월1회) 비교와 차이 분해 산식, 확정된 설계 결정, 데이터 실측 기록(**국내 선물 계약별 시세를 KRX `MDCSTAT12601` 로 받는 법**·거를 것·상장 첫날·거래승수 역산·만기일 유도·전용 로더가 필요한 이유) | 검증 #9 관련 전부. **국내 선물 시세가 필요할 때 §5.2, 함정은 §5.3** |
| [spec/옵션_만기일_설계.md](spec/옵션_만기일_설계.md) | **검증 #7 확정 설계** — 만기일 달력 규칙(미국 셋째 금요일·한국 둘째 목요일)과 휴장 앞당김, 상대 거래일(offset) 정의, **달력 기준 청산(만기일 매수 → 다음주 금요일 매도)**, 가격 기준 결정, 확정된 설계 결정, 데이터 실측 기록(만기 달력·QQQ 배당락·재수집·pykrx 수정주가 창·KODEX 분배락·만기일 요일 분포·DIA 수집·휴장 규칙 대조·9월) | 옵션 만기일 검증 관련 전부 |
| [spec/월말_진입_설계.md](spec/월말_진입_설계.md) | **검증 #10 확정 설계** — 월 하순 진입(20일 매수 → 말일 매도), **코스피·코스닥 8대상**. 진입일 앞당김과 말일 기준 상대 거래일 청산, 진입 11칸 × 청산 7칸 격자, **집행 축**(「아래」는 인버스 실물로 잰다), 확정된 설계 결정, 데이터 실측 기록(**데이터 마지막 달이 가짜 표본을 만드는 함정**·격자 극단 칸의 표본 불균등·보유 거래일 분포·**네 지수의 조회 구간과 소급 산출 0값**) | 검증 #10 관련 전부. **부분 월 함정은 §7.1**, 코스피 지수 실측은 **§7.11** |
| [research/원달러_ETF_등가성.md](research/원달러_ETF_등가성.md) | **검증 #5 결과** — 261240 이 「환전 + 달러 예치」의 대체재인가. 판정은 조건부 가능 | 원달러 그리드의 ETF 경로를 다룰 때 |
| [research/옵션_만기일.md](research/옵션_만기일.md) | **검증 #7 결과** — 만기 앞뒤 상대 거래일 -10~+10 의 수익률과 **「만기일 매수 → 다음주 금요일 매도」 매매**(§11), **만기월별 통계**(§12). 판정은 **우위 없음**(유의 칸 24개 대 우연 기대치 21.0개). **유일한 예외는 미국 9월** — 같은 달 대비 -0.91~-0.97%p 이지만 다중 비교를 넘지 못한다(§12.3). 베이스라인·가격 기준 선택이 결론을 바꾼 기록이 §8·§14 | 옵션 만기일 결과를 인용하거나 재실행할 때. **만기일 요일 분포**(§3.4)를 확인할 때 |
| [research/역방향.md](research/역방향.md) | **검증 #1 결과** — 역대급 등락 이후 수익률 측정과 판정. **후보 판정(1차 게이트·등급)은 이 검증의 산출물에 없다** — `screen_candidates` 를 부르지 않으므로 그 수치는 재현되지 않는다. 판정을 붙이려면 별도 계획서가 필요하다 | 검증 #1 결과를 인용하거나 재실행할 때 |
| [research/연속_등락.md](research/연속_등락.md) | **참고용 보존 문서** — N일 연속 상승·하락 이후 수익률. **우연과 구별되지 않아 측정 코드를 제거**했고, 이 문서가 그 측정의 유일한 기록이다. 재실행 불가(§8 에 git 복원 절차) | 같은 가설을 다시 세우기 전에. **역대급 등락을 볼 때는 읽지 않아도 된다** |
| [research/달러_조달_방식.md](research/달러_조달_방식.md) | **검증 #6 결과** — 미국주식 매수 자금용 달러를 어떻게 사서 보유할 것인가. 그리드·밴드 리밸런싱·분할 진입·백분위를 전부 재서 **"매매 규칙을 얹지 않는다"** 로 결론 | 달러 조달·보유 방식을 다시 논의할 때. **그리드를 왜 안 쓰는지의 근거** |
| [research/레버리지_ETF_괴리.md](research/레버리지_ETF_괴리.md) | **검증 #8 결과** — 배수 상품이 1배 대비 얼마나 벌어지는가. 22쌍 × 보유 기간 7격자. **1~2주는 명목 배수대로 움직이고**(총 괴리 −0.22%p 안쪽), **인버스는 오래 들수록 배수가 녹는다**(3년 실현 배수 −3배 → −1.45). 괴리를 경로 효과와 상품 비용으로 분해했다. **§8.2 는 경로 효과가 U자를 그리는 것**을 보인다 — **「보통의 해」(완만한 상승)가 가장 불리**하고 큰 추세 양끝은 오히려 낫다 | **기존 검증 결과를 2~3배로 옮겨 읽기 전에.** 인버스로 집행하는 설계를 세울 때 |
| [research/선물_대_레버리지_ETF.md](research/선물_대_레버리지_ETF.md) | **검증 #9 결과** — 같은 배수를 선물로 굴리는 것과 ETF 를 사는 것 중 어느 쪽이 싼가. 6쌍 × 7격자 × **4방식**(ETF · 선물 매일 · 월 1회 · **그대로 두기**). **매일 되돌리면 코스피200 2배는 1년까지 ETF 와 0.05%p 차이**이고, 되돌리지 않으면 **평균과 중앙값의 답이 반대로** 갈린다(§7). 정수 계약 제약으로 **자기자본 1억은 2배가 아니라 2.575배**(§10) | 선물로 배수를 만들지 고민할 때. **리밸런싱 주기가 결과를 만드는 크기**를 볼 때 |
| [research/월말_진입.md](research/월말_진입.md) | **검증 #10 결과** — 「20일 매수 → 말일 매도」에 통계적 우위가 있는가, **코스피·코스닥 8대상**. 판정은 **두 시장 모두 우위 없음**(1차 게이트를 하나도 못 넘는다). **20일이라는 날짜에도 실체가 없다** — 두 시장 다 15~22일이 비슷하고 23일부터 뒤집힌다(§6). 격자 616칸의 유의 칸 18개가 우연 기대치 30.8개에 못 미치고, **월별 96칸에서 우연확률 0.05 미만이 0칸**이다(§7.4). **9월만 여덟 대상 전부 「아래」**(§7.1), **12월은 두 시장 모두 긴 축에서 무너지며**(§7.2), **4·6월은 코스닥에만·11월은 코스피에만 있다**(§7.3). 실제 매매 수치는 `execution.csv` 가 담는다(§9) | 월말 매매를 다시 검토하거나 그 수치를 인용할 때. **시장을 바꾸면 사라지는 달은 §7.3**, 분배락 크기는 **§10** |
| [strategy/원달러_백분위_알림.md](strategy/원달러_백분위_알림.md) | **채택한 규칙** — 기계적 시간 분할 매수(§1.1)와 백분위 알림 규격(§1.2·§1.3). 창 4개(1·3·5·10년), 판정 어휘 없음 | **백분위 알림을 구현할 때 볼 문서.** 규격과 문구 형식이 여기 있다 |
| [strategy/원달러_그리드.md](strategy/원달러_그리드.md) | **원달러 그리드의 규칙과 성적** — 확정 규칙(§1)·성적(§2)·결정 근거(§3)·한계(§4)·체결 원자료(§5). **채택되지 않았다**(§2.8) — 급등장에 달러가 0이 되어 사용자 목적과 충돌한다. 성적은 **왜 안 쓰는지의 근거**로 보존 | 그리드를 다시 검토하거나 그 성적을 인용할 때 |
| [strategy/옵션_만기일_매매_규칙.md](strategy/옵션_만기일_매매_규칙.md) | **옵션 만기일 매매의 SoT** — 확정 규칙(§1)·구간별 성적(§2)·결정 근거(§3)·한계(§4)·원자료(§5). **4칸**(9월 둘·12월 둘, **전부 미국 ETF**), 손절 −5%, **알림 없음(직접 챙김)**. 제외한 칸이 둘이고 근거가 다르다 — **QQQ 두 칸은 배당락이 보유 구간에 걸려**(§3.2·§3.4, 데이터 오염), **KODEX 200 9월은 근거가 약해**(§3.2, 손익비 0.788 · t=1.16 · 최악 1건이 22년 성과의 33%) 뺐다. §2 의 성적표는 KODEX 를 포함한 5칸 기준이며 **측정 기록으로 남겨 둔 것**이다 | **9월·12월에 매매하기 전에 §1 만 읽으면 된다.** 2026년 실행 날짜는 §1.6. **손절선 격자 전체는 §3.1.** 국내 칸을 다시 넣으려면 §1.4 의 릴레이 근거를 본다 |
| [strategy/월말_진입_매매_규칙.md](strategy/월말_진입_매매_규칙.md) | **코스닥 월말 매매의 손절 격자** — 20일 매수 → 말일 매도에 손절선 −3~−10%(1%p 간격)와 무손절을 걸어 12개월 × 두 방향으로 냈다. **후보 4달에서 −5% 이상이면 손절이 거의 걸리지 않아 무손절과 성적이 같고**(6·9·12월 0건), **−3%는 반등 구간을 끊어 6월 −8.19%p·12월 −10.77%p 를 깎는다**(§2.1·§3①). 손절이 최악을 **악화시킬 수 있다는 실측**은 §3②. 사용자 확정 전이라 §1 은 권고안이다 | 손절선을 정하거나 그 근거를 인용할 때. **12개월 전체에서 손절이 무엇을 했는지는 §2.4** |
| [strategy/역방향_매매_규칙.md](strategy/역방향_매매_규칙.md) | **현재 운용 중인 매매 규칙의 SoT** — 확정 규칙(§1)·성적·결정 근거·신호일 원자료. 측정이 아니라 측정 결과로부터 도출한 규칙이다 | **"확정된 매매법만 참고하라"의 지시 대상은 §1** |
| [strategy/투자금_결정.md](strategy/투자금_결정.md) | **「얼마 넣는가」의 SoT — 매매법에 종속되지 않는다.** 계산식(§1)·검증(§2)·결정 근거(§3)·한계(§4)·재현 절차(§5). **세 단계다** — 게이트(승률 60%·평균 0 초과, 구간에도 건다 §1.8) → `노출 = 켈리분수 × 평균 ÷ 표준편차²` → 배수로 나눠 매수. **판정 축은 계좌 낙폭이 아니라 «회당 최악 1건»** 이다(§3.1) — 시장 노출이 연 7.6% 라 이벤트형에 곡선 지표를 붙이지 않는다. **최대 손실은 금액이 아니라 「원금의 10%」** 라 노출 상한 식에서 원금이 약분된다(§1.5). **켈리분수 1/20 은 고정**이며 세 가지로 같이 읽힌다 — 회당 최악 5.44% · 최대 성장의 9.75% · 「우위가 진짜일 확률 21%」(§1.3·§3.1). **1배 집행은 금지**다(손익분기 확률 52.3%, §3.8). 승률·손익비·「평균−표준편차」·표본 수·최악 1건·손절폭·변동성 천장을 **크기 결정에서 뺀 이유**가 §3.3~§3.12 에 있고, **다른 사이징 방식을 416칸으로 떨어뜨린 기록과 웹 출처**가 §2.3 에 있다 | **새 매매법의 투자금을 정할 때 §1 만 읽으면 된다.** 계산기 시트는 §1.9. **켈리분수를 바꾸려 할 때는 §2.2 조견표**, **구간 게이트와 확인 플래그는 §1.8**, **KODEX 200 9월을 뺀 근거는 §2.4** |
| [COMMANDS.md](COMMANDS.md) | 실행 명령어 단일 SoT | 스크립트 만들거나 실행할 때 |
| [../README.md](../README.md) | 프로젝트 소개 (사람용) | — |

검증 결과 문서는 완료 시 `docs/research/<검증명>.md`로 생깁니다.
계획서는 `docs/plans/PLAN_*.md`이며 **임시 산출물**이라 이 지도에 등록하지 않습니다.

---

## 4. reference/ — 참고용 원본 (읽기 전용)

수정·import·실행하지 않습니다. 읽고 이해한 뒤 `src/verify_lab/`에 새로 작성합니다.
품질 검사(Ruff·PyRight·pytest) 대상에서 제외돼 있습니다.

### 안내

| 파일 | 용도 |
| --- | --- |
| [../reference/README.md](../reference/README.md) | reference 폴더 규칙과 파일별 상세 안내 |

### 통계 해석·과최적화 방어 (결과를 해석하기 전에 읽을 것)

| 파일 | 용도 |
| --- | --- |
| [../reference/과최적화_검증_노하우.md](../reference/과최적화_검증_노하우.md) | 과최적화 원리, PBO/DSR, **거래 수와 통계적 검정력**, **"이미 답을 본" 오염 문제** |
| [../reference/데이터처리_설계원칙.md](../reference/데이터처리_설계원칙.md) | **절대 원칙**(look-ahead·보간·생존편향 금지), 데이터 처리 규칙, 판정식 단일화 |

### 데이터 수집

| 파일 | 용도 |
| --- | --- |
| [../reference/yfinance_downloader.py](../reference/yfinance_downloader.py) | QQQ 수집기 작성 시 — yfinance 호출, 수정주가, 이상치 검증, 최근 2일 제외 |
| [../reference/pykrx_실측기록.md](../reference/pykrx_실측기록.md) | **pykrx 실측 전 필독** — 함수별 반환값과 함정이 실측으로 기록됨 |
| [../reference/data_loader_qbt.py](../reference/data_loader_qbt.py) | `data/` 계층 — CSV 로딩 중앙집중 패턴, 겹치는 기간 추출 |

### 측정 계층

| 파일 | 용도 |
| --- | --- |
| [../reference/event_study.py](../reference/event_study.py) | `measure/` — forward return 2기준, 초과수익, 구간 절단, 계층별 집계 |
| [../reference/analysis_script_example.py](../reference/analysis_script_example.py) | 검증 스크립트의 크기와 형태 |
| [../reference/parallel_executor_qbt.py](../reference/parallel_executor_qbt.py) | 병렬이 실제로 필요해질 때만. **먼저 numpy 벡터화를 시도할 것** |

### 상수 정의

| 파일 | 용도 |
| --- | --- |
| [../reference/common_constants_qbt.py](../reference/common_constants_qbt.py) | `common_constants.py` 작성 시 |
| [../reference/common_constants_krx.py](../reference/common_constants_krx.py) | 같은 용도. 접두사(`COL_`·`KEY_`·`DISPLAY_`·`DEFAULT_`) 사용 예 |

### 테스트 작성 예시

| 파일 | 용도 |
| --- | --- |
| [../reference/test_examples/event_study_test_example.py](../reference/test_examples/event_study_test_example.py) | **look-ahead 감시 테스트**와 산식 고정 테스트 실제 예시 |
| [../reference/test_examples/conftest_example.py](../reference/test_examples/conftest_example.py) | 합성 데이터 픽스처 |
| [../reference/test_examples/conftest_qbt_example.py](../reference/test_examples/conftest_qbt_example.py) | **파일 격리 픽스처** — import 시점 경로 캡처 모듈까지 패치 |

### pykrx 수집 원본 (`reference/pykrx_collect/`)

전종목 스냅샷용 코드입니다. verify-lab은 ETF 한 종목만 필요하므로 **호출 패턴과 검증 방식만** 참고하고
스냅샷·백필 구조를 그대로 가져오지 않습니다.

| 파일 | 용도 |
| --- | --- |
| [../reference/pykrx_collect/__init__.py](../reference/pykrx_collect/__init__.py) | 패키지 초기화 |
| [../reference/pykrx_collect/snapshot.py](../reference/pykrx_collect/snapshot.py) | pykrx 호출과 스키마 검증의 핵심 |
| [../reference/pykrx_collect/snapshot_store.py](../reference/pykrx_collect/snapshot_store.py) | 일자별 불변 파일 저장 |
| [../reference/pykrx_collect/adjusted.py](../reference/pykrx_collect/adjusted.py) | 수정주가 산출 |
| [../reference/pykrx_collect/adjusted_store.py](../reference/pykrx_collect/adjusted_store.py) | 수정주가 저장 |
| [../reference/pykrx_collect/adjusted_backfill.py](../reference/pykrx_collect/adjusted_backfill.py) | 수정주가 백필 루프 |
| [../reference/pykrx_collect/adjusted_quality.py](../reference/pykrx_collect/adjusted_quality.py) | 수정주가 정합성 검증 |
| [../reference/pykrx_collect/backfill.py](../reference/pykrx_collect/backfill.py) | 체크포인트·재시도·휴장 처리 |
| [../reference/pykrx_collect/calendar.py](../reference/pykrx_collect/calendar.py) | **거래일 달력** — 휴장일 판정 |
| [../reference/pykrx_collect/gate_checks.py](../reference/pykrx_collect/gate_checks.py) | **pykrx 실측 스팟체크** — 실측 스크립트 작성 시 참고 |
| [../reference/pykrx_collect/quality.py](../reference/pykrx_collect/quality.py) | 커버리지·이상치·검산 리포트 |
| [../reference/pykrx_collect/names.py](../reference/pykrx_collect/names.py) | 종목명 관리 |
| [../reference/pykrx_collect/meta_store.py](../reference/pykrx_collect/meta_store.py) | 수집 메타 저장 |
| [../reference/pykrx_collect/krx_credentials.py](../reference/pykrx_collect/krx_credentials.py) | KRX 자격증명 처리 |

---

## 5. 데이터와 산출물

| 위치 | 내용 | git |
| --- | --- | --- |
| `storage/market/QQQ_max.csv` | QQQ 일별 시세 (**원본가**, 전 기간). `scripts/data/collect_yfinance.py` 로 재수집한다 | 동기화 |
| `storage/market/069500_max.csv` | KODEX 200 일별 시세 (**원본가**, 상장일부터 전 기간) | 동기화 |
| `storage/market/` | 수집한 원시 시세 | 동기화 |
| `storage/results/{검증, 매매, 실측}/<실행시각>_<매매법>/` | 산출물 (CSV, summary.json). **계층이 경로로 드러납니다** | 동기화 (결과 문서가 근거로 인용한다) |
| `storage/results/meta.json` | 실행 이력 (최근 5개 순환) | 제외 (실행마다 재작성돼 PC 간 충돌) |

**산출물이 사는 자리는 하나입니다.** 계층 폴더 도입 전의 산출물 16개도 2026-09-11 에 전부 옮겼고,
그때 옛 slug 6개(`index_extreme` ×4 · `expiry_trading` ×2)를 현재 이름으로 개명했습니다.
자리가 둘이면 **같은 매매법이 계층에 따라 다른 이름으로 불리는 상태가 남기 때문**입니다.

**옮길 때 기계가 지킨 것은 「경로」입니다.** `utils/result_citations.py` 의 `missing_citations`
는 폴더 **이름**만 보고 탐색이 여러 자리를 훑으므로, **이동만 한 폴더는 그 판정에 잡히지 않습니다** —
실측으로 10개가 그랬고, 이름 판정은 개명된 6개만 봤습니다. 그래서 `missing_result_paths` 가
문서에 적힌 산출물 **경로의 실재**를 따로 검사합니다. 두 판정은 역할이 다르며
어느 쪽도 다른 쪽을 대신하지 못합니다.

`result_dir_paths` 는 **루트 직하도 계속 훑습니다.** 이제 거기 산출물이 없지만, 두 장치가
이어서 동작하기 때문입니다 — 테스트가 루트 직하의 폴더를 품질 검증에서 실패로 알리고,
`/clean-results` 가 **그 탐색을 통해** 찾아 지웁니다. 탐색을 빼면 알림은 오는데 치울 수단이 없습니다.

같은 이름이 두 자리에서 나오면 예외를 던지지 않고 **경로를 목록으로** 돌려줍니다 — 측정과
매매가 같은 slug 를 쓰는 것이 이 저장소의 규약이라, 같은 초에 두 계층을 돌리면 실제로 그 상태가 됩니다.

**폴더 이름에 계층 접미사를 붙이지 않습니다.** 같은 매매법의 측정과 매매가 같은 이름을 쓰고
상위 폴더가 둘을 가릅니다. 전에는 접미사가 계층마다 달라 같은 매매법이 `index_extreme` 과
`reverse_trading` 두 이름으로 불렸고, 사용자가 그 둘을 옛것/새것으로 오해했습니다.

### 파일 이름도 두 벌이 공존합니다 — 의도입니다

**`매매/` 안의 산출물은 `성적표.csv` · `거래내역.csv` 입니다**(규격은
[../src/verify_lab/CLAUDE.md](../src/verify_lab/CLAUDE.md) 「매매 산출물 계약」).
**`검증/` 안은 영문 그대로**입니다 — 측정 계층은 방향이 미정이라 「승률」을 쓸 수 없고
기준선·우연확률 축을 버릴 수 없어 파일을 둘로 줄일 수 없습니다. 같은 이름을 붙이면
**다른 것이 같아 보입니다.**

그리고 **폴더를 옮길 때도 그 안의 파일명은 바꾸지 않았습니다.** 이름만 맞추면 **다른 것이
같아 보이기** 때문입니다 — 옛 `stop_loss_grid.csv` 는 17컬럼이고 계약이 정한 `성적표.csv` 는
25컬럼이라, 같은 이름을 붙이면 없는 축(`손익비`·`질 때 표본`·`구간 시작일`)이 있는 것처럼 읽힙니다.
그래서 살아있는 문서에 두 이름이 함께 보일 수 있습니다.

**판정 규칙은 하나입니다 — 「재실행이 그 산출물을 대체했는가」.**

| 상태 | 인용 |
| --- | --- |
| 재실행이 같은 값을 재현했다 | **새 폴더·새 이름으로 갱신한다.** 갱신 전에 **공통 컬럼을 기계로 대조**하고, 행 수와 값이 맞지 않으면 **문서를 고치지 않는다** — 어긋남 자체가 조사 대상이다 |
| 별도 실행이라 대체되지 않았다 (예: 손절선 격자) | **옛 파일명 그대로 둔다.** 그 사실을 문서 머리말에 적는다 |

**대조 기록에 옛 폴더 이름을 적지 않습니다.** 적으면 인용 스캐너가 그것을 인용으로 잡아
**그 폴더가 영구히 묶여** 정리할 수 없게 됩니다. 남길 것은 「무엇을 몇 열 대조했고 값이
같았다」이며, 어느 폴더였는지는 git 이력이 말합니다.

국내 두 파일은 `scripts/data/collect_pykrx.py` 로 한 번에 재수집합니다.
**같은 `_max.csv` 라도 종목에 따라 가격 기준이 다릅니다** — 이유와 근거는
[../src/verify_lab/CLAUDE.md](../src/verify_lab/CLAUDE.md) 「계층 간 계약」의 원시 시세 저장 규칙에 있습니다.

---

## 6. 이 지도의 유지 규칙

- **`docs/`와 `reference/`에 파일을 추가하면 이 문서에 등록합니다.** 예외는 `docs/plans/`(임시 산출물)뿐입니다
- 파일을 지우거나 옮기면 여기서도 지웁니다
- `tests/test_index.py`가 양방향으로 검사합니다 — 등록된 경로가 실재하는지, 실재하는 파일이 등록됐는지
- 규칙 문서 자체의 내용은 여기에 복제하지 않습니다. **어디에 무엇이 있는지만** 적습니다
