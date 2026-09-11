"""Tests for Phase 65 P65-02: complete applicable toolchain provisioning.

Covers the declarative registry (§6.2 exhaustiveness), the uv/pip, npm/yarn,
crates, RubyGems, Composer, Maven, Go-source and native-binary (GitHub)
manager families, the immutable plan builder, the tamper-detecting manifest
binding in `rush.runtime.binaries`, and the fail-closed apply path.

Real network downloads are not exercised here (sandboxed environment); every
resolver/downloader/runner/prober is exercised through its injectable seam
using saved-shape fixtures, per the plan's own "runtime network resolution
tests use saved official metadata fixtures" contract.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

import pytest

from rush.catalog import ENGINE_SPECS
from rush.permissions import ExecutionPermissions
from rush.runtime.binaries import (
    ManifestVerificationError,
    ProvisionManifest,
    clear_manifest_cache,
    compute_file_sha256,
    read_manifest,
    resolve_project_binary,
    verify_manifest,
    write_manifest,
)
from rush.setup.engine_packages import (
    ENGINE_PACKAGES,
    OS_PACKAGE_NAMES,
    RUNTIME_PACKAGES,
    UnknownEngineError,
    UnknownProjectManagerError,
    resolve_engine_package,
    resolve_project_manager_command,
)
from rush.setup.provision import (
    ProvisionError,
    _destination_for,
    apply_provision_plan,
    build_provision_plan,
    current_os_arch,
)

# --- Registry exhaustiveness -------------------------------------------------


def test_engine_packages_covers_exactly_all_121_engine_specs_keys() -> None:
    assert set(ENGINE_PACKAGES.keys()) == set(ENGINE_SPECS.keys())
    assert len(ENGINE_PACKAGES) == 121


@pytest.mark.parametrize("engine_id", sorted(ENGINE_SPECS.keys()))
def test_every_engine_spec_key_resolves_without_arbitrary_override(
    engine_id: str,
) -> None:
    package = resolve_engine_package(engine_id)
    assert package.engine_id == engine_id
    assert package.source in (
        "pypi",
        "npm",
        "crates",
        "gem",
        "composer",
        "maven",
        "go",
        "github",
        "alias",
        "internal",
    )
    assert package.package_id  # never empty


def test_uv_pip_family_uses_pypi_source_and_uv_manager() -> None:
    for engine_id in ("ruff", "pytest", "pip-audit", "mypy"):
        pkg = ENGINE_PACKAGES[engine_id]
        assert pkg.source == "pypi"
        assert pkg.manager == "uv"
        assert pkg.package_id == engine_id
        assert pkg.prerequisites == ("uv", "python")


def test_npm_yarn_family_uses_npm_source_and_canonical_identities() -> None:
    assert ENGINE_PACKAGES["eslint"].source == "npm"
    assert ENGINE_PACKAGES["prettier"].source == "npm"
    assert ENGINE_PACKAGES["biome"].package_id == "@biomejs/biome"
    assert ENGINE_PACKAGES["tsc"].package_id == "typescript"
    assert ENGINE_PACKAGES["playwright"].package_id == "@playwright/test"
    for engine_id in ("eslint", "prettier", "biome", "tsc"):
        assert ENGINE_PACKAGES[engine_id].prerequisites == ("node", "npm")


def test_go_source_build_family() -> None:
    pkg = ENGINE_PACKAGES["zally"]
    assert pkg.source == "go"
    assert pkg.package_id == "zalando/zally"
    assert pkg.version_policy == "pinned:v2.1.1"
    assert pkg.prerequisites == ("go",)


def test_composer_family() -> None:
    pkg = ENGINE_PACKAGES["infection"]
    assert pkg.source == "composer"
    assert pkg.package_id == "infection/infection"
    assert pkg.prerequisites == ("php", "composer")


def test_mix_prerequisite_declared_as_runtime_package() -> None:
    assert "mix" in RUNTIME_PACKAGES
    assert "elixir" in RUNTIME_PACKAGES


def test_maven_gradle_family() -> None:
    pitest = ENGINE_PACKAGES["pitest"]
    assert pitest.source == "maven"
    assert pitest.package_id == "org.pitest:pitest-maven"
    assert pitest.scan_class == "project_bound"
    assert "gradle" in RUNTIME_PACKAGES
    assert "maven" in RUNTIME_PACKAGES


def test_native_binary_github_family() -> None:
    for engine_id, repo in (
        ("osv-scanner", "google/osv-scanner"),
        ("gitleaks", "gitleaks/gitleaks"),
        ("trivy", "aquasecurity/trivy"),
    ):
        pkg = ENGINE_PACKAGES[engine_id]
        assert pkg.source == "github"
        assert pkg.package_id == repo
        assert pkg.manager == "github"
        assert pkg.prerequisites == ()


def test_crates_family() -> None:
    for engine_id in ("cargo-mutants", "clines"):
        pkg = ENGINE_PACKAGES[engine_id]
        assert pkg.source == "crates"
        assert pkg.package_id == engine_id
        assert pkg.prerequisites == ("rust", "cargo")


def test_gem_family() -> None:
    pkg = ENGINE_PACKAGES["undercover"]
    assert pkg.source == "gem"
    assert pkg.prerequisites == ("ruby",)


def test_alias_engines_do_not_install_a_separate_package() -> None:
    assert ENGINE_PACKAGES["npm-audit"].source == "alias"
    assert ENGINE_PACKAGES["npm-audit"].package_id == "node/npm"
    assert ENGINE_PACKAGES["git-guard"].source == "alias"
    assert ENGINE_PACKAGES["git-guard"].package_id == "git"


def test_internal_target_adapter_never_installs_fictional_executable() -> None:
    pkg = ENGINE_PACKAGES["semantic-drift"]
    assert pkg.source == "internal"
    assert pkg.scan_class == "target_adapter"


def test_unknown_engine_rejected_everywhere() -> None:
    with pytest.raises(UnknownEngineError):
        resolve_engine_package("nonexistent-engine")
    assert "nonexistent-engine" not in ENGINE_PACKAGES


def test_os_prerequisite_packages_exact_names() -> None:
    assert OS_PACKAGE_NAMES["php"]["winget"] == "PHP.PHP.8.4"
    assert OS_PACKAGE_NAMES["ruby"]["winget"] == "RubyInstallerTeam.Ruby.3.4"
    assert OS_PACKAGE_NAMES["erlang"]["apt"] == "erlang-base"
    assert OS_PACKAGE_NAMES["git"]["brew"] == "git"


def test_project_manager_commands_are_lockfile_preserving() -> None:
    assert resolve_project_manager_command("npm").argv == (
        "npm",
        "ci",
        "--ignore-scripts",
    )
    assert resolve_project_manager_command("uv").argv == ("uv", "sync", "--frozen")
    assert resolve_project_manager_command("go").argv == ("go", "mod", "download")
    assert resolve_project_manager_command("composer").isolation_supported is True
    assert resolve_project_manager_command("maven").isolation_supported is True
    with pytest.raises(UnknownProjectManagerError):
        resolve_project_manager_command("some-arbitrary-manager")


# --- Plan building ------------------------------------------------------


def test_build_provision_plan_rejects_unknown_engine(tmp_path: Path) -> None:
    with pytest.raises(UnknownEngineError):
        build_provision_plan(tmp_path, ["ruff", "not-a-real-engine"])


def test_build_provision_plan_is_deterministic(tmp_path: Path) -> None:
    plan_a = build_provision_plan(
        tmp_path, ["ruff", "eslint"], os_name="linux", arch="x86_64"
    )
    plan_b = build_provision_plan(
        tmp_path, ["ruff", "eslint"], os_name="linux", arch="x86_64"
    )
    assert plan_a.plan_id == plan_b.plan_id


def test_build_provision_plan_marks_internal_engine_requires_input(
    tmp_path: Path,
) -> None:
    plan = build_provision_plan(tmp_path, ["semantic-drift"])
    assert plan.entries[0].disposition == "requires_input"


def test_build_provision_plan_required_grants_include_build_for_source_installs(
    tmp_path: Path,
) -> None:
    plan = build_provision_plan(tmp_path, ["zally"])
    assert "build" in plan.entries[0].required_grants


# --- Resolver error codes (fixture-based, no live network) -----------------


def test_resolve_identity_pypi_package_not_found(tmp_path: Path) -> None:
    from urllib.error import HTTPError

    from rush.setup.provision import resolve_identity

    engine = ENGINE_PACKAGES["ruff"]

    def http_get_404(url: str) -> bytes:
        raise HTTPError(url, 404, "not found", None, None)  # type: ignore[arg-type]

    with pytest.raises(ProvisionError) as exc_info:
        resolve_identity(engine, os_name="linux", arch="x86_64", http_get=http_get_404)
    assert exc_info.value.code == "PACKAGE_NOT_FOUND"


def test_resolve_identity_npm_missing_integrity_is_unavailable() -> None:
    from rush.setup.provision import resolve_identity

    engine = ENGINE_PACKAGES["eslint"]

    def http_get(url: str) -> bytes:
        return json.dumps(
            {"dist-tags": {"latest": "1.0.0"}, "versions": {"1.0.0": {"dist": {}}}}
        ).encode()

    with pytest.raises(ProvisionError) as exc_info:
        resolve_identity(engine, os_name="linux", arch="x86_64", http_get=http_get)
    assert exc_info.value.code == "INTEGRITY_UNAVAILABLE"


def test_resolve_identity_github_no_compatible_asset() -> None:
    from rush.setup.provision import resolve_identity

    engine = ENGINE_PACKAGES["osv-scanner"]

    def http_get(url: str) -> bytes:
        return json.dumps(
            {
                "tag_name": "v1.0.0",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {
                        "name": "osv-scanner_windows_arm64.zip",
                        "browser_download_url": "u",
                    }
                ],
            }
        ).encode()

    with pytest.raises(ProvisionError) as exc_info:
        resolve_identity(engine, os_name="linux", arch="x86_64", http_get=http_get)
    assert exc_info.value.code == "NO_COMPATIBLE_ASSET"


def test_resolve_identity_github_ambiguous_asset() -> None:
    from rush.setup.provision import resolve_identity

    engine = ENGINE_PACKAGES["osv-scanner"]

    def http_get(url: str) -> bytes:
        return json.dumps(
            {
                "tag_name": "v1.0.0",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {
                        "name": "osv-scanner_linux_amd64.tar.gz",
                        "browser_download_url": "u1",
                        "digest": "sha256:a",
                    },
                    {
                        "name": "osv-scanner_linux_amd64_v2.tar.gz",
                        "browser_download_url": "u2",
                        "digest": "sha256:b",
                    },
                ],
            }
        ).encode()

    with pytest.raises(ProvisionError) as exc_info:
        resolve_identity(engine, os_name="linux", arch="x86_64", http_get=http_get)
    assert exc_info.value.code == "AMBIGUOUS_ASSET"


def test_resolve_identity_github_draft_release_is_version_unavailable() -> None:
    from rush.setup.provision import resolve_identity

    engine = ENGINE_PACKAGES["osv-scanner"]

    def http_get(url: str) -> bytes:
        return json.dumps(
            {"tag_name": "v1.0.0", "draft": True, "prerelease": False, "assets": []}
        ).encode()

    with pytest.raises(ProvisionError) as exc_info:
        resolve_identity(engine, os_name="linux", arch="x86_64", http_get=http_get)
    assert exc_info.value.code == "VERSION_UNAVAILABLE"


def test_resolve_identity_crates_no_non_yanked_version() -> None:
    from rush.setup.provision import resolve_identity

    engine = ENGINE_PACKAGES["cargo-mutants"]

    def http_get(url: str) -> bytes:
        return json.dumps({"versions": [{"num": "1.0.0", "yanked": True}]}).encode()

    with pytest.raises(ProvisionError) as exc_info:
        resolve_identity(engine, os_name="linux", arch="x86_64", http_get=http_get)
    assert exc_info.value.code == "VERSION_UNAVAILABLE"


# --- Apply: GitHub native-binary family (real download+verify+extract logic) --


def _github_release_fixture(archive_bytes: bytes, asset_name: str) -> bytes:
    digest = hashlib.sha256(archive_bytes).hexdigest()
    return json.dumps(
        {
            "tag_name": "v1.2.3",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": asset_name,
                    "browser_download_url": "https://example.com/asset.tar.gz",
                    "digest": f"sha256:{digest}",
                }
            ],
        }
    ).encode()


def _make_tar_gz(binary_name: str, content: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name=binary_name)
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def test_apply_github_engine_downloads_verifies_extracts_and_binds_manifest(
    tmp_path: Path,
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    data_root = tmp_path / "data"

    binary_bytes = b"#!/bin/sh\necho osv-scanner v1.2.3\n"
    archive = _make_tar_gz("osv-scanner", binary_bytes)

    def http_get(url: str) -> bytes:
        return _github_release_fixture(archive, "osv-scanner_linux_x86_64.tar.gz")

    def downloader(url: str) -> bytes:
        return archive

    def prober(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            argv, 0, stdout="osv-scanner 1.2.3", stderr=""
        )

    plan = build_provision_plan(
        project, ["osv-scanner"], os_name="linux", arch="x86_64"
    )
    result = apply_provision_plan(
        plan,
        ExecutionPermissions(network=True, download=True, cache_write=True),
        project_id="proj-a",
        data_root=data_root,
        http_get=http_get,
        downloader=downloader,
        prober=prober,
    )
    assert result.failed == {}
    manifest = result.applied["osv-scanner"]
    assert manifest.version == "v1.2.3"
    assert Path(manifest.executable).is_file()
    assert manifest.executable_sha256 == compute_file_sha256(Path(manifest.executable))
    assert manifest.project_root == str(project.resolve())

    resolved = resolve_project_binary("osv-scanner", project)
    assert resolved == manifest.executable


def test_apply_github_engine_fails_closed_on_checksum_mismatch(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    binary_bytes = b"payload"
    archive = _make_tar_gz("gitleaks", binary_bytes)

    def http_get(url: str) -> bytes:
        # Publish a digest that does not match the archive actually downloaded.
        return json.dumps(
            {
                "tag_name": "v1.0.0",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {
                        "name": "gitleaks_linux_x86_64.tar.gz",
                        "browser_download_url": "u",
                        "digest": "sha256:" + ("0" * 64),
                    }
                ],
            }
        ).encode()

    plan = build_provision_plan(project, ["gitleaks"], os_name="linux", arch="x86_64")
    result = apply_provision_plan(
        plan,
        ExecutionPermissions(network=True, download=True, cache_write=True),
        project_id="proj-a",
        data_root=tmp_path / "data",
        http_get=http_get,
        downloader=lambda url: archive,
        prober=lambda argv: subprocess.CompletedProcess(
            argv, 0, stdout="ok", stderr=""
        ),
    )
    assert "gitleaks" not in result.applied
    assert result.failed["gitleaks"]["code"] == "INTEGRITY_MISMATCH"


def test_apply_never_reports_ready_when_probe_fails(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    binary_bytes = b"payload"
    archive = _make_tar_gz("gitleaks", binary_bytes)

    plan = build_provision_plan(project, ["gitleaks"], os_name="linux", arch="x86_64")
    result = apply_provision_plan(
        plan,
        ExecutionPermissions(network=True, download=True, cache_write=True),
        project_id="proj-a",
        data_root=tmp_path / "data",
        http_get=lambda url: _github_release_fixture(
            archive, "gitleaks_linux_x86_64.tar.gz"
        ),
        downloader=lambda url: archive,
        prober=lambda argv: subprocess.CompletedProcess(
            argv, 1, stdout="", stderr="crash"
        ),
    )
    assert "gitleaks" not in result.applied
    assert result.failed["gitleaks"]["code"] == "ENGINE_PROTOCOL_MISMATCH"
    assert resolve_project_binary("gitleaks", project) is None


def test_apply_permission_blocked_reports_missing_grants(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    plan = build_provision_plan(
        project, ["osv-scanner"], os_name="linux", arch="x86_64"
    )
    result = apply_provision_plan(
        plan,
        ExecutionPermissions(),  # no grants at all
        project_id="proj-a",
        data_root=tmp_path / "data",
    )
    assert result.applied == {}
    assert "--allow-network" in result.permission_blocked["osv-scanner"]


def test_apply_missing_manager_reports_exact_unresolved_prerequisite(
    tmp_path: Path,
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    plan = build_provision_plan(project, ["ruff"], os_name="linux", arch="x86_64")

    def http_get(url: str) -> bytes:
        return json.dumps(
            {
                "info": {"version": "1.0.0"},
                "releases": {
                    "1.0.0": [
                        {
                            "packagetype": "bdist_wheel",
                            "url": "u",
                            "digests": {"sha256": "a"},
                        }
                    ]
                },
            }
        ).encode()

    result = apply_provision_plan(
        plan,
        ExecutionPermissions(network=True, download=True, cache_write=True),
        project_id="proj-a",
        data_root=tmp_path / "data",
        http_get=http_get,
        which=lambda name: None,  # ambient PATH stripped: no manager found
    )
    assert result.failed["ruff"]["code"] == "SYSTEM_PREREQUISITE_REQUIRED"
    assert "uv" in result.failed["ruff"]["message"]


def test_two_projects_select_different_compatible_versions_without_collision(
    tmp_path: Path,
) -> None:
    project_a = tmp_path / "proj-a"
    project_a.mkdir()
    project_b = tmp_path / "proj-b"
    project_b.mkdir()
    data_root = tmp_path / "data"

    def make_release(version: str, content: bytes) -> tuple[bytes, bytes]:
        archive = _make_tar_gz("osv-scanner", content)
        return archive, _github_release_fixture(
            archive, "osv-scanner_linux_x86_64.tar.gz"
        ).replace(b"v1.2.3", version.encode())

    archive_a, release_a = make_release("v1.0.0", b"binary-a")
    archive_b, release_b = make_release("v2.0.0", b"binary-b")

    plan_a = build_provision_plan(
        project_a, ["osv-scanner"], os_name="linux", arch="x86_64"
    )
    result_a = apply_provision_plan(
        plan_a,
        ExecutionPermissions(network=True, download=True, cache_write=True),
        project_id="proj-a",
        data_root=data_root,
        http_get=lambda url: release_a,
        downloader=lambda url: archive_a,
        prober=lambda argv: subprocess.CompletedProcess(
            argv, 0, stdout="ok v1.0.0", stderr=""
        ),
    )
    plan_b = build_provision_plan(
        project_b, ["osv-scanner"], os_name="linux", arch="x86_64"
    )
    result_b = apply_provision_plan(
        plan_b,
        ExecutionPermissions(network=True, download=True, cache_write=True),
        project_id="proj-b",
        data_root=data_root,
        http_get=lambda url: release_b,
        downloader=lambda url: archive_b,
        prober=lambda argv: subprocess.CompletedProcess(
            argv, 0, stdout="ok v2.0.0", stderr=""
        ),
    )

    manifest_a = result_a.applied["osv-scanner"]
    manifest_b = result_b.applied["osv-scanner"]
    assert manifest_a.version != manifest_b.version
    assert manifest_a.executable != manifest_b.executable
    assert Path(manifest_a.executable).is_file()
    assert Path(manifest_b.executable).is_file()

    assert resolve_project_binary("osv-scanner", project_a) == manifest_a.executable
    assert resolve_project_binary("osv-scanner", project_b) == manifest_b.executable


def test_retry_after_interrupted_download_leaves_no_partial_manifest(
    tmp_path: Path,
) -> None:
    """A download interrupted/corrupted mid-transfer fails closed on the digest

    check before any bytes are written to the toolchain destination, and a
    subsequent retry with a good transfer succeeds cleanly.
    """
    project = tmp_path / "proj"
    project.mkdir()
    data_root = tmp_path / "data"
    binary_bytes = b"good-binary"
    archive = _make_tar_gz("osv-scanner", binary_bytes)

    calls: list[int] = []

    def flaky_downloader(url: str) -> bytes:
        calls.append(1)
        if len(calls) == 1:
            return b"CORRUPTED-INTERRUPTED-TRANSFER"
        return archive

    def http_get(url: str) -> bytes:
        return _github_release_fixture(archive, "osv-scanner_linux_x86_64.tar.gz")

    plan = build_provision_plan(
        project, ["osv-scanner"], os_name="linux", arch="x86_64"
    )
    first_result = apply_provision_plan(
        plan,
        ExecutionPermissions(network=True, download=True, cache_write=True),
        project_id="proj-a",
        data_root=data_root,
        http_get=http_get,
        downloader=flaky_downloader,
        prober=lambda argv: subprocess.CompletedProcess(
            argv, 0, stdout="ok", stderr=""
        ),
    )
    assert first_result.failed["osv-scanner"]["code"] == "INTEGRITY_MISMATCH"
    dest_dir = _destination_for(data_root, "osv-scanner", "v1.2.3", "linux", "x86_64")
    assert not (dest_dir / "manifest.json").exists()

    plan_retry = build_provision_plan(
        project, ["osv-scanner"], os_name="linux", arch="x86_64"
    )
    result = apply_provision_plan(
        plan_retry,
        ExecutionPermissions(network=True, download=True, cache_write=True),
        project_id="proj-a",
        data_root=data_root,
        http_get=http_get,
        downloader=flaky_downloader,
        prober=lambda argv: subprocess.CompletedProcess(
            argv, 0, stdout="ok", stderr=""
        ),
    )
    assert "osv-scanner" in result.applied


def test_retry_after_interrupted_manager_install_cleans_partial_directory(
    tmp_path: Path,
) -> None:
    """A manager-command install that writes partial files then crashes

    (e.g. the probe fails) leaves no manifest; retrying cleans the stale
    partial directory and can then succeed without manual intervention.
    """
    project = tmp_path / "proj"
    project.mkdir()
    data_root = tmp_path / "data"

    def http_get(url: str) -> bytes:
        return json.dumps(
            {
                "info": {"version": "1.0.0"},
                "releases": {
                    "1.0.0": [
                        {
                            "packagetype": "bdist_wheel",
                            "url": "u",
                            "digests": {"sha256": "a"},
                        }
                    ]
                },
            }
        ).encode()

    def runner_writes_junk(
        argv: list[str], env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        dest_dir = _destination_for(data_root, "ruff", "1.0.0", "linux", "x86_64")
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "ruff").write_bytes(b"partial-junk")
        return subprocess.CompletedProcess(argv, 0, stdout="installed", stderr="")

    plan = build_provision_plan(project, ["ruff"], os_name="linux", arch="x86_64")
    first_result = apply_provision_plan(
        plan,
        ExecutionPermissions(network=True, download=True, cache_write=True),
        project_id="proj-a",
        data_root=data_root,
        http_get=http_get,
        runner=runner_writes_junk,
        prober=lambda argv: subprocess.CompletedProcess(
            argv, 1, stdout="", stderr="crash mid-probe"
        ),
    )
    assert first_result.failed["ruff"]["code"] == "ENGINE_PROTOCOL_MISMATCH"
    dest_dir = _destination_for(data_root, "ruff", "1.0.0", "linux", "x86_64")
    assert dest_dir.is_dir()
    assert not (dest_dir / "manifest.json").exists()

    plan_retry = build_provision_plan(project, ["ruff"], os_name="linux", arch="x86_64")
    retry_result = apply_provision_plan(
        plan_retry,
        ExecutionPermissions(network=True, download=True, cache_write=True),
        project_id="proj-a",
        data_root=data_root,
        http_get=http_get,
        runner=runner_writes_junk,
        prober=lambda argv: subprocess.CompletedProcess(
            argv, 0, stdout="ruff 1.0.0", stderr=""
        ),
    )
    assert "ruff" in retry_result.applied


# --- Manifest binding / tamper detection (rush.runtime.binaries) -----------


def test_manifest_roundtrip(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    toolchain_dir = tmp_path / "toolchains" / "ruff" / "1.0.0"
    exe = toolchain_dir / "ruff"
    toolchain_dir.mkdir(parents=True)
    exe.write_bytes(b"binary-bytes")

    manifest = ProvisionManifest(
        schema_version=1,
        engine_id="ruff",
        package_id="ruff",
        version="1.0.0",
        source="pypi",
        manager="uv",
        executable=str(exe),
        executable_sha256=compute_file_sha256(exe),
        os_name="linux",
        arch="x86_64",
        project_id="p1",
        project_root=str(project.resolve()),
        runtime_identity="uv 1.0.0",
        plan_id="plan1",
        created_at="2026-01-01T00:00:00Z",
    )
    path = write_manifest(toolchain_dir, manifest)
    loaded = read_manifest(path)
    assert loaded == manifest
    verify_manifest(loaded, project_root=project)  # does not raise


def test_verify_manifest_fails_closed_on_hash_mismatch(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    toolchain_dir = tmp_path / "toolchains" / "ruff" / "1.0.0"
    exe = toolchain_dir / "ruff"
    toolchain_dir.mkdir(parents=True)
    exe.write_bytes(b"original-bytes")

    manifest = ProvisionManifest(
        schema_version=1,
        engine_id="ruff",
        package_id="ruff",
        version="1.0.0",
        source="pypi",
        manager="uv",
        executable=str(exe),
        executable_sha256=compute_file_sha256(exe),
        os_name="linux",
        arch="x86_64",
        project_id="p1",
        project_root=str(project.resolve()),
        runtime_identity="uv 1.0.0",
        plan_id="plan1",
        created_at="2026-01-01T00:00:00Z",
    )
    write_manifest(toolchain_dir, manifest)

    exe.write_bytes(b"TAMPERED-BYTES")
    clear_manifest_cache()
    reloaded = read_manifest(toolchain_dir / "manifest.json")
    assert reloaded is not None
    with pytest.raises(ManifestVerificationError) as exc_info:
        verify_manifest(reloaded, project_root=project)
    assert exc_info.value.code == "HASH_MISMATCH"


def test_verify_manifest_fails_closed_on_scope_mismatch(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    other_project = tmp_path / "other"
    other_project.mkdir()
    toolchain_dir = tmp_path / "toolchains" / "ruff" / "1.0.0"
    exe = toolchain_dir / "ruff"
    toolchain_dir.mkdir(parents=True)
    exe.write_bytes(b"bytes")

    manifest = ProvisionManifest(
        schema_version=1,
        engine_id="ruff",
        package_id="ruff",
        version="1.0.0",
        source="pypi",
        manager="uv",
        executable=str(exe),
        executable_sha256=compute_file_sha256(exe),
        os_name="linux",
        arch="x86_64",
        project_id="p1",
        project_root=str(project.resolve()),
        runtime_identity="uv 1.0.0",
        plan_id="plan1",
        created_at="2026-01-01T00:00:00Z",
    )
    write_manifest(toolchain_dir, manifest)
    with pytest.raises(ManifestVerificationError) as exc_info:
        verify_manifest(manifest, project_root=other_project)
    assert exc_info.value.code == "SCOPE_MISMATCH"


def test_resolve_project_binary_missing_selection_returns_none(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    assert resolve_project_binary("ruff", project) is None


def test_resolve_project_binary_incompatible_schema_fails_closed(
    tmp_path: Path,
) -> None:
    project = tmp_path / "proj"
    (project / ".rush").mkdir(parents=True)
    toolchain_dir = tmp_path / "toolchains" / "ruff" / "1.0.0"
    exe = toolchain_dir / "ruff"
    toolchain_dir.mkdir(parents=True)
    exe.write_bytes(b"bytes")

    manifest_path = toolchain_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 999,
                "engine_id": "ruff",
                "package_id": "ruff",
                "version": "1.0.0",
                "source": "pypi",
                "manager": "uv",
                "executable": str(exe),
                "executable_sha256": compute_file_sha256(exe),
                "os_name": "linux",
                "arch": "x86_64",
                "project_id": "p1",
                "project_root": str(project.resolve()),
                "runtime_identity": "uv 1.0.0",
                "plan_id": "plan1",
                "created_at": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (project / ".rush" / "toolchains.json").write_text(
        json.dumps({"ruff": {"manifest": str(manifest_path)}}), encoding="utf-8"
    )
    assert resolve_project_binary("ruff", project) is None


def test_resolve_binary_falls_through_to_path_when_manifest_absent(
    tmp_path: Path,
) -> None:
    from rush.runtime.binaries import resolve_binary

    project = tmp_path / "proj"
    project.mkdir()
    # No .rush/toolchains.json at all -- must not raise, must fall through.
    result = resolve_binary(
        "definitely-not-a-real-binary-xyz", engine_id="ruff", project_root=project
    )
    assert result is None


def test_current_os_arch_returns_normalized_values() -> None:
    os_name, arch = current_os_arch()
    assert os_name in ("macos", "linux", "windows")
    assert arch in ("x86_64", "arm64")
