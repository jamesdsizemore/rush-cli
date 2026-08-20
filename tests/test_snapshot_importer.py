"""Phase 04 contained snapshot-report importer contracts."""

from __future__ import annotations

import json
from pathlib import Path

from rush.tools.snapshot import SnapshotTool


def test_snapshot_imports_local_comparison_report_without_baseline_update(
    tmp_path: Path,
) -> None:
    report = tmp_path / "snapshot-report.json"
    report.write_text(json.dumps({"matched": 9, "mismatched": 1}))

    result = SnapshotTool().run(tmp_path, report_path=report)

    assert result["status"] == "fail"
    assert result["engine"] == "snapshot-report"
    assert result["metrics"] == {"matched": 9, "mismatched": 1}
    assert result["metadata"]["baseline_mutated"] is False


def test_snapshot_rejects_missing_malformed_and_outside_reports(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-snapshot.json"
    outside.write_text("{}")
    malformed = tmp_path / "bad-snapshot.json"
    malformed.write_text("not-json")

    missing = SnapshotTool().run(tmp_path, report_path=tmp_path / "absent.json")
    bad = SnapshotTool().run(tmp_path, report_path=malformed)
    escaped = SnapshotTool().run(tmp_path, report_path=outside)

    assert [item["status"] for item in (missing, bad, escaped)] == [
        "skipped",
        "error",
        "error",
    ]
