"""Test tool — engine dispatch per project type.

Architecture §4.3 + §10. Detects project type:
  - pyproject.toml or setup.py present → pytest
  - package.json present → vitest (preferred) or npm test

Returns skipped if neither project marker is present.
"""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolName, ToolResult
from .common import elapsed_ms, now_ms, run_engine


class TestTool(ToolFn):
    name: ToolName = "test"

    @property
    def mcp_description(self) -> str:
        return (
            "Run tests for project at <path>. Returns {status, findings[], summary}. "
            "Engines: pytest (Python), vitest/npm (JS/TS). status='skipped' means engine not on PATH."
        )

    def __call__(self, path: Path) -> ToolResult:
        return self.run(path)

    def run(self, path: Path, *, config=None) -> ToolResult:
        from ..engines import ENGINES

        start = now_ms()
        project_root = _find_project_root(path)

        if project_root is None:
            return ToolResult(
                tool="test",
                engine=None,
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"test: no pyproject.toml or package.json found above {path}",
                findings=[],
                raw=None,
            )

        if (project_root / "pyproject.toml").exists() or (
            project_root / "setup.py"
        ).exists():
            # Python project
            r = run_engine(ENGINES["pytest"], project_root, [], tool_name="test")
            return r

        if (project_root / "package.json").exists():
            # JS/TS project — try vitest first, fall back to npm test
            r = run_engine(ENGINES["vitest"], project_root, ["run"], tool_name="test")
            if r.get("status") == "skipped":
                # vitest not installed — try npm test (but npm test has no JSON)
                # Fall back to skipping; v0.2 may add a generic npm-test fallback
                pass
            return r

        return ToolResult(
            tool="test",
            engine=None,
            engine_version=None,
            status="skipped",
            duration_ms=elapsed_ms(start),
            summary=f"test: unrecognized project type at {project_root}",
            findings=[],
            raw=None,
        )


def _find_project_root(path: Path) -> Path | None:
    """Walk up from `path` looking for pyproject.toml, setup.py, or package.json.

    Order matters: check project markers FIRST, then the git boundary.
    (If we checked .git first, we'd bail out at the same level where
    pyproject.toml lives — bug discovered by `rush test src/rush`.)

    Hard cap of 5 levels so we don't escape a tmp dir and match a
    stale package.json in the user's home dir.
    """
    start = path if path.is_dir() else path.parent
    MAX_LEVELS = 5
    for levels, d in enumerate([start, *start.parents]):
        if levels > MAX_LEVELS:
            return None
        if (d / "pyproject.toml").exists():
            return d
        if (d / "setup.py").exists():
            return d
        if (d / "package.json").exists():
            return d
        if (d / ".git").exists():
            return None  # crossed git boundary without finding a marker
        if d.parent == d:
            return None  # filesystem root
    return None
