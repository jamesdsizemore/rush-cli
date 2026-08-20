"""Diff-Cover adapter for diff-only test coverage threshold enforcement."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class DiffCoverEngine(Engine):
    name = "diff-cover"
    binary = "diff-cover"
    file_extensions = ("xml", "json")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = [
            "coverage.xml",
            "--compare-branch=main",
            "--json-report=diff-cover.json",
        ]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        report_file = (cwd or path) / "diff-cover.json"
        if report_file.exists():
            try:
                parsed = json.loads(report_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                parsed = None
        elif proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
            except json.JSONDecodeError:
                pass

        findings_raw: list[dict] = []
        if isinstance(parsed, dict) and "src_stats" in parsed:
            for file_name, stats in parsed["src_stats"].items():
                percent = stats.get("percent_covered", 100)
                if percent < 80:  # Threshold 80% diff coverage
                    findings_raw.append(
                        {
                            "file": file_name,
                            "percent": percent,
                            "missing": stats.get("violation_lines", []),
                        }
                    )

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"diff-cover exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("file", str(path)),
                    "line": 0,
                    "column": 0,
                    "rule": "diff-cover/under-threshold",
                    "severity": "warn",
                    "message": f"Diff coverage below target: {item.get('percent', 0):.1f}% (missing lines: {item.get('missing', [])})",
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
            summary=f"diff-cover: {len(findings)} low diff-coverage file(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
