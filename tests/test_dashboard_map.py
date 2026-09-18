"""Phase 66 P66-02: project map data projection (build_project_map).

Verifies plan section 3.5's node/edge contract against the §3.9 fixtures,
the hard 200-node/400-edge render bound with complete server-paginated
membership above it, and layout determinism (same input, same output --
no randomness, no iterative physics).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import rush.tools.common  # noqa: F401 -- import first: avoids a circular

# import through `rush.runtime` when `rush.runtime.subprocesses` is imported
# on its own (same rationale as `tests/test_subprocess_contract.py`).
import rush.tui as tui_module
from rush.dashboard import server as server_module
from rush.dashboard.project_map import (
    RENDER_EDGE_LIMIT,
    RENDER_NODE_LIMIT,
    CursorRejected,
    build_project_map,
    compute_layout,
    expand_group,
    expand_group_edge,
)
from rush.dashboard.server import create_dashboard_server, publish_check_suite_scan
from rush.dashboard.state import (
    MutationLedger,
    OwnerLock,
    claim_dead_owner,
    reconcile_admissions,
)
from rush.permissions import ExecutionPermissions
from rush.runtime.subprocesses import (
    _record_owned_process,
    read_owned_process_records,
)
from rush.setup import provision as provision_module
from rush.tools.review import ReviewTool
from rush.workflows import project_run as project_run_module
from rush.workflows import projects as projects_module
from rush.workflows import suites as suites_module
from rush.workflows.projects import register_project
from rush.workflows.suites import CHECK_SUITE, run_workflow_suite

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "dashboard"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


# --- P69-03.1 RED: real scan-publication helpers (mirrors the HTTP action
# harness in tests/test_dashboard_scan_actions.py; this file stays
# self-contained rather than cross-importing another test module) ----------


class _StubLint:
    """A minimal `lint`-named tool for `run_workflow_suite`'s own `ALL_TOOLS`
    lookup (`rush.workflows.suites`, not `project_run`'s catalog) -- fast,
    deterministic, and real enough to prove the CHECK_SUITE finding-id and
    manifest-publication fix without any external engine binary."""

    name = "lint"

    def __call__(
        self,
        path: Path,
        engine_args: list[str] | None = None,
        owner_instance_id: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, object]:
        return {
            "tool": "lint",
            "engine": "ruff",
            "engine_version": None,
            "status": "warn",
            "duration_ms": 1,
            "summary": "lint: 1 issue",
            "findings": [
                {
                    "path": "app.py",
                    "line": 1,
                    "column": 0,
                    "rule": "seeded-lint-rule",
                    "severity": "warn",
                    "message": "seeded lint issue",
                }
            ],
            "raw": None,
        }


def _isolate_data_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_root = tmp_path / "rush-data"
    monkeypatch.setattr(projects_module, "default_data_root", lambda: data_root)
    monkeypatch.setattr(provision_module, "default_data_root", lambda: data_root)


def _register(tmp_path: Path) -> tuple[str, Path]:
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("def broken():\n    pass\n", encoding="utf-8")
    record = register_project(root)
    return record.project_id, root


def _empty_snapshot(project_id: str, root: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "project_id": project_id,
        "source_identity": str(root),
        "root": str(root),
        "files": [],
        "findings": [],
        "memories": [],
        "agents": [],
    }


def _serve(server: Any) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def _get(url: str, headers: dict | None = None):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        return urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as exc:
        return exc


def _post(url: str, headers: dict | None = None, body: bytes = b""):
    req = urllib.request.Request(url, data=body, headers=headers or {}, method="POST")
    try:
        return urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as exc:
        return exc


def _bootstrap_session(base_url: str, token: str) -> tuple[str, str]:
    resp = _post(
        f"{base_url}/api/session", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status == 200
    payload = json.loads(resp.read())
    cookie_value = resp.headers.get("Set-Cookie").split(";")[0]
    return cookie_value, payload["csrf_token"]


def _action(
    base_url: str,
    project_id: str,
    cookie: str,
    csrf: str,
    *,
    operation: str,
    arguments: dict[str, Any] | None = None,
    grants: dict[str, Any] | None = None,
):
    body = json.dumps(
        {
            "schema_version": 1,
            "operation": operation,
            "arguments": arguments or {},
            "grants": grants or {},
            "expected": {},
            "request_id": str(uuid.uuid4()),
        }
    ).encode("utf-8")
    resp = _post(
        f"{base_url}/api/projects/{project_id}/actions",
        headers={
            "Cookie": cookie,
            "X-Rush-CSRF": csrf,
            "Origin": base_url,
            "Content-Type": "application/json",
        },
        body=body,
    )
    return resp.status, json.loads(resp.read())


def _scans(base_url: str, project_id: str, cookie: str, **query: str):
    from urllib.parse import urlencode

    qs = urlencode({"section": "scans", **query})
    resp = _get(
        f"{base_url}/api/projects/{project_id}/snapshot?{qs}",
        headers={"Cookie": cookie},
    )
    return resp.status, json.loads(resp.read())


def _wait_until(predicate, *, timeout: float = 5.0, interval: float = 0.02) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    assert predicate(), "condition never became true within timeout"


def _grant_all() -> dict[str, bool]:
    return {"cache_write": True, "artifact_write": True}


def _start_dashboard(project_id: str, root: Path):
    server, ctx, token = create_dashboard_server(
        {project_id: _empty_snapshot(project_id, root)}
    )
    _serve(server)
    base_url = ctx.launch_origin
    cookie, csrf = _bootstrap_session(base_url, token)
    return server, ctx, base_url, cookie, csrf


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
    # P69-08.2 sign-off (2026-09-18): kept at 1.0s rather than restoring the
    # original 250ms figure -- see phase-66-interactive-tui-and-local-web-plan.md
    # sec0 row 18 for the full evidenced decision record (this environment's
    # own local runs measure well under 250ms, but that can't stand in for the
    # actual shared CI runner where the 0.2514s breach above was measured).
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


# --- P69-03q: group-edge budget -- a dropped relationship survives as a
# counted, expandable group-edge, not silent loss, and summary edges
# themselves stay within the 400-edge bound. -------------------------------


def test_dense_relationship_set_preserves_counted_edges() -> None:
    """Reproduce the live-probed dense-relationship gap: when grouping hides
    both a `cites` edge's source (many memories, bucketed into
    `group:memory`) and target (findings scattered across many directory
    groups), the relationship must survive as one counted, expandable
    group-edge per (group, relation) pair -- never silently dropped -- and
    the rendered result must stay within the 200-node/400-edge bound even
    with the replacement edges counted in."""
    files = []
    findings = []
    for d in range(30):
        for f in range(5):
            path = f"dir{d}/file{f}.py"
            files.append({"path": path})
            findings.append(
                {"id": f"f{d}-{f}", "path": path, "line": 1, "severity": "warn"}
            )
    memories = [
        {"id": f"m{i}", "cites": [findings[i % len(findings)]["id"]]}
        for i in range(200)
    ]

    snapshot = {
        "schema_version": 1,
        "project_id": "dense",
        "source_identity": "src-dense",
        "root": "/fixtures/dashboard/dense",
        "files": files,
        "findings": findings,
        "memories": memories,
        "agents": [],
    }

    result = build_project_map(snapshot)
    assert len(result["nodes"]) <= RENDER_NODE_LIMIT
    assert len(result["edges"]) <= RENDER_EDGE_LIMIT
    # Full evidence inventory is never dropped from the totals, even though
    # only a bounded overview renders.
    assert result["total_nodes"] == 1 + len(files) + len(findings) + len(memories)

    cites_summaries = [
        e for e in result["edges"] if e["relation"] == "cites" and e["expandable"]
    ]
    assert cites_summaries, "dropped cites relationships must survive as group-edges"
    assert sum(e["count"] for e in cites_summaries) == len(memories)

    # Every counted relationship must stay reachable through expansion --
    # page each summary edge to exhaustion and confirm the real edges
    # returned add up to exactly its own count.
    total_expanded = 0
    for summary in cites_summaries:
        cursor = summary["cursor"]
        edge_id = summary["id"]
        seen = 0
        while cursor is not None:
            page = expand_group_edge(snapshot, edge_id, cursor=cursor)
            assert len(page["members"]) <= 100
            seen += len(page["members"])
            cursor = page["next_cursor"]
        assert seen == summary["count"]
        total_expanded += seen
    assert total_expanded == len(memories)


def test_group_endpoint_expansion_stays_within_rendering_bound() -> None:
    """Even when there are enough groups and relation types that one
    per-(group, relation) summary edge each would itself exceed the
    400-edge bound, the rendered response must still respect the
    200-node/400-edge limits -- and every dropped relationship must still
    be accounted for by some counted edge (per-group, or the further-
    collapsed per-relation overflow fallback), never silently lost."""
    files = []
    findings = []
    for d in range(190):
        path = f"dir{d}/file.py"
        files.append({"path": path})
        findings.append({"id": f"f{d}", "path": path, "line": 1, "severity": "warn"})

    agents = [{"id": f"a{i}", "assigned_to": [f"f{i % 190}"]} for i in range(300)]
    memories = [{"id": f"m{i}", "cites": [f"f{i % 190}"]} for i in range(300)]

    snapshot = {
        "schema_version": 1,
        "project_id": "overflow",
        "source_identity": "src-overflow",
        "root": "/fixtures/dashboard/overflow",
        "files": files,
        "findings": findings,
        "memories": memories,
        "agents": agents,
    }

    result = build_project_map(snapshot)
    assert len(result["nodes"]) <= RENDER_NODE_LIMIT
    assert len(result["edges"]) <= RENDER_EDGE_LIMIT

    counted = [e for e in result["edges"] if e["relation"] in ("assigned_to", "cites")]
    assert sum(e["count"] for e in counted) == len(agents) + len(memories)


# --- P69-03t: map/group cursor tuple binding -------------------------------


def test_cursor_rejected_across_project_or_revision() -> None:
    """Reproduce the live-probed cross-project cursor acceptance as a
    failing-then-fixed gap: a cursor minted for one project/revision must
    never be silently accepted by build_project_map for a different
    project, or the same project after a rescan bumped `sequence`."""
    files = [{"path": f"dir{i}/file.py"} for i in range(250)]
    snapshot_a = {
        "schema_version": 1,
        "project_id": "proj-a",
        "source_identity": "src-a",
        "root": "/fixtures/dashboard/proj-a",
        "files": files,
        "findings": [],
        "memories": [],
        "agents": [],
    }
    snapshot_b = {**snapshot_a, "project_id": "proj-b", "source_identity": "src-b"}

    result_a = build_project_map(snapshot_a)
    cursor = result_a["next_cursor"]
    assert cursor is not None

    with pytest.raises(CursorRejected):
        build_project_map(snapshot_b, cursor=cursor)

    snapshot_a_rescanned = {**snapshot_a, "sequence": 2}
    with pytest.raises(CursorRejected):
        build_project_map(snapshot_a_rescanned, cursor=cursor)

    # The same project/revision the cursor was issued under still works.
    result_page_2 = build_project_map(snapshot_a, cursor=cursor)
    assert result_page_2["groups"] or result_page_2["nodes"]


def test_non_map_section_cursor_rejects_malformed_or_cross_snapshot_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03u: row 10's "other section cursors silently reset to zero" gap
    -- every non-map section (memory here) binds its cursor to its own
    backing store's revision. A malformed cursor, and a well-formed cursor
    replayed after the store's revision has moved on, must both be
    rejected, never silently reset to offset 0."""
    from urllib.parse import urlencode

    from rush.memory.store import MemoryArtifact, TypedArtifactStore

    def _seed(store: TypedArtifactStore, note: str) -> None:
        store.write(
            MemoryArtifact(
                id=str(uuid.uuid4()),
                family="memory",
                subject="domain_knowledge",
                trust_tier="EXTERNAL_WRITE",
                content={"note": note},
                source="test-source",
                created_at=time.time(),
            )
        )

    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    store = TypedArtifactStore(root)
    for i in range(3):
        _seed(store, f"seed-{i}")

    server, _ctx, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:

        def _memory(**extra: str):
            qs = urlencode({"section": "memory", **extra})
            resp = _get(
                f"{base_url}/api/projects/{project_id}/snapshot?{qs}",
                headers={"Cookie": cookie},
            )
            return resp.status, json.loads(resp.read())

        # A genuinely malformed cursor is rejected, not silently reset.
        status, body = _memory(cursor="not-a-real-cursor!!", limit="1")
        assert status != 200
        assert "error" in body

        status, body = _memory(limit="1")
        assert status == 200
        cursor = body["data"]["next_cursor"]
        assert cursor is not None

        # A real mutation between two page requests moves the store's
        # revision -- the outstanding cursor must be rejected, never
        # silently splice pre/post-mutation pages into one response.
        _seed(store, "seed-after")
        status, body = _memory(cursor=cursor, limit="1")
        assert status == 409
        assert body["error"]["code"] == "cursor_rejected"
    finally:
        server.shutdown()
        server.server_close()


