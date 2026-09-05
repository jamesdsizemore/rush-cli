"""Data models and custom exceptions for Phase 57 Invocation Context.

Standardizes invocation lifecycle, target specifications, cache policies,
and error boundaries across CLI and MCP transports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

TransportType = Literal["cli", "mcp"]
OperationKind = Literal["tool", "admin", "service"]
TargetState = Literal["present", "deleted", "renamed"]
CachePolicy = Literal["eligible", "bypass"]
ProviderOutcome = Literal["completed", "skipped", "error"]


@dataclass(frozen=True)
class PhysicalTarget:
    """Represents a bounded physical target for tool execution."""

    relative_path: Path
    state: TargetState
    capability: str = "read"
    provenance: str = "explicit"
    content_hash: str = ""


@dataclass(frozen=True)
class InvocationContext:
    """Canonical execution context shared across CLI and MCP transports."""

    workspace_root: Path
    transport: TransportType = field(compare=False)
    operation_id: str
    operation_kind: OperationKind
    targets: tuple[PhysicalTarget, ...]
    effective_config_digest: str
    permissions: tuple[str, ...]
    ordered_args: tuple[str, ...]
    declared_ignored_inputs: tuple[str, ...]
    cache_policy: CachePolicy
    artifact_build_identity: str
    tool_revision: str
    normalizer_revision: str
    environment_digest: str
    request_id: str = ""


@dataclass(frozen=True)
class CacheDecision:
    """Structured decision on result cache eligibility."""

    decision: CachePolicy
    reason: str
    cache_key: str | None = None
    key_payload: dict[str, Any] = field(default_factory=dict)


class InvocationError(Exception):
    """Base exception for invocation lifecycle and resolution failures."""


class TransportDivergenceError(InvocationError):
    """Raised when CLI and MCP transport definitions or outputs diverge."""


class ScopeWideningError(InvocationError):
    """Raised when target resolution widens execution scope beyond boundary."""


class UndeclaredInputError(InvocationError):
    """Raised when input artifacts or parameters are undeclared."""


class SignatureAdaptationError(InvocationError):
    """Raised when parameter or signature adaptation fails across transports."""

    def __init__(
        self,
        message: str,
        operation_id: str = "",
        param_name: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.operation_id = operation_id
        self.param_name = param_name
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "signature_adaptation_error",
            "operation_id": self.operation_id,
            "param_name": self.param_name,
            "message": self.message,
            "details": self.details,
        }


class ProviderEgressError(InvocationError):
    """Raised when external provider egress violates execution policy."""


__all__ = [
    "CacheDecision",
    "CachePolicy",
    "InvocationContext",
    "InvocationError",
    "OperationKind",
    "PhysicalTarget",
    "ProviderEgressError",
    "ProviderOutcome",
    "ScopeWideningError",
    "SignatureAdaptationError",
    "TargetState",
    "TransportDivergenceError",
    "TransportType",
    "UndeclaredInputError",
]
