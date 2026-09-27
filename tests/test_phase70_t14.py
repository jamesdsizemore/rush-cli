"""T14 test matrix: audit Python dependency inputs (uv.lock, requirements*.txt, pyproject.toml).

Binding brief: `.scratch/phase-70-design-gate/W2-T9-T17.md` §T14 (design), §0 (cross-cutting
findings). Plan packet: `docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md` T14.

T14 is not implemented in this worktree (tests-first task). Every test below is expected to
fail RED against the current `SecurityTool`/`OsvScannerEngine`/`PipAuditEngine`, which do not yet
recognize uv.lock/requirements*/pyproject.toml as a per-input inventory, do not build
`metadata.scope.dependencies`, and do not gate pip-audit project mode behind explicit grants.

Predecessors T8 (path containment helper) and T13 (dedup) are not implemented here either. Only
`test_t14_requirements_include_outside_root_is_malformed` touches T8-shaped containment behavior;
it is still asserting T14's own final per-input state, so it is not labelled RED-via-T8 — T14's
own dispatch is entirely absent, which is sufficient on its own to fail this test.

No network calls: every OSV/pip-audit subprocess boundary is faked at `run_subprocess` (the seam
both engines import from `rush.tools.common`) or at `rush.tools.security.run_engine` (the seam
`SecurityTool` dispatches through). Zero-spawn assertions patch `run_subprocess` to fail the test
if called at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from rush.permissions import ExecutionPermissions
from rush.tools.security import SecurityTool

# ---------------------------------------------------------------------------
# Fixtures (local helpers, no conftest / shared file per task scope)
# ---------------------------------------------------------------------------

_UV_LOCK_VULNERABLE = """\
version = 1
requires-python = ">=3.12"

[[package]]
name = "requests"
version = "2.6.0"
source = { registry = "https://pypi.org/simple" }
"""

_UV_LOCK_MALFORMED = "this is not [ valid toml\n"


def _fail_if_spawned(*_args: Any, **_kwargs: Any) -> Any:
    pytest.fail("no subprocess should have been spawned")


def _denied_permissions() -> ExecutionPermissions:
    return ExecutionPermissions()


def _granted_project_mode_permissions() -> ExecutionPermissions:
    return ExecutionPermissions(
        network=True, download=True, cache_write=True, build=True
    )


# ---------------------------------------------------------------------------
# Group 1 — offline OSV recognition of uv.lock (S14.1, S14.2)
# ---------------------------------------------------------------------------


def test_t14_python_dependency_inventory(monkeypatch, tmp_path: Path) -> None:
    """Vulnerable pinned uv.lock + offline DB fixture gives exact package/version/advisory."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text(_UV_LOCK_VULNERABLE)

    calls: list[tuple[str, list[str]]] = []

    def fake_osv_run_subprocess(argv: list[str], **_kwargs: Any) -> Any:
        calls.append(("osv-scanner", argv))
        import subprocess

        stdout = (
            f'{{"results": [{{"source": {{"path": "{lockfile}"}}, "packages": ['
            '{"package": {"name": "requests", "version": "2.6.0", "ecosystem": "PyPI"}, '
            '"vulnerabilities": [{"id": "PYSEC-2014-0001", "fixed_version": "2.6.1"}]}'
            "]}]}"
        )
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout=stdout, stderr=""
        )

    monkeypatch.setattr("rush.engines.osv.run_subprocess", fake_osv_run_subprocess)
    monkeypatch.setattr("rush.engines.osv.resolve_binary", lambda binary: binary)
    monkeypatch.setattr("rush.tools.common.engine_on_path", lambda binary: True)

    result = SecurityTool().run(tmp_path, permissions=_denied_permissions())

    assert calls, "osv-scanner should have been invoked for uv.lock"
    argv = calls[0][1]
    assert "--offline" in argv
    assert any(str(lockfile) in part for part in argv)

    deps = result["metadata"]["scope"]["dependencies"]
    uv_entry = next(d for d in deps if d["path"] == str(lockfile))
    assert uv_entry["kind"] == "uv_lock"
    assert uv_entry["state"] == "audited"

    finding = next(f for f in result["findings"] if "requests==2.6.0" in f["message"])
    assert finding["evidence"]["input"] == str(lockfile)


