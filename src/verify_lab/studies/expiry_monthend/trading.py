"""만기_말일 체결 조립 — 확정 칸의 성적을 낸다

**계산하지 않는다.** 판정식과 성적 산식이 이미 있으므로 그것들을 조합해 돌리고,
어느 행이 어떤 설정의 결과인지를 붙여 쌓기만 한다.

| 빌려 쓰는 것 | 어디서 |
| --- | --- |
| 진입일·청산일 정의 | `studies/expiry_monthend/pairing.py` — 측정과 **같은 날에 들어간다** |
| 손절 판정 (시가 → 장중 → 청산일) | `execution/trade_fill.simulate_scheduled_trade` |
| 구간별 성적 산식 | `execution/periods.period_rows` |

**손절선은 두 종뿐이고 격자가 아니다.** 확정 −5% 와 무손절 대조이며, −5% 는 이 매매법이 고른
값이 아니라 두 매매법이 이미 확정한 값이다. 무손절을 함께 내는 것은
`.claude/rules/trading.md` 가 「손절이 무엇을 막았는가」를 수치로 요구하기 때문이고,
산출물이 그것을 직접 낸다 — `docs/매매/만기_말일/규칙.md` §2.3 이 같은 값을 문서로도 갖는다.

**지수는 한 줄뿐이다** — 장중 손절에 고가·저가가 필요한데 지수는 종가만 있어
`손절선(%)` 에 「손절불가」로 적힌다. 거부하지 않고 강등하는 것은 **긴 기간 축을 성적표에서
보기 위해서**다.

**비용을 넣지 않는다.** 수수료·슬리피지·세금은 사용자가 별도로 요청할 때만 넣는다
(루트 `CLAUDE.md` 2026-09-06 확정).
"""

from dataclasses import dataclass, field
from typing import Any

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
    DISPLAY_WORST_HOLD,
    NOTE_STOP_BASE,
    SUMMARY_FILENAME,
    TRADES_FILENAME,
    stop_level_value,
)
from verify_lab.execution.periods import period_rows, to_summary_frame
from verify_lab.execution.run_summary import build_run_summary
from verify_lab.execution.trade_fill import TradeResult, resolve_positions, simulate_scheduled_trade
from verify_lab.measure.constants import COL_EXCLUDED_REASON, COL_EXIT_DATE, COL_MONTH, REASON_NONE
from verify_lab.measure.screening import DIRECTION_DOWN, DIRECTION_UP
from verify_lab.report.constants import DATE_FORMAT, DISPLAY_MONTH_NUMBER, PERCENT_DECIMALS
from verify_lab.report.run_summary import dataset_record
from verify_lab.studies.expiry_monthend.constants import (
    COMBOS,
    DATASETS,
    DEFAULT_BET_DOWN,
    DISPLAY_COMBO,
    KEY_COMBO_ENTRY,
    KEY_COMBO_EXIT,
    KEY_COMBOS,
    KEY_ENTRY_COUNT,
    KEY_EXCLUDED_COUNT,
    KEY_LABEL,
    KEY_MONTHS,
    MONTHS,
    STOP_LEVELS_ETF,
    STOP_LEVELS_INDEX,
    TRACK_NAME,
    Combo,
    Dataset,
)
from verify_lab.studies.expiry_monthend.pairing import combo_entries, combo_returns
from verify_lab.studies.expiry_monthend.runner import load_dataset
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# `summary.json` 의 `rule` 안 — 무엇을 어떤 규칙으로 돌렸나.
# **최상위 키와 비용 표기는 `execution/run_summary.py` 가 소유한다**
KEY_STOP_LEVELS = "stop_levels"
KEY_TARGETS = "targets"

