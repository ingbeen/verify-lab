"""만기_말일 — 네 조합의 진입·청산 조립 계약

이 검증의 고유 로직은 **조립**뿐이다. 달력 계산은 `measure/calendar_*` 가 소유하고
그쪽 테스트가 이미 본다. 여기서는 **조합이 실제로 네 벌의 다른 일정을 만드는지**와
**붕괴 세기가 맞는지**, 그리고 **미래를 참조하지 않는지**를 본다.
"""

from collections.abc import Sequence

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.measure.constants import (
    COL_EXCLUDED_REASON,
    COL_EXIT_DATE,
    COL_MONTH,
    REASON_NO_EXPIRY_DAY,
    REASON_NONE,
)
from verify_lab.studies.expiry_monthend.constants import (
    COMBOS,
    ENTRY_DAY,
    ENTRY_EXPIRY,
    EXIT_MONTH_END,
    EXIT_NEXT_WEEK,
    FRIDAY,
    combos_of,
)
from verify_lab.studies.expiry_monthend.pairing import (
    baseline_entries,
    combo_entries,
    combo_returns,
    shared_year_counts,
)

# 합성 시세의 기준 가격. 값 자체는 판정에 쓰이지 않는다
BASE_PRICE = 100.0


def _trading_days(start: str, end: str, holidays: Sequence[str] = ()) -> pd.DatetimeIndex:
    """주중에서 지정한 휴장일을 뺀 합성 거래일 목록을 만든다.

    Args:
        start: 시작일 (`YYYY-MM-DD`)
        end: 종료일 (`YYYY-MM-DD`)
        holidays: 휴장일 목록

    Returns:
        거래일 인덱스
    """
    days = pd.bdate_range(start, end)
    excluded = pd.DatetimeIndex([pd.Timestamp(day) for day in holidays])

    return pd.DatetimeIndex(days.difference(excluded))


def _market(days: pd.DatetimeIndex) -> pd.DataFrame:
    """합성 시세를 만든다.

    Args:
        days: 거래일 목록

    Returns:
        시세 스키마 DataFrame
    """
    closes = [BASE_PRICE + index for index in range(len(days))]

    return pd.DataFrame(
        {
            COL_DATE: days,
            COL_OPEN: closes,
            COL_HIGH: [price + 1.0 for price in closes],
            COL_LOW: [price - 1.0 for price in closes],
            COL_CLOSE: closes,
            COL_VOLUME: [1_000] * len(days),
        }
    )


class TestComboSelection:
    """조합 고르기는 「전부」와 「고른 결과가 없다」를 가른다"""

    def test_인자를_주지_않으면_넷_전부다(self) -> None:
        """
        목적: 기본값이 격자 전체임을 고정한다.

        Given: 인자 없음
        When: 조합을 고른다
        Then: 선언된 넷이 그 순서로 나온다
        """
        # When / Then
        assert combos_of() == COMBOS

    def test_빈_목록은_거부한다(self) -> None:
        """
        목적: 조용히 전부로 넓히는 것을 막는다 — 좁히려던 실행이 전 범위 산출물로 폴더를 덮는다.

        Given: 빈 튜플
        When: 조합을 고른다
        Then: `ValueError`
        """
        # When / Then
        with pytest.raises(ValueError, match="고른 조합이 없습니다"):
            combos_of(())

    def test_모르는_이름은_거부한다(self) -> None:
        """
        목적: 오타가 조용히 빈 결과가 되는 것을 막는다.

        Given: 없는 이름
        When: 조합을 고른다
        Then: `ValueError`
        """
        # When / Then
        with pytest.raises(ValueError, match="모르는 조합입니다"):
            combos_of(("c9",))

    def test_네_조합이_진입과_청산의_곱이다(self) -> None:
        """
        목적: 2×2 가 빠짐없이 펼쳐졌음을 고정한다.

        Given: 선언된 조합
        When: (진입, 청산) 쌍을 모은다
        Then: 네 가지 곱이 전부 한 번씩 있다
        """
        # When
        pairs = {(combo.entry, combo.exit_rule) for combo in COMBOS}

        # Then
        assert pairs == {
            (ENTRY_EXPIRY, EXIT_NEXT_WEEK),
            (ENTRY_EXPIRY, EXIT_MONTH_END),
            (ENTRY_DAY, EXIT_NEXT_WEEK),
            (ENTRY_DAY, EXIT_MONTH_END),
        }


