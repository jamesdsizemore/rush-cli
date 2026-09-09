"""Review result assembly and canonical contract normalization.

Constructs canonical ToolResult with coordinate-sorted, sanitized, and
fingerprinted findings.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from rush.tools.base import Finding, LlmStatus, ToolResult, ToolStatus
from rush.tools.common import elapsed_ms, finding_fingerprint


def _sanitize_finding(finding: Finding) -> None:
    """Enrich finding in-place with evidence, fingerprint, and freshness."""
    if "evidence" not in finding and finding.get("path"):
        finding["evidence"] = {
            "kind": "source-location",
            "path": finding["path"],
            "line": finding.get("line", 0),
        }
    finding["fingerprint"] = finding_fingerprint(
        str(finding.get("path", "")),
        finding.get("line", 0) or 0,
        finding.get("column", 0) or 0,
        str(finding.get("rule_id") or finding.get("rule") or ""),
        str(finding.get("severity", "")),
        str(finding.get("message", "")),
    )
    finding["freshness"] = "unknown"


def _finding_sort_key(finding: Finding) -> tuple[int, str, int, int, str]:
    """Sort key placing real file findings in coordinate order and synthetic findings at end."""
    path = str(finding.get("path", ""))
    is_synthetic = 1 if not path else 0
    line = int(finding.get("line", 0) or 0)
    column = int(finding.get("column", 0) or 0)
    rule = str(finding.get("rule_id") or finding.get("rule") or "")
    return (is_synthetic, path, line, column, rule)


def _determine_status(findings: Sequence[Finding]) -> ToolStatus:
    """Determine tool status based on finding severity (error -> fail, warn -> warn, else ok)."""
    if any(f.get("severity") == "error" for f in findings):
        return "fail"
    if any(f.get("severity") == "warn" for f in findings):
        return "warn"
    return "ok"


def _determine_summary(findings: Sequence[Finding], review_kind: str) -> str:
    """Format human-readable review summary message."""
    suffix = " (+LLM)" if review_kind == "llm" else ""
    if findings:
        return f"review: {len(findings)} heuristic finding(s){suffix}"
    return f"review: clean{suffix}"


def assemble_review_result(
    findings: Sequence[Finding],
    *,
    start_ms: int,
    scope: dict[str, Any],
    graft_state: str = "not-requested",
    review_kind: LlmStatus = "heuristic",
    review_provider: str | None = None,
) -> ToolResult:
    """Assemble and validate canonical ToolResult for the review pipeline."""
    normalized: list[Finding] = [
        f if isinstance(f, dict) else f.to_dict() for f in findings
    ]
    for finding in normalized:
        _sanitize_finding(finding)

    normalized.sort(key=_finding_sort_key)

    status = _determine_status(normalized)
    summary = _determine_summary(normalized, review_kind)
    engine_name = "heuristic-v1" + (
        f"+llm/{review_provider}" if review_provider else ""
    )
    heuristic_count = len(normalized) - sum(
        1 for f in normalized if f.get("rule") == "llm-summary"
    )

    return ToolResult(
        tool="review",
        engine=engine_name,
        engine_version=None,
        status=status,
        duration_ms=elapsed_ms(start_ms),
        summary=summary,
        findings=normalized,
        raw={"heuristic_count": heuristic_count},
        metadata={"graft": graft_state, "scope": scope},
        review_kind=review_kind,
        review_provider=review_provider,
    )


def build_error_review_result(error_msg: str, start_ms: int) -> ToolResult:
    """Build canonical ToolResult for a review configuration or collection error."""
    return ToolResult(
        tool="review",
        engine="heuristic-v1",
        engine_version=None,
        status="error",
        duration_ms=elapsed_ms(start_ms),
        summary=f"review: {error_msg}",
        findings=[],
        raw=None,
        metadata={"graft": "not-requested"},
        review_kind="heuristic",
        review_provider=None,
    )


def build_empty_review_result(
    path: Path, scope: dict[str, Any], start_ms: int
) -> ToolResult:
    """Build canonical ToolResult when no reviewable Python files are discovered."""
    return ToolResult(
        tool="review",
        engine="heuristic-v1",
        engine_version=None,
        status="ok",
        duration_ms=elapsed_ms(start_ms),
        summary=f"review: no Python files found under {path}",
        findings=[],
        raw=None,
        metadata={"graft": "not-requested", "scope": scope},
        review_kind="heuristic",
        review_provider=None,
    )


__all__ = [
    "_determine_status",
    "_determine_summary",
    "_finding_sort_key",
    "_sanitize_finding",
    "assemble_review_result",
    "build_empty_review_result",
    "build_error_review_result",
]
