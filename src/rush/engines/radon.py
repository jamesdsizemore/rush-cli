"""Radon adapter for Python cyclomatic-complexity analysis."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class RadonEngine(Engine):
    name = "radon"
    binary = "radon"
    file_extensions = ("py", "pyi")

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        proc = run_subprocess(
            [resolve_binary(self.binary) or self.binary, "cc", "--json", *args],
            cwd=cwd,
            timeout=120,
        )
        return EngineResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> dict:
        from ..tools.base import ToolResult

        try:
            parsed = json.loads(raw.get("stdout", "{}"))
        except json.JSONDecodeError:
            parsed = {}
        findings = [
            {
                "path": file,
                "line": item.get("lineno"),
                "rule": "radon",
                "severity": "warn",
                "message": f"{item.get('name', '<module>')}: complexity {item.get('complexity', 0)}",
            }
            for file, items in parsed.items()
            for item in items
            if item.get("complexity", 0) > 10
        ]
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="warn" if findings else "ok",
            duration_ms=0,
            summary=f"radon: {len(findings)} complex item(s)",
            findings=findings,
            raw=parsed,
        )
