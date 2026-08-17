"""eslint engine — JS/TS lint."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import Engine, EngineResult


class EslintEngine(Engine):
    name = "eslint"
    binary = "eslint"
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
            stderr="eslint engine stub",
            parsed=None,
            findings=[],
            summary="eslint stub",
            duration_ms=0,
        )
