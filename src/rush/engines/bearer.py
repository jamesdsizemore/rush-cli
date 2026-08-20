"""Bearer adapter for privacy, PII, and sensitive data flow SAST analysis."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class BearerEngine(Engine):
    name = "bearer"
    binary = "bearer"
    file_extensions = ("py", "js", "jsx", "ts", "tsx", "rb", "java", "go", "php")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = [
            "scan",
            "--format",
            "json",
            "--output",
            "bearer-report.json",
            "--quiet",
            "--disable-version-check",
        ]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=240)

        parsed = None
        report_file = (cwd or path) / "bearer-report.json"
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
        if isinstance(parsed, dict):
            for severity in ("critical", "high", "medium", "low", "warning"):
                findings_raw.extend(parsed.get(severity, []))

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"bearer exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("filename", str(path)),
                    "line": item.get("line_number", 0),
                    "column": item.get("column_number", 0),
                    "rule": item.get("cwe_ids", ["privacy-finding"])[0]
                    if item.get("cwe_ids")
                    else "privacy-finding",
                    "severity": "fail"
                    if item.get("severity") in ("critical", "high")
                    else "warn",
                    "message": item.get("title")
                    or item.get("description", "Sensitive data flow finding"),
                }
            )

        exit_code = raw.get("exit_code", 0)
        has_errors = any(f["severity"] == "fail" for f in findings)
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
            summary=f"bearer: {len(findings)} finding(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
