"""Phase 62 P62.3 contract tests: the maintenance sub-agent (`run_maintenance_cycle`).

Covers T-62.05, T-62.06, T-62.21, T-62.22 (phase-62-memory-integration-layer-plan.md §7).
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

import rush.tools.memory as memory_module
from rush.mcp_mesh.lock_manager import MeshLockManager
from rush.memory.maintenance import MaintenanceRunResult, run_maintenance_cycle
from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.tools.memory import MemoryTool

_LOCK_PATH = Path(".rush/memory-maintenance.lock")


def _seed_candidate_rows(root: Path, count: int) -> None:
    store = TypedArtifactStore(root)
    for i in range(count):
        store.write(
            MemoryArtifact(
                id=f"candidate-{i}",
                family="memory",
                subject="domain_knowledge",
                trust_tier="DERIVED",
                content={"note": i},
                source=f"tool-{i}",
                created_at=time.time() + i,
            )
        )


def test_maintenance_cycle_acquires_and_releases_lock(
    tmp_path: Path, monkeypatch
) -> None:
    """T-62.05: `run_maintenance_cycle()` calls `MeshLockManager.acquire`/`release` (spy),
    releasing even when the cycle body raises."""
    monkeypatch.chdir(tmp_path)
    original_acquire = MeshLockManager.acquire
    original_release = MeshLockManager.release
    with (
        patch.object(MeshLockManager, "acquire", autospec=True) as spy_acquire,
        patch.object(MeshLockManager, "release", autospec=True) as spy_release,
    ):
        spy_acquire.side_effect = original_acquire
        spy_release.side_effect = original_release

        result = run_maintenance_cycle("promotion_sweep")
        assert isinstance(result, MaintenanceRunResult)
        assert spy_acquire.call_count == 1
        assert spy_release.call_count == 1

        # An unrecognized task isn't in _SELECT_SQL, so the cycle body raises KeyError
        # before any row processing — release() must still fire (T-62.05's actual intent).
        with pytest.raises(KeyError):
            run_maintenance_cycle("not_a_real_task")  # type: ignore[arg-type]
        assert spy_acquire.call_count == 2
        assert spy_release.call_count == 2


def test_maintenance_cycle_respects_batch_size_parameter(
    tmp_path: Path, monkeypatch
) -> None:
    """T-62.06: 600 candidate rows seeded; `batch_size=500` processes exactly 500, and a
    separate `batch_size=50` call processes exactly 50 — proving a real parameter, not a
    hardcoded constant."""
    root_500 = tmp_path / "run-500"
    root_500.mkdir()
    monkeypatch.chdir(root_500)
    _seed_candidate_rows(root_500, 600)
    result_500 = run_maintenance_cycle("promotion_sweep", batch_size=500)
    assert result_500.processed == 500

    root_50 = tmp_path / "run-50"
    root_50.mkdir()
    monkeypatch.chdir(root_50)
    _seed_candidate_rows(root_50, 600)
    result_50 = run_maintenance_cycle("promotion_sweep", batch_size=50)
    assert result_50.processed == 50


def test_expired_lease_reclaimed_by_second_cycle_survives_first_cycles_stale_release(
    tmp_path: Path, monkeypatch
) -> None:
    """T-62.21: cycle A's lease expires mid-run; cycle B reclaims the lock (new generation,
    same fixed `agent_id`); cycle A's stale `release()` (via its now-stale capability) must
    return `False` and must not delete cycle B's live lock."""
    monkeypatch.chdir(tmp_path)
    mgr = MeshLockManager()

    acquired_a, cap_a = mgr.acquire(
        _LOCK_PATH,
        agent_id="memory-maintenance",
        timeout_s=1.0,
        ttl_s=0.05,
        return_capability=True,
    )
    assert acquired_a is True
    assert cap_a is not None
    generation_a = MeshLockManager.inspect(tmp_path, _LOCK_PATH)["generation"]

    time.sleep(0.15)  # let cycle A's lease expire

    acquired_b, cap_b = mgr.acquire(
        _LOCK_PATH,
        agent_id="memory-maintenance",
        timeout_s=1.0,
        ttl_s=60.0,
        return_capability=True,
    )
    assert acquired_b is True
    assert cap_b is not None

    state_before = MeshLockManager.inspect(tmp_path, _LOCK_PATH)
    assert state_before["state"] == "held"
    generation_b = state_before["generation"]
    assert generation_b > generation_a

    # Cycle A's cleanup runs against its now-stale capability.
    assert mgr.release(_LOCK_PATH, capability=cap_a) is False

    state_after = MeshLockManager.inspect(tmp_path, _LOCK_PATH)
    assert state_after["state"] == "held"
    assert state_after["generation"] == generation_b


def test_memory_tool_maintain_operation_dispatches_to_run_maintenance_cycle(
    tmp_path: Path, monkeypatch
) -> None:
    """T-62.22: `MemoryTool()(operation="maintain", task="promotion_sweep")` dispatches to
    `run_maintenance_cycle(task="promotion_sweep")`, via the registered "maintain" operation
    (not only reachable by directly importing `run_maintenance_cycle` in a test)."""
    monkeypatch.chdir(tmp_path)
    stub_result = MaintenanceRunResult(
        task="promotion_sweep", processed=0, changed=0, errors=()
    )
    with patch.object(memory_module, "run_maintenance_cycle") as spy:
        spy.return_value = stub_result
        result = MemoryTool()(
            tmp_path,
            operation="maintain",
            task="promotion_sweep",
            allow_cache_write=True,
        )

    spy.assert_called_once_with(
        "promotion_sweep", batch_size=500, project_root=tmp_path.resolve()
    )
    assert result["status"] == "ok"
    assert result["metadata"]["operation"] == "maintain"
