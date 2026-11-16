"""하락_단계_매수 체결 조립 — 대상 × 지표 × 단계 × 보유 기간을 무손절로 체결한 성적표와 거래내역

**계산하지 않는다.** 판정식과 성적 산식이 이미 있으므로 조합해 돌리고, 어느 행이 어떤 칸의 결과인지를 붙여 쌓는다.

| 빌려 쓰는 것 | 어디서 |
| --- | --- |
| 시세 · 단계 신호 · 판정일 × 보유 기간 일정 | `studies/drawdown_tiers/runner` — 측정과 **같은 신호 · 같은 진입점**(판정일 다음 거래일 종가 · 설계 결정 D1) |
| 체결 (무손절) | `execution/trade_fill.simulate_scheduled_trade` |
| 거래내역의 공통 칸 | `execution/trade_rows.trade_columns` |
| 시기별 성적과 1차 판정 | `execution/periods.period_rows` — 사건 번호(하락장 시작일)를 넘겨 `사건` 칸을 낸다 (D6) |

**맨몸 격자다** — 분할 방식 · 비중 · 청산 · 손절 규칙은 이 결과를 본 뒤 정한다(`docs/검증/하락_단계_매수/설계.md` §1). 손절선은 무손절 한 종,
지수는 장중을 잴 수 없어 `손절불가` 다. **방향은 「위」 하나다** — 빠졌을 때 사는 매매법이다.

**비용을 넣지 않는다.** 수수료 · 슬리피지 · 세금은 사용자가 별도로 요청할 때만 넣는다 (루트 `CLAUDE.md` 2026-09-06 확정).
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Final

import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.execution.constants import (
    DISPLAY_DIRECTION,
    DISPLAY_STOP_LEVEL,
    DISPLAY_TICKER,
    SUMMARY_FILENAME,
    TRADES_FILENAME,
    stop_level_value,
)
from verify_lab.execution.periods import period_rows, to_summary_frame
from verify_lab.execution.run_summary import KEY_TARGETS, build_run_summary
from verify_lab.execution.trade_fill import resolve_positions, simulate_scheduled_trade
from verify_lab.execution.trade_rows import trade_columns
from verify_lab.measure.constants import COL_EXCLUDED_REASON, COL_HORIZON, MIN_SAMPLE_PER_CELL, REASON_NONE
from verify_lab.measure.screening import DIRECTION_UP
from verify_lab.report.constants import DATE_FORMAT
from verify_lab.report.run_summary import KEY_DATASET_LABEL, KEY_EXCLUDED_COUNT, dataset_record
from verify_lab.studies.drawdown_tiers.constants import (
    COL_ENTRY_DATE,
    COL_EVENT_START,
    COL_TIER,
    DATASETS,
    DISPLAY_EVENT_START,
    DISPLAY_HORIZON,
    DISPLAY_INDICATOR,
    DISPLAY_JUDGMENT_DATE,
    DISPLAY_TIER,
    DRAWDOWN_RULE,
    HORIZONS,
    INDICATOR_FILES,
    KEY_EXCLUDED_BY_REASON,
    KEY_INDICATOR,
    KEY_SIGNAL_COUNT,
    RULES,
    TRACK_NAME,
    Dataset,
    IndicatorFiles,
)
from verify_lab.studies.drawdown_tiers.runner import (
    IndicatorSignals,
    load_dataset,
    load_indicators,
    signal_set,
    tier_returns,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 사던 매매법 — 체결 판정식의 방향 인자
BET_DOWN: Final = False

# 산출물만 보고는 알 수 없는 실행 조건. **격자 값을 글자로 박지 않는다** — 값은 측정 요약의 `rules` · `horizons` 가 말함
NOTE_ENTRY = (
    "판정일(그날 종가로 단계에 닿은 날)의 다음 거래일 종가에 사서 보유 기간(거래일) 뒤 종가에 판다 — " "VIX 종가와 공포탐욕지수는 ETF 종가보다 늦게 확정돼 판정일 종가에는 살 수 없다"
)
NOTE_SIGNAL_SOURCE = (
    "ETF 행은 신호 대상(측정 요약 datasets 의 signal_file)의 낙폭 · 거래일로 판정한 같은 신호를 쓴다 — 신호 대상보다 늦게 상장한 "
    "대상의 상장 전 신호는 거래내역에 없고 요약의 제외 사유에 남는다. 지수 행은 자기 낙폭 · 자기 거래일로 판정한다"
)
NOTE_EPISODE = (
    "신호는 구간마다 단계별로 처음 닿은 날 한 번이다 — 지표가 다시 켜는 수준("
    + " · ".join(f"{rule.indicator} {rule.rearm_label()}" for rule in RULES)
    + f")에 닿으면 단계를 모두 다시 켠다. {DRAWDOWN_RULE.indicator} {DRAWDOWN_RULE.rearm_label()}이 곧 새 고점(고점과 같은 종가 포함)이다"
)
NOTE_INDEPENDENCE = (
    "같은 하락장의 단계 · 지표 · 보유 기간은 같은 미래 경로를 공유해 행끼리 독립이 아니다 — 성적표의 사건 칸은 "
    "신호가 든 하락장(판정일까지의 역대 고점 → 새 고점) 수다. 후보는 자격이지 발견이 아니다"
)
# **하한을 리터럴로 적지 않는다** — 값의 소유자는 `measure/constants.MIN_SAMPLE_PER_CELL` 하나
NOTE_SAMPLE = (
    f"깊은 단계는 사건이 적어 칸당 표본 하한({MIN_SAMPLE_PER_CELL})에 못 미친다 — 「판정가능」이 「아니오」인 칸은 " "통계로 우열을 가릴 수 없다. 결론의 일부이지 버그가 아니다"
)
NOTE_STOP = "손절선이 없는 맨몸 격자다 — 지수는 장중을 잴 수 없어 손절불가이고 보유 중 최악도 종가로 잰 값이라 실제보다 얕다"
NOTE_SCREEN = (
    "보유가 길어 평균이 양수인 칸은 거의 모두 1차 판정을 넘는다 — 게이트는 하나이고 이 격자에 맞춰 바꾸지 않는다. "
    "성적표에는 기준선을 두지 않는다 — 같은 진입 규칙의 기준선과 그 차이는 측정 표(excess)에 있다"
)
NOTE_DIRECTION = "방향은 「위」 하나다. 아래로 거는 칸의 크기와 빈도는 측정 표(통계)의 내린 비율과 평균이 준다"
NOTES: Final = (
    NOTE_ENTRY,
    NOTE_SIGNAL_SOURCE,
    NOTE_EPISODE,
    NOTE_INDEPENDENCE,
    NOTE_SAMPLE,
    NOTE_STOP,
    NOTE_SCREEN,
    NOTE_DIRECTION,
)


@dataclass(frozen=True)
class TradingOutputs:
    """체결 산출물

    Attributes:
        trades: 체결 원자료 — 판정일 · 진입 · 청산 · 하락장 시작일 (측정의 원칙 8)
        performance: 종목 × 지표 × 단계 × 보유 × 시기의 성적표
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


