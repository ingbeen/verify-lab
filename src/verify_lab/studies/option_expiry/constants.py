"""검증 #7(옵션 만기일) 이벤트 정의와 실행이 공유하는 상수

파라미터 값은 `docs/spec/option_expiry.md` 가 확정한 것이며, **성과를 보며 돌리는 노브가 아니다.**
여러 값을 나란히 산출해 보고하기 위한 목록이므로 하나를 골라 두지 않는다.

표시용 한글 레이블도 여기 둔다. `report` 는 어떤 검증이 자기를 쓰는지 몰라야 하므로
검증별 컬럼 이름을 알 수 없고, 그 이름을 정하는 것은 이 검증의 몫이다.
"""

from dataclasses import dataclass
from typing import Final

from verify_lab.common_constants import PRICE_DECIMALS


@dataclass(frozen=True)
class ExpiryRule:
    """월물 만기일을 정하는 달력 규칙

    만기일은 시세와 무관한 **달력 규칙**이다. 규칙일이 휴장이면 직전 거래일까지 앞당겨지며,
    그 판정에 필요한 거래일 목록은 시세 파일의 날짜 인덱스에서 온다
    (`docs/spec/option_expiry.md` 결정 ⑤).

    Attributes:
        label: 표시 이름
        weekday: 요일 (월=0 ~ 일=6). `pandas` 의 `dayofweek` 와 같은 기준이다
        ordinal: 그 달에서 몇 번째 해당 요일인가 (1부터)
    """

    label: str
    weekday: int
    ordinal: int


# 미국 월물 옵션 만기 — 매월 셋째 금요일
US_MONTHLY_EXPIRY: Final = ExpiryRule(label="셋째 금요일", weekday=4, ordinal=3)

# 한국 월물 옵션 만기 — 매월 둘째 목요일
KR_MONTHLY_EXPIRY: Final = ExpiryRule(label="둘째 목요일", weekday=3, ordinal=2)


# ============================================================
# 상대 거래일 (offset)
# ============================================================

# 만기일을 0 으로 두고 앞뒤로 셀 거래일 수. 앞뒤 2주씩이면 문헌이 말하는 창이 전부 들어간다.
# 하나를 고르지 않고 이 범위를 전부 산출해 나란히 보고한다 (측정의 원칙 1)
MAX_OFFSET: Final = 10

# 동시만기(위칭)가 있는 달. 미국·한국 모두 분기 말 달에 선물 만기가 겹친다
WITCHING_MONTHS: Final = (3, 6, 9, 12)


# ============================================================
# DataFrame 컬럼
# ============================================================

COL_EXPIRY_MONTH: Final = "expiry_month"
COL_RULE_DATE: Final = "rule_date"
COL_EXPIRY_DATE: Final = "expiry_date"
COL_ADVANCED_DAYS: Final = "advanced_days"
COL_OFFSET: Final = "offset"

# 그날이 그 달의 몇 번째 거래일인가. 만기 창은 언제나 월 중순이라 offset 과 거의 붙어 다니므로,
# **두 축이 구별되는지**를 독자가 직접 볼 수 있게 함께 낸다 (결정 ⑭)
COL_MONTH_DAY_INDEX: Final = "month_day_index"

# 그날 하루의 등락률. forward return 과 달리 앞날을 보지 않는다
COL_DAILY_RETURN: Final = "daily_return"

# 산출물의 식별 컬럼 — 어떤 조합에서 나온 행인지
COL_TICKER: Final = "ticker"
COL_PRICE_BASIS: Final = "price_basis"
COL_REGIME: Final = "regime"
COL_WITCHING: Final = "witching"


# ============================================================
# 측정 구간
# ============================================================

# offset 을 앵커로 잰 forward return 의 구간 (거래일). "만기주 전체" 같은 창은
# (앵커 offset, 구간) 조합으로 표현된다 — 예: 미국 만기주 = 앵커 -5 · 구간 5
OFFSET_HORIZONS: Final = (1, 2, 3, 5, 10)


# ============================================================
# 분리 축 — 위칭과 국면
# ============================================================


@dataclass(frozen=True)
class WitchingGroup:
    """동시만기 여부로 나눈 집계 축

    Attributes:
        label: 표시 이름
        months: 포함할 만기월. `None` 이면 자르지 않는다
        exclude: True 면 `months` 를 제외한 나머지를 뜻한다
    """

    label: str
    months: tuple[int, ...] | None
    exclude: bool = False


WITCHING_GROUPS: Final = (
    WitchingGroup(label="전체", months=None),
    WitchingGroup(label="동시만기(3·6·9·12월)", months=WITCHING_MONTHS),
    WitchingGroup(label="옵션 단독(그 외 8개월)", months=WITCHING_MONTHS, exclude=True),
)


@dataclass(frozen=True)
class Regime:
    """시장 구조가 바뀐 시점으로 나눈 집계 축

    경계는 **결과를 보기 전에** 정한다. 나중에 자르면 결과를 보고 자른 것이 된다
    (`docs/spec/option_expiry.md` 결정 ⑨).

    Attributes:
        label: 표시 이름
        start: 이 날부터 포함 (`None` 이면 앞을 자르지 않는다)
        end: 이 날까지 포함 (`None` 이면 뒤를 자르지 않는다)
    """

    label: str
    start: str | None
    end: str | None


