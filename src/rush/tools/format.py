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

from .base import ToolFn, ToolName, ToolResult
from .common import elapsed_ms, now_ms, run_engine


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
        targets = _collect_files(path)

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

        ruff_files = [t for t in targets if t.suffix.lstrip(".") in ENGINES["ruff"].file_extensions]
        prettier_files = [t for t in targets if t.suffix.lstrip(".") in ENGINES["prettier"].file_extensions]

        findings_all: list = []
        engines_used: list[str] = []
        last_status = "ok"

        if ruff_files:
            argv = ["format", "--check", *[str(p) for p in ruff_files]]
            r = run_engine(ENGINES["ruff"], path, argv, tool_name="format")
            findings_all.extend(self._parse_ruff_format(r))
            engines_used.append("ruff")
            last_status = _combine_status(last_status, r.get("status", "ok"))

        if prettier_files:
            argv = ["--check", *[str(p) for p in prettier_files]]
            r = run_engine(ENGINES["prettier"], path, argv, tool_name="format")
            findings_all.extend(r.get("findings", []))
            engines_used.append("prettier")
            last_status = _combine_status(last_status, r.get("status", "ok"))

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
            status = "ok"
            summary = f"format [{'+'.join(engines_used)}]: all formatted"
        else:
            status = "warn"
            summary = f"format [{'+'.join(engines_used)}]: {n} file(s) need reformatting"

        return ToolResult(
            tool="format",
            engine="+".join(engines_used),
            engine_version=None,
            status=status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings_all,
            raw=None,
        )

    @staticmethod
    def _parse_ruff_format(result: dict) -> list:
        """ruff format --check prints filenames needing reformat to stdout."""
        out = []
        for line in (result.get("stdout") or "").splitlines():
            line = line.strip()
            if line and not line.startswith(("Found", "reformat")):
                # Lines look like: "file.py:62:80:"
                if ":" in line:
                    file_part = line.split(":")[0]
                    out.append({
                        "path": file_part,
                        "line": 0,
                        "rule": "formatting",
                        "severity": "warn",
                        "message": "ruff format would reformat this file",
                    })
        # ruff also exits non-zero when files need reformat; check status
        if result.get("status") == "warn" and not out:
            # Try stderr for the file list
            for line in (result.get("stderr") or "").splitlines():
                line = line.strip()
                if line.endswith("would be reformatted"):
                    # line like: "Would reformat: file.py"
                    fname = line.replace("Would reformat:", "").replace("would be reformatted", "").strip()
                    if fname:
                        out.append({
                            "path": fname,
                            "line": 0,
                            "rule": "formatting",
                            "severity": "warn",
                            "message": "ruff format would reformat this file",
                        })
        return out


def _collect_files(path: Path) -> list[Path]:
    from ..engines import ENGINES
    exts: set[str] = set()
    for e in ENGINES.values():
        exts.update(e.file_extensions)

    if path.is_file():
        return [path] if path.suffix.lstrip(".") in exts else []

    if path.is_dir():
        out: list[Path] = []
        for ext in exts:
            out.extend(path.rglob(f"*.{ext}"))
        skip_dirs = {".venv", "venv", "node_modules", "__pycache__", ".git", "dist", "build", ".next"}
        return [
            p for p in out
            if not any(part in skip_dirs for part in p.parts)
        ]
    return []


def _combine_status(a: str, b: str) -> str:
    rank = {"error": 4, "fail": 3, "warn": 2, "ok": 1, "skipped": 0}
    return a if rank.get(a, 0) >= rank.get(b, 0) else b
