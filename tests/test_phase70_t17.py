"""Phase 70 T17 -- Run and display every check step.

RED-only test matrix for the design-gate brief
`.scratch/phase-70-design-gate/W2-T9-T17.md` (## T17) and the plan packet
(`docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md`, T17).

T17 is last in W2 and depends on T8/T9/T16 landing first (Cross-task
sequencing summary). None of T8-T16 are implemented in this worktree, so
most cases here fail for that reason and are labelled RED-via-T{8,9,16}.
Cases that exercise only `run_workflow_suite`/`TestTool`/dashboard code
that exists today are asserted directly against real, current behavior.

No fixtures/helpers are shared with any other test file -- everything is
local to keep this task's edits to exactly one new file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rush.permissions import ExecutionPermissions
from rush.workflows.suites import CHECK_SUITE, WorkflowSuite


class _StubTool:
    """Minimal ToolFn-shaped double: `.name` + `__call__(path) -> ToolResult`."""

    def __init__(
        self,
        name: str,
        status: str = "ok",
        raises: bool = False,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self._status = status
        self._raises = raises
        self._extra = extra

    def __call__(self, path: Path) -> dict[str, Any]:
        if self._raises:
            raise RuntimeError(f"{self.name} handler blew up")
        result: dict[str, Any] = {
            "tool": self.name,
            "engine": None,
            "engine_version": None,
            "status": self._status,
            "duration_ms": 1,
            "summary": f"{self.name}: {self._status}",
            "findings": [],
            "raw": None,
        }
        if self._extra:
            result.update(self._extra)
        return result


def _six_step_suite(fail_fast_default: bool = False) -> WorkflowSuite:
    """A test double of the real 6-step D5 check suite, independent of
    whether `CHECK_SUITE` itself has landed the 6th step yet."""
    return WorkflowSuite(
        name="check",
        description="test double of the D5 six-step check suite",
        tool_sequence=("format", "lint", "typecheck", "dead", "slop", "test"),
        fail_fast_default=fail_fast_default,
    )


# --- S17.1/S17.2: CHECK_SUITE composition (real, current suites.py) --------


def test_t17_check_suite_composition_six_steps_in_d5_order():
    """S17.1: CHECK_SUITE gains `test` as its 6th step in D5 order.

    RED: today's `CHECK_SUITE.tool_sequence` is the 5-tuple
    ("format", "lint", "typecheck", "dead", "slop") -- no `test` step.
    """
    assert CHECK_SUITE.tool_sequence == (
        "format",
        "lint",
        "typecheck",
        "dead",
        "slop",
        "test",
    )


def test_t17_check_suite_fail_fast_default_is_false():
    """S17.2: `rush check` --fail-fast/--no-fail-fast default flips to False.

    RED: today's `CHECK_SUITE.fail_fast_default` is True.
    """
    assert CHECK_SUITE.fail_fast_default is False


# --- S17.1: the new CheckTool module (T17's own deliverable) ---------------


def test_t17_check_tool_module_exists_and_is_workflow_category():
    """S17.1/R17.1: new `rush.tools.check.CheckTool`, catalog category
    "workflow" (so full-project scans classify it not_applicable and it
    isn't double-counted as an analysis candidate).

    RED-via-T17-not-yet-implemented: `rush.tools.check` does not exist.
    """
    from rush.tools.check import CheckTool  # local import: module is new

    tool = CheckTool()
    assert tool.name == "check"

    from rush.catalog import TOOL_SPECS

    assert TOOL_SPECS["check"].category == "workflow"


# --- Guards: existing run_workflow_suite continuation semantics ------------
# These already hold today and must keep holding once the suite grows to
# six steps -- proves the 6th step doesn't need new continuation logic.


def test_t17_run_all_continues_through_fail_error_and_skip_outcomes(
    tmp_path, monkeypatch
):
    """S17.2/S17.4 (run-all + other step outcomes): a fail, a raising
    handler, and a skip mid-sequence all still let every later step run
    exactly once, in order.

    Guard: passes today against a synthetic 6-step suite (no dependency on
    the real CHECK_SUITE's step count).
    """
    import rush.workflows.suites as suites_mod

    stub_tools = [
        _StubTool("format", status="fail"),
        _StubTool("lint", status="ok"),
        _StubTool("typecheck", raises=True),
        _StubTool("dead", status="skipped"),
        _StubTool("slop", status="ok"),
        _StubTool("test", status="ok"),
    ]
    monkeypatch.setattr(suites_mod, "ALL_TOOLS", stub_tools)

    suite = _six_step_suite()
    result = suites_mod.run_workflow_suite(
        suite, tmp_path, ExecutionPermissions(), fail_fast=False
    )

    children = result["metadata"]["children"]
    assert [c["tool"] for c in children] == [
        "format",
        "lint",
        "typecheck",
        "dead",
        "slop",
        "test",
    ]
    assert [c["status"] for c in children] == [
        "fail",
        "ok",
        "error",
        "skipped",
        "ok",
        "ok",
    ]
    # The raising handler's exception path never appends to executed_tools.
    assert result["metadata"]["executed_tools"] == (
        "format",
        "lint",
        "dead",
        "slop",
        "test",
    )


def test_t17_step_not_registered_in_all_tools_recorded_as_skipped_child(
    tmp_path, monkeypatch
):
    """S17.4: an unregistered step name (e.g. a name mismatch) becomes a
    real skipped child, never silently dropped.

    Guard: passes today; "test" is deliberately absent from the stub
    registry to hit the existing `tool is None` branch.
    """
    import rush.workflows.suites as suites_mod

    stub_tools = [_StubTool(n) for n in ("format", "lint", "typecheck", "dead", "slop")]
    monkeypatch.setattr(suites_mod, "ALL_TOOLS", stub_tools)

    suite = _six_step_suite()
    result = suites_mod.run_workflow_suite(
        suite, tmp_path, ExecutionPermissions(), fail_fast=False
    )

    children = result["metadata"]["children"]
    assert children[-1]["tool"] == "test"
    assert children[-1]["status"] == "skipped"


# --- S17.2: fail-fast / cancellation must fill in the remaining steps ------


def test_t17_fail_fast_records_remaining_steps_not_run_with_cause(
    tmp_path, monkeypatch
):
    """S17.2: explicit fail-fast gives every remaining step a `skipped`
    child with `metadata.execution.disposition="not_run"` and
    `cause="fail_fast_after:<step>"` -- never just stops emitting entries.

    RED: today's `run_workflow_suite` `break`s on fail-fast with nothing
    appended for the remaining steps at all, so `len(children) == 1`.
    """
    import rush.workflows.suites as suites_mod

    stub_tools = [
        _StubTool("format", status="fail"),
        _StubTool("lint"),
        _StubTool("typecheck"),
        _StubTool("dead"),
        _StubTool("slop"),
        _StubTool("test"),
    ]
    monkeypatch.setattr(suites_mod, "ALL_TOOLS", stub_tools)

    suite = _six_step_suite()
    result = suites_mod.run_workflow_suite(
        suite, tmp_path, ExecutionPermissions(), fail_fast=True
    )

    children = result["metadata"]["children"]
    assert len(children) == 6, (
        f"expected all 6 steps recorded (1 executed + 5 not-run), got {len(children)}"
    )
    remaining = children[1:]
    assert all(c["status"] == "skipped" for c in remaining)
    for child in remaining:
        exec_meta = child.get("metadata", {}).get("execution", {})
        assert exec_meta.get("disposition") == "not_run"
        assert exec_meta.get("cause") == "fail_fast_after:format"


def test_t17_cancellation_marks_remaining_not_run_and_never_reports_clean_ok(
    tmp_path, monkeypatch
):
    """S17.2: cancellation between steps stops safely, marks every
    remaining step not-run/cancelled, and the aggregate is never a clean
    "ok" -- it must be at least warn.

    RED: today's `run_workflow_suite` appends nothing for the cancelled
    remainder (`len(children) == 2`), and because `skipped` ranks below
    `ok` in `routing._STATUS_RANK`, an all-ok-so-far aggregate would
    incorrectly stay "ok" even though 4 of 6 steps never ran.
    """
    import rush.workflows.suites as suites_mod

    stub_tools = [
        _StubTool(n) for n in ("format", "lint", "typecheck", "dead", "slop", "test")
    ]
    monkeypatch.setattr(suites_mod, "ALL_TOOLS", stub_tools)

    suite = _six_step_suite()
    calls = {"n": 0}

    def _cancel_after_two_started() -> bool:
        calls["n"] += 1
        return calls["n"] > 2

    result = suites_mod.run_workflow_suite(
        suite,
        tmp_path,
        ExecutionPermissions(),
        fail_fast=False,
        cancel_check=_cancel_after_two_started,
    )

    children = result["metadata"]["children"]
    assert len(children) == 6, (
        f"expected all 6 steps recorded (2 executed + 4 not-run/cancelled), "
        f"got {len(children)}"
    )
    assert result["metadata"]["cancelled"] is True
    assert result["status"] != "ok", (
        "a cancelled run with unrun steps must never report a clean ok status"
    )
    for child in children[2:]:
        exec_meta = child.get("metadata", {}).get("execution", {})
        assert exec_meta.get("disposition") == "not_run"
        assert exec_meta.get("cause") == "cancelled"


def test_t17_cancel_mid_step_terminates_real_long_running_child(tmp_path, monkeypatch):
    """S17.2/merged finding-17 resolution (amendment 2): cancelling while a
    step's own engine child is *actually running* must terminate that real
    child (checked here by its live pid), not just stop before the *next*
    step starts.

    Step 3 (typecheck) spawns a real `python -c "time.sleep(30)"` child
    through the normal `run_subprocess` path (Popen-level spy captures its
    real pid, per finding 26 -- no engine/run_engine is patched away).
    Cancellation is triggered ~0.5s after that child starts. This proves
    real, observable behavior -- a live child process either dies or it
    doesn't -- not just the presence of a contextvar name.

    RED: today, `run_workflow_suite`'s `cancel_check` is only ever polled
    *between* steps (see the cancellation test above), so it cannot reach
    a child already spawned mid-step -- the real child is still alive
    after 5s.
    """
    import contextlib
    import os
    import signal
    import subprocess
    import sys
    import threading
    import time as time_mod

    import rush.workflows.suites as suites_mod
    from rush.runtime.subprocesses import run_subprocess

    captured_pid: dict[str, int] = {}
    orig_popen_init = subprocess.Popen.__init__

    def _spy_popen_init(self, *args, **kwargs):
        orig_popen_init(self, *args, **kwargs)
        captured_pid.setdefault("pid", self.pid)

    monkeypatch.setattr(subprocess.Popen, "__init__", _spy_popen_init)

    step3_started = threading.Event()
    step3_start_time: dict[str, float] = {}

    class _RealLongRunningStep:
        name = "typecheck"

        def __call__(self, path: Path) -> dict[str, Any]:
            step3_start_time["t"] = time_mod.monotonic()
            step3_started.set()
            run_subprocess(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                timeout=35,
            )
            return {
                "tool": "typecheck",
                "engine": None,
                "engine_version": None,
                "status": "ok",
                "duration_ms": 1,
                "summary": "typecheck: ok",
                "findings": [],
                "raw": None,
            }

    stub_tools = [
        _StubTool("format"),
        _StubTool("lint"),
        _RealLongRunningStep(),
        _StubTool("dead"),
        _StubTool("slop"),
        _StubTool("test"),
    ]
    monkeypatch.setattr(suites_mod, "ALL_TOOLS", stub_tools)

    def _cancel_after_half_second() -> bool:
        started_at = step3_start_time.get("t")
        return started_at is not None and (time_mod.monotonic() - started_at) > 0.5

    suite = _six_step_suite()
    result_holder: dict[str, Any] = {}

    def _run() -> None:
        result_holder["result"] = suites_mod.run_workflow_suite(
            suite,
            tmp_path,
            ExecutionPermissions(),
            fail_fast=False,
            cancel_check=_cancel_after_half_second,
        )

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    assert step3_started.wait(timeout=5), "step 3's real child never started"

    deadline = time_mod.monotonic() + 5.0
    pid: int | None = None
    while time_mod.monotonic() < deadline and pid is None:
        pid = captured_pid.get("pid")
        if pid is None:
            time_mod.sleep(0.05)
    assert pid is not None, "step 3 never spawned a real child process"

    def _alive(p: int) -> bool:
        try:
            os.kill(p, 0)
        except OSError:
            return False
        return True

    try:
        deadline = time_mod.monotonic() + 5.0
        while time_mod.monotonic() < deadline and _alive(pid):
            time_mod.sleep(0.1)

        assert not _alive(pid), (
            f"expected the step-3 child (pid {pid}) to be terminated within "
            f"5s of cancellation (~0.5s after it started), but it is still "
            f"running 30s into its sleep -- cancel_check is never consulted "
            f"once a step's own subprocess is already in flight"
        )
    finally:
        # Never leak a real 30s-sleeping child regardless of the assertion
        # outcome above.
        if _alive(pid):
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGKILL)

    thread.join(timeout=5)
    result = result_holder.get("result")
    assert result is not None, "run_workflow_suite never returned"

    children = result["metadata"]["children"]
    typecheck_child = next(c for c in children if c["tool"] == "typecheck")
    exec_meta = typecheck_child.get("metadata", {}).get("execution", {})
    assert exec_meta.get("disposition") == "cancelled", (
        f"expected the terminated child's step to be recorded as "
        f"cancelled (not an 'engine crashed' error), got {typecheck_child!r}"
    )

    remaining = children[3:]
    assert all(c["status"] == "skipped" for c in remaining), (
        "steps after the cancelled one must be not_run, not executed"
    )
    for child in remaining:
        assert (
            child.get("metadata", {}).get("execution", {}).get("disposition")
            == "not_run"
        )

    assert result["status"] != "ok", (
        "a run that killed a mid-flight child must never report clean ok"
    )


# --- S17.4: step entries retain summary/status/scope/memory/reason --------


def test_t17_executed_children_metadata_carries_disposition_executed(
    tmp_path, monkeypatch
):
    """S17.4/Design §3: a step that actually ran gets
    `metadata.execution.disposition == "executed"` on its child entry.

    RED: today's `metadata.children` list comprehension keeps only
    `{"tool", "status"}` -- no per-child `metadata` at all.
    """
    import rush.workflows.suites as suites_mod

    stub_tools = [
        _StubTool(n) for n in ("format", "lint", "typecheck", "dead", "slop", "test")
    ]
    monkeypatch.setattr(suites_mod, "ALL_TOOLS", stub_tools)

    suite = _six_step_suite()
    result = suites_mod.run_workflow_suite(
        suite, tmp_path, ExecutionPermissions(), fail_fast=False
    )

    children = result["metadata"]["children"]
    assert len(children) == 6
    for child in children:
        exec_meta = child.get("metadata", {}).get("execution", {})
        assert exec_meta.get("disposition") == "executed", (
            f"step {child.get('tool')!r} missing executed disposition metadata"
        )


def test_t17_step_children_pass_through_summary_scope_and_memory_when_present(
    tmp_path, monkeypatch
):
    """S17.4: children keep each step's summary, and pass through scope
    and memory when the child ToolResult carries them; a skipped step
    keeps its reason.

    RED: today's children entries only have `tool`/`status` -- `summary`,
    `scope`, `memory` and the skip reason are all dropped.
    """
    import rush.workflows.suites as suites_mod

    stub_tools = [
        _StubTool("format"),
        _StubTool("lint"),
        _StubTool(
            "typecheck",
            extra={"scope": "changed-files", "memory": {"consumed": ["mem-1"]}},
        ),
        _StubTool("dead", status="skipped"),
        _StubTool("slop"),
        _StubTool("test"),
    ]
    monkeypatch.setattr(suites_mod, "ALL_TOOLS", stub_tools)

    suite = _six_step_suite()
    result = suites_mod.run_workflow_suite(
        suite, tmp_path, ExecutionPermissions(), fail_fast=False
    )

    children = result["metadata"]["children"]
    typecheck_child = next(c for c in children if c["tool"] == "typecheck")
    assert typecheck_child.get("summary"), "child entry dropped the step's summary"
    assert typecheck_child.get("scope") == "changed-files", "scope not passed through"
    assert typecheck_child.get("memory") == {"consumed": ["mem-1"]}, (
        "memory not passed through"
    )

    dead_child = next(c for c in children if c["tool"] == "dead")
    assert dead_child.get("reason") or "skipped" in dead_child.get("summary", ""), (
        "skipped child must retain the skip reason"
    )


# --- S17.2: CLI wiring ------------------------------------------------------


def test_t17_check_cmd_fail_fast_default_is_false():
    """S17.2: `rush check`'s own `--fail-fast/--no-fail-fast` click option
    default flips to False.

    RED: today's `check_cmd` option default is True.
    """
    from rush.cli import cli

    check_cmd = cli.commands["check"]
    fail_fast_param = next(p for p in check_cmd.params if p.name == "fail_fast")
    assert fail_fast_param.default is False


# --- S17.3/Trust boundary: TestTool is build-gated -------------------------


def _count_popen_spawns(monkeypatch) -> dict[str, int]:
    """Design-gate finding 26: every zero-spawn assertion counts spawns at
    `subprocess.Popen`, never by patching a tool's own `run_engine`/
    `run_subprocess` reference -- a spy at that level can't tell "the code
    took a path that never calls run_engine" apart from "run_engine itself
    would have spawned nothing anyway", and per finding 26's own probe,
    patching the wrong shared name can miss real spawns entirely. This
    still calls the *real* `Popen.__init__`, so a granted call really runs.
    """
    import subprocess

    calls = {"n": 0}
    orig_init = subprocess.Popen.__init__

    def _spy_init(self, *args, **kwargs):
        calls["n"] += 1
        return orig_init(self, *args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "__init__", _spy_init)
    return calls


def test_t17_popen_spy_detects_spawn_today_positive_control(tmp_path, monkeypatch):
    """Positive control (finding 26) for the Popen-level spy used by the two
    zero/one-spawn assertions below: today's still-ungated `TestTool.run`
    really spawns a runner, proving the spy observes real spawns rather
    than passing vacuously.

    Guard: passes today.
    """
    import rush.tools.test as test_mod

    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    calls = _count_popen_spawns(monkeypatch)

    test_mod.TestTool().run(tmp_path, permissions=ExecutionPermissions(build=True))

    assert calls["n"] >= 1, "expected the positive control to observe a real spawn"


def test_t17_test_tool_run_without_permissions_is_denied_with_zero_spawns(
    tmp_path, monkeypatch
):
    """S17.3 (fix round 1): `TestTool.run(path)` with no `permissions` is no
    grant -- `skipped` with the exact build-permission reason and zero
    runner/version spawns, counted at both `subprocess.Popen` and
    `subprocess.run`."""
    import subprocess

    import rush.tools.test as test_mod

    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    calls = _count_popen_spawns(monkeypatch)
    runs: list[object] = []
    orig_run = subprocess.run

    def _spy_run(*args, **kwargs):
        runs.append(args)
        return orig_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _spy_run)

    result = test_mod.TestTool().run(tmp_path)

    assert calls["n"] == 0, f"expected 0 Popen spawns, got {calls['n']}"
    assert runs == [], f"expected 0 subprocess.run calls, got {runs!r}"
    assert result["status"] == "skipped"
    assert result["summary"] == "skipped: requires permission: --allow-build"


def test_t17_test_tool_direct_call_without_grant_zero_runner_spawns(
    tmp_path, monkeypatch
):
    """S17.3: `TestTool.__call__`/`.run` must gate on an explicit build
    grant *before* any runner subprocess spawn -- denial gives 0 spawns,
    including any version probe, counted at `subprocess.Popen` (finding 26),
    and a skipped child naming the missing permission.

    RED: today's `TestTool.run` has no `permissions` parameter at all (so
    this raises TypeError instead of gating), and even if it did, nothing
    in the current `run()` body would stop the real spawn.
    """
    import rush.tools.test as test_mod

    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    calls = _count_popen_spawns(monkeypatch)

    result = test_mod.TestTool().run(tmp_path, permissions=ExecutionPermissions())

    assert calls["n"] == 0, (
        f"expected 0 Popen spawns (incl. version probes) without "
        f"--allow-build, got {calls['n']}"
    )
    assert result["status"] == "skipped"
    assert "build" in result["summary"] or "permission" in result["summary"]


def test_t17_test_tool_direct_call_with_allow_build_grant_one_runner_spawn(
    tmp_path, monkeypatch
):
    """S17.3: with an explicit build grant, `TestTool.run` invokes at least
    one real runner spawn, counted at `subprocess.Popen` (finding 26).

    RED-via-signature-gap: today's `TestTool.run(self, path, *, config=None)`
    has no `permissions` parameter at all, so passing one raises TypeError
    instead of gating -- the exact absence S17.3 requires closing.
    """
    import rush.tools.test as test_mod

    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    calls = _count_popen_spawns(monkeypatch)

    result = test_mod.TestTool().run(
        tmp_path, permissions=ExecutionPermissions(build=True)
    )

    assert calls["n"] >= 1, (
        f"expected at least 1 real Popen spawn with --allow-build, got {calls['n']}"
    )
    assert result["status"] == "ok"


# --- S17.5 (dashboard consumer): cancelled/incomplete run_state ------------


def test_t17_dashboard_manifest_run_state_reflects_cancelled_not_hardcoded_completed(
    tmp_path, monkeypatch
):
    """S17.5/R17.4: the dashboard's CHECK_SUITE manifest `run_state` must
    reflect a cancelled/incomplete aggregate, not a hardcoded "completed".

    RED: `publish_check_suite_scan` hardcodes `"run_state": "completed"`
    unconditionally today, ignoring `aggregate["metadata"]["cancelled"]`.
    """
    from rush.dashboard import server as dashboard_server

    monkeypatch.setattr(dashboard_server, "_scan_file_inventory", lambda root: [])
    monkeypatch.setattr(
        dashboard_server, "_content_digests", lambda root, inventory: {}
    )
    monkeypatch.setattr(dashboard_server, "_source_identity", lambda digests, root: {})
    monkeypatch.setattr(
        dashboard_server, "_publish_scan_snapshot", lambda *a, **k: None
    )

    written: dict[str, bytes] = {}

    def _fake_atomic_write_bytes(root, relative, data):
        written["manifest"] = data

    monkeypatch.setattr(
        dashboard_server, "atomic_write_bytes", _fake_atomic_write_bytes
    )

    aggregate = {
        "tool": "check",
        "status": "warn",
        "findings": [],
        "summary": "check: cancelled mid-run",
        "metadata": {"cancelled": True, "children": []},
    }

    dashboard_server.publish_check_suite_scan(
        object(),
        "proj-1",
        tmp_path,
        aggregate,
        run_id="r1",
        attempt_id="1",
        scan_generation=1,
    )

    manifest = json.loads(written["manifest"])
    assert manifest["run_state"] != "completed", (
        "cancelled/incomplete check-suite run must not report a clean "
        "completed manifest run_state"
    )


# --- S17.5 (TUI consumer): cancelled worker status -------------------------


def test_t17_initial_check_worker_reports_cancelled_status_not_complete(monkeypatch):
    """S17.5: `_start_initial_check_thread`'s background worker must map a
    cancelled CHECK_SUITE aggregate to `project.status == "cancelled"`,
    matching the dashboard's own incomplete/cancelled `run_state` (previous
    test) instead of a blanket "complete".

    Real `ProjectState`/`ScanActions` fixtures, built locally in this file
    (no shared conftest/helpers): `dashboard_owner=None` takes the local
    daemon-thread path (`_dashboard_owner_for` returns None), and the
    process-wide owner lock is faked exactly like `tests/test_tui.py`'s own
    established pattern (`_OWNER_INSTANCE`/`_OWNER_LOCK` reset plus a fake
    `rush.dashboard.state.OwnerLock`), so no real lockfile/data-root I/O is
    needed.

    RED: today's worker (`tui.py`) unconditionally sets
    `project.status = "complete"` for any dict result, regardless of
    `metadata.cancelled`.
    """
    from types import SimpleNamespace

    import rush.tui as tui_module

    monkeypatch.setattr(tui_module, "_OWNER_INSTANCE", [])
    monkeypatch.setattr(tui_module, "_OWNER_LOCK", [])
    monkeypatch.setattr(
        "rush.dashboard.state.OwnerLock",
        lambda owner_instance_id, **k: SimpleNamespace(
            owner_instance_id=owner_instance_id
        ),
    )

    def _cancelled_check_suite(root, **kwargs):
        return {
            "tool": "check",
            "status": "warn",
            "findings": [],
            "summary": "check: cancelled mid-run",
            "metadata": {"cancelled": True, "children": []},
        }

    actions = tui_module.ScanActions(
        plan_scan=lambda *a, **k: None,
        execute_scan=lambda *a, **k: None,
        cancel_scan_run=lambda *a, **k: None,
        rescan_project_run=lambda *a, **k: None,
        build_handoff=lambda *a, **k: None,
        dispatch_handoff=lambda *a, **k: None,
        load_scan_events=lambda *a, **k: None,
        list_agents=list,
        run_check_suite=_cancelled_check_suite,
        dashboard_owner=None,
    )
    project = tui_module.ProjectState(
        name="demo", root=Path("/tmp/rush-tui-t17-cancel")
    )

    tui_module._start_initial_check_thread(project, actions)

    assert project.scan_thread is not None
    project.scan_thread.join(timeout=5)

    assert project.status == "cancelled", (
        f"expected a cancelled CHECK_SUITE result to set "
        f"project.status='cancelled', got {project.status!r}"
    )


# --- S17.6: MCP rush_check registered in the full profile ------------------


def test_t17_check_tool_registered_as_mcp_tool_in_full_profile():
    """S17.6: MCP `rush_check` is registered in the full profile.

    Written against T4's own names (`build_server(profile="full")"), per
    the orchestrator's explicit direction, even though T4 (core/full MCP
    profiles) is itself unimplemented.

    RED-via-T4-not-yet-implemented: today's `build_server` has only a
    `memory_session` parameter -- no `profile` at all -- so this raises
    TypeError instead of building a profiled server.
    """
    from rush.mcp import build_server

    server = build_server(profile="full")
    assert "rush_check" in server._tool_manager._tools


# --- Startup guard -----------------------------------------------------


def test_t17_tools_package_imports_without_cycle_and_cli_help_works():
    """Design §6 Startup: adding CheckTool must not introduce an import
    cycle, and `rush --help` keeps working.

    Guard: passes today (no CheckTool registered yet); must keep passing
    once T17 lands, which is why `CheckTool.run` is required to import
    `run_workflow_suite` lazily instead of at module scope.
    """
    import importlib

    importlib.import_module("rush.tools")

    from click.testing import CliRunner

    from rush.cli import cli

    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "check" in result.output
