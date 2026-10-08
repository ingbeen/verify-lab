"""반감기_사이클 체결 조립 — 일시 격자(진입 시점 × 청산 시점)와 확정 규칙(달력 매달 분할 + 저점 이탈)의 성적표와 거래내역을 낸다

**계산하지 않는다.** 판정식과 성적 산식이 이미 있으므로 그것들을 조합해 돌리고, 어느 행이 어떤 칸의
결과인지를 붙여 쌓는다.

| 빌려 쓰는 것 | 어디서 |
| --- | --- |
| 진입일 · 청산일 | `studies/halving_cycle/halving_calendar.position_schedule` — 1단계 측정과 같은 반감기 날짜 · 같은 달력월 규칙 |
| 시세와 종가 대체 | `studies/halving_cycle/runner.load_dataset` — 측정과 **같은 가격에** 들어간다 |
| 일시 격자 체결 (무손절) | `execution/trade_fill.simulate_scheduled_trade` |
| 확정 규칙의 포지션 성적 | `studies/halving_cycle/split_rule.calendar_split_grid` — 측정의 손절 표를 만든 바로 그 성적 |
| 거래내역의 공통 칸 | `execution/trade_rows.trade_columns` · `trade_columns_from` |
| 구간별 성적 산식과 1차 판정 | `execution/periods.period_rows` |
| 하드포크 몫 | `studies/halving_cycle/hard_fork.hard_fork_share` — 확정 규칙은 손절 표의 몫 그대로 |

**일시 격자의 칸을 고르지 않는다** (`docs/검증/반감기_사이클/설계.md` 결정 ㉞) — 격자 전부를 비교용으로 낸다.
**진입가 % 손절선을 두지 않는다** (결정 60) — 일시 격자는 무손절 한 종이다.

**확정 규칙은 끝난 포지션 하나가 체결 한 건이다** (결정 61) — 진입가는 평균 매수가, 청산가는 평균 매도가, 보유 중 최악은
평균 단가 대비 최악이고, 손절선은 무손절 · 저점 이탈 두 줄이다. 개월 칸은 첫 회차라 일시 격자의 칸과 겹칠 수 있어
`매매 방식` 칸이 둘을 가른다.

**방향은 「위」 하나다.** 두 방향을 내면 같은 칸이 위·아래 둘 다 후보가 될 수 있다(`docs/매매/중간선거_사이클/설계.md`
결정 ⑨ 의 실측). 아래로 거는 칸의 크기와 빈도는 측정 표의 내린 비율이 준다.

**하드포크 몫은 수익률에 더하지 않는다** (결정 ㊲) — BTC 시세에 없고 지급이 보장되지 않는 몫이라 거래내역 끝 칸에 따로 싣는다.

**비용을 넣지 않는다.** 수수료·슬리피지·세금은 사용자가 별도로 요청할 때만 넣는다 (루트 `CLAUDE.md` 2026-09-06 확정).
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Final, TypeVar

import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE, RATE_TO_PERCENT
from verify_lab.execution.constants import (
    DISPLAY_DIRECTION,
    DISPLAY_STOP_LEVEL,
    DISPLAY_TICKER,
    EXIT_LIMIT,
    NO_STOP_LABEL,
    SUMMARY_FILENAME,
    TRADES_FILENAME,
    named_stop_value,
    stop_level_value,
)
from verify_lab.execution.periods import period_rows, to_summary_frame
from verify_lab.execution.run_summary import build_run_summary
from verify_lab.execution.trade_fill import TradeResult, resolve_positions, simulate_scheduled_trade
from verify_lab.execution.trade_rows import trade_columns, trade_columns_from
from verify_lab.measure.constants import COL_EXCLUDED_REASON, COL_EXIT_DATE, MIN_SAMPLE_PER_CELL, REASON_NONE
from verify_lab.measure.screening import DIRECTION_DOWN, DIRECTION_UP
from verify_lab.report.constants import DATE_FORMAT, PERCENT_DECIMALS
from verify_lab.report.run_summary import dataset_record
from verify_lab.studies.halving_cycle.constants import (
    BET_DOWN,
    CALENDAR_SPLIT_STEP_MONTHS,
    CALENDAR_SPLITS,
    COL_ENTRY_MONTHS,
    COL_EXIT_MONTHS,
    COL_HALVING,
    DATASETS,
    DISPLAY_ENTRY_MONTHS,
    DISPLAY_EXIT_MONTHS,
    DISPLAY_FORK_SHARE,
    DISPLAY_HALVING,
    DISPLAY_TRADE_METHOD,
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
    PEAK_WINDOW_MONTHS,
    STOP_METHOD_LOW_BREAK,
    TRACK_NAME,
    TRADE_METHOD_LUMP,
    CalendarSplit,
    Dataset,
)
from verify_lab.studies.halving_cycle.halving_calendar import position_schedule
from verify_lab.studies.halving_cycle.hard_fork import hard_fork_share
from verify_lab.studies.halving_cycle.runner import halving_records, load_dataset
from verify_lab.studies.halving_cycle.split_rule import StopOutcome, calendar_split_grid
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

_T = TypeVar("_T")

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
# 확정 규칙의 폭 이름. **폭의 기간 · 회차 수는 측정 칸(`calendar_split_rule`)이 갖는다** — 두 칸에 적으면 한쪽이 낡는다
KEY_CALENDAR_SPLITS = "calendar_splits"

# 대상 기록 — **몇 건이 왜 빠졌는지** (절대 원칙 4 · 결정 ㊴). 제외는 행이 있고, 나머지 둘은 행이 없다
KEY_EXCLUDED_BY_REASON = "excluded_by_reason"
KEY_OUTSIDE_CYCLE_COUNT = "outside_cycle_count"
KEY_NOT_YET_COUNT = "not_yet_count"
# 확정 규칙의 폭마다 포지션 수와 끝나지 않은 포지션 — 끝나지 않은 것은 체결이 아니라 거래내역에 없고 여기에만 남는다
# (결정 61). **포지션을 한 번 센다** — 표본은 무손절 포지션이 끝났는가로 정해 두 손절 방식이 같은 포지션을 잰다
KEY_SPLIT_TARGETS = "calendar_split_targets"
# 그 폭에서 저점 이탈로 남은 보유를 판 포지션 수 — **표본에서 빠진 포지션도 센다.** 저점 이탈은 갭손절 · 장중손절에 들지 않고,
# 무손절이 끝나기 전에 이탈한 포지션은 거래내역에도 없어 이 칸이 아니면 체결 산출물에 숫자로 남지 않는다
KEY_STOP_SOLD_COUNT = "stop_sold_count"

# 요약에 싣는 비율(0 ~ 1)의 자릿수 — 전역 반올림 규칙표의 「비율」이다
RATIO_DECIMALS: Final = 4

# 산출물만 보고는 알 수 없는 실행 조건. **격자 값을 글자로 박지 않는다** — 값은 `rule` 의 목록이 말한다
NOTE_ENTRY = (
    "일시 격자 — 진입은 반감기일 + 진입 개월(달력월) 날의 종가다. 청산은 청산 개월이 진입 개월보다 크면 같은 반감기일 + 청산 개월, "
    "같거나 작으면 다음 반감기일 + 청산 개월 날의 종가다 — 보유는 최대 한 사이클이다. 없는 날짜는 그 달 말일로 당긴다. "
    "진입일이 다음 반감기 뒤인 시점은 그 사이클에 없고, 청산 시점 전에 반감기가 한 번 더 오면 그 행은 제외된다. "
    "반감기일은 블록 헤더 시각의 UTC 날짜다(2024 는 04-20)"
)
NOTE_RULE = (
    "확정 규칙 — 매매 방식이 달력 분할의 폭 이름인 행이다. 끝난 포지션 하나가 체결 한 건이고, 진입일은 첫 매수일 · 진입가는 "
    "평균 매수가 · 청산일은 마지막 매도일(저점 이탈로 판 포지션은 손절 매도일) · 청산가는 평균 매도가다. 개월 칸은 첫 매수 · "
    "첫 매도 회차라 일시 격자의 같은 개월 칸과 겹친다 — 매매 방식 칸으로 가른다. 회차 원자료는 측정 표 달력분할회차에 있다. "
    "표본은 무손절 포지션이 끝났는가로 정한다 — 저점 이탈로 먼저 끝난 포지션도 무손절이 끝날 때까지 두 손절 방식 행 모두에서 "
    "빠지고(일시 격자가 예정 청산일로 표본을 정하는 것과 같다), 그동안 그 손절 성적은 측정 표 달력분할손절에 있다"
)
NOTE_WORST = "보유 중 최악은 일시 격자가 진입가 대비, 확정 규칙이 평균 단가 대비(그날 전에 산 회차의 평균 단가 대비 장중 저가)다 — " "확정 규칙은 진입가가 하나가 아니다"
# **하한을 리터럴로 적지 않는다** — 값의 소유자는 `measure/constants.MIN_SAMPLE_PER_CELL` 하나다
NOTE_SAMPLE = (
    f"칸마다 표본이 많아야 반감기 사이클 수라 칸당 표본 하한({MIN_SAMPLE_PER_CELL})에 못 미친다 — 「판정가능」이 전 구간에서 "
    "「아니오」다. 다음 반감기 뒤에 파는 칸은 그 반감기가 지나야 표본이 생겨 더 적다. 결론의 일부이지 버그가 아니다"
)
NOTE_INDEPENDENCE = "칸은 같은 반감기 사이클들을 진입 · 청산 시점으로 나눈 것이라 칸끼리 독립이 아니다 — 「후보」 칸의 수를 독립된 발견의 수로 읽지 않는다. 후보는 자격이지 발견이 아니다"
NOTE_HOLD_LENGTH = "다음 반감기 뒤에 파는 칸은 사이클 길이가 달라 같은 칸이라도 사이클마다 보유 길이가 몇 달씩 다르다 — 반감기에 묶어 파는 규칙이라 그 차이를 받아들인다"
NOTE_STOP = (
    "일시 격자는 무손절 한 종이다 — 진입가 대비 % 손절선을 두지 않는다. 확정 규칙의 손절은 저점 이탈이다: 매수 기간에는 "
    "손절이 없고, 마지막 매수일까지의 사이클 고점 뒤 최저 종가가 손절선이며, 그 뒤 종가가 손절선 아래면 다음 거래일 종가에 "
    "남은 보유를 전부 판다. 종가로 판정하고 다음 날 종가에 팔아 갭손절 · 장중손절 건수에 들지 않는다 — 이탈은 거래내역의 "
    "청산 사유와, 표본에서 빠진 포지션까지 세는 요약의 폭별 저점 이탈 매도 수(stop_sold_count)가 말한다"
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
    f"하드포크로 나눠 받은 코인({' · '.join(fork.name for fork in HARD_FORKS)})의 몫은 BTC 시세에 없고 지급도 보장되지 않아 "
    "(Bitstamp 의 BCH 거래는 2017-12 에 열렸고 BTG 지급은 확인하지 못했다) 수익률 · 성적표 · "
    "1차 판정에 넣지 않는다 — 거래내역 끝 칸이 따로 잰다. 포크 코인을 첫 시세일 종가에 팔아 BTC 를 더 샀다고 보고, "
    "진입일 < 포크일 ≤ 청산일인 체결에 (Π(1 + 비율) − 1) × (1 + 체결 수익률) 이다. 확정 규칙은 (매수 회차 × 매도 회차) "
    "칸마다의 몫의 평균이다"
)
NOTES = (
    NOTE_ENTRY,
    NOTE_RULE,
    NOTE_WORST,
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
        performance: 종목 × 매매 방식 × 진입 개월 × 청산 개월 × 손절선 × 시기의 성적표. **방향은 「위」 하나다**
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
) -> None:
    """일시 격자 한 칸(진입 개월 × 청산 개월)을 무손절로 돌려 체결과 성적을 쌓는다.

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
    """
    entry_dates = pd.DatetimeIndex(rows[COL_DATE])
    entry_positions = resolve_positions(trading_days, entry_dates, label="진입일")
    exit_positions = resolve_positions(trading_days, pd.DatetimeIndex(rows[COL_EXIT_DATE]), label="청산일")

    # **표기를 한 번만 만든다** — 두 표가 같은 칸에 다른 값을 실으면 조인이 안 된다.
    # Bitstamp 시세는 고가·저가가 있어 장중 손절을 잴 수 있다 (로더가 네 가격을 검증한다)
    stop_display = stop_level_value(None, measurable=True)
    direction = DIRECTION_DOWN if BET_DOWN else DIRECTION_UP
    identity = {
        DISPLAY_TICKER: dataset.label,
        DISPLAY_TRADE_METHOD: TRADE_METHOD_LUMP,
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
            stop_level=None,
            price_column=COL_CLOSE,
        )
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


def _finished(value: _T | None, name: str, outcome: StopOutcome) -> _T:
    """끝난 포지션의 값을 꺼낸다 — 끝났는데 값이 비었으면 성적 산식이 깨진 것이다.

    Args:
        value: 꺼낼 값
        name: 값의 이름 (예외 메시지용)
        outcome: 그 값을 가진 결과

    Returns:
        그 값

    Raises:
        RuntimeError: 끝난 포지션인데 값이 비었을 때 (내부 불변조건)
    """
    if value is None:
        raise RuntimeError(
            f"내부 불변조건 위반: 끝난 포지션의 {name} 이 비었습니다 — {outcome.split.name} · {outcome.halving.label} · {outcome.method}"
        )

    return value


def _run_rule(
    dataset: Dataset,
    trading_days: pd.DatetimeIndex,
    split: CalendarSplit,
    method: str,
    outcomes: list[StopOutcome],
    accumulator: _Accumulator,
) -> None:
    """확정 규칙의 폭 하나 × 손절 방식 하나를 체결과 성적으로 쌓는다 — 끝난 포지션 하나가 체결 한 건이다 (결정 61).

    **확정 규칙은 사는 매매다** — 포지션 성적이 평균 매도가 ÷ 평균 매수가 − 1 이라 방향은 「위」이고 청산가는 위로 되돌린다.

    **보유일은 거래일 수다** — 일시 격자와 같은 단위로 첫 매수일과 청산일의 거래일 위치 차이로 센다.

    Args:
        dataset: 대상
        trading_days: 그 시세의 거래일 목록. 마지막 날이 「최근 N년」의 기준점이다
        split: 폭
        method: 손절 방식 — `NO_STOP_LABEL` 또는 `STOP_METHOD_LOW_BREAK`
        outcomes: 그 폭 · 손절 방식에서 **무손절 포지션이 끝난** 포지션의 결과 (반감기 순 — 첫 매수일 오름차순).
            무손절이 끝났으면 저점 이탈도 끝나 있다 — 남은 매도 회차가 데이터 안에 있어 손절 매도일도 데이터 안이다
        accumulator: 결과를 쌓는 자리

    Raises:
        RuntimeError: 넘겨받은 결과가 끝나지 않았을 때 (내부 불변조건)
    """
    first_buy_months, first_sell_months = split.first_deadlines(CALENDAR_SPLIT_STEP_MONTHS)
    stop_display = stop_level_value(None, measurable=True) if method == NO_STOP_LABEL else named_stop_value(method)
    identity = {
        DISPLAY_TICKER: dataset.label,
        DISPLAY_TRADE_METHOD: split.name,
        DISPLAY_ENTRY_MONTHS: first_buy_months,
        DISPLAY_EXIT_MONTHS: first_sell_months,
    }

    entry_days: list[pd.Timestamp] = []
    returns: list[float] = []
    hold_days: list[int] = []
    reasons: list[str] = []
    worst_rates: list[float] = []
    for outcome in outcomes:
        if outcome.reason != REASON_NONE:
            raise RuntimeError(
                f"내부 불변조건 위반: 무손절이 끝난 포지션의 {outcome.method} 성적이 끝나지 않았습니다 — "
                f"{outcome.split.name} · {outcome.halving.label} · {outcome.reason}"
            )
        result = outcome.result
        entry_day = _finished(result.first_buy_day, "첫 매수일", outcome)
        exit_day = _finished(result.last_sell_day, "마지막 매도일", outcome)
        entry_position, exit_position = resolve_positions(
            trading_days, pd.DatetimeIndex([entry_day, exit_day]), label="포지션 첫 매수일 · 청산일"
        ).tolist()
        trade = TradeResult(
            return_rate=_finished(result.return_rate, "수익률", outcome),
            reason=STOP_METHOD_LOW_BREAK if outcome.stop_sold else EXIT_LIMIT,
            hold_days=exit_position - entry_position,
            worst_hold_rate=_finished(result.worst_vs_cost, "평균 단가 대비 최악", outcome),
        )
        accumulator.trades.append(
            {
                **identity,
                DISPLAY_HALVING: outcome.halving.label,
                DISPLAY_DIRECTION: DIRECTION_UP,
                DISPLAY_STOP_LEVEL: stop_display,
                **trade_columns_from(
                    entry_day,
                    _finished(result.avg_buy_price, "평균 매수가", outcome),
                    exit_day,
                    trade,
                    bet_down=False,
                    price_decimals=dataset.price_decimals,
                ),
                DISPLAY_FORK_SHARE: round(
                    _finished(outcome.fork_share, "하드포크 몫", outcome) * RATE_TO_PERCENT, PERCENT_DECIMALS
                ),
            }
        )
        entry_days.append(entry_day)
        returns.append(trade.return_rate)
        hold_days.append(trade.hold_days)
        reasons.append(trade.reason)
        worst_rates.append(trade.worst_hold_rate)

    for row in period_rows(
        pd.DatetimeIndex(entry_days),
        returns,
        last_day=trading_days[-1],
        # **판정은 살 수 있는 것에만 건다** (측정의 원칙 9)
        tradable=dataset.is_judged,
        hold_days=hold_days,
        reasons=reasons,
        worst_hold_rates=worst_rates,
    ):
        accumulator.performance.append(
            {**identity, DISPLAY_DIRECTION: DIRECTION_UP, DISPLAY_STOP_LEVEL: stop_display, **row}
        )


def run_halving_cycle_trading(
    datasets: tuple[Dataset, ...] = DATASETS, *, calendar_splits: tuple[CalendarSplit, ...] = CALENDAR_SPLITS
) -> TradingOutputs:
    """반감기_사이클의 체결 성적을 낸다 — 대상 × 일시 격자(진입 개월 × 청산 개월, 무손절)와 확정 규칙(폭 × 손절 방식).

    Args:
        datasets: 대상 목록
        calendar_splits: 확정 규칙의 폭 목록. 기본은 확정한 폭(결정 57) — 테스트가 실제와 다른 폭을 넣는다

    Returns:
        체결 원자료와 성적표

    Raises:
        ValueError: 대상 목록이나 폭 목록이 비어 있는 경우
        RuntimeError: `BET_DOWN` 이 참인 경우 (내부 불변조건 위반)
    """
    if not datasets:
        raise ValueError("검증 대상이 하나도 없습니다")
    if not calendar_splits:
        raise ValueError("확정 규칙의 달력 분할 폭이 하나도 없습니다")
    # **방향은 「위」 하나다** — 확정 규칙은 사는 매매라 늘 「위」인데, 일시 격자만 아래로 걸면 한 성적표와 요약의 `direction`
    # 한 칸에 방향이 둘이 된다
    if BET_DOWN:
        raise RuntimeError(
            f"내부 불변조건 위반: 반감기_사이클의 체결은 「위」 한 방향입니다 — 확정 규칙이 사는 매매라 일시 격자만 아래로 걸 수 " f"없습니다: BET_DOWN={BET_DOWN}"
        )

    accumulator = _Accumulator()
    dataset_records: list[dict[str, Any]] = []
    target_records: list[dict[str, Any]] = []

    for dataset in datasets:
        frame = load_dataset(dataset).frame
        # **대상마다 한 번 만든다** — 칸마다 다시 만들 이유가 없다
        trading_days = pd.DatetimeIndex(frame[COL_DATE])

        schedule = position_schedule(trading_days, HALVINGS, ENTRY_MONTHS, EXIT_MONTHS)
        reasons = schedule.schedule[COL_EXCLUDED_REASON]
        valid = schedule.schedule[reasons == REASON_NONE].sort_values(COL_DATE, kind="stable")

        for entry_months in ENTRY_MONTHS:
            for exit_months in EXIT_MONTHS:
                rows = valid[(valid[COL_ENTRY_MONTHS] == entry_months) & (valid[COL_EXIT_MONTHS] == exit_months)]
                _run_cell(
                    dataset,
                    frame,
                    trading_days,
                    rows,
                    accumulator,
                    entry_months=entry_months,
                    exit_months=exit_months,
                )

        # **측정의 손절 표와 같은 인자로 부른다** — 같은 성적이 두 산출물에서 다르게 나오지 않는다
        grid = calendar_split_grid(
            frame,
            HALVINGS,
            calendar_splits,
            step_months=CALENDAR_SPLIT_STEP_MONTHS,
            peak_window_months=PEAK_WINDOW_MONTHS,
            forks=HARD_FORKS,
        )
        split_records: list[dict[str, Any]] = []
        for split in calendar_splits:
            outcomes = [outcome for outcome in grid.outcomes if outcome.split == split]
            # **표본은 무손절 포지션이 끝났는가로 정한다** — 두 손절 방식이 같은 포지션을 재야 「손절이 무엇을 막았는가」를
            # 한 표에서 견준다. 손절 방식마다 고르면 이탈로 먼저 끝난 포지션이 저점 이탈 행에만 들어가 두 행이 다른 표본을 잰다.
            # 그런 포지션은 무손절이 끝날 때까지 두 행 모두에서 빠지고, 그동안 그 손절 성적은 측정 표(달력분할손절)에,
            # 이탈했다는 사실은 아래 폭별 기록의 저점 이탈 매도 수에 있다
            plain = [outcome for outcome in outcomes if outcome.method == NO_STOP_LABEL]
            judged = {outcome.halving for outcome in plain if outcome.reason == REASON_NONE}
            for method in (NO_STOP_LABEL, STOP_METHOD_LOW_BREAK):
                chosen = [outcome for outcome in outcomes if outcome.method == method and outcome.halving in judged]
                _run_rule(dataset, trading_days, split, method, chosen, accumulator)
            unfinished = Counter(outcome.reason for outcome in plain if outcome.reason != REASON_NONE)
            split_records.append(
                {
                    KEY_NAME: split.name,
                    KEY_SIGNAL_COUNT: len(plain),
                    KEY_EXCLUDED_COUNT: sum(unfinished.values()),
                    KEY_EXCLUDED_BY_REASON: dict(unfinished),
                    KEY_STOP_SOLD_COUNT: sum(
                        outcome.stop_sold for outcome in outcomes if outcome.method == STOP_METHOD_LOW_BREAK
                    ),
                }
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
                KEY_SPLIT_TARGETS: split_records,
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
            KEY_CALENDAR_SPLITS: [split.name for split in calendar_splits],
            KEY_DIRECTION: DIRECTION_UP,
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
    "KEY_SPLIT_TARGETS",
    "KEY_STOP_SOLD_COUNT",
    "KEY_TARGETS",
    "TradingOutputs",
    "run_halving_cycle_trading",
]
