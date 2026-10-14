"""Phase 70 T21 -- show memory contribution in scan/check summaries.

Binding design: `.scratch/phase-70-design-gate/W3-T18-T22.md` ("## T21").
Predecessors T16 (metadata assembly), T17 (six check steps / CheckTool) and
T19 (attribute actual memory reads/writes, including the `aggregate_results`
union and scan-resume receipt relocation) are **not implemented** in this
worktree. Every group below says explicitly whether its RED is T21's own
(clause formatting, merge-instead-of-overwrite in `suites.py`, lifting into
`ScanTool`'s `ToolResult`) or requires a predecessor to land first.

Where T19/T16's future `aggregate_results` union is a precondition for
testing T21's own downstream code, this file monkeypatches
`aggregate_results` with `_make_union_aggregate_results` -- a small stand-in
that unions `metadata.memory` across children by `(id, revision, operation)`,
mirroring T19's own documented contract (design doc T19 B1/B3). This isolates
T21's own clause/lift/persist code from T19's undone union work. Fixtures
and helpers are local to this file only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from rush.config import RushConfig
from rush.permissions import ExecutionPermissions
from rush.tools import scan as scan_module
from rush.tools.routing import aggregate_results as real_aggregate_results
from rush.tools.scan import ScanTool
from rush.workflows import project_run, suites
from rush.workflows.project_run import (
    ScanCandidate,
    cancel_scan_run,
    execute_scan,
    load_run_manifest,
    resume_scan_run,
)
from rush.workflows.projects import register_project
from rush.workflows.suites import WorkflowSuite, run_workflow_suite

# --------------------------------------------------------------------------
# Local fixtures / helpers (no shared conftest, no edits to other test files)
# --------------------------------------------------------------------------


def _mem_item(
    id_: str, *, revision: int = 1, source: str = "s", operation: str = "recall"
) -> dict[str, Any]:
    return {"id": id_, "revision": revision, "source": source, "operation": operation}


def _union_memory(children: list[dict[str, Any]]) -> dict[str, Any] | None:
    """T19 B1/B3 stand-in: union `metadata.memory` across children, deduped
    by `(id, revision, operation)`, first-use order kept."""
    used: list[dict[str, Any]] = []
    written: list[dict[str, Any]] = []
    seen_used: set[tuple[Any, Any, Any]] = set()
    seen_written: set[tuple[Any, Any, Any]] = set()
    for child in children:
        memory = (child.get("metadata") or {}).get("memory") or {}
        for item in memory.get("used", []):
            key = (item.get("id"), item.get("revision"), item.get("operation"))
            if key not in seen_used:
                seen_used.add(key)
                used.append(item)
        for item in memory.get("written", []):
            key = (item.get("id"), item.get("revision"), item.get("operation"))
            if key not in seen_written:
                seen_written.add(key)
                written.append(item)
    if not used and not written:
        return None
    return {"version": 1, "used": used, "written": written}


def _make_union_aggregate_results(real_fn):
    def _wrapped(tool, children, *, baseline_fingerprints=None):
        result = real_fn(tool, children, baseline_fingerprints=baseline_fingerprints)
        memory = _union_memory(list(children))
        if memory is not None:
            metadata = dict(result.get("metadata") or {})
            metadata["memory"] = memory
            result["metadata"] = metadata
        return result

    return _wrapped


class _MemTool:
    """A step whose retained `ToolResult` optionally carries `metadata.memory`
    -- stands in for a real T19-observing tool (review/lint/etc)."""

    def __init__(self, name: str, memory: dict[str, Any] | None = None) -> None:
        self.name = name
        self._memory = memory

    def __call__(self, path: Path) -> dict[str, Any]:
        result: dict[str, Any] = {
            "tool": self.name,
            "status": "ok",
            "duration_ms": 0,
            "summary": f"{self.name}: ok",
            "findings": [],
        }
        if self._memory is not None:
            result["metadata"] = {"memory": self._memory}
        return result


def _data_root(tmp_path: Path) -> Path:
    return tmp_path / "rush-data"


def _register(tmp_path: Path) -> tuple[str, Path]:
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("x = 1\n", encoding="utf-8")
    data_root = _data_root(tmp_path)
    record = register_project(root, data_root=data_root)
    return record.project_id, data_root


class _FakeScanRun:
    """Stand-in for `ScanRun` -- isolates `ScanTool`'s own lift/clause code
    from `execute_scan`'s real (T19-dependent) union."""

    def __init__(self, aggregate: dict[str, Any]) -> None:
        self._aggregate = aggregate

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": "run-1",
            "attempt_id": "attempt-1",
            "aggregate": dict(self._aggregate),
        }