class TestComboEntries:
    """진입 규칙이 진입일과 주 기준일을 갈라 낸다"""

    def test_셋째_금요일_진입의_주_기준일은_규칙일이다(self) -> None:
        """
        목적: 앞당김이 목표 주를 끌고 가지 않게 고정한다 — 연휴가 낀 달의 보유가 무너진다.

        Given: 2024-09-20(셋째 금요일)이 휴장인 거래일 목록
        When: 셋째 금요일 진입을 만든다
        Then: 진입일은 앞당겨지고 주 기준일은 09-20 그대로다
        """
        # Given
        days = _trading_days("2024-09-01", "2024-10-31", holidays=["2024-09-20"])

        # When
        entries = combo_entries(days, COMBOS[0])
        picked = pd.DatetimeIndex(entries.frame[COL_DATE]).month == 9

        # Then
        assert pd.DatetimeIndex(entries.frame[COL_DATE])[picked][0] == pd.Timestamp("2024-09-19")
        assert entries.week_references[picked][0] == pd.Timestamp("2024-09-20")

    def test_20일_진입의_주_기준일은_달력일이다(self) -> None:
        """
        목적: 두 진입이 같은 기준(규칙일)을 쓰게 고정한다 — 한쪽만 진입일로 세면 조합이 어긋난다.

        Given: 2024-09-20 이 휴장인 거래일 목록
        When: 20일 진입을 만든다
        Then: 진입일은 앞당겨지고 주 기준일은 09-20 그대로다
        """
        # Given
        days = _trading_days("2024-09-01", "2024-10-31", holidays=["2024-09-20"])

        # When
        entries = combo_entries(days, COMBOS[2])
        picked = pd.DatetimeIndex(entries.frame[COL_DATE]).month == 9

        # Then
        assert pd.DatetimeIndex(entries.frame[COL_DATE])[picked][0] == pd.Timestamp("2024-09-19")
        assert entries.week_references[picked][0] == pd.Timestamp("2024-09-20")

    def test_기준선은_주_기준일이_진입일_자신이다(self) -> None:
        """
        목적: 기준선에는 앞당김이 없으므로 규칙일과 진입일이 같음을 고정한다.

        Given: 두 달치 거래일
        When: 기준선 진입을 만든다
        Then: 두 축이 같다
        """
        # Given
        days = _trading_days("2024-09-01", "2024-10-31")

        # When
        entries = baseline_entries(days, COMBOS[2])

        # Then
        assert list(entries.frame[COL_DATE]) == list(entries.week_references)

    def test_만기_진입의_기준선은_그_요일만_모은다(self) -> None:
        """
        목적: 기준선 모집단이 진입 규칙을 따름을 고정한다 — 전 거래일로 통일하면 주 기준
            청산에서 보유 길이가 신호와 어긋나 그 차이가 우연확률에 실린다.

        Given: 두 달치 거래일
        When: 만기 진입 조합과 달력일 진입 조합의 기준선을 각각 만든다
        Then: 만기 쪽은 전부 금요일이고 달력일 쪽은 전 거래일이다
        """
        # Given
        days = _trading_days("2024-09-01", "2024-10-31")

        # When
        expiry = baseline_entries(days, COMBOS[0])
        calendar_day = baseline_entries(days, COMBOS[2])

        # Then
        assert set(pd.DatetimeIndex(expiry.frame[COL_DATE]).dayofweek) == {FRIDAY}
        assert len(calendar_day.frame) > len(expiry.frame)

    def test_만기_진입도_마지막_달을_뺀다(self) -> None:
        """
        목적: 네 조합이 같은 달 집합을 보게 고정한다.

        **`month_entry_dates` 는 마지막 달을 빼는데 `monthly_expiry_dates` 는 빼지 않는다.**
        맞추지 않으면 말일 청산에서 「데이터가 끊긴 날」이 월말로 잡힌 가짜 표본이 생기고,
        기준선은 그 달을 빼므로 비교 구간까지 어긋난다.

        Given: 10월 중순에서 끊긴 거래일 목록
        When: 네 조합의 진입 달을 본다
        Then: 넷이 같고 10월이 없다
        """
        # Given
        days = _trading_days("2024-08-01", "2024-10-18")

        # When
        months = {combo.key: set(combo_entries(days, combo).frame[COL_MONTH]) for combo in COMBOS}

        # Then
        assert len(set(map(frozenset, months.values()))) == 1
        assert pd.Timestamp("2024-10-01") not in months["c1"]

    def test_만기일을_확정하지_못한_달도_행으로_남는다(self) -> None:
        """
        목적: 표본 보존을 만기 진입에도 건다 — 달력일 진입은 이미 그렇게 한다.

        Given: 9월 셋째 금요일 «뒤»부터 시작하는 거래일 목록
        When: 만기 진입을 만든다
        Then: 9월 행이 남고 사유가 붙어 있다
        """
        # Given
        days = _trading_days("2024-09-23", "2024-11-29")

        # When
        frame = combo_entries(days, COMBOS[0]).frame
        september = frame[pd.DatetimeIndex(frame[COL_MONTH]).month == 9]

        # Then
        assert len(september) == 1
        assert september.iloc[0][COL_EXCLUDED_REASON] == REASON_NO_EXPIRY_DAY


