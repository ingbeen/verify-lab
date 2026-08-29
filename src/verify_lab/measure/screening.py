"""후보 판정 — 축별 집계표에서 방향성 우위 후보를 걸러낸다

루트 `CLAUDE.md` 「후보 판정 기준」의 네 조건을 코드로 옮긴 것이다. 규격만 문서에 두면
판정이 매번 일회용 스크립트로 이루어져 재현되지 않고 산출물에도 남지 않는다.

**축을 모른다.** 만기월이든 요일이든 시기든, 축 컬럼 이름을 인자로 받아 그대로 쓴다.
어떤 축을 돌릴지는 그 검증이 정하고, 이 모듈은 받은 칸을 판정하기만 한다.

**방향을 가리지 않는다** (측정의 원칙 11). 오른 비율이 기준선보다 낮은 칸은 탈락이 아니라
**아래로 거는 후보**다. 판정은 기준선에서 얼마나 멀어졌는가(크기)로 하고, 부호는 방향을 알려줄 뿐이다.

**시기를 쪼갤 수 없으면 탈락이 아니라 보류다** (측정의 원칙 12). 표본이 모자란 것과
기준에 못 미치는 것은 다르며, 둘을 같이 묶으면 나중에 "왜 떨어졌나"를 되물을 수 없다.
"""

from typing import Final

import pandas as pd

