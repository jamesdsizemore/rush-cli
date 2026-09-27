"""Type-check Python and JavaScript/TypeScript source with discovered engines."""

from __future__ import annotations

import configparser
import os
import tomllib
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from ..io.physical_paths import ContainmentError, PhysicalRoot
from ..permissions import ExecutionPermissions, build_execution_metadata
from ..runtime.binaries import (
    AnalysisEnvironment,
    AnalysisScope,
    analysis_scope,
    select_analysis_environment,
)
from .base import ToolFn, ToolResult
from .common import (
    elapsed_ms,
    engine_on_path,
    error_result,
    now_ms,
    run_engine,
    skipped_result,
)
from .routing import (
    aggregate_results,
    classify_finding_scopes,
    collect_files,
    detect_project_languages,
    merge_scopes,
)

if TYPE_CHECKING:
    from ..engines.base import Engine

# tsc executes no project interpreter; it only reads project type declarations.
_TSC_ENVIRONMENT: dict[str, Any] = {
    "mode": "project_files",
    "interpreter": None,
    "cause": "typescript_reads_project_type_declarations_no_execution",
    "permission": "not_required",
}

# S12.7: freeform engine args that would select a different config.
_CONFIG_SELECTING_ARGS = ("-p", "--project", "--config-file", "--config")
_MYPY_CONFIG_NAMES = ("mypy.ini", ".mypy.ini", "pyproject.toml", "setup.cfg")
_PYREFLY_CONFIG_NAMES = ("pyrefly.toml", "pyproject.toml")
_MYPY_PLUGIN_REASON = (
    "requires permission: --allow-build (project mypy plugins execute code)"
)
_PYREFLY_PROGRAM_REASON = (
    "requires permission: --allow-build "
    "(project pyrefly interpreter config executes a program)"
)
# Finding 25: pyrefly config keys that make pyrefly execute a program.
_PYREFLY_PROGRAM_KEYS = (
    "python-interpreter-path",
    "python-interpreter-find-command",
    "fallback-python-interpreter-name",
    "conda-environment",
)


class TypecheckResult(ToolResult, total=False):
    analysis_environment: dict[str, Any]


def _interpreter_args(engine_name: str, env: AnalysisEnvironment) -> list[str]:
    """Environment argv for a Python checker (S11.1, R11.2).

    Isolated mode never lets the engine query or execute an interpreter the
    project configures: mypy's `--no-site-packages` also disables executable
    search (a config `python_executable` is dropped), and pyrefly's
    `--skip-interpreter-query` overrides its `python-interpreter-*` config.
    mypy's `--no-install-types` keeps a project config from triggering pip.
    """
    project = env.mode == "project" and env.interpreter is not None
    if engine_name == "mypy":
        selection = (
            ["--python-executable", str(env.interpreter)]
            if project
            else ["--no-site-packages"]
        )
        return [*selection, "--no-install-types"]
    if engine_name == "pyrefly":
        return (
            ["--python-interpreter-path", str(env.interpreter)]
            if project
            else ["--skip-interpreter-query"]
        )
    return []


def _config_families(config: Path) -> set[str]:
    """R12.5: which engines a literal `typecheck_config` applies to."""
    if config.suffix == ".json":
        return {"tsc"}
    if config.name == "pyproject.toml":
        return {"mypy", "pyrefly"}
    if config.name == "pyrefly.toml":
        return {"pyrefly"}
    if config.suffix in (".ini", ".cfg"):
        return {"mypy"}
    return set()


def _read_toml_tool(config: Path, tool: str) -> Any:
    return tomllib.loads(config.read_text(encoding="utf-8")).get("tool", {}).get(tool)


def _mypy_section(config: Path) -> dict[str, Any] | None:
    """The `[tool.mypy]`/`[mypy]` table; raises when unreadable."""
    if config.suffix == ".toml":
        section = _read_toml_tool(config, "mypy")
        return section if isinstance(section, dict) else None
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(config.read_text(encoding="utf-8"))
    return dict(parser["mypy"]) if parser.has_section("mypy") else None


def _declares(config: Path, engine: str) -> bool:
    """Design step 1: whether `config` is an owning config for `engine`. An
    unreadable candidate still owns (the engine reports it, never Rush)."""
    if config.name in ("mypy.ini", ".mypy.ini", "pyrefly.toml"):
        return True
    try:
        if engine == "pyrefly":
            return isinstance(_read_toml_tool(config, "pyrefly"), dict)
        return _mypy_section(config) is not None
    except (OSError, ValueError, configparser.Error):
        return True


