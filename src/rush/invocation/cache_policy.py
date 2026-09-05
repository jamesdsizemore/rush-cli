"""Deterministic cryptographic cache key policy and execution gating.

Phase 57: Workstream P57.5.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from rush.invocation.models import CacheDecision, InvocationContext


def decide_cache(context: InvocationContext, pure: bool = True) -> CacheDecision:
    """Evaluate cache eligibility and derive deterministic cryptographic cache key.

    Enforces:
    1. Operation purity: Only operations declared pure in manifest are eligible.
    2. Explicit cache bypass: Respects cache_policy="bypass" (--no-cache).
    3. Complete identity binding: All required context fields and target content hashes
       must be present with zero fallback salt.
    4. Deterministic SHA-256 key derivation over canonical identity payload.
    """
    if not pure:
        return CacheDecision(
            decision="bypass",
            reason="operation_not_pure",
            cache_key=None,
            key_payload={},
        )

    if context.cache_policy == "bypass":
        return CacheDecision(
            decision="bypass",
            reason="explicit_bypass",
            cache_key=None,
            key_payload={},
        )

    # Validate required context identity fields
    required_fields = (
        "operation_id",
        "tool_revision",
        "normalizer_revision",
        "artifact_build_identity",
        "effective_config_digest",
        "environment_digest",
    )
    for field_name in required_fields:
        val = getattr(context, field_name, None)
        if not val or not str(val).strip():
            return CacheDecision(
                decision="bypass",
                reason=f"missing_identity_{field_name}",
                cache_key=None,
                key_payload={},
            )

    # Validate targets: every target with state == "present" must have non-empty content_hash
    for target in context.targets:
        if target.state == "present" and (
            not target.content_hash or not target.content_hash.strip()
        ):
            return CacheDecision(
                decision="bypass",
                reason="missing_identity_target_content_hash",
                cache_key=None,
                key_payload={},
            )

    # Build canonical JSON dictionary of all identities
    serialized_targets = [
        {
            "relative_path": str(t.relative_path).replace("\\", "/"),
            "state": t.state,
            "capability": t.capability,
            "provenance": t.provenance,
            "content_hash": t.content_hash,
        }
        for t in sorted(
            context.targets, key=lambda x: str(x.relative_path).replace("\\", "/")
        )
    ]

    key_payload: dict[str, Any] = {
        "operation_id": context.operation_id,
        "ordered_args": list(context.ordered_args),
        "effective_config_digest": context.effective_config_digest,
        "permissions": sorted(context.permissions),
        "artifact_build_identity": context.artifact_build_identity,
        "tool_revision": context.tool_revision,
        "normalizer_revision": context.normalizer_revision,
        "environment_digest": context.environment_digest,
        "targets": serialized_targets,
    }

    serialized = json.dumps(key_payload, sort_keys=True, separators=(",", ":"))
    cache_key = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    return CacheDecision(
        decision="eligible",
        reason="eligible",
        cache_key=cache_key,
        key_payload=key_payload,
    )


__all__ = ["decide_cache"]
