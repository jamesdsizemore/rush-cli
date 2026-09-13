"""Phase 66 P66-02: project map data projection (build_project_map).

Verifies plan section 3.5's node/edge contract against the §3.9 fixtures,
the hard 200-node/400-edge render bound with complete server-paginated
membership above it, and layout determinism (same input, same output --
no randomness, no iterative physics).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from rush.dashboard.project_map import (
    RENDER_EDGE_LIMIT,
    RENDER_NODE_LIMIT,
    build_project_map,
    compute_layout,
    expand_group,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "dashboard"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def test_map_preserves_scoped_evidence_links() -> None:
    snapshot = _load_fixture("project_a.json")
    result = build_project_map(snapshot)

    assert result["schema_version"] == 1
    assert result["project_id"] == "project-a"
    assert result["source_identity"] == "source-a-0001"
    assert result["groups"] == []
    assert result["next_cursor"] is None

    nodes = result["nodes"]
    edges = result["edges"]
    assert len(nodes) == 9
    assert len(edges) == 8
    assert result["total_nodes"] == 9
    assert result["total_edges"] == 8

    kinds = [n["kind"] for n in nodes]
    assert kinds.count("project") == 1
    assert kinds.count("file") == 2
    assert kinds.count("finding") == 3
    assert kinds.count("memory") == 2
    assert kinds.count("agent") == 1

    relations = [e["relation"] for e in edges]
    assert relations.count("contains") == 2
    assert relations.count("reports") == 3
    assert relations.count("cites") == 2
    assert relations.count("assigned_to") == 1

    # Every edge endpoint must exist in the returned node set (spec 3.5).
    node_ids = {n["id"] for n in nodes}
    for edge in edges:
        assert edge["source"] in node_ids
        assert edge["target"] in node_ids

    # IDs are opaque, kind-prefixed, and file IDs are path-content-derived
    # (never the fixture's raw filesystem path).
    finding_ids = {n["id"] for n in nodes if n["kind"] == "finding"}
    assert finding_ids == {"finding:f1", "finding:f2", "finding:f3"}
    file_ids = {n["id"] for n in nodes if n["kind"] == "file"}
    assert all(fid.startswith("file:") and fid != "file:src/a.py" for fid in file_ids)


def test_large_map_pagination_is_complete() -> None:
    files = []
    findings = []
    for i in range(10_000):
        top = "src" if i % 2 == 0 else "lib"
        files.append({"path": f"{top}/mod{i // 1000}/file{i}.py"})
    for i in range(30_000):
        top = "src" if i % 2 == 0 else "lib"
        path = f"{top}/mod{(i % 10_000) // 1000}/file{i % 10_000}.py"
        findings.append({"id": f"f{i}", "path": path, "line": 1, "severity": "warn"})

    snapshot = {
        "schema_version": 1,
        "project_id": "big",
        "source_identity": "src-big",
        "root": "/fixtures/dashboard/big",
        "files": files,
        "findings": findings,
        "memories": [],
        "agents": [],
    }

    started = time.perf_counter()
    result = build_project_map(snapshot)
    elapsed = time.perf_counter() - started

    # Full evidence inventory (10,000 files + 30,000 findings + root) is
    # never dropped, even though only a bounded overview is rendered.
    assert result["total_nodes"] == 40_001
    assert len(result["nodes"]) <= RENDER_NODE_LIMIT
    assert len(result["edges"]) <= RENDER_EDGE_LIMIT
    # Bounded-time guard, not a precision benchmark: 0.25s tripped on a loaded
    # shared CI runner (measured 0.2514s), 1s still catches a real regression
    # (e.g. an accidental quadratic blowup) for 40k nodes.
    assert elapsed < 1.0

    group_ids = {g["id"] for g in result["groups"]}
    assert group_ids == {"group:src", "group:lib"}
    assert sum(g["member_count"] for g in result["groups"]) == 40_000

    # Pagination must eventually expose every underlying evidence ID.
    seen: set[str] = set()
    for group in result["groups"]:
        cursor = None
        while True:
            page = expand_group(snapshot, group["id"], cursor=cursor)
            assert len(page["members"]) <= 100
            seen.update(member["id"] for member in page["members"])
            cursor = page["next_cursor"]
            if cursor is None:
                break
    assert len(seen) == 40_000


def test_layout_is_deterministic() -> None:
    snapshot = _load_fixture("project_a.json")
    result = build_project_map(snapshot)

    first = compute_layout(result["nodes"])
    second = compute_layout(result["nodes"])
    assert first == second

    # Project root is always the fixed origin.
    assert first["project:project-a"] == (0.0, 0.0)

    # Re-running against a freshly rebuilt (but identical) snapshot produces
    # the same coordinates -- determinism is a property of the data, not of
    # object identity or call ordering.
    rebuilt = build_project_map(_load_fixture("project_a.json"))
    third = compute_layout(rebuilt["nodes"])
    assert first == third


def test_overview_pagination_cursor_covers_every_group() -> None:
    """When the grouped overview itself has more top-level groups than the
    200-node render bound, build_project_map must page across them via a
    real cursor rather than silently truncating with next_cursor=None
    (T303/T314: build_project_map's cursor param was dead code)."""
    files = [{"path": f"dir{i}/file.py"} for i in range(250)]
    snapshot = {
        "schema_version": 1,
        "project_id": "wide",
        "source_identity": "src-wide",
        "root": "/fixtures/dashboard/wide",
        "files": files,
        "findings": [],
        "memories": [],
        "agents": [],
    }

    seen_group_ids: set[str] = set()
    cursor = None
    pages = 0
    while True:
        page = build_project_map(snapshot, cursor=cursor)
        assert len(page["nodes"]) <= RENDER_NODE_LIMIT
        seen_group_ids.update(g["id"] for g in page["groups"])
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert pages > 1
    assert seen_group_ids == {f"group:dir{i}" for i in range(250)}


def test_expand_group_is_filter_consistent_with_member_count() -> None:
    """T303's exact repro: expand_group must be called with the SAME
    filters that produced a group's member_count, and must return exactly
    that many members -- never a filter-inconsistent superset."""
    findings = []
    for i in range(60):
        severity = "critical" if i % 3 == 0 else "warn"
        findings.append(
            {
                "id": f"f{i}",
                "path": f"src/mod/file{i}.py",
                "line": 1,
                "severity": severity,
            }
        )
    snapshot = {
        "schema_version": 1,
        "project_id": "filtered",
        "source_identity": "src-filtered",
        "root": "/fixtures/dashboard/filtered",
        "files": [],
        "findings": findings,
        "memories": [],
        "agents": [],
    }

    # Force the grouped overview by requesting a render limit smaller than
    # the finding count, under a severity filter.
    result = build_project_map(snapshot, severity=("critical",), limit=5)
    group = next(g for g in result["groups"] if g["id"] == "group:src")
    critical_count = sum(1 for f in findings if f["severity"] == "critical")
    assert group["member_count"] == critical_count

    # Same filter threaded through expand_group: total/members match exactly.
    filtered_page = expand_group(snapshot, "group:src", severity=("critical",))
    assert filtered_page["total"] == critical_count
    seen = set()
    cursor = None
    while True:
        page = expand_group(
            snapshot, "group:src", severity=("critical",), cursor=cursor
        )
        seen.update(m["id"] for m in page["members"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == critical_count

    # No filter args at all: expand_group returns the FULL membership, which
    # legitimately diverges from the filtered member_count above -- proving
    # the caller must thread the real filters through, not that expand_group
    # itself is broken.
    unfiltered_total = expand_group(snapshot, "group:src")["total"]
    assert unfiltered_total == len(findings)
    assert unfiltered_total != critical_count
