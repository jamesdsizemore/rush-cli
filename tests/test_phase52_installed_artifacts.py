"""Contract tests for Installed Artifacts and Scrubbed Environment Parity (Phase 52: P52.4)."""

from __future__ import annotations

from pathlib import Path

from scripts.probe_installed_artifacts import (
    probe_installed_artifact,
    scrub_environment,
    verify_package_origin,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_scrub_environment_removes_pythonpath_and_virtualenv() -> None:
    """Verify that scrub_environment strips PYTHONPATH, VIRTUAL_ENV, and PYTHONHOME."""
    dirty_env = {
        "PATH": "/bin:/usr/bin",
        "PYTHONPATH": "/somewhere/cheating/src",
        "VIRTUAL_ENV": "/my/active/venv",
        "PYTHONHOME": "/bad/home",
        "OTHER_VAR": "keep_me",
    }
    scrubbed = scrub_environment(dirty_env)

    assert "PYTHONPATH" not in scrubbed
    assert "VIRTUAL_ENV" not in scrubbed
    assert "PYTHONHOME" not in scrubbed
    assert scrubbed["PATH"] == "/bin:/usr/bin"
    assert scrubbed["OTHER_VAR"] == "keep_me"


import tempfile


def test_verify_package_origin_flags_checkout_root() -> None:
    """Verify that verify_package_origin correctly flags in-tree modules."""
    in_tree = PROJECT_ROOT / "src" / "rush" / "__init__.py"
    out_of_tree = (
        Path(tempfile.gettempdir())
        / "external_venv"
        / "site-packages"
        / "rush"
        / "__init__.py"
    )

    assert verify_package_origin(in_tree, PROJECT_ROOT) is False
    assert verify_package_origin(out_of_tree, PROJECT_ROOT) is True


def test_wheel_and_sdist_pass_every_safe_probe(tmp_path: Path) -> None:
    """Verify that both built wheel and sdist pass clean installation and external-CWD probes."""
    import tomllib

    pyproject_data = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    expected_version = pyproject_data["project"]["version"]

    dist_dir = PROJECT_ROOT / "dist"
    wheels = sorted(dist_dir.glob(f"rush_cli-{expected_version}*.whl"))
    sdists = sorted(dist_dir.glob(f"rush_cli-{expected_version}*.tar.gz"))

    assert wheels, (
        f"No wheel for v{expected_version} found in {dist_dir}. Build artifacts first."
    )
    assert sdists, (
        f"No sdist for v{expected_version} found in {dist_dir}. Build artifacts first."
    )

    # Probe wheel
    wheel_result = probe_installed_artifact(
        wheels[0], PROJECT_ROOT, tmp_path / "wheel_test"
    )
    assert wheel_result.status == "passed", f"Wheel probe failed: {wheel_result.stderr}"
    assert wheel_result.origin_verified is True
    assert wheel_result.import_clean is True

    # Probe sdist
    sdist_result = probe_installed_artifact(
        sdists[0], PROJECT_ROOT, tmp_path / "sdist_test"
    )
    assert sdist_result.status == "passed", f"Sdist probe failed: {sdist_result.stderr}"
    assert sdist_result.origin_verified is True
    assert sdist_result.import_clean is True


def test_artifact_imports_never_resolve_to_checkout_or_src(tmp_path: Path) -> None:
    """Verify that verify_package_origin strictly rejects in-tree origins."""
    assert (
        verify_package_origin(
            PROJECT_ROOT / "src" / "rush" / "__init__.py", PROJECT_ROOT
        )
        is False
    )
    assert (
        verify_package_origin(PROJECT_ROOT / "rush" / "__init__.py", PROJECT_ROOT)
        is False
    )
    assert (
        verify_package_origin(
            PROJECT_ROOT / "src" / "rush" / "tools" / "base.py", PROJECT_ROOT
        )
        is False
    )

    # External paths must be verified as valid out-of-tree origins
    external_site_packages = (
        tmp_path / "venv" / "lib" / "site-packages" / "rush" / "__init__.py"
    )
    assert verify_package_origin(external_site_packages, PROJECT_ROOT) is True


def test_artifact_version_matches_distribution_metadata() -> None:
    """Verify that built wheel distribution metadata version matches pyproject.toml."""
    import tomllib
    import zipfile

    pyproject_data = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    expected_version = pyproject_data["project"]["version"]

    dist_dir = PROJECT_ROOT / "dist"
    wheels = sorted(dist_dir.glob(f"rush_cli-{expected_version}*.whl"))
    assert wheels, f"No wheel found for v{expected_version} in dist/"

    with zipfile.ZipFile(wheels[0]) as zf:
        metadata_content = zf.read(
            f"rush_cli-{expected_version}.dist-info/METADATA"
        ).decode("utf-8")
        assert f"Version: {expected_version}" in metadata_content


def test_windows_and_posix_jobs_cover_both_artifacts() -> None:
    """Verify that CI workflow artifact-probes matrix covers Windows and POSIX without failure masking."""
    import ruamel.yaml

    ci_yaml_path = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    yaml = ruamel.yaml.YAML(typ="safe")
    ci_data = yaml.load(ci_yaml_path.read_text(encoding="utf-8"))

    probes_job = ci_data.get("jobs", {}).get("artifact-probes", {})
    assert probes_job, "ci.yml missing 'artifact-probes' job"

    matrix_os = probes_job.get("strategy", {}).get("matrix", {}).get("os", [])
    assert "ubuntu-latest" in matrix_os, (
        "artifact-probes matrix must include POSIX (ubuntu-latest)"
    )
    assert "windows-latest" in matrix_os, (
        "artifact-probes matrix must include Windows (windows-latest)"
    )

    # Check steps for unmasked probe execution
    probe_step = None
    for step in probes_job.get("steps", []):
        if "probe_installed_artifacts.py" in step.get("run", ""):
            probe_step = step
            break

    assert probe_step is not None, (
        "artifact-probes job missing probe_installed_artifacts.py step"
    )
    run_cmd = probe_step.get("run", "")
    assert "|| true" not in run_cmd, (
        f"Artifact probe step must not mask errors with '|| true': {run_cmd}"
    )
