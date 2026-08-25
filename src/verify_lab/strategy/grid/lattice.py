"""등비 격자 — 그리드의 좌표계

`레벨_k = 앵커 × (1+g)^k` 로 정의되는 **영구 고정 가격표**다. 범위(동적 범위)는
어느 레벨을 켤지만 정하고, **레벨 가격 자체는 절대 바뀌지 않는다.**

범위 하단 기준으로 레벨을 재생성하면 재조정 때마다 격자가 미세하게 어긋나
**기존 보유 슬롯 바로 옆에 유령 레벨이 생기고 중복 매수가 누적된다**(사양서 §3.2).
고정 격자는 이 사고가 구조적으로 발생하지 않는다.

**경계 판정을 로그 추정에 맡기지 않는다.** 범위 하단이 레벨가와 정확히 같을 때
`ceil(log(하단/앵커) / log(1+g))` 는 부동소수점 오차로 한 칸 밀린다 —
g=0.008 에서 k=-40~39 의 경계 80개 중 28개가 어긋나는 것을 실측했다. 레벨 하나가
조용히 사라지면 슬롯 금액의 분모(활성 레벨 배수 합)가 달라져 전 구간의 자금 배분이 틀어지고,
예외는 나지 않는다. 그래서 로그로 후보만 잡고 **레벨가를 직접 비교해 앞뒤로 보정**한다.
"""

import math

from verify_lab.strategy.grid.constants import GRID_ANCHOR_PRICE
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)


def level_price(index: int, *, growth_rate: float, anchor: float = GRID_ANCHOR_PRICE) -> float:
    """레벨 하나의 가격을 낸다.

    **반올림하지 않는다.** 미리 반올림하면 `목표가 / 레벨가 - 1 == g` 가 레벨마다 미세하게
    깨져 익절폭이 칸마다 달라진다. 자릿수는 저장·표시 직전에만 적용한다.

    Args:
        index: 레벨 번호 k. 음수를 허용하며 앵커가 k=0 이다
        growth_rate: 익절폭 g (비율, 0.008 = 0.8%)
        anchor: 격자의 앵커 가격

    Returns:
        레벨 가격

    Raises:
        ValueError: 익절폭이 0과 1 사이가 아니거나 앵커가 양수가 아닌 경우
    """
    _validate_lattice(growth_rate=growth_rate, anchor=anchor)

    return anchor * (1.0 + growth_rate) ** index


def target_price(index: int, *, growth_rate: float, anchor: float = GRID_ANCHOR_PRICE) -> float:
    """레벨 하나의 매도 목표가를 낸다.

    목표가는 **언제나 바로 위 칸**(`레벨_(k+1)`)이며 **실제 매수 체결가와 무관하다**
    (사양서 §3.3). 종가 체결 가정에서는 체결가가 레벨가보다 낮을 수 있는데,
    그 차이는 격자 이탈 보너스로 따로 집계할 몫이지 목표가를 옮길 이유가 아니다.

    Args:
        index: 레벨 번호 k
        growth_rate: 익절폭 g (비율)
        anchor: 격자의 앵커 가격

    Returns:
        매도 목표가

    Raises:
        ValueError: 익절폭이 0과 1 사이가 아니거나 앵커가 양수가 아닌 경우
    """
    return level_price(index + 1, growth_rate=growth_rate, anchor=anchor)


def active_level_indices(
    low: float,
    high: float,
    *,
    growth_rate: float,
    anchor: float = GRID_ANCHOR_PRICE,
) -> list[int]:
    """범위 안에 있는 레벨의 번호를 오름차순으로 낸다.

    **양끝을 포함한다** — 범위 경계가 레벨가와 정확히 같으면 그 레벨은 켜진다.
    최소 범위폭 강제(사양서 §4.2)가 만들어 내는 하단·상단은 계산값이라 레벨가와
    맞아떨어지는 일이 실제로 생기며, 그때만 레벨이 하나 사라지면 원인을 알 수 없는 차이가 남는다.

    오름차순 계약은 **현금 부족 시 아래(싼) 레벨부터 체결**하는 결정 C5 가 그대로 기댄다.

    Args:
        low: 범위 하단 (양수)
        high: 범위 상단 (하단 이상)
        growth_rate: 익절폭 g (비율)
        anchor: 격자의 앵커 가격

    Returns:
        `low` 이상 `high` 이하인 레벨의 번호 k 오름차순 목록.
        범위 안에 레벨이 없으면 빈 목록 — 이것은 "매수할 곳이 없다"는 정상 상태다

    Raises:
        ValueError: 하단이 양수가 아니거나, 상단이 하단보다 낮거나,
            익절폭·앵커가 유효하지 않은 경우
    """
    _validate_lattice(growth_rate=growth_rate, anchor=anchor)

    if low <= 0:
        raise ValueError(f"범위 하단은 양수여야 합니다: {low}")

    if high < low:
        raise ValueError(f"범위 상단이 하단보다 낮습니다: 하단 {low}, 상단 {high}")

    step = math.log1p(growth_rate)

    # 1. 로그로 후보를 잡는다. 이 값은 경계에서 한 칸 밀릴 수 있으므로 **추정일 뿐**이다
    lowest = math.ceil(math.log(low / anchor) / step)
    highest = math.floor(math.log(high / anchor) / step)

    # 2. 레벨가를 직접 비교해 보정한다. 두 루프의 방향이 반대라 순서대로 돌리면
    #    `레벨(lowest-1) < low <= 레벨(lowest)` 가 성립한 채로 끝난다
    while level_price(lowest - 1, growth_rate=growth_rate, anchor=anchor) >= low:
        lowest -= 1
    while level_price(lowest, growth_rate=growth_rate, anchor=anchor) < low:
        lowest += 1

    while level_price(highest + 1, growth_rate=growth_rate, anchor=anchor) <= high:
        highest += 1
    while level_price(highest, growth_rate=growth_rate, anchor=anchor) > high:
        highest -= 1

    if highest < lowest:
        logger.debug(f"범위 안에 레벨이 없습니다: 하단 {low}, 상단 {high}, 익절폭 {growth_rate}")
        return []

    return list(range(lowest, highest + 1))


def _validate_lattice(*, growth_rate: float, anchor: float) -> None:
    """격자를 정의하는 두 값을 검사한다.

    Args:
        growth_rate: 익절폭 g (비율)
        anchor: 격자의 앵커 가격

    Raises:
        ValueError: 익절폭이 0과 1 사이가 아니거나 앵커가 양수가 아닌 경우
    """
    if not 0.0 < growth_rate < 1.0:
        raise ValueError(f"익절폭은 0과 1 사이여야 합니다: {growth_rate}")

    if anchor <= 0:
        raise ValueError(f"격자의 앵커는 양수여야 합니다: {anchor}")
