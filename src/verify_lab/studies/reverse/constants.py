"""검증 #1(역방향) 이벤트 정의와 실행이 공유하는 상수

파라미터 값은 `docs/매매/역방향/설계.md` 가 확정한 것이며, **성과를 보며 돌리는
노브가 아니다.** 여러 값을 나란히 산출해 보고하기 위한 목록이므로 하나를 골라 두지 않는다.

표시용 한글 레이블도 여기 둔다. `report` 는 어떤 검증이 자기를 쓰는지 몰라야 하므로
검증별 컬럼 이름을 알 수 없고, 그 이름을 정하는 것은 이 검증의 몫이다.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final

from verify_lab.common_constants import MARKET_DIR, MARKET_FILE_TEMPLATE, PRICE_DECIMALS, PRICE_DECIMALS_KRW
from verify_lab.report.constants import (
    CANDIDATES_FILENAME,
    EXCESS_FILENAME,
    SIGNALS_FILENAME,
    STATISTICS_FILENAME,
    TEST_FILENAME,
)


class Direction(Enum):
    """등락 방향

    Attributes:
        UP: 상승 — 폭등
        DOWN: 하락 — 폭락
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

DISPLAY_PRICE_BASIS_RAW: Final = "원본가"


@dataclass(frozen=True)
class Dataset:
    """검증 대상 시세 하나

    **가격 기준 하나에 파일 하나**이므로 같은 종목이 기준별로 여러 항목이 될 수 있다.
    다만 **이 검증은 원본가만 쓴다.** 사용자가 결과를 차트와 직접 대조하는 것이 전제인데
    보통의 차트는 배당 미포함이기 때문이며, 근거는
    `docs/매매/역방향/설계.md` "가격 처리" 다.

    **`ticker` 와 `label` 은 다른 것이다.** 코드는 차트·증권앱과 대조할 때 필요하고
    표시 이름은 산출물이 쓴다. **미국 ETF 는 둘이 같아(`QQQ`) 구별이 드러나지 않지만
    국내는 갈린다** — 둘을 겸하면 `069500` 이 어디에도 남지 않는다.

    Attributes:
        key: 실행 인자로 고르는 이름
        ticker: 종목코드. **`summary.json` 의 `datasets` 에만 실린다** — 행마다 반복할
            값이 아니라 데이터셋 단위 속성이다 (`src/verify_lab/CLAUDE.md` 출력 계약)
        label: 종목 표시 이름. **산출물의 종목 컬럼이 쓰는 값**이다
        price_basis: 가격 기준 표시 이름
        path: 원시 시세 파일 경로
        price_decimals: 종가를 저장할 때의 반올림 자릿수
    """

    key: str
    ticker: str
    label: str
    price_basis: str
    path: Path
    price_decimals: int


