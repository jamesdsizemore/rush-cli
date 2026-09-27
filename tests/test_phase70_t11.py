"""Phase 70 T11 tests: analyze against the project environment safely.

RED-only. T11 is not implemented yet: `rush.runtime.binaries` has no
`select_analysis_environment`/`AnalysisEnvironment`, and
`TypecheckTool.run`/`__call__` accept no `environment`/`allow_build`/
`allow_cache_write` kwargs. Every case below fails for that reason --
either an `AttributeError`/`TypeError` against the not-yet-existing API,
a `KeyError` against a not-yet-existing `ToolResult` field, or a real
behavioral mismatch against the current implementation that T11 must
fix (identity-keyed caches, PATH-scoped executable trust). Two cases are
keep-green guards against already-correct Phase 65 manifest behavior
that T11 must preserve.

Binding design: .scratch/phase-70-design-gate/W2-T9-T17.md ## T11
Plan packet: docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md #T11
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


def _fake_venv(tmp_path: Path, name: str = "proj") -> Path:
    """A minimal on-disk venv layout: .venv/{bin,Scripts}/python + pyvenv.cfg.

    The interpreter is a regular file directly inside the venv (not a
    symlink), which S11.1 accepts without walking a symlink chain.
    """
    project = tmp_path / name
    venv_dir = project / ".venv"
    bin_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
    bin_dir.mkdir(parents=True)
    (venv_dir / "pyvenv.cfg").write_text(f"home = {sys.prefix}\n")
    interpreter = bin_dir / ("python.exe" if os.name == "nt" else "python")
    interpreter.write_text("#!/bin/sh\necho fake-interpreter\n")
    interpreter.chmod(0o755)
    return project


def _real_dependency_project(tmp_path: Path) -> Path:
    """A project with a real (offline) venv holding a dependency importable
    only there -- no pip, no network: the module is dropped directly into
    site-packages."""
    project = tmp_path / "realproj"
    project.mkdir()
    venv_dir = project / ".venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv_dir)],
        check=True,
        timeout=60,
    )
    site_packages = next(venv_dir.rglob("site-packages"))
    # A typed package (PEP 561), so mypy follows it under any cwd's config.
    (site_packages / "onlyinvenv").mkdir()
    (site_packages / "onlyinvenv" / "__init__.py").write_text("VALUE: int = 1\n")
    (site_packages / "onlyinvenv" / "py.typed").write_text("")
    (project / "consumer.py").write_text(
        "import onlyinvenv\n\nVALUE2 = onlyinvenv.VALUE\n"
    )
    return project


def _remove_venv(project: Path) -> None:
    shutil.rmtree(project / ".venv")


def _invalidate_pyvenv_cfg(project: Path) -> None:
    (project / ".venv" / "pyvenv.cfg").write_text("garbage, not key = value\n")


def _tamper_symlink_outside_home(project: Path) -> None:
    bin_dir = project / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    interpreter = bin_dir / ("python.exe" if os.name == "nt" else "python")
    interpreter.unlink()
    outside = project.parent / "evil"
    outside.write_text("#!/bin/sh\necho evil\n")
    outside.chmod(0o755)
    interpreter.symlink_to(outside)


def _remove_interpreter(project: Path) -> None:
    bin_dir = project / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    interpreter = bin_dir / ("python.exe" if os.name == "nt" else "python")
    interpreter.unlink()


@pytest.fixture
def granted_build():
    from rush.permissions import ExecutionPermissions

    return ExecutionPermissions(build=True)


@pytest.fixture
def spawn_spy(monkeypatch) -> list[list[str]]:
    """Record every child process at the `subprocess` layer itself.

    Engines bind `run_subprocess` at import, so a spy on
    `rush.runtime.subprocesses.run_subprocess` alone misses their spawns;
    `subprocess.Popen` (which `subprocess.run` also uses) sees all of them.
    Recording only: every call still delegates to the real implementation.
    """
    spawned: list[list[str]] = []
    real_popen = subprocess.Popen
    real_run = subprocess.run

    def _argv(args) -> list[str]:
        return (
            [str(part) for part in args]
            if isinstance(args, (list, tuple))
            else [str(args)]
        )

    class RecordingPopen(real_popen):
        def __init__(self, args, *rest, **kwargs):
            spawned.append(_argv(args))
            super().__init__(args, *rest, **kwargs)

    def recording_run(args, *rest, **kwargs):
        spawned.append(_argv(args))
        return real_run(args, *rest, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", RecordingPopen)
    monkeypatch.setattr(subprocess, "run", recording_run)
    return spawned


# --- S11.1 / S11.2: TypecheckTool environment kwargs (missing today) ------


def test_t11_project_environment_and_trust_project_dependency_with_allow_build(
    tmp_path,
) -> None:
    """S11.1: real mypy against a fixture-venv-only dependency, with
    --environment project --allow-build, resolves clean; the entry
    records the interpreter and its digest."""
    from rush.tools.typecheck import TypecheckTool

    project = _real_dependency_project(tmp_path)

    result = TypecheckTool().run(project, environment="project", allow_build=True)

    assert result["analysis_environment"]["mode"] == "project"
    assert result["analysis_environment"]["interpreter_sha256"]
    findings_messages = " ".join(f["message"] for f in result["findings"])
    assert "onlyinvenv" not in findings_messages


def test_t11_project_environment_and_trust_default_without_build_is_isolated_with_import_error(
    tmp_path,
) -> None:
    """S11.1/S11.2: default mode with no allow_build grant falls back to
    isolated, keeping the real (now-visible) import diagnostic."""
    from rush.tools.typecheck import TypecheckTool

    project = _real_dependency_project(tmp_path)

    result = TypecheckTool().run(project)

    assert result["analysis_environment"]["mode"] == "isolated"
    assert (
        result["analysis_environment"]["cause"]
        == "project_environment_requires_allow_build"
    )
    findings_messages = " ".join(f["message"] for f in result["findings"])
    assert "onlyinvenv" in findings_messages


def test_t11_project_environment_and_trust_explicit_project_without_grant_denied_zero_spawns(
    tmp_path, monkeypatch, spawn_spy
) -> None:
    """S11.3: explicit --environment project without the grant skips python
    engines with 'requires permission: --allow-build' and spawns nothing."""
    from rush.tools.typecheck import TypecheckTool

    (tmp_path / "a.py").write_text("x = 1\n")
    calls: list[tuple] = []
    monkeypatch.setattr(
        "rush.engines.mypy.run_subprocess",
        lambda *a, **k: calls.append((a, k)),
    )

    result = TypecheckTool().run(tmp_path, environment="project", allow_build=False)

    assert spawn_spy == []
    assert calls == []
    assert result["status"] == "skipped"
    assert "--allow-build" in result["summary"]


def test_t11_project_environment_and_trust_explicit_isolated_reports_requested_cause(
    tmp_path,
) -> None:
    """S11.4: explicit --environment isolated reports cause 'requested'."""
    from rush.tools.typecheck import TypecheckTool

    (tmp_path / "a.py").write_text("x = 1\n")

    result = TypecheckTool().run(tmp_path, environment="isolated")

    assert result["analysis_environment"]["mode"] == "isolated"
    assert result["analysis_environment"]["cause"] == "requested"


def test_t11_project_environment_and_trust_missing_engine_executable_gives_skipped(
    tmp_path, monkeypatch
) -> None:
    """S11.5-adjacent: with no engine executable at all, typecheck is
    skipped, even when an environment is explicitly requested."""
    from rush.tools.typecheck import TypecheckTool

    (tmp_path / "a.py").write_text("x = 1\n")
    monkeypatch.setattr("rush.tools.common.resolve_binary", lambda binary: None)

    result = TypecheckTool().run(tmp_path, environment="isolated")

    assert result["status"] == "skipped"


def test_t11_project_environment_and_trust_ownership_preserved_in_project_mode(
    tmp_path, monkeypatch
) -> None:
    """Ownership: owner_instance_id/run_id still reach run_subprocess in the
    new environment-aware call path (existing
    test_subprocess_contract.py:900-910 style)."""
    from rush.runtime import subprocesses
    from rush.tools.typecheck import TypecheckTool

    project = _fake_venv(tmp_path)
    (project / "a.py").write_text("x = 1\n")
    observed: list[tuple[str | None, str | None] | None] = []

    def spy(argv, **kwargs):
        observed.append(subprocesses._OWNED_EXECUTION.get())
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr("rush.engines.mypy.run_subprocess", spy)

    with subprocesses.owned_execution_scope("owner-t11", "run-t11"):
        TypecheckTool().run(project, environment="project", allow_build=True)

    assert ("owner-t11", "run-t11") in observed


# --- S11.5: binaries.select_analysis_environment interpreter validation ---


@pytest.mark.parametrize(
    ("tamper", "expected_cause"),
    [
        (_remove_venv, "venv_missing"),
        (_invalidate_pyvenv_cfg, "pyvenv_cfg_invalid"),
        (_tamper_symlink_outside_home, "interpreter_outside_home"),
        (_remove_interpreter, "interpreter_missing"),
    ],
    ids=[
        "venv_missing",
        "pyvenv_cfg_invalid",
        "interpreter_outside_home",
        "interpreter_missing",
    ],
)
def test_t11_project_environment_and_trust_invalid_venv_never_claims_project_success(
    tmp_path, granted_build, tamper, expected_cause
) -> None:
    """S11.5: a tampered/moved/missing venv or invalid config gives an
    isolated fallback with a precise cause, never a false project success."""
    from rush.runtime import binaries

    project = _fake_venv(tmp_path)
    tamper(project)

    env = binaries.select_analysis_environment(
        root=project, mode="project", granted=granted_build
    )

    assert env.mode != "project"
    assert env.cause == expected_cause


def test_t11_project_environment_and_trust_tampered_interpreter_never_executed(
    tmp_path, granted_build, monkeypatch, spawn_spy
) -> None:
    """S11.5: a tampered interpreter is never spawned, even to probe it."""
    from rush.runtime import binaries

    project = _fake_venv(tmp_path)
    _tamper_symlink_outside_home(project)
    spawned: list[list[str]] = []
    monkeypatch.setattr(
        "rush.runtime.subprocesses.run_subprocess",
        lambda argv, **k: spawned.append(argv),
    )

    binaries.select_analysis_environment(
        root=project, mode="project", granted=granted_build
    )

    assert spawn_spy == []
    assert not any("evil" in str(part) for argv in spawned for part in argv)


def test_t11_project_environment_and_trust_foreign_cwd_config_does_not_change_selection(
    tmp_path, granted_build, monkeypatch
) -> None:
    """A strict mypy.ini in the process cwd must not change interpreter
    selection -- it's a project-tree decision, not a cwd artifact."""
    from rush.runtime import binaries

    project = _fake_venv(tmp_path)
    foreign_cwd = tmp_path / "elsewhere"
    foreign_cwd.mkdir()
    (foreign_cwd / "mypy.ini").write_text("[mypy]\nstrict = True\n")
    monkeypatch.chdir(foreign_cwd)

    env = binaries.select_analysis_environment(
        root=project, mode="project", granted=granted_build
    )

    assert env.mode == "project"
    assert Path(env.environment_root) == project / ".venv"


