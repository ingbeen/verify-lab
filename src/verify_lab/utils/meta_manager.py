"""실행 이력 관리

검증·수집을 실행할 때마다 무엇을 어떤 설정으로 돌렸는지 `storage/results/meta.json` 에 쌓는다.
산출물 폴더만 보고는 알 수 없는 실행 조건이 여기 남는다.

**타입별로 최근 N개만 순환 저장한다.** 전부 쌓으면 파일이 계속 커지는데, 오래된 실행은
산출물 폴더가 이미 실행 시각으로 구분해 두고 있어 이력의 값이 떨어진다.
"""

import json
from datetime import UTC, datetime
from typing import Any

from verify_lab.common_constants import KST, META_JSON_PATH

# 타입별로 남기는 최대 실행 이력 수
MAX_HISTORY_COUNT = 5

MetaDict = dict[str, Any]
HistoryList = list[MetaDict]
FullMetaJson = dict[str, HistoryList]


def _load_full_metadata() -> FullMetaJson:
    """`meta.json` 전체를 읽는다.

    Returns:
        타입 → 실행 이력. 파일이 없으면 빈 dict
    """
    if not META_JSON_PATH.exists():
        return {}

    with META_JSON_PATH.open("r", encoding="utf-8") as f:
        full_meta: FullMetaJson = json.load(f)

    return full_meta


def _rotate_history(history: HistoryList, new_entry: MetaDict) -> HistoryList:
    """새 항목을 맨 앞에 넣고 최대 개수를 유지한다.

    Args:
        history: 기존 이력
        new_entry: 새 항목

    Returns:
        최신순으로 정렬된 이력 (최대 `MAX_HISTORY_COUNT` 개)
    """
    return ([new_entry] + history)[:MAX_HISTORY_COUNT]


def _add_timestamp(metadata: MetaDict) -> MetaDict:
    """KST 타임스탬프를 붙인 사본을 만든다.

    Args:
        metadata: 원본 메타데이터

    Returns:
        타임스탬프가 추가된 사본. 원본은 변경하지 않는다
    """
    result = metadata.copy()
    result["timestamp"] = datetime.now(UTC).astimezone(KST).isoformat(timespec="seconds")

    return result


def save_metadata(csv_type: str, metadata: MetaDict) -> None:
    """실행 정보를 `meta.json` 에 저장한다.

    타임스탬프는 자동으로 붙으며, 같은 타입의 오래된 이력은 순환 저장으로 밀려난다.

    Args:
        csv_type: 실행 종류 식별자 (목록은 `scripts/CLAUDE.md`)
        metadata: 남길 실행 정보
    """
    full_meta = _load_full_metadata()
    full_meta[csv_type] = _rotate_history(full_meta.get(csv_type, []), _add_timestamp(metadata))

    META_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with META_JSON_PATH.open("w", encoding="utf-8") as f:
        json.dump(full_meta, f, indent=2, ensure_ascii=False)
