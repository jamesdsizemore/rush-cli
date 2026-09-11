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


def _cursor_encode(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _cursor_decode(cursor: str) -> dict[str, Any]:
    padded = cursor + "=" * (-len(cursor) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))


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
    *, edge_id: str, source: str, target: str, relation: str, source_identity: str
) -> dict[str, Any]:
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "relation": relation,
        "evidence_ids": [],
        "source_identity": source_identity,
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


def _grouped_overview(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    source_identity: str,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], bool]:
    project_node = next(n for n in nodes if n["kind"] == "project")
    groupable = [n for n in nodes if n["kind"] != "project" and n.get("path")]
    ungroupable = [n for n in nodes if n["kind"] != "project" and not n.get("path")]

    buckets: dict[str, list[dict[str, Any]]] = {}
    for node in groupable:
        top = _normalize_path(node["path"]).split("/", 1)[0] or "(root)"
        buckets.setdefault(top, []).append(node)

    group_nodes: list[dict[str, Any]] = []
    groups_meta: list[dict[str, Any]] = []
    for top, members in sorted(buckets.items()):
        group_id = f"group:{top}"
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
                "cursor": _cursor_encode({"group": group_id, "offset": 0}),
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
                    "cursor": _cursor_encode({"group": group_id, "offset": 0}),
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
    visible_edges = contains_edges + kept_edges
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
    node_types: tuple[str, ...] = (),
    severity: tuple[str, ...] = (),
    status: tuple[str, ...] = (),
    query: str = "",
    center_id: str | None = None,
    cursor: str | None = None,
    limit: int = RENDER_NODE_LIMIT,
) -> dict[str, Any]:
    """Project a scoped snapshot into typed node/edge map data (spec 3.5)."""
    project_id = snapshot["project_id"]
    source_identity = snapshot.get("source_identity", project_id)
    sequence = snapshot.get("sequence", 1)

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
            offset = int(_cursor_decode(cursor).get("overview_offset", 0))
        nodes, edges, groups, has_more = _grouped_overview(
            filtered_nodes,
            filtered_edges,
            source_identity=source_identity,
            offset=offset,
        )
        if has_more:
            next_offset = offset + max(RENDER_NODE_LIMIT - 1, 0)
            next_cursor = _cursor_encode({"overview_offset": next_offset})

    return {
        "schema_version": 1,
        "project_id": project_id,
        "run_id": run_id,
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
    source_identity = snapshot.get("source_identity", snapshot["project_id"])
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
        offset = int(_cursor_decode(cursor).get("offset", 0))
    page = members[offset : offset + page_size]
    next_offset = offset + page_size
    next_cursor = (
        _cursor_encode({"group": group_id, "offset": next_offset})
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
    "build_project_map",
    "compute_layout",
    "expand_group",
]
