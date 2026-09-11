"""월말 매매의 손절 격자 실행 — 조립만 한다

**계산하지 않는다.** 판정식과 성적 산식이 이미 있으므로 그것들을 조합해 돌리고,
어느 행이 어떤 설정의 결과인지를 붙여 쌓기만 한다.

| 빌려 쓰는 것 | 어디서 |
| --- | --- |
| 진입일·청산일 정의 | `studies/month_end/schedule.py` — 검증 #10 과 **같은 날에 들어간다** |
| 손절 판정 (시가 → 장중 → 청산일) | `strategy/trade_fill.simulate_scheduled_trade` |
| 구간별 성적 산식 | `strategy/periods.period_rows` |

**이 매매법에는 고유 체결 로직이 한 줄도 없다.** 규칙이 옵션 만기일과 같아(며칠 들고 정해진 날
청산 + 손절) 공유 계층을 그대로 부른다. 그래서 `month_end_trading.py` 를 두지 않는다 —
만들면 내용이 비거나, 계산을 복사해 **같은 매매법의 성적이 산출물마다 갈라진다.**
빌려 쓰는 두 모듈은 **매매법 이름을 갖지 않는다** — 전에는 둘이 옵션 만기일 파일 안에 있어
월말이 그쪽을 import 했고, 그러면 옵션 만기일 사정으로 고칠 때 이 매매법 성적이 함께 바뀐다.

**새 판정식을 만들지 않는다.** 시가·장중 순서가 뒤바뀌면 손실이 실제보다 작게 나오는데,
그 함정을 여러 곳에서 관리하게 된다 (`docs/spec/월말_진입_설계.md` 가 가리키는 결정 ㉝).

**방향을 고르지 않는다** (측정의 원칙 11). 달마다 「아래로 걸었을 때」와 「위로 걸었을 때」를
나란히 내며, 어느 쪽으로 걸지는 결과를 읽는 쪽이 정한다. 고르는 코드를 두면 그 선택이
결론에 숨고, 검증 #10 의 월별 집계를 다시 계산하면 판정식이 두 벌이 된다.

**비용을 넣지 않는다.** 수수료·슬리피지·세금은 사용자가 별도로 요청할 때만 넣는다
(루트 `CLAUDE.md` 2026-09-06 확정).
"""

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from verify_lab.common_constants import COL_DATE, RATE_TO_PERCENT
from verify_lab.data.loader import load_market_csv, load_series_csv
from verify_lab.measure.constants import COL_EXCLUDED_REASON, REASON_NONE
from verify_lab.measure.screening import DIRECTION_DOWN, DIRECTION_UP
from verify_lab.report.constants import DATE_FORMAT, PERCENT_DECIMALS
from verify_lab.strategy.constants import (
    DISPLAY_DIRECTION,
    DISPLAY_ENTRY_DATE,
    DISPLAY_ENTRY_PRICE,
    DISPLAY_EXIT_DATE,
    DISPLAY_EXIT_PRICE,
    DISPLAY_EXIT_REASON,
    DISPLAY_HOLD_DAYS,
    DISPLAY_RETURN,
    DISPLAY_STOP_APPLICABLE,
    DISPLAY_STOP_LEVEL,
    DISPLAY_TICKER,
    FIXED_STOP_LEVEL,
    MONTH_END_STOP_LEVELS,
    STOP_APPLICABLE,
    STOP_NOT_APPLICABLE,
)
from verify_lab.strategy.periods import period_rows
from verify_lab.strategy.trade_fill import simulate_scheduled_trade
from verify_lab.studies.month_end.constants import (
    BASE_ENTRY_DAY,
    BASE_EXIT_OFFSET,
    COL_EXIT_DATE,
    COL_MONTH,
    DATASETS_KOSDAQ,
    Dataset,
)
from verify_lab.studies.month_end.schedule import month_entry_dates, month_exit_schedule
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 월 축의 한글 레이블. 이 파일에서만 쓰므로 여기에 둔다
DISPLAY_MONTH = "월"

# 손절선 축에서 무손절을 가리키는 값. **비워 두지 않는다** — 빈칸은 「값을 못 구했다」로 읽힌다
DISPLAY_NO_STOP = "무손절"

# 달력의 열두 달. 신호가 있는 달만 고르지 않는다 — 눈에 띄는 달만 돌리면 그 선택이
# 손절 결과에도 그대로 실린다
ALL_MONTHS = tuple(range(1, 13))

# `summary.json` 의 키
KEY_STOP_LEVELS = "stop_levels"
KEY_FIXED_STOP_LEVEL = "fixed_stop_level"
KEY_DATASETS = "datasets"
KEY_ROW_COUNTS = "row_counts"
KEY_TICKER = "ticker"
KEY_LABEL = "label"
KEY_FILE = "file"
KEY_PERIOD = "period"
KEY_ENTRY_COUNT = "entry_count"
KEY_EXCLUDED_COUNT = "excluded_count"
KEY_COST = "cost"

