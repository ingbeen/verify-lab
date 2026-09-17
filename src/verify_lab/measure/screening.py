"""후보 판정 — 축별 집계표에서 방향성 우위 후보를 걸러낸다

루트 `CLAUDE.md` 「후보 판정 기준」을 코드로 옮긴 것이다. 규격만 문서에 두면 판정이 매번
일회용 스크립트로 이루어져 재현되지 않고 산출물에도 남지 않는다.

**판정은 게이트 하나뿐이고 «조건도 하나»다** — 방향 기대값이 하한 이상인가
(2026-09-17 사용자 확정). 적중률 하한을 함께 걸던 것을 걷어냈다.
이것 말고는 아무것도 떨어뜨리지 않는다.

**이 모듈의 함수는 둘이고 하는 일이 다르다.**

| 함수 | 답하는 것 | 쓰는 곳 |
| --- | --- | --- |
| `screen_verdict` | **걸 만한가** — 후보 / 제외 / 판정 안 함 | `execution/periods.py` 가 성적표 행마다 부른다 |
| `direction_profile` | **어느 쪽으로 얼마나** — 방향·적중률·기대값·합산 | 축별 집계표가 필요한 곳 (월말의 집행 축) |

**게이트의 소유자는 `screen_verdict` 하나다.** 1차 판정이 나가는 자리는 `성적표.csv` 뿐이므로
(`src/verify_lab/CLAUDE.md` 「매매 산출물 계약」) **축별 «판정표»를 만드는 함수를 두지 않는다** —
두면 같은 판정이 두 표에 실리고 한쪽이 낡는다.

**`direction_profile` 은 판정하지 않으므로 `tradable` 을 받지 않는다.** 방향과 크기는 살 수 있든
없든 사실이고, 「이 대상으로 판정하는가」는 게이트의 질문이다.

**게이트 위에 「등급」(기준선 대비 차이·우연확률·시기 안정성·손익비)을 얹지 않는다.** 얹으면
매매 계층이 **같은 것을 다른 기준으로 또 묻게 된다** — 시기를 등급은 55% 로, 구간 게이트는
60% 로 물어 같은 질문에 답이 갈린다. 판단은 사용자가 하고, 이 모듈은 볼 목록만 만든다.
그 대가로 판정이 느슨해져 후보가 늘어나는 것은 **의도한 것**이다.

**방향 기대값은 「같은 금액을 반복 투자했을 때 남는 수익률」이다.** 이것 하나로 거르는 것은
**적중률이 그 안에 이미 들어 있기 때문이다** — "자주 조금 맞고 가끔 크게 틀리는" 칸은
적중률이 높아도 기대값이 하한에 못 미쳐 걸린다. 반대는 성립하지 않아 **적중률만으로는
그 칸을 거르지 못하고**, 그래서 남긴 쪽이 기대값이다.

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
**우선순위로 줄 세우지 않는다** — 축 오름차순으로 낼 뿐이고, 무엇을 먼저 보여줄지는
표시 계층의 몫이다.

**대신 «축당 한 행»을 요구한다.** 축을 모르므로 어느 행을 고를지도 모른다 — 둘 이상이 오면
고르지 않고 거부한다. 식별 컬럼(종목·방향 등)은 판정이 끝난 뒤 실행 계층이 붙이므로,
여기 오는 표는 이미 한 대상의 것이어야 한다.

**방향을 가리지 않는다** (측정의 원칙 11). 오른 비율이 낮은 칸은 탈락이 아니라
**아래로 거는 후보**다. 부호는 어느 쪽에 거는지를 알려줄 뿐이다.

**방향은 1배 롱의 «오른/내린 비율» 로 정한다.** 두 비율 중 큰 쪽이 거는 방향이다.
두 방향 비율은 여집합이 아니며(보합이 어느 쪽에도 안 들어간다) 그 정의는
`statistics.summarize` 가 소유한다.
**이것은 «방향 표»의 규칙이고 게이트와 무관하다** — 게이트는 기대값 하나만 본다.

**기준선을 방향 결정에서 뺐다** (2026-09-15). 기준선 대비 초과분으로 방향을 정하면 **칸마다
다른 허들**이 서고(월말 기준선 24.9~73.2%), 기준선이 높은 칸에서 멀쩡한 우위가 뒤집힌다 —
실측으로 두 검증 156칸에서 기준선 방식이 **더해 주는 칸은 0개**이고 **5칸을 빼기만 했다**.
KODEX 코스닥150 8월은 오른 비율 63.6% · 회당 +2.11% 인데 기준선 66.2% 에 걸려
「아래 36.4%」로 뒤집혀 제외됐다.

**판정표에서도 기준선을 뺐다** (2026-09-16). 기준선은 「이 신호가 시장 전체와 다른가」를 묻고
판정은 「걸 만한가」를 묻는다 — **다른 질문이다.** 판정에 안 쓰는 축을 판정표에 실으면 읽는
사람이 그것으로 거른다: 실제로 「기준선과 같으니 그냥 들고 있는 것과 다를 바 없다」는 잘못된
탈락 근거로 읽혔다. **기준선이 80% 인 칸에서 신호도 80% 면 그 신호에 특별함은 없어도 80% 로
이기는 매매인 것은 그대로**이고, 이벤트형은 그 성적을 **연 며칠의 노출로** 얻는다 —
365일 묶여 같은 성적을 내는 것과 자본 효율이 다르다.
**값은 `통계.csv` 계열이 기준선 14컬럼과 차이 4컬럼으로 그대로 담는다.**
근거는 루트 `CLAUDE.md` 「기준선은 탈락 사유가 아니다」가 SoT 다.
"""

