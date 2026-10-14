"""Phase 70 T15 -- report actionable engine readiness.

Binding design: .scratch/phase-70-design-gate/W2-T9-T17.md, section "## T15".
Plan packet: docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md,
"#### T15 -- Report actionable engine readiness".

`build_engine_inventory(root, *, probe: bool)` does not exist yet in
`rush.tools.doctor` -- every case below fails against real, current source
(AttributeError: module has no attribute `build_engine_inventory`), which is
the correct RED reason for an unimplemented task. T11 (the resolver
`project_root=`/`engine_id=` keyword path) and T14 (`engine_packages`
versions) are named as T15 predecessors in the design's "Conflicts and
sequencing", but `rush.runtime.binaries.resolve_binary` already accepts
`engine_id=`/`project_root=` today (verified by reading `binaries.py`), so no
case here is RED-via-T11/T14 -- every failure is T15's own missing function.

Fixtures use temp dirs and a temp PATH only. No network calls.
"""

from __future__ import annotations

import os
import shlex
import stat
import sys
from pathlib import Path

import pytest

from rush.runtime import binaries as binaries_mod
from rush.setup.engine_packages import (
    ENGINE_PACKAGES,
    UnknownEngineError,
    resolve_engine_package,
)
from rush.tools import doctor as doctor_mod

pytestmark = pytest.mark.posix_only  # POSIX shebang fixtures


