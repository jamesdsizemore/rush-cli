"""MC03 §6.3 duplicate episode consolidation preserving originals, exceptions, contradictions
and trust (docs/phase-plans/MC03.md).

`consolidate_episodes()` groups `episodic` artifacts sharing one `symptom` by an exact
canonical `(symptom, condition, attempt, outcome)` tuple — never a fuzzy/semantic match, per
§6.3 ("semantic similarity may propose a group but cannot merge contradictory conditions
automatically"). The largest exact-duplicate group becomes the summary's repeated majority;
every other member (a differing condition, attempt, or outcome under the same symptom) is
recorded as a distinct `exceptions` entry, never folded into the repetition count. Every
original member row is left untouched — the derived summary is a new artifact referencing
member IDs/versions, not a replacement.

72-T03: members are selected through the shared visibility decision under one access
(owner-scoped), the summary records `member_refs` binding each member's exact version and
hashes, and `summary_invalid_reason()` is the derived-summary validity check the shared
decision applies to every summary row on every read route.
"""

from __future__ import annotations

import dataclasses
import json
import time
import uuid
from collections.abc import Iterable
from contextlib import ExitStack
from pathlib import Path
from typing import Any, cast

from rush.memory.retrieval import (
    _GRANT_FOR_OPERATION,
    MemoryAccess,
    SourceValidationMemo,
    _access_allows,
    evaluate_artifact_visibility,
    memory_policy_decision,
    recheck_failure,
)
from rush.memory.store import (
    MemoryArtifact,
    OwnerScope,
    TypedArtifactStore,
    decode_content,
    legacy_owner_scope,
    owner_scope_for_row,
    sqlite_integer_in_range,
)

_REQUIRED_FIELDS = ("symptom", "condition", "attempt", "outcome")

DERIVED_SUMMARY_KIND = "consolidated_episode_summary"
# Owner decision 2026-10-05 (T006): provenance order, weakest to strongest. A summary
# takes its weakest member's tier and is never STATED.
TRUST_TIER_ORDER = ("IMPORTED", "EXTERNAL_WRITE", "DERIVED", "STATED")

_MEMBERS_INVALID = "derived_members_invalid"
_MEMBER_NOT_CURRENT = "derived_member_not_current"
_MEMBER_NOT_VISIBLE = "derived_member_not_visible"


def is_derived_summary(content: object) -> bool:
    return isinstance(content, dict) and content.get("kind") == DERIVED_SUMMARY_KIND


def _canonical_tuple(content: dict[str, Any]) -> tuple[str, str, str, str] | None:
    """`None` marks an episode missing one of the four required fields — skipped, never
    raised, so one malformed episode can't abort grouping the rest."""
    if not all(field in content for field in _REQUIRED_FIELDS):
        return None
    canonical_condition = json.dumps(
        content["condition"], sort_keys=True, separators=(",", ":")
    )
    return (
        str(content["symptom"]),
        canonical_condition,
        str(content["attempt"]),
        str(content["outcome"]),
    )


def _permission(message: str) -> dict[str, Any]:
    return {"code": "E_PERMISSION", "message": message}


def _refused(code: str, reason: str) -> dict[str, Any]:
    return {
        "code": code,
        "reason": reason,
        "message": f"memory consolidate refused: {reason}",
    }


def _has_pattern(sources: Iterable[Any]) -> bool:
    return any(isinstance(item, str) and "*" in item for item in sources)


@dataclasses.dataclass(frozen=True)
class _Admission:
    reader: MemoryAccess
    required_owner: OwnerScope | None
    member_sources: tuple[str, ...]
    summary_owner: OwnerScope | None
    recheck: MemoryAccess


