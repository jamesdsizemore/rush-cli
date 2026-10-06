"""MC02 §9.0 bounded recall and exact expansion.

`recall_page()` pages `TypedArtifactStore.search_candidates()` into a token/byte-bounded
result within a 512-candidate scan cap, returning an HMAC-signed continuation cursor when the
cap is hit before the page fills. `expand_artifact()` returns exact byte slices of one stored
artifact version, base64-encoded so a caller can page across a multi-byte-character boundary
and still reconstruct the original bytes exactly on concatenation.

Both functions return a plain dict with a leading `"code"` key (`"OK"` or one of the §9.0
warn/fail codes); `rush.tools.memory.MemoryTool` maps that code onto `ToolResult.status` and
wraps the rest as the operation envelope's `data`. Neither function raises for a denied,
missing, or stale-cursor request — only for a genuine programming error.

`defended_recall()` (MC04) is the one shared defended-lookup path for cache/citation
consumers that used to run their own `store.search()`-then-`store.recall()` pair: it issues a
single `store.search_candidates()` query (MC02's already-bounded/ranked path, never a second
raw FTS query) and applies `store.recall()`'s exact signature/Trojan-source/staleness checks,
routed through a caller-supplied `SourceValidationMemo` so N candidate rows that share one
backing source file are hashed/API-diffed once per request, not once per row.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import math
import sqlite3
import time
import uuid
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, Literal

import tiktoken

from rush.memory.embeddings import (
    EmbeddingConfig,
    EmbeddingEngineUnavailable,
    EmbeddingResponseError,
    embed_chunks,
)
from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.store import (
    MemoryArtifact,
    MemorySubject,
    OwnerScope,
    SignatureMismatchError,
    TrojanSourceFoundError,
    TypedArtifactStore,
    _inspect_text_for_trojan_chars,
    _row_to_artifact,
    _row_value,
    compute_content_signature,
    legacy_owner_scope,
    owner_scope_for_row,
    payload_digest,
)
from rush.token_economy.telemetry import TelemetryStore

_SCAN_CAP = 512
_BATCH_SIZE = 64
_RANKING_VERSION = "mc02-v1"

# MC12 §6.7: reciprocal-rank-fusion constant and vector-candidate scan cap (documented
# ceiling, matches the lexical `_SCAN_CAP`).
_RRF_K = 60
_VECTOR_SCAN_CAP = 512

DEFAULT_LIMIT = 8
DEFAULT_MAX_TOKENS = 2048
DEFAULT_MAX_BYTES = 8192
DEFAULT_ENCODING = "cl100k_base"

_EXCERPT_CHARS = 200

# T19: `MerkleInvalidator.hash_content` (sha256 of the UTF-8 text) through an
# instance built without `__init__`, whose constructor creates `.rush/cache`;
# a read-only recall creates nothing.
_CONTENT_HASHER = MerkleInvalidator.__new__(MerkleInvalidator)


@dataclasses.dataclass
class SourceValidationMemo:
    """MC04 request-local canonical-path memo: caches a source file's current content hash
    and API-diff freshness result so `defended_recall()` computes each exactly once per
    request, however many returned candidates share that same backing file. Discard after
    the request that created it — never persisted, never shared across requests."""

    _hash_cache: dict[Path, str | None] = dataclasses.field(default_factory=dict)
    _api_diff_cache: dict[tuple[Path, str], Any] = dataclasses.field(
        default_factory=dict
    )

    def source_hash(self, file_path: Path) -> str | None:
        if file_path not in self._hash_cache:
            try:
                self._hash_cache[file_path] = _CONTENT_HASHER.hash_content(
                    file_path.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError):
                self._hash_cache[file_path] = None
        return self._hash_cache[file_path]

    def api_diff(self, project_root: Path, file_path: Path, symbol: str) -> Any:
        key = (file_path, symbol)
        if key not in self._api_diff_cache:
            # Deferred import mirrors `TypedArtifactStore.recall()`'s own local import of
            # `ApiDiffer` (avoids a module-load-time cycle between `rush.memory` and
            # `rush.tools`).
            from rush.tools.api_diff import ApiDiffer

            self._api_diff_cache[key] = ApiDiffer(
                project_root=project_root
            ).diff_symbol(file_path, symbol)
        return self._api_diff_cache[key]


# 72-T01: memory operation -> policy grant operation (T003 §4). Anything else
# (`overlay_read`, `write`, `bootstrap`, a raw grant name) passes through unchanged.
_GRANT_FOR_OPERATION = {
    "ask": "ask",
    "recall": "ask",
    "related": "ask",
    "explain": "ask",
    "list": "list",
    "expand": "expand",
    "historical": "history",
}

Freshness = Literal["current", "stale", "unknown", "not_applicable"]
VisibilityMode = Literal["ordinary", "inspect", "historical"]


@dataclasses.dataclass(frozen=True)
class MemoryAccess:
    """72-T01: the resolved authority behind one memory read.

    `kind="policy"` comes from `resolve()` (the owner-consented grant in
    `rush.memory.authorization`, never a caller claim); `kind="legacy_allowlist"` is
    the explicit `session_allowlist` form (`legacy()`), which filters by source and,
    only when an owner is declared, by owner. Every read route takes one of these and
    decides each row through `evaluate_artifact_visibility`.
    """

    kind: Literal["policy", "legacy_allowlist"]
    project_root: Path
    operation: str
    sources: tuple[str, ...]
    owner_scope: OwnerScope | None
    grant_id: str | None = None
    policy_revision: int | None = None
    project_id: str | None = None
    worktree_id: str | None = None
    session_binding: str | None = None
    data_root: Path | None = None
    requested_sources: tuple[str, ...] = ()

    @classmethod
    def legacy(
        cls,
        project_root: Path,
        session_allowlist: Iterable[str] | None,
        *,
        owner_scope: OwnerScope | None = None,
        operation: str = "ask",
    ) -> MemoryAccess:
        """The legacy explicit-allowlist access. An empty allowlist yields no sources,
        so every route fails closed on it."""
        return cls(
            kind="legacy_allowlist",
            project_root=Path(project_root).resolve(),
            operation=operation,
            sources=tuple(sorted(set(session_allowlist or ()))),
            owner_scope=owner_scope,
        )

    @classmethod
    def resolve(
        cls,
        project_root: Path,
        *,
        operation: str,
        owner_scope: OwnerScope | None = None,
        requested_sources: Iterable[str] = (),
        session_binding: str | None = None,
        data_root: Path | None = None,
    ) -> MemoryAccess | None:
        """Policy access for one operation, or `None` when the policy denies it (a
        missing policy included). Never writes: `resolve_memory_scope` only reads."""
        from rush.memory.authorization import resolve_memory_scope

        requested = tuple(requested_sources)
        result = resolve_memory_scope(
            project_root=Path(project_root),
            operation=_GRANT_FOR_OPERATION.get(operation, operation),
            owner_scope=owner_scope,
            requested_sources=list(requested),
            session_binding=session_binding,
            data_root=data_root,
        )
        if result.get("access") not in ("read", "write"):
            return None
        try:
            owner = OwnerScope.from_value(result["owner_scope"])
        except (TypeError, ValueError):
            return None
        return cls(
            kind="policy",
            project_root=Path(result["project_root"]),
            operation=operation,
            sources=tuple(result["approved_sources"]),
            owner_scope=owner,
            grant_id=result["grant_id"],
            policy_revision=result["policy_revision"],
            project_id=result["project_id"],
            worktree_id=result["worktree_id"],
            session_binding=session_binding,
            data_root=data_root,
            requested_sources=requested,
        )

    def recheck(self) -> Literal["ok", "changed", "denied"]:
        """Resolve again with this access's inputs: `denied` when the policy now denies
        it, `changed` when the grant, revision, ids, root, owner or sources moved."""
        if self.kind != "policy":
            return "ok"
        fresh = MemoryAccess.resolve(
            self.project_root,
            operation=self.operation,
            owner_scope=self.owner_scope,
            requested_sources=self.requested_sources,
            session_binding=self.session_binding,
            data_root=self.data_root,
        )
        if fresh is None:
            return "denied"
        return "ok" if fresh == self else "changed"

    @property
    def historical_allowed(self) -> bool:
        """Historical reads need the legacy explicit form or a `history` grant."""
        return (
            self.kind == "legacy_allowlist"
            or _GRANT_FOR_OPERATION.get(self.operation, self.operation) == "history"
        )


@dataclasses.dataclass(frozen=True)
class VisibilityDecision:
    """72-T01: the one shared answer for one row under one access and mode."""

    visible: bool
    usable_as_current: bool
    freshness: Freshness
    reason_codes: tuple[str, ...]
    reference: dict[str, Any] | None


_NOT_VISIBLE = VisibilityDecision(False, False, "unknown", ("not_visible",), None)


def read_access(
    project_root: Path,
    operation: str,
    session_allowlist: Iterable[str] | None = None,
    *,
    owner_scope: OwnerScope | None = None,
    data_root: Path | None = None,
) -> MemoryAccess | None:
    """72-T01 read convention shared by `MemoryTool` and the learned-advice readers: a
    non-empty `session_allowlist` is the legacy form; otherwise the policy is resolved
    at `data_root` (default: the OS data root). `None` means fail closed."""
    allowlist = list(session_allowlist or ())
    if allowlist:
        return MemoryAccess.legacy(
            project_root, allowlist, owner_scope=owner_scope, operation=operation
        )
    return MemoryAccess.resolve(
        project_root, operation=operation, owner_scope=owner_scope, data_root=data_root
    )


def _route_access(
    store: TypedArtifactStore,
    access: MemoryAccess | None,
    session_allowlist: Iterable[str] | None,
) -> MemoryAccess | None:
    """One route's access: the given `access`, else the legacy allowlist form. Both
    raise `ValueError`; neither, or no sources, is `None` (fail closed)."""
    if access is not None and session_allowlist is not None:
        raise ValueError("pass access or session_allowlist, not both")
    if access is None:
        if not session_allowlist:
            return None
        access = MemoryAccess.legacy(store.project_root, session_allowlist)
    return access if access.sources else None


def _row_owner(row: sqlite3.Row, project_root: Path) -> OwnerScope | None:
    try:
        return owner_scope_for_row(row, project_root)
    except (TypeError, ValueError):
        return None


def _root_allows(store: TypedArtifactStore, access: MemoryAccess) -> bool:
    """§3 step 2 root check. X1: the personal-overlay access (`overlay_read` with the
    overlay owner) reads only the store rooted at `<data_root>/user`; every other
    access needs `access.project_root == store.project_root`."""
    if access.operation == "overlay_read" and access.owner_scope is not None:
        from rush.memory.authorization import (
            MemoryPolicyError,
            user_overlay_owner_scope,
        )

        try:
            overlay = user_overlay_owner_scope(data_root=access.data_root)
        except MemoryPolicyError:
            return False
        if access.owner_scope == overlay:
            return str(store.project_root) == overlay.id
    return access.project_root == store.project_root


def _access_allows(
    store: TypedArtifactStore,
    row: sqlite3.Row,
    access: MemoryAccess,
    mode: VisibilityMode,
) -> bool:
    if not _root_allows(store, access) or row["source"] not in access.sources:
        return False
    if (
        access.owner_scope is not None
        and _row_owner(row, store.project_root) != access.owner_scope
    ):
        return False
    return mode != "historical" or access.historical_allowed


def _lifecycle_reasons(row: sqlite3.Row, now: float) -> list[str]:
    """`expired` needs a sweep (`expired_at`) or a stamped `expires_at` in the past; an
    elapsed TTL alone stays the sweep's job."""
    reasons = []
    if _row_value(row, "archived_at") is not None:
        reasons.append("archived")
    expires_at = _row_value(row, "expires_at")
    if _row_value(row, "expired_at") is not None or (
        expires_at is not None and expires_at <= now
    ):
        reasons.append("expired")
    return reasons


