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
    COL_CONTRACT,
    COL_CONTRACT_NAME,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_OPEN_INTEREST,
    COL_SETTLE,
    COL_SPOT,
    COL_VALUE,
    COL_VOLUME,
)
from verify_lab.data.loader import (
    MAX_DAILY_CHANGE_RATE,
    load_futures_csv,
    load_market_csv,
    load_series_csv,
)


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


# ============================================================
# 선물 시세 로더
#
# **판정이 OHLCV 시세와 세 군데에서 갈린다.** 유일 키가 `날짜 + 계약` 이고,
# 결측 종가가 정상이며, 일간 변동을 계약별로 본다. 셋 중 하나라도 공통 로더의 판정을
# 그대로 쓰면 표본이 조용히 사라지거나 정상 데이터가 막힌다.
# ============================================================


def _futures_row(
    date: str,
    contract: str,
    settle: float,
    *,
    close: float | None = None,
    volume: int = 100,
    open_interest: int = 1_000,
) -> dict[str, object]:
    """합성 선물 시세 한 행을 만든다.

    거래가 없던 날은 `close=None` 으로 표현한다 — 실제 데이터에서 그날 가격은 결측이고
    정산가만 남는다.

    Args:
        date: 거래일 (YYYY-MM-DD)
        contract: 계약 ISIN
        settle: 정산가
        close: 종가. None 이면 그날 체결이 없었다는 뜻이다
        volume: 거래량
        open_interest: 미결제약정

    Returns:
        선물 시세 스키마의 한 행
    """
    price = close if close is not None else None
    return {
        COL_DATE: date,
        COL_CONTRACT: contract,
        COL_CONTRACT_NAME: f"테스트 {contract}",
        COL_OPEN: price,
        COL_HIGH: price,
        COL_LOW: price,
        COL_CLOSE: price,
        COL_VOLUME: volume,
        COL_SETTLE: settle,
        COL_OPEN_INTEREST: open_interest,
        COL_SPOT: settle - 1.0,
    }


@pytest.fixture
def valid_futures_csv(tmp_path: Path) -> Path:
    """같은 날짜에 두 계약이 있는 정상 선물 시세 파일을 만든다."""
    return _write_csv(
        tmp_path / "futures.csv",
        [
            _futures_row("2020-09-02", "AAA", 300.0, close=300.0),
            _futures_row("2020-09-02", "BBB", 301.0, close=None, volume=0),
            _futures_row("2020-09-03", "AAA", 302.0, close=302.0),
            _futures_row("2020-09-03", "BBB", 303.0, close=None, volume=0),
        ],
    )


def test_futures_keeps_every_contract_on_the_same_date(valid_futures_csv: Path) -> None:
    """
    목적: **같은 날짜의 여러 계약이 한 행도 사라지지 않음**을 고정한다.

    공통 로더는 날짜만으로 중복을 지워 첫 계약만 남긴다. 선물에서 그렇게 되면
    차월물이 통째로 사라져 롤 계수를 구할 수 없고, 예외가 아니라 경고라서 조용히 지나간다.

    Given: 날짜 2개 × 계약 2개짜리 파일
    When: 선물 로더로 읽는다
    Then: 4행이 그대로 남는다
    """
    # Given / When
    df = load_futures_csv(valid_futures_csv)

    # Then
    assert len(df) == 4
    assert df.groupby(COL_DATE)[COL_CONTRACT].nunique().tolist() == [2, 2]


def test_futures_sorted_by_date_then_contract(tmp_path: Path) -> None:
    """
    목적: 정렬 키가 `날짜 → 계약` 임을 고정한다.

    같은 날짜 안의 순서까지 정해두지 않으면 저장할 때마다 행 순서가 흔들려
    산출물을 이전 실행과 대조할 수 없다.

    Given: 날짜와 계약이 뒤섞인 파일
    When: 선물 로더로 읽는다
    Then: 날짜 오름차순, 같은 날짜 안에서는 계약 오름차순이다
    """
    # Given
    path = _write_csv(
        tmp_path / "unsorted.csv",
        [
            _futures_row("2020-09-03", "BBB", 303.0, close=303.0),
            _futures_row("2020-09-02", "BBB", 301.0, close=301.0),
            _futures_row("2020-09-03", "AAA", 302.0, close=302.0),
            _futures_row("2020-09-02", "AAA", 300.0, close=300.0),
        ],
    )

    # When
    df = load_futures_csv(path)

    # Then
    assert df[COL_CONTRACT].tolist() == ["AAA", "BBB", "AAA", "BBB"]
    assert df[COL_SETTLE].tolist() == [300.0, 301.0, 302.0, 303.0]


