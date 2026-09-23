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
from verify_lab.measure.baseline import DEFAULT_MA_WINDOW
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
# 진입 위치 지표 — 진입위치 표와 분할매수 C 방식이 함께 쓴다
# ============================================================

# RSI 창과 과매도 기준. **Wilder 가 정한 관행값**이고 증권앱·차트가 보여 주는 값이다 —
# 사용자가 차트로 대조할 수 있어야 한다 (측정의 원칙 8). **RSI 는 0~100 지수값이지 비율이 아니다.**
#
# [중요] **Wilder 평활은 지수형 평균이다** — 「이동평균은 SMA 만」(측정의 원칙 15)과 문자
# 그대로는 부딪힌다. 그 원칙의 취지는 **둘을 나란히 내 고를 여지를 만들지 않는 것**이라
# 한 방식만 쓰면 충족된다고 보고 사용자가 정했다 (2026-09-23, `설계.md` 결정 ⑰)
RSI_WINDOW: Final = 14
RSI_OVERSOLD: Final = 30.0

# 이격도(종가 ÷ SMA)의 두 창. 200일은 **조건부 기준선이 이미 쓰는 창**이라 그 값을 가져온다 —
# 같은 창을 두 곳에 적으면 한쪽만 바뀌어도 예외가 나지 않는다
SHORT_MA_WINDOW: Final = 20
LONG_MA_WINDOW: Final = DEFAULT_MA_WINDOW

# 20일 이격도의 과매도 기준 (비율, 0.95 = 이동평균의 95%)
DISPARITY_OVERSOLD: Final = 0.95

# 52주 = 252 거래일. **진입일을 포함한** 창의 최고 종가와 견준다
HIGH_LOOKBACK_DAYS: Final = 252

# 지표 표의 컬럼 (내부 토큰)
COL_RSI: Final = "rsi"
COL_DISPARITY_SHORT: Final = "disparity_short"
COL_DISPARITY_LONG: Final = "disparity_long"
COL_HIGH_DISTANCE: Final = "high_distance"


# ============================================================
# 분할매수 — 격자는 결과를 보기 전(2026-09-23 계획서 승인)에 고정했다
# ============================================================

# 추가 몫을 살 수 있는 달. **진입 다음 거래일부터 마지막 달의 마지막 거래일까지가 창이다.**
#
# [중요] **이 창은 결과를 보고 정한 값이다** — 최저점이 ETF 21건 전부 4분기에 있었다는
# 측정(`결과.md` §9.2)에서 나왔다. 그 사실을 결과 문서 한계에 적는다
ADDITION_MONTHS: Final = (10, 11, 12)

# 미체결 처리. **조건부 방식은 둘 다 낸다** — 하나를 고르면 그 선택이 결론에 숨는다.
# 조건이 없는 방식(일시매수·월말)은 미체결이 생길 수 없어 「해당 없음」 하나다
FALLBACK_NONE: Final = "해당 없음"
FALLBACK_BUY_AT_Q4_END: Final = "12월 말 일괄 매수"
FALLBACK_KEEP_CASH: Final = "현금 유지"

# 몫마다의 체결 사유. **몫이 없는 칸은 비우고 몫이 있는데 안 산 칸은 「미체결」이다** —
# 둘을 한 값으로 적으면 「그 방식에는 그 몫이 없다」와 「조건이 안 왔다」가 구별되지 않는다
FILL_FIRST: Final = "첫 몫"
FILL_MONTH_END: Final = "월말"
FILL_LADDER: Final = "단계 도달"
FILL_INDICATOR: Final = "지표 신호"
FILL_Q4_END: Final = "12월 말 일괄"
FILL_UNFILLED: Final = "미체결"


@dataclass(frozen=True)
class LumpSum:
    """9월 마지막 거래일 종가에 전액 — 분할 격자의 대조 칸"""

    @property
    def tranches(self) -> int:
        """몫 수.

        Returns:
            1
        """
        return 1


@dataclass(frozen=True)
class MonthEnds:
    """정해진 달의 마지막 거래일 종가에 한 몫씩 — 조건이 없어 미체결이 생기지 않는다

    Attributes:
        months: 추가 몫을 사는 달. `ADDITION_MONTHS` 안의 값이어야 한다
    """

    months: tuple[int, ...]

    def __post_init__(self) -> None:
        """달 목록을 검사한다.

        Raises:
            ValueError: 비었거나, 창 밖의 달이 있거나, 오름차순이 아닌 경우
        """
        if not self.months:
            raise ValueError("추가 몫을 살 달이 없습니다")
        if not set(self.months) <= set(ADDITION_MONTHS):
            raise ValueError(f"추가 매수 창 밖의 달이 있습니다: {self.months} (가능한 달: {ADDITION_MONTHS})")
        if list(self.months) != sorted(set(self.months)):
            raise ValueError(f"달은 겹치지 않는 오름차순이어야 합니다: {self.months}")

    @property
    def tranches(self) -> int:
        """몫 수 — 첫 몫에 달마다 한 몫.

        Returns:
            달 수 + 1
        """
        return len(self.months) + 1


