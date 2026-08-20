"""Phase 00 result and evidence contract tests."""

from __future__ import annotations

from rush.tools.common import error_result, normalize_findings


def test_error_result_records_timeout_as_execution_metadata() -> None:
    result = error_result(
        "lint",
        "ruff",
        "timed out after 10s",
        terminal_reason="timeout",
        partial=True,
    )

    assert result["status"] == "error"
    assert result["metadata"] == {"terminal_reason": "timeout", "partial": True}


def test_normalize_findings_redacts_and_stably_identifies_findings() -> None:
    findings = normalize_findings(
        [
            {
                "path": "z.py",
                "line": 3,
                "column": 2,
                "rule_id": "Z001",
                "severity": "warn",
                "message": "token=secret-value",
            },
            {
                "path": "a.py",
                "line": 1,
                "rule_id": "A001",
                "severity": "error",
                "message": "problem",
            },
        ]
    )

    assert [finding["path"] for finding in findings] == ["a.py", "z.py"]
    assert findings[1]["rule_id"] == "Z001"
    assert findings[1]["fingerprint"]
    assert findings[1]["message"] == "token=[REDACTED]"
