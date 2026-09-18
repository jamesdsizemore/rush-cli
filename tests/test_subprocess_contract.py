"""Phase 00 shared local-subprocess safety contract.

P69-01 subsections i/j extend this module with the owned-subprocess
bootstrap-gate, recorded-pgid termination, and ownership-propagation
contract. Every owned-path test here is POSIX-only by construction (the
gate is an `os.pipe()` plus a `/bin/sh` `read`; termination is
`os.killpg`). Windows CI runs a named subset of test files that never
includes this one, so nothing here is skipped anywhere it runs.
"""

from __future__ import annotations

import dataclasses
import os
import signal
import subprocess
import time
import uuid
from contextlib import suppress
from pathlib import Path

import pytest

# `rush.tools.common` is imported first on purpose: importing the
# `rush.runtime` package first partially initializes it and raises a circular
# ImportError (pre-existing import topology, not introduced here).
import rush.tools.common  # noqa: F401
from rush.runtime import subprocesses
from rush.tools import common


def test_run_subprocess_uses_a_bounded_redacted_no_shell_process(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout="token=super-secret " + ("x" * 200),
            stderr="password=hunter2",
        )

    monkeypatch.setattr(common.subprocess, "run", fake_run)
    monkeypatch.setattr(common, "MAX_SUBPROCESS_OUTPUT_CHARS", 64)

    result = common.run_subprocess(
        ["fixture-engine", "--json"], cwd=tmp_path, timeout=7
    )

    assert calls == [
        (
            ["fixture-engine", "--json"],
            {
                "cwd": str(tmp_path),
                "timeout": 7,
                "stdin": subprocess.DEVNULL,
                "capture_output": True,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "env": None,
                "check": False,
                "shell": False,
            },
        )
    ]

    assert result.stdout.endswith("[TRUNCATED]")
    assert "super-secret" not in result.stdout
    assert "hunter2" not in result.stderr
    assert "[REDACTED]" in result.stderr


# ---------------------------------------------------------------------------
# P69-01.2i -- owned-subprocess bootstrap gate, records and termination
# ---------------------------------------------------------------------------


@pytest.fixture
def owned_data_root(tmp_path: Path, monkeypatch) -> Path:
    """Isolate `<data_root>/owners/` so `.procs` records never touch this
    OS user's real Rush data directory."""
    root = tmp_path / "rush-data"
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: root)
    return root


def _sentinel_binary(
    tmp_path: Path, sentinel: Path, *, sleep_seconds: float = 0.0
) -> Path:
    """A stand-in for a real engine binary whose very first action is an
    externally observable marker, so "did the real program actually start"
    is answerable without trusting any Rush-side bookkeeping."""
    script = tmp_path / f"fake-engine-{uuid.uuid4().hex}.sh"
    script.write_text(
        "#!/bin/sh\n"
        f'touch "{sentinel}"\n'
        f"sleep {sleep_seconds}\n"
        "echo fake-engine 1.2.3\n"
    )
    script.chmod(0o755)
    return script


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _pattern_pids(pattern: str) -> list[int]:
    result = subprocess.run(
        ["pgrep", "-f", pattern], capture_output=True, text=True, check=False
    )
    return [int(line) for line in result.stdout.split() if line.strip().isdigit()]


def _fork_and_run(target, *args) -> int:
    pid = os.fork()
    if pid == 0:  # pragma: no cover -- child process, never reported by pytest
        try:
            target(*args)
        finally:
            os._exit(0)
    return pid


def _kill_and_reap(pid: int) -> None:
    with suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)
    with suppress(ChildProcessError):
        os.waitpid(pid, 0)


