"""yfinance 수집기의 저장 계약과 실패 정책을 고정한다.

수집기는 "무엇을 원자료로 남길 것인가"를 정하는 지점이다. 여기서 잘못 저장하면
그 위의 모든 측정이 틀린 원자료를 보게 되고, 집계값만 봐서는 알아챌 수 없다.

yfinance 는 웹 API 래퍼라 기본 인자와 반환 컬럼이 버전 사이에 조용히 바뀔 수 있다.
따라서 **어떤 인자로 호출했는지**까지 테스트로 못 박는다. 네트워크는 쓰지 않고
호출을 스텁으로 대체한다.
"""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from freezegun import freeze_time

from verify_lab.common_constants import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_VOLUME,
    REQUIRED_COLUMNS,
)
from verify_lab.data import yfinance_collector
from verify_lab.data.loader import load_market_csv
from verify_lab.data.yfinance_collector import PRICE_DECIMALS, collect_yfinance_history

# 테스트에서 오늘로 고정하는 날짜. 최근 제외 기준일은 이 날짜에서 계산된다
FROZEN_TODAY = "2026-08-11"

# 최근 제외 대상이 아닌 충분히 과거인 날짜들
OLD_DATES = ["2026-06-01", "2026-06-02", "2026-06-03"]


def _history_frame(rows: list[tuple[str, float]]) -> pd.DataFrame:
    """yfinance `history()` 가 돌려주는 형태의 DataFrame 을 만든다.

    실제 반환값은 거래소 타임존이 붙은 DatetimeIndex 를 쓰고, 필수 컬럼 외에
    `Dividends`·`Stock Splits` 를 함께 담는다. 그 형태를 그대로 흉내 낸다.

    Args:
        rows: (날짜 문자열, 종가) 목록. OHLC 는 모두 종가와 같게 채운다

    Returns:
        yfinance 반환값을 모사한 DataFrame
    """
    closes = [close for _, close in rows]
    index = pd.DatetimeIndex([pd.Timestamp(day, tz="America/New_York") for day, _ in rows], name=COL_DATE)

    return pd.DataFrame(
        {
            COL_OPEN: closes,
            COL_HIGH: closes,
            COL_LOW: closes,
            COL_CLOSE: closes,
            COL_VOLUME: [1_000] * len(rows),
            "Dividends": [0.0] * len(rows),
            "Stock Splits": [0.0] * len(rows),
        },
        index=index,
    )


def _stub_yfinance(
    monkeypatch: pytest.MonkeyPatch,
    frame: pd.DataFrame,
) -> dict[str, object]:
    """yfinance 호출을 스텁으로 대체하고 호출 인자를 기록한다.

    Args:
        monkeypatch: 테스트 종료 시 원복을 보장하는 pytest 패치 도구
        frame: 스텁이 돌려줄 DataFrame

    Returns:
        호출 기록 dict. `symbol` 에 생성 인자, `kwargs` 에 `history()` 인자가 담긴다
    """
    recorded: dict[str, object] = {}

    class _StubTicker:
        def __init__(self, symbol: str) -> None:
            recorded["symbol"] = symbol

        def history(self, **kwargs: object) -> pd.DataFrame:
            recorded["kwargs"] = kwargs
            return frame

    monkeypatch.setattr(yfinance_collector, "yf", SimpleNamespace(Ticker=_StubTicker))

    return recorded


@pytest.fixture
def old_rows() -> list[tuple[str, float]]:
    """최근 제외 대상이 아닌 정상 3거래일."""
    return [(OLD_DATES[0], 100.0), (OLD_DATES[1], 101.0), (OLD_DATES[2], 102.0)]


@freeze_time(FROZEN_TODAY)
def test_saved_file_name_follows_ticker_max_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, float]]
) -> None:
    """
    목적: 저장 파일명 규칙을 하나로 고정한다.

    파일명이 여러 갈래면 로더가 어느 파일을 읽어야 하는지 모호해진다.

    Given: 정상 응답을 돌려주는 스텁
    When: QQQ 를 수집한다
    Then: `QQQ_max.csv` 가 만들어진다
    """
    # Given
    _stub_yfinance(monkeypatch, _history_frame(old_rows))

    # When
    result = collect_yfinance_history("QQQ", output_dir=tmp_path)

    # Then
    assert result.path == tmp_path / "QQQ_max.csv"
    assert result.path.is_file()


