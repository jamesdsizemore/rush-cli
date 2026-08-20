"""SLSA Verifier adapter for provenance and build attestation validation."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class SlsaVerifierEngine(Engine):
    name = "slsa-verifier"
    binary = "slsa-verifier"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["verify-artifact"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and not parsed.get("verified", True):
                    findings_raw.append(parsed)
            except json.JSONDecodeError:
                parsed = {"output": proc.stdout}

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"slsa-verifier exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        exit_code = raw.get("exit_code", 0)
        if exit_code != 0 or raw.get("findings"):
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": "slsa/provenance-verification-failed",
                    "severity": "fail",
                    "message": raw.get("stderr")
                    or "SLSA provenance verification failed",
                }
            )

        status = "fail" if findings else ("ok" if exit_code == 0 else "error")

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"slsa-verifier: verification {'failed' if findings else 'passed'}",
            findings=findings,
            raw=raw.get("parsed"),
        )
