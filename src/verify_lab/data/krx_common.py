"""KRX 를 상대하는 코드가 공유하는 판정

수집기 `pykrx` 와 실측 프로브 `check_pykrx_splice` 는 같은 규격(`YYYYMMDD` 요청 · 확정되지 않은 최근 구간)을
상대하므로 **판정도 한 벌이어야 한다** (`src/verify_lab/CLAUDE.md` 「측정 계층의 절대 원칙」 5).
ETN · 선물 수집기가 쓰는 숫자 변환(`to_numeric`)은 그 수집기와 함께 되살린다 — `docs/조사/레버리지_ETF_괴리.md`(ETN) ·
`docs/조사/선물_대_레버리지_ETF.md`(선물) 「재현 방법」.

**수집기마다 복사본을 두지 않는다.** 복사본은 한 곳만 고쳐도 예외가 나지 않는다 —
저장 경계가 수집기마다 하루씩 갈려도 파일은 그대로 만들어진다.

[중요] **지연 import 헬퍼(`_import_krx_client`)는 여기 오지 않는다.** `tests/test_layer_contracts.py` 의
순서 검사가 **`load_krx_credentials()` 호출과 `from pykrx` 가 같은 함수 본문 안에 있는지**를 보므로,
뽑아내면 수집기가 그 계약을 잃는다.
"""

from datetime import date, datetime, timedelta
from typing import Final

import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.data.constants import DOMESTIC_RECENT_EXCLUSION_DAYS, KRX_REQUEST_DATE_FORMAT

# 날짜 형식 오류 메시지. **어느 인자인지를 `label` 로 받는다** — 수집기마다 조회 시작일·
# 훑기 종료일처럼 이름이 다른데, 이름을 빼면 인자가 둘인 호출에서 어느 쪽이 틀렸는지 알 수 없다
_DATE_FORMAT_ERROR: Final = "{label} 형식이 잘못되었습니다 (YYYYMMDD 여야 합니다): {value}"


def exclude_recent(df: pd.DataFrame, today: date) -> tuple[pd.DataFrame, int]:
    """확정되지 않은 최근 구간을 제외하고 빠진 행 수를 함께 돌려준다.

    건수를 함께 내는 것은 표본 보존 때문이다 — 조용히 줄어든 표본은 생존편향을 만든다.

    Args:
        df: 날짜 컬럼을 가진 DataFrame
        today: 기준일

    Returns:
        (제외 후 DataFrame, 제외된 행 수)
    """
    cutoff_date = today - timedelta(days=DOMESTIC_RECENT_EXCLUSION_DAYS)
    total_count = len(df)
    trimmed = df.loc[df[COL_DATE] <= cutoff_date].reset_index(drop=True)

    return trimmed, total_count - len(trimmed)


def validate_krx_date(label: str, value: str) -> None:
    """KRX 요청에 넣을 날짜 문자열의 형식을 검증한다.

    Args:
        label: 예외 메시지에 쓸 인자 이름 (예: `조회 시작일`)
        value: 검사할 날짜 문자열 (YYYYMMDD)

    Raises:
        ValueError: 형식이 잘못된 경우
    """
    try:
        datetime.strptime(value, KRX_REQUEST_DATE_FORMAT)
    except ValueError as error:
        raise ValueError(_DATE_FORMAT_ERROR.format(label=label, value=value)) from error


__all__ = ["exclude_recent", "validate_krx_date"]
