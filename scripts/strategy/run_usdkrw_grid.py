#!/usr/bin/env python3
"""원달러 그리드 실행 CLI

고정 격자 위에서 하향 돌파로 사고 한 칸 위에서 파는 규칙을 돌린다.
확정 설계는 `docs/spec/usdkrw_grid.md` §4 가 SoT이며, 규칙 본문은
`docs/spec/usdkrw_grid_rules.md` 이되 §4 가 바꾼 부분은 §4 가 이긴다.

**한 번에 한 경로·한 하단 이탈 대응을 돌린다.** 격자·범위·판정은 언제나 원달러 종가이고,
경로가 바꾸는 것은 집행 가격·비용·세금·보유 이자뿐이다. 거래비용과 이자·세금이 모두 반영돼 있다.

**하단 이탈 A·B 는 파라미터가 아니라 설계 대안이다.** 사양서 §7 이 둘 다 실행해 비교하라고
규정했으므로 하나를 고르지 않는다 — `--lower-breach` 로 갈라 두 번 돌리고 나란히 놓는다.

**ETF 는 2016-12-27 상장이라 환전 경로와 기간이 다르다.** 그냥 견주면 순위가 기간에서 나온 건지
경로에서 나온 건지 알 수 없으므로, `--start-date` 로 **같은 시작일의 대조군**을 만들어 비교한다.

**벤치마크 3종을 매 실행에 병기한다** (사양서 §13.3). 질문은 "이기는가"가 아니라
**"얼마나 자주 지고, 질 때 얼마나 지는가"** 이며, 그중 **「분할매수 후 보유」가 판정**이다 —
못 이기면 §13.3 은 익절 로직을 제거하는 것이 맞다고 적었다.

**인자는 사양서 §12 의 검사 범위로 제한한다.** 성과가 좋아지는 값을 찾는 연속 노브가 아니라
결론이 뒤집히는지 보는 대조 축이다.

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

from verify_lab.report.constants import PERCENT_DECIMALS, RATE_TO_PERCENT
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.strategy.grid.constants import (
    ALLOCATION_SPREAD_CHOICES,
    BENCHMARK_SPLIT_BUY_HOLD,
    DEFAULT_ALLOCATION_SPREAD,
    DEFAULT_BROKERAGE_RATE,
    DEFAULT_EXCHANGE_SPREAD_RATE,
    DEFAULT_GROWTH_RATE,
    DEFAULT_LOOKBACK_YEARS,
    DEFAULT_LOWER_BREACH,
    DEFAULT_MIN_RANGE_WIDTH,
    DEFAULT_PARKING_FLOOR_RATE,
    DEFAULT_RP_FLOOR_RATE,
    DEFAULT_SLIPPAGE_RATE,
    DEFAULT_SLOT_CAP_RATIO,
    DISPLAY_STRATEGY,
    EXCHANGE_SPREAD_RATE_CHOICES,
    GROWTH_RATE_CHOICES,
    INITIAL_CAPITAL,
    INTEREST_TAX_RATE,
    LOOKBACK_YEAR_CHOICES,
    LOWER_BREACH_CHOICES,
    LOWER_BREACH_EXTEND,
    MIN_RANGE_WIDTH_CHOICES,
    PARKING_FLOOR_RATE_CHOICES,
    PATH_CHOICES,
    PATH_EXCHANGE,
    PATH_START_DATES,
    RP_FLOOR_RATE_CHOICES,
    SLOT_CAP_RATIO_CHOICES,
    STRATEGY_NAME,
)
from verify_lab.strategy.grid.engine import GridConfig
from verify_lab.strategy.grid.interest import InterestConfig
from verify_lab.strategy.grid.metrics import red_flags
from verify_lab.strategy.grid.paths.base import CostConfig
from verify_lab.strategy.grid.runner import (
    KEY_CURVES,
    KEY_DAILY,
    KEY_PERIOD,
    KEY_RESULT,
    KEY_ROW_COUNTS,
    KEY_TRADES,
    GridOutputs,
    run_usdkrw_grid,
)
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_USDKRW_GRID = "usdkrw_grid_strategy"

# 산출물 파일 이름
DAILY_FILENAME = "daily.csv"
TRADES_FILENAME = "trades.csv"
CURVES_FILENAME = "benchmarks.csv"

# 실행 조건 표의 컬럼 정의 (컬럼명, 폭, 정렬)
SETTING_COLUMNS = [("항목", 16, Align.LEFT), ("값", 24, Align.RIGHT)]

# 결과 표의 컬럼 정의
RESULT_COLUMNS = [("항목", 22, Align.LEFT), ("값", 24, Align.RIGHT)]

# 산출물 표의 컬럼 정의
OUTPUT_COLUMNS = [("파일", 16, Align.LEFT), ("행", 10, Align.RIGHT)]

# 성과 지표 표의 컬럼 정의
METRIC_COLUMNS = [("지표", 22, Align.LEFT), ("값", 24, Align.RIGHT)]

# 사양서 §15.3 판정 표의 컬럼 정의
FLAG_COLUMNS = [("징후", 34, Align.LEFT), ("판정", 10, Align.LEFT), ("근거", 46, Align.LEFT)]

# 사양서 §13.3 벤치마크 표의 컬럼 정의
BENCHMARK_COLUMNS = [
    ("기준", 18, Align.LEFT),
    ("확인 목적", 20, Align.LEFT),
    ("종료 총자산", 18, Align.RIGHT),
    ("총수익률", 11, Align.RIGHT),
    ("CAGR", 9, Align.RIGHT),
    ("MDD", 9, Align.RIGHT),
    ("Sharpe", 8, Align.RIGHT),
    ("전략 − 기준", 16, Align.RIGHT),
]

# 사양서 §13.3 판정 표의 컬럼 정의. 판정 문장이 길어 값 칸을 넓게 잡는다
VERDICT_COLUMNS = [("항목", 24, Align.LEFT), ("값", 44, Align.RIGHT)]

# 전략 행에는 목적도 차이도 없다. 비워 두는 대신 그렇게 적는다
NOT_APPLICABLE = "—"


def _optional(value: float | None, template: str) -> str:
    """계산 불가를 숨기지 않고 그대로 표시한다.

    Args:
        value: 지표 값이거나 `None`
        template: 값이 있을 때 쓸 포맷 문자열

    Returns:
        표시 문자열
    """
    return "계산 불가" if value is None else template.format(value)


def _print_metrics(outputs: GridOutputs) -> None:
    """사양서 §13 의 지표를 표로 보여준다.

    Args:
        outputs: 실행 산출물
    """
    performance = outputs.performance
    grid = outputs.grid_metrics

    rows = [
        ["총수익률", f"{performance.total_return_rate * RATE_TO_PERCENT:+.{PERCENT_DECIMALS}f}%"],
        ["CAGR", f"{performance.cagr * RATE_TO_PERCENT:+.{PERCENT_DECIMALS}f}%"],
        ["MDD", f"{performance.max_drawdown * RATE_TO_PERCENT:.{PERCENT_DECIMALS}f}%"],
        ["└ 최저점 / 신고점", f"{performance.max_drawdown_date.date()} / {performance.peak_date.date()}"],
        ["Calmar", _optional(performance.calmar, "{:.3f}")],
        ["변동성 (연환산)", _optional(performance.volatility, "{:.4%}")],
        ["Sharpe", _optional(performance.sharpe, "{:.3f}")],
        ["Sortino", _optional(performance.sortino, "{:.3f}")],
        ["무위험 수익률 평균", f"연 {performance.risk_free_mean:.3f}%"],
        ["└ 그대로 굴렸다면", f"{performance.risk_free_return_rate * RATE_TO_PERCENT:+.{PERCENT_DECIMALS}f}%"],
        ["최장 보유", _optional(grid.hold_days_max, "{:,.0f}일")],
        [
            "└ 평균 / 중앙값",
            f"{_optional(grid.hold_days_mean, '{:,.1f}')}일 / {_optional(grid.hold_days_median, '{:,.1f}')}일",
        ],
        ["└ 미청산 최장", _optional(grid.open_hold_days_max, "{:,.0f}일")],
        ["회전 전체 / 슬롯당", f"{grid.turnover_per_year:.2f}회/년 / {_optional(grid.turnover_per_slot_per_year, '{:.2f}회/년')}"],
        ["평균 투입률 / 현금", f"{grid.deployment_mean:.2%} / {grid.cash_ratio_mean:.2%}"],
        ["일일 최대 투입", f"{grid.daily_deploy_max:.2%} ({grid.daily_deploy_max_date.date()})"],
        ["하루 3건 이상 매수", f"{grid.multi_fill_days:,}일"],
        ["자금 소진율", f"{grid.blocked_day_ratio:.2%} ({grid.blocked_days:,}일)"],
        ["최대 미실현 손실", _optional(grid.unrealised_worst_rate, "{:.2%}")],
        ["이탈 보너스 / 총수익", _optional(grid.grid_excess_share_of_total_return, "{:.2%}")],
        [
            "└ 실현손익 / 매매기여",
            f"{_optional(grid.grid_excess_share_of_realized, '{:.2%}')} / {_optional(grid.grid_excess_share_of_trading, '{:.2%}')}",
        ],
        ["세후 이자 / 매매 기여", f"{grid.interest_after_tax:,.0f}원 / {grid.trading_return:,.0f}원"],
        ["하단 이탈", f"{grid.breach_days:,}일 / {grid.breach_episodes}구간 / 최장 {grid.breach_days_max_run:,}일"],
        ["└ 최대 깊이", _optional(grid.breach_depth_max, "{:.3%}")],
        ["상한 발동", f"{grid.capped_days:,}일"],
        [
            "재조정 범위 변화 하단",
            f"중앙 {_optional(grid.range_low_shift_median, '{:.2%}')} / 최대 {_optional(grid.range_low_shift_max, '{:.2%}')}",
        ],
        [
            "└ 상단",
            f"중앙 {_optional(grid.range_high_shift_median, '{:.2%}')} / 최대 {_optional(grid.range_high_shift_max, '{:.2%}')}",
        ],
    ]
    TableLogger(METRIC_COLUMNS, logger).print_table(rows, title="성과 지표 (사양서 §13)")


def _print_red_flags(outputs: GridOutputs) -> None:
    """사양서 §15.3 의 징후를 전부 판정해 보여준다.

    **판정할 수 없는 항목도 남긴다** — 빼 버리면 검사한 것과 구분되지 않는다.

    Args:
        outputs: 실행 산출물
    """
    verdicts = {True: "걸림", False: "통과", None: "판정 불가"}
    rows = [
        [flag.name, verdicts[flag.triggered], flag.detail]
        for flag in red_flags(outputs.performance, outputs.grid_metrics)
    ]
    TableLogger(FLAG_COLUMNS, logger).print_table(rows, title="Red Flag 판정 (사양서 §15.3)")


def _print_benchmarks(outputs: GridOutputs) -> None:
    """사양서 §13.3 의 벤치마크 3종을 전략과 나란히 보여준다.

    **질문은 「이기는가」가 아니다.** §13.3 이 "얼마나 자주 지고, 질 때 얼마나 지는가" 로 적었으므로
    승패가 아니라 **차이의 금액**을 함께 싣는다.

    Args:
        outputs: 실행 산출물
    """
    performance = outputs.performance
    rows = [
        [
            DISPLAY_STRATEGY,
            NOT_APPLICABLE,
            f"{performance.last_value:,.0f}원",
            f"{performance.total_return_rate * RATE_TO_PERCENT:+.{PERCENT_DECIMALS}f}%",
            f"{performance.cagr * RATE_TO_PERCENT:+.{PERCENT_DECIMALS}f}%",
            f"{performance.max_drawdown * RATE_TO_PERCENT:.{PERCENT_DECIMALS}f}%",
            _optional(performance.sharpe, "{:.3f}"),
            NOT_APPLICABLE,
        ]
    ]
    rows.extend(
        [
            benchmark.name,
            benchmark.purpose,
            f"{benchmark.performance.last_value:,.0f}원",
            f"{benchmark.performance.total_return_rate * RATE_TO_PERCENT:+.{PERCENT_DECIMALS}f}%",
            f"{benchmark.performance.cagr * RATE_TO_PERCENT:+.{PERCENT_DECIMALS}f}%",
            f"{benchmark.performance.max_drawdown * RATE_TO_PERCENT:.{PERCENT_DECIMALS}f}%",
            _optional(benchmark.performance.sharpe, "{:.3f}"),
            f"{performance.last_value - benchmark.performance.last_value:+,.0f}원",
        ]
        for benchmark in outputs.benchmarks
    )
    TableLogger(BENCHMARK_COLUMNS, logger).print_table(rows, title="벤치마크 (사양서 §13.3)")


def _print_verdict(outputs: GridOutputs) -> None:
    """사양서 §13.3 의 판정을 보여준다.

    **「분할매수 후 보유」가 판정이다.** §13.3 이 "여기서 못 이기면 익절 로직을 제거하는 것이
    맞다" 고 적었으므로, 그 한 줄을 결과에서 감추지 않는다.

    Args:
        outputs: 실행 산출물
    """
    split = next(
        (benchmark for benchmark in outputs.benchmarks if benchmark.key == BENCHMARK_SPLIT_BUY_HOLD),
        None,
    )
    if split is None:
        return

    contribution = outputs.performance.last_value - split.performance.last_value
    rows = [
        ["익절 로직의 순수 기여", f"{contribution:+,.0f}원"],
        ["└ 전략 / 벤치마크", f"{outputs.performance.last_value:,.0f}원 / {split.performance.last_value:,.0f}원"],
        [
            "판정",
            "그리드가 이긴다" if contribution > 0 else "못 이긴다 — §13.3 은 익절 로직 제거를 권한다",
        ],
        [
            "벤치마크 자금 소진율",
            f"{_detail(split.detail.get('blocked_day_ratio'), '{:.2%}')}"
            f" ({_detail(split.detail.get('blocked_days'), '{:,}일')})",
        ],
        [
            "└ 최장 보유 / 투입률",
            f"{_detail(split.detail.get('hold_days_max'), '{:,}일')}"
            f" / {_detail(split.detail.get('deployment_mean'), '{:.2%}')}",
        ],
    ]
    TableLogger(VERDICT_COLUMNS, logger).print_table(rows, title="§13.3 판정 — 익절 로직의 순수 기여")


def _detail(value: float | int | str | None, template: str) -> str:
    """벤치마크 부가 사실을 표시 문자열로 바꾼다. 계산 불가는 그대로 적는다.

    체결이 한 건도 없으면 보유기간이 `None` 이다 (결정 C91). 그때 `0일` 로 적으면
    **"하루 만에 판다"로 읽히므로** 값이 없다는 사실을 그대로 남긴다.

    Args:
        value: 부가 사실의 값이거나 `None`
        template: 값이 있을 때 쓸 포맷 문자열

    Returns:
        표시 문자열
    """
    return "계산 불가" if value is None else template.format(value)


def _build_parser() -> argparse.ArgumentParser:
    """명령행 인자 파서를 만든다.

    Returns:
        인자 파서
    """
    parser = argparse.ArgumentParser(description="원달러 그리드 백테스트 (경로 하나씩, 거래비용·이자·세금 반영)")
    parser.add_argument(
        "--path",
        default=PATH_EXCHANGE,
        choices=PATH_CHOICES,
        help="집행 경로. 격자·판정은 어느 경로든 원달러 종가로 한다",
    )
    parser.add_argument(
        "--lower-breach",
        default=DEFAULT_LOWER_BREACH,
        choices=LOWER_BREACH_CHOICES,
        help="하단 이탈 대응. A 는 하단을 유지하고 B 는 격자를 아래로 연장한다. 설계 대안이라 둘 다 돌려 견준다",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="매매 시작일 (YYYY-MM-DD). 생략하면 경로의 기본값. 기간을 맞춘 대조군을 만들 때 쓴다",
    )
    parser.add_argument(
        "--lookback-years",
        type=int,
        default=DEFAULT_LOOKBACK_YEARS,
        choices=LOOKBACK_YEAR_CHOICES,
        help="범위 산출에 쓰는 룩백 N (년)",
    )
    parser.add_argument(
        "--growth-rate",
        type=float,
        default=DEFAULT_GROWTH_RATE,
        choices=GROWTH_RATE_CHOICES,
        help="익절폭 g (비율). 격자 자체를 바꾸므로 값마다 독립 실행이다",
    )
    parser.add_argument(
        "--min-range-width",
        type=float,
        default=DEFAULT_MIN_RANGE_WIDTH,
        choices=MIN_RANGE_WIDTH_CHOICES,
        help="최소 범위폭 (비율)",
    )
    parser.add_argument(
        "--allocation-spread",
        type=float,
        default=DEFAULT_ALLOCATION_SPREAD,
        choices=ALLOCATION_SPREAD_CHOICES,
        help="3구간 자금 차등 폭 (비율)",
    )
    parser.add_argument(
        "--slot-cap-ratio",
        type=float,
        default=DEFAULT_SLOT_CAP_RATIO,
        choices=SLOT_CAP_RATIO_CHOICES,
        help="슬롯 상한 (총자산 대비 비율)",
    )
    parser.add_argument(
        "--exchange-spread",
        type=float,
        default=DEFAULT_EXCHANGE_SPREAD_RATE,
        choices=EXCHANGE_SPREAD_RATE_CHOICES,
        help="환전 스프레드 편도 (비율). 결론이 스프레드 가정에 의존하는지 보는 축이다",
    )
    parser.add_argument(
        "--rp-floor",
        type=float,
        default=DEFAULT_RP_FLOOR_RATE,
        choices=RP_FLOOR_RATE_CHOICES,
        help="달러 RP 금리의 하한 (연%%). 절반 가까운 날을 이 값이 정한다",
    )
    parser.add_argument(
        "--parking-floor",
        type=float,
        default=DEFAULT_PARKING_FLOOR_RATE,
        choices=PARKING_FLOOR_RATE_CHOICES,
        help="원화 파킹 금리의 하한 (연%%)",
    )

    return parser


def _print_settings(config: GridConfig, *, path_name: str, start_date: str, lower_breach: str) -> None:
    """적용한 설정을 먼저 보여준다.

    Args:
        config: 실행 파라미터
        path_name: 집행 경로 이름
        start_date: 매매 시작일
        lower_breach: 하단 이탈 대응
    """
    rows = [
        ["집행 경로", path_name],
        ["하단 이탈", f"{lower_breach}안 ({'격자 아래 연장' if lower_breach == LOWER_BREACH_EXTEND else '하단 유지·매수 중단'})"],
        ["룩백 N", f"{config.lookback_years}년 (월 {config.lookback_years * 12}개)"],
        ["익절폭 g", f"{config.growth_rate * RATE_TO_PERCENT:.2f}%"],
        ["최소 범위폭", f"{config.min_range_width * RATE_TO_PERCENT:.0f}%"],
        ["자금 차등", f"±{config.allocation_spread:.1f}"],
        ["슬롯 상한", f"{config.slot_cap_ratio * RATE_TO_PERCENT:.0f}%"],
        ["초기 자본금", f"{config.initial_capital:,.0f}원"],
        ["매매 시작", start_date],
        ["환전 스프레드", f"편도 {config.cost.exchange_spread_rate * RATE_TO_PERCENT:.3f}%"],
        ["위탁수수료", f"편도 {config.cost.brokerage_rate * RATE_TO_PERCENT:.3f}%"],
        ["슬리피지", f"편도 {config.cost.slippage_rate * RATE_TO_PERCENT:.3f}%"],
        ["RP 하한", f"연 {config.interest.rp_floor_rate:.2f}%"],
        ["파킹 하한", f"연 {config.interest.parking_floor_rate:.2f}%"],
        ["이자 원천징수", f"{INTEREST_TAX_RATE * RATE_TO_PERCENT:.1f}%"],
    ]
    TableLogger(SETTING_COLUMNS, logger).print_table(rows, title="실행 조건")


def _print_result(outputs: GridOutputs) -> None:
    """실행 결과를 표로 보여준다.

    Args:
        outputs: 실행 산출물
    """
    period = outputs.meta[KEY_PERIOD]
    result = outputs.meta[KEY_RESULT]
    share = result["grid_excess_share_of_realized"]

    unrealised = result["unrealised_rate_at_first_block"]

    rows = [
        ["집행 경로", outputs.meta["parameters"]["path"]],
        ["하단 이탈", f"{outputs.meta['parameters']['lower_breach']}안"],
        ["기간", f"{period['first_date']} ~ {period['last_date']}"],
        ["거래일 / 재조정", f"{period['trading_days']:,}일 / {period['rebalance_count']:,}회"],
        ["시작 총자산", f"{result['first_total_assets']:,.0f}원"],
        ["종료 총자산", f"{result['last_total_assets']:,.0f}원"],
        ["총수익률", f"{result['total_return_rate'] * RATE_TO_PERCENT:+.{PERCENT_DECIMALS}f}%"],
        ["매수 / 매도 체결", f"{result['buy_fills']:,}건 / {result['sell_fills']:,}건"],
        ["청산 완료 / 미청산", f"{result['closed_trades']:,}건 / {result['open_slots']:,}건"],
        ["실현손익 합계", f"{result['realized_total']:,.0f}원"],
        ["거래비용 합계", f"{result['cost_total']:,.0f}원"],
        ["└ 매수 / 매도", f"{result['buy_cost_total']:,.0f}원 / {result['sell_cost_total']:,.0f}원"],
        ["이자 합계 (세전)", f"{result['interest_total']:,.0f}원"],
        ["└ RP / 파킹", f"{result['rp_interest_total']:,.0f}원 / {result['parking_interest_total']:,.0f}원"],
        ["└ 평균 금리", f"연 {result['rp_rate_mean']:.3f}% / {result['parking_rate_mean']:.3f}%"],
        ["이자 원천징수", f"{result['tax_paid_total']:,.0f}원"],
        ["매매 차익 과세", f"{result['gain_tax_total']:,.0f}원"],
        ["미인출 이자 (세전)", f"{result['open_accrued_interest']:,.0f}원"],
        ["금리 이월일 (RP/파킹)", f"{result['rp_rate_filled_days']:,}일 / {result['parking_rate_filled_days']:,}일"],
        ["이탈 보너스 합계", f"{result['grid_excess_total']:,.0f}원"],
        ["이탈 보너스 비중", "계산 불가" if share is None else f"{share * RATE_TO_PERCENT:.{PERCENT_DECIMALS}f}%"],
        ["미청산 평가손익", f"{result['open_unrealised']:,.0f}원"],
        ["활성 레벨 min~max", f"{result['active_levels_min']}~{result['active_levels_max']}개"],
        ["보유 슬롯 최대", f"{result['held_slots_max']}개"],
        ["자금 부족일", f"{result['blocked_days']:,}일"],
        ["첫 자금 부족일", result["first_blocked_date"] or "없음"],
        [
            "그때 미실현 손익률",
            "계산 불가" if unrealised is None else f"{unrealised * RATE_TO_PERCENT:+.{PERCENT_DECIMALS}f}%",
        ],
        ["격자 연장", f"{result['extension_days']:,}일 / 최대 {result['extension_levels_max']}칸"],
        ["평균단가", "계산 불가" if result["average_unit_cost"] is None else f"{result['average_unit_cost']:,.4f}"],
    ]
    TableLogger(RESULT_COLUMNS, logger).print_table(rows, title="실행 결과")


@cli_exception_handler
def main() -> None:
    """원달러 그리드를 실행하고 산출물을 저장한다."""
    args = _build_parser().parse_args()

    config = GridConfig(
        lookback_years=args.lookback_years,
        growth_rate=args.growth_rate,
        min_range_width=args.min_range_width,
        allocation_spread=args.allocation_spread,
        slot_cap_ratio=args.slot_cap_ratio,
        initial_capital=INITIAL_CAPITAL,
        cost=CostConfig(
            exchange_spread_rate=args.exchange_spread,
            slippage_rate=DEFAULT_SLIPPAGE_RATE,
            brokerage_rate=DEFAULT_BROKERAGE_RATE,
        ),
        interest=InterestConfig(rp_floor_rate=args.rp_floor, parking_floor_rate=args.parking_floor),
    )

    start_date = args.start_date or PATH_START_DATES[args.path]

    _print_settings(config, path_name=args.path, start_date=start_date, lower_breach=args.lower_breach)
    outputs = run_usdkrw_grid(
        config,
        path_name=args.path,
        start_date=start_date,
        lower_breach=args.lower_breach,
    )
    _print_result(outputs)
    _print_metrics(outputs)
    _print_red_flags(outputs)
    _print_benchmarks(outputs)
    _print_verdict(outputs)

    directory = create_run_directory(STRATEGY_NAME)
    save_table(directory, DAILY_FILENAME, outputs.daily)
    if not outputs.trades.empty:
        save_table(directory, TRADES_FILENAME, outputs.trades)
    save_table(directory, CURVES_FILENAME, outputs.curves)
    save_run_summary(directory, outputs.meta)

    counts = outputs.meta[KEY_ROW_COUNTS]
    TableLogger(OUTPUT_COLUMNS, logger).print_table(
        [
            [DAILY_FILENAME, f"{counts[KEY_DAILY]:,}"],
            [TRADES_FILENAME, f"{counts[KEY_TRADES]:,}"],
            [CURVES_FILENAME, f"{counts[KEY_CURVES]:,}"],
        ],
        title=f"산출물 (저장 폴더: {directory})",
    )
    save_metadata(
        KEY_META_USDKRW_GRID,
        {
            "parameters": outputs.meta["parameters"],
            "period": outputs.meta[KEY_PERIOD],
            "closed_trades": counts[KEY_TRADES],
            "output": str(directory),
        },
    )
    logger.debug(f"일별 곡선 {counts[KEY_DAILY]:,}행, 체결 {counts[KEY_TRADES]:,}건을 산출했습니다")


if __name__ == "__main__":
    main()
