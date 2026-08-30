"""후보 판정 — 축별 집계표에서 방향성 우위 후보를 걸러낸다

루트 `CLAUDE.md` 「후보 판정 기준」을 코드로 옮긴 것이다. 규격만 문서에 두면 판정이 매번
일회용 스크립트로 이루어져 재현되지 않고 산출물에도 남지 않는다.

**판정은 두 겹이며 역할이 다르다.**

- **1차 게이트** (적중률 · 방향 기대값) — 볼 목록에 올릴지를 가른다
- **등급** (기준선 대비 차이 · 우연확률 · 시기 안정성) — 얼마나 믿을 만한지를 알려주되 **떨어뜨리지 않는다**

세 지표를 게이트로 쓰면 코드가 사용자 대신 판단하게 된다(측정의 원칙 1). 그렇다고 적중률
하나만 게이트로 두면 **기준선과 사실상 같은 칸까지 통과한다** — 주식은 원래 자주 올라
오른 비율이 절반을 넘는 칸이 흔하기 때문이다. 그래서 게이트에 방향 기대값을 함께 둔다.

**방향 기대값은 「같은 금액을 반복 투자했을 때 남는 수익률」이다.** 적중률만 보면
"방향은 맞지만 걸면 손실"인 칸을 거르지 못한다 — 자주 조금 맞고 가끔 크게 틀리는 칸이 실재한다.

**축을 모른다.** 만기월이든 요일이든 시기든, 축 컬럼 이름을 인자로 받아 그대로 쓴다.
어떤 축을 돌릴지는 그 검증이 정하고, 이 모듈은 받은 칸을 판정하기만 한다.
**정렬도 하지 않는다** — 무엇을 먼저 보여줄지는 표시 계층의 몫이다.

**방향을 가리지 않는다** (측정의 원칙 11). 오른 비율이 기준선보다 낮은 칸은 탈락이 아니라
**아래로 거는 후보**다. 판정은 기준선에서 얼마나 멀어졌는가(크기)로 하고, 부호는 방향을 알려줄 뿐이다.

**시기를 쪼갤 수 없으면 등급의 분모가 줄 뿐이다** (측정의 원칙 12). 표본이 모자라 물을 수
없었던 항목을 미충족으로 세면, 표본이 작다는 이유로 두 번 깎인다.

**전체 축과 시기 축이 같은 컬럼을 읽는다.** 방향이 「아래」면 두 축 모두 내린 비율을 그대로
쓴다 — 한쪽만 `1 − 오른 비율` 로 만들면 **보합이 「내림」으로 새어** 시기 항목이 관대해진다.
두 방향 비율은 여집합이 아니며, 그 정의는 `statistics.summarize` 가 소유한다.
"""

from typing import Final

import pandas as pd

