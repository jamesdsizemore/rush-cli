"""MC03 §6.3 evidence relations: explicit versioned links with bounded, authorized traversal
(docs/phase-plans/MC03.md).

`add_relation()` atomically inserts one `memory_relations` row after checking both endpoints
are visible and usable as current under one access (72-T01's shared decision), at their
current versions, and, for acyclic kinds (`supersedes`), that the new edge wouldn't close a
cycle. A missing endpoint and a denied one return the identical body. `related_artifacts()`
walks that table breadth-first from one seed over current-version edges, deciding every
node through the shared decision before the node cap — a denied or stale neighbor is
silently dropped, never disclosed by ID or count (§6.3: "Do not disclose denied neighbor
IDs, counts or source names").

Both functions return a plain dict with a leading `"code"` key, mirroring `retrieval.py`'s
contract so `rush.tools.memory.MemoryTool` can map it onto `ToolResult.status` unchanged.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable, Collection, Iterable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import tiktoken

from rush.memory.retrieval import (
    DEFAULT_ENCODING,
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_TOKENS,
    MemoryAccess,
    SourceValidationMemo,
    evaluate_artifact_visibility,
    is_write_access,
    memory_policy_decision,
    recheck_failure,
)
from rush.memory.store import (
    OwnerScope,
    TypedArtifactStore,
    owner_scope_for_row,
    sqlite_integer_in_range,
)

RELATION_KINDS: frozenset[str] = frozenset(
    {
        "supersedes",
        "contradicts",
        "caused_by",
        "fixed_by",
        "validated_by",
        "implements",
        "depends_on",
    }
)

DEFAULT_DEPTH = 1
_MAX_DEPTH = 2
_MAX_NODES = 32
_ACYCLIC_KINDS = frozenset({"supersedes"})

_ENDPOINT_NOT_VISIBLE = {
    "code": "E_NOT_VISIBLE",
    "message": "relation endpoint is not visible",
}


def missing_root_result(encoding: str = DEFAULT_ENCODING) -> dict[str, Any]:
    """The `related` body for a missing, denied or ineligible root."""
    return {
        "code": "E_NOT_VISIBLE",
        "items": [],
        "complete": True,
        "tokens": 0,
        "bytes": 0,
        "encoding": encoding,
    }


def _connect(store: TypedArtifactStore) -> sqlite3.Connection:
    # The store's own connection: a writable store opens one as before, and a
    # read-only view (R20.G8) returns its single `open_readonly()` connection,
    # so a related-by-ID read never creates a DB or `-wal`/`-shm` sidecars.
    return store._connect()


def _owner(row: sqlite3.Row, project_root: Path) -> OwnerScope | None:
    try:
        return owner_scope_for_row(row, project_root)
    except (TypeError, ValueError):
        return None


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_text(value: object) -> bool:
    """A `str` every UTF-8 encoder accepts (no lone surrogate reaches SQLite)."""
    if not isinstance(value, str):
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _input_error(field_name: str, message: str) -> dict[str, Any]:
    return {"code": "E_INPUT", "field": field_name, "message": message}


def _refusal(code: str, reason: str) -> dict[str, Any]:
    return {"code": code, "reason": reason, "message": f"memory link denied: {reason}."}


def relation_input_error(
    *,
    source_id: Any,
    source_version: Any,
    target_id: Any,
    target_version: Any,
    kind: Any,
    origin_ref: Any = None,
    known_kind: bool = True,
) -> dict[str, Any] | None:
    """72-T03 B1: the `E_INPUT` body for an invalid link request, else `None`. Checked in
    order: kind, versions, id/`origin_ref` types, UTF-8 encodability, `supersedes`
    self-loop. Never echoes a rejected value. `known_kind=False` checks only that the
    kind is text: MemoryTool `link` checks the request shape before its route decision
    and the kind's membership in `RELATION_KINDS` after admission, as at HEAD."""
    if not isinstance(kind, str) or (known_kind and kind not in RELATION_KINDS):
        shown = repr(kind) if _is_text(kind) else "a non-text value"
        return _input_error("kind", f"unsupported relation kind: {shown}")
    for name, version in (
        ("source_version", source_version),
        ("target_version", target_version),
    ):
        if not _is_int(version) or not sqlite_integer_in_range(version):
            return _input_error(
                name, f"{name} must be an integer in the storable integer range"
            )
    texts: tuple[tuple[str, Any], ...] = (
        ("source_id", source_id),
        ("target_id", target_id),
    )
    if origin_ref is not None:
        texts += (("origin_ref", origin_ref),)
    for name, value in texts:
        if not isinstance(value, str):
            return _input_error(name, f"{name} must be a string")
    for name, value in texts:
        if not _is_text(value):
            return _input_error(name, f"{name} must be valid UTF-8 text")
    if kind in _ACYCLIC_KINDS and source_id == target_id:
        return _input_error(
            "target_id", f"{kind} {source_id!r}->{target_id!r} would create a cycle"
        )
    return None


