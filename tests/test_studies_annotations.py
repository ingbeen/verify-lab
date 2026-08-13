"""신호일 목록에 붙는 부가 컬럼(사건 번호·참고용 z-score)을 고정한다.

둘 다 **판정이 아니라 해석 보조**다. 이벤트 판정은 순위와 연속 길이로만 한다 (스펙 §11).

고정하는 계약은 셋이다.
- 사건 번호는 **달력 30일 이내로 붙어 있는 신호**를 하나로 묶는다. 간격은 **바로 앞 신호**와
  재므로, 30일 이내로 이어지면 사건이 계속 길어진다
- z-score 는 **당일 등락률 ÷ 직전 N거래일 등락률 표준편차**다. 평균을 빼지 않고 판정일을 뺀다
- 뒤에 데이터가 더 붙어도 이미 지난 날의 값이 달라지지 않는다 (look-ahead 감시)
"""

from collections.abc import Callable, Sequence

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.studies.index_extreme.annotations import assign_event_ids, reference_zscore
from verify_lab.studies.index_extreme.constants import EVENT_GAP_DAYS, ZSCORE_WINDOW

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12


def _market(closes: Sequence[float]) -> pd.DataFrame:
    """합성 시세를 만든다. z-score 는 종가만 보므로 나머지 가격 컬럼은 종가와 같게 둔다."""
    prices = list(closes)

    return pd.DataFrame(
        {
            COL_DATE: pd.bdate_range("2026-01-05", periods=len(prices)),
            COL_OPEN: prices,
            COL_HIGH: prices,
            COL_LOW: prices,
            COL_CLOSE: prices,
            COL_VOLUME: [1_000] * len(prices),
        }
    )


def _dates(values: Sequence[str]) -> pd.Series:
    """신호일 목록을 만든다."""
    return pd.Series(pd.to_datetime(list(values)))


class TestEventGrouping:
    """사건 묶기를 고정한다 — 표본이 서로 독립인지를 드러내는 값이다."""

    def test_groups_signals_within_thirty_calendar_days(self) -> None:
        """
        목적: **달력 30일 이내는 같은 사건, 31일부터 새 사건**이다.

        Given: 1/5 → 2/4(30일 뒤) → 3/7(31일 뒤) → 3/8(1일 뒤)
        When: 사건 번호를 매긴다
        Then: 1 · 1 · 2 · 2 다
        """
        # Given
        dates = _dates(["2026-01-05", "2026-02-04", "2026-03-07", "2026-03-08"])

        # When
        result = assign_event_ids(dates)

        # Then
        assert result.tolist() == [1, 1, 2, 2]

    def test_measures_the_gap_from_the_previous_signal(self) -> None:
        """
        목적: 간격은 **바로 앞 신호**와 잰다 — 사건 시작일이 아니다.

        30일 이내로 계속 이어지면 사건 하나가 그만큼 길어진다. 스펙 §8 의 2008년 사건이
        9/29 → 10/13 → 10/15 → 10/28 로 한 달 넘게 이어지면서도 한 사건인 근거다.

        Given: 30일 간격으로 두 번 이어지는 신호 세 건 (총 60일에 걸침)
        When: 사건 번호를 매긴다
        Then: 셋 다 같은 사건이다
        """
        # Given
        dates = _dates(["2026-01-05", "2026-02-04", "2026-03-06"])

        # When
        result = assign_event_ids(dates)

        # Then
        assert result.tolist() == [1, 1, 1]

    def test_groups_both_directions_together(self) -> None:
        """
        목적: 폭등과 폭락을 **합쳐서** 번호를 매긴다.

        같은 충격에서 나온 폭락과 폭등이 별개 사건으로 세어지면, 사건 단위 집계가 드러내려던
        비독립성이 오히려 숨는다. 입력이 두 방향을 합친 목록이라는 것이 이 계약이다.

        Given: 폭락·폭등이 며칠 간격으로 섞인 신호 네 건
        When: 사건 번호를 매긴다
        Then: 네 건이 모두 한 사건이고, 서로 다른 사건 수가 1이다
        """
        # Given
        dates = _dates(["2008-09-29", "2008-10-13", "2008-10-15", "2008-10-28"])

        # When
        result = assign_event_ids(dates)

        # Then
        assert result.tolist() == [1, 1, 1, 1]
        assert result.nunique() == 1

    def test_numbers_start_at_one_and_increase(self) -> None:
        """
        목적: 사건 번호는 1부터 시작해 시간순으로 증가한다.

        Given: 서로 멀리 떨어진 신호 세 건
        When: 사건 번호를 매긴다
        Then: 1 · 2 · 3 이다
        """
        # Given
        dates = _dates(["2026-01-05", "2026-06-01", "2026-11-02"])

        # When
        result = assign_event_ids(dates)

        # Then
        assert result.tolist() == [1, 2, 3]

    def test_keeps_the_input_index(self) -> None:
        """
        목적: 반환 Series 는 입력과 같은 축을 쓴다 — 신호일 목록에 그대로 붙기 때문이다.

        Given: 인덱스가 0부터가 아닌 신호일 목록
        When: 사건 번호를 매긴다
        Then: 인덱스가 입력과 같다
        """
        # Given
        dates = _dates(["2026-01-05", "2026-06-01"])
        dates.index = pd.Index([7, 9])

        # When
        result = assign_event_ids(dates)

        # Then
        assert result.index.equals(dates.index)

    def test_empty_input_gives_empty_result(self) -> None:
        """
        목적: 신호 0건은 오류가 아니라 정상적인 측정 결과다.

        Given: 빈 신호일 목록
        When: 사건 번호를 매긴다
        Then: 빈 결과가 나온다
        """
        # Given
        dates = _dates([])

        # When
        result = assign_event_ids(dates)

        # Then
        assert result.empty

    def test_default_gap_is_thirty_days(self) -> None:
        """
        목적: 30일은 스펙 §7 결정 ③ 이 확정한 값이다.

        Given: 상수
        When: 값을 확인한다
        Then: 30 이다
        """
        assert EVENT_GAP_DAYS == 30

    def test_rejects_unsorted_dates(self) -> None:
        """
        목적: 날짜가 뒤섞이면 "앞 신호와의 간격"이 성립하지 않는다.

        Given: 시간 역순인 신호일 목록
        When: 사건 번호를 매긴다
        Then: ValueError
        """
        dates = _dates(["2026-06-01", "2026-01-05"])

        with pytest.raises(ValueError, match="오름차순"):
            assign_event_ids(dates)


