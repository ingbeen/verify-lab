"""검증 #10(월 하순 진입) 이벤트 정의와 실행이 공유하는 상수

파라미터 값은 `docs/매매/월말_진입/설계.md` 가 확정한 것이며, **성과를 보며 돌리는 노브가 아니다.**
**확정 칸과 확정 손절선은 `규칙.md` §3 의 결론을 옮겨 적은 것**이고, 손절선 격자는
재선정 수단으로 남아 있다 (`--stop-grid`).

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
    COL_DIVIDEND_HIT_COUNT,
    COL_DIVIDEND_MEAN_IMPACT,
    COL_DIVIDEND_MEASURED,
    COL_EXCLUDED_COUNT,
    COL_EXCLUDED_REASON,
    COL_FORWARD_RETURN,
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
    DISPLAY_EXCLUDED,
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
TRACK_NAME: Final = "month_end"


# ============================================================
# 검증 대상 (`docs/매매/월말_진입/설계.md` §3.4)
# ============================================================

# 집행 역할 — **이 상품으로 어느 방향을 거는가.** 방향을 고르는 값이 아니라 상품의 성질이다
# (측정의 원칙 11 은 그대로 지킨다 — 산출물은 언제나 두 방향을 나란히 낸다).
#
# 「아래」를 1배 ETF 의 하락률로 재면 분배락 하락이 이익으로 잡히는데 **인버스는 그만큼 오르지
# 않는다** (코스닥 4월 실측 +0.65%p). 인버스 종가에는 분배락·총보수·일일 리밸런싱 손실이
# 이미 들어 있어 따로 뺄 것이 없다. 근거는 `docs/매매/월말_진입/설계.md` §7.9 다
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
        market: 어느 시장인가. **조회표가 아니라 대상 자신이 갖는다** — 종목명으로 찾는
            사전으로 두면 호출자가 넘긴 대상이 거기 없어 `시장` 이 **조용히 빈칸**이 된다.
            바로 옆의 `execution_role` 과 같은 자리에 두면 그 구멍이 구조적으로 생기지 않는다
        directory: 파일이 있는 폴더
        file_template: 파일명 템플릿
        price_column: 가격 컬럼 이름
        price_decimals: 가격 출력 자릿수. 원시 데이터를 저장한 값과 같아야 한다
        is_index: 지수면 True. **살 수 없다는 사실을 산출물에 남기기 위한 값**이다
        execution_role: 이 상품으로 거는 방향. 지수는 `EXECUTION_ROLE_NONE` 이다
    """

    ticker: str
    label: str
    market: str
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

    @property
    def is_judged(self) -> bool:
        """이 대상으로 1차 판정을 하는가.

        **판정은 「살 수 있는 1배 롱」에만 건다** (2026-09-15 개편). 나머지 둘은 성적이 그대로
        나오되 `1차 판정` 이 「판정 안 함」이 되며, 빼는 것이 아니라 **참고용으로 남긴다.**

        | 빠지는 대상 | 왜 |
        | --- | --- |
        | 지수 | 살 수 없다. 그 결과로 「우위가 있다」를 주장하면 **집행할 수 없는 성적이 근거**가 된다 (측정의 원칙 9) |
        | 인버스 실물 | 1배 롱이 **같은 질문에 이미 답한다.** 둘 다 판정하면 같은 달이 두 번 판정되고 **방향이 반대로 나온다** — 실측으로 8월이 롱 「아래」·인버스 「위」였고 둘 다 제외였다 |

        **인버스 행을 지우지 않는 이유**는 그 성적이 일일 리밸런싱과 총보수가 든 실제 값이라
        분배락 교차검증의 재료이기 때문이다 (`.claude/rules/trading.md`).

        **조회표가 아니라 대상 자신이 답한다** (`src/verify_lab/CLAUDE.md` 출력 계약) —
        종목명으로 찾는 사전으로 두면 호출자가 넘긴 대상이 거기 없을 때 조용히 빈 답이 나온다.

        Returns:
            판정 대상이면 True
        """
        return self.execution_role == EXECUTION_ROLE_UP


