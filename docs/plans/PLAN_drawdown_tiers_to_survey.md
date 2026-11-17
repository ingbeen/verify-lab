# Implementation Plan: 하락_단계_매수를 조사로 내리고 코드 지우기

> 작성/운영 규칙(SoT): `/impl-plan` 스킬(`~/.claude/skills/impl-plan/SKILL.md`)을 반드시 참고하세요.  
> (이 템플릿을 수정하거나 새로운 양식의 계획서를 만들 때도 해당 스킬을 포인터로 두고 준수합니다.)

**상태**: ✅ Done

---

> 상태는 🟡 Draft / 🔄 In Progress / ✅ Done. Done 조건과 기록 규칙은 `/impl-plan` 「3) 스킵 및 완료 규칙」이며 `~/.claude/hooks/plan_lint.py` 가 저장 때 검사한다.

---

**작성일**: 2026-11-17 11:11
**마지막 업데이트**: 2026-11-17 12:40
**관련 범위**: docs(조사 · INDEX · COMMANDS · DEFERRED_FINDINGS) · studies(drawdown_tiers 삭제) · data(loader) · tracks · tests · storage(market 사본 · results)
**관련 문서**: `.claude/rules/docs.md` · `.claude/rules/research.md` · `.claude/rules/trading.md` · `src/verify_lab/CLAUDE.md` · `scripts/CLAUDE.md` · `tests/CLAUDE.md`

---

## 1) 목표(Goal)

- [x] 목표 1: `docs/검증/하락_단계_매수/` 의 세 문서(설계 · 결과 · 사전조사)를 한 장 `docs/조사/하락_단계_매수.md` 로 합친다 — 수치는 한 자리도 바꾸지 않고, 바꾸는 글은 아래 「합칠 때의 변경 목록」뿐이다
- [x] 목표 2: 이 매매법의 코드 · 테스트 · 산출물과, 이 매매법 때문에 공유 계층에 생겨 호출처가 0 이 되는 것(`load_close_series` 의 `max_daily_change_rate` 키워드)을 지운다
- [x] 목표 3: `tracks.py` 의 줄을 조사 · 성질 조사로 바꾸고 INDEX 상태를 「우위 없음」으로 한다
- [x] 목표 4: 이 매매법만 읽던 사본 둘(`^VIX_raw.csv` · `fear_greed_daily.csv`)을 quant-data 갱신 없이 다시 내보내 목록 · 매니페스트에서 빼고, 남은 매매법 둘의 산출물이 바이트 단위로 그대로임을 확인한다
- [x] 목표 5: 저장소에 이 매매법을 가리키는 곳이 「남길 목록」 밖에 남지 않는다

## 2) 비목표(Non-Goals)

- 수치를 다시 재지 않는다 — 새 문서의 수치는 2026-11-16 실행과 2026-11-17 스크래치의 기록이다(중간선거_사이클 · 반감기_사이클 재실행은 「바뀌지 않았다」를 보는 확인용)
- **quant-data 를 고치지 않는다** — 그 저장소의 `docs/research/시세_받기_판정.md`(94 · 271행)가 `docs/검증/하락_단계_매수/설계.md` 를 가리키고, `src/quant_data/catalog.py:152` 가 「verify-lab 용 하락_단계_매수의 신호」로 VIX · 공포탐욕지수를 계속 받는다. 경로가 죽는 것과 받기를 이어 갈지는 quant-data 의 일이라 Done 보고에 올리고 사용자가 정한다
- `3423368` 이 공유 계층으로 올린 12개 이름을 패키지로 되내리지 않는다(사용자 결정 2026-11-17 — 지운 뒤에도 중간선거_사이클 · 반감기_사이클이 쓴다)
- `execution/periods.period_rows` 의 `event_ids` 인자를 정리하지 않는다 — 2026-09-15(`d838db9`)부터 있었고 이 매매법이 들어오기 직전(`3423368`)에도 넘기는 곳이 0 이었다. 원래 상태로 돌아가는 것이라 언급만 한다
- `docs/plans/PLAN_drawdown_tiers.md` 는 손대지 않는다(임시 문서 — 영구 문서가 가리키지 않게만 한다)
- 「하락장」 · 「다시 켬」 · 「이 검증」 같은 말은 바꾸지 않는다 — 사용자가 정한 실무 용어는 「이벤트 스터디 격자」 · 「비용 차감 전 성적」 둘이다
- §13 물타기를 저장소 코드로 짓지 않는다(설계 Q14)

## 3) 배경/맥락(Context)

### 현재 문제점 / 동기

- 설계 Q14(2026-11-17 사용자 결정): 규칙을 세우지 않고 참고용으로 둔다 — 조사로 내려 세 문서를 한 장으로 합치고 이 매매법의 코드 · 테스트 · 산출물을 지운다
- 선례: `docs/조사/역방향.md` — 머리말 · 「관련 파일」의 묘비 표기(「**삭제** — … 였다」 · `git show <커밋>:<경로>`) · 「재현 방법」의 되살리는 절차를 그 모양대로 따른다

### 사용자 결정 (2026-11-17 질문 라운드 — 「추천대로 진행」)

| # | 항목 | 결정 |
| --- | --- | --- |
| 1 | INDEX 상태 낱말 | **우위 없음** — 규칙을 세운 적이 없어 「걸지 않음」의 정의(규칙을 세웠다가 걸지 않기로 함)와 맞지 않고, 신호가 있어 「성질 조사」와도 맞지 않는다. `tests/test_tracks.py:313` 의 강등 목록(「걸지 않기로 한 매매법」)에는 넣지 않는다 — `usdkrw_grid` 도 그 목록 밖이다 |
| 2a | `load_close_series` 의 `max_daily_change_rate` 키워드 | **지운다** — 키워드와 `46f081e` 가 더한 테스트 셋(`tests/test_data_loader.py:788` · `:804` · `:824`)을 그 전 상태로 되돌린다. 셋째(`:788`)는 키워드를 쓰지 않지만 docstring 이 그 인자를 전제하고, 같은 동작은 `test_close_series_applies_market_checks`(`:770`)가 본다 |
| 2b | `3423368` 의 12개 이름 | **둔다** |
| 3 | VIX · 공포탐욕지수 사본 | **지금 뺀다** — quant-data 갱신 없이 다시 내보내고 남는 CSV 둘을 지운다 |
| 4 | 용어 | **둘 다 바꾼다** — 「맨몸 격자」 → 「이벤트 스터디 격자」(첫 등장에 기준선 대비 차이 한 줄) · 「맨몸 성적」 → 「비용 차감 전 성적」 |
| 5 | `docs/DEFERRED_FINDINGS.md` 의 공유 `trade_rows` 줄 | **남기고**, 하락_단계_매수 수치를 「지운 하락_단계_매수의 마지막 산출물(커밋)」 기록으로 바꾸며 지울 신호내역을 가리키는 문장은 지운다 |

### 실측 — 지운 뒤 공유 계층에서 호출처가 0 이 되는 것 (2026-11-17)

