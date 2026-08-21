"""Tests for Phase 30: Standalone Packaging, Strict SemVer & Hardened CI/CD."""

from __future__ import annotations

from pathlib import Path

from rush.release.ci_generator import CIWorkflowGenerator
from rush.release.docker_generator import DockerfileGenerator
from rush.release.multi_arch import MultiArchCoordinator
from rush.release.provenance import ArtifactProvenanceVerifier
from rush.release.semver import SemVer, SemVerValidator


def test_semver_parsing_and_bumping() -> None:
    v = SemVerValidator.parse("0.2.1-alpha.1+build.100")
    assert v is not None
    assert v.major == 0
    assert v.minor == 2
    assert v.patch == 1
    assert v.prerelease == "alpha.1"

    base = SemVer(1, 0, 0)
    assert str(base.bump_patch()) == "1.0.1"
    assert str(base.bump_minor()) == "1.1.0"
    assert str(base.bump_major()) == "2.0.0"


def test_manifest_parity_check(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.2.0"\n', encoding="utf-8")
    (tmp_path / "package.json").write_text('{"version": "0.2.0"}', encoding="utf-8")

    versions = SemVerValidator.check_manifest_parity(tmp_path)
    assert versions["pyproject.toml"] == "0.2.0"
    assert versions["package.json"] == "0.2.0"


def test_ci_workflow_generator(tmp_path: Path) -> None:
    ci_file = CIWorkflowGenerator.generate_ci_workflow(tmp_path)
    assert ci_file.exists()
    content = ci_file.read_text(encoding="utf-8")
    assert "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683" in content
    assert "actions/setup-python@42375524e23c412d93fb67b49958b491fce71c38" in content


def test_dockerfile_generator(tmp_path: Path) -> None:
    df = DockerfileGenerator.generate_dockerfile(tmp_path)
    assert df.exists()
    content = df.read_text(encoding="utf-8")
    assert "distroless" in content
    assert "USER nonroot:nonroot" in content


def test_artifact_provenance_verifier(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "rush-linux.tar.gz").write_bytes(b"dummy linux binary")
    (dist / "rush-windows.zip").write_bytes(b"dummy windows binary")

    manifest = ArtifactProvenanceVerifier.generate_checksums_manifest(dist)
    assert manifest.exists()
    lines = manifest.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "rush-linux.tar.gz" in lines[0] or "rush-linux.tar.gz" in lines[1]


def test_multi_arch_coordinator() -> None:
    targets = MultiArchCoordinator.get_supported_targets()
    assert len(targets) >= 5
    linux_target = MultiArchCoordinator.get_target_for_os("linux", "x86_64")
    assert linux_target is not None
    assert linux_target.triple == "x86_64-unknown-linux-gnu"
