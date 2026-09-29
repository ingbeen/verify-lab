"""Coin Metrics 커뮤니티 API 수집기의 요청 · 페이지 순회 · 저장 정책을 고정한다.

외부 서버를 부르지 않는다. `urllib.request.urlopen` 을 요청 URL 에 따라 다른 페이지를 돌려주는
모의로 바꾼다. 이 테스트가 지키는 것은 셋이다.

1. **첫 요청이 `paging_from=start` 를 명시한다** — 주지 않으면 서버가 **최신 행부터** 준다
   (`docs/검증/반감기_사이클/사전조사.md` §4.8, 2026-09-29 실측). 그 상태로 한 페이지만 받으면
   예외 없이 최근 구간만 저장된다
2. **`next_page_url` 을 끝까지 따라가고, 제자리를 도는 응답은 막는다**
3. **UTC 로 끝나지 않은 날을 저장하지 않고, 빠진 날을 메우지 않고 센다**
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from freezegun import freeze_time

from verify_lab.common_constants import COL_DATE, COL_VALUE
from verify_lab.data.coinmetrics_collector import (
    COINMETRICS_SERIES,
    CoinMetricsSeries,
    collect_coinmetrics_series,
    fetch_metric_rows,
    first_page_url,
    parse_metric_rows,
)

SERIES = CoinMetricsSeries(
    key="test",
    label="테스트 기준가",
    asset="btc",
    metric="PriceUSD",
    file_name="TEST_PriceUSD.csv",
    decimals=4,
    unit="달러",
    first_date=date(2010, 7, 18),
)

NEXT_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?next_page_token=abc"


def _row(day: str, value: str | None) -> dict[str, Any]:
    """Coin Metrics 가 주는 모양의 하루치 행. 값이 문자열로 오고, 없으면 키 자체가 없다."""
    row: dict[str, Any] = {"asset": "btc", "time": f"{day}T00:00:00.000000000Z"}
    if value is not None:
        row["PriceUSD"] = value
    return row


def _install_pages(
    monkeypatch: pytest.MonkeyPatch,
    pages: dict[str, dict[str, Any]],
    on_request: Callable[[], None] | None = None,
) -> list[str]:
    """URL 로 응답을 골라 주는 모의 서버를 설치하고, 받은 URL 목록을 돌려준다.

    첫 요청처럼 목록에 없는 URL 은 `"first"` 키의 응답을 준다.
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
        payload = pages.get(url, pages["first"])
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return requested


def test_first_page_url_asks_oldest_first() -> None:
    """
    목적: 첫 요청이 오래된 행부터 · 한 번에 최대 개수로 · 일 단위로 묻는지 고정한다.

    Given: 수집 대상 하나
    When: 첫 요청 URL 을 만든다
    Then: `paging_from=start` · `page_size=10000` · `frequency=1d` · 자산 · 지표가 들어 있다
    """
    query = urllib.parse.parse_qs(urllib.parse.urlparse(first_page_url(SERIES)).query)

    assert query["paging_from"] == ["start"]
    assert query["page_size"] == ["10000"]
    assert query["frequency"] == ["1d"]
    assert query["assets"] == ["btc"]
    assert query["metrics"] == ["PriceUSD"]


def test_pages_are_followed_until_no_next_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: `next_page_url` 이 있는 동안 따라가 모든 행을 모음을 고정한다.

    Given: 첫 페이지(2행 + 다음 URL) · 둘째 페이지(1행, 다음 없음)
    When: 행을 받는다
    Then: 3행이고 둘째 요청이 다음 URL 이다
    """
    # Given
    requested = _install_pages(
        monkeypatch,
        {
            "first": {"data": [_row("2010-07-18", "0.08584"), _row("2010-07-19", "0.0808")], "next_page_url": NEXT_URL},
            NEXT_URL: {"data": [_row("2010-07-20", "0.0747")]},
        },
    )

    # When
    rows = fetch_metric_rows(SERIES)

    # Then
    assert len(rows) == 3
    assert requested[1] == NEXT_URL


def test_next_url_that_repeats_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 다음 URL 이 방금 받은 URL 과 같으면 끝없이 돌지 않고 막음을 고정한다.

    Given: 다음 URL 이 자기 자신인 둘째 페이지
    When: 행을 받는다
    Then: ValueError 가 발생한다
    """
    # Given
    _install_pages(
        monkeypatch,
        {
            "first": {"data": [_row("2010-07-18", "0.08584")], "next_page_url": NEXT_URL},
            NEXT_URL: {"data": [_row("2010-07-19", "0.0808")], "next_page_url": NEXT_URL},
        },
    )

    # When / Then
    with pytest.raises(ValueError, match="나아가지"):
        fetch_metric_rows(SERIES)


