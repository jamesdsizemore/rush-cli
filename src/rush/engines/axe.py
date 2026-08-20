"""Axe-core accessibility audit adapter."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class AxeEngine(Engine):
    name = "axe"
    binary = "axe"
    file_extensions = ("html", "htm")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["--save", "--stdout"]
        argv = [binary_path, str(path), *default_args, *args]
        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    for item in parsed:
                        findings_raw.extend(item.get("violations", []))
                elif isinstance(parsed, dict) and "violations" in parsed:
                    findings_raw = parsed["violations"]
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"axe exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            impact = item.get("impact", "minor")
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "rule": item.get("id", "axe-violation"),
                    "severity": "error"
                    if impact in {"critical", "serious"}
                    else "warn",
                    "message": f"{item.get('help', 'Accessibility violation')}: {item.get('description', '')}",
                }
            )

        exit_code = raw.get("exit_code", 0)
        has_critical = any(f["severity"] == "error" for f in findings)
        status = (
            "fail"
            if has_critical
            else ("warn" if findings else ("ok" if exit_code == 0 else "error"))
        )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"axe: {len(findings)} accessibility violation(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
