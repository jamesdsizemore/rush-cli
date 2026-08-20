"""Deadfinder adapter for scanning web services for 404s and dead routes."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class DeadfinderEngine(Engine):
    name = "deadfinder"
    binary = "deadfinder"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        target = str(path) if str(path).startswith("http") else "http://localhost:3000"
        default_args = [target, "--json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    findings_raw = parsed
            except json.JSONDecodeError:
                for line in proc.stdout.splitlines():
                    if line.strip():
                        findings_raw.append({"url": line.strip(), "status": 404})

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"deadfinder exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("url", str(path)),
                    "line": 0,
                    "column": 0,
                    "rule": "deadfinder/broken-link",
                    "severity": "warn",
                    "message": f"Broken web route or 404 link: {item.get('url')} (status {item.get('status', 'dead')})",
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
            summary=f"deadfinder: {len(findings)} broken route(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
