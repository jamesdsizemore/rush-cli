"""Shared safety guards for expensive test-quality tools."""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, now_ms, skipped_result


class GuardedQualityTool(ToolFn):
    """Safe default for optional quality workflows before engine execution."""

    required_option: str | None = None
    default_reason: str = "requires configured project command"

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
        **options: object,
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
        return self.run(path, permissions=permissions, **options)

    def run(
        self,
        path: Path,
        *,
        config=None,
        permissions=None,
        **options: object,
    ) -> ToolResult:
        from ..permissions import (
            ExecutionPermissions,
            build_execution_metadata,
        )

        start = now_ms()
        has_required = False
        if self.required_option:
            if options.get(self.required_option):
                has_required = True
            elif permissions is not None:
                perm_field = self.required_option.replace("allow_", "")
                if getattr(permissions, perm_field, False):
                    has_required = True

        if self.required_option and not has_required:
            req_perms = (
                ExecutionPermissions(browser=True)
                if self.required_option == "allow_browser"
                else (
                    ExecutionPermissions(artifact_write=True)
                    if self.required_option == "accept"
                    else ExecutionPermissions()
                )
            )
            result = skipped_result(
                self.name,
                None,
                f"{self.default_reason}; pass --{self.required_option.replace('_', '-')}",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=req_perms,
                        granted=permissions,
                    )
                },
            )
            return result

        result = skipped_result(
            self.name,
            None,
            self.default_reason,
            duration_ms=elapsed_ms(start),
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    granted=permissions,
                )
            },
        )
        return result
