"""pykrx 수집기의 저장 계약과 실패 정책을 고정한다.

이 수집기는 국내 원시 시세의 유일한 생성 지점이다. 여기서 잘못 저장하면 그 위의 모든 측정이
틀린 원자료를 보게 되고, 집계값만 봐서는 알아챌 수 없다. 특히 두 가지가 조용히 깨진다.

1. **부호 없는 정수(`uint32`)** — 그대로 저장하면 차분에서 언더플로우가 나서 하락일이
   40억 근처의 거대한 양수가 된다. 예외가 아니라 그럴듯한 숫자로 나타난다
2. **자격증명과 pykrx import 의 순서** — `import pykrx` 자체가 로그인을 시도하므로
   순서가 뒤집히면 조회가 통째로 실패한다

네트워크는 쓰지 않는다. pykrx 호출을 스텁으로 대체하고, 실제 패키지는 import 하지 않는다.
"""

import sys
from datetime import date
from pathlib import Path
from types import ModuleType, SimpleNamespace

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
from verify_lab.data import pykrx_collector
from verify_lab.data.loader import load_market_csv
from verify_lab.data.pykrx_collector import collect_pykrx_history

# 테스트에서 오늘로 고정하는 날짜. 최근 제외 기준일은 이 날짜에서 계산된다
FROZEN_TODAY = "2026-08-12"

# 검증 #1 의 국내 대상과 그 상장일
TICKER = "069500"
LISTING_DATE = "20021014"

# 최근 제외 대상이 아닌 충분히 과거인 날짜들
OLD_DATES = ["2026-06-01", "2026-06-02", "2026-06-03"]


def _etf_frame(rows: list[tuple[str, int]]) -> pd.DataFrame:
    """`get_etf_ohlcv_by_date` 반환 형태를 모사한다.

    실제 반환값은 `날짜` 인덱스에 `NAV`·`거래대금`·`기초지수` 를 함께 담고,
    **가격을 `uint32`, 거래량·거래대금을 `uint64`** 로 준다. 그 dtype 까지 그대로 흉내 낸다.

    Args:
        rows: (날짜 문자열, 종가) 목록. OHLC 는 모두 종가와 같게 채운다

    Returns:
        pykrx ETF 조회 반환값을 모사한 DataFrame
    """
    closes = [close for _, close in rows]
    index = pd.DatetimeIndex([pd.Timestamp(day) for day, _ in rows], name=pykrx_collector.KRX_INDEX_NAME)

    frame = pd.DataFrame(
        {
            "NAV": [float(close) for close in closes],
            "시가": closes,
            "고가": closes,
            "저가": closes,
            "종가": closes,
            "거래량": [1_000] * len(rows),
            "거래대금": [10_000_000] * len(rows),
            "기초지수": [float(close) / 100 for close in closes],
        },
        index=index,
    )

    return frame.astype(
        {
            "시가": "uint32",
            "고가": "uint32",
            "저가": "uint32",
            "종가": "uint32",
            "거래량": "uint64",
            "거래대금": "uint64",
        }
    )


def _market_frame(rows: list[tuple[str, int]]) -> pd.DataFrame:
    """`get_market_ohlcv(adjusted=True)` 반환 형태를 모사한다.

    ETF 조회와 달리 `거래대금`·`NAV` 가 없고 `등락률` 이 붙으며, dtype 이 `int64` 다.
    같은 pykrx 라도 함수마다 반환이 다르다는 사실을 테스트에 담는다.

    Args:
        rows: (날짜 문자열, 종가) 목록

    Returns:
        pykrx 개별종목 조회 반환값을 모사한 DataFrame
    """
    closes = [close for _, close in rows]
    index = pd.DatetimeIndex([pd.Timestamp(day) for day, _ in rows], name=pykrx_collector.KRX_INDEX_NAME)

    return pd.DataFrame(
        {
            "시가": closes,
            "고가": closes,
            "저가": closes,
            "종가": closes,
            "거래량": [1_000] * len(rows),
            "등락률": [float("nan")] + [0.5] * (len(rows) - 1) if rows else [],
        },
        index=index,
    )


