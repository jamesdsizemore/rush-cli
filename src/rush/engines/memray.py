"""Memray adapter for Python memory profiling and allocation leak tracking."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class MemrayEngine(Engine):
    name = "memray"
    binary = "memray"
    file_extensions = ("py",)

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["summary", "--json", "memray-profile.bin"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=180)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    findings_raw = parsed
                elif isinstance(parsed, dict) and "allocations" in parsed:
                    findings_raw = parsed["allocations"]
            except json.JSONDecodeError:
                pass

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"memray exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            size_mb = item.get("total_bytes", 0) / (1024 * 1024)
            findings.append(
                {
                    "path": item.get("location", str(path)),
                    "line": item.get("line", 0),
                    "column": 0,
                    "rule": "memray/high-memory-allocation",
                    "severity": "warn",
                    "message": f"Memory allocation hot spot: {item.get('name', 'function')} ({size_mb:.2f} MB)",
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
            summary=f"memray: {len(findings)} memory hot spot(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
