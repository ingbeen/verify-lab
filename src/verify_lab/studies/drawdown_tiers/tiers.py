"""하락_단계_매수 이벤트 정의 — 지표가 단계에 «처음 닿은 날»과 그 다음 거래일 종가 진입의 수익률

**신호는 구간마다 단계별로 한 번이다.** 구간은 지표가 다시 켜는 수준에 닿은 날 시작해 다음에 닿는 날 끝나고,
그 안에서 단계마다 처음 닿은 날이 신호다(설계 결정 Q7). 깊은 단계는 같은 날이거나 그 뒤에 닿는다.

| 경우 | 처리 | 근거 |
| --- | --- | --- |
| 데이터 첫 값이 이미 구간 안 | 처음 다시 켜질 때까지 판정하지 않고 그 날 수를 센다 | 구간이 언제 시작했는지 몰라 「처음 닿은 날」을 정할 수 없다 (D4 · D10) |
| 값이 없는 날 | 신호도 다시 켜기도 하지 않고 상태를 그대로 둔다 · 날 수를 센다 | 앞뒤 값으로 메우면 없던 값으로 판정한다 (D5 · 절대 원칙 3) |
| 판정일 | 대상의 거래일 | 지표의 다른 날 값은 쓰지 않는다 (D5) |

**진입은 판정일 다음 거래일 종가다** (D1) — VIX 종가는 ETF 종가보다 늦게 확정되고 공포탐욕지수도 장 마감 뒤에
나와, 판정일 종가에 사면 그날 알 수 없던 값으로 산 것이 된다. **측정과 체결이 같은 진입점을 쓴다.**

판정은 그날까지의 값만 본다 — 누적 최고가 · 누적 합이라 뒤를 잘라도 앞의 신호가 그대로다(look-ahead 감시 테스트).
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_DATE, COL_VALUE
from verify_lab.data.loader import validate_market_frame
from verify_lab.measure.calendar_entry import validate_trading_days
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_ENTRY_CLOSE,
    COL_EXCLUDED_REASON,
    COL_EXIT_CLOSE,
    COL_EXIT_DATE,
    COL_FORWARD_RETURN,
    COL_HORIZON,
    REASON_NONE,
    REASON_OUT_OF_RANGE,
)
from verify_lab.measure.forward_return import ReturnBasis
from verify_lab.studies.drawdown_tiers.constants import (
    COL_ENTRY_DATE,
    COL_INDICATOR_VALUE,
    COL_TIER,
    DRAWDOWN_DECIMALS,
    REASON_BEFORE_LISTING,
    TierRule,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 신호 표의 컬럼과 dtype — 빈 결과에서도 같은 스키마
SIGNAL_DTYPES = {
    COL_DATE: "datetime64[ns]",
    COL_TIER: "float64",
    COL_INDICATOR_VALUE: "float64",
}

# 수익률 long-form 의 컬럼 순서 — 판정일 · 진입 · 청산 원자료 뒤에 `summarize` 가 요구하는 축
RETURN_COLUMNS = [
    COL_DATE,
    COL_ENTRY_DATE,
    COL_EXIT_DATE,
    COL_ENTRY_CLOSE,
    COL_EXIT_CLOSE,
    COL_BASIS,
    COL_HORIZON,
    COL_FORWARD_RETURN,
    COL_EXCLUDED_REASON,
]


@dataclass(frozen=True)
class TierSignals:
    """지표 하나의 단계 신호

    Attributes:
        signals: 신호마다 한 행 — 판정일 · 단계 · 그날의 지표 값. 판정일 → 규칙의 단계 순
        missing_days: 값이 없어 판정하지 않은 날 수 (D5)
        unjudged_days: 값은 있지만 시작을 모르는 첫 구간이라 판정하지 않은 날 수 (D4)
    """

    signals: pd.DataFrame
    missing_days: int
    unjudged_days: int


def drawdown_rates(close: pd.Series) -> pd.Series:
    """그날까지의 역대 최고 종가 대비 낙폭 (비율, 0 이하).

    Args:
        close: 날짜를 인덱스로 단 종가. 날짜 오름차순 · 중복 없음

    Returns:
        같은 인덱스의 낙폭. `DRAWDOWN_DECIMALS` 자리에서 끊는다 — 단계 경계가 부동소수점 잡음에 갈리지 않게

    Raises:
        ValueError: 비었거나 날짜 순서 · 중복 조건을 어긴 경우
    """
    _require_ordered(close)

    return (close / close.cummax() - 1.0).round(DRAWDOWN_DECIMALS)


def peak_dates(close: pd.Series) -> pd.Series:
    """날마다 그날이 속한 하락장의 시작일 — 그날까지 마지막으로 역대 최고 종가였던 날 (D6).

    **낙폭이 0 인 날이 고점이다** — 단계를 다시 켜는 날과 같은 판정이라 구간과 사건이 어긋나지 않는다.

    Args:
        close: 날짜를 인덱스로 단 종가. 날짜 오름차순 · 중복 없음

    Returns:
        같은 인덱스의 시작일

    Raises:
        ValueError: 비었거나 날짜 순서 · 중복 조건을 어긴 경우
    """
    at_peak = drawdown_rates(close) >= 0.0
    dates = pd.Series(close.index, index=close.index)

    return dates.where(at_peak).ffill()


def align_indicator(trading_days: pd.DatetimeIndex, indicator: pd.DataFrame) -> pd.Series:
    """지표를 대상 거래일 위에 놓는다 — 판정 기간은 지표 첫날부터다 (D5 · D8).

    거래일에 값이 없는 날은 비워 두고(메우지 않는다), 거래일이 아닌 날의 지표 값은 쓰지 않는다.

    Args:
        trading_days: 대상의 거래일. 오름차순 · 중복 없음
        indicator: 날짜 · 값 두 칸의 지표 (`load_series_csv` · `load_close_series` 의 모양)

    Returns:
        지표 첫날 이후 거래일을 인덱스로 단 값

    Raises:
        ValueError: 거래일 목록이나 지표가 조건을 어긴 경우, 지표 첫날 뒤에 거래일이 없는 경우
    """
    validate_trading_days(trading_days, purpose="판정일")
    validate_market_frame(indicator, [COL_DATE, COL_VALUE])

    first_day = indicator[COL_DATE].iloc[0]
    days = trading_days[trading_days >= first_day]
    if len(days) == 0:
        raise ValueError(f"지표 첫날({first_day.date()}) 뒤에 대상 거래일이 없습니다 — 대상 마지막 거래일 {trading_days[-1].date()}")

    return indicator.set_index(COL_DATE)[COL_VALUE].reindex(days)


def tier_signals(values: pd.Series, rule: TierRule) -> TierSignals:
    """구간마다 단계별로 처음 닿은 날을 찾는다.

    Args:
        values: 판정일을 인덱스로 단 지표 값. 값이 없는 날은 비어 있다
        rule: 단계 규칙

    Returns:
        신호와 판정하지 않은 날 수

    Raises:
        ValueError: 인덱스가 날짜가 아니거나 비었거나 순서 · 중복 조건을 어긴 경우
    """
    _require_ordered(values)

    valid = values.notna()
    if rule.fires_below:
        rearm = values >= rule.rearm_level
    else:
        rearm = values < rule.rearm_level

    # 다시 켠 날마다 구간 번호가 하나 오름 → 첫 다시 켜기 전(0)은 시작을 모르는 구간
    episode = rearm.astype("int64").cumsum()
    judged = episode > 0

    blocks: list[pd.DataFrame] = []
    for order, level in enumerate(rule.levels):
        hit = (values <= level) if rule.fires_below else (values >= level)
        fired = hit & judged
        # 구간 번호가 처음 나온 닿은 날만 — 닿지 않은 날은 비워 두고 세지 않음
        first = fired & ~episode.where(fired).duplicated(keep="first")
        days = values.index[first.to_numpy()]
        # 빈 조각을 이어 붙이면 pandas 가 날짜 칸의 단위를 잃음
        if len(days) == 0:
            continue
        blocks.append(
            pd.DataFrame(
                {
                    COL_DATE: days,
                    COL_TIER: level,
                    COL_INDICATOR_VALUE: values.loc[days].to_numpy(dtype=float),
                    "_order": order,
                }
            )
        )

    if blocks:
        combined = pd.concat(blocks, ignore_index=True).sort_values([COL_DATE, "_order"], kind="stable")
        signals = combined[list(SIGNAL_DTYPES)].astype(SIGNAL_DTYPES).reset_index(drop=True)
    else:
        signals = pd.DataFrame({column: pd.Series(dtype=dtype) for column, dtype in SIGNAL_DTYPES.items()})

    missing_days = int((~valid).sum())
    unjudged_days = int((valid & ~judged).sum())
    logger.debug(
        f"단계 신호: {rule.indicator} {len(signals):,}건, 다시 켠 날 {int(rearm.sum()):,}일, "
        f"빠진 날 {missing_days:,} · 판정하지 않은 날 {unjudged_days:,}"
    )

    return TierSignals(signals=signals, missing_days=missing_days, unjudged_days=unjudged_days)


def entry_returns(
    prices: pd.DataFrame,
    signal_dates: pd.DatetimeIndex,
    *,
    horizons: Sequence[int],
    price_column: str,
) -> pd.DataFrame:
    """판정일 다음 거래일 종가에 사서 보유 기간 뒤 거래일 종가에 판 수익률 (long-form) (D1).

    **행을 지우지 않는다** — 판정일 × 보유 기간마다 한 행이고, 잴 수 없는 행은 값을 비우고 사유를 단다.

    | 사유 | 경우 |
    | --- | --- |
    | `REASON_BEFORE_LISTING` | 판정일이 대상 첫 거래일 앞 (D11) |
    | `REASON_OUT_OF_RANGE` | 진입일이나 청산일이 데이터 끝을 넘음 — 판정일이 대상 마지막 거래일 뒤인 것도(대상 사본이 신호 대상보다 짧다) |

    Args:
        prices: 날짜 오름차순 대상 가격. 시세(`Close`) 또는 종가 계열(`Value`)
        signal_dates: 판정일. 오름차순 · 중복 없음
        horizons: 보유 기간 (거래일)
        price_column: 가격 컬럼 이름

    Returns:
        `RETURN_COLUMNS` 순서 · 판정일 → 보유 기간 오름차순. 진입일이 있으면 끝 넘김 행에도 진입 값이 남는다

    Raises:
        ValueError: 가격이 조건을 어겼거나, 보유 기간이 비었거나 1 미만이거나,
            판정일이 순서 · 중복 조건을 어겼거나, 상장 뒤인데 대상 거래일이 아닌 판정일이 있는 경우
    """
    validate_market_frame(prices, [COL_DATE, price_column])
    holds = sorted(horizons)
    if not holds or holds[0] < 1:
        raise ValueError(f"보유 기간은 1 거래일 이상이 하나 이상 있어야 합니다: {list(horizons)}")
    if not signal_dates.is_monotonic_increasing or signal_dates.has_duplicates:
        raise ValueError("판정일은 오름차순이고 중복이 없어야 합니다")

    trading_days = pd.DatetimeIndex(prices[COL_DATE])
    closes = prices[price_column].to_numpy(dtype=float)
    count = len(trading_days)

    before = np.asarray(signal_dates < trading_days[0])
    after = np.asarray(signal_dates > trading_days[-1])
    positions = np.asarray(trading_days.get_indexer(signal_dates), dtype=np.int64)
    # 마지막 거래일 뒤의 판정일은 진입 위치를 데이터 밖에 둠 — 찾지 못한 위치(−1)에 1을 더하면 첫 행이 진입일이 됨
    positions = np.where(after, count, positions)
    unknown = ~before & ~after & (positions < 0)
    if unknown.any():
        raise ValueError(
            f"판정일이 대상의 거래일에 없습니다: {[day.date().isoformat() for day in signal_dates[unknown][:5]]} — "
            "신호 대상과 측정 대상의 거래일이 어긋납니다"
        )

    # 판정일 × 보유 기간 — 판정일이 바깥, 보유가 안쪽 순서
    signal_count = len(signal_dates)
    hold = np.tile(np.asarray(holds, dtype=np.int64), signal_count)
    listed = np.repeat(~before, len(holds))
    entry = np.repeat(positions + 1, len(holds))
    exit_ = entry + hold
    has_entry = listed & (entry < count)
    usable = listed & (exit_ < count)

    entry_close = np.where(has_entry, closes[np.minimum(entry, count - 1)], np.nan)
    exit_close = np.where(usable, closes[np.minimum(exit_, count - 1)], np.nan)
    day_values = trading_days.to_numpy()
    not_a_time = np.datetime64("NaT", "ns")

    frame = pd.DataFrame(
        {
            COL_DATE: np.repeat(signal_dates.to_numpy(), len(holds)),
            COL_ENTRY_DATE: np.where(has_entry, day_values[np.minimum(entry, count - 1)], not_a_time),
            COL_EXIT_DATE: np.where(usable, day_values[np.minimum(exit_, count - 1)], not_a_time),
            COL_ENTRY_CLOSE: entry_close,
            COL_EXIT_CLOSE: exit_close,
            COL_BASIS: ReturnBasis.CLOSE.value,
            COL_HORIZON: hold,
            COL_FORWARD_RETURN: exit_close / entry_close - 1.0,
            COL_EXCLUDED_REASON: np.where(
                listed, np.where(usable, REASON_NONE, REASON_OUT_OF_RANGE), REASON_BEFORE_LISTING
            ),
        }
    )

    if frame.loc[usable, COL_FORWARD_RETURN].isna().any():
        raise RuntimeError("내부 불변조건 위반: 제외되지 않은 행의 수익률이 비어 있습니다")

    return frame[RETURN_COLUMNS]


def baseline_returns(
    prices: pd.DataFrame,
    *,
    start: pd.Timestamp,
    horizons: Sequence[int],
    price_column: str,
) -> pd.DataFrame:
    """기준선 — 판정할 수 있는 기간의 모든 대상 거래일을 신호와 같은 진입 규칙으로 잰다 (D8).

    Args:
        prices: 날짜 오름차순 대상 가격
        start: 판정할 수 있는 첫날 (지표 첫날). 대상 상장 전이면 대상 첫 거래일부터다
        horizons: 보유 기간 (거래일)
        price_column: 가격 컬럼 이름

    Returns:
        `entry_returns` 와 같은 모양

    Raises:
        ValueError: `entry_returns` 가 거부하는 경우, 시작일 뒤에 대상 거래일이 없는 경우
    """
    validate_market_frame(prices, [COL_DATE, price_column])
    trading_days = pd.DatetimeIndex(prices[COL_DATE])
    dates = trading_days[trading_days >= start]
    if len(dates) == 0:
        raise ValueError(f"기준선 시작일({start.date()}) 뒤에 대상 거래일이 없습니다")

    return entry_returns(prices, dates, horizons=horizons, price_column=price_column)


def _require_ordered(values: pd.Series) -> None:
    """날짜 인덱스가 판정의 전제를 만족하는지 본다 — 「처음 닿은 날」 · 누적 최고가가 날짜 순서에 기댄다.

    Raises:
        ValueError: 인덱스가 날짜가 아니거나 비었거나 오름차순 · 중복 조건을 어긴 경우
    """
    if not isinstance(values.index, pd.DatetimeIndex):
        raise ValueError(f"인덱스가 날짜가 아닙니다: {type(values.index).__name__}")
    validate_trading_days(values.index, purpose="판정일")
