"""Subprocess execution and engine dispatching primitives.

Architecture §4.4 — enforces requirement C10 (engine discovery, never hard-fail).
"""

from __future__ import annotations

import contextvars
import inspect
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..permissions import build_execution_metadata, check_permissions
from ..safety.redactor import SecretRedactor
from ..tools.base import ToolResult
from .binaries import engine_on_path, resolve_binary
from .result_helpers import elapsed_ms, error_result, now_ms, skipped_result

if TYPE_CHECKING:
    from ..engines.base import Engine
    from ..permissions import ExecutionPermissions

MAX_SUBPROCESS_OUTPUT_CHARS = 256 * 1024


class SubprocessCancelled(Exception):
    """Raised by `run_subprocess` when `cancel_check()` returns True while
    its child is still running (P65-08). The owned child process group
    (POSIX) / process tree (Windows) is already terminated before this is
    raised -- callers never need to kill anything themselves."""

    def __init__(self, argv: list[str], pid: int) -> None:
        self.argv = argv
        self.pid = pid
        super().__init__(f"subprocess cancelled: {argv} (pid={pid})")


def _terminate_owned_group(proc: subprocess.Popen[str]) -> None:
    """Terminate only this owned child's own process group (POSIX, started
    with `start_new_session=True`) or process tree (Windows, started with
    `CREATE_NEW_PROCESS_GROUP`) -- never a foreign process, never orphaned."""
    if sys.platform == "win32":
        with suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                timeout=5,
                check=False,
            )
        return
    with suppress(ProcessLookupError, PermissionError):
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError, PermissionError):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)


OWNED_TERMINATION_TIMEOUT_SECONDS = 5.0
"""P69-01.2i: matches Detach's own force-exit deadline."""

_PROCS_RECORD_LOCK = threading.Lock()

# P69-01.2i bootstrap gate (POSIX). `/bin/sh` blocks on a `read` from an
# inherited pipe and only `exec`s the real engine command once the owner
# explicitly releases it. If the owner dies first, its copy of the write end
# closes with it, the `read` returns EOF, `&&` short-circuits, and the shell
# exits without ever running the real binary -- airtight, not a narrowed race.
_GATE_SHELL = "/bin/sh"
_GATE_SCRIPT = 'read -r _ <&"$RUSH_GATE_FD" && exec "$@"'
_GATE_RELEASE_PAYLOAD = b"\n"

_WINDOWS_GATE_GAP = (
    "owned-subprocess fencing on Windows needs the named-pipe gate "
    "(CreateNamedPipe / AnonymousPipeServerStream + AnonymousPipeClientStream) "
    "and CREATE_NEW_PROCESS_GROUP + GenerateConsoleCtrlEvent termination; "
    "only the POSIX path is implemented"
)


_OWNED_EXECUTION: contextvars.ContextVar[tuple[str, str] | None] = (
    contextvars.ContextVar("rush_owned_execution", default=None)
)


@contextmanager
def owned_execution_scope(
    owner_instance_id: str | None, run_id: str | None
) -> Iterator[None]:
    """Make an owner identity ambient for one engine dispatch.

    P69-01.2j: an engine's own `run()` receives and forwards the pair
    explicitly, but the *nested* children it spawns -- most importantly
    `Engine.version()`'s cold-cache `--version` probe, which several adapters
    fire from inside `normalize()` -- have no parameter to receive it through.
    A slow `--version` child on an empty cache is exactly as unowned and
    exactly as reachable by Detach's force-exit deadline as the main command,
    so `run_engine` scopes the identity across the whole dispatch and
    `run_subprocess` adopts it whenever no explicit pair was passed.

    Context-local, so a concurrent dispatch on another thread never inherits
    this one's identity.
    """
    if owner_instance_id is None or run_id is None:
        yield
        return
    token = _OWNED_EXECUTION.set((owner_instance_id, run_id))
    try:
        yield
    finally:
        _OWNED_EXECUTION.reset(token)


