"""후보 판정 — 축별 집계표에서 방향성 우위 후보를 걸러낸다

루트 `CLAUDE.md` 「후보 판정 기준」을 코드로 옮긴 것이다. 규격만 문서에 두면 판정이 매번
일회용 스크립트로 이루어져 재현되지 않고 산출물에도 남지 않는다.

**판정은 게이트 하나뿐이다** — 적중률과 방향 기대값. 이것 말고는 아무것도 떨어뜨리지 않는다.

전에는 게이트 위에 「등급」(기준선 대비 차이·우연확률·시기 안정성·손익비)을 두어 「충족/물음」을
셌고, 매매 계층이 **같은 것을 다른 기준으로 또 물었다**(등급의 시기는 55%, 구간 게이트는 60%).
**2026-09-12 에 전부 걷어냈다** — 판단은 사용자가 하고, 이 모듈은 볼 목록만 만든다.
그 결과 판정이 느슨해져 후보가 늘어나는 것은 **의도한 대가**다.

**방향 기대값은 「같은 금액을 반복 투자했을 때 남는 수익률」이다.** 적중률만 보면
"방향은 맞지만 걸면 손실"인 칸을 거르지 못한다 — 자주 조금 맞고 가끔 크게 틀리는 칸이 실재한다.

**표본 하한을 걸지 않는다.** 1건짜리 칸도 판정한다. 그런 칸이 과대평가라는 것은 `표본` 컬럼이
말해 주며, 뺄지는 사용자가 신호를 보고 정한다 (2026-09-12 사용자 결정).
**다만 0건은 다르다** — 잴 것이 없으므로 판정하지 않고 「판정 안 함」이 된다.

**살 수 없는 대상은 판정하지 않는다** (측정의 원칙 9). 지수는 긴 시계열을 참고하려고 재지만,
**그 결과로 「우위가 있다」를 주장하면 집행할 수 없는 성적을 근거로 삼게 된다.** 값은 그대로
내고 `1차 판정` 만 「판정 안 함」이 된다 — 판정을 막는 것이지 값을 지우는 것이 아니다.

**회당 기대값과 함께 합산 수익률을 낸다** (루트 `CLAUDE.md` 측정의 원칙 16). 신호가 드물거나
보유가 며칠짜리인 매매법은 회당 평균이 구조적으로 작게 나와 크기 감각을 주지 못하고, 왕복
수수료와 견줄 값인지도 그 자리에서 보이지 않는다. **표본 수가 같은 표에 있어야 한다** —
합산은 표본이 많을수록 커지므로 표본 없이 칸끼리 비교하면 기간이 긴 칸이 자동으로 이긴다.
**게이트는 회당 기대값 그대로이며 합산은 표시용이다.**

**축을 모른다.** 만기월이든 요일이든 시기든, 축 컬럼 이름을 인자로 받아 그대로 쓴다.
어떤 축을 돌릴지는 그 검증이 정하고, 이 모듈은 받은 칸을 판정하기만 한다.
**정렬도 하지 않는다** — 무엇을 먼저 보여줄지는 표시 계층의 몫이다.

**방향을 가리지 않는다** (측정의 원칙 11). 오른 비율이 기준선보다 낮은 칸은 탈락이 아니라
**아래로 거는 후보**다. 판정은 기준선에서 얼마나 멀어졌는가(크기)로 하고, 부호는 방향을 알려줄 뿐이다.

**그래서 기준선은 지웠다가 다시 넣을 수 있는 표시값이 아니라 방향을 정하는 재료다.**
절대 비율로 방향을 정하면 주식이 원래 자주 오르는 탓에 기준선보다 «낮은» 칸까지 「위」가 된다 —
옵션 만기일 60칸으로 재면 두 방식에서 **12칸의 방향이 갈리고 1칸의 판정이 뒤집힌다.**
두 방향 비율은 여집합이 아니며, 그 정의는 `statistics.summarize` 가 소유한다.
"""

