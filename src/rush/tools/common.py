"""Subprocess runner + engine discovery.

Architecture §4.4 — enforces requirement C10 (engine discovery, never hard-fail).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from .base import Finding, ToolResult, ToolStatus


def _venv_scripts_dir() -> Optional[Path]:
    """If we're running inside a uv-managed venv, return its Scripts/bin dir.

    shutil.which() with no explicit `path=` reads $PATH, which on Windows
    doesn't include the venv's Scripts/ when the venv is invoked by
    absolute path (vs activated via `source .venv/bin/activate`). Adding
    the venv's Scripts dir to the search list makes `engine_on_path()`
    find ruff/pytest/pip-audit installed via `uv pip install`.
    """
    # sys.prefix points at the venv root when running inside a venv.
    scripts = Path(sys.prefix) / ("Scripts" if os.name == "nt" else "bin")
    if scripts.is_dir():
        return scripts
    return None


def engine_on_path(binary: str) -> bool:
    """True if `binary` is findable on PATH or in the active venv's Scripts/.

    Cross-platform via shutil.which. Falls back to the venv's Scripts/bin
    directory so dev-installed engines (ruff, pip-audit) are discoverable
    even when the venv isn't activated.
    """
    if shutil.which(binary) is not None:
        return True
    scripts = _venv_scripts_dir()
    if scripts is not None:
        ext = ".exe" if os.name == "nt" else ""
        if (scripts / (binary + ext)).is_file():
            return True
    return False


def resolve_binary(binary: str) -> Optional[str]:
    """Return the absolute path to `binary` if findable, else None.

    Search priority:
      1. The active venv's Scripts/ directory (when running inside one)
      2. $PATH (via shutil.which)

    Preferring the venv prevents PATH pollution from a different tool's
    binary sneaking in (e.g. Hermes system pytest when rush-cli has its own).
    """
    scripts = _venv_scripts_dir()
    if scripts is not None:
        ext = ".exe" if os.name == "nt" else ""
        candidate = scripts / (binary + ext)
        if candidate.is_file():
            return str(candidate)

    return shutil.which(binary)


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


def run_engine(
    engine: "Engine",
    path: Path,
    args: list[str] | None = None,
    *,
    cwd: Path | None = None,
    tool_name: str | None = None,
    timeout: int = 120,
) -> ToolResult:
    """Architecture §4.4 — C10 enforcement point.

    Run `engine` on `path`. Returns a ToolResult; never raises.

    Status semantics:
        - 'skipped' — engine not on PATH (or no source files for this engine)
        - 'error'   — engine crashed, timed out, or returned unparseable output
        - 'ok'      — engine ran, no findings
        - 'warn'/'fail' — engine ran with findings (status set by engine.normalize())

    stdout is never written here. Engine subprocess captures its own stdout.
    """
    from ..engines.base import Engine

    tool_name = tool_name or engine.name
    extra_args = list(args or [])

    if not engine_on_path(engine.binary):
        return skipped_result(
            tool_name,
            engine.name,
            f"{engine.binary} not on PATH (install: {_install_hint(engine.name)})",
        )

    start = now_ms()
    try:
        result = engine.run(path, extra_args, cwd=cwd)
    except subprocess.TimeoutExpired:
        return error_result(
            tool_name, engine.name, f"timed out after {timeout}s",
            duration_ms=elapsed_ms(start),
        )
    except FileNotFoundError:
        # race: engine was on PATH at check, disappeared between then and run
        return skipped_result(
            tool_name, engine.name,
            f"{engine.binary} disappeared from PATH mid-run",
        )
    except Exception as e:
        return error_result(
            tool_name, engine.name, f"engine crashed: {e!r}",
            duration_ms=elapsed_ms(start),
        )

    # Stamp duration_ms onto the raw result so engine.normalize can read it.
    result.setdefault("duration_ms", elapsed_ms(start))

    # Default status mapping if engine didn't set one. Non-zero exit usually
    # means "found something" → warn/fail, not error. The engine's own
    # normalize() can override.
    return engine.normalize(result, path, tool_name)


def _install_hint(engine_name: str) -> str:
    """User-facing install hint per engine. Architecture §3.5 / C10."""
    return {
        "ruff": "pip install ruff",
        "pytest": "pip install pytest",
        "pip-audit": "pip install pip-audit",
        "eslint": "npm install -g eslint",
        "prettier": "npm install -g prettier",
        "vitest": "npm install -D vitest (in your project)",
        "npm-audit": "ships with npm",
    }.get(engine_name, "see engine docs")


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
        line = (
            f.get("line")
            or f.get("line_number")
            or (f.get("location") or {}).get("row", 0)
            or (f.get("position") or {}).get("line", 0)
            or 0
        )
        col = (
            f.get("column")
            or f.get("col")
            or (f.get("location") or {}).get("column", 0)
            or (f.get("position") or {}).get("column", 0)
            or 0
        )
        rule = str(
            f.get("rule")
            or f.get("code")
            or f.get("rule_id")
            or (f.get("location") or {}).get("rule", "")
            or ""
        )
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
