"""실행 메타데이터 저장의 순환·타임스탬프·불변성 계약을 고정한다.

메타데이터는 "어떤 파라미터로 돌린 결과인가"를 남기는 유일한 기록이다. 이력이 조용히
사라지거나 타임스탬프 기준 시간대가 흔들리면 결과를 재현할 수 없다.
"""

import json
from pathlib import Path
from typing import Any

from freezegun import freeze_time

from verify_lab.utils import meta_manager


def _read_meta(meta_json_path: Path) -> dict[str, list[dict[str, Any]]]:
    """저장된 meta.json 을 읽어 파싱한다."""
    return json.loads(meta_json_path.read_text(encoding="utf-8"))


def test_save_creates_file_when_missing(mock_meta_path: Path) -> None:
    """
    목적: 파일도 상위 디렉터리도 없는 상태에서 저장이 성립함을 고정한다 (경계 조건).

    Given: meta.json 이 없고 상위 디렉터리도 없는 임시 경로
    When: 메타데이터를 한 번 저장한다
    Then: 파일이 생성된다
    """
    # Given
    assert not mock_meta_path.exists()

    # When
    meta_manager.save_metadata("smoke", {"rows": 10})

    # Then
    assert mock_meta_path.is_file()


def test_saved_entry_keeps_original_fields(mock_meta_path: Path) -> None:
    """
    목적: 저장된 항목이 원본 필드를 그대로 보존함을 고정한다.

    Given: 임의의 메타데이터
    When: 저장 후 다시 읽는다
    Then: 원본 필드가 값 그대로 남아 있다
    """
    # Given
    metadata = {"rows": 10, "ticker": "QQQ"}

    # When
    meta_manager.save_metadata("smoke", metadata)
    saved = _read_meta(mock_meta_path)["smoke"][0]

    # Then
    assert saved["rows"] == 10
    assert saved["ticker"] == "QQQ"


@freeze_time("2026-08-10 01:35:00")
def test_timestamp_is_recorded_in_kst(mock_meta_path: Path) -> None:
    """
    목적: 타임스탬프가 KST(+09:00) ISO 8601 초 단위임을 고정한다.

    UTC 01:35 은 KST 10:35 이다. 시간대가 바뀌면 실행 시각이 9시간 어긋나
    결과 폴더와 이력이 서로 다른 날짜를 가리키게 된다.

    Given: UTC 2026-08-10 01:35:00 으로 고정된 시각
    When: 메타데이터를 저장한다
    Then: timestamp 가 KST 표기로 기록된다
    """
    # When
    meta_manager.save_metadata("smoke", {"rows": 1})

    # Then
    saved = _read_meta(mock_meta_path)["smoke"][0]
    assert saved["timestamp"] == "2026-08-10T10:35:00+09:00"


def test_history_is_capped_at_max_count(mock_meta_path: Path) -> None:
    """
    목적: 이력이 최대 개수를 넘지 않음을 고정한다.

    Given: 최대 개수보다 3회 많은 저장
    When: 저장된 이력을 읽는다
    Then: 이력 길이가 MAX_HISTORY_COUNT 와 같다
    """
    # Given / When
    for index in range(meta_manager.MAX_HISTORY_COUNT + 3):
        meta_manager.save_metadata("smoke", {"seq": index})

    # Then
    history = _read_meta(mock_meta_path)["smoke"]
    assert len(history) == meta_manager.MAX_HISTORY_COUNT


def test_history_is_newest_first(mock_meta_path: Path) -> None:
    """
    목적: 이력 정렬이 최신순임을 고정한다 (오래된 것부터 밀려남).

    Given: 최대 개수보다 3회 많은 저장
    When: 저장된 이력의 순번을 읽는다
    Then: 가장 최근 저장이 맨 앞이고 순번이 내림차순이다
    """
    # Given / When
    total = meta_manager.MAX_HISTORY_COUNT + 3
    for index in range(total):
        meta_manager.save_metadata("smoke", {"seq": index})

    # Then
    history = _read_meta(mock_meta_path)["smoke"]
    expected = list(range(total - 1, total - 1 - meta_manager.MAX_HISTORY_COUNT, -1))
    assert [entry["seq"] for entry in history] == expected


def test_original_metadata_is_not_mutated(mock_meta_path: Path) -> None:
    """
    목적: 저장이 호출자의 dict 를 변경하지 않음을 고정한다 (데이터 불변성).

    Given: 타임스탬프가 없는 메타데이터
    When: 저장한다
    Then: 원본 dict 에 timestamp 가 추가되지 않는다
    """
    # Given
    metadata = {"rows": 10}

    # When
    meta_manager.save_metadata("smoke", metadata)

    # Then
    assert metadata == {"rows": 10}


def test_types_are_stored_independently(mock_meta_path: Path) -> None:
    """
    목적: 서로 다른 타입의 이력이 섞이지 않음을 고정한다.

    Given: 두 종류의 타입으로 각각 저장
    When: 저장된 전체 메타를 읽는다
    Then: 타입별로 분리돼 각각 1건씩 존재한다
    """
    # Given / When
    meta_manager.save_metadata("collect", {"rows": 1})
    meta_manager.save_metadata("study", {"rows": 2})

    # Then
    full_meta = _read_meta(mock_meta_path)
    assert len(full_meta["collect"]) == 1
    assert len(full_meta["study"]) == 1


def test_existing_history_survives_new_type(mock_meta_path: Path) -> None:
    """
    목적: 새 타입을 저장해도 기존 타입의 이력이 유실되지 않음을 고정한다.

    Given: 한 타입으로 저장된 이력
    When: 다른 타입으로 저장한다
    Then: 먼저 저장한 타입의 값이 그대로 남아 있다
    """
    # Given
    meta_manager.save_metadata("collect", {"rows": 1})

    # When
    meta_manager.save_metadata("study", {"rows": 2})

    # Then
    assert _read_meta(mock_meta_path)["collect"][0]["rows"] == 1
