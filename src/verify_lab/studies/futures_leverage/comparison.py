"""세 방식의 구간 수익률과 차이 분해

같은 자기자본·같은 목표 배수·같은 구간에서 **① 레버리지 ETF ② 선물 매일 리밸런싱
③ 선물 월 1회 리밸런싱 ④ 선물 그대로 두기** 를 나란히 낸다.

**④ 가 사용자가 실제로 하는 것이다** — 1억을 넣고 계약 수를 그대로 두는 것. ①~③ 은
「선물로 ETF 를 복제할 수 있는가」에 답하고, ④ 는 「그냥 사서 들고 있으면 같은가」에 답한다.

## 구간 수익률을 엔진으로 하나씩 돌리지 않는다

시작일 7,602개 × 구간 7개 × 짝 6개 × 롤 규칙 2벌 × 이자 2벌을 포지션 엔진으로 돌리면
2억 회가 넘는 반복이 된다. 대신 `position` 과 **같은 규약**을 벡터화해서 낸다.

구간(리밸런싱 사이) 안에서 자기자본은

```
E = E_구간시작 × (1 + 배수 × 구간수익률) × Π(1 + 이자율)
```

이고 손익 흐름과 이자 흐름이 곱으로 갈린다. 그래서 보유 구간의 수익률은
**리밸런싱 경계로 자른 조각들의 곱**이 된다.

- **매일 리밸런싱** — 조각이 하루씩이므로 일간 누적곱 하나로 전 구간이 나온다
- **월 1회** — 조각이 진입일로부터 `REBALANCE_INTERVAL_DAYS` 거래일마다다
- **그대로 두기** — 조각이 하나뿐이라 `배수 × 구간수익률` 로 닫힌다. 복리가 붙지 않는 것이
  다른 둘과의 차이이며, 그 대가로 **배수가 표류한다**

두 경로가 엔진과 정확히 같은 값을 내는지는 테스트로 고정한다 (절대 원칙 5 판정식 단일화).

## 분해는 잔여를 나머지로 두지 않는다

`잔여 = 차이 − 나머지` 로 두면 항등식이 정의상 성립해 아무것도 검증하지 못한다.
그래서 세 항을 **독립 산식**으로 내고 잔여만 남긴다.

| 항 | 산식 | 성질 |
| --- | --- | --- |
| **롤·베이시스 몫** | `선물 연속계열 구간수익률 − 현물지수 구간수익률` | 독립 산식 |
| **리밸런싱 오차** | `선물(월1회) − 선물(매일)` | 정의상 이 차이 하나 |
| **그대로 두기 오차** | `선물(그대로) − 선물(매일)` | 정의상 이 차이 하나 |
| **여유현금 이자** | `선물(이자 있음) − 선물(이자 없음)` | 정의상 이 차이 하나 |
| **잔여** | `[선물(매일·이자없음) − ETF] − 배수 × 롤·베이시스 몫` | 남는 것 = ETF 총보수·차입·추적오차·배당 미반영 |

> **기준선을 1배 ETF 가 아니라 현물지수로 둔다.** 1배 ETF 를 쓰면 롤 몫에 **그 ETF 의
> 총보수와 배당 미반영**이 섞여 들어와, 「롤이 얼마를 벌거나 잃는가」를 따로 볼 수 없다.
> 현물지수는 거래소가 선물 시세와 함께 주므로 따로 받을 것도 없다.
>
> **부호는 「선물이 현물보다 얼마나 앞섰나」다.** 백워데이션(차월물이 근월물보다 쌈)에서는
> 롤할 때 비싼 근월물을 팔고 싼 차월물을 사므로 **양수(롤 수익)** 가 되고,
> 콘탱고에서는 음수(롤 비용)가 된다. 「비용」이라는 말이 부호를 정하지 않는다.

**비교의 기준선은 「선물 매일·이자 없음」 하나로 고정한다.** 세 방식을 한 항등식에 넣으면
좌변의 「선물」이 무엇인지 정해지지 않아 분해가 성립하지 않는다.

> **인버스 칸에서는 롤 비용이 양쪽에 있다.** 국내 인버스 ETF 는 자신이 선물지수를 추종해
> ETF 안에도 롤 비용이 들어 있고, 그 몫은 분리되지 않아 **잔여에 섞인다.**
> 레버리지 칸만 현물지수를 추종해 깨끗하게 갈린다.
"""

