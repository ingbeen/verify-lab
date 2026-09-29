"""반감기_사이클 체결 조립 — 48칸을 무손절 · 「위」 한 방향으로 체결해 성적표와 거래내역을 낸다

**계산하지 않는다.** 판정식과 성적 산식이 이미 있으므로 그것들을 조합해 돌리고, 어느 행이 어떤 칸의
결과인지를 붙여 쌓기만 한다.

| 빌려 쓰는 것 | 어디서 |
| --- | --- |
| 진입일·청산일 정의와 종가 대체 | `studies/halving_cycle/runner` — 측정과 **같은 날, 같은 가격에** 들어간다 |
| 체결 (무손절 — 청산일 종가, 보유 중 최악은 장중 저가) | `execution/trade_fill.simulate_scheduled_trade` |
| 거래내역의 공통 칸 | `execution/trade_rows.trade_columns` |
| 구간별 성적 산식과 1차 판정 | `execution/periods.period_rows` |

**손절을 걸지 않는다** (`docs/검증/반감기_사이클/설계.md` 결정 ⑦). 손절은 사용자가 따로 정하고, 이 성적표는
맨몸 측정이다 — 「후보」는 규칙이 아니라 판단 재료다.

**방향은 「위」 하나다.** 두 방향을 내면 측정 표와의 1:1 조인이 깨지고 같은 칸이 위·아래 둘 다 후보가 될 수
있다(`docs/매매/중간선거_사이클/설계.md` 결정 ⑨ 의 실측). 아래로 거는 칸의 크기와 빈도는 측정 표의 내린 비율이 준다.

**비용을 넣지 않는다.** 수수료·슬리피지·세금은 사용자가 별도로 요청할 때만 넣는다 (루트 `CLAUDE.md` 2026-09-06 확정).
"""

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE
from verify_lab.execution.constants import (
    DISPLAY_DIRECTION,
    DISPLAY_STOP_LEVEL,
    DISPLAY_TICKER,
    SUMMARY_FILENAME,
    TRADES_FILENAME,
    stop_level_value,
)
from verify_lab.execution.periods import period_rows, to_summary_frame
from verify_lab.execution.run_summary import build_run_summary
from verify_lab.execution.trade_fill import resolve_positions, simulate_scheduled_trade
from verify_lab.execution.trade_rows import trade_columns
from verify_lab.measure.constants import COL_EXCLUDED_REASON, COL_EXIT_DATE, MIN_SAMPLE_PER_CELL, REASON_NONE
from verify_lab.measure.screening import DIRECTION_DOWN, DIRECTION_UP
from verify_lab.report.run_summary import dataset_record
from verify_lab.studies.halving_cycle.constants import (
    BET_DOWN,
    COL_ENTRY_MONTHS,
    COL_HALVING,
    COL_HOLD_MONTHS,
    DATASETS,
    DISPLAY_ENTRY_MONTHS,
    DISPLAY_HALVING,
    DISPLAY_HOLD_MONTHS,
    ENTRY_MONTHS,
    HOLD_MONTHS,
    KEY_ENTRY_MONTHS,
    KEY_EXCLUDED_COUNT,
    KEY_HALVINGS,
    KEY_HOLD_MONTHS,
    KEY_LABEL,
    KEY_SIGNAL_COUNT,
    STOP_LEVELS,
    TRACK_NAME,
    Dataset,
)
from verify_lab.studies.halving_cycle.runner import halving_records, load_dataset, signal_returns
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# `summary.json` 의 `rule` 안 — 무엇을 어떤 규칙으로 돌렸나.
# **최상위 키와 비용 표기는 `execution/run_summary.py` 가 소유한다**
KEY_STOP_LEVELS = "stop_levels"
KEY_TARGETS = "targets"
KEY_DIRECTION = "direction"