def test_t11_project_environment_and_trust_windows_scripts_path_construction(
    tmp_path, granted_build, monkeypatch
) -> None:
    """S11.6 Windows path: Scripts\\python.exe construction, exercised as a
    pure unit test (no real Windows platform required)."""
    from rush.runtime import binaries

    project = tmp_path / "winproj"
    venv_dir = project / ".venv"
    scripts_dir = venv_dir / "Scripts"
    scripts_dir.mkdir(parents=True)
    (venv_dir / "pyvenv.cfg").write_text(f"home = {sys.prefix}\n")
    (scripts_dir / "python.exe").write_text("fake\n")
    monkeypatch.setattr(os, "name", "nt")

    env = binaries.select_analysis_environment(
        root=project, mode="project", granted=granted_build
    )

    assert env.mode == "project"
    assert env.interpreter.endswith("python.exe")


# --- S11.7: identity-keyed caches (real bug against current code) --------


def test_t11_project_environment_and_trust_engine_version_cache_invalidates_on_identity_change(
    tmp_path, monkeypatch
) -> None:
    """S11.7: replacing the engine binary's bytes at an unchanged path must
    invalidate the cached version -- today's cache is keyed by path only."""
    from rush.engines.base import Engine
    from rush.engines.mypy import MypyEngine

    Engine._cached_versions.clear()
    binary = tmp_path / "fakebin"
    binary.write_text("#!/bin/sh\necho 1.0.0\n")
    binary.chmod(0o755)
    monkeypatch.setattr("rush.engines.base.resolve_binary", lambda b: str(binary))

    engine = MypyEngine()
    first = engine.version()
    time.sleep(0.01)
    binary.write_text("#!/bin/sh\necho 2.0.0\n")
    binary.chmod(0o755)
    second = engine.version()

    assert first == "1.0.0"
    assert second == "2.0.0", (
        "Engine._cached_versions is keyed by path only; replacing the "
        "binary's bytes at an unchanged path must invalidate the cache "
        "(S11.7), but the stale version was returned"
    )


