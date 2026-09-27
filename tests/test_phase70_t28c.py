"""Phase 70 T28-C: TUI scan evidence and relationship navigation.

Tests-first only (no source changes). Binding design:
`.scratch/phase-70-design-gate/W4-T23-T29.md`, "### T28-C: scan evidence and
relationship navigation" plus the shared T28 design; plan packet T28-C in
`docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md`.

Cursor is removed from Phase 70 scope; nothing here targets it.

The brief names one selector, `test_t28c_results_and_relationships`
(in a module this packet doesn't own, `tests/test_phase70_tui_usability.py`).
That name is kept below for the zero-finding-summaries case (plan's own
first bullet); every other plan bullet and every T28-C-owned sub-contract
(`project_map_snapshot`, the `_scan_file_inventory` extraction) has its own
independently-diagnosable test, prefixed `test_t28c_`.

Merged at 2a664ec: T2, T3, T6, T8-T18, T20, T22, T23, T24, T26, TS.
Not merged: T1, T4, T5, T7, T19, T21, T25, T27, T28, T29 (T28-C included).
Every case below is RED against real, currently-merged source -- none
depends on an unmerged predecessor, so no `RED-via-Tn` label applies.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from rich.console import Console

from rush.dashboard.project_map import build_project_map
from rush.tools.base import Finding, ToolResult
from rush.tui import (
    ProjectState,
    _bounded_local_detail,
    _map_nodes,
    _render_project_table,
)
from rush.workflows.projects import register_project, resolve_project

# ---------------------------------------------------------------------------
# Local fixtures/helpers (no shared conftest -- this file is standalone).
# ---------------------------------------------------------------------------

_MANIFEST_TEMPLATE = ".rush/runs/{run_id}/attempts/{attempt_id}/manifest.json"
_ATTEMPT_HEADER_TEMPLATE = ".rush/runs/{run_id}/attempts/{attempt_id}/attempt.json"


def _tool_result(
    tool: str,
    status: str,
    *,
    engine: str | None = None,
    engine_version: str | None = None,
    summary: str = "",
    findings: list[Finding] | None = None,
    duration_ms: int = 5,
) -> ToolResult:
    return ToolResult(
        tool=tool,  # type: ignore[typeddict-item]
        engine=engine,
        engine_version=engine_version,
        status=status,  # type: ignore[typeddict-item]
        duration_ms=duration_ms,
        summary=summary,
        findings=findings or [],
    )


def _write_manifest(
    root: Path,
    *,
    run_id: str,
    attempt_id: str,
    findings: list[dict[str, Any]] | None = None,
    file_inventory: list[dict[str, str]] | None = None,
    frozen: dict[str, Any] | None = None,
    raw_text: str | None = None,
) -> Path:
    manifest_path = root / _MANIFEST_TEMPLATE.format(
        run_id=run_id, attempt_id=attempt_id
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_text is not None:
        manifest_path.write_text(raw_text, encoding="utf-8")
        return manifest_path
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "attempt_id": attempt_id,
        "aggregate": {"findings": findings or []},
    }
    if file_inventory is not None:
        manifest["file_inventory"] = file_inventory
    if frozen is not None:
        manifest["historical_memory_agent_snapshot"] = frozen
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest_path


def _write_attempt_header(
    root: Path,
    *,
    run_id: str,
    attempt_id: str,
    started_at: datetime,
    project_id: str | None = None,
    generation: int | None = 1,
) -> Path:
    """A real `select_attempt_chronology`-validated attempt header (see
    `workflows/projects.py::_load_attempt`): identities must match their
    directories, `started_at` must be ISO-8601 UTC, and a present
    `attempt_generation` must be a positive int."""
    header_path = root / _ATTEMPT_HEADER_TEMPLATE.format(
        run_id=run_id, attempt_id=attempt_id
    )
    header_path.parent.mkdir(parents=True, exist_ok=True)
    header: dict[str, Any] = {
        "run_id": run_id,
        "attempt_id": attempt_id,
        "started_at": started_at.isoformat(),
    }
    if project_id is not None:
        header["project_id"] = project_id
    if generation is not None:
        header["attempt_generation"] = generation
    header_path.write_text(json.dumps(header), encoding="utf-8")
    return header_path


def _write_handoff(
    root: Path,
    *,
    handoff_id: str,
    run_id: str,
    agent_id: str,
    finding_ids: list[str],
) -> Path:
    """A real `.rush/handoffs/*.json` packet subset, matching
    `ScanHandoff.to_dict()`'s field names (`project_run.py`)."""
    handoffs_dir = root / ".rush" / "handoffs"
    handoffs_dir.mkdir(parents=True, exist_ok=True)
    path = handoffs_dir / f"{handoff_id}.json"
    path.write_text(
        json.dumps(
            {
                "handoff_id": handoff_id,
                "run_id": run_id,
                "agent_id": agent_id,
                "finding_ids": finding_ids,
            }
        ),
        encoding="utf-8",
    )
    return path


def _project(tmp_path: Path, name: str) -> tuple[Path, Path, str]:
    """Registers a fresh project under its own data_root. Returns
    (project_root, data_root, project_id)."""
    root = tmp_path / name
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("print(1)\n")
    data_root = tmp_path / f"{name}-data"
    record = register_project(root, data_root=data_root)
    return root, data_root, record.project_id


def _snapshot(
    root: Path,
    data_root: Path,
    project_id: str,
    *,
    run_id: str | None,
    attempt_id: str | None,
):
    from rush.workflows.projects import project_map_snapshot  # new, T28-C-owned

    project = resolve_project(project_id, data_root=data_root)
    return project_map_snapshot(project, run_id, attempt_id)


# ---------------------------------------------------------------------------
# Group 1: `workflows/projects.py::project_map_snapshot` -- new function.
# Design: ".scratch/.../W4-T23-T29.md" "### T28-C", bullet "New read-only
# `workflows/projects.py::project_map_snapshot(project, run_id, attempt_id)`".
# ---------------------------------------------------------------------------


def test_t28c_project_map_snapshot_assembles_files_findings_memories_agents(
    tmp_path: Path,
) -> None:
    """files/findings/memories/agents are all present in the assembled
    snapshot, matching the `build_project_map` input contract (the same
    shape as `tests/fixtures/dashboard/project_a.json`)."""
    root, data_root, project_id = _project(tmp_path, "proj")
    _write_manifest(
        root,
        run_id="run-1",
        attempt_id="1",
        file_inventory=[{"path": "src/a.py"}],
        findings=[
            {"finding_id": "f1", "path": "src/a.py", "line": 3, "severity": "error"}
        ],
        frozen={
            "memories": [{"id": "m1", "cites": ["src/a.py"]}],
            "agents": [{"id": "ag1", "assigned_to": ["f1"]}],
        },
    )

    snapshot = _snapshot(root, data_root, project_id, run_id="run-1", attempt_id="1")

    assert snapshot["project_id"] == project_id
    assert snapshot["files"] == [{"path": "src/a.py"}]
    assert snapshot["findings"] == [
        {
            "finding_id": "f1",
            "path": "src/a.py",
            "line": 3,
            "severity": "error",
            "id": "f1",
        }
    ]
    assert snapshot["memories"] == [{"id": "m1", "cites": ["src/a.py"]}]
    assert snapshot["agents"] == [{"id": "ag1", "assigned_to": ["f1"]}]


