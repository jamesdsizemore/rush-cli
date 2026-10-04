"""Every `rush` module imports on Windows, where POSIX-only stdlib modules
(`fcntl`, `termios`, ...) do not exist. A module-level import of one breaks
Rush itself there (and `tests/conftest.py`), not only one feature.

Simulated on this host in a fresh interpreter: stdlib and third-party
dependencies load first under the real platform (their own platform
branches are not Rush's), then the POSIX-only modules are made unimportable
and `sys.platform` reads `win32` while every `rush` module is imported."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import ClassVar

import pytest
from _process_children import spawn_child
from test_subprocess_contract import _wait_until

POSIX_ONLY = ("fcntl", "termios", "tty", "pwd", "grp", "resource")

_LIST_RUSH_MODULES = textwrap.dedent(
    """
    import importlib, json, pkgutil, sys
    import rush
    names = [info.name for info in pkgutil.walk_packages(rush.__path__, "rush.")]
    for name in names:
        importlib.import_module(name)
    deps = sorted(
        m for m in sys.modules
        if m != "rush" and not m.startswith("rush.") and m != "__main__"
    )
    print(json.dumps({"rush": names, "deps": deps}))
    """
)

_IMPORT_AS_WINDOWS = textwrap.dedent(
    """
    import importlib, json, sys
    spec = json.loads(sys.stdin.read())
    for name in spec["deps"]:
        if name.split(".")[0] not in spec["posix_only"]:
            try:
                importlib.import_module(name)
            except Exception:
                pass
    for name in spec["posix_only"]:
        sys.modules[name] = None  # `import name` now raises ImportError
    sys.platform = "win32"
    failures = []
    for name in ["rush", *spec["rush"]]:
        try:
            importlib.import_module(name)
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    print("\\n".join(failures))
    sys.exit(1 if failures else 0)
    """
)


def _python(code: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def test_every_rush_module_imports_without_posix_only_modules() -> None:
    listed = _python(_LIST_RUSH_MODULES)
    assert listed.returncode == 0, listed.stderr
    spec = json.loads(listed.stdout.splitlines()[-1])
    assert len(spec["rush"]) > 100
    spec["posix_only"] = list(POSIX_ONLY)

    proc = _python(_IMPORT_AS_WINDOWS, json.dumps(spec))

    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_probe_detects_a_module_level_posix_import() -> None:
    """The simulation is live: a module-level `import fcntl` fails under it."""
    spec = {"rush": [], "deps": [], "posix_only": list(POSIX_ONLY)}
    probe = _IMPORT_AS_WINDOWS.replace(
        'for name in ["rush", *spec["rush"]]:', 'for name in ["fcntl", "termios"]:'
    )

    proc = _python(probe, json.dumps(spec))

    assert proc.returncode == 1
    assert "fcntl: ModuleNotFoundError" in proc.stdout
    assert "termios: ModuleNotFoundError" in proc.stdout


@pytest.fixture
def windows_kernel():
    """Native APIs only; non-Windows hosts cannot supply this acceptance lane."""
    assert sys.platform == "win32", "native acceptance requires Windows"
    import ctypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.OpenMutexW.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p)
    kernel.OpenMutexW.restype = ctypes.c_void_p
    kernel.OpenJobObjectW.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p)
    kernel.OpenJobObjectW.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel.ReleaseMutex.argtypes = (ctypes.c_void_p,)
    kernel.TerminateJobObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    kernel.GetHandleInformation.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
    )
    return kernel


def _windows_lock_child(owner: str, root: str, ready: str) -> None:
    from rush.dashboard.state import OwnerLock
    from rush.runtime.filesystem import atomic_write_bytes

    lock = OwnerLock(owner, data_root=Path(root))
    atomic_write_bytes(Path(root), Path(ready).name, str(os.getpid()).encode())
    time.sleep(300)
    lock.release()


def _windows_tree_script(path: Path, pids: Path) -> None:
    path.write_text(
        "import json, os, subprocess, sys, time\nfrom pathlib import Path\n"
        "leaf = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        f"temporary = Path({str(pids.with_suffix('.tmp'))!r})\n"
        "temporary.write_text(json.dumps([os.getpid(), leaf.pid]), encoding='utf-8')\n"
        f"temporary.replace({str(pids)!r})\n"
        "time.sleep(300)\n",
        encoding="utf-8",
    )


def _windows_tree_owner_child(
    root: str, owner: str, script: str, ready: str, release: str, before_release: bool
) -> None:
    import rush.tools.common  # noqa: F401 -- initializes the shared runtime
    from rush.dashboard.state import OwnerLock
    from rush.runtime import subprocesses
    from rush.runtime.filesystem import atomic_write_bytes
    from rush.setup import provision

    provision.default_data_root = lambda: Path(root)
    lock = OwnerLock(owner, data_root=Path(root))
    real_record = subprocesses._record_owned_process

    def record(*args, **kwargs):
        real_record(*args, **kwargs)
        if before_release:
            atomic_write_bytes(Path(root), Path(ready).name, str(args[2]).encode())
            assert _wait_until(Path(release).exists)

    subprocesses._record_owned_process = record
    if not before_release:
        atomic_write_bytes(Path(root), Path(ready).name, b"owner-ready")
        assert _wait_until(Path(release).exists)
    proc = subprocesses._launch_gated_process_windows(
        [sys.executable, script],
        popen_kwargs={"stdin": subprocess.DEVNULL},
        env=None,
        owner_instance_id=owner,
        run_id="run-native",
    )
    atomic_write_bytes(Path(root), Path(ready).name, str(proc.pid).encode())
    time.sleep(300)
    lock.release()


def _windows_recover_child(root: str, owner: str, result: str) -> None:
    import ctypes

    import rush.tools.common  # noqa: F401 -- initializes the shared runtime
    from rush.runtime import subprocesses

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    record = subprocesses.read_owned_process_records(owner, data_root=Path(root))[0]
    ids = [record["pgid"], *json.loads((Path(root) / "pids.json").read_text())]
    handles = []
    try:
        for pid in ids:
            handle = kernel.OpenProcess(0x00100000, False, pid)
            assert handle
            handles.append(handle)
        outcome = subprocesses.reap_owner_processes(owner, data_root=Path(root))
        if not outcome["reconcilable"]:
            assert outcome["terminated"] == []
            assert outcome["termination_unconfirmed"] == [record["pgid"]]
            assert subprocesses.read_owned_process_records(
                owner, data_root=Path(root)
            ) == [{**record, "termination_unconfirmed": True}]
        assert all(kernel.WaitForSingleObject(handle, 5000) == 0 for handle in handles)
        if not outcome["reconcilable"]:
            # Job termination is asynchronous. Retry only after native
            # process handles prove the first attempt changed kernel state.
            outcome = subprocesses.reap_owner_processes(owner, data_root=Path(root))
        assert outcome["reconcilable"] is True
        Path(result).write_text(json.dumps(outcome), encoding="utf-8")
    finally:
        for handle in handles:
            kernel.CloseHandle(handle)


@pytest.fixture
def windows_tree(tmp_path, monkeypatch, windows_kernel):
    """One actual fenced wrapper, engine and descendant, with owned cleanup."""
    import rush.tools.common  # noqa: F401 -- initializes the shared runtime
    from rush.runtime import subprocesses
    from rush.setup import provision

    owner = f"native-{uuid.uuid4().hex}"
    script, pids = tmp_path / "tree.py", tmp_path / "pids.json"
    _windows_tree_script(script, pids)
    monkeypatch.setattr(provision, "default_data_root", lambda: tmp_path)
    held = {"job": None}
    real_create = subprocesses._create_kill_on_close_job

    def create(name):
        held["job"] = real_create(name)
        return held["job"]

    monkeypatch.setattr(subprocesses, "_create_kill_on_close_job", create)
    proc = subprocesses._launch_gated_process_windows(
        [sys.executable, str(script)],
        popen_kwargs={"stdin": subprocess.DEVNULL},
        env=None,
        owner_instance_id=owner,
        run_id="run-native",
    )
    handles = []
    try:
        import ctypes

        flags = ctypes.c_uint32()
        assert windows_kernel.GetHandleInformation(held["job"], ctypes.byref(flags))
        assert flags.value & 1 == 0
        assert _wait_until(pids.exists)
        ids = [proc.pid, *json.loads(pids.read_text(encoding="utf-8"))]
        for pid in ids:
            handle = windows_kernel.OpenProcess(0x00100000, False, pid)
            assert handle, f"cannot retain process {pid} for native termination proof"
            handles.append(handle)
        records = subprocesses.read_owned_process_records(owner, data_root=tmp_path)
        assert len(records) == 1
        assert records[0]["pgid"] == proc.pid
        assert records[0]["windows_job_assigned"] is True
        yield owner, proc, held, handles, records[0]
    finally:
        if held["job"] is not None:
            windows_kernel.TerminateJobObject(held["job"], 1)
            windows_kernel.CloseHandle(held["job"])
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        for handle in handles:
            windows_kernel.CloseHandle(handle)


@pytest.mark.windows_only
def test_windows_owner_lock_acquire_release_via_named_mutex(tmp_path, windows_kernel):
    import ctypes

    from rush.dashboard.state import OwnerLock, OwnerLockError, claim_dead_owner

    owner = f"native-{uuid.uuid4().hex}"
    lock = OwnerLock(owner, data_root=tmp_path)
    handle = lock._windows_mutex_handle
    try:
        with claim_dead_owner(owner, data_root=tmp_path) as claimed:
            assert claimed is False
        with pytest.raises(OwnerLockError):
            OwnerLock(owner, data_root=tmp_path)
    finally:
        lock.release()
    assert not lock._windows_thread.is_alive()
    flags = ctypes.c_uint32()
    assert windows_kernel.GetHandleInformation(handle, ctypes.byref(flags)) == 0
    with claim_dead_owner(owner, data_root=tmp_path) as claimed:
        assert claimed is True


@pytest.mark.windows_only
def test_windows_owner_lock_abandoned_mutex_detected_as_dead_owner(
    tmp_path, windows_kernel
):
    from rush.dashboard.state import (
        _windows_mutex_name,
        claim_dead_owner,
        observe_owner,
    )

    owner = f"native-{uuid.uuid4().hex}"
    ready = tmp_path / "ready"
    proc = spawn_child(
        __name__, "_windows_lock_child", [owner, str(tmp_path), str(ready)]
    )
    retained = None
    try:
        assert _wait_until(ready.exists)
        retained = windows_kernel.OpenMutexW(
            0x00100001, False, _windows_mutex_name(owner)
        )
        assert retained
        assert windows_kernel.WaitForSingleObject(retained, 0) == 0x102
        proc.kill()
        proc.wait(timeout=5)
        assert windows_kernel.WaitForSingleObject(retained, 0) == 0x80
        assert windows_kernel.ReleaseMutex(retained)
        assert observe_owner(owner, tmp_path) == "dead"

        def claim_from_another_thread():
            with claim_dead_owner(owner, data_root=tmp_path) as claimed:
                return claimed

        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(claim_from_another_thread).result(timeout=5) is True
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        if retained is not None:
            windows_kernel.CloseHandle(retained)


@pytest.mark.windows_only
def test_windows_gate_wrapper_blocks_engine_launch_until_release(
    tmp_path, monkeypatch, windows_kernel
):
    import ctypes

    import rush.tools.common  # noqa: F401 -- initializes the shared runtime
    from rush.runtime import subprocesses
    from rush.setup import provision

    monkeypatch.setattr(provision, "default_data_root", lambda: tmp_path)
    sentinel = tmp_path / "engine-started"
    owner = f"native-{uuid.uuid4().hex}"
    real_record = subprocesses._record_owned_process
    real_create = subprocesses._create_kill_on_close_job
    real_popen = subprocess.Popen
    observed = {}

    def create(name):
        observed["job"] = real_create(name)
        return observed["job"]

    def popen(argv, **kwargs):
        assert kwargs["close_fds"] is True
        inherited = kwargs["startupinfo"].lpAttributeList["handle_list"]
        assert len(inherited) == 1
        observed["gate_read_handle"] = inherited[0]
        return real_popen(argv, **kwargs)

    def record(*args, **kwargs):
        assert not sentinel.exists()
        real_record(*args, **kwargs)
        stored = subprocesses.read_owned_process_records(owner, data_root=tmp_path)
        assert stored[0]["pgid"] == args[2]
        assert stored[0]["windows_job_assigned"] is True
        assert stored[0]["windows_creation_time"] is not None
        flags = ctypes.c_uint32()
        assert windows_kernel.GetHandleInformation(observed["job"], ctypes.byref(flags))
        assert flags.value & 1 == 0
        assert not sentinel.exists()

    monkeypatch.setattr(subprocesses, "_record_owned_process", record)
    monkeypatch.setattr(subprocesses, "_create_kill_on_close_job", create)
    monkeypatch.setattr(subprocess, "Popen", popen)
    try:
        result = subprocesses.run_subprocess(
            [sys.executable, "-c", f"open({str(sentinel)!r}, 'w').write('started')"],
            owner_instance_id=owner,
            run_id="run-native",
        )
    finally:
        if observed.get("job"):
            windows_kernel.CloseHandle(observed["job"])
    assert result.returncode == 0
    assert sentinel.read_text(encoding="utf-8") == "started"
    assert observed["gate_read_handle"]


@pytest.mark.windows_only
def test_windows_gate_wrapper_never_launches_if_owner_dies_before_release(
    tmp_path, windows_kernel
):
    import msvcrt

    from rush.runtime import subprocesses

    # EOF on the real inherited gate, without a job masking a leaked writer.
    read_fd, write_fd = os.pipe()
    gate = None
    try:
        os.set_inheritable(read_fd, True)
        read_handle = msvcrt.get_osfhandle(read_fd)
        assert os.get_inheritable(write_fd) is False
        startup = subprocess.STARTUPINFO()
        startup.lpAttributeList = {"handle_list": [read_handle]}
        marker = tmp_path / "eof-engine-started"
        gate = subprocess.Popen(
            [
                sys.executable,
                "-c",
                subprocesses._WINDOWS_GATE_SCRIPT,
                str(read_handle),
                sys.executable,
                "-c",
                f"open({str(marker)!r}, 'w').write('started')",
            ],
            close_fds=True,
            startupinfo=startup,
        )
    finally:
        os.close(read_fd)
        os.close(write_fd)
    try:
        assert gate.wait(timeout=5) == 1
        assert not marker.exists()
    finally:
        if gate.poll() is None:
            gate.kill()
            gate.wait(timeout=5)

    owner = f"native-{uuid.uuid4().hex}"
    script, pids = tmp_path / "tree.py", tmp_path / "pids.json"
    ready, release = tmp_path / "ready", tmp_path / "release"
    _windows_tree_script(script, pids)
    proc = spawn_child(
        __name__,
        "_windows_tree_owner_child",
        [str(tmp_path), owner, str(script), str(ready), str(release), True],
    )
    wrapper = None
    try:
        assert _wait_until(ready.exists)
        wrapper = windows_kernel.OpenProcess(
            0x00100000, False, int(ready.read_text(encoding="utf-8"))
        )
        assert wrapper
        assert not pids.exists()
        proc.kill()
        proc.wait(timeout=5)
        assert windows_kernel.WaitForSingleObject(wrapper, 5000) == 0
        assert not pids.exists()
        assert not release.exists()
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        if wrapper is not None:
            windows_kernel.CloseHandle(wrapper)


@pytest.mark.windows_only
def test_windows_job_object_kills_entire_process_tree_on_close(
    windows_tree, windows_kernel
):
    _owner, proc, held, handles, _record = windows_tree
    assert all(
        windows_kernel.WaitForSingleObject(handle, 0) == 0x102 for handle in handles
    )
    assert windows_kernel.CloseHandle(held["job"])
    held["job"] = None
    assert all(
        windows_kernel.WaitForSingleObject(handle, 5000) == 0 for handle in handles
    )
    proc.wait(timeout=5)


@pytest.mark.windows_only
def test_windows_job_object_survives_parent_job_nesting(tmp_path, windows_kernel):
    import rush.tools.common  # noqa: F401 -- initializes the shared runtime
    from rush.runtime import subprocesses

    owner = f"native-{uuid.uuid4().hex}"
    script, pids = tmp_path / "tree.py", tmp_path / "pids.json"
    ready, release = tmp_path / "ready", tmp_path / "release"
    _windows_tree_script(script, pids)
    outer = subprocesses._create_kill_on_close_job(
        f"Local\\RushTest-{uuid.uuid4().hex}"
    )
    assert outer
    proc = spawn_child(
        __name__,
        "_windows_tree_owner_child",
        [str(tmp_path), owner, str(script), str(ready), str(release), False],
    )
    try:
        assert _wait_until(ready.exists)
        assert subprocesses._assign_process_to_job(outer, proc.pid)
        release.write_text("launch", encoding="utf-8")
        assert _wait_until(pids.exists)
        records = subprocesses.read_owned_process_records(owner, data_root=tmp_path)
        assert records[0]["windows_job_assigned"] is True
        assert records[0]["run_id"] == "run-native"
        inner = windows_kernel.OpenJobObjectW(
            0x0004, False, records[0]["windows_job_name"]
        )
        assert inner
        try:
            assert subprocesses._windows_job_has_zero_processes(inner) is False
        finally:
            windows_kernel.CloseHandle(inner)
    finally:
        windows_kernel.TerminateJobObject(outer, 1)
        windows_kernel.CloseHandle(outer)
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)


@pytest.mark.windows_only
def test_windows_recovery_confirms_zero_active_processes_before_clearing_records(
    tmp_path, windows_tree, windows_kernel, monkeypatch
):
    from rush.runtime import subprocesses

    owner, _proc, _held, handles, record = windows_tree
    uncertain = {**record, "windows_job_name": f"Local\\Missing-{uuid.uuid4().hex}"}
    subprocesses._write_owned_process_records(owner, [uncertain], data_root=tmp_path)
    outcome = subprocesses.reap_owner_processes(owner, data_root=tmp_path)
    assert outcome["reconcilable"] is False
    assert outcome["terminated"] == []
    assert outcome["termination_unconfirmed"] == [record["pgid"]]
    assert subprocesses.read_owned_process_records(owner, data_root=tmp_path) == [
        {**uncertain, "termination_unconfirmed": True}
    ]
    assert all(
        windows_kernel.WaitForSingleObject(handle, 0) == 0x102 for handle in handles
    )

    queries = []
    real_query = subprocesses._windows_job_has_zero_processes

    def query(job_handle):
        result = real_query(job_handle)
        queries.append(result)
        return result

    monkeypatch.setattr(subprocesses, "_windows_job_has_zero_processes", query)
    subprocesses._write_owned_process_records(owner, [record], data_root=tmp_path)
    outcome = subprocesses.reap_owner_processes(owner, data_root=tmp_path)
    if not outcome["reconcilable"]:
        assert outcome["terminated"] == []
        assert outcome["termination_unconfirmed"] == [record["pgid"]]
        assert subprocesses.read_owned_process_records(owner, data_root=tmp_path) == [
            {**record, "termination_unconfirmed": True}
        ]
    assert all(
        windows_kernel.WaitForSingleObject(handle, 5000) == 0 for handle in handles
    )
    if not outcome["reconcilable"]:
        outcome = subprocesses.reap_owner_processes(owner, data_root=tmp_path)
    assert outcome["reconcilable"] is True
    assert outcome["terminated"] == [record["pgid"]]
    assert outcome["termination_unconfirmed"] == []
    assert all(
        windows_kernel.WaitForSingleObject(handle, 5000) == 0 for handle in handles
    )
    assert subprocesses.read_owned_process_records(owner, data_root=tmp_path) == []
    assert queries and queries[-1] is True


@pytest.mark.windows_only
def test_windows_pid_reuse_does_not_falsely_confirm_termination(
    tmp_path, windows_tree, windows_kernel
):
    from rush.runtime import subprocesses

    owner, proc, _held, handles, record = windows_tree
    old = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    try:
        old_creation = subprocesses._windows_process_creation_time(old.pid)
        assert old_creation is not None
    finally:
        old.kill()
        old.wait(timeout=5)
    current_creation = subprocesses._windows_process_creation_time(proc.pid)
    assert current_creation is not None and current_creation != old_creation
    # Persist an older process identity whose numeric PID now names a live
    # unrelated process. Creation times come from actual native processes.
    stale = {
        **record,
        "windows_job_name": f"Local\\Missing-{uuid.uuid4().hex}",
        "windows_creation_time": old_creation,
    }
    subprocesses._write_owned_process_records(owner, [stale], data_root=tmp_path)
    outcome = subprocesses.reap_owner_processes(owner, data_root=tmp_path)
    assert outcome["reconcilable"] is True
    assert outcome["terminated"] == [proc.pid]
    assert outcome["termination_unconfirmed"] == []
    assert subprocesses.read_owned_process_records(owner, data_root=tmp_path) == []
    assert all(
        windows_kernel.WaitForSingleObject(handle, 0) == 0x102 for handle in handles
    )


@pytest.mark.windows_only
def test_windows_query_denial_keeps_owner_record(
    tmp_path, windows_tree, windows_kernel
):
    import ctypes

    from rush.runtime import subprocesses

    owner, proc, _held, handles, record = windows_tree
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_uint32),
    )
    advapi.SetKernelObjectSecurity.argtypes = (
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
    )
    for query in (advapi.GetKernelObjectSecurity, advapi.GetTokenInformation):
        query.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
        )
    windows_kernel.GetCurrentThread.restype = ctypes.c_void_p
    windows_kernel.GetCurrentProcess.restype = ctypes.c_void_p
    advapi.OpenThreadToken.argtypes = (
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p),
    )
    advapi.OpenProcessToken.argtypes = (
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
    )
    advapi.LookupPrivilegeValueW.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_void_p,
    )
    advapi.AdjustTokenPrivileges.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
    )
    windows_kernel.LocalFree.argtypes = (ctypes.c_void_p,)
    descriptor = ctypes.c_void_p()
    assert advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        "D:P", 1, ctypes.byref(descriptor), None
    )
    process, original_security = None, None
    token = ctypes.c_void_p()
    privilege_changed = False
    previous = (ctypes.c_uint32 * 4)()
    try:
        process = windows_kernel.OpenProcess(0x00060000, False, proc.pid)
        assert process  # READ_CONTROL | WRITE_DAC; retain DACL restoration access.
        size = ctypes.c_uint32()
        assert not advapi.GetKernelObjectSecurity(
            process, 4, None, 0, ctypes.byref(size)
        )
        assert ctypes.get_last_error() == 122  # ERROR_INSUFFICIENT_BUFFER
        saved_security = ctypes.create_string_buffer(size.value)
        assert advapi.GetKernelObjectSecurity(
            process, 4, saved_security, size.value, ctypes.byref(size)
        )
        original_security = saved_security
        assert advapi.SetKernelObjectSecurity(process, 4, descriptor)
        # CI's enabled SeDebugPrivilege bypasses even an empty process DACL.
        if not advapi.OpenThreadToken(
            windows_kernel.GetCurrentThread(), 0x28, True, ctypes.byref(token)
        ):
            assert ctypes.get_last_error() == 1008  # ERROR_NO_TOKEN
            assert advapi.OpenProcessToken(
                windows_kernel.GetCurrentProcess(), 0x28, ctypes.byref(token)
            )
        debug_luid = (ctypes.c_uint32 * 2)()
        assert advapi.LookupPrivilegeValueW(None, "SeDebugPrivilege", debug_luid)
        size = ctypes.c_uint32()
        assert not advapi.GetTokenInformation(token, 3, None, 0, ctypes.byref(size))
        assert ctypes.get_last_error() == 122
        privileges = ctypes.create_string_buffer(size.value)
        assert advapi.GetTokenInformation(
            token, 3, privileges, size.value, ctypes.byref(size)
        )
        # TOKEN_PRIVILEGES: DWORD count, then LUID_AND_ATTRIBUTES (3 DWORDs).
        words = (ctypes.c_uint32 * (size.value // 4)).from_buffer(privileges)
        debug_enabled = any(
            words[index] == debug_luid[0]
            and words[index + 1] == debug_luid[1]
            and bool(words[index + 2] & 2)
            for index in range(1, 1 + 3 * words[0], 3)
        )
        if debug_enabled:
            disabled = (ctypes.c_uint32 * 4)(1, debug_luid[0], debug_luid[1], 0)
            returned = ctypes.c_uint32()
            assert advapi.AdjustTokenPrivileges(
                token,
                False,
                disabled,
                ctypes.sizeof(previous),
                previous,
                ctypes.byref(returned),
            )
            privilege_changed = True
            assert ctypes.get_last_error() == 0

        probe = windows_kernel.OpenProcess(0x1000, False, proc.pid)
        try:
            assert not probe
            assert ctypes.get_last_error() == 5  # ERROR_ACCESS_DENIED
        finally:
            if probe:
                windows_kernel.CloseHandle(probe)

        denied = {**record, "windows_job_name": f"Local\\Missing-{uuid.uuid4().hex}"}
        subprocesses._write_owned_process_records(owner, [denied], data_root=tmp_path)
        outcome = subprocesses.reap_owner_processes(owner, data_root=tmp_path)
        assert outcome["reconcilable"] is False
        assert outcome["terminated"] == []
        assert outcome["termination_unconfirmed"] == [proc.pid]
        assert subprocesses.read_owned_process_records(owner, data_root=tmp_path) == [
            {**denied, "termination_unconfirmed": True}
        ]
        assert all(
            windows_kernel.WaitForSingleObject(handle, 0) == 0x102 for handle in handles
        )
    finally:
        try:
            if privilege_changed:
                assert advapi.AdjustTokenPrivileges(
                    token, False, previous, 0, None, None
                )
                assert ctypes.get_last_error() == 0
        finally:
            try:
                if original_security is not None:
                    assert advapi.SetKernelObjectSecurity(process, 4, original_security)
            finally:
                if token.value:
                    windows_kernel.CloseHandle(token)
                if process:
                    windows_kernel.CloseHandle(process)
                windows_kernel.LocalFree(descriptor)


@pytest.mark.windows_only
def test_windows_restart_after_crash_reopens_and_verifies_job_object(
    tmp_path, windows_kernel
):
    import rush.tools.common  # noqa: F401 -- initializes the shared runtime
    from rush.runtime import subprocesses

    owner = f"native-{uuid.uuid4().hex}"
    script, pids = tmp_path / "tree.py", tmp_path / "pids.json"
    ready, release, result = (
        tmp_path / "ready",
        tmp_path / "release",
        tmp_path / "result",
    )
    _windows_tree_script(script, pids)
    proc = spawn_child(
        __name__,
        "_windows_tree_owner_child",
        [str(tmp_path), owner, str(script), str(ready), str(release), False],
    )
    job, handles, recovery = None, [], None
    try:
        assert _wait_until(ready.exists)
        release.write_text("launch", encoding="utf-8")
        assert _wait_until(pids.exists)
        record = subprocesses.read_owned_process_records(owner, data_root=tmp_path)[0]
        job = windows_kernel.OpenJobObjectW(0x000C, False, record["windows_job_name"])
        assert job
        for pid in [record["pgid"], *json.loads(pids.read_text(encoding="utf-8"))]:
            handle = windows_kernel.OpenProcess(0x00100000, False, pid)
            assert handle
            handles.append(handle)
        proc.kill()
        proc.wait(timeout=5)
        assert all(
            windows_kernel.WaitForSingleObject(handle, 0) == 0x102 for handle in handles
        )
        recovery = spawn_child(
            __name__, "_windows_recover_child", [str(tmp_path), owner, str(result)]
        )
        assert recovery.wait(timeout=5) == 0
        outcome = json.loads(result.read_text(encoding="utf-8"))
        assert outcome["reconcilable"] is True
        assert outcome["terminated"] == [record["pgid"]]
        assert outcome["termination_unconfirmed"] == []
        assert all(
            windows_kernel.WaitForSingleObject(handle, 5000) == 0 for handle in handles
        )
        assert subprocesses.read_owned_process_records(owner, data_root=tmp_path) == []
    finally:
        if recovery is not None and recovery.poll() is None:
            recovery.kill()
            recovery.wait(timeout=5)
        if job is not None:
            windows_kernel.TerminateJobObject(job, 1)
            windows_kernel.CloseHandle(job)
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        for handle in handles:
            windows_kernel.CloseHandle(handle)


def _windows_console_child(result: str) -> None:
    import ctypes

    from rush.dashboard import terminal_input

    class Key(ctypes.Structure):
        _fields_ = [
            ("down", ctypes.c_int),
            ("repeat", ctypes.c_uint16),
            ("virtual", ctypes.c_uint16),
            ("scan", ctypes.c_uint16),
            ("char", ctypes.c_wchar),
            ("control", ctypes.c_uint32),
        ]

    class Event(ctypes.Union):
        _fields_: ClassVar = [("key", Key), ("padding", ctypes.c_byte * 16)]

    class Record(ctypes.Structure):
        _fields_ = [("kind", ctypes.c_uint16), ("event", Event)]

    kernel = terminal_input._windows_kernel32()
    kernel.FreeConsole()
    assert kernel.AllocConsole(), "native child could not allocate a real console"
    kernel.WriteConsoleInputW.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(Record),
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
    )
    input_handle, output_handle = kernel.GetStdHandle(-10), kernel.GetStdHandle(-11)

    def modes():
        values = []
        for handle in (input_handle, output_handle):
            value = ctypes.c_uint32()
            assert kernel.GetConsoleMode(handle, ctypes.byref(value))
            values.append(value.value)
        return values

    def keys(reader):
        actual = []
        for virtual, scan, char, control in (
            (0x71, 0x3C, "\0", 0),
            (0x72, 0x3D, "\0", 0),
            (0x09, 0x0F, "\t", 0x10),
        ):
            records = (Record * 2)()
            for index, down in enumerate((1, 0)):
                records[index].kind = 1
                records[index].event.key = Key(down, 1, virtual, scan, char, control)
            written = ctypes.c_uint32()
            assert kernel.WriteConsoleInputW(
                input_handle, records, 2, ctypes.byref(written)
            )
            assert written.value == 2
            actual.append(reader.read_key(1.0))
        assert actual == ["f2", "f3", "shift_tab"]
        return actual

    original = modes()
    transcript = []
    try:
        # Exercise actual native extended-key fallback, not injected msvcrt.
        assert kernel.SetConsoleMode(input_handle, original[0] & ~0x0200)
        transcript.append(keys(terminal_input.WindowsKeyReader()))
        assert kernel.SetConsoleMode(input_handle, original[0])
        for error in (None, ValueError, KeyboardInterrupt):
            try:
                with terminal_input.raw_terminal():
                    assert terminal_input._WINDOWS_VT_INPUT == [True]
                    transcript.append(keys(terminal_input.WindowsKeyReader()))
                    if error is not None:
                        raise error
            except (ValueError, KeyboardInterrupt):
                if error is None:
                    raise
            assert modes() == original
            assert terminal_input._WINDOWS_VT_INPUT == [False]
        Path(result).write_text(json.dumps(transcript), encoding="utf-8")
    finally:
        kernel.SetConsoleMode(input_handle, original[0])
        kernel.SetConsoleMode(output_handle, original[1])
        kernel.FreeConsole()


@pytest.mark.windows_only
def test_windows_f2_f3_shift_tab_decode_to_named_actions_not_escape(
    tmp_path, windows_kernel
):
    result = tmp_path / "console.json"
    proc = spawn_child(__name__, "_windows_console_child", [str(result)])
    try:
        assert proc.wait(timeout=10) == 0
        assert (
            json.loads(result.read_text(encoding="utf-8"))
            == [["f2", "f3", "shift_tab"]] * 4
        )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def _seed_native_artifact_actions(root: Path, project_id: str) -> dict:
    """Actual captured bytes for installed UI actions, including broken snapshots."""
    import hashlib
    from contextlib import chdir

    from rush.workflows.project_run import _capture_artifact_snapshots

    run_id, attempt_id = "run-native-artifacts", "1"
    payloads = {
        **{
            f"native-report-{n:02d}.txt": f"CAPTURED REPORT {n:02d}\n".encode()
            for n in range(21)
        },
        "native-unknown.ctrace": b"NATIVE UNKNOWN TRACE\n",
        "native-binary.bin": b"\x00\x01\xffNATIVE\x00\x1b[2J",
        "native-long.txt": b"NATIVE PAGE ONE\n"
        + b"A" * (1048576 - len(b"NATIVE PAGE ONE\n"))
        + b"NATIVE PAGE TWO\n",
        "native-missing.txt": b"MISSING CAPTURED BYTES\n",
        "native-corrupt.txt": b"ORIGINAL CORRUPT SNAPSHOT\n",
    }
    scheduled, entries = [], {}
    for index, (rel, data) in enumerate(payloads.items()):
        tool_id = f"native-artifact-{index:02d}"
        (root / rel).write_bytes(data)
        with chdir(root):
            snapshots = _capture_artifact_snapshots(
                root, run_id, attempt_id, tool_id, {"artifacts": [rel]}
            )
        snapshot = snapshots[rel]
        assert snapshot["size"] == len(data)
        assert snapshot["sha256"] == hashlib.sha256(data).hexdigest()
        if rel.endswith(".ctrace"):
            snapshot["media_type"] = "application/x-native-trace"
        scheduled.append(
            {
                "candidate_id": tool_id,
                "category": "native-custom-evidence",
                "outcome": "executed",
                "child": {"status": "ok", "artifacts": [rel]},
                "artifact_snapshots": snapshots,
            }
        )
        entries[rel] = {**snapshot, "bytes": data, "tool_id": tool_id}
    attempt = root / ".rush" / "runs" / run_id / "attempts" / attempt_id
    attempt.mkdir(parents=True, exist_ok=True)
    identity = {"run_id": run_id, "attempt_id": attempt_id, "project_id": project_id}
    (attempt / "attempt.json").write_text(
        json.dumps(
            {
                **identity,
                "attempt_generation": 1,
                "started_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )
    (attempt / "manifest.json").write_text(
        json.dumps(
            {
                **identity,
                "schema_version": 1,
                "run_state": "completed",
                "scheduled": scheduled,
                "aggregate": {"findings": []},
            }
        )
    )
    (root / "native-report-00.txt").write_bytes(b"CHANGED LIVE SENTINEL\n")
    (root / "native-report-01.txt").unlink()
    (root / entries["native-missing.txt"]["immutable_path"]).unlink()
    corrupt = root / entries["native-corrupt.txt"]["immutable_path"]
    original = corrupt.read_bytes()
    corrupt.write_bytes(b"X" + original[1:])
    return entries


def _seed_native_memory_actions(root: Path, project_id: str) -> dict:
    import hashlib

    from rush.memory.maintenance import run_maintenance_cycle
    from rush.memory.store import MemoryArtifact, OwnerScope, TypedArtifactStore
    from rush.permissions import ExecutionPermissions
    from rush.tools.memory import MemoryTool

    store = TypedArtifactStore(root)
    owner = OwnerScope("project", project_id)
    entries = {}
    fixtures = [
        (f"native-page-{n:02d}", f"NATIVEPAGE {n:02d}", "native-pages")
        for n in range(22)
    ] + [
        ("native-lone", "NATIVELONE", "native-lone-source"),
        ("native-primary", "NATIVECORROBORATED", "native-primary-source"),
        ("native-secondary", "NATIVECORROBORATED", "native-secondary-source"),
        ("native-related", "NATIVERELATED", "native-related-source"),
        (
            "native-long",
            "NATIVELONG EARLYMARKER "
            + "A" * 230
            + " MIDDLEMARKER "
            + "B" * 250
            + " ENDMARKER",
            "native-long-source",
        ),
    ]
    fixtures.extend(
        (
            f"native-related-{index:02d}",
            f"NATIVERELATED {index:02d}",
            f"native-related-source-{index:02d}",
        )
        for index in range(1, 6)
    )
    for index, (identifier, note, source) in enumerate(fixtures):
        entries[identifier] = store.write(
            MemoryArtifact(
                id=identifier,
                family="memory",
                subject="domain_knowledge",
                trust_tier="DERIVED",
                content={"note": note},
                source=source,
                created_at=time.time() + index,
                owner_scope=owner,
            ),
            receipt_operation_id=f"native-create-{identifier}",
        )
    first = entries["native-lone"]
    for identifier in [
        "native-related",
        *[f"native-related-{index:02d}" for index in range(1, 6)],
    ]:
        second = entries[identifier]
        linked = MemoryTool().run(
            root,
            operation="link",
            request={
                "source_id": first.id,
                "source_version": first.artifact_version,
                "target_id": second.id,
                "target_version": second.artifact_version,
                "kind": "depends_on",
            },
            permissions=ExecutionPermissions(cache_write=True),
        )
        assert linked["raw"]["code"] == "OK"
    for index in range(6):
        expanded = MemoryTool().run(
            root,
            operation="expand",
            request={"id": first.id, "version": first.artifact_version},
            session_allowlist=[first.source],
            permissions=ExecutionPermissions(cache_write=True),
            invocation_id=f"native-use-{index:02d}",
            project_id=project_id,
        )
        assert expanded["raw"]["code"] == "OK"
    from rush.token_economy.telemetry import read_artifact_expansion_receipts_readonly

    receipts = read_artifact_expansion_receipts_readonly(
        root, first.id, first.artifact_version
    )
    assert {receipt["id"] for receipt in receipts} == {
        f"native-use-{index:02d}" for index in range(6)
    }
    stale_source = root / "native-missing-source.py"
    stale_source.write_text("def symbol():\n    return 1\n", encoding="utf-8")
    stale_source_hash = hashlib.sha256(stale_source.read_bytes()).hexdigest()
    maintenance = (
        (
            "native-stale",
            "architectural_decision",
            time.time(),
            "native-missing-source.py::symbol",
        ),
        ("native-expiry", "failure", time.time() - 20 * 86400, None),
        ("native-skill", "skill_pattern", time.time(), None),
    )
    for identifier, subject, created_at, symbol in maintenance:
        entries[identifier] = store.write(
            MemoryArtifact(
                id=identifier,
                family="memory",
                subject=subject,
                trust_tier="DERIVED",
                content={"note": identifier},
                source=identifier,
                created_at=created_at,
                owner_scope=owner,
                symbol_ref=symbol,
                content_hash=stale_source_hash if symbol else None,
            ),
            receipt_operation_id=f"native-create-{identifier}",
        )
    # Canonical sweep computes corroboration counts; fixtures never fabricate them.
    sweep = run_maintenance_cycle(
        "promotion_sweep",
        project_root=root,
        owner_scope=owner,
        candidate_ids=[item[0] for item in maintenance],
    )
    assert sweep.processed == 3 and sweep.changed == 3 and sweep.errors == ()
    stale_source.unlink()
    return entries


def _exercise_native_memory_actions(root: Path, entries: dict, press) -> dict:
    from rush.memory.store import TypedArtifactStore

    store = TypedArtifactStore(root)
    observations = {}
    press(b"\x1bOR", "[1-8] go")
    press(b"4", "owner=project:")
    press(b"]", "page 2/2")
    press(b"[", "page 1/2")
    press(b" ", ">[x]")
    press(b" ", ">[ ]")
    skill_filter = press(b"S", "page 1/1")
    assert "subject=skill_pattern" in skill_filter
    skill = store.get_current("native-skill")
    assert skill.artifact_version == entries[skill.id].artifact_version + 1
    assert skill.subject == "skill_pattern"
    skill_detail = press(b"x", f"{skill.id} v{skill.artifact_version}")
    assert '"note": "native-skill"' in skill_detail
    observations["subject_skill"] = {"filter": skill_filter, "detail": skill_detail}
    press(b"-", "subject=skill_pattern")
    for subject in (
        "active_context",
        "episodic",
        "preference",
        "failure",
        "architectural_decision",
        "domain_knowledge",
    ):
        press(b"S", f"subject={subject}")
    press(b"o", "owner project id>")
    press(b"\t", "owner user id>")
    press(b"\t", "owner session id>")
    press(b"\t", "owner agent id>")
    press(b"\t\r", "owner scope = project:")
    press(b"f", "> trust:")
    press(b"DERIVED\tnative-lone-source\tfresh\tfalse\t", "> owner:")
    owner = entries["native-lone"].owner_scope
    press(f"{owner.kind}:{owner.id}".encode() + b"\r", "native-lone")
    press(b"f", "> trust:")
    # Clear each reviewed filter using its exact previously supplied value.
    for value in (
        "DERIVED",
        "native-lone-source",
        "fresh",
        "false",
        f"{owner.kind}:{owner.id}",
    ):
        press(b"\x7f" * len(value) + b"\t", "[tab] field")
    press(b"\r", "page 1/2")
    press(b"/NATIVELONE\r", "native-lone")
    import re

    expanded = press(b"x", "Content:")
    assert "NATIVELONE" in expanded
    assert "Relationships:" in expanded
    observations["expansion"] = expanded
    # Every returned real row remains reachable; unique footer bounds reject stale frames.
    required = {
        "native-related",
        *[f"native-related-{index:02d}" for index in range(1, 6)],
        "native-create-native-lone",
        *[f"native-use-{index:02d}" for index in range(6)],
    }
    seen = set()
    detail_frames = []
    while required - seen:
        seen.update(marker for marker in required if marker in expanded)
        detail_frames.append(expanded)
        if required <= seen:
            break
        bounds = re.search(r"rows (\d+)-(\d+)/(\d+)", expanded)
        assert bounds is not None, expanded
        start, end, total = map(int, bounds.groups())
        visible = end - start + 1
        next_start = min(start + visible, total - visible + 1)
        assert next_start > start, (required - seen, expanded)
        expanded = press(b"]", f"rows {next_start}-")
    observations["all_relationships_and_receipts"] = detail_frames
    bounds = re.search(r"rows (\d+)-(\d+)/(\d+)", expanded)
    assert bounds is not None
    start, end, _total = map(int, bounds.groups())
    if start > 1:
        previous_start = max(1, start - (end - start + 1))
        returned = press(b"[", f"rows {previous_start}-")
        assert "rows " in returned
        observations["detail_scroll_previous"] = returned
    press(b"-", "native-lone")
    press(b"p", "promote preview:")
    press(b"n", "promote cancelled")
    assert store.get_current("native-lone").artifact_version == 1
    press(b"p", "promote preview:")
    press(b"y", "promotion denied:")
    assert store.get_current("native-lone").trust_tier == "DERIVED"
    press(b"/NATIVECORROBORATED\r", "native-primary")
    press(b"p", "promote preview:")
    observations["promotion"] = press(b"y", "promoted to STATED")
    # Promotion creates canonical reviewed candidate; original evidence retained.
    promoted = [store.get_current(row["id"]) for row in store.list_artifact_refs()]
    assert any(
        row.trust_tier == "STATED" and row.content == {"note": "NATIVECORROBORATED"}
        for row in promoted
    )
    press(b"/NATIVELONE\r", "native-lone")
    press(b"e", "edit note>")
    press(b"NATIVEEDITED\r", "edit preview:")
    press(b"n", "edit cancelled")
    assert store.get_current("native-lone").content == {"note": "NATIVELONE"}
    press(b"e", "edit note>")
    press(b"NATIVEEDITED\r", "edit preview:")
    store.update_content("native-lone", {"note": "NATIVEEXTERNAL"}, expected_version=1)
    observations["conflict"] = press(b"y", "edit conflict on native-lone")
    assert store.get_current("native-lone").content == {"note": "NATIVEEXTERNAL"}
    press(b"r", "refreshed native-lone to v2")
    press(b"\r", "edit preview:")
    press(b"y", "edit applied")
    assert store.get_current("native-lone").artifact_version == 3
    assert store.get_current("native-lone").content == {"note": "NATIVEEDITED"}
    press(b"/NATIVEEDITED\r", "native-lone")
    press(b"a", "archive preview:")
    press(b"n", "archive cancelled")
    assert store.get_current("native-lone").archived_at is None
    press(b"a", "archive preview:")
    press(b"y", "archived native-lone")
    assert store.get_current("native-lone").archived_at is not None
    press(b"f\t\t\ttrue\r", "native-lone")
    press(b"a", "restore preview:")
    press(b"y", "restored native-lone")
    assert store.get_current("native-lone").archived_at is None
    press(b"f\t\t\t" + b"\x7f" * 4 + b"\r", "native-lone")
    press(b"d", "preview: 1 record(s) selected")
    press(b"n", "delete cancelled")
    assert store.get_current("native-lone") is not None
    press(b"d", "preview: 1 record(s) selected")
    press(b"y", "deleted 1 record(s)")
    assert store.get_current("native-lone") is None
    before = {row["id"]: row["artifact_version"] for row in store.list_artifact_refs()}
    press(b"n", "> content:")
    press(b"NATIVECREATED\r", "propose preview:")
    press(b"n", "propose cancelled")
    assert {
        row["id"]: row["artifact_version"] for row in store.list_artifact_refs()
    } == before
    press(b"n", "> content:")
    press(b"NATIVECREATED\r", "propose preview:")
    observations["creation"] = press(b"y", "proposed ")
    created = [
        store.get_current(row["id"])
        for row in store.list_artifact_refs()
        if row["id"] not in before
    ]
    assert len(created) == 1 and created[0].content == {"note": "NATIVECREATED"}
    press(b"/NATIVELONG\r", "native-long")
    payload = store.get_version_content("native-long", 1).encode()
    page_ranges = []
    visible_contents = []

    def visible_page(frame: str, index: int) -> list[str]:
        size = re.search(r"\((\d+)x\d+\)", frame)
        assert size is not None, frame
        width = int(size.group(1))
        chunk_width = max(12, min(48, (width - 12) // 2))
        lines = frame.splitlines()
        top = max(n for n, line in enumerate(lines) if "Memory detail" in line)
        header_rows = []
        for line in lines[top + 1 :]:
            left, right = line.find("│"), line.rfind("│")
            assert left >= 0 and right > left, frame
            rendered = line[left + 2 : right - 1]
            if rendered.rstrip() == "Content:":
                break
            header_rows.append(rendered[:chunk_width])
        header = "".join(header_rows).rstrip()
        bounds = re.fullmatch(
            r"native-long v1 bytes (\d+)\.\.(\d+) (complete|\[x\] next page)",
            header,
        )
        assert bounds is not None, frame
        offset, end = map(int, bounds.groups()[:2])
        assert 0 <= offset < end <= len(payload)
        assert (bounds.group(3) == "complete") == (end == len(payload))
        if index == len(page_ranges):
            assert offset == (page_ranges[-1][1] if page_ranges else 0)
            page_ranges.append((offset, end))
        else:
            assert (offset, end) == page_ranges[index]
        expected = payload[offset:end].decode()
        first_content_row = len(header_rows) + 2
        chunks = [
            expected[start : start + chunk_width]
            for start in range(0, len(expected), chunk_width)
        ]
        seen = {}
        captured = []
        while len(seen) < len(chunks):
            lines = frame.splitlines()
            top = max(n for n, line in enumerate(lines) if "Memory detail" in line)
            bounds = re.search(r"rows (\d+)-(\d+)/(\d+)", "\n".join(lines[top:]))
            assert bounds is not None, frame
            start, stop, total = map(int, bounds.groups())
            body = lines[top + 1 : top + 1 + stop - start + 1]
            assert len(body) == stop - start + 1
            for chunk_index, chunk in enumerate(chunks):
                row = first_content_row + chunk_index
                if start <= row <= stop:
                    line = body[row - start]
                    left, right = line.find("│"), line.rfind("│")
                    assert left >= 0 and right > left
                    # Panel's one-cell padding; exact data includes meaningful spaces.
                    rendered = line[left + 2 : right - 1]
                    assert rendered.startswith(chunk), (row, chunk, rendered)
                    assert rendered[len(chunk) :].strip() == ""
                    seen[chunk_index] = rendered[: len(chunk)]
            captured.append(frame)
            if len(seen) < len(chunks):
                visible = stop - start + 1
                next_start = min(start + visible, total - visible + 1)
                assert next_start > start, (seen, chunks, frame)
                frame = press(b"]", f"rows {next_start}-")
        # Cached-page navigation applies only at top of detail scroll.
        while start > 1:
            previous_start = max(1, start - (stop - start + 1))
            frame = press(b"[", f"rows {previous_start}-")
            bounds = re.search(r"rows (\d+)-(\d+)/(\d+)", frame)
            assert bounds is not None
            start, stop, _total = map(int, bounds.groups())
        content = "".join(seen[n] for n in range(len(chunks)))
        assert content == expected
        if index == len(visible_contents):
            visible_contents.append(content)
        else:
            assert content == visible_contents[index]
        return captured

    frames = []
    while not page_ranges or page_ranges[-1][1] < len(payload):
        index = len(page_ranges)
        offset = page_ranges[-1][1] if page_ranges else 0
        page = press(b"x", f"bytes {offset}")
        captured = visible_page(page, index)
        frames.append(captured)
        if index == 1:
            previous = press(b"[", "bytes 0..")
            visible_page(previous, 0)
            page = press(b"x", f"bytes {page_ranges[1][0]}")
            visible_page(page, 1)
    assert len(page_ranges) >= 3
    visible_text = "".join(visible_contents)
    assert visible_text.encode() == payload
    for marker in ("EARLYMARKER", "MIDDLEMARKER", "ENDMARKER"):
        assert marker in visible_text
    assert any("complete" in frame for frame in frames[-1])
    previous_index = len(page_ranges) - 2
    previous = press(b"[", f"bytes {page_ranges[previous_index][0]}")
    observations["cached_previous_chunks"] = visible_page(previous, previous_index)
    observations["continuation"] = frames
    press(b"-", "native-long")
    versions = {
        row["id"]: row["artifact_version"] for row in store.list_artifact_refs()
    }
    review = press(b"w", "maintenance preview:")
    for task in (
        "promotion_sweep",
        "staleness_sweep",
        "skill_admission_check",
        "expiry_sweep",
    ):
        assert task in review
    press(b"n", "maintenance cancelled")
    assert {
        row["id"]: row["artifact_version"] for row in store.list_artifact_refs()
    } == versions
    press(b"w", "maintenance preview:")
    observations["maintenance"] = press(b"y", "Maintenance cycle 'promotion_sweep'")
    assert store.get_current("native-stale").stale is True
    assert store.get_current("native-expiry").expired is True
    skill = store.get_current("native-skill")
    assert (
        skill.trust_tier == "DERIVED" and skill.artifact_version == versions[skill.id]
    )
    return observations


def _exercise_native_artifact_actions(root: Path, entries: dict, press) -> dict:
    """Same real-key/persisted-byte assertions on POSIX and Windows consoles."""
    import hashlib

    press(b"\x1bOR", "[1-8] go")
    press(b"7", "Captured (")
    press(b"\t", "│ > ")
    press(b"j" * 20, "page 2/2")
    observations = {}
    for rel, marker in (
        ("native-report-00.txt", "CAPTURED REPORT 00"),
        ("native-report-01.txt", "CAPTURED REPORT 01"),
        ("native-unknown.ctrace", "NATIVE UNKNOWN TRACE"),
        ("native-binary.bin", "binary content ("),
        ("native-missing.txt", "immutable_content_unavailable"),
        ("native-corrupt.txt", "immutable_content_unavailable"),
        ("native-long.txt", "NATIVE PAGE ONE"),
    ):
        press(b"/" + rel.encode() + b"\r", rel)
        shown = press(b"i", marker)
        assert "CHANGED LIVE SENTINEL" not in shown
        observations[rel] = {"detail": shown, "sha256": entries[rel]["sha256"]}
        if rel == "native-long.txt":
            continuation = press(b"i", "NATIVE PAGE TWO")
            assert "bytes 1048576-" in continuation
            observations[rel]["continuation"] = continuation
        if rel == "native-binary.bin":
            entry = entries[rel]
            destination = root / ".rush" / "exports" / f"{entry['sha256'][:12]}-{rel}"
            reviewed = press(b"e", "Review before mutation: artifact_export")
            assert "artifact_write" in reviewed
            press(b"n", "declined")
            assert not destination.exists()
            press(b"e", "Review before mutation: artifact_export")
            press(b"y", "exported ")
            assert destination.read_bytes() == entry["bytes"]
            assert destination.stat().st_size == entry["size"]
            assert (
                hashlib.sha256(destination.read_bytes()).hexdigest() == entry["sha256"]
            )
            destination.write_bytes(b"KEEP EXISTING DESTINATION")
            press(b"e", "Review before mutation: artifact_export")
            press(b"y", "export failed:")
            assert destination.read_bytes() == b"KEEP EXISTING DESTINATION"
            assert list(destination.parent.glob("*.partial")) == []
            observations[rel]["declined_no_file"] = True
            observations[rel]["no_overwrite"] = True
        press(b"\x1b", "Captured (")
    return observations


def test_native_action_fixtures_use_real_snapshot_and_memory_producers(tmp_path: Path):
    import base64

    from rush.memory.maintenance import (
        preview_maintenance_candidates,
        run_maintenance_cycle,
    )
    from rush.memory.store import TypedArtifactStore
    from rush.tui import _artifact_cursor
    from rush.workflows.projects import read_project_artifact_page, register_project

    root = tmp_path / "project"
    root.mkdir()
    data_root = tmp_path / "registry"
    project_id = register_project(root, data_root=data_root).project_id
    artifacts = _seed_native_artifact_actions(root, project_id)
    memory = _seed_native_memory_actions(root, project_id)
    for rel in ("native-report-00.txt", "native-report-01.txt", "native-binary.bin"):
        entry = artifacts[rel]
        cursor = _artifact_cursor(
            project_id,
            {
                **entry,
                "run_id": "run-native-artifacts",
                "attempt_id": "1",
                "path": rel,
            },
        )
        page = read_project_artifact_page(project_id, cursor, data_root=data_root)
        assert base64.b64decode(page["content_base64"]) == entry["bytes"]
        assert page["sha256"] == entry["sha256"] and page["size"] == entry["size"]
    store = TypedArtifactStore(root)
    assert store.get_current("native-lone").content == {"note": "NATIVELONE"}
    assert (
        TypedArtifactStore.read_artifact_receipts_readonly(root, "native-lone", 1)[0][
            "id"
        ]
        == "native-create-native-lone"
    )
    owner = memory["native-lone"].owner_scope
    for task, identifier in (
        ("staleness_sweep", "native-stale"),
        ("skill_admission_check", "native-skill"),
        ("expiry_sweep", "native-expiry"),
    ):
        candidates = preview_maintenance_candidates(
            task, project_root=root, owner_scope=owner
        )
        assert candidates == [{"id": identifier, "artifact_version": 2}]
    stale_sweep = run_maintenance_cycle(
        "staleness_sweep",
        project_root=root,
        owner_scope=owner,
        candidate_ids=["native-stale"],
        expected_revisions={"native-stale": 2},
    )
    assert stale_sweep.processed == 1 and stale_sweep.changed == 1
    assert stale_sweep.errors == () and stale_sweep.refused == ()
    assert TypedArtifactStore(root).get_current("native-stale").stale is True


def _windows_installed_tui_child(
    binary: str,
    projects: list[str],
    version: str,
    result: str,
    local_app_data: str,
    git_directory: str,
    pytest_directory: str,
    release: str,
) -> None:
    """Drive installed executable through one real Windows console and read its screen."""
    import ctypes

    from rush.dashboard.terminal_input import _windows_kernel32
    from rush.safety.redactor import SecretRedactor
    from rush.workflows.project_run import load_run_manifest, load_scan_events

    deadline = time.monotonic() + 10
    while not Path(release).exists():
        assert time.monotonic() < deadline, "native console launch gate timed out"
        time.sleep(0.02)

    class Coord(ctypes.Structure):
        _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short)]

    class Rect(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_short),
            ("top", ctypes.c_short),
            ("right", ctypes.c_short),
            ("bottom", ctypes.c_short),
        ]

    class BufferInfo(ctypes.Structure):
        _fields_ = [
            ("size", Coord),
            ("cursor", Coord),
            ("attributes", ctypes.c_uint16),
            ("window", Rect),
            ("max_window", Coord),
        ]

    class CursorInfo(ctypes.Structure):
        _fields_ = [("size", ctypes.c_uint32), ("visible", ctypes.c_int)]

    class Key(ctypes.Structure):
        _fields_ = [
            ("down", ctypes.c_int),
            ("repeat", ctypes.c_uint16),
            ("virtual", ctypes.c_uint16),
            ("scan", ctypes.c_uint16),
            ("char", ctypes.c_wchar),
            ("control", ctypes.c_uint32),
        ]

    class Event(ctypes.Union):
        _fields_: ClassVar = [("key", Key), ("padding", ctypes.c_byte * 16)]

    class Record(ctypes.Structure):
        _fields_ = [("kind", ctypes.c_uint16), ("event", Event)]

    kernel = _windows_kernel32()
    kernel.CreateFileW.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    )
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.GetConsoleScreenBufferInfo.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(BufferInfo),
    )
    kernel.GetConsoleCursorInfo.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(CursorInfo),
    )
    kernel.SetConsoleScreenBufferSize.argtypes = (ctypes.c_void_p, Coord)
    kernel.SetConsoleWindowInfo.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.POINTER(Rect),
    )
    kernel.ReadConsoleOutputCharacterW.argtypes = (
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        Coord,
        ctypes.POINTER(ctypes.c_uint32),
    )
    kernel.ReadConsoleOutputAttribute.argtypes = (
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        Coord,
        ctypes.POINTER(ctypes.c_uint32),
    )
    kernel.WriteConsoleOutputCharacterW.argtypes = (
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        Coord,
        ctypes.POINTER(ctypes.c_uint32),
    )
    kernel.WriteConsoleInputW.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(Record),
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
    )
    kernel.SetStdHandle.argtypes = (ctypes.c_uint32, ctypes.c_void_p)
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel.CloseHandle.restype = ctypes.c_int
    CtrlHandler = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint32)
    kernel.SetConsoleCtrlHandler.argtypes = (CtrlHandler, ctypes.c_int)
    kernel.GenerateConsoleCtrlEvent.argtypes = (ctypes.c_uint32, ctypes.c_uint32)
    kernel.GenerateConsoleCtrlEvent.restype = ctypes.c_int
    kernel.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    kernel.GetConsoleMode.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
    )
    transcript: dict = {"sizes": [], "inputs": [], "frames": {}, "exit": None}
    assert kernel.FreeConsole() or ctypes.get_last_error() == 6
    assert kernel.AllocConsole(), "native child could not allocate a real console"
    input_handle = output_handle = None
    proc = None
    worker_handle = None
    controller_handler = None
    standard_handles = None
    try:
        # Both real handles are inherited explicitly by the installed process.
        input_handle = kernel.CreateFileW("CONIN$", 0xC0000000, 3, None, 3, 0, None)
        output_handle = kernel.CreateFileW("CONOUT$", 0xC0000000, 3, None, 3, 0, None)
        invalid = ctypes.c_void_p(-1).value
        assert input_handle not in (None, invalid)
        assert output_handle not in (None, invalid)
        os.set_handle_inheritable(input_handle, True)
        os.set_handle_inheritable(output_handle, True)
        standard_handles = [kernel.GetStdHandle(which) for which in (-10, -11, -12)]
        for which, handle in (
            (-10, input_handle),
            (-11, output_handle),
            (-12, output_handle),
        ):
            assert kernel.SetStdHandle(which, handle)

        def modes() -> list[int]:
            values = []
            for handle in (input_handle, output_handle):
                value = ctypes.c_uint32()
                assert kernel.GetConsoleMode(handle, ctypes.byref(value))
                values.append(value.value)
            return values

        def active_output() -> int:
            # Rich Live(screen=True) activates an alternate screen buffer;
            # the inherited output handle still names its original buffer.
            handle = kernel.CreateFileW("CONOUT$", 0xC0000000, 3, None, 3, 0, None)
            assert handle not in (None, invalid)
            return handle

        def info_for(handle: int) -> BufferInfo:
            info = BufferInfo()
            assert kernel.GetConsoleScreenBufferInfo(handle, ctypes.byref(info))
            return info

        def size() -> tuple[int, int]:
            handle = active_output()
            try:
                info = info_for(handle)
            finally:
                assert kernel.CloseHandle(handle)
            return (
                info.window.right - info.window.left + 1,
                info.window.bottom - info.window.top + 1,
            )

        def resize(width: int, height: int) -> None:
            # A small window permits buffer shrink; set buffer before growing.
            handle = active_output()
            try:
                small = Rect(0, 0, 1, 1)
                assert kernel.SetConsoleWindowInfo(handle, True, ctypes.byref(small))
                assert kernel.SetConsoleScreenBufferSize(handle, Coord(width, height))
                window = Rect(0, 0, width - 1, height - 1)
                assert kernel.SetConsoleWindowInfo(handle, True, ctypes.byref(window))
            finally:
                assert kernel.CloseHandle(handle)
            assert size() == (width, height)
            transcript["sizes"].append([width, height])

        def screen() -> str:
            handle = active_output()
            try:
                info = info_for(handle)
                width = info.window.right - info.window.left + 1
                lines = []
                for row in range(info.window.top, info.window.bottom + 1):
                    chars = ctypes.create_unicode_buffer(width + 1)
                    count = ctypes.c_uint32()
                    assert kernel.ReadConsoleOutputCharacterW(
                        handle,
                        chars,
                        width,
                        Coord(info.window.left, row),
                        ctypes.byref(count),
                    )
                    assert count.value == width
                    lines.append(chars.value.rstrip())
                return "\n".join(lines)
            finally:
                assert kernel.CloseHandle(handle)

        def foreground_colors() -> list[int]:
            handle = active_output()
            try:
                info = info_for(handle)
                width = info.window.right - info.window.left + 1
                colors = set()
                for row in range(info.window.top, info.window.bottom + 1):
                    attributes = (ctypes.c_uint16 * width)()
                    count = ctypes.c_uint32()
                    assert kernel.ReadConsoleOutputAttribute(
                        handle,
                        attributes,
                        width,
                        Coord(info.window.left, row),
                        ctypes.byref(count),
                    )
                    assert count.value == width
                    colors.update(value & 0x0F for value in attributes)
                return sorted(colors)
            finally:
                assert kernel.CloseHandle(handle)

        def cursor_info() -> tuple[int, bool]:
            handle = active_output()
            try:
                cursor = CursorInfo()
                assert kernel.GetConsoleCursorInfo(handle, ctypes.byref(cursor))
                return cursor.size, bool(cursor.visible)
            finally:
                assert kernel.CloseHandle(handle)

        def observe(
            label: str,
            marker: str,
            timeout: float = 12.0,
            absent: str = "",
        ) -> None:
            deadline = time.monotonic() + timeout
            frame = ""
            while time.monotonic() < deadline:
                try:
                    frame = screen()
                except AssertionError:
                    # Console host may swap buffers during a single read.
                    if proc is not None and proc.poll() is not None:
                        break
                    time.sleep(0.05)
                    continue
                if marker in frame and (not absent or absent not in frame):
                    transcript["frames"][label] = SecretRedactor.redact_text(frame)
                    return
                if proc is not None and proc.poll() is not None:
                    break
                time.sleep(0.05)
            raise AssertionError(
                f"{label}: no visible {marker!r}; "
                f"screen={SecretRedactor.redact_text(frame)!r}"
            )

        def press(
            name: str, virtual: int, scan: int, char: str = "\0", control: int = 0
        ) -> None:
            records = (Record * 2)()
            for index, down in enumerate((1, 0)):
                records[index].kind = 1
                records[index].event.key = Key(down, 1, virtual, scan, char, control)
            written = ctypes.c_uint32()
            assert kernel.WriteConsoleInputW(
                input_handle, records, 2, ctypes.byref(written)
            )
            assert written.value == 2
            transcript["inputs"].append(
                {
                    "key": name,
                    "record_bytes_hex": ctypes.string_at(
                        ctypes.byref(records), ctypes.sizeof(records)
                    ).hex(),
                }
            )

        resize(80, 24)
        original_modes = modes()
        original_cursor = cursor_info()
        sentinel = "RUSH-NATIVE-ORIGINAL-BUFFER"
        written = ctypes.c_uint32()
        assert kernel.WriteConsoleOutputCharacterW(
            output_handle,
            sentinel,
            len(sentinel),
            Coord(0, 0),
            ctypes.byref(written),
        )
        assert written.value == len(sentinel)
        default_foreground = info_for(output_handle).attributes & 0x0F
        env = {
            "PATH": os.pathsep.join(
                (
                    os.path.join(
                        os.environ.get("SystemRoot", "C:\\Windows"), "System32"
                    ),
                    git_directory,
                    pytest_directory,
                )
            ),
            "SystemRoot": os.environ.get("SystemRoot", "C:\\Windows"),
            "windir": os.environ.get("windir", "C:\\Windows"),
            "LOCALAPPDATA": local_app_data,
            "USERPROFILE": str(Path(local_app_data).parent),
            "NO_COLOR": "1",
        }
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESTDHANDLES
        startup.hStdInput = input_handle
        startup.hStdOutput = output_handle
        startup.hStdError = output_handle
        startup.lpAttributeList = {"handle_list": [input_handle, output_handle]}
        proc = subprocess.Popen(
            [binary, "ui", "--allow-build", *projects],
            cwd=Path(projects[0]).parent,
            env=env,
            startupinfo=startup,
            close_fds=True,
        )
        observe("launch", f"Rush Interactive Quality Explorer v{version}")
        assert sentinel not in transcript["frames"]["launch"]
        transcript["no_color_foregrounds"] = foreground_colors()
        assert set(transcript["no_color_foregrounds"]) <= {
            default_foreground,
            default_foreground | 0x08,
        }
        assert f"[1/2] {Path(projects[0]).name}" in transcript["frames"]["launch"]
        assert "(80x24)" in transcript["frames"]["launch"]
        for width, height in ((80, 24), (120, 40), (60, 20)):
            if (width, height) != (80, 24):
                resize(width, height)
            observe(f"size-{width}x{height}", f"({width}x{height})")
            assert size() == (width, height)
            for digit, label, domain in (
                (1, "Overview", "Runs: 1 recorded"),
                (2, "Map", "observed.py"),
                (3, "Scans/Findings", "run-alpha"),
                (4, "Memory", "owner=project:"),
                (5, "Tokens", "net_tokens_saved"),
                (6, "Git", "observed.py"),
                (7, "Artifacts", "Captured (1)"),
                (8, "Setup/Agents", "Config: create rush.toml"),
            ):
                press("F3", 0x72, 0x3D)
                observe(f"chooser-{width}x{height}-{digit}", "[1-8] go")
                press(str(digit), ord(str(digit)), digit + 1, str(digit))
                key = f"section-{width}x{height}-{digit}"
                section_header = (
                    f"{label}  ({width}x{height})  [1/2] {Path(projects[0]).name}"
                    if width < 80
                    else f"[1/2] {Path(projects[0]).name}  {label}"
                )
                observe(
                    key,
                    section_header,
                    absent="[1-8] go",
                )
                observe(key, domain)
                if digit == 1:
                    assert "run-alpha" in transcript["frames"][key]
                elif digit == 4:
                    assert "native-memory-alpha" in transcript["frames"][key]
                elif digit == 5:
                    compact = "".join(transcript["frames"][key].split())
                    assert '"net_tokens_saved":80' in compact
                    assert '"compression_ratio":0.8' in compact
                elif digit == 6:
                    assert "dirty=True" in transcript["frames"][key]
                elif digit == 7:
                    assert "run-alpha" in transcript["frames"][key]
                    assert " / 1" in transcript["frames"][key]
                elif digit == 8:
                    assert "Register: already" in transcript["frames"][key]
        press("F2", 0x71, 0x3C)
        observe("project-selector", Path(projects[1]).name)
        press("down", 0x28, 0x50)
        press("Enter", 0x0D, 0x1C, "\r")
        observe("project-two", f"[2/2] {Path(projects[1]).name}")
        project_two_map = (
            f"Map  (60x20)  [2/2] {Path(projects[1]).name}"
            if size() == (60, 20)
            else f"[2/2] {Path(projects[1]).name}  Map"
        )
        press("F3", 0x72, 0x3D)
        observe("project-two-chooser", "[1-8] go")
        press("2", 0x32, 0x03, "2")
        observe("project-two-map", project_two_map)
        observe("project-two-map-root", ">[+] bravo")
        press("Right", 0x27, 0x4D)
        observe("project-two-map-file", "bravo-only.py")
        assert (
            f"[2/2] {Path(projects[1]).name}"
            in transcript["frames"]["project-two-map-file"]
        )
        assert ">[-] bravo" in transcript["frames"]["project-two-map-file"]
        resize(80, 24)
        observe("focus-start", ">2 Map")
        press("Tab", 0x09, 0x0F, "\t")
        time.sleep(0.1)
        observe("tab-detail", "[2/2] bravo", absent=">Refresh")
        press("Tab", 0x09, 0x0F, "\t")
        observe("tab-actions", ">Refresh")
        press("Shift+Tab", 0x09, 0x0F, "\t", 0x10)
        observe("shift-tab-detail", "[2/2] bravo", absent=">Refresh")
        press("Shift+Tab", 0x09, 0x0F, "\t", 0x10)
        time.sleep(0.1)
        observe("shift-tab-list", "[2/2] bravo", absent=">Refresh")
        press("Shift+Tab", 0x09, 0x0F, "\t", 0x10)
        time.sleep(0.1)
        observe("shift-tab-nav", ">2 Map")
        press("down", 0x28, 0x50)
        observe("nav-scans-selected", ">3 Scans/Findings")
        press("Enter", 0x0D, 0x1C, "\r")
        observe("nav-scans-entered", "Scan history")
        press("F3", 0x72, 0x3D)
        observe("overview-chooser", "[1-8] go")
        press("1", 0x31, 0x02, "1")
        observe("overview-before-recovery", "[2/2] bravo  Overview")
        config = Path(projects[1]) / "rush.toml"
        config.write_text("[tools\n", encoding="utf-8")
        press("F5", 0x74, 0x3F)
        observe("invalid-config", "rush.toml: invalid")
        config.write_text("[tools]\n", encoding="utf-8")
        press("F5", 0x74, 0x3F)
        observe("recovered-config", "rush.toml: valid")
        prior_attempts = sorted(
            (Path(projects[1]) / ".rush" / "runs").rglob("attempt.json")
        )
        press("s", 0x53, 0x1F, "s")
        observe("start-scan-review", "Review before mutation: start_scan")
        observe("start-scan-grants", "grants: artifact_write, build, cache_write")
        press("n", 0x4E, 0x31, "n")
        observe("start-scan-denied", "declined")
        assert (
            sorted((Path(projects[1]) / ".rush" / "runs").rglob("attempt.json"))
            == prior_attempts
        )
        test_source = Path(projects[1]) / "test_native.py"
        started = Path(projects[1]) / "native-started.json"
        release_gate = Path(projects[1]) / "native-release"
        test_source.write_text(
            "import json, os, time\n"
            "from pathlib import Path\n"
            "def test_real_native_work():\n"
            f"    Path({str(started)!r}).write_text(json.dumps({{'pid': os.getpid()}}))\n"
            "    deadline = time.monotonic() + 30\n"
            f"    while not Path({str(release_gate)!r}).exists() and time.monotonic() < deadline:\n"
            "        time.sleep(0.02)\n"
            f"    assert Path({str(release_gate)!r}).exists(), 'native gate was not released'\n",
            encoding="utf-8",
        )
        (Path(projects[1]) / "pyproject.toml").write_text(
            '[tool.pytest.ini_options]\ntestpaths = ["test_native.py"]\n',
            encoding="utf-8",
        )
        press("s", 0x53, 0x1F, "s")
        observe("accepted-scan-review", "Review before mutation: start_scan")
        observe("accepted-scan-grants", "grants: artifact_write, build, cache_write")
        press("y", 0x59, 0x15, "y")
        start_deadline = time.monotonic() + 30
        while not started.is_file() and time.monotonic() < start_deadline:
            assert proc.poll() is None, (
                "installed TUI exited before native pytest started"
            )
            time.sleep(0.05)
        assert started.is_file(), "installed scan did not execute discovered pytest"
        worker_pid = json.loads(started.read_text(encoding="utf-8"))["pid"]
        assert isinstance(worker_pid, int) and worker_pid > 0
        worker_handle = kernel.OpenProcess(0x00100000, False, worker_pid)
        assert worker_handle, "native pytest process could not be observed"
        transcript["native_pytest_pid"] = worker_pid
        press("c", 0x43, 0x2E, "c")
        cancel_deadline = time.monotonic() + 12
        requests: list[Path] = []
        while not requests and time.monotonic() < cancel_deadline:
            requests = list(
                (Path(projects[1]) / ".rush" / "runs").glob(
                    "*/attempts/*/cancel_requested.json"
                )
            )
            time.sleep(0.05)
        assert len(requests) == 1, "native scan cancel marker absent or ambiguous"
        cancellation = json.loads(requests[0].read_text(encoding="utf-8"))
        transcript["cancel_request"] = cancellation
        cancel_deadline = time.monotonic() + 20
        events: dict = {}
        while time.monotonic() < cancel_deadline:
            events = load_scan_events(
                Path(projects[1]), cancellation["run_id"], cancellation["attempt_id"]
            )
            if events["run_state"] == "cancelled":
                break
            time.sleep(0.05)
        assert events.get("run_state") == "cancelled"
        manifest = load_run_manifest(
            Path(projects[1]),
            cancellation["run_id"],
            attempt_id=cancellation["attempt_id"],
        )
        assert manifest is not None and manifest["run_state"] == "cancelled"
        assert kernel.WaitForSingleObject(worker_handle, 5000) == 0
        transcript["scan_events"] = events
        transcript["scan_manifest"] = manifest
        post_cancel_attempts = sorted(
            (Path(projects[1]) / ".rush" / "runs").rglob("attempt.json")
        )
        assert len(post_cancel_attempts) == len(prior_attempts) + 1
        press("F3", 0x72, 0x3D)
        observe("cancelled-scan-chooser", "[1-8] go")
        press("3", 0x33, 0x04, "3")
        observe("cancelled-scan-visible", "cancelled")
        assert cancellation["run_id"] in transcript["frames"]["cancelled-scan-visible"]
        press("F3", 0x72, 0x3D)
        observe("paste-map-chooser", "[1-8] go")
        press("2", 0x32, 0x03, "2")
        observe("paste-map", ">[-] bravo")
        press("/", 0xBF, 0x35, "/")
        observe("paste-search", "map search /")
        for character in "\x1b[200~βqC\x1b[2J\x1b[201~":
            press(f"paste-{ord(character):04x}", 0, 0, character)
        observe("literal-bracketed-paste", "βqC")
        assert (
            sorted((Path(projects[1]) / ".rush" / "runs").rglob("attempt.json"))
            == post_cancel_attempts
        )
        press("Esc", 0x1B, 0x01, "\x1b")
        observe("paste-search-closed", ">[-] bravo")
        press("?", 0xBF, 0x35, "?", 0x10)
        observe("help", "Key Bindings")
        press("Esc", 0x1B, 0x01, "\x1b")
        observe("help-closed", f"[2/2] {Path(projects[1]).name}", absent="Key Bindings")
        press("q", 0x51, 0x10, "q")
        transcript["exit"] = proc.wait(timeout=15)
        assert transcript["exit"] == 0
        assert modes() == original_modes
        assert cursor_info() == original_cursor
        assert sentinel in screen()
        transcript["quit_console_restored"] = True
        local_actions_start = len(transcript["inputs"])
        from rush.workflows.projects import register_project

        transcript["local_actions_viewports"] = []
        for columns, rows in ((80, 24), (120, 40), (60, 20)):
            artifact_root = Path(projects[0]).parent / f"local-actions-{columns}x{rows}"
            artifact_root.mkdir()
            artifact_project = register_project(
                artifact_root, data_root=Path(local_app_data) / "Rush"
            )
            artifact_entries = _seed_native_artifact_actions(
                artifact_root, artifact_project.project_id
            )
            memory_entries = _seed_native_memory_actions(
                artifact_root, artifact_project.project_id
            )
            resize(columns, rows)
            proc = subprocess.Popen(
                [binary, "ui", str(artifact_root)],
                cwd=artifact_root.parent,
                env=env,
                startupinfo=startup,
                close_fds=True,
            )
            observe(f"local-ready-{columns}x{rows}", "[1/1]")

            def local_press(keys: bytes, marker: str) -> str:
                if keys == b"\x1bOR":
                    press("F3", 0x72, 0x3D)
                else:
                    for character in keys.decode():
                        press(f"local-{ord(character):04x}", 0, 0, character)
                label = f"local-actions-{len(transcript['inputs'])}"
                observe(label, marker)
                return transcript["frames"][label]

            memory_actions = _exercise_native_memory_actions(
                artifact_root, memory_entries, local_press
            )
            artifact_actions = _exercise_native_artifact_actions(
                artifact_root, artifact_entries, local_press
            )
            press("local-q", 0x51, 0x10, "q")
            assert proc.wait(timeout=15) == 0
            assert modes() == original_modes
            assert cursor_info() == original_cursor
            assert sentinel in screen()
            transcript["local_actions_viewports"].append(
                {
                    "size": [columns, rows],
                    "root": str(artifact_root),
                    "project_id": artifact_project.project_id,
                    "memory_actions": memory_actions,
                    "artifact_actions": artifact_actions,
                    "console_restored": True,
                }
            )
        resize(80, 24)
        transcript["local_actions_inputs"] = (
            len(transcript["inputs"]) - local_actions_start
        )
        controller_handler = CtrlHandler(lambda _event: True)
        assert kernel.SetConsoleCtrlHandler(controller_handler, True)
        reduced_env = {**env, "RUSH_REDUCED_MOTION": "1"}
        proc = subprocess.Popen(
            [binary, "ui", *projects],
            cwd=Path(projects[0]).parent,
            env=reduced_env,
            startupinfo=startup,
            close_fds=True,
        )
        observe("idle-interrupt-ready", f"[1/2] {Path(projects[0]).name}")
        observe("reduced-motion-loaded", "Runs: 1 recorded")
        settled = screen()
        time.sleep(0.7)
        assert screen() == settled, "reduced-motion idle screen changed"
        transcript["reduced_motion_idle_stable_seconds"] = 0.7
        interrupt_start = time.monotonic()
        press("Ctrl+C", 0x43, 0x2E, "\x03", 0x08)
        transcript["idle_interrupt_exit"] = proc.wait(timeout=5)
        transcript["idle_interrupt_seconds"] = time.monotonic() - interrupt_start
        assert transcript["idle_interrupt_exit"] == 0
        assert modes() == original_modes
        assert cursor_info() == original_cursor
        assert sentinel in screen()
        transcript["key_event_console_restored"] = True
        proc = subprocess.Popen(
            [binary, "ui", *projects],
            cwd=Path(projects[0]).parent,
            env=reduced_env,
            startupinfo=startup,
            close_fds=True,
        )
        observe("control-event-ready", f"[1/2] {Path(projects[0]).name}")
        interrupt_start = time.monotonic()
        assert kernel.GenerateConsoleCtrlEvent(0, 0)
        transcript["control_event"] = "CTRL_C_EVENT"
        transcript["control_event_exit"] = proc.wait(timeout=5)
        transcript["control_event_seconds"] = time.monotonic() - interrupt_start
        assert transcript["control_event_exit"] == 0
        assert modes() == original_modes
        assert cursor_info() == original_cursor
        assert sentinel in screen()
        transcript["control_event_console_restored"] = True
        transcript["restored_modes"] = original_modes
        transcript["restored_cursor"] = list(original_cursor)
        transcript["process_reaped"] = True
    except BaseException as exc:
        transcript["failure"] = SecretRedactor.redact_text(repr(exc))
        raise
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        if worker_handle is not None:
            assert kernel.CloseHandle(worker_handle)
        if controller_handler is not None:
            kernel.SetConsoleCtrlHandler(controller_handler, False)
        if standard_handles is not None:
            for which, handle in zip((-10, -11, -12), standard_handles, strict=True):
                kernel.SetStdHandle(which, handle)
        if input_handle not in (None, ctypes.c_void_p(-1).value):
            assert kernel.CloseHandle(input_handle)
        if output_handle not in (None, ctypes.c_void_p(-1).value):
            assert kernel.CloseHandle(output_handle)
        kernel.FreeConsole()
        Path(result).write_text(json.dumps(transcript), encoding="utf-8")


@pytest.mark.windows_only
def test_windows_installed_tui_real_console_journey(tmp_path, windows_kernel) -> None:
    import hashlib
    import platform
    import shutil
    import zipfile
    from contextlib import chdir

    from rush.dashboard.state import MutationLedger
    from rush.memory.store import MemoryArtifact, OwnerScope, TypedArtifactStore
    from rush.runtime import subprocesses as runtime_subprocesses
    from rush.token_economy.telemetry import TelemetryStore
    from rush.workflows.project_run import _capture_artifact_snapshots
    from rush.workflows.projects import register_project
    from scripts.probe_installed_artifacts import verify_archive_checksum

    archive = Path(os.environ["RUSH_G8_NATIVE_ARCHIVE"])
    sums = Path(os.environ["RUSH_G8_NATIVE_SUMS"])
    receipt_dir = Path(os.environ["RUSH_G8_NATIVE_RECEIPT_DIR"])
    assert verify_archive_checksum(archive, sums)
    assert archive.suffix == ".zip"
    with zipfile.ZipFile(archive) as package:
        assert sorted(package.namelist()) == ["VERSION", "rush.exe"]
        version = package.read("VERSION").decode("utf-8").strip()
        binary = tmp_path / "rush.exe"
        binary.write_bytes(package.read("rush.exe"))
    assert version and binary.stat().st_size > 0
    data_home = tmp_path / "local_app_data"
    data_root = data_home / "Rush"
    roots = []
    for name in ("alpha", "bravo"):
        root = tmp_path / name
        root.mkdir()
        subprocess.run(["git", "init", "--quiet", str(root)], check=True, timeout=10)
        file_name = "observed.py" if name == "alpha" else "bravo-only.py"
        source = root / file_name
        source.write_text("answer = 42\n", encoding="utf-8")
        record = register_project(root, data_root=data_root)
        with chdir(root):
            snapshots = _capture_artifact_snapshots(
                root,
                f"run-{name}",
                "1",
                "native-tool",
                {"artifacts": [file_name]},
            )
        assert file_name in snapshots
        attempt = root / ".rush" / "runs" / f"run-{name}" / "attempts" / "1"
        attempt.mkdir(parents=True)
        (attempt / "attempt.json").write_text(
            json.dumps(
                {
                    "run_id": f"run-{name}",
                    "attempt_id": "1",
                    "project_id": record.project_id,
                    "started_at": "2026-01-01T00:00:00+00:00",
                    "attempt_generation": 1,
                }
            ),
            encoding="utf-8",
        )
        (attempt / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "run_id": f"run-{name}",
                    "attempt_id": "1",
                    "run_state": "completed",
                    "aggregate": {
                        "findings": [
                            {
                                "finding_id": f"finding-{name}",
                                "path": file_name,
                                "line": 1,
                                "severity": "warning",
                                "rule": "R1",
                                "message": f"{name} row",
                                "provenance": "fixture/1",
                            }
                        ]
                    },
                    "totals": {"finding_count": 1},
                    "file_inventory": [{"path": file_name}],
                    "scheduled": [
                        {
                            "candidate_id": "native-tool",
                            "category": "quality",
                            "outcome": "completed",
                            "child": {"status": "ok", "artifacts": [file_name]},
                            "artifact_snapshots": snapshots,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        TypedArtifactStore(root).write(
            MemoryArtifact(
                id=f"native-memory-{name}",
                family="memory",
                subject="domain_knowledge",
                trust_tier="EXTERNAL_WRITE",
                content={"note": f"{name} native evidence"},
                source="native-fixture",
                created_at=time.time(),
                owner_scope=OwnerScope("project", record.project_id),
            )
        )
        TelemetryStore(root).record_savings(
            "native",
            raw_tokens=100,
            compressed_tokens=20,
            project_id=record.project_id,
            run_id=f"run-{name}",
            agent_id="native",
            session_id="native",
        )
        roots.append(str(root))
    MutationLedger(db_path=data_root / "dashboard" / "mutation_ledger.db")
    git_executable = shutil.which("git")
    pytest_executable = shutil.which("pytest")
    assert git_executable is not None
    assert pytest_executable is not None
    child_result = tmp_path / "native-console.json"
    release = tmp_path / "native-console-release"
    job = runtime_subprocesses._create_kill_on_close_job(
        f"Local\\RushNativeTui-{uuid.uuid4().hex}"
    )
    assert job
    child = None
    try:
        child = spawn_child(
            __name__,
            "_windows_installed_tui_child",
            [
                str(binary),
                roots,
                version,
                str(child_result),
                str(data_home),
                str(Path(git_executable).parent),
                str(Path(pytest_executable).parent),
                str(release),
            ],
        )
        assert runtime_subprocesses._assign_process_to_job(job, child.pid)
        release.write_text("launch", encoding="utf-8")
        exit_code = child.wait(timeout=180)
        natural_zero_processes = _wait_until(
            lambda: runtime_subprocesses._windows_job_has_zero_processes(job)
        )
        assert natural_zero_processes, "installed TUI left child processes after exit"
        assert child_result.is_file()
        observations = json.loads(child_result.read_text(encoding="utf-8"))
        assert exit_code == 0, observations.get("failure", observations)
        assert observations["sizes"] == [
            [80, 24],
            [120, 40],
            [60, 20],
            [80, 24],
            [80, 24],
            [120, 40],
            [60, 20],
            [80, 24],
        ]
        assert [row["size"] for row in observations["local_actions_viewports"]] == [
            [80, 24],
            [120, 40],
            [60, 20],
        ]
        assert all(
            row["console_restored"] for row in observations["local_actions_viewports"]
        )
        assert observations["exit"] == 0
        assert observations["idle_interrupt_exit"] == 0
        assert observations["idle_interrupt_seconds"] <= 5
        assert observations["control_event"] == "CTRL_C_EVENT"
        assert observations["control_event_exit"] == 0
        assert observations["control_event_seconds"] <= 5
        assert observations["quit_console_restored"] is True
        assert observations["key_event_console_restored"] is True
        assert observations["control_event_console_restored"] is True
        assert len(observations["restored_cursor"]) == 2
        assert observations["process_reaped"] is True
        assert len(observations["restored_modes"]) == 2
        assert len(observations["inputs"]) - observations["local_actions_inputs"] == 99
        for width, height in ((80, 24), (120, 40), (60, 20)):
            assert (
                f"({width}x{height})"
                in observations["frames"][f"size-{width}x{height}"]
            )
            assert all(
                f"section-{width}x{height}-{digit}" in observations["frames"]
                for digit in range(1, 9)
            )
    finally:
        windows_kernel.TerminateJobObject(job, 1)
        zero_processes = _wait_until(
            lambda: runtime_subprocesses._windows_job_has_zero_processes(job)
        )
        windows_kernel.CloseHandle(job)
        if child is not None:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
        assert zero_processes, "installed TUI process tree remained in Windows job"
    receipt = {
        "executable": str(binary),
        "version": version,
        "archive": str(archive),
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "platform": platform.platform(),
        "observations": observations,
        "natural_zero_processes": natural_zero_processes,
        "job_zero_processes": zero_processes,
    }
    receipt_dir.mkdir(parents=True, exist_ok=True)
    (receipt_dir / "windows-installed-tui.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