class TestComboReturns:
    """청산 규칙이 조합마다 다른 날을 지목한다"""

    def test_말일_청산은_그_달_마지막_거래일이다(self) -> None:
        """
        목적: 말일 청산이 실제로 월말임을 고정한다.

        Given: 2024-09 ~ 2024-11 거래일과 합성 시세
        When: 셋째 금요일 → 말일 조합을 돌린다
        Then: 9월 청산일이 09-30 이다
        """
        # Given
        days = _trading_days("2024-09-01", "2024-11-29")
        frame = _market(days)

        # When
        entries = combo_entries(days, COMBOS[1])
        returns = combo_returns(frame, days, entries, COMBOS[1], price_column=COL_CLOSE)
        september = returns[(returns[COL_DATE].dt.month == 9) & (returns[COL_EXCLUDED_REASON] == REASON_NONE)]

        # Then
        assert september.iloc[0][COL_EXIT_DATE] == pd.Timestamp("2024-09-30")

    def test_다음주_금요일_청산은_한_주_뒤_금요일이다(self) -> None:
        """
        목적: 「다음 주」가 주 기준일이 속한 주의 한 주 뒤임을 고정한다.

        Given: 2024-09 ~ 2024-11 거래일과 합성 시세
        When: 셋째 금요일 → 다음 주 금요일 조합을 돌린다
        Then: 09-20 진입의 청산일이 09-27 이다
        """
        # Given
        days = _trading_days("2024-09-01", "2024-11-29")
        frame = _market(days)

        # When
        entries = combo_entries(days, COMBOS[0])
        returns = combo_returns(frame, days, entries, COMBOS[0], price_column=COL_CLOSE)
        september = returns[(returns[COL_DATE].dt.month == 9) & (returns[COL_EXCLUDED_REASON] == REASON_NONE)]

        # Then
        assert september.iloc[0][COL_DATE] == pd.Timestamp("2024-09-20")
        assert september.iloc[0][COL_EXIT_DATE] == pd.Timestamp("2024-09-27")

    def test_제외된_진입도_행으로_남는다(self) -> None:
        """
        목적: 표본 보존을 고정한다 — 행이 사라지면 생존편향이 생긴다.

        Given: 마지막 달의 청산일을 확정할 수 없는 짧은 거래일 목록
        When: 말일 청산 조합을 돌린다
        Then: 유효 행보다 전체 행이 많고 제외 사유가 붙어 있다
        """
        # Given
        days = _trading_days("2024-09-01", "2024-09-27")
        frame = _market(days)

        # When
        entries = combo_entries(days, COMBOS[1])
        returns = combo_returns(frame, days, entries, COMBOS[1], price_column=COL_CLOSE)

        # Then
        assert len(returns) >= len(returns[returns[COL_EXCLUDED_REASON] == REASON_NONE])


