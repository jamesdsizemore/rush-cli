"""Optional commitlint adapter; Rush never installs it."""

from __future__ import annotations

from pathlib import Path

from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class CommitlintEngine(Engine):
    name = "commitlint"
    binary = "commitlint"
    file_extensions = ()

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        proc = run_subprocess(
            [resolve_binary(self.binary) or self.binary, *args],
            cwd=cwd or path,
            timeout=30,
        )
        return EngineResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )
