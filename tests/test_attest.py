"""Unit tests for AttestationTool (PR50.5)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rush.permissions import ExecutionPermissions
from rush.tools.attest import AttestationTool, SLSAAttestationGenerator


def test_attest_tool_metadata() -> None:
    tool = AttestationTool()
    assert tool.name == "attest"
    assert "provenance" in tool.mcp_description.lower()
    assert len(tool.mcp_description) < 200


def test_attest_generates_intoto_v1_slsa_v1_statement(tmp_path: Path) -> None:
    target_file = tmp_path / "app.whl"
    target_file.write_bytes(b"package content binary")
    expected_digest = hashlib.sha256(b"package content binary").hexdigest()

    tool = AttestationTool()
    result = tool.run(tmp_path, artifact_path="app.whl")

    assert result["tool"] == "attest"
    assert result["status"] == "ok"
    assert result["findings"] == []
    assert (
        "SLSA Provenance v1" in result["summary"]
        or "in-toto" in result["summary"]
        or "draft" in result["summary"]
    )

    raw = result.get("raw") or {}
    assert raw.get("_type") == "https://in-toto.io/Statement/v1"
    assert raw.get("predicateType") == "https://slsa.dev/provenance/v1"
    assert len(raw.get("subject", [])) == 1
    assert raw["subject"][0]["name"] == "app.whl"
    assert raw["subject"][0]["digest"]["sha256"] == expected_digest

    predicate = raw.get("predicate", {})
    build_def = predicate.get("buildDefinition", {})
    assert build_def.get("buildType") == "https://rush-cli.org/build/draft/v1"
    run_details = predicate.get("runDetails", {})
    metadata = run_details.get("metadata", {})
    assert metadata.get("assurance") == "unsigned_draft"


def test_attest_direct_file_target(tmp_path: Path) -> None:
    target_file = tmp_path / "binary.tar.gz"
    target_file.write_bytes(b"binary tar archive")
    expected_digest = hashlib.sha256(b"binary tar archive").hexdigest()

    tool = AttestationTool()
    result = tool.run(target_file)

    assert result["status"] == "ok"
    raw = result.get("raw") or {}
    assert raw["subject"][0]["name"] == "binary.tar.gz"
    assert raw["subject"][0]["digest"]["sha256"] == expected_digest


def test_attest_export_requires_artifact_write_permission(tmp_path: Path) -> None:
    target_file = tmp_path / "app.whl"
    target_file.write_bytes(b"package content")

    tool = AttestationTool()
    # Without artifact_write permission
    res_skipped = tool.run(
        tmp_path,
        artifact_path="app.whl",
        output_path="provenance.json",
        permissions=ExecutionPermissions(artifact_write=False),
    )
    assert res_skipped["status"] == "skipped"
    assert (
        "artifact-write" in res_skipped["summary"]
        or "artifact_write" in res_skipped["summary"]
    )
    assert not (tmp_path / "provenance.json").exists()

    # With artifact_write permission
    res_ok = tool.run(
        tmp_path,
        artifact_path="app.whl",
        output_path="provenance.json",
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert res_ok["status"] == "ok"
    out_file = tmp_path / "provenance.json"
    assert out_file.exists()
    assert str(out_file) in res_ok.get("artifacts", [])

    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["_type"] == "https://in-toto.io/Statement/v1"


def test_attest_export_rejects_escaping_path(tmp_path: Path) -> None:
    tool = AttestationTool()
    res = tool.run(
        tmp_path,
        output_path="../outside.json",
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert res["status"] == "error"
    assert (
        "Parent traversal" in res["summary"]
        or "escapes root" in res["summary"]
        or "error" in res["summary"]
    )


def test_attest_legacy_generator_backward_compatibility(tmp_path: Path) -> None:
    dummy_bin = tmp_path / "rush.whl"
    dummy_bin.write_bytes(b"binary content for packaging")

    gen = SLSAAttestationGenerator(project_root=tmp_path)
    stmt = gen.generate_attestation(dummy_bin)

    assert stmt["_type"] == "https://in-toto.io/Statement/v1"
    assert stmt["predicateType"] == "https://slsa.dev/provenance/v1"
    assert stmt["subject"][0]["name"] == "rush.whl"
    assert "sha256" in stmt["subject"][0]["digest"]


def test_attest_auto_discovers_dist_artifacts(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    wheel_file = dist_dir / "rush_cli-0.3.0-py3-none-any.whl"
    wheel_file.write_bytes(b"built wheel binary artifact")
    expected_digest = hashlib.sha256(b"built wheel binary artifact").hexdigest()

    tool = AttestationTool()
    result = tool.run(tmp_path)

    assert result["status"] == "ok"
    raw = result.get("raw") or {}
    assert raw["subject"][0]["name"] == "rush_cli-0.3.0-py3-none-any.whl"
    assert raw["subject"][0]["digest"]["sha256"] == expected_digest
