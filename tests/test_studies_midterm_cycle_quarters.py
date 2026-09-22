"""중간선거_사이클 — 보유 구간의 분기 분해와 보유 중 최악의 분포

**이 표는 「어느 분기가 수익을 만들고 어느 분기에 밀리나」에 답한다.** 진입이 9월 마지막
거래일이고 청산이 다음해 6월 마지막 거래일이라 보유가 **4분기·1분기·2분기에 정확히 맞는다.**

[중요] **검산 둘이 이 모듈의 계약이다.**

| 검산 | 왜 |
| --- | --- |
| `(1+4분기)(1+1분기)(1+2분기) = 1 + 전체 수익률` | 분기 경계가 어긋나거나 구간이 겹치면 깨진다 |
| `min(분기별 진입가 대비 최악) = 전체 보유 중 최악` | 세 구간의 합집합이 보유 구간 전체임을 말한다 |

**둘 다 «조용히» 깨지는 종류다** — 경계가 하루 어긋나도 값은 그럴듯하게 나온다.

**산식을 새로 만들지 않는다.** 분기 하나를 `execution/trade_fill.simulate_scheduled_trade` 에
무손절로 넘기면 분기 수익률과 분기 시작가 대비 최악이 그대로 나오고, 진입가 대비 최악은
거기서 **분모만 바꾼 항등식**이다 (설계 결정 ⑯).
"""

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VALUE
from verify_lab.execution.trade_fill import simulate_scheduled_trade
from verify_lab.studies.midterm_cycle.constants import DRAWDOWN_BUCKETS, QUARTER_LABELS
from verify_lab.studies.midterm_cycle.quarters import drawdown_profile, quarter_trades


def _frame(
    start: str, end: str, *, closes: dict[str, float] | None = None, lows: dict[str, float] | None = None
) -> pd.DataFrame:
    """주중 거래일마다 OHLC 가 있는 합성 시세를 만든다.

    종가는 기본 100 이고 저가는 종가와 같다. 특정 날짜만 `closes`·`lows` 로 덮는다.

    Args:
        start: 시작일
        end: 종료일
        closes: 날짜 → 종가
        lows: 날짜 → 저가

    Returns:
        `Date`·`Open`·`High`·`Low`·`Close` 가 있는 DataFrame
    """
    days = pd.DatetimeIndex(pd.bdate_range(start, end))
    close_values = [float((closes or {}).get(day.strftime("%Y-%m-%d"), 100.0)) for day in days]
    low_values = [
        float((lows or {}).get(day.strftime("%Y-%m-%d"), close_values[index])) for index, day in enumerate(days)
    ]

    return pd.DataFrame(
        {
            COL_DATE: days,
            COL_OPEN: close_values,
            COL_HIGH: close_values,
            COL_LOW: low_values,
            COL_CLOSE: close_values,
        }
    )


def _position_of(frame: pd.DataFrame, date: str) -> int:
    """날짜의 거래일 위치를 찾는다.

    Args:
        frame: 시세
        date: 찾을 날짜

    Returns:
        위치 인덱스
    """
    matches = frame.index[frame[COL_DATE] == pd.Timestamp(date)]
    assert len(matches) == 1, f"{date} 가 거래일이 아닙니다"

    return int(matches[0])


