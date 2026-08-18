"""Sloppylint JSON adapter for Python AI-slop analysis."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class SloppylintEngine(Engine):
    name = "sloppylint"
    binary = "sloppylint"
    file_extensions = ("py", "pyi")

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        proc = run_subprocess(
            [resolve_binary(self.binary) or self.binary, "--format", "json", *args],
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
                "path": issue.get("file", str(path)),
                "line": issue.get("line"),
                "rule": issue.get("pattern_id", "sloppylint"),
                "severity": "error"
                if issue.get("severity") in {"critical", "high"}
                else "warn",
                "message": issue.get("message", "AI slop detected"),
            }
            for issue in parsed.get("issues", [])
        ]
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="warn" if findings else "ok",
            duration_ms=0,
            summary=f"sloppylint: {len(findings)} issue(s)",
            findings=findings,
            raw=json.dumps(parsed),
        )
