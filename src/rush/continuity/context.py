"""Context packing and retrieval operations for session continuity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import tiktoken

from ..codegraph.context_packer import ContextPacker
from ..permissions import (
    ExecutionPermissions,
    check_permissions,
)
from ..safety.redactor import SecretRedactor
from ..token_economy.ccr_store import CCRStore
from ..token_economy.memory_cache_gate import check_memory_before_pack, write_cache_fill
from ..token_economy.telemetry import TelemetryStore
from .results import _WRITE_PERMISSION, ContinuityOutput, build_continuity_result

# MC04 §9.0: `ContextPacker` always tokenizes with this encoding today (its own default,
# never overridden by `pack_context()`) — recorded/compared as the cache identity's
# "tokenizer" dimension so a future caller that does vary it can't collide with this one.
_DEFAULT_ENCODING = "cl100k_base"


def _build_recovery_envelope(
    selected_evidence: list[dict[str, Any]],
    estimated: int,
    token_budget: int,
    handle: str | None,
    redactions: int,
    cache_write_denied: bool = False,
) -> dict[str, Any]:
    if cache_write_denied:
        return {
            "selected_evidence": selected_evidence,
            "tokens": {
                "estimated": estimated,
                "actual": None,
                "budget": token_budget,
            },
            "omissions": [{"reason": "insufficient_budget", "mandatory": True}],
            "recovery": {
                "state": "not_created",
                "reason": "cache_write_required",
            },
            "telemetry": {
                "state": "not_recorded",
                "reason": "cache_write_required",
                "provider_cost": None,
            },
            "redaction_count": 0,
        }
    return {
        "selected_evidence": selected_evidence,
        "tokens": {
            "estimated": estimated,
            "actual": None,
            "budget": token_budget,
        },
        "omissions": [{"reason": "insufficient_budget", "mandatory": True}],
        "recovery": {"state": "available", "handle": handle},
        "telemetry": {
            "state": "not_measured",
            "reason": "omitted_context_not_delivered",
            "provider_cost": None,
        },
        "redaction_count": redactions,
    }


def pack_context(
    started: float,
    project_root: Path,
    context_path: str | None,
    target_symbol: str,
    token_budget: int,
    granted: ExecutionPermissions,
    as_v1: bool = False,
) -> ContinuityOutput:
    """Pack bounded context evidence, spilling to CCR cache if over budget."""
    if not context_path or token_budget < 1:
        return build_continuity_result(
            started,
            "error",
            "Context pack requires a repository-relative path and positive token budget.",
            operation="context_pack",
            granted=granted,
            as_v1=as_v1,
        )
    target = (project_root / context_path).resolve()
    if project_root not in target.parents or not target.is_file():
        return build_continuity_result(
            started,
            "skipped",
            "Context target was not found inside the project.",
            operation="context_pack",
            granted=granted,
            as_v1=as_v1,
        )
    gate = check_memory_before_pack(
        context_path,
        target_symbol,
        project_root=project_root,
        token_budget=token_budget,
        encoding=_DEFAULT_ENCODING,
    )
    if gate.hit:
        if gate.content is None:
            return build_continuity_result(
                started,
                "error",
                "Cached context payload was unavailable.",
                operation="context_pack",
                granted=granted,
                as_v1=as_v1,
            )
        packed = gate.content
    else:
        packed = ContextPacker(project_root).pack(
            target, target_symbol=target_symbol, max_tokens=1_000_000
        )
        if granted.cache_write:
            write_cache_fill(
                project_root,
                context_path,
                target_symbol,
                packed,
                token_budget=token_budget,
                encoding=_DEFAULT_ENCODING,
                view="v1" if as_v1 else "v2",
            )
    estimated = int(packed.get("tokens", 0))
    selected_evidence = [{"path": context_path, "selection": "target_file"}]
    if estimated > token_budget:
        allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
        if not allowed:
            envelope = _build_recovery_envelope(
                selected_evidence,
                estimated,
                token_budget,
                None,
                0,
                cache_write_denied=True,
            )
            return build_continuity_result(
                started,
                "skipped",
                f"Context recovery requires {', '.join(missing)}.",
                operation="context_pack",
                granted=granted,
                requested=_WRITE_PERMISSION,
                context_envelope=envelope,
                as_v1=as_v1,
            )
        safe_packed, redactions = SecretRedactor.redact_value(packed)
        tag = CCRStore(project_root).store_chunk(
            json.dumps(safe_packed, sort_keys=True, default=str)
        )
        handle = tag.removeprefix("<!-- ccr:chunk:").removesuffix(" -->")
        envelope = _build_recovery_envelope(
            selected_evidence, estimated, token_budget, handle, redactions
        )
        return build_continuity_result(
            started,
            "skipped",
            "Context pack requires a larger token budget.",
            operation="context_pack",
            granted=granted,
            requested=_WRITE_PERMISSION,
            context_envelope=envelope,
            as_v1=as_v1,
        )
    safe_packed, redactions = SecretRedactor.redact_value(packed)
    if not gate.hit and granted.cache_write:
        # MC04 §9.0: count the actual packing cost only when real packing work happened
        # (a cache hit re-delivers already-paid-for content) and delivery is confirmed
        # (fits budget, unlike the CCR-spill branch above, which never counts as "measured").
        TelemetryStore(project_root).record_memory_event(
            "packing",
            estimated,
            request_id=f"{context_path}:{target_symbol}:{token_budget}",
            event_id="packing",
            cache_write=True,
        )
    envelope = {
        "selected_evidence": selected_evidence,
        "tokens": {"estimated": estimated, "actual": None, "budget": token_budget},
        "omissions": [],
        "recovery": {"state": "not_needed"},
        "redaction_count": redactions,
    }
    return build_continuity_result(
        started,
        "ok",
        "Packed bounded context evidence.",
        operation="context_pack",
        granted=granted,
        raw=safe_packed,
        context_envelope=envelope,
        as_v1=as_v1,
    )


def retrieve_context(
    started: float,
    root: Path,
    handle: str | None,
    granted: ExecutionPermissions,
    as_v1: bool = False,
) -> ContinuityOutput:
    """Retrieve CCR chunk by handle."""
    database = root / ".rush" / "cache" / "ccr.db"
    content = (
        CCRStore(root).retrieve_chunk(handle or "", touch=granted.cache_write)
        if handle and database.is_file()
        else None
    )
    safe_content, redactions = (
        SecretRedactor.redact_value(content) if content is not None else (None, 0)
    )
    if content is not None and granted.cache_write and handle:
        # MC04 §9.0: a real handoff (content actually recovered) counted once per handle,
        # never on a miss/not-found lookup.
        handoff_tokens = len(tiktoken.get_encoding(_DEFAULT_ENCODING).encode(content))
        TelemetryStore(root).record_memory_event(
            "handoff",
            handoff_tokens,
            request_id=handle,
            event_id="handoff",
            cache_write=True,
        )
    recovery = {
        "state": "recovered" if content is not None else "not_found",
        "handle": handle,
    }
    return build_continuity_result(
        started,
        "ok" if content is not None else "skipped",
        "Recovered context handle."
        if content is not None
        else "Context handle was not found.",
        operation="context_retrieve",
        granted=granted,
        raw={"content": safe_content} if safe_content is not None else None,
        context_envelope={
            "selected_evidence": [],
            "tokens": {"estimated": None, "actual": None, "budget": None},
            "omissions": [],
            "recovery": recovery,
            "redaction_count": redactions,
        },
        as_v1=as_v1,
    )


_context_pack = pack_context
_context_retrieve = retrieve_context
