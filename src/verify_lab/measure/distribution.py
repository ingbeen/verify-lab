"""분배금 몫 — 원본가로 재서 생기는 왜곡의 크기

이 프로젝트는 **원본가**로 잰다 (루트 `CLAUDE.md` 측정의 원칙 14). 원본가는 배당·분배금을
조정하지 않으므로 지급일마다 가격이 계단으로 떨어지고, 그만큼 구간 수익률이 낮게 나온다.

**원칙 14 가 「배당락 규모를 결과 문서에 적는다」를 모든 검증에 요구하므로 공통 계층에 있다.**
검증 #8(레버리지 ETF 괴리)과 #9(선물 대 레버리지 ETF), 그리고 옵션 만기일 매매가 함께 쓴다.

**답하는 질문이 둘이고 축이 다르다.**

| 함수 | 축 | 묻는 것 |
| --- | --- | --- |
| `measure_distribution_share` | **종목 × 전 기간** | 이 상품이 한 해에 배당으로 얼마를 주나 |
| `dividend_impact` | **체결 구간** | 이 매매가 실제로 들고 있던 며칠에 배당락이 들어왔나 |

둘을 하나로 합칠 수 없다 — 앞은 배수 상품의 괴리를 총수익 기준으로 되돌리는 데 쓰고,
뒤는 **보유 구간 안에 배당락이 들어왔는지**를 묻는다. 연 3%를 주는 종목이라도 배당락일이
진입일 «당일»이면 진입가에 이미 반영돼 그 매매는 하나도 안 걸린다 — SPY·DIA 가 그 경우다.

> **부호 규약: 이 모듈의 「과소·과대」는 전부 «부호 있는 값» 기준이다.**
> 총 괴리 `C − A` 는 음수일 수 있고, 그때 「과소평가」는 «실제보다 더 작은(더 음수인) 값이
> 나온다» 는 뜻이다. 벌어진 **크기**(절대값) 기준으로 읽으면 같은 상황이 「과대」가 되므로,
> 두 말이 섞이지 않도록 한 규약으로 고정한다.

**그 왜곡은 1배와 배수 상품에 다른 크기로 걸린다.** 총 괴리를 총수익 기준으로 다시 쟀다면
얼마가 달라졌을지를 여기서 낸다.

총수익 기준 총 괴리를 `C' − A'` 라 하면

```
C' − A' = (C + d_target) − 배수 × (1배 수익률 + d_base)
        = (C − A) + (d_target − 배수 × d_base)
```

이므로 **배당 보정분 = `d_target − 배수 × d_base`** 다. 여기서 `d` 는 그 구간의 분배 기여이며,
수정주가와 원본가의 일간 수익률 차이를 쌓아서 구한다.

**인버스에서는 보정 방향이 뒤집힌다.** 배수가 음수면 `− 배수 × d_base` 가 양수가 되므로,
1배가 배당을 많이 줄수록 원본가로 잰 인버스의 괴리는 **과소평가**된다
(위 부호 규약대로 «부호 있는 값이 실제보다 작게 나온다» 는 뜻이다).

ETN 은 분배금을 지급하지 않고 지표가치에서 제비용만 차감하므로 `d_target` 이 0 이다.
수정주가 파일이 없는 것이 정상이며 결측이 아니다.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from verify_lab.common_constants import (
    ADJUSTED_FILE_TEMPLATE,
    COL_CLOSE,
    COL_DATE,
    MARKET_DIR,
    MARKET_FILE_TEMPLATE,
    RATE_TO_PERCENT,
)
from verify_lab.data.loader import load_market_csv
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 연율 환산에 쓰는 거래일 수. 미국·국내 모두 연 245~252일이며 관행값을 쓴다
TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class DistributionShare:
    """한 종목의 분배 기여.

    Attributes:
        ticker: 종목
        daily_contribution: 일간 평균 분배 기여 (비율)
        annual_contribution: 연율 환산 분배 기여 (비율)
        overlap_days: 원본가와 수정주가가 겹치는 거래일 수
        start_date: 겹치는 구간의 첫 거래일. 잰 구간이 어디인지 밝히기 위해 남긴다
        end_date: 겹치는 구간의 마지막 거래일
        measured: 실제로 쟀으면 True. 수정주가 파일이 없으면 False 이고 기여는 0 이다
    """

    ticker: str
    daily_contribution: float
    annual_contribution: float
    overlap_days: int
    start_date: pd.Timestamp | None
    end_date: pd.Timestamp | None
    measured: bool


def measure_distribution_share(ticker: str, market_dir: Path = MARKET_DIR) -> DistributionShare:
    """한 종목의 분배 기여를 원본가와 수정주가의 차이로 잰다.

    수정주가는 분배금을 재투자한 총수익 경로이므로, 두 계열의 **일간 수익률 차이**가
    곧 그날의 분배 기여다. 국내는 KRX 가 수정주가를 최근 3,000거래일만 주므로 겹치는
    구간이 원본가보다 짧을 수 있다 — 그래서 잰 구간을 함께 돌려준다.

    수정주가 파일이 없으면 **결측이 아니라 「분배금 없음」**으로 본다. ETN 이 여기 해당한다.

    Args:
        ticker: 종목 코드
        market_dir: 원시 시세 폴더

    Returns:
        분배 기여 요약

    Raises:
        ValueError: 원본가 파일이 없거나, 두 계열이 겹치는 거래일이 없는 경우
    """
    raw_path = market_dir / MARKET_FILE_TEMPLATE.format(ticker=ticker)
    adjusted_path = market_dir / ADJUSTED_FILE_TEMPLATE.format(ticker=ticker)

    if not raw_path.is_file():
        raise ValueError(f"원본가 파일이 없습니다: {raw_path}")

    if not adjusted_path.is_file():
        logger.debug(f"수정주가 파일이 없어 분배 기여를 0 으로 둡니다: {ticker} (ETN 은 분배금을 지급하지 않습니다)")
        return DistributionShare(
            ticker=ticker,
            daily_contribution=0.0,
            annual_contribution=0.0,
            overlap_days=0,
            start_date=None,
            end_date=None,
            measured=False,
        )

    raw = load_market_csv(raw_path)
    adjusted = load_market_csv(adjusted_path)

    merged = raw[[COL_DATE, COL_CLOSE]].merge(
        adjusted[[COL_DATE, COL_CLOSE]],
        on=COL_DATE,
        how="inner",
        suffixes=("_raw", "_adjusted"),
    )

    if len(merged) < 2:
        raise ValueError(f"원본가와 수정주가가 겹치는 거래일이 부족합니다 - 종목: {ticker}, 겹침: {len(merged)}일")

    raw_daily = merged[f"{COL_CLOSE}_raw"].pct_change()
    adjusted_daily = merged[f"{COL_CLOSE}_adjusted"].pct_change()
    contribution = (adjusted_daily - raw_daily).dropna()

    daily_contribution = float(contribution.mean())

    return DistributionShare(
        ticker=ticker,
        daily_contribution=daily_contribution,
        annual_contribution=daily_contribution * TRADING_DAYS_PER_YEAR,
        overlap_days=len(merged),
        start_date=merged[COL_DATE].iloc[0],
        end_date=merged[COL_DATE].iloc[-1],
        measured=True,
    )


@dataclass(frozen=True)
class DividendImpact:
    """체결 구간에 들어간 배당락의 크기.

    Attributes:
        measured_count: 실제로 대조한 체결 수. **진입 수보다 적을 수 있다** —
            수정주가가 그 구간을 덮지 못하면 건너뛰기 때문이며, 그 사실이 이 수로 드러난다
        hit_count: 배당락이 걸린 체결 수 (왜곡이 `HIT_THRESHOLD_PERCENT` 를 넘은 건)
        mean_percent: 전체 평균 왜곡 (%p). 잰 것이 없으면 `NaN` 이고 **0 이 아니다**
        max_abs_percent: 개별 체결의 최대 왜곡 크기 (%p). 잰 것이 없으면 `NaN`
    """

    measured_count: int
    hit_count: int
    mean_percent: float
    max_abs_percent: float


# 배당락이 「걸렸다」고 볼 왜곡의 하한 (%p). 두 계열의 부동소수점 차이가 1e-4 %p 수준이라
# 그보다 두 자리 위에 둔다. 국내 정수 가격의 반올림 잡음도 이 아래에 들어온다
HIT_THRESHOLD_PERCENT = 0.01


def dividend_impact(
    raw_close: pd.Series,
    adjusted_close: pd.Series,
    *,
    entry_dates: pd.DatetimeIndex,
    exit_dates: pd.DatetimeIndex,
    bet_down: bool,
) -> DividendImpact:
    """체결 구간마다 원본가와 수정주가의 수익률을 각각 내 그 차이를 잰다.

    수정주가는 배당을 되돌려 조정하므로 **두 값의 차이가 곧 그 구간에 들어간 배당락**이다.
    배율의 계단을 찾는 방법과 달리 **임계값을 정할 필요가 없고**, 그 매매가 실제로 잰 구간에만
    답한다 (`docs/매매/옵션_만기일/설계.md` 결정 ㊱).

    **부호는 방향에 따라 뜻이 반대다** (측정의 원칙 14). 「아래」 칸에서 양수면 원본가 성적이
    **과대평가**돼 있다 — 원본가에서 보이는 그 하락은 배당락이 만든 것이라 인버스로도
    공매도로도 못 먹는다. 「위」 칸이면 **과소평가**이며 실제로는 배당을 받아 보전된다.

    **수정주가가 덮지 못한 구간은 건너뛰되 센 수를 돌려준다.** 0 으로 채우면 「안 걸림」과
    「못 쟀다」가 구별되지 않고, 실제로 그렇게 새어 역방향이 신호 19건을 못 잰 채 0건으로 셌다
    (`.claude/rules/trading.md`).

    Args:
        raw_close: 원본가 종가. 날짜를 인덱스로 갖는다
        adjusted_close: 수정주가 종가. **전 구간을 덮지 않아도 된다**
        entry_dates: 체결의 진입일
        exit_dates: 같은 순서의 청산일
        bet_down: 아래로 거는 칸인지 여부

    Returns:
        구간에 들어간 배당락 요약

    Raises:
        ValueError: 진입과 청산의 개수가 다르거나 체결이 하나도 없는 경우
        RuntimeError: 체결 날짜가 원본가에 없는 경우 (그 시세에서 나온 체결이므로 있을 수 없다)
    """
    if len(entry_dates) != len(exit_dates):
        raise ValueError(f"진입과 청산의 개수가 다릅니다 - 진입: {len(entry_dates)}, 청산: {len(exit_dates)}")

    if len(entry_dates) == 0:
        raise ValueError("체결이 하나도 없습니다")

    # 원본가·수정주가 «둘 다»에 같은 부호를 곱하므로 차이에서 부호가 지워진다.
    # 그래서 방향은 결과의 부호만 뒤집고 크기는 바꾸지 않는다
    sign = -1.0 if bet_down else 1.0
    diffs: list[float] = []

    for entry_date, exit_date in zip(entry_dates, exit_dates, strict=True):
        if entry_date not in raw_close.index or exit_date not in raw_close.index:
            raise RuntimeError(f"내부 불변조건 위반 - 체결 날짜가 원본가에 없습니다: {entry_date} ~ {exit_date}")

        # 수정주가가 덮지 못하는 구간은 **지어내지 않고 건너뛴다**
        if entry_date not in adjusted_close.index or exit_date not in adjusted_close.index:
            continue

        raw_rate = float(raw_close[exit_date]) / float(raw_close[entry_date]) - 1.0
        adjusted_rate = float(adjusted_close[exit_date]) / float(adjusted_close[entry_date]) - 1.0
        diffs.append((raw_rate - adjusted_rate) * sign * RATE_TO_PERCENT)

    if not diffs:
        logger.debug(f"수정주가가 체결 구간을 하나도 덮지 못했습니다 (체결 {len(entry_dates)}건)")
        return DividendImpact(measured_count=0, hit_count=0, mean_percent=float("nan"), max_abs_percent=float("nan"))

    series = pd.Series(diffs, dtype=float)
    hit = series[series.abs() > HIT_THRESHOLD_PERCENT]

    return DividendImpact(
        measured_count=len(series),
        hit_count=len(hit),
        mean_percent=float(series.mean()),
        max_abs_percent=float(series.abs().max()),
    )


def dividend_adjustment(
    base_share: DistributionShare, target_share: DistributionShare, multiple: float, horizon: int
) -> float:
    """총수익 기준으로 다시 쟀다면 총 괴리가 얼마나 달라졌을지 낸다.

    `배당 보정분 = d_target − 배수 × d_base` 이며, `d` 는 구간 길이만큼 쌓은 분배 기여다.
    **인버스에서는 부호가 뒤집힌다** — 배수가 음수면 1배의 배당이 괴리를 키우는 쪽으로 작용한다.

    Args:
        base_share: 1배 상품의 분배 기여
        target_share: 배수 상품의 분배 기여
        multiple: 명목 배수
        horizon: 보유 기간 (거래일)

    Returns:
        총 괴리에 더해야 할 보정분 (비율). 양수면 원본가 기준 괴리가 **과소**평가돼 있다는 뜻이다

    Raises:
        ValueError: 보유 기간이 1 미만인 경우
    """
    if horizon < 1:
        raise ValueError(f"보유 기간은 1 이상이어야 합니다: {horizon}")

    base_contribution = base_share.daily_contribution * horizon
    target_contribution = target_share.daily_contribution * horizon

    return target_contribution - multiple * base_contribution
