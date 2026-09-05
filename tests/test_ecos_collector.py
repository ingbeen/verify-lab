"""ECOS 수집기의 응답 해석·실패 정책·비밀값 보호를 고정한다.

외부 서버를 부르지 않는다. ECOS 응답은 전부 모의로 만들며, 이 테스트가 지키는 것은 셋이다.

1. **잘린 응답을 조용히 넘기지 않는다** — 잘린 시계열은 "그 날짜부터 데이터가 없다"로 읽힌다
2. **결측을 메우지 않고 제외하되 건수를 돌려준다** — 조용히 사라진 표본은 나중에 오해된다
3. **인증키가 예외 메시지로 새지 않는다** — ECOS 는 키를 URL 경로에 넣는다
"""

import io
import json
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from verify_lab.common_constants import COL_DATE, COL_VALUE
from verify_lab.data import ecos_collector
from verify_lab.data.ecos_collector import (
    ECOS_SERIES,
    SERVICE_SEARCH,
    EcosSeries,
    collect_ecos_series,
    fetch_rows,
    fetch_series,
    find_series,
    request_ecos,
)

API_KEY = "secret-key-value"

SERIES = EcosSeries(
    key="test",
    label="테스트 시계열",
    stat_code="731Y001",
    item_code="0000001",
    cycle="D",
    file_name="TEST.csv",
    decimals=2,
    unit="원",
)


def _row(time: str, value: str) -> dict[str, Any]:
    """조회 응답 한 행을 만든다."""
    return {"TIME": time, "DATA_VALUE": value, "UNIT_NAME": "원"}


def _install_response(monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]) -> list[str]:
    """`urlopen` 을 모의 응답으로 바꾸고, 요청된 URL 목록을 돌려준다."""
    requested: list[str] = []

    class _FakeResponse(io.BytesIO):
        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            self.close()

    def fake_urlopen(url: str, timeout: float | None = None) -> _FakeResponse:
        requested.append(url)
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return requested


def _search_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """조회 서비스의 정상 응답을 만든다."""
    return {SERVICE_SEARCH: {"list_total_count": len(rows), "row": rows}}


