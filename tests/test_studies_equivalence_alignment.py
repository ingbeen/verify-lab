"""세 소스를 ETF 거래일에 맞추는 정렬 규칙을 고정한다.

원달러 고시일·미국 영업일·KRX 거래일은 **서로 다른 달력**이다. 정렬 규칙을 명시하지 않으면
어긋난 채로 계산이 돌아가고 예외도 나지 않는다.

이 테스트가 지키는 것은 셋이다.

1. **마스터 달력은 ETF 거래일이다** — 회귀 대상이 ETF 수익률이므로
2. **조용히 사라지는 표본이 없다** — 제외와 이월은 반드시 건수로 보고된다
3. **이월은 달러금리에만 허용된다** — 사양서 §6.5 가 미국 휴일만 전일값 이월로 규정했다
"""

from datetime import date

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VALUE, COL_VOLUME
from verify_lab.studies.usdkrw_equivalence.alignment import align_to_etf_calendar, to_market_dates
from verify_lab.studies.usdkrw_equivalence.constants import (
    COL_DAY_COUNT,
    COL_ETF_CLOSE,
    COL_KRW_RATE,
    COL_SPOT,
    COL_USD_RATE,
    KEY_KRW_RATE_MISSING,
    KEY_SPOT_MISSING,
    KEY_USD_RATE_CARRIED,
    KEY_USD_RATE_MISSING,
)


def _etf(dates: list[str], closes: list[float]) -> pd.DataFrame:
    """합성 ETF 시세를 만든다."""
    return pd.DataFrame(
        {
            COL_DATE: pd.to_datetime(dates),
            COL_OPEN: closes,
            COL_HIGH: closes,
            COL_LOW: closes,
            COL_CLOSE: closes,
            COL_VOLUME: [1_000] * len(dates),
        }
    )


def _series(dates: list[str], values: list[float]) -> pd.DataFrame:
    """합성 단일 값 시계열을 만든다."""
    return pd.DataFrame({COL_DATE: pd.to_datetime(dates), COL_VALUE: values})


ETF_DATES = ["2026-01-02", "2026-01-05", "2026-01-06"]
FULL_SPOT = _series(ETF_DATES, [1_380.0, 1_385.0, 1_390.0])
FULL_KRW = _series(ETF_DATES, [3.50, 3.50, 3.51])
FULL_USD = _series(ETF_DATES, [4.20, 4.21, 4.22])


def test_master_calendar_is_etf_trading_days() -> None:
    """
    목적: 결과 날짜가 ETF 거래일과 같음을 고정한다.

    Given: ETF 보다 날짜가 많은 보조 시계열들
    When: 정렬한다
    Then: ETF 거래일만 남는다
    """
    # Given
    wide = ["2026-01-01", *ETF_DATES, "2026-01-07"]
    spot = _series(wide, [1.0, 1_380.0, 1_385.0, 1_390.0, 9.0])
    krw = _series(wide, [1.0, 3.50, 3.50, 3.51, 9.0])
    usd = _series(wide, [1.0, 4.20, 4.21, 4.22, 9.0])

    # When
    result = align_to_etf_calendar(_etf(ETF_DATES, [14_000, 14_050, 14_100]), spot, krw, usd)

    # Then
    assert result.frame[COL_DATE].dt.date.tolist() == [date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6)]


def test_returns_all_expected_columns() -> None:
    """
    목적: 정렬 결과의 컬럼 구성을 고정한다.

    Given: 결측 없는 입력
    When: 정렬한다
    Then: 계산에 필요한 컬럼이 모두 있다
    """
    result = align_to_etf_calendar(_etf(ETF_DATES, [14_000, 14_050, 14_100]), FULL_SPOT, FULL_KRW, FULL_USD)

    assert {COL_DATE, COL_ETF_CLOSE, COL_SPOT, COL_KRW_RATE, COL_USD_RATE, COL_DAY_COUNT} <= set(result.frame.columns)


def test_day_count_is_calendar_days_from_previous_row() -> None:
    """
    목적: 일수가 **달력일** 차이임을 고정한다.

    이자는 달력일로 붙는다. 거래일 수로 세면 주말 사흘치 이자가 사라진다.

    Given: 금요일 다음이 월요일인 거래일 배열
    When: 정렬한다
    Then: 그 칸의 일수가 3이다
    """
    # Given: 2026-01-02(금) → 2026-01-05(월)
    result = align_to_etf_calendar(_etf(ETF_DATES, [14_000, 14_050, 14_100]), FULL_SPOT, FULL_KRW, FULL_USD)

    # Then
    assert result.frame[COL_DAY_COUNT].tolist()[1:] == [3.0, 1.0]