# --- P69-03.1 RED: no code path published a completed scan back into a
# ProjectRecord at all -- these reproduce that gap for all four real
# producers (execute_scan/resume_scan_run/rescan_project_run's HTTP
# dispatchers, and CHECK_SUITE's initial-launch scan) before P69-03.2 GREEN.


def test_launch_populates_map_from_completed_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CHECK_SUITE's initial-launch scan (what `dashboard_cmd` runs) must
    reach the project's live map -- before this fix, `_run_initial_scan`
    discarded `run_workflow_suite()`'s result entirely and the map stayed
    the launch-time empty snapshot forever."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(suites_module, "ALL_TOOLS", [_StubLint()])
    project_id, root = _register(tmp_path)
    _server, ctx, _token = create_dashboard_server(
        {project_id: _empty_snapshot(project_id, root)}
    )

    aggregate = run_workflow_suite(
        suite=CHECK_SUITE, path=root, permissions=ExecutionPermissions()
    )
    publish_check_suite_scan(ctx, project_id, root, aggregate)

    record = ctx.projects.get(project_id)
    assert record.snapshot["findings"], "map snapshot still has zero findings"
    assert record.snapshot["files"], "map snapshot still has zero files"
    assert record.sequence == 2

    result = build_project_map(record.snapshot)
    finding_nodes = [n for n in result["nodes"] if n["kind"] == "finding"]
    assert any(n["path"] == "app.py" for n in finding_nodes)


def test_check_suite_findings_carry_a_real_finding_id_and_are_visible_in_the_scans_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`aggregate_results()` never assigns `finding_id` (only `provenance`);
    `_build_scans_section` drops any finding missing one. Without the fix
    every CHECK_SUITE finding is silently invisible there."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(suites_module, "ALL_TOOLS", [_StubLint()])
    project_id, root = _register(tmp_path)
    _server, ctx, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        aggregate = run_workflow_suite(
            suite=CHECK_SUITE, path=root, permissions=ExecutionPermissions()
        )
        assert not (aggregate.get("findings") or [{}])[0].get("finding_id")
        run_id, _attempt_id = publish_check_suite_scan(ctx, project_id, root, aggregate)

        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        assert status == 200
        items = scans["data"]["findings"]["items"]
        assert len(items) == 1
        assert items[0]["finding_id"]
        assert items[0]["rule"] == "seeded-lint-rule"
    finally:
        _server.shutdown()
        _server.server_close()