# --- S11.6 / R11.3: PATH trust for engine executable selection -----------


def test_t11_project_environment_and_trust_path_never_trusts_project_scoped_bin_without_manifest(
    tmp_path, monkeypatch
) -> None:
    """S11.6/R11.3: a project's own node_modules/.bin placed first on PATH
    is never trusted absent a verified manifest."""
    from rush.runtime import binaries

    binaries.clear_binary_cache()
    project_root = tmp_path / "proj"
    poisoned_bin = project_root / "node_modules" / ".bin"
    poisoned_bin.mkdir(parents=True)
    fake_tsc = poisoned_bin / "tsc"
    fake_tsc.write_text("#!/bin/sh\necho poisoned\n")
    fake_tsc.chmod(0o755)
    monkeypatch.setenv(
        "PATH", f"{poisoned_bin}{os.pathsep}{os.environ.get('PATH', '')}"
    )

    result = binaries.resolve_binary("tsc", engine_id="tsc", project_root=project_root)

    assert result is None or Path(result).resolve() != fake_tsc.resolve(), (
        "resolve_binary selected the project-scoped, PATH-poisoned tsc "
        "with no verified manifest backing it"
    )


def test_t11_project_environment_and_trust_manifest_verified_binary_selected(
    tmp_path,
) -> None:
    """Keep-green: an already-verified manifest wins over PATH (existing
    Phase 65 behavior T11 must preserve)."""
    from rush.runtime import binaries

    binaries.clear_binary_cache()
    binaries.clear_manifest_cache()
    project_root = tmp_path / "proj"
    project_root.mkdir()
    provisioned = tmp_path / "provisioned" / "tsc"
    provisioned.parent.mkdir()
    provisioned.write_text("#!/bin/sh\necho verified\n")
    provisioned.chmod(0o755)

    manifest = binaries.ProvisionManifest(
        schema_version=binaries.MANIFEST_SCHEMA_VERSION,
        engine_id="tsc",
        package_id="tsc",
        version="1.0.0",
        source="test",
        manager="test",
        executable=str(provisioned),
        executable_sha256=binaries.compute_file_sha256(provisioned),
        os_name=os.name,
        arch="test",
        project_id="proj",
        project_root=str(project_root.resolve()),
        runtime_identity="test",
        plan_id="test",
        created_at="2026-01-01T00:00:00Z",
    )
    manifest_path = binaries.write_manifest(project_root / ".rush" / "tsc", manifest)
    (project_root / ".rush" / "toolchains.json").write_text(
        json.dumps({"tsc": {"manifest": str(manifest_path)}})
    )

    result = binaries.resolve_binary("tsc", engine_id="tsc", project_root=project_root)

    assert result == str(provisioned)


def test_t11_project_environment_and_trust_tampered_manifest_falls_back(
    tmp_path, monkeypatch
) -> None:
    """Keep-green: a manifest whose executable hash no longer matches falls
    back to the normal PATH policy instead of trusting stale bytes."""
    from rush.runtime import binaries

    binaries.clear_binary_cache()
    binaries.clear_manifest_cache()
    project_root = tmp_path / "proj"
    project_root.mkdir()
    provisioned = tmp_path / "provisioned2" / "tsc"
    provisioned.parent.mkdir()
    provisioned.write_text("#!/bin/sh\necho verified\n")
    provisioned.chmod(0o755)
    manifest = binaries.ProvisionManifest(
        schema_version=binaries.MANIFEST_SCHEMA_VERSION,
        engine_id="tsc",
        package_id="tsc",
        version="1.0.0",
        source="test",
        manager="test",
        executable=str(provisioned),
        executable_sha256="0" * 64,
        os_name=os.name,
        arch="test",
        project_id="proj",
        project_root=str(project_root.resolve()),
        runtime_identity="test",
        plan_id="test",
        created_at="2026-01-01T00:00:00Z",
    )
    manifest_path = binaries.write_manifest(project_root / ".rush" / "tsc", manifest)
    (project_root / ".rush" / "toolchains.json").write_text(
        json.dumps({"tsc": {"manifest": str(manifest_path)}})
    )
    monkeypatch.setattr(
        binaries, "_resolve_binary_cached", lambda binary: "/fallback/tsc"
    )

    result = binaries.resolve_binary("tsc", engine_id="tsc", project_root=project_root)

    assert result == "/fallback/tsc"


# --- Design-gate corrections: Homebrew chains, dispatch scope, caches ------


def _homebrew_layout(tmp_path: Path) -> tuple[Path, Path]:
    """opt -> Cellar -> Frameworks, as Homebrew lays out python@3.12.

    Returns (home, real interpreter). `realpath(home)` is the Cellar keg's
    `bin`, which does NOT contain the Frameworks target.
    """
    keg = tmp_path / "brew" / "Cellar" / "python@3.12" / "3.12.13_4"
    framework_bin = (
        keg / "Frameworks" / "Python.framework" / "Versions" / "3.12" / "bin"
    )
    framework_bin.mkdir(parents=True)
    real = framework_bin / "python3.12"
    real.write_text("#!/bin/sh\necho framework-python\n")
    real.chmod(0o755)
    (keg / "bin").mkdir()
    (keg / "bin" / "python3.12").symlink_to(
        "../Frameworks/Python.framework/Versions/3.12/bin/python3.12"
    )
    opt = tmp_path / "brew" / "opt"
    opt.mkdir()
    (opt / "python@3.12").symlink_to("../Cellar/python@3.12/3.12.13_4")
    return opt / "python@3.12" / "bin", real


