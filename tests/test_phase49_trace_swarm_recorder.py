"""Unit tests for Phase 49 TraceScanner, SwarmMergeSolver, MeshLockManager, and FlightRecorder."""

from pathlib import Path

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
