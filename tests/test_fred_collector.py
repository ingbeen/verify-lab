"""FRED 수집기의 CSV 해석과 실패 정책을 고정한다.

외부 서버를 부르지 않는다. FRED 응답은 전부 모의로 만들며, 이 테스트가 지키는 것은 셋이다.

1. **헤더 이름이 바뀌어도 날짜를 잡는다** — FRED 는 `DATE` 를 `observation_date` 로 바꾼 적이 있다
2. **결측을 메우지 않고 제외하되 건수를 돌려준다**
3. **휴장일을 전일값으로 이월하지 않는다** — 이월은 측정 계층의 판단이다

미국 휴장일은 행이 있고 값만 비어 있다. 그래서 결측 제외가 곧 휴장일 제외다.
"""

import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import pytest

from verify_lab.common_constants import COL_DATE, COL_VALUE
from verify_lab.data.fred_collector import (
    FRED_SERIES,
    FredSeries,
    collect_fred_series,
    find_series,
    parse_fred_csv,
    request_fred_csv,
)

SERIES = FredSeries(
    key="test",
    label="테스트 금리",
    series_id="DTB3",
    file_name="TEST.csv",
    decimals=2,
    unit="연%",
)


def _install_response(monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    """`urlopen` 을 모의 CSV 응답으로 바꾼다."""

    class _FakeResponse:
        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return body.encode("utf-8")

    def fake_urlopen(request: object, timeout: float | None = None) -> _FakeResponse:
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def test_parses_current_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 현재 헤더(`observation_date`)를 해석함을 고정한다.

    Given: 현재 형식의 CSV
    When: 파싱한다
    Then: 날짜와 값이 단일 값 스키마로 나온다
    """
    frame, excluded = parse_fred_csv("observation_date,DTB3\n1954-01-04,1.33\n1954-01-05,1.28\n", SERIES)

    assert list(frame.columns) == [COL_DATE, COL_VALUE]
    assert frame[COL_DATE].tolist() == [date(1954, 1, 4), date(1954, 1, 5)]
    assert frame[COL_VALUE].tolist() == pytest.approx([1.33, 1.28], abs=1e-12)
    assert excluded == 0


def test_parses_legacy_header() -> None:
    """
    목적: 예전 헤더(`DATE`)도 해석함을 고정한다.

    **날짜 컬럼을 이름이 아니라 위치로 잡는 이유**다. 이름에 기대면 FRED 가 헤더를
    다시 바꿀 때 조용히 깨진다.

    Given: 예전 형식의 CSV
    When: 파싱한다
    Then: 똑같이 해석된다
    """
    frame, _ = parse_fred_csv("DATE,DTB3\n1954-01-04,1.33\n", SERIES)

    assert frame[COL_DATE].tolist() == [date(1954, 1, 4)]


def test_excludes_dot_missing_values_and_counts_them() -> None:
    """
    목적: 마침표 결측을 메우지 않고 제외하되 건수를 돌려줌을 고정한다 (보간 금지).

    Given: 값이 마침표인 행이 섞인 CSV
    When: 파싱한다
    Then: 그 행이 빠지고 제외 건수가 반환된다
    """
    frame, excluded = parse_fred_csv("observation_date,DTB3\n2026-01-02,4.20\n2026-01-05,.\n2026-01-06,4.18\n", SERIES)

    assert len(frame) == 2
    assert excluded == 1


def test_does_not_fill_missing_calendar_days() -> None:
    """
    목적: 빠진 날짜를 채워 넣지 않음을 고정한다.

    결측을 제외하고 나면 그 날짜는 아예 사라진다. 전일값 이월은 측정 계층의 판단이며,
    수집기가 미리 메우면 "원래 값이 없던 날"과 "메운 날"을 구분할 수 없게 된다.

    Given: 중간 날짜가 빠진 CSV
    When: 파싱한다
    Then: 행 수가 그대로이고 빠진 날짜가 생기지 않는다
    """
    frame, _ = parse_fred_csv("observation_date,DTB3\n2026-01-02,4.20\n2026-01-06,4.18\n", SERIES)

    assert len(frame) == 2
    assert frame[COL_DATE].tolist() == [date(2026, 1, 2), date(2026, 1, 6)]


def test_missing_value_column_raises() -> None:
    """
    목적: 값 컬럼이 없으면 즉시 실패함을 고정한다.

    Given: 다른 시리즈의 CSV
    When: 파싱한다
    Then: ValueError 가 발생하고 메시지에 기대한 컬럼명이 담긴다
    """
    with pytest.raises(ValueError, match=SERIES.series_id):
        parse_fred_csv("observation_date,GDP\n2026-01-02,4.20\n", SERIES)


def test_all_missing_response_raises() -> None:
    """
    목적: 값이 하나도 없는 응답을 빈 파일로 저장하지 않음을 고정한다 (경계 조건).

    Given: 모든 값이 마침표인 CSV
    When: 파싱한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="값이 있는 행"):
        parse_fred_csv("observation_date,DTB3\n2026-01-02,.\n2026-01-05,.\n", SERIES)


def test_header_only_response_raises() -> None:
    """
    목적: 헤더만 있는 응답을 정상으로 보지 않음을 고정한다 (경계 조건).

    Given: 헤더만 있는 CSV
    When: 파싱한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="비어"):
        parse_fred_csv("observation_date,DTB3\n", SERIES)


def test_empty_series_id_raises() -> None:
    """
    목적: 빈 시리즈 ID 로 요청하지 않음을 고정한다 (경계 조건).

    Given: 공백뿐인 시리즈 ID
    When: 요청한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="시리즈 ID"):
        request_fred_csv("   ")


def test_http_error_is_translated(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: HTTP 오류를 프로젝트 예외로 바꿔 올림을 고정한다.

    Given: HTTP 404 를 주는 서버
    When: 요청한다
    Then: ValueError 가 발생하고 메시지에 상태 코드가 담긴다
    """

    # Given
    def fake_urlopen(request: object, timeout: float | None = None) -> None:
        raise urllib.error.HTTPError("https://example.invalid", 404, "Not Found", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    # When / Then
    with pytest.raises(ValueError, match="404"):
        request_fred_csv("DTB3")


def test_collect_saves_sorted_and_rounded_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    목적: 저장 파일이 날짜 오름차순이고 지정 자릿수로 반올림됨을 고정한다.

    Given: 날짜가 뒤섞이고 자릿수가 깊은 CSV
    When: 수집한다
    Then: 정렬·반올림된 파일이 저장된다
    """
    # Given
    _install_response(monkeypatch, "observation_date,DTB3\n2026-01-06,4.187\n2026-01-02,4.202\n")

    # When
    result = collect_fred_series(SERIES, output_dir=tmp_path)

    # Then
    saved = (tmp_path / SERIES.file_name).read_text(encoding="utf-8").splitlines()
    assert saved[0] == f"{COL_DATE},{COL_VALUE}"
    assert saved[1] == "2026-01-02,4.2"
    assert saved[2] == "2026-01-06,4.19"
    assert result.row_count == 2
    assert result.start_date == date(2026, 1, 2)
    assert result.end_date == date(2026, 1, 6)


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

    Given: 등록된 수집 대상 목록
    When: 이름과 파일명을 센다
    Then: 중복이 없다
    """
    assert len({s.key for s in FRED_SERIES}) == len(FRED_SERIES)
    assert len({s.file_name for s in FRED_SERIES}) == len(FRED_SERIES)