def _stub_pykrx(monkeypatch: pytest.MonkeyPatch, frame: pd.DataFrame) -> dict[str, object]:
    """pykrx 조회를 스텁으로 대체하고 호출 내용을 기록한다.

    Args:
        monkeypatch: 테스트 종료 시 원복을 보장하는 pytest 패치 도구
        frame: 스텁이 돌려줄 DataFrame

    Returns:
        호출 기록 dict. `function` 에 함수 이름, `args`·`kwargs` 에 전달 인자가 담긴다
    """
    recorded: dict[str, object] = {}

    def _record(name: str) -> object:
        def _call(*args: object, **kwargs: object) -> pd.DataFrame:
            recorded["function"] = name
            recorded["args"] = args
            recorded["kwargs"] = kwargs
            return frame

        return _call

    stub_stock = SimpleNamespace(
        get_etf_ohlcv_by_date=_record("get_etf_ohlcv_by_date"),
        get_market_ohlcv=_record("get_market_ohlcv"),
    )
    monkeypatch.setattr(pykrx_collector, "_import_pykrx_stock", lambda: stub_stock)

    return recorded


@pytest.fixture
def old_rows() -> list[tuple[str, int]]:
    """최근 제외 대상이 아닌 정상 3거래일."""
    return [(OLD_DATES[0], 30_000), (OLD_DATES[1], 30_500), (OLD_DATES[2], 31_000)]


@freeze_time(FROZEN_TODAY)
def test_raw_basis_uses_default_file_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, int]]
) -> None:
    """
    목적: 원본가 파일명 규칙을 고정한다.

    Given: 정상 응답을 돌려주는 스텁
    When: 원본가로 수집한다
    Then: `<종목>_max.csv` 가 만들어진다
    """
    # Given
    _stub_pykrx(monkeypatch, _etf_frame(old_rows))

    # When
    result = collect_pykrx_history(TICKER, LISTING_DATE, adjusted=False, output_dir=tmp_path)

    # Then
    assert result.path == tmp_path / f"{TICKER}_max.csv"
    assert result.path.is_file()


@freeze_time(FROZEN_TODAY)
def test_adjusted_basis_uses_separate_file_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, int]]
) -> None:
    """
    목적: 가격 기준이 다르면 파일이 갈린다는 계약을 고정한다.

    두 기준을 한 파일에 섞으면 어느 행이 어느 기준인지 알 수 없게 되고,
    측정 계층이 기준을 혼용하게 된다.

    Given: 정상 응답을 돌려주는 스텁
    When: 수정주가로 수집한다
    Then: `<종목>_adjusted_max.csv` 가 만들어진다
    """
    # Given
    _stub_pykrx(monkeypatch, _market_frame(old_rows))

    # When
    result = collect_pykrx_history(TICKER, LISTING_DATE, adjusted=True, output_dir=tmp_path)

    # Then
    assert result.path == tmp_path / f"{TICKER}_adjusted_max.csv"
    assert result.path.is_file()


@freeze_time(FROZEN_TODAY)
def test_raw_basis_calls_etf_function(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, int]]
) -> None:
    """
    목적: 원본가 조회 경로를 고정한다.

    ETF 는 주식 ISIN 목록에 없어 `get_market_ohlcv(adjusted=False)` 가 아예 동작하지 않는다.
    원본가는 ETF 전용 함수로만 얻을 수 있다.

    Given: 정상 응답을 돌려주는 스텁
    When: 원본가로 수집한다
    Then: `get_etf_ohlcv_by_date` 가 종목·기간과 함께 호출된다
    """
    # Given
    recorded = _stub_pykrx(monkeypatch, _etf_frame(old_rows))

    # When
    collect_pykrx_history(TICKER, LISTING_DATE, adjusted=False, output_dir=tmp_path)

    # Then
    assert recorded["function"] == "get_etf_ohlcv_by_date"
    assert recorded["args"] == (LISTING_DATE, "20260812", TICKER)


@freeze_time(FROZEN_TODAY)
def test_adjusted_basis_passes_adjusted_flag_explicitly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, int]]
) -> None:
    """
    목적: 수정주가 인자를 명시적으로 넘김을 고정한다.

    `adjusted` 가 빠지면 라이브러리 기본값에 따라 원본가가 돌아올 수 있고, 그러면
    두 파일이 같은 내용이 되어 대조 자체가 무의미해진다. 그 사고는 소리 없이 일어난다.

    Given: 정상 응답을 돌려주는 스텁
    When: 수정주가로 수집한다
    Then: `get_market_ohlcv` 가 `adjusted=True` 와 함께 호출된다
    """
    # Given
    recorded = _stub_pykrx(monkeypatch, _market_frame(old_rows))

    # When
    collect_pykrx_history(TICKER, LISTING_DATE, adjusted=True, output_dir=tmp_path)

    # Then
    assert recorded["function"] == "get_market_ohlcv"
    assert recorded["kwargs"] == {"adjusted": True}


