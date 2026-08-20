"""Globstar adapter for Tree-Sitter custom pattern static analysis."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class GlobstarEngine(Engine):
    name = "globstar"
    binary = "globstar"
    file_extensions = ("py", "js", "ts", "jsx", "tsx", "go", "rs", "java", "c", "cpp")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["check", "--format=json"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    findings_raw = parsed
                elif isinstance(parsed, dict) and "results" in parsed:
                    findings_raw = parsed["results"]
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"globstar exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            sev = item.get("severity", "warning").lower()
            findings.append(
                {
                    "path": item.get("file", str(path)),
                    "line": item.get("line", 0),
                    "column": item.get("column", 0),
                    "rule": f"globstar/{item.get('pattern_id', item.get('rule', 'pattern-match'))}",
                    "severity": "fail" if sev in ("error", "critical") else "warn",
                    "message": item.get("message", "Tree-Sitter pattern matched"),
                    "fix": item.get("fix"),
                    "remediation": item.get("remediation"),
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
            summary=f"globstar: {len(findings)} pattern match(es)",
            findings=findings,
            raw=raw.get("parsed"),
        )
