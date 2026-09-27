"""Context packing and retrieval operations for session continuity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import tiktoken

from ..codegraph.context_packer import ContextPacker
from ..memory.store import MemoryArtifact
from ..permissions import (
    ExecutionPermissions,
    check_permissions,
)
from ..safety.redactor import SecretRedactor
from ..token_economy.ccr_store import CCRStore
from ..token_economy.memory_cache_gate import (
    CacheGateResult,
    check_memory_before_pack,
    write_cache_fill,
)
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


def _memory_event_attribution(
    project_id: str | None,
    run_id: str | None,
    agent_id: str | None,
    session_id: str | None,
) -> dict[str, str]:
    """M11: `project_id`/`run_id`/`agent_id`/`session_id` are pure caller-
    supplied attribution -- never invented from a project root path (a
    filesystem path is not a registered project UUID). Omitted dimensions
    are left out so `TelemetryStore.record_memory_event()`'s own
    `_UNSCOPED` default applies, mirroring `memory/retrieval.py`'s own
    `_record_memory_event` helper."""
    return {
        key: value
        for key, value in (
            ("project_id", project_id),
            ("run_id", run_id),
            ("agent_id", agent_id),
            ("session_id", session_id),
        )
        if value is not None
    }


def _cache_fill_receipts(filled: MemoryArtifact | None) -> list[dict[str, Any]]:
    from ..tools.routing import memory_receipt

    if filled is None:
        return []
    return [
        memory_receipt(filled.id, filled.artifact_version, filled.source, "cache_fill")
    ]


def _cache_hit_receipts(gate: CacheGateResult) -> list[dict[str, Any]]:
    from ..tools.routing import memory_receipt

    if not gate.hit or gate.artifact_id is None or gate.revision is None:
        return []
    return [
        memory_receipt(gate.artifact_id, gate.revision, gate.source or "", "cache_hit")
    ]


def _pack_memory(
    used: list[dict[str, Any]], written: list[dict[str, Any]]
) -> dict[str, Any] | None:
    from ..tools.routing import memory_block

    return memory_block(used, written)


def pack_context(
    started: float,
    project_root: Path,
    context_path: str | None,
    target_symbol: str,
    token_budget: int,
    granted: ExecutionPermissions,
    as_v1: bool = False,
    *,
    invocation_id: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
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
    filled = None
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
            filled = write_cache_fill(
                project_root,
                context_path,
                target_symbol,
                packed,
                token_budget=token_budget,
                encoding=_DEFAULT_ENCODING,
                view="v1" if as_v1 else "v2",
            )
    # T19: a committed cache fill is `written` whether or not the pack is then
    # delivered; the gate hit is `used` only when delivered (below).
    written = _cache_fill_receipts(filled)
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
            memory=_pack_memory([], written),
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
            invocation_id=invocation_id,
            cache_write=True,
            **_memory_event_attribution(project_id, run_id, agent_id, session_id),
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
        memory=_pack_memory(_cache_hit_receipts(gate), written),
    )


def retrieve_context(
    started: float,
    root: Path,
    handle: str | None,
    granted: ExecutionPermissions,
    as_v1: bool = False,
    *,
    invocation_id: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
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
            invocation_id=invocation_id,
            cache_write=True,
            **_memory_event_attribution(project_id, run_id, agent_id, session_id),
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


def _read_stored(db: Path, handle: str) -> str | None:
    """One CCR row over a genuinely read-only connection: no constructor, no
    LRU touch, no telemetry (X1: `ccr.db` uses a rollback journal, so
    `mode=ro` leaves no side files)."""
    import sqlite3
    import urllib.parse

    uri = f"file:{urllib.parse.quote(str(db))}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        row = conn.execute(
            "SELECT content FROM chunks WHERE hash = ?", (handle,)
        ).fetchone()
    finally:
        conn.close()
    return None if row is None else str(row[0])


def _load_result(root: Path, handle: str) -> tuple[dict[str, Any], bytes]:
    """§3 item 10 steps 1-6: the stored T16 object for `handle`, or a
    RESULT_MISSING / RESULT_CORRUPT view error. Never reruns an engine."""
    import hashlib
    import re
    import sqlite3

    from ..delivery.compact import ViewError, ccr_path, is_storage_object

    if not re.fullmatch(r"[0-9a-f]{64}", handle or ""):
        raise ViewError(
            "RESULT_VIEW_INVALID", "handle must be 64 lowercase hex characters"
        )
    db = ccr_path(root, "read")
    if not db.is_file():
        raise ViewError("RESULT_MISSING", f"no stored result for handle {handle}")
    try:
        content = _read_stored(db, handle)
    except sqlite3.Error as exc:
        raise ViewError("RESULT_CORRUPT", f"result store is unreadable: {exc}") from exc
    if content is None:
        raise ViewError("RESULT_MISSING", f"no stored result for handle {handle}")
    data = content.encode("utf-8")
    if hashlib.sha256(data).hexdigest() != handle or not is_storage_object(content):
        raise ViewError("RESULT_CORRUPT", "stored result does not match its handle")
    return json.loads(content), data


def _result_page(
    root: Path,
    handle: str,
    stored: dict[str, Any],
    data: bytes,
    *,
    view: str,
    cursor: str | None,
    offset: int | None,
    limit: int,
    max_bytes: int,
    serialize: Any,
) -> dict[str, Any]:
    from ..delivery.compact import ViewError, decode_cursor, project_page, slice_bytes

    total = (
        len(stored["full_result"].get("findings") or [])
        if view == "result"
        else len(data)
    )
    start = offset or 0
    if cursor is not None:
        start = decode_cursor(
            cursor,
            root=root,
            handle=handle,
            view=view,
            limit=limit,
            max_bytes=max_bytes,
            total=total,
        )
    if isinstance(start, bool) or not isinstance(start, int) or not 0 <= start <= total:
        raise ViewError("RESULT_VIEW_INVALID", f"offset must be between 0 and {total}")
    if view == "bytes":
        return slice_bytes(
            stored,
            data,
            root=root,
            handle=handle,
            offset=start,
            limit=limit,
            max_bytes=max_bytes,
            serialize=serialize,
        )
    return project_page(
        stored["full_result"],
        list(stored["finding_ids"]),
        root=root,
        handle=handle,
        view="result",
        start=start,
        limit=limit,
        max_bytes=max_bytes,
        full_bytes=len(data),
        serialize=serialize,
    )


def retrieve_result_view(
    root: Path,
    handle: str,
    *,
    view: str,
    cursor: str | None = None,
    offset: int | None = None,
    limit: int | None = None,
    max_bytes: int | None = None,
    serialize: Any = None,
) -> dict[str, Any]:
    """T16 §3 item 10 (S16.6): a `result` page (findings with the compact
    projection) or a `bytes` slice of a stored compact result. Missing or
    corrupt stores are errors, never a rerun; a symlinked `.rush/cache`
    raises `ContainmentError`. T23's `rush_status(operation="result")`
    calls this same function."""
    from ..delivery.compact import (
        ViewError,
        error_payload,
        retrieval_size,
        validate_budget,
    )

    try:
        if view not in ("result", "bytes"):
            raise ViewError(
                "RESULT_VIEW_INVALID", f"view must be 'result' or 'bytes'; got {view!r}"
            )
        page_limit, budget = validate_budget(limit, max_bytes)
        if cursor is not None and offset is not None:
            raise ViewError(
                "RESULT_VIEW_INVALID", "pass either cursor or offset, not both"
            )
        stored, data = _load_result(root, handle)
        return _result_page(
            root,
            handle,
            stored,
            data,
            view=view,
            cursor=cursor,
            offset=offset,
            limit=page_limit,
            max_bytes=budget,
            serialize=serialize or retrieval_size,
        )
    except ViewError as exc:
        return error_payload("continuity", exc.code, exc.message)


_context_pack = pack_context
_context_retrieve = retrieve_context