class TestSharedYearCounts:
    """조합 붕괴를 세는 것이 이 검증의 고유 지표다"""

    def test_같은_일정이면_서로_같은_해로_센다(self) -> None:
        """
        목적: 붕괴 세기가 「진입·청산이 둘 다 같은가」로 판정함을 고정한다.

        Given: 두 조합이 같은 날짜 쌍을 갖는 해 하나
        When: 붕괴를 센다
        Then: 둘 다 「다른 조합과 같은 해」가 1 이다
        """
        # Given
        frame = pd.DataFrame({COL_DATE: [pd.Timestamp("2024-09-20")], COL_EXIT_DATE: [pd.Timestamp("2024-09-30")]})

        # When
        counts = shared_year_counts({"가": frame, "나": frame.copy()}, 9)

        # Then
        assert counts["가"] == (1, 0)
        assert counts["나"] == (1, 0)

    def test_청산일만_달라도_다른_조합으로_센다(self) -> None:
        """
        목적: 진입일만 비교하지 않음을 고정한다 — 그러면 붕괴가 실제보다 많이 세어진다.

        Given: 진입일은 같고 청산일이 다른 두 조합
        When: 붕괴를 센다
        Then: 둘 다 「이 조합만 다른 해」가 1 이다
        """
        # Given
        left = pd.DataFrame({COL_DATE: [pd.Timestamp("2024-09-20")], COL_EXIT_DATE: [pd.Timestamp("2024-09-27")]})
        right = pd.DataFrame({COL_DATE: [pd.Timestamp("2024-09-20")], COL_EXIT_DATE: [pd.Timestamp("2024-09-30")]})

        # When
        counts = shared_year_counts({"가": left, "나": right}, 9)

        # Then
        assert counts["가"] == (0, 1)
        assert counts["나"] == (0, 1)

    def test_다른_달은_세지_않는다(self) -> None:
        """
        목적: 붕괴를 달마다 따로 세는 것을 고정한다 — 9월에는 갈리고 12월에는 겹칠 수 있다.

        Given: 12월 체결만 있는 두 조합
        When: 9월로 센다
        Then: 둘 다 0 이다
        """
        # Given
        frame = pd.DataFrame({COL_DATE: [pd.Timestamp("2024-12-20")], COL_EXIT_DATE: [pd.Timestamp("2024-12-31")]})

        # When
        counts = shared_year_counts({"가": frame, "나": frame.copy()}, 9)

        # Then
        assert counts["가"] == (0, 0)
        assert counts["나"] == (0, 0)


class TestLookAhead:
    """뒤를 잘라도 겹치는 구간의 결과가 같아야 한다 (측정 계층의 절대 원칙 1)"""

    @pytest.mark.parametrize("combo", COMBOS, ids=[combo.key for combo in COMBOS])
    def test_뒤를_잘라도_앞의_판정이_같다(self, combo: object) -> None:
        """
        목적: 구현이 판정일 이후의 데이터에 의존하지 않음을 고정한다.

        Given: 전체 거래일과 뒤를 자른 거래일
        When: 같은 조합으로 일정을 만든다
        Then: 짧은 쪽에서 값이 있는 칸은 긴 쪽과 같다

        Args:
            combo: 검사할 조합
        """
        # Given
        full_days = _trading_days("2023-01-02", "2024-12-31")
        short_days = full_days[full_days <= pd.Timestamp("2024-06-28")]
        full_frame = _market(full_days)
        short_frame = _market(short_days)

        # When
        full = combo_returns(
            full_frame, full_days, combo_entries(full_days, combo), combo, price_column=COL_CLOSE  # type: ignore[arg-type]
        )
        short = combo_returns(
            short_frame, short_days, combo_entries(short_days, combo), combo, price_column=COL_CLOSE  # type: ignore[arg-type]
        )

        # Then
        usable = short[short[COL_EXCLUDED_REASON] == REASON_NONE]
        merged = usable.merge(full, on=COL_DATE, suffixes=("_short", "_full"))

        assert len(merged) == len(usable)
        assert list(merged[f"{COL_EXIT_DATE}_short"]) == list(merged[f"{COL_EXIT_DATE}_full"])
