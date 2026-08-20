"""Composite developer workflow suites (check, audit, gate).

Architecture §8, Phase 24.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rush.config import RushConfig
from rush.logging import get_logger, log_subsystem
from rush.permissions import ExecutionPermissions
from rush.tools import ALL_TOOLS
from rush.tools.base import ToolResult, ToolStatus

logger = get_logger("workflows.suites")


@dataclass(frozen=True)
class WorkflowSuite:
    name: str
    description: str
    tool_sequence: tuple[str, ...]
    fail_fast_default: bool = False


CHECK_SUITE = WorkflowSuite(
    name="check",
    description="Fast inner-loop sanity check (format, lint, typecheck, dead, slop).",
    tool_sequence=("format", "lint", "typecheck", "dead", "slop"),
    fail_fast_default=True,
)

AUDIT_SUITE = WorkflowSuite(
    name="audit",
    description="Security and supply chain audit (security, secrets, sbom, iac, containerfile).",
    tool_sequence=("security", "secrets", "sbom", "iac", "containerfile"),
    fail_fast_default=False,
)

GATE_SUITE = WorkflowSuite(
    name="gate",
    description="Full pre-merge release gate (test, coverage, complexity, tdd, audit).",
    tool_sequence=("test", "coverage", "complexity", "tdd", "security", "secrets"),
    fail_fast_default=True,
)


def run_workflow_suite(
    suite: WorkflowSuite,
    path: Path,
    permissions: ExecutionPermissions,
    config: RushConfig | None = None,
    fail_fast: bool = False,
) -> ToolResult:
    """Execute a sequence of tools defined by a workflow suite and combine results."""
    log_subsystem(
        "workflow", "INFO", f"Starting workflow suite '{suite.name}' on {path}"
    )

    tools_by_name = {tool.name: tool for tool in ALL_TOOLS}
    findings = []
    statuses: list[ToolStatus] = []
    executed_tools = []

    for tool_name in suite.tool_sequence:
        tool = tools_by_name.get(tool_name)
        if not tool:
            continue

        log_subsystem("workflow", "INFO", f"[{suite.name}] Running step: {tool_name}")
        try:
            try:
                res: ToolResult = tool.run(path, config=config, permissions=permissions)
            except TypeError:
                res = tool.run(path, config=config)

            statuses.append(res["status"])
            findings.extend(res.get("findings") or [])
            executed_tools.append(tool_name)

            if fail_fast and res["status"] in {"fail", "error"}:
                log_subsystem(
                    "workflow",
                    "WARN",
                    f"Workflow suite '{suite.name}' short-circuited on failure at '{tool_name}'",
                )
                break
        except Exception as exc:  # noqa: BLE001
            log_subsystem(
                "workflow", "ERROR", f"Tool {tool_name} failed with error: {exc}"
            )
            statuses.append("error")
            if fail_fast:
                break

    # Aggregate status
    if "error" in statuses:
        overall: ToolStatus = "error"
    elif "fail" in statuses:
        overall = "fail"
    elif "warn" in statuses:
        overall = "warn"
    elif "ok" in statuses:
        overall = "ok"
    else:
        overall = "skipped"

    return ToolResult(
        tool=suite.name,
        status=overall,
        duration_ms=0,
        summary=f"{suite.name}: executed {len(executed_tools)} tool(s) with status '{overall}'",
        findings=findings,
    )
