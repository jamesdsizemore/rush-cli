"""Contracts and schemas for Rush tools and operations."""

from __future__ import annotations

from rush.contracts.operations import (
    AdminOperationAdapter,
    BaseOperationAdapter,
    OperationKind,
    OperationRegistry,
    ServiceOperationAdapter,
    ToolOperationAdapter,
)
from rush.contracts.results import (
    LEGACY_SEVERITY_MAP,
    FindingSeverity,
    FindingV1,
    ToolResultV1,
    ToolStatus,
    ValidationErrorV1,
    adapt_legacy_finding,
    adapt_legacy_tool_result,
    serialize_tool_result,
    validate_finding,
    validate_tool_result,
)

__all__ = [
    "LEGACY_SEVERITY_MAP",
    "AdminOperationAdapter",
    "BaseOperationAdapter",
    "FindingSeverity",
    "FindingV1",
    "OperationKind",
    "OperationRegistry",
    "ServiceOperationAdapter",
    "ToolOperationAdapter",
    "ToolResultV1",
    "ToolStatus",
    "ValidationErrorV1",
    "adapt_legacy_finding",
    "adapt_legacy_tool_result",
    "serialize_tool_result",
    "validate_finding",
    "validate_tool_result",
]
