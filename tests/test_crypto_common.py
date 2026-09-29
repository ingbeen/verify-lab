"""암호화폐 두 수집기가 공유하는 판정을 고정한다.

비트코인은 하루가 **UTC 00:00 에 끝난다** — 한국 시각으로 09:00 이다. 그래서 「아직 끝나지 않은 봉」의
경계가 KST 09:00 에 한 칸 움직이고, 그 앞뒤로 저장 범위가 하루씩 달라진다. 이 경계를 두 수집기가
따로 계산하면 한쪽만 하루 밀려도 예외가 나지 않으므로 판정을 한 곳에 두고 여기서 고정한다.

빠진 날 수는 「빈 공간 없이 받았는가」를 매 수집마다 숫자로 보려고 센다. **메우지 않는다.**
"""

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME, KST
from verify_lab.data.crypto_common import (
    count_missing_days,
    exclude_unfinished_days,
    load_crypto_market_csv,
    require_complete_range,
    unfinished_utc_day,
)
from verify_lab.data.loader import load_market_csv


def _frame(days: list[date]) -> pd.DataFrame:
    """날짜마다 종가가 하나씩 있는 합성 프레임."""
    return pd.DataFrame({COL_DATE: days, COL_CLOSE: [100.0 + i for i in range(len(days))]})


def _write_market(path: Path, closes: list[float]) -> Path:
    """종가 목록으로 시세 스키마 CSV 를 쓴다 — 시가·고가·저가는 종가와 같다.

    Args:
        path: 저장할 파일
        closes: 날마다의 종가

    Returns:
        저장한 경로
    """
    days = pd.date_range("2011-10-26", periods=len(closes), freq="D").strftime("%Y-%m-%d")
    pd.DataFrame(
        {
            COL_DATE: days,
            COL_OPEN: closes,
            COL_HIGH: closes,
            COL_LOW: closes,
            COL_CLOSE: closes,
            COL_VOLUME: [1.0] * len(closes),
        }
    ).to_csv(path, index=False)

    return path


class TestCryptoMarketLoader:
    """비트코인 시세는 «한 로더»로 읽는다 — 급등락 임계값을 호출마다 넘기지 않는다

    공용 로더에 임계값을 호출마다 넘기면 **수집기와 로더가 같은 값을 넘긴다는 약속이 기억에만 걸린다** —
    측정 runner 가 평소처럼 `load_market_csv(path)` 로 부르면 2011-10-28 +56.1% 에서 막힌다
    (2026-09-29 사용자 결정 d · `docs/검증/반감기_사이클/설계.md`).
    """

    def test_실제로_있었던_큰_변동은_통과한다(self, tmp_path: Path) -> None:
        """
        목적: 비트코인 임계값이 실제 최대 변동(+56.1%)을 막지 않음을 고정한다.

        Given: 하루 +56% 가 한 번 있는 시세 파일
        When: 비트코인 로더로 읽는다
        Then: 예외 없이 네 행이 읽힌다
        """
        # Given
        path = _write_market(tmp_path / "BTCUSD_max.csv", [10.0, 10.0, 15.6, 15.0])

        # When
        frame = load_crypto_market_csv(path)

        # Then
        assert len(frame) == 4

    def test_공용_로더는_같은_파일을_막는다(self, tmp_path: Path) -> None:
        """
        목적: 위 통과가 비트코인 로더의 «임계값» 덕분임을 대조로 고정한다 — 공용 값(0.50)이면 막힌다.

        Given: 같은 시세 파일
        When: 공용 로더를 인자 없이 부른다
        Then: 급등락으로 ValueError 가 발생한다
        """
        # Given
        path = _write_market(tmp_path / "BTCUSD_max.csv", [10.0, 10.0, 15.6, 15.0])

        # When / Then
        with pytest.raises(ValueError, match="급등락"):
            load_market_csv(path)

    def test_자릿수_오류_모양의_변동은_여전히_막는다(self, tmp_path: Path) -> None:
        """
        목적: 임계값을 넓혀도 데이터 오류(÷10 = −90%)는 걸림을 고정한다 (경계 조건).

        Given: 하루 −90% 가 있는 시세 파일
        When: 비트코인 로더로 읽는다
        Then: ValueError 가 발생한다
        """
        # Given
        path = _write_market(tmp_path / "BTCUSD_max.csv", [10.0, 10.0, 1.0, 1.0])

        # When / Then
        with pytest.raises(ValueError, match="급등락"):
            load_crypto_market_csv(path)


def test_before_kst_nine_the_previous_utc_day_is_still_open() -> None:
    """
    목적: KST 09:00 전에는 UTC 로 아직 전날이라 그날 봉이 끝나지 않았음을 고정한다 (경계 조건).

    Given: KST 2026-09-29 08:59 (= UTC 2026-09-28 23:59)
    When: 끝나지 않은 UTC 날짜를 구한다
    Then: 2026-09-28 이다
    """
    assert unfinished_utc_day(datetime(2026, 9, 29, 8, 59, tzinfo=KST)) == date(2026, 9, 28)