def test_futures_duplicate_row_key_is_removed(tmp_path: Path) -> None:
    """
    목적: 중복 판정이 `날짜 + 계약` 조합임을 고정한다.

    Given: 같은 (날짜, 계약) 이 두 번 있는 파일
    When: 선물 로더로 읽는다
    Then: 한 행만 남는다
    """
    # Given
    path = _write_csv(
        tmp_path / "duplicated.csv",
        [
            _futures_row("2020-09-02", "AAA", 300.0, close=300.0),
            _futures_row("2020-09-02", "AAA", 300.0, close=300.0),
            _futures_row("2020-09-02", "BBB", 301.0, close=301.0),
        ],
    )

    # When
    df = load_futures_csv(path)

    # Then
    assert len(df) == 2
    assert df[COL_CONTRACT].tolist() == ["AAA", "BBB"]


def test_futures_missing_close_is_accepted(valid_futures_csv: Path) -> None:
    """
    목적: 결측 종가가 정상임을 고정한다.

    원월물은 체결이 없는 날이 많다. 공통 로더의 「결측 가격은 오류」 판정을 그대로 걸면
    정상 데이터가 통째로 막힌다.

    Given: 종가가 비어 있는 행이 포함된 파일
    When: 선물 로더로 읽는다
    Then: 예외 없이 읽히고 그 행의 종가는 결측이다
    """
    # Given / When
    df = load_futures_csv(valid_futures_csv)

    # Then
    assert df[COL_CLOSE].isna().sum() == 2


def test_futures_missing_settlement_raises(tmp_path: Path) -> None:
    """
    목적: 정산가 결측을 조용히 넘기지 않음을 고정한다.

    롤 계수를 정산가로 내므로 비면 계산이 성립하지 않는다.

    Given: 정산가가 빈 행
    When: 선물 로더로 읽는다
    Then: ValueError 를 던진다
    """
    # Given
    row = _futures_row("2020-09-02", "AAA", 300.0, close=300.0)
    row[COL_SETTLE] = None
    path = _write_csv(tmp_path / "no_settle.csv", [row])

    # When / Then
    with pytest.raises(ValueError, match="정산가 결측"):
        load_futures_csv(path)


def test_futures_zero_settlement_raises(tmp_path: Path) -> None:
    """
    목적: 정산가 0 을 오류로 봄을 고정한다.

    야간 세션·당일·스프레드 종목이 섞이면 이 값이 0 으로 온다. 수집기가 걸러내야 하며
    로더까지 왔다면 무언가 잘못된 것이다.

    Given: 정산가가 0 인 행
    When: 선물 로더로 읽는다
    Then: ValueError 를 던진다
    """
    # Given
    path = _write_csv(tmp_path / "zero_settle.csv", [_futures_row("2020-09-02", "AAA", 0.0, close=None, volume=0)])

    # When / Then
    with pytest.raises(ValueError, match="0 이하 정산가"):
        load_futures_csv(path)


def test_futures_missing_open_interest_raises(tmp_path: Path) -> None:
    """
    목적: 미결제약정 결측을 오류로 봄을 고정한다 (0 은 정상값이다).

    스프레드 종목이 섞이면 이 값이 비어서 온다.

    Given: 미결제약정이 빈 행
    When: 선물 로더로 읽는다
    Then: ValueError 를 던진다
    """
    # Given
    row = _futures_row("2020-09-02", "AAA", 300.0, close=300.0)
    row[COL_OPEN_INTEREST] = None
    path = _write_csv(tmp_path / "no_interest.csv", [row])

    # When / Then
    with pytest.raises(ValueError, match="미결제약정 결측"):
        load_futures_csv(path)


def test_futures_zero_open_interest_is_accepted(tmp_path: Path) -> None:
    """
    목적: 미결제약정 0 이 정상임을 고정한다.

    상장 직후 원월물은 미결제약정이 0 이며 실제 데이터에 그대로 존재한다.

    Given: 미결제약정이 0 인 행
    When: 선물 로더로 읽는다
    Then: 예외 없이 읽힌다
    """
    # Given
    path = _write_csv(
        tmp_path / "zero_interest.csv",
        [_futures_row("2020-09-02", "AAA", 300.0, close=None, volume=0, open_interest=0)],
    )

    # When
    df = load_futures_csv(path)

    # Then
    assert df[COL_OPEN_INTEREST].tolist() == [0]


