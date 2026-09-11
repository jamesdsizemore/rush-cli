"""MC07 (Phase 63) confirmed intent: an executed behavior's requirement, confirmed only by
a resolvable, currently-`STATED` user statement -- never by a caller-asserted `confirmed`
flag, an agent-authored timestamp, or an imported/inferred role label (MC07 authority rule).

One `architectural_decision` artifact per `intent_id` (the artifact's own `id`), mutated
in place through `TypedArtifactStore.update_content()`'s existing compare-and-swap path --
never a parallel store. Every mutation (`record_intent`, `supersede_intent`) therefore keeps
its full prior content readable forever in `memory_artifact_versions` (MC01 §6.1's existing
audit trail): supersession replaces the *current* row but never deletes or overwrites that
history. `check_intent`/`intent_evidence` are read-only -- they inspect already-recorded
evidence and never launch a command.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from rush.memory.store import (
    MemoryArtifact,
    TypedArtifactStore,
    VersionConflictError,
    compute_content_signature,
)
from rush.memory.trust import default_entry_tier

IntentStatus = Literal["confirmed", "candidate"]

# A real `ToolResult.status` (`rush.tools.base.ToolStatus`) or `VerifyAttemptOutcome.outcome`
# (`rush.patch.contracts.PatchOutcome`) on a `check_ref`'s evidence -- the only two truthful,
# already-executed result vocabularies this repo writes into memory (MC05/`experience.py`).
# A bare label/tag record (e.g. `{"kind": "trace", "tags": [...]}`) has neither key and is
# never mistaken for behavioral verification.
_STATUS_RECOGNIZED = frozenset({"ok", "warn", "fail", "error", "skipped"})
_STATUS_PASS = frozenset({"ok"})
_OUTCOME_RECOGNIZED = frozenset({"completed", "unavailable", "failed"})
_OUTCOME_PASS = frozenset({"completed"})


def _fts_phrase(text: str) -> str:
    """Quotes `text` as one FTS5 phrase so a hyphenated ID (e.g. `"guest-buy"`) can't be
    misread as the `-` NOT operator."""
    return '"' + text.replace('"', '""') + '"'


def _resolve_authorized_statement(
    project_root: Path, statement_ref: Mapping[str, Any] | None
) -> MemoryArtifact | None:
    """An intent may only be confirmed by a resolvable, currently-`STATED` statement at
    *exactly* its current stored version. A stale ref (superseded since), a missing
    artifact, or any non-`STATED` tier (`DERIVED`/`EXTERNAL_WRITE`/`IMPORTED` -- an inferred
    preference, an agent-authored record, or an imported role label) resolves to `None`.
    """
    if not statement_ref:
        return None
    statement_id = statement_ref.get("id")
    statement_version = statement_ref.get("version")
    if not statement_id or statement_version is None:
        return None
    current = TypedArtifactStore(project_root).get_current(str(statement_id))
    if current is None or current.trust_tier != "STATED":
        return None
    if current.artifact_version != statement_version:
        return None
    return current


def _execution_result(content: Mapping[str, Any]) -> tuple[bool, bool]:
    """`(recognized, passed)` for one evidence artifact's content."""
    status = content.get("status")
    if status in _STATUS_RECOGNIZED:
        return True, status in _STATUS_PASS
    outcome = content.get("outcome")
    if outcome in _OUTCOME_RECOGNIZED:
        return True, outcome in _OUTCOME_PASS
    return False, False