# 시장마다 **1배 ETF 가 본검증이고, 인버스와 지수는 보조**다.
#
# - **지수**는 살 수 없으므로(측정의 원칙 9) 게이트 판정을 받지 않는다. 그래도 기본 대상에
#   남는 것은 **ETF 로는 볼 수 없는 기간이 거기 있기 때문**이다 (코스피 종합 46년 · 코스닥 종합 30년)
# - **인버스**는 기본 대상에서 뺐다 (2026-09-12). 「아래」 방향을 1배의 부호를 뒤집어 재는 것과
#   실물로 재는 것의 차이가 6월 1.94 대 1.95 · 9월 2.97 대 3.05 · 12월 2.99 대 3.01 로 잡음이고,
#   실제 집행은 2배 인버스라 1배 실물도 집행 상품이 아니다. **정의는 남긴다** —
#   어긋나는 칸이 곧 분배락이 걸린 칸이라(4월 +18.63% 대 +10.44%) 확정 전 교차검증에 쓴다
#
# **두 시장을 나눠 둔 것은 시장 하나만 돌려 보기 위해서다.**
DATASETS_KOSPI: Final = (
    Dataset(
        ticker="069500",
        label="KODEX 200",
        market=MARKET_KOSPI,
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
        market=MARKET_KOSPI,
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
        market=MARKET_KOSPI,
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
        market=MARKET_KOSPI,
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
        market=MARKET_KOSDAQ,
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
        market=MARKET_KOSDAQ,
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
        market=MARKET_KOSDAQ,
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
        market=MARKET_KOSDAQ,
        directory=SERIES_DIR,
        file_template=INDEX_FILE_TEMPLATE,
        price_column=COL_VALUE,
        price_decimals=PRICE_DECIMALS,
        is_index=True,
        execution_role=EXECUTION_ROLE_NONE,
    ),
)

# **정의된 대상 전부이자 «측정» 계층의 기본값.** 인버스가 여기 드는 이유는 **「아래」를
# 인버스 실물로도 재기 위해서**다 — 1배 ETF 의 하락률로 재면 분배락 하락이 이익으로 잡히는데
# 인버스는 그만큼 오르지 않는다(4월 +18.63% 대 +10.44%). 그 값은 `측정.csv` 의 인버스 행이
# 갖는다. `--ticker` 로 지목할 수 있는 것도 이 목록이다
DATASETS: Final = DATASETS_KOSPI + DATASETS_KOSDAQ

# **«매매» 계층의 기본값 — 인버스를 뺀 여섯.** 성적표는 사용자가 판단하는 표인데 인버스는
# 1배의 부호를 뒤집은 값과 차이가 잡음이라(6월 0.01 · 9월 0.08 · 12월 0.02%p) 같은 베팅이
# 두 줄로 실린다. 실제 집행도 2배 인버스라 1배 실물은 집행 상품이 아니다.
# **`--ticker` 로 지목하면 매매에서도 돈다** — 확정 전 분배락 교차검증이 그 용도다
# (`docs/매매/월말_진입/설계.md` §7.16)
DATASETS_TRADING: Final = tuple(dataset for dataset in DATASETS if dataset.execution_role != EXECUTION_ROLE_DOWN)


# ============================================================
# 격자 축 (`docs/매매/월말_진입/설계.md` §3.3 결정 ③)
# ============================================================

# 확정 칸의 진입 달력일과 청산 상대 거래일. **격자 축이 아니라 값 하나씩이다** —
# 「20일이 특별한가」는 `docs/매매/월말_진입/결과.md` §6 이 이미 답했고(**아니다**),
# 그래서 2026-09-21 에 격자 축을 걷어냈다 (설계 결정 ⑮). **되살리려면 그 결정을 먼저 읽는다**
BASE_ENTRY_DAY: Final = 20
BASE_EXIT_OFFSET: Final = 0


# ============================================================
# 확정 칸과 확정 손절선 (2026-09-21 사용자 확정)
# ============================================================


@dataclass(frozen=True)
class MonthEndCell:
    """월말 매매의 대상 칸 하나

    **대상을 가리지 않는다.** 옵션 만기일의 칸은 종목까지 지목하지만 여기서는 같은 달·같은
    방향을 모든 대상에 건다 — 시장이 이 매매법의 축이지 다른 질문이 아니기 때문이다
    (`docs/매매/월말_진입/설계.md` 결정 ⑪).

    Attributes:
        month: 진입 달 (1~12)
        bet_down: 아래로 거는 칸인지 여부. 참이면 원지수가 내려야 이익이다
    """

    month: int
    bet_down: bool