def test_owned_subprocess_real_engine_binary_never_execs_before_the_procs_record_is_durably_persisted_and_the_gate_is_released(
    tmp_path: Path, monkeypatch, owned_data_root: Path
) -> None:
    sentinel = tmp_path / "engine-started"
    binary = _sentinel_binary(tmp_path, sentinel)
    observed: dict[str, object] = {}
    real_record = subprocesses._record_owned_process

    def observing_record(owner_instance_id: str, run_id: str, pgid: int) -> None:
        observed["sentinel_before_record"] = sentinel.exists()
        real_record(owner_instance_id, run_id, pgid)
        # The record is now durably persisted but the gate has NOT been
        # released: the real binary must still not have run a single
        # instruction, however long we wait here.
        time.sleep(0.3)
        observed["sentinel_after_record_before_release"] = sentinel.exists()
        observed["record_on_disk"] = subprocesses._owner_procs_path(
            owner_instance_id
        ).read_text()

    monkeypatch.setattr(subprocesses, "_record_owned_process", observing_record)

    result = subprocesses.run_subprocess(
        [str(binary)], owner_instance_id="owner-gate", run_id="run-gate"
    )

    assert observed["sentinel_before_record"] is False
    assert observed["sentinel_after_record_before_release"] is False
    assert "owner-gate" in str(observed["record_on_disk"])
    assert _wait_until(sentinel.exists)
    assert result.returncode == 0


def test_release_payload_actually_causes_the_real_engine_binary_to_launch_not_merely_that_it_never_launches_early(
    tmp_path: Path, owned_data_root: Path
) -> None:
    sentinel = tmp_path / "engine-started"
    binary = _sentinel_binary(tmp_path, sentinel)

    result = subprocesses.run_subprocess(
        [str(binary)], owner_instance_id="owner-release", run_id="run-release"
    )

    # A gate stuck permanently closed must not silently pass this suite.
    assert sentinel.exists()
    assert result.returncode == 0
    assert "fake-engine 1.2.3" in result.stdout


def test_owner_death_before_gate_release_including_before_popen_returns_means_the_real_engine_binary_never_launches_at_all(
    tmp_path: Path, owned_data_root: Path
) -> None:
    # Variant A: the owner dies after the gate process exists and its pgid
    # is known, but before the release payload is ever written.
    sentinel_a = tmp_path / "engine-started-a"
    binary_a = _sentinel_binary(tmp_path, sentinel_a)
    pgid_file = tmp_path / "gate-pgid"

    def _owner_hangs_before_release() -> None:
        def hang(owner_instance_id: str, run_id: str, pgid: int) -> None:
            pgid_file.write_text(str(pgid))
            time.sleep(300)

        subprocesses._record_owned_process = hang  # type: ignore[assignment]
        subprocesses.run_subprocess(
            [str(binary_a)], owner_instance_id="owner-dies-a", run_id="run-dies-a"
        )

    owner_pid = _fork_and_run(_owner_hangs_before_release)
    try:
        assert _wait_until(pgid_file.exists), "gate process was never spawned"
        gate_pgid = int(pgid_file.read_text())
        assert _group_alive(gate_pgid)
    finally:
        _kill_and_reap(owner_pid)

    assert _wait_until(lambda: not _group_alive(gate_pgid)), (
        "gate process outlived its owner instead of exiting on pipe EOF"
    )
    assert not sentinel_a.exists()

    # Variant B: the owner dies while `Popen()` itself is still returning --
    # the child is already forked, but Rush holds no handle to it yet.
    sentinel_b = tmp_path / "engine-started-b"
    binary_b = _sentinel_binary(tmp_path, sentinel_b)
    token = f"rush-gate-probe-{uuid.uuid4().hex}"

    def _owner_hangs_inside_popen() -> None:
        real_popen = subprocess.Popen

        def hanging_popen(*args, **kwargs):
            real_popen(*args, **kwargs)
            time.sleep(300)

        subprocesses.subprocess.Popen = hanging_popen  # type: ignore[assignment]
        subprocesses.run_subprocess(
            [str(binary_b), token],
            owner_instance_id="owner-dies-b",
            run_id="run-dies-b",
        )

    owner_pid_b = _fork_and_run(_owner_hangs_inside_popen)
    try:
        assert _wait_until(lambda: bool(_pattern_pids(token))), (
            "gate process was never spawned for the before-Popen-returns variant"
        )
    finally:
        _kill_and_reap(owner_pid_b)

    assert _wait_until(lambda: not _pattern_pids(token))
    assert not sentinel_b.exists()


