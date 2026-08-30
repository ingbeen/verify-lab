"""이론값 구성 — 「달러를 들고 이자를 받았다면」의 원화 수익률

**사양서 안에서 두 식이 갈린다.**

| 모형 | 식 | 출처 |
| --- | --- | --- |
| `CARRY` | 현물 + (달러금리 − 원화금리) | §16.1 의 H₀ |
| `USD_RATE` | 현물 + 달러금리 | §2.1 의 커버드 금리평형 (달러 현물 + 달러 이자 = 달러선물 롱 + 원화 담보 이자) |

두 식은 **원화금리만큼** 다르고, 어느 쪽을 쓰느냐로 알파가 통째로 달라진다.
하나를 고르는 것은 측정이 아니므로 **둘 다 산출하고 어느 쪽이 실제와 맞는지를 결과로 답한다.**

세 가지 산식 규칙이 결과를 좌우한다.

1. **이자는 달력일 ÷ 365 로 일할한다** (`docs/spec/usdkrw_grid.md` 결정 C14).
   거래일 수로 세면 주말 사흘치 이자가 사라진다
2. **직전 행의 금리를 쓴다.** 구간이 끝난 뒤에 고시된 금리로 그 구간의 이자를 계산하면 미래를 참조한다
3. **현물과 이자를 곱으로 결합한다.** 이론 자산의 원화 평가액이 `환율 × (1 + 이자)` 로 커지므로,
   더하기로 두면 누적 비교에서 복리가 어긋난다. 사양서가 `+` 로 적은 것은 근사 표기다
"""

import pandas as pd

from verify_lab.common_constants import COL_DATE, RATE_TO_PERCENT
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
    DAYS_PER_YEAR,
    TheoreticalModel,
)

# 결과 컬럼 순서. 사용자가 손으로 검산할 수 있도록 중간값(현물 변화·이자)을 함께 남긴다
RETURN_COLUMNS = [
    COL_DATE,
    COL_ACTUAL_RETURN,
    COL_SPOT_RETURN,
    COL_RATE_CONTRIBUTION,
    COL_THEORETICAL_RETURN,
]

# 계산에 필요한 정렬 결과의 컬럼
REQUIRED_COLUMNS = [COL_DATE, COL_ETF_CLOSE, COL_SPOT, COL_KRW_RATE, COL_USD_RATE, COL_DAY_COUNT]


def build_returns(aligned: pd.DataFrame, model: TheoreticalModel) -> pd.DataFrame:
    """정렬된 표에서 실제·이론 일간수익률을 만든다.

    첫 행은 직전 거래일이 없어 수익률도 이자도 정의되지 않으므로 결과에서 빠진다.

    Args:
        aligned: `alignment.align_to_etf_calendar` 가 낸 표
        model: 이론값 구성 방식

    Returns:
        `RETURN_COLUMNS` 구성의 표. 행 수는 입력보다 하나 적다

    Raises:
        ValueError: 필요한 컬럼이 없거나, 행이 두 개 미만인 경우
    """
    missing_columns = set(REQUIRED_COLUMNS) - set(aligned.columns)
    if missing_columns:
        raise ValueError(f"정렬 결과에 필수 컬럼이 없습니다: {sorted(missing_columns)}")

    if len(aligned) < 2:
        raise ValueError(f"수익률을 만들려면 두 행 이상이 필요합니다: {len(aligned)}행")

    frame = aligned.copy()

    # 1. 실제·현물 변화율
    frame[COL_ACTUAL_RETURN] = frame[COL_ETF_CLOSE].pct_change()
    frame[COL_SPOT_RETURN] = frame[COL_SPOT].pct_change()

    # 2. 이자. **직전 행의 금리**를 그 구간 내내 적용한다 — 구간이 끝난 뒤의 금리를 쓰면 미래 참조다
    annual_rate = _annual_rate(frame, model).shift(1) / RATE_TO_PERCENT
    frame[COL_RATE_CONTRIBUTION] = annual_rate * frame[COL_DAY_COUNT] / DAYS_PER_YEAR

    # 3. 현물과 이자를 곱으로 결합한다
    frame[COL_THEORETICAL_RETURN] = (1 + frame[COL_SPOT_RETURN]) * (1 + frame[COL_RATE_CONTRIBUTION]) - 1

    return frame[RETURN_COLUMNS].iloc[1:].reset_index(drop=True)


def _annual_rate(frame: pd.DataFrame, model: TheoreticalModel) -> pd.Series:
    """모형에 맞는 연 금리(백분율)를 고른다.

    Args:
        frame: 정렬된 표
        model: 이론값 구성 방식

    Returns:
        연 금리 (백분율 단위)

    Raises:
        RuntimeError: 정의되지 않은 모형이 들어온 경우
    """
    if model is TheoreticalModel.CARRY:
        return frame[COL_USD_RATE] - frame[COL_KRW_RATE]

    if model is TheoreticalModel.USD_RATE:
        return frame[COL_USD_RATE]

    raise RuntimeError(f"내부 불변조건 위반: 알 수 없는 이론값 모형입니다 - model={model}")
