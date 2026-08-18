"""gitleaks adapter that deliberately redacts secret values."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class GitleaksEngine(Engine):
    name = "gitleaks"
    binary = "gitleaks"
    file_extensions = ()

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        proc = run_subprocess(
            [
                resolve_binary(self.binary) or self.binary,
                "detect",
                "--source",
                str(path),
                "--report-format",
                "json",
                "--report-path",
                "-",
                "--no-banner",
            ],
            cwd=cwd,
            timeout=120,
        )
        return EngineResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        try:
            reports = json.loads(raw.get("stdout", "[]"))
        except json.JSONDecodeError:
            reports = []
        findings = [
            {
                "path": str(item.get("File", "")),
                "line": item.get("StartLine", 0),
                "rule": str(item.get("RuleID", "gitleaks")),
                "severity": "error",
                "message": "Potential secret detected",
            }
            for item in reports
            if isinstance(item, dict)
        ]
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="fail" if findings else "ok",
            duration_ms=raw.get("duration_ms", 0),
            summary=f"gitleaks: {len(findings)} potential secret(s)",
            findings=findings,
            raw=None,
        )
