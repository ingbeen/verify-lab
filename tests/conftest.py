"""테스트 공통 픽스처

파일을 쓰는 기능은 프로덕션 경로(`storage/`)를 건드리지 않도록 `tmp_path`로 격리한다.
"""

from pathlib import Path

import pytest

from verify_lab import common_constants
from verify_lab.utils import meta_manager


@pytest.fixture
def mock_meta_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """실행 메타데이터 경로를 임시 디렉터리로 격리한다.

    `meta_manager`는 `from ... import META_JSON_PATH` 형태로 import 시점에 경로 값을
    자기 모듈에 캡처한다. 따라서 `common_constants`만 패치하면 이미 캡처된 실제 경로가
    그대로 쓰인다. 두 모듈을 함께 패치해야 격리가 성립한다.

    Args:
        tmp_path: pytest가 테스트마다 새로 만드는 임시 디렉터리
        monkeypatch: 테스트 종료 시 원복을 보장하는 pytest 패치 도구

    Returns:
        격리된 meta.json 경로 (아직 파일은 생성되지 않은 상태)
    """
    meta_json_path = tmp_path / "results" / "meta.json"

    monkeypatch.setattr(common_constants, "META_JSON_PATH", meta_json_path)
    monkeypatch.setattr(meta_manager, "META_JSON_PATH", meta_json_path)

    return meta_json_path
