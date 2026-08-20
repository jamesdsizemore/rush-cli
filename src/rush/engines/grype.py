"""Grype vulnerability scanner adapter."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class GrypeEngine(Engine):
    name = "grype"
    binary = "grype"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["dir:.", "--output", "json", "-q"]
        argv = [binary_path, *default_args, *args]
        proc = run_subprocess(argv, cwd=cwd or path, timeout=180)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "matches" in parsed:
                    findings_raw = parsed["matches"]
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"grype exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            vuln = item.get("vulnerability", {})
            artifact = item.get("artifact", {})
            sev = vuln.get("severity", "").upper()
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "rule": vuln.get("id", "grype-vuln"),
                    "severity": "error" if sev in {"CRITICAL", "HIGH"} else "warn",
                    "message": f"{artifact.get('name')} {artifact.get('version')}: {vuln.get('description') or vuln.get('id')}",
                }
            )

        exit_code = raw.get("exit_code", 0)
        has_errors = any(f["severity"] == "error" for f in findings)
        status = (
            "fail"
            if has_errors
            else ("warn" if findings else ("ok" if exit_code == 0 else "error"))
        )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"grype: {len(findings)} vulnerability match(es)",
            findings=findings,
            raw=raw.get("parsed"),
        )