from typing import Final

import pandas as pd

from verify_lab.measure.statistics import (
    COL_LOSS_RATE,
    COL_LOSS_RATE_EXCESS,
    COL_MEAN,
    COL_SAMPLE_COUNT,
    COL_WIN_RATE,
    COL_WIN_RATE_EXCESS,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================
# 게이트 (루트 CLAUDE.md 「후보 판정 기준」이 SoT)
# ============================================================

# 방향 적중률의 하한 (비율, 0.60 = 60%). 크기가 커도 적중률이 낮으면 집행할 수 없다
MIN_HIT_RATE: Final = 0.60

# 방향 기대값의 하한 (비율, 0.0 = 0%). **초과**여야 통과한다 — 반복 투자해 0 이 남는 것은 우위가 아니다.
# 거래비용을 반영하기로 하면 이 값이 그 자리다. 지금은 맨몸 성적이므로 0 이다 (측정의 원칙 10)
MIN_EXPECTED_VALUE: Final = 0.0

# ============================================================
# 판정 결과 스키마
# ============================================================

COL_DIRECTION = "Direction"
COL_HIT_RATE = "HitRate"
COL_EXPECTED_VALUE = "ExpectedValue"
COL_TOTAL_RETURN = "TotalReturn"
COL_BASELINE_HIT_RATE = "BaselineHitRate"
COL_BASELINE_GAP = "BaselineGap"
COL_SCREEN = "Screen"

# 방향. 신호가 기준선에서 어느 쪽으로 멀어졌는가
DIRECTION_UP: Final = "위"
DIRECTION_DOWN: Final = "아래"

# 1차 판정. **제외는 「우위가 없다」가 아니라 「이 목록에서는 빼둔다」이다** — 값은 산출물에 그대로 남는다.
# **「판정 안 함」은 또 다른 사실이다** — 합격도 불합격도 «묻지 않았다»는 뜻이며 이유가 둘이다:
# ① 살 수 없는 대상(지수) ② 표본이 0건이라 잴 것이 없는 칸.
# 제외와 한 값으로 합치면 **「재봤더니 아니었다」와 「재본 적이 없다」가 구별되지 않는다**
SCREEN_CANDIDATE: Final = "후보"
SCREEN_EXCLUDED: Final = "제외"
SCREEN_NOT_JUDGED: Final = "판정 안 함"

SCREENING_COLUMNS: Final = [
    COL_SAMPLE_COUNT,
    COL_DIRECTION,
    COL_HIT_RATE,
    COL_EXPECTED_VALUE,
    COL_TOTAL_RETURN,
    COL_BASELINE_HIT_RATE,
    COL_BASELINE_GAP,
    COL_SCREEN,
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


def screen_candidates(
    summary: pd.DataFrame,
    *,
    axis_column: str,
    tradable: bool,
) -> pd.DataFrame:
    """축의 각 칸을 게이트로 가른다.

    **방향은 절대 비율이 아니라 기준선과의 거리로 정한다.** 주식은 원래 자주 올라
    오른 비율이 절반을 넘는 칸이 흔하므로, 절대 비율로 정하면 기준선보다 낮은 칸도 「위」가 된다.

    **제외된 칸도 행이 그대로 남는다.** 산출물에서 사라지면 사용자가 되짚을 수 없다.

    Args:
        summary: 축별 집계표. `REQUIRED_SUMMARY_COLUMNS` 가 있어야 한다
        axis_column: 축 컬럼 이름. 만기월·요일 등 무엇이든 받는다
        tradable: 살 수 있는 대상인가. `False` 면 값만 내고 판정하지 않는다 —
            지수가 그 경우이며 `1차 판정` 이 전부 「판정 안 함」이 된다.
            **기본값을 두지 않는다** — 기본이 「살 수 있다」면 지수를 받는 호출처가 인자를
            빠뜨렸을 때 **틀린 판정이 조용히 나간다**. `strategy.constants.stop_level_value`
            의 `measurable` 과 같은 이유다

    Returns:
        축 컬럼 뒤에 `SCREENING_COLUMNS` 가 붙은 판정표. **축 오름차순**이며 정렬은 하지 않는다

    Raises:
        ValueError: 필요한 컬럼이 없는 경우
    """
    required = [axis_column, *REQUIRED_SUMMARY_COLUMNS]
    missing = [column for column in required if column not in summary.columns]
    if missing:
        raise ValueError(f"집계표에 필수 컬럼이 없습니다: {missing}")

    rows = [
        _screen_cell(cell.iloc[0], axis_column=axis_column, tradable=tradable)
        for _, cell in summary.groupby(axis_column, sort=True)
    ]
    result = pd.DataFrame(rows, columns=[axis_column, *SCREENING_COLUMNS])

    candidates = int((result[COL_SCREEN] == SCREEN_CANDIDATE).sum())
    judged = "판정함" if tradable else "판정 안 함"
    logger.debug(f"후보 판정 완료: {len(result)}칸 중 후보 {candidates} ({judged})")

    return result


def _screen_cell(row: pd.Series, *, axis_column: str, tradable: bool) -> dict[str, object]:
    """한 칸을 판정한다.

    Args:
        row: 집계표의 한 줄
        axis_column: 축 컬럼 이름
        tradable: 살 수 있는 대상인가

    Returns:
        판정표 한 줄
    """
    sample_count = int(row[COL_SAMPLE_COUNT])

    downward = float(row[COL_LOSS_RATE_EXCESS]) > float(row[COL_WIN_RATE_EXCESS])
    hit_rate = float(row[COL_LOSS_RATE] if downward else row[COL_WIN_RATE])
    gap = float(row[COL_LOSS_RATE_EXCESS] if downward else row[COL_WIN_RATE_EXCESS])

    # 아래로 거는 신호는 주가가 내릴 때 버는 것이므로 평균의 부호를 뒤집는다
    expected_value = -float(row[COL_MEAN]) if downward else float(row[COL_MEAN])

    # 같은 금액을 표본 수만큼 반복 투자했을 때의 단순 합 (측정의 원칙 16). 신호가 드문
    # 매매법은 회당 평균이 구조적으로 작아 크기 감각을 주지 못하므로 둘을 나란히 낸다.
    # **게이트에는 쓰지 않는다** — 표시용이며 판정 기준을 바꾸지 않는다
    total_return = expected_value * sample_count

    screened = hit_rate >= MIN_HIT_RATE and expected_value > MIN_EXPECTED_VALUE

    # **「판정 안 함」이 게이트 결과를 덮는다.** 묻지 않은 칸에는 합격도 불합격도 없다.
    # **표본 0건을 함께 거른다** — 그 칸의 적중률·평균은 `NaN` 이고 비교가 전부 거짓이 되어
    # 가만히 두면 **「제외」로 찍힌다.** 「재봤더니 아니었다」와 「재본 적이 없다」는 다른 사실이다.
    # **표본 하한은 걸지 않는다** — 1건짜리도 판정하며, 과대평가는 `표본` 컬럼이 말해 준다
    if not tradable or sample_count == 0:
        verdict = SCREEN_NOT_JUDGED
    else:
        verdict = SCREEN_CANDIDATE if screened else SCREEN_EXCLUDED

    return {
        axis_column: row[axis_column],
        COL_SAMPLE_COUNT: int(row[COL_SAMPLE_COUNT]),
        COL_DIRECTION: DIRECTION_DOWN if downward else DIRECTION_UP,
        COL_HIT_RATE: hit_rate,
        COL_EXPECTED_VALUE: expected_value,
        COL_TOTAL_RETURN: total_return,
        COL_BASELINE_HIT_RATE: hit_rate - gap,
        COL_BASELINE_GAP: gap,
        COL_SCREEN: verdict,
    }