class TestReferenceZscore:
    """참고용 z-score 산식을 손계산 값으로 고정한다."""

    def test_divides_change_rate_by_the_prior_volatility(self) -> None:
        """
        목적: z-score 는 **당일 등락률 ÷ 직전 N거래일 등락률 표준편차**다 (평균 차감 없음).

        Given: 등락률이 +10% · −10% · 0% · +10% · 0% 인 시세, 창 3일
        When: z-score 를 낸다
        Then: 5행이 1.0 이다
              (직전 3일 등락률 +0.1 · −0.1 · 0 의 표준편차가 0.1 이고, 당일 +0.1 ÷ 0.1 = 1.0)
        """
        # Given
        df = _market([100.0, 110.0, 99.0, 99.0, 108.9, 108.9])

        # When
        result = reference_zscore(df, window=3)

        # Then
        assert result.iloc[4] == pytest.approx(1.0, abs=EXACT_TOLERANCE)

    def test_zero_change_gives_zero_score(self) -> None:
        """
        목적: 보합일의 z-score 는 0 이다 — 평균을 빼지 않기 때문이다.

        Given: 같은 시세, 창 3일
        When: z-score 를 낸다
        Then: 등락률이 0인 6행이 0.0 이다
        """
        # Given
        df = _market([100.0, 110.0, 99.0, 99.0, 108.9, 108.9])

        # When
        result = reference_zscore(df, window=3)

        # Then
        assert result.iloc[5] == pytest.approx(0.0, abs=EXACT_TOLERANCE)

    def test_days_before_the_window_fills_have_no_score(self) -> None:
        """
        목적: 창이 차기 전에는 값을 내지 않는다. 창 부족을 0 으로 채우면 "평범한 날"로 읽힌다.

        Given: 창 3일
        When: z-score 를 낸다
        Then: 앞 4행이 비어 있다
              (첫 행은 등락률이 없고, 직전 3일 등락률이 모두 모이는 것은 5행부터다)
        """
        # Given
        df = _market([100.0, 110.0, 99.0, 99.0, 108.9, 108.9])

        # When
        result = reference_zscore(df, window=3)

        # Then
        assert result.isna().tolist()[:4] == [True, True, True, True]

    def test_zero_volatility_gives_no_score(self) -> None:
        """
        목적: 직전 구간의 변동이 전혀 없으면 나눌 수 없어 값이 비어 있다.

        무한대나 0 을 돌려주면 해석 보조 컬럼이 거꾸로 읽힌다.

        종가를 2배씩 올리는 것은 등락률이 **부동소수점 오차 없이 정확히 같아야** 표준편차가
        정확히 0 이 되기 때문이다. 133.1 · 146.41 같은 값은 이진수로 딱 떨어지지 않아
        표준편차가 0 이 아닌 미세한 값으로 남는다.

        Given: 등락률이 계속 +100% 로 정확히 같은 시세, 창 3일
        When: z-score 를 낸다
        Then: 5행이 비어 있다
        """
        # Given
        df = _market([100.0, 200.0, 400.0, 800.0, 1600.0])

        # When
        result = reference_zscore(df, window=3)

        # Then
        assert bool(result.isna().iloc[4])

    def test_default_window_is_sixty(self) -> None:
        """
        목적: 창 60거래일은 스펙 §11 이 확정한 값이다.

        Given: 상수
        When: 값을 확인한다
        Then: 60 이다
        """
        assert ZSCORE_WINDOW == 60

    def test_rejects_too_small_window(self) -> None:
        """
        목적: 창이 2 미만이면 표준편차를 낼 수 없다.

        Given: 창 1일
        When: z-score 를 낸다
        Then: ValueError
        """
        df = _market([100.0, 110.0, 99.0])

        with pytest.raises(ValueError, match="창"):
            reference_zscore(df, window=1)

    def test_input_is_not_modified(self) -> None:
        """
        목적: 원본 데이터 불변성을 고정한다.

        Given: 시세
        When: z-score 를 낸다
        Then: 입력이 그대로다
        """
        # Given
        df = _market([100.0, 110.0, 99.0, 99.0, 108.9])
        before = df.copy()

        # When
        reference_zscore(df, window=3)

        # Then
        pd.testing.assert_frame_equal(df, before)


