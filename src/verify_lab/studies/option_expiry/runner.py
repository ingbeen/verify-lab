"""검증 #7 실행 — 만기 기준 상대 거래일을 전부 돌고 산출물을 조립한다

이 모듈은 **계산 규칙을 새로 만들지 않는다.** 만기일 달력과 offset 배정(`studies`),
forward return 과 통계(`measure`)가 이미 있으므로, 하는 일은 그것을 조합해 돌리고
사람이 읽을 형태로 쌓는 것이다.

**한 실행에서 offset 전 범위를 돌린다.** 하나를 골라 내는 순간 측정이 아니라 과최적화가 되고,
문헌이 말하는 "만기 1주 전"은 정의에 따라 부호가 뒤집히므로 전부 나란히 놓아야 판단할 수 있다
(`docs/spec/option_expiry.md` 결정 ②).

**가격 기준 두 벌을 함께 돌린다.** 배당락이 만기일에 고정돼 있어 원본가에는 한 방향 편향이
들어가는데, 두 기준의 차이가 곧 그 몫이라 **차이 자체가 검산**이 된다(같은 문서 §3.4).

**자르는 것은 언제나 신호 선택이지 시세가 아니다.** 국면·위칭으로 자를 때도 시세는 전 구간을
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
from verify_lab.measure.statistics import (
    COL_DOWN_RATE_P_VALUE,
    COL_LOSS_RATE,
    COL_LOSS_RATE_EXCESS,
    COL_MEAN,
    COL_MEAN_EXCESS,
    COL_MEAN_P_VALUE,
    COL_MEDIAN,
    COL_MEDIAN_EXCESS,
    COL_MEDIAN_P_VALUE,
    COL_SAMPLE_COUNT,
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
    COL_REGIME,
    COL_RULE_DATE,
    COL_TICKER,
    COL_TIME_HALF,
    COL_WITCHING,
    DATASETS,
    DISPLAY_TIME_HALF_EARLY,
    DISPLAY_TIME_HALF_LATE,
    HALF_RATE,
    HORIZON_NEXT_WEEK_EXIT,
    MAX_OFFSET,
    MIN_SAMPLE_FOR_HALVES,
    OFFSET_HORIZONS,
    REGIME_ALL,
    WEEKDAY_LABELS,
    WITCHING_GROUPS,
    Dataset,
    PriceSeries,
    Regime,
    WitchingGroup,
)
from verify_lab.studies.option_expiry.expiry_calendar import monthly_expiry_dates
from verify_lab.studies.option_expiry.offsets import expiry_offsets
from verify_lab.studies.option_expiry.weekly_exit import (
    HolidayExit,
    weekly_exit_returns,
    weekly_exit_schedule,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 산출물의 식별 컬럼. 모든 표 앞머리에 같은 순서로 붙어 조합을 되짚을 수 있게 한다
IDENTITY_COLUMNS = [COL_TICKER, COL_PRICE_BASIS, COL_REGIME, COL_WITCHING, COL_OFFSET]

# 순열 검정을 돌릴 범위. 국면·위칭까지 곱하면 검정 수가 수천 건이 되는데, 그렇게 쪼갠 칸은
# 표본이 수십 건이라 검정의 검정력이 없다. **전체 국면·전체 월에서만** 돌리고 나머지 축은
# 표본 수·평균·중앙값·승률로 보고한다 — 무엇을 안 돌렸는지 요약에 남긴다
PERMUTATION_REGIME = REGIME_ALL.label
PERMUTATION_WITCHING = WITCHING_GROUPS[0].label


@dataclass(frozen=True)
class StudyOutputs:
    """실행 산출물

    Attributes:
        expiries: 종목별 만기일 목록 (규칙일·만기일·앞당김)
        signals: 만기 창에 든 거래일 전체 목록 (사용자가 차트로 직접 대조하는 원자료)
        daily: offset 별 일간 등락 집계
        month_position: 월중 서수별 일간 등락 집계 (offset 과 구별되는지 보는 대조축)
        forward: offset 앵커 × 구간 forward return 집계
        excess: 단순 보유(같은 국면 전 거래일) 대비 초과분
        test: 순열 검정
        trade_signals: 만기일 매수 → 다음주 청산 매매의 신호일 원자료
        trade_summary: 그 매매의 묶음 집계 (국면 × 만기 종류)
        trade_excess: 두 베이스라인 대비 초과분 — 같은 요일 주간 보유 · 같은 길이 단순 보유
        trade_test: 그 매매의 순열 검정
        trade_by_month: 만기월(1~12)별 집계와 같은 달 베이스라인
        trade_by_month_halves: 만기월 × 시기 앞뒤 절반 — 후보 판정 기준 4 를 재는 축
        trade_rule_variants: 휴장 처리 규칙 네 조합의 대조
        summary: 실행 파라미터와 핵심 수치
    """

    expiries: pd.DataFrame
    signals: pd.DataFrame
    daily: pd.DataFrame
    month_position: pd.DataFrame
    forward: pd.DataFrame
    excess: pd.DataFrame
    test: pd.DataFrame
    trade_signals: pd.DataFrame
    trade_summary: pd.DataFrame
    trade_excess: pd.DataFrame
    trade_test: pd.DataFrame
    trade_by_month: pd.DataFrame
    trade_by_month_halves: pd.DataFrame
    trade_rule_variants: pd.DataFrame
    summary: dict[str, Any]


@dataclass
class _Accumulator:
    """표별로 행을 모으는 자리"""

    expiries: list[pd.DataFrame] = field(default_factory=list)
    signals: list[pd.DataFrame] = field(default_factory=list)
    daily: list[pd.DataFrame] = field(default_factory=list)
    month_position: list[pd.DataFrame] = field(default_factory=list)
    forward: list[pd.DataFrame] = field(default_factory=list)
    excess: list[pd.DataFrame] = field(default_factory=list)
    test: list[pd.DataFrame] = field(default_factory=list)
    trade_signals: list[pd.DataFrame] = field(default_factory=list)
    trade_summary: list[pd.DataFrame] = field(default_factory=list)
    trade_excess: list[pd.DataFrame] = field(default_factory=list)
    trade_test: list[pd.DataFrame] = field(default_factory=list)
    trade_by_month: list[pd.DataFrame] = field(default_factory=list)
    trade_by_month_halves: list[pd.DataFrame] = field(default_factory=list)
    trade_rule_variants: list[pd.DataFrame] = field(default_factory=list)


def _month_day_index(dates: pd.Series) -> pd.Series:
    """각 거래일이 그 달의 몇 번째 거래일인지 센다 (1부터).

    Args:
        dates: 오름차순 날짜 Series

    Returns:
        같은 인덱스의 정수 Series
    """
    month_key = dates.dt.to_period("M")

    return month_key.groupby(month_key).cumcount() + 1


def _regime_mask(dates: pd.Series, regime: Regime) -> pd.Series:
    """국면 구간에 드는 날을 True 로 표시한다.

    Args:
        dates: 날짜 Series
        regime: 국면 정의

    Returns:
        같은 인덱스의 bool Series
    """
    mask = pd.Series(True, index=dates.index)
    if regime.start is not None:
        mask &= dates >= pd.Timestamp(regime.start)
    if regime.end is not None:
        mask &= dates <= pd.Timestamp(regime.end)

    return mask


def _witching_mask(expiry_months: pd.Series, group: WitchingGroup) -> pd.Series:
    """동시만기 축에 드는 날을 True 로 표시한다.

    만기월은 **배정된 만기일의 달**이지 그 날짜의 달이 아니다. 만기 다음 달로 넘어간 날도
    자기가 붙은 만기의 성격을 따라야 한다.

    Args:
        expiry_months: 배정된 만기일의 월 (정수)
        group: 위칭 축 정의

    Returns:
        같은 인덱스의 bool Series
    """
    if group.months is None:
        return pd.Series(True, index=expiry_months.index)

    inside = expiry_months.isin(group.months)

    return ~inside if group.exclude else inside


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


def _aggregate_daily(frame: pd.DataFrame, group_column: str) -> pd.DataFrame:
    """일간 등락을 지정한 축으로 집계한다.

    Args:
        frame: 일간 등락이 붙은 시세 조각
        group_column: 집계 축 컬럼

    Returns:
        축·표본수·평균·중앙값·승률을 담은 DataFrame
    """
    usable = frame[frame[COL_DAILY_RETURN].notna()].copy()
    if usable.empty:
        return pd.DataFrame(
            {
                group_column: pd.Series(dtype="int64"),
                COL_SAMPLE_COUNT: pd.Series(dtype="int64"),
                COL_MEAN: pd.Series(dtype="float64"),
                COL_MEDIAN: pd.Series(dtype="float64"),
                COL_WIN_RATE: pd.Series(dtype="float64"),
            }
        )

    # 축을 **프레임 안의 컬럼으로** 만든 뒤 이름으로 묶는다. 바깥 Series 로 묶으면 집계 결과에
    # 축 컬럼이 남지 않아, 행이 무엇에 대한 값인지 알 수 없는 표가 조용히 나온다
    usable[group_column] = usable[group_column].astype(int)

    return usable.groupby(group_column, as_index=False, sort=True).agg(
        **{
            COL_SAMPLE_COUNT: (COL_DAILY_RETURN, "size"),
            COL_MEAN: (COL_DAILY_RETURN, "mean"),
            COL_MEDIAN: (COL_DAILY_RETURN, "median"),
            # 승률은 양수 비율이다. 정확히 0인 날은 승리가 아니다
            COL_WIN_RATE: (COL_DAILY_RETURN, lambda values: float((values > 0).mean())),
        }
    )


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
    expiry_months = annotated[COL_EXPIRY_DATE].dt.month

    # 신호일 원자료. 사용자가 차트로 직접 대조하는 산출물이라 창 안의 날을 하나도 빼지 않는다
    signal_columns = [COL_DATE, COL_CLOSE, COL_DAILY_RETURN, COL_EXPIRY_DATE, COL_OFFSET, COL_MONTH_DAY_INDEX]
    signals = annotated.loc[inside_window, signal_columns].copy()
    signals[COL_EXPIRY_MONTH] = signals[COL_EXPIRY_DATE].dt.strftime("%Y-%m")
    signals[COL_OFFSET] = signals[COL_OFFSET].astype(int)
    accumulator.signals.append(_identify(signals, **{COL_TICKER: dataset.ticker, COL_PRICE_BASIS: series.basis}))

    for regime in dataset.regimes:
        regime_mask = _regime_mask(annotated[COL_DATE], regime)

        # 월중 서수 대조는 만기 종류와 무관하므로 국면마다 한 번만 낸다
        month_table = _aggregate_daily(annotated[regime_mask], COL_MONTH_DAY_INDEX)
        accumulator.month_position.append(
            _identify(
                month_table,
                **{COL_TICKER: dataset.ticker, COL_PRICE_BASIS: series.basis, COL_REGIME: regime.label},
            )
        )

        for group in WITCHING_GROUPS:
            selected = regime_mask & _witching_mask(expiry_months, group)
            identity = {
                COL_TICKER: dataset.ticker,
                COL_PRICE_BASIS: series.basis,
                COL_REGIME: regime.label,
                COL_WITCHING: group.label,
            }

            daily_table = _aggregate_daily(annotated[selected & inside_window], COL_OFFSET)
            accumulator.daily.append(_identify(daily_table, **identity))

            _run_forward(
                annotated,
                selected=selected,
                inside_window=inside_window,
                regime_mask=regime_mask,
                identity=identity,
                accumulator=accumulator,
                repeats=repeats,
                seed=seed,
            )

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


def _run_forward(
    annotated: pd.DataFrame,
    *,
    selected: pd.Series,
    inside_window: pd.Series,
    regime_mask: pd.Series,
    identity: dict[str, Any],
    accumulator: _Accumulator,
    repeats: int,
    seed: int,
) -> None:
    """offset 앵커별 forward return·초과분·검정을 낸다.

    베이스라인은 **같은 국면의 전 거래일**(단순 보유)이다. 신호일이 베이스라인에 포함되므로
    초과분은 "이 위치가 평소보다 얼마나 나은가"를 뜻한다 — 검증 #1 의 단순 보유와 같은 정의다.

    **만기 창 밖을 베이스라인으로 쓰지 않는다.** offset 범위가 ±10 이라 창이 한 달을 거의 다
    덮고, 남는 날은 전 거래일의 5% 뿐이다. 그 5%는 연휴로 만기 간격이 비정상적으로 길었던 달에서만
    나오는 치우친 표본이라, 그것과 견주면 평균 0.004% 짜리 칸까지 유의하게 나온다
    (`docs/spec/option_expiry.md` 결정 ⑮).

    국면마다 베이스라인을 다시 만든다. 전 기간 한 벌을 돌려쓰면 초과분의 차이에
    "그 사이 시장이 어땠는가"가 섞여, 국면 분할이 신호가 아니라 시장을 재게 된다.

    Args:
        annotated: 부가 컬럼이 붙은 시세 전체
        selected: 국면·위칭 축으로 고른 날
        inside_window: 만기 창에 든 날
        regime_mask: 국면 구간에 든 날
        identity: 식별 컬럼 값
        accumulator: 결과를 쌓는 자리
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드
    """
    market = annotated
    baseline_frame = compute_forward_returns(market, regime_mask, horizons=OFFSET_HORIZONS)
    baseline_summary = summarize(baseline_frame)

    run_test = identity[COL_REGIME] == PERMUTATION_REGIME and identity[COL_WITCHING] == PERMUTATION_WITCHING

    for offset in range(-MAX_OFFSET, MAX_OFFSET + 1):
        signals = selected & inside_window & (annotated[COL_OFFSET] == offset)
        if not signals.any():
            continue

        signal_frame = compute_forward_returns(market, signals, horizons=OFFSET_HORIZONS)
        signal_summary = summarize(signal_frame)

        row_identity = {**identity, COL_OFFSET: offset}
        accumulator.forward.append(_identify(signal_summary, **row_identity))
        accumulator.excess.append(_identify(excess(signal_summary, baseline_summary), **row_identity))

        if run_test:
            test = permutation_test(signal_frame, baseline_frame, repeats=repeats, seed=seed)
            accumulator.test.append(_identify(test, **row_identity))


# ============================================================
# 만기일 매수 → 다음주 청산
# ============================================================

# 초과분 표에서 어느 베이스라인과 견줬는지 밝히는 이름. 둘은 묻는 질문이 다르다
# (`docs/spec/option_expiry.md` §3.7)
COL_BASELINE = "baseline"
BASELINE_WEEKLY = "같은 요일 주간 보유"
BASELINE_MATCHED_LENGTH = "같은 길이 단순 보유"

# 휴장 처리 규칙 대조에서 쓰는 축 이름 (결정 ㉔)
COL_WEEK_ANCHOR = "week_anchor"
COL_HOLIDAY_RULE = "holiday_rule"
ANCHOR_RULE_DATE = "규칙일 기준"
ANCHOR_EXPIRY_DATE = "실제 만기일 기준"


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


def _matched_length_baseline(market: pd.DataFrame, regime_mask: pd.Series, lengths: list[int]) -> pd.DataFrame:
    """같은 국면의 전 거래일을 신호와 같은 보유 길이로 잡은 베이스라인을 만든다.

    종가 기준만 남긴다. 익일 시가 칸은 이 매매의 정의에 없고, 남겨두면 신호군과 칸 구성이
    달라져 초과분 계산이 성립하지 않는다.

    Args:
        market: 시세 전체
        regime_mask: 국면 구간에 든 날
        lengths: 신호에 나타난 보유 거래일 수 목록

    Returns:
        길이별 칸을 갖는 long-form
    """
    baseline = compute_forward_returns(market, regime_mask, horizons=sorted(set(lengths)))

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

    후보 판정 기준 4(시기를 쪼개도 방향이 유지되는가)를 재는 축이다.
    **국면(`Regime`) 축으로는 이 기준을 잴 수 없다** — 국면은 시장 구조가 바뀐 달력 시점으로
    나눈 것이라 칸마다 표본이 4~17건으로 들쭉날쭉하고, 10건 미만 칸에는 검정이 붙지 않는다
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


def _rule_variants(df: pd.DataFrame, expiries: pd.DataFrame, exit_weekday: int) -> pd.DataFrame:
    """휴장 처리 규칙 네 조합의 묶음 성적을 낸다 (결정 ㉔).

    주 기준(규칙일 / 실제 만기일) × 청산 휴장(직전 거래일 / 다음 거래일)이다.
    **규칙 선택이 결론을 만들지 않았다는 것 자체가 근거**이므로 네 값이 다 있어야 한다.

    네 조합 모두 같은 `weekly_exit_schedule` 을 호출한다 — 청산 규칙을 두 벌 구현하면
    두 곳이 조용히 갈라진다.

    Args:
        df: 날짜 오름차순 시세
        expiries: 만기일 표
        exit_weekday: 청산 목표 요일

    Returns:
        네 조합의 집계
    """
    trading_days = pd.DatetimeIndex(df[COL_DATE])
    entries = pd.DatetimeIndex(expiries[COL_EXPIRY_DATE])
    anchors = {
        ANCHOR_RULE_DATE: pd.DatetimeIndex(expiries[COL_RULE_DATE]),
        ANCHOR_EXPIRY_DATE: entries,
    }

    blocks: list[pd.DataFrame] = []
    for anchor_label, references in anchors.items():
        for on_holiday in HolidayExit:
            schedule = weekly_exit_schedule(
                trading_days, entries, references, exit_weekday=exit_weekday, on_holiday=on_holiday
            )
            summary = summarize(weekly_exit_returns(df, schedule))
            blocks.append(_identify(summary, **{COL_WEEK_ANCHOR: anchor_label, COL_HOLIDAY_RULE: on_holiday.value}))

    return pd.concat(blocks, ignore_index=True)


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

        accumulator.trade_rule_variants.append(_identify(_rule_variants(df, expiries, exit_weekday), **identity))

        # 시기 2등분은 **전 구간의 신호를 시간순으로** 갈라야 의미가 있으므로 국면 루프 밖에서 낸다
        halves = _aggregate_month_halves(_per_length(signal), _per_length(baseline), repeats=repeats, seed=seed)
        if not halves.empty:
            accumulator.trade_by_month_halves.append(_identify(halves, **identity))

        expiry_months = signal[COL_DATE].dt.month
        for regime in dataset.regimes:
            regime_signal = signal[_regime_mask(signal[COL_DATE], regime)]
            regime_baseline = baseline[_regime_mask(baseline[COL_DATE], regime)]
            if regime_signal.empty:
                continue

            # 만기월 축은 만기 종류와 무관하므로 국면마다 한 번만 낸다
            accumulator.trade_by_month.append(
                _identify(
                    _aggregate_by_month(
                        _per_length(regime_signal), _per_length(regime_baseline), repeats=repeats, seed=seed
                    ),
                    **{**identity, COL_REGIME: regime.label},
                )
            )

            for group in WITCHING_GROUPS:
                selected = _regime_mask(signal[COL_DATE], regime) & _witching_mask(expiry_months, group)
                sliced = signal[selected]
                if sliced.empty:
                    continue

                row_identity = {**identity, COL_REGIME: regime.label, COL_WITCHING: group.label}
                run_test = regime.label == PERMUTATION_REGIME and group.label == PERMUTATION_WITCHING

                _record_trade_cell(
                    sliced,
                    regime_baseline,
                    df,
                    _regime_mask(df[COL_DATE], regime),
                    row_identity,
                    accumulator,
                    repeats=repeats,
                    seed=seed,
                    run_test=run_test,
                )

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
    regime_baseline: pd.DataFrame,
    market: pd.DataFrame,
    regime_mask: pd.Series,
    row_identity: dict[str, Any],
    accumulator: _Accumulator,
    *,
    repeats: int,
    seed: int,
    run_test: bool,
) -> None:
    """한 칸(국면 × 만기 종류)의 집계·초과분·검정을 쌓는다.

    **묶음 비교와 길이별 비교의 베이스라인이 다르다** (`docs/spec/option_expiry.md` 결정 ㉑).
    묶음은 「같은 요일 주간 보유」와만 견준다 — 보유 길이가 섞인 묶음을 길이 매칭 베이스라인과
    견주려면 표본 수를 부풀리는 가중이 필요한데, 그러면 보고되는 베이스라인 표본 수가 거짓이 된다.
    길이 매칭은 **길이별 칸에서만** 정확히 성립한다.

    Args:
        sliced: 이 칸의 신호군 long-form
        regime_baseline: 같은 국면의 「같은 요일 주간 보유」 long-form
        market: 시세 전체
        regime_mask: 국면 구간에 든 날
        row_identity: 식별 컬럼 값
        accumulator: 결과를 쌓는 자리
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드
        run_test: 순열 검정을 돌릴지 여부
    """
    # 1. 묶음 — 이 매매 하나의 성적이다
    accumulator.trade_summary.append(_identify(summarize(sliced), **row_identity))

    pooled_excess = excess(summarize(sliced), summarize(regime_baseline))
    accumulator.trade_excess.append(_identify(pooled_excess, **{**row_identity, COL_BASELINE: BASELINE_WEEKLY}))

    if run_test:
        pooled_test = permutation_test(sliced, regime_baseline, repeats=repeats, seed=seed)
        accumulator.trade_test.append(_identify(pooled_test, **{**row_identity, COL_BASELINE: BASELINE_WEEKLY}))

    # 2. 보유 길이별 — 여기서만 「같은 길이 단순 보유」와 정확히 견줄 수 있다
    per_length = _per_length(sliced)
    if per_length.empty:
        return

    lengths = sorted({int(value) for value in per_length[COL_HORIZON]})
    length_baseline = _matched_length_baseline(market, regime_mask, lengths)

    accumulator.trade_summary.append(_identify(summarize(per_length), **row_identity))
    length_excess = excess(summarize(per_length), summarize(length_baseline))
    accumulator.trade_excess.append(_identify(length_excess, **{**row_identity, COL_BASELINE: BASELINE_MATCHED_LENGTH}))

    if run_test:
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
        "horizons": list(OFFSET_HORIZONS),
        "permutation_repeats": repeats,
        "permutation_seed": seed,
        "permutation_scope": f"국면 「{PERMUTATION_REGIME}」 · 만기 종류 「{PERMUTATION_WITCHING}」 에서만 실행",
        "series": series_summaries,
    }

    outputs = StudyOutputs(
        expiries=_concat(accumulator.expiries),
        signals=_concat(accumulator.signals),
        daily=_concat(accumulator.daily),
        month_position=_concat(accumulator.month_position),
        forward=_concat(accumulator.forward),
        excess=_concat(accumulator.excess),
        test=_concat(accumulator.test),
        trade_signals=_concat(accumulator.trade_signals),
        trade_summary=_concat(accumulator.trade_summary),
        trade_excess=_concat(accumulator.trade_excess),
        trade_test=_concat(accumulator.trade_test),
        trade_by_month=_concat(accumulator.trade_by_month),
        trade_by_month_halves=_concat(accumulator.trade_by_month_halves),
        trade_rule_variants=_concat(accumulator.trade_rule_variants),
        summary=summary,
    )

    summary["row_counts"] = {
        "expiries": len(outputs.expiries),
        "signals": len(outputs.signals),
        "daily": len(outputs.daily),
        "month_position": len(outputs.month_position),
        "forward": len(outputs.forward),
        "excess": len(outputs.excess),
        "test": len(outputs.test),
        "trade_signals": len(outputs.trade_signals),
        "trade_summary": len(outputs.trade_summary),
        "trade_excess": len(outputs.trade_excess),
        "trade_test": len(outputs.trade_test),
        "trade_by_month": len(outputs.trade_by_month),
        "trade_by_month_halves": len(outputs.trade_by_month_halves),
        "trade_rule_variants": len(outputs.trade_rule_variants),
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


def headline_table(outputs: StudyOutputs) -> pd.DataFrame:
    """본검증 기준·전체 국면·전체 월의 offset 별 일간 등락을 뽑는다.

    Args:
        outputs: 실행 산출물

    Returns:
        종목 × offset 의 요약표
    """
    daily = outputs.daily
    primary_bases = {row["price_basis"] for row in outputs.summary["series"] if row["primary"]}

    selected = daily[
        daily[COL_PRICE_BASIS].isin(primary_bases)
        & (daily[COL_REGIME] == PERMUTATION_REGIME)
        & (daily[COL_WITCHING] == PERMUTATION_WITCHING)
    ]

    return selected.reset_index(drop=True)


def basis_gap(outputs: StudyOutputs) -> pd.DataFrame:
    """같은 칸에서 수정주가와 원본가의 평균이 얼마나 갈리는지 낸다.

    **차이가 곧 배당락 몫**이라 이 표 자체가 가격 기준 선택의 검산이 된다.

    Args:
        outputs: 실행 산출물

    Returns:
        종목 × offset 의 두 기준 평균과 그 차이
    """
    daily = outputs.daily
    selected = daily[(daily[COL_REGIME] == PERMUTATION_REGIME) & (daily[COL_WITCHING] == PERMUTATION_WITCHING)]

    pivot = selected.pivot_table(
        index=[COL_TICKER, COL_OFFSET], columns=COL_PRICE_BASIS, values=COL_MEAN, aggfunc="first"
    ).reset_index()
    bases = [column for column in pivot.columns if column not in (COL_TICKER, COL_OFFSET)]
    if len(bases) == 2:
        pivot["gap"] = pivot[bases[0]] - pivot[bases[1]]

    return pivot


def trade_headline(outputs: StudyOutputs) -> pd.DataFrame:
    """본검증 기준·전체 국면·전체 월의 매매 묶음 성적을 뽑는다.

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
    selected = summary[
        summary[COL_PRICE_BASIS].isin(primary_bases)
        & (summary[COL_REGIME] == PERMUTATION_REGIME)
        & (summary[COL_WITCHING] == PERMUTATION_WITCHING)
        & (summary[COL_HORIZON] == HORIZON_NEXT_WEEK_EXIT)
    ]

    return selected.reset_index(drop=True)


__all__ = ["StudyOutputs", "basis_gap", "headline_table", "run_study", "trade_headline"]
