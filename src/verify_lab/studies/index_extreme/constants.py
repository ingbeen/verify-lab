"""검증 #1(지수 극단 이벤트) 이벤트 정의와 실행이 공유하는 상수

파라미터 값은 `docs/spec/index_extreme_events.md` 가 확정한 것이며, **성과를 보며 돌리는
노브가 아니다.** 여러 값을 나란히 산출해 보고하기 위한 목록이므로 하나를 골라 두지 않는다.

표시용 한글 레이블도 여기 둔다. `report` 는 어떤 검증이 자기를 쓰는지 몰라야 하므로
검증별 컬럼 이름을 알 수 없고, 그 이름을 정하는 것은 이 검증의 몫이다.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final

from verify_lab.common_constants import MARKET_DIR, PRICE_DECIMALS


class Direction(Enum):
    """등락 방향

    두 테스트가 같은 방향 개념을 쓰되 부르는 이름이 다르다. 스펙은 테스트 A 를 폭등·폭락으로,
    테스트 B 를 연속 상승·연속 하락으로 부른다.

    Attributes:
        UP: 상승 — 테스트 A 의 폭등, 테스트 B 의 연속 상승
        DOWN: 하락 — 테스트 A 의 폭락, 테스트 B 의 연속 하락
    """

    UP = "up"
    DOWN = "down"


# ============================================================
# 테스트 A — 역대급 등락
# ============================================================

# 순위 컷. 메인은 10위이고 5·20 은 특정 값에만 붙은 우연인지 확인하기 위한 대조다
DEFAULT_RANK_CUT: Final = 10
RANK_CUTS: Final = (5, 10, 20)

# ============================================================
# 테스트 B — 연속 등락
# ============================================================

# 연속 일수. 전부 산출해 발생 빈도와 함께 보고한다
CONSECUTIVE_LENGTHS: Final = (3, 4, 5, 6, 7, 8, 9, 10)

# ============================================================
# 집계 구간
# ============================================================

# 신호 집계 시작 연도. 메인은 2011년이고 나머지는 구간 선택에 의존하는지 보기 위한 대조다.
# 시작 연도 이전의 날도 순위 축적과 연속 길이 누적에는 들어간다
DEFAULT_START_YEAR: Final = 2011
START_YEARS: Final = (2003, 2005, 2008, 2011)

# ============================================================
# 신호일 목록의 부가 컬럼
# ============================================================

# 사건 묶기 창 (달력일). 간격은 바로 앞 신호와 재며, 이 값 이내면 같은 사건으로 본다.
# 스펙은 거래일 단위일 때 "N거래일"로 명시하므로 여기의 "30일"은 달력일이다
EVENT_GAP_DAYS: Final = 30

# 참고용 z-score 창 (거래일). 판정일은 포함하지 않는다
ZSCORE_WINDOW: Final = 60


# ============================================================
# 시대 구간 — 강건성 체크 "구간별 일관성"
# ============================================================


@dataclass(frozen=True)
class Period:
    """신호를 집계할 시대 구간

    스펙 §6 강건성 체크의 "2010년대 / 2020년대로 나눠 방향이 일관되는가"를 재기 위한 축이다.
    구간은 **신호 선택의 양끝**을 좁힐 뿐이며 시세를 자르지 않는다 — 시세를 자르면 확장창
    순위가 그 지점부터 다시 쌓이고 걸쳐 있던 연속이 끊긴다.

    Attributes:
        label: 표시 이름
        start_year: 이 해부터 신호로 센다. `None` 이면 신호군의 집계 시작연도를 그대로 쓴다
        end_year: 이 해까지 신호로 센다. `None` 이면 끝을 자르지 않는다
    """

    label: str
    start_year: int | None
    end_year: int | None


# 끝을 자르지 않는 기본 구간. 모든 신호군이 이 구간을 갖는다
PERIOD_ALL: Final = Period(label="전체", start_year=None, end_year=None)

# 시대 구간은 **기본 시작연도에만** 붙인다. 모든 시작연도에 곱하면 "2003년 시작 + 2020년대"처럼
# 해석하기 어려운 조합이 생기고, 스펙 §6 이 이것을 축이 아니라 "체크"로 둔 취지에서도 멀어진다
DECADE_PERIODS: Final = (
    Period(label="2010년대", start_year=2010, end_year=2019),
    Period(label="2020년대", start_year=2020, end_year=None),
)


# ============================================================
# 검증 대상 시세
# ============================================================

# 종가 반올림 자릿수. KRX 원화 가격은 정수이므로 소수 자리를 붙이지 않는다
# (`.claude/rules/python.md` 출력 반올림 규칙표). 소수가 나오는 시장은 `PRICE_DECIMALS` 를 쓴다 —
# 원시 시세를 저장한 자릿수와 갈라지지 않도록 정의를 `common_constants` 한 곳에 둔다
PRICE_DECIMALS_KRW: Final = 0

DISPLAY_PRICE_BASIS_RAW: Final = "원본가"


@dataclass(frozen=True)
class Dataset:
    """검증 대상 시세 하나

    **가격 기준 하나에 파일 하나**이므로 같은 종목이 기준별로 여러 항목이 될 수 있다.
    다만 **이 검증은 원본가만 쓴다.** 사용자가 결과를 차트와 직접 대조하는 것이 전제인데
    보통의 차트는 배당 미포함이기 때문이며, 근거는
    `docs/spec/index_extreme_events.md` "가격 처리" 다.

    Attributes:
        key: 실행 인자로 고르는 이름
        ticker: 종목 표시 이름
        price_basis: 가격 기준 표시 이름
        path: 원시 시세 파일 경로
        price_decimals: 종가를 저장할 때의 반올림 자릿수
    """

    key: str
    ticker: str
    price_basis: str
    path: Path
    price_decimals: int


DATASETS: Final = (
    Dataset(
        key="qqq",
        ticker="QQQ",
        price_basis=DISPLAY_PRICE_BASIS_RAW,
        path=MARKET_DIR / "QQQ_max.csv",
        price_decimals=PRICE_DECIMALS,
    ),
    Dataset(
        key="kodex200",
        ticker="KODEX 200",
        price_basis=DISPLAY_PRICE_BASIS_RAW,
        path=MARKET_DIR / "069500_max.csv",
        price_decimals=PRICE_DECIMALS_KRW,
    ),
)


# ============================================================
# 표시용 레이블 — 신호군 식별
# ============================================================

DISPLAY_TICKER: Final = "종목"
DISPLAY_PRICE_BASIS: Final = "가격기준"
DISPLAY_TEST: Final = "테스트"
DISPLAY_PARAMETER: Final = "파라미터"
DISPLAY_START_YEAR: Final = "시작연도"
DISPLAY_DIRECTION: Final = "방향"

# `report` 가 측정 구간에 "구간"을 이미 쓰므로 시대 구간은 다른 이름을 쓴다.
# 같은 표에 두 축이 함께 실리기 때문이다
DISPLAY_PERIOD: Final = "시대 구간"

DISPLAY_GROUP_SIGNAL_COUNT: Final = "신호"
DISPLAY_EVENT_COUNT: Final = "사건"

DISPLAY_TEST_EXTREME: Final = "테스트 A(역대급 등락)"
DISPLAY_TEST_CONSECUTIVE: Final = "테스트 B(연속 등락)"

# 방향을 부르는 이름이 테스트마다 다르다. 스펙은 테스트 A 를 폭등·폭락으로,
# 테스트 B 를 연속 상승·연속 하락으로 부른다
EXTREME_DIRECTION_LABELS: Final = {Direction.UP: "폭등", Direction.DOWN: "폭락"}
CONSECUTIVE_DIRECTION_LABELS: Final = {Direction.UP: "연속 상승", Direction.DOWN: "연속 하락"}

# 파라미터는 테스트마다 뜻이 달라 한 컬럼에 접두사와 함께 담는다
PARAMETER_PREFIX_RANK_CUT: Final = "K"
PARAMETER_PREFIX_LENGTH: Final = "N"


# ============================================================
# 표시용 레이블 — 신호일 목록의 부가 컬럼
# ============================================================

DISPLAY_CLOSE: Final = "종가"
DISPLAY_CHANGE_RATE: Final = "등락률(%)"
DISPLAY_RANK: Final = "당시 순위"
DISPLAY_EVENT_ID: Final = "사건 번호"
DISPLAY_ZSCORE: Final = "z-score"

# z-score 는 비율도 백분율도 아닌 배수다. 스펙 §8 의 표기와 같은 자릿수를 쓴다
ZSCORE_DECIMALS: Final = 2


# ============================================================
# 표시용 레이블 — 베이스라인과 모집단
# ============================================================

DISPLAY_BASELINE_ALL: Final = "단순 보유"
DISPLAY_BASELINE_BELOW_SMA: Final = "조건부 SMA200"
DISPLAY_BASELINE_BELOW_EMA: Final = "조건부 EMA200"


# ============================================================
# 산출물
# ============================================================

# 결과 폴더 이름 뒤에 붙는 검증명
STUDY_NAME: Final = "index_extreme"
