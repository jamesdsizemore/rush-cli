"""Refurb adapter for Python syntax modernization and code elegance."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class RefurbEngine(Engine):
    name = "refurb"
    binary = "refurb"
    file_extensions = ("py", "pyi")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["--format", "json"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    findings_raw = parsed
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"refurb exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("path", str(path)),
                    "line": item.get("line", 0),
                    "column": item.get("column", 0),
                    "rule": f"refurb/{item.get('code', 'FURB')}",
                    "severity": "warn",
                    "message": item.get(
                        "message", "Python modernization recommendation"
                    ),
                    "fix": item.get("fix") or item.get("suggestion"),
                    "remediation": item.get("message"),
                }
            )

        exit_code = raw.get("exit_code", 0)
        status = "warn" if findings else ("ok" if exit_code == 0 else "error")

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"refurb: {len(findings)} modernization suggestion(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
