"""Tests for context packing, token budgeting, required fact preservation, and CCR retrieval."""

from __future__ import annotations

from pathlib import Path

from scripts.benchmarks.context import run_context_probe
from scripts.benchmarks.contracts import (
    Outcome,
    Scenario,
)
from scripts.benchmarks.fixtures import load_context_cases


def test_required_fact_loss_cannot_pass(tmp_path: Path):
    # Create a dummy target file with python code
    sample_file = tmp_path / "sample_service.py"
    sample_file.write_text(
        "class AuthService:\n"
        '    """repository uses Python 3.12"""\n'
        "    def login(self, username, password):\n"
        "        return True\n"
        "\n"
        "class HelperA:\n"
        "    def compute_1(self):\n"
        "        x = [i * 2 for i in range(100)]\n"
        "        return sum(x)\n"
        "    def compute_2(self):\n"
        "        y = [i * 3 for i in range(100)]\n"
        "        return sum(y)\n"
        "\n"
        "class HelperB:\n"
        "    def process_data(self, data):\n"
        "        result = []\n"
        "        for d in data:\n"
        "            result.append(d * 10)\n"
        "        return result\n",
        encoding="utf-8",
    )

    # Scenario where budget is adequate and required fact is present
    sc_pass = Scenario(
        scenario_id="budget-ctx-pass",
        probe="context",
        category="budget",
        input={
            "file": str(sample_file),
            "target_symbol": "AuthService.login",
            "budget": 2000,
        },
        required_facts=("repository uses Python 3.12",),
        expected_outcome=Outcome.PASS,
    )
    res_pass = run_context_probe(sc_pass, project_root=tmp_path)
    assert res_pass.outcome == Outcome.PASS
    assert "tokens_raw" in res_pass.metrics
    assert "tokens_packed" in res_pass.metrics
    assert "token_savings_pct" in res_pass.metrics
    assert res_pass.metrics["token_savings_pct"] >= 0.0

    # Scenario where required fact is missing from file -> must be inconclusive with insufficient-budget
    sc_missing = Scenario(
        scenario_id="budget-ctx-missing-fact",
        probe="context",
        category="budget",
        input={"file": str(sample_file), "budget": 2000},
        required_facts=("missing fact that does not exist in code",),
        expected_outcome=Outcome.PASS,
    )
    res_missing = run_context_probe(sc_missing, project_root=tmp_path)
    assert res_missing.outcome == Outcome.INCONCLUSIVE
    assert res_missing.fallback == "insufficient-budget"


def test_ccr_round_trip_and_missing_chunk(tmp_path: Path):
    # Store chunk probe
    content = "def calculate_hash(): return 123456789"
    sc_store = Scenario(
        scenario_id="ccr-store-test",
        probe="context",
        category="budget",
        input={"ccr_action": "store", "content": content},
        required_facts=(),
        expected_outcome=Outcome.PASS,
    )
    res_store = run_context_probe(sc_store, project_root=tmp_path)
    assert res_store.outcome == Outcome.PASS
    chunk_hash = str(res_store.metrics.get("chunk_hash", ""))
    assert len(chunk_hash) == 64

    # Retrieve stored chunk -> must match exactly
    sc_retrieve = Scenario(
        scenario_id="ccr-retrieve-test",
        probe="context",
        category="budget",
        input={"ccr_action": "retrieve", "chunk_hash": chunk_hash},
        required_facts=(),
        expected_outcome=Outcome.PASS,
    )
    res_retrieve = run_context_probe(sc_retrieve, project_root=tmp_path)
    assert res_retrieve.outcome == Outcome.PASS
    assert res_retrieve.metrics.get("retrieved_match") is True

    # Retrieve missing chunk -> must return None / fail
    sc_missing = Scenario(
        scenario_id="ccr-missing-test",
        probe="context",
        category="budget",
        input={"ccr_action": "retrieve", "chunk_hash": "non_existent_hash_xyz"},
        required_facts=(),
        expected_outcome=Outcome.FAIL,
    )
    res_missing = run_context_probe(sc_missing, project_root=tmp_path)
    assert res_missing.outcome == Outcome.FAIL


def test_context_cases_fixture():
    cases = load_context_cases()
    assert len(cases) >= 4
    for c in cases:
        assert "case_id" in c
        assert "budget" in c