@freeze_time(FROZEN_TODAY)
def test_ticker_is_normalized_to_upper_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, float]]
) -> None:
    """
    목적: 티커 표기 차이로 같은 종목이 두 파일에 나뉘지 않게 고정한다.

    Given: 소문자로 입력한 티커
    When: 수집한다
    Then: 조회와 파일명 모두 대문자를 쓴다
    """
    # Given
    recorded = _stub_yfinance(monkeypatch, _history_frame(old_rows))

    # When
    result = collect_yfinance_history(" qqq ", output_dir=tmp_path)

    # Then
    assert recorded["symbol"] == "QQQ"
    assert result.path.name == "QQQ_max.csv"


@freeze_time(FROZEN_TODAY)
def test_history_is_called_with_adjusted_price_and_raising_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, float]]
) -> None:
    """
    목적: yfinance 호출 인자를 명시적으로 고정한다.

    `auto_adjust` 가 빠지면 원본가를 수정주가로 착각해 분배락일이 인위적 하락으로 잡히고,
    `raise_errors` 가 빠지면 조회 실패가 예외 대신 빈 DataFrame 으로 조용히 돌아온다.
    둘 다 지금은 기대한 값이 기본값이지만, 기본값에 기대면 그 변경이 소리 없이 통과한다.

    Given: 정상 응답을 돌려주는 스텁
    When: 수집한다
    Then: 전 기간·수정주가·예외 전파 인자가 전달된다
    """
    # Given
    recorded = _stub_yfinance(monkeypatch, _history_frame(old_rows))

    # When
    collect_yfinance_history("QQQ", output_dir=tmp_path)

    # Then
    kwargs = recorded["kwargs"]
    assert kwargs == {"period": "max", "auto_adjust": True, "raise_errors": True}


@freeze_time(FROZEN_TODAY)
def test_saved_columns_match_market_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, float]]
) -> None:
    """
    목적: 저장 스키마를 고정한다 (컬럼 구성과 순서).

    yfinance 가 함께 주는 `Dividends`·`Stock Splits` 는 원시 시세 스키마에 없으므로 남기지 않는다.

    Given: 부가 컬럼이 섞인 응답
    When: 수집한다
    Then: 저장 파일의 컬럼이 필수 컬럼과 정확히 같다
    """
    # Given
    _stub_yfinance(monkeypatch, _history_frame(old_rows))

    # When
    result = collect_yfinance_history("QQQ", output_dir=tmp_path)

    # Then
    saved = pd.read_csv(result.path)
    assert list(saved.columns) == REQUIRED_COLUMNS


@freeze_time(FROZEN_TODAY)
def test_saved_dates_use_iso_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, float]]
) -> None:
    """
    목적: 날짜 저장 포맷을 고정한다.

    이미 저장돼 있는 원시 시세 파일이 `YYYY-MM-DD` 를 쓰므로 코드가 데이터에 맞춘다.
    타임존이 붙은 문자열이 섞이면 같은 폴더의 파일이 서로 다른 포맷을 갖게 된다.

    Given: 거래소 타임존이 붙은 응답
    When: 수집한다
    Then: 저장된 첫 날짜가 타임존 없는 ISO 날짜다
    """
    # Given
    _stub_yfinance(monkeypatch, _history_frame(old_rows))

    # When
    result = collect_yfinance_history("QQQ", output_dir=tmp_path)

    # Then
    saved = pd.read_csv(result.path)
    assert saved[COL_DATE].iloc[0] == OLD_DATES[0]


