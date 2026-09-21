"""월말 매매의 손절 격자 실행 — 조립만 한다

**계산하지 않는다.** 판정식과 성적 산식이 이미 있으므로 그것들을 조합해 돌리고,
어느 행이 어떤 설정의 결과인지를 붙여 쌓기만 한다.

| 빌려 쓰는 것 | 어디서 |
| --- | --- |
| 진입일·청산일 정의 | `studies/month_end/schedule.py` — 검증 #10 과 **같은 날에 들어간다** |
| 손절 판정 (시가 → 장중 → 청산일) | `execution/trade_fill.simulate_scheduled_trade` |
| 구간별 성적 산식 | `execution/periods.period_rows` |

**이 매매법에는 고유 체결 로직이 한 줄도 없다.** 규칙이 옵션 만기일과 같아(며칠 들고 정해진 날
청산 + 손절) 공유 계층을 그대로 부른다. 그래서 `month_end_trading.py` 를 두지 않는다 —
만들면 내용이 비거나, 계산을 복사해 **같은 매매법의 성적이 산출물마다 갈라진다.**
빌려 쓰는 두 모듈은 **매매법 이름을 갖지 않는다** — 둘이 옵션 만기일 파일 안에 있으면
월말이 그쪽을 import 하게 되고, 옵션 만기일 사정으로 고칠 때 이 매매법 성적이 함께 바뀐다.

**새 판정식을 만들지 않는다.** 시가·장중 순서가 뒤바뀌면 손실이 실제보다 작게 나오는데,
그 함정을 여러 곳에서 관리하게 된다 (`docs/매매/월말_진입/설계.md` 가 가리키는 결정 ㉝).

**확정 칸만 돈다** (2026-09-21 사용자 결정). 전에는 12개월 × 두 방향을 전부 냈고,
그 방침을 사용자가 뒤집어 **실제로 거는 칸 하나**로 좁혔다.
[중요] **코드가 칸을 고르는 것은 아니다** — 목록은 `docs/매매/월말_진입/규칙.md` §3 의
결론을 옮겨 적은 것이고, **재수집하면 성적표를 보고 다시 판단해야 한다.**
**격자를 재는 수단은 남아 있다** — 손절선은 `--stop-grid`, 방향과 달은 그 문서의 근거다.

**비용을 넣지 않는다.** 수수료·슬리피지·세금은 사용자가 별도로 요청할 때만 넣는다
(루트 `CLAUDE.md` 2026-09-06 확정).
"""

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from verify_lab.common_constants import COL_DATE, RATE_TO_PERCENT
from verify_lab.data.loader import load_market_csv, load_series_csv
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
from verify_lab.measure.constants import COL_EXCLUDED_REASON, REASON_NONE
from verify_lab.report.constants import DATE_FORMAT, PERCENT_DECIMALS
from verify_lab.report.run_summary import dataset_record
from verify_lab.studies.month_end.constants import (
    BASE_ENTRY_DAY,
    BASE_EXIT_OFFSET,
    COL_EXIT_DATE,
    COL_MONTH,
    DATASETS_TRADING,
    DISPLAY_MONTH_NUMBER,
    KEY_CELL_DIRECTION,
    KEY_CELL_MONTH,
    KEY_CELLS,
    KEY_ENTRY_COUNT,
    KEY_EXCLUDED_COUNT,
    MONTH_END_STOP_DEFAULT,
    TRACK_NAME,
    TRADING_CELLS,
    Dataset,
    MonthEndCell,
)
from verify_lab.studies.month_end.runner import cell_direction
from verify_lab.studies.month_end.schedule import month_entry_dates, month_exit_schedule
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# **손절선 목록도 확정 칸 목록도 `constants.py` 가 소유한다.** 여기서 만들면 CLI 와 두 벌이
# 되고, 갈려도 예외가 나지 않는다 — `meta.json` 이 돌지 않은 격자를 적게 된다

# `summary.json` 의 `rule` 안 — 무엇을 어떤 규칙으로 돌렸나.
# **최상위 키와 비용 표기는 `execution/run_summary.py` 가 소유한다** — 매매법이 각자 가지면
# 가진 쪽과 안 가진 쪽이 갈려 세 요약을 나란히 읽을 수 없다
KEY_STOP_LEVELS = "stop_levels"
KEY_TARGETS = "targets"
KEY_LABEL = "label"