# --- fixtures ---------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_binary_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the resolver's venv-Scripts lookup off so only our fake PATH counts.

    `_resolve_binary_cached` consults `rush.tools.common._venv_scripts_dir`
    when that module is already imported (it is, transitively, by the time
    the suite runs), so both bindings must be patched -- `common` re-exports
    the function object by name at import time, it does not re-read
    `binaries` lazily.
    """
    monkeypatch.setattr(binaries_mod, "_venv_scripts_dir", lambda: None)
    common_mod = sys.modules.get("rush.tools.common")
    if common_mod is not None:
        monkeypatch.setattr(
            common_mod, "_venv_scripts_dir", lambda: None, raising=False
        )
    binaries_mod.clear_binary_cache()
    binaries_mod.clear_manifest_cache()
    yield
    binaries_mod.clear_binary_cache()
    binaries_mod.clear_manifest_cache()


def _empty_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # T11 (runtime/binaries.py) filters any PATH entry living inside the
    # project's logical root as project-scoped and untrusted. Every caller
    # here treats `tmp_path` as the project root (`_python_project` etc.
    # write markers directly into it), so this fixture directory must be a
    # sibling of `tmp_path`, not a child of it -- otherwise a "real, installed"
    # engine placed here would be excluded by T11 exactly like a shadow.
    empty_dir = tmp_path.with_name(tmp_path.name + "_bin")
    empty_dir.mkdir()
    monkeypatch.setenv("PATH", str(empty_dir))
    return empty_dir


def _fake_executable(directory: Path, name: str, version_output: str = "1.0.0") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    exe = directory / name
    exe.write_text(f"#!/bin/sh\necho {version_output}\n", encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return exe


def _python_project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    return tmp_path


def _ts_project(tmp_path: Path) -> Path:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
    return tmp_path


def _rust_project(tmp_path: Path) -> Path:
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    return tmp_path


# --- group: existence / signature -------------------------------------------


def test_build_engine_inventory_exists() -> None:
    """S15.2/§3: `build_engine_inventory(root, *, probe)` must exist on doctor.

    RED reason: T15 unimplemented -- doctor.py has no such attribute yet.
    """
    assert hasattr(doctor_mod, "build_engine_inventory")


# --- group: per-stack fixtures (S15.1, R15.1) --------------------------------


def test_python_only_all_required_engines_installed_gives_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _python_project(tmp_path)
    bin_dir = _empty_path(tmp_path, monkeypatch)
    for engine in ("ruff", "mypy", "pytest", "pip-audit", "aislop", "tach"):
        _fake_executable(bin_dir, engine)

    entries = doctor_mod.build_engine_inventory(root, probe=False)

    engines_found = {e["engine"] for e in entries}
    assert engines_found == {
        "ruff",
        "mypy",
        "pytest",
        "pip-audit",
        "aislop",
        "tach",
        "bandit",
    }
    for e in entries:
        if e["engine"] == "bandit":
            assert e["disposition"] == "unsupported"
            assert e["required"] is False
        else:
            assert e["disposition"] == "installed"
            assert e["required"] is True


def test_python_only_no_engines_installed_gives_warn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _python_project(tmp_path)
    _empty_path(tmp_path, monkeypatch)

    entries = doctor_mod.build_engine_inventory(root, probe=False)

    required = [e for e in entries if e["required"]]
    assert required, "python stack must have at least one required engine"
    assert all(e["disposition"] == "missing" for e in required)


def test_python_only_partial_engines_installed_gives_warn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _python_project(tmp_path)
    bin_dir = _empty_path(tmp_path, monkeypatch)
    _fake_executable(bin_dir, "ruff")

    entries = doctor_mod.build_engine_inventory(root, probe=False)

    by_engine = {e["engine"]: e for e in entries}
    assert by_engine["ruff"]["disposition"] == "installed"
    assert by_engine["mypy"]["disposition"] == "missing"


def test_typescript_only_all_suggested_engines_have_package_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _ts_project(tmp_path)
    bin_dir = _empty_path(tmp_path, monkeypatch)
    for engine in ("biome", "eslint", "prettier", "tsc"):
        _fake_executable(bin_dir, engine)

    entries = doctor_mod.build_engine_inventory(root, probe=False)

    engines_found = {e["engine"] for e in entries}
    assert engines_found == {"biome", "eslint", "prettier", "tsc"}
    assert all(e["required"] for e in entries)
    assert all(e["disposition"] == "installed" for e in entries)


def test_mixed_python_and_typescript_combines_both_stacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _python_project(tmp_path)
    _ts_project(tmp_path)
    _empty_path(tmp_path, monkeypatch)

    entries = doctor_mod.build_engine_inventory(root, probe=False)

    stacks_seen = {e["stack"] for e in entries}
    assert "python" in stacks_seen
    assert {"typescript"} & stacks_seen or {"javascript"} & stacks_seen
    engines_found = {e["engine"] for e in entries}
    assert {"ruff", "mypy", "biome", "eslint", "tsc"} <= engines_found


def test_no_marker_project_gives_empty_inventory_and_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    _empty_path(tmp_path, monkeypatch)

    entries = doctor_mod.build_engine_inventory(root, probe=False)

    assert entries == []


def test_rust_only_zero_supported_engines_gives_warn_no_supported_engine_for_stack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R15.1: clippy/cargo-audit/rustfmt all lack ENGINE_PACKAGES metadata."""
    root = _rust_project(tmp_path)
    _empty_path(tmp_path, monkeypatch)

    entries = doctor_mod.build_engine_inventory(root, probe=False)

    rust_entries = [e for e in entries if e["stack"] == "rust"]
    assert rust_entries, "rust stack must still surface its (unsupported) engines"
    assert all(e["disposition"] == "unsupported" for e in rust_entries)
    assert all(e["required"] is False for e in rust_entries)
    # The stack-level warn reason is asserted at the tool level in
    # test_doctor_tool_rust_only_gives_warn_via_no_supported_engine_for_stack;
    # this test only pins the per-engine disposition contract from R15.1.


# --- group: irrelevant optional absence (S15.4) ------------------------------


def test_python_project_missing_eslint_has_no_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """eslint is not a python-suggested engine; its absence must not appear."""
    root = _python_project(tmp_path)
    bin_dir = _empty_path(tmp_path, monkeypatch)
    for engine in ("ruff", "mypy", "pytest", "pip-audit", "aislop", "tach"):
        _fake_executable(bin_dir, engine)

    entries = doctor_mod.build_engine_inventory(root, probe=False)

    assert "eslint" not in {e["engine"] for e in entries}
    required = [e for e in entries if e["required"]]
    assert all(e["disposition"] == "installed" for e in required)


# --- group: shadowing (S15.3, design ("never probes a cwd-shadowing binary")) --