def test_t14_requirements_dev_via_parser_prefix(monkeypatch, tmp_path: Path) -> None:
    """requirements-dev.txt is recognized and sent through the explicit parser prefix."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
    req_dev = tmp_path / "requirements-dev.txt"
    req_dev.write_text("requests==2.6.0\n")

    calls: list[list[str]] = []

    def fake_osv_run_subprocess(argv: list[str], **_kwargs: Any) -> Any:
        calls.append(argv)
        import subprocess

        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"results": []}', stderr=""
        )

    monkeypatch.setattr("rush.engines.osv.run_subprocess", fake_osv_run_subprocess)
    monkeypatch.setattr("rush.engines.osv.resolve_binary", lambda binary: binary)
    monkeypatch.setattr("rush.tools.common.engine_on_path", lambda binary: True)

    result = SecurityTool().run(tmp_path, permissions=_denied_permissions())

    assert calls, "osv-scanner should have been invoked for requirements-dev.txt"
    argv = calls[0]
    expected_prefix = f"requirements.txt:{req_dev}"
    assert any(expected_prefix in part for part in argv)

    deps = result["metadata"]["scope"]["dependencies"]
    entry = next(d for d in deps if d["path"] == str(req_dev))
    assert entry["kind"] == "requirements"
    assert entry["state"] == "audited"


def test_t14_multiple_manifests_preserve_input_provenance_including_duplicates(
    monkeypatch, tmp_path: Path
) -> None:
    """uv.lock and requirements.txt both flagging the same package keep separate provenance."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text(_UV_LOCK_VULNERABLE)
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("requests==2.6.0\n")

    def fake_osv_run_subprocess(argv: list[str], **_kwargs: Any) -> Any:
        import subprocess

        stdout = (
            '{"results": ['
            f'{{"source": {{"path": "{lockfile}"}}, "packages": [{{"package": '
            '{"name": "requests", "version": "2.6.0", "ecosystem": "PyPI"}, '
            '"vulnerabilities": [{"id": "PYSEC-2014-0001"}]}]},'
            f'{{"source": {{"path": "{requirements}"}}, "packages": [{{"package": '
            '{"name": "requests", "version": "2.6.0", "ecosystem": "PyPI"}, '
            '"vulnerabilities": [{"id": "PYSEC-2014-0001"}]}]}'
            "]}"
        )
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout=stdout, stderr=""
        )

    monkeypatch.setattr("rush.engines.osv.run_subprocess", fake_osv_run_subprocess)
    monkeypatch.setattr("rush.engines.osv.resolve_binary", lambda binary: binary)
    monkeypatch.setattr("rush.tools.common.engine_on_path", lambda binary: True)

    result = SecurityTool().run(tmp_path, permissions=_denied_permissions())

    matching = [f for f in result["findings"] if "requests==2.6.0" in f["message"]]
    assert len(matching) == 2, "duplicate finding across two inputs must not be deduped"
    inputs = {f["evidence"]["input"] for f in matching}
    assert inputs == {str(lockfile), str(requirements)}


# ---------------------------------------------------------------------------
# Group 2 — pyproject.toml project-mode audit (S14.3, S14.4)
# ---------------------------------------------------------------------------


def test_t14_pyproject_pinned_dependency_resolves_via_granted_project_mode(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'fixture'\ndependencies = ['requests==2.6.0']\n"
    )

    calls: list[list[str]] = []

    def fake_pip_audit_run_subprocess(argv: list[str], **_kwargs: Any) -> Any:
        calls.append(argv)
        import subprocess

        stdout = (
            '{"dependencies": [{"name": "requests", "version": "2.6.0", '
            '"vulns": [{"id": "PYSEC-2014-0001", "fix_versions": ["2.6.1"], '
            '"description": "advisory"}]}]}'
        )
        return subprocess.CompletedProcess(
            args=[], returncode=1, stdout=stdout, stderr=""
        )

    monkeypatch.setattr(
        "rush.engines.pip_audit.run_subprocess", fake_pip_audit_run_subprocess
    )
    monkeypatch.setattr("rush.engines.pip_audit.resolve_binary", lambda binary: binary)
    monkeypatch.setattr("rush.tools.common.engine_on_path", lambda binary: True)

    result = SecurityTool().run(
        tmp_path, permissions=_granted_project_mode_permissions()
    )

    assert calls, "pip-audit project mode should have spawned with grants"
    argv = calls[0]
    assert str(tmp_path) in argv
    assert "--no-deps" not in argv
    assert "--disable-pip" not in argv

    deps = result["metadata"]["scope"]["dependencies"]
    entry = next(d for d in deps if d["kind"] == "pyproject")
    assert entry["state"] == "resolved-for-this-audit"


