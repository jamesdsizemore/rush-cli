"""Statoscope adapter for JavaScript bundle size and duplicate module analysis."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class StatoscopeEngine(Engine):
    name = "statoscope"
    binary = "statoscope"
    file_extensions = ("json",)

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["validate", "--input", str(path), "--format", "json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "rules" in parsed:
                    for rule in parsed["rules"]:
                        if rule.get("status") in ("error", "warn"):
                            findings_raw.append(rule)
            except json.JSONDecodeError:
                pass

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"statoscope exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            is_error = item.get("status") == "error"
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": f"statoscope/{item.get('name', 'bundle-validation')}",
                    "severity": "fail" if is_error else "warn",
                    "message": item.get(
                        "message", "Bundle size / duplicate package issue"
                    ),
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
            summary=f"statoscope: {len(findings)} bundle validation finding(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
