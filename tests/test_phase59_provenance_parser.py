"""Phase 59 Workstream P59.3 Contract Tests: Strict Provenance Parser."""

from __future__ import annotations

import pytest

from rush.release import (
    AmbiguousKeyError,
    DuplicateKeyError,
    ProvenanceError,
    StrictProvenanceParser,
)


def test_duplicate_keys_at_raw_envelope_level_reject() -> None:
    """T-59.10: Asserts duplicate top-level keys in raw DSSE envelope are rejected with DuplicateKeyError."""
    # Duplicate payload key in JSON string
    raw_envelope_str = (
        '{"payloadType": "application/vnd.in-toto+json", '
        '"payload": "eyJhbGciOi...", '
        '"signatures": [], '
        '"payload": "eyJhbGciOiJ0YW1wZXJlZCJ9"}'
    )
    with pytest.raises(DuplicateKeyError) as exc_info:
        StrictProvenanceParser.parse(raw_envelope_str)

    assert exc_info.value.key == "payload"
    assert isinstance(exc_info.value, ProvenanceError)
    assert "Duplicate key" in str(exc_info.value)
    assert exc_info.value.path is not None

    # Duplicate payload key in UTF-8 bytes representation
    raw_envelope_bytes = raw_envelope_str.encode("utf-8")
    with pytest.raises(DuplicateKeyError) as exc_info_bytes:
        StrictProvenanceParser.parse(raw_envelope_bytes)

    assert exc_info_bytes.value.key == "payload"
    assert isinstance(exc_info_bytes.value, ProvenanceError)

    # Duplicate signatures key
    raw_envelope_signatures = (
        '{"payloadType": "application/vnd.in-toto+json", '
        '"payload": "eyJhbGciOi...", '
        '"signatures": [{"keyid": "k1", "sig": "s1"}], '
        '"signatures": [{"keyid": "k2", "sig": "s2"}]}'
    )
    with pytest.raises(DuplicateKeyError) as exc_info_sig:
        StrictProvenanceParser.parse(raw_envelope_signatures)

    assert exc_info_sig.value.key == "signatures"


def test_duplicate_keys_at_decoded_statement_and_predicate_level_reject() -> None:
    """T-59.11: Asserts duplicate keys at nested statement and predicate levels are rejected."""
    # Duplicate buildDefinition inside predicate
    stmt_dup_build_def = (
        "{\n"
        '  "_type": "https://in-toto.io/Statement/v1",\n'
        '  "subject": [{"name": "pkg", "digest": {"sha256": "abc"}}],\n'
        '  "predicateType": "https://slsa.dev/provenance/v1",\n'
        '  "predicate": {\n'
        '    "buildDefinition": {\n'
        '      "buildType": "https://rush-cli.org/build/draft/v1",\n'
        '      "externalParameters": {}\n'
        "    },\n"
        '    "buildDefinition": {\n'
        '      "buildType": "https://malicious.org/build/v1",\n'
        '      "externalParameters": {}\n'
        "    }\n"
        "  }\n"
        "}"
    )
    with pytest.raises(DuplicateKeyError) as exc_info_build:
        StrictProvenanceParser.parse(stmt_dup_build_def)

    assert exc_info_build.value.key == "buildDefinition"
    assert isinstance(exc_info_build.value, ProvenanceError)

    # Duplicate entryPoint inside externalParameters
    stmt_dup_entrypoint = (
        "{\n"
        '  "_type": "https://in-toto.io/Statement/v1",\n'
        '  "subject": [{"name": "pkg", "digest": {"sha256": "abc"}}],\n'
        '  "predicateType": "https://slsa.dev/provenance/v1",\n'
        '  "predicate": {\n'
        '    "buildDefinition": {\n'
        '      "buildType": "https://rush-cli.org/build/draft/v1",\n'
        '      "externalParameters": {\n'
        '        "sourceUri": "git+https://github.com/org/repo",\n'
        '        "commit": "0123456789abcdef0123456789abcdef01234567",\n'
        '        "entryPoint": "trusted.sh",\n'
        '        "entryPoint": "malicious.sh"\n'
        "      }\n"
        "    }\n"
        "  }\n"
        "}"
    )
    with pytest.raises(DuplicateKeyError) as exc_info_entry:
        StrictProvenanceParser.parse(stmt_dup_entrypoint)

    assert exc_info_entry.value.key == "entryPoint"

    # Duplicate builder inside runDetails
    stmt_dup_builder = (
        "{\n"
        '  "_type": "https://in-toto.io/Statement/v1",\n'
        '  "subject": [{"name": "pkg", "digest": {"sha256": "abc"}}],\n'
        '  "predicateType": "https://slsa.dev/provenance/v1",\n'
        '  "predicate": {\n'
        '    "runDetails": {\n'
        '      "builder": {"id": "https://rush-cli.org/builder/v1"},\n'
        '      "builder": {"id": "https://evil.org/builder/v1"}\n'
        "    }\n"
        "  }\n"
        "}"
    )
    with pytest.raises(DuplicateKeyError) as exc_info_builder:
        StrictProvenanceParser.parse(stmt_dup_builder)

    assert exc_info_builder.value.key == "builder"


