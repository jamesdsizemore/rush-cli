"""MC03 §6.3 evidence relations: explicit versioned links with bounded, authorized traversal
(docs/phase-plans/MC03.md).

`add_relation()` atomically inserts one `memory_relations` row after checking both endpoints
exist as real `(artifact_id, artifact_version)` pairs and, for acyclic kinds (`supersedes`),
that the new edge wouldn't close a cycle. `related_artifacts()` walks that table breadth-first
from one seed, revalidating every node's authorization and endpoint-version currency before
including it — a denied or stale-version neighbor is silently dropped, never disclosed by ID
or count (§6.3: "Do not disclose denied neighbor IDs, counts or source names").

Both functions return a plain dict with a leading `"code"` key, mirroring `retrieval.py`'s
contract so `rush.tools.memory.MemoryTool` can map it onto `ToolResult.status` unchanged.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterable
from typing import Any

import tiktoken

from rush.memory.retrieval import (
    DEFAULT_ENCODING,
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_TOKENS,
)
from rush.memory.store import TypedArtifactStore

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

# §6.3: "`related` defaults to depth 1, maximum depth 2 and 32 nodes."
DEFAULT_DEPTH = 1
_MAX_DEPTH = 2
_MAX_NODES = 32
# §6.3: "`supersedes` must remain acyclic." No other kind is direction-constrained this way.
_ACYCLIC_KINDS = frozenset({"supersedes"})


def _connect(store: TypedArtifactStore) -> sqlite3.Connection:
    conn = sqlite3.connect(str(store.db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _endpoint_exists(conn: sqlite3.Connection, artifact_id: str, version: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM memory_artifact_versions WHERE artifact_id = ? AND artifact_version = ?",
        (artifact_id, version),
    ).fetchone()
    return row is not None


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


def add_relation(
    store: TypedArtifactStore,
    *,
    source_id: str,
    source_version: int,
    target_id: str,
    target_version: int,
    kind: str,
    origin_ref: str | None = None,
) -> dict[str, Any]:
    """MC03 §6.3: atomically inserts one versioned evidence edge. Returns `{"code": ...}`
    (never raises for a business-rule rejection) with `"OK"` plus the new row's `sequence` on
    success, or `"E_INPUT"` with a `message` for an unsupported kind, an endpoint that isn't a
    real stored `(id, version)` pair, or a `supersedes` edge that would close a cycle. The
    whole check-then-insert sequence runs inside one `BEGIN IMMEDIATE` transaction, so a
    rejected edge (e.g. the inverse of an existing `supersedes` pair) never leaves a partial
    row — nothing is written unless every check passes.
    """
    if kind not in RELATION_KINDS:
        return {"code": "E_INPUT", "message": f"unsupported relation kind: {kind!r}"}
    with _connect(store) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for endpoint_id, endpoint_version in (
            (source_id, source_version),
            (target_id, target_version),
        ):
            if not _endpoint_exists(conn, endpoint_id, endpoint_version):
                return {
                    "code": "E_INPUT",
                    "message": f"unknown endpoint {endpoint_id!r}@{endpoint_version}",
                }
        if kind in _ACYCLIC_KINDS and _supersedes_cycle_exists(
            conn, source_id, target_id
        ):
            return {
                "code": "E_INPUT",
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
        sequence = cur.lastrowid
    return {"code": "OK", "sequence": sequence}


def _measure_related(items: list[dict[str, Any]], encoding: str) -> tuple[int, int]:
    text = json.dumps({"items": items}, ensure_ascii=False, separators=(",", ":"))
    return len(text.encode("utf-8")), len(tiktoken.get_encoding(encoding).encode(text))


def related_artifacts(
    store: TypedArtifactStore,
    *,
    artifact_id: str,
    version: int,
    session_allowlist: Iterable[str] | None,
    depth: int = DEFAULT_DEPTH,
    max_nodes: int = _MAX_NODES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    encoding: str = DEFAULT_ENCODING,
) -> dict[str, Any]:
    """MC03 §6.3 bounded authorized traversal from one seed artifact.

    `depth`/`max_nodes` clamp to the §6.3 hard caps (2, 32) regardless of a larger request.
    Every discovered neighbor is revalidated against `session_allowlist` and its edge's
    recorded endpoint version against the neighbor's *current* version (`get_current()`,
    never a snapshot) — a denied, missing, or version-changed neighbor is dropped silently, no
    ID/count/source disclosed for it, matching `expand_artifact()`'s identical-body denial
    precedent (§9.0). `complete=False` means the node cap or the shared token/byte budget
    stopped traversal before every reachable neighbor within `depth` was included — never that
    something was denied or invalidated, which is indistinguishable from "not linked at all".
    """
    allowed_sources = set(session_allowlist or ())
    depth = max(1, min(depth, _MAX_DEPTH))
    max_nodes = max(1, min(max_nodes, _MAX_NODES))
    root = store.get_current(artifact_id)
    if (
        root is None
        or root.artifact_version != version
        or root.source not in allowed_sources
    ):
        return {
            "code": "E_NOT_VISIBLE",
            "items": [],
            "complete": True,
            "tokens": 0,
            "bytes": 0,
            "encoding": encoding,
        }

    items: list[dict[str, Any]] = []
    visited = {artifact_id}
    frontier = [artifact_id]
    truncated = False
    with _connect(store) as conn:
        for _level in range(depth):
            next_frontier: list[str] = []
            for node_id in frontier:
                edges = conn.execute(
                    "SELECT source_id, source_version, target_id, target_version, kind "
                    "FROM memory_relations WHERE source_id = ? OR target_id = ?",
                    (node_id, node_id),
                ).fetchall()
                for edge in edges:
                    if edge["source_id"] == node_id:
                        neighbor_id = edge["target_id"]
                        neighbor_version = edge["target_version"]
                        direction = "outgoing"
                    else:
                        neighbor_id = edge["source_id"]
                        neighbor_version = edge["source_version"]
                        direction = "incoming"
                    if neighbor_id in visited:
                        continue
                    if len(visited) >= max_nodes:
                        truncated = True
                        continue
                    current = store.get_current(neighbor_id)
                    if current is None or current.source not in allowed_sources:
                        continue
                    if current.artifact_version != neighbor_version:
                        continue
                    candidate = {
                        "id": neighbor_id,
                        "version": current.artifact_version,
                        "kind": edge["kind"],
                        "direction": direction,
                    }
                    trial_bytes, trial_tokens = _measure_related(
                        [*items, candidate], encoding
                    )
                    if trial_bytes > max_bytes or trial_tokens > max_tokens:
                        truncated = True
                        continue
                    visited.add(neighbor_id)
                    items.append(candidate)
                    next_frontier.append(neighbor_id)
            frontier = next_frontier
            if not frontier:
                break

    size_bytes, size_tokens = _measure_related(items, encoding)
    return {
        "code": "OK",
        "items": items,
        "complete": not truncated,
        "tokens": size_tokens,
        "bytes": size_bytes,
        "encoding": encoding,
    }
