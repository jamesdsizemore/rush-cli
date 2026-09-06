"""Result building and common types for session continuity."""

from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal

from ..contracts.results import ToolResultV1, adapt_legacy_tool_result
from ..permissions import (
    ExecutionPermissions,
    build_execution_metadata,
)

if TYPE_CHECKING:
    from ..tools.base import Finding, ToolResult

_WRITE_PERMISSION = ExecutionPermissions(cache_write=True)


class ContinuityResult(dict):
    """ToolResult dictionary conforming to ToolResultV1 contract via to_tool_result_v1."""

    def to_tool_result_v1(self) -> ToolResultV1:
        return adapt_legacy_tool_result(self)


def valid_name(name: str | None) -> bool:
    """Validate that name is a single non-empty filename without directory traversal."""
    return bool(name) and Path(name).name == name and name not in {".", ".."}


def build_continuity_result(
    started: float,
    status: Literal["ok", "error", "skipped", "warn", "fail"],
    summary: str,
    *,
    operation: str,
    granted: ExecutionPermissions,
    requested: ExecutionPermissions | None = None,
    raw: Any = None,
    artifacts: list[str] | None = None,
    handoff: dict[str, Any] | None = None,
    context_envelope: dict[str, Any] | None = None,
    coordination: dict[str, Any] | None = None,
    provider_route: dict[str, Any] | None = None,
    findings: list[Finding] | None = None,
    as_v1: bool = False,
    tool_name: str = "continuity",
) -> ToolResult | ToolResultV1:
    """Build canonical ToolResult or ToolResultV1 for session continuity."""
    metadata = {
        "operation": operation,
        "execution": build_execution_metadata(
            mode="executed",
            requested=requested,
            granted=granted,
            producer="checkpoint-journal",
        ),
        **({"handoff": handoff} if handoff is not None else {}),
        **(
            {"context_envelope": context_envelope}
            if context_envelope is not None
            else {}
        ),
        **({"coordination": coordination} if coordination is not None else {}),
        **({"provider_route": provider_route} if provider_route is not None else {}),
    }
    extensions: dict[str, Any] = {
        "metadata": metadata,
    }
    if artifacts is not None:
        extensions["artifacts"] = artifacts

    res_dict = {
        "schema_version": "1.0.0",
        "tool": tool_name,
        "engine": "checkpoint-journal",
        "engine_version": None,
        "status": status,
        "duration_ms": int((monotonic() - started) * 1000),
        "summary": summary,
        "findings": list(findings or []),
        "raw": raw,
        "artifacts": artifacts,
        "metadata": metadata,
        "extensions": extensions,
    }
    res = ContinuityResult(res_dict)
    if as_v1:
        return res.to_tool_result_v1()
    return res
