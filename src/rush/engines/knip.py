"""Knip adapter for JavaScript and TypeScript dead-code analysis."""

from __future__ import annotations

import re
from pathlib import Path

from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class KnipEngine(Engine):
    name = "knip"
    binary = "knip"
    file_extensions = ("js", "jsx", "mjs", "cjs", "ts", "tsx")

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        proc = run_subprocess(
            [resolve_binary(self.binary) or self.binary, "--no-exit-code", *args],
            cwd=cwd,
            timeout=120,
        )
        return EngineResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> dict:
        from ..tools.base import ToolResult

        pattern = re.compile(r"^\s*(?P<name>.+?)\s{2,}(?P<path>.+?):(?P<line>\d+)\s*$")
        findings = []
        for line in raw.get("stdout", "").splitlines():
            match = pattern.match(line)
            if match:
                findings.append(
                    {
                        "path": match["path"],
                        "line": int(match["line"]),
                        "rule": "knip",
                        "severity": "warn",
                        "message": f"Unused export: {match['name']}",
                    }
                )
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="warn" if findings else "ok",
            duration_ms=0,
            summary=f"knip: {len(findings)} unused item(s)",
            findings=findings,
            raw=None,
        )
