"""Infection adapter for PHP AST mutation testing."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class InfectionEngine(Engine):
    name = "infection"
    binary = "infection"
    file_extensions = ("php",)

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["--json=infection-log.json", "--no-interaction", "--silent"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=300)

        parsed = None
        report_file = (cwd or path) / "infection-log.json"
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
        if isinstance(parsed, dict) and "escaped" in parsed:
            findings_raw = parsed["escaped"]

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"infection exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("sourceFilePath", str(path)),
                    "line": item.get("line", 0),
                    "column": 0,
                    "rule": f"infection/{item.get('mutator', 'mutator')}",
                    "severity": "warn",
                    "message": f"PHP mutant survived: {item.get('mutator', 'mutation')} at line {item.get('line', 0)}",
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
            summary=f"infection: {len(findings)} survived mutant(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