@freeze_time(FROZEN_TODAY)
def test_korean_columns_are_normalized_at_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, int]]
) -> None:
    """
    목적: 정규화 시점을 수집 시점으로 고정한다 (계층 간 계약).

    저장 파일이 이미 공통 스키마면 로더는 파일의 출처를 몰라도 된다.
    `NAV`·`거래대금`·`기초지수` 는 공통 스키마에 없으므로 저장하지 않는다.

    Given: 한글 컬럼과 부가 컬럼이 섞인 응답
    When: 수집한다
    Then: 저장 파일의 컬럼이 필수 컬럼과 정확히 같다
    """
    # Given
    _stub_pykrx(monkeypatch, _etf_frame(old_rows))

    # When
    result = collect_pykrx_history(TICKER, LISTING_DATE, adjusted=False, output_dir=tmp_path)

    # Then
    saved = pd.read_csv(result.path)
    assert list(saved.columns) == REQUIRED_COLUMNS


@freeze_time(FROZEN_TODAY)
def test_saved_dates_use_iso_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, int]]
) -> None:
    """
    목적: 날짜 저장 포맷을 고정한다.

    이미 저장돼 있는 원시 시세 파일이 `YYYY-MM-DD` 를 쓰므로 코드가 데이터에 맞춘다.

    Given: 날짜 인덱스를 가진 응답
    When: 수집한다
    Then: 저장된 첫 날짜가 ISO 날짜 문자열이다
    """
    # Given
    _stub_pykrx(monkeypatch, _etf_frame(old_rows))

    # When
    result = collect_pykrx_history(TICKER, LISTING_DATE, adjusted=False, output_dir=tmp_path)

    # Then
    saved = pd.read_csv(result.path)
    assert saved[COL_DATE].iloc[0] == OLD_DATES[0]


@freeze_time(FROZEN_TODAY)
def test_unsigned_prices_become_signed_integers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 부호 없는 정수를 그대로 남기지 않음을 고정한다.

    `uint32` 를 그대로 두면 하락일의 전일 대비 차분이 언더플로우로 40억 근처 양수가 된다.
    예외가 아니라 **그럴듯한 숫자**로 나타나므로, 저장 dtype 을 계약으로 못 박아야 한다.

    Given: 하락일이 포함된 `uint32` 응답
    When: 수집한 뒤 저장 파일을 읽는다
    Then: 가격 dtype 이 부호 있는 정수이고, 하락일의 변동률이 음수다
    """
    # Given
    rows = [(OLD_DATES[0], 30_000), (OLD_DATES[1], 27_000)]
    frame = _etf_frame(rows)
    assert frame["종가"].dtype == "uint32"
    _stub_pykrx(monkeypatch, frame)

    # When
    result = collect_pykrx_history(TICKER, LISTING_DATE, adjusted=False, output_dir=tmp_path)
    saved = pd.read_csv(result.path)

    # Then
    assert saved[COL_CLOSE].dtype == "int64"
    assert saved[COL_CLOSE].pct_change().iloc[-1] == pytest.approx(-0.1, abs=1e-12)


@freeze_time(FROZEN_TODAY)
def test_today_row_is_excluded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 확정되지 않은 당일 데이터를 저장하지 않음을 고정한다.

    국내는 시차가 없어 전일 종가가 확정이지만, **장중에도 당일 행이 그대로 반환**된다.
    미확정 종가가 남으면 그날이 극단 이벤트로 잡힌다.

    Given: 어제와 오늘이 포함된 응답
    When: 수집한다
    Then: 마지막 저장일이 어제다
    """
    # Given
    rows = [("2026-08-10", 30_000), ("2026-08-11", 30_100), (FROZEN_TODAY, 30_200)]
    _stub_pykrx(monkeypatch, _etf_frame(rows))

    # When
    result = collect_pykrx_history(TICKER, LISTING_DATE, adjusted=False, output_dir=tmp_path)

    # Then
    assert result.end_date == date(2026, 8, 11)


