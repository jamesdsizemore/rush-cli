"""Composite developer workflow suites (check, audit, gate).

Architecture §8, Phase 24.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rush.config import RushConfig, RushConfigError, load_config
from rush.invocation import InvocationExecutor, resolve_invocation
from rush.invocation.models import InvocationError
from rush.invocation.targets import RootSelection, assert_contained, select_root
from rush.logging import get_logger, log_subsystem
from rush.permissions import ExecutionPermissions, build_execution_metadata
from rush.runtime.subprocesses import SubprocessCancelled, cancel_scope
from rush.tools import ALL_TOOLS
from rush.tools.base import ToolResult
from rush.tools.common import error_result, skipped_result
from rush.tools.routing import aggregate_results, aggregate_status, child_entry

logger = get_logger("workflows.suites")


@dataclass(frozen=True)
class WorkflowSuite:
    name: str
    description: str
    tool_sequence: tuple[str, ...]
    fail_fast_default: bool = False


# Phase 70 T17 (D5): six steps, run-all by default; `test` stays build-gated.
CHECK_SUITE = WorkflowSuite(
    name="check",
    description=(
        "Fast inner-loop sanity check (format, lint, typecheck, dead, slop, test)."
    ),
    tool_sequence=("format", "lint", "typecheck", "dead", "slop", "test"),
    fail_fast_default=False,
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


def _suite_metadata(
    aggregate: ToolResult, selection: RootSelection | None
) -> dict[str, Any]:
    """T16 §3 item 3: the aggregation's engines and scope, the scope naming
    the suite's own target."""
    metadata = dict(aggregate.get("metadata") or {})
    if selection is not None:
        metadata["scope"] = {
            **metadata.get("scope", {}),
            "logical_root": str(selection.root),
            "requested_targets": [selection.relative.as_posix()],
        }
    return metadata


def memory_summary_clause(memory: Mapping[str, Any] | None) -> str | None:
    """T21: the neutral count of an already-deduplicated `metadata.memory`
    union, or `None` when nothing was read or written. Never recalls."""
    used = len((memory or {}).get("used") or [])
    written = len((memory or {}).get("written") or [])
    if not used and not written:
        return None
    return (
        f"memory: read {used} prior record{'s' if used != 1 else ''}, "
        f"wrote {written} record{'s' if written != 1 else ''}"
    )


def _step_outcome(
    tool_name: str, disposition: str, cause: str, summary: str
) -> ToolResult:
    """T17 S17.2: a step that never ran (`not_run`) or was stopped mid-run
    (`cancelled`) -- `skipped`, with the disposition and its cause."""
    return skipped_result(
        tool_name,
        None,
        summary,
        metadata={
            "execution": build_execution_metadata(
                "executed", extra={"disposition": disposition, "cause": cause}
            )
        },
    )


def _mark_cancelled(result: ToolResult, cause: str) -> ToolResult:
    """T17: a step whose engine child was cancelled mid-run keeps its partial
    result, recorded as `cancelled` rather than executed."""
    metadata = dict(result.get("metadata") or {})
    metadata["execution"] = {
        **(metadata.get("execution") or {}),
        "disposition": "cancelled",
        "cause": cause,
    }
    result["metadata"] = metadata
    return result


