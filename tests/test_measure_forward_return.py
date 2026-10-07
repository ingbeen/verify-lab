"""forward return 표의 제외 건수 요약 계약을 고정한다 (측정 계층의 절대 원칙 4).

표를 만드는 것은 각 매매법이고 이 모듈은 그 표의 공통 모양만 소비한다. 그래서 이 테스트는
long-form 표를 **자기 픽스처로** 만든다 — 매매법의 계산을 빌려 쓰면 그 매매법을 지우는 순간
공유 계층의 검사가 함께 무너진다 (`tests/CLAUDE.md` 「공유 계층의 테스트는 «자기 픽스처»를 갖는다」).

실제 시세 파일에 의존하면 데이터를 갱신할 때마다 테스트가 깨지므로 합성 데이터만 쓴다.
"""

from collections.abc import Sequence

import pandas as pd
import pytest

from verify_lab.common_constants import COL_DATE
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_EXCLUDED_COUNT,
    COL_EXCLUDED_REASON,
    COL_FORWARD_RETURN,
    COL_HORIZON,
    COL_SIGNAL_COUNT,
    REASON_NONE,
    REASON_OUT_OF_RANGE,
)
from verify_lab.measure.forward_return import ReturnBasis, count_excluded

CLOSE = ReturnBasis.CLOSE.value

# 실제로 쓰이는 기준은 종가 하나뿐이다. 칸을 «기준별로» 가르는지 보려면 두 번째 기준 값이 있어야 하므로
# 픽스처가 만든다 — 실제 값만 쓰면 기준 축을 무시하는 구현도 통과한다
OTHER_BASIS = "other"


def _long_form(cells: Sequence[tuple[str, str, int, float | None]]) -> pd.DataFrame:
    """long-form forward return 표를 만든다.

    Args:
        cells: (신호일, 기준, 구간, 수익률) 목록. 수익률이 None 이면 구간 끝이 데이터 밖이라 제외된 칸이다

    Returns:
        신호일 × 기준 × 구간 한 줄씩의 표
    """
    return pd.DataFrame(
        {
            COL_DATE: pd.to_datetime([cell[0] for cell in cells]),
            COL_BASIS: [cell[1] for cell in cells],
            COL_HORIZON: [cell[2] for cell in cells],
            COL_FORWARD_RETURN: [float("nan") if cell[3] is None else cell[3] for cell in cells],
            COL_EXCLUDED_REASON: [REASON_OUT_OF_RANGE if cell[3] is None else REASON_NONE for cell in cells],
        }
    )


class TestCountExcluded:
    """제외 건수 요약의 계약을 고정한다."""

    def test_summary_covers_every_cell(self) -> None:
        """
        목적: 요약은 (기준 × 구간) 모든 칸을 낸다. 제외가 0건인 칸도 빠지지 않는다.

        Given: 신호 2건 · 종가 기준 구간 2개 · 다른 기준 구간 1개, 제외는 한 칸에만 있다
        When: 제외 건수를 센다
        Then: 칸이 3개이고 컬럼 순서가 계약대로다
        """
        # Given
        frame = _long_form(
            [
                ("2026-01-05", CLOSE, 1, 0.01),
                ("2026-01-05", CLOSE, 3, 0.02),
                ("2026-01-05", OTHER_BASIS, 1, 0.03),
                ("2026-01-12", CLOSE, 1, -0.01),
                ("2026-01-12", CLOSE, 3, None),
                ("2026-01-12", OTHER_BASIS, 1, 0.0),
            ]
        )

        # When
        summary = count_excluded(frame)

        # Then
        assert len(summary) == 3
        assert list(summary.columns) == [COL_BASIS, COL_HORIZON, COL_SIGNAL_COUNT, COL_EXCLUDED_COUNT]

    def test_summary_matches_the_preservation_identity(self) -> None:
        """
        목적: 칸마다 `신호 수 − 제외 수 = 값이 있는 행 수` 가 성립한다 (표본 보존).

        Given: 신호 3건 중 2건이 3일 구간에서 데이터 끝을 넘어 제외된 표
        When: 제외 건수를 센다
        Then: 1일 칸은 제외 0, 3일 칸은 제외 2 이고 보존 항등식이 성립한다
        """
        # Given
        frame = _long_form(
            [
                ("2026-01-05", CLOSE, 1, 0.01),
                ("2026-01-05", CLOSE, 3, 0.02),
                ("2026-01-14", CLOSE, 1, 0.03),
                ("2026-01-14", CLOSE, 3, None),
                ("2026-01-15", CLOSE, 1, -0.02),
                ("2026-01-15", CLOSE, 3, None),
            ]
        )

        # When
        summary = count_excluded(frame).set_index(COL_HORIZON)

        # Then
        assert summary.loc[1, COL_SIGNAL_COUNT] == 3
        assert summary.loc[1, COL_EXCLUDED_COUNT] == 0
        assert summary.loc[3, COL_SIGNAL_COUNT] == 3
        assert summary.loc[3, COL_EXCLUDED_COUNT] == 2
        for horizon in (1, 3):
            valid = int(frame.loc[frame[COL_HORIZON] == horizon, COL_FORWARD_RETURN].notna().sum())
            assert int(summary.loc[horizon, COL_SIGNAL_COUNT]) - int(summary.loc[horizon, COL_EXCLUDED_COUNT]) == valid

    def test_rejects_frame_without_required_columns(self) -> None:
        """
        목적: 다른 프레임을 넘기면 조용히 빈 요약을 내지 않고 즉시 거부한다.

        Given: 사유 컬럼이 없는 프레임
        When: 제외 건수를 센다
        Then: ValueError
        """
        # Given
        frame = _long_form([("2026-01-05", CLOSE, 1, 0.01)]).drop(columns=[COL_EXCLUDED_REASON])

        # When / Then
        with pytest.raises(ValueError, match="필수 컬럼"):
            count_excluded(frame)
