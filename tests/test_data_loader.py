"""시세 파일 로딩의 반환 계약과 예외 정책을 고정한다.

로더는 모든 검증이 데이터를 만나는 첫 지점이다. 여기서 이상을 조용히 메우면
그 위의 측정 결과 전체가 무효가 되므로, "무엇을 거르고 무엇을 예외로 던지는가"를
코드로 못 박는다.

실제 시세 파일에 의존하면 데이터를 갱신할 때마다 테스트가 깨지므로 합성 데이터만 쓴다.
"""

from pathlib import Path

import pandas as pd
import pytest

from verify_lab.common_constants import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_VALUE,
    COL_VOLUME,
)
from verify_lab.data.loader import MAX_DAILY_CHANGE_RATE, load_market_csv, load_series_csv


def _write_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    """합성 시세 행을 CSV로 써서 경로를 돌려준다."""
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _row(date: str, close: float, volume: int = 1_000) -> dict[str, object]:
    """OHLC가 모두 같은 단순한 하루치 행을 만든다."""
    return {
        COL_DATE: date,
        COL_OPEN: close,
        COL_HIGH: close,
        COL_LOW: close,
        COL_CLOSE: close,
        COL_VOLUME: volume,
    }


@pytest.fixture
def valid_csv(tmp_path: Path) -> Path:
    """이상이 없는 3거래일짜리 시세 파일."""
    return _write_csv(
        tmp_path / "TEST_max.csv",
        [_row("2026-01-02", 100.0), _row("2026-01-05", 101.0), _row("2026-01-06", 102.0)],
    )


def test_returns_all_required_columns(valid_csv: Path) -> None:
    """
    목적: 반환 DataFrame의 컬럼 구성을 고정한다.

    Given: 정상 시세 파일
    When: 로드한다
    Then: 필수 컬럼이 모두 들어 있다
    """
    df = load_market_csv(valid_csv)

    assert {COL_DATE, COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME} <= set(df.columns)


def test_date_column_is_datetime64(valid_csv: Path) -> None:
    """
    목적: 날짜 dtype을 고정한다.

    확장창 순위와 이동평균 같은 창 기반 연산이 벡터화되려면 object dtype이면 안 된다.

    Given: 정상 시세 파일
    When: 로드한다
    Then: 날짜 컬럼이 datetime64 다
    """
    df = load_market_csv(valid_csv)

    assert pd.api.types.is_datetime64_any_dtype(df[COL_DATE])


def test_rows_are_sorted_by_date(tmp_path: Path) -> None:
    """
    목적: 입력 순서와 무관하게 날짜 오름차순으로 반환됨을 고정한다.

    Given: 날짜가 뒤섞인 파일
    When: 로드한다
    Then: 날짜가 오름차순이다
    """
    # Given
    path = _write_csv(
        tmp_path / "unsorted.csv",
        [_row("2026-01-06", 102.0), _row("2026-01-02", 100.0), _row("2026-01-05", 101.0)],
    )

    # When
    df = load_market_csv(path)

    # Then
    assert df[COL_DATE].is_monotonic_increasing


def test_index_is_reset_after_sorting(tmp_path: Path) -> None:
    """
    목적: 정렬 후 인덱스가 0부터 다시 매겨짐을 고정한다.

    Given: 날짜가 뒤섞인 파일
    When: 로드한다
    Then: 인덱스가 0..N-1 이다
    """
    path = _write_csv(
        tmp_path / "unsorted.csv",
        [_row("2026-01-06", 102.0), _row("2026-01-02", 100.0)],
    )

    df = load_market_csv(path)

    assert list(df.index) == [0, 1]


def test_duplicate_dates_are_removed(tmp_path: Path) -> None:
    """
    목적: 중복 날짜가 한 건만 남음을 고정한다.

    Given: 같은 날짜가 두 번 들어 있는 파일
    When: 로드한다
    Then: 그 날짜가 한 번만 남는다
    """
    # Given
    path = _write_csv(
        tmp_path / "dup.csv",
        [_row("2026-01-02", 100.0), _row("2026-01-02", 100.0), _row("2026-01-05", 101.0)],
    )

    # When
    df = load_market_csv(path)

    # Then
    assert len(df) == 2
    assert df[COL_DATE].duplicated().sum() == 0


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    """
    목적: 없는 파일을 조용히 빈 결과로 넘기지 않음을 고정한다.

    Given: 존재하지 않는 경로
    When: 로드한다
    Then: FileNotFoundError 가 발생한다
    """
    with pytest.raises(FileNotFoundError):
        load_market_csv(tmp_path / "없는파일.csv")