def test_t14_pyproject_dynamic_dependencies_reported_as_explicit_exclusion(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'fixture'\ndynamic = ['dependencies']\n"
    )
    monkeypatch.setattr("rush.engines.pip_audit.run_subprocess", _fail_if_spawned)

    result = SecurityTool().run(
        tmp_path, permissions=_granted_project_mode_permissions()
    )

    deps = result["metadata"]["scope"]["dependencies"]
    entry = next(d for d in deps if d["kind"] == "pyproject")
    exclusions = entry.get("exclusions") or []
    assert "dynamic" in exclusions
    assert entry["state"] != "audited"


def test_t14_malformed_uv_lock_is_an_error_child(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text(_UV_LOCK_MALFORMED)
    monkeypatch.setattr("rush.engines.osv.run_subprocess", _fail_if_spawned)

    result = SecurityTool().run(tmp_path, permissions=_denied_permissions())

    deps = result["metadata"]["scope"]["dependencies"]
    entry = next(d for d in deps if d["path"] == str(lockfile))
    assert entry["state"] == "malformed"
    assert result["status"] == "error"


def test_t14_editable_local_dependency_is_unresolved(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("-e ./local\n")
    monkeypatch.setattr("rush.engines.osv.run_subprocess", _fail_if_spawned)

    result = SecurityTool().run(tmp_path, permissions=_denied_permissions())

    deps = result["metadata"]["scope"]["dependencies"]
    entry = next(d for d in deps if d["path"] == str(requirements))
    assert entry["state"] == "unresolved"


def test_t14_requirements_include_outside_root_is_malformed(
    monkeypatch, tmp_path: Path
) -> None:
    """`-r ../escape.txt` breaks containment: T14's own dispatch must reject it, regardless
    of whether T8's shared helper exists yet."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
    requirements = project / "requirements.txt"
    requirements.write_text("-r ../escape.txt\n")
    (tmp_path / "escape.txt").write_text("requests==2.6.0\n")
    monkeypatch.setattr("rush.engines.osv.run_subprocess", _fail_if_spawned)

    result = SecurityTool().run(project, permissions=_denied_permissions())

    deps = result["metadata"]["scope"]["dependencies"]
    entry = next(d for d in deps if d["path"] == str(requirements))
    assert entry["state"] == "malformed"
    assert entry["reason"] == "include_outside_root"


# ---------------------------------------------------------------------------
# Group 3 — engine/DB availability (S14.4, S14.5)
# ---------------------------------------------------------------------------


def test_t14_absent_osv_engine_gives_scanner_unavailable(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text(_UV_LOCK_VULNERABLE)
    monkeypatch.setattr("rush.tools.common.engine_on_path", lambda binary: False)
    monkeypatch.setattr("rush.engines.osv.run_subprocess", _fail_if_spawned)

    result = SecurityTool().run(tmp_path, permissions=_denied_permissions())

    deps = result["metadata"]["scope"]["dependencies"]
    entry = next(d for d in deps if d["path"] == str(lockfile))
    assert entry["state"] == "scanner_unavailable"


def test_t14_old_osv_version_gives_scanner_unavailable(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text(_UV_LOCK_VULNERABLE)
    monkeypatch.setattr("rush.tools.common.engine_on_path", lambda binary: True)
    monkeypatch.setattr(
        "rush.engines.osv.OsvScannerEngine.version", lambda self: "1.9.0"
    )
    monkeypatch.setattr("rush.engines.osv.run_subprocess", _fail_if_spawned)

    result = SecurityTool().run(tmp_path, permissions=_denied_permissions())

    deps = result["metadata"]["scope"]["dependencies"]
    entry = next(d for d in deps if d["path"] == str(lockfile))
    assert entry["state"] == "scanner_unavailable"
    assert "1.9.0" in entry["reason"] or "2.0.0" in entry["reason"]


def test_t14_offline_db_missing_gives_db_unavailable_zero_network(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text(_UV_LOCK_VULNERABLE)

    spawned_argv: list[list[str]] = []

    def fake_osv_run_subprocess(argv: list[str], **_kwargs: Any) -> Any:
        spawned_argv.append(argv)
        import subprocess

        return subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="no offline version of the OSV database is available",
        )

    monkeypatch.setattr("rush.tools.common.engine_on_path", lambda binary: True)
    monkeypatch.setattr("rush.engines.osv.resolve_binary", lambda binary: binary)
    monkeypatch.setattr("rush.engines.osv.run_subprocess", fake_osv_run_subprocess)

    result = SecurityTool().run(tmp_path, permissions=_denied_permissions())

    deps = result["metadata"]["scope"]["dependencies"]
    entry = next(d for d in deps if d["path"] == str(lockfile))
    assert entry["state"] == "db_unavailable"
    for argv in spawned_argv:
        assert "--download" not in argv


# ---------------------------------------------------------------------------
# Group 4 — pip-audit project mode gating (S14.3, R14.1)
# ---------------------------------------------------------------------------


def test_t14_denied_project_mode_gives_zero_spawns_and_exact_flag_list(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'fixture'\ndependencies = ['requests==2.6.0']\n"
    )
    monkeypatch.setattr("rush.engines.pip_audit.run_subprocess", _fail_if_spawned)

    result = SecurityTool().run(tmp_path, permissions=_denied_permissions())

    deps = result["metadata"]["scope"]["dependencies"]
    entry = next(d for d in deps if d["kind"] == "pyproject")
    assert entry["state"] != "resolved-for-this-audit"
    for flag in ("network", "download", "cache_write", "build"):
        assert flag in entry["reason"]


def test_t14_granted_project_mode_labels_resolved_with_exclusions(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'fixture'\n"
        "dependencies = ['requests==2.6.0']\n"
        "optional-dependencies = { dev = ['pytest'] }\n"
    )

    def fake_pip_audit_run_subprocess(argv: list[str], **_kwargs: Any) -> Any:
        import subprocess

        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"dependencies": []}', stderr=""
        )

    monkeypatch.setattr(
        "rush.engines.pip_audit.run_subprocess", fake_pip_audit_run_subprocess
    )
    monkeypatch.setattr("rush.engines.pip_audit.resolve_binary", lambda binary: binary)
    monkeypatch.setattr("rush.tools.common.engine_on_path", lambda binary: True)

    result = SecurityTool().run(
        tmp_path, permissions=_granted_project_mode_permissions()
    )

    deps = result["metadata"]["scope"]["dependencies"]
    entry = next(d for d in deps if d["kind"] == "pyproject")
    assert entry["state"] == "resolved-for-this-audit"
    assert "optional" in (entry.get("exclusions") or [])


# ---------------------------------------------------------------------------
# Group 5 — constraint: never audit Rush's own interpreter (S14.6)
# ---------------------------------------------------------------------------


def test_t14_never_audits_rush_own_interpreter_environment(
    monkeypatch, tmp_path: Path
) -> None:
    """pip-audit project mode must target the audited project's root, never Rush's own
    interpreter/site-packages, even when granted."""
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'fixture'\ndependencies = ['requests==2.6.0']\n"
    )

    calls: list[list[str]] = []

    def fake_pip_audit_run_subprocess(argv: list[str], **_kwargs: Any) -> Any:
        calls.append(argv)
        import subprocess

        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"dependencies": []}', stderr=""
        )

    monkeypatch.setattr(
        "rush.engines.pip_audit.run_subprocess", fake_pip_audit_run_subprocess
    )
    monkeypatch.setattr("rush.engines.pip_audit.resolve_binary", lambda binary: binary)
    monkeypatch.setattr("rush.tools.common.engine_on_path", lambda binary: True)

    import sys

    SecurityTool().run(tmp_path, permissions=_granted_project_mode_permissions())

    assert calls, "pip-audit project mode should have spawned with grants"
    for argv in calls:
        assert sys.prefix not in argv
        assert str(tmp_path) in argv


# ---------------------------------------------------------------------------
# Group 6 — W2 adversarial-review corrections: relative include resolution
# and nested requirements/ discovery (post-review additions, not part of the
# original frozen 14).
# ---------------------------------------------------------------------------


def test_t14_nested_requirements_include_resolves_relative_to_including_file(
    monkeypatch, tmp_path: Path
) -> None:
    """`requirements/dev.txt` with `-r ../base.txt` resolves relative to its
    own directory (`requirements/../base.txt` == `<root>/base.txt`), which is
    inside the root -- legitimate, not malformed."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
    requirements_dir = tmp_path / "requirements"
    requirements_dir.mkdir()
    dev = requirements_dir / "dev.txt"
    dev.write_text("-r ../base.txt\n")
    (tmp_path / "base.txt").write_text("requests==2.6.0\n")

    def fake_osv_run_subprocess(argv: list[str], **_kwargs: Any) -> Any:
        import subprocess

        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"results": []}', stderr=""
        )

    monkeypatch.setattr("rush.engines.osv.run_subprocess", fake_osv_run_subprocess)
    monkeypatch.setattr("rush.engines.osv.resolve_binary", lambda binary: binary)
    monkeypatch.setattr("rush.tools.common.engine_on_path", lambda binary: True)

    result = SecurityTool().run(tmp_path, permissions=_denied_permissions())

    deps = result["metadata"]["scope"]["dependencies"]
    entry = next(d for d in deps if d["path"] == str(dev))
    assert entry["state"] == "audited"