def test_gate_process_interrupted_between_fork_and_popen_return_is_still_cleaned_up_and_never_left_unrecorded_and_unreleased(
    tmp_path: Path, monkeypatch, owned_data_root: Path
) -> None:
    sentinel = tmp_path / "engine-started"
    binary = _sentinel_binary(tmp_path, sentinel)
    token = f"rush-gate-interrupt-{uuid.uuid4().hex}"
    real_popen = subprocess.Popen

    interrupted: list[object] = []

    def interrupted_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        if interrupted:
            # `Popen` is patched globally; only the gate spawn is interrupted,
            # so later helpers (`pgrep`) can still start processes normally.
            return proc
        interrupted.append(proc)
        raise KeyboardInterrupt("interrupted between fork and Popen return")

    monkeypatch.setattr(subprocesses.subprocess, "Popen", interrupted_popen)

    with pytest.raises(KeyboardInterrupt):
        subprocesses.run_subprocess(
            [str(binary), token],
            owner_instance_id="owner-interrupted",
            run_id="run-interrupted",
        )
    assert _wait_until(lambda: not _pattern_pids(token)), (
        "the forked gate process was left running, unrecorded and unreleasable"
    )
    assert not sentinel.exists()
    assert not subprocesses._owner_procs_path("owner-interrupted").exists()


def test_a_fault_injected_descriptor_close_failure_during_cleanup_never_replaces_an_original_propagating_exception_and_still_attempts_every_remaining_cleanup_step(
    tmp_path: Path, monkeypatch, owned_data_root: Path
) -> None:
    sentinel = tmp_path / "engine-started"
    binary = _sentinel_binary(tmp_path, sentinel, sleep_seconds=30)
    token = f"rush-gate-cleanup-{uuid.uuid4().hex}"
    attempted_closes: list[int] = []
    reaped: list[object] = []
    real_reap = subprocesses._reap_gate_process

    def failing_close(fd: int) -> None:
        attempted_closes.append(fd)
        raise OSError(9, "fault-injected close failure")

    def observing_reap(proc) -> None:
        reaped.append(proc)
        real_reap(proc)

    def failing_record(owner_instance_id: str, run_id: str, pgid: int) -> None:
        raise RuntimeError("record write failed")

    monkeypatch.setattr(subprocesses, "_close_fd", failing_close)
    monkeypatch.setattr(subprocesses, "_reap_gate_process", observing_reap)
    monkeypatch.setattr(subprocesses, "_record_owned_process", failing_record)

    with pytest.raises(RuntimeError, match="record write failed"):
        subprocesses.run_subprocess(
            [str(binary), token],
            owner_instance_id="owner-cleanup",
            run_id="run-cleanup",
        )

    # Both descriptors were attempted even though the first close failed,
    # and the best-effort reap still ran -- no cleanup step was skipped.
    assert len(attempted_closes) == 2
    assert len(reaped) == 1
    assert _wait_until(lambda: not _pattern_pids(token))
    assert not sentinel.exists()

    for fd in attempted_closes:  # the fault injection left these really open
        with suppress(OSError):
            os.close(fd)


def test_owned_subprocess_call_persists_owner_instance_run_id_pgid_record_before_returning(
    tmp_path: Path, monkeypatch, owned_data_root: Path
) -> None:
    sentinel = tmp_path / "engine-started"
    binary = _sentinel_binary(tmp_path, sentinel)
    persisted: list[dict] = []
    real_record = subprocesses._record_owned_process

    def observing_record(owner_instance_id: str, run_id: str, pgid: int) -> None:
        real_record(owner_instance_id, run_id, pgid)
        persisted.extend(subprocesses.read_owned_process_records(owner_instance_id))

    monkeypatch.setattr(subprocesses, "_record_owned_process", observing_record)

    subprocesses.run_subprocess(
        [str(binary)], owner_instance_id="owner-record", run_id="run-record"
    )

    assert len(persisted) == 1
    record = persisted[0]
    assert record["owner_instance_id"] == "owner-record"
    assert record["run_id"] == "run-record"
    assert isinstance(record["pgid"], int) and record["pgid"] > 0


def test_unowned_subprocess_call_keeps_exact_current_kwargs_and_behavior_unchanged(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout="clean", stderr="")

    monkeypatch.setattr(common.subprocess, "run", fake_run)

    result = common.run_subprocess(
        ["fixture-engine", "--json"], cwd=tmp_path, timeout=7
    )

    assert calls == [
        (
            ["fixture-engine", "--json"],
            {
                "cwd": str(tmp_path),
                "timeout": 7,
                "stdin": subprocess.DEVNULL,
                "capture_output": True,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "env": None,
                "check": False,
                "shell": False,
            },
        )
    ]
    assert result.stdout == "clean"