def _parsed_content(row: sqlite3.Row) -> dict[str, Any] | None:
    try:
        content = json.loads(row["content"])
    except (TypeError, ValueError, RecursionError):
        return None
    return content if isinstance(content, dict) else None


def _integrity(row: sqlite3.Row) -> tuple[list[str], str]:
    """Integrity reasons and the OD-1 label: `verified` (bound by an authorized write),
    `backfilled` (bound by the additive migration) or `unbound` (no binding)."""
    content = _parsed_content(row)
    reasons = []
    if content is None:
        reasons.append("integrity_content_corrupt")
    if row["trust_tier"] == "STATED":
        signature = row["signature"]
        if not signature:
            reasons.append("integrity_signature_missing")
        elif content is None or compute_content_signature(content) != signature:
            reasons.append("integrity_signature_mismatch")
    if content is not None and _inspect_text_for_trojan_chars(
        json.dumps(content, ensure_ascii=False)
    ):
        reasons.append("integrity_trojan_source")
    digest = _row_value(row, "payload_hash")
    text = row["content"]
    mismatched = digest is not None and (
        not isinstance(text, str) or payload_digest(text) != digest
    )
    if mismatched:
        reasons.append("integrity_payload_mismatch")
        label = "mismatch"
    elif digest is None:
        label = "unbound"
    elif _row_value(row, "payload_hash_origin") == "backfill":
        label = "backfilled"
    else:
        label = "verified"
    return reasons, label


# PM gate delta 2 (B6): checkpoint-journal rows store the checkpoint *name* in
# `symbol_ref` (`checkpoint_journal.py`), not a code anchor.
_CHECKPOINT_SOURCE = "checkpoint_journal:save_checkpoint"


