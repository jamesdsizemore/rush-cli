"""A frozen (PyInstaller) Rush's `sys.executable` is the rush binary itself,
never a Python. Every child that runs project code must run a real project
interpreter: the project's own .venv/venv python, else the active virtualenv's
python, else `python3`/`python` on PATH -- and name the missing prerequisite
when none exists instead of running `rush -m pytest` into `exit 2`."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

import rush.tools.fuzz as fuzz_mod
from rush.engines.support_policy import EngineSupportPolicy
from rush.permissions import ExecutionPermissions
from rush.tools.cold_start import ColdStartTool
from rush.tools.fuzz import FuzzTool
from rush.tools.mem_profile import MemProfileTool
from rush.tools.patch_apply import PatchApplyTool
from rush.tools.test import TestTool
from rush.tools.test_heal import TestHealer

REAL_PYTHON = sys.executable
GIT = shutil.which("git")
BUILD = ExecutionPermissions(build=True)
SLOW = ExecutionPermissions(slow=True)


def _script(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _python_shim(path: Path, marker: Path) -> Path:
    """A working interpreter that records each time it runs."""
    return _script(path, f'echo run >> "{marker}"\nexec "{REAL_PYTHON}" "$@"\n')


def _frozen_rush(monkeypatch, tmp_path: Path) -> Path:
    """Make this process look like the installed binary: frozen, with
    `sys.executable` a fake rush that records any self-invocation."""
    marker = tmp_path / "rush-self-invoked"
    fake_rush = _script(
        tmp_path / "installed" / "rush",
        f'echo "$@" >> "{marker}"\necho "rush: no such option -m" >&2\nexit 2\n',
    )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_rush))
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    return marker


def _path_bin(monkeypatch, tmp_path: Path, *, python: bool) -> Path:
    """A PATH holding only git, a `pytest` launcher and (optionally) python3."""
    bin_dir = tmp_path / "path-bin"
    bin_dir.mkdir()
    assert GIT is not None
    (bin_dir / "git").symlink_to(GIT)
    _script(bin_dir / "pytest", f'exec "{REAL_PYTHON}" -m pytest "$@"\n')
    if python:
        _python_shim(bin_dir / "python3", tmp_path / "path-python-ran")
    monkeypatch.setenv("PATH", str(bin_dir))
    return bin_dir


def _commit(root: Path) -> None:
    for argv in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "rush@example.invalid"],
        ["git", "config", "user.name", "Rush Test"],
        ["git", "add", "."],
        ["git", "commit", "-qm", "fixture"],
    ):
        subprocess.run(argv, cwd=root, check=True)


def _pytest_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[project]\nname = 'demo'\n", "utf-8")
    (root / "test_demo.py").write_text("def test_ok():\n    assert True\n", "utf-8")
    return root


def test_frozen_rush_never_runs_itself_as_python(monkeypatch, tmp_path: Path) -> None:
    marker = _frozen_rush(monkeypatch, tmp_path)
    bin_dir = _path_bin(monkeypatch, tmp_path, python=True)
    path_python = str(bin_dir / "python3")

    # pytest engine (rush test / rush check): the project's real pytest result.
    project = _pytest_project(tmp_path / "project")
    tested = TestTool().run(project, permissions=BUILD)
    assert tested["status"] == "ok", tested
    assert "1 passed" in tested["summary"]

    # test-heal: collection, perturbation runs and the verified repair.
    heal_root = tmp_path / "heal"
    heal_root.mkdir()
    (heal_root / "test_flaky.py").write_text(
        "import random\n\ndef test_random_value():\n"
        "    value = random.random()\n"
        "    assert value > 0.35\n",
        encoding="utf-8",
    )
    _commit(heal_root)
    healed = TestHealer(project_root=heal_root).diagnose_and_heal(
        "test_flaky.py",
        runs=12,
        permissions=ExecutionPermissions(slow=True, artifact_write=True),
    )
    assert healed["status"] == "ok", healed
    assert healed["verified"] is True

    # patch-apply: the sandbox verification command.
    patch_root = _pytest_project(tmp_path / "patch")
    (patch_root / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    (patch_root / "change.diff").write_text(
        "--- a/mod.py\n+++ b/mod.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n",
        encoding="utf-8",
    )
    _commit(patch_root)
    patched = PatchApplyTool().run(patch_root, patch_file=Path("change.diff"))
    assert patched["status"] == "ok", patched["summary"]

    # cold-start and mem-profile: dynamic measurement of the target.
    target = tmp_path / "measure" / "main.py"
    target.parent.mkdir()
    target.write_text("import json\nprint(json.dumps([1]))\n", encoding="utf-8")
    cold = ColdStartTool().run(target, dynamic=True, permissions=SLOW)
    assert cold["status"] != "error", cold
    assert cold["metrics"]["import_time_measured"] is True
    mem = MemProfileTool().run(target, dynamic=True, permissions=SLOW)
    assert mem["status"] != "error", mem
    assert mem["metrics"]["completed"] is True

    # fuzz: the harness argv.
    fuzz_root = tmp_path / "fuzz"
    (fuzz_root / "corpus").mkdir(parents=True)
    (fuzz_root / "corpus" / "seed").write_bytes(b"SAFE")
    (fuzz_root / "harness.py").write_text("print('clean')\n", encoding="utf-8")
    monkeypatch.setattr(fuzz_mod, "atheris_available", lambda _python: True)
    argvs: list[list[str]] = []
    real_run = fuzz_mod.run_subprocess

    def recording_run(argv, **kwargs):
        argvs.append(list(argv))
        return real_run(argv, **kwargs)

    monkeypatch.setattr(fuzz_mod, "run_subprocess", recording_run)
    fuzzed = FuzzTool().run(
        fuzz_root,
        config={"options": {"harness": "harness.py", "corpus": "corpus"}},
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    assert fuzzed["status"] != "error", fuzzed
    assert [argv[0] for argv in argvs] == [path_python]

    # python-module engine discovery never reports the rush binary.
    assert EngineSupportPolicy.load().discover_engine("onnxruntime") == path_python

    assert not marker.exists(), marker.read_text(encoding="utf-8")


def test_project_python_prefers_the_project_venv(monkeypatch, tmp_path: Path) -> None:
    from rush.runtime.project_python import project_python

    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    project = _pytest_project(tmp_path / "project")
    venv_marker = tmp_path / "venv-python-ran"
    venv_python = _python_shim(project / ".venv" / "bin" / "python", venv_marker)

    # From source, a project with its own venv runs its tests with it.
    assert project_python(project) == str(venv_python)
    assert project_python(project / "test_demo.py") == str(venv_python)
    tested = TestTool().run(project, permissions=BUILD)
    assert tested["status"] == "ok", tested
    assert "1 passed" in tested["summary"]
    assert venv_marker.exists()

    # `venv` is honored too; a project without one keeps Rush's interpreter.
    other = _pytest_project(tmp_path / "other")
    other_python = _python_shim(other / "venv" / "bin" / "python", venv_marker)
    assert project_python(other) == str(other_python)
    bare = _pytest_project(tmp_path / "bare")
    assert project_python(bare) == REAL_PYTHON

    # Frozen, the project venv still wins over the active virtualenv and PATH.
    marker = _frozen_rush(monkeypatch, tmp_path)
    _path_bin(monkeypatch, tmp_path, python=True)
    active = _python_shim(tmp_path / "active" / "bin" / "python", venv_marker)
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "active"))
    assert project_python(project) == str(venv_python)
    # ...and the active virtualenv wins over python3 on PATH.
    assert project_python(bare) == str(active)
    assert not marker.exists()


def test_no_python_available_is_a_clear_prerequisite_result(
    monkeypatch, tmp_path: Path
) -> None:
    from rush.runtime.project_python import PYTHON_PREREQUISITE, project_python

    marker = _frozen_rush(monkeypatch, tmp_path)
    _path_bin(monkeypatch, tmp_path, python=False)
    project = _pytest_project(tmp_path / "project")
    assert project_python(project) is None

    tested = TestTool().run(project, permissions=BUILD)
    assert tested["status"] == "skipped", tested
    assert PYTHON_PREREQUISITE in tested["summary"]
    assert "exit 2" not in tested["summary"]

    healed = TestHealer(project_root=project).diagnose_and_heal(
        "test_demo.py", permissions=ExecutionPermissions(slow=True, artifact_write=True)
    )
    assert healed["status"] == "skipped", healed
    assert PYTHON_PREREQUISITE in healed["summary"]

    (project / "change.diff").write_text("", encoding="utf-8")
    patched = PatchApplyTool().run(project, patch_file=Path("change.diff"))
    assert patched["status"] == "skipped", patched
    assert PYTHON_PREREQUISITE in patched["summary"]

    target = project / "test_demo.py"
    for result in (
        ColdStartTool().run(target, dynamic=True, permissions=SLOW),
        MemProfileTool().run(target, dynamic=True, permissions=SLOW),
    ):
        assert result["status"] == "skipped", result
        assert PYTHON_PREREQUISITE in result["summary"]

    (project / "corpus").mkdir()
    (project / "harness.py").write_text("print('clean')\n", encoding="utf-8")
    monkeypatch.setattr(fuzz_mod, "atheris_available", lambda _python: True)
    fuzzed = FuzzTool().run(
        project,
        config={"options": {"harness": "harness.py", "corpus": "corpus"}},
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    assert fuzzed["status"] == "skipped", fuzzed
    assert PYTHON_PREREQUISITE in fuzzed["summary"]

    assert EngineSupportPolicy.load().discover_engine("onnxruntime") is None
    assert not marker.exists()


class _GateLaunched(Exception):
    pass


def test_frozen_windows_gate_uses_the_rush_entry(monkeypatch, tmp_path: Path) -> None:
    import rush.runtime.subprocesses as subprocesses_mod
    from rush import entry

    fake_rush = str(tmp_path / "rush.exe")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(
        sys.modules, "msvcrt", types.SimpleNamespace(get_osfhandle=lambda fd: 4242)
    )
    monkeypatch.setattr(subprocess, "STARTUPINFO", types.SimpleNamespace, raising=False)
    launched: list[list[str]] = []

    def recording_popen(argv, **kwargs):
        launched.append(list(argv))
        raise _GateLaunched

    monkeypatch.setattr(subprocess, "Popen", recording_popen)

    def launch() -> list[str]:
        with pytest.raises(_GateLaunched):
            subprocesses_mod._launch_gated_process_windows(
                ["engine", "--flag"],
                popen_kwargs={},
                env={},
                owner_instance_id="owner",
                run_id="run",
            )
        return launched.pop()

    # From source the gate stays a `python -c` script.
    source_argv = launch()
    assert source_argv[1] == "-c"
    assert source_argv[3:] == ["4242", "engine", "--flag"]

    # Frozen, rush.exe has no `-c`: the gate is rush's own hidden entry.
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", fake_rush)
    frozen_argv = launch()
    assert frozen_argv == [
        fake_rush,
        "__rush_windows_gate__",
        "4242",
        "engine",
        "--flag",
    ]
    assert "-c" not in frozen_argv

    # The frozen entry dispatches that argument to the gate function.
    gate_calls: list[list[str]] = []

    def recording_gate(argv: list[str]) -> int:
        gate_calls.append(list(argv))
        return 7

    monkeypatch.setattr(subprocesses_mod, "windows_gate", recording_gate)
    monkeypatch.setattr(
        sys, "argv", [fake_rush, "__rush_windows_gate__", "4242", "engine"]
    )
    with pytest.raises(SystemExit) as exited:
        entry.main()
    assert exited.value.code == 7
    assert gate_calls == [["4242", "engine"]]


def test_windows_gate_function_matches_the_gate_script(
    monkeypatch, tmp_path: Path
) -> None:
    """The gate function runs exactly `_WINDOWS_GATE_SCRIPT`'s logic: a released
    gate runs the real argv and returns its exit code; EOF exits 1 unlaunched."""
    from rush.runtime.subprocesses import windows_gate

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(
        sys.modules, "msvcrt", types.SimpleNamespace(open_osfhandle=lambda h, _f: h)
    )
    marker = tmp_path / "engine-ran"
    child = [
        REAL_PYTHON,
        "-c",
        f"open({str(marker)!r}, 'w').close(); raise SystemExit(3)",
    ]

    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"\n")
    os.close(write_fd)
    assert windows_gate([str(read_fd), *child]) == 3
    assert marker.exists()
    marker.unlink()

    read_fd, write_fd = os.pipe()
    os.close(write_fd)
    assert windows_gate([str(read_fd), *child]) == 1
    assert not marker.exists()


def _trusted_plugin(tmp_path: Path, repo_root: Path):
    from rush.plugins.closure import build_plugin_closure
    from rush.plugins.executor import HardenedPluginExecutor
    from rush.plugins.loader import PluginSpec
    from rush.plugins.snapshot_store import PluginSnapshotStore
    from rush.plugins.trust_store import PluginTrustStore

    plugin_dir = repo_root / "plugins" / "demo"
    plugin_dir.mkdir(parents=True)
    main_py = plugin_dir / "main.py"
    main_py.write_text(
        "import json\nprint(json.dumps({'status': 'ok', 'summary': 'ran'}))\n",
        encoding="utf-8",
    )
    command = ["python", "main.py"]
    closure = build_plugin_closure(
        plugin_root=plugin_dir,
        entrypoint=main_py,
        config={"name": "demo", "command": command},
        plugin_name="demo",
    )
    snapshot_store = PluginSnapshotStore(snapshots_root=tmp_path / "home" / "snaps")
    snapshot_dir = snapshot_store.materialize_snapshot(
        closure=closure, plugin_root=plugin_dir
    )
    trust_store = PluginTrustStore(
        repo_root=repo_root, ledger_path=tmp_path / "home" / "ledger.json"
    )
    trust_store.grant_trust("demo", closure.closure_digest, snapshot_dir)
    executor = HardenedPluginExecutor(
        repo_root=repo_root, trust_store=trust_store, snapshot_store=snapshot_store
    )
    spec = PluginSpec(
        name="demo", executable_path=main_py, command=command, closure=closure
    )
    return executor, spec


def test_plugin_python_uses_the_project_interpreter(
    monkeypatch, tmp_path: Path
) -> None:
    from rush.runtime.project_python import PYTHON_PREREQUISITE

    marker = _frozen_rush(monkeypatch, tmp_path)
    _path_bin(monkeypatch, tmp_path, python=False)

    # The project's own venv python runs a `python` plugin command.
    project = _pytest_project(tmp_path / "project")
    venv_marker = tmp_path / "venv-python-ran"
    _python_shim(project / ".venv" / "bin" / "python", venv_marker)
    executor, spec = _trusted_plugin(tmp_path / "plugin-a", project)
    result = executor.execute(spec, [project / "test_demo.py"])
    assert result.status == "ok", result
    assert result.summary == "ran"
    assert venv_marker.exists()

    # No interpreter at all: the named prerequisite, never `rush main.py`.
    bare = _pytest_project(tmp_path / "bare")
    executor, spec = _trusted_plugin(tmp_path / "plugin-b", bare)
    result = executor.execute(spec, [bare / "test_demo.py"])
    assert result.status == "skipped", result
    assert PYTHON_PREREQUISITE in result.summary

    assert not marker.exists(), marker.read_text(encoding="utf-8")


def test_atheris_probe_asks_the_harness_interpreter(
    monkeypatch, tmp_path: Path
) -> None:
    probes = tmp_path / "probes"
    with_atheris = _script(
        tmp_path / "with" / "python",
        f'echo "$@" >> "{probes}"\n'
        'case "$2" in *atheris*) exit 0;; esac\n'
        f'exec "{REAL_PYTHON}" "$@"\n',
    )
    without_atheris = _script(
        tmp_path / "without" / "python",
        f'echo "$@" >> "{probes}"\nexit 1\n',
    )
    assert fuzz_mod.atheris_available(str(with_atheris)) is True
    assert fuzz_mod.atheris_available(str(without_atheris)) is False
    probe_lines = probes.read_text(encoding="utf-8").splitlines()
    assert len(probe_lines) == 2
    assert all(line.startswith("-c ") for line in probe_lines)
    assert all("find_spec('atheris')" in line for line in probe_lines)

    # Rush's own interpreter claiming atheris does not matter...
    real_find_spec = importlib.util.find_spec

    def rush_has_atheris(name, *args, **kwargs):
        if name == "atheris":
            return types.SimpleNamespace(name="atheris")
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", rush_has_atheris)
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    options = {"options": {"harness": "harness.py", "corpus": "corpus"}}
    perms = ExecutionPermissions(build=True, slow=True, artifact_write=True)

    lacking = _pytest_project(tmp_path / "lacking")
    (lacking / "corpus").mkdir()
    (lacking / "harness.py").write_text("print('clean')\n", encoding="utf-8")
    _script(lacking / ".venv" / "bin" / "python", "exit 1\n")
    skipped = FuzzTool().run(lacking, config=options, permissions=perms)
    assert skipped["status"] == "skipped", skipped
    assert "atheris module not available" in skipped["summary"]

    # ...and the harness interpreter having it runs the harness.
    monkeypatch.setattr(importlib.util, "find_spec", real_find_spec)
    having = _pytest_project(tmp_path / "having")
    (having / "corpus").mkdir()
    (having / "corpus" / "seed").write_bytes(b"SAFE")
    (having / "harness.py").write_text("print('clean')\n", encoding="utf-8")
    harness_python = _script(
        having / ".venv" / "bin" / "python",
        f'case "$2" in *atheris*) exit 0;; esac\nexec "{REAL_PYTHON}" "$@"\n',
    )
    argvs: list[list[str]] = []
    real_run = fuzz_mod.run_subprocess

    def recording_run(argv, **kwargs):
        argvs.append(list(argv))
        return real_run(argv, **kwargs)

    monkeypatch.setattr(fuzz_mod, "run_subprocess", recording_run)
    ran = FuzzTool().run(having, config=options, permissions=perms)
    assert "atheris module not available" not in ran["summary"], ran
    assert [argv[0] for argv in argvs] == [str(harness_python)]


def test_atheris_version_reads_the_harness_interpreter(
    monkeypatch, tmp_path: Path
) -> None:
    """The reported engine version comes from the harness interpreter's
    metadata, never Rush's own -- they can differ (frozen Rush has none)."""
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    project = _pytest_project(tmp_path / "having")
    (project / "corpus").mkdir()
    (project / "corpus" / "seed").write_bytes(b"SAFE")
    (project / "harness.py").write_text("print('clean')\n", encoding="utf-8")
    _script(
        project / ".venv" / "bin" / "python",
        'case "$2" in\n'
        "  *find_spec*) exit 0 ;;\n"
        '  *importlib.metadata*) echo "9.9.9-harness"; exit 0 ;;\n'
        "esac\n"
        f'exec "{REAL_PYTHON}" "$@"\n',
    )

    def fake_run(argv, *, cwd=None, timeout=120, **_kwargs):
        return subprocess.CompletedProcess(
            argv, 0, stdout="", stderr="stat::number_of_executed_units: 3\n"
        )

    monkeypatch.setattr(fuzz_mod, "run_subprocess", fake_run)
    options = {"options": {"harness": "harness.py", "corpus": "corpus"}}
    perms = ExecutionPermissions(build=True, slow=True, artifact_write=True)
    result = FuzzTool().run(project, config=options, permissions=perms)
    assert result["status"] == "ok", result
    assert result["engine_version"] == "9.9.9-harness"
    try:
        rush_own_version = importlib.metadata.version("atheris")
    except importlib.metadata.PackageNotFoundError:
        rush_own_version = None
    assert result["engine_version"] != rush_own_version
