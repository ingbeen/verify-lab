"""자금 배분 — 활성 레벨 하나에 얼마를 넣을지 정한다

```
위치       = ln(레벨가 / 하단) ÷ ln(상단 / 하단)          → 0(하단) ~ 1(상단)
슬롯금액_k = min( 총자산 × 배수_k ÷ Σ(활성 레벨 배수),  총자산 × 상한 )
잉여       = 총자산 − Σ(슬롯금액)                        → 원화현금에 남는다
```

**등비 격자를 로그로 재기 때문에 위치가 균등 간격이 된다**(사양서 §5.1). 가격 차이로 재면
같은 익절폭짜리 칸들이 위로 갈수록 넓어 보여 구간 배정이 왜곡된다.

**분모는 활성 레벨 전체이며 보유분을 포함한다**(결정 C4). 미보유 활성 레벨만 세면 보유가
늘수록 남은 슬롯이 커져 **하단에서 노출이 폭증**하는데, 자산곡선은 그럴듯해 보인다.
이 모듈의 함수는 **보유 상태를 인자로 받지 않아** 그 사고가 구조적으로 불가능하다.

**총자산은 계산하지 않고 받는다.** 시가평가는 평가 계층의 책임이며, 여기서 다시 구하면
같은 값이 두 곳에서 계산돼 조용히 갈라진다.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from verify_lab.strategy.grid.constants import GRID_ANCHOR_PRICE, LOWER_BAND_LIMIT, UPPER_BAND_LIMIT
from verify_lab.strategy.grid.lattice import level_price
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class AllocationResult:
    """하루치 슬롯 배분

    상한 적용 **이전** 금액을 함께 담는다. 상한이 얼마나 잘라냈는지는 이 둘의 차이로만
    알 수 있고, 사양서 §13.2 는 상한 발동 횟수를 필수 지표로 요구한다.

    Attributes:
        amounts: 레벨 k → 배정된 슬롯 금액
        uncapped_amounts: 레벨 k → 상한 적용 이전 금액. 합은 언제나 총자산이다
        multipliers: 레벨 k → 3구간 배수
        positions: 레벨 k → 로그 위치 (0=하단 ~ 1=상단)
        capped_levels: 상한이 걸린 레벨 k (오름차순)
        surplus: 배정되지 못하고 원화현금에 남는 몫. `Σamounts + surplus == 총자산`
    """

    amounts: dict[int, float]
    uncapped_amounts: dict[int, float]
    multipliers: dict[int, float]
    positions: dict[int, float]
    capped_levels: tuple[int, ...]
    surplus: float


def level_position(price: float, *, low: float, high: float) -> float:
    """범위 안에서 가격이 놓인 로그 위치를 낸다.

    하단이 정확히 0, 상단이 정확히 1 이다. **범위 밖 가격도 계산한다** — 하단 이탈 B안(G3)이
    격자를 아래로 연장하면 음수 위치가 실제로 생기며, 그 구간의 배수는 별도 규정(결정 C6)이다.

    Args:
        price: 위치를 잴 가격
        low: 범위 하단 (양수)
        high: 범위 상단 (하단보다 커야 한다)

    Returns:
        로그 위치. 하단에서 0, 상단에서 1

    Raises:
        ValueError: 하단이나 가격이 양수가 아니거나, 상단이 하단보다 크지 않은 경우
    """
    if low <= 0:
        raise ValueError(f"범위 하단은 양수여야 합니다: {low}")

    if price <= 0:
        raise ValueError(f"가격은 양수여야 합니다: {price}")

    if high <= low:
        raise ValueError(f"범위 상단은 하단보다 커야 합니다: 하단 {low}, 상단 {high}")

    return math.log(price / low) / math.log(high / low)


def band_multiplier(position: float, *, spread: float) -> float:
    """로그 위치가 속한 구간의 자금 배수를 낸다.

    구간은 **정확한 3등분**이며 경계값은 위 구간에 들어간다. 사양서 §5.1 의 0.33·0.67 은
    1/3·2/3 의 반올림 표기이고, 문자 그대로 쓰면 중간부만 0.34 폭이 되어
    「3구간 차등」이 균등 분할이 아니게 된다.

    배수는 `(1+s, 1.0, 1−s)` 로 1 을 중심으로 대칭이다. 비대칭으로 두면 숫자 두 개를
    각각 정당화해야 하므로 자유 파라미터가 늘어난다.

    Args:
        position: 로그 위치 (0=하단 ~ 1=상단). 범위 밖 값도 받는다
        spread: 차등 폭 (비율, 0.5 → 1.5 / 1.0 / 0.5). 0 이면 균등 배분이다

    Returns:
        자금 배수

    Raises:
        ValueError: 차등이 0 미만이거나 1 이상인 경우
    """
    if not 0.0 <= spread < 1.0:
        raise ValueError(f"자금 차등은 0 이상 1 미만이어야 합니다: {spread}")

    if position < LOWER_BAND_LIMIT:
        return 1.0 + spread

    if position < UPPER_BAND_LIMIT:
        return 1.0

    return 1.0 - spread


def allocate_slots(
    level_indices: Sequence[int],
    *,
    low: float,
    high: float,
    total_assets: float,
    growth_rate: float,
    anchor: float = GRID_ANCHOR_PRICE,
    spread: float,
    slot_cap_ratio: float,
) -> AllocationResult:
    """활성 레벨에 하루치 슬롯 금액을 배분한다.

    사양서 §5.2 대로 **매일 종가 확정 후 재계산**하는 것을 전제한다. 월 1회 재계산이면
    급락하는 달에 첫날 금액으로 마지막 날까지 매수하게 된다.

    **보유 여부를 받지 않는다.** 분모는 언제나 활성 레벨 전체다 (결정 C4).

    **상한 판정은 곱셈으로 한다.** 비중을 나눗셈으로 만들어 비교하면 정확히 상한과 같은 값이
    오발동해, 값은 그대로인 채 「상한 발동 횟수」만 늘어난다.

    Args:
        level_indices: 활성 레벨 번호 (오름차순). 비어 있으면 전액이 잉여다
        low: 범위 하단
        high: 범위 상단
        total_assets: 시가평가 총자산 (양수)
        growth_rate: 익절폭 g (비율)
        anchor: 격자의 앵커 가격
        spread: 자금 차등 폭 (비율)
        slot_cap_ratio: 슬롯 상한 (비율, 0.08 = 총자산의 8%)

    Returns:
        레벨별 슬롯 금액과 잉여·상한 발동 내역

    Raises:
        ValueError: 총자산이 양수가 아니거나, 상한이 0과 1 사이가 아니거나,
            범위·격자·차등이 유효하지 않은 경우
    """
    if total_assets <= 0:
        raise ValueError(f"총자산은 양수여야 합니다: {total_assets}")

    if not 0.0 < slot_cap_ratio <= 1.0:
        raise ValueError(f"슬롯 상한은 0 초과 1 이하여야 합니다: {slot_cap_ratio}")

    if not level_indices:
        return AllocationResult(
            amounts={},
            uncapped_amounts={},
            multipliers={},
            positions={},
            capped_levels=(),
            surplus=total_assets,
        )

    # 1. 위치와 배수. 범위 검증은 `level_position`, 차등 검증은 `band_multiplier` 가 한다
    positions = {
        index: level_position(level_price(index, growth_rate=growth_rate, anchor=anchor), low=low, high=high)
        for index in level_indices
    }
    multipliers = {index: band_multiplier(position, spread=spread) for index, position in positions.items()}

    # 2. 분모는 **활성 레벨 전체**의 배수 합이다. 차등 0 이 아니고서는 0 이 될 수 없다
    total_multiplier = sum(multipliers.values())
    if total_multiplier <= 0:
        raise RuntimeError(f"내부 불변조건 위반: 배수 합이 양수가 아닙니다 - 합 {total_multiplier}, 차등 {spread}")

    uncapped = {index: total_assets * multiplier / total_multiplier for index, multiplier in multipliers.items()}

    # 3. 상한을 건다. 잘린 몫은 사라지지 않고 잉여로 남아 원화현금에 머문다
    cap = total_assets * slot_cap_ratio
    amounts = {index: min(amount, cap) for index, amount in uncapped.items()}
    capped_levels = tuple(index for index, amount in uncapped.items() if amount > cap)

    surplus = total_assets - sum(amounts.values())

    if capped_levels:
        logger.debug(f"슬롯 상한 발동: {len(capped_levels)}개 레벨, 상한 {cap:,.0f}원, 잉여 {surplus:,.0f}원")

    return AllocationResult(
        amounts=amounts,
        uncapped_amounts=uncapped,
        multipliers=multipliers,
        positions=positions,
        capped_levels=capped_levels,
        surplus=surplus,
    )