def _owning_config(start: Path, root: Path, engine: str) -> Path | None:
    """Nearest ancestor config for `engine` from `start` up to `root`."""
    names = _MYPY_CONFIG_NAMES if engine == "mypy" else _PYREFLY_CONFIG_NAMES
    # Physical paths on both sides, so an aliased path still finds its config.
    directory = Path(os.path.realpath(start))
    root = Path(os.path.realpath(root))
    while directory == root or root in directory.parents:
        for name in names:
            candidate = directory / name
            if candidate.is_file() and _declares(candidate, engine):
                return candidate
        directory = directory.parent
    return None


def _pyrefly_executes_program(config: Path) -> bool:
    """Finding 25: whether the owning pyrefly config names a program for
    pyrefly to execute. An unreadable config fails closed."""
    try:
        if config.name == "pyproject.toml":
            section = _read_toml_tool(config, "pyrefly")
        else:
            section = tomllib.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return isinstance(section, dict) and any(
        str(key).replace("_", "-") in _PYREFLY_PROGRAM_KEYS for key in section
    )


def _mypy_plugins_declared(config: Path) -> bool:
    """S12.5: an unreadable config fails closed (it may declare plugins)."""
    try:
        section = _mypy_section(config)
    except (OSError, ValueError, configparser.Error):
        return True
    return bool(section and section.get("plugins"))


def _config_error(code: str, message: str) -> ToolResult:
    return error_result(
        "typecheck",
        None,
        message,
        metadata={"error": {"code": code, "message": message}},
    )


def _logical_root(path: Path) -> Path:
    from ..invocation.targets import resolve_logical_root

    return Path(resolve_logical_root(Path(os.path.abspath(path))))


def _engine_args(config: Any, logical_root: Path) -> list[str]:
    """Existing freeform engine args: `[tools.typecheck] engine_args`."""
    if config is None:
        from ..config import load_config

        config = load_config(start=logical_root)
    tool = getattr(config, "tools", {}).get("typecheck")
    return [str(arg) for arg in getattr(tool, "engine_args", None) or []]


def _validate_config(
    value: str, logical_root: Path, config: Any
) -> tuple[Path, set[str]] | ToolResult:
    """S12.7: the explicit config wins, lies within the logical root, is
    family-checked, and no freeform engine arg may select another config."""
    from ..config import RushConfigError

    literal = Path(os.path.abspath(value))
    real = Path(os.path.realpath(literal))
    if not real.is_file():
        return _config_error(
            "TYPECHECK_CONFIG_NOT_FOUND",
            f"typecheck: --typecheck-config {literal} is not an existing regular file",
        )
    outside = _config_error(
        "TYPECHECK_CONFIG_OUTSIDE_ROOT",
        f"typecheck: --typecheck-config {real} lies outside the project root "
        f"{logical_root}",
    )
    try:
        PhysicalRoot(logical_root).open_contained(
            literal.relative_to(logical_root), purpose="read"
        )
    except (ValueError, ContainmentError):
        return outside
    families = _config_families(literal)
    if not families:
        return _config_error(
            "TYPECHECK_CONFIG_INVALID",
            f"typecheck: --typecheck-config {literal} is not a tsconfig (.json), "
            "mypy (mypy.ini, .mypy.ini, setup.cfg, pyproject.toml) or pyrefly "
            "(pyrefly.toml, pyproject.toml) config",
        )
    try:
        engine_args = _engine_args(config, logical_root)
    except RushConfigError as exc:
        return _config_error("TYPECHECK_CONFIG_INVALID", f"typecheck: {exc}")
    for arg in engine_args:
        if any(
            arg == flag or arg.startswith(flag + "=") for flag in _CONFIG_SELECTING_ARGS
        ):
            return _config_error(
                "TYPECHECK_CONFIG_CONFLICT",
                f"typecheck: engine_args {arg!r} conflicts with --typecheck-config "
                f"{literal}",
            )
    return literal, families


def _python_scope(
    logical_root: Path,
    path: Path,
    targets: list[str],
    dependencies: list[str],
    config: Path | None,
    cwd: Path,
    status: str,
) -> dict[str, Any]:
    """S12.2 scope for a Python checker: it reports no consumed-file list,
    so consumption is unavailable, never guessed."""
    return {
        "version": 1,
        "kind": "file",
        "logical_root": str(logical_root),
        "requested_targets": [str(path)],
        "requested_file_count": len(targets),
        "matched_file_count": len(targets),
        "consumed_file_count": None,
        "coverage": "unavailable",
        "reason": "engine_reports_no_consumed_files",
        "dependency_files": dependencies,
        "ambient_files": [],
        "configuration_files": [] if config is None else [str(config)],
        "excluded_files": [],
        "unclassifiable": False,
        "unclassifiable_files": [],
        "explicit_override": False,
        "engine_library_file_count": None,
        "groups": [
            {
                "config": None if config is None else str(config),
                "explicit_override": False,
                "cwd": str(cwd),
                "status": status,
                "codes": [],
                "requested_files": sorted(targets),
                "dependency_files": dependencies,
                "ambient_files": [],
                "consumed_file_count": None,
            }
        ],
    }


