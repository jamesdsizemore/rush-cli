"""Contract tests for Installed Artifacts Isolation & Probes (Phase 51: P51.3.1)."""

from __future__ import annotations

from pathlib import Path

from scripts.probe_installed_artifacts import (
    ArtifactProbeResult,
    scrub_environment,
)


def test_probe_scrubs_pythonpath_and_editable_state() -> None:
    env = {
        "PYTHONPATH": "/some/source/checkout",
        "VIRTUAL_ENV": "/some/venv",
        "PATH": "/usr/bin",
        "CUSTOM_VAR": "val",
    }
    scrubbed = scrub_environment(env)
    assert "PYTHONPATH" not in scrubbed
    assert "VIRTUAL_ENV" not in scrubbed
    assert scrubbed.get("PATH") == "/usr/bin"
    assert scrubbed.get("CUSTOM_VAR") == "val"


def test_external_cwd_rejects_checkout_origin(tmp_path: Path) -> None:
    # Fake module inside checkout
    checkout_dir = tmp_path / "checkout"
    checkout_dir.mkdir()
    (checkout_dir / "rush").mkdir()
    (checkout_dir / "rush" / "__init__.py").write_text(
        "__file__ = 'checkout/rush/__init__.py'", encoding="utf-8"
    )

    external_cwd = tmp_path / "empty_external_dir"
    external_cwd.mkdir()

    # If an imported package points inside checkout_dir, it must be rejected
    from scripts.probe_installed_artifacts import verify_package_origin

    fake_installed_path = external_cwd / "site-packages" / "rush" / "__init__.py"
    fake_checkout_path = checkout_dir / "rush" / "__init__.py"

    assert (
        verify_package_origin(fake_installed_path, checkout_root=checkout_dir) is True
    )
    assert (
        verify_package_origin(fake_checkout_path, checkout_root=checkout_dir) is False
    )


def test_broken_import_control_is_detected(tmp_path: Path) -> None:
    # A package containing invalid 'from src.rush' import should be flagged
    from scripts.probe_installed_artifacts import check_import_integrity

    broken_code = "from src.rush.tools import something\n"
    clean_code = "from rush.tools import something\n"

    assert check_import_integrity(broken_code) is False
    assert check_import_integrity(clean_code) is True


def test_wheel_and_sdist_are_probed_independently() -> None:
    # Verify probe result structure supports independent results
    wheel_res = ArtifactProbeResult(
        artifact_type="wheel",
        artifact_path="dist/rush_cli-0.3.0-py3-none-any.whl",
        status="passed",
        origin_verified=True,
        import_clean=True,
        stdout="rush 0.3.0",
        stderr="",
    )
    sdist_res = ArtifactProbeResult(
        artifact_type="sdist",
        artifact_path="dist/rush_cli-0.3.0.tar.gz",
        status="passed",
        origin_verified=True,
        import_clean=True,
        stdout="rush 0.3.0",
        stderr="",
    )

    assert wheel_res.artifact_type == "wheel"
    assert sdist_res.artifact_type == "sdist"
    assert wheel_res != sdist_res