- 이 매매법이 import 하는 공유 이름 전부를 `git grep -w` 로 세면 src · scripts 의 다른 호출처가 0 인 것은 `report/run_summary.KEY_DATASET_LABEL` 하나 — 정의 파일의 `dataset_record`(`report/run_summary.py:96`)가 쓰고 2026-09-15(`94a2273`)부터 있던 이름이라 대상 아님
- 이 매매법이 공유 함수에 넘기는 키워드를 AST 로 전부 뽑아 다른 호출처와 대조하면 0 인 것은 둘 — `load_close_series(max_daily_change_rate=)`(이 매매법이 더함 → 지움) · `period_rows(event_ids=)`(원래 있던 것 → Non-Goals)
- `3423368` 의 12개 이름은 11개를 두 매매법이 함께 쓰고 `BASELINE_PREFIX` 는 `report/constants.py` 안과 `scripts/run_halving_cycle.py` 가 쓴다
- **`3423368` 뒤 커밋 셋(`46f081e` · `b1d27e9` · `4efd7fb`)이 모두 이 매매법의 것**이다. 그래서 공유 파일 대부분은 지운 뒤 `git diff 3423368 -- <파일>` 이 비어야 한다 — 예외는 아래 「`src/verify_lab/CLAUDE.md` 에서 남기는 것」 · INDEX · tracks.py · DEFERRED_FINDINGS · 매니페스트(커밋 줄)

### 실측 — 사본을 갱신 없이 다시 내보내면 (2026-11-17)

- quant-data HEAD `ff3306d`(사본 매니페스트의 커밋과 같다) · `git status --porcelain` 비어 있음
- 남길 사본 9개가 quant-data `storage/` 원본과 `cmp` 로 바이트 같다
- 내보내기(`quant-data/src/quant_data/export.py` 의 `export_files`)는 목록의 파일만 복사하고 매니페스트를 목록대로 다시 쓰며 「받는 폴더의 다른 파일은 건드리지 않는다」 — 남는 CSV 둘은 손으로 지운다
- 예측: quant-data `storage/manifest.json` 의 9개 항목 값이 지금 사본 매니페스트의 같은 항목과 같고(스크립트 대조 `True`) 기준일도 2026-11-10 으로 같다 → 다시 쓴 매니페스트는 **지금 것에서 끝의 두 항목만 빠진 모양**이어야 한다

### `src/verify_lab/CLAUDE.md` 에서 남기는 것 — `46f081e` 가 함께 고친 이 매매법 밖의 사실

이 매매법을 말하는 구절은 `3423368` 때 문장으로 되돌리되, 아래는 그대로 둔다. 지운 뒤 `git diff 3423368 -- src/verify_lab/CLAUDE.md` 는 이것만 보여야 한다.

| # | 자리 | 남기는 것 |
| --- | --- | --- |
| K1 | 「studies의 계약」 코드 블록 주석 | 「등락 순위로 … (아래 「이벤트 정의 계약」)」 |
| K2 | 「studies의 계약」 끝 문단 | 「중간선거_사이클 · 반감기_사이클은 달력으로 진입일을 정해 넘기고, 반감기_사이클 2단계는 지표가 문턱을 건넌 날의 목록을 넘깁니다」 — 하락_단계_매수 구절만 뺀다 |
| K3 | 「`사건` 은 번호를 넘긴 매매법만 낸다」 행 | 「중간선거_사이클 · 반감기_사이클은 … **신호 = 사건**이고 컬럼을 내지 않습니다 — 빈칸은 …」 — 끝의 하락_단계_매수 문장만 뺀다 |
| K4 | 「「아래」를 인버스 실물로 재는 축은 없습니다」 행 | 「지금 매매법은 모두 「위」 하나라」 |
| K5 | 「이벤트 정의 계약 — studies」 첫 문단 | 「등락 순위로」 · 「그 모양의 이벤트형을」 |
| K6 | 같은 절 둘째 문단 | 반감기_사이클 2단계의 지표 신호 한 문단으로 줄인다 — 「지표 «수준»으로 신호를 정하는 이벤트형은 반감기_사이클 2단계의 지표 신호(`studies/halving_cycle/indicator_signals.crossing_days`)입니다 — 문턱을 건널 때마다 신호이고 다시 켜는 수준이 문턱 자체입니다(그 매매법 `설계.md` 결정 ㉔ · ㉖ · ㉗ · ㉙). 그 계약은 그 패키지가 갖고 공유 계층 계약으로 올리지 않습니다 — 달력형 둘을 각자의 패키지에 두는 것과 같은 이유입니다(위 「지금 공유 계층에 있는 달력형은 아래뿐」 문단).」 |

### 새 문서의 장 구성과 § 재매핑

`.claude/rules/research.md` 「필수 구조」 · 「파일 네이밍」 — 설계 장은 측정 장 뒤 · 해석 앞. 결정 번호(Q1 ~ Q14 · D1 ~ D12)와 절 제목은 그대로 둔다.

| 새 문서 | 원문 |
| --- | --- |
| 머리말 · 재실행 기록 · 관련 파일 · 목차 | 새로 쓴다(재실행 기록 표는 결과 그대로 + 한 행) |
| §1 결론 요약 | 결과 §1 |
| §2 문제 정의 | 설계 §1 「이 검증이 묻는 것」 + 결과 §2 의 측정 절차 문장 |
| §3 ~ §13 | 결과 §3 ~ §13 (번호 그대로) |
| §14 확정된 설계 결정 | 설계 §2 |
| §15 데이터 실측 기록 (§15.1 ~ §15.8) | 설계 §3 (§3.1 ~ §3.8) |
| §16 사전조사 (§16.1 ~ §16.4) | 사전조사 §1 ~ §4 |
| §17 해석 | 결과 §14 |
| §18 한계 | 결과 §15 |
| §19 재현 방법 (§19.1 되살리는 절차 · §19.2 공유 계층에서 함께 지운 정의 · §19.3 원문 · 산출물 · 사본 보기와 다시 내보내 되살리면 · §19.4 §13 물타기 스크래치) | 결과 §16 을 새로 쓰되 §13 스크래치의 bullet 과 스크립트 전문은 그대로 옮긴다 |

### 합칠 때의 변경 목록 — 이 밖의 글자 변경은 0

| # | 무엇 |
| --- | --- |
| E1 | 머리말을 새로 쓴다 — 작성일 · 조사로 내림(Q14 · 우위 없음) · 「실행 코드가 없어 수치는 그때의 측정 기록이다 — §13 스크래치만 §19.4 의 스크립트로 재현된다」 · 대상 · **데이터 기간 · 판정 기간 · 가격 기준은 결과 머리말 글자 그대로** · 미리보기 수 줄(설계 머리말 그대로, §3.1 → §15.1) · 본문의 산출물 CSV 는 커밋 `<삭제 직전 HEAD>` 에 있다(§19.3) · 재현 스크립트 묘비 · 비용 차감 전 성적 · 과거 재구성 |
| E2 | 재실행 기록에 2026-11-17 한 행 — 조사로 내리며 한 장으로 합쳤다 · 이 표와 본문의 § 는 합친 뒤 번호 · 용어 둘을 실무 용어로 · 수치는 바뀌지 않았다 |
| E3 | 「관련 파일」을 묘비 표기로 새로 쓴다(원문 세 문서 · 이벤트 정의 · 측정 · 체결 · 공유 계층에서 함께 지운 것 · 실행 스크립트 · 테스트 · 산출물 · 데이터 · 물타기 스크래치 · 실행 명령어 · 도출된 매매 규칙 없음) |
| E4 | 목차를 새 번호로 |
| E5 | §2 — 설계 §1 본문을 쓰고, 결과 §2 의 첫 문단(같은 질문)은 겹쳐 뺀다. 「질문의 배경과 웹 자료는 … 설계 결정은 … 가 갖는다」는 §16 · §14 를 가리키게 남긴다. 결과 §2 의 「분할 · 비중 · 청산 · 손절은 아직 정하지 않았다」는 설계 §1 의 Q14 문장이 대신해 뺀다. 측정 절차 문장(「지표가 단계에 처음 닿은 날의 다음 거래일 종가에 사서 정해진 거래일 뒤 종가에 팔면 어땠나」)은 남긴다 |
| E6 | 「맨몸 격자」 2곳 → 「이벤트 스터디 격자」 — 첫 등장(§2)에 「학계처럼 시장모형 대비 초과수익률이 아니라 모든 거래일 기준선 대비 차이로 잰다」 한 줄. §4 용어 정의에 그 말의 행 하나를 더한다. 「맨몸 성적」(결과 머리말)은 E1 의 새 머리말에서 「비용 차감 전 성적」 |
| E7 | § 재매핑 — 위 표대로. 원문의 `설계.md` · `결과.md` · `사전조사.md` · 「설계 Q13」 · 「설계 결정 D7」 같은 다른 문서 가리킴을 이 문서의 § 로(예: `설계.md` §3.4 → §15.4, 설계 Q13 → §14 Q13, `사전조사.md` §3 → §16.3, 결과 §16 의 스크립트 → §19.4). 재실행 기록 표의 § 도 새 번호로(E2 가 그 사실을 적는다) |
| E8 | §14 머리 인용의 「코드 주석과 테스트가 이 번호를 가리킨다」 → 「지운 코드 주석과 테스트가 이 번호를 가리켰다(§19)」 |
| E9 | §16 머리 인용 — 사전조사 머리말을 장 머리로: 작성 · 웹 조사 날짜와 인용 표기 범례는 그대로, 「이 문서는 자료만 담는다 … `설계.md` · `결과.md` 가 갖는다」 → 「이 장은 자료만 담는다 … §14 · §5 ~ §13 이 갖는다」 |
| E10 | §9 끝 문장의 산출물 경로 앞에 「커밋 `<삭제 직전 HEAD>` 의」 |
| E11 | §19 — 결과 §16 의 선행 조건 · 실행 · 데이터 기간 · 「다시 내보내 재실행하면」 bullet 을 §19.1 · §19.3 으로 다시 쓰고(실행 명령이 지워졌으므로), §13 스크래치 bullet 과 스크립트 전문은 §19.4 로 그대로 옮긴다. 스크립트 안에서 바꾸는 것은 주석 「결과.md §3」 → 「이 문서 §3」 한 곳 |

