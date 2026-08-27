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

import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE, MARKET_DIR
from verify_lab.data.loader import load_market_csv
from verify_lab.measure.forward_return import compute_forward_returns
from verify_lab.measure.statistics import (
    COL_MEAN,
    COL_MEDIAN,
    COL_SAMPLE_COUNT,
    COL_WIN_RATE,
    DEFAULT_RANDOM_SEED,
    DEFAULT_REPEAT_COUNT,
    excess,
    permutation_test,
    summarize,
)
from verify_lab.studies.option_expiry.constants import (
    COL_DAILY_RETURN,
    COL_EXPIRY_DATE,
    COL_EXPIRY_MONTH,
    COL_MONTH_DAY_INDEX,
    COL_OFFSET,
    COL_PRICE_BASIS,
    COL_REGIME,
    COL_TICKER,
    COL_WITCHING,
    DATASETS,
    MAX_OFFSET,
    OFFSET_HORIZONS,
    REGIME_ALL,
    WITCHING_GROUPS,
    Dataset,
    PriceSeries,
    Regime,
    WitchingGroup,
)
from verify_lab.studies.option_expiry.expiry_calendar import monthly_expiry_dates
from verify_lab.studies.option_expiry.offsets import expiry_offsets
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
        summary: 실행 파라미터와 핵심 수치
    """

    expiries: pd.DataFrame
    signals: pd.DataFrame
    daily: pd.DataFrame
    month_position: pd.DataFrame
    forward: pd.DataFrame
    excess: pd.DataFrame
    test: pd.DataFrame
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


__all__ = ["StudyOutputs", "basis_gap", "headline_table", "run_study"]