# **실제로 거는 한 칸이다** (2026-09-21 사용자 확정).
#
# [중요] **전에는 코드가 12개월 × 두 방향을 전부 냈고, 그 방침을 사용자가 뒤집었다.**
# 전부 내던 이유는 「눈에 띄는 달만 돌리면 그 선택이 결과에 실린다」였는데, 사용자가
# **실제로 걸 것만 남기기로 정했다** — 안 거는 23칸의 성적이 판단을 돕지 않았다.
#
# **그 대신 두 가지를 지킨다.**
#   - **왜 이 칸인가는 `docs/매매/월말_진입/규칙.md` §3 이 「확정 / 탈락안 / 근거」로 갖는다.**
#     코드는 그 결론을 옮겨 적을 뿐이고, 목록만 보고 근거를 짐작하면 안 된다
#   - **재수집하면 이 목록을 다시 판단한다** — 시세가 늘면 성적이 바뀌는데 이 목록은
#     따라오지 않는다. 그것이 격자를 내던 이유였고 지금도 사실이다
TRADING_CELLS: Final = (MonthEndCell(month=9, bet_down=True),)

# 확정 손절선 (비율, 0.05 = 5%). **기초자산 기준이다** — 2배 상품으로 집행하면 그 상품
# 가격으로는 −10% 이며, 그 환산은 `docs/매매/월말_진입/규칙.md` §1 이 갖는다.
# 성적표의 1배 롱·지수는 이 값을 그대로 쓴다
MONTH_END_STOP_LEVEL: Final = 0.05

# **확정 규칙이 아니라 대조축이다.** 손절선을 다시 고를 때 쓰는 격자이고 **기본 실행은
# 이것을 내지 않는다** — `scripts/run_month_end.py --stop-grid` 로 켠다.
# [중요] **그래서 이 상수를 지우지 않는다.** 지우면 재선정하는 길이 함께 사라지고, 그것이
# 확정 손절선 하나만 내는 것을 허용한 세 조건 중 하나다 (`.claude/rules/trading.md`).
#
# **하한이 −3% 인 이유**: 검증 #7 의 손절 격자에서 **−1.0% 가 4칸의 적중률을 60% 아래로
# 무너뜨렸다.** 그보다 좁은 구간은 이미 쓸모없다고 확인됐다.
# **간격이 1%p 인 이유**: 이 매매는 칸당 표본이 10~23건이라 0.5%p 해상도를 표본이 지탱하지
# 못한다. 값 하나를 옮겼을 때 크게 흔들리면 그것은 「좋은 값을 찾았다」가 아니라
# 「표본이 그 지점을 특정할 만큼 크지 않다」는 신호다 (`.claude/rules/trading.md`)
MONTH_END_STOP_LEVELS: Final = (0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10)

# 실행이 도는 두 목록이다. **CLI 도 trading 도 이것을 조립하지 않고 이름으로 고른다** —
# 두 곳에서 만들면 갈리고, 갈려도 예외가 나지 않는다
MONTH_END_STOP_DEFAULT: Final[tuple[float | None, ...]] = (MONTH_END_STOP_LEVEL,)
# 재선정할 때 도는 격자 — 위 격자에 **무손절 대조축**(`None`)을 더한 것
MONTH_END_STOP_GRID: Final[tuple[float | None, ...]] = (None, *MONTH_END_STOP_LEVELS)

# 이번 실행이 어느 칸을 잰 것인가. **측정과 체결이 같은 목록을 받으므로 키도 하나다** —
# 두 파일에 한 벌씩 두면 `summary.json` 의 `measure` 와 `trade` 가 다른 이름으로 같은 것을 적는다
KEY_CELLS: Final = "cells"
KEY_CELL_MONTH: Final = "month"
KEY_CELL_DIRECTION: Final = "direction"

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

# 월별 분해의 축 (1~12)
COL_MONTH_NUMBER: Final = "month_number"

# 기준선 집계를 신호 집계와 나란히 놓을 때 붙이는 접미사
BASELINE_SUFFIX: Final = "_baseline"


# ============================================================
# 시기 구분 (측정의 원칙 17)
# ============================================================