### 영향받는 규칙(반드시 읽고 전체 숙지)

> 아래 문서에 기재된 규칙을 **모두 숙지**하고 준수합니다.

- `.claude/plan-config.json` — 이 저장소의 검증 명령·자동 포맷·근거 승격 목적지 (**값의 SoT**)
- 루트 `CLAUDE.md` — 특히 「계획서 규약 — 이 프로젝트의 설정」 · 「재수집은 이미 나온 결과를 바꿉니다」
- `docs/MEMORY.md` — 「이름만 바꾸는 변경과 값을 바꾸는 변경을 한 커밋에 섞지 않는다」
- `.claude/rules/docs.md` · `.claude/rules/research.md` · `.claude/rules/trading.md`
- `src/verify_lab/CLAUDE.md` · `scripts/CLAUDE.md` · `tests/CLAUDE.md`
- 전역 `~/.claude/docs/실무_용어.md` §2 · 「바꿀 때」
- quant-data `CLAUDE.md` · `docs/COMMANDS.md` 「내보내기」 (Phase 3 의 실행)

## 4) 완료 조건(Definition of Done)

> Done은 "서술"이 아니라 "체크리스트 상태"로만 판단합니다. (정의/예외는 `/impl-plan` 스킬)

- [x] `docs/조사/하락_단계_매수.md` 가 필수 구조와 「관련 파일」 묘비 표기를 갖고, 원문 세 문서의 내용이 「합칠 때의 변경 목록」 밖의 변경 없이 들어 있다(스크립트 대조)
- [x] 새 문서 §19.4 의 스크립트를 꺼내 저장소 루트에서 돌린 결과가 §13.2(60행) · §13.3(12행) 표와 같고 「대조 §3 신호 수: … 같음」이 찍힌다
- [x] 이 매매법의 코드 · 전용 테스트 셋 · 산출물 폴더 · `docs/검증/하락_단계_매수/` 가 지워졌고 빈 폴더 `docs/검증/` · `storage/results/검증/` 도 없다
- [x] `loader.py` · `tests/test_output_contract.py` · `tests/test_layer_contracts.py` · `tests/test_execution_trade_rows.py` · `src/verify_lab/report/constants.py` · `docs/COMMANDS.md` · `scripts/CLAUDE.md` · `storage/market/quant_data_files.txt` 의 `git diff 3423368` 이 비었고, `tests/test_data_loader.py` 는 되살린 테스트 하나만, `src/verify_lab/CLAUDE.md` 는 K1 ~ K6 과 결정 2b 의 근거 문단만 남는다 (2026-11-17 12:26 사용자 승인으로 문구 수정 — 진행 로그)
- [x] 매니페스트의 diff 가 끝의 두 항목 삭제뿐이고, 중간선거_사이클 · 반감기_사이클을 인자 없이 다시 돌린 뒤 `git diff --stat storage/results/` 가 `검증/하락_단계_매수/` 삭제뿐이다
- [x] `git grep --untracked -l -E "drawdown_tiers|하락_단계_매수"` 가 정확히 {`docs/조사/하락_단계_매수.md` · `docs/INDEX.md` · `src/verify_lab/tracks.py` · `docs/DEFERRED_FINDINGS.md` · `docs/plans/` 아래 파일}이다
- [x] 회귀/신규 테스트 정리 — 이 매매법의 계약 테스트 자리를 `3423368` 상태로 되돌렸다(추가 테스트 없음 — 지우는 작업)
- [x] 코드 리뷰 실행 및 결과 기록 (마지막 Phase 의 Validation 에 적는다)
- [x] 품질 검증 통과 (마지막 Phase 의 Validation 에 passed/failed/skipped 수를 적는다)
- [x] 자동 포맷 적용 완료 (마지막 Phase에서 실행)
- [x] 필요한 문서 업데이트 — `docs/INDEX.md` 변경 · `docs/COMMANDS.md` 변경(「하락_단계_매수」 절 · 다시 돌리는 순서의 줄 삭제) · `scripts/CLAUDE.md` 변경 · `src/verify_lab/CLAUDE.md` 변경 · `docs/DEFERRED_FINDINGS.md` 변경 · 루트 `CLAUDE.md` 변경 없음 · `tests/CLAUDE.md` 변경 없음
- [x] 근거 승격 완료 — 이 계획서를 지금 삭제해도 잃을 정보가 없다 (사용자 결정 2a · 3 의 근거를 새 문서 §19.2 · §19.3 에, 결정 1 은 INDEX, 결정 4 는 새 문서 재실행 기록, 결정 5 는 DEFERRED_FINDINGS 에)
- [x] 미룬 지적 옮김 (해당 없음 — 고치지 않은 지적은 전부 거름, 기준 번호는 진행 로그 · Done 보고 표. 결정 5 로 기존 항목은 고쳐 씀) — 고치지 않은 리뷰 지적을 거르는 기준으로 걸러 `docs/DEFERRED_FINDINGS.md` 로 옮겼다. 계획서 없이 읽히게 썼다.
      거른 지적은 진행 로그에 기준 번호와 함께 남기고 Done 보고에 표로 냈다
      이 계획서가 그 파일의 항목을 고쳤다면 그 항목을 지웠다
- [x] plan 체크박스 최신화(Phase/DoD/Validation 모두 반영)

## 5) 변경 범위(Scope)

### 변경 대상 파일(예상)

