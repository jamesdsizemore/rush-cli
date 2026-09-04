"""Unit tests for Phase 50 SLSA Attestation, License Matrix, IAM Audit, Dead Asset, and PR Synthesizer."""

from pathlib import Path

from rush.tools.attest import AttestationTool, SLSAAttestationGenerator
from rush.tools.dead_asset import DeadAssetScanner
from rush.tools.iam_audit import IamAuditTool, IamPolicySynthesizer
from rush.tools.license_matrix import LicenseMatrixScanner, LicenseMatrixTool
from rush.tools.pr_synthesize import PrSynthesizer


def test_slsa_attestation_generator(tmp_path: Path):
    dummy_bin = tmp_path / "rush.whl"
    dummy_bin.write_bytes(b"binary content for packaging")

    gen = SLSAAttestationGenerator(project_root=tmp_path)
    stmt = gen.generate_attestation(dummy_bin)

    assert stmt["_type"] == "https://in-toto.io/Statement/v1"
    assert stmt["predicateType"] == "https://slsa.dev/provenance/v1"
    assert stmt["subject"][0]["name"] == "rush.whl"
    assert "sha256" in stmt["subject"][0]["digest"]


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
    app_file = tmp_path / "app.py"
    app_file.write_text(
        "import boto3\ns3 = boto3.client('s3')\ns3.get_object(Bucket='my-bucket', Key='item.txt')\n",
        encoding="utf-8",
    )
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

    assert "Build Provenance" in card
    assert "Architecture Guard" in card


def test_phase50_manual_mcp_names_contain_no_business_implementations() -> None:
    import inspect

    import rush.mcp as mcp_mod

    source = inspect.getsource(mcp_mod._register_tools)
    # Ensure no manual instantiation of ad-hoc classes inside _register_tools
    assert "SLSAAttestationGenerator(" not in source
    assert "LicenseMatrixScanner(" not in source
    assert "IamPolicySynthesizer(" not in source
    assert "DeadAssetScanner(" not in source
    assert "PrSynthesizer(" not in source


def test_canonical_phase50_tools_return_canonical_result(tmp_path: Path) -> None:
    # AttestationTool with real dist artifact
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "rush-0.3.0.whl").write_bytes(b"package-data")

    attest_tool = AttestationTool()
    attest_res = attest_tool.run(tmp_path)
    assert attest_res["tool"] == "attest"
    assert attest_res["status"] == "ok"
    assert "statement" in attest_res["metadata"]

    # LicenseMatrixTool on clean repo
    lic_tool = LicenseMatrixTool()
    lic_res = lic_tool.run(tmp_path)
    assert lic_res["tool"] == "license-matrix"
    assert lic_res["status"] == "ok"

    # IamAuditTool on clean repo
    iam_tool = IamAuditTool()
    iam_res = iam_tool.run(tmp_path)
    assert iam_res["tool"] == "iam-audit"
    assert iam_res["status"] == "ok"