def test_unicode_and_escaped_key_ambiguity_rejects_before_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T-59.12: Asserts Unicode NFKC collisions and ambiguous escaped keys reject before policy."""
    # \uff42 is fullwidth small latin letter 'b' which normalizes under NFKC to 'b'
    # Collision between ASCII "builder" and fullwidth "\uff42uilder"
    ambiguous_json = (
        "{\n"
        '  "builder": "https://rush-cli.org/builder/v1",\n'
        '  "\\uff42uilder": "https://spoofed.org/builder/v1"\n'
        "}"
    )

    # Ensure zero downstream policy calls can occur
    policy_called = False

    def fake_policy(*args: object, **kwargs: object) -> None:
        nonlocal policy_called
        policy_called = True

    monkeypatch.setattr(
        "rush.release.provenance_policy.validate_provenance_statement", fake_policy
    )

    with pytest.raises(AmbiguousKeyError) as exc_info:
        StrictProvenanceParser.parse(ambiguous_json)

    assert not policy_called, "Downstream policy was invoked despite ambiguous keys!"
    assert isinstance(exc_info.value, ProvenanceError)
    assert {exc_info.value.key1, exc_info.value.key2} == {"builder", "\uff42uilder"}
    assert "Ambiguous key" in str(exc_info.value)
    assert exc_info.value.path is not None

    # Nested collision inside predicate
    ambiguous_nested = (
        "{\n"
        '  "_type": "https://in-toto.io/Statement/v1",\n'
        '  "predicate": {\n'
        '    "buildDefinition": {},\n'
        '    "\\uff42uildDefinition": {}\n'
        "  }\n"
        "}"
    )
    with pytest.raises(AmbiguousKeyError) as exc_info_nested:
        StrictProvenanceParser.parse(ambiguous_nested)

    assert {exc_info_nested.value.key1, exc_info_nested.value.key2} == {
        "buildDefinition",
        "\uff42uildDefinition",
    }


def test_malformed_or_truncated_json_rejects_cleanly() -> None:
    """T-59.13: Asserts malformed or truncated JSON strings reject cleanly with ProvenanceError."""
    # Truncated array
    truncated_array = '{"_type": "https://in-toto.io/Statement/v1", "subject": ['
    with pytest.raises(ProvenanceError) as exc_info_arr:
        StrictProvenanceParser.parse(truncated_array)
    assert "Malformed or truncated JSON" in str(exc_info_arr.value)

    # Truncated object
    truncated_obj = '{"_type": "https://in-toto.io/Statement/v1", "predicate": {'
    with pytest.raises(ProvenanceError) as exc_info_obj:
        StrictProvenanceParser.parse(truncated_obj)
    assert "Malformed or truncated JSON" in str(exc_info_obj.value)

    # Unterminated string literal
    unterminated_str = (
        '{"_type": "https://in-toto.io/Statement/v1", "subject": "unterminated'
    )
    with pytest.raises(ProvenanceError) as exc_info_str:
        StrictProvenanceParser.parse(unterminated_str)
    assert "Malformed or truncated JSON" in str(exc_info_str.value)

    # Completely invalid syntax
    invalid_syntax = "{not valid json at all: true}"
    with pytest.raises(ProvenanceError) as exc_info_syntax:
        StrictProvenanceParser.parse(invalid_syntax)
    assert "Malformed or truncated JSON" in str(exc_info_syntax.value)

    # Empty string
    with pytest.raises(ProvenanceError) as exc_info_empty:
        StrictProvenanceParser.parse("")
    assert "Malformed or truncated JSON" in str(exc_info_empty.value)

    # Non-object root (e.g. integer or list instead of object)
    with pytest.raises(ProvenanceError) as exc_info_root:
        StrictProvenanceParser.parse("[1, 2, 3]")
    assert "Malformed or truncated JSON" in str(
        exc_info_root.value
    ) or "Expected JSON object" in str(exc_info_root.value)

    # Invalid UTF-8 bytes
    with pytest.raises(ProvenanceError) as exc_info_utf8:
        StrictProvenanceParser.parse(b"\xff\xfe\xfd")
    assert "Malformed or truncated JSON" in str(exc_info_utf8.value)