- 새로 만듦: `docs/조사/하락_단계_매수.md`
- 지움: `src/verify_lab/studies/drawdown_tiers/`(5개 + `__pycache__`) · `scripts/run_drawdown_tiers.py` · `tests/test_studies_drawdown_tiers_runner.py` · `tests/test_studies_drawdown_tiers_tiers.py` · `tests/test_studies_drawdown_tiers_trading.py` · `storage/results/검증/하락_단계_매수/`(7개) · `docs/검증/하락_단계_매수/`(3개) · `storage/market/^VIX_raw.csv` · `storage/market/fear_greed_daily.csv` · 빈 폴더 `docs/검증/` · `storage/results/검증/`
- 고침(코드): `src/verify_lab/tracks.py`(줄 · 주석) · `src/verify_lab/data/loader.py`(키워드) · `src/verify_lab/report/constants.py`(주석)
- 고침(테스트): `tests/test_data_loader.py`(셋 삭제) · `tests/test_output_contract.py`(import · 축 상수 · `METHOD_SPECS` · `_outputs` 반환 타입 · 픽스처 · 합성 입력 · `TestPriceBasis` 줄) · `tests/test_layer_contracts.py`(slug 집합 · 경로 목록) · `tests/test_execution_trade_rows.py`(docstring)
- 고침(문서): `docs/INDEX.md`(행) · `docs/COMMANDS.md` · `scripts/CLAUDE.md`(표 행) · `src/verify_lab/CLAUDE.md`(이 매매법 구절) · `docs/DEFERRED_FINDINGS.md`(결정 5)
- 고침(사본 · quant-data 내보내기): `storage/market/quant_data_files.txt` · `storage/market/quant_data_manifest.json`
- `docs/COMMANDS.md`: 변경 있음 — 「하락_단계_매수」 절과 「시세를 다시 받은 뒤 다시 돌리는 순서」의 `run_drawdown_tiers.py` 줄 삭제(실행 명령어가 사라짐)

### 데이터/결과 영향

- 산출물: `storage/results/검증/하락_단계_매수/` 삭제 외에 바이트 변화 0 이어야 한다(중간선거_사이클 · 반감기_사이클 재실행으로 확인)
- 사본: 남길 9개는 바이트 그대로(재내보내기가 같은 원본을 복사), 매니페스트는 두 항목 삭제
- 판정 · 성적 · 출력 스키마 변화 없음

## 6) 단계별 계획(Phases)

### Phase 1 — 새 조사 문서 작성 (코드는 그대로)

**작업 내용**:

- [x] 이웃을 연다 — `.claude/rules/research.md` 가 한 장짜리 조사의 실물 예시로 든 `docs/조사/레버리지_ETF_괴리.md` 의 장 구성(설계 장의 자리 · 머리말 · 관련 파일)을 `Read` 로 열어 새 문서와 맞춘다
- [x] 원문 세 문서를 장 단위로 잘라 위 「장 구성」 순서로 이어 붙이는 스크립트를 scratchpad 에 쓰고 돌려 초안을 만든다 — 본문을 손으로 다시 타이핑하지 않는다. 코드블록 안의 `#` 을 제목으로 자르지 않게 한다(전역 도구 함정 §9)
- [x] E1 ~ E11 을 `Edit` 으로 적용한다
- [x] `docs/INDEX.md` 의 하락_단계_매수 행 문서 칸에 새 문서 링크를 **더한다**(옛 링크는 Phase 2 에서 걷는다 — `tests/test_index.py` 의 등록 검사)

**Validation**:

- [x] 변경 대조 — 옮긴 장마다 원문 장에 E7 의 § 재매핑만 기계적으로 적용한 것과 새 문서 장을 `difflib` 로 비교해, 남은 다른 줄이 전부 E1 ~ E11 중 하나에 해당한다(목록과 건수를 진행 로그에)
- [x] 숫자 대조 — 원문 본문(머리말 · 관련 파일 · 목차 제외)의 숫자 토큰 다중집합이 새 문서에 모두 같은 수 이상 있다(§ 번호 · 결정 번호의 숫자는 제외). 새 머리말의 데이터 기간 · 판정 기간 · 가격 기준이 결과 머리말과 글자 그대로 같다
- [x] 표 행 수 — 옮긴 표마다 행 수가 원문과 같다(§4 용어 정의만 +1)
- [x] §13 스크래치 재현 — §19.4 의 코드 블록을 scratchpad 로 꺼내 저장소 루트에서 `env -u VIRTUAL_ENV poetry run python -I <파일> <scratchpad 출력 폴더>` → 「같음」이 찍히고, `btd_scratch_summary.csv` 60행이 §13.2 표 60행과 · `btd_scratch_episodes.csv` 의 S −10 · d 10 행이 §13.3 표 12행과 셀 단위로 같다(스크립트 대조, 다른 셀 0)
- [x] 남은 원문 가리킴 — 새 문서 안에서 이 매매법의 `설계.md` · `결과.md` · `사전조사.md` 를 가리키는 곳이 「관련 파일」 묘비 · §19 밖에서 0건(다른 매매법의 `설계.md` 결정 인용은 대상 아님)
- [x] `env -u VIRTUAL_ENV poetry run pytest tests/test_index.py tests/test_research_docs.py` 통과

---

### Phase 2 — 코드 · 테스트 · 원문 삭제와 공유 계층 되돌리기 (그린 유지)

**작업 내용**:

- [x] 시작 전 기준점 — `git status --short storage/results/` 가 비어 있고, `git log -1` 의 HEAD 를 「삭제 직전 HEAD」로 정해 그 커밋에 지울 경로가 전부 있는지 `git cat-file -e` 로 확인한다(지금은 `4efd7fb`). 새 문서의 커밋 표기를 그 값으로 맞춘다(DEFERRED 는 Phase 4 에서 같은 값을 쓴다)
- [x] 지운다 — `src/verify_lab/studies/drawdown_tiers/` · `scripts/run_drawdown_tiers.py` · 전용 테스트 셋 · `storage/results/검증/하락_단계_매수/` · `docs/검증/하락_단계_매수/`, 그리고 빈 폴더 `docs/검증/` · `storage/results/검증/`
- [x] `docs/INDEX.md` — 행을 `| 하락_단계_매수 | \`drawdown_tiers\` | 없음 | [하락_단계_매수.md](조사/하락_단계_매수.md) | 우위 없음 |` 로(자리는 그대로)
- [x] `src/verify_lab/tracks.py` — `GRADE_SURVEY` · `KIND_PROPERTY` 로, 주석을 「조사로 내림 · 실행 코드 없음 · 근거와 되살리는 절차는 `docs/조사/하락_단계_매수.md` 「재현 방법」」의 간결체 두 줄로(자리는 그대로)
- [x] `src/verify_lab/data/loader.py` — `load_close_series` 의 키워드 · docstring 을 `3423368` 상태로. `tests/test_data_loader.py` 의 `:788` · `:804` · `:824` 셋을 지운다
- [x] `tests/test_output_contract.py` · `tests/test_layer_contracts.py` · `tests/test_execution_trade_rows.py` · `src/verify_lab/report/constants.py` — 이 매매법 자리를 `3423368` 상태로(`Edit` 으로 지우고 diff 로 확인 — `git checkout` · `git restore` 는 쓰지 않는다)

**Validation**:

- [x] `git diff 3423368 -- src/verify_lab/data/loader.py tests/test_data_loader.py tests/test_output_contract.py tests/test_layer_contracts.py tests/test_execution_trade_rows.py src/verify_lab/report/constants.py` 가 비었다
- [x] `git grep -n -E "studies\.drawdown_tiers|run_drawdown_tiers|test_studies_drawdown_tiers"` 가 `.py` 에서 0건
- [x] `env -u VIRTUAL_ENV poetry run pytest tests/test_data_loader.py tests/test_output_contract.py tests/test_layer_contracts.py tests/test_execution_trade_rows.py tests/test_execution_periods.py tests/test_tracks.py tests/test_index.py tests/test_research_docs.py` 통과(전체 품질 검증은 마지막 Phase)

