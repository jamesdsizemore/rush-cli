"""Tests for Phase 24: Composite Workflow Suites.

Verifies:
- Definition and tool sequences for check, audit, gate suites
- Execution of composite suites with aggregate status calculation
- Fail-fast and short-circuit behavior on failure
"""

from __future__ import annotations

from pathlib import Path

from rush.config import RushConfig
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


def test_suite_retains_child_results_and_skips(tmp_path: Path, monkeypatch) -> None:
    """An unregistered step is a real, visible `skipped` child -- never a
    silent drop, and never counted in `executed_tools`."""

    class RealTool:
        name = "real"

        def __call__(self, path: Path) -> dict[str, object]:
            return {
                "tool": "real",
                "status": "ok",
                "duration_ms": 0,
                "summary": "real: ok",
                "findings": [],
            }

    monkeypatch.setattr(suites, "ALL_TOOLS", [RealTool()])
    workflow = WorkflowSuite("mixed", "mixed", ("real", "missing-tool"))

    result = run_workflow_suite(workflow, tmp_path, ExecutionPermissions())

    children = result["metadata"]["children"]
    assert [child["tool"] for child in children] == ["real", "missing-tool"]
    assert children[0]["status"] == "ok"
    assert children[1]["status"] == "skipped"
    assert result["metadata"]["executed_tools"] == ("real",)


def test_tool_typeerror_runs_once(tmp_path: Path, monkeypatch) -> None:
    """A handler `TypeError` surfaces as one real `error` child -- the
    handler runs exactly once, with zero exception-based retry."""

    calls = 0

    class BrokenTool:
        name = "broken"

        def __call__(self, path: Path) -> dict[str, object]:
            nonlocal calls
            calls += 1
            raise TypeError("boom")

    monkeypatch.setattr(suites, "ALL_TOOLS", [BrokenTool()])
    workflow = WorkflowSuite("broken-suite", "broken", ("broken",))

    result = run_workflow_suite(workflow, tmp_path, ExecutionPermissions())

    assert calls == 1
    assert result["status"] == "error"
    assert result["metadata"]["children"] == [{"tool": "broken", "status": "error"}]
    assert result["metadata"]["executed_tools"] == ()


def test_config_reaches_each_child(tmp_path: Path, monkeypatch) -> None:
    """The same `config` object passed to `run_workflow_suite` reaches
    `resolve_invocation` for every child in the sequence, not just the
    first."""

    seen_configs: list[object] = []
    real_resolve_invocation = suites.resolve_invocation

    def spy_resolve_invocation(request, **kwargs):
        seen_configs.append(kwargs.get("config"))
        return real_resolve_invocation(request, **kwargs)

    class RealTool:
        def __init__(self, name: str) -> None:
            self.name = name

        def __call__(self, path: Path) -> dict[str, object]:
            return {
                "tool": self.name,
                "status": "ok",
                "duration_ms": 0,
                "summary": f"{self.name}: ok",
                "findings": [],
            }

    monkeypatch.setattr(suites, "ALL_TOOLS", [RealTool("one"), RealTool("two")])
    monkeypatch.setattr(suites, "resolve_invocation", spy_resolve_invocation)
    workflow = WorkflowSuite("cfg-suite", "cfg", ("one", "two"))
    sentinel_config = RushConfig()

    run_workflow_suite(
        workflow, tmp_path, ExecutionPermissions(), config=sentinel_config
    )

    assert len(seen_configs) == 2
    assert seen_configs[0] is sentinel_config
    assert seen_configs[1] is sentinel_config
