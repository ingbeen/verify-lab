"""만기일 기준 상대 거래일(offset) 배정

만기일을 0 으로 두고 **거래일 위치 인덱스**의 차이로 offset 을 센다. 달력일이 아니다 —
휴장이 끼면 달력일 간격이 흔들려 두 만기의 offset 이 같은 뜻을 갖지 못한다
(`docs/spec/option_expiry.md` 결정 ⑥).

만기 간격이 좁은 달에는 **한 날이 두 만기의 창에 동시에 들 수 있다.** 그때는 가까운 쪽에
배정하고, 거리가 같으면 이전 만기 쪽(양수 offset)에 붙인다 — 만기일을 사건으로 두고 그 이후를
재는 것이 이 프로젝트의 기본 측정 방향이라 사건과 이후 구간의 연결을 끊지 않는다(결정 ⑦·⑫).
양쪽에 모두 배정하면 같은 날을 두 번 세어 표본 독립성이 깨지고, 겹치는 구간을 버리면 표본이
조용히 줄어든다. **어느 쪽도 하지 않는 대신 겹친 건수를 세어 보고한다.**
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.studies.option_expiry.constants import COL_EXPIRY_DATE, COL_OFFSET

# 어느 쪽 만기와도 이어지지 않는 자리를 채우는 거리. 실제 거리와 섞이지 않도록
# 거래일 수로 도달할 수 없는 값을 쓴다
_UNREACHABLE_DISTANCE = np.iinfo(np.int64).max


@dataclass(frozen=True)
class OffsetAssignment:
    """거래일에 배정된 만기 상대 거래일

    Attributes:
        frame: 배정된 날만 담은 DataFrame (날짜·offset·만기일). 날짜 오름차순
        total_days: 입력 거래일 수
        contested_count: 두 만기의 창에 동시에 들어 가까운 쪽으로 갈린 날의 수
        tie_count: 두 만기와의 거리가 같아 규칙으로 갈린 날의 수
    """

    frame: pd.DataFrame
    total_days: int
    contested_count: int
    tie_count: int

    @property
    def assigned_count(self) -> int:
        """어느 만기의 창에든 배정된 날의 수.

        Returns:
            배정된 날의 수
        """
        return len(self.frame)

    @property
    def unassigned_count(self) -> int:
        """어느 만기의 창에도 들지 않은 날의 수.

        Returns:
            배정되지 않은 날의 수
        """
        return self.total_days - len(self.frame)


def expiry_offsets(
    trading_days: pd.DatetimeIndex,
    expiry_dates: pd.DatetimeIndex,
    max_offset: int,
) -> OffsetAssignment:
    """각 거래일에 가장 가까운 만기일 기준 offset 을 배정한다.

    Args:
        trading_days: 거래일 목록. 오름차순 정렬된 중복 없는 인덱스여야 한다
        expiry_dates: 만기일 목록. 전부 `trading_days` 안에 있어야 한다
        max_offset: 만기일 앞뒤로 배정할 최대 거래일 수 (0 이상)

    Returns:
        배정 결과와 겹침 통계

    Raises:
        ValueError: 입력이 정렬·포함·범위 조건을 어긴 경우
    """
    if len(trading_days) == 0:
        raise ValueError("거래일 목록이 비어 있어 offset 을 배정할 수 없습니다")
    if not trading_days.is_monotonic_increasing:
        raise ValueError("거래일 목록이 오름차순으로 정렬되어 있어야 합니다")
    if trading_days.has_duplicates:
        raise ValueError("거래일 목록에 중복된 날짜가 있습니다")
    if max_offset < 0:
        raise ValueError(f"max_offset 은 0 이상이어야 합니다: {max_offset}")

    expiry_positions = np.asarray(trading_days.get_indexer(expiry_dates), dtype=np.int64)
    if len(expiry_positions) and expiry_positions.min() < 0:
        missing = expiry_dates[expiry_positions < 0]
        raise ValueError(f"만기일이 거래일 목록에 없습니다: {[d.date().isoformat() for d in missing]}")
    if len(expiry_positions) > 1 and not np.all(np.diff(expiry_positions) > 0):
        raise ValueError("만기일 목록이 오름차순으로 정렬되어 있어야 합니다")

    if len(expiry_positions) == 0:
        return OffsetAssignment(
            frame=_empty_frame(),
            total_days=len(trading_days),
            contested_count=0,
            tie_count=0,
        )

    day_positions = np.arange(len(trading_days), dtype=np.int64)

    # 1. 각 거래일에 대해 "그 날 이상인 첫 만기"의 위치. 그 앞이 직전 만기다
    insert_at = np.searchsorted(expiry_positions, day_positions, side="left")
    has_previous = insert_at > 0
    has_next = insert_at < len(expiry_positions)

    # 2. 앞뒤 만기까지의 거리. 없는 쪽은 도달 불가 값으로 채워 비교에서 자동 탈락시킨다
    previous_distance = np.where(
        has_previous,
        day_positions - expiry_positions[np.clip(insert_at - 1, 0, len(expiry_positions) - 1)],
        _UNREACHABLE_DISTANCE,
    )
    next_distance = np.where(
        has_next,
        expiry_positions[np.clip(insert_at, 0, len(expiry_positions) - 1)] - day_positions,
        _UNREACHABLE_DISTANCE,
    )

    within_previous = previous_distance <= max_offset
    within_next = next_distance <= max_offset

    # 3. 겹친 날은 가까운 쪽으로, 거리가 같으면 이전 만기 쪽으로 배정한다
    use_previous = within_previous & (~within_next | (previous_distance <= next_distance))
    assigned = within_previous | within_next

    offsets = np.where(use_previous, previous_distance, -next_distance)
    chosen_expiry_index = np.where(use_previous, insert_at - 1, insert_at)

    frame = pd.DataFrame(
        {
            COL_DATE: trading_days[assigned],
            COL_OFFSET: offsets[assigned].astype(np.int64),
            COL_EXPIRY_DATE: trading_days[expiry_positions[chosen_expiry_index[assigned]]],
        }
    )

    contested = within_previous & within_next
    return OffsetAssignment(
        frame=frame,
        total_days=len(trading_days),
        contested_count=int(contested.sum()),
        tie_count=int((contested & (previous_distance == next_distance)).sum()),
    )


def _empty_frame() -> pd.DataFrame:
    """만기일이 하나도 없을 때 돌려줄 빈 배정 표를 만든다.

    Returns:
        배정 표와 같은 스키마의 빈 DataFrame
    """
    return pd.DataFrame(
        {
            COL_DATE: pd.Series(dtype="datetime64[ns]"),
            COL_OFFSET: pd.Series(dtype="int64"),
            COL_EXPIRY_DATE: pd.Series(dtype="datetime64[ns]"),
        }
    )
