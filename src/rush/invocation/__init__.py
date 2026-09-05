"""Invocation context subsystem for Rush CLI and MCP parity.

Phase 57: Workstream P57.1.
"""

from __future__ import annotations

from .cache_policy import decide_cache
from .executor import (
    InvocationExecutor,
    RegisteredOperation,
    adapt_signature_at_registration,
    format_signature_error_diagnostic,
)
from .models import (
    CacheDecision,
    CachePolicy,
    InvocationContext,
    InvocationError,
    OperationKind,
    PhysicalTarget,
    ProviderEgressError,
    ProviderOutcome,
    ScopeWideningError,
    SignatureAdaptationError,
    TargetState,
    TransportDivergenceError,
    TransportType,
    UndeclaredInputError,
)
from .resolver import resolve_invocation
from .targets import build_physical_targets, resolve_target

__all__ = [
    "CacheDecision",
    "CachePolicy",
    "InvocationContext",
    "InvocationError",
    "InvocationExecutor",
    "OperationKind",
    "PhysicalTarget",
    "ProviderEgressError",
    "ProviderOutcome",
    "RegisteredOperation",
    "ScopeWideningError",
    "SignatureAdaptationError",
    "TargetState",
    "TransportDivergenceError",
    "TransportType",
    "UndeclaredInputError",
    "adapt_signature_at_registration",
    "build_physical_targets",
    "decide_cache",
    "format_signature_error_diagnostic",
    "resolve_invocation",
    "resolve_target",
]