def _tsc_targets_present(path: Path) -> bool:
    from ..engines.tsc import FAMILY_SUFFIXES, directory_pool

    if path.is_dir():
        return bool(directory_pool(path))
    return path.suffix in FAMILY_SUFFIXES


class TypecheckTool(ToolFn):
    name = "typecheck"

    @property
    def mcp_description(self) -> str:
        return "Type-check Python and JS/TS at <path>. Uses mypy or tsc; missing engines return status='skipped'."

    def __call__(
        self,
        path: Path,
        environment: Literal["project", "isolated"] | None = None,
        typecheck_config: str | None = None,
        allow_build: bool = False,
        allow_cache_write: bool = False,
    ) -> ToolResult:
        return self.run(
            path,
            environment=environment,
            typecheck_config=typecheck_config,
            allow_build=allow_build,
            allow_cache_write=allow_cache_write,
        )

    def _unsupported_engine(self, engine: Engine, root: Path) -> str | None:
        """R11.5: pyrefly runs only at or above its pinned minimum and when
        this binary's own `check --help` offers both selection flags."""
        from ..engines.pyrefly import PyreflyEngine

        if not isinstance(engine, PyreflyEngine):
            return None
        with analysis_scope(
            AnalysisScope(root, engine_id=engine.name, binary=engine.binary)
        ):
            if not engine_on_path(engine.binary):
                return None
            return engine.support_problem()

    def _run_python_engine(
        self,
        engine: Engine,
        path: Path,
        root: Path,
        targets: list[str],
        env: AnalysisEnvironment,
        granted: ExecutionPermissions,
        config: Path | None,
        cwd: Path,
    ) -> ToolResult:
        problem = (
            self._unsupported_engine(engine, root) if env.mode != "denied" else None
        )
        if problem is not None:
            return error_result(
                self.name,
                engine.name,
                f"engine-unsupported: {problem}; not run",
                metadata={
                    "engine_support": "engine-unsupported",
                    "analysis_environment": {
                        **env.to_dict(),
                        "mode": "isolated",
                        "cause": "engine_lacks_interpreter_selection",
                    },
                },
            )
        flag = "--config-file" if engine.name == "mypy" else "--config"
        config_args = [] if config is None else [flag, str(config)]
        return run_engine(
            engine,
            path,
            [*_interpreter_args(engine.name, env), *config_args, *targets],
            cwd=cwd,
            tool_name=self.name,
            consumed_paths=targets,
            permissions=granted,
            required_permissions=(
                None if env.mode == "isolated" else ExecutionPermissions(build=True)
            ),
            project_root=root,
        )

    def _python_child(
        self,
        engine: Engine,
        path: Path,
        root: Path,
        logical_root: Path,
        targets: list[str],
        env: AnalysisEnvironment,
        granted: ExecutionPermissions,
        explicit: Path | None,
    ) -> ToolResult:
        """Design steps 1-2 and S12.5 for mypy/pyrefly."""
        start = path if path.is_dir() else path.parent
        config = explicit or _owning_config(start, logical_root, engine.name)
        # S12.5 / finding 25: a config that makes the engine execute project
        # code needs the build grant, checked before any spawn (including
        # the version and `check --help` probes).
        gate = (
            None
            if config is None or granted.build
            else _MYPY_PLUGIN_REASON
            if engine.name == "mypy" and _mypy_plugins_declared(config)
            else _PYREFLY_PROGRAM_REASON
            if engine.name == "pyrefly" and _pyrefly_executes_program(config)
            else None
        )
        if gate is not None:
            return skipped_result(
                self.name,
                engine.name,
                gate,
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=ExecutionPermissions(build=True),
                        granted=granted,
                        producer=engine.name,
                    )
                },
            )
        cwd = logical_root if config is None else config.parent
        result = self._run_python_engine(
            engine, path, root, targets, env, granted, config, cwd
        )
        if result.get("status") in ("skipped", "error") and not result.get("findings"):
            return result
        dependencies = classify_finding_scopes(
            result.get("findings") or [],
            targets,
            [] if config is None else [str(config)],
        )
        metadata = dict(result.get("metadata") or {})
        metadata["scope"] = _python_scope(
            logical_root,
            path,
            targets,
            dependencies,
            config,
            cwd,
            str(result.get("status")),
        )
        result["metadata"] = metadata
        return result

    def run(
        self,
        path: Path,
        *,
        config=None,
        environment: Literal["project", "isolated"] | None = None,
        typecheck_config: str | None = None,
        allow_build: bool = False,
        allow_cache_write: bool = False,
    ) -> ToolResult:
        from ..engines import ENGINES

        start = now_ms()
        languages = detect_project_languages(path)
        python_engines = (ENGINES["mypy"], ENGINES["pyrefly"])
        files = collect_files(
            path, {ext for engine in python_engines for ext in engine.file_extensions}
        )
        tsc_present = _tsc_targets_present(path)
        if not files and not tsc_present:
            return ToolResult(
                tool=self.name,
                engine=None,
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=(
                    "typecheck: detected "
                    + ", ".join(languages)
                    + " project markers, but their adapters are feasibility-gated"
                    if languages
                    else f"typecheck: no supported source files found under {path}"
                ),
                findings=[],
                raw=None,
            )
        logical_root = _logical_root(path)
        explicit: Path | None = None
        families: set[str] = set()
        if typecheck_config is not None:
            validated = _validate_config(typecheck_config, logical_root, config)
            if not isinstance(validated, tuple):
                validated["duration_ms"] = elapsed_ms(start)
                return validated
            explicit, families = validated
        root = path if path.is_dir() else path.parent
        granted = ExecutionPermissions(build=allow_build, cache_write=allow_cache_write)
        # Engine order is mypy, tsc, pyrefly.
        children: list[tuple[dict[str, Any], Callable[[], ToolResult]]] = []
        python: dict[str, Callable[[], ToolResult]] = {}
        python_record: dict[str, Any] = {}
        if files:
            python_env = select_analysis_environment(root, environment, granted)
            python_record = python_env.to_dict()
            targets = [str(file) for file in files]
            for engine in python_engines:
                python[engine.name] = partial(
                    self._python_child,
                    engine,
                    path,
                    root,
                    logical_root,
                    targets,
                    python_env,
                    granted,
                    explicit if engine.name in families else None,
                )
            children.append((python_record, python["mypy"]))
        if tsc_present:
            # R12.4: tsc needs only cache-write, checked before any spawn.
            children.append(
                (
                    dict(_TSC_ENVIRONMENT),
                    partial(
                        run_engine,
                        ENGINES["tsc"],
                        path,
                        ["-p", str(explicit)] if "tsc" in families else [],
                        tool_name=self.name,
                        permissions=granted,
                        required_permissions=ExecutionPermissions(cache_write=True),
                        consumed_paths=[str(path)],
                        project_root=root,
                    ),
                )
            )
        if files:
            children.append((python_record, python["pyrefly"]))
        results: list[ToolResult] = []
        environments: list[dict[str, Any]] = []
        for record, child in children:
            environment_record = dict(record)
            engine_result = child()
            metadata = dict(engine_result.get("metadata") or {})
            metadata.setdefault("analysis_environment", environment_record)
            engine_result["metadata"] = metadata
            environments.append(environment_record)
            results.append(engine_result)
        return self._assemble(results, environments, start)

    def _assemble(
        self,
        results: list[ToolResult],
        environments: list[dict[str, Any]],
        start: int,
    ) -> ToolResult:
        aggregated = aggregate_results(self.name, results)
        # Finding 9 (owner): every engine this tool runs is required, so a
        # skipped engine next to an ok one is never a clean result (plan
        # §3.2: mixed ok+skipped is promoted to warn; T16 owns precedence).
        if aggregated["status"] == "ok" and any(
            item.get("status") == "skipped" for item in results
        ):
            aggregated["status"] = "warn"
        # Permission denials and unsupported engines stay visible in the
        # aggregate summary rather than disappearing behind a finding count.
        notices = [
            f"{item.get('engine')}: {item.get('summary')}"
            for item in results
            if "requires permission:" in str(item.get("summary", ""))
            or (item.get("metadata") or {}).get("engine_support")
            == "engine-unsupported"
        ]
        if notices:
            aggregated["summary"] += " (" + "; ".join(notices) + ")"
        aggregated["duration_ms"] = elapsed_ms(start)
        if not environments:
            return aggregated
        # The Python interpreter decision leads; tsc-only runs report tsc's.
        selected = next(
            (item for item in environments if item["mode"] != "project_files"),
            environments[0],
        )
        metadata: dict[str, Any] = {
            **(aggregated.get("metadata") or {}),
            "analysis_environment": selected,
        }
        # A13: the children's scopes merged; the first child error leads.
        scope = merge_scopes(
            [
                (str(item.get("engine")), (item.get("metadata") or {})["scope"])
                for item in results
                if (item.get("metadata") or {}).get("scope")
            ]
        )
        if scope is not None:
            metadata["scope"] = scope
        error = next(
            (
                (item.get("metadata") or {})["error"]
                for item in results
                if (item.get("metadata") or {}).get("error")
            ),
            None,
        )
        if error is not None:
            metadata["error"] = error
        result: TypecheckResult = {**aggregated, "analysis_environment": selected}
        result["metadata"] = metadata
        return result