def test_rows_are_parsed_into_the_series_schema() -> None:
    """
    목적: 문자열 값과 UTC 시각을 단일 값 스키마(날짜 + 실수)로 바꿈을 고정한다.

    Given: 2010-07-18 한 행
    When: 해석한다
    Then: 컬럼이 [Date, Value] 이고 날짜가 그 UTC 날짜다
    """
    frame = parse_metric_rows([_row("2010-07-18", "0.08584")], SERIES)

    assert list(frame.columns) == [COL_DATE, COL_VALUE]
    assert frame[COL_DATE].tolist() == [date(2010, 7, 18)]
    assert frame[COL_VALUE].tolist() == pytest.approx([0.08584], abs=1e-12)


def test_time_off_utc_midnight_is_rejected() -> None:
    """
    목적: UTC 자정이 아닌 시각을 하루 값으로 받아들이지 않음을 고정한다.

    날짜 기준이 바뀌면 값이 하루 밀린 채 저장되고, 크로스체크 상대(Bitstamp 의 UTC 하루)와 조용히 어긋난다.

    Given: 시각이 12:00Z 인 행
    When: 해석한다
    Then: ValueError 가 발생한다
    """
    row = {"asset": "btc", "time": "2010-07-18T12:00:00.000000000Z", "PriceUSD": "0.08584"}

    with pytest.raises(ValueError, match="자정"):
        parse_metric_rows([row], SERIES)


