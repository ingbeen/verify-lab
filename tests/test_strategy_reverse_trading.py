"""역방향 매매 규칙의 체결 계약을 고정한다.

이 계층이 틀리는 방식은 **판정 순서가 뒤바뀌는 것**이다. 시가·장중·종가를 이 순서로 보지 않으면
갭 하락한 날이 장중 손절가로 체결된 것처럼 계산되어 **손실이 실제보다 작게 나온다.**
예외는 나지 않고 표도 정상으로 보이므로 손계산으로 박는다.

핵심 계약은 다섯 가지다.
- 갭 청산은 **손절선보다 더 잃는다**. 시가가 이미 아래면 그 시가가 체결가다
- 장중 손절은 **손절선 가격**에 체결된다
- 손절선은 **진입가 기준**이며 보유 기간 내내 갱신하지 않는다
- 이익이 나면 **그날 종가**로 청산된다
- 상승 방향 신호는 **고가**로 손절을 판정한다 (인버스 진입)
"""

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.strategy.constants import (
    EXIT_GAP_STOP,
    EXIT_INTRADAY_STOP,
    EXIT_LIMIT,
    EXIT_PROFIT,
    HOLD_LIMIT,
    STOP_LOSS_LEVEL,
)
from verify_lab.strategy.reverse_trading import simulate_signal

# 손계산을 쉽게 하려고 진입가를 100 으로 둔다
ENTRY_PRICE = 100.0

# 수익률 비교 허용오차 (tests/CLAUDE.md — 수학적 정확 계산)
RATE_TOLERANCE = 1e-12


