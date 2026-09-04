"""1배 상품과 배수 상품의 날짜 정렬

두 종목을 짝지어 재는 것이 이 검증의 전제다. 상장일이 다르고 국내·미국의 휴장일이 다르므로
**공통 거래일만 남긴다.** 한쪽에만 있는 날을 앞뒤 값으로 채우면 그날의 괴리가 통째로
지어낸 값이 되고, 조용히 버리면 표본이 얼마나 줄었는지 알 수 없다.

그래서 제외하되 **몇 건이 어느 쪽에서 빠졌는지 함께 돌려준다.**
"""

from dataclasses import dataclass

import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE
from verify_lab.studies.leverage_tracking.constants import COL_BASE_CLOSE, COL_TARGET_CLOSE
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

RESULT_COLUMNS = [COL_DATE, COL_BASE_CLOSE, COL_TARGET_CLOSE]


@dataclass(frozen=True)
class PairAlignment:
    """정렬 결과.

    Attributes:
        frame: 공통 거래일만 담은 DataFrame. `RESULT_COLUMNS` 구성이며 날짜 오름차순이다
        base_only_count: 1배 상품에만 있어서 빠진 거래일 수
        target_only_count: 배수 상품에만 있어서 빠진 거래일 수
    """

    frame: pd.DataFrame
    base_only_count: int
    target_only_count: int


def align_pair(base: pd.DataFrame, target: pd.DataFrame) -> PairAlignment:
    """두 시세를 공통 거래일로 맞춘다.

    보간하지 않는다. 한쪽에만 있는 거래일은 빼고 그 건수를 돌려준다.

    Args:
        base: 1배 상품의 시세 (`data/loader.py` 가 돌려준 형태)
        target: 배수 상품의 시세

    Returns:
        공통 거래일 프레임과 양쪽 제외 건수

    Raises:
        ValueError: 필요한 컬럼이 없거나, 겹치는 거래일이 하나도 없는 경우
    """
    for label, frame in (("1배 상품", base), ("배수 상품", target)):
        missing_columns = {COL_DATE, COL_CLOSE} - set(frame.columns)
        if missing_columns:
            raise ValueError(f"{label} 시세에 필수 컬럼이 없습니다: {sorted(missing_columns)}")

    base_dates = set(base[COL_DATE])
    target_dates = set(target[COL_DATE])
    common_dates = base_dates & target_dates

    if not common_dates:
        raise ValueError(
            f"겹치는 거래일이 없습니다 - 1배 {len(base_dates):,}일, 배수 {len(target_dates):,}일. " f"두 종목의 기간이 어긋나지 않는지 확인하세요"
        )

    merged = (
        base[[COL_DATE, COL_CLOSE]]
        .rename(columns={COL_CLOSE: COL_BASE_CLOSE})
        .merge(
            target[[COL_DATE, COL_CLOSE]].rename(columns={COL_CLOSE: COL_TARGET_CLOSE}),
            on=COL_DATE,
            how="inner",
        )
        .sort_values(COL_DATE)
        .reset_index(drop=True)
    )

    base_only_count = len(base_dates - target_dates)
    target_only_count = len(target_dates - base_dates)

    logger.debug(f"날짜 정렬 완료: 공통 {len(merged):,}일 " f"(1배에만 {base_only_count:,}일, 배수에만 {target_only_count:,}일 제외)")

    return PairAlignment(
        frame=merged[RESULT_COLUMNS],
        base_only_count=base_only_count,
        target_only_count=target_only_count,
    )
