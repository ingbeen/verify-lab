"""측정 계열 — 거래량 0 인 날의 종가를 대조 계열 값으로 바꾼다

거래가 없던 날의 Bitstamp 가격은 체결가가 아니라 **전일값 이월**이다 — 2015-01-06 ~ 08 은 네 값이 모두
276.80 이고 같은 날 Coin Metrics 는 287.55 · 297.54 · 284.34 다(`docs/검증/반감기_사이클/설계.md` 결정 ④).

**종가만 바꾼다.** 대조 계열은 값이 하나뿐이라 시가·고가·저가를 지어낼 수 없다. 그 사흘을 품는 신호 구간은
전부 2015-01-14 바닥도 품어 보유 중 최악이 그 사흘로 정해지지 않는다(2026-09-29 실측).

**원시 파일은 바꾸지 않는다** — 원시 시세는 불변 자산이라 메모리 안에서만 바꾸고, 바꾼 날을 목록으로 돌려준다.
보간이 아니다 — 없는 값을 메우는 것이 아니라 **다른 소스가 잰 그날의 값**으로 바꾸는 것이다(2026-09-29 사용자 결정).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_VALUE, COL_VOLUME
from verify_lab.data.crosscheck import COL_PRIMARY, COL_SECONDARY
from verify_lab.data.loader import validate_market_frame
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 바꾼 날 목록의 컬럼 — 날짜 · 원래 종가(이월값) · 바꾼 종가. 크로스체크 표와 같은 토큰이라 한 이름표로 읽힌다
REPLACED_COLUMNS = [COL_DATE, COL_PRIMARY, COL_SECONDARY]


@dataclass(frozen=True)
class ReplacedPrices:
    """종가를 바꾼 시세와 바꾼 날 목록

    Attributes:
        frame: 측정이 쓰는 시세. 거래량 0 인 날의 종가만 대조 계열 값이다
        replaced: 바꾼 날마다 한 행 — 날짜 · 원래 종가 · 바꾼 종가
    """

    frame: pd.DataFrame
    replaced: pd.DataFrame


def replace_zero_volume_closes(market: pd.DataFrame, reference: pd.DataFrame) -> ReplacedPrices:
    """거래량이 0 인 날의 종가를 같은 날 대조 계열 값으로 바꾼다.

    Args:
        market: 로더를 지난 시세 — 날짜(오름차순) · 종가 · 거래량
        reference: 로더를 지난 단일 값 계열 — 날짜(오름차순) · 값

    Returns:
        바꾼 시세와 바꾼 날 목록. 바꿀 날이 없으면 입력과 같은 시세와 빈 목록이다. 입력은 변경하지 않는다

    Raises:
        ValueError: 필요한 컬럼이 없거나, 거래가 없던 날의 값이 대조 계열에 없거나 유한한 양수가 아닌 경우 —
            이월값을 그대로 두고 지나가면 대체했다고 적힌 날과 실제로 쓴 값이 어긋난다
    """
    validate_market_frame(market, [COL_DATE, COL_CLOSE, COL_VOLUME])
    validate_market_frame(reference, [COL_DATE, COL_VALUE])

    frame = market.copy()
    halted = frame[COL_VOLUME] == 0
    if not halted.any():
        return ReplacedPrices(frame=frame, replaced=pd.DataFrame(columns=REPLACED_COLUMNS))

    halted_dates = frame.loc[halted, COL_DATE]
    substitutes = halted_dates.map(reference.set_index(COL_DATE)[COL_VALUE])
    if substitutes.isna().any():
        missing = halted_dates[substitutes.isna()]
        raise ValueError(
            f"거래가 없던 날의 대조 값이 없어 종가를 바꿀 수 없습니다 (대조 계열에 그날이 없다): " f"{[day.date().isoformat() for day in missing]}"
        )

    # **바꿔 넣는 값은 시세 검증을 다시 지나지 않는다.** 단일 값 계열 로더는 값의 부호를 보지 않으므로(마이너스
    # 금리가 실재한다) 0 이하 · 무한대가 조용히 측정 종가가 되고, 그날 진입은 무한대 · 청산은 −100% 로 집계에 섞인다
    values = substitutes.to_numpy(dtype=float)
    unusable = ~(np.isfinite(values) & (values > 0))
    if unusable.any():
        raise ValueError(
            "거래가 없던 날의 대조 값이 유한한 양수가 아니어서 종가로 쓸 수 없습니다: "
            f"{[(day.date().isoformat(), float(value)) for day, value in zip(halted_dates[unusable], values[unusable], strict=True)]}"
        )

    replaced = pd.DataFrame(
        {
            COL_DATE: halted_dates.to_numpy(),
            COL_PRIMARY: frame.loc[halted, COL_CLOSE].to_numpy(),
            COL_SECONDARY: substitutes.to_numpy(),
        }
    )
    frame.loc[halted, COL_CLOSE] = substitutes.to_numpy()

    logger.debug(f"거래량 0 인 날 {len(replaced):,}일의 종가를 대조 계열 값으로 바꿨습니다")

    return ReplacedPrices(frame=frame, replaced=replaced)


__all__ = ["REPLACED_COLUMNS", "ReplacedPrices", "replace_zero_volume_closes"]
