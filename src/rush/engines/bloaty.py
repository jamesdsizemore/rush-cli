"""Bloaty McBloatface adapter for native binary size and section analysis."""

from __future__ import annotations

from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class BloatyEngine(Engine):
    name = "bloaty"
    binary = "bloaty"
    file_extensions = ("exe", "dll", "so", "dylib", "wasm")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["-d", "compileunits,symbols", "--csv"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        findings_raw: list[dict] = []
        for line in proc.stdout.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith("compileunits"):
                continue
            parts = line_str.split(",")
            if len(parts) >= 3:
                findings_raw.append(
                    {
                        "unit": parts[0],
                        "symbol": parts[1],
                        "vmsize": parts[2],
                        "filesize": parts[3] if len(parts) > 3 else parts[2],
                    }
                )

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed={"sections": findings_raw[:50]},
            findings=findings_raw[:50],
            summary=f"bloaty exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": "bloaty/binary-footprint",
                    "severity": "warn",
                    "message": f"Binary section footprint: {item.get('unit')} ({item.get('filesize')} bytes)",
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
            summary=f"bloaty: {len(findings)} binary section report(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
