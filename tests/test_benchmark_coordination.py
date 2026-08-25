"""Tests for coordination, multi-agent lock mutual exclusion, checkpoint journal, and flight recording."""

from __future__ import annotations

from pathlib import Path

from scripts.benchmarks.contracts import (
    Outcome,
    Scenario,
)
from scripts.benchmarks.coordination import run_coordination_probe
from scripts.benchmarks.fixtures import load_coordination_cases


def test_second_agent_cannot_acquire_held_lock(tmp_path: Path):
    # Scenario: Agent 1 holds lock on file; Agent 2 tries to acquire -> must fail to acquire
    sc = Scenario(
        scenario_id="concurrency-lock-contention",
        probe="coordination",
        category="concurrency",
        input={
            "action": "lock_contention",
            "file": "src/rush/tools/base.py",
            "agent_1": "agent-primary",
            "agent_2": "agent-secondary",
        },
        required_facts=(),
        expected_outcome=Outcome.PASS,
    )
    res = run_coordination_probe(sc, project_root=tmp_path)
    assert res.outcome == Outcome.PASS
    assert res.metrics.get("agent_1_acquired") is True
    assert res.metrics.get("agent_2_blocked") is True


def test_checkpoint_and_flight_replay_match(tmp_path: Path):
    # Scenario: Save checkpoint, record flight events, then verify replay fidelity
    sc = Scenario(
        scenario_id="coordination-checkpoint-replay",
        probe="coordination",
        category="recovery",
        input={
            "action": "checkpoint_and_flight",
            "session_id": "sess-test-01",
            "checkpoint_name": "ckpt-01",
            "metadata": {"task": "auth_refactor", "tests_passing": 5},
            "files": ["src/rush/config.py", "tests/test_config.py"],
            "events": [
                {"type": "tool_call", "payload": {"tool": "rush_lint"}},
                {"type": "tool_result", "payload": {"status": "pass"}},
            ],
        },
        required_facts=(),
        expected_outcome=Outcome.PASS,
    )
    res = run_coordination_probe(sc, project_root=tmp_path)
    assert res.outcome == Outcome.PASS
    assert res.metrics.get("checkpoint_restored") is True
    assert res.metrics.get("replay_events_count") == 2


def test_coordination_cases_fixture():
    cases = load_coordination_cases()
    assert len(cases) >= 3
    for c in cases:
        assert "action" in c