def run_drawdown_tiers_trading(
    datasets: tuple[Dataset, ...] = DATASETS, *, indicator_files: IndicatorFiles = INDICATOR_FILES
) -> TradingOutputs:
    """하락_단계_매수의 체결 성적을 낸다 — 대상 × 지표 × 단계 × 보유 기간, 무손절.

    Args:
        datasets: 대상 목록
        indicator_files: 외부 지표 파일 둘 — 테스트가 합성 파일을 넣는다

    Returns:
        체결 원자료와 성적표

    Raises:
        ValueError: 대상 목록이 비어 있는 경우
    """
    if not datasets:
        raise ValueError("검증 대상이 하나도 없습니다")

    indicators = load_indicators(indicator_files)
    accumulator = _Accumulator()
    dataset_records: list[dict[str, Any]] = []
    target_records: list[dict[str, Any]] = []

    for dataset in datasets:
        loaded = load_dataset(dataset)
        frame = loaded.frame
        trading_days = pd.DatetimeIndex(frame[COL_DATE])
        signals = signal_set(loaded, indicators)

        for signal in signals.indicators:
            returns = tier_returns(
                frame, signal, signals.context, label=dataset.label, price_column=dataset.price_column
            )
            _run_indicator(dataset, frame, trading_days, signal, returns, accumulator)

            reasons = Counter(reason for reason in returns[COL_EXCLUDED_REASON] if reason != REASON_NONE)
            target_records.append(
                {
                    KEY_DATASET_LABEL: dataset.label,
                    KEY_INDICATOR: signal.rule.indicator,
                    KEY_SIGNAL_COUNT: len(returns),
                    KEY_EXCLUDED_COUNT: sum(reasons.values()),
                    KEY_EXCLUDED_BY_REASON: dict(reasons),
                }
            )

        # `ticker` 는 반드시 `dataset.ticker` 에서 — 둘 다 `str` 이라 다른 필드를 넘겨도 키는 그대로고 값만 뒤바뀜
        dataset_records.append(
            dataset_record(ticker=dataset.ticker, label=dataset.label, file=dataset.path.name, frame=frame)
        )

    trades = pd.DataFrame(accumulator.trades)
    performance = to_summary_frame(accumulator.performance)
    summary = build_run_summary(
        track=TRACK_NAME,
        datasets=dataset_records,
        rule={KEY_TARGETS: target_records},
        row_counts={TRADES_FILENAME: len(trades), SUMMARY_FILENAME: len(performance)},
        notes=NOTES,
    )

    logger.debug(f"체결 완료: 거래내역 {len(trades):,}행, 성적표 {len(performance):,}행")

    return TradingOutputs(trades=trades, performance=performance, summary=summary)


