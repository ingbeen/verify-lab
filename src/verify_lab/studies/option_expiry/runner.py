"""검증 #7 실행 — 만기일 매수 → 다음주 청산 매매를 재고 산출물을 조립한다

이 모듈은 **계산 규칙을 새로 만들지 않는다.** 만기일 달력과 offset 배정(`studies`),
forward return·통계·후보 판정(`measure`)이 이미 있으므로, 하는 일은 그것을 조합해 돌리고
사람이 읽을 형태로 쌓는 것이다.

**만기 창의 거래일을 하나도 빼지 않고 원자료로 남긴다.** 사용자가 차트로 직접 대조하는
산출물이므로 창을 좁혀 내지 않는다 (`docs/spec/option_expiry.md` 결정 ②).

**가격 기준 두 벌을 함께 돌린다.** 배당락이 만기일에 고정돼 있어 원본가에는 한 방향 편향이
들어가는데, 두 기준의 차이가 곧 그 몫이라 **차이 자체가 검산**이 된다(같은 문서 §3.4).

**자르는 것은 언제나 신호 선택이지 시세가 아니다.** 시기로 가를 때도 시세는 전 구간을
그대로 두고 신호일만 고른다 — 시세를 먼저 자르면 경계에서 만기 간격이 달라져 offset 이 어긋난다.
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE, MARKET_DIR
from verify_lab.data.loader import load_market_csv
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_EXCLUDED_REASON,
    COL_HORIZON,
    REASON_NONE,
)
from verify_lab.measure.forward_return import ReturnBasis, compute_forward_returns
from verify_lab.measure.screening import COL_HIT_RATE, COL_SCREEN, SCREEN_CANDIDATE, screen_candidates
from verify_lab.measure.statistics import (
    COL_DOWN_RATE_P_VALUE,
    COL_LOSS_RATE,
    COL_LOSS_RATE_EXCESS,
    COL_MEAN,
    COL_MEAN_EXCESS,
    COL_MEAN_P_VALUE,
    COL_MEDIAN_EXCESS,
    COL_MEDIAN_P_VALUE,
    COL_TEST_NOTE,
    COL_UP_RATE_P_VALUE,
    COL_WIN_RATE,
    COL_WIN_RATE_EXCESS,
    DEFAULT_RANDOM_SEED,
    DEFAULT_REPEAT_COUNT,
    excess,
    permutation_test,
    summarize,
)
from verify_lab.studies.option_expiry.constants import (
    COL_DAILY_RETURN,
    COL_EXIT_WEEKDAY,
    COL_EXPIRY_DATE,
    COL_EXPIRY_MONTH,
    COL_EXPIRY_MONTH_NUMBER,
    COL_HOLD_DAYS,
    COL_MEAN_RATE_CONFLICT,
    COL_MONTH_DAY_INDEX,
    COL_OFFSET,
    COL_PRICE_BASIS,
    COL_RULE_DATE,
    COL_TICKER,
    COL_TIME_HALF,
    DATASETS,
    DISPLAY_TIME_HALF_EARLY,
    DISPLAY_TIME_HALF_LATE,
    HALF_RATE,
    HORIZON_NEXT_WEEK_EXIT,
    MAX_OFFSET,
    MIN_SAMPLE_FOR_HALVES,
    WEEKDAY_LABELS,
    Dataset,
    PriceSeries,
)
from verify_lab.studies.option_expiry.expiry_calendar import monthly_expiry_dates
from verify_lab.studies.option_expiry.offsets import expiry_offsets
from verify_lab.studies.option_expiry.weekly_exit import (
    weekly_exit_returns,
    weekly_exit_schedule,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class StudyOutputs:
    """실행 산출물

    Attributes:
        expiries: 종목별 만기일 목록 (규칙일·만기일·앞당김)
        signals: 만기 창에 든 거래일 전체 목록 (사용자가 차트로 직접 대조하는 원자료)
        trade_signals: 만기일 매수 → 다음주 청산 매매의 신호일 원자료
        trade_summary: 그 매매의 묶음 집계와 보유 길이별 집계
        trade_excess: 두 기준선 대비 차이 — 같은 요일 주간 보유 · 같은 길이 단순 보유
        trade_test: 그 매매의 순열 검정
        trade_by_month: 만기월(1~12)별 집계와 같은 달 기준선
        trade_by_month_halves: 만기월 × 시기 앞뒤 절반 — 판정의 시기 항목을 재는 축
        candidates: 후보 판정 결과 — 전 칸의 1차 판정과 등급 (제외된 칸도 남는다)
        summary: 실행 파라미터와 핵심 수치
    """

    expiries: pd.DataFrame
    signals: pd.DataFrame
    trade_signals: pd.DataFrame
    trade_summary: pd.DataFrame
    trade_excess: pd.DataFrame
    trade_test: pd.DataFrame
    trade_by_month: pd.DataFrame
    trade_by_month_halves: pd.DataFrame
    candidates: pd.DataFrame
    summary: dict[str, Any]


@dataclass
class _Accumulator:
    """표별로 행을 모으는 자리"""

    expiries: list[pd.DataFrame] = field(default_factory=list)
    signals: list[pd.DataFrame] = field(default_factory=list)
    trade_signals: list[pd.DataFrame] = field(default_factory=list)
    trade_summary: list[pd.DataFrame] = field(default_factory=list)
    trade_excess: list[pd.DataFrame] = field(default_factory=list)
    trade_test: list[pd.DataFrame] = field(default_factory=list)
    trade_by_month: list[pd.DataFrame] = field(default_factory=list)
    trade_by_month_halves: list[pd.DataFrame] = field(default_factory=list)
    candidates: list[pd.DataFrame] = field(default_factory=list)


def _month_day_index(dates: pd.Series) -> pd.Series:
    """각 거래일이 그 달의 몇 번째 거래일인지 센다 (1부터).

    Args:
        dates: 오름차순 날짜 Series

    Returns:
        같은 인덱스의 정수 Series
    """
    month_key = dates.dt.to_period("M")

    return month_key.groupby(month_key).cumcount() + 1


def _annotate(df: pd.DataFrame, dataset: Dataset) -> tuple[pd.DataFrame, pd.DataFrame]:
    """시세에 만기일·offset·월중 서수·일간 등락을 붙인다.

    Args:
        df: 날짜 오름차순 시세
        dataset: 검증 대상 정의

    Returns:
        (만기일 목록, 부가 컬럼이 붙은 시세)
    """
    trading_days = pd.DatetimeIndex(df[COL_DATE])
    expiries = monthly_expiry_dates(trading_days, dataset.rule)
    assignment = expiry_offsets(trading_days, pd.DatetimeIndex(expiries[COL_EXPIRY_DATE]), MAX_OFFSET)

    annotated = df.merge(assignment.frame, on=COL_DATE, how="left")
    annotated[COL_MONTH_DAY_INDEX] = _month_day_index(annotated[COL_DATE])

    # 일간 등락은 앞날을 보지 않는다. 첫 행은 앞선 종가가 없어 비어 있는 것이 정상이다
    annotated[COL_DAILY_RETURN] = annotated[COL_CLOSE].pct_change()

    logger.debug(
        f"{dataset.ticker}: 거래일 {assignment.total_days:,}, 만기 {len(expiries):,}, "
        f"창 안 {assignment.assigned_count:,}, 겹침 {assignment.contested_count:,}, 동률 {assignment.tie_count:,}"
    )

    return expiries, annotated


def _count_labels(values: np.ndarray, labels: tuple[str, ...] | None = None) -> dict[str, int]:
    """정수 배열의 값별 건수를 세어 요약용 dict 로 만든다.

    `summary.json` 에 그대로 실리는 값이라 키는 문자열이고 정렬이 고정돼야 한다.
    `labels` 를 주면 값을 그 이름으로 바꾼다 (요일 번호 → 요일 이름).

    Args:
        values: 셀 정수 배열
        labels: 값을 이름으로 바꿀 목록. `None` 이면 숫자를 문자열로 쓴다

    Returns:
        값(또는 이름)별 건수. 값 오름차순
    """
    found, counts = np.unique(values, return_counts=True)

    return {
        (labels[int(value)] if labels is not None else str(int(value))): int(count)
        for value, count in zip(found, counts, strict=True)
    }


def _identify(frame: pd.DataFrame, **values: Any) -> pd.DataFrame:
    """표 앞머리에 식별 컬럼을 붙인다.

    Args:
        frame: 대상 표
        **values: 식별 컬럼 이름과 값

    Returns:
        식별 컬럼이 앞에 붙은 새 DataFrame
    """
    identified = frame.copy()
    for column, value in reversed(list(values.items())):
        identified.insert(0, column, value)

    return identified


def _run_series(
    dataset: Dataset,
    series: PriceSeries,
    accumulator: _Accumulator,
    *,
    repeats: int,
    seed: int,
) -> dict[str, Any]:
    """종목 하나의 가격 기준 하나를 전부 돌린다.

    Args:
        dataset: 검증 대상 정의
        series: 가격 기준 정의
        accumulator: 결과를 쌓는 자리
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        이 가격 기준의 요약 수치
    """
    df = load_market_csv(MARKET_DIR / series.file_name)
    expiries, annotated = _annotate(df, dataset)

    accumulator.expiries.append(_identify(expiries, **{COL_TICKER: dataset.ticker, COL_PRICE_BASIS: series.basis}))

    inside_window = annotated[COL_OFFSET].notna()

    # 신호일 원자료. 사용자가 차트로 직접 대조하는 산출물이라 창 안의 날을 하나도 빼지 않는다
    signal_columns = [COL_DATE, COL_CLOSE, COL_DAILY_RETURN, COL_EXPIRY_DATE, COL_OFFSET, COL_MONTH_DAY_INDEX]
    signals = annotated.loc[inside_window, signal_columns].copy()
    signals[COL_EXPIRY_MONTH] = signals[COL_EXPIRY_DATE].dt.strftime("%Y-%m")
    signals[COL_OFFSET] = signals[COL_OFFSET].astype(int)
    accumulator.signals.append(_identify(signals, **{COL_TICKER: dataset.ticker, COL_PRICE_BASIS: series.basis}))

    trade_records = _run_weekly_trade(df, dataset, series, expiries, accumulator, repeats=repeats, seed=seed)

    expiry_weekdays = pd.DatetimeIndex(expiries[COL_EXPIRY_DATE]).dayofweek
    return {
        "ticker": dataset.ticker,
        "price_basis": series.basis,
        "primary": series.primary,
        "file": series.file_name,
        "rows": len(df),
        "period": f"{df[COL_DATE].iloc[0].date()} ~ {df[COL_DATE].iloc[-1].date()}",
        "expiry_count": len(expiries),
        "advanced_count": int((expiries["advanced_days"] > 0).sum()),
        "inside_window_days": int(inside_window.sum()),
        # 만기일이 실제로 무슨 요일이었나. 미국은 셋째 금요일, 한국은 둘째 목요일이 규칙이지만
        # 휴장 앞당김으로 벗어나는 달이 있어 그 비율 자체가 보고 대상이다
        "expiry_weekdays": _count_labels(np.asarray(expiry_weekdays), WEEKDAY_LABELS),
        "weekly_trade": trade_records,
    }


# ============================================================
# 만기일 매수 → 다음주 청산
# ============================================================

# 초과분 표에서 어느 베이스라인과 견줬는지 밝히는 이름. 둘은 묻는 질문이 다르다
# (`docs/spec/option_expiry.md` §3.7)
COL_BASELINE = "baseline"
BASELINE_WEEKLY = "같은 요일 주간 보유"
BASELINE_MATCHED_LENGTH = "같은 길이 단순 보유"


def _weekly_trade_frames(
    df: pd.DataFrame,
    dataset: Dataset,
    expiries: pd.DataFrame,
    exit_weekday: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """매매 신호군과 「같은 요일 주간 보유」 베이스라인의 long-form 을 만든다.

    베이스라인은 **만기 규칙 요일에 해당하는 모든 거래일**(미국 금요일·한국 목요일)에서 같은
    달력 규칙으로 청산한 것이다. 보유 길이 분포가 신호와 같은 달력 구조에서 나오므로
    묶음 비교에 가중치를 지어낼 필요가 없다 (`docs/spec/option_expiry.md` 결정 ㉑).

    Args:
        df: 날짜 오름차순 시세
        dataset: 검증 대상 정의
        expiries: 만기일 표
        exit_weekday: 청산 목표 요일

    Returns:
        (신호군 long-form, 베이스라인 long-form)
    """
    trading_days = pd.DatetimeIndex(df[COL_DATE])

    signal_schedule = weekly_exit_schedule(
        trading_days,
        pd.DatetimeIndex(expiries[COL_EXPIRY_DATE]),
        pd.DatetimeIndex(expiries[COL_RULE_DATE]),
        exit_weekday=exit_weekday,
    )

    # 베이스라인은 만기가 아니므로 규칙일이 따로 없다. 진입일 자신이 주 기준일이다
    weekday_days = trading_days[trading_days.dayofweek == dataset.rule.weekday]
    baseline_schedule = weekly_exit_schedule(trading_days, weekday_days, weekday_days, exit_weekday=exit_weekday)

    signal = weekly_exit_returns(df, signal_schedule)
    baseline = weekly_exit_returns(df, baseline_schedule)

    return signal, baseline


def _per_length(frame: pd.DataFrame) -> pd.DataFrame:
    """묶음 표지를 실제 보유 거래일 수로 바꾼 유효 행만 남긴다.

    「같은 길이 단순 보유」와 견주려면 칸 축이 실제 보유일수여야 한다. 제외된 행은 보유일수가
    없어 어느 칸에도 속하지 못하므로 여기서 빠진다 — **제외 건수는 묶음 표와 신호일 원자료가
    담당한다.**

    Args:
        frame: `weekly_exit_returns` 의 결과

    Returns:
        보유일수를 구간 축으로 갖는 long-form
    """
    valid = frame[frame[COL_EXCLUDED_REASON] == REASON_NONE].copy()
    valid[COL_HORIZON] = valid[COL_HOLD_DAYS].astype(int)

    return valid


def _matched_length_baseline(market: pd.DataFrame, lengths: list[int]) -> pd.DataFrame:
    """전 거래일을 신호와 같은 보유 길이로 잡은 베이스라인을 만든다.

    종가 기준만 남긴다. 익일 시가 칸은 이 매매의 정의에 없고, 남겨두면 신호군과 칸 구성이
    달라져 기준선 대비 차이 계산이 성립하지 않는다.

    Args:
        market: 시세 전체
        lengths: 신호에 나타난 보유 거래일 수 목록

    Returns:
        길이별 칸을 갖는 long-form
    """
    every_day = pd.Series(True, index=market.index)
    baseline = compute_forward_returns(market, every_day, horizons=sorted(set(lengths)))

    return baseline[baseline[COL_BASIS] == ReturnBasis.CLOSE.value]


def _aggregate_by_month(
    signal: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    repeats: int,
    seed: int,
) -> pd.DataFrame:
    """만기월(1~12)별로 신호군과 같은 달 베이스라인을 나란히 낸다.

    **구간 축을 만기월로 빌려 `summarize`·`excess`·`permutation_test` 를 재사용한다.**
    통계량 정의를 두 곳에서 구현하면 두 곳이 조용히 갈라지기 때문이다. 축 이름은 돌려주기
    직전에 만기월로 바꾼다.

    같은 달 베이스라인이 반드시 필요하다 — 만기월별로 쪼개면 미국 세 ETF 모두 9월이 크게
    음수인데, 9월 약세는 옵션 만기와 무관하게 알려진 계절성이라 **같은 달과 견주지 않으면
    만기 효과와 가를 수 없다** (`docs/spec/option_expiry.md` 결정 ㉓).

    **검정을 함께 붙인다.** 이 축은 칸이 12개이고 칸당 표본이 수십 건이라, p 값 없이 내면
    가장 큰 칸을 골라 읽게 된다. 귀무분포는 **같은 달의 베이스라인**에서 뽑으므로 검정이
    묻는 것도 "그 달 안에서 만기 주가 특별한가" 이다.

    Args:
        signal: 신호군 long-form (유효 행)
        baseline: 같은 요일 주간 보유 베이스라인 long-form (유효 행)
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        만기월별 신호·베이스라인 집계와 초과분, 순열 검정
    """
    signal_by_month = signal.copy()
    signal_by_month[COL_HORIZON] = signal_by_month[COL_DATE].dt.month
    baseline_by_month = baseline.copy()
    baseline_by_month[COL_HORIZON] = baseline_by_month[COL_DATE].dt.month

    # 신호가 있는 달만 낸다. 베이스라인에만 있는 달을 남기면 초과분의 칸 구성이 어긋난다
    months = sorted(set(signal_by_month[COL_HORIZON].tolist()))
    baseline_by_month = baseline_by_month[baseline_by_month[COL_HORIZON].isin(months)]

    signal_summary = summarize(signal_by_month)
    baseline_summary = summarize(baseline_by_month)
    month_excess = excess(signal_summary, baseline_summary)
    month_test = permutation_test(signal_by_month, baseline_by_month, repeats=repeats, seed=seed)

    merged = (
        signal_summary.merge(baseline_summary, on=[COL_BASIS, COL_HORIZON], suffixes=("", "_baseline"))
        .merge(
            month_excess[
                [
                    COL_BASIS,
                    COL_HORIZON,
                    COL_MEAN_EXCESS,
                    COL_MEDIAN_EXCESS,
                    COL_WIN_RATE_EXCESS,
                    COL_LOSS_RATE_EXCESS,
                ]
            ],
            on=[COL_BASIS, COL_HORIZON],
        )
        .merge(
            month_test[
                [
                    COL_BASIS,
                    COL_HORIZON,
                    COL_MEAN_P_VALUE,
                    COL_MEDIAN_P_VALUE,
                    COL_UP_RATE_P_VALUE,
                    COL_DOWN_RATE_P_VALUE,
                    COL_TEST_NOTE,
                ]
            ],
            on=[COL_BASIS, COL_HORIZON],
        )
    )
    merged[COL_MEAN_RATE_CONFLICT] = _mean_rate_conflict(merged)

    return merged.rename(columns={COL_HORIZON: COL_EXPIRY_MONTH_NUMBER}).drop(columns=[COL_BASIS])


def _aggregate_month_halves(
    signal: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    repeats: int,
    seed: int,
) -> pd.DataFrame:
    """만기월별로 신호를 시간순 **앞뒤 절반**으로 갈라 방향 비율을 낸다.

    후보 판정의 **시기 항목**(시기를 쪼개도 방향이 유지되는가)을 재는 축이다.
    **달력 경계로 자르면 이 항목을 잴 수 없다** — 시장 구조가 바뀐 시점으로 나누면 칸마다
    표본이 4~17건으로 들쭉날쭉하고, 10건 미만 칸에는 검정이 붙지 않는다
    (측정의 원칙 12). 여기서는 신호를 시간순으로 세어 균등하게 갈라 양쪽 표본을 맞춘다.

    **절반으로 갈랐을 때 한쪽이라도 검정 하한에 못 미치는 달은 내지 않는다.** 쪼갤 수 없다는
    사실 자체가 결과이며, 억지로 쪼개 숫자를 만드는 것이 더 나쁘다.

    Args:
        signal: 신호군 long-form (유효 행)
        baseline: 같은 요일 주간 보유 베이스라인 long-form (유효 행)
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        만기월 × 앞뒤 절반 집계. 쪼갤 수 없는 달은 행이 없다
    """
    blocks: list[pd.DataFrame] = []
    months = sorted(set(signal[COL_DATE].dt.month.tolist()))

    for month in months:
        month_signal = signal[signal[COL_DATE].dt.month == month].sort_values(COL_DATE)
        if len(month_signal) < MIN_SAMPLE_FOR_HALVES:
            continue

        month_baseline = baseline[baseline[COL_DATE].dt.month == month]
        boundary = month_signal[COL_DATE].iloc[len(month_signal) // 2]
        halves = (
            (DISPLAY_TIME_HALF_EARLY, month_signal[COL_DATE] < boundary, month_baseline[COL_DATE] < boundary),
            (DISPLAY_TIME_HALF_LATE, month_signal[COL_DATE] >= boundary, month_baseline[COL_DATE] >= boundary),
        )
        for label, signal_mask, baseline_mask in halves:
            # **구간 축을 만기월로 덮어쓴다.** 입력은 보유일수를 축으로 갖고 있어(`_per_length`)
            # 그대로 집계하면 한 달이 보유일수별로 쪼개져 앞뒤 표본이 어긋난다.
            # `_aggregate_by_month` 와 같은 관용이다
            half_signal = month_signal[signal_mask].assign(**{COL_HORIZON: month})
            half_baseline = month_baseline[baseline_mask].assign(**{COL_HORIZON: month})
            if half_signal.empty or half_baseline.empty:
                continue

            summary = summarize(half_signal)
            test = permutation_test(half_signal, half_baseline, repeats=repeats, seed=seed)
            merged = summary.merge(
                test[[COL_BASIS, COL_HORIZON, COL_UP_RATE_P_VALUE, COL_DOWN_RATE_P_VALUE, COL_TEST_NOTE]],
                on=[COL_BASIS, COL_HORIZON],
            )
            merged[COL_EXPIRY_MONTH_NUMBER] = month
            merged[COL_TIME_HALF] = label
            blocks.append(merged.drop(columns=[COL_BASIS, COL_HORIZON]))

    if not blocks:
        return pd.DataFrame()

    return pd.concat(blocks, ignore_index=True)


def _mean_rate_conflict(frame: pd.DataFrame) -> pd.Series:
    """평균의 부호와 방향 비율이 어긋나는 칸을 표시한다 (측정의 원칙 13).

    평균이 양수인데 절반 넘게 내렸다면 **소수의 큰 사건이 평균을 만든 것**이고, 그 반대도 같다.
    평균만 보고 방향을 읽으면 이런 칸에서 정반대로 판단하게 된다.

    Args:
        frame: 평균과 두 방향 비율이 들어 있는 집계 프레임

    Returns:
        어긋나는 칸이면 True 인 Series
    """
    mean_up_but_fell = (frame[COL_MEAN] > 0) & (frame[COL_LOSS_RATE] > HALF_RATE)
    mean_down_but_rose = (frame[COL_MEAN] < 0) & (frame[COL_WIN_RATE] > HALF_RATE)

    return mean_up_but_fell | mean_down_but_rose


def _run_weekly_trade(
    df: pd.DataFrame,
    dataset: Dataset,
    series: PriceSeries,
    expiries: pd.DataFrame,
    accumulator: _Accumulator,
    *,
    repeats: int,
    seed: int,
) -> list[dict[str, Any]]:
    """만기일 매수 → 다음주 청산 매매를 청산 요일마다 전부 돌린다.

    Args:
        df: 날짜 오름차순 시세
        dataset: 검증 대상 정의
        series: 가격 기준 정의
        expiries: 만기일 표
        accumulator: 결과를 쌓는 자리
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        청산 요일별 요약 수치
    """
    records: list[dict[str, Any]] = []

    for exit_weekday in dataset.exit_weekdays:
        exit_label = WEEKDAY_LABELS[exit_weekday]
        identity = {COL_TICKER: dataset.ticker, COL_PRICE_BASIS: series.basis, COL_EXIT_WEEKDAY: exit_label}

        signal, baseline = _weekly_trade_frames(df, dataset, expiries, exit_weekday)

        # 신호일 원자료. 진입·청산 가격과 날짜를 전부 남겨 사용자가 차트로 대조한다 (측정의 원칙 8)
        raw = signal.copy()
        raw[COL_EXPIRY_MONTH_NUMBER] = raw[COL_DATE].dt.month
        accumulator.trade_signals.append(_identify(raw.drop(columns=[COL_BASIS, COL_HORIZON]), **identity))

        # 시기 2등분은 **전 구간의 신호를 시간순으로** 갈라야 의미가 있다
        halves = _aggregate_month_halves(_per_length(signal), _per_length(baseline), repeats=repeats, seed=seed)
        if not halves.empty:
            accumulator.trade_by_month_halves.append(_identify(halves, **identity))

        # 후보 판정은 **전체 시기 · 만기월 축**에서만 낸다. 달력 경계로 자른 칸은 표본이
        # 수십 건이라 우연확률이 성립하지 않고, 시기 축과 역할이 겹친다
        by_month = _aggregate_by_month(_per_length(signal), _per_length(baseline), repeats=repeats, seed=seed)
        accumulator.candidates.append(
            _identify(
                screen_candidates(by_month, halves, axis_column=COL_EXPIRY_MONTH_NUMBER),
                **identity,
            )
        )

        accumulator.trade_by_month.append(_identify(by_month, **identity))

        # 매매 하나의 묶음 성적. **시기 축 말고는 쪼개지 않는다** — 달력 경계로 자른 칸은
        # 표본이 수십 건이라 판정력이 없고, 시기 2등분이 같은 질문에 더 균등한 표본으로 답한다
        _record_trade_cell(signal, baseline, df, identity, accumulator, repeats=repeats, seed=seed)

        valid = signal[signal[COL_EXCLUDED_REASON] == REASON_NONE]
        records.append(
            {
                "exit_weekday": exit_label,
                "entry_count": len(signal),
                "excluded_count": len(signal) - len(valid),
                "hold_days": _count_labels(valid[COL_HOLD_DAYS].to_numpy(dtype=int)),
                "baseline_entry_count": len(baseline),
            }
        )

    return records


def _record_trade_cell(
    sliced: pd.DataFrame,
    weekly_baseline: pd.DataFrame,
    market: pd.DataFrame,
    row_identity: dict[str, Any],
    accumulator: _Accumulator,
    *,
    repeats: int,
    seed: int,
) -> None:
    """매매 하나의 집계·기준선 대비 차이·검정을 쌓는다.

    **묶음 비교와 길이별 비교의 베이스라인이 다르다** (`docs/spec/option_expiry.md` 결정 ㉑).
    묶음은 「같은 요일 주간 보유」와만 견준다 — 보유 길이가 섞인 묶음을 길이 매칭 베이스라인과
    견주려면 표본 수를 부풀리는 가중이 필요한데, 그러면 보고되는 베이스라인 표본 수가 거짓이 된다.
    길이 매칭은 **길이별 칸에서만** 정확히 성립한다.

    Args:
        sliced: 이 칸의 신호군 long-form
        weekly_baseline: 「같은 요일 주간 보유」 long-form
        market: 시세 전체
        row_identity: 식별 컬럼 값
        accumulator: 결과를 쌓는 자리
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드
    """
    # 1. 묶음 — 이 매매 하나의 성적이다
    accumulator.trade_summary.append(_identify(summarize(sliced), **row_identity))

    pooled_excess = excess(summarize(sliced), summarize(weekly_baseline))
    accumulator.trade_excess.append(_identify(pooled_excess, **{**row_identity, COL_BASELINE: BASELINE_WEEKLY}))

    pooled_test = permutation_test(sliced, weekly_baseline, repeats=repeats, seed=seed)
    accumulator.trade_test.append(_identify(pooled_test, **{**row_identity, COL_BASELINE: BASELINE_WEEKLY}))

    # 2. 보유 길이별 — 여기서만 「같은 길이 단순 보유」와 정확히 견줄 수 있다
    per_length = _per_length(sliced)
    if per_length.empty:
        return

    lengths = sorted({int(value) for value in per_length[COL_HORIZON]})
    length_baseline = _matched_length_baseline(market, lengths)

    accumulator.trade_summary.append(_identify(summarize(per_length), **row_identity))
    length_excess = excess(summarize(per_length), summarize(length_baseline))
    accumulator.trade_excess.append(_identify(length_excess, **{**row_identity, COL_BASELINE: BASELINE_MATCHED_LENGTH}))

    length_test = permutation_test(per_length, length_baseline, repeats=repeats, seed=seed)
    accumulator.trade_test.append(_identify(length_test, **{**row_identity, COL_BASELINE: BASELINE_MATCHED_LENGTH}))


def run_study(
    datasets: tuple[Dataset, ...] = DATASETS,
    *,
    repeats: int = DEFAULT_REPEAT_COUNT,
    seed: int = DEFAULT_RANDOM_SEED,
) -> StudyOutputs:
    """검증 #7 을 실행하고 산출물을 조립한다.

    Args:
        datasets: 검증 대상 목록
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        실행 산출물

    Raises:
        ValueError: 대상 목록이 빈 경우
    """
    if not datasets:
        raise ValueError("검증 대상이 하나도 없습니다")

    accumulator = _Accumulator()
    series_summaries: list[dict[str, Any]] = []

    for dataset in datasets:
        for series in dataset.series:
            series_summaries.append(_run_series(dataset, series, accumulator, repeats=repeats, seed=seed))

    summary: dict[str, Any] = {
        "max_offset": MAX_OFFSET,
        "permutation_repeats": repeats,
        "permutation_seed": seed,
        "series": series_summaries,
    }

    outputs = StudyOutputs(
        expiries=_concat(accumulator.expiries),
        signals=_concat(accumulator.signals),
        trade_signals=_concat(accumulator.trade_signals),
        trade_summary=_concat(accumulator.trade_summary),
        trade_excess=_concat(accumulator.trade_excess),
        trade_test=_concat(accumulator.trade_test),
        trade_by_month=_concat(accumulator.trade_by_month),
        trade_by_month_halves=_concat(accumulator.trade_by_month_halves),
        candidates=_concat(accumulator.candidates),
        summary=summary,
    )

    summary["row_counts"] = {
        "expiries": len(outputs.expiries),
        "signals": len(outputs.signals),
        "trade_signals": len(outputs.trade_signals),
        "trade_summary": len(outputs.trade_summary),
        "trade_excess": len(outputs.trade_excess),
        "trade_test": len(outputs.trade_test),
        "trade_by_month": len(outputs.trade_by_month),
        "trade_by_month_halves": len(outputs.trade_by_month_halves),
        "candidates": len(outputs.candidates),
    }

    return outputs


def _concat(blocks: list[pd.DataFrame]) -> pd.DataFrame:
    """모아둔 표 조각을 하나로 잇는다.

    Args:
        blocks: 표 조각 목록

    Returns:
        이어붙인 DataFrame (조각이 없으면 빈 DataFrame)
    """
    if not blocks:
        return pd.DataFrame()

    return pd.concat(blocks, ignore_index=True)


def trade_headline(outputs: StudyOutputs) -> pd.DataFrame:
    """본검증 기준·전체 월의 매매 묶음 성적을 뽑는다.

    보유 길이별 칸은 빼고 **묶음 칸만** 남긴다 — 사용자가 물은 것은 매매 하나의 성적이다.

    Args:
        outputs: 실행 산출물

    Returns:
        종목 × 청산 요일의 요약표
    """
    summary = outputs.trade_summary
    if summary.empty:
        return summary

    primary_bases = {row["price_basis"] for row in outputs.summary["series"] if row["primary"]}
    selected = summary[summary[COL_PRICE_BASIS].isin(primary_bases) & (summary[COL_HORIZON] == HORIZON_NEXT_WEEK_EXIT)]

    return selected.reset_index(drop=True)


__all__ = ["StudyOutputs", "candidates_headline", "run_study", "trade_headline"]


def candidates_headline(outputs: StudyOutputs) -> pd.DataFrame:
    """본검증 기준의 **후보 칸만** 적중률 내림차순으로 뽑는다.

    제외된 칸은 산출물에 그대로 남기되 화면에는 내지 않는다 — 화면은 "지금 볼 것"을 위한
    자리이고, 전 칸은 `candidates.csv` 가 만기월 순서로 답한다.

    **정렬이 여기 있는 이유**: 판정 계층(`measure`)은 축을 모르므로 무엇을 먼저 보여줄지
    정할 수 없다. 동률이 흔해(적중률이 표본의 분수라 값이 겹친다) **안정 정렬**을 써서
    같은 적중률 안에서는 종목·만기월 순서가 유지되게 한다.

    Args:
        outputs: 실행 산출물

    Returns:
        후보 칸만 남긴 판정표. 하나도 없으면 빈 표
    """
    candidates = outputs.candidates
    if candidates.empty:
        return candidates

    primary_bases = {row["price_basis"] for row in outputs.summary["series"] if row["primary"]}
    selected = candidates[
        candidates[COL_PRICE_BASIS].isin(primary_bases) & (candidates[COL_SCREEN] == SCREEN_CANDIDATE)
    ]

    return selected.sort_values(COL_HIT_RATE, ascending=False, kind="stable").reset_index(drop=True)