@contextmanager
def _policy_lock(access: MemoryAccess | None) -> Iterator[str | None]:
    """D24/D1: hold the policy lock for the whole helper. Yields `lock_unavailable`
    when it cannot be acquired, else `None` while the lock is held.
    72-T01's `PolicyLockRootUncreatable` fallback applies to legacy forms only."""
    from rush.dashboard.state import PolicyLockRootUncreatable
    from rush.memory.authorization import hold_policy_lock, load_policy_readonly

    data_root = access.data_root if access is not None else None
    with ExitStack() as stack:
        try:
            stack.enter_context(hold_policy_lock(data_root=data_root))
        except PolicyLockRootUncreatable:
            legacy_form = access is None or access.kind == "legacy_allowlist"
            if not (
                legacy_form
                and load_policy_readonly(data_root=data_root)["state"] == "missing"
            ):
                yield "lock_unavailable"
                return
        except Exception:  # noqa: BLE001 - any acquire failure denies the mutation
            yield "lock_unavailable"
            return
        yield None


def _write_denial(
    access: MemoryAccess | None, mode: str, why: str | None
) -> str | None:
    """72-T03 B2/B3 (D3): the `E_PERMISSION` reason a mutation helper refuses with, or
    `None` when `access` (or the `access=None` legacy form) may write."""
    if access is not None and access.kind == "policy":
        return None if is_write_access(access) else "write_access_required"
    if mode == "policy":
        return "policy_grant_required"
    if mode != "legacy":
        return why or "policy_invalid"
    if access is None:
        return None
    if not is_write_access(access):
        return "write_access_required"
    if not access.sources:
        return "session_allowlist_required"
    return None


def _supersedes_cycle_exists(
    conn: sqlite3.Connection, new_source: str, new_target: str
) -> bool:
    """True if a `supersedes` path already exists from `new_target` back to `new_source`,
    meaning inserting `new_source -> new_target` would close a cycle. BFS over existing
    `supersedes` edges only — other kinds never participate in this check."""
    seen = {new_target}
    frontier = [new_target]
    while frontier:
        current = frontier.pop()
        for (nxt,) in conn.execute(
            "SELECT target_id FROM memory_relations WHERE source_id = ? AND kind = 'supersedes'",
            (current,),
        ).fetchall():
            if nxt == new_source:
                return True
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return False


