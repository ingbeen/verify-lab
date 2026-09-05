"""실효 총비용 — ETF 가 실제로 떼어가는 몫

**공시 총보수가 아니라 실제 부담을 잰다.** 공시값에는 기타비용·내부 매매비용·롤 비용이 빠져 있고,
반대로 담보 운용 초과수익 같은 플러스 요인도 반영되지 않는다. NAV 는 그 모든 것이 이미 반영된
순자산가치이므로, **NAV 수익률을 구조에 맞는 기준선에 회귀하면 절편이 곧 실효 비용**이다.

두 가지를 반드시 맞춰야 값이 맞는다.

1. **NAV 에도 분배금 조정을 건다.** 원 NAV 는 분배락일에 뚝 떨어지므로 그대로 쓰면 비용이 부풀려진다
   — 261240 에서 실측 0.095% 가 0.198% 로 두 배가 된다. 조정 배율은 시세의 `수정 종가 ÷ 원본가` 로 뽑는다
2. **기준선에 노출 배수를 반영한다.** 2배 상품은 2배 노출을 **1배 담보**로 굴리므로 원화 이자를
   1배만 받는다. 이것을 빼먹고 `2 × (현물 + 달러금리)` 에 견주면 원화금리 전액이 비용으로 잡힌다
   — 261250 에서 −0.05% 가 −2.12% 로 뒤바뀐다

```
기준선(일간) = L × 현물수익 + (L × 달러금리 − (L−1) × 원화금리) × 달력일 ÷ 365
```

일간 리밸런싱 상품의 하루 수익은 기초자산 하루 수익의 정확히 L 배이므로 **더하기로 결합**한다.
L=1 이면 `theoretical` 의 `현물 + 달러금리` 와 같아진다.
"""

import pandas as pd

from verify_lab.common_constants import CALENDAR_DAYS_PER_YEAR, COL_CLOSE, COL_DATE, COL_VALUE, RATE_TO_PERCENT
from verify_lab.data.loader import load_market_csv, load_series_csv
from verify_lab.studies.usdkrw_equivalence.constants import (
    COL_ACTUAL_RETURN,
    COL_DAY_COUNT,
    COL_ETF_CLOSE,
    COL_KRW_RATE,
    COL_RATE_CONTRIBUTION,
    COL_SPOT,
    COL_SPOT_RETURN,
    COL_THEORETICAL_RETURN,
    COL_USD_RATE,
    EtfTarget,
)

# 결과 컬럼. `theoretical.build_returns` 와 같은 이름을 써서 회귀 함수를 그대로 재사용한다
COST_RETURN_COLUMNS = [
    COL_DATE,
    COL_ACTUAL_RETURN,
    COL_SPOT_RETURN,
    COL_RATE_CONTRIBUTION,
    COL_THEORETICAL_RETURN,
]

# 조정 배율을 낼 때만 쓰는 중간 컬럼. 세 계열을 한 표에 합치므로 이름이 겹치면 안 된다
_COL_RAW_CLOSE = "RawClose"
_COL_ADJUSTED_CLOSE = "AdjustedClose"
_COL_RAW_NAV = "RawNav"


def build_adjusted_nav(target: EtfTarget) -> pd.DataFrame:
    """분배금이 조정된 NAV 계열을 만든다.

    조정 배율을 **시세에서 뽑아** NAV 에 그대로 적용한다(`수정 종가 ÷ 원본가`).
    운용사가 공표한 배율이 아니라 저장된 두 시세 계열에서 유도한 값이다.

    Args:
        target: 대상 ETF

    Returns:
        `Date` 와 `Close`(조정된 NAV) 두 컬럼짜리 표

    Raises:
        FileNotFoundError: 입력 파일이 없는 경우
        ValueError: 세 계열에 겹치는 날이 없거나, 원본가에 0 이하가 있는 경우
    """
    raw = load_market_csv(target.raw_price_path)[[COL_DATE, COL_CLOSE]].rename(columns={COL_CLOSE: _COL_RAW_CLOSE})
    adjusted = load_market_csv(target.price_path)[[COL_DATE, COL_CLOSE]].rename(
        columns={COL_CLOSE: _COL_ADJUSTED_CLOSE}
    )
    nav = load_series_csv(target.nav_path).rename(columns={COL_VALUE: _COL_RAW_NAV})

    merged = raw.merge(adjusted, on=COL_DATE).merge(nav, on=COL_DATE)

    if merged.empty:
        raise ValueError(f"원본가·수정주가·NAV 에 겹치는 날이 없습니다: {target.ticker}")

    if (merged[_COL_RAW_CLOSE] <= 0).any():
        raise ValueError(f"원본가에 0 이하 값이 있어 조정 배율을 낼 수 없습니다: {target.ticker}")

    merged[COL_CLOSE] = merged[_COL_RAW_NAV] * (merged[_COL_ADJUSTED_CLOSE] / merged[_COL_RAW_CLOSE])

    return merged[[COL_DATE, COL_CLOSE]]


def build_cost_returns(aligned: pd.DataFrame, exposure: int) -> pd.DataFrame:
    """노출 배수를 반영한 기준선과 실제 수익률을 만든다.

    Args:
        aligned: `alignment.align_to_etf_calendar` 가 낸 표 (NAV 계열로 만든 것)
        exposure: 노출 배수 (1 이상)

    Returns:
        `COST_RETURN_COLUMNS` 구성의 표. 첫 행은 수익률이 정의되지 않아 빠진다

    Raises:
        ValueError: 노출 배수가 1 미만이거나, 행이 두 개 미만인 경우
    """
    if exposure < 1:
        raise ValueError(f"노출 배수는 1 이상이어야 합니다: {exposure}")

    if len(aligned) < 2:
        raise ValueError(f"수익률을 만들려면 두 행 이상이 필요합니다: {len(aligned)}행")

    frame = aligned.copy()

    frame[COL_ACTUAL_RETURN] = frame[COL_ETF_CLOSE].pct_change()
    frame[COL_SPOT_RETURN] = frame[COL_SPOT].pct_change()

    # 2배 노출은 달러금리를 2배로 받지만 담보는 1배뿐이라 원화 이자를 1배만 받는다.
    # 금리는 직전 행의 값을 쓴다 — 구간이 끝난 뒤 고시된 금리를 쓰면 미래를 참조한다
    annual_rate = (
        exposure * frame[COL_USD_RATE].shift(1) - (exposure - 1) * frame[COL_KRW_RATE].shift(1)
    ) / RATE_TO_PERCENT
    frame[COL_RATE_CONTRIBUTION] = annual_rate * frame[COL_DAY_COUNT] / CALENDAR_DAYS_PER_YEAR

    # 일간 리밸런싱 상품의 하루 수익은 기초자산 하루 수익의 정확히 L 배다
    frame[COL_THEORETICAL_RETURN] = exposure * frame[COL_SPOT_RETURN] + frame[COL_RATE_CONTRIBUTION]

    return frame[COST_RETURN_COLUMNS].iloc[1:].reset_index(drop=True)
