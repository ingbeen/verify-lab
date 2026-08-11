# verify-lab 실행 명령어 레퍼런스

> 이 파일은 verify-lab 실행 명령어의 **단일 SoT(Source of Truth)** 입니다.
> README.md·CLAUDE.md 등 다른 문서에는 실행 명령어를 기재하지 않으며, 필요 시 이 문서를 참조합니다.
> 설치처럼 한 번만 쓰는 일회성 명령어는 기재하지 않습니다. **평상시 반복 실행하는 명령어만** 관리합니다.

---

## 품질 검증

```bash
# 전체 검증 (Ruff + PyRight + Pytest)
poetry run python validate_project.py

# 개별 실행
poetry run python validate_project.py --only-lint
poetry run python validate_project.py --only-pyright
poetry run python validate_project.py --only-tests

# 커버리지 포함 테스트
poetry run python validate_project.py --cov

# 포맷 자동 적용 (마지막 Phase에서만)
poetry run black .
```

> 검증이 **세 항목 모두 실패**하면서 `Command not found` 가 보이면 코드 문제가 아니라 실행 환경 문제입니다.
> `poetry env info --path` 가 프로젝트의 `.venv` 를 가리키는지 먼저 확인하세요.
> 원인과 대처는 [ROADMAP.md](ROADMAP.md) Phase 0 의 실측 기록에 있습니다.

---

## 데이터 수집

> **사용자만 실행합니다.** 외부 서버(Yahoo Finance, KRX)에 실제 요청을 보내므로
> AI 모델은 이 명령어를 직접 실행하지 않습니다.

### yfinance (미국 종목)

```bash
# QQQ 전 기간 수집 (기본값)
poetry run python scripts/data/collect_yfinance.py

# 다른 종목 수집
poetry run python scripts/data/collect_yfinance.py --ticker SPY
```

- 전 기간(`period="max"`)을 받아 `storage/market/<종목>_max.csv` 에 저장합니다. 기존 파일은 덮어씁니다
- **확정되지 않은 최근 며칠은 저장하지 않습니다.** 제외된 행 수는 실행 결과 표의 "최근 제외"에 표시됩니다
- 이상치가 발견되면 **파일을 만들지 않고 예외로 중단**합니다. 반쪽짜리 파일이 남지 않습니다

### pykrx (국내 종목)

**KRX 데이터포털 계정이 필요합니다.** 저장소 루트의 `.env` 에 `KRX_ID`·`KRX_PW` 가 있어야 하며,
계정이 없으면 pykrx 는 아무것도 조회하지 못합니다.

```bash
# KODEX 200 데이터 성질 실측 (분배금 조정 여부·유동성·괴리율·결측)
poetry run python scripts/data/check_pykrx_etf.py

# 다른 ETF 나 다른 시작일로 실측
poetry run python scripts/data/check_pykrx_etf.py --ticker 069500 --start 20021014
```

- KRX 를 5회 호출하고, **각 결과를 받는 즉시** `storage/results/<실행시각>_pykrx_etf_probe/` 에 CSV 로 남깁니다.
  뒤쪽 호출이 실패해도 앞선 원자료는 보존됩니다
- ⚠️ **pykrx 는 로그인 시 로그인 ID 를 표준 출력에 찍습니다**(비밀번호는 찍지 않습니다).
  실행 로그를 공유하거나 문서에 붙일 때 그 줄을 빼세요

*(KODEX 200 수집 명령어는 위 실측 결과로 수집기를 설계한 뒤 추가합니다)*

---

## 검증 실행

> AI 모델이 직접 실행할 수 있습니다. 파라미터를 바꿔가며 반복 실행하는 것이 검증의 본질입니다.

*(Phase 3에서 스크립트 작성 후 이 절을 채웁니다)*