def insert_relation_tx(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    source_version: int,
    target_id: str,
    target_version: int,
    kind: str,
    origin_ref: str | None = None,
) -> dict[str, Any]:
    """72-T05 3.6.3: insert one edge inside the caller's open transaction (never
    begins or commits). Validates the kind, both versions (strict, storable
    integers), the `supersedes` self-edge/cycle rule and that both
    `(id, version)` pairs are live version rows. No visibility, owner or
    current-version check: callers that need them (`add_relation`) run them first."""
    if kind not in RELATION_KINDS:
        return {"code": "E_INPUT", "message": f"unsupported relation kind: {kind!r}"}
    for endpoint_id, endpoint_version in (
        (source_id, source_version),
        (target_id, target_version),
    ):
        if type(endpoint_version) is not int or not sqlite_integer_in_range(
            endpoint_version
        ):
            return {
                "code": "E_INPUT",
                "message": f"endpoint {endpoint_id!r} version must be a storable integer",
            }
    if kind in _ACYCLIC_KINDS and (
        source_id == target_id or _supersedes_cycle_exists(conn, source_id, target_id)
    ):
        return {
            "code": "E_INPUT",
            "message": f"{kind} {source_id!r}->{target_id!r} would create a cycle",
        }
    for endpoint_id, endpoint_version in (
        (source_id, source_version),
        (target_id, target_version),
    ):
        live = conn.execute(
            "SELECT 1 FROM memory_artifact_versions WHERE artifact_id = ? "
            "AND artifact_version = ? AND deleted = 0",
            (endpoint_id, endpoint_version),
        ).fetchone()
        if live is None:
            return {"code": "E_NOT_VISIBLE", "message": "relation endpoint not visible"}
    cur = conn.execute(
        "INSERT INTO memory_relations "
        "(source_id, source_version, target_id, target_version, kind, origin_ref, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            source_id,
            source_version,
            target_id,
            target_version,
            kind,
            origin_ref,
            time.time(),
        ),
    )
    return {"code": "OK", "sequence": cur.lastrowid}


