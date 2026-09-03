"""옵션 만기일 매매 실행 — 대상 칸을 순회해 성적표와 원자료를 조립한다

이 모듈은 **매매 규칙을 계산하지 않는다.** 만기일과 청산일은 `studies.option_expiry` 가,
체결은 `expiry_trading` 이 이미 하므로, 하는 일은 그것을 조합해 돌리고 사람이 읽을 형태로
쌓는 것이다.

**손절선은 확정값 하나다** (`EXPIRY_STOP_LEVEL`). `.claude/rules/strategy.md` 가
`strategy/` 계층에 한해 파라미터 확정을 허용하며, 값을 고른 근거와 탈락안은
`docs/research/옵션_만기일.md` 12B 와 `docs/spec/option_expiry.md` 결정 ㊴ 에 있다.
**값을 옮겨 가며 성적을 보는 노브를 만들지 않는다** — 그것이 과최적화다.

**격자는 지우지 않고 옵션으로 남긴다.** `stop_levels` 에 여러 값을 넘기면 손절선 컬럼이
붙은 비교표가 나온다. **시세를 재수집하면 「평평한 구간」을 다시 찾아야 하기 때문**이며,
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
    DISPLAY_EXCLUDED_COUNT,
    DISPLAY_EXIT_DATE,
    DISPLAY_EXIT_PRICE,
    DISPLAY_EXIT_REASON,
    DISPLAY_EXPIRY_MONTH,
    DISPLAY_GAP_STOP_COUNT,
    DISPLAY_HOLD_DAYS,
    DISPLAY_INTRADAY_STOP_COUNT,
    DISPLAY_JUDGEABLE,
    DISPLAY_MAX,
    DISPLAY_MEAN,
    DISPLAY_MEAN_HOLD,
    DISPLAY_MIN,
    DISPLAY_PERIOD,
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
    EXPIRY_PERIODS,
    EXPIRY_STOP_LEVEL,
    HOLD_DAYS_DECIMALS,
    JUDGEABLE_NO,
    JUDGEABLE_YES,
    MIN_PERIOD_SAMPLE,
    NO_STOP_LABEL,
    PERIOD_ALL,
    PERIOD_FIRST_HALF,
    PERIOD_SECOND_HALF,
    RECENT_YEARS,
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

# 성적표와 원자료 모두 앞에 붙는 식별 컬럼. 한 파일에 여러 칸을 쌓으므로 어느 행이 어떤
# 설정의 결과인지가 행 자체에 있어야 한다.
# **손절선은 여러 값을 낼 때만 붙는다** — 확정값 하나만 낼 때는 전 행이 같아 자리만 차지한다
IDENTITY_COLUMNS = (DISPLAY_TICKER, DISPLAY_EXPIRY_MONTH, DISPLAY_DIRECTION)
IDENTITY_COLUMNS_WITH_STOP = (*IDENTITY_COLUMNS, DISPLAY_STOP_LEVEL)


@dataclass(frozen=True)
class ExpiryOutputs:
    """실행 산출물

    Attributes:
        grid: 칸별 성적표. 손절선을 여러 개 넘겼을 때만 `손절선(%)` 컬럼이 붙는다
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


