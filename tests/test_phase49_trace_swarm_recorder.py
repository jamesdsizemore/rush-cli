"""Unit tests for Phase 49 TraceScanner, SwarmMergeSolver, MeshLockManager, and FlightRecorder."""

from pathlib import Path

from rush.tools.continuity import SessionContinuityTool
from src.rush.mcp_mesh.lock_manager import MeshLockManager
from src.rush.tools.flight_recorder import FlightRecorder
from src.rush.tools.swarm_merge import SwarmMergeSolver
from src.rush.tools.trace import TraceScanner


def test_trace_scanner(tmp_path: Path):
    doc_dir = tmp_path / "docs"
    src_dir = tmp_path / "src"
    test_dir = tmp_path / "tests"
    doc_dir.mkdir(parents=True, exist_ok=True)
    src_dir.mkdir(parents=True, exist_ok=True)
    test_dir.mkdir(parents=True, exist_ok=True)

    (doc_dir / "spec.md").write_text(
        "Requirements: [REQ-001] and FR-01-01.", encoding="utf-8"
    )
    (src_dir / "app.py").write_text(
        "# Implements [REQ-001]\ndef run(): pass\n", encoding="utf-8"
    )
    (test_dir / "test_app.py").write_text(
        "# Verifies [REQ-001]\ndef test_run(): pass\n", encoding="utf-8"
    )

    scanner = TraceScanner(project_root=tmp_path)
    res = scanner.scan_traceability()

    assert res["total_requirements"] == 2
    req1 = next(r for r in res["matrix"] if r["requirement"] == "REQ-001")
    assert req1["status"] == "VERIFIED"
    assert len(req1["implementations"]) == 1
    assert len(req1["tests"]) == 1


def test_swarm_3way_ast_merge():
    base = """
def common_fn():
    return 1
"""
    ours = """
def common_fn():
    return 1

def feature_ours():
    return 'ours'
"""
    theirs = """
def common_fn():
    return 1

def feature_theirs():
    return 'theirs'
"""
    solver = SwarmMergeSolver()
    res = solver.merge_3way(base, ours, theirs)

    assert res["success"] is True
    assert "feature_ours" in res["merged_code"]
    assert "feature_theirs" in res["merged_code"]


def test_mesh_lock_manager(tmp_path: Path):
    mgr = MeshLockManager(project_root=tmp_path)
    target = tmp_path / "critical_file.py"

    # Acquire lock
    assert mgr.acquire(target, agent_id="agent-1", timeout_s=1.0) is True

    # Second acquire with different agent should fail
    assert mgr.acquire(target, agent_id="agent-2", timeout_s=0.2) is False

    # Release lock
    assert mgr.release(target, agent_id="agent-1") is True

    # Now second agent can acquire
    assert mgr.acquire(target, agent_id="agent-2", timeout_s=1.0) is True
    assert mgr.release(target, agent_id="agent-2") is True


def test_flight_recorder(tmp_path: Path):
    recorder = FlightRecorder(project_root=tmp_path)
    recorder.record_event("session-abc", "TOOL_CALL", {"tool": "rush_context_pack"})
    recorder.record_event("session-abc", "TOOL_RESULT", {"status": "success"})

    events = recorder.replay_session("session-abc")
    assert len(events) == 2
    assert events[0]["event_type"] == "TOOL_CALL"
    assert events[1]["event_type"] == "TOOL_RESULT"


def test_continuity_coordination_reports_held_lock_without_overwrite(tmp_path: Path):
    target = tmp_path / "owned.py"
    target.write_text("value = 1\n")
    locks = MeshLockManager(project_root=tmp_path)
    assert locks.acquire(target, agent_id="agent-a", timeout_s=0.1)

    result = SessionContinuityTool().run(
        tmp_path,
        operation="coordination_check",
        coordination_path="owned.py",
        agent_id="agent-b",
    )

    assert result["status"] == "skipped"
    assert result["metadata"]["coordination"]["state"] == "conflict"
    assert result["metadata"]["coordination"]["owner"] == "agent-a"
    assert target.read_text() == "value = 1\n"


def test_continuity_coordination_reports_same_owner_as_held_evidence(tmp_path: Path):
    target = tmp_path / "owned.py"
    target.write_text("value = 1\n")
    locks = MeshLockManager(project_root=tmp_path)
    assert locks.acquire(target, agent_id="agent-a", timeout_s=0.1)

    result = SessionContinuityTool().run(
        tmp_path,
        operation="coordination_check",
        coordination_path="owned.py",
        agent_id="agent-a",
    )

    assert result["status"] == "ok"
    assert result["summary"] == "Local ownership is held by this agent."
    assert result["metadata"]["coordination"] == {"state": "held", "owner": "agent-a"}


def test_failure_ledger_receipt_never_returns_failed_patch(tmp_path: Path):
    from rush.memory.failure_ledger import FailureLedger

    ledger = FailureLedger(tmp_path)
    fingerprint = ledger.record_failure(
        "api_key=sk-ant-abcdefghijklmnopqrstuvwxyz012345", "patch failed"
    )
    receipt = ledger.get_receipt(fingerprint)

    assert receipt is not None
    assert "failed_patch" not in receipt
    assert "sk-ant-abcdefghijklmnopqrstuvwxyz012345" not in str(receipt)


