"""중간선거_사이클 — 파라미터와 레이블

**매매 규칙은 하나다** — 9월 마지막 거래일 종가 매수 → 다음해 6월 마지막 거래일 종가 매도.
진입일·청산일 격자를 두지 않는다 (2026-09-22 사용자 결정).

**산출 축은 «중간선거해» 하나다** (`설계.md` 결정 ⑬). 사이클 네 칸을 견주던 대조는
10월 진입으로 잰 `결과.md` 의 기록으로 남고, 지금 구성은 그 한 칸만 낸다.
**기준선 컬럼은 그대로 남아** 「그 해 아무 달에 9개월 들어도 같은가」에 계속 답한다.

**진입이 9월 말이라 보유가 달력 분기에 맞는다** — 4분기·1분기·2분기 셋이며,
그 위에서 분기 분해(`quarters.py`)가 성립한다.

**달력 계산을 `measure/calendar_*` 에 올리지 않는다.** 진입이 「그 달 마지막 거래일」이라
달력일을 목표로 삼는 기존 규칙으로는 **말일이 30일인 달과 31일인 달을 한 인자로 겨눌 수 없고**,
청산도 진입 달이 아니라 **9개월 뒤 달**을 겨눈다. `src/verify_lab/CLAUDE.md` 가 공통 계층을
「확정 후 · 세 번째가 올 때」로 정했고 이것이 첫 번째다.
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
    RATE_TO_PERCENT,
    SERIES_DIR,
)
from verify_lab.execution.constants import (
    DISPLAY_EXIT_DATE,
    DISPLAY_RETURN,
    DISPLAY_TICKER,
)
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
    DISPLAY_NEGATIVE_COUNT,
    DISPLAY_NEGATIVE_MEAN,
    DISPLAY_NON_OVERLAPPING,
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
    MEASURE_FILENAME,
)

# 이 매매법의 이름(slug). 규약은 `src/verify_lab/CLAUDE.md` 「매매법 이름 계약」이 SoT다
TRACK_NAME: Final = "midterm_cycle"


# ============================================================
# 진입과 청산의 규칙 값
# ============================================================

# 진입 달. **그 달의 마지막 거래일에 산다** — 3분기가 끝나는 날이고, 그래서 보유가
# 4분기 첫 거래일부터 시작해 달력 분기와 어긋나지 않는다
ENTRY_MONTH: Final = 9

# 청산 달. 다음 해 2분기가 끝나는 달이다
EXIT_MONTH: Final = 6

# 진입 달에서 청산 달까지의 개월 수. **9월 → 다음해 6월이 9개월**이다.
#
# [중요] **이 값 하나가 신호와 기준선을 잇는다.** 신호는 「9월 마지막 거래일 진입」이고
# 기준선은 「아무 달 마지막 거래일 진입」인데, **청산 규칙은 둘 다 `진입 달 + 9개월의 마지막
# 거래일`** 이다. 기준선에 다른 청산 규칙을 쓰면 보유 길이가 어긋나 그 차이가 그대로
# 「기준선 대비 차이」에 실린다
EXIT_MONTH_OFFSET: Final = EXIT_MONTH - ENTRY_MONTH + 12

# 거는 방향. **「위」 하나다** — 이 매매법의 가설이 「그 구간이 강하다」이고, 반대 방향을
# 되짚을 재료는 측정 표의 오른 비율·내린 비율(1배 롱 기준)이 그대로 준다 (측정의 원칙 11).
#
# [중요] **측정과 체결이 «같은 값»을 봐야 한다.** 두 계층이 각자 들면 한쪽만 바뀌었을 때
# `측정.csv` 의 `방향` 과 `성적표.csv` 의 `방향` 이 어긋나 **1:1 조인이 조용히 깨진다**
BET_DOWN: Final = False

# 묶음 집계에서 쓰는 구간 표지. 보유 거래일 수를 구간 축에 넣으면 **한 매매가 여러 칸으로
# 쪼개져** 묶음 값이 나오지 않는다. 실제 보유일수로는 도달할 수 없는 음수를 쓴다
HORIZON_POOLED: Final = -1


# ============================================================
# 사이클 위치 — 이 검증의 축
# ============================================================

# 진입 연도를 4로 나눈 나머지로 정한다. **미국 선거 달력은 법으로 고정돼 있어
# 수십 년 전부터 알 수 있으므로 미래 참조가 아니다** (측정의 원칙 6).
#
# **이름에 「진입 연도」의 뜻이 들어 있다** — 창이 해를 걸치므로 「중간선거해」는
# 「중간선거 해 10월에 들어가 다음해 6월에 나온다」는 뜻이다
CYCLE_MIDTERM: Final = "중간선거해"
CYCLE_PRE_ELECTION: Final = "대선전해"
CYCLE_ELECTION: Final = "대선해"
CYCLE_POST_ELECTION: Final = "대선다음해"

# 나머지 → 위치. **사전으로 두는 이유**는 분기문으로 쓰면 네 갈래가 코드에 흩어져
# 「빠진 나머지」가 생겨도 예외가 나지 않기 때문이다
CYCLE_POSITION_BY_REMAINDER: Final = {
    2: CYCLE_MIDTERM,
    3: CYCLE_PRE_ELECTION,
    0: CYCLE_ELECTION,
    1: CYCLE_POST_ELECTION,
}

# **산출 축은 중간선거해 하나다** (`설계.md` 결정 ⑬, 2026-09-22 사용자 결정).
#
# [중요] **네 라벨을 남기는 것은 「중간선거해」의 정의가 그 사전이기 때문이다** —
# 4로 나눈 나머지가 2 라는 사실은 나머지 셋과 함께여야 말이 된다. 산출 축만 좁힌다.
#
# **순서가 결정적이어야** 산출물 diff 가 「숫자가 바뀌었는가」를 말해 준다
CYCLE_POSITIONS: Final = (CYCLE_MIDTERM,)


# ============================================================
# 분기 분해
# ============================================================

# 보유 구간이 지나는 달력 분기. **진입이 9월 마지막 거래일·청산이 6월 마지막 거래일이라
# 정확히 셋**이고, `quarters.py` 가 실제 분해 결과를 이 값과 대조해 어긋나면 즉시 실패한다.
#
# [중요] **달을 세어 자르지 않고 달력 분기로 묶는다.** 규칙이 바뀌면 묶음 수가 달라지는데,
# 이 상수와 대조하지 않으면 **한 칸짜리 표가 조용히 나온다**
QUARTER_LABELS: Final = ("4분기", "1분기", "2분기")

# 분기 표에서 「보유 구간 전체」를 가리키는 값. 분기 셋과 같은 컬럼에 실려 나란히 읽힌다
PERIOD_WHOLE: Final = "전체 보유"

# 「보통 얼마나 밀리나」를 읽는 축. 진입가 대비 최악이 이 값들 «안»에 든 체결 수를 센다
# (비율 0.05 = 5%). **경계값은 이내에 넣지 않는다** — 그만큼 밀린 것이 사실이다
DRAWDOWN_BUCKETS: Final[tuple[float, ...]] = (0.05, 0.10, 0.15, 0.20)


# ============================================================
# 검증 대상
# ============================================================


@dataclass(frozen=True)
class Dataset:
    """검증 대상 하나

    **ETF 와 지수는 스키마가 다르다.** ETF 는 시세(`storage/market/`)의 `Close`,
    지수는 단일 값 계열(`storage/series/`)의 `Value` 다.

    Attributes:
        ticker: 파일명에 쓰는 이름. **산출물의 데이터셋 구분자이므로 겹치면 안 된다**
        label: 표시 이름. **산출물의 종목 컬럼이 쓰는 값**이다
        symbol: 원 심볼. 지수는 `^GSPC` 처럼 접두가 붙어 파일명과 다르다
        directory: 파일이 있는 폴더
        file_template: 파일명 템플릿
        price_column: 가격 컬럼 이름
        price_decimals: 가격 출력 자릿수. 원시 데이터를 저장한 값과 같아야 한다
        is_index: 지수면 True. **살 수 없다는 사실을 산출물에 남기기 위한 값**이다
    """

    ticker: str
    label: str
    symbol: str
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


# **미국만이다** (2026-09-22 사용자 결정). 이 매매법의 신호는 미국 선거 달력이라
# 한국 시장은 교차 재현의 대상이지 이 검증의 범위가 아니다.
#
# [중요] **다우 지수(`^DJI`)를 넣지 않는다.** yfinance 가 **1992-01-02** 부터만 주어
# 완결 표본이 8건인데 **DIA(7건)보다 한 건 많을 뿐**이라 「긴 축」 구실을 못 한다
# `[실측] 2026-09-22`. 그래서 **DIA 에는 대응하는 긴 축이 없는 상태로 간다.**
#
# **지수 둘은 판정하지 않는다** — 살 수 없으므로(측정의 원칙 9) 값만 내고
# `1차 판정` 이 「판정 안 함」이 된다. 그래도 재는 것은 **중간선거 칸의 표본이
# ETF 로는 6~8건뿐이고 하한 10 에 못 미치기 때문**이다
DATASETS: Final = (
    Dataset(
        ticker="SPY",
        label="SPY",
        symbol="SPY",
        directory=MARKET_DIR,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS,
        is_index=False,
    ),
    Dataset(
        ticker="DIA",
        label="DIA",
        symbol="DIA",
        directory=MARKET_DIR,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS,
        is_index=False,
    ),
    Dataset(
        ticker="QQQ",
        label="QQQ",
        symbol="QQQ",
        directory=MARKET_DIR,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS,
        is_index=False,
    ),
    Dataset(
        ticker="GSPC",
        label="S&P 500 지수",
        symbol="^GSPC",
        directory=SERIES_DIR,
        file_template=INDEX_FILE_TEMPLATE,
        price_column=COL_VALUE,
        price_decimals=PRICE_DECIMALS,
        is_index=True,
    ),
    Dataset(
        ticker="IXIC",
        label="나스닥 종합 지수",
        symbol="^IXIC",
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

# **격자를 전부 낸다** (측정의 원칙 1 · `.claude/rules/trading.md` 「경계는 행위」).
# 고르지 않으므로 과최적화가 아니며, 값을 확정하는 것은 `규칙.md` 의 몫이다.
#
# [중요] **다른 매매법의 −2 ~ −10% 격자는 9개월 보유에 너무 좁다.** 2018년 4분기 하나만
# S&P 500 −14% 라 그 격자로는 전 구간이 손절로 끊겨 `.claude/rules/trading.md` 가 요구하는
# 「평평한 구간」을 찾을 수 없다. 그래서 −30% 까지 넓힌다 (2026-09-22 사용자 승인).
#
# **`None` 은 무손절 대조축**이다 — 손절이 무엇을 막았는지는 대조 없이 보이지 않는다
STOP_LEVELS_ETF: Final[tuple[float | None, ...]] = (None, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30)

# **지수는 한 줄뿐이다.** 장중 손절에 고가·저가가 필요한데 지수는 종가만 있어
# `손절선(%)` 에 「손절불가」로 적힌다
STOP_LEVELS_INDEX: Final[tuple[float | None, ...]] = (None,)


# ============================================================
# DataFrame 컬럼 (내부 계산용 토큰)
# ============================================================

COL_TICKER: Final = "ticker"

# 진입 연도. **청산 연도가 아니다** — 창이 해를 걸치므로 둘을 섞으면 축이 한 해씩 밀린다
COL_CYCLE_YEAR: Final = "cycle_year"

# 사이클 위치. 이 검증의 축이다
COL_CYCLE_POSITION: Final = "cycle_position"

# 기준선 집계를 신호 집계와 나란히 놓을 때 붙이는 접미사
BASELINE_SUFFIX: Final = "_baseline"

# 겹치지 않게 고를 수 있는 체결의 최대 개수. **산식은 `measure.statistics.max_non_overlapping`
# 하나가 소유한다** (`src/verify_lab/CLAUDE.md` 「비중첩 표본 계약」).
#
# [중요] **기준선이 이 값을 «반드시» 필요로 한다.** 기준선은 달마다 진입해 9개월을 드는
# 롤링이라 이웃 구간이 8/9 씩 겹친다 — 표본 수만 적으면 **실제보다 훨씬 단단해 보인다**
# (S&P 500 중간선거해의 기준선 표본은 288 인데 겹치지 않게 고르면 그 1/9 수준이다).
# **신호 쪽도 함께 낸다** — 4년 간격이라 겹침이 없다는 사실 자체가 「표본이 서로 독립인가」
# (측정의 원칙 5)에 대한 답이고, 두 값이 같다는 것으로 그것이 드러난다.
#
# **표시 이름은 `report/constants.py` 가 소유한다** — 이 매매법이 세 번째라
# 「세 번째가 올 때 정한다」에 따라 올렸다 (2026-09-22). 컬럼 토큰만 여기 둔다
COL_NON_OVERLAPPING: Final = "NonOverlappingCount"
COL_BASELINE_NON_OVERLAPPING: Final = f"{COL_NON_OVERLAPPING}{BASELINE_SUFFIX}"


# ============================================================
# 표시용 한글 레이블
# ============================================================

# **여기 없는 이름은 공통 계층에서 가져온다** — 같은 뜻에 이름이 두 벌이 되면
# 두 산출물의 헤더가 갈린다
DISPLAY_CYCLE_POSITION: Final = "사이클 위치"
DISPLAY_CYCLE_YEAR: Final = "진입 연도"

# 분기 표의 축. **`구간` 을 쓰지 않는다** — `report/constants.DISPLAY_HORIZON` 이
# 측정 구간을 그 이름으로 부르고 있어 같은 낱말이 두 뜻을 갖게 된다
DISPLAY_QUARTER: Final = "분기"

# 분기 원자료의 양 끝. **`진입가`·`청산가` 와 다른 이름인 것은 뜻이 다르기 때문이다** —
# 분기의 시작가는 «직전 분기의 종가»이지 이 매매의 진입가가 아니다.
#
# [중요] **앞에 「분기」를 붙인다.** 배수 검증 둘이 `시작일`·`종료일` 을 그 구간의 양 끝이라는
# 뜻으로 이미 쓰고 있어, 그냥 두면 같은 낱말이 세 곳에서 다른 것을 가리킨다
# (`tests/test_layer_contracts.py` 의 레이블 겹침 검사가 이것을 막는다)
DISPLAY_SEGMENT_START_DATE: Final = "분기 시작일"
DISPLAY_SEGMENT_START_PRICE: Final = "분기 시작가"
DISPLAY_SEGMENT_END_DATE: Final = "분기 종료일"
DISPLAY_SEGMENT_END_PRICE: Final = "분기 종료가"

# 낙폭의 두 분모 (`설계.md` 결정 ⑯). **이름에 분모를 박는 것이 요점이다** —
# 어느 기준으로 잰 값인지가 헤더에 없으면 두 열이 구별되지 않는다
DISPLAY_WORST_VS_ENTRY: Final = "진입가 대비 최악(%)"
DISPLAY_WORST_VS_SEGMENT: Final = "분기 시작가 대비 최악(%)"

# 낙폭 분포. **성적표의 `보유 중 최악(%)` 은 구간 «최솟값» 하나**라
# 「보통 얼마나 밀리나」에 답하지 못한다 — 그 자리를 이 컬럼들이 채운다
DISPLAY_WORST_MEAN: Final = "진입가 대비 최악 평균(%)"
DISPLAY_WORST_MEDIAN: Final = "진입가 대비 최악 중앙값(%)"
DISPLAY_WORST_Q25: Final = "진입가 대비 최악 25%분위(%)"
DISPLAY_WORST_Q75: Final = "진입가 대비 최악 75%분위(%)"
DISPLAY_WORST_SHALLOWEST: Final = "진입가 대비 최악 가장 얕게(%)"
DISPLAY_WORST_DEEPEST: Final = "진입가 대비 최악 가장 깊게(%)"
DISPLAY_SEGMENT_WORST_MEAN: Final = "분기 시작가 대비 최악 평균(%)"
DISPLAY_SEGMENT_WORST_MEDIAN: Final = "분기 시작가 대비 최악 중앙값(%)"
DISPLAY_SEGMENT_WORST_DEEPEST: Final = "분기 시작가 대비 최악 가장 깊게(%)"


def bucket_label(threshold: float) -> str:
    """낙폭 구간 컬럼의 머리를 만든다.

    **상수 넷을 손으로 적지 않는다** — `DRAWDOWN_BUCKETS` 를 고치면 헤더가 따라와야 하고,
    두 벌로 두면 한쪽만 바뀌어도 예외가 나지 않는다.

    Args:
        threshold: 낙폭 상한 (비율, 0.05 = 5%)

    Returns:
        `-5% 이내 건수` 형태의 헤더
    """
    return f"-{threshold * RATE_TO_PERCENT:g}% 이내 건수"


# 기준선 값 컬럼 앞에 붙이는 말
BASELINE_PREFIX: Final = "기준선 "


# ============================================================
# 저장 직전 컬럼 헤더 (`COL_* → DISPLAY_*`)
# ============================================================

# **정의만 하고 `rename` 에 연결하지 않으면 규칙을 지킨 것이 아니다**
# (`src/verify_lab/CLAUDE.md` 「내부/출력 분리」)
COLUMN_LABELS: Final = {
    # 식별
    COL_TICKER: DISPLAY_TICKER,
    COL_CYCLE_POSITION: DISPLAY_CYCLE_POSITION,
    COL_CYCLE_YEAR: DISPLAY_CYCLE_YEAR,
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
    # 비중첩 표본 — 기준선이 롤링이라 표본 수만으로는 단단함을 오독한다
    COL_NON_OVERLAPPING: DISPLAY_NON_OVERLAPPING,
    COL_BASELINE_NON_OVERLAPPING: f"{BASELINE_PREFIX}{DISPLAY_NON_OVERLAPPING}",
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
    # 무작위 뽑기 대조. **판정에 쓰지 않지만 계산은 남긴다** — 지우면 기준선 셋 중
    # 「무작위 진입」이 통째로 사라진다 (루트 `CLAUDE.md`)
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
# **측정 한 장뿐이다.** 축이 (종목 × 사이클 위치) 하나라 기준선·차이·우연확률·배당락이
# 전부 같은 행에 실린다. 이름이 `측정.csv` 인 것은 **확정 규칙 하나만 내기** 때문이다 —
# `통계.csv` 는 축 전체를 내는 표의 이름이라 담는 축이 다르다.
#
# **`signals.csv` 를 내지 않는다** — 신호가 달력으로 정의되고 체결 원자료가 `거래내역.csv` 에
# 진입가·청산가까지 들어 있어 측정의 원칙 8 을 그쪽이 충족한다.
# **키는 문자열 리터럴이다** — 계약 검사가 이 사전을 AST 로 읽으므로 상수를 키에 쓰면
# 선언이 없는 것으로 보인다
OUTPUT_FILES: Final[dict[str, str]] = {"statistics": MEASURE_FILENAME}

# 산출물 필드 이름. **사전에서 꺼낸다** — 같은 리터럴을 두 번 적으면 한쪽만 바뀌었을 때
# 측정이 다 끝난 «저장 시점»에야 `KeyError` 가 난다
FIELD_STATISTICS: Final = next(iter(OUTPUT_FILES))

# **분기 표 둘은 이 매매법의 것이라 여기가 소유자다.** 성적표·거래내역은 세 매매법이
# 공유하는 이름이라 `execution/constants.py` 가 갖는다 — 소유자가 갈리는 것은
# 계층이 달라서가 아니라 **공유 여부가 달라서**다.
#
# **원자료와 집계를 나누는 것은 매매 산출물의 관용 그대로다** (`거래내역` ↔ `성적표`) —
# 한 파일에 두 granularity 를 섞으면 어느 행이 무엇인지 표 안에서 판별되지 않는다
QUARTER_TRADES_FILENAME: Final = "분기내역.csv"
QUARTER_SUMMARY_FILENAME: Final = "분기.csv"


# ============================================================
# 실행 요약 키
# ============================================================

# **측정과 체결이 같은 것을 세므로 키도 한 벌이다** — 두 파일에 한 벌씩 두면
# `summary.json` 의 `measure` 와 `trade` 가 다른 이름으로 같은 것을 적는다
KEY_ENTRY_COUNT: Final = "entry_count"
KEY_EXCLUDED_COUNT: Final = "excluded_count"
KEY_ENTRY_MONTH: Final = "entry_month"
KEY_EXIT_MONTH: Final = "exit_month"
KEY_POSITIONS: Final = "cycle_positions"
KEY_LABEL: Final = "label"


def datasets_of(tickers: tuple[str, ...] | None = None) -> tuple[Dataset, ...]:
    """이름으로 대상을 고른다.

    Args:
        tickers: 고를 대상의 `ticker` 목록. **인자를 아예 주지 않으면** `DATASETS` 전부.
            빈 튜플은 **거부한다** — 「전부」와 「고른 결과가 없다」는 다른 사실이고,
            조용히 전부로 넓히면 좁히려던 실행이 전 범위 산출물로 폴더를 덮는다

    Returns:
        `DATASETS` 의 순서를 그대로 지킨 목록.
        **순서가 결정적이어야** 산출물 diff 가 「숫자가 바뀌었는가」를 말해 준다

    Raises:
        ValueError: 빈 목록을 넘겼거나 모르는 이름이 섞인 경우
    """
    if tickers is None:
        return DATASETS
    if not tickers:
        raise ValueError("고른 대상이 없습니다")

    known = {dataset.ticker: dataset for dataset in DATASETS}
    unknown = sorted(set(tickers) - set(known))
    if unknown:
        raise ValueError(f"모르는 종목입니다: {unknown} (가능한 값: {sorted(known)})")

    return tuple(dataset for dataset in DATASETS if dataset.ticker in set(tickers))
