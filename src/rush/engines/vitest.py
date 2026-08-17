"""vitest engine — JS/TS test runner with JSON reporter."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import Engine, EngineResult


class VitestEngine(Engine):
    name = "vitest"
    binary = "vitest"
    file_extensions = ("js", "jsx", "ts", "tsx", "mjs", "cjs")

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
            stderr="vitest engine stub",
            parsed=None,
            findings=[],
            summary="vitest stub",
            duration_ms=0,
        )
