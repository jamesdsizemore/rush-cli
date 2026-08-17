"""Subprocess runner + engine discovery.

Architecture §4.4 — enforces requirement C10 (engine discovery, never hard-fail).
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from .base import Finding, ToolResult, ToolStatus


def engine_on_path(binary: str) -> bool:
    """True if `binary` is findable on PATH (cross-platform via shutil.which)."""
    return shutil.which(binary) is not None


def run_subprocess(
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 120,
    env: dict | None = None,
) -> subprocess.CompletedProcess:
    """Run a subprocess and return the CompletedProcess.

    Captures stdout+stderr as text. Raises subprocess.TimeoutExpired
    on timeout; callers should wrap.
    """
    return subprocess.run(
        argv,
        cwd=str(cwd) if cwd is not None else None,
        timeout=timeout,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def skipped_result(tool_name: str, engine: Optional[str], reason: str) -> ToolResult:
    """Build a ToolResult for a skipped tool (engine not on PATH, etc.)."""
    return ToolResult(
        tool=tool_name,
        engine=engine,
        engine_version=None,
        status="skipped",
        duration_ms=0,
        summary=f"skipped: {reason}",
        findings=[],
        raw=None,
    )


def error_result(
    tool_name: str,
    engine: Optional[str],
    message: str,
    *,
    duration_ms: int = 0,
) -> ToolResult:
    """Build a ToolResult for an engine error (distinct from 'fail')."""
    return ToolResult(
        tool=tool_name,
        engine=engine,
        engine_version=None,
        status="error",
        duration_ms=duration_ms,
        summary=f"error: {message}",
        findings=[],
        raw=None,
    )


def normalize_findings(
    raw_findings: list[dict],
    *,
    default_severity: str = "warn",
    path_prefix: str = "",
) -> list[Finding]:
    """Convert engine-native finding dicts to canonical Finding TypedDict shape.

    Filters out items missing required fields (path/message). Caps list
    length at 10,000 to bound memory on misbehaving engines.
    """
    out: list[Finding] = []
    for f in raw_findings[:10000]:
        path = str(f.get("path") or f.get("filename") or "")
        if path_prefix and not path.startswith("/"):
            path = f"{path_prefix.rstrip('/')}/{path}"
        message = str(f.get("message") or f.get("desc") or f.get("text") or "")
        if not message:
            continue
        sev = f.get("severity") or default_severity
        if sev not in ("info", "warn", "error"):
            sev = default_severity
        line = f.get("line") or f.get("line_number") or 0
        col = f.get("column") or f.get("col") or 0
        rule = str(f.get("rule") or f.get("code") or f.get("rule_id") or "")
        out.append(
            Finding(
                path=path,
                line=int(line) if isinstance(line, (int, float)) else 0,
                column=int(col) if isinstance(col, (int, float)) else 0,
                rule=rule,
                severity=sev,
                message=message,
                fix=f.get("fix"),
            )
        )
    return out


def exit_code_for(result: ToolResult) -> int:
    """Map a ToolResult status to a CLI exit code.

    0 = ok / skipped (not a failure)
    1 = warn / fail (findings present)
    2 = error (engine crashed)
    """
    status = result.get("status")
    if status in ("ok", "skipped"):
        return 0
    if status in ("warn", "fail"):
        return 1
    if status == "error":
        return 2
    return 0


def now_ms() -> int:
    """Milliseconds since epoch as int. Use as the start timestamp;
    subtract from a later now_ms() call to get elapsed duration_ms."""
    return int(time.time() * 1000)


def elapsed_ms(start_ms: int) -> int:
    """Elapsed milliseconds since start_ms. Returns 0 if start_ms <= 0
    or if the result would be negative (clock skew)."""
    if start_ms <= 0:
        return 0
    delta = now_ms() - start_ms
    return max(delta, 0)
