"""Runtime tool result and finding normalization helpers.

Architecture §4.4 — structured error and skipped status mapping.
"""

from __future__ import annotations

import hashlib
import time

from ..safety.redactor import SecretRedactor
from ..tools.base import Finding, Severity, ToolResult


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


def _redact_finding_message(message: str) -> str:
    """Keep a finding useful without returning an assigned secret-like value."""
    return SecretRedactor.redact_text(message)


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
    default_severity: Severity = "warn",
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
        severity: Severity = raw_finding.get("severity") or default_severity
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


def exit_code_for(result: object) -> int:
    """Map canonical statuses to CLI process exit codes."""
    status: object
    if isinstance(result, str):
        status = result
    elif hasattr(result, "status"):
        status = result.status
    elif isinstance(result, dict):
        status = result.get("status")
    else:
        status = None

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


__all__ = [
    "_redact_finding_message",
    "elapsed_ms",
    "error_result",
    "exit_code_for",
    "finding_fingerprint",
    "normalize_findings",
    "now_ms",
    "skipped_result",
]