class TestLookAhead:
    """미래 참조 감시 계약을 고정한다."""

    def test_event_ids_are_stable_under_truncation(self, assert_stable_under_truncation: Callable[..., None]) -> None:
        """
        목적: **look-ahead 감시** — 뒤에 신호가 더 붙어도 앞선 신호의 사건 번호가 달라지면 안 된다.

        Given: 사건이 셋으로 갈리는 신호 다섯 건
        When: 앞 3건만 준 결과와 전체를 준 결과를 비교한다
        Then: 겹치는 구간의 사건 번호가 같다
        """
        # Given
        signals = pd.DataFrame(
            {COL_DATE: pd.to_datetime(["2026-01-05", "2026-02-04", "2026-03-07", "2026-03-08", "2026-06-01"])}
        )

        def run(frame: pd.DataFrame) -> pd.DataFrame:
            return pd.DataFrame({COL_DATE: frame[COL_DATE], "EventId": assign_event_ids(frame[COL_DATE]).astype(float)})

        # When / Then
        assert_stable_under_truncation(run, signals, 3, key_columns=[COL_DATE], value_column="EventId")

    def test_zscore_is_stable_under_truncation(self, assert_stable_under_truncation: Callable[..., None]) -> None:
        """
        목적: **look-ahead 감시** — z-score 는 직전 구간만 보므로 뒤가 붙어도 달라지지 않는다.

        Given: 12거래일 시세
        When: 앞 8일만 준 결과와 전체를 준 결과를 비교한다
        Then: 겹치는 구간의 값이 같다
        """
        # Given
        df = _market([100.0, 120.0, 90.0, 110.0, 80.0, 130.0, 95.0, 105.0, 85.0, 115.0, 92.0, 108.0])

        def run(frame: pd.DataFrame) -> pd.DataFrame:
            return pd.DataFrame({COL_DATE: frame[COL_DATE], "ZScore": reference_zscore(frame, window=3)})

        # When / Then
        assert_stable_under_truncation(run, df, 8, key_columns=[COL_DATE], value_column="ZScore")