def test_t28c_project_map_snapshot_finding_id_alias(tmp_path: Path) -> None:
    """Finding identity uses the real pipeline's `finding_id` field aliased
    into `id` (server.py:1296-1299's contract), never a second identity
    scheme."""
    root, data_root, project_id = _project(tmp_path, "proj")
    _write_manifest(
        root,
        run_id="run-1",
        attempt_id="1",
        findings=[{"finding_id": "abc123", "path": "src/a.py", "severity": "warn"}],
        frozen={"memories": [], "agents": []},
    )

    snapshot = _snapshot(root, data_root, project_id, run_id="run-1", attempt_id="1")

    assert snapshot["findings"][0]["id"] == "abc123"


def test_t28c_project_map_snapshot_historical_without_freeze_is_unavailable(
    tmp_path: Path,
) -> None:
    """A historical attempt with no `historical_memory_agent_snapshot` key
    shows memory/agents as not captured (unavailable) -- it is never
    silently frozen (that write belongs only to the browser dashboard path,
    server.py:1507-1529) and never live-substituted."""
    root, data_root, project_id = _project(tmp_path, "proj")
    manifest_path = _write_manifest(
        root,
        run_id="run-1",
        attempt_id="1",
        findings=[{"finding_id": "f1", "path": "src/a.py"}],
    )
    before = manifest_path.read_bytes()

    snapshot = _snapshot(root, data_root, project_id, run_id="run-1", attempt_id="1")

    assert snapshot["memories"] == "not captured (unavailable)"
    assert snapshot["agents"] == "not captured (unavailable)"
    after = manifest_path.read_bytes()
    assert after == before, "the TUI must never write the historical freeze"


def test_t28c_project_map_snapshot_corrupt_manifest_is_explicit_not_a_crash(
    tmp_path: Path,
) -> None:
    """A corrupt/unreadable manifest degrades to an explicit unavailable
    result, never an unhandled exception and never a silent empty-looking
    success (mirrors X5's corrupt-vs-missing distinction)."""
    root, data_root, project_id = _project(tmp_path, "proj")
    _write_manifest(root, run_id="run-1", attempt_id="1", raw_text="{not json")

    snapshot = _snapshot(root, data_root, project_id, run_id="run-1", attempt_id="1")

    assert snapshot.get("available", True) is False
    assert snapshot.get("reason")


def test_t28c_project_map_snapshot_creates_no_store_ledger_or_telemetry_files(
    tmp_path: Path,
) -> None:
    """Read-only cross-cutting requirement: rendering evidence never
    constructs `TypedArtifactStore`, `TelemetryStore`, or `MutationLedger`
    in their current (write-on-construct) form (design gate dimension
    'Architecture fit', critical finding #2)."""
    root, data_root, project_id = _project(tmp_path, "proj")
    _write_manifest(
        root,
        run_id="run-1",
        attempt_id="1",
        findings=[],
        frozen={"memories": [], "agents": []},
    )
    rush_dir = root / ".rush"
    before_paths = set(rush_dir.rglob("*")) if rush_dir.exists() else set()

    _snapshot(root, data_root, project_id, run_id="run-1", attempt_id="1")

    after_paths = set(rush_dir.rglob("*")) if rush_dir.exists() else set()
    new_paths = {p.name for p in after_paths - before_paths}
    assert not any(name.endswith((".db", "-wal", "-shm")) for name in new_paths)


def test_t28c_project_map_snapshot_isolates_projects_with_duplicate_paths(
    tmp_path: Path,
) -> None:
    """Two distinct registered projects that each happen to contain
    `src/a.py` never leak one project's evidence into the other's
    snapshot, even though `project_map.py::_file_id` hashes only the
    normalized path (design gate case: 'duplicate paths across
    projects')."""
    root_a, data_root_a, project_a_id = _project(tmp_path, "proj-a")
    root_b, data_root_b, project_b_id = _project(tmp_path, "proj-b")
    _write_manifest(
        root_a,
        run_id="run-1",
        attempt_id="1",
        findings=[{"finding_id": "f1-a", "path": "src/a.py"}],
        frozen={"memories": [], "agents": []},
    )
    _write_manifest(
        root_b,
        run_id="run-1",
        attempt_id="1",
        findings=[{"finding_id": "f1-b", "path": "src/a.py"}],
        frozen={"memories": [], "agents": []},
    )

    snap_a = _snapshot(
        root_a, data_root_a, project_a_id, run_id="run-1", attempt_id="1"
    )
    snap_b = _snapshot(
        root_b, data_root_b, project_b_id, run_id="run-1", attempt_id="1"
    )

    assert snap_a["project_id"] != snap_b["project_id"]
    assert [f["id"] for f in snap_a["findings"]] == ["f1-a"]
    assert [f["id"] for f in snap_b["findings"]] == ["f1-b"]


def test_t28c_project_map_snapshot_memory_cites_recorded_only(tmp_path: Path) -> None:
    """`memories[].cites` is carried through exactly as recorded -- never
    augmented with an inferred citation (e.g. a path that superficially
    matches unrelated memory content). Design gate: 'memories: ... with
    `cites` only from recorded fields'."""
    root, data_root, project_id = _project(tmp_path, "proj")
    (root / "src" / "unrelated.py").write_text("# mentions src/a.py in a comment\n")
    _write_manifest(
        root,
        run_id="run-1",
        attempt_id="1",
        file_inventory=[{"path": "src/a.py"}, {"path": "src/unrelated.py"}],
        findings=[{"finding_id": "f1", "path": "src/a.py"}],
        frozen={
            "memories": [{"id": "m1", "cites": ["src/a.py"]}],
            "agents": [],
        },
    )

    snapshot = _snapshot(root, data_root, project_id, run_id="run-1", attempt_id="1")

    assert snapshot["memories"] == [{"id": "m1", "cites": ["src/a.py"]}], (
        "cites must equal exactly the recorded field -- never gain "
        "'src/unrelated.py' just because its own text mentions the cited path"
    )


