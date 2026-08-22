"""Subprocess runner + engine discovery.

Architecture §4.4 — enforces requirement C10 (engine discovery, never hard-fail).
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .base import Finding, ToolResult

if TYPE_CHECKING:
    from ..engines.base import Engine
    from ..permissions import ExecutionPermissions


MAX_SUBPROCESS_OUTPUT_CHARS = 256 * 1024


def _bounded_redacted_output(output: str) -> str:
    """Redact secret assignments and cap child output before adapters consume it."""
    redacted = _SECRET_ASSIGNMENT.sub(r"\1\2[REDACTED]", output)
    if len(redacted) <= MAX_SUBPROCESS_OUTPUT_CHARS:
        return redacted
    return redacted[:MAX_SUBPROCESS_OUTPUT_CHARS] + "[TRUNCATED]"


def _venv_scripts_dir() -> Path | None:
    """If we're running inside a uv-managed venv, return its Scripts/bin dir.

    shutil.which() with no explicit `path=` reads $PATH, which on Windows
    doesn't include the venv's Scripts/ when the venv is invoked by
    absolute path (vs activated via `source .venv/bin/activate`). Adding
    the venv's Scripts dir to the search list makes `engine_on_path()`
    find ruff/pytest/pip-audit installed via `uv pip install`.
    """
    scripts = Path(sys.prefix) / ("Scripts" if os.name == "nt" else "bin")
    if scripts.is_dir():
        return scripts
    return None


from functools import lru_cache


@lru_cache(maxsize=256)
def _resolve_binary_cached(binary: str) -> str | None:
    scripts = _venv_scripts_dir()
    if scripts is not None:
        ext = ".exe" if os.name == "nt" else ""
        candidate = scripts / (binary + ext)
        if candidate.is_file():
            return str(candidate)
    return shutil.which(binary)


def clear_binary_cache() -> None:
    """Clear the in-memory binary resolution cache."""
    _resolve_binary_cached.cache_clear()


def resolve_binary(binary: str) -> str | None:
    """Return an executable from the active venv Scripts/bin, then PATH.

    This resolver is the only engine-discovery policy. Configuration cannot
    supply an executable path, which prevents a project file from selecting an
    arbitrary local binary. Results are cached in-memory for fast repeated lookups.
    """
    return _resolve_binary_cached(binary)


def engine_on_path(binary: str) -> bool:
    """True if `binary` is findable on PATH or in the active venv's Scripts/."""
    return resolve_binary(binary) is not None


