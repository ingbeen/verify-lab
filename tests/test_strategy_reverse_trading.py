"""역방향 매매 규칙의 체결 계약을 고정한다.

이 계층이 틀리는 방식은 **판정 순서가 뒤바뀌는 것**이다. 시가·장중·종가를 이 순서로 보지 않으면
갭 하락한 날이 장중 손절가로 체결된 것처럼 계산되어 **손실이 실제보다 작게 나온다.**
예외는 나지 않고 표도 정상으로 보이므로 손계산으로 박는다.

핵심 계약은 다섯 가지다.
- 손절은 **단계별로 따로** 발동한다. 얕은 선만 걸리고 깊은 선은 살아남는다
- 갭 청산은 **손절선보다 더 잃는다**. 시가가 이미 아래면 그 시가가 체결가다
- 손절선은 **진입가 기준**이며 보유 기간 내내 갱신하지 않는다
- 이익이 나면 **남은 전량**이 그날 종가로 청산된다
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
    HOLD_LIMITS,
    STOP_LOSS_LEVELS,
)
from verify_lab.strategy.reverse_trading import average_return, simulate_signal

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


class TestStopLossSplit:
    """손절 3분할 계약"""

    def test_얕은_손절선만_걸리고_깊은_선은_살아남는다(self) -> None:
        """
        목적: 손절이 단계별로 따로 발동하는지 고정한다 (3분할의 존재 이유)

        Given: 장중 -5.5% 까지 밀렸다가 종가는 +0.8% 로 마감한 다음날
        When: 손절선 3단계로 체결했을 때
        Then: -4%·-5% 는 손절되고 -6% 는 살아남아 종가로 수익 청산된다
        """
        # Given
        frame = _frame([_signal_day(), (100.0, 101.0, 94.5, 100.8)])

        # When
        legs = simulate_signal(frame, 0, upward=False, hold_limit=1)

        # Then
        assert [leg.reason for leg in legs] == [EXIT_INTRADAY_STOP, EXIT_INTRADAY_STOP, EXIT_PROFIT]
        assert legs[0].return_rate == pytest.approx(-0.04, abs=RATE_TOLERANCE)
        assert legs[1].return_rate == pytest.approx(-0.05, abs=RATE_TOLERANCE)
        assert legs[2].return_rate == pytest.approx(0.008, abs=RATE_TOLERANCE)

    def test_장중_손절은_손절선_가격에_체결된다(self) -> None:
        """
        목적: 장중 손절의 체결가가 저가가 아니라 손절선임을 고정한다

        Given: 장중 -9% 까지 밀린 다음날
        When: 체결했을 때
        Then: 세 조각이 각각 -4%·-5%·-6% 로 체결된다 (-9% 가 아니다)
        """
        # Given
        frame = _frame([_signal_day(), (100.0, 100.0, 91.0, 92.0)])

        # When
        legs = simulate_signal(frame, 0, upward=False, hold_limit=1)

        # Then
        assert [leg.return_rate for leg in legs] == pytest.approx([-0.04, -0.05, -0.06], abs=RATE_TOLERANCE)
        assert all(leg.reason == EXIT_INTRADAY_STOP for leg in legs)

    def test_손절선이_중복되면_거부한다(self) -> None:
        """
        목적: 같은 손절선을 두 번 넘기는 실수를 막는다 (경계 조건)

        Given: 중복된 손절선 목록
        When: 체결을 시도했을 때
        Then: ValueError 가 난다
        """
        # Given
        frame = _frame([_signal_day(), (100.0, 101.0, 99.0, 100.5)])

        # When / Then
        with pytest.raises(ValueError, match="중복"):
            simulate_signal(frame, 0, upward=False, hold_limit=1, stop_levels=(0.04, 0.04))


class TestGapExit:
    """갭 청산 계약"""

    def test_갭_청산은_손절선보다_더_잃는다(self) -> None:
        """
        목적: 시가가 이미 손절선 아래면 그 시가가 체결가임을 고정한다

        **이 계약이 깨지면 손실이 실제보다 작게 계산되는데 표는 정상으로 보인다.**

        Given: 시가가 -4.89% 로 열린 다음날
        When: 체결했을 때
        Then: -4% 조각이 -4% 가 아니라 **-4.89%** 로 체결된다
        """
        # Given
        frame = _frame([_signal_day(), (95.11, 95.11, 90.0, 91.0)])

        # When
        legs = simulate_signal(frame, 0, upward=False, hold_limit=1)

        # Then
        assert legs[0].reason == EXIT_GAP_STOP
        assert legs[0].return_rate == pytest.approx(-0.0489, abs=RATE_TOLERANCE)
        assert legs[0].return_rate < -legs[0].stop_level

    def test_갭이_모든_손절선_아래면_세_조각이_같은_시가로_나간다(self) -> None:
        """
        목적: 깊은 갭에서 분할이 아무 도움이 안 된다는 사실을 고정한다 (경계 조건)

        Given: 시가가 -8% 로 열린 다음날
        When: 체결했을 때
        Then: 세 조각 모두 -8% 로 갭 청산된다
        """
        # Given
        frame = _frame([_signal_day(), (92.0, 92.0, 90.0, 91.0)])

        # When
        legs = simulate_signal(frame, 0, upward=False, hold_limit=1)

        # Then
        assert all(leg.reason == EXIT_GAP_STOP for leg in legs)
        assert [leg.return_rate for leg in legs] == pytest.approx([-0.08] * 3, abs=RATE_TOLERANCE)


class TestHoldLimit:
    """보유 한도 계약"""

    def test_이익이면_남은_전량이_그날_청산된다(self) -> None:
        """
        목적: 이익이 나면 한도와 무관하게 그날 끝난다는 계약을 고정한다

        Given: 다음날 종가가 +2% 인 시세와 한도 3일
        When: 체결했을 때
        Then: 세 조각이 D+1 에 수익 청산되고 보유일이 1이다
        """
        # Given
        frame = _frame([_signal_day(), (100.0, 103.0, 99.0, 102.0), (102.0, 105.0, 101.0, 104.0)])

        # When
        legs = simulate_signal(frame, 0, upward=False, hold_limit=3)

        # Then
        assert all(leg.reason == EXIT_PROFIT for leg in legs)
        assert all(leg.hold_days == 1 for leg in legs)

    def test_손실이면_한도까지_보유하고_종가에_전량_청산된다(self) -> None:
        """
        목적: 한도일에는 손실이어도 나간다는 계약을 고정한다

        Given: 이틀 내내 소폭 손실이고 손절선에는 안 닿는 시세
        When: 한도 2일로 체결했을 때
        Then: D+2 종가로 기한 청산되고 보유일이 2다
        """
        # Given
        frame = _frame([_signal_day(), (100.0, 100.0, 98.0, 99.0), (99.0, 99.5, 97.5, 98.0)])

        # When
        legs = simulate_signal(frame, 0, upward=False, hold_limit=2)

        # Then
        assert all(leg.reason == EXIT_LIMIT for leg in legs)
        assert all(leg.hold_days == 2 for leg in legs)
        assert legs[0].return_rate == pytest.approx(-0.02, abs=RATE_TOLERANCE)

    def test_한도를_늘려도_이익_신호는_결과가_같다(self) -> None:
        """
        목적: 한도 축이 손실 신호에서만 갈린다는 계약을 고정한다

        Given: D+1 종가가 이익인 시세
        When: 한도 1·2·3 으로 각각 체결했을 때
        Then: 세 결과가 완전히 같다
        """
        # Given
        frame = _frame(
            [_signal_day(), (100.0, 103.0, 99.0, 102.0), (102.0, 103.0, 95.0, 96.0), (96.0, 97.0, 90.0, 91.0)]
        )

        # When
        results = [simulate_signal(frame, 0, upward=False, hold_limit=limit) for limit in HOLD_LIMITS]

        # Then
        assert all(result == results[0] for result in results)

    def test_한도를_늘리면_보유일이_줄지_않는다(self) -> None:
        """
        목적: 한도 축의 단조성을 고정한다

        Given: 손실이 이어지다 D+3 에 반등하는 시세
        When: 한도 1·2·3 으로 각각 체결했을 때
        Then: 보유일이 1 → 2 → 3 으로 늘어난다
        """
        # Given
        frame = _frame(
            [_signal_day(), (100.0, 100.0, 98.0, 99.0), (99.0, 99.5, 97.5, 98.0), (98.0, 102.0, 97.5, 101.0)]
        )

        # When
        holds = [max(leg.hold_days for leg in simulate_signal(frame, 0, upward=False, hold_limit=n)) for n in (1, 2, 3)]

        # Then
        assert holds == [1, 2, 3]


class TestStopBase:
    """손절선 기준 계약"""

    def test_손절선은_진입가_기준이며_갱신되지_않는다(self) -> None:
        """
        목적: 손절선을 매일 다시 잡지 않는다는 계약을 고정한다

        기준을 전일 종가로 갱신하면 손실이 이어질 때 손절선이 따라 내려가
        **최악이 무제한으로 열린다.**

        Given: D+1 에 -3%(손절 미발동), D+2 에 진입가 대비 -5.5% 인 시세
        When: 한도 2일로 체결했을 때
        Then: D+2 에 -4%·-5% 가 손절된다. D+1 종가(-3%) 기준이었다면 발동하지 않았을 값이다
        """
        # Given
        frame = _frame([_signal_day(), (100.0, 100.0, 96.5, 97.0), (97.0, 97.0, 94.5, 95.0)])

        # When
        legs = simulate_signal(frame, 0, upward=False, hold_limit=2)

        # Then
        assert legs[0].reason == EXIT_INTRADAY_STOP
        assert legs[0].hold_days == 2
        assert legs[0].return_rate == pytest.approx(-0.04, abs=RATE_TOLERANCE)
        assert legs[2].reason == EXIT_LIMIT


class TestDirection:
    """방향 계약"""

    def test_상승_방향_신호는_고가로_손절을_판정한다(self) -> None:
        """
        목적: 폭등 신호가 인버스 진입이라는 사실을 고정한다

        원지수가 **오르면** 손실이므로 저가가 아니라 고가를 본다.

        Given: 다음날 고가가 +6%, 종가가 +1% 인 시세
        When: 상승 방향 신호로 체결했을 때
        Then: 세 조각 모두 손절되고 부호가 뒤집혀 있다
        """
        # Given
        frame = _frame([_signal_day(), (100.0, 106.0, 99.0, 101.0)])

        # When
        legs = simulate_signal(frame, 0, upward=True, hold_limit=1)

        # Then
        assert [leg.return_rate for leg in legs] == pytest.approx([-0.04, -0.05, -0.06], abs=RATE_TOLERANCE)

    def test_상승_방향_신호는_원지수_하락이_이익이다(self) -> None:
        """
        목적: 부호 정규화를 고정한다

        Given: 다음날 종가가 원지수 기준 -3% 인 시세
        When: 상승 방향 신호로 체결했을 때
        Then: 수익률이 +3% 다
        """
        # Given
        frame = _frame([_signal_day(), (100.0, 100.5, 96.0, 97.0)])

        # When
        legs = simulate_signal(frame, 0, upward=True, hold_limit=1)

        # Then
        assert all(leg.return_rate == pytest.approx(0.03, abs=RATE_TOLERANCE) for leg in legs)
        assert all(leg.reason == EXIT_PROFIT for leg in legs)


class TestBoundary:
    """경계 조건"""

    def test_한도가_데이터_끝을_넘어가면_빈_목록을_낸다(self) -> None:
        """
        목적: 부분 체결을 남기지 않는다는 계약을 고정한다

        부분 체결을 남기면 한도마다 표본이 달라져 조합끼리 비교할 수 없게 된다.

        Given: 신호일 다음에 하루뿐인 시세
        When: 한도 3일로 체결했을 때
        Then: 빈 목록이 나온다
        """
        # Given
        frame = _frame([_signal_day(), (100.0, 100.0, 98.0, 99.0)])

        # When
        legs = simulate_signal(frame, 0, upward=False, hold_limit=3)

        # Then
        assert legs == []

    def test_손절선에_정확히_닿으면_손절된다(self) -> None:
        """
        목적: 경계값 처리를 고정한다 (저가가 손절선과 같은 경우)

        Given: 저가가 정확히 -4.00% 인 다음날
        When: 체결했을 때
        Then: -4% 조각이 손절된다
        """
        # Given
        frame = _frame([_signal_day(), (100.0, 100.0, 96.0, 99.0)])

        # When
        legs = simulate_signal(frame, 0, upward=False, hold_limit=1)

        # Then
        assert legs[0].reason == EXIT_INTRADAY_STOP
        assert legs[1].reason == EXIT_LIMIT

    def test_종가가_정확히_진입가면_이익이_아니다(self) -> None:
        """
        목적: 보합을 이익으로 세지 않는다는 계약을 고정한다 (경계 조건)

        Given: 다음날 종가가 진입가와 같은 시세
        When: 한도 1일로 체결했을 때
        Then: 수익 청산이 아니라 기한 청산이고 수익률이 0 이다
        """
        # Given
        frame = _frame([_signal_day(), (100.0, 101.0, 99.0, ENTRY_PRICE)])

        # When
        legs = simulate_signal(frame, 0, upward=False, hold_limit=1)

        # Then
        assert all(leg.reason == EXIT_LIMIT for leg in legs)
        assert all(leg.return_rate == pytest.approx(0.0, abs=RATE_TOLERANCE) for leg in legs)

    @pytest.mark.parametrize(
        ("hold_limit", "stop_levels", "match"),
        [
            (0, STOP_LOSS_LEVELS, "한도"),
            (1, (), "비어"),
            (1, (-0.04,), "양수"),
        ],
    )
    def test_잘못된_인자를_즉시_거부한다(self, hold_limit: int, stop_levels: tuple[float, ...], match: str) -> None:
        """
        목적: 입력 검증을 고정한다

        Given: 잘못된 한도 또는 손절선
        When: 체결을 시도했을 때
        Then: ValueError 가 난다
        """
        # Given
        frame = _frame([_signal_day(), (100.0, 101.0, 99.0, 100.5)])

        # When / Then
        with pytest.raises(ValueError, match=match):
            simulate_signal(frame, 0, upward=False, hold_limit=hold_limit, stop_levels=stop_levels)

    def test_시세에_필수_컬럼이_없으면_거부한다(self) -> None:
        """
        목적: 장중 판정에 고가·저가가 반드시 필요함을 고정한다

        Given: 저가 컬럼이 빠진 시세
        When: 체결을 시도했을 때
        Then: ValueError 가 난다
        """
        # Given
        frame = _frame([_signal_day(), (100.0, 101.0, 99.0, 100.5)]).drop(columns=[COL_LOW])

        # When / Then
        with pytest.raises(ValueError, match="필수 컬럼"):
            simulate_signal(frame, 0, upward=False, hold_limit=1)


class TestAverageReturn:
    """균등 분할 계약"""

    def test_신호_수익률은_조각_수익률의_평균이다(self) -> None:
        """
        목적: 자금을 3등분했으므로 조각을 그대로 세지 않는다는 계약을 고정한다

        조각을 표본으로 세면 표본이 세 배로 부풀고 승률이 왜곡된다.

        Given: -4%·-5% 손절되고 -6% 가 +0.8% 로 살아남은 체결
        When: 신호 수익률을 냈을 때
        Then: 세 값의 단순 평균이다
        """
        # Given
        frame = _frame([_signal_day(), (100.0, 101.0, 94.5, 100.8)])

        # When
        value = average_return(simulate_signal(frame, 0, upward=False, hold_limit=1))

        # Then
        assert value == pytest.approx((-0.04 - 0.05 + 0.008) / 3, abs=RATE_TOLERANCE)

    def test_체결이_비면_거부한다(self) -> None:
        """
        목적: 빈 체결에서 0 을 돌려주지 않는다는 계약을 고정한다 (경계 조건)

        Given: 빈 체결 목록
        When: 평균을 냈을 때
        Then: ValueError 가 난다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="비어"):
            average_return([])
