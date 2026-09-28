"""Review result assembly and canonical contract normalization.

Constructs canonical ToolResult with coordinate-sorted, sanitized, and
fingerprinted findings.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rush.runtime.result_helpers import elapsed_ms, finding_fingerprint

if TYPE_CHECKING:
    from rush.tools.base import Finding, LlmStatus, ToolResult, ToolStatus


def _consumed(target: Path) -> bool:
    """The heuristics read a file only below the size cap (`collection`)."""
    from rush.review.collection import MAX_FILE_BYTES

    try:
        return target.stat().st_size <= MAX_FILE_BYTES
    except OSError:
        return False


def review_scope_v1(
    scope: dict[str, Any],
    *,
    root: Path,
    targets: Sequence[Path],
    requested_file_count: int,
) -> dict[str, Any]:
    """T16 (finding 8): the §3.2 v1 scope, keeping review's own `mode` and
    `files`. Requested = what the caller asked for (explicit files) or what
    matched under the target; consumed = files the heuristics read."""
    consumed = sum(1 for target in targets if _consumed(target))
    if consumed == 0:
        coverage, reason = "none", "no_reviewable_python_files"
    elif consumed < requested_file_count:
        coverage, reason = "partial", "requested_files_not_reviewed"
    else:
        coverage, reason = "complete", None
    return {
        "version": 1,
        "kind": "file",
        **scope,
        "logical_root": str(root),
        "requested_file_count": requested_file_count,
        "matched_file_count": len(targets),
        "consumed_file_count": consumed,
        "coverage": coverage,
        "reason": reason,
    }


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
    from rush.tools.base import ToolResult

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
    from rush.tools.base import ToolResult

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
    from rush.tools.base import ToolResult

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
    "review_scope_v1",
]