# 비용을 넣지 않았다는 사실을 산출물에 남긴다. 「빠뜨린 것」과 「일부러 뺀 것」을
# 구별할 수 없으면 다음 사람이 다시 계산한다
COST_NOTE = "맨몸 성적 — 수수료·슬리피지·세금 미반영 (사용자 요청 시에만 반영)"


@dataclass(frozen=True)
class TradingOutputs:
    """손절 격자 산출물

    Attributes:
        trades: 체결 원자료. 진입·청산 날짜와 실제 체결가가 들어 있다 (측정의 원칙 8)
        performance: 종목 × 월 × 방향 × 손절선 × 구간의 성적표
        performance_fixed_stop: 위 표에서 손절선 하나만 골라 그 컬럼을 뺀 것.
            **대상 넷을 한 장에서 견주기 위한 표**이며 값은 격자에서 그대로 온다
        summary: 실행 요약
    """

    trades: pd.DataFrame
    performance: pd.DataFrame
    performance_fixed_stop: pd.DataFrame
    summary: dict[str, Any]


@dataclass
class _Accumulator:
    """표 조각을 쌓는 자리"""

    trades: list[dict[str, Any]] = field(default_factory=list)
    performance: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class _Entries:
    """한 달의 진입·청산 위치

    Attributes:
        entry_positions: 진입일의 위치 인덱스
        exit_positions: 청산일의 위치 인덱스
        entry_dates: 진입일
    """

    entry_positions: list[int]
    exit_positions: list[int]
    entry_dates: pd.DatetimeIndex


def stop_level_label(stop_level: float | None) -> str:
    """손절선을 표시용 문자열로 바꾼다.

    Args:
        stop_level: 손절선 (비율). `None` 이면 무손절

    Returns:
        `5.0` 형태의 백분율 문자열, 또는 무손절 표기
    """
    if stop_level is None:
        return DISPLAY_NO_STOP

    return f"{stop_level * RATE_TO_PERCENT:.1f}"


def _stop_applicable(dataset: Dataset) -> str:
    """그 대상에 장중 손절을 걸 수 있었는지 표기를 낸다.

    **무손절 값만으로는 「손절을 걸었는데 안 걸렸다」와 구별되지 않는다.**
    지수는 종가만 있어 장중 최악을 알 수 없고, 그것은 성적의 성질을 바꾸는 사실이므로
    행 안에 남긴다.

    Args:
        dataset: 대상 종목 또는 지수

    Returns:
        「가능」 또는 「불가(고저가 없음)」
    """
    return STOP_NOT_APPLICABLE if dataset.is_index else STOP_APPLICABLE


def _fixed_stop_table(performance: pd.DataFrame) -> pd.DataFrame:
    """손절선 하나로 고정한 성적표를 격자에서 **골라낸다.**

    **다시 계산하지 않는다** — 같은 값을 두 곳에서 만들면 조용히 갈라진다.

    **지수는 그 손절선 행이 없으므로 무손절 행을 쓴다.** 걸러내면 지수가 표에서 통째로
    사라지는데, 30년 축을 보려고 넣은 것이라 목적이 없어진다.

    Args:
        performance: 손절선 격자 성적표

    Returns:
        손절선 컬럼을 뺀 성적표

    Raises:
        ValueError: 고를 행이 하나도 없는 경우 (격자에 그 손절선이 없다는 뜻이다)
    """
    wanted = stop_level_label(FIXED_STOP_LEVEL)
    applicable = performance[DISPLAY_STOP_APPLICABLE] == STOP_APPLICABLE

    picked = performance[
        (applicable & (performance[DISPLAY_STOP_LEVEL] == wanted))
        | (~applicable & (performance[DISPLAY_STOP_LEVEL] == DISPLAY_NO_STOP))
    ]
    if picked.empty:
        raise ValueError(f"손절선 {wanted}% 행을 격자에서 찾지 못했습니다. 손절선 목록에 그 값이 있는지 확인하세요")

    return picked.drop(columns=[DISPLAY_STOP_LEVEL]).reset_index(drop=True)


