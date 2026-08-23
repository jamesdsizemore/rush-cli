"""Unit tests for Phase 50 SLSA Attestation, License Matrix, IAM Audit, Dead Asset, and PR Synthesizer."""

from pathlib import Path

from src.rush.tools.attest import SLSAAttestationGenerator
from src.rush.tools.dead_asset import DeadAssetScanner
from src.rush.tools.iam_audit import IamPolicySynthesizer
from src.rush.tools.license_matrix import LicenseMatrixScanner
from src.rush.tools.pr_synthesize import PrSynthesizer


def test_slsa_attestation_generator(tmp_path: Path):
    dummy_bin = tmp_path / "rush.whl"
    dummy_bin.write_bytes(b"binary content for packaging")

    gen = SLSAAttestationGenerator(project_root=tmp_path)
    stmt = gen.generate_attestation(dummy_bin)

    assert stmt["_type"] == "https://in-toto.io/Statement/v0.1"
    assert stmt["predicateType"] == "https://slsa.dev/provenance/v0.2"
    assert stmt["subject"][0]["name"] == "rush.whl"
    assert "sha256" in stmt["subject"][0]["digest"]
    assert stmt["predicate"]["metadata"]["reproducible"] is True


def test_license_matrix_scanner(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
dependencies = [
    "pydantic>=2.0",
    "click>=8.0",
]
""",
        encoding="utf-8",
    )

    scanner = LicenseMatrixScanner(project_root=tmp_path)
    res = scanner.scan_licenses()

    assert res["total_packages"] >= 2
    assert res["copyleft_violations_count"] == 0


def test_iam_policy_synthesizer(tmp_path: Path):
    synth = IamPolicySynthesizer(project_root=tmp_path)
    policy = synth.synthesize_policy()

    assert policy["Version"] == "2012-10-17"
    assert len(policy["Statement"]) > 0
    assert "s3:GetObject" in policy["Statement"][0]["Action"]


def test_dead_asset_scanner(tmp_path: Path):
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "logo_used.png").write_bytes(b"used")
    (assets_dir / "dead_icon.svg").write_bytes(b"dead")

    src_file = tmp_path / "index.html"
    src_file.write_text('<img src="assets/logo_used.png">', encoding="utf-8")

    scanner = DeadAssetScanner(project_root=tmp_path)
    res = scanner.scan_dead_assets()

    assert res["total_assets"] == 2
    assert res["dead_assets_count"] == 1
    assert any("dead_icon.svg" in a for a in res["dead_assets"])


def test_pr_synthesizer(tmp_path: Path):
    synth = PrSynthesizer(project_root=tmp_path)
    card = synth.synthesize_pr_card(base_branch="HEAD")

    assert "SLSA Provenance" in card
    assert "Architecture Guard" in card
