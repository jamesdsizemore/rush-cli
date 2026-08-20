"""Terrascan adapter for IaC security and compliance policy scanning."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class TerrascanEngine(Engine):
    name = "terrascan"
    binary = "terrascan"
    file_extensions = ("tf", "yaml", "yml", "json")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["scan", "-i", "terraform", "-d", str(path), "-o", "json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=180)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "results" in parsed:
                    findings_raw = parsed["results"].get("violations", [])
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"terrascan exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            severity = item.get("severity", "MEDIUM").upper()
            findings.append(
                {
                    "path": item.get("file", str(path)),
                    "line": int(item.get("line", 0) or 0),
                    "column": 0,
                    "rule": item.get("rule_name")
                    or item.get("rule_id", "terrascan-policy"),
                    "severity": "fail" if severity in ("HIGH", "CRITICAL") else "warn",
                    "message": item.get("description", "Terrascan policy violation"),
                }
            )

        exit_code = raw.get("exit_code", 0)
        has_fail = any(f["severity"] == "fail" for f in findings)
        status = (
            "fail"
            if has_fail
            else ("warn" if findings else ("ok" if exit_code == 0 else "error"))
        )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"terrascan: {len(findings)} violation(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
