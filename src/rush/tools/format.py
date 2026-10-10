"""Format tool — engine dispatch per file extension.

Architecture §4.3 + §10. Wires ruff format (Python) and prettier --check
(JS/TS + JSON/MD/YAML/CSS/HTML).

Important: v0.1 always runs --check mode for prettier — never mutates
files silently. The user must invoke `rush format <path>` and accept the
changes; the tool reports what WOULD change as findings.

For ruff format, we likewise use `--check` so the tool reports files that
need reformatting without modifying them. Future v0.2 may add an explicit
`--write` flag.
"""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolName, ToolResult, ToolStatus
from .common import elapsed_ms, now_ms, run_engine
from .routing import aggregate_status, collect_files, concat_engine_entries


class FormatTool(ToolFn):
    name: ToolName = "format"

    @property
    def mcp_description(self) -> str:
        return (
            "Format Python/JS/TS files at <path>. Returns {status, findings[], summary}. "
            "Engines: ruff format (Python), prettier (JS/TS). Always check-only in v0.1."
        )

    def __call__(self, path: Path, check: bool = False) -> ToolResult:
        return self.run(path, check=check)

    def run(self, path: Path, *, check: bool = False, config=None) -> ToolResult:
        # v0.1 always treats check=True (no file mutation). The CLI flag is
        # accepted for forward compatibility but ignored.
        from ..engines import ENGINES

        start = now_ms()
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
                tool="format",
                engine=None,
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"format: no Python/JS/TS files found under {path}",
                findings=[],
                raw=None,
            )

        ruff_files = [
            t
            for t in targets
            if t.suffix.lstrip(".") in ENGINES["ruff"].file_extensions
        ]
        prettier_files = [
            t
            for t in targets
            if t.suffix.lstrip(".") in ENGINES["prettier"].file_extensions
        ]

        # T16 (R16.1, S16.3): keep every engine child and aggregate once --
        # no `skipped` sentinel, which the new precedence would turn into warn.
        children: list[ToolResult] = []
        engines_used: list[str] = []

        if ruff_files:
            argv = ["format", "--check", *[str(p) for p in ruff_files]]
            children.append(
                run_engine(
                    ENGINES["ruff"],
                    path,
                    argv,
                    tool_name="format",
                    consumed_paths=[str(p) for p in ruff_files],
                )
            )
            engines_used.append("ruff")

        if prettier_files:
            argv = ["--check", *[str(p) for p in prettier_files]]
            children.append(
                run_engine(
                    ENGINES["prettier"],
                    path,
                    argv,
                    tool_name="format",
                    consumed_paths=[str(p) for p in prettier_files],
                )
            )
            engines_used.append("prettier")

        findings_all: list = [
            finding for child in children for finding in child.get("findings", [])
        ]
        last_status: ToolStatus = aggregate_status(
            str(child.get("status", "ok")) for child in children
        )

        if not engines_used:
            return ToolResult(
                tool="format",
                engine=None,
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary="format: ruff + prettier not installed",
                findings=[],
                raw=None,
            )

        n = len(findings_all)
        if n == 0:
            status: ToolStatus = last_status
            summary = (
                f"format [{'+'.join(engines_used)}]: all formatted"
                if status == "ok"
                else f"format [{'+'.join(engines_used)}]: engine {status}"
            )
        else:
            status = aggregate_status([last_status, "warn"])
            summary = (
                f"format [{'+'.join(engines_used)}]: engine error"
                if status == "error"
                else f"format [{'+'.join(engines_used)}]: {n} file(s) need reformatting"
            )

        return ToolResult(
            tool="format",
            engine="+".join(engines_used),
            engine_version=None,
            status=status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings_all,
            raw=None,
            metadata={"engines": concat_engine_entries(children)},
        )
