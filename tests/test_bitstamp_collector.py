"""Bitstamp 일봉 수집기의 응답 해석 · 페이지 순회 · 저장 정책을 고정한다.

외부 서버를 부르지 않는다. `urllib.request.urlopen` 을 요청 URL 의 `start` 값에 따라 다른 페이지를
돌려주는 모의로 바꾼다. 이 테스트가 지키는 것은 넷이다.

1. **첫 요청의 시작 시각이 첫 거래일(2011-08-18 00:00 UTC)이다** — 그보다 앞이면 서버가 에러 없이
   빈 응답을 준다 (`docs/검증/반감기_사이클/사전조사.md` §4.8, 2026-09-29 실측)
2. **페이지를 빠짐없이 잇고, 제자리를 도는 응답은 막는다**
3. **UTC 로 끝나지 않은 봉은 저장하지 않는다** — 경계는 KST 09:00
4. **이상치 검사를 통과한 뒤에만 파일을 쓴다** — 비트코인의 급변동 임계값으로
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from freezegun import freeze_time

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_VOLUME, REQUIRED_COLUMNS
from verify_lab.data import bitstamp_collector
from verify_lab.data.bitstamp_collector import (
    BITSTAMP_TICKER,
    FIRST_TRADE_TIMESTAMP,
    collect_bitstamp_history,
    fetch_ohlc_history,
    parse_ohlc_rows,
)

DAY = 86_400

# 2011-08-18 00:00 UTC
FIRST = FIRST_TRADE_TIMESTAMP


def _row(timestamp: int, close: float, volume: float = 1.5) -> dict[str, str]:
    """Bitstamp 가 주는 모양의 하루치 행. 값이 전부 문자열로 온다."""
    return {
        "timestamp": str(timestamp),
        "open": f"{close:.2f}",
        "high": f"{close:.2f}",
        "low": f"{close:.2f}",
        "close": f"{close:.2f}",
        "volume": f"{volume:.8f}",
    }


def _install_pages(
    monkeypatch: pytest.MonkeyPatch,
    pages: dict[int, list[dict[str, str]]],
    on_request: Callable[[], None] | None = None,
) -> list[str]:
    """요청 URL 의 `start` 로 페이지를 골라 주는 모의 서버를 설치하고, 받은 URL 목록을 돌려준다.

    목록에 없는 `start` 는 빈 페이지를 준다. **실제 서버는 마지막 봉 뒤를 물으면 빈 목록이 아니라 최근 봉을 다시
    준다** — 그 동작은 `test_latest_bar_returned_for_a_future_start_ends_the_history` 가 따로 고정한다. 순회는
    두 응답 모두에서 「새 봉 없음」으로 멈춰야 하므로, 여기서는 단순한 쪽(빈 페이지)을 기본으로 둔다.
    `on_request` 는 요청마다 불린다 — 조회 도중 시계가 흐르는 상황을 만들 때 쓴다.
    """
    requested: list[str] = []

    class _FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return self._body

    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None) -> _FakeResponse:
        url = request.full_url
        requested.append(url)
        if on_request is not None:
            on_request()
        start = int(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["start"][0])
        payload = {"data": {"pair": "BTC/USD", "ohlc": pages.get(start, [])}}
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return requested


def _query(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in urllib.parse.parse_qs(urllib.parse.urlparse(url).query).items()}


def test_first_request_starts_at_the_first_trade_day(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 첫 요청이 첫 거래일 00:00 UTC 부터 하루 봉을 최대 개수로 묻는지 고정한다.

    Given: 한 행짜리 첫 페이지
    When: 전 기간을 받는다
    Then: 첫 URL 의 start · step · limit 이 약속한 값이다
    """
    # Given
    requested = _install_pages(monkeypatch, {FIRST: [_row(FIRST, 10.9)]})

    # When
    fetch_ohlc_history()

    # Then
    query = _query(requested[0])
    assert query["start"] == str(1_313_625_600)
    assert query["step"] == str(DAY)
    assert query["limit"] == str(bitstamp_collector.PAGE_LIMIT)


