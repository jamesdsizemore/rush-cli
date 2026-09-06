"""Context packing and retrieval operations for session continuity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..codegraph.context_packer import ContextPacker
from ..permissions import (
    ExecutionPermissions,
    check_permissions,
)
from ..safety.redactor import SecretRedactor
from ..token_economy.ccr_store import CCRStore
from .results import _WRITE_PERMISSION, build_continuity_result

if TYPE_CHECKING:
    from ..tools.base import ToolResult


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
) -> ToolResult:
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
    packed = ContextPacker(project_root).pack(
        target, target_symbol=target_symbol, max_tokens=1_000_000
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
) -> ToolResult:
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