from verify_lab.measure.statistics import (
    COL_DOWN_RATE_P_VALUE,
    COL_LOSS_RATE,
    COL_LOSS_RATE_EXCESS,
    COL_SAMPLE_COUNT,
    COL_UP_RATE_P_VALUE,
    COL_WIN_RATE,
    COL_WIN_RATE_EXCESS,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================
# 판정 기준 (루트 CLAUDE.md 「후보 판정 기준」이 SoT)
# ============================================================

# 기준선 대비 차이의 하한 (비율, 0.10 = 10%p). **방향 무관 절대값이다.**
# 같은 적중률 60% 가 오르는 쪽에서는 기준선(55~59%) 대비 +2~5%p 에 불과하고
# 내리는 쪽에서는 기준선(41~45%) 대비 +15~19%p 다. 이 기준이 없으면 오르는 쪽이 부당하게 쉽게 통과한다
MIN_BASELINE_GAP: Final = 0.10

# 방향 적중률의 하한 (비율, 0.60 = 60%). 크기가 커도 적중률이 낮으면 집행할 수 없다
MIN_HIT_RATE: Final = 0.60

# 우연확률의 상한. 관습적인 선이며 자연법칙이 아니다 — 0.049 와 0.051 은 사실상 같다
MAX_P_VALUE: Final = 0.05

# 시기별 적중률의 하한 (비율, 0.55 = 55%). 전체 하한보다 낮다 —
# 쪼개면 표본이 절반이 되어 흔들림이 커지므로, 같은 선을 요구하면 실체가 있는 칸도 떨어진다
MIN_PERIOD_HIT_RATE: Final = 0.55

# ============================================================
# 판정 결과 스키마
# ============================================================

COL_DIRECTION = "Direction"
COL_HIT_RATE = "HitRate"
COL_BASELINE_HIT_RATE = "BaselineHitRate"
COL_BASELINE_GAP = "BaselineGap"
COL_P_VALUE = "PValue"
COL_PERIOD_MIN_HIT_RATE = "PeriodMinHitRate"
COL_PERIOD_COUNT = "PeriodCount"
COL_VERDICT = "Verdict"
COL_FAILED_CRITERIA = "FailedCriteria"

# 방향. 신호가 기준선에서 어느 쪽으로 멀어졌는가
DIRECTION_UP: Final = "위"
DIRECTION_DOWN: Final = "아래"

# 판정. **보류는 탈락이 아니다** — 시기를 쪼갤 표본이 모자라 기준 4 를 물을 수 없었다는 뜻이다
VERDICT_PASS: Final = "통과"
VERDICT_FAIL: Final = "탈락"
VERDICT_HELD: Final = "보류"

# 떨어진 기준의 번호. 왜 떨어졌는지가 남지 않으면 기준을 조정했을 때 무엇이 달라지는지 알 수 없다
CRITERION_GAP: Final = "1(차이)"
CRITERION_HIT_RATE: Final = "2(적중률)"
CRITERION_P_VALUE: Final = "3(우연확률)"
CRITERION_PERIOD: Final = "4(시기)"

SCREENING_COLUMNS: Final = [
    COL_SAMPLE_COUNT,
    COL_DIRECTION,
    COL_HIT_RATE,
    COL_BASELINE_HIT_RATE,
    COL_BASELINE_GAP,
    COL_P_VALUE,
    COL_PERIOD_COUNT,
    COL_PERIOD_MIN_HIT_RATE,
    COL_VERDICT,
    COL_FAILED_CRITERIA,
]

# 집계표에서 읽는 입력 컬럼. 신호와 기준선의 두 방향 비율이 모두 있어야 한다
REQUIRED_SUMMARY_COLUMNS: Final = [
    COL_SAMPLE_COUNT,
    COL_WIN_RATE,
    COL_LOSS_RATE,
    COL_WIN_RATE_EXCESS,
    COL_LOSS_RATE_EXCESS,
]


def screen_candidates(
    summary: pd.DataFrame,
    periods: pd.DataFrame,
    *,
    axis_column: str,
) -> pd.DataFrame:
    """축의 각 칸을 후보 판정 기준 네 개로 거른다.

    **방향은 절대 비율이 아니라 기준선과의 거리로 정한다.** 주식은 원래 자주 올라
    오른 비율이 절반을 넘는 칸이 흔하므로, 절대 비율로 정하면 기준선보다 낮은 칸도 「위」가 된다.

    **보류는 탈락이 아니다.** 앞 세 기준을 통과했는데 시기를 쪼갤 표본이 없으면 보류로 남긴다 —
    기준 4 를 물을 수 없었다는 뜻이지 못 넘었다는 뜻이 아니다. 이미 다른 기준에 걸린 칸은
    보류로 두지 않는다. 통과 가능성이 남은 것처럼 읽히기 때문이다.

    Args:
        summary: 축별 집계표. `REQUIRED_SUMMARY_COLUMNS` 와 두 방향의 우연확률이 있어야 한다
        periods: 축 × 시기 집계표. 비어 있으면 그 칸은 보류가 된다
        axis_column: 축 컬럼 이름. 만기월·요일 등 무엇이든 받는다

    Returns:
        축 컬럼 뒤에 `SCREENING_COLUMNS` 가 붙은 판정표

    Raises:
        ValueError: 필요한 컬럼이 없는 경우
    """
    required = [axis_column, *REQUIRED_SUMMARY_COLUMNS, COL_UP_RATE_P_VALUE, COL_DOWN_RATE_P_VALUE]
    missing = [column for column in required if column not in summary.columns]
    if missing:
        raise ValueError(f"집계표에 필수 컬럼이 없습니다: {missing}")

    rows = [
        _screen_cell(cell.iloc[0], periods, axis_column=axis_column)
        for _, cell in summary.groupby(axis_column, sort=True)
    ]
    result = pd.DataFrame(rows, columns=[axis_column, *SCREENING_COLUMNS])

    passed = int((result[COL_VERDICT] == VERDICT_PASS).sum())
    held = int((result[COL_VERDICT] == VERDICT_HELD).sum())
    logger.debug(f"후보 판정 완료: {len(result)}칸 중 통과 {passed} · 보류 {held}")

    return result


def _screen_cell(row: pd.Series, periods: pd.DataFrame, *, axis_column: str) -> dict[str, object]:
    """한 칸을 판정한다.

    Args:
        row: 집계표의 한 줄
        periods: 축 × 시기 집계표 전체
        axis_column: 축 컬럼 이름

    Returns:
        판정표 한 줄
    """
    downward = float(row[COL_LOSS_RATE_EXCESS]) > float(row[COL_WIN_RATE_EXCESS])
    hit_rate = float(row[COL_LOSS_RATE] if downward else row[COL_WIN_RATE])
    gap = float(row[COL_LOSS_RATE_EXCESS] if downward else row[COL_WIN_RATE_EXCESS])
    p_value = float(row[COL_DOWN_RATE_P_VALUE if downward else COL_UP_RATE_P_VALUE])

    cell_periods = periods[periods[axis_column] == row[axis_column]] if not periods.empty else periods
    period_rates = (
        [float(1.0 - value if downward else value) for value in cell_periods[COL_WIN_RATE]]
        if not cell_periods.empty
        else []
    )

    failed: list[str] = []
    if abs(gap) < MIN_BASELINE_GAP:
        failed.append(CRITERION_GAP)
    if hit_rate < MIN_HIT_RATE:
        failed.append(CRITERION_HIT_RATE)
    if p_value >= MAX_P_VALUE:
        failed.append(CRITERION_P_VALUE)
    if period_rates and min(period_rates) < MIN_PERIOD_HIT_RATE:
        failed.append(CRITERION_PERIOD)

    if failed:
        verdict = VERDICT_FAIL
    elif not period_rates:
        verdict = VERDICT_HELD
    else:
        verdict = VERDICT_PASS

    return {
        axis_column: row[axis_column],
        COL_SAMPLE_COUNT: int(row[COL_SAMPLE_COUNT]),
        COL_DIRECTION: DIRECTION_DOWN if downward else DIRECTION_UP,
        COL_HIT_RATE: hit_rate,
        COL_BASELINE_HIT_RATE: hit_rate - gap,
        COL_BASELINE_GAP: gap,
        COL_P_VALUE: p_value,
        COL_PERIOD_COUNT: len(period_rates),
        COL_PERIOD_MIN_HIT_RATE: min(period_rates) if period_rates else float("nan"),
        COL_VERDICT: verdict,
        COL_FAILED_CRITERIA: " · ".join(failed),
    }
