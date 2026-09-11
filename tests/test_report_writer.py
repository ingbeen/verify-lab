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
from verify_lab.common_constants import RESULT_LAYER_PROBE, RESULT_LAYER_STRATEGY, RESULT_LAYER_STUDY
from verify_lab.report import writer
from verify_lab.report.constants import RUN_SUMMARY_FILENAME, SIGNALS_FILENAME

TRACK_NAME = "reverse"


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
def test_directory_name_uses_run_time_and_track_name(mock_results_dir: Path) -> None:
    """
    목적: 결과 폴더 이름이 `<실행시각>_<매매법>` 임을 고정한다.

    **계층 접미사를 붙이지 않는다.** 계층은 상위 폴더가 말하므로 이름에 또 넣으면 중복이다.

    Given: 고정된 실행 시각 (KST 21:30:45)
    When: 결과 폴더를 만든다
    Then: 이름이 실행 시각과 매매법 이름으로만 구성된다
    """
    # When
    directory = writer.create_run_directory(TRACK_NAME, layer=RESULT_LAYER_STUDY)

    # Then
    assert directory.name == f"20260813_213045_{TRACK_NAME}"


@freeze_time("2026-08-13 12:30:45", tz_offset=0)
@pytest.mark.parametrize("layer", [RESULT_LAYER_STUDY, RESULT_LAYER_STRATEGY, RESULT_LAYER_PROBE])
def test_layer_becomes_the_parent_folder(mock_results_dir: Path, layer: str) -> None:
    """
    목적: 계층이 **경로**로 드러나는 것을 고정한다 (결정 3).

    같은 매매법의 측정과 매매가 같은 이름을 쓰므로, 둘을 가르는 것은 상위 폴더뿐이다.
    이 계약이 무너지면 두 계층의 산출물이 한 자리에 섞여 폴더 목록만 봐서는 구별되지 않는다.

    Given: 계층 이름
    When: 결과 폴더를 만든다
    Then: 산출물 루트 바로 아래 그 계층 폴더가 부모다
    """
    # When
    directory = writer.create_run_directory(TRACK_NAME, layer=layer)

    # Then
    assert directory.parent == mock_results_dir / layer


@freeze_time("2026-08-13 12:30:45", tz_offset=0)
def test_same_track_splits_by_layer(mock_results_dir: Path) -> None:
    """
    목적: **같은 slug 가 두 계층에서 충돌하지 않는다** (목표 1 의 집행).

    매매법 이름을 하나로 통일한 결과 측정과 매매가 같은 문자열을 넘긴다. 계층 폴더가
    갈라주지 않으면 같은 시각에 돌린 두 실행이 한 폴더를 공유해 산출물이 섞인다.

    Given: 같은 매매법 이름과 서로 다른 두 계층
    When: 각각 결과 폴더를 만든다
    Then: 이름은 같고 경로는 다르다
    """
    # When
    study = writer.create_run_directory(TRACK_NAME, layer=RESULT_LAYER_STUDY)
    strategy = writer.create_run_directory(TRACK_NAME, layer=RESULT_LAYER_STRATEGY)

    # Then
    assert study.name == strategy.name
    assert study != strategy


@freeze_time("2026-08-13 12:30:45", tz_offset=0)
def test_directory_is_created(mock_results_dir: Path) -> None:
    """
    목적: 폴더가 실제로 만들어진다 (계층 폴더까지 함께).

    Given: 아직 없는 결과 경로
    When: 결과 폴더를 만든다
    Then: 디렉터리가 존재한다
    """
    # When
    directory = writer.create_run_directory(TRACK_NAME, layer=RESULT_LAYER_STUDY)

    # Then
    assert directory.is_dir()


def test_rejects_blank_track_name(mock_results_dir: Path) -> None:
    """
    목적: 매매법 이름이 비면 폴더 이름이 시각뿐이라 무엇의 결과인지 알 수 없다.

    Given: 공백 이름
    When: 결과 폴더를 만든다
    Then: ValueError
    """
    with pytest.raises(ValueError, match="매매법"):
        writer.create_run_directory("   ", layer=RESULT_LAYER_STUDY)


@pytest.mark.parametrize("bad_name", ["month_end_v2", "QQQ_expiry", "month-end", "월말"])
def test_rejects_track_name_the_citation_scanner_cannot_find(mock_results_dir: Path, bad_name: str) -> None:
    """
    목적: 인용 판정기가 못 찾는 이름으로 폴더를 만들지 못하게 한다 (경계 조건).

    `result_citations` 는 폴더 이름을 `<8자리>_<6자리>_<영소문자와 밑줄>` 로 찾는다. 숫자나
    대문자가 섞인 slug 로 폴더를 만들면 **폴더는 멀쩡히 생기는데 그 이름은 영원히 인용으로
    잡히지 않는다** — 결과 문서가 근거로 적어도 `/clean-results` 가 삭제 후보로 내놓는다.
    계층 이름을 검사하는 것과 **같은 계열의 조용한 실패**라 같은 자리에서 막는다.

    Given: 스캐너 패턴에 맞지 않는 매매법 이름
    When: 결과 폴더를 만든다
    Then: ValueError
    """
    with pytest.raises(ValueError, match="영소문자"):
        writer.create_run_directory(bad_name, layer=RESULT_LAYER_STUDY)


def test_accepts_every_real_track_name() -> None:
    """
    목적: 위 검사가 **실제로 쓰는 이름을 막지 않는다**를 고정한다.

    거부 테스트만 두면 패턴을 지나치게 좁혀도 통과한다. 짝으로 둬서 저장소의 실제 slug 가
    전부 통과하는지 본다.

    Given: 각 검증 패키지가 선언한 매매법 이름
    When: 폴더 이름 검사 패턴에 맞춘다
    Then: 전부 통과한다
    """
    # Given
    from verify_lab.studies.futures_leverage.constants import TRACK_NAME as FUTURES
    from verify_lab.studies.leverage_tracking.constants import TRACK_NAME as LEVERAGE
    from verify_lab.studies.month_end.constants import TRACK_NAME as MONTH_END
    from verify_lab.studies.option_expiry.constants import TRACK_NAME as OPTION_EXPIRY
    from verify_lab.studies.reverse.constants import TRACK_NAME as REVERSE
    from verify_lab.studies.usdkrw_equivalence.constants import TRACK_NAME as EQUIVALENCE

    names = [REVERSE, OPTION_EXPIRY, MONTH_END, EQUIVALENCE, LEVERAGE, FUTURES]

    # When / Then
    unmatched = [name for name in names if not writer.VALID_TRACK_NAME.match(name)]
    assert unmatched == [], f"실제 매매법 이름이 폴더 이름 검사를 통과하지 못합니다: {unmatched}"


def test_rejects_unknown_layer(mock_results_dir: Path) -> None:
    """
    목적: 선언되지 않은 계층으로 폴더를 파지 못하게 한다 (경계 조건).

    오타 하나를 통과시키면 **예외 없이 새 상위 폴더가 생긴다.** 그 폴더는 인용 판정기의
    탐색 대상이 아니므로 산출물이 조용히 시야에서 사라지고, 정리 도구도 보지 못한다.

    Given: 목록에 없는 계층 이름
    When: 결과 폴더를 만든다
    Then: ValueError
    """
    with pytest.raises(ValueError, match="계층"):
        writer.create_run_directory(TRACK_NAME, layer="연구")


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
    payload = {"study": TRACK_NAME, "seed": 0, "repeats": 1000}

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
    path = writer.save_run_summary(tmp_path, {"study": TRACK_NAME})

    # Then
    assert path.name == RUN_SUMMARY_FILENAME