---

### Phase 3 — 사본 정리(갱신 없는 재내보내기)와 남은 매매법 재실행

**작업 내용**:

- [x] 사전 확인 — quant-data HEAD 가 `ff3306d` · `git status --porcelain` 비어 있음 · 남길 9개가 원본과 `cmp` 같음. 하나라도 다르면 멈추고 보고한다
- [x] `storage/market/quant_data_files.txt` — 두 줄을 빼고 주석을 `3423368` 의 「두 매매법이 읽는 것만 받는다 — …」로
- [x] 🔴 **실행 승인을 받는다** — 다른 저장소의 스크립트가 이 저장소의 사본 · 매니페스트를 바꾸는 실행이다
- [x] quant-data 에서 `python3 scripts/export.py --to ../verify-lab/storage/market` (갱신은 돌리지 않는다) → `storage/market/^VIX_raw.csv` · `fear_greed_daily.csv` 를 지운다
- [x] 중간선거_사이클 · 반감기_사이클을 인자 없이 다시 돌린다(`docs/COMMANDS.md` 「시세를 다시 받은 뒤 다시 돌리는 순서」 — 하락_단계_매수 줄은 Phase 4 에서 지우므로 두 줄만)

**Validation**:

- [x] `git status --short storage/market` 이 목록 · 매니페스트 수정과 CSV 둘 삭제뿐이고, 매니페스트 diff 가 끝의 두 항목 삭제뿐이다(커밋 · 커밋 안 된 변경 · 기준일 그대로)
- [x] `git diff 3423368 -- storage/market/quant_data_files.txt` 가 비었다
- [x] `git diff --stat storage/results/` 가 `검증/하락_단계_매수/` 의 7개 삭제뿐이다

---

### Phase 4 — 문서 · 주석 참조 정리 (그린 유지)

**작업 내용**:

- [x] `docs/COMMANDS.md` — 「하락_단계_매수」 절과 다시 돌리는 순서의 줄을 지운다
- [x] `scripts/CLAUDE.md` — 메타 타입 표의 `drawdown_tiers` 행을 지운다
- [x] `src/verify_lab/CLAUDE.md` — 이 매매법을 말하는 구절 16곳을 `3423368` 의 문장으로 되돌리되 K1 ~ K6 은 남긴다
- [x] `docs/DEFERRED_FINDINGS.md` — 결정 5: 「같은 모양의 다른 자리」의 첫 줄(`drawdown_tiers/runner.py` 신호내역)을 지우고, 둘째 줄(`trade_rows.py`)의 수치를 「중간선거_사이클 58행 중 0 · 반감기_사이클 783행 중 0 — 조사로 내린 하락_단계_매수의 마지막 산출물(커밋 `<삭제 직전 HEAD>` 의 `거래내역.csv`)에서 6,528행 중 9행」으로, 「신호내역만 고치면 …」 문장은 지운다. 예시 한 행이 필요하면 그 커밋의 `거래내역.csv` 에서 도구로 뽑는다. 「종류」의 행 수도 맞춘다

**Validation**:

- [x] `git diff 3423368 -- docs/COMMANDS.md scripts/CLAUDE.md` 가 비었다
- [x] `git diff 3423368 -- src/verify_lab/CLAUDE.md` 가 K1 ~ K6 과 결정 2b 의 근거 문단만 보인다 (근거 문단은 리뷰 1회차 뒤 근거 승격 — 2026-11-17 12:26 사용자 승인으로 문구 수정)
- [x] `git grep --untracked -l -E "drawdown_tiers|하락_단계_매수"` 가 DoD 의 남길 목록과 정확히 같다
- [x] 지운 정의 이름(`VIX_MAX_DAILY_CHANGE_RATE` · `load_indicators` · `tier_signals` · `entry_returns` · `IndicatorFiles` · `run_drawdown_tiers_trading`) grep 이 새 문서(§14 · §15 · §19 의 기록)와 `docs/plans/` 밖에서 0건

---

### 마지막 Phase — 문서 정리 및 최종 검증

**작업 내용**

> 🔴 **체크박스와 상태를 먼저 확정하고, `/commit` 은 맨 마지막에** — 이유는 `/impl-plan` 「5) Commit Messages」.

- [x] 필요한 문서 업데이트 (`docs/COMMANDS.md` 변경 있음 — Phase 4)
- [x] 자동 포맷 적용 (`poetry run black .`)
- [x] 변경 기능 및 전체 플로우 최종 검증
- [x] Validation 절에 `/code-review` 와 품질 검증 **실행 결과**를 적는다
- [x] DoD 체크리스트 최종 업데이트 및 체크 완료
- [x] 전체 Phase 체크리스트 최종 업데이트 및 상태 확정
- [x] 🔴 **마지막에 `/commit` 을 실행하고 그 후보를 «이 계획서» 의 `#### Commit Messages` 절에 옮긴다** —
      대화에만 내면 그 절이 빈 채로 남는다. **커밋은 사용자가 한다 — 후보만 낸다**

**Validation**:

> 순서는 `/code-review` → 품질 검증이다. 고칠 것 · 회차 상한 · 수정분 검증은 `/impl-plan` 의 `review.md` 가 정한다.

- [x] `/code-review xhigh` **1회차** (발견 8건 — 버그 2 [무거움 1 · 가벼움 1] · 그 외 6 · 조치: 무거움 1 수정(§19.1 ⑤) · 가벼움 1 은 그때의 기록이라 두고 거름 기준 2 · 그 외 중 ② 는 근거 승격으로 계층 문서에 한 문장)
- [x] `/code-review xhigh` **2회차** (발견 9건 — 버그 2 [무거움 2 · 가벼움 0] · 사용자 결정 1 · 그 외 6 · 조치: 무거움 2 수정(§19.1 ③ · §19.3 · §19.4 — 같은 모양) · ④ 지운 셋째 테스트는 결정 2a 의 근거가 틀려 사용자에게 올림)
- [x] 수정분 검증 (수정 2건(hunk 셋) · 발견 6건 — 무거움 1 · 조치: 멈추고 사용자 선택 → 「다시 고치고 한 번 더」(2026-11-17 12:26))
- [x] 수정분 검증 2차 (수정 hunk 9 — 무거움 1 · 가벼움 5 · 결정 2a 테스트 · 그 외 둘 · 발견 8건 — 무거움 0 · 조치: 고치지 않음 — 거름 기준 1 · 3, 진행 로그)
- [x] `poetry run python validate_project.py` (passed=1044, failed=0, skipped=0)

#### Commit Messages (Final candidates) — 5개 중 1개 선택

> **Done 직전에 `/commit` 을 실행해 이 절을 채운다. 그전에는 비워 둔다** — 추측으로 적은 줄은 그대로 나간다.

1. 검증 / 하락_단계_매수 조사 등급 이관과 실행 코드 삭제
2. 검증 / 하락_단계_매수 세 문서의 조사 한 장 통합과 코드 · 산출물 · VIX · 공포탐욕지수 사본 삭제
3. 검증 / 우위 없는 하락_단계_매수의 조사 강등 — 로더 VIX 임계 키워드 제거와 남은 매매법 산출물 바이트 불변 확인
4. 검증 / 하락_단계_매수 조사 이관 — 이벤트 스터디 격자 · 비용 차감 전 성적 용어 반영과 되살리는 절차 정리
5. 검증 / 하락_단계_매수 코드 삭제에 따른 공유 계층 · 계약 테스트 원복과 종가 계열 공용 임계 테스트 복원

## 7) 리스크(Risks)

