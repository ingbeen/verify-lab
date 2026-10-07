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

- **자리**: `tests/test_report_writer.py:290` — `test_accepts_every_real_track_name` 의
  `writer.VALID_TRACK_NAME.match(name)`. 운영 코드는 `src/verify_lab/report/writer.py:96` 에서 `fullmatch` 로 잰다
- **무엇**: `.match` 는 앞부분만 맞으면 통과하므로, `TRACK_NAME_PATTERN` 을 뒤쪽에서 좁히는 변경을 이 테스트가 잡지 못한다.
  예: 패턴을 `[a-z][a-z_]{0,16}`(17자 상한)으로 바꾸면 `.match` 는 실제 이름 8개(매매법·조사 5 · 프로브 3)를 전부
  통과시키지만 `fullmatch` 는 `usdkrw_equivalence` · `pykrx_splice_probe` 를 거부한다 — `run_usdkrw_equivalence.py` 와
  `check_pykrx_splice.py` 가 결과 폴더를 만들다 `ValueError` 로 멈춘다. 이 파일의 `create_run_directory` 테스트들은
  `leverage_tracking`(17자) · `futures_leverage` · `midterm_cycle` 만 넘겨 이 경우를 잡지 못한다.
  패턴 수준에서만 재현했다(2026-10-07) — 패턴을 실제로 바꿔 전체 테스트를 돌리지는 않았다
- **종류**: 무거운 버그 — 검사가 약하고, 그 검사가 막는 결함이 「정상 이름으로 실행이 멈춘다」(`/impl-plan` review.md
  「버그의 무게」의 「죽는다」)라서 「비켜 간다」로 분류했다. 찾아낸 수정분 검증은 「가벼움」으로 냈다.
  이 계획서의 diff 밖 기존 코드라 고치지 않았다
- **출처**: PLAN_reverse_to_survey (2026-10-06 ~ 10-07) — 리뷰 2회차 수정분 검증