def add_relation(
    store: TypedArtifactStore,
    *,
    source_id: str,
    source_version: int,
    target_id: str,
    target_version: int,
    kind: str,
    origin_ref: str | None = None,
    access: MemoryAccess | None = None,
    now: float | None = None,
    memo: SourceValidationMemo | None = None,
    receipt_writer: Callable[[sqlite3.Connection, dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """MC03 §6.3: atomically inserts one versioned evidence edge. Returns `{"code": ...}`
    (never raises for a business-rule rejection) with `"OK"` plus the new row's `sequence` on
    success; `"E_INPUT"` (with `field`) for an invalid request or a `supersedes` edge that
    would close a cycle; `"E_PERMISSION"` (with `reason`) for an access that may not write
    (72-T03 D3), an unavailable lock or a failed policy recheck; `"E_RESTART"` when the
    policy changed; `"E_NOT_VISIBLE"` (one body, no ID) when an endpoint is missing or not
    visible and usable as current under the access; and `"E_VERSION"` when a visible
    endpoint's requested version is not its current one.

    The policy lock is held for the whole call. `access=None` is the D1 `legacy`-mode
    form: each endpoint is decided under the legacy allowlist of the two endpoints' own
    sources, and both must share one effective owner (a legacy access additionally narrows
    to its declared owner). Every endpoint check runs inside one `BEGIN IMMEDIATE`
    transaction before the INSERT, and the access is rechecked before the commit, so a
    rejected edge never leaves a row.

    72-T06 D29: `receipt_writer` records the v2 `link` receipt inside that same
    transaction, after the insert and before commit.
    """
    refused = relation_input_error(
        source_id=source_id,
        source_version=source_version,
        target_id=target_id,
        target_version=target_version,
        kind=kind,
        origin_ref=origin_ref,
    )
    if refused is not None:
        return refused
    with _policy_lock(access) as lock_denial:
        if lock_denial is not None:
            return _refusal("E_PERMISSION", lock_denial)
        mode, why = memory_policy_decision(
            store.project_root,
            data_root=access.data_root if access is not None else None,
        )
        denial = _write_denial(access, mode, why)
        if denial is not None:
            return _refusal("E_PERMISSION", denial)
        if access is not None:
            failure = recheck_failure(access)
            if failure is not None:
                return _refusal(*failure)
        memo = memo or SourceValidationMemo()
        moment = time.time() if now is None else now
        with _connect(store) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                result = _insert_relation(
                    store,
                    conn,
                    endpoints=(
                        (source_id, source_version),
                        (target_id, target_version),
                    ),
                    kind=kind,
                    origin_ref=origin_ref,
                    access=access,
                    moment=moment,
                    memo=memo,
                    receipt_writer=receipt_writer,
                )
            except BaseException:
                conn.rollback()
                raise
            if result["code"] != "OK":
                conn.rollback()
            return result


def _insert_relation(
    store: TypedArtifactStore,
    conn: sqlite3.Connection,
    *,
    endpoints: tuple[tuple[str, int], tuple[str, int]],
    kind: str,
    origin_ref: str | None,
    access: MemoryAccess | None,
    moment: float,
    memo: SourceValidationMemo,
    receipt_writer: Callable[[sqlite3.Connection, dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """B4 inside the open transaction: rows, shared eligibility, legacy owner rule,
    versions, cycle, INSERT, recheck. The caller rolls back any non-`OK` result."""
    rows = []
    for endpoint_id, _requested in endpoints:
        row = conn.execute(
            "SELECT * FROM memory_artifacts WHERE id = ?", (endpoint_id,)
        ).fetchone()
        if row is None:
            return dict(_ENDPOINT_NOT_VISIBLE)
        rows.append(row)
    decide_with = access or MemoryAccess.legacy(
        store.project_root, sorted({row["source"] for row in rows}), operation="write"
    )
    for row in rows:
        decision = evaluate_artifact_visibility(
            store, row, access=decide_with, mode="ordinary", now=moment, memo=memo
        )
        if not (decision.visible and decision.usable_as_current):
            return dict(_ENDPOINT_NOT_VISIBLE)
    if decide_with.kind == "legacy_allowlist":
        owners = {_owner(row, store.project_root) for row in rows}
        if len(owners) != 1 or None in owners:
            return dict(_ENDPOINT_NOT_VISIBLE)
        if (
            decide_with.owner_scope is not None
            and decide_with.owner_scope not in owners
        ):
            return dict(_ENDPOINT_NOT_VISIBLE)
    for (endpoint_id, requested), row in zip(endpoints, rows, strict=True):
        if row["artifact_version"] != requested:
            return {
                "code": "E_VERSION",
                "message": f"endpoint {endpoint_id!r}@{requested} is not the "
                "current version",
            }
    (source_id, source_version), (target_id, target_version) = endpoints
    if kind in _ACYCLIC_KINDS and _supersedes_cycle_exists(conn, source_id, target_id):
        return {
            "code": "E_INPUT",
            "field": "target_id",
            "message": f"{kind} {source_id!r}->{target_id!r} would create a cycle",
        }
    cur = conn.execute(
        "INSERT INTO memory_relations "
        "(source_id, source_version, target_id, target_version, kind, origin_ref, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            source_id,
            source_version,
            target_id,
            target_version,
            kind,
            origin_ref,
            time.time(),
        ),
    )
    failure = recheck_failure(decide_with)
    if failure is not None:
        return _refusal(*failure)
    sequence = cur.lastrowid
    if receipt_writer is not None:
        receipt_writer(
            conn,
            {
                "artifact_id": source_id,
                "artifact_version": source_version,
                "result_refs": [
                    {"artifact_id": source_id, "artifact_version": source_version},
                    {"artifact_id": target_id, "artifact_version": target_version},
                ],
                "result": {"code": "OK", "sequence": sequence},
            },
        )
    return {"code": "OK", "sequence": sequence}


def _measure_related(items: list[dict[str, Any]], encoding: str) -> tuple[int, int]:
    text = json.dumps({"items": items}, ensure_ascii=False, separators=(",", ":"))
    return len(text.encode("utf-8")), len(tiktoken.get_encoding(encoding).encode(text))


@dataclass
class _Walk:
    """One traversal pass: the kept items, whether eligible evidence was left out, and
    every id that was eligible at its decision (kept or cut by a cap)."""

    items: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False
    eligible: set[str] = field(default_factory=set)


def _walk(
    store: TypedArtifactStore,
    *,
    artifact_id: str,
    version: int,
    access: MemoryAccess,
    historical: bool,
    moment: float,
    memo: SourceValidationMemo,
    depth: int,
    max_nodes: int,
    max_tokens: int,
    max_bytes: int,
    encoding: str,
    candidates: set[str] | None,
    selected_ids: Collection[str] | None,
) -> _Walk | None:
    """One breadth-first pass from the root through the shared decision, or `None` when
    the root fails it. With `candidates` (the final pass, R14) a node outside that set is
    never added: an eligible one only marks the result incomplete. 72-T01 D22: with
    `selected_ids` (the restricted bridge), a node outside it is never returned, counted
    against the cap, or traversed."""
    mode: Literal["ordinary", "historical"] = "historical" if historical else "ordinary"
    root = store.get_current_row(artifact_id)
    if root is None or root["artifact_version"] != version:
        return None
    decision = evaluate_artifact_visibility(
        store, root, access=access, mode=mode, now=moment, memo=memo
    )
    if not decision.visible or (not historical and not decision.usable_as_current):
        return None
    legacy = access.kind == "legacy_allowlist"
    anchor_owner = _owner(root, store.project_root)

    walk = _Walk()
    visited = {artifact_id}
    current_versions = {artifact_id: version}
    frontier = [artifact_id]
    with _connect(store) as conn:
        for _level in range(depth):
            next_frontier: list[str] = []
            for node_id in frontier:
                if historical:
                    edges = conn.execute(
                        "SELECT source_id, source_version, target_id, target_version, "
                        "kind FROM memory_relations WHERE source_id = ? OR target_id = ?",
                        (node_id, node_id),
                    ).fetchall()
                else:
                    node_version = current_versions[node_id]
                    edges = conn.execute(
                        "SELECT source_id, source_version, target_id, target_version, "
                        "kind FROM memory_relations "
                        "WHERE (source_id = ? AND source_version = ?) "
                        "OR (target_id = ? AND target_version = ?)",
                        (node_id, node_version, node_id, node_version),
                    ).fetchall()
                for edge in edges:
                    if edge["source_id"] == node_id:
                        neighbor_id = edge["target_id"]
                        edge_version = edge["target_version"]
                        direction = "outgoing"
                    else:
                        neighbor_id = edge["source_id"]
                        edge_version = edge["source_version"]
                        direction = "incoming"
                    if neighbor_id in visited:
                        continue
                    if selected_ids is not None and neighbor_id not in selected_ids:
                        continue
                    row = store.get_current_row(neighbor_id)
                    if row is None:
                        continue
                    if legacy and _owner(row, store.project_root) != anchor_owner:
                        continue
                    neighbor = evaluate_artifact_visibility(
                        store, row, access=access, mode=mode, now=moment, memo=memo
                    )
                    if not neighbor.visible:
                        continue
                    edge_current = row["artifact_version"] == edge_version
                    usable = neighbor.usable_as_current and edge_current
                    if not historical and not usable:
                        continue
                    walk.eligible.add(neighbor_id)
                    if candidates is not None and neighbor_id not in candidates:
                        walk.truncated = True
                        continue
                    if len(visited) >= max_nodes:
                        walk.truncated = True
                        continue
                    candidate: dict[str, Any] = {
                        "id": neighbor_id,
                        "version": row["artifact_version"],
                        "kind": edge["kind"],
                        "direction": direction,
                    }
                    if historical:
                        reasons = list(neighbor.reason_codes)
                        if not edge_current:
                            reasons.append("edge_version_not_current")
                        candidate.update(
                            usable_as_current=usable,
                            reason_codes=sorted(reasons),
                            edge_version=edge_version,
                        )
                    trial_bytes, trial_tokens = _measure_related(
                        [*walk.items, candidate], encoding
                    )
                    if trial_bytes > max_bytes or trial_tokens > max_tokens:
                        walk.truncated = True
                        continue
                    visited.add(neighbor_id)
                    current_versions[neighbor_id] = row["artifact_version"]
                    walk.items.append(candidate)
                    next_frontier.append(neighbor_id)
            frontier = next_frontier
            if not frontier:
                break
    return walk


def related_artifacts(
    store: TypedArtifactStore,
    *,
    artifact_id: str,
    version: int,
    session_allowlist: Iterable[str] | None,
    selected_ids: Collection[str] | None = None,
    access: MemoryAccess | None = None,
    mode: Literal["ordinary", "historical"] = "ordinary",
    now: float | None = None,
    memo: SourceValidationMemo | None = None,
    depth: int = DEFAULT_DEPTH,
    max_nodes: int = _MAX_NODES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    encoding: str = DEFAULT_ENCODING,
) -> dict[str, Any]:
    """MC03 §6.3 bounded authorized traversal from one seed artifact.

    `depth`/`max_nodes` clamp to the §6.3 hard caps (2, 32) regardless of a larger request.
    The root and every neighbor are decided by the shared decision under `access` (else
    the legacy `session_allowlist` form, where a neighbor must also share the root's
    effective owner), from fresh rows. Ordinary mode follows only edges recorded at the
    node's current version and keeps a neighbor only when it is usable as current at the
    edge's recorded version. A neighbor that fails is skipped before the node cap and the
    budget, so `complete=False` means only that the cap or the shared token/byte budget
    stopped traversal — never that something was denied, which is indistinguishable from
    "not linked at all".

    72-T03 R14: before returning, a final pass re-reads and re-decides the root and every
    kept node through a fresh read-only view with a fresh source memo; a node that now
    fails is dropped with every descendant reached only through it, and the sizes and
    completeness are recomputed from what remains.

    `mode="historical"` needs an access carrying historical authorization: it lists every
    visible neighbor over every edge, each with `usable_as_current`, `reason_codes` and
    `edge_version`, and the result carries `"mode": "historical", "actionable": False`.
    """
    if not isinstance(mode, str) or mode not in ("ordinary", "historical"):
        return _input_error("mode", "related mode must be 'ordinary' or 'historical'")
    if not _is_text(artifact_id):
        return _input_error("id", "id must be valid UTF-8 text")
    if not _is_int(version) or not sqlite_integer_in_range(version):
        return _input_error("version", "version must be a storable integer")
    for name, value in (
        ("depth", depth),
        ("max_nodes", max_nodes),
        ("max_tokens", max_tokens),
        ("max_bytes", max_bytes),
    ):
        if not _is_int(value):
            return _input_error(name, f"{name} must be an integer")
    missing = missing_root_result(encoding)
    if access is None:
        if mode == "historical":
            return missing
        access = MemoryAccess.legacy(store.project_root, session_allowlist)
    if not access.sources:
        return missing
    historical = mode == "historical"
    walk_args: dict[str, Any] = {
        "artifact_id": artifact_id,
        "version": version,
        "access": access,
        "historical": historical,
        "moment": time.time() if now is None else now,
        "depth": max(1, min(depth, _MAX_DEPTH)),
        "max_nodes": max(1, min(max_nodes, _MAX_NODES)),
        "max_tokens": max_tokens,
        "max_bytes": max_bytes,
        "encoding": encoding,
        "selected_ids": selected_ids,
    }
    first = _walk(
        store, memo=memo or SourceValidationMemo(), candidates=None, **walk_args
    )
    if first is None:
        return missing
    view, state = TypedArtifactStore.open_readonly_view(store.project_root)
    if view is None or state is not None:
        return missing
    try:
        final = _walk(
            view, memo=SourceValidationMemo(), candidates=first.eligible, **walk_args
        )
    finally:
        view.close()
    if final is None:
        return missing

    size_bytes, size_tokens = _measure_related(final.items, encoding)
    result: dict[str, Any] = {
        "code": "OK",
        "items": final.items,
        "complete": not final.truncated,
        "tokens": size_tokens,
        "bytes": size_bytes,
        "encoding": encoding,
    }
    if historical:
        result.update(mode="historical", actionable=False)
    return result
