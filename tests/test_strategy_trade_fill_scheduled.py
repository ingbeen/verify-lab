"""정해진 날까지 들고 가는 체결(`simulate_scheduled_trade`)의 계약을 고정한다.

**옵션 만기일과 월말이 함께 쓰는 경로다.** 둘 다 달력이 지목한 날에 나가므로 중간 익절이
없고, 차이는 그 날을 누가 정하느냐뿐이다.

이 매매는 역방향 매매와 **한 가지만 다르다** — 중간 익절이 없다.
청산이 달력 기준(다음 주 금요일)이라 이익이 나도 그날까지 들고 간다.
나머지(진입가 기준 고정 손절선, 시가 → 장중 순서, 방향별 고가·저가)는 같은 판정식을 쓴다.

핵심 계약은 일곱 가지다.
- 손절이 안 걸리면 **이익이어도 청산일 종가**로 나간다 (역방향과 갈리는 자리)
- 갭 청산은 **손절선보다 더 잃는다**. 시가가 이미 아래면 그 시가가 체결가다
- 장중 손절은 **손절선 가격**에 체결된다
- **아래로 거는 칸은 고가**로, **위로 거는 칸은 저가**로 손절을 판정한다
- **무손절**이면 얼마나 밀려도 청산일까지 보유한다
- 청산일 이후의 데이터를 잘라도 결과가 같다 (**미래 참조 감시**)
- **음수 진입 위치는 두 경로 모두에서 거부한다.** `iloc[-1]` 이 뒤에서 세어 마지막 행을
  진입가로 잡으므로, 막지 않으면 무손절 경로가 **예외 없이** 엉뚱한 체결을 만든다
- **보유 중 최악은 결과와 따로 잰다.** ETF 는 장중 고가·저가로, 종가 하나뿐인 지수는
  종가로 재며 **기준을 가르는 것은 `price_column` 하나**다. 보유 구간 안의 0 이하 가격은
  거부한다 — 진입가·청산가 검사는 양 끝만 보기 때문이다
"""

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VALUE, COL_VOLUME
from verify_lab.execution.constants import EXIT_GAP_STOP, EXIT_INTRADAY_STOP, EXIT_LIMIT
from verify_lab.execution.trade_fill import resolve_positions, simulate_scheduled_trade

# 손계산을 쉽게 하려고 진입가를 100 으로 둔다
ENTRY_PRICE = 100.0

# 이 파일에서 쓰는 손절선. 프로덕션 기본값과 무관하게 테스트가 값을 명시한다 —
# 만기 매매의 손절선은 아직 확정되지 않았고 격자로 재는 중이다
STOP_LEVEL = 0.05

# 수익률 비교 허용오차 (tests/CLAUDE.md — 수학적 정확 계산)
RATE_TOLERANCE = 1e-12