DATASETS: Final = (
    Dataset(
        key="qqq",
        ticker="QQQ",
        label="QQQ",
        price_basis=DISPLAY_PRICE_BASIS_RAW,
        path=MARKET_DIR / MARKET_FILE_TEMPLATE.format(ticker="QQQ"),
        price_decimals=PRICE_DECIMALS,
    ),
    Dataset(
        key="kodex200",
        ticker="069500",
        label="KODEX 200",
        price_basis=DISPLAY_PRICE_BASIS_RAW,
        path=MARKET_DIR / MARKET_FILE_TEMPLATE.format(ticker="069500"),
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

# `report` 가 측정 구간에 `구간`, 원칙 17 의 시기 축에 `시기` 를 이미 쓰므로 시대 구간은
# 값도 **파이썬 이름도** 다르게 둔다. 같은 표에 두 축이 함께 실리고, 이름까지 같으면
# **잘못된 모듈에서 가져와도 문자열이 나와 조용히 다른 축이 된다**
# (`src/verify_lab/CLAUDE.md` — 같은 이유로 `TREND_*` 를 갈랐다)
DISPLAY_ERA: Final = "시대 구간"

DISPLAY_GROUP_SIGNAL_COUNT: Final = "신호"
DISPLAY_EVENT_COUNT: Final = "사건"

# **`테스트` 컬럼 값은 바꾸지 않는다.** 연속 등락(테스트 B)을 분리한 뒤에도 이 이름을 그대로 두는 것은
# 이전 산출물과 나란히 놓고 대조하기 위해서다 — 이름을 바꾸면 그 대조가 끊긴다
DISPLAY_TEST_EXTREME: Final = "테스트 A(역대급 등락)"

EXTREME_DIRECTION_LABELS: Final = {Direction.UP: "폭등", Direction.DOWN: "폭락"}

# 두 방향을 한 표본으로 묶은 신호군의 이름. 상승 방향 신호의 수익률에 −1 을 곱해
# **역방향으로 진입했을 때의 부호**로 통일한 값이다.
#
# `전체` 로 두지 않는 이유는 **같은 표의 `시대 구간` 컬럼에 이미 `전체` 가 있기 때문**이다.
# 한 행에 같은 문자열이 두 컬럼에 실리면 대조할 때 어느 축의 값인지 헷갈린다
DISPLAY_DIRECTION_REVERSE_ALL: Final = "역방향 전체"

# 판정표에서 그 표본이 기준선의 «어느 쪽»으로 치우쳤는가. 식별 컬럼의 `방향` 과 다른 것이라
# 이름을 가른다 — 그쪽은 신호군의 종류(폭등·폭락·역방향 전체)다.
#
# [중요] **「거는 방향」으로 부르지 않는다.** 지시 대상이 행마다 다르기 때문이다 —
# 방향별 행은 «원지수»가 어느 쪽인지를 말하지만(폭등 신호는 「아래」 = 인버스 진입),
# `역방향 전체` 행은 수익률이 이미 역방향 부호로 통일돼 있어 「위」가 «역방향 진입이 이익»을
# 뜻한다. 같은 이름이 두 뜻을 가지면 이 열로 거른 목록이 조용히 틀린다
DISPLAY_LEAN_SIDE: Final = "치우친 쪽"

# 파라미터 컬럼에 접두사와 함께 담는다
PARAMETER_PREFIX_RANK_CUT: Final = "K"


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


# ============================================================
# 산출물
# ============================================================

# 이 매매법의 이름(slug). 규약은 `src/verify_lab/CLAUDE.md` 「매매법 이름 계약」이 SoT다.
#
# **값이 「재는 사건」이 아니라 「거는 방향」인 것은 사용자 결정이다** (2026-09-10). 이 검증이
# 재는 것은 역대급 등락이지만 그 신호로 하는 매매가 역방향이고, **둘을 한 이름으로 묶는 쪽**을
# 택했다. 본문에서 신호 자체를 가리킬 때는 「역대급 등락」을 그대로 쓴다
TRACK_NAME: Final = "reverse"


# ============================================================
# 산출물 파일
# ============================================================

# **산출물 필드 이름 → 파일 이름.** 이 사전이 「이 검증이 무슨 파일을 내는가」의 자리다.
# runner 가 `row_counts` 를 이것으로 키잉하고 CLI 가 이것을 돌며 저장한다 —
# 왜 CLI 가 이름을 갖지 않는지는 `src/verify_lab/CLAUDE.md` 실행 요약 계약이 SoT 다.
OUTPUT_FILES: Final[dict[str, str]] = {
    "signals": SIGNALS_FILENAME,
    "statistics": STATISTICS_FILENAME,
    "excess": EXCESS_FILENAME,
    "test": TEST_FILENAME,
    "candidates": CANDIDATES_FILENAME,
}


# ============================================================
# 매매 파라미터
# ============================================================
#
# 규칙의 확정 근거는 매매 규칙 문서 §3 이 SoT다. **여기 값은 과거 신호를 보고 고른 것**이며,
# 성적은 과거 재구성이지 예측이 아니다. **표본 수는 시세 기간에 묶여 있으므로 그 문서의
# 머리말이 기준이다** — 값을 여기 적으면 재수집할 때마다 두 곳이 갈라진다.
#
# **이 매매법의 값을 공유 모듈에 두지 않는다.** 공유 체결식(`execution/trade_fill.py`)에
# 두면 그 기본값이 이 매매법의 -5% 가 되고, 공유 상수 모듈에 두면 그 모듈이 이 패키지를
# import 하게 되어 **다른 매매법을 돌려도 역방향의 `DATASETS` 가 딸려 온다.**
# `tests/test_layer_contracts.py` 가 그 결합이 생기는 것을 막는다

# 손절선은 진입가 기준이며 보유 기간 내내 바뀌지 않는다 — 매일 갱신하면 손실이 이어질 때
# 최악이 무제한으로 열린다. 비율(0.05 = 5%)로 정의한다.
#
# **-5% 는 성적이 가장 좋아서 고른 값이 아니다.** 실측에서 -4%~-10% 구간은 회당 평균이
# +1.27~+1.46% 로 평평해 값 선택이 결과를 만들지 않는다. 이 값을 고른 근거는
# **갭손절(시가가 이미 손절선 아래여서 더 잃는 체결)이 0건이 되는 첫 지점**이라는 것이다 —
# -4% 에서 2건, -3% 에서 4건, -2% 에서 7건이 발생한다.
# 반대로 -4% 아래로 내려가면 매매법 자체가 무너진다(적중률 56.8%)
STOP_LOSS_LEVEL: Final = 0.05

# 이익이 나면 그날 즉시 청산하고, 손실일 때만 한도까지 끈다.
# **D+2 로 고정한다** — 3일 구간은 평균 우연확률이 0.2917 로 근거가 없고, D+3 에서만
# 갭손절이 새로 생긴다(밤을 하나 더 넘기므로). D+1 은 KODEX 200 에서 회당 평균이
# +1.57% → +1.38%, 적중률이 75.00% → 68.18% 로 내려간다
HOLD_LIMIT: Final = 2

# **확정 규칙이 아니라 대조축이다.** 손절선을 다시 고를 때 쓰는 격자이며,
# `.claude/rules/trading.md` 가 「손절선 후보를 격자로 전부 돌려 평평한 구간을 찾는다」를
# 절차로 요구한다. **시세를 재수집하면 그 절차를 다시 밟아야 한다.**
#
# 하한 -2% 는 노이즈 손절이 시작되는 지점이다(적중률 59.09%). 상한 -10% 는 그보다 넓히면
# 손절이 사실상 무손절과 같아지는 지점이며, **무손절 자체는 `None` 행으로 따로 낸다** —
# 「손절이 무엇을 막았는가」는 그 행과 견줘야 보인다
STOP_LOSS_LEVELS: Final = tuple(round(0.02 + 0.01 * step, 4) for step in range(9))

# 백테스트 구간의 시작연도. **모든 대상이 이 값을 쓴다** — 종목마다 구간이 갈리면
# 산출물의 시작연도 열을 읽는 사람이 그 차이에 뜻이 있다고 오해한다 (결정 ③).
#
# **성적이 아니라 표본 근거로 고른 값이다.** KODEX 200 기준 축적 550거래일에서 "상위 10위"는
# **상위 1.8%** 라 극단의 뜻이 유지되고(등락률 하한 4.29%, 4% 미만 신호 0건),
# 사건 수가 K=10 은 9→12 · K=20 은 13→20 으로 늘어난다.
#
# 2003 은 축적이 54거래일뿐이라 상위 10위가 **상위 18.5%** 이고 등락률 0.83% 짜리까지 잡혀 탈락했다.
# QQQ 는 첫 신호가 2008-09-29 라 이 값을 앞당겨도 신호 집합이 바뀌지 않는다
START_YEAR: Final = 2005


@dataclass(frozen=True)
class Target:
    """매매 대상 하나

    Attributes:
        dataset: 검증 대상 시세 (측정과 같은 정의를 쓴다)
        rank_cut: 순위 컷. 이 순위 이내의 등락이면 신호다
        start_year: 이 해부터 신호로 센다. **앞 구간은 순위 축적에만 쓰이므로
            시작연도를 앞당겨도 뒤 구간의 판정은 바뀌지 않는다** — 앞 구간이 더해질 뿐이다
    """

    dataset: Dataset
    rank_cut: int
    start_year: int = START_YEAR


def dataset_of(key: str) -> Dataset:
    """데이터셋 목록에서 이름으로 하나를 찾는다.

    Args:
        key: 데이터셋 이름

    Returns:
        해당 데이터셋

    Raises:
        ValueError: 그 이름의 데이터셋이 없는 경우
    """
    for dataset in DATASETS:
        if dataset.key == key:
            return dataset

    raise ValueError(f"알 수 없는 데이터셋입니다: {key}")


# **같은 순위 컷이 두 종목에서 다른 의미다.** 데이터 시작일이 달라 순위 축적량이 959거래일과
# 54거래일로 갈리며, 2008 기준 등락률 하한이 QQQ K=20 은 6.34% 인데 KODEX 200 K=5 는 4.79% 다.
# QQQ 는 K=10 이 7건이라 검정이 붙지 않으므로 K=20 을 함께 둔다 — K=10 은 K=20 의 부분집합이고,
# 강한 신호와 약한 신호의 대비 자체가 결과다 (결정 ②)
#
# **KODEX 200 의 확정 규칙은 K=10 이고 K=20 은 비교축이다** (규칙 문서 §1.1 이 정한다).
# 여기 함께 두는 것은 같은 규칙·같은 산출물로 두 컷을 나란히 놓기 위해서이며, K=20 을 채택한
# 것이 아니다. K=20 은 등락률 하한이 4.79% → 3.63% 로 내려가 약한 신호가 들어온다 —
# 그것이 성적을 희석하는지는 산출물의 두 행을 대조해 판단한다
#
# **시작연도는 전부 기본값이다** — 두 종목 × 두 컷이고 구간 축은 닫혀 있다 (결정 ③).
# 남은 결정은 순위 컷 하나이며 사용자가 판단한다
TARGETS: Final = (
    Target(dataset=dataset_of("kodex200"), rank_cut=10),
    Target(dataset=dataset_of("kodex200"), rank_cut=20),
    Target(dataset=dataset_of("qqq"), rank_cut=10),
    Target(dataset=dataset_of("qqq"), rank_cut=20),
)


# ============================================================
# 실행 요약 키
# ============================================================

# 집계 시작 연도. **측정과 매매가 같은 값을 남기므로 한 곳에서 정의한다**
KEY_START_YEAR: Final = "start_year"
