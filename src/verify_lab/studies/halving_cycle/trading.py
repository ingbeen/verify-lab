"""반감기_사이클 체결 조립 — 진입 시점 × 청산 시점 격자를 손절선 격자 전부로 체결해 성적표와 거래내역을 낸다

**계산하지 않는다.** 판정식과 성적 산식이 이미 있으므로 그것들을 조합해 돌리고, 어느 행이 어떤 칸의
결과인지를 붙여 쌓는다.

| 빌려 쓰는 것 | 어디서 |
| --- | --- |
| 진입일 · 청산일 | `studies/halving_cycle/halving_calendar.position_schedule` — 1단계 측정과 같은 반감기 날짜 · 같은 달력월 규칙 |
| 시세와 종가 대체 | `studies/halving_cycle/runner.load_dataset` — 측정과 **같은 가격에** 들어간다 |
| 체결 (무손절 · 손절선) | `execution/trade_fill.simulate_scheduled_trade` |
| 거래내역의 공통 칸 | `execution/trade_rows.trade_columns` |
| 구간별 성적 산식과 1차 판정 | `execution/periods.period_rows` |
| 하드포크 몫 | `studies/halving_cycle/hard_fork.hard_fork_share` — 달력 분할 손절 표와 같은 산식 |

**칸과 손절선을 고르지 않는다** (`docs/검증/반감기_사이클/설계.md` 결정 ㉞ · ㉟) — 격자 전부를 내고, 고르는 것은
사용자가 `규칙.md` 에서 한다.

**방향은 「위」 하나다.** 두 방향을 내면 같은 칸이 위·아래 둘 다 후보가 될 수 있다(`docs/매매/중간선거_사이클/설계.md`
결정 ⑨ 의 실측). 아래로 거는 칸의 크기와 빈도는 측정 표의 내린 비율이 준다.

**하드포크 몫은 수익률에 더하지 않는다** (결정 ㊲) — 원본가에 없는 몫이라 거래내역 끝 칸에 따로 싣는다.

**비용을 넣지 않는다.** 수수료·슬리피지·세금은 사용자가 별도로 요청할 때만 넣는다 (루트 `CLAUDE.md` 2026-09-06 확정).
"""

from dataclasses import dataclass, field
from typing import Any, Final

import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE, RATE_TO_PERCENT
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
from verify_lab.report.constants import DATE_FORMAT, PERCENT_DECIMALS
from verify_lab.report.run_summary import dataset_record
from verify_lab.studies.halving_cycle.constants import (
    BET_DOWN,
    COL_ENTRY_MONTHS,
    COL_EXIT_MONTHS,
    COL_HALVING,
    DATASETS,
    DISPLAY_ENTRY_MONTHS,
    DISPLAY_EXIT_MONTHS,
    DISPLAY_FORK_SHARE,
    DISPLAY_HALVING,
    ENTRY_MONTHS,
    EXIT_MONTHS,
    GRID_BASELINE_FILENAME,
    HALVINGS,
    HARD_FORKS,
    KEY_BLOCK_TIME,
    KEY_DATE,
    KEY_ENTRY_MONTHS,
    KEY_EXCLUDED_COUNT,
    KEY_HALVINGS,
    KEY_HEIGHT,
    KEY_LABEL,
    KEY_NAME,
    KEY_SIGNAL_COUNT,
    STOP_LEVELS,
    TRACK_NAME,
    Dataset,
)
from verify_lab.studies.halving_cycle.halving_calendar import position_schedule
from verify_lab.studies.halving_cycle.hard_fork import hard_fork_share
from verify_lab.studies.halving_cycle.runner import halving_records, load_dataset
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# `summary.json` 의 `rule` 안 — 무엇을 어떤 규칙으로 돌렸나.
# **최상위 키와 비용 표기는 `execution/run_summary.py` 가 소유한다**
KEY_EXIT_MONTHS = "exit_months"
KEY_STOP_LEVELS = "stop_levels"
KEY_TARGETS = "targets"
KEY_DIRECTION = "direction"
KEY_HARD_FORKS = "hard_forks"
KEY_PRICE_DATE = "price_date"
KEY_COIN_PRICE = "coin_price_usd"
KEY_BTC_PRICE = "btc_price_usd"
KEY_RATIO = "ratio"