def _freshness_of(
    store: TypedArtifactStore,
    symbol_ref: str | None,
    content_hash: str | None,
    memo: SourceValidationMemo,
    source: str | None,
) -> tuple[Freshness, tuple[str, ...]]:
    """§3 step 6: the first matching check wins. Containment is decided before the
    file is touched, so an outside file is never hashed, read or parsed. A checkpoint
    row naming a checkpoint (no `::`) is unanchored; an anchored one is checked."""
    if symbol_ref is None or (source == _CHECKPOINT_SOURCE and "::" not in symbol_ref):
        return "not_applicable", ()
    # `path::` (an empty symbol) anchors the whole file, as cache fills write it.
    path_part, sep, symbol = symbol_ref.partition("::")
    if not sep or not path_part:
        return "unknown", ("symbol_ref_malformed",)
    from rush.memory.trust import contained_source_path

    file_path = contained_source_path(store.project_root, path_part)
    if file_path is None:
        return "unknown", ("source_not_contained",)
    if not content_hash:
        return "unknown", ("source_hash_missing",)
    if not file_path.is_file():
        return "unknown", ("source_missing",)
    current_hash = memo.source_hash(file_path)
    if current_hash is None:
        return "unknown", ("source_unreadable",)
    if current_hash != content_hash:
        return "stale", ("source_hash_mismatch",)
    if file_path.suffix != ".py":
        return "unknown", ("parser_unsupported",)
    if not symbol:
        # A whole-file anchor has no symbol to API-diff: its source hash decides, as
        # before T01, and a read spawns no `git`.
        return "current", ()
    diff = memo.api_diff(store.project_root, file_path, symbol)
    if isinstance(diff, dict):
        return "stale", ("api_changed",)
    if diff is not None:
        return "unknown", ("api_baseline_unknown",)
    return "current", ()


def artifact_freshness(
    store: TypedArtifactStore,
    artifact: MemoryArtifact | sqlite3.Row,
    *,
    now: float | None = None,
    memo: SourceValidationMemo | None = None,
) -> tuple[str, tuple[str, ...]]:
    """X5: `(freshness, reasons)` for one artifact, with no access value and no write --
    the same freshness `evaluate_artifact_visibility` reports. Unanchored rows give
    `("not_applicable", ())`. `now` is accepted for a uniform read signature; freshness
    depends only on the source file."""
    del now
    memo = memo or SourceValidationMemo()
    if isinstance(artifact, MemoryArtifact):
        return _freshness_of(
            store, artifact.symbol_ref, artifact.content_hash, memo, artifact.source
        )
    return _freshness_of(
        store,
        artifact["symbol_ref"],
        artifact["content_hash"],
        memo,
        artifact["source"],
    )


def _reference(
    store: TypedArtifactStore,
    row: sqlite3.Row,
    access: MemoryAccess,
    freshness: str,
    integrity: str,
) -> dict[str, Any]:
    owner = _row_owner(row, store.project_root)
    return {
        "artifact_id": row["id"],
        "artifact_version": row["artifact_version"],
        "project_id": access.project_id,
        "worktree_id": access.worktree_id,
        "owner_scope": owner.as_dict() if owner is not None else None,
        "source": row["source"],
        "subject": row["subject"],
        "trust_tier": row["trust_tier"],
        "origin_kind": row["origin_kind"],
        "origin_id": row["origin_id"],
        "freshness": freshness,
        "integrity": integrity,
        "payload_hash": _row_value(row, "payload_hash"),
    }


def _decide(
    store: TypedArtifactStore,
    row: sqlite3.Row,
    *,
    access: MemoryAccess,
    mode: VisibilityMode,
    now: float | None,
    memo: SourceValidationMemo | None,
) -> VisibilityDecision:
    """§3 steps 3-8 for a row that already passed the access gate."""
    moment = time.time() if now is None else now
    integrity_reasons, label = _integrity(row)
    blocking = _lifecycle_reasons(row, moment) + integrity_reasons
    if blocking and mode != "historical":
        return _NOT_VISIBLE
    freshness, freshness_reasons = _freshness_of(
        store,
        row["symbol_ref"],
        row["content_hash"],
        memo or SourceValidationMemo(),
        row["source"],
    )
    reasons = tuple(sorted({*blocking, *freshness_reasons}))
    return VisibilityDecision(
        visible=True,
        usable_as_current=not reasons and freshness in ("current", "not_applicable"),
        freshness=freshness,
        reason_codes=reasons,
        reference=_reference(store, row, access, freshness, label),
    )


def evaluate_artifact_visibility(
    store: TypedArtifactStore,
    artifact: sqlite3.Row | MemoryArtifact | None,
    *,
    access: MemoryAccess,
    mode: VisibilityMode = "ordinary",
    now: float | None = None,
    memo: SourceValidationMemo | None = None,
) -> VisibilityDecision:
    """72-T01: the one shared visibility decision every memory read route uses.

    A `MemoryArtifact` is re-read as its current row. Denied by root, source, owner or
    an unauthorized historical mode: `NOT` (`visible=False`, `("not_visible",)`, no
    reference). Archived, expired or integrity-failed rows are `NOT` in ordinary and
    inspect modes and visible-but-not-usable, with sorted reasons, in historical mode.
    Ordinary delivery needs `visible and usable_as_current`: no reasons and freshness
    `current` or `not_applicable`.
    """
    row = (
        store.get_current_row(artifact.id)
        if isinstance(artifact, MemoryArtifact)
        else artifact
    )
    if row is None or not _access_allows(store, row, access, mode):
        return _NOT_VISIBLE
    return _decide(store, row, access=access, mode=mode, now=now, memo=memo)


def _raise_legacy_integrity(row: sqlite3.Row) -> None:
    """The legacy recall contract (Invariants 3/4): raise rather than skip."""
    content = _parsed_content(row)
    if row["trust_tier"] == "STATED" and (
        not row["signature"]
        or content is None
        or compute_content_signature(content) != row["signature"]
    ):
        raise SignatureMismatchError(
            f"signature mismatch for STATED artifact {row['id']}"
        )
    if content is not None:
        findings = _inspect_text_for_trojan_chars(
            json.dumps(content, ensure_ascii=False)
        )
        if findings:
            raise TrojanSourceFoundError(
                f"Trojan Source characters detected in artifact {row['id']}: {findings}"
            )


def visible_artifacts(
    store: TypedArtifactStore,
    rows: Iterable[sqlite3.Row],
    *,
    access: MemoryAccess,
    mode: VisibilityMode = "ordinary",
    now: float | None = None,
    memo: SourceValidationMemo | None = None,
    legacy_raise: bool = False,
) -> list[MemoryArtifact]:
    """`rows` through the shared decision, as `MemoryArtifact`s carrying their decision
    `freshness`. The decision sets `stale=True` only for `stale` freshness and never
    clears a stored `stale` flag. Ordinary mode keeps rows usable as
    current; inspect and historical keep every visible row. With `legacy_raise`, a
    legacy-allowlist access raises `SignatureMismatchError`/`TrojanSourceFoundError`
    for a row that passed the source/owner filter."""
    memo = memo or SourceValidationMemo()
    moment = time.time() if now is None else now
    default_owner = legacy_owner_scope(store.project_root)
    found: list[MemoryArtifact] = []
    for row in rows:
        if not _access_allows(store, row, access, mode):
            continue
        if legacy_raise and access.kind == "legacy_allowlist":
            _raise_legacy_integrity(row)
        decision = _decide(store, row, access=access, mode=mode, now=moment, memo=memo)
        if not decision.visible or (
            mode == "ordinary" and not decision.usable_as_current
        ):
            continue
        try:
            artifact = _row_to_artifact(row, default_owner_scope=default_owner)
        except (TypeError, ValueError):
            continue
        if not isinstance(artifact.content, dict):
            continue
        found.append(
            dataclasses.replace(
                artifact,
                freshness=decision.freshness,
                stale=artifact.stale or decision.freshness == "stale",
            )
        )
    return found