# 균등 2분할의 이름은 **공통 계층이 소유한다** (`measure/constants.py` 의
# `PERIOD_FIRST_HALF`·`PERIOD_SECOND_HALF`). 원칙 17 이 모든 매매법에 요구하는 축이라
# 검증마다 두면 같은 축이 다른 말로 불린다

# **시기 구간은 판정에 쓰이지 않는다** (2026-09-12 개편). 게이트는 전체 구간 하나만 보고,
# 앞/뒤 절반과 최근 N년은 **관찰용**으로 `성적표.csv` 의 시기 5행에만 남는다 —
# 쪼개면 칸당 표본이 5~6건까지 줄어 한 건이 20%p 를 움직이므로, 그 값으로 칸을 떨어뜨리면
# 멀쩡한 매매법이 우연으로 죽는다. 과대평가 여부는 사용자가 표본 수를 보고 판단한다

DISPLAY_MONTH: Final = "진입 달"
DISPLAY_MONTH_LAST_DATE: Final = "그 달 마지막 거래일"
DISPLAY_EXIT_DATE: Final = "청산일"
DISPLAY_HOLD_DAYS: Final = "보유 거래일"
DISPLAY_ENTRY_CLOSE: Final = "진입 종가"
DISPLAY_EXIT_CLOSE: Final = "청산 종가"
# **성적표와 같은 말을 쓴다** (`execution/constants.py` 의 같은 값). `측정.csv` 의 칸 한 행과
# 성적표의 `시기 = 전체` 행이 1:1 로 조인되어야 하는데, 한쪽이 `대상` 이고 다른 쪽이 `종목` 이면
# 두 표를 나란히 읽을 수 없다. **겹침은 테스트의 허용목록이 고정한다** — 이 저장소는 이 레이블을
# 이미 네 파일이 나눠 갖고 있고, 소유자를 하나로 모으는 것은 이 계획서의 범위가 아니다
DISPLAY_TICKER: Final = "종목"
DISPLAY_MONTH_NUMBER: Final = "월"

# `report/constants.py` 에 없어 이 검증이 정한다 — 원자료 표에만 쓰인다
DISPLAY_RETURN: Final = "수익률(%)"
DISPLAY_EXCLUDED_REASON: Final = "제외 사유"

# 기준선 값 컬럼 앞에 붙이는 말
BASELINE_PREFIX: Final = "기준선 "

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
    COL_MONTH_NUMBER: DISPLAY_MONTH_NUMBER,
    COL_DIRECTION: DISPLAY_DIRECTION,
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

# 확률로 들어와 자릿수만 맞출 컬럼
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
# runner 가 `row_counts` 를 이것으로 키잉하고 CLI 가 이것을 돌며 저장한다 —
# 왜 CLI 가 이름을 갖지 않는지는 `src/verify_lab/CLAUDE.md` 실행 요약 계약이 SoT 다.
# **측정 한 장뿐이다** (2026-09-21). 확정 칸이 하나가 되면서 격자 축(11 × 7칸)·월별 12칸·
# 시기 분해·집행 축이 전부 1칸짜리가 됐고, 그 다섯 표를 `측정.csv` 로 합쳤다.
# 체결 둘(`성적표.csv`·`거래내역.csv`)과 합쳐 폴더에 CSV 가 **셋**이다.
#
# **이름은 `report/constants.py` 가 소유하고 옵션 만기일과 같은 상수를 쓴다** —
# 매매법마다 다른 말을 쓰면 두 산출물을 나란히 읽을 수 없다
OUTPUT_FILES: Final[dict[str, str]] = {"measure": MEASURE_FILENAME}


# ============================================================
# 실행 요약 키
# ============================================================
#
# **측정과 매매가 같은 것을 센다.** 두 파일에 한 벌씩 두면 한쪽만 고쳐도 예외가 나지 않고
# `summary.json` 의 키만 조용히 갈린다 (`src/verify_lab/CLAUDE.md` 상수 관리)

# 진입 건수. 대상마다 남긴다
KEY_ENTRY_COUNT: Final = "entry_count"

# 청산일을 확정하지 못해 빠진 진입 수. **표본 보존이라 반드시 요약에 남는다**
KEY_EXCLUDED_COUNT: Final = "excluded_count"