from collections.abc import Sequence

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.measure.constants import COL_EXCLUDED_REASON, COL_HORIZON, REASON_NONE, REASON_OUT_OF_RANGE
from verify_lab.studies.futures_leverage.constants import (
    HOLDING_HORIZONS,
    REBALANCE_DAILY,
    REBALANCE_INTERVAL_DAYS,
    REBALANCE_MONTHLY,
    REBALANCE_NONE,
    REBALANCE_RULES,
    WIPEOUT_RETURN,
)
from verify_lab.studies.futures_leverage.position import daily_interest_rates
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)


def _validated_horizons(horizons: Sequence[int]) -> list[int]:
    """보유 기간 목록을 검증하고 오름차순으로 돌려준다.

    Args:
        horizons: 보유 기간 목록 (거래일)

    Returns:
        오름차순 보유 기간 목록

    Raises:
        ValueError: 비었거나, 1 미만이거나, 중복이 있는 경우
    """
    if not horizons:
        raise ValueError("보유 기간 목록이 비어 있습니다")
    if any(horizon < 1 for horizon in horizons):
        raise ValueError(f"보유 기간은 1 이상이어야 합니다: {sorted(horizons)}")
    if len(set(horizons)) != len(horizons):
        raise ValueError(f"보유 기간에 중복이 있습니다: {sorted(horizons)}")

    return sorted(horizons)


def _segment_boundaries(horizon: int, rebalance_rule: str) -> list[int]:
    """진입일 기준 리밸런싱 경계를 돌려준다.

    매일 리밸런싱이면 하루씩, 월 1회면 `REBALANCE_INTERVAL_DAYS` 거래일마다이며,
    마지막 경계는 언제나 구간 끝이다.

    Args:
        horizon: 보유 기간 (거래일)
        rebalance_rule: 리밸런싱 규칙

    Returns:
        진입일을 0 으로 한 경계 위치 목록 (오름차순, 0 과 `horizon` 을 포함)

    Raises:
        ValueError: 모르는 규칙인 경우
    """
    if rebalance_rule == REBALANCE_DAILY:
        return list(range(horizon + 1))

    # 그대로 두기는 진입일과 종료일 둘뿐이다 — 구간 안에서 한 번도 배수를 되돌리지 않는다
    if rebalance_rule == REBALANCE_NONE:
        return [0, horizon]

    if rebalance_rule != REBALANCE_MONTHLY:
        raise ValueError(f"모르는 리밸런싱 규칙입니다: {rebalance_rule} (가능: {list(REBALANCE_RULES)})")

    boundaries = list(range(0, horizon, REBALANCE_INTERVAL_DAYS))
    if boundaries[-1] != horizon:
        boundaries.append(horizon)

    return boundaries