# --------------------------------------------------------------------------
# Group A -- `memory_summary_clause` (pure T21: workflows/suites.py, no
# predecessor needed at all; the function does not exist yet).
# --------------------------------------------------------------------------


def test_memory_summary_clause_contract() -> None:
    from rush.workflows.suites import memory_summary_clause

    # B2: no clause when both counts are 0 (missing member, empty member,
    # and empty used/written arrays are all "zero").
    assert memory_summary_clause(None) is None
    assert memory_summary_clause({}) is None
    assert memory_summary_clause({"version": 1, "used": [], "written": []}) is None

    # Singular "record" at exactly 1, plural otherwise -- both directions.
    assert (
        memory_summary_clause({"version": 1, "used": [_mem_item("a")], "written": []})
        == "memory: read 1 prior record, wrote 0 records"
    )
    assert (
        memory_summary_clause(
            {
                "version": 1,
                "used": [_mem_item("a"), _mem_item("b")],
                "written": [_mem_item("c", operation="observation")],
            }
        )
        == "memory: read 2 prior records, wrote 1 record"
    )

    # B2 continued: no "quality"/"learning"/"token-savings" wording.
    clause = memory_summary_clause(
        {"version": 1, "used": [_mem_item("a")], "written": []}
    )
    assert clause is not None
    for banned in ("quality", "learn", "token", "saving"):
        assert banned not in clause.lower()


# --------------------------------------------------------------------------
# Group B -- check-suite merge (`run_workflow_suite`, `workflows/suites.py`).
# T21 owns the union/dedup here (design §2: "sets memory = union(children)"),
# so with T19's own `aggregate_results` union simulated via monkeypatch,
# these cases isolate T21's own merge + clause code.
# --------------------------------------------------------------------------


def test_t21_summary_uses_actual_receipts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Binding-design test name (design §6). Two children cite the same
    memory id -- the summary must reflect the deduped union, not a per-child
    sum, and must still carry T17's step entries (no wholesale overwrite)."""
    monkeypatch.setattr(
        suites,
        "aggregate_results",
        _make_union_aggregate_results(real_aggregate_results),
    )
    monkeypatch.setattr(
        suites,
        "ALL_TOOLS",
        [
            _MemTool("one", {"version": 1, "used": [_mem_item("r1")], "written": []}),
            _MemTool(
                "two",
                {
                    "version": 1,
                    "used": [_mem_item("r1")],  # duplicate of "one"'s read
                    "written": [_mem_item("w1", operation="observation")],
                },
            ),
        ],
    )
    workflow = WorkflowSuite("probe-suite", "probe", ("one", "two"))

    result = run_workflow_suite(
        workflow, tmp_path, ExecutionPermissions(), config=RushConfig()
    )

    assert result["summary"] == (
        "probe-suite: executed 2 tool(s) with status 'ok'"
        "; memory: read 1 prior record, wrote 1 record"
    )
    memory = result["metadata"]["memory"]
    assert [item["id"] for item in memory["used"]] == ["r1"]
    assert [item["id"] for item in memory["written"]] == ["w1"]
    # Merge, not overwrite -- T17's step entries survive alongside memory.
    assert [child["tool"] for child in result["metadata"]["children"]] == ["one", "two"]
    assert result["metadata"]["executed_tools"] == ("one", "two")


