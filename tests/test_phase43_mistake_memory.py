"""Unit tests for Phase 43 InvariantGraph, FailureLedger, and MistakeMiner."""

from pathlib import Path

from src.rush.memory.failure_ledger import FailureLedger
from src.rush.memory.invariant_graph import InvariantGraph
from src.rush.memory.mistake_miner import MistakeMiner


def test_invariant_graph(tmp_path: Path):
    graph = InvariantGraph(project_root=tmp_path)
    assert graph.get_all() == {}

    graph.add_invariant(
        "INV-001",
        "FastMCP stdio output must not have logs",
        "Prevents transport corruption",
    )
    all_invs = graph.get_all()
    assert "INV-001" in all_invs
    assert all_invs["INV-001"]["status"] == "active"


def test_failure_ledger(tmp_path: Path):
    ledger = FailureLedger(project_root=tmp_path)
    patch_code = "--- a/src/rush/cli.py\n+++ b/src/rush/cli.py\n- old\n+ broken"

    assert ledger.is_known_failure(patch_code) is False

    fp = ledger.record_failure(patch_code, "SyntaxError on line 42")
    assert len(fp) == 64
    assert ledger.is_known_failure(patch_code) is True


def test_mistake_miner_parse_revert():
    miner = MistakeMiner()

    subject = 'Revert "feat: enable aggressive async socket pooling"'
    body = "Caused race condition under 50+ concurrent requests."

    parsed = miner.parse_revert_message(subject, body)
    assert parsed is not None
    assert parsed["reverted_subject"] == "feat: enable aggressive async socket pooling"
    assert "race condition" in parsed["rationale"]

    # Non-revert commit
    assert miner.parse_revert_message("feat: normal commit", "") is None
