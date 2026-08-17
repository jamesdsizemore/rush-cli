"""ruff engine — Python lint + format."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import Engine, EngineResult


class RuffEngine(Engine):
    name = "ruff"
    binary = "ruff"
    file_extensions = ("py", "pyi")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Optional[Path] = None,
    ) -> EngineResult:
        # Phase 3 stub. Phase 4 will subprocess ruff + parse --output-format=json.
        return EngineResult(
            exit_code=0,
            stdout="",
            stderr="ruff engine stub",
            parsed=None,
            findings=[],
            summary="ruff stub",
            duration_ms=0,
        )
