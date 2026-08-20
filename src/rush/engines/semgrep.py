"""Semgrep adapter for SAST analysis with local rule isolation."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class SemgrepEngine(Engine):
    name = "semgrep"
    binary = "semgrep"
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
        "yaml",
        "yml",
        "json",
    )

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        # Use --metrics=off and --disable-version-check to prevent automatic network calls
        default_args = ["scan", "--json", "--metrics=off", "--disable-version-check"]
        if not any(arg.startswith("--config") for arg in args):
            default_args.extend(["--config", "auto"])

        argv = [binary_path, *default_args, *args, str(path)]
        proc = run_subprocess(argv, cwd=cwd or path, timeout=180)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "results" in parsed:
                    findings_raw = parsed["results"]
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"semgrep exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("path", str(path)),
                    "line": item.get("start", {}).get("line", 0),
                    "column": item.get("start", {}).get("col", 0),
                    "rule": item.get("check_id", "semgrep-rule"),
                    "severity": (
                        "error"
                        if item.get("extra", {}).get("severity") == "ERROR"
                        else "warn"
                    ),
                    "message": item.get("extra", {}).get("message", "Semgrep finding"),
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
            summary=f"semgrep: {len(findings)} finding(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
