"""Contract tests for Installed Artifacts and Scrubbed Environment Parity (Phase 52: P52.4)."""

from __future__ import annotations

from pathlib import Path

from scripts.probe_installed_artifacts import (
    probe_installed_artifact,
    probe_native_artifact,
    scrub_environment,
    select_platform_asset,
    verify_archive_checksum,
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


def test_wheel_and_sdist_pass_every_safe_probe(
    tmp_path: Path, distribution_artifacts: tuple[Path, Path]
) -> None:
    """Verify that both built wheel and sdist pass clean installation and external-CWD
    probes. `distribution_artifacts` (conftest.py) builds both from the current source
    once per session."""
    wheel, sdist = distribution_artifacts

    # Probe wheel
    wheel_result = probe_installed_artifact(
        wheel, PROJECT_ROOT, tmp_path / "wheel_test"
    )
    assert wheel_result.status == "passed", f"Wheel probe failed: {wheel_result.stderr}"
    assert wheel_result.origin_verified is True
    assert wheel_result.import_clean is True

    # Probe sdist
    sdist_result = probe_installed_artifact(
        sdist, PROJECT_ROOT, tmp_path / "sdist_test"
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


def test_artifact_version_matches_distribution_metadata(
    distribution_artifacts: tuple[Path, Path],
) -> None:
    """Verify that built wheel distribution metadata version matches pyproject.toml."""
    import tomllib
    import zipfile

    pyproject_data = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    expected_version = pyproject_data["project"]["version"]

    wheel, _sdist = distribution_artifacts
    assert wheel.name.startswith(f"rush_cli-{expected_version}-")

    with zipfile.ZipFile(wheel) as zf:
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


def test_native_artifact_needs_no_checkout_python_or_uv(
    tmp_path: Path, native_release_archive: Path
) -> None:
    """Verify the extracted native release archive proves origin, version and a real MCP
    initialize handshake from a clean external directory with checkout/Python/uv absent
    from PATH (Phase 65: P65-01.3). `native_release_archive` (conftest.py) builds the
    archive from the current source once per session."""
    import json
    import os
    import platform
    import queue
    import subprocess
    import threading
    import tomllib
    import urllib.parse
    import urllib.request

    pyproject_data = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    expected_version = pyproject_data["project"]["version"]

    archive_path = native_release_archive
    checksums_path = archive_path.parent / "SHA256SUMS"
    assert archive_path.name == select_platform_asset(
        platform.system(), platform.machine()
    )

    assert verify_archive_checksum(archive_path, checksums_path) is True, (
        "Native archive bytes do not match its recorded SHA256SUMS entry."
    )

    result = probe_native_artifact(archive_path, PROJECT_ROOT, tmp_path)

    assert result.status == "passed", f"Native artifact probe failed: {result.stderr}"
    assert result.origin_verified is True
    assert result.mcp_initialized is True
    assert result.stdout.strip() == expected_version

    # Bundled Python/MCP alone does not prove the native dashboard's JS
    # resources survived PyInstaller's data collection.
    home = tmp_path / "dashboard-home"
    home.mkdir()
    env = {
        "PATH": "C:\\Windows\\System32" if os.name == "nt" else "/usr/bin:/bin",
        "HOME": str(home),
        "USERPROFILE": str(home),
        "LOCALAPPDATA": str(home / "local"),
        "XDG_DATA_HOME": str(home / "data"),
    }
    if os.name == "nt":
        env["SystemRoot"] = os.environ.get("SystemRoot", "C:\\Windows")
        env["windir"] = env["SystemRoot"]
    binary = tmp_path / "extracted" / ("rush.exe" if os.name == "nt" else "rush")
    with (tmp_path / "dashboard.stderr").open("w") as stderr:
        proc = subprocess.Popen(
            [str(binary), "dashboard", "--port", "0", "--no-open", "--json"],
            cwd=tmp_path / "cwd_native",
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
        )
        assert proc.stdout is not None
        ready_lines: queue.Queue[str] = queue.Queue()
        reader = threading.Thread(
            target=lambda: ready_lines.put(proc.stdout.readline()), daemon=True
        )
        reader.start()
        try:
            readiness = json.loads(ready_lines.get(timeout=20))
            assert readiness["ready"] is True
            # Bootstrap fragment is private: retain only the public origin.
            url = urllib.parse.urlsplit(readiness["url"])
            origin = f"{url.scheme}://{url.netloc}"
            for asset in ("application.js", "project_map.js"):
                with urllib.request.urlopen(
                    f"{origin}/assets/{asset}", timeout=5
                ) as response:
                    assert response.status == 200
                    assert (
                        response.read()
                        == (
                            PROJECT_ROOT / "src" / "rush" / "dashboard" / asset
                        ).read_bytes()
                    )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            reader.join(timeout=5)
            proc.stdout.close()