def _brew_venv(tmp_path: Path, home: Path, first_hop: Path) -> Path:
    project = tmp_path / "brewproj"
    bin_dir = project / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    (project / ".venv" / "pyvenv.cfg").write_text(f"home = {home}\n")
    (bin_dir / "python3.12").symlink_to(first_hop)
    (bin_dir / "python").symlink_to("python3.12")
    return project


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink chain")
def test_t11_project_environment_and_trust_homebrew_framework_chain(
    tmp_path, granted_build
) -> None:
    """A venv whose python resolves opt -> Cellar -> Frameworks (outside
    realpath(home)) is accepted, recording the final target and its digest."""
    from rush.runtime import binaries

    home, real = _homebrew_layout(tmp_path)
    assert not str(real.resolve()).startswith(str(home.resolve()))
    project = _brew_venv(tmp_path, home, home / "python3.12")

    env = binaries.select_analysis_environment(
        root=project, mode="project", granted=granted_build
    )

    assert env.mode == "project", env
    assert env.interpreter == str(project / ".venv" / "bin" / "python")
    assert env.interpreter_target == str(real.resolve())
    assert env.interpreter_sha256 == binaries.compute_file_sha256(real)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink chain")
def test_t11_project_environment_and_trust_homebrew_same_basename_elsewhere_rejected(
    tmp_path, granted_build
) -> None:
    """Relinking to a same-named interpreter outside what `home` provides is
    still tampering, even in a Homebrew-shaped venv."""
    from rush.runtime import binaries

    home, _real = _homebrew_layout(tmp_path)
    evil = tmp_path / "evil" / "python3.12"
    evil.parent.mkdir()
    evil.write_text("#!/bin/sh\necho evil\n")
    evil.chmod(0o755)
    project = _brew_venv(tmp_path, home, evil)

    env = binaries.select_analysis_environment(
        root=project, mode="project", granted=granted_build
    )

    assert env.mode == "isolated"
    assert env.cause == "interpreter_outside_home"


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink chain")
def test_t11_project_environment_and_trust_symlink_loop_rejected(
    tmp_path, granted_build
) -> None:
    from rush.runtime import binaries

    project = _fake_venv(tmp_path)
    bin_dir = project / ".venv" / "bin"
    (bin_dir / "python").unlink()
    (bin_dir / "python").symlink_to("python-a")
    (bin_dir / "python-a").symlink_to("python")

    env = binaries.select_analysis_environment(
        root=project, mode="project", granted=granted_build
    )

    assert env.mode == "isolated"
    assert env.cause == "interpreter_symlink_loop"


def _write_tool(directory: Path, name: str = "tsc") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    tool = directory / name
    tool.write_text("#!/bin/sh\necho tool\n")
    tool.chmod(0o755)
    return tool


def _dispatch_tsc(monkeypatch, path: Path) -> list[tuple[list[str], object]]:
    """Run TscEngine through `run_engine`, capturing argv and ambient scope."""
    from rush.engines import tsc
    from rush.engines.tsc import TscEngine
    from rush.runtime import binaries
    from rush.tools import common

    seen: list[tuple[list[str], object]] = []

    def fake_run(argv, **_kwargs):
        seen.append((argv, binaries.current_analysis_scope()))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(tsc, "run_subprocess", fake_run)
    monkeypatch.setattr(TscEngine, "version", lambda _self: "5.0.0")
    # T12: tsc only spawns when there is a TypeScript file to analyze.
    path.mkdir(parents=True, exist_ok=True)
    (path / "main.ts").write_text("export const x = 1;\n")
    common.run_engine(TscEngine(), path, [], tool_name="typecheck")
    return seen


def test_t11_project_environment_and_trust_dispatch_never_selects_project_path_bin(
    tmp_path, monkeypatch
) -> None:
    """S11.6 through the real dispatch (not just `resolve_binary`): the
    engine's own argv never uses a project `node_modules/.bin` first on PATH."""
    from rush.runtime import binaries

    binaries.clear_binary_cache()
    project = tmp_path / "proj"
    poisoned = _write_tool(project / "node_modules" / ".bin")
    trusted = _write_tool(tmp_path / "trusted")
    monkeypatch.setenv(
        "PATH", os.pathsep.join([str(poisoned.parent), str(trusted.parent)])
    )

    seen = _dispatch_tsc(monkeypatch, project)

    assert seen, "tsc was not dispatched"
    assert seen[0][0][0] == str(trusted)


