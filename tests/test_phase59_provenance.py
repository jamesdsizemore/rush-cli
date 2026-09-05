"""Governance test for Phase 59: R-013 SLSA Provenance Cryptographic Verification."""

from __future__ import annotations

from pathlib import Path

import pytest

from rush.release.provenance import ArtifactProvenanceVerifier, ProvenanceError
from rush.tools.attest import AttestationTool


def test_slsa_provenance_cryptographic_verification(tmp_path: Path) -> None:
    """T-59.05 (R-013 Governance Test): Unverified draft statements return is_signed=False and unsigned verification fails closed."""
    from tests.test_phase59_provenance_draft import (
        test_default_output_is_explicit_unsigned_draft,
        test_subject_is_actual_artifact_and_package_identity,
    )

    # 1. Execute imported draft contract tests on isolated subdirectories
    draft_dir = tmp_path / "draft_run"
    draft_dir.mkdir()
    test_default_output_is_explicit_unsigned_draft(draft_dir)

    identity_dir = tmp_path / "identity_run"
    identity_dir.mkdir()
    test_subject_is_actual_artifact_and_package_identity(identity_dir)

    # 2. Run AttestationTool on real artifact
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    whl_file = dist_dir / "rush-0.3.0-py3-none-any.whl"
    whl_file.write_bytes(b"payload content for cryptographic verification test")

    tool = AttestationTool()
    res = tool.run(tmp_path)
    assert res["status"] == "ok"
    assert res["metadata"].get("is_signed") is False

    statement = res["metadata"]["statement"]

    # 3. Attempting to verify an unsigned draft without a signature raises ProvenanceError or returns is_valid=False
    with pytest.raises(ProvenanceError):
        ArtifactProvenanceVerifier.verify(statement)
