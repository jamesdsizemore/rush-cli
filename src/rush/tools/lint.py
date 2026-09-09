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

from pathlib import Path
from typing import Any

from .base import Finding, ToolFn, ToolName, ToolResult, ToolStatus
from .common import (
    elapsed_ms,
    engine_on_path,
    now_ms,
    run_engine,
)
from .routing import collect_files, combine_status, detect_project_languages


def _build_skipped_result(start: int, summary: str) -> ToolResult:
    return ToolResult(
        tool="lint",
        engine=None,
        engine_version=None,
        status="skipped",
        duration_ms=elapsed_ms(start),
        summary=summary,
        findings=[],
        raw=None,
    )


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
) -> tuple[list[Finding], ToolStatus, list[str]]:
    """Execute each applicable engine sequentially and aggregate findings."""
    from ..engines import ENGINES

    findings_all: list[Finding] = []
    last_status: ToolStatus = "skipped"
    engines_used: list[str] = []

    for name in ("ruff", "eslint"):
        files = engine_files.get(name, [])
        if files:
            args = [str(p) for p in files] + (engine_args or [])
            r = run_engine(ENGINES[name], path, args, tool_name="lint")
            findings_all.extend(r.get("findings", []))
            engines_used.append(name)
            last_status = combine_status(last_status, r.get("status", "ok"))

    if engine_on_path("globstar"):
        globstar_args = [str(p) for p in targets] + (engine_args or [])
        r = run_engine(ENGINES["globstar"], path, globstar_args, tool_name="lint")
        findings_all.extend(r.get("findings", []))
        engines_used.append("globstar")
        last_status = combine_status(last_status, r.get("status", "ok"))

    return findings_all, last_status, engines_used


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
    summary = (
        f"lint: engines not installed ({', '.join(engines_missing)})"
        if engines_missing
        else "lint: no engines could run on these files"
    )
    return _build_skipped_result(start, summary)


def _assemble_lint_result(
    findings_all: list[Finding],
    last_status: ToolStatus,
    engines_used: list[str],
    start: int,
) -> ToolResult:
    """Assemble canonical ToolResult from aggregated engine findings and status."""
    status = last_status
    n_findings = len(findings_all)
    if status == "ok" and n_findings > 0:
        has_non_error = any(f.get("severity") != "error" for f in findings_all)
        status = "warn" if has_non_error else "fail"

    engine_str = "+".join(engines_used)
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
    )


class LintTool(ToolFn):
    name: ToolName = "lint"

    @property
    def mcp_description(self) -> str:
        return (
            "Lint Python/JS/TS files at <path>. Returns {status, findings[], summary}. "
            "Engines: ruff (Python), eslint (JS/TS). status='skipped' means engine not on PATH."
        )

    def __call__(self, path: Path, engine_args: list[str] | None = None) -> ToolResult:
        return self.run(path, engine_args=engine_args)

    def run(
        self, path: Path, *, engine_args: list[str] | None = None, config=None
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
            return _build_skipped_result(start, summary)

        findings, last_status, engines_used = _run_selected_engines(
            engine_files, targets, path, engine_args
        )
        if not engines_used:
            return _check_missing_engines_result(engine_files, start)

        return _assemble_lint_result(findings, last_status, engines_used, start)