def test_check_suite_manifest_summary_reports_its_real_finding_count_not_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_run_summary()`'s `totals.get("finding_count", 0)` silently reports
    zero unless CHECK_SUITE's own minimal manifest computes it for real."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(suites_module, "ALL_TOOLS", [_StubLint()])
    project_id, root = _register(tmp_path)
    _server, ctx, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        aggregate = run_workflow_suite(
            suite=CHECK_SUITE, path=root, permissions=ExecutionPermissions()
        )
        run_id, _attempt_id = publish_check_suite_scan(ctx, project_id, root, aggregate)

        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        assert status == 200
        assert scans["data"]["run"]["finding_count"] == 1
    finally:
        _server.shutdown()
        _server.server_close()


def test_scan_result_published_atomically_not_partially_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A concurrent reader must never observe a `snapshot`/`source_identity`
    combination that didn't exist together at any single point in time --
    `ProjectRegistry.publish_scan_result` updates all three under one lock,
    and `get()` is itself lock-serialized, so a reader that always re-reads
    through `get()` (never caches a stale `record` reference) can only ever
    see a fully-published generation."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    empty_snapshot = _empty_snapshot(project_id, root)
    _server, ctx, _token = create_dashboard_server({project_id: empty_snapshot})

    mismatches: list[str] = []
    stop = threading.Event()

    def _reader() -> None:
        while not stop.is_set():
            record = ctx.projects.get(project_id)
            marker = record.snapshot.get("_publish_marker")
            if marker is not None and record.source_identity != f"identity-{marker}":
                mismatches.append(
                    f"marker={marker} source_identity={record.source_identity}"
                )

    reader_thread = threading.Thread(target=_reader, daemon=True)
    reader_thread.start()
    try:
        for i in range(200):
            ctx.projects.publish_scan_result(
                project_id,
                snapshot={**empty_snapshot, "_publish_marker": i},
                source_identity=f"identity-{i}",
            )
    finally:
        stop.set()
        reader_thread.join(timeout=5)

    assert mismatches == []
    assert ctx.projects.get(project_id).sequence == 201


def test_initial_launch_scan_publishes_via_same_path_as_rescan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CHECK_SUITE's initial launch and a real `scan_start`/`rescan` HTTP
    dispatch must fund the exact same `ProjectRegistry.publish_scan_result`
    sequence counter -- never two divergent publication routes."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(suites_module, "ALL_TOOLS", [_StubLint()])
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [ReviewTool()])
    project_id, root = _register(tmp_path)
    _server, ctx, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        assert ctx.projects.get(project_id).sequence == 1

        aggregate = run_workflow_suite(
            suite=CHECK_SUITE, path=root, permissions=ExecutionPermissions()
        )
        publish_check_suite_scan(ctx, project_id, root, aggregate)
        assert ctx.projects.get(project_id).sequence == 2

        status, body = _action(
            base_url, project_id, cookie, csrf, operation="provision_plan"
        )
        assert status == 200
        plan_id = body["data"]["scan_plan"]["plan_id"]
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_start",
            arguments={"plan_id": plan_id},
            grants=_grant_all(),
        )
        assert status == 202
        baseline_run_id = body["data"]["run_id"]
        _wait_until(lambda: ctx.projects.get(project_id).sequence == 3)

        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="rescan",
            arguments={"run_id": baseline_run_id},
            grants=_grant_all(),
        )
        assert status == 202
        _wait_until(lambda: ctx.projects.get(project_id).sequence == 4)
    finally:
        _server.shutdown()
        _server.server_close()


def test_scan_resume_publishes_result_not_discarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`scan_resume`'s dispatcher discarded `resume_scan_run()`'s own
    `ScanRun` entirely -- the map never learned a resume ever happened."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [ReviewTool()])
    project_id, root = _register(tmp_path)
    _server, ctx, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, body = _action(
            base_url, project_id, cookie, csrf, operation="provision_plan"
        )
        assert status == 200
        plan_id = body["data"]["scan_plan"]["plan_id"]
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_start",
            arguments={"plan_id": plan_id},
            grants=_grant_all(),
        )
        assert status == 202
        run_id = body["data"]["run_id"]
        _wait_until(lambda: ctx.projects.get(project_id).sequence == 2)
        sequence_after_start = ctx.projects.get(project_id).sequence

        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_resume",
            arguments={"run_id": run_id},
            grants=_grant_all(),
        )
        assert status == 202
        _wait_until(
            lambda: ctx.projects.get(project_id).sequence > sequence_after_start
        )
        assert ctx.projects.get(project_id).snapshot["findings"]
    finally:
        _server.shutdown()
        _server.server_close()


# --- P69-03.1 RED (subsections d-j): staging, path mapping, provenance ------


class _RuffThroughStagingTool:
    """A real scan candidate that runs a real path-based engine through
    `run_engine()` -- the one code path P69-03e/g redirects into the staged
    tree. `_InstantTool`-style stubs never touch it, so they cannot prove
    anything about staging or per-file consumption digests."""

    name = "only-check"

    def __call__(self, path: Path) -> dict[str, Any]:
        from rush.engines.ruff import RuffEngine
        from rush.runtime.subprocesses import run_engine

        return dict(run_engine(RuffEngine(), path, [], cwd=path, tool_name=self.name))


def _attempt_dir(root: Path, run_id: str, attempt_id: str) -> Path:
    return root / ".rush" / "runs" / run_id / "attempts" / attempt_id


def _run_one_scan(tmp_path: Path, project_id: str):
    from rush.workflows.project_run import execute_scan, plan_scan

    plan = plan_scan(project_id, data_root=tmp_path / "rush-data")
    return execute_scan(
        plan,
        permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
        data_root=tmp_path / "rush-data",
    )


def test_pre_execution_guard_detects_equal_length_content_replacement_via_ctime_even_when_mtime_is_preserved(
    tmp_path: Path,
) -> None:
    """P69-03d: the pre-execution signature read only path/size/mtime, so
    replacing a file's bytes with a different payload of the same length and
    restoring its mtime produced an identical fingerprint -- a real
    `git checkout`-shaped miss. `st_ctime_ns` comes back on the `path.stat()`
    call this function already made and cannot be reset through `utime()`."""
    import os

    root = tmp_path / "project"
    root.mkdir()
    target = root / "app.py"
    target.write_bytes(b"AAAA")
    before_stat = target.stat()
    before = project_run_module._source_signature(root)

    target.write_bytes(b"BBBB")
    os.utime(target, ns=(before_stat.st_atime_ns, before_stat.st_mtime_ns))

    after_stat = target.stat()
    assert after_stat.st_size == before_stat.st_size
    assert after_stat.st_mtime_ns == before_stat.st_mtime_ns
    assert target.read_bytes() != b"AAAA"

    assert project_run_module._source_signature(root) != before


def test_resume_pre_execution_guard_is_a_separate_cheap_check_not_the_consumption_aggregate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03d/j: `source_identity` cannot gate a decision made before any
    engine has run -- it does not exist yet. The attempt header keeps the
    cheap path/size/mtime/ctime signature under its own name and format tag;
    the consumption aggregate lands only in the terminal manifest, and the two
    are never substituted for one another. An untagged (old-format) header is
    unsupported, never reinterpreted as a content hash."""
    from rush.workflows.project_run import ScanResumeStaleError, resume_scan_run

    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [_RuffThroughStagingTool()])
    project_id, root = _register(tmp_path)
    run = _run_one_scan(tmp_path, project_id)

    header_path = _attempt_dir(root, run.run_id, run.attempt_id) / "attempt.json"
    header = json.loads(header_path.read_text())
    manifest = json.loads(Path(run.manifest_path).read_text())

    assert header["source_signature_format"] == 2
    assert header["source_signature"] == project_run_module._source_signature(root)
    # The consumption aggregate is not, and cannot be, in a pre-execution record.
    assert "source_identity" not in header

    identity = manifest["source_identity"]
    assert identity["provenance_format"] == 2
    assert identity["content"] and identity["content"] != header["source_signature"]
    assert identity["file_count"] >= 1

    # An old-format header is refused outright rather than compared.
    legacy = dict(header)
    legacy.pop("source_signature_format")
    header_path.write_text(json.dumps(legacy, indent=2, sort_keys=True))
    with pytest.raises(ScanResumeStaleError) as excinfo:
        resume_scan_run(
            root,
            run.run_id,
            permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
            data_root=tmp_path / "rush-data",
        )
    assert "old-format" in str(excinfo.value)


def test_retained_candidates_on_resume_carry_forward_their_original_per_file_digests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03e: a candidate a resume *retains* is never re-executed, so nothing
    re-reads its content -- its original per-file digests carry forward into
    the new attempt's consumption aggregate instead of a fresh consumption
    event being manufactured for bytes nobody read."""
    from rush.engines.staging import aggregate_content_identity
    from rush.workflows import project_run
    from rush.workflows.project_run import resume_scan_run

    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [_RuffThroughStagingTool()])
    project_id, root = _register(tmp_path)
    first = _run_one_scan(tmp_path, project_id)

    def _entry(manifest: dict) -> dict:
        return next(
            item
            for item in manifest["scheduled"]
            if item["candidate_id"] == "only-check"
        )

    first_manifest = json.loads(Path(first.manifest_path).read_text())
    assert _entry(first_manifest)["outcome"] == "executed"
    first_digests = _entry(first_manifest)["source_digests"]
    assert first_digests, "the executed candidate recorded no staged-content digests"
    assert first_manifest["source_identity"]["content"] == aggregate_content_identity(
        first_digests
    )

    executed: list[str] = []
    original = project_run._execute_candidate

    def _spy(candidate, **kwargs):
        executed.append(candidate.candidate_id)
        return original(candidate, **kwargs)

    monkeypatch.setattr(project_run, "_execute_candidate", _spy)

    second = resume_scan_run(
        root,
        first.run_id,
        permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
        data_root=tmp_path / "rush-data",
    )
    second_manifest = json.loads(Path(second.manifest_path).read_text())

    assert "only-check" not in executed, "a retained candidate must not be re-executed"
    assert _entry(second_manifest)["source_digests"] == first_digests
    assert (
        second_manifest["source_identity"]["content"]
        == first_manifest["source_identity"]["content"]
    )


def _write_eslint_fixture(root: Path) -> None:
    (root / "src").mkdir(parents=True)
    plugin = root / "node_modules" / "eslint-plugin-demo"
    plugin.mkdir(parents=True)
    (plugin / "package.json").write_text(
        '{"name":"eslint-plugin-demo","version":"1.0.0","main":"index.js"}'
    )
    (plugin / "index.js").write_text("module.exports = { rules: {} };\n")
    (root / "eslint.config.mjs").write_text(
        'import demo from "eslint-plugin-demo";\nexport default [{plugins: {demo}}];\n'
    )
    (root / "src" / "app.js").write_text("const x = 1;\n")


def test_eslint_staged_run_resolves_its_own_config_and_plugins_identically_to_the_live_run(
    tmp_path: Path,
) -> None:
    """P69-03e/g: the bounded inventory deliberately excludes `node_modules`,
    so staging only the in-scope files would silently lose ESLint's own config
    and plugin resolution. Exercises ESLint's real resolution mechanism --
    Node's ESM import of `eslint.config.mjs` plus `require.resolve` of the
    plugin that config names -- from the staging root against the live root."""
    import shutil
    import subprocess

    from rush.engines.staging import stage_inventory

    assert shutil.which("node") is not None, "node is required for this parity test"

    root = tmp_path / "project"
    root.mkdir()
    _write_eslint_fixture(root)

    resolve_script = (
        'process.stdout.write(require.resolve("eslint-plugin-demo",'
        "{paths:[process.cwd()]}))"
    )
    config_script = (
        'const m = await import("./eslint.config.mjs");'
        "process.stdout.write(JSON.stringify(Object.keys(m.default[0].plugins)))"
    )

    def _node(cwd: Path, argv: list[str]) -> tuple[int, str]:
        proc = subprocess.run(
            ["node", *argv],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout.strip()

    def _resolve_plugin(cwd: Path) -> tuple[int, str]:
        return _node(cwd, ["-e", resolve_script])

    def _load_config(cwd: Path) -> tuple[int, str]:
        return _node(cwd, ["--input-type=module", "-e", config_script])

    live_plugin = _resolve_plugin(root)
    live_config = _load_config(root)
    assert live_plugin[0] == 0
    assert live_config[1] == '["demo"]'

    staging_root = tmp_path / "staging"
    staging = stage_inventory(
        root, staging_root, project_run_module._scan_inventory(root)
    )
    # The excluded dependency directory is reachable from the staging root at
    # its live relative path, and was never copied.
    assert (staging.staged_root / "node_modules").is_symlink()
    assert "node_modules/eslint-plugin-demo/index.js" not in staging.digests
    # The in-scope config file is a real, independently-mutable copy.
    assert "eslint.config.mjs" in staging.digests
    assert not (staging.staged_root / "eslint.config.mjs").is_symlink()

    assert _resolve_plugin(staging.staged_root) == live_plugin
    assert _load_config(staging.staged_root) == live_config

    staged_config = staging.staged_root / "eslint.config.mjs"
    original_staged = staged_config.read_bytes()
    with (root / "eslint.config.mjs").open("r+b") as handle:
        handle.seek(0)
        handle.write(b"/")
    assert staged_config.read_bytes() == original_staged


def test_tsc_staged_run_resolves_a_node_modules_type_definition_identically_to_the_live_run(
    tmp_path: Path,
) -> None:
    """P69-03e/g: `tsc --noEmit <files>` (TscEngine's real invocation) resolves
    module types out of `node_modules`, which the bounded inventory excludes.
    A staged run must produce the identical diagnostic, reported against the
    live path, never the staging directory."""
    import shutil

    from rush.engines.staging import stage_inventory, staging_scope
    from rush.engines.tsc import TscEngine
    from rush.runtime.binaries import clear_binary_cache
    from rush.runtime.subprocesses import run_engine

    assert shutil.which("tsc") is not None, "tsc is required for this parity test"

    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    pkg = root / "node_modules" / "demo-pkg"
    pkg.mkdir(parents=True)
    (pkg / "package.json").write_text(
        '{"name":"demo-pkg","version":"1.0.0","main":"index.js","types":"index.d.ts"}'
    )
    (pkg / "index.d.ts").write_text(
        "export declare function greet(name: string): void;\n"
    )
    (pkg / "index.js").write_text("exports.greet = function () {};\n")
    (root / "src" / "app.ts").write_text(
        'import { greet } from "demo-pkg";\ngreet(123);\n'
    )

    # A stale negative in the process-wide binary-resolution cache would make
    # both runs `skipped` and the comparison below vacuous.
    clear_binary_cache()

    target = root / "src" / "app.ts"
    live = run_engine(TscEngine(), root, [str(target)], cwd=root)
    live_findings = live.get("findings") or []
    assert live["status"] not in ("skipped", "error"), (
        f"the live tsc run did not execute: {live['status']} / {live['summary']}"
    )
    assert live_findings, "the fixture must produce a real node_modules-typed error"

    staging_root = tmp_path / "staging"
    staging = stage_inventory(
        root, staging_root, project_run_module._scan_inventory(root)
    )
    with staging_scope(staging):
        staged = run_engine(TscEngine(), root, [str(target)], cwd=root)

    staged_findings = staged.get("findings") or []
    assert len(staged_findings) == len(live_findings)
    for staged_finding, live_finding in zip(
        staged_findings, live_findings, strict=True
    ):
        assert staged_finding["rule"] == live_finding["rule"]
        assert staged_finding["line"] == live_finding["line"]
        assert staged_finding["column"] == live_finding["column"]
        assert staged_finding["message"] == live_finding["message"]
        # Reported against the live tree, never the staging directory.
        assert Path(staged_finding["path"]).resolve() == target.resolve()
        assert str(staging_root) not in staged_finding["path"]


def _init_git_repo(root: Path) -> None:
    """A minimal real repo -- one commit on `main` -- for the P69-03h
    repository-state-dependent engine tests below."""
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=root, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)


def _dispatching_fake_run(
    argv: list[str], **_kwargs: object
) -> subprocess.CompletedProcess[str]:
    """Real `git` (installed, genuinely needed to exercise pin resolution and
    the independent diff computation) for a `git` invocation; a faked success
    for diff-cover's own binary invocation (not installed in this
    environment)."""
    if argv[0] == "git":
        return subprocess.run(argv, capture_output=True, text=True, check=False)
    return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")


def test_diff_cover_and_undercover_are_classified_repository_state_dependent_by_actual_invoked_command_behavior_not_a_literal_git_argv_grep() -> (
    None
):
    """P69-03h: `diff-cover`/`undercover` each launch their own binary, never
    `git` directly, yet both require a real repository internally --
    classification into `REPOSITORY_STATE_ENGINES` is by what the invoked
    command actually needs, never by grepping the engine's own argv for the
    literal string 'git'."""
    from rush.engines.diff_cover import DiffCoverEngine
    from rush.engines.staging import REPOSITORY_STATE_ENGINES
    from rush.engines.undercover import UndercoverEngine

    diff_cover_engine = DiffCoverEngine()
    undercover_engine = UndercoverEngine()

    assert diff_cover_engine.binary != "git"
    assert undercover_engine.binary != "git"
    assert diff_cover_engine.name in REPOSITORY_STATE_ENGINES
    assert undercover_engine.name in REPOSITORY_STATE_ENGINES
    assert "git" not in (diff_cover_engine.binary, undercover_engine.binary)


def test_diff_covers_consumed_coverage_xml_gets_an_independently_staged_hashed_copy_while_cwd_stays_on_the_live_repository_for_git_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03h: diff-cover's `coverage.xml` input is a real, independent
    staged copy (never a hardlink) passed via an explicit path argument,
    while `cwd` stays on the live repository so diff-cover's own Git access
    still works."""
    from rush.engines import diff_cover

    root = tmp_path / "project"
    _init_git_repo(root)
    (root / "coverage.xml").write_text("<coverage><original/></coverage>\n")

    calls: list[tuple[list[str], Any]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if argv[0] == "git":
            return subprocess.run(argv, capture_output=True, text=True, check=False)
        calls.append((argv, kwargs.get("cwd")))
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(diff_cover, "resolve_binary", lambda _binary: "diff-cover")
    monkeypatch.setattr(diff_cover, "run_subprocess", fake_run)

    diff_cover.DiffCoverEngine().run(root, [], cwd=root)

    assert len(calls) == 1
    argv, cwd = calls[0]
    assert cwd == root, "cwd must stay on the live repository for Git access"
    coverage_arg = Path(argv[1])
    assert coverage_arg != root / "coverage.xml"
    assert coverage_arg.name == "coverage.xml"
    original_bytes = coverage_arg.read_bytes()
    assert original_bytes == (root / "coverage.xml").read_bytes()

    (root / "coverage.xml").write_bytes(b"<coverage><mutated/></coverage>\n")
    assert coverage_arg.read_bytes() == original_bytes, (
        "the staged copy must be a real independent copy, never a hardlink"
    )


def test_git_guards_provenance_hashes_its_own_real_invocation_stdout_the_same_bytes_that_produced_its_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03h: GitGuardEngine's provenance is the exact stdout bytes that
    already produced its own findings -- no separate capture-then-compare
    step, no race between what was hashed and what was parsed."""
    from hashlib import sha256

    from rush.engines import git_guard

    stdout = "# branch.oid abc123\n? secrets.env\n"

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(git_guard, "resolve_binary", lambda _binary: "git")
    monkeypatch.setattr(git_guard, "run_subprocess", fake_run)

    raw = git_guard.GitGuardEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["stdout"] == stdout
    assert raw["provenance"]["kind"] == "git-status-stdout"
    assert raw["provenance"]["digest"] == sha256(stdout.encode("utf-8")).hexdigest()


def test_diff_covers_provenance_hashes_an_independently_computed_actual_diff_against_the_pinned_base_and_target_not_a_status_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03h: diff-cover's provenance is Rush's own independently computed
    `git diff <pinned-base>...<pinned-target>` content, not a status
    summary -- a status-only hash would be identical whether or not the two
    endpoints actually diverged."""
    from hashlib import sha256

    from rush.engines import diff_cover

    root = tmp_path / "project"
    _init_git_repo(root)
    base_sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "main"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    subprocess.run(
        ["git", "-C", str(root), "checkout", "-q", "-b", "feature"], check=True
    )
    (root / "README.md").write_text("hello\nchanged\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "change"], check=True)
    target_sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    expected_diff = subprocess.run(
        ["git", "-C", str(root), "diff", f"{base_sha}...{target_sha}", "--", "."],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    expected_digest = sha256(expected_diff.encode("utf-8")).hexdigest()

    monkeypatch.setattr(diff_cover, "resolve_binary", lambda _binary: "diff-cover")
    monkeypatch.setattr(diff_cover, "run_subprocess", _dispatching_fake_run)

    raw = diff_cover.DiffCoverEngine().run(root, [], cwd=root)

    assert raw["provenance"]["digest"] == expected_digest

    status_digest = sha256(
        subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.encode("utf-8")
    ).hexdigest()
    assert raw["provenance"]["digest"] != status_digest


def test_the_comparison_ref_is_resolved_to_a_pinned_sha_and_passed_directly_to_the_child_never_a_symbolic_branch_name_the_child_could_independently_move_past(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03h: `--compare-branch=` carries a resolved commit sha, never the
    symbolic branch name `main` -- pinning before invocation makes a branch
    that moves mid-scan structurally impossible to race, rather than merely
    detected after the fact."""
    import re

    from rush.engines import diff_cover

    root = tmp_path / "project"
    _init_git_repo(root)
    main_sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "main"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if argv[0] == "git":
            return subprocess.run(argv, capture_output=True, text=True, check=False)
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(diff_cover, "resolve_binary", lambda _binary: "diff-cover")
    monkeypatch.setattr(diff_cover, "run_subprocess", fake_run)

    diff_cover.DiffCoverEngine().run(root, [], cwd=root)

    assert len(calls) == 1
    compare_arg = next(a for a in calls[0] if a.startswith("--compare-branch="))
    resolved = compare_arg.removeprefix("--compare-branch=")
    assert resolved == main_sha
    assert re.fullmatch(r"[0-9a-f]{40}", resolved), "must be a real commit sha"
    assert resolved != "main"


def test_git_state_dependent_engines_git_guard_diff_cover_undercover_run_against_the_live_tree_never_the_staging_copy_and_carry_combined_git_link_plus_at_the_moment_of_read_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03h: all three repository-state-dependent engines stay pointed at
    the live tree even while a staged scan attempt is active, and each still
    carries its own real, at-the-moment-of-read evidence -- which combines
    with the shared Git-link (HEAD + dirty flag) to provide real provenance
    for this whole category, never Git-link metadata alone."""
    from rush.engines.diff_cover import DiffCoverEngine
    from rush.engines.git_guard import GitGuardEngine
    from rush.engines.staging import stage_inventory, staging_scope
    from rush.engines.undercover import UndercoverEngine
    from rush.runtime.subprocesses import _staged_invocation

    root = tmp_path / "project"
    _init_git_repo(root)

    staging_root = tmp_path / "staging"
    staging = stage_inventory(
        root, staging_root, project_run_module._scan_inventory(root)
    )
    with staging_scope(staging):
        for engine in (GitGuardEngine(), DiffCoverEngine(), UndercoverEngine()):
            resolved_staging, run_path, run_cwd, _ = _staged_invocation(
                engine, root, root, []
            )
            assert resolved_staging is None, (
                f"{engine.name} must never be redirected into the staging copy"
            )
            assert run_path == root
            assert run_cwd == root

        git_guard_raw = GitGuardEngine().run(root, [], cwd=root)

        from rush.engines import diff_cover as diff_cover_module
        from rush.engines import undercover as undercover_module

        monkeypatch.setattr(
            diff_cover_module, "resolve_binary", lambda _binary: "diff-cover"
        )
        monkeypatch.setattr(diff_cover_module, "run_subprocess", _dispatching_fake_run)
        diff_cover_raw = diff_cover_module.DiffCoverEngine().run(root, [], cwd=root)

        monkeypatch.setattr(
            undercover_module, "resolve_binary", lambda _binary: "undercover"
        )
        monkeypatch.setattr(
            undercover_module,
            "run_subprocess",
            lambda argv, **_kwargs: subprocess.CompletedProcess(
                argv, 0, stdout="[]", stderr=""
            ),
        )
        undercover_raw = undercover_module.UndercoverEngine().run(root, [], cwd=root)

    assert git_guard_raw["provenance"]["digest"]
    assert diff_cover_raw["provenance"]["digest"]
    assert undercover_raw["provenance"]["digest"]

    link = project_run_module._git_link(root)
    assert link["repository"] is True
    assert link["head"]


# --- P69-03.3 RED (subsections k/l/n): publication paths, sequence/identity -


def test_rescan_with_unchanged_source_bumps_sequence_not_source_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03l: `project_map.build_project_map` reads `sequence`/
    `source_identity` straight off the `snapshot` dict (project_map.py:
    427-428), but `_snapshot_from_scan_result` never sets either key --
    without mirroring `ProjectRecord.sequence`/`.source_identity` into
    `snapshot["sequence"]`/`snapshot["source_identity"]` at every publish,
    the map would silently report `sequence=1`/`source_identity=project_id`
    forever after every real scan. A rescan of genuinely unchanged source
    must still bump the map's reported sequence while leaving its reported
    source_identity byte-identical to before."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [ReviewTool()])
    project_id, root = _register(tmp_path)
    _server, ctx, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, body = _action(
            base_url, project_id, cookie, csrf, operation="provision_plan"
        )
        assert status == 200
        plan_id = body["data"]["scan_plan"]["plan_id"]
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_start",
            arguments={"plan_id": plan_id},
            grants=_grant_all(),
        )
        assert status == 202
        run_id = body["data"]["run_id"]
        _wait_until(lambda: ctx.projects.get(project_id).sequence == 2)

        record = ctx.projects.get(project_id)
        map_after_start = build_project_map(record.snapshot)
        assert map_after_start["sequence"] == 2
        source_identity_after_start = map_after_start["source_identity"]
        assert source_identity_after_start != project_id

        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="rescan",
            arguments={"run_id": run_id},
            grants=_grant_all(),
        )
        assert status == 202
        _wait_until(lambda: ctx.projects.get(project_id).sequence == 3)

        record = ctx.projects.get(project_id)
        map_after_rescan = build_project_map(record.snapshot)
        assert map_after_rescan["sequence"] == 3
        assert map_after_rescan["source_identity"] == source_identity_after_start
    finally:
        _server.shutdown()
        _server.server_close()


def test_memory_mutation_bumps_sequence_without_touching_source_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03l/n: `refresh_memories` bumps `ProjectRecord.sequence` but
    `build_project_map` only ever reads `snapshot.get("sequence"/
    "source_identity")` -- a dict-embedded copy `refresh_memories` alone
    never touched left the map showing `sequence=1` forever after a pure
    memory mutation. `source_identity` must stay byte-identical to whatever a
    scan last published (a memory edit never touches source tree state)."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    _server, ctx, _base_url, _cookie, _csrf = _start_dashboard(project_id, root)
    try:
        record = ctx.projects.get(project_id)
        record.snapshot["source_identity"] = "scan-source-identity-v1"
        record.source_identity = "scan-source-identity-v1"

        assert ctx.projects.refresh_memories(project_id, [{"id": "m1"}], generation=1)

        record = ctx.projects.get(project_id)
        map_data = build_project_map(record.snapshot)
        assert map_data["sequence"] == 2
        assert map_data["source_identity"] == "scan-source-identity-v1"
    finally:
        _server.shutdown()
        _server.server_close()


def test_initial_launch_scan_captures_provenance_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03k: `run_workflow_suite()` (the CHECK_SUITE initial-launch path
    `dashboard_cmd`'s `_run_initial_scan` drives) called no attempt-header/
    provenance capture at all -- unlike `execute_scan`/`resume_scan_run`/
    `rescan_project_run`, which all persist `_write_attempt_header()`'s
    pre-execution `source_signature` before their first candidate runs.
    `capture_initial_scan_provenance` must write that identical header
    before a single tool executes."""
    from rush.dashboard.server import (
        capture_initial_scan_provenance,
        publish_check_suite_scan,
    )
    from rush.workflows.project_run import _load_attempt_header

    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    attempt_dirs_seen_at_call_time: list[int] = []

    class _CheckHeaderTool:
        name = "lint"

        def __call__(
            self,
            path: Path,
            engine_args: list[str] | None = None,
            owner_instance_id: str | None = None,
            run_id: str | None = None,
        ) -> dict[str, object]:
            attempt_dirs = list((root / ".rush" / "runs").glob("*/attempts/*"))
            attempt_dirs_seen_at_call_time.append(len(attempt_dirs))
            assert attempt_dirs, "provenance header must exist before any tool runs"
            header = _load_attempt_header(attempt_dirs[0])
            assert header is not None
            assert header["source_signature"]
            return {
                "tool": "lint",
                "engine": "ruff",
                "engine_version": None,
                "status": "ok",
                "duration_ms": 1,
                "summary": "clean",
                "findings": [],
                "raw": None,
            }

    monkeypatch.setattr(suites_module, "ALL_TOOLS", [_CheckHeaderTool()])
    _server, ctx, _base_url, _cookie, _csrf = _start_dashboard(project_id, root)
    try:
        run_id, attempt_id = capture_initial_scan_provenance(root, project_id)
        aggregate = run_workflow_suite(
            suite=CHECK_SUITE, path=root, permissions=ExecutionPermissions()
        )
        run_id2, attempt_id2 = publish_check_suite_scan(
            ctx, project_id, root, aggregate, run_id=run_id, attempt_id=attempt_id
        )
        assert (run_id2, attempt_id2) == (run_id, attempt_id)
        assert attempt_dirs_seen_at_call_time == [1]
    finally:
        _server.shutdown()
        _server.server_close()


# --- P69-03.1/03.3 RED (subsections m/o): durable cross-process generation
# counter, published pointer, and stale-map rehydration -----------------------


def _map(base_url: str, project_id: str, cookie: str) -> dict[str, Any]:
    resp = _get(
        f"{base_url}/api/projects/{project_id}/snapshot?section=map",
        headers={"Cookie": cookie},
    )
    assert resp.status == 200
    return json.loads(resp.read())["data"]


def _publish_real_scan(ctx: Any, project_id: str, root: Path) -> tuple[str, str]:
    """One real CHECK_SUITE execution published through the production path
    (`publish_check_suite_scan`), which writes a real terminal manifest,
    allocates a durable generation, and records the published pointer."""
    aggregate = run_workflow_suite(
        suite=CHECK_SUITE, path=root, permissions=ExecutionPermissions()
    )
    return publish_check_suite_scan(ctx, project_id, root, aggregate)


def _write_attempt(
    root: Path, run_id: str, attempt_id: str, *, finding_id: str
) -> None:
    """A terminal attempt manifest written through the same relative path the
    production pipeline uses, with a real per-attempt generation header (which
    is what `load_run_manifest`'s latest-attempt resolution ranks on)."""
    from rush.workflows.project_run import _write_attempt_header

    _write_attempt_header(root, run_id, attempt_id, "plan-x", "project-x")
    attempt_dir = root / ".rush" / "runs" / run_id / "attempts" / attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=True)
    (attempt_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "attempt_id": attempt_id,
                "run_state": "completed",
                "aggregate": {
                    "findings": [
                        {
                            "finding_id": finding_id,
                            "path": "app.py",
                            "line": 1,
                            "severity": "warn",
                            "message": finding_id,
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )


def test_project_generations_first_publish_for_a_project_creates_the_row_starting_at_1_not_a_silent_no_op(
    tmp_path: Path,
) -> None:
    """P69-03m: the durable counter's very first allocation for a project has
    no row to increment -- a bare `UPDATE ... SET value = value + 1` would
    match zero rows and silently return nothing. `INSERT ... ON CONFLICT DO
    UPDATE ... RETURNING` must create the row at 1 and increment from there,
    per project."""
    ledger = MutationLedger(db_path=tmp_path / "ledger.db")

    assert ledger.published_pointer("project-a") is None
    assert ledger.allocate_scan_generation("project-a") == 1
    assert ledger.allocate_scan_generation("project-a") == 2
    assert ledger.allocate_scan_generation("project-a") == 3
    # Counters are per project, never one global sequence.
    assert ledger.allocate_scan_generation("project-b") == 1

    # Allocation alone never moves the published pointer: an accepted request
    # that has not executed yet must not point at a run with no results.
    assert ledger.published_pointer("project-a") is None
    assert ledger.record_published_scan("project-a", 3, "run-1", "attempt-1") is True
    assert ledger.published_pointer("project-a") == {
        "published_generation": 3,
        "run_id": "run-1",
        "attempt_id": "attempt-1",
    }


def test_two_independent_server_processes_allocate_non_colliding_increasing_scan_generation_values(
    tmp_path: Path,
) -> None:
    """P69-03m: a per-process in-memory counter cannot order publishes across
    two independent server processes -- each starts from its own baseline and
    hands out the same numbers. Two genuinely separate OS processes
    allocating against the same durable database file must between them
    produce every value exactly once, with each process's own sequence
    strictly increasing."""
    db_path = tmp_path / "ledger.db"
    child = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "from rush.dashboard.state import MutationLedger\n"
        "ledger = MutationLedger(db_path=Path(sys.argv[1]))\n"
        "print(json.dumps("
        "[ledger.allocate_scan_generation('project-a') for _ in range(25)]))\n"
    )
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", child, str(db_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    allocations: list[list[int]] = []
    for proc in procs:
        stdout, stderr = proc.communicate(timeout=120)
        assert proc.returncode == 0, stderr
        allocations.append(json.loads(stdout))

    for own in allocations:
        assert own == sorted(own)
        assert len(set(own)) == len(own)
    combined = sorted(allocations[0] + allocations[1])
    assert combined == list(range(1, 51))


def test_publication_pointer_update_is_a_compare_and_swap_a_lower_generation_never_overwrites_a_higher_one(
    tmp_path: Path,
) -> None:
    """P69-03m: recording the published pointer is a durable compare-and-swap,
    never an unconditional write -- a delayed publish that lost its race must
    leave the newer pointer (and the newer `published_generation`) exactly as
    it found them. `published_generation` stays a separate column from
    `value`: losing the CAS never rewinds the allocation counter."""
    ledger = MutationLedger(db_path=tmp_path / "ledger.db")
    slow = ledger.allocate_scan_generation("project-a")
    fast = ledger.allocate_scan_generation("project-a")
    assert (slow, fast) == (1, 2)

    assert ledger.record_published_scan("project-a", fast, "run-fast", "att-fast")
    # The slow job finishes later and tries to record its older generation.
    lost = ledger.record_published_scan("project-a", slow, "run-slow", "att-slow")
    assert lost is False
    assert ledger.published_pointer("project-a") == {
        "published_generation": fast,
        "run_id": "run-fast",
        "attempt_id": "att-fast",
    }
    # Equal generations lose too (strictly-newer wins only).
    assert (
        ledger.record_published_scan("project-a", fast, "run-dup", "att-dup") is False
    )
    assert ledger.published_pointer("project-a")["run_id"] == "run-fast"
    # The counter itself was never rewound by the losing publish.
    assert ledger.allocate_scan_generation("project-a") == 3
    assert ledger.record_published_scan("project-a", 3, "run-newest", "att-newest")
    assert ledger.published_pointer("project-a")["run_id"] == "run-newest"


def test_hydration_racing_a_newer_local_publish_loses_via_the_existing_generation_check_not_a_separate_mechanism(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03m/o: a hydration that read an already-superseded published
    generation must lose the very same `publish_scan_result` generation check
    every other completion goes through -- never a second, divergent
    staleness rule, and never overwriting a newer outcome."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(suites_module, "ALL_TOOLS", [_StubLint()])
    project_id, root = _register(tmp_path)
    _server, ctx, _base_url, _cookie, _csrf = _start_dashboard(project_id, root)
    try:
        _publish_real_scan(ctx, project_id, root)
        pointer = ctx.mutations.published_pointer(project_id)
        assert pointer["published_generation"] == 1

        # A faster, newer scan already landed in this server's registry.
        newer = {
            **_empty_snapshot(project_id, root),
            "findings": [{"id": "newer-finding"}],
        }
        assert ctx.projects.publish_scan_result(
            project_id,
            snapshot=newer,
            source_identity="newer-identity",
            generation=5,
        )

        server_module._hydrate_published_scan(ctx, project_id)

        record = ctx.projects.get(project_id)
        assert record.scan_generation == 5
        assert [f["id"] for f in record.snapshot["findings"]] == ["newer-finding"]
        assert record.source_identity == "newer-identity"

        # The same check, reached directly: a stale completion is a no-op.
        assert (
            ctx.projects.publish_scan_result(
                project_id,
                snapshot=_empty_snapshot(project_id, root),
                source_identity="stale-identity",
                generation=3,
            )
            is False
        )
        assert ctx.projects.get(project_id).source_identity == "newer-identity"
    finally:
        _server.shutdown()
        _server.server_close()


def test_load_run_manifest_with_explicit_attempt_id_loads_that_exact_attempt_not_latest(
    tmp_path: Path,
) -> None:
    """P69-03m: without an explicit `attempt_id`, `load_run_manifest` always
    resolves the run's highest-generation attempt -- so a later, unpublished
    attempt of the same run (a resume still in progress, or one that failed)
    silently shadows the actually-published one. The explicit parameter must
    skip latest-attempt resolution entirely; omitting it must keep today's
    behaviour."""
    from rush.workflows.project_run import load_run_manifest

    root = tmp_path / "project"
    root.mkdir()
    _write_attempt(root, "run-1", "att-published", finding_id="published-finding")
    _write_attempt(root, "run-1", "att-later", finding_id="later-finding")

    assert load_run_manifest(root, "run-1")["attempt_id"] == "att-later"
    pinned = load_run_manifest(root, "run-1", attempt_id="att-published")
    assert pinned["attempt_id"] == "att-published"
    assert pinned["aggregate"]["findings"][0]["finding_id"] == "published-finding"
    assert load_run_manifest(root, "run-1", attempt_id="never-existed") is None


def test_hydrating_server_discovers_the_current_published_run_and_attempt_from_the_durable_pointer_not_by_scanning_run_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03m/o: the admission row that would hint at the active run is
    released the moment its job reaches terminal state, so the
    `project_generations` pointer is the only durable record of which
    `(run_id, attempt_id)` is published. Hydration must read it first and load
    that exact attempt -- never enumerate run directories, and never take
    whichever attempt happens to be latest."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    _server, ctx, _base_url, _cookie, _csrf = _start_dashboard(project_id, root)
    try:
        generation = ctx.mutations.allocate_scan_generation(project_id)
        _write_attempt(root, "run-published", "att-1", finding_id="published-finding")
        # A later, unpublished attempt of the same run (higher attempt
        # generation, so latest-attempt resolution would pick it) plus an
        # entirely unrelated run directory: neither may be hydrated.
        _write_attempt(root, "run-published", "att-2", finding_id="unpublished-finding")
        _write_attempt(root, "run-unrelated", "att-1", finding_id="unrelated-finding")
        assert ctx.mutations.record_published_scan(
            project_id, generation, "run-published", "att-1"
        )

        loaded: list[tuple[str, str | None]] = []
        real_load = server_module.load_run_manifest

        def _spy(root_arg, run_id, *, attempt_id=None):
            loaded.append((run_id, attempt_id))
            return real_load(root_arg, run_id, attempt_id=attempt_id)

        monkeypatch.setattr(server_module, "load_run_manifest", _spy)
        server_module._hydrate_published_scan(ctx, project_id)

        assert loaded == [("run-published", "att-1")]
        record = ctx.projects.get(project_id)
        assert record.scan_generation == generation
        assert [f["id"] for f in record.snapshot["findings"]] == ["published-finding"]
    finally:
        _server.shutdown()
        _server.server_close()


def test_a_second_server_reading_a_published_run_it_never_executed_hydrates_its_own_map_from_the_manifest_not_just_its_publication_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03o: a second dashboard server attached to the same project shows
    its *own* `record.snapshot`'s empty scan data through `section=map` -- the
    published attempt's own `publication` field being correct on disk hydrates
    nothing in this server's registry. The current-map request path must
    detect the drift against the durable pointer and rebuild through the same
    `_snapshot_from_scan_result` adapter a live execution result uses."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(suites_module, "ALL_TOOLS", [_StubLint()])
    project_id, root = _register(tmp_path)
    server_a, ctx_a, _url_a, _cookie_a, _csrf_a = _start_dashboard(project_id, root)
    server_b, ctx_b, url_b, cookie_b, _csrf_b = _start_dashboard(project_id, root)
    try:
        _publish_real_scan(ctx_a, project_id, root)
        published = ctx_a.mutations.published_pointer(project_id)

        # The second server executed nothing: its own registry is still empty.
        assert ctx_b.projects.get(project_id).scan_generation == 0
        assert ctx_b.projects.get(project_id).snapshot["findings"] == []

        data = _map(url_b, project_id, cookie_b)

        record_b = ctx_b.projects.get(project_id)
        assert record_b.scan_generation == published["published_generation"]
        assert len(record_b.snapshot["findings"]) == 1
        assert [n["kind"] for n in data["nodes"]].count("finding") == 1
        # Same evidence identity server A published, not a re-derived one.
        assert (
            record_b.snapshot["findings"][0]["id"]
            == ctx_a.projects.get(project_id).snapshot["findings"][0]["id"]
        )
    finally:
        for server in (server_b, server_a):
            server.shutdown()
            server.server_close()


def test_a_restarted_server_rehydrates_its_map_from_the_latest_published_manifest_on_first_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03o: the same drift, across a restart -- the registry is rebuilt
    empty in the new process, and only the durable pointer survives. The very
    first current-map request must serve the published scan, not an empty
    map, without waiting for this server to run a scan of its own."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(suites_module, "ALL_TOOLS", [_StubLint()])
    project_id, root = _register(tmp_path)
    server_a, ctx_a, _url_a, _cookie_a, _csrf_a = _start_dashboard(project_id, root)
    try:
        _publish_real_scan(ctx_a, project_id, root)
        published = ctx_a.mutations.published_pointer(project_id)
        finding_id = ctx_a.projects.get(project_id).snapshot["findings"][0]["id"]
    finally:
        server_a.shutdown()
        server_a.server_close()

    server_b, ctx_b, url_b, cookie_b, _csrf_b = _start_dashboard(project_id, root)
    try:
        assert ctx_b.projects.get(project_id).snapshot["findings"] == []

        data = _map(url_b, project_id, cookie_b)

        record_b = ctx_b.projects.get(project_id)
        assert record_b.scan_generation == published["published_generation"]
        assert [f["id"] for f in record_b.snapshot["findings"]] == [finding_id]
        assert [n["kind"] for n in data["nodes"]].count("finding") == 1
        assert data["sequence"] == record_b.sequence
    finally:
        server_b.shutdown()
        server_b.server_close()


# --- P69-03.1/03.3 RED (subsections r/s/v, CONNECT): historical run
# identity, frozen historical memory/agent data, and the per-attempt
# publication outcome record -----------------------------------------------


def test_iter_run_manifests_uses_the_shared_generation_based_selector_not_its_own_uuid_sort(
    tmp_path: Path,
) -> None:
    """P69-03r: `_iter_run_manifests` (`workflows/projects.py`) carried its
    own, third, independent `sorted(attempts)[-1]` UUID-lexicographic
    selector -- the identical drift point P69-02k's shared
    `_highest_generation_attempt_dir()` fix already warned about for the
    other two selectors. A lexicographically-earlier attempt carrying a
    real `attempt_generation` header must win over a lexicographically-later
    one that has none (a legacy, pre-P69-02k attempt)."""

    def _write_manifest(attempt_id: str, finding_id: str) -> None:
        attempt_dir = root / ".rush" / "runs" / "run-1" / "attempts" / attempt_id
        attempt_dir.mkdir(parents=True, exist_ok=True)
        (attempt_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "run_id": "run-1",
                    "attempt_id": attempt_id,
                    "run_state": "completed",
                    "aggregate": {
                        "findings": [{"finding_id": finding_id, "path": "app.py"}]
                    },
                }
            ),
            encoding="utf-8",
        )

    root = tmp_path / "project"
    root.mkdir()
    # Lexicographically last, but no attempt_generation header at all.
    _write_manifest("z-legacy", "legacy-finding")
    # Lexicographically first, but carries a real attempt_generation header
    # -- must win regardless of UUID sort order.
    from rush.workflows.project_run import _write_attempt_header

    _write_attempt_header(root, "run-1", "a-newer", "plan-x", "project-x")
    _write_manifest("a-newer", "newer-finding")

    manifests = projects_module._iter_run_manifests(root)
    assert len(manifests) == 1
    assert manifests[0]["attempt_id"] == "a-newer"
    assert manifests[0]["aggregate"]["findings"][0]["finding_id"] == "newer-finding"


def test_map_selects_historical_run_by_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03r: a caller-selected historical run is pinned to its exact
    `(run_id, attempt_id)` -- never bare `run_id` -- and stays selected even
    after that same `run_id` is later resumed with a new attempt. An
    unrecognized `(run_id, attempt_id)` is rejected with 404, never silently
    falling back to the current map."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    _server, ctx, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        _write_attempt(root, "run-a", "att-a", finding_id="finding-a")

        gen = ctx.mutations.allocate_scan_generation(project_id)
        server_module._publish_scan_snapshot(
            ctx,
            project_id,
            root,
            {
                "findings": [
                    {
                        "finding_id": "finding-current",
                        "path": "app.py",
                        "line": 1,
                        "severity": "warn",
                        "message": "current",
                    }
                ]
            },
            generation=gen,
            run_id="run-current",
            attempt_id="att-current",
        )

        current_data = _map(base_url, project_id, cookie)
        assert {n["id"] for n in current_data["nodes"] if n["kind"] == "finding"} == {
            "finding:finding-current"
        }

        resp = _get(
            f"{base_url}/api/projects/{project_id}/snapshot"
            "?section=map&run_id=run-a&attempt_id=att-a",
            headers={"Cookie": cookie},
        )
        assert resp.status == 200
        historical_data = json.loads(resp.read())["data"]
        assert historical_data["run_id"] == "run-a"
        assert historical_data["attempt_id"] == "att-a"
        assert {
            n["id"] for n in historical_data["nodes"] if n["kind"] == "finding"
        } == {"finding:finding-a"}

        # A resume of "run-a" (a new attempt) must not change the pinned
        # historical selection for the original attempt.
        _write_attempt(root, "run-a", "att-a-resumed", finding_id="finding-a-resumed")
        resp_again = _get(
            f"{base_url}/api/projects/{project_id}/snapshot"
            "?section=map&run_id=run-a&attempt_id=att-a",
            headers={"Cookie": cookie},
        )
        again_data = json.loads(resp_again.read())["data"]
        assert {n["id"] for n in again_data["nodes"] if n["kind"] == "finding"} == {
            "finding:finding-a"
        }

        missing = _get(
            f"{base_url}/api/projects/{project_id}/snapshot"
            "?section=map&run_id=run-a&attempt_id=never-existed",
            headers={"Cookie": cookie},
        )
        assert missing.status == 404
    finally:
        _server.shutdown()
        _server.server_close()


def test_historical_attempt_memory_agent_data_is_frozen_not_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03s: the adapter in subsection a merges *current* memory/agent
    data into every snapshot it builds, including historical ones -- a
    historical view's memory node isn't actually frozen and can change out
    from under a supposedly-immutable historical cache entry. The frozen
    data must be captured once, at first request for this exact
    `(run_id, attempt_id)`, and never re-derived from the live registry on a
    later request."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    _server, ctx, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        _write_attempt(root, "run-a", "att-a", finding_id="finding-a")
        assert ctx.projects.refresh_memories(
            project_id, [{"id": "m-original"}], generation=1
        )

        resp = _get(
            f"{base_url}/api/projects/{project_id}/snapshot"
            "?section=map&run_id=run-a&attempt_id=att-a",
            headers={"Cookie": cookie},
        )
        first = json.loads(resp.read())["data"]
        assert {n["id"] for n in first["nodes"] if n["kind"] == "memory"} == {
            "memory:m-original"
        }

        # The live registry's memory data changes entirely after the
        # historical snapshot was frozen.
        assert ctx.projects.refresh_memories(
            project_id, [{"id": "m-new"}], generation=2
        )

        resp_again = _get(
            f"{base_url}/api/projects/{project_id}/snapshot"
            "?section=map&run_id=run-a&attempt_id=att-a",
            headers={"Cookie": cookie},
        )
        again = json.loads(resp_again.read())["data"]
        assert {n["id"] for n in again["nodes"] if n["kind"] == "memory"} == {
            "memory:m-original"
        }

        current = _map(base_url, project_id, cookie)
        assert {n["id"] for n in current["nodes"] if n["kind"] == "memory"} == {
            "memory:m-new"
        }
    finally:
        _server.shutdown()
        _server.server_close()


def test_historical_snapshot_survives_cache_eviction_and_restart_identically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03s: the frozen historical memory/agent data is persisted into
    the attempt's own manifest, so a restart -- a brand-new process whose
    registry starts empty, with no memory of the first process's live state
    at all -- reconstructs the identical frozen graph rather than freezing a
    second, different moment."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)

    server_a, ctx_a, url_a, cookie_a, _csrf_a = _start_dashboard(project_id, root)
    try:
        _write_attempt(root, "run-a", "att-a", finding_id="finding-a")
        assert ctx_a.projects.refresh_memories(
            project_id, [{"id": "m-frozen"}], generation=1
        )
        resp = _get(
            f"{url_a}/api/projects/{project_id}/snapshot"
            "?section=map&run_id=run-a&attempt_id=att-a",
            headers={"Cookie": cookie_a},
        )
        frozen_at_a = json.loads(resp.read())["data"]
        assert {n["id"] for n in frozen_at_a["nodes"] if n["kind"] == "memory"} == {
            "memory:m-frozen"
        }
    finally:
        server_a.shutdown()
        server_a.server_close()

    server_b, ctx_b, url_b, cookie_b, _csrf_b = _start_dashboard(project_id, root)
    try:
        assert ctx_b.projects.get(project_id).snapshot.get("memories") == []
        resp_b = _get(
            f"{url_b}/api/projects/{project_id}/snapshot"
            "?section=map&run_id=run-a&attempt_id=att-a",
            headers={"Cookie": cookie_b},
        )
        frozen_at_b = json.loads(resp_b.read())["data"]
        assert {n["id"] for n in frozen_at_b["nodes"] if n["kind"] == "memory"} == {
            "memory:m-frozen"
        }
    finally:
        server_b.shutdown()
        server_b.server_close()


def test_per_run_publication_record_answers_independent_of_newest_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03v: the map/snapshot's own publication marker only ever exposes
    "most recently published" -- a later, unrelated run's publication must
    not make an earlier run's own `(run_id, attempt_id)` publication record
    disappear or change, even though that earlier run is no longer the
    active snapshot."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(suites_module, "ALL_TOOLS", [_StubLint()])
    project_id, root = _register(tmp_path)
    _server, ctx, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        aggregate_a = run_workflow_suite(
            suite=CHECK_SUITE, path=root, permissions=ExecutionPermissions()
        )
        run_a, _attempt_a = publish_check_suite_scan(ctx, project_id, root, aggregate_a)

        aggregate_b = run_workflow_suite(
            suite=CHECK_SUITE, path=root, permissions=ExecutionPermissions()
        )
        run_b, _attempt_b = publish_check_suite_scan(ctx, project_id, root, aggregate_b)
        assert run_b != run_a

        status_a, scans_a = _scans(base_url, project_id, cookie, run_id=run_a)
        assert status_a == 200
        assert scans_a["data"]["publication"] == "published"

        status_b, scans_b = _scans(base_url, project_id, cookie, run_id=run_b)
        assert status_b == 200
        assert scans_b["data"]["publication"] == "published"
    finally:
        _server.shutdown()
        _server.server_close()


def test_unpublished_run_id_reports_not_yet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03v: no attempt matching a requested `(run_id, attempt_id)` has
    reached `publish_scan_result` -- the field must be present and explicit
    (`not_yet`), never silently absent."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    _server, _ctx, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, scans = _scans(base_url, project_id, cookie, run_id="never-existed")
        assert status == 200
        assert scans["data"]["publication"] == "not_yet"
    finally:
        _server.shutdown()
        _server.server_close()


def test_a_completion_that_loses_the_generation_race_reports_superseded_not_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03v: an attempt that reaches `publish_scan_result` but loses its
    generation race (a slower, earlier-accepted completion racing a faster,
    later-accepted one that already published) still reports its own real
    outcome for its own `(run_id, attempt_id)` -- `superseded`, never
    absent."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(suites_module, "ALL_TOOLS", [_StubLint()])
    project_id, root = _register(tmp_path)
    _server, ctx, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        gen_early = ctx.mutations.allocate_scan_generation(project_id)
        gen_late = ctx.mutations.allocate_scan_generation(project_id)
        assert gen_late > gen_early

        aggregate = run_workflow_suite(
            suite=CHECK_SUITE, path=root, permissions=ExecutionPermissions()
        )
        # A later-accepted attempt publishes first (a faster, later scan
        # completing before an earlier-accepted, slower one).
        run_late, _attempt_late = publish_check_suite_scan(
            ctx, project_id, root, aggregate, scan_generation=gen_late
        )
        run_early, _attempt_early = publish_check_suite_scan(
            ctx, project_id, root, aggregate, scan_generation=gen_early
        )
        assert run_early != run_late

        status_early, scans_early = _scans(
            base_url, project_id, cookie, run_id=run_early
        )
        assert status_early == 200
        assert scans_early["data"]["publication"] == "superseded"

        _status_late, scans_late = _scans(base_url, project_id, cookie, run_id=run_late)
        assert scans_late["data"]["publication"] == "published"
    finally:
        _server.shutdown()
        _server.server_close()


def test_publication_query_resolves_the_correct_attempt_not_whichever_attempt_id_is_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03v: an optional `attempt_id` query parameter lets a caller
    holding a specific historical attempt id query that exact attempt's own
    outcome; omitting it resolves the latest attempt's own outcome -- never
    a blend with an earlier attempt's."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(suites_module, "ALL_TOOLS", [_StubLint()])
    project_id, root = _register(tmp_path)
    _server, ctx, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        aggregate = run_workflow_suite(
            suite=CHECK_SUITE, path=root, permissions=ExecutionPermissions()
        )
        run_id, _attempt_1 = publish_check_suite_scan(
            ctx, project_id, root, aggregate, run_id="run-x", attempt_id="att-1"
        )
        assert run_id == "run-x"

        # A second, later attempt of the same run is written but never
        # published (still running, or failed before publish).
        _write_attempt(root, "run-x", "att-2", finding_id="unpublished-finding")

        status, scans = _scans(base_url, project_id, cookie, run_id="run-x")
        assert status == 200
        assert scans["data"]["run"]["run_id"] == "run-x"
        assert scans["data"]["publication"] == "not_yet"

        status_pinned, scans_pinned = _scans(
            base_url, project_id, cookie, run_id="run-x", attempt_id="att-1"
        )
        assert status_pinned == 200
        assert scans_pinned["data"]["publication"] == "published"
    finally:
        _server.shutdown()
        _server.server_close()


def test_current_map_reloads_memory_mutated_entirely_outside_this_dashboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-03o, the memory half: `refresh_memories()` only ever ran when this
    dashboard's own dispatch functions called it, so a standalone TUI
    invocation, a bare CLI memory command, or a second server writing the same
    store left the current map showing stale memory indefinitely. The
    current-map request path must compare the store's real committed
    generation against the published `memory_generation` and reload when it
    has advanced."""
    from rush.memory.store import MemoryArtifact, TypedArtifactStore

    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    _server, ctx, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        assert ctx.projects.get(project_id).memory_generation == 0

        # Written straight to the store: this dashboard's dispatchers are
        # never involved, so nothing calls `refresh_memories()` for it.
        TypedArtifactStore(root).write(
            MemoryArtifact(
                id="external-memory",
                family="memory",
                subject="domain_knowledge",
                trust_tier="DERIVED",
                content={"note": "written outside this dashboard"},
                source="external-tool",
                created_at=time.time(),
            )
        )

        data = _map(base_url, project_id, cookie)

        record = ctx.projects.get(project_id)
        assert record.memory_generation > 0
        assert [m["id"] for m in record.snapshot["memories"]] == ["external-memory"]
        assert [n["kind"] for n in data["nodes"]].count("memory") == 1
    finally:
        _server.shutdown()
        _server.server_close()


# ---------------------------------------------------------------------------
# P69-06g/h/i -- the q-with-running-work three-way menu (Detach/Cancel run
# and stay/Return, per Phase 66 S3.9 and this plan's own S3 Detach-ownership
# clarification), Detach's force-exit actually stopping owned subprocess
# groups (P69-01's `reap_owner_processes`, reused as-is), and
# `recovery_required` replacing `unresolved_cancellation` as the durable,
# never-TTL-pruned status a dead local run's row is left in for a later
# invocation's generic recovery sweep (`reconcile_admissions`, unmodified)
# to reconcile through the same owner-liveness lock as any other row.
#
# NOTE (plan-doc inconsistency, flagged in this packet's own receipt): the
# plan's official P69-06.4 VERIFY command line does not list this file even
# though its own RED step (P69-06.2h/i, "Add tests/test_dashboard_map.py::
# ...") names these tests as belonging here -- this packet's real verify
# gate runs this file alongside the official command.
# ---------------------------------------------------------------------------


def _local_scan_actions(**overrides: object) -> tui_module.ScanActions:
    base: dict[str, object] = {
        "plan_scan": lambda root, **k: SimpleNamespace(
            plan_id="plan-1", candidates=[1, 2]
        ),
        "execute_scan": lambda plan, **k: SimpleNamespace(
            aggregate={"tool": "x", "status": "ok", "findings": []}
        ),
        "cancel_scan_run": lambda *a, **k: {},
        "rescan_project_run": lambda *a, **k: {"run": {"run_id": "r2"}},
        "build_handoff": lambda *a, **k: None,
        "dispatch_handoff": lambda *a, **k: None,
        "load_scan_events": lambda *a, **k: {"events": [], "run_state": None},
        "list_agents": list,
    }
    base.update(overrides)
    return tui_module.ScanActions(**base)


def _local_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[tui_module.ProjectState, str]:
    """Isolated data root, a registered project, and a fresh
    `tui._OWNER_INSTANCE` mint. `_tui_owner_instance_id()` caches its result
    for this whole process's lifetime, so each test that needs its own fresh
    owner lock (against its own tmp_path data root) must reset it."""
    _isolate_data_roots(tmp_path, monkeypatch)
    tui_module._OWNER_INSTANCE.clear()
    project_id, root = _register(tmp_path)
    return tui_module.ProjectState(name="demo", root=root), project_id


class _FakeDashboardOwner:
    """Stand-in for a live dashboard server discovered at scan-start time --
    same contract as `tests/test_tui.py`'s own `_FakeDashboardOwner`, kept
    local here since it is a private test helper, not a shared fixture."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def dispatch(self, operation: str, **arguments: object) -> dict:
        self.calls.append((operation, dict(arguments)))
        return {"operation_id": f"op-{len(self.calls)}", "run_id": "dashboard-run"}


def test_standalone_tui_process_acquires_its_own_owner_lock_before_reserving_local_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, project_id = _local_project(tmp_path, monkeypatch)
    gate = threading.Event()
    actions = _local_scan_actions(
        execute_scan=lambda plan, **k: (
            gate.wait(timeout=5),
            SimpleNamespace(aggregate={}),
        )[1]
    )
    tui_module._start_scan_thread(project, actions)
    try:
        assert project.owner == "local"
        assert project.owner_instance_id
        lock_path = (
            tmp_path / "rush-data" / "owners" / f"{project.owner_instance_id}.lock"
        )
        assert lock_path.exists(), (
            "no owner-liveness lock acquired before reserving local work"
        )
        assert project.ledger_admitted
        admission = MutationLedger().admission_for_project(project_id)
        assert admission is not None
        assert admission["owner_instance_id"] == project.owner_instance_id
    finally:
        gate.set()
        project.scan_thread.join(timeout=5)


def test_recovery_rejects_a_claim_while_the_actual_tui_process_is_still_alive(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "rush-data"
    owner_id = "tui:alive"
    OwnerLock(owner_id, data_root=data_root)  # held for this process's lifetime
    with claim_dead_owner(owner_id, data_root=data_root) as claimed:
        assert claimed is False, "recovery must not claim a live owner's lock"


def test_q_menu_offers_all_three_choices_detach_cancel_and_stay_return_distinctly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _ = _local_project(tmp_path, monkeypatch)
    project.status = "scanning"
    project.run_id = "run-1"
    cancel_calls: list[str] = []
    actions = _local_scan_actions(
        cancel_scan_run=lambda root, run_id: cancel_calls.append(run_id)
    )
    state = tui_module.TuiState(projects=[project])

    tui_module._dispatch_key(state, "q", actions)
    assert state.mode == "quit_confirm"

    tui_module._dispatch_key(state, "r", actions)
    assert state.mode == "list"
    assert state.should_quit is False

    project.status = "scanning"
    tui_module._dispatch_key(state, "q", actions)
    tui_module._dispatch_key(state, "c", actions)
    assert state.mode == "list"
    assert state.should_quit is False
    assert cancel_calls == ["run-1"]
    assert project.status == "cancelling"

    project.owner = "dashboard"  # trivial Detach case (a): no wait, no cancel
    project.status = "scanning"
    tui_module._dispatch_key(state, "q", actions)
    tui_module._dispatch_key(state, "d", actions)
    assert state.should_quit is True


def test_cancel_and_stay_does_not_exit_the_tui_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _ = _local_project(tmp_path, monkeypatch)
    project.status = "scanning"
    project.run_id = "run-1"
    calls: list[str] = []
    actions = _local_scan_actions(
        cancel_scan_run=lambda root, run_id: calls.append(run_id)
    )
    state = tui_module.TuiState(projects=[project])
    state.mode = "quit_confirm"

    tui_module._handle_cancel_and_stay(state, project, actions)

    assert state.should_quit is False
    assert state.mode == "list"
    assert calls == ["run-1"]
    assert project.status == "cancelling"


def test_cancel_and_stay_never_exits_even_past_the_5s_window_a_late_worker_acknowledgment_still_lands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _ = _local_project(tmp_path, monkeypatch)
    project.status = "scanning"
    project.run_id = "run-1"
    project.plan_total = 1
    events_state: dict[str, object] = {"events": [], "run_state": "running"}
    actions = _local_scan_actions(
        cancel_scan_run=lambda *a, **k: None,
        load_scan_events=lambda *a, **k: dict(events_state),
    )
    state = tui_module.TuiState(projects=[project])
    state.mode = "quit_confirm"

    t0 = time.monotonic()
    tui_module._handle_cancel_and_stay(state, project, actions)
    elapsed = time.monotonic() - t0
    assert elapsed < 1.0, "Cancel run and stay must never block waiting for ack"
    assert state.should_quit is False

    # A worker acknowledgment arriving well past Detach's own 5s window --
    # Cancel-run-and-stay has no timeout, so the still-open TUI's normal
    # render-tick polling must still observe it correctly, whenever it lands.
    events_state["run_state"] = "cancelled"
    tui_module._poll_running_scans(state, actions)
    assert project.status == "cancelled"
    assert state.should_quit is False


def test_detach_force_exit_terminates_owned_subprocess_groups_before_process_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _ = _local_project(tmp_path, monkeypatch)
    owner_id = "tui:detach-reap"
    project.owner = "local"
    project.owner_instance_id = owner_id
    project.status = "scanning"
    project.run_id = "run-1"
    project.plan_total = 1

    child = subprocess.Popen(
        ["sleep", "60"], start_new_session=True, stdin=subprocess.DEVNULL
    )
    pgid = child.pid
    # `child` is this test's own direct child -- a killed-but-unreaped
    # direct child is a zombie, and `kill(pid, 0)` still succeeds against a
    # zombie, so `terminate_owned_group`'s confirmation poll never observes
    # it as gone without something waiting on it. Production `.procs`
    # entries are not necessarily this process's own children (recovery
    # commonly reaps another process's), so this reaping is this test's own
    # harness concern, not something `terminate_owned_group` itself owns.
    threading.Thread(target=child.wait, daemon=True).start()
    _record_owned_process(owner_id, "run-1", pgid)
    try:
        actions = _local_scan_actions(
            cancel_scan_run=lambda *a, **k: None,
            load_scan_events=lambda *a, **k: {"events": [], "run_state": "running"},
        )
        state = tui_module.TuiState(projects=[project])
        state.mode = "quit_confirm"

        # A generous timeout here: `sleep 60` normally dies within
        # milliseconds of SIGTERM, but the confirmation poll's own interval
        # plus process-scheduling jitter under a loaded CI runner can miss a
        # tight deadline -- this is about giving `_wait_group_gone` enough
        # headroom to observe a real, fast termination, not about masking a
        # slow one.
        tui_module._handle_detach(state, project, actions, timeout=1.0)

        assert state.should_quit is True
        # A racy re-probe of `pgid` via `os.killpg` after the fact is not
        # reliable (the OS may already have recycled the pgid to an
        # unrelated process) -- `reap_owner_processes` only clears a
        # `.procs` record once its own confirmation poll (`_wait_group_gone`)
        # positively observed the group gone, so an empty record set here is
        # the real, non-racy contract this subsection guarantees.
        assert (
            read_owned_process_records(owner_id, data_root=tmp_path / "rush-data") == []
        )
    finally:
        with suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, signal.SIGKILL)


def test_detach_force_exit_escalates_to_sigkill_when_a_descendant_ignores_sigterm_past_the_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _ = _local_project(tmp_path, monkeypatch)
    owner_id = "tui:detach-sigkill"
    project.owner = "local"
    project.owner_instance_id = owner_id
    project.status = "scanning"
    project.run_id = "run-1"
    project.plan_total = 1

    pid_file = tmp_path / "descendant-pid"
    leader = subprocess.Popen(
        [
            "/bin/sh",
            "-c",
            f"sh -c 'trap \"\" TERM; sleep 60' & echo $! > {pid_file}; exit 0",
        ],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
    )
    pgid = leader.pid
    _record_owned_process(owner_id, "run-1", pgid)
    try:
        deadline = time.monotonic() + 5.0
        while not (pid_file.exists() and pid_file.read_text().strip()):
            assert time.monotonic() < deadline, "descendant never recorded its pid"
            time.sleep(0.02)
        leader.wait(timeout=5)

        actions = _local_scan_actions(
            cancel_scan_run=lambda *a, **k: None,
            load_scan_events=lambda *a, **k: {"events": [], "run_state": "running"},
        )
        state = tui_module.TuiState(projects=[project])
        state.mode = "quit_confirm"

        tui_module._handle_detach(state, project, actions, timeout=1.0)

        assert state.should_quit is True
        # See the identical comment in the SIGTERM-only test above: a
        # non-racy `.procs`-record check, not a re-probe of a pgid the OS
        # may already have recycled.
        assert (
            read_owned_process_records(owner_id, data_root=tmp_path / "rush-data") == []
        )
    finally:
        with suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, signal.SIGKILL)


def test_recovery_required_is_never_ttl_pruned_like_pending(tmp_path: Path) -> None:
    ledger = MutationLedger(db_path=tmp_path / "ledger.db")
    reservation = ledger.reserve(
        "proj-1", request_id="req-1", body_hash="", operation_type="scan_start"
    )
    op_id = reservation.operation_id
    ledger.record_status_transition(
        op_id, "recovery_required", {"status": "recovery_required"}
    )

    pruned = ledger.prune_expired(ttl_seconds=0)

    assert pruned == 0
    status = ledger.get_operation_status(op_id)
    assert status is not None
    assert status["status"] == "recovery_required"


def test_late_worker_acknowledgment_racing_the_timeout_uses_cas_not_a_blind_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _ = _local_project(tmp_path, monkeypatch)
    project.operation_id = "op-race"
    project.owner_instance_id = "tui:race"
    project.ledger_admitted = True
    project.run_resolved = False

    winner = tui_module._resolve_local_run(project)
    loser = tui_module._resolve_local_run(project)

    assert winner is True
    assert loser is False


def test_recovery_claims_a_recovery_required_row_through_the_same_ownership_lock_as_any_other_pending_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    data_root = tmp_path / "rush-data"
    project_id, _root = _register(tmp_path)
    owner_id = "tui:recovery-claim"
    op_id_file = tmp_path / "op_id.txt"

    child_pid = os.fork()
    if child_pid == 0:  # pragma: no cover -- child process, never reported by pytest
        try:
            OwnerLock(owner_id, data_root=data_root)
            ledger = MutationLedger()
            reservation = ledger.reserve(
                project_id,
                request_id="tui-local:run-x",
                body_hash="",
                operation_type="scan_start:plan-1",
            )
            op_id = reservation.operation_id
            ledger.admit(
                project_id,
                execution_identity="scan_start:plan-1",
                slot_id=op_id,
                operation_id=op_id,
                run_id="run-x",
                plan_id="plan-1",
                owner_instance_id=owner_id,
            )
            ledger.record_status_transition(
                op_id, "recovery_required", {"status": "recovery_required"}
            )
            op_id_file.write_text(op_id)
        finally:
            os._exit(0)
    os.waitpid(child_pid, 0)

    op_id = op_id_file.read_text()
    ledger = MutationLedger()
    assert ledger.get_operation_status(op_id)["status"] == "recovery_required"
    assert ledger.admission_for_project(project_id) is not None

    reconciled = reconcile_admissions(ledger, data_root=data_root)

    assert reconciled == 1
    assert ledger.admission_for_project(project_id) is None
    assert ledger.get_operation_status(op_id)["status"] == "terminal"


def test_recovery_required_is_reconciled_by_a_later_invocations_recovery_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    data_root = tmp_path / "rush-data"
    _project_id, root = _register(tmp_path)
    result_file = tmp_path / "result.json"

    child_pid = os.fork()
    if child_pid == 0:  # pragma: no cover -- child process, never reported by pytest
        try:
            tui_module._OWNER_INSTANCE.clear()
            project = tui_module.ProjectState(name="demo", root=root)
            never = threading.Event()
            actions = _local_scan_actions(
                execute_scan=lambda plan, **k: (
                    never.wait(timeout=30),
                    SimpleNamespace(aggregate={}),
                )[1],
            )
            tui_module._start_scan_thread(project, actions)
            time.sleep(0.2)
            state = tui_module.TuiState(projects=[project])
            tui_module._handle_detach(state, project, actions, timeout=0.2)
            result_file.write_text(
                json.dumps(
                    {
                        "op_id": project.operation_id,
                        "owner_id": project.owner_instance_id,
                    }
                )
            )
        finally:
            os._exit(0)
    os.waitpid(child_pid, 0)

    result = json.loads(result_file.read_text())
    op_id, owner_id = result["op_id"], result["owner_id"]

    ledger = MutationLedger()
    assert ledger.get_operation_status(op_id)["status"] == "recovery_required"
    with claim_dead_owner(owner_id, data_root=data_root) as claimed:
        assert claimed is True  # the crashed child's owner lock is provably gone

    reconciled = reconcile_admissions(ledger, data_root=data_root)
    assert reconciled == 1
    assert ledger.get_operation_status(op_id)["status"] == "terminal"


def test_cancel_waits_for_worker_acknowledgment_before_process_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _ = _local_project(tmp_path, monkeypatch)
    project.owner = "local"
    project.owner_instance_id = "tui:ack-test"
    project.status = "scanning"
    project.run_id = "run-1"
    project.plan_total = 1
    events_state: dict[str, object] = {"events": [], "run_state": "running"}

    def _cancel(*_a: object, **_k: object) -> dict:
        events_state["run_state"] = "cancelled"
        return {}

    actions = _local_scan_actions(
        cancel_scan_run=_cancel,
        load_scan_events=lambda *a, **k: dict(events_state),
    )
    state = tui_module.TuiState(projects=[project])
    state.mode = "quit_confirm"

    t0 = time.monotonic()
    tui_module._handle_detach(state, project, actions, timeout=5.0)
    elapsed = time.monotonic() - t0

    assert elapsed < 4.0, "must return promptly once acknowledged, not the full timeout"
    assert state.should_quit is True
    assert project.status == "cancelled"


def test_cancel_timeout_marks_recovery_required_not_silent_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, project_id = _local_project(tmp_path, monkeypatch)
    gate = threading.Event()
    actions = _local_scan_actions(
        execute_scan=lambda plan, **k: (
            gate.wait(timeout=10),
            SimpleNamespace(aggregate={}),
        )[1],
        cancel_scan_run=lambda *a, **k: None,  # accepted; the fake worker never stops
        load_scan_events=lambda *a, **k: {"events": [], "run_state": "running"},
    )
    tui_module._start_scan_thread(project, actions)
    time.sleep(0.2)
    state = tui_module.TuiState(projects=[project])
    state.mode = "quit_confirm"

    tui_module._handle_detach(state, project, actions, timeout=0.3)

    assert state.should_quit is True
    ledger = MutationLedger()
    status = ledger.get_operation_status(project.operation_id)
    assert status is not None
    assert status["status"] == "recovery_required", status
    assert ledger.admission_for_project(project_id) is not None, (
        "the row must stay present for recovery, never silently dropped"
    )
    gate.set()


def test_dashboard_owned_scan_then_rescan_stays_dashboard_owned_not_silently_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _ = _local_project(tmp_path, monkeypatch)
    owner = _FakeDashboardOwner()
    actions = _local_scan_actions(dashboard_owner=lambda root: owner)

    tui_module._start_scan_thread(project, actions)
    project.scan_thread.join(timeout=5)
    assert project.owner == "dashboard"

    tui_module._start_rescan_thread(project, actions)
    project.scan_thread.join(timeout=5)
    assert project.owner == "dashboard"
    assert [call[0] for call in owner.calls] == ["scan_start", "rescan"]


def test_quit_after_dashboard_owned_rescan_cancels_the_correct_run_not_a_stale_local_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _ = _local_project(tmp_path, monkeypatch)
    project.run_id = "stale-local-run"
    owner = _FakeDashboardOwner()
    actions = _local_scan_actions(dashboard_owner=lambda root: owner)

    tui_module._start_rescan_thread(project, actions)
    project.scan_thread.join(timeout=5)
    assert project.owner == "dashboard"
    assert project.run_id == "dashboard-run"

    cancel_calls: list[str] = []
    project.status = "scanning"
    actions_with_cancel = _local_scan_actions(
        dashboard_owner=lambda root: owner,
        cancel_scan_run=lambda root, run_id: cancel_calls.append(run_id),
    )
    tui_module._request_cancel(project, actions_with_cancel)
    assert cancel_calls == ["dashboard-run"], (
        "Cancel run and stay must target the current run, never the stale "
        "pre-rescan local one"
    )


def test_scan_start_with_live_dashboard_server_dispatches_through_its_http_action_not_a_local_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _ = _local_project(tmp_path, monkeypatch)
    owner = _FakeDashboardOwner()
    local_calls: list[int] = []
    actions = _local_scan_actions(
        dashboard_owner=lambda root: owner,
        execute_scan=lambda plan, **k: local_calls.append(1),
    )

    tui_module._start_scan_thread(project, actions)
    project.scan_thread.join(timeout=5)

    assert project.owner == "dashboard"
    assert owner.calls and owner.calls[0][0] == "scan_start"
    assert local_calls == [], "must never fall back to a local daemon thread"


def test_detach_with_dashboard_owned_scan_survives_tui_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _ = _local_project(tmp_path, monkeypatch)
    owner = _FakeDashboardOwner()
    actions = _local_scan_actions(dashboard_owner=lambda root: owner)

    tui_module._start_scan_thread(project, actions)
    state = tui_module.TuiState(projects=[project])
    state.mode = "quit_confirm"

    t0 = time.monotonic()
    tui_module._handle_detach(state, project, actions)
    elapsed = time.monotonic() - t0

    assert elapsed < 1.0, "case (a) Detach is trivial -- it must never wait or cancel"
    assert state.should_quit is True
    assert all(call[0] != "cancel" for call in owner.calls)
    if project.scan_thread is not None:
        project.scan_thread.join(timeout=2)


def test_detach_with_no_dashboard_server_running_is_cancel_with_saved_partial_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _project_id = _local_project(tmp_path, monkeypatch)
    events_state: dict[str, object] = {"events": [], "run_state": "running"}

    def _cancel(*_a: object, **_k: object) -> dict:
        events_state["run_state"] = "cancelled"
        return {}

    actions = _local_scan_actions(
        cancel_scan_run=_cancel,
        load_scan_events=lambda *a, **k: dict(events_state),
    )
    tui_module._start_scan_thread(project, actions)
    time.sleep(0.05)
    state = tui_module.TuiState(projects=[project])
    state.mode = "quit_confirm"

    tui_module._handle_detach(state, project, actions, timeout=2.0)

    assert project.owner == "local"
    assert state.should_quit is True
    assert project.status == "cancelled", (
        "Detach with no dashboard server is cancel-with-saved-partial-result"
    )
    if project.scan_thread is not None:
        project.scan_thread.join(timeout=5)
