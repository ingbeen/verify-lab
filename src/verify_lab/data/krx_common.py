"""KRX 를 상대하는 세 수집기가 공유하는 판정

`pykrx`·`etn`·`krx_futures` 는 같은 규격(쉼표 붙은 숫자 · `-` 결측 · `YYYYMMDD` 요청 ·
확정되지 않은 최근 구간)을 상대하므로 **판정도 한 벌이어야 한다**
(`src/verify_lab/CLAUDE.md` 「측정 계층의 절대 원칙」 5).

전에는 최근 구간 제외와 숫자 변환이 `etn`·`krx_futures` 에 **바이트 단위로 같은 복사본**으로
있었고 `pykrx_collector` 는 같은 로직을 세 함수에 인라인으로 들고 있었다. 복사본은 한 곳만
고쳐도 예외가 나지 않는다 — 저장 경계가 수집기마다 하루씩 갈려도 파일은 그대로 만들어진다.

[중요] **지연 import 헬퍼(`_import_krx_client`)는 여기 오지 않는다.** 세 수집기가 서로 다른
pykrx 클래스를 가져오므로 공통 부분이 `load_krx_credentials()` 한 줄뿐이고,
`tests/test_layer_contracts.py` 의 순서 검사가 **그 호출과 `from pykrx` 가 같은 함수 본문 안에
있는지**를 보므로 뽑아내면 세 수집기 모두 그 계약을 잃는다.
"""

from datetime import date, datetime, timedelta
from typing import Final

import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.data.constants import DOMESTIC_RECENT_EXCLUSION_DAYS, KRX_REQUEST_DATE_FORMAT

# 날짜 형식 오류 메시지. **어느 인자인지를 `label` 로 받는다** — 수집기마다 조회 시작일·
# 훑기 종료일처럼 이름이 다른데, 이름을 빼면 인자가 둘인 호출에서 어느 쪽이 틀렸는지 알 수 없다
_DATE_FORMAT_ERROR: Final = "{label} 형식이 잘못되었습니다 (YYYYMMDD 여야 합니다): {value}"


def to_numeric(series: pd.Series) -> pd.Series:
    """KRX 가 문자열로 주는 숫자를 실수로 바꾼다.

    천 단위 구분 쉼표가 붙어 있고, 값이 없는 칸은 `-` 로 온다. 쉼표만 떼고 숫자로 바꾸며
    **`-` 는 결측으로 남긴다** — 0 으로 채우면 「가격 0」인 날이 생겨 이상치 검사를 통과해 버린다.

    Args:
        series: KRX 반환값의 한 컬럼

    Returns:
        실수 Series. 변환할 수 없는 칸은 NaN
    """
    return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False), errors="coerce")


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


__all__ = ["exclude_recent", "to_numeric", "validate_krx_date"]
