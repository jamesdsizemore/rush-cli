from __future__ import annotations

import hmac
import json
from unittest.mock import patch

import pytest

from rush.io.verifier_record import VerifierError, VerifierRecord, _calculate_entropy


def test_record_contains_no_raw_capability() -> None:
    """T-55.09: Asserts raw capability string/bytes does not appear anywhere in VerifierRecord fields, repr(), str(), or to_dict()."""
    # Test with string capability
    raw_secret_str = "SuperSecret_Cap_Token_2026_Secure!"
    record_from_str = VerifierRecord.create(raw_secret_str)

    # Asserts raw capability does not appear in str or repr
    assert raw_secret_str not in str(record_from_str)
    assert raw_secret_str not in repr(record_from_str)

    # Asserts raw capability does not appear in serialized dictionary
    dict_repr = record_from_str.to_dict()
    assert raw_secret_str not in json.dumps(dict_repr)

    # Asserts raw capability does not appear in any field value
    for field_name, val in dict_repr.items():
        assert raw_secret_str not in str(val), f"Secret leaked in field {field_name}"

    # Test with bytes capability
    raw_secret_bytes = b"BinarySecret_Cap_Token_Bytes_998877!"
    record_from_bytes = VerifierRecord.create(raw_secret_bytes)

    assert "BinarySecret" not in str(record_from_bytes)
    assert "BinarySecret" not in repr(record_from_bytes)
    bytes_dict = record_from_bytes.to_dict()
    assert "BinarySecret" not in json.dumps(bytes_dict)
    for field_name, val in bytes_dict.items():
        assert "BinarySecret" not in str(val), f"Secret leaked in field {field_name}"


def test_wrong_reused_low_entropy_and_stale_values_fail() -> None:
    """T-55.10: Asserts that wrong candidate returns False, valid returns True, and low entropy/short raises VerifierError."""
    valid_cap = "Valid_Secure_Capability_String_12345!"
    record = VerifierRecord.create(valid_cap)

    # Valid candidate returns True (both str and bytes)
    assert record.verify(valid_cap) is True
    assert record.verify(valid_cap.encode("utf-8")) is True

    # Wrong candidate returns False
    assert record.verify("Wrong_Candidate_Token_String_99999!") is False
    assert record.verify(b"Wrong_Candidate_Token_String_99999!") is False
    assert record.verify(valid_cap + "_extra") is False
    assert record.verify("") is False

    # Low-entropy or short capabilities raise VerifierError fail-closed
    # 1. Short strings (< 16 chars)
    with pytest.raises(VerifierError, match="at least 16"):
        VerifierRecord.create("short_token")

    with pytest.raises(VerifierError, match="at least 16"):
        VerifierRecord.create("")

    with pytest.raises(VerifierError, match="at least 16"):
        VerifierRecord.create(b"short_bytes_123")

    with pytest.raises(VerifierError, match="at least 16"):
        # Whitespace padded string with trimmed length < 16
        VerifierRecord.create("   short_token   ")

    # 2. Shannon entropy < 2.5 bits/symbol
    # Constant character string (entropy = 0.0)
    with pytest.raises(VerifierError, match="entropy too low"):
        VerifierRecord.create("aaaaaaaaaaaaaaaaaaaaaaaa")

    # Low entropy repeating 2 characters (entropy = 1.0 < 2.5)
    with pytest.raises(VerifierError, match="entropy too low"):
        VerifierRecord.create("abababababababababababab")

    # Low entropy repeating 4 characters (entropy = 2.0 < 2.5)
    with pytest.raises(VerifierError, match="entropy too low"):
        VerifierRecord.create("abcdabcdabcdabcd")

    # Helper function unit validation
    assert _calculate_entropy("") == 0.0
    assert _calculate_entropy("aaaa") == 0.0
    assert _calculate_entropy("abcdefghijklmnopqrstuvwxyz0123456789") > 5.0


def test_metadata_cannot_recover_capability() -> None:
    """T-55.11: Asserts to_dict contains only allowed fields and verifies constant-time comparison via hmac.compare_digest."""
    cap = "Cryptographic_Capability_Token_XYZ_987654"
    record = VerifierRecord.create(cap, work_factor=100_000, algorithm="pbkdf2_sha256")
    data = record.to_dict()

    # Allowed keys exactly
    allowed_keys = {
        "version",
        "salt",
        "algorithm",
        "work_factor",
        "verifier",
        "created_at",
    }
    assert set(data.keys()) == allowed_keys

    # Valid values and formats
    assert data["version"] == "1.0.0"
    assert data["algorithm"] == "pbkdf2_sha256"
    assert data["work_factor"] == 100_000
    assert len(data["salt"]) == 64  # 32 bytes hex
    assert len(data["verifier"]) == 64  # 32 bytes hex (SHA-256)
    int(data["salt"], 16)  # Must be valid hex
    int(data["verifier"], 16)  # Must be valid hex

    # Serialization roundtrip via from_dict
    restored = VerifierRecord.from_dict(data)
    assert restored == record
    assert restored.version == "1.0.0"
    assert restored.salt == data["salt"]
    assert restored.algorithm == "pbkdf2_sha256"
    assert restored.work_factor == 100_000
    assert restored.verifier == data["verifier"]
    assert restored.created_at == data["created_at"]
    assert restored.verify(cap) is True
    assert restored.verify("invalid_candidate_guess_123") is False

    # Constant-time comparison verification via hmac.compare_digest
    with patch("hmac.compare_digest", wraps=hmac.compare_digest) as mock_compare:
        res = restored.verify(cap)
        assert res is True
        mock_compare.assert_called_once()
        args, _ = mock_compare.call_args
        assert args[0] == restored.verifier
        assert len(args[1]) == 64
