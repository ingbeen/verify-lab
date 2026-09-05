"""레버리지 포지션 엔진 — 선물로 «배수»를 만든다

**선물에는 배수가 없다.** 레버리지 ETF 의 2배는 매일 리밸런싱으로 유지되는 값이지만,
선물은 증거금 대비 노출이 가격이 움직이면 저절로 변한다.

- 지수가 오르면 → 평가익이 자기자본에 쌓여 → **배수가 저절로 내려간다**
- 지수가 내리면 → 자기자본이 줄어 → **배수가 저절로 올라간다** (위험이 커지는 쪽)

그래서 **리밸런싱 규칙이 곧 배수의 정의**이고, 이 모듈이 그 규칙을 집행한다.

규칙은 셋이다 — **매일**·**월 1회**·**그대로 두기**. 마지막 것은 진입일에 한 번만 잡고
손대지 않는 방식이며, 사람이 실제로 하는 것이 그것이다. 배수가 유지되지 않으므로
**최대 유효 레버리지가 목표를 크게 넘어설 수 있다.**

## 이 계층은 `strategy/` 가 아니다

**손절·익절·진입 조건을 넣지 않는다.** 리밸런싱은 매매 신호가 아니라 «목표 배수를 유지하는
방법» 이며, 루트 `CLAUDE.md` 가 `strategy/` 밖에서 금지한 「진입·손절·익절 설계」에 해당하지
않는다. 경계가 모호하므로 여기에 못박는다 — 이 모듈에 조건부 청산이 들어오면 그것은
측정이 아니라 매매 규칙이고, 그때는 `strategy/` 로 옮겨야 한다.

## 가격은 실제 계약 가격을 쓴다

**비율 조정 계열을 넣지 않는다.** 조정 계열은 수익률만 보존하고 **가격 수준이 실제 체결가가
아니다.** 계약 수·명목금액·정수 계약 제약은 전부 실제 가격에 걸리므로, 조정가를 넣으면
누적 조정계수만큼 명목이 계통적으로 어긋나고 **정수 계약 대조와 최대 유효 레버리지가 틀린다.**

소수 계약 손익은 수익률만 쓰므로 조정가로 계산해도 같은 값이 나오지만, 그것은 «우연히 맞는
경로» 다. 실제 가격으로 굴리면 셋이 한 번에 맞는다.

## 증거금을 모델링하지 않는다

증거금률 상수를 두지 않는다. 세 가지 이유가 있고 전부 실측이다.

1. 소수 계약 자기자본은 `E × (1 + 배수 × 일간수익률) + 이자` 로 닫혀 **증거금률이 식에 없다**
2. 자기자본 전액이 계좌 담보이므로 **이자도 증거금률과 무관**하다
3. 유지증거금률 7% 로 풀면 마진콜 조건이 **매일 리밸런싱에서 `배수 > 14`(도달 불가)**,
   **월1회 −2배에서 월중 −46.2%**, **월1회 3배에서 월중 −28.3%(자기자본 15% 잔존)** 이다.
   마진콜이 걸리는 유일한 칸에서 이미 사실상 파산이며, **「자기자본 소진」이 가정 없이 같은
   사실을 말한다**

대신 **구간 최대 유효 레버리지**(`노출 ÷ 자기자본`의 구간 최대값)를 낸다. 가정이 하나도
들어가지 않으면서 "월 1회로 끌 때 얼마나 위험해졌는가"를 그대로 보여준다.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.studies.futures_leverage.constants import (
    INITIAL_EQUITY,
    REBALANCE_DAILY,
    REBALANCE_INTERVAL_DAYS,
    REBALANCE_MONTHLY,
    REBALANCE_NONE,
    REBALANCE_RULES,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 자기자본 곡선의 컬럼
COL_PRICE = "Price"
COL_EQUITY = "Equity"
COL_EXPOSURE = "Exposure"
COL_CONTRACT_COUNT = "ContractCount"
COL_EFFECTIVE_LEVERAGE = "EffectiveLeverage"
COL_INTEREST = "Interest"
COL_REBALANCED = "Rebalanced"

# 연 이자율을 하루치로 나눌 때 쓰는 일수. **달력일 기준이다** —
# `CD91` 은 연율 표기이고 이자는 거래일이 아니라 달력일로 붙는다
CALENDAR_DAYS_PER_YEAR = 365

# 백분율로 주어지는 금리를 비율로 바꾸는 계수. `storage/series/CD91.csv` 는 `14.7` 처럼 % 로 온다
PERCENT_TO_RATE = 100.0


@dataclass(frozen=True)
class PositionResult:
    """한 포지션을 끝까지 굴린 결과.

    Attributes:
        curve: 일별 자기자본 곡선. 원자료로 그대로 저장한다
        multiple: 목표 배수
        rebalance_rule: 리밸런싱 규칙
        with_interest: 여유현금 이자를 붙였는지
        final_equity: 마지막 자기자본
        max_effective_leverage: 구간 최대 유효 레버리지 (`노출 ÷ 자기자본`)
        rebalance_count: 리밸런싱한 횟수
        wipeout_date: 자기자본이 0 이하가 된 날. 끝까지 살아남았으면 None
        days_to_wipeout: 소진까지 걸린 거래일 수. 살아남았으면 None
    """

    curve: pd.DataFrame
    multiple: float
    rebalance_rule: str
    with_interest: bool
    final_equity: float
    max_effective_leverage: float
    rebalance_count: int
    wipeout_date: pd.Timestamp | None
    days_to_wipeout: int | None


def _rebalance_flags(dates: pd.Series, rule: str) -> list[bool]:
    """날짜마다 그날 리밸런싱하는지를 정한다.

    **첫날은 언제나 리밸런싱한다** — 포지션을 처음 잡는 날이다.

    월 1회는 **달력이 아니라 진입일에 맞춘다.** 달력(매월 첫 거래일)에 맞추면 리밸런싱
    시점이 월중 위치에 묶여, 5거래일 구간이 진입일에 따라 리밸런싱 0회가 되기도 1회가
    되기도 한다 — 「월 1회」가 어떤 칸에서는 「무리밸런싱」이 되어 **재려는 것이 아닌 축이
    결과에 섞인다.** 진입일에 맞추면 구간 길이만으로 횟수가 정해진다.

    Args:
        dates: 거래일 Series (오름차순)
        rule: 리밸런싱 규칙

    Returns:
        날짜마다 리밸런싱 여부

    Raises:
        ValueError: 모르는 규칙인 경우
    """
    if rule == REBALANCE_DAILY:
        return [True] * len(dates)

    # 그대로 두기는 진입일에 한 번만 잡는다. **진입일 리밸런싱은 남긴다** —
    # 목표 배수로 시작해야 항상 정확히 배수로 시작하는 ETF 와 출발선이 같아진다
    if rule == REBALANCE_NONE:
        return [position == 0 for position in range(len(dates))]

    if rule != REBALANCE_MONTHLY:
        raise ValueError(f"모르는 리밸런싱 규칙입니다: {rule} (가능: {list(REBALANCE_RULES)})")

    return [position % REBALANCE_INTERVAL_DAYS == 0 for position in range(len(dates))]


def _daily_interest_rates(dates: pd.Series, interest: pd.Series | None) -> list[float]:
    """거래일마다 붙는 이자율을 낸다.

    **직전 거래일부터 그날까지의 달력일 수만큼** 붙인다. 주말·연휴가 끼면 그만큼 더 붙는데
    실제로 그렇게 지급되며, 거래일로 나누면 연휴가 긴 해에 이자가 덜 붙는다.

    금리는 **판정일 직전에 알 수 있는 값**을 쓴다. 그날 고시된 금리를 그날 이자에 쓰면
    미래를 참조하는 것은 아니지만, 없는 날은 직전 값을 끌어 쓴다.

    Args:
        dates: 거래일 Series (오름차순)
        interest: 날짜를 인덱스로 하는 연율 금리(%) Series. None 이면 이자를 붙이지 않는다

    Returns:
        거래일마다의 이자율 (비율). 첫날은 0 이다
    """
    if interest is None:
        return [0.0] * len(dates)

    aligned = interest.reindex(dates).ffill().fillna(0.0).to_numpy(dtype=float) / PERCENT_TO_RATE
    stamps = pd.DatetimeIndex(dates)
    elapsed = np.diff(stamps.to_numpy(dtype="datetime64[D]").astype(int), prepend=0.0)
    elapsed[0] = 0.0

    return (aligned * elapsed / CALENDAR_DAYS_PER_YEAR).tolist()


def run_position(
    prices: pd.DataFrame,
    multiple: float,
    rebalance_rule: str,
    *,
    price_column: str,
    interest: pd.Series | None = None,
    initial_equity: float = INITIAL_EQUITY,
    contract_multiplier: float = 1.0,
) -> PositionResult:
    """자기자본 `E` 로 목표 배수 `L` 의 선물 포지션을 끝까지 굴린다.

    리밸런싱하는 날 노출을 `L × E` 로 맞추고, 그 사이에는 계약 수가 고정된 채
    **노출과 자기자본이 따로 움직인다.** 그래서 월 1회 리밸런싱에서는 월중에
    실효 배수가 목표에서 벗어난다 — 그 표류가 이 검증이 재려는 것 중 하나다.

    **자기자본이 0 이하가 되면 그 시점에 종료한다.** 강제청산을 모델링하지 않으므로
    그 이후를 이어 붙이면 실제로 존재할 수 없는 경로가 된다.

    Args:
        prices: 날짜와 가격을 가진 DataFrame (오름차순). 연속 계열이 아니라
            **실제 계약 가격**을 넘긴다
        multiple: 목표 배수 (인버스는 음수)
        rebalance_rule: 리밸런싱 규칙
        price_column: 가격으로 쓸 컬럼 이름
        interest: 날짜를 인덱스로 하는 연율 금리(%) Series. None 이면 이자 없음
        initial_equity: 초기 자기자본
        contract_multiplier: 거래승수. 계약 수를 원 단위로 환산할 때만 쓰인다

    Returns:
        포지션 결과

    Raises:
        ValueError: 입력이 비었거나, 초기 자기자본이 0 이하이거나, 규칙을 모르는 경우
    """
    if prices.empty:
        raise ValueError("가격 계열이 비어 있습니다")
    if initial_equity <= 0:
        raise ValueError(f"초기 자기자본은 0보다 커야 합니다: {initial_equity}")
    if price_column not in prices.columns:
        raise ValueError(f"가격 컬럼이 없습니다: {price_column} (있는 컬럼: {list(prices.columns)})")

    frame = prices[[COL_DATE, price_column]].reset_index(drop=True)
    flags = _rebalance_flags(frame[COL_DATE], rebalance_rule)
    rates = _daily_interest_rates(frame[COL_DATE], interest)

    # 위치 인덱스 접근을 배열로 미리 뽑는다. `DataFrame.at` 은 반환 타입이 Scalar 라
    # 곱셈·비교마다 형변환이 필요하고, 루프 안에서 매번 하면 읽기 어려워진다
    price_values = frame[price_column].to_numpy(dtype=float)
    date_values = pd.DatetimeIndex(frame[COL_DATE])

    equity = initial_equity
    # 손익만 쌓은 자기자본과 이자 배수를 따로 든다. 리밸런싱하는 날 둘을 합쳐 되돌린다
    pnl_equity = initial_equity
    interest_factor = 1.0
    contracts = 0.0
    rows: list[dict[str, object]] = []
    wipeout_date: pd.Timestamp | None = None
    days_to_wipeout: int | None = None
    rebalance_count = 0

    for position in range(len(frame)):
        price = float(price_values[position])
        if price <= 0:
            raise ValueError(f"가격이 0 이하입니다 - 날짜: {date_values[position].date()}, 가격: {price}")

        if position > 0:
            # 1. 손익과 이자를 «구간 안에서 분리해» 쌓는다.
            #    구간(리밸런싱 사이) 안에서 자기자본은
            #        `E = E_구간시작 × (1 + 배수 × 구간수익률) × Π(1 + 이자율)`
            #    이며, 손익 흐름과 이자 흐름이 곱으로 갈린다.
            #
            #    **이 규약이 있어야 롤링 전수 구간을 벡터화할 수 있다.** 이자를 매일 손익에
            #    섞으면 구간 수익률이 경로에 얽혀 곱으로 분해되지 않고, 시작일 7,602개 ×
            #    구간 7개를 엔진으로 하나씩 돌려야 해서 계산이 성립하지 않는다.
            #    두 흐름의 상호작용은 이자율이 하루 0.01% 수준이라 2차항이다.
            #    `comparison` 의 구간 수익률이 같은 규약을 쓰며 테스트로 일치를 고정한다
            previous_price = float(price_values[position - 1])
            pnl_equity += contracts * contract_multiplier * (price - previous_price)
            interest_factor *= 1.0 + rates[position]
            equity = pnl_equity * interest_factor

        if equity <= 0:
            wipeout_date = date_values[position]
            days_to_wipeout = position
            rows.append(
                {
                    COL_DATE: date_values[position],
                    COL_PRICE: price,
                    COL_EQUITY: 0.0,
                    COL_EXPOSURE: 0.0,
                    COL_CONTRACT_COUNT: 0.0,
                    COL_EFFECTIVE_LEVERAGE: float("nan"),
                    COL_INTEREST: rates[position],
                    COL_REBALANCED: False,
                }
            )
            break

        # 3. 리밸런싱하는 날이면 노출을 목표 배수로 되돌리고, 그때까지 쌓인 이자를
        #    자기자본에 합쳐 다음 구간의 출발점으로 삼는다
        rebalanced = flags[position]
        if rebalanced:
            pnl_equity = equity
            interest_factor = 1.0
            contracts = multiple * equity / (price * contract_multiplier)
            rebalance_count += 1

        exposure = contracts * contract_multiplier * price
        rows.append(
            {
                COL_DATE: date_values[position],
                COL_PRICE: price,
                COL_EQUITY: equity,
                COL_EXPOSURE: exposure,
                COL_CONTRACT_COUNT: contracts,
                COL_EFFECTIVE_LEVERAGE: exposure / equity,
                COL_INTEREST: rates[position],
                COL_REBALANCED: rebalanced,
            }
        )

    curve = pd.DataFrame(rows)
    leverage = curve[COL_EFFECTIVE_LEVERAGE].abs()

    return PositionResult(
        curve=curve,
        multiple=multiple,
        rebalance_rule=rebalance_rule,
        with_interest=interest is not None,
        final_equity=float(curve[COL_EQUITY].iloc[-1]),
        max_effective_leverage=float(leverage.max()) if leverage.notna().any() else float("nan"),
        rebalance_count=rebalance_count,
        wipeout_date=wipeout_date,
        days_to_wipeout=days_to_wipeout,
    )
