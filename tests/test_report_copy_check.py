import json
from pathlib import Path

from verify_lab.report.copy_check import DISPLAY_MISSING_FROM_MANIFEST, copy_check

Dataset = tuple[str, str, int]


def _write_manifest(path: Path, files: dict[str, tuple[str, str, int]]) -> Path:
    payload = {"파일": {name: {"첫날": first, "끝날": last, "행 수": rows} for name, (first, last, rows) in files.items()}}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _record(file: str, period: str, rows: int) -> dict[str, object]:
    return {"ticker": file, "label": file, "file": file, "period": period, "rows": rows}


def _write_payload(results_dir: Path, track: str, payload: dict[str, object]) -> None:
    folder = results_dir / "매매" / track
    folder.mkdir(parents=True)
    (folder / "summary.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_summary(results_dir: Path, track: str, *, measure: list[Dataset], trade: list[Dataset]) -> None:
    payload: dict[str, object] = {
        "track": track,
        "measure": {"datasets": [_record(*dataset) for dataset in measure]},
        "trade": {"datasets": [_record(*dataset) for dataset in trade]},
    }
    _write_payload(results_dir, track, payload)


def test_results_matching_the_copy_have_no_mismatch(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path / "manifest.json", {"SPY_adjusted.csv": ("1993-01-29", "2026-11-10", 8504)})
    results = tmp_path / "results"
    spy = ("SPY_adjusted.csv", "1993-01-29 ~ 2026-11-10", 8504)
    _write_summary(results, "중간선거_사이클", measure=[spy], trade=[spy])

    check = copy_check(results, manifest)

    assert check.mismatches == ()


def test_result_made_from_an_older_copy_is_reported(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path / "manifest.json", {"QQQ_adjusted.csv": ("1999-03-10", "2026-11-10", 6962)})
    results = tmp_path / "results"
    old = ("QQQ_adjusted.csv", "1999-03-10 ~ 2026-10-05", 6936)
    _write_summary(results, "중간선거_사이클", measure=[old], trade=[])

    mismatches = copy_check(results, manifest).mismatches

    assert [(m.summary.parent.name, m.file) for m in mismatches] == [("중간선거_사이클", "QQQ_adjusted.csv")]
    assert mismatches[0].result != mismatches[0].copy


def test_result_with_only_a_different_row_count_is_reported(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path / "manifest.json", {"SPY_adjusted.csv": ("1993-01-29", "2026-11-10", 8504)})
    results = tmp_path / "results"
    _write_summary(results, "중간선거_사이클", measure=[("SPY_adjusted.csv", "1993-01-29 ~ 2026-11-10", 8503)], trade=[])

    mismatches = copy_check(results, manifest).mismatches

    assert [m.file for m in mismatches] == ["SPY_adjusted.csv"]


def test_mismatch_inside_the_trade_block_is_reported(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path / "manifest.json", {"SPY_adjusted.csv": ("1993-01-29", "2026-11-10", 8504)})
    results = tmp_path / "results"
    _write_summary(
        results,
        "중간선거_사이클",
        measure=[("SPY_adjusted.csv", "1993-01-29 ~ 2026-11-10", 8504)],
        trade=[("SPY_adjusted.csv", "1993-01-29 ~ 2026-10-05", 8480)],
    )

    mismatches = copy_check(results, manifest).mismatches

    assert [m.file for m in mismatches] == ["SPY_adjusted.csv"]


def test_mismatch_in_a_record_nested_under_another_record_is_reported(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path / "manifest.json",
        {
            "BTCUSD_raw.csv": ("2011-08-18", "2026-11-10", 5564),
            "BTC_PriceUSD.csv": ("2010-07-18", "2026-11-10", 5960),
        },
    )
    results = tmp_path / "results"
    outer = _record("BTCUSD_raw.csv", "2011-08-18 ~ 2026-11-10", 5564)
    outer["reference"] = {"file": "BTC_PriceUSD.csv", "period": "2010-07-18 ~ 2026-10-05", "rows": 5924}
    _write_payload(results, "반감기_사이클", {"measure": {"datasets": [outer]}})

    mismatches = copy_check(results, manifest).mismatches

    assert [m.file for m in mismatches] == ["BTC_PriceUSD.csv"]


def test_result_reading_a_file_absent_from_the_manifest_is_reported(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path / "manifest.json", {"SPY_adjusted.csv": ("1993-01-29", "2026-11-10", 8504)})
    results = tmp_path / "results"
    _write_summary(results, "반감기_사이클", measure=[("BTCUSD_raw.csv", "2011-08-18 ~ 2026-11-10", 5520)], trade=[])

    mismatches = copy_check(results, manifest).mismatches

    assert [(m.file, m.copy) for m in mismatches] == [("BTCUSD_raw.csv", DISPLAY_MISSING_FROM_MANIFEST)]


def test_result_folder_without_summary_is_skipped(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path / "manifest.json", {"SPY_adjusted.csv": ("1993-01-29", "2026-11-10", 8504)})
    results = tmp_path / "results"
    (results / "조사" / "pykrx_ETF_실측").mkdir(parents=True)

    check = copy_check(results, manifest)

    assert (check.summaries, check.mismatches) == (0, ())