def _collect_entries(dataset: Dataset, frame: pd.DataFrame) -> tuple[dict[int, _Entries], int]:
    """검증 #10 과 같은 규칙으로 월별 진입·청산 위치를 만든다.

    **진입일 정의를 두 벌 만들지 않는다** — `studies` 의 함수를 그대로 부르므로
    측정과 매매가 같은 날에 들어간다.

    Args:
        dataset: 대상 종목
        frame: 날짜 오름차순 시세

    Returns:
        (월 → 진입 목록, 청산일을 확정하지 못해 빠진 진입 수)
    """
    trading_days = pd.DatetimeIndex(frame[COL_DATE])

    entries = month_entry_dates(trading_days, calendar_day=BASE_ENTRY_DAY)
    schedule = month_exit_schedule(trading_days, entries, exit_offset=BASE_EXIT_OFFSET)

    usable = schedule.frame[schedule.frame[COL_EXCLUDED_REASON] == REASON_NONE]
    excluded_count = len(schedule.frame) - len(usable)

    by_month: dict[int, _Entries] = {}
    for month in ALL_MONTHS:
        rows = usable[usable[COL_MONTH].dt.month == month]
        entry_dates = pd.DatetimeIndex(rows[COL_DATE])
        by_month[month] = _Entries(
            entry_positions=[int(position) for position in trading_days.get_indexer(entry_dates)],
            exit_positions=[
                int(position) for position in trading_days.get_indexer(pd.DatetimeIndex(rows[COL_EXIT_DATE]))
            ],
            entry_dates=entry_dates,
        )

    logger.debug(f"{dataset.ticker}: 진입 {len(usable):,}건, 제외 {excluded_count:,}건")

    return by_month, excluded_count


