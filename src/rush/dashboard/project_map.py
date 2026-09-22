"""Phase 66 P66-02: project map data projection (plan section 3.5).

`build_project_map` projects an already-scoped project snapshot (files,
findings, memories, agents -- see `tests/fixtures/dashboard/project_a.json`)
into typed node/edge graph data for the browser map renderer
(`project_map.js`). It never rescans the filesystem and never derives a
relationship beyond the recorded fields below:

- ``contains``    project -> file, from the recorded file path list.
- ``reports``     finding -> file, from the finding's own ``path`` field.
- ``cites``       memory -> file|finding, from the memory's own ``cites`` list.
- ``assigned_to`` agent -> finding, from the agent's own ``assigned_to`` list.

Above the hard render bound (200 nodes / 400 edges) the full evidence
inventory is never dropped: it is exposed instead as paginated ``group``
nodes (`expand_group`), one per top-level path segment.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from typing import Any

RENDER_NODE_LIMIT = 200
RENDER_EDGE_LIMIT = 400
GROUP_PAGE_SIZE = 100

# Polar layout sectors (spec 3.5), degrees, clockwise from (0,0).
_SECTORS: dict[str, tuple[float, float]] = {
    "file": (-150.0, -30.0),
    "directory": (-150.0, -30.0),
    "finding": (-30.0, 60.0),
    "memory": (60.0, 150.0),
    "agent": (150.0, 210.0),
}
_OVERVIEW_GROUP_RADIUS = 180.0
_OVERVIEW_MEMBER_RADIUS = 340.0


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def _file_id(path: str) -> str:
    digest = hashlib.sha256(_normalize_path(path).encode("utf-8")).hexdigest()
    return f"file:{digest}"


class CursorRejected(ValueError):
    """P69-03t: raised when a cursor's embedded `(project_id,
    source_identity, sequence, filter_hash, view_id)` tuple -- or, for a
    group/group-edge cursor, its own scope name -- doesn't match the request
    it's being replayed against (a different project, a rescan that bumped
    `sequence`, different active filters, or a malformed/corrupt cursor
    string). `server.py` turns this into an HTTP 409, never a silent
    fallback to offset 0."""


def _filter_hash(
    *,
    node_types: tuple[str, ...],
    severity: tuple[str, ...],
    status: tuple[str, ...],
    query: str,
) -> str:
    raw = json.dumps(
        {
            "node_types": sorted(node_types),
            "severity": sorted(severity),
            "status": sorted(status),
            "query": query,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _cursor_tuple(
    *,
    project_id: str,
    source_identity: str,
    sequence: int,
    filter_hash: str,
    view_id: tuple[Any, ...],
) -> dict[str, Any]:
    """P69-03t: the exact tuple a map/group cursor is bound to. `view_id` is
    `("current",)` for the live map, or `("run", run_id, attempt_id)` for a
    caller-selected historical run (P69-03r: pinned to that run's exact
    attempt, never bare `run_id` -- a later resume of the same `run_id`
    mints a new attempt and must not invalidate or change an already-issued
    historical cursor)."""
    return {
        "project_id": project_id,
        "source_identity": source_identity,
        "sequence": sequence,
        "filter_hash": filter_hash,
        "view_id": list(view_id),
    }


def _cursor_encode(payload: dict[str, Any], *, tuple_key: dict[str, Any]) -> str:
    raw = json.dumps(
        {"payload": payload, "key": tuple_key}, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _cursor_decode(cursor: str, *, tuple_key: dict[str, Any]) -> dict[str, Any]:
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        decoded = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, UnicodeDecodeError, TypeError) as exc:
        raise CursorRejected("malformed map cursor") from exc
    if not isinstance(decoded, dict) or decoded.get("key") != tuple_key:
        raise CursorRejected(
            "cursor was issued under a different project/source/sequence/filter/view"
        )
    payload = decoded.get("payload")
    return payload if isinstance(payload, dict) else {}


def _node(
    *,
    node_id: str,
    kind: str,
    label: str,
    artifact_id: str | None,
    path: str | None,
    status: str | None,
    scope: str | None,
    source_identity: str,
    count: int | None,
    expandable: bool,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "kind": kind,
        "label": label,
        "artifact_id": artifact_id,
        "path": path,
        "status": status,
        "scope": scope,
        "source_identity": source_identity,
        "count": count,
        "expandable": expandable,
    }


def _edge(
    *,
    edge_id: str,
    source: str,
    target: str,
    relation: str,
    source_identity: str,
    count: int | None = None,
    expandable: bool = False,
    cursor: str | None = None,
) -> dict[str, Any]:
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "relation": relation,
        "evidence_ids": [],
        "source_identity": source_identity,
        "count": count,
        "expandable": expandable,
        "cursor": cursor,
    }


def _build_full_graph(
    snapshot: dict[str, Any], source_identity: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    project_id = snapshot["project_id"]
    project_node_id = f"project:{project_id}"

    nodes: list[dict[str, Any]] = [
        _node(
            node_id=project_node_id,
            kind="project",
            label=project_id,
            artifact_id=project_id,
            path=None,
            status=None,
            scope=None,
            source_identity=source_identity,
            count=None,
            expandable=False,
        )
    ]
    edges: list[dict[str, Any]] = []

    file_ids_by_path: dict[str, str] = {}
    for entry in snapshot.get("files", []):
        path = entry["path"]
        node_id = _file_id(path)
        file_ids_by_path[path] = node_id
        nodes.append(
            _node(
                node_id=node_id,
                kind="file",
                label=path.rsplit("/", 1)[-1],
                artifact_id=path,
                path=path,
                status=None,
                scope=None,
                source_identity=source_identity,
                count=None,
                expandable=False,
            )
        )
        edges.append(
            _edge(
                edge_id=f"edge:contains:{project_node_id}:{node_id}",
                source=project_node_id,
                target=node_id,
                relation="contains",
                source_identity=source_identity,
            )
        )

    finding_ids_by_original: dict[str, str] = {}
    for entry in snapshot.get("findings", []):
        original_id = entry["id"]
        node_id = f"finding:{original_id}"
        finding_ids_by_original[original_id] = node_id
        path = entry.get("path")
        nodes.append(
            _node(
                node_id=node_id,
                kind="finding",
                label=f"{path}:{entry.get('line')}" if path else original_id,
                artifact_id=original_id,
                path=path,
                status=entry.get("severity"),
                scope=None,
                source_identity=source_identity,
                count=None,
                expandable=False,
            )
        )
        target_id = file_ids_by_path.get(path) if path else None
        if target_id is not None:
            edges.append(
                _edge(
                    edge_id=f"edge:reports:{node_id}:{target_id}",
                    source=node_id,
                    target=target_id,
                    relation="reports",
                    source_identity=source_identity,
                )
            )

    for entry in snapshot.get("memories", []):
        original_id = entry["id"]
        node_id = f"memory:{original_id}"
        nodes.append(
            _node(
                node_id=node_id,
                kind="memory",
                label=original_id,
                artifact_id=original_id,
                path=None,
                status=None,
                scope=None,
                source_identity=source_identity,
                count=None,
                expandable=False,
            )
        )
        for cite in entry.get("cites", []):
            target_id = file_ids_by_path.get(cite) or finding_ids_by_original.get(cite)
            if target_id is None:
                continue
            edges.append(
                _edge(
                    edge_id=f"edge:cites:{node_id}:{target_id}",
                    source=node_id,
                    target=target_id,
                    relation="cites",
                    source_identity=source_identity,
                )
            )

    for entry in snapshot.get("agents", []):
        original_id = entry["id"]
        node_id = f"agent:{original_id}"
        assigned_to = entry.get("assigned_to", [])
        nodes.append(
            _node(
                node_id=node_id,
                kind="agent",
                label=original_id,
                artifact_id=original_id,
                path=None,
                status="unlinked" if not assigned_to else None,
                scope=None,
                source_identity=source_identity,
                count=None,
                expandable=False,
            )
        )
        for assigned in assigned_to:
            target_id = finding_ids_by_original.get(assigned)
            if target_id is None:
                continue
            edges.append(
                _edge(
                    edge_id=f"edge:assigned_to:{node_id}:{target_id}",
                    source=node_id,
                    target=target_id,
                    relation="assigned_to",
                    source_identity=source_identity,
                )
            )

    return nodes, edges


def _apply_filters(
    nodes: list[dict[str, Any]],
    *,
    node_types: tuple[str, ...],
    severity: tuple[str, ...],
    status: tuple[str, ...],
    query: str,
) -> list[dict[str, Any]]:
    query = query[:256].strip().lower()
    result = []
    for node in nodes:
        if node["kind"] == "project":
            result.append(node)
            continue
        if node_types and node["kind"] not in node_types:
            continue
        if severity and node["kind"] == "finding" and node["status"] not in severity:
            continue
        if status and node["status"] not in status:
            continue
        if query:
            haystack = " ".join(
                str(node[field] or "") for field in ("id", "label", "path")
            ).lower()
            if query not in haystack:
                continue
        result.append(node)
    return result


def _focus_neighborhood(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]], center_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    neighbor_ids = {center_id}
    neighbor_edges = []
    for edge in edges:
        if edge["source"] == center_id or edge["target"] == center_id:
            neighbor_edges.append(edge)
            neighbor_ids.add(edge["source"])
            neighbor_ids.add(edge["target"])
    neighbor_nodes = [n for n in nodes if n["id"] in neighbor_ids]
    return neighbor_nodes, neighbor_edges


def _sort_key(node: dict[str, Any]) -> tuple[str, str]:
    return (node.get("path") or "", node["id"])


def _group_page_membership(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    source_identity: str,
    offset: int,
    tuple_key: dict[str, Any],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    set[str],
    set[str],
    dict[str, str],
    bool,
]:
    """Shared by `_grouped_overview` (rendering) and `expand_group_edge`'s
    overflow branch (M05 bullet 3): the exact same node-grouping and
    page-window computation, so an overflow selector's `page_offset` can
    reconstruct precisely which groups/nodes were visible when that overflow
    bucket was minted -- same input always yields the same grouping, so
    recomputing here from `(nodes, edges, offset)` alone is exact, not an
    approximation. `edges` is accepted for signature symmetry with callers
    but not used directly -- membership only depends on nodes/offset."""
    project_node = next(n for n in nodes if n["kind"] == "project")
    groupable = [n for n in nodes if n["kind"] != "project" and n.get("path")]
    ungroupable = [n for n in nodes if n["kind"] != "project" and not n.get("path")]

    buckets: dict[str, list[dict[str, Any]]] = {}
    for node in groupable:
        top = _normalize_path(node["path"]).split("/", 1)[0] or "(root)"
        buckets.setdefault(top, []).append(node)

    # P69-03q: every grouped-away node's own group id, so a relationship
    # edge whose endpoint got hidden behind a group can be re-homed onto
    # that group instead of silently dropped.
    member_group_id: dict[str, str] = {}

    group_nodes: list[dict[str, Any]] = []
    groups_meta: list[dict[str, Any]] = []
    for top, members in sorted(buckets.items()):
        group_id = f"group:{top}"
        for member in members:
            member_group_id[member["id"]] = group_id
        group_nodes.append(
            _node(
                node_id=group_id,
                kind="group",
                label=top,
                artifact_id=None,
                path=top,
                status=None,
                scope=None,
                source_identity=source_identity,
                count=len(members),
                expandable=True,
            )
        )
        groups_meta.append(
            {
                "id": group_id,
                "kind": "group",
                "label": top,
                "member_count": len(members),
                "cursor": _cursor_encode(
                    {"group": group_id, "offset": 0}, tuple_key=tuple_key
                ),
            }
        )

    remaining_budget = max(RENDER_NODE_LIMIT - 1 - len(group_nodes), 0)
    if len(ungroupable) > remaining_budget:
        kind_buckets: dict[str, list[dict[str, Any]]] = {}
        for node in ungroupable:
            kind_buckets.setdefault(node["kind"], []).append(node)
        extra_group_nodes = []
        for kind, members in sorted(kind_buckets.items()):
            group_id = f"group:{kind}"
            for member in members:
                member_group_id[member["id"]] = group_id
            extra_group_nodes.append(
                _node(
                    node_id=group_id,
                    kind="group",
                    label=kind,
                    artifact_id=None,
                    path=None,
                    status=None,
                    scope=None,
                    source_identity=source_identity,
                    count=len(members),
                    expandable=True,
                )
            )
            groups_meta.append(
                {
                    "id": group_id,
                    "kind": "group",
                    "label": kind,
                    "member_count": len(members),
                    "cursor": _cursor_encode(
                        {"group": group_id, "offset": 0}, tuple_key=tuple_key
                    ),
                }
            )
        ungroupable_nodes = extra_group_nodes
    else:
        ungroupable_nodes = ungroupable

    # Group/ungroupable-as-groups nodes are the paginated portion of the
    # overview -- the project root is always present regardless of page.
    rest = [*group_nodes, *ungroupable_nodes]
    page_capacity = max(RENDER_NODE_LIMIT - 1, 0)
    page = rest[offset : offset + page_capacity]
    has_more = offset + page_capacity < len(rest)
    page_ids = {n["id"] for n in page}

    visible_nodes = [project_node, *page]
    visible_ids = {n["id"] for n in visible_nodes}
    return (
        project_node,
        group_nodes,
        groups_meta,
        page,
        page_ids,
        visible_ids,
        member_group_id,
        has_more,
    )


def _relation_overflow_members(
    edges: list[dict[str, Any]],
    *,
    visible_ids: set[str],
    page_ids: set[str],
    member_group_id: dict[str, str],
    relation: str,
) -> list[dict[str, Any]]:
    """The exact raw edges a `by_relation` overflow count (M05 bullet 3)
    aggregates -- same inclusion test `_grouped_overview` uses to build
    `summary_counts`, just not bucketed by (source, target), so every one of
    them stays individually reachable through `expand_group_edge`."""
    matched = []
    for e in edges:
        if e["relation"] != relation:
            continue
        if e["source"] in visible_ids and e["target"] in visible_ids:
            continue
        resolved_source = (
            e["source"]
            if e["source"] in visible_ids
            else member_group_id.get(e["source"])
        )
        resolved_target = (
            e["target"]
            if e["target"] in visible_ids
            else member_group_id.get(e["target"])
        )
        if resolved_source is None or resolved_target is None:
            continue
        if resolved_source.startswith("group:") and resolved_source not in page_ids:
            continue
        if resolved_target.startswith("group:") and resolved_target not in page_ids:
            continue
        matched.append(e)
    return matched


def _grouped_overview(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    source_identity: str,
    offset: int = 0,
    tuple_key: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], bool]:
    (
        project_node,
        group_nodes,
        groups_meta,
        page,
        page_ids,
        visible_ids,
        member_group_id,
        has_more,
    ) = _group_page_membership(
        nodes,
        edges,
        source_identity=source_identity,
        offset=offset,
        tuple_key=tuple_key,
    )
    visible_nodes = [project_node, *page]
    contains_edges = [
        _edge(
            edge_id=f"edge:contains:{project_node['id']}:{group['id']}",
            source=project_node["id"],
            target=group["id"],
            relation="contains",
            source_identity=source_identity,
        )
        for group in group_nodes
        if group["id"] in page_ids
    ]
    kept_edges = [
        e for e in edges if e["source"] in visible_ids and e["target"] in visible_ids
    ]

    # P69-03q: group-edge budget. A `reports`/`cites`/`assigned_to` edge
    # whose endpoint was hidden behind grouping is never silently dropped --
    # it's re-homed onto that endpoint's group and counted, one summary edge
    # per (resolved source, resolved target, relation) triple, never one
    # edge per individual dropped relationship (which is exactly what let
    # summary edges themselves exceed the 400-edge bound on a graph with
    # many groups).
    summary_counts: dict[tuple[str, str, str], int] = {}
    for e in edges:
        if e["source"] in visible_ids and e["target"] in visible_ids:
            continue
        resolved_source = (
            e["source"]
            if e["source"] in visible_ids
            else member_group_id.get(e["source"])
        )
        resolved_target = (
            e["target"]
            if e["target"] in visible_ids
            else member_group_id.get(e["target"])
        )
        if resolved_source is None or resolved_target is None:
            continue
        # M05 bullet 1: both endpoints collapsing into the same group is no
        # longer a dropped relationship -- it becomes an expandable counted
        # self-summary on that group (`expand_group_edge`'s own bucket
        # matching already resolves a self-loop selector correctly: both
        # the source and target bucket checks compare against the same
        # `src`/`tgt` value). Previously every one of the 101 file<->finding
        # relationships collapsing into one directory group vanished here.
        if resolved_source.startswith("group:") and resolved_source not in page_ids:
            continue
        if resolved_target.startswith("group:") and resolved_target not in page_ids:
            continue
        key = (resolved_source, resolved_target, e["relation"])
        summary_counts[key] = summary_counts.get(key, 0) + 1

    summary_edges = [
        _edge(
            edge_id=f"edge:{relation}:{src}:{tgt}:summary",
            source=src,
            target=tgt,
            relation=relation,
            source_identity=source_identity,
            count=count,
            expandable=True,
            cursor=_cursor_encode(
                {
                    "edge": f"edge:{relation}:{src}:{tgt}:summary",
                    "relation": relation,
                    "source": src,
                    "target": tgt,
                    "offset": 0,
                    "page_offset": offset,
                },
                tuple_key=tuple_key,
            ),
        )
        for (src, tgt, relation), count in sorted(summary_counts.items())
    ]

    visible_edges = contains_edges + kept_edges + summary_edges
    if len(visible_edges) > RENDER_EDGE_LIMIT:
        # ponytail: even one summary edge per (group, relation) pair can
        # still exceed the bound on a graph with very many groups times
        # relation types. Collapse further to one edge per relation type,
        # project-wide, sacrificing per-group granularity -- still counted
        # and expandable, never a silent drop. Ceiling: a genuinely
        # multi-level drill-down (collapse groups of groups) is real future
        # work if this path is ever hit in practice.
        by_relation: dict[str, int] = {}
        for (_src, _tgt, relation), count in summary_counts.items():
            by_relation[relation] = by_relation.get(relation, 0) + count
        collapsed_edges = [
            _edge(
                edge_id=f"edge:{relation}:{project_node['id']}:overflow:summary",
                source=project_node["id"],
                target=project_node["id"],
                relation=relation,
                source_identity=source_identity,
                count=count,
                expandable=True,
                cursor=_cursor_encode(
                    {
                        "edge": f"edge:{relation}:{project_node['id']}:overflow:summary",
                        "relation": relation,
                        "source": project_node["id"],
                        "target": project_node["id"],
                        "offset": 0,
                        "page_offset": offset,
                        "overflow": True,
                    },
                    tuple_key=tuple_key,
                ),
            )
            for relation, count in sorted(by_relation.items())
        ]
        visible_edges = (contains_edges + kept_edges + collapsed_edges)[
            :RENDER_EDGE_LIMIT
        ]

    visible_groups_meta = [g for g in groups_meta if g["id"] in page_ids]

    return (
        visible_nodes[:RENDER_NODE_LIMIT],
        visible_edges[:RENDER_EDGE_LIMIT],
        visible_groups_meta,
        has_more,
    )


def build_project_map(
    snapshot: dict[str, Any],
    *,
    run_id: str | None = None,
    attempt_id: str | None = None,
    node_types: tuple[str, ...] = (),
    severity: tuple[str, ...] = (),
    status: tuple[str, ...] = (),
    query: str = "",
    center_id: str | None = None,
    cursor: str | None = None,
    limit: int = RENDER_NODE_LIMIT,
) -> dict[str, Any]:
    """Project a scoped snapshot into typed node/edge map data (spec 3.5).
    `run_id`/`attempt_id` (P69-03r) only affect the cursor's `view_id`
    binding and the echoed identity fields -- the caller is responsible for
    passing a `snapshot` already resolved to that specific historical
    attempt (frozen memory/agent data included, per P69-03s), never the
    live current snapshot."""
    project_id = snapshot["project_id"]
    source_identity = snapshot.get("source_identity", project_id)
    sequence = snapshot.get("sequence", 1)
    # P69-03t: cursor/cache tuple -- (project_id, source_identity, sequence,
    # filter_hash, view_id). `view_id` is `("current",)` for the live map
    # or `("run", run_id, attempt_id)` for a caller-selected historical run.
    filter_hash = _filter_hash(
        node_types=node_types, severity=severity, status=status, query=query
    )
    view_id: tuple[Any, ...] = (
        ("current",) if run_id is None else ("run", run_id, attempt_id)
    )
    tuple_key = _cursor_tuple(
        project_id=project_id,
        source_identity=source_identity,
        sequence=sequence,
        filter_hash=filter_hash,
        view_id=view_id,
    )

    all_nodes, all_edges = _build_full_graph(snapshot, source_identity)
    total_nodes = len(all_nodes)
    total_edges = len(all_edges)

    filtered_nodes = _apply_filters(
        all_nodes, node_types=node_types, severity=severity, status=status, query=query
    )
    filtered_ids = {n["id"] for n in filtered_nodes}
    filtered_edges = [
        e
        for e in all_edges
        if e["source"] in filtered_ids and e["target"] in filtered_ids
    ]

    if center_id is not None:
        filtered_nodes, filtered_edges = _focus_neighborhood(
            filtered_nodes, filtered_edges, center_id
        )

    render_limit = min(limit, RENDER_NODE_LIMIT)
    next_cursor: str | None = None
    if len(filtered_nodes) <= render_limit and len(filtered_edges) <= RENDER_EDGE_LIMIT:
        nodes = sorted(filtered_nodes, key=_sort_key)
        edges = sorted(filtered_edges, key=lambda e: e["id"])
        groups: list[dict[str, Any]] = []
    else:
        offset = 0
        if cursor:
            offset = int(
                _cursor_decode(cursor, tuple_key=tuple_key).get("overview_offset", 0)
            )
        nodes, edges, groups, has_more = _grouped_overview(
            filtered_nodes,
            filtered_edges,
            source_identity=source_identity,
            offset=offset,
            tuple_key=tuple_key,
        )
        if has_more:
            next_offset = offset + max(RENDER_NODE_LIMIT - 1, 0)
            next_cursor = _cursor_encode(
                {"overview_offset": next_offset}, tuple_key=tuple_key
            )

    return {
        "schema_version": 1,
        "project_id": project_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "source_identity": source_identity,
        "sequence": sequence,
        "nodes": nodes,
        "edges": edges,
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "next_cursor": next_cursor,
        "groups": groups,
    }


def expand_group(
    snapshot: dict[str, Any],
    group_id: str,
    *,
    node_types: tuple[str, ...] = (),
    severity: tuple[str, ...] = (),
    status: tuple[str, ...] = (),
    query: str = "",
    cursor: str | None = None,
    page_size: int = GROUP_PAGE_SIZE,
    view_id: tuple[Any, ...] = ("current",),
) -> dict[str, Any]:
    """Page through a group node's full membership (spec 3.5: "server-
    paginated members (100 per page)"). Loop until ``next_cursor`` is
    ``None`` to enumerate every underlying evidence ID the group represents.

    ``node_types``/``severity``/``status``/``query`` MUST be the exact same
    active filters passed to the ``build_project_map`` call that produced
    this group's ``member_count`` -- membership is derived from the same
    ``_apply_filters`` pass so ``member_count`` never diverges from what this
    function actually returns for that group under those filters.
    """
    project_id = snapshot["project_id"]
    source_identity = snapshot.get("source_identity", project_id)
    sequence = snapshot.get("sequence", 1)
    filter_hash = _filter_hash(
        node_types=node_types, severity=severity, status=status, query=query
    )
    tuple_key = _cursor_tuple(
        project_id=project_id,
        source_identity=source_identity,
        sequence=sequence,
        filter_hash=filter_hash,
        view_id=view_id,
    )
    all_nodes, _all_edges = _build_full_graph(snapshot, source_identity)
    filtered_nodes = _apply_filters(
        all_nodes, node_types=node_types, severity=severity, status=status, query=query
    )

    top = group_id.removeprefix("group:")
    if top in ("file", "finding", "memory", "agent"):
        members = [n for n in filtered_nodes if n["kind"] == top]
    else:
        members = [
            n
            for n in filtered_nodes
            if n.get("path") and _normalize_path(n["path"]).split("/", 1)[0] == top
        ]
    members = sorted(members, key=_sort_key)

    offset = 0
    if cursor:
        decoded = _cursor_decode(cursor, tuple_key=tuple_key)
        # P69-03t: a cursor minted for a *different* group must never be
        # replayed here -- two groups sharing the same project/source/
        # sequence/filter tuple would otherwise collide on one cursor space.
        if decoded.get("group") != group_id:
            raise CursorRejected(f"cursor does not belong to group {group_id!r}")
        offset = int(decoded.get("offset", 0))
    page = members[offset : offset + page_size]
    next_offset = offset + page_size
    next_cursor = (
        _cursor_encode({"group": group_id, "offset": next_offset}, tuple_key=tuple_key)
        if next_offset < len(members)
        else None
    )
    return {
        "schema_version": 1,
        "group_id": group_id,
        "members": page,
        "next_cursor": next_cursor,
        "total": len(members),
    }


def expand_group_edge(
    snapshot: dict[str, Any],
    edge_id: str,
    *,
    node_types: tuple[str, ...] = (),
    severity: tuple[str, ...] = (),
    status: tuple[str, ...] = (),
    query: str = "",
    cursor: str,
    page_size: int = GROUP_PAGE_SIZE,
    view_id: tuple[Any, ...] = ("current",),
) -> dict[str, Any]:
    """P69-03q: page through the real, individual relationships a summary
    group-edge (`_grouped_overview`'s counted, expandable group-edge)
    collapsed -- reuses the exact member-pagination cursor contract
    `expand_group` uses, so every relationship a group-edge counts stays
    reachable, never silently dropped. `cursor` is required: it's always the
    summary edge's own `cursor` field (or a previous page's `next_cursor`),
    which is what actually carries the `(relation, source, target)` triple
    this function pages through -- `edge_id` alone is not enough to recover
    which real nodes were collapsed together."""
    project_id = snapshot["project_id"]
    source_identity = snapshot.get("source_identity", project_id)
    sequence = snapshot.get("sequence", 1)
    filter_hash = _filter_hash(
        node_types=node_types, severity=severity, status=status, query=query
    )
    tuple_key = _cursor_tuple(
        project_id=project_id,
        source_identity=source_identity,
        sequence=sequence,
        filter_hash=filter_hash,
        view_id=view_id,
    )
    decoded = _cursor_decode(cursor, tuple_key=tuple_key)
    if decoded.get("edge") != edge_id:
        raise CursorRejected(f"cursor does not belong to group-edge {edge_id!r}")
    relation = decoded.get("relation")
    src = decoded.get("source")
    tgt = decoded.get("target")
    offset = int(decoded.get("offset", 0))
    page_offset = int(decoded.get("page_offset", 0))
    overflow = bool(decoded.get("overflow", False))

    all_nodes, all_edges = _build_full_graph(snapshot, source_identity)
    filtered_nodes = _apply_filters(
        all_nodes, node_types=node_types, severity=severity, status=status, query=query
    )
    filtered_ids = {n["id"] for n in filtered_nodes}
    filtered_edges = [
        e
        for e in all_edges
        if e["source"] in filtered_ids and e["target"] in filtered_ids
    ]

    if overflow:
        # M05 bullet 3: an overflow selector's source/target are both the
        # project node -- there is no literal/group pair to bucket-match
        # against. Rebuild the exact page context the overflow bucket was
        # minted under (`page_offset`) and collect every real edge that
        # page's relation-level budget rolled up, instead of a selector that
        # can never match anything.
        (
            _project_node,
            _group_nodes,
            _groups_meta,
            _page,
            page_ids,
            visible_ids,
            member_group_id,
            _has_more,
        ) = _group_page_membership(
            filtered_nodes,
            filtered_edges,
            source_identity=source_identity,
            offset=page_offset,
            tuple_key=tuple_key,
        )
        matches = _relation_overflow_members(
            filtered_edges,
            visible_ids=visible_ids,
            page_ids=page_ids,
            member_group_id=member_group_id,
            relation=relation,
        )
    else:
        nodes_by_id = {n["id"]: n for n in filtered_nodes}

        def _bucket(node_id: str) -> str:
            node = nodes_by_id.get(node_id)
            if node is None:
                return node_id
            if node.get("path"):
                top = _normalize_path(node["path"]).split("/", 1)[0] or "(root)"
                return f"group:{top}"
            return f"group:{node['kind']}"

        matches = [
            e
            for e in filtered_edges
            if e["relation"] == relation
            and (e["source"] if e["source"] == src else _bucket(e["source"])) == src
            and (e["target"] if e["target"] == tgt else _bucket(e["target"])) == tgt
        ]
    matches = sorted(matches, key=lambda e: e["id"])

    page = matches[offset : offset + page_size]
    next_offset = offset + page_size
    next_payload: dict[str, Any] = {
        "edge": edge_id,
        "relation": relation,
        "source": src,
        "target": tgt,
        "offset": next_offset,
        "page_offset": page_offset,
    }
    if overflow:
        next_payload["overflow"] = True
    next_cursor = (
        _cursor_encode(next_payload, tuple_key=tuple_key)
        if next_offset < len(matches)
        else None
    )
    return {
        "schema_version": 1,
        "edge_id": edge_id,
        "relation": relation,
        "members": page,
        "next_cursor": next_cursor,
        "total": len(matches),
    }


def compute_layout(nodes: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    """Deterministic polar overview layout (spec 3.5): project at (0,0),
    kind sectors clockwise, each sector sorted by normalized path then
    stable ID, ``angle = sector_start + (index+.5)*sector_width/count``.
    Returns ``{node_id: (x, y)}``; same input always yields identical output
    (no randomness, no iterative physics, no ordering dependence beyond the
    input list's own contents)."""
    positions: dict[str, tuple[float, float]] = {}
    by_sector: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        if node["kind"] == "project":
            positions[node["id"]] = (0.0, 0.0)
            continue
        sector_kind = node["kind"] if node["kind"] in _SECTORS else "file"
        by_sector.setdefault(sector_kind, []).append(node)

    for sector_kind, members in by_sector.items():
        start, end = _SECTORS[sector_kind]
        width = end - start
        ordered = sorted(members, key=_sort_key)
        count = len(ordered)
        radius = (
            _OVERVIEW_GROUP_RADIUS
            if any(n["kind"] == "group" for n in ordered)
            else _OVERVIEW_MEMBER_RADIUS
        )
        for index, node in enumerate(ordered):
            angle_deg = start + (index + 0.5) * width / count
            angle_rad = math.radians(angle_deg)
            positions[node["id"]] = (
                radius * math.cos(angle_rad),
                radius * math.sin(angle_rad),
            )

    return positions


__all__ = [
    "GROUP_PAGE_SIZE",
    "RENDER_EDGE_LIMIT",
    "RENDER_NODE_LIMIT",
    "CursorRejected",
    "build_project_map",
    "compute_layout",
    "expand_group",
    "expand_group_edge",
]
