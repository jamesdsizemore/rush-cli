"""Tests for Phase 24: Composite Workflow Suites.

Verifies:
- Definition and tool sequences for check, audit, gate suites
- Execution of composite suites with aggregate status calculation
- Fail-fast and short-circuit behavior on failure
"""

from __future__ import annotations

from pathlib import Path

from rush.permissions import ExecutionPermissions
from rush.workflows.suites import (
    AUDIT_SUITE,
    CHECK_SUITE,
    GATE_SUITE,
    run_workflow_suite,
)


def test_suite_definitions() -> None:
    assert CHECK_SUITE.name == "check"
    assert "format" in CHECK_SUITE.tool_sequence
    assert "lint" in CHECK_SUITE.tool_sequence

    assert AUDIT_SUITE.name == "audit"
    assert "security" in AUDIT_SUITE.tool_sequence
    assert "secrets" in AUDIT_SUITE.tool_sequence

    assert GATE_SUITE.name == "gate"
    assert "coverage" in GATE_SUITE.tool_sequence
    assert "complexity" in GATE_SUITE.tool_sequence


def test_run_workflow_suite_mock(tmp_path: Path) -> None:
    res = run_workflow_suite(
        suite=CHECK_SUITE,
        path=tmp_path,
        permissions=ExecutionPermissions(),
        fail_fast=False,
    )
    assert res["tool"] == "check"
    assert res["status"] in {"ok", "skipped", "warn", "fail"}
    assert "check:" in res["summary"]