def _owner_procs_path(owner_instance_id: str, *, data_root: Path | None = None) -> Path:
    """`<data_root>/owners/<owner_instance_id>.procs` -- the durable, cross-
    process record of every process group this owner still owns. Sits beside
    the owner-liveness lock (`<owner_instance_id>.lock`) deliberately: a dead
    owner's lock says its *process* exited, this file says which of its
    *children* still need reaping."""
    if data_root is None:
        from rush.setup.provision import default_data_root

        data_root = default_data_root()
    owners_dir = Path(data_root) / "owners"
    owners_dir.mkdir(parents=True, exist_ok=True)
    return owners_dir / f"{owner_instance_id}.procs"


def read_owned_process_records(
    owner_instance_id: str, *, data_root: Path | None = None
) -> list[dict[str, Any]]:
    """Every still-owned process-group record for this owner, readable from
    any process (recovery never has the original `Popen` handle)."""
    path = _owner_procs_path(owner_instance_id, data_root=data_root)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        with suppress(json.JSONDecodeError):
            records.append(json.loads(line))
    return records


def _write_owned_process_records(
    owner_instance_id: str,
    records: list[dict[str, Any]],
    *,
    data_root: Path | None = None,
) -> None:
    path = _owner_procs_path(owner_instance_id, data_root=data_root)
    if not records:
        with suppress(FileNotFoundError):
            path.unlink()
        return
    payload = "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _record_owned_process(owner_instance_id: str, run_id: str, pgid: int) -> None:
    """Durably persist one owned process group. Always called *before* the
    bootstrap gate is released, so the real engine binary can never be
    running while its group is unrecorded."""
    with _PROCS_RECORD_LOCK:
        path = _owner_procs_path(owner_instance_id)
        record = {
            "owner_instance_id": owner_instance_id,
            "run_id": run_id,
            "pgid": pgid,
        }
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def _clear_owned_process_record(
    owner_instance_id: str, pgid: int, *, data_root: Path | None = None
) -> None:
    with _PROCS_RECORD_LOCK:
        remaining = [
            record
            for record in read_owned_process_records(
                owner_instance_id, data_root=data_root
            )
            if record.get("pgid") != pgid
        ]
        _write_owned_process_records(owner_instance_id, remaining, data_root=data_root)


def _close_fd(fd: int) -> None:
    """Indirection so cleanup-path descriptor failures are fault-injectable."""
    os.close(fd)


def _reap_gate_process(proc: subprocess.Popen[str]) -> None:
    """Best-effort reap of a gate process that was never released."""
    _terminate_owned_group(proc)
    with suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=OWNED_TERMINATION_TIMEOUT_SECONDS)


def _finish_gate_cleanup(
    fds: tuple[int | None, ...],
    unreleased_proc: subprocess.Popen[str] | None,
    pending: BaseException | None,
) -> None:
    """Run every gate-teardown step, each guarded on its own.

    A cleanup failure never replaces the exception already in flight -- it
    attaches to it as context. It becomes the propagating error only on an
    otherwise-successful exit with nothing else in flight.
    """
    cleanup_errors: list[BaseException] = []
    for fd in fds:
        if fd is None:
            continue
        try:
            _close_fd(fd)
        except BaseException as close_error:  # noqa: BLE001 -- collected, not raised
            cleanup_errors.append(close_error)
    if unreleased_proc is not None:
        try:
            _reap_gate_process(unreleased_proc)
        except BaseException as reap_error:  # noqa: BLE001 -- collected, not raised
            cleanup_errors.append(reap_error)
    if not cleanup_errors:
        return
    if pending is None:
        raise cleanup_errors[0]
    for cleanup_error in cleanup_errors:
        with suppress(AttributeError):
            pending.add_note(  # type: ignore[attr-defined]
                f"owned-subprocess gate cleanup failure: {cleanup_error!r}"
            )