def read_visible(
    project_root: Path,
    queries: Iterable[tuple[MemorySubject, str]],
    *,
    access: MemoryAccess,
    now: float | None = None,
) -> list[list[MemoryArtifact]]:
    """72-T01 (OD-3) learned-advice reads: one `search_rows()` FTS match per
    `(subject, query)` through a read-only view and the shared decision (ordinary mode),
    one result list per query. A missing, old or unreadable store reads nothing and
    creates nothing."""
    pending = list(queries)
    view, _state = TypedArtifactStore.open_readonly_view(project_root)
    if view is None:
        return [[] for _ in pending]
    memo = SourceValidationMemo()
    try:
        found = [
            visible_artifacts(
                view,
                view.search_rows(subject, query),
                access=access,
                now=now,
                memo=memo,
            )
            for subject, query in pending
        ]
    finally:
        view.close()
    # 72-T01 F2: recheck immediately before emit; a moved policy emits nothing.
    return found if access.recheck() == "ok" else [[] for _ in pending]


def defended_recall(
    store: TypedArtifactStore,
    subject: MemorySubject,
    query: str,
    session_allowlist: Iterable[str] | None = None,
    *,
    memo: SourceValidationMemo | None = None,
    access: MemoryAccess | None = None,
    now: float | None = None,
) -> list[MemoryArtifact]:
    """MC04 one-query defended lookup: `store.search_candidates()` (MC02's own bounded/ranked
    query — never a second raw FTS query), deduplicating source-file hashing and API-diff
    calls across candidates via `memo` (fresh per call when the caller passes none).

    72-T01: every candidate goes through `evaluate_artifact_visibility` in ordinary mode,
    so only rows usable as current come back. `access` and `session_allowlist` are
    mutually exclusive (`ValueError`); neither fails closed.

    `query` is the raw (unquoted) search text — `search_candidates()` quotes it as an FTS5
    literal phrase itself; callers must not pre-quote it (unlike the legacy `store.search()`).
    A legacy allowlist raises `SignatureMismatchError`/`TrojanSourceFoundError` exactly as
    `store.recall()` does; callers that treat a defended read as fail-closed should keep
    wrapping this in `contextlib.suppress(Exception)`, same as before.
    """
    access = _route_access(store, access, session_allowlist)
    if access is None or access.recheck() != "ok":
        return []
    moment = time.time() if now is None else now
    rows = store.search_candidates(
        subject,
        query,
        source_allowlist=list(access.sources),
        scan_limit=_SCAN_CAP,
        owner_scope=access.owner_scope,
        now=moment,
    )
    found = visible_artifacts(
        store,
        rows,
        access=access,
        mode="ordinary",
        now=moment,
        memo=memo,
        legacy_raise=True,
    )
    # 72-T01 F2: recheck immediately before emit; a moved policy emits nothing.
    return found if access.recheck() == "ok" else []


def _record_memory_event(
    telemetry: TelemetryStore | None,
    kind: str,
    tokens: int,
    *,
    request_id: str | None,
    event_id: str | None,
    invocation_id: str | None,
    project_id: str | None,
    run_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    opt_in: bool,
    cache_write: bool,
) -> None:
    """No-op unless a caller opts into real cost accounting by passing `telemetry` plus both
    IDs — existing `recall_page()`/`expand_artifact()` callers that pass none of this see zero
    behavior change. P69-07 subsection e: `invocation_id` identifies this call, never the
    content-derived `request_id` — a caller (`tools/memory.py`, out of this fix's reach)
    passing the same content-derived `request_id` twice for two genuinely distinct calls no
    longer collides, since `invocation_id` is minted per call by `recall_page()`/
    `expand_artifact()`/`hybrid_page()`, not reused from `request_id`.

    M11: `project_id`/`run_id`/`agent_id`/`session_id` are pure caller-supplied attribution
    (never invented from `store.project_root` -- a path is not a registered project UUID).
    Omitted dimensions are left unset here so `TelemetryStore.record_memory_event()`'s own
    `_UNSCOPED` default applies, rather than duplicating that sentinel in two places."""
    if telemetry is None or not request_id or not event_id:
        return
    attribution = {
        key: value
        for key, value in (
            ("project_id", project_id),
            ("run_id", run_id),
            ("agent_id", agent_id),
            ("session_id", session_id),
        )
        if value is not None
    }
    telemetry.record_memory_event(
        kind,
        tokens,
        request_id=request_id,
        event_id=event_id,
        invocation_id=invocation_id,
        opt_in=opt_in,
        cache_write=cache_write,
        **attribution,
    )


def _encoder(encoding: str) -> tiktoken.Encoding:
    return tiktoken.get_encoding(encoding)


def _count_tokens(text: str, encoding: str) -> int:
    return len(_encoder(encoding).encode(text))


