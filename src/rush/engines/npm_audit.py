"""npm audit engine — JS/TS dependency vulnerability scanner."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import Engine, EngineResult


class NpmAuditEngine(Engine):
    name = "npm-audit"
    binary = "npm"
    file_extensions = ("js", "jsx", "ts", "tsx", "mjs", "cjs")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Optional[Path] = None,
    ) -> EngineResult:
        # Phase 3 stub. Real impl will run `npm audit --json` from package.json dir.
        return EngineResult(
            exit_code=0,
            stdout="",
            stderr="npm audit engine stub",
            parsed=None,
            findings=[],
            summary="npm audit stub",
            duration_ms=0,
        )