def test_t14_nested_requirements_include_escaping_root_is_malformed(
    monkeypatch, tmp_path: Path
) -> None:
    """`requirements/dev.txt` with `-r ../../escape.txt` resolves outside the
    root even though it is relative to the including file, not the root --
    still `malformed`/`include_outside_root`."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
    requirements_dir = project / "requirements"
    requirements_dir.mkdir()
    dev = requirements_dir / "dev.txt"
    dev.write_text("-r ../../escape.txt\n")
    (tmp_path / "escape.txt").write_text("requests==2.6.0\n")
    monkeypatch.setattr("rush.engines.osv.run_subprocess", _fail_if_spawned)

    result = SecurityTool().run(project, permissions=_denied_permissions())

    deps = result["metadata"]["scope"]["dependencies"]
    entry = next(d for d in deps if d["path"] == str(dev))
    assert entry["state"] == "malformed"
    assert entry["reason"] == "include_outside_root"


def test_t14_discovers_nested_requirements_directory_files(
    monkeypatch, tmp_path: Path
) -> None:
    """Discovery covers `requirements/*.txt` (and nested `requirements*.txt`),
    not only root-level files."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
    requirements_dir = tmp_path / "requirements"
    requirements_dir.mkdir()
    nested = requirements_dir / "prod.txt"
    nested.write_text("requests==2.6.0\n")

    def fake_osv_run_subprocess(argv: list[str], **_kwargs: Any) -> Any:
        import subprocess

        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"results": []}', stderr=""
        )

    monkeypatch.setattr("rush.engines.osv.run_subprocess", fake_osv_run_subprocess)
    monkeypatch.setattr("rush.engines.osv.resolve_binary", lambda binary: binary)
    monkeypatch.setattr("rush.tools.common.engine_on_path", lambda binary: True)

    result = SecurityTool().run(tmp_path, permissions=_denied_permissions())

    deps = result["metadata"]["scope"]["dependencies"]
    entry = next(d for d in deps if d["path"] == str(nested))
    assert entry["kind"] == "requirements"
    assert entry["state"] == "audited"


