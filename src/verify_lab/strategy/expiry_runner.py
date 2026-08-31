"""옵션 만기일 매매 실행 — 대상 칸과 손절선을 순회해 격자를 조립한다

이 모듈은 **매매 규칙을 계산하지 않는다.** 만기일과 청산일은 `studies.option_expiry` 가,
체결은 `expiry_trading` 이 이미 하므로, 하는 일은 그것을 조합해 돌리고 사람이 읽을 형태로
쌓는 것이다.

**손절선은 자금을 나누는 축이 아니라 비교 축이다.** 한 포지션이 두 손절선을 동시에 가질 수
없으므로, 손절선별 결과는 "어느 값을 택할지"의 비교표다. 하나를 골라 내면 표본에 맞춘
튜닝이 되므로 전부 산출해 나란히 낸다 (루트 `CLAUDE.md` 측정의 원칙 1).

**무손절 행을 반드시 함께 낸다.** 손절의 실질 효용은 수익이 아니라 최악 통제이므로,
대조가 없으면 손절이 무엇을 막았는지 보이지 않는다 (`.claude/rules/strategy.md`).
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
    DISPLAY_EXCLUDED_COUNT,
    DISPLAY_EXIT_DATE,
    DISPLAY_EXIT_PRICE,
    DISPLAY_EXIT_REASON,
    DISPLAY_EXPIRY_MONTH,
    DISPLAY_GAP_STOP_COUNT,
    DISPLAY_HOLD_DAYS,
    DISPLAY_INTRADAY_STOP_COUNT,
    DISPLAY_MAX,
    DISPLAY_MEAN,
    DISPLAY_MEAN_HOLD,
    DISPLAY_MIN,
    DISPLAY_RETURN,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_STDEV,
    DISPLAY_STOP_LEVEL,
    DISPLAY_TARGET_DATE,
    DISPLAY_TICKER,
    DISPLAY_TOTAL,
    DISPLAY_WIN_RATE,
    EXIT_GAP_STOP,
    EXIT_INTRADAY_STOP,
    EXPIRY_CELLS,
    EXPIRY_DIRECTION_DOWN,
    EXPIRY_DIRECTION_UP,
    EXPIRY_STOP_LEVELS,
    HOLD_DAYS_DECIMALS,
    NO_STOP_LABEL,
    ExpiryCell,
)
from verify_lab.strategy.expiry_trading import simulate_expiry_trade
from verify_lab.strategy.reverse_trading import TradeResult
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

# 격자표와 원자료 모두 앞에 붙는 식별 컬럼. 한 파일에 여러 칸을 쌓으므로 어느 행이 어떤
# 설정의 결과인지가 행 자체에 있어야 한다
IDENTITY_COLUMNS = (DISPLAY_TICKER, DISPLAY_EXPIRY_MONTH, DISPLAY_DIRECTION, DISPLAY_STOP_LEVEL)


@dataclass(frozen=True)
class ExpiryOutputs:
    """실행 산출물

    Attributes:
        grid: 칸 × 손절선 격자표. **무손절 행이 칸마다 하나씩 들어 있다**
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
    """

    trades: list[dict[str, Any]] = field(default_factory=list)
    returns: list[float] = field(default_factory=list)
    hold_days: list[int] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def run_expiry_trading(
    cells: Sequence[ExpiryCell] = EXPIRY_CELLS,
    stop_levels: Sequence[float] = EXPIRY_STOP_LEVELS,
) -> ExpiryOutputs:
    """대상 칸마다 손절선 격자를 돌려 성적표와 원자료를 낸다.

    Args:
        cells: 대상 칸 목록
        stop_levels: 손절선 목록 (비율). **무손절은 여기 넣지 않는다** — 칸마다 자동으로 붙는다

    Returns:
        격자표와 체결 원자료

    Raises:
        ValueError: 대상 칸이 비었거나, 데이터셋 이름을 찾을 수 없는 경우
    """
    if not cells:
        raise ValueError("대상 칸이 비어 있어 격자를 돌릴 수 없습니다")

    grid_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []

    for cell in cells:
        dataset = _dataset(cell.dataset_key)
        entries = collect_entries(dataset, cell)

        # 무손절을 맨 앞에 둔다. 손절이 무엇을 막았는지는 이 행과 견줘야 보인다
        for stop_level in [None, *stop_levels]:
            block = _measure(dataset, cell, entries, stop_level)
            grid_rows.append(_summarize(dataset, cell, entries, block, stop_level))
            trade_rows.extend(block.trades)

    logger.debug(f"만기 매매 격자 산출: 칸 {len(cells)}개, 격자 {len(grid_rows)}행, 체결 {len(trade_rows)}건")

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


def _measure(dataset: Dataset, cell: ExpiryCell, entries: Entries, stop_level: float | None) -> _Block:
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

        result = simulate_expiry_trade(
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


def _summarize(
    dataset: Dataset,
    cell: ExpiryCell,
    entries: Entries,
    block: _Block,
    stop_level: float | None,
) -> dict[str, Any]:
    """한 칸 × 한 손절선의 집계를 만든다.

    **합계는 「매 신호 같은 금액을 투입」한 수익률의 단순 합이다** (루트 `CLAUDE.md`
    측정의 원칙 16). 회당 평균만 적으면 크기 감각이 없고 왕복 수수료와 견줄 값인지도 보이지
    않으므로 둘을 나란히 둔다. **표본 수를 반드시 함께 적는다** — 합계는 표본이 많을수록
    커지므로 표본 없이 칸끼리 비교하면 기간이 긴 칸이 자동으로 이긴다.

    **갭손절을 따로 센다.** 시가가 이미 손절선을 넘어 **더 잃고** 나간 체결 수이며,
    그 손절선이 실제로 지켜지는지를 말해 준다.

    Args:
        dataset: 대상 종목
        cell: 대상 칸
        entries: 진입 목록
        block: 체결 결과
        stop_level: 손절선. `None` 이면 무손절

    Returns:
        격자표 한 줄
    """
    returns = np.asarray(block.returns, dtype=float)
    reasons = np.asarray(block.reasons, dtype=object)
    percent = returns * RATE_TO_PERCENT

    return {
        **_identity(dataset, cell, stop_level),
        DISPLAY_SIGNAL_COUNT: len(returns),
        DISPLAY_EXCLUDED_COUNT: entries.excluded_count,
        DISPLAY_TOTAL: round(float(percent.sum()), PERCENT_DECIMALS),
        DISPLAY_MEAN: round(float(percent.mean()), PERCENT_DECIMALS),
        DISPLAY_WIN_RATE: round(float((returns > 0).mean()) * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_MAX: round(float(percent.max()), PERCENT_DECIMALS),
        DISPLAY_MIN: round(float(percent.min()), PERCENT_DECIMALS),
        # 표본이 하나뿐인 칸에서 표본표준편차는 정의되지 않는다. 0 으로 채우면 "흔들림이 없다"로
        # 읽히므로 비워 둔다
        DISPLAY_STDEV: round(float(percent.std(ddof=1)), PERCENT_DECIMALS) if len(returns) > 1 else np.nan,
        DISPLAY_GAP_STOP_COUNT: int((reasons == EXIT_GAP_STOP).sum()),
        DISPLAY_INTRADAY_STOP_COUNT: int((reasons == EXIT_INTRADAY_STOP).sum()),
        DISPLAY_MEAN_HOLD: round(float(np.mean(block.hold_days)), HOLD_DAYS_DECIMALS),
    }


def _identity(dataset: Dataset, cell: ExpiryCell, stop_level: float | None) -> dict[str, Any]:
    """행을 식별하는 앞 컬럼들을 만든다.

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
        DISPLAY_STOP_LEVEL: (
            NO_STOP_LABEL if stop_level is None else round(-stop_level * RATE_TO_PERCENT, PERCENT_DECIMALS)
        ),
    }


__all__ = ["Entries", "ExpiryOutputs", "collect_entries", "run_expiry_trading"]