def test_request_puts_api_key_in_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 인증키가 URL 경로에 들어감을 고정한다.

    ECOS 는 쿼리스트링이 아니라 경로에 키를 받는다. 이 사실이 마스킹의 존재 이유다.

    Given: 정상 응답을 주는 서버
    When: 요청한다
    Then: 요청 URL 에 인증키가 들어 있다
    """
    # Given
    requested = _install_response(monkeypatch, _search_payload([]))

    # When
    request_ecos([SERVICE_SEARCH, "1", "10"], API_KEY)

    # Then
    assert API_KEY in requested[0]


def test_ecos_error_response_raises_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: ECOS 오류 코드를 예외로 올리되 인증키를 담지 않음을 고정한다.

    Given: RESULT 오류를 주는 서버
    When: 요청한다
    Then: ValueError 가 발생하고 메시지에 코드는 있으나 인증키는 없다
    """
    # Given
    _install_response(monkeypatch, {"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}})

    # When / Then
    with pytest.raises(ValueError) as error:
        request_ecos([SERVICE_SEARCH, "1", "10"], API_KEY)

    assert "INFO-200" in str(error.value)
    assert API_KEY not in str(error.value)


def test_http_error_message_hides_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: HTTP 오류 예외에 인증키가 섞이지 않음을 고정한다.

    `HTTPError` 의 문자열에는 요청 URL 이 담긴다. 그대로 올리면 키가 예외로 샌다.

    Given: HTTP 500 을 주는 서버
    When: 요청한다
    Then: ValueError 가 발생하고 메시지에 인증키가 없다
    """

    # Given
    def fake_urlopen(url: str, timeout: float | None = None) -> None:
        raise urllib.error.HTTPError(url, 500, "Internal Server Error", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    # When / Then
    with pytest.raises(ValueError) as error:
        request_ecos([SERVICE_SEARCH, "1", "10"], API_KEY)

    assert API_KEY not in str(error.value)
    assert "500" in str(error.value)


def test_truncated_response_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 전체 건수와 받은 행 수가 어긋나면 실패함을 고정한다.

    잘린 응답을 통과시키면 "그 날짜부터 데이터가 없다"로 읽히고,
    측정 결과에는 아무 흔적도 남지 않는다.

    Given: 전체 5건이라 알리면서 2건만 주는 응답
    When: 행을 받는다
    Then: ValueError 가 발생한다
    """
    # Given
    _install_response(
        monkeypatch, {SERVICE_SEARCH: {"list_total_count": 5, "row": [_row("20260102", "1"), _row("20260105", "2")]}}
    )

    # When / Then
    with pytest.raises(ValueError, match="잘렸습니다"):
        fetch_rows(SERVICE_SEARCH, ["1", "10"], API_KEY)


def test_missing_service_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 서비스 키가 없는 응답을 빈 결과로 처리하지 않음을 고정한다 (경계 조건).

    Given: 알 수 없는 최상위 키만 있는 응답
    When: 행을 받는다
    Then: ValueError 가 발생한다
    """
    # Given
    _install_response(monkeypatch, {"UnknownService": {}})

    # When / Then
    with pytest.raises(ValueError, match=SERVICE_SEARCH):
        fetch_rows(SERVICE_SEARCH, ["1", "10"], API_KEY)


def test_fetch_series_parses_date_and_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 조회 응답이 단일 값 스키마로 변환됨을 고정한다.

    Given: 이틀치 정상 응답
    When: 시계열을 받는다
    Then: 날짜와 값 컬럼만 남고 값이 숫자로 해석된다
    """
    # Given
    _install_response(monkeypatch, _search_payload([_row("19980103", "1695.8"), _row("19980105", "1700")]))

    # When
    frame, excluded = fetch_series(SERIES, date(1998, 1, 1), date(1998, 1, 31), API_KEY)

    # Then
    assert list(frame.columns) == [COL_DATE, COL_VALUE]
    assert frame[COL_DATE].tolist() == [date(1998, 1, 3), date(1998, 1, 5)]
    assert frame[COL_VALUE].tolist() == pytest.approx([1695.8, 1700.0], abs=1e-12)
    assert excluded == 0


def test_fetch_series_excludes_blank_values_and_counts_them(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 값이 빈 행을 메우지 않고 제외하되 건수를 돌려줌을 고정한다 (보간 금지·표본 보존).

    Given: 값이 빈 행이 섞인 응답
    When: 시계열을 받는다
    Then: 그 행이 빠지고 제외 건수가 함께 반환된다
    """
    # Given
    _install_response(
        monkeypatch, _search_payload([_row("20260102", "1380.5"), _row("20260105", ""), _row("20260106", "1379")])
    )

    # When
    frame, excluded = fetch_series(SERIES, date(2026, 1, 1), date(2026, 1, 31), API_KEY)

    # Then
    assert len(frame) == 2
    assert excluded == 1


def test_fetch_series_rejects_reversed_range() -> None:
    """
    목적: 뒤집힌 조회 구간을 즉시 거부함을 고정한다 (경계 조건).

    Given: 시작일이 종료일보다 뒤인 구간
    When: 시계열을 받는다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="뒤집혔습니다"):
        fetch_series(SERIES, date(2026, 2, 1), date(2026, 1, 1), API_KEY)


def test_fetch_series_rejects_all_blank_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 값이 하나도 없는 응답을 빈 파일로 저장하지 않음을 고정한다 (경계 조건).

    Given: 모든 값이 빈 응답
    When: 시계열을 받는다
    Then: ValueError 가 발생한다
    """
    # Given
    _install_response(monkeypatch, _search_payload([_row("20260102", ""), _row("20260105", "")]))

    # When / Then
    with pytest.raises(ValueError, match="값이 있는 행"):
        fetch_series(SERIES, date(2026, 1, 1), date(2026, 1, 31), API_KEY)


def test_collect_saves_sorted_and_rounded_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    목적: 저장 파일이 날짜 오름차순이고 지정 자릿수로 반올림됨을 고정한다.

    Given: 날짜가 뒤섞이고 자릿수가 깊은 응답
    When: 수집한다
    Then: 정렬·반올림된 파일이 저장되고 결과 요약이 실제 파일과 일치한다
    """
    # Given
    _install_response(monkeypatch, _search_payload([_row("20260106", "1379.987"), _row("20260102", "1380.512")]))

    # When
    result = collect_ecos_series(SERIES, date(2026, 1, 1), date(2026, 1, 31), api_key=API_KEY, output_dir=tmp_path)

    # Then
    saved = (tmp_path / SERIES.file_name).read_text(encoding="utf-8").splitlines()
    assert saved[0] == f"{COL_DATE},{COL_VALUE}"
    assert saved[1] == "2026-01-02,1380.51"
    assert saved[2] == "2026-01-06,1379.99"
    assert result.row_count == 2
    assert result.start_date == date(2026, 1, 2)
    assert result.end_date == date(2026, 1, 6)


def test_collect_does_not_read_env_when_key_given(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    목적: 인증키를 넘기면 `.env` 를 읽지 않음을 고정한다.

    테스트가 사용자의 실제 자격증명 파일에 의존하면 환경에 따라 결과가 갈린다.

    Given: `.env` 읽기가 실패하도록 만든 상태
    When: 인증키를 직접 넘겨 수집한다
    Then: 예외 없이 저장된다
    """

    # Given
    def explode() -> str:
        raise AssertionError("인증키를 넘겼는데 .env 를 읽었습니다")

    monkeypatch.setattr(ecos_collector, "load_ecos_api_key", explode)
    _install_response(monkeypatch, _search_payload([_row("20260102", "1380.5")]))

    # When
    result = collect_ecos_series(SERIES, date(2026, 1, 1), date(2026, 1, 31), api_key=API_KEY, output_dir=tmp_path)

    # Then
    assert result.row_count == 1


def test_find_series_rejects_unknown_key() -> None:
    """
    목적: 모르는 시계열 이름을 조용히 넘기지 않음을 고정한다.

    Given: 목록에 없는 이름
    When: 시계열을 찾는다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="알 수 없는 시계열"):
        find_series("없는이름")


def test_registered_series_keys_are_unique() -> None:
    """
    목적: 수집 대상 이름과 저장 파일명이 겹치지 않음을 고정한다.

    겹치면 뒤에 수집한 시계열이 앞의 파일을 덮어쓴다.

    Given: 등록된 수집 대상 목록
    When: 이름과 파일명을 센다
    Then: 중복이 없다
    """
    assert len({s.key for s in ECOS_SERIES}) == len(ECOS_SERIES)
    assert len({s.file_name for s in ECOS_SERIES}) == len(ECOS_SERIES)


def test_missing_total_count_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: **잘림 검사가 스스로 꺼지지 않음**을 고정한다 (경계 조건).

    전에는 전체 건수 키가 없으면 기본값을 `len(rows)` 로 두었다. 그러면 바로 다음 줄의
    `len(rows) != total_count` 대조가 **언제나 통과**해, 응답이 잘렸는지 확인하는 장치가
    스스로 꺼진다. 잘린 시계열은 "그 날짜부터 데이터가 없다"로 읽힌다.

    Given: 행은 있는데 전체 건수 키가 없는 응답
    When: 행을 받는다
    Then: ValueError 가 발생한다
    """
    # Given
    _install_response(monkeypatch, {SERVICE_SEARCH: {"row": [_row("20260102", "1")]}})

    # When / Then
    with pytest.raises(ValueError, match="전체 건수"):
        fetch_rows(SERVICE_SEARCH, ["1", "10"], API_KEY)


def test_missing_row_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 행 키가 없는 응답을 **빈 결과 0건**으로 처리하지 않음을 고정한다 (경계 조건).

    응답 스키마가 바뀌면 조용히 0건이 되는데, 그것은 "데이터가 없다"와 구별되지 않는다.

    Given: 전체 건수는 있는데 행 키가 없는 응답
    When: 행을 받는다
    Then: ValueError 가 발생한다
    """
    # Given
    _install_response(monkeypatch, {SERVICE_SEARCH: {"list_total_count": 3}})

    # When / Then
    with pytest.raises(ValueError, match="행"):
        fetch_rows(SERVICE_SEARCH, ["1", "10"], API_KEY)
