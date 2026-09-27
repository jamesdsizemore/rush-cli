"""Security tool — engine dispatch per project type.

Architecture §4.3 + §10. Detects project type:
  - pyproject.toml/setup.py → pip-audit
  - package.json → npm audit

Returns skipped if neither marker is present.

Phase 70 T14: Python dependency inputs (`uv.lock`, `requirements*.txt`,
`pyproject.toml`) are inventoried explicitly and audited offline through
osv-scanner (uv.lock/requirements*) or gated pip-audit project mode
(pyproject-declared dependencies). Binding brief:
`.scratch/phase-70-design-gate/W2-T9-T17.md` §T14.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

from .base import ToolFn, ToolName, ToolResult
from .common import elapsed_ms, error_result, now_ms, run_engine, skipped_result
from .routing import aggregate_results

if TYPE_CHECKING:
    from ..permissions import ExecutionPermissions

    class _EnginePermissions(TypedDict, total=False):
        permissions: ExecutionPermissions


_OSV_LOCKFILES = (
    "poetry.lock",
    "package-lock.json",
    "Cargo.lock",
    "go.sum",
)

_MIN_OSV_VERSION = (2, 0, 0)

_INCLUDE_PREFIXES = ("-r", "--requirement", "-c", "--constraint")
_VCS_PREFIXES = ("git+", "hg+", "svn+", "bzr+")
_URL_PREFIXES = ("http://", "https://")


class SecurityTool(ToolFn):
    name: ToolName = "security"

    @property
    def mcp_description(self) -> str:
        from rush.catalog import TOOL_SPECS

        return TOOL_SPECS["security"].mcp_description

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

        engine_kwargs: _EnginePermissions = (
            {"permissions": permissions} if permissions is not None else {}
        )
        results: list[ToolResult] = []
        dependencies: list[dict[str, Any]] = []

        _audit_python_dependency_inputs(
            project_root, engine_kwargs, results, dependencies
        )
        _audit_pyproject_project_mode(
            project_root, permissions, engine_kwargs, results, dependencies
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
            final = aggregate_results(self.name, results)
            # T5: every audit denied a permission -> the step never ran.
            if all(_permission_denied(result) for result in results):
                final["metadata"] = {
                    **(final.get("metadata") or {}),
                    "execution": _denied_execution(None, permissions),
                }
        else:
            final = ToolResult(
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

        metadata = final.get("metadata")
        if metadata is None:
            metadata = {}
        metadata["scope"] = {"version": 1, "dependencies": dependencies}
        final["metadata"] = metadata
        return final


def _denied_execution(
    required: ExecutionPermissions | None, granted: ExecutionPermissions | None
) -> dict[str, Any]:
    """T5: execution metadata of a permission-denied audit -- `not_run`, so a
    suite never counts it as executed (same as `run_engine`'s denial)."""
    from ..permissions import build_execution_metadata

    return build_execution_metadata(
        "executed",
        requested=required,
        granted=granted,
        extra={"disposition": "not_run", "cause": "permission_denied"},
    )


def _permission_denied(result: ToolResult) -> bool:
    execution = (result.get("metadata") or {}).get("execution") or {}
    return (
        execution.get("disposition") == "not_run"
        and execution.get("cause") == "permission_denied"
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
        if (d / "uv.lock").is_file():
            return d
        if any(d.glob("requirements*.txt")):
            return d
        if any((d / name).is_file() for name in _OSV_LOCKFILES):
            return d
        if (d / ".git").exists():
            return None  # crossed git boundary without finding a marker
        if d.parent == d:
            return None  # filesystem root
    return None


# ---------------------------------------------------------------------------
# T14: uv.lock / requirements* discovery, classification, and offline audit
# ---------------------------------------------------------------------------


def _discover_dependency_files(project_root: Path) -> list[Path]:
    """Every uv.lock/requirements* input this project declares.

    Root-level `requirements*.txt` (requirements.txt, requirements-dev.txt, ...)
    plus any nested `requirements*.txt` under a `requirements/` directory.
    """
    found: list[Path] = []
    uv_lock = project_root / "uv.lock"
    if uv_lock.is_file():
        found.append(uv_lock)
    found.extend(sorted(project_root.glob("requirements*.txt")))
    requirements_dir = project_root / "requirements"
    if requirements_dir.is_dir():
        found.extend(sorted(requirements_dir.rglob("*.txt")))
    # de-dupe while preserving order (nested globs can overlap)
    seen: set[Path] = set()
    ordered: list[Path] = []
    for candidate in found:
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


def _resolve_include_target(
    including_file: Path, raw_target: str, root: Path
) -> tuple[Path, bool]:
    """Resolve a `-r`/`-c` include relative to its including file's directory.

    Lexical join + normalize (no filesystem access, the target need not
    exist), then containment-check the normalized path against the logical
    root. Returns (normalized_path, contained_in_root).
    """
    candidate = including_file.parent / raw_target
    normalized = Path(os.path.normpath(str(candidate)))
    root_normalized = Path(os.path.normpath(str(root)))
    try:
        contained = normalized.is_relative_to(root_normalized)
    except ValueError:
        contained = False
    return normalized, contained


def _classify_requirements(path: Path, root: Path) -> tuple[str, str | None]:
    """Return (state, reason) for a requirements*.txt input.

    `unresolved`: editable/VCS/URL references osv-scanner cannot pin.
    `malformed`/`include_outside_root`: a `-r`/`-c` include escapes root.
    `pending`: safe to send to osv-scanner offline.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return "malformed", "unreadable"

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(_INCLUDE_PREFIXES):
            parts = line.split(maxsplit=1)
            target = parts[1].strip() if len(parts) > 1 else ""
            if not target:
                continue
            _normalized, contained = _resolve_include_target(path, target, root)
            if not contained:
                return "malformed", "include_outside_root"
            continue
        if line.startswith(("-e", "--editable")):
            return "unresolved", "editable_local_dependency"
        if line.startswith(_VCS_PREFIXES):
            return "unresolved", "vcs_reference"
        if line.startswith(_URL_PREFIXES):
            return "unresolved", "url_reference"
    return "pending", None


def _classify_uv_lock(path: Path) -> tuple[str, str | None]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return "malformed", "unreadable"
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return "malformed", "invalid_toml"
    return "pending", None


def _osv_parser_prefix(path: Path) -> str | None:
    """osv-scanner's explicit `<parser>:<path>` prefix for a non-canonical
    requirements filename (e.g. `requirements-dev.txt`)."""
    if path.name == "requirements.txt":
        return None
    return "requirements.txt:"


def _osv_gate(engine: Any) -> tuple[bool, str | None]:
    from .common import engine_on_path

    if not engine_on_path(engine.binary):
        return False, f"{engine.binary} not on PATH"
    version = engine.version()
    if version is None:
        return False, "osv-scanner version could not be determined"
    parts = version.split(".")[:3]
    try:
        numeric = tuple(int(p) for p in parts)
    except ValueError:
        return False, f"osv-scanner version {version} could not be parsed"
    numeric = numeric + (0,) * (3 - len(numeric))
    if numeric < _MIN_OSV_VERSION:
        return (
            False,
            f"osv-scanner {version} is older than the required 2.0.0",
        )
    return True, None


def _audit_python_dependency_inputs(
    project_root: Path,
    engine_kwargs: _EnginePermissions,
    results: list[ToolResult],
    dependencies: list[dict[str, Any]],
) -> None:
    from ..engines import ENGINES

    entries: list[dict[str, Any]] = []
    for input_path in _discover_dependency_files(project_root):
        if input_path.name == "uv.lock":
            state, reason = _classify_uv_lock(input_path)
            kind = "uv_lock"
        else:
            state, reason = _classify_requirements(input_path, project_root)
            kind = "requirements"
        entry: dict[str, Any] = {"path": str(input_path), "kind": kind, "state": state}
        if reason is not None:
            entry["reason"] = reason
        entries.append(entry)
        dependencies.append(entry)

        if state == "malformed":
            results.append(
                error_result(
                    "security",
                    None,
                    f"malformed dependency input {input_path}: {reason}",
                )
            )

    pending = [e for e in entries if e["state"] == "pending"]
    if not pending:
        return

    engine = ENGINES["osv-scanner"]
    ok, gate_reason = _osv_gate(engine)
    if not ok:
        for entry in pending:
            entry["state"] = "scanner_unavailable"
            entry["reason"] = gate_reason
        return

    lockfile_args: list[str] = []
    for entry in pending:
        input_path = Path(entry["path"])
        prefix = (
            _osv_parser_prefix(input_path) if entry["kind"] == "requirements" else None
        )
        value = f"{prefix}{input_path}" if prefix else str(input_path)
        lockfile_args.extend(["--lockfile", value])

    osv_result = run_engine(
        engine,
        project_root,
        lockfile_args,
        tool_name="security",
        **engine_kwargs,
    )
    results.append(osv_result)

    # The state comes from the real scan outcome, not the gate: osv-scanner
    # can vanish, fail to spawn or error out after `_osv_gate` passed.
    status = osv_result.get("status")
    summary = str(osv_result.get("summary") or "")
    for entry in pending:
        if "no offline vulnerability database available" in summary:
            entry["state"] = "db_unavailable"
        elif status in ("skipped", "error"):
            entry["state"] = "scanner_unavailable"
            entry["reason"] = summary
        else:
            entry["state"] = "audited"


def _audit_pyproject_project_mode(
    project_root: Path,
    permissions: ExecutionPermissions | None,
    engine_kwargs: _EnginePermissions,
    results: list[ToolResult],
    dependencies: list[dict[str, Any]],
) -> None:
    from ..engines import ENGINES
    from ..permissions import ExecutionPermissions as _ExecutionPermissions
    from ..permissions import check_permissions

    pyproject = project_root / "pyproject.toml"
    if not pyproject.is_file():
        return

    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="ignore"))
    except tomllib.TOMLDecodeError:
        dependencies.append(
            {
                "path": str(pyproject),
                "kind": "pyproject",
                "state": "malformed",
                "reason": "invalid_toml",
            }
        )
        results.append(
            error_result("security", None, f"malformed pyproject.toml: {pyproject}")
        )
        return

    project = data.get("project", {}) if isinstance(data, dict) else {}
    declared_deps = project.get("dependencies") if isinstance(project, dict) else None
    dynamic = project.get("dynamic") if isinstance(project, dict) else None
    dynamic_list = dynamic if isinstance(dynamic, list) else []

    if "dependencies" in dynamic_list:
        dependencies.append(
            {
                "path": str(pyproject),
                "kind": "pyproject",
                "state": "unresolved",
                "reason": "dynamic dependencies cannot be resolved without a build",
                "exclusions": ["dynamic"],
            }
        )
        return

    if not declared_deps:
        return

    entry: dict[str, Any] = {
        "path": str(pyproject),
        "kind": "pyproject",
        "state": "unresolved",
    }
    optional_deps = (
        project.get("optional-dependencies") if isinstance(project, dict) else None
    )
    if optional_deps:
        entry["exclusions"] = ["optional"]
    dependencies.append(entry)

    required = _ExecutionPermissions(
        network=True, download=True, cache_write=True, build=True
    )
    ok, _missing = check_permissions(required, permissions)
    if not ok:
        entry["state"] = "denied"
        entry["reason"] = "requires permissions: network, download, cache_write, build"
        results.append(
            skipped_result(
                "security",
                "pip-audit",
                "pyproject project-mode audit requires permissions: "
                "network, download, cache_write, build",
                metadata={"execution": _denied_execution(required, permissions)},
            )
        )
        return

    pip_result = run_engine(
        ENGINES["pip-audit"],
        project_root,
        ["--project-mode"],
        tool_name="security",
        required_permissions=required,
        **engine_kwargs,
    )
    results.append(pip_result)
    entry["state"] = "resolved-for-this-audit"
