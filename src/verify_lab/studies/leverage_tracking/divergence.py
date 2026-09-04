"""괴리 분해 — 배수 상품이 명목 배수에서 얼마나, 왜 벗어났는가

보유 기간마다 세 값을 낸다.

| 값 | 산식 | 뜻 |
| --- | --- | --- |
| 단순 배수 기대치 `A` | `배수 × 1배 구간 수익률` | "2배면 2배 오르겠지" |
| 이론 경로 `B` | `Π(1 + 배수 × 1배 일간수익률) − 1` | 매일 정확히 배수로 리밸런싱만 하고 비용이 0 인 상품 |
| 실제 `C` | 배수 상품의 구간 수익률 | 실제로 손에 쥐는 것 |

여기서 괴리가 둘로 갈린다.

- **경로 효과 = `B − A`** — 변동성이 만든 몫. 수수료와 무관하며 추세장에서는 양수가 된다
- **상품 비용 = `C − B`** — 총보수·스왑·차입·추적오차. 보유 기간에 대체로 비례한다
- **총 괴리 = `C − A`** — 두 몫의 합

**`B` 를 중간에 두는 것이 이 모듈의 존재 이유다.** `A` 와 `C` 만 비교하면 음의 복리와 비용이
한 덩어리로 뭉쳐 "장기에 벌어진다"는 것만 알 뿐 왜 벌어지는지를 나눌 수 없다.

구간은 전부 **거래일**이며 날짜 연산이 아니라 위치 인덱스로만 계산한다. 구간 끝이 데이터를
넘어가는 시작일은 **행을 지우지 않고** 값만 비운 뒤 사유를 단다.
"""

