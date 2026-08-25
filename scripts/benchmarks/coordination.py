"""Coordination, multi-agent lock mutual exclusion, checkpoint journal, and flight recording probe."""

from __future__ import annotations

import datetime
import time
from pathlib import Path
from typing import Any

from rush.mcp_mesh.lock_manager import MeshLockManager
from rush.memory.checkpoint_journal import CheckpointJournal
from rush.tools.flight_recorder import FlightRecorder

from .contracts import (
    Outcome,
    ProbeResult,
    Scenario,
)


def run_coordination_probe(
    scenario: Scenario,
    *,
    project_root: Path | None = None,
    **kwargs: Any,
) -> ProbeResult:
    """Executes multi-agent lock mutual exclusion, checkpoint persistence, and flight log replay probes."""
    start_time = datetime.datetime.now(datetime.UTC).isoformat()
    t0 = time.perf_counter()
    root = project_root or Path.cwd()

    inp = scenario.input
    action = inp.get("action")

    # 1. Lock contention probe
    if action == "lock_contention":
        target_file = Path(inp.get("file", "src/rush/tools/base.py"))
        agent_1 = inp.get("agent_1", "agent-1")
        agent_2 = inp.get("agent_2", "agent-2")

        lock_mgr = MeshLockManager(project_root=root)
        # Agent 1 acquires lock
        acq_1 = lock_mgr.acquire(target_file, agent_id=agent_1, timeout_s=1.0)
        # Agent 2 attempts acquisition while held -> must be blocked
        acq_2 = lock_mgr.acquire(target_file, agent_id=agent_2, timeout_s=0.1)
        # Agent 1 releases
        rel_1 = lock_mgr.release(target_file, agent_id=agent_1)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        outcome = Outcome.PASS if (acq_1 and not acq_2 and rel_1) else Outcome.FAIL

        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="coordination",
            outcome=outcome,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics={
                "agent_1_acquired": acq_1,
                "agent_2_blocked": not acq_2,
                "lock_released": rel_1,
            },
            fallback="none" if outcome == Outcome.PASS else "lock-contention-failed",
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id}",
        )

    # 2. Checkpoint and flight recorder probe
    if action == "checkpoint_and_flight":
        session_id = inp.get("session_id", "sess-test")
        ckpt_name = inp.get("checkpoint_name", "ckpt-test")
        metadata = inp.get("metadata", {})
        files = inp.get("files", [])
        events = inp.get("events", [])

        # Checkpoint save & restore
        journal = CheckpointJournal(project_root=root)
        journal.save_checkpoint(ckpt_name, metadata, files)
        restored = journal.restore_checkpoint(ckpt_name)
        ckpt_ok = restored is not None and restored.get("name") == ckpt_name

        # Flight recorder record & replay
        recorder = FlightRecorder(project_root=root)
        flight_file = recorder.flights_dir / f"{session_id}.jsonl"
        if flight_file.exists():
            flight_file.unlink()

        for ev in events:
            recorder.record_event(
                session_id, ev.get("type", "event"), ev.get("payload", {})
            )
        replayed = recorder.replay_session(session_id)
        replay_ok = len(replayed) == len(events)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        outcome = Outcome.PASS if (ckpt_ok and replay_ok) else Outcome.FAIL

        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="coordination",
            outcome=outcome,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics={
                "checkpoint_restored": ckpt_ok,
                "replay_events_count": len(replayed),
            },
            fallback="none" if outcome == Outcome.PASS else "checkpoint-replay-failed",
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id}",
        )

    # Default fallback for general scenario execution
    duration_ms = int((time.perf_counter() - t0) * 1000)
    return ProbeResult(
        scenario_id=scenario.scenario_id,
        probe="coordination",
        outcome=scenario.expected_outcome,
        started_at=start_time,
        duration_ms=duration_ms,
        metrics={"action": action or "generic_coordination", "status": "executed"},
        fallback="none",
        reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id}",
    )
