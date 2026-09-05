from __future__ import annotations

import json
from pathlib import Path

import pytest

from rush.contracts.results import (
    FindingV1,
    ToolResultV1,
    ValidationErrorV1,
    adapt_legacy_finding,
    adapt_legacy_tool_result,
    serialize_tool_result,
    validate_finding,
    validate_tool_result,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "remediation"


def _load_json(filename: str) -> dict:
    with open(FIXTURES_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)


def test_tool_result_v1_requires_exact_fields_and_vocabularies() -> None:
    """T-54.01: Enforces 8 core fields, strict schema version, and status vocabulary."""
    valid_data = _load_json("tool_result_v1_valid.json")
    result = validate_tool_result(valid_data)

    assert isinstance(result, ToolResultV1)
    assert result.schema_version == "1.0.0"
    assert result.tool == "lint"
    assert result.engine == "ruff"
    assert result.engine_version == "0.9.9"
    assert result.status == "ok"
    assert result.duration_ms == 42
    assert result.summary == "all clean"
    assert len(result.findings) == 1
    assert isinstance(result.findings[0], FindingV1)
    assert result.findings[0].severity == "warning"

    invalid_cases = _load_json("tool_result_v1_invalid.json")

    # Missing schema_version
    with pytest.raises(ValidationErrorV1) as exc_info:
        validate_tool_result(invalid_cases["missing_schema_version"])
    assert exc_info.value.code == "MISSING_REQUIRED_FIELD"
    assert "schema_version" in exc_info.value.path

    # Invalid schema_version
    with pytest.raises(ValidationErrorV1) as exc_info:
        validate_tool_result(invalid_cases["invalid_schema_version"])
    assert exc_info.value.code == "INVALID_SCHEMA_VERSION"

    # Invalid status
    with pytest.raises(ValidationErrorV1) as exc_info:
        validate_tool_result(invalid_cases["invalid_status"])
    assert exc_info.value.code == "INVALID_STATUS"

    # Negative duration
    with pytest.raises(ValidationErrorV1) as exc_info:
        validate_tool_result(invalid_cases["negative_duration"])
    assert exc_info.value.code == "INVALID_TYPE"


def test_finding_v1_rejects_unknown_severity() -> None:
    """T-54.02: FindingV1 requires canonical severity ('info', 'warning', 'error')."""
    base_finding = {
        "path": "src/rush/main.py",
        "line": 12,
        "column": 4,
        "rule_id": "SEC-001",
        "message": "Potential issue",
        "fingerprint": "11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff",
    }

    for sev in ("info", "warning", "error"):
        f = validate_finding({**base_finding, "severity": sev})
        assert isinstance(f, FindingV1)
        assert f.severity == sev

    # Unknown or legacy non-canonical severities must be rejected by validate_finding
    for invalid_sev in ("warn", "fail", "fatal", "critical", "notice", ""):
        with pytest.raises(ValidationErrorV1) as exc_info:
            validate_finding({**base_finding, "severity": invalid_sev})
        assert exc_info.value.code == "INVALID_SEVERITY"
        assert exc_info.value.path == "findings.severity"

    invalid_cases = _load_json("tool_result_v1_invalid.json")
    with pytest.raises(ValidationErrorV1) as exc_info:
        validate_finding(invalid_cases["missing_rule_id"])
    assert (
        exc_info.value.code == "INVALID_TYPE"
        or exc_info.value.code == "MISSING_REQUIRED_FIELD"
    )


def test_extensions_are_namespaced_json_safe() -> None:
    """T-54.03: Rejects unknown top-level keys; allows namespaced JSON-safe extensions."""
    invalid_cases = _load_json("tool_result_v1_invalid.json")

    # Rejection of unknown top-level key on ToolResult
    with pytest.raises(ValidationErrorV1) as exc_info:
        validate_tool_result(invalid_cases["unknown_top_level_key"])
    assert exc_info.value.code == "UNKNOWN_TOP_LEVEL_KEY"
    assert exc_info.value.path == "unexpected_key"

    # Rejection of unknown top-level key on Finding
    with pytest.raises(ValidationErrorV1) as exc_info:
        validate_finding(invalid_cases["unknown_finding_key"])
    assert exc_info.value.code == "UNKNOWN_TOP_LEVEL_KEY"
    assert exc_info.value.path == "findings.extra_finding_key"

    # Valid namespaced extensions
    valid_data = _load_json("tool_result_v1_valid.json")
    valid_data["extensions"] = {
        "metrics": {"loc": 100, "cyclomatic_complexity": 5},
        "review": {"review_kind": "security", "provider": "deepcode"},
    }
    result = validate_tool_result(valid_data)
    assert result.extensions["metrics"]["loc"] == 100

    # Non JSON-safe extension rejected
    valid_data["extensions"]["bad"] = object()
    with pytest.raises(ValidationErrorV1) as exc_info:
        validate_tool_result(valid_data)
    assert exc_info.value.code == "NON_JSON_SAFE_VALUE"


def test_serializer_is_deterministic() -> None:
    """T-54.04: Byte-deterministic serialization across insertion orders and secret redaction."""
    finding_dict_a = {
        "path": "src/rush/cli.py",
        "line": 1,
        "column": 0,
        "rule_id": "R001",
        "severity": "info",
        "message": "Found secret sk-ant-api03-1234567890abcdef",
        "fingerprint": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
    }
    finding_dict_b = {
        "fingerprint": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        "message": "Found secret sk-ant-api03-1234567890abcdef",
        "severity": "info",
        "rule_id": "R001",
        "column": 0,
        "line": 1,
        "path": "src/rush/cli.py",
    }

    res_a = {
        "schema_version": "1.0.0",
        "tool": "secret_scanner",
        "engine": "custom",
        "engine_version": "1.0",
        "status": "ok",
        "duration_ms": 15,
        "summary": "completed check",
        "findings": [finding_dict_a],
        "extensions": {"z_key": "last", "a_key": "first"},
    }
    res_b = {
        "extensions": {"a_key": "first", "z_key": "last"},
        "summary": "completed check",
        "duration_ms": 15,
        "status": "ok",
        "engine_version": "1.0",
        "engine": "custom",
        "findings": [finding_dict_b],
        "tool": "secret_scanner",
        "schema_version": "1.0.0",
    }

    serialized_a = serialize_tool_result(res_a)
    serialized_b = serialize_tool_result(res_b)

    # Must be byte-identical
    assert serialized_a == serialized_b

    # Must be valid JSON matching sorted key ordering
    parsed = json.loads(serialized_a)
    assert parsed["schema_version"] == "1.0.0"

    # Sensitive data must be redacted via Phase 53 integration
    assert "sk-ant-api03-1234567890abcdef" not in serialized_a
    assert "REDACTED" in serialized_a


def test_legacy_warn_maps_only_to_warning() -> None:
    """T-54.05: Legacy finding severity 'warn' maps strictly to 'warning'."""
    legacy_finding = {
        "path": "src/rush/tools/common.py",
        "line": 45,
        "column": 2,
        "rule_id": "W001",
        "severity": "warn",
        "message": "Use of deprecated function",
        "fingerprint": "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
    }
    adapted = adapt_legacy_finding(legacy_finding)
    assert isinstance(adapted, FindingV1)
    assert adapted.severity == "warning"
    assert adapted.rule_id == "W001"
    assert adapted.path == "src/rush/tools/common.py"


def test_legacy_fail_maps_only_to_error() -> None:
    """T-54.06: Legacy finding severity 'fail' maps strictly to 'error'."""
    legacy_finding = {
        "path": "src/rush/tools/tdd_guard.py",
        "line": 84,
        "column": 0,
        "rule_id": "TDD-001",
        "severity": "fail",
        "message": "Test failure occurred",
        "fingerprint": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
    }
    adapted = adapt_legacy_finding(legacy_finding)
    assert isinstance(adapted, FindingV1)
    assert adapted.severity == "error"

    # Identity mappings must also preserve canonical severities
    for sev in ("info", "warning", "error"):
        res = adapt_legacy_finding({**legacy_finding, "severity": sev})
        assert res.severity == sev


def test_unknown_legacy_value_returns_canonical_validation_error() -> None:
    """T-54.07: Unmappable legacy severities or invalid structures raise ValidationErrorV1."""
    base_finding = {
        "path": "src/rush/main.py",
        "line": 1,
        "column": 1,
        "rule_id": "R001",
        "message": "Unknown severity test",
        "fingerprint": "0000000000000000000000000000000000000000000000000000000000000000",
    }

    # Zero silent default coercion: unknown severity must raise structured ValidationErrorV1
    for unmappable in ("critical", "fatal", "notice", "high", "low", 123):
        with pytest.raises(ValidationErrorV1) as exc_info:
            adapt_legacy_finding({**base_finding, "severity": unmappable})
        assert exc_info.value.code == "INVALID_SEVERITY"
        assert exc_info.value.path == "severity"

    # Test full legacy ToolResult adaptation
    legacy_tool_result = {
        "tool": "legacy_lint",
        "engine": "flake8",
        "engine_version": "3.9.0",
        "status": "warn",
        "duration_ms": 120,
        "summary": "found 1 warning",
        "findings": [
            {
                "path": "src/rush/legacy.py",
                "line": 10,
                "column": 5,
                "rule_id": "W291",
                "severity": "warn",
                "message": "trailing whitespace",
            }
        ],
        "metrics": {"total_files": 12},
        "artifacts": ["artifact.txt"],
    }
    adapted_result = adapt_legacy_tool_result(legacy_tool_result)
    assert isinstance(adapted_result, ToolResultV1)
    assert adapted_result.schema_version == "1.0.0"
    assert adapted_result.status == "warn"
    assert len(adapted_result.findings) == 1
    assert adapted_result.findings[0].severity == "warning"
    # Fingerprint should be deterministically synthesized if absent
    assert len(adapted_result.findings[0].fingerprint) == 64
    # Non-core fields should be routed to extensions
    assert adapted_result.extensions["metrics"] == {"total_files": 12}
    assert adapted_result.extensions["artifacts"] == ["artifact.txt"]