def test_owner_instance_id_and_run_id_must_be_supplied_as_a_pair(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError):
        subprocesses.run_subprocess(["/bin/echo", "hi"], owner_instance_id="owner-only")
    with pytest.raises(ValueError):
        subprocesses.run_subprocess(["/bin/echo", "hi"], run_id="run-only")


def test_terminate_owned_group_stops_a_surviving_sigterm_ignoring_descendant_even_when_the_leader_already_exited(
    tmp_path: Path,
) -> None:
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
    try:
        assert _wait_until(lambda: pid_file.exists() and pid_file.read_text().strip())
        descendant = int(pid_file.read_text().strip())
        leader.wait(timeout=5)  # the group leader itself is already gone
        assert _group_alive(pgid)

        assert subprocesses.terminate_owned_group(pgid, timeout=1.0) is True

        assert not _group_alive(pgid)
        with pytest.raises(ProcessLookupError):
            os.kill(descendant, 0)
    finally:
        with suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, signal.SIGKILL)


def test_parent_death_during_blocking_owned_subprocess_call_is_reaped_by_recovery_not_left_running(
    tmp_path: Path, owned_data_root: Path
) -> None:
    sentinel = tmp_path / "engine-started"
    binary = _sentinel_binary(tmp_path, sentinel, sleep_seconds=300)
    owner_id = "owner-crashes-mid-scan"

    def _owner_runs_slow_engine_child() -> None:
        subprocesses.run_subprocess(
            [str(binary)],
            owner_instance_id=owner_id,
            run_id="run-crashes",
            timeout=600,
        )

    owner_pid = _fork_and_run(_owner_runs_slow_engine_child)
    try:
        assert _wait_until(
            lambda: bool(subprocesses.read_owned_process_records(owner_id))
        ), "owner never durably persisted its `.procs` record"
        record = subprocesses.read_owned_process_records(owner_id)[0]
        pgid = int(record["pgid"])
        assert _wait_until(sentinel.exists), "the owned engine child never started"
        assert _group_alive(pgid)
    finally:
        _kill_and_reap(owner_pid)

    # The owner-liveness lock is releasable the instant the owner dies, but
    # its engine child is still running and still free to mutate files --
    # recovery must positively confirm that child is gone first.
    assert _group_alive(pgid)

    outcome = subprocesses.reap_owner_processes(owner_id)

    assert outcome["reconcilable"] is True
    assert pgid in outcome["terminated"]
    assert outcome["termination_unconfirmed"] == []
    assert not _group_alive(pgid)
    assert subprocesses.read_owned_process_records(owner_id) == []


def test_engine_version_probe_on_a_cold_cache_carries_owner_instance_id_and_run_id_and_is_terminated_by_detach_the_same_as_the_main_command(
    tmp_path: Path, monkeypatch, owned_data_root: Path
) -> None:
    from rush.engines.base import Engine, EngineResult

    sentinel = tmp_path / "version-probe-started"
    probe_binary = _sentinel_binary(tmp_path, sentinel)

    class _ProbeEngine(Engine):
        name = "probe"
        binary = str(probe_binary)
        file_extensions = ()

        def run(
            self,
            path: Path,
            args: list[str],
            cwd: Path | None = None,
            *,
            owner_instance_id: str | None = None,
            run_id: str | None = None,
        ) -> EngineResult:  # pragma: no cover -- unused by this test
            return EngineResult(exit_code=0)

    records: list[dict] = []
    real_record = subprocesses._record_owned_process

    def observing_record(owner_instance_id: str, run_id: str, pgid: int) -> None:
        real_record(owner_instance_id, run_id, pgid)
        records.extend(subprocesses.read_owned_process_records(owner_instance_id))

    monkeypatch.setattr(subprocesses, "_record_owned_process", observing_record)
    Engine._cached_versions.pop(str(probe_binary), None)

    version = _ProbeEngine().version(
        owner_instance_id="owner-version", run_id="run-version"
    )

    assert version == "1.2.3"
    assert records, "the cold-cache `--version` probe ran unowned"
    assert records[0]["owner_instance_id"] == "owner-version"
    assert records[0]["run_id"] == "run-version"
    # Detach's force-exit reaches it through the identical recorded-pgid path
    # it uses for the main command.
    assert subprocesses.terminate_owned_group(int(records[0]["pgid"]), timeout=1.0)
    Engine._cached_versions.pop(str(probe_binary), None)