class TestQuarterTrades:
    """보유 구간을 달력 분기로 갈라 분기마다 체결을 잰다."""

    def test_세_분기로_갈리고_순서가_고정이다(self) -> None:
        """
        목적: 보유 구간이 4분기·1분기·2분기에 맞아떨어짐을 고정한다

        Given: 2025-09-30 진입 · 2026-06-30 청산
        When: 분기 분해를 하면
        Then: 라벨이 («4분기», «1분기», «2분기») 다
        """
        # Given
        frame = _frame("2025-01-01", "2026-12-31")
        entry = _position_of(frame, "2025-09-30")
        exit_position = _position_of(frame, "2026-06-30")

        # When
        result = quarter_trades(
            frame, entry_position=entry, exit_position=exit_position, bet_down=False, price_column=COL_CLOSE
        )

        # Then
        assert tuple(trade.label for trade in result) == QUARTER_LABELS

    def test_분기_경계가_그_분기_마지막_거래일이다(self) -> None:
        """
        목적: 경계 규칙을 고정한다 — 달을 세어 자르지 않고 달력 분기로 묶는다

        Given: 2025-09-30 진입 · 2026-06-30 청산
        When: 분기 분해를 하면
        Then: 4분기 끝이 2025-12-31, 1분기 끝이 2026-03-31, 2분기 끝이 청산일이다
        """
        # Given
        frame = _frame("2025-01-01", "2026-12-31")
        entry = _position_of(frame, "2025-09-30")
        exit_position = _position_of(frame, "2026-06-30")

        # When
        result = quarter_trades(
            frame, entry_position=entry, exit_position=exit_position, bet_down=False, price_column=COL_CLOSE
        )

        # Then
        ends = [pd.Timestamp(frame.iloc[trade.end_position][COL_DATE]) for trade in result]
        assert ends == [pd.Timestamp("2025-12-31"), pd.Timestamp("2026-03-31"), pd.Timestamp("2026-06-30")]

    def test_구간이_빈틈없이_이어진다(self) -> None:
        """
        목적: [중요] 합집합이 보유 구간 전체임을 고정한다 — 어긋나면 낙폭 검산이 깨진다

        Given: 2025-09-30 진입 · 2026-06-30 청산
        When: 분기 분해를 하면
        Then: 첫 구간의 시작이 진입일이고, 앞 구간의 끝이 다음 구간의 시작이며,
              마지막 구간의 끝이 청산일이다
        """
        # Given
        frame = _frame("2025-01-01", "2026-12-31")
        entry = _position_of(frame, "2025-09-30")
        exit_position = _position_of(frame, "2026-06-30")

        # When
        result = quarter_trades(
            frame, entry_position=entry, exit_position=exit_position, bet_down=False, price_column=COL_CLOSE
        )

        # Then
        assert result[0].start_position == entry
        assert result[-1].end_position == exit_position
        assert all(result[index].end_position == result[index + 1].start_position for index in range(len(result) - 1))

    def test_세_분기_수익률의_곱이_전체_수익률이다(self) -> None:
        """
        목적: **검산 1** — 분기 경계가 어긋나면 조용히 깨지는 불변조건을 고정한다

        Given: 분기마다 종가가 다르게 움직이는 시세
        When: 분기 분해와 전체 체결을 각각 재면
        Then: 세 분기 수익률의 곱이 전체 수익률과 같다
        """
        # Given
        frame = _frame(
            "2025-01-01",
            "2026-12-31",
            closes={"2025-09-30": 100.0, "2025-12-31": 110.0, "2026-03-31": 99.0, "2026-06-30": 130.0},
        )
        entry = _position_of(frame, "2025-09-30")
        exit_position = _position_of(frame, "2026-06-30")

        # When
        quarters = quarter_trades(
            frame, entry_position=entry, exit_position=exit_position, bet_down=False, price_column=COL_CLOSE
        )
        whole = simulate_scheduled_trade(
            frame, entry, exit_position, bet_down=False, stop_level=None, price_column=COL_CLOSE
        )

        # Then
        product = 1.0
        for trade in quarters:
            product *= 1.0 + trade.return_rate
        assert product == pytest.approx(1.0 + whole.return_rate, abs=1e-12)

    def test_분기별_진입가_대비_최악의_최솟값이_전체_보유_중_최악이다(self) -> None:
        """
        목적: **검산 2** — 세 구간의 합집합이 보유 구간 전체임을 값으로 고정한다

        Given: 분기마다 저가가 다르게 찍히는 시세
        When: 분기 분해와 전체 체결을 각각 재면
        Then: 분기별 진입가 대비 최악의 최솟값이 전체 보유 중 최악과 같다
        """
        # Given
        frame = _frame(
            "2025-01-01",
            "2026-12-31",
            closes={"2025-09-30": 100.0, "2025-12-31": 110.0, "2026-03-31": 99.0, "2026-06-30": 130.0},
            lows={"2025-11-14": 92.0, "2026-02-13": 85.0, "2026-05-15": 95.0},
        )
        entry = _position_of(frame, "2025-09-30")
        exit_position = _position_of(frame, "2026-06-30")

        # When
        quarters = quarter_trades(
            frame, entry_position=entry, exit_position=exit_position, bet_down=False, price_column=COL_CLOSE
        )
        whole = simulate_scheduled_trade(
            frame, entry, exit_position, bet_down=False, stop_level=None, price_column=COL_CLOSE
        )

        # Then
        assert min(trade.worst_vs_entry for trade in quarters) == pytest.approx(whole.worst_hold_rate, abs=1e-12)

    def test_진입가_대비_최악을_손으로_계산한_값과_맞춘다(self) -> None:
        """
        목적: 산식 고정 — 두 분모의 관계를 값으로 박아 둔다

        Given: 진입가 100 · 1분기 시작가(12월말 종가) 110 · 1분기 저가 85
        When: 분기 분해를 하면
        Then: 1분기의 분기 시작가 대비 최악은 85/110-1, 진입가 대비 최악은 85/100-1 이다
        """
        # Given
        frame = _frame(
            "2025-01-01",
            "2026-12-31",
            closes={"2025-09-30": 100.0, "2025-12-31": 110.0, "2026-03-31": 99.0, "2026-06-30": 130.0},
            lows={"2026-02-13": 85.0},
        )
        entry = _position_of(frame, "2025-09-30")
        exit_position = _position_of(frame, "2026-06-30")

        # When
        result = quarter_trades(
            frame, entry_position=entry, exit_position=exit_position, bet_down=False, price_column=COL_CLOSE
        )

        # Then
        first_quarter = next(trade for trade in result if trade.label == "1분기")
        assert first_quarter.worst_vs_start == pytest.approx(85.0 / 110.0 - 1.0, abs=1e-12)
        assert first_quarter.worst_vs_entry == pytest.approx(85.0 / 100.0 - 1.0, abs=1e-12)

    def test_종가_계열도_돈다(self) -> None:
        """
        목적: 지수(고가·저가가 없는 계열)에서도 분해가 성립함을 고정한다

        Given: `Value` 컬럼 하나짜리 계열
        When: 분기 분해를 하면
        Then: 세 분기가 나오고 낙폭이 종가로 재진다
        """
        # Given
        frame = _frame("2025-01-01", "2026-12-31", closes={"2026-02-13": 85.0}).rename(columns={COL_CLOSE: COL_VALUE})[
            [COL_DATE, COL_VALUE]
        ]
        entry = _position_of(frame, "2025-09-30")
        exit_position = _position_of(frame, "2026-06-30")

        # When
        result = quarter_trades(
            frame, entry_position=entry, exit_position=exit_position, bet_down=False, price_column=COL_VALUE
        )

        # Then
        assert tuple(trade.label for trade in result) == QUARTER_LABELS
        first_quarter = next(trade for trade in result if trade.label == "1분기")
        assert first_quarter.worst_vs_entry == pytest.approx(85.0 / 100.0 - 1.0, abs=1e-12)

    def test_분기가_셋이_아니면_예외다(self) -> None:
        """
        목적: [중요] 내부 불변조건 — 규칙이 바뀌어 보유가 세 분기를 벗어나면 즉시 실패한다

        Given: 같은 분기 안에서 끝나는 짧은 보유
        When: 분기 분해를 하면
        Then: RuntimeError 가 난다 — 조용히 한 칸짜리 표를 내지 않는다
        """
        # Given
        frame = _frame("2025-01-01", "2026-12-31")
        entry = _position_of(frame, "2025-10-01")
        exit_position = _position_of(frame, "2025-11-03")

        # When / Then
        with pytest.raises(RuntimeError, match="내부 불변조건 위반"):
            quarter_trades(
                frame, entry_position=entry, exit_position=exit_position, bet_down=False, price_column=COL_CLOSE
            )


