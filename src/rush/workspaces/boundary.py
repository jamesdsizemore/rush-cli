"""Cross-workspace illegal relative import guard."""

from __future__ import annotations

import re
from pathlib import Path

from rush.tools.base import Finding, ToolResult
from rush.workspaces.models import WorkspacePackage

ILLEGAL_IMPORT_REGEX = re.compile(
    r"(?:from|import)\s+[\"']" + r"(?:\.\./){2,}[^\"']*[\"']"
)


class WorkspaceBoundaryGuard:
    """Verifies that packages do not import from external workspace paths via relative traversal."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def check_package_boundaries(self, packages: list[WorkspacePackage]) -> ToolResult:
        findings: list[Finding] = []

        for pkg in packages:
            for src_file in pkg.root_path.rglob("*"):
                if (
                    src_file.is_file()
                    and src_file.suffix in (".py", ".ts", ".tsx", ".js", ".jsx")
                    and "node_modules" not in src_file.parts
                    and ".venv" not in src_file.parts
                ):
                    content = src_file.read_text(encoding="utf-8", errors="replace")
                    for line_idx, line in enumerate(content.splitlines(), start=1):
                        match = ILLEGAL_IMPORT_REGEX.search(line)
                        if match:
                            rel_path = (
                                src_file.relative_to(self.repo_root).as_posix()
                                if src_file.is_relative_to(self.repo_root)
                                else str(src_file)
                            )
                            findings.append(
                                {
                                    "path": rel_path,
                                    "line": line_idx,
                                    "column": 1,
                                    "rule": "workspace-boundary-violation",
                                    "severity": "fail",
                                    "message": f"Illegal cross-workspace relative import in '{src_file.name}' violates modular encapsulation.",
                                }
                            )

        return ToolResult(
            tool="workspace",
            engine="boundary_guard",
            engine_version="1.0",
            status="ok" if not findings else "fail",
            duration_ms=0,
            summary=f"Workspace boundary check: {len(packages)} packages scanned, {len(findings)} violations.",
            findings=findings,
        )
