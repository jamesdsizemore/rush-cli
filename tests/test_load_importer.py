"""Phase 04 contained load-report importer contracts."""

from __future__ import annotations

import json
from pathlib import Path

from rush.tools.load import LoadTool


def test_load_imports_local_report_without_contacting_a_target(tmp_path: Path) -> None:
    report = tmp_path / "load-report.json"
    report.write_text(
        json.dumps(
            {"failed_requests": 2, "total_requests": 100, "duration_seconds": 10}
        )
    )

    result = LoadTool().run(tmp_path, report_path=report)

    assert result["status"] == "fail"
    assert result["engine"] == "load-report"
    assert result["metrics"] == {
        "failed_requests": 2,
        "total_requests": 100,
        "duration_seconds": 10,
    }
    assert result["metadata"]["evidence_source"] == "imported-local-report"


def test_load_rejects_missing_malformed_and_outside_reports(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-load.json"
    outside.write_text("{}")
    malformed = tmp_path / "bad-load.json"
    malformed.write_text("not-json")

    missing = LoadTool().run(tmp_path, report_path=tmp_path / "absent.json")
    bad = LoadTool().run(tmp_path, report_path=malformed)
    escaped = LoadTool().run(tmp_path, report_path=outside)

    assert [item["status"] for item in (missing, bad, escaped)] == [
        "skipped",
        "error",
        "error",
    ]