- **합치며 글이 조용히 빠지거나 숫자가 바뀐다** — 초안을 스크립트로 만들고, Phase 1 의 변경 대조 · 숫자 대조 · 표 행 수로 E1 ~ E11 밖의 변경을 0 으로 확인한다
- **재내보내기 시점에 quant-data 상태가 바뀌어 있다**(갱신 · 커밋 안 된 변경) — 그러면 다른 사본 · 매니페스트가 함께 바뀌어 모든 매매법을 다시 돌려야 하는 원래 지시서의 경우가 된다. 사전 확인에서 하나라도 어긋나면 멈추고 묻는다
- **내보내기가 남는 CSV 를 지우지 않는다** — 손으로 지우지 않으면 매니페스트에 없는 사본이 폴더에 남는다. Phase 3 Validation 의 `git status` 로 잡는다
- **공유 계층 되돌리기가 다른 매매법을 건드린다** — `loader.py` 는 `46f081e` 뒤 바뀐 적이 없어 되돌린 결과가 `3423368` 판과 같다. 재실행 바이트 대조가 최종 확인이다
- **`src/verify_lab/CLAUDE.md` 를 `3423368` 으로 되돌리며 이 매매법 밖의 정정(K1 ~ K6)까지 되돌린다** — diff 대조가 K1 ~ K6 을 «남아 있는 것»으로도 확인한다
- **삭제 직전 HEAD 가 `4efd7fb` 에서 바뀐다**(사용자가 그사이 커밋) — Phase 2 시작에 `git log -1` 로 다시 정하고 지울 경로가 전부 있는지 확인한다
- **quant-data 문서의 죽는 경로** — 이 계획서 밖(Non-Goals). Done 보고에 올린다

## 8) 메모(Notes)

- 지시서: 사용자가 붙여 넣은 지시(2026-11-17) — 결정 출처는 설계 Q14 와 위 「사용자 결정」 표
- 빈 폴더 둘을 지우는 근거: 검증 등급의 줄이 이 매매법 하나라 지우면 비고, 둘 다 `46f081e` 전에는 없던 폴더다. 검사 0곳 — `tests/test_research_docs.py` 는 없는 폴더를 빈 목록으로 읽고 `test_세_등급이_모두_쓰인다` 는 검증 등급을 요구하지 않는다
- `tests/test_index.py` 의 `REMOVED_DOCUMENTS` 에는 넣지 않는다 — 역방향 선례도 옛 문서 경로를 넣지 않았다

### 진행 로그 (KST)