class TestDrawdownProfile:
    """보유 중 최악의 «분포» — 최솟값 하나로는 「보통 얼마나 밀리나」에 답하지 못한다."""

    def test_평균과_중앙값을_함께_낸다(self) -> None:
        """
        목적: 측정의 원칙 4 — 두 값이 벌어지는지 볼 수 있게 병기함을 고정한다

        Given: 낙폭 다섯 건
        When: 분포를 내면
        Then: 평균과 중앙값이 손으로 계산한 값과 같다
        """
        # Given
        rates = [-0.01, -0.02, -0.05, -0.10, -0.32]

        # When
        result = drawdown_profile(rates)

        # Then
        assert result.sample_count == len(rates)
        assert result.mean == pytest.approx(-0.10, abs=1e-12)
        assert result.median == pytest.approx(-0.05, abs=1e-12)

    def test_가장_얕게와_가장_깊게를_낸다(self) -> None:
        """
        목적: 기존 성적표의 `보유 중 최악(%)`(최솟값)과 이어짐을 고정한다

        Given: 낙폭 다섯 건
        When: 분포를 내면
        Then: 가장 얕게가 최댓값, 가장 깊게가 최솟값이다
        """
        # Given
        rates = [-0.01, -0.02, -0.05, -0.10, -0.32]

        # When
        result = drawdown_profile(rates)

        # Then
        assert result.shallowest == pytest.approx(-0.01, abs=1e-12)
        assert result.deepest == pytest.approx(-0.32, abs=1e-12)

    def test_구간별_건수를_센다(self) -> None:
        """
        목적: 「보통 5~10% 밀린다」를 읽을 수 있게 하는 축을 고정한다

        Given: -1% · -2% · -5% · -10% · -32% 다섯 건
        When: 분포를 내면
        Then: -5% 이내 2건 · -10% 이내 3건 · -15% 이내 4건 · -20% 이내 4건이다
        """
        # Given
        rates = [-0.01, -0.02, -0.05, -0.10, -0.32]

        # When
        result = drawdown_profile(rates)

        # Then — 경계값(-0.05·-0.10)은 «이내»에 넣지 않는다. 그 값만큼 밀린 것이 사실이다
        assert len(result.within) == len(DRAWDOWN_BUCKETS)
        assert result.within == (2, 3, 4, 4)

    def test_체결이_없으면_예외다(self) -> None:
        """
        목적: 입력 검증 — 0 으로 채워 「안 밀렸다」를 만들지 않음을 고정한다

        Given: 빈 목록
        When: 분포를 내면
        Then: ValueError 가 난다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="비어 있"):
            drawdown_profile([])
