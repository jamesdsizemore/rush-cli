"""Tests for SARIF 2.1.0 export utilities."""

from __future__ import annotations

from rush.sarif import export_to_sarif, finding_to_sarif_result
from rush.tools.base import Finding, ToolResult


def test_finding_to_sarif_result():
    finding = Finding(
        path="src/app.py",
        line=42,
        rule="no-eval",
        severity="fail",
        message="Use of eval is prohibited",
        fix="literal_eval()",
    )
    sarif_res = finding_to_sarif_result(finding)
    assert sarif_res["ruleId"] == "no-eval"
    assert sarif_res["level"] == "error"
    assert sarif_res["message"]["text"] == "Use of eval is prohibited"
    assert sarif_res["locations"][0]["physicalLocation"]["region"]["startLine"] == 42
    assert (
        sarif_res["fixes"][0]["changes"][0]["replacement"]["text"] == "literal_eval()"
    )


def test_export_to_sarif():
    result: ToolResult = {
        "tool": "security",
        "engine": "semgrep",
        "engine_version": "1.0.0",
        "status": "fail",
        "duration_ms": 120,
        "summary": "1 security issue found",
        "findings": [
            Finding(
                path="src/auth.py",
                line=10,
                rule="hardcoded-secret",
                severity="fail",
                message="Potential hardcoded secret",
            )
        ],
        "raw": None,
        "metadata": {},
    }

    doc = export_to_sarif(result)
    assert doc["version"] == "2.1.0"
    assert len(doc["runs"]) == 1
    run = doc["runs"][0]
    assert run["tool"]["driver"]["name"] == "semgrep"
    assert len(run["results"]) == 1
    assert run["results"][0]["ruleId"] == "hardcoded-secret"
