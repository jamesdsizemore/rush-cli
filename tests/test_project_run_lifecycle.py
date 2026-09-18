"""Tests for Phase 65 P65-08: progress, cancellation, and restart recovery
(F35).

Fixture tools are monkeypatched into `rush.workflows.project_run.ALL_TOOLS`
(with `ENGINE_SPECS` cleared so the real ~89 engine-only catalog rows never
mix in) -- the same technique `tests/test_full_project_scan.py` already
uses -- so every scenario here is deterministic and fast:

- `_InstantTool`: a normal candidate that returns immediately (optionally
  with a seeded finding), exercising the existing, unchanged generic
  `InvocationExecutor` execution path.
- `_CancellableChildTool`: implements the new duck-typed
  `run_cancellable(root, *, cancel_check)` contract and spawns a real,
  long-lived child process through `rush.runtime.subprocesses.run_subprocess`
  -- proving genuine mid-subprocess cancellation and no orphaned owned
  process, not a permissive/fake success condition.
- `_SelfCancellingTool`: a normal (non-cancellable) candidate that requests
  cancellation of its own run while it executes, deterministically
  exercising the candidate-boundary cooperative cancel check without any
  thread timing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

from rush.permissions import ExecutionPermissions
from rush.workflows import project_run
from rush.workflows.project_run import (
    ScanBusyError,
    ScanInvalidRequestError,
    ScanResumeStaleError,
    build_handoff,
    cancel_scan_run,
    compare_runs,
    execute_scan,
    latest_attempt_id,
    load_scan_events,
    plan_scan,
    rescan_project_run,
    resume_scan_run,
)
from rush.workflows.projects import register_project

_WRITE_PERMISSIONS = ExecutionPermissions(cache_write=True, artifact_write=True)


class _InstantTool:
    """A candidate that returns immediately through the existing, unchanged
    generic `InvocationExecutor` path -- no `run_cancellable`."""

    def __init__(self, name: str, findings: list[dict[str, Any]] | None = None) -> None:
        self.name = name
        self._findings = list(findings or [])

    def __call__(self, path: Path) -> dict[str, Any]:
        return {
            "tool": self.name,
            "engine": None,
            "engine_version": None,
            "status": "warn" if self._findings else "ok",
            "duration_ms": 1,
            "summary": f"{self.name}: ok",
            "findings": list(self._findings),
        }


class _CancellableChildTool:
    """A candidate exposing the new P65-08 duck-typed cancellation contract,
    running a real long-lived local child process."""

    def __init__(self, name: str, sleep_seconds: float = 8.0) -> None:
        self.name = name
        self.sleep_seconds = sleep_seconds

    def __call__(self, path: Path) -> dict[str, Any]:  # pragma: no cover
        raise AssertionError(f"{self.name} must be scheduled through run_cancellable")

    def run_cancellable(self, root: Path, *, cancel_check: Any) -> dict[str, Any]:
        # Deferred import: `rush.runtime.subprocesses` imported at module
        # level, before `rush.workflows.*` has fully triggered `rush.tools`/
        # `rush.runtime.result_helpers` init, hits a pre-existing circular-
        # import ordering issue -- see `tests/test_providers.py`'s own
        # function-local `from rush.runtime import subprocesses` for the
        # same workaround.
        from rush.runtime.subprocesses import SubprocessCancelled, run_subprocess

        argv = [sys.executable, "-c", f"import time; time.sleep({self.sleep_seconds})"]
        try:
            run_subprocess(
                argv,
                cwd=root,
                timeout=60,
                cancel_check=cancel_check,
                poll_interval=0.02,
            )
        except SubprocessCancelled as exc:
            return {
                "tool": self.name,
                "engine": None,
                "engine_version": None,
                "status": "error",
                "duration_ms": 0,
                "summary": f"{self.name}: cancelled",
                "findings": [],
                "metadata": {"cancelled": True, "cancelled_pid": exc.pid},
            }
        return {
            "tool": self.name,
            "engine": None,
            "engine_version": None,
            "status": "ok",
            "duration_ms": 0,
            "summary": f"{self.name}: ok",
            "findings": [],
        }


class _SelfCancellingTool:
    """A candidate that requests cancellation of its own run_id while it
    executes -- deterministically exercises the candidate-boundary
    cooperative cancel check with no thread timing involved."""

    def __init__(
        self, name: str, project_id: str, run_id: str, data_root: Path
    ) -> None:
        self.name = name
        self._project_id = project_id
        self._run_id = run_id
        self._data_root = data_root

    def __call__(self, path: Path) -> dict[str, Any]:
        cancel_scan_run(self._project_id, self._run_id, data_root=self._data_root)
        return {
            "tool": self.name,
            "engine": None,
            "engine_version": None,
            "status": "ok",
            "duration_ms": 1,
            "summary": f"{self.name}: ok",
            "findings": [],
        }


def _process_alive(pid: int) -> bool:
    """Portable liveness check -- always executed, never skipped by
    platform: POSIX uses a signal-0 probe, Windows parses `tasklist`."""
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/fi", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_until(
    predicate: Any, *, timeout: float = 10.0, interval: float = 0.02
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _safe_events(root: Path, run_id: str) -> list[dict[str, Any]]:
    try:
        return list(load_scan_events(root, run_id)["events"])
    except ScanInvalidRequestError:
        return []


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("def unreviewed():\n    pass\n", encoding="utf-8")
    return root


def _register(tmp_path: Path) -> tuple[str, Path]:
    root = _fixture_root(tmp_path)
    data_root = tmp_path / "rush-data"
    record = register_project(root, data_root=data_root)
    return record.project_id, data_root


def test_cancel_mid_subprocess_terminates_owned_child_with_no_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_run, "ENGINE_SPECS", {})
    seeded_finding = {
        "path": "app.py",
        "line": 1,
        "rule": "seeded-rule",
        "severity": "warn",
        "message": "seeded finding",
    }
    monkeypatch.setattr(
        project_run,
        "ALL_TOOLS",
        [
            _InstantTool("aaa-quick-check", findings=[seeded_finding]),
            _CancellableChildTool("download", sleep_seconds=8.0),
            _InstantTool("zzz-never-started"),
        ],
    )
    project_id, data_root = _register(tmp_path)
    plan = plan_scan(project_id, data_root=data_root)
    root = Path(plan.root)
    run_id = str(uuid.uuid4())

    outcome: dict[str, Any] = {}

    def _do_run() -> None:
        try:
            outcome["run"] = execute_scan(
                plan,
                run_id=run_id,
                permissions=_WRITE_PERMISSIONS,
                data_root=data_root,
            )
        except BaseException as exc:  # noqa: BLE001 -- surfaced in main thread below
            outcome["error"] = exc

    thread = threading.Thread(target=_do_run)
    thread.start()
    try:
        started = _wait_until(
            lambda: any(
                e.get("event") == "candidate_started"
                and e.get("candidate_id") == "download"
                for e in _safe_events(root, run_id)
            ),
            timeout=10.0,
        )
        assert started, "download candidate never started"
        cancel_scan_run(project_id, run_id, data_root=data_root)
        thread.join(timeout=15)
        assert not thread.is_alive(), "execute_scan did not return after cancellation"
    finally:
        if thread.is_alive():
            thread.join(timeout=1)

    if "error" in outcome:
        raise outcome["error"]
    run = outcome["run"]

    assert run.run_state == "cancelled"
    by_id = {item.candidate.candidate_id: item for item in run.candidate_results}
    assert by_id["aaa-quick-check"].outcome == "executed"
    assert by_id["download"].outcome == "cancelled"
    assert "zzz-never-started" not in by_id, (
        "candidate scheduled after cancel must not start"
    )

    for item in run.candidate_results:
        assert item.outcome in {
            "executed",
            "unavailable",
            "permission_blocked",
            "failed",
            "cancelled",
        }

    pid = by_id["download"].result["metadata"]["cancelled_pid"]
    assert not _process_alive(pid), "cancelled child process was left as an orphan"

    # Retained evidence from before the cancellation still supports a normal
    # handoff -- a cancelled run's partial findings are not lost.
    handoff = build_handoff(project_id, run.run_id, "agent-1", data_root=data_root)
    assert handoff.state == "prepared"
    assert handoff.finding_ids


def test_resume_after_crash_before_aggregate_retains_executed_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_run, "ENGINE_SPECS", {})
    monkeypatch.setattr(
        project_run,
        "ALL_TOOLS",
        [_InstantTool("quick-a"), _InstantTool("quick-b")],
    )
    project_id, data_root = _register(tmp_path)
    plan = plan_scan(project_id, data_root=data_root)
    root = Path(plan.root)

    def _boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("simulated process death before aggregate")

    with monkeypatch.context() as crash_patch:
        crash_patch.setattr(project_run, "aggregate_results", _boom)
        with pytest.raises(RuntimeError, match="simulated process death"):
            execute_scan(plan, permissions=_WRITE_PERMISSIONS, data_root=data_root)

    runs_dir = root / ".rush" / "runs"
    run_id = next(p.name for p in runs_dir.iterdir() if p.is_dir())
    attempts_dir = runs_dir / run_id / "attempts"
    attempt_id = next(p.name for p in attempts_dir.iterdir() if p.is_dir())
    manifest_path = attempts_dir / attempt_id / "manifest.json"
    assert not manifest_path.is_file(), (
        "manifest must not exist yet -- the simulated crash happened before it"
    )

    candidates_dir = attempts_dir / attempt_id / "candidates"
    assert candidates_dir.is_dir()
    assert len(list(candidates_dir.glob("*.json"))) == 2, (
        "both child results must be retained even though the aggregate never ran"
    )

    re_executed: list[str] = []
    original = project_run._execute_candidate

    def _spy(candidate: Any, **kwargs: Any) -> Any:
        re_executed.append(candidate.candidate_id)
        return original(candidate, **kwargs)

    monkeypatch.setattr(project_run, "_execute_candidate", _spy)

    run = resume_scan_run(
        project_id, run_id, permissions=_WRITE_PERMISSIONS, data_root=data_root
    )

    assert run.run_id == run_id
    assert run.attempt_id != attempt_id, "a valid resume mints a new attempt id"
    assert run.run_state == "completed"
    assert re_executed == [], "already-completed candidates must not be re-executed"

    by_id = {item.candidate.candidate_id: item for item in run.candidate_results}
    assert by_id["quick-a"].outcome == "executed"
    assert by_id["quick-b"].outcome == "executed"
    assert Path(run.manifest_path).is_file()


def test_stale_resume_denied_then_valid_resume_gets_new_attempt_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_run, "ENGINE_SPECS", {})
    project_id, data_root = _register(tmp_path)
    run_id = str(uuid.uuid4())
    seeded_finding = {
        "path": "app.py",
        "line": 1,
        "rule": "seeded-rule",
        "severity": "warn",
        "message": "seeded finding",
    }
    monkeypatch.setattr(
        project_run,
        "ALL_TOOLS",
        [
            _InstantTool("aaa-quick-check", findings=[seeded_finding]),
            _SelfCancellingTool("mid-cancel", project_id, run_id, data_root),
            _InstantTool("zzz-never-started"),
        ],
    )
    plan = plan_scan(project_id, data_root=data_root)
    root = Path(plan.root)

    run = execute_scan(
        plan, run_id=run_id, permissions=_WRITE_PERMISSIONS, data_root=data_root
    )
    assert run.run_state == "cancelled"
    by_id = {item.candidate.candidate_id: item for item in run.candidate_results}
    assert by_id["aaa-quick-check"].outcome == "executed"
    assert by_id["mid-cancel"].outcome == "executed", (
        "the self-cancelling candidate itself finishes"
    )
    assert "zzz-never-started" not in by_id
    original_attempt_id = run.attempt_id
    attempts_dir = root / ".rush" / "runs" / run_id / "attempts"

    # First, a valid retry with *no* source change: new attempt id, the two
    # already-'executed' candidates are retained (never re-run), and the
    # candidate that never got to start now actually executes.
    re_executed: list[str] = []
    original = project_run._execute_candidate

    def _spy(candidate: Any, **kwargs: Any) -> Any:
        re_executed.append(candidate.candidate_id)
        return original(candidate, **kwargs)

    monkeypatch.setattr(project_run, "_execute_candidate", _spy)

    resumed = resume_scan_run(
        project_id, run_id, permissions=_WRITE_PERMISSIONS, data_root=data_root
    )

    assert resumed.run_id == run_id
    assert resumed.attempt_id != original_attempt_id
    assert resumed.run_state == "completed"
    assert "aaa-quick-check" not in re_executed
    assert "mid-cancel" not in re_executed
    assert "zzz-never-started" in re_executed

    by_id_resumed = {
        item.candidate.candidate_id: item for item in resumed.candidate_results
    }
    assert by_id_resumed["zzz-never-started"].outcome == "executed"
    assert len(list(attempts_dir.iterdir())) == 2, (
        "the valid retry adds exactly one new attempt"
    )

    # Now the project's source changes after that latest attempt started ->
    # a further resume must be denied, not silently accepted, and must not
    # create a third attempt.
    (root / "app.py").write_text(
        "def unreviewed():\n    pass\n# changed\n", encoding="utf-8"
    )
    with pytest.raises(ScanResumeStaleError):
        resume_scan_run(
            project_id, run_id, permissions=_WRITE_PERMISSIONS, data_root=data_root
        )
    assert len(list(attempts_dir.iterdir())) == 2, (
        "a denied stale resume must not create a new attempt"
    )


def test_cancel_scan_run_rejects_unknown_run_id(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    with pytest.raises(ScanInvalidRequestError):
        cancel_scan_run(project_id, "not-a-real-run-id", data_root=data_root)


def test_resume_scan_run_rejects_unknown_run_id(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    with pytest.raises(ScanInvalidRequestError):
        resume_scan_run(project_id, "not-a-real-run-id", data_root=data_root)


def test_load_scan_events_exposes_ordered_sequence_and_terminal_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_run, "ENGINE_SPECS", {})
    monkeypatch.setattr(project_run, "ALL_TOOLS", [_InstantTool("only-check")])
    project_id, data_root = _register(tmp_path)
    plan = plan_scan(project_id, data_root=data_root)
    root = Path(plan.root)

    run = execute_scan(plan, permissions=_WRITE_PERMISSIONS, data_root=data_root)

    progress = load_scan_events(root, run.run_id)
    assert progress["run_state"] == "completed"
    sequences = [event["sequence"] for event in progress["events"]]
    assert sequences == list(range(1, len(sequences) + 1))
    event_names = [event["event"] for event in progress["events"]]
    assert "attempt_started" in event_names
    assert "candidate_started" in event_names
    assert "candidate_completed" in event_names
    assert event_names[-1] == "run_completed"


# --- P69-02j/k/l/m: execution identity, attempt-ordering fix, locking -----


def _write_legacy_attempt_header(
    root: Path, run_id: str, attempt_id: str, *, started_at: str
) -> None:
    """A pre-fix attempt header: no `attempt_generation` field at all."""
    attempt_dir = root / ".rush" / "runs" / run_id / "attempts" / attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=True)
    header = {
        "run_id": run_id,
        "attempt_id": attempt_id,
        "plan_id": "fixture-plan",
        "project_id": "fixture-project",
        "started_at": started_at,
        "source_signature": "fixture-signature",
    }
    (attempt_dir / "attempt.json").write_text(json.dumps(header), encoding="utf-8")


def test_generation_counter_file_does_not_appear_inside_attempts_dir_and_does_not_change_its_entry_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_run, "ENGINE_SPECS", {})
    monkeypatch.setattr(project_run, "ALL_TOOLS", [_InstantTool("only-check")])
    project_id, data_root = _register(tmp_path)
    plan = plan_scan(project_id, data_root=data_root)
    root = Path(plan.root)

    run = execute_scan(plan, permissions=_WRITE_PERMISSIONS, data_root=data_root)

    run_dir = root / ".rush" / "runs" / run.run_id
    attempts_dir = run_dir / "attempts"
    assert len(list(attempts_dir.iterdir())) == 1

    generation_path = run_dir / ".generation"
    assert generation_path.is_file(), (
        "generation counter must be a sibling of attempts/"
    )
    assert not (attempts_dir / ".generation").exists()
    # The counter file's existence must never itself count as an attempt.
    assert len(list(attempts_dir.iterdir())) == 1


def test_generation_counter_bootstraps_from_existing_attempt_count_not_zero_for_a_run_with_pre_fix_attempts(
    tmp_path: Path,
) -> None:
    project_id, data_root = _register(tmp_path)
    root = Path(project_run.resolve_project(project_id, data_root=data_root)["root"])
    run_id = str(uuid.uuid4())
    for _ in range(2):
        _write_legacy_attempt_header(
            root, run_id, str(uuid.uuid4()), started_at="2020-01-01T00:00:00+00:00"
        )

    first = project_run._next_attempt_generation(root, run_id)
    assert first == 3, "bootstraps from the 2 existing legacy attempts, not 0"
    second = project_run._next_attempt_generation(root, run_id)
    assert second == 4, (
        "a persisted counter is read-and-incremented, not re-bootstrapped"
    )


def test_a_single_post_fix_attempt_always_outranks_every_legacy_attempt_for_the_same_run_regardless_of_started_at(
    tmp_path: Path,
) -> None:
    project_id, data_root = _register(tmp_path)
    root = Path(project_run.resolve_project(project_id, data_root=data_root)["root"])
    run_id = str(uuid.uuid4())
    _write_legacy_attempt_header(
        root, run_id, "legacy-attempt", started_at="2999-01-01T00:00:00+00:00"
    )
    post_fix_dir = root / ".rush" / "runs" / run_id / "attempts" / "post-fix-attempt"
    post_fix_dir.mkdir(parents=True, exist_ok=True)
    (post_fix_dir / "attempt.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "attempt_id": "post-fix-attempt",
                "started_at": "2000-01-01T00:00:00+00:00",
                "attempt_generation": 1,
            }
        ),
        encoding="utf-8",
    )

    selected = project_run._highest_generation_attempt_dir(root, run_id)
    assert selected is not None
    assert selected.name == "post-fix-attempt"


def test_latest_attempt_selection_falls_back_to_started_at_when_every_attempt_for_a_run_is_still_legacy(
    tmp_path: Path,
) -> None:
    project_id, data_root = _register(tmp_path)
    root = Path(project_run.resolve_project(project_id, data_root=data_root)["root"])
    run_id = str(uuid.uuid4())
    _write_legacy_attempt_header(
        root, run_id, "earlier", started_at="2020-01-01T00:00:00+00:00"
    )
    _write_legacy_attempt_header(
        root, run_id, "later", started_at="2021-01-01T00:00:00+00:00"
    )

    selected = project_run._highest_generation_attempt_dir(root, run_id)
    assert selected is not None
    assert selected.name == "later"


def test_two_legacy_attempts_sharing_an_identical_started_at_select_deterministically_regardless_of_directory_enumeration_order(
    tmp_path: Path,
) -> None:
    project_id, data_root = _register(tmp_path)
    root = Path(project_run.resolve_project(project_id, data_root=data_root)["root"])
    run_id = str(uuid.uuid4())
    _write_legacy_attempt_header(
        root, run_id, "zzz-attempt", started_at="2020-01-01T00:00:00+00:00"
    )
    _write_legacy_attempt_header(
        root, run_id, "aaa-attempt", started_at="2020-01-01T00:00:00+00:00"
    )

    first = project_run._highest_generation_attempt_dir(root, run_id)
    second = project_run._highest_generation_attempt_dir(root, run_id)
    assert first is not None
    assert first.name == second.name == "zzz-attempt", (
        "attempt_id is the final tie-break, deterministic regardless of call order"
    )


def test_execute_scan_and_resume_and_rescan_accept_attempt_id_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_run, "ENGINE_SPECS", {})
    monkeypatch.setattr(project_run, "ALL_TOOLS", [_InstantTool("only-check")])
    project_id, data_root = _register(tmp_path)
    plan = plan_scan(project_id, data_root=data_root)

    run = execute_scan(
        plan,
        attempt_id="custom-attempt-1",
        permissions=_WRITE_PERMISSIONS,
        data_root=data_root,
    )
    assert run.attempt_id == "custom-attempt-1"

    resumed = resume_scan_run(
        project_id,
        run.run_id,
        attempt_id="custom-attempt-2",
        expected_attempt_id="custom-attempt-1",
        permissions=_WRITE_PERMISSIONS,
        data_root=data_root,
    )
    assert resumed.attempt_id == "custom-attempt-2"

    result = rescan_project_run(
        project_id,
        run.run_id,
        new_run_id="custom-run-3",
        attempt_id="custom-attempt-3",
        permissions=_WRITE_PERMISSIONS,
        data_root=data_root,
    )
    assert result["run"]["run_id"] == "custom-run-3"
    assert result["run"]["attempt_id"] == "custom-attempt-3"


def test_resume_raises_structured_conflict_when_a_concurrent_resume_lands_a_newer_attempt_between_dispatch_capture_and_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_run, "ENGINE_SPECS", {})
    monkeypatch.setattr(project_run, "ALL_TOOLS", [_InstantTool("only-check")])
    project_id, data_root = _register(tmp_path)
    plan = plan_scan(project_id, data_root=data_root)
    root = Path(plan.root)

    run = execute_scan(plan, permissions=_WRITE_PERMISSIONS, data_root=data_root)
    attempts_dir = root / ".rush" / "runs" / run.run_id / "attempts"
    assert len(list(attempts_dir.iterdir())) == 1

    with pytest.raises(ScanBusyError):
        resume_scan_run(
            project_id,
            run.run_id,
            expected_attempt_id="stale-attempt-id-not-the-real-one",
            permissions=_WRITE_PERMISSIONS,
            data_root=data_root,
        )
    assert len(list(attempts_dir.iterdir())) == 1, (
        "a rejected conflict must not create a new attempt"
    )


def test_cancellation_is_not_cleared_when_the_locked_expected_attempt_id_check_rejects_the_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_run, "ENGINE_SPECS", {})
    monkeypatch.setattr(project_run, "ALL_TOOLS", [_InstantTool("only-check")])
    project_id, data_root = _register(tmp_path)
    plan = plan_scan(project_id, data_root=data_root)
    root = Path(plan.root)

    run = execute_scan(plan, permissions=_WRITE_PERMISSIONS, data_root=data_root)
    cancel_scan_run(project_id, run.run_id, data_root=data_root)
    assert project_run._cancel_requested(root, run.run_id)

    with pytest.raises(ScanBusyError):
        resume_scan_run(
            project_id,
            run.run_id,
            expected_attempt_id="stale-attempt-id-not-the-real-one",
            permissions=_WRITE_PERMISSIONS,
            data_root=data_root,
        )
    assert project_run._cancel_requested(root, run.run_id), (
        "a rejected conflict must not clear a pending cancel request"
    )


def test_rescan_raises_structured_conflict_when_the_baseline_advances_between_dispatch_capture_and_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_run, "ENGINE_SPECS", {})
    monkeypatch.setattr(project_run, "ALL_TOOLS", [_InstantTool("only-check")])
    project_id, data_root = _register(tmp_path)
    plan = plan_scan(project_id, data_root=data_root)

    baseline = execute_scan(plan, permissions=_WRITE_PERMISSIONS, data_root=data_root)
    stale_attempt_id = baseline.attempt_id

    # Advance the baseline run with a real resume before the rescan executes.
    resume_scan_run(
        project_id, baseline.run_id, permissions=_WRITE_PERMISSIONS, data_root=data_root
    )

    with pytest.raises(ScanBusyError):
        rescan_project_run(
            project_id,
            baseline.run_id,
            expected_attempt_id=stale_attempt_id,
            permissions=_WRITE_PERMISSIONS,
            data_root=data_root,
        )


def test_rescan_conflict_path_handles_a_missing_baseline_manifest_without_raising_typeerror(
    tmp_path: Path,
) -> None:
    project_id, data_root = _register(tmp_path)
    root = Path(project_run.resolve_project(project_id, data_root=data_root)["root"])
    run_id = str(uuid.uuid4())
    # A concurrent resume can publish a newer attempt directory without ever
    # finishing -- the run directory exists, but no attempt of it has a
    # terminal manifest yet.
    (root / ".rush" / "runs" / run_id / "attempts" / "in-flight").mkdir(
        parents=True, exist_ok=True
    )

    with pytest.raises(ScanBusyError):
        rescan_project_run(project_id, run_id, data_root=data_root)


def test_compare_runs_pinned_to_baseline_attempt_id_ignores_a_newer_baseline_attempt_published_after_execute_scan_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded_finding = {
        "path": "app.py",
        "line": 1,
        "rule": "seeded-rule",
        "severity": "warn",
        "message": "seeded finding",
    }
    monkeypatch.setattr(project_run, "ENGINE_SPECS", {})
    monkeypatch.setattr(
        project_run,
        "ALL_TOOLS",
        [_InstantTool("only-check", findings=[seeded_finding])],
    )
    project_id, data_root = _register(tmp_path)
    plan = plan_scan(project_id, data_root=data_root)

    baseline = execute_scan(plan, permissions=_WRITE_PERMISSIONS, data_root=data_root)
    original_attempt_id = baseline.attempt_id
    original_finding_ids = {
        f["finding_id"] for f in baseline.aggregate.get("findings") or []
    }
    assert original_finding_ids

    current = execute_scan(plan, permissions=_WRITE_PERMISSIONS, data_root=data_root)

    pinned = compare_runs(
        project_id,
        baseline.run_id,
        current.run_id,
        baseline_attempt_id=original_attempt_id,
        data_root=data_root,
    )
    assert set(pinned["persisting"]) == original_finding_ids
    assert pinned["resolved"] == []
    assert pinned["new"] == []

    # Advance the baseline run's own latest attempt to a clean one (zero
    # findings) -- a naive re-derivation of "latest" for the baseline side
    # would now see nothing to compare against.
    monkeypatch.setattr(project_run, "ALL_TOOLS", [_InstantTool("only-check")])
    advanced = execute_scan(
        plan,
        run_id=baseline.run_id,
        permissions=_WRITE_PERMISSIONS,
        data_root=data_root,
    )
    assert advanced.attempt_id != original_attempt_id
    assert not (advanced.aggregate.get("findings") or [])

    still_pinned = compare_runs(
        project_id,
        baseline.run_id,
        current.run_id,
        baseline_attempt_id=original_attempt_id,
        data_root=data_root,
    )
    assert set(still_pinned["persisting"]) == original_finding_ids, (
        "pinning must ignore the baseline run's newer, unrelated attempt"
    )

    unpinned = compare_runs(
        project_id, baseline.run_id, current.run_id, data_root=data_root
    )
    assert unpinned["persisting"] == [], (
        "without a pin, comparison re-selects the baseline's now-empty latest attempt"
    )
    assert set(unpinned["new"]) == original_finding_ids


def test_latest_attempt_id_returns_the_current_latest_attempt_and_none_for_unknown_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_run, "ENGINE_SPECS", {})
    monkeypatch.setattr(project_run, "ALL_TOOLS", [_InstantTool("only-check")])
    project_id, data_root = _register(tmp_path)
    plan = plan_scan(project_id, data_root=data_root)

    run = execute_scan(plan, permissions=_WRITE_PERMISSIONS, data_root=data_root)
    assert latest_attempt_id(project_id, run.run_id, data_root=data_root) == (
        run.attempt_id
    )
    assert (
        latest_attempt_id(project_id, "not-a-real-run-id", data_root=data_root) is None
    )
