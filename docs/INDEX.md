# INDEX — 문서 지도

> **위치만 적습니다.** 각 문서가 무엇을 말하는지는 그 문서의 머리말과 목차가 말합니다 —
> 여기에 요약을 두면 원문과 두 벌이 되고 한쪽이 낡습니다.
>
> 진입 순서의 SoT 는 [../.claude/rules/session-bootstrap.md](../.claude/rules/session-bootstrap.md) 입니다.
> `docs/`·`reference/` 에 파일을 더하거나 지우면 이 지도도 고칩니다(`docs/plans/` 는 예외) —
> `tests/test_index.py` 가 링크 실재와 등록 누락을 양방향으로 검사합니다.

---

## 1. 규칙 문서

| 문서 | 담당 | 로드 |
| --- | --- | --- |
| [../CLAUDE.md](../CLAUDE.md) | 측정의 원칙 · 후보 판정 기준 · 프로젝트 전반 규칙 | 항상 |
| [MEMORY.md](MEMORY.md) | 모르면 틀리는 함정 · 작업 규율 · 환경 노하우 | 항상 (`CLAUDE.md` 가 `@import`) |
| [../.claude/rules/session-bootstrap.md](../.claude/rules/session-bootstrap.md) | 세션 진입 순서 | 항상 |
| [../src/verify_lab/CLAUDE.md](../src/verify_lab/CLAUDE.md) | 계층 분리 · 절대 원칙 · 계층 간 계약 · 산출물 계약 | `src/verify_lab/` 를 Read 할 때 |
| [../scripts/CLAUDE.md](../scripts/CLAUDE.md) | CLI 계층 책임 · 인자 정책 | `scripts/` 를 Read 할 때 |
| [../tests/CLAUDE.md](../tests/CLAUDE.md) | 필수 테스트 · 결정적 테스트 · 파일 격리 | `tests/` 를 Read 할 때 |
| [../.claude/rules/docs.md](../.claude/rules/docs.md) | 문서 종류와 수명 · 시제 · 계획서 승격 | `docs/**` 를 Read 할 때 |
| [../.claude/rules/research.md](../.claude/rules/research.md) | 결과 문서 형식 | `docs/{검증,매매,조사}/**` 를 Read 할 때 |
| [../.claude/rules/trading.md](../.claude/rules/trading.md) | 매매 규칙 계층의 예외와 제약 | `docs/{검증,매매,조사}/**` · `src/verify_lab/{execution,studies}/**` 를 Read 할 때 |
| [../.claude/rules/reference.md](../.claude/rules/reference.md) | reference 폴더 읽기 전용 | `reference/**` 를 Read 할 때 |
| `~/.claude/rules/python.md` (전역 — 저장소 밖이라 링크하지 않음) | 파이썬 코딩 표준 · 반올림 · 로깅 | `**/*.py` 를 Read 할 때 |
| `~/.claude/skills/impl-plan/SKILL.md` (전역) | 계획서 절차 | `/impl-plan` 호출 |

경로 규칙은 **`Read` 도구로 열 때만** 주입됩니다 — 셸로 읽으면 따라오지 않습니다(session-bootstrap 「규칙 자동 로드는 `Read` 도구에만 걸린다」).

---

## 2. 매매법·조사

**등급의 SoT 는 [../src/verify_lab/tracks.py](../src/verify_lab/tracks.py) 입니다.** 승격·강등은 그 한 줄을 바꾸는 것이고,
한글 이름이 곧 `docs/<등급>/<이름>/` 과 `storage/results/<등급>/<이름>/` 의 폴더 이름입니다.
코드가 있는 매매법의 한글 이름이 이 표에 있는지 `tests/test_tracks.py` 가 확인합니다.

**상태**는 여섯 낱말 중 하나입니다 — `확정 규칙`(규칙까지 정함) · `재는 중`(검증 등급) · `걸지 않음`(규칙을 세웠다가
걸지 않기로 함) · `우위 없음`(우연과 구별되지 않음) · `성질 조사`(신호 없이 성질을 잼) · `데이터 실측`(데이터 소스의 성질).