def test_missing_required_column_raises(tmp_path: Path) -> None:
    """
    목적: 스키마가 다른 파일을 즉시 거부함을 고정한다.

    Given: 거래량 컬럼이 없는 파일
    When: 로드한다
    Then: ValueError 가 발생하고 메시지에 누락 컬럼이 담긴다
    """
    # Given
    rows = [_row("2026-01-02", 100.0)]
    del rows[0][COL_VOLUME]
    path = _write_csv(tmp_path / "no_volume.csv", rows)

    # When / Then
    with pytest.raises(ValueError, match="필수 컬럼"):
        load_market_csv(path)


def test_missing_price_value_raises(tmp_path: Path) -> None:
    """
    목적: 결측 가격을 보간하지 않고 예외로 드러냄을 고정한다 (보간 금지).

    Given: 종가가 비어 있는 행이 섞인 파일
    When: 로드한다
    Then: ValueError 가 발생한다
    """
    # Given
    rows = [_row("2026-01-02", 100.0), _row("2026-01-05", 101.0)]
    rows[1][COL_CLOSE] = None
    path = _write_csv(tmp_path / "missing.csv", rows)

    # When / Then
    with pytest.raises(ValueError, match="결측"):
        load_market_csv(path)


def test_zero_price_raises(tmp_path: Path) -> None:
    """
    목적: 0원 가격을 데이터 오류로 판정함을 고정한다.

    Given: 종가가 0인 행이 섞인 파일
    When: 로드한다
    Then: ValueError 가 발생한다
    """
    path = _write_csv(tmp_path / "zero.csv", [_row("2026-01-02", 100.0), _row("2026-01-05", 0.0)])

    with pytest.raises(ValueError, match="0 이하"):
        load_market_csv(path)


def test_negative_price_raises(tmp_path: Path) -> None:
    """
    목적: 음수 가격을 데이터 오류로 판정함을 고정한다.

    Given: 종가가 음수인 행이 섞인 파일
    When: 로드한다
    Then: ValueError 가 발생한다
    """
    path = _write_csv(tmp_path / "negative.csv", [_row("2026-01-02", 100.0), _row("2026-01-05", -1.0)])

    with pytest.raises(ValueError, match="0 이하"):
        load_market_csv(path)


def test_extreme_daily_change_raises(tmp_path: Path) -> None:
    """
    목적: 물리적으로 불가능한 일간 변동을 데이터 오류로 판정함을 고정한다.

    yfinance 의 국내 ETF 처럼 값이 망가진 소스를 조용히 통과시키면 그 값이 그대로
    "역대급 이벤트"로 잡힌다.

    Given: 전일 대비 두 배가 되는 행
    When: 로드한다
    Then: ValueError 가 발생한다
    """
    path = _write_csv(tmp_path / "extreme.csv", [_row("2026-01-02", 100.0), _row("2026-01-05", 200.0)])

    with pytest.raises(ValueError, match="급등락"):
        load_market_csv(path)


def test_change_just_below_threshold_is_accepted(tmp_path: Path) -> None:
    """
    목적: 임계 바로 아래의 급변동은 통과함을 고정한다 (경계 조건).

    국내 지수 ETF 의 가격제한폭(±30%)과 QQQ 의 역대 최대 변동(약 ±17%)이
    모두 임계 아래에 있어야 정상 데이터가 오탐되지 않는다.

    Given: 임계보다 조금 작은 상승
    When: 로드한다
    Then: 예외 없이 두 행이 반환된다
    """
    # Given
    just_below = 100.0 * (1 + MAX_DAILY_CHANGE_RATE - 0.01)
    path = _write_csv(tmp_path / "edge.csv", [_row("2026-01-02", 100.0), _row("2026-01-05", just_below)])

    # When
    df = load_market_csv(path)

    # Then
    assert len(df) == 2


def test_single_row_file_is_accepted(tmp_path: Path) -> None:
    """
    목적: 변동률을 계산할 수 없는 최소 길이 입력을 고정한다 (경계 조건).

    Given: 한 행짜리 파일
    When: 로드한다
    Then: 예외 없이 한 행이 반환된다
    """
    path = _write_csv(tmp_path / "single.csv", [_row("2026-01-02", 100.0)])

    assert len(load_market_csv(path)) == 1


