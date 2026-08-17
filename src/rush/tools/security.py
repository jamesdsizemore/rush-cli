"""Security tool — engine dispatch per project type.

Architecture §4.3 + §10. Detects project type:
  - pyproject.toml/setup.py → pip-audit
  - package.json → npm audit

Returns skipped if neither marker is present.
"""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolName, ToolResult
from .common import elapsed_ms, now_ms, run_engine


class SecurityTool(ToolFn):
    name: ToolName = "security"

    @property
    def mcp_description(self) -> str:
        return (
            "Scan deps at <path> for known vulnerabilities. Returns {status, findings[], summary}. "
            "Engines: pip-audit (Python), npm audit (JS/TS). status='skipped' means engine not on PATH."
        )

    def __call__(self, path: Path) -> ToolResult:
        return self.run(path)

    def run(self, path: Path, *, config=None) -> ToolResult:
        from ..engines import ENGINES

        start = now_ms()
        project_root = _find_project_root(path)

        if project_root is None:
            return ToolResult(
                tool="security",
                engine=None,
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"security: no pyproject.toml or package.json found above {path}",
                findings=[],
                raw=None,
            )

        if (project_root / "pyproject.toml").exists() or (
            project_root / "setup.py"
        ).exists():
            return run_engine(
                ENGINES["pip-audit"], project_root, [], tool_name="security"
            )

        if (project_root / "package.json").exists():
            return run_engine(
                ENGINES["npm-audit"], project_root, [], tool_name="security"
            )

        return ToolResult(
            tool="security",
            engine=None,
            engine_version=None,
            status="skipped",
            duration_ms=elapsed_ms(start),
            summary=f"security: unrecognized project type at {project_root}",
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
