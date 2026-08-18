"""Shared adapter for discovered check-only text linters."""

from __future__ import annotations

from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class TextLintEngine(Engine):
    """Run a checker in report mode and preserve its non-empty report lines."""

    command_prefix: tuple[str, ...] = ()
    command_suffix: tuple[str, ...] = ()

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        proc = run_subprocess(
            [
                resolve_binary(self.binary) or self.binary,
                *self.command_prefix,
                *args,
                *self.command_suffix,
            ],
            cwd=cwd,
            timeout=120,
        )
        return EngineResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        lines = [
            line.strip()
            for line in (raw.get("stdout") or raw.get("stderr", "")).splitlines()
            if line.strip()
        ]
        findings = [
            {"path": str(path), "rule": self.name, "severity": "warn", "message": line}
            for line in lines
        ]
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="warn" if findings else "ok",
            duration_ms=raw.get("duration_ms", 0),
            summary=f"{self.name}: {len(findings)} issue(s)",
            findings=findings,
            raw=None,
        )
