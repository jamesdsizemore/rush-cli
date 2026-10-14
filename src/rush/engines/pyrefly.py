"""Pyrefly adapter for fast Rust-based Python type checking."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import ClassVar

from ..tools.base import Finding, ToolResult, ToolStatus
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult, ownership_kwargs

# Exact pyrefly CLI flags T11 uses, verified against `pyrefly check --help` of
# 0.37.0 (the pinned minimum, `setup/engine_packages.py`) through 1.3.1:
# `--python-interpreter-path` selects the interpreter to query, and
# `--skip-interpreter-query` suppresses every interpreter query, including a
# project config's `python-interpreter-path`/`python-interpreter-find-command`.
INTERPRETER_SELECTION_FLAGS = ("--python-interpreter-path", "--skip-interpreter-query")
# JSON diagnostics on stdout. (`--output=json` is `-o FILE`: it writes a file
# literally named `json` into the cwd and prints nothing parseable.)
OUTPUT_FORMAT_FLAG = "--output-format=json"


def _version_tuple(version: str) -> tuple[int, int, int] | None:
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", version.strip())
    if match is None:
        return None
    return (int(match[1]), int(match[2]), int(match[3]))


def minimum_version() -> str:
    """The pinned minimum from the engine package policy (`minimum:<ver>`)."""
    from ..setup.engine_packages import ENGINE_PACKAGES

    return ENGINE_PACKAGES["pyrefly"].version_policy.split(":", 1)[1]


class PyreflyEngine(Engine):
    name = "pyrefly"
    binary = "pyrefly"
    file_extensions = ("py", "pyi")

    # (path, st_ino, st_size, st_mtime_ns) -> both selection flags offered.
    _interpreter_flag_support: ClassVar[dict[tuple[str, int, int, int], bool]] = {}

    def support_problem(self) -> str | None:
        """Why this pyrefly must not run (engine-unsupported), or None.

        Runtime gate: an unknown or older-than-minimum version, or a binary
        whose own `check --help` lacks the selection flags, is unsupported --
        reported explicitly, never run with unverified flags or passed.
        """
        minimum = minimum_version()
        found = self.version()
        found_tuple = _version_tuple(found) if found else None
        minimum_tuple = _version_tuple(minimum)
        if found_tuple is None or minimum_tuple is None:
            return f"pyrefly version {found or 'unknown'} could not be verified against minimum {minimum}"
        if found_tuple < minimum_tuple:
            return f"pyrefly {found} is below the supported minimum {minimum}"
        if not self.supports_interpreter_selection():
            return f"pyrefly {found} lacks {' / '.join(INTERPRETER_SELECTION_FLAGS)}"
        return None

    def supports_interpreter_selection(self) -> bool:
        """R11.5: verify the selection flags against this exact binary's own
        `check --help`, cached by executable identity. Any probe failure is
        "unsupported", so pyrefly never runs with an unverified flag set."""
        binary_path = resolve_binary(self.binary)
        if binary_path is None:
            return False
        try:
            st = os.stat(binary_path)
        except OSError:
            return False
        key = (binary_path, st.st_ino, st.st_size, st.st_mtime_ns)
        cached = PyreflyEngine._interpreter_flag_support.get(key)
        if cached is not None:
            return cached
        try:
            proc = run_subprocess([binary_path, "check", "--help"], timeout=10)
        except (subprocess.TimeoutExpired, OSError):
            return False
        supported = proc.returncode == 0 and all(
            flag in proc.stdout for flag in INTERPRETER_SELECTION_FLAGS
        )
        PyreflyEngine._interpreter_flag_support[key] = supported
        return supported

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
        *,
        owner_instance_id: str | None = None,
        run_id: str | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["check", OUTPUT_FORMAT_FLAG]
        # S12.1: explicit file targets are the only targets -- re-appending
        # the directory would make pyrefly check every unrelated sibling.
        explicit_targets = any(
            not arg.startswith("-") and arg.endswith((".py", ".pyi")) for arg in args
        )
        argv = [binary_path, *default_args, *args]
        if not explicit_targets:
            argv.append(str(path))
        # S12.1: always a directory cwd, never a file.
        run_cwd = cwd or (path if path.is_dir() else path.parent)

        proc = run_subprocess(
            argv,
            cwd=run_cwd,
            timeout=120,
            **ownership_kwargs(owner_instance_id, run_id),
        )

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    findings_raw = parsed
                elif isinstance(parsed, dict) and "errors" in parsed:
                    findings_raw = parsed["errors"]
            except json.JSONDecodeError:
                parsed = None
        # S12.3: pyrefly prints paths relative to its (physical) cwd.
        base = os.path.realpath(run_cwd)
        for item in findings_raw:
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                item["path"] = os.path.normpath(os.path.join(base, item["path"]))

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"pyrefly exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings: list[Finding] = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("path", str(path)),
                    "line": item.get("line", 0),
                    "column": item.get("column", 0),
                    "rule": f"pyrefly/{item.get('name', 'type-error')}",
                    "severity": "error",
                    "message": item.get("description", "Python type mismatch"),
                    "fix": None,
                    "remediation": "Update type annotation or value to satisfy typechecker.",
                }
            )

        exit_code = raw.get("exit_code", 0)
        status: ToolStatus = (
            "fail" if findings else ("ok" if exit_code == 0 else "error")
        )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"pyrefly: {len(findings)} type diagnostic(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