# ---------------------------------------------------------------------------
# P69-01.2j -- ownership propagation through the real dispatch chain
# ---------------------------------------------------------------------------


def test_invocation_context_carries_owner_instance_id_and_run_id_as_optional_fields(
    tmp_path: Path,
) -> None:
    from rush.invocation import resolve_invocation

    bare = resolve_invocation(
        {"operation_id": "lint", "path": str(tmp_path)},
        transport="cli",
        workspace_root=tmp_path,
    )
    assert bare.owner_instance_id == ""
    assert bare.run_id == ""

    owned = resolve_invocation(
        {
            "operation_id": "lint",
            "path": str(tmp_path),
            "owner_instance_id": "owner-ctx",
            "run_id": "run-ctx",
        },
        transport="cli",
        workspace_root=tmp_path,
    )
    assert owned.owner_instance_id == "owner-ctx"
    assert owned.run_id == "run-ctx"


def test_owner_instance_id_and_run_id_are_excluded_from_ordered_args_typed_args_and_never_reach_an_unopted_in_variadic_kwargs_handler(
    tmp_path: Path,
) -> None:
    from rush.invocation import resolve_invocation
    from rush.invocation.executor import (
        adapt_signature_at_registration,
        invocation_arguments,
    )

    typed = resolve_invocation(
        {
            "operation_id": "lint",
            "path": str(tmp_path),
            "typed_args": [("engine_args", ["--fix"])],
            "owner_instance_id": "owner-typed",
            "run_id": "run-typed",
        },
        transport="cli",
        workspace_root=tmp_path,
    )
    assert "owner_instance_id" not in typed.ordered_args
    assert "run_id" not in typed.ordered_args
    assert not any("owner-instance-id" in arg for arg in typed.ordered_args)
    assert "owner_instance_id" not in invocation_arguments(typed)
    assert "run_id" not in invocation_arguments(typed)

    # Legacy hyphen-normalized `ordered_args` must not smuggle them through
    # `_parse_ordered_args` either.
    legacy = resolve_invocation(
        {
            "operation_id": "lint",
            "path": str(tmp_path),
            "ordered_args": ["--owner-instance-id=leak", "--run-id=leak", "--fix"],
        },
        transport="cli",
        workspace_root=tmp_path,
    )
    legacy_args = invocation_arguments(legacy)
    assert "owner_instance_id" not in legacy_args
    assert "run_id" not in legacy_args
    assert legacy_args.get("fix") is True

    seen: dict[str, object] = {}

    def variadic_handler(*targets, **kwargs):
        seen.update(kwargs)
        return {"status": "ok"}

    adapter = adapt_signature_at_registration(variadic_handler, "lint")
    for context in (typed, legacy):
        _args, kwargs = adapter(context)
        variadic_handler(*_args, **kwargs)
        assert "owner_instance_id" not in seen
        assert "run_id" not in seen


def test_signature_adapter_binds_owner_instance_id_and_run_id_by_name_to_a_tools_own_call_parameters(
    tmp_path: Path,
) -> None:
    from rush.invocation import resolve_invocation
    from rush.invocation.executor import (
        adapt_signature_at_registration,
        invocation_arguments,
    )

    def handler(
        path: Path, engine_args=None, owner_instance_id=None, run_id=None
    ) -> dict:
        return {"status": "ok"}

    context = resolve_invocation(
        {
            "operation_id": "lint",
            "path": str(tmp_path),
            "owner_instance_id": "owner-bind",
            "run_id": "run-bind",
        },
        transport="cli",
        workspace_root=tmp_path,
    )
    _args, kwargs = adapt_signature_at_registration(handler, "lint")(context)

    assert kwargs["owner_instance_id"] == "owner-bind"
    assert kwargs["run_id"] == "run-bind"
    # Bound as structural context, never as a tool argument that happened to
    # share the name -- the argument path must not carry them at all.
    assert "owner_instance_id" not in invocation_arguments(context)
    assert "run_id" not in invocation_arguments(context)


