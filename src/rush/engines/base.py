"""Engine ABC + EngineResult TypedDict.

Architecture §4.1. Every engine (ruff, eslint, etc.) implements ``Engine``.
"""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar, TypedDict

from ..tools.base import ToolResult, ToolStatus
from ..tools.common import resolve_binary, run_subprocess

RawFinding = dict[str, Any]


def ownership_kwargs(
    owner_instance_id: str | None, run_id: str | None
) -> dict[str, str]:
    """P69-01.2j: the ownership pair as `run_subprocess` kwargs, or `{}`.

    An engine forwards its own `owner_instance_id`/`run_id` into its
    `run_subprocess()` call through this helper so an *unowned* call keeps
    today's exact kwargs, byte for byte -- the unowned contract that
    `tests/test_subprocess_contract.py` and every engine reference test
    assert on is not allowed to change just because ownership became
    expressible.
    """
    if owner_instance_id is None or run_id is None:
        return {}
    return {"owner_instance_id": owner_instance_id, "run_id": run_id}


class EngineResult(TypedDict, total=False):
    exit_code: int
    stdout: str
    stderr: str
    parsed: Any | None  # engine-native JSON if available, else None
    findings: list[RawFinding]  # engine-native records; normalize before ToolResult
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
        *,
        owner_instance_id: str | None = None,
        run_id: str | None = None,
    ) -> EngineResult: ...

    _cached_versions: ClassVar[dict[str, str]] = {}

    def version(
        self,
        *,
        owner_instance_id: str | None = None,
        run_id: str | None = None,
    ) -> str | None:
        """Capture the engine's version string. Return None if unavailable.

        Architecture §13 (Q1): cache after first call (subclasses override
        with functools.lru_cache if they want eager caching).

        P69-01.2j: a cold-cache probe spawns a real child, exactly as
        reachable by Detach's force-exit deadline as the main command, so it
        carries the same ownership identity.
        """
        binary_path = resolve_binary(self.binary)
        if binary_path is None:
            return None
        if binary_path in Engine._cached_versions:
            return Engine._cached_versions[binary_path]

        try:
            r = run_subprocess(
                [binary_path, "--version"],
                timeout=10,
                **ownership_kwargs(owner_instance_id, run_id),
            )
            if r.returncode != 0:
                return None
            out = (r.stdout or r.stderr).strip()
            # First token that looks like a version, e.g. "ruff 0.6.9" or "v0.6.9"
            ver = None
            for token in out.split():
                if (
                    token
                    and (token[0].isdigit() or token.startswith("v"))
                    and any(c.isdigit() for c in token)
                ):
                    ver = token.lstrip("v")
                    break
            if ver is None and out:
                ver = out.splitlines()[0]
            if ver is not None:
                Engine._cached_versions[binary_path] = ver
            return ver
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        """Convert an EngineResult into the canonical ToolResult.

        Default impl is conservative — subclasses override for richer
        normalization (e.g. ruff's structured JSON output).
        """
        from ..tools.common import normalize_findings, now_ms

        exit_code = raw.get("exit_code", 0)
        # Engines return non-zero on findings. That's "fail" or "warn", not "error".
        # "error" is reserved for engine crashes — those are caught upstream.
        status: ToolStatus = "ok" if exit_code == 0 else "warn"
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=None,
            status=status,
            duration_ms=raw.get("duration_ms", now_ms()),
            summary=raw.get("summary", "") or f"{self.name} exit {exit_code}",
            findings=normalize_findings(raw.get("findings", [])),
            raw=raw.get("parsed"),
        )
