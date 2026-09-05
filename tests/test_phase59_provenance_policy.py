"""Phase 59 Workstream P59.4 Contract Tests: Signed Provenance Policy & DSSE Verification."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from rush.release import (
    BuilderMismatchError,
    DuplicateKeyError,
    ProvenanceError,
    ProvenancePolicyVerifier,
    SignedProvenancePolicy,
    SubjectMismatchError,
    UntrustedSignerError,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "remediation" / "provenance"
VALID_ENVELOPE_PATH = FIXTURES_DIR / "signed-valid-envelope.json"
INVALID_ENVELOPES_PATH = FIXTURES_DIR / "signed-invalid-envelopes.json"


def _load_valid_fixture() -> tuple[dict, str]:
    content = VALID_ENVELOPE_PATH.read_text(encoding="utf-8")
    data = json.loads(content)
    pub_key = data["publicKey"]
    return data, pub_key


def test_valid_synthetic_signed_envelope_passes_exact_policy(tmp_path: Path) -> None:
    """T-59.14: Verifies valid synthetic DSSE envelope passes exact policy and returns valid result."""
    data, pub_key = _load_valid_fixture()

    policy = SignedProvenancePolicy(
        trusted_roots=(pub_key,),
        allowed_signers=("synthetic-test-key-1",),
        allowed_builders=("https://rush-cli.org/builder/v1",),
    )
    verifier = ProvenancePolicyVerifier(policy)

    # 1. Verification with raw envelope string
    raw_str = VALID_ENVELOPE_PATH.read_text(encoding="utf-8")
    result = verifier.verify(raw_str)
    assert result.is_valid is True
    assert result.signer_id == "synthetic-test-key-1"
    assert result.builder_id == "https://rush-cli.org/builder/v1"
    assert result.statement is not None
    assert (
        result.statement.predicate.build_definition.build_type
        == "https://rush-cli.org/build/draft/v1"
    )

    # 2. Verification with expected artifact matching subject digest
    artifact_file = tmp_path / "rush-0.3.0-py3-none-any.whl"
    artifact_file.write_bytes(b"dummy wheel payload for hash matching")
    expected_sha = hashlib.sha256(artifact_file.read_bytes()).hexdigest()

    # Update subject digest to match artifact_file
    seed1 = b"TEST_ONLY_SYNTHETIC_KEY_SEED_001"
    priv1 = ed25519.Ed25519PrivateKey.from_private_bytes(seed1)

    stmt = json.loads(base64.b64decode(data["payload"]).decode("utf-8"))
    stmt["subject"][0]["digest"]["sha256"] = expected_sha
    payload_bytes = json.dumps(stmt, indent=2).encode("utf-8")
    payload_b64 = base64.b64encode(payload_bytes).decode("ascii")
    payload_type = "application/vnd.in-toto+json"
    pae = (
        f"DSSEv1 {len(payload_type)} {payload_type} {len(payload_bytes)} ".encode()
        + payload_bytes
    )
    sig = priv1.sign(pae)
    sig_b64 = base64.b64encode(sig).decode("ascii")

    matched_envelope = {
        "payloadType": payload_type,
        "payload": payload_b64,
        "signatures": [{"keyid": "synthetic-test-key-1", "sig": sig_b64}],
        "publicKey": pub_key,
        "test_marker": "TEST_ONLY_SYNTHETIC_KEY",
    }
    result_with_artifact = verifier.verify(
        json.dumps(matched_envelope), expected_artifact_path=artifact_file
    )
    assert result_with_artifact.is_valid is True
    assert result_with_artifact.subject_digest == expected_sha


def test_each_signer_builder_root_subject_type_parameter_source_mismatch_rejects(
    tmp_path: Path,
) -> None:
    """T-59.15: Tests each invalid envelope fixture; asserts appropriate typed rejection."""
    _, pub_key = _load_valid_fixture()
    invalid_data = json.loads(INVALID_ENVELOPES_PATH.read_text(encoding="utf-8"))

    policy = SignedProvenancePolicy(
        trusted_roots=(pub_key,),
        allowed_signers=("synthetic-test-key-1",),
        allowed_builders=("https://rush-cli.org/builder/v1",),
        expected_build_type="https://rush-cli.org/build/draft/v1",
        source_uri_pattern=r"^https://github\.com/rush-cli/rush.*$",
    )
    verifier = ProvenancePolicyVerifier(policy)

    # 1. Duplicate keys in envelope JSON -> DuplicateKeyError
    dup_keys_raw = invalid_data["duplicate_keys"]
    with pytest.raises(DuplicateKeyError):
        verifier.verify(dup_keys_raw)

    # 2. Untrusted signer keyid -> UntrustedSignerError
    untrusted_signer_raw = json.dumps(invalid_data["untrusted_signer"])
    with pytest.raises(UntrustedSignerError):
        verifier.verify(untrusted_signer_raw)

    # 3. Untrusted root public key -> UntrustedSignerError
    untrusted_root_raw = json.dumps(invalid_data["untrusted_root"])
    with pytest.raises(UntrustedSignerError):
        verifier.verify(untrusted_root_raw)

    # 4. Builder mismatch -> BuilderMismatchError
    builder_mismatch_raw = json.dumps(invalid_data["builder_mismatch"])
    with pytest.raises(BuilderMismatchError):
        verifier.verify(builder_mismatch_raw)

    # 5. Build type mismatch -> BuilderMismatchError
    build_type_mismatch_raw = json.dumps(invalid_data["build_type_mismatch"])
    with pytest.raises(BuilderMismatchError):
        verifier.verify(build_type_mismatch_raw)

    # 6. Source URI pattern mismatch -> ProvenanceError
    source_mismatch_raw = json.dumps(invalid_data["source_mismatch"])
    with pytest.raises(ProvenanceError):
        verifier.verify(source_mismatch_raw)

    # 7. Subject mismatch: artifact hash does not match envelope subject -> SubjectMismatchError
    artifact_file = tmp_path / "rush-0.3.0-py3-none-any.whl"
    artifact_file.write_bytes(b"content whose sha256 will not match ffff...ffff")
    subject_mismatch_raw = json.dumps(invalid_data["subject_mismatch"])
    with pytest.raises(SubjectMismatchError):
        verifier.verify(subject_mismatch_raw, expected_artifact_path=artifact_file)

    # 8. Tampered signature byte -> ProvenanceError
    tampered_sig_raw = json.dumps(invalid_data["tampered_signature"])
    with pytest.raises(ProvenanceError):
        verifier.verify(tampered_sig_raw)


def test_empty_allowlist_fails_closed() -> None:
    """T-59.16: Configures policy with empty allowlists and asserts fail-closed behavior."""
    raw_str = VALID_ENVELOPE_PATH.read_text(encoding="utf-8")
    _, pub_key = _load_valid_fixture()

    # Empty allowed_signers -> UntrustedSignerError
    policy_no_signers = SignedProvenancePolicy(
        trusted_roots=(pub_key,),
        allowed_signers=(),
        allowed_builders=("https://rush-cli.org/builder/v1",),
    )
    with pytest.raises(UntrustedSignerError):
        ProvenancePolicyVerifier(policy_no_signers).verify(raw_str)

    # Empty trusted_roots -> UntrustedSignerError
    policy_no_roots = SignedProvenancePolicy(
        trusted_roots=(),
        allowed_signers=("synthetic-test-key-1",),
        allowed_builders=("https://rush-cli.org/builder/v1",),
    )
    with pytest.raises(UntrustedSignerError):
        ProvenancePolicyVerifier(policy_no_roots).verify(raw_str)

    # Empty allowed_builders -> BuilderMismatchError
    policy_no_builders = SignedProvenancePolicy(
        trusted_roots=(pub_key,),
        allowed_signers=("synthetic-test-key-1",),
        allowed_builders=(),
    )
    with pytest.raises(BuilderMismatchError):
        ProvenancePolicyVerifier(policy_no_builders).verify(raw_str)


def test_tampered_payload_or_signature_fails_verification() -> None:
    """T-59.17: Mutating payload bytes or signature bytes causes verification rejection."""
    data, pub_key = _load_valid_fixture()
    policy = SignedProvenancePolicy(
        trusted_roots=(pub_key,),
        allowed_signers=("synthetic-test-key-1",),
        allowed_builders=("https://rush-cli.org/builder/v1",),
    )
    verifier = ProvenancePolicyVerifier(policy)

    # Tampered payload
    tampered_payload = copy.deepcopy(data)
    # Flip characters in base64 payload
    payload_chars = list(tampered_payload["payload"])
    payload_chars[20] = "X" if payload_chars[20] != "X" else "Y"
    tampered_payload["payload"] = "".join(payload_chars)
    with pytest.raises(ProvenanceError):
        verifier.verify(json.dumps(tampered_payload))

    # Tampered signature
    tampered_sig = copy.deepcopy(data)
    sig_chars = list(tampered_sig["signatures"][0]["sig"])
    sig_chars[15] = "Z" if sig_chars[15] != "Z" else "W"
    tampered_sig["signatures"][0]["sig"] = "".join(sig_chars)
    with pytest.raises(ProvenanceError):
        verifier.verify(json.dumps(tampered_sig))


def test_synthetic_fixtures_contain_zero_live_keys() -> None:
    """T-59.18: Scans all provenance fixtures to assert zero live secrets and all keys are synthetic."""
    fixture_files = list(FIXTURES_DIR.glob("*.json"))
    assert len(fixture_files) >= 3, (
        f"Expected at least 3 fixture files, found {len(fixture_files)}"
    )

    for fpath in fixture_files:
        content = fpath.read_text(encoding="utf-8")
        assert content.strip(), f"Fixture file {fpath.name} must not be empty"

        # Check for presence of TEST_ONLY or synthetic marker if cryptographic material exists
        if "publicKey" in content or "signatures" in content:
            assert "TEST_ONLY" in content or "synthetic" in content, (
                f"Fixture {fpath.name} contains cryptographic material without synthetic marker"
            )

        # Assert no real private key PEM blocks
        assert "-----BEGIN EC PRIVATE KEY-----" not in content
        assert "-----BEGIN RSA PRIVATE KEY-----" not in content
        assert "-----BEGIN PRIVATE KEY-----" not in content
        assert "-----BEGIN OPENSSH PRIVATE KEY-----" not in content

        # Check JSON parsed keyids
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "signatures" in parsed:
                for s in parsed["signatures"]:
                    assert "synthetic" in s["keyid"] or "TEST_ONLY" in s["keyid"]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass


def test_attest_tool_verify_parameter_enforces_signed_policy(tmp_path: Path) -> None:
    """Tests AttestationTool --verify support using ProvenancePolicyVerifier."""
    from rush.tools.attest import AttestationTool

    tool = AttestationTool()
    _, pub_key = _load_valid_fixture()

    # 1. Verification succeeds when valid envelope and authorized keys are passed
    res_ok = tool.run(
        tmp_path,
        verify=str(VALID_ENVELOPE_PATH),
        trusted_roots=(pub_key,),
        allowed_signers=("synthetic-test-key-1",),
    )
    assert res_ok["status"] == "ok"
    assert "Verified signed provenance" in res_ok["summary"]
    assert res_ok["metadata"]["is_valid"] is True
    assert res_ok["metadata"]["signer_id"] == "synthetic-test-key-1"

    # 2. Verification fails-closed when empty allowlists are passed
    res_fail = tool.run(
        tmp_path,
        verify=str(VALID_ENVELOPE_PATH),
        trusted_roots=(),
        allowed_signers=(),
    )
    assert res_fail["status"] == "error"
    assert "trusted_roots is empty: fail-closed" in res_fail["summary"]
