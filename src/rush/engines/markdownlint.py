"""markdownlint-cli2 adapter for non-mutating Markdown checks."""

from __future__ import annotations

from pathlib import Path

from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class MarkdownlintEngine(Engine):
    name = "markdownlint-cli2"
    binary = "markdownlint-cli2"
    file_extensions = ("md", "mdx")

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        proc = run_subprocess(
            [resolve_binary(self.binary) or self.binary, *args], cwd=cwd, timeout=120
        )
        return EngineResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> dict:
        from ..tools.base import ToolResult

        lines = [line for line in raw.get("stdout", "").splitlines() if line.strip()]
        findings = [
            {
                "path": str(path),
                "rule": "markdownlint",
                "severity": "warn",
                "message": line,
            }
            for line in lines
        ]
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="warn" if findings else "ok",
            duration_ms=0,
            summary=f"markdownlint: {len(findings)} issue(s)",
            findings=findings,
            raw=None,
        )