def test_continuity_coordination_keeps_stale_lock_as_evidence(tmp_path: Path):
    import json
    import time

    target = tmp_path / "stale.py"
    target.write_text("value = 1\n")
    locks = MeshLockManager(project_root=tmp_path)
    locks._lock_file_for(target).write_text(
        json.dumps({"agent_id": "agent-a", "acquired_at": time.time() - 600}),
        encoding="utf-8",
    )

    result = SessionContinuityTool().run(
        tmp_path,
        operation="coordination_check",
        coordination_path="stale.py",
        coordination_max_age_s=60,
    )

    assert result["status"] == "skipped"
    assert result["metadata"]["coordination"] == {
        "state": "stale",
        "owner": "agent-a",
        "action": "manual_recovery_required",
    }
    assert target.read_text() == "value = 1\n"


def test_continuity_coordination_reports_merge_conflict_without_merging(tmp_path: Path):
    result = SessionContinuityTool().run(
        tmp_path,
        operation="coordination_merge_preview",
        base_code="def shared():\n    return 1\n",
        ours_code="def shared():\n    return 2\n",
        theirs_code="def shared():\n    return 3\n",
    )

    assert result["status"] == "skipped"
    assert result["raw"] is None
    assert result["metadata"]["coordination"] == {
        "state": "merge_conflict",
        "action": "manual_reconciliation_required",
        "conflicts": ["shared"],
    }


def test_continuity_recovery_exposes_only_replay_and_failure_receipts(
    tmp_path: Path,
):
    from rush.memory.failure_ledger import FailureLedger

    FlightRecorder(tmp_path).record_event(
        "session-a", "TOOL_RESULT", {"status": "fail"}
    )
    fingerprint = FailureLedger(tmp_path).record_failure(
        "token=sk-ant-abcdefghijklmnopqrstuvwxyz012345", "patch failed"
    )

    result = SessionContinuityTool().run(
        tmp_path,
        operation="coordination_recovery",
        flight_session_id="session-a",
        failure_fingerprint=fingerprint,
    )

    assert result["status"] == "ok"
    recovery = result["metadata"]["coordination"]["recovery"]
    assert recovery["replay"] == {
        "state": "recorded",
        "session_id": "session-a",
        "event_count": 1,
        "last_event_type": "TOOL_RESULT",
    }
    assert recovery["failure"]["fingerprint"] == fingerprint
    assert "failed_patch" not in str(result)
    assert "sk-ant-abcdefghijklmnopqrstuvwxyz012345" not in str(result)


def test_continuity_recovery_surfaces_redacted_mined_mistake_evidence(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(
        "rush.memory.mistake_miner.MistakeMiner.mine_mistakes",
        lambda _self: [
            {
                "reverted_subject": "unsafe resume adapter",
                "rationale": "token=sk-ant-abcdefghijklmnopqrstuvwxyz012345",
                "guard_status": "active",
            }
        ],
    )

    result = SessionContinuityTool().run(tmp_path, operation="coordination_recovery")

    assert result["status"] == "ok"
    mistakes = result["metadata"]["coordination"]["recovery"]["mistakes"]
    assert mistakes[0]["authority"] == "historical_evidence"
    assert mistakes[0]["guard_status"] == "active"
    assert mistakes[0]["reverted_subject"] == "unsafe resume adapter"
    assert mistakes[0]["rationale"].startswith("token=[REDACTED")
    assert "sk-ant-abcdefghijklmnopqrstuvwxyz012345" not in str(result)


def test_continuity_recovery_skips_missing_or_corrupt_replay_evidence(
    tmp_path: Path,
):
    missing = SessionContinuityTool().run(
        tmp_path,
        operation="coordination_recovery",
        flight_session_id="missing",
    )
    assert missing["status"] == "skipped"
    assert (
        missing["metadata"]["coordination"]["recovery"]["replay"]["state"]
        == "not_found"
    )

    flights = tmp_path / ".rush" / "sessions" / "flights"
    flights.mkdir(parents=True)
    (flights / "corrupt.jsonl").write_text("not JSON\n", encoding="utf-8")
    corrupt = SessionContinuityTool().run(
        tmp_path,
        operation="coordination_recovery",
        flight_session_id="corrupt",
    )
    assert corrupt["status"] == "skipped"
    assert (
        corrupt["metadata"]["coordination"]["recovery"]["replay"]["state"]
        == "unavailable"
    )


def test_continuity_recovery_handles_corrupt_failure_ledger_as_evidence(
    tmp_path: Path,
):
    database = tmp_path / ".rush" / "memory" / "failures.db"
    database.parent.mkdir(parents=True)
    database.write_bytes(b"not a sqlite database")

    result = SessionContinuityTool().run(
        tmp_path,
        operation="coordination_recovery",
        failure_fingerprint="a" * 64,
    )

    assert result["status"] == "skipped"
    assert result["metadata"]["coordination"]["recovery"]["failure"] == {
        "fingerprint": "a" * 64,
        "state": "unavailable",
    }
