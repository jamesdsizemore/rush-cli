"""A frozen (PyInstaller) Rush's `sys.executable` is the rush binary itself,
never a Python. Every child that runs project code must run a real project
interpreter: the project's own .venv/venv python, else the active virtualenv's
python, else `python3`/`python` on PATH -- and name the missing prerequisite
when none exists instead of running `rush -m pytest` into `exit 2`."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

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
    monkeypatch.setattr(fuzz_mod, "atheris_available", lambda: True)
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
    monkeypatch.setattr(fuzz_mod, "atheris_available", lambda: True)
    fuzzed = FuzzTool().run(
        project,
        config={"options": {"harness": "harness.py", "corpus": "corpus"}},
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    assert fuzzed["status"] == "skipped", fuzzed
    assert PYTHON_PREREQUISITE in fuzzed["summary"]

    assert EngineSupportPolicy.load().discover_engine("onnxruntime") is None
    assert not marker.exists()
