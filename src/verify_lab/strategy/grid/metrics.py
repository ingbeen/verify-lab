"""그리드 전용 지표 — 표준 지표가 감추는 실패 양상을 드러낸다

사양서 §13.2 가 요구하는 것들이다. **표준 지표만 보면 이 매매법은 멀쩡해 보인다** —
CAGR 2.75% 에 MDD −8.10% 는 평범한 성적표인데, 같은 실행에서 **최장 보유가 15.8년**이고
**회전이 어느 해석으로도 기대 범위를 벗어난다.** §13.2 가 "백테스트는 통과해도 사람이
통과 못 하는 전략이 그리드에 흔하다" 고 적은 것이 그 얘기다.

**분모를 하나로 두지 않는다.** 격자 이탈 보너스의 비중은 총수익·실현손익·매매 기여분 셋으로
낸다 — 이자가 분모에 들어오면 비중이 내려가 **§15.3 의 30% 판정이 다른 것을 재게 된다.**
이자는 종가 체결 가정과 아무 관계가 없는 수익원이기 때문이다.

**회전은 두 단위로 낸다** (결정 C10). 사양서 §17.2 의 "연 5~15회" 가 전체 건수를 말하는지
슬롯당 회전율을 말하는지 불명확한데, 실측에서 **어느 쪽도 그 범위에 들어오지 않았다.**
하나만 내면 그 사실이 보고서에서 사라진다.

**계산할 수 없으면 `None` 이다.** 체결이 0건일 때 평균 보유기간을 0 으로 답하면
"하루 만에 판다"로 읽히는데, 사실은 **한 번도 사지 않았다**는 뜻이다.

**이 계층은 판정을 다시 하지 않는다.** 곡선과 체결표에 이미 적힌 것을 세고 나눌 뿐이며,
하향 돌파나 범위를 재계산하면 그것이 두 번째 판정식이 되어 조용히 갈라진다.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.strategy.grid.constants import (
    COL_ACTIVE_LEVELS,
    COL_BLOCKED_COUNT,
    COL_BUY_AMOUNT,
    COL_BUY_COUNT,
    COL_CAPPED_LEVELS,
    COL_CASH,
    COL_CLOSE_RATE,
    COL_HELD_INVESTED,
    COL_PARKING_INTEREST,
    COL_RANGE_HIGH,
    COL_RANGE_LOW,
    COL_REBALANCED,
    COL_RP_INTEREST,
    COL_TAX_PAID,
    COL_TOTAL_ASSETS,
    COL_USD_VALUE,
)
from verify_lab.strategy.grid.engine import GridResult
from verify_lab.strategy.performance import TRADING_DAYS_PER_YEAR, PerformanceMetrics
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 사양서 §13.2 의 「하루 3개 이상 체결 횟수」 기준. 다중 체결로 하루에 얼마가 나가는지를 본다
MULTI_FILL_THRESHOLD = 3


@dataclass(frozen=True)
class GridMetrics:
    """사양서 §13.2 의 그리드 전용 지표

    Attributes:
        hold_days_max: 최장 보유기간 (일). **미청산 슬롯을 포함한다** — "5년 물리는 슬롯"은
            아직 안 팔린 것이 더 위험하다. 체결도 보유도 없으면 `None`
        hold_days_mean: 청산된 체결의 평균 보유기간
        hold_days_median: 청산된 체결의 중앙값 보유기간. **평균과 반드시 함께 읽는다**
        open_hold_days_max: 미청산 슬롯 중 최장 보유기간 (마지막 거래일 기준)
        turnover_per_year: 연간 전체 왕복 체결 건수
        turnover_per_slot_per_year: 활성 레벨 하나당 연간 회전율. 활성 레벨이 없었으면 `None`
        blocked_days: 하향 돌파했는데 현금이 모자라 체결하지 못한 거래일 수
        blocked_day_ratio: 그 비중 — "총알 없음" 상태의 시간 비중
        deployment_mean: 평균 투입률 (보유 평가액 ÷ 총자산)
        cash_ratio_mean: 평균 현금 잔류율
        daily_deploy_max: 하루에 총자산의 몇 %가 매수로 나갔는지의 최대
        daily_deploy_max_date: 그날
        multi_fill_days: 하루에 3건 이상 매수한 거래일 수
        unrealised_worst_rate: 최대 미실현 손실률 (보유 투입액 대비). 보유가 없었으면 `None`
        unrealised_worst_date: 그날
        grid_excess_total: 격자 이탈 보너스 합계 (§6.4)
        grid_excess_share_of_total_return: **§15.3 의 판정 분모.** 총수익 대비 비중
        grid_excess_share_of_realized: 실현손익 대비 비중
        grid_excess_share_of_trading: **매매 기여분 대비 비중.** 총수익에서 세후 이자를 뺀 몫이
            분모이며, 이자가 비중을 희석하는 것을 막는다
        total_return: 총수익 (금액)
        interest_after_tax: 세후 이자 (세전 이자 − 원천징수)
        trading_return: 매매 기여분 (총수익 − 세후 이자)
        breach_days: 종가가 범위 하단 아래였던 거래일 수
        breach_episodes: 그 연속 구간의 수. **이탈일은 독립 표본이 아니다**
        breach_days_max_run: 가장 긴 연속 이탈 구간의 길이
        breach_depth_max: 최대 이탈 깊이 (음수 비율). 이탈이 없었으면 `None`
        active_levels_min: 활성 레벨 수의 최솟값
        active_levels_max: 활성 레벨 수의 최댓값
        capped_days: 슬롯 상한이 걸린 거래일 수 (§5.3 작동 빈도)
        range_low_shift_median: 재조정 시 하단 변화율의 중앙값 (절댓값)
        range_low_shift_max: 재조정 시 하단 변화율의 최대 (절댓값)
        range_high_shift_median: 재조정 시 상단 변화율의 중앙값 (절댓값)
        range_high_shift_max: 재조정 시 상단 변화율의 최대 (절댓값)
    """

    hold_days_max: int | None
    hold_days_mean: float | None
    hold_days_median: float | None
    open_hold_days_max: int | None
    turnover_per_year: float
    turnover_per_slot_per_year: float | None
    blocked_days: int
    blocked_day_ratio: float
    deployment_mean: float
    cash_ratio_mean: float
    daily_deploy_max: float
    daily_deploy_max_date: pd.Timestamp
    multi_fill_days: int
    unrealised_worst_rate: float | None
    unrealised_worst_date: pd.Timestamp | None
    grid_excess_total: float
    grid_excess_share_of_total_return: float | None
    grid_excess_share_of_realized: float | None
    grid_excess_share_of_trading: float | None
    total_return: float
    interest_after_tax: float
    trading_return: float
    breach_days: int
    breach_episodes: int
    breach_days_max_run: int
    breach_depth_max: float | None
    active_levels_min: int
    active_levels_max: int
    capped_days: int
    range_low_shift_median: float | None
    range_low_shift_max: float | None
    range_high_shift_median: float | None
    range_high_shift_max: float | None


def evaluate_grid(result: GridResult) -> GridMetrics:
    """실행 결과에서 사양서 §13.2 의 그리드 전용 지표를 낸다.

    Args:
        result: 엔진이 낸 원값. **반올림된 표시용 표를 넘기지 않는다** —
            이중 반올림으로 합계가 어긋난다

    Returns:
        그리드 전용 지표

    Raises:
        ValueError: 일별 곡선이 비어 있는 경우
    """
    daily = result.daily
    if daily.empty:
        raise ValueError("일별 곡선이 비어 있어 지표를 낼 수 없습니다")

    trades = result.trades
    last_date = pd.Timestamp(daily[COL_DATE].iloc[-1])
    trading_days = len(daily)

    hold_days_mean, hold_days_median = _hold_days(trades)
    open_hold_days_max = _open_hold_days_max(result, last_date=last_date)
    hold_days_max = _combined_max(
        None if trades.empty else int(trades["hold_days"].max()),
        open_hold_days_max,
    )

    # 회전. **두 단위로 낸다** — 사양서 §17.2 가 어느 쪽을 전제했는지 불명확하다 (결정 C10)
    years = (trading_days - 1) / TRADING_DAYS_PER_YEAR if trading_days > 1 else 0.0
    active_mean = float(daily[COL_ACTIVE_LEVELS].mean())
    turnover_per_year = len(trades) / years if years > 0 else 0.0

    total_return, interest_after_tax, trading_return = _return_split(daily)
    grid_excess_total = float(trades["grid_excess"].sum()) if not trades.empty else 0.0
    realized_total = float(trades["realized"].sum()) if not trades.empty else 0.0

    deploy_ratio = daily[COL_BUY_AMOUNT] / daily[COL_TOTAL_ASSETS]
    deploy_index = int(deploy_ratio.to_numpy().argmax())

    unrealised_rate, unrealised_date = _worst_unrealised(daily)
    breach_days, breach_episodes, breach_max_run, breach_depth = _breach(daily)
    low_shift_median, low_shift_max = _range_shift(daily, COL_RANGE_LOW)
    high_shift_median, high_shift_max = _range_shift(daily, COL_RANGE_HIGH)

    metrics = GridMetrics(
        hold_days_max=hold_days_max,
        hold_days_mean=hold_days_mean,
        hold_days_median=hold_days_median,
        open_hold_days_max=open_hold_days_max,
        turnover_per_year=turnover_per_year,
        turnover_per_slot_per_year=None if active_mean <= 0 else turnover_per_year / active_mean,
        blocked_days=int((daily[COL_BLOCKED_COUNT] > 0).sum()),
        blocked_day_ratio=float((daily[COL_BLOCKED_COUNT] > 0).sum()) / trading_days,
        deployment_mean=float((daily[COL_USD_VALUE] / daily[COL_TOTAL_ASSETS]).mean()),
        cash_ratio_mean=float((daily[COL_CASH] / daily[COL_TOTAL_ASSETS]).mean()),
        daily_deploy_max=float(deploy_ratio.iloc[deploy_index]),
        daily_deploy_max_date=pd.Timestamp(daily[COL_DATE].iloc[deploy_index]),
        multi_fill_days=int((daily[COL_BUY_COUNT] >= MULTI_FILL_THRESHOLD).sum()),
        unrealised_worst_rate=unrealised_rate,
        unrealised_worst_date=unrealised_date,
        grid_excess_total=grid_excess_total,
        grid_excess_share_of_total_return=_share(grid_excess_total, total_return),
        grid_excess_share_of_realized=_share(grid_excess_total, realized_total),
        grid_excess_share_of_trading=_share(grid_excess_total, trading_return),
        total_return=total_return,
        interest_after_tax=interest_after_tax,
        trading_return=trading_return,
        breach_days=breach_days,
        breach_episodes=breach_episodes,
        breach_days_max_run=breach_max_run,
        breach_depth_max=breach_depth,
        active_levels_min=int(daily[COL_ACTIVE_LEVELS].min()),
        active_levels_max=int(daily[COL_ACTIVE_LEVELS].max()),
        capped_days=int((daily[COL_CAPPED_LEVELS] > 0).sum()),
        range_low_shift_median=low_shift_median,
        range_low_shift_max=low_shift_max,
        range_high_shift_median=high_shift_median,
        range_high_shift_max=high_shift_max,
    )

    logger.debug(
        f"그리드 지표: 최장 보유 {metrics.hold_days_max}일, 회전 전체 {turnover_per_year:.2f}회/년 · "
        f"슬롯당 {metrics.turnover_per_slot_per_year}, 하단 이탈 {breach_days:,}일 ({breach_episodes}구간)"
    )

    return metrics


def _hold_days(trades: pd.DataFrame) -> tuple[float | None, float | None]:
    """청산된 체결의 평균·중앙값 보유기간을 낸다.

    **둘을 함께 낸다.** 두 값이 크게 벌어지면 소수 사건이 결과를 만들고 있다는 신호이며,
    실측에서 평균 262일 대 중앙값 20일이었다.

    Args:
        trades: 청산이 끝난 체결 내역

    Returns:
        `(평균, 중앙값)`. 체결이 없으면 둘 다 `None`
    """
    if trades.empty:
        return None, None

    return float(trades["hold_days"].mean()), float(trades["hold_days"].median())


def _open_hold_days_max(result: GridResult, *, last_date: pd.Timestamp) -> int | None:
    """미청산 슬롯 중 최장 보유기간을 낸다.

    Args:
        result: 실행 결과
        last_date: 마지막 거래일. 아직 팔리지 않았으므로 이날까지가 보유기간이다

    Returns:
        일 수. 미청산이 없으면 `None`
    """
    if not result.open_slots:
        return None

    return max(int((last_date - slot.entry_date).days) for slot in result.open_slots)


def _combined_max(closed: int | None, opened: int | None) -> int | None:
    """청산분과 미청산분의 최장 보유기간을 합친다.

    Args:
        closed: 청산된 체결의 최장 보유기간
        opened: 미청산 슬롯의 최장 보유기간

    Returns:
        둘 중 큰 값. 둘 다 없으면 `None`
    """
    candidates = [value for value in (closed, opened) if value is not None]

    return max(candidates) if candidates else None


def _return_split(daily: pd.DataFrame) -> tuple[float, float, float]:
    """총수익을 세후 이자와 매매 기여분으로 가른다.

    **이자는 종가 체결 가정과 무관한 수익원**이므로 이탈 보너스 비중을 총수익으로만 재면
    §15.3 이 잡으려던 위험이 분모에 숨는다.

    Args:
        daily: 일별 곡선 원값

    Returns:
        `(총수익, 세후 이자, 매매 기여분)`
    """
    total_return = float(daily[COL_TOTAL_ASSETS].iloc[-1] - daily[COL_TOTAL_ASSETS].iloc[0])
    interest_gross = float(daily[COL_RP_INTEREST].sum() + daily[COL_PARKING_INTEREST].sum())
    interest_after_tax = interest_gross - float(daily[COL_TAX_PAID].sum())

    return total_return, interest_after_tax, total_return - interest_after_tax


def _share(value: float, denominator: float) -> float | None:
    """비중을 낸다. 분모가 0이면 `None` 이다.

    Args:
        value: 분자
        denominator: 분모

    Returns:
        비율. 분모가 0이면 `None` — 0 을 돌려주면 "기여가 없다"로 읽힌다
    """
    return None if denominator == 0 else value / denominator


def _worst_unrealised(daily: pd.DataFrame) -> tuple[float | None, pd.Timestamp | None]:
    """최대 미실현 손실률과 그날을 낸다.

    **분모는 보유분 투입액**이지 총자산이 아니다. 총자산으로 나누면 원화현금이 섞여
    물린 정도가 투입률에 희석된다.

    Args:
        daily: 일별 곡선 원값

    Returns:
        `(손익률, 날짜)`. 보유가 한 번도 없었으면 둘 다 `None`
    """
    held = daily[daily[COL_HELD_INVESTED] > 0]
    if held.empty:
        return None, None

    rates = held[COL_USD_VALUE] / held[COL_HELD_INVESTED] - 1.0
    worst = int(rates.to_numpy().argmin())

    return float(rates.iloc[worst]), pd.Timestamp(held[COL_DATE].iloc[worst])


def _breach(daily: pd.DataFrame) -> tuple[int, int, int, float | None]:
    """하단 이탈의 횟수·기간·최대 깊이를 낸다 (사양서 §13.2 — 월평균 방식의 대가).

    **연속 구간을 함께 센다.** 이탈일은 서로 독립인 표본이 아니라 몇 개의 국면에서
    파생된 것이며, 실측에서 261일이 16구간이었다.

    Args:
        daily: 일별 곡선 원값

    Returns:
        `(이탈일 수, 연속 구간 수, 최장 연속 길이, 최대 깊이)`.
        이탈이 없으면 깊이는 `None`
    """
    breached = daily[COL_CLOSE_RATE] < daily[COL_RANGE_LOW]
    days = int(breached.sum())
    if days == 0:
        return 0, 0, 0, None

    starts = breached & ~breached.shift(1, fill_value=False)
    runs = starts.cumsum().where(breached)
    depth = float((daily.loc[breached, COL_CLOSE_RATE] / daily.loc[breached, COL_RANGE_LOW] - 1.0).min())

    return days, int(starts.sum()), int(runs.value_counts().max()), depth


def _range_shift(daily: pd.DataFrame, column: str) -> tuple[float | None, float | None]:
    """재조정마다 범위 경계가 얼마나 움직였는지를 낸다 (사양서 §13.2 — 윈도우 엣지 효과).

    **첫 거래일은 비교 대상이 아니다.** 직전 범위가 없어 변화량이 정의되지 않는다.

    Args:
        daily: 일별 곡선 원값
        column: 범위 하단이나 상단 컬럼

    Returns:
        `(중앙값, 최대)` 변화율의 절댓값. 재조정이 한 번뿐이면 둘 다 `None`
    """
    rebalanced = daily[daily[COL_REBALANCED]]
    if len(rebalanced) < 2:
        return None, None

    shifts = (rebalanced[column] / rebalanced[column].shift(1) - 1.0).abs().dropna()
    if shifts.empty:
        return None, None

    return float(shifts.median()), float(shifts.max())


@dataclass(frozen=True)
class RedFlag:
    """사양서 §15.3 의 Red Flag 하나

    §15.3 은 "아래에 해당하면 **결과를 신뢰하지 말고 구현을 재점검한다**" 로 규정했다.
    걸린 항목을 감추지 않는 것이 이 자료구조의 존재 이유이며,
    **한 실행으로 판정할 수 없는 항목은 `None` 으로 남긴다** — 통과로 적으면 검사한 것이 된다.

    Attributes:
        name: 징후 이름 (§15.3 표의 행)
        triggered: 걸렸는지 여부. **이 실행으로 판정할 수 없으면 `None`**
        detail: 실제 값과 판정 근거
    """

    name: str
    triggered: bool | None
    detail: str


# §15.3 의 임계값
CAGR_LIMIT = 0.10
SHALLOW_DRAWDOWN_LIMIT = -0.10
CALMAR_LIMIT = 1.0
SHARPE_LIMIT = 1.0
TOTAL_RETURN_LIMIT = 10.0
GRID_EXCESS_LIMIT = 0.30


def red_flags(performance: PerformanceMetrics, grid: GridMetrics) -> tuple[RedFlag, ...]:
    """사양서 §15.3 의 징후 아홉 개를 전부 판정한다.

    **판정할 수 없는 항목도 목록에 남긴다.** 빼 버리면 "검사했는데 통과했다"와
    "애초에 검사하지 않았다"가 구분되지 않는다.

    Args:
        performance: 표준 지표
        grid: 그리드 전용 지표

    Returns:
        §15.3 표 순서의 판정 결과
    """
    excess_share = grid.grid_excess_share_of_total_return

    return (
        RedFlag(
            name="CAGR > 10% (총자산 기준)",
            triggered=performance.cagr > CAGR_LIMIT,
            detail=f"CAGR {performance.cagr:.2%} — 룩어헤드·체결가정 완화·분모 오류를 의심한다",
        ),
        RedFlag(
            name="MDD 가 −10%보다 얕음",
            triggered=performance.max_drawdown > SHALLOW_DRAWDOWN_LIMIT,
            detail=f"MDD {performance.max_drawdown:.2%} — 미실현 손실 누락을 의심한다",
        ),
        RedFlag(
            name="Calmar > 1.0",
            triggered=None if performance.calmar is None else performance.calmar > CALMAR_LIMIT,
            detail="낙폭이 없어 계산할 수 없다" if performance.calmar is None else f"Calmar {performance.calmar:.3f}",
        ),
        RedFlag(
            name="Sharpe > 1.0",
            triggered=None if performance.sharpe is None else performance.sharpe > SHARPE_LIMIT,
            detail=(
                "변동이 없어 계산할 수 없다"
                if performance.sharpe is None
                else f"Sharpe {performance.sharpe:.3f} (rf 평균 연 {performance.risk_free_mean:.2f}%) — 걸리면 rf=0 을 의심한다"
            ),
        ),
        RedFlag(
            name="총수익률 1000% 이상",
            triggered=performance.total_return_rate >= TOTAL_RETURN_LIMIT,
            detail=f"총수익률 {performance.total_return_rate:.2%}",
        ),
        RedFlag(
            name="자산곡선 단조 증가",
            # 곡선이 한 번도 내려가지 않았다는 것이 이 징후다. 낙폭이 0 이면 그렇다
            triggered=performance.max_drawdown == 0.0,
            detail=f"최대 낙폭 {performance.max_drawdown:.2%} — 걸리면 실현손익만 집계했음을 의심한다",
        ),
        RedFlag(
            name="격자 이탈 보너스가 총수익의 30% 초과",
            triggered=None if excess_share is None else excess_share > GRID_EXCESS_LIMIT,
            detail=(
                "총수익이 0이라 계산할 수 없다"
                if excess_share is None
                else f"총수익 대비 {excess_share:.2%} · 매매 기여분 대비 {_format_share(grid.grid_excess_share_of_trading)}"
                " — 총수익 기준만 보면 이자가 위험을 가린다"
            ),
        ),
        RedFlag(
            name="N 에 따라 경로 순위 변동",
            triggered=None,
            detail="축별 검사가 끝나야 판정할 수 있다 — 한 실행으로는 알 수 없다",
        ),
        RedFlag(
            name="261250 β < 1.95",
            triggered=None,
            detail="등가성 검증이 답하는 항목이다 — 그리드 실행의 산출물이 아니다",
        ),
    )


def _format_share(value: float | None) -> str:
    """비중을 사람이 읽는 문자열로 바꾼다. 계산 불가는 그렇게 적는다.

    Args:
        value: 비율이거나 `None`

    Returns:
        표시 문자열
    """
    return "계산 불가" if value is None else f"{value:.2%}"


def rounded(value: float | None, digits: int) -> float | None:
    """`None` 을 그대로 통과시키는 반올림.

    지표는 계산 불가를 `None` 으로 답하므로 저장 직전 반올림에서 매번 분기해야 한다.

    Args:
        value: 반올림할 값이거나 `None`
        digits: 소수 자릿수

    Returns:
        반올림한 값. 입력이 `None` 이면 `None`
    """
    return None if value is None else round(float(np.asarray(value).item()), digits)