@dataclass(frozen=True)
class PriceLadder:
    """첫 몫 가격 대비 사다리 — 종가가 단계 이하로 처음 내려간 날의 «다음 거래일» 종가에 한 몫씩

    Attributes:
        step_rate: 단계 간격 (비율, 0.05 = 5%). k 번째 단계는 첫 몫 가격의 `1 − k × 간격` 이다
        tranches: 첫 몫을 포함한 몫 수
    """

    step_rate: float
    tranches: int

    def __post_init__(self) -> None:
        """사다리 모양을 검사한다.

        Raises:
            ValueError: 몫이 둘 미만이거나, 간격이 양수가 아니거나, 가장 깊은 단계가 0 이하인 경우
        """
        if self.tranches < 2:
            raise ValueError(f"사다리는 몫이 둘 이상이어야 합니다 (하나면 일시매수다): {self.tranches}")
        if self.step_rate <= 0:
            raise ValueError(f"단계 간격은 양수여야 합니다: {self.step_rate}")
        if 1.0 - (self.tranches - 1) * self.step_rate <= 0:
            raise ValueError(f"가장 깊은 단계가 0 이하라 영원히 닿지 않습니다: 간격 {self.step_rate}, 몫 {self.tranches}")

    @property
    def level_rates(self) -> tuple[float, ...]:
        """단계마다 첫 몫 가격에서 내려간 비율.

        Returns:
            얕은 단계부터 (간격 × 1, 간격 × 2, …)
        """
        return tuple(self.step_rate * order for order in range(1, self.tranches))


@dataclass(frozen=True)
class IndicatorCross:
    """지표가 기준 아래로 «새로 들어간 날»(거짓 → 참)마다 그 «다음 거래일» 종가에 한 몫씩

    **조건이 이어지는 날에는 다시 사지 않는다** — 그러면 과매도 구간 첫 며칠에 몫을 다 써서
    사실상 한 날에 몰아 사는 것이 된다.

    Attributes:
        column: 지표 표의 컬럼 (`COL_RSI` 등)
        threshold: 기준값. 지표가 이 값 «미만»이면 조건이 참이다
        tranches: 첫 몫을 포함한 몫 수
    """

    column: str
    threshold: float
    tranches: int

    def __post_init__(self) -> None:
        """몫 수를 검사한다.

        Raises:
            ValueError: 몫이 둘 미만인 경우
        """
        if self.tranches < 2:
            raise ValueError(f"지표 분할은 몫이 둘 이상이어야 합니다 (하나면 일시매수다): {self.tranches}")


SplitTrigger = LumpSum | MonthEnds | PriceLadder | IndicatorCross


@dataclass(frozen=True)
class SplitMethod:
    """분할 방식 하나

    Attributes:
        label: 산출물의 `분할 방식` 값. **산출물의 구분자라 겹치면 행이 섞인다**
        trigger: 추가 몫을 언제 사는가
        fallbacks: 이 방식이 내는 미체결 처리 목록
    """

    label: str
    trigger: SplitTrigger
    fallbacks: tuple[str, ...]

    def __post_init__(self) -> None:
        """미체결 처리가 방식과 맞는지 검사한다.

        Raises:
            ValueError: 미체결이 생길 수 없는 방식에 처리를 붙였거나, 생길 수 있는 방식에
                「해당 없음」을 붙인 경우 — 앞은 같은 칸이 두 번 나오고, 뒤는 미체결이 조용히 사라진다
        """
        conditional = isinstance(self.trigger, PriceLadder | IndicatorCross)
        if not conditional and self.fallbacks != (FALLBACK_NONE,):
            raise ValueError(f"{self.label}: 미체결이 생기지 않는 방식의 미체결 처리는 「{FALLBACK_NONE}」 하나입니다: {self.fallbacks}")
        allowed = {FALLBACK_BUY_AT_Q4_END, FALLBACK_KEEP_CASH}
        if conditional and (not self.fallbacks or not set(self.fallbacks) <= allowed):
            raise ValueError(f"{self.label}: 조건부 방식의 미체결 처리는 {sorted(allowed)} 안에서 골라야 합니다: {self.fallbacks}")

    @property
    def tranches(self) -> int:
        """첫 몫을 포함한 몫 수.

        Returns:
            몫 수
        """
        return self.trigger.tranches


# 조건부 방식의 몫 수와 사다리 간격 — 사용자 승인값 (2026-09-23)
SPLIT_TRANCHES: Final = 3
LADDER_STEPS: Final[tuple[float, ...]] = (0.05, 0.10)
_CONDITIONAL_FALLBACKS: Final = (FALLBACK_BUY_AT_Q4_END, FALLBACK_KEEP_CASH)