def test_empty_file_raises(tmp_path: Path) -> None:
    """
    목적: 행이 하나도 없는 파일을 빈 결과로 통과시키지 않음을 고정한다 (경계 조건).

    Given: 헤더만 있는 파일
    When: 로드한다
    Then: ValueError 가 발생한다
    """
    # Given
    path = tmp_path / "empty.csv"
    path.write_text("Date,Open,High,Low,Close,Volume\n", encoding="utf-8")

    # When / Then
    with pytest.raises(ValueError, match="비어"):
        load_market_csv(path)


def test_source_file_is_not_modified(valid_csv: Path) -> None:
    """
    목적: 로딩이 원본 파일을 건드리지 않음을 고정한다 (원시 시세 불변).

    Given: 정상 시세 파일의 원본 내용
    When: 로드한다
    Then: 파일 내용이 그대로다
    """
    # Given
    before = valid_csv.read_text(encoding="utf-8")

    # When
    load_market_csv(valid_csv)

    # Then
    assert valid_csv.read_text(encoding="utf-8") == before


# ============================================================
# 일별 단일 값 시계열 로더
# ============================================================
#
# 시세 로더와 **의도적으로 다른 계약**을 갖는다. 값의 부호와 변동폭을 검사하지 않는다 —
# 금리는 0 과 음수가 실제로 존재하고, 환율은 하루에 수십 % 움직인 해가 있다.
# 시세 로더의 판정을 그대로 걸면 정상 데이터가 예외로 막힌다.


def _series_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    """합성 단일 값 시계열을 CSV로 써서 경로를 돌려준다."""
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


@pytest.fixture
def valid_series_csv(tmp_path: Path) -> Path:
    """이상이 없는 3일짜리 단일 값 시계열."""
    return _series_csv(
        tmp_path / "TEST_series.csv",
        [
            {COL_DATE: "2026-01-02", COL_VALUE: 1_380.50},
            {COL_DATE: "2026-01-05", COL_VALUE: 1_382.10},
            {COL_DATE: "2026-01-06", COL_VALUE: 1_379.90},
        ],
    )


def test_series_returns_required_columns(valid_series_csv: Path) -> None:
    """
    목적: 단일 값 시계열의 반환 컬럼을 고정한다.

    Given: 정상 시계열 파일
    When: 로드한다
    Then: 날짜와 값 컬럼이 들어 있다
    """
    df = load_series_csv(valid_series_csv)

    assert {COL_DATE, COL_VALUE} <= set(df.columns)


def test_series_date_column_is_datetime64(valid_series_csv: Path) -> None:
    """
    목적: 날짜 dtype 을 고정한다.

    금리·환율은 거래일 기준으로 시세와 정렬해야 하므로 object dtype 이면 안 된다.

    Given: 정상 시계열 파일
    When: 로드한다
    Then: 날짜 컬럼이 datetime64 다
    """
    df = load_series_csv(valid_series_csv)

    assert pd.api.types.is_datetime64_any_dtype(df[COL_DATE])


def test_series_rows_are_sorted_and_reindexed(tmp_path: Path) -> None:
    """
    목적: 입력 순서와 무관하게 날짜 오름차순이고 인덱스가 0부터임을 고정한다.

    Given: 날짜가 뒤섞인 시계열 파일
    When: 로드한다
    Then: 날짜가 오름차순이고 인덱스가 0부터 연속이다
    """
    # Given
    path = _series_csv(
        tmp_path / "unsorted.csv",
        [
            {COL_DATE: "2026-01-06", COL_VALUE: 3.0},
            {COL_DATE: "2026-01-02", COL_VALUE: 1.0},
            {COL_DATE: "2026-01-05", COL_VALUE: 2.0},
        ],
    )

    # When
    df = load_series_csv(path)

    # Then
    assert df[COL_DATE].is_monotonic_increasing
    assert df.index.tolist() == [0, 1, 2]


def test_series_duplicate_dates_are_removed(tmp_path: Path) -> None:
    """
    목적: 같은 날짜가 두 번 오면 첫 행만 남김을 고정한다.

    Given: 날짜가 중복된 시계열 파일
    When: 로드한다
    Then: 행이 하나로 줄고 먼저 나온 값이 남는다
    """
    # Given
    path = _series_csv(
        tmp_path / "duplicated.csv",
        [
            {COL_DATE: "2026-01-02", COL_VALUE: 1.0},
            {COL_DATE: "2026-01-02", COL_VALUE: 9.0},
        ],
    )

    # When
    df = load_series_csv(path)

    # Then
    assert len(df) == 1
    assert df[COL_VALUE].iloc[0] == pytest.approx(1.0, abs=1e-12)


