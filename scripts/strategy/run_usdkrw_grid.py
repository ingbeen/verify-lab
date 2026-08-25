#!/usr/bin/env python3
"""원달러 그리드 실행 CLI

고정 격자 위에서 하향 돌파로 사고 한 칸 위에서 파는 규칙을 **환전 경로 단독**으로 돌린다.
확정 설계는 `docs/spec/usdkrw_grid.md` §4 가 SoT이며, 규칙 본문은
`docs/spec/usdkrw_grid_rules.md` 이되 §4 가 바꾼 부분은 §4 가 이긴다.

**거래비용까지만 반영된 결과다.** 환전 스프레드와 슬리피지는 붙었지만 **달러 RP·원화 파킹
이자와 세금은 아직 없다.** 사양서 §17.1 이 대기자금 이자를 가장 큰 수익원으로 잡았으므로,
지금 곡선은 그리드 매매의 기여분에서 거래비용을 뺀 것까지만 담고 있다.

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
    DEFAULT_EXCHANGE_SPREAD_RATE,
    DEFAULT_GROWTH_RATE,
    DEFAULT_LOOKBACK_YEARS,
    DEFAULT_MIN_RANGE_WIDTH,
    DEFAULT_SLIPPAGE_RATE,
    DEFAULT_SLOT_CAP_RATIO,
    EXCHANGE_SPREAD_RATE_CHOICES,
    GROWTH_RATE_CHOICES,
    INITIAL_CAPITAL,
    LOOKBACK_YEAR_CHOICES,
    MIN_RANGE_WIDTH_CHOICES,
    SLOT_CAP_RATIO_CHOICES,
    STRATEGY_NAME,
    TRADING_START_DATE,
)
from verify_lab.strategy.grid.engine import GridConfig
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
    parser = argparse.ArgumentParser(description="원달러 그리드 백테스트 (환전 경로 단독, 거래비용 반영 · 이자·세금 미반영)")
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

    return parser


def _print_settings(config: GridConfig) -> None:
    """적용한 설정을 먼저 보여준다.

    Args:
        config: 실행 파라미터
    """
    rows = [
        ["룩백 N", f"{config.lookback_years}년 (월 {config.lookback_years * 12}개)"],
        ["익절폭 g", f"{config.growth_rate * RATE_TO_PERCENT:.2f}%"],
        ["최소 범위폭", f"{config.min_range_width * RATE_TO_PERCENT:.0f}%"],
        ["자금 차등", f"±{config.allocation_spread:.1f}"],
        ["슬롯 상한", f"{config.slot_cap_ratio * RATE_TO_PERCENT:.0f}%"],
        ["초기 자본금", f"{config.initial_capital:,.0f}원"],
        ["매매 시작", TRADING_START_DATE],
        ["환전 스프레드", f"편도 {config.cost.exchange_spread_rate * RATE_TO_PERCENT:.3f}%"],
        ["슬리피지", f"편도 {config.cost.slippage_rate * RATE_TO_PERCENT:.3f}%"],
        ["왕복 비용", f"{2 * (config.cost.exchange_spread_rate + config.cost.slippage_rate) * RATE_TO_PERCENT:.3f}%"],
    ]
    TableLogger(SETTING_COLUMNS, logger).print_table(rows, title="실행 조건")
    logger.debug("이자와 세금은 아직 반영되지 않았다 — 대기자금 이자가 붙으면 곡선의 성격이 달라진다")


def _print_result(outputs: GridOutputs) -> None:
    """실행 결과를 표로 보여준다.

    Args:
        outputs: 실행 산출물
    """
    period = outputs.meta[KEY_PERIOD]
    result = outputs.meta[KEY_RESULT]
    share = result["grid_excess_share_of_realized"]

    rows = [
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
        ["이탈 보너스 합계", f"{result['grid_excess_total']:,.0f}원"],
        ["이탈 보너스 비중", "계산 불가" if share is None else f"{share * RATE_TO_PERCENT:.{PERCENT_DECIMALS}f}%"],
        ["미청산 평가손익", f"{result['open_unrealised']:,.0f}원"],
        ["활성 레벨 min~max", f"{result['active_levels_min']}~{result['active_levels_max']}개"],
        ["보유 슬롯 최대", f"{result['held_slots_max']}개"],
        ["자금 부족일", f"{result['blocked_days']:,}일"],
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
        cost=CostConfig(exchange_spread_rate=args.exchange_spread, slippage_rate=DEFAULT_SLIPPAGE_RATE),
    )

    _print_settings(config)
    outputs = run_usdkrw_grid(config)
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
