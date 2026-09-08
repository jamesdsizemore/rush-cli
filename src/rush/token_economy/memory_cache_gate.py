"""Token-savings cache front-end for `pack_context()` (Phase 62 §6.1).

`check_memory_before_pack()` is a read-only, defended lookup ahead of a real
`ContextPacker.pack()` call: a `search()`-then-`recall()` pair that never
mutates state. Any defended-recall failure (signature mismatch, Trojan-source
content, a malformed FTS query) or a `stale=True` result collapses to
`hit=False` rather than propagating, so the caller always falls through to a
real pack on any doubt (§6.5 Invariant 1).

`write_cache_fill()` is the separately-gated write-back half: it persists a
`pack_context()` miss's real result as a `DERIVED` row, keyed by the exact
same cache key, so a later call for the identical `(context_path,
target_symbol)` pair can hit. It is a distinct call with a distinct
authorization requirement (`granted.cache_write`) from the read side above.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..memory.store import MemoryArtifact, MemorySubject, TypedArtifactStore

# Fixed source tag for cache-gate write-backs. `recall()` fails closed without
# a session_allowlist (Phase 61 §9 P61.9), so a read must allowlist the exact
# source a write used, or it can never see its own cache-fills.
_CACHE_SOURCE = "context_pack"
_CACHE_KEY_FIELD = "cache_key"


@dataclass(frozen=True)
class CacheGateResult:
    hit: bool
    artifact_id: str | None
    content: dict[str, Any] | None


def _cache_key(context_path: str, target_symbol: str) -> str:
    return f"{context_path}:{target_symbol}"


def check_memory_before_pack(
    context_path: str,
    target_symbol: str,
    subject: MemorySubject = "domain_knowledge",
    *,
    project_root: Path | None = None,
) -> CacheGateResult:
    """Defended `search()`-then-`recall()` read. Never mutates state, never raises."""
    cache_key = _cache_key(context_path, target_symbol)
    store = TypedArtifactStore(project_root)
    try:
        # FTS5 query syntax treats a bare ":" as a column filter and a bare
        # "/" outside quotes as a syntax error; quoting makes cache_key a
        # literal phrase match instead of a malformed query expression.
        query = f'"{cache_key}"'
        if not store.search(subject, query):
            return CacheGateResult(hit=False, artifact_id=None, content=None)
        artifacts = store.recall(subject, query, session_allowlist=[_CACHE_SOURCE])
    except Exception:
        return CacheGateResult(hit=False, artifact_id=None, content=None)

    for artifact in artifacts:
        if artifact.stale:
            continue
        # search()/recall() are coarse FTS matches, never an exact-key
        # guarantee; only a literal cache_key match counts as a real hit.
        if artifact.content.get(_CACHE_KEY_FIELD) != cache_key:
            continue
        content = {k: v for k, v in artifact.content.items() if k != _CACHE_KEY_FIELD}
        return CacheGateResult(hit=True, artifact_id=artifact.id, content=content)
    return CacheGateResult(hit=False, artifact_id=None, content=None)


def write_cache_fill(
    project_root: Path | None,
    context_path: str,
    target_symbol: str,
    packed: dict[str, Any],
    subject: MemorySubject = "domain_knowledge",
) -> None:
    """Write a `pack_context()` miss's real result back as a `DERIVED` cache row.

    Caller must already have confirmed `granted.cache_write is True` — this
    function performs no permission check of its own.
    """
    cache_key = _cache_key(context_path, target_symbol)
    store = TypedArtifactStore(project_root)
    store.write(
        MemoryArtifact(
            id=str(uuid.uuid4()),
            family="memory",
            subject=subject,
            trust_tier="DERIVED",
            content={**packed, _CACHE_KEY_FIELD: cache_key},
            source=_CACHE_SOURCE,
            created_at=time.time(),
            symbol_ref=f"{context_path}::{target_symbol}" if target_symbol else None,
        )
    )