def _trade_row(
    dataset: Dataset,
    frame: pd.DataFrame,
    entry_position: int,
    result: Any,
    *,
    month: int,
    bet_down: bool,
    stop_level: float | None,
) -> dict[str, Any]:
    """체결 하나를 표 행으로 바꾼다.

    **청산가는 실제 체결가다.** 손절이 걸린 체결은 예정 청산일의 종가가 아니라 손절가
    (또는 갭이 열린 시가)에 나가므로, 예정일 종가를 적으면 차트와 대조할 때 어긋난다.

    Args:
        dataset: 대상 종목
        frame: 시세
        entry_position: 진입 위치
        result: 체결 결과
        month: 진입 달
        bet_down: 아래로 걸었는지 여부
        stop_level: 손절선. `None` 이면 무손절

    Returns:
        표 한 줄
    """
    entry_price = float(frame.iloc[entry_position][dataset.price_column])
    exit_position = entry_position + result.hold_days

    # 수익률은 방향 부호가 적용된 값이므로, 체결가를 되돌리려면 같은 부호를 다시 곱한다
    sign = -1.0 if bet_down else 1.0
    exit_price = entry_price * (1.0 + sign * result.return_rate)

    return {
        DISPLAY_TICKER: dataset.label,
        DISPLAY_MONTH: month,
        DISPLAY_DIRECTION: DIRECTION_DOWN if bet_down else DIRECTION_UP,
        DISPLAY_STOP_LEVEL: stop_level_label(stop_level),
        DISPLAY_STOP_APPLICABLE: _stop_applicable(dataset),
        DISPLAY_ENTRY_DATE: pd.Timestamp(frame.iloc[entry_position][COL_DATE]).strftime(DATE_FORMAT),
        DISPLAY_ENTRY_PRICE: round(entry_price, dataset.price_decimals),
        DISPLAY_EXIT_DATE: pd.Timestamp(frame.iloc[exit_position][COL_DATE]).strftime(DATE_FORMAT),
        DISPLAY_HOLD_DAYS: result.hold_days,
        DISPLAY_EXIT_PRICE: round(exit_price, dataset.price_decimals),
        DISPLAY_RETURN: round(result.return_rate * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_EXIT_REASON: result.reason,
    }


def _run_cell(
    dataset: Dataset,
    frame: pd.DataFrame,
    entries: _Entries,
    accumulator: _Accumulator,
    *,
    month: int,
    bet_down: bool,
    stop_level: float | None,
    last_day: pd.Timestamp,
) -> None:
    """한 칸(월 × 방향 × 손절선)을 돌려 체결과 성적을 쌓는다.

    Args:
        dataset: 대상 종목
        frame: 시세
        entries: 그 달의 진입 목록
        accumulator: 결과를 쌓는 자리
        month: 진입 달
        bet_down: 아래로 걸었는지 여부
        stop_level: 손절선. `None` 이면 무손절
        last_day: 시세의 마지막 거래일. 「최근 N년」의 기준점이다
    """
    returns: list[float] = []
    hold_days: list[int] = []
    reasons: list[str] = []

    for entry_position, exit_position in zip(entries.entry_positions, entries.exit_positions, strict=True):
        result = simulate_scheduled_trade(
            frame,
            entry_position,
            exit_position,
            bet_down=bet_down,
            stop_level=stop_level,
            price_column=dataset.price_column,
        )

        accumulator.trades.append(
            _trade_row(dataset, frame, entry_position, result, month=month, bet_down=bet_down, stop_level=stop_level)
        )
        returns.append(result.return_rate)
        hold_days.append(result.hold_days)
        reasons.append(result.reason)

    identity = {
        DISPLAY_TICKER: dataset.label,
        DISPLAY_MONTH: month,
        DISPLAY_DIRECTION: DIRECTION_DOWN if bet_down else DIRECTION_UP,
        DISPLAY_STOP_LEVEL: stop_level_label(stop_level),
        DISPLAY_STOP_APPLICABLE: _stop_applicable(dataset),
    }

    # 성적 산식은 `periods` 가 소유한다. 구간 5개와 갭손절 집계가 여기서 나온다
    for row in period_rows(entries.entry_dates, returns, last_day=last_day, hold_days=hold_days, reasons=reasons):
        accumulator.performance.append({**identity, **row})


def run_month_end_trading(
    datasets: tuple[Dataset, ...] = DATASETS_KOSDAQ,
    *,
    stop_levels: tuple[float, ...] = MONTH_END_STOP_LEVELS,
) -> TradingOutputs:
    """코스닥 월말 매매에 손절 격자를 걸어 성적을 낸다.

    **12개월 × 두 방향 × (손절선 + 무손절)** 을 전부 돈다. 눈에 띄는 달만 돌리면
    그 선택이 손절 결과에도 그대로 실린다.

    Args:
        datasets: 대상 목록. **지수도 받는다** — 다만 장중 손절에 고가·저가가 필요하므로
            지수는 무손절 한 줄로 강등되고 「손절적용」 컬럼에 그 사실이 남는다
        stop_levels: 손절선 목록 (비율). 무손절은 자동으로 함께 산출된다

    Returns:
        체결 원자료와 성적표 둘 (격자 · 손절선 고정)

    Raises:
        ValueError: 대상 목록이 비었거나 손절선이 비어 있는 경우
    """
    if not datasets:
        raise ValueError("검증 대상이 하나도 없습니다")
    if not stop_levels:
        raise ValueError("손절선 목록이 비어 있습니다")

    accumulator = _Accumulator()
    dataset_summaries: list[dict[str, Any]] = []

    # 무손절을 격자의 한 행으로 함께 돈다 — 「손절이 무엇을 막았는가」를 재려면 기준이 있어야 한다
    etf_levels: tuple[float | None, ...] = (*stop_levels, None)

    # **지수는 무손절 한 줄뿐이다.** 장중 손절에는 고가·저가가 필요한데 지수는 종가만 있고
    # (`docs/spec/월말_진입_설계.md` §7.6), 종가로 근사하면 실제보다 손절이 덜 걸려
    # 성적이 좋아진다. 거부하지 않고 강등하는 것은 **30년 축을 성적표에서 보기 위해서**다
    index_levels: tuple[float | None, ...] = (None,)

    for dataset in datasets:
        frame = load_series_csv(dataset.path) if dataset.is_index else load_market_csv(dataset.path)
        last_day = pd.Timestamp(frame[COL_DATE].iloc[-1])
        by_month, excluded_count = _collect_entries(dataset, frame)
        levels = index_levels if dataset.is_index else etf_levels

        for month in ALL_MONTHS:
            entries = by_month[month]
            for bet_down in (True, False):
                for stop_level in levels:
                    _run_cell(
                        dataset,
                        frame,
                        entries,
                        accumulator,
                        month=month,
                        bet_down=bet_down,
                        stop_level=stop_level,
                        last_day=last_day,
                    )

        dataset_summaries.append(
            {
                KEY_TICKER: dataset.ticker,
                KEY_LABEL: dataset.label,
                KEY_FILE: dataset.path.name,
                KEY_PERIOD: f"{frame[COL_DATE].iloc[0].date()} ~ {last_day.date()}",
                KEY_ENTRY_COUNT: sum(len(by_month[month].entry_positions) for month in ALL_MONTHS),
                KEY_EXCLUDED_COUNT: excluded_count,
            }
        )

    trades = pd.DataFrame(accumulator.trades)
    performance = pd.DataFrame(accumulator.performance)
    fixed_stop = _fixed_stop_table(performance)

    summary: dict[str, Any] = {
        KEY_STOP_LEVELS: [stop_level_label(level) for level in etf_levels],
        KEY_FIXED_STOP_LEVEL: stop_level_label(FIXED_STOP_LEVEL),
        KEY_COST: COST_NOTE,
        KEY_DATASETS: dataset_summaries,
        KEY_ROW_COUNTS: {
            "trades": len(trades),
            "performance": len(performance),
            "performance_fixed_stop": len(fixed_stop),
        },
    }

    logger.debug(f"손절 격자 완료: 체결 {len(trades):,}행, 성적 {len(performance):,}행, 고정 손절선 {len(fixed_stop):,}행")

    return TradingOutputs(trades=trades, performance=performance, performance_fixed_stop=fixed_stop, summary=summary)


__all__ = ["DISPLAY_MONTH", "DISPLAY_NO_STOP", "TradingOutputs", "run_month_end_trading", "stop_level_label"]
