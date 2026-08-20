"""Cosign artifact signature and provenance verification adapter."""

from __future__ import annotations

from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class CosignEngine(Engine):
    name = "cosign"
    binary = "cosign"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        argv = [binary_path, "verify-blob", *args, str(path)]
        proc = run_subprocess(argv, cwd=cwd or path, timeout=60)

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            findings=[],
            summary=f"cosign exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        exit_code = raw.get("exit_code", 0)
        findings = []
        if exit_code != 0:
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "rule": "signature-verification-failed",
                    "severity": "error",
                    "message": (
                        raw.get("stderr") or "Cosign signature verification failed"
                    ).splitlines()[0]
                    if raw.get("stderr")
                    else "Signature verification failed",
                }
            )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="ok" if exit_code == 0 else "fail",
            duration_ms=raw.get("duration_ms", 0),
            summary="cosign: signature verified"
            if exit_code == 0
            else "cosign: signature verification failed",
            findings=findings,
            raw=raw.get("stdout"),
        )
