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
- **보유 중 최악은 결과 수익률과 다른 값이다.** 진입 다음 날부터 실제 청산일까지의
  장중 최저점이며, 언제나 결과보다 나쁘거나 같다
"""

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.execution.constants import (
    EXIT_GAP_STOP,
    EXIT_INTRADAY_STOP,
    EXIT_LIMIT,
    EXIT_PROFIT,
)
from verify_lab.execution.trade_fill import simulate_signal
from verify_lab.studies.reverse.constants import HOLD_LIMIT, STOP_LOSS_LEVEL

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
        result = simulate_signal(frame, 0, upward=False, hold_limit=1, stop_level=STOP_LOSS_LEVEL)

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
        result = simulate_signal(frame, 0, upward=False, hold_limit=1, stop_level=STOP_LOSS_LEVEL)

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
        result = simulate_signal(frame, 0, upward=False, hold_limit=1, stop_level=STOP_LOSS_LEVEL)

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
        result = simulate_signal(frame, 0, upward=False, hold_limit=2, stop_level=STOP_LOSS_LEVEL)

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
        result = simulate_signal(frame, 0, upward=False, hold_limit=2, stop_level=STOP_LOSS_LEVEL)

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
            simulate_signal(frame, 0, upward=False, hold_limit=0, stop_level=STOP_LOSS_LEVEL)


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
        result = simulate_signal(frame, 0, upward=False, hold_limit=2, stop_level=STOP_LOSS_LEVEL)

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
        result = simulate_signal(frame, 0, upward=True, hold_limit=1, stop_level=STOP_LOSS_LEVEL)

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
        result = simulate_signal(frame, 0, upward=True, hold_limit=1, stop_level=STOP_LOSS_LEVEL)

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
        result = simulate_signal(frame, 0, upward=False, hold_limit=2, stop_level=STOP_LOSS_LEVEL)

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
        result = simulate_signal(frame, 0, upward=False, hold_limit=1, stop_level=STOP_LOSS_LEVEL)

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
            simulate_signal(frame, 5, upward=False, hold_limit=1, stop_level=STOP_LOSS_LEVEL)

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
            simulate_signal(frame, 0, upward=False, hold_limit=1, stop_level=STOP_LOSS_LEVEL)


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
        result = simulate_signal(frame, 0, upward=False, hold_limit=1, stop_level=STOP_LOSS_LEVEL)

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
        result = simulate_signal(frame, 0, upward=False, hold_limit=1, stop_level=STOP_LOSS_LEVEL)

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
        result = simulate_signal(frame, 0, upward=False, hold_limit=2, stop_level=STOP_LOSS_LEVEL)

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
        result = simulate_signal(frame, 0, upward=False, hold_limit=2, take_profit=False, stop_level=STOP_LOSS_LEVEL)

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
        result = simulate_signal(frame, 0, upward=False, hold_limit=2, take_profit=False, stop_level=STOP_LOSS_LEVEL)

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
        result = simulate_signal(frame, 0, upward=False, hold_limit=2, take_profit=False, stop_level=STOP_LOSS_LEVEL)

        # Then
        assert result is not None
        assert result.reason == EXIT_GAP_STOP
        assert result.return_rate == pytest.approx(-0.08, abs=RATE_TOLERANCE)


class TestNoStop:
    """무손절(`stop_level=None`) 경로

    `.claude/rules/trading.md` 가 **「손절이 무엇을 막았는가」의 대조축으로 무손절 성적을
    요구**한다. 그것을 낼 수 없으면 규칙이 인용한 실측(무손절 최악 -17.45%)을 코드로
    재현할 방법이 없고, 손절선 격자에 기준이 되는 행이 빠진다.

    **달력형 진입점은 이미 `None` 을 받았다** — 두 진입점의 손절선 타입이 갈려 있으면
    같은 격자를 매매법마다 다르게 내게 된다.
    """

    def test_갭이_열려도_손절하지_않는다(self) -> None:
        """
        목적: 무손절이면 1단계(시가 갭)를 건너뛴다.

        Given: 시가가 -8% 로 열렸다가 종가가 회복된 다음날
        When: `stop_level=None` 으로 체결했을 때
        Then: 갭 청산이 아니라 **종가 기준 이익 청산**이다
        """
        # Given
        frame = _frame([_signal_day(), (92.0, 102.0, 90.0, 101.0), (101.0, 103.0, 100.0, 102.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=HOLD_LIMIT, stop_level=None)

        # Then
        assert result is not None
        assert result.reason == EXIT_PROFIT
        assert result.return_rate == pytest.approx(0.01, abs=RATE_TOLERANCE)

    def test_장중에_크게_밀려도_한도까지_끈다(self) -> None:
        """
        목적: 무손절이면 2단계(장중 손절)도 건너뛰고 한도일 종가로 청산한다.

        **이것이 무손절 최악이 손절선보다 깊어지는 이유다** — 역방향 실측에서
        무손절 최악 -17.45% 대 -5% 손절 최악 -5.00% 였다.

        Given: 장중 -20% 까지 밀리고 종가도 손실인 이틀
        When: `stop_level=None` 으로 체결했을 때
        Then: 한도일 청산이며 한도일 **종가** 수익률이다
        """
        # Given
        frame = _frame([_signal_day(), (99.0, 99.5, 80.0, 90.0), (90.0, 92.0, 85.0, 88.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=2, stop_level=None)

        # Then
        assert result is not None
        assert result.reason == EXIT_LIMIT
        assert result.return_rate == pytest.approx(-0.12, abs=RATE_TOLERANCE)

    def test_손절선이_0이면_거부한다(self) -> None:
        """
        목적: **`0` 을 무손절로 읽지 않는다** (경계 조건).

        무손절은 `None` 이고 `0` 은 「진입가에 닿으면 손절」이라 뜻이 다르다. 한 값이 둘을
        겸하면 성적표의 `손절선(%)` 이 어느 쪽인지 구별되지 않는다.

        Given: 손절선 0
        When: 체결했을 때
        Then: ValueError
        """
        # Given
        frame = _frame([_signal_day(), (99.0, 101.0, 98.0, 100.5), (100.5, 102.0, 100.0, 101.0)])

        # When / Then
        with pytest.raises(ValueError, match="양수"):
            simulate_signal(frame, 0, upward=False, hold_limit=HOLD_LIMIT, stop_level=0.0)


class TestWorstHoldRate:
    """보유 중 최악 계약 — 「매도 시점 손실」과 「보유 중 감당한 손실」은 다른 값이다

    청산가만 보면 **-5% 로 끝난 체결과 -20% 까지 밀렸다가 -5% 로 끝난 체결이 같아 보인다.**
    회당 기대값 대비 감당해야 하는 손실이 전혀 다르므로 두 값을 갈라 낸다.

    **부등식 하나가 이 산식의 불변조건이다** — `보유 중 최악 <= 결과 수익률`.
    청산가는 보유 중에 실제로 지난 가격이고 보유 중 최악은 그것을 포함한 구간의 최솟값이므로,
    이 부등식이 깨지면 구간이나 부호가 틀린 것이다.
    """

    def test_보유_중_최악은_장중_저가로_잡힌다(self) -> None:
        """
        목적: 위로 거는 칸의 보유 중 최악이 **종가가 아니라 저가**임을 고정한다

        종가로 재면 장중에 밀렸다가 회복한 날이 통째로 빠져 **실제로 감당한 손실보다 얕게**
        나온다 — 손절 판정이 저가를 보는 것과 같은 이유다.

        Given: 장중 -12% 까지 밀렸다가 종가는 -1% 로 회복한 날
        When: 무손절로 위에 걸었을 때
        Then: 보유 중 최악이 **-12%** 다 (종가 기준이면 -1% 였다)
        """
        # Given
        frame = _frame([_signal_day(), (99.0, 99.5, 88.0, 99.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=1, stop_level=None)

        # Then
        assert result is not None
        assert result.worst_hold_rate == pytest.approx(-0.12, abs=RATE_TOLERANCE)

    def test_아래로_거는_칸은_고가로_잡힌다(self) -> None:
        """
        목적: 방향에 따라 어느 쪽이 손실인지 갈리는 것을 고정한다

        아래로 걸면 **주가가 오를 때 잃는다.** 저가를 보면 부호가 뒤집혀
        「가장 많이 번 지점」을 최악이라고 적게 된다.

        Given: 장중 +8% 까지 올랐다가 종가는 진입가인 날
        When: 무손절로 아래에 걸었을 때
        Then: 보유 중 최악이 **-8%** 다
        """
        # Given
        frame = _frame([_signal_day(), (100.0, 108.0, 99.0, 100.0)])

        # When
        result = simulate_signal(frame, 0, upward=True, hold_limit=1, stop_level=None)

        # Then
        assert result is not None
        assert result.worst_hold_rate == pytest.approx(-0.08, abs=RATE_TOLERANCE)

    def test_진입일_당일은_세지_않는다(self) -> None:
        """
        목적: 구간의 시작을 고정한다 (엣지 케이스)

        **진입가가 진입일 «종가»이므로 그날 장중은 이미 지나간 시간이다.** 그 저가를 세면
        사지도 않은 구간의 손실이 성적에 실린다.

        Given: 진입일 장중이 -30% 까지 밀렸고 다음날은 아무 일도 없는 시세
        When: 무손절로 위에 걸었을 때
        Then: 보유 중 최악이 진입일 저가(-30%)가 아니라 다음날 저가(-1%)다
        """
        # Given
        frame = _frame([(100.0, 100.0, 70.0, ENTRY_PRICE), (100.0, 100.5, 99.0, 100.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=1, stop_level=None)

        # Then
        assert result is not None
        assert result.worst_hold_rate == pytest.approx(-0.01, abs=RATE_TOLERANCE)

    def test_익절로_일찍_나가면_그_전까지만_본다(self) -> None:
        """
        목적: 구간의 끝이 **한도일이 아니라 실제 청산일**임을 고정한다

        역방향 매매는 이익이 나면 그날 청산한다. 청산 뒤의 날을 세면 **들고 있지도 않은
        기간의 낙폭**이 성적에 실린다.

        Given: 다음날 +2% 로 익절되고, 그 뒤에 -20% 가 오는 시세
        When: 한도를 3일로 두고 위에 걸었을 때
        Then: 청산일까지만 보므로 보유 중 최악이 -1% 다
        """
        # Given
        frame = _frame(
            [_signal_day(), (100.0, 102.5, 99.0, 102.0), (100.0, 100.0, 80.0, 81.0), (81.0, 82.0, 79.0, 80.0)]
        )

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=3, stop_level=None)

        # Then
        assert result is not None
        assert result.reason == EXIT_PROFIT
        assert result.hold_days == 1
        assert result.worst_hold_rate == pytest.approx(-0.01, abs=RATE_TOLERANCE)

    def test_장중_손절은_체결가에서_끊긴다(self) -> None:
        """
        목적: **손절이 «막아 준» 몫을 「감당한 손실」로 적지 않는다** (2026-09-17 사용자 확정)

        손절이 발동한 순간 포지션이 끝나므로 그 뒤의 하락은 감당한 적이 없다.
        그날 저가까지 세면 **손절을 건 칸이 실제보다 나빠 보인다** — 실측으로 역방향
        KODEX 200 이 -5.00% 대신 -13.55% 로 나왔다. 그 -13.55% 는 같은 칸의 **무손절 행이
        말해야 하는 값**이고 실제로 거기 실린다.

        Given: 장중 -7% 까지 밀린 다음날
        When: 손절선 -5% 로 위에 걸었을 때
        Then: -5% 에 체결되고 보유 중 최악도 **-5%** 다 (-7% 가 아니다)
        """
        # Given
        frame = _frame([_signal_day(), (99.5, 100.0, 93.0, 94.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=1, stop_level=STOP_LOSS_LEVEL)

        # Then
        assert result is not None
        assert result.reason == EXIT_INTRADAY_STOP
        assert result.return_rate == pytest.approx(-STOP_LOSS_LEVEL, abs=RATE_TOLERANCE)
        assert result.worst_hold_rate == pytest.approx(-STOP_LOSS_LEVEL, abs=RATE_TOLERANCE)

    def test_갭_청산은_시가에서_끊긴다(self) -> None:
        """
        목적: 같은 규칙을 **갭 청산**에서 고정한다

        갭은 시가로 나가므로 그 시가까지가 감당한 것이고, 그날 더 빠진 것은 나온 뒤의 일이다.
        **갭이 손절선보다 더 잃는다는 사실은 그대로다** — 여기서는 -5% 가 아니라 -9% 다.

        Given: 다음날 시가가 -9% 로 열리고 장중에 -15% 까지 밀린 시세
        When: 손절선 -5% 로 위에 걸었을 때
        Then: 갭으로 -9% 에 나가고 보유 중 최악도 **-9%** 다
        """
        # Given
        frame = _frame([_signal_day(), (91.0, 92.0, 85.0, 90.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=1, stop_level=STOP_LOSS_LEVEL)

        # Then
        assert result is not None
        assert result.reason == EXIT_GAP_STOP
        assert result.return_rate == pytest.approx(-0.09, abs=RATE_TOLERANCE)
        assert result.worst_hold_rate == pytest.approx(-0.09, abs=RATE_TOLERANCE)

    def test_손절_전에_밀린_날은_그대로_센다(self) -> None:
        """
        목적: 「체결에서 끊는다」가 **그 전날까지 지우는 것으로 과잉 적용되지 않게** 짝으로 둔다

        손절 봉 «이전» 의 날들은 온전히 들고 있었으므로 그 장중이 그대로 견딘 값이다.
        앞의 두 테스트만 있으면 구간을 통째로 체결가로 덮는 구현도 통과한다.

        Given: 첫날 장중 -4% 까지 밀렸다가 종가 회복, 이튿날 장중 -5.5% 까지 밀려 종가 -5% 인 시세
        When: 손절선 -5% 와 -7% 로 각각 위에 걸었을 때
        Then: -5% 는 이튿날 손절로 끊겨 보유 중 최악이 **-5%** 이고,
              -7% 는 손절이 안 걸려 이튿날 장중 **-5.5%** 가 그대로 드러난다
        """
        # Given
        frame = _frame([_signal_day(), (100.0, 100.0, 96.0, 99.0), (99.0, 99.0, 94.5, 95.0)])

        # When
        tight = simulate_signal(frame, 0, upward=False, hold_limit=2, stop_level=STOP_LOSS_LEVEL)
        wide = simulate_signal(frame, 0, upward=False, hold_limit=2, stop_level=0.07)

        # Then
        assert tight is not None and wide is not None
        assert tight.reason == EXIT_INTRADAY_STOP
        assert tight.worst_hold_rate == pytest.approx(-STOP_LOSS_LEVEL, abs=RATE_TOLERANCE)
        assert wide.reason == EXIT_LIMIT
        assert wide.worst_hold_rate == pytest.approx(-0.055, abs=RATE_TOLERANCE)

    def test_한_번도_밀리지_않으면_양수다(self) -> None:
        """
        목적: **0 으로 깎지 않는다**는 정책을 고정한다 (엣지 케이스)

        보유 내내 진입가 위였다면 보유 중 최악은 양수다. 0 으로 깎으면
        「한 번은 본전까지 내려왔다」는 없는 사실을 만들게 된다 —
        기존 `최악(%)` 도 같은 이유로 양수가 나올 수 있다.

        Given: 저가조차 진입가보다 높았던 다음날
        When: 무손절로 위에 걸었을 때
        Then: 보유 중 최악이 +1% 다
        """
        # Given
        frame = _frame([_signal_day(), (101.0, 103.0, 101.0, 102.0)])

        # When
        result = simulate_signal(frame, 0, upward=False, hold_limit=1, stop_level=None)

        # Then
        assert result is not None
        assert result.worst_hold_rate == pytest.approx(0.01, abs=RATE_TOLERANCE)
