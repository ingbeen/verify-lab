"""검증 #8 실행 계층 — 전 쌍을 한 번에 산출한다

**나란히 놓고 보는 전제는 「파라미터가 같았다」** 이므로 쌍마다 따로 돌리지 않는다.
따로 돌리면 그 사실을 사람이 확인해야 하는데, 확인을 빠뜨려도 표는 정상으로 보인다.

산출물은 넷이다.

| 파일 | 내용 |
| --- | --- |
| `divergence.csv` | 쌍 × 구간 집계. 가장 먼저 볼 표다 |
| `breakdown.csv` | 쌍 × 구간 × 축(변동성·방향·시기) |
| `distribution.csv` | 분배금 몫과 배당 보정분 — 원본가로 재서 생긴 왜곡의 크기 |
| `full_period.csv` | 상장 후 전체 구간 1건. 표본 1건이라 통계가 아니라 사례다 |
| `windows_<티커>.csv` | 시작일 전체 목록 원자료. 사용자가 차트와 대조하는 자리다 |
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from verify_lab.common_constants import COL_DATE, MARKET_DIR, RATE_TO_PERCENT
from verify_lab.data.loader import load_market_csv
from verify_lab.measure.constants import COL_EXCLUDED_COUNT, COL_EXCLUDED_REASON, COL_HORIZON, REASON_OUT_OF_RANGE
from verify_lab.measure.distribution import (
    DistributionShare,
    dividend_adjustment,
    measure_distribution_share,
)
from verify_lab.report.constants import (
    DISPLAY_DATE,
    DISPLAY_EXCLUDED,
    DISPLAY_HORIZON,
    DISPLAY_SAMPLE_COUNT,
    EMPTY_MARK,
    PERCENT_DECIMALS,
)
from verify_lab.studies.leverage_tracking.breakdown import attach_axes, summarize_by_axis, summarize_by_horizon
from verify_lab.studies.leverage_tracking.constants import (
    COL_ACTUAL,
    COL_BASE_RETURN,
    COL_DIRECTION,
    COL_JUDGEABLE,
    COL_NAIVE_EXPECTED,
    COL_NON_OVERLAPPING_COUNT,
    COL_PATH_EFFECT,
    COL_PATH_IDEAL,
    COL_PERIOD,
    COL_PRODUCT_COST,
    COL_REALIZED_MULTIPLE,
    COL_SAMPLE_COUNT,
    COL_TOTAL_DIVERGENCE,
    COL_VOLATILITY_BUCKET,
    DISPLAY_ACTUAL,
    DISPLAY_ANNUAL_DISTRIBUTION,
    DISPLAY_AXIS,
    DISPLAY_AXIS_VALUE,
    DISPLAY_BASE_INDEX,
    DISPLAY_BASE_ONLY,
    DISPLAY_BASE_RETURN,
    DISPLAY_BASE_TICKER,
    DISPLAY_COMMON_DAYS,
    DISPLAY_DIRECTION_AXIS,
    DISPLAY_DISTRIBUTION_MEASURED,
    DISPLAY_DISTRIBUTION_PERIOD,
    DISPLAY_DIVIDEND_ADJUSTMENT,
    DISPLAY_END_DATE,
    DISPLAY_INDEX_NAME,
    DISPLAY_JUDGEABLE,
    DISPLAY_MULTIPLE,
    DISPLAY_NAIVE_EXPECTED,
    DISPLAY_NON_OVERLAPPING,
    DISPLAY_PATH_EFFECT,
    DISPLAY_PATH_IDEAL,
    DISPLAY_PERIOD_AXIS,
    DISPLAY_PRODUCT_COST,
    DISPLAY_PRODUCT_TYPE,
    DISPLAY_REALIZED_MULTIPLE,
    DISPLAY_REALIZED_MULTIPLE_COUNT,
    DISPLAY_START_DATE,
    DISPLAY_TARGET_ONLY,
    DISPLAY_TARGET_TICKER,
    DISPLAY_TOTAL_DIVERGENCE,
    DISPLAY_TOTAL_DIVERGENCE_P05,
    DISPLAY_TOTAL_DIVERGENCE_P95,
    DISPLAY_VOLATILITY_AXIS,
    HORIZON_LABELS,
    HORIZONS,
    PAIRS,
    LeveragePair,
)
from verify_lab.studies.leverage_tracking.divergence import compute_divergence
from verify_lab.studies.leverage_tracking.pairing import align_pair
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 축 컬럼과 그 표시 이름. 세 축을 한 표에 세로로 쌓는다
AXIS_COLUMNS = (
    (COL_VOLATILITY_BUCKET, DISPLAY_VOLATILITY_AXIS),
    (COL_DIRECTION, DISPLAY_DIRECTION_AXIS),
    (COL_PERIOD, DISPLAY_PERIOD_AXIS),
)

# 쌍을 식별하는 컬럼. 모든 표의 왼쪽에 같은 순서로 붙는다
IDENTITY_COLUMNS = [
    DISPLAY_INDEX_NAME,
    DISPLAY_BASE_TICKER,
    DISPLAY_TARGET_TICKER,
    DISPLAY_MULTIPLE,
    DISPLAY_PRODUCT_TYPE,
]

# 백분율로 바꿔 저장하는 집계 항목 (내부 컬럼 접미사 → 표시 이름)
SUMMARY_PERCENT_COLUMNS = [
    (f"{COL_PATH_EFFECT}Mean", f"{DISPLAY_PATH_EFFECT} 평균"),
    (f"{COL_PATH_EFFECT}Median", f"{DISPLAY_PATH_EFFECT} 중앙값"),
    (f"{COL_PRODUCT_COST}Mean", f"{DISPLAY_PRODUCT_COST} 평균"),
    (f"{COL_PRODUCT_COST}Median", f"{DISPLAY_PRODUCT_COST} 중앙값"),
    (f"{COL_TOTAL_DIVERGENCE}Mean", f"{DISPLAY_TOTAL_DIVERGENCE} 평균"),
    (f"{COL_TOTAL_DIVERGENCE}Median", f"{DISPLAY_TOTAL_DIVERGENCE} 중앙값"),
    (f"{COL_TOTAL_DIVERGENCE}P05", DISPLAY_TOTAL_DIVERGENCE_P05),
    (f"{COL_TOTAL_DIVERGENCE}P95", DISPLAY_TOTAL_DIVERGENCE_P95),
    (f"{COL_BASE_RETURN}Mean", f"{DISPLAY_BASE_RETURN} 평균"),
    (f"{COL_ACTUAL}Mean", f"{DISPLAY_ACTUAL} 평균"),
]

# 원자료에서 백분율로 바꿀 컬럼
WINDOW_PERCENT_COLUMNS = [
    (COL_BASE_RETURN, DISPLAY_BASE_RETURN),
    (COL_NAIVE_EXPECTED, DISPLAY_NAIVE_EXPECTED),
    (COL_PATH_IDEAL, DISPLAY_PATH_IDEAL),
    (COL_ACTUAL, DISPLAY_ACTUAL),
    (COL_PATH_EFFECT, DISPLAY_PATH_EFFECT),
    (COL_PRODUCT_COST, DISPLAY_PRODUCT_COST),
    (COL_TOTAL_DIVERGENCE, DISPLAY_TOTAL_DIVERGENCE),
]

# 실현 배수는 배수 자체라 백분율이 아니다. 자릿수만 맞춘다
REALIZED_MULTIPLE_DECIMALS = 3

# 축을 나누지 못한 칸의 표기. 빈칸으로 두면 «값이 없다»와 «못 나눴다»가 구별되지 않는다
AXIS_VALUE_UNAVAILABLE = "판정 불가"


@dataclass(frozen=True)
class StudyOutputs:
    """실행 산출물.

    Attributes:
        divergence: 쌍 × 구간 집계
        breakdown: 쌍 × 구간 × 축 집계
        distribution: 분배금 몫과 배당 보정분
        full_period: 상장 후 전체 구간 1건씩
        windows: 티커별 시작일 원자료
        pair_count: 실제로 잰 쌍 수
    """

    divergence: pd.DataFrame
    breakdown: pd.DataFrame
    distribution: pd.DataFrame
    full_period: pd.DataFrame
    windows: dict[str, pd.DataFrame]
    pair_count: int


def _identity(pair: LeveragePair) -> dict[str, str | float]:
    """쌍 식별 컬럼을 만든다.

    Args:
        pair: 측정 대상 짝

    Returns:
        식별 컬럼 dict
    """
    return {
        DISPLAY_INDEX_NAME: pair.index_name,
        DISPLAY_BASE_TICKER: pair.base_ticker,
        DISPLAY_TARGET_TICKER: pair.target_ticker,
        DISPLAY_MULTIPLE: pair.multiple,
        DISPLAY_PRODUCT_TYPE: pair.product_type,
    }


def _to_percent(frame: pd.DataFrame, columns: list[tuple[str, str]]) -> pd.DataFrame:
    """비율 컬럼을 백분율로 바꾸고 한글 이름을 붙인다.

    `measure` 계층은 비율(0~1)로 내고 저장 직전에만 백분율로 바꾼다는 규약을 따른다.

    Args:
        frame: 원본 프레임
        columns: (내부 컬럼, 표시 이름) 짝 목록

    Returns:
        백분율로 바뀐 새 프레임 조각
    """
    result = pd.DataFrame(index=frame.index)
    for source, display in columns:
        if source in frame.columns:
            result[display] = (frame[source] * RATE_TO_PERCENT).round(PERCENT_DECIMALS)

    return result


def _summary_block(summary: pd.DataFrame, pair: LeveragePair, extra: dict[str, str] | None = None) -> pd.DataFrame:
    """집계표를 저장용 한글 표로 바꾼다.

    Args:
        summary: `breakdown.summarize` 의 결과
        pair: 측정 대상 짝
        extra: 식별 컬럼 뒤에 덧붙일 컬럼 (축 이름 등)

    Returns:
        한글 헤더의 표시용 표
    """
    block = pd.DataFrame(index=summary.index)

    for column, value in _identity(pair).items():
        block[column] = value

    for column, value in (extra or {}).items():
        block[column] = value

    block[DISPLAY_HORIZON] = summary[COL_HORIZON].map(HORIZON_LABELS)
    block[DISPLAY_SAMPLE_COUNT] = summary[COL_SAMPLE_COUNT]
    block[DISPLAY_NON_OVERLAPPING] = summary[COL_NON_OVERLAPPING_COUNT]
    block[DISPLAY_EXCLUDED] = summary[COL_EXCLUDED_COUNT]
    block[DISPLAY_JUDGEABLE] = summary[COL_JUDGEABLE]

    block = pd.concat([block, _to_percent(summary, SUMMARY_PERCENT_COLUMNS)], axis=1)

    block[DISPLAY_REALIZED_MULTIPLE] = summary[f"{COL_REALIZED_MULTIPLE}Median"].round(REALIZED_MULTIPLE_DECIMALS)
    block[DISPLAY_REALIZED_MULTIPLE_COUNT] = summary[f"{COL_REALIZED_MULTIPLE}Count"]

    return block


def _full_period_row(
    pair: LeveragePair, alignment_frame: pd.DataFrame, base_only: int, target_only: int
) -> dict[str, object]:
    """상장 후 전체 구간을 한 줄로 낸다.

    **표본 1건이라 통계가 아니라 사례다.** 그래도 내는 이유는 "그래서 지금까지 총 얼마나
    벌어졌나"가 격자만으로는 안 보이기 때문이다.

    Args:
        pair: 측정 대상 짝
        alignment_frame: 공통 거래일 프레임
        base_only: 1배에만 있어 빠진 거래일 수
        target_only: 배수에만 있어 빠진 거래일 수

    Returns:
        전체 구간 한 줄
    """
    horizon = len(alignment_frame) - 1
    single = compute_divergence(alignment_frame, multiple=pair.multiple, horizons=(horizon,))
    first = single.iloc[0]

    row: dict[str, object] = {}
    row.update(_identity(pair))
    row[DISPLAY_BASE_INDEX] = pair.base_index
    row[DISPLAY_COMMON_DAYS] = len(alignment_frame)
    row[DISPLAY_START_DATE] = alignment_frame[COL_DATE].iloc[0].date()
    row[DISPLAY_END_DATE] = alignment_frame[COL_DATE].iloc[-1].date()
    row[DISPLAY_BASE_ONLY] = base_only
    row[DISPLAY_TARGET_ONLY] = target_only

    for source, display in WINDOW_PERCENT_COLUMNS:
        row[display] = round(float(first[source]) * RATE_TO_PERCENT, PERCENT_DECIMALS)

    return row


def _distribution_rows(
    pair: LeveragePair,
    base_share: DistributionShare,
    target_share: DistributionShare,
    horizons: tuple[int, ...],
) -> list[dict[str, object]]:
    """쌍의 배당 보정분을 구간마다 낸다.

    Args:
        pair: 측정 대상 짝
        base_share: 1배 상품의 분배 기여
        target_share: 배수 상품의 분배 기여
        horizons: 보유 기간 목록

    Returns:
        구간별 한 줄씩
    """
    rows: list[dict[str, object]] = []

    for horizon in horizons:
        row: dict[str, object] = {}
        row.update(_identity(pair))
        row[DISPLAY_HORIZON] = HORIZON_LABELS[horizon]
        row[f"1배 {DISPLAY_ANNUAL_DISTRIBUTION}"] = round(
            base_share.annual_contribution * RATE_TO_PERCENT, PERCENT_DECIMALS
        )
        row[f"배수 {DISPLAY_ANNUAL_DISTRIBUTION}"] = round(
            target_share.annual_contribution * RATE_TO_PERCENT, PERCENT_DECIMALS
        )
        row[DISPLAY_DIVIDEND_ADJUSTMENT] = round(
            dividend_adjustment(base_share, target_share, pair.multiple, horizon) * RATE_TO_PERCENT, PERCENT_DECIMALS
        )
        row[DISPLAY_DISTRIBUTION_MEASURED] = "예" if target_share.measured else "아니오 (ETN — 분배금 없음)"

        # 잰 구간을 밝힌다 — 국내는 수정주가 창이 짧아 원본가 전 기간을 못 덮는다
        if base_share.start_date is None or base_share.end_date is None:
            row[DISPLAY_DISTRIBUTION_PERIOD] = EMPTY_MARK
        else:
            row[DISPLAY_DISTRIBUTION_PERIOD] = f"{base_share.start_date.date()} ~ {base_share.end_date.date()}"
        rows.append(row)

    return rows


def _window_block(prepared: pd.DataFrame, pair: LeveragePair) -> pd.DataFrame:
    """시작일 원자료를 저장용 표로 바꾼다.

    **사용자가 차트와 대조하는 자리**이므로 구간이 데이터를 넘어간 행은 빼고 낸다 —
    값이 전부 빈 행은 대조할 것이 없고 파일만 키운다. 몇 건이 빠졌는지는 집계표에 있다.

    Args:
        prepared: 축이 붙은 괴리 결과
        pair: 측정 대상 짝

    Returns:
        한글 헤더의 원자료 표
    """
    valid = prepared.loc[prepared[COL_EXCLUDED_REASON] != REASON_OUT_OF_RANGE].copy()

    block = pd.DataFrame(index=valid.index)
    block[DISPLAY_TARGET_TICKER] = pair.target_ticker
    block[DISPLAY_MULTIPLE] = pair.multiple
    block[DISPLAY_DATE] = valid[COL_DATE].dt.date
    block[DISPLAY_HORIZON] = valid[COL_HORIZON].map(HORIZON_LABELS)

    block = pd.concat([block, _to_percent(valid, WINDOW_PERCENT_COLUMNS)], axis=1)

    block[DISPLAY_REALIZED_MULTIPLE] = valid[COL_REALIZED_MULTIPLE].round(REALIZED_MULTIPLE_DECIMALS)
    block[DISPLAY_VOLATILITY_AXIS] = valid[COL_VOLATILITY_BUCKET]
    block[DISPLAY_DIRECTION_AXIS] = valid[COL_DIRECTION]
    block[DISPLAY_PERIOD_AXIS] = valid[COL_PERIOD]

    return block.reset_index(drop=True)


def run_study(
    pairs: tuple[LeveragePair, ...] = PAIRS,
    horizons: tuple[int, ...] = HORIZONS,
    market_dir: Path = MARKET_DIR,
) -> StudyOutputs:
    """전 쌍의 괴리를 재고 산출물 표를 만든다.

    Args:
        pairs: 측정 대상 짝 목록
        horizons: 보유 기간 목록 (거래일)
        market_dir: 원시 시세 폴더

    Returns:
        산출물 표 묶음

    Raises:
        ValueError: 시세 파일이 없거나, 겹치는 거래일이 없는 경우
    """
    divergence_blocks: list[pd.DataFrame] = []
    breakdown_blocks: list[pd.DataFrame] = []
    distribution_rows: list[dict[str, object]] = []
    full_period_rows: list[dict[str, object]] = []
    windows: dict[str, pd.DataFrame] = {}

    # 분배 기여는 종목마다 한 번만 재고 재사용한다. 1배 종목은 여러 쌍이 공유한다
    share_cache: dict[str, DistributionShare] = {}

    def share_of(ticker: str) -> DistributionShare:
        """종목의 분배 기여를 캐시에서 꺼내거나 새로 잰다."""
        if ticker not in share_cache:
            share_cache[ticker] = measure_distribution_share(ticker, market_dir=market_dir)
        return share_cache[ticker]

    for pair in pairs:
        base = load_market_csv(market_dir / f"{pair.base_ticker}_max.csv")
        target = load_market_csv(market_dir / f"{pair.target_ticker}_max.csv")

        alignment = align_pair(base, target)
        divergence = compute_divergence(alignment.frame, multiple=pair.multiple, horizons=horizons)
        prepared = attach_axes(divergence, alignment.frame)

        divergence_blocks.append(_summary_block(summarize_by_horizon(prepared), pair))

        for axis_column, axis_label in AXIS_COLUMNS:
            axis_summary = summarize_by_axis(prepared, axis_column)
            block = _summary_block(axis_summary, pair, extra={DISPLAY_AXIS: axis_label})

            # 축 값은 구간 바로 앞에 둔다 — 「무엇으로 나눴는가」가 수치보다 왼쪽에 있어야 읽힌다.
            # 축 값이 비는 칸(변동성을 못 나눈 구간)은 빈칸이 아니라 사유로 채운다
            horizon_position = list(block.columns).index(DISPLAY_HORIZON)
            block.insert(horizon_position, DISPLAY_AXIS_VALUE, axis_summary[axis_column].fillna(AXIS_VALUE_UNAVAILABLE))
            breakdown_blocks.append(block)

        distribution_rows.extend(
            _distribution_rows(pair, share_of(pair.base_ticker), share_of(pair.target_ticker), horizons)
        )
        full_period_rows.append(
            _full_period_row(pair, alignment.frame, alignment.base_only_count, alignment.target_only_count)
        )
        windows[pair.target_ticker] = _window_block(prepared, pair)

        logger.debug(
            f"쌍 완료: {pair.base_ticker} → {pair.target_ticker} ({pair.multiple}배), 공통 {len(alignment.frame):,}일"
        )

    return StudyOutputs(
        divergence=pd.concat(divergence_blocks, ignore_index=True),
        breakdown=pd.concat(breakdown_blocks, ignore_index=True),
        distribution=pd.DataFrame(distribution_rows),
        full_period=pd.DataFrame(full_period_rows),
        windows=windows,
        pair_count=len(pairs),
    )


def headline(outputs: StudyOutputs) -> pd.DataFrame:
    """화면에 먼저 띄울 요약을 만든다.

    **총 괴리 평균이 아니라 두 분해 항목을 나란히** 보여준다. 이 검증의 답은 합계가 아니라
    "얼마가 음의 복리이고 얼마가 비용인가"이기 때문이다.

    Args:
        outputs: 실행 산출물

    Returns:
        구간별 요약 (판정 가능한 칸만)

    Raises:
        ValueError: 산출물이 비어 있는 경우
    """
    if outputs.divergence.empty:
        raise ValueError("산출물이 비어 있습니다")

    columns = [
        DISPLAY_TARGET_TICKER,
        DISPLAY_MULTIPLE,
        DISPLAY_HORIZON,
        DISPLAY_SAMPLE_COUNT,
        DISPLAY_NON_OVERLAPPING,
        f"{DISPLAY_PATH_EFFECT} 평균",
        f"{DISPLAY_PRODUCT_COST} 평균",
        f"{DISPLAY_TOTAL_DIVERGENCE} 평균",
        f"{DISPLAY_TOTAL_DIVERGENCE} 중앙값",
        DISPLAY_REALIZED_MULTIPLE,
    ]

    return outputs.divergence.loc[outputs.divergence[DISPLAY_JUDGEABLE] == "예", columns].reset_index(drop=True)
