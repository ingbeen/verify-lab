"""축 분해와 집계 — 전체 합계 하나로 끝내지 않는다

**반대 방향의 두 칸은 합치면 사라진다.** 경로 효과는 변동성이 클수록 커지고 방향에 따라
부호가 갈리므로, 전체 평균만 내면 서로 다른 국면이 상쇄돼 아무것도 안 보인다
(루트 `CLAUDE.md` 측정의 원칙 12).

세 축으로 쪼갠다.

| 축 | 나누는 기준 | 왜 |
| --- | --- | --- |
| 변동성 | 구간 **안**의 1배 일간 변동성 사분위 | 경로 효과는 변동성의 함수다 |
| 방향 | 구간 1배 수익률의 부호 | 배수 상품은 오를 때와 내릴 때가 대칭이 아니다 |
| 시기 | 금리 국면 (2022년 경계) | 차입·스왑 비용이 금리에 연동된다 |

**비중첩 표본 수를 모든 칸에 함께 낸다.** 롤링 전수는 이웃끼리 심하게 겹치므로 표본 수만
적으면 실제보다 훨씬 단단해 보인다. 겹치지 않게 뽑을 수 있는 최대 개수를 그리디로 정확히 센다.

칸당 유효 표본이 하한에 못 미치면 **행을 지우지 않고** `판정가능` 을 「아니오」로 적는다 —
행이 사라지면 그 칸을 못 봤다는 사실 자체를 사용자가 모른다 (측정의 원칙 17).
"""

