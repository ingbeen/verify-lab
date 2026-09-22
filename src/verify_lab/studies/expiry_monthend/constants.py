"""만기_말일 — 진입 2종 × 청산 2종 교차 검증의 파라미터와 레이블

이 검증은 **두 매매법이 각자 쓰던 진입·청산을 한 축에 올려 놓는다.**

| | 청산: 다음 주 금요일 | 청산: 그 달 마지막 거래일 |
| --- | --- | --- |
| **진입: 셋째 금요일** | C1 (미국 = 옵션 만기일과 같다) | C2 |
| **진입: 20일** | C3 | C4 (한국 = 월말 진입과 같다) |

**한국에도 셋째 금요일을 쓴다** (2026-09-21 사용자 결정). 국내 만기(둘째 목요일)는 사용자가
이미 재 봤고 성과가 약했다. 실측으로 앞당김이 드물다 — `KODEX 200` 47해 중 2해뿐이며
둘 다 추석이다.

**9월·12월만 잰다** (같은 날 결정). 두 매매법이 이미 그 두 달을 가리킨 뒤에 고른 것이라
**사후 선택**이고, 그래서 이 검증의 용도는 「우위가 있다」가 아니라 **「조합 선택이 결과를
만드는가」**다. 그 한계는 `docs/검증/만기_말일/결과.md` 가 적는다.

**달력 계산 자체는 `measure/calendar_entry.py`·`calendar_exit.py` 가 소유한다** —
세 매매법이 같은 달력을 쓰므로 한 자리에 있어야 하고, 매매법끼리는 서로를 가져올 수 없다
(`tests/test_layer_contracts.py`). 여기 있는 것은 **이 검증의 파라미터**뿐이다.

**표시용 한글 레이블은 이 검증만의 것 셋뿐이다** — 나머지는 공통 계층에서 가져온다.
같은 뜻에 이름이 두 벌이 되면 두 산출물의 헤더가 갈리고, 한쪽이 바뀌어도 예외가 나지 않는다.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from verify_lab.common_constants import (
    COL_CLOSE,
    COL_DATE,
    COL_VALUE,
    INDEX_FILE_TEMPLATE,
    MARKET_DIR,
    MARKET_FILE_TEMPLATE,
    PRICE_DECIMALS,
    PRICE_DECIMALS_KRW,
    SERIES_DIR,
)
from verify_lab.execution.constants import (
    DISPLAY_EXIT_DATE,
    DISPLAY_RETURN,
    DISPLAY_TICKER,
)
from verify_lab.measure.calendar_entry import ExpiryRule
from verify_lab.measure.constants import (
    COL_DIVIDEND_HIT_COUNT,
    COL_DIVIDEND_MEAN_IMPACT,
    COL_DIVIDEND_MEASURED,
    COL_ENTRY_CLOSE,
    COL_EXCLUDED_COUNT,
    COL_EXCLUDED_REASON,
    COL_EXIT_CLOSE,
    COL_EXIT_DATE,
    COL_FORWARD_RETURN,
    COL_HOLD_DAYS,
    COL_JUDGEABLE,
    COL_MEAN_RATE_CONFLICT,
    COL_SIGNAL_COUNT,
)
from verify_lab.measure.screening import COL_DIRECTION
from verify_lab.measure.statistics import (
    COL_BASELINE_SAMPLE_COUNT,
    COL_DOWN_RATE_P_VALUE,
    COL_LOSS_RATE,
    COL_LOSS_RATE_EXCESS,
    COL_MAX,
    COL_MEAN,
    COL_MEAN_EXCESS,
    COL_MEAN_P_VALUE,
    COL_MEDIAN,
    COL_MEDIAN_EXCESS,
    COL_MEDIAN_P_VALUE,
    COL_MIN,
    COL_NEGATIVE_COUNT,
    COL_NEGATIVE_MEAN,
    COL_POSITIVE_COUNT,
    COL_POSITIVE_MEAN,
    COL_SAMPLE_COUNT,
    COL_SIGNAL_SAMPLE_COUNT,
    COL_STD,
    COL_TEST_NOTE,
    COL_UP_RATE_P_VALUE,
    COL_WIN_RATE,
    COL_WIN_RATE_EXCESS,
)
from verify_lab.report.constants import (
    DISPLAY_BASELINE_SAMPLE,
    DISPLAY_DATE,
    DISPLAY_DIRECTION,
    DISPLAY_DIVIDEND_HIT_COUNT,
    DISPLAY_DIVIDEND_MEAN_IMPACT,
    DISPLAY_DIVIDEND_MEASURED,
    DISPLAY_DOWN_RATE,
    DISPLAY_DOWN_RATE_DIFF,
    DISPLAY_DOWN_RATE_P_VALUE,
    DISPLAY_ENTRY_CLOSE,
    DISPLAY_EXCLUDED,
    DISPLAY_EXCLUDED_REASON,
    DISPLAY_EXIT_CLOSE,
    DISPLAY_HOLD_DAYS_EXACT,
    DISPLAY_JUDGEABLE,
    DISPLAY_MAX,
    DISPLAY_MEAN,
    DISPLAY_MEAN_DIFF,
    DISPLAY_MEAN_P_VALUE,
    DISPLAY_MEAN_RATE_CONFLICT,
    DISPLAY_MEDIAN,
    DISPLAY_MEDIAN_DIFF,
    DISPLAY_MEDIAN_P_VALUE,
    DISPLAY_MIN,
    DISPLAY_MONTH_NUMBER,
    DISPLAY_NEGATIVE_COUNT,
    DISPLAY_NEGATIVE_MEAN,
    DISPLAY_POSITIVE_COUNT,
    DISPLAY_POSITIVE_MEAN,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_SIGNAL_SAMPLE,
    DISPLAY_STD,
    DISPLAY_TEST_NOTE,
    DISPLAY_UP_RATE,
    DISPLAY_UP_RATE_DIFF,
    DISPLAY_UP_RATE_P_VALUE,
    STATISTICS_FILENAME,
)

# 이 매매법의 이름(slug). 규약은 `src/verify_lab/CLAUDE.md` 「매매법 이름 계약」이 SoT다
TRACK_NAME: Final = "expiry_monthend"


# ============================================================
# 진입과 청산의 규칙 값
# ============================================================

# 요일 번호 (월=0 ~ 일=6). `pandas` 의 `dayofweek` 와 같은 기준이다
FRIDAY: Final = 4

# **양 시장 공통으로 셋째 금요일을 쓴다** (2026-09-21 사용자 결정).
# 국내 만기(둘째 목요일)는 이미 재 봤고 성과가 약해 이 검증에서 뺐다
THIRD_FRIDAY: Final = ExpiryRule(label="셋째 금요일", weekday=FRIDAY, ordinal=3)

# 달력일 진입의 목표일. 사용자가 사전에 전해 들은 가설의 값이라 격자로 훑지 않는다
ENTRY_CALENDAR_DAY: Final = 20

# 주 기준 청산의 목표 요일
EXIT_WEEKDAY: Final = FRIDAY

# 말일 기준 청산의 상대 거래일. 0 이 그 달 마지막 거래일이다
EXIT_OFFSET: Final = 0

# 묶음 집계에서 쓰는 구간 표지. 보유 거래일 수를 구간 축에 넣으면 **한 매매가 여러 칸으로
# 쪼개져** 묶음 값이 나오지 않는다. 실제 보유일수로는 도달할 수 없는 음수를 쓴다
HORIZON_POOLED: Final = -1

# 재는 달. **9월·12월만이고 그것은 사후 선택이다** — 두 매매법이 이미 그 달을 가리킨 뒤에
# 골랐으므로 나오는 숫자로 「우위가 있다」를 새로 주장할 수 없다 (결과 문서의 한계)
MONTHS: Final = (9, 12)


# ============================================================
# 네 조합
# ============================================================

# 진입 규칙의 종류
ENTRY_EXPIRY: Final = "셋째 금요일"
ENTRY_DAY: Final = "20일"

# 청산 규칙의 종류
EXIT_NEXT_WEEK: Final = "다음 주 금요일"
EXIT_MONTH_END: Final = "말일"


@dataclass(frozen=True)
class Combo:
    """진입 × 청산 조합 하나

    Attributes:
        key: 실행 인자로 고르는 이름
        label: 산출물의 `조합` 컬럼에 실리는 표시 이름
        entry: 진입 규칙 (`ENTRY_EXPIRY` 또는 `ENTRY_DAY`)
        exit_rule: 청산 규칙 (`EXIT_NEXT_WEEK` 또는 `EXIT_MONTH_END`)
    """

    key: str
    label: str
    entry: str
    exit_rule: str


# **네 조합을 전부 낸다.** 고르지 않으므로 과최적화가 아니다 (측정의 원칙 1).
#
# [중요] **네 조합이 언제나 네 개의 다른 매매인 것은 아니다.** 절반 가까운 해에
# **진입·청산이 둘 다 같아** 두 조합이 한 매매가 된다.
#
# **그 크기를 여기 숫자로 적지 않는다** — 산출물이 매 실행 다시 세므로 시세를 재수집하면
# 산문만 낡는다. 값의 자리는 `통계.csv` 의 **「다른 조합과 같은 해」·「이 조합만 다른 해」**
# 두 컬럼이고, 그때의 수치는 `docs/검증/만기_말일/결과.md` §5 가 데이터 기간과 함께 갖는다.
# 그래서 산출물이 **「다른 조합과 같은 해」와 「이 조합만 다른 해」를 세어 함께 낸다** —
# 조합 간 성적 차이가 실제로 몇 건에서 나온 것인지 그 자리에서 보이지 않으면 판단할 수 없다
COMBOS: Final = (
    Combo(key="c1", label="만기→다음주금", entry=ENTRY_EXPIRY, exit_rule=EXIT_NEXT_WEEK),
    Combo(key="c2", label="만기→말일", entry=ENTRY_EXPIRY, exit_rule=EXIT_MONTH_END),
    Combo(key="c3", label="20일→다음주금", entry=ENTRY_DAY, exit_rule=EXIT_NEXT_WEEK),
    Combo(key="c4", label="20일→말일", entry=ENTRY_DAY, exit_rule=EXIT_MONTH_END),
)


# ============================================================
# 검증 대상
# ============================================================


@dataclass(frozen=True)
class Dataset:
    """검증 대상 하나

    **ETF 와 지수는 스키마가 다르다.** ETF 는 시세(`storage/market/`)의 `Close`,
    지수는 단일 값 계열(`storage/series/`)의 `Value` 다.

    Attributes:
        ticker: 종목 또는 지수 코드. **산출물의 데이터셋 구분자이므로 겹치면 안 된다**
        label: 표시 이름. **산출물의 종목 컬럼이 쓰는 값**이다
        market: 어느 시장인가. **조회표가 아니라 대상 자신이 갖는다**
        directory: 파일이 있는 폴더
        file_template: 파일명 템플릿
        price_column: 가격 컬럼 이름
        price_decimals: 가격 출력 자릿수. 원시 데이터를 저장한 값과 같아야 한다
        is_index: 지수면 True. **살 수 없다는 사실을 산출물에 남기기 위한 값**이다
    """

    ticker: str
    label: str
    market: str
    directory: Path
    file_template: str
    price_column: str
    price_decimals: int
    is_index: bool

    @property
    def path(self) -> Path:
        """데이터 파일 경로.

        Returns:
            읽을 파일의 전체 경로
        """
        return self.directory / self.file_template.format(ticker=self.ticker)

    @property
    def is_judged(self) -> bool:
        """이 대상으로 1차 판정을 하는가.

        **판정은 살 수 있는 것에만 건다** (측정의 원칙 9). 지수로 「우위가 있다」를 주장하면
        집행할 수 없는 성적이 근거가 된다. 값은 그대로 내고 판정만 「판정 안 함」이 된다.

        Returns:
            판정 대상이면 True
        """
        return not self.is_index


MARKET_US: Final = "미국"
MARKET_KOSPI: Final = "코스피"
MARKET_KOSDAQ: Final = "코스닥"

# **여섯 대상이다** (2026-09-21 사용자 결정).
#
# [중요] **종합지수(코스피 종합·코스닥 종합)를 넣지 않는다.** 실측으로 코스닥 종합이
# `KODEX 코스닥150` 과 상관 **0.8924 ~ 0.9743** (절대차 0.64~1.29%p) 인 반면
# 코스닥150 지수는 **0.9928 ~ 0.9991** (0.18~0.40%p) 이다 — 종합지수는 「같은 것의 긴 축」이
# 아니라 **다른 것**이고, 그것으로 판단 재료를 삼으면 집행할 상품과 어긋난 값을 보게 된다.
# **대가는 긴 축이 짧아지는 것**이다 (코스피 46해 → 36해 · 코스닥 30해 → 16해).
#
# **QQQ 를 넣지 않는다** — 배당락이 보유 구간에 들어와 측정값이 오염된 것이 이미 실측됐고
# (`docs/매매/옵션_만기일/규칙.md` §3.4), 만기→말일 조합에서는 더 걸린다.
#
# **인버스를 넣지 않는다** — 「아래」는 1배의 부호를 뒤집어 재고, 실물 대조는 월말 진입이
# 이미 갖고 있다
DATASETS: Final = (
    Dataset(
        ticker="SPY",
        label="SPY",
        market=MARKET_US,
        directory=MARKET_DIR,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS,
        is_index=False,
    ),
    Dataset(
        ticker="DIA",
        label="DIA",
        market=MARKET_US,
        directory=MARKET_DIR,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS,
        is_index=False,
    ),
    Dataset(
        ticker="069500",
        label="KODEX 200",
        market=MARKET_KOSPI,
        directory=MARKET_DIR,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS_KRW,
        is_index=False,
    ),
    Dataset(
        ticker="1028",
        label="코스피200 지수",
        market=MARKET_KOSPI,
        directory=SERIES_DIR,
        file_template=INDEX_FILE_TEMPLATE,
        price_column=COL_VALUE,
        price_decimals=PRICE_DECIMALS,
        is_index=True,
    ),
    Dataset(
        ticker="229200",
        label="KODEX 코스닥150",
        market=MARKET_KOSDAQ,
        directory=MARKET_DIR,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS_KRW,
        is_index=False,
    ),
    Dataset(
        ticker="2203",
        label="코스닥150 지수",
        market=MARKET_KOSDAQ,
        directory=SERIES_DIR,
        file_template=INDEX_FILE_TEMPLATE,
        price_column=COL_VALUE,
        price_decimals=PRICE_DECIMALS,
        is_index=True,
    ),
)


# ============================================================
# 손절선
# ============================================================

# 확정 손절선 (비율, 0.05 = 5%). **진입가 기준이며 보유 기간 내내 바뀌지 않는다.**
# **이 검증이 고른 값이 아니라 두 매매법이 이미 확정한 값을 그대로 쓴다** — 조합을 비교하는
# 것이 목적이라 손절선까지 축으로 두면 무엇이 차이를 만들었는지 갈리지 않는다
STOP_LEVEL: Final = 0.05

# **ETF 는 확정 손절선과 무손절 둘을 낸다.** 무손절은 `.claude/rules/trading.md` 가
# 「손절이 무엇을 막았는가」로 요구하는 대조축이고, 이 트랙은 `규칙.md` 가 없어 산출로 메운다.
# **손절선을 고르는 격자가 아니다** — 값은 하나뿐이고 옆에 대조가 붙을 뿐이다
STOP_LEVELS_ETF: Final[tuple[float | None, ...]] = (STOP_LEVEL, None)

# **지수는 한 줄뿐이다.** 장중 손절에 고가·저가가 필요한데 지수는 종가만 있어
# `손절선(%)` 에 「손절불가」로 적힌다
STOP_LEVELS_INDEX: Final[tuple[float | None, ...]] = (None,)


# ============================================================
# DataFrame 컬럼 (내부 계산용 토큰)
# ============================================================

COL_TICKER: Final = "ticker"
COL_COMBO: Final = "combo"
COL_MONTH_NUMBER: Final = "month_number"

# **조합이 다른 조합과 같은 날로 붕괴했는가.** 네 조합이 절반 가까운 해에 진입·청산이 둘 다
# 같으므로, 조합 간 성적 차이가 실제로 몇 건에서 나온 것인지 이 두 컬럼이 말해 준다
COL_SHARED_YEARS: Final = "shared_years"
COL_UNIQUE_YEARS: Final = "unique_years"

# 기준선 집계를 신호 집계와 나란히 놓을 때 붙이는 접미사
BASELINE_SUFFIX: Final = "_baseline"


# ============================================================
# 표시용 한글 레이블
# ============================================================

# **이 검증만의 이름 셋뿐이다.** 나머지는 공통 계층에서 가져온다 —
# 종목·수익률·청산일은 `execution/constants.py`, 달력형 다섯은 `report/constants.py` 다.
# 여기서 다시 정의하면 같은 뜻에 이름이 두 벌이 되고, 그러면 두 산출물의 헤더가 갈린다
DISPLAY_COMBO: Final = "조합"
DISPLAY_SHARED_YEARS: Final = "다른 조합과 같은 해"
DISPLAY_UNIQUE_YEARS: Final = "이 조합만 다른 해"

# 기준선 값 컬럼 앞에 붙이는 말
BASELINE_PREFIX: Final = "기준선 "


# ============================================================
# 저장 직전 컬럼 헤더 (`COL_* → DISPLAY_*`)
# ============================================================

# **정의만 하고 `rename` 에 연결하지 않으면 규칙을 지킨 것이 아니다**
# (`src/verify_lab/CLAUDE.md` 「내부/출력 분리」). `report.tables.to_display_columns` 가
# 사전에 없는 컬럼을 발견하면 예외를 던져 그 사고를 막는다
COLUMN_LABELS: Final = {
    # 식별
    COL_TICKER: DISPLAY_TICKER,
    COL_COMBO: DISPLAY_COMBO,
    COL_MONTH_NUMBER: DISPLAY_MONTH_NUMBER,
    COL_DIRECTION: DISPLAY_DIRECTION,
    # 원자료
    COL_DATE: DISPLAY_DATE,
    COL_EXIT_DATE: DISPLAY_EXIT_DATE,
    COL_HOLD_DAYS: DISPLAY_HOLD_DAYS_EXACT,
    COL_ENTRY_CLOSE: DISPLAY_ENTRY_CLOSE,
    COL_EXIT_CLOSE: DISPLAY_EXIT_CLOSE,
    COL_FORWARD_RETURN: DISPLAY_RETURN,
    COL_EXCLUDED_REASON: DISPLAY_EXCLUDED_REASON,
    # 집계
    COL_SIGNAL_COUNT: DISPLAY_SIGNAL_COUNT,
    COL_EXCLUDED_COUNT: DISPLAY_EXCLUDED,
    COL_SAMPLE_COUNT: DISPLAY_SAMPLE_COUNT,
    COL_MEAN: DISPLAY_MEAN,
    COL_MEDIAN: DISPLAY_MEDIAN,
    COL_WIN_RATE: DISPLAY_UP_RATE,
    COL_LOSS_RATE: DISPLAY_DOWN_RATE,
    COL_MAX: DISPLAY_MAX,
    COL_MIN: DISPLAY_MIN,
    COL_STD: DISPLAY_STD,
    COL_POSITIVE_MEAN: DISPLAY_POSITIVE_MEAN,
    COL_NEGATIVE_MEAN: DISPLAY_NEGATIVE_MEAN,
    COL_POSITIVE_COUNT: DISPLAY_POSITIVE_COUNT,
    COL_NEGATIVE_COUNT: DISPLAY_NEGATIVE_COUNT,
    COL_MEAN_RATE_CONFLICT: DISPLAY_MEAN_RATE_CONFLICT,
    COL_JUDGEABLE: DISPLAY_JUDGEABLE,
    # 조합 붕괴
    COL_SHARED_YEARS: DISPLAY_SHARED_YEARS,
    COL_UNIQUE_YEARS: DISPLAY_UNIQUE_YEARS,
    # 기준선 (merge 가 붙인 접미사)
    **{
        f"{column}{BASELINE_SUFFIX}": f"{BASELINE_PREFIX}{label}"
        for column, label in (
            (COL_SIGNAL_COUNT, DISPLAY_SIGNAL_COUNT),
            (COL_EXCLUDED_COUNT, DISPLAY_EXCLUDED),
            (COL_SAMPLE_COUNT, DISPLAY_SAMPLE_COUNT),
            (COL_MEAN, DISPLAY_MEAN),
            (COL_MEDIAN, DISPLAY_MEDIAN),
            (COL_WIN_RATE, DISPLAY_UP_RATE),
            (COL_LOSS_RATE, DISPLAY_DOWN_RATE),
            (COL_MAX, DISPLAY_MAX),
            (COL_MIN, DISPLAY_MIN),
            (COL_STD, DISPLAY_STD),
            (COL_POSITIVE_MEAN, DISPLAY_POSITIVE_MEAN),
            (COL_NEGATIVE_MEAN, DISPLAY_NEGATIVE_MEAN),
            (COL_POSITIVE_COUNT, DISPLAY_POSITIVE_COUNT),
            (COL_NEGATIVE_COUNT, DISPLAY_NEGATIVE_COUNT),
        )
    },
    # 기준선 대비 차이
    COL_SIGNAL_SAMPLE_COUNT: DISPLAY_SIGNAL_SAMPLE,
    COL_BASELINE_SAMPLE_COUNT: DISPLAY_BASELINE_SAMPLE,
    COL_MEAN_EXCESS: DISPLAY_MEAN_DIFF,
    COL_MEDIAN_EXCESS: DISPLAY_MEDIAN_DIFF,
    COL_WIN_RATE_EXCESS: DISPLAY_UP_RATE_DIFF,
    COL_LOSS_RATE_EXCESS: DISPLAY_DOWN_RATE_DIFF,
    # 무작위 뽑기 대조
    COL_MEAN_P_VALUE: DISPLAY_MEAN_P_VALUE,
    COL_MEDIAN_P_VALUE: DISPLAY_MEDIAN_P_VALUE,
    COL_UP_RATE_P_VALUE: DISPLAY_UP_RATE_P_VALUE,
    COL_DOWN_RATE_P_VALUE: DISPLAY_DOWN_RATE_P_VALUE,
    COL_TEST_NOTE: DISPLAY_TEST_NOTE,
    # 배당락 (측정의 원칙 14) — 컬럼도 레이블도 공통 계층이 소유한다
    COL_DIVIDEND_MEASURED: DISPLAY_DIVIDEND_MEASURED,
    COL_DIVIDEND_HIT_COUNT: DISPLAY_DIVIDEND_HIT_COUNT,
    COL_DIVIDEND_MEAN_IMPACT: DISPLAY_DIVIDEND_MEAN_IMPACT,
}

# 비율(0~1)로 들어와 백분율로 내보낼 컬럼. **기준선과 차이 컬럼도 빠짐없이 넣는다** —
# 하나라도 빠지면 헤더는 `(%)` 인데 값이 비율로 남아 표 안에서 단위가 섞인다
_RATE_COLUMNS: Final = (
    COL_MEAN,
    COL_MEDIAN,
    COL_WIN_RATE,
    COL_LOSS_RATE,
    COL_MAX,
    COL_MIN,
    COL_STD,
    COL_POSITIVE_MEAN,
    COL_NEGATIVE_MEAN,
)

PERCENT_COLUMNS: Final = (
    *_RATE_COLUMNS,
    *(f"{column}{BASELINE_SUFFIX}" for column in _RATE_COLUMNS),
    COL_MEAN_EXCESS,
    COL_MEDIAN_EXCESS,
    COL_WIN_RATE_EXCESS,
    COL_LOSS_RATE_EXCESS,
    COL_FORWARD_RETURN,
)

# 확률로 들어와 자릿수만 맞출 컬럼. **100 을 곱하지 않는다** — 우연확률은 비율이 아니다
PROBABILITY_COLUMNS: Final = (
    COL_MEAN_P_VALUE,
    COL_MEDIAN_P_VALUE,
    COL_UP_RATE_P_VALUE,
    COL_DOWN_RATE_P_VALUE,
)


# ============================================================
# 산출물 파일
# ============================================================

# **산출물 필드 이름 → 파일 이름.** 이 사전이 「이 검증이 무슨 파일을 내는가」의 자리다.
#
# **측정 한 장뿐이다.** 축이 (종목 × 조합 × 달) 하나라 기준선·차이·우연확률·배당락이 전부
# 같은 48행이고, 나누면 사용자가 조인해야 한다. 이름이 `측정.csv` 가 아니라 `통계.csv` 인 것은
# **좁히지 않은 격자**이기 때문이다 (`src/verify_lab/CLAUDE.md` 「매매 산출물 계약」).
#
# **`signals.csv` 를 내지 않는다** — 신호가 달력으로 정의되고 체결 원자료가 `거래내역.csv` 에
# 진입가·청산가까지 들어 있어 측정의 원칙 8 을 그쪽이 충족한다.
# 체결 둘(`성적표.csv`·`거래내역.csv`)은 `execution/constants.py` 가 소유한다
# **키는 문자열 리터럴이다** — 계약 검사(`tests/test_layer_contracts.py`)가 이 사전을
# AST 로 읽으므로 상수를 키에 쓰면 선언이 없는 것으로 보인다
OUTPUT_FILES: Final[dict[str, str]] = {"statistics": STATISTICS_FILENAME}

# 산출물 필드 이름. **사전에서 꺼낸다** — 같은 리터럴을 두 번 적으면 한쪽만 바뀌었을 때
# 측정이 다 끝난 «저장 시점»에야 `KeyError` 가 난다
FIELD_STATISTICS: Final = next(iter(OUTPUT_FILES))


# ============================================================
# 실행 요약 키
# ============================================================

# **측정과 체결이 같은 것을 세므로 키도 한 벌이다** — 두 파일에 한 벌씩 두면
# `summary.json` 의 `measure` 와 `trade` 가 다른 이름으로 같은 것을 적는다
KEY_ENTRY_COUNT: Final = "entry_count"
KEY_EXCLUDED_COUNT: Final = "excluded_count"
KEY_COMBOS: Final = "combos"
KEY_MONTHS: Final = "months"
KEY_LABEL: Final = "label"
KEY_COMBO_ENTRY: Final = "entry"
KEY_COMBO_EXIT: Final = "exit"


def combos_of(keys: tuple[str, ...] | None = None) -> tuple[Combo, ...]:
    """이름으로 조합을 고른다.

    Args:
        keys: 고를 조합의 `key` 목록. **인자를 아예 주지 않으면** `COMBOS` 전부.
            빈 튜플은 **거부한다** — 「전부」와 「고른 결과가 없다」는 다른 사실이고,
            조용히 전부로 넓히면 좁히려던 실행이 전 범위 산출물로 폴더를 덮는다

    Returns:
        `COMBOS` 의 순서를 그대로 지킨 목록.
        **순서가 결정적이어야** 산출물 diff 가 「숫자가 바뀌었는가」를 말해 준다

    Raises:
        ValueError: 빈 목록을 넘겼거나 모르는 이름이 섞인 경우
    """
    if keys is None:
        return COMBOS
    if not keys:
        raise ValueError("고른 조합이 없습니다")

    known = {combo.key: combo for combo in COMBOS}
    unknown = sorted(set(keys) - set(known))
    if unknown:
        raise ValueError(f"모르는 조합입니다: {unknown} (가능한 값: {sorted(known)})")

    return tuple(combo for combo in COMBOS if combo.key in set(keys))
