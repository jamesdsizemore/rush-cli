"""Dependency-Cruiser adapter for architectural boundary and cycle detection."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class DepcruiseEngine(Engine):
    name = "depcruise"
    binary = "depcruise"
    file_extensions = ("js", "jsx", "ts", "tsx", "mjs", "cjs")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["--output-type", "json"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=180)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "summary" in parsed:
                    findings_raw = parsed.get("summary", {}).get("violations", [])
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"depcruise exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            severity = item.get("rule", {}).get("severity", "warn").lower()
            findings.append(
                {
                    "path": item.get("from", str(path)),
                    "line": 0,
                    "column": 0,
                    "rule": f"depcruise/{item.get('rule', {}).get('name', 'architecture-boundary')}",
                    "severity": "fail" if severity == "error" else "warn",
                    "message": f"Dependency rule violation from '{item.get('from')}' to '{item.get('to')}'",
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
            summary=f"depcruise: {len(findings)} architectural violation(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