from collections.abc import Sequence

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.measure.constants import COL_EXCLUDED_COUNT, COL_EXCLUDED_REASON, COL_HORIZON, REASON_OUT_OF_RANGE
from verify_lab.studies.leverage_tracking.constants import (
    COL_ACTUAL,
    COL_BASE_CLOSE,
    COL_BASE_RETURN,
    COL_DIRECTION,
    COL_JUDGEABLE,
    COL_NON_OVERLAPPING_COUNT,
    COL_PATH_EFFECT,
    COL_PERIOD,
    COL_PRODUCT_COST,
    COL_REALIZED_MULTIPLE,
    COL_SAMPLE_COUNT,
    COL_START_POSITION,
    COL_TOTAL_DIVERGENCE,
    COL_VOLATILITY_BUCKET,
    DIRECTION_DOWN,
    DIRECTION_FLAT,
    DIRECTION_UP,
    JUDGEABLE_NO,
    JUDGEABLE_YES,
    MIN_SAMPLE_PER_CELL,
    PERIOD_CUTOFF,
    PERIOD_HIGH_RATE,
    PERIOD_LOW_RATE,
    VOLATILITY_BUCKETS,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 평균과 중앙값을 나란히 내는 항목. 둘이 벌어지면 소수 사건이 평균을 만들었다는 신호다
# (루트 `CLAUDE.md` 측정의 원칙 4)
MEAN_MEDIAN_COLUMNS = [COL_PATH_EFFECT, COL_PRODUCT_COST, COL_TOTAL_DIVERGENCE, COL_BASE_RETURN, COL_ACTUAL]

# 분포의 양 끝. 평균만 보면 «최악에 얼마나 벌어졌나»를 알 수 없다
TAIL_QUANTILES = (0.05, 0.95)


def attach_axes(divergence: pd.DataFrame, alignment: pd.DataFrame) -> pd.DataFrame:
    """분해 축과 시작일 위치를 붙인다.

    변동성은 구간 **안**의 1배 일간 수익률 표준편차이며, 구간마다 창 길이가 다르므로
    구간별로 따로 계산한다. 사분위 경계도 **구간별로** 매긴다 — 1주와 3년의 변동성을
    한 자로 재면 긴 구간이 전부 한쪽 사분위에 몰린다.

    Args:
        divergence: `divergence.compute_divergence` 의 결과
        alignment: 그 계산에 쓴 `pairing.align_pair` 의 공통 거래일 프레임

    Returns:
        입력에 `StartPosition`·`VolatilityBucket`·`Direction`·`Period` 를 더한 DataFrame.
        입력은 변경하지 않는다

    Raises:
        ValueError: 필요한 컬럼이 없거나, 두 입력의 날짜가 어긋나는 경우
    """
    missing_columns = {COL_DATE, COL_HORIZON, COL_BASE_RETURN, COL_EXCLUDED_REASON} - set(divergence.columns)
    if missing_columns:
        raise ValueError(f"괴리 결과에 필수 컬럼이 없습니다: {sorted(missing_columns)}")

    if COL_BASE_CLOSE not in alignment.columns:
        raise ValueError(f"정렬 프레임에 필수 컬럼이 없습니다: {COL_BASE_CLOSE}")

    result = divergence.copy()

    # 1. 시작일을 거래일 위치로 바꾼다. 비중첩 판정은 날짜가 아니라 위치로만 정확하다
    position_by_date = pd.Series(np.arange(len(alignment)), index=alignment[COL_DATE])
    result[COL_START_POSITION] = result[COL_DATE].map(position_by_date)

    if result[COL_START_POSITION].isna().any():
        raise ValueError("괴리 결과에 정렬 프레임이 모르는 날짜가 있습니다 — 같은 짝에서 나온 결과인지 확인하세요")

    result[COL_START_POSITION] = result[COL_START_POSITION].astype(int)

    # 2. 방향. 보합을 어느 쪽에도 넣지 않는다
    result[COL_DIRECTION] = np.where(
        result[COL_BASE_RETURN] > 0,
        DIRECTION_UP,
        np.where(result[COL_BASE_RETURN] < 0, DIRECTION_DOWN, DIRECTION_FLAT),
    )
    result.loc[result[COL_BASE_RETURN].isna(), COL_DIRECTION] = None

    # 3. 시기. 시작일 기준이다 — 구간이 경계를 걸치면 진입 시점의 국면으로 센다
    cutoff = pd.Timestamp(PERIOD_CUTOFF)
    result[COL_PERIOD] = np.where(result[COL_DATE] < cutoff, PERIOD_LOW_RATE, PERIOD_HIGH_RATE)

    # 4. 변동성. 구간별로 계산하고 사분위도 구간별로 매긴다
    result[COL_VOLATILITY_BUCKET] = _volatility_buckets(result, alignment)

    return result


def _volatility_buckets(divergence: pd.DataFrame, alignment: pd.DataFrame) -> pd.Series:
    """구간 안의 1배 일간 변동성을 재고 구간별 사분위로 나눈다.

    시작일 `i`, 구간 `h` 의 창은 일간 수익률 `i..i+h-1` 이다 (구간 안에서 실제로 겪은 등락).

    Args:
        divergence: 시작일 위치가 붙은 괴리 결과
        alignment: 공통 거래일 프레임

    Returns:
        `divergence` 와 같은 인덱스의 사분위 라벨 Series. 유효하지 않은 칸은 None
    """
    base_close = alignment[COL_BASE_CLOSE].to_numpy(dtype=float)
    daily_return = pd.Series(base_close[1:] / base_close[:-1] - 1.0)

    buckets = pd.Series(index=divergence.index, dtype=object)

    for horizon_key, group in divergence.groupby(COL_HORIZON, sort=True):
        horizon = int(str(horizon_key))

        # 창 안의 표준편차. rolling 은 «끝나는 자리» 기준이라 시작일 i 의 값은 i+h-1 에 있다
        rolling_std = daily_return.rolling(window=horizon).std(ddof=1)
        end_positions = group[COL_START_POSITION] + horizon - 1

        valid = (group[COL_EXCLUDED_REASON] != REASON_OUT_OF_RANGE) & (end_positions < len(daily_return))
        volatility = pd.Series(np.nan, index=group.index)
        volatility.loc[valid] = rolling_std.to_numpy()[end_positions[valid].to_numpy()]

        usable = volatility.notna()
        if usable.sum() < len(VOLATILITY_BUCKETS):
            continue

        # 같은 값이 많아 사분위 경계가 겹치면 구간 수를 줄여서라도 나눈다.
        # 나누지 못하면 그 구간은 비운 채로 둔다 — 억지로 라벨을 붙이면 없는 구분이 생긴다
        try:
            buckets.loc[volatility[usable].index] = pd.qcut(
                volatility[usable], q=len(VOLATILITY_BUCKETS), labels=list(VOLATILITY_BUCKETS)
            )
        except ValueError:
            logger.debug(f"변동성 사분위를 나누지 못했습니다 (구간 {horizon}거래일) — 값이 한쪽에 몰려 있습니다")

    return buckets


def max_non_overlapping(start_positions: Sequence[int], horizon: int) -> int:
    """겹치지 않게 고를 수 있는 구간의 최대 개수를 센다.

    시작일이 이르면 끝나는 것도 이르므로, **가장 이른 것부터 집는 그리디가 최적**이다
    (구간 스케줄링). 근사가 아니라 정확한 최대값이다.

    Args:
        start_positions: 시작일의 거래일 위치 목록
        horizon: 보유 기간 (거래일)

    Returns:
        서로 겹치지 않는 구간의 최대 개수

    Raises:
        ValueError: 보유 기간이 1 미만인 경우
    """
    if horizon < 1:
        raise ValueError(f"보유 기간은 1 이상이어야 합니다: {horizon}")

    count = 0
    next_available = -1

    for position in sorted(start_positions):
        if position >= next_available:
            count += 1
            next_available = position + horizon

    return count


def summarize(frame: pd.DataFrame, group_columns: Sequence[str]) -> pd.DataFrame:
    """칸별로 표본 수와 통계량을 낸다.

    **평균과 중앙값을 나란히 낸다** (측정의 원칙 4). 실현 배수는 중앙값만 낸다 —
    분모가 작은 칸에서 평균이 폭발하기 때문이다.

    유효 표본이 하한에 못 미치는 칸도 **행을 남기고** `판정가능` 을 「아니오」로 적는다.

    Args:
        frame: `attach_axes` 를 거친 괴리 결과
        group_columns: 칸을 정의하는 컬럼 목록 (예: 구간만, 또는 구간 + 축)

    Returns:
        칸별 집계표. `group_columns` 오름차순으로 정렬된다

    Raises:
        ValueError: 필요한 컬럼이 없는 경우
    """
    keys = list(group_columns)
    required = {COL_EXCLUDED_REASON, COL_HORIZON, COL_START_POSITION, *keys}
    missing_columns = required - set(frame.columns)
    if missing_columns:
        raise ValueError(f"집계에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")

    rows: list[dict[str, object]] = []

    # 컬럼 목록으로 묶으면 키가 항상 튜플로 온다 — 컬럼 하나여도 1-튜플이다
    for key_values, group in frame.groupby(keys, sort=True, dropna=False):
        out_of_range = group[COL_EXCLUDED_REASON] == REASON_OUT_OF_RANGE
        valid = group.loc[~out_of_range]

        horizon = int(str(group[COL_HORIZON].iloc[0]))
        row: dict[str, object] = dict(zip(keys, key_values, strict=True))
        row[COL_SAMPLE_COUNT] = len(valid)
        row[COL_EXCLUDED_COUNT] = int(out_of_range.sum())
        row[COL_NON_OVERLAPPING_COUNT] = max_non_overlapping(valid[COL_START_POSITION].tolist(), horizon)
        row[COL_JUDGEABLE] = JUDGEABLE_YES if len(valid) >= MIN_SAMPLE_PER_CELL else JUDGEABLE_NO

        for column in MEAN_MEDIAN_COLUMNS:
            row[f"{column}Mean"] = valid[column].mean() if len(valid) else np.nan
            row[f"{column}Median"] = valid[column].median() if len(valid) else np.nan

        for quantile in TAIL_QUANTILES:
            label = f"{COL_TOTAL_DIVERGENCE}P{int(quantile * 100):02d}"
            row[label] = valid[COL_TOTAL_DIVERGENCE].quantile(quantile) if len(valid) else np.nan

        realized = valid[COL_REALIZED_MULTIPLE].dropna()
        row[f"{COL_REALIZED_MULTIPLE}Median"] = realized.median() if len(realized) else np.nan
        row[f"{COL_REALIZED_MULTIPLE}Count"] = len(realized)

        rows.append(row)

    return pd.DataFrame(rows)


def summarize_by_horizon(frame: pd.DataFrame) -> pd.DataFrame:
    """구간별 전체 집계를 낸다.

    Args:
        frame: `attach_axes` 를 거친 괴리 결과

    Returns:
        구간별 집계표
    """
    return summarize(frame, [COL_HORIZON])


def summarize_by_axis(frame: pd.DataFrame, axis_column: str) -> pd.DataFrame:
    """구간 × 축으로 쪼갠 집계를 낸다.

    Args:
        frame: `attach_axes` 를 거친 괴리 결과
        axis_column: 축 컬럼 이름 (`VolatilityBucket` / `Direction` / `Period`)

    Returns:
        구간 × 축 집계표

    Raises:
        ValueError: 축 컬럼이 없는 경우
    """
    if axis_column not in frame.columns:
        raise ValueError(f"축 컬럼이 없습니다: {axis_column}")

    return summarize(frame, [COL_HORIZON, axis_column])
