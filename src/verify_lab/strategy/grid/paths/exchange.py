"""환전 경로 — 원화를 달러로 바꿔 들고 있다가 되판다

```
매수: 슬롯 금액에서 비용을 빼고 남은 원화로 당일 종가에 달러를 산다
매도: 보유 달러를 당일 종가로 원화로 바꾸고 비용을 뺀다
비용: (환전 스프레드 + 슬리피지) × 편도
```

**비용은 예산 안에서 나간다.** 배분 계층이 `Σ슬롯금액 + 잉여 == 총자산` 을 보장하므로
예산 밖에서 나가면 총액 보존이 깨진다. 실계좌 환전 영수증도 「낸 원화 999,987원(수수료 391원
**포함**)」으로 지불액 안에 수수료가 들어 있었다.

**환전 스프레드는 원화 금액에 곱한다.** 매매기준율 계열을 읽지 않는다 —
스프레드율의 **정의**가 매매기준율 대비인 것이지(기본 0.783% = 10.8원 ÷ 1,379.40원)
적용 대상이 매매기준율인 것이 아니다. 두 계열의 비율 차이가 중앙값 0.328% 라
어느 쪽에 곱하든 명목의 0.000262% 차이다.

**슬리피지는 체결가를 밀지 않고 비용 금액으로 처리한다.** 체결가를 밀면 명목이 종가에서
벗어나 **격자 이탈 보너스의 기준선이 흔들린다.** 비용으로 두면 한 곳에서 집계되고
명목은 종가 그대로 보존된다.

**달러 현금 잔고는 언제나 0이다** (사양서 §9.1). 산 달러는 전액 슬롯이 되고 슬롯이 팔리면
전액 원화가 된다. 보유 중 발생하는 RP 이자는 이 계층이 아니라 평가 계층의 몫이다.

**환차익은 비과세다** (사양서 §10). 매도에서 세금을 떼지 않는 것은 이 경로의 성질이며,
ETF 경로는 차익에 15.4% 가 붙는다.
"""

from dataclasses import dataclass
from typing import Final

from verify_lab.strategy.grid.paths.base import Acquisition, CostConfig, Liquidation

# 결과 표시와 요약에서 이 경로를 가리키는 이름
EXCHANGE_PATH_NAME: Final = "환전"


@dataclass(frozen=True)
class ExchangePath:
    """환전으로 달러를 사고파는 경로

    상태를 들지 않는다. 보유는 엔진이 슬롯으로 들고 있고, 이 객체는 비용률만 안다.

    Attributes:
        cost: 거래비용 파라미터. 이 경로가 쓰는 것은 환전 스프레드와 슬리피지 둘이다
    """

    cost: CostConfig

    @property
    def name(self) -> str:
        """경로 이름."""
        return EXCHANGE_PATH_NAME

    @property
    def one_way_cost_rate(self) -> float:
        """편도 비용률 (비율). 환전 스프레드와 슬리피지의 합이다."""
        return self.cost.exchange_spread_rate + self.cost.slippage_rate

    def acquire(self, budget: float, *, price: float) -> Acquisition:
        """예산에서 비용을 빼고 남은 원화로 달러를 산다.

        Args:
            budget: 배정된 슬롯 금액 (0 이상)
            price: 체결 환율 — 당일 정규장 종가 (양수)

        Returns:
            사들인 달러와 실제 지출·비용·명목. **지출은 언제나 예산과 같다**

        Raises:
            ValueError: 예산이 음수이거나 환율이 양수가 아닌 경우
        """
        _validate(budget, price=price, quantity_label="예산")

        cost = budget * self.one_way_cost_rate
        notional = budget - cost

        return Acquisition(units=notional / price, spent=budget, cost=cost, notional=notional)

    def liquidate(self, units: float, *, price: float) -> Liquidation:
        """보유 달러를 전부 원화로 바꾼다.

        Args:
            units: 팔 달러 (0 이상)
            price: 체결 환율 — 당일 정규장 종가 (양수)

        Returns:
            회수 원화와 비용·명목

        Raises:
            ValueError: 달러가 음수이거나 환율이 양수가 아닌 경우
        """
        _validate(units, price=price, quantity_label="보유 단위")

        notional = units * price
        cost = notional * self.one_way_cost_rate

        return Liquidation(proceeds=notional - cost, cost=cost, notional=notional)


def _validate(quantity: float, *, price: float, quantity_label: str) -> None:
    """집행 인자를 검사한다.

    Args:
        quantity: 예산 또는 보유 단위
        price: 체결 가격
        quantity_label: 예외 메시지에 쓸 수량의 이름

    Raises:
        ValueError: 수량이 음수이거나 가격이 양수가 아닌 경우
    """
    if quantity < 0:
        raise ValueError(f"{quantity_label}은 0 이상이어야 합니다: {quantity}")

    if price <= 0:
        raise ValueError(f"체결 가격은 양수여야 합니다: {price}")