def leveraged_window_returns(
    prices: np.ndarray,
    multiple: float,
    horizon: int,
    rebalance_rule: str,
    interest_factor: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """시작일마다 보유 구간의 레버리지 수익률을 낸다.

    `position.run_position` 과 **같은 규약**이다 — 구간(리밸런싱 사이) 안에서
    `E = E_시작 × (1 + 배수 × 구간수익률) × Π(1 + 이자율)` 이므로, 보유 구간의 수익률은
    리밸런싱 경계로 자른 조각들의 곱이 된다.

    **자기자본이 0 이하로 떨어지는 구간은 `WIPEOUT_RETURN`(−100%) 으로 돌려준다.**
    강제청산되면 자기자본이 전액 사라지므로 그것이 그 구간의 성적이다. 비워두면 살아남은
    구간만 평균에 들어가 **생존편향**이 생긴다 — 그대로 두기 축에서 소진이 대량 발생하며,
    제외하면 망한 구간이 결과에서 통째로 사라진다.

    **구간이 데이터를 넘어가 못 잰 시작일과는 구분한다.** 그쪽은 «성적이 없는» 것이라
    `NaN` 이다. 소진 표시는 별도로 함께 돌려주므로 몇 건이었는지 그대로 남는다
    (`src/verify_lab/CLAUDE.md` 절대 원칙 4 표본 보존).

    Args:
        prices: 가격 배열 (날짜 오름차순). **실제 계약 가격이 아니라 연속 계열을 넘긴다** —
            구간 수익률만 쓰므로 조정 계열로 계산해도 같은 값이 나오고, 계약 경계에서
            끊기지 않는다
        multiple: 목표 배수 (인버스는 음수)
        horizon: 보유 기간 (거래일)
        rebalance_rule: 리밸런싱 규칙
        interest_factor: 첫날을 1 로 하는 이자 누적 배수. None 이면 이자 없음

    Returns:
        (구간 수익률, 자기자본 소진 표시) 짝. 구간 끝이 데이터를 넘어간 시작일은 NaN 이고,
        자기자본이 소진된 시작일은 `WIPEOUT_RETURN`(−100%) 이다

    Raises:
        ValueError: 보유 기간이 1 미만인 경우
    """
    if horizon < 1:
        raise ValueError(f"보유 기간은 1 이상이어야 합니다: {horizon}")

    row_count = len(prices)
    positions = np.arange(row_count)
    usable = positions + horizon <= row_count - 1

    growth = np.ones(row_count)
    wiped_out = np.zeros(row_count, dtype=bool)
    boundaries = _segment_boundaries(horizon, rebalance_rule)

    for start_offset, end_offset in zip(boundaries[:-1], boundaries[1:], strict=False):
        segment_start = np.where(usable, positions + start_offset, 0)
        segment_end = np.where(usable, positions + end_offset, 0)
        segment_return = prices[segment_end] / prices[segment_start] - 1.0
        factor = 1.0 + multiple * segment_return

        # 한 조각에서라도 0 이하가 되면 그 구간은 거기서 끝난 것이다.
        # 이후 조각을 곱하지 않는다 — 존재할 수 없는 경로를 이어 붙이게 된다
        wiped_out |= usable & (factor <= 0.0)
        growth = np.where(usable & ~wiped_out, growth * factor, growth)

    if interest_factor is not None:
        window_interest = (
            interest_factor[np.where(usable, positions + horizon, 0)] / interest_factor[np.where(usable, positions, 0)]
        )
        growth = np.where(usable & ~wiped_out, growth * window_interest, growth)

    # **소진과 「못 잼」을 구분한다.** 소진은 −100% 라는 «성적» 이고, 구간이 데이터를
    # 넘어간 시작일은 «성적이 없는» 것이다. 소진을 비우면 살아남은 구간만 평균에 들어가
    # 생존편향이 생기고, 못 잰 칸을 −100% 로 채우면 없던 손실을 지어낸다
    result = np.where(usable, np.where(wiped_out, WIPEOUT_RETURN, growth - 1.0), np.nan)

    return result, wiped_out


def plain_window_returns(prices: np.ndarray, horizon: int) -> np.ndarray:
    """시작일마다 보유 구간의 단순 수익률을 낸다.

    ETF 보유와 1배 기준선이 여기 해당한다. **검증 #8 의 `divergence` 와 같은 산식이라**
    같은 (종목, 시작일, 구간) 에서 같은 값이 나와야 한다.

    Args:
        prices: 가격 배열 (날짜 오름차순)
        horizon: 보유 기간 (거래일)

    Returns:
        시작일마다의 구간 수익률. 구간 끝이 데이터를 넘어가는 시작일은 NaN

    Raises:
        ValueError: 보유 기간이 1 미만인 경우
    """
    if horizon < 1:
        raise ValueError(f"보유 기간은 1 이상이어야 합니다: {horizon}")

    row_count = len(prices)
    positions = np.arange(row_count)
    ends = positions + horizon
    usable = ends <= row_count - 1

    result = np.full(row_count, np.nan)
    result[usable] = prices[ends[usable]] / prices[positions[usable]] - 1.0

    return result


def build_interest_factor(dates: pd.Series, interest: pd.Series | None) -> np.ndarray | None:
    """거래일마다의 이자 누적 배수를 만든다.

    첫날을 1 로 두고 **직전 거래일부터의 달력일 수**만큼 붙인다.
    구간 이자는 `factor[끝] ÷ factor[시작]` 으로 나온다.

    Args:
        dates: 거래일 Series (오름차순)
        interest: 날짜를 인덱스로 하는 연율 금리(%) Series. None 이면 None 을 돌려준다

    Returns:
        누적 배수 배열. 이자가 없으면 None
    """
    if interest is None:
        return None

    # **일간 이자율 산식은 `position` 이 소유한다.** 여기서 다시 쓰면 두 경로가 조용히 갈라진다
    return np.cumprod(1.0 + daily_interest_rates(dates, interest))


def build_window_table(
    dates: pd.Series,
    returns_by_method: dict[str, np.ndarray],
    horizon: int,
) -> pd.DataFrame:
    """방식별 구간 수익률을 long-form 표로 만든다.

    **구간 끝이 데이터를 넘어가는 시작일도 행을 남긴다** — 값만 비우고 사유를 단다.
    행이 사라지면 그 시작일을 못 쟀다는 사실 자체가 보이지 않는다 (측정의 원칙 17).

    Args:
        dates: 거래일 Series (오름차순)
        returns_by_method: 방식 이름 → 구간 수익률 배열
        horizon: 보유 기간 (거래일)

    Returns:
        `Date` · `Horizon` · 방식별 수익률 컬럼 · `ExcludedReason` 을 갖는 DataFrame
    """
    table = pd.DataFrame({COL_DATE: dates.to_numpy(), COL_HORIZON: horizon})

    for method, values in returns_by_method.items():
        table[method] = values

    any_method = next(iter(returns_by_method.values()))
    table[COL_EXCLUDED_REASON] = np.where(np.isnan(any_method), REASON_OUT_OF_RANGE, REASON_NONE)

    return table


def decompose(
    etf_return: np.ndarray,
    futures_daily: np.ndarray,
    futures_monthly: np.ndarray,
    futures_hold: np.ndarray,
    futures_daily_with_interest: np.ndarray,
    continuous_return: np.ndarray,
    spot_return: np.ndarray,
    multiple: float,
) -> pd.DataFrame:
    """세 방식의 차이를 독립 산식 네 항으로 가른다.

    **잔여를 나머지로 정의하지 않는다.** 앞의 세 항이 각자 독립 산식이고 잔여만 남는다.
    그래야 잔여의 크기가 뜻을 갖는다 — ETF 총보수와 같은 자릿수여야 정상이다.

    Args:
        etf_return: ETF 보유의 구간 수익률
        futures_daily: 선물 매일 리밸런싱(이자 없음)의 구간 수익률. **비교의 기준선**
        futures_monthly: 선물 월 1회(이자 없음)의 구간 수익률
        futures_hold: 선물 그대로 두기(이자 없음)의 구간 수익률
        futures_daily_with_interest: 선물 매일 리밸런싱(이자 있음)의 구간 수익률
        continuous_return: 선물 연속 계열의 1배 구간 수익률
        spot_return: **현물지수**의 구간 수익률. 1배 ETF 가 아니다 — ETF 를 쓰면
            롤 몫에 그 ETF 의 총보수와 배당 미반영이 섞인다
        multiple: 목표 배수

    Returns:
        `RollCost` · `RebalanceError` · `HoldError` · `InterestGain` · `Residual` ·
        `FuturesMinusEtf` · `HoldMinusEtf` 컬럼.
        `RollCost` 는 **양수면 롤 수익**(백워데이션), 음수면 롤 비용(콘탱고)이다
    """
    roll_cost = continuous_return - spot_return
    rebalance_error = futures_monthly - futures_daily
    hold_error = futures_hold - futures_daily
    interest_gain = futures_daily_with_interest - futures_daily
    futures_minus_etf = futures_daily - etf_return
    residual = futures_minus_etf - multiple * roll_cost

    return pd.DataFrame(
        {
            "RollCost": roll_cost,
            "RebalanceError": rebalance_error,
            "HoldError": hold_error,
            "InterestGain": interest_gain,
            "Residual": residual,
            "FuturesMinusEtf": futures_minus_etf,
            # **사용자 질문에 직접 답하는 열이다** — 「1억을 넣고 그대로 두면 ETF 와 같은가」
            "HoldMinusEtf": futures_hold - etf_return,
        }
    )


def horizons_or_default(horizons: Sequence[int] | None) -> list[int]:
    """보유 기간 목록을 정한다. 생략하면 이 검증의 격자를 쓴다.

    Args:
        horizons: 보유 기간 목록. None 이면 `HOLDING_HORIZONS`

    Returns:
        검증된 오름차순 보유 기간 목록
    """
    return _validated_horizons(list(horizons) if horizons is not None else list(HOLDING_HORIZONS))