def test_check_suite_no_clause_when_no_memory_used(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Keep-green guard (B2): today's summary already has no clause when no
    step reports memory use -- this must remain true once T21 lands."""
    monkeypatch.setattr(
        suites,
        "aggregate_results",
        _make_union_aggregate_results(real_aggregate_results),
    )
    monkeypatch.setattr(suites, "ALL_TOOLS", [_MemTool("one"), _MemTool("two")])
    workflow = WorkflowSuite("probe-suite", "probe", ("one", "two"))

    result = run_workflow_suite(workflow, tmp_path, ExecutionPermissions())

    assert result["summary"] == "probe-suite: executed 2 tool(s) with status 'ok'"
    assert "; memory:" not in result["summary"]


def test_check_suite_config_none_best_effort_loads_rush_toml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """G4: `run_workflow_suite(config=None)` must best-effort `load_config`
    from the target path -- otherwise `[tools.memory] record` is inert in
    check (G4, owner: T21 for suites)."""
    (tmp_path / "rush.toml").write_text(
        "[tools.memory]\nrecord = true\n", encoding="utf-8"
    )
    seen_configs: list[object] = []
    real_resolve_invocation = suites.resolve_invocation

    def _spy_resolve_invocation(request, **kwargs):
        seen_configs.append(kwargs.get("config"))
        return real_resolve_invocation(request, **kwargs)

    monkeypatch.setattr(suites, "resolve_invocation", _spy_resolve_invocation)
    monkeypatch.setattr(suites, "ALL_TOOLS", [_MemTool("one")])
    workflow = WorkflowSuite("probe-suite", "probe", ("one",))

    run_workflow_suite(workflow, tmp_path, ExecutionPermissions(), config=None)

    assert len(seen_configs) == 1
    loaded = seen_configs[0]
    assert loaded is not None, "config stayed None -- no best-effort load happened"
    assert isinstance(loaded, RushConfig)
    assert loaded.source == tmp_path / "rush.toml"


# --------------------------------------------------------------------------
# Group C -- scan attempt (`_finalize_attempt`, `workflows/project_run.py`).
# T19's union is simulated via monkeypatch (same stand-in as Group B); this
# isolates T21's own "clause after the T19 union" + persistence code.
# --------------------------------------------------------------------------


def test_scan_run_summary_and_manifest_carry_memory_clause(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        project_run,
        "aggregate_results",
        _make_union_aggregate_results(real_aggregate_results),
    )
    monkeypatch.setattr(
        project_run,
        "_build_candidates",
        lambda _tools: [ScanCandidate("probe", "tool", "quality", "applicable", "t")],
    )
    monkeypatch.setattr(
        project_run,
        "ALL_TOOLS",
        [_MemTool("probe", {"version": 1, "used": [_mem_item("a")], "written": []})],
    )
    project_id, data_root = _register(tmp_path)
    plan = project_run.plan_scan(project_id, data_root=data_root)

    run = execute_scan(plan, permissions=ExecutionPermissions(), data_root=data_root)

    assert run.aggregate["summary"].endswith(
        "; memory: read 1 prior record, wrote 0 records"
    )
    assert run.aggregate["metadata"]["memory"]["used"][0]["id"] == "a"

    manifest = load_run_manifest(Path(run.root), run.run_id, attempt_id=run.attempt_id)
    assert manifest is not None
    assert manifest["aggregate"]["summary"].endswith(
        "; memory: read 1 prior record, wrote 0 records"
    )
    # Keep-green: the per-candidate child already carries its own receipt
    # today (`CandidateResult.to_dict`'s `child: dict(self.result)`), with no
    # T21 code change needed for this half of B4.
    child = manifest["scheduled"][0]["child"]
    assert child["metadata"]["memory"]["used"][0]["id"] == "a"


def test_scan_run_no_clause_when_no_memory_used(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Keep-green guard: no step reports memory use -> no clause."""
    monkeypatch.setattr(
        project_run,
        "aggregate_results",
        _make_union_aggregate_results(real_aggregate_results),
    )
    monkeypatch.setattr(
        project_run,
        "_build_candidates",
        lambda _tools: [ScanCandidate("probe", "tool", "quality", "applicable", "t")],
    )
    monkeypatch.setattr(project_run, "ALL_TOOLS", [_MemTool("probe")])
    project_id, data_root = _register(tmp_path)
    plan = project_run.plan_scan(project_id, data_root=data_root)

    run = execute_scan(plan, permissions=ExecutionPermissions(), data_root=data_root)

    assert "; memory:" not in run.aggregate["summary"]


# --------------------------------------------------------------------------
# Group D -- `ScanTool` lift + clause (`tools/scan.py`). `execute_scan` and
# `load_run_manifest` are monkeypatched directly so these isolate ScanTool's
# own deliverable from both T19 and the real scan pipeline.
# --------------------------------------------------------------------------


def test_scantool_run_lifts_memory_into_result_and_clause(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        scan_module,
        "resolve_project",
        lambda *_a, **_k: {"project_id": "p", "root": str(tmp_path)},
    )
    monkeypatch.setattr(scan_module, "load_scan_plan", lambda *_a, **_k: object())
    fake_run = _FakeScanRun(
        {
            "tool": "scan",
            "status": "ok",
            "summary": "scan: 0 finding(s)",
            "metadata": {
                "memory": {"version": 1, "used": [_mem_item("a")], "written": []}
            },
        }
    )
    monkeypatch.setattr(scan_module, "execute_scan", lambda *_a, **_k: fake_run)

    result = ScanTool().run(
        tmp_path,
        action="run",
        plan_id="plan-1",
        permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
    )

    assert (
        result["summary"]
        == "scan run: ok; memory: read 1 prior record, wrote 0 records"
    )
    assert (
        result.get("metadata", {}).get("memory", {}).get("used", [{}])[0].get("id")
        == "a"
    )


def test_scantool_run_no_clause_when_no_memory_used(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Keep-green guard."""
    monkeypatch.setattr(
        scan_module,
        "resolve_project",
        lambda *_a, **_k: {"project_id": "p", "root": str(tmp_path)},
    )
    monkeypatch.setattr(scan_module, "load_scan_plan", lambda *_a, **_k: object())
    fake_run = _FakeScanRun(
        {"tool": "scan", "status": "ok", "summary": "scan: 0 finding(s)"}
    )
    monkeypatch.setattr(scan_module, "execute_scan", lambda *_a, **_k: fake_run)

    result = ScanTool().run(
        tmp_path,
        action="run",
        plan_id="plan-1",
        permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
    )

    assert result["summary"] == "scan run: ok"
    assert "memory" not in result.get("metadata", {})


def test_scantool_run_denied_without_grant_has_no_clause(tmp_path: Path) -> None:
    """Keep-green guard (design §6: "without --allow-cache-write -> no
    clause, no metadata.memory"). `execute_scan` is never reached."""
    result = ScanTool().run(
        tmp_path, action="run", plan_id="plan-1", permissions=ExecutionPermissions()
    )

    assert result["status"] == "skipped"
    assert "; memory:" not in result["summary"]
    assert "memory" not in result.get("metadata", {})


def test_scantool_status_appends_attempt_memory_clause_from_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """B3: the clause comes verbatim from the stored manifest's
    `aggregate.metadata.memory` -- no new recall (B5)."""
    monkeypatch.setattr(
        scan_module,
        "resolve_project",
        lambda *_a, **_k: {"project_id": "p", "root": str(tmp_path)},
    )
    manifest = {
        "attempt_id": "attempt-7",
        "scheduled": [],
        "aggregate": {
            "metadata": {
                "memory": {"version": 1, "used": [_mem_item("a")], "written": []}
            }
        },
    }
    monkeypatch.setattr(scan_module, "load_run_manifest", lambda *_a, **_k: manifest)

    result = ScanTool().run(tmp_path, action="status", run_id="run-1")

    assert result["summary"] == (
        "scan status: ok"
        "; attempt attempt-7 memory: read 1 prior record, wrote 0 records"
    )
    # B3: the ToolResult's own metadata.memory is omitted for status.
    assert "memory" not in result.get("metadata", {})


def test_scantool_status_no_clause_when_manifest_has_no_memory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Keep-green guard."""
    monkeypatch.setattr(
        scan_module,
        "resolve_project",
        lambda *_a, **_k: {"project_id": "p", "root": str(tmp_path)},
    )
    manifest = {"attempt_id": "attempt-7", "scheduled": [], "aggregate": {}}
    monkeypatch.setattr(scan_module, "load_run_manifest", lambda *_a, **_k: manifest)

    result = ScanTool().run(tmp_path, action="status", run_id="run-1")

    assert result["summary"] == "scan status: ok"
    assert "; memory:" not in result["summary"]


# --------------------------------------------------------------------------
# Group E -- resume/history receipt relocation. RED-via-T19: no monkeypatch
# stands in for this without re-implementing T19's own relocation logic in
# the test itself (which would test the fake, not the product). T21 adds
# only the clause on top of whatever `metadata.memory`/`metadata.cache.
# original_memory` T19 leaves behind; the exclusion itself is entirely T19's
# contract (design doc T19 B7; T21 design §6 "Resume"/"History"). T21's own
# formatting is still asserted exactly (the required, not the current,
# string).
# --------------------------------------------------------------------------


def test_resume_excludes_retained_candidates_read_from_new_attempt_clause(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """RED-via-T19. Design §6 "Resume": "the new attempt's clause excludes
    the retained review's read; `cache.original_memory` holds it." Candidate
    `retained` executes and is cancelled before `fresh` runs; on resume,
    `fresh` is the only candidate actually re-executed this attempt, so the
    clause must count only `fresh`'s read -- until T19 relocates the
    retained candidate's receipt to `metadata.cache.original_memory`, this
    worktree's `aggregate_results` (even simulated here per T19's own
    documented union contract) has no such relocation to apply, and the
    retained receipt keeps leaking into `metadata.memory`."""
    monkeypatch.setattr(
        project_run,
        "aggregate_results",
        _make_union_aggregate_results(real_aggregate_results),
    )
    monkeypatch.setattr(
        project_run,
        "_build_candidates",
        lambda _tools: [
            # Sorted execution order in `_run_candidates` is by candidate_id
            # -- "a-retained" must run (and request cancel) before
            # "b-fresh" is even started, so "b-fresh" is the only candidate
            # the resumed attempt actually (re-)executes.
            ScanCandidate("a-retained", "tool", "quality", "applicable", "t"),
            ScanCandidate("b-fresh", "tool", "quality", "applicable", "t"),
        ],
    )
    project_id, data_root = _register(tmp_path)
    plan = project_run.plan_scan(project_id, data_root=data_root)
    run_id = "run-resume-1"
    attempt_id = "attempt-resume-1"

    def _cancel_after_retained(_path: Path) -> dict[str, Any]:
        cancel_scan_run(project_id, run_id, attempt_id=attempt_id, data_root=data_root)
        return {
            "tool": "a-retained",
            "status": "ok",
            "duration_ms": 0,
            "summary": "a-retained: ok",
            "findings": [],
            "metadata": {
                "memory": {
                    "version": 1,
                    "used": [_mem_item("retained-read")],
                    "written": [],
                }
            },
        }

    monkeypatch.setattr(
        project_run,
        "ALL_TOOLS",
        [
            type(
                "_RetainedTool",
                (),
                {
                    "name": "a-retained",
                    "__call__": lambda self, path: _cancel_after_retained(path),
                },
            )(),
            _MemTool(
                "b-fresh",
                {"version": 1, "used": [_mem_item("fresh-read")], "written": []},
            ),
        ],
    )

    first = execute_scan(
        plan,
        run_id=run_id,
        attempt_id=attempt_id,
        permissions=ExecutionPermissions(),
        data_root=data_root,
    )
    assert first.run_state == "cancelled"

    resumed = resume_scan_run(project_id, run_id, data_root=data_root)

    memory = resumed.aggregate.get("metadata", {}).get("memory") or {}
    used_ids = {item["id"] for item in memory.get("used", [])}
    assert used_ids == {"fresh-read"}, (
        "resumed attempt's clause must count only the freshly-executed "
        "candidate's read, excluding the retained candidate's -- requires "
        "T19's metadata.cache.original_memory relocation, not implemented"
    )
    original_memory = (
        resumed.aggregate.get("metadata", {}).get("cache", {}).get("original_memory")
    )
    assert original_memory is not None, (
        "retained candidate's receipt must be disclosed in "
        "metadata.cache.original_memory (T19 B7), not implemented"
    )
