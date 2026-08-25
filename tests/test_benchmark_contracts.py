"""Tests for benchmark contracts, dataclasses, and fixture loading."""

from __future__ import annotations

import pytest

from scripts.benchmarks.contracts import (
    REQUIRED_RESULT_KEYS,
    SCHEMA_VERSION,
    FixtureError,
    Outcome,
    ProbeResult,
    SourceEvidence,
    require_exact_keys,
)
from scripts.benchmarks.fixtures import fixture_path, load_scenarios


def test_outcome_enum_values():
    assert Outcome.PASS.value == "pass"
    assert Outcome.FAIL.value == "fail"
    assert Outcome.INCONCLUSIVE.value == "inconclusive"
    assert Outcome.DEFERRED.value == "deferred"
    assert Outcome.SKIPPED.value == "skipped"
    with pytest.raises(ValueError):
        Outcome("monitor")


def test_require_exact_keys_validation():
    expected = frozenset({"a", "b", "c"})
    # exact keys pass
    require_exact_keys({"a": 1, "b": 2, "c": 3}, expected)

    # missing key
    with pytest.raises(FixtureError, match="missing="):
        require_exact_keys({"a": 1, "b": 2}, expected)

    # unknown key
    with pytest.raises(FixtureError, match="unknown="):
        require_exact_keys({"a": 1, "b": 2, "c": 3, "extra": 4}, expected)


def test_probe_result_serialization():
    evidence = SourceEvidence(url="https://example.com", retrieved_at="2026-08-24")
    res = ProbeResult(
        scenario_id="sc-01",
        probe="context",
        outcome=Outcome.PASS,
        started_at="2026-08-24T00:00:00Z",
        duration_ms=120,
        metrics={"tokens_saved": 450},
        evidence=(evidence,),
        redactions=("secret",),
        fallback="none",
        reproduction="python -m scripts.benchmarks.run --scenario sc-01",
    )
    data = res.to_dict()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["outcome"] == "pass"
    assert len(data["evidence"]) == 1
    assert data["evidence"][0]["url"] == "https://example.com"
    assert data["evidence"][0]["retrieved_at"] == "2026-08-24"
    assert set(data.keys()) == REQUIRED_RESULT_KEYS


def test_fixture_path_security():
    # Valid json inside fixture root
    path = fixture_path("scenarios.json")
    assert path.name == "scenarios.json"
    assert path.suffix == ".json"

    # Non-json denied
    with pytest.raises(FixtureError, match="fixture path denied"):
        fixture_path("scenarios.txt")

    # Path traversal denied
    with pytest.raises(FixtureError, match="fixture path denied"):
        fixture_path("../secret.json")


def test_load_scenarios_validation():
    scenarios = load_scenarios()
    assert len(scenarios) == 40

    categories = {}
    for sc in scenarios.values():
        categories[sc.category] = categories.get(sc.category, 0) + 1
        assert isinstance(sc.scenario_id, str)
        assert isinstance(sc.probe, str)
        assert isinstance(sc.input, dict)
        assert isinstance(sc.required_facts, tuple)
        assert isinstance(sc.expected_outcome, Outcome)

    # Verify counts: 8 handoff, 6 drift, 6 recovery, 8 privacy, 8 budget, 4 concurrency
    assert categories.get("handoff") == 8
    assert categories.get("drift") == 6
    assert categories.get("recovery") == 6
    assert categories.get("privacy") == 8
    assert categories.get("budget") == 8
    assert categories.get("concurrency") == 4
