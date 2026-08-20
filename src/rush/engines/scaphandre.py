"""Scaphandre adapter for software energy consumption and carbon footprint estimation."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class ScaphandreEngine(Engine):
    name = "scaphandre"
    binary = "scaphandre"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["json", "-t", "5", "-s", "1", "-f", "scaphandre-power.json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=60)

        parsed = None
        report_file = (cwd or path) / "scaphandre-power.json"
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
        if isinstance(parsed, list):
            for report in parsed:
                host_power = report.get("host", {}).get("consumption", 0)
                if host_power > 100_000_000:  # > 100W micro-watts
                    findings_raw.append({"consumption_microwatts": host_power})

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"scaphandre exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            watts = item.get("consumption_microwatts", 0) / 1_000_000.0
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": "energy/high-power-draw",
                    "severity": "warn",
                    "message": f"Elevated host energy consumption during run: {watts:.2f} W",
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
            summary=f"scaphandre: energy profiling completed ({len(findings)} power spike(s))",
            findings=findings,
            raw=raw.get("parsed"),
        )
