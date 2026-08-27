"""검증 #7 의 만기일 기준 상대 거래일(offset) 배정을 고정한다.

offset 은 **거래일 위치**로 센다. 달력일로 세면 휴장이 낀 달과 안 낀 달의 offset 이 같은 뜻을
갖지 못한다. 만기 간격이 좁은 달에는 한 날이 두 만기의 창에 동시에 들 수 있으므로, 배정 규칙과
겹침 집계를 함께 고정한다.

고정하는 계약은 다섯이다.
- 만기일의 offset 은 0 이고, 그 앞은 음수·뒤는 양수다
- offset 은 달력일이 아니라 **거래일 수**다
- 두 만기의 창에 동시에 들면 가까운 쪽, 거리가 같으면 이전 만기 쪽으로 배정한다
- 배정된 날 + 배정되지 않은 날 = 전체 거래일 (표본 보존)
- 이미 두 만기 사이에 놓인 날의 배정은 뒤에 데이터가 붙어도 달라지지 않는다 (look-ahead 감시)
"""

import pandas as pd
import pytest

from verify_lab.common_constants import COL_DATE
from verify_lab.studies.option_expiry.constants import COL_EXPIRY_DATE, COL_OFFSET
from verify_lab.studies.option_expiry.offsets import expiry_offsets


def _days(count: int) -> pd.DatetimeIndex:
    """연속한 합성 거래일을 만든다. 주말·휴장을 섞지 않아야 위치 계산만 순수하게 검사된다."""
    return pd.bdate_range("2026-01-05", periods=count)


def _offset_of(assignment_frame: pd.DataFrame, date: pd.Timestamp) -> int:
    """배정 표에서 지정한 날의 offset 을 꺼낸다."""
    rows = assignment_frame[assignment_frame[COL_DATE] == date]
    assert len(rows) == 1, f"{date.date()} 의 배정 행이 1개가 아닙니다: {len(rows)}개"

    return int(rows.iloc[0][COL_OFFSET])