| 이름 | slug | 등급 | 코드 | 문서 | 상태 |
| --- | --- | --- | --- | --- | --- |
| 역방향 | `reverse` | 매매 | `studies/reverse/` | [설계](매매/역방향/설계.md) · [결과](매매/역방향/결과.md) · [규칙](매매/역방향/규칙.md) | 확정 규칙 |
| 중간선거_사이클 | `midterm_cycle` | 매매 | `studies/midterm_cycle/` | [설계](매매/중간선거_사이클/설계.md) · [결과](매매/중간선거_사이클/결과.md) · [규칙](매매/중간선거_사이클/규칙.md) | 확정 규칙 |
| 원달러_ETF_등가성 | `usdkrw_equivalence` | 조사 | `studies/usdkrw_equivalence/` | [결과](조사/원달러_ETF_등가성/결과.md) | 성질 조사 |
| 레버리지_ETF_괴리 | `leverage_tracking` | 조사 | `studies/leverage_tracking/` | [설계](조사/레버리지_ETF_괴리/설계.md) · [결과](조사/레버리지_ETF_괴리/결과.md) | 성질 조사 |
| 선물_대_레버리지_ETF | `futures_leverage` | 조사 | `studies/futures_leverage/` | [설계](조사/선물_대_레버리지_ETF/설계.md) · [결과](조사/선물_대_레버리지_ETF/결과.md) | 성질 조사 |
| 옵션_만기일 | `option_expiry` | 조사 | 없음 | [설계](조사/옵션_만기일/설계.md) · [결과](조사/옵션_만기일/결과.md) · [규칙](조사/옵션_만기일/규칙.md) | 걸지 않음 |
| 월말_진입 | `month_end` | 조사 | 없음 | [설계](조사/월말_진입/설계.md) · [결과](조사/월말_진입/결과.md) · [규칙](조사/월말_진입/규칙.md) | 걸지 않음 |
| 만기_말일 | `expiry_monthend` | 조사 | 없음 | [설계](조사/만기_말일/설계.md) · [결과](조사/만기_말일/결과.md) · [규칙](조사/만기_말일/규칙.md) | 걸지 않음 |
| 원달러_그리드 | `usdkrw_grid` | 조사 | 없음 | [설계](조사/원달러_그리드/설계.md) · [사양서](조사/원달러_그리드/사양서.md) · [규칙](조사/원달러_그리드/규칙.md) | 걸지 않음 |
| 원달러_조달 | — | 조사 | 없음 | [원달러_조달.md](조사/원달러_조달.md) | 성질 조사 |
| 연속_등락 | — | 조사 | 없음 | [결과](조사/연속_등락/결과.md) | 우위 없음 |
| ECOS_실측 | `ecos_probe` | 조사 | `scripts/data/check_ecos.py` | 없음 | 데이터 실측 |
| pykrx_ETF_실측 | `pykrx_etf_probe` | 조사 | `scripts/data/check_pykrx_etf.py` | 없음 | 데이터 실측 |
| pykrx_이어붙이기_실측 | `pykrx_splice_probe` | 조사 | `scripts/data/check_pykrx_splice.py` | 없음 | 데이터 실측 |

확정 규칙의 본문은 각 `규칙.md` §1 입니다. 코드가 없는 매매법을 되살리는 절차는 그 매매법의 `결과.md` 머리말에 있습니다.

---

## 3. 찾는 것 → 어디

매매법 폴더 밖에서 찾기 어려운 것만 둡니다. **절 번호가 아니라 절 제목**으로 가리킵니다.

| 찾는 것 | 문서 · 절 |
| --- | --- |
| ETN 시세를 KRX 에서 직접 받는 법 | [조사/레버리지_ETF_괴리/설계.md](조사/레버리지_ETF_괴리/설계.md) 「데이터 실측 기록」 |
| 국내 선물 계약별 시세와 그 함정 | [조사/선물_대_레버리지_ETF/설계.md](조사/선물_대_레버리지_ETF/설계.md) 「데이터 실측 기록 — KRX 파생상품 통계」 |
| 지수를 OHLCV 로 받으려 할 때 (미국·한국 지수 OHLC 의 진위) | [매매/중간선거_사이클/설계.md](매매/중간선거_사이클/설계.md) 「데이터 실측 기록」 |
| ECOS·FRED 통계 코드, 매매기준율의 하루 시차 | [조사/원달러_그리드/설계.md](조사/원달러_그리드/설계.md) 「데이터 소스 (확정)」·「데이터 실측 기록」 |
| pykrx 함수가 무엇을 반환하고 어디서 틀리는가 | [../reference/pykrx_실측기록.md](../reference/pykrx_실측기록.md) · [매매/역방향/설계.md](매매/역방향/설계.md) 「사전 실측 기록」 |
| 1배로 잰 결과를 2·3배 상품으로 옮겨 읽을 때 | [조사/레버리지_ETF_괴리/결과.md](조사/레버리지_ETF_괴리/결과.md) |
| 9월 만기일·월말에 다시 걸려 할 때 | [조사/만기_말일/규칙.md](조사/만기_말일/규칙.md) 「등급 — 걸지 않기로 하고 조사로 내린다」 |
| 결과를 해석하기 전 — 과최적화와 검정력 | [../reference/과최적화_검증_노하우.md](../reference/과최적화_검증_노하우.md) |

---

## 4. 그 밖

| 문서 | 담당 |
| --- | --- |
| [COMMANDS.md](COMMANDS.md) | 실행 명령어 |
| [../README.md](../README.md) | 사람용 소개 |
| [../reference/README.md](../reference/README.md) | 참고 원본(읽기 전용)의 파일별 용도 |

reference 의 나머지 파일: [데이터처리_설계원칙.md](../reference/데이터처리_설계원칙.md) ·
[test_examples/event_study_test_example.py](../reference/test_examples/event_study_test_example.py) ·
[test_examples/conftest_example.py](../reference/test_examples/conftest_example.py) ·
[test_examples/conftest_qbt_example.py](../reference/test_examples/conftest_qbt_example.py)

계획서(`docs/plans/`)는 임시 산출물이라 이 지도에 등록하지 않습니다.
