"""Core types for the 5 tool functions.

Architecture §3.

Single source of truth for the canonical output shape (ToolResult) and the
abstract base that all tool subclasses inherit from.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal, TypedDict

# --- String literal unions --------------------------------------------------

ToolStatus = Literal["ok", "warn", "fail", "error", "skipped"]
ToolName = str
Severity = Literal["info", "warn", "error"]
LlmStatus = Literal["heuristic", "llm"]  # never "reviewed" — requirement C7


# --- TypedDicts -------------------------------------------------------------


class Finding(TypedDict, total=False):
    """One issue from any engine. total=False because not all engines
    populate every field (e.g. heuristics may lack `rule`)."""

    path: str
    line: int
    column: int
    rule: str
    rule_id: str
    severity: Severity
    message: str
    fix: dict | None
    remediation: dict | str | None
    evidence: dict | str | None
    provenance: str | None
    fingerprint: str
    freshness: str | None


class ToolResult(TypedDict, total=False):
    """The canonical output every tool returns, regardless of CLI or MCP.

    Always-present minimum: tool, status, duration_ms, summary, findings.
    Other fields are tool-specific or engine-specific.
    """

    tool: ToolName
    engine: str | None
    engine_version: str | None
    status: ToolStatus
    duration_ms: int
    summary: str
    findings: list[Finding]
    raw: Any | None
    # review-only:
    review_kind: LlmStatus | None
    review_provider: str | None
    # v0.2 optional extensions. Existing consumers can ignore these fields.
    metrics: dict[str, int | float | str] | None
    artifacts: list[str] | None
    metadata: dict[str, Any] | None


# --- Base class -------------------------------------------------------------


class ToolFn(ABC):
    """Base for the 5 tool modules. Each subclass is a single source-of-truth
    function callable from both CLI and MCP (requirement C3)."""

    name: ToolName

    @property
    @abstractmethod
    def mcp_description(self) -> str:
        """Short (<200 chars) description for the MCP tool registry.

        Architecture §5.2 template:
            <verb> <path>. Returns {status, findings[], summary}.
            Engines: <engines>. status='skipped' means engine not on PATH.
            <one sentence on what it does>.
        """
        ...

    @abstractmethod
    def __call__(self, path: Path, config: Any) -> ToolResult:
        """Run the tool on `path` (file or directory) under `config`.

        Implementations must NEVER raise — return a ToolResult with
        status='error' if anything goes wrong.
        """
        ...
