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

**인자는 사양서 §12 의 검사 범위로 제한한다.** 성과가 좋아지는 값을 찾는 연속 노브가 아니라
결론이 뒤집히는지 보는 대조 축이다.

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

from verify_lab.report.constants import PERCENT_DECIMALS, RATE_TO_PERCENT
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.strategy.grid.constants import (
    ALLOCATION_SPREAD_CHOICES,
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
from verify_lab.strategy.grid.paths.base import CostConfig
from verify_lab.strategy.grid.runner import (
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

# 실행 조건 표의 컬럼 정의 (컬럼명, 폭, 정렬)
SETTING_COLUMNS = [("항목", 16, Align.LEFT), ("값", 24, Align.RIGHT)]

# 결과 표의 컬럼 정의
RESULT_COLUMNS = [("항목", 22, Align.LEFT), ("값", 24, Align.RIGHT)]

# 산출물 표의 컬럼 정의
OUTPUT_COLUMNS = [("파일", 16, Align.LEFT), ("행", 10, Align.RIGHT)]


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

    directory = create_run_directory(STRATEGY_NAME)
    save_table(directory, DAILY_FILENAME, outputs.daily)
    if not outputs.trades.empty:
        save_table(directory, TRADES_FILENAME, outputs.trades)
    save_run_summary(directory, outputs.meta)

    counts = outputs.meta[KEY_ROW_COUNTS]
    TableLogger(OUTPUT_COLUMNS, logger).print_table(
        [[DAILY_FILENAME, f"{counts[KEY_DAILY]:,}"], [TRADES_FILENAME, f"{counts[KEY_TRADES]:,}"]],
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
