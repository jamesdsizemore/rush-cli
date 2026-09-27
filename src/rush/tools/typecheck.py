"""Type-check Python and JavaScript/TypeScript source with discovered engines."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from ..permissions import ExecutionPermissions
from ..runtime.binaries import (
    AnalysisEnvironment,
    AnalysisScope,
    analysis_scope,
    select_analysis_environment,
)
from .base import ToolFn, ToolResult
from .common import elapsed_ms, engine_on_path, error_result, now_ms, run_engine
from .routing import aggregate_results, collect_files, detect_project_languages

if TYPE_CHECKING:
    from ..engines.base import Engine

# tsc executes no project interpreter; it only reads project type declarations.
_TSC_ENVIRONMENT: dict[str, Any] = {
    "mode": "project_files",
    "interpreter": None,
    "cause": "typescript_reads_project_type_declarations_no_execution",
    "permission": "not_required",
}


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


class TypecheckTool(ToolFn):
    name = "typecheck"

    @property
    def mcp_description(self) -> str:
        return "Type-check Python and JS/TS at <path>. Uses mypy or tsc; missing engines return status='skipped'."

    def __call__(
        self,
        path: Path,
        environment: Literal["project", "isolated"] | None = None,
        allow_build: bool = False,
    ) -> ToolResult:
        return self.run(path, environment=environment, allow_build=allow_build)

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
        return run_engine(
            engine,
            path,
            [*_interpreter_args(engine.name, env), *targets],
            tool_name=self.name,
            consumed_paths=targets,
            permissions=granted,
            required_permissions=(
                None if env.mode == "isolated" else ExecutionPermissions(build=True)
            ),
            project_root=root,
        )

    def run(
        self,
        path: Path,
        *,
        config=None,
        environment: Literal["project", "isolated"] | None = None,
        allow_build: bool = False,
    ) -> ToolResult:
        from ..engines import ENGINES

        start = now_ms()
        languages = detect_project_languages(path)
        engines = (ENGINES["mypy"], ENGINES["tsc"], ENGINES["pyrefly"])
        files = collect_files(
            path, {ext for engine in engines for ext in engine.file_extensions}
        )
        if not files:
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
        root = path if path.is_dir() else path.parent
        granted = ExecutionPermissions(build=allow_build)
        python_env = select_analysis_environment(root, environment, granted)
        results: list[ToolResult] = []
        environments: list[dict[str, Any]] = []
        for engine in engines:
            targets = [
                str(file)
                for file in files
                if file.suffix.lower().lstrip(".") in engine.file_extensions
            ]
            if not targets:
                continue
            if engine.name == "tsc":
                environment_record = dict(_TSC_ENVIRONMENT)
                engine_result = run_engine(
                    engine,
                    path,
                    targets,
                    tool_name=self.name,
                    consumed_paths=targets,
                    project_root=root,
                )
            else:
                environment_record = python_env.to_dict()
                engine_result = self._run_python_engine(
                    engine, path, root, targets, python_env, granted
                )
            metadata = dict(engine_result.get("metadata") or {})
            metadata.setdefault("analysis_environment", environment_record)
            engine_result["metadata"] = metadata
            environments.append(environment_record)
            results.append(engine_result)
        aggregated = aggregate_results(self.name, results)
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
        result: TypecheckResult = {**aggregated, "analysis_environment": selected}
        result["metadata"] = {
            **(result.get("metadata") or {}),
            "analysis_environment": selected,
        }
        return result