- 2026-11-17 11:11: 계획서 작성. 질문 라운드(INDEX 상태 · 공유 계층 · 사본 · 용어 · DEFERRED) 답 「추천대로 진행」 반영
- 2026-11-17 11:11: 자체 검증 — 1회차(지시서 · 순서 · 그린 유지) 개선 0 · 2회차(다른 로직 영향 — 로더 · 내보내기 · 재실행 원인 분리) 개선 0 · 3회차(새 파일 규약) 개선 1(이웃 문서 열기) · 4회차(Phase 간 정합) 개선 1(DEFERRED 커밋 표기는 Phase 4) · 5회차(검사식의 오탐) 개선 1(원문 가리킴 검사를 이 매매법 문서로 한정) · 6 ~ 8회차 개선 0 → 멈춤
- 2026-11-17 11:29: **Phase 1 완료.** 이웃 `docs/조사/레버리지_ETF_괴리.md` 를 열어 맞춤(머리말에 합친 사실과 옛 § 대응 · 설계 장은 해석 앞). 합치기 스크립트(scratchpad `merge_doc.py`)로 초안 생성 — E1 ~ E11 의 바꿈마다 「정확히 한 번」 검사. 스크립트에 이모지를 넣는 것을 훅이 막아(코드 파일) §19 의 경고 표시 둘은 문서에 `Edit` 으로 더함. E7 에 붙여 §3 의 「설계 §15.1」(원문 「설계 `설계.md` §3.1」을 옮긴 모양)을 「§15.1」로. 대조(scratchpad `verify_merge.py`): 정규화 뒤 다른 줄 35 — 전부 E 목록(재실행 기록 행 1 · §3 「설계」 2 · §4 행 1 · §9 커밋 2 · §2 구성 · 용어 7 · §14 머리 인용 2 · §16 머리와 제목 단계 20), 스크립트 다른 줄은 주석 1. 숫자 대조 — 제목 줄을 뺀 원문 숫자 토큰 3,680개가 모두 새 문서에 같은 수 이상(제목 줄을 넣으면 옮긴 제목 번호 3.1 ~ 3.8 · 2.1 ~ 2.4 만 모자람). 머리말의 데이터 기간 · 판정 기간 · 가격 기준 · 미리보기 수 줄이 원문과 글자 그대로. 표 행 수 — 재실행 기록 · §4 만 +1, 나머지 같음. §19.4 스크립트를 꺼내 저장소 루트에서 돌림 → 「대조 §3 신호 수: … 같음」 · 660 · 60행, §13.2 60행 · §13.3 12행 셀 대조 다른 행 0. 원문 문서 이름은 관련 파일 묘비 · §19.3 의 `git show` 만. `pytest tests/test_index.py tests/test_research_docs.py` 123 passed. 결과 §2 에서 뺀 것: 첫 문단(설계 §1 과 같은 질문) · 「분할 · 비중 · 청산 · 손절은 아직 정하지 않았다」(Q14 문장이 대신함). §19.3 의 「갱신 없이 다시 내보내 남은 사본 9개는 바이트 그대로 · 매니페스트 두 항목만」은 Phase 3 에서 확인한다
- 2026-11-17 11:31: **Phase 2 완료.** 기준점 — `git status --short storage/results/` 비어 있음 · HEAD `4efd7fb` 그대로 · 지울 경로 21개가 그 커밋에 전부 있음(`git cat-file -e`) → 새 문서의 커밋 표기는 그대로. 지움: 패키지 5개 + `__pycache__` · 스크립트 · 전용 테스트 셋 · 산출물 7개 · 원문 세 문서 · 빈 폴더 `docs/검증/` · `storage/results/검증/`. INDEX 행을 「없음 · 새 문서 하나 · 우위 없음」으로. `tracks.py` 를 조사 · 성질 조사로(주석 간결체 두 줄). 로더 키워드와 테스트 셋 · 계약 테스트 셋 · `report/constants.py` 주석을 `Edit` 으로 되돌림 → `git diff 3423368` 이 여섯 파일 모두 비었음. `.py` 의 지운 모듈 참조 0건. Ruff(`tracks.py` · `loader.py`) 통과. `pytest`(바뀐 테스트 넷 + `test_execution_periods` · `test_tracks` · `test_index` · `test_research_docs`) 364 passed
- 2026-11-17 11:35: **Phase 3 완료.** 사전 확인 — quant-data HEAD `ff3306d` · `git status --porcelain` 비어 있음 · 남길 9개 `cmp` 같음. 목록을 고침(`git diff 3423368` 비었음). 실행 승인(사용자 「실행」) 뒤 quant-data 에서 `python3 scripts/export.py --to ../verify-lab/storage/market` → 「9개 복사 · 데이터 저장소 커밋 ff3306d…」 종료 코드 0. CSV 둘 삭제. `git status --short storage/market` = 목록 M · 매니페스트 M · CSV 둘 D 뿐(사본 9개 변화 없음), 매니페스트 diff 는 끝의 두 항목 삭제뿐. 중간선거_사이클 · 반감기_사이클을 인자 없이 다시 돌림(둘 다 종료 0) → `git diff --stat storage/results/` 는 `검증/하락_단계_매수/` 7개 삭제뿐. 코드를 지운 뒤 §19.4 스크래치를 다시 돌려 「같음」 · Phase 1 출력과 두 CSV 바이트 같음 — 새 문서 §19.3 · §19.4 의 서술이 실측과 맞음
- 2026-11-17 11:37: **Phase 4 완료.** `docs/COMMANDS.md`(절 · 다시 돌리는 순서의 줄) · `scripts/CLAUDE.md`(메타 타입 행) → `git diff 3423368` 비었음. `src/verify_lab/CLAUDE.md` 13곳을 `Edit` → 이 매매법 언급 0, `git diff 3423368` 이 K1 ~ K6 만 남김. **K6 문장은 계획서 문안에서 근거만 바꿈** — 계획서는 「달력형 둘을 각자의 패키지에 두는 것과 같은 이유」였으나 그 이유는 「모양이 달라서」라 하나만 남은 지금 맞지 않아 「쓰는 매매법이 하나라 … (위 「원칙에 없는 것은 「세 번째가 올 때」 정합니다」)」로 씀. `docs/DEFERRED_FINDINGS.md` — 신호내역 줄 삭제, `trade_rows` 줄의 수치를 도구로 다시 세어 옮김(지금 중간선거 58행 중 0 · 반감기 783행 중 0 · 커밋 `4efd7fb` 의 하락_단계_매수 거래내역 6,528행 중 9행 — 예시 SPY VIX 25 이상 126거래일 판정일 1997-09-04 는 거래내역에서 뽑음), 「종류」의 행 수를 「덧붙인 자리는 지금 0행」으로. `git grep --untracked -l` = 새 문서 · INDEX · tracks.py · DEFERRED_FINDINGS · `docs/plans/` 둘 — 남길 목록과 같음. 지운 정의 이름은 새 문서 §14 D3 · §15.1 · §19.2 의 기록에만
- 2026-11-17 11:46: 정정 — 위 Phase 4 로그의 「`src/verify_lab/CLAUDE.md` 13곳」은 **14곳**(Edit 14번 · grep 으로 센 줄은 16 — 135 ~ 136 과 662 ~ 665 를 한 번씩 고침). 자동 포맷 `poetry run black .` — 92 files left unchanged
- 2026-11-17 11:46: `/code-review xhigh` **1회차** — 발견 8: ① §19.1 ⑤ 「공유 계층을 옛 모양으로 되돌리지 않는다」가 ② · §19.2 와 부딪힘(글자대로 따르면 되살린 VIX 읽기가 공용 임계에 막혀 멈춤) — 버그 · 무거움(죽는다) · 고침. ⑦ §19.4 스크립트가 출력 폴더를 만들지 않음 — 버그 · 가벼움 · 고치지 않음: `4efd7fb` 결과.md §16 의 전문을 그대로 옮긴 기록(diff 밖 기존 코드)이고, 거름 기준 2(폴더가 없으면 `OSError` 로 멈출 뿐 틀린 값을 내지 않는다)로 미룬 지적에도 옮기지 않음. 그 외 6(고치지 않음 · 거름 기준 3): ② 계층 문서가 두 매매법만 남은 공유 이름을 설명하지 않음(→ 근거 승격으로 처리, 아래) · ③ quant-data 의 죽는 경로와 계속 받는 두 자료(Non-Goals — Done 보고) · ④ §14 Q1 · D3 · D12 가 지금 상태와 다르게 읽힘(확정된 설계 결정은 그때의 기록 — 과거형 허용 자리) · ⑤ 머리말의 산출물 줄이 관련 파일과 겹침(커밋에 고정된 경로라 낡지 않음 — 선례 역방향 머리말도 같은 모양) · ⑥ DEFERRED 출처 줄의 「신호내역」(그 리뷰가 찾은 것의 기록) · ⑧ 계획서 K6 문안 · 곳 수(계획서 자신). 수정: ① — 같은 모양(재현 절차가 지운 공유 정의를 되살리라면서 옛 모양 복원을 금함)을 diff 에서 찾음 → 1곳. 근거 승격: `src/verify_lab/CLAUDE.md` 「세 번째가 올 때」 문단에 「올린 뒤 쓰는 매매법이 둘로 줄어도 내리지 않습니다 (2026-11-17 사용자 결정)」 — 결정 2b 의 근거
- 2026-11-17 11:58: `/code-review xhigh` **2회차(상한)** — 발견 9: ① §19.1 ③ · §19.3 「그때의 사본으로 재현만」이 VIX · 공포탐욕지수 둘만 `4efd7fb` 에서 꺼내고 나머지 넷은 지금 사본을 쓰게 해, 다시 내보낸 뒤에는 기간이 섞인 수치가 예외 없이 나오는데 「머리말의 기간과 같다」고 함 — 버그 · 무거움(위험한 쪽) · 닿음(계기: 재수집) · 고침. ③ §19.4 「같음」이 신호 수만 보는데 사본이 바뀐 것을 가리는 것처럼 읽힘 — 같은 모양(재현 절차가 사본이 그 커밋의 것인지 가리지 못한 채 「같다」고 말함) · 버그 · 무거움 · 고침(스크립트는 그때의 기록이라 두고 안내 문장만). ④ 지운 셋째 테스트 `test_close_series_default_threshold_rejects_a_large_move` 를 `test_close_series_applies_market_checks` 가 대신한다는 계획서 근거가 틀림(그 테스트는 「0 이하」만 봄 — 공용 급등락 임계를 거는지는 이제 아무 테스트도 고정하지 않음) — 사용자 결정 2a 의 근거가 틀렸으므로 고치지 않고 사용자에게 올림. 그 외 6(고치지 않음 · 거름 기준 3): ② quant-data 쪽(1회차 ③ 과 같음 — Done 보고) · ⑤ §19.4 스크립트가 로더 검사를 거치지 않음(그때의 기록 · quant-data 판정이 막는 입력이라 닿지 않음 — 기준 1) · ⑥ 결정 2b 문장이 예로 측정 표 칸만 들고 `trade_rows` 를 빼먹음(지금 `trade_rows` 를 import 하는 곳도 중간선거 · 반감기 둘 — 서술 누락) · ⑦ §19.1 ④ 의 되살릴 자리에 `report/constants.py` 주석이 빠짐 · ⑧ DoD · Phase 4 의 「K1 ~ K6 만」이 근거 승격 문단 뒤로 맞지 않음(계획서 자신 — 고치려면 사용자 승인) · ⑨ §5 · §8 · §10 ~ §12 의 산출물 언급에 커밋이 없음(머리말 산출물 줄이 함께 안내). 수정 전 사본: scratchpad `survey_before_round2.md`, 수정분 `round2_fix.diff`(hunk 셋)
- 2026-11-17 11:58: 품질 검증 `poetry run python validate_project.py` — Ruff 통과 · PyRight 통과 · Pytest passed=1043, failed=0, skipped=0. 수정분 검증(서브에이전트)을 기다리는 중
- 2026-11-17 12:06: 수정분 검증(맥락 없는 서브에이전트 — 수정분 diff 와 겨냥한 지적 둘만 줌) — 발견 6 · 무거움 1: §19.3 의 「`git worktree add <폴더> 4efd7fb` … 옮겨 붙일 것이 없다」는 실행 환경을 빠뜨림 — `poetry.toml` 이 `in-project = true` 라 worktree 에 `.venv` 가 없고, 메인 `.venv` 의 `verify_lab.pth` 가 `/Users/yubeen/Workspace/verify-lab/src` 를 가리켜(직접 확인) 적힌 대로는 `ModuleNotFoundError` 로 멈추며, 자연스러운 대응인 같은 셸의 `poetry install` 은 메인 `.venv` 를 worktree 의 `src` 로 돌려 메인 트리가 에러 없이 옛 코드로 돈다. 가벼움 5: ③ 「여섯을 모두 그 커밋의 것으로」가 어디서 하는지 말하지 않음 · 「다시 내보냈으면 기간이 다르다」는 늘 참이 아님 · §19.3 「새 사본으로 … 바뀐다」의 장 목록이 §1 · §12 · §13 · §15 를 빠뜨림 · §19.4 「기간이 다르면 다르다」는 「다를 수 있다」가 맞음(실측: SPY 끝 2행을 잘라도 §13.2 CSV 는 바이트 같음) · §19.4 의 되돌림 안내가 암묵적. 규칙대로 고치지 않고 멈춤 — 사용자 선택 대기
- 2026-11-17 12:07: 상태를 「사용자 결정 대기」로 — `/impl-plan` `review.md` 대로 멈추고 사용자에게 네 가지(수정분 검증의 무거움 처리 · 지운 셋째 테스트 · DoD 문구 · 그 외 둘)를 물음. 커밋 후보는 답을 받아 diff 가 확정된 뒤 `/commit` 으로 만든다
- 2026-11-17 12:26: 사용자 답 「추천대로」 — ① 수정분 검증의 무거움 1 · 가벼움 5 를 다시 고치고 수정분 검증을 한 번 더 ② 지운 셋째 테스트를 docstring 만 고쳐 되살림(결정 2a 의 그 부분을 거둠) ③ DoD · Phase 4 의 「K1 ~ K6 만」 문구 수정 승인 ④ 그 외 중 사실이 틀린 둘(결정 2b 문장의 `trade_rows` · §19.1 ④ 의 `report/constants.py`)을 함께 고침. 수정 전 사본: scratchpad `before_fix3/`(새 문서 · 계층 문서 · `test_data_loader.py`)
- 2026-11-17 12:40: 셋째 수정 — 새 문서: §19 머리 · 머리말 7행에 「머리말의 SPY 사본일 때」(가벼움) · §19.1 ③ 을 「지금 트리에 되살려 지금 사본으로 다시 재는 길」로 하고 재현만은 §19.3 으로, 옛 사본을 지금 트리에 꺼내지 말 것(가벼움) · §19.1 ④ 에 `report/constants.py` 주석(그 외 ⑦) · §19.2 와 관련 파일 행을 「키워드를 넘기던 테스트 둘」로 · §19.3 재현만을 「저장소 밖 폴더 + `env -u VIRTUAL_ENV poetry install` + 같은 접두로 실행 + `git worktree remove --force`」와 그 이유로(무거움) · 바뀌는 장 목록에 §1 · §12 · §15.1 · §15.6 · §13(가벼움) · §19.4 「다를 수 있다」와 `git diff --quiet 4efd7fb -- …` 판별 · 꺼낸 폴더에서 같은 명령(가벼움). 계층 문서: 결정 2b 문장에 거래내역 공통 여덟 칸(그 외 ⑥ — `trade_rows` 를 import 하는 곳 중간선거 · 반감기 둘). 테스트: `test_close_series_rejects_a_move_above_the_common_threshold` 로 되살림(키워드를 말하지 않는 이름 · docstring). 변형 확인 — `loader.py:232` 를 `load_market_csv(path, max_daily_change_rate=10.0)` 으로 바꾸고 `PYTHONDONTWRITEBYTECODE=1` 로 돌리자 `FAILED …::test_close_series_rejects_a_move_above_the_common_threshold`(나머지 종가 계열 둘은 통과 — 옛 근거가 틀렸음을 실측), 사본으로 되돌려 `cmp` 같음 · `git diff 3423368 -- loader.py` 비었음. DoD · Phase 4 문구를 승인대로 고침. 품질 검증 다시 — passed=1044, failed=0, skipped=0. 수정분 `fix3.diff`(hunk 9)를 서브에이전트에 맡김
- 2026-11-17 12:40: 수정분 검증 2차(서브에이전트 — `fix3.diff` 와 겨냥한 지적만 줌) — 무거움 0 · 가벼움 8. 그 서브에이전트는 `git archive 4efd7fb` 를 scratchpad 에 풀어 돌려 산출물 7개가 커밋본과 바이트 같음 · §19.4 스크립트 「같음」 · `git diff --quiet 4efd7fb -- storage/market/<파일>` 이 SPY · DIA · QQQ · ^GSPC 에 0 · 되살린 테스트가 임계 10.0 · 로더 우회 · 키워드 기본값 2.0 변형을 잡음을 실측. 규칙대로 고치지 않음. **거른 지적**(미룬 지적으로 옮기지 않음): ① §19.3 「실행이 산출물을 바꿔 `--force` 가 필요하다」는 사실과 다름(재현 실행은 바이트 같음 · 무시 파일만 생김) — 기준 3(서술) ② `git diff --quiet` 의 결과를 종료 상태로 읽으라는 말이 없음 — 기준 3 ③ 「새 사본으로」 바뀌는 장 목록에 §17 · §18 · §15.3 · §3 파일 표가 빠지고 §15.1 · §15.6 은 날짜 박힌 실측이라 덮어쓸 자리가 아님 — 기준 1(지운 코드를 되살려 다시 잴 때만) ④ §19.1 ⑥ 이 아직 기간 · 행 수를 같은 사본의 기준으로 씀 — 기준 3 ⑤ §19.1 ③ 「옛 사본을 지금 트리에 꺼내지 않는다」와 §19.3 「둘만 꺼내는 길」이 문장끼리 갈림 — 기준 3 ⑥ §19.1 ④ 에 `docs/DEFERRED_FINDINGS.md`(지운 신호내역 반올림 항목) 누락 — 기준 1(되살릴 때만) ⑦ 결정 2b 문장이 「단위 목록」을 빠뜨림 — 기준 3 ⑧ 되살린 테스트의 +60% 픽스처가 임계를 0.5 ~ 0.6 으로 넓히는 변경을 못 잡음 — 기준 1(저장소의 임계 상수는 0.50 · 0.75 뿐 · 그 구간의 값을 새로 넣는 변경이어야 함 · 본문은 `4efd7fb` 의 테스트와 같음). 1 · 2회차의 거른 지적은 위 1 · 2회차 로그. 자동 포맷 다시 — 92 files left unchanged. DoD 검사 다시: `3423368` 대비 여덟 파일 diff 비었음 · `test_data_loader.py` 는 되살린 테스트 하나 · 계층 문서 더한 줄 11(K1 ~ K6 + 결정 2b 문단) · `git grep --untracked -l` 이 남길 목록과 같음 · `storage/results/` 변화는 7개 삭제 · 빈 폴더 둘 없음
- 2026-11-17 12:55: Done 뒤 사용자 「제안 진행」 — 거른 지적 중 사실이 틀린 두 곳만 고침(문서): 새 문서 §19.3 의 「실행이 산출물을 바꿔 `--force` 가 필요하다」를 「재현이 맞으면 추적 파일이 안 바뀐다 — 실행 뒤 `git status --short` 가 비는 것이 재현의 확인 · 먼저 `git worktree remove` 하고 남긴 파일로 거부되면 `--force`」로(무시 파일 처리는 git 설명서가 밝히지 않아 단정하지 않음 · 임시 저장소 실측은 허가되지 않아 하지 않음), 계층 문서 결정 2b 문장을 「바로 위에 든 것이 모두 지금 그 상태입니다」로(단위 목록 누락). `pytest tests/test_research_docs.py tests/test_index.py` 116 passed. 커밋 후보는 그대로 맞음(같은 변경 안의 문서 수정). quant-data 쪽 둘은 사용자에게 범위를 물음