def test_shadow_plus_trusted_install_resolves_trusted_and_still_reports_shadow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both a project-root shadow and a real install on trusted PATH: the
    engine resolves to the trusted binary (T11 recovers it), is never the
    shadow, and doctor still reports the shadow as a warn-level finding."""
    root = _python_project(tmp_path)
    bin_dir = _empty_path(tmp_path, monkeypatch)
    real = _fake_executable(bin_dir, "ruff", version_output="9.9.9-real")
    shadow = _fake_executable(root, "ruff", version_output="EVIL-SHADOW")
    monkeypatch.setenv("PATH", f"{root}{os.pathsep}{bin_dir}")

    entries = doctor_mod.build_engine_inventory(root, probe=False)
    ruff_entry = next(e for e in entries if e["engine"] == "ruff")
    assert ruff_entry["disposition"] == "installed"
    assert Path(ruff_entry["executable"]).resolve() == real.resolve()
    assert Path(ruff_entry["executable"]).resolve() != shadow.resolve()

    result = doctor_mod.DoctorTool().run(root)
    rules = {f.get("rule") for f in result.get("findings", [])}
    assert "binary-shadowing" in rules
    assert result["status"] == "warn"


def test_cwd_shadowing_binary_reported_and_never_probed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _python_project(tmp_path)
    # T11: `resolve_binary` excludes any project-scoped PATH candidate. To
    # exercise "excluded, with nothing legitimate to recover elsewhere" (not
    # "excluded, then a real install found elsewhere"), no real ruff is
    # placed anywhere trusted -- only the project-root shadow itself.
    bin_dir = _empty_path(tmp_path, monkeypatch)
    # Shadow: a same-named binary living inside the project root itself, with
    # the root also placed on PATH ahead of the (empty) trusted directory.
    _fake_executable(root, "ruff", version_output="EVIL-SHADOW")
    monkeypatch.setenv("PATH", f"{root}{os.pathsep}{bin_dir}")

    entries = doctor_mod.build_engine_inventory(root, probe=True)

    ruff_entry = next(e for e in entries if e["engine"] == "ruff")
    assert ruff_entry["probe_state"] != "probed"
    # A shadowed binary is never trusted as "installed" -- the design says
    # it is "reported as a finding instead" of being probed/resolved as real.
    assert ruff_entry["disposition"] != "installed"

    result = doctor_mod.DoctorTool().run(root)
    rules = {f.get("rule") for f in result.get("findings", [])}
    assert "binary-shadowing" in rules


# --- group: integrity (S15.4, R15.3) -----------------------------------------


def test_tampered_manifest_gives_error_status_and_integrity_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    root = _python_project(tmp_path)
    bin_dir = _empty_path(tmp_path, monkeypatch)
    exe = _fake_executable(bin_dir, "ruff")

    from rush.runtime.binaries import (
        ProvisionManifest,
        compute_file_sha256,
        write_manifest,
    )

    manifest_dir = tmp_path / "manifests" / "ruff"
    manifest = ProvisionManifest(
        schema_version=1,
        engine_id="ruff",
        package_id="ruff",
        version="1.0.0",
        source="pypi",
        manager="uv",
        executable=str(exe),
        executable_sha256=compute_file_sha256(exe),
        os_name="test",
        arch="test",
        project_id="proj",
        project_root=str(root.resolve()),
        runtime_identity="test",
        plan_id="plan",
        created_at="2026-01-01T00:00:00Z",
    )
    manifest_path = write_manifest(manifest_dir, manifest)

    # Tamper: rewrite the executable's bytes after the manifest recorded its hash.
    exe.write_text("#!/bin/sh\necho tampered\n", encoding="utf-8")

    rush_dir = root / ".rush"
    rush_dir.mkdir()
    (rush_dir / "toolchains.json").write_text(
        json.dumps({"ruff": {"manifest": str(manifest_path)}}), encoding="utf-8"
    )
    binaries_mod.clear_manifest_cache()

    result = doctor_mod.DoctorTool().run(root)

    assert result["status"] == "error"
    rules = {f.get("rule") for f in result.get("findings", [])}
    assert "engine-integrity" in rules


# --- group: unsupported package/platform -------------------------------------


def test_bandit_recommended_engine_lacks_package_metadata_guard() -> None:
    """Guard: confirms the premise the unsupported-engine tests rely on.

    Currently passing -- this does not depend on T15's unimplemented
    function, it only checks the existing `engine_packages` registry.
    """
    with pytest.raises(UnknownEngineError):
        resolve_engine_package("bandit")
    assert "bandit" not in ENGINE_PACKAGES


def test_rust_suggested_engines_all_lack_package_metadata_guard() -> None:
    """Guard for the rust-only warn case: none of clippy/cargo-audit/rustfmt
    has ENGINE_PACKAGES metadata today. Currently passing."""
    for engine in ("clippy", "cargo-audit", "rustfmt"):
        assert engine not in ENGINE_PACKAGES


def test_python_bandit_entry_marked_unsupported_and_excluded_from_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _python_project(tmp_path)
    _empty_path(tmp_path, monkeypatch)

    entries = doctor_mod.build_engine_inventory(root, probe=False)

    bandit_entry = next(e for e in entries if e["engine"] == "bandit")
    assert bandit_entry["disposition"] == "unsupported"
    assert bandit_entry["required"] is False


# --- group: exact JSON shape / action string (S15.2, S15.5) -----------------


def test_engine_entry_has_exact_required_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _python_project(tmp_path)
    bin_dir = _empty_path(tmp_path, monkeypatch)
    _fake_executable(bin_dir, "ruff")

    entries = doctor_mod.build_engine_inventory(root, probe=False)
    ruff_entry = next(e for e in entries if e["engine"] == "ruff")

    assert set(ruff_entry.keys()) == {
        "engine",
        "stack",
        "required",
        "disposition",
        "executable",
        "source",
        "version",
        "probe_state",
        "action",
    }


def test_missing_engine_action_is_exact_rush_setup_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _python_project(tmp_path)
    _empty_path(tmp_path, monkeypatch)

    entries = doctor_mod.build_engine_inventory(root, probe=False)
    ruff_entry = next(e for e in entries if e["engine"] == "ruff")

    # T26: the action is the saved-plan step of the non-interactive route;
    # it prints the exact `--apply --yes --plan-file --plan-id` command with
    # the plan's grants (the plan id exists only once the plan is saved).
    quoted_root = shlex.quote(str(root.resolve()))
    quoted_plan = shlex.quote(str(root.resolve() / ".rush" / "setup-plan.json"))
    expected = (
        f"rush setup {quoted_root} --save-plan {quoted_plan} "
        "--allow-artifact-write --allow-network"
    )
    assert ruff_entry["action"] == expected
    assert "--allow-build" not in ruff_entry["action"]


def test_installed_engine_has_no_setup_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _python_project(tmp_path)
    bin_dir = _empty_path(tmp_path, monkeypatch)
    _fake_executable(bin_dir, "ruff")

    entries = doctor_mod.build_engine_inventory(root, probe=False)
    ruff_entry = next(e for e in entries if e["engine"] == "ruff")

    assert not ruff_entry["action"]


# --- group: probe vs no-probe (R15.2) ----------------------------------------


def test_probe_false_never_executes_any_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _python_project(tmp_path)
    bin_dir = _empty_path(tmp_path, monkeypatch)
    _fake_executable(bin_dir, "ruff")

    called: list[tuple] = []
    import subprocess

    real_run = subprocess.run

    def _tracking_run(*args: object, **kwargs: object) -> object:
        called.append((args, kwargs))
        return real_run(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(subprocess, "run", _tracking_run)

    entries = doctor_mod.build_engine_inventory(root, probe=False)

    assert called == []
    ruff_entry = next(e for e in entries if e["engine"] == "ruff")
    assert ruff_entry["probe_state"] == "not_probed"


def test_probe_true_sets_probed_state_for_installed_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _python_project(tmp_path)
    bin_dir = _empty_path(tmp_path, monkeypatch)
    _fake_executable(bin_dir, "ruff", version_output="ruff 1.2.3")

    entries = doctor_mod.build_engine_inventory(root, probe=True)

    ruff_entry = next(e for e in entries if e["engine"] == "ruff")
    assert ruff_entry["probe_state"] == "probed"
    assert ruff_entry["version"]


# --- group: doctor tool status/exit integration ------------------------------


def test_doctor_tool_python_all_engines_installed_gives_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _python_project(tmp_path)
    bin_dir = _empty_path(tmp_path, monkeypatch)
    for engine in ("ruff", "mypy", "pytest", "pip-audit", "aislop", "tach"):
        _fake_executable(bin_dir, engine)

    result = doctor_mod.DoctorTool().run(root)

    assert result["status"] == "ok"


def test_doctor_tool_python_missing_engine_gives_warn_and_names_engine_and_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _python_project(tmp_path)
    _empty_path(tmp_path, monkeypatch)

    result = doctor_mod.DoctorTool().run(root)

    assert result["status"] == "warn"
    findings = result.get("findings", [])
    assert any(f.get("rule") == "engine-missing" for f in findings)
    messages = " ".join(str(f.get("message", "")) for f in findings)
    assert "ruff" in messages
    assert "rush setup" in messages


def test_doctor_tool_rust_only_gives_warn_via_no_supported_engine_for_stack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _rust_project(tmp_path)
    _empty_path(tmp_path, monkeypatch)

    result = doctor_mod.DoctorTool().run(root)

    assert result["status"] == "warn"
    rules = {f.get("rule") for f in result.get("findings", [])}
    assert "engine-unsupported" in rules or "no_supported_engine_for_stack" in rules


def test_doctor_status_warn_when_required_engine_only_shadowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A required engine resolvable only via a project-root shadow must not
    be reported as a healthy project -- disposition is "missing", so status
    must be "warn" via the "binary-shadowing" finding, exactly like any
    other required-engine-unavailable case."""
    root = _python_project(tmp_path)
    bin_dir = _empty_path(tmp_path, monkeypatch)
    for engine in ("mypy", "pytest", "pip-audit", "aislop", "tach"):
        _fake_executable(bin_dir, engine)
    _fake_executable(root, "ruff", version_output="EVIL-SHADOW")
    monkeypatch.setenv("PATH", f"{root}{os.pathsep}{bin_dir}")

    result = doctor_mod.DoctorTool().run(root)

    assert result["status"] == "warn"
    rules = {f.get("rule") for f in result.get("findings", [])}
    assert "binary-shadowing" in rules


