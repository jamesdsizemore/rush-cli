"""Phase 04 contained Pact contract-report importer contracts."""

from __future__ import annotations

import json
from pathlib import Path

from rush.tools.contract import ContractTool


def test_contract_imports_local_pact_report_without_live_target(tmp_path: Path) -> None:
    report = tmp_path / "pact-report.json"
    report.write_text(json.dumps({"summary": {"errors": 1, "warnings": 0}}))

    result = ContractTool().run(tmp_path, report_path=report)

    assert result["status"] == "fail"
    assert result["engine"] == "pact-report"
    assert result["metrics"] == {"errors": 1, "warnings": 0}
    assert result["metadata"]["evidence_source"] == "imported-local-report"


def test_contract_rejects_missing_malformed_and_outside_reports(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-pact.json"
    outside.write_text("{}")
    malformed = tmp_path / "bad-pact.json"
    malformed.write_text("not-json")

    missing = ContractTool().run(tmp_path, report_path=tmp_path / "absent.json")
    bad = ContractTool().run(tmp_path, report_path=malformed)
    escaped = ContractTool().run(tmp_path, report_path=outside)

    assert [item["status"] for item in (missing, bad, escaped)] == [
        "skipped",
        "error",
        "error",
    ]
