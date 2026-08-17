"""Core types for the 5 tool functions.

Architecture §3.

Single source of truth for the canonical output shape (ToolResult) and the
abstract base that all tool subclasses inherit from.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal, Optional, TypedDict

# --- String literal unions --------------------------------------------------

ToolStatus = Literal["ok", "warn", "fail", "error", "skipped"]
ToolName = Literal["review", "lint", "format", "test", "security"]
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
    severity: Severity
    message: str
    fix: Optional[dict]


class ToolResult(TypedDict, total=False):
    """The canonical output every tool returns, regardless of CLI or MCP.

    Always-present minimum: tool, status, duration_ms, summary, findings.
    Other fields are tool-specific or engine-specific.
    """

    tool: ToolName
    engine: Optional[str]
    engine_version: Optional[str]
    status: ToolStatus
    duration_ms: int
    summary: str
    findings: list[Finding]
    raw: Optional[Any]
    # review-only:
    review_kind: LlmStatus
    review_provider: Optional[str]


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
