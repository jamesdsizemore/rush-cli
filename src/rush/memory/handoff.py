"""MC11: bounded memory-delta rehydration through a restricted receiver session.

Wholly new code (Phase 63 §9 MC11). A "handoff session" is a short-lived, capability-gated
window over an immutable, explicit set of authorized artifact IDs (`granted_ids`) and source
allowlist (`session_allowlist`) -- never a general-purpose remote query surface. Reuses
`TypedArtifactStore`'s existing `memory_artifact_versions`/`memory_changes` audit trail for
"what changed" and `rush.memory.intent`/`store.find_any_behavior_success` for read-only
Guest-intent/last-success references (never authority) carried alongside the delta.

Delivery acknowledgement (a transport turn completing successfully) is a wholly separate
concept from a memory read-back acknowledgement here: only `acknowledge_readback()`, given the
exact SHA-256 digest of a version's stored bytes, ever advances a session's per-artifact
cursor (`memory_handoff_receipts`). `receive_handoff()` is a pure read -- it never writes --
so paging and replay are trivially atomic.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rush.memory import intent as intent_module
from rush.memory.store import TypedArtifactStore, VersionConflictError

SESSION_TTL_SECONDS = 900.0
DEFAULT_PAGE_SIZE = 50


class HandoffError(Exception):
    """Raised by every handoff entry point on denial. `code` mirrors §9.0's status/code
    pairs (`E_INPUT`/`E_PERMISSION`/`E_NOT_VISIBLE`/`E_VERSION`) so callers can map it onto
    a `ToolResult` envelope without re-deriving the reason."""

    def __init__(self, message: str, *, code: str = "E_PERMISSION") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class HandoffSession:
    """A validated, unexpired handoff session -- never constructed directly by a caller;
    only `load_session()`/`prepare_handoff()` produce one, after checking the capability."""

    session_id: str
    root: str
    audience: str
    granted_ids: tuple[str, ...]
    session_allowlist: tuple[str, ...]
    constraints: dict[str, Any]
    created_at: float
    expires_at: float


def _hash_capability(raw_capability: str) -> str:
    return hashlib.sha256(raw_capability.encode("utf-8")).hexdigest()


def prepare_handoff(
    store: TypedArtifactStore,
    *,
    root: Path,
    audience: str,
    granted_ids: Sequence[str],
    session_allowlist: Sequence[str],
    constraints: Mapping[str, Any] | None = None,
    intent_behavior_ids: Sequence[str] = (),
    namespace: str = "",
    budgets: Mapping[str, Any] | None = None,
    now: float | None = None,
) -> tuple[HandoffSession, str, dict[str, Any]]:
    """Create a brand-new bounded handoff session bound to `root`/`audience`/`granted_ids`
    (versions authorized are always the artifacts' *current* version, re-checked fresh on
    every `receive_handoff()` call, never frozen at prepare time) /`session_allowlist`/
    `budgets`. Returns `(session, raw_capability, initial_delta)` -- `raw_capability` is
    returned exactly once; only its SHA-256 hash is ever persisted. Widening scope always
    requires calling this again for a fresh session_id (`test_scope_change_requires_new_snapshot`).
    """
    if not granted_ids:
        raise HandoffError(
            "prepare_handoff requires at least one granted artifact id.", code="E_INPUT"
        )
    if not session_allowlist:
        raise HandoffError(
            "prepare_handoff requires a non-empty session_allowlist.", code="E_INPUT"
        )
    ts = now if now is not None else time.time()
    session_id = secrets.token_hex(16)
    raw_capability = secrets.token_urlsafe(32)

    constraints_payload: dict[str, Any] = dict(constraints or {})
    constraints_payload["budgets"] = dict(budgets or {})
    if intent_behavior_ids:
        constraints_payload["intent_refs"] = intent_module.intent_evidence(
            project_root=root,
            behavior_ids=intent_behavior_ids,
            session_allowlist=session_allowlist,
        )
        last_success_refs: list[dict[str, Any]] = []
        for behavior_id in intent_behavior_ids:
            pointer = store.find_any_behavior_success(
                namespace=namespace, behavior_id=behavior_id
            )
            if pointer is not None:
                last_success_refs.append(
                    {
                        "behavior_id": behavior_id,
                        "artifact_id": pointer[0],
                        "artifact_version": pointer[1],
                    }
                )
        constraints_payload["last_success_refs"] = last_success_refs

    store.create_handoff_session(
        session_id=session_id,
        root=str(root),
        audience=audience,
        capability_hash=_hash_capability(raw_capability),
        granted_ids=tuple(granted_ids),
        session_allowlist=tuple(session_allowlist),
        constraints=constraints_payload,
        created_at=ts,
        expires_at=ts + SESSION_TTL_SECONDS,
    )
    delta = receive_handoff(
        store, session_id=session_id, capability=raw_capability, now=ts
    )
    return (
        HandoffSession(
            session_id=session_id,
            root=str(root),
            audience=audience,
            granted_ids=tuple(granted_ids),
            session_allowlist=tuple(session_allowlist),
            constraints=constraints_payload,
            created_at=ts,
            expires_at=ts + SESSION_TTL_SECONDS,
        ),
        raw_capability,
        delta,
    )


def load_session(
    store: TypedArtifactStore,
    session_id: str,
    capability: str,
    *,
    now: float | None = None,
) -> HandoffSession:
    """Validate `session_id`/`capability`/expiry -- the single choke point every handoff
    operation (`receive_handoff`, `acknowledge_readback`, and the restricted-receiver bridge's
    `expand`/`related`/`resume` delegation) must pass through first. Denies identically
    (`E_PERMISSION`) for an unknown session, a wrong capability, and an expired one, so a
    caller can never distinguish "never existed" from "revoked" from "timed out" -- and every
    operation is denied the same way (`test_expired_session_capability_denies_every_operation`).
    """
    row = store.get_handoff_session(session_id)
    if row is None:
        raise HandoffError("Unknown or revoked handoff session.", code="E_PERMISSION")
    if not hmac.compare_digest(row["capability_hash"], _hash_capability(capability)):
        raise HandoffError("Invalid handoff capability.", code="E_PERMISSION")
    ts = now if now is not None else time.time()
    if ts >= row["expires_at"]:
        raise HandoffError("Handoff session expired.", code="E_PERMISSION")
    return HandoffSession(
        session_id=row["session_id"],
        root=row["root"],
        audience=row["audience"],
        granted_ids=tuple(row["granted_ids"]),
        session_allowlist=tuple(row["session_allowlist"]),
        constraints=row["constraints"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )


def receive_handoff(
    store: TypedArtifactStore,
    *,
    session_id: str,
    capability: str,
    cursor: str | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    now: float | None = None,
) -> dict[str, Any]:
    """Read-only bounded delta: exactly the `granted_ids` whose *current* version exceeds
    this session's already-acknowledged version, ordered by artifact ID for a deterministic,
    replayable page. Carries no content -- only `id`/`version`/`trust_tier`/`source` -- so a
    receiver must call `expand` for the exact bytes before it can prove a read-back. Never
    writes, so calling this twice (a replay, or an interrupted page) is trivially atomic and
    idempotent (`test_partial_page_and_replay_are_atomic`)."""
    session = load_session(store, session_id, capability, now=now)
    receipts = store.get_handoff_receipts(session_id)
    candidate_ids = sorted(session.granted_ids)
    if cursor is not None:
        candidate_ids = [i for i in candidate_ids if i > cursor]
    page_ids = candidate_ids[:page_size]
    next_cursor = page_ids[-1] if len(candidate_ids) > page_size else None

    changes: list[dict[str, Any]] = []
    for artifact_id in page_ids:
        current = store.get_current(artifact_id)
        if current is None:
            continue
        acknowledged = receipts.get(artifact_id, 0)
        if current.artifact_version <= acknowledged:
            continue
        changes.append(
            {
                "id": artifact_id,
                "version": current.artifact_version,
                "trust_tier": current.trust_tier,
                "source": current.source,
            }
        )
    return {
        "session_id": session_id,
        "audience": session.audience,
        "changes": changes,
        "constraints": session.constraints,
        "cursor": next_cursor,
    }


def acknowledge_readback(
    store: TypedArtifactStore,
    *,
    session_id: str,
    capability: str,
    readbacks: Sequence[Mapping[str, Any]],
    now: float | None = None,
) -> dict[str, int]:
    """Advance this session's per-artifact cursor -- the *only* thing that ever does. Every
    entry must name an artifact in `granted_ids` and the exact SHA-256 digest of that exact
    version's stored bytes; one bad entry fails the whole call atomically before any receipt
    is written (`TypedArtifactStore.acknowledge_handoff`). Merely completing a transport
    delivery turn never calls this -- `test_delivery_ack_does_not_advance_cursor`."""
    session = load_session(store, session_id, capability, now=now)
    updates: list[tuple[str, int, str]] = []
    for entry in readbacks:
        artifact_id = entry.get("id")
        version = entry.get("version")
        digest = entry.get("digest")
        if (
            not isinstance(artifact_id, str)
            or not isinstance(version, int)
            or isinstance(version, bool)
            or not isinstance(digest, str)
        ):
            raise HandoffError(
                "Each readback requires id (str), version (int) and digest (str).",
                code="E_INPUT",
            )
        if artifact_id not in session.granted_ids:
            raise HandoffError(
                f"Artifact {artifact_id!r} was never granted to this session.",
                code="E_PERMISSION",
            )
        updates.append((artifact_id, version, digest))
    try:
        return store.acknowledge_handoff(session_id, updates)
    except VersionConflictError as exc:
        raise HandoffError(str(exc), code="E_VERSION") from exc