# 산출물만 보고는 알 수 없는 실행 조건
NOTE_ENTRY = (
    "진입은 반감기일 + 진입 개월(달력월) 날의 종가, 청산은 진입일 + 보유 개월 날의 종가다 — 없는 날짜는 그 달 말일로 "
    "당긴다. 반감기일은 블록 헤더 시각의 UTC 날짜다(2024 는 04-20). 측정과 같은 날, 같은 가격에 들어간다"
)
# **하한을 리터럴로 적지 않는다** — 값의 소유자는 `measure/constants.MIN_SAMPLE_PER_CELL` 하나다
NOTE_SAMPLE = (
    f"칸마다 표본이 반감기 사이클 수(3~4건)라 칸당 표본 하한({MIN_SAMPLE_PER_CELL})에 못 미친다 — "
    "「판정가능」이 전 구간에서 「아니오」이고 우연확률도 붙지 않는다. 결론의 일부이지 버그가 아니다"
)
NOTE_INDEPENDENCE = "48칸은 같은 사이클 3~4개를 진입·보유로 나눈 것이라 칸끼리 독립이 아니다 — 「후보」 칸의 수를 " "독립된 발견의 수로 읽지 않는다. 후보는 자격이지 발견이 아니다"
NOTE_STOP = "손절선을 걸지 않은 무손절 한 종이다 — 손절은 사용자가 따로 정한다. 성적과 1차 판정은 맨몸 무손절 기준이다"
NOTE_DIRECTION = "방향은 「위」 하나다. 아래로 거는 칸의 크기와 빈도는 측정 표(통계)의 내린 비율과 평균이 준다"
NOTE_REPLACED = "Bitstamp 에서 거래량이 0 인 날의 종가는 Coin Metrics 기준가로 바꿔 쟀다(시가·고가·저가는 받은 그대로). " "바꾼 날은 측정 산출물의 대체일 표에 있다"
NOTE_FORK = "하드포크로 나눠 받은 코인(2017-08-01 BCH 등)의 몫은 원본가에 없다 — 그 날을 보유 구간에 품은 「위」 체결은 " "그만큼 과소평가돼 있다"
NOTES = (NOTE_ENTRY, NOTE_SAMPLE, NOTE_INDEPENDENCE, NOTE_STOP, NOTE_DIRECTION, NOTE_REPLACED, NOTE_FORK)


@dataclass(frozen=True)
class TradingOutputs:
    """체결 산출물

    Attributes:
        trades: 체결 원자료. 진입·청산 날짜와 실제 체결가가 들어 있다 (측정의 원칙 8)
        performance: 종목 × 진입 개월 × 보유 개월 × 손절선 × 시기의 성적표. **방향은 「위」 하나다**
        summary: 실행 요약
    """

    trades: pd.DataFrame
    performance: pd.DataFrame
    summary: dict[str, Any]


@dataclass
class _Accumulator:
    """표 조각을 쌓는 자리"""

    trades: list[dict[str, Any]] = field(default_factory=list)
    performance: list[dict[str, Any]] = field(default_factory=list)


def _run_cell(
    dataset: Dataset,
    frame: pd.DataFrame,
    rows: pd.DataFrame,
    accumulator: _Accumulator,
    *,
    entry_months: int,
    hold_months: int,
    stop_level: float | None,
    last_day: pd.Timestamp,
) -> None:
    """한 칸(진입 개월 × 보유 개월 × 손절선)을 돌려 체결과 성적을 쌓는다.

    **체결이 하나도 없는 칸도 시기 다섯 행을 낸다** — 행이 사라지면 그 칸을 못 봤다는 사실 자체를 모른다
    (측정의 원칙 17). 그 행의 지표는 비고 1차 판정은 「판정 안 함」이다.

    Args:
        dataset: 대상
        frame: 측정이 쓰는 시세 (종가 대체 뒤)
        rows: 그 칸의 유효 진입 (진입일 오름차순)
        accumulator: 결과를 쌓는 자리
        entry_months: 반감기 뒤 진입 개월
        hold_months: 보유 개월
        stop_level: 손절선. `None` 이면 무손절
        last_day: 시세의 마지막 거래일. 「최근 N년」의 기준점이다
    """
    trading_days = pd.DatetimeIndex(frame[COL_DATE])
    entry_dates = pd.DatetimeIndex(rows[COL_DATE])
    entry_positions = resolve_positions(trading_days, entry_dates, label="진입일")
    exit_positions = resolve_positions(trading_days, pd.DatetimeIndex(rows[COL_EXIT_DATE]), label="청산일")

    # **표기를 한 번만 만든다** — 두 표가 같은 칸에 다른 값을 실으면 조인이 안 된다.
    # Bitstamp 시세는 고가·저가가 있어 장중 손절을 잴 수 있다 (로더가 네 가격을 검증한다)
    stop_display = stop_level_value(stop_level, measurable=True)
    direction = DIRECTION_DOWN if BET_DOWN else DIRECTION_UP
    identity = {
        DISPLAY_TICKER: dataset.label,
        DISPLAY_ENTRY_MONTHS: entry_months,
        DISPLAY_HOLD_MONTHS: hold_months,
    }

    returns: list[float] = []
    hold_days: list[int] = []
    reasons: list[str] = []
    worst_hold_rates: list[float] = []
    for entry_position, exit_position, halving in zip(
        entry_positions.tolist(), exit_positions.tolist(), rows[COL_HALVING], strict=True
    ):
        result = simulate_scheduled_trade(
            frame,
            entry_position,
            exit_position,
            bet_down=BET_DOWN,
            stop_level=stop_level,
            price_column=COL_CLOSE,
        )
        accumulator.trades.append(
            {
                **identity,
                DISPLAY_HALVING: halving,
                DISPLAY_DIRECTION: direction,
                DISPLAY_STOP_LEVEL: stop_display,
                **trade_columns(
                    frame,
                    entry_position,
                    result,
                    bet_down=BET_DOWN,
                    price_column=COL_CLOSE,
                    price_decimals=dataset.price_decimals,
                ),
            }
        )
        returns.append(result.return_rate)
        hold_days.append(result.hold_days)
        reasons.append(result.reason)
        worst_hold_rates.append(result.worst_hold_rate)

    for row in period_rows(
        entry_dates,
        returns,
        last_day=last_day,
        # **판정은 살 수 있는 것에만 건다** (측정의 원칙 9)
        tradable=dataset.is_judged,
        hold_days=hold_days,
        reasons=reasons,
        worst_hold_rates=worst_hold_rates,
    ):
        accumulator.performance.append(
            {**identity, DISPLAY_DIRECTION: direction, DISPLAY_STOP_LEVEL: stop_display, **row}
        )


