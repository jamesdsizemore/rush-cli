"""Check tool -- the shared six-step check suite (Phase 70 T17).

One `CheckTool` runs `CHECK_SUITE` (format check-only, lint, typecheck,
dead, slop, test) through `run_workflow_suite`, so CLI `rush check`, MCP
`rush_check` and agent hooks share one implementation. It grants nothing on
its own: the test step runs only under an explicit build grant.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..invocation.models import InvocationContext
from ..permissions import ExecutionPermissions
from .base import ToolFn, ToolName, ToolResult


class CheckTool(ToolFn):
    name: ToolName = "check"

    @property
    def mcp_description(self) -> str:
        return (
            "Run the check suite at <path>: format (check-only), lint, typecheck, "
            "dead, slop, test; every step is reported. The test step needs "
            "allow_build."
        )

    def __call__(
        self,
        path: Path,
        fail_fast: bool = False,
        allow_network: bool = False,
        allow_download: bool = False,
        allow_cache_write: bool = False,
        allow_build: bool = False,
        allow_slow: bool = False,
        allow_artifact_write: bool = False,
        allow_browser: bool = False,
        context: InvocationContext | None = None,
    ) -> ToolResult:
        permissions = ExecutionPermissions(
            network=allow_network,
            download=allow_download,
            cache_write=allow_cache_write,
            build=allow_build,
            slow=allow_slow,
            artifact_write=allow_artifact_write,
            browser=allow_browser,
        )
        if context is None:
            return self.run(path, permissions=permissions, fail_fast=fail_fast)
        # The invocation's own originals, start cwd and owner travel into
        # every step, exactly as the caller supplied them.
        return self.run(
            path,
            permissions=permissions,
            fail_fast=fail_fast,
            owner_instance_id=context.owner_instance_id,
            run_id=context.run_id,
            original_requested_targets=context.original_requested_targets,
            invocation_start_cwd=context.invocation_start_cwd,
        )

    def run(
        self,
        path: Path,
        *,
        permissions: ExecutionPermissions | None = None,
        fail_fast: bool = False,
        cancel_check: Callable[[], bool] | None = None,
        cancel_cause: str = "cancelled",
        owner_instance_id: str = "",
        run_id: str = "",
        original_requested_targets: tuple[str, ...] | None = None,
        invocation_start_cwd: Path | None = None,
    ) -> ToolResult:
        """Run `CHECK_SUITE` on `path`. Omitted `permissions` grant nothing, so
        the test step is skipped."""
        # Imported here, not at module scope: `rush.workflows.suites` imports
        # `ALL_TOOLS`, which registers this tool.
        from ..workflows import suites

        return suites.run_workflow_suite(
            suites.CHECK_SUITE,
            path,
            permissions or ExecutionPermissions(),
            fail_fast=fail_fast,
            cancel_check=cancel_check,
            cancel_cause=cancel_cause,
            owner_instance_id=owner_instance_id,
            run_id=run_id,
            original_requested_targets=original_requested_targets,
            invocation_start_cwd=invocation_start_cwd,
        )
