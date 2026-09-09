"""Subprocess execution and engine dispatching primitives.

Architecture §4.4 — enforces requirement C10 (engine discovery, never hard-fail).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from ..permissions import build_execution_metadata, check_permissions
from ..safety.redactor import SecretRedactor
from ..tools.base import ToolResult
from .binaries import engine_on_path, resolve_binary
from .result_helpers import elapsed_ms, error_result, now_ms, skipped_result

if TYPE_CHECKING:
    from ..engines.base import Engine
    from ..permissions import ExecutionPermissions

MAX_SUBPROCESS_OUTPUT_CHARS = 256 * 1024


def _bounded_redacted_output(output: str) -> str:
    """Redact secrets and cap child output before adapters consume it."""
    redacted = SecretRedactor.redact_text(output)
    common = sys.modules.get("rush.tools.common")
    max_chars = (
        getattr(common, "MAX_SUBPROCESS_OUTPUT_CHARS", MAX_SUBPROCESS_OUTPUT_CHARS)
        if common is not None
        else MAX_SUBPROCESS_OUTPUT_CHARS
    )
    if len(redacted) <= max_chars:
        return redacted
    return redacted[:max_chars] + "[TRUNCATED]"


def run_subprocess(
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: float = 120,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a list-only local child process without inheriting stdin.

    The helper deliberately has no shell mode. Engines receive a bounded argv,
    fixed optional working directory, and DEVNULL stdin so they cannot consume
    the stdio MCP transport. Timeout exceptions remain observable by the shared
    `run_engine` error mapping.
    """
    if not argv or any(not isinstance(arg, str) for arg in argv):
        raise ValueError("argv must be a non-empty list of strings")
    common = sys.modules.get("rush.tools.common")
    resolver = (
        getattr(common, "resolve_binary", resolve_binary)
        if common is not None
        else resolve_binary
    )
    resolved_cmd = resolver(argv[0]) or argv[0]
    if os.name == "nt":
        which_cmd = shutil.which(resolved_cmd) or resolved_cmd
        if which_cmd.lower().endswith((".cmd", ".bat")):
            exec_argv = ["cmd.exe", "/c", which_cmd, *argv[1:]]
        else:
            exec_argv = [which_cmd, *argv[1:]]
    else:
        exec_argv = [resolved_cmd, *argv[1:]]
    try:
        result = subprocess.run(
            exec_argv,
            cwd=str(cwd) if cwd is not None else None,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=False,
            shell=False,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            argv,
            127,
            stdout="",
            stderr=f"{argv[0]}: command not found",
        )

    return subprocess.CompletedProcess(
        result.args,
        result.returncode,
        stdout=_bounded_redacted_output(result.stdout),
        stderr=_bounded_redacted_output(result.stderr),
    )


def _install_hint(engine_name: str) -> str:
    """Return a user-facing install hint without installing anything."""
    return {
        "ruff": "pip install ruff",
        "pytest": "pip install pytest",
        "pip-audit": "pip install pip-audit",
        "eslint": "npm install -g eslint",
        "prettier": "npm install -g prettier",
        "vitest": "npm install -D vitest (in your project)",
        "npm-audit": "ships with npm",
    }.get(engine_name, "see engine docs")


def run_engine(
    engine: Engine,
    path: Path,
    args: list[str] | None = None,
    *,
    cwd: Path | None = None,
    tool_name: str | None = None,
    timeout: int = 120,
    permissions: ExecutionPermissions | None = None,
    required_permissions: ExecutionPermissions | None = None,
) -> ToolResult:
    """Run an engine and always return a canonical result.

    Status semantics: missing engines or ungranted permissions are `skipped`;
    engine/process failures are `error`; valid engine findings are normalized
    as `warn` or `fail` by the adapter. No child output is written to Rush stdout.
    """
    common = sys.modules.get("rush.tools.common")
    _engine_on_path = (
        getattr(common, "engine_on_path", engine_on_path)
        if common is not None
        else engine_on_path
    )
    _skipped = (
        getattr(common, "skipped_result", skipped_result)
        if common is not None
        else skipped_result
    )
    _error = (
        getattr(common, "error_result", error_result)
        if common is not None
        else error_result
    )
    _now = getattr(common, "now_ms", now_ms) if common is not None else now_ms
    _elapsed = (
        getattr(common, "elapsed_ms", elapsed_ms) if common is not None else elapsed_ms
    )

    tool_name = tool_name or engine.name
    extra_args = list(args or [])

    # Check execution permissions before PATH probe or process spawning
    ok, missing = check_permissions(required_permissions, permissions)
    if not ok:
        missing_str = ", ".join(missing)
        return _skipped(
            tool_name,
            engine.name,
            f"requires permission: {missing_str}",
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_permissions,
                    granted=permissions,
                    producer=engine.name,
                )
            },
        )

    if not _engine_on_path(engine.binary):
        return _skipped(
            tool_name,
            engine.name,
            f"{engine.binary} not on PATH (install: {_install_hint(engine.name)})",
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_permissions,
                    granted=permissions,
                    producer=engine.name,
                )
            },
        )

    start = _now()
    try:
        result = engine.run(path, extra_args, cwd=cwd)
    except subprocess.TimeoutExpired:
        return _error(
            tool_name,
            engine.name,
            f"timed out after {timeout}s",
            duration_ms=_elapsed(start),
            terminal_reason="timeout",
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_permissions,
                    granted=permissions,
                    producer=engine.name,
                )
            },
        )
    except FileNotFoundError:
        return _skipped(
            tool_name,
            engine.name,
            f"{engine.binary} disappeared from PATH mid-run",
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_permissions,
                    granted=permissions,
                    producer=engine.name,
                )
            },
        )
    except Exception as error:  # noqa: BLE001 - C10 requires structured engine errors
        return _error(
            tool_name,
            engine.name,
            f"engine crashed: {error!r}",
            duration_ms=_elapsed(start),
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_permissions,
                    granted=permissions,
                    producer=engine.name,
                )
            },
        )

    result.setdefault("duration_ms", _elapsed(start))
    tool_res = engine.normalize(result, path, tool_name)
    metadata = tool_res.get("metadata")
    if metadata is None:
        metadata = {}
        tool_res["metadata"] = metadata
    if "execution" not in metadata:
        metadata["execution"] = build_execution_metadata(
            "executed",
            requested=required_permissions,
            granted=permissions,
            producer=engine.name,
            producer_version=tool_res.get("engine_version"),
        )
    return tool_res


__all__ = [
    "MAX_SUBPROCESS_OUTPUT_CHARS",
    "_bounded_redacted_output",
    "_install_hint",
    "run_engine",
    "run_subprocess",
]