# 어느 구간을 잰 것인가. **폴더 이름으로는 구별되지 않는다** — 측정과 매매가 slug 하나를
# 공유하므로 전 기간 실행과 걸러낸 실행이 같은 이름을 갖는다. 여기가 유일한 구분자다
KEY_FROM_YEAR = "from_year"

# 산출물만 보고는 알 수 없는 실행 조건
NOTE_ENTRY = "진입은 그 달 20일(휴장이면 직전 거래일) 종가이고 청산은 말일 종가다 — 검증 #10 과 같은 날에 들어간다"
NOTE_INDEX = (
    "지수는 종가만 있어 장중 손절을 잴 수 없다. 한 줄로만 나오며 「손절선(%)」 에 「손절불가」로 적힌다. "
    "같은 이유로 「보유 중 최악(%)」 도 종가로 재므로 ETF 행(장중 고가·저가 기준)보다 얕게 나온다"
)
NOTE_FROM_YEAR = "시작 연도로 «신호»만 걸렀고 시세는 자르지 않았다 — 「최근 N년」의 기준일은 여전히 시세의 마지막 거래일이다"


@dataclass(frozen=True)
class TradingOutputs:
    """손절 격자 산출물

    Attributes:
        trades: 체결 원자료. 진입·청산 날짜와 실제 체결가가 들어 있다 (측정의 원칙 8)
        performance: 종목 × 월 × 방향 × 손절선 × 구간의 성적표.
            **손절선 하나만 보려면 `손절선(%)` 을 그 숫자와 `손절불가` 로 거른다** —
            지수는 숫자 행이 없으므로 그 값을 함께 걸어야 긴 기간 축이 남는다.
            **확정 손절선은 기초자산 기준 −5% 이고 2배 상품으로는 −10% 다**
            (`docs/매매/월말_진입/규칙.md` §1.1)
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
    """한 달의 진입·청산 위치

    Attributes:
        entry_positions: 진입일의 위치 인덱스
        exit_positions: 청산일의 위치 인덱스
        entry_dates: 진입일
    """

    entry_positions: list[int]
    exit_positions: list[int]
    entry_dates: pd.DatetimeIndex


def _collect_entries(
    dataset: Dataset, frame: pd.DataFrame, *, from_year: int | None
) -> tuple[dict[int, _Entries], int]:
    """검증 #10 과 같은 규칙으로 월별 진입·청산 위치를 만든다.

    **진입일 정의를 두 벌 만들지 않는다** — `studies` 의 함수를 그대로 부르므로
    측정과 매매가 같은 날에 들어간다.

    **시작 연도는 «신호»에만 건다.** 시세를 먼저 잘라 넘기면 「최근 N년」의 기준일이
    함께 움직여 두 실행이 다른 창을 가리키게 되고, **결과는 달라지는데 예외는 나지 않는다**
    (루트 `CLAUDE.md` — 잘라내는 대상은 언제나 신호 선택이지 시세가 아니다).

    Args:
        dataset: 대상 종목
        frame: 날짜 오름차순 시세
        from_year: 이 연도의 진입부터 센다 (포함). `None` 이면 전 기간

    Returns:
        (월 → 진입 목록, 청산일을 확정하지 못해 빠진 진입 수)

    Raises:
        RuntimeError: 진입일·청산일이 시세의 거래일에 없는 경우 (내부 불변조건 위반)
    """
    trading_days = pd.DatetimeIndex(frame[COL_DATE])

    entries = month_entry_dates(trading_days, calendar_day=BASE_ENTRY_DAY)
    schedule = month_exit_schedule(trading_days, entries, exit_offset=BASE_EXIT_OFFSET)

    kept = schedule.frame[COL_EXCLUDED_REASON] == REASON_NONE
    usable = schedule.frame[kept]
    dropped = schedule.frame[~kept]

    # **거르는 기준은 진입일이 아니라 «진입 달» 이다.** 앞당김으로 며칠 당겨져도 그 신호가
    # 속한 달은 변하지 않으므로, 달력으로 세는 편이 「2000년 이후」라는 말과 정확히 맞는다.
    #
    # **제외 목록에도 같은 필터를 건다.** 걸지 않으면 범위 «밖» 의 제외가 성적표에 실려
    # 「청산일을 확정하지 못했다」와 「아예 묻지 않았다」가 한 숫자로 합쳐진다 (표본 보존)
    if from_year is not None:
        usable = usable[usable[COL_MONTH].dt.year >= from_year]
        dropped = dropped[dropped[COL_MONTH].dt.year >= from_year]

    # **제외 건수의 분모를 진입 건수와 맞춘다.** 아래에서 진입을 확정 칸의 달로만 세므로
    # 제외를 열두 달로 세면 **두 숫자가 다른 모집단을 가리킨다** — `summary.json` 이
    # 「진입 23, 제외 1」로 적어 9월 진입 하나가 빠진 것처럼 읽히는데 실제로는 다른 달이다.
    # 표본 보존은 「몇 건이 왜 빠졌는지」가 맞아야 지켜진 것이다
    wanted = {cell.month for cell in TRADING_CELLS}
    dropped = dropped[dropped[COL_MONTH].dt.month.isin(wanted)]

    excluded_count = len(dropped)

    # **확정 칸의 달만 만든다.** 안 거는 달의 진입을 모아 두면 아래 순회가 그것을 쓰지
    # 않는데도 `resolve_positions` 가 도는 비용만 든다
    by_month: dict[int, _Entries] = {}
    for month in sorted({cell.month for cell in TRADING_CELLS}):
        rows = usable[usable[COL_MONTH].dt.month == month]
        entry_dates = pd.DatetimeIndex(rows[COL_DATE])
        exit_dates = pd.DatetimeIndex(rows[COL_EXIT_DATE])
        by_month[month] = _Entries(
            entry_positions=[int(position) for position in resolve_positions(trading_days, entry_dates, label="진입일")],
            exit_positions=[int(position) for position in resolve_positions(trading_days, exit_dates, label="청산일")],
            entry_dates=entry_dates,
        )

    # **로그도 요약과 같은 모집단이어야 한다** — 달 축 전체를 찍으면 바로 위에서 맞춘
    # 분모가 화면에서 다시 갈린다
    cell_entries = sum(len(entries.entry_positions) for entries in by_month.values())
    logger.debug(f"{dataset.ticker}: 확정 칸 진입 {cell_entries:,}건, 제외 {excluded_count:,}건")

    return by_month, excluded_count


def _trade_row(
    dataset: Dataset,
    frame: pd.DataFrame,
    entry_position: int,
    result: TradeResult,
    *,
    month: int,
    bet_down: bool,
    stop_display: float | str,
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
        stop_display: 산출물에 실을 손절선 표기. **여기서 만들지 않고 받는다** —
            두 표가 같은 칸에 다른 값을 실으면 조인이 안 되므로 호출부가 한 번만 만든다

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
        DISPLAY_MONTH_NUMBER: month,
        DISPLAY_DIRECTION: cell_direction(MonthEndCell(month=month, bet_down=bet_down)),
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
    worst_hold_rates: list[float] = []

    # **표기를 한 번만 만든다.** 두 표가 같은 칸에 다른 값을 실으면 조인이 안 된다 —
    # 지수 여부에서 유도되는 식이라 두 곳에 두면 한쪽만 바뀔 수 있다.
    #
    # **보유 중 최악의 가격 기준은 넘기지 않는다** — `price_column` 이 이미 그것을 말한다.
    # 지수는 종가 계열이라 장중 최저점을 알 방법이 없어 그 컬럼 하나로 재지며, 그 값은 실제로
    # 감당한 낙폭보다 **얕다.** 어느 기준으로 잰 행인지는 `손절선(%)` 의 `손절불가` 표기가 말한다
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
                dataset, frame, entry_position, result, month=month, bet_down=bet_down, stop_display=stop_display
            )
        )
        returns.append(result.return_rate)
        hold_days.append(result.hold_days)
        reasons.append(result.reason)
        worst_hold_rates.append(result.worst_hold_rate)

    identity = {
        DISPLAY_TICKER: dataset.label,
        DISPLAY_MONTH_NUMBER: month,
        DISPLAY_DIRECTION: cell_direction(MonthEndCell(month=month, bet_down=bet_down)),
        DISPLAY_STOP_LEVEL: stop_display,
    }

    # 성적 산식은 `periods` 가 소유한다. 구간 5개와 갭손절 집계가 여기서 나온다.
    # **제외 건수는 넘기지 않는다** — 성적표에서 그 컬럼을 걷어냈고 자리는 `summary.json` 의
    # `rule` 하나다. 표본을 줄이는 처리는 몇 건이 왜 빠졌는지 함께 내야 하므로
    # (패키지 절대 원칙 「표본 보존」) **요약에는 반드시 남는다**
    for row in period_rows(
        entries.entry_dates,
        returns,
        last_day=last_day,
        # **판정은 살 수 있는 1배 롱에만 건다.** 지수와 인버스 실물은 성적만 내고 「판정 안 함」이다 —
        # 그 성질은 대상 자신이 답한다 (`Dataset.is_judged`)
        tradable=dataset.is_judged,
        hold_days=hold_days,
        reasons=reasons,
        worst_hold_rates=worst_hold_rates,
    ):
        accumulator.performance.append({**identity, **row})


def run_month_end_trading(
    datasets: tuple[Dataset, ...] = DATASETS_TRADING,
    *,
    stop_levels: tuple[float | None, ...] = MONTH_END_STOP_DEFAULT,
    from_year: int | None = None,
) -> TradingOutputs:
    """월말 매매의 확정 칸 성적을 낸다.

    **확정 칸 × 확정 손절선**만 돈다 (2026-09-21 사용자 결정). 전에는 12개월 × 두 방향 ×
    격자 9종을 전부 냈는데, 사용자가 실제로 거는 것만 남기기로 정했다.

    [중요] **코드가 칸을 고르는 것이 아니다.** 목록은 `docs/매매/월말_진입/규칙.md` §3 의
    결론을 옮겨 적은 것이고, **재수집하면 성적표를 보고 다시 판단해야 한다** —
    시세가 늘면 성적이 바뀌는데 이 목록은 따라오지 않는다.

    Args:
        datasets: 대상 목록. 기본값은 **인버스를 뺀 여섯**(`DATASETS_TRADING`)이다 —
            성적표는 사용자가 판단하는 표인데 인버스는 1배의 부호를 뒤집은 값과 차이가 잡음이라
            같은 베팅이 두 줄로 실린다. **확정 전 교차검증이 필요하면 `--ticker` 로 지목한다** —
            어긋나는 칸이 곧 분배락이 걸린 칸이다.
            **지수도 받는다** — 다만 장중 손절에 고가·저가가 필요하므로 지수는 한 줄로
            강등되고 `손절선(%)` 에 「손절불가」로 적힌다
        stop_levels: 손절선 목록 (비율). **`None` 이 무손절 행이고 호출 측이 목록에 넣는다** —
            기본값은 확정 손절선 하나뿐이고 `MONTH_END_STOP_GRID` 가 무손절 + 격자 전부다.
            **값을 하나씩 받는 인자가 아니다** — 그러면 「성과가 좋아지는 값을 찾아 돌리기」가 된다
        from_year: 이 연도의 진입부터 잰다 (포함). `None` 이면 전 기간이다.
            **성과가 좋아지는 값을 찾는 노브가 아니라 미리 정한 구간을 대조하는 축이며**,
            쓴 값은 `summary.json` 에 남는다

    Returns:
        체결 원자료와 손절선 격자 성적표

    Raises:
        ValueError: 대상 목록이나 손절선이 비어 있거나, 어떤 대상의 진입이 하나도 없는 경우
    """
    if not datasets:
        raise ValueError("검증 대상이 하나도 없습니다")
    if not stop_levels:
        raise ValueError("손절선 목록이 비어 있습니다")

    accumulator = _Accumulator()
    dataset_records: list[dict[str, Any]] = []
    target_records: list[dict[str, Any]] = []

    # **무손절을 여기서 붙이지 않는다.** 기본 실행은 확정 손절선 하나만 내고, 그 대가로
    # 「손절이 무엇을 막았는가」의 수치는 `docs/매매/월말_진입/규칙.md` §2 가 갖는다 —
    # 그것이 손절선 축을 좁히도록 허용한 세 조건 중 하나다 (`.claude/rules/trading.md`)
    etf_levels: tuple[float | None, ...] = stop_levels

    # **지수는 한 줄뿐이고 「손절불가」로 적힌다.** 장중 손절에는 고가·저가가 필요한데 지수는 종가만 있고
    # (`docs/매매/월말_진입/설계.md` §7.6), 종가로 근사하면 실제보다 손절이 덜 걸려
    # 성적이 좋아진다. 거부하지 않고 강등하는 것은 **30년 축을 성적표에서 보기 위해서**다
    index_levels: tuple[float | None, ...] = (None,)

    for dataset in datasets:
        frame = load_series_csv(dataset.path) if dataset.is_index else load_market_csv(dataset.path)
        last_day = pd.Timestamp(frame[COL_DATE].iloc[-1])
        by_month, excluded_count = _collect_entries(dataset, frame, from_year=from_year)
        levels = index_levels if dataset.is_index else etf_levels

        # **진입이 하나도 없으면 조용히 넘어가지 않는다.** 표본 0 인 칸도 행을 남기는 것이
        # 규칙이라(측정의 원칙 17) 그대로 두면 **0 으로 가득 찬 그럴듯한 성적표**가 나오고,
        # 사용자는 필터를 잘못 줬거나 시세가 짧다는 것을 알아채지 못한다.
        #
        # **원인을 지어내지 않는다** — 필터를 안 걸었는데 「시작 연도 None 이후」라고 적으면
        # 쓰지도 않은 인자를 가리키게 된다. 필터가 있을 때만 그 사실을 덧붙인다
        entry_count = sum(len(entries.entry_positions) for entries in by_month.values())
        if not entry_count:
            scope = f" (시작 연도 {from_year} 이후)" if from_year is not None else ""
            raise ValueError(f"{dataset.label}: 진입이 하나도 없습니다{scope}")

        for cell in TRADING_CELLS:
            for stop_level in levels:
                _run_cell(
                    dataset,
                    frame,
                    by_month[cell.month],
                    accumulator,
                    month=cell.month,
                    bet_down=cell.bet_down,
                    stop_level=stop_level,
                    last_day=last_day,
                )

        dataset_records.append(
            dataset_record(ticker=dataset.ticker, label=dataset.label, file=dataset.path.name, frame=frame)
        )
        # **제외 건수를 대상마다 남긴다** (패키지 절대 원칙 「표본 보존」)
        target_records.append(
            {
                KEY_LABEL: dataset.label,
                KEY_ENTRY_COUNT: entry_count,
                KEY_EXCLUDED_COUNT: excluded_count,
            }
        )

    trades = pd.DataFrame(accumulator.trades)
    performance = to_summary_frame(accumulator.performance)

    # **성적표에 실제로 나온 값을 적는다.** ETF 격자를 그대로 적으면 지수만 고른 실행
    # (`--ticker 2203`)에서 돌지도 않은 손절선을 적게 되고, 특히 `무손절` 은 **지수 행이
    # 가질 수 없는 값**이라 요약과 CSV 가 어긋난다. 표에서 뽑으면 어긋날 수가 없다
    stop_levels_run = list(dict.fromkeys(performance[DISPLAY_STOP_LEVEL]))

    notes = [NOTE_ENTRY, NOTE_STOP_BASE, NOTE_INDEX]
    if from_year is not None:
        notes.append(NOTE_FROM_YEAR)

    summary = build_run_summary(
        track=TRACK_NAME,
        datasets=dataset_records,
        rule={
            KEY_CELLS: [
                {KEY_CELL_MONTH: cell.month, KEY_CELL_DIRECTION: cell_direction(cell)} for cell in TRADING_CELLS
            ],
            KEY_STOP_LEVELS: stop_levels_run,
            # **안 걸렀으면 `None` 을 그대로 남긴다.** 데이터 시작 연도 같은 값으로 채우면
            # 「걸렀다」와 「안 걸렀다」가 구별되지 않는다
            KEY_FROM_YEAR: from_year,
            KEY_TARGETS: target_records,
        },
        row_counts={
            TRADES_FILENAME: len(trades),
            SUMMARY_FILENAME: len(performance),
        },
        notes=notes,
    )

    logger.debug(f"손절 격자 완료: 체결 {len(trades):,}행, 성적 {len(performance):,}행")

    return TradingOutputs(trades=trades, performance=performance, summary=summary)


__all__ = ["KEY_FROM_YEAR", "TradingOutputs", "run_month_end_trading"]
