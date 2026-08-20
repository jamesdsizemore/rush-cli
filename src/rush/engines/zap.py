"""OWASP ZAP CLI adapter for Dynamic Application Security Testing."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class ZapEngine(Engine):
    name = "zap"
    binary = "zap-cli"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        target = str(path) if str(path).startswith("http") else "http://localhost:8080"
        default_args = ["quick-scan", "--self-contained", "--format", "json", target]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=240)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "alerts" in parsed:
                    findings_raw = parsed["alerts"]
                elif isinstance(parsed, list):
                    findings_raw = parsed
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"zap exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            risk = item.get("risk", "Medium").lower()
            findings.append(
                {
                    "path": item.get("url", str(path)),
                    "line": 0,
                    "column": 0,
                    "rule": f"zap/{item.get('pluginId', 'alert')}",
                    "severity": "fail" if risk in ("high", "critical") else "warn",
                    "message": item.get("alert", "OWASP ZAP DAST vulnerability alert"),
                }
            )

        exit_code = raw.get("exit_code", 0)
        status = (
            "fail"
            if any(f["severity"] == "fail" for f in findings)
            else ("warn" if findings else ("ok" if exit_code == 0 else "error"))
        )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"zap: {len(findings)} DAST security finding(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