def test_at_kst_nine_a_new_utc_day_opens() -> None:
    """
    목적: KST 09:00 에 UTC 새 날이 열려 전날 봉이 확정됨을 고정한다 (경계 조건).

    Given: KST 2026-09-29 09:00 (= UTC 2026-09-29 00:00)
    When: 끝나지 않은 UTC 날짜를 구한다
    Then: 2026-09-29 이다
    """
    assert unfinished_utc_day(datetime(2026, 9, 29, 9, 0, tzinfo=KST)) == date(2026, 9, 29)


def test_naive_datetime_is_rejected() -> None:
    """
    목적: 시간대 없는 시각을 받지 않음을 고정한다.

    시간대가 없으면 실행 PC 의 시간대로 읽혀 **PC 마다 경계가 하루 갈린다** — 예외 없이 저장 범위만 달라진다.

    Given: 시간대 없는 datetime
    When: 끝나지 않은 UTC 날짜를 구한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="시간대"):
        unfinished_utc_day(datetime(2026, 9, 29, 9, 0))


def test_before_kst_nine_two_rows_are_excluded() -> None:
    """
    목적: 끝나지 않은 날과 그 뒤의 행을 빼고 뺀 건수를 돌려줌을 고정한다 (표본 보존).

    Given: 09-27 · 09-28 · 09-29 세 행, 기준 시각 KST 09-29 08:59
    When: 끝나지 않은 날을 뺀다
    Then: 09-27 만 남고 제외 건수는 2 다
    """
    # Given
    frame = _frame([date(2026, 9, 27), date(2026, 9, 28), date(2026, 9, 29)])

    # When
    trimmed, excluded = exclude_unfinished_days(frame, datetime(2026, 9, 29, 8, 59, tzinfo=KST))

    # Then
    assert trimmed[COL_DATE].tolist() == [date(2026, 9, 27)]
    assert excluded == 2


def test_at_kst_nine_only_the_new_day_is_excluded() -> None:
    """
    목적: KST 09:00 이 지나면 전날 봉이 저장 대상에 들어옴을 고정한다 (경계 조건).

    Given: 09-27 · 09-28 · 09-29 세 행, 기준 시각 KST 09-29 09:00
    When: 끝나지 않은 날을 뺀다
    Then: 09-27 · 09-28 이 남고 제외 건수는 1 이다
    """
    # Given
    frame = _frame([date(2026, 9, 27), date(2026, 9, 28), date(2026, 9, 29)])

    # When
    trimmed, excluded = exclude_unfinished_days(frame, datetime(2026, 9, 29, 9, 0, tzinfo=KST))

    # Then
    assert trimmed[COL_DATE].tolist() == [date(2026, 9, 27), date(2026, 9, 28)]
    assert excluded == 1


def test_exclusion_does_not_modify_the_input() -> None:
    """
    목적: 입력 프레임을 바꾸지 않음을 고정한다 (데이터 불변성).

    Given: 세 행짜리 프레임
    When: 끝나지 않은 날을 뺀다
    Then: 원본은 세 행 그대로다
    """
    # Given
    frame = _frame([date(2026, 9, 27), date(2026, 9, 28), date(2026, 9, 29)])
    before = frame.copy()

    # When
    exclude_unfinished_days(frame, datetime(2026, 9, 29, 9, 0, tzinfo=KST))

    # Then
    pd.testing.assert_frame_equal(frame, before)


def test_missing_days_are_counted_not_filled() -> None:
    """
    목적: 첫 날과 마지막 날 사이에 행이 없는 달력일을 셈을 고정한다.

    Given: 1일 · 2일 · 5일 (3일 · 4일이 빠짐)
    When: 빠진 날을 센다
    Then: 2 다
    """
    days = pd.Series([date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 5)])

    assert count_missing_days(days) == 2


def test_no_missing_day_counts_zero() -> None:
    """
    목적: 빈틈 없는 날짜 목록은 0 임을 고정한다.

    Given: 연속한 사흘
    When: 빠진 날을 센다
    Then: 0 이다
    """
    days = pd.Series([date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)])

    assert count_missing_days(days) == 0


def test_single_day_counts_zero() -> None:
    """
    목적: 한 행짜리 입력의 빠진 날은 0 임을 고정한다 (경계 조건).

    Given: 하루
    When: 빠진 날을 센다
    Then: 0 이다
    """
    assert count_missing_days(pd.Series([date(2026, 1, 1)])) == 0


def test_duplicate_days_do_not_hide_a_gap() -> None:
    """
    목적: 같은 날이 두 번 있어도 빠진 날을 가리지 않음을 고정한다.

    행 수로 세면 중복 하루가 빠진 하루를 상쇄해 0 이 나온다 — 날짜 종류 수로 센다.

    Given: 1일 · 1일 · 3일 (2일이 빠짐)
    When: 빠진 날을 센다
    Then: 1 이다
    """
    days = pd.Series([date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 3)])

    assert count_missing_days(days) == 1


def test_empty_dates_are_rejected() -> None:
    """
    목적: 빈 입력을 「빠진 날 0」으로 통과시키지 않음을 고정한다 (경계 조건).

    Given: 빈 Series
    When: 빠진 날을 센다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="비어"):
        count_missing_days(pd.Series([], dtype=object))


