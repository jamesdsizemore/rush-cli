"""Phase 04 contained property-test report importer contracts."""

from __future__ import annotations

import json
from pathlib import Path

from rush.tools.pbt import PbtTool


def test_pbt_imports_seeded_local_report_without_executing_tests(
    tmp_path: Path,
) -> None:
    report = tmp_path / "property-report.json"
    report.write_text(
        json.dumps(
            {
                "seed": 1234,
                "failures": [
                    {"property": "sort_is_ordered", "message": "counterexample"}
                ],
            }
        )
    )

    result = PbtTool().run(tmp_path, report_path=report)

    assert result["status"] == "fail"
    assert result["engine"] == "property-report"
    assert result["findings"][0]["rule"] == "property-failure"
    assert result["metadata"]["evidence_source"] == "imported-local-report"
    assert result["metadata"]["report_format"] == "property-json"
    assert result["metadata"]["seed"] == 1234
    assert result["metadata"]["execution"]["mode"] == "imported"


def test_pbt_rejects_missing_malformed_and_outside_reports(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-property.json"
    outside.write_text("{}")
    malformed = tmp_path / "bad-property.json"
    malformed.write_text("not-json")

    missing = PbtTool().run(tmp_path, report_path=tmp_path / "absent.json")
    bad = PbtTool().run(tmp_path, report_path=malformed)
    escaped = PbtTool().run(tmp_path, report_path=outside)

    assert [item["status"] for item in (missing, bad, escaped)] == [
        "skipped",
        "error",
        "error",
    ]