def record_intent(
    *,
    project_root: Path,
    intent_id: str,
    behavior_id: str | None = None,
    statement_ref: Mapping[str, Any] | None = None,
    source_refs: Sequence[Mapping[str, Any]] | None = None,
    check_refs: Sequence[Mapping[str, Any]] | None = None,
    exceptions: Sequence[str] | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """MC07.2: create a new intent, or re-record (confirm) an existing one.

    An inferred record -- `statement_ref=None`, e.g. mined from a preference or observation
    -- always stays `status="candidate"`; there is no `confirmed=` parameter here precisely
    so a caller can never assert its way past resolution. Re-recording an *existing*
    `intent_id` requires `expected_version` to match its current version (compare-and-swap);
    any field omitted on a re-record defaults to its currently-stored value, never silently
    cleared. `behavior_id` is required for a brand-new `intent_id` (there is no prior value
    to default from).
    """
    store = TypedArtifactStore(project_root)
    current = store.get_current(intent_id)
    if current is None:
        if expected_version is not None:
            return {
                "code": "E_VERSION",
                "message": f"intent {intent_id!r} does not exist yet; omit expected_version.",
            }
        if not behavior_id:
            return {
                "code": "E_INPUT",
                "message": f"intent {intent_id!r} is new; behavior_id is required.",
            }
    else:
        if expected_version is None or expected_version != current.artifact_version:
            return {
                "code": "E_VERSION",
                "message": (
                    f"intent {intent_id!r} already exists at version "
                    f"{current.artifact_version}; expected_version must match to re-record."
                ),
            }
        prior = current.content
        if behavior_id is None:
            behavior_id = prior.get("behavior_id")
        if statement_ref is None:
            statement_ref = prior.get("statement_ref")
        if source_refs is None:
            source_refs = prior.get("source_refs", [])
        if check_refs is None:
            check_refs = prior.get("check_refs", [])
        if exceptions is None:
            exceptions = prior.get("exceptions", [])

    resolved = _resolve_authorized_statement(project_root, statement_ref)
    status: IntentStatus = "confirmed" if resolved is not None else "candidate"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "intent",
        "intent_id": intent_id,
        "behavior_id": behavior_id,
        "statement_ref": dict(statement_ref) if statement_ref else None,
        "source_refs": [dict(r) for r in (source_refs or ())],
        "check_refs": [dict(r) for r in (check_refs or ())],
        "exceptions": list(exceptions or ()),
        "status": status,
    }

    if current is None:
        artifact = MemoryArtifact(
            id=intent_id,
            family="memory",
            subject="architectural_decision",
            trust_tier=default_entry_tier("local_tool"),
            content=payload,
            source=f"intent:{intent_id}",
            created_at=time.time(),
            content_hash=compute_content_signature(payload),
        )
        version = store.write(artifact).artifact_version
    else:
        try:
            store.update_content(intent_id, payload, expected_version=expected_version)
        except VersionConflictError as exc:
            return {"code": exc.code, "message": str(exc)}
        version = current.artifact_version + 1

    return {
        "code": "OK",
        "id": intent_id,
        "version": version,
        "intent_id": intent_id,
        "status": status,
        "statement_ref": payload["statement_ref"],
        "behavior_id": behavior_id,
        "check_refs": payload["check_refs"],
    }


def supersede_intent(
    *,
    project_root: Path,
    intent_id: str,
    expected_old_version: int,
    new_statement_ref: Mapping[str, Any],
    new_behavior_id: str | None = None,
    source_refs: Sequence[Mapping[str, Any]] | None = None,
    check_refs: Sequence[Mapping[str, Any]] | None = None,
    exceptions: Sequence[str] | None = None,
) -> dict[str, Any]:
    """MC07.2: explicit supersession -- an actual change to the recorded requirement.

    Requires the exact current version (`expected_old_version`, compare-and-swap) and a
    *new*, resolvable, currently-`STATED` `new_statement_ref`. A caller-asserted flag, an
    agent-authored timestamp, or an imported/inferred role label never resolves to `STATED`
    and is therefore rejected here the same way (MC07 authority rule) -- never a permissive
    fallback. `source_refs`/`check_refs`/`exceptions` default to the prior record's values
    when omitted, so old evidence is carried forward rather than silently dropped; the prior
    content itself is never deleted -- it stays readable at `expected_old_version` in
    `memory_artifact_versions`.
    """
    store = TypedArtifactStore(project_root)
    current = store.get_current(intent_id)
    if current is None:
        return {"code": "E_INPUT", "message": f"unknown intent {intent_id!r}"}
    if current.artifact_version != expected_old_version:
        return {
            "code": "E_VERSION",
            "message": (
                f"expected_old_version={expected_old_version} does not match current "
                f"version={current.artifact_version}"
            ),
        }
    resolved = _resolve_authorized_statement(project_root, new_statement_ref)
    if resolved is None:
        return {
            "code": "E_PERMISSION",
            "message": (
                "supersede_intent requires a resolvable, currently-STATED "
                "new_statement_ref -- an agent timestamp or an imported/inferred role "
                "label can never confirm or supersede an intent."
            ),
        }

    prior = current.content
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "intent",
        "intent_id": intent_id,
        "behavior_id": new_behavior_id or prior.get("behavior_id"),
        "statement_ref": dict(new_statement_ref),
        "source_refs": [
            dict(r)
            for r in (
                source_refs if source_refs is not None else prior.get("source_refs", [])
            )
        ],
        "check_refs": [
            dict(r)
            for r in (
                check_refs if check_refs is not None else prior.get("check_refs", [])
            )
        ],
        "exceptions": list(
            exceptions if exceptions is not None else prior.get("exceptions", [])
        ),
        "status": "confirmed",
        "supersedes_version": expected_old_version,
    }
    try:
        store.update_content(intent_id, payload, expected_version=expected_old_version)
    except VersionConflictError as exc:
        return {"code": exc.code, "message": str(exc)}

    return {
        "code": "OK",
        "id": intent_id,
        "version": expected_old_version + 1,
        "intent_id": intent_id,
        "status": "confirmed",
        "behavior_id": payload["behavior_id"],
        "statement_ref": payload["statement_ref"],
        "supersedes_version": expected_old_version,
    }


