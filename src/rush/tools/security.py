"""Security tool — engine dispatch per project type.

Architecture §4.3 + §10. Detects project type:
  - pyproject.toml/setup.py → pip-audit
  - package.json → npm audit

Returns skipped if neither marker is present.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .base import ToolFn, ToolName, ToolResult
from .common import elapsed_ms, now_ms, run_engine
from .routing import aggregate_results

if TYPE_CHECKING:
    from ..permissions import ExecutionPermissions

_OSV_LOCKFILES = (
    "poetry.lock",
    "requirements.txt",
    "package-lock.json",
    "Cargo.lock",
    "go.sum",
)


class SecurityTool(ToolFn):
    name: ToolName = "security"

    @property
    def mcp_description(self) -> str:
        return (
            "Scan deps at <path> for known vulnerabilities. Returns {status, findings[], summary}. "
            "Engines: pip-audit (Python), npm audit (JS/TS). status='skipped' means engine not on PATH."
        )

    def __call__(
        self,
        path: Path,
        *,
        allow_network: bool = False,
        allow_download: bool = False,
        allow_cache_write: bool = False,
        allow_build: bool = False,
        allow_slow: bool = False,
        allow_artifact_write: bool = False,
        allow_browser: bool = False,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions

        permissions = ExecutionPermissions(
            network=allow_network,
            download=allow_download,
            cache_write=allow_cache_write,
            build=allow_build,
            slow=allow_slow,
            artifact_write=allow_artifact_write,
            browser=allow_browser,
        )
        return self.run(path, permissions=permissions)

    def run(
        self,
        path: Path,
        *,
        config=None,
        permissions: ExecutionPermissions | None = None,
    ) -> ToolResult:
        from ..engines import ENGINES
        from ..permissions import build_execution_metadata

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
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        granted=permissions,
                    )
                },
            )

        engine_kwargs = {"permissions": permissions} if permissions is not None else {}
        results: list[ToolResult] = []
        if (project_root / "requirements.txt").is_file():
            results.append(
                run_engine(
                    ENGINES["pip-audit"],
                    project_root,
                    [],
                    tool_name="security",
                    **engine_kwargs,
                )
            )

        if (project_root / "package-lock.json").is_file():
            results.append(
                run_engine(
                    ENGINES["npm-audit"],
                    project_root,
                    [],
                    tool_name="security",
                    **engine_kwargs,
                )
            )

        lockfile = next(
            (
                project_root / name
                for name in _OSV_LOCKFILES
                if (project_root / name).is_file()
            ),
            None,
        )
        if lockfile is not None:
            results.append(
                run_engine(
                    ENGINES["osv-scanner"],
                    lockfile,
                    [],
                    tool_name="security",
                    **engine_kwargs,
                )
            )

        # Check for Medusa scanner
        from .common import engine_on_path

        if engine_on_path("medusa"):
            results.append(
                run_engine(
                    ENGINES["medusa"],
                    project_root,
                    [],
                    tool_name="security",
                    **engine_kwargs,
                )
            )

        if results:
            return aggregate_results(self.name, results)

        return ToolResult(
            tool="security",
            engine=None,
            engine_version=None,
            status="skipped",
            duration_ms=elapsed_ms(start),
            summary=f"security: unrecognized project type at {project_root}",
            findings=[],
            raw=None,
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    granted=permissions,
                )
            },
        )


def _find_project_root(path: Path) -> Path | None:
    """Walk up from `path` looking for dependency manifests or local lockfiles.

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
        if any((d / name).is_file() for name in _OSV_LOCKFILES):
            return d
        if (d / ".git").exists():
            return None  # crossed git boundary without finding a marker
        if d.parent == d:
            return None  # filesystem root
    return None