def _admit(
    store: TypedArtifactStore,
    access: MemoryAccess | None,
    allowlist: list[Any] | None,
    source: str,
    data_root: Path | None,
) -> _Admission | dict[str, Any]:
    """B12 gates, run under the policy lock: the D3 write predicate per access form
    (with its denial reason), the project root, the summary source and the
    `session_allowlist` narrowing (D40 `source_granted`), then the D1 recheck."""
    from rush.memory.authorization import source_granted

    root = store.project_root
    mode, why = memory_policy_decision(root, data_root=data_root)
    if access is None:
        if mode == "policy":
            return _refused("E_PERMISSION", "policy_grant_required")
        if mode != "legacy":
            return _refused("E_PERMISSION", why or "policy_invalid")
        if not allowlist:
            return _permission(
                "memory consolidate requires a non-empty session_allowlist "
                "(fail-closed, no default cross-session access)."
            )
        if _has_pattern(allowlist):
            return _refused("E_INPUT", "source_pattern")
        owner = legacy_owner_scope(root)
        reader = MemoryAccess.legacy(
            root, allowlist, owner_scope=owner, operation="write"
        )
        return _Admission(reader, owner, reader.sources, None, reader)
    if access.kind == "policy":
        if "write" not in access.required_operations:
            return _refused("E_PERMISSION", "write_access_required")
    else:
        if mode == "policy":
            return _refused("E_PERMISSION", "policy_grant_required")
        if mode != "legacy":
            return _refused("E_PERMISSION", why or "policy_invalid")
        if _GRANT_FOR_OPERATION.get(access.operation, access.operation) != "write":
            return _refused("E_PERMISSION", "write_access_required")
        if not access.sources:
            return _refused("E_PERMISSION", "session_allowlist_required")
    if access.project_root != root:
        return _refused("E_PERMISSION", "project_mismatch")
    if access.kind == "policy":
        if not isinstance(source, str) or "*" in source:
            return _refused("E_INPUT", "source_pattern")
        if not source_granted(source, access.sources):
            return _refused("E_PERMISSION", "source_not_granted")
    member_sources = access.sources
    if allowlist is not None:
        if _has_pattern(allowlist):
            return _refused("E_INPUT", "source_pattern")
        if not all(source_granted(item, access.sources) for item in allowlist):
            return _refused("E_PERMISSION", "source_not_granted")
        member_sources = tuple(sorted(set(allowlist)))
    failure = recheck_failure(access)
    if failure is not None:
        return _refused(*failure)
    if access.kind == "policy":
        reader = dataclasses.replace(access, sources=member_sources)
        return _Admission(
            reader, access.owner_scope, member_sources, access.owner_scope, access
        )
    owner = legacy_owner_scope(root)
    reader = MemoryAccess.legacy(
        root,
        member_sources,
        owner_scope=owner,
        operation="write",
        data_root=access.data_root,
    )
    return _Admission(reader, owner, member_sources, None, access)


