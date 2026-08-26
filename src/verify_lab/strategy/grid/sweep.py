"""축별 단독 검사 — 결론이 뒤집히는지만 본다

사양서 §12.1 이 정한 검사 방식이며, **최적 조합을 찾는 것이 아니다.**
§12.1 은 "전수 탐색 금지 — 4×4×3×4×4×3×3 = 6,912가지를 돌려 최고 조합을 고르면 그것이
과최적화" 라고 못 박았고, §15.1 은 「결과를 보고 파라미터 변경 금지」를 규정했다.

**그래서 판정을 불리언으로만 낸다.** 축값마다 결론이 참인지 거짓인지를 내고
「전 축값에서 같은가」만 답한다. 금액의 크기로 순위를 매기는 순간 그것은 검사가 아니라
좋은 값 고르기가 된다.

**한 번에 한 축만 바꾼다.** 두 축이 함께 움직이면 어느 것이 결과를 만들었는지 알 수 없다.
다만 축이 서로 독립이라는 뜻은 아니다 — 익절폭 g 를 올리면 슬롯 상한이 함께 지배하므로
그 축의 결과에는 익절폭·상한 발동·차등 소멸·현금 잔류가 함께 들어 있다.

**N 축만 네 실행 전부에 돈다** (결정 C105). 사양서 §15.3 #8 의 「N 에 따라 경로 순위 변동」과
§18 의 1차 목적(세 경로의 상대 관계가 N과 국면에 걸쳐 안정적인가)이 N×경로를 요구하기 때문이다.
나머지 축까지 네 배로 늘리면 표만 커지고 §12.1 이 경계한 지점에 가까워진다.

**기본 설정 실행은 한 번만 돈다.** 여덟 축이 전부 기본값을 포함하므로 그대로 돌리면
같은 실행을 여덟 번 한다. 비교표에는 축마다 그 결과를 다시 실어 기준선을 남긴다.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.report.constants import DATE_FORMAT, RATE_TO_PERCENT
from verify_lab.strategy.grid.constants import (
    ALLOCATION_SPREAD_CHOICES,
    AXIS_ALLOCATION_SPREAD,
    AXIS_EXCHANGE_SPREAD,
    AXIS_GROWTH_RATE,
    AXIS_LOOKBACK_YEARS,
    AXIS_MIN_RANGE_WIDTH,
    AXIS_PARKING_FLOOR,
    AXIS_RP_FLOOR,
    AXIS_SLOT_CAP_RATIO,
    BENCHMARK_BUY_HOLD,
    BENCHMARK_KRW_PARKING,
    BENCHMARK_SPLIT_BUY_HOLD,
    COL_TOTAL_ASSETS,
    DEFAULT_ALLOCATION_SPREAD,
    DEFAULT_BROKERAGE_RATE,
    DEFAULT_EXCHANGE_SPREAD_RATE,
    DEFAULT_GROWTH_RATE,
    DEFAULT_LOOKBACK_YEARS,
    DEFAULT_MIN_RANGE_WIDTH,
    DEFAULT_PARKING_FLOOR_RATE,
    DEFAULT_RP_FLOOR_RATE,
    DEFAULT_SLIPPAGE_RATE,
    DEFAULT_SLOT_CAP_RATIO,
    DISPLAY_AXIS_ALLOCATION_SPREAD,
    DISPLAY_AXIS_EXCHANGE_SPREAD,
    DISPLAY_AXIS_GROWTH_RATE,
    DISPLAY_AXIS_LOOKBACK_YEARS,
    DISPLAY_AXIS_MIN_RANGE_WIDTH,
    DISPLAY_AXIS_PARKING_FLOOR,
    DISPLAY_AXIS_RP_FLOOR,
    DISPLAY_AXIS_SLOT_CAP_RATIO,
    EXCHANGE_SPREAD_RATE_CHOICES,
    EXECUTION_ETF_1X,
    EXECUTION_ETF_2X,
    EXECUTION_EXCHANGE_FULL,
    EXECUTION_EXCHANGE_MATCHED,
    GROWTH_RATE_CHOICES,
    INITIAL_CAPITAL,
    LOOKBACK_YEAR_CHOICES,
    MIN_RANGE_WIDTH_CHOICES,
    PARKING_FLOOR_RATE_CHOICES,
    PATH_ETF_1X,
    PATH_ETF_2X,
    PATH_EXCHANGE,
    RP_FLOOR_RATE_CHOICES,
    SLOT_CAP_RATIO_CHOICES,
)
from verify_lab.strategy.grid.engine import GridConfig
from verify_lab.strategy.grid.interest import InterestConfig
from verify_lab.strategy.grid.metrics import red_flags
from verify_lab.strategy.grid.paths.base import CostConfig
from verify_lab.strategy.grid.regimes import (
    CONTIGUOUS_REGIMES,
    SPEC_REGIMES,
    RateGapSummary,
    RegimeResult,
    evaluate_regimes,
    rate_gap_regimes,
    rate_gap_summaries,
)
from verify_lab.strategy.grid.runner import CAPITAL_DECIMALS, RATIO_DECIMALS, GridOutputs, run_usdkrw_grid
from verify_lab.strategy.performance import PerformanceMetrics
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 국면 표에서 전략 곡선을 가리키는 키. 벤치마크 키와 같은 평면에 놓여야 한 표에 실린다
STRATEGY_CURVE: Final = "strategy"

# ETF 와 기간을 맞춘 대조군의 시작일. 세 실행이 **같은 날 시작해야** 순위 비교가 성립한다 (결정 C72)
MATCHED_START_DATE: Final = "2017-01-01"

# 사양서 §15.3 #2 의 경계. 이보다 얕으면 미실현 손실 누락을 의심하라고 규정돼 있다
SHALLOW_DRAWDOWN_THRESHOLD: Final = -0.10

# 사양서 §15.3 #7 의 경계. 이탈 보너스가 총수익의 이 비율을 넘으면 종가 체결 가정 과의존이다
EXCESS_SHARE_THRESHOLD: Final = 0.30

# 「이자가 수익의 대부분이다」의 경계. 실측 기본 설정이 63.9% 라 절반을 기준으로 둔다
INTEREST_MAJORITY_THRESHOLD: Final = 0.50

# ============================================================
# 결론 — 축을 옮겨도 유지되는지 보는 대상
# ============================================================

CONCLUSION_BEAT_SPLIT_BUY_HOLD: Final = "분할매수 후 보유를 이긴다"
CONCLUSION_BEAT_BUY_HOLD: Final = "B&H 를 이긴다"
CONCLUSION_BEAT_PARKING: Final = "원화 파킹 100% 를 이긴다"
CONCLUSION_SHALLOW_DRAWDOWN: Final = "MDD 가 −10%보다 얕다"
CONCLUSION_INTEREST_MAJORITY: Final = "세후 이자가 총수익의 절반을 넘는다"
CONCLUSION_EXCESS_OVER_THRESHOLD: Final = "이탈 보너스가 총수익의 30%를 넘는다"

CONCLUSION_KEYS: Final = (
    CONCLUSION_BEAT_SPLIT_BUY_HOLD,
    CONCLUSION_BEAT_BUY_HOLD,
    CONCLUSION_BEAT_PARKING,
    CONCLUSION_SHALLOW_DRAWDOWN,
    CONCLUSION_INTEREST_MAJORITY,
    CONCLUSION_EXCESS_OVER_THRESHOLD,
)

# 사양서 §15.3 #8 을 판정하는 기준. **금액과 리스크 조정 지표를 함께 본다** —
# §1.1 이 노출이 다르면 리스크 조정 지표로만 판단하라고 규정했고, §13.3 은 금액으로 물었다
RANK_BASIS_ASSETS: Final = "종료 총자산"
RANK_BASIS_CALMAR: Final = "Calmar"
RANK_BASIS_SHARPE: Final = "Sharpe"

RANK_BASES: Final = (RANK_BASIS_ASSETS, RANK_BASIS_CALMAR, RANK_BASIS_SHARPE)


@dataclass(frozen=True)
class Axis:
    """검사 축 하나

    Attributes:
        key: `GridConfig` 계열에서 이 축이 바꾸는 필드 이름
        name: 표시 이름
        values: 검사 범위. **`constants.py` 의 `*_CHOICES` 를 그대로 쓴다**
        default: 기본 설정의 값
        in_spec: 사양서 §12 파라미터 표에 있는 축인가.
            거짓이면 이 프로젝트가 더한 축이며 표에 그렇게 표기한다
        scope: 이 축을 돌릴 실행 키. 비어 있으면 본 실행에만 돈다
    """

    key: str
    name: str
    values: tuple[float, ...] | tuple[int, ...]
    default: float | int
    in_spec: bool
    scope: tuple[str, ...]


@dataclass(frozen=True)
class Execution:
    """축 검사를 돌릴 실행 하나

    Attributes:
        key: 표시·집계에서 이 실행을 가리키는 이름
        path_name: 집행 경로 이름
        start_date: 매매 시작일. `None` 이면 경로의 기본 시작일
    """

    key: str
    path_name: str
    start_date: str | None


@dataclass(frozen=True)
class PlannedRun:
    """돌려야 할 실행 하나

    Attributes:
        execution: 실행 키
        axis: 이 실행을 요구한 축 키. 기본 설정은 **처음 요구한 축**에 달린다
        value: 축값
        is_default: 모든 축이 기본값인가
        settings: 축 키 → 값. **기본 설정과 정확히 한 필드만 달라야 한다**
    """

    execution: str
    axis: str
    value: float | int
    is_default: bool
    settings: Mapping[str, float | int]


@dataclass(frozen=True)
class SweepRow:
    """비교표의 한 줄 — 실행 하나가 낸 값을 축 하나의 관점에서 본 것

    기본 설정 행은 **여러 축에 같은 값으로 실린다.** 실행은 한 번뿐이고
    축마다 기준선이 필요하기 때문이다.

    Attributes:
        execution: 실행 키
        axis: 축 키
        value_label: 축값의 표시 문자열
        is_default: 기본 설정인가
        in_spec: 사양서 §12 에 있는 축인가
        final_assets: 종료 총자산 (원)
        total_return_rate: 총수익률 (비율)
        cagr: 연평균 성장률 (비율)
        max_drawdown: 최대 낙폭 (비율, 음수)
        calmar: Calmar. 낙폭이 없으면 `None`
        volatility: 연환산 변동성. 수익률이 하나면 `None`
        sharpe: Sharpe. 초과수익 표준편차가 0 이면 `None`
        sortino: Sortino. 하방편차가 0 이면 `None`
        deployment_mean: 평균 투입률 (비율)
        turnover_per_year: 연 회전 횟수 (전체 기준)
        total_return: 총수익 (원)
        interest_after_tax: 세후 이자 (원)
        grid_excess_share_of_total_return: 이탈 보너스 ÷ 총수익
        grid_excess_share_of_trading: 이탈 보너스 ÷ 매매 기여분
        benchmark_gaps: 벤치마크 키 → 전략 − 벤치마크 (원)
        red_flags_triggered: 사양서 §15.3 에서 걸린 항목 수
    """

    execution: str
    axis: str
    value_label: str
    is_default: bool
    in_spec: bool
    final_assets: float
    total_return_rate: float
    cagr: float
    max_drawdown: float
    calmar: float | None
    volatility: float | None
    sharpe: float | None
    sortino: float | None
    deployment_mean: float
    turnover_per_year: float
    total_return: float
    interest_after_tax: float
    grid_excess_share_of_total_return: float | None
    grid_excess_share_of_trading: float | None
    benchmark_gaps: Mapping[str, float]
    red_flags_triggered: int


@dataclass(frozen=True)
class AxisVerdict:
    """축 하나에서 결론 하나가 뒤집혔는가

    Attributes:
        execution: 실행 키
        axis: 축 키
        conclusion: 결론 이름
        stable: 전 축값에서 같으면 참. 하나라도 다르면 거짓.
            **판정할 수 없는 축값이 섞이면 `None`** 이다 (결정 C95)
        detail: 근거. 갈렸다면 **어느 축값에서 갈렸는지**가 들어간다
    """

    execution: str
    axis: str
    conclusion: str
    stable: bool | None
    detail: str


@dataclass(frozen=True)
class RankVerdict:
    """사양서 §15.3 #8 — N 에 따라 경로 순위가 바뀌는가

    Attributes:
        basis: 순위를 매긴 기준
        triggered: 순위가 바뀌면 참. **값이 없는 실행이 있으면 `None`**
        detail: 근거. N 별 순위를 그대로 적는다
    """

    basis: str
    triggered: bool | None
    detail: str


def build_axes() -> tuple[Axis, ...]:
    """검사 축을 만든다.

    **값을 손으로 적지 않는다.** 사양서 §12 의 검사 범위는 `constants.py` 의 `*_CHOICES` 가
    SoT이며, 여기서 복제하면 한쪽만 고쳐질 때 조용히 갈라진다.

    Returns:
        축 목록. 사양서 §12 의 일곱 축 다음에 추가 축이 온다
    """
    matched = (EXECUTION_EXCHANGE_MATCHED, EXECUTION_ETF_1X, EXECUTION_ETF_2X)

    return (
        Axis(
            AXIS_LOOKBACK_YEARS,
            DISPLAY_AXIS_LOOKBACK_YEARS,
            LOOKBACK_YEAR_CHOICES,
            DEFAULT_LOOKBACK_YEARS,
            True,
            matched,
        ),
        Axis(AXIS_GROWTH_RATE, DISPLAY_AXIS_GROWTH_RATE, GROWTH_RATE_CHOICES, DEFAULT_GROWTH_RATE, True, ()),
        Axis(
            AXIS_ALLOCATION_SPREAD,
            DISPLAY_AXIS_ALLOCATION_SPREAD,
            ALLOCATION_SPREAD_CHOICES,
            DEFAULT_ALLOCATION_SPREAD,
            True,
            (),
        ),
        Axis(
            AXIS_MIN_RANGE_WIDTH,
            DISPLAY_AXIS_MIN_RANGE_WIDTH,
            MIN_RANGE_WIDTH_CHOICES,
            DEFAULT_MIN_RANGE_WIDTH,
            True,
            (),
        ),
        Axis(
            AXIS_SLOT_CAP_RATIO, DISPLAY_AXIS_SLOT_CAP_RATIO, SLOT_CAP_RATIO_CHOICES, DEFAULT_SLOT_CAP_RATIO, True, ()
        ),
        Axis(AXIS_RP_FLOOR, DISPLAY_AXIS_RP_FLOOR, RP_FLOOR_RATE_CHOICES, DEFAULT_RP_FLOOR_RATE, True, ()),
        Axis(
            AXIS_PARKING_FLOOR,
            DISPLAY_AXIS_PARKING_FLOOR,
            PARKING_FLOOR_RATE_CHOICES,
            DEFAULT_PARKING_FLOOR_RATE,
            True,
            (),
        ),
        # 사양서 §12 파라미터 표에 없다. 슬리피지·스프레드 가정이 환전 왕복비용의 56% 라
        # 결론이 그 가정에 걸려 있는지 봐야 해서 더했다 (결정 C106)
        Axis(
            AXIS_EXCHANGE_SPREAD,
            DISPLAY_AXIS_EXCHANGE_SPREAD,
            EXCHANGE_SPREAD_RATE_CHOICES,
            DEFAULT_EXCHANGE_SPREAD_RATE,
            False,
            (),
        ),
    )


def build_executions() -> tuple[Execution, ...]:
    """축 검사를 돌릴 실행을 만든다.

    **환전 2005~ 가 본 실행이다.** 사양서 §11.4 가 N=7 의 워밍업에 맞춰 시작일을 통일했고,
    §14 축1 이 최악으로 지목한 2009~2014 대세 하락이 그 기간에만 들어 있다.

    나머지 셋은 **같은 시작일로 맞춘 비교군**이다. ETF 는 2016-12-27 상장이라
    그냥 견주면 순위가 기간에서 나온 건지 경로에서 나온 건지 알 수 없다 (결정 C72).

    Returns:
        실행 목록
    """
    return (
        Execution(EXECUTION_EXCHANGE_FULL, PATH_EXCHANGE, None),
        Execution(EXECUTION_EXCHANGE_MATCHED, PATH_EXCHANGE, MATCHED_START_DATE),
        Execution(EXECUTION_ETF_1X, PATH_ETF_1X, MATCHED_START_DATE),
        Execution(EXECUTION_ETF_2X, PATH_ETF_2X, MATCHED_START_DATE),
    )


def plan_runs(axes: Sequence[Axis], executions: Sequence[Execution]) -> tuple[PlannedRun, ...]:
    """돌려야 할 실행 목록을 만든다. 같은 설정은 한 번만 넣는다.

    Args:
        axes: 검사 축
        executions: 실행 정의. **첫 번째가 본 실행**이며 나머지는 축의 `scope` 가 부른다

    Returns:
        중복이 지워진 실행 계획

    Raises:
        ValueError: 실행이 하나도 없는 경우
    """
    if not executions:
        raise ValueError("실행이 하나도 없습니다")

    base = {axis.key: axis.default for axis in axes}
    primary = executions[0].key
    planned: list[PlannedRun] = []
    seen: set[tuple[str, tuple[tuple[str, float | int], ...]]] = set()

    for axis in axes:
        targets = (primary, *axis.scope)
        for execution in targets:
            for value in axis.values:
                settings = {**base, axis.key: value}
                fingerprint = (execution, tuple(sorted(settings.items())))
                if fingerprint in seen:
                    continue

                seen.add(fingerprint)
                planned.append(
                    PlannedRun(
                        execution=execution,
                        axis=axis.key,
                        value=value,
                        is_default=settings == base,
                        settings=settings,
                    )
                )

    logger.debug(f"실행 계획: 축 {len(axes)}개, 고유 실행 {len(planned)}회")

    return tuple(planned)


def build_config(settings: Mapping[str, float | int]) -> GridConfig:
    """축 설정을 실행 파라미터로 바꾼다.

    Args:
        settings: 축 키 → 값

    Returns:
        실행 파라미터
    """
    return GridConfig(
        lookback_years=int(settings[AXIS_LOOKBACK_YEARS]),
        growth_rate=float(settings[AXIS_GROWTH_RATE]),
        min_range_width=float(settings[AXIS_MIN_RANGE_WIDTH]),
        allocation_spread=float(settings[AXIS_ALLOCATION_SPREAD]),
        slot_cap_ratio=float(settings[AXIS_SLOT_CAP_RATIO]),
        initial_capital=INITIAL_CAPITAL,
        cost=CostConfig(
            exchange_spread_rate=float(settings[AXIS_EXCHANGE_SPREAD]),
            slippage_rate=DEFAULT_SLIPPAGE_RATE,
            brokerage_rate=DEFAULT_BROKERAGE_RATE,
        ),
        interest=InterestConfig(
            rp_floor_rate=float(settings[AXIS_RP_FLOOR]),
            parking_floor_rate=float(settings[AXIS_PARKING_FLOOR]),
        ),
    )


def run_sweep(
    axes: Sequence[Axis],
    executions: Sequence[Execution],
    *,
    on_progress: Callable[[int, int, PlannedRun], None] | None = None,
) -> dict[tuple[str, tuple[tuple[str, float | int], ...]], GridOutputs]:
    """실행 계획을 그대로 돌린다.

    **엔진·경로·벤치마크를 새로 쓰지 않는다.** 한 실행짜리 진입점을 그대로 부르므로
    축 검사의 값과 단독 실행의 값이 어긋날 수 없다.

    Args:
        axes: 검사 축
        executions: 실행 정의
        on_progress: 실행마다 부르는 진행 알림 (완료 수, 전체 수, 방금 끝난 실행)

    Returns:
        (실행 키, 설정 지문) → 실행 산출물
    """
    by_key = {item.key: item for item in executions}
    planned = plan_runs(axes, executions)
    results: dict[tuple[str, tuple[tuple[str, float | int], ...]], GridOutputs] = {}

    for index, run in enumerate(planned, start=1):
        execution = by_key[run.execution]
        results[(run.execution, tuple(sorted(run.settings.items())))] = run_usdkrw_grid(
            build_config(run.settings),
            path_name=execution.path_name,
            start_date=execution.start_date,
        )
        if on_progress is not None:
            on_progress(index, len(planned), run)

    return results


def build_rows(
    axes: Sequence[Axis],
    executions: Sequence[Execution],
    outputs: Mapping[tuple[str, tuple[tuple[str, float | int], ...]], GridOutputs],
    *,
    label: Callable[[Axis, float | int], str],
) -> tuple[SweepRow, ...]:
    """축마다 비교표 줄을 만든다.

    **기본 설정 줄이 축마다 반복된다.** 실행은 한 번뿐이지만 축마다 기준선이 있어야
    "이 축에서 뭐가 달라졌나"를 한 표 안에서 읽을 수 있다.

    Args:
        axes: 검사 축
        executions: 실행 정의
        outputs: `run_sweep` 이 낸 산출물
        label: 축값을 표시 문자열로 바꾸는 함수

    Returns:
        비교표 줄 목록
    """
    base = {axis.key: axis.default for axis in axes}
    primary = executions[0].key
    rows: list[SweepRow] = []

    for axis in axes:
        for execution in (primary, *axis.scope):
            for value in axis.values:
                settings = {**base, axis.key: value}
                rows.append(
                    _row(
                        outputs[(execution, tuple(sorted(settings.items())))],
                        execution=execution,
                        axis=axis,
                        value_label=label(axis, value),
                        is_default=settings == base,
                    )
                )

    return tuple(rows)


def _row(outputs: GridOutputs, *, execution: str, axis: Axis, value_label: str, is_default: bool) -> SweepRow:
    """실행 산출물에서 비교표 한 줄을 뽑는다."""
    performance, grid = outputs.performance, outputs.grid_metrics
    gaps = {item.key: performance.last_value - item.performance.last_value for item in outputs.benchmarks}
    triggered = sum(1 for flag in red_flags(performance, grid) if flag.triggered)

    return SweepRow(
        execution=execution,
        axis=axis.key,
        value_label=value_label,
        is_default=is_default,
        in_spec=axis.in_spec,
        final_assets=performance.last_value,
        total_return_rate=performance.total_return_rate,
        cagr=performance.cagr,
        max_drawdown=performance.max_drawdown,
        calmar=performance.calmar,
        volatility=performance.volatility,
        sharpe=performance.sharpe,
        sortino=performance.sortino,
        deployment_mean=grid.deployment_mean,
        turnover_per_year=grid.turnover_per_year,
        total_return=grid.total_return,
        interest_after_tax=grid.interest_after_tax,
        grid_excess_share_of_total_return=grid.grid_excess_share_of_total_return,
        grid_excess_share_of_trading=grid.grid_excess_share_of_trading,
        benchmark_gaps=gaps,
        red_flags_triggered=triggered,
    )


def conclusion_flags(row: SweepRow) -> dict[str, bool | None]:
    """축값 하나에서 결론이 참인지 낸다.

    **판정할 수 없으면 `None` 이다** (결정 C91). 총수익이 0 이하일 때 비중을 그대로 계산하면
    부호가 조용히 뒤집혀 "이자 기여가 없다"로 읽힌다.

    Args:
        row: 비교표 한 줄

    Returns:
        결론 이름 → 참 / 거짓 / 판정 불가
    """
    interest_share = row.interest_after_tax / row.total_return if row.total_return > 0 else None
    excess_share = row.grid_excess_share_of_total_return if row.total_return > 0 else None

    return {
        CONCLUSION_BEAT_SPLIT_BUY_HOLD: row.benchmark_gaps[BENCHMARK_SPLIT_BUY_HOLD] > 0,
        CONCLUSION_BEAT_BUY_HOLD: row.benchmark_gaps[BENCHMARK_BUY_HOLD] > 0,
        CONCLUSION_BEAT_PARKING: row.benchmark_gaps[BENCHMARK_KRW_PARKING] > 0,
        CONCLUSION_SHALLOW_DRAWDOWN: row.max_drawdown > SHALLOW_DRAWDOWN_THRESHOLD,
        CONCLUSION_INTEREST_MAJORITY: None if interest_share is None else interest_share > INTEREST_MAJORITY_THRESHOLD,
        CONCLUSION_EXCESS_OVER_THRESHOLD: None if excess_share is None else excess_share > EXCESS_SHARE_THRESHOLD,
    }


def axis_verdicts(rows: Sequence[SweepRow]) -> tuple[AxisVerdict, ...]:
    """축마다 결론이 뒤집혔는지 판정한다.

    **크기를 비교하지 않는다.** 축값별 불리언이 전부 같은지만 보며, 갈렸다면
    어느 축값에서 갈렸는지를 근거에 남긴다 — 그 사실 자체가 결과다.

    Args:
        rows: 비교표 줄 목록

    Returns:
        (실행 × 축 × 결론) 마다 한 개씩
    """
    grouped: dict[tuple[str, str], list[SweepRow]] = {}
    for row in rows:
        grouped.setdefault((row.execution, row.axis), []).append(row)

    verdicts: list[AxisVerdict] = []
    for (execution, axis), group in grouped.items():
        flags = [(row.value_label, conclusion_flags(row)) for row in group]
        for conclusion in CONCLUSION_KEYS:
            values = [(label, flag[conclusion]) for label, flag in flags]
            verdicts.append(
                AxisVerdict(
                    execution=execution,
                    axis=axis,
                    conclusion=conclusion,
                    stable=_stable(values),
                    detail=_verdict_detail(values),
                )
            )

    return tuple(verdicts)


def _stable(values: Sequence[tuple[str, bool | None]]) -> bool | None:
    """축값별 불리언이 전부 같은지 낸다. 판정 불가가 섞이면 `None`."""
    flags = [flag for _, flag in values]
    if any(flag is None for flag in flags):
        return None

    return len(set(flags)) == 1


def _verdict_detail(values: Sequence[tuple[str, bool | None]]) -> str:
    """판정 근거. 갈렸다면 소수파 축값을 적는다."""
    unknown = [label for label, flag in values if flag is None]
    if unknown:
        return f"판정 불가 — {', '.join(unknown)}"

    truthy = [label for label, flag in values if flag]
    falsy = [label for label, flag in values if flag is False]
    if not truthy or not falsy:
        answer = "참" if truthy else "거짓"
        return f"{len(values)}개 축값 전부 {answer}"

    minority = truthy if len(truthy) <= len(falsy) else falsy
    answer = "참" if minority is truthy else "거짓"

    return f"{', '.join(minority)} 에서만 {answer} (참 {len(truthy)}개 · 거짓 {len(falsy)}개)"


def path_rank_verdicts(rows: Sequence[SweepRow]) -> tuple[RankVerdict, ...]:
    """사양서 §15.3 #8 — N 에 따라 경로 순위가 바뀌는지 판정한다.

    바뀌면 §14 축3 이 적은 대로 **"전략이 아니라 N 을 맞춘 것"** 이다.
    기준을 셋 두는 이유는 §13.3 이 금액으로 묻고 §1.1 이 노출이 다르면 리스크 조정 지표로만
    보라고 규정했기 때문이다 — 둘이 다른 답을 낼 수 있고 그것도 사실이다.

    Args:
        rows: 비교표 줄 목록. N 축의 비교 실행 줄만 쓴다

    Returns:
        기준마다 한 개씩
    """
    comparison = (EXECUTION_EXCHANGE_MATCHED, EXECUTION_ETF_1X, EXECUTION_ETF_2X)
    by_value: dict[str, dict[str, SweepRow]] = {}
    for row in rows:
        if row.axis == AXIS_LOOKBACK_YEARS and row.execution in comparison:
            by_value.setdefault(row.value_label, {})[row.execution] = row

    getters: dict[str, Callable[[SweepRow], float | None]] = {
        RANK_BASIS_ASSETS: lambda row: row.final_assets,
        RANK_BASIS_CALMAR: lambda row: row.calmar,
        RANK_BASIS_SHARPE: lambda row: row.sharpe,
    }

    verdicts: list[RankVerdict] = []
    for basis in RANK_BASES:
        rankings: dict[str, tuple[str, ...] | None] = {}
        for label in sorted(by_value):
            scored = [(execution, getters[basis](row)) for execution, row in by_value[label].items()]
            rankings[label] = (
                None
                if any(value is None for _, value in scored)
                else tuple(execution for execution, _ in sorted(scored, key=lambda item: -(item[1] or 0.0)))
            )

        verdicts.append(_rank_verdict(basis, rankings))

    return tuple(verdicts)


def _rank_verdict(basis: str, rankings: Mapping[str, tuple[str, ...] | None]) -> RankVerdict:
    """N 별 순위에서 판정 하나를 만든다."""
    if not rankings:
        return RankVerdict(basis=basis, triggered=None, detail="비교할 실행이 없습니다")

    if any(order is None for order in rankings.values()):
        missing = ", ".join(label for label, order in rankings.items() if order is None)
        return RankVerdict(basis=basis, triggered=None, detail=f"판정 불가 — 값이 없는 축값: {missing}")

    orders = {label: order for label, order in rankings.items() if order is not None}
    distinct = set(orders.values())
    detail = " · ".join(f"N={label} {' > '.join(order)}" for label, order in orders.items())
    if len(distinct) == 1:
        return RankVerdict(basis=basis, triggered=False, detail=f"네 축값 순위 동일 — {detail}")

    return RankVerdict(basis=basis, triggered=True, detail=f"순위가 갈린다 — {detail}")


# ============================================================
# 조립과 표시용 프레임
# ============================================================
#
# 단일 실행에서 `runner.py` 가 하는 역할을 견고성 검사에 대해 한다 —
# 계산은 위의 축 순회와 `regimes.py` 가 이미 하므로, 여기서는 그 결과를
# 사람이 읽는 표로 바꾸고 요약을 모으기만 한다.

# 축 비교표의 한글 헤더. 내부 계산은 `SweepRow` 의 영문 필드로 하고 저장 직전에만 바꾼다
AXES_LABELS: Final = (
    "실행",
    "축",
    "사양서 축",
    "축값",
    "기본값",
    "종료 총자산",
    "총수익률",
    "CAGR",
    "MDD",
    "Calmar",
    "변동성",
    "Sharpe",
    "Sortino",
    "투입률",
    "연 회전",
    "총수익",
    "세후 이자",
    "이자 비중",
    "보너스/총수익",
    "보너스/매매기여",
    "전략-B&H",
    "전략-분할매수",
    "전략-파킹",
    "Red Flag 걸림",
)

# 국면 비교표의 한글 헤더
REGIMES_LABELS: Final = (
    "축",
    "실행",
    "구간",
    "성격",
    "시작",
    "종료",
    "거래일",
    "수익률",
    "전략 총수익률",
    "전략 CAGR",
    "전략 MDD",
    "전략 Sharpe",
    "B&H 총수익률",
    "B&H MDD",
    "분할매수 총수익률",
    "분할매수 MDD",
    "파킹 총수익률",
    "전략-B&H",
    "전략-분할매수",
    "전략-파킹",
)

# summary.json 키
KEY_AXES: Final = "axes"
KEY_REGIMES: Final = "regimes"
KEY_VERDICTS: Final = "axis_verdicts"
KEY_RANK: Final = "path_rank"
KEY_RATE_GAP: Final = "rate_gap_summary"
KEY_RUNS: Final = "runs"

# 산출물만 보고는 알 수 없는 실행 조건
NOTE_SCOPE = (
    "사양서 §12.1 의 축별 단독 검사와 §14 의 분할 분석을 한 실행에서 낸다. "
    "최적 조합을 찾는 것이 아니라 기본 설정에서 나온 결론이 축을 옮겨도 유지되는지만 본다 - "
    "§12.1 이 전수 탐색을 금지했고 §15.1 이 결과를 보고 파라미터를 바꾸는 것을 금지했다"
)
NOTE_AXIS_SCOPE = (
    "축은 환전 2005~ 에 돌리고 룩백 N 만 네 실행 전부에 돌린다. "
    "사양서 §15.3 #8 과 §18 의 1차 목적이 N×경로를 요구하기 때문이며, "
    "비교 실행 셋은 같은 시작일이라야 순위가 기간에서 나온 것이 아님이 보장된다"
)
NOTE_AXIS_SPREAD = (
    "환전 스프레드 축은 사양서 §12 파라미터 표에 없는 추가 축이다. "
    "슬리피지가 실측되지 않은 가정인데 환전 왕복비용의 절반을 넘어 "
    "결론이 그 가정에 걸려 있는지 봐야 하므로 넣었고, 표에 출처를 따로 표기한다"
)
NOTE_AXIS_COUPLING = (
    "축이 서로 독립이라는 뜻은 아니다. 익절폭 g 를 올리면 슬롯 상한이 함께 지배하므로 "
    "그 축의 결과에는 익절폭·상한 발동·차등 소멸·현금 잔류가 함께 들어 있다. "
    "슬롯 상한 축은 기본 g 에서 8/10/12% 가 전부 미발동이라 세 칸이 같게 나온다"
)
NOTE_REGIME_SPEC = (
    "사양서 §14 축1 의 8구간은 겹치고(2009·2014·2016·2018) 빈다(2021·2023·2026). " "원문을 재는 표라 고치지 않고, 빠진 해는 겹침 없는 연속 분할이 따로 덮는다"
)
NOTE_REGIME_ANCHOR = (
    "구간 지표는 직전 거래일을 앵커로 포함해 자른 곡선에서 낸다. "
    "앵커가 없으면 구간 첫날의 수익률이 어느 구간에도 안 들어가 조용히 사라진다. "
    "구간 MDD 는 그 구간 시작을 기준으로 다시 잰 값이라 전 기간 MDD 와 다르다"
)
NOTE_REGIME_RATE_GAP = (
    "한미 금리차 부호는 실수령 금리가 아니라 원지표 DTB3 - CD91 로 잰다. "
    "동률은 (+)에도 (-)에도 넣지 않고 별도 칸으로 둔다. "
    "구간 대부분이 전환기의 며칠짜리 깜빡임이라 부호별 우열에 통계적 주장을 하지 않는다"
)


def format_value(axis: Axis, value: float | int) -> str:
    """축값을 표시 문자열로 바꾼다.

    축마다 단위가 달라 한 형식으로 찍을 수 없다 — 룩백은 연 단위 정수이고,
    익절폭·최소폭·상한은 비율이며, 금리 하한은 이미 연 % 로 표기된 값이다.

    Args:
        axis: 축
        value: 축값

    Returns:
        표시 문자열
    """
    if axis.key == AXIS_LOOKBACK_YEARS:
        return f"{int(value)}년"

    if axis.key == AXIS_ALLOCATION_SPREAD:
        return f"±{value:.1f}"

    if axis.key in (AXIS_RP_FLOOR, AXIS_PARKING_FLOOR):
        return f"{value:.2f}%"

    if axis.key == AXIS_EXCHANGE_SPREAD:
        return f"{value * RATE_TO_PERCENT:.3f}%"

    return f"{value * RATE_TO_PERCENT:.1f}%"


def axes_table(rows: Sequence[SweepRow], *, names: Mapping[str, str]) -> pd.DataFrame:
    """축 비교표를 표시용으로 만든다.

    Args:
        rows: 비교표 줄 목록
        names: 축 키 → 표시 이름

    Returns:
        한글 헤더의 표
    """
    records = [
        (
            row.execution,
            names[row.axis],
            "예" if row.in_spec else "아니오 (추가 축)",
            row.value_label,
            "예" if row.is_default else "",
            round(row.final_assets, CAPITAL_DECIMALS),
            _ratio(row.total_return_rate),
            _ratio(row.cagr),
            _ratio(row.max_drawdown),
            _ratio(row.calmar),
            _ratio(row.volatility),
            _ratio(row.sharpe),
            _ratio(row.sortino),
            _ratio(row.deployment_mean),
            _ratio(row.turnover_per_year),
            round(row.total_return, CAPITAL_DECIMALS),
            round(row.interest_after_tax, CAPITAL_DECIMALS),
            _ratio(row.interest_after_tax / row.total_return if row.total_return > 0 else None),
            _ratio(row.grid_excess_share_of_total_return),
            _ratio(row.grid_excess_share_of_trading),
            round(row.benchmark_gaps[BENCHMARK_BUY_HOLD], CAPITAL_DECIMALS),
            round(row.benchmark_gaps[BENCHMARK_SPLIT_BUY_HOLD], CAPITAL_DECIMALS),
            round(row.benchmark_gaps[BENCHMARK_KRW_PARKING], CAPITAL_DECIMALS),
            row.red_flags_triggered,
        )
        for row in rows
    ]

    return pd.DataFrame(records, columns=list(AXES_LABELS))


def regimes_table(results: Mapping[str, Sequence[RegimeResult]]) -> pd.DataFrame:
    """국면 비교표를 표시용으로 만든다.

    **범위 밖 구간도 줄을 남긴다.** ETF 두 경로는 사양서 8구간 중 앞 다섯이 비는데,
    빼 버리면 「기간 밖」과 「재고 0」이 구분되지 않는다.

    Args:
        results: 실행 키 → 국면별 결과

    Returns:
        한글 헤더의 표
    """
    records: list[tuple[object, ...]] = []
    for execution, items in results.items():
        for item in items:
            strategy = item.metrics.get(STRATEGY_CURVE)
            buy_hold = item.metrics.get(BENCHMARK_BUY_HOLD)
            split = item.metrics.get(BENCHMARK_SPLIT_BUY_HOLD)
            parking = item.metrics.get(BENCHMARK_KRW_PARKING)

            records.append(
                (
                    item.regime.axis,
                    execution,
                    item.regime.name,
                    item.regime.nature,
                    item.regime.start.strftime(DATE_FORMAT),
                    item.regime.end.strftime(DATE_FORMAT),
                    item.trading_days,
                    item.returns,
                    _ratio(None if strategy is None else strategy.total_return_rate),
                    _ratio(None if strategy is None else strategy.cagr),
                    _ratio(None if strategy is None else strategy.max_drawdown),
                    _ratio(None if strategy is None else strategy.sharpe),
                    _ratio(None if buy_hold is None else buy_hold.total_return_rate),
                    _ratio(None if buy_hold is None else buy_hold.max_drawdown),
                    _ratio(None if split is None else split.total_return_rate),
                    _ratio(None if split is None else split.max_drawdown),
                    _ratio(None if parking is None else parking.total_return_rate),
                    _ratio(_gap(strategy, buy_hold)),
                    _ratio(_gap(strategy, split)),
                    _ratio(_gap(strategy, parking)),
                )
            )

    return pd.DataFrame(records, columns=list(REGIMES_LABELS))


def _gap(strategy: PerformanceMetrics | None, benchmark: PerformanceMetrics | None) -> float | None:
    """구간 총수익률의 차이. 한쪽이라도 없으면 `None` 이다."""
    if strategy is None or benchmark is None:
        return None

    return strategy.total_return_rate - benchmark.total_return_rate


def _ratio(value: float | None) -> float | None:
    """비율을 저장용 자릿수로 반올림한다. 계산 불가는 그대로 `None` 이다."""
    return None if value is None else round(float(value), RATIO_DECIMALS)


@dataclass(frozen=True)
class RobustnessOutputs:
    """견고성 검사의 산출물

    Attributes:
        rows: 축 비교표 줄. **기본 설정 줄이 축마다 반복**되므로 고유 실행 수보다 많다
        verdicts: 축마다 결론이 뒤집혔는지
        ranks: 사양서 §15.3 #8 판정
        regimes: 실행 키 → 국면별 결과 (사양서 국면 · 연속 분할 · 금리차 순)
        rate_gaps: 실행 키 → 부호별 표본 구조
        axes_frame: 축 비교표 (표시용)
        regimes_frame: 국면 비교표 (표시용)
        run_count: 실제로 돌린 고유 실행 수
        meta: 실행 조건과 핵심 수치
    """

    rows: tuple[SweepRow, ...]
    verdicts: tuple[AxisVerdict, ...]
    ranks: tuple[RankVerdict, ...]
    regimes: Mapping[str, tuple[RegimeResult, ...]]
    rate_gaps: Mapping[str, tuple[RateGapSummary, ...]]
    axes_frame: pd.DataFrame
    regimes_frame: pd.DataFrame
    run_count: int
    meta: dict[str, object]


def run_robustness(*, on_progress: Callable[[int, int, PlannedRun], None] | None = None) -> RobustnessOutputs:
    """사양서 §12.1 축별 검사와 §14 분할 분석을 한 번에 낸다.

    **한 실행에서 둘 다 내는 이유는 대조의 전제가 「같은 코드·같은 데이터」이기 때문이다.**
    따로 돌리면 그 사실을 사람이 확인해야 하고, 국면 분석이 쓰는 네 실행은 어차피
    축 검사가 이미 돌린 것들이라 추가 실행이 없다.

    Args:
        on_progress: 실행마다 부르는 진행 알림

    Returns:
        축·국면 산출물과 표시용 프레임
    """
    axes, executions = build_axes(), build_executions()
    outputs = run_sweep(axes, executions, on_progress=on_progress)
    rows = build_rows(axes, executions, outputs, label=format_value)

    base = tuple(sorted({axis.key: axis.default for axis in axes}.items()))
    regimes: dict[str, tuple[RegimeResult, ...]] = {}
    rate_gaps: dict[str, tuple[RateGapSummary, ...]] = {}
    for execution in executions:
        result = outputs[(execution.key, base)]
        curve = result.result.daily.set_index(COL_DATE)[COL_TOTAL_ASSETS]
        curves = {STRATEGY_CURVE: curve, **{item.key: item.curve for item in result.benchmarks}}
        risk_free = result.rates.risk_free.set_axis(curve.index)
        gap_regimes = rate_gap_regimes(
            result.rates.tbill.set_axis(curve.index), result.rates.cd91.set_axis(curve.index)
        )

        regimes[execution.key] = evaluate_regimes(
            curves,
            risk_free=risk_free,
            regimes=(*SPEC_REGIMES, *CONTIGUOUS_REGIMES, *gap_regimes),
        )
        rate_gaps[execution.key] = rate_gap_summaries(gap_regimes)

    names = {axis.key: axis.name for axis in axes}
    verdicts = axis_verdicts(rows)
    ranks = path_rank_verdicts(rows)

    return RobustnessOutputs(
        rows=rows,
        verdicts=verdicts,
        ranks=ranks,
        regimes=regimes,
        rate_gaps=rate_gaps,
        axes_frame=axes_table(rows, names=names),
        regimes_frame=regimes_table(regimes),
        run_count=len(outputs),
        meta=_meta(
            axes,
            executions,
            rows=rows,
            verdicts=verdicts,
            ranks=ranks,
            rate_gaps=rate_gaps,
            run_count=len(outputs),
            names=names,
        ),
    )


def _meta(
    axes: Sequence[Axis],
    executions: Sequence[Execution],
    *,
    rows: Sequence[SweepRow],
    verdicts: Sequence[AxisVerdict],
    ranks: Sequence[RankVerdict],
    rate_gaps: Mapping[str, Sequence[RateGapSummary]],
    run_count: int,
    names: Mapping[str, str],
) -> dict[str, object]:
    """실행 조건과 판정을 요약으로 모은다."""
    return {
        KEY_RUNS: {
            "unique_runs": run_count,
            "comparison_rows": len(rows),
            "axes": [
                {
                    "key": axis.key,
                    "name": axis.name,
                    "values": list(axis.values),
                    "default": axis.default,
                    "in_spec": axis.in_spec,
                }
                for axis in axes
            ],
            "executions": [
                {"key": item.key, "path": item.path_name, "start_date": item.start_date} for item in executions
            ],
        },
        KEY_VERDICTS: [
            {
                "execution": item.execution,
                "axis": names[item.axis],
                "conclusion": item.conclusion,
                "stable": item.stable,
                "detail": item.detail,
            }
            for item in verdicts
        ],
        KEY_RANK: [{"basis": item.basis, "triggered": item.triggered, "detail": item.detail} for item in ranks],
        KEY_RATE_GAP: {
            execution: [
                {
                    "sign": item.sign,
                    "episodes": item.episodes,
                    "trading_days": item.trading_days,
                    "longest_days": item.longest_days,
                    "short_episodes": item.short_episodes,
                    "long_episodes": item.long_episodes,
                }
                for item in summaries
            ]
            for execution, summaries in rate_gaps.items()
        },
        "notes": [
            NOTE_SCOPE,
            NOTE_AXIS_SCOPE,
            NOTE_AXIS_SPREAD,
            NOTE_AXIS_COUPLING,
            NOTE_REGIME_SPEC,
            NOTE_REGIME_ANCHOR,
            NOTE_REGIME_RATE_GAP,
        ],
    }