def test_t28c_project_map_snapshot_agents_from_run_scoped_handoffs(
    tmp_path: Path,
) -> None:
    """`agents` for the current view come from `.rush/handoffs/*.json`
    (`agent_id`, `assigned_to` = that run's `finding_ids`); a handoff from a
    different run is excluded (design gate case: 'agents: from
    `.rush/handoffs/*.json`')."""
    root, data_root, project_id = _project(tmp_path, "proj")
    started = datetime.now(UTC)
    _write_attempt_header(
        root,
        run_id="run-current",
        attempt_id="1",
        started_at=started,
        project_id=project_id,
    )
    _write_manifest(
        root,
        run_id="run-current",
        attempt_id="1",
        findings=[{"finding_id": "f1", "path": "src/a.py"}],
    )
    _write_handoff(
        root,
        handoff_id="h1",
        run_id="run-current",
        agent_id="ag-current",
        finding_ids=["f1"],
    )
    _write_handoff(
        root,
        handoff_id="h2",
        run_id="run-other",
        agent_id="ag-other",
        finding_ids=["f-other"],
    )

    snapshot = _snapshot(root, data_root, project_id, run_id=None, attempt_id=None)

    assert snapshot["agents"] == [{"id": "ag-current", "assigned_to": ["f1"]}], (
        "a handoff recorded against a different run must never appear"
    )


# ---------------------------------------------------------------------------
# Group 1b: current-attempt resolution through the real T23 selector
# (`select_attempt_chronology`), never a reimplementation. Design gate
# addition: "the TUI map section with no explicit run chooses the current
# run and attempt through the T23 selectors".
# ---------------------------------------------------------------------------


def test_t28c_project_map_snapshot_current_uses_t23_chronology_selector(
    tmp_path: Path,
) -> None:
    """With no explicit run/attempt, the snapshot's findings come from
    whichever attempt the real `select_attempt_chronology` (T23, merged)
    resolves as `published` -- never a second, divergent "latest" pick."""
    from rush.workflows.projects import select_attempt_chronology

    root, data_root, project_id = _project(tmp_path, "proj")
    older = datetime.now(UTC) - timedelta(minutes=5)
    newer = datetime.now(UTC)
    _write_attempt_header(
        root, run_id="run-old", attempt_id="1", started_at=older, project_id=project_id
    )
    _write_manifest(
        root,
        run_id="run-old",
        attempt_id="1",
        findings=[{"finding_id": "f-old", "path": "src/a.py"}],
    )
    _write_attempt_header(
        root, run_id="run-new", attempt_id="1", started_at=newer, project_id=project_id
    )
    _write_manifest(
        root,
        run_id="run-new",
        attempt_id="1",
        findings=[{"finding_id": "f-new", "path": "src/a.py"}],
    )

    chronology = select_attempt_chronology(root, project_id)
    assert chronology.published is not None
    expected_run_id = chronology.published.run_id
    expected_attempt_id = chronology.published.attempt_id

    snapshot = _snapshot(root, data_root, project_id, run_id=None, attempt_id=None)

    assert [f["id"] for f in snapshot["findings"]] == [
        f"f-{'new' if expected_run_id == 'run-new' else 'old'}"
    ]
    assert snapshot.get("run_id") == expected_run_id
    assert snapshot.get("attempt_id") == expected_attempt_id


def test_t28c_project_map_snapshot_current_ambiguous_chronology_has_reason(
    tmp_path: Path,
) -> None:
    """Two attempts in the same run sharing a duplicate generation is
    `chronology_ambiguous` (T23's own real state) -- the map must surface
    that reason explicitly, never silently pick one."""
    root, data_root, project_id = _project(tmp_path, "proj")
    started = datetime.now(UTC)
    _write_attempt_header(
        root,
        run_id="run-1",
        attempt_id="1",
        started_at=started,
        generation=1,
        project_id=project_id,
    )
    _write_attempt_header(
        root,
        run_id="run-1",
        attempt_id="2",
        started_at=started,
        generation=1,
        project_id=project_id,
    )

    snapshot = _snapshot(root, data_root, project_id, run_id=None, attempt_id=None)

    assert snapshot.get("available", True) is False
    assert snapshot.get("reason") == "chronology_ambiguous"


def test_t28c_project_map_snapshot_current_unresolved_chronology_has_reason(
    tmp_path: Path,
) -> None:
    """A run whose attempt directory is missing its header entirely is
    `latest_unresolved` (T23's own real state) -- surfaced explicitly, never
    substituted with an older success."""
    root, data_root, project_id = _project(tmp_path, "proj")
    broken_attempt_dir = root / ".rush" / "runs" / "run-1" / "attempts" / "1"
    broken_attempt_dir.mkdir(parents=True)
    # No attempt.json written: `_load_attempt` returns None for this one,
    # so the run itself is unresolved.

    snapshot = _snapshot(root, data_root, project_id, run_id=None, attempt_id=None)

    assert snapshot.get("available", True) is False
    assert snapshot.get("reason") == "latest_unresolved"


# ---------------------------------------------------------------------------
# Group 2: `_scan_file_inventory` extraction (design gate: dimension "Scope
# soundness", "T28-D needs ... ; T28-C needs `dashboard/server.py::
# _scan_file_inventory` extraction"; X8 file-ownership order).
# ---------------------------------------------------------------------------


def test_t28c_scan_file_inventory_extracted_to_workflows_projects(
    tmp_path: Path,
) -> None:
    """The inventory walk is a `workflows/projects.py`-owned function (a
    project concept, never derived from a scan's own findings), and
    `dashboard/server.py` calls that one copy instead of keeping a second
    definition."""
    import rush.dashboard.server as server_module
    from rush.workflows.projects import _scan_file_inventory as extracted

    root = tmp_path / "inv"
    (root / "src").mkdir(parents=True)
    (root / "src" / "keep.py").write_text("x = 1\n")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "skip.js").write_text("skip\n")
    (root / ".git").mkdir()
    (root / ".git" / "skip2").write_text("skip\n")

    assert extracted(root) == [{"path": "src/keep.py"}]
    # server.py must call the extracted copy, not keep its own duplicate.
    assert server_module._scan_file_inventory is extracted