def test_a_tool_whose_call_declares_neither_parameter_is_unaffected_by_the_new_whitelist_entries(
    tmp_path: Path,
) -> None:
    from rush.invocation import resolve_invocation
    from rush.invocation.executor import adapt_signature_at_registration

    def handler(path: Path, engine_args=None) -> dict:
        return {"status": "ok"}

    context = resolve_invocation(
        {
            "operation_id": "lint",
            "path": str(tmp_path),
            "owner_instance_id": "owner-unaffected",
            "run_id": "run-unaffected",
        },
        transport="cli",
        workspace_root=tmp_path,
    )
    _args, kwargs = adapt_signature_at_registration(handler, "lint")(context)

    assert set(kwargs) <= {"path", "engine_args"}
    assert handler(*_args, **kwargs) == {"status": "ok"}


def _lint_only_project(tmp_path: Path, monkeypatch):
    """Register a real project and return a real one-candidate (`lint`)
    `ScanPlan` for it, so the whole `execute_scan` dispatch chain runs for
    real without scheduling the entire catalog."""
    import rush.workflows.projects as projects_module

    data_root = tmp_path / "rush-projects"
    monkeypatch.setattr(projects_module, "default_data_root", lambda: data_root)

    from rush.workflows.project_run import plan_scan
    from rush.workflows.projects import register_project

    project_root = tmp_path / "proj"
    project_root.mkdir()
    (project_root / "a.py").write_text("x = 1\n")
    register_project(project_root, data_root=data_root)

    plan = plan_scan(project_root, data_root=data_root)
    lint_candidates = tuple(c for c in plan.candidates if c.candidate_id == "lint")
    assert lint_candidates, "the real catalog no longer plans a `lint` candidate"
    return dataclasses.replace(plan, candidates=lint_candidates)


def test_execute_scan_propagates_owner_and_run_id_through_execute_candidate_resolve_invocation_and_lint_tools_call_to_a_real_run_subprocess_call(
    tmp_path: Path, monkeypatch, owned_data_root: Path
) -> None:
    import rush.engines.ruff as ruff_engine
    from rush.workflows.project_run import execute_scan

    plan = _lint_only_project(tmp_path, monkeypatch)
    observed: list[dict] = []
    real_run_subprocess = ruff_engine.run_subprocess

    def spy(argv, **kwargs):
        observed.append(dict(kwargs))
        return real_run_subprocess(argv, **kwargs)

    monkeypatch.setattr(ruff_engine, "run_subprocess", spy)

    run = execute_scan(
        plan, run_id="run-propagated", owner_instance_id="owner-propagated"
    )

    assert run.run_state == "completed"
    assert observed, "the real engine dispatch never reached `run_subprocess`"
    assert observed[0]["owner_instance_id"] == "owner-propagated"
    assert observed[0]["run_id"] == "run-propagated"


def test_a_real_tui_dispatched_scan_produces_a_procs_record_attributed_to_the_scans_own_run_id(
    tmp_path: Path, monkeypatch, owned_data_root: Path
) -> None:
    from rush import tui
    from rush.workflows.project_run import execute_scan

    plan = _lint_only_project(tmp_path, monkeypatch)
    recorded: list[dict] = []
    real_record = subprocesses._record_owned_process

    def observing_record(owner_instance_id: str, run_id: str, pgid: int) -> None:
        real_record(owner_instance_id, run_id, pgid)
        recorded.extend(subprocesses.read_owned_process_records(owner_instance_id))

    monkeypatch.setattr(subprocesses, "_record_owned_process", observing_record)

    project = tui.ProjectState(name="proj", root=Path(plan.root))
    actions = dataclasses.replace(
        tui.default_scan_actions(),
        plan_scan=lambda _root: plan,
        execute_scan=execute_scan,
    )

    tui._start_scan_thread(project, actions)
    project.scan_thread.join(timeout=120)

    assert "scan error" not in project.last_message
    assert recorded, "a real TUI-dispatched scan produced no `.procs` record at all"
    assert {record["run_id"] for record in recorded} == {project.run_id}
    assert all(record["owner_instance_id"] for record in recorded)
