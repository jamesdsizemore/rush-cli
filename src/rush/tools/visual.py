"""Visual regression tool."""

from __future__ import annotations

import shutil
from pathlib import Path

from .base import ToolResult
from .common import elapsed_ms, now_ms, run_subprocess, skipped_result
from .quality import GuardedQualityTool


class VisualTool(GuardedQualityTool):
    name = "visual"
    required_option = "accept"
    default_reason = "visual baselines are never updated by default"

    @property
    def mcp_description(self):
        return "Check visual baselines; updates require --accept."

    def run(
        self,
        path: Path,
        *,
        accept: bool = False,
        config=None,
        permissions=None,
        **options: object,
    ) -> ToolResult:
        from ..permissions import (
            ExecutionPermissions,
            build_execution_metadata,
        )

        start = now_ms()
        has_accept = accept or bool(options.get("accept"))
        if not has_accept and permissions is not None:
            has_accept = getattr(permissions, "artifact_write", False)

        if not has_accept:
            return skipped_result(
                self.name,
                None,
                f"{self.default_reason}; pass --accept",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=ExecutionPermissions(artifact_write=True),
                        granted=permissions,
                    )
                },
            )

        visual_bin = shutil.which("lost-pixel") or shutil.which("backstop")
        if not visual_bin:
            return skipped_result(
                self.name,
                "lost-pixel",
                "visual: Visual regression engine (lost-pixel/backstop) not found on PATH.",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        granted=permissions,
                    )
                },
            )

        proc = run_subprocess(
            [visual_bin, "test"],
            cwd=path if path.is_dir() else path.parent,
            timeout=180.0,
        )
        status = "ok" if proc.returncode == 0 else "fail"
        return ToolResult(
            tool=self.name,
            engine=Path(visual_bin).stem,
            engine_version="1.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=f"visual: Visual regression tests completed with status '{status}'.",
            findings=[],
            raw=proc.stdout,
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    granted=permissions,
                )
            },
        )