@freeze_time(FROZEN_TODAY)
def test_excluded_recent_count_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 줄어든 표본이 조용히 사라지지 않음을 고정한다 (표본 보존).

    Given: 당일이 포함된 3행 응답
    When: 수집한다
    Then: 저장 행 수와 제외 건수의 합이 원래 행 수와 같다
    """
    # Given
    rows = [("2026-08-10", 30_000), ("2026-08-11", 30_100), (FROZEN_TODAY, 30_200)]
    _stub_pykrx(monkeypatch, _etf_frame(rows))

    # When
    result = collect_pykrx_history(TICKER, LISTING_DATE, adjusted=False, output_dir=tmp_path)

    # Then
    assert result.excluded_recent_count == 1
    assert result.row_count + result.excluded_recent_count == len(rows)


@freeze_time(FROZEN_TODAY)
def test_old_data_is_not_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, int]]
) -> None:
    """
    목적: 제외 대상이 하나도 없는 경우를 고정한다 (경계 조건).

    Given: 전부 충분히 과거인 응답
    When: 수집한다
    Then: 한 행도 빠지지 않는다
    """
    # Given
    _stub_pykrx(monkeypatch, _etf_frame(old_rows))

    # When
    result = collect_pykrx_history(TICKER, LISTING_DATE, adjusted=False, output_dir=tmp_path)

    # Then
    assert result.excluded_recent_count == 0
    assert result.row_count == len(old_rows)


@freeze_time(FROZEN_TODAY)
def test_adjusted_result_may_start_later_than_requested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 수정주가가 요청 시작일보다 늦게 시작하는 것이 **정상 경로**임을 고정한다.

    KRX 는 수정주가를 조회 시점 기준 최근 3,000거래일만 준다. 상장일을 넣어도 그보다
    늦게 시작하며, 이를 오류로 처리하면 수정주가를 아예 받을 수 없게 된다.

    Given: 상장일보다 한참 늦게 시작하는 응답
    When: 상장일을 시작일로 넣어 수정주가를 수집한다
    Then: 예외 없이 저장되고 시작일은 응답이 준 날짜다
    """
    # Given
    rows = [("2026-05-04", 30_000), ("2026-05-06", 30_500)]
    _stub_pykrx(monkeypatch, _market_frame(rows))

    # When
    result = collect_pykrx_history(TICKER, LISTING_DATE, adjusted=True, output_dir=tmp_path)

    # Then
    assert result.start_date == date(2026, 5, 4)


@freeze_time(FROZEN_TODAY)
def test_saved_file_is_readable_by_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, int]]
) -> None:
    """
    목적: 수집기가 남긴 파일을 로더가 그대로 읽을 수 있음을 고정한다 (계층 간 계약).

    수집과 로딩이 서로 다른 스키마를 전제하면 "받아는 놨는데 읽을 수 없는" 파일이 생긴다.

    Given: 수집으로 저장된 파일
    When: 로더로 읽는다
    Then: 같은 행 수가 예외 없이 반환된다
    """
    # Given
    _stub_pykrx(monkeypatch, _etf_frame(old_rows))
    result = collect_pykrx_history(TICKER, LISTING_DATE, adjusted=False, output_dir=tmp_path)

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
    _stub_pykrx(monkeypatch, _etf_frame([]))

    # When / Then
    with pytest.raises(ValueError, match="비어"):
        collect_pykrx_history(TICKER, LISTING_DATE, adjusted=False, output_dir=tmp_path)


@freeze_time(FROZEN_TODAY)
def test_all_rows_excluded_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 최근 제외로 데이터가 전부 사라진 경우를 고정한다 (경계 조건).

    Given: 당일에만 데이터가 있는 응답
    When: 수집한다
    Then: ValueError 가 발생한다
    """
    # Given
    _stub_pykrx(monkeypatch, _etf_frame([(FROZEN_TODAY, 30_000)]))

    # When / Then
    with pytest.raises(ValueError, match="제외 후"):
        collect_pykrx_history(TICKER, LISTING_DATE, adjusted=False, output_dir=tmp_path)


@freeze_time(FROZEN_TODAY)
def test_invalid_data_is_not_saved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 검증을 통과한 데이터만 저장됨을 고정한다.

    예외만 던지고 파일을 남기면 반쪽짜리 원자료가 남는다.

    Given: 전일 대비 두 배가 되는 응답
    When: 수집한다
    Then: ValueError 가 발생하고 파일이 만들어지지 않는다
    """
    # Given
    _stub_pykrx(monkeypatch, _etf_frame([(OLD_DATES[0], 30_000), (OLD_DATES[1], 60_000)]))

    # When / Then
    with pytest.raises(ValueError, match="급등락"):
        collect_pykrx_history(TICKER, LISTING_DATE, adjusted=False, output_dir=tmp_path)

    assert not (tmp_path / f"{TICKER}_max.csv").exists()