# ---------------------------------------------------------------------------
# Group 7 — orchestrator scope correction: catalog.py, engine_packages.py,
# and the finding-26 Popen-level zero-spawn amendment.
# ---------------------------------------------------------------------------


def test_t14_security_owns_osv_scanner_and_medusa_in_catalog() -> None:
    """R14.2: osv-scanner and medusa become owned by security's ToolSpec, so
    they drop out of the standalone engine-only scan candidate set."""
    from rush.catalog import TOOL_SPECS

    engine_names = TOOL_SPECS["security"].engine_names
    assert "osv-scanner" in engine_names
    assert "medusa" in engine_names


def test_t14_osv_scanner_engine_spec_markers_include_uv_lock() -> None:
    from rush.catalog import ENGINE_SPECS

    markers = ENGINE_SPECS["osv-scanner"].project_markers
    assert "uv.lock" in markers
    assert "requirements.txt" in markers


def test_t14_engine_packages_pins_osv_scanner_and_pip_audit_minimums() -> None:
    from rush.setup.engine_packages import ENGINE_PACKAGES

    assert ENGINE_PACKAGES["osv-scanner"].version_policy == "minimum:2.0.0"
    assert ENGINE_PACKAGES["pip-audit"].version_policy == "minimum:2.10.1"


def test_t14_denied_project_mode_zero_spawn_at_popen_level(
    monkeypatch, tmp_path: Path
) -> None:
    """Finding 26: the per-module `run_subprocess` patch misses a version
    probe made through `engines/base.py`. Count spawns at the real OS
    boundary -- both `subprocess.Popen` and `subprocess.run`, since an
    unowned call takes the blocking `subprocess.run` path."""
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'fixture'\ndependencies = ['requests==2.6.0']\n"
    )
    monkeypatch.setattr(
        "rush.tools.common.engine_on_path", lambda binary: binary != "medusa"
    )

    import subprocess as _subprocess

    def _fail_popen(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("no real subprocess.Popen should have been spawned")

    def _fail_run(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("no real subprocess.run should have been spawned")

    monkeypatch.setattr(_subprocess, "Popen", _fail_popen)
    monkeypatch.setattr(_subprocess, "run", _fail_run)

    result = SecurityTool().run(tmp_path, permissions=_denied_permissions())

    deps = result["metadata"]["scope"]["dependencies"]
    entry = next(d for d in deps if d["kind"] == "pyproject")
    assert entry["state"] != "resolved-for-this-audit"


def test_t14_missing_offline_db_zero_network_at_popen_level(
    monkeypatch, tmp_path: Path
) -> None:
    """Finding 26: same OS-boundary guarantee for the missing-offline-DB
    path -- no `--download` flag ever reaches a real spawned process,
    observed at `subprocess.run` (the actual unowned spawn path) with a
    `subprocess.Popen` guard as defense in depth."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text(_UV_LOCK_VULNERABLE)
    monkeypatch.setattr(
        "rush.tools.common.engine_on_path", lambda binary: binary != "medusa"
    )
    monkeypatch.setattr("rush.engines.osv.resolve_binary", lambda binary: binary)

    import subprocess as _subprocess

    spawned_argv: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: Any) -> Any:
        if "--version" in argv:
            return _subprocess.CompletedProcess(
                args=argv, returncode=0, stdout="osv-scanner version: 2.4.0", stderr=""
            )
        spawned_argv.append(list(argv))
        return _subprocess.CompletedProcess(
            args=argv,
            returncode=1,
            stdout="",
            stderr="no offline version of the OSV database is available",
        )

    def _fail_popen(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("no real subprocess.Popen should have been spawned")

    monkeypatch.setattr(_subprocess, "run", fake_run)
    monkeypatch.setattr(_subprocess, "Popen", _fail_popen)

    result = SecurityTool().run(tmp_path, permissions=_denied_permissions())

    deps = result["metadata"]["scope"]["dependencies"]
    entry = next(d for d in deps if d["path"] == str(lockfile))
    assert entry["state"] == "db_unavailable"
    assert spawned_argv, "osv-scanner should have been invoked"
    for argv in spawned_argv:
        assert "--download" not in argv
