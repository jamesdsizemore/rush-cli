"""Wait-On adapter for local service port, file, and HTTP health polling."""

from __future__ import annotations

from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class WaitOnEngine(Engine):
    name = "wait-on"
    binary = "wait-on"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        target = (
            str(path)
            if str(path).startswith("http") or str(path).startswith("tcp:")
            else "http://localhost:3000"
        )
        default_args = ["--timeout", "5000", target]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=60)

        findings_raw: list[dict] = []
        if proc.returncode != 0:
            findings_raw.append(
                {
                    "target": target,
                    "error": proc.stderr.strip() or "Service readiness timeout reached",
                }
            )

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed={"ready": proc.returncode == 0},
            findings=findings_raw,
            summary=f"wait-on exit {proc.returncode}",
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
                    "rule": "wait-on/readiness-timeout",
                    "severity": "warn",
                    "message": f"Service is not yet available at {item.get('target')}",
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
            summary="wait-on: service readiness poll completed",
            findings=findings,
            raw=raw.get("parsed"),
        )
