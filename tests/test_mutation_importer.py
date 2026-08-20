"""Phase 04 contained mutation-report importer contracts."""

from __future__ import annotations

import json
from pathlib import Path

from rush.tools.mutation import MutationTool


def test_mutation_imports_local_report_without_executing_mutation_engine(
    tmp_path: Path,
) -> None:
    report = tmp_path / "mutation-report.json"
    report.write_text(json.dumps({"killed": 8, "survived": 2, "timeout": 1}))

    result = MutationTool().run(tmp_path, report_path=report)

    assert result["status"] == "fail"
    assert result["engine"] == "mutation-report"
    assert result["metrics"] == {"killed": 8, "survived": 2, "timeout": 1}
    assert result["metadata"]["evidence_source"] == "imported-local-report"


def test_mutation_rejects_missing_malformed_and_outside_reports(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-mutation.json"
    outside.write_text("{}")
    malformed = tmp_path / "bad-mutation.json"
    malformed.write_text("not-json")

    missing = MutationTool().run(tmp_path, report_path=tmp_path / "absent.json")
    bad = MutationTool().run(tmp_path, report_path=malformed)
    escaped = MutationTool().run(tmp_path, report_path=outside)

    assert [item["status"] for item in (missing, bad, escaped)] == [
        "skipped",
        "error",
        "error",
    ]