# 산출물만 보고는 알 수 없는 실행 조건
NOTE_ENTRY = "진입은 셋째 금요일 또는 그 달 20일(둘 다 휴장이면 직전 거래일) 종가이고, " "청산은 다음 주 금요일 또는 그 달 마지막 거래일 종가다 — 측정과 같은 날에 들어간다"
NOTE_COLLAPSE = (
    "네 조합은 해에 따라 같은 날로 붕괴한다 — 진입·청산이 둘 다 같아 두 조합이 한 매매가 되는 해가 절반 가까이 된다. "
    "그 크기는 이 실행의 통계 표가 「이 조합만 다른 해」로 직접 세므로 여기에 숫자를 적지 않는다"
)
NOTE_INDEX = (
    "지수는 종가만 있어 장중 손절을 잴 수 없다. 한 줄로만 나오며 「손절선(%)」 에 「손절불가」로 적힌다. "
    "같은 이유로 「보유 중 최악(%)」 도 종가로 재므로 ETF 행(장중 고가·저가 기준)보다 얕게 나온다"
)
NOTE_MONTHS = "재는 달은 두 매매법이 이미 가리킨 뒤에 고른 것이라 사후 선택이다 — " "이 성적으로 「우위가 있다」를 새로 주장할 수 없다"

# **방향은 격자로 돌지 않는다.** 확정 칸의 방향 하나만 내므로, 축을 넓혀 돌린 실행에서
# 「그 칸을 반대로 걸면 어떤가」는 이 산출물이 답하지 않는다 — 판정도 그 방향의 것이다.
# **좁혀 돌린 실행이 전체 실행 폴더를 덮으므로 요약이 유일한 기록이다**
NOTE_DIRECTION = "방향은 확정 칸의 한 값으로 고정해 돌았다 — 반대 방향의 성적과 판정은 이 산출물에 없다. " "그 방향을 다시 고를 재료는 측정 표의 오른 비율·내린 비율(1배 롱 기준)이다"