# **격자다 — 고르지 않는다** (`.claude/rules/trading.md` 「경계는 행위」). 대상마다 칸 전부를 낸다.
# **첫 칸이 일시매수**이며 나머지 칸의 「일시매수 대비 차이」가 그 행을 기준으로 삼는다.
# 이름은 파라미터에서 만든다 — 손으로 적으면 값을 바꿨을 때 이름이 거짓말을 한다
SPLIT_METHODS: Final[tuple[SplitMethod, ...]] = (
    SplitMethod(label="일시매수", trigger=LumpSum(), fallbacks=(FALLBACK_NONE,)),
    SplitMethod(
        label=f"A 시간 {len(ADDITION_MONTHS) + 1}등분",
        trigger=MonthEnds(months=ADDITION_MONTHS),
        fallbacks=(FALLBACK_NONE,),
    ),
    *(
        SplitMethod(
            label=f"B 사다리 {step * RATE_TO_PERCENT:g}%",
            trigger=PriceLadder(step_rate=step, tranches=SPLIT_TRANCHES),
            fallbacks=_CONDITIONAL_FALLBACKS,
        )
        for step in LADDER_STEPS
    ),
    SplitMethod(
        label=f"C1 RSI({RSI_WINDOW}) {RSI_OVERSOLD:g} 아래",
        trigger=IndicatorCross(column=COL_RSI, threshold=RSI_OVERSOLD, tranches=SPLIT_TRANCHES),
        fallbacks=_CONDITIONAL_FALLBACKS,
    ),
    SplitMethod(
        label=f"C2 {SHORT_MA_WINDOW}일 이격도 {DISPARITY_OVERSOLD * RATE_TO_PERCENT:g}% 아래",
        trigger=IndicatorCross(column=COL_DISPARITY_SHORT, threshold=DISPARITY_OVERSOLD, tranches=SPLIT_TRANCHES),
        fallbacks=_CONDITIONAL_FALLBACKS,
    ),
)

# 원자료 표에 펼칠 몫의 최대 개수. **격자에서 유도한다** — 손으로 적으면 방식을 더할 때 컬럼이 모자란다
MAX_TRANCHES: Final = max(method.tranches for method in SPLIT_METHODS)


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


# 진입 위치 표. **창 길이를 이름에서 손으로 적지 않는다** — 창을 바꾸면 헤더가 따라와야 한다
DISPLAY_HIGH_DISTANCE: Final = "52주 최고 대비(%)"
DISPLAY_DISPARITY_LONG: Final = f"{LONG_MA_WINDOW}일 이격도(%)"
DISPLAY_DISPARITY_SHORT: Final = f"{SHORT_MA_WINDOW}일 이격도(%)"
DISPLAY_RSI: Final = f"RSI({RSI_WINDOW})"
DISPLAY_FIRST_QUARTER_RETURN: Final = f"{QUARTER_LABELS[0]} 수익률(%)"

# 분할매수 표의 축
DISPLAY_SPLIT_METHOD: Final = "분할 방식"
DISPLAY_FALLBACK: Final = "미체결 처리"

# 분할매수 원자료 — 진입 한 건의 값. **수익률과 보유 중 최악의 분모는 배정액이다**
DISPLAY_INVESTED: Final = "투자 비율(%)"
DISPLAY_AVERAGE_COST: Final = "첫 몫 대비 평균 매수가(%)"

# 분할매수 집계
DISPLAY_LUMP_DIFF: Final = "일시매수 대비 평균 차이(%p)"
DISPLAY_HOLD_WORST_MEAN: Final = "보유 중 최악 평균(%)"
DISPLAY_HOLD_WORST_MEDIAN: Final = "보유 중 최악 중앙값(%)"
DISPLAY_MEAN_INVESTED: Final = "평균 투자 비율(%)"
DISPLAY_MEAN_AVERAGE_COST: Final = "첫 몫 대비 평균 매수가 평균(%)"
# **몫 수가 아니라 «진입» 수이고, «규칙»으로 산 것만 센다** — 추가 몫이 하나라도 규칙 자체로
# 체결된 진입(해)이다. 「체결 건수」로 두면 A 방식의 8 이 「몫 8개」로 읽히고(실제로는 24몫),
# 「규칙으로」를 빼면 12월 말 일괄로 산 진입까지 세는 것으로 읽힌다
DISPLAY_RULE_FILLED: Final = "추가 몫이 규칙으로 체결된 진입 수"

# 원자료의 몫별 컬럼 이름에 붙는 말
TRANCHE_FIELD_DATE: Final = "체결일"
TRANCHE_FIELD_PRICE: Final = "체결가"
TRANCHE_FIELD_REASON: Final = "체결 사유"


def tranche_label(order: int, field: str) -> str:
    """분할매수 원자료의 몫별 컬럼 머리를 만든다.

    Args:
        order: 몫 순번 (2 이상 — 첫 몫은 `진입일`·`진입가` 가 담는다)
        field: `TRANCHE_FIELD_*` 중 하나

    Returns:
        `2번째 몫 체결일` 형태의 헤더
    """
    return f"{order}번째 몫 {field}"


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

# **분할매수와 진입 위치도 이 매매법의 것이다.** 원자료(`분할매수내역`)와 집계(`분할매수`)를
# 나누는 것은 분기 표와 같은 관용이다
ENTRY_CONTEXT_FILENAME: Final = "진입위치.csv"
SPLIT_TRADES_FILENAME: Final = "분할매수내역.csv"
SPLIT_SUMMARY_FILENAME: Final = "분할매수.csv"


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