def test_futures_daily_change_is_measured_within_contract(tmp_path: Path) -> None:
    """
    목적: 일간 변동을 **계약별로** 봄을 고정한다.

    한 프레임에 여러 계약이 날짜순으로 섞여 있어 그대로 `pct_change` 를 걸면
    서로 다른 계약의 가격을 잇게 된다. 계약 사이 가격 차이가 커도 오류가 아니다.

    Given: 두 계약의 가격이 두 배 넘게 벌어져 있지만 계약 안에서는 완만한 파일
    When: 선물 로더로 읽는다
    Then: 예외 없이 읽힌다
    """
    # Given
    path = _write_csv(
        tmp_path / "two_levels.csv",
        [
            _futures_row("2020-09-02", "AAA", 100.0, close=100.0),
            _futures_row("2020-09-02", "BBB", 300.0, close=300.0),
            _futures_row("2020-09-03", "AAA", 101.0, close=101.0),
            _futures_row("2020-09-03", "BBB", 303.0, close=303.0),
        ],
    )

    # When
    df = load_futures_csv(path)

    # Then
    assert len(df) == 4


def test_futures_extreme_change_within_contract_raises(tmp_path: Path) -> None:
    """
    목적: 한 계약 안에서 임계를 넘는 변동은 오류로 봄을 고정한다.

    Given: 같은 계약의 정산가가 하루에 임계를 넘어 뛰는 파일
    When: 선물 로더로 읽는다
    Then: ValueError 를 던진다
    """
    # Given
    jumped = 100.0 * (1 + MAX_DAILY_CHANGE_RATE + 0.01)
    path = _write_csv(
        tmp_path / "jump.csv",
        [
            _futures_row("2020-09-02", "AAA", 100.0, close=100.0),
            _futures_row("2020-09-03", "AAA", jumped, close=jumped),
        ],
    )

    # When / Then
    with pytest.raises(ValueError, match="비정상 급등락"):
        load_futures_csv(path)


def test_futures_missing_required_column_raises(tmp_path: Path) -> None:
    """
    목적: 스키마가 다르면 계산 전에 막힘을 고정한다.

    Given: 계약 컬럼이 없는 파일
    When: 선물 로더로 읽는다
    Then: ValueError 를 던진다
    """
    # Given
    row = _futures_row("2020-09-02", "AAA", 300.0, close=300.0)
    del row[COL_CONTRACT]
    path = _write_csv(tmp_path / "no_contract.csv", [row])

    # When / Then
    with pytest.raises(ValueError, match="필수 컬럼이 누락되었습니다"):
        load_futures_csv(path)


def test_futures_missing_file_raises(tmp_path: Path) -> None:
    """
    목적: 없는 파일에 대해 FileNotFoundError 를 던짐을 고정한다.

    Given: 존재하지 않는 경로
    When: 선물 로더로 읽는다
    Then: FileNotFoundError 를 던진다
    """
    # Given / When / Then
    with pytest.raises(FileNotFoundError, match="선물 시세 파일을 찾을 수 없습니다"):
        load_futures_csv(tmp_path / "없는파일.csv")


def test_futures_date_column_is_datetime64(valid_futures_csv: Path) -> None:
    """
    목적: 날짜 컬럼 dtype 을 고정한다.

    Given: 정상 선물 시세 파일
    When: 선물 로더로 읽는다
    Then: 날짜 dtype 이 datetime64[ns] 다
    """
    # Given / When
    df = load_futures_csv(valid_futures_csv)

    # Then
    assert pd.api.types.is_datetime64_any_dtype(df[COL_DATE])


def test_futures_source_file_is_not_modified(valid_futures_csv: Path) -> None:
    """
    목적: 로딩이 원본 파일을 건드리지 않음을 고정한다.

    Given: 정상 선물 시세 파일의 원본 내용
    When: 로드한다
    Then: 파일 내용이 그대로다
    """
    # Given
    before = valid_futures_csv.read_text(encoding="utf-8")

    # When
    load_futures_csv(valid_futures_csv)

    # Then
    assert valid_futures_csv.read_text(encoding="utf-8") == before