def _frame(bars: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """(시가, 고가, 저가, 종가) 목록으로 시세를 만든다.

    첫 행이 진입일(만기일)이며 종가가 진입가다.

    Args:
        bars: 봉 목록

    Returns:
        날짜 오름차순 시세
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


def _entry_day() -> tuple[float, float, float, float]:
    """진입일 봉. 종가가 진입가가 된다.

    Returns:
        진입일의 (시가, 고가, 저가, 종가)
    """
    return (ENTRY_PRICE, ENTRY_PRICE, ENTRY_PRICE, ENTRY_PRICE)


def _flat_day() -> tuple[float, float, float, float]:
    """아무 일도 없는 날. 손절 판정에 걸리지 않는다.

    Returns:
        진입가 근처에서 움직인 봉
    """
    return (100.0, 100.5, 99.5, 100.0)


class TestScheduledExit:
    """달력 청산 계약 — 역방향 매매와 갈리는 자리"""

    def test_이익이_나도_청산일까지_보유한다(self) -> None:
        """
        목적: **중간 익절이 없다**는 이 매매의 정의를 고정한다

        역방향 매매는 종가가 진입가 위면 그날 청산한다. 이 매매는 청산이 달력 기준이라
        그러지 않는다. **이 계약이 깨지면 성적이 실제보다 좋게 나온다** — 오른 날마다
        이익을 확정하고 내린 날은 끌고 가는 것이 되기 때문이다.

        Given: 다음날 +3% 로 올랐고 청산일에는 +1% 인 시세
        When: 청산일을 3일 뒤로 두고 아래가 아닌 위로 걸었을 때
        Then: +3% 가 아니라 **청산일 종가 +1%** 로 나간다
        """
        # Given
        frame = _frame([_entry_day(), (100.0, 103.5, 100.0, 103.0), _flat_day(), (100.0, 101.5, 99.0, 101.0)])

        # When
        result = simulate_scheduled_trade(frame, 0, 3, bet_down=False, stop_level=STOP_LEVEL)

        # Then
        assert result is not None
        assert result.reason == EXIT_LIMIT
        assert result.return_rate == pytest.approx(0.01, abs=RATE_TOLERANCE)

    def test_손실이어도_청산일_종가로_나간다(self) -> None:
        """
        목적: 손절선에 닿지 않은 손실은 청산일까지 간다는 계약을 고정한다

        Given: 손절선(-5%) 안쪽에서 -2% 로 끝난 청산일
        When: 위로 걸었을 때
        Then: -2% 로 청산된다
        """
        # Given
        frame = _frame([_entry_day(), _flat_day(), (99.0, 99.5, 97.5, 98.0)])

        # When
        result = simulate_scheduled_trade(frame, 0, 2, bet_down=False, stop_level=STOP_LEVEL)

        # Then
        assert result is not None
        assert result.reason == EXIT_LIMIT
        assert result.return_rate == pytest.approx(-0.02, abs=RATE_TOLERANCE)

    def test_보유일수는_진입에서_청산까지의_거래일_수다(self) -> None:
        """
        목적: 보유일수가 신호마다 다르다는 사실을 고정한다

        미국은 만기 다음 주에 휴장이 잦아 4거래일인 달이 넷 중 하나꼴이다.

        Given: 청산 위치가 진입에서 4거래일 뒤인 시세
        When: 체결했을 때
        Then: 보유일수가 4 다
        """
        # Given
        frame = _frame([_entry_day(), _flat_day(), _flat_day(), _flat_day(), _flat_day()])

        # When
        result = simulate_scheduled_trade(frame, 0, 4, bet_down=False, stop_level=STOP_LEVEL)

        # Then
        assert result is not None
        assert result.hold_days == 4


class TestStopOrder:
    """판정 순서 계약 — 시가 → 장중 → 청산일"""

    def test_갭_청산은_손절선보다_더_잃는다(self) -> None:
        """
        목적: 시가 판정이 장중 판정보다 먼저라는 순서를 고정한다

        **이 계약이 깨지면 손실이 실제보다 작게 나온다.** 시가가 이미 손절선 아래인데
        장중 판정을 먼저 하면 -5% 에 체결된 것으로 계산된다.

        Given: 다음날 시가가 -8% 로 열린 시세
        When: 손절선 -5% 로 체결했을 때
        Then: -5% 가 아니라 **시가 그대로 -8%** 에 청산된다
        """
        # Given
        frame = _frame([_entry_day(), (92.0, 95.0, 90.0, 94.0), _flat_day()])

        # When
        result = simulate_scheduled_trade(frame, 0, 2, bet_down=False, stop_level=STOP_LEVEL)

        # Then
        assert result is not None
        assert result.reason == EXIT_GAP_STOP
        assert result.return_rate == pytest.approx(-0.08, abs=RATE_TOLERANCE)

    def test_장중_손절은_손절선_가격에_체결된다(self) -> None:
        """
        목적: 장중 손절의 체결가를 고정한다

        Given: 시가는 손절선 위인데 장중에 -7% 까지 밀린 다음날
        When: 손절선 -5% 로 체결했을 때
        Then: 실제 저가(-7%)가 아니라 **손절선 가격(-5%)** 에 체결된다
        """
        # Given
        frame = _frame([_entry_day(), (99.5, 100.0, 93.0, 94.0), _flat_day()])

        # When
        result = simulate_scheduled_trade(frame, 0, 2, bet_down=False, stop_level=STOP_LEVEL)

        # Then
        assert result is not None
        assert result.reason == EXIT_INTRADAY_STOP
        assert result.return_rate == pytest.approx(-STOP_LEVEL, abs=RATE_TOLERANCE)

    def test_손절은_청산일_전에_걸리면_그날_끝난다(self) -> None:
        """
        목적: 손절이 걸린 뒤 남은 날을 보지 않는다는 계약을 고정한다

        Given: 2일차에 손절선을 터치하고 3일차(청산일)에 크게 반등한 시세
        When: 체결했을 때
        Then: 반등을 먹지 못하고 **2일차 손절가**로 끝난다
        """
        # Given
        frame = _frame([_entry_day(), (99.5, 100.0, 94.0, 95.0), (110.0, 115.0, 109.0, 114.0)])

        # When
        result = simulate_scheduled_trade(frame, 0, 2, bet_down=False, stop_level=STOP_LEVEL)

        # Then
        assert result is not None
        assert result.reason == EXIT_INTRADAY_STOP
        assert result.hold_days == 1


class TestDirection:
    """방향 계약 — 아래로 걸면 고가가 손실이다"""

    def test_아래로_거는_칸은_고가로_손절을_판정한다(self) -> None:
        """
        목적: 「아래」 칸의 손실 방향을 고정한다

        미국 9월 세 칸이 여기 해당한다. 원지수가 **오르면** 손실이므로 고가를 본다.

        Given: 다음날 고가가 +7% 까지 오른 시세 (저가는 손절선 밖)
        When: 아래로 걸고 손절선 -5% 로 체결했을 때
        Then: 손절된다
        """
        # Given
        frame = _frame([_entry_day(), (100.5, 107.0, 100.0, 106.0), _flat_day()])

        # When
        result = simulate_scheduled_trade(frame, 0, 2, bet_down=True, stop_level=STOP_LEVEL)

        # Then
        assert result is not None
        assert result.reason == EXIT_INTRADAY_STOP
        assert result.return_rate == pytest.approx(-STOP_LEVEL, abs=RATE_TOLERANCE)

    def test_아래로_거는_칸은_원지수가_내리면_이익이다(self) -> None:
        """
        목적: 「아래」 칸의 수익 부호를 고정한다

        **이 값은 원지수 부호를 뒤집은 것이지 인버스 상품의 손익이 아니다.**
        일간 복리·보수·괴리율은 반영되지 않는다.

        Given: 청산일 종가가 -3% 인 시세
        When: 아래로 걸었을 때
        Then: **+3%** 로 청산된다
        """
        # Given
        frame = _frame([_entry_day(), _flat_day(), (98.0, 98.5, 96.5, 97.0)])

        # When
        result = simulate_scheduled_trade(frame, 0, 2, bet_down=True, stop_level=STOP_LEVEL)

        # Then
        assert result is not None
        assert result.return_rate == pytest.approx(0.03, abs=RATE_TOLERANCE)

    def test_위로_거는_칸은_저가로_손절을_판정한다(self) -> None:
        """
        목적: 「위」 칸의 손실 방향을 고정한다

        DIA 12월·SPY 12월·KODEX 200 9월이 여기 해당한다.

        Given: 다음날 저가가 -7% 까지 밀린 시세 (고가는 손절선 밖)
        When: 위로 걸고 손절선 -5% 로 체결했을 때
        Then: 손절된다
        """
        # Given
        frame = _frame([_entry_day(), (99.5, 100.0, 93.0, 94.0), _flat_day()])

        # When
        result = simulate_scheduled_trade(frame, 0, 2, bet_down=False, stop_level=STOP_LEVEL)

        # Then
        assert result is not None
        assert result.reason == EXIT_INTRADAY_STOP

    def test_위로_거는_칸은_고가가_올라도_손절되지_않는다(self) -> None:
        """
        목적: 방향을 뒤집어 판정하지 않는지 고정한다 (엣지 케이스)

        Given: 다음날 고가가 +9% 까지 오른 시세
        When: 위로 걸었을 때
        Then: 손절되지 않고 청산일까지 간다
        """
        # Given
        frame = _frame([_entry_day(), (100.5, 109.0, 100.0, 108.0), (108.0, 108.5, 107.0, 107.0)])

        # When
        result = simulate_scheduled_trade(frame, 0, 2, bet_down=False, stop_level=STOP_LEVEL)

        # Then
        assert result is not None
        assert result.reason == EXIT_LIMIT
        assert result.return_rate == pytest.approx(0.07, abs=RATE_TOLERANCE)


class TestNoStop:
    """무손절 계약 — 손절이 무엇을 막았는지 재기 위한 대조축"""

    def test_무손절이면_얼마나_밀려도_청산일까지_보유한다(self) -> None:
        """
        목적: 무손절 행이 실제로 손절을 안 한다는 계약을 고정한다

        `.claude/rules/trading.md` 가 **무손절 성적을 함께 산출하도록** 요구한다 —
        손절의 실질 효용은 수익이 아니라 최악 통제이므로 대조가 없으면 보일 수 없다.

        Given: 중간에 -20% 까지 밀렸다가 청산일에 -6% 로 끝난 시세
        When: 손절선을 None 으로 두었을 때
        Then: **-6%** 로 청산된다 (손절선이 있었다면 -20% 또는 -5% 였다)
        """
        # Given
        frame = _frame([_entry_day(), (95.0, 96.0, 80.0, 82.0), (90.0, 95.0, 89.0, 94.0)])

        # When
        result = simulate_scheduled_trade(frame, 0, 2, bet_down=False, stop_level=None)

        # Then
        assert result is not None
        assert result.reason == EXIT_LIMIT
        assert result.return_rate == pytest.approx(-0.06, abs=RATE_TOLERANCE)

    def test_무손절은_갭도_보지_않는다(self) -> None:
        """
        목적: 무손절에서 시가 판정도 건너뛰는지 고정한다 (엣지 케이스)

        Given: 다음날 시가가 -30% 로 열렸다가 청산일에 회복한 시세
        When: 손절선을 None 으로 두었을 때
        Then: 청산일 종가로 나간다
        """
        # Given
        frame = _frame([_entry_day(), (70.0, 75.0, 68.0, 74.0), (99.0, 100.0, 98.0, 99.0)])

        # When
        result = simulate_scheduled_trade(frame, 0, 2, bet_down=False, stop_level=None)

        # Then
        assert result is not None
        assert result.reason == EXIT_LIMIT
        assert result.return_rate == pytest.approx(-0.01, abs=RATE_TOLERANCE)


class TestLookAhead:
    """미래 참조 감시 — 청산일 이후를 보지 않는다"""

    def test_청산일_이후_데이터를_잘라도_결과가_같다(self) -> None:
        """
        목적: 판정이 청산일까지의 데이터만 쓴다는 것을 고정한다

        **미래를 참조하면 성과가 실제보다 좋게 나오고 눈으로는 발견되지 않는다.**

        Given: 청산일 뒤에 큰 등락이 이어지는 시세와, 그 뒤를 잘라낸 시세
        When: 둘 다 같은 진입·청산 위치로 체결했을 때
        Then: 수익률·사유·보유일이 모두 같다
        """
        # Given
        tail = [_entry_day(), _flat_day(), (99.0, 99.5, 97.5, 98.0)]
        full = _frame([*tail, (120.0, 130.0, 119.0, 129.0), (60.0, 61.0, 55.0, 56.0)])
        truncated = _frame(tail)

        # When
        from_full = simulate_scheduled_trade(full, 0, 2, bet_down=False, stop_level=STOP_LEVEL)
        from_truncated = simulate_scheduled_trade(truncated, 0, 2, bet_down=False, stop_level=STOP_LEVEL)

        # Then
        assert from_full == from_truncated

    def test_손절이_걸린_경우에도_뒤를_잘라도_같다(self) -> None:
        """
        목적: 손절 경로에서도 미래를 참조하지 않는지 고정한다

        Given: 1일차에 손절되고 그 뒤로 시세가 이어지는 경우
        When: 손절일 다음 행까지만 남기고 잘랐을 때
        Then: 결과가 같다
        """
        # Given
        head = [_entry_day(), (99.5, 100.0, 93.0, 94.0), _flat_day()]
        full = _frame([*head, (150.0, 160.0, 149.0, 159.0)])
        truncated = _frame(head)

        # When
        from_full = simulate_scheduled_trade(full, 0, 2, bet_down=False, stop_level=STOP_LEVEL)
        from_truncated = simulate_scheduled_trade(truncated, 0, 2, bet_down=False, stop_level=STOP_LEVEL)

        # Then
        assert from_full == from_truncated


class TestValidation:
    """입력 검증 계약"""

    def test_청산_위치가_진입보다_뒤가_아니면_거부한다(self) -> None:
        """
        목적: 보유일 0 이하인 체결을 막는지 고정한다

        Given: 청산 위치가 진입 위치와 같은 요청
        When: 체결을 요청했을 때
        Then: ValueError 가 난다
        """
        # Given
        frame = _frame([_entry_day(), _flat_day()])

        # When / Then
        with pytest.raises(ValueError, match="청산 위치"):
            simulate_scheduled_trade(frame, 0, 0, bet_down=False, stop_level=STOP_LEVEL)

    def test_청산_위치가_시세_범위_밖이면_거부한다(self) -> None:
        """
        목적: 데이터를 넘어가는 청산을 조용히 채우지 않는지 고정한다

        청산 목표일이 데이터 끝을 넘는 진입은 **호출 전에 제외**돼야 한다
        (`measure/calendar_exit.py` 가 사유를 붙여 걸러낸다). 여기까지 오면 계약 위반이다.

        Given: 시세 길이를 넘는 청산 위치
        When: 체결을 요청했을 때
        Then: ValueError 가 난다
        """
        # Given
        frame = _frame([_entry_day(), _flat_day()])

        # When / Then
        with pytest.raises(ValueError, match="청산 위치"):
            simulate_scheduled_trade(frame, 0, 5, bet_down=False, stop_level=STOP_LEVEL)

    def test_무손절_경로에서_음수_진입_위치를_거부한다(self) -> None:
        """
        목적: **예외도 경고도 없이 결과만 틀리던 경로**를 막는다.

        `pandas.Index.get_indexer` 는 찾지 못한 날짜에 `-1` 을 돌려준다. 그 값이 여기까지
        오면 `_scheduled_exit` 의 `iloc[-1]` 이 **마지막 행을 진입가로** 잡는다 —
        예외가 나지 않고 체결 하나가 조용히 만들어진다.

        **무손절은 월말의 지수 대상이 언제나 지나는 길**이라(지수는 고가·저가가 없어
        손절을 못 건다) 가드가 없는 쪽이 하필 상시 경로였다.

        Given: 마지막 행만 500 으로 튀는 시세 (진입가로 잡히면 -79.4% 가 나온다)
        When: 진입 위치 -1 로 무손절 체결을 요청했을 때
        Then: 체결되지 않고 ValueError 가 난다
        """
        # Given
        frame = _frame([_entry_day(), _flat_day(), _flat_day(), (500.0, 500.0, 500.0, 500.0)])

        # When / Then
        with pytest.raises(ValueError, match="진입 위치"):
            simulate_scheduled_trade(frame, -1, 3, bet_down=False, stop_level=None)

    def test_손절_경로에서도_음수_진입_위치를_거부한다(self) -> None:
        """
        목적: 두 경로의 가드 강도를 같게 고정한다 (엣지 케이스).

        손절 경로는 `simulate_signal._validate` 의 `0 <= entry_position` 에 걸려 원래
        살아났다. **그 동작이 유지되는지** 함께 고정한다 — 근본 수정이 한쪽만 고치면
        두 경로가 다시 갈린다.

        Given: 같은 시세
        When: 진입 위치 -1 로 손절 체결을 요청했을 때
        Then: ValueError 가 난다
        """
        # Given
        frame = _frame([_entry_day(), _flat_day(), _flat_day(), (500.0, 500.0, 500.0, 500.0)])

        # When / Then
        with pytest.raises(ValueError, match="진입 위치"):
            simulate_scheduled_trade(frame, -1, 3, bet_down=False, stop_level=STOP_LEVEL)

    def test_손절선이_양수가_아니면_거부한다(self) -> None:
        """
        목적: 잘못된 손절선을 즉시 막는지 고정한다

        무손절은 `None` 으로 표현한다 — 0 이나 음수가 아니다.

        Given: 손절선 0
        When: 체결을 요청했을 때
        Then: ValueError 가 난다
        """
        # Given
        frame = _frame([_entry_day(), _flat_day()])

        # When / Then
        with pytest.raises(ValueError, match="손절선"):
            simulate_scheduled_trade(frame, 0, 1, bet_down=False, stop_level=0.0)

    def test_진입가가_0_이하이면_거부한다(self) -> None:
        """
        목적: 무손절 경로에서 0 으로 나누는 것을 막는다

        **시세 로더는 「0 이하 가격」을 거부하지만 계열 로더는 값의 부호를 보지 않는다** —
        마이너스 금리와 0% 금리가 실재하기 때문이며 그 판정은 옳다. 그런데 월말 매매가
        지수 계열을 무손절 경로로 넘기고 거기서 진입가가 **분모**가 된다. 그래서 나누는 쪽에서 막는다.

        Given: 진입일의 가격이 0 인 계열
        When: 무손절 체결을 요청했을 때
        Then: ValueError 가 난다
        """
        # Given
        frame = pd.DataFrame({COL_DATE: pd.to_datetime(["2020-01-02", "2020-01-03"]), COL_CLOSE: [0.0, 100.0]})

        # When / Then
        with pytest.raises(ValueError, match="진입가"):
            simulate_scheduled_trade(frame, 0, 1, bet_down=False, stop_level=None)

    def test_청산가가_0_이하이면_거부한다(self) -> None:
        """
        목적: **조용히 −100% 짜리 체결이 만들어지던 것**을 막는다

        진입가는 분모라 0 이면 예외로 터지지만 **청산가는 아니다** — 0 이어도 계산이 되어
        `-100%` 가 합계·평균·최악에 그대로 섞인다. 두 값이 같은 계열에서 오므로 함께 막는다.

        Given: 청산일의 가격이 0 인 계열
        When: 무손절 체결을 요청했을 때
        Then: ValueError 가 난다
        """
        # Given
        frame = pd.DataFrame({COL_DATE: pd.to_datetime(["2020-01-02", "2020-01-03"]), COL_CLOSE: [100.0, 0.0]})

        # When / Then
        with pytest.raises(ValueError, match="청산가"):
            simulate_scheduled_trade(frame, 0, 1, bet_down=False, stop_level=None)


class TestResolvePositions:
    """날짜 → 거래일 위치 변환의 계약 — 매매 계층 네 곳이 공유한다.

    **`-1` 을 흘려보내지 않는 것이 이 함수의 존재 이유다.** 매매 계층은 진입일·청산일을
    `trading_days` 자신에서 만들므로 `-1` 은 일정 모듈의 버그로만 생긴다. 그래서
    입력 검증(`ValueError`)이 아니라 **내부 불변조건 위반(`RuntimeError`)** 이다.

    같은 사고를 **날짜 목록을 파라미터로 받는** `studies/` 세 곳은 `ValueError` 로 던진다 —
    거기서는 잘못된 값이 외부에서 올 수 있기 때문이며, 메시지 본문만 같게 맞춘다.
    """

    def test_전부_거래일이면_위치를_그대로_돌려준다(self) -> None:
        """
        목적: 정상 경로가 `get_indexer` 와 같은 값을 낸다는 것을 고정한다.

        Given: 거래일 목록에 모두 들어 있는 날짜 셋
        When: 위치를 구하면
        Then: 오름차순 위치가 그대로 나온다
        """
        # Given
        trading_days = pd.DatetimeIndex(pd.bdate_range("2020-01-01", periods=5))
        dates = trading_days[[0, 2, 4]]

        # When
        positions = resolve_positions(trading_days, dates, label="진입일")

        # Then
        assert positions.tolist() == [0, 2, 4]

    def test_거래일에_없는_날짜가_있으면_내부_불변조건_위반이다(self) -> None:
        """
        목적: **이 계획서가 막으려는 사고 그 자체**를 고정한다.

        `get_indexer` 가 `-1` 을 돌려주는데 그것을 검사하지 않으면 음수 위치가
        `simulate_scheduled_trade` 로 흘러간다.

        Given: 거래일 목록에 없는 날짜(휴장일)가 섞인 목록
        When: 위치를 구하면
        Then: RuntimeError 이고 메시지에 **그 날짜**가 담긴다
        """
        # Given
        trading_days = pd.DatetimeIndex(pd.bdate_range("2020-01-01", periods=5))
        dates = pd.DatetimeIndex([trading_days[0], pd.Timestamp("2020-01-04")])

        # When / Then
        with pytest.raises(RuntimeError, match="내부 불변조건 위반") as caught:
            resolve_positions(trading_days, dates, label="진입일")

        assert "2020-01-04" in str(caught.value)

    def test_라벨이_메시지에_실린다(self) -> None:
        """
        목적: 진입일이 없는 것과 청산일이 없는 것을 메시지로 가른다.

        원인이 다르다 — 진입일은 일정 모듈의 앞당김, 청산일은 상대 거래일 계산에서 온다.
        같은 문구로 나가면 어느 쪽을 봐야 하는지 알 수 없다.

        Given: 거래일 목록에 없는 날짜
        When: 라벨을 「청산일」로 주고 위치를 구하면
        Then: 메시지에 「청산일」이 들어간다
        """
        # Given
        trading_days = pd.DatetimeIndex(pd.bdate_range("2020-01-01", periods=5))
        dates = pd.DatetimeIndex([pd.Timestamp("2020-01-04")])

        # When / Then
        with pytest.raises(RuntimeError, match="청산일"):
            resolve_positions(trading_days, dates, label="청산일")

    def test_빈_날짜_목록은_빈_배열이다(self) -> None:
        """
        목적: 신호가 하나도 없는 달에서 터지지 않는지 고정한다 (엣지 케이스).

        `numpy` 의 `min()` 은 빈 배열에서 `ValueError` 를 낸다 — 그 자리를 막지 않으면
        정상적인 「그 달에 진입이 없음」이 예외가 된다.

        Given: 빈 날짜 목록
        When: 위치를 구하면
        Then: 빈 배열이 나오고 예외가 없다
        """
        # Given
        trading_days = pd.DatetimeIndex(pd.bdate_range("2020-01-01", periods=5))
        dates = pd.DatetimeIndex([])

        # When
        positions = resolve_positions(trading_days, dates, label="진입일")

        # Then
        assert positions.tolist() == []


class TestWorstHoldRateScheduled:
    """보유 중 최악 계약 — 달력 청산 경로

    **이 경로에만 있는 갈림이 하나다: 종가 계열(지수)은 장중을 잴 수 없다.**
    고가·저가가 아예 없으므로 종가로 재며, 그 값은 실제로 감당한 낙폭보다 **얕다.**
    어느 기준으로 잰 행인지는 `손절선(%)` 의 `손절불가` 표기가 이미 말해 준다.
    """

    def test_무손절_ETF_도_장중으로_잰다(self) -> None:
        """
        목적: 무손절 행이 **결과만 보고 끝나지 않는다**는 계약을 고정한다

        무손절 경로는 청산일 종가만 읽어 체결을 만든다. 보유 중 최악까지 그 방식으로 재면
        **손절이 무엇을 막았는지**를 견줄 대조축이 사라진다 — 무손절 행의 존재 이유가 그것이다.

        Given: 중간에 -20% 까지 밀렸다가 청산일에 -6% 로 끝난 시세
        When: 손절선 없이 위에 걸었을 때
        Then: 결과는 -6% 이고 보유 중 최악은 **-20%** 다
        """
        # Given
        frame = _frame([_entry_day(), (95.0, 96.0, 80.0, 82.0), (90.0, 95.0, 89.0, 94.0)])

        # When
        result = simulate_scheduled_trade(frame, 0, 2, bet_down=False, stop_level=None)

        # Then
        assert result.return_rate == pytest.approx(-0.06, abs=RATE_TOLERANCE)
        assert result.worst_hold_rate == pytest.approx(-0.20, abs=RATE_TOLERANCE)
        assert result.worst_hold_rate <= result.return_rate

    def test_종가_계열은_종가로_잰다(self) -> None:
        """
        목적: **지수 경로**를 고정한다 — 고가·저가가 없어도 값을 낸다

        지수는 `storage/series/` 에 종가 하나로 저장돼 장중 최저점을 알 방법이 없다.
        여기서 예외를 내면 30년짜리 긴 축에서 이 컬럼을 통째로 잃는다.

        **기준을 가르는 것은 `price_column` 하나다** — 종가가 아니면 장중을 잴 수 없다는 뜻이라
        별도 인자를 두지 않는다. 두면 같은 사실을 두 곳에서 말하게 되고 어긋나면 한쪽이 조용히 틀린다.

        Given: 종가만 있는 계열이 중간에 -10% 까지 내렸다가 -2% 로 끝난 경우
        When: 그 계열의 가격 컬럼으로 무손절 체결을 요청했을 때
        Then: 종가 기준으로 **-10%** 가 나온다
        """
        # Given
        frame = pd.DataFrame(
            {
                COL_DATE: pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]),
                COL_VALUE: [100.0, 90.0, 98.0],
            }
        )

        # When
        result = simulate_scheduled_trade(frame, 0, 2, bet_down=False, stop_level=None, price_column=COL_VALUE)

        # Then
        assert result.return_rate == pytest.approx(-0.02, abs=RATE_TOLERANCE)
        assert result.worst_hold_rate == pytest.approx(-0.10, abs=RATE_TOLERANCE)

    def test_보유_구간의_0_이하_가격을_거부한다(self) -> None:
        """
        목적: **진입가·청산가 검사가 「구간 안」을 막지 못하는 것**을 닫는다 (엣지 케이스)

        계열 로더는 값의 부호를 보지 않는다 — 마이너스 금리와 0% 금리가 실재하기 때문이며
        그 판정은 옳다. 그런데 양 끝만 검사하면 **가운데 0 하나가 조용히 −100% 짜리
        보유 중 최악을 만들고**, 그 값이 칸의 최솟값이 되어 성적표에 그대로 실린다.

        Given: 진입가·청산가는 멀쩡한데 «가운데» 값이 0 인 계열
        When: 무손절 체결을 요청했을 때
        Then: ValueError 가 난다
        """
        # Given
        frame = pd.DataFrame(
            {
                COL_DATE: pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]),
                COL_VALUE: [100.0, 0.0, 98.0],
            }
        )

        # When / Then
        with pytest.raises(ValueError, match="0 이하"):
            simulate_scheduled_trade(frame, 0, 2, bet_down=False, stop_level=None, price_column=COL_VALUE)

    def test_아래로_거는_칸은_고가로_잡힌다(self) -> None:
        """
        목적: 달력 경로에서도 방향에 따라 손실 쪽이 갈리는 것을 고정한다

        Given: 장중 +9% 까지 올랐다가 청산일에 진입가로 돌아온 시세
        When: 무손절로 아래에 걸었을 때
        Then: 결과는 0% 이고 보유 중 최악은 -9% 다
        """
        # Given
        frame = _frame([_entry_day(), (100.0, 109.0, 99.0, 105.0), (105.0, 106.0, 99.0, 100.0)])

        # When
        result = simulate_scheduled_trade(frame, 0, 2, bet_down=True, stop_level=None)

        # Then
        assert result.return_rate == pytest.approx(0.0, abs=RATE_TOLERANCE)
        assert result.worst_hold_rate == pytest.approx(-0.09, abs=RATE_TOLERANCE)
        assert result.worst_hold_rate <= result.return_rate