# 대상 기록 — **몇 건이 왜 빠졌는지** (절대 원칙 4 · 결정 ㊴). 제외는 행이 있고, 나머지 둘은 행이 없다
KEY_EXCLUDED_BY_REASON = "excluded_by_reason"
KEY_OUTSIDE_CYCLE_COUNT = "outside_cycle_count"
KEY_NOT_YET_COUNT = "not_yet_count"

# 요약에 싣는 비율(0 ~ 1)의 자릿수 — 전역 반올림 규칙표의 「비율」이다
RATIO_DECIMALS: Final = 4

# 산출물만 보고는 알 수 없는 실행 조건. **격자 값을 글자로 박지 않는다** — 값은 `rule` 의 목록이 말한다
NOTE_ENTRY = (
    "진입은 반감기일 + 진입 개월(달력월) 날의 종가다. 청산은 청산 개월이 진입 개월보다 크면 같은 반감기일 + 청산 개월, "
    "같거나 작으면 다음 반감기일 + 청산 개월 날의 종가다 — 보유는 최대 한 사이클이다. 없는 날짜는 그 달 말일로 당긴다. "
    "진입일이 다음 반감기 뒤인 시점은 그 사이클에 없고, 청산 시점 전에 반감기가 한 번 더 오면 그 행은 제외된다. "
    "반감기일은 블록 헤더 시각의 UTC 날짜다(2024 는 04-20)"
)
# **하한을 리터럴로 적지 않는다** — 값의 소유자는 `measure/constants.MIN_SAMPLE_PER_CELL` 하나다
NOTE_SAMPLE = (
    f"칸마다 표본이 많아야 반감기 사이클 수라 칸당 표본 하한({MIN_SAMPLE_PER_CELL})에 못 미친다 — 「판정가능」이 전 구간에서 "
    "「아니오」다. 다음 반감기 뒤에 파는 칸은 그 반감기가 지나야 표본이 생겨 더 적다. 결론의 일부이지 버그가 아니다"
)
NOTE_INDEPENDENCE = "칸은 같은 반감기 사이클들을 진입 · 청산 시점으로 나눈 것이라 칸끼리 독립이 아니다 — 「후보」 칸의 수를 독립된 발견의 수로 읽지 않는다. 후보는 자격이지 발견이 아니다"
NOTE_HOLD_LENGTH = "다음 반감기 뒤에 파는 칸은 사이클 길이가 달라 같은 칸이라도 사이클마다 보유 길이가 몇 달씩 다르다 — 반감기에 묶어 파는 규칙이라 그 차이를 받아들인다"
NOTE_STOP = (
    "손절선은 무손절과 진입가 대비 가격 손절선 격자 전부다 — 진입가 기준으로 고정하고, 장중 저가가 닿으면 손절가에, "
    "시가가 이미 아래면 그 시가에 판다. 값을 고르지 않는다 — 고르는 것은 규칙 문서에서 한다"
)
NOTE_SCREEN = (
    "보유가 몇 달에서 한 사이클이라 평균이 양수인 칸은 거의 모두 1차 판정을 넘는다 — 게이트는 하나이고 이 격자에 맞춰 "
    "바꾸지 않는다. 성적표에는 기준선을 두지 않는다 — 같은 사이클에 파는 칸의 기준선은 측정 표"
    f"({GRID_BASELINE_FILENAME})에 있고, 다음 사이클에 파는 칸은 사이클마다 보유 길이가 달라 같은 보유의 기준선이 "
    "정의되지 않는다"
)
NOTE_DIRECTION = "방향은 「위」 하나다. 아래로 거는 칸의 크기와 빈도는 측정 표(통계)의 내린 비율과 평균이 준다"
NOTE_REPLACED = "Bitstamp 에서 거래량이 0 인 날의 종가는 Coin Metrics 기준가로 바꿔 쟀다(시가·고가·저가는 받은 그대로). " "바꾼 날은 측정 산출물의 대체일 표에 있다"
NOTE_FORK = (
    f"하드포크로 나눠 받은 코인({' · '.join(fork.name for fork in HARD_FORKS)})의 몫은 원본가에 없어 수익률 · 성적표 · "
    "1차 판정에 넣지 않는다 — 거래내역 끝 칸이 따로 잰다. 포크 코인을 첫 시세일 종가에 팔아 BTC 를 더 샀다고 보고, "
    "진입일 < 포크일 ≤ 청산일인 체결에 (Π(1 + 비율) − 1) × (1 + 체결 수익률) 이다"
)
NOTES = (
    NOTE_ENTRY,
    NOTE_SAMPLE,
    NOTE_INDEPENDENCE,
    NOTE_HOLD_LENGTH,
    NOTE_STOP,
    NOTE_SCREEN,
    NOTE_DIRECTION,
    NOTE_REPLACED,
    NOTE_FORK,
)


