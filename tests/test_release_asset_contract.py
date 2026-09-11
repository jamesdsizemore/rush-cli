"""Contract tests for verified standalone release artifacts (Phase 65: P65-01, F28)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from scripts.probe_installed_artifacts import (
    PLATFORM_ASSET_MATRIX,
    UnsupportedPlatformError,
    build_release_archive,
    compute_sha256,
    probe_native_artifact,
    select_platform_asset,
    verify_archive_checksum,
    write_sha256sums,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# All six OS/architecture pairs the release matrix must cover (Darwin/Linux/Windows x
# arm64/x86_64), keyed by the (platform.system(), platform.machine()) inputs a real host
# would report, including the aliases those hosts actually use (aarch64, AMD64).
SIX_WAY_MATRIX = [
    ("Darwin", "arm64", "rush-darwin-arm64.tar.gz"),
    ("Darwin", "x86_64", "rush-darwin-x86_64.tar.gz"),
    ("Linux", "x86_64", "rush-linux-x86_64.tar.gz"),
    ("Linux", "aarch64", "rush-linux-arm64.tar.gz"),
    ("Windows", "AMD64", "rush-windows-x86_64.zip"),
    ("Windows", "arm64", "rush-windows-arm64.zip"),
]


def _project_version() -> str:
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def test_platform_asset_selection() -> None:
    """Every one of the six supported OS/architecture pairs selects its exact release asset."""
    assert len(PLATFORM_ASSET_MATRIX) == 6

    for system, machine, expected_name in SIX_WAY_MATRIX:
        assert select_platform_asset(system, machine) == expected_name
        # Case-insensitivity on the OS name (as reported inconsistently across probes).
        assert select_platform_asset(system.upper(), machine) == expected_name
        assert select_platform_asset(system.lower(), machine) == expected_name

    # Unsupported architecture must fail closed, never silently fall back to a guess.
    with pytest.raises(UnsupportedPlatformError):
        select_platform_asset("Darwin", "riscv64")
    with pytest.raises(UnsupportedPlatformError):
        select_platform_asset("Plan9", "x86_64")


def test_archive_matches_manifest_and_checksum(tmp_path: Path) -> None:
    """Built archives, SHA256SUMS and packaging manifests all reference exactly what was produced."""
    version = _project_version()

    # 1. Paths with spaces: build into a directory containing a space and verify real bytes.
    dest_dir = tmp_path / "release dir with spaces"
    fake_binary = tmp_path / "source binary" / "rush"
    fake_binary.parent.mkdir(parents=True)
    fake_binary.write_bytes(b"#!/bin/sh\necho fake-rush\n")
    fake_binary.chmod(0o755)

    archive_path = build_release_archive(
        fake_binary, dest_dir, "rush-linux-x86_64.tar.gz", version
    )
    assert archive_path == dest_dir / "rush-linux-x86_64.tar.gz"
    assert archive_path.is_file()

    checksums_path = write_sha256sums([archive_path], dest_dir / "SHA256SUMS")
    assert verify_archive_checksum(archive_path, checksums_path) is True
    assert compute_sha256(archive_path) in checksums_path.read_text(encoding="utf-8")

    # 2. Missing artifact: checksum verification refuses, never fabricates a pass.
    missing_path = dest_dir / "rush-windows-arm64.zip"
    assert verify_archive_checksum(missing_path, checksums_path) is False

    # 3. Mismatched hash: corrupt the archive after the manifest was written.
    archive_path.write_bytes(archive_path.read_bytes() + b"\x00corrupted")
    assert verify_archive_checksum(archive_path, checksums_path) is False

    # 4. Manifests name exactly produced artifacts: cross-check every packaging file's
    # referenced asset names against the single canonical release matrix. No manifest may
    # invent a name outside the matrix, and every name it does reference must be exact.
    referenced_names: set[str] = set()

    homebrew_text = (PROJECT_ROOT / "packaging" / "homebrew" / "rush.rb").read_text(
        encoding="utf-8"
    )
    for name in PLATFORM_ASSET_MATRIX.values():
        if name in homebrew_text:
            referenced_names.add(name)
    assert f'version "{version}"' in homebrew_text

    import json as jsonlib

    scoop_data = jsonlib.loads(
        (PROJECT_ROOT / "packaging" / "scoop" / "rush.json").read_text(encoding="utf-8")
    )
    assert scoop_data["version"] == version
    for arch_entry in scoop_data["architecture"].values():
        url = arch_entry["url"]
        asset_name = url.rsplit("/", 1)[-1]
        assert asset_name in PLATFORM_ASSET_MATRIX.values(), (
            f"scoop manifest references unknown asset {asset_name!r}"
        )
        referenced_names.add(asset_name)

    import ruamel.yaml

    yaml = ruamel.yaml.YAML(typ="safe")
    winget_data = yaml.load(
        (PROJECT_ROOT / "packaging" / "winget" / "rush.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert winget_data["PackageVersion"] == version
    for installer in winget_data["Installers"]:
        asset_name = installer["InstallerUrl"].rsplit("/", 1)[-1]
        assert asset_name in PLATFORM_ASSET_MATRIX.values(), (
            f"winget manifest references unknown asset {asset_name!r}"
        )
        referenced_names.add(asset_name)

    # Every packaging file's asset names are drawn from the canonical matrix, and Windows
    # coverage in scoop/winget plus macOS/Linux coverage in Homebrew together name every
    # one of the six matrix members at least once.
    assert referenced_names == set(PLATFORM_ASSET_MATRIX.values())

    # 5. release.yml's own build matrix must produce exactly these six asset names too.
    release_yaml = yaml.load(
        (PROJECT_ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
    )
    build_job = release_yaml["jobs"]["build-binaries"]
    matrix_assets = {
        entry["asset_name"] for entry in build_job["strategy"]["matrix"]["include"]
    }
    assert matrix_assets == set(PLATFORM_ASSET_MATRIX.values())


def test_installed_binary_needs_no_checkout_or_python(tmp_path: Path) -> None:
    """A real self-contained archive runs with checkout/Python/uv absent from PATH."""
    import platform

    asset_name = select_platform_asset(platform.system(), platform.machine())
    archive_path = PROJECT_ROOT / "dist" / asset_name
    checksums_path = PROJECT_ROOT / "dist" / "SHA256SUMS"

    if not archive_path.is_file():
        pytest.skip(
            f"No native archive at {archive_path}. CI does not build PyInstaller "
            "archives yet; build one first with "
            "scripts.probe_installed_artifacts.build_release_archive from a PyInstaller "
            "--onefile executable to exercise this probe locally."
        )

    assert verify_archive_checksum(archive_path, checksums_path) is True

    result = probe_native_artifact(archive_path, PROJECT_ROOT, tmp_path)

    assert result.status == "passed", f"Native artifact probe failed: {result.stderr}"
    assert result.origin_verified is True
    assert result.mcp_initialized is True
    assert result.stdout.strip() == _project_version()