def consolidate_episodes(
    store: TypedArtifactStore,
    *,
    symptom: str,
    session_allowlist: Iterable[str] | None,
    source: str = "consolidation",
    access: MemoryAccess | None = None,
    now: float | None = None,
    memo: SourceValidationMemo | None = None,
) -> dict[str, Any]:
    """Groups `episodic` members matching `symptom` and writes one derived summary artifact.

    Returns `{"code": ...}`: `"E_PERMISSION"`/`"E_INPUT"` with a `reason` for a refused
    access, source or allowlist (B12), `"E_PERMISSION"` for an empty legacy
    `session_allowlist` (fail-closed, matching `TypedArtifactStore.recall()`'s
    precedent), `"E_INPUT"` when no visible episode matches `symptom`, else `"OK"` with
    the summary under `"summary"`.

    One policy-lock interval and one `BEGIN IMMEDIATE` cover the member read and the
    summary insert (R9): members are selected by SQL on that connection (never FTS, so
    a symptom is literal text), filtered through the shared visibility decision, and
    the summary is inserted through `_prepare_write`/`_insert_row` on the same
    connection before the D1 recheck and commit.
    """
    allowlist = None if session_allowlist is None else list(session_allowlist)
    from rush.dashboard.state import PolicyLockRootUncreatable
    from rush.memory.authorization import (
        hold_policy_lock,
        load_policy_readonly,
        source_granted,
    )

    data_root = access.data_root if access is not None else None
    with ExitStack() as stack:
        try:
            stack.enter_context(hold_policy_lock(data_root=data_root))
        except PolicyLockRootUncreatable:
            if load_policy_readonly(data_root=data_root)["state"] != "missing":
                return _refused("E_PERMISSION", "lock_unavailable")
        except Exception:  # noqa: BLE001 - any lock failure denies the mutation
            return _refused("E_PERMISSION", "lock_unavailable")
        admitted = _admit(store, access, allowlist, source, data_root)
        if isinstance(admitted, dict):
            return admitted
        moment = time.time() if now is None else now
        memo = memo or SourceValidationMemo()

        clause, params = store._owner_prefilter("", admitted.required_owner)
        sql = (
            "SELECT * FROM memory_artifacts WHERE subject = 'episodic' "
            "AND archived_at IS NULL AND expired_at IS NULL"
        )
        if clause:
            sql += " AND " + clause
        sql += " ORDER BY id"
        with store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            groups: dict[
                tuple[str, str, str, str], list[tuple[Any, dict[str, Any]]]
            ] = {}
            for row in conn.execute(sql, params).fetchall():
                if (
                    admitted.required_owner is not None
                    and owner_scope_for_row(row, store.project_root)
                    != admitted.required_owner
                ):
                    continue
                if not source_granted(row["source"], admitted.member_sources):
                    continue
                decision = evaluate_artifact_visibility(
                    store, row, access=admitted.reader, now=moment, memo=memo
                )
                if not (decision.visible and decision.usable_as_current):
                    continue
                try:
                    content = decode_content(row["content"])
                except (TypeError, ValueError):
                    continue
                if not isinstance(content, dict) or is_derived_summary(content):
                    continue
                canonical = _canonical_tuple(content)
                if canonical is None or canonical[0] != symptom:
                    continue
                groups.setdefault(canonical, []).append((row, content))

            if not groups:
                conn.rollback()
                return {
                    "code": "E_INPUT",
                    "message": f"no episodes found for symptom {symptom!r}",
                }

            majority_tuple, majority_members = max(
                groups.items(), key=lambda kv: len(kv[1])
            )
            exception_members = [
                member
                for canonical, members in groups.items()
                if canonical != majority_tuple
                for member in members
            ]
            all_members = majority_members + exception_members

            # §6.3: "repetition/model agreement never promotes it" — the summary takes its
            # weakest member's tier (TRUST_TIER_ORDER) and is never STATED (D6).
            summary_trust = min(
                (row["trust_tier"] for row, _ in all_members),
                key=TRUST_TIER_ORDER.index,
            )
            if summary_trust == "STATED":
                summary_trust = "DERIVED"

            member_refs: dict[str, dict[str, Any]] = {}
            for row, _ in all_members:
                version_row = conn.execute(
                    "SELECT payload_hash FROM memory_artifact_versions "
                    "WHERE artifact_id = ? AND artifact_version = ?",
                    (row["id"], row["artifact_version"]),
                ).fetchone()
                member_refs[row["id"]] = {
                    "version": row["artifact_version"],
                    "payload_hash": version_row[0] if version_row is not None else None,
                    "content_hash": row["content_hash"],
                }

            summary_content = {
                "kind": DERIVED_SUMMARY_KIND,
                "symptom": symptom,
                "common_condition": json.loads(majority_tuple[1]),
                "common_attempt": majority_tuple[2],
                "common_outcome": majority_tuple[3],
                "repetition": len(majority_members),
                "member_ids": sorted(row["id"] for row, _ in all_members),
                "member_versions": {
                    row["id"]: row["artifact_version"] for row, _ in all_members
                },
                "member_refs": member_refs,
                "exceptions": [
                    {
                        "id": row["id"],
                        "version": row["artifact_version"],
                        "condition": content.get("condition"),
                        "attempt": content.get("attempt"),
                        "outcome": content.get("outcome"),
                    }
                    for row, content in exception_members
                ],
            }
            stored, evicted = store._prepare_write(
                conn,
                MemoryArtifact(
                    id=str(uuid.uuid4()),
                    family="experience",
                    subject="episodic",
                    trust_tier=summary_trust,
                    content=summary_content,
                    source=source,
                    created_at=time.time(),
                    owner_scope=admitted.summary_owner,
                ),
            )
            store._insert_row(conn, stored)
            failure = recheck_failure(admitted.recheck)
            if failure is not None:
                conn.rollback()
                return _refused(*failure)
            conn.commit()
        store._note_inserted(stored, evicted)
        return {
            "code": "OK",
            "summary": {
                "id": stored.id,
                "version": stored.artifact_version,
                "trust_tier": stored.trust_tier,
                **stored.content,
            },
        }


def _is_version(value: object) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and sqlite_integer_in_range(value)
    )


def _safe_id(value: object) -> bool:
    """A member id that can reach SQLite: a non-empty UTF-8-encodable string."""
    if not isinstance(value, str) or not value:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _member_identities(content: object) -> list[str] | None:
    """Every member id named anywhere in a summary body (`member_ids`, the keys of
    `member_versions` and `member_refs`), or `None` when one of them is not a safe
    id: an identity that cannot be attributed cannot authorize disclosure."""
    if not isinstance(content, dict):
        return []
    named: list[object] = []
    ids = content.get("member_ids")
    if isinstance(ids, list):
        named.extend(ids)
    for key in ("member_versions", "member_refs"):
        mapping = content.get(key)
        if isinstance(mapping, dict):
            named.extend(mapping)
    if not all(_safe_id(member_id) for member_id in named):
        return None
    return sorted({cast(str, member_id) for member_id in named})