from verify_lab.measure.statistics import (
    COL_DOWN_RATE_P_VALUE,
    COL_LOSS_RATE,
    COL_LOSS_RATE_EXCESS,
    COL_MEAN,
    COL_SAMPLE_COUNT,
    COL_UP_RATE_P_VALUE,
    COL_WIN_RATE,
    COL_WIN_RATE_EXCESS,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================
# 1차 게이트 (루트 CLAUDE.md 「후보 판정 기준」이 SoT)
# ============================================================

# 방향 적중률의 하한 (비율, 0.60 = 60%). 크기가 커도 적중률이 낮으면 집행할 수 없다
MIN_HIT_RATE: Final = 0.60

# 방향 기대값의 하한 (비율, 0.0 = 0%). **초과**여야 통과한다 — 반복 투자해 0 이 남는 것은 우위가 아니다.
# 거래비용을 반영하기로 하면 이 값이 그 자리다. 지금은 맨몸 성적이므로 0 이다 (측정의 원칙 10)
MIN_EXPECTED_VALUE: Final = 0.0

# ============================================================
# 등급 — 떨어뜨리지 않고 얼마나 믿을 만한지만 알려준다
# ============================================================

# 기준선 대비 차이의 하한 (비율, 0.10 = 10%p). **방향 무관 절대값이다.**
# 같은 적중률 60% 가 오르는 쪽에서는 기준선(55~59%) 대비 +2~5%p 에 불과하고
# 내리는 쪽에서는 기준선(41~45%) 대비 +15~19%p 다
MIN_BASELINE_GAP: Final = 0.10

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
COL_EXPECTED_VALUE = "ExpectedValue"
COL_BASELINE_HIT_RATE = "BaselineHitRate"
COL_BASELINE_GAP = "BaselineGap"
COL_P_VALUE = "PValue"
COL_PERIOD_MIN_HIT_RATE = "PeriodMinHitRate"
COL_PERIOD_COUNT = "PeriodCount"
COL_SCREEN = "Screen"
COL_SUPPORT_COUNT = "SupportCount"
COL_SUPPORT_TOTAL = "SupportTotal"
COL_UNMET_SUPPORT = "UnmetSupport"

# 방향. 신호가 기준선에서 어느 쪽으로 멀어졌는가
DIRECTION_UP: Final = "위"
DIRECTION_DOWN: Final = "아래"

# 1차 판정. **제외는 「우위가 없다」가 아니라 「이 목록에서는 빼둔다」이다** — 값은 산출물에 그대로 남는다
SCREEN_CANDIDATE: Final = "후보"
SCREEN_EXCLUDED: Final = "제외"

# 등급 항목의 이름. 무엇이 부족한지가 남지 않으면 기준을 조정했을 때 무엇이 달라지는지 알 수 없다
SUPPORT_GAP: Final = "차이"
SUPPORT_P_VALUE: Final = "우연확률"
SUPPORT_PERIOD: Final = "시기"

SCREENING_COLUMNS: Final = [
    COL_SAMPLE_COUNT,
    COL_DIRECTION,
    COL_HIT_RATE,
    COL_EXPECTED_VALUE,
    COL_BASELINE_HIT_RATE,
    COL_BASELINE_GAP,
    COL_P_VALUE,
    COL_PERIOD_COUNT,
    COL_PERIOD_MIN_HIT_RATE,
    COL_SCREEN,
    COL_SUPPORT_COUNT,
    COL_SUPPORT_TOTAL,
    COL_UNMET_SUPPORT,
]

# 집계표에서 읽는 입력 컬럼. 신호와 기준선의 두 방향 비율에 더해 **평균이 반드시 있어야 한다** —
# 평균 없이 게이트를 통과시키면 방향은 맞지만 걸면 손실인 칸이 후보로 올라간다
REQUIRED_SUMMARY_COLUMNS: Final = [
    COL_SAMPLE_COUNT,
    COL_MEAN,
    COL_WIN_RATE,
    COL_LOSS_RATE,
    COL_WIN_RATE_EXCESS,
    COL_LOSS_RATE_EXCESS,
]

# 시기 집계표에서 읽는 입력 컬럼. **두 방향 비율이 모두 있어야 한다** —
# 시기 항목도 전체 축과 같은 컬럼을 읽기 때문이며, 하나만 받아 나머지를 만들면 보합이 샌다
REQUIRED_PERIOD_COLUMNS: Final = [COL_WIN_RATE, COL_LOSS_RATE]


def screen_candidates(
    summary: pd.DataFrame,
    periods: pd.DataFrame,
    *,
    axis_column: str,
) -> pd.DataFrame:
    """축의 각 칸을 1차 게이트로 가르고 나머지 세 지표로 등급을 매긴다.

    **방향은 절대 비율이 아니라 기준선과의 거리로 정한다.** 주식은 원래 자주 올라
    오른 비율이 절반을 넘는 칸이 흔하므로, 절대 비율로 정하면 기준선보다 낮은 칸도 「위」가 된다.

    **제외된 칸도 행이 그대로 남는다.** 산출물에서 사라지면 사용자가 되짚을 수 없다.

    Args:
        summary: 축별 집계표. `REQUIRED_SUMMARY_COLUMNS` 와 두 방향의 우연확률이 있어야 한다
        periods: 축 × 시기 집계표. 비어 있으면 그 칸의 등급 분모가 준다
        axis_column: 축 컬럼 이름. 만기월·요일 등 무엇이든 받는다

    Returns:
        축 컬럼 뒤에 `SCREENING_COLUMNS` 가 붙은 판정표. **축 오름차순**이며 정렬은 하지 않는다

    Raises:
        ValueError: 필요한 컬럼이 없는 경우
    """
    required = [axis_column, *REQUIRED_SUMMARY_COLUMNS, COL_UP_RATE_P_VALUE, COL_DOWN_RATE_P_VALUE]
    missing = [column for column in required if column not in summary.columns]
    if missing:
        raise ValueError(f"집계표에 필수 컬럼이 없습니다: {missing}")

    # 시기표도 같은 강도로 본다. 컬럼이 없는 채로 넘기면 판정이 죽거나 시기 항목이 조용히 빠진다
    if not periods.empty:
        missing_periods = [
            column for column in (axis_column, *REQUIRED_PERIOD_COLUMNS) if column not in periods.columns
        ]
        if missing_periods:
            raise ValueError(f"시기 집계표에 필수 컬럼이 없습니다: {missing_periods}")

    rows = [
        _screen_cell(cell.iloc[0], periods, axis_column=axis_column)
        for _, cell in summary.groupby(axis_column, sort=True)
    ]
    result = pd.DataFrame(rows, columns=[axis_column, *SCREENING_COLUMNS])

    candidates = int((result[COL_SCREEN] == SCREEN_CANDIDATE).sum())
    logger.debug(f"후보 판정 완료: {len(result)}칸 중 후보 {candidates}")

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

    # 아래로 거는 신호는 주가가 내릴 때 버는 것이므로 평균의 부호를 뒤집는다
    expected_value = -float(row[COL_MEAN]) if downward else float(row[COL_MEAN])

    cell_periods = periods[periods[axis_column] == row[axis_column]] if not periods.empty else periods

    # 시기 항목도 전체 축과 **같은 컬럼**을 읽는다. `1 − 오른 비율` 로 내린 비율을 만들면
    # **보합이 통째로 「내림」으로 새어** 값이 부풀고 등급이 관대해진다 — 두 비율은 여집합이 아니다
    # (`statistics.summarize` 의 방향 비율 정의)
    rate_column = COL_LOSS_RATE if downward else COL_WIN_RATE
    period_rates = [float(value) for value in cell_periods[rate_column]] if not cell_periods.empty else []

    screened = hit_rate >= MIN_HIT_RATE and expected_value > MIN_EXPECTED_VALUE

    # 시기 항목은 **물을 수 있었을 때만** 등급에 넣는다. 표본이 모자라 못 물은 것을
    # 미충족으로 세면 표본이 작다는 이유로 두 번 깎인다
    checks: list[tuple[str, bool]] = [
        (SUPPORT_GAP, abs(gap) >= MIN_BASELINE_GAP),
        (SUPPORT_P_VALUE, p_value < MAX_P_VALUE),
    ]
    if period_rates:
        checks.append((SUPPORT_PERIOD, min(period_rates) >= MIN_PERIOD_HIT_RATE))

    unmet = [name for name, met in checks if not met]

    return {
        axis_column: row[axis_column],
        COL_SAMPLE_COUNT: int(row[COL_SAMPLE_COUNT]),
        COL_DIRECTION: DIRECTION_DOWN if downward else DIRECTION_UP,
        COL_HIT_RATE: hit_rate,
        COL_EXPECTED_VALUE: expected_value,
        COL_BASELINE_HIT_RATE: hit_rate - gap,
        COL_BASELINE_GAP: gap,
        COL_P_VALUE: p_value,
        COL_PERIOD_COUNT: len(period_rates),
        COL_PERIOD_MIN_HIT_RATE: min(period_rates) if period_rates else float("nan"),
        COL_SCREEN: SCREEN_CANDIDATE if screened else SCREEN_EXCLUDED,
        COL_SUPPORT_COUNT: len(checks) - len(unmet),
        COL_SUPPORT_TOTAL: len(checks),
        COL_UNMET_SUPPORT: " · ".join(unmet),
    }