def run_expiry_trading(
    cells: Sequence[ExpiryCell] = EXPIRY_CELLS,
    stop_levels: Sequence[float | None] = (EXPIRY_STOP_LEVEL,),
) -> ExpiryOutputs:
    """대상 칸마다 손절선을 적용해 성적표와 원자료를 낸다.

    **기본은 확정 손절선 하나다.** 손절선이 하나뿐이면 `손절선(%)` 컬럼을 내지 않는다 —
    전 행이 같은 값이라 읽는 사람에게 아무것도 알려주지 않기 때문이다.
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

    # 손절선이 하나면 식별 컬럼에서 뺀다. 전 행이 같은 값인 컬럼은 자리만 차지한다
    with_stop_column = len(stop_levels) > 1

    grid_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []

    for cell in cells:
        dataset = _dataset(cell.dataset_key)
        entries = collect_entries(dataset, cell)

        for stop_level in stop_levels:
            block = _measure(dataset, cell, entries, stop_level, with_stop_column=with_stop_column)
            last_day = pd.Timestamp(entries.frame[COL_DATE].iloc[-1])
            identity = _identity(dataset, cell, stop_level, with_stop_column=with_stop_column)
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
    *,
    with_stop_column: bool,
) -> _Block:
    """한 칸 × 한 손절선의 체결 내역과 집계용 원값을 만든다.

    **표시용 표와 집계용 값을 함께 낸다.** 표는 저장 직전 반올림이 걸린 값이라,
    그것으로 다시 평균을 내면 이중 반올림이 되어 합계가 어긋난다.

    Args:
        dataset: 대상 종목
        cell: 대상 칸
        entries: 진입 목록
        stop_level: 손절선. `None` 이면 무손절
        with_stop_column: 식별 컬럼에 손절선을 넣을지 여부

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

        block.trades.append(
            _trade_row(
                dataset, cell, entries, order, entry_position, result, stop_level, with_stop_column=with_stop_column
            )
        )
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
    *,
    with_stop_column: bool,
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
        with_stop_column: 식별 컬럼에 손절선을 넣을지 여부

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
        **_identity(dataset, cell, stop_level, with_stop_column=with_stop_column),
        DISPLAY_ENTRY_DATE: pd.Timestamp(frame.iloc[entry_position][COL_DATE]).strftime(DATE_FORMAT),
        DISPLAY_ENTRY_PRICE: round(entry_price, dataset.price_decimals),
        DISPLAY_TARGET_DATE: entries.target_dates[order].strftime(DATE_FORMAT),
        DISPLAY_EXIT_DATE: pd.Timestamp(frame.iloc[exit_position][COL_DATE]).strftime(DATE_FORMAT),
        DISPLAY_HOLD_DAYS: result.hold_days,
        DISPLAY_EXIT_PRICE: round(exit_price, dataset.price_decimals),
        DISPLAY_RETURN: round(result.return_rate * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_EXIT_REASON: result.reason,
    }


def period_rows(
    entry_dates: pd.DatetimeIndex,
    returns: Sequence[float],
    *,
    last_day: pd.Timestamp,
    hold_days: Sequence[int] | None = None,
    reasons: Sequence[str] | None = None,
    excluded_count: int = 0,
) -> list[dict[str, Any]]:
    """체결 목록을 구간별로 갈라 성적 행들을 만든다.

    구간은 `EXPIRY_PERIODS` 다 — 전체 · 앞 절반 · 뒤 절반 · 최근 10년 · 최근 5년.
    **균등 2분할만으로는 신호가 식는 것을 놓친다** (루트 `CLAUDE.md` 측정의 원칙 17).

    **표본이 모자란 구간도 행을 남긴다.** 0건이어도 행이 있고 `판정가능` 이 「아니오」다 —
    행이 사라지면 사용자가 그 구간을 못 봤다는 사실 자체를 모른다 (패키지 절대 원칙 「표본 보존」).

    **최근 N년의 경계는 `last_day` 기준이다.** 실행 시각을 쓰면 코드를 안 고쳐도 날짜가
    지나면 결과가 바뀌어 재현되지 않는다.

    Args:
        entry_dates: 신호별 진입일 (시간순)
        returns: 신호별 수익률 (비율). `entry_dates` 와 길이가 같아야 한다
        last_day: 시세의 마지막 거래일. 「최근 N년」의 기준점이다
        hold_days: 신호별 보유 거래일 수. 없으면 평균 보유일을 비운다
        reasons: 신호별 청산 사유. 없으면 손절 건수를 비운다
        excluded_count: 청산일을 확정하지 못해 빠진 진입 수 (전체 행에만 적는다)

    Returns:
        구간마다 한 줄씩. 순서는 `EXPIRY_PERIODS` 와 같다

    Raises:
        ValueError: 진입일과 수익률의 길이가 다른 경우
    """
    if len(entry_dates) != len(returns):
        raise ValueError(f"진입일과 수익률의 길이가 다릅니다: 진입일 {len(entry_dates)}개, 수익률 {len(returns)}개")

    total = len(returns)
    half = total // 2
    values = np.asarray(returns, dtype=float)
    days = np.asarray(hold_days, dtype=float) if hold_days is not None else None
    labels = np.asarray(reasons, dtype=object) if reasons is not None else None

    # 홀수면 뒤 절반이 하나 많다. `studies` 의 시기 2등분과 같은 규칙이라 두 산출물이 어긋나지 않는다
    masks: dict[str, np.ndarray] = {
        PERIOD_ALL: np.ones(total, dtype=bool),
        PERIOD_FIRST_HALF: np.arange(total) < half,
        PERIOD_SECOND_HALF: np.arange(total) >= half,
    }
    for period, years in RECENT_YEARS.items():
        masks[period] = np.asarray(entry_dates > last_day - pd.DateOffset(years=years), dtype=bool)

    return [
        _period_row(
            period,
            values[masks[period]],
            days[masks[period]] if days is not None else None,
            labels[masks[period]] if labels is not None else None,
            excluded_count if period == PERIOD_ALL else 0,
        )
        for period in EXPIRY_PERIODS
    ]


