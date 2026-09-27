"""Composite developer workflow suites (check, audit, gate).

Architecture §8, Phase 24.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from rush.config import RushConfig
from rush.invocation import InvocationExecutor, resolve_invocation
from rush.invocation.models import InvocationError
from rush.invocation.targets import RootSelection, assert_contained, select_root
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
    *,
    cancel_check: Callable[[], bool] | None = None,
    on_tool_complete: Callable[[ToolResult], None] | None = None,
    owner_instance_id: str = "",
    run_id: str = "",
    original_requested_targets: tuple[str, ...] | None = None,
    invocation_start_cwd: Path | None = None,
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

    P69-06f: wrapping this in status transitions alone gives a cancel request
    nothing to interrupt and leaves nothing durable behind mid-flight, so the
    capabilities live here instead:

    * `cancel_check` is polled *between* tools -- the suite returns promptly
      with whatever completed, marked `metadata["cancelled"] = True`, rather
      than only after the whole sequence has run.
    * `on_tool_complete` receives each finished child's `ToolResult` as it
      completes, so the caller can persist it under the job's own operation
      id and reconstruct a real partial aggregate from whatever landed
      before a cancel or a kill.
    * `owner_instance_id`/`run_id` travel into this function's own
      `resolve_invocation()` request exactly as `_execute_candidate` does
      (P69-01.2j) -- this is a separate invocation-construction site, so
      without them every subprocess a suite run spawns records no owner and
      Detach's force-exit/recovery reap path has nothing to act on.
    * `original_requested_targets` (T8) is never derived from `path` here --
      a caller may pass a value it already normalized (the dashboard passes
      its registered root), so only the caller's own supplied originals are
      recorded. Omitting it (the default) is explicitly "unavailable".
    * `path` is walked once, from `invocation_start_cwd` (default: the
      current working directory), by the shared ROOT-ENTRY walk
      (`select_root`); every step reuses that selection.
    """
    log_subsystem(
        "workflow", "INFO", f"Starting workflow suite '{suite.name}' on {path}"
    )

    anchor = invocation_start_cwd if invocation_start_cwd is not None else Path.cwd()
    # T8: walked exactly once for the whole suite; a rejected input becomes
    # each step's error child without re-resolving it.
    selection: RootSelection | None = None
    selection_error: Exception | None = None
    try:
        selection = select_root(str(path), anchor=anchor)
        assert_contained(selection)
    except (InvocationError, OSError, ValueError) as exc:
        selection_error = exc
    tools_by_name = {tool.name: tool for tool in ALL_TOOLS}
    children: list[ToolResult] = []
    executed_tools: list[str] = []
    cancelled = False

    for tool_name in suite.tool_sequence:
        if cancel_check is not None and cancel_check():
            cancelled = True
            log_subsystem(
                "workflow",
                "WARN",
                f"Workflow suite '{suite.name}' cancelled before '{tool_name}'",
            )
            break
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
            if selection is None:
                assert selection_error is not None
                raise selection_error
            executor = InvocationExecutor()
            executor.register(tool_name, tool.__call__)
            request: dict[str, object] = {
                "operation_id": tool_name,
                "path": selection.relative.as_posix(),
            }
            # P69-01.2j: structural ownership travels with the request, so
            # each tool's own `run_subprocess()` call is fenced and reapable.
            if owner_instance_id and run_id:
                request["owner_instance_id"] = owner_instance_id
                request["run_id"] = run_id
            context = resolve_invocation(
                request,
                transport="cli",
                workspace_root=selection.root,
                config=config,
                permissions=permissions,
                original_requested_targets=original_requested_targets,
                invocation_start_cwd=anchor,
            )
            res: ToolResult = executor.execute(context)
            children.append(res)
            executed_tools.append(tool_name)
            if on_tool_complete is not None:
                on_tool_complete(res)

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
        # P69-06f: the aggregate reconstructed from whichever children
        # actually completed is real partial evidence, explicitly labelled
        # as cancelled rather than silently presented as a full run.
        "cancelled": cancelled,
    }
    return aggregate