def _run_indicator(
    dataset: Dataset,
    frame: pd.DataFrame,
    trading_days: pd.DatetimeIndex,
    signal: IndicatorSignals,
    returns: pd.DataFrame,
    accumulator: _Accumulator,
) -> None:
    """지표 하나의 단계 × 보유 기간 칸을 무손절로 돌려 체결과 성적을 쌓는다.

    **체결이 하나도 없는 칸도 시기 다섯 행을 낸다** — 행이 사라지면 그 칸을 못 봤다는 사실 자체를 모른다
    (측정의 원칙 17). 그 행의 지표는 비고 1차 판정은 「판정 안 함」이다.

    Args:
        dataset: 대상
        frame: 대상 가격
        trading_days: 대상 거래일. 마지막 날이 「최근 N년」의 기준점이다
        signal: 지표 하나의 단계 신호
        returns: 그 지표의 단계별 long-form (`runner.tier_returns`)
        accumulator: 결과를 쌓는 자리
    """
    # 지수는 고가 · 저가가 없어 장중 손절을 잴 수 없음 — 무손절 한 줄이 손절불가로 적힘
    stop_display = stop_level_value(None, measurable=not dataset.is_index)
    valid = returns[returns[COL_EXCLUDED_REASON] == REASON_NONE]

    for level in signal.rule.levels:
        tier = signal.rule.label(level)
        for horizon in HORIZONS:
            rows = valid[(valid[COL_TIER] == tier) & (valid[COL_HORIZON] == horizon)]
            identity = {
                DISPLAY_TICKER: dataset.label,
                DISPLAY_INDICATOR: signal.rule.indicator,
                DISPLAY_TIER: tier,
                DISPLAY_HORIZON: horizon,
            }
            entry_dates = pd.DatetimeIndex(rows[COL_ENTRY_DATE])
            entry_positions = resolve_positions(trading_days, entry_dates, label="진입일")

            results = [
                simulate_scheduled_trade(
                    frame,
                    entry_position,
                    entry_position + horizon,
                    bet_down=BET_DOWN,
                    stop_level=None,
                    price_column=dataset.price_column,
                )
                for entry_position in entry_positions.tolist()
            ]
            event_starts = pd.DatetimeIndex(rows[COL_EVENT_START])
            judgment_dates = pd.DatetimeIndex(rows[COL_DATE])

            for entry_position, result, judgment_day, event_start in zip(
                entry_positions.tolist(), results, judgment_dates, event_starts, strict=True
            ):
                accumulator.trades.append(
                    {
                        **identity,
                        DISPLAY_JUDGMENT_DATE: judgment_day.strftime(DATE_FORMAT),
                        DISPLAY_DIRECTION: DIRECTION_UP,
                        DISPLAY_STOP_LEVEL: stop_display,
                        **trade_columns(
                            frame,
                            entry_position,
                            result,
                            bet_down=BET_DOWN,
                            price_column=dataset.price_column,
                            price_decimals=dataset.price_decimals,
                        ),
                        DISPLAY_EVENT_START: event_start.strftime(DATE_FORMAT),
                    }
                )

            # 사건 번호 — 하락장 시작일을 그 자리에서 정수로 바꿈 (구간마다 서로 다른 값의 수만 셈)
            event_ids = pd.factorize(event_starts)[0].tolist()
            for row in period_rows(
                entry_dates,
                [result.return_rate for result in results],
                last_day=trading_days[-1],
                # **판정은 살 수 있는 것에만 건다** (측정의 원칙 9)
                tradable=dataset.is_judged,
                hold_days=[result.hold_days for result in results],
                reasons=[result.reason for result in results],
                event_ids=event_ids,
                worst_hold_rates=[result.worst_hold_rate for result in results],
            ):
                accumulator.performance.append(
                    {**identity, DISPLAY_DIRECTION: DIRECTION_UP, DISPLAY_STOP_LEVEL: stop_display, **row}
                )
