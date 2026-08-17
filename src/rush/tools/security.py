"""Security tool — engine dispatch per project type.

Architecture §4.3. Phase 3 stub. Phase 4 will detect pyproject.toml vs
package.json and dispatch to pip-audit / npm audit.
"""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolName, ToolResult
from .common import elapsed_ms, now_ms


class SecurityTool(ToolFn):
    name: ToolName = "security"

    @property
    def mcp_description(self) -> str:
        return (
            "Scan deps at <path> for known vulnerabilities. Returns {status, findings[], summary}. "
            "Engines: pip-audit (Python), npm audit (JS/TS). status='skipped' means engine not on PATH."
        )

    def __call__(self, path: Path) -> ToolResult:
        return self.run(path)

    def run(self, path: Path, *, config=None) -> ToolResult:
        # Phase 3 stub. Phase 4 will detect project type and dispatch.
        start = now_ms()
        return ToolResult(
            tool="security",
            engine=None,
            engine_version=None,
            status="skipped",
            duration_ms=elapsed_ms(start),
            summary=f"security: stub (Phase 4 will detect + run pip-audit/npm audit for {path})",
            findings=[],
            raw=None,
        )