def _launch_gated_process(
    exec_argv: list[str],
    *,
    popen_kwargs: dict[str, Any],
    env: dict[str, str] | None,
    owner_instance_id: str,
    run_id: str,
) -> subprocess.Popen[str]:
    """Spawn the bootstrap gate in place of the real engine command, persist
    the `.procs` record, then release the gate -- in exactly that order.

    Cleanup discipline: `Popen()` forks before its constructor returns, so an
    interruption in between can leave a live, unrecorded gate process. Every
    descriptor and the reap are guarded independently and all of them are
    attempted, but a cleanup failure never replaces whatever exception is
    already in flight (a failed record write is itself an original exception);
    it only propagates on an otherwise-successful exit.
    """
    if sys.platform == "win32":  # pragma: no cover -- POSIX-only environment
        raise NotImplementedError(_WINDOWS_GATE_GAP)

    read_fd: int | None = None
    write_fd: int | None = None
    proc: subprocess.Popen[str] | None = None
    released = False
    pending: BaseException | None = None
    try:
        read_fd, write_fd = os.pipe()
        gate_env = dict(os.environ if env is None else env)
        gate_env["RUSH_GATE_FD"] = str(read_fd)
        proc = subprocess.Popen(
            [_GATE_SHELL, "-c", _GATE_SCRIPT, "sh", *exec_argv],
            **{**popen_kwargs, "env": gate_env, "pass_fds": (read_fd,)},
        )
        # `start_new_session=True` makes the gate shell its own process-group
        # leader, and its pid survives its own later `exec`.
        _record_owned_process(owner_instance_id, run_id, proc.pid)
        os.write(write_fd, _GATE_RELEASE_PAYLOAD)
        released = True
        return proc
    except BaseException as error:
        pending = error
        raise
    finally:
        _finish_gate_cleanup(
            (write_fd, read_fd),
            proc if not released else None,
            pending,
        )


def _signal_group(pgid: int, sig: int) -> None:
    with suppress(ProcessLookupError, PermissionError):
        os.killpg(pgid, sig)


