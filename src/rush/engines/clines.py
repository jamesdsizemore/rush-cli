"""Clines adapter for terminal codebase metrics and LLM token estimation."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class ClinesEngine(Engine):
    name = "clines"
    binary = "clines"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["--json"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "metrics" in parsed:
                    findings_raw = parsed.get("warnings", [])
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"clines exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("file", str(path)),
                    "line": item.get("line", 0),
                    "column": 0,
                    "rule": f"clines/{item.get('kind', 'metric-anomaly')}",
                    "severity": "warn",
                    "message": item.get(
                        "message", "High complexity or token density anomaly"
                    ),
                    "fix": None,
                    "remediation": item.get("remediation"),
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
            summary=f"clines: {len(findings)} metric observation(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
