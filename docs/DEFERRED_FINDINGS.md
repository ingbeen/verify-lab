# DEFERRED_FINDINGS — 미룬 지적

> 코드 리뷰가 낸 지적 중 **계획서가 고치지 않은 것**을 모은다. 이 저장소의 판단 대기열이다.
> 무엇을 어떻게 추려 어떤 모양으로 옮기는지는 전역 `/impl-plan` 스킬 「미룬 지적 옮기기」가 SoT 다.
>
> **이 파일을 처리할 때는 먼저 그 절의 「처리」 순서를 따른다** — 항목마다 지금 코드에서 재현 → 재현 결과와
> 추천을 표로 → **고칠지는 사용자가 고른다.** 테스트를 고치면 `tests/CLAUDE.md` 「테스트 보강」대로 변형해
> 실패를 확인한다. 버린 항목은 바로, 고친 항목은 그 계획서가 Done 될 때 지운다 — 판단 전이거나 고치는 중인 것만 남는다.
>
> 항목은 계획서 없이 읽히게 쓴다. 계획서는 지워지므로 **출처는 이름과 날짜만 평문으로** 적는다.
> 줄 번호는 옮긴 시점의 값이다 — 밀렸으면 함수·테스트 이름으로 다시 찾는다.

---

## 폴더 이름 검사 테스트가 `.match` 라 좁아진 패턴을 못 잡는다

- **자리**: `tests/test_report_writer.py:287` — `test_accepts_every_real_track_name` 의
  `writer.VALID_TRACK_NAME.match(name)`. 운영 코드는 `src/verify_lab/report/writer.py:96` 에서 `fullmatch` 로 잰다
- **무엇**: `.match` 는 앞부분만 맞으면 통과하므로, `TRACK_NAME_PATTERN` 을 뒤쪽에서 좁히는 변경을 이 테스트가 잡지 못한다.
  예: 패턴을 `[a-z][a-z_]{0,16}`(17자 상한)으로 바꾸면 `.match` 는 실제 이름 4개(매매법 2 · 프로브 2)를 전부
  통과시키지만 `fullmatch` 는 `pykrx_splice_probe`(18자)를 거부한다 — `check_pykrx_splice.py` 가 결과 폴더를 만들다
  `ValueError` 로 멈춘다. 이 파일의 `create_run_directory` 테스트들은
  `leverage_tracking`(17자) · `futures_leverage` · `midterm_cycle` 만 넘겨 이 경우를 잡지 못한다.
  패턴 수준에서만 재현했다(2026-10-07) — 패턴을 실제로 바꿔 전체 테스트를 돌리지는 않았다.
  2026-10-17 에 이름 목록이 줄었다(조사 셋의 코드와 ECOS 프로브를 지웠다) — 예시는 지금 이름으로 고쳤고 지적의 판단은 그대로다
- **종류**: 무거운 버그 — 검사가 약하고, 그 검사가 막는 결함이 「정상 이름으로 실행이 멈춘다」(`/impl-plan` review.md
  「버그의 무게」의 「죽는다」)라서 「비켜 간다」로 분류했다. 찾아낸 수정분 검증은 「가벼움」으로 냈다.
  이 계획서의 diff 밖 기존 코드라 고치지 않았다
- **출처**: PLAN_reverse_to_survey (2026-10-06 ~ 10-07) — 리뷰 2회차 수정분 검증

## 문서 자리의 일반 표기 `docs/<등급>/<매매법>/…` 가 「조사는 한 장」을 반영하지 않는다

- **자리**: 루트 `CLAUDE.md:23`(「이 프로젝트가 무엇인가」의 예외 인용 블록 — `docs/<등급>/<매매법>/규칙.md`) ·
  `.claude/rules/session-bootstrap.md:18`(「2. 조건부」 표의 매매 규칙 행) · `.claude/rules/trading.md:200`(「문서 구성」 끝 문단의
  `docs/<등급>/<매매법>/결과.md`) · `.claude/rules/docs.md:48 ~ 50`(「문서의 두 종류」 역할 목록 — 항목 머리는 `{검증,매매}/<매매법>/규칙.md` 인데
  본문이 조사를 말한다) · `src/verify_lab/report/writer.py:66`(`create_run_directory` docstring — `docs/<등급>/<한글 이름>/`) ·
  `tests/test_report_writer.py:56`(`test_directory_name_is_the_korean_label` docstring — `docs/<등급>/<이름>/`)