def run_subprocess(
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 120,
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
    resolved_cmd = resolve_binary(argv[0]) or argv[0]
    if os.name == "nt":
        which_cmd = shutil.which(resolved_cmd) or resolved_cmd
        if which_cmd.lower().endswith((".cmd", ".bat")):
            exec_argv = ["cmd.exe", "/c", which_cmd, *argv[1:]]
        else:
            exec_argv = [which_cmd, *argv[1:]]
    else:
        exec_argv = [resolved_cmd, *argv[1:]]
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

    return subprocess.CompletedProcess(
        result.args,
        result.returncode,
        stdout=_bounded_redacted_output(result.stdout),
        stderr=_bounded_redacted_output(result.stderr),
    )


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
    from ..permissions import build_execution_metadata, check_permissions

    tool_name = tool_name or engine.name
    extra_args = list(args or [])

    # Check execution permissions before PATH probe or process spawning
    ok, missing = check_permissions(required_permissions, permissions)
    if not ok:
        missing_str = ", ".join(missing)
        return skipped_result(
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

    if not engine_on_path(engine.binary):
        return skipped_result(
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

    start = now_ms()
    try:
        result = engine.run(path, extra_args, cwd=cwd)
    except subprocess.TimeoutExpired:
        return error_result(
            tool_name,
            engine.name,
            f"timed out after {timeout}s",
            duration_ms=elapsed_ms(start),
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
        return skipped_result(
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
        return error_result(
            tool_name,
            engine.name,
            f"engine crashed: {error!r}",
            duration_ms=elapsed_ms(start),
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_permissions,
                    granted=permissions,
                    producer=engine.name,
                )
            },
        )

    result.setdefault("duration_ms", elapsed_ms(start))
    tool_res = engine.normalize(result, path, tool_name)
    if "metadata" not in tool_res or tool_res["metadata"] is None:
        tool_res["metadata"] = {}
    if "execution" not in tool_res["metadata"]:
        tool_res["metadata"]["execution"] = build_execution_metadata(
            "executed",
            requested=required_permissions,
            granted=permissions,
            producer=engine.name,
            producer_version=tool_res.get("engine_version"),
        )
    return tool_res


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


def skipped_result(
    tool_name: str,
    engine: str | None,
    reason: str,
    *,
    duration_ms: int = 0,
    metadata: dict | None = None,
) -> ToolResult:
    """Build a ToolResult for an unavailable local engine or missing permission."""
    result = ToolResult(
        tool=tool_name,
        engine=engine,
        engine_version=None,
        status="skipped",
        duration_ms=duration_ms,
        summary=f"skipped: {reason}",
        findings=[],
        raw=None,
    )
    if metadata is not None:
        result["metadata"] = metadata
    return result


def error_result(
    tool_name: str,
    engine: str | None,
    message: str,
    *,
    duration_ms: int = 0,
    terminal_reason: str | None = None,
    partial: bool = False,
    metadata: dict | None = None,
) -> ToolResult:
    """Build an engine error result with optional execution metadata."""
    result = ToolResult(
        tool=tool_name,
        engine=engine,
        engine_version=None,
        status="error",
        duration_ms=duration_ms,
        summary=f"error: {message}",
        findings=[],
        raw=None,
    )
    meta = dict(metadata or {})
    if terminal_reason is not None:
        meta["terminal_reason"] = terminal_reason
        meta["partial"] = partial
    if meta:
        result["metadata"] = meta
    return result


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|authorization)\s*([=:])\s*([^\s,;]+)"
)


def _redact_finding_message(message: str) -> str:
    """Keep a finding useful without returning an assigned secret-like value."""
    return _SECRET_ASSIGNMENT.sub(r"\1\2[REDACTED]", message)


def finding_fingerprint(
    path: str,
    line: int | str,
    column: int | str,
    rule_id: str,
    severity: str,
    message: str,
) -> str:
    """Return a deterministic, redaction-safe identity for one finding."""
    payload = "\x1f".join((path, str(line), str(column), rule_id, severity, message))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_findings(
    raw_findings: list[dict],
    *,
    default_severity: str = "warn",
    path_prefix: str = "",
) -> list[Finding]:
    """Normalize, redact, identify, and deterministically order engine findings.

    Invalid records without a message are omitted. At most 10,000 records are
    processed to bound memory use from a malformed external engine payload.
    """
    findings: list[Finding] = []
    for raw_finding in raw_findings[:10000]:
        path = str(raw_finding.get("path") or raw_finding.get("filename") or "")
        if path_prefix and not path.startswith("/"):
            path = f"{path_prefix.rstrip('/')}/{path}"
        message = str(
            raw_finding.get("message")
            or raw_finding.get("desc")
            or raw_finding.get("text")
            or ""
        )
        if not message:
            continue
        message = _redact_finding_message(message)
        severity = raw_finding.get("severity") or default_severity
        if severity not in ("info", "warn", "error"):
            severity = default_severity
        line = (
            raw_finding.get("line")
            or raw_finding.get("line_number")
            or (raw_finding.get("location") or {}).get("row", 0)
            or (raw_finding.get("position") or {}).get("line", 0)
            or 0
        )
        column = (
            raw_finding.get("column")
            or raw_finding.get("col")
            or (raw_finding.get("location") or {}).get("column", 0)
            or (raw_finding.get("position") or {}).get("column", 0)
            or 0
        )
        rule_id = str(
            raw_finding.get("rule_id")
            or raw_finding.get("rule")
            or raw_finding.get("code")
            or (raw_finding.get("location") or {}).get("rule", "")
            or ""
        )
        normalized = Finding(
            path=path,
            line=int(line) if isinstance(line, (int, float)) else 0,
            column=int(column) if isinstance(column, (int, float)) else 0,
            rule=rule_id,
            rule_id=rule_id,
            severity=severity,
            message=message,
            fix=raw_finding.get("fix"),
            remediation=raw_finding.get("remediation") or raw_finding.get("fix"),
            evidence=raw_finding.get("evidence"),
            provenance=raw_finding.get("provenance"),
            freshness=raw_finding.get("freshness"),
        )
        normalized["fingerprint"] = finding_fingerprint(
            normalized["path"],
            normalized["line"],
            normalized["column"],
            normalized["rule_id"],
            normalized["severity"],
            normalized["message"],
        )
        findings.append(normalized)
    return sorted(
        findings,
        key=lambda finding: (
            finding["path"],
            finding["line"],
            finding["column"],
            finding["rule_id"],
            finding["severity"],
            finding["message"],
        ),
    )


def exit_code_for(result: ToolResult) -> int:
    """Map canonical statuses to CLI process exit codes."""
    status = result.get("status")
    if status in ("ok", "skipped"):
        return 0
    if status in ("warn", "fail"):
        return 1
    if status == "error":
        return 2
    return 0


def now_ms() -> int:
    """Return milliseconds since epoch for duration measurement."""
    return int(time.time() * 1000)


def elapsed_ms(start_ms: int) -> int:
    """Return non-negative elapsed milliseconds since a start timestamp."""
    if start_ms <= 0:
        return 0
    return max(now_ms() - start_ms, 0)