def _encode_cursor(key: bytes, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    body_b64 = base64.urlsafe_b64encode(body).rstrip(b"=").decode("ascii")
    signature = hmac.new(key, body, hashlib.sha256).hexdigest()
    return f"{body_b64}.{signature}"


def _decode_cursor(key: bytes, cursor: str) -> dict[str, Any] | None:
    """Returns `None` for anything untrustworthy: wrong shape, bad signature, or a payload
    that isn't the JSON object `_encode_cursor()` produces. Callers treat `None` as
    restart-required, never as an empty-but-valid cursor."""
    try:
        body_b64, signature = cursor.split(".", 1)
        padding = "=" * (-len(body_b64) % 4)
        body = base64.urlsafe_b64decode(body_b64 + padding)
        expected = hmac.new(key, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(body)
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _excerpt(content: dict[str, Any]) -> str:
    text = content.get("text")
    if not isinstance(text, str):
        text = json.dumps(content, ensure_ascii=False, sort_keys=True)
    return text[:_EXCERPT_CHARS]


def _item_relations(
    store: TypedArtifactStore,
    artifact_id: str,
    version: int,
    access: MemoryAccess,
    *,
    now: float | None = None,
    memo: SourceValidationMemo | None = None,
) -> list[dict[str, Any]]:
    """MC03: the candidate's authorized depth-1 relations through
    `related_artifacts()`, which revalidates every neighbor's source and current
    version. 72-T01: a neighbor the shared decision does not deliver as current
    (archived, expired, tampered, another owner, stale) is dropped, never disclosed."""
    # Deferred import: `rush.memory.relations` imports this module's budgets.
    from rush.memory.relations import related_artifacts

    related = related_artifacts(
        store,
        artifact_id=artifact_id,
        version=version,
        session_allowlist=list(access.sources),
    )
    if related["code"] != "OK":
        return []
    kept = []
    for item in related["items"]:
        decision = evaluate_artifact_visibility(
            store,
            store.get_current_row(item["id"]),
            access=access,
            now=now,
            memo=memo,
        )
        if decision.usable_as_current:
            kept.append(item)
    return kept


def _candidate_to_item(
    row: Any,
    store: TypedArtifactStore,
    access: MemoryAccess,
    decision: VisibilityDecision,
    *,
    now: float | None = None,
    memo: SourceValidationMemo | None = None,
) -> dict[str, Any] | None:
    """`None` marks a corrupt candidate (malformed/non-object `content`) to skip — never
    raises, so one bad row can't abort the whole page (MC02.1 "corrupt candidates do not
    starve page"). 72-T01: `freshness` is the shared decision's vocabulary."""
    try:
        content = json.loads(row["content"])
    except (TypeError, ValueError, RecursionError):
        return None
    if not isinstance(content, dict):
        return None
    return {
        "id": row["id"],
        "version": row["artifact_version"],
        "excerpt": _excerpt(content),
        "source": row["source"],
        "trust": row["trust_tier"],
        "freshness": decision.freshness,
        "relations": _item_relations(
            store, row["id"], row["artifact_version"], access, now=now, memo=memo
        ),
    }


def _measure_page(
    items: list[dict[str, Any]], next_cursor: str | None, complete: bool, encoding: str
) -> tuple[int, int]:
    """Byte/token size of the serialized `data` payload a page will actually return — the
    §9.0 "budgets include the serialized returned memory payload, metadata and cursor"
    envelope, not the outer MCP/JSON-RPC transport framing (counted separately, per §9.0)."""
    payload = {
        "items": items,
        "next_cursor": next_cursor,
        "complete": complete,
        "encoding": encoding,
    }
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return len(text.encode("utf-8")), _count_tokens(text, encoding)


def _contains_special_token(text: str, encoding: str) -> bool:
    """Whether tiktoken's default `encode` would refuse `text` (it raises
    `ValueError` on any special-token string)."""
    return any(token in text for token in _encoder(encoding).special_tokens_set)


def _trial_page_bytes(
    items: list[dict[str, Any]],
    items_bytes: int,
    item: dict[str, Any],
    *,
    max_bytes: int,
    max_tokens: int,
    encoding: str,
) -> int | None:
    """Byte size of the `_measure_page(items + [item], None, True, ...)` page,
    or `None` when that page exceeds either budget -- the same decision as
    measuring the whole trial page, without retokenizing it per candidate.

    `items_bytes` is the running byte size of the current page. Appending an
    item adds its compact JSON plus one separating comma. Tiktoken's
    encodings are byte-level, so a text never has more tokens than bytes:
    while the trial page's bytes are within `max_tokens` its tokens are too,
    and only a larger page is fully tokenized. An item carrying a
    special-token string is always fully tokenized so tiktoken raises its
    `ValueError` exactly as it did when every trial page was tokenized."""
    item_text = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
    trial_bytes = items_bytes + len(item_text.encode("utf-8")) + (1 if items else 0)
    if trial_bytes > max_tokens or _contains_special_token(item_text, encoding):
        _bytes, trial_tokens = _measure_page([*items, item], None, True, encoding)
        if trial_tokens > max_tokens:
            return None
    if trial_bytes > max_bytes:
        return None
    return trial_bytes


def _page(
    code: str,
    *,
    items: list[dict[str, Any]] | None = None,
    next_cursor: str | None = None,
    complete: bool = False,
    encoding: str = DEFAULT_ENCODING,
    tokens: int = 0,
    bytes_: int = 0,
) -> dict[str, Any]:
    return {
        "code": code,
        "items": items or [],
        "next_cursor": next_cursor,
        "complete": complete,
        "tokens": tokens,
        "bytes": bytes_,
        "encoding": encoding,
    }


def _recheck_code(access: MemoryAccess, denied_code: str) -> str | None:
    """72-T01 recheck: `None` when `access` still holds, else the route's failure code
    (`denied_code` when the policy now denies it, `E_RESTART` when it changed)."""
    status = access.recheck()
    if status == "ok":
        return None
    return denied_code if status == "denied" else "E_RESTART"


def recall_page(
    store: TypedArtifactStore,
    *,
    subject: MemorySubject,
    query: str,
    session_allowlist: Iterable[str] | None = None,
    access: MemoryAccess | None = None,
    limit: int = DEFAULT_LIMIT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    encoding: str = DEFAULT_ENCODING,
    cursor: str | None = None,
    telemetry: TelemetryStore | None = None,
    request_id: str | None = None,
    event_id: str | None = None,
    invocation_id: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    opt_in: bool = False,
    cache_write: bool = False,
    now: float | None = None,
) -> dict[str, Any]:
    """MC02 §9.0 bounded recall: pages `store.search_candidates()` (prefiltered by
    subject/source/owner/archive/expiry) into a token/byte-bounded result.

    72-T01: every candidate goes through `evaluate_artifact_visibility` in ordinary mode;
    only rows usable as current become items. `access` (a resolved `MemoryAccess`) and
    `session_allowlist` (the legacy form) are mutually exclusive (`ValueError`); neither,
    or an empty allowlist, fails closed (an empty, `complete=True` page). The access is
    rechecked at entry and again after the page is measured, before telemetry: a denied
    recheck returns `E_PERMISSION`, a changed grant or revision `E_RESTART`, both with
    no items.

    MC04: passing `telemetry` plus `request_id`/`event_id` records this page's real token
    cost as a `"retrieval"` event (deduplicated by those IDs), gated on `opt_in`/`cache_write`
    exactly like `TelemetryStore.record_memory_event()`. Omitting `telemetry` (the default)
    persists nothing — existing callers see no behavior change.

    Scans up to `_SCAN_CAP` (512) candidates for *this call*; if the cap is hit before the
    page is full, returns `complete=False` and a `next_cursor` bound to `(subject, query,
    sources, store generation, ranking version)` — any change to that binding
    between calls fails the continuation closed with `"E_RESTART"` rather than silently
    paging over stale or rescoped data.
    """
    access = _route_access(store, access, session_allowlist)
    if access is None:
        return _page("OK", complete=True, encoding=encoding)
    failed = _recheck_code(access, "E_PERMISSION")
    if failed is not None:
        return _page(failed, encoding=encoding)
    allowed_sources = list(access.sources)
    moment = time.time() if now is None else now
    memo = SourceValidationMemo()

    # P69-07 subsection e: mint a real per-call identity when the caller doesn't supply
    # one (today's only caller, `tools/memory.py`, passes a content-derived `request_id`
    # instead) so two distinct calls sharing identical content never collide.
    real_invocation_id = invocation_id or str(uuid.uuid4())

    key = store.cursor_key()
    namespace = str(store.project_root)

    if cursor is None:
        scan_offset = 0
        generation = store.current_generation()
    else:
        decoded = _decode_cursor(key, cursor)
        if decoded is None:
            return _page("E_RESTART", encoding=encoding)
        expected_binding = (
            subject,
            query,
            allowed_sources,
            namespace,
            _RANKING_VERSION,
        )
        actual_binding = (
            decoded.get("subject"),
            decoded.get("query"),
            decoded.get("sources"),
            decoded.get("namespace"),
            decoded.get("ranking_version"),
        )
        if expected_binding != actual_binding:
            return _page("E_RESTART", encoding=encoding)
        generation = int(decoded.get("generation", -1))
        if generation != store.current_generation():
            return _page("E_RESTART", encoding=encoding)
        scan_offset = int(decoded.get("scan_offset", 0))

    floor_bytes, floor_tokens = _measure_page([], None, True, encoding)
    if floor_bytes > max_bytes or floor_tokens > max_tokens:
        return _page("E_BUDGET", encoding=encoding)

    items: list[dict[str, Any]] = []
    items_bytes = floor_bytes
    scanned = 0
    hit_cap = False
    exhausted = False
    budget_full = False

    while scanned < _SCAN_CAP and len(items) < limit and not budget_full:
        batch_limit = min(_BATCH_SIZE, _SCAN_CAP - scanned)
        batch = store.search_candidates(
            subject,
            query,
            source_allowlist=allowed_sources,
            scan_offset=scan_offset,
            scan_limit=batch_limit,
            owner_scope=access.owner_scope,
            now=moment,
        )
        if not batch:
            exhausted = True
            break
        for row in batch:
            scanned += 1
            decision = evaluate_artifact_visibility(
                store, row, access=access, now=moment, memo=memo
            )
            if not decision.usable_as_current:
                continue
            item = _candidate_to_item(
                row, store, access, decision, now=moment, memo=memo
            )
            if item is None:
                continue
            trial_bytes = _trial_page_bytes(
                items,
                items_bytes,
                item,
                max_bytes=max_bytes,
                max_tokens=max_tokens,
                encoding=encoding,
            )
            if trial_bytes is None:
                budget_full = True
                break
            items.append(item)
            items_bytes = trial_bytes
            if len(items) >= limit:
                break
        scan_offset += len(batch)
        if len(batch) < batch_limit:
            exhausted = True
        if scanned >= _SCAN_CAP:
            hit_cap = True
        if budget_full or len(items) >= limit or exhausted or hit_cap:
            break

    complete = not (hit_cap and not exhausted and len(items) < limit)
    # `hit_cap` only forces a continuation when neither the candidate set nor the page's own
    # limit/budget already finished it first (MC02.1: continue "until budget/limit is filled
    # or a 512-candidate scan cap is reached" — the cap is the fallback stop, not a race).
    next_cursor = None
    if not complete:
        next_cursor = _encode_cursor(
            key,
            {
                "subject": subject,
                "query": query,
                "sources": allowed_sources,
                "namespace": namespace,
                "ranking_version": _RANKING_VERSION,
                "generation": generation,
                "scan_offset": scan_offset,
            },
        )

    size_bytes, size_tokens = _measure_page(items, next_cursor, complete, encoding)
    failed = _recheck_code(access, "E_PERMISSION")
    if failed is not None:
        return _page(failed, encoding=encoding)
    _record_memory_event(
        telemetry,
        "retrieval",
        size_tokens,
        request_id=request_id,
        event_id=event_id,
        invocation_id=real_invocation_id,
        project_id=project_id,
        run_id=run_id,
        agent_id=agent_id,
        session_id=session_id,
        opt_in=opt_in,
        cache_write=cache_write,
    )
    return _page(
        "OK",
        items=items,
        next_cursor=next_cursor,
        complete=complete,
        encoding=encoding,
        tokens=size_tokens,
        bytes_=size_bytes,
    )


def _measure_expand(
    chunk: bytes, next_offset: int | None, complete: bool, encoding: str
) -> tuple[int, int]:
    payload = {
        "content_base64": base64.b64encode(chunk).decode("ascii"),
        "next_offset": next_offset,
        "complete": complete,
        "encoding": encoding,
    }
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return len(text.encode("utf-8")), _count_tokens(text, encoding)


def _expand(
    code: str,
    *,
    artifact_id: str,
    version: int | None,
    offset: int = 0,
    next_offset: int | None = None,
    complete: bool = False,
    content_base64: str | None = None,
    encoding: str = DEFAULT_ENCODING,
    tokens: int = 0,
    bytes_: int = 0,
) -> dict[str, Any]:
    return {
        "code": code,
        "id": artifact_id,
        "version": version,
        "offset": offset,
        "next_offset": next_offset,
        "complete": complete,
        "content_base64": content_base64,
        "tokens": tokens,
        "bytes": bytes_,
        "encoding": encoding,
    }


def expand_artifact(
    store: TypedArtifactStore,
    *,
    artifact_id: str,
    version: int,
    session_allowlist: Iterable[str] | None = None,
    access: MemoryAccess | None = None,
    mode: Literal["ordinary", "historical"] = "ordinary",
    now: float | None = None,
    offset: int = 0,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    encoding: str = DEFAULT_ENCODING,
    telemetry: TelemetryStore | None = None,
    request_id: str | None = None,
    event_id: str | None = None,
    invocation_id: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    opt_in: bool = False,
    cache_write: bool = False,
) -> dict[str, Any]:
    """MC02 §9.0 exact expansion: returns a base64-encoded byte slice of one stored artifact
    version, starting at `offset`. Concatenating `content_base64` across pages (following
    `next_offset` until `complete`) reconstructs the stored version's bytes exactly, even
    across a multi-byte UTF-8 character split mid-page.

    72-T01: visibility is decided first, through `evaluate_artifact_visibility` on the
    *current* row: a missing, denied, archived, expired, tampered or not-current artifact
    returns `"E_NOT_VISIBLE"` (identical bodies apart from the echoed id, so a caller
    can't distinguish "never existed" from "excluded"), whatever `version` was asked.
    Only then may a visible current row answer `"E_VERSION"` for a since-changed
    `version`. A version row whose `payload_hash` disagrees with its bytes is never
    expanded in ordinary mode.

    `mode="historical"` needs a historical-capable access; it may expand a superseded
    version (`version_superseded`), reports a version payload mismatch as
    `integrity_payload_mismatch`, and adds `"historical": True` and `"reason_codes"`.
    The access is rechecked at entry and after the slice is measured, before telemetry:
    denied is `E_NOT_VISIBLE`, changed is `E_RESTART`.

    MC04: passing `telemetry` plus `request_id`/`event_id` records a real successful
    expansion's token cost as an `"expansion"` event; omitted (the default), nothing persists.
    """
    # P69-07 subsection e: see `recall_page()`'s identical rationale.
    real_invocation_id = invocation_id or str(uuid.uuid4())
    requested_offset = offset

    def denied(code: str = "E_NOT_VISIBLE") -> dict[str, Any]:
        return _expand(
            code,
            artifact_id=artifact_id,
            version=None,
            offset=requested_offset,
            encoding=encoding,
        )

    access = _route_access(store, access, session_allowlist)
    if access is None:
        return denied()
    failed = _recheck_code(access, "E_NOT_VISIBLE")
    if failed is not None:
        return denied(failed)
    historical = mode == "historical"
    row = store.get_current_row(artifact_id)
    if row is None:
        return denied()
    decision = evaluate_artifact_visibility(
        store,
        row,
        access=access,
        mode="historical" if historical else "ordinary",
        now=now,
    )
    if not decision.visible or not (historical or decision.usable_as_current):
        return denied()
    reasons = set(decision.reason_codes)
    current_version = row["artifact_version"]
    if version != current_version:
        if not historical:
            return _expand(
                "E_VERSION",
                artifact_id=artifact_id,
                version=current_version,
                offset=offset,
                encoding=encoding,
            )
        reasons.add("version_superseded")
    payload = store.get_version_payload(artifact_id, version)
    if payload is None:
        return denied()
    stored_text, stored_digest = payload
    if stored_digest is not None and payload_digest(stored_text) != stored_digest:
        if not historical:
            return denied()
        reasons.add("integrity_payload_mismatch")

    stored_bytes = stored_text.encode("utf-8")
    total = len(stored_bytes)
    offset = max(0, min(offset, total))

    floor_bytes, floor_tokens = _measure_expand(b"", None, True, encoding)
    if floor_bytes > max_bytes or floor_tokens > max_tokens:
        return _expand(
            "E_BUDGET",
            artifact_id=artifact_id,
            version=version,
            offset=offset,
            encoding=encoding,
        )

    remaining = stored_bytes[offset:]
    chunk = b""
    next_offset: int | None = None
    complete = True
    size = (floor_bytes, floor_tokens)
    chunk_len = len(remaining)
    while chunk_len > 0:
        chunk = remaining[:chunk_len]
        next_offset = offset + chunk_len if offset + chunk_len < total else None
        complete = next_offset is None
        size_bytes, size_tokens = _measure_expand(
            chunk, next_offset, complete, encoding
        )
        if size_bytes <= max_bytes and size_tokens <= max_tokens:
            size = (size_bytes, size_tokens)
            break
        chunk_len -= max(1, chunk_len // 4)
    else:
        if remaining:
            # Shrank the chunk all the way to nothing without ever fitting the envelope
            # inside both caps: the budget itself is too small to return any content.
            return _expand(
                "E_BUDGET",
                artifact_id=artifact_id,
                version=version,
                offset=offset,
                encoding=encoding,
            )

    failed = _recheck_code(access, "E_NOT_VISIBLE")
    if failed is not None:
        return denied(failed)
    _record_memory_event(
        telemetry,
        "expansion",
        size[1],
        request_id=request_id,
        event_id=event_id,
        invocation_id=real_invocation_id,
        project_id=project_id,
        run_id=run_id,
        agent_id=agent_id,
        session_id=session_id,
        opt_in=opt_in,
        cache_write=cache_write,
    )
    result = _expand(
        "OK",
        artifact_id=artifact_id,
        version=version,
        offset=offset,
        next_offset=next_offset,
        complete=complete,
        content_base64=base64.b64encode(chunk).decode("ascii"),
        encoding=encoding,
        tokens=size[1],
        bytes_=size[0],
    )
    if historical:
        result["historical"] = True
        result["reason_codes"] = sorted(reasons)
    return result


def embedding_text(content: dict[str, Any]) -> str:
    """MC12 §6.7: the exact, deterministic text embedded (and hashed for the vector cache
    key) for one artifact's `content` -- sorted-key JSON so the same content always produces
    the same text regardless of dict insertion order."""
    return json.dumps(content, ensure_ascii=False, sort_keys=True)


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def hybrid_candidates(
    store: TypedArtifactStore,
    *,
    subject: MemorySubject,
    query: str,
    session_allowlist: Iterable[str] | None = None,
    access: MemoryAccess | None = None,
    embed_config: EmbeddingConfig | None,
    cache_write: bool = False,
    embed_fn: Callable[
        [EmbeddingConfig, Sequence[str]], list[list[float]]
    ] = embed_chunks,
    scan_limit: int = _VECTOR_SCAN_CAP,
    now: float | None = None,
    memo: SourceValidationMemo | None = None,
) -> dict[str, Any]:
    """MC12 §6.7 hybrid ranking: fuses MC02's lexical `search_candidates()` ranking with
    cosine similarity over authorized scoped candidates (`TypedArtifactStore.scope_artifacts()`
    -- never lexical-matched, so a candidate with zero shared terms with `query` is still
    eligible) via deterministic reciprocal-rank fusion: `1/(60+lexical_rank) +
    1/(60+vector_rank)`, an absent rank contributing zero, ID-ascending tie-break.

    Returns `{"available": False, "reason": ...}` when no engine is configured or it is
    unreachable/invalid -- callers must fall back to a plainly-labelled lexical result, never
    report that as hybrid success. 72-T01: every candidate goes through
    `evaluate_artifact_visibility` (ordinary mode) before any content is embedded, so an
    excluded row never reaches the embedding endpoint. Without `cache_write`, a freshly
    computed vector is used for this call's ranking only and is never persisted
    (`TypedArtifactStore.put_embedding()` is only ever called when `cache_write` is true).

    An `"available": True` result also carries `"candidates_truncated"`: `True` when either
    the lexical or vector-scope scan returned a full `scan_limit` (512) batch, meaning
    unseen candidates beyond the cap were never ranked (§6.7 "report candidate truncation").
    """
    access = _route_access(store, access, session_allowlist)
    if access is None:
        return {"available": True, "rows": [], "candidates_truncated": False}
    if embed_config is None:
        return {"available": False, "reason": "no embedding engine configured"}
    allowed_sources = list(access.sources)
    moment = time.time() if now is None else now
    memo = memo or SourceValidationMemo()

    lexical_rows = store.search_candidates(
        subject,
        query,
        source_allowlist=allowed_sources,
        scan_limit=scan_limit,
        owner_scope=access.owner_scope,
        now=moment,
    )
    scoped_rows = store.scope_artifacts(
        subject,
        source_allowlist=allowed_sources,
        scan_limit=scan_limit,
        owner_scope=access.owner_scope,
        now=moment,
    )
    # §6.7 "bound vector candidates to 512 and report candidate truncation": either scan
    # returning a full `scan_limit` batch means unseen rows may exist beyond the cap, mirroring
    # `recall_page()`'s own `scanned >= _SCAN_CAP` cap-hit detection.
    candidates_truncated = (
        len(lexical_rows) >= scan_limit or len(scoped_rows) >= scan_limit
    )
    rows_by_id: dict[str, Any] = {}
    for row in [*scoped_rows, *lexical_rows]:
        if row["id"] in rows_by_id:
            continue
        decision = evaluate_artifact_visibility(
            store, row, access=access, now=moment, memo=memo
        )
        if decision.usable_as_current:
            rows_by_id[row["id"]] = row
    lexical_order = [row["id"] for row in lexical_rows if row["id"] in rows_by_id]
    if not rows_by_id:
        return {
            "available": True,
            "rows": [],
            "candidates_truncated": candidates_truncated,
        }

    texts: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for artifact_id, row in rows_by_id.items():
        try:
            content = json.loads(row["content"])
        except (TypeError, ValueError, RecursionError):
            continue
        text = embedding_text(content)
        texts[artifact_id] = text
        hashes[artifact_id] = hashlib.sha256(text.encode("utf-8")).hexdigest()

    vectors: dict[str, list[float]] = {}
    missing: list[str] = []
    for artifact_id in texts:
        row = rows_by_id[artifact_id]
        cached = store.get_embedding(
            artifact_id=artifact_id,
            artifact_version=row["artifact_version"],
            content_hash=hashes[artifact_id],
            model_digest=embed_config.model_digest,
            chunking_version=embed_config.chunking_version,
        )
        if cached is not None:
            vectors[artifact_id] = cached
        else:
            missing.append(artifact_id)

    try:
        if missing:
            fresh = embed_fn(embed_config, [texts[i] for i in missing])
            for artifact_id, vector in zip(missing, fresh, strict=True):
                vectors[artifact_id] = vector
                if cache_write:
                    row = rows_by_id[artifact_id]
                    store.put_embedding(
                        artifact_id=artifact_id,
                        artifact_version=row["artifact_version"],
                        content_hash=hashes[artifact_id],
                        model_digest=embed_config.model_digest,
                        chunking_version=embed_config.chunking_version,
                        vector=vector,
                    )
        (query_vector,) = embed_fn(embed_config, [query])
    except EmbeddingEngineUnavailable as exc:
        return {"available": False, "reason": str(exc)}
    except EmbeddingResponseError as exc:
        return {"available": False, "reason": str(exc)}

    vector_order = sorted(
        vectors, key=lambda aid: (-_cosine(query_vector, vectors[aid]), aid)
    )

    lexical_rank = {aid: i + 1 for i, aid in enumerate(lexical_order)}
    vector_rank = {aid: i + 1 for i, aid in enumerate(vector_order)}
    all_ids = set(lexical_order) | set(vector_order)

    def rrf_score(aid: str) -> float:
        score = 0.0
        if aid in lexical_rank:
            score += 1.0 / (_RRF_K + lexical_rank[aid])
        if aid in vector_rank:
            score += 1.0 / (_RRF_K + vector_rank[aid])
        return score

    ranked_ids = sorted(all_ids, key=lambda aid: (-rrf_score(aid), aid))
    return {
        "available": True,
        "rows": [rows_by_id[aid] for aid in ranked_ids],
        "candidates_truncated": candidates_truncated,
    }


def hybrid_page(
    store: TypedArtifactStore,
    *,
    subject: MemorySubject,
    query: str,
    session_allowlist: Iterable[str] | None = None,
    access: MemoryAccess | None = None,
    embed_config: EmbeddingConfig | None,
    limit: int = DEFAULT_LIMIT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    encoding: str = DEFAULT_ENCODING,
    cache_write: bool = False,
    embed_fn: Callable[
        [EmbeddingConfig, Sequence[str]], list[list[float]]
    ] = embed_chunks,
    telemetry: TelemetryStore | None = None,
    request_id: str | None = None,
    event_id: str | None = None,
    invocation_id: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    opt_in: bool = False,
    now: float | None = None,
) -> dict[str, Any]:
    """MC12 §6.7 hybrid retrieval page: `hybrid_candidates()`'s RRF-fused ranking, applying
    the same compact-item budget rules `recall_page()` uses. No cursor/continuation in this
    cut -- the candidate pool is already bounded to `_VECTOR_SCAN_CAP` (512); `data.
    candidates_truncated` reports when that bound actually clipped the scan (§6.7 "report
    candidate truncation") instead of silently treating the capped pool as exhaustive.
    # ponytail: no hybrid pagination; add a cursor if a real workload needs paging past one
    # page of a 512-candidate pool.

    72-T01: the same access rules as `recall_page()` (mutually exclusive `access` and
    `session_allowlist`, entry and pre-telemetry rechecks); only rows usable as current
    are embedded or returned.

    Falls back to a plainly-labelled lexical page (`code: "E_EMBEDDING_UNAVAILABLE"`,
    `retrieval: "lexical"`, `embedding_status: "skipped"`, plus `hybrid_unavailable_reason`)
    when no engine is configured or it is unreachable/invalid -- never reports that as hybrid
    success (§9.0 fixed contract).
    """
    access = _route_access(store, access, session_allowlist)
    if access is None:
        page = _page("OK", complete=True, encoding=encoding)
        page["retrieval"] = "hybrid"
        page["candidates_truncated"] = False
        return page
    failed = _recheck_code(access, "E_PERMISSION")
    if failed is not None:
        return _page(failed, encoding=encoding)
    moment = time.time() if now is None else now
    memo = SourceValidationMemo()

    # P69-07 subsection e: minted once, forwarded to the lexical fallback below so a
    # fallback call never mints a second, different identity for this one logical call.
    real_invocation_id = invocation_id or str(uuid.uuid4())

    fused = hybrid_candidates(
        store,
        subject=subject,
        query=query,
        access=access,
        embed_config=embed_config,
        cache_write=cache_write,
        embed_fn=embed_fn,
        now=moment,
        memo=memo,
    )
    if not fused["available"]:
        fallback = recall_page(
            store,
            subject=subject,
            query=query,
            access=access,
            limit=limit,
            max_tokens=max_tokens,
            max_bytes=max_bytes,
            encoding=encoding,
            telemetry=telemetry,
            request_id=request_id,
            event_id=event_id,
            invocation_id=real_invocation_id,
            project_id=project_id,
            run_id=run_id,
            agent_id=agent_id,
            session_id=session_id,
            opt_in=opt_in,
            cache_write=cache_write,
            now=moment,
        )
        if fallback["code"] in ("E_PERMISSION", "E_RESTART"):
            return fallback
        fallback["code"] = "E_EMBEDDING_UNAVAILABLE"
        fallback["retrieval"] = "lexical"
        fallback["embedding_status"] = "skipped"
        fallback["hybrid_unavailable_reason"] = fused["reason"]
        return fallback

    items: list[dict[str, Any]] = []
    items_bytes, _tokens = _measure_page([], None, True, encoding)
    for row in fused["rows"]:
        decision = evaluate_artifact_visibility(
            store, row, access=access, now=moment, memo=memo
        )
        if not decision.usable_as_current:
            continue
        item = _candidate_to_item(row, store, access, decision, now=moment, memo=memo)
        if item is None:
            continue
        trial_bytes = _trial_page_bytes(
            items,
            items_bytes,
            item,
            max_bytes=max_bytes,
            max_tokens=max_tokens,
            encoding=encoding,
        )
        if trial_bytes is None:
            break
        items.append(item)
        items_bytes = trial_bytes
        if len(items) >= limit:
            break

    size_bytes, size_tokens = _measure_page(items, None, True, encoding)
    failed = _recheck_code(access, "E_PERMISSION")
    if failed is not None:
        return _page(failed, encoding=encoding)
    _record_memory_event(
        telemetry,
        "retrieval",
        size_tokens,
        request_id=request_id,
        event_id=event_id,
        invocation_id=real_invocation_id,
        project_id=project_id,
        run_id=run_id,
        agent_id=agent_id,
        session_id=session_id,
        opt_in=opt_in,
        cache_write=cache_write,
    )
    page = _page(
        "OK",
        items=items,
        next_cursor=None,
        complete=True,
        encoding=encoding,
        tokens=size_tokens,
        bytes_=size_bytes,
    )
    page["retrieval"] = "hybrid"
    page["candidates_truncated"] = fused["candidates_truncated"]
    return page
