"""등가성 검증 실행 — 축을 순회해 산출물을 조립한다

이 모듈은 **판정하지 않는다.** 합격선 대비 통과 여부만 표에 담고, "대체 가능한가"라는 결론은
사람이 `docs/research/원달러_ETF_등가성.md` 에 쓴다.

두 축을 모두 돌린다.

| 축 | 값 | 이유 |
| --- | --- | --- |
| 이론값 | 현물+금리차 / 현물+달러금리 | 사양서 §16.1 과 §2.1 이 서로 다른 식을 가리킨다 |
| 이상치 | 포함 / 제외 | 2019-03-14 의 종가 이상치 이틀이 회귀를 뒤집는다 |

**하나를 고르지 않는다.** 어느 쪽이 맞는지는 결과가 답한다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_VALUE, RATE_TO_PERCENT
from verify_lab.data.loader import load_market_csv, load_series_csv
from verify_lab.report.constants import DATE_FORMAT, PERCENT_DECIMALS
from verify_lab.studies.usdkrw_equivalence.alignment import align_to_etf_calendar, to_market_dates
from verify_lab.studies.usdkrw_equivalence.constants import (
    ALPHA_REFERENCE,
    ANNUAL_DRIFT_SPREAD_MAX,
    BETA_MAX,
    BETA_MIN,
    COL_ACTUAL_CUMULATIVE,
    COL_ACTUAL_RETURN,
    COL_DRIFT,
    COL_ETF_CLOSE,
    COL_NAV,
    COL_PREMIUM_ABS_MEAN,
    COL_PREMIUM_MAX,
    COL_PREMIUM_MEAN,
    COL_PREMIUM_MIN,
    COL_RATE_CONTRIBUTION,
    COL_SPOT_RETURN,
    COL_THEORETICAL_CUMULATIVE,
    COL_THEORETICAL_RETURN,
    COL_TRADING_DAYS,
    COL_YEAR,
    CORRELATION_MIN,
    DAILY_PERCENT_DECIMALS,
    DISPLAY_ACTUAL_DAILY,
    DISPLAY_ACTUAL_RETURN,
    DISPLAY_ALPHA_ANNUAL,
    DISPLAY_BETA,
    DISPLAY_CORRELATION,
    DISPLAY_DATE,
    DISPLAY_DRIFT,
    DISPLAY_DRIFT_SPREAD,
    DISPLAY_EFFECTIVE_COST,
    DISPLAY_EXPOSURE,
    DISPLAY_MODEL,
    DISPLAY_OUTLIER,
    DISPLAY_PASS,
    DISPLAY_PREMIUM_ABS_MEAN,
    DISPLAY_PREMIUM_MAX,
    DISPLAY_PREMIUM_MEAN,
    DISPLAY_PREMIUM_MIN,
    DISPLAY_PUBLISHED_TER,
    DISPLAY_R_SQUARED,
    DISPLAY_RATE_DAILY,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_SPOT,
    DISPLAY_SPOT_DAILY,
    DISPLAY_TER_GAP,
    DISPLAY_THEORETICAL_DAILY,
    DISPLAY_THEORETICAL_RETURN,
    DISPLAY_TICKER,
    DISPLAY_TRACKING_ERROR,
    DISPLAY_TRADING_DAYS,
    DISPLAY_YEAR,
    ETF_BASE,
    ETF_LEVERAGE,
    ETF_TARGETS,
    FAIL_MARK,
    KRW_RATE_PATH,
    LEVERAGE_ALPHA_MAX,
    LEVERAGE_ALPHA_MIN,
    LEVERAGE_BETA_MAX,
    LEVERAGE_BETA_MIN,
    LEVERAGE_R_SQUARED_MIN,
    MODEL_LABELS,
    OUTLIER_DATES,
    OUTLIER_LABEL_EXCLUDED,
    OUTLIER_LABEL_INCLUDED,
    PASS_MARK,
    RATIO_DECIMALS,
    SPOT_CLOSE,
    SPOT_SOURCES,
    TRACKING_ERROR_MAX,
    USD_RATE_PATH,
    EtfTarget,
    SpotSource,
    TheoreticalModel,
)
from verify_lab.studies.usdkrw_equivalence.effective_cost import build_adjusted_nav, build_cost_returns
from verify_lab.studies.usdkrw_equivalence.premium import annual_premium
from verify_lab.studies.usdkrw_equivalence.regression import annual_drift, fit_regression
from verify_lab.studies.usdkrw_equivalence.theoretical import build_returns
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# summary.json 키
KEY_STUDY = "study"
KEY_INPUTS = "inputs"
KEY_ALIGNMENT = "alignment"
KEY_ROW_COUNTS = "row_counts"
KEY_THRESHOLDS = "thresholds"
KEY_NOTES = "notes"

# 산출물만 보고는 알 수 없는 실행 조건
NOTE_MODELS = "이론값을 하나로 고르지 않았다. 사양서 §16.1 의 H₀(현물+금리차)와 §2.1 의 커버드 금리평형(현물+달러금리)이 서로 다른 식이라 둘 다 산출한다"
NOTE_OUTLIER = "2019-03-14·15 는 261240 의 종가가 NAV 대비 +21.85% 튄 날과 되돌아온 날이다. NAV 는 정상이었다. 포함·제외 두 벌을 모두 산출한다"
NOTE_ALPHA = "알파의 합격 판정을 붙이지 않았다. 사양서 §16.2 가 기준을 '총보수 근방'으로 적었는데 두 ETF 의 총보수가 아직 확인되지 않았다"
NOTE_RATE = "이자는 직전 거래일의 금리를 달력일 ÷ 365 로 일할한 값이다. 구간이 끝난 뒤 고시된 금리를 쓰면 미래를 참조한다"
NOTE_LP = "사양서 §16.4 의 LP 호가 스프레드는 일별 데이터로 측정할 수 없어 산출하지 않았다"
NOTE_COST = "실효 총비용은 분배금을 조정한 NAV 를 노출 배수 기준선에 회귀한 절편이다. 두 보정 중 하나라도 빠지면 값이 크게 틀린다"
NOTE_TER = "공시 총보수는 판정 기준이 아니라 측정값의 교차확인용이다. 출처와 조회 시점은 docs/spec/usdkrw_grid.md 에 있다"


@dataclass(frozen=True)
class EquivalenceOutputs:
    """실행 산출물

    Attributes:
        equivalence: 261240 대 이론값의 회귀 지표 (사양서 §16.2)
        annual_drift: 연도별 실제·이론 누적수익률과 괴리
        leverage: 261250 대 261240 의 회귀 지표 (사양서 §16.3)
        premium: 종목별·연도별 NAV 프리미엄 (사양서 §16.4)
        effective_cost: 종목별 실효 총비용과 공시 총보수 대조
        daily: 날짜별 원자료. 사용자가 손으로 검산하는 대상이다
        meta: 실행 파라미터와 핵심 수치
    """

    equivalence: pd.DataFrame
    annual_drift: pd.DataFrame
    leverage: pd.DataFrame
    premium: pd.DataFrame
    effective_cost: pd.DataFrame
    daily: pd.DataFrame
    meta: dict[str, Any]


@dataclass(frozen=True)
class _Series:
    """한 조합의 일간수익률

    Attributes:
        frame: 날짜별 실제·현물·이자·이론 수익률
        label: 이상치 축의 표시 이름
    """

    frame: pd.DataFrame
    label: str


def run_equivalence(
    models: Sequence[TheoreticalModel] = tuple(TheoreticalModel),
    sources: Sequence[SpotSource] = SPOT_SOURCES,
) -> EquivalenceOutputs:
    """등가성 검증을 실행해 산출물을 조립한다.

    Args:
        models: 산출할 이론값 모형. 기본값은 전부
        sources: 산출할 현물 환율 계열. 기본값은 전부

    Returns:
        산출물 묶음

    Raises:
        ValueError: 모형이나 환율 계열 목록이 비었거나, 입력 파일이 전제를 만족하지 않는 경우
        FileNotFoundError: 입력 파일이 없는 경우
    """
    if not models:
        raise ValueError("이론값 모형 목록이 비어 있습니다")

    if not sources:
        raise ValueError("환율 계열 목록이 비어 있습니다")

    krw_rate = load_series_csv(KRW_RATE_PATH)
    usd_rate = load_series_csv(USD_RATE_PATH)
    prices = {target.key: load_market_csv(target.price_path) for target in ETF_TARGETS}

    equivalence_rows: list[dict[str, Any]] = []
    drift_rows: list[pd.DataFrame] = []
    daily_blocks: list[pd.DataFrame] = []
    leverage_rows: list[dict[str, Any]] = []
    alignment_counts: dict[str, Any] = {}

    for source in sources:
        spot = _load_spot(source)
        aligned = {}
        for target in ETF_TARGETS:
            result = align_to_etf_calendar(prices[target.key], spot, krw_rate, usd_rate)
            aligned[target.key] = result.frame
            alignment_counts[f"{source.key}:{target.key}"] = result.counts

        for model in models:
            for variant in _variants(build_returns(aligned[ETF_BASE.key], model)):
                equivalence_rows.append(_equivalence_row(source, model, variant))
                drift_rows.append(_drift_frame(source, model, variant))
                if variant.label == OUTLIER_LABEL_INCLUDED:
                    daily_blocks.append(_daily_frame(source, model, variant))

        # 레버리지 회귀는 두 ETF 의 수익률만 쓰므로 환율 계열과 무관하다. 한 번만 낸다
        if source is sources[0]:
            leverage_rows = [
                _leverage_row(variant)
                for variant in _variants(_leverage_returns(aligned[ETF_BASE.key], aligned[ETF_LEVERAGE.key]))
            ]

    premium_rows = [_premium_frame(target) for target in ETF_TARGETS]

    # 실효 총비용은 **NAV 기준**이라 시장가의 프리미엄 잡음이 섞이지 않는다.
    # 환율 계열은 확정된 종가를 쓴다 (`docs/spec/usdkrw_grid.md` 결정 C15)
    cost_spot = _load_spot(SPOT_CLOSE)
    cost_rows = [_effective_cost_row(target, cost_spot, krw_rate, usd_rate) for target in ETF_TARGETS]

    equivalence = pd.DataFrame(equivalence_rows)
    drift = pd.concat(drift_rows, ignore_index=True)
    leverage = pd.DataFrame(leverage_rows)
    premium = pd.concat(premium_rows, ignore_index=True)
    effective_cost = pd.DataFrame(cost_rows)
    daily = pd.concat(daily_blocks, ignore_index=True)

    meta = {
        KEY_STUDY: "usdkrw_equivalence",
        KEY_INPUTS: {
            "spot": {source.key: str(source.path) for source in sources},
            "krw_rate": str(KRW_RATE_PATH),
            "usd_rate": str(USD_RATE_PATH),
            **{target.key: str(target.price_path) for target in ETF_TARGETS},
        },
        KEY_ALIGNMENT: alignment_counts,
        KEY_THRESHOLDS: {
            "correlation_min": CORRELATION_MIN,
            "beta_range": [BETA_MIN, BETA_MAX],
            "tracking_error_max": TRACKING_ERROR_MAX,
            "annual_drift_spread_max": ANNUAL_DRIFT_SPREAD_MAX,
            "alpha_reference": ALPHA_REFERENCE,
            "leverage_beta_range": [LEVERAGE_BETA_MIN, LEVERAGE_BETA_MAX],
            "leverage_alpha_range": [LEVERAGE_ALPHA_MIN, LEVERAGE_ALPHA_MAX],
            "leverage_r_squared_min": LEVERAGE_R_SQUARED_MIN,
        },
        KEY_ROW_COUNTS: {
            "equivalence": len(equivalence),
            "annual_drift": len(drift),
            "leverage": len(leverage),
            "premium": len(premium),
            "effective_cost": len(effective_cost),
            "daily": len(daily),
        },
        KEY_NOTES: [NOTE_MODELS, NOTE_OUTLIER, NOTE_ALPHA, NOTE_RATE, NOTE_LP, NOTE_COST, NOTE_TER],
    }

    logger.debug(f"등가성 검증 완료: 회귀 {len(equivalence)}행, 연도별 {len(drift)}행")

    return EquivalenceOutputs(
        equivalence=equivalence,
        annual_drift=drift,
        leverage=leverage,
        premium=premium,
        effective_cost=effective_cost,
        daily=daily,
        meta=meta,
    )


def _load_spot(source: SpotSource) -> pd.DataFrame:
    """현물 환율 계열을 읽고 필요하면 시장일 기준으로 옮긴다.

    매매기준율만 고시 시차 보정이 필요하다. 종가 계열은 그날 장의 값이라 옮기지 않는다.

    Args:
        source: 현물 환율 계열

    Returns:
        시장일 기준의 시계열
    """
    spot = load_series_csv(source.path)

    return to_market_dates(spot) if source.needs_publication_shift else spot


def _variants(returns: pd.DataFrame) -> list[_Series]:
    """이상치 포함본과 제외본을 만든다.

    **두 날을 모두 뺀다.** 급등일의 수익률과 되돌아온 날의 수익률이 각각 한 칸씩이므로,
    한쪽만 빼면 왜곡된 값이 남는다.

    Args:
        returns: 일간수익률 표

    Returns:
        포함본과 제외본
    """
    outliers = pd.to_datetime(list(OUTLIER_DATES))
    excluded = returns.loc[~returns[COL_DATE].isin(outliers)].reset_index(drop=True)

    return [_Series(returns, OUTLIER_LABEL_INCLUDED), _Series(excluded, OUTLIER_LABEL_EXCLUDED)]


def _equivalence_row(source: SpotSource, model: TheoreticalModel, variant: _Series) -> dict[str, Any]:
    """261240 대 이론값의 회귀 한 줄을 만든다.

    회귀는 **이론값을 설명변수, 실제를 종속변수**로 둔다. 사양서 §16.2 의 베타가
    "이론값 대비 실제가 얼마나 움직이는가"이기 때문이다.

    Args:
        source: 현물 환율 계열
        model: 이론값 모형
        variant: 이상치 축의 한 벌

    Returns:
        표 한 줄
    """
    frame = variant.frame
    fit = fit_regression(frame[COL_THEORETICAL_RETURN], frame[COL_ACTUAL_RETURN])
    drift = annual_drift(frame[COL_DATE], frame[COL_ACTUAL_RETURN], frame[COL_THEORETICAL_RETURN])

    passed = (
        fit.correlation >= CORRELATION_MIN
        and BETA_MIN <= fit.beta <= BETA_MAX
        and fit.tracking_error <= TRACKING_ERROR_MAX
        and drift.spread <= ANNUAL_DRIFT_SPREAD_MAX
    )

    return {
        DISPLAY_TICKER: ETF_BASE.ticker,
        DISPLAY_SPOT: source.label,
        DISPLAY_MODEL: MODEL_LABELS[model],
        DISPLAY_OUTLIER: variant.label,
        DISPLAY_SAMPLE_COUNT: fit.sample_count,
        DISPLAY_CORRELATION: round(fit.correlation, RATIO_DECIMALS),
        DISPLAY_BETA: round(fit.beta, RATIO_DECIMALS),
        DISPLAY_ALPHA_ANNUAL: _percent(fit.alpha_annual),
        DISPLAY_R_SQUARED: round(fit.r_squared, RATIO_DECIMALS),
        DISPLAY_TRACKING_ERROR: _percent(fit.tracking_error),
        DISPLAY_DRIFT_SPREAD: _percent(drift.spread),
        DISPLAY_PASS: PASS_MARK if passed else FAIL_MARK,
    }


def _drift_frame(source: SpotSource, model: TheoreticalModel, variant: _Series) -> pd.DataFrame:
    """연도별 괴리 표를 만든다.

    Args:
        source: 현물 환율 계열
        model: 이론값 모형
        variant: 이상치 축의 한 벌

    Returns:
        연도 수만큼의 행
    """
    frame = variant.frame
    drift = annual_drift(frame[COL_DATE], frame[COL_ACTUAL_RETURN], frame[COL_THEORETICAL_RETURN])
    table = drift.frame

    return pd.DataFrame(
        {
            DISPLAY_TICKER: ETF_BASE.ticker,
            DISPLAY_SPOT: source.label,
            DISPLAY_MODEL: MODEL_LABELS[model],
            DISPLAY_OUTLIER: variant.label,
            DISPLAY_YEAR: table[COL_YEAR],
            DISPLAY_TRADING_DAYS: table[COL_TRADING_DAYS],
            DISPLAY_ACTUAL_RETURN: table[COL_ACTUAL_CUMULATIVE].map(_percent),
            DISPLAY_THEORETICAL_RETURN: table[COL_THEORETICAL_CUMULATIVE].map(_percent),
            DISPLAY_DRIFT: table[COL_DRIFT].map(_percent),
        }
    )


def _leverage_returns(base: pd.DataFrame, leverage: pd.DataFrame) -> pd.DataFrame:
    """두 ETF 의 일간수익률을 같은 날짜에 맞춰 나란히 놓는다.

    이론값 모형과 무관하므로 아무 모형으로나 만들어도 실제 수익률은 같다.

    Args:
        base: 1배 ETF 의 정렬 결과
        leverage: 2배 ETF 의 정렬 결과

    Returns:
        날짜 · 1배 수익률(이론 칸에 담김) · 2배 수익률(실제 칸에 담김)

    Raises:
        ValueError: 겹치는 날이 없는 경우
    """
    base_returns = build_returns(base, TheoreticalModel.USD_RATE)[[COL_DATE, COL_ACTUAL_RETURN]]
    leverage_returns = build_returns(leverage, TheoreticalModel.USD_RATE)[[COL_DATE, COL_ACTUAL_RETURN]]

    merged = base_returns.merge(leverage_returns, on=COL_DATE, suffixes=("_base", "_leverage"))
    if merged.empty:
        raise ValueError("두 ETF 에 겹치는 거래일이 없습니다")

    # 이상치 필터와 회귀 함수를 그대로 재사용하려고 표준 컬럼 이름에 담는다
    return merged.rename(
        columns={
            f"{COL_ACTUAL_RETURN}_base": COL_THEORETICAL_RETURN,
            f"{COL_ACTUAL_RETURN}_leverage": COL_ACTUAL_RETURN,
        }
    )


def _leverage_row(variant: _Series) -> dict[str, Any]:
    """261250 대 261240 의 회귀 한 줄을 만든다 (사양서 §16.3).

    Args:
        variant: 이상치 축의 한 벌

    Returns:
        표 한 줄
    """
    frame = variant.frame
    fit = fit_regression(frame[COL_THEORETICAL_RETURN], frame[COL_ACTUAL_RETURN])

    passed = (
        LEVERAGE_BETA_MIN <= fit.beta <= LEVERAGE_BETA_MAX
        and LEVERAGE_ALPHA_MIN <= fit.alpha_annual <= LEVERAGE_ALPHA_MAX
        and fit.r_squared >= LEVERAGE_R_SQUARED_MIN
    )

    return {
        DISPLAY_TICKER: ETF_LEVERAGE.ticker,
        DISPLAY_OUTLIER: variant.label,
        DISPLAY_SAMPLE_COUNT: fit.sample_count,
        DISPLAY_CORRELATION: round(fit.correlation, RATIO_DECIMALS),
        DISPLAY_BETA: round(fit.beta, RATIO_DECIMALS),
        DISPLAY_ALPHA_ANNUAL: _percent(fit.alpha_annual),
        DISPLAY_R_SQUARED: round(fit.r_squared, RATIO_DECIMALS),
        DISPLAY_TRACKING_ERROR: _percent(fit.tracking_error),
        DISPLAY_PASS: PASS_MARK if passed else FAIL_MARK,
    }


def _premium_frame(target: EtfTarget) -> pd.DataFrame:
    """종목 하나의 연도별 NAV 프리미엄 표를 만든다.

    **원본가로 잰다.** 수정 종가는 분배금만큼 과거가 낮아져 있어 원본 기준인 NAV 와 비교하면
    그 조정폭이 통째로 디스카운트로 잡힌다 — 261240 에서 실제로 −1% 대의 가짜 디스카운트가 나온다.

    Args:
        target: 대상 ETF

    Returns:
        연도 수만큼의 행

    Raises:
        ValueError: 종가와 NAV 에 겹치는 날이 없는 경우
    """
    price = load_market_csv(target.raw_price_path)[[COL_DATE, COL_CLOSE]].rename(columns={COL_CLOSE: COL_ETF_CLOSE})
    nav = load_series_csv(target.nav_path).rename(columns={COL_VALUE: COL_NAV})
    merged = price.merge(nav, on=COL_DATE)

    if merged.empty:
        raise ValueError(f"종가와 NAV 에 겹치는 날이 없습니다: {target.ticker}")

    result = annual_premium(merged[COL_DATE], merged[COL_ETF_CLOSE], merged[COL_NAV])
    table = result.frame

    return pd.DataFrame(
        {
            DISPLAY_TICKER: target.ticker,
            DISPLAY_YEAR: table[COL_YEAR],
            DISPLAY_TRADING_DAYS: table[COL_TRADING_DAYS],
            DISPLAY_PREMIUM_MEAN: table[COL_PREMIUM_MEAN].map(_percent),
            DISPLAY_PREMIUM_ABS_MEAN: table[COL_PREMIUM_ABS_MEAN].map(_percent),
            DISPLAY_PREMIUM_MAX: table[COL_PREMIUM_MAX].map(_percent),
            DISPLAY_PREMIUM_MIN: table[COL_PREMIUM_MIN].map(_percent),
        }
    )


def _effective_cost_row(
    target: EtfTarget,
    spot: pd.DataFrame,
    krw_rate: pd.DataFrame,
    usd_rate: pd.DataFrame,
) -> dict[str, Any]:
    """종목 하나의 실효 총비용 한 줄을 만든다.

    **NAV 기준이고 노출 배수를 반영한 기준선을 쓴다.** 둘 중 하나만 빠져도 값이 크게 틀린다 —
    근거는 `effective_cost` 모듈 docstring 참고.

    이상치는 제외한다. 2019-03-14 는 **종가**가 튄 날이고 NAV 는 정상이었으므로 원칙적으로
    영향이 없지만, 다른 표와 표본을 맞춰 대조가 성립하게 한다.

    Args:
        target: 대상 ETF
        spot: 시장일 기준 환율
        krw_rate: 원화 금리
        usd_rate: 달러 금리

    Returns:
        표 한 줄
    """
    aligned = align_to_etf_calendar(build_adjusted_nav(target), spot, krw_rate, usd_rate).frame
    returns = build_cost_returns(aligned, target.exposure)
    outliers = pd.to_datetime(list(OUTLIER_DATES))
    returns = returns.loc[~returns[COL_DATE].isin(outliers)].reset_index(drop=True)

    fit = fit_regression(returns[COL_THEORETICAL_RETURN], returns[COL_ACTUAL_RETURN])
    effective_cost = -fit.alpha_annual

    return {
        DISPLAY_TICKER: target.ticker,
        DISPLAY_EXPOSURE: target.exposure,
        DISPLAY_SAMPLE_COUNT: fit.sample_count,
        DISPLAY_BETA: round(fit.beta, RATIO_DECIMALS),
        DISPLAY_R_SQUARED: round(fit.r_squared, RATIO_DECIMALS),
        DISPLAY_EFFECTIVE_COST: _percent(effective_cost),
        DISPLAY_PUBLISHED_TER: _percent(target.published_ter),
        DISPLAY_TER_GAP: _percent(effective_cost - target.published_ter),
    }


def _daily_frame(source: SpotSource, model: TheoreticalModel, variant: _Series) -> pd.DataFrame:
    """날짜별 원자료 표를 만든다.

    사용자가 차트와 대조해 손으로 검산하는 대상이므로 중간값(현물 변화·이자)을 함께 담는다.

    Args:
        source: 현물 환율 계열
        model: 이론값 모형
        variant: 이상치 축의 한 벌

    Returns:
        날짜 수만큼의 행
    """
    frame = variant.frame

    return pd.DataFrame(
        {
            DISPLAY_TICKER: ETF_BASE.ticker,
            DISPLAY_SPOT: source.label,
            DISPLAY_MODEL: MODEL_LABELS[model],
            DISPLAY_DATE: frame[COL_DATE].dt.strftime(DATE_FORMAT),
            DISPLAY_ACTUAL_DAILY: frame[COL_ACTUAL_RETURN].map(_daily_percent),
            DISPLAY_SPOT_DAILY: frame[COL_SPOT_RETURN].map(_daily_percent),
            DISPLAY_RATE_DAILY: frame[COL_RATE_CONTRIBUTION].map(_daily_percent),
            DISPLAY_THEORETICAL_DAILY: frame[COL_THEORETICAL_RETURN].map(_daily_percent),
        }
    )


def _percent(ratio: float) -> float:
    """비율을 저장용 백분율로 바꾼다.

    Args:
        ratio: 비율 (0.03 = 3%)

    Returns:
        백분율, 소수 둘째 자리
    """
    return round(float(ratio) * RATE_TO_PERCENT, PERCENT_DECIMALS)


def _daily_percent(ratio: float) -> float:
    """일간 값을 저장용 백분율로 바꾼다.

    집계표보다 자릿수가 깊다 — 일간 이자 기여분이 0.0x% 수준이라 두 자리로는 전부 0 이 된다.

    Args:
        ratio: 비율

    Returns:
        백분율, 소수 넷째 자리
    """
    return round(float(ratio) * RATE_TO_PERCENT, DAILY_PERCENT_DECIMALS)
