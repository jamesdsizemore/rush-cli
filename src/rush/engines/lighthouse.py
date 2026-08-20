"""Lighthouse adapter for Core Web Vitals, performance, and SEO auditing."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class LighthouseEngine(Engine):
    name = "lighthouse"
    binary = "lighthouse"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        target = str(path) if str(path).startswith("http") else "http://localhost:3000"
        default_args = [
            target,
            "--output=json",
            "--output-path=lighthouse-report.json",
            "--chrome-flags=--headless",
        ]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=180)

        parsed = None
        report_file = (cwd or path) / "lighthouse-report.json"
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
        if isinstance(parsed, dict) and "audits" in parsed:
            for audit_id, audit in parsed["audits"].items():
                score = audit.get("score")
                if score is not None and score < 0.9:
                    findings_raw.append({"id": audit_id, **audit})

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"lighthouse exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            score = item.get("score", 1.0)
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": f"lighthouse/{item.get('id', 'audit')}",
                    "severity": "fail" if score < 0.5 else "warn",
                    "message": item.get("title", "Lighthouse audit recommendation"),
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
            summary=f"lighthouse: {len(findings)} performance/SEO recommendation(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