def test_t28c_server_calls_extracted_scan_file_inventory(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Drives the real server publication path (`publish_check_suite_scan`,
    the same function `dashboard_cmd`'s initial-launch scan uses) with a
    spy wrapped around the module attribute `dashboard/server.py` calls,
    and asserts it actually fires -- not just that the two names are the
    same object (that half is `test_t28c_scan_file_inventory_extracted_to_
    workflows_projects` above)."""
    from rush.dashboard import server as server_module
    from rush.dashboard.server import create_dashboard_server, publish_check_suite_scan
    from rush.workflows.projects import _scan_file_inventory as extracted

    root, data_root, project_id = _project(tmp_path, "proj")
    empty_snapshot = {
        "schema_version": 1,
        "project_id": project_id,
        "source_identity": str(root),
        "root": str(root),
        "files": [],
        "findings": [],
        "memories": [],
        "agents": [],
    }
    server, ctx, _token = create_dashboard_server(
        {project_id: empty_snapshot}, data_root=data_root
    )
    try:
        calls: list[Path] = []

        def spy(root_arg: Path) -> list[dict[str, str]]:
            calls.append(root_arg)
            return extracted(root_arg)

        monkeypatch.setattr(server_module, "_scan_file_inventory", spy)

        aggregate = _tool_result("ruff", "ok")
        publish_check_suite_scan(ctx, project_id, root, aggregate)

        assert calls == [root], (
            "publish_check_suite_scan must call the extracted "
            "workflows.projects._scan_file_inventory"
        )
    finally:
        server.server_close()


# ---------------------------------------------------------------------------
# Group 3: directory grouping is presentation-only (design gate: "Rendering:
# directories are presentation-only grouping of file nodes by `path`, so the
# `build_project_map` node and edge set is unchanged"). Keep-green guard:
# already true of the existing, unmodified `build_project_map`.
# ---------------------------------------------------------------------------


def test_t28c_directory_grouping_does_not_change_build_project_map_totals() -> None:
    """`total_nodes`/`total_edges` (the true full-graph counts, computed
    before any grouped-overview pagination) are identical whether the
    result stays flat (under the render limit) or is paginated into
    `groups` (over it) -- directories/grouping never change the underlying
    node/edge set, only how it is paged for presentation."""
    small_snapshot = {
        "schema_version": 1,
        "project_id": "small",
        "files": [{"path": f"dir{i}/f.py"} for i in range(5)],
        "findings": [],
        "memories": [],
        "agents": [],
    }
    flat = build_project_map(small_snapshot)
    assert flat["groups"] == []
    assert flat["total_nodes"] == len(flat["nodes"])

    big_snapshot = {
        "schema_version": 1,
        "project_id": "big",
        "files": [{"path": f"dir{i}/f.py"} for i in range(250)],
        "findings": [],
        "memories": [],
        "agents": [],
    }
    grouped = build_project_map(big_snapshot)
    assert grouped["groups"], (
        "250 files must exceed the render limit and page into groups"
    )
    # 250 files + 1 project node = 251 real nodes, regardless of how the
    # grouped presentation pages them.
    assert grouped["total_nodes"] == 251


# ---------------------------------------------------------------------------
# Group 4: the brief's own named case -- zero-finding tool outcomes.
# ---------------------------------------------------------------------------


def test_t28c_results_and_relationships() -> None:
    """`tests/test_phase70_tui_usability.py::test_t28c_results_and_relationships`
    per plan packet T28-C's own first bullet: clean/skipped/denied/error
    with no findings must each surface a distinct, visible outcome and
    reason -- the verified baseline gap (three zero-finding summaries were
    absent)."""
    project = ProjectState(
        name="demo",
        root=Path("/tmp/does-not-matter"),
        results=[
            _tool_result("ruff", "ok", summary="clean"),
            _tool_result("bandit", "skipped", summary="engine not installed"),
            _tool_result(
                "semgrep", "skipped", summary="denied: missing artifact_write grant"
            ),
            _tool_result("mypy", "error", summary="typecheck crashed"),
        ],
    )
    console = Console(record=True, width=120)
    console.print(_render_project_table(project))
    rendered = console.export_text()
    for expected in (
        "ruff",
        "clean",
        "bandit",
        "engine not installed",
        "denied",
        "mypy",
        "crashed",
    ):
        assert expected in rendered, (
            f"{expected!r} missing: a zero-finding tool outcome is invisible"
        )


def test_t28c_map_partial_suite_shows_running_state() -> None:
    """A tool still running must be distinguishable from one that already
    finished, even with no findings from either (plan bullet: 'partial
    suite')."""
    partial = ProjectState(
        name="demo",
        root=Path("/tmp/does-not-matter"),
        status="scanning",
        results=[_tool_result("ruff", "ok", summary="clean")],
    )
    console = Console(record=True, width=120)
    console.print(_render_project_table(partial))
    rendered = console.export_text()
    assert "running" in rendered or "pending" in rendered, (
        "a still-running tool in a partial suite must surface distinctly"
    )


def test_t28c_map_pagination_multi_page_guard() -> None:
    """Keep-green guard: existing pagination already handles more than one
    result page (plan bullet: 'more than one result page')."""
    many_findings = [
        Finding(path=f"f{i}.py", line=1, message=f"m{i}", severity="warn")
        for i in range(25)
    ]
    paged = ProjectState(
        name="demo",
        root=Path("/tmp/does-not-matter"),
        results=[_tool_result("ruff", "fail", findings=many_findings)],
    )
    console = Console(record=True, width=120)
    console.print(_render_project_table(paged))
    rendered = console.export_text()
    assert "page 1/2" in rendered, "existing pagination contract regressed"


def test_t28c_map_long_report_shows_full_scrollable_detail() -> None:
    """Plan bullet: 'long report' / 'No fixed first page or first-line-only
    detail'. A large file with a finding carrying no `line` must not
    collapse to a first-lines-only snippet -- current `_bounded_local_detail`
    does exactly that."""
    with tempfile.TemporaryDirectory() as tmp:
        big_root = Path(tmp)
        big_file = big_root / "big.py"
        big_file.write_text("\n".join(f"line {i}" for i in range(500)))
        finding = {"path": "big.py", "message": "no line info"}
        detail = _bounded_local_detail(big_root, finding)
        assert "line 400" in detail or "line 499" in detail, (
            "detail view must reach content beyond the first lines of a "
            "long report, not only its first page"
        )


def test_t28c_map_control_characters_stripped_from_detail() -> None:
    """Plan bullet: 'unsafe path/control-character report'. A hostile
    message/path must never carry a raw ESC byte into the rendered detail
    text."""
    with tempfile.TemporaryDirectory() as tmp:
        hostile_root = Path(tmp)
        hostile_finding = {
            "path": "",
            "message": "pwned\x1b]0;evil\x07 and \x1b[2J",
        }
        detail = _bounded_local_detail(hostile_root, hostile_finding)
        assert "\x1b" not in detail, "raw ESC byte must never reach terminal output"


def test_t28c_map_symlinked_finding_path_refused_and_labelled_live_file() -> None:
    """T8 decision (3): no in-root symlinks; reads go through
    `PhysicalRoot.open_contained`, not ad hoc `resolve()`. Detail is
    labelled 'live file' for a live (non-snapshot) read."""
    with tempfile.TemporaryDirectory() as tmp:
        link_root = Path(tmp)
        target = link_root / "secret.py"
        target.write_text("SECRET_CONTENT\n")
        link = link_root / "link.py"
        link.symlink_to(target)
        finding = {"path": "link.py", "message": "(fallback)"}
        detail = _bounded_local_detail(link_root, finding)
        assert "SECRET_CONTENT" not in detail, (
            "a symlinked finding path must be refused, never dereferenced "
            "and read even when it stays inside the project root"
        )

    with tempfile.TemporaryDirectory() as tmp:
        plain_root = Path(tmp)
        (plain_root / "plain.py").write_text("x = 1\n")
        detail = _bounded_local_detail(plain_root, {"path": "plain.py", "line": 1})
        assert "live file" in detail.lower(), (
            "a live (non-snapshot) read must be labelled 'live file'"
        )


def test_t28c_map_shows_memory_and_agent_branches() -> None:
    """Map is Project -> Files, Findings, Memories, Agents. Current
    `_map_nodes` explicitly omits Memories/Agents branches (see its own
    docstring); it must reuse `build_project_map`, not a Files/Findings-
    only shape."""
    map_project = ProjectState(
        name="demo",
        root=Path("/tmp/does-not-matter"),
        results=[
            _tool_result(
                "ruff",
                "fail",
                findings=[Finding(path="a.py", line=1, message="m", severity="error")],
            )
        ],
    )
    tui_kinds = {node["kind"] for node in _map_nodes(map_project)}
    assert "memory" in tui_kinds and "agent" in tui_kinds, (
        "the TUI Map must render Memories/Agents branches, not only "
        "Project/Files/Findings"
    )


def test_t28c_map_reuses_build_project_map_mixed_nodes_and_edges() -> None:
    """The Map must reuse `build_project_map`'s exact node/edge contract
    for a mixed file/finding/memory/agent snapshot (plan bullet: 'mixed
    file/finding/memory/agent nodes with exact edges')."""
    snapshot = {
        "schema_version": 1,
        "project_id": "proj",
        "files": [{"path": "src/a.py"}],
        "findings": [{"id": "f1", "path": "src/a.py", "line": 1, "severity": "error"}],
        "memories": [{"id": "m1", "cites": ["src/a.py"]}],
        "agents": [{"id": "ag1", "assigned_to": ["f1"]}],
    }
    graph = build_project_map(snapshot)
    kinds = {n["kind"] for n in graph["nodes"]}
    assert kinds == {"project", "file", "finding", "memory", "agent"}
    relations = {e["relation"] for e in graph["edges"]}
    assert relations == {"contains", "reports", "cites", "assigned_to"}


def test_t28c_map_search_reaches_collapsed_nodes_guard() -> None:
    """Keep-green guard: existing `build_project_map` `query` filtering
    already searches the full graph, including a node that would render
    under a collapsed group (plan bullet: 'collapsed-node search')."""
    big_snapshot = {
        "schema_version": 1,
        "project_id": "proj-big",
        "files": [{"path": f"dir{i}/f.py"} for i in range(250)],
        "findings": [],
        "memories": [],
        "agents": [],
    }
    filtered = build_project_map(big_snapshot, query="dir7/f.py")
    assert any(n.get("path") == "dir7/f.py" for n in filtered["nodes"]), (
        "a collapsed-group member must still be reachable by search"
    )


def test_t28c_map_empty_graph_shape_guard() -> None:
    """Keep-green guard: an empty/no-relations snapshot degrades cleanly --
    project root only, no crash (plan bullet: 'empty/no-relations/corrupt
    graph')."""
    empty_graph = build_project_map(
        {
            "schema_version": 1,
            "project_id": "empty",
            "files": [],
            "findings": [],
            "memories": [],
            "agents": [],
        }
    )
    assert len(empty_graph["nodes"]) == 1  # project root only, no crash
    assert empty_graph["edges"] == []


def test_t28c_project_map_snapshot_is_read_only_wired_into_render(
    tmp_path: Path,
) -> None:
    """Reading evidence to render the Map/Scans sections never touches the
    write-on-construct stores that `project_map_snapshot` itself already
    proves it avoids -- this is the render-path integration half of that
    guarantee, exercised through `project_map_snapshot` and
    `build_project_map` together, matching how `_render_map` must call
    them."""
    root, data_root, project_id = _project(tmp_path, "proj")
    _write_manifest(
        root,
        run_id="run-1",
        attempt_id="1",
        findings=[{"finding_id": "f1", "path": "src/a.py"}],
        frozen={"memories": [{"id": "m1", "cites": ["src/a.py"]}], "agents": []},
    )

    snapshot = _snapshot(root, data_root, project_id, run_id="run-1", attempt_id="1")
    graph = build_project_map(snapshot)

    assert {n["kind"] for n in graph["nodes"]} >= {
        "project",
        "file",
        "finding",
        "memory",
    }
    assert not (root / ".rush" / "memory.db").exists()


def test_t28c_map_detail_prefers_captured_snapshot_over_live_file(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """W4 T28-C shared design: 'Detail: ... labelled "live file", with the
    captured snapshot preferred.' Orchestrator resolution R28C.1: the
    captured snapshot IS the attempt's real `artifact_snapshots`
    (`CandidateExecution.artifact_snapshots`, project_run.py:347/663),
    already keyed into the manifest's `scheduled[].artifact_snapshots`
    (`dashboard/server.py::_read_artifact_content_page`, the exact shape
    reused here). The reader itself -- `workflows/projects.py::
    read_project_artifact_page`, T28-E's extraction of that function --
    does not exist yet; that is this test's RED, not the field."""
    import base64
    import hashlib

    import pytest

    from rush.io.physical_paths import PhysicalRoot

    root, data_root, project_id = _project(tmp_path, "proj")
    run_id, attempt_id, candidate_id = "run-1", "1", "ruff"
    captured_bytes = b"CAPTURED_SNAPSHOT_CONTENT\n"
    immutable_rel = (
        f".rush/runs/{run_id}/attempts/{attempt_id}/artifacts/{candidate_id}-0.bin"
    )
    (root / immutable_rel).parent.mkdir(parents=True, exist_ok=True)
    (root / immutable_rel).write_bytes(captured_bytes)

    manifest_path = root / _MANIFEST_TEMPLATE.format(
        run_id=run_id, attempt_id=attempt_id
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "attempt_id": attempt_id,
                "project_id": project_id,
                "aggregate": {
                    "findings": [{"finding_id": "f1", "path": "src/a.py", "line": 1}]
                },
                "scheduled": [
                    {
                        "candidate_id": candidate_id,
                        "artifact_snapshots": {
                            "src/a.py": {
                                "immutable_path": immutable_rel,
                                "size": len(captured_bytes),
                                "sha256": hashlib.sha256(captured_bytes).hexdigest(),
                                "media_type": "text/x-python",
                            }
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    # The live file has since changed -- the captured snapshot must win.
    (root / "src" / "a.py").write_text("LIVE_CHANGED_CONTENT\n")

    open_contained_calls: list[Any] = []
    original_open_contained = PhysicalRoot.open_contained

    def spy(self: PhysicalRoot, relative_path: Any, purpose: str = "read") -> Path:
        open_contained_calls.append(relative_path)
        return original_open_contained(self, relative_path, purpose)

    monkeypatch.setattr(PhysicalRoot, "open_contained", spy)

    try:
        from rush.workflows.projects import read_project_artifact_page
    except ImportError:
        pytest.fail(
            "read_project_artifact_page (T28-E's extracted reader in "
            "workflows/projects.py, relocating dashboard/server.py::"
            "_read_artifact_content_page) does not exist yet -- detail "
            "cannot prefer a captured snapshot over a live read without it."
        )

    cursor = base64.urlsafe_b64encode(
        json.dumps(
            {
                "project_id": project_id,
                "run_id": run_id,
                "attempt_id": attempt_id,
                "tool_id": candidate_id,
                "path": "src/a.py",
                "sha256": hashlib.sha256(captured_bytes).hexdigest(),
                "offset": 0,
            }
        ).encode("utf-8")
    ).decode("ascii")
    page = read_project_artifact_page(
        project_id, cursor, data_root=data_root, limit=4096
    )

    content = base64.b64decode(page["content_base64"])
    assert content == captured_bytes, (
        "detail must show the captured bytes, not the changed live file"
    )
    assert open_contained_calls == [
        _MANIFEST_TEMPLATE.format(run_id=run_id, attempt_id=attempt_id),
        immutable_rel,
    ], (
        "containment goes through PhysicalRoot for the manifest and the "
        "immutable snapshot only; the live file must never be read when a "
        "captured snapshot exists"
    )
    assert page.get("run_id") == run_id
    assert page.get("attempt_id") == attempt_id
    assert "captured" in str(page.get("label", "")).lower(), (
        "the result must be labelled as a captured snapshot, not 'live file'"
    )


def test_t28c_map_detail_falls_back_to_live_file_without_captured_snapshot() -> None:
    """The other half of the same contract: with no captured content
    available, detail reads the live file and labels it 'live file'
    (current `_bounded_local_detail` never labels anything)."""
    import tempfile
    from pathlib import Path

    from rush.tui import _bounded_local_detail

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "plain.py").write_text("x = 1\n")
        detail = _bounded_local_detail(root, {"path": "plain.py", "line": 1})
        assert "live file" in detail.lower(), (
            "with no captured snapshot, detail must read the live file and "
            "label it 'live file'"
        )


# ---------------------------------------------------------------------------
# T28-C fix round 1 (review r1).
# ---------------------------------------------------------------------------


def _cursor(
    *,
    project_id: str,
    run_id: str,
    attempt_id: str,
    tool_id: str,
    path: str,
    sha256: str,
    offset: int = 0,
) -> str:
    """Encodes an artifact-page cursor exactly as the server issues it."""
    import base64

    payload = {
        "project_id": project_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "tool_id": tool_id,
        "path": path,
        "sha256": sha256,
        "offset": offset,
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def _artifact_project(tmp_path: Path) -> tuple[str, Path, Path, dict[str, Any]]:
    """Registers a project whose run-a attempt published one immutable
    artifact snapshot (`report.txt`). Returns (project_id, root, data_root,
    snapshot)."""
    import hashlib

    root = tmp_path / "proj"
    root.mkdir(parents=True, exist_ok=True)
    (root / "app.py").write_text("print('hi')\n", encoding="utf-8")
    data_root = tmp_path / "rush-data" / "proj"
    project_id = register_project(root, data_root=data_root).project_id
    data = b"hello artifact bytes"
    digest = hashlib.sha256(b"tool-a").hexdigest()[:24]
    attempt_rel = ".rush/runs/run-a/attempts/run-a-attempt-1"
    immutable_rel = f"{attempt_rel}/artifacts/{digest}/0.bin"
    (root / immutable_rel).parent.mkdir(parents=True, exist_ok=True)
    (root / immutable_rel).write_bytes(data)
    snapshot = {
        "immutable_path": immutable_rel,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "media_type": "text/plain",
    }
    scheduled = [
        {
            "candidate_id": "tool-a",
            "category": "lint",
            "outcome": "executed",
            "child": {"status": "ok", "artifacts": ["report.txt"]},
            "artifact_snapshots": {"report.txt": snapshot},
        }
    ]
    manifest = {
        "schema_version": 1,
        "run_id": "run-a",
        "attempt_id": "run-a-attempt-1",
        "plan_id": "plan-run-a",
        "project_id": project_id,
        "root": str(root),
        "run_state": "completed",
        "severity": "warn",
        "concurrency": 1,
        "timeout_seconds": 300,
        "created_at": "2026-01-01T00:00:00+00:00",
        "candidates": scheduled,
        "scheduled": scheduled,
        "aggregate": {
            "tool": "scan",
            "engine": None,
            "status": "ok",
            "findings": [],
            "metadata": {"coverage": {"empty": False}},
        },
        "totals": {
            "candidate_count": 1,
            "scheduled_count": 1,
            "executed_count": 1,
            "finding_count": 0,
        },
    }
    (root / attempt_rel / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (root / attempt_rel / "attempt.json").write_text(
        json.dumps(
            {
                "run_id": "run-a",
                "attempt_id": "run-a-attempt-1",
                "plan_id": "plan-run-a",
                "project_id": project_id,
                "started_at": "2026-01-01T00:00:00+00:00",
                "attempt_generation": 1,
            }
        ),
        encoding="utf-8",
    )
    return project_id, root, data_root, snapshot


def test_t28c_artifact_page_reads_a_check_suite_manifest_without_project_id(
    tmp_path: Path,
) -> None:
    """A CHECK_SUITE-published manifest carries no `project_id`; identity is
    the cursor's project resolved to its root, so the page reads. A manifest
    naming a different project stays not_found."""
    import base64

    from rush.workflows.projects import read_project_artifact_page

    project_id, root, data_root, snapshot = _artifact_project(tmp_path)
    manifest_path = root / _MANIFEST_TEMPLATE.format(
        run_id="run-a", attempt_id="run-a-attempt-1"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["project_id"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    cursor = _cursor(
        project_id=project_id,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        tool_id="tool-a",
        path="report.txt",
        sha256=snapshot["sha256"],
    )
    page = read_project_artifact_page(project_id, cursor, data_root=data_root)
    assert page.get("error") is None, page
    assert base64.b64decode(page["content_base64"]) == b"hello artifact bytes"

    manifest["project_id"] = "someone-else"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    page = read_project_artifact_page(project_id, cursor, data_root=data_root)
    assert page["error"] == "not_found"


def _seed_memory_db(root: Path) -> Path:
    import sqlite3

    db = root / ".rush" / "memory.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "CREATE TABLE memory_artifacts (id TEXT, symbol_ref TEXT, source TEXT)"
        )
        conn.execute(
            "INSERT INTO memory_artifacts VALUES ('m1', 'src/a.py::f', 'agent')"
        )
        conn.commit()
    finally:
        conn.close()
    return db


def test_t28c_map_shows_memories_before_any_scan(tmp_path: Path) -> None:
    root, data_root, project_id = _project(tmp_path, "proj")
    _seed_memory_db(root)
    snapshot = _snapshot(root, data_root, project_id, run_id=None, attempt_id=None)
    assert snapshot["memories"] == [{"id": "m1", "cites": ["src/a.py"]}]
    assert snapshot["agents"] == []


def test_t28c_malformed_inventory_is_missing_not_rewalked(tmp_path: Path) -> None:
    root, data_root, project_id = _project(tmp_path, "proj")
    manifest_path = _write_manifest(
        root,
        run_id="run-1",
        attempt_id="1",
        findings=[{"finding_id": "f1", "path": "src/a.py"}],
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["file_inventory"] = {"not": "a list"}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (root / "src" / "live_only.py").write_text("x = 1\n")

    snapshot = _snapshot(root, data_root, project_id, run_id="run-1", attempt_id="1")
    assert snapshot["file_inventory_missing"] is True
    assert snapshot["files"] == [{"path": "src/a.py"}]


def test_t28c_deeply_nested_cursor_is_invalid(tmp_path: Path) -> None:
    import base64

    from rush.workflows.projects import read_project_artifact_page

    _root, data_root, project_id = _project(tmp_path, "proj")
    for raw in (b"[" * 100000 + b"]" * 100000, b"[1, 2]", b"\xff\xfe"):
        cursor = base64.urlsafe_b64encode(raw).decode("ascii")
        page = read_project_artifact_page(project_id, cursor, data_root=data_root)
        assert page["error"] == "invalid_cursor"


def test_t28c_map_reloads_after_memory_delete_and_new_handoff(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The map snapshot cache key covers `.rush/memory.db` and
    `.rush/handoffs` mtimes, so a deleted memory store or a new handoff
    reloads the snapshot without a new run or status change."""
    import os

    from rush import tui as tui_mod
    from rush.workflows import projects as wp

    root = tmp_path / "proj"
    (root / ".rush" / "handoffs").mkdir(parents=True)
    db = root / ".rush" / "memory.db"
    db.write_bytes(b"x")
    calls: list[int] = []
    monkeypatch.setattr(wp, "resolve_project", lambda project_id: object())
    monkeypatch.setattr(
        wp,
        "project_map_snapshot",
        lambda record, run_id, attempt_id: calls.append(1) or {"available": True},
    )
    project = ProjectState(name="proj", root=root, project_id="pid")

    tui_mod._load_map_snapshot(project)
    tui_mod._load_map_snapshot(project)
    assert len(calls) == 1, "unchanged state is served from the cache"

    db.unlink()
    tui_mod._load_map_snapshot(project)
    assert len(calls) == 2, "deleting memory.db must reload the snapshot"

    handoffs = root / ".rush" / "handoffs"
    (handoffs / "h1.json").write_text("{}", encoding="utf-8")
    st = handoffs.stat()
    os.utime(handoffs, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    tui_mod._load_map_snapshot(project)
    assert len(calls) == 3, "a new handoff must reload the snapshot"

    tui_mod._load_map_snapshot(project)
    assert len(calls) == 3


def _artifact_cursor_for(project_id: str, snapshot: dict[str, Any]) -> str:
    return _cursor(
        project_id=project_id,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        tool_id="tool-a",
        path="report.txt",
        sha256=snapshot["sha256"],
    )


def test_t28c_intermediate_symlink_component_is_refused(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A directory component swapped for a symlink after
    `PhysicalRoot.open_contained` validated the path (the check/use race)
    must still be refused: each component is opened from the root with
    dir_fd and O_NOFOLLOW, never re-resolved by path."""
    import shutil

    from rush.io.physical_paths import PhysicalRoot
    from rush.workflows.projects import read_project_artifact_page

    project_id, root, data_root, snapshot = _artifact_project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    swap: dict[str, Any] = {}
    original = PhysicalRoot.open_contained

    def racing_open_contained(
        self: PhysicalRoot, relative_path: Any, purpose: str = "read"
    ) -> Path:
        result = original(self, relative_path, purpose)
        victim = swap.get("dir")
        if str(relative_path) == swap.get("rel") and not victim.is_symlink():
            shutil.copytree(victim, outside / victim.name)
            shutil.rmtree(victim)
            victim.symlink_to(outside / victim.name, target_is_directory=True)
        return result

    monkeypatch.setattr(PhysicalRoot, "open_contained", racing_open_contained)

    # Artifact page: the snapshot's parent directory is swapped for a
    # symlink to an identical copy outside the root.
    swap["rel"] = snapshot["immutable_path"]
    swap["dir"] = (root / snapshot["immutable_path"]).parent
    page = read_project_artifact_page(
        project_id, _artifact_cursor_for(project_id, snapshot), data_root=data_root
    )
    assert page.get("error") == "invalid_path", page
    assert not page.get("content_base64"), "no bytes are served on refusal"

    # Live-file detail: `src` is swapped for a symlink to an outside copy.
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("OUTSIDE_SECRET = 1\n", encoding="utf-8")
    swap["rel"] = "src/a.py"
    swap["dir"] = root / "src"
    detail = _bounded_local_detail(root, {"path": "src/a.py", "message": "(fb)"})
    assert "OUTSIDE_SECRET" not in detail, detail
    assert "live file" not in detail.lower()


def test_t28c_hard_link_to_outside_file_is_refused(tmp_path: Path) -> None:
    """A regular file inside the root that is a hard link (st_nlink > 1) to
    a file outside it is refused by both the live-file detail and the
    captured-artifact page read."""
    from rush.workflows.projects import read_project_artifact_page

    project_id, root, data_root, snapshot = _artifact_project(tmp_path)
    outside_file = tmp_path / "outside-secret.py"
    outside_file.write_text("HARDLINK_SECRET = 1\n", encoding="utf-8")
    os.link(outside_file, root / "x.py")
    detail = _bounded_local_detail(root, {"path": "x.py", "message": "(fb)"})
    assert "HARDLINK_SECRET" not in detail, detail
    assert "live file" not in detail.lower()

    immutable = root / snapshot["immutable_path"]
    outside_bytes = tmp_path / "outside-artifact.bin"
    outside_bytes.write_bytes(immutable.read_bytes())
    immutable.unlink()
    os.link(outside_bytes, immutable)
    page = read_project_artifact_page(
        project_id, _artifact_cursor_for(project_id, snapshot), data_root=data_root
    )
    assert page.get("error") == "invalid_path", page

    # A single-link regular file still reads.
    (root / "y.py").write_text("PLAIN = 1\n", encoding="utf-8")
    detail = _bounded_local_detail(root, {"path": "y.py", "message": "(fb)"})
    assert "PLAIN = 1" in detail


def test_t28c_detail_shows_the_finding_line_of_a_long_file(tmp_path: Path) -> None:
    """A 3000-line file with the finding at line 1500: the detail opens at
    the finding line (minus context) with a marker that earlier lines are
    above, the cursor scrolls, selecting a row resets the scroll, and a file
    over the 1 MiB cap says it is truncated."""
    from rich.layout import Layout

    from rush import tui as tui_mod

    root = tmp_path / "proj"
    root.mkdir()
    (root / "big.py").write_text(
        "\n".join(f"row_{i:04d} = {i}" for i in range(1, 3001)) + "\n",
        encoding="utf-8",
    )
    finding = Finding(path="big.py", line=1500, message="too long", severity="warn")
    project = ProjectState(
        name="proj",
        root=root,
        results=[_tool_result("ruff", "fail", findings=[finding])],
    )

    def screen() -> str:
        console = Console(record=True, width=100, height=24)
        console.print(Layout(tui_mod._render_detail(project)))
        return console.export_text()

    rendered = screen()
    assert "row_1500 = 1500" in rendered, rendered
    assert "row_0001" not in rendered
    assert "earlier lines above" in rendered
    assert "too long" in rendered, "the finding message stays visible"

    state = tui_mod.TuiState(projects=[project], active_index=0)
    state.mode = "detail"
    tui_mod._cursor(40)(state, None)  # type: ignore[arg-type]
    assert project.selected_index == 0, "scrolling must not move the selection"
    assert "row_1540 = 1540" in screen()
    tui_mod._cursor(-5000)(state, None)  # type: ignore[arg-type]
    rendered = screen()
    assert "row_0001 = 1" in rendered
    assert "earlier lines above" not in rendered

    tui_mod._select_row(state, None)  # type: ignore[arg-type]
    assert project.detail_scroll is None
    assert "row_1500 = 1500" in screen()

    big = root / "big.py"
    big.write_bytes(b"x = 1\n" * ((1024 * 1024) // 6 + 100))
    size = big.stat().st_size
    detail = tui_mod._bounded_local_detail(root, {"path": "big.py", "line": 1})
    assert f"truncated at {1024 * 1024} of {size} bytes" in detail


def _inventory_project(tmp_path: Path, paths: list[str]) -> ProjectState:
    """A project whose loaded map snapshot records `paths` as its file
    inventory (the `build_project_map` input), with no findings."""
    return ProjectState(
        name="inv",
        root=tmp_path,
        map_snapshot={
            "schema_version": 1,
            "project_id": "inv",
            "files": [{"path": path} for path in paths],
            "findings": [],
            "memories": [],
            "agents": [],
        },
    )


def test_t28c_map_groups_files_into_directories_from_the_inventory(
    tmp_path: Path,
) -> None:
    """Map file nodes come from the recorded inventory (not only finding
    paths) and nest under expandable directory nodes; a root-level file
    stays at depth 1 with no parent."""
    from rush import tui as tui_mod

    project = _inventory_project(
        tmp_path, ["a.py", "src/b.py", "src/pkg/c.py", "docs/d.md"]
    )
    project.results = [
        _tool_result(
            "ruff",
            "fail",
            findings=[
                Finding(path="src/b.py", line=3, message="bad b", severity="warn")
            ],
        )
    ]
    by_key = {node["key"]: node for node in tui_mod._map_nodes(project)}
    assert by_key["file:a.py"]["depth"] == 1
    assert by_key["file:a.py"].get("parent") is None
    assert by_key["dir:src"]["depth"] == 1 and by_key["dir:src"].get("parent") is None
    assert by_key["dir:src/pkg"]["parent"] == "dir:src"
    assert by_key["file:src/pkg/c.py"]["parent"] == "dir:src/pkg"
    assert by_key["file:src/pkg/c.py"]["depth"] == 3
    assert by_key["file:docs/d.md"]["parent"] == "dir:docs"
    assert by_key["file:src/b.py:finding:0"]["parent"] == "file:src/b.py"
    assert by_key["file:src/b.py:finding:0"]["depth"] == 3

    collapsed = [n["key"] for n in tui_mod._map_visible_nodes(project, set())]
    assert collapsed[:4] == ["root", "dir:docs", "dir:src", "file:a.py"], collapsed
    assert "file:src/b.py" not in collapsed

    state = tui_mod.TuiState(projects=[project], active_index=0)
    state.mode = "map"
    state.map_selected_index = collapsed.index("dir:src")
    tui_mod._map_expand(state, None)  # type: ignore[arg-type]
    shown = [n["key"] for n in tui_mod._map_visible_nodes(project, state.map_expanded)]
    assert "file:src/b.py" in shown and "dir:src/pkg" in shown
    assert "file:src/pkg/c.py" not in shown
    tui_mod._map_collapse(state, None)  # type: ignore[arg-type]
    shown = [n["key"] for n in tui_mod._map_visible_nodes(project, state.map_expanded)]
    assert "file:src/b.py" not in shown


def test_t28c_map_paginates_a_large_directory(tmp_path: Path) -> None:
    """A directory with more than 100 files shows 100 at a time plus a
    'more' node; expanding it shows the next page until every file shows.
    250 files also force `build_project_map` to group, so the inventory is
    read through `expand_group` pages without losing a file."""
    from rush import tui as tui_mod

    paths = [f"big/f_{i:04d}.py" for i in range(250)]
    project = _inventory_project(tmp_path, paths)

    state = tui_mod.TuiState(projects=[project], active_index=0)
    state.mode = "map"
    state.map_expanded = {"dir:big"}

    def big_files() -> list[str]:
        return [
            n["key"]
            for n in tui_mod._map_visible_nodes(project, state.map_expanded)
            if n["key"].startswith("file:big/")
        ]

    for expected in (100, 200, 250):
        assert len(big_files()) == expected
        visible = tui_mod._map_visible_nodes(project, state.map_expanded)
        more = [i for i, n in enumerate(visible) if n["key"] == "more:big"]
        if expected == 250:
            assert more == []
            break
        assert len(more) == 1
        assert f"{250 - expected} more" in visible[more[0]]["label"]
        state.map_selected_index = more[0]
        tui_mod._map_expand(state, None)  # type: ignore[arg-type]
    assert big_files() == [f"file:{path}" for path in paths]


def test_t28c_map_search_reaches_a_collapsed_file(tmp_path: Path) -> None:
    """`/` in Map mode searches every node, including files under
    collapsed directories and beyond a directory's first page, expands the
    path to the match and selects it -- it never enters findings search."""
    from types import SimpleNamespace

    from rush import tui as tui_mod

    paths = ["a.py", "deep/nested/target_mod.py"] + [
        f"big/f_{i:04d}.py" for i in range(250)
    ]
    project = _inventory_project(tmp_path, paths)
    state = tui_mod.TuiState(projects=[project], active_index=0)
    state.section = "map"
    state.mode = "map"
    actions = SimpleNamespace()

    def search(query: str) -> str:
        tui_mod._dispatch_key(state, "/", actions)  # type: ignore[arg-type]
        assert state.mode == "map_search"
        for ch in query:
            tui_mod._dispatch_key(state, ch, actions)  # type: ignore[arg-type]
        tui_mod._dispatch_key(state, "enter", actions)  # type: ignore[arg-type]
        assert state.mode == "map"
        visible = tui_mod._map_visible_nodes(project, state.map_expanded)
        return str(visible[state.map_selected_index]["key"])

    assert search("target_mod") == "file:deep/nested/target_mod.py"
    assert {"dir:deep", "dir:deep/nested"} <= state.map_expanded
    assert project.filter_text == "", "Map search must not filter findings"

    assert search("f_0230") == "file:big/f_0230.py"
    assert "dir:big" in state.map_expanded

    tui_mod._dispatch_key(state, "/", actions)  # type: ignore[arg-type]
    for ch in "zz":
        tui_mod._dispatch_key(state, ch, actions)  # type: ignore[arg-type]
    tui_mod._dispatch_key(state, "escape", actions)  # type: ignore[arg-type]
    assert state.mode == "map"
    assert state.map_query == ""