def check_intent(
    *,
    project_root: Path,
    intent_id: str,
    current_revision: str | None = None,
) -> dict[str, Any]:
    """MC07.3: read-only -- exact-revision execution evidence for one intent's `check_refs`,
    or `"UNRESOLVED"`. Never launches a command; a stale reference, an unrecognized
    label/tag record, a behavior-ID mismatch, or a revision mismatch (when `current_revision`
    is given) is silently skipped, never treated as proof.
    """
    current = TypedArtifactStore(project_root).get_current(intent_id)
    if current is None:
        return {"code": "E_INPUT", "message": f"unknown intent {intent_id!r}"}
    content = current.content
    behavior_id = content.get("behavior_id")
    store = TypedArtifactStore(project_root)
    for ref in content.get("check_refs", []):
        ref_id = ref.get("id") if isinstance(ref, Mapping) else None
        ref_version = ref.get("version") if isinstance(ref, Mapping) else None
        if not ref_id:
            continue
        evidence = store.get_current(str(ref_id))
        if evidence is None or evidence.artifact_version != ref_version:
            continue  # stale/unresolved reference -- never trusted
        recognized, passed = _execution_result(evidence.content)
        if not recognized:
            continue  # e.g. a bare trace/tag record -- not behavioral verification
        evidence_behaviors = evidence.content.get("behavior_ids")
        if evidence_behaviors is None:
            evidence_behaviors = [evidence.content.get("behavior_id")]
        if behavior_id not in evidence_behaviors:
            continue
        revision = evidence.content.get("revision") or evidence.content.get(
            "base_commit"
        )
        if current_revision is not None and revision != current_revision:
            continue  # bound to current revision -- a stale receipt is never proof
        return {
            "code": "OK",
            "intent_id": intent_id,
            "behavior_id": behavior_id,
            "passed": passed,
            "evidence_ref": {"id": evidence.id, "version": evidence.artifact_version},
            "revision": revision,
        }
    return {
        "code": "UNRESOLVED",
        "intent_id": intent_id,
        "behavior_id": behavior_id,
        "message": "no exact-revision execution evidence found for this intent's check_refs.",
    }


def intent_evidence(
    *,
    project_root: Path,
    behavior_ids: Sequence[str] = (),
    session_allowlist: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """MC07.3: read-only -- the current intent record (refs only, not resolved evidence) for
    each of `behavior_ids`, for `prepare_memory` to surface without executing anything.

    Fails closed on an empty/absent `session_allowlist` or empty `behavior_ids`, matching
    `recall_repair_episodes()`'s existing no-default-cross-session-access precedent.
    """
    allowed_sources = set(session_allowlist or ())
    if not behavior_ids or not allowed_sources:
        return []
    store = TypedArtifactStore(project_root)
    seen_ids: set[str] = set()
    results: list[dict[str, Any]] = []
    for behavior_id in behavior_ids:
        for artifact in store.search(
            "architectural_decision", _fts_phrase(behavior_id)
        ):
            if artifact.id in seen_ids or artifact.source not in allowed_sources:
                continue
            content = artifact.content
            if (
                content.get("kind") != "intent"
                or content.get("behavior_id") != behavior_id
            ):
                continue
            seen_ids.add(artifact.id)
            results.append(
                {
                    "id": artifact.id,
                    "version": artifact.artifact_version,
                    "intent_id": content.get("intent_id"),
                    "behavior_id": behavior_id,
                    "status": content.get("status"),
                    "statement_ref": content.get("statement_ref"),
                    "check_refs": content.get("check_refs", []),
                }
            )
    return results


__all__ = [
    "IntentStatus",
    "check_intent",
    "intent_evidence",
    "record_intent",
    "supersede_intent",
]
