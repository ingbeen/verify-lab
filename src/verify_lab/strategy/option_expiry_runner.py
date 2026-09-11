"""옵션 만기일 매매 실행 — 대상 칸을 순회해 성적표와 원자료를 조립한다

이 모듈은 **매매 규칙을 계산하지 않는다.** 만기일과 청산일은 `studies.option_expiry` 가,
체결은 `strategy/trade_fill.py` 가 이미 하므로, 하는 일은 그것을 조합해 돌리고 사람이 읽을 형태로
쌓는 것이다.

**손절선은 확정값 하나다** (`EXPIRY_STOP_LEVEL`). `.claude/rules/strategy.md` 가
`strategy/` 계층에 한해 파라미터 확정을 허용하며, 값을 고른 근거와 탈락안은
`docs/research/옵션_만기일.md` 12B 와 `docs/spec/옵션_만기일_설계.md` 결정 ㊴ 에 있다.
**값을 옮겨 가며 성적을 보는 노브를 만들지 않는다** — 그것이 과최적화다.

**격자는 지우지 않고 옵션으로 남긴다.** `stop_levels` 에 여러 값을 넘기면 손절선마다
행이 늘어난 비교표가 나온다. **시세를 재수집하면 「평평한 구간」을 다시 찾아야 하기 때문**이며,
그때 무손절(`None`)을 함께 넣어 손절이 무엇을 막았는지 대조한다.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE, MARKET_DIR, RATE_TO_PERCENT
from verify_lab.data.loader import load_market_csv
from verify_lab.measure.constants import COL_EXCLUDED_REASON, REASON_NONE
from verify_lab.report.constants import DATE_FORMAT, PERCENT_DECIMALS
from verify_lab.strategy.constants import (
    DISPLAY_DIRECTION,
    DISPLAY_ENTRY_DATE,
    DISPLAY_ENTRY_PRICE,
    DISPLAY_EXIT_DATE,
    DISPLAY_EXIT_PRICE,
    DISPLAY_EXIT_REASON,
    DISPLAY_EXPIRY_MONTH,
    DISPLAY_HOLD_DAYS,
    DISPLAY_RETURN,
    DISPLAY_STOP_APPLICABLE,
    DISPLAY_STOP_LEVEL,
    DISPLAY_TARGET_DATE,
    DISPLAY_TICKER,
    EXPIRY_CELLS,
    EXPIRY_DIRECTION_DOWN,
    EXPIRY_DIRECTION_UP,
    EXPIRY_STOP_LEVEL,
    STOP_APPLICABLE,
    ExpiryCell,
    stop_level_value,
)
from verify_lab.strategy.periods import period_rows
from verify_lab.strategy.trade_fill import TradeResult, simulate_scheduled_trade
from verify_lab.studies.option_expiry.constants import (
    COL_EXIT_DATE,
    COL_EXPIRY_DATE,
    COL_RULE_DATE,
    COL_TARGET_DATE,
    DATASETS,
    FRIDAY,
    Dataset,
)
from verify_lab.studies.option_expiry.expiry_calendar import monthly_expiry_dates
from verify_lab.studies.option_expiry.weekly_exit import weekly_exit_schedule
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ExpiryOutputs:
    """실행 산출물

    Attributes:
        grid: 칸별 성적표. 칸 × 손절선 × 구간이 한 행이다
        trades: 체결 원자료. 사용자가 차트로 대조하는 자리 (측정의 원칙 8)
    """

    grid: pd.DataFrame
    trades: pd.DataFrame


@dataclass
class Entries:
    """한 칸의 진입 목록

    Attributes:
        frame: 시세
        entry_positions: 진입일의 위치 인덱스
        exit_positions: 청산일의 위치 인덱스
        target_dates: 달력이 지목한 청산 목표일
        excluded_count: 청산일을 확정하지 못해 빠진 진입 수
    """

    frame: pd.DataFrame
    entry_positions: np.ndarray
    exit_positions: np.ndarray
    target_dates: pd.DatetimeIndex
    excluded_count: int = 0


@dataclass
class _Block:
    """한 칸 × 한 손절선의 결과

    Attributes:
        trades: 체결 내역 표
        returns: 신호별 수익률 원값. **표는 반올림된 값이라 그것으로 다시 집계하면 어긋난다**
        hold_days: 신호별 보유 거래일 수
        reasons: 신호별 청산 사유
        entry_dates: 신호별 진입일. **구간 분해가 이것으로 행을 나눈다**
    """

    trades: list[dict[str, Any]] = field(default_factory=list)
    returns: list[float] = field(default_factory=list)
    hold_days: list[int] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    entry_dates: list[pd.Timestamp] = field(default_factory=list)


def run_option_expiry_trading(
    cells: Sequence[ExpiryCell] = EXPIRY_CELLS,
    stop_levels: Sequence[float | None] = (EXPIRY_STOP_LEVEL,),
) -> ExpiryOutputs:
    """대상 칸마다 손절선을 적용해 성적표와 원자료를 낸다.

    **기본은 확정 손절선 하나다.** 그때도 `손절선(%)` 컬럼은 나온다 — 없으면 그 표가
    −5% 성적인지 무손절 성적인지 **산출물만 봐서는 판별되지 않는다.**
    격자를 낼 때는 `[None, *EXPIRY_STOP_LEVELS]` 를 넘긴다(무손절 포함).

    Args:
        cells: 대상 칸 목록
        stop_levels: 적용할 손절선 목록 (비율). **`None` 이 들어 있으면 무손절 행**이다

    Returns:
        성적표와 체결 원자료

    Raises:
        ValueError: 대상 칸이 비었거나, 손절선 목록이 비었거나, 데이터셋 이름을 찾을 수 없는 경우
    """
    if not cells:
        raise ValueError("대상 칸이 비어 있어 매매를 돌릴 수 없습니다")
    if not stop_levels:
        raise ValueError("손절선 목록이 비어 있습니다")

    grid_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []

    for cell in cells:
        dataset = _dataset(cell.dataset_key)
        entries = collect_entries(dataset, cell)

        for stop_level in stop_levels:
            block = _measure(dataset, cell, entries, stop_level)
            last_day = pd.Timestamp(entries.frame[COL_DATE].iloc[-1])
            identity = _identity(dataset, cell, stop_level)
            for row in period_rows(
                pd.DatetimeIndex(block.entry_dates),
                block.returns,
                last_day=last_day,
                hold_days=block.hold_days,
                reasons=block.reasons,
                excluded_count=entries.excluded_count,
            ):
                grid_rows.append({**identity, **row})
            trade_rows.extend(block.trades)

    logger.debug(f"만기 매매 산출: 칸 {len(cells)}개, 손절선 {len(stop_levels)}종, " f"성적 {len(grid_rows)}행, 체결 {len(trade_rows)}건")

    return ExpiryOutputs(grid=pd.DataFrame(grid_rows), trades=pd.DataFrame(trade_rows))


def _dataset(key: str) -> Dataset:
    """데이터셋 목록에서 이름으로 하나를 찾는다.

    Args:
        key: 데이터셋 이름

    Returns:
        해당 데이터셋

    Raises:
        ValueError: 그 이름의 데이터셋이 없는 경우
    """
    for dataset in DATASETS:
        if dataset.key == key:
            return dataset

    raise ValueError(f"알 수 없는 데이터셋입니다: {key}")


def collect_entries(dataset: Dataset, cell: ExpiryCell) -> Entries:
    """한 칸의 진입일과 청산일을 모은다.

    **만기월은 진입일(실제 만기일)의 월로 센다** — `studies.option_expiry` 의 만기월 축과
    같은 정의여야 두 산출물을 나란히 읽을 수 있다.

    **청산일을 확정하지 못한 진입은 빼되 몇 건인지 센다** (표본 보존). 목표일이 데이터 끝을
    넘는 달이 여기 해당하며, 값을 지어내면 보유 기간이 다른 표본이 같은 평균에 섞인다.

    Args:
        dataset: 대상 종목
        cell: 대상 칸

    Returns:
        진입 목록
    """
    df = load_market_csv(MARKET_DIR / dataset.file_name)
    trading_days = pd.DatetimeIndex(df[COL_DATE])
    expiries = monthly_expiry_dates(trading_days, dataset.rule)

    schedule = weekly_exit_schedule(
        trading_days,
        pd.DatetimeIndex(expiries[COL_EXPIRY_DATE]),
        pd.DatetimeIndex(expiries[COL_RULE_DATE]),
        exit_weekday=FRIDAY,
    ).frame

    in_month = pd.DatetimeIndex(schedule[COL_DATE]).month == cell.expiry_month
    month_rows = schedule.loc[in_month]

    usable = month_rows[COL_EXCLUDED_REASON] == REASON_NONE
    kept = month_rows.loc[usable]

    return Entries(
        frame=df,
        entry_positions=np.asarray(trading_days.get_indexer(pd.DatetimeIndex(kept[COL_DATE])), dtype=np.int64),
        exit_positions=np.asarray(trading_days.get_indexer(pd.DatetimeIndex(kept[COL_EXIT_DATE])), dtype=np.int64),
        target_dates=pd.DatetimeIndex(kept[COL_TARGET_DATE]),
        excluded_count=int((~usable).sum()),
    )


def _measure(
    dataset: Dataset,
    cell: ExpiryCell,
    entries: Entries,
    stop_level: float | None,
) -> _Block:
    """한 칸 × 한 손절선의 체결 내역과 집계용 원값을 만든다.

    **표시용 표와 집계용 값을 함께 낸다.** 표는 저장 직전 반올림이 걸린 값이라,
    그것으로 다시 평균을 내면 이중 반올림이 되어 합계가 어긋난다.

    Args:
        dataset: 대상 종목
        cell: 대상 칸
        entries: 진입 목록
        stop_level: 손절선. `None` 이면 무손절

    Returns:
        체결 내역과 신호별 원값
    """
    block = _Block()

    for order in range(len(entries.entry_positions)):
        entry_position = int(entries.entry_positions[order])
        exit_position = int(entries.exit_positions[order])

        result = simulate_scheduled_trade(
            entries.frame,
            entry_position,
            exit_position,
            bet_down=cell.bet_down,
            stop_level=stop_level,
        )

        block.trades.append(_trade_row(dataset, cell, entries, order, entry_position, result, stop_level))
        block.returns.append(result.return_rate)
        block.hold_days.append(result.hold_days)
        block.reasons.append(result.reason)
        block.entry_dates.append(pd.Timestamp(entries.frame.iloc[entry_position][COL_DATE]))

    return block


def _trade_row(
    dataset: Dataset,
    cell: ExpiryCell,
    entries: Entries,
    order: int,
    entry_position: int,
    result: TradeResult,
    stop_level: float | None,
) -> dict[str, Any]:
    """체결 하나를 표 행으로 바꾼다.

    **청산가는 실제 체결가다.** 손절이 걸린 체결은 청산 목표일의 종가가 아니라 손절가(또는
    갭이 열린 시가)에 나가므로, 목표일 종가를 적으면 사용자가 차트와 대조할 때 어긋난다.

    Args:
        dataset: 대상 종목
        cell: 대상 칸
        entries: 진입 목록
        order: 진입 목록 안에서의 순서
        entry_position: 시세에서의 진입 위치
        result: 체결 결과
        stop_level: 손절선. `None` 이면 무손절

    Returns:
        표 한 줄
    """
    frame = entries.frame
    entry_price = float(frame.iloc[entry_position][COL_CLOSE])
    exit_position = entry_position + result.hold_days

    # 수익률은 방향 부호가 적용된 값이므로, 체결가를 되돌리려면 같은 부호를 다시 곱한다
    sign = -1.0 if cell.bet_down else 1.0
    exit_price = entry_price * (1.0 + sign * result.return_rate)

    return {
        **_identity(dataset, cell, stop_level),
        DISPLAY_ENTRY_DATE: pd.Timestamp(frame.iloc[entry_position][COL_DATE]).strftime(DATE_FORMAT),
        DISPLAY_ENTRY_PRICE: round(entry_price, dataset.price_decimals),
        DISPLAY_TARGET_DATE: entries.target_dates[order].strftime(DATE_FORMAT),
        DISPLAY_EXIT_DATE: pd.Timestamp(frame.iloc[exit_position][COL_DATE]).strftime(DATE_FORMAT),
        DISPLAY_HOLD_DAYS: result.hold_days,
        DISPLAY_EXIT_PRICE: round(exit_price, dataset.price_decimals),
        DISPLAY_RETURN: round(result.return_rate * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_EXIT_REASON: result.reason,
    }


def _identity(dataset: Dataset, cell: ExpiryCell, stop_level: float | None) -> dict[str, Any]:
    """행을 식별하는 앞 컬럼들을 만든다.

    **손절선이 하나뿐일 때도 그 컬럼을 낸다.** 전에는 전 행이 같은 값이라 빼고 있었는데,
    그 근거는 **한 파일 안에서만** 성립한다 — 파일을 여는 사람은 그 표가 무손절 성적인지
    −5% 성적인지 알 수 없고, 같은 매매법의 격자표와 나란히 놓으면 컬럼 구성이 달라져
    대조가 끊긴다. 세 매매법이 공유하는 계약이며 `tests/test_strategy_output_contract.py`
    가 고정한다. 확정 규칙의 손절선 값은 `EXPIRY_STOP_LEVEL` 이 SoT다.

    Args:
        dataset: 대상 종목
        cell: 대상 칸
        stop_level: 손절선. `None` 이면 무손절

    Returns:
        식별 컬럼 dict
    """
    return {
        DISPLAY_TICKER: dataset.ticker,
        DISPLAY_EXPIRY_MONTH: cell.expiry_month,
        DISPLAY_DIRECTION: EXPIRY_DIRECTION_DOWN if cell.bet_down else EXPIRY_DIRECTION_UP,
        DISPLAY_STOP_LEVEL: stop_level_value(stop_level),
        # **언제나 「가능」인 것이 로더로 보장된다.** 이 매매법은 `load_market_csv` 만 쓰고
        # 그 로더가 시가·고가·저가를 요구하므로 종가 계열(지수)은 읽는 단계에서 거부된다 —
        # 그래서 값을 시세에서 유도하지 않는다. 지수를 받는 매매법(월말)은 `is_index` 로 가른다
        DISPLAY_STOP_APPLICABLE: STOP_APPLICABLE,
    }


# **`period_rows` 를 재노출하지 않는다.** 이 모듈은 `strategy/periods.py` 에서 가져다 쓰는
# 쪽이며, 여기서 내보내면 공유 로직을 매매법 이름이 붙은 경로로도 가져올 수 있게 되어
# 사슬이 되살아난다 (`tests/test_layer_contracts.py` 가 금지한 그것이다)
__all__ = ["Entries", "ExpiryOutputs", "collect_entries", "run_option_expiry_trading"]