@freeze_time(FROZEN_TODAY)
def test_recent_rows_are_excluded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 확정되지 않은 최근 데이터를 저장하지 않음을 고정한다.

    미국장은 한국 시각 기준으로 하루가 밀리고, 마감 직후 값은 확정값이 아니다.
    미확정 종가가 그대로 들어오면 그날이 "역대급 등락"으로 잡힐 수 있다.

    Given: 오늘·어제를 포함한 응답
    When: 수집한다
    Then: 기준일 이후 행이 저장되지 않는다
    """
    # Given
    rows = [
        ("2026-08-05", 100.0),
        ("2026-08-06", 101.0),
        ("2026-08-07", 102.0),
        ("2026-08-10", 103.0),
        (FROZEN_TODAY, 104.0),
    ]
    _stub_yfinance(monkeypatch, _history_frame(rows))

    # When
    result = collect_yfinance_history("QQQ", output_dir=tmp_path)

    # Then
    assert result.end_date == date(2026, 8, 7)


@freeze_time(FROZEN_TODAY)
def test_excluded_recent_count_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 줄어든 표본이 조용히 사라지지 않음을 고정한다 (표본 보존).

    Given: 최근 2거래일이 포함된 5행 응답
    When: 수집한다
    Then: 저장 행 수와 제외 건수의 합이 원래 행 수와 같다
    """
    # Given
    rows = [
        ("2026-08-05", 100.0),
        ("2026-08-06", 101.0),
        ("2026-08-07", 102.0),
        ("2026-08-10", 103.0),
        (FROZEN_TODAY, 104.0),
    ]
    _stub_yfinance(monkeypatch, _history_frame(rows))

    # When
    result = collect_yfinance_history("QQQ", output_dir=tmp_path)

    # Then
    assert result.excluded_recent_count == 2
    assert result.row_count + result.excluded_recent_count == len(rows)


@freeze_time(FROZEN_TODAY)
def test_old_data_is_not_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, float]]
) -> None:
    """
    목적: 제외 대상이 하나도 없는 경우를 고정한다 (경계 조건).

    Given: 전부 충분히 과거인 응답
    When: 수집한다
    Then: 한 행도 빠지지 않는다
    """
    # Given
    _stub_yfinance(monkeypatch, _history_frame(old_rows))

    # When
    result = collect_yfinance_history("QQQ", output_dir=tmp_path)

    # Then
    assert result.excluded_recent_count == 0
    assert result.row_count == len(old_rows)


@freeze_time(FROZEN_TODAY)
def test_reported_period_matches_saved_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, float]]
) -> None:
    """
    목적: 요약에 보고되는 기간이 실제 저장 내용과 일치함을 고정한다.

    Given: 정상 3거래일 응답
    When: 수집한다
    Then: 시작·종료일과 행 수가 저장 파일과 같다
    """
    # Given
    _stub_yfinance(monkeypatch, _history_frame(old_rows))

    # When
    result = collect_yfinance_history("QQQ", output_dir=tmp_path)

    # Then
    saved = pd.read_csv(result.path)
    assert result.row_count == len(saved)
    assert result.start_date == date(2026, 6, 1)
    assert result.end_date == date(2026, 6, 3)


@freeze_time(FROZEN_TODAY)
def test_prices_are_rounded_before_saving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 저장 직전 반올림 자릿수를 고정한다.

    Given: 자릿수가 긴 가격이 담긴 응답
    When: 수집한다
    Then: 저장된 종가가 규정 자릿수로 반올림된다
    """
    # Given
    raw_close = 100.1234567891
    _stub_yfinance(monkeypatch, _history_frame([(OLD_DATES[0], raw_close)]))

    # When
    result = collect_yfinance_history("QQQ", output_dir=tmp_path)

    # Then
    saved = pd.read_csv(result.path)
    assert saved[COL_CLOSE].iloc[0] == pytest.approx(round(raw_close, PRICE_DECIMALS), abs=1e-12)


@freeze_time(FROZEN_TODAY)
def test_saved_file_is_readable_by_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, float]]
) -> None:
    """
    목적: 수집기가 남긴 파일을 로더가 그대로 읽을 수 있음을 고정한다 (계층 간 계약).

    수집과 로딩이 서로 다른 스키마를 전제하면 "받아는 놨는데 읽을 수 없는" 파일이 생긴다.

    Given: 수집으로 저장된 파일
    When: 로더로 읽는다
    Then: 같은 행 수가 예외 없이 반환된다
    """
    # Given
    _stub_yfinance(monkeypatch, _history_frame(old_rows))
    result = collect_yfinance_history("QQQ", output_dir=tmp_path)

    # When
    loaded = load_market_csv(result.path)

    # Then
    assert len(loaded) == result.row_count


@freeze_time(FROZEN_TODAY)
def test_empty_response_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 빈 응답을 성공으로 처리하지 않음을 고정한다.

    Given: 아무 행도 없는 응답
    When: 수집한다
    Then: ValueError 가 발생한다
    """
    # Given
    _stub_yfinance(monkeypatch, _history_frame([]))

    # When / Then
    with pytest.raises(ValueError, match="비어"):
        collect_yfinance_history("QQQ", output_dir=tmp_path)