def test_rows_are_parsed_into_the_market_schema() -> None:
    """
    목적: 문자열로 오는 응답을 시세 스키마(날짜 + OHLCV 실수)로 바꿈을 고정한다.

    Given: 2011-08-18 00:00 UTC 한 행
    When: 해석한다
    Then: 컬럼이 시세 스키마 순서이고 날짜가 UTC 날짜다
    """
    frame = parse_ohlc_rows([_row(FIRST, 10.9, volume=0.48990826)])

    assert list(frame.columns) == REQUIRED_COLUMNS
    assert frame[COL_DATE].tolist() == [date(2011, 8, 18)]
    assert frame[COL_CLOSE].tolist() == pytest.approx([10.9], abs=1e-12)
    assert frame[COL_VOLUME].tolist() == pytest.approx([0.48990826], abs=1e-12)


def test_short_page_does_not_end_the_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 덜 찬 페이지에서 멈추지 않고, 새 봉이 없는 응답이 올 때까지 이어 묻는지 고정한다.

    덜 찬 페이지에서 멈추면 서버가 한 번에 주는 개수를 줄이거나 부하로 덜 줄 때 뒤가 잘린 채 끝난다.

    Given: 첫 페이지 2행 · 둘째 페이지 1행(덜 참) · 그 뒤는 새 봉 없음(빈 페이지)
    When: 전 기간을 받는다
    Then: 3행이 이어지고, 요청은 셋이며 둘째 · 셋째 요청의 start 가 앞 페이지 마지막 봉 + 하루다
    """
    # Given
    requested = _install_pages(
        monkeypatch,
        {
            FIRST: [_row(FIRST, 10.0), _row(FIRST + DAY, 11.0)],
            FIRST + 2 * DAY: [_row(FIRST + 2 * DAY, 12.0)],
        },
    )

    # When
    frame = fetch_ohlc_history()

    # Then
    assert frame[COL_DATE].tolist() == [date(2011, 8, 18), date(2011, 8, 19), date(2011, 8, 20)]
    assert [_query(url)["start"] for url in requested] == [str(FIRST), str(FIRST + 2 * DAY), str(FIRST + 3 * DAY)]


def test_full_last_page_followed_by_empty_page_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 마지막 페이지가 꼭 한도만큼 찼을 때 다음 응답에 새 봉이 없으면 예외 없이 멈춤을 고정한다 (경계 조건).

    Given: 한 페이지 2행 한도 · 첫 페이지 2행 · 그 뒤는 새 봉 없음(빈 페이지)
    When: 전 기간을 받는다
    Then: 2행을 돌려준다
    """
    # Given
    monkeypatch.setattr(bitstamp_collector, "PAGE_LIMIT", 2)
    _install_pages(monkeypatch, {FIRST: [_row(FIRST, 10.0), _row(FIRST + DAY, 11.0)]})

    # When
    frame = fetch_ohlc_history()

    # Then
    assert len(frame) == 2


def test_empty_first_page_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 첫 페이지가 비면 「데이터 없음」으로 넘기지 않고 예외를 냄을 고정한다.

    시작 시각이 첫 거래일보다 앞이면 서버가 **에러 없이** 빈 응답을 준다(실측). 그대로 두면 빈 파일이 된다.

    Given: 빈 첫 페이지
    When: 전 기간을 받는다
    Then: ValueError 가 발생한다
    """
    _install_pages(monkeypatch, {})

    with pytest.raises(ValueError, match="빈 응답"):
        fetch_ohlc_history()


def test_latest_bar_returned_for_a_future_start_ends_the_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 시작이 마지막 봉보다 뒤일 때 서버가 가장 최근 봉을 다시 줘도, 그것을 새 봉으로 받지 않고 끝남을 고정한다.

    실측(2026-09-29): 시작이 미래면 Bitstamp 는 빈 목록이 아니라 **진행 중인 최근 봉을 다시** 준다.
    「빈 페이지가 올 때까지」 도는 순회는 이때 끝나지 않는다(설계 문서 결정 ⑪ 탈락안 ③).

    Given: 첫 페이지 2행 · 그다음 시작(마지막 봉 + 하루)을 물으면 마지막 봉을 다시 주는 서버
    When: 전 기간을 받는다
    Then: 2행만 남고(중복 없음) 요청은 둘이다
    """
    # Given
    latest = _row(FIRST + DAY, 11.0)
    requested = _install_pages(monkeypatch, {FIRST: [_row(FIRST, 10.0), latest], FIRST + 2 * DAY: [latest]})

    # When
    frame = fetch_ohlc_history()

    # Then
    assert frame[COL_DATE].tolist() == [date(2011, 8, 18), date(2011, 8, 19)]
    assert len(requested) == 2


