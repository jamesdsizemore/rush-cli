"""Cherrybomb adapter for OpenAPI specification security and OWASP Top 10 auditing."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class CherrybombEngine(Engine):
    name = "cherrybomb"
    binary = "cherrybomb"
    file_extensions = ("json", "yaml", "yml")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = [
            "--file",
            str(path),
            "--format",
            "json",
            "--output",
            "cherrybomb-report.json",
        ]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        report_file = (cwd or path) / "cherrybomb-report.json"
        if report_file.exists():
            try:
                parsed = json.loads(report_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                parsed = None
        elif proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
            except json.JSONDecodeError:
                parsed = None

        findings_raw: list[dict] = []
        if isinstance(parsed, dict) and "alerts" in parsed:
            findings_raw = parsed["alerts"]
        elif isinstance(parsed, list):
            findings_raw = parsed

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"cherrybomb exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            level = item.get("level", "medium").lower()
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": f"cherrybomb/{item.get('check_id', 'api-vuln')}",
                    "severity": "fail" if level in ("critical", "high") else "warn",
                    "message": item.get("description", "OpenAPI security flaw"),
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
            summary=f"cherrybomb: {len(findings)} OpenAPI security finding(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