def test_t11_project_environment_and_trust_dispatch_prefers_verified_manifest(
    tmp_path, monkeypatch
) -> None:
    """A manifest-verified executable wins in the real dispatch, even when it
    lives inside the project; a project PATH entry never does."""
    from rush.runtime import binaries

    binaries.clear_binary_cache()
    binaries.clear_manifest_cache()
    project = (tmp_path / "proj").resolve()
    poisoned = _write_tool(project / "node_modules" / ".bin")
    provisioned = _write_tool(project / ".rush" / "toolchains" / "tsc-bin")
    manifest = binaries.ProvisionManifest(
        schema_version=binaries.MANIFEST_SCHEMA_VERSION,
        engine_id="tsc",
        package_id="typescript",
        version="5.0.0",
        source="test",
        manager="test",
        executable=str(provisioned),
        executable_sha256=binaries.compute_file_sha256(provisioned),
        os_name=os.name,
        arch="test",
        project_id="proj",
        project_root=str(project),
        runtime_identity="test",
        plan_id="test",
        created_at="2026-01-01T00:00:00Z",
    )
    manifest_path = binaries.write_manifest(project / ".rush" / "tsc", manifest)
    (project / ".rush" / "toolchains.json").write_text(
        json.dumps({"tsc": {"manifest": str(manifest_path)}})
    )
    monkeypatch.setenv("PATH", str(poisoned.parent))

    seen = _dispatch_tsc(monkeypatch, project)

    assert seen[0][0][0] == str(provisioned)


def test_t11_project_environment_and_trust_staged_scan_filters_logical_and_execution_roots(
    tmp_path, monkeypatch
) -> None:
    """Under a staged scan whose engine path lies inside the snapshot, the
    logical root is the original tree (not the temp snapshot) and both the
    original's and the snapshot's `node_modules/.bin` are excluded."""
    from rush.engines.staging import StagingContext, staging_scope
    from rush.runtime import binaries

    binaries.clear_binary_cache()
    original = (tmp_path / "orig").resolve()
    staged = (tmp_path / "staged").resolve()
    live_bin = _write_tool(original / "node_modules" / ".bin")
    staged_bin = _write_tool(staged / "node_modules" / ".bin")
    trusted = _write_tool(tmp_path / "trusted")
    monkeypatch.setenv(
        "PATH",
        os.pathsep.join(
            [str(staged_bin.parent), str(live_bin.parent), str(trusted.parent)]
        ),
    )

    with staging_scope(StagingContext(original_root=original, staged_root=staged)):
        seen = _dispatch_tsc(monkeypatch, staged)

    argv, scope = seen[0]
    assert argv[0] == str(trusted)
    assert scope.logical_root == original
    assert scope.execution_root == staged


def test_t11_project_environment_and_trust_resolution_cache_revalidates_identity(
    tmp_path, monkeypatch
) -> None:
    """S11.7: a cached executable path is re-lstat'ed on every hit; once the
    binary is gone the stale path is never returned."""
    from rush.runtime import binaries

    binaries.clear_binary_cache()
    tool = _write_tool(tmp_path / "bin", "rush-t11-probe-tool")
    monkeypatch.setenv("PATH", str(tool.parent))

    assert binaries.resolve_binary("rush-t11-probe-tool") == str(tool)
    tool.unlink()

    assert binaries.resolve_binary("rush-t11-probe-tool") is None


def test_t11_project_environment_and_trust_cli_and_mcp_expose_environment(
    tmp_path,
) -> None:
    """R11.6: only `rush typecheck` gains `--environment`; the MCP schema
    carries the enum and routes `allow_build` into the grant."""
    import inspect
    import typing

    from click.testing import CliRunner

    from rush.cli import cli
    from rush.invocation import InvocationExecutor
    from rush.mcp_support.tool_registry import make_tool_wrapper
    from rush.tools.typecheck import TypecheckTool

    (tmp_path / "a.py").write_text("x = 1\n")
    runner = CliRunner()
    ok = runner.invoke(
        cli, ["typecheck", str(tmp_path), "--environment", "isolated", "--json"]
    )
    bogus = runner.invoke(cli, ["typecheck", str(tmp_path), "--environment", "bogus"])
    lint_help = runner.invoke(cli, ["lint", "--help"])

    assert ok.exit_code in (0, 1), ok.output
    payload = json.loads(ok.output)
    environment = (
        payload.get("analysis_environment")
        or payload["extensions"]["analysis_environment"]
    )
    assert environment["cause"] == "requested"
    assert bogus.exit_code == 2
    assert "--environment" not in lint_help.output

    tool = TypecheckTool()
    executor = InvocationExecutor()
    executor.register(tool.name, tool.__call__)
    wrapper = make_tool_wrapper(tool, executor)
    annotation = inspect.signature(wrapper).parameters["environment"].annotation
    hints = typing.get_type_hints(TypecheckTool.__call__)
    assert "Literal['project', 'isolated']" in str(annotation)
    assert set(typing.get_args(typing.get_args(hints["environment"])[0])) == {
        "project",
        "isolated",
    }
    denied = wrapper(path=str(tmp_path), environment="project")
    assert denied["analysis_environment"]["mode"] == "denied"
    granted = wrapper(path=str(tmp_path), environment="project", allow_build=True)
    assert granted["analysis_environment"]["permission"] == "granted"


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell fixture")
def test_t11_project_environment_and_trust_exec_never_falls_back_to_project_path(
    tmp_path, monkeypatch, spawn_spy
) -> None:
    """A bare command the trusted policy cannot resolve inside a dispatch
    must not reach the OS PATH search (which would find the project's copy);
    outside any dispatch the unscoped behavior is unchanged."""
    from rush.runtime import binaries, subprocesses

    binaries.clear_binary_cache()
    project = tmp_path / "proj"
    only_in_project = _write_tool(project / "node_modules" / ".bin", "rush-t11-helper")
    monkeypatch.setenv("PATH", str(only_in_project.parent))

    with (
        binaries.analysis_scope(binaries.AnalysisScope(project)),
        pytest.raises(FileNotFoundError),
    ):
        subprocesses.run_subprocess(["rush-t11-helper"])
    assert spawn_spy == []

    unscoped = subprocesses.run_subprocess(["rush-t11-helper"])
    assert unscoped.returncode == 0