# --- keep-green guards: existing, currently-passing behavior -----------------


def test_write_and_verify_manifest_roundtrip_still_works(tmp_path: Path) -> None:
    """Sanity check for the manifest fixture helper used above -- this
    exercises only existing `runtime.binaries` API and must pass today."""
    from rush.runtime.binaries import (
        ProvisionManifest,
        compute_file_sha256,
        write_manifest,
    )

    exe = tmp_path / "bin" / "ruff"
    exe.parent.mkdir()
    exe.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")

    manifest = ProvisionManifest(
        schema_version=1,
        engine_id="ruff",
        package_id="ruff",
        version="1.0.0",
        source="pypi",
        manager="uv",
        executable=str(exe),
        executable_sha256=compute_file_sha256(exe),
        os_name="test",
        arch="test",
        project_id="proj",
        project_root=str(tmp_path.resolve()),
        runtime_identity="test",
        plan_id="plan",
        created_at="2026-01-01T00:00:00Z",
    )
    manifest_path = write_manifest(tmp_path / "manifests", manifest)

    from rush.runtime.binaries import read_manifest, verify_manifest

    loaded = read_manifest(manifest_path)
    assert loaded is not None
    verify_manifest(loaded, project_root=tmp_path)  # must not raise


def test_existing_doctor_tool_run_still_returns_tool_result_shape(
    tmp_path: Path,
) -> None:
    """Guard: today's DoctorTool.run keeps returning the shared ToolResult
    shape (tool/status/summary) regardless of T15's future changes."""
    result = doctor_mod.DoctorTool().run(tmp_path)
    assert result["tool"] == "doctor"
    assert "summary" in result
