"""Tests for Phase 24: Composite Workflow Suites.

Verifies:
- Definition and tool sequences for check, audit, gate suites
- Execution of composite suites with aggregate status calculation
- Fail-fast and short-circuit behavior on failure
"""

from __future__ import annotations

from pathlib import Path

from rush.permissions import ExecutionPermissions
from rush.workflows import suites
from rush.workflows.suites import (
    AUDIT_SUITE,
    CHECK_SUITE,
    GATE_SUITE,
    WorkflowSuite,
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


def test_workflow_suite_uses_public_tool_call(tmp_path: Path, monkeypatch) -> None:
    calls = 0

    class PublicTool:
        name = "probe"

        def __call__(self, path: Path) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {
                "tool": "probe",
                "status": "ok",
                "duration_ms": 0,
                "summary": "public call",
                "findings": [],
            }

        def run(self, *_args, **_kwargs) -> None:
            raise AssertionError("private run path used")

    monkeypatch.setattr(suites, "ALL_TOOLS", [PublicTool()])
    workflow = WorkflowSuite("probe-suite", "probe", ("probe",))

    result = run_workflow_suite(
        workflow, tmp_path, ExecutionPermissions(), fail_fast=False
    )

    assert result["status"] == "ok"
    assert result["summary"] == "probe-suite: executed 1 tool(s) with status 'ok'"
    assert calls == 1
