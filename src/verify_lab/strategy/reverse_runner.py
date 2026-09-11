"""역방향 매매 실행 — 대상과 보유 한도를 순회해 산출물을 조립한다

이 모듈은 **매매 규칙을 계산하지 않는다.** 신호 판정은 `studies`, 체결은 `strategy/trade_fill.py`,
구간별 성적은 `strategy/periods.py` 가 이미 하므로, 하는 일은 그것을 조합해 돌리고
사람이 읽을 형태로 쌓는 것이다.

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
from verify_lab.report.constants import DATE_FORMAT, PERCENT_DECIMALS
from verify_lab.strategy.constants import (
    DISPLAY_CHANGE_RATE,
    DISPLAY_DIRECTION,
    DISPLAY_ENTRY_DATE,
    DISPLAY_ENTRY_PRICE,
    DISPLAY_EVENT_ID,
    DISPLAY_EXIT_DATE,
    DISPLAY_EXIT_PRICE,
    DISPLAY_EXIT_REASON,
    DISPLAY_HOLD_DAYS,
    DISPLAY_PARAMETER,
    DISPLAY_RETURN,
    DISPLAY_START_YEAR,
    DISPLAY_STOP_APPLICABLE,
    DISPLAY_STOP_LEVEL,
    DISPLAY_TICKER,
    HOLD_LIMIT,
    PARAMETER_PREFIX_RANK_CUT,
    STOP_APPLICABLE,
    STOP_LOSS_LEVEL,
    SUMMARY_FILENAME,
    TARGETS,
    TRADES_FILENAME,
    Target,
    stop_level_value,
)
from verify_lab.strategy.periods import period_rows, to_summary_frame
from verify_lab.strategy.run_summary import build_run_summary, dataset_record
from verify_lab.strategy.trade_fill import TradeResult, simulate_signal
from verify_lab.studies.reverse.annotations import assign_event_ids
from verify_lab.studies.reverse.constants import (
    DISPLAY_DIRECTION_REVERSE_ALL,
    EVENT_GAP_DAYS,
    EXTREME_DIRECTION_LABELS,
    TRACK_NAME,
    Direction,
)
from verify_lab.studies.reverse.daily_change import daily_change_rate
from verify_lab.studies.reverse.extreme_move import expanding_rank, find_extreme_move_events
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 산출물의 식별 컬럼. 두 표 모두 이 순서로 앞에 붙는다 —
# 조합을 한 파일에 쌓으므로 어느 행이 어떤 설정의 결과인지가 행 자체에 있어야 한다.
#
# **순서는 세 매매법이 공유하는 계약이다** (`tests/test_strategy_output_contract.py`).
# `방향` 은 두 표에서 «다른 것»을 가리킨다 — 성적표는 두 방향을 합친 표본이라 `역방향 전체`,
# 거래내역은 그 신호가 폭등이었나 폭락이었나다. 거는 쪽은 언제나 그 반대다
IDENTITY_COLUMNS = (
    DISPLAY_TICKER,
    DISPLAY_PARAMETER,
    DISPLAY_START_YEAR,
    DISPLAY_DIRECTION,
    DISPLAY_STOP_LEVEL,
    DISPLAY_STOP_APPLICABLE,
)

# ============================================================
# `summary.json` 의 `rule` 안 — 무엇을 어떤 규칙으로 돌렸나
# ============================================================

# **최상위 키는 이 모듈이 갖지 않는다** (`strategy/run_summary.py`). 전에는 여기에
# `KEY_STRATEGY = "strategy"` 가 있었고 그 값이 `"reverse_trading"` 이라 **작업 B 가
# 없애려던 옛 이름이 데이터 값으로 남아** 있었다 — 폴더는 `reverse` 인데 요약만 달랐다
KEY_TARGETS = "targets"
KEY_LABEL = "label"
KEY_RANK_CUT = "rank_cut"
KEY_START_YEAR = "start_year"
KEY_SIGNAL_COUNT = "signal_count"
KEY_EVENT_COUNT = "event_count"
KEY_EXCLUDED_COUNT = "excluded_count"

KEY_STOP_LEVEL = "stop_loss_level"
KEY_HOLD_LIMIT = "hold_limit"
KEY_ENTRY = "entry"
KEY_EXIT = "exit"

# 산출물만 보고는 알 수 없는 실행 조건
NOTE_ENTRY = "진입은 신호일 종가다. 15:20 판정 후 종가 단일가매매로 체결하는 것을 전제하며, 익일 시가 집행이 아니다"
NOTE_STOP_BASE = "손절선은 전부 진입가 기준이고 보유 기간 내내 갱신하지 않는다. 갭 청산은 손절선보다 더 잃는다"
NOTE_HOLD_LIMIT = "보유 한도는 D+2 로 고정돼 있다. 이익이 나면 그날 즉시 청산하고 손실일 때만 한도까지 끈다"
NOTE_INVERSE = "상승 방향 신호는 원지수 수익률에 -1 을 곱한 값이다. 인버스 상품의 손익이 아니며 일간 복리·보수·롤 비용은 반영되지 않는다"


@dataclass(frozen=True)
class StrategyOutputs:
    """실행 산출물

    **세 매매법이 같은 이름을 쓴다** — 성적표는 `performance`, 실행 요약은 `meta` 처럼
    매매법마다 다른 이름을 쓰면 스크립트가 매번 다른 속성을 찾아야 한다.

    Attributes:
        trades: 신호별 체결 내역 (신호 하나가 한 행)
        performance: 대상 × 구간 성적표
        summary: 실행 요약 (`strategy/run_summary.py` 의 틀)
    """

    trades: pd.DataFrame
    performance: pd.DataFrame
    summary: dict[str, Any]


@dataclass(frozen=True)
class _Block:
    """한 대상의 결과

    Attributes:
        trades: 체결 내역 (표시용 — 값이 이미 반올림돼 있다)
        returns: 신호별 수익률 (비율 원값). **집계는 이 값으로 한다** —
            반올림된 표에서 다시 평균을 내면 이중 반올림으로 합계가 어긋난다
        hold_days: 신호별 보유일 (진입일로부터의 거래일 수)
        reasons: 신호별 청산 사유. 구간별 손절 건수를 이것으로 센다
        entry_dates: 신호별 진입일. **구간 분해가 이것으로 행을 나눈다**
        event_ids: 신호별 사건 번호. 구간마다 사건 수를 따로 센다 (측정의 원칙 5)
        excluded_count: 보유 한도가 데이터 끝을 넘어가 체결을 만들지 못한 신호 수.
            **버린 건수를 세어 보고한다** — 조용히 사라진 표본은 생존편향을 만든다
        last_day: 시세의 마지막 거래일. 「최근 N년」의 기준점이다 —
            실행 시각을 쓰면 코드를 안 고쳐도 날짜가 지나면 결과가 바뀌어 재현되지 않는다
    """

    trades: pd.DataFrame
    returns: list[float]
    hold_days: list[int]
    reasons: list[str]
    entry_dates: list[pd.Timestamp]
    event_ids: list[int]
    excluded_count: int
    last_day: pd.Timestamp


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


def run_reverse_trading(
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

    # **데이터셋 단위로 모은다.** 대상은 종목 × 순위 컷이라 같은 시세를 여러 대상이 쓴다 —
    # 대상마다 한 줄씩 내면 같은 파일의 기간이 네 번 반복된다
    dataset_records: dict[str, dict[str, Any]] = {}

    for target in targets:
        signals = _find_signals(target)
        block = _measure(target, signals, hold_limit=hold_limit, stop_level=stop_level)

        # **`setdefault` 를 쓰지 않는다.** 기본값을 «먼저» 계산하므로 이미 있는 키에도
        # `dataset_record` 가 돈다 — 건너뛰려던 일을 그대로 한다
        if target.dataset.key not in dataset_records:
            dataset_records[target.dataset.key] = dataset_record(
                ticker=target.dataset.ticker,
                label=target.dataset.label,
                file=target.dataset.path.name,
                frame=signals.frame,
            )

        # **요약을 먼저 쌓는다.** 아래에서 체결이 없는 대상을 건너뛰므로, 그 뒤에 쌓으면
        # 전부 제외된 대상의 제외 건수가 어디에도 남지 않는다 (표본 보존)
        target_records.append(_target_record(target, signals, block.excluded_count))

        if block.trades.empty:
            logger.warning(f"체결이 하나도 없어 집계에서 뺐습니다 - {target.dataset.label} (제외 {block.excluded_count}건)")
            continue

        trade_blocks.append(block.trades)
        summary_rows.extend(_summary_rows(target, block, stop_level=stop_level))

    trades = pd.concat(trade_blocks, ignore_index=True) if trade_blocks else pd.DataFrame()
    performance = to_summary_frame(summary_rows)

    summary = build_run_summary(
        track=TRACK_NAME,
        datasets=list(dataset_records.values()),
        rule={
            KEY_STOP_LEVEL: stop_level_value(stop_level),
            KEY_HOLD_LIMIT: hold_limit,
            KEY_ENTRY: NOTE_ENTRY,
            KEY_EXIT: NOTE_STOP_BASE,
            KEY_TARGETS: target_records,
        },
        row_counts={TRADES_FILENAME: len(trades), SUMMARY_FILENAME: len(performance)},
        notes=[NOTE_ENTRY, NOTE_STOP_BASE, NOTE_HOLD_LIMIT, NOTE_INVERSE],
    )

    logger.debug(
        f"매매 실행 완료: 대상 {len(targets)}종, 손절 -{stop_level * RATE_TO_PERCENT:.0f}%, "
        f"한도 D+{hold_limit}, 체결 {len(trades):,}건"
    )

    return StrategyOutputs(trades=trades, performance=performance, summary=summary)


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
    start = pd.Timestamp(year=target.start_year, month=1, day=1)

    # 확장창 순위는 **방향과 무관하게 같은 값**이므로 한 번만 만들어 두 방향에 넘긴다.
    # 넘기지 않으면 이벤트 정의가 방향마다 다시 만든다 — 같은 값을 두 경로로 내면 갈라질 여지가 생긴다
    ranks = expanding_rank(frame)
    selected = {
        direction: find_extreme_move_events(
            frame, direction=direction, rank_cut=target.rank_cut, start_date=start, ranks=ranks
        )
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
    reasons: list[str] = []
    entry_dates: list[pd.Timestamp] = []
    event_ids: list[int] = []
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

        rows.append(_trade_row(target, signals, order, position, result, stop_level))
        returns.append(result.return_rate)
        hold_days.append(result.hold_days)
        reasons.append(result.reason)
        entry_dates.append(pd.Timestamp(frame.iloc[int(position)][COL_DATE]))
        event_ids.append(int(signals.event_ids[order]))

    return _Block(
        trades=pd.DataFrame(rows),
        returns=returns,
        hold_days=hold_days,
        reasons=reasons,
        entry_dates=entry_dates,
        event_ids=event_ids,
        excluded_count=excluded_count,
        last_day=pd.Timestamp(frame[COL_DATE].iloc[-1]),
    )


def _identity(target: Target, *, direction: str, stop_level: float) -> dict[str, Any]:
    """행을 식별하는 앞 컬럼들을 만든다.

    **손절선을 행 안에 둔다.** 전 행이 같은 값이지만, 없으면 그 표가 −5% 적용 성적인지
    무손절인지 **산출물만 봐서는 판별되지 않는다** — 실제로 역방향 체결 160건 중 19건이
    손절로 나갔는데 성적표에 그 사실이 남지 않았다.

    Args:
        target: 매매 대상
        direction: 방향 표기. 성적표는 두 방향을 합친 표본이라 `역방향 전체` 이고,
            거래내역은 그 신호가 폭등이었나 폭락이었나다
        stop_level: 손절선 (비율)

    Returns:
        식별 컬럼 dict
    """
    return {
        DISPLAY_TICKER: target.dataset.label,
        DISPLAY_PARAMETER: f"{PARAMETER_PREFIX_RANK_CUT}={target.rank_cut}",
        DISPLAY_START_YEAR: target.start_year,
        DISPLAY_DIRECTION: direction,
        DISPLAY_STOP_LEVEL: stop_level_value(stop_level),
        # **언제나 「가능」인 것이 로더로 보장된다.** 이 매매법은 `load_market_csv` 만 쓰고
        # 그 로더가 시가·고가·저가를 요구하므로 종가 계열(지수)은 읽는 단계에서 거부된다 —
        # 그래서 값을 시세에서 유도하지 않는다. 지수를 받는 매매법(월말)은 `is_index` 로 가른다
        DISPLAY_STOP_APPLICABLE: STOP_APPLICABLE,
    }


def _trade_row(
    target: Target,
    signals: _Signals,
    order: int,
    position: int,
    result: TradeResult,
    stop_level: float,
) -> dict[str, Any]:
    """신호 하나의 체결 결과를 표 행으로 바꾼다.

    **청산가는 실제 체결가다.** 손절이 걸린 체결은 한도일 종가가 아니라 손절가(또는 갭이
    열린 시가)에 나가므로, 한도일 종가를 적으면 사용자가 차트와 대조할 때 어긋난다.

    Args:
        target: 매매 대상
        signals: 신호 목록
        order: 신호 목록 안에서의 순서
        position: 시세에서의 위치 인덱스
        result: 체결 결과
        stop_level: 손절선 (비율)

    Returns:
        표 한 줄
    """
    frame = signals.frame
    row = frame.iloc[position]
    upward = bool(signals.upward[order])
    direction = Direction.UP if upward else Direction.DOWN
    entry_price = float(row[COL_CLOSE])

    # 수익률은 방향 부호가 적용된 값이므로, 체결가를 되돌리려면 같은 부호를 다시 곱한다
    sign = -1.0 if upward else 1.0
    exit_price = entry_price * (1.0 + sign * result.return_rate)

    return {
        **_identity(target, direction=EXTREME_DIRECTION_LABELS[direction], stop_level=stop_level),
        DISPLAY_ENTRY_DATE: pd.Timestamp(row[COL_DATE]).strftime(DATE_FORMAT),
        DISPLAY_ENTRY_PRICE: round(entry_price, target.dataset.price_decimals),
        DISPLAY_EXIT_DATE: pd.Timestamp(frame.iloc[position + result.hold_days][COL_DATE]).strftime(DATE_FORMAT),
        DISPLAY_HOLD_DAYS: result.hold_days,
        DISPLAY_EXIT_PRICE: round(exit_price, target.dataset.price_decimals),
        DISPLAY_RETURN: round(result.return_rate * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_EXIT_REASON: result.reason,
        DISPLAY_CHANGE_RATE: round(float(signals.change_rates[order]) * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_EVENT_ID: int(signals.event_ids[order]),
    }


def _summary_rows(target: Target, block: _Block, *, stop_level: float) -> list[dict[str, Any]]:
    """한 대상의 성적을 구간마다 한 줄씩 만든다.

    **산식은 `strategy/periods.py` 가 소유한다.** 구간 5행은 측정의 원칙 17 이 **모든**
    매매법에 요구하는 축이므로, 여기서 다시 구현하면 같은 원칙이 매매법마다 다른 답을 낸다.

    **`신호 + 제외 = 그 대상의 전체 신호 수`** 가 성립한다. 「신호」는 체결을 만든 수이고
    「제외」는 보유 한도가 데이터 끝을 넘어가 버린 수다. 전체 신호 수는 실행 요약에 있다.

    **방향은 `역방향 전체` 하나다.** 이 표본은 폭등 신호와 폭락 신호를 합친 것이라 「위」도
    「아래」도 아니며, 확정 규칙이 그 합친 것을 쓴다.

    Args:
        target: 매매 대상
        block: 그 대상의 체결 내역과 원값
        stop_level: 손절선 (비율)

    Returns:
        구간마다 한 줄씩
    """
    identity = _identity(target, direction=DISPLAY_DIRECTION_REVERSE_ALL, stop_level=stop_level)

    return [
        {**identity, **row}
        for row in period_rows(
            pd.DatetimeIndex(block.entry_dates),
            block.returns,
            last_day=block.last_day,
            hold_days=block.hold_days,
            reasons=block.reasons,
            event_ids=block.event_ids,
            excluded_count=block.excluded_count,
        )
    ]


def _target_record(target: Target, signals: _Signals, excluded_count: int) -> dict[str, Any]:
    """대상 정보를 요약용 dict 로 만든다.

    **제외 건수를 여기 담는다.** 집계표는 체결이 하나라도 있는 대상만 행을 갖는데,
    보유 한도가 데이터 끝을 넘어가 **전부 제외되면 그 대상의 행 자체가 없어** 몇 건이 왜
    빠졌는지가 어디에도 남지 않는다. 요약은 대상마다 항상 한 줄이라 그 구멍이 없다.

    Args:
        target: 매매 대상
        signals: 신호 목록
        excluded_count: 보유 한도가 데이터 끝을 넘어가 체결을 만들지 못한 신호 수

    Returns:
        요약 dict
    """
    return {
        KEY_LABEL: target.dataset.label,
        KEY_RANK_CUT: target.rank_cut,
        KEY_START_YEAR: target.start_year,
        KEY_SIGNAL_COUNT: len(signals.positions),
        KEY_EVENT_COUNT: int(pd.Series(signals.event_ids).nunique()),
        KEY_EXCLUDED_COUNT: excluded_count,
    }