def _parse_member_refs(
    content: object,
) -> tuple[dict[str, int], dict[str, dict[str, Any]]] | None:
    """`(member_versions, member_refs)` from a summary body, or `None` when any of
    `member_ids`, `member_versions` or `member_refs` is absent, empty or malformed
    (B15, AM6 R15): unique safe ids, matching member sets, exact versions, and every
    ref carrying `version`, `payload_hash` and `content_hash` (a string or `None`)."""
    if not isinstance(content, dict):
        return None
    ids = content.get("member_ids")
    versions = content.get("member_versions")
    refs = content.get("member_refs")
    if not (
        isinstance(ids, list)
        and isinstance(versions, dict)
        and isinstance(refs, dict)
        and versions
    ):
        return None
    if (
        not all(_safe_id(member_id) for member_id in ids)
        or len(ids) != len(set(ids))
        or set(ids) != set(versions)
        or set(refs) != set(versions)
    ):
        return None
    for member_id, version in versions.items():
        ref = refs[member_id]
        if (
            not _safe_id(member_id)
            or not _is_version(version)
            or not isinstance(ref, dict)
            or not {"version", "payload_hash", "content_hash"} <= set(ref)
            or not _is_version(ref["version"])
            or ref["version"] != version
            or not isinstance(ref["payload_hash"], (str, type(None)))
            or not isinstance(ref["content_hash"], (str, type(None)))
        ):
            return None
    return versions, refs


def summary_invalid_reason(
    store: TypedArtifactStore,
    summary_content: object,
    *,
    access: MemoryAccess,
    now: float | None = None,
    memo: SourceValidationMemo | None = None,
) -> str | None:
    """`None` when the summary is current for this reader, else its reason code (B15).

    First pass, authorization before qualification: a member that is missing, that
    `access` may not read (root, source or owner), or whose id cannot be attributed
    safely → `derived_member_not_visible` (C01/C02: no artifact receives copied
    authority), whatever else is wrong with the summary. Second pass: absent, empty or
    malformed refs, or a member that is itself a summary → `derived_members_invalid`;
    a member whose version, exact-version payload hash or content hash differs from
    its ref (`None` compared exactly), or that is not visible and usable as current
    under `access` → `derived_member_not_current`."""
    identities = _member_identities(summary_content)
    if identities is None:
        return _MEMBER_NOT_VISIBLE
    rows: dict[str, Any] = {}
    for member_id in identities:
        row = store.get_current_row(member_id)
        if row is None or not _access_allows(store, row, access, "ordinary"):
            return _MEMBER_NOT_VISIBLE
        rows[member_id] = row
    parsed = _parse_member_refs(summary_content)
    if parsed is None:
        return _MEMBERS_INVALID
    versions, refs = parsed
    for member_id in versions:
        try:
            member_content = decode_content(rows[member_id]["content"])
        except (TypeError, ValueError):
            return _MEMBER_NOT_CURRENT
        if is_derived_summary(member_content):
            return _MEMBERS_INVALID
    memo = memo or SourceValidationMemo()
    moment = time.time() if now is None else now
    for member_id, version in versions.items():
        row = rows[member_id]
        ref = refs[member_id]
        if row["artifact_version"] != version:
            return _MEMBER_NOT_CURRENT
        payload = store.get_version_payload(member_id, version)
        if payload is None or payload[1] != ref["payload_hash"]:
            return _MEMBER_NOT_CURRENT
        if row["content_hash"] != ref["content_hash"]:
            return _MEMBER_NOT_CURRENT
        decision = evaluate_artifact_visibility(
            store, row, access=access, now=moment, memo=memo
        )
        if not (decision.visible and decision.usable_as_current):
            return _MEMBER_NOT_CURRENT
    return None


def summary_is_current(
    store: TypedArtifactStore,
    summary_content: object,
    *,
    access: MemoryAccess,
    now: float | None = None,
    memo: SourceValidationMemo | None = None,
) -> bool:
    """True iff every referenced member is still at its recorded version and bound bytes
    and is visible and usable as current to `access` (§6.3: "an edited member
    invalidates or re-derives the summary")."""
    return (
        summary_invalid_reason(
            store, summary_content, access=access, now=now, memo=memo
        )
        is None
    )
