"""cdxgen adapter for CycloneDX SBOM generation."""

from __future__ import annotations

from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class CdxgenEngine(Engine):
    name = "cdxgen"
    binary = "cdxgen"
    file_extensions = ()

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        proc = run_subprocess(
            [resolve_binary(self.binary) or self.binary, *args, str(path)],
            cwd=cwd,
            timeout=120,
        )
        return EngineResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        """cdxgen exits nonzero only for generation failures, never findings."""
        exit_code = raw.get("exit_code", 0)
        if exit_code != 0:
            detail = (raw.get("stderr") or "cdxgen generation failed").splitlines()[0]
            return ToolResult(
                tool=tool_name,
                engine=self.name,
                engine_version=self.version(),
                status="error",
                duration_ms=raw.get("duration_ms", 0),
                summary=f"cdxgen error (exit {exit_code}): {detail}",
                findings=[],
                raw=None,
            )
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="ok",
            duration_ms=raw.get("duration_ms", 0),
            summary="cdxgen: SBOM generated",
            findings=[],
            raw=None,
        )