def _group_has_members(pgid: int) -> bool:
    """True while *any* member of the group is still around -- not just the
    leader, which may have exited long before its descendants."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_group_gone(pgid: int, timeout: float, poll_interval: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _group_has_members(pgid):
            return True
        time.sleep(poll_interval)
    return not _group_has_members(pgid)


def terminate_owned_group(
    pgid: int,
    *,
    timeout: float = OWNED_TERMINATION_TIMEOUT_SECONDS,
    poll_interval: float = 0.05,
) -> bool:
    """Bounded SIGTERM-then-SIGKILL of one recorded process group, reachable
    from any process (recovery, Detach's force-exit) that has the pgid.

    Returns True only when a confirmation poll positively observes every
    group member gone. A False return means termination is unconfirmed: the
    caller must keep the `.procs` record and must not let recovery reconcile.
    """
    if sys.platform == "win32":  # pragma: no cover -- POSIX-only environment
        return False
    _signal_group(pgid, signal.SIGTERM)
    if _wait_group_gone(pgid, timeout, poll_interval):
        return True
    _signal_group(pgid, signal.SIGKILL)
    return _wait_group_gone(pgid, timeout, poll_interval)


def reap_owner_processes(
    owner_instance_id: str,
    *,
    data_root: Path | None = None,
    timeout: float = OWNED_TERMINATION_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Recovery's reap-and-reconcile entry point for a dead owner.

    Terminates every recorded group and drops only the records whose
    termination was positively confirmed. A surviving group keeps its record,
    flagged `termination_unconfirmed`, for the next recovery attempt to retry
    against the same pgid -- and `reconcilable` stays False so recovery never
    reconciles the owner's rows while its children may still be mutating
    files.
    """
    terminated: list[int] = []
    unconfirmed: list[int] = []
    retained: list[dict[str, Any]] = []
    for record in read_owned_process_records(owner_instance_id, data_root=data_root):
        pgid = record.get("pgid")
        if not isinstance(pgid, int):
            continue
        if terminate_owned_group(pgid, timeout=timeout):
            terminated.append(pgid)
        else:
            unconfirmed.append(pgid)
            retained.append({**record, "termination_unconfirmed": True})
    with _PROCS_RECORD_LOCK:
        _write_owned_process_records(owner_instance_id, retained, data_root=data_root)
    return {
        "owner_instance_id": owner_instance_id,
        "terminated": terminated,
        "termination_unconfirmed": unconfirmed,
        "reconcilable": not unconfirmed,
    }


def _bounded_redacted_output(output: str) -> str:
    """Redact secrets and cap child output before adapters consume it."""
    redacted = SecretRedactor.redact_text(output)
    common = sys.modules.get("rush.tools.common")
    max_chars = (
        getattr(common, "MAX_SUBPROCESS_OUTPUT_CHARS", MAX_SUBPROCESS_OUTPUT_CHARS)
        if common is not None
        else MAX_SUBPROCESS_OUTPUT_CHARS
    )
    if len(redacted) <= max_chars:
        return redacted
    return redacted[:max_chars] + "[TRUNCATED]"


def run_subprocess(
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: float = 120,
    env: dict[str, str] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    poll_interval: float = 0.05,
    owner_instance_id: str | None = None,
    run_id: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a list-only local child process without inheriting stdin.

    The helper deliberately has no shell mode. Engines receive a bounded argv,
    fixed optional working directory, and DEVNULL stdin so they cannot consume
    the stdio MCP transport. Timeout exceptions remain observable by the shared
    `run_engine` error mapping.

    `cancel_check` (P65-08) is optional and defaults to `None`, which keeps
    every existing caller's exact prior `subprocess.run`-blocking behavior
    unchanged. When given, the child runs under `Popen` in its own owned
    process group/tree instead, polled every `poll_interval` seconds; if
    `cancel_check()` ever returns `True` before the child exits, only that
    owned group/tree is terminated and `SubprocessCancelled` is raised.

    `owner_instance_id`/`run_id` (P69-01.2i) are supplied together or not at
    all. Supplying them makes the call *owned*: the child runs behind the
    bootstrap gate, in its own process group, with a durable `.procs` record
    another process can reap it by. An unowned blocking call keeps today's
    exact `subprocess.run`-based kwargs and behavior, unchanged.
    """
    if not argv or any(not isinstance(arg, str) for arg in argv):
        raise ValueError("argv must be a non-empty list of strings")
    if (owner_instance_id is None) != (run_id is None):
        raise ValueError(
            "owner_instance_id and run_id must be supplied together, or not at all"
        )
    if owner_instance_id is None:
        ambient = _OWNED_EXECUTION.get()
        if ambient is not None:
            owner_instance_id, run_id = ambient
    exec_argv = _resolve_exec_argv(argv)

    if cancel_check is None and owner_instance_id is None:
        return _run_subprocess_blocking(
            exec_argv, argv, cwd=cwd, timeout=timeout, env=env
        )
    return _run_subprocess_cancellable(
        exec_argv,
        argv,
        cwd=cwd,
        timeout=timeout,
        env=env,
        cancel_check=cancel_check,
        poll_interval=poll_interval,
        owner_instance_id=owner_instance_id,
        run_id=run_id,
    )


def _resolve_exec_argv(argv: list[str]) -> list[str]:
    common = sys.modules.get("rush.tools.common")
    resolver = (
        getattr(common, "resolve_binary", resolve_binary)
        if common is not None
        else resolve_binary
    )
    resolved_cmd = resolver(argv[0]) or argv[0]
    if os.name != "nt":
        return [resolved_cmd, *argv[1:]]
    which_cmd = shutil.which(resolved_cmd) or resolved_cmd
    if which_cmd.lower().endswith((".cmd", ".bat")):
        return ["cmd.exe", "/c", which_cmd, *argv[1:]]
    return [which_cmd, *argv[1:]]


def _run_subprocess_blocking(
    exec_argv: list[str],
    argv: list[str],
    *,
    cwd: Path | None,
    timeout: float,
    env: dict[str, str] | None,
) -> subprocess.CompletedProcess[str]:
    """The original, unchanged `subprocess.run`-blocking path -- every
    caller that never passes `cancel_check` gets this exact behavior."""
    try:
        result = subprocess.run(
            exec_argv,
            cwd=str(cwd) if cwd is not None else None,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=False,
            shell=False,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            argv, 127, stdout="", stderr=f"{argv[0]}: command not found"
        )

    return subprocess.CompletedProcess(
        result.args,
        result.returncode,
        stdout=_bounded_redacted_output(result.stdout),
        stderr=_bounded_redacted_output(result.stderr),
    )


def _popen_kwargs_for_cancellable(
    *, cwd: Path | None, env: dict[str, str] | None
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "cwd": str(cwd) if cwd is not None else None,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "env": env,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    return kwargs


def _run_subprocess_cancellable(
    exec_argv: list[str],
    argv: list[str],
    *,
    cwd: Path | None,
    timeout: float,
    env: dict[str, str] | None,
    cancel_check: Callable[[], bool] | None,
    poll_interval: float,
    owner_instance_id: str | None = None,
    run_id: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """P65-08: `Popen`-based poll loop used when a caller opts in with
    `cancel_check`, and (P69-01.2i) for every *owned* call, cancellable or
    blocking. Terminates only this owned child's own process group/tree,
    never a foreign process.

    An owned call launches behind the bootstrap gate and keeps its durable
    `.procs` record for exactly as long as the child can still be running.
    """
    popen_kwargs = _popen_kwargs_for_cancellable(cwd=cwd, env=env)
    if owner_instance_id is not None and run_id is not None:
        proc = _launch_gated_process(
            exec_argv,
            popen_kwargs=popen_kwargs,
            env=env,
            owner_instance_id=owner_instance_id,
            run_id=run_id,
        )
    else:
        try:
            proc = subprocess.Popen(exec_argv, **popen_kwargs)
        except FileNotFoundError:
            return subprocess.CompletedProcess(
                argv, 127, stdout="", stderr=f"{argv[0]}: command not found"
            )

    try:
        start = time.monotonic()
        stdout = ""
        stderr = ""
        while True:
            try:
                stdout, stderr = proc.communicate(timeout=poll_interval)
                break
            except subprocess.TimeoutExpired:
                if cancel_check is not None and cancel_check():
                    _terminate_owned_group(proc)
                    with suppress(subprocess.TimeoutExpired):
                        stdout, stderr = proc.communicate(timeout=5)
                    raise SubprocessCancelled(exec_argv, proc.pid) from None
                if time.monotonic() - start >= timeout:
                    _terminate_owned_group(proc)
                    with suppress(subprocess.TimeoutExpired):
                        stdout, stderr = proc.communicate(timeout=5)
                    raise subprocess.TimeoutExpired(
                        exec_argv, timeout, output=stdout, stderr=stderr
                    ) from None
    finally:
        if owner_instance_id is not None:
            with suppress(OSError):
                _clear_owned_process_record(owner_instance_id, proc.pid)

    return subprocess.CompletedProcess(
        exec_argv,
        proc.returncode,
        stdout=_bounded_redacted_output(stdout or ""),
        stderr=_bounded_redacted_output(stderr or ""),
    )


def _engine_run_ownership(
    engine: Engine, owner_instance_id: str | None, run_id: str | None
) -> dict[str, str]:
    """The ownership pair as `Engine.run()` kwargs, or `{}`.

    P69-01.2j: every in-tree adapter takes the pair, but `Engine` is a public
    ABC -- an out-of-tree subclass written against the older signature must
    keep dispatching, not turn into an "engine crashed" result. It is still
    fenced: `owned_execution_scope` (which wraps this call) is what
    `run_subprocess` reads when no explicit pair reaches it.
    """
    if owner_instance_id is None or run_id is None:
        return {}
    try:
        params = inspect.signature(engine.run).parameters
    except (TypeError, ValueError):  # pragma: no cover -- exotic callables
        return {}
    if not {"owner_instance_id", "run_id"} <= set(params):
        return {}
    return {"owner_instance_id": owner_instance_id, "run_id": run_id}


def _install_hint(engine_name: str) -> str:
    """Return a user-facing install hint without installing anything."""
    return {
        "ruff": "pip install ruff",
        "pytest": "pip install pytest",
        "pip-audit": "pip install pip-audit",
        "eslint": "npm install -g eslint",
        "prettier": "npm install -g prettier",
        "vitest": "npm install -D vitest (in your project)",
        "npm-audit": "ships with npm",
    }.get(engine_name, "see engine docs")


def _remap_paths(payload: Any, staged_root: Path, original_root: Path) -> None:
    from ..engines.staging import remap_paths

    remap_paths(payload, staged_root, original_root)


def _staged_invocation(
    engine: Engine, path: Path, cwd: Path | None, extra_args: list[str]
) -> tuple[Any, Path, Path | None, list[str]]:
    """P69-03e/g/h: resolve what this engine is actually pointed at.

    When a scan attempt has staged its bounded inventory, a path-based engine
    runs against that immutable copy instead of the live working tree: both the
    `path`/`cwd` it receives and any explicit file-path argument a caller built
    itself are redirected, and everything staged under the redirected path is
    recorded as genuinely consumed. Repository-state-dependent engines are
    excluded entirely -- they need real `.git` history/index/branches a file
    copy cannot provide -- and so is every call made outside a staged attempt,
    which keeps today's exact behavior byte for byte.
    """
    from ..engines.staging import REPOSITORY_STATE_ENGINES, active_staging

    staging = active_staging()
    if staging is None or engine.name in REPOSITORY_STATE_ENGINES:
        return None, path, cwd, extra_args
    run_path = staging.stage_path(path) or path
    run_cwd = staging.stage_path(cwd) if cwd is not None else staging.staged_root
    staging.record_consumption(run_path)
    return staging, run_path, run_cwd, [staging.substitute_arg(a) for a in extra_args]


def _merge_provenance_metadata(
    tool_res: ToolResult,
    provenance: Any,
    engine: Engine,
    required_permissions: ExecutionPermissions | None,
    permissions: ExecutionPermissions | None,
) -> None:
    """P69-03h/T033: attach a repository-state engine's provenance digest (if
    any) and ensure `execution` metadata exists on the normalized result.
    Mutates `tool_res["metadata"]` in place -- extracted from `run_engine`
    verbatim to keep it under the enforced C901<=10 threshold; no behavior
    change.
    """
    metadata = tool_res.get("metadata")
    if metadata is None:
        metadata = {}
        tool_res["metadata"] = metadata
    if provenance is not None:
        metadata["repository_state_provenance"] = provenance
    if "execution" not in metadata:
        metadata["execution"] = build_execution_metadata(
            "executed",
            requested=required_permissions,
            granted=permissions,
            producer=engine.name,
            producer_version=tool_res.get("engine_version"),
        )


def run_engine(
    engine: Engine,
    path: Path,
    args: list[str] | None = None,
    *,
    cwd: Path | None = None,
    tool_name: str | None = None,
    timeout: int = 120,
    permissions: ExecutionPermissions | None = None,
    required_permissions: ExecutionPermissions | None = None,
    owner_instance_id: str | None = None,
    run_id: str | None = None,
) -> ToolResult:
    """Run an engine and always return a canonical result.

    Status semantics: missing engines or ungranted permissions are `skipped`;
    engine/process failures are `error`; valid engine findings are normalized
    as `warn` or `fail` by the adapter. No child output is written to Rush stdout.

    P69-01.2j: `owner_instance_id`/`run_id` are forwarded into `Engine.run()`
    and into `Engine.normalize()` (whose own cold-cache `self.version()`
    probe spawns a second, equally reapable child), so the identity does not
    stop here -- it reaches each engine's own `run_subprocess()` call.
    """
    common = sys.modules.get("rush.tools.common")
    _engine_on_path = (
        getattr(common, "engine_on_path", engine_on_path)
        if common is not None
        else engine_on_path
    )
    _skipped = (
        getattr(common, "skipped_result", skipped_result)
        if common is not None
        else skipped_result
    )
    _error = (
        getattr(common, "error_result", error_result)
        if common is not None
        else error_result
    )
    _now = getattr(common, "now_ms", now_ms) if common is not None else now_ms
    _elapsed = (
        getattr(common, "elapsed_ms", elapsed_ms) if common is not None else elapsed_ms
    )

    tool_name = tool_name or engine.name
    extra_args = list(args or [])

    # Check execution permissions before PATH probe or process spawning
    ok, missing = check_permissions(required_permissions, permissions)
    if not ok:
        missing_str = ", ".join(missing)
        return _skipped(
            tool_name,
            engine.name,
            f"requires permission: {missing_str}",
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_permissions,
                    granted=permissions,
                    producer=engine.name,
                )
            },
        )

    if not _engine_on_path(engine.binary):
        return _skipped(
            tool_name,
            engine.name,
            f"{engine.binary} not on PATH (install: {_install_hint(engine.name)})",
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_permissions,
                    granted=permissions,
                    producer=engine.name,
                )
            },
        )

    staging, run_path, run_cwd, extra_args = _staged_invocation(
        engine, path, cwd, extra_args
    )

    start = _now()
    try:
        with owned_execution_scope(owner_instance_id, run_id):
            result = engine.run(
                run_path,
                extra_args,
                cwd=run_cwd,
                **_engine_run_ownership(engine, owner_instance_id, run_id),
            )
    except subprocess.TimeoutExpired:
        return _error(
            tool_name,
            engine.name,
            f"timed out after {timeout}s",
            duration_ms=_elapsed(start),
            terminal_reason="timeout",
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_permissions,
                    granted=permissions,
                    producer=engine.name,
                )
            },
        )
    except FileNotFoundError:
        return _skipped(
            tool_name,
            engine.name,
            f"{engine.binary} disappeared from PATH mid-run",
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_permissions,
                    granted=permissions,
                    producer=engine.name,
                )
            },
        )
    except Exception as error:  # noqa: BLE001 - C10 requires structured engine errors
        return _error(
            tool_name,
            engine.name,
            f"engine crashed: {error!r}",
            duration_ms=_elapsed(start),
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_permissions,
                    granted=permissions,
                    producer=engine.name,
                )
            },
        )

    result.setdefault("duration_ms", _elapsed(start))
    # P69-03g: output-side remapping runs on *decoded* data at both real decode
    # points -- whatever this engine already parsed inside `run()` (ruff,
    # eslint, cspell, ...) and, after `normalize()`, whatever it parses there
    # instead (hadolint/actionlint's still-JSON `stdout`, tsc's regex over raw
    # text) plus any field the adapter constructs itself post-run
    # (`wasm_tools`'s `"file"`). Never a raw-text substitution.
    if staging is not None:
        _remap_paths(result, staging.staged_root, staging.original_root)
    # `normalize()` keeps its exact prior signature; several adapters fire a
    # cold-cache `self.version()` probe from inside it, and this scope is what
    # makes that nested child owned and reapable too.
    # P69-03h: a repository-state-dependent engine (git-guard/diff-cover/
    # undercover) stashes its own real-evidence digest on `result` itself --
    # carry it forward onto the returned `ToolResult`'s metadata so
    # `project_run.py` can fold it into the run's consumption identity.
    provenance = result.get("provenance")  # type: ignore[typeddict-item]
    with owned_execution_scope(owner_instance_id, run_id):
        tool_res = engine.normalize(result, run_path, tool_name)
    if staging is not None:
        _remap_paths(tool_res, staging.staged_root, staging.original_root)
    _merge_provenance_metadata(
        tool_res, provenance, engine, required_permissions, permissions
    )
    return tool_res


__all__ = [
    "MAX_SUBPROCESS_OUTPUT_CHARS",
    "OWNED_TERMINATION_TIMEOUT_SECONDS",
    "SubprocessCancelled",
    "_bounded_redacted_output",
    "_install_hint",
    "owned_execution_scope",
    "read_owned_process_records",
    "reap_owner_processes",
    "run_engine",
    "run_subprocess",
    "terminate_owned_group",
]