# 받은 범위 확인의 기준 시각 — KST 2026-09-29 10:00 (= UTC 09-29 01:00). 끝난 마지막 UTC 날은 09-28 이다
_NOW = datetime(2026, 9, 29, 10, 0, tzinfo=KST)


def test_range_reaching_the_last_finished_day_passes() -> None:
    """
    목적: 첫 날이 맞고 끝난 마지막 날까지 닿은 범위는 통과함을 고정한다.

    Given: 09-26 ~ 09-28, 소스 첫 날 09-26, 지연 0
    When: 범위를 확인한다
    Then: 예외가 없다
    """
    days = pd.Series([date(2026, 9, 26), date(2026, 9, 27), date(2026, 9, 28)])

    require_complete_range(days, first_day=date(2026, 9, 26), now=_NOW, publication_lag_days=0)


def test_range_that_starts_late_is_rejected() -> None:
    """
    목적: 소스의 첫 날에서 시작하지 않는 범위를 막음을 고정한다 (앞이 잘림).

    Given: 09-27 ~ 09-28, 소스 첫 날 09-26
    When: 범위를 확인한다
    Then: ValueError 가 발생한다
    """
    days = pd.Series([date(2026, 9, 27), date(2026, 9, 28)])

    with pytest.raises(ValueError, match="시작"):
        require_complete_range(days, first_day=date(2026, 9, 26), now=_NOW, publication_lag_days=0)


def test_range_that_ends_before_the_last_finished_day_is_rejected() -> None:
    """
    목적: 공개 지연이 없는 소스에서 끝난 마지막 날보다 일찍 끝난 범위를 막음을 고정한다 (뒤가 잘림).

    Given: 09-26 ~ 09-27, 끝난 마지막 날 09-28, 지연 0
    When: 범위를 확인한다
    Then: ValueError 가 발생한다
    """
    days = pd.Series([date(2026, 9, 26), date(2026, 9, 27)])

    with pytest.raises(ValueError, match="끝"):
        require_complete_range(days, first_day=date(2026, 9, 26), now=_NOW, publication_lag_days=0)


def test_publication_lag_allows_exactly_that_many_days() -> None:
    """
    목적: 공개 지연 일수만큼 이른 끝은 통과하고 하루 더 이르면 막음을 고정한다 (경계 조건).

    Given: 끝난 마지막 날 09-28, 지연 1 — 09-25 부터 빈틈없이 09-27 까지인 범위와 09-26 까지인 범위
    When: 범위를 확인한다
    Then: 09-27 은 통과하고 09-26 은 ValueError 다
    """
    first = date(2026, 9, 25)
    through_27 = pd.Series([first, date(2026, 9, 26), date(2026, 9, 27)])
    through_26 = pd.Series([first, date(2026, 9, 26)])

    require_complete_range(through_27, first_day=first, now=_NOW, publication_lag_days=1)
    with pytest.raises(ValueError, match="끝"):
        require_complete_range(through_26, first_day=first, now=_NOW, publication_lag_days=1)


def test_negative_publication_lag_is_rejected() -> None:
    """
    목적: 음수 지연 일수를 받지 않음을 고정한다 (입력 검증).

    Given: 지연 −1
    When: 범위를 확인한다
    Then: ValueError 가 발생한다
    """
    days = pd.Series([date(2026, 9, 28)])

    with pytest.raises(ValueError, match="지연"):
        require_complete_range(days, first_day=date(2026, 9, 28), now=_NOW, publication_lag_days=-1)


def test_empty_range_is_rejected() -> None:
    """
    목적: 빈 날짜 목록을 「확인 통과」로 넘기지 않음을 고정한다 (경계 조건).

    Given: 빈 Series
    When: 범위를 확인한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="비어"):
        require_complete_range(
            pd.Series([], dtype=object), first_day=date(2026, 9, 28), now=_NOW, publication_lag_days=0
        )


def test_range_with_a_gap_in_between_is_rejected() -> None:
    """
    목적: 양 끝이 맞아도 사이에 빠진 날이 있으면 막음을 고정한다 (2026-09-29 사용자 결정).

    Given: 09-26 · 09-28 (09-27 이 빠짐), 소스 첫 날 09-26, 끝난 마지막 날 09-28
    When: 범위를 확인한다
    Then: ValueError 가 발생한다
    """
    days = pd.Series([date(2026, 9, 26), date(2026, 9, 28)])

    with pytest.raises(ValueError, match="빠진 날"):
        require_complete_range(days, first_day=date(2026, 9, 26), now=_NOW, publication_lag_days=0)
