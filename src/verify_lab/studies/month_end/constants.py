"""검증 #10(코스닥 월 하순 진입) 이벤트 정의와 실행이 공유하는 상수

파라미터 값은 `docs/spec/month_end.md` 가 확정한 것이며, **성과를 보며 돌리는 노브가 아니다.**
격자 축을 나란히 산출해 보고하기 위한 목록이므로 하나를 골라 두지 않는다 (측정의 원칙 1).

표시용 한글 레이블도 여기 둔다. `report` 는 어떤 검증이 자기를 쓰는지 몰라야 하므로
검증별 컬럼 이름을 알 수 없고, 그 이름을 정하는 것은 이 검증의 몫이다.
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
from verify_lab.measure.constants import (
    COL_EXCLUDED_COUNT,
    COL_EXCLUDED_REASON,
    COL_FORWARD_RETURN,
    COL_JUDGEABLE,
    COL_SIGNAL_COUNT,
)
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
    DISPLAY_DOWN_RATE,
    DISPLAY_DOWN_RATE_DIFF,
    DISPLAY_DOWN_RATE_P_VALUE,
    DISPLAY_EXCLUDED,
    DISPLAY_JUDGEABLE,
    DISPLAY_MAX,
    DISPLAY_MEAN,
    DISPLAY_MEAN_DIFF,
    DISPLAY_MEAN_P_VALUE,
    DISPLAY_MEDIAN,
    DISPLAY_MEDIAN_DIFF,
    DISPLAY_MEDIAN_P_VALUE,
    DISPLAY_MIN,
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
)

# 산출물 폴더 이름에 붙는 검증 이름
STUDY_NAME: Final = "month_end"


# ============================================================
# 검증 대상 (`docs/spec/month_end.md` §3.4)
# ============================================================

# 집행 역할 — **이 상품으로 어느 방향을 거는가.** 방향을 고르는 값이 아니라 상품의 성질이다
# (측정의 원칙 11 은 그대로 지킨다 — 산출물은 언제나 두 방향을 나란히 낸다).
#
# 「아래」를 1배 ETF 의 하락률로 재면 분배락 하락이 이익으로 잡히는데 **인버스는 그만큼 오르지
# 않는다** (코스닥 4월 실측 +0.65%p). 인버스 종가에는 분배락·총보수·일일 리밸런싱 손실이
# 이미 들어 있어 따로 뺄 것이 없다. 근거는 `docs/spec/month_end.md` §7.9 다
EXECUTION_ROLE_UP: Final = "위 집행"
EXECUTION_ROLE_DOWN: Final = "아래 집행"
EXECUTION_ROLE_NONE: Final = "불가"

EXECUTION_ROLES: Final = (EXECUTION_ROLE_UP, EXECUTION_ROLE_DOWN, EXECUTION_ROLE_NONE)

MARKET_KOSPI: Final = "코스피"
MARKET_KOSDAQ: Final = "코스닥"


# ============================================================
# 검증 대상 정의
# ============================================================


@dataclass(frozen=True)
class Dataset:
    """검증 대상 하나

    **ETF 와 지수는 스키마가 다르다.** ETF 는 시세(`storage/market/`)의 `Close`,
    지수는 단일 값 계열(`storage/series/`)의 `Value` 다. 코스닥150 지수는 소급 산출 구간의
    시가·고가·저가가 전부 0 이라 시세 스키마로 받을 수 없었다 (spec §7.6).
    코스피 두 지수도 같은 성질이며 그 실측은 spec §7.11 에 있다.

    Attributes:
        ticker: 종목 또는 지수 코드. **산출물의 데이터셋 구분자이므로 겹치면 안 된다**
        label: 표시 이름
        directory: 파일이 있는 폴더
        file_template: 파일명 템플릿
        price_column: 가격 컬럼 이름
        price_decimals: 가격 출력 자릿수. 원시 데이터를 저장한 값과 같아야 한다
        is_index: 지수면 True. **살 수 없다는 사실을 산출물에 남기기 위한 값**이다
        execution_role: 이 상품으로 거는 방향. 지수는 `EXECUTION_ROLE_NONE` 이다
    """

    ticker: str
    label: str
    directory: Path
    file_template: str
    price_column: str
    price_decimals: int
    is_index: bool
    execution_role: str

    @property
    def path(self) -> Path:
        """데이터 파일 경로.

        Returns:
            읽을 파일의 전체 경로
        """
        return self.directory / self.file_template.format(ticker=self.ticker)


# 시장마다 **ETF 둘이 본검증이고 지수 둘은 기간 확장용 보조**다.
# 지수는 살 수 없으므로(측정의 원칙 9) 결과 문서에 그 사실을 적는다.
#
# **두 시장을 나눠 두는 이유**는 `strategy` 가 코스닥만 돌기 때문이다. 손절 격자는 아직
# 코스닥에서만 냈으므로, 전체 목록을 기본값으로 받으면 매매 규칙이 조용히 코스피까지 돈다
DATASETS_KOSPI: Final = (
    Dataset(
        ticker="069500",
        label="KODEX 200",
        directory=MARKET_DIR,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS_KRW,
        is_index=False,
        execution_role=EXECUTION_ROLE_UP,
    ),
    Dataset(
        ticker="114800",
        label="KODEX 인버스",
        directory=MARKET_DIR,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS_KRW,
        is_index=False,
        execution_role=EXECUTION_ROLE_DOWN,
    ),
    Dataset(
        ticker="1028",
        label="코스피200 지수",
        directory=SERIES_DIR,
        file_template=INDEX_FILE_TEMPLATE,
        price_column=COL_VALUE,
        price_decimals=PRICE_DECIMALS,
        is_index=True,
        execution_role=EXECUTION_ROLE_NONE,
    ),
    Dataset(
        ticker="1001",
        label="코스피 종합지수",
        directory=SERIES_DIR,
        file_template=INDEX_FILE_TEMPLATE,
        price_column=COL_VALUE,
        price_decimals=PRICE_DECIMALS,
        is_index=True,
        execution_role=EXECUTION_ROLE_NONE,
    ),
)

DATASETS_KOSDAQ: Final = (
    Dataset(
        ticker="229200",
        label="KODEX 코스닥150",
        directory=MARKET_DIR,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS_KRW,
        is_index=False,
        execution_role=EXECUTION_ROLE_UP,
    ),
    Dataset(
        ticker="251340",
        label="KODEX 코스닥150선물인버스",
        directory=MARKET_DIR,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS_KRW,
        is_index=False,
        execution_role=EXECUTION_ROLE_DOWN,
    ),
    Dataset(
        ticker="2203",
        label="코스닥150 지수",
        directory=SERIES_DIR,
        file_template=INDEX_FILE_TEMPLATE,
        price_column=COL_VALUE,
        price_decimals=PRICE_DECIMALS,
        is_index=True,
        execution_role=EXECUTION_ROLE_NONE,
    ),
    Dataset(
        ticker="2001",
        label="코스닥 종합지수",
        directory=SERIES_DIR,
        file_template=INDEX_FILE_TEMPLATE,
        price_column=COL_VALUE,
        price_decimals=PRICE_DECIMALS,
        is_index=True,
        execution_role=EXECUTION_ROLE_NONE,
    ),
)

# 인자 없이 실행했을 때 재는 대상 — 두 시장 전부
DATASETS: Final = DATASETS_KOSPI + DATASETS_KOSDAQ

# 종목명 → 시장. **두 목록에서 파생시킨다** — 대상마다 시장을 손으로 적으면 목록과 어긋나도
# 예외가 나지 않는다. 구분자가 종목명인 것은 출력 계약과 같다
MARKET_BY_LABEL: Final = {
    **{dataset.label: MARKET_KOSPI for dataset in DATASETS_KOSPI},
    **{dataset.label: MARKET_KOSDAQ for dataset in DATASETS_KOSDAQ},
}

# ============================================================
# 격자 축 (`docs/spec/month_end.md` §3.3 결정 ③)
# ============================================================

# 진입 목표 달력일. 원 매매법인 20일 앞뒤를 감싼다 — 20일만 튀는지 이웃도 같은지가
# 오버피팅 판정의 근거다 (측정의 원칙 7)
ENTRY_CALENDAR_DAYS: Final = (15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25)

# 청산 상대 거래일. **그 달 마지막 거래일이 0** 이고 음수는 그 이전, 양수는 익월이다.
# 양수 칸은 「월말 효과를 통과했는가」를 함께 묻는다
EXIT_OFFSETS: Final = (-3, -2, -1, 0, 1, 2, 3)

# 원 매매법의 칸. 월별 분해는 **이 칸에만** 건다 — 격자 전부를 쪼개면 924칸이 되어
# 다중 비교가 폭발하고 칸당 표본이 무너진다 (§3.7)
BASE_ENTRY_DAY: Final = 20
BASE_EXIT_OFFSET: Final = 0

# ============================================================
# 일정표 컬럼 (내부 계산용 토큰)
# ============================================================

# 진입 달. 청산이 익월로 넘어가도 **그 매매가 속한 달은 진입 달**이다
COL_MONTH: Final = "month"

# 목표 달력일. 앞당김 전의 값이라 격자 축으로 그대로 쓴다
COL_TARGET_DAY: Final = "target_day"

# 그 달의 마지막 거래일. 청산 상대 거래일의 기준점이다
COL_MONTH_LAST_DATE: Final = "month_last_date"

COL_EXIT_DATE: Final = "exit_date"
COL_EXIT_OFFSET: Final = "exit_offset"

# 실제 보유 거래일 수. 달마다 다르므로 구간 축이 아니라 별도 컬럼으로 남긴다
COL_HOLD_DAYS: Final = "hold_days"

# 사용자가 차트로 직접 대조하는 원자료 (측정의 원칙 8)
COL_ENTRY_CLOSE: Final = "entry_close"
COL_EXIT_CLOSE: Final = "exit_close"

# 앞당김으로 서로 다른 달력일이 같은 거래일에 모인 달의 수 (결정 ⑥).
# 격자의 칸들이 독립이 아니라는 사실의 근거값이다
COL_CONVERGED_MONTHS: Final = "converged_months"

# ============================================================
# 구간 표지
# ============================================================

# 구간 축에 넣는 값. **보유일수가 아니라 표지 하나**다 — 보유일수를 넣으면 한 매매가
# 길이별 여러 칸으로 쪼개져 묶음 값이 나오지 않는다. 실제 보유일수는 `COL_HOLD_DAYS` 에 남는다.
# 음수를 쓰는 것은 거래일 구간(1 이상)과 섞이지 않게 하기 위해서다
HORIZON_MONTH_END: Final = -1

# ============================================================
# 제외 사유
# ============================================================

# 그 달에 목표 달력일 이전 거래일이 없는 경우. 앞당김은 **그 달 안에서만** 일어나므로
# 전월로 넘어가지 않고 여기서 멈춘다
REASON_NO_ENTRY_DAY: Final = "그 달에 목표 달력일 이전 거래일이 없음"

# 청산일이 진입일보다 뒤가 아닌 경우. 격자의 극단 칸에서 생기며, 값을 지어내는 대신
# 제외하고 사유를 남긴다 (결정 ④)
REASON_NO_HOLDING: Final = "청산일이 진입일보다 뒤가 아님"

# ============================================================
# 표시용 한글 레이블
# ============================================================

# ============================================================
# 집계 축과 기준선 이름
# ============================================================

COL_TICKER: Final = "ticker"

# 격자 칸 하나를 가리키는 이름 (`20일 → 말일` 처럼). **판정 계층이 단일 축 컬럼을 받으므로**
# 2차원 격자를 한 축으로 접어 넘긴다
COL_GRID_CELL: Final = "grid_cell"

# 월별 분해의 축 (1~12)
COL_MONTH_NUMBER: Final = "month_number"

# 시기 구분 이름이 들어가는 컬럼
COL_PERIOD: Final = "period"

# 어느 기준선과 견줬는지 밝히는 컬럼
COL_BASELINE_KIND: Final = "baseline"

# 평균의 부호와 방향 비율이 어긋나는 칸 (측정의 원칙 13)
COL_MEAN_RATE_CONFLICT: Final = "mean_rate_conflict"

# 그 행을 실제로 집행하는 상품이 무엇인가
COL_EXECUTION_ROLE: Final = "execution_role"

# 집행 축 표가 어느 시장의 행인가. 코스피와 코스닥을 나란히 읽으려면 축이 하나 더 필요하다
COL_MARKET: Final = "market"

# 어느 기준선과 견줬는지 밝히는 이름. 둘은 묻는 질문이 다르다 (spec §3.6 결정 ⑤)
BASELINE_MONTH_ANY: Final = "그 달 아무 날 진입"
BASELINE_MATCHED_LENGTH: Final = "같은 길이 단순 보유"

# 기준선 집계를 신호 집계와 나란히 놓을 때 붙이는 접미사
BASELINE_SUFFIX: Final = "_baseline"

# 방향 비율의 절반. 평균-비율 어긋남 판정의 기준선이다
HALF_RATE: Final = 0.5

# ============================================================
# 시기 구분 (측정의 원칙 17)
# ============================================================

# 균등 2분할의 이름. **판정용**이며 칸당 표본 하한을 지킨다
DISPLAY_PERIOD_EARLY: Final = "앞 절반"
DISPLAY_PERIOD_LATE: Final = "뒤 절반"

# 관찰용 최근 구간. **판정용에서 이미 무너진 칸을 확인하는 데에만 쓴다** —
# 이 구간만으로 칸을 떨어뜨리지 않는다. 기준일은 실행 시각이 아니라 **데이터의 마지막 거래일**이다
RECENT_WINDOWS_YEARS: Final = (10, 5)
DISPLAY_PERIOD_RECENT: Final = "최근 {years}년"

# **후보 판정의 시기 항목이 읽는 구간.** 균등 분할만이며 관찰용 최근 구간은 들어가지 않는다.
# 최근 구간은 기간이 짧아 표본이 적고, **결과를 보고 구간을 고르는 것과 구별되지 않는다** —
# 판정에 섞으면 「최근이 좋으니 통과」가 되어 측정의 원칙 17 이 금지한 일이 일어난다.
# 산출물(`periods.csv`·`month_halves.csv`)에는 네 구간이 모두 남는다
JUDGING_PERIODS: Final = (DISPLAY_PERIOD_EARLY, DISPLAY_PERIOD_LATE)

DISPLAY_MONTH: Final = "진입 달"
DISPLAY_TARGET_DAY: Final = "진입 달력일"
DISPLAY_MONTH_LAST_DATE: Final = "그 달 마지막 거래일"
DISPLAY_EXIT_DATE: Final = "청산일"
DISPLAY_EXIT_OFFSET: Final = "청산 상대 거래일"
DISPLAY_HOLD_DAYS: Final = "보유 거래일"
DISPLAY_ENTRY_CLOSE: Final = "진입 종가"
DISPLAY_EXIT_CLOSE: Final = "청산 종가"
DISPLAY_CONVERGED_MONTHS: Final = "앞당김 수렴 달 수"
DISPLAY_TICKER: Final = "대상"
DISPLAY_MONTH_NUMBER: Final = "월"
DISPLAY_PERIOD: Final = "시기"
DISPLAY_BASELINE_KIND: Final = "기준선"
DISPLAY_MEAN_RATE_CONFLICT: Final = "평균-비율 어긋남"
DISPLAY_MARKET: Final = "시장"
DISPLAY_EXECUTION_ROLE: Final = "집행"

# `report/constants.py` 에 없어 이 검증이 정한다 — 원자료 표에만 쓰인다
DISPLAY_RETURN: Final = "수익률(%)"
DISPLAY_EXCLUDED_REASON: Final = "제외 사유"

DISPLAY_GRID_CELL: Final = "격자 칸"

# 격자 칸 이름의 형식. 청산 상대 거래일 0 은 「말일」로 적어 원 매매법이 눈에 띄게 한다
GRID_CELL_TEMPLATE: Final = "{day}일 → {exit}"
GRID_EXIT_MONTH_END: Final = "말일"
GRID_EXIT_RELATIVE: Final = "말일{offset:+d}"

# 기준선 값 컬럼 앞에 붙이는 말
_BASELINE_PREFIX: Final = "기준선 "

# ============================================================
# 저장 직전 컬럼 헤더 (`COL_* → DISPLAY_*`)
# ============================================================

# **정의만 하고 `rename` 에 연결하지 않으면 규칙을 지킨 것이 아니다.**
# 검증 #7 이 이 연결을 빠뜨려 영문 헤더가 그대로 나간 적이 있다
# (`src/verify_lab/CLAUDE.md` 「내부/출력 분리」). `report.tables.to_display_columns` 가
# 사전에 없는 컬럼을 발견하면 예외를 던져 그 사고를 막는다
COLUMN_LABELS: Final = {
    # 식별
    COL_TICKER: DISPLAY_TICKER,
    COL_GRID_CELL: DISPLAY_GRID_CELL,
    COL_TARGET_DAY: DISPLAY_TARGET_DAY,
    COL_EXIT_OFFSET: DISPLAY_EXIT_OFFSET,
    COL_MONTH_NUMBER: DISPLAY_MONTH_NUMBER,
    COL_PERIOD: DISPLAY_PERIOD,
    COL_BASELINE_KIND: DISPLAY_BASELINE_KIND,
    # 원자료
    COL_MONTH: DISPLAY_MONTH,
    COL_DATE: DISPLAY_DATE,
    COL_MONTH_LAST_DATE: DISPLAY_MONTH_LAST_DATE,
    COL_EXIT_DATE: DISPLAY_EXIT_DATE,
    COL_HOLD_DAYS: DISPLAY_HOLD_DAYS,
    COL_ENTRY_CLOSE: DISPLAY_ENTRY_CLOSE,
    COL_EXIT_CLOSE: DISPLAY_EXIT_CLOSE,
    COL_FORWARD_RETURN: DISPLAY_RETURN,
    COL_EXCLUDED_REASON: DISPLAY_EXCLUDED_REASON,
    COL_CONVERGED_MONTHS: DISPLAY_CONVERGED_MONTHS,
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
    # 기준선 (merge 가 붙인 접미사)
    **{
        f"{column}{BASELINE_SUFFIX}": f"{_BASELINE_PREFIX}{label}"
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

# 확률로 들어와 자릿수만 맞출 컬럼
PROBABILITY_COLUMNS: Final = (
    COL_MEAN_P_VALUE,
    COL_MEDIAN_P_VALUE,
    COL_UP_RATE_P_VALUE,
    COL_DOWN_RATE_P_VALUE,
)