@freeze_time(FROZEN_TODAY)
def test_missing_schema_column_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 반환 컬럼이 바뀐 경우를 즉시 드러냄을 고정한다.

    pykrx 는 KRX 웹을 감싼 라이브러리라 반환 컬럼이 조용히 바뀔 수 있다.

    Given: 거래량 컬럼이 빠진 응답
    When: 수집한다
    Then: ValueError 가 발생하고 메시지에 누락 컬럼이 담긴다
    """
    # Given
    frame = _etf_frame([(OLD_DATES[0], 30_000)]).drop(columns=["거래량"])
    _stub_pykrx(monkeypatch, frame)

    # When / Then
    with pytest.raises(ValueError, match="누락"):
        collect_pykrx_history(TICKER, LISTING_DATE, adjusted=False, output_dir=tmp_path)


@freeze_time(FROZEN_TODAY)
def test_blank_ticker_raises(tmp_path: Path) -> None:
    """
    목적: 잘못된 입력을 조회 전에 막음을 고정한다.

    Given: 공백뿐인 티커
    When: 수집한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="종목"):
        collect_pykrx_history("   ", LISTING_DATE, adjusted=False, output_dir=tmp_path)


@freeze_time(FROZEN_TODAY)
def test_invalid_start_date_raises(tmp_path: Path) -> None:
    """
    목적: 시작일 형식을 조회 전에 검증함을 고정한다.

    pykrx 는 `YYYYMMDD` 만 받는다. 형식이 틀리면 KRX 에 요청을 보낸 뒤에야 실패한다.

    Given: 하이픈이 섞인 시작일
    When: 수집한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="시작일"):
        collect_pykrx_history(TICKER, "2002-10-14", adjusted=False, output_dir=tmp_path)


def test_credentials_are_loaded_before_pykrx_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 자격증명 로딩이 pykrx import 보다 먼저임을 고정한다.

    **`import pykrx` 자체가 로그인을 시도한다.** 순서가 뒤집히면 자격증명이 없는 상태로
    로그인이 시도되어 모든 조회가 실패한다. import 를 함수 안에 두는 것이 이 순서를 지키는
    유일한 방법이므로, 누군가 최상단으로 옮기면 이 테스트가 깨져야 한다.

    Given: 호출 순서를 기록하는 자격증명 로더와 가짜 pykrx 모듈
    When: pykrx 를 가져온다
    Then: 자격증명 로딩이 먼저 일어난다
    """

    # Given
    calls: list[str] = []
    stub_stock = SimpleNamespace()

    class _OrderRecordingModule(ModuleType):
        """`stock` 속성 접근 시점을 기록하는 가짜 pykrx 모듈."""

        @property
        def stock(self) -> object:
            calls.append("import")
            return stub_stock

    monkeypatch.setattr(pykrx_collector, "load_krx_credentials", lambda: calls.append("credentials"))
    monkeypatch.setitem(sys.modules, "pykrx", _OrderRecordingModule("pykrx"))

    # When
    result = pykrx_collector._import_pykrx_stock()

    # Then
    assert calls == ["credentials", "import"]
    assert result is stub_stock


@freeze_time(FROZEN_TODAY)
def test_price_columns_are_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old_rows: list[tuple[str, int]]
) -> None:
    """
    목적: 한글 컬럼이 뒤바뀌어 매핑되지 않음을 고정한다.

    시가와 종가가 뒤집혀도 값이 그럴듯해 보여 눈으로는 발견되지 않는다.

    Given: 고가만 종가보다 높은 응답
    When: 수집한다
    Then: 각 컬럼이 제자리에 저장된다
    """
    # Given
    frame = _etf_frame(old_rows)
    frame["고가"] = frame["종가"] + 500
    _stub_pykrx(monkeypatch, frame)

    # When
    result = collect_pykrx_history(TICKER, LISTING_DATE, adjusted=False, output_dir=tmp_path)

    # Then
    saved = pd.read_csv(result.path)
    assert saved[COL_HIGH].tolist() == [close + 500 for _, close in old_rows]
    assert saved[COL_CLOSE].tolist() == [close for _, close in old_rows]
    assert saved[COL_OPEN].tolist() == saved[COL_LOW].tolist()
    assert saved[COL_VOLUME].tolist() == [1_000] * len(old_rows)
