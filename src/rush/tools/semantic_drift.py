"""Semantic-drift detector with explicit browser runtime execution guards."""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolName, ToolResult
from .common import elapsed_ms, engine_on_path, now_ms, run_subprocess


class SemanticDriftTool(ToolFn):
    """Guard browser/.NET drift detection behind explicit consent."""

    name: ToolName = "semantic-drift"

    @property
    def mcp_description(self) -> str:
        return (
            "Semantic drift detection comparing rendered DOM/accessibility against baseline. "
            "Requires both --allow-browser and --allow-slow."
        )

    def __call__(
        self,
        path: Path,
        *,
        allow_network: bool = False,
        allow_download: bool = False,
        allow_cache_write: bool = False,
        allow_build: bool = False,
        allow_slow: bool = False,
        allow_artifact_write: bool = False,
        allow_browser: bool = False,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions

        permissions = ExecutionPermissions(
            network=allow_network,
            download=allow_download,
            cache_write=allow_cache_write,
            build=allow_build,
            slow=allow_slow,
            artifact_write=allow_artifact_write,
            browser=allow_browser,
        )
        return self.run(path, permissions=permissions)

    def run(
        self,
        path: Path,
        *,
        allow_browser: bool = False,
        allow_slow: bool = False,
        config=None,
        permissions=None,
    ) -> ToolResult:
        from ..permissions import (
            ExecutionPermissions,
            build_execution_metadata,
            check_permissions,
        )

        start = now_ms()
        effective_perms = permissions
        if effective_perms is None and (allow_browser or allow_slow):
            effective_perms = ExecutionPermissions(
                browser=allow_browser, slow=allow_slow
            )

        required_perms = ExecutionPermissions(browser=True, slow=True)
        is_satisfied, _missing_perms = check_permissions(
            required_perms, effective_perms
        )
        if not is_satisfied:
            return ToolResult(
                tool=self.name,
                engine="semantic-drift",
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=(
                    "semantic drift is experimental; pass both --allow-browser and "
                    "--allow-slow to permit configured local analysis"
                ),
                findings=[],
                raw=None,
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=effective_perms,
                    )
                },
            )

        if not engine_on_path("playwright"):
            return ToolResult(
                tool=self.name,
                engine="semantic-drift",
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary="semantic drift needs a configured local .NET or Playwright target",
                findings=[],
                raw=None,
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=effective_perms,
                        producer="semantic-drift",
                    )
                },
            )

        proc = run_subprocess(
            ["playwright", "test", "--grep", "@drift", str(path)],
            cwd=path if path.is_dir() else path.parent,
            timeout=180,
        )
        return ToolResult(
            tool=self.name,
            engine="playwright",
            engine_version=None,
            status="ok" if proc.returncode == 0 else "warn",
            duration_ms=elapsed_ms(start),
            summary=f"semantic-drift: analysis complete (exit {proc.returncode})",
            findings=[],
            raw=proc.stdout,
            metadata={
                "evidence_source": "browser-runtime",
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_perms,
                    granted=effective_perms,
                    producer="playwright",
                ),
            },
        )