def test_first_row_has_no_day_count() -> None:
    """
    목적: 첫 행의 일수가 비어 있음을 고정한다 (경계 조건).

    직전 거래일이 없으므로 그 행에는 수익률도 이자도 정의되지 않는다.

    Given: 결측 없는 입력
    When: 정렬한다
    Then: 첫 행의 일수가 결측이다
    """
    result = align_to_etf_calendar(_etf(ETF_DATES, [14_000, 14_050, 14_100]), FULL_SPOT, FULL_KRW, FULL_USD)

    assert pd.isna(result.frame[COL_DAY_COUNT].iloc[0])


def test_missing_spot_row_is_dropped_and_counted() -> None:
    """
    목적: 환율이 없는 거래일을 **제외하고 건수를 보고**함을 고정한다.

    환율은 이 검증의 기준 가격이라 이월하지 않는다. 없으면 그날은 계산 대상이 아니다.

    Given: 하루치 환율이 빠진 입력
    When: 정렬한다
    Then: 그 행이 빠지고 제외 건수가 1이다
    """
    # Given
    spot = _series(["2026-01-02", "2026-01-06"], [1_380.0, 1_390.0])

    # When
    result = align_to_etf_calendar(_etf(ETF_DATES, [14_000, 14_050, 14_100]), spot, FULL_KRW, FULL_USD)

    # Then
    assert len(result.frame) == 2
    assert result.counts[KEY_SPOT_MISSING] == 1


def test_missing_krw_rate_row_is_dropped_and_counted() -> None:
    """
    목적: 원화금리가 없는 거래일도 제외하고 건수를 보고함을 고정한다.

    사양서 §6.5 는 **미국 휴일만** 전일값 이월로 규정했다. 원화금리는 그 대상이 아니다.

    Given: 하루치 원화금리가 빠진 입력
    When: 정렬한다
    Then: 그 행이 빠지고 제외 건수가 1이다
    """
    # Given
    krw = _series(["2026-01-02", "2026-01-06"], [3.50, 3.51])

    # When
    result = align_to_etf_calendar(_etf(ETF_DATES, [14_000, 14_050, 14_100]), FULL_SPOT, krw, FULL_USD)

    # Then
    assert len(result.frame) == 2
    assert result.counts[KEY_KRW_RATE_MISSING] == 1


def test_missing_usd_rate_is_carried_forward_and_counted() -> None:
    """
    목적: 달러금리 결측을 **전일값으로 이월하고 건수를 보고**함을 고정한다.

    사양서 §6.5 "미국 휴일은 T-bill 전일값 이월" 을 코드로 옮긴 것이다.

    Given: 가운데 날의 달러금리가 빠진 입력
    When: 정렬한다
    Then: 그 행이 남고 값이 직전 값이며 이월 건수가 1이다
    """
    # Given
    usd = _series(["2026-01-02", "2026-01-06"], [4.20, 4.22])

    # When
    result = align_to_etf_calendar(_etf(ETF_DATES, [14_000, 14_050, 14_100]), FULL_SPOT, FULL_KRW, usd)

    # Then
    assert len(result.frame) == 3
    assert result.frame[COL_USD_RATE].tolist() == pytest.approx([4.20, 4.20, 4.22], abs=1e-12)
    assert result.counts[KEY_USD_RATE_CARRIED] == 1
    assert result.counts[KEY_USD_RATE_MISSING] == 0


def test_usd_rate_before_first_available_is_dropped() -> None:
    """
    목적: 이월할 직전 값이 없으면 제외하고 건수를 보고함을 고정한다 (경계 조건).

    이월은 **뒤에서 앞으로 채우지 않는다.** 미래 값을 끌어오면 look-ahead 다.

    Given: 첫 거래일보다 늦게 시작하는 달러금리
    When: 정렬한다
    Then: 앞선 행이 빠지고 결측 건수가 1이다
    """
    # Given
    usd = _series(["2026-01-05", "2026-01-06"], [4.21, 4.22])

    # When
    result = align_to_etf_calendar(_etf(ETF_DATES, [14_000, 14_050, 14_100]), FULL_SPOT, FULL_KRW, usd)

    # Then
    assert len(result.frame) == 2
    assert result.counts[KEY_USD_RATE_MISSING] == 1


def test_day_count_spans_dropped_rows() -> None:
    """
    목적: 행이 제외되면 일수가 그만큼 벌어짐을 고정한다.

    제외된 날에도 이자는 붙는다. 남은 행의 일수가 실제 경과 일수를 담아야
    이자 합계가 어긋나지 않는다.

    Given: 가운데 거래일의 환율이 빠진 입력
    When: 정렬한다
    Then: 마지막 행의 일수가 2일이 아니라 4일이다
    """
    # Given: 01-02 → (01-05 제외) → 01-06
    spot = _series(["2026-01-02", "2026-01-06"], [1_380.0, 1_390.0])

    # When
    result = align_to_etf_calendar(_etf(ETF_DATES, [14_000, 14_050, 14_100]), spot, FULL_KRW, FULL_USD)

    # Then
    assert result.frame[COL_DAY_COUNT].iloc[-1] == pytest.approx(4.0, abs=1e-12)


