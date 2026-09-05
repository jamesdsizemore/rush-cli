"""Governance test for Phase 58: R-009 Caller Capability Lock Verification."""

from __future__ import annotations

from pathlib import Path

from rush.mcp_mesh.capabilities import LockCapabilityInput, create_capability
from rush.mcp_mesh.lock_manager import MeshLockManager


def test_lock_acquisition_requires_caller_capability(tmp_path: Path) -> None:
    """T-58.07 (R-009 Governance Test): Asserts lock acquisition requires and validates caller capability with generation tracking."""
    mgr = MeshLockManager(project_root=tmp_path)
    target = tmp_path / "critical_section.py"
    target.write_text("counter = 0\n", encoding="utf-8")

    # 1. Invalid / low-entropy capability is rejected fail-closed
    bad_cap = LockCapabilityInput(
        token="tooshort", agent_id="agent-bad", channel_type="stdin"
    )
    assert (
        mgr.acquire(target, agent_id="agent-bad", capability=bad_cap, timeout_s=0.1)
        is False
    )
    assert mgr.inspect(tmp_path, target)["state"] == "available"

    # 2. Valid high-entropy caller capability successfully acquires generation 1
    cap1, _token1 = create_capability(agent_id="agent-1", channel_type="stdin")
    assert (
        mgr.acquire(target, agent_id="agent-1", capability=cap1, timeout_s=1.0) is True
    )

    state1 = mgr.inspect(tmp_path, target)
    assert state1["state"] == "held"
    assert state1["owner"] == "agent-1"
    assert state1["generation"] == 1

    # 3. Renewing requires matching capability and advances generation
    assert mgr.renew(target, capability=cap1) is True
    state2 = mgr.inspect(tmp_path, target)
    assert state2["generation"] == 2

    # 4. Unauthorized agent without matching capability cannot renew or release
    cap_unauth, _ = create_capability(agent_id="agent-2")
    assert mgr.renew(target, capability=cap_unauth) is False
    assert mgr.release(target, capability=cap_unauth) is False
    assert mgr.inspect(tmp_path, target)["generation"] == 2

    # 5. Clean release with verified capability
    assert mgr.release(target, capability=cap1) is True
    assert mgr.inspect(tmp_path, target)["state"] == "available"
