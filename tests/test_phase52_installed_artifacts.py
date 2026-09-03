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
    dist_dir = PROJECT_ROOT / "dist"
    wheels = list(dist_dir.glob("*.whl"))
    sdists = list(dist_dir.glob("*.tar.gz"))

    assert wheels, f"No wheel found in {dist_dir}. Build artifacts first."
    assert sdists, f"No sdist found in {dist_dir}. Build artifacts first."

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