REGIME_ALL: Final = Regime(label="전체", start=None, end=None)

# 미국 — 위클리 옵션(2005)과 0DTE 확산(2022)으로 만기가 흩어졌다
US_REGIMES: Final = (
    REGIME_ALL,
    Regime(label="~2004 (월물 중심)", start=None, end="2004-12-31"),
    Regime(label="2005~2021 (위클리)", start="2005-01-01", end="2021-12-31"),
    Regime(label="2022~ (0DTE)", start="2022-01-01", end=None),
)

# 한국 — 위클리옵션 상장일이 경계다
KR_REGIMES: Final = (
    REGIME_ALL,
    Regime(label="~2019-09-22 (월물만)", start=None, end="2019-09-22"),
    Regime(label="2019-09-23~ (위클리)", start="2019-09-23", end=None),
)


# ============================================================
# 검증 대상 시세
# ============================================================

# 원화 정수 가격은 소수 자리를 붙이지 않는다 (`.claude/rules/python.md` 반올림 규칙표)
PRICE_DECIMALS_KRW: Final = 0

DISPLAY_BASIS_ADJUSTED: Final = "수정주가"
DISPLAY_BASIS_RAW: Final = "원본가"

# 만기 창 밖의 날로 만든 베이스라인의 이름
DISPLAY_BASELINE_OUTSIDE: Final = "만기 창 밖"


@dataclass(frozen=True)
class PriceSeries:
    """한 종목의 가격 기준 하나

    **가격 기준 하나에 파일 하나**다. 이 검증은 두 기준을 나란히 내며, 차이가 곧 배당락 몫이라
    차이 자체가 검산이 된다 (`docs/spec/option_expiry.md` §3.4).

    Attributes:
        basis: 가격 기준 표시 이름
        file_name: `storage/market/` 안의 파일 이름
        primary: 본검증 기준이면 True, 대조면 False
    """

    basis: str
    file_name: str
    primary: bool


@dataclass(frozen=True)
class Dataset:
    """검증 대상 종목 하나

    Attributes:
        key: 실행 인자로 고르는 이름
        ticker: 종목 표시 이름
        rule: 그 시장의 월물 만기 규칙
        regimes: 그 시장의 국면 분할 축
        series: 가격 기준별 파일
        price_decimals: 종가를 저장할 때의 반올림 자릿수
    """

    key: str
    ticker: str
    rule: ExpiryRule
    regimes: tuple[Regime, ...]
    series: tuple[PriceSeries, ...]
    price_decimals: int


DATASETS: Final = (
    Dataset(
        key="qqq",
        ticker="QQQ",
        rule=US_MONTHLY_EXPIRY,
        regimes=US_REGIMES,
        series=(
            PriceSeries(basis=DISPLAY_BASIS_ADJUSTED, file_name="QQQ_adjusted_max.csv", primary=True),
            PriceSeries(basis=DISPLAY_BASIS_RAW, file_name="QQQ_max.csv", primary=False),
        ),
        price_decimals=PRICE_DECIMALS,
    ),
    Dataset(
        key="spy",
        ticker="SPY",
        rule=US_MONTHLY_EXPIRY,
        regimes=US_REGIMES,
        series=(
            PriceSeries(basis=DISPLAY_BASIS_ADJUSTED, file_name="SPY_adjusted_max.csv", primary=True),
            PriceSeries(basis=DISPLAY_BASIS_RAW, file_name="SPY_max.csv", primary=False),
        ),
        price_decimals=PRICE_DECIMALS,
    ),
    Dataset(
        key="kodex200",
        ticker="KODEX 200",
        rule=KR_MONTHLY_EXPIRY,
        regimes=KR_REGIMES,
        series=(
            # 국내 수정주가는 조회 시점 기준 최근 3,000거래일만 존재한다. 그래서 본검증 구간이
            # 원본가보다 짧다 — 그 사실 자체를 결과에 적는다 (결정 ⑬)
            PriceSeries(basis=DISPLAY_BASIS_ADJUSTED, file_name="069500_adjusted_max.csv", primary=True),
            PriceSeries(basis=DISPLAY_BASIS_RAW, file_name="069500_max.csv", primary=False),
        ),
        price_decimals=PRICE_DECIMALS_KRW,
    ),
)


# ============================================================
# 표시용 레이블
# ============================================================

DISPLAY_EXPIRY_MONTH: Final = "만기월"
DISPLAY_RULE_DATE: Final = "규칙일"
DISPLAY_EXPIRY_DATE: Final = "만기일"
DISPLAY_ADVANCED_DAYS: Final = "앞당김(달력일)"
DISPLAY_OFFSET: Final = "상대 거래일"
DISPLAY_TICKER: Final = "종목"
DISPLAY_PRICE_BASIS: Final = "가격기준"
DISPLAY_REGIME: Final = "국면"
DISPLAY_WITCHING: Final = "만기 종류"
DISPLAY_MONTH_DAY_INDEX: Final = "월중 서수"
DISPLAY_DAILY_RETURN: Final = "일간 등락률(%)"
DISPLAY_CLOSE: Final = "종가"


# ============================================================
# 산출물
# ============================================================

# 결과 폴더 이름 뒤에 붙는 검증명
STUDY_NAME: Final = "option_expiry"
