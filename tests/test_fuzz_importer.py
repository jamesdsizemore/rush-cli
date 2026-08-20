"""Phase 04 contained fuzz-report importer contracts."""

from __future__ import annotations

import json
from pathlib import Path

from rush.tools.fuzz import FuzzTool


def test_fuzz_imports_local_report_without_executing_fuzzer(tmp_path: Path) -> None:
    report = tmp_path / "fuzz-report.json"
    report.write_text(json.dumps({"crashes": 1, "timeouts": 0, "seed": 42}))

    result = FuzzTool().run(tmp_path, report_path=report)

    assert result["status"] == "fail"
    assert result["engine"] == "fuzz-report"
    assert result["metrics"] == {"crashes": 1, "timeouts": 0}
    assert result["metadata"]["seed"] == 42


def test_fuzz_rejects_missing_malformed_and_outside_reports(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-fuzz.json"
    outside.write_text("{}")
    malformed = tmp_path / "bad-fuzz.json"
    malformed.write_text("not-json")

    missing = FuzzTool().run(tmp_path, report_path=tmp_path / "absent.json")
    bad = FuzzTool().run(tmp_path, report_path=malformed)
    escaped = FuzzTool().run(tmp_path, report_path=outside)

    assert [item["status"] for item in (missing, bad, escaped)] == [
        "skipped",
        "error",
        "error",
    ]
