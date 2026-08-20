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

from .base import ToolFn, ToolName, ToolResult
from .common import (
    elapsed_ms,
    engine_on_path,
    now_ms,
    run_engine,
)
from .routing import collect_files, combine_status, detect_project_languages


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
        from ..engines import ENGINES

        start = now_ms()
        languages = detect_project_languages(path)
        # Walk path: if it's a directory, find all supported files. If it's
        # a file, dispatch on its extension directly.
        targets = collect_files(
            path,
            {
                extension
                for engine in ENGINES.values()
                for extension in engine.file_extensions
            },
        )

        if not targets:
            return ToolResult(
                tool="lint",
                engine=None,
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=(
                    "lint: detected "
                    + ", ".join(languages)
                    + " project markers, but their adapters are feasibility-gated"
                    if languages
                    else f"lint: no Python/JS/TS files found under {path}"
                ),
                findings=[],
                raw=None,
            )

        # Dispatch: group by engine, run each engine once with its file list.
        ruff_files = [
            t
            for t in targets
            if t.suffix.lstrip(".") in ENGINES["ruff"].file_extensions
        ]
        eslint_files = [
            t
            for t in targets
            if t.suffix.lstrip(".") in ENGINES["eslint"].file_extensions
        ]

        findings_all: list = []
        last_status = "ok"
        engines_used: list[str] = []
        summaries: list[str] = []

        if ruff_files:
            ruff_args = [str(p) for p in ruff_files] + (engine_args or [])
            r = run_engine(ENGINES["ruff"], path, ruff_args, tool_name="lint")
            findings_all.extend(r.get("findings", []))
            engines_used.append("ruff")
            summaries.append(r.get("summary", ""))
            last_status = combine_status(last_status, r.get("status", "ok"))

        if eslint_files:
            eslint_args = [str(p) for p in eslint_files] + (engine_args or [])
            r = run_engine(ENGINES["eslint"], path, eslint_args, tool_name="lint")
            findings_all.extend(r.get("findings", []))
            engines_used.append("eslint")
            summaries.append(r.get("summary", ""))
            last_status = combine_status(last_status, r.get("status", "ok"))

        if engine_on_path("globstar"):
            globstar_args = [str(p) for p in targets] + (engine_args or [])
            r = run_engine(ENGINES["globstar"], path, globstar_args, tool_name="lint")
            findings_all.extend(r.get("findings", []))
            engines_used.append("globstar")
            summaries.append(r.get("summary", ""))
            last_status = combine_status(last_status, r.get("status", "ok"))

        # If neither engine is installed, return a single skipped result.
        if not engines_used:
            engines_missing = []
            if ruff_files and not engine_on_path("ruff"):
                engines_missing.append("ruff")
            if eslint_files and not engine_on_path("eslint"):
                engines_missing.append("eslint")
            return ToolResult(
                tool="lint",
                engine=None,
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"lint: engines not installed ({', '.join(engines_missing)})",
                findings=[],
                raw=None,
            )

        # If we found files but no engines could be used (because none of the
        # files matched an installed engine), still return skipped.
        if not engines_used and (ruff_files or eslint_files):
            return ToolResult(
                tool="lint",
                engine=None,
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary="lint: no engines could run on these files",
                findings=[],
                raw=None,
            )

        n_findings = len(findings_all)
        if last_status == "ok" and n_findings > 0:
            last_status = (
                "warn"
                if any(f.get("severity") != "error" for f in findings_all)
                else "fail"
            )
            if all(f.get("severity") == "error" for f in findings_all):
                last_status = "fail"

        engine_str = "+".join(engines_used)
        if n_findings:
            summary = f"lint [{engine_str}]: {n_findings} issue(s)"
        else:
            summary = f"lint [{engine_str}]: clean"

        return ToolResult(
            tool="lint",
            engine=engine_str,
            engine_version=None,
            status=last_status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings_all,
            raw=None,
        )
