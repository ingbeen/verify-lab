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
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_DATE, COL_VALUE
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
    COL_BASELINE_NON_OVERLAPPING,
    COL_CYCLE_COUNT,
    COL_DISPARITY,
    COL_ENTRY_DATE,
    COL_ENTRY_MONTHS,
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
    COL_TICKER,
    COL_ZERO_VOLUME,
    COLUMN_LABELS,
    DATASETS,
    DISPARITY_WINDOW,
    ENTRY_MONTHS,
    FIELD_CALENDAR_YEARS,
    FIELD_CROSSCHECK,
    FIELD_ENTRIES,
    FIELD_ENTRY_INDICATORS,
    FIELD_EXCESS,
    FIELD_INDICATOR_CYCLES,
    FIELD_INDICATOR_SIGNALS,
    FIELD_INDICATOR_STATISTICS,
    FIELD_REPLACED,
    FIELD_STATISTICS,
    FIELD_TEST,
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
    TRACK_NAME,
    Dataset,
    IndicatorSignal,
)
from verify_lab.studies.halving_cycle.halving_calendar import (
    baseline_entries,
    calendar_returns,
    calendar_year_returns,
    exit_schedule,
    halving_entries,
)
from verify_lab.studies.halving_cycle.indicator_signals import entry_indicator_values, indicator_signal_returns
from verify_lab.studies.halving_cycle.indicators import daily_indicator_frame, monthly_indicator_frame
from verify_lab.studies.halving_cycle.price_series import replace_zero_volume_closes
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

# 2단계 지표통계의 값. **판정이 없어 기준선을 옆에 둔다** — 기준선은 방향 비율을 읽는 데 필요한 것만 싣는다
_INDICATOR_BASELINE_VALUES = [
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
    *_INDICATOR_BASELINE_VALUES,
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

    **2단계 측정만 쓴다** — 체결은 읽지 않으므로 `load_dataset` 에 넣지 않는다.

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


def _baseline_returns(frame: pd.DataFrame) -> pd.DataFrame:
    """기준선(첫 반감기부터 매일 진입 × 같은 보유)의 long-form 수익률을 낸다.

    Args:
        frame: 날짜 오름차순 시세

    Returns:
        매일 × 보유 행
    """
    trading_days = pd.DatetimeIndex(frame[COL_DATE])
    entries = baseline_entries(trading_days, HALVINGS[0].day)

    return calendar_returns(frame, exit_schedule(trading_days, entries, HOLD_MONTHS))


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
        }
        for field, table in tables.items():
            labelled = table.copy()
            labelled.insert(0, COL_TICKER, dataset.label)
            # **방향은 칸 표 셋에만 붙는다** — 성적표와 조인되는 표이고, 나머지는 칸이 아니다
            if field in (FIELD_STATISTICS, FIELD_EXCESS, FIELD_TEST):
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
        KEY_INDICATOR_RULE: _indicator_rule(INDICATOR_SIGNALS),
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
    }

    return {
        field: to_display_columns(
            table,
            COLUMN_LABELS,
            percent_columns=[column for column in PERCENT_COLUMNS if column in table.columns],
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
    "halving_records",
    "load_onchain",
    "load_dataset",
    "run_study",
    "signal_returns",
]