import math
from typing import Final

import pandas as pd

from verify_lab.measure.statistics import (
    COL_LOSS_RATE,
    COL_MEAN,
    COL_SAMPLE_COUNT,
    COL_WIN_RATE,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================
# 게이트 (루트 CLAUDE.md 「후보 판정 기준」이 SoT)
# ============================================================

# 방향 기대값의 하한 (비율, 0.01 = 1%). **이상**이면 통과한다.
#
# **게이트는 이 하나뿐이다** (2026-09-17 사용자 확정). 적중률 하한(`MIN_HIT_RATE`, 60%)이
# 함께 있었으나 걷어냈다 — **조건은 하나다.** 그래서 이 모듈에 적중률 하한 상수가 없다:
# 게이트 밖에서 쓰던 곳이 없었으므로 남기면 결론이 난 축의 잔여물이 된다.
# **적중률 자체는 사라지지 않는다** — 성적표의 `승률(%)` 과 방향 표의 `적중률(%)` 로 그대로
# 나가며, 그것으로 칸을 거를지는 사용자가 정한다.
#
# **사용자가 정한 최소 회당 기대값이지 거래비용이 아니다** (2026-09-17 사용자 확정).
# 성적은 여전히 맨몸이며(측정의 원칙 10) **거래비용을 반영하기로 하면 그것은 이 값 «위에»
# 더해진다** — 비용을 문턱으로 쓰지 않는다는 결정은 `docs/조사/투자금_결정/규칙.md` §3.2 가 SoT 다.
#
# **이 값을 바꾸면 산출물의 `1차 판정` 이 통째로 달라진다.** 그래서
# `tests/test_measure_screening.py` 의 `TestGateValues` 가 값을 손으로 박아 두었다 —
# 나머지 경계 테스트는 이 상수에서 파생되므로 **그것만으로는 값 변경이 아무것도 실패시키지 않는다**
MIN_EXPECTED_VALUE: Final = 0.01

# ============================================================
# 판정 결과 스키마
# ============================================================

COL_DIRECTION = "Direction"
COL_HIT_RATE = "HitRate"
COL_EXPECTED_VALUE = "ExpectedValue"
COL_TOTAL_RETURN = "TotalReturn"
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

# 방향 표의 컬럼. **판정을 싣지 않는다** — 1차 판정이 나가는 자리는 `성적표.csv` 뿐이다.
# 판정에 안 쓰는 축을 함께 실으면 읽는 사람이 그것으로 거른다
DIRECTION_COLUMNS: Final = [
    COL_SAMPLE_COUNT,
    COL_DIRECTION,
    COL_HIT_RATE,
    COL_EXPECTED_VALUE,
    COL_TOTAL_RETURN,
]

# 집계표에서 읽는 입력 컬럼. 두 방향 비율에 더해 **평균이 반드시 있어야 한다** —
# 평균 없이 게이트를 통과시키면 방향은 맞지만 걸면 손실인 칸이 후보로 올라간다.
#
# **기준선 초과분을 요구하지 않는다.** 쓰지 않는 값을 계속 요구하면 호출하는 쪽이 그것을
# 계산해 넘겨야 하고, 그러면 「빼지 않은 것」과 같아진다
REQUIRED_SUMMARY_COLUMNS: Final = [
    COL_SAMPLE_COUNT,
    COL_MEAN,
    COL_WIN_RATE,
    COL_LOSS_RATE,
]


def screen_verdict(
    *,
    expected_value: float,
    sample_count: int,
    tradable: bool,
) -> str:
    """한 칸의 1차 판정을 낸다. **게이트의 소유자는 이 함수 하나다.**

    **조건은 하나다** — 방향 기대값이 하한 이상인가 (2026-09-17 사용자 확정).
    적중률 하한을 함께 걸던 것을 걷어냈다.

    **방향을 정하지 않는다.** 부르는 쪽이 이미 방향을 알고 그 방향으로 기대값을 계산해 넘긴다 —
    성적표는 행마다 방향이 확정돼 있어 평균이 곧 그 방향의 값이다.

    [중요] **한 칸의 두 방향이 모두 후보가 될 수 있는지는 이 함수가 보장하지 않는다.**
    적중률 하한이 있던 시절에는 두 방향 비율의 합이 100% 를 넘지 못해 **구조적으로** 하나만
    통과했다. 지금은 그 보장이 없고, 대신 **두 방향의 평균이 서로 부호가 반대**라는 사실이
    같은 일을 한다 — 다만 손절이 손실만 끊어 두 값의 크기가 대칭이 아니므로 **보장이 아니라
    관찰**이다. 실측으로 세 매매법 전 칸에서 0건이며 그 사실은 산출물 대조로 확인한다.

    **스칼라를 받는 이유**: 판정이 나가는 자리가 성적표뿐인데 그 표는 방향과 손절선이 확정된
    «체결» 결과라 집계표 모양을 만들 수 없다. 그렇다고 판정을 거기서 다시 구현하면
    **같은 칸이 표마다 다르게 판정된다** (패키지 절대 원칙 5).

    Args:
        expected_value: 방향 기대값 (비율). 「아래」 칸은 평균의 부호를 뒤집은 값이다
        sample_count: 표본 수. **하한을 걸지 않는다** — 1건도 판정하며 과대평가 가능성은
            표본 수를 보고 사용자가 판단한다 (2026-09-12 사용자 결정)
        tradable: **판정 대상인가.** 거짓이면 게이트 결과와 무관하게 「판정 안 함」이다 —
            지수(살 수 없다)와 인버스 실물(1배 롱이 같은 질문에 이미 답한다)이 그 경우다

    Returns:
        `SCREEN_CANDIDATE` · `SCREEN_EXCLUDED` · `SCREEN_NOT_JUDGED` 중 하나
    """
    # **「판정 안 함」이 게이트 결과를 덮는다.** 묻지 않은 칸에는 합격도 불합격도 없다.
    # **결측을 함께 거른다** — `NaN` 과의 비교는 전부 거짓이라 가드가 없으면 조용히 「제외」가
    # 되고, 그러면 「재봤더니 아니었다」와 「재본 적이 없다」가 구별되지 않는다
    if not tradable or sample_count == 0:
        return SCREEN_NOT_JUDGED
    if math.isnan(expected_value):
        return SCREEN_NOT_JUDGED

    return SCREEN_CANDIDATE if expected_value >= MIN_EXPECTED_VALUE else SCREEN_EXCLUDED


def direction_profile(summary: pd.DataFrame, *, axis_column: str) -> pd.DataFrame:
    """축의 각 칸이 **어느 쪽으로 얼마나** 치우쳤는지 낸다.

    **판정하지 않는다.** 1차 판정이 나가는 자리는 `성적표.csv` 뿐이므로(`src/verify_lab/CLAUDE.md`
    「매매 산출물 계약」) 여기서 판정을 내면 같은 판정이 두 표에 실리고 한쪽이 낡는다.
    같은 이유로 `tradable` 을 받지 않는다 — 방향과 크기는 살 수 있든 없든 사실이고,
    「이 대상으로 판정하는가」는 게이트의 질문이다.

    **방향은 두 방향 비율 중 큰 쪽이다.** 기준선과의 거리로 정하지 않는다 —
    칸마다 다른 허들이 서서 기준선이 높은 칸의 우위가 뒤집힌다 (모듈 docstring 의 실측).

    **결과에 기준선이 없다.** 판정이 묻지 않는 축이라 빼는 것이며, 값은 같은 폴더의
    `통계.csv` 계열이 담는다.

    **치우치지 않은 칸도 행이 그대로 남는다.** 산출물에서 사라지면 사용자가 되짚을 수 없다.

    Args:
        summary: 축별 집계표. `REQUIRED_SUMMARY_COLUMNS` 가 있어야 하고
            **축 값마다 행이 하나**여야 한다
        axis_column: 축 컬럼 이름. 만기월·격자 칸 등 무엇이든 받는다

    Returns:
        축 컬럼 뒤에 `DIRECTION_COLUMNS` 가 붙은 표. **축 오름차순**이며
        우선순위로 줄 세우지 않는다

    Raises:
        ValueError: 필요한 컬럼이 없거나, **축 값이 비었거나, 한 축 값에 행이 둘 이상인 경우**
    """
    required = [axis_column, *REQUIRED_SUMMARY_COLUMNS]
    missing = [column for column in required if column not in summary.columns]
    if missing:
        raise ValueError(f"집계표에 필수 컬럼이 없습니다: {missing}")

    # **빈 축 값도 조용히 사라진다.** `groupby` 는 기본이 `dropna=True` 라 축이 비어 있는 행을
    # 그룹째 버리는데, 아래 「축당 한 행」 검사는 남은 그룹만 보므로 그것을 잡지 못한다
    blank_axis = int(summary[axis_column].isna().sum())
    if blank_axis:
        raise ValueError(f"축 값이 비어 있는 행이 있습니다: {axis_column} {blank_axis}행")

    # **축 값 하나에 행 하나를 «요구»한다.** `iloc[0]` 으로 첫 행만 쓰면 나머지가 조용히
    # 버려진다 — 예외도 경고도 없고 로그마저 「1칸」으로 정상처럼 찍힌다.
    # 축을 하나 더 붙이는 날 없는 우위를 보고하게 된다.
    # `report/tables.py` 가 같은 종류의 사고를 거부하므로 가드 강도를 그쪽에 맞춘다
    rows: list[dict[str, object]] = []
    for axis_value, cell in summary.groupby(axis_column, sort=True):
        if len(cell) != 1:
            raise ValueError(f"축 값 하나에 행이 하나여야 합니다: {axis_column}={axis_value} ({len(cell)}행)")
        rows.append(_direction_row(cell.iloc[0], axis_column=axis_column))
    result = pd.DataFrame(rows, columns=[axis_column, *DIRECTION_COLUMNS])

    downward = int((result[COL_DIRECTION] == DIRECTION_DOWN).sum())
    logger.debug(f"방향 표 산출: {len(result)}칸 (아래 {downward} · 위 {len(result) - downward})")

    return result


def _direction_row(row: pd.Series, *, axis_column: str) -> dict[str, object]:
    """한 칸의 방향과 크기를 낸다.

    Args:
        row: 집계표의 한 줄
        axis_column: 축 컬럼 이름

    Returns:
        방향 표 한 줄
    """
    sample_count = int(row[COL_SAMPLE_COUNT])

    # **거는 방향은 두 방향 비율 중 큰 쪽이다.** 보합이 어느 쪽에도 안 들어가 두 비율의 합이
    # 100% 를 넘지 못하므로 **큰 쪽은 언제나 하나**다 (같은 값이면 「위」로 간다).
    # **이 표는 판정하지 않는다** — 게이트는 기대값 하나만 보고 그 판단은 성적표에서 난다.
    # **기준선 대비 초과분으로 정하지 않는다** — 칸마다 다른 허들이 서서 기준선이 높은 칸의
    # 우위가 뒤집힌다 (모듈 docstring 의 실측)
    downward = float(row[COL_LOSS_RATE]) > float(row[COL_WIN_RATE])
    hit_rate = float(row[COL_LOSS_RATE] if downward else row[COL_WIN_RATE])

    # 아래로 거는 신호는 주가가 내릴 때 버는 것이므로 평균의 부호를 뒤집는다
    expected_value = -float(row[COL_MEAN]) if downward else float(row[COL_MEAN])

    # 같은 금액을 표본 수만큼 반복 투자했을 때의 단순 합 (측정의 원칙 16). 신호가 드문
    # 매매법은 회당 평균이 구조적으로 작아 크기 감각을 주지 못하므로 둘을 나란히 낸다
    total_return = expected_value * sample_count

    return {
        axis_column: row[axis_column],
        COL_SAMPLE_COUNT: sample_count,
        COL_DIRECTION: DIRECTION_DOWN if downward else DIRECTION_UP,
        COL_HIT_RATE: hit_rate,
        COL_EXPECTED_VALUE: expected_value,
        COL_TOTAL_RETURN: total_return,
    }
