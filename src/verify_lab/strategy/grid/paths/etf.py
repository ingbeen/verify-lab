"""ETF 경로 — 원화로 미국달러선물 ETF 를 사고 되판다

```
매수: 예산에서 비용을 빼고 남은 원화로 **살 수 있는 만큼 정수 주식**을 산다
매도: 보유 주식을 당일 수정 종가로 팔고 비용과 차익 과세를 뺀다
비용: (위탁수수료 + 슬리피지) × 편도
세금: 매도 차익의 15.4%. 손실이면 0
```

**261240 과 261250 이 같은 구현을 쓴다.** 둘의 차이는 **어느 가격 계열을 넘기느냐**뿐이고,
노출 2배는 그 가격 자체에 이미 들어 있다 — 사양서 §9.2 의 「261250 은 슬롯 금액 전액 투입」이
곧 「배분은 같고 상품만 다르다」는 뜻이다.

**정수 주식 수만 산다** (사양서 §6.5·§15.2 #6). 못 쓴 예산은 **현금으로 남는다** —
사라지지도, 다음 레벨로 넘어가지도 않는다. 넘기면 체결 금액이 가격이 아니라 반올림에
의존하게 되어 규칙이 하나 늘어난다. 남은 현금은 원화 파킹 이자를 받으므로 버려지지 않는다.
중앙 슬롯 기준 잔액이 **0.15~0.25%** 로 왕복비용과 같은 자릿수라 무시할 수 없다.

**캐리·보수·롤오버·감쇠를 더하지도 빼지도 않는다** (사양서 §2.3·§15.2 #4·#5).
전부 **종가에 이미 내재**돼 있다. 보유 중 이자율이 0 인 것도, 실효 총비용을 별도로
차감하지 않는 것도 같은 이유다 — 빼면 이중차감이다.

**수정 종가를 쓴다** (사양서 §11.3). 원본가를 쓰면 분배락이 손실로 잡힌다.

**차익 과세는 매도 시점에 실현손익에 붙는다.** 취득원가는 **비용을 포함한 실제 지출**이라
매수 수수료가 과세 대상 차익을 줄인다.
"""

from dataclasses import dataclass
from typing import Final

from verify_lab.strategy.grid.constants import ETF_GAIN_TAX_RATE
from verify_lab.strategy.grid.paths.base import Acquisition, CostConfig, Liquidation

# 보유 중 붙는 이자율. 캐리가 종가에 내재돼 있어 **별도 가산이 금지**된다 (사양서 §15.2 #4)
ETF_HOLDING_INTEREST_RATE: Final = 0.0


@dataclass(frozen=True)
class EtfPath:
    """ETF 를 사고파는 경로

    상태를 들지 않는다. 보유는 엔진이 슬롯으로 들고 있고, 이 객체는 종목 이름과 비용률만 안다.

    Attributes:
        ticker: 종목 코드. 261240(1배) 또는 261250(2배)
        cost: 거래비용 파라미터. 이 경로가 쓰는 것은 위탁수수료와 슬리피지 둘이다
    """

    ticker: str
    cost: CostConfig

    @property
    def name(self) -> str:
        """경로 이름."""
        return self.ticker

    @property
    def one_way_cost_rate(self) -> float:
        """편도 비용률 (비율). 위탁수수료와 슬리피지의 합이다."""
        return self.cost.brokerage_rate + self.cost.slippage_rate

    def acquire(self, budget: float, *, price: float) -> Acquisition:
        """예산으로 살 수 있는 만큼 **정수 주식**을 산다.

        비용은 예산 안에서 나가고, 남은 돈으로 살 수 있는 주식 수를 내림한다.
        **못 쓴 예산은 지출에 포함되지 않아 현금으로 남는다.**

        Args:
            budget: 배정된 슬롯 금액 (0 이상)
            price: 체결 가격 — 당일 수정 종가 (양수)

        Returns:
            사들인 주식 수와 실제 지출·비용·명목. **지출은 예산 이하**이며,
            한 주도 못 사면 전부 0 이다

        Raises:
            ValueError: 예산이 음수이거나 가격이 양수가 아닌 경우
        """
        _validate(budget, price=price, quantity_label="예산")

        # 1. 비용을 뺀 뒤 살 수 있는 주식 수를 내림한다. 비용률이 명목 대비이므로
        #    한 주의 실질 단가는 `가격 × (1 + 비용률)` 이다
        unit_outlay = price * (1.0 + self.one_way_cost_rate)
        units = float(int(budget / unit_outlay))

        if units <= 0:
            return Acquisition(units=0.0, spent=0.0, cost=0.0, notional=0.0)

        notional = units * price
        cost = notional * self.one_way_cost_rate

        return Acquisition(units=units, spent=notional + cost, cost=cost, notional=notional)

    def liquidate(self, units: float, *, price: float, cost_basis: float = 0.0) -> Liquidation:
        """보유 주식을 전부 판다.

        **차익에 15.4% 가 붙는다.** 손실이면 0 이며, 결손금을 이월하지 않는다 —
        사양서가 규정하지 않았고 넣으면 경로마다 다른 새 규칙이 생긴다.

        Args:
            units: 팔 주식 수 (0 이상)
            price: 체결 가격 — 당일 수정 종가 (양수)
            cost_basis: 이 주식을 사는 데 실제로 나간 원화 (매수 비용 포함, 0 이상)

        Returns:
            회수 원화와 비용·세금·명목

        Raises:
            ValueError: 주식 수나 취득원가가 음수이거나 가격이 양수가 아닌 경우
        """
        _validate(units, price=price, quantity_label="보유 단위")

        if cost_basis < 0:
            raise ValueError(f"취득원가는 0 이상이어야 합니다: {cost_basis}")

        notional = units * price
        cost = notional * self.one_way_cost_rate

        # 2. 과세 대상은 **비용을 뺀 실현손익**이다. 매수·매도 수수료가 차익을 줄인다
        gain = notional - cost - cost_basis
        tax = max(gain, 0.0) * ETF_GAIN_TAX_RATE

        return Liquidation(proceeds=notional - cost - tax, cost=cost, tax=tax, notional=notional)

    def holding_interest_rate(self, market_rate: float) -> float:
        """보유 주식에 붙는 연 이자율을 낸다.

        **언제나 0 이다.** 캐리·보수·롤오버·감쇠가 전부 종가에 내재돼 있어 여기서 이자를 더하면
        사양서 §15.2 #4 의 「ETF 캐리 이중계산」이 된다.

        Args:
            market_rate: 그날의 시장 금리 (연%). 쓰지 않는다

        Returns:
            0
        """
        return ETF_HOLDING_INTEREST_RATE


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
