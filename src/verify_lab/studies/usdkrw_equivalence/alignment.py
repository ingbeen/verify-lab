"""세 소스를 ETF 거래일에 맞춘다

원달러 고시일·미국 영업일·KRX 거래일은 **서로 다른 달력**이다. 정렬 규칙을 명시하지 않으면
어긋난 채로 계산이 돌아가고 예외도 나지 않는다.

| 소스 | 없는 날의 처리 | 근거 |
| --- | --- | --- |
| 원달러 매매기준율 | **제외** | 이 검증의 기준 가격이다. 이월하면 그날 수익률이 0으로 조작된다 |
| CD 91일물 | **제외** | 사양서 §6.5 는 **미국 휴일만** 이월 대상으로 규정했다 |
| 미국 T-bill | **전일값 이월** | 사양서 §6.5 |

**이월은 뒤에서 앞으로 채우지 않는다.** 미래 값을 끌어오면 look-ahead 다. 첫 값보다 앞선
거래일은 이월할 것이 없으므로 제외한다.

제외와 이월은 **반드시 건수로 함께 돌려준다.** 조용히 사라진 표본은 생존편향을 만든다.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_VALUE
from verify_lab.data.loader import validate_market_frame
from verify_lab.studies.usdkrw_equivalence.constants import (
    COL_DAY_COUNT,
    COL_ETF_CLOSE,
    COL_KRW_RATE,
    COL_SPOT,
    COL_USD_RATE,
    KEY_KRW_RATE_MISSING,
    KEY_SPOT_MISSING,
    KEY_USD_RATE_CARRIED,
    KEY_USD_RATE_MISSING,
    SPOT_PUBLICATION_LAG_ROWS,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 정렬 결과의 컬럼 순서
ALIGNED_COLUMNS = [COL_DATE, COL_ETF_CLOSE, COL_SPOT, COL_KRW_RATE, COL_USD_RATE, COL_DAY_COUNT]


@dataclass(frozen=True)
class AlignedResult:
    """정렬 결과

    Attributes:
        frame: ETF 거래일에 맞춰진 표. 컬럼 구성은 `ALIGNED_COLUMNS`
        counts: 제외·이월 건수. 키는 `constants` 의 `KEY_*`
    """

    frame: pd.DataFrame
    counts: dict[str, int]


def align_to_etf_calendar(
    etf: pd.DataFrame,
    spot: pd.DataFrame,
    krw_rate: pd.DataFrame,
    usd_rate: pd.DataFrame,
) -> AlignedResult:
    """ETF 거래일을 마스터 달력으로 삼아 네 시계열을 한 표로 맞춘다.

    마스터를 ETF 거래일로 두는 이유는 **회귀 대상이 ETF 수익률**이기 때문이다. ETF 가 쉬는 날의
    환율 움직임은 이 검증에서 잴 수 있는 대상이 아니다.

    Args:
        etf: ETF 시세 (`load_market_csv` 가 돌려준 형태)
        spot: 원달러 매매기준율 (`load_series_csv` 가 돌려준 형태)
        krw_rate: 원화 단기금리
        usd_rate: 달러 단기금리

    Returns:
        정렬된 표와 제외·이월 건수

    Raises:
        ValueError: 필요한 컬럼이 없거나, 날짜가 오름차순이 아니거나, 겹치는 날이 하나도 없는 경우
    """
    validate_market_frame(etf, [COL_DATE, COL_CLOSE])
    for name, frame in (("환율", spot), ("원화금리", krw_rate), ("달러금리", usd_rate)):
        _validate_series(frame, name)

    master = etf[[COL_DATE, COL_CLOSE]].rename(columns={COL_CLOSE: COL_ETF_CLOSE}).copy()

    # 1. 같은 날 값만 쓰는 두 소스. 없으면 제외 대상이다
    merged = master.merge(_renamed(spot, COL_SPOT), on=COL_DATE, how="left")
    merged = merged.merge(_renamed(krw_rate, COL_KRW_RATE), on=COL_DATE, how="left")

    # 2. 달러금리는 전일값 이월. `merge_asof` 의 backward 방향이 "직전 또는 같은 날"이라
    #    미래를 끌어오지 않는다. 이월 여부를 세려고 정확 일치본을 따로 만들어 대조한다
    exact_usd = merged.merge(_renamed(usd_rate, COL_USD_RATE), on=COL_DATE, how="left")[COL_USD_RATE]
    merged = pd.merge_asof(merged, _renamed(usd_rate, COL_USD_RATE), on=COL_DATE, direction="backward")

    carried = exact_usd.isna() & merged[COL_USD_RATE].notna()

    # 3. 제외 판정. 어느 소스 때문에 빠졌는지를 따로 세어야 원인을 알 수 있다
    spot_missing = merged[COL_SPOT].isna()
    krw_missing = merged[COL_KRW_RATE].isna()
    usd_missing = merged[COL_USD_RATE].isna()

    counts = {
        KEY_SPOT_MISSING: int(spot_missing.sum()),
        KEY_KRW_RATE_MISSING: int(krw_missing.sum()),
        KEY_USD_RATE_MISSING: int(usd_missing.sum()),
        KEY_USD_RATE_CARRIED: int((carried & ~spot_missing & ~krw_missing).sum()),
    }

    kept = merged.loc[~(spot_missing | krw_missing | usd_missing)].reset_index(drop=True)

    if kept.empty:
        raise ValueError(f"네 시계열에 겹치는 날이 하나도 없습니다 (ETF {len(master):,}거래일, 제외 내역 {counts})")

    # 4. 일수는 **남은 행 사이의 달력일 차이**다. 제외된 날에도 이자는 붙으므로
    #    제외 뒤에 계산해야 실제 경과 일수가 담긴다
    kept[COL_DAY_COUNT] = _calendar_day_gaps(kept[COL_DATE])

    logger.debug(f"정렬 완료: {len(kept):,}행 (ETF {len(master):,}거래일), 제외·이월 {counts}")

    return AlignedResult(frame=kept[ALIGNED_COLUMNS], counts=counts)


def _calendar_day_gaps(dates: pd.Series) -> np.ndarray:
    """직전 행과의 달력일 차이를 낸다.

    첫 행은 직전 행이 없어 결측이다.

    Args:
        dates: 날짜 (오름차순)

    Returns:
        길이가 입력과 같은 실수 배열
    """
    days = pd.DatetimeIndex(dates).to_numpy(dtype="datetime64[D]").astype("int64")

    return np.concatenate([[np.nan], np.diff(days).astype(float)])


def _renamed(series: pd.DataFrame, column: str) -> pd.DataFrame:
    """단일 값 시계열의 값 컬럼 이름을 바꿔 돌려준다.

    Args:
        series: 단일 값 시계열
        column: 새 컬럼 이름

    Returns:
        `Date` 와 새 이름의 값 컬럼만 남긴 DataFrame
    """
    return series[[COL_DATE, COL_VALUE]].rename(columns={COL_VALUE: column})


def _validate_series(series: pd.DataFrame, name: str) -> None:
    """단일 값 시계열이 정렬의 전제를 만족하는지 확인한다.

    Args:
        series: 검사할 시계열
        name: 오류 메시지에 담을 이름

    Raises:
        ValueError: 비었거나, 컬럼이 없거나, 날짜가 오름차순이 아닌 경우
    """
    try:
        validate_market_frame(series, [COL_DATE, COL_VALUE])
    except ValueError as error:
        raise ValueError(f"{name} 시계열이 정렬 전제를 만족하지 않습니다: {error}") from None


def to_market_dates(spot: pd.DataFrame) -> pd.DataFrame:
    """매매기준율을 **고시일 기준에서 시장일 기준으로** 옮긴다.

    매매기준율은 「전영업일 은행간 거래의 거래량 가중평균」이라, 고시일 D 의 값이 담고 있는 것은
    **D−1 의 시장**이다. 그대로 쓰면 ETF 종가와 하루 어긋난 채로 계산되며,
    **예외는 나지 않고 결과만 틀린다** — 261240 과의 일간 상관이 −0.03 으로 무의미해진다.

    보정은 고시일을 한 칸 앞으로 당기는 것이다. 첫 행은 대응할 시장일이 없어 빠진다.

    **이 함수는 측정 전용이다.** 시장일 D 의 값을 알려면 D+1 의 고시를 봐야 하므로,
    매매 판정에 쓰면 look-ahead 가 된다.

    Args:
        spot: 고시일 기준 매매기준율 (`load_series_csv` 가 돌려준 형태)

    Returns:
        시장일 기준으로 옮긴 시계열. 행 수가 하나 줄어든다

    Raises:
        ValueError: 컬럼이 없거나, 날짜가 오름차순이 아니거나, 행이 두 개 미만인 경우
    """
    _validate_series(spot, "환율")

    if len(spot) < SPOT_PUBLICATION_LAG_ROWS + 1:
        raise ValueError(f"시차 보정에는 {SPOT_PUBLICATION_LAG_ROWS + 1}행 이상이 필요합니다: {len(spot)}행")

    shifted = spot[[COL_DATE, COL_VALUE]].copy()
    shifted[COL_DATE] = spot[COL_DATE].shift(SPOT_PUBLICATION_LAG_ROWS)

    return shifted.dropna(subset=[COL_DATE]).reset_index(drop=True)
