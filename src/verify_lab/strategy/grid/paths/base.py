"""집행 경로의 계약 — 예산 하나로 무엇을 얼마나 사는가

격자·범위·배분·체결 판정은 **어느 레벨을 사고 파는가**까지를 답한다.
거기서부터 **그 예산으로 실제 무엇을 얼마나 사는가**가 경로의 일이다.

경로마다 갈리는 것은 다섯이다.

| | 환전 | ETF |
| --- | --- | --- |
| 무엇을 들고 있나 | 달러 | 주식 수 |
| 비용이 어떻게 붙나 | 환전 스프레드 + 슬리피지 | 위탁수수료 + 슬리피지 |
| 예산을 다 쓸 수 있나 | 쓴다 | **못 쓴다** — 정수 주식 수라 남는다 |
| 매도 차익에 세금이 붙나 | **아니다** (환차익 비과세) | 15.4% |
| 보유 중 이자를 받나 | 달러 RP 이자 | **아니다** — 캐리가 종가에 내재돼 있다 |

**세금과 보유 이자도 경로가 답한다.** 엔진이 경로 종류로 분기하면 매수·매도·이자 세 자리에
각각 분기가 생기고, 그중 한 곳만 고쳐질 때 **예외 없이 결과만 틀린다.**

**예산과 지출을 분리한다.** 환전 경로에서 둘이 같은 것은 그 경로의 성질이지 계약이 아니다.
엔진이 예산을 현금에서 빼면 「예산 = 지출」이 엔진에 박히고, 그 가정이 깨지는 경로가 왔을 때
**예외 없이 현금이 틀린다.**

**명목을 함께 돌려준다.** 격자 이탈 보너스(사양서 §6.4)는 「지정가 운용이었다면」과의 차이인데,
지정가 운용도 같은 비용을 물므로 비용은 상쇄된다. 비용 후 금액으로 재면 §15.3 의
「총수익의 30% 초과」 판정이 다른 것을 재게 된다.

**평가 함수를 두지 않는다.** 보유 평가액은 세 경로 모두 `보유 단위 × 그날 가격` 이고,
다른 것은 **어느 가격 계열을 쓰는가**인데 그것은 엔진의 입력이지 경로의 메서드가 아니다.

**격자 판정에 쓰는 가격과 집행 가격은 다르다.** 격자·범위·하향 돌파는 **원달러 종가**로
판정하고(결정 C1·C17), 여기 들어오는 `price` 는 **집행 가격**이다. 환전 경로에서는 둘이 같고
ETF 경로에서는 갈라진다. 단일 정의라야 세 경로가 **같은 날 같은 판정**을 받는다.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CostConfig:
    """거래비용 파라미터

    값의 출처는 사양서 §10 이며 환전 스프레드는 실계좌 실측으로 바뀌었다 (결정 C35).

    Attributes:
        exchange_spread_rate: 환전 스프레드 편도 (비율). 환전 경로에만 붙는다
        slippage_rate: 슬리피지 편도 (비율). **전 경로 공통**이며 실측되지 않은 가정이다
        brokerage_rate: ETF 위탁수수료 편도 (비율). ETF 경로에만 붙는다
    """

    exchange_spread_rate: float
    slippage_rate: float
    brokerage_rate: float

    def __post_init__(self) -> None:
        """비용률을 즉시 검사한다.

        Raises:
            ValueError: 비용률이 0 이상 1 미만이 아닌 경우
        """
        rates = (
            ("환전 스프레드", self.exchange_spread_rate),
            ("슬리피지", self.slippage_rate),
            ("위탁수수료", self.brokerage_rate),
        )
        for name, rate in rates:
            if not 0.0 <= rate < 1.0:
                raise ValueError(f"{name}은 0 이상 1 미만이어야 합니다: {rate}")


@dataclass(frozen=True)
class Acquisition:
    """매수 집행 하나의 결과

    `spent == notional + cost` 가 언제나 성립한다. `spent` 는 예산 **이하**다 —
    경로가 예산을 다 쓰지 못할 수 있기 때문이다.

    Attributes:
        units: 사들인 보유 단위 (환전은 달러, ETF 는 주식 수)
        spent: 실제로 나간 원화. **비용을 포함한다**
        cost: 그중 거래비용
        notional: 비용 전 명목 (`units × 체결가`)
    """

    units: float
    spent: float
    cost: float
    notional: float


@dataclass(frozen=True)
class Liquidation:
    """매도 집행 하나의 결과

    `proceeds == notional − cost − tax` 가 언제나 성립한다.

    Attributes:
        proceeds: 실제로 들어온 원화. **비용과 세금을 뺀 값이다**
        cost: 거래비용
        tax: 매매 차익 과세액. **환전 경로는 환차익 비과세라 언제나 0** 이다
        notional: 비용 전 명목 (`units × 체결가`)
    """

    proceeds: float
    cost: float
    tax: float
    notional: float


class ExecutionPath(Protocol):
    """슬롯 하나를 사고파는 방법

    구현체는 **상태를 들지 않는다.** 보유는 엔진이 슬롯으로 들고 있고, 경로는
    「이 예산으로 이 가격에 사면 무엇이 남는가」와 「이 단위를 이 가격에 팔면 얼마가 들어오는가」에만 답한다.
    같은 입력에 언제나 같은 출력을 내야 한다.
    """

    @property
    def name(self) -> str:
        """경로 이름. 결과 표시와 요약에서 어느 경로의 곡선인지 밝히는 데 쓴다."""
        ...

    def acquire(self, budget: float, *, price: float) -> Acquisition:
        """예산으로 살 수 있는 만큼 산다.

        Args:
            budget: 배정된 슬롯 금액 (0 이상)
            price: 집행 가격 (양수)

        Returns:
            사들인 단위와 실제 지출·비용·명목

        Raises:
            ValueError: 예산이 음수이거나 가격이 양수가 아닌 경우
        """
        ...

    def liquidate(self, units: float, *, price: float, cost_basis: float) -> Liquidation:
        """보유 단위를 전부 판다.

        **취득원가를 함께 받는다.** 매매 차익 과세가 경로마다 다르므로(환차익 0%, ETF 15.4%)
        경로가 자기 세금을 계산하려면 무엇에 얼마를 넣었는지 알아야 한다.

        Args:
            units: 팔 보유 단위 (0 이상)
            price: 집행 가격 (양수)
            cost_basis: 이 단위를 사는 데 실제로 나간 원화 (비용 포함, 0 이상)

        Returns:
            회수 원화와 비용·세금·명목

        Raises:
            ValueError: 단위나 취득원가가 음수이거나 가격이 양수가 아닌 경우
        """
        ...

    def holding_interest_rate(self, market_rate: float) -> float:
        """보유 단위에 붙는 연 이자율을 낸다.

        **경로가 답한다.** 환전 경로는 달러를 들고 있으므로 RP 금리를 그대로 받지만,
        ETF 경로는 캐리·보수가 **종가에 이미 내재**돼 있어 0 이다 — 여기서 이자를 더하면
        사양서 §15.2 #4 의 「ETF 캐리 이중계산」이 된다.

        Args:
            market_rate: 그날의 시장 금리 (연%)

        Returns:
            이 경로의 보유 단위에 적용할 연 이자율 (연%)
        """
        ...
