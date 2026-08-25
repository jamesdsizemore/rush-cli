"""Tests for privacy redaction, synthetic secret detection, parser bounding, and binary dependency safety."""

from __future__ import annotations

import json

from scripts.benchmarks.contracts import (
    CandidateBinary,
    Outcome,
    Scenario,
)
from scripts.benchmarks.fixtures import load_privacy_cases
from scripts.benchmarks.privacy import (
    run_privacy_probe,
    scan_and_redact_secrets,
    validate_candidate_binary,
)


def test_secret_never_reaches_json_or_exception():
    secret_text = "API_KEY=ghp_ABC1234567890XYZabcdefghijk and AWS=AKIAIOSFODNN7EXAMPLE"
    cleaned, redactions = scan_and_redact_secrets(secret_text)

    # Raw secrets must be absent from cleaned text
    assert "ghp_ABC1234567890XYZabcdefghijk" not in cleaned
    assert "AKIAIOSFODNN7EXAMPLE" not in cleaned
    assert "[REDACTED:GITHUB_TOKEN]" in cleaned
    assert "[REDACTED:AWS_KEY]" in cleaned
    assert len(redactions) == 2

    # ProbeResult serialization verification
    scenario = Scenario(
        scenario_id="privacy-secret-probe",
        probe="privacy",
        category="privacy",
        input={"text": secret_text},
        required_facts=(),
        expected_outcome=Outcome.PASS,
    )
    res = run_privacy_probe(scenario)
    res_dict = res.to_dict()
    res_json = json.dumps(res_dict)

    assert "ghp_ABC1234567890XYZabcdefghijk" not in res_json
    assert "AKIAIOSFODNN7EXAMPLE" not in res_json
    assert len(res.redactions) == 2


def test_candidate_binary_validation():
    # Valid candidate with version, license, and bounds
    valid = CandidateBinary(
        name="gitleaks",
        version="8.18.0",
        license="MIT",
        bounds={"max_kb": 10000, "timeout_s": 10},
    )
    status = validate_candidate_binary(valid)
    assert status == Outcome.PASS

    # Incomplete candidate missing license or bounds
    invalid = CandidateBinary(name="unknown-secret-tool", version="", license="")
    status_inv = validate_candidate_binary(invalid)
    assert status_inv == Outcome.DEFERRED


def test_bounded_parser_limits():
    # Input exceeding max_bytes
    oversize_scenario = Scenario(
        scenario_id="privacy-oversize",
        probe="privacy",
        category="privacy",
        input={"byte_size": 25_000_000, "max_bytes": 10_000_000},
        required_facts=(),
        expected_outcome=Outcome.PASS,
    )
    res = run_privacy_probe(oversize_scenario)
    assert res.outcome == Outcome.PASS
    assert res.metrics.get("size_bounded") is True
    assert res.fallback == "input-exceeded-byte-limit"


def test_privacy_cases_fixture():
    cases = load_privacy_cases()
    assert len(cases) >= 6
    for c in cases:
        assert "type" in c
        assert "input" in c
