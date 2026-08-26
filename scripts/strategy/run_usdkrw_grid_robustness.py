#!/usr/bin/env python3
"""원달러 그리드 견고성 검사 CLI

사양서 §12.1 의 **축별 단독 검사**와 §14 의 **분할 분석**을 한 실행에서 낸다.
확정 설계는 `docs/spec/usdkrw_grid.md` §4 가 SoT다.

**최적 조합을 찾는 것이 아니다.** §12.1 이 "전수 탐색 금지 — 6,912가지를 돌려 최고 조합을
고르면 그것이 과최적화" 라고 못 박았고, §15.1 이 「결과를 보고 파라미터 변경 금지」를 규정했다.
이 실행이 답하는 것은 하나다 — **기본 설정에서 나온 결론이 축을 옮겨도 유지되는가.**

**인자가 없다.** 사양서가 확정한 축과 구간을 전부 산출하는 것이 설계이며, 골라 돌리는 노브로 쓰면
어느 축을 안 돌렸는지가 산출물에서 보이지 않는다. 파라미터 하나를 골라 돌리려면
`run_usdkrw_grid.py` 를 쓴다.

**한 실행에서 축과 국면을 함께 내는 이유는 대조의 전제가 「같은 코드·같은 데이터」이기 때문이다.**
국면 분석이 쓰는 네 실행은 축 검사가 이미 돌린 것들이라 추가 실행이 없다.

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

from verify_lab.report.constants import PERCENT_DECIMALS, RATE_TO_PERCENT
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.strategy.grid.constants import (
    BENCHMARK_BUY_HOLD,
    BENCHMARK_KRW_PARKING,
    BENCHMARK_SPLIT_BUY_HOLD,
    EXECUTION_ETF_2X,
    EXECUTION_EXCHANGE_FULL,
    REGIME_AXIS_CONTIGUOUS,
    REGIME_AXIS_RATE_GAP,
    REGIME_AXIS_SPEC,
    ROBUSTNESS_NAME,
)
from verify_lab.strategy.grid.regimes import LONG_EPISODE_DAYS, SHORT_EPISODE_DAYS, RegimeResult
from verify_lab.strategy.grid.sweep import (
    CONCLUSION_KEYS,
    KEY_RANK,
    KEY_RATE_GAP,
    KEY_RUNS,
    KEY_VERDICTS,
    PlannedRun,
    RobustnessOutputs,
    SweepRow,
    build_axes,
    run_robustness,
)
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_ROBUSTNESS = "usdkrw_grid_robustness"

# 산출물 파일 이름
AXES_FILENAME = "axes.csv"
REGIMES_FILENAME = "regimes.csv"

# 축 비교표의 컬럼 정의 (컬럼명, 폭, 정렬)
AXIS_COLUMNS = [
    ("축값", 10, Align.LEFT),
    ("종료 총자산", 17, Align.RIGHT),
    ("총수익률", 10, Align.RIGHT),
    ("MDD", 9, Align.RIGHT),
    ("Calmar", 8, Align.RIGHT),
    ("Sharpe", 8, Align.RIGHT),
    ("투입률", 9, Align.RIGHT),
    ("전략−분할매수", 17, Align.RIGHT),
    ("전략−B&H", 17, Align.RIGHT),
    ("전략−파킹", 17, Align.RIGHT),
]

# 결론 뒤집힘 판정표. 결론 여섯 개를 가로로 늘어놓아 **축 하나가 한 줄**이 되게 한다
VERDICT_COLUMNS = [("축", 16, Align.LEFT), ("출처", 8, Align.LEFT)] + [
    (name[:14], 16, Align.LEFT) for name in CONCLUSION_KEYS
]

# 사양서 §15.3 #8 판정표
RANK_COLUMNS = [("기준", 12, Align.LEFT), ("판정", 10, Align.LEFT), ("근거", 78, Align.LEFT)]

# 국면 비교표
REGIME_COLUMNS = [
    ("구간", 26, Align.LEFT),
    ("성격", 16, Align.LEFT),
    ("거래일", 8, Align.RIGHT),
    ("전략", 10, Align.RIGHT),
    ("MDD", 9, Align.RIGHT),
    ("B&H", 10, Align.RIGHT),
    ("분할매수", 10, Align.RIGHT),
    ("파킹", 10, Align.RIGHT),
    ("전략−분할매수", 14, Align.RIGHT),
]

# 금리차 부호의 표본 구조표
RATE_GAP_COLUMNS = [
    ("부호", 12, Align.LEFT),
    ("구간 수", 9, Align.RIGHT),
    ("거래일", 9, Align.RIGHT),
    ("최장", 9, Align.RIGHT),
    (f"{SHORT_EPISODE_DAYS}일 미만", 11, Align.RIGHT),
    (f"{LONG_EPISODE_DAYS}일 이상", 11, Align.RIGHT),
]

# 산출물 표
OUTPUT_COLUMNS = [("파일", 16, Align.LEFT), ("행", 10, Align.RIGHT)]

# 판정 표기
MARK_STABLE = "안정"
MARK_FLIPPED = "뒤집힘"
MARK_UNKNOWN = "판정 불가"


def _build_parser() -> argparse.ArgumentParser:
    """인자 없는 파서를 만든다.

    **축과 구간을 골라 돌리는 인자를 두지 않는다.** 사양서 §12.1·§14 가 확정한 목록을
    전부 산출하는 것이 설계이며, 고르는 노브로 쓰면 무엇을 안 돌렸는지가 보이지 않는다.

    Returns:
        인자 파서
    """
    return argparse.ArgumentParser(
        description="원달러 그리드 견고성 검사 — 축별 단독 검사(사양서 §12.1)와 분할 분석(§14)",
        epilog="파라미터 하나를 골라 돌리려면 run_usdkrw_grid.py 를 쓴다",
    )


def _percent(value: float | None, *, sign: bool = False) -> str:
    """비율을 백분율 문자열로 바꾼다. 계산 불가는 그렇게 적는다."""
    if value is None:
        return "계산 불가"

    return f"{value * RATE_TO_PERCENT:{'+' if sign else ''}.{PERCENT_DECIMALS}f}%"


def _number(value: float | None) -> str:
    """지수형 지표를 문자열로 바꾼다."""
    return "계산 불가" if value is None else f"{value:.3f}"


def _print_plan(outputs: RobustnessOutputs) -> None:
    """무엇을 돌렸는지 먼저 보여준다.

    Args:
        outputs: 견고성 검사 산출물
    """
    axes = build_axes()
    rows = [
        [
            "검사 축",
            f"{len(axes)}개 (사양서 {sum(1 for item in axes if item.in_spec)} + 추가 {sum(1 for item in axes if not item.in_spec)})",
        ],
        ["축값 합계", f"{sum(len(item.values) for item in axes)}개"],
        ["고유 실행", f"{outputs.run_count}회"],
        ["비교표 줄", f"{len(outputs.rows)}줄 (기본 설정이 축마다 반복된다)"],
        ["국면 구간", f"{sum(len(item) for item in outputs.regimes.values()):,}줄"],
    ]
    TableLogger([("항목", 16, Align.LEFT), ("값", 44, Align.RIGHT)], logger).print_table(rows, title="실행 계획")


def _print_axes(outputs: RobustnessOutputs) -> None:
    """축마다 축값을 나란히 놓은 표를 보여준다.

    Args:
        outputs: 견고성 검사 산출물
    """
    axes = {item.key: item for item in build_axes()}
    for key, axis in axes.items():
        for execution in (EXECUTION_EXCHANGE_FULL, *axis.scope):
            rows = [item for item in outputs.rows if item.axis == key and item.execution == execution]
            source = "" if axis.in_spec else " · 사양서 §12 에 없는 추가 축"
            TableLogger(AXIS_COLUMNS, logger).print_table(
                [_axis_row(item) for item in rows],
                title=f"{axis.name} — {execution}{source}",
            )


def _axis_row(row: SweepRow) -> list[str]:
    """축 비교표의 한 줄."""
    mark = " (기본)" if row.is_default else ""

    return [
        f"{row.value_label}{mark}",
        f"{row.final_assets:,.0f}원",
        _percent(row.total_return_rate, sign=True),
        _percent(row.max_drawdown),
        _number(row.calmar),
        _number(row.sharpe),
        _percent(row.deployment_mean),
        f"{row.benchmark_gaps[BENCHMARK_SPLIT_BUY_HOLD]:+,.0f}원",
        f"{row.benchmark_gaps[BENCHMARK_BUY_HOLD]:+,.0f}원",
        f"{row.benchmark_gaps[BENCHMARK_KRW_PARKING]:+,.0f}원",
    ]


def _print_verdicts(outputs: RobustnessOutputs) -> None:
    """결론이 축을 옮겨도 유지되는지 한 표로 보여준다.

    Args:
        outputs: 견고성 검사 산출물
    """
    axes = {item.key: item for item in build_axes()}
    by_axis: dict[str, dict[str, bool | None]] = {}
    for verdict in outputs.verdicts:
        if verdict.execution == EXECUTION_EXCHANGE_FULL:
            by_axis.setdefault(verdict.axis, {})[verdict.conclusion] = verdict.stable

    rows = [
        [axes[key].name, "사양서" if axes[key].in_spec else "추가"]
        + [_mark(flags.get(conclusion)) for conclusion in CONCLUSION_KEYS]
        for key, flags in by_axis.items()
    ]
    TableLogger(VERDICT_COLUMNS, logger).print_table(rows, title=f"결론 뒤집힘 판정 — {EXECUTION_EXCHANGE_FULL}")

    flipped = [item for item in outputs.verdicts if item.execution == EXECUTION_EXCHANGE_FULL and item.stable is False]
    for verdict in flipped:
        logger.debug(f"뒤집힘: {axes[verdict.axis].name} / {verdict.conclusion} — {verdict.detail}")


def _mark(stable: bool | None) -> str:
    """판정 표기. **판정 불가를 안정으로 적지 않는다** (결정 C95)."""
    if stable is None:
        return MARK_UNKNOWN

    return MARK_STABLE if stable else MARK_FLIPPED


def _print_ranks(outputs: RobustnessOutputs) -> None:
    """사양서 §15.3 #8 판정을 보여준다.

    Args:
        outputs: 견고성 검사 산출물
    """
    rows = [
        [item.basis, MARK_UNKNOWN if item.triggered is None else ("걸림" if item.triggered else "통과"), item.detail]
        for item in outputs.ranks
    ]
    TableLogger(RANK_COLUMNS, logger).print_table(rows, title="§15.3 #8 — N 에 따라 경로 순위 변동")


def _print_regimes(outputs: RobustnessOutputs) -> None:
    """국면별 성적을 축마다 보여준다.

    Args:
        outputs: 견고성 검사 산출물
    """
    for axis, title in ((REGIME_AXIS_SPEC, "사양서 §14 축1"), (REGIME_AXIS_CONTIGUOUS, "연속 분할")):
        items = [item for item in outputs.regimes[EXECUTION_EXCHANGE_FULL] if item.regime.axis == axis]
        TableLogger(REGIME_COLUMNS, logger).print_table(
            [_regime_row(item) for item in items],
            title=f"{title} — {EXECUTION_EXCHANGE_FULL}",
        )

    for execution in (EXECUTION_EXCHANGE_FULL, EXECUTION_ETF_2X):
        TableLogger(RATE_GAP_COLUMNS, logger).print_table(
            [
                [
                    item.sign,
                    f"{item.episodes:,}",
                    f"{item.trading_days:,}",
                    f"{item.longest_days:,}",
                    f"{item.short_episodes:,}",
                    f"{item.long_episodes:,}",
                ]
                for item in outputs.rate_gaps[execution]
            ],
            title=f"§14 축2 한미 금리차 부호의 표본 구조 — {execution}",
        )

    long_runs = [
        item
        for item in outputs.regimes[EXECUTION_EXCHANGE_FULL]
        if item.regime.axis == REGIME_AXIS_RATE_GAP and item.trading_days >= LONG_EPISODE_DAYS
    ]
    TableLogger(REGIME_COLUMNS, logger).print_table(
        [_regime_row(item) for item in long_runs],
        title=f"§14 축2 — {LONG_EPISODE_DAYS}거래일 이상 구간만 ({EXECUTION_EXCHANGE_FULL})",
    )


def _regime_row(item: RegimeResult) -> list[str]:
    """국면 표의 한 줄."""
    strategy = item.metrics.get("strategy")
    split = item.metrics.get(BENCHMARK_SPLIT_BUY_HOLD)
    gap = None if strategy is None or split is None else strategy.total_return_rate - split.total_return_rate

    return [
        item.regime.name,
        item.regime.nature,
        f"{item.trading_days:,}",
        _percent(None if strategy is None else strategy.total_return_rate, sign=True),
        _percent(None if strategy is None else strategy.max_drawdown),
        _percent(
            None if (value := item.metrics.get(BENCHMARK_BUY_HOLD)) is None else value.total_return_rate, sign=True
        ),
        _percent(None if split is None else split.total_return_rate, sign=True),
        _percent(
            None if (value := item.metrics.get(BENCHMARK_KRW_PARKING)) is None else value.total_return_rate, sign=True
        ),
        _percent(gap, sign=True),
    ]


def _on_progress(index: int, total: int, run: PlannedRun) -> None:
    """실행 진행을 알린다."""
    logger.debug(f"[{index}/{total}] {run.execution} · {run.axis}={run.value}")


@cli_exception_handler
def main() -> None:
    """견고성 검사를 실행하고 산출물을 저장한다."""
    _build_parser().parse_args()

    outputs = run_robustness(on_progress=_on_progress)

    _print_plan(outputs)
    _print_axes(outputs)
    _print_verdicts(outputs)
    _print_ranks(outputs)
    _print_regimes(outputs)

    directory = create_run_directory(ROBUSTNESS_NAME)
    save_table(directory, AXES_FILENAME, outputs.axes_frame)
    save_table(directory, REGIMES_FILENAME, outputs.regimes_frame)
    save_run_summary(directory, outputs.meta)

    TableLogger(OUTPUT_COLUMNS, logger).print_table(
        [
            [AXES_FILENAME, f"{len(outputs.axes_frame):,}"],
            [REGIMES_FILENAME, f"{len(outputs.regimes_frame):,}"],
        ],
        title=f"산출물 (저장 폴더: {directory})",
    )
    save_metadata(
        KEY_META_ROBUSTNESS,
        {
            "runs": outputs.meta[KEY_RUNS],
            "axis_verdicts": outputs.meta[KEY_VERDICTS],
            "path_rank": outputs.meta[KEY_RANK],
            "rate_gap_summary": outputs.meta[KEY_RATE_GAP],
            "output": str(directory),
        },
    )
    logger.debug(
        f"고유 실행 {outputs.run_count}회로 축 {len(outputs.axes_frame):,}줄, 국면 {len(outputs.regimes_frame):,}줄을 산출했습니다"
    )


if __name__ == "__main__":
    main()
