"""반감기_사이클 측정 조립 — 1단계 반감기 경과 격자 48칸과 2단계 지표 신호를 기준선과 함께 낸다

**계산하지 않는다.** 달력은 `halving_calendar`, 종가 대체는 `price_series`, 지표 산식은 `indicators`,
신호의 시점 규칙은 `indicator_signals`, 통계는 `measure/statistics`, 두 소스 대조는 `data/crosscheck` 가
소유하고 여기서는 조립만 한다.

**2단계는 측정만 낸다** (설계 결정 ㉘ ②) — 지표 신호는 체결하지 않고 성적표에 오르지 않는다. 신호의 칸은
(신호 × 보유)이고 1단계와 **같은 기준선 · 같은 칸 집계**를 쓴다.

**칸은 (진입 개월 × 보유 개월)이다.** 진입 개월마다 돌며 보유 개월을 구간 축에 둬서
`summarize` · `excess` · `permutation_test` 를 그대로 쓴다 — 통계량 정의를 여기서 다시 구현하면 두 곳이
조용히 갈라진다(절대 원칙 5).

**기준선은 「첫 반감기부터 매일 진입 × 같은 보유」다.** 청산 규칙이 신호와 같아 보유 길이가 어긋나지 않는다.
**판정에 쓰지 않는다** (루트 `CLAUDE.md` 「기준선을 넘지 못하는 것은 탈락 사유가 아닙니다」).

**값은 1배 롱 기준 그대로다.** `방향` 은 식별 라벨이고 부호를 뒤집지 않는다 — 뒤집으면 `기준선 오른 비율` 이
실제로는 내린 비율을 가리켜 이름이 거짓이 된다.

**3단계 혼합 분할(달력 + MVRV)도 측정 표로만 낸다** (결정 ㊼) — 회차 체결과 포지션 성적은 `split_rule` 이 소유하고,
1차 판정 · 손절 · 기준선이 없다. 체결 성적표(`trading.py`)와 다른 파일이다.

**3단계 체결 격자 중 같은 사이클에 파는 칸의 기준선도 측정 표로 낸다** (결정 ㊶) — 칸 값은 체결과 같은 일정을
측정 쪽에서 종가로 잰 것이고, 기준선은 1단계와 같은 모집단에 보유(청산 − 진입)를 준 것이다. 판정에 쓰지 않는다.

**3단계 달력 매달 분할도 측정 표로 낸다** (결정 51 · 52) — 회차와 포지션 성적은 혼합 분할과 같은 `split_rule` 함수가 낸다.
1차 판정 · 손절 · 하드포크 몫 · 기준선이 없다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_DATE, COL_VALUE, PRICE_DECIMALS
from verify_lab.data.coinmetrics_collector import PUBLICATION_LAG_DAYS
from verify_lab.data.crosscheck import (
    COL_DIFF_RATE,
    COL_PRIMARY,
    COL_SECONDARY,
    CrosscheckResult,
    crosscheck_closes,
)
from verify_lab.data.crypto_common import load_crypto_market_csv
from verify_lab.data.loader import load_series_csv
from verify_lab.execution.run_summary import KEY_DATASETS, KEY_ROW_COUNTS
from verify_lab.execution.trade_fill import resolve_positions
from verify_lab.measure.constants import (
    COL_ENTRY_CLOSE,
    COL_EXCLUDED_COUNT,
    COL_EXCLUDED_REASON,
    COL_EXIT_CLOSE,
    COL_EXIT_DATE,
    COL_FORWARD_RETURN,
    COL_HOLD_DAYS,
    COL_HORIZON,
    COL_JUDGEABLE,
    COL_MEAN_RATE_CONFLICT,
    COL_SIGNAL_COUNT,
    REASON_NONE,
)
from verify_lab.measure.screening import COL_DIRECTION, DIRECTION_DOWN, DIRECTION_UP
from verify_lab.measure.statistics import (
    COL_BASIS,
    COL_DOWN_RATE_P_VALUE,
    COL_LOSS_RATE,
    COL_LOSS_RATE_EXCESS,
    COL_MEAN,
    COL_MEAN_EXCESS,
    COL_MEAN_P_VALUE,
    COL_MEDIAN,
    COL_MEDIAN_EXCESS,
    COL_MEDIAN_P_VALUE,
    COL_NEGATIVE_COUNT,
    COL_POSITIVE_COUNT,
    COL_SAMPLE_COUNT,
    COL_SIGNAL_SAMPLE_COUNT,
    COL_TEST_NOTE,
    COL_UP_RATE_P_VALUE,
    COL_WIN_RATE,
    COL_WIN_RATE_EXCESS,
    DEFAULT_RANDOM_SEED,
    DEFAULT_REPEAT_COUNT,
    NOTE_TOO_FEW_SAMPLES,
    SUMMARY_COLUMNS,
    TEST_COLUMNS,
    excess,
    judgeable,
    max_non_overlapping,
    mean_rate_conflict,
    permutation_test,
    summarize,
    yes_no,
)
from verify_lab.report.run_summary import KEY_TRACK, dataset_record, format_period
from verify_lab.report.tables import to_display_columns
from verify_lab.studies.halving_cycle.constants import (
    BASELINE_SUFFIX,
    BET_DOWN,
    CALENDAR_SPLIT_STEP_MONTHS,
    CALENDAR_SPLITS,
    COL_AVG_BUY_PRICE,
    COL_AVG_SELL_PRICE,
    COL_BASELINE_NON_OVERLAPPING,
    COL_CYCLE_COUNT,
    COL_CYCLE_RETURN_TEMPLATE,
    COL_CYCLE_WORST_TEMPLATE,
    COL_DISPARITY,
    COL_ENTRY_DATE,
    COL_ENTRY_MONTHS,
    COL_EXIT_MONTHS,
    COL_HALVING,
    COL_HOLD_MONTHS,
    COL_HOLD_RETURNS,
    COL_INDICATOR_SIGNAL,
    COL_INDICATOR_VALUE,
    COL_JUDGMENT_DATE,
    COL_MACD_HISTOGRAM,
    COL_MARKET_CAP,
    COL_MONTHLY_RSI,
    COL_MONTHS_SINCE_HALVING,
    COL_MVRV,
    COL_MVRV_Z,
    COL_NON_OVERLAPPING,
    COL_PI_CYCLE,
    COL_PREVIOUS_VALUE,
    COL_SIGNAL_MEANING,
    COL_SPLIT_FILL_CLOSE,
    COL_TICKER,
    COL_ZERO_VOLUME,
    COLUMN_LABELS,
    CYCLE_RETURN_LABEL_TEMPLATE,
    CYCLE_WORST_LABEL_TEMPLATE,
    DATASETS,
    DISPARITY_WINDOW,
    ENTRY_MONTHS,
    EXIT_MONTHS,
    FIELD_CALENDAR_SPLIT_FILLS,
    FIELD_CALENDAR_SPLIT_POSITIONS,
    FIELD_CALENDAR_YEARS,
    FIELD_CROSSCHECK,
    FIELD_ENTRIES,
    FIELD_ENTRY_INDICATORS,
    FIELD_EXCESS,
    FIELD_GRID_BASELINE,
    FIELD_INDICATOR_CYCLES,
    FIELD_INDICATOR_SIGNALS,
    FIELD_INDICATOR_STATISTICS,
    FIELD_REPLACED,
    FIELD_SPLIT_COMBINATIONS,
    FIELD_SPLIT_FILLS,
    FIELD_SPLIT_POSITIONS,
    FIELD_STATISTICS,
    FIELD_TEST,
    GRID_BASELINE_HOLD_MONTHS,
    HALVINGS,
    HOLD_MONTHS,
    INDICATOR_DECIMALS,
    INDICATOR_SIGNALS,
    INDICATOR_VALUE_COLUMNS,
    KEY_BLOCK_TIME,
    KEY_DATE,
    KEY_ENTRY_MONTHS,
    KEY_EXCLUDED_COUNT,
    KEY_HALVINGS,
    KEY_HEIGHT,
    KEY_HOLD_MONTHS,
    KEY_NAME,
    KEY_SIGNAL_COUNT,
    MACD_FAST_SPAN,
    MACD_SIGNAL_SPAN,
    MACD_SLOW_SPAN,
    MVRV_Z_MIN_DAYS,
    OUTPUT_FILES,
    PERCENT_COLUMNS,
    PI_CYCLE_LONG_MULTIPLIER,
    PI_CYCLE_LONG_WINDOW,
    PI_CYCLE_SHORT_WINDOW,
    PROBABILITY_COLUMNS,
    RSI_DECIMALS,
    RSI_WINDOW,
    SPLIT_BUY_BOOK_LEVELS,
    SPLIT_BUY_LAST_DEADLINES,
    SPLIT_BUY_RANK_LEVELS,
    SPLIT_BUY_START_MONTHS_HALVING,
    SPLIT_BUY_START_MONTHS_HIGH,
    SPLIT_DEADLINE_STEP_MONTHS,
    SPLIT_RANK_MIN_DAYS,
    SPLIT_RANK_YEARS,
    SPLIT_SELL_BOOK_LEVELS,
    SPLIT_SELL_LAST_DEADLINES,
    SPLIT_SELL_RANK_LEVELS,
    SPLIT_SELL_START_MONTHS,
    SPLIT_SIDE_BUY,
    SPLIT_SIDE_SELL,
    SPLIT_TRANCHES,
    TRACK_NAME,
    CalendarSplit,
    Dataset,
    IndicatorSignal,
)
from verify_lab.studies.halving_cycle.halving_calendar import (
    baseline_entries,
    calendar_returns,
    calendar_year_returns,
    exit_schedule,
    halving_entries,
    position_schedule,
)
from verify_lab.studies.halving_cycle.indicator_signals import entry_indicator_values, indicator_signal_returns
from verify_lab.studies.halving_cycle.indicators import daily_indicator_frame, monthly_indicator_frame
from verify_lab.studies.halving_cycle.price_series import replace_zero_volume_closes
from verify_lab.studies.halving_cycle.split_rule import (
    CalendarSplitGrid,
    SplitGrid,
    calendar_split_grid,
    split_grid,
    split_legs,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# `summary.json` 의 측정 칸 — 무엇을 어떤 규칙으로 쟀나
KEY_PERMUTATION_REPEATS = "permutation_repeats"
KEY_PERMUTATION_SEED = "permutation_seed"
KEY_BASELINE_START = "baseline_start"
KEY_REFERENCE = "reference"
KEY_FILE = "file"
KEY_PERIOD = "period"
KEY_ROWS = "rows"
KEY_REPLACED_COUNT = "replaced_count"
KEY_CROSSCHECK = "crosscheck"
KEY_TOLERANCE = "tolerance"
KEY_OVERLAP_DAYS = "overlap_days"
KEY_OVER_TOLERANCE_DAYS = "over_tolerance_days"
KEY_PRIMARY_ONLY_DAYS = "primary_only_days"
KEY_SECONDARY_ONLY_DAYS = "secondary_only_days"
KEY_ZERO_VOLUME_DAYS = "zero_volume_days"

# `summary.json` 의 측정 칸 — 2단계 지표의 규칙과 대상별 온체인 계열 · 신호 건수
KEY_INDICATOR_RULE = "indicators"
KEY_PI_CYCLE_WINDOWS = "pi_cycle_windows"
KEY_PI_CYCLE_MULTIPLIER = "pi_cycle_multiplier"
KEY_DISPARITY_WINDOW = "disparity_window"
KEY_RSI_WINDOW = "monthly_rsi_window"
KEY_MACD_SPANS = "monthly_log_macd_spans"
KEY_MVRV_Z_MIN_DAYS = "mvrv_z_min_days"
KEY_SIGNALS = "signals"
KEY_INDICATOR = "indicator"
KEY_THRESHOLD = "threshold"
KEY_UPWARD = "upward"
KEY_ONCHAIN = "onchain"
KEY_MVRV = "mvrv"
KEY_MARKET_CAP = "market_cap"
KEY_DROPPED_TAIL_DAYS = "dropped_tail_days"
KEY_MISSING_PRICE_DAYS = "missing_price_days"
KEY_INDICATOR_SIGNALS = "indicator_signals"

# `summary.json` 의 측정 칸 — 3단계 혼합 분할의 규칙과 대상별 건수 (결정 ㊺ ~ ㊼)
KEY_SPLIT_RULE = "split_rule"
KEY_SPLIT_TRANCHES = "tranches"
KEY_SPLIT_DEADLINE_STEP = "deadline_step_months"
KEY_SPLIT_BUY = "buy"
KEY_SPLIT_SELL = "sell"
KEY_SPLIT_START_HALVING = "start_months_after_halving"
KEY_SPLIT_START_HIGH = "start_months_after_new_high"
KEY_SPLIT_LAST_DEADLINES = "last_deadlines"
KEY_SPLIT_BOOK_LEVELS = "book_mvrv_levels"
KEY_SPLIT_RANK_LEVELS = "rank_levels"
KEY_SPLIT_COMBINATIONS = "combinations"
KEY_SPLIT_RANK_YEARS = "rank_years"
KEY_SPLIT_RANK_MIN_DAYS = "rank_min_days"
KEY_SPLIT_NOTES = "notes"
KEY_SPLIT = "split"
KEY_SPLIT_FILL_COUNT = "fill_rows"
KEY_SPLIT_UNFILLED = "unfilled_by_reason"
KEY_SPLIT_POSITION_COUNT = "position_rows"
KEY_SPLIT_UNFINISHED = "unfinished_by_reason"

# `summary.json` 의 측정 칸 — 3단계 같은 사이클 칸의 기준선 보유 (결정 ㊶ · ㊽)
KEY_GRID_BASELINE_HOLD_MONTHS = "grid_baseline_hold_months"

# `summary.json` 의 측정 칸 — 3단계 달력 매달 분할의 폭과 대상별 건수 (결정 52). 건수 칸은 혼합 분할과 같은 키를 쓴다
KEY_CALENDAR_SPLIT_RULE = "calendar_split_rule"
KEY_CALENDAR_SPLIT_STEP = "step_months"
KEY_CALENDAR_SPLIT_SPLITS = "splits"
KEY_CALENDAR_SPLIT_BUY_MONTHS = "buy_months_after_halving"
KEY_CALENDAR_SPLIT_SELL_MONTHS = "sell_months_after_next_halving"
KEY_CALENDAR_SPLIT = "calendar_split"

# 3단계 혼합 분할 표만 보고는 알 수 없는 조건 (결정 ㊺ · ㊼). **격자 값을 글자로 박지 않는다** — 값은 같은 칸의 목록이 말한다
NOTE_SPLIT_MEASURE_ONLY = "혼합 분할 표 셋은 측정 표다 — 1차 판정 · 손절 · 기준선이 없고 체결 성적표 · 거래내역과 다른 파일이다. 조합을 고르지 않는다"
NOTE_SPLIT_FORK = "혼합 분할 포지션에는 하드포크 몫이 없다 — 포크일에 코인을 들고 있던 포지션(2012 사이클)은 그만큼 과소평가된다. " "거래내역 끝 칸의 하드포크 몫은 체결 격자에만 있다"
NOTE_SPLIT_HINDSIGHT = (
    "혼합 분할의 달력 쪽 값(반감기 기준 매수 창 · 매수 기한 · 매도 기한)은 과거 고점 · 바닥 시점을 본 뒤 정했다 — "
    "달력만 조합이 유리하게 짜여 있다. 온체인 문턱(책 범위 · 4년 순위)은 결과를 보기 전의 값이다"
)
SPLIT_NOTES = (NOTE_SPLIT_MEASURE_ONLY, NOTE_SPLIT_FORK, NOTE_SPLIT_HINDSIGHT)

# 3단계 달력 매달 분할 표만 보고는 알 수 없는 조건 (결정 52). **폭의 값을 글자로 박지 않는다** — 값은 같은 칸의 목록이 말한다
NOTE_CALENDAR_SPLIT_MEASURE_ONLY = "달력 분할 표 둘은 측정 표다 — 1차 판정 · 손절 · 기준선이 없고 체결 성적표 · 거래내역과 다른 파일이다. 폭을 고르지 않는다"
NOTE_CALENDAR_SPLIT_FORK = "달력 분할 포지션에는 하드포크 몫이 없다 — 포크일에 코인을 들고 있던 포지션은 그만큼 과소평가된다"
NOTE_CALENDAR_SPLIT_HINDSIGHT = "폭의 가운데는 과거 바닥 · 고점 시점을 본 뒤 정했다 — 좁은 폭일수록 과거에 더 맞춰져 있다"
CALENDAR_SPLIT_NOTES = (NOTE_CALENDAR_SPLIT_MEASURE_ONLY, NOTE_CALENDAR_SPLIT_FORK, NOTE_CALENDAR_SPLIT_HINDSIGHT)

# 3단계 혼합 분할의 조합 — **격자 전부**다. 값의 출처와 「결과를 본 뒤 정한 값」 표시는 `constants.py` 의 그 절이 갖는다
_SPLIT_BUY_LEGS = split_legs(
    SPLIT_SIDE_BUY,
    halving_starts=SPLIT_BUY_START_MONTHS_HALVING,
    high_starts=SPLIT_BUY_START_MONTHS_HIGH,
    last_deadlines=SPLIT_BUY_LAST_DEADLINES,
    book_levels=SPLIT_BUY_BOOK_LEVELS,
    rank_levels=SPLIT_BUY_RANK_LEVELS,
)
# 매도 창은 다음 반감기 기준 하나다 — 신고가 기준을 두지 않는다
_SPLIT_SELL_LEGS = split_legs(
    SPLIT_SIDE_SELL,
    halving_starts=SPLIT_SELL_START_MONTHS,
    high_starts=(),
    last_deadlines=SPLIT_SELL_LAST_DEADLINES,
    book_levels=SPLIT_SELL_BOOK_LEVELS,
    rank_levels=SPLIT_SELL_RANK_LEVELS,
)

# 3단계 혼합 분할 표에서 가격으로 내는 컬럼 — 평균 단가는 계산값이라 저장 직전에 가격 자릿수로 자른다
_SPLIT_PRICE_COLUMNS = (COL_SPLIT_FILL_CLOSE, COL_AVG_BUY_PRICE, COL_AVG_SELL_PRICE)

# 조합 표의 사이클별 가로 칸 — 반감기 목록에서 이름을 만든다
_CYCLE_LABELS = {
    **{
        COL_CYCLE_RETURN_TEMPLATE.format(halving=halving.label): CYCLE_RETURN_LABEL_TEMPLATE.format(
            halving=halving.label
        )
        for halving in HALVINGS
    },
    **{
        COL_CYCLE_WORST_TEMPLATE.format(halving=halving.label): CYCLE_WORST_LABEL_TEMPLATE.format(halving=halving.label)
        for halving in HALVINGS
    },
}

# 진입내역의 컬럼 — 측정 long-form 에서 사용자가 대조할 값만 남긴다 (측정의 원칙 8). 종목은 조립 때 앞에 붙는다
_ENTRY_COLUMNS = [
    COL_HALVING,
    COL_ENTRY_MONTHS,
    COL_HOLD_MONTHS,
    COL_DATE,
    COL_ENTRY_CLOSE,
    COL_EXIT_DATE,
    COL_EXIT_CLOSE,
    COL_HOLD_DAYS,
    COL_FORWARD_RETURN,
    COL_EXCLUDED_REASON,
]

# 집계 값 — 기준과 구간 축을 뺀 `summarize` 결과 전부. 신호 쪽은 그대로, 기준선 쪽은 접미사를 붙여 싣는다
_SUMMARY_VALUES = [column for column in SUMMARY_COLUMNS if column not in (COL_BASIS, COL_HORIZON)]

# excess 표의 값 — 신호 표본 · 기준선 집계 · 기준선 비중첩 · 기준선 대비 차이. **기준선 표본은 한 번만 싣는다** —
# `excess` 가 내는 기준선 표본 수는 기준선 집계의 표본과 같은 값이라 두 열이 되면 어느 쪽이 맞는지 매번 견줘야 한다
_EXCESS_VALUES = [
    COL_SIGNAL_SAMPLE_COUNT,
    *(f"{column}{BASELINE_SUFFIX}" for column in _SUMMARY_VALUES),
    COL_BASELINE_NON_OVERLAPPING,
    COL_MEAN_EXCESS,
    COL_MEDIAN_EXCESS,
    COL_WIN_RATE_EXCESS,
    COL_LOSS_RATE_EXCESS,
]

# 무작위 뽑기 대조에서 표에 싣는 값. **관측값 · 백분위는 싣지 않는다** — 관측값은 `통계.csv` 의 평균 · 중앙값 ·
# 두 비율과 같은 값이고, 백분위는 검정한 칸에만 채워지는데 칸마다 표본이 하한에 못 미쳐 지금은 전부 빈다.
# 판단 재료는 우연확률 넷과 비고다
_TEST_VALUES = [
    COL_SAMPLE_COUNT,
    COL_MEAN_P_VALUE,
    COL_MEDIAN_P_VALUE,
    COL_UP_RATE_P_VALUE,
    COL_DOWN_RATE_P_VALUE,
    COL_TEST_NOTE,
]

# 2단계 신호일 목록의 컬럼 — long-form 에서 기준 · 구간 축을 뺀 것. 종목은 조립 때 앞에 붙는다
_INDICATOR_SIGNAL_COLUMNS = [
    COL_INDICATOR_SIGNAL,
    COL_HALVING,
    COL_MONTHS_SINCE_HALVING,
    COL_JUDGMENT_DATE,
    COL_PREVIOUS_VALUE,
    COL_INDICATOR_VALUE,
    COL_DATE,
    COL_ENTRY_CLOSE,
    COL_HOLD_MONTHS,
    COL_EXIT_DATE,
    COL_EXIT_CLOSE,
    COL_HOLD_DAYS,
    COL_FORWARD_RETURN,
    COL_EXCLUDED_REASON,
]

# 칸 집계 옆에 두는 기준선 값 — 2단계 지표통계와 3단계 격자기준선이 함께 쓴다. **판정이 없어 기준선을 옆에 둔다** —
# 기준선은 방향 비율을 읽는 데 필요한 것만 싣는다
_BASELINE_BESIDE_VALUES = [
    *(f"{column}{BASELINE_SUFFIX}" for column in (COL_SAMPLE_COUNT, COL_MEAN, COL_MEDIAN, COL_WIN_RATE, COL_LOSS_RATE)),
    COL_BASELINE_NON_OVERLAPPING,
]
_INDICATOR_STATISTICS_COLUMNS = [
    COL_INDICATOR_SIGNAL,
    COL_SIGNAL_MEANING,
    COL_HOLD_MONTHS,
    COL_SIGNAL_COUNT,
    COL_EXCLUDED_COUNT,
    COL_SAMPLE_COUNT,
    COL_CYCLE_COUNT,
    COL_NON_OVERLAPPING,
    *(column for column in _SUMMARY_VALUES if column not in (COL_SIGNAL_COUNT, COL_EXCLUDED_COUNT, COL_SAMPLE_COUNT)),
    COL_MEAN_RATE_CONFLICT,
    COL_JUDGEABLE,
    *_BASELINE_BESIDE_VALUES,
    COL_MEAN_EXCESS,
    COL_MEDIAN_EXCESS,
    COL_WIN_RATE_EXCESS,
    COL_LOSS_RATE_EXCESS,
    *(column for column in _TEST_VALUES if column != COL_SAMPLE_COUNT),
]

# 3단계 격자기준선의 컬럼 — 지표통계와 같은 구성에서 신호 이름 · 뜻 대신 (진입 · 청산 · 보유)를 둔다.
# **사이클 수는 싣지 않는다** — 칸마다 사이클당 한 번이라 표본과 늘 같다
_GRID_BASELINE_COLUMNS = [
    COL_ENTRY_MONTHS,
    COL_EXIT_MONTHS,
    COL_HOLD_MONTHS,
    COL_SIGNAL_COUNT,
    COL_EXCLUDED_COUNT,
    COL_SAMPLE_COUNT,
    COL_NON_OVERLAPPING,
    *(column for column in _SUMMARY_VALUES if column not in (COL_SIGNAL_COUNT, COL_EXCLUDED_COUNT, COL_SAMPLE_COUNT)),
    COL_MEAN_RATE_CONFLICT,
    COL_JUDGEABLE,
    *_BASELINE_BESIDE_VALUES,
    COL_MEAN_EXCESS,
    COL_MEDIAN_EXCESS,
    COL_WIN_RATE_EXCESS,
    COL_LOSS_RATE_EXCESS,
    *(column for column in _TEST_VALUES if column != COL_SAMPLE_COUNT),
]

# 2단계 사이클 분해의 값 — 한 사이클에 몰렸는지를 보는 데 필요한 것만 싣는다
_INDICATOR_CYCLE_VALUES = [
    COL_SIGNAL_COUNT,
    COL_EXCLUDED_COUNT,
    COL_SAMPLE_COUNT,
    COL_MEAN,
    COL_MEDIAN,
    COL_WIN_RATE,
    COL_LOSS_RATE,
]

# 1단계 진입일에 붙이는 지표 — 일간 넷 · 월간 둘 (결정 ㉖). NUPL 은 MVRV 에서 바로 나와 싣지 않는다
_ENTRY_DAILY_INDICATORS = [COL_MVRV, COL_MVRV_Z, COL_PI_CYCLE, COL_DISPARITY]
_ENTRY_MONTHLY_INDICATORS = [COL_MONTHLY_RSI, COL_MACD_HISTOGRAM]


@dataclass(frozen=True)
class LoadedDataset:
    """대상 하나를 읽은 결과 — **측정과 체결이 같은 것을 쓴다**

    Attributes:
        frame: 측정이 쓰는 시세. 거래량 0 인 날의 종가만 대조 계열 값이다
        reference: 대조 계열 (Coin Metrics 기준가)
        replaced: 종가를 바꾼 날 목록
        crosscheck: **바꾸기 전** 원시 종가로 잰 두 소스 대조
    """

    frame: pd.DataFrame
    reference: pd.DataFrame
    replaced: pd.DataFrame
    crosscheck: CrosscheckResult


@dataclass(frozen=True)
class StudyOutputs:
    """측정 산출물

    Attributes:
        statistics: (진입 × 보유) 칸마다 한 행 — 신호 집계 · 평균-비율 어긋남 · 판정가능 · 비중첩
        excess: 칸마다 한 행 — 기준선 집계 · 기준선 대비 차이 · 기준선 비중첩
        test: 칸마다 한 행 — 무작위 뽑기 대조
        entries: 진입 × 보유 long-form. **청산이 오지 않은 행도 사유와 함께 남는다**
        calendar_years: 달력 연도마다 한 행 (관찰용)
        crosscheck: 두 소스의 차이가 허용폭을 넘은 날 전체
        replaced: 거래량 0 이라 종가를 바꾼 날 전체
        indicator_signals: 2단계 신호 × 보유 long-form. **제외된 판정도 사유와 함께 남는다**
        indicator_statistics: 2단계 (신호 × 보유) 칸마다 한 행 — 신호 집계 · 사이클 수 · 기준선 · 차이 · 우연확률.
            **0건인 신호도 행이 있다**
        indicator_cycles: 2단계 (신호 × 보유 × 반감기)마다 한 행. **0건인 사이클도 행이 있다**
        entry_indicators: 1단계 진입마다 진입 전날까지의 지표 값과 보유별 수익률
        split_fills: 3단계 혼합 분할의 회차 — 쪽 × 조합 × 사이클 × 회차. **체결 전 회차도 행이 있다**
        split_positions: 3단계 혼합 분할의 포지션 — 매수 조합 × 매도 조합 × 사이클. **끝나지 않은 포지션도 행이 있다**
        split_combinations: 3단계 혼합 분할의 조합 — 사이클별 수익률을 가로로, 끝난 포지션의 집계를 함께
        grid_baseline: 3단계 격자 중 같은 사이클에 파는 (진입 × 청산) 칸마다 한 행 — 칸 집계 · 같은 보유의 기준선 ·
            차이 · 우연확률. **진입이 없던 칸도 행이 있다**
        calendar_split_fills: 3단계 달력 매달 분할의 회차 — 폭 × 사이클 × 쪽 × 회차. **체결 전 회차도 행이 있다**
        calendar_split_positions: 3단계 달력 매달 분할의 포지션 — 폭 × 사이클. **끝나지 않은 포지션도 행이 있다**
        summary: 실행 요약
    """

    statistics: pd.DataFrame
    excess: pd.DataFrame
    test: pd.DataFrame
    entries: pd.DataFrame
    calendar_years: pd.DataFrame
    crosscheck: pd.DataFrame
    replaced: pd.DataFrame
    indicator_signals: pd.DataFrame
    indicator_statistics: pd.DataFrame
    indicator_cycles: pd.DataFrame
    entry_indicators: pd.DataFrame
    split_fills: pd.DataFrame
    split_positions: pd.DataFrame
    split_combinations: pd.DataFrame
    grid_baseline: pd.DataFrame
    calendar_split_fills: pd.DataFrame
    calendar_split_positions: pd.DataFrame
    summary: dict[str, Any]


@dataclass(frozen=True)
class _Baseline:
    """기준선 — 1단계와 2단계가 함께 쓴다

    Attributes:
        returns: 매일 진입 × 보유 long-form (무작위 뽑기 대조의 모집단)
        summary: 보유마다 집계
        values: 보유 + 접미사를 붙인 집계 값
        overlap: 보유 + 기준선 비중첩 표본
    """

    returns: pd.DataFrame
    summary: pd.DataFrame
    values: pd.DataFrame
    overlap: pd.DataFrame


def load_dataset(dataset: Dataset) -> LoadedDataset:
    """대상의 시세와 대조 계열을 읽고, 대조한 뒤 거래량 0 인 날의 종가를 바꾼다.

    **측정과 체결이 이 함수를 함께 쓴다** — 두 벌을 두면 한쪽만 종가를 바꿔 같은 날에 다른 가격이 쓰인다.

    **대조는 바꾸기 «전»에 한다.** 바꾼 값끼리 견주면 거래가 없던 날의 괴리가 사라져 목록에서 빠진다.

    Args:
        dataset: 검증 대상

    Returns:
        읽은 결과
    """
    raw = load_crypto_market_csv(dataset.path)
    reference = load_series_csv(dataset.reference_path)
    crosscheck = crosscheck_closes(raw, reference)
    prices = replace_zero_volume_closes(raw, reference)

    return LoadedDataset(frame=prices.frame, reference=reference, replaced=prices.replaced, crosscheck=crosscheck)


@dataclass(frozen=True)
class LoadedOnchain:
    """온체인 두 계열을 읽은 결과

    Attributes:
        frame: 두 계열이 함께 있는 날의 날짜 · MVRV · 시가총액
        mvrv: 읽은 MVRV 계열 그대로 (요약에 그 파일의 기간을 적는다)
        market_cap: 읽은 시가총액 계열 그대로
        dropped_days: 한쪽에만 있어 뺀 끝 날의 수 (요약에 남긴다)
    """

    frame: pd.DataFrame
    mvrv: pd.DataFrame
    market_cap: pd.DataFrame
    dropped_days: int


def load_onchain(dataset: Dataset) -> LoadedOnchain:
    """MVRV 와 시가총액을 읽어 **두 계열이 함께 있는 날**만 한 표로 맞춘다.

    **측정만 쓴다** — 2단계 지표와 3단계 혼합 분할의 문턱 · 4년 순위가 이 표의 MVRV 를 쓴다. 체결은 읽지 않으므로
    `load_dataset` 에 넣지 않는다.

    두 계열은 따로 받고 각자 공개 지연을 허용받으므로(`data/coinmetrics_collector.PUBLICATION_LAG_DAYS`)
    **끝이 그만큼 어긋날 수 있다** — 그때는 한쪽에만 있는 끝 날을 빼고 경고하며 뺀 날 수를 돌려준다.
    **허용치를 넘는 끝 어긋남은 멈춘다** — 묵은 파일이 섞인 것이라, 빼고 지나가면 그 사이의 온체인 돌파가
    예외 없이 사라진다. 어긋남이 끝이 아닌 자리에 있으면 「같은 날의 값끼리」라는 전제가 무너진 것이라 멈춘다.

    Args:
        dataset: 검증 대상

    Returns:
        읽은 결과

    Raises:
        ValueError: 두 계열의 날짜가 끝이 아닌 자리에서 어긋나거나, 끝 어긋남이 공개 지연 허용치를 넘는 경우 —
            다른 날의 값끼리 나누거나 묵은 파일로 재면 예외 없이 틀린다
    """
    mvrv = load_series_csv(dataset.mvrv_path)
    market_cap = load_series_csv(dataset.market_cap_path)

    common = mvrv[COL_DATE][mvrv[COL_DATE].isin(market_cap[COL_DATE])].reset_index(drop=True)
    for path, series in ((dataset.mvrv_path, mvrv), (dataset.market_cap_path, market_cap)):
        if not series[COL_DATE].iloc[: len(common)].reset_index(drop=True).equals(common):
            raise ValueError(
                f"MVRV 와 시가총액의 날짜가 끝이 아닌 자리에서 어긋납니다 ({path.name}) — "
                "두 계열을 같은 수집에서 받았는지 확인하고 `scripts/data/collect_btc.py` 로 다시 받으세요"
            )
    tails = {
        path.name: len(series) - len(common)
        for path, series in ((dataset.mvrv_path, mvrv), (dataset.market_cap_path, market_cap))
    }
    if max(tails.values()) > PUBLICATION_LAG_DAYS:
        raise ValueError(
            f"MVRV 와 시가총액의 끝 날짜가 공개 지연 허용치({PUBLICATION_LAG_DAYS}일)보다 크게 어긋납니다 "
            f"(한쪽에만 있는 끝 날: {tails}) — 묵은 파일이 섞였을 수 있습니다. "
            "`scripts/data/collect_btc.py` 로 두 계열을 함께 다시 받으세요"
        )
    dropped = sum(tails.values())
    if dropped:
        logger.warning(f"MVRV 와 시가총액의 끝 날짜가 달라 한쪽에만 있는 끝 {dropped}일을 뺐습니다 (공개 지연)")

    mvrv_values = mvrv.set_index(COL_DATE)[COL_VALUE]
    market_cap_values = market_cap.set_index(COL_DATE)[COL_VALUE]
    frame = pd.DataFrame(
        {
            COL_DATE: common.to_numpy(),
            COL_MVRV: mvrv_values.loc[common].to_numpy(),
            COL_MARKET_CAP: market_cap_values.loc[common].to_numpy(),
        }
    )

    return LoadedOnchain(frame=frame, mvrv=mvrv, market_cap=market_cap, dropped_days=dropped)


def _onchain_gap(trading_days: pd.DatetimeIndex, onchain: pd.DataFrame) -> int:
    """시세의 거래일 중 온체인 값이 없는 날을 센다 — **끝에서 공개 지연 허용치까지만** 받는다.

    온체인 두 계열은 시세와 따로 받고 공개 지연을 허용받으므로 시세보다 그만큼 짧을 수 있다
    (`data/coinmetrics_collector.PUBLICATION_LAG_DAYS`). 그보다 짧거나 끝이 아닌 자리가 비면 **묵은 온체인 파일**이
    섞인 것이라 멈춘다 — 빈칸으로 두고 지나가면 그 사이의 온체인 돌파가 예외 없이 사라진다. 수집은 시세를 먼저
    저장하므로 온체인 수집이 실패하면 새 시세 옆에 묵은 온체인 파일이 남는다.

    Args:
        trading_days: 시세의 거래일
        onchain: 두 온체인 계열이 함께 있는 날의 표 (`load_onchain` 의 `frame`)

    Returns:
        온체인 값이 없는 끝 거래일의 수

    Raises:
        ValueError: 값이 없는 거래일이 허용치보다 많거나 끝이 아닌 자리에 있는 경우
    """
    covered = np.asarray(trading_days.isin(pd.DatetimeIndex(onchain[COL_DATE])))
    missing = int((~covered).sum())
    if missing > PUBLICATION_LAG_DAYS or not covered[: len(covered) - missing].all():
        raise ValueError(
            f"온체인 계열이 시세의 거래일을 덮지 못합니다 — 온체인 값이 없는 거래일 {missing:,}일"
            f"(허용: 끝 {PUBLICATION_LAG_DAYS}일까지) · 시세 {trading_days[0].date()} ~ {trading_days[-1].date()} · "
            f"온체인 {onchain[COL_DATE].iloc[0].date()} ~ {onchain[COL_DATE].iloc[-1].date()}. "
            "묵은 파일이 섞였을 수 있습니다 — `scripts/data/collect_btc.py` 로 다시 받으세요"
        )
    if missing:
        logger.warning(f"시세의 끝 {missing}일에 온체인 값이 없어 그날들의 온체인 돌파를 판정하지 않습니다 (공개 지연)")

    return missing


def signal_returns(frame: pd.DataFrame) -> pd.DataFrame:
    """신호(반감기 × 진입 개월 × 보유 개월)의 long-form 수익률을 낸다.

    **측정만 쓰고 체결은 부르지 않는다.** 3단계 체결은 `halving_calendar.position_schedule` 의 일정으로 들어가고,
    두 일정은 진입일 규칙이 같고 구현이 둘이다 — 규칙을 바꿀 때 함께 바꿀 곳은 그 모듈 docstring 이 말한다.

    Args:
        frame: 날짜 오름차순 시세

    Returns:
        진입 × 보유 행. 청산이 데이터 끝을 넘은 행도 남는다
    """
    trading_days = pd.DatetimeIndex(frame[COL_DATE])
    entries = halving_entries(trading_days, HALVINGS, ENTRY_MONTHS)

    return calendar_returns(frame, exit_schedule(trading_days, entries, HOLD_MONTHS))


def _baseline_returns(frame: pd.DataFrame, hold_months: Sequence[int] = HOLD_MONTHS) -> pd.DataFrame:
    """기준선(첫 반감기부터 매일 진입 × 같은 보유)의 long-form 수익률을 낸다.

    Args:
        frame: 날짜 오름차순 시세
        hold_months: 보유 개월 — 기본은 1단계 격자의 보유다

    Returns:
        매일 × 보유 행
    """
    trading_days = pd.DatetimeIndex(frame[COL_DATE])
    entries = baseline_entries(trading_days, HALVINGS[0].day)

    return calendar_returns(frame, exit_schedule(trading_days, entries, hold_months))


def halving_records() -> list[dict[str, Any]]:
    """실행 요약에 싣는 반감기 넷 — 높이 · 블록 시각 · 날짜.

    **측정과 체결의 요약이 같은 함수로 낸다** — 두 칸이 다른 형식으로 같은 값을 적지 않게 한다.

    Returns:
        반감기마다 한 줄
    """
    return [
        {KEY_HEIGHT: halving.height, KEY_BLOCK_TIME: halving.block_time.isoformat(), KEY_DATE: halving.label}
        for halving in HALVINGS
    ]


def _non_overlapping(trading_days: pd.DatetimeIndex, frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """칸마다 **겹치지 않게 고를 수 있는 체결의 최대 개수**를 센다.

    **산식은 `measure.statistics.max_non_overlapping` 이 소유한다.** 보유가 달력월이라 체결마다 길이가
    며칠씩 다르므로 **그 칸의 가장 긴 보유**를 구간 길이로 쓴다 — 짧게 잡으면 실제로 겹친 두 구간을
    독립으로 세어 표본이 실제보다 단단해 보인다.

    Args:
        trading_days: 거래일 목록
        frame: 제외 행이 섞인 long-form
        keys: 칸을 가르는 컬럼

    Returns:
        칸 키 컬럼 + 비중첩 개수
    """
    valid = frame[frame[COL_EXCLUDED_REASON] == REASON_NONE]

    rows: list[dict[str, Any]] = []
    # 키를 «목록»으로 넘기므로 묶음 키는 칸이 하나여도 언제나 튜플이다
    for key, cell in valid.groupby(keys, sort=True):
        positions = resolve_positions(trading_days, pd.DatetimeIndex(cell[COL_DATE]), label="진입일")
        count = max_non_overlapping(positions.tolist(), int(cell[COL_HOLD_DAYS].max()))
        rows.append({**dict(zip(keys, key, strict=True)), COL_NON_OVERLAPPING: count})

    return pd.DataFrame(rows, columns=[*keys, COL_NON_OVERLAPPING])


def _baseline(baseline: pd.DataFrame, trading_days: pd.DatetimeIndex) -> _Baseline:
    """기준선 long-form 을 한 번만 집계해 두 단계가 함께 쓰게 한다.

    Args:
        baseline: 기준선 long-form (제외 행 포함)
        trading_days: 거래일 목록

    Returns:
        기준선 묶음
    """
    summary = summarize(baseline)
    values = summary[[COL_HORIZON, *_SUMMARY_VALUES]].rename(
        columns={column: f"{column}{BASELINE_SUFFIX}" for column in _SUMMARY_VALUES}
    )
    overlap = _non_overlapping(trading_days, baseline, [COL_HOLD_MONTHS]).rename(
        columns={COL_HOLD_MONTHS: COL_HORIZON, COL_NON_OVERLAPPING: COL_BASELINE_NON_OVERLAPPING}
    )

    return _Baseline(returns=baseline, summary=summary, values=values, overlap=overlap)


def _baseline_for(baseline: _Baseline, hold_months: int) -> _Baseline:
    """기준선 묶음에서 보유 하나만 남긴다.

    **칸의 보유 구성이 기준선과 같아야 `excess` 가 돈다** — 3단계 격자의 칸은 보유가 하나라, 여러 보유의 기준선을
    그대로 넘기면 칸 구성이 달라 멈춘다. 유효 표본이 없는 보유는 비중첩 행이 없으므로 **빈칸 한 행**을 둔다 —
    없으면 차이 표를 붙일 때 그 칸이 조용히 사라진다.

    Args:
        baseline: 여러 보유의 기준선 묶음
        hold_months: 남길 보유 개월

    Returns:
        그 보유만 담은 기준선 묶음

    Raises:
        RuntimeError: 기준선 집계에 그 보유가 없는 경우 (내부 불변조건 위반 — 기준선 보유는 격자에서 유도한다)
    """
    summary = baseline.summary[baseline.summary[COL_HORIZON] == hold_months]
    if summary.empty:
        raise RuntimeError(f"내부 불변조건 위반: 기준선 집계에 보유 {hold_months}개월이 없습니다")

    overlap = baseline.overlap[baseline.overlap[COL_HORIZON] == hold_months]
    if overlap.empty:
        overlap = pd.DataFrame({COL_HORIZON: [hold_months], COL_BASELINE_NON_OVERLAPPING: [pd.NA]})

    return _Baseline(
        returns=baseline.returns[baseline.returns[COL_HORIZON] == hold_months],
        summary=summary,
        values=baseline.values[baseline.values[COL_HORIZON] == hold_months],
        overlap=overlap,
    )


def _empty_summary(baseline: _Baseline) -> pd.DataFrame:
    """신호가 한 번도 없던 칸의 집계 — 기준선과 같은 보유 칸에 건수 0 · 지표는 빈칸.

    **0 으로 채우지 않는다** — 「손실도 이익도 없었다」로 읽힌다 (측정의 원칙 17).

    Args:
        baseline: 기준선 묶음

    Returns:
        `SUMMARY_COLUMNS` 구성
    """
    counts = (COL_SIGNAL_COUNT, COL_EXCLUDED_COUNT, COL_SAMPLE_COUNT, COL_POSITIVE_COUNT, COL_NEGATIVE_COUNT)
    empty = baseline.summary[[COL_BASIS, COL_HORIZON]].copy()
    for column in SUMMARY_COLUMNS[2:]:
        empty[column] = 0 if column in counts else float("nan")

    return empty[SUMMARY_COLUMNS]


def _untested(summary: pd.DataFrame) -> pd.DataFrame:
    """검정하지 않은 칸의 무작위 뽑기 대조 — 표본 0 · 우연확률 빈칸 · 사유.

    Args:
        summary: 그 칸의 집계

    Returns:
        `TEST_COLUMNS` 구성
    """
    untested = summary[[COL_BASIS, COL_HORIZON, COL_SAMPLE_COUNT]].copy()
    for column in TEST_COLUMNS[3:]:
        untested[column] = NOTE_TOO_FEW_SAMPLES if column == COL_TEST_NOTE else float("nan")

    return untested[TEST_COLUMNS]


def _cell_tables(
    cell: pd.DataFrame, baseline: _Baseline, *, repeats: int, seed: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """칸 하나(보유 개월별)의 집계 · 기준선 대비 차이 · 우연확률 — 1단계와 2단계가 같은 것을 쓴다.

    **통계량 정의를 여기서 다시 구현하지 않는다** — `summarize` · `excess` · `permutation_test` 를 조립할 뿐이다.
    행이 하나도 없는 칸(한 번도 없던 신호)은 건수 0 · 지표 빈칸 · 「표본 부족으로 검정 불가」다.

    Args:
        cell: 그 칸의 long-form (제외 행 포함)
        baseline: 기준선 묶음
        repeats: 무작위 뽑기 반복 수
        seed: 무작위 뽑기 시드

    Returns:
        (집계 + 어긋남 · 판정가능, 차이 + 기준선 값 · 비중첩, 무작위 뽑기 대조) — 셋 다 구간 축(보유 개월)을 갖는다
    """
    summary = summarize(cell) if not cell.empty else _empty_summary(baseline)
    cell_excess = excess(summary, baseline.summary).merge(baseline.values, on=COL_HORIZON)
    cell_excess = cell_excess.merge(baseline.overlap, on=COL_HORIZON)
    cell_test = (
        permutation_test(cell, baseline.returns, repeats=repeats, seed=seed) if not cell.empty else _untested(summary)
    )

    summary[COL_MEAN_RATE_CONFLICT] = yes_no(mean_rate_conflict(summary))
    summary[COL_JUDGEABLE] = summary[COL_SAMPLE_COUNT].map(lambda count: judgeable(int(count)))

    return summary, cell_excess, cell_test


def _aggregate(
    signal: pd.DataFrame,
    baseline: _Baseline,
    *,
    trading_days: pd.DatetimeIndex,
    repeats: int,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """1단계 칸마다 신호 집계 · 기준선 대비 차이 · 우연확률을 낸다.

    [중요] **제외 행을 포함한 «전체»를 받는다.** 유효 행만 넘기면 `summarize` 가 셀 제외가 없어
    `제외` 가 언제나 0 이 되는데, 이 저장소에서 0 은 「재서 0」이라 없는 안전을 보고하게 된다.

    Args:
        signal: 신호 long-form (제외 행 포함)
        baseline: 기준선 묶음
        trading_days: 거래일 목록
        repeats: 무작위 뽑기 반복 수
        seed: 무작위 뽑기 시드

    Returns:
        (통계, excess, test) — 식별 컬럼 없이 진입 · 보유 칸 축만 붙은 표

    Raises:
        ValueError: 진입이 하나도 없는 진입 개월이 있는 경우 — 칸 구성이 기준선과 어긋나 차이를 낼 수 없다
    """
    signal_overlap = _non_overlapping(trading_days, signal, [COL_ENTRY_MONTHS, COL_HOLD_MONTHS])

    statistics: list[pd.DataFrame] = []
    excess_blocks: list[pd.DataFrame] = []
    test_blocks: list[pd.DataFrame] = []
    for entry_months in ENTRY_MONTHS:
        cell = signal[signal[COL_ENTRY_MONTHS] == entry_months]
        if cell.empty:
            raise ValueError(f"진입이 하나도 없는 칸이 있습니다: 반감기 뒤 {entry_months}개월 진입")

        summary, cell_excess, cell_test = _cell_tables(cell, baseline, repeats=repeats, seed=seed)

        for table, blocks in ((summary, statistics), (cell_excess, excess_blocks), (cell_test, test_blocks)):
            blocks.append(table.assign(**{COL_ENTRY_MONTHS: entry_months}))

    def cells(blocks: list[pd.DataFrame], values: list[str]) -> pd.DataFrame:
        combined = pd.concat(blocks, ignore_index=True).rename(columns={COL_HORIZON: COL_HOLD_MONTHS})
        return combined[[COL_ENTRY_MONTHS, COL_HOLD_MONTHS, *values]]

    statistics_values = [*_SUMMARY_VALUES, COL_MEAN_RATE_CONFLICT, COL_JUDGEABLE]
    statistics_table = cells(statistics, statistics_values).merge(
        signal_overlap, on=[COL_ENTRY_MONTHS, COL_HOLD_MONTHS], how="left"
    )
    # 유효 체결이 없는 칸은 비중첩도 0 이 아니라 **센 것이 없다** — 결측을 견디는 정수로 둔다
    statistics_table[COL_NON_OVERLAPPING] = statistics_table[COL_NON_OVERLAPPING].astype("Int64")

    return statistics_table, cells(excess_blocks, _EXCESS_VALUES), cells(test_blocks, _TEST_VALUES)


def _crosscheck_table(result: CrosscheckResult) -> pd.DataFrame:
    """허용폭을 넘은 날 전체와 그날 Bitstamp 에 거래가 있었는지.

    Args:
        result: 크로스체크 결과

    Returns:
        날짜 · 두 종가 · 차이율 · 거래량 0 여부
    """
    table = result.over_tolerance[[COL_DATE, COL_PRIMARY, COL_SECONDARY, COL_DIFF_RATE]].reset_index(drop=True)
    table[COL_ZERO_VOLUME] = yes_no(table[COL_DATE].isin(result.zero_volume[COL_DATE]))

    return table


def _indicator_statistics(
    returns: pd.DataFrame,
    baseline: _Baseline,
    *,
    signals: tuple[IndicatorSignal, ...],
    trading_days: pd.DatetimeIndex,
    repeats: int,
    seed: int,
) -> pd.DataFrame:
    """2단계 (신호 × 보유) 칸마다 집계 · 사이클 수 · 비중첩 · 기준선 · 차이 · 우연확률을 한 행에 낸다.

    **한 번도 없던 신호도 보유마다 행을 남긴다** (측정의 원칙 17). 칸 집계는 1단계와 같은 함수(`_cell_tables`)다.

    Args:
        returns: 신호 × 보유 long-form (제외 행 포함)
        baseline: 기준선 묶음 — 1단계와 같다
        signals: 신호 목록 (행 순서)
        trading_days: 거래일 목록
        repeats: 무작위 뽑기 반복 수
        seed: 무작위 뽑기 시드

    Returns:
        `_INDICATOR_STATISTICS_COLUMNS` 구성. 신호 목록 → 보유 순서
    """
    keys = [COL_INDICATOR_SIGNAL, COL_HOLD_MONTHS]
    overlap = _non_overlapping(trading_days, returns, keys)
    valid = returns[returns[COL_EXCLUDED_REASON] == REASON_NONE]
    cycles = valid.groupby(keys)[COL_HALVING].nunique().rename(COL_CYCLE_COUNT).reset_index()

    blocks: list[pd.DataFrame] = []
    for signal in signals:
        cell = returns[returns[COL_INDICATOR_SIGNAL] == signal.name]
        summary, cell_excess, cell_test = _cell_tables(cell, baseline, repeats=repeats, seed=seed)
        table = summary.drop(columns=[COL_BASIS]).merge(cell_excess.drop(columns=[COL_BASIS]), on=COL_HORIZON)
        table = table.merge(cell_test[[COL_HORIZON, *_TEST_VALUES[1:]]], on=COL_HORIZON)
        table.insert(0, COL_INDICATOR_SIGNAL, signal.name)
        table.insert(1, COL_SIGNAL_MEANING, signal.meaning)
        blocks.append(table.rename(columns={COL_HORIZON: COL_HOLD_MONTHS}))

    combined = (
        pd.concat(blocks, ignore_index=True).merge(overlap, on=keys, how="left").merge(cycles, on=keys, how="left")
    )
    # 유효 체결이 없는 칸은 비중첩을 «센 것이 없다»(빈칸)로, 사이클 수는 «0 사이클»로 둔다 — 사이클 수 0 은 사실이다
    combined[COL_NON_OVERLAPPING] = combined[COL_NON_OVERLAPPING].astype("Int64")
    combined[COL_CYCLE_COUNT] = combined[COL_CYCLE_COUNT].fillna(0).astype("int64")

    return combined[_INDICATOR_STATISTICS_COLUMNS]


def grid_baseline_table(frame: pd.DataFrame, *, repeats: int, seed: int) -> pd.DataFrame:
    """3단계 격자 중 **같은 사이클에 파는 칸**마다 칸 집계와 같은 보유의 기준선을 한 행에 낸다 (결정 ㊶).

    칸 값은 체결 격자와 같은 일정(`halving_calendar.position_schedule`)을 **측정 쪽에서** 종가로 잰 것이라 무손절
    체결과 같다 — 체결 코드는 부르지 않는다(`trading` 이 이 모듈을 가져온다). 보유는 청산 − 진입 달력월이고, 기준선은
    1단계와 같은 모집단(첫 반감기부터 매일 진입)에 그 보유를 준 것이다. 칸 집계는 1단계 · 2단계와 같은 `_cell_tables` 다.

    **진입이 한 번도 없던 칸도 행을 남긴다** (측정의 원칙 17). **판정에 쓰지 않는다.**

    Args:
        frame: 날짜 오름차순 시세 (측정 계열)
        repeats: 무작위 뽑기 반복 수
        seed: 무작위 뽑기 시드

    Returns:
        `_GRID_BASELINE_COLUMNS` 구성. 진입 → 청산 순서

    Raises:
        RuntimeError: 반감기일 + 진입 개월 + 보유 개월이 반감기일 + 청산 개월과 다른 (반감기 × 칸)이 있는 경우
            (내부 불변조건 위반 — 아래 가드)
    """
    pairs = [(entry, exit_) for entry in ENTRY_MONTHS for exit_ in EXIT_MONTHS if exit_ > entry]

    # **칸의 보유를 (청산 − 진입) 개월로 두는 전제를 지킨다.** 반감기일 + 진입 개월 + 보유 개월이 반감기일 + 청산 개월과
    # 같은 날이어야 기준선이 칸과 같은 보유를 잰다. 반감기일이 29 ~ 31일이면 짧은 달의 말일 당김으로 며칠 어긋날 수 있고,
    # 그러면 예외 없이 다른 보유와 견주게 된다. **반감기일이 아니라 등식 자체를 쌍마다 본다** — 격자가 지나는 달이 모두
    # 길면 29 ~ 31일이어도 성립한다. 날짜만의 사실이라 데이터를 잘라도 판정이 바뀌지 않는다
    broken = [
        (halving.label, entry, exit_)
        for halving in HALVINGS
        for entry, exit_ in pairs
        if halving.day + pd.DateOffset(months=entry) + pd.DateOffset(months=exit_ - entry)
        != halving.day + pd.DateOffset(months=exit_)
    ]
    if broken:
        raise RuntimeError(
            "내부 불변조건 위반: 반감기일에 진입 개월과 보유 개월을 나눠 더한 날이 청산일과 다른 칸이 있어 같은 사이클 칸의 "
            f"보유를 (청산 − 진입) 개월로 둘 수 없습니다 — (반감기, 진입, 청산) {broken[:5]} 외 {max(len(broken) - 5, 0)}건. "
            "칸마다 실제 보유 일수로 기준선을 짝짓도록 설계를 먼저 정하세요"
        )

    trading_days = pd.DatetimeIndex(frame[COL_DATE])
    schedule = position_schedule(trading_days, HALVINGS, ENTRY_MONTHS, EXIT_MONTHS).schedule
    same_cycle = schedule[schedule[COL_EXIT_MONTHS] > schedule[COL_ENTRY_MONTHS]]
    # **구간 축은 보유 개월이다** — 칸 집계가 기준선의 같은 보유와 짝지어지려면 보유가 칸의 이름이어야 한다
    returns = calendar_returns(
        frame, same_cycle.assign(**{COL_HOLD_MONTHS: same_cycle[COL_EXIT_MONTHS] - same_cycle[COL_ENTRY_MONTHS]})
    )
    baseline = _baseline(_baseline_returns(frame, GRID_BASELINE_HOLD_MONTHS), trading_days)

    keys = [COL_ENTRY_MONTHS, COL_EXIT_MONTHS]
    overlap = _non_overlapping(trading_days, returns, keys)

    blocks: list[pd.DataFrame] = []
    for entry_months, exit_months in pairs:
        cell = returns[(returns[COL_ENTRY_MONTHS] == entry_months) & (returns[COL_EXIT_MONTHS] == exit_months)]
        summary, cell_excess, cell_test = _cell_tables(
            cell, _baseline_for(baseline, exit_months - entry_months), repeats=repeats, seed=seed
        )
        table = summary.drop(columns=[COL_BASIS]).merge(cell_excess.drop(columns=[COL_BASIS]), on=COL_HORIZON)
        table = table.merge(cell_test[[COL_HORIZON, *_TEST_VALUES[1:]]], on=COL_HORIZON)
        blocks.append(
            table.rename(columns={COL_HORIZON: COL_HOLD_MONTHS}).assign(
                **{COL_ENTRY_MONTHS: entry_months, COL_EXIT_MONTHS: exit_months}
            )
        )

    combined = pd.concat(blocks, ignore_index=True).merge(overlap, on=keys, how="left")
    # 유효 체결이 없는 칸 · 유효 기준선이 없는 보유는 비중첩을 «센 것이 없다»(빈칸)로 둔다
    for column in (COL_NON_OVERLAPPING, COL_BASELINE_NON_OVERLAPPING):
        combined[column] = combined[column].astype("Int64")

    return combined[_GRID_BASELINE_COLUMNS]


def _indicator_cycles(returns: pd.DataFrame, signals: tuple[IndicatorSignal, ...]) -> pd.DataFrame:
    """2단계 (신호 × 보유 × 반감기)마다 집계 — **0건인 사이클도 행을 남긴다** (결정 ㉘ ④).

    첫 반감기 전 판정은 어느 사이클에도 들지 않아 이 표에 없다 — 그 행은 신호일 목록에 사유와 함께 있다.

    Args:
        returns: 신호 × 보유 long-form (제외 행 포함)
        signals: 신호 목록 (행 순서)

    Returns:
        신호 · 보유 · 반감기 · `_INDICATOR_CYCLE_VALUES`. 신호 목록 → 보유 → 반감기 순서
    """
    counts = (COL_SIGNAL_COUNT, COL_EXCLUDED_COUNT, COL_SAMPLE_COUNT)
    order = "_signal_order"
    rows: list[pd.DataFrame] = []
    for position, signal in enumerate(signals):
        for halving in HALVINGS:
            cell = returns[(returns[COL_INDICATOR_SIGNAL] == signal.name) & (returns[COL_HALVING] == halving.label)]
            summary = summarize(cell).set_index(COL_HORIZON) if not cell.empty else pd.DataFrame()
            table = summary.reindex(list(HOLD_MONTHS), columns=_INDICATOR_CYCLE_VALUES)
            for column in counts:
                table[column] = table[column].fillna(0).astype("int64")
            table.index.name = COL_HOLD_MONTHS
            rows.append(
                table.reset_index().assign(
                    **{order: position, COL_INDICATOR_SIGNAL: signal.name, COL_HALVING: halving.label}
                )
            )

    # 반감기 표지는 `YYYY-MM-DD` 라 글자 순서가 곧 시간 순서다
    combined = pd.concat(rows, ignore_index=True).sort_values([order, COL_HOLD_MONTHS, COL_HALVING], kind="stable")

    return combined[[COL_INDICATOR_SIGNAL, COL_HOLD_MONTHS, COL_HALVING, *_INDICATOR_CYCLE_VALUES]].reset_index(
        drop=True
    )


def _entry_indicator_table(
    signal: pd.DataFrame, trading_days: pd.DatetimeIndex, daily: pd.DataFrame, monthly: pd.DataFrame
) -> pd.DataFrame:
    """1단계 진입마다 진입 전날까지의 지표 값과 보유별 수익률을 한 행에 낸다 (결정 ㉔ 의 (나) · ㉗).

    **수익률은 1단계 long-form 의 값을 펼칠 뿐이다** — 다시 계산하지 않는다. 청산 전인 보유는 빈칸이다.

    Args:
        signal: 1단계 long-form (제외 행 포함)
        trading_days: 거래일 목록
        daily: 일간 지표 표 (시세 날짜 인덱스)
        monthly: 월간 지표 표 (말일 인덱스)

    Returns:
        반감기 · 진입 개월 · 진입일 · 값 기준일 · 월간 기준 달 · 지표 여섯 · 보유별 수익률. 1단계 진입 순서
    """
    keys = [COL_HALVING, COL_ENTRY_MONTHS]
    entries = signal.drop_duplicates(keys)[[*keys, COL_DATE]].reset_index(drop=True)
    values = entry_indicator_values(
        trading_days,
        pd.DatetimeIndex(entries[COL_DATE]),
        daily[_ENTRY_DAILY_INDICATORS],
        monthly[_ENTRY_MONTHLY_INDICATORS],
    )
    returns = (
        signal.set_index([*keys, COL_HOLD_MONTHS])[COL_FORWARD_RETURN]
        .unstack(COL_HOLD_MONTHS)
        .rename(columns=COL_HOLD_RETURNS)
        .rename_axis(columns=None)
        .reset_index()
    )

    return pd.concat([entries[keys], values], axis=1).merge(returns, on=keys, how="left")


def _indicator_rule(signals: tuple[IndicatorSignal, ...]) -> dict[str, Any]:
    """실행 요약에 싣는 2단계 규칙 — 창 · 신호 목록.

    Args:
        signals: 신호 목록

    Returns:
        요약의 한 칸
    """
    return {
        KEY_PI_CYCLE_WINDOWS: [PI_CYCLE_SHORT_WINDOW, PI_CYCLE_LONG_WINDOW],
        KEY_PI_CYCLE_MULTIPLIER: PI_CYCLE_LONG_MULTIPLIER,
        KEY_DISPARITY_WINDOW: DISPARITY_WINDOW,
        KEY_RSI_WINDOW: RSI_WINDOW,
        KEY_MACD_SPANS: [MACD_FAST_SPAN, MACD_SLOW_SPAN, MACD_SIGNAL_SPAN],
        KEY_MVRV_Z_MIN_DAYS: MVRV_Z_MIN_DAYS,
        KEY_SIGNALS: [
            {
                KEY_NAME: signal.name,
                KEY_INDICATOR: signal.indicator,
                KEY_THRESHOLD: signal.threshold,
                KEY_UPWARD: signal.upward,
            }
            for signal in signals
        ],
    }


def _series_record(path_name: str, frame: pd.DataFrame) -> dict[str, Any]:
    """요약에 싣는 단일 값 계열 한 줄 — 파일 이름 · 기간 · 행 수. **경로는 싣지 않는다**.

    Args:
        path_name: 파일 이름
        frame: 로더를 지난 계열 (날짜 오름차순)

    Returns:
        요약의 한 칸
    """
    dates = frame[COL_DATE]

    return {KEY_FILE: path_name, KEY_PERIOD: format_period(dates.iloc[0], dates.iloc[-1]), KEY_ROWS: len(frame)}


def _split_rule() -> dict[str, Any]:
    """요약에 싣는 3단계 혼합 분할의 규칙 — 격자 값 전부와 조합 수.

    Returns:
        요약의 한 칸
    """
    return {
        KEY_SPLIT_TRANCHES: SPLIT_TRANCHES,
        KEY_SPLIT_DEADLINE_STEP: SPLIT_DEADLINE_STEP_MONTHS,
        KEY_SPLIT_BUY: {
            KEY_SPLIT_START_HALVING: list(SPLIT_BUY_START_MONTHS_HALVING),
            KEY_SPLIT_START_HIGH: list(SPLIT_BUY_START_MONTHS_HIGH),
            KEY_SPLIT_LAST_DEADLINES: list(SPLIT_BUY_LAST_DEADLINES),
            KEY_SPLIT_BOOK_LEVELS: list(SPLIT_BUY_BOOK_LEVELS),
            KEY_SPLIT_RANK_LEVELS: list(SPLIT_BUY_RANK_LEVELS),
            KEY_SPLIT_COMBINATIONS: len(_SPLIT_BUY_LEGS),
        },
        KEY_SPLIT_SELL: {
            KEY_SPLIT_START_HALVING: list(SPLIT_SELL_START_MONTHS),
            KEY_SPLIT_LAST_DEADLINES: list(SPLIT_SELL_LAST_DEADLINES),
            KEY_SPLIT_BOOK_LEVELS: list(SPLIT_SELL_BOOK_LEVELS),
            KEY_SPLIT_RANK_LEVELS: list(SPLIT_SELL_RANK_LEVELS),
            KEY_SPLIT_COMBINATIONS: len(_SPLIT_SELL_LEGS),
        },
        KEY_SPLIT_RANK_YEARS: SPLIT_RANK_YEARS,
        KEY_SPLIT_RANK_MIN_DAYS: SPLIT_RANK_MIN_DAYS,
        KEY_SPLIT_NOTES: list(SPLIT_NOTES),
    }


def _calendar_split_rule(splits: Sequence[CalendarSplit], step_months: int) -> dict[str, Any]:
    """요약에 싣는 3단계 달력 매달 분할의 규칙 — 폭마다 회차 수와 매수 · 매도 개월(첫 · 마지막).

    Args:
        splits: 폭 목록
        step_months: 회차 간격(개월)

    Returns:
        요약의 한 칸
    """
    entries: list[dict[str, Any]] = []
    for split in splits:
        buy_first, sell_first = split.first_deadlines(step_months)
        entries.append(
            {
                KEY_NAME: split.name,
                KEY_SPLIT_TRANCHES: split.tranches,
                KEY_CALENDAR_SPLIT_BUY_MONTHS: [buy_first, split.buy_last_deadline],
                KEY_CALENDAR_SPLIT_SELL_MONTHS: [sell_first, split.sell_last_deadline],
            }
        )

    return {
        KEY_CALENDAR_SPLIT_STEP: step_months,
        KEY_CALENDAR_SPLIT_SPLITS: entries,
        KEY_SPLIT_NOTES: list(CALENDAR_SPLIT_NOTES),
    }


def _split_counts(split: SplitGrid | CalendarSplitGrid) -> dict[str, Any]:
    """요약에 싣는 대상별 3단계 분할 건수 — **몇 건이 왜 빠졌는지** (표본 보존). 혼합 분할과 달력 분할이 함께 쓴다.

    Args:
        split: 혼합 분할 격자 또는 달력 분할 격자

    Returns:
        요약의 한 칸
    """

    def by_reason(table: pd.DataFrame) -> dict[str, int]:
        reasons = table[COL_EXCLUDED_REASON]
        return {str(reason): int(count) for reason, count in reasons[reasons != REASON_NONE].value_counts().items()}

    return {
        KEY_SPLIT_FILL_COUNT: len(split.fills),
        KEY_SPLIT_UNFILLED: by_reason(split.fills),
        KEY_SPLIT_POSITION_COUNT: len(split.positions),
        KEY_SPLIT_UNFINISHED: by_reason(split.positions),
    }


def run_study(
    datasets: tuple[Dataset, ...] = DATASETS,
    *,
    repeats: int = DEFAULT_REPEAT_COUNT,
    seed: int = DEFAULT_RANDOM_SEED,
) -> StudyOutputs:
    """반감기_사이클 측정을 실행하고 산출물을 조립한다.

    Args:
        datasets: 검증 대상 목록
        repeats: 무작위 뽑기 반복 수
        seed: 무작위 뽑기 시드

    Returns:
        실행 산출물

    Raises:
        ValueError: 대상 목록이 비어 있는 경우
    """
    if not datasets:
        raise ValueError("검증 대상이 하나도 없습니다")

    blocks: dict[str, list[pd.DataFrame]] = {field: [] for field in OUTPUT_FILES}
    dataset_summaries: list[dict[str, Any]] = []

    for dataset in datasets:
        loaded = load_dataset(dataset)
        frame = loaded.frame
        trading_days = pd.DatetimeIndex(frame[COL_DATE])

        signal = signal_returns(frame)
        baseline = _baseline(_baseline_returns(frame), trading_days)
        statistics, cell_excess, cell_test = _aggregate(
            signal, baseline, trading_days=trading_days, repeats=repeats, seed=seed
        )
        # 3단계 격자 중 같은 사이클에 파는 칸 — 1단계와 같은 모집단에 보유(청산 − 진입)를 준 기준선과 나란히 둔다
        grid_baseline = grid_baseline_table(frame, repeats=repeats, seed=seed)

        # 2단계 — 지표는 측정 계열(종가 대체 뒤)로 내고, 신호는 1단계와 같은 기준선에 견준다
        onchain = load_onchain(dataset)
        missing_price_days = _onchain_gap(trading_days, onchain.frame)
        daily = daily_indicator_frame(frame, onchain.frame)
        monthly = monthly_indicator_frame(frame)
        indicator_values = {
            **{column: daily[column] for column in daily.columns},
            COL_MONTHLY_RSI: monthly[COL_MONTHLY_RSI],
            COL_MACD_HISTOGRAM: monthly[COL_MACD_HISTOGRAM],
        }
        indicator_returns = indicator_signal_returns(frame, indicator_values, INDICATOR_SIGNALS, HALVINGS, HOLD_MONTHS)

        # 3단계 혼합 분할 — MVRV 는 2단계 지표와 같은 계열(두 온체인 계열이 함께 있는 날)이다
        split = split_grid(
            frame,
            onchain.frame.set_index(COL_DATE)[COL_MVRV],
            HALVINGS,
            _SPLIT_BUY_LEGS,
            _SPLIT_SELL_LEGS,
            tranches=SPLIT_TRANCHES,
            step_months=SPLIT_DEADLINE_STEP_MONTHS,
            rank_years=SPLIT_RANK_YEARS,
            rank_min_days=SPLIT_RANK_MIN_DAYS,
        )
        # 3단계 달력 매달 분할 — 같은 측정 시세로 폭 전부를 잰다
        calendar_split = calendar_split_grid(frame, HALVINGS, CALENDAR_SPLITS, step_months=CALENDAR_SPLIT_STEP_MONTHS)

        direction = DIRECTION_DOWN if BET_DOWN else DIRECTION_UP
        tables = {
            FIELD_STATISTICS: statistics,
            FIELD_EXCESS: cell_excess,
            FIELD_TEST: cell_test,
            FIELD_ENTRIES: signal[_ENTRY_COLUMNS],
            FIELD_CALENDAR_YEARS: calendar_year_returns(frame, HALVINGS),
            FIELD_CROSSCHECK: _crosscheck_table(loaded.crosscheck),
            FIELD_REPLACED: loaded.replaced,
            FIELD_INDICATOR_SIGNALS: indicator_returns[_INDICATOR_SIGNAL_COLUMNS],
            FIELD_INDICATOR_STATISTICS: _indicator_statistics(
                indicator_returns,
                baseline,
                signals=INDICATOR_SIGNALS,
                trading_days=trading_days,
                repeats=repeats,
                seed=seed,
            ),
            FIELD_INDICATOR_CYCLES: _indicator_cycles(indicator_returns, INDICATOR_SIGNALS),
            FIELD_ENTRY_INDICATORS: _entry_indicator_table(signal, trading_days, daily, monthly),
            FIELD_SPLIT_FILLS: split.fills,
            FIELD_SPLIT_POSITIONS: split.positions,
            FIELD_SPLIT_COMBINATIONS: split.combinations,
            FIELD_GRID_BASELINE: grid_baseline,
            FIELD_CALENDAR_SPLIT_FILLS: calendar_split.fills,
            FIELD_CALENDAR_SPLIT_POSITIONS: calendar_split.positions,
        }
        for field, table in tables.items():
            labelled = table.copy()
            labelled.insert(0, COL_TICKER, dataset.label)
            # **방향은 칸 표 넷에만 붙는다** — 성적표와 조인되는 표이고, 나머지는 칸이 아니다
            if field in (FIELD_STATISTICS, FIELD_EXCESS, FIELD_TEST, FIELD_GRID_BASELINE):
                labelled.insert(3, COL_DIRECTION, direction)
            blocks[field].append(labelled)

        excluded_count = int((signal[COL_EXCLUDED_REASON] != REASON_NONE).sum())
        crosscheck = loaded.crosscheck
        indicator_excluded = indicator_returns[COL_EXCLUDED_REASON] != REASON_NONE
        dataset_summaries.append(
            {
                # **`ticker` 는 반드시 `dataset.ticker` 에서 온다** — 둘 다 `str` 이라 다른 필드를 넘겨도
                # 키 이름은 그대로고 값만 조용히 뒤바뀐다 (`tests/test_layer_contracts.py` 가 출처를 검사한다)
                **dataset_record(ticker=dataset.ticker, label=dataset.label, file=dataset.path.name, frame=frame),
                # **파일 이름만 싣는다** — 절대경로는 PC 마다 달라 커밋된 요약이 갈린다
                KEY_REFERENCE: _series_record(dataset.reference_path.name, loaded.reference),
                KEY_ONCHAIN: {
                    KEY_MVRV: _series_record(dataset.mvrv_path.name, onchain.mvrv),
                    KEY_MARKET_CAP: _series_record(dataset.market_cap_path.name, onchain.market_cap),
                    # 두 온체인 파일 중 한쪽에만 있어 뺀 끝 날
                    KEY_DROPPED_TAIL_DAYS: onchain.dropped_days,
                    # 시세의 끝 거래일 중 온체인 값이 없는 날 — 그날들의 온체인 지표는 비어 있어 돌파를 판정하지 않았다
                    KEY_MISSING_PRICE_DAYS: missing_price_days,
                },
                # 신호 × 보유 행의 수와 그중 제외 — 사유별 행은 신호일 목록에 있다
                KEY_INDICATOR_SIGNALS: [
                    {
                        KEY_NAME: indicator_signal.name,
                        KEY_SIGNAL_COUNT: int((indicator_returns[COL_INDICATOR_SIGNAL] == indicator_signal.name).sum()),
                        KEY_EXCLUDED_COUNT: int(
                            (
                                indicator_excluded & (indicator_returns[COL_INDICATOR_SIGNAL] == indicator_signal.name)
                            ).sum()
                        ),
                    }
                    for indicator_signal in INDICATOR_SIGNALS
                ],
                KEY_SIGNAL_COUNT: len(signal),
                KEY_EXCLUDED_COUNT: excluded_count,
                KEY_REPLACED_COUNT: len(loaded.replaced),
                KEY_SPLIT: _split_counts(split),
                KEY_CALENDAR_SPLIT: _split_counts(calendar_split),
                KEY_CROSSCHECK: {
                    KEY_TOLERANCE: crosscheck.tolerance,
                    KEY_OVERLAP_DAYS: len(crosscheck.overlap),
                    KEY_OVER_TOLERANCE_DAYS: len(crosscheck.over_tolerance),
                    KEY_PRIMARY_ONLY_DAYS: crosscheck.primary_only_count,
                    KEY_SECONDARY_ONLY_DAYS: crosscheck.secondary_only_count,
                    KEY_ZERO_VOLUME_DAYS: len(crosscheck.zero_volume),
                },
            }
        )

    combined = {field: pd.concat(frames, ignore_index=True) for field, frames in blocks.items()}

    summary: dict[str, Any] = {
        KEY_TRACK: TRACK_NAME,
        KEY_PERMUTATION_REPEATS: repeats,
        KEY_PERMUTATION_SEED: seed,
        KEY_HALVINGS: halving_records(),
        KEY_ENTRY_MONTHS: list(ENTRY_MONTHS),
        KEY_HOLD_MONTHS: list(HOLD_MONTHS),
        KEY_BASELINE_START: HALVINGS[0].label,
        KEY_GRID_BASELINE_HOLD_MONTHS: list(GRID_BASELINE_HOLD_MONTHS),
        KEY_INDICATOR_RULE: _indicator_rule(INDICATOR_SIGNALS),
        KEY_SPLIT_RULE: _split_rule(),
        KEY_CALENDAR_SPLIT_RULE: _calendar_split_rule(CALENDAR_SPLITS, CALENDAR_SPLIT_STEP_MONTHS),
        KEY_DATASETS: dataset_summaries,
        KEY_ROW_COUNTS: {OUTPUT_FILES[field]: len(table) for field, table in combined.items()},
    }

    logger.debug(
        f"측정 완료: 1단계 {len(combined[FIELD_STATISTICS]):,}칸 · 2단계 {len(combined[FIELD_INDICATOR_STATISTICS]):,}칸 "
        f"(대상 {len(datasets)})"
    )

    return StudyOutputs(
        statistics=combined[FIELD_STATISTICS],
        excess=combined[FIELD_EXCESS],
        test=combined[FIELD_TEST],
        entries=combined[FIELD_ENTRIES],
        calendar_years=combined[FIELD_CALENDAR_YEARS],
        crosscheck=combined[FIELD_CROSSCHECK],
        replaced=combined[FIELD_REPLACED],
        indicator_signals=combined[FIELD_INDICATOR_SIGNALS],
        indicator_statistics=combined[FIELD_INDICATOR_STATISTICS],
        indicator_cycles=combined[FIELD_INDICATOR_CYCLES],
        entry_indicators=combined[FIELD_ENTRY_INDICATORS],
        split_fills=combined[FIELD_SPLIT_FILLS],
        split_positions=combined[FIELD_SPLIT_POSITIONS],
        split_combinations=combined[FIELD_SPLIT_COMBINATIONS],
        grid_baseline=combined[FIELD_GRID_BASELINE],
        calendar_split_fills=combined[FIELD_CALENDAR_SPLIT_FILLS],
        calendar_split_positions=combined[FIELD_CALENDAR_SPLIT_POSITIONS],
        summary=summary,
    )


def _rounded_indicators(table: pd.DataFrame) -> pd.DataFrame:
    """지표 값을 저장 자릿수로 자른다 — RSI 2자리 · 나머지 4자리. 입력은 변경하지 않는다.

    **돌파 판정은 반올림 «전» 값으로 이미 끝났다** — 여기서 자르는 것은 부동소수점 잡음이 CSV 로 나가지 않게 하는 것뿐이다.
    이격도는 백분율로 바꾸는 컬럼이라 `to_display_columns` 가 자릿수를 맞춘다.

    Args:
        table: 지표 값이 있는 표

    Returns:
        자릿수를 맞춘 사본
    """
    decimals = {column: INDICATOR_DECIMALS for column in INDICATOR_VALUE_COLUMNS if column in table.columns}
    if COL_MONTHLY_RSI in table.columns:
        decimals[COL_MONTHLY_RSI] = RSI_DECIMALS

    return table.round(decimals)


def _rounded_prices(table: pd.DataFrame) -> pd.DataFrame:
    """3단계 분할 표(혼합 · 달력)의 가격을 가격 자릿수로 자른다. 입력은 변경하지 않는다.

    **평균 단가는 계산값이라 실제 시세에 없는 자리가 생긴다** — 그대로 내면 차트와 대조할 때 방해가 된다.

    Args:
        table: 가격 컬럼이 있는 표

    Returns:
        자릿수를 맞춘 사본
    """
    return table.round({column: PRICE_DECIMALS for column in _SPLIT_PRICE_COLUMNS if column in table.columns})


def display_tables(outputs: StudyOutputs) -> dict[str, pd.DataFrame]:
    """저장할 표를 표시용(한글 헤더·백분율)으로 바꾼다.

    **터미널과 CSV 가 같은 프레임을 쓴다.** 따로 가공하면 반올림 시점이 갈려 화면에서 본 숫자를
    CSV 에서 찾지 못한다.

    **빈 표는 내지 않는다** — 저장 계층이 빈 표를 거부하고, 행 수는 요약이 `0` 으로 남긴다
    (`src/verify_lab/CLAUDE.md` 「`row_counts` 의 `0` 은 「파일이 없다」는 뜻입니다」).

    Args:
        outputs: 실행 산출물

    Returns:
        산출물 필드 이름 → 표시용 DataFrame
    """
    tables = {
        FIELD_STATISTICS: outputs.statistics,
        FIELD_EXCESS: outputs.excess,
        FIELD_TEST: outputs.test,
        # **진입일을 시세의 날짜와 다른 이름으로 낸다** — 거래내역의 「진입일」과 같은 헤더가 나가야 대조된다
        FIELD_ENTRIES: outputs.entries.rename(columns={COL_DATE: COL_ENTRY_DATE}),
        FIELD_CALENDAR_YEARS: outputs.calendar_years,
        FIELD_CROSSCHECK: outputs.crosscheck,
        FIELD_REPLACED: outputs.replaced,
        FIELD_INDICATOR_SIGNALS: _rounded_indicators(
            outputs.indicator_signals.rename(columns={COL_DATE: COL_ENTRY_DATE})
        ),
        FIELD_INDICATOR_STATISTICS: outputs.indicator_statistics,
        FIELD_INDICATOR_CYCLES: outputs.indicator_cycles,
        FIELD_ENTRY_INDICATORS: _rounded_indicators(
            outputs.entry_indicators.rename(columns={COL_DATE: COL_ENTRY_DATE})
        ),
        FIELD_SPLIT_FILLS: _rounded_indicators(_rounded_prices(outputs.split_fills)),
        FIELD_SPLIT_POSITIONS: _rounded_prices(outputs.split_positions),
        FIELD_SPLIT_COMBINATIONS: outputs.split_combinations,
        FIELD_GRID_BASELINE: outputs.grid_baseline,
        FIELD_CALENDAR_SPLIT_FILLS: _rounded_prices(outputs.calendar_split_fills),
        FIELD_CALENDAR_SPLIT_POSITIONS: _rounded_prices(outputs.calendar_split_positions),
    }
    # 조합 표의 사이클별 가로 칸은 반감기 목록에서 이름을 만든다 — 사전에 박아 두면 반감기가 늘 때 빠진다
    labels = {**COLUMN_LABELS, **_CYCLE_LABELS}
    percent = (*PERCENT_COLUMNS, *_CYCLE_LABELS)

    return {
        field: to_display_columns(
            table,
            labels,
            percent_columns=[column for column in percent if column in table.columns],
            probability_columns=[column for column in PROBABILITY_COLUMNS if column in table.columns],
        )
        for field, table in tables.items()
        if not table.empty
    }


__all__ = [
    "LoadedDataset",
    "LoadedOnchain",
    "StudyOutputs",
    "display_tables",
    "grid_baseline_table",
    "halving_records",
    "load_onchain",
    "load_dataset",
    "run_study",
    "signal_returns",
]
