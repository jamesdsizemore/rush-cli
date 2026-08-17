"""pip-audit engine — Python dependency vulnerability scanner."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import Engine, EngineResult


class PipAuditEngine(Engine):
    name = "pip-audit"
    binary = "pip-audit"
    file_extensions = ("py", "toml")  # scans deps from pyproject.toml

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Optional[Path] = None,
    ) -> EngineResult:
        # Phase 3 stub.
        return EngineResult(
            exit_code=0,
            stdout="",
            stderr="pip-audit engine stub",
            parsed=None,
            findings=[],
            summary="pip-audit stub",
            duration_ms=0,
        )
