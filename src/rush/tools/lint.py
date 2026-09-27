"""Lint tool — engine dispatch per file extension.

Architecture §4.3 + §10. Wires ruff (Python) and eslint (JS/TS) through
``tools/common.py:run_engine``.

Routing rule (per architecture §4.3):
  - For each file matching `path`, look up engine by extension.
  - If path is a directory, walk it and dispatch per-file.
  - If no file matches any supported extension, return ``skipped``.

Each tool invocation runs each engine exactly once and aggregates the
findings. Sequential execution per architecture §13 Q2 (determinism > speed).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .base import Finding, ToolFn, ToolName, ToolResult, ToolStatus
from .common import (
    elapsed_ms,
    engine_on_path,
    now_ms,
    run_engine,
)
from .routing import (
    aggregate_status,
    collect_files,
    concat_engine_entries,
    detect_project_languages,
    no_target_scope,
)


def _build_skipped_result(
    start: int,
    summary: str,
    scope: dict[str, Any] | None = None,
    children: list[ToolResult] | None = None,
) -> ToolResult:
    result = ToolResult(
        tool="lint",
        engine=None,
        engine_version=None,
        status="skipped",
        duration_ms=elapsed_ms(start),
        summary=summary,
        findings=[],
        raw=None,
    )
    if scope is not None:
        result["metadata"] = {
            "scope": scope,
            "engines": concat_engine_entries(children or []),
        }
    return result


def _select_engines(
    path: Path, config: Any = None
) -> tuple[list[Path], dict[str, list[Path]], list[str]]:
    """Identify project languages and partition target files by engine."""
    from ..engines import ENGINES

    languages = detect_project_languages(path)
    supported_extensions = {
        extension for engine in ENGINES.values() for extension in engine.file_extensions
    }
    targets = collect_files(path, supported_extensions)
    engine_files = {
        name: [t for t in targets if t.suffix.lstrip(".") in engine.file_extensions]
        for name, engine in ENGINES.items()
        if name in ("ruff", "eslint")
    }
    return targets, engine_files, languages


def _run_selected_engines(
    engine_files: dict[str, list[Path]],
    targets: list[Path],
    path: Path,
    engine_args: list[str] | None = None,
    *,
    owner_instance_id: str | None = None,
    run_id: str | None = None,
    skip_reasons: list[str] | None = None,
) -> tuple[list[ToolResult], list[str]]:
    """Execute each applicable engine sequentially and keep every child.

    T9: an engine that returned `skipped` (e.g. `ruff not on PATH`) has its
    own reason appended to `skip_reasons`, so the lint summary can name it.
    T16 (finding 24): ruff also runs its `--show-files` scope probe."""
    from ..engines import ENGINES

    children: list[ToolResult] = []
    engines_used: list[str] = []
    reasons = skip_reasons if skip_reasons is not None else []

    for name in ("ruff", "eslint"):
        files = engine_files.get(name, [])
        if files:
            args = [str(p) for p in files] + (engine_args or [])
            r = run_engine(
                ENGINES[name],
                path,
                args,
                tool_name="lint",
                owner_instance_id=owner_instance_id,
                run_id=run_id,
                consumed_paths=[str(p) for p in files],
                scope_probe=name == "ruff",
            )
            children.append(r)
            engines_used.append(name)
            if r.get("status") == "skipped":
                reasons.append(str(r.get("summary", "")).removeprefix("skipped: "))

    if engine_on_path("globstar"):
        globstar_args = [str(p) for p in targets] + (engine_args or [])
        children.append(
            run_engine(
                ENGINES["globstar"],
                path,
                globstar_args,
                tool_name="lint",
                owner_instance_id=owner_instance_id,
                run_id=run_id,
                consumed_paths=[str(p) for p in targets],
            )
        )
        engines_used.append("globstar")

    return children, engines_used


def _identity(path: str | Path) -> tuple[int, int] | None:
    try:
        st = os.stat(path)
    except (OSError, ValueError):
        return None
    return (st.st_dev, st.st_ino)


def _consumed_files(children: list[ToolResult]) -> tuple[list[str], list[str], str]:
    """Every file an executed engine reported consuming, its configuration
    inputs, and where the list came from (T16 design step 5, finding 24)."""
    consumed: list[str] = []
    configuration: list[str] = []
    source = "explicit_arguments"
    for entry in concat_engine_entries(children):
        scope = entry.get("scope") or {}
        if scope.get("consumption_source") == "engine_show_files":
            source = "engine_show_files"
            consumed.extend(scope.get("consumed_files") or [])
            configuration.extend(scope.get("configuration_files") or [])
    return consumed, sorted(set(configuration)), source


def _executed_engines(children: list[ToolResult]) -> set[str]:
    return {
        str(entry.get("engine"))
        for entry in concat_engine_entries(children)
        if (entry.get("executable") or {}).get("path")
    }


def _explicit_consumption(
    engine_files: dict[str, list[Path]], children: list[ToolResult]
) -> list[str]:
    """Files handed explicitly to an executed engine without a listing."""
    listed = {
        entry.get("engine")
        for entry in concat_engine_entries(children)
        if (entry.get("scope") or {}).get("consumption_source") == "engine_show_files"
    }
    executed = _executed_engines(children)
    return [
        str(file)
        for name, files in engine_files.items()
        if name in executed and name not in listed
        for file in files
    ]


def _excluded_files(
    engine_files: dict[str, list[Path]],
    children: list[ToolResult],
    consumed: dict[tuple[int, int], str],
) -> list[dict[str, str]]:
    """Requested files no engine consumed: `engine_excluded` when their
    engine ran (its own configuration left them out), `engine_unavailable`
    when it never ran (missing, denied or crashed before spawning)."""
    executed = _executed_engines(children)
    excluded: dict[str, dict[str, str]] = {}
    for name, files in engine_files.items():
        for file in files:
            if _identity(file) in consumed or str(file) in excluded:
                continue
            reason = "engine_excluded" if name in executed else "engine_unavailable"
            excluded[str(file)] = {"path": str(file), "reason": reason}
    return list(excluded.values())


def lint_scope(
    requested: list[Path],
    engine_files: dict[str, list[Path]],
    children: list[ToolResult],
    root: Path,
) -> dict[str, Any]:
    """T16 design step 5: requested = files matched under the target;
    consumed = files the executed engines consumed (finding 24: ruff's own
    `--show-files` listing), as physical identities `(st_dev, st_ino)`."""
    listed, configuration, source = _consumed_files(children)
    consumed = {
        ident: path
        for path in [*listed, *_explicit_consumption(engine_files, children)]
        if (ident := _identity(path))
    }
    excluded = _excluded_files(engine_files, children, consumed)
    if not consumed:
        coverage = "none"
    else:
        coverage = "partial" if excluded else "complete"
    return {
        "version": 1,
        "kind": "file",
        "logical_root": str(root),
        "requested_targets": [str(root)],
        "requested_file_count": len(requested),
        "matched_file_count": len(requested),
        "consumed_file_count": len(consumed),
        "consumption_source": source,
        "configuration_files": configuration,
        "excluded_files": excluded,
        "coverage": coverage,
        "reason": None if coverage == "complete" else "requested_files_not_consumed",
    }


def _check_missing_engines_result(
    engine_files: dict[str, list[Path]], start: int
) -> ToolResult:
    """Return a skipped result when required engines are missing from PATH."""
    ruff_files = engine_files.get("ruff", [])
    eslint_files = engine_files.get("eslint", [])
    engines_missing = []
    if ruff_files and not engine_on_path("ruff"):
        engines_missing.append("ruff")
    if eslint_files and not engine_on_path("eslint"):
        engines_missing.append("eslint")
    if engines_missing:
        return _build_skipped_result(
            start,
            f"lint: engines not installed ({', '.join(engines_missing)})",
            no_target_scope(
                "engine_unavailable",
                matched_file_count=len(ruff_files) + len(eslint_files),
                consumed_file_count=0,
            ),
        )
    return _build_skipped_result(
        start,
        "lint: no engines could run on these files",
        no_target_scope(
            "no_supported_targets", matched_file_count=0, consumed_file_count=0
        ),
    )


def _assemble_lint_result(
    children: list[ToolResult],
    engines_used: list[str],
    start: int,
    skip_reasons: list[str] | None = None,
    scope: dict[str, Any] | None = None,
    matched_file_count: int = 0,
) -> ToolResult:
    """Assemble canonical ToolResult from every engine child.

    T9: when every engine that should have run was skipped, the summary names
    each engine's own reason (e.g. `ruff not on PATH`) and the scope records
    that nothing was consumed (`engine_unavailable`). T16 (S16.3): the status
    aggregates every child once (mixed ok+skipped is warn)."""
    findings_all: list[Finding] = [
        finding for child in children for finding in child.get("findings", [])
    ]
    status: ToolStatus = aggregate_status(
        str(child.get("status", "ok")) for child in children
    )
    n_findings = len(findings_all)
    if status == "ok" and n_findings > 0:
        has_non_error = any(f.get("severity") != "error" for f in findings_all)
        status = "warn" if has_non_error else "fail"

    engine_str = "+".join(engines_used)
    if status == "skipped" and not n_findings and skip_reasons:
        result = _build_skipped_result(
            start,
            f"lint [{engine_str}]: {'; '.join(skip_reasons)}",
            no_target_scope(
                "engine_unavailable",
                matched_file_count=matched_file_count,
                consumed_file_count=0,
            ),
            children,
        )
        result["engine"] = engine_str
        return result
    summary = (
        f"lint [{engine_str}]: {n_findings} issue(s)"
        if n_findings
        else (
            f"lint [{engine_str}]: clean"
            if status == "ok"
            else f"lint [{engine_str}]: {status}"
        )
    )

    return ToolResult(
        tool="lint",
        engine=engine_str,
        engine_version=None,
        status=status,
        duration_ms=elapsed_ms(start),
        summary=summary,
        findings=findings_all,
        raw=None,
        metadata={"engines": concat_engine_entries(children), "scope": scope},
    )


class LintTool(ToolFn):
    name: ToolName = "lint"

    @property
    def mcp_description(self) -> str:
        return (
            "Lint Python/JS/TS files at <path>. Returns {status, findings[], summary}. "
            "Engines: ruff (Python), eslint (JS/TS). status='skipped' means engine not on PATH."
        )

    def __call__(
        self,
        path: Path,
        engine_args: list[str] | None = None,
        owner_instance_id: str | None = None,
        run_id: str | None = None,
    ) -> ToolResult:
        return self.run(
            path,
            engine_args=engine_args,
            owner_instance_id=owner_instance_id,
            run_id=run_id,
        )

    def run(
        self,
        path: Path,
        *,
        engine_args: list[str] | None = None,
        config=None,
        owner_instance_id: str | None = None,
        run_id: str | None = None,
    ) -> ToolResult:
        start = now_ms()
        targets, engine_files, languages = _select_engines(path, config)
        if not targets:
            summary = (
                "lint: detected "
                + ", ".join(languages)
                + " project markers, but their adapters are feasibility-gated"
                if languages
                else f"lint: no Python/JS/TS files found under {path}"
            )
            return _build_skipped_result(
                start,
                summary,
                no_target_scope(
                    "no_supported_targets", matched_file_count=0, consumed_file_count=0
                ),
            )

        skip_reasons: list[str] = []
        children, engines_used = _run_selected_engines(
            engine_files,
            targets,
            path,
            engine_args,
            owner_instance_id=owner_instance_id,
            run_id=run_id,
            skip_reasons=skip_reasons,
        )
        if not engines_used:
            return _check_missing_engines_result(engine_files, start)

        dispatched = dict(engine_files)
        if "globstar" in engines_used:
            dispatched["globstar"] = targets
        requested = list(
            dict.fromkeys(file for files in dispatched.values() for file in files)
        )
        root = path if path.is_dir() else path.parent
        return _assemble_lint_result(
            children,
            engines_used,
            start,
            skip_reasons,
            scope=lint_scope(requested, dispatched, children, root),
            matched_file_count=sum(len(files) for files in engine_files.values()),
        )