# --- pyrefly: pinned minimum, exact flags, runtime version gate -------------

PYREFLY_MINIMUM = "0.37.0"  # first release whose `check --help` has both flags


def test_t11_pyrefly_minimum_policy_and_flags_match_real_binary() -> None:
    """The pinned minimum and recorded flags are the ones the installed
    (dev-extra) pyrefly actually offers; it is installed, never optional."""
    from rush.engines import pyrefly
    from rush.runtime import binaries
    from rush.setup.engine_packages import ENGINE_PACKAGES

    assert ENGINE_PACKAGES["pyrefly"].version_policy == f"minimum:{PYREFLY_MINIMUM}"
    assert pyrefly.INTERPRETER_SELECTION_FLAGS == (
        "--python-interpreter-path",
        "--skip-interpreter-query",
    )
    binaries.clear_binary_cache()
    real = binaries.resolve_binary("pyrefly")
    assert real is not None, "pyrefly must be installed by `uv sync --extra dev`"
    help_text = subprocess.run(
        [real, "check", "--help"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    ).stdout
    for flag in (*pyrefly.INTERPRETER_SELECTION_FLAGS, "--output-format"):
        assert flag in help_text
    engine = pyrefly.PyreflyEngine()
    assert engine.support_problem() is None
    assert engine.supports_interpreter_selection()


def _fake_pyrefly(directory: Path, version: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    fake = directory / "pyrefly"
    fake.write_text(
        "#!/bin/sh\n"
        f'if [ "$1" = "--version" ]; then echo "pyrefly {version}"; exit 0; fi\n'
        'if [ "$2" = "--help" ]; then '
        'echo "--python-interpreter-path --skip-interpreter-query"; exit 0; fi\n'
        f"echo ran-check >> '{directory / 'checks.log'}'\n"
        "echo '{\"errors\": []}'\n"
    )
    fake.chmod(0o755)
    return fake


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell fixture")
def test_t11_pyrefly_below_minimum_is_engine_unsupported(tmp_path, monkeypatch) -> None:
    """Below the pinned minimum pyrefly never runs `check`; the result is an
    explicit engine-unsupported error, never a silent pass."""
    from rush.runtime import binaries
    from rush.tools import common
    from rush.tools.typecheck import TypecheckTool

    binaries.clear_binary_cache()
    fake = _fake_pyrefly(tmp_path / "oldbin", "0.36.2")
    monkeypatch.setattr(common, "_venv_scripts_dir", lambda: None)
    monkeypatch.setenv("PATH", str(fake.parent))
    project = tmp_path / "proj"
    project.mkdir()
    (project / "a.py").write_text("x = 1\n")

    result = TypecheckTool().run(project, environment="isolated")

    assert not (fake.parent / "checks.log").exists(), "old pyrefly ran check"
    assert result["status"] == "error"
    assert "engine-unsupported" in result["summary"]
    assert "0.36.2" in result["summary"] and PYREFLY_MINIMUM in result["summary"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell fixture")
def test_t11_pyrefly_at_minimum_runs(tmp_path, monkeypatch) -> None:
    from rush.runtime import binaries
    from rush.tools import common
    from rush.tools.typecheck import TypecheckTool

    binaries.clear_binary_cache()
    fake = _fake_pyrefly(tmp_path / "minbin", PYREFLY_MINIMUM)
    monkeypatch.setattr(common, "_venv_scripts_dir", lambda: None)
    monkeypatch.setenv("PATH", str(fake.parent))
    project = tmp_path / "proj"
    project.mkdir()
    (project / "a.py").write_text("x = 1\n")

    result = TypecheckTool().run(project, environment="isolated")

    assert (fake.parent / "checks.log").read_text().strip() == "ran-check"
    assert "engine-unsupported" not in result["summary"]


def test_t11_pyrefly_real_flags_isolated_vs_project(tmp_path, monkeypatch) -> None:
    """Real pyrefly: isolated (`--skip-interpreter-query`) cannot see the
    venv-only dependency; project (`--python-interpreter-path`) can. Output
    is parsed from stdout JSON and no stray output file is written."""
    from rush.runtime import binaries
    from rush.tools import typecheck as typecheck_module
    from rush.tools.typecheck import TypecheckTool

    binaries.clear_binary_cache()
    project = _real_dependency_project(tmp_path)
    monkeypatch.chdir(project)
    argvs: list[list[str]] = []
    real_run_engine = typecheck_module.run_engine

    def spy_run_engine(engine, path, args=None, **kwargs):
        argvs.append([engine.name, *(args or [])])
        return real_run_engine(engine, path, args, **kwargs)

    monkeypatch.setattr(typecheck_module, "run_engine", spy_run_engine)

    def pyrefly_messages(result) -> str:
        return " ".join(
            f["message"]
            for f in result["findings"]
            if str(f.get("rule", "")).startswith("pyrefly/")
        )

    isolated = TypecheckTool().run(project, environment="isolated")
    project_mode = TypecheckTool().run(project, environment="project", allow_build=True)

    pyrefly_argvs = [argv for argv in argvs if argv[0] == "pyrefly"]
    assert "--skip-interpreter-query" in pyrefly_argvs[0]
    assert "--python-interpreter-path" in pyrefly_argvs[1]
    assert "onlyinvenv" in pyrefly_messages(isolated)
    assert "onlyinvenv" not in pyrefly_messages(project_mode)
    assert not (project / "json").exists()


# --- S11.8: no installs or downloads as an analysis side effect ------------

_INSTALLERS = {"pip", "pip3", "uv", "uvx", "npm", "npx", "pnpm", "yarn", "curl", "wget"}


def _installer_invocations(argvs: list[list[str]]) -> list[list[str]]:
    flagged = []
    for argv in argvs:
        if not argv:
            continue
        program = os.path.basename(argv[0]).lower().removesuffix(".exe")
        tokens = {token.lower() for token in argv[1:]}
        if (
            program in _INSTALLERS
            or program.startswith("pip")
            or {"install", "download", "--install-types"} & tokens
            or ("-m" in tokens and {"pip", "ensurepip"} & tokens)
        ):
            flagged.append(argv)
    return flagged


@pytest.mark.parametrize(
    ("environment", "allow_build"),
    [
        (None, False),
        (None, True),
        ("isolated", False),
        ("project", False),
        ("project", True),
    ],
    ids=["default", "default-granted", "isolated", "project-denied", "project-granted"],
)
def test_t11_project_environment_and_trust_no_installs_or_downloads(
    tmp_path, monkeypatch, spawn_spy, environment, allow_build
) -> None:
    """S11.8: no mode installs or downloads anything. Every child argv (at the
    `subprocess` layer, `run_subprocess` and `run_engine`) is inspected, and
    any in-process network connection attempt is recorded and refused."""
    import socket
    import urllib.request

    from rush.runtime import subprocesses
    from rush.tools import typecheck as typecheck_module
    from rush.tools.typecheck import TypecheckTool

    project = _real_dependency_project(tmp_path)
    (project / "mypy.ini").write_text("[mypy]\ninstall_types = True\n")
    run_subprocess_argvs: list[list[str]] = []
    engine_argvs: list[list[str]] = []
    network: list[object] = []

    real_run_subprocess = subprocesses.run_subprocess

    def spy_run_subprocess(argv, **kwargs):
        run_subprocess_argvs.append(list(argv))
        return real_run_subprocess(argv, **kwargs)

    real_run_engine = typecheck_module.run_engine

    def spy_run_engine(engine, path, args=None, **kwargs):
        engine_argvs.append([engine.binary, *(args or [])])
        return real_run_engine(engine, path, args, **kwargs)

    def refuse_network(*args, **_kwargs):
        network.append(args)
        raise OSError("network disabled by T11 S11.8 test")

    for module in ("mypy", "pyrefly", "tsc", "base"):
        monkeypatch.setattr(f"rush.engines.{module}.run_subprocess", spy_run_subprocess)
    monkeypatch.setattr(subprocesses, "run_subprocess", spy_run_subprocess)
    monkeypatch.setattr(typecheck_module, "run_engine", spy_run_engine)
    monkeypatch.setattr(socket.socket, "connect", refuse_network)
    monkeypatch.setattr(socket, "create_connection", refuse_network)
    monkeypatch.setattr(urllib.request, "urlopen", refuse_network)

    TypecheckTool().run(project, environment=environment, allow_build=allow_build)

    all_argvs = spawn_spy + run_subprocess_argvs + engine_argvs
    assert _installer_invocations(all_argvs) == []
    assert network == []
    mypy_argvs = [argv for argv in engine_argvs if argv[0] == "mypy"]
    # The project config's `install_types = True` is overridden, not obeyed.
    assert all("--no-install-types" in argv for argv in mypy_argvs)