def _period_row(
    period: str,
    values: np.ndarray,
    days: np.ndarray | None,
    labels: np.ndarray | None,
    excluded_count: int,
) -> dict[str, Any]:
    """구간 하나의 집계를 만든다.

    **합계는 「매 신호 같은 금액을 투입」한 수익률의 단순 합이다** (측정의 원칙 16).
    회당 평균만 적으면 크기 감각이 없으므로 둘을 나란히 둔다.

    **표본이 0건이면 지표를 비운다.** 0 으로 채우면 「손실도 이익도 없었다」로 읽히는데
    실제로는 「잰 적이 없다」이다.

    Args:
        period: 구간 이름
        values: 그 구간의 수익률 (비율)
        days: 그 구간의 보유 거래일 수
        labels: 그 구간의 청산 사유
        excluded_count: 제외 건수

    Returns:
        성적표 한 줄
    """
    count = len(values)
    percent = values * RATE_TO_PERCENT
    empty = count == 0

    return {
        DISPLAY_PERIOD: period,
        DISPLAY_SIGNAL_COUNT: count,
        DISPLAY_EXCLUDED_COUNT: excluded_count,
        DISPLAY_TOTAL: np.nan if empty else round(float(percent.sum()), PERCENT_DECIMALS),
        DISPLAY_MEAN: np.nan if empty else round(float(percent.mean()), PERCENT_DECIMALS),
        DISPLAY_WIN_RATE: np.nan if empty else round(float((values > 0).mean()) * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_MAX: np.nan if empty else round(float(percent.max()), PERCENT_DECIMALS),
        DISPLAY_MIN: np.nan if empty else round(float(percent.min()), PERCENT_DECIMALS),
        # 표본이 하나뿐인 칸에서 표본표준편차는 정의되지 않는다. 0 으로 채우면 "흔들림이 없다"로
        # 읽히므로 비워 둔다
        DISPLAY_STDEV: round(float(percent.std(ddof=1)), PERCENT_DECIMALS) if count > 1 else np.nan,
        DISPLAY_GAP_STOP_COUNT: 0 if labels is None else int((labels == EXIT_GAP_STOP).sum()),
        DISPLAY_INTRADAY_STOP_COUNT: 0 if labels is None else int((labels == EXIT_INTRADAY_STOP).sum()),
        DISPLAY_MEAN_HOLD: np.nan if (empty or days is None) else round(float(days.mean()), HOLD_DAYS_DECIMALS),
        # **미달이어도 행은 남는다.** 이 컬럼이 「판정에 쓰지 말라」를 표에 남기는 자리다
        DISPLAY_JUDGEABLE: JUDGEABLE_YES if count >= MIN_PERIOD_SAMPLE else JUDGEABLE_NO,
    }


def _identity(
    dataset: Dataset, cell: ExpiryCell, stop_level: float | None, *, with_stop_column: bool
) -> dict[str, Any]:
    """행을 식별하는 앞 컬럼들을 만든다.

    **손절선이 하나뿐이면 그 컬럼을 넣지 않는다.** 전 행이 같은 값이라 자리만 차지하며,
    확정 규칙의 손절선은 `EXPIRY_STOP_LEVEL` 이 SoT다.

    Args:
        dataset: 대상 종목
        cell: 대상 칸
        stop_level: 손절선. `None` 이면 무손절
        with_stop_column: 손절선 컬럼을 넣을지 여부

    Returns:
        식별 컬럼 dict
    """
    identity: dict[str, Any] = {
        DISPLAY_TICKER: dataset.ticker,
        DISPLAY_EXPIRY_MONTH: cell.expiry_month,
        DISPLAY_DIRECTION: EXPIRY_DIRECTION_DOWN if cell.bet_down else EXPIRY_DIRECTION_UP,
    }
    if with_stop_column:
        identity[DISPLAY_STOP_LEVEL] = (
            NO_STOP_LABEL if stop_level is None else round(-stop_level * RATE_TO_PERCENT, PERCENT_DECIMALS)
        )

    return identity


__all__ = ["Entries", "ExpiryOutputs", "collect_entries", "period_rows", "run_expiry_trading"]