@freeze_time(FROZEN_TODAY)
def test_all_rows_excluded_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 최근 제외로 데이터가 전부 사라진 경우를 고정한다 (경계 조건).

    Given: 최근 2거래일에만 데이터가 있는 응답
    When: 수집한다
    Then: ValueError 가 발생한다
    """
    # Given
    _stub_yfinance(monkeypatch, _history_frame([("2026-08-10", 100.0), (FROZEN_TODAY, 101.0)]))

    # When / Then
    with pytest.raises(ValueError, match="제외 후"):
        collect_yfinance_history("QQQ", output_dir=tmp_path)


@freeze_time(FROZEN_TODAY)
def test_invalid_data_is_not_saved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 검증을 통과한 데이터만 저장됨을 고정한다.

    yfinance 의 국내 ETF 처럼 값이 망가진 응답을 그대로 저장하면, 그 값이 원자료가 되어
    이후 모든 측정이 오염된다. 예외만 던지고 파일을 남기면 반쪽짜리 파일이 남는다.

    Given: 전일 대비 두 배가 되는 응답
    When: 수집한다
    Then: ValueError 가 발생하고 파일이 만들어지지 않는다
    """
    # Given
    _stub_yfinance(monkeypatch, _history_frame([(OLD_DATES[0], 100.0), (OLD_DATES[1], 200.0)]))

    # When / Then
    with pytest.raises(ValueError, match="급등락"):
        collect_yfinance_history("QQQ", output_dir=tmp_path)

    assert not (tmp_path / "QQQ_max.csv").exists()


@freeze_time(FROZEN_TODAY)
def test_missing_schema_column_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 반환 컬럼이 바뀐 경우를 즉시 드러냄을 고정한다.

    Given: 거래량 컬럼이 빠진 응답
    When: 수집한다
    Then: ValueError 가 발생하고 메시지에 누락 컬럼이 담긴다
    """
    # Given
    frame = _history_frame([(OLD_DATES[0], 100.0)]).drop(columns=[COL_VOLUME])
    _stub_yfinance(monkeypatch, frame)

    # When / Then
    with pytest.raises(ValueError, match="누락"):
        collect_yfinance_history("QQQ", output_dir=tmp_path)


@freeze_time(FROZEN_TODAY)
def test_blank_ticker_raises(tmp_path: Path) -> None:
    """
    목적: 잘못된 입력을 조회 전에 막음을 고정한다.

    Given: 공백뿐인 티커
    When: 수집한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="종목"):
        collect_yfinance_history("   ", output_dir=tmp_path)


@freeze_time(FROZEN_TODAY)
def test_output_directory_is_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, float]]
) -> None:
    """
    목적: 저장 폴더가 없어도 수집이 성립함을 고정한다 (경계 조건).

    Given: 아직 없는 저장 폴더
    When: 수집한다
    Then: 폴더가 만들어지고 파일이 저장된다
    """
    # Given
    output_dir = tmp_path / "market"
    _stub_yfinance(monkeypatch, _history_frame(old_rows))

    # When
    result = collect_yfinance_history("QQQ", output_dir=output_dir)

    # Then
    assert result.path.is_file()


@freeze_time(FROZEN_TODAY)
def test_high_low_columns_are_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, float]]
) -> None:
    """
    목적: 가격 컬럼이 뒤바뀌지 않고 그대로 저장됨을 고정한다.

    Given: OHLC 가 모두 종가와 같은 응답
    When: 수집한다
    Then: 저장된 고가·저가가 종가와 같다
    """
    # Given
    _stub_yfinance(monkeypatch, _history_frame(old_rows))

    # When
    result = collect_yfinance_history("QQQ", output_dir=tmp_path)

    # Then
    saved = pd.read_csv(result.path)
    assert saved[COL_HIGH].tolist() == saved[COL_CLOSE].tolist()
    assert saved[COL_LOW].tolist() == saved[COL_OPEN].tolist()