@dataclass(frozen=True)
class TradingOutputs:
    """체결 산출물

    Attributes:
        trades: 체결 원자료. 진입·청산 날짜와 실제 체결가 · 하드포크 몫이 들어 있다 (측정의 원칙 8)
        performance: 종목 × 진입 개월 × 청산 개월 × 손절선 × 시기의 성적표. **방향은 「위」 하나다**
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


def _hard_fork_records() -> list[dict[str, Any]]:
    """실행 요약에 싣는 하드포크 — 몫을 다시 계산할 수 있는 값 전부.

    Returns:
        하드포크마다 한 줄
    """
    return [
        {
            KEY_NAME: fork.name,
            KEY_HEIGHT: fork.height,
            KEY_BLOCK_TIME: fork.block_time.isoformat(),
            KEY_DATE: fork.day.strftime(DATE_FORMAT),
            KEY_PRICE_DATE: fork.price_day.strftime(DATE_FORMAT),
            KEY_COIN_PRICE: fork.coin_price,
            KEY_BTC_PRICE: fork.btc_price,
            KEY_RATIO: round(fork.ratio, RATIO_DECIMALS),
        }
        for fork in HARD_FORKS
    ]


def _run_cell(
    dataset: Dataset,
    frame: pd.DataFrame,
    trading_days: pd.DatetimeIndex,
    rows: pd.DataFrame,
    accumulator: _Accumulator,
    *,
    entry_months: int,
    exit_months: int,
    stop_level: float | None,
) -> None:
    """한 칸(진입 개월 × 청산 개월 × 손절선)을 돌려 체결과 성적을 쌓는다.

    **체결이 하나도 없는 칸도 시기 다섯 행을 낸다** — 행이 사라지면 그 칸을 못 봤다는 사실 자체를 모른다
    (측정의 원칙 17). 그 행의 지표는 비고 1차 판정은 「판정 안 함」이다.

    Args:
        dataset: 대상
        frame: 측정이 쓰는 시세 (종가 대체 뒤)
        trading_days: 그 시세의 거래일 목록. 마지막 날이 「최근 N년」의 기준점이다
        rows: 그 칸의 유효 일정 (진입일 오름차순)
        accumulator: 결과를 쌓는 자리
        entry_months: 반감기 뒤 진입 개월
        exit_months: 반감기 뒤 청산 개월
        stop_level: 손절선. `None` 이면 무손절
    """
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
        DISPLAY_EXIT_MONTHS: exit_months,
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
        # **실제로 나간 날로 잰다** — 손절로 나간 체결은 예정 청산일 전에 끝나 그 뒤의 포크를 받지 못한다
        fork_share = hard_fork_share(
            trading_days[entry_position],
            trading_days[entry_position + result.hold_days],
            result.return_rate,
            HARD_FORKS,
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
                DISPLAY_FORK_SHARE: round(fork_share * RATE_TO_PERCENT, PERCENT_DECIMALS),
            }
        )
        returns.append(result.return_rate)
        hold_days.append(result.hold_days)
        reasons.append(result.reason)
        worst_hold_rates.append(result.worst_hold_rate)

    for row in period_rows(
        entry_dates,
        returns,
        last_day=trading_days[-1],
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
    """반감기_사이클의 체결 성적을 낸다 — 대상 × 진입 개월 × 청산 개월 × 손절선 격자 전부.

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
        # **대상마다 한 번 만든다** — 칸 × 손절선마다 다시 만들 이유가 없다
        trading_days = pd.DatetimeIndex(frame[COL_DATE])

        schedule = position_schedule(trading_days, HALVINGS, ENTRY_MONTHS, EXIT_MONTHS)
        reasons = schedule.schedule[COL_EXCLUDED_REASON]
        valid = schedule.schedule[reasons == REASON_NONE].sort_values(COL_DATE, kind="stable")

        for entry_months in ENTRY_MONTHS:
            for exit_months in EXIT_MONTHS:
                rows = valid[(valid[COL_ENTRY_MONTHS] == entry_months) & (valid[COL_EXIT_MONTHS] == exit_months)]
                for stop_level in STOP_LEVELS:
                    _run_cell(
                        dataset,
                        frame,
                        trading_days,
                        rows,
                        accumulator,
                        entry_months=entry_months,
                        exit_months=exit_months,
                        stop_level=stop_level,
                    )

        # **`ticker` 는 반드시 `dataset.ticker` 에서 온다** — 둘 다 `str` 이라 다른 필드를 넘겨도 키 이름은
        # 그대로고 값만 조용히 뒤바뀐다 (계층 계약 검사가 출처를 본다)
        dataset_records.append(
            dataset_record(ticker=dataset.ticker, label=dataset.label, file=dataset.path.name, frame=frame)
        )
        # **몇 건이 왜 빠졌는지를 대상마다 남긴다** (패키지 절대 원칙 「표본 보존」) — 성적표에는 제외 컬럼이 없다
        excluded = reasons[reasons != REASON_NONE]
        target_records.append(
            {
                KEY_LABEL: dataset.label,
                KEY_SIGNAL_COUNT: len(schedule.schedule),
                KEY_EXCLUDED_COUNT: len(excluded),
                KEY_EXCLUDED_BY_REASON: {str(reason): int(count) for reason, count in excluded.value_counts().items()},
                KEY_OUTSIDE_CYCLE_COUNT: schedule.outside_cycle_count,
                KEY_NOT_YET_COUNT: schedule.not_yet_count,
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
            KEY_EXIT_MONTHS: list(EXIT_MONTHS),
            KEY_DIRECTION: DIRECTION_DOWN if BET_DOWN else DIRECTION_UP,
            KEY_STOP_LEVELS: stop_levels_run,
            KEY_HARD_FORKS: _hard_fork_records(),
            KEY_TARGETS: target_records,
        },
        row_counts={TRADES_FILENAME: len(trades), SUMMARY_FILENAME: len(performance)},
        notes=NOTES,
    )

    logger.debug(f"체결 완료: 거래내역 {len(trades):,}행, 성적표 {len(performance):,}행")

    return TradingOutputs(trades=trades, performance=performance, summary=summary)


__all__ = [
    "KEY_EXCLUDED_BY_REASON",
    "KEY_NOT_YET_COUNT",
    "KEY_OUTSIDE_CYCLE_COUNT",
    "KEY_TARGETS",
    "TradingOutputs",
    "run_halving_cycle_trading",
]
