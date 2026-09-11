"""Composite developer workflow suites (check, audit, gate).

Architecture §8, Phase 24.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rush.config import RushConfig
from rush.invocation import InvocationExecutor, resolve_invocation
from rush.logging import get_logger, log_subsystem
from rush.permissions import ExecutionPermissions
from rush.tools import ALL_TOOLS
from rush.tools.base import ToolResult
from rush.tools.common import error_result, skipped_result
from rush.tools.routing import aggregate_results

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
    """Execute a sequence of tools defined by a workflow suite and combine results.

    Every step in `suite.tool_sequence` produces exactly one retained child
    `ToolResult`: an unregistered tool name or a handler exception is recorded
    as a real `skipped`/`error` child, never silently dropped and never
    counted toward `executed_tools`. `InvocationExecutor.execute` already runs
    each child exactly once (zero retry on `TypeError` or any other
    exception); this loop does not add a second retry path. Overall
    status/findings reuse the canonical `aggregate_results` (Phase 65 P65-04)
    instead of a hand-rolled status merge, so suites and full-project scans
    share one aggregation rule and one child-metadata shape.
    """
    log_subsystem(
        "workflow", "INFO", f"Starting workflow suite '{suite.name}' on {path}"
    )

    tools_by_name = {tool.name: tool for tool in ALL_TOOLS}
    children: list[ToolResult] = []
    executed_tools: list[str] = []

    for tool_name in suite.tool_sequence:
        tool = tools_by_name.get(tool_name)
        if tool is None:
            children.append(
                skipped_result(tool_name, None, "not registered in ALL_TOOLS")
            )
            if fail_fast:
                break
            continue

        log_subsystem("workflow", "INFO", f"[{suite.name}] Running step: {tool_name}")
        try:
            executor = InvocationExecutor()
            executor.register(tool_name, tool.__call__)
            target = path.resolve()
            context = resolve_invocation(
                {"operation_id": tool_name, "path": str(target)},
                transport="cli",
                workspace_root=target if target.is_dir() else target.parent,
                config=config,
                permissions=permissions,
            )
            res: ToolResult = executor.execute(context)
            children.append(res)
            executed_tools.append(tool_name)

            if fail_fast and res["status"] in {"fail", "error"}:
                log_subsystem(
                    "workflow",
                    "WARN",
                    f"Workflow suite '{suite.name}' short-circuited on failure at '{tool_name}'",
                )
                break
        except Exception as exc:  # noqa: BLE001 -- one real child result, zero retry
            log_subsystem(
                "workflow", "ERROR", f"Tool {tool_name} failed with error: {exc}"
            )
            children.append(error_result(tool_name, None, str(exc)))
            if fail_fast:
                break

    aggregate = aggregate_results(suite.name, children)
    aggregate["summary"] = (
        f"{suite.name}: executed {len(executed_tools)} tool(s) "
        f"with status '{aggregate['status']}'"
    )
    aggregate["metadata"] = {
        "children": [
            {"tool": child.get("tool"), "status": child.get("status")}
            for child in children
        ],
        "executed_tools": tuple(executed_tools),
    }
    return aggregate
