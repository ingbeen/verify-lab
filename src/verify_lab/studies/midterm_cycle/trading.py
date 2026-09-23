"""중간선거_사이클 체결 조립 — 중간선거해의 성적과 분기 분해를 낸다

**계산하지 않는다.** 판정식과 성적 산식이 이미 있으므로 그것들을 조합해 돌리고,
어느 행이 어떤 설정의 결과인지를 붙여 쌓기만 한다.

| 빌려 쓰는 것 | 어디서 |
| --- | --- |
| 진입일·청산일 정의 | `studies/midterm_cycle/runner.signal_returns` — 측정과 **같은 날에 들어간다** |
| 손절 판정 (시가 → 장중 → 청산일) | `execution/trade_fill.simulate_scheduled_trade` |
| 구간별 성적 산식 | `execution/periods.period_rows` |
| 분기 분해와 낙폭 분포 | `studies/midterm_cycle/quarters` |
| 분할매수 체결 | `studies/midterm_cycle/split_entry` |
| 진입 위치 지표 | `studies/midterm_cycle/indicators` |

**표를 일곱 낸다.** 성적표·거래내역은 세 매매법이 공유하는 규격이고, 나머지 다섯은 이 매매법의
것이다 — **분기 표 둘**(진입이 9월 마지막 거래일이라 보유가 4분기·1분기·2분기에 맞아떨어진다),
**분할매수 표 둘**(원자료와 집계), **진입 위치 표 하나**.

[중요] **분할매수 표는 무손절이고 성적의 분모가 «배정액»이다** — 현금으로 남은 몫은 수익 0 으로
들어간다. 그래야 일시매수와 같은 분모로 견줘진다. **격자는 결과를 보기 전(2026-09-23)에 고정했다.**

[중요] **분기 표는 «무손절» 경로 하나로만 낸다** (`설계.md` 결정 ⑮). 손절이 걸리면 보유가
중간에 끊겨 남은 분기의 표본이 사라진다. 그래서 그 두 표에 `손절선(%)` 축이 없다.

**손절선은 격자다** (`.claude/rules/trading.md` 「경계는 행위」 — 고르지 않으므로 허용).
무손절 대조와 −5 ~ −30% 여덟 종이며, **다른 매매법의 −2 ~ −10% 가 9개월 보유에 너무
좁기 때문**에 넓혔다 — 2018년 4분기 하나만 S&P 500 −14% 라 그 격자로는 전 구간이 손절로
끊겨 「평평한 구간」을 찾을 수 없다. **값을 확정하는 것은 `규칙.md` 의 몫이다.**

**방향은 「위」 하나다.** 측정의 원칙 11(방향을 가리지 않는다)은 **측정 표의 오른 비율·내린
비율**이 충족한다 — 두 값이 1배 롱 기준으로 나란히 실려 반대 방향을 그대로 되짚을 수 있다.

[중요] **두 방향을 성적표에 함께 내면 계약 둘이 깨진다.**

| 무엇 | 어떻게 |
| --- | --- |
| **`측정.csv` 와의 1:1 조인** | 측정 표는 칸마다 한 행인데 성적표가 두 행이 된다. 실측으로 측정 20행 대 성적표 `시기=전체` 232행이었고, 「아래」 칸 셋은 **중앙값·기준선·배당락이 어디에도 없었다** |
| **「한 방향만 게이트를 통과한다」** | 손절이 손실만 끊어 두 방향의 평균이 더는 부호가 반대가 아니다 — 실측으로 **QQQ 대선해 −8% 칸이 위·아래 «둘 다» 후보**가 됐다. 같은 칸을 사고 동시에 팔라는 표가 된다 |

`src/verify_lab/CLAUDE.md` 가 후자를 「보장이 아니라 관찰이며 재실행할 때마다 대조한다」로
적어 두었고, **이 매매법이 그 관찰을 깬 첫 사례**다 (`docs/매매/중간선거_사이클/설계.md` 결정 ⑨).

**지수는 한 줄뿐이다** — 장중 손절에 고가·저가가 필요한데 지수는 종가만 있어
`손절선(%)` 에 「손절불가」로 적힌다. 거부하지 않고 강등하는 것은 **긴 기간 축을 성적표에서
보기 위해서**다 — ETF 의 중간선거 칸이 6~8건뿐이다.

**비용을 넣지 않는다.** 수수료·슬리피지·세금은 사용자가 별도로 요청할 때만 넣는다
(루트 `CLAUDE.md` 2026-09-06 확정).
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_DATE, RATE_TO_PERCENT
from verify_lab.execution.constants import (
    DISPLAY_DIRECTION,
    DISPLAY_ENTRY_DATE,
    DISPLAY_ENTRY_PRICE,
    DISPLAY_EXIT_DATE,
    DISPLAY_EXIT_PRICE,
    DISPLAY_EXIT_REASON,
    DISPLAY_HOLD_DAYS,
    DISPLAY_RETURN,
    DISPLAY_STOP_LEVEL,
    DISPLAY_TICKER,
    DISPLAY_TOTAL,
    DISPLAY_WORST_HOLD,
    NOTE_STOP_BASE,
    SUMMARY_FILENAME,
    TRADES_FILENAME,
    stop_level_value,
)
from verify_lab.execution.periods import period_rows, to_summary_frame
from verify_lab.execution.run_summary import build_run_summary
from verify_lab.execution.trade_fill import TradeResult, resolve_positions, simulate_scheduled_trade
from verify_lab.measure.constants import (
    COL_EXCLUDED_REASON,
    COL_EXIT_DATE,
    MIN_SAMPLE_PER_CELL,
    REASON_NONE,
)
from verify_lab.measure.screening import DIRECTION_DOWN, DIRECTION_UP
from verify_lab.report.constants import (
    DATE_FORMAT,
    DISPLAY_MAX,
    DISPLAY_MEAN,
    DISPLAY_MEDIAN,
    DISPLAY_MIN,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_UP_RATE,
    PERCENT_DECIMALS,
)
from verify_lab.report.run_summary import dataset_record
from verify_lab.studies.midterm_cycle.constants import (
    BET_DOWN,
    COL_CYCLE_POSITION,
    COL_CYCLE_YEAR,
    COL_DISPARITY_LONG,
    COL_DISPARITY_SHORT,
    COL_HIGH_DISTANCE,
    COL_RSI,
    CYCLE_POSITIONS,
    DATASETS,
    DISPLAY_AVERAGE_COST,
    DISPLAY_CYCLE_POSITION,
    DISPLAY_CYCLE_YEAR,
    DISPLAY_DISPARITY_LONG,
    DISPLAY_DISPARITY_SHORT,
    DISPLAY_FALLBACK,
    DISPLAY_FIRST_QUARTER_RETURN,
    DISPLAY_HIGH_DISTANCE,
    DISPLAY_HOLD_WORST_MEAN,
    DISPLAY_HOLD_WORST_MEDIAN,
    DISPLAY_INVESTED,
    DISPLAY_LUMP_DIFF,
    DISPLAY_MEAN_AVERAGE_COST,
    DISPLAY_MEAN_INVESTED,
    DISPLAY_QUARTER,
    DISPLAY_RSI,
    DISPLAY_RULE_FILLED,
    DISPLAY_SEGMENT_END_DATE,
    DISPLAY_SEGMENT_END_PRICE,
    DISPLAY_SEGMENT_START_DATE,
    DISPLAY_SEGMENT_START_PRICE,
    DISPLAY_SEGMENT_WORST_DEEPEST,
    DISPLAY_SEGMENT_WORST_MEAN,
    DISPLAY_SEGMENT_WORST_MEDIAN,
    DISPLAY_SPLIT_METHOD,
    DISPLAY_WORST_DEEPEST,
    DISPLAY_WORST_MEAN,
    DISPLAY_WORST_MEDIAN,
    DISPLAY_WORST_Q25,
    DISPLAY_WORST_Q75,
    DISPLAY_WORST_SHALLOWEST,
    DISPLAY_WORST_VS_ENTRY,
    DISPLAY_WORST_VS_SEGMENT,
    DRAWDOWN_BUCKETS,
    ENTRY_CONTEXT_FILENAME,
    ENTRY_MONTH,
    EXIT_MONTH,
    KEY_ENTRY_COUNT,
    KEY_ENTRY_MONTH,
    KEY_EXCLUDED_COUNT,
    KEY_EXIT_MONTH,
    KEY_LABEL,
    MAX_TRANCHES,
    PERIOD_WHOLE,
    QUARTER_LABELS,
    QUARTER_SUMMARY_FILENAME,
    QUARTER_TRADES_FILENAME,
    SPLIT_METHODS,
    SPLIT_SUMMARY_FILENAME,
    SPLIT_TRADES_FILENAME,
    STOP_LEVELS_ETF,
    STOP_LEVELS_INDEX,
    TRACK_NAME,
    TRANCHE_FIELD_DATE,
    TRANCHE_FIELD_PRICE,
    TRANCHE_FIELD_REASON,
    Dataset,
    LumpSum,
    SplitMethod,
    bucket_label,
    tranche_label,
)
from verify_lab.studies.midterm_cycle.indicators import indicator_frame
from verify_lab.studies.midterm_cycle.quarters import QuarterTrade, drawdown_profile, quarter_trades
from verify_lab.studies.midterm_cycle.runner import load_dataset, signal_returns
from verify_lab.studies.midterm_cycle.split_entry import EntryWindow, SplitResult, entry_windows, simulate_split_entry
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# `summary.json` 의 `rule` 안 — 무엇을 어떤 규칙으로 돌렸나.
# **최상위 키와 비용 표기는 `execution/run_summary.py` 가 소유한다**
KEY_STOP_LEVELS = "stop_levels"
KEY_TARGETS = "targets"
KEY_DIRECTION = "direction"
KEY_SPLIT_METHODS = "split_methods"
KEY_FALLBACKS = "fallbacks"

# 산출물만 보고는 알 수 없는 실행 조건
NOTE_ENTRY = "진입은 9월 마지막 거래일 종가, 청산은 다음해 6월 마지막 거래일 종가다 — " "둘 다 말일이 휴장이면 직전 거래일로 «앞당긴다». 측정과 같은 날에 들어간다"
NOTE_AXIS = (
    "사이클 위치는 중간선거해 한 칸만 낸다 (사용자 결정). "
    "사이클 네 칸을 견주어 「달력이라 좋았다」와 「중간선거 뒤라 좋았다」를 가른 대조는 "
    "10월 첫 거래일 진입으로 잰 기록이며 `docs/매매/중간선거_사이클/결과.md` 가 갖는다 — "
    "지금 구성으로는 재현되지 않는다"
)
NOTE_QUARTER = (
    "분기 표 둘(`분기.csv`·`분기내역.csv`)은 «무손절» 경로 하나로만 낸다 — 손절이 걸리면 "
    "보유가 중간에 끊겨 남은 분기의 표본이 사라지고, 끊긴 분기는 「그 분기 성적」이 아니라 "
    "「손절까지의 성적」이 된다. 그래서 그 두 표에는 「손절선(%)」 축이 없다"
)
# **하한을 리터럴로 적지 않는다.** 값의 소유자는 `measure/constants.MIN_SAMPLE_PER_CELL` 하나이고,
# 여기 숫자를 박으면 그 상수를 바꿨을 때 **`summary.json` 이 같은 파일 안의 `판정가능` 과
# 어긋난 말을 하면서 예외는 나지 않는다**
NOTE_SAMPLE = (
    f"중간선거 칸의 표본이 ETF 로는 6~8건이라 칸당 표본 하한({MIN_SAMPLE_PER_CELL})에 못 미친다 — "
    "「판정가능」이 전 구간에서 「아니오」이고 우연확률도 붙지 않는다. 결론의 일부이지 버그가 아니다"
)
NOTE_SPLIT = (
    "분할매수 표 둘(`분할매수.csv`·`분할매수내역.csv`)은 «무손절»이고 수익률·보유 중 최악의 분모는 "
    "«배정액»이다 — 현금으로 남은 몫은 수익 0 으로 들어간다. 첫 몫은 언제나 9월 마지막 거래일 종가이고, "
    "추가 몫은 진입 다음 거래일부터 12월 마지막 거래일까지 산다 — A(월말)와 12월 말 일괄은 그날 종가에, "
    "B·C 는 «판정일 종가로 판정하고 다음 거래일 종가에» 산다(같은 종가에 사면 미래 참조다). "
    "격자는 결과를 보기 전(2026-09-23)에 고정했고, 4분기 창 자체는 「최저점이 4분기에 있었다」는 "
    "측정을 보고 정한 값이다"
)
NOTE_ENTRY_CONTEXT = (
    "`진입위치.csv` 의 지표는 진입일 종가까지로만 계산한다. 창(52주 = 252거래일 · 200일)이 차기 전인 " "진입은 그 칸을 비운다 — 0 으로 채우면 「그때 고점이었다」 같은 없는 사실이 된다"
)
NOTE_DIVIDEND = "보유가 9개월이라 분기 배당 3회가 «매번» 구조적으로 들어온다. 원본가로 재므로 " "「위」 칸의 성적은 그만큼 과소평가돼 있으며, 그 크기는 측정 표의 배당락 세 컬럼이 낸다"
NOTE_INDEX = (
    "지수는 종가만 있어 장중 손절을 잴 수 없다. 한 줄로만 나오며 「손절선(%)」 에 「손절불가」로 적힌다. "
    "같은 이유로 「보유 중 최악(%)」 도 종가로 재므로 ETF 행(장중 고가·저가 기준)보다 얕게 나온다. "
    "게다가 옛 구간은 고가·저가가 종가로 채워져 있어(^GSPC 34.5%) OHLCV 로 받았다면 "
    "「장중에 안 밀렸다」가 조용히 실렸을 자리다"
)


@dataclass(frozen=True)
class TradingOutputs:
    """체결 산출물

    Attributes:
        trades: 체결 원자료. 진입·청산 날짜와 실제 체결가가 들어 있다 (측정의 원칙 8)
        performance: 종목 × 사이클 위치 × 손절선 × 구간의 성적표. **방향은 「위」 하나다**
        quarter_trades: 분기 원자료. 종목 × 진입 연도 × 분기마다 한 행이다
        quarter_summary: 분기 집계. 종목 × (전체 보유 · 분기 셋) 마다 한 행이다
        split_trades: 분할매수 원자료. 종목 × 분할 방식 × 미체결 처리 × 진입 연도마다 한 행이다
        split_summary: 분할매수 집계. 종목 × 분할 방식 × 미체결 처리마다 한 행이다
        entry_context: 진입 위치. 종목 × 진입 연도마다 한 행이다
        summary: 실행 요약
    """

    trades: pd.DataFrame
    performance: pd.DataFrame
    quarter_trades: pd.DataFrame
    quarter_summary: pd.DataFrame
    split_trades: pd.DataFrame
    split_summary: pd.DataFrame
    entry_context: pd.DataFrame
    summary: dict[str, Any]


@dataclass
class _Accumulator:
    """표 조각을 쌓는 자리"""

    trades: list[dict[str, Any]] = field(default_factory=list)
    performance: list[dict[str, Any]] = field(default_factory=list)
    quarter_trades: list[dict[str, Any]] = field(default_factory=list)
    quarter_summary: list[dict[str, Any]] = field(default_factory=list)
    split_trades: list[dict[str, Any]] = field(default_factory=list)
    split_summary: list[dict[str, Any]] = field(default_factory=list)
    entry_context: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class _Entries:
    """한 칸의 진입·청산 위치

    Attributes:
        entry_positions: 진입일의 위치 인덱스
        exit_positions: 청산일의 위치 인덱스
        entry_dates: 진입일
        entry_years: 진입 연도. 거래내역에 실어 사용자가 차트로 대조한다
    """

    entry_positions: list[int]
    exit_positions: list[int]
    entry_dates: pd.DatetimeIndex
    entry_years: list[int]


def _collect_entries(dataset: Dataset, frame: pd.DataFrame) -> tuple[dict[str, _Entries], int]:
    """측정과 같은 규칙으로 사이클 위치별 진입·청산 위치를 만든다.

    **진입일 정의를 두 벌 만들지 않는다** — `runner.signal_returns` 를 그대로 부르므로
    측정과 체결이 같은 날에 들어간다.

    Args:
        dataset: 대상 종목
        frame: 날짜 오름차순 가격 데이터

    Returns:
        (사이클 위치 → 진입 목록, 청산일을 확정하지 못해 빠진 진입 수)

    Raises:
        RuntimeError: 진입일·청산일이 시세의 거래일에 없는 경우 (내부 불변조건 위반)
    """
    trading_days = pd.DatetimeIndex(frame[COL_DATE])
    returns = signal_returns(frame, dataset)

    kept = returns[COL_EXCLUDED_REASON] == REASON_NONE
    usable = returns[kept]
    excluded_count = int((~kept).sum())

    by_position: dict[str, _Entries] = {}
    for position in CYCLE_POSITIONS:
        rows = usable[usable[COL_CYCLE_POSITION] == position]
        entry_dates = pd.DatetimeIndex(rows[COL_DATE])
        exit_dates = pd.DatetimeIndex(rows[COL_EXIT_DATE])
        by_position[position] = _Entries(
            entry_positions=[
                int(position_index) for position_index in resolve_positions(trading_days, entry_dates, label="진입일")
            ],
            exit_positions=[
                int(position_index) for position_index in resolve_positions(trading_days, exit_dates, label="청산일")
            ],
            entry_dates=entry_dates,
            entry_years=[int(year) for year in rows[COL_CYCLE_YEAR]],
        )

    logger.debug(f"{dataset.label}: 진입 {len(usable):,}건, 제외 {excluded_count:,}건")

    return by_position, excluded_count


def _trade_row(
    dataset: Dataset,
    frame: pd.DataFrame,
    entry_position: int,
    result: TradeResult,
    *,
    position: str,
    entry_year: int,
    bet_down: bool,
    stop_display: float | str,
) -> dict[str, Any]:
    """체결 하나를 표 행으로 바꾼다.

    **청산가는 실제 체결가다.** 손절이 걸린 체결은 예정 청산일의 종가가 아니라 손절가
    (또는 갭이 열린 시가)에 나간다.

    Args:
        dataset: 대상 종목
        frame: 가격 데이터
        entry_position: 진입 위치
        result: 체결 결과
        position: 사이클 위치
        entry_year: 진입 연도
        bet_down: 아래로 걸었는지 여부
        stop_display: 산출물에 실을 손절선 표기. **여기서 만들지 않고 받는다**

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
        DISPLAY_CYCLE_POSITION: position,
        DISPLAY_CYCLE_YEAR: entry_year,
        DISPLAY_DIRECTION: DIRECTION_DOWN if bet_down else DIRECTION_UP,
        DISPLAY_STOP_LEVEL: stop_display,
        DISPLAY_ENTRY_DATE: pd.Timestamp(frame.iloc[entry_position][COL_DATE]).strftime(DATE_FORMAT),
        DISPLAY_ENTRY_PRICE: round(entry_price, dataset.price_decimals),
        DISPLAY_EXIT_DATE: pd.Timestamp(frame.iloc[exit_position][COL_DATE]).strftime(DATE_FORMAT),
        DISPLAY_HOLD_DAYS: result.hold_days,
        DISPLAY_EXIT_PRICE: round(exit_price, dataset.price_decimals),
        DISPLAY_RETURN: round(result.return_rate * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_WORST_HOLD: round(result.worst_hold_rate * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_EXIT_REASON: result.reason,
    }


def _run_cell(
    dataset: Dataset,
    frame: pd.DataFrame,
    entries: _Entries,
    accumulator: _Accumulator,
    *,
    position: str,
    bet_down: bool,
    stop_level: float | None,
    last_day: pd.Timestamp,
) -> None:
    """한 칸(사이클 위치 × 손절선)을 돌려 체결과 성적을 쌓는다.

    Args:
        dataset: 대상 종목
        frame: 가격 데이터
        entries: 그 위치의 진입 목록
        accumulator: 결과를 쌓는 자리
        position: 사이클 위치
        bet_down: 아래로 걸었는지 여부
        stop_level: 손절선. `None` 이면 무손절
        last_day: 가격 데이터의 마지막 거래일. 「최근 N년」의 기준점이다
    """
    returns: list[float] = []
    hold_days: list[int] = []
    reasons: list[str] = []
    worst_hold_rates: list[float] = []

    # **표기를 한 번만 만든다.** 두 표가 같은 칸에 다른 값을 실으면 조인이 안 된다
    stop_display = stop_level_value(stop_level, measurable=not dataset.is_index)

    for entry_position, exit_position, entry_year in zip(
        entries.entry_positions, entries.exit_positions, entries.entry_years, strict=True
    ):
        result = simulate_scheduled_trade(
            frame,
            entry_position,
            exit_position,
            bet_down=bet_down,
            stop_level=stop_level,
            price_column=dataset.price_column,
        )

        accumulator.trades.append(
            _trade_row(
                dataset,
                frame,
                entry_position,
                result,
                position=position,
                entry_year=entry_year,
                bet_down=bet_down,
                stop_display=stop_display,
            )
        )
        returns.append(result.return_rate)
        hold_days.append(result.hold_days)
        reasons.append(result.reason)
        worst_hold_rates.append(result.worst_hold_rate)

    identity = {
        DISPLAY_TICKER: dataset.label,
        DISPLAY_CYCLE_POSITION: position,
        DISPLAY_DIRECTION: DIRECTION_DOWN if bet_down else DIRECTION_UP,
        DISPLAY_STOP_LEVEL: stop_display,
    }

    for row in period_rows(
        entries.entry_dates,
        returns,
        last_day=last_day,
        # **판정은 살 수 있는 것에만 건다** (측정의 원칙 9)
        tradable=dataset.is_judged,
        hold_days=hold_days,
        reasons=reasons,
        worst_hold_rates=worst_hold_rates,
    ):
        accumulator.performance.append({**identity, **row})


def _quarter_detail_row(
    dataset: Dataset, frame: pd.DataFrame, *, position: str, entry_year: int, trade: QuarterTrade
) -> dict[str, Any]:
    """분기 체결 하나를 표 행으로 바꾼다.

    **`진입가`·`청산가` 가 아니라 `시작가`·`종료가` 다** — 분기의 시작가는 «직전 분기의 종가»이지
    이 매매의 진입가가 아니다. 이름을 같이 쓰면 두 값이 같은 것으로 읽힌다.

    Args:
        dataset: 대상 종목
        frame: 가격 데이터
        position: 사이클 위치
        entry_year: 진입 연도
        trade: 분기 체결

    Returns:
        표 한 줄
    """
    return {
        DISPLAY_TICKER: dataset.label,
        DISPLAY_CYCLE_POSITION: position,
        DISPLAY_CYCLE_YEAR: entry_year,
        DISPLAY_QUARTER: trade.label,
        DISPLAY_DIRECTION: DIRECTION_DOWN if BET_DOWN else DIRECTION_UP,
        DISPLAY_SEGMENT_START_DATE: pd.Timestamp(frame.iloc[trade.start_position][COL_DATE]).strftime(DATE_FORMAT),
        DISPLAY_SEGMENT_START_PRICE: round(trade.start_price, dataset.price_decimals),
        DISPLAY_SEGMENT_END_DATE: pd.Timestamp(frame.iloc[trade.end_position][COL_DATE]).strftime(DATE_FORMAT),
        DISPLAY_SEGMENT_END_PRICE: round(trade.end_price, dataset.price_decimals),
        DISPLAY_HOLD_DAYS: trade.hold_days,
        DISPLAY_RETURN: round(trade.return_rate * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_WORST_VS_ENTRY: round(trade.worst_vs_entry * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_WORST_VS_SEGMENT: round(trade.worst_vs_start * RATE_TO_PERCENT, PERCENT_DECIMALS),
    }


def _quarter_summary_row(
    dataset: Dataset,
    *,
    position: str,
    label: str,
    returns: list[float],
    worst_vs_entry: list[float],
    worst_vs_segment: list[float],
) -> dict[str, Any]:
    """한 구간(전체 보유 또는 분기 하나)의 수익과 낙폭 분포를 표 행으로 바꾼다.

    **`가장 깊게` 는 성적표의 `보유 중 최악(%)` 과 같은 값이다** — 전체 보유 행에서 두 표가
    이어지는 지점이며, 나머지 분포 컬럼이 「보통 얼마나 밀리나」를 답한다.

    Args:
        dataset: 대상 종목
        position: 사이클 위치
        label: 구간 이름
        returns: 그 구간의 수익률 (비율)
        worst_vs_entry: **진입가** 대비 보유 중 최악 (비율)
        worst_vs_segment: **그 구간 시작가** 대비 보유 중 최악 (비율).
            전체 보유 행에서는 진입가가 곧 시작가라 두 목록이 같다

    Returns:
        표 한 줄
    """
    versus_entry = drawdown_profile(worst_vs_entry)
    versus_segment = drawdown_profile(worst_vs_segment)

    return {
        DISPLAY_TICKER: dataset.label,
        DISPLAY_CYCLE_POSITION: position,
        DISPLAY_QUARTER: label,
        DISPLAY_DIRECTION: DIRECTION_DOWN if BET_DOWN else DIRECTION_UP,
        **_return_columns(returns),
        DISPLAY_WORST_MEAN: round(versus_entry.mean * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_WORST_MEDIAN: round(versus_entry.median * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_WORST_Q25: round(versus_entry.quantile_25 * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_WORST_Q75: round(versus_entry.quantile_75 * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_WORST_SHALLOWEST: round(versus_entry.shallowest * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_WORST_DEEPEST: round(versus_entry.deepest * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_SEGMENT_WORST_MEAN: round(versus_segment.mean * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_SEGMENT_WORST_MEDIAN: round(versus_segment.median * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_SEGMENT_WORST_DEEPEST: round(versus_segment.deepest * RATE_TO_PERCENT, PERCENT_DECIMALS),
        # **헤더를 손으로 적지 않는다** — 격자를 고치면 컬럼이 따라온다
        **{
            bucket_label(threshold): count
            for threshold, count in zip(DRAWDOWN_BUCKETS, versus_entry.within, strict=True)
        },
    }


def _return_columns(returns: list[float]) -> dict[str, Any]:
    """수익률 목록의 요약 컬럼 — 분기 표와 분할매수 표가 같은 산식을 쓴다.

    **두 표가 각자 계산하지 않는다.** 같은 이름의 컬럼(`합계`·`평균`·`중앙값` …)이 두 표에서
    다른 반올림 순서로 나오면 같은 체결이 다른 숫자로 적힌다.

    Args:
        returns: 수익률 (비율)

    Returns:
        표본 · 합계 · 평균 · 중앙값 · 오른 비율 · 최고 · 최악 (백분율 2자리)
    """
    percent = pd.Series(returns, dtype="float64") * RATE_TO_PERCENT

    return {
        DISPLAY_SAMPLE_COUNT: len(percent),
        DISPLAY_TOTAL: round(float(percent.sum()), PERCENT_DECIMALS),
        DISPLAY_MEAN: round(float(percent.mean()), PERCENT_DECIMALS),
        DISPLAY_MEDIAN: round(float(percent.median()), PERCENT_DECIMALS),
        DISPLAY_UP_RATE: round(float((percent > 0).mean()) * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_MAX: round(float(percent.max()), PERCENT_DECIMALS),
        DISPLAY_MIN: round(float(percent.min()), PERCENT_DECIMALS),
    }


def _percent(rate: float) -> float:
    """비율을 백분율 2자리로. **비어 있으면 비운 채로 둔다** — 0 으로 채우지 않는다.

    Args:
        rate: 비율

    Returns:
        백분율
    """
    # **`+ 0.0` 은 음수 0 을 지운다.** 일시매수의 평균 매수가처럼 산식상 0 인 값이 부동소수점
    # 잔차로 −1e-16 이 되면 반올림 뒤 `-0.0` 으로 찍혀 「첫 몫보다 싸게 샀다」로 읽힌다
    return round(float(rate) * RATE_TO_PERCENT, PERCENT_DECIMALS) + 0.0


def _split_trade_row(
    dataset: Dataset,
    frame: pd.DataFrame,
    window: EntryWindow,
    result: SplitResult,
    *,
    position: str,
    entry_year: int,
    method: SplitMethod,
    fallback: str,
) -> dict[str, Any]:
    """분할매수 체결 하나를 표 행으로 바꾼다.

    **몫이 없는 칸은 비우고, 몫이 있는데 안 산 칸은 사유에 「미체결」을 적는다** — 둘을 한 값으로
    적으면 「그 방식에는 그 몫이 없다」와 「조건이 안 왔다」가 구별되지 않는다.

    Args:
        dataset: 대상 종목
        frame: 가격 데이터
        window: 추가 매수 창
        result: 분할 체결 결과
        position: 사이클 위치
        entry_year: 진입 연도
        method: 분할 방식
        fallback: 미체결 처리

    Returns:
        표 한 줄
    """
    dates = pd.DatetimeIndex(frame[COL_DATE])
    prices = frame[dataset.price_column]

    row: dict[str, Any] = {
        DISPLAY_TICKER: dataset.label,
        DISPLAY_CYCLE_POSITION: position,
        DISPLAY_CYCLE_YEAR: entry_year,
        DISPLAY_SPLIT_METHOD: method.label,
        DISPLAY_FALLBACK: fallback,
        DISPLAY_ENTRY_DATE: dates[window.entry_position].strftime(DATE_FORMAT),
        DISPLAY_ENTRY_PRICE: round(float(prices.iloc[window.entry_position]), dataset.price_decimals),
    }
    # **첫 몫은 진입일·진입가가 담는다** — 2번째 몫부터 펼친다
    for order in range(2, MAX_TRANCHES + 1):
        fill = result.fills[order - 1] if order <= len(result.fills) else None
        bought_at = fill.position if fill is not None else None
        row[tranche_label(order, TRANCHE_FIELD_DATE)] = (
            dates[bought_at].strftime(DATE_FORMAT) if bought_at is not None else None
        )
        row[tranche_label(order, TRANCHE_FIELD_PRICE)] = (
            round(float(prices.iloc[bought_at]), dataset.price_decimals) if bought_at is not None else None
        )
        row[tranche_label(order, TRANCHE_FIELD_REASON)] = fill.reason if fill is not None else None

    row.update(
        {
            DISPLAY_EXIT_DATE: dates[window.exit_position].strftime(DATE_FORMAT),
            DISPLAY_EXIT_PRICE: round(float(prices.iloc[window.exit_position]), dataset.price_decimals),
            DISPLAY_INVESTED: _percent(result.invested_rate),
            DISPLAY_AVERAGE_COST: _percent(result.average_cost_rate),
            DISPLAY_RETURN: _percent(result.return_rate),
            DISPLAY_WORST_HOLD: _percent(result.worst_hold_rate),
        }
    )

    return row


def _split_summary_row(
    dataset: Dataset,
    *,
    position: str,
    method: SplitMethod,
    fallback: str,
    results: list[SplitResult],
    lump_mean: float,
) -> dict[str, Any]:
    """분할 방식 한 칸의 집계. **분기 표와 같은 형태**(칸마다 한 행 · 중앙값 · 낙폭 분포)다.

    **시기 행을 내지 않는다** — 분할매수 고유 컬럼(투자 비율 · 평균 매수가)을 시기 구간마다
    붙이려면 `execution/periods` 가 안에서만 만드는 구간 마스크를 밖에서 다시 만들어야 하고,
    그러면 시기 분할이 두 벌이 된다. 일시매수의 시기 5행은 `성적표.csv` 에 있다.

    Args:
        dataset: 대상 종목
        position: 사이클 위치
        method: 분할 방식
        fallback: 미체결 처리
        results: 진입마다의 결과
        lump_mean: 같은 대상·위치의 일시매수 평균 (백분율, **표에 실린 반올림 뒤 값**)

    Returns:
        표 한 줄
    """
    returns = [result.return_rate for result in results]
    worst = drawdown_profile([result.worst_hold_rate for result in results])
    summary = _return_columns(returns)

    return {
        DISPLAY_TICKER: dataset.label,
        DISPLAY_CYCLE_POSITION: position,
        DISPLAY_DIRECTION: DIRECTION_DOWN if BET_DOWN else DIRECTION_UP,
        DISPLAY_SPLIT_METHOD: method.label,
        DISPLAY_FALLBACK: fallback,
        **summary,
        # **표에 실린 값끼리 뺀다** — 원값으로 빼면 표가 자기 자신과 어긋난다
        DISPLAY_LUMP_DIFF: round(summary[DISPLAY_MEAN] - lump_mean, PERCENT_DECIMALS),
        DISPLAY_HOLD_WORST_MEAN: _percent(worst.mean),
        DISPLAY_HOLD_WORST_MEDIAN: _percent(worst.median),
        # **가장 깊은 한 건이 곧 성적표의 `보유 중 최악(%)`** 이다 — 같은 이름을 쓴다
        DISPLAY_WORST_HOLD: _percent(worst.deepest),
        DISPLAY_MEAN_INVESTED: _percent(float(np.mean([result.invested_rate for result in results]))),
        DISPLAY_MEAN_AVERAGE_COST: _percent(float(np.mean([result.average_cost_rate for result in results]))),
        DISPLAY_RULE_FILLED: sum(result.rule_filled for result in results),
    }


def _run_split(
    dataset: Dataset,
    frame: pd.DataFrame,
    entries: _Entries,
    windows: list[EntryWindow],
    indicators: pd.DataFrame,
    accumulator: _Accumulator,
    *,
    position: str,
) -> None:
    """분할 격자 전부를 돌려 원자료와 집계를 쌓는다.

    **첫 방식이 일시매수여야 한다** — 나머지 칸의 「일시매수 대비 차이」가 그 행을 기준으로 삼는다.

    Args:
        dataset: 대상 종목
        frame: 가격 데이터
        entries: 그 위치의 진입 목록
        windows: 진입마다의 추가 매수 창
        indicators: 지표 표
        accumulator: 결과를 쌓는 자리
        position: 사이클 위치

    Raises:
        RuntimeError: 격자의 첫 방식이 일시매수가 아닌 경우 (내부 불변조건 위반)
    """
    if not isinstance(SPLIT_METHODS[0].trigger, LumpSum):
        raise RuntimeError(f"내부 불변조건 위반: 분할 격자의 첫 방식이 일시매수가 아닙니다: {SPLIT_METHODS[0].label}")

    lump_mean = 0.0
    for method in SPLIT_METHODS:
        for fallback in method.fallbacks:
            results = [
                simulate_split_entry(
                    frame,
                    window,
                    method,
                    fallback=fallback,
                    price_column=dataset.price_column,
                    indicators=indicators,
                )
                for window in windows
            ]
            for window, entry_year, result in zip(windows, entries.entry_years, results, strict=True):
                accumulator.split_trades.append(
                    _split_trade_row(
                        dataset,
                        frame,
                        window,
                        result,
                        position=position,
                        entry_year=entry_year,
                        method=method,
                        fallback=fallback,
                    )
                )

            if isinstance(method.trigger, LumpSum):
                lump_mean = _return_columns([result.return_rate for result in results])[DISPLAY_MEAN]
            accumulator.split_summary.append(
                _split_summary_row(
                    dataset, position=position, method=method, fallback=fallback, results=results, lump_mean=lump_mean
                )
            )


def _run_entry_context(
    dataset: Dataset,
    frame: pd.DataFrame,
    entries: _Entries,
    indicators: pd.DataFrame,
    accumulator: _Accumulator,
    *,
    position: str,
) -> None:
    """진입마다 그날의 위치(지표 넷)와 그 해의 결과를 한 행에 싣는다.

    **결과는 무손절 경로다** — 「고점 근처에서 들어간 해가 더 깊이 밀렸나」를 묻는 표라
    손절이 끊은 경로로는 답이 안 나온다.

    Args:
        dataset: 대상 종목
        frame: 가격 데이터
        entries: 그 위치의 진입 목록
        indicators: 지표 표
        accumulator: 결과를 쌓는 자리
        position: 사이클 위치
    """
    dates = pd.DatetimeIndex(frame[COL_DATE])
    prices = frame[dataset.price_column]

    for entry_position, exit_position, entry_year in zip(
        entries.entry_positions, entries.exit_positions, entries.entry_years, strict=True
    ):
        whole = simulate_scheduled_trade(
            frame,
            entry_position,
            exit_position,
            bet_down=BET_DOWN,
            stop_level=None,
            price_column=dataset.price_column,
        )
        first_quarter = quarter_trades(
            frame,
            entry_position=entry_position,
            exit_position=exit_position,
            bet_down=BET_DOWN,
            price_column=dataset.price_column,
        )[0]
        on_entry = indicators.iloc[entry_position]

        accumulator.entry_context.append(
            {
                DISPLAY_TICKER: dataset.label,
                DISPLAY_CYCLE_POSITION: position,
                DISPLAY_CYCLE_YEAR: entry_year,
                DISPLAY_ENTRY_DATE: dates[entry_position].strftime(DATE_FORMAT),
                DISPLAY_ENTRY_PRICE: round(float(prices.iloc[entry_position]), dataset.price_decimals),
                DISPLAY_HIGH_DISTANCE: _percent(on_entry[COL_HIGH_DISTANCE]),
                DISPLAY_DISPARITY_LONG: _percent(on_entry[COL_DISPARITY_LONG]),
                DISPLAY_DISPARITY_SHORT: _percent(on_entry[COL_DISPARITY_SHORT]),
                # **RSI 는 이미 0~100 지수값이다** — 100 을 다시 곱하지 않는다
                DISPLAY_RSI: round(float(on_entry[COL_RSI]), PERCENT_DECIMALS),
                DISPLAY_RETURN: _percent(whole.return_rate),
                DISPLAY_WORST_HOLD: _percent(whole.worst_hold_rate),
                DISPLAY_FIRST_QUARTER_RETURN: _percent(first_quarter.return_rate),
            }
        )


def _run_quarters(
    dataset: Dataset, frame: pd.DataFrame, entries: _Entries, accumulator: _Accumulator, *, position: str
) -> None:
    """보유 구간을 분기로 갈라 원자료와 집계를 쌓는다.

    **무손절 경로 하나뿐이다** (`설계.md` 결정 ⑮). 손절이 걸리면 보유가 중간에 끊겨 남은 분기의
    표본이 사라지고, 끊긴 분기는 「그 분기 성적」이 아니라 「손절까지의 성적」이 된다.

    **전체 보유 행을 여기서 함께 낸다.** 같은 체결에서 나와야 `가장 깊게` 가 성적표의
    `보유 중 최악(%)` 과 맞고, 세 분기의 검산이 그 값을 겨눌 수 있다.

    Args:
        dataset: 대상 종목
        frame: 가격 데이터
        entries: 그 위치의 진입 목록
        accumulator: 결과를 쌓는 자리
        position: 사이클 위치
    """
    whole_returns: list[float] = []
    whole_worst: list[float] = []
    by_label: dict[str, list[QuarterTrade]] = {label: [] for label in QUARTER_LABELS}

    for entry_position, exit_position, entry_year in zip(
        entries.entry_positions, entries.exit_positions, entries.entry_years, strict=True
    ):
        whole = simulate_scheduled_trade(
            frame,
            entry_position,
            exit_position,
            bet_down=BET_DOWN,
            stop_level=None,
            price_column=dataset.price_column,
        )
        whole_returns.append(whole.return_rate)
        whole_worst.append(whole.worst_hold_rate)

        for trade in quarter_trades(
            frame,
            entry_position=entry_position,
            exit_position=exit_position,
            bet_down=BET_DOWN,
            price_column=dataset.price_column,
        ):
            by_label[trade.label].append(trade)
            accumulator.quarter_trades.append(
                _quarter_detail_row(dataset, frame, position=position, entry_year=entry_year, trade=trade)
            )

    # **전체 보유가 첫 행이다** — 사용자가 먼저 보는 값이고, 분기 셋이 그것을 쪼갠 것이다.
    # 전체 행에서는 진입가가 곧 시작가라 두 낙폭 목록이 같다
    accumulator.quarter_summary.append(
        _quarter_summary_row(
            dataset,
            position=position,
            label=PERIOD_WHOLE,
            returns=whole_returns,
            worst_vs_entry=whole_worst,
            worst_vs_segment=whole_worst,
        )
    )
    for label in QUARTER_LABELS:
        trades = by_label[label]
        accumulator.quarter_summary.append(
            _quarter_summary_row(
                dataset,
                position=position,
                label=label,
                returns=[trade.return_rate for trade in trades],
                worst_vs_entry=[trade.worst_vs_entry for trade in trades],
                worst_vs_segment=[trade.worst_vs_start for trade in trades],
            )
        )


def run_midterm_cycle_trading(datasets: tuple[Dataset, ...] = DATASETS) -> TradingOutputs:
    """중간선거_사이클 체결 성적과 분기 분해를 낸다.

    **대상 × 중간선거해 × 손절선 격자**를 돌고, 그와 별도로 **무손절 경로에서 분기 표 둘 ·
    분할매수 표 둘 · 진입 위치 표**를 낸다. 방향은 「위」 하나다 (모듈 docstring).

    Args:
        datasets: 대상 목록

    Returns:
        체결 원자료와 성적표

    Raises:
        ValueError: 대상 목록이 비어 있거나, 어떤 대상의 진입이 하나도 없는 경우
    """
    if not datasets:
        raise ValueError("검증 대상이 하나도 없습니다")

    accumulator = _Accumulator()
    dataset_records: list[dict[str, Any]] = []
    target_records: list[dict[str, Any]] = []

    for dataset in datasets:
        frame = load_dataset(dataset)
        last_day = pd.Timestamp(frame[COL_DATE].iloc[-1])
        levels = STOP_LEVELS_INDEX if dataset.is_index else STOP_LEVELS_ETF

        by_position, excluded_count = _collect_entries(dataset, frame)

        # **대상마다 한 번만 계산한다** — 진입 위치 표와 분할매수 C 가 같은 값을 봐야 한다
        indicators = indicator_frame(frame, price_column=dataset.price_column)
        trading_days = pd.DatetimeIndex(frame[COL_DATE])

        # **체결 «전»에 본다.** 가드를 뒤에 두면 빈 칸의 시기 5행이 이미 쌓인 뒤다
        empty_positions = sorted(position for position in CYCLE_POSITIONS if not by_position[position].entry_positions)
        if empty_positions:
            raise ValueError(f"{dataset.label}: 진입이 하나도 없는 사이클 위치가 있습니다 ({empty_positions})")

        # **측정과 같은 것을 센다** — 측정은 「유효 + 제외」를 진입으로 세고 제외를 따로 낸다
        entry_count = sum(len(entries.entry_positions) for entries in by_position.values()) + excluded_count

        for position in CYCLE_POSITIONS:
            for stop_level in levels:
                _run_cell(
                    dataset,
                    frame,
                    by_position[position],
                    accumulator,
                    position=position,
                    bet_down=BET_DOWN,
                    stop_level=stop_level,
                    last_day=last_day,
                )

            # **손절선 루프 «밖»이다** — 분기 분해는 무손절 경로 하나뿐이다 (설계 결정 ⑮).
            # 안에 두면 같은 표가 손절선 수만큼 중복으로 쌓인다
            _run_quarters(dataset, frame, by_position[position], accumulator, position=position)

            # **분할매수와 진입 위치도 무손절 경로라 손절선 루프 밖이다**
            entries = by_position[position]
            windows = entry_windows(trading_days, entries.entry_positions, entries.exit_positions)
            _run_split(dataset, frame, entries, windows, indicators, accumulator, position=position)
            _run_entry_context(dataset, frame, entries, indicators, accumulator, position=position)

        # **`ticker` 는 반드시 `dataset.ticker` 에서 온다** — 둘 다 `str` 이라 다른 필드를
        # 넘겨도 키 이름은 그대로고 값만 조용히 뒤바뀐다 (계층 계약 검사가 출처를 본다)
        dataset_records.append(
            dataset_record(ticker=dataset.ticker, label=dataset.label, file=dataset.path.name, frame=frame)
        )
        # **제외 건수를 대상마다 남긴다** (패키지 절대 원칙 「표본 보존」)
        target_records.append(
            {KEY_LABEL: dataset.label, KEY_ENTRY_COUNT: entry_count, KEY_EXCLUDED_COUNT: excluded_count}
        )

    trades = pd.DataFrame(accumulator.trades)
    performance = to_summary_frame(accumulator.performance)
    quarter_detail = pd.DataFrame(accumulator.quarter_trades)
    quarter_summary = pd.DataFrame(accumulator.quarter_summary)
    split_trades = pd.DataFrame(accumulator.split_trades)
    split_summary = pd.DataFrame(accumulator.split_summary)
    entry_context = pd.DataFrame(accumulator.entry_context)

    # **성적표에 실제로 나온 값을 적는다.** 격자를 그대로 적으면 지수만 고른 실행에서
    # 돌지도 않은 손절선을 적게 된다
    stop_levels_run = list(dict.fromkeys(performance[DISPLAY_STOP_LEVEL]))

    notes = [NOTE_ENTRY, NOTE_AXIS, NOTE_QUARTER, NOTE_SPLIT, NOTE_ENTRY_CONTEXT, NOTE_STOP_BASE, NOTE_SAMPLE]
    if any(not dataset.is_index for dataset in datasets):
        notes.append(NOTE_DIVIDEND)
    if any(dataset.is_index for dataset in datasets):
        notes.append(NOTE_INDEX)

    summary = build_run_summary(
        track=TRACK_NAME,
        datasets=dataset_records,
        rule={
            KEY_ENTRY_MONTH: ENTRY_MONTH,
            KEY_EXIT_MONTH: EXIT_MONTH,
            KEY_DIRECTION: DIRECTION_DOWN if BET_DOWN else DIRECTION_UP,
            KEY_STOP_LEVELS: stop_levels_run,
            KEY_TARGETS: target_records,
            KEY_SPLIT_METHODS: [
                {KEY_LABEL: method.label, KEY_FALLBACKS: list(method.fallbacks)} for method in SPLIT_METHODS
            ],
        },
        row_counts={
            TRADES_FILENAME: len(trades),
            SUMMARY_FILENAME: len(performance),
            QUARTER_TRADES_FILENAME: len(quarter_detail),
            QUARTER_SUMMARY_FILENAME: len(quarter_summary),
            SPLIT_TRADES_FILENAME: len(split_trades),
            SPLIT_SUMMARY_FILENAME: len(split_summary),
            ENTRY_CONTEXT_FILENAME: len(entry_context),
        },
        notes=notes,
    )

    logger.debug(
        f"체결 완료: 거래내역 {len(trades):,}행, 성적표 {len(performance):,}행, "
        f"분기내역 {len(quarter_detail):,}행, 분기 {len(quarter_summary):,}행"
    )

    return TradingOutputs(
        trades=trades,
        performance=performance,
        quarter_trades=quarter_detail,
        quarter_summary=quarter_summary,
        split_trades=split_trades,
        split_summary=split_summary,
        entry_context=entry_context,
        summary=summary,
    )


__all__ = ["TradingOutputs", "run_midterm_cycle_trading"]