@dataclass(frozen=True)
class TradingOutputs:
    """체결 산출물

    Attributes:
        trades: 체결 원자료. 진입·청산 날짜와 실제 체결가가 들어 있다 (측정의 원칙 8)
        performance: 종목 × 조합 × 달 × 방향 × 손절선 × 구간의 성적표
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


@dataclass(frozen=True)
class _Entries:
    """한 칸의 진입·청산 위치

    Attributes:
        entry_positions: 진입일의 위치 인덱스
        exit_positions: 청산일의 위치 인덱스
        entry_dates: 진입일
    """

    entry_positions: list[int]
    exit_positions: list[int]
    entry_dates: pd.DatetimeIndex


def _collect_entries(
    dataset: Dataset, frame: pd.DataFrame, combo: Combo, months: tuple[int, ...]
) -> tuple[dict[int, _Entries], int]:
    """측정과 같은 규칙으로 달별 진입·청산 위치를 만든다.

    **진입일 정의를 두 벌 만들지 않는다** — `pairing` 의 함수를 그대로 부르므로
    측정과 체결이 같은 날에 들어간다.

    Args:
        dataset: 대상 종목
        frame: 날짜 오름차순 가격 데이터
        combo: 진입 × 청산 조합
        months: 재는 달 목록

    Returns:
        (달 → 진입 목록, 청산일을 확정하지 못해 빠진 진입 수)

    Raises:
        RuntimeError: 진입일·청산일이 시세의 거래일에 없는 경우 (내부 불변조건 위반)
    """
    trading_days = pd.DatetimeIndex(frame[COL_DATE])
    entries = combo_entries(trading_days, combo)
    returns = combo_returns(frame, trading_days, entries, combo, price_column=dataset.price_column)

    # **진입일이 아니라 «진입 달» 로 거른다** — 진입일을 못 정한 행은 날짜가 `NaT` 라
    # `.dt.month` 가 비고, 그러면 진입에도 제외에도 안 들어가 몇 건이 왜 빠졌는지가 사라진다
    in_months = returns[returns[COL_MONTH].dt.month.isin(months)]
    kept = in_months[COL_EXCLUDED_REASON] == REASON_NONE
    usable = in_months[kept]
    excluded_count = int((~kept).sum())

    by_month: dict[int, _Entries] = {}
    for month in months:
        rows = usable[usable[COL_DATE].dt.month == month]
        entry_dates = pd.DatetimeIndex(rows[COL_DATE])
        exit_dates = pd.DatetimeIndex(rows[COL_EXIT_DATE])
        by_month[month] = _Entries(
            entry_positions=[int(position) for position in resolve_positions(trading_days, entry_dates, label="진입일")],
            exit_positions=[int(position) for position in resolve_positions(trading_days, exit_dates, label="청산일")],
            entry_dates=entry_dates,
        )

    logger.debug(f"{dataset.ticker} / {combo.label}: 진입 {len(usable):,}건, 제외 {excluded_count:,}건")

    return by_month, excluded_count


def _trade_row(
    dataset: Dataset,
    frame: pd.DataFrame,
    entry_position: int,
    result: TradeResult,
    *,
    combo: Combo,
    month: int,
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
        combo: 진입 × 청산 조합
        month: 진입 달
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
        DISPLAY_COMBO: combo.label,
        DISPLAY_MONTH_NUMBER: month,
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
    combo: Combo,
    month: int,
    bet_down: bool,
    stop_level: float | None,
    last_day: pd.Timestamp,
) -> None:
    """한 칸(조합 × 달 × 방향 × 손절선)을 돌려 체결과 성적을 쌓는다.

    Args:
        dataset: 대상 종목
        frame: 가격 데이터
        entries: 그 달의 진입 목록
        accumulator: 결과를 쌓는 자리
        combo: 진입 × 청산 조합
        month: 진입 달
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
            _trade_row(
                dataset,
                frame,
                entry_position,
                result,
                combo=combo,
                month=month,
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
        DISPLAY_COMBO: combo.label,
        DISPLAY_MONTH_NUMBER: month,
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


def run_expiry_monthend_trading(
    datasets: tuple[Dataset, ...] = DATASETS,
    *,
    combos: tuple[Combo, ...] = COMBOS,
    months: tuple[int, ...] = MONTHS,
    bet_down: bool = DEFAULT_BET_DOWN,
) -> TradingOutputs:
    """만기_말일 체결 성적을 낸다.

    **대상 × 조합 × 달 × 손절선 두 종**을 돈다. 방향은 확정 칸의 값 하나이며,
    손절선은 확정 −5% 와 무손절 대조 둘이다 (`.claude/rules/trading.md` 가 요구하는 대조축).

    Args:
        datasets: 대상 목록
        combos: 돌릴 조합 목록
        months: 재는 달 목록
        bet_down: 아래로 거는지 여부. 기본값의 SoT 는 `TRADING_CELLS` 다

    Returns:
        체결 원자료와 성적표

    Raises:
        ValueError: 목록이 비어 있거나, 어떤 대상의 진입이 하나도 없는 경우
    """
    if not datasets:
        raise ValueError("검증 대상이 하나도 없습니다")
    if not combos:
        raise ValueError("조합이 하나도 없습니다")
    if not months:
        raise ValueError("재는 달이 하나도 없습니다")

    accumulator = _Accumulator()
    dataset_records: list[dict[str, Any]] = []
    target_records: list[dict[str, Any]] = []

    for dataset in datasets:
        frame = load_dataset(dataset)
        last_day = pd.Timestamp(frame[COL_DATE].iloc[-1])
        levels = STOP_LEVELS_INDEX if dataset.is_index else STOP_LEVELS_ETF

        entry_count = 0
        excluded_count = 0
        for combo in combos:
            by_month, dropped = _collect_entries(dataset, frame, combo, months)
            excluded_count += dropped

            # **조합마다, 그리고 체결 «전»에 본다.** 조합을 합쳐 세면 한 조합이 0 이어도
            # 다른 조합이 채워 통과하고, 그 사이 빈 조합의 시기 5행이 **전부 빈 채로**
            # 성적표에 들어간다. 가드를 뒤에 두면 그 행은 이미 쌓인 뒤다
            empty_months = sorted(month for month in months if not by_month[month].entry_positions)
            if empty_months:
                raise ValueError(f"{dataset.label} / {combo.label}: 진입이 하나도 없습니다 (빈 달 {empty_months})")
            # **측정과 같은 것을 센다** — `KEY_ENTRY_COUNT` 가 한 벌인 이유가 그것이다.
            # 측정은 「유효 + 제외」를 진입으로 세고 제외를 따로 내므로 여기서도 더한다.
            # 유효만 세면 제외가 생기는 순간 두 요약이 다른 숫자를 적는데 예외는 나지 않는다
            entry_count += sum(len(entries.entry_positions) for entries in by_month.values()) + dropped

            for month in months:
                # **방향을 격자로 돌지 않는다.** 확정 칸의 방향 하나만 내며, 반대 방향의 성적은
                # 측정 표의 오른 비율·내린 비율(1배 롱 기준)로 되짚는다. 두 방향을 함께 내면
                # 측정 표의 한 행에 성적표 두 행이 붙어 1:1 조인이 깨진다
                for stop_level in levels:
                    _run_cell(
                        dataset,
                        frame,
                        by_month[month],
                        accumulator,
                        combo=combo,
                        month=month,
                        bet_down=bet_down,
                        stop_level=stop_level,
                        last_day=last_day,
                    )

        dataset_records.append(
            dataset_record(ticker=dataset.ticker, label=dataset.label, file=dataset.path.name, frame=frame)
        )
        # **제외 건수를 대상마다 남긴다** (패키지 절대 원칙 「표본 보존」)
        target_records.append(
            {KEY_LABEL: dataset.label, KEY_ENTRY_COUNT: entry_count, KEY_EXCLUDED_COUNT: excluded_count}
        )

    trades = pd.DataFrame(accumulator.trades)
    performance = to_summary_frame(accumulator.performance)

    # **성적표에 실제로 나온 값을 적는다.** 격자를 그대로 적으면 지수만 고른 실행에서
    # 돌지도 않은 손절선을 적게 된다
    stop_levels_run = list(dict.fromkeys(performance[DISPLAY_STOP_LEVEL]))

    # **실제로 돈 것만 적는다.** `notes` 는 「산출물만 보고는 알 수 없는 실행 조건」이고,
    # 좁혀 돌린 실행이 전체 실행 폴더를 덮으므로 **`summary.json` 이 유일한 기록**이다 —
    # 안 돈 달과 안 쓴 대상의 주의를 적으면 그 기록이 거짓이 된다
    notes = [NOTE_ENTRY, NOTE_STOP_BASE, NOTE_DIRECTION]
    if len(combos) > 1:
        notes.append(NOTE_COLLAPSE)
    if any(dataset.is_index for dataset in datasets):
        notes.append(NOTE_INDEX)
    # **부분집합에도 붙인다.** 「9월·12월 전부일 때만」으로 두면 기본 실행(9월 하나)에서
    # **사후 선택 경고가 통째로 빠진다** — 그 한 달이 바로 사후에 고른 달인데도 그렇다
    if set(months) <= set(MONTHS):
        notes.append(NOTE_MONTHS)

    summary = build_run_summary(
        track=TRACK_NAME,
        datasets=dataset_records,
        rule={
            KEY_COMBOS: [
                {KEY_LABEL: combo.label, KEY_COMBO_ENTRY: combo.entry, KEY_COMBO_EXIT: combo.exit_rule}
                for combo in combos
            ],
            KEY_MONTHS: list(months),
            KEY_STOP_LEVELS: stop_levels_run,
            KEY_TARGETS: target_records,
        },
        row_counts={TRADES_FILENAME: len(trades), SUMMARY_FILENAME: len(performance)},
        notes=notes,
    )

    logger.debug(f"체결 완료: 거래내역 {len(trades):,}행, 성적표 {len(performance):,}행")

    return TradingOutputs(trades=trades, performance=performance, summary=summary)


__all__ = ["TradingOutputs", "run_expiry_monthend_trading"]
