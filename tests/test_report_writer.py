"""검증 산출물 저장의 계약을 고정한다.

산출물은 덮어쓰지 않고 실행 시각으로 구분한다 — 같은 검증을 파라미터만 바꿔 여러 번 돌리는 것이
이 프로젝트의 전제이기 때문이다. 폴더 규칙이 흔들리면 나중에 그 결과들이 같은 검증의 산출물인지
알 수 없게 된다.

**테스트는 실제 `storage/` 를 건드리지 않는다.** 경로 상수를 import 시점에 캡처하는 모듈까지
함께 패치해야 격리가 성립한다.
"""

import json
from pathlib import Path

import pandas as pd
import pytest
from freezegun import freeze_time

from verify_lab import common_constants
from verify_lab.report import writer
from verify_lab.report.constants import RUN_SUMMARY_FILENAME, SIGNALS_FILENAME

STUDY_NAME = "index_extreme"


@pytest.fixture
def mock_results_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """검증 산출물 경로를 임시 디렉터리로 격리한다.

    `writer` 는 `from ... import RESULTS_DIR` 로 import 시점에 경로를 자기 모듈에 캡처한다.
    `common_constants` 만 패치하면 이미 캡처된 실제 경로가 그대로 쓰인다.
    """
    results_dir = tmp_path / "results"

    monkeypatch.setattr(common_constants, "RESULTS_DIR", results_dir)
    monkeypatch.setattr(writer, "RESULTS_DIR", results_dir)

    return results_dir


@freeze_time("2026-08-13 12:30:45", tz_offset=0)
def test_directory_name_uses_run_time_and_study_name(mock_results_dir: Path) -> None:
    """
    목적: 결과 폴더 이름이 `<실행시각>_<검증명>` 임을 고정한다.

    Given: 고정된 실행 시각 (KST 21:30:45)
    When: 결과 폴더를 만든다
    Then: 이름이 실행 시각과 검증명으로 구성된다
    """
    # When
    directory = writer.create_run_directory(STUDY_NAME)

    # Then
    assert directory.parent == mock_results_dir
    assert directory.name == f"20260813_213045_{STUDY_NAME}"


@freeze_time("2026-08-13 12:30:45", tz_offset=0)
def test_directory_is_created(mock_results_dir: Path) -> None:
    """
    목적: 폴더가 실제로 만들어진다.

    Given: 아직 없는 결과 경로
    When: 결과 폴더를 만든다
    Then: 디렉터리가 존재한다
    """
    # When
    directory = writer.create_run_directory(STUDY_NAME)

    # Then
    assert directory.is_dir()


def test_rejects_blank_study_name(mock_results_dir: Path) -> None:
    """
    목적: 검증명이 비면 폴더 이름이 시각뿐이라 무엇의 결과인지 알 수 없다.

    Given: 공백 검증명
    When: 결과 폴더를 만든다
    Then: ValueError
    """
    with pytest.raises(ValueError, match="검증명"):
        writer.create_run_directory("   ")


def test_table_is_saved_without_index(tmp_path: Path) -> None:
    """
    목적: CSV 에 인덱스 컬럼이 섞이지 않는다. 섞이면 사용자가 여는 표에 의미 없는 열이 생긴다.

    Given: 2행짜리 표
    When: 저장한다
    Then: 첫 줄이 선언한 헤더 그대로다
    """
    # Given
    table = pd.DataFrame({"날짜": ["2026-01-05", "2026-01-06"], "평균(%)": [2.22, 3.33]})

    # When
    path = writer.save_table(tmp_path, SIGNALS_FILENAME, table)

    # Then
    assert path.read_text(encoding="utf-8-sig").splitlines()[0] == "날짜,평균(%)"


def test_table_is_saved_with_bom(tmp_path: Path) -> None:
    """
    목적: 한글 헤더가 엑셀에서 깨지지 않도록 BOM 을 붙인다 (기존 산출물 관용과 동일).

    Given: 한글 헤더를 가진 표
    When: 저장한다
    Then: 파일이 BOM 으로 시작한다
    """
    # Given
    table = pd.DataFrame({"구간": ["1일"]})

    # When
    path = writer.save_table(tmp_path, SIGNALS_FILENAME, table)

    # Then
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_rejects_empty_table(tmp_path: Path) -> None:
    """
    목적: 빈 표를 조용히 저장하지 않는다. 헤더만 있는 파일은 "결과가 없다"와 구분되지 않는다.

    Given: 행이 없는 표
    When: 저장한다
    Then: ValueError
    """
    with pytest.raises(ValueError, match="비어"):
        writer.save_table(tmp_path, SIGNALS_FILENAME, pd.DataFrame({"구간": []}))


def test_run_summary_keeps_parameters(tmp_path: Path) -> None:
    """
    목적: 실행 파라미터가 산출물 옆에 남는다. 남지 않으면 어떤 설정의 결과인지 재구성할 수 없다.

    Given: 시드와 반복 수를 담은 실행 정보
    When: 저장한다
    Then: JSON 에 그대로 남는다
    """
    # Given
    payload = {"study": STUDY_NAME, "seed": 0, "repeats": 1000}

    # When
    path = writer.save_run_summary(tmp_path, payload)

    # Then
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["seed"] == 0
    assert saved["repeats"] == 1000


def test_run_summary_uses_the_declared_filename(tmp_path: Path) -> None:
    """
    목적: 실행 정보 파일명을 고정한다 — 검증마다 이름이 달라지면 찾을 수 없다.

    Given: 실행 정보
    When: 저장한다
    Then: 선언된 파일명으로 저장된다
    """
    # When
    path = writer.save_run_summary(tmp_path, {"study": STUDY_NAME})

    # Then
    assert path.name == RUN_SUMMARY_FILENAME