def test_empty_overlap_raises() -> None:
    """
    목적: 겹치는 날이 하나도 없으면 빈 결과를 돌려주지 않음을 고정한다 (경계 조건).

    Given: 기간이 전혀 겹치지 않는 입력
    When: 정렬한다
    Then: ValueError 가 발생한다
    """
    spot = _series(["2020-01-02"], [1_100.0])

    with pytest.raises(ValueError, match="겹치는"):
        align_to_etf_calendar(_etf(ETF_DATES, [14_000, 14_050, 14_100]), spot, FULL_KRW, FULL_USD)


def test_source_frames_are_not_modified() -> None:
    """
    목적: 정렬이 원본 DataFrame 을 건드리지 않음을 고정한다 (데이터 불변성).

    Given: 입력 프레임의 사본
    When: 정렬한다
    Then: 원본이 그대로다
    """
    # Given
    etf = _etf(ETF_DATES, [14_000, 14_050, 14_100])
    before = etf.copy()

    # When
    align_to_etf_calendar(etf, FULL_SPOT, FULL_KRW, FULL_USD)

    # Then
    pd.testing.assert_frame_equal(etf, before)


def test_alignment_is_stable_under_truncation(assert_stable_under_truncation) -> None:  # type: ignore[no-untyped-def]
    """
    목적: 뒤를 잘라내도 앞선 행의 값이 같음을 고정한다 (look-ahead 감시).

    이월이 뒤에서 앞으로 채우면 이 계약이 깨진다.

    Given: 달러금리에 구멍이 있는 긴 입력
    When: 뒤를 잘라 정렬한 결과와 전체를 정렬한 결과를 비교한다
    Then: 겹치는 범위의 값이 같다
    """
    # Given
    dates = [f"2026-01-{day:02d}" for day in range(2, 12)]
    etf = _etf(dates, [14_000 + index * 10 for index in range(len(dates))])
    spot = _series(dates, [1_380.0 + index for index in range(len(dates))])
    krw = _series(dates, [3.50] * len(dates))
    usd = _series([d for index, d in enumerate(dates) if index % 3 != 1], [4.20] * 7)

    # When / Then
    assert_stable_under_truncation(
        lambda frame: align_to_etf_calendar(frame, spot, krw, usd).frame,
        etf,
        cut=6,
        key_columns=[COL_DATE],
        value_column=COL_USD_RATE,
    )


# ============================================================
# 매매기준율의 고시 시차 보정
# ============================================================


def test_market_dates_shift_publication_back_by_one_row() -> None:
    """
    목적: 고시값이 **직전 고시일의 시장**에 대응하도록 옮겨짐을 고정한다.

    매매기준율은 전영업일 은행간 거래의 가중평균이다. 보정하지 않으면 ETF 종가와 하루 어긋난 채
    계산되며 예외도 나지 않는다.

    Given: 고시일 기준 3행짜리 환율
    When: 시장일 기준으로 옮긴다
    Then: 각 값이 직전 고시일의 날짜를 갖는다
    """
    # Given
    spot = _series(["2026-01-02", "2026-01-05", "2026-01-06"], [1_380.0, 1_385.0, 1_390.0])

    # When
    result = to_market_dates(spot)

    # Then
    assert result[COL_DATE].dt.date.tolist() == [date(2026, 1, 2), date(2026, 1, 5)]
    assert result[COL_VALUE].tolist() == pytest.approx([1_385.0, 1_390.0], abs=1e-12)


def test_market_dates_drop_the_last_publication() -> None:
    """
    목적: 대응할 시장일이 없는 첫 고시가 빠짐을 고정한다 (경계 조건).

    Given: 3행짜리 환율
    When: 시장일 기준으로 옮긴다
    Then: 2행이 남는다
    """
    spot = _series(["2026-01-02", "2026-01-05", "2026-01-06"], [1_380.0, 1_385.0, 1_390.0])

    assert len(to_market_dates(spot)) == 2


def test_market_dates_reject_too_short_input() -> None:
    """
    목적: 보정할 수 없는 입력을 조용히 빈 표로 돌려주지 않음을 고정한다 (경계 조건).

    Given: 한 행짜리 환율
    When: 시장일 기준으로 옮긴다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="시차 보정"):
        to_market_dates(_series(["2026-01-02"], [1_380.0]))


def test_market_dates_do_not_modify_source() -> None:
    """
    목적: 보정이 원본을 건드리지 않음을 고정한다 (데이터 불변성).

    Given: 환율 시계열의 사본
    When: 시장일 기준으로 옮긴다
    Then: 원본이 그대로다
    """
    spot = _series(["2026-01-02", "2026-01-05"], [1_380.0, 1_385.0])
    before = spot.copy()

    to_market_dates(spot)

    pd.testing.assert_frame_equal(spot, before)