def run_workflow_suite(
    suite: WorkflowSuite,
    path: Path,
    permissions: ExecutionPermissions,
    config: RushConfig | None = None,
    fail_fast: bool = False,
    *,
    cancel_check: Callable[[], bool] | None = None,
    cancel_cause: str = "cancelled",
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

    * `cancel_check` is polled *between* tools, and (T17, finding 17) is
      ambient inside each step, so a step's in-flight engine child is
      terminated mid-step. The stopped step is a `cancelled` child, every
      later step a `not_run` child with `cause=cancel_cause`, and the result
      is marked `metadata["cancelled"] = True` with a status of at least
      `warn` -- never a clean success.
    * T17 S17.2: every step yields exactly one child. After a fail-fast stop
      the remaining steps are `not_run` with `cause="fail_fast_after:<step>"`.
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
    if config is None and selection is not None:
        # T21 (G4): as single-tool CLI/MCP calls do, so `[tools.memory]
        # record` applies inside a suite; a malformed `rush.toml` fails open.
        try:
            config = load_config(start=selection.root)
        except RushConfigError:
            config = None
    tools_by_name = {tool.name: tool for tool in ALL_TOOLS}
    children: list[ToolResult] = []
    executed_tools: list[str] = []
    cancelled = False
    # T17 S17.2: once set, every remaining step is a `not_run` child.
    stop_cause: str | None = None

    for tool_name in suite.tool_sequence:
        if stop_cause is None and cancel_check is not None and cancel_check():
            cancelled = True
            stop_cause = cancel_cause
            log_subsystem(
                "workflow",
                "WARN",
                f"Workflow suite '{suite.name}' cancelled before '{tool_name}'",
            )
        if stop_cause is not None:
            children.append(_step_outcome(tool_name, "not_run", stop_cause, "not run"))
            continue
        tool = tools_by_name.get(tool_name)
        if tool is None:
            children.append(
                skipped_result(tool_name, None, "not registered in ALL_TOOLS")
            )
            if fail_fast:
                stop_cause = f"fail_fast_after:{tool_name}"
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
            with cancel_scope(cancel_check, cancel_cause) as scope:
                res: ToolResult = executor.execute(context)
            if scope is not None and scope.hit:
                cancelled = True
                stop_cause = cancel_cause
                res = _mark_cancelled(res, cancel_cause)
            children.append(res)
            # T9: a step the executor refused to run (e.g. a missing target)
            # is a retained child, never counted as executed; nor is a step
            # cancelled before it finished (T17).
            execution = (res.get("metadata") or {}).get("execution") or {}
            ran = execution.get("disposition") not in ("not_run", "cancelled")
            if ran:
                executed_tools.append(tool_name)
            if on_tool_complete is not None:
                on_tool_complete(res)

            if stop_cause is None and fail_fast and res["status"] in {"fail", "error"}:
                # T9: a refused step is an input error, not a tool failure --
                # recorded in the result, not warned about as one.
                log_subsystem(
                    "workflow",
                    "WARN" if ran else "INFO",
                    f"Workflow suite '{suite.name}' short-circuited on failure at '{tool_name}'"
                    if ran
                    else f"Workflow suite '{suite.name}' stopped: '{tool_name}' was not run",
                )
                stop_cause = f"fail_fast_after:{tool_name}"
        except SubprocessCancelled:
            # T17 (finding 17): the step's own child was terminated mid-run.
            log_subsystem(
                "workflow",
                "WARN",
                f"Workflow suite '{suite.name}' cancelled during '{tool_name}'",
            )
            cancelled = True
            stop_cause = cancel_cause
            children.append(
                _step_outcome(
                    tool_name,
                    "cancelled",
                    cancel_cause,
                    f"cancelled before {tool_name} finished",
                )
            )
        except Exception as exc:  # noqa: BLE001 -- one real child result, zero retry
            log_subsystem(
                "workflow", "ERROR", f"Tool {tool_name} failed with error: {exc}"
            )
            children.append(error_result(tool_name, None, str(exc)))
            if fail_fast:
                stop_cause = f"fail_fast_after:{tool_name}"

    aggregate = aggregate_results(suite.name, children)
    if cancelled:
        # T17 S17.2: a cancelled run is never a clean result -- at least warn.
        aggregate["status"] = aggregate_status([aggregate["status"], "warn"])
    aggregate["summary"] = (
        f"{suite.name}: executed {len(executed_tools)} tool(s) "
        f"with status '{aggregate['status']}'"
    )
    # T16 §3 item 3: engines and scope from the aggregation, plus one full
    # entry per child; the aggregate scope names the suite's own target.
    aggregate["metadata"] = {
        **_suite_metadata(aggregate, selection),
        "children": [child_entry(child) for child in children],
        "executed_tools": tuple(executed_tools),
        # P69-06f: the aggregate reconstructed from whichever children
        # actually completed is real partial evidence, explicitly labelled
        # as cancelled rather than silently presented as a full run.
        "cancelled": cancelled,
    }
    clause = memory_summary_clause((aggregate.get("metadata") or {}).get("memory"))
    if clause is not None:
        aggregate["summary"] += f"; {clause}"
    return aggregate
