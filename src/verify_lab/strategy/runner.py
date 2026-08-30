"""역방향 매매 실행 — 대상과 보유 한도를 순회해 산출물을 조립한다

이 모듈은 **매매 규칙을 계산하지 않는다.** 신호 판정은 `studies`, 체결은 `reverse_trading` 이
이미 하므로, 하는 일은 그것을 조합해 돌리고 사람이 읽을 형태로 쌓는 것이다.

**보유 한도는 자금을 나누는 축이 아니라 비교 축이다.** 한 포지션이 두 한도를 동시에 가질 수
없으므로, 한도별 결과는 "어느 쪽을 택할지"의 비교표다. 하나를 고르면 표본에 맞춘 튜닝이 되므로
전부 산출해 나란히 낸다 (`docs/strategy/역방향_매매_규칙.md` 결정 ⑥).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE, RATE_TO_PERCENT
from verify_lab.data.loader import load_market_csv
from verify_lab.report.constants import DATE_FORMAT, DISPLAY_EXCLUDED, PERCENT_DECIMALS
from verify_lab.strategy.constants import (
    DISPLAY_CHANGE_RATE,
    DISPLAY_DATE,
    DISPLAY_DIRECTION,
    DISPLAY_ENTRY_PRICE,
    DISPLAY_EVENT_COUNT,
    DISPLAY_EVENT_ID,
    DISPLAY_EXIT_REASON,
    DISPLAY_HOLD_DAYS,
    DISPLAY_MAX,
    DISPLAY_MEAN,
    DISPLAY_MEAN_HOLD,
    DISPLAY_MIN,
    DISPLAY_PARAMETER,
    DISPLAY_RETURN,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_START_YEAR,
    DISPLAY_TICKER,
    DISPLAY_TOTAL,
    DISPLAY_WIN_RATE,
    HOLD_DAYS_DECIMALS,
    HOLD_LIMIT,
    PARAMETER_PREFIX_RANK_CUT,
    START_YEAR,
    STOP_LOSS_LEVEL,
    TARGETS,
    Target,
)
from verify_lab.strategy.reverse_trading import TradeResult, simulate_signal
from verify_lab.studies.index_extreme.annotations import assign_event_ids
from verify_lab.studies.index_extreme.constants import EVENT_GAP_DAYS, EXTREME_DIRECTION_LABELS, Direction
from verify_lab.studies.index_extreme.daily_change import daily_change_rate
from verify_lab.studies.index_extreme.extreme_move import find_extreme_move_events
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 산출물의 식별 컬럼. 두 표 모두 이 순서로 앞에 붙는다 —
# 조합을 한 파일에 쌓으므로 어느 행이 어떤 설정의 결과인지가 행 자체에 있어야 한다
IDENTITY_COLUMNS = (
    DISPLAY_TICKER,
    DISPLAY_PARAMETER,
    DISPLAY_START_YEAR,
)

# ============================================================
# summary.json 키
# ============================================================

KEY_STRATEGY = "strategy"
KEY_TARGETS = "targets"
KEY_RULE = "rule"
KEY_ROW_COUNTS = "row_counts"
KEY_NOTES = "notes"

KEY_TICKER = "ticker"
KEY_RANK_CUT = "rank_cut"
KEY_START_YEAR = "start_year"
KEY_PATH = "path"
KEY_SIGNAL_COUNT = "signal_count"
KEY_EVENT_COUNT = "event_count"

KEY_STOP_LEVEL = "stop_loss_level"
KEY_HOLD_LIMIT = "hold_limit"
KEY_ENTRY = "entry"
KEY_EXIT = "exit"

KEY_TRADES = "trades"
KEY_SUMMARY = "summary_by_target"

# 산출물만 보고는 알 수 없는 실행 조건
NOTE_ENTRY = "진입은 신호일 종가다. 15:20 판정 후 종가 단일가매매로 체결하는 것을 전제하며, 익일 시가 집행이 아니다"
NOTE_STOP_BASE = "손절선은 전부 진입가 기준이고 보유 기간 내내 갱신하지 않는다. 갭 청산은 손절선보다 더 잃는다"
NOTE_HOLD_LIMIT = "보유 한도는 D+2 로 고정돼 있다. 이익이 나면 그날 즉시 청산하고 손실일 때만 한도까지 끈다"
NOTE_INVERSE = "상승 방향 신호는 원지수 수익률에 -1 을 곱한 값이다. 인버스 상품의 손익이 아니며 일간 복리·보수·롤 비용은 반영되지 않는다"


@dataclass(frozen=True)
class StrategyOutputs:
    """실행 산출물

    Attributes:
        trades: 신호별 체결 내역 (신호 하나가 한 행)
        summary: 대상별 집계
        meta: 실행 파라미터와 핵심 수치
    """

    trades: pd.DataFrame
    summary: pd.DataFrame
    meta: dict[str, Any]


@dataclass(frozen=True)
class _Block:
    """한 대상의 결과

    Attributes:
        trades: 체결 내역 (표시용 — 값이 이미 반올림돼 있다)
        returns: 신호별 수익률 (비율 원값). **집계는 이 값으로 한다** —
            반올림된 표에서 다시 평균을 내면 이중 반올림으로 합계가 어긋난다
        hold_days: 신호별 보유일 (진입일로부터의 거래일 수)
        excluded_count: 보유 한도가 데이터 끝을 넘어가 체결을 만들지 못한 신호 수.
            **버린 건수를 세어 보고한다** — 조용히 사라진 표본은 생존편향을 만든다
    """

    trades: pd.DataFrame
    returns: list[float]
    hold_days: list[int]
    excluded_count: int


@dataclass(frozen=True)
class _Signals:
    """한 대상의 신호 목록

    Attributes:
        frame: 시세
        positions: 신호일의 위치 인덱스
        upward: 위치별 상승 방향 여부
        change_rates: 위치별 등락률 (비율)
        event_ids: 위치별 사건 번호
    """

    frame: pd.DataFrame
    positions: np.ndarray
    upward: np.ndarray
    change_rates: np.ndarray
    event_ids: np.ndarray


def run_strategy(
    targets: Sequence[Target] = TARGETS,
    *,
    hold_limit: int = HOLD_LIMIT,
    stop_level: float = STOP_LOSS_LEVEL,
) -> StrategyOutputs:
    """대상을 전부 돌고 체결 내역과 집계를 만든다.

    Args:
        targets: 매매 대상 목록
        hold_limit: 보유 한도 (거래일)
        stop_level: 손절선 (비율)

    Returns:
        체결 내역·집계·실행 정보

    Raises:
        ValueError: 대상이 비어 있거나 시세를 읽을 수 없는 경우
    """
    if not targets:
        raise ValueError("매매 대상이 비어 있습니다")

    trade_blocks: list[pd.DataFrame] = []
    summary_rows: list[dict[str, Any]] = []
    target_records: list[dict[str, Any]] = []

    for target in targets:
        signals = _find_signals(target)
        target_records.append(_target_record(target, signals))

        block = _measure(target, signals, hold_limit=hold_limit, stop_level=stop_level)
        if block.trades.empty:
            continue

        trade_blocks.append(block.trades)
        summary_rows.append(_summarize(target, block))

    trades = pd.concat(trade_blocks, ignore_index=True) if trade_blocks else pd.DataFrame()
    summary = pd.DataFrame(summary_rows)

    meta = {
        KEY_STRATEGY: "reverse_trading",
        KEY_TARGETS: target_records,
        KEY_RULE: {
            KEY_STOP_LEVEL: round(stop_level * RATE_TO_PERCENT, PERCENT_DECIMALS),
            KEY_HOLD_LIMIT: hold_limit,
            KEY_ENTRY: NOTE_ENTRY,
            KEY_EXIT: NOTE_STOP_BASE,
        },
        KEY_ROW_COUNTS: {KEY_TRADES: len(trades), KEY_SUMMARY: len(summary)},
        KEY_NOTES: [NOTE_ENTRY, NOTE_STOP_BASE, NOTE_HOLD_LIMIT, NOTE_INVERSE],
    }

    logger.debug(
        f"매매 실행 완료: 대상 {len(targets)}종, 손절 -{stop_level * RATE_TO_PERCENT:.0f}%, "
        f"한도 D+{hold_limit}, 체결 {len(trades):,}건"
    )

    return StrategyOutputs(trades=trades, summary=summary, meta=meta)


def _find_signals(target: Target) -> _Signals:
    """대상의 신호일과 부가 정보를 찾는다.

    신호 판정은 `studies` 가 소유한다. 이 계층은 **어느 날이 신호인가**를 다시 정하지 않는다.
    두 방향을 합친 목록에 사건 번호를 매기는 것도 그쪽 결정을 그대로 따른다.

    Args:
        target: 매매 대상

    Returns:
        신호일 위치와 방향·등락률·사건 번호

    Raises:
        FileNotFoundError: 시세 파일이 없는 경우
        ValueError: 시세가 검증을 통과하지 못한 경우
    """
    frame = load_market_csv(target.dataset.path)
    start = pd.Timestamp(year=START_YEAR, month=1, day=1)
    selected = {
        direction: find_extreme_move_events(frame, direction=direction, rank_cut=target.rank_cut, start_date=start)
        for direction in Direction
    }
    union = selected[Direction.UP] | selected[Direction.DOWN]
    numbered = assign_event_ids(frame.loc[union, COL_DATE], EVENT_GAP_DAYS)

    positions = np.flatnonzero(union.to_numpy())

    return _Signals(
        frame=frame,
        positions=positions,
        upward=selected[Direction.UP].to_numpy()[positions],
        change_rates=daily_change_rate(frame).to_numpy()[positions],
        event_ids=numbered.to_numpy(),
    )


def _measure(
    target: Target,
    signals: _Signals,
    *,
    hold_limit: int,
    stop_level: float,
) -> _Block:
    """한 대상의 체결 내역과 집계용 원값을 만든다.

    **표시용 표와 집계용 값을 함께 낸다.** 표는 저장 직전 반올림이 걸린 값이라,
    그것으로 다시 평균을 내면 이중 반올림이 되어 합계가 어긋난다.

    Args:
        target: 매매 대상
        signals: 신호 목록
        hold_limit: 보유 한도
        stop_level: 손절선

    Returns:
        체결 내역과 신호별 원값. **신호 하나가 한 행**이다
    """
    frame = signals.frame
    rows: list[dict[str, Any]] = []
    returns: list[float] = []
    hold_days: list[int] = []
    excluded_count = 0

    for order, position in enumerate(signals.positions):
        result = simulate_signal(
            frame,
            int(position),
            upward=bool(signals.upward[order]),
            hold_limit=hold_limit,
            stop_level=stop_level,
        )
        if result is None:
            # 보유 한도가 데이터 끝을 넘어간 신호다. 조용히 넘기면 표본이 달라지므로
            # 빼되 **몇 건이 왜 빠졌는지 세어 돌려준다** (표본 보존)
            excluded_count += 1
            continue

        rows.append(_trade_row(target, signals, order, position, result))
        returns.append(result.return_rate)
        hold_days.append(result.hold_days)

    return _Block(
        trades=pd.DataFrame(rows),
        returns=returns,
        hold_days=hold_days,
        excluded_count=excluded_count,
    )


def _trade_row(
    target: Target,
    signals: _Signals,
    order: int,
    position: int,
    result: TradeResult,
) -> dict[str, Any]:
    """신호 하나의 체결 결과를 표 행으로 바꾼다.

    Args:
        target: 매매 대상
        signals: 신호 목록
        order: 신호 목록 안에서의 순서
        position: 시세에서의 위치 인덱스
        result: 체결 결과

    Returns:
        표 한 줄
    """
    row = signals.frame.iloc[position]
    upward = bool(signals.upward[order])
    direction = Direction.UP if upward else Direction.DOWN

    return {
        DISPLAY_TICKER: target.dataset.ticker,
        DISPLAY_PARAMETER: f"{PARAMETER_PREFIX_RANK_CUT}={target.rank_cut}",
        DISPLAY_START_YEAR: START_YEAR,
        DISPLAY_DATE: pd.Timestamp(row[COL_DATE]).strftime(DATE_FORMAT),
        DISPLAY_DIRECTION: EXTREME_DIRECTION_LABELS[direction],
        DISPLAY_ENTRY_PRICE: round(float(row[COL_CLOSE]), target.dataset.price_decimals),
        DISPLAY_CHANGE_RATE: round(float(signals.change_rates[order]) * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_EVENT_ID: int(signals.event_ids[order]),
        DISPLAY_EXIT_REASON: result.reason,
        DISPLAY_HOLD_DAYS: result.hold_days,
        DISPLAY_RETURN: round(result.return_rate * RATE_TO_PERCENT, PERCENT_DECIMALS),
    }


def _summarize(target: Target, block: _Block) -> dict[str, Any]:
    """한 대상의 집계를 만든다.

    **`신호 + 제외 = 그 대상의 전체 신호 수`** 가 성립한다. 「신호」는 체결을 만든 수이고
    「제외」는 보유 한도가 데이터 끝을 넘어가 버린 수다. 전체 신호 수는 실행 요약에 있다.

    Args:
        target: 매매 대상
        block: 그 대상의 체결 내역과 원값

    Returns:
        집계 한 줄
    """
    returns = pd.Series(block.returns)
    percent = returns * RATE_TO_PERCENT

    return {
        DISPLAY_TICKER: target.dataset.ticker,
        DISPLAY_PARAMETER: f"{PARAMETER_PREFIX_RANK_CUT}={target.rank_cut}",
        DISPLAY_START_YEAR: START_YEAR,
        DISPLAY_SIGNAL_COUNT: len(returns),
        DISPLAY_EXCLUDED: block.excluded_count,
        DISPLAY_EVENT_COUNT: int(block.trades[DISPLAY_EVENT_ID].nunique()),
        DISPLAY_TOTAL: round(float(percent.sum()), PERCENT_DECIMALS),
        DISPLAY_MEAN: round(float(percent.mean()), PERCENT_DECIMALS),
        DISPLAY_WIN_RATE: round(float((returns > 0).mean()) * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_MAX: round(float(percent.max()), PERCENT_DECIMALS),
        DISPLAY_MIN: round(float(percent.min()), PERCENT_DECIMALS),
        DISPLAY_MEAN_HOLD: round(float(pd.Series(block.hold_days).mean()), HOLD_DAYS_DECIMALS),
    }


def _target_record(target: Target, signals: _Signals) -> dict[str, Any]:
    """대상 정보를 요약용 dict 로 만든다.

    Args:
        target: 매매 대상
        signals: 신호 목록

    Returns:
        요약 dict
    """
    return {
        KEY_TICKER: target.dataset.ticker,
        KEY_RANK_CUT: target.rank_cut,
        KEY_START_YEAR: START_YEAR,
        KEY_PATH: str(target.dataset.path),
        KEY_SIGNAL_COUNT: len(signals.positions),
        KEY_EVENT_COUNT: int(pd.Series(signals.event_ids).nunique()),
    }
