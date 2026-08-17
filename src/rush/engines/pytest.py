"""pytest engine — Python test runner."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import Engine, EngineResult


class PytestEngine(Engine):
    name = "pytest"
    binary = "pytest"
    file_extensions = ("py", "pyi")

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
            stderr="pytest engine stub",
            parsed=None,
            findings=[],
            summary="pytest stub",
            duration_ms=0,
        )