def test_timestamp_off_utc_midnight_is_rejected() -> None:
    """
    목적: UTC 자정이 아닌 봉 시각을 하루 봉으로 받아들이지 않음을 고정한다.

    봉의 경계가 바뀌면 날짜가 가리키는 하루가 달라지고, 크로스체크 상대(UTC 하루)와 조용히 어긋난다.

    Given: 자정에서 1시간 벗어난 시각
    When: 해석한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="자정"):
        parse_ohlc_rows([_row(FIRST + 3_600, 10.0)])


def test_duplicate_timestamps_keep_one_row() -> None:
    """
    목적: 같은 봉이 두 번 와도 한 행만 남음을 고정한다.

    Given: 같은 시각의 행 두 개
    When: 해석한다
    Then: 한 행이다
    """
    frame = parse_ohlc_rows([_row(FIRST, 10.0), _row(FIRST, 10.0)])

    assert len(frame) == 1


def test_http_error_is_translated(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: HTTP 오류를 프로젝트 예외로 바꿔 올림을 고정한다.

    Given: HTTP 429 를 주는 서버
    When: 전 기간을 받는다
    Then: ValueError 가 발생하고 메시지에 상태 코드가 담긴다
    """

    # Given
    def fake_urlopen(request: object, timeout: float | None = None) -> None:
        raise urllib.error.HTTPError("https://example.invalid", 429, "Too Many Requests", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    # When / Then
    with pytest.raises(ValueError, match="429"):
        fetch_ohlc_history()


def test_malformed_response_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 모양이 다른 응답을 빈 결과로 넘기지 않음을 고정한다.

    Given: `data.ohlc` 가 없는 JSON
    When: 전 기간을 받는다
    Then: ValueError 가 발생한다
    """

    # Given
    class _FakeResponse:
        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"code": "API0001", "errors": []}'

    def fake_urlopen(request: object, timeout: float | None = None) -> _FakeResponse:
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    # When / Then
    with pytest.raises(ValueError, match="응답"):
        fetch_ohlc_history()


@freeze_time("2011-08-21 00:30:00")
def test_collect_saves_finished_days_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    목적: UTC 로 끝난 봉만 시세 파일에 저장하고 제외 건수를 돌려줌을 고정한다.

    Given: 08-18 ~ 08-21 네 봉, 현재 UTC 2011-08-21 00:30 (= KST 09:30) — 08-21 봉은 진행 중
    When: 수집한다
    Then: 08-18 ~ 08-20 세 행이 `BTCUSD_max.csv` 에 저장되고 제외 건수는 1 이다
    """
    # Given
    _install_pages(monkeypatch, {FIRST: [_row(FIRST + i * DAY, 10.0 + i) for i in range(4)]})

    # When
    result = collect_bitstamp_history(output_dir=tmp_path)

    # Then
    saved = pd.read_csv(tmp_path / f"{BITSTAMP_TICKER}_max.csv")
    assert list(saved.columns) == REQUIRED_COLUMNS
    assert saved[COL_DATE].tolist() == ["2011-08-18", "2011-08-19", "2011-08-20"]
    assert result.excluded_recent_count == 1
    assert result.row_count == 3
    assert result.start_date == date(2011, 8, 18)
    assert result.end_date == date(2011, 8, 20)
    assert result.missing_day_count == 0


@freeze_time("2011-08-22 00:30:00")
def test_collect_rejects_missing_day_and_writes_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    목적: 사이에 빠진 날이 있는 이력을 메우지도 저장하지도 않음을 고정한다 (2026-09-29 사용자 결정).

    비트코인은 휴장이 없어 빠진 날은 소스의 결함이다. 양 끝만 보면 중간이 빠진 이력이 전체 파일을 덮는다.

    Given: 08-18 · 08-19 · 08-21 (08-20 이 빠짐), 끝난 마지막 날 08-21
    When: 수집한다
    Then: ValueError 가 발생하고 저장 파일이 없다
    """
    # Given
    _install_pages(monkeypatch, {FIRST: [_row(FIRST, 10.0), _row(FIRST + DAY, 11.0), _row(FIRST + 3 * DAY, 12.0)]})

    # When / Then
    with pytest.raises(ValueError, match="빠진 날"):
        collect_bitstamp_history(output_dir=tmp_path)
    assert not (tmp_path / f"{BITSTAMP_TICKER}_max.csv").exists()


@freeze_time("2011-08-20 00:30:00")
def test_collect_accepts_bitcoin_scale_daily_move(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    목적: 비트코인에서 실제로 있었던 크기의 하루 변동(+56.1%)을 데이터 오류로 막지 않음을 고정한다.

    공용 임계값(50%)이면 2011-10-28 이 막혀 **전 기간을 저장할 수 없다** — 원시 시세는 전 기간을
    남긴다는 계약(`src/verify_lab/CLAUDE.md` 「원시 시세 저장 규칙」)과 부딪힌다.

    Given: 10.00 → 15.61 (+56.1%)
    When: 수집한다
    Then: 예외 없이 두 행이 저장된다
    """
    # Given
    _install_pages(monkeypatch, {FIRST: [_row(FIRST, 10.0), _row(FIRST + DAY, 15.61)]})

    # When
    result = collect_bitstamp_history(output_dir=tmp_path)

    # Then
    assert result.row_count == 2


@freeze_time("2011-08-20 00:30:00")
def test_collect_rejects_data_error_and_writes_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    목적: 자릿수 오류 크기의 변동(×10)은 여전히 막고, 그때 파일을 쓰지 않음을 고정한다.

    Given: 10.00 → 100.00 (+900%)
    When: 수집한다
    Then: ValueError 가 발생하고 저장 파일이 없다
    """
    # Given
    _install_pages(monkeypatch, {FIRST: [_row(FIRST, 10.0), _row(FIRST + DAY, 100.0)]})

    # When / Then
    with pytest.raises(ValueError, match="급등락"):
        collect_bitstamp_history(output_dir=tmp_path)
    assert not (tmp_path / f"{BITSTAMP_TICKER}_max.csv").exists()


@freeze_time("2011-08-22 00:30:00")
def test_collect_rejects_history_that_starts_late(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    목적: 첫 거래일에서 시작하지 않는 이력을 저장하지 않음을 고정한다.

    빠진 날 수는 첫 날과 마지막 날 **사이**만 보므로 앞이 잘린 것을 잡지 못한다.

    Given: 첫 요청에 08-19 부터의 봉이 온다 (08-18 이 없다)
    When: 수집한다
    Then: ValueError 가 발생하고 저장 파일이 없다
    """
    # Given
    _install_pages(monkeypatch, {FIRST: [_row(FIRST + i * DAY, 10.0 + i) for i in range(1, 4)]})

    # When / Then
    with pytest.raises(ValueError, match="시작"):
        collect_bitstamp_history(output_dir=tmp_path)
    assert not (tmp_path / f"{BITSTAMP_TICKER}_max.csv").exists()


@freeze_time("2011-08-25 00:30:00")
def test_collect_rejects_history_that_ends_early(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    목적: 끝난 마지막 날에 닿지 않는 이력을 저장하지 않음을 고정한다 (잘린 이력이 전체 파일을 덮지 않게).

    Given: 08-18 ~ 08-20 세 봉, 현재 UTC 08-25 00:30 — 끝난 마지막 날은 08-24
    When: 수집한다
    Then: ValueError 가 발생하고 저장 파일이 없다
    """
    # Given
    _install_pages(monkeypatch, {FIRST: [_row(FIRST + i * DAY, 10.0 + i) for i in range(3)]})

    # When / Then
    with pytest.raises(ValueError, match="끝"):
        collect_bitstamp_history(output_dir=tmp_path)
    assert not (tmp_path / f"{BITSTAMP_TICKER}_max.csv").exists()


def test_clock_is_read_before_the_fetch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    목적: 「끝나지 않은 날」의 기준 시각을 조회 «전»에 잼을 고정한다.

    조회 뒤에 재면 KST 09:00 을 걸쳐 돈 실행에서, 조회할 때 진행 중이던 봉이 끝난 봉으로 저장된다.

    Given: KST 08:59:50 (UTC 08-20 23:59:50) 에 시작하고 조회 도중 UTC 08-21 00:00:05 로 넘어간다.
        서버는 진행 중이던 08-20 봉까지 준다
    When: 수집한다
    Then: 08-20 봉은 빠지고(제외 1) 08-19 까지 저장된다
    """
    with freeze_time("2011-08-20 23:59:50") as frozen:
        # Given
        _install_pages(
            monkeypatch,
            {FIRST: [_row(FIRST + i * DAY, 10.0 + i) for i in range(3)]},
            on_request=lambda: frozen.move_to("2011-08-21 00:00:05"),
        )

        # When
        result = collect_bitstamp_history(output_dir=tmp_path)

    # Then
    assert result.end_date == date(2011, 8, 19)
    assert result.excluded_recent_count == 1