def test_series_accepts_zero_and_negative_values(tmp_path: Path) -> None:
    """
    목적: 0 과 음수를 정상 값으로 통과시킴을 고정한다.

    **시세 로더와 갈리는 지점이다.** 마이너스 금리와 0% 금리는 실제로 존재하며,
    시세의 "0 이하 가격은 오류" 판정을 여기 그대로 걸면 정상 데이터가 막힌다.

    Given: 0 과 음수가 섞인 시계열 파일
    When: 로드한다
    Then: 예외 없이 모든 행이 남는다
    """
    # Given
    path = _series_csv(
        tmp_path / "negative.csv",
        [
            {COL_DATE: "2026-01-02", COL_VALUE: 0.0},
            {COL_DATE: "2026-01-05", COL_VALUE: -0.35},
        ],
    )

    # When
    df = load_series_csv(path)

    # Then
    assert len(df) == 2
    assert df[COL_VALUE].tolist() == pytest.approx([0.0, -0.35], abs=1e-12)


def test_series_accepts_large_daily_change(tmp_path: Path) -> None:
    """
    목적: 하루 사이 큰 변동을 오류로 보지 않음을 고정한다 (경계 조건).

    원달러는 1997년에 하루 20% 넘게 움직인 날이 있고 그것은 실제 시장 사건이다.

    Given: 하루 만에 두 배가 된 시계열 파일
    When: 로드한다
    Then: 예외 없이 로드된다
    """
    # Given
    path = _series_csv(
        tmp_path / "jump.csv",
        [
            {COL_DATE: "1997-12-22", COL_VALUE: 1_000.0},
            {COL_DATE: "1997-12-23", COL_VALUE: 2_000.0},
        ],
    )

    # When
    df = load_series_csv(path)

    # Then
    assert len(df) == 2


def test_series_missing_file_raises(tmp_path: Path) -> None:
    """
    목적: 파일이 없을 때의 예외 타입을 고정한다.

    Given: 존재하지 않는 경로
    When: 로드한다
    Then: FileNotFoundError 가 발생한다
    """
    with pytest.raises(FileNotFoundError):
        load_series_csv(tmp_path / "없는파일.csv")


def test_series_missing_required_column_raises(tmp_path: Path) -> None:
    """
    목적: 컬럼 구성이 다르면 즉시 실패함을 고정한다.

    Given: 값 컬럼이 없는 파일
    When: 로드한다
    Then: ValueError 가 발생하고 메시지에 빠진 컬럼명이 담긴다
    """
    # Given
    path = tmp_path / "no_value.csv"
    pd.DataFrame([{COL_DATE: "2026-01-02", "Rate": 1.0}]).to_csv(path, index=False)

    # When / Then
    with pytest.raises(ValueError, match=COL_VALUE):
        load_series_csv(path)


def test_series_missing_value_raises(tmp_path: Path) -> None:
    """
    목적: 결측을 메우지 않고 예외로 막음을 고정한다 (보간 금지).

    Given: 값이 비어 있는 행이 있는 파일
    When: 로드한다
    Then: ValueError 가 발생한다
    """
    # Given
    path = _series_csv(
        tmp_path / "missing.csv",
        [
            {COL_DATE: "2026-01-02", COL_VALUE: 1.0},
            {COL_DATE: "2026-01-05", COL_VALUE: None},
        ],
    )

    # When / Then
    with pytest.raises(ValueError, match="결측"):
        load_series_csv(path)


def test_series_empty_file_raises(tmp_path: Path) -> None:
    """
    목적: 헤더만 있는 파일을 정상으로 보지 않음을 고정한다 (경계 조건).

    Given: 헤더만 있는 파일
    When: 로드한다
    Then: ValueError 가 발생한다
    """
    # Given
    path = tmp_path / "empty_series.csv"
    path.write_text(f"{COL_DATE},{COL_VALUE}\n", encoding="utf-8")

    # When / Then
    with pytest.raises(ValueError, match="비어"):
        load_series_csv(path)


def test_series_source_file_is_not_modified(valid_series_csv: Path) -> None:
    """
    목적: 로딩이 원본 파일을 건드리지 않음을 고정한다.

    Given: 정상 시계열 파일의 원본 내용
    When: 로드한다
    Then: 파일 내용이 그대로다
    """
    # Given
    before = valid_series_csv.read_text(encoding="utf-8")

    # When
    load_series_csv(valid_series_csv)

    # Then
    assert valid_series_csv.read_text(encoding="utf-8") == before
