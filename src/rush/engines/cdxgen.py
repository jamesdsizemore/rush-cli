"""cdxgen adapter for CycloneDX SBOM generation."""

from __future__ import annotations

from pathlib import Path

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
