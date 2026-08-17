"""prettier engine — JS/TS + JSON/MD/YAML/CSS/HTML format."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import Engine, EngineResult


class PrettierEngine(Engine):
    name = "prettier"
    binary = "prettier"
    file_extensions = ("js", "jsx", "ts", "tsx", "mjs", "cjs",
                       "json", "md", "yaml", "yml", "css", "html")

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
            stderr="prettier engine stub",
            parsed=None,
            findings=[],
            summary="prettier stub",
            duration_ms=0,
        )
