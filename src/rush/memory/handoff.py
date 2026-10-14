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
import sqlite3
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rush.memory import intent as intent_module
from rush.memory.store import (
    TypedArtifactStore,
    VersionConflictError,
    sqlite_integer_in_range,
)

SESSION_TTL_SECONDS = 900.0
DEFAULT_PAGE_SIZE = 50


class HandoffError(Exception):
    """Raised by every handoff entry point on denial. `code` mirrors §9.0's status/code
    pairs (`E_INPUT`/`E_PERMISSION`/`E_NOT_VISIBLE`/`E_VERSION`) so callers can map it onto
    a `ToolResult` envelope without re-deriving the reason. 72-T01: a sender-binding
    denial also carries `reason` (and, for a pre-72 session, `next_action`)."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "E_PERMISSION",
        reason: str | None = None,
        next_action: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.reason = reason
        self.next_action = next_action

    def data(self) -> dict[str, Any]:
        """The envelope `data` for this denial."""
        body: dict[str, Any] = {"message": str(self)}
        if self.reason is not None:
            body["reason"] = self.reason
        if self.next_action is not None:
            body["next_action"] = self.next_action
        return body


# D22: one constant denial for an unknown, revoked or wrong-capability session and
# for a missing or unreadable store; expiry is revealed only after the capability
# matches.
_SESSION_DENIAL = "Unknown or revoked handoff session."
RE_PREPARE = "re-prepare handoff"


def _session_denied() -> HandoffError:
    return HandoffError(_SESSION_DENIAL, code="E_PERMISSION")


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
    sender: dict[str, Any] | None = None
    # 72-T05: the sender's task context; delivery decides task-bound rows under it.
    sender_task_id: str | None = None


def _session_from_row(row: Mapping[str, Any]) -> HandoffSession:
    return HandoffSession(
        session_id=row["session_id"],
        root=row["root"],
        audience=row["audience"],
        granted_ids=tuple(row["granted_ids"]),
        session_allowlist=tuple(row["session_allowlist"]),
        constraints=row["constraints"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        sender={
            key: row.get(key)
            for key in (
                "sender_columns",
                "sender_grant_id",
                "sender_owner_kind",
                "sender_owner_id",
                "sender_project_id",
                "sender_worktree_id",
                "sender_policy_revision",
            )
        },
        sender_task_id=row.get("sender_task_id"),
    )


def sender_binding(access: Any) -> dict[str, Any] | None:
    """D21: the sender columns a policy-mode prepare persists (`None` in legacy)."""
    if access is None or getattr(access, "kind", None) != "policy":
        return None
    owner = access.owner_scope
    return {
        "sender_grant_id": access.grant_id,
        "sender_owner_kind": owner.kind if owner is not None else None,
        "sender_owner_id": owner.id if owner is not None else None,
        "sender_project_id": access.project_id,
        "sender_worktree_id": access.worktree_id,
        "sender_policy_revision": access.policy_revision,
    }


def delivery_access(store: TypedArtifactStore, session: HandoffSession) -> Any:
    """D21 delivery authority: `legacy` mode delivers under the session's own
    allowlist; `policy` mode re-resolves the sender's grant (`expand`) and requires
    the same grant, project and worktree (a revision-only change still delivers);
    `unavailable` denies. Raises `HandoffError` with the denial `reason`."""
    from rush.memory.retrieval import MemoryAccess, memory_policy_decision
    from rush.memory.store import OwnerScope

    root = store.project_root
    mode, reason = memory_policy_decision(root)
    if mode == "unavailable":
        raise HandoffError(
            f"Handoff delivery denied: {reason}.", reason=reason or "policy_invalid"
        )
    if mode == "legacy":
        return MemoryAccess.legacy(
            root,
            session.session_allowlist,
            operation="receive",
            task_id=session.sender_task_id,
        )
    sender = session.sender or {}
    grant_id = sender.get("sender_grant_id")
    kind, owner_id = sender.get("sender_owner_kind"), sender.get("sender_owner_id")
    if grant_id is None or not kind or not owner_id:
        raise HandoffError(
            "Handoff session predates sender binding; prepare a new handoff.",
            reason="sender_unbound",
            next_action=RE_PREPARE,
        )
    try:
        owner = OwnerScope(kind, owner_id)
    except ValueError:
        raise HandoffError(
            "Handoff session sender is invalid; prepare a new handoff.",
            reason="sender_unbound",
            next_action=RE_PREPARE,
        ) from None
    access, why = MemoryAccess.resolve_with_reason(
        root,
        operation="receive",
        owner_scope=owner,
        requested_sources=list(session.session_allowlist),
        task_id=session.sender_task_id,
    )
    if access is None:
        raise HandoffError(f"Handoff delivery denied: {why}.", reason=why)
    if (
        access.grant_id != grant_id
        or access.project_id != sender.get("sender_project_id")
        or access.worktree_id != sender.get("sender_worktree_id")
    ):
        raise HandoffError(
            "Handoff delivery denied: grant_changed.", reason="grant_changed"
        )
    return access


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
    receipt_operation_id: str | None = None,
    sender: Any = None,
    commit_check: Any = None,
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
    # 72-T05: the preparing access's task context (none without an access).
    sender_task_id = getattr(sender, "task_id", None)
    session_id = secrets.token_hex(16)
    raw_capability = secrets.token_urlsafe(32)

    constraints_payload: dict[str, Any] = dict(constraints or {})
    constraints_payload["budgets"] = dict(budgets or {})
    if intent_behavior_ids:
        # 72-T01 D21: a policy sender's intent refs are read under its own access.
        constraints_payload["intent_refs"] = (
            intent_module.intent_records_under(root, intent_behavior_ids, sender)
            if sender is not None
            else intent_module.intent_evidence(
                project_root=root,
                behavior_ids=intent_behavior_ids,
                session_allowlist=session_allowlist,
            )
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
        receipt_operation_id=receipt_operation_id,
        sender=sender_binding(sender),
        commit_check=commit_check,
        sender_task_id=sender_task_id,
    )
    # The initial delta is computed under the preparing sender's own access (an
    # internal caller with none reads under the session's allowlist); every later
    # delivery re-resolves the sender binding (`delivery_access`).
    from rush.memory.retrieval import MemoryAccess

    session_row = store.get_handoff_session(session_id)
    assert session_row is not None
    delta = _bounded_session_delta(
        store,
        _session_from_row(session_row),
        session_id=session_id,
        cursor=None,
        page_size=DEFAULT_PAGE_SIZE,
        access=sender
        if sender is not None
        else MemoryAccess.legacy(store.project_root, session_allowlist),
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
            sender=sender_binding(sender),
            sender_task_id=sender_task_id,
        ),
        raw_capability,
        delta,
    )


def load_session(
    store: TypedArtifactStore | None,
    session_id: str,
    capability: str,
    *,
    now: float | None = None,
) -> HandoffSession:
    """Validate `session_id`/`capability`/expiry -- the single choke point every handoff
    operation (`receive_handoff`, `acknowledge_readback`, and the restricted-receiver bridge's
    `expand`/`related`/`resume` delegation) must pass through first. 72-T01 D22: an
    unknown, revoked or wrong-capability session, and a missing (`store=None`) or
    unreadable store, all get the identical constant denial; expiry is reported only
    after the capability matches. `store` may be a read-only view.
    """
    if store is None:
        raise _session_denied()
    try:
        row = store.get_handoff_session(session_id)
    except (sqlite3.DatabaseError, KeyError, TypeError, ValueError):
        raise _session_denied() from None
    if row is None or row.get("revoked_at") is not None:
        raise _session_denied()
    if not isinstance(capability, str) or not hmac.compare_digest(
        str(row["capability_hash"]), _hash_capability(capability)
    ):
        raise _session_denied()
    ts = now if now is not None else time.time()
    if ts >= row["expires_at"]:
        raise HandoffError("Handoff session expired.", code="E_PERMISSION")
    return _session_from_row(row)


def _usable_ids(store: TypedArtifactStore, ids: Sequence[str], access: Any) -> set[str]:
    """D23: the selected ids whose current row the shared decision shows and
    deems usable as current under the delivery access."""
    from rush.memory.retrieval import SourceValidationMemo, evaluate_artifact_visibility
    from rush.memory.store import binding_verifier

    memo = SourceValidationMemo()
    verifier = binding_verifier(store)
    usable: set[str] = set()
    for artifact_id in ids:
        row = store.get_current_row(artifact_id)
        if row is None:
            continue
        decision = evaluate_artifact_visibility(
            store, row, access=access, memo=memo, verifier=verifier
        )
        if decision.visible and decision.usable_as_current:
            usable.add(artifact_id)
    return usable


def _selected_constraints(
    constraints: Mapping[str, Any], usable: set[str]
) -> dict[str, Any]:
    """D23: constraint refs survive only when they name a selected, usable id."""
    kept = dict(constraints)
    for key, field in (("intent_refs", "id"), ("last_success_refs", "artifact_id")):
        refs = kept.get(key)
        if isinstance(refs, list):
            kept[key] = [
                ref
                for ref in refs
                if isinstance(ref, Mapping) and ref.get(field) in usable
            ]
    return kept


def _bounded_session_delta(
    store: TypedArtifactStore,
    session: HandoffSession,
    *,
    session_id: str,
    cursor: str | None,
    page_size: int,
    access: Any,
) -> dict[str, Any]:
    """Shared delta computation behind `receive_handoff` (public, capability-
    checked) and `recover_session_delta_without_capability` (S05 bullet 2,
    internal dead-owner recovery only) -- identical bounded, read-only
    result; only how the caller is authorized to reach it differs. 72-T01 D23:
    hidden (not visible or not usable) selected ids are dropped before the page
    boundary, so no cursor, page, count or constraint ever names one."""
    receipts = store.get_handoff_receipts(session_id)
    usable = _usable_ids(store, sorted(set(session.granted_ids)), access)
    candidate_ids = sorted(usable)
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
        "constraints": _selected_constraints(session.constraints, usable),
        "cursor": next_cursor,
    }


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
    access = delivery_access(store, session)
    return _bounded_session_delta(
        store,
        session,
        session_id=session_id,
        cursor=cursor,
        page_size=page_size,
        access=access,
    )


def recover_session_delta_without_capability(
    store: TypedArtifactStore,
    session_id: str,
    *,
    expected_root: str,
    expected_audience: str,
    expected_session_allowlist: Sequence[str],
    now: float | None = None,
) -> dict[str, Any] | None:
    """S05 bullet 2: the one internal path allowed to read a handoff
    session's bounded delta without its raw capability -- a crashed
    `prepare` loses the in-memory-only capability forever, so normal
    `receive_handoff` can never be called again for that session. NOT an
    HTTP/CLI/MCP entry point; callable only from a process's own dead-owner
    reconciliation path (`rush.workflows.project_run.recover_prepared_handoff`,
    itself only reachable from inside a won `claim_dead_owner` claim), which
    has already independently verified operation/artifact/session receipts,
    project, and source run/attempt before calling this. This function
    still independently re-verifies session-row state itself (never trusts
    the caller alone): existence, not revoked, not expired, and that
    `root`/`audience`/`session_allowlist` match the caller's own recovered
    expectations -- returns `None` (recovery-required, never a fabricated
    or partial result) if the session row disagrees on any of them, rather
    than calling `load_session` with an empty or invented capability."""
    row = store.get_handoff_session(session_id)
    if row is None:
        return None
    if row.get("revoked_at") is not None:
        return None
    ts = now if now is not None else time.time()
    if ts >= row["expires_at"]:
        return None
    if row["root"] != expected_root or row["audience"] != expected_audience:
        return None
    if sorted(row["session_allowlist"]) != sorted(expected_session_allowlist):
        return None
    session = _session_from_row(row)
    try:
        access = delivery_access(store, session)
    except HandoffError:
        return None  # the sender's authority is gone: recovery delivers nothing
    return _bounded_session_delta(
        store,
        session,
        session_id=session_id,
        cursor=None,
        page_size=DEFAULT_PAGE_SIZE,
        access=access,
    )


def validate_readbacks(
    readbacks: Any,
) -> list[tuple[str, int, str]]:
    """Strict `ack` validation (before any read or effect): every entry is an
    object with `id` (str), `version` (storable int) and `digest` (str)."""
    if not isinstance(readbacks, (list, tuple)):
        raise HandoffError("ack must be a list of readbacks.", code="E_INPUT")
    updates: list[tuple[str, int, str]] = []
    for entry in readbacks:
        if not isinstance(entry, Mapping):
            raise HandoffError(
                "Each readback must be an object with id, version and digest.",
                code="E_INPUT",
            )
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
        if not sqlite_integer_in_range(version):
            raise HandoffError(
                f"Readback version {version} is outside the storable integer range.",
                code="E_INPUT",
            )
        updates.append((artifact_id, version, digest))
    return updates


def acknowledge_readback(
    store: TypedArtifactStore | Callable[[], TypedArtifactStore],
    *,
    session_id: str,
    capability: str,
    readbacks: Sequence[Mapping[str, Any]],
    now: float | None = None,
    view: TypedArtifactStore | None = None,
) -> dict[str, int]:
    """Advance this session's per-artifact cursor -- the *only* thing that ever does. Every
    entry must name an artifact in `granted_ids` and the exact SHA-256 digest of that exact
    version's stored bytes; one bad entry fails the whole call atomically before any receipt
    is written (`TypedArtifactStore.acknowledge_handoff`). Merely completing a transport
    delivery turn never calls this -- `test_delivery_ack_does_not_advance_cursor`.

    72-T01 D23: validation, the read-only session load, the sender recheck and the
    shared decision for every acked id (any id not visible and usable voids the
    whole ack, `E_NOT_VISIBLE`) all precede the policy lock; under the lock the
    sender is rechecked again and the write commits only while it still holds.
    `view` (read-only) serves the checks; `store` (writable) only the write."""
    from rush.memory.authorization import hold_policy_lock
    from rush.memory.retrieval import recheck_failure
    from rush.memory.store import MemoryAccessChanged

    updates = validate_readbacks(readbacks)
    reader = view if view is not None else store
    if not isinstance(reader, TypedArtifactStore):
        reader = reader()
    session = load_session(reader, session_id, capability, now=now)
    access = delivery_access(reader, session)
    for artifact_id, _version, _digest in updates:
        if artifact_id not in session.granted_ids:
            raise HandoffError(
                f"Artifact {artifact_id!r} was never granted to this session.",
                code="E_PERMISSION",
            )
    acked = {artifact_id for artifact_id, _version, _digest in updates}
    if acked - _usable_ids(reader, sorted(acked), access):
        raise HandoffError(
            "An acknowledged artifact is not visible.", code="E_NOT_VISIBLE"
        )
    try:
        with hold_policy_lock(data_root=getattr(access, "data_root", None)):
            delivery_access(reader, load_session(reader, session_id, capability))
            writer = store if isinstance(store, TypedArtifactStore) else store()
            try:
                return writer.acknowledge_handoff(
                    session_id, updates, commit_check=lambda: recheck_failure(access)
                )
            except VersionConflictError as exc:
                raise HandoffError(str(exc), code="E_VERSION") from exc
            except MemoryAccessChanged as exc:
                raise HandoffError(
                    f"Handoff acknowledgement denied: {exc.reason}.",
                    code=exc.code,
                    reason=exc.reason,
                ) from exc
    except OSError:
        raise HandoffError(
            "Handoff acknowledgement denied: lock_unavailable.",
            reason="lock_unavailable",
        ) from None
