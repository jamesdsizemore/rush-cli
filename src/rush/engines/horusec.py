"""Horusec adapter for multi-language static code analysis."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class HorusecEngine(Engine):
    name = "horusec"
    binary = "horusec"
    file_extensions = (
        "py",
        "js",
        "jsx",
        "ts",
        "tsx",
        "go",
        "java",
        "c",
        "cpp",
        "rb",
        "php",
        "tf",
        "yaml",
    )

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = [
            "start",
            "-p",
            str(path),
            "-o",
            "json",
            "-O",
            "horusec-result.json",
            "-s",
            "LOW",
            "-D",
        ]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=240)

        parsed = None
        report_file = (cwd or path) / "horusec-result.json"
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
        if isinstance(parsed, dict) and "analysisVulnerabilities" in parsed:
            for vuln_item in parsed.get("analysisVulnerabilities", []):
                vuln = vuln_item.get("vulnerabilities", {})
                if vuln:
                    findings_raw.append(vuln)

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"horusec exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            severity = item.get("severity", "LOW").upper()
            findings.append(
                {
                    "path": item.get("file", str(path)),
                    "line": int(item.get("line", 0) or 0),
                    "column": int(item.get("column", 0) or 0),
                    "rule": item.get("rule_id") or item.get("type", "horusec-vuln"),
                    "severity": "fail" if severity in ("CRITICAL", "HIGH") else "warn",
                    "message": item.get("details", "Horusec vulnerability finding"),
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
            summary=f"horusec: {len(findings)} vulnerability finding(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