def run_halving_cycle_trading(datasets: tuple[Dataset, ...] = DATASETS) -> TradingOutputs:
    """반감기_사이클의 체결 성적을 낸다 — 대상 × 48칸 × 무손절.

    Args:
        datasets: 대상 목록

    Returns:
        체결 원자료와 성적표

    Raises:
        ValueError: 대상 목록이 비어 있는 경우
    """
    if not datasets:
        raise ValueError("검증 대상이 하나도 없습니다")

    accumulator = _Accumulator()
    dataset_records: list[dict[str, Any]] = []
    target_records: list[dict[str, Any]] = []

    for dataset in datasets:
        frame = load_dataset(dataset).frame
        last_day = pd.Timestamp(frame[COL_DATE].iloc[-1])

        signal = signal_returns(frame)
        valid = signal[signal[COL_EXCLUDED_REASON] == REASON_NONE].sort_values(COL_DATE, kind="stable")

        for entry_months in ENTRY_MONTHS:
            for hold_months in HOLD_MONTHS:
                rows = valid[(valid[COL_ENTRY_MONTHS] == entry_months) & (valid[COL_HOLD_MONTHS] == hold_months)]
                for stop_level in STOP_LEVELS:
                    _run_cell(
                        dataset,
                        frame,
                        rows,
                        accumulator,
                        entry_months=entry_months,
                        hold_months=hold_months,
                        stop_level=stop_level,
                        last_day=last_day,
                    )

        # **`ticker` 는 반드시 `dataset.ticker` 에서 온다** — 둘 다 `str` 이라 다른 필드를 넘겨도 키 이름은
        # 그대로고 값만 조용히 뒤바뀐다 (계층 계약 검사가 출처를 본다)
        dataset_records.append(
            dataset_record(ticker=dataset.ticker, label=dataset.label, file=dataset.path.name, frame=frame)
        )
        # **제외 건수를 대상마다 남긴다** (패키지 절대 원칙 「표본 보존」) — 성적표에는 제외 컬럼이 없다
        target_records.append(
            {
                KEY_LABEL: dataset.label,
                KEY_SIGNAL_COUNT: len(signal),
                KEY_EXCLUDED_COUNT: len(signal) - len(valid),
            }
        )

    trades = pd.DataFrame(accumulator.trades)
    performance = to_summary_frame(accumulator.performance)

    # **성적표에 실제로 나온 값을 적는다** — 목록을 그대로 적으면 돌지도 않은 손절선을 적게 된다
    stop_levels_run = list(dict.fromkeys(performance[DISPLAY_STOP_LEVEL]))

    summary = build_run_summary(
        track=TRACK_NAME,
        datasets=dataset_records,
        rule={
            KEY_HALVINGS: halving_records(),
            KEY_ENTRY_MONTHS: list(ENTRY_MONTHS),
            KEY_HOLD_MONTHS: list(HOLD_MONTHS),
            KEY_DIRECTION: DIRECTION_DOWN if BET_DOWN else DIRECTION_UP,
            KEY_STOP_LEVELS: stop_levels_run,
            KEY_TARGETS: target_records,
        },
        row_counts={TRADES_FILENAME: len(trades), SUMMARY_FILENAME: len(performance)},
        notes=NOTES,
    )

    logger.debug(f"체결 완료: 거래내역 {len(trades):,}행, 성적표 {len(performance):,}행")

    return TradingOutputs(trades=trades, performance=performance, summary=summary)


__all__ = ["KEY_TARGETS", "TradingOutputs", "run_halving_cycle_trading"]