def _frame(bars: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """(시가, 고가, 저가, 종가) 목록으로 시세를 만든다.

    첫 행이 신호일이며 종가가 진입가다.
    """
    dates = pd.DatetimeIndex(pd.bdate_range("2020-01-01", periods=len(bars)))

    return pd.DataFrame(
        {
            COL_DATE: dates,
            COL_OPEN: [bar[0] for bar in bars],
            COL_HIGH: [bar[1] for bar in bars],
            COL_LOW: [bar[2] for bar in bars],
            COL_CLOSE: [bar[3] for bar in bars],
            COL_VOLUME: 1_000_000,
        }
    )


def _signal_day() -> tuple[float, float, float, float]:
    """신호일 봉. 종가가 진입가가 된다."""
    return (ENTRY_PRICE, ENTRY_PRICE, ENTRY_PRICE, ENTRY_PRICE)


class TestStopLoss:
    """손절 체결 계약"""

    def test_장중_손절은_손절선_가격에_체결된다(self) -> None:
        """
        목적: 장중 손절의 체결가를 고정한다

        Given: 시가는 손절선 위인데 장중에 -7% 까지 밀린 다음날
        When: 손절선 -5% 로 체결했을 때
        Then: 실제 저가(-7%)가 아니라 **손절선 가격(-5%)** 에 체결된다
        """
        # Given
        frame = _frame([_signal_day(), (99.5, 100.0, 93.0, 94.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=1)

        # Then
        assert result is not None
        assert result.reason == EXIT_INTRADAY_STOP
        assert result.return_rate == pytest.approx(-STOP_LOSS_LEVEL, abs=RATE_TOLERANCE)

    def test_손절선에_정확히_닿으면_손절된다(self) -> None:
        """
        목적: 경계에서의 판정을 고정한다 (엣지 케이스)

        Given: 저가가 손절선에 **정확히** 닿은 다음날
        When: 체결했을 때
        Then: 손절된다 (경계값을 포함한다)
        """
        # Given
        stop_price = ENTRY_PRICE * (1.0 - STOP_LOSS_LEVEL)
        frame = _frame([_signal_day(), (99.5, 100.0, stop_price, 99.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=1)

        # Then
        assert result is not None
        assert result.reason == EXIT_INTRADAY_STOP

    def test_손절선이_양수가_아니면_거부한다(self) -> None:
        """
        목적: 잘못된 파라미터를 즉시 막는지 고정한다

        Given: 손절선 0
        When: 체결을 요청했을 때
        Then: ValueError 가 난다
        """
        # Given
        frame = _frame([_signal_day(), (99.0, 100.0, 98.0, 99.0)])

        # When / Then
        with pytest.raises(ValueError, match="손절선"):
            simulate_signal(frame, 0, upward=False, hold_limit=1, stop_level=0.0)


class TestGapExit:
    """갭 청산 계약 — 손절선이 지켜지지 않는 유일한 경로"""

    def test_갭_청산은_손절선보다_더_잃는다(self) -> None:
        """
        목적: 갭 하락이 손절선으로 막히지 않는다는 사실을 고정한다

        **이 계약이 깨지면 손실이 실제보다 작게 나온다.** 시가가 이미 손절선 아래인데
        장중 판정을 먼저 하면 -5% 에 체결된 것으로 계산된다.

        Given: 시가가 -8% 로 열린 다음날
        When: 손절선 -5% 로 체결했을 때
        Then: -5% 가 아니라 **시가 그대로 -8%** 에 청산된다
        """
        # Given
        frame = _frame([_signal_day(), (92.0, 95.0, 90.0, 94.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=1)

        # Then
        assert result is not None
        assert result.reason == EXIT_GAP_STOP
        assert result.return_rate == pytest.approx(-0.08, abs=RATE_TOLERANCE)
        assert result.return_rate < -STOP_LOSS_LEVEL


class TestHoldLimit:
    """보유 한도 계약"""

    def test_이익이면_그날_청산된다(self) -> None:
        """
        목적: 반등을 놓치지 않는지 고정한다

        Given: 다음날 종가가 +2% 인 시세와 넉넉한 한도
        When: 체결했을 때
        Then: D+1 에 청산된다 (한도까지 끌지 않는다)
        """
        # Given
        frame = _frame([_signal_day(), (99.0, 103.0, 98.0, 102.0), (102.0, 105.0, 101.0, 104.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=2)

        # Then
        assert result is not None
        assert result.reason == EXIT_PROFIT
        assert result.hold_days == 1
        assert result.return_rate == pytest.approx(0.02, abs=RATE_TOLERANCE)

    def test_손실이면_한도까지_보유하고_종가에_청산된다(self) -> None:
        """
        목적: 손실일 때만 한도까지 끄는 계약을 고정한다

        Given: 이틀 내내 손실이지만 손절선에는 닿지 않는 시세
        When: 한도 D+2 로 체결했을 때
        Then: D+2 종가에 손실이어도 청산된다
        """
        # Given
        frame = _frame([_signal_day(), (99.5, 100.0, 98.0, 99.0), (99.0, 99.5, 97.5, 98.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=2)

        # Then
        assert result is not None
        assert result.reason == EXIT_LIMIT
        assert result.hold_days == 2
        assert result.return_rate == pytest.approx(-0.02, abs=RATE_TOLERANCE)

    def test_확정된_한도는_D_플러스_2다(self) -> None:
        """
        목적: 규칙이 정한 기본 한도를 고정한다

        3일 구간은 평균 우연확률이 0.2917 로 근거가 없고, D+3 에서만 갭손절이 새로 생긴다.

        Given: 확정 상수
        When: 값을 봤을 때
        Then: D+2 다
        """
        assert HOLD_LIMIT == 2

    def test_한도가_1_미만이면_거부한다(self) -> None:
        """
        목적: 잘못된 파라미터를 즉시 막는지 고정한다

        Given: 한도 0
        When: 체결을 요청했을 때
        Then: ValueError 가 난다
        """
        # Given
        frame = _frame([_signal_day(), (99.0, 100.0, 98.0, 99.0)])

        # When / Then
        with pytest.raises(ValueError, match="보유 한도"):
            simulate_signal(frame, 0, upward=False, hold_limit=0)


class TestStopBase:
    """손절선 기준 계약"""

    def test_손절선은_진입가_기준이며_갱신되지_않는다(self) -> None:
        """
        목적: 손절선이 따라 내려가 최악이 무제한으로 열리는 사고를 막는다

        **전일 종가 기준으로 갱신하면** D+2 의 손절선이 -5% 가 아니라 그날 시가 근처가 되어
        손실이 계속 이어져도 손절이 걸리지 않는다.

        Given: D+1 에 -3%, D+2 에 진입가 대비 -6% 까지 밀리는 시세
        When: 한도 D+2 로 체결했을 때
        Then: D+2 에 **진입가 기준** -5% 로 손절된다
        """
        # Given
        frame = _frame([_signal_day(), (99.5, 100.0, 96.5, 97.0), (97.0, 97.5, 94.0, 94.5)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=2)

        # Then
        assert result is not None
        assert result.reason == EXIT_INTRADAY_STOP
        assert result.hold_days == 2
        assert result.return_rate == pytest.approx(-STOP_LOSS_LEVEL, abs=RATE_TOLERANCE)


class TestDirection:
    """방향 계약 — 폭등 신호는 인버스로 진입한다"""

    def test_상승_방향_신호는_고가로_손절을_판정한다(self) -> None:
        """
        목적: 인버스 진입에서 어느 쪽이 손실인지 고정한다

        **저가로 판정하면 손절이 영영 걸리지 않는다.** 인버스는 원지수가 오를 때 손실이다.

        Given: 원지수가 장중 +7% 까지 오른 다음날
        When: 상승 방향 신호로 체결했을 때
        Then: 손절된다 (고가를 봤다)
        """
        # Given
        frame = _frame([_signal_day(), (100.5, 107.0, 100.0, 101.0)])

        # When
        result = simulate_signal(frame, 0, upward=True, hold_limit=1)

        # Then
        assert result is not None
        assert result.reason == EXIT_INTRADAY_STOP
        assert result.return_rate == pytest.approx(-STOP_LOSS_LEVEL, abs=RATE_TOLERANCE)

    def test_상승_방향_신호는_원지수_하락이_이익이다(self) -> None:
        """
        목적: 부호 반전을 고정한다

        Given: 원지수가 -3% 로 마감한 다음날
        When: 상승 방향 신호로 체결했을 때
        Then: **+3%** 이익으로 청산된다
        """
        # Given
        frame = _frame([_signal_day(), (99.0, 99.5, 96.5, 97.0)])

        # When
        result = simulate_signal(frame, 0, upward=True, hold_limit=1)

        # Then
        assert result is not None
        assert result.reason == EXIT_PROFIT
        assert result.return_rate == pytest.approx(0.03, abs=RATE_TOLERANCE)


class TestBoundary:
    """경계 조건"""

    def test_한도가_데이터_끝을_넘어가면_없음을_낸다(self) -> None:
        """
        목적: 부분 체결을 남기지 않는지 고정한다 (표본 보존)

        구간이 데이터를 넘어간 신호를 부분 체결로 남기면 조합마다 표본이 달라진다.

        Given: 신호일 다음에 하루만 있는 시세
        When: 한도 D+2 로 체결했을 때
        Then: `None` 이다 (그 신호는 통째로 빠진다)
        """
        # Given
        frame = _frame([_signal_day(), (99.5, 100.0, 98.0, 99.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=2)

        # Then
        assert result is None

    def test_종가가_정확히_진입가면_이익이_아니다(self) -> None:
        """
        목적: 보합의 처리를 고정한다 (엣지 케이스)

        Given: 다음날 종가가 진입가와 **정확히 같은** 시세
        When: 한도 D+1 로 체결했을 때
        Then: 수익 청산이 아니라 기한 청산이다 (0 은 이익이 아니다)
        """
        # Given
        frame = _frame([_signal_day(), (99.5, 100.5, 98.0, ENTRY_PRICE)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=1)

        # Then
        assert result is not None
        assert result.reason == EXIT_LIMIT
        assert result.return_rate == pytest.approx(0.0, abs=RATE_TOLERANCE)

    def test_진입_위치가_범위_밖이면_거부한다(self) -> None:
        """
        목적: 잘못된 입력을 즉시 막는지 고정한다

        Given: 시세 길이를 넘는 진입 위치
        When: 체결을 요청했을 때
        Then: ValueError 가 난다
        """
        # Given
        frame = _frame([_signal_day(), (99.0, 100.0, 98.0, 99.0)])

        # When / Then
        with pytest.raises(ValueError, match="진입 위치"):
            simulate_signal(frame, 5, upward=False, hold_limit=1)

    def test_시세에_필수_컬럼이_없으면_거부한다(self) -> None:
        """
        목적: 장중 판정에 필요한 컬럼이 빠진 입력을 막는지 고정한다

        Given: 고가·저가가 없는 시세
        When: 체결을 요청했을 때
        Then: ValueError 가 난다
        """
        # Given
        frame = _frame([_signal_day(), (99.0, 100.0, 98.0, 99.0)]).drop(columns=[COL_HIGH, COL_LOW])

        # When / Then
        with pytest.raises(ValueError, match="필수 컬럼"):
            simulate_signal(frame, 0, upward=False, hold_limit=1)


class TestJudgementOrder:
    """판정 순서 계약 — 이 계층이 틀리는 방식"""

    def test_갭이_먼저고_장중이_나중이다(self) -> None:
        """
        목적: 시가 판정이 장중 판정보다 먼저인지 고정한다

        시가와 장중이 **둘 다** 손절선 아래인 날을 만들어 어느 쪽으로 체결되는지 본다.
        순서가 뒤바뀌면 손절선 가격(-5%)에 체결돼 손실이 실제보다 작게 나온다.

        Given: 시가 -8%, 저가 -12% 인 다음날
        When: 체결했을 때
        Then: 갭 청산이며 체결가는 **시가**다
        """
        # Given
        frame = _frame([_signal_day(), (92.0, 93.0, 88.0, 90.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=1)

        # Then
        assert result is not None
        assert result.reason == EXIT_GAP_STOP
        assert result.return_rate == pytest.approx(-0.08, abs=RATE_TOLERANCE)

    def test_손절이_이익_청산보다_먼저다(self) -> None:
        """
        목적: 장중 손절이 종가 이익보다 먼저 걸리는지 고정한다

        장중에 손절선을 지나갔다면 그 자리에서 이미 청산된 것이므로, 그날 종가가
        플러스로 끝났더라도 이익 청산이 아니다.

        Given: 장중 -7% 까지 밀렸다가 종가는 +1% 로 마감한 다음날
        When: 체결했을 때
        Then: 손절이다 (이익 청산이 아니다)
        """
        # Given
        frame = _frame([_signal_day(), (99.5, 101.5, 93.0, 101.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=1)

        # Then
        assert result is not None
        assert result.reason == EXIT_INTRADAY_STOP
        assert result.return_rate == pytest.approx(-STOP_LOSS_LEVEL, abs=RATE_TOLERANCE)


class TestTakeProfitSwitch:
    """익절 스위치 계약 — 옵션 만기일 매매가 이 함수를 함께 쓰기 위한 축

    두 매매의 차이는 **종가 익절 단계 하나뿐**이라 판정식을 두 벌 만들지 않고 스위치로 가른다.
    **기본값은 켜짐이며, 역방향 매매의 동작은 한 자리도 바뀌지 않아야 한다.**
    """

    def test_기본값은_익절_켜짐이다(self) -> None:
        """
        목적: 역방향 매매의 기존 동작이 기본값으로 유지되는지 고정한다

        **이 계약이 깨지면 확정된 규칙의 성적이 조용히 달라진다.**

        Given: 다음날 종가가 +2% 인 시세
        When: 스위치를 넘기지 않고 체결했을 때
        Then: 이익 청산이다 (D+1 에 나간다)
        """
        # Given
        frame = _frame([_signal_day(), (99.0, 103.0, 98.0, 102.0), (102.0, 105.0, 101.0, 104.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=2)

        # Then
        assert result is not None
        assert result.reason == EXIT_PROFIT
        assert result.hold_days == 1

    def test_익절을_끄면_이익이어도_한도까지_보유한다(self) -> None:
        """
        목적: 스위치가 실제로 익절 단계를 건너뛰는지 고정한다

        Given: D+1 에 +2%, D+2 에 +4% 인 시세
        When: `take_profit=False` 로 체결했을 때
        Then: D+1 의 +2% 가 아니라 **한도일의 +4%** 로 청산된다
        """
        # Given
        frame = _frame([_signal_day(), (99.0, 103.0, 98.0, 102.0), (102.0, 105.0, 101.0, 104.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=2, take_profit=False)

        # Then
        assert result is not None
        assert result.reason == EXIT_LIMIT
        assert result.hold_days == 2
        assert result.return_rate == pytest.approx(0.04, abs=RATE_TOLERANCE)

    def test_익절을_꺼도_손절은_그대로_걸린다(self) -> None:
        """
        목적: 스위치가 손절 경로를 건드리지 않는지 고정한다

        Given: D+1 에 장중 -7% 까지 밀린 시세
        When: `take_profit=False` 로 체결했을 때
        Then: 손절선 가격에 체결된다
        """
        # Given
        frame = _frame([_signal_day(), (99.5, 100.0, 93.0, 94.0), (94.0, 96.0, 93.5, 95.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=2, take_profit=False)

        # Then
        assert result is not None
        assert result.reason == EXIT_INTRADAY_STOP
        assert result.return_rate == pytest.approx(-STOP_LOSS_LEVEL, abs=RATE_TOLERANCE)

    def test_익절을_꺼도_갭_판정이_먼저다(self) -> None:
        """
        목적: 스위치가 판정 순서를 흔들지 않는지 고정한다 (엣지 케이스)

        Given: 시가가 -8% 로 열린 다음날
        When: `take_profit=False` 로 체결했을 때
        Then: 갭 청산이며 시가로 체결된다
        """
        # Given
        frame = _frame([_signal_day(), (92.0, 95.0, 90.0, 94.0), (94.0, 96.0, 93.0, 95.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=2, take_profit=False)

        # Then
        assert result is not None
        assert result.reason == EXIT_GAP_STOP
        assert result.return_rate == pytest.approx(-0.08, abs=RATE_TOLERANCE)
