"""분배금 몫 — 원본가로 재서 생기는 왜곡의 크기

이 프로젝트는 **원본가**로 잰다 (루트 `CLAUDE.md` 측정의 원칙 14). 원본가는 배당·분배금을
조정하지 않으므로 지급일마다 가격이 계단으로 떨어지고, 그만큼 구간 수익률이 낮게 나온다.

**원칙 14 가 「배당락 규모를 결과 문서에 적는다」를 모든 검증에 요구하므로 공통 계층에 있다.**
검증 #8(레버리지 ETF 괴리)과 #9(선물 대 레버리지 ETF)가 함께 쓴다.

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

from verify_lab.common_constants import ADJUSTED_FILE_TEMPLATE, COL_CLOSE, COL_DATE, MARKET_DIR, MARKET_FILE_TEMPLATE
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
