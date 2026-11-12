# verify-lab 실행 명령어 레퍼런스

> 이 파일은 verify-lab 실행 명령어의 **단일 SoT(Source of Truth)** 입니다.
> README.md·CLAUDE.md 등 다른 문서에는 실행 명령어를 기재하지 않으며, 필요 시 이 문서를 참조합니다.
> 설치처럼 한 번만 쓰는 일회성 명령어는 기재하지 않습니다. **평상시 반복 실행하는 명령어만** 관리합니다.
>
> **명령과 한 줄 주석만 둡니다.** 인자의 뜻·기본값·저장 위치는 각 스크립트의
> `--help`·모듈 docstring 이, 데이터 소스의 함정은 quant-data 문서가, 산출물을 읽는 법은 그 매매법 결과 문서의 「재현 방법」이 말합니다 —
> 여기에 함께 두면 코드와 두 벌이 되어 어긋납니다 (2026-09-26 사용자 결정).

---

## 품질 검증

```bash
poetry run python validate_project.py                # Ruff + PyRight + Pytest. 통과 기준은 failed=0 skipped=0
poetry run python validate_project.py --only-tests   # --only-lint · --only-pyright 도 같은 모양
poetry run python validate_project.py --cov          # 커버리지 포함
poetry run black .                                   # 포맷 적용 (계획서의 마지막 Phase 에서만)
```

> **`passed` 수는 기준이 아닙니다** — 코드를 지우면 테스트도 함께 줄어듭니다. 판단이 필요하면 직전 실행과 비교하고,
> 지운 코드 없이 줄었을 때가 신호입니다.
>
> **세 항목이 모두 실패하고 `Command not found` 가 보이면** 코드가 아니라 실행 환경입니다. 셸에 남은 `VIRTUAL_ENV` 를
> Poetry 가 프로젝트 `.venv` 보다 우선한 것이고(그 환경에는 개발 의존성이 없다 — `poetry env info --path` 로 확인),
> `env -u VIRTUAL_ENV` 를 붙여 다시 돌면 됩니다.

---

## 데이터 받기

> 시세는 quant-data 가 받고 판정해 내보낸 사본이고, **이 저장소에는 받기 명령이 없습니다** — quant-data 저장소에서
> 그 저장소 `docs/COMMANDS.md` 의 「갱신」 → 「내보내기」를 돌립니다(받는 폴더 `storage/market/`).
>
> - 받을 파일: `storage/market/quant_data_files.txt` (한 줄에 quant-data storage 기준 경로 하나)
> - 받은 버전: `storage/market/quant_data_manifest.json` — quant-data 커밋 · 커밋 안 된 변경 · 기준일 · 파일별 기간
>
> 다시 내보냈으면 아래 「시세를 다시 받은 뒤 다시 돌리는 순서」대로 다시 돌립니다.

---

## 매매법·조사 실행

> **결과 문서에 쓸 수치는 인자 없이 돌린 것이어야 합니다** — 대상을 좁혀 돌리면 같은 산출물 폴더를 덮습니다.

### 중간선거_사이클

```bash
poetry run python scripts/run_midterm_cycle.py                              # 전 대상 (기본값)
poetry run python scripts/run_midterm_cycle.py --ticker SPY --ticker GSPC   # 대상을 좁힌다 (여러 번 줄 수 있다)
poetry run python scripts/run_midterm_cycle.py --repeats 5000 --seed 42     # 무작위 뽑기 대조의 반복 수·시드
poetry run python scripts/run_midterm_cycle.py --stop-grid                  # 손절선 격자 전부 (기본은 확정 무손절 한 종)
```

### 반감기_사이클

```bash
poetry run python scripts/run_halving_cycle.py                              # 1단계 반감기 경과 격자 · 2단계 지표 신호 열넷 · 3단계 달력 + MVRV 혼합 분할 격자 · 달력 매달 분할 측정과 그 손절(무손절 · 저점 이탈) + 3단계 체결 — 진입 × 청산 일시 격자(무손절)와 확정 규칙(월말 분할 · 무손절 · 저점 이탈) (기본값). 원시 파일만 읽는다
poetry run python scripts/run_halving_cycle.py --repeats 5000 --seed 42     # 무작위 뽑기 대조의 반복 수·시드 (표본이 하한 이상인 칸에만 검정이 붙는다 — 1단계 격자는 전 칸 미만)
poetry run python scripts/chart_halving_cycle.py                            # 판단용 차트 HTML 한 장을 만들어 브라우저로 연다 — 측정을 다시 돌리고, 산출물 폴더는 쓰지 않는다
BROWSER=true poetry run python scripts/chart_halving_cycle.py               # 같은 차트를 브라우저를 열지 않고 만든다 (헤드리스 캡처 확인용)
```

선행 조건은 「데이터 받기」로 받은 사본 넷(`BTCUSD_raw.csv` · Coin Metrics 셋)이다.

---

## 시세를 다시 받은 뒤 다시 돌리는 순서

> 결과 파일은 만들 때의 시세로 굳은 사본입니다. quant-data 에서 갱신 · 내보내기를 다시 해 `storage/market/` 의 사본이 바뀌면
> 아래 매매법을 끝까지 차례로 다시 돌리고, 그 수치를 쓴 결과 문서에 새 데이터 기간을 적습니다(루트 [CLAUDE.md](../CLAUDE.md)
> 「재수집은 이미 나온 결과를 바꿉니다」). **단계마다 끝까지 성공한 것을 보고 다음 단계로 갑니다.**
>
> **① 시세 받기** — 「데이터 받기」. quant-data 의 갱신이 비정상으로 멈추면 아무 파일도 쓰이지 않습니다 — 처리는 quant-data `CLAUDE.md`.
> 갱신에서 `--exclude` 로 뺀 종목은 옛 끝날에 머물러, 그 종목의 결과도 거기서 에러 없이 끝납니다 — 반감기_사이클만은 온체인 두 계열
> (MVRV · 시가총액)이 시세보다 하루 넘게 짧으면 멈춥니다. 파일별 끝날은 `storage/market/quant_data_manifest.json`.
>
> **② 매매법** — 블록의 줄 순서대로 돕니다. 하나가 실패하면 뒤는 돌지 않습니다(`set -e` 는 괄호 안 하위 셸에만 걸린다). 블록 안에는
> 주석을 두지 않습니다 — 주석 옵션(`interactivecomments`)이 꺼진 대화형 zsh 는 `#` 줄을 명령으로 읽어 첫 줄에서 멈춥니다.

```bash
(
  set -e
  poetry run python scripts/run_midterm_cycle.py
  poetry run python scripts/run_halving_cycle.py
)
```
