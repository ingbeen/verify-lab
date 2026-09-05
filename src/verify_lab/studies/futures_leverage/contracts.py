"""정수 계약 제약 — 계약은 쪼갤 수 없다

본선 측정은 **소수 계약**으로 굴린다. 자기자본이 `E × (1 + 배수 × 수익률)` 로 닫혀
규모가 결과에 들어오지 않기 때문이며, 그래야 ETF 와 같은 조건에서 비교할 수 있다.

**그러나 실제로는 계약을 0.78 개 살 수 없다.** 코스피200 선물 1계약이 2억 원대라
자기자본이 작으면 목표 배수를 만들 수 없고, 이 모듈이 그 크기를 낸다.

```
자기자본 1억 · 목표 2배 · 정산가 1,030 · 승수 250,000원
    1계약 명목 = 1,030 × 250,000 = 2억 5,750만원
    목표 노출  = 2억
    필요 계약  = 0.78 개  →  1계약을 사면 실제 배수가 «2.58배»
```

**여기서는 규모가 결과를 만든다** — 본선과 달리 자기자본이 얼마냐가 실제 배수를 정한다.
그래서 「얼마부터 선물이 실용적인가」에 답하는 자리다.

## 반올림은 목표 노출에 가장 가까운 정수로 한다

**파이썬 기본 `round` 를 쓰지 않는다.** 짝수로 붙이는 규칙이라 `round(0.5) == 0` 이 되어
경계에서 계약이 사라진다. 크기에 `0.5` 를 더해 내림하는 방식으로 못박는다.

**내림(floor)을 쓰지 않는 이유**: 항상 목표보다 낮은 배수가 되어, 재려는 것이
「정수 제약의 비용」이 아니라 「배수를 낮춘 효과」로 바뀐다.
"""

import math
from dataclasses import dataclass
from datetime import date

from verify_lab.studies.futures_leverage.constants import CONTRACT_MULTIPLIER_HISTORY


@dataclass(frozen=True)
class IntegerContractPosition:
    """정수 계약으로 잡은 포지션.

    Attributes:
        equity: 자기자본 (원)
        target_multiple: 목표 배수 (인버스는 음수)
        price: 그날의 가격
        contract_multiplier: 거래승수
        notional: 1계약 명목금액 (원)
        contracts: 정수 계약 수. 인버스는 음수다
        exposure: 실제 노출 (원). 부호를 유지한다
        actual_multiple: 실제 배수 `노출 ÷ 자기자본`. 집행 불가면 NaN
        executable: 계약을 하나라도 살 수 있으면 True
    """

    equity: float
    target_multiple: float
    price: float
    contract_multiplier: float
    notional: float
    contracts: int
    exposure: float
    actual_multiple: float
    executable: bool


def contract_multiplier_on(product_id: str, target: date) -> float:
    """그 날짜에 적용되던 거래승수를 고른다.

    **만료 계약의 승수를 주는 조회가 없어 거래대금으로 역산해 확정한 값이다**
    (`docs/spec/futures_leverage.md` §5.5). 경계를 하루 잘못 잡으면 그날의 명목금액이
    두 배로 틀린다.

    Args:
        product_id: 선물 상품 코드
        target: 기준 날짜

    Returns:
        그날의 거래승수 (원)

    Raises:
        ValueError: 이력에 없는 상품이거나, 이력이 시작되기 전 날짜인 경우
    """
    history = CONTRACT_MULTIPLIER_HISTORY.get(product_id)
    if history is None:
        raise ValueError(f"거래승수 이력이 없는 상품입니다: {product_id} (있는 상품: {sorted(CONTRACT_MULTIPLIER_HISTORY)})")

    selected: int | None = None
    for effective_from, multiplier in history:
        if target >= effective_from:
            selected = multiplier

    if selected is None:
        raise ValueError(f"거래승수 이력이 시작되기 전 날짜입니다 - 상품: {product_id}, " f"날짜: {target}, 이력 시작: {history[0][0]}")

    return float(selected)


def integer_contract_position(
    equity: float, target_multiple: float, price: float, contract_multiplier: float
) -> IntegerContractPosition:
    """자기자본으로 목표 배수를 정수 계약으로 만들어 본다.

    목표 노출에 가장 가까운 정수 계약을 고르고 **실제 배수가 목표에서 얼마나 벗어나는지**
    를 낸다. 계약을 하나도 못 사면 「집행 불가」이며, 그때 실제 배수는 **0 이 아니라 NaN**
    이다 — 0 은 「배수 0 으로 굴렸다」로 읽히지만 실제로는 «그 규모에서는 할 수 없다» 는
    뜻이다 (측정의 원칙 17).

    Args:
        equity: 자기자본 (원). 0보다 커야 한다
        target_multiple: 목표 배수 (인버스는 음수). 0이 아니어야 한다
        price: 그날의 가격
        contract_multiplier: 거래승수

    Returns:
        정수 계약으로 잡은 포지션

    Raises:
        ValueError: 자기자본·가격·거래승수가 0 이하이거나, 목표 배수가 0 인 경우
    """
    if equity <= 0:
        raise ValueError(f"자기자본은 0보다 커야 합니다: {equity}")
    if target_multiple == 0:
        raise ValueError(f"목표 배수는 0이 아니어야 합니다: {target_multiple}")
    if price <= 0:
        raise ValueError(f"가격은 0보다 커야 합니다: {price}")
    if contract_multiplier <= 0:
        raise ValueError(f"거래승수는 0보다 커야 합니다: {contract_multiplier}")

    notional = price * contract_multiplier

    # 목표 노출에 가장 가까운 정수. **`round` 를 쓰지 않는다** — 짝수로 붙는 규칙이라
    # 정확히 0.5 인 경계에서 계약이 사라진다
    magnitude = abs(target_multiple) * equity / notional
    count = math.floor(magnitude + 0.5)

    sign = 1 if target_multiple > 0 else -1
    contracts = sign * count
    exposure = contracts * notional
    executable = count > 0

    return IntegerContractPosition(
        equity=equity,
        target_multiple=target_multiple,
        price=price,
        contract_multiplier=contract_multiplier,
        notional=notional,
        contracts=contracts,
        exposure=exposure,
        actual_multiple=exposure / equity if executable else math.nan,
        executable=executable,
    )
