import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from verify_lab.report.constants import RUN_SUMMARY_FILENAME
from verify_lab.report.run_summary import KEY_DATASET_FILE, KEY_DATASET_PERIOD, KEY_DATASET_ROWS, PERIOD_SEPARATOR

KEY_MANIFEST_FILES: Final = "파일"
KEY_MANIFEST_FIRST_DAY: Final = "첫날"
KEY_MANIFEST_LAST_DAY: Final = "끝날"
KEY_MANIFEST_ROWS: Final = "행 수"

DISPLAY_MISSING_FROM_MANIFEST: Final = "매니페스트에 없음"


@dataclass(frozen=True)
class CopyMismatch:
    summary: Path
    file: str
    result: str
    copy: str


@dataclass(frozen=True)
class CopyCheck:
    summaries: int
    records: int
    mismatches: tuple[CopyMismatch, ...]


def copy_check(results_dir: Path, manifest_path: Path) -> CopyCheck:
    copies = _copy_records(manifest_path)
    summaries = sorted(results_dir.glob(f"*/*/{RUN_SUMMARY_FILENAME}"))
    records = 0
    mismatches: list[CopyMismatch] = []
    for summary in summaries:
        for record in _dataset_records(json.loads(summary.read_text(encoding="utf-8"))):
            records += 1
            file = f"{record[KEY_DATASET_FILE]}"
            result = _describe(record[KEY_DATASET_PERIOD], record[KEY_DATASET_ROWS])
            copy = copies.get(file, DISPLAY_MISSING_FROM_MANIFEST)
            mismatch = CopyMismatch(summary=summary, file=file, result=result, copy=copy)
            if result != copy and mismatch not in mismatches:
                mismatches.append(mismatch)

    return CopyCheck(summaries=len(summaries), records=records, mismatches=tuple(mismatches))


def _copy_records(manifest_path: Path) -> dict[str, str]:
    manifest = cast(dict[str, object], json.loads(manifest_path.read_text(encoding="utf-8")))
    files = cast(dict[str, dict[str, object]], manifest[KEY_MANIFEST_FILES])

    return {
        name: _describe(
            f"{entry[KEY_MANIFEST_FIRST_DAY]}{PERIOD_SEPARATOR}{entry[KEY_MANIFEST_LAST_DAY]}",
            entry[KEY_MANIFEST_ROWS],
        )
        for name, entry in files.items()
    }


def _dataset_records(node: object) -> list[dict[str, object]]:
    if isinstance(node, list):
        return [record for item in cast(list[object], node) for record in _dataset_records(item)]
    if not isinstance(node, dict):
        return []

    mapping = cast(dict[str, object], node)
    found = [mapping] if {KEY_DATASET_FILE, KEY_DATASET_PERIOD, KEY_DATASET_ROWS} <= mapping.keys() else []

    return found + [record for value in mapping.values() for record in _dataset_records(value)]


def _describe(period: object, rows: object) -> str:
    return f"{period} · {rows}행"


__all__ = ["DISPLAY_MISSING_FROM_MANIFEST", "CopyCheck", "CopyMismatch", "copy_check"]
