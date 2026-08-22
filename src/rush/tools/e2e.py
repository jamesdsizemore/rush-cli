"""End-to-end test tool."""

from __future__ import annotations

from pathlib import Path

from .base import ToolResult
from .common import elapsed_ms, now_ms, resolve_binary, run_subprocess, skipped_result
from .quality import GuardedQualityTool


class E2eTool(GuardedQualityTool):
    name = "e2e"
    required_option = "allow_browser"
    default_reason = "browser execution is disabled by default"

    @property
    def mcp_description(self):
        return "Run configured E2E tests only with --allow-browser."

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
        has_browser = False
        if (
            options.get("allow_browser")
            or permissions is not None
            and getattr(permissions, "browser", False)
        ):
            has_browser = True

        if not has_browser:
            return skipped_result(
                self.name,
                None,
                f"{self.default_reason}; pass --allow-browser",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=ExecutionPermissions(browser=True),
                        granted=permissions,
                    )
                },
            )

        playwright_bin = resolve_binary("playwright")
        if not playwright_bin:
            return skipped_result(
                self.name,
                "playwright",
                "e2e: Playwright not found on PATH.",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        granted=permissions,
                    )
                },
            )

        proc = run_subprocess(
            ["playwright", "test"],
            cwd=path if path.is_dir() else path.parent,
            timeout=180.0,
        )
        status = "ok" if proc.returncode == 0 else "fail"
        return ToolResult(
            tool=self.name,
            engine="playwright",
            engine_version="1.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=f"e2e: Playwright test suite completed with status '{status}'.",
            findings=[],
            raw=proc.stdout,
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    granted=permissions,
                )
            },
        )