- **무엇**: 조사는 폴더 없이 한 장 `docs/조사/<이름>.md` 인데(2026-10-16 사용자 결정 — `.claude/rules/docs.md` 「배치는 «등급» 축이다」),
  이 자리들은 문서 자리를 `docs/<등급>/<매매법>/<종류>.md`(폴더형) 하나로만 적는다. 조사에 대입하면 없는 경로(`docs/조사/<이름>/규칙.md`)가 나온다.
  그 표기를 따라 폴더를 만들면 `tests/test_index.py` 의 `test_survey_grade_has_no_folders` 가 막는다 — 잘못 통과시키는 길은 없다
- **종류**: 그 외 — 사용자가 미루기로 함. 리뷰 2회차 수정분 검증은 규칙 문서의 지시라 가벼움으로 냈다
- **출처**: PLAN_survey_single_page (2026-10-16 ~ 10-17) — 리뷰 2회차 수정분 검증

## 「문서와 산출물 폴더가 같은 한글 이름」이 레지스트리 이름 일부에 맞지 않는다

- **자리**: `src/verify_lab/CLAUDE.md:301`(「매매법 이름 계약 — 모든 계층」 표의 「폴더 이름은 slug 가 아니라 한글 이름」 행) ·
  루트 `CLAUDE.md:273`(「디렉토리 구조」 아래 등급 인용 블록). 위 항목의 `writer.py:66` · `test_report_writer.py:56` 도 같은 일반화를 담는다
- **무엇**: 두 자리는 문서와 산출물 폴더가 `src/verify_lab/tracks.py` 의 같은 한글 이름(`label`)을 따른다고 일반화한다. 레지스트리 이름 중
  그 이름의 문서가 없는 것이 있다 — `원달러_그리드`(문서는 `docs/조사/원달러_조달.md` 부록) · `ECOS_실측`(`docs/조사/원달러_ETF_등가성.md` 「재현 방법」) ·
  `pykrx_ETF_실측` · `pykrx_이어붙이기_실측`(문서 없음). 대응은 `docs/INDEX.md` 「매매법·조사」 표가 갖고, `tracks.py` 의 `label` docstring 은
  「문서가 따로 있으면」으로 이미 한정한다
- **종류**: 그 외 — 사용자가 미루기로 함. 리뷰 2회차 수정분 검증은 가벼움으로 냈다
- **출처**: PLAN_survey_single_page (2026-10-16 ~ 10-17) — 리뷰 2회차 수정분 검증

## 과거형 이력 서술과 지금 없는 이름이 주석 · 규칙 문서에 남아 있다

- **자리**: `tests/test_layer_contracts.py:1673 ~ 1675`(`test_최근_구간_제외를_인라인으로_다시_만들지_않는다` docstring — 「`etn`·`krx_futures` 가 …
  복사본을 갖고 … 있었다」) · `tests/test_layer_contracts.py:396`(`_rename_dicts` docstring — 값-사전의 예 `HORIZON_LABELS`·`MODEL_LABELS`·`EXTREME_DIRECTION_LABELS`) ·
  `src/verify_lab/CLAUDE.md:132`(「어디까지가 공통이고 어디부터 그 검증의 것인가」 — 「달력 함수는 지웠고」) ·
  `src/verify_lab/CLAUDE.md:587`(「베이스라인·통계 계약 — measure」 — 「조건부 기준선은 … 역방향과 함께 지웠습니다」)
- **무엇**: 전역 「주석은 코드가 못 하는 말만 한다」의 「적지 않는 것 — 과거 상태 · 변경 이력」과 `.claude/rules/docs.md` 「과거형이 허용되는 자리는 둘뿐입니다」에
  어긋나는 과거형 서술이다. 396 의 세 이름은 지금 `src` 에 없다 — `EXTREME_DIRECTION_LABELS` 는 2026-10-07 에, `HORIZON_LABELS` · `MODEL_LABELS` 는
  2026-10-17 에 조사 셋의 코드와 함께 지웠다. 동작에는 영향이 없다. 1673 ~ 1675 는 그 검사가 있는 이유라 시제만 바꿔 근거로 남길 수 있다
- **종류**: 그 외 — 사용자가 미루기로 함. 396 의 `HORIZON_LABELS` · `MODEL_LABELS` 밖은 PLAN_survey_single_page 의 변경 전부터 있던 서술이다
- **출처**: PLAN_survey_single_page (2026-10-16 ~ 10-17) — 리뷰 2회차 수정분 검증
