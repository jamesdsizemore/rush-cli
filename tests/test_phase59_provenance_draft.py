"""Phase 59 Workstream P59.1 Contract Tests: Truthful Unsigned Provenance Drafts."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from rush.permissions import ExecutionPermissions
from rush.tools.attest import AttestationTool


def test_default_output_is_explicit_unsigned_draft(tmp_path: Path) -> None:
    """T-59.01: Default output is an explicit unsigned draft with no fabricated SLSA Level 3 claims."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    whl_file = dist_dir / "rush-0.3.0-py3-none-any.whl"
    whl_file.write_bytes(b"binary content for unsigned draft test")

    tool = AttestationTool()
    res = tool.run(tmp_path)

    assert res["status"] == "ok"
    assert "draft" in res["summary"].lower()
    assert (
        res["summary"]
        == "Generated unsigned in-toto v1 SLSA Provenance v1 draft statement for rush-0.3.0-py3-none-any.whl"
    )

    metadata = res.get("metadata", {})
    assert "statement" in metadata
    statement = metadata["statement"]

    assert statement["_type"] == "https://in-toto.io/Statement/v1"
    assert statement["predicateType"] == "https://slsa.dev/provenance/v1"
    run_meta = statement["predicate"]["runDetails"]["metadata"]
    assert run_meta["assurance"] == "unsigned_draft"

    # Must NOT claim SLSA Level 3
    assert "SLSA Level 3" not in str(statement)
    assert "SLSA Level 3" not in res["summary"]
    assert "SLSA Level 3" not in str(metadata)

    # Must NOT claim to be signed
    assert metadata.get("is_signed") is False
    assert "signatures" not in statement or statement.get("signatures") == []
    assert "signatures" not in metadata or metadata.get("signatures") == []


def test_subject_is_actual_artifact_and_package_identity(tmp_path: Path) -> None:
    """T-59.02: Subject identity is the actual distribution package and exact byte digest."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    whl_bytes = b"sample wheel payload content"
    tar_bytes = b"sample source distribution tarball content"

    whl_file = dist_dir / "rush-0.3.0-py3-none-any.whl"
    whl_file.write_bytes(whl_bytes)
    tar_file = dist_dir / "rush-0.3.0.tar.gz"
    tar_file.write_bytes(tar_bytes)

    tool = AttestationTool()
    res = tool.run(tmp_path)

    assert res["status"] == "ok"
    statement = res["metadata"]["statement"]
    subject = statement["subject"][0]

    assert subject["name"] in ("rush-0.3.0-py3-none-any.whl", "rush-0.3.0.tar.gz")

    if subject["name"] == "rush-0.3.0-py3-none-any.whl":
        expected_digest = hashlib.sha256(whl_bytes).hexdigest()
    else:
        expected_digest = hashlib.sha256(tar_bytes).hexdigest()

    assert subject["digest"]["sha256"] == expected_digest

    # Asserts git commit hash is NOT used as subject name or digest
    commit = statement["predicate"]["buildDefinition"]["externalParameters"]["commit"]
    assert not re.match(r"^[0-9a-f]{40}$", subject["name"])
    assert subject["digest"]["sha256"] != commit


def test_missing_evidence_never_fabricates_claim(tmp_path: Path) -> None:
    """T-59.03: Missing package evidence returns skipped result without fabricating statements."""
    empty_dir = tmp_path / "empty_workspace"
    empty_dir.mkdir(parents=True, exist_ok=True)

    tool = AttestationTool()
    res = tool.run(empty_dir)

    assert res["status"] == "skipped"
    assert res["findings"] == []
    assert "no built package (.whl, .tar.gz) found" in res["summary"]
    assert res.get("raw") is None or res.get("raw") == {}
    assert "statement" not in res.get("metadata", {})


def test_draft_envelope_conforms_to_sanitizer_contract(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """T-59.04: Draft envelope passes through sanitizer contract with zero leaked secrets or unredacted paths."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    whl_file = dist_dir / "rush-0.3.0-py3-none-any.whl"
    whl_file.write_bytes(b"package bytes for sanitization test")

    secret_token = "ghp_SECRETTOKEN12345678901234567890"
    fake_remote = f"https://bot:{secret_token}@github.com/rush-cli/rush.git"

    def mock_run_subprocess(
        cmd: list[str], cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        if "remote.origin.url" in cmd:
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout=fake_remote, stderr=""
            )
        if "rev-parse" in cmd:
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="a" * 40, stderr=""
            )
        return subprocess.CompletedProcess(
            args=cmd, returncode=1, stdout="", stderr="error"
        )

    monkeypatch.setattr("rush.tools.attest.run_subprocess", mock_run_subprocess)

    output_file = "provenance-draft.json"
    tool = AttestationTool()
    perms = ExecutionPermissions(artifact_write=True)
    res = tool.run(tmp_path, output_path=output_file, permissions=perms)

    assert res["status"] == "ok"

    raw_text = json.dumps(res.get("raw", {}))
    meta_text = json.dumps(res.get("metadata", {}))
    file_text = (tmp_path / output_file).read_text(encoding="utf-8")

    assert secret_token not in raw_text
    assert secret_token not in meta_text
    assert secret_token not in file_text

    assert "[REDACTED_GITHUB_TOKEN]" in raw_text or "[REDACTED_PASSWORD]" in raw_text
    assert "[REDACTED_GITHUB_TOKEN]" in meta_text or "[REDACTED_PASSWORD]" in meta_text
    assert "[REDACTED_GITHUB_TOKEN]" in file_text or "[REDACTED_PASSWORD]" in file_text