class TestExpiryOffsets:
    """offset 배정 규칙을 고정한다."""

    def test_만기일의_offset_은_0이다(self) -> None:
        """
        목적: 앵커 정의를 고정한다

        Given: 거래일 21개 중 10번째가 만기일
        When: offset 을 배정하면
        Then: 그날의 offset 이 0 이다
        """
        # Given
        days = _days(21)
        expiries = pd.DatetimeIndex([days[10]])

        # When
        result = expiry_offsets(days, expiries, max_offset=5)

        # Then
        assert _offset_of(result.frame, days[10]) == 0

    def test_만기_이전은_음수_이후는_양수다(self) -> None:
        """
        목적: 부호 규약을 고정한다

        Given: 거래일 21개 중 10번째가 만기일
        When: offset 을 배정하면
        Then: 하루 전은 -1, 하루 뒤는 +1 이다
        """
        # Given
        days = _days(21)
        expiries = pd.DatetimeIndex([days[10]])

        # When
        result = expiry_offsets(days, expiries, max_offset=5)

        # Then
        assert _offset_of(result.frame, days[9]) == -1
        assert _offset_of(result.frame, days[11]) == 1

    def test_offset_은_달력일이_아니라_거래일로_센다(self) -> None:
        """
        목적: 휴장이 끼어도 offset 이 흔들리지 않음을 고정한다

        Given: 만기일 직전에 이틀이 휴장인 달력
        When: offset 을 배정하면
        Then: 달력상 3일 전인 날의 offset 이 -1 이다
        """
        # Given
        days = pd.DatetimeIndex(
            [
                pd.Timestamp("2026-03-09"),
                pd.Timestamp("2026-03-12"),  # 달력상 만기 3일 전이지만 직전 거래일
                pd.Timestamp("2026-03-13"),  # 만기일
            ]
        )
        expiries = pd.DatetimeIndex([pd.Timestamp("2026-03-13")])

        # When
        result = expiry_offsets(days, expiries, max_offset=5)

        # Then
        assert _offset_of(result.frame, pd.Timestamp("2026-03-12")) == -1
        assert _offset_of(result.frame, pd.Timestamp("2026-03-09")) == -2

    def test_창_밖의_날은_배정되지_않는다(self) -> None:
        """
        목적: max_offset 이 실제로 창을 자르는지 고정한다

        Given: 거래일 21개 중 10번째가 만기일, 창은 ±2
        When: offset 을 배정하면
        Then: 배정된 날이 5개(-2~+2)뿐이다
        """
        # Given
        days = _days(21)
        expiries = pd.DatetimeIndex([days[10]])

        # When
        result = expiry_offsets(days, expiries, max_offset=2)

        # Then
        assert result.assigned_count == 5
        assert sorted(result.frame[COL_OFFSET].tolist()) == [-2, -1, 0, 1, 2]

    def test_표본이_보존된다(self) -> None:
        """
        목적: 표본 보존 — 날이 조용히 사라지지 않음을 고정한다

        Given: 거래일 21개, 만기 1개, 창 ±2
        When: offset 을 배정하면
        Then: 배정된 수 + 배정되지 않은 수 = 전체 거래일 수
        """
        # Given
        days = _days(21)
        expiries = pd.DatetimeIndex([days[10]])

        # When
        result = expiry_offsets(days, expiries, max_offset=2)

        # Then
        assert result.assigned_count + result.unassigned_count == len(days)
        assert result.total_days == len(days)

    def test_두_만기의_창이_겹치면_가까운_쪽에_배정한다(self) -> None:
        """
        목적: 결정 ⑦ — 같은 날을 두 번 세지 않음을 고정한다

        Given: 만기가 위치 5·15 이고 창이 ±6 이라 위치 9~11 이 양쪽 창에 든다
        When: offset 을 배정하면
        Then: 위치 9 는 이전 만기 기준 +4, 위치 11 은 다음 만기 기준 -4 다
        """
        # Given
        days = _days(21)
        expiries = pd.DatetimeIndex([days[5], days[15]])

        # When
        result = expiry_offsets(days, expiries, max_offset=6)

        # Then
        assert _offset_of(result.frame, days[9]) == 4
        assert _offset_of(result.frame, days[11]) == -4
        assert result.contested_count == 3

    def test_거리가_같으면_이전_만기_쪽에_배정한다(self) -> None:
        """
        목적: 결정 ⑫ — 동률 처리를 결정적으로 고정한다

        Given: 만기가 위치 5·15 이고 창이 ±6 이라 위치 10 이 양쪽에서 5거래일 거리다
        When: offset 을 배정하면
        Then: 이전 만기 기준 +5 이고 동률로 집계된다
        """
        # Given
        days = _days(21)
        expiries = pd.DatetimeIndex([days[5], days[15]])

        # When
        result = expiry_offsets(days, expiries, max_offset=6)

        # Then
        assert _offset_of(result.frame, days[10]) == 5
        assert result.frame[result.frame[COL_DATE] == days[10]].iloc[0][COL_EXPIRY_DATE] == days[5]
        assert result.tie_count == 1

    def test_한_날은_한_만기에만_배정된다(self) -> None:
        """
        목적: 표본 독립성 — 중복 배정이 없음을 고정한다

        Given: 창이 겹치도록 촘촘한 만기 3개
        When: offset 을 배정하면
        Then: 배정 표에 같은 날짜가 두 번 나오지 않는다
        """
        # Given
        days = _days(31)
        expiries = pd.DatetimeIndex([days[5], days[15], days[25]])

        # When
        result = expiry_offsets(days, expiries, max_offset=8)

        # Then
        assert not result.frame[COL_DATE].duplicated().any()

    def test_만기가_없으면_아무것도_배정되지_않는다(self) -> None:
        """
        목적: 경계 조건 — 빈 만기 목록에서 예외 없이 빈 결과를 내는지 고정한다

        Given: 거래일 21개, 만기 0개
        When: offset 을 배정하면
        Then: 배정 표가 비고 전체 거래일이 미배정으로 집계된다
        """
        # Given
        days = _days(21)

        # When
        result = expiry_offsets(days, pd.DatetimeIndex([]), max_offset=5)

        # Then
        assert result.assigned_count == 0
        assert result.unassigned_count == len(days)

    def test_거래일에_없는_만기일은_예외다(self) -> None:
        """
        목적: 입력 검증 — 만기일이 거래일 목록 안에 있어야 함을 고정한다

        Given: 거래일 목록에 없는 만기일
        When: offset 을 배정하면
        Then: ValueError 가 난다
        """
        # Given
        days = _days(21)
        expiries = pd.DatetimeIndex([pd.Timestamp("2030-01-04")])

        # When / Then
        with pytest.raises(ValueError, match="거래일 목록에 없습니다"):
            expiry_offsets(days, expiries, max_offset=5)

    def test_음수_창은_예외다(self) -> None:
        """
        목적: 입력 검증을 고정한다

        Given: 음수 max_offset
        When: offset 을 배정하면
        Then: ValueError 가 난다
        """
        # Given
        days = _days(21)
        expiries = pd.DatetimeIndex([days[10]])

        # When / Then
        with pytest.raises(ValueError, match="max_offset"):
            expiry_offsets(days, expiries, max_offset=-1)

    def test_뒤에_데이터가_붙어도_두_만기_사이의_배정은_그대로다(self) -> None:
        """
        목적: **look-ahead 감시** — 확정된 구간의 배정이 미래 데이터에 흔들리지 않음을 고정한다

        Given: 만기 3개(위치 5·15·25)를 갖는 달력과, 두 번째 만기 창까지만 남긴 잘린 달력
        When: 각각 offset 을 배정하면
        Then: 두 번째 만기의 창 끝까지의 배정이 양쪽에서 같다
        """
        # Given
        days = _days(31)
        expiries = pd.DatetimeIndex([days[5], days[15], days[25]])
        cut = 21  # 두 번째 만기(위치 15) + 창 5 까지 확정된 지점
        truncated_days = days[:cut]
        truncated_expiries = pd.DatetimeIndex([d for d in expiries if d in truncated_days])

        # When
        truncated = expiry_offsets(truncated_days, truncated_expiries, max_offset=5)
        whole = expiry_offsets(days, expiries, max_offset=5)

        # Then
        settled = days[: cut - 5]
        truncated_settled = truncated.frame[truncated.frame[COL_DATE].isin(settled)].reset_index(drop=True)
        whole_settled = whole.frame[whole.frame[COL_DATE].isin(settled)].reset_index(drop=True)

        assert not truncated_settled.empty, "비교할 칸이 하나도 없습니다"
        pd.testing.assert_frame_equal(
            truncated_settled,
            whole_settled,
            obj="뒤를 잘라낸 입력과 전체 입력의 배정이 다릅니다 — 미래 데이터를 참조하고 있습니다",
        )