from collections.abc import Sequence

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.measure.constants import COL_EXCLUDED_REASON, COL_HORIZON, REASON_NONE, REASON_OUT_OF_RANGE
from verify_lab.studies.leverage_tracking.constants import (
    COL_ACTUAL,
    COL_BASE_CLOSE,
    COL_BASE_RETURN,
    COL_NAIVE_EXPECTED,
    COL_PATH_EFFECT,
    COL_PATH_IDEAL,
    COL_PRODUCT_COST,
    COL_REALIZED_MULTIPLE,
    COL_TARGET_CLOSE,
    COL_TOTAL_DIVERGENCE,
    HORIZONS,
    MIN_BASE_RETURN_FOR_REALIZED_MULTIPLE,
    REASON_BASE_RETURN_TOO_SMALL,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

RESULT_COLUMNS = [
    COL_DATE,
    COL_HORIZON,
    COL_BASE_RETURN,
    COL_NAIVE_EXPECTED,
    COL_PATH_IDEAL,
    COL_ACTUAL,
    COL_PATH_EFFECT,
    COL_PRODUCT_COST,
    COL_TOTAL_DIVERGENCE,
    COL_REALIZED_MULTIPLE,
    COL_EXCLUDED_REASON,
]


def compute_divergence(
    frame: pd.DataFrame,
    multiple: float,
    horizons: Sequence[int] = HORIZONS,
) -> pd.DataFrame:
    """시작일마다 구간별 괴리를 내고 두 몫으로 분해한다.

    모든 거래일을 시작일로 삼는 롤링 전수다. 그래서 결과 표본은 서로 심하게 겹치며,
    독립 표본 수를 함께 봐야 한다 — 그 계산은 `breakdown` 이 맡는다.

    Args:
        frame: `pairing.align_pair` 가 낸 공통 거래일 프레임 (날짜 오름차순)
        multiple: 상품이 약속한 명목 배수. 인버스는 음수다
        horizons: 보유 기간 목록 (거래일, 모두 1 이상이며 중복 불가)

    Returns:
        `RESULT_COLUMNS` 순서의 long-form DataFrame.
        행 순서는 시작일 → 구간 오름차순이며 행 수는 `거래일 수 × 구간 수` 다.
        입력은 변경하지 않는다

    Raises:
        ValueError: 프레임이 비었거나 필수 컬럼이 없거나 날짜가 오름차순이 아닌 경우,
            구간이 비었거나 1 미만이거나 중복된 경우,
            이론 경로가 0 이하로 떨어져 구간 수익률을 정의할 수 없는 경우
    """
    ordered_horizons = _validated_horizons(horizons)
    _validate_frame(frame)

    base = frame[COL_BASE_CLOSE].to_numpy(dtype=float)
    target = frame[COL_TARGET_CLOSE].to_numpy(dtype=float)
    dates = frame[COL_DATE].to_numpy()

    row_count = len(frame)
    last_position = row_count - 1
    positions = np.arange(row_count)

    # 1. 이론 경로를 누적곱으로 만든다. 매일 배수만큼 리밸런싱한 «완벽한» 상품의 가치이며
    #    시작값은 1 이다. 구간 (i, i+h] 의 곱은 `path[i + h] / path[i]` 로 나온다
    daily_return = base[1:] / base[:-1] - 1.0
    daily_factor = 1.0 + multiple * daily_return

    non_positive = daily_factor <= 0.0
    if non_positive.any():
        first_position = int(np.flatnonzero(non_positive)[0]) + 1
        raise ValueError(
            f"이론 경로가 0 이하로 떨어져 구간 수익률을 정의할 수 없습니다 - "
            f"날짜: {frame[COL_DATE].iloc[first_position]}, 배수: {multiple}, "
            f"1배 일간수익률: {daily_return[first_position - 1]:+.2%}. "
            f"배수 상품이 하루에 전액 손실되는 구간이므로 측정 대상이 아닙니다"
        )

    ideal_path = np.empty(row_count)
    ideal_path[0] = 1.0
    ideal_path[1:] = np.cumprod(daily_factor)

    # 2. 구간 오름차순으로 블록을 쌓는다. 이 순서가 뒤의 안정 정렬에서 그대로 유지된다
    blocks: list[pd.DataFrame] = []
    for horizon in ordered_horizons:
        targets = positions + horizon
        usable = targets <= last_position

        base_return = np.full(row_count, np.nan)
        naive_expected = np.full(row_count, np.nan)
        path_ideal = np.full(row_count, np.nan)
        actual = np.full(row_count, np.nan)

        usable_starts = positions[usable]
        usable_ends = targets[usable]

        base_return[usable] = base[usable_ends] / base[usable_starts] - 1.0
        naive_expected[usable] = multiple * base_return[usable]
        path_ideal[usable] = ideal_path[usable_ends] / ideal_path[usable_starts] - 1.0
        actual[usable] = target[usable_ends] / target[usable_starts] - 1.0

        # 3. 분해. 두 몫의 합이 총 괴리와 같다는 항등식이 이 검증의 결론을 떠받친다
        path_effect = path_ideal - naive_expected
        product_cost = actual - path_ideal
        total_divergence = actual - naive_expected

        # 4. 실현 배수. 분모가 0 근처면 값이 폭발하므로 임계 미만은 내지 않는다.
        #    괴리 3값은 그대로 두고 실현 배수만 비운다
        too_small = usable & (np.abs(base_return) < MIN_BASE_RETURN_FOR_REALIZED_MULTIPLE)
        realized_multiple = np.full(row_count, np.nan)
        computable = usable & ~too_small
        realized_multiple[computable] = actual[computable] / base_return[computable]

        reason = np.where(~usable, REASON_OUT_OF_RANGE, np.where(too_small, REASON_BASE_RETURN_TOO_SMALL, REASON_NONE))

        blocks.append(
            pd.DataFrame(
                {
                    COL_DATE: dates,
                    COL_HORIZON: horizon,
                    COL_BASE_RETURN: base_return,
                    COL_NAIVE_EXPECTED: naive_expected,
                    COL_PATH_IDEAL: path_ideal,
                    COL_ACTUAL: actual,
                    COL_PATH_EFFECT: path_effect,
                    COL_PRODUCT_COST: product_cost,
                    COL_TOTAL_DIVERGENCE: total_divergence,
                    COL_REALIZED_MULTIPLE: realized_multiple,
                    COL_EXCLUDED_REASON: reason,
                }
            )
        )

    # 5. 시작일만 안정 정렬한다. 같은 날 안에서는 블록을 쌓은 순서(구간 오름차순)가 보존된다
    result = pd.concat(blocks, ignore_index=True).sort_values(COL_DATE, kind="stable").reset_index(drop=True)
    result = result[RESULT_COLUMNS]

    out_of_range = int((result[COL_EXCLUDED_REASON] == REASON_OUT_OF_RANGE).sum())
    logger.debug(
        f"괴리 계산 완료: 배수 {multiple}, 거래일 {row_count:,}일, "
        f"{len(result):,}행 (구간 초과 {out_of_range:,}칸, 구간 {list(ordered_horizons)})"
    )

    return result


def _validated_horizons(horizons: Sequence[int]) -> tuple[int, ...]:
    """보유 기간을 검증하고 오름차순으로 정렬해 돌려준다.

    인자 순서를 그대로 쓰면 같은 데이터로 두 번 돌린 결과의 행 순서가 달라진다.

    Args:
        horizons: 보유 기간 목록 (거래일)

    Returns:
        오름차순으로 정렬된 보유 기간

    Raises:
        ValueError: 비었거나, 1 미만이거나, 중복된 구간이 있는 경우
    """
    ordered = tuple(sorted(horizons))

    if not ordered:
        raise ValueError("보유 기간이 비어 있습니다")

    invalid = [horizon for horizon in ordered if horizon < 1]
    if invalid:
        raise ValueError(f"보유 기간은 1 이상이어야 합니다: {invalid}")

    if len(set(ordered)) != len(ordered):
        raise ValueError(f"보유 기간이 중복됩니다: {list(ordered)}")

    return ordered


def _validate_frame(frame: pd.DataFrame) -> None:
    """정렬된 짝 프레임이 위치 기반 계산의 전제를 만족하는지 확인한다.

    날짜가 뒤섞이면 구간 수익률이 예외 없이 조용히 어긋난다.

    Args:
        frame: 정렬된 짝 프레임

    Raises:
        ValueError: 비었거나, 필수 컬럼이 없거나, 날짜가 오름차순이 아닌 경우
    """
    if frame.empty:
        raise ValueError("정렬된 시세가 비어 있습니다")

    missing_columns = {COL_DATE, COL_BASE_CLOSE, COL_TARGET_CLOSE} - set(frame.columns)
    if missing_columns:
        raise ValueError(f"필수 컬럼이 누락되었습니다: {sorted(missing_columns)}")

    if not frame[COL_DATE].is_monotonic_increasing:
        raise ValueError("정렬된 시세가 날짜 오름차순이 아닙니다")