def test_empty_response_is_rejected() -> None:
    """
    목적: 행이 하나도 없는 응답을 빈 파일로 넘기지 않음을 고정한다 (경계 조건).

    Given: 빈 행 목록
    When: 해석한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="비어"):
        parse_metric_rows([], SERIES)


def test_http_error_is_translated(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: HTTP 오류를 프로젝트 예외로 바꿔 올림을 고정한다.

    Given: HTTP 429 를 주는 서버
    When: 행을 받는다
    Then: ValueError 가 발생하고 메시지에 상태 코드가 담긴다
    """

    # Given
    def fake_urlopen(request: object, timeout: float | None = None) -> None:
        raise urllib.error.HTTPError("https://example.invalid", 429, "Too Many Requests", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    # When / Then
    with pytest.raises(ValueError, match="429"):
        fetch_metric_rows(SERIES)


def test_malformed_response_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: `data` 가 없는 응답을 빈 결과로 넘기지 않음을 고정한다.

    Given: 오류 모양의 JSON
    When: 행을 받는다
    Then: ValueError 가 발생한다
    """
    _install_pages(monkeypatch, {"first": {"error": {"type": "bad_parameter"}}})

    with pytest.raises(ValueError, match="응답"):
        fetch_metric_rows(SERIES)


@freeze_time("2010-07-21 00:30:00")
def test_collect_saves_finished_days_rounded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    목적: UTC 로 끝난 날만 가격 자릿수로 반올림해 저장하고 제외 건수를 돌려줌을 고정한다.

    Given: 07-18 ~ 07-21 네 행, 현재 UTC 2010-07-21 00:30 — 07-21 은 진행 중
    When: 수집한다
    Then: 07-18 ~ 07-20 세 행이 소수 4자리로 저장되고 제외 건수는 1 이다
    """
    # Given
    _install_pages(
        monkeypatch,
        {
            "first": {
                "data": [
                    _row("2010-07-18", "0.08584"),
                    _row("2010-07-19", "0.0808"),
                    _row("2010-07-20", "0.0747357288135593"),
                    _row("2010-07-21", "0.079"),
                ]
            }
        },
    )

    # When
    result = collect_coinmetrics_series(SERIES, output_dir=tmp_path)

    # Then
    saved = pd.read_csv(tmp_path / SERIES.file_name)
    assert list(saved.columns) == [COL_DATE, COL_VALUE]
    assert saved[COL_DATE].tolist() == ["2010-07-18", "2010-07-19", "2010-07-20"]
    assert saved[COL_VALUE].tolist() == pytest.approx([0.0858, 0.0808, 0.0747], abs=1e-12)
    assert result.excluded_recent_count == 1
    assert result.row_count == 3
    assert result.missing_day_count == 0


@freeze_time("2010-07-21 00:30:00")
def test_collect_rejects_missing_day_and_writes_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    목적: 사이에 빠진 날이 있는 이력을 메우지도 저장하지도 않음을 고정한다 (2026-09-29 사용자 결정).

    Given: 07-18 · 07-20 (07-19 가 빠짐)
    When: 수집한다
    Then: ValueError 가 발생하고 저장 파일이 없다
    """
    # Given
    _install_pages(monkeypatch, {"first": {"data": [_row("2010-07-18", "0.08584"), _row("2010-07-20", "0.0747")]}})

    # When / Then
    with pytest.raises(ValueError, match="빠진 날"):
        collect_coinmetrics_series(SERIES, output_dir=tmp_path)
    assert not (tmp_path / SERIES.file_name).exists()


@freeze_time("2010-07-20 00:30:00")
def test_collect_rejects_row_without_value_and_writes_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    목적: 값이 빠진 행을 메우지 않고 예외로 드러내며, 그때 파일을 쓰지 않음을 고정한다.

    Given: 07-19 행에 지표 값이 없다
    When: 수집한다
    Then: ValueError 가 발생하고 저장 파일이 없다
    """
    # Given
    _install_pages(monkeypatch, {"first": {"data": [_row("2010-07-18", "0.08584"), _row("2010-07-19", None)]}})

    # When / Then
    with pytest.raises(ValueError, match="결측"):
        collect_coinmetrics_series(SERIES, output_dir=tmp_path)
    assert not (tmp_path / SERIES.file_name).exists()


def test_registered_series_keys_and_files_are_unique() -> None:
    """
    목적: 수집 대상 이름과 저장 파일명이 겹치지 않음을 고정한다.

    Given: 등록된 수집 대상 목록
    When: 이름과 파일명을 센다
    Then: 중복이 없다
    """
    assert len({s.key for s in COINMETRICS_SERIES}) == len(COINMETRICS_SERIES)
    assert len({s.file_name for s in COINMETRICS_SERIES}) == len(COINMETRICS_SERIES)


def test_registered_series_are_price_mvrv_and_market_cap() -> None:
    """
    목적: 반감기_사이클이 받는 세 지표의 이름 · 파일 · 자릿수 · 첫 날을 고정한다.

    **파일 이름은 `{자산}_{지표}.csv` 이고 지표 이름은 Coin Metrics 의 것 그대로다**(설계 결정 ⑨).
    MVRV 계열만 데이터로 받는다(결정 ⑧) — 실현 시가총액은 무료 목록에 없어 시가총액 ÷ MVRV 로 나온다.
    기대값은 손으로 적는다 — 프로덕션 상수에서 가져오면 상수를 바꿀 때 테스트가 함께 따라온다.

    Given: 등록된 수집 대상 목록
    When: 지표 이름으로 대상을 찾는다
    Then: 가격 · MVRV · 시가총액 셋이며 각각 약속한 파일 이름 · 자릿수 · 첫 날을 갖는다
    """
    # Given / When
    by_metric = {series.metric: series for series in COINMETRICS_SERIES}

    # Then
    assert set(by_metric) == {"PriceUSD", "CapMVRVCur", "CapMrktCurUSD"}
    expected = {
        "PriceUSD": ("BTC_PriceUSD.csv", 4),
        "CapMVRVCur": ("BTC_CapMVRVCur.csv", 4),
        "CapMrktCurUSD": ("BTC_CapMrktCurUSD.csv", 0),
    }
    for metric, (file_name, decimals) in expected.items():
        series = by_metric[metric]
        assert series.asset == "btc"
        assert series.file_name == file_name
        assert series.decimals == decimals
        assert series.first_date == date(2010, 7, 18)


@freeze_time("2010-07-21 00:30:00")
def test_collect_accepts_one_day_publication_lag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    목적: 끝난 마지막 날의 값이 아직 없어도 하루까지는 정상으로 받음을 고정한다 (경계 조건).

    Coin Metrics 는 날짜 d 의 값을 d+1 일 UTC 02:28 ~ 03:32 에 완성한다(실측) — KST 09:00 ~ 12:30 에
    돌리면 어제 값이 없다.

    Given: 07-18 · 07-19 두 행, 현재 UTC 07-21 00:30 — 끝난 마지막 날(07-20)의 값이 아직 없다
    When: 수집한다
    Then: 예외 없이 두 행이 저장된다
    """
    # Given
    _install_pages(monkeypatch, {"first": {"data": [_row("2010-07-18", "0.08584"), _row("2010-07-19", "0.0808")]}})

    # When
    result = collect_coinmetrics_series(SERIES, output_dir=tmp_path)

    # Then
    assert result.row_count == 2


@freeze_time("2010-07-22 00:30:00")
def test_collect_rejects_history_beyond_the_lag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    목적: 허용 지연(하루)보다 일찍 끝난 이력을 저장하지 않음을 고정한다 (잘린 이력이 전체 파일을 덮지 않게).

    Given: 07-18 · 07-19 두 행, 현재 UTC 07-22 00:30 — 끝난 마지막 날은 07-21, 허용 하한은 07-20
    When: 수집한다
    Then: ValueError 가 발생하고 저장 파일이 없다
    """
    # Given
    _install_pages(monkeypatch, {"first": {"data": [_row("2010-07-18", "0.08584"), _row("2010-07-19", "0.0808")]}})

    # When / Then
    with pytest.raises(ValueError, match="끝"):
        collect_coinmetrics_series(SERIES, output_dir=tmp_path)
    assert not (tmp_path / SERIES.file_name).exists()


@freeze_time("2010-07-21 00:30:00")
def test_collect_rejects_history_that_starts_late(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    목적: 지표의 첫 날에서 시작하지 않는 이력을 저장하지 않음을 고정한다.

    Given: 07-19 부터의 행 (첫 날 07-18 이 없다)
    When: 수집한다
    Then: ValueError 가 발생하고 저장 파일이 없다
    """
    # Given
    _install_pages(monkeypatch, {"first": {"data": [_row("2010-07-19", "0.0808"), _row("2010-07-20", "0.0747")]}})

    # When / Then
    with pytest.raises(ValueError, match="시작"):
        collect_coinmetrics_series(SERIES, output_dir=tmp_path)
    assert not (tmp_path / SERIES.file_name).exists()


def test_clock_is_read_before_the_fetch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    목적: 「끝나지 않은 날」의 기준 시각을 조회 «전»에 잼을 고정한다.

    Given: UTC 07-19 23:59:50 에 시작하고 조회 도중 UTC 07-20 00:00:05 로 넘어간다. 서버가 07-19 값까지 준다
    When: 수집한다
    Then: 07-19 는 조회 시작 때 끝나지 않은 날이라 빠진다(제외 1)
    """
    with freeze_time("2010-07-19 23:59:50") as frozen:
        # Given
        _install_pages(
            monkeypatch,
            {"first": {"data": [_row("2010-07-18", "0.08584"), _row("2010-07-19", "0.0808")]}},
            on_request=lambda: frozen.move_to("2010-07-20 00:00:05"),
        )

        # When
        result = collect_coinmetrics_series(SERIES, output_dir=tmp_path)

    # Then
    assert result.end_date == date(2010, 7, 18)
    assert result.excluded_recent_count == 1


@pytest.mark.parametrize("bad_value", ["0", "-1", "0.00004", "inf"])
@freeze_time("2010-07-20 00:30:00")
def test_collect_rejects_value_that_is_not_a_finite_positive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad_value: str
) -> None:
    """
    목적: 유한한 양수가 아닌 가격을 저장하지 않음을 고정한다.

    단일 값 로더는 부호도 무한대도 보지 않고 값의 범위를 수집기에 맡긴다. 0 이면 크로스체크가 무한대를 내고,
    무한대면 그 날의 대조가 무한대가 된다. 반올림(소수 4자리)으로 0 이 되는 값(0.00004)도 같다.

    Given: 07-19 값이 0 · 음수 · 반올림하면 0 · 무한대 중 하나
    When: 수집한다
    Then: ValueError 가 발생하고 저장 파일이 없다
    """
    # Given
    _install_pages(monkeypatch, {"first": {"data": [_row("2010-07-18", "0.08584"), _row("2010-07-19", bad_value)]}})

    # When / Then
    with pytest.raises(ValueError, match="유한한 양수"):
        collect_coinmetrics_series(SERIES, output_dir=tmp_path)
    assert not (tmp_path / SERIES.file_name).exists()
