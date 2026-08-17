"""Engine ABC + EngineResult TypedDict.

Architecture §4.1. Every engine (ruff, eslint, etc.) implements ``Engine``.
"""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, TypedDict

from ..tools.base import Finding, ToolResult
from ..tools.common import resolve_binary


class EngineResult(TypedDict, total=False):
    exit_code: int
    stdout: str
    stderr: str
    parsed: Any | None  # engine-native JSON if available, else None
    findings: list[Finding]  # normalized from parsed
    summary: str
    duration_ms: int


class Engine(ABC):
    """Base for the 7 concrete engines (ruff, eslint, prettier, vitest,
    pytest, pip-audit, npm-audit).

    Engines never raise. ``run()`` returns an EngineResult even on failure.
    """

    name: str
    binary: str
    file_extensions: tuple[str, ...]

    @abstractmethod
    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult: ...

    def version(self) -> str | None:
        """Capture the engine's version string. Return None if unavailable.

        Architecture §13 (Q1): cache after first call (subclasses override
        with functools.lru_cache if they want eager caching).
        """
        binary_path = resolve_binary(self.binary)
        if binary_path is None:
            return None
        try:
            r = subprocess.run(
                [binary_path, "--version"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            out = (r.stdout or r.stderr).strip()
            # First token that looks like a version, e.g. "ruff 0.6.9" or "v0.6.9"
            for token in out.split():
                if (
                    token
                    and (token[0].isdigit() or token.startswith("v"))
                    and any(c.isdigit() for c in token)
                ):
                    return token.lstrip("v")
            return out.splitlines()[0] if out else None
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        """Convert an EngineResult into the canonical ToolResult.

        Default impl is conservative — subclasses override for richer
        normalization (e.g. ruff's structured JSON output).
        """
        from ..tools.common import now_ms

        exit_code = raw.get("exit_code", 0)
        # Engines return non-zero on findings. That's "fail" or "warn", not "error".
        # "error" is reserved for engine crashes — those are caught upstream.
        status = "ok" if exit_code == 0 else "warn"
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=None,
            status=status,
            duration_ms=raw.get("duration_ms", now_ms()),
            summary=raw.get("summary", "") or f"{self.name} exit {exit_code}",
            findings=raw.get("findings", []),
            raw=raw.get("parsed"),
        )
