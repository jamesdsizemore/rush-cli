"""Token-savings cache front-end for `pack_context()` (Phase 62 §6.1, MC04 §9.0).

`check_memory_before_pack()` is a read-only, defended lookup ahead of a real
`ContextPacker.pack()` call: one `defended_recall()` query (MC02's own bounded
`search_candidates()` path, never a `search()`-then-`recall()` pair) that never mutates state.
Any defended-recall failure (signature mismatch, Trojan-source content, a malformed FTS
query) or a `stale=True` result collapses to `hit=False` rather than propagating, so the
caller always falls through to a real pack on any doubt (§6.5 Invariant 1). It never touches
`TelemetryStore` — a read-only lookup persists nothing.

`write_cache_fill()` is the separately-gated write-back half: it persists a
`pack_context()` miss's real result as a `DERIVED` row, keyed by the exact
same cache key, so a later call for the identical `(context_path,
target_symbol)` pair can hit. It is a distinct call with a distinct
authorization requirement (`granted.cache_write`) from the read side above.

MC04 §9.0 cache identity: the stored `cache_key` field stays the plain `context_path:
target_symbol` string (an existing, pinned on-disk contract other call sites match against
literally) — the additional identity dimensions (budget, tokenizer, namespace, audience,
view, engine revision) live alongside it in a nested `cache_identity` dict and are compared
on lookup only when both the request and the stored row carry a value for that dimension, so
a legacy row with no `cache_identity` at all (or a caller that doesn't care about a given
dimension) still hits exactly as before.
"""

from __future__ import annotations

import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..memory.retrieval import SourceValidationMemo, defended_recall
from ..memory.store import MemoryArtifact, MemorySubject, TypedArtifactStore

# Fixed source tag for cache-gate write-backs. `recall()`/`defended_recall()` fail closed
# without a session_allowlist (Phase 61 §9 P61.9), so a read must allowlist the exact source
# a write used, or it can never see its own cache-fills.
_CACHE_SOURCE = "context_pack"
_CACHE_KEY_FIELD = "cache_key"
_CACHE_IDENTITY_FIELD = "cache_identity"
# Bumped whenever ContextPacker's packing algorithm changes in a way that would make an
# already-cached payload no longer represent what a fresh pack would produce.
_ENGINE_REVISION = "context-pack-v1"


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
    memo: SourceValidationMemo | None = None,
    token_budget: int | None = None,
    encoding: str | None = None,
    view: str | None = None,
) -> CacheGateResult:
    """Defended one-query read via `defended_recall()`. Never mutates state, never raises.

    `token_budget`/`encoding`/`view`, when given, must match the stored `cache_identity`'s
    value for that dimension whenever the stored row actually has one — a caller that omits
    any of them (or a legacy/seeded row with no `cache_identity` at all) skips that
    comparison, so this stays fully backward compatible with callers that only pass
    `context_path`/`target_symbol`. `view` is currently write-only from every real caller
    (`write_cache_fill()` stores it, but no caller of `check_memory_before_pack()` passes it
    yet), so this comparison is behaviorally inert today — it only matters once a caller
    starts varying packed content by view.
    """
    cache_key = _cache_key(context_path, target_symbol)
    store = TypedArtifactStore(project_root)
    artifacts: list[MemoryArtifact] = []
    # Failed defended reads are cache misses; never reuse unverified content.
    with suppress(Exception):
        artifacts = defended_recall(
            store, subject, cache_key, [_CACHE_SOURCE], memo=memo
        )
    for artifact in artifacts:
        if artifact.stale or not artifact.content_hash or not artifact.symbol_ref:
            continue
        # search_candidates() is a coarse FTS match, never an exact-key guarantee; only a
        # literal cache_key match counts as a real hit.
        if artifact.content.get(_CACHE_KEY_FIELD) != cache_key:
            continue
        identity = artifact.content.get(_CACHE_IDENTITY_FIELD)
        if isinstance(identity, dict):
            if (
                token_budget is not None
                and "token_budget" in identity
                and identity["token_budget"] != token_budget
            ):
                continue
            if (
                encoding is not None
                and "encoding" in identity
                and identity["encoding"] != encoding
            ):
                continue
            if view is not None and "view" in identity and identity["view"] != view:
                continue
        content = {
            k: v
            for k, v in artifact.content.items()
            if k not in (_CACHE_KEY_FIELD, _CACHE_IDENTITY_FIELD)
        }
        return CacheGateResult(hit=True, artifact_id=artifact.id, content=content)
    return CacheGateResult(hit=False, artifact_id=None, content=None)


def write_cache_fill(
    project_root: Path | None,
    context_path: str,
    target_symbol: str,
    packed: dict[str, Any],
    subject: MemorySubject = "domain_knowledge",
    *,
    token_budget: int | None = None,
    encoding: str | None = None,
    view: str | None = None,
) -> None:
    """Write a `pack_context()` miss's real result back as a `DERIVED` cache row.

    Caller must already have confirmed `granted.cache_write is True` — this
    function performs no permission check of its own.
    """
    # The producer hashes the same source read used to build packed_text. A later
    # read here could pair changed source bytes with an already-obsolete payload.
    content_hash = packed.get("source_content_hash")
    if not isinstance(content_hash, str) or not content_hash:
        return
    cache_key = _cache_key(context_path, target_symbol)
    store = TypedArtifactStore(project_root)
    identity: dict[str, Any] = {
        "namespace": str(store.project_root),
        "audience": _CACHE_SOURCE,
        "engine_revision": _ENGINE_REVISION,
    }
    if token_budget is not None:
        identity["token_budget"] = token_budget
    if encoding is not None:
        identity["encoding"] = encoding
    if view is not None:
        identity["view"] = view
    store.write(
        MemoryArtifact(
            id=str(uuid.uuid4()),
            family="memory",
            subject=subject,
            trust_tier="DERIVED",
            content={
                **packed,
                _CACHE_KEY_FIELD: cache_key,
                _CACHE_IDENTITY_FIELD: identity,
            },
            source=_CACHE_SOURCE,
            created_at=time.time(),
            symbol_ref=f"{context_path}::{target_symbol}",
            content_hash=content_hash,
        )
    )
